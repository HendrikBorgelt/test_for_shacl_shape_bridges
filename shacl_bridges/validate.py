"""
Bridge mapping validator.

Runs structural and semantic checks on a loaded :class:`BridgeMapping` and
returns a list of :class:`ValidationIssue` objects. An empty list means the
mapping passed all checks.

CLI usage::

    shacl-bridges validate my_bridge.yaml

Python usage::

    from shacl_bridges.io.yaml_reader import load_mapping
    from shacl_bridges.validate import validate_mapping, Severity

    mapping = load_mapping("bridge.yaml")
    issues = validate_mapping(mapping)
    errors = [i for i in issues if i.severity == Severity.ERROR]
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

import networkx as nx

from shacl_bridges.core.graph import check_connectivity, select_root_class
from shacl_bridges.io.yaml_reader import BridgeMapping


# ---------------------------------------------------------------------------
# Issue types
# ---------------------------------------------------------------------------

class Severity(str, Enum):
    ERROR = "error"
    WARNING = "warning"


@dataclass
class ValidationIssue:
    """A single validation finding."""

    severity: Severity
    message: str
    hint: str = field(default="")

    def __str__(self) -> str:
        icon = "✗" if self.severity == Severity.ERROR else "⚠"
        line = f"{icon}  {self.message}"
        if self.hint:
            line += f"\n   hint: {self.hint}"
        return line


# ---------------------------------------------------------------------------
# Standard prefixes that don't need to be declared
# ---------------------------------------------------------------------------

_BUILTIN_PREFIXES: frozenset[str] = frozenset({
    "rdf", "rdfs", "xsd", "owl", "sh",
    "skos", "semapv", "dcterms", "dc", "prov",
})


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _all_curies(mapping: BridgeMapping) -> list[str]:
    """Collect every CURIE used anywhere in the mapping (for prefix checks)."""
    curies: list[str] = []
    for s, p, o in mapping.source_pattern.triples:
        curies.extend([s, p, o])
    for s, p, o in mapping.target_pattern.triples:
        curies.extend([s, p, o])
    for entry in mapping.class_map:
        curies.extend([entry.source, entry.target])
        if entry.justification:
            curies.append(entry.justification)
    if mapping.source_pattern.root:
        curies.append(mapping.source_pattern.root)
    return curies


def _source_nodes(mapping: BridgeMapping) -> set[str]:
    return {n for t in mapping.source_pattern.triples for n in (t[0], t[2])}


def _target_nodes(mapping: BridgeMapping) -> set[str]:
    return {n for t in mapping.target_pattern.triples for n in (t[0], t[2])}


# ---------------------------------------------------------------------------
# Public validator
# ---------------------------------------------------------------------------

def validate_mapping(mapping: BridgeMapping) -> list[ValidationIssue]:
    """Run all validation checks on *mapping*.

    Checks performed:

    1. **Prefix completeness** — every CURIE used references a declared prefix
       (or a well-known built-in).
    2. **Root exists** — ``source_pattern.root`` (if set) appears in at least
       one source triple.
    3. **Source connectivity** — every node in ``source_pattern`` is reachable
       from the chosen root. Disconnected nodes would cause silent over-matching.
    4. **Class-map sources ⊆ source nodes** — every ``class_map[].source`` appears
       in ``source_pattern.triples``.
    5. **Class-map targets ⊆ target nodes** — every ``class_map[].target`` appears
       in ``target_pattern.triples``.
    6. **Target connectivity** — the target pattern forms a connected graph.
       Disconnected target nodes produce isolated triples in the bridge output.

    Args:
        mapping: A loaded :class:`~shacl_bridges.io.yaml_reader.BridgeMapping`.

    Returns:
        List of :class:`ValidationIssue` objects. An empty list means the
        mapping passed all checks.
    """
    issues: list[ValidationIssue] = []

    # ------------------------------------------------------------------
    # 1. Prefix completeness
    # ------------------------------------------------------------------
    declared = set(mapping.prefixes.keys()) | _BUILTIN_PREFIXES
    seen_bad_prefixes: set[str] = set()
    for curie in _all_curies(mapping):
        if ":" in curie and not curie.startswith(("http", "urn", "_")):
            prefix = curie.split(":")[0]
            if prefix not in declared and prefix not in seen_bad_prefixes:
                seen_bad_prefixes.add(prefix)
                issues.append(ValidationIssue(
                    Severity.ERROR,
                    f"Prefix '{prefix}' (used in '{curie}') is not declared in prefixes",
                    f"Add '{prefix}: <namespace_IRI>' to the prefixes block",
                ))

    # ------------------------------------------------------------------
    # 2. Root exists in source_pattern
    # ------------------------------------------------------------------
    root = mapping.source_pattern.root
    src_nodes = _source_nodes(mapping)
    if root and root not in src_nodes:
        issues.append(ValidationIssue(
            Severity.ERROR,
            f"source_pattern.root '{root}' does not appear in any source_pattern triple",
            "Check for typos or add a triple that involves this class",
        ))

    # ------------------------------------------------------------------
    # 3. Source graph connectivity from root
    # ------------------------------------------------------------------
    if mapping.source_pattern.triples:
        try:
            effective_root = select_root_class(mapping.source_pattern.triples, root)
            # Skip connectivity check if root was already flagged as absent (check 2)
            if effective_root not in src_nodes:
                effective_root = select_root_class(mapping.source_pattern.triples, None)
            disconnected = check_connectivity(mapping.source_pattern.triples, effective_root)
            for node in disconnected:
                issues.append(ValidationIssue(
                    Severity.WARNING,
                    f"'{node}' is not reachable from root '{effective_root}' in source_pattern",
                    (
                        "This node will be omitted from the SPARQL WHERE clause, "
                        "causing silent over-matching. Set a different source_pattern.root "
                        "or connect this node to the rest of the pattern."
                    ),
                ))
        except ValueError as exc:
            issues.append(ValidationIssue(Severity.ERROR, str(exc)))

    # ------------------------------------------------------------------
    # 4. Class-map sources ⊆ source_pattern nodes
    # ------------------------------------------------------------------
    for entry in mapping.class_map:
        if entry.source not in src_nodes:
            issues.append(ValidationIssue(
                Severity.ERROR,
                f"class_map source '{entry.source}' does not appear in source_pattern.triples",
                (
                    "Add a source_pattern triple that involves this class, "
                    "or remove the class_map entry"
                ),
            ))

    # ------------------------------------------------------------------
    # 5. Class-map targets ⊆ target_pattern nodes
    # ------------------------------------------------------------------
    tgt_nodes = _target_nodes(mapping)
    for entry in mapping.class_map:
        if entry.target not in tgt_nodes:
            issues.append(ValidationIssue(
                Severity.ERROR,
                f"class_map target '{entry.target}' does not appear in target_pattern.triples",
                (
                    "Add a target_pattern triple that involves this class, "
                    "or remove the class_map entry"
                ),
            ))

    # ------------------------------------------------------------------
    # 6. Target pattern connectivity
    # ------------------------------------------------------------------
    if len(mapping.target_pattern.triples) > 1:
        G_tgt = nx.DiGraph()
        for s, _p, o in mapping.target_pattern.triples:
            G_tgt.add_edge(s, o)
        if not nx.is_weakly_connected(G_tgt):
            issues.append(ValidationIssue(
                Severity.WARNING,
                "target_pattern.triples do not form a connected graph",
                (
                    "Disconnected target nodes may produce isolated triples "
                    "in the bridge output that are hard to trace"
                ),
            ))

    return issues

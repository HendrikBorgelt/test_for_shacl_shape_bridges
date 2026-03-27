"""
YAML-based bridge mapping loader.

A mapping is defined in a single YAML file (conventionally named ``bridge.yaml``)
with five top-level sections:

* ``metadata``        — title, version, creator, license, default justification
* ``prefixes``        — namespace declarations (prefix → IRI)
* ``source_pattern``  — S-P-O triples defining the source design pattern; optional ``root`` override
* ``target_pattern``  — S-P-O triples defining the target design pattern
* ``class_map``       — explicit alignment between source and target classes

See ``docs/yaml_format.md`` for the full schema and annotated example.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


# ---------------------------------------------------------------------------
# Type aliases
# ---------------------------------------------------------------------------

Triple = tuple[str, str, str]
"""A (subject, predicate, object) triple where all three are CURIE strings."""


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class Metadata:
    """Human-readable metadata about the bridge mapping."""

    title: str = ""
    version: str = "0.1.0"
    creator: str = ""
    license: str = ""
    mapping_justification: str = "semapv:ManualMappingCuration"
    """Default justification applied to all class-map entries that don't override it."""


@dataclass
class SourcePattern:
    """The source design pattern: a list of S-P-O triples and an optional root override."""

    triples: list[Triple]
    """All triples (core structural + peripheral validation) of the source pattern."""

    root: str | None = None
    """CURIE of the class that should anchor ``sh:targetClass`` and ``?this``.
    When *None* the root is computed automatically via closeness centrality."""


@dataclass
class TargetPattern:
    """The target design pattern: the triples that the bridge CONSTRUCT will produce."""

    triples: list[Triple]


@dataclass
class ClassMapEntry:
    """A single source-class → target-class alignment.

    For a standard 1-to-1 mapping leave *derived_iri* as *None*.

    For **instance-split** mappings — where one source instance must become two
    target instances (e.g. a conflated "Agent+Role" class splitting into a
    separate ``Agent`` and ``AgentRole``) — add a second entry for the same
    *source* class with ``derived_iri`` set.  The tool will mint a new IRI for
    the derived instance at query time.

    Supported ``derived_iri`` forms:

    * ``"suffix:<string>"`` — append *<string>* to the source instance IRI.
      Example: ``suffix:_role`` turns ``ex:agent1`` into ``ex:agent1_role``.
    """

    source: str
    """CURIE of the source class (must appear in ``source_pattern.triples``)."""

    target: str
    """CURIE of the target class (must appear in ``target_pattern.triples``)."""

    justification: str | None = None
    """SSSOM-style justification CURIE, e.g. ``semapv:ManualMappingCuration``."""

    comment: str | None = None
    """Human-readable explanation of why this mapping is valid."""

    derived_iri: str | None = None
    """IRI minting rule for instance-split targets (see class docstring).
    When *None* the target instance reuses the source instance IRI (standard case)."""


@dataclass
class BridgeMapping:
    """All information that defines one bridge mapping.

    Load with :func:`load_mapping`. Validate with
    :func:`~shacl_bridges.validate.validate_mapping`.
    """

    prefixes: dict[str, str]
    """Namespace declarations: ``{prefix: IRI}``."""

    source_pattern: SourcePattern
    """The source design pattern with its triples and optional root override."""

    target_pattern: TargetPattern
    """The target design pattern triples."""

    class_map: list[ClassMapEntry]
    """Alignment between source and target classes."""

    metadata: Metadata = field(default_factory=Metadata)
    """Title, version, creator, license, default justification."""

    # ------------------------------------------------------------------
    # Convenience accessors
    # ------------------------------------------------------------------

    def prefix_map(self) -> dict[str, str]:
        """Return ``{prefix: namespace}`` dict for SHACL/SPARQL generation."""
        return dict(self.prefixes)

    def root_class(self) -> str | None:
        """Return the explicitly declared root class CURIE, or *None*."""
        return self.source_pattern.root

    def class_alignment(self) -> dict[str, str]:
        """Return ``{source_curie: target_curie}`` for **regular** (non-derived) entries.

        Entries with a ``derived_iri`` represent *new* instances minted at query
        time and are intentionally excluded here — they are accessed via
        :meth:`derived_class_map` and handled separately by the SPARQL builder.

        When the same source class appears in both a regular and a derived entry
        the regular (non-derived) entry wins and sets the primary ``?this``
        target type.
        """
        result: dict[str, str] = {}
        for e in self.class_map:
            if e.derived_iri is None and e.source not in result:
                result[e.source] = e.target
        return result

    def derived_class_map(self) -> list[ClassMapEntry]:
        """Return only the entries that carry a ``derived_iri`` (instance-split targets)."""
        return [e for e in self.class_map if e.derived_iri is not None]

    def source_classes(self) -> set[str]:
        """Return the set of source CURIEs declared in the class map."""
        return {e.source for e in self.class_map}

    def target_classes(self) -> set[str]:
        """Return the set of target CURIEs declared in the class map (regular + derived)."""
        return {e.target for e in self.class_map}


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

def _parse_triple(t: Any) -> Triple:
    """Parse a YAML list ``[s, p, o]`` into a :data:`Triple`."""
    if not isinstance(t, (list, tuple)) or len(t) != 3:
        raise ValueError(
            f"Each triple must be a list of exactly three strings [subject, predicate, object],"
            f" got {t!r}"
        )
    return (str(t[0]), str(t[1]), str(t[2]))


def _require(data: dict, key: str, location: str = "") -> Any:
    if key not in data:
        loc = f" (in {location})" if location else ""
        raise ValueError(f"Bridge YAML missing required key '{key}'{loc}")
    return data[key]


# ---------------------------------------------------------------------------
# Public loader
# ---------------------------------------------------------------------------

def load_mapping(path: str | Path) -> BridgeMapping:
    """Load a :class:`BridgeMapping` from a YAML file.

    Args:
        path: Path to the ``bridge.yaml`` file.

    Returns:
        Parsed and structurally validated :class:`BridgeMapping`.

    Raises:
        ValueError: If required keys are missing or triples are malformed.
        FileNotFoundError: If *path* does not exist.
    """
    path = Path(path)
    with path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if not isinstance(data, dict):
        raise ValueError(
            f"{path}: YAML root must be a mapping, got {type(data).__name__}"
        )

    # metadata (optional)
    m = data.get("metadata", {}) or {}
    metadata = Metadata(
        title=str(m.get("title", "")),
        version=str(m.get("version", "0.1.0")),
        creator=str(m.get("creator", "")),
        license=str(m.get("license", "")),
        mapping_justification=str(
            m.get("mapping_justification", "semapv:ManualMappingCuration")
        ),
    )

    # prefixes (required)
    raw_prefixes = _require(data, "prefixes")
    if not isinstance(raw_prefixes, dict):
        raise ValueError("'prefixes' must be a mapping of prefix → namespace IRI")
    prefixes = {str(k): str(v) for k, v in raw_prefixes.items()}

    # source_pattern (required)
    sp_raw = _require(data, "source_pattern")
    source_triples_raw = _require(sp_raw, "triples", "source_pattern")
    source_pattern = SourcePattern(
        root=sp_raw.get("root"),
        triples=[_parse_triple(t) for t in source_triples_raw],
    )

    # target_pattern (required)
    tp_raw = _require(data, "target_pattern")
    target_triples_raw = _require(tp_raw, "triples", "target_pattern")
    target_pattern = TargetPattern(
        triples=[_parse_triple(t) for t in target_triples_raw],
    )

    # class_map (required)
    cm_raw = _require(data, "class_map")
    if not isinstance(cm_raw, list):
        raise ValueError("'class_map' must be a list of {source, target, ...} entries")
    class_map: list[ClassMapEntry] = []
    for i, entry in enumerate(cm_raw):
        if not isinstance(entry, dict):
            raise ValueError(
                f"class_map[{i}] must be a mapping, got {type(entry).__name__}"
            )
        derived_iri_raw = entry.get("derived_iri")
        if derived_iri_raw is not None:
            derived_iri_raw = str(derived_iri_raw)
            if not derived_iri_raw.startswith("suffix:"):
                raise ValueError(
                    f"class_map[{i}].derived_iri: unsupported form {derived_iri_raw!r}."
                    " Currently supported: 'suffix:<string>'"
                )
        class_map.append(ClassMapEntry(
            source=str(_require(entry, "source", f"class_map[{i}]")),
            target=str(_require(entry, "target", f"class_map[{i}]")),
            justification=entry.get("justification"),
            comment=entry.get("comment"),
            derived_iri=derived_iri_raw,
        ))

    return BridgeMapping(
        metadata=metadata,
        prefixes=prefixes,
        source_pattern=source_pattern,
        target_pattern=target_pattern,
        class_map=class_map,
    )

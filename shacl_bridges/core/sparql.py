"""
SPARQL CONSTRUCT query generation.

Generates the ``CONSTRUCT { ... } WHERE { ... }`` block that is embedded inside
a ``sh:SPARQLRule``. The WHERE clause is always anchored to ``?this`` (the SHACL
convention for the focused node), which guarantees that only subgraphs that are
fully connected to the root class are matched.

Variable naming:
  - ``?this`` — the focused node (bound to the root class by SHACL)
  - ``?var_<suffix>`` — auto-generated variables for all other nodes, where
    *suffix* is a letter sequence (a, b, c, … z, aa, ab, …)
"""

from __future__ import annotations

from shacl_bridges.io.yaml_reader import ClassMapEntry, Triple


# ---------------------------------------------------------------------------
# Variable name generation
# ---------------------------------------------------------------------------

def _generate_variable_names(entities: list[str]) -> dict[str, str]:
    """Map each unique entity label to a SPARQL variable name.

    Variables are named ``?var_a``, ``?var_b``, … to keep generated SPARQL concise.

    Args:
        entities: Ordered list of unique entity CURIEs/labels.

    Returns:
        ``{entity: "?var_x"}`` mapping.
    """
    mapping: dict[str, str] = {}
    alphabet = "abcdefghijklmnopqrstuvwxyz"
    counter = 0
    for entity in entities:
        if entity not in mapping:
            if counter < 26:
                suffix = alphabet[counter]
            else:
                first = alphabet[(counter // 26) - 1]
                second = alphabet[counter % 26]
                suffix = first + second
            mapping[entity] = f"?var_{suffix}"
            counter += 1
    return mapping


# ---------------------------------------------------------------------------
# Public query builder
# ---------------------------------------------------------------------------

def build_sparql_construct(
    class_alignment: dict[str, str],
    source_triples: list[Triple],
    target_triples: list[Triple],
    root_class: str,
    prefix_map: dict[str, str],
    derived_entries: list[ClassMapEntry] | None = None,
) -> str:
    """Generate a SPARQL CONSTRUCT query from the bridge mapping.

    The WHERE clause:
    - Binds ``?this`` to the *root_class* (``?this rdf:type <root_class>``)
    - Includes only *core* source triples — those where both the subject and object
      are source classes present in *class_alignment*. Peripheral/upper-level triples
      (e.g. ``ex:Process isSome ex:ChemicalInvestigation``) exist only at the TBox
      level and are omitted from the SPARQL pattern.
    - Every core triple produces type assertions for the non-root nodes.
    - For each *derived_entry* a ``BIND(IRI(CONCAT(STR(?this), "…")) AS ?derived_X)``
      line is appended to mint a fresh IRI for the split-off instance.

    The CONSTRUCT clause:
    - Asserts new ``rdf:type`` triples for each source → target class mapping
    - Asserts new ``rdf:type`` triples for each derived entry (instance split)
    - Asserts the target-pattern relation triples, with variables resolved via the
      reverse of *class_alignment* and the derived variable map

    Args:
        class_alignment: ``{source_curie: target_curie}`` from the **regular**
            (non-derived) class-map entries.
        source_triples: All triples from ``source_pattern.triples``.
        target_triples: All triples from ``target_pattern.triples``.
        root_class: CURIE of the root class (the ``sh:targetClass``).
        prefix_map: ``{prefix: namespace}`` dict (used for context; not embedded here).
        derived_entries: Entries with a ``derived_iri`` field — each describes one
            instance to be split off from the source and assigned a minted IRI.

    Returns:
        SPARQL CONSTRUCT string (without ``PREFIX`` declarations — those are
        emitted separately as ``sh:prefixes`` blocks in the SHACL shape).
    """
    derived_entries = derived_entries or []
    source_classes = set(class_alignment.keys())

    # Collect all source-side entities in a stable order so variable
    # assignment is deterministic. Class-map sources come first so they
    # always get the lowest-suffix variables.
    all_source_entities: list[str] = []
    seen: set[str] = set()

    for src in class_alignment:
        if src not in seen:
            all_source_entities.append(src)
            seen.add(src)
    for s, _p, o in source_triples:
        for v in (s, o):
            if v not in seen:
                all_source_entities.append(v)
                seen.add(v)

    var_map = _generate_variable_names(all_source_entities)
    var_map[root_class] = "?this"  # root class always binds to ?this

    # ------------------------------------------------------------------
    # Derived-entry variable map
    # Maps each derived target CURIE to a fresh SPARQL variable name.
    # Variable name: ?derived_<LocalName> where LocalName is the part
    # after the last ":" in the CURIE.
    # ------------------------------------------------------------------
    derived_var_map: dict[str, str] = {}
    for entry in derived_entries:
        local = entry.target.split(":")[-1]
        derived_var_map[entry.target] = f"?derived_{local}"

    # ------------------------------------------------------------------
    # WHERE clause
    # ------------------------------------------------------------------
    # Only include source triples where BOTH subject and object are source
    # classes in the class_alignment. Upper-level / taxonomic triples are
    # excluded — they apply only at the TBox level, not in instance data.
    where_lines: list[str] = [f"  ?this rdf:type {root_class} ."]

    for s, p, o in source_triples:
        if s in source_classes and o in source_classes:
            s_var = var_map.get(s, f"?{s}")
            o_var = var_map.get(o, f"?{o}")
            where_lines.append(f"  {s_var} {p} {o_var} .")
            if s != root_class:
                where_lines.append(f"  {s_var} rdf:type {s} .")
            where_lines.append(f"  {o_var} rdf:type {o} .")

    where_lines = list(dict.fromkeys(where_lines))  # deduplicate preserving order

    # BIND lines for derived (instance-split) entries come after pattern triples.
    for entry in derived_entries:
        suffix = entry.derived_iri[len("suffix:"):]   # strip "suffix:" prefix
        var_name = derived_var_map[entry.target]
        where_lines.append(
            f'  BIND(IRI(CONCAT(STR(?this), "{suffix}")) AS {var_name})'
        )

    # ------------------------------------------------------------------
    # CONSTRUCT clause
    # ------------------------------------------------------------------
    construct_lines: list[str] = []
    seen_construct: set[str] = set()

    # 1. rdf:type assertions: each source instance is also asserted as its target type.
    # Blank-node targets (``_:label``) are skipped — blank nodes have no fixed rdf:type.
    for src, tgt in class_alignment.items():
        if tgt.startswith("_:"):
            continue
        src_var = var_map.get(src, f"?{src}")
        line = f"  {src_var} rdf:type {tgt} ."
        if line not in seen_construct:
            construct_lines.append(line)
            seen_construct.add(line)

    # 2. rdf:type assertions for derived (instance-split) targets.
    for entry in derived_entries:
        var_name = derived_var_map[entry.target]
        line = f"  {var_name} rdf:type {entry.target} ."
        if line not in seen_construct:
            construct_lines.append(line)
            seen_construct.add(line)

    # 3. Target-pattern relation triples.
    # Resolve target classes back to their source variables via the reverse map,
    # falling back to derived_var_map for split-off nodes.
    # Blank-node labels (``_:label``) pass through verbatim — SPARQL CONSTRUCT
    # creates a fresh blank node for each solution row.
    rev_alignment = {tgt: src for src, tgt in class_alignment.items()}

    def _resolve_target_node(node: str) -> str:
        """Return the SPARQL term for a target-pattern node."""
        if node.startswith("_:"):
            return node  # blank node label — kept as-is in CONSTRUCT
        if node in derived_var_map:
            return derived_var_map[node]  # derived / minted instance
        src = rev_alignment.get(node)
        return var_map.get(src) if src else f"<{node}>"

    for s, p, o in target_triples:
        s_var = _resolve_target_node(s)
        o_var = _resolve_target_node(o)
        line = f"  {s_var} {p} {o_var} ."
        if line not in seen_construct:
            construct_lines.append(line)
            seen_construct.add(line)

    construct_block = "\n".join(construct_lines)
    where_block = "\n".join(where_lines)

    return f"CONSTRUCT {{\n{construct_block}\n}}\nWHERE {{\n{where_block}\n}}"

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

from shacl_bridges.io.yaml_reader import Triple


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
) -> str:
    """Generate a SPARQL CONSTRUCT query from the bridge mapping.

    The WHERE clause:
    - Binds ``?this`` to the *root_class* (``?this rdf:type <root_class>``)
    - Includes only *core* source triples — those where both the subject and object
      are source classes present in *class_alignment*. Peripheral/upper-level triples
      (e.g. ``ex:Process isSome ex:ChemicalInvestigation``) exist only at the TBox
      level and are omitted from the SPARQL pattern.
    - Every core triple produces type assertions for the non-root nodes.

    The CONSTRUCT clause:
    - Asserts new ``rdf:type`` triples for each source → target class mapping
    - Asserts the target-pattern relation triples, with variables resolved via the
      reverse of *class_alignment*

    Args:
        class_alignment: ``{source_curie: target_curie}`` from the class map.
        source_triples: All triples from ``source_pattern.triples``.
        target_triples: All triples from ``target_pattern.triples``.
        root_class: CURIE of the root class (the ``sh:targetClass``).
        prefix_map: ``{prefix: namespace}`` dict (used for context; not embedded here).

    Returns:
        SPARQL CONSTRUCT string (without ``PREFIX`` declarations — those are
        emitted separately as ``sh:prefixes`` blocks in the SHACL shape).
    """
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

    # ------------------------------------------------------------------
    # CONSTRUCT clause
    # ------------------------------------------------------------------
    construct_lines: list[str] = []
    seen_construct: set[str] = set()

    # 1. rdf:type assertions: each source instance is also asserted as its target type
    for src, tgt in class_alignment.items():
        src_var = var_map.get(src, f"?{src}")
        line = f"  {src_var} rdf:type {tgt} ."
        if line not in seen_construct:
            construct_lines.append(line)
            seen_construct.add(line)

    # 2. Target-pattern relation triples
    # Resolve target classes back to their source variables via the reverse map.
    rev_alignment = {tgt: src for src, tgt in class_alignment.items()}

    for s, p, o in target_triples:
        s_source = rev_alignment.get(s)
        o_source = rev_alignment.get(o)
        s_var = var_map.get(s_source) if s_source else f"<{s}>"
        o_var = var_map.get(o_source) if o_source else f"<{o}>"
        line = f"  {s_var} {p} {o_var} ."
        if line not in seen_construct:
            construct_lines.append(line)
            seen_construct.add(line)

    construct_block = "\n".join(construct_lines)
    where_block = "\n".join(where_lines)

    return f"CONSTRUCT {{\n{construct_block}\n}}\nWHERE {{\n{where_block}\n}}"

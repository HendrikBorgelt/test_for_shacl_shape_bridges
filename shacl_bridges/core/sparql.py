"""
SPARQL CONSTRUCT query generation.

Generates the ``CONSTRUCT { ... } WHERE { ... }`` block that is embedded inside
a ``sh:SPARQLRule``.  The WHERE clause is always anchored to ``?this`` (the SHACL
convention for the focused node), which guarantees that only subgraphs that are
fully connected to the target class are matched.

Variable naming:
  - ``?this`` — the focused node (bound to the root class by SHACL)
  - ``?var_<suffix>`` — auto-generated variables for all other nodes, where
    *suffix* is a letter sequence (a, b, c, … z, aa, ab, …)
"""

from __future__ import annotations

import pandas as pd


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
    shape_bridge: pd.DataFrame,
    shape_validation: pd.DataFrame,
    root_class: str,
    prefix_map: dict[str, str],
) -> str:
    """Generate a SPARQL CONSTRUCT query from bridge and validation tables.

    The WHERE clause:
    - Binds ``?this`` to the *root_class* (``?this rdf:type <root_class>``)
    - Traverses all relationships from *shape_validation* starting at the root,
      ensuring a connected pattern
    - Every entity from *shape_bridge* that also appears in *shape_validation*
      gets the same variable, so CONSTRUCT can reference it

    The CONSTRUCT clause:
    - Asserts new ``rdf:type`` triples mapping source classes to target classes
    - Asserts new relation triples between target instances

    Args:
        shape_bridge: DataFrame with columns ``from_id``, ``to_id``,
                      ``relation_id``, ``target_id``.
        shape_validation: DataFrame with columns ``subject_id``, ``predicate_id``,
                          ``object_id``.
        root_class: CURIE of the root class (the ``sh:targetClass``).
        prefix_map: ``{prefix: namespace}`` dict for CURIE resolution.

    Returns:
        SPARQL CONSTRUCT string (without ``PREFIX`` declarations — those are
        emitted separately as ``sh:prefixes`` blocks in the SHACL shape).
    """
    # Collect all unique source-side entities in a stable order so variable
    # assignment is deterministic.
    all_source_entities: list[str] = []
    seen: set[str] = set()

    # Root first so it always gets ?this (handled specially below)
    for col in ("from_id",):
        for val in shape_bridge[col].dropna():
            if val and val not in seen:
                all_source_entities.append(val)
                seen.add(val)

    for col in ("subject_id", "object_id"):
        for val in shape_validation[col].dropna():
            if val and val not in seen:
                all_source_entities.append(val)
                seen.add(val)

    var_map = _generate_variable_names(all_source_entities)

    # Override: root class → ?this
    var_map[root_class] = "?this"

    # ------------------------------------------------------------------
    # WHERE clause
    # ------------------------------------------------------------------
    # Only include shape_validation rows where BOTH subject and object are
    # source classes being bridged (appear in shape_bridge.from_id).
    # Upper-level / taxonomic triples (e.g. Process isSome ChemicalInvestigation)
    # only exist at the TBox level — not in instance data — and belong only in
    # the nested sh:property constraints, not in the SPARQL WHERE clause.
    source_classes: set[str] = set(shape_bridge["from_id"].dropna().astype(str))
    core_sv = shape_validation[
        shape_validation["subject_id"].isin(source_classes)
        & shape_validation["object_id"].isin(source_classes)
    ]

    where_lines: list[str] = []

    # Root type assertion (anchors ?this)
    where_lines.append(f"  ?this rdf:type {root_class} .")

    # Relationship traversal from core shape_validation only
    for _, row in core_sv.iterrows():
        subj = row["subject_id"]
        pred = row["predicate_id"]
        obj = row["object_id"]
        subj_var = var_map.get(subj, f"?{subj}")
        obj_var = var_map.get(obj, f"?{obj}")
        where_lines.append(f"  {subj_var} {pred} {obj_var} .")
        if subj != root_class:
            where_lines.append(f"  {subj_var} rdf:type {subj} .")
        where_lines.append(f"  {obj_var} rdf:type {obj} .")

    where_lines = list(dict.fromkeys(where_lines))  # deduplicate preserving order

    # ------------------------------------------------------------------
    # CONSTRUCT clause
    # ------------------------------------------------------------------
    construct_lines: list[str] = []

    # Build a lookup: from_id → to_id (for variable reuse)
    from_to: dict[str, str] = {}
    for _, row in shape_bridge.iterrows():
        fid = str(row["from_id"])
        tid = str(row["to_id"])
        if fid and tid and tid not in ("-", ""):
            from_to[fid] = tid

    # Type mappings: each source instance also becomes the target type
    seen_type_lines: set[str] = set()
    for from_id, to_id in from_to.items():
        src_var = var_map.get(from_id, f"?{from_id}")
        line = f"  {src_var} rdf:type {to_id} ."
        if line not in seen_type_lines:
            construct_lines.append(line)
            seen_type_lines.add(line)

    # Relation mappings
    for _, row in shape_bridge.iterrows():
        from_id = str(row["from_id"])
        relation = str(row.get("relation_id", ""))
        target = str(row.get("target_id", ""))
        if not relation or relation in ("-", "") or not target or target in ("-", ""):
            continue
        # The subject of the new relation is the source variable (same instance)
        src_var = var_map.get(from_id, f"?{from_id}")
        # The object variable: find the from_id that maps to target_id
        target_from = next(
            (fid for fid, tid in from_to.items() if tid == target), None
        )
        if target_from is None:
            # target_id is referenced directly — try var_map
            tgt_var = var_map.get(target, f"?{target}")
        else:
            tgt_var = var_map.get(target_from, f"?{target_from}")
        line = f"  {src_var} {relation} {tgt_var} ."
        if line not in construct_lines:
            construct_lines.append(line)

    construct_block = "\n".join(construct_lines)
    where_block = "\n".join(where_lines)

    return f"CONSTRUCT {{\n{construct_block}\n}}\nWHERE {{\n{where_block}\n}}"

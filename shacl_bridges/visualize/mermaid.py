"""
Mermaid flowchart generation.

Produces a Mermaid ``flowchart TD`` diagram that shows:
- Common nodes (shared by both source and target patterns) — rectangle ``[Label]``
- Source-only nodes (only in shape validation) — stadium shape ``([Label])``
- Target-only nodes (only in shape bridge) — rounded rectangle ``(Label)``
- ShapeValidation subgraph: core relationships (double arrow ``==>``) and
  extended validation edges (long dashed arrow)
- TransformedGraph subgraph: target pattern relationships
- SHACL bridge edges (dotted arrow connecting source to target classes)

The arrow lengths are scaled to the longest path in the respective graphs to
give the diagram a consistent visual rhythm.
"""

from __future__ import annotations

from copy import deepcopy

import pandas as pd

from shacl_bridges.core.graph import (
    build_bridge_graph,
    build_validation_graph,
    longest_path_length,
)
from shacl_bridges.io.csv_reader import BridgeMapping


# ---------------------------------------------------------------------------
# CURIE helpers
# ---------------------------------------------------------------------------

def _curie_for(label: str, classes: pd.DataFrame) -> str:
    """Return the CURIE for *label* from the classes table, or *label* itself."""
    if classes.empty:
        return label
    row = classes.loc[classes["id"] == label]
    if not row.empty and "label" in classes.columns:
        return label  # already a CURIE/id
    # Try label column
    row = classes.loc[classes.get("label", pd.Series(dtype=str)) == label]
    if not row.empty:
        return str(row.iloc[0]["id"])
    return label


def _safe_node_id(curie: str) -> str:
    """Convert a CURIE like ``ex:Process`` to a Mermaid-safe node ID ``ex_Process``."""
    return curie.replace(":", "_").replace("#", "_").replace("/", "_").replace(".", "_")


# ---------------------------------------------------------------------------
# Main diagram generator
# ---------------------------------------------------------------------------

def generate_mermaid(mapping: BridgeMapping) -> str:
    """Generate a Mermaid flowchart diagram for *mapping*.

    Args:
        mapping: Loaded :class:`~shacl_bridges.io.csv_reader.BridgeMapping`.

    Returns:
        Mermaid diagram string (suitable for embedding in Markdown or saving to
        a ``.mmd`` file).
    """
    sv = mapping.shape_validation
    sb = deepcopy(mapping.shape_bridge)

    # Build graphs for path-length computation
    G_bridge = build_bridge_graph(sb)
    G_valid = build_validation_graph(sv)

    try:
        bridge_path_len = longest_path_length(G_bridge)
    except ValueError:
        bridge_path_len = 1
    try:
        valid_path_len = longest_path_length(G_valid)
    except ValueError:
        valid_path_len = 1

    # ------------------------------------------------------------------
    # Classify nodes: common / SV-only / SB-only
    # ------------------------------------------------------------------
    sv_nodes: set[str] = set(sv["subject_id"]) | set(sv["object_id"])
    sb_from_nodes: set[str] = set(sb["from_id"].dropna())
    sb_to_nodes: set[str] = set(sb["to_id"].dropna())
    sb_nodes = sb_from_nodes | sb_to_nodes

    common = sv_nodes & sb_from_nodes  # source classes that appear in both
    sv_only = sv_nodes - common
    sb_only = sb_to_nodes - set(sb["from_id"].dropna())

    lines: list[str] = ["flowchart TD"]

    # Node declarations
    for node in sorted(common):
        nid = _safe_node_id(node)
        lines.append(f'    {nid}["{node}"]')
    for node in sorted(sv_only):
        nid = _safe_node_id(node)
        lines.append(f'    {nid}(["  {node}  "])')
    for node in sorted(sb_only):
        nid = _safe_node_id(node)
        lines.append(f'    {nid}("{node}")')

    # ------------------------------------------------------------------
    # ShapeValidation subgraph
    # ------------------------------------------------------------------
    long_arrow = "-" * (bridge_path_len + 1) + ">"
    lines.append("")
    lines.append("    subgraph ShapeValidation")
    lines.append("        subgraph CoreShapeInformation")

    extended_lines: list[str] = []
    for _, row in sv.iterrows():
        subj = row["subject_id"]
        pred = row["predicate_id"]
        obj = row["object_id"]
        sid = _safe_node_id(subj)
        oid = _safe_node_id(obj)
        if subj in common and obj in common:
            lines.append(f'        {sid} ==>|"{pred}"| {oid}')
        else:
            extended_lines.append(f'    {sid} {long_arrow}|"{pred}"| {oid}')

    lines.append("        end")
    lines.extend(extended_lines)
    lines.append("    end")

    # ------------------------------------------------------------------
    # TransformedGraph subgraph
    # ------------------------------------------------------------------
    lines.append("")
    lines.append("    subgraph TransformedGraph")

    temp_to: str | None = None
    relation_lines: list[str] = []
    bridge_arrows: list[str] = []
    dotted = "-" + "." * (valid_path_len + bridge_path_len) + "->"

    for _, row in sb.iterrows():
        from_id = str(row["from_id"]) if pd.notna(row["from_id"]) else ""
        to_id = str(row["to_id"]) if pd.notna(row["to_id"]) else ""
        relation = str(row.get("relation_id", ""))
        target = str(row.get("target_id", ""))

        if from_id and to_id and from_id != to_id:
            temp_to = to_id
            fid = _safe_node_id(from_id)
            tid = _safe_node_id(to_id)
            bridge_arrows.append(f'    {fid} {dotted}|"bridge"| {tid}')

        if temp_to and relation and relation not in ("-", "") and target and target not in ("-", ""):
            tid = _safe_node_id(temp_to)
            tgt_id = _safe_node_id(target)
            relation_lines.append(f'    {tid} -->|"{relation}"| {tgt_id}')

    lines.extend(relation_lines)
    lines.append("    end")
    lines.append("")
    lines.extend(bridge_arrows)

    return "\n".join(lines)


def generate_mermaid_markdown(mapping: BridgeMapping) -> str:
    """Wrap the Mermaid diagram in a fenced code block for Markdown embedding."""
    diagram = generate_mermaid(mapping)
    return f"```mermaid\n{diagram}\n```"

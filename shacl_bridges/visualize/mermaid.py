"""
Mermaid flowchart generation.

Produces a Mermaid ``flowchart TD`` diagram that shows:

- **Core source nodes** (in class_map) — rectangle ``[Label]``
- **Peripheral source nodes** (validation-only, not in class_map) — stadium shape ``([Label])``
- **Target nodes** — rounded rectangle ``(Label)``
- **ShapeValidation** subgraph:
    - *CoreShapeInformation* inner subgraph: core structural triples (thick ``==>`` arrows)
    - Peripheral/upper-level triples outside the inner subgraph (thin ``--->`` arrows)
- **TransformedGraph** subgraph: target pattern triples (``-->`` arrows)
- Bridge connections: dotted ``-.....->`` arrows from each source class to its target class

This diagram is generated automatically from the YAML mapping and stays in sync
with the source/target patterns without manual maintenance.
"""

from __future__ import annotations

from shacl_bridges.core.graph import build_validation_graph, longest_path_length
from shacl_bridges.io.yaml_reader import BridgeMapping


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _local_name(curie: str) -> str:
    """Extract the local name from a CURIE (the part after the last ``:``).

    ``"ex:Process"`` → ``"Process"``.  Falls back to the full string if no
    colon is present.
    """
    return curie.split(":")[-1] if ":" in curie else curie


# ---------------------------------------------------------------------------
# Main diagram generator
# ---------------------------------------------------------------------------

def generate_mermaid(mapping: BridgeMapping) -> str:
    """Generate a Mermaid flowchart diagram for *mapping*.

    Args:
        mapping: Loaded :class:`~shacl_bridges.io.yaml_reader.BridgeMapping`.

    Returns:
        Mermaid diagram string (suitable for embedding in Markdown or saving
        to a ``.mmd`` file).
    """
    source_triples = mapping.source_pattern.triples
    target_triples = mapping.target_pattern.triples
    class_alignment = mapping.class_alignment()

    # Core source classes = those present in the class_map (will be bridged)
    source_classes: set[str] = set(class_alignment.keys())

    # All nodes that appear anywhere in the source pattern
    all_source_nodes: set[str] = set()
    for s, _p, o in source_triples:
        all_source_nodes.add(s)
        all_source_nodes.add(o)

    # All nodes that appear anywhere in the target pattern
    all_target_nodes: set[str] = set()
    for s, _p, o in target_triples:
        all_target_nodes.add(s)
        all_target_nodes.add(o)

    # Peripheral = source nodes that are NOT bridged (validation-only)
    peripheral: set[str] = all_source_nodes - source_classes

    # Path lengths for dotted bridge arrow sizing
    try:
        G_src = build_validation_graph(source_triples)
        src_len = longest_path_length(G_src)
    except ValueError:
        src_len = 1
    try:
        G_tgt = build_validation_graph(target_triples)
        tgt_len = longest_path_length(G_tgt)
    except ValueError:
        tgt_len = 1

    dot_count = src_len + tgt_len + 3
    dotted = "-" + "." * dot_count + "->"

    lines: list[str] = ["flowchart TD"]

    # ------------------------------------------------------------------
    # Node declarations
    # ------------------------------------------------------------------
    for node in sorted(source_classes):
        lines.append(f"    {node}[{_local_name(node)}]")
    for node in sorted(peripheral):
        lines.append(f"    {node}([{_local_name(node)}])")
    for node in sorted(all_target_nodes):
        lines.append(f"    {node}({_local_name(node)})")
    lines.append("")

    # ------------------------------------------------------------------
    # ShapeValidation subgraph
    # ------------------------------------------------------------------
    lines.append("    subgraph ShapeValidation")
    lines.append("        subgraph CoreShapeInformation")

    extended: list[str] = []
    for s, p, o in source_triples:
        if s in source_classes and o in source_classes:
            lines.append(f"        {s} ==>|{_local_name(p)}| {o}")
        else:
            extended.append(f"    {s} --->|{_local_name(p)}| {o}")

    lines.append("        end")
    lines.extend(extended)
    lines.append("    end")
    lines.append("")

    # ------------------------------------------------------------------
    # TransformedGraph subgraph
    # ------------------------------------------------------------------
    lines.append("    subgraph TransformedGraph")
    for s, p, o in target_triples:
        lines.append(f"    {s} -->|{_local_name(p)}| {o}")
    lines.append("    end")
    lines.append("")

    # ------------------------------------------------------------------
    # Bridge connections (dotted arrows from source to target class)
    # ------------------------------------------------------------------
    for src, tgt in sorted(class_alignment.items()):
        lines.append(f"    {src} {dotted}|SHACL_bridge| {tgt}")

    return "\n".join(lines)


def generate_mermaid_markdown(mapping: BridgeMapping) -> str:
    """Wrap the Mermaid diagram in a fenced code block for Markdown embedding."""
    diagram = generate_mermaid(mapping)
    return f"```mermaid\n{diagram}\n```"

"""
SHACL shape generation.

Produces a complete Turtle-serialized SHACL document containing:
1. A ``sh:NodeShape`` targeting the root class with nested ``sh:property``
   constraints that mirror the source design pattern.
2. A ``sh:SPARQLRule`` embedding the SPARQL CONSTRUCT query from
   :mod:`shacl_bridges.core.sparql`.

The nested property validation ensures that pyshacl only fires the SPARQL rule
against nodes that genuinely conform to the source pattern — preventing the rule
from matching isolated instances that happen to share a class name.
"""

from __future__ import annotations

import networkx as nx

from shacl_bridges.core.graph import build_validation_graph
from shacl_bridges.core.sparql import build_sparql_construct
from shacl_bridges.io.csv_reader import BridgeMapping


# ---------------------------------------------------------------------------
# Nested sh:property generation
# ---------------------------------------------------------------------------

def _nested_properties(
    G: nx.DiGraph,
    node: str,
    visited: set[str] | None = None,
    indent: int = 2,
) -> str:
    """Recursively generate nested ``sh:property`` blocks for *node*.

    Args:
        G: Directed validation graph (from :func:`build_validation_graph`).
        node: Current node being processed.
        visited: Set of already-visited nodes (prevents infinite loops on cycles).
        indent: Current indentation level (in units of 4 spaces).

    Returns:
        Turtle fragment string.
    """
    if visited is None:
        visited = set()
    if node in visited:
        return ""
    visited.add(node)

    pad = "    " * indent
    inner_pad = "    " * (indent + 1)
    fragments: list[str] = []

    for neighbor in G.successors(node):
        predicate = G[node][neighbor]["predicate"]
        nested = _nested_properties(G, neighbor, visited, indent + 2)

        block = f"{pad}sh:property [\n"
        block += f"{inner_pad}sh:path {predicate} ;\n"
        block += f"{inner_pad}sh:node [\n"
        block += f"{inner_pad}    a sh:NodeShape ;\n"
        block += f"{inner_pad}    sh:class {neighbor} ;\n"
        if nested:
            block += nested
        block += f"{inner_pad}] ;\n"
        block += f"{inner_pad}sh:message \"{node} must have {predicate} pointing to a {neighbor}.\" ;\n"
        block += f"{pad}] ;\n"
        fragments.append(block)

    return "".join(fragments)


# ---------------------------------------------------------------------------
# sh:prefixes block
# ---------------------------------------------------------------------------

def _prefix_block(prefix_map: dict[str, str], indent: int = 2) -> str:
    """Render a ``sh:prefixes [ sh:declare [...] ; ... ]`` block.

    Args:
        prefix_map: ``{prefix: namespace}`` dict.
        indent: Indentation in units of 4 spaces.

    Returns:
        Turtle fragment.
    """
    pad = "    " * indent
    inner = "    " * (indent + 1)
    lines = [f"{pad}sh:prefixes [\n"]
    for pfx, ns in prefix_map.items():
        lines.append(f"{inner}sh:declare [\n")
        lines.append(f"{inner}    sh:prefix \"{pfx}\" ;\n")
        lines.append(f"{inner}    sh:namespace \"{ns}\" ;\n")
        lines.append(f"{inner}] ;\n")
    lines.append(f"{pad}] ;\n")
    return "".join(lines)


# ---------------------------------------------------------------------------
# Full SHACL document
# ---------------------------------------------------------------------------

def generate_shacl(
    mapping: BridgeMapping,
    root_class: str,
    shape_name: str = "shapes:BridgeShape",
) -> str:
    """Generate a complete SHACL Turtle document for the given mapping.

    Args:
        mapping: Loaded :class:`~shacl_bridges.io.csv_reader.BridgeMapping`.
        root_class: CURIE of the class that the shape targets (``sh:targetClass``).
        shape_name: Local name for the generated ``sh:NodeShape``.

    Returns:
        Full Turtle string ready to be written to a ``.ttl`` file.
    """
    prefix_map = mapping.prefix_map()

    # ------------------------------------------------------------------
    # Turtle @prefix declarations
    # ------------------------------------------------------------------
    prefix_lines = [
        "@prefix sh:    <http://www.w3.org/ns/shacl#> .",
        "@prefix rdf:   <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .",
        "@prefix rdfs:  <http://www.w3.org/2000/01/rdf-schema#> .",
        "@prefix xsd:   <http://www.w3.org/2001/XMLSchema#> .",
        "@prefix shapes: <urn:shacl-bridges:shapes#> .",
    ]
    for pfx, ns in prefix_map.items():
        prefix_lines.append(f"@prefix {pfx}: <{ns}> .")
    prefix_block = "\n".join(prefix_lines)

    # ------------------------------------------------------------------
    # Nested sh:property validation
    # ------------------------------------------------------------------
    G = build_validation_graph(mapping.shape_validation)
    nested = _nested_properties(G, root_class)

    # ------------------------------------------------------------------
    # SPARQL CONSTRUCT query
    # ------------------------------------------------------------------
    construct_query = build_sparql_construct(
        mapping.shape_bridge,
        mapping.shape_validation,
        root_class,
        prefix_map,
    )
    # Indent the query body for embedding in Turtle triple-quote string
    indented_query = "\n".join(
        "        " + line if line.strip() else line
        for line in construct_query.splitlines()
    )

    sparql_rule = (
        "    sh:rule [\n"
        "        a sh:SPARQLRule ;\n"
        + _prefix_block(prefix_map, indent=2)
        + "        sh:message \"Bridge rule: transforms source design pattern to target.\" ;\n"
        f"        sh:construct \"\"\"\n{indented_query}\n        \"\"\" ;\n"
        "    ] ;\n"
    )

    # ------------------------------------------------------------------
    # Assemble
    # ------------------------------------------------------------------
    shape = (
        f"{shape_name}\n"
        "    a sh:NodeShape ;\n"
        f"    sh:targetClass {root_class} ;\n"
        + nested
        + sparql_rule
        + ".\n"
    )

    return f"{prefix_block}\n\n{shape}"

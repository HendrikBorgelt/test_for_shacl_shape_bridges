"""
Graph analysis utilities used to select the root (target) class for SHACL generation.

The root class becomes ``sh:targetClass`` in the generated NodeShape and anchors
the ``?this`` variable in the SPARQL CONSTRUCT WHERE clause. Choosing the wrong
root produces a disconnected WHERE pattern that over-matches — the most common
source of incorrect bridge output.

Two mechanisms are provided:
1. Explicit override via ``is_root: true`` in ``shape_bridge.csv``.
2. Automatic selection using closeness centrality on the shape-validation graph,
   with out-degree as a tiebreaker. This mirrors the original logic but now
   actually wires the result into SHACL generation.
"""

from __future__ import annotations

import networkx as nx
import pandas as pd


# ---------------------------------------------------------------------------
# Graph construction
# ---------------------------------------------------------------------------

def build_validation_graph(shape_validation: pd.DataFrame) -> nx.DiGraph:
    """Build a directed graph from the shape-validation S-P-O table.

    Each row ``(subject_id, predicate_id, object_id)`` becomes a directed edge
    ``subject → object`` labelled with the predicate.

    Args:
        shape_validation: DataFrame with columns ``subject_id``, ``predicate_id``,
                          ``object_id``.

    Returns:
        Directed graph with ``predicate`` edge attribute.
    """
    G = nx.DiGraph()
    for _, row in shape_validation.iterrows():
        G.add_edge(
            row["subject_id"],
            row["object_id"],
            predicate=row["predicate_id"],
        )
    return G


def build_bridge_graph(shape_bridge: pd.DataFrame) -> nx.DiGraph:
    """Build a directed graph from the shape-bridge From/Target columns.

    Used to compute the longest path (for Mermaid arrow sizing) and to detect
    isolated target nodes.

    Args:
        shape_bridge: DataFrame with columns ``from_id``, ``to_id``,
                      ``relation_id``, ``target_id``.

    Returns:
        Directed graph over *target* nodes (``to_id → target_id``).
    """
    G = nx.DiGraph()
    for _, row in shape_bridge.iterrows():
        to_node = row["to_id"]
        target = row.get("target_id", "")
        if pd.notna(target) and str(target) not in ("", "-"):
            G.add_edge(to_node, target)
    return G


# ---------------------------------------------------------------------------
# Root selection
# ---------------------------------------------------------------------------

def select_root_class(
    shape_validation: pd.DataFrame,
    explicit_root: str | None = None,
) -> str:
    """Return the CURIE of the class that should anchor the SHACL shape.

    Selection order:
    1. *explicit_root* if provided (comes from ``is_root: true`` in the CSV).
    2. The node with the highest closeness centrality in the undirected view of
       the validation graph; ties broken by out-degree in the directed view.

    Args:
        shape_validation: DataFrame with columns ``subject_id``, ``predicate_id``,
                          ``object_id``.
        explicit_root: CURIE string supplied by the user, or *None*.

    Returns:
        CURIE string of the selected root class.

    Raises:
        ValueError: If the validation graph is empty (no rows in *shape_validation*).
    """
    if explicit_root:
        return explicit_root

    G_directed = build_validation_graph(shape_validation)

    if G_directed.number_of_nodes() == 0:
        raise ValueError("shape_validation has no rows; cannot select a root class.")

    # Undirected copy with asymmetric weights so that traversing "against" an
    # edge is penalised — nodes reachable via outgoing edges are preferred.
    G_undirected = nx.Graph()
    for u, v in G_directed.edges():
        G_undirected.add_edge(u, v, weight=1)
        G_undirected.add_edge(v, u, weight=2)

    centrality = nx.closeness_centrality(G_undirected, distance="weight")
    max_val = max(centrality.values())
    candidates = [n for n, c in centrality.items() if c == max_val]

    if len(candidates) == 1:
        return candidates[0]

    # Tiebreak: highest out-degree in the directed graph
    return max(candidates, key=lambda n: G_directed.out_degree(n))


def check_connectivity(
    shape_validation: pd.DataFrame,
    root: str,
) -> list[str]:
    """Return a list of nodes in the validation graph that are NOT reachable from *root*.

    A non-empty result means the WHERE clause would contain disconnected
    sub-patterns, which would cause the SPARQL CONSTRUCT to over-match.

    Args:
        shape_validation: Validation pattern DataFrame.
        root: CURIE of the chosen root class.

    Returns:
        List of unreachable node CURIEs (empty if the pattern is fully connected).
    """
    G = build_validation_graph(shape_validation)
    # Use undirected reachability — we want to know if every node can be
    # reached by some path from the root, even via reverse edges.
    reachable = nx.node_connected_component(G.to_undirected(), root)
    all_nodes = set(G.nodes())
    return sorted(all_nodes - reachable)


# ---------------------------------------------------------------------------
# Path length helpers (used for Mermaid arrow sizing)
# ---------------------------------------------------------------------------

def longest_path_length(G: nx.DiGraph) -> int:
    """Return the number of *edges* on the longest path in a DAG.

    Args:
        G: A directed acyclic graph.

    Returns:
        Number of edges (0 for a single-node graph with no edges).

    Raises:
        ValueError: If *G* is not a DAG.
    """
    if not nx.is_directed_acyclic_graph(G):
        raise ValueError("Graph is not a DAG; longest path is undefined.")
    path = nx.dag_longest_path(G)
    return max(0, len(path) - 1)

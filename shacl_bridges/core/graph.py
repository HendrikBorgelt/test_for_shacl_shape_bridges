"""
Graph analysis utilities used to select the root (target) class for SHACL generation.

The root class becomes ``sh:targetClass`` in the generated NodeShape and anchors
the ``?this`` variable in the SPARQL CONSTRUCT WHERE clause. Choosing the wrong
root produces a disconnected WHERE pattern that over-matches — the most common
source of incorrect bridge output.

Two mechanisms are provided:
1. Explicit override via ``source_pattern.root`` in the bridge YAML.
2. Automatic selection using closeness centrality on the source-pattern graph,
   with out-degree as a tiebreaker.
"""

from __future__ import annotations

import networkx as nx

from shacl_bridges.io.yaml_reader import Triple


# ---------------------------------------------------------------------------
# Graph construction
# ---------------------------------------------------------------------------

def build_validation_graph(triples: list[Triple]) -> nx.DiGraph:
    """Build a directed graph from a list of S-P-O triples.

    Each triple ``(subject, predicate, object)`` becomes a directed edge
    ``subject → object`` labelled with the predicate.

    Args:
        triples: List of ``(subject_curie, predicate_curie, object_curie)`` tuples.

    Returns:
        Directed graph with ``predicate`` edge attribute.
    """
    G = nx.DiGraph()
    for s, p, o in triples:
        G.add_edge(s, o, predicate=p)
    return G


# ---------------------------------------------------------------------------
# Root selection
# ---------------------------------------------------------------------------

def select_root_class(
    triples: list[Triple],
    explicit_root: str | None = None,
) -> str:
    """Return the CURIE of the class that should anchor the SHACL shape.

    Selection order:
    1. *explicit_root* if provided (comes from ``source_pattern.root`` in the YAML).
    2. The node with the highest closeness centrality in the undirected view of
       the source-pattern graph; ties broken by out-degree in the directed view.

    Args:
        triples: Source-pattern triples (``source_pattern.triples``).
        explicit_root: CURIE string supplied by the user, or *None*.

    Returns:
        CURIE string of the selected root class.

    Raises:
        ValueError: If *triples* is empty.
    """
    if explicit_root:
        return explicit_root

    G_directed = build_validation_graph(triples)

    if G_directed.number_of_nodes() == 0:
        raise ValueError("source_pattern has no triples; cannot select a root class.")

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
    triples: list[Triple],
    root: str,
) -> list[str]:
    """Return a list of nodes NOT reachable from *root* in the source-pattern graph.

    A non-empty result means the WHERE clause would contain disconnected
    sub-patterns, causing the SPARQL CONSTRUCT to over-match.

    Args:
        triples: Source-pattern triples.
        root: CURIE of the chosen root class.

    Returns:
        Sorted list of unreachable node CURIEs (empty if fully connected).
    """
    G = build_validation_graph(triples)
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

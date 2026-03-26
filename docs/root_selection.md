# Root Class Selection

The *root class* is the class that the generated SHACL `sh:NodeShape` targets (`sh:targetClass`). It is also the class to which `?this` is bound in the SPARQL WHERE clause.

Choosing the wrong root produces a **disconnected WHERE pattern**: the query matches any instance of the root class, regardless of whether it is actually connected to the other pattern nodes. This causes the bridge to fire on data that only superficially resembles the source pattern.

---

## Selection order

1. **Explicit override** — set `is_root=true` on one row in `shape_bridge.csv`. The `from_id` of that row becomes the root. This is the recommended approach for production mappings.

2. **Automatic selection** — if no row is marked, the tool computes [closeness centrality](https://networkx.org/documentation/stable/reference/algorithms/generated/networkx.algorithms.centrality.closeness_centrality.html) on an undirected view of the shape-validation graph, where traversing *against* an edge has twice the cost of traversing *with* it. Ties are broken by out-degree in the directed graph. The node with the highest centrality becomes the root.

---

## Connectivity check

After root selection (regardless of method), the tool runs a connectivity check: it verifies that every node in the shape-validation graph is reachable from the root via any path (directed or undirected).

If unreachable nodes are found, the tool raises:

```
ValueError: The validation pattern contains nodes not reachable from 'ex:Process':
['ex:SomeIsolatedClass']. Mark a different root class with is_root=true in
shape_bridge.csv, or add the missing relationships to shape_validation.csv.
```

This check catches the most common user error — declaring a class in `shape_validation.csv` that is not actually connected to the rest of the pattern.

---

## Why the automatic heuristic works (and when it doesn't)

Closeness centrality favours nodes that are "closest" to all other nodes. In a chain-shaped pattern (`A → B → C → D`), this selects the middle nodes (`B` or `C`). For a hub-and-spoke pattern, it selects the hub.

The heuristic breaks when:
- The pattern is disconnected to begin with (caught by the connectivity check)
- Multiple roots are equally central and out-degree tiebreaking picks the wrong one

In these cases, set `is_root=true` explicitly.

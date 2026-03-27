# Root Class Selection

The *root class* is the class that the generated SHACL `sh:NodeShape` targets
(`sh:targetClass`). It is also the class to which `?this` is bound in the SPARQL
WHERE clause.

Choosing the wrong root produces a **disconnected WHERE pattern**: the query
matches any instance of the root class, regardless of whether it is actually
connected to the other pattern nodes. This causes the bridge to fire on data
that only superficially resembles the source pattern.

---

## Selection order

1. **Explicit override** — set `root` in the `source_pattern` section of
   `bridge.yaml`. This is the recommended approach for production mappings.

   ```yaml
   source_pattern:
     root: "ex:Process"
     triples: ...
   ```

2. **Automatic selection** — if `root` is omitted, the tool computes
   [closeness centrality](https://networkx.org/documentation/stable/reference/algorithms/generated/networkx.algorithms.centrality.closeness_centrality.html)
   on an undirected view of the source-pattern graph, where traversing *against*
   an edge has twice the cost of traversing *with* it. Ties are broken by
   out-degree in the directed graph. The node with the highest centrality becomes
   the root.

---

## Connectivity check

After root selection (regardless of method), the tool runs a connectivity check:
it verifies that every node in the source-pattern graph is reachable from the
root via any path (directed or undirected).

If unreachable nodes are found, the tool raises a `ValueError`:

```
ValueError: The validation pattern contains nodes not reachable from 'ex:Process':
['ex:SomeIsolatedClass']. Set source_pattern.root to a different class or add the
missing relationship to source_pattern.triples.
```

Run `shacl-bridges validate` first to catch this before running the bridge:

```
⚠  'ex:SomeIsolatedClass' is not reachable from root 'ex:Process' in source_pattern
   hint: This node will be omitted from the SPARQL WHERE clause, causing silent over-matching.
```

---

## Why the automatic heuristic works (and when it doesn't)

Closeness centrality favours nodes that are "closest" to all other nodes. In a
chain-shaped pattern (`A → B → C → D`), this selects the middle nodes (`B` or
`C`). For a hub-and-spoke pattern, it selects the hub.

The heuristic breaks when:
- The pattern is disconnected to begin with (caught by the connectivity check)
- Multiple roots are equally central and out-degree tiebreaking picks the wrong one

In these cases, set `source_pattern.root` explicitly.

# Validator

SHACL Bridges includes a built-in validator that checks a bridge YAML file for
structural and semantic correctness before you run it. This is analogous to the
LinkML schema validator — it catches authoring mistakes early, before they
produce silent wrong output.

---

## CLI usage

```bash
shacl-bridges validate my_bridge.yaml
```

Example output for a valid file:

```
✓  my_bridge.yaml: valid
```

Example output for a file with issues:

```
✗  Prefix 'foo' (used in 'foo:Undeclared') is not declared in prefixes
   hint: Add 'foo: <namespace_IRI>' to the prefixes block

⚠  'ex:Setup' is not reachable from root 'ex:Process' in source_pattern
   hint: This node will be omitted from the SPARQL WHERE clause, causing
         silent over-matching. Set a different source_pattern.root or connect
         this node to the rest of the pattern.

1 error(s), 1 warning(s)
```

The exit code is `1` if there are any errors, `0` if valid (warnings don't
affect the exit code).

---

## Python usage

```python
from shacl_bridges.io.yaml_reader import load_mapping
from shacl_bridges.validate import validate_mapping, Severity

mapping = load_mapping("bridge.yaml")
issues = validate_mapping(mapping)

errors = [i for i in issues if i.severity == Severity.ERROR]
if errors:
    raise ValueError(f"Bridge mapping has {len(errors)} error(s)")
```

---

## Checks performed

| # | Severity | Check |
|---|----------|-------|
| 1 | Error | Every CURIE used references a declared prefix (or a well-known built-in) |
| 2 | Error | `source_pattern.root` (if set) appears in at least one source triple |
| 3 | Warning | Every node in `source_pattern` is reachable from the chosen root |
| 4 | Error | Every `class_map[].source` appears in `source_pattern.triples` |
| 5 | Error | Every `class_map[].target` appears in `target_pattern.triples` |
| 6 | Warning | `target_pattern.triples` form a connected graph |

### Why check 3 matters

A disconnected source pattern means the SPARQL WHERE clause will contain
sub-patterns not anchored to `?this`. The query will match any instance of the
root class — regardless of whether the rest of the pattern is present. This is
the most common source of silent over-matching.

The validator reports exactly which nodes are unreachable, making it easy to
decide whether to set `source_pattern.root` to a different class or to add a
missing triple.

### Why check 6 is a warning not an error

Disconnected target patterns are unusual but not always wrong. For example, you
might intentionally produce two independent subgraphs as bridge output. The
warning prompts you to verify this is intentional.

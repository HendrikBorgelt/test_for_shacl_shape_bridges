github pages: https://hendrikborgelt.github.io/test_for_shacl_shape_bridges/

# SHACL Bridges

**N-to-m semantic mapping via SHACL shapes with SPARQL CONSTRUCT rules.**

SHACL Bridges transforms instance data conforming to one ontological design
pattern into instance data conforming to a different pattern. Unlike 1-to-1
crosswalk tools, it handles structural n-to-m mappings: one source class can map
to multiple target classes, relationships can be rerouted, and new connections
are created between transformed instances.

---

## How it works

1. **Define the mapping** in a single annotated YAML file (`bridge.yaml`):
   - `source_pattern` — the source design pattern as S-P-O triples
   - `target_pattern` — the target design pattern as S-P-O triples
   - `class_map` — which source class maps to which target class (with justification)

2. **Validate** the mapping with the built-in validator:
   ```bash
   shacl-bridges validate bridge.yaml
   ```

3. **Generate a SHACL shape** with an embedded SPARQL CONSTRUCT rule. The shape
   validates that only conforming source instances are transformed.

4. **Run the bridge** via pyshacl. Two passes are made: one for the RDFS-inferred
   baseline, one with the bridge shape applied.

5. **Inspect the diff**: the difference between the two passes gives exactly the
   triples introduced by the bridge.

```
bridge.yaml ──► generate_shacl() ──► bridge.ttl ──► pyshacl ──► diff.ttl
                                                        ▲
                                                   data.ttl (harmonized)
```

---

## Installation

```bash
# From source (recommended during development)
uv pip install -e ".[dev,docs,notebook]"

# Once published to PyPI
pip install shacl-bridges
```

**Requirements**: Python ≥ 3.10, `pyyaml`, `networkx`, `pyshacl`, `rdflib`, `owlrl`.

---

## Quick start

```python
from shacl_bridges import (
    load_mapping, select_root_class, check_connectivity,
    generate_shacl, run_bridge_from_files, save_result,
)

mapping = load_mapping("bridge.yaml")
root = select_root_class(mapping.source_pattern.triples, mapping.root_class())

issues = check_connectivity(mapping.source_pattern.triples, root)
if issues:
    raise ValueError(f"Disconnected nodes from root {root!r}: {issues}")

shacl_ttl = generate_shacl(mapping, root)
open("bridge.ttl", "w").write(shacl_ttl)

result = run_bridge_from_files("data.ttl", "bridge.ttl")
save_result(result, "expanded.ttl", "diff.ttl")
print(f"Bridge added {len(result.diff_graph)} new triples.")
```

Or use the CLI end-to-end:

```bash
shacl-bridges validate  bridge.yaml
shacl-bridges diagram   bridge.yaml
shacl-bridges generate  bridge.yaml -o shape.ttl
shacl-bridges run       bridge.yaml data.ttl
```

Run the worked example:

```bash
just example
```

---

## Repository layout

```
shacl_bridges/            # Python package
├── core/
│   ├── graph.py          # Root selection, connectivity check
│   ├── sparql.py         # SPARQL CONSTRUCT generation
│   ├── shacl.py          # SHACL shape assembly
│   └── diff.py           # pyshacl validation + graph diff
├── io/
│   ├── yaml_reader.py    # Load bridge.yaml mapping files
│   └── rdf_utils.py      # RDF syntax harmonization
├── visualize/
│   └── mermaid.py        # Mermaid diagram generation
├── validate.py           # Bridge mapping validator
└── cli.py                # CLI: validate / diagram / generate / run

examples/
└── process_to_experiment/
    ├── mapping/
    │   └── bridge.yaml   # Bridge mapping (single YAML file)
    ├── data.ttl           # Source instance data (in tests/test_data/)
    └── run_example.py    # End-to-end script

tests/
docs/                     # mkdocs source
pyproject.toml
justfile
```

---

## Development

```bash
just install    # install in editable mode with dev + docs + notebook deps
just test       # run tests
just docs       # serve docs at localhost:8000
just example    # run the worked example
```

---

## Key design decisions

**Why a single YAML file?** The previous four-CSV approach had redundancy
(class CURIEs repeated across files), a placeholder `-` convention for terminal
nodes, and conflated the class alignment with the target pattern. A single YAML
file separates `source_pattern`, `target_pattern`, and `class_map` cleanly,
removes all placeholders, and makes the mapping easier to author and validate.

**Why SHACL SPARQLRule?** The `sh:SPARQLRule` fires per-instance and has access
to `?this`, which anchors the WHERE clause to a specific node. This guarantees
only connected, conforming subgraphs are transformed.

**Why a graph diff?** Running pyshacl twice (baseline with RDFS inference, then
with the bridge shape) and diffing the results isolates exactly the bridge output.
The source data is never modified.

**Root class selection**: the `sh:targetClass` determines which class anchors
`?this` in the WHERE clause. A wrong choice produces a disconnected WHERE pattern
that over-matches. The tool selects the root via closeness centrality and validates
connectivity before generating any SHACL. See [docs/root_selection.md](docs/root_selection.md).

---

## Acknowledgements

The mapping justification vocabulary is inspired by
[SSSOM](https://mapping-commons.github.io/sssom/) (Simple Standard for Sharing
Ontological Mappings).

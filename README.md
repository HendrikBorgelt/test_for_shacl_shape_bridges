# SHACL Bridges

**N-to-m semantic mapping via SHACL shapes with SPARQL CONSTRUCT rules.**

SHACL Bridges transforms instance data conforming to one ontological design pattern into instance data conforming to a different pattern. Unlike 1-to-1 crosswalk tools, it handles structural n-to-m mappings: one source class can map to multiple target classes, relationships can be rerouted, and new connections are created between transformed instances.

---

## How it works

1. **Define the mapping** in four annotated CSV files:
   - `prefixes.csv` — namespace declarations
   - `shape_validation.csv` — the source design pattern as S-P-O triples
   - `shape_bridge.csv` — transformation rules from source to target pattern
   - `classes.csv` — optional labels for visualization

2. **Generate a SHACL shape** with an embedded SPARQL CONSTRUCT rule. The shape validates that only conforming source instances are transformed.

3. **Run the bridge** via pyshacl. Two passes are made: one for the RDFS-inferred baseline, one with the bridge shape applied.

4. **Inspect the diff**: the difference between the two passes gives exactly the triples introduced by the bridge.

```
shape_validation.csv ─┐
shape_bridge.csv      ├─► generate_shacl() ─► bridge.ttl ─► pyshacl ─► diff.ttl
prefixes.csv          ┘                                        ▲
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

**Requirements**: Python ≥ 3.10, `pandas`, `networkx`, `pyshacl`, `rdflib`, `owlrl`.

---

## Quick start

```python
from shacl_bridges import (
    load_mapping, select_root_class, check_connectivity,
    generate_shacl, run_bridge_from_files, save_result,
)

mapping = load_mapping("examples/process_to_experiment/mapping/")
root = select_root_class(mapping.shape_validation, mapping.root_class())

issues = check_connectivity(mapping.shape_validation, root)
if issues:
    raise ValueError(f"Disconnected nodes from root {root!r}: {issues}")

shacl_ttl = generate_shacl(mapping, root)
open("bridge.ttl", "w").write(shacl_ttl)

result = run_bridge_from_files("data.ttl", "bridge.ttl")
save_result(result, "expanded.ttl", "diff.ttl")
print(f"Bridge added {len(result.diff_graph)} new triples.")
```

Or run the worked example end-to-end:

```bash
just example
```

---

## Repository layout

```
shacl_bridges/           # Python package
├── core/
│   ├── graph.py         # Root selection, connectivity check
│   ├── sparql.py        # SPARQL CONSTRUCT generation
│   ├── shacl.py         # SHACL shape assembly
│   └── diff.py          # pyshacl validation + graph diff
├── io/
│   ├── csv_reader.py    # Load SSSOM-inspired CSV mapping files
│   └── rdf_utils.py     # RDF syntax harmonization
└── visualize/
    └── mermaid.py       # Mermaid diagram generation

examples/
└── process_to_experiment/
    ├── mapping/         # Four CSV files defining the mapping
    ├── data.ttl         # Source instance data
    └── run_example.py   # End-to-end script

tests/
docs/                    # mkdocs source
pyproject.toml
justfile
```

---

## Development

```bash
just install    # install in editable mode
just test       # run tests
just docs       # serve docs at localhost:8000
just example    # run the worked example
```

---

## Key design decisions

**Why SHACL SPARQLRule?** The `sh:SPARQLRule` fires per-instance and has access to `?this`, which anchors the WHERE clause to a specific node. This guarantees only connected, conforming subgraphs are transformed.

**Why a graph diff?** Running pyshacl twice (baseline with RDFS inference, then with the bridge shape) and diffing the results isolates exactly the bridge output. The source data is never modified.

**Root class selection**: the `sh:targetClass` determines which class anchors `?this` in the WHERE clause. A wrong choice produces a disconnected WHERE pattern that over-matches. The tool selects the root via closeness centrality and validates connectivity before generating any SHACL. See [docs/root_selection.md](docs/root_selection.md).

---

## Acknowledgements

The CSV mapping format is inspired by [SSSOM](https://mapping-commons.github.io/sssom/) (Simple Standard for Sharing Ontological Mappings), particularly the `mapping_justification` vocabulary.

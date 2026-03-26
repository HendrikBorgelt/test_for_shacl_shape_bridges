# SHACL Bridges

**N-to-m semantic mapping via SHACL shapes with SPARQL CONSTRUCT rules.**

## What is this?

SHACL Bridges transforms instance data that conforms to one ontological *design pattern* into instance data that conforms to a different design pattern — without touching the source data and without requiring a full ontology alignment.

It is not a 1-to-1 class crosswalk. It handles **n-to-m structural mappings**: one source class can fan out to multiple target classes, relationships can be rerouted, and new connections can be introduced between transformed instances.

## Why not SSSOM or an alignment tool?

Standard mapping tools (SSSOM, OWL equivalence axioms, YARRRML) operate on concepts in isolation. They answer "class A is equivalent to class B." They cannot express "a chain of three classes connected by two specific properties in ontology A corresponds to a different chain of three classes in ontology B."

SHACL Bridges expresses exactly that:

1. A **shape validation** pattern defines what the source data must look like.
2. A **shape bridge** defines how each class and relationship transforms.
3. A SHACL `sh:SPARQLRule` is generated and applied via pyshacl.
4. The diff between the inferred base graph and the expanded graph gives only the newly bridged triples.

## Quick start

```bash
pip install shacl-bridges  # once published
# or: uv pip install -e ".[dev]" from the repo root
```

```python
from shacl_bridges import load_mapping, select_root_class, check_connectivity
from shacl_bridges import generate_shacl, run_bridge_from_files, save_result

mapping = load_mapping("examples/process_to_experiment/mapping/")
root = select_root_class(mapping.shape_validation, mapping.root_class())
check_connectivity(mapping.shape_validation, root)  # raises on disconnected pattern

shacl_ttl = generate_shacl(mapping, root)
open("bridge.ttl", "w").write(shacl_ttl)

result = run_bridge_from_files("data.ttl", "bridge.ttl")
save_result(result, "expanded.ttl", "diff.ttl")
```

See the [Process → Experiment example](examples/process_experiment.md) for a full walkthrough.

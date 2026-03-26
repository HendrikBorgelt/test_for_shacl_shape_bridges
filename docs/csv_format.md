# CSV Format Reference

A mapping is defined by a directory containing up to four CSV files. Lines beginning with `#` are treated as comments and ignored by the reader.

---

## `prefixes.csv` (required)

Declares all namespace prefixes used in the other CSVs.

| Column | Required | Description |
|--------|----------|-------------|
| `prefix` | yes | Short prefix string (e.g. `ex`) |
| `namespace` | yes | Full namespace URI (e.g. `http://example.org/ontology#`) |
| `comment` | no | Human-readable note |

```csv
prefix,namespace,comment
ex,http://example.org/ontology#,Example ontology
rdf,http://www.w3.org/1999/02/22-rdf-syntax-ns#,RDF core
```

---

## `shape_validation.csv` (required)

Defines the **source design pattern** as a set of S-P-O triples. These become:
- Nested `sh:property` constraints in the SHACL shape
- Pattern triples in the SPARQL WHERE clause

| Column | Required | Description |
|--------|----------|-------------|
| `subject_id` | yes | CURIE of the subject class |
| `predicate_id` | yes | CURIE of the connecting property |
| `object_id` | yes | CURIE of the object class |
| `comment` | no | Justification for including this triple |

The `-` placeholder in any column is forward-filled from the previous row.

---

## `shape_bridge.csv` (required)

Defines the **transformation rules** from source to target design pattern.

| Column | Required | Description |
|--------|----------|-------------|
| `from_id` | yes | Source class CURIE |
| `to_id` | yes | Target class CURIE |
| `relation_id` | yes | New relation in the target pattern, or `-` |
| `target_id` | yes | Target of the new relation, or `-` |
| `is_root` | no | `true` marks this row's `from_id` as the SHACL anchor class |
| `mapping_justification` | no | SSSOM-style justification CURIE (e.g. `semapv:ManualMappingCuration`) |
| `comment` | no | Human-readable explanation |

The `-` placeholder in `from_id`/`to_id` is forward-filled. A row where both `relation_id` and `target_id` are `-` declares a terminal node with no outgoing relation in the target pattern.

**`is_root`**: At most one row should have `is_root=true`. If none is marked, the tool selects the root class automatically via closeness centrality. See [Root Selection](root_selection.md).

**Mapping justification vocabulary** (SSSOM `semapv`):

| Value | Meaning |
|-------|---------|
| `semapv:ManualMappingCuration` | A human expert reviewed and approved this mapping |
| `semapv:StructuralMatching` | Mapping follows structural equivalence of graph patterns |
| `semapv:LexicalMatching` | Based on lexical similarity of labels |

---

## `classes.csv` (optional)

Provides human-readable labels and descriptions for CURIEs. Used only for visualization (Mermaid diagrams). Not required for SHACL generation.

| Column | Required | Description |
|--------|----------|-------------|
| `id` | yes | CURIE |
| `label` | yes | Human-readable label |
| `description` | no | Longer description |

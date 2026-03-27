# YAML Format Reference

A mapping is defined in a single YAML file (conventionally named `bridge.yaml`).
Lines beginning with `#` are treated as YAML comments and ignored.

---

## Top-level structure

```yaml
metadata:       # optional
prefixes:       # required
source_pattern: # required
target_pattern: # required
class_map:      # required
```

---

## `metadata` (optional)

Human-readable information about the bridge. None of these fields affect code generation.

| Key | Default | Description |
|-----|---------|-------------|
| `title` | `""` | Short human-readable name |
| `version` | `"0.1.0"` | Semver string |
| `creator` | `""` | Author or organization |
| `license` | `""` | License identifier (e.g. `CC0`) |
| `mapping_justification` | `semapv:ManualMappingCuration` | Default SSSOM justification applied to all class_map entries that don't declare their own |

---

## `prefixes` (required)

A flat mapping of prefix → namespace IRI. All CURIEs used anywhere in the file
must reference a declared prefix (or a well-known built-in such as `rdf`, `rdfs`,
`xsd`, `owl`, `sh`, `skos`, `semapv`).

```yaml
prefixes:
  ex:   "http://example.org/ontology#"
  prov: "http://www.w3.org/ns/prov#"
```

---

## `source_pattern` (required)

Defines the source design pattern as a list of S-P-O triples.

| Key | Required | Description |
|-----|----------|-------------|
| `triples` | yes | List of `[subject, predicate, object]` CURIE arrays |
| `root` | no | CURIE of the class to use as `sh:targetClass` and `?this`. Omit to auto-compute via closeness centrality. |

```yaml
source_pattern:
  root: "ex:Process"
  triples:
    # Core structural triples (both nodes are bridged classes)
    - ["ex:Process",     "ex:hasPart",     "ex:ProcessStep"]
    - ["ex:Input",       "ex:isInput",     "ex:ProcessStep"]
    # Peripheral validation triples (upper-level TBox constraints)
    - ["ex:Process",     "ex:isSome",      "ex:ChemicalInvestigation"]
```

### Core vs peripheral triples

**Core triples** have both subject and object present in `class_map` as source
classes. They drive both the nested `sh:property` constraints and the SPARQL
WHERE clause.

**Peripheral triples** have at least one endpoint that is not a bridged class
(e.g., an upper-level superclass). They appear only in the `sh:property`
validation block — they are TBox-level constraints, not ABox patterns.

---

## `target_pattern` (required)

Defines the target design pattern as a list of S-P-O triples. These triples
appear in the SPARQL CONSTRUCT clause.

```yaml
target_pattern:
  triples:
    - ["ex:Experiment",      "ex:hasSetup",  "ex:ExperimentSetup"]
    - ["ex:Experiment",      "ex:hasSample", "ex:Sample"]
    - ["ex:ExperimentSetup", "ex:performedWith", "ex:Parameters"]
```

---

## `class_map` (required)

A list of source-class → target-class alignments. Each entry declares:

| Key | Required | Description |
|-----|----------|-------------|
| `source` | yes | CURIE of the source class (must appear in `source_pattern.triples`) |
| `target` | yes | CURIE of the target class (must appear in `target_pattern.triples`) |
| `justification` | no | SSSOM-style justification CURIE (overrides `metadata.mapping_justification`) |
| `comment` | no | Human-readable explanation of why this mapping is valid |

```yaml
class_map:
  - source: "ex:Process"
    target: "ex:Experiment"
    justification: "semapv:ManualMappingCuration"
    comment: "Process as investigative activity maps to Experiment"

  - source: "ex:InputSettings"
    target: "ex:Parameters"
    comment: "Terminal node — no outgoing relation in the source pattern"
```

Terminal nodes (source classes with no outgoing structural relations) are handled
naturally: simply declare them in `class_map` and omit them from the core
`source_pattern.triples`. No `-` placeholder rows needed.

### Mapping justification vocabulary

| Value | Meaning |
|-------|---------|
| `semapv:ManualMappingCuration` | A human expert reviewed and approved this mapping |
| `semapv:StructuralMatching` | Mapping follows structural equivalence of graph patterns |
| `semapv:LexicalMatching` | Based on lexical similarity of labels |

---

## Validation

Run `shacl-bridges validate my_bridge.yaml` to check a file before using it.
See [Validator](validate.md) for the full list of checks.

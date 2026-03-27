# Concepts

## Design patterns in ontologies

An ontological *design pattern* is a recurring, reusable template for modelling
a domain concept. For example, a "process with steps" pattern might look like:

```
Process --hasPart--> ProcessStep --isInput--> Input --hasModifier--> InputSettings
```

Different communities model the same real-world structure with different patterns.
A laboratory workflow ontology might use the above, while a scientific experiment
ontology uses:

```
Experiment --hasExperimentSetup--> ExperimentSetup --performedWith--> Parameters
Experiment --hasSample--> Sample --hasConcentrations--> Parameters
```

Both encode the same structure — a structured investigation with configuration
and material inputs — but the class names, relationship names, and graph topology
differ.

## The bridging approach

SHACL Bridges generates a SHACL shape that:

1. **Validates** that source instances actually conform to the source design pattern
   (nested `sh:property` constraints). Only conforming subgraphs are transformed.
2. **Transforms** via a `sh:SPARQLRule` containing a SPARQL `CONSTRUCT` query.
   The CONSTRUCT adds new `rdf:type` assertions and new relations, mapping source
   instances to target classes.
3. **Produces a diff** between the pre-rule graph (with RDFS inference only) and
   the post-rule graph, giving exactly the triples introduced by the bridge.

## The YAML mapping file

A bridge is defined in a single `bridge.yaml` file with three core sections:

```
source_pattern  →  what the source data must look like (S-P-O triples)
target_pattern  →  what to construct (S-P-O triples in the target vocabulary)
class_map       →  which source class maps to which target class (with justification)
```

The source and target patterns are expressed symmetrically — both are just lists
of triples. The class map is the explicit bridge between them.

See [YAML Format](yaml_format.md) for the full schema.

## The root class and `?this`

The SHACL `sh:SPARQLRule` fires for every instance of `sh:targetClass`. Inside
the rule, `?this` is automatically bound to each such instance.

The WHERE clause is **anchored to `?this`** and traverses outward through the
source pattern:

```sparql
WHERE {
  ?this rdf:type ex:Process .
  ?this ex:hasPart ?var_b .
  ?var_b rdf:type ex:ProcessStep .
  ?var_c ex:isInput ?var_b .
  ...
}
```

This guarantees that **only connected subgraphs** are matched. If the root class
is poorly chosen (e.g. a leaf node), the WHERE clause becomes disconnected and
matches any isolated instance of that class — a silent over-match.

The tool detects this and raises an error before generating the SHACL shape.
See [Root Selection](root_selection.md) for details.

## Core vs peripheral source triples

Not all source triples should appear in the SPARQL WHERE clause:

- **Core triples** have both subject and object as bridged classes (present in
  `class_map` as source classes). They appear in both the `sh:property` constraints
  and the SPARQL WHERE clause.
- **Peripheral triples** have at least one endpoint that is *not* a bridged class —
  typically upper-level classification constraints like
  `ex:Process isSome ex:ChemicalInvestigation`. These classes exist only at the TBox
  level. They appear only in the `sh:property` validation block, not in the WHERE clause.

The tool distinguishes these automatically based on which classes are in `class_map`.

## Inference and syntax harmonization

Before running the bridge, it is advisable to harmonize the RDF syntax of your
source data using `harmonize_to_turtle()`. This re-parses and re-serializes the
graph, normalizing:

- Serialization format (RDF/XML, OWL/XML, N-Triples → Turtle)
- Namespace prefix declarations
- Blank node identifiers

No semantic inference is applied at this stage. RDFS inference is applied by
pyshacl during the validation passes.

## Graph diff

Two pyshacl `Validator` runs are performed:

1. **Base pass**: data graph only, RDFS inference enabled → captures all triples
   RDFS alone would add.
2. **Bridge pass**: data graph + SHACL shape, RDFS inference enabled → captures
   base triples + bridged triples.

The rdflib `graph_diff` on the two isomorphic representations yields only the
triples unique to pass 2 — the bridge output.

# DCAT-AP+ to NFDICore Mapping — Discovered Issues

## Tool Issues (SHACL Bridges)

### ISSUE-T1: `derived_iri` always binds to `?this` (root class)
- **Phase**: 1b (Agent Splitting)
- **Severity**: Medium — workaround exists (re-root the bridge)
- **Description**: `BIND(IRI(CONCAT(STR(?this), suffix)))` always mints from the root class IRI. If you need to mint from a non-root class (e.g., mint a role IRI from the agent, not the activity), you must restructure the bridge to make that class the root.
- **Workaround**: Re-root the bridge on the class whose IRI you want to mint from. Bridge 1b was re-rooted from `prov:Activity` to `prov:Agent`.
- **Fix**: Allow `derived_iri` to specify which source class variable to bind from, e.g., `derived_iri: "suffix:_role" from: "prov:Agent"`.
- **Status**: User acknowledged — will implement fix.

#### Proposed fix in detail

Currently in `sparql.py`, `derived_iri` entries always produce:

```sparql
BIND(IRI(CONCAT(STR(?this), "_role")) AS ?derived_NFDI_0000229)
```

The fix would add an optional `from` field to `derived_iri` entries in the bridge YAML:

```yaml
class_map:
  - source: "prov:Agent"
    target: "nfdi:NFDI_0000229"
    derived_iri: "suffix:_role"
    from: "prov:Agent"     # <-- new field: mint from this source class, not root
```

In `sparql.py`, the BIND generation (around line 148–153) would change from always using `?this` to looking up the variable for the `from` class:

```python
# Current:
where_lines.append(
    f'  BIND(IRI(CONCAT(STR(?this), "{suffix}")) AS {var_name})'
)

# Proposed:
source_var = var_map.get(entry.from_class, "?this") if entry.from_class else "?this"
where_lines.append(
    f'  BIND(IRI(CONCAT(STR({source_var}), "{suffix}")) AS {var_name})'
)
```

The `ClassMapEntry` dataclass in `yaml_reader.py` would need the new optional `from_class` field. The validator should check that the `from` class exists in the source class_map.

### ISSUE-T2: No scope filtering (bridge fires on all type-matching instances)
- **Phase**: 1b (Agent Splitting)
- **Severity**: High — produces incorrect mappings
- **Description**: Bridge 1b fires on ALL `prov:Activity` instances that have `prov:wasAssociatedWith`, not just DataGeneratingActivity ones. The WHERE clause has no way to restrict scope beyond the types in `class_map`.
- **Status**: Discussed with user. User asked for feasible datamodel fix discussion.

#### Why the current bridge matches too broadly

Bridge 1b's generated SPARQL WHERE clause is:

```sparql
?this rdf:type prov:Agent .
?var_b rdf:type prov:Activity .
?var_b prov:wasAssociatedWith ?this .
```

This fires for **every** `prov:Activity` that has agents — including `DataAnalysis` activities, not just `DataGeneratingActivity` instances. In the sample data, the NMRSpectralAnalysis (a DataAnalysis) also has `prov:wasAssociatedWith` links, so those agents get role triples pointing to `nfdi:NFDI_0010029` (data producing process) even though the analysis is conceptually a *data transformation* process, not a data producing one.

#### Why graph-shape discrimination doesn't help here

For Bridge 1a, we successfully discriminated `DataGeneratingActivity` from `DataAnalysis` using topology — `dcat:Dataset --prov:wasGeneratedBy--> prov:Activity` only matches the generation activities. But in Bridge 1b, the root is `prov:Agent`, and the structural pattern `prov:Activity --prov:wasAssociatedWith--> prov:Agent` is shared by **all** activity types. There's no topological difference from the agent's perspective.

#### Proposed fix: Option A — filter triples (recommended)

Allow source_pattern triples to be explicitly marked as `filter: true`, forcing them into the SPARQL WHERE even if they're structurally peripheral (i.e., not both endpoints in class_map):

```yaml
source_pattern:
  root: "prov:Agent"
  triples:
    - ["prov:Activity", "prov:wasAssociatedWith", "prov:Agent"]
    - triple: ["dcat:Dataset", "prov:wasGeneratedBy", "prov:Activity"]
      filter: true  # Force into WHERE clause for discrimination
```

This would generate:

```sparql
WHERE {
  ?this rdf:type prov:Agent .
  ?var_b rdf:type prov:Activity .
  ?var_b prov:wasAssociatedWith ?this .
  ?var_c rdf:type dcat:Dataset .          # <-- added by filter: true
  ?var_c prov:wasGeneratedBy ?var_b .     # <-- added by filter: true
}
```

Now only activities that generated a Dataset will match.

**Implementation** in `sparql.py` (around line 136–144): the current check is `if s in source_classes and o in source_classes`. Add an OR condition:

```python
for triple in source_triples:
    s, p, o = triple[:3]
    is_filter = getattr(triple, 'filter', False) or (len(triple) > 3 and triple[3].get('filter'))
    if (s in source_classes and o in source_classes) or is_filter:
        # include in WHERE clause
```

The triple format in `bridge.yaml` would accept either a simple list `[s, p, o]` or a dict `{triple: [s, p, o], filter: true}`. The `yaml_reader.py` Triple type would need to accommodate this.

**Trade-offs**: Small, focused change. Doesn't duplicate bridge logic. Doesn't require negative reasoning. Aligns with the existing core/peripheral distinction — just gives the user explicit control.

#### Proposed fix: Option B — separate bridges per activity type

Write Bridge 1b-gen (for DataGeneratingActivity agents) and Bridge 1b-analysis (for DataAnalysis agents), each with the correct target process type:

```yaml
# bridge_1b_gen_agent.yaml — agents of data-producing activities
class_map:
  - source: "prov:Agent"
    target: "nfdi:NFDI_0000102"
  - source: "prov:Agent"
    target: "nfdi:NFDI_0000229"
    derived_iri: "suffix:_role"
  - source: "prov:Activity"
    target: "nfdi:NFDI_0010029"       # data producing process
  - source: "dcat:Dataset"
    target: "nfdi:NFDI_0000009"       # needed just for WHERE discrimination
```

```yaml
# bridge_1b_analysis_agent.yaml — agents of data analysis activities
class_map:
  - source: "prov:Agent"
    target: "nfdi:NFDI_0000102"
  - source: "prov:Agent"
    target: "nfdi:NFDI_0000229"
    derived_iri: "suffix:_role"
  - source: "prov:Activity"
    target: "nfdi:NFDI_0010035"       # data transformation process
  - source: "prov:Entity"
    target: "prov:Entity"             # AnalysisSourceData, for discrimination
```

**Trade-off**: Works within the current tool, but duplicates the agent splitting logic. Each new activity type needs another agent bridge. Semantically correct (different process types should have different role contexts), but scales poorly.

#### Proposed fix: Option C — FILTER NOT EXISTS (negative constraints)

The most surgical fix: a negative constraint — "match agents of activities that are NOT analysis activities":

```yaml
source_pattern:
  root: "prov:Agent"
  triples:
    - ["prov:Activity", "prov:wasAssociatedWith", "prov:Agent"]
  exclude:
    - ["prov:Activity", "prov:wasInformedBy", "?any"]  # analysis activities have this
```

This would generate `FILTER NOT EXISTS { ?var_b prov:wasInformedBy ?x }` in the WHERE clause.

**Trade-off**: Very powerful for discrimination, but a bigger tool change. Requires the user to know which negative patterns distinguish activity types.

### ISSUE-T3: No "type-only" bridges (all entries must appear in triples)
- **Phase**: 2a (Quantitative Attributes)
- **Severity**: Low — workaround exists but causes bridge duplication
- **Description**: The validator requires every class_map entry to appear in source_pattern and target_pattern triples. A bridge that only adds a `rdf:type` assertion without transforming any structural triple is not supported.
- **Impact**: For qudt:Quantity type enrichment, we need 3 nearly-identical bridges (one per parent type: Entity, Activity, Agent) instead of a single type-assertion bridge.

#### Proposed fix in detail

Allow bridges with empty triples lists if the class_map has at least one entry. The minimal bridge would look like:

```yaml
source_pattern:
  root: "qudt:Quantity"
  triples: []

target_pattern:
  triples: []

class_map:
  - source: "qudt:Quantity"
    target: "obo:IAO_0000027"
```

The generated SPARQL would be:

```sparql
CONSTRUCT {
  ?this rdf:type obo:IAO_0000027 .
}
WHERE {
  ?this rdf:type qudt:Quantity .
}
```

This is valid SPARQL and semantically correct — it simply enriches every `qudt:Quantity` instance with an additional type assertion, regardless of what it's connected to.

**Implementation**: The validator checks in two places need relaxing:
1. The check that `source_pattern.root` appears in a source triple — allow it to be absent if `triples` is empty.
2. The check that every class_map source/target appears in triples — allow absence if `triples` is empty and `class_map` has entries.

The SPARQL generator already handles this correctly: if `source_triples` is empty, the WHERE clause contains only `?this rdf:type <root> .` and the CONSTRUCT contains only the class_map type assertions. No code change needed in `sparql.py`.

**Benefit**: Eliminates the need for 3 near-identical bridges (2a-entity, 2a-activity, 2a-agent). A single type-only bridge covers all `qudt:Quantity` instances regardless of parent type.

### ISSUE-T4: Variable collision on same-type endpoints
- **Phase**: 2b (Qualitative Attributes on Entities)
- **Severity**: High — blocks a class of bridges entirely
- **Description**: When the same CURIE appears as both subject and object of a source triple (e.g., `["prov:Entity", "dcterms:relation", "prov:Entity"]`), the variable generator assigns the same variable to both, producing a self-referential pattern like `?this dcterms:relation ?this` that never matches.
- **Root cause**: `_generate_variable_names()` maps each unique CURIE to exactly one variable.
- **Blocked bridge**: Entity → QualitativeAttribute (both typed `prov:Entity`).

#### Proposed fix in detail

The root cause is in `sparql.py`, function `_generate_variable_names()` (line 24–48). It creates a `{curie: variable}` dict — each CURIE gets exactly one variable. When `prov:Entity` appears on both sides of a triple, both resolve to the same `?var_a`.

**The desired SPARQL** for an Entity→QualitativeAttribute bridge would be:

```sparql
CONSTRUCT {
  ?var_b rdf:type obo:IAO_0000027 .   # the qualitative attribute
  ?this dcterms:relation ?var_b .
}
WHERE {
  ?this rdf:type prov:Entity .         # the parent entity
  ?this dcterms:relation ?var_b .
  ?var_b rdf:type prov:Entity .        # the qualitative attribute (same type!)
}
```

Here `?this` and `?var_b` are both `prov:Entity`, but they're different individuals.

**Fix approach — positional class references**: Allow the same CURIE to appear multiple times in triples, distinguished by position. The bridge YAML would use indexed references:

```yaml
source_pattern:
  root: "prov:Entity"
  triples:
    - ["prov:Entity", "dcterms:relation", "prov:Entity#2"]
    #                                      ^^^^^^^^^^^^^ indexed reference

class_map:
  - source: "prov:Entity"       # the parent (position 1, root)
    target: "prov:Entity"
  - source: "prov:Entity#2"     # the qualitative attribute (position 2)
    target: "obo:IAO_0000027"
```

The `#2` suffix (or similar convention like `@2`, `[1]`) tells the variable generator to create a distinct variable. In the SPARQL, `prov:Entity#2` still produces `rdf:type prov:Entity` (the suffix is stripped for the type assertion) but binds to a separate variable `?var_b`.

**Implementation changes**:

1. `_generate_variable_names()` — detect indexed references and create separate variables:
   ```python
   def _generate_variable_names(entities: list[str]) -> dict[str, str]:
       # "prov:Entity" and "prov:Entity#2" get different variables
       # but both produce rdf:type prov:Entity in WHERE
       ...
   ```

2. A helper to strip the index suffix for type assertions:
   ```python
   def _base_curie(curie: str) -> str:
       """Strip positional index: 'prov:Entity#2' -> 'prov:Entity'"""
       return curie.split('#')[0] if '#' in curie and curie.split('#')[1].isdigit() else curie
   ```

3. WHERE clause generation (line 136–144) — use `_base_curie()` for `rdf:type` assertions but the full indexed key for variable lookup.

4. `yaml_reader.py` — the Triple and ClassMapEntry types need to allow indexed CURIEs.

**Alternative fix — use ISSUE-T3 (type-only bridges) combined with discrimination**:
If type-only bridges were supported (ISSUE-T3 fix), you could root on `prov:Entity` and just add `IAO:0000027` to ALL `prov:Entity` instances. But this is semantically wrong — EvaluatedEntity is NOT a data item. So ISSUE-T4 truly requires its own fix.

**Alternative — DCAT-AP+ schema fix (ISSUE-S2)**:
Give QualitativeAttribute a distinct `class_uri` (e.g., `dcatap:QualitativeAttribute`). This avoids the variable collision entirely and is arguably the more principled fix — a qualitative attribute *is* semantically different from the entity it describes, so sharing `prov:Entity` as the class_uri is debatable.

**Recommendation**: Implement both the tool fix (for generality) and consider the schema fix (for semantic clarity). The tool fix handles any future case where the same type appears on both sides; the schema fix makes the data self-describing.

## Schema Issues (DCAT-AP+)

### ISSUE-S1: Shared class_uri across multiple LinkML classes
- **Severity**: Medium — manageable via graph-shape discrimination in most cases
- **Description**: Multiple DCAT-AP+ classes share the same `class_uri`:
  - `prov:Entity`: Entity, EvaluatedEntity, AnalysisSourceData, QualitativeAttribute
  - `prov:Activity`: Activity, DataGeneratingActivity, DataAnalysis, EvaluatedActivity
- **Impact**: Bridges can't distinguish these by type alone; must rely on surrounding graph topology.
- **Mitigated by**: Graph-shape discrimination works for Phase 1 (Dataset→Activity pattern). Fails for same-type endpoints (ISSUE-T4).

### ISSUE-S2: QualitativeAttribute reuses prov:Entity class_uri
- **Severity**: High — directly causes ISSUE-T4
- **Description**: QualitativeAttribute is defined with `class_uri: prov:Entity`, identical to EvaluatedEntity (its typical parent). This makes `Entity → QualitativeAttribute` bridges impossible with the current tool because both endpoints have the same RDF type.
- **Potential schema fix**: Assign QualitativeAttribute a distinct class_uri (e.g., `dcatap:QualitativeAttribute` or `prov:Value`).

### ISSUE-S3: dcterms:relation as a generic attribute predicate
- **Severity**: Low — works, but semantically ambiguous in NFDICore context
- **Description**: Both `has_qualitative_attribute` and `has_quantitative_attribute` in DCAT-AP+ use `dcterms:relation` as their `slot_uri`. In the RDF, all attributes (quantitative and qualitative) hang off the same predicate. No structural difference exists between a quantitative and qualitative attribute connection beyond the object's type.
- **Impact**: Bridges can only distinguish quant vs qual by checking the object type (qudt:Quantity vs prov:Entity), which is sufficient for the tool's type-based matching.

## Mapping Issues (DCAT-AP+ → NFDICore Semantics)

### ISSUE-M1: Agent role differentiation
- **Phase**: 1b
- **Description**: All agents currently get the generic `NFDI_0000229` (NFDI role). In reality, spectrometers, solvents, acquisition nuclei, and calibration compounds play fundamentally different roles.
- **Status**: Deferred — DCAT-AP+ schema doesn't classify agents well enough yet. Revisit when agent taxonomy is refined.

### ISSUE-M2: EvaluatedActivity BFO mapping
- **Phase**: 4 (deferred)
- **Description**: How to map the evaluation relationship between a DataAnalysis and its target Activity in BFO? BFO restricts roles to independent continuants, so a process can't "bear" an evaluand role.
- **Status**: Needs dedicated semantic discussion. Deferred to Phase 4.

### ISSUE-M3: rdfs:Resource type assertions in diff output
- **Phase**: 2a, 2b
- **Severity**: Low — cosmetic
- **Description**: The SHACL rule engine adds `rdfs:Resource` type assertions to matched instances. These are technically correct but noisy.
- **Status**: SHACL engine behavior, not a bridge issue. Can be filtered from output.

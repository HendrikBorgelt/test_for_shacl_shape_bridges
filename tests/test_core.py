"""
Tests for the shacl_bridges core pipeline.

Each test is deliberately small and focused — testing one layer at a time
so failures are easy to locate.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from shacl_bridges.core.graph import (
    build_validation_graph,
    check_connectivity,
    longest_path_length,
    select_root_class,
)
from shacl_bridges.core.sparql import build_sparql_construct
from shacl_bridges.io.yaml_reader import BridgeMapping, Triple, load_mapping

HERE = Path(__file__).parent
BRIDGE_YAML = HERE.parent / "examples" / "process_to_experiment" / "mapping" / "bridge.yaml"
DATA_TTL = HERE / "test_data" / "data.ttl"
SPLIT_YAML = HERE / "test_data" / "split_bridge.yaml"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def mapping() -> BridgeMapping:
    return load_mapping(BRIDGE_YAML)


@pytest.fixture()
def simple_triples() -> list[Triple]:
    """Minimal source pattern: A → B → C (chain of 3 nodes)."""
    return [
        ("ex:A", "ex:hasB", "ex:B"),
        ("ex:B", "ex:hasC", "ex:C"),
    ]


@pytest.fixture()
def simple_alignment() -> dict[str, str]:
    return {"ex:A": "ex:X", "ex:B": "ex:Y", "ex:C": "ex:Z"}


@pytest.fixture()
def simple_target_triples() -> list[Triple]:
    return [
        ("ex:X", "ex:hasY", "ex:Y"),
        ("ex:Y", "ex:hasZ", "ex:Z"),
    ]


# ---------------------------------------------------------------------------
# yaml_reader
# ---------------------------------------------------------------------------

class TestLoadMapping:
    def test_loads_mapping(self, mapping: BridgeMapping):
        assert mapping.source_pattern.triples
        assert mapping.target_pattern.triples
        assert mapping.class_map

    def test_prefix_map(self, mapping: BridgeMapping):
        pm = mapping.prefix_map()
        assert "ex" in pm
        assert pm["ex"] == "http://example.org/ontology#"

    def test_root_class_from_yaml(self, mapping: BridgeMapping):
        assert mapping.root_class() == "ex:Process"

    def test_class_alignment(self, mapping: BridgeMapping):
        alignment = mapping.class_alignment()
        assert alignment["ex:Process"] == "ex:Experiment"
        assert alignment["ex:InputSettings"] == "ex:Parameters"

    def test_source_classes(self, mapping: BridgeMapping):
        sc = mapping.source_classes()
        assert "ex:Process" in sc
        assert "ex:Input" in sc

    def test_missing_required_key_raises(self, tmp_path: Path):
        bad_yaml = tmp_path / "bad.yaml"
        bad_yaml.write_text("prefixes:\n  ex: http://example.org/\n", encoding="utf-8")
        with pytest.raises(ValueError, match="missing required key"):
            load_mapping(bad_yaml)

    def test_malformed_triple_raises(self, tmp_path: Path):
        bad_yaml = tmp_path / "bad.yaml"
        bad_yaml.write_text(
            "prefixes:\n  ex: http://example.org/\n"
            "source_pattern:\n  triples:\n    - [ex:A, ex:p]\n"
            "target_pattern:\n  triples: []\n"
            "class_map: []\n",
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match="triple"):
            load_mapping(bad_yaml)


# ---------------------------------------------------------------------------
# graph
# ---------------------------------------------------------------------------

class TestGraphAnalysis:
    def test_build_validation_graph(self, simple_triples: list[Triple]):
        G = build_validation_graph(simple_triples)
        assert G.number_of_nodes() == 3
        assert G.number_of_edges() == 2
        assert G.has_edge("ex:A", "ex:B")

    def test_select_root_explicit(self, simple_triples: list[Triple]):
        root = select_root_class(simple_triples, explicit_root="ex:A")
        assert root == "ex:A"

    def test_select_root_auto(self, simple_triples: list[Triple]):
        # In chain A→B→C, B has highest closeness centrality
        root = select_root_class(simple_triples, explicit_root=None)
        assert root == "ex:B"

    def test_select_root_from_mapping(self, mapping: BridgeMapping):
        root = select_root_class(
            mapping.source_pattern.triples, mapping.root_class()
        )
        assert root == "ex:Process"

    def test_connectivity_ok(self, simple_triples: list[Triple]):
        assert check_connectivity(simple_triples, "ex:A") == []

    def test_connectivity_disconnected(self):
        triples = [
            ("ex:A", "ex:hasB", "ex:B"),
            ("ex:X", "ex:hasY", "ex:Y"),  # disconnected component
        ]
        issues = check_connectivity(triples, "ex:A")
        assert "ex:X" in issues or "ex:Y" in issues

    def test_longest_path(self, simple_triples: list[Triple]):
        G = build_validation_graph(simple_triples)
        assert longest_path_length(G) == 2


# ---------------------------------------------------------------------------
# sparql
# ---------------------------------------------------------------------------

class TestSparqlGeneration:
    def test_contains_construct_and_where(
        self,
        simple_triples: list[Triple],
        simple_alignment: dict[str, str],
        simple_target_triples: list[Triple],
    ):
        query = build_sparql_construct(
            simple_alignment, simple_triples, simple_target_triples,
            root_class="ex:A", prefix_map={"ex": "http://example.org/"},
        )
        assert "CONSTRUCT" in query
        assert "WHERE" in query

    def test_this_anchors_root(
        self,
        simple_triples: list[Triple],
        simple_alignment: dict[str, str],
        simple_target_triples: list[Triple],
    ):
        query = build_sparql_construct(
            simple_alignment, simple_triples, simple_target_triples,
            root_class="ex:A", prefix_map={"ex": "http://example.org/"},
        )
        assert "?this rdf:type ex:A" in query

    def test_target_types_in_construct(
        self,
        simple_triples: list[Triple],
        simple_alignment: dict[str, str],
        simple_target_triples: list[Triple],
    ):
        query = build_sparql_construct(
            simple_alignment, simple_triples, simple_target_triples,
            root_class="ex:A", prefix_map={"ex": "http://example.org/"},
        )
        assert "ex:X" in query
        assert "ex:Y" in query
        assert "ex:Z" in query

    def test_mapping_query(self, mapping: BridgeMapping):
        root = mapping.root_class()
        query = build_sparql_construct(
            mapping.class_alignment(),
            mapping.source_pattern.triples,
            mapping.target_pattern.triples,
            root_class=root,
            prefix_map=mapping.prefix_map(),
        )
        assert "ex:Experiment" in query
        assert "ex:ExperimentSetup" in query
        assert "?this rdf:type ex:Process" in query


# ---------------------------------------------------------------------------
# validator
# ---------------------------------------------------------------------------

class TestValidator:
    def test_valid_mapping_has_no_issues(self, mapping: BridgeMapping):
        from shacl_bridges.validate import Severity, validate_mapping
        issues = validate_mapping(mapping)
        errors = [i for i in issues if i.severity == Severity.ERROR]
        assert errors == [], f"Unexpected errors: {errors}"

    def test_missing_prefix_raises_error(self, mapping: BridgeMapping):
        from shacl_bridges.io.yaml_reader import ClassMapEntry
        from shacl_bridges.validate import Severity, validate_mapping

        # Add a class_map entry with an undeclared prefix
        extra = ClassMapEntry(source="foo:Undeclared", target="ex:Experiment")
        bad = BridgeMapping(
            metadata=mapping.metadata,
            prefixes=mapping.prefixes,
            source_pattern=mapping.source_pattern,
            target_pattern=mapping.target_pattern,
            class_map=[*mapping.class_map, extra],
        )
        issues = validate_mapping(bad)
        errors = [i for i in issues if i.severity == Severity.ERROR]
        assert any("foo" in i.message for i in errors)

    def test_root_not_in_source_raises_error(self, mapping: BridgeMapping):
        from shacl_bridges.io.yaml_reader import SourcePattern
        from shacl_bridges.validate import Severity, validate_mapping

        bad = BridgeMapping(
            metadata=mapping.metadata,
            prefixes=mapping.prefixes,
            source_pattern=SourcePattern(
                root="ex:NonExistent",
                triples=mapping.source_pattern.triples,
            ),
            target_pattern=mapping.target_pattern,
            class_map=mapping.class_map,
        )
        issues = validate_mapping(bad)
        errors = [i for i in issues if i.severity == Severity.ERROR]
        assert any("NonExistent" in i.message for i in errors)


# ---------------------------------------------------------------------------
# Instance split (derived_iri)
# ---------------------------------------------------------------------------

class TestInstanceSplit:
    @pytest.fixture()
    def split_mapping(self) -> BridgeMapping:
        return load_mapping(SPLIT_YAML)

    def test_loads_derived_entry(self, split_mapping: BridgeMapping):
        derived = split_mapping.derived_class_map()
        assert len(derived) == 1
        assert derived[0].target == "ex:AgentRole"
        assert derived[0].derived_iri == "suffix:_role"

    def test_class_alignment_excludes_derived(self, split_mapping: BridgeMapping):
        """class_alignment() must not include the derived entry."""
        alignment = split_mapping.class_alignment()
        # Only the regular ex:AgenticEntity → ex:Agent entry should appear
        assert alignment.get("ex:AgenticEntity") == "ex:Agent"
        assert "ex:AgentRole" not in alignment.values()

    def test_derived_class_in_target_classes(self, split_mapping: BridgeMapping):
        """target_classes() must include both regular and derived targets."""
        tc = split_mapping.target_classes()
        assert "ex:Agent" in tc
        assert "ex:AgentRole" in tc

    def test_sparql_contains_bind(self, split_mapping: BridgeMapping):
        """Generated SPARQL must contain a BIND for the minted IRI."""
        query = build_sparql_construct(
            split_mapping.class_alignment(),
            split_mapping.source_pattern.triples,
            split_mapping.target_pattern.triples,
            root_class="ex:AgenticEntity",
            prefix_map=split_mapping.prefix_map(),
            derived_entries=split_mapping.derived_class_map(),
        )
        assert "BIND" in query
        assert "_role" in query
        assert "?derived_AgentRole" in query

    def test_sparql_construct_has_derived_type(self, split_mapping: BridgeMapping):
        """CONSTRUCT clause must assert rdf:type for the minted instance."""
        query = build_sparql_construct(
            split_mapping.class_alignment(),
            split_mapping.source_pattern.triples,
            split_mapping.target_pattern.triples,
            root_class="ex:AgenticEntity",
            prefix_map=split_mapping.prefix_map(),
            derived_entries=split_mapping.derived_class_map(),
        )
        assert "?derived_AgentRole rdf:type ex:AgentRole" in query

    def test_sparql_construct_has_bearer_relation(self, split_mapping: BridgeMapping):
        """CONSTRUCT clause must wire the entity to its role via obo:RO_0000087."""
        query = build_sparql_construct(
            split_mapping.class_alignment(),
            split_mapping.source_pattern.triples,
            split_mapping.target_pattern.triples,
            root_class="ex:AgenticEntity",
            prefix_map=split_mapping.prefix_map(),
            derived_entries=split_mapping.derived_class_map(),
        )
        assert "obo:RO_0000087" in query

    def test_invalid_derived_iri_form_raises(self, tmp_path: Path):
        bad = tmp_path / "bad_split.yaml"
        bad.write_text(
            "prefixes:\n  ex: http://example.org/\n"
            "source_pattern:\n  triples:\n    - [ex:A, ex:p, ex:B]\n"
            "target_pattern:\n  triples: []\n"
            "class_map:\n"
            "  - source: ex:A\n    target: ex:B\n    derived_iri: uuid\n",
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match="derived_iri"):
            load_mapping(bad)


# ---------------------------------------------------------------------------
# End-to-end (integration — requires pyshacl)
# ---------------------------------------------------------------------------

class TestEndToEnd:
    def test_run_example(self, tmp_path: Path, mapping: BridgeMapping):
        """Run the full pipeline and verify the diff graph is non-empty."""
        from shacl_bridges import (
            check_connectivity,
            generate_shacl,
            run_bridge_from_files,
            save_result,
            select_root_class,
        )

        root = select_root_class(mapping.source_pattern.triples, mapping.root_class())
        assert check_connectivity(mapping.source_pattern.triples, root) == []

        shacl_ttl = generate_shacl(mapping, root)
        shape_path = tmp_path / "bridge.ttl"
        shape_path.write_text(shacl_ttl, encoding="utf-8")

        result = run_bridge_from_files(DATA_TTL, shape_path)

        assert result.expanded_graph is not None
        assert result.diff_graph is not None
        assert len(result.diff_graph) > 0

        expanded_path = tmp_path / "expanded.ttl"
        diff_path = tmp_path / "diff.ttl"
        save_result(result, expanded_path, diff_path)
        assert expanded_path.exists()
        assert diff_path.exists()

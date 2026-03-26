"""
Tests for the shacl_bridges core pipeline.

Each test is deliberately small and focused — testing one layer at a time
so failures are easy to locate.
"""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pandas as pd
import pytest

from shacl_bridges.core.graph import (
    build_validation_graph,
    check_connectivity,
    longest_path_length,
    select_root_class,
)
from shacl_bridges.core.sparql import build_sparql_construct
from shacl_bridges.io.csv_reader import BridgeMapping, load_mapping

HERE = Path(__file__).parent
MAPPING_DIR = HERE.parent / "examples" / "process_to_experiment" / "mapping"
DATA_TTL = HERE / "test_data" / "data.ttl"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def mapping() -> BridgeMapping:
    return load_mapping(MAPPING_DIR)


@pytest.fixture()
def simple_sv() -> pd.DataFrame:
    """Minimal shape-validation DataFrame: A → B → C."""
    return pd.DataFrame({
        "subject_id": ["ex:A", "ex:B"],
        "predicate_id": ["ex:hasB", "ex:hasC"],
        "object_id": ["ex:B", "ex:C"],
    })


@pytest.fixture()
def simple_sb() -> pd.DataFrame:
    """Minimal shape-bridge DataFrame."""
    return pd.DataFrame({
        "from_id": ["ex:A", "ex:B", "ex:C"],
        "to_id": ["ex:X", "ex:Y", "ex:Z"],
        "relation_id": ["ex:hasY", "ex:hasZ", "-"],
        "target_id": ["ex:Y", "ex:Z", "-"],
        "is_root": [True, False, False],
    })


# ---------------------------------------------------------------------------
# csv_reader
# ---------------------------------------------------------------------------

class TestLoadMapping:
    def test_loads_all_tables(self, mapping: BridgeMapping):
        assert not mapping.prefixes.empty
        assert not mapping.shape_validation.empty
        assert not mapping.shape_bridge.empty

    def test_prefix_map(self, mapping: BridgeMapping):
        pm = mapping.prefix_map()
        assert "ex" in pm
        assert pm["ex"] == "http://example.org/ontology#"

    def test_root_class_from_csv(self, mapping: BridgeMapping):
        root = mapping.root_class()
        assert root == "ex:Process"

    def test_missing_required_column_raises(self, tmp_path: Path):
        bad_csv = tmp_path / "prefixes.csv"
        bad_csv.write_text("wrong_col,namespace\nex,http://example.org/\n")
        with pytest.raises(ValueError, match="missing required column"):
            from shacl_bridges.io.csv_reader import load_prefixes
            load_prefixes(bad_csv)


# ---------------------------------------------------------------------------
# graph
# ---------------------------------------------------------------------------

class TestGraphAnalysis:
    def test_build_validation_graph(self, simple_sv: pd.DataFrame):
        G = build_validation_graph(simple_sv)
        assert G.number_of_nodes() == 3
        assert G.number_of_edges() == 2
        assert G.has_edge("ex:A", "ex:B")

    def test_select_root_explicit(self, simple_sv: pd.DataFrame):
        root = select_root_class(simple_sv, explicit_root="ex:A")
        assert root == "ex:A"

    def test_select_root_auto(self, simple_sv: pd.DataFrame):
        # In chain A→B→C, B has highest closeness centrality
        root = select_root_class(simple_sv, explicit_root=None)
        assert root == "ex:B"

    def test_select_root_from_mapping(self, mapping: BridgeMapping):
        root = select_root_class(mapping.shape_validation, mapping.root_class())
        assert root == "ex:Process"

    def test_connectivity_ok(self, simple_sv: pd.DataFrame):
        issues = check_connectivity(simple_sv, "ex:A")
        assert issues == []

    def test_connectivity_disconnected(self):
        sv = pd.DataFrame({
            "subject_id": ["ex:A", "ex:X"],
            "predicate_id": ["ex:hasB", "ex:hasY"],
            "object_id": ["ex:B", "ex:Y"],
        })
        issues = check_connectivity(sv, "ex:A")
        assert "ex:X" in issues or "ex:Y" in issues

    def test_longest_path(self, simple_sv: pd.DataFrame):
        G = build_validation_graph(simple_sv)
        assert longest_path_length(G) == 2


# ---------------------------------------------------------------------------
# sparql
# ---------------------------------------------------------------------------

class TestSparqlGeneration:
    def test_contains_construct(self, simple_sv: pd.DataFrame, simple_sb: pd.DataFrame):
        query = build_sparql_construct(
            simple_sb, simple_sv, root_class="ex:A",
            prefix_map={"ex": "http://example.org/"}
        )
        assert "CONSTRUCT" in query
        assert "WHERE" in query

    def test_this_in_where(self, simple_sv: pd.DataFrame, simple_sb: pd.DataFrame):
        query = build_sparql_construct(
            simple_sb, simple_sv, root_class="ex:A",
            prefix_map={"ex": "http://example.org/"}
        )
        assert "?this rdf:type ex:A" in query

    def test_target_types_in_construct(self, simple_sv: pd.DataFrame, simple_sb: pd.DataFrame):
        query = build_sparql_construct(
            simple_sb, simple_sv, root_class="ex:A",
            prefix_map={"ex": "http://example.org/"}
        )
        assert "ex:X" in query
        assert "ex:Y" in query
        assert "ex:Z" in query

    def test_mapping_query(self, mapping: BridgeMapping):
        root = mapping.root_class()
        query = build_sparql_construct(
            mapping.shape_bridge,
            mapping.shape_validation,
            root_class=root,
            prefix_map=mapping.prefix_map(),
        )
        assert "ex:Experiment" in query
        assert "ex:ExperimentSetup" in query
        assert "?this rdf:type ex:Process" in query


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

        root = select_root_class(mapping.shape_validation, mapping.root_class())
        assert check_connectivity(mapping.shape_validation, root) == []

        shacl_ttl = generate_shacl(mapping, root)
        shape_path = tmp_path / "bridge.ttl"
        shape_path.write_text(shacl_ttl, encoding="utf-8")

        result = run_bridge_from_files(DATA_TTL, shape_path)

        assert result.expanded_graph is not None
        assert result.diff_graph is not None
        # The diff should contain the bridged triples
        assert len(result.diff_graph) > 0

        expanded_path = tmp_path / "expanded.ttl"
        diff_path = tmp_path / "diff.ttl"
        save_result(result, expanded_path, diff_path)
        assert expanded_path.exists()
        assert diff_path.exists()

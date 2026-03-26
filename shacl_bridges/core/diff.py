"""
Graph validation and diff computation.

Runs pyshacl in two passes:
1. *Base pass*: validates the data graph against itself (no external shape),
   with RDFS inference enabled. This captures any triples that RDFS alone
   would add and establishes the baseline.
2. *Bridge pass*: runs the generated SHACL shape against the data graph.
   The SPARQL CONSTRUCT rule fires and adds new triples.

The diff between pass-1 and pass-2 (via rdflib's isomorphic graph diff) gives
exactly the triples introduced by the bridge — nothing more.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from pyshacl import Validator
from rdflib import Graph
from rdflib.compare import graph_diff, to_isomorphic


@dataclass
class BridgeResult:
    """Outcome of running the bridge pipeline on a data graph."""

    expanded_graph: Graph
    """The full data graph after SHACL rule application (base + bridged triples)."""

    diff_graph: Graph
    """Only the triples introduced by the bridge (expanded minus inferred base)."""

    conforms: bool
    """Whether the data graph conforms to the validation constraints."""

    report_text: str
    """Human-readable SHACL validation report."""

    report_graph: Graph
    """Machine-readable SHACL report graph."""


def run_bridge(
    data_graph: Graph,
    shacl_graph: Graph,
    inference: str = "rdfs",
) -> BridgeResult:
    """Apply a SHACL bridge shape to *data_graph* and return the result.

    Args:
        data_graph: The instance data to transform.
        shacl_graph: The generated SHACL shape (containing the SPARQLRule).
        inference: Reasoner to apply before validation. ``"rdfs"`` is the default
                   and sufficient for most harmonization needs.  Pass ``"none"``
                   to disable inference entirely.

    Returns:
        A :class:`BridgeResult` with expanded graph, diff, and report.
    """
    # Pass 1 — baseline with inference only, no external shape
    val_base = Validator(
        data_graph,
        options={"advanced": True, "inference": inference},
    )
    _, _, _ = val_base.run()
    inferred_base = val_base.target_graph

    # Pass 2 — full bridge shape
    val_bridge = Validator(
        data_graph,
        shacl_graph=shacl_graph,
        options={"advanced": True, "inference": inference},
    )
    conforms, report_g, report_text = val_bridge.run()
    expanded = val_bridge.target_graph

    # Diff
    iso_base = to_isomorphic(inferred_base)
    iso_expanded = to_isomorphic(expanded)
    _both, _only_base, only_expanded = graph_diff(iso_base, iso_expanded)

    return BridgeResult(
        expanded_graph=expanded,
        diff_graph=only_expanded,
        conforms=bool(conforms),
        report_text=report_text,
        report_graph=report_g,
    )


def run_bridge_from_files(
    data_path: str | Path,
    shacl_path: str | Path,
    inference: str = "rdfs",
) -> BridgeResult:
    """Convenience wrapper: load graphs from file paths, then call :func:`run_bridge`.

    Args:
        data_path: Path to the instance data Turtle file.
        shacl_path: Path to the SHACL shape Turtle file.
        inference: Reasoner to apply.

    Returns:
        A :class:`BridgeResult`.
    """
    data_graph = Graph()
    data_graph.parse(str(data_path), format="turtle")

    shacl_graph = Graph()
    shacl_graph.parse(str(shacl_path), format="turtle")

    return run_bridge(data_graph, shacl_graph, inference=inference)


def save_result(
    result: BridgeResult,
    expanded_path: str | Path,
    diff_path: str | Path,
) -> None:
    """Serialize expanded and diff graphs to Turtle files.

    Args:
        result: Output of :func:`run_bridge`.
        expanded_path: Destination path for the expanded graph.
        diff_path: Destination path for the diff graph.
    """
    result.expanded_graph.serialize(destination=str(expanded_path), format="turtle")
    result.diff_graph.serialize(destination=str(diff_path), format="turtle")

"""
shacl_bridges — N-to-m semantic mapping via SHACL shapes with SPARQL CONSTRUCT rules.

Typical usage::

    from shacl_bridges.io.csv_reader import load_mapping
    from shacl_bridges.core.graph import select_root_class, check_connectivity
    from shacl_bridges.core.shacl import generate_shacl
    from shacl_bridges.core.diff import run_bridge_from_files, save_result

    mapping = load_mapping("examples/process_to_experiment/mapping/")
    root = select_root_class(mapping.shape_validation, mapping.root_class())
    issues = check_connectivity(mapping.shape_validation, root)
    if issues:
        raise ValueError(f"Disconnected nodes for root {root!r}: {issues}")

    shacl_ttl = generate_shacl(mapping, root)
    with open("bridge_shape.ttl", "w") as f:
        f.write(shacl_ttl)

    result = run_bridge_from_files("data.ttl", "bridge_shape.ttl")
    save_result(result, "expanded.ttl", "diff.ttl")
"""

from shacl_bridges.core.diff import BridgeResult, run_bridge, run_bridge_from_files, save_result
from shacl_bridges.core.graph import check_connectivity, select_root_class
from shacl_bridges.core.shacl import generate_shacl
from shacl_bridges.io.csv_reader import BridgeMapping, load_mapping
from shacl_bridges.io.rdf_utils import harmonize_to_turtle

__all__ = [
    "load_mapping",
    "BridgeMapping",
    "select_root_class",
    "check_connectivity",
    "generate_shacl",
    "run_bridge",
    "run_bridge_from_files",
    "save_result",
    "BridgeResult",
    "harmonize_to_turtle",
]

"""
shacl_bridges — N-to-m semantic mapping via SHACL shapes with SPARQL CONSTRUCT rules.

Typical usage::

    from shacl_bridges.io.yaml_reader import load_mapping
    from shacl_bridges.core.graph import select_root_class, check_connectivity
    from shacl_bridges.core.shacl import generate_shacl
    from shacl_bridges.core.diff import run_bridge_from_files, save_result

    mapping = load_mapping("bridge.yaml")
    root = select_root_class(mapping.source_pattern.triples, mapping.root_class())

    issues = check_connectivity(mapping.source_pattern.triples, root)
    if issues:
        raise ValueError(f"Disconnected nodes for root {root!r}: {issues}")

    shacl_ttl = generate_shacl(mapping, root)
    with open("bridge_shape.ttl", "w") as f:
        f.write(shacl_ttl)

    result = run_bridge_from_files("data.ttl", "bridge_shape.ttl")
    save_result(result, "expanded.ttl", "diff.ttl")

Or use the CLI::

    shacl-bridges validate  bridge.yaml
    shacl-bridges diagram   bridge.yaml -o diagram.mmd
    shacl-bridges generate  bridge.yaml -o bridge_shape.ttl
    shacl-bridges run       bridge.yaml data.ttl
"""

from shacl_bridges.core.diff import BridgeResult, run_bridge, run_bridge_from_files, save_result
from shacl_bridges.core.graph import check_connectivity, select_root_class
from shacl_bridges.core.shacl import generate_shacl
from shacl_bridges.io.yaml_reader import BridgeMapping, load_mapping
from shacl_bridges.io.rdf_utils import harmonize_to_turtle

__all__ = [
    # IO
    "load_mapping",
    "BridgeMapping",
    # Graph analysis
    "select_root_class",
    "check_connectivity",
    # SHACL generation
    "generate_shacl",
    # Bridge execution
    "run_bridge",
    "run_bridge_from_files",
    "save_result",
    "BridgeResult",
    # RDF utilities
    "harmonize_to_turtle",
]

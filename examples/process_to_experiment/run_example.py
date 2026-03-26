"""
End-to-end example: Process → Experiment design pattern bridge.

Run from the repository root::

    python examples/process_to_experiment/run_example.py

Or via the justfile::

    just example

Outputs (written to this directory):
- ``bridge_shape.ttl``  — generated SHACL shape with embedded SPARQL rule
- ``expanded.ttl``      — instance data with all bridged triples added
- ``diff.ttl``          — only the triples introduced by the bridge
- ``diagram.mmd``       — Mermaid diagram of the mapping
"""

from pathlib import Path

from shacl_bridges import (
    check_connectivity,
    generate_shacl,
    load_mapping,
    run_bridge_from_files,
    save_result,
    select_root_class,
)
from shacl_bridges.visualize.mermaid import generate_mermaid

HERE = Path(__file__).parent


def main() -> None:
    # 1. Load mapping from CSV files
    print("Loading mapping…")
    mapping = load_mapping(HERE / "mapping")

    # 2. Select root class (uses is_root from CSV, falls back to centrality)
    root = select_root_class(mapping.shape_validation, mapping.root_class())
    print(f"  Root class: {root}")

    # 3. Connectivity check — fail early with a clear error if disconnected
    issues = check_connectivity(mapping.shape_validation, root)
    if issues:
        raise ValueError(
            f"The validation pattern contains nodes not reachable from '{root}': "
            f"{issues}. "
            "Mark a different root class with is_root=true in shape_bridge.csv, "
            "or add the missing relationships to shape_validation.csv."
        )
    print("  Connectivity check passed.")

    # 4. Generate SHACL shape
    print("Generating SHACL shape…")
    shacl_ttl = generate_shacl(mapping, root)
    shape_path = HERE / "bridge_shape.ttl"
    shape_path.write_text(shacl_ttl, encoding="utf-8")
    print(f"  Written: {shape_path}")

    # 5. Run the bridge
    print("Running bridge…")
    result = run_bridge_from_files(HERE / "data.ttl", shape_path)
    print(f"  Conforms: {result.conforms}")
    if not result.conforms:
        print("  Validation report:")
        print(result.report_text)

    # 6. Save outputs
    expanded_path = HERE / "expanded.ttl"
    diff_path = HERE / "diff.ttl"
    save_result(result, expanded_path, diff_path)
    print(f"  Written: {expanded_path}")
    print(f"  Written: {diff_path}")

    # 7. Generate Mermaid diagram
    print("Generating Mermaid diagram…")
    diagram = generate_mermaid(mapping)
    diagram_path = HERE / "diagram.mmd"
    diagram_path.write_text(diagram, encoding="utf-8")
    print(f"  Written: {diagram_path}")

    # Quick summary
    n_diff = len(result.diff_graph)
    print(f"\nDone. Bridge added {n_diff} new triples.")


if __name__ == "__main__":
    main()

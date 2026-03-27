"""
Command-line interface for SHACL Bridges.

Available subcommands::

    shacl-bridges validate  BRIDGE_YAML          # validate a bridge YAML file
    shacl-bridges diagram   BRIDGE_YAML [-o FILE] # generate a Mermaid diagram
    shacl-bridges generate  BRIDGE_YAML [-o FILE] # generate a SHACL Turtle shape
    shacl-bridges run       BRIDGE_YAML DATA_TTL  # run the bridge on instance data
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Subcommand implementations
# ---------------------------------------------------------------------------

def _cmd_validate(args: argparse.Namespace) -> int:
    from shacl_bridges.io.yaml_reader import load_mapping
    from shacl_bridges.validate import Severity, validate_mapping

    try:
        mapping = load_mapping(args.mapping)
    except Exception as exc:
        print(f"✗  Could not load '{args.mapping}': {exc}", file=sys.stderr)
        return 1

    issues = validate_mapping(mapping)
    errors = [i for i in issues if i.severity == Severity.ERROR]
    warnings = [i for i in issues if i.severity == Severity.WARNING]

    if not issues:
        print(f"✓  {args.mapping}: valid")
        return 0

    for issue in issues:
        print(issue)

    parts = []
    if errors:
        parts.append(f"{len(errors)} error(s)")
    if warnings:
        parts.append(f"{len(warnings)} warning(s)")
    print(f"\n{', '.join(parts)}")
    return 1 if errors else 0


def _cmd_diagram(args: argparse.Namespace) -> int:
    from shacl_bridges.io.yaml_reader import load_mapping
    from shacl_bridges.visualize.mermaid import generate_mermaid_markdown

    try:
        mapping = load_mapping(args.mapping)
    except Exception as exc:
        print(f"✗  Could not load '{args.mapping}': {exc}", file=sys.stderr)
        return 1

    diagram = generate_mermaid_markdown(mapping)

    if args.output:
        Path(args.output).write_text(diagram, encoding="utf-8")
        print(f"Written: {args.output}")
    else:
        print(diagram)
    return 0


def _cmd_generate(args: argparse.Namespace) -> int:
    from shacl_bridges.core.graph import check_connectivity, select_root_class
    from shacl_bridges.core.shacl import generate_shacl
    from shacl_bridges.io.yaml_reader import load_mapping

    try:
        mapping = load_mapping(args.mapping)
    except Exception as exc:
        print(f"✗  Could not load '{args.mapping}': {exc}", file=sys.stderr)
        return 1

    root = select_root_class(mapping.source_pattern.triples, mapping.root_class())
    disconnected = check_connectivity(mapping.source_pattern.triples, root)
    if disconnected:
        print(
            f"✗  Disconnected nodes from root '{root}': {disconnected}\n"
            "   Fix source_pattern.triples or set source_pattern.root explicitly.",
            file=sys.stderr,
        )
        return 1

    shacl_ttl = generate_shacl(mapping, root)

    if args.output:
        Path(args.output).write_text(shacl_ttl, encoding="utf-8")
        print(f"Written: {args.output}")
    else:
        print(shacl_ttl)
    return 0


def _cmd_run(args: argparse.Namespace) -> int:
    from shacl_bridges.core.diff import run_bridge_from_files, save_result
    from shacl_bridges.core.graph import check_connectivity, select_root_class
    from shacl_bridges.core.shacl import generate_shacl
    from shacl_bridges.io.yaml_reader import load_mapping

    try:
        mapping = load_mapping(args.mapping)
    except Exception as exc:
        print(f"✗  Could not load '{args.mapping}': {exc}", file=sys.stderr)
        return 1

    root = select_root_class(mapping.source_pattern.triples, mapping.root_class())
    disconnected = check_connectivity(mapping.source_pattern.triples, root)
    if disconnected:
        print(f"✗  Disconnected nodes: {disconnected}", file=sys.stderr)
        return 1

    shacl_ttl = generate_shacl(mapping, root)
    shape_path = Path(args.mapping).with_suffix(".shacl.ttl")
    shape_path.write_text(shacl_ttl, encoding="utf-8")

    result = run_bridge_from_files(args.data, shape_path, inference=args.inference)
    save_result(result, args.expanded, args.diff)

    status = "conforms" if result.conforms else "does NOT conform"
    print(f"Data {status} to source pattern.")
    print(f"Bridge added {len(result.diff_graph)} new triple(s).")
    print(f"Written: {args.expanded}")
    print(f"Written: {args.diff}")
    return 0 if result.conforms else 1


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="shacl-bridges",
        description=(
            "N-to-m semantic mapping via SHACL shapes with SPARQL CONSTRUCT rules.\n\n"
            "Run 'shacl-bridges <command> --help' for per-command options."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", metavar="<command>")

    # validate
    val_p = sub.add_parser(
        "validate",
        help="Validate a bridge YAML file",
        description="Check a bridge YAML file for structural and semantic errors.",
    )
    val_p.add_argument("mapping", metavar="BRIDGE_YAML", help="Path to bridge YAML file")

    # diagram
    dia_p = sub.add_parser(
        "diagram",
        help="Generate a Mermaid diagram from a bridge YAML file",
        description=(
            "Produce a Mermaid flowchart showing the source pattern, target pattern, "
            "and SHACL bridge connections."
        ),
    )
    dia_p.add_argument("mapping", metavar="BRIDGE_YAML")
    dia_p.add_argument(
        "-o", "--output", metavar="FILE",
        help="Write diagram to FILE (default: stdout)",
    )

    # generate
    gen_p = sub.add_parser(
        "generate",
        help="Generate a SHACL Turtle shape from a bridge YAML file",
    )
    gen_p.add_argument("mapping", metavar="BRIDGE_YAML")
    gen_p.add_argument(
        "-o", "--output", metavar="FILE",
        help="Write shape to FILE (default: stdout)",
    )

    # run
    run_p = sub.add_parser(
        "run",
        help="Run the bridge on instance data",
        description=(
            "Generate the SHACL shape from the bridge YAML, apply it to the data "
            "graph, and write the expanded and diff graphs."
        ),
    )
    run_p.add_argument("mapping", metavar="BRIDGE_YAML")
    run_p.add_argument("data", metavar="DATA_TTL", help="Instance data Turtle file")
    run_p.add_argument(
        "--expanded", default="expanded.ttl", metavar="FILE",
        help="Output path for the expanded graph (default: expanded.ttl)",
    )
    run_p.add_argument(
        "--diff", default="diff.ttl", metavar="FILE",
        help="Output path for the diff graph (default: diff.ttl)",
    )
    run_p.add_argument(
        "--inference", default="rdfs", choices=["rdfs", "owlrl", "none"],
        help="Reasoner to apply before validation (default: rdfs)",
    )

    return parser


def main(argv: list[str] | None = None) -> None:
    """Entry point for the ``shacl-bridges`` CLI."""
    # Ensure Unicode output works on Windows terminals
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    parser = _build_parser()
    args = parser.parse_args(argv)

    dispatch = {
        "validate": _cmd_validate,
        "diagram": _cmd_diagram,
        "generate": _cmd_generate,
        "run": _cmd_run,
    }

    if args.command in dispatch:
        sys.exit(dispatch[args.command](args))
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()

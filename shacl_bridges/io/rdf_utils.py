"""
Utilities for loading and normalizing RDF graphs.

The primary purpose here is syntax harmonization: converting any RDF serialization
(RDF/XML, OWL/XML, Turtle, N-Triples, JSON-LD, etc.) to a canonical Turtle
representation before the bridge pipeline runs. This avoids blank-node ID
collisions and namespace prefix inconsistencies that arise when mixing serialization
styles from tools like Protégé, OWLTools, or robot.

No semantic inference is performed here. That belongs in core/diff.py via pyshacl.
"""

from __future__ import annotations

from pathlib import Path

from rdflib import Graph


# rdflib format strings for the serializations we explicitly advertise support for.
# rdflib can usually auto-detect format, but being explicit is safer for edge cases.
_FORMAT_MAP: dict[str, str] = {
    ".ttl": "turtle",
    ".turtle": "turtle",
    ".rdf": "xml",
    ".owl": "xml",
    ".xml": "xml",
    ".nt": "nt",
    ".nq": "nquads",
    ".n3": "n3",
    ".jsonld": "json-ld",
    ".json": "json-ld",
    ".trig": "trig",
}


def _guess_format(path: Path) -> str:
    suffix = path.suffix.lower()
    return _FORMAT_MAP.get(suffix, "turtle")


def load_graph(source: str | Path, fmt: str | None = None) -> Graph:
    """Load an RDF graph from *source*, auto-detecting serialization if *fmt* is None.

    Args:
        source: File path or URL.
        fmt: Explicit rdflib format string (e.g. ``"xml"``, ``"turtle"``).
             When *None* the format is guessed from the file extension.

    Returns:
        A parsed :class:`rdflib.Graph`.
    """
    path = Path(source)
    resolved_fmt = fmt or _guess_format(path)
    g = Graph()
    g.parse(str(path), format=resolved_fmt)
    return g


def harmonize_to_turtle(
    source: str | Path,
    destination: str | Path | None = None,
    fmt: str | None = None,
) -> Graph:
    """Load *source* in any RDF serialization and re-serialize as Turtle.

    This normalizes syntax differences between tools (Protégé RDF/XML,
    robot OWL/XML, hand-written Turtle, etc.) before the bridge pipeline runs.
    No inference is applied.

    Args:
        source: Input RDF file (any serialization).
        destination: Output ``.ttl`` path. When *None* the file is written
                     alongside *source* with a ``.ttl`` suffix replacing the
                     original extension.
        fmt: Force an input format string instead of auto-detecting.

    Returns:
        The loaded :class:`rdflib.Graph` (the in-memory representation after
        round-tripping through rdflib's parser/serializer).
    """
    source = Path(source)
    g = load_graph(source, fmt=fmt)

    if destination is None:
        destination = source.with_suffix(".ttl")
    destination = Path(destination)

    g.serialize(destination=str(destination), format="turtle")
    return g


def harmonize_many(
    sources: list[str | Path],
    output_dir: str | Path | None = None,
    fmt: str | None = None,
) -> dict[Path, Graph]:
    """Harmonize multiple RDF files to Turtle in one call.

    Args:
        sources: List of input file paths.
        output_dir: Directory for output files. When *None* each file is written
                    next to its source.
        fmt: Force an input format for all files.

    Returns:
        Mapping from output path to loaded :class:`rdflib.Graph`.
    """
    results: dict[Path, Graph] = {}
    for src in sources:
        src = Path(src)
        if output_dir is not None:
            dest = Path(output_dir) / src.with_suffix(".ttl").name
        else:
            dest = None
        g = harmonize_to_turtle(src, destination=dest, fmt=fmt)
        out_path = dest if dest is not None else src.with_suffix(".ttl")
        results[out_path] = g
    return results

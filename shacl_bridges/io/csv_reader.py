"""
CSV reader for SSSOM-inspired bridge mapping files.

The tool uses four CSV files to define a mapping:

* ``prefixes.csv``          — namespace declarations
* ``classes.csv``           — class/concept labels and CURIEs (optional, for visualization)
* ``shape_validation.csv``  — S-P-O triples defining the *source* design pattern
* ``shape_bridge.csv``      — From-To-Relation-Target transformation rules

Column schemas are documented in ``docs/csv_format.md``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import io

import pandas as pd


def _read_csv_strip_comments(path: str | Path) -> pd.DataFrame:
    """Read a CSV file, ignoring lines that START with '#'.

    pandas ``comment="#"`` treats ``#`` as an inline comment character, which
    truncates URIs containing ``#`` (e.g. ``http://example.org/ontology#``).
    This helper strips only full-line comments before handing the data to pandas.
    """
    path = Path(path)
    lines = [
        line for line in path.read_text(encoding="utf-8").splitlines()
        if not line.lstrip().startswith("#")
    ]
    return pd.read_csv(io.StringIO("\n".join(lines)), skip_blank_lines=True).fillna("")


# ---------------------------------------------------------------------------
# Dataclass holding all four tables
# ---------------------------------------------------------------------------

@dataclass
class BridgeMapping:
    """All tables that make up one bridge mapping definition."""

    prefixes: pd.DataFrame
    """Columns: ``prefix``, ``namespace``, ``comment`` (optional)."""

    shape_validation: pd.DataFrame
    """Columns: ``subject_id``, ``predicate_id``, ``object_id``, ``comment`` (optional)."""

    shape_bridge: pd.DataFrame
    """Columns: ``from_id``, ``to_id``, ``relation_id``, ``target_id``,
    ``is_root`` (optional), ``mapping_justification`` (optional), ``comment`` (optional)."""

    classes: pd.DataFrame = field(default_factory=pd.DataFrame)
    """Optional. Columns: ``id``, ``label``, ``description``."""

    def prefix_map(self) -> dict[str, str]:
        """Return ``{prefix: namespace}`` dict for use in SHACL/SPARQL generation."""
        return dict(zip(self.prefixes["prefix"], self.prefixes["namespace"]))

    def root_class(self) -> str | None:
        """Return the CURIE of the explicitly marked root class, or *None* if not set."""
        if "is_root" not in self.shape_bridge.columns:
            return None
        roots = self.shape_bridge.loc[
            self.shape_bridge["is_root"].astype(str).str.lower() == "true", "from_id"
        ]
        if roots.empty:
            return None
        return str(roots.iloc[0])


# ---------------------------------------------------------------------------
# Required columns per file
# ---------------------------------------------------------------------------

_REQUIRED: dict[str, list[str]] = {
    "prefixes": ["prefix", "namespace"],
    "shape_validation": ["subject_id", "predicate_id", "object_id"],
    "shape_bridge": ["from_id", "to_id", "relation_id", "target_id"],
    "classes": ["id", "label"],
}


def _validate_columns(df: pd.DataFrame, name: str) -> None:
    missing = [c for c in _REQUIRED[name] if c not in df.columns]
    if missing:
        raise ValueError(
            f"{name}.csv is missing required column(s): {missing}. "
            f"Found columns: {list(df.columns)}"
        )


# ---------------------------------------------------------------------------
# Public loaders
# ---------------------------------------------------------------------------

def load_prefixes(path: str | Path) -> pd.DataFrame:
    """Load ``prefixes.csv``."""
    df = _read_csv_strip_comments(path)
    _validate_columns(df, "prefixes")
    return df


def load_shape_validation(path: str | Path) -> pd.DataFrame:
    """Load ``shape_validation.csv``.

    The ``-`` placeholder in ``subject_id`` or ``object_id`` is forward-filled
    from the previous row (same convention as the original Excel sheets).
    """
    df = _read_csv_strip_comments(path)
    _validate_columns(df, "shape_validation")
    for col in ("subject_id", "predicate_id", "object_id"):
        df[col] = df[col].replace("-", pd.NA).ffill()
    return df


def load_shape_bridge(path: str | Path) -> pd.DataFrame:
    """Load ``shape_bridge.csv``.

    The ``-`` placeholder in ``from_id`` and ``to_id`` is forward-filled.
    Rows where both ``relation_id`` and ``target_id`` are ``-`` represent
    terminal nodes (no outgoing relation in the target pattern).
    """
    df = _read_csv_strip_comments(path)
    _validate_columns(df, "shape_bridge")
    for col in ("from_id", "to_id"):
        df[col] = df[col].replace("-", pd.NA).ffill()
    # Normalise is_root to bool if present
    if "is_root" in df.columns:
        df["is_root"] = df["is_root"].astype(str).str.lower() == "true"
    return df


def load_classes(path: str | Path) -> pd.DataFrame:
    """Load optional ``classes.csv``."""
    df = _read_csv_strip_comments(path)
    _validate_columns(df, "classes")
    return df


def load_mapping(directory: str | Path) -> BridgeMapping:
    """Load a full :class:`BridgeMapping` from a directory containing the four CSVs.

    The directory must contain ``prefixes.csv``, ``shape_validation.csv``, and
    ``shape_bridge.csv``. ``classes.csv`` is optional.

    Args:
        directory: Path to the folder holding the CSV files.

    Returns:
        A :class:`BridgeMapping` with all tables populated.
    """
    d = Path(directory)

    prefixes = load_prefixes(d / "prefixes.csv")
    shape_validation = load_shape_validation(d / "shape_validation.csv")
    shape_bridge = load_shape_bridge(d / "shape_bridge.csv")

    classes_path = d / "classes.csv"
    classes = load_classes(classes_path) if classes_path.exists() else pd.DataFrame()

    return BridgeMapping(
        prefixes=prefixes,
        shape_validation=shape_validation,
        shape_bridge=shape_bridge,
        classes=classes,
    )

"""Stage 18 read-only loaders for a Stage 17 output directory.

Stage 18 consumes a completed Stage 17 output directory as its sole
input. This module enforces the input contract:

  * All five required artifacts (four CSVs + manifest.json) are
    present.
  * Each CSV begins with the exact header tuple Stage 17 emitted
    (verified against locally duplicated constants in
    ``PHX2.stage18.constants``; no Stage 17 imports).
  * Each CSV data row has exactly the expected number of cells.
  * The manifest parses as JSON, the top-level value is an object,
    and ``schema_version == 'stage17_run_manifest_v0'``.

All file opens use ``newline=""`` so the LF newlines Stage 17 wrote
survive intact across platforms; the reader does not normalize,
transcode, or re-format any value -- cells are returned as the raw
strings the underlying ``csv.reader`` produced. Type coercion to
int, float, or bool is the consumer's job (Phase 18.2 metrics and
classifier).

Empty-file semantics:

  * A required CSV with **no header line** is a B01 violation.
  * A required CSV with **only a header line** (zero data rows) is
    valid; this is the common case for ``unevaluable_breakdown.csv``
    on runs that produced no UNEVALUABLE evaluations.
  * A truly empty manifest.json (zero bytes / whitespace only) is a
    B01 violation, surfaced before JSON parsing.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, NamedTuple, Sequence

from PHX2.stage18.constants import (
    COARSE_COLUMNS,
    COARSE_FILENAME,
    DATA_QUALITY_COLUMNS,
    DATA_QUALITY_FILENAME,
    HEADLINE_COLUMNS,
    HEADLINE_FILENAME,
    MANIFEST_FILENAME,
    REQUIRED_INPUT_FILES,
    STAGE17_MANIFEST_SCHEMA_VERSION,
    UNEVALUABLE_BREAKDOWN_FILENAME,
    UNEVALUABLE_COLUMNS,
)
from PHX2.stage18.errors import Stage18Error


class Stage17InputBundle(NamedTuple):
    """Parsed contents of a Stage 17 output directory.

    Each ``*_rows`` field is a tuple of ``dict[str, str]`` rows --
    one dict per CSV data row, keyed by the column tuple Stage 17
    emitted. Cells are kept as raw strings; downstream consumers
    cast to int/float/bool as needed.

    ``input_row_counts`` maps each of the four input CSV filenames
    to its observed data-row count and is intended for direct
    embedding into Stage 18's manifest.
    """

    input_dir: Path
    manifest: dict
    headline_rows: tuple[dict, ...]
    coarse_rows: tuple[dict, ...]
    unevaluable_rows: tuple[dict, ...]
    data_quality_rows: tuple[dict, ...]
    input_row_counts: dict


def load_stage17_input_dir(input_dir: Path) -> Stage17InputBundle:
    """Validate and load every required artifact under ``input_dir``.

    Raises:
        Stage18Error: code ``B01`` when ``input_dir`` is missing /
            not a directory, when a required artifact is missing,
            when a required CSV has no header line, or when a CSV
            header does not match the locked column tuple.
        Stage18Error: code ``B02`` when the manifest's
            ``schema_version`` is missing or not
            ``"stage17_run_manifest_v0"``.
        Stage18Error: code ``B07`` when a CSV data row's cell count
            does not match the expected column count.
        Stage18Error: code ``B08`` when the manifest is not valid
            JSON or its top-level value is not a JSON object.
    """

    if not input_dir.exists() or not input_dir.is_dir():
        raise Stage18Error(
            "B01",
            f"--stage17-input-dir does not exist or is not a directory: "
            f"{input_dir}",
        )

    for name in REQUIRED_INPUT_FILES:
        path = input_dir / name
        if not path.is_file():
            raise Stage18Error(
                "B01", f"missing required Stage 17 artifact: {name}"
            )

    manifest = _load_manifest(input_dir / MANIFEST_FILENAME)

    headline_rows = _load_csv(
        input_dir / HEADLINE_FILENAME, HEADLINE_COLUMNS
    )
    coarse_rows = _load_csv(
        input_dir / COARSE_FILENAME, COARSE_COLUMNS
    )
    unevaluable_rows = _load_csv(
        input_dir / UNEVALUABLE_BREAKDOWN_FILENAME, UNEVALUABLE_COLUMNS
    )
    data_quality_rows = _load_csv(
        input_dir / DATA_QUALITY_FILENAME, DATA_QUALITY_COLUMNS
    )

    return Stage17InputBundle(
        input_dir=input_dir,
        manifest=manifest,
        headline_rows=headline_rows,
        coarse_rows=coarse_rows,
        unevaluable_rows=unevaluable_rows,
        data_quality_rows=data_quality_rows,
        input_row_counts={
            HEADLINE_FILENAME: len(headline_rows),
            COARSE_FILENAME: len(coarse_rows),
            UNEVALUABLE_BREAKDOWN_FILENAME: len(unevaluable_rows),
            DATA_QUALITY_FILENAME: len(data_quality_rows),
        },
    )


def _load_manifest(path: Path) -> dict:
    """Parse the Stage 17 manifest and validate its schema_version.

    A zero-byte / whitespace-only manifest is treated as a B01
    contract violation rather than a B08 JSON error: the file
    exists, but is empty, which is a contract problem, not a
    parse problem.
    """

    raw = path.read_text(encoding="utf-8")
    if not raw.strip():
        raise Stage18Error("B01", f"manifest file is empty: {path.name}")

    try:
        manifest = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise Stage18Error(
            "B08",
            f"{path.name}: {exc.msg} at line {exc.lineno} col {exc.colno}",
        ) from exc

    if not isinstance(manifest, dict):
        raise Stage18Error(
            "B08", f"{path.name}: top-level JSON value is not an object"
        )

    schema_version = manifest.get("schema_version")
    if schema_version != STAGE17_MANIFEST_SCHEMA_VERSION:
        raise Stage18Error(
            "B02",
            f"{path.name}: schema_version is {schema_version!r}; "
            f"expected {STAGE17_MANIFEST_SCHEMA_VERSION!r}",
        )

    return manifest


def _load_csv(
    path: Path, expected_columns: Sequence[str]
) -> tuple[dict, ...]:
    """Load a Stage 17 CSV and return its data rows as ``dict`` records.

    The header row must equal ``expected_columns`` exactly (order
    and string content); each data row must have exactly
    ``len(expected_columns)`` cells.

    Stage 18 does not coerce cell types here: every value in the
    returned dicts is the raw string ``csv.reader`` produced. The
    classifier and metrics layers in later phases convert to int /
    float / bool at point of use, where they can also surface
    type-error context that this generic reader cannot.
    """

    with path.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.reader(fh)
        try:
            header = next(reader)
        except StopIteration:
            raise Stage18Error(
                "B01",
                f"{path.name}: file is empty (no header line)",
            ) from None

        if tuple(header) != tuple(expected_columns):
            raise Stage18Error(
                "B01",
                (
                    f"{path.name}: unexpected header.\n"
                    f"  expected: {list(expected_columns)}\n"
                    f"  actual:   {header}"
                ),
            )

        rows: list[dict] = []
        for line_no, row in enumerate(reader, start=2):
            if len(row) != len(expected_columns):
                raise Stage18Error(
                    "B07",
                    (
                        f"{path.name}:{line_no}: expected "
                        f"{len(expected_columns)} cells, got {len(row)}"
                    ),
                )
            rows.append(dict(zip(expected_columns, row)))

        return tuple(rows)


__all__ = [
    "Stage17InputBundle",
    "load_stage17_input_dir",
]

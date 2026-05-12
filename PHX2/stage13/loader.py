"""Stage 13 loader / validator.

Reads a Stage 12 run-directory snapshot into Python dicts/lists and
validates its schema against the contract Stage 13 was built for.
Uses ONLY the stdlib (csv + json + pathlib + hashlib via hashing.py).
No pandas, no DB driver, no PHX2.analysis runtime imports.

The four cohort CSVs are returned as ``list[dict[str, object]]`` (one
dict per row, with numeric columns parsed to int/float/None). The
column names returned are exactly the Stage 12 column names; the
builder maps them onto Stage 13's locked output schema.

Spec L11 / L12 / L13 are enforced here:
  * L11: every consumed CSV is hashed; the manifest hash is recorded.
  * L12: the Stage 12 manifest's ``schema_version`` field must match
    the locked Stage 13 expectation ("1"). Any other value raises
    ``Stage13IncompatibleStage12``.
  * L13: the ``confidence_flag`` column is normalized so the builder
    can compare against ``CONFIDENCE_FLAG_LOW_SENTINEL`` without
    re-discovering the value domain.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PHX2.stage13.hashing import sha256_file


# ---------------------------------------------------------------------------
# Locked file names (mirrors Stage 12's runtime constants -- the strings
# are duplicated here intentionally so Stage 13 does NOT import
# PHX2.analysis runtime modules).
# ---------------------------------------------------------------------------


MANIFEST_FILENAME = "manifest.json"
COHORT_TIER_BASELINE_FILENAME = "cohort_tier_baseline.csv"
COHORT_FILTER_LABEL_OVERALL_FILENAME = "cohort_filter_label_overall.csv"
COHORT_FILTER_LABEL_BY_TIER_FILENAME = "cohort_filter_label_by_tier.csv"
COHORT_PRIMITIVE_BUCKET_BY_TIER_FILENAME = "cohort_primitive_bucket_by_tier.csv"


REQUIRED_INPUT_FILES: tuple[str, ...] = (
    COHORT_TIER_BASELINE_FILENAME,
    COHORT_FILTER_LABEL_OVERALL_FILENAME,
    COHORT_FILTER_LABEL_BY_TIER_FILENAME,
    COHORT_PRIMITIVE_BUCKET_BY_TIER_FILENAME,
)


EXPECTED_STAGE12_SCHEMA_VERSION = "1"
"""Spec L12 + STEP 0 S0-1: Stage 12's manifest field is ``schema_version``
with literal value "1". Stage 13 fails loudly if it sees anything else."""


# Required columns per Stage 12 cohort file (subset Stage 13 actually
# consumes -- Stage 12 may emit additional columns, those are tolerated).
_REQUIRED_BASELINE_COLUMNS = (
    "tier_index",
    "tier_name",
    "n_complete",
    "n_censored",
    "hit_2x_24h_count",
    "hit_2x_24h_rate",
    "hit_2x_24h_ci_low",
    "hit_2x_24h_ci_high",
    "confidence_flag",
)


_REQUIRED_FILTER_LABEL_OVERALL_COLUMNS = (
    "filter_name",
    "filter_version",
    "threshold_version",
    "filter_label",
    "n_complete",
    "n_censored",
    "hit_2x_24h_count",
    "hit_2x_24h_rate",
    "hit_2x_24h_ci_low",
    "hit_2x_24h_ci_high",
    "confidence_flag",
)


_REQUIRED_FILTER_LABEL_BY_TIER_COLUMNS = (
    "tier_index",
    "tier_name",
    "filter_name",
    "filter_version",
    "threshold_version",
    "filter_label",
    "n_complete",
    "n_censored",
    "hit_2x_24h_count",
    "hit_2x_24h_rate",
    "hit_2x_24h_ci_low",
    "hit_2x_24h_ci_high",
    "confidence_flag",
)


_REQUIRED_PRIMITIVE_BUCKET_COLUMNS = (
    "tier_index",
    "tier_name",
    "primitive_name",
    "bucket_label",
    "n_complete",
    "n_censored",
    "hit_2x_24h_count",
    "hit_2x_24h_rate",
    "hit_2x_24h_ci_low",
    "hit_2x_24h_ci_high",
    "confidence_flag",
)


# Optional decision-volume columns that, if present in any per-cohort
# CSV, allow Stage 13 to compute policy_severity. Detection happens at
# load time; spec §POLICY SEVERITY says no Stage 12 DB re-query.
SEVERITY_COLUMN_CANDIDATES: tuple[str, ...] = (
    "n_decisions_total",
    "decision_share",
)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class Stage13ValidationError(ValueError):
    """Base class for all Stage 13 loader validation failures."""


class Stage13IncompatibleStage12(Stage13ValidationError):
    """Stage 12 manifest is present but its schema_version does not
    match the value Stage 13 was built against. Spec L12."""


class Stage13MissingInput(Stage13ValidationError):
    """One of the required Stage 12 run-directory files is missing."""


class Stage13MissingColumn(Stage13ValidationError):
    """A required column is absent from a Stage 12 cohort CSV."""


# ---------------------------------------------------------------------------
# Public dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Stage12Manifest:
    """Parsed Stage 12 manifest -- the subset Stage 13 actually reads."""

    raw: dict[str, Any]
    schema_version: str
    stage: str
    stage_version: str
    run_id: str
    created_at: str
    data_window_start: str | None
    data_window_end: str | None
    manifest_hash: str


@dataclass(frozen=True)
class CSVBundle:
    """Loaded Stage 12 cohort CSVs.

    Rows are ``list[dict[str, object]]`` where numeric columns are
    parsed to ``int | float | None``. String columns retain their
    Stage 12 spelling.
    """

    tier_baseline: list[dict[str, Any]]
    filter_label_overall: list[dict[str, Any]]
    filter_label_by_tier: list[dict[str, Any]]
    primitive_bucket_by_tier: list[dict[str, Any]]
    input_hashes: dict[str, str]
    severity_column: str | None


# ---------------------------------------------------------------------------
# Manifest load + validation
# ---------------------------------------------------------------------------


def load_stage12_manifest(run_path: Path) -> Stage12Manifest:
    """Read manifest.json from ``run_path`` and parse the L12-relevant
    fields. Raises ``Stage13MissingInput`` if the file is missing and
    ``Stage13IncompatibleStage12`` on schema-version mismatch.
    """

    manifest_path = Path(run_path) / MANIFEST_FILENAME
    if not manifest_path.exists():
        raise Stage13MissingInput(
            f"Stage 12 manifest not found at {manifest_path}"
        )

    with open(manifest_path, "r", encoding="utf-8") as handle:
        raw = json.load(handle)

    validate_stage12_schema_version(raw)

    parameters = raw.get("parameters", {}) or {}
    # STEP 0 S0-2: Stage 12 stores the data window under parameters,
    # not at the top level. Either bound may be None.
    data_window_start = parameters.get("decision_time_range_start")
    data_window_end = parameters.get("decision_time_range_end")

    return Stage12Manifest(
        raw=raw,
        schema_version=str(raw.get("schema_version")),
        stage=str(raw.get("stage", "")),
        stage_version=str(raw.get("stage_version", "")),
        run_id=str(raw.get("run_id", "")),
        created_at=str(raw.get("created_at", "")),
        data_window_start=str(data_window_start) if data_window_start else None,
        data_window_end=str(data_window_end) if data_window_end else None,
        manifest_hash=sha256_file(manifest_path),
    )


def validate_stage12_schema_version(raw: dict[str, Any]) -> None:
    """Spec L12: Stage 12's manifest must declare the schema_version
    Stage 13 was built for. Anything else fails loudly.

    The actual field name on Stage 12 manifests is literally
    ``schema_version`` (STEP 0 S0-1). If a future Stage 12 introduces a
    differently named field, Stage 13's expectation must be updated
    here in lock-step.
    """

    actual = raw.get("schema_version")
    if actual is None:
        raise Stage13IncompatibleStage12(
            "Stage 12 manifest missing required 'schema_version' field"
        )
    if str(actual) != EXPECTED_STAGE12_SCHEMA_VERSION:
        raise Stage13IncompatibleStage12(
            f"Stage 12 schema_version mismatch: expected "
            f"{EXPECTED_STAGE12_SCHEMA_VERSION!r}, got {actual!r}"
        )


# ---------------------------------------------------------------------------
# CSV load + per-column validation
# ---------------------------------------------------------------------------


def _coerce_value(raw: str, column: str) -> Any:
    """Parse a raw CSV cell string into int / float / None / str.

    Stage 12 writes ``""`` for NULLs (na_rep=""). Numeric column names
    are detected by suffix (``_rate``, ``_ci_low``, ``_ci_high``,
    ``_count``, ``n_*``); other columns are returned as strings.
    """

    if raw == "":
        return None

    if column in (
        "tier_index",
        "bucket_index",
        "bucket_order",
    ):
        try:
            return int(raw)
        except ValueError:
            try:
                return int(float(raw))
            except ValueError:
                return raw

    if column.startswith("n_") or column.endswith("_count"):
        try:
            return int(raw)
        except ValueError:
            try:
                return int(float(raw))
            except ValueError:
                return raw

    if (
        column.endswith("_rate")
        or column.endswith("_ci_low")
        or column.endswith("_ci_high")
        or column.endswith("_low")
        or column.endswith("_high")
        or column in ("median_max_return_24h", "median_max_drawdown_24h")
    ):
        try:
            return float(raw)
        except ValueError:
            return None

    if column == "decision_share":
        try:
            return float(raw)
        except ValueError:
            return None

    if column == "n_decisions_total":
        try:
            return int(raw)
        except ValueError:
            try:
                return int(float(raw))
            except ValueError:
                return None

    return raw


def _read_csv_rows(
    csv_path: Path, required_columns: tuple[str, ...]
) -> list[dict[str, Any]]:
    """Read a CSV file, validate required columns, and parse cell values."""

    if not csv_path.exists():
        raise Stage13MissingInput(
            f"Stage 12 cohort CSV not found at {csv_path}"
        )

    with open(csv_path, "r", encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle)
        try:
            header = next(reader)
        except StopIteration:
            raise Stage13ValidationError(
                f"Empty CSV (no header row) at {csv_path}"
            ) from None

        missing = [col for col in required_columns if col not in header]
        if missing:
            raise Stage13MissingColumn(
                f"CSV {csv_path.name} is missing required columns "
                f"{missing!r}; available columns: {header!r}"
            )

        rows: list[dict[str, Any]] = []
        for raw_row in reader:
            if not raw_row:
                continue
            row: dict[str, Any] = {}
            for col, cell in zip(header, raw_row):
                row[col] = _coerce_value(cell, col)
            rows.append(row)
        return rows


def load_stage12_csvs(run_path: Path) -> CSVBundle:
    """Read the four cohort CSVs, hash them, detect the severity column.

    The bundle's ``input_hashes`` dict keys match the Stage 12 file
    names verbatim (e.g. ``cohort_tier_baseline.csv``) so the manifest
    can record them under ``stage12_input_hashes`` without renaming.
    """

    run_path = Path(run_path)

    tier_baseline = _read_csv_rows(
        run_path / COHORT_TIER_BASELINE_FILENAME,
        _REQUIRED_BASELINE_COLUMNS,
    )
    filter_label_overall = _read_csv_rows(
        run_path / COHORT_FILTER_LABEL_OVERALL_FILENAME,
        _REQUIRED_FILTER_LABEL_OVERALL_COLUMNS,
    )
    filter_label_by_tier = _read_csv_rows(
        run_path / COHORT_FILTER_LABEL_BY_TIER_FILENAME,
        _REQUIRED_FILTER_LABEL_BY_TIER_COLUMNS,
    )
    primitive_bucket_by_tier = _read_csv_rows(
        run_path / COHORT_PRIMITIVE_BUCKET_BY_TIER_FILENAME,
        _REQUIRED_PRIMITIVE_BUCKET_COLUMNS,
    )

    input_hashes = hash_stage12_inputs(run_path)

    severity_column = detect_severity_column(
        [
            tier_baseline,
            filter_label_overall,
            filter_label_by_tier,
            primitive_bucket_by_tier,
        ]
    )

    return CSVBundle(
        tier_baseline=tier_baseline,
        filter_label_overall=filter_label_overall,
        filter_label_by_tier=filter_label_by_tier,
        primitive_bucket_by_tier=primitive_bucket_by_tier,
        input_hashes=input_hashes,
        severity_column=severity_column,
    )


def hash_stage12_inputs(run_path: Path) -> dict[str, str]:
    """Compute SHA-256 of every required Stage 12 CSV.

    Returned mapping uses the Stage 12 file names as keys, identical to
    the manifest schema's ``stage12_input_hashes`` section.
    """

    out: dict[str, str] = {}
    for filename in REQUIRED_INPUT_FILES:
        path = Path(run_path) / filename
        if not path.exists():
            raise Stage13MissingInput(
                f"Stage 12 cohort CSV not found at {path}"
            )
        out[filename] = sha256_file(path)
    return out


def detect_severity_column(
    bundles: list[list[dict[str, Any]]],
) -> str | None:
    """Return the name of the decision-volume column if present, else None.

    Stage 13 looks for any of ``SEVERITY_COLUMN_CANDIDATES``; the first
    one observed (in any row of any bundle) wins. Per spec §POLICY
    SEVERITY, when the column is absent, ``severity_available = false``
    and every recommendation row gets ``policy_severity = "unknown"``.
    """

    for bundle in bundles:
        for row in bundle:
            for candidate in SEVERITY_COLUMN_CANDIDATES:
                if candidate in row:
                    return candidate
    return None

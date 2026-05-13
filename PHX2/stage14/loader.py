"""Stage 14 loader / validator.

Reads two run directories into memory:

  * Stage 13 run directory: candidate_recommendations.csv + manifest.json.
    The manifest must declare ``safe_for_live_policy_consumption=false``
    (Stage 13's hardcoded invariant) and a non-empty ``stage12_run_path``.
  * Stage 12 run directory: decision_filter_outcome_long.csv +
    manifest.json. The manifest's ``schema_version`` must be ``"1"`` and
    its sha256 must match the value Stage 13 recorded when it was built
    (this is how a stage12-path override is sanity-checked).

The loader uses ONLY the stdlib (csv + json + pathlib + the local
hashing module). No pandas, no DB driver, no PHX2.analysis or
PHX2.stage13 runtime imports. Stage 13's CSV column list is duplicated
here on purpose so Stage 14 stays import-isolated from Stage 13's
runtime modules.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from PHX2.stage14.hashing import sha256_file
from PHX2.stage14.types import LongCsvRow


# ---------------------------------------------------------------------------
# Locked file names + schema expectations
# ---------------------------------------------------------------------------


STAGE13_MANIFEST_FILENAME = "manifest.json"
STAGE13_CANDIDATE_CSV_FILENAME = "candidate_recommendations.csv"
STAGE12_MANIFEST_FILENAME = "manifest.json"
STAGE12_LONG_CSV_FILENAME = "decision_filter_outcome_long.csv"


EXPECTED_STAGE12_SCHEMA_VERSION = "1"
"""Mirrors Stage 13's ``EXPECTED_STAGE12_SCHEMA_VERSION``. If Stage 12
ever bumps its manifest schema_version, both Stage 13 and Stage 14
must be updated in lock-step."""


EXPECTED_STAGE13_SCHEMA_VERSION = "1.1"
"""Stage 14 requires Stage 13 schema_version exactly ``"1.1"``. The
1.1 patch is what added the explicit filter-identity columns
(filter_name, filter_version, filter_label, threshold_version) on
candidate_recommendations.csv that Stage 14's tuple-match step
depends on. Older 1.0 runs are rejected loudly rather than silently
producing an empty rule set, and any future 1.2+ bump must be
audited against Stage 14 and the constant updated here in
lock-step."""


# Stage 13's candidate_recommendations.csv column list (locked in
# PHX2.stage13.writer.CSV_COLUMNS). Duplicated here so Stage 14 does
# not import a Stage 13 runtime module.
STAGE13_CANDIDATE_CSV_COLUMNS: tuple[str, ...] = (
    "policy_surface",
    "cohort_id",
    "filter_name",
    "filter_version",
    "filter_label",
    "threshold_version",
    "tier_scope",
    "action_class",
    "direction",
    "evidence_class",
    "policy_severity",
    "review_priority",
    "n_complete",
    "n_censored",
    "cohort_rate",
    "baseline_rate",
    "lift_absolute",
    "lift_relative",
    "wilson_ci_low",
    "wilson_ci_high",
    "ci_excludes_baseline",
    "censoring_rate",
    "censoring_warning_flag",
    "watchlist_flag",
    "tier_evidence_support",
    "cross_tier_disagreement",
    "loosen_capped_flag",
    "confidence_ceiling_applied",
    "notes",
)


# Stage 12 long-CSV columns Stage 14 actually consumes. Stage 12 emits
# many additional outcome / score columns; those are tolerated and
# ignored. Missing required columns trigger a hard fail.
_REQUIRED_LONG_CSV_COLUMNS: tuple[str, ...] = (
    "alert_decision_id",
    "tier_name",
    "decision_type",
    "filter_name",
    "filter_version",
    "filter_label",
    "threshold_version",
    "has_primary_outcome",
    "primary_outcome_hit_2x_24h",
)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class Stage14ValidationError(ValueError):
    """Base class for all Stage 14 loader validation failures."""


class Stage14MissingInput(Stage14ValidationError):
    """A required Stage 12 or Stage 13 input file is missing."""


class Stage14MissingColumn(Stage14ValidationError):
    """A required column is absent from a Stage 12 / Stage 13 CSV."""


class Stage14IncompatibleStage13(Stage14ValidationError):
    """Stage 13 manifest is present but its invariants do not match
    Stage 14's expectations (schema_version mismatch, or
    safe_for_live_policy_consumption not literal false)."""


class Stage14IncompatibleStage12(Stage14ValidationError):
    """Stage 12 manifest is incompatible (schema_version mismatch, or
    its manifest hash does not match the override sanity check)."""


# ---------------------------------------------------------------------------
# Public dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Stage13Run:
    """The Stage 13 inputs Stage 14 consumes.

    ``candidate_rows`` preserves each Stage 13 row as a raw
    ``dict[str, str]`` because the excluded_recommendations CSV
    needs to round-trip the original cell strings. The translator
    (``rules.translate_recommendations``) is the only consumer that
    coerces specific columns to typed values.
    """

    manifest_path: Path
    manifest: dict[str, Any]
    manifest_hash: str
    candidate_csv_path: Path
    candidate_csv_hash: str
    candidate_rows: tuple[dict[str, str], ...]


@dataclass(frozen=True)
class Stage12Run:
    """The Stage 12 inputs Stage 14 consumes."""

    manifest_path: Path
    manifest: dict[str, Any]
    manifest_hash: str
    long_csv_path: Path
    long_csv_hash: str
    long_rows: tuple[LongCsvRow, ...]


# ---------------------------------------------------------------------------
# Stage 13 loader
# ---------------------------------------------------------------------------


def load_stage13_run(run_path: Path) -> Stage13Run:
    """Load the Stage 13 run directory and validate its invariants.

    Enforces:
      * manifest.json exists and parses as JSON.
      * Stage 13 ``schema_version`` is in the 1.x series.
      * ``safe_for_live_policy_consumption`` is present and is the
        literal Python ``False`` (i.e., the JSON value ``false`` --
        not the string ``"false"``, not ``None``, not missing).
      * candidate_recommendations.csv exists with the locked column
        header.

    Returns a ``Stage13Run`` carrying the parsed manifest, the hash of
    each input file, and the raw rows of the candidate CSV.
    """

    run_path = Path(run_path)
    manifest_path = run_path / STAGE13_MANIFEST_FILENAME
    candidate_path = run_path / STAGE13_CANDIDATE_CSV_FILENAME

    if not manifest_path.exists():
        raise Stage14MissingInput(
            f"Stage 13 manifest not found at {manifest_path}"
        )
    if not candidate_path.exists():
        raise Stage14MissingInput(
            f"Stage 13 candidate CSV not found at {candidate_path}"
        )

    with open(manifest_path, "r", encoding="utf-8") as handle:
        manifest_raw = json.load(handle)

    _validate_stage13_manifest(manifest_raw, manifest_path)

    rows = _read_csv_raw_rows(candidate_path, STAGE13_CANDIDATE_CSV_COLUMNS)

    return Stage13Run(
        manifest_path=manifest_path,
        manifest=manifest_raw,
        manifest_hash=sha256_file(manifest_path),
        candidate_csv_path=candidate_path,
        candidate_csv_hash=sha256_file(candidate_path),
        candidate_rows=tuple(rows),
    )


def _validate_stage13_manifest(raw: dict[str, Any], manifest_path: Path) -> None:
    schema_version = raw.get("stage13_schema_version")
    if schema_version != EXPECTED_STAGE13_SCHEMA_VERSION:
        raise Stage14IncompatibleStage13(
            f"Stage 13 schema_version mismatch at {manifest_path}: expected "
            f"exactly {EXPECTED_STAGE13_SCHEMA_VERSION!r}, got "
            f"{schema_version!r}"
        )

    if "safe_for_live_policy_consumption" not in raw:
        raise Stage14IncompatibleStage13(
            "Stage 13 manifest missing required "
            "'safe_for_live_policy_consumption' field; Stage 14 refuses to "
            "proceed without this invariant."
        )
    flag = raw["safe_for_live_policy_consumption"]
    if flag is not False:
        # Reject True, None, "false", 0, anything else. Stage 13's L11
        # contract is that this is hardcoded to the Python False; if it
        # ever flips, Stage 14 must be re-audited from scratch.
        raise Stage14IncompatibleStage13(
            f"Stage 13 manifest field 'safe_for_live_policy_consumption' "
            f"is {flag!r}; Stage 14 requires it to be literal false."
        )


# ---------------------------------------------------------------------------
# Stage 12 loader
# ---------------------------------------------------------------------------


def load_stage12_run(
    run_path: Path,
    *,
    expected_manifest_hash: str,
) -> Stage12Run:
    """Load the Stage 12 run directory and validate its invariants.

    Enforces:
      * manifest.json exists and parses as JSON.
      * ``schema_version`` equals ``"1"``.
      * ``expected_manifest_hash`` matches the actual sha256 of the
        Stage 12 manifest on disk. This argument is REQUIRED -- there
        is no opt-out. The CLI/pipeline path sources the expected
        hash from Stage 13's recorded ``stage12_manifest_hash`` via
        ``resolve_stage12_run_path``; direct callers (tests, ad-hoc
        scripts) must compute the hash themselves and pass it in. A
        mismatch means the run directory's manifest has been
        rewritten / replaced / swapped since the expected hash was
        captured, which would invalidate every replay metric.
      * decision_filter_outcome_long.csv exists with the documented
        required columns.

    The long CSV is read in one pass into a tuple of ``LongCsvRow``.
    Empty CSV (header only) is allowed; tests cover the no-decisions
    edge case.
    """

    run_path = Path(run_path)
    manifest_path = run_path / STAGE12_MANIFEST_FILENAME
    long_csv_path = run_path / STAGE12_LONG_CSV_FILENAME

    if not manifest_path.exists():
        raise Stage14MissingInput(
            f"Stage 12 manifest not found at {manifest_path}"
        )
    if not long_csv_path.exists():
        raise Stage14MissingInput(
            f"Stage 12 long CSV not found at {long_csv_path}"
        )

    with open(manifest_path, "r", encoding="utf-8") as handle:
        manifest_raw = json.load(handle)

    _validate_stage12_manifest(manifest_raw, manifest_path)

    manifest_hash = sha256_file(manifest_path)
    if manifest_hash != expected_manifest_hash:
        raise Stage14IncompatibleStage12(
            f"Stage 12 manifest hash mismatch at {manifest_path}: "
            f"expected {expected_manifest_hash!r}, got "
            f"{manifest_hash!r}. Refusing to replay against a "
            "Stage 12 manifest that differs from the one whose hash "
            "was supplied as the integrity anchor."
        )

    long_rows = _read_long_csv(long_csv_path)

    return Stage12Run(
        manifest_path=manifest_path,
        manifest=manifest_raw,
        manifest_hash=manifest_hash,
        long_csv_path=long_csv_path,
        long_csv_hash=sha256_file(long_csv_path),
        long_rows=long_rows,
    )


def _validate_stage12_manifest(raw: dict[str, Any], manifest_path: Path) -> None:
    actual = raw.get("schema_version")
    if actual is None:
        raise Stage14IncompatibleStage12(
            f"Stage 12 manifest at {manifest_path} missing required "
            "'schema_version' field."
        )
    if str(actual) != EXPECTED_STAGE12_SCHEMA_VERSION:
        raise Stage14IncompatibleStage12(
            f"Stage 12 schema_version mismatch at {manifest_path}: "
            f"expected {EXPECTED_STAGE12_SCHEMA_VERSION!r}, got {actual!r}."
        )


# ---------------------------------------------------------------------------
# Stage 12 path resolution
# ---------------------------------------------------------------------------


def resolve_stage12_run_path(
    *,
    stage13_manifest: dict[str, Any],
    override: Path | None,
) -> tuple[Path, str]:
    """Decide which Stage 12 run path to load.

    Returns ``(path, expected_hash)``. The hash is REQUIRED in both
    branches -- Stage 14 always re-verifies the Stage 12 manifest
    hash against the value Stage 13 recorded, regardless of whether
    the path was supplied via override or pulled from Stage 13's
    manifest.

    Branches:
      * No override + Stage 13 manifest carries ``stage12_run_path``
        + ``stage12_manifest_hash``: use Stage 13's recorded values.
        The hash is checked downstream against the actual Stage 12
        manifest bytes on disk so a Stage 12 directory whose
        manifest has been touched, swapped, or rewritten since Stage
        13 ran is rejected loudly.
      * Override provided: use the override path; the same recorded
        hash from Stage 13 is the expected value.
      * Missing ``stage12_run_path`` or ``stage12_manifest_hash`` on
        the Stage 13 manifest: hard fail. Stage 14 will not replay
        without an integrity anchor for its Stage 12 input.
    """

    recorded = stage13_manifest.get("stage12_run_path")
    recorded_hash = stage13_manifest.get("stage12_manifest_hash")

    if not isinstance(recorded_hash, str) or recorded_hash == "":
        raise Stage14IncompatibleStage13(
            "Stage 13 manifest missing 'stage12_manifest_hash'; "
            "Stage 14 refuses to proceed without an integrity anchor "
            "to verify the Stage 12 manifest against."
        )

    if override is not None:
        return Path(override), recorded_hash

    if not isinstance(recorded, str) or recorded == "":
        raise Stage14IncompatibleStage13(
            "Stage 13 manifest missing 'stage12_run_path' and no "
            "--stage12-run override was supplied. Stage 14 cannot "
            "locate the Stage 12 long CSV."
        )
    return Path(recorded), recorded_hash


# ---------------------------------------------------------------------------
# CSV reading helpers
# ---------------------------------------------------------------------------


def _read_csv_raw_rows(
    csv_path: Path, required_columns: Iterable[str]
) -> list[dict[str, str]]:
    """Read a CSV preserving every cell as a string.

    Returns rows as ``dict[str, str]`` so the writer can round-trip the
    original bytes verbatim into excluded_recommendations.csv. Header
    must contain every column in ``required_columns``; extra columns
    are tolerated and preserved.
    """

    required = list(required_columns)
    with open(csv_path, "r", encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle)
        try:
            header = next(reader)
        except StopIteration:
            raise Stage14ValidationError(
                f"Empty CSV (no header row) at {csv_path}"
            ) from None

        missing = [col for col in required if col not in header]
        if missing:
            raise Stage14MissingColumn(
                f"CSV {csv_path.name} is missing required columns "
                f"{missing!r}; available columns: {header!r}"
            )

        rows: list[dict[str, str]] = []
        for raw_row in reader:
            if not raw_row:
                continue
            # Pad short rows with "" so dict lookup is well-defined.
            cells = list(raw_row) + [""] * max(0, len(header) - len(raw_row))
            row = {col: cells[i] for i, col in enumerate(header)}
            rows.append(row)
        return rows


def _read_long_csv(csv_path: Path) -> tuple[LongCsvRow, ...]:
    """Read decision_filter_outcome_long.csv into typed ``LongCsvRow``.

    Numeric/boolean coercion is gentle: empty cells become ``None``;
    unparseable cells become ``None`` rather than raising. Stage 12's
    long CSV is large in production; we still read it eagerly because
    Stage 14 needs at least two passes (rule matching + per-decision
    aggregation), and the working set is bounded by the input row
    count -- typical runs have tens of thousands of rows, which fits
    comfortably in memory.
    """

    with open(csv_path, "r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        header = reader.fieldnames or []
        missing = [c for c in _REQUIRED_LONG_CSV_COLUMNS if c not in header]
        if missing:
            raise Stage14MissingColumn(
                f"Stage 12 long CSV {csv_path.name} is missing required "
                f"columns {missing!r}; available columns: {header!r}"
            )

        out: list[LongCsvRow] = []
        for raw in reader:
            out.append(_coerce_long_row(raw))
        return tuple(out)


def _coerce_long_row(raw: dict[str, str]) -> LongCsvRow:
    return LongCsvRow(
        alert_decision_id=raw.get("alert_decision_id", "") or "",
        token_address=_optional_string(raw.get("token_address")),
        tier_index=_optional_int(raw.get("tier_index")),
        tier_name=_optional_string(raw.get("tier_name")),
        decision_type=_optional_string(raw.get("decision_type")),
        filter_name=_optional_string(raw.get("filter_name")),
        filter_version=_optional_string(raw.get("filter_version")),
        filter_label=_optional_string(raw.get("filter_label")),
        threshold_version=_optional_string(raw.get("threshold_version")),
        has_primary_outcome=_optional_bool(raw.get("has_primary_outcome")),
        primary_outcome_hit_2x_24h=_optional_bool(
            raw.get("primary_outcome_hit_2x_24h")
        ),
        primary_outcome_hit_3x_24h=_optional_bool(
            raw.get("primary_outcome_hit_3x_24h")
        ),
        primary_outcome_hit_5x_24h=_optional_bool(
            raw.get("primary_outcome_hit_5x_24h")
        ),
    )


def _optional_string(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.strip()
    return text if text != "" else None


def _optional_int(value: str | None) -> int | None:
    text = _optional_string(value)
    if text is None:
        return None
    try:
        return int(text)
    except ValueError:
        try:
            return int(float(text))
        except ValueError:
            return None


def _optional_bool(value: str | None) -> bool | None:
    """Parse a Stage 12 nullable boolean cell.

    Stage 12 writes nullable booleans via pandas' ``boolean`` dtype:
    True -> "True", False -> "False", NA -> "". We accept both that
    spelling and the JSON/CSV lowercase ``"true"``/``"false"`` Stage
    13 / Stage 14 themselves emit so a Stage 14 run that consumes its
    own intermediate output (e.g. for cross-validation tests) does not
    require a separate parser.
    """

    text = _optional_string(value)
    if text is None:
        return None
    lowered = text.lower()
    if lowered in ("true", "1"):
        return True
    if lowered in ("false", "0"):
        return False
    return None

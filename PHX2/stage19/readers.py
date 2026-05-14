"""Stage 19 readers: Stage 18 manifest, Stage 18 review_matrix,
operator-input CSV, and prior Stage 19 ledger.

Cross-stage column-name renames carried by these readers:

  * Stage 18 manifest key ``"run_id"`` (flat, in
    ``manifest.json``) maps to Stage 19's outputs as the
    namespaced column ``"stage18_run_id"`` to disambiguate from
    Stage 19's own ``"stage19_run_id"`` (Stage 19's per-run id
    recorded in its own ledger and manifest).

  * Stage 18 ``review_matrix.csv`` source column
    ``"classification"`` maps to Stage 19's normalized field /
    ledger column ``"stage18_classification"``. The rename
    disambiguates from any future Stage 19-introduced
    classification field and makes the ledger self-describing
    about which stage produced the value.

  * Stage 18 ``"stage17_label_preserved"`` passes through
    verbatim into the normalized review-matrix record and into
    the Stage 19 ledger.

Stage 18 packets are read as plain files. Nothing in this module
imports ``PHX2.stage17`` or ``PHX2.stage18``; the Stage 18
classification value set is hardcoded locally
(``_STAGE18_CLASSIFICATIONS``) to satisfy the Phase 19 boundary
policy.

E-code coverage:
  * read_stage18_manifest        : E01, E02, E04, E05
  * read_stage18_review_matrix   : E01, E03, E20, E21
  * read_operator_input          : E06, E07, E08, E09, E13
  * read_prior_ledger            : E16, E17, E18

All CSV reads use ``newline=""`` so the embedded csv module
handles line endings correctly.
"""

from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Mapping, NamedTuple

from PHX2.stage19.constants import (
    LABELS,
    LEDGER_COLUMNS,
    MAX_REVIEW_NOTES_LENGTH,
    OPERATOR_INPUT_COLUMNS,
    STAGE18_EXPECTED_MANIFEST_SCHEMA_VERSION,
    STAGE18_REVIEW_MATRIX_EXPECTED_COLUMNS,
)
from PHX2.stage19.errors import Stage19ValidationError
from PHX2.stage19.ledger import LedgerRow


# ---------------------------------------------------------------------------
# Locked constants (hardcoded -- no PHX2.stage18 import)
# ---------------------------------------------------------------------------


# Stage 18's six review classification values, hand-duplicated here.
# Drift in Stage 18's classifier produces an E21 row error rather than
# silently mirroring an unknown value.
_STAGE18_CLASSIFICATIONS: frozenset[str] = frozenset({
    "PROMISING_REVIEW",
    "WEAK_REVIEW",
    "HARMFUL_REVIEW",
    "MIXED_BY_TIER_REVIEW",
    "INSUFFICIENT_SAMPLE_REVIEW",
    "DATA_BLOCKED_REVIEW",
})


# Stage 18 manifest filename (within the Stage 18 input directory)
_STAGE18_MANIFEST_FILENAME: str = "manifest.json"

# Stage 18 review_matrix filename (within the Stage 18 input directory)
_STAGE18_REVIEW_MATRIX_FILENAME: str = "review_matrix.csv"


# Stage 19 prior-ledger artifact filenames (within --prior-ledger-dir)
_PRIOR_LEDGER_CSV_FILENAME: str = "operator_review_ledger.csv"
_PRIOR_LEDGER_MANIFEST_FILENAME: str = "manifest.json"


# Stage 19's expected prior-ledger schema version (locked)
_PRIOR_LEDGER_SCHEMA_VERSION: str = "stage19_ledger_v1"


# Run-timestamp format for prior ledger row validation (matches the
# CLI --run-timestamp form validated in PHX2.stage19.validators).
_RUN_TIMESTAMP_FORMAT: str = "%Y-%m-%dT%H:%M:%SZ"


# ---------------------------------------------------------------------------
# Typed records returned by the readers
# ---------------------------------------------------------------------------


class Stage18ManifestData(NamedTuple):
    """Normalized projection of the Stage 18 manifest. Stage 19
    consumes only these two fields; other manifest keys are
    ignored at this layer."""

    schema_version: str
    run_id: str


class ReviewMatrixRecord(NamedTuple):
    """Normalized v0 projection of one Stage 18 review_matrix row.

    Stage 18's source column ``classification`` is renamed to
    ``stage18_classification`` here (namespaced rename --
    documented at module level)."""

    policy_hash: str
    rule_id: str
    window_seconds: int
    stage18_classification: str
    stage17_label_preserved: str


# Type alias for the in-memory index returned by
# read_stage18_review_matrix. Mapping from
# (policy_hash, rule_id, window_seconds_int) to ReviewMatrixRecord.
ReviewMatrixIndex = Mapping[tuple[str, str, int], ReviewMatrixRecord]


class OperatorInputRow(NamedTuple):
    """One typed row of the operator-input CSV.

    ID-like fields (stage18_run_id, policy_hash, rule_id) have
    been stripped of leading/trailing whitespace.
    window_seconds has been parsed as a positive int.
    review_notes is preserved verbatim (no stripping)."""

    stage18_run_id: str
    policy_hash: str
    rule_id: str
    window_seconds: int
    review_label: str
    review_notes: str


# ---------------------------------------------------------------------------
# Public reader: read_stage18_manifest
# ---------------------------------------------------------------------------


def read_stage18_manifest(stage18_dir: Path) -> Stage18ManifestData:
    """Read and validate the Stage 18 manifest at
    ``stage18_dir/manifest.json``.

    Returns a Stage18ManifestData with the manifest's
    ``schema_version`` and flat ``run_id`` fields. Other manifest
    keys are accepted but not surfaced.

    Raises Stage19ValidationError with:
      * E01 if ``stage18_dir`` is not an existing directory.
      * E02 if ``manifest.json`` is absent inside ``stage18_dir``.
      * E04 if ``manifest.json`` is malformed JSON, is not a JSON
        object, or is missing the required ``schema_version`` /
        ``run_id`` keys (or those keys are not strings).
      * E05 if ``manifest["schema_version"]`` does not equal
        STAGE18_EXPECTED_MANIFEST_SCHEMA_VERSION.

    Treats ``stage18_dir`` as read-only.
    """

    if not stage18_dir.is_dir():
        raise Stage19ValidationError("E01", detail=f"stage18_dir={stage18_dir!s}")

    manifest_path = stage18_dir / _STAGE18_MANIFEST_FILENAME
    if not manifest_path.is_file():
        raise Stage19ValidationError("E02", detail=str(manifest_path))

    raw = manifest_path.read_text(encoding="utf-8")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise Stage19ValidationError(
            "E04", detail=f"manifest.json decode: {exc}"
        ) from exc

    if not isinstance(data, dict):
        raise Stage19ValidationError(
            "E04", detail="manifest.json is not a JSON object"
        )

    if "schema_version" not in data:
        raise Stage19ValidationError(
            "E04", detail="manifest.json missing required key: schema_version"
        )
    if "run_id" not in data:
        raise Stage19ValidationError(
            "E04", detail="manifest.json missing required key: run_id"
        )

    schema_version = data["schema_version"]
    run_id = data["run_id"]

    if not isinstance(schema_version, str):
        raise Stage19ValidationError(
            "E04", detail="manifest.json schema_version is not a string"
        )
    if not isinstance(run_id, str):
        raise Stage19ValidationError(
            "E04", detail="manifest.json run_id is not a string"
        )

    if schema_version != STAGE18_EXPECTED_MANIFEST_SCHEMA_VERSION:
        raise Stage19ValidationError(
            "E05",
            detail=(
                f"got {schema_version!r}, "
                f"expected {STAGE18_EXPECTED_MANIFEST_SCHEMA_VERSION!r}"
            ),
        )

    return Stage18ManifestData(schema_version=schema_version, run_id=run_id)


# ---------------------------------------------------------------------------
# Public reader: read_stage18_review_matrix
# ---------------------------------------------------------------------------


def read_stage18_review_matrix(
    stage18_dir: Path,
) -> dict[tuple[str, str, int], ReviewMatrixRecord]:
    """Read and validate the Stage 18 review_matrix at
    ``stage18_dir/review_matrix.csv``.

    Returns a dict indexed by ``(policy_hash, rule_id,
    window_seconds)`` where ``window_seconds`` is the parsed int.
    Each value is a normalized ReviewMatrixRecord exposing the
    slice key plus ``stage18_classification`` (renamed from
    Stage 18's ``classification``) and ``stage17_label_preserved``
    (verbatim passthrough).

    Duplicate-row behavior: if two rows share the same
    ``(policy_hash, rule_id, window_seconds)`` tuple, the LATER
    row in source order wins (last-write-wins). Phase 19.2 does
    not introduce a duplicate-row E-code; a future phase may
    revisit if duplicates become a real concern.

    Raises Stage19ValidationError with:
      * E01 if ``stage18_dir`` is not an existing directory.
      * E03 if ``review_matrix.csv`` is absent inside
        ``stage18_dir``.
      * E20 if the CSV header does not exactly match
        STAGE18_REVIEW_MATRIX_EXPECTED_COLUMNS (column names,
        order, and count).
      * E21 if any row has wrong column count, unparseable or
        non-positive ``window_seconds``, or invalid Stage 18
        ``classification`` value.

    Treats ``stage18_dir`` as read-only.
    """

    if not stage18_dir.is_dir():
        raise Stage19ValidationError("E01", detail=f"stage18_dir={stage18_dir!s}")

    csv_path = stage18_dir / _STAGE18_REVIEW_MATRIX_FILENAME
    if not csv_path.is_file():
        raise Stage19ValidationError("E03", detail=str(csv_path))

    expected_cols = STAGE18_REVIEW_MATRIX_EXPECTED_COLUMNS
    expected_width = len(expected_cols)

    idx_policy_hash = expected_cols.index("policy_hash")
    idx_rule_id = expected_cols.index("rule_id")
    idx_window_seconds = expected_cols.index("window_seconds")
    idx_classification = expected_cols.index("classification")
    idx_stage17_label = expected_cols.index("stage17_label_preserved")

    index: dict[tuple[str, str, int], ReviewMatrixRecord] = {}

    with csv_path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.reader(f)
        try:
            header = next(reader)
        except StopIteration:
            raise Stage19ValidationError(
                "E20", detail="review_matrix.csv is empty (no header)"
            ) from None

        if tuple(header) != expected_cols:
            raise Stage19ValidationError(
                "E20",
                detail=(
                    f"header mismatch: got {header!r}, "
                    f"expected {list(expected_cols)!r}"
                ),
            )

        for row_idx, row in enumerate(reader, start=1):
            if len(row) != expected_width:
                raise Stage19ValidationError(
                    "E21",
                    detail=(
                        f"row {row_idx} column count {len(row)}, "
                        f"expected {expected_width}"
                    ),
                )

            window_seconds_str = row[idx_window_seconds]
            try:
                window_seconds_int = int(window_seconds_str)
            except ValueError:
                raise Stage19ValidationError(
                    "E21",
                    detail=(
                        f"row {row_idx} window_seconds "
                        f"{window_seconds_str!r} is not an integer"
                    ),
                ) from None
            if window_seconds_int <= 0:
                raise Stage19ValidationError(
                    "E21",
                    detail=(
                        f"row {row_idx} window_seconds "
                        f"{window_seconds_int} is not positive"
                    ),
                )

            classification = row[idx_classification]
            if classification not in _STAGE18_CLASSIFICATIONS:
                raise Stage19ValidationError(
                    "E21",
                    detail=(
                        f"row {row_idx} classification "
                        f"{classification!r} not in Stage 18 set"
                    ),
                )

            record = ReviewMatrixRecord(
                policy_hash=row[idx_policy_hash],
                rule_id=row[idx_rule_id],
                window_seconds=window_seconds_int,
                stage18_classification=classification,
                stage17_label_preserved=row[idx_stage17_label],
            )
            key = (record.policy_hash, record.rule_id, record.window_seconds)
            index[key] = record  # last-write-wins per docstring

    return index


# ---------------------------------------------------------------------------
# Public reader: read_operator_input
# ---------------------------------------------------------------------------


def read_operator_input(path: Path) -> list[OperatorInputRow]:
    """Read and validate the operator-input CSV at ``path``.

    Validates the CSV header against ``OPERATOR_INPUT_COLUMNS``
    (exact column names and order). Returns a list of typed
    OperatorInputRow records, one per data row. A header-only
    CSV returns an empty list (this is a valid, no-op input).

    Per-row contract:
      * stage18_run_id, policy_hash, rule_id  -- stripped of
        leading/trailing whitespace; non-empty after stripping.
      * window_seconds  -- stripped, parsed as positive integer.
      * review_label    -- in LABELS (case-sensitive).
      * review_notes    -- preserved verbatim, no stripping.
        Length cap MAX_REVIEW_NOTES_LENGTH (2000). Forbidden
        characters: every chr with ord(c) < 32 except space, plus
        chr(127) DEL.

    Raises Stage19ValidationError with:
      * E06 if ``path`` is not an existing regular file.
      * E07 if header does not match OPERATOR_INPUT_COLUMNS.
      * E08 if a row has wrong column count, empty required field,
        or unparseable / non-positive window_seconds.
      * E09 if ``review_label`` is not in LABELS.
      * E13 if ``review_notes`` exceeds the length cap or contains
        forbidden control characters.
    """

    if not path.is_file():
        raise Stage19ValidationError("E06", detail=str(path))

    expected_cols = OPERATOR_INPUT_COLUMNS
    expected_width = len(expected_cols)

    rows: list[OperatorInputRow] = []

    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.reader(f)
        try:
            header = next(reader)
        except StopIteration:
            raise Stage19ValidationError(
                "E07", detail="operator_review_input.csv is empty (no header)"
            ) from None

        if tuple(header) != expected_cols:
            raise Stage19ValidationError(
                "E07",
                detail=(
                    f"header mismatch: got {header!r}, "
                    f"expected {list(expected_cols)!r}"
                ),
            )

        for row_idx, raw_row in enumerate(reader, start=1):
            if len(raw_row) != expected_width:
                raise Stage19ValidationError(
                    "E08",
                    detail=(
                        f"row {row_idx} column count {len(raw_row)}, "
                        f"expected {expected_width}"
                    ),
                )

            stage18_run_id = raw_row[0].strip()
            policy_hash = raw_row[1].strip()
            rule_id = raw_row[2].strip()
            window_seconds_raw = raw_row[3].strip()
            review_label = raw_row[4]
            review_notes = raw_row[5]

            if not stage18_run_id:
                raise Stage19ValidationError(
                    "E08",
                    detail=f"row {row_idx} stage18_run_id empty after strip",
                )
            if not policy_hash:
                raise Stage19ValidationError(
                    "E08",
                    detail=f"row {row_idx} policy_hash empty after strip",
                )
            if not rule_id:
                raise Stage19ValidationError(
                    "E08", detail=f"row {row_idx} rule_id empty after strip"
                )
            if not window_seconds_raw:
                raise Stage19ValidationError(
                    "E08",
                    detail=f"row {row_idx} window_seconds empty after strip",
                )

            try:
                window_seconds = int(window_seconds_raw)
            except ValueError:
                raise Stage19ValidationError(
                    "E08",
                    detail=(
                        f"row {row_idx} window_seconds "
                        f"{window_seconds_raw!r} is not an integer"
                    ),
                ) from None
            if window_seconds <= 0:
                raise Stage19ValidationError(
                    "E08",
                    detail=(
                        f"row {row_idx} window_seconds {window_seconds} "
                        f"is not positive"
                    ),
                )

            if review_label not in LABELS:
                raise Stage19ValidationError(
                    "E09",
                    detail=(
                        f"row {row_idx} review_label {review_label!r} "
                        f"not in LABELS"
                    ),
                )

            if len(review_notes) > MAX_REVIEW_NOTES_LENGTH:
                raise Stage19ValidationError(
                    "E13",
                    detail=(
                        f"row {row_idx} review_notes length "
                        f"{len(review_notes)} > {MAX_REVIEW_NOTES_LENGTH}"
                    ),
                )
            for ch in review_notes:
                if ch == " ":
                    continue
                code_point = ord(ch)
                if code_point < 32 or code_point == 127:
                    raise Stage19ValidationError(
                        "E13",
                        detail=(
                            f"row {row_idx} review_notes contains forbidden "
                            f"control char ord={code_point}"
                        ),
                    )

            rows.append(OperatorInputRow(
                stage18_run_id=stage18_run_id,
                policy_hash=policy_hash,
                rule_id=rule_id,
                window_seconds=window_seconds,
                review_label=review_label,
                review_notes=review_notes,
            ))

    return rows


# ---------------------------------------------------------------------------
# Public reader: read_prior_ledger
# ---------------------------------------------------------------------------


def read_prior_ledger(path_dir: Path) -> tuple[list[LedgerRow], dict]:
    """Read a prior Stage 19 output directory as read-only.

    Strict contract: ``path_dir`` MUST be a non-None Path
    pointing to an existing directory containing both
    ``operator_review_ledger.csv`` and ``manifest.json``.
    Phase 19.3 CLI orchestration is responsible for explicitly
    checking whether ``--prior-ledger-dir`` was supplied and
    only calling this function when it was; this function does
    NOT accept ``None``.

    Validates:
      * Prior manifest ``stage19_schema_version`` ==
        ``"stage19_ledger_v1"``.
      * Prior ledger CSV header matches LEDGER_COLUMNS exactly
        (column names, order, count).
      * Each ledger row: 13 columns; positive int
        ``window_seconds``; positive int ``review_sequence``;
        ``review_label`` in LABELS; ``review_timestamp_utc`` in
        ``YYYY-MM-DDTHH:MM:SSZ`` form.

    Returns ``(rows, manifest_dict)`` where ``rows`` is a list of
    LedgerRow records and ``manifest_dict`` is the parsed prior
    manifest JSON.

    Raises Stage19ValidationError with:
      * E16 if ``path_dir`` is None / not a directory, or either
        required file is missing inside it.
      * E17 if prior manifest cannot be parsed as a JSON object,
        or its ``stage19_schema_version`` does not equal
        ``"stage19_ledger_v1"``.
      * E18 if the ledger CSV header is invalid or any ledger row
        is malformed (column count, unparseable required field,
        invalid review_label, invalid timestamp).
    """

    if path_dir is None or not path_dir.is_dir():
        raise Stage19ValidationError(
            "E16", detail=f"prior-ledger-dir invalid: {path_dir!r}"
        )

    ledger_path = path_dir / _PRIOR_LEDGER_CSV_FILENAME
    manifest_path = path_dir / _PRIOR_LEDGER_MANIFEST_FILENAME

    missing: list[str] = []
    if not ledger_path.is_file():
        missing.append(_PRIOR_LEDGER_CSV_FILENAME)
    if not manifest_path.is_file():
        missing.append(_PRIOR_LEDGER_MANIFEST_FILENAME)
    if missing:
        raise Stage19ValidationError(
            "E16",
            detail=f"missing files in {path_dir}: {missing}",
        )

    try:
        manifest_dict = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise Stage19ValidationError(
            "E17", detail=f"manifest.json decode: {exc}"
        ) from exc
    if not isinstance(manifest_dict, dict):
        raise Stage19ValidationError(
            "E17", detail="manifest.json is not a JSON object"
        )
    schema_version = manifest_dict.get("stage19_schema_version")
    if schema_version != _PRIOR_LEDGER_SCHEMA_VERSION:
        raise Stage19ValidationError(
            "E17",
            detail=(
                f"got stage19_schema_version={schema_version!r}, "
                f"expected {_PRIOR_LEDGER_SCHEMA_VERSION!r}"
            ),
        )

    expected_cols = LEDGER_COLUMNS
    expected_width = len(expected_cols)

    rows: list[LedgerRow] = []

    with ledger_path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.reader(f)
        try:
            header = next(reader)
        except StopIteration:
            raise Stage19ValidationError(
                "E18",
                detail="operator_review_ledger.csv is empty (no header)",
            ) from None

        if tuple(header) != expected_cols:
            raise Stage19ValidationError(
                "E18",
                detail=(
                    f"ledger header mismatch: got {header!r}, "
                    f"expected {list(expected_cols)!r}"
                ),
            )

        for row_idx, raw_row in enumerate(reader, start=1):
            if len(raw_row) != expected_width:
                raise Stage19ValidationError(
                    "E18",
                    detail=(
                        f"ledger row {row_idx} column count {len(raw_row)}, "
                        f"expected {expected_width}"
                    ),
                )

            (
                stage19_run_id,
                ledger_row_id,
                stage18_run_id,
                policy_hash,
                rule_id,
                window_seconds_raw,
                operator_id,
                review_sequence_raw,
                review_label,
                review_notes,
                review_timestamp_utc,
                stage18_classification,
                stage17_label_preserved,
            ) = raw_row

            try:
                window_seconds = int(window_seconds_raw)
            except ValueError:
                raise Stage19ValidationError(
                    "E18",
                    detail=(
                        f"ledger row {row_idx} window_seconds "
                        f"{window_seconds_raw!r} is not an integer"
                    ),
                ) from None
            if window_seconds <= 0:
                raise Stage19ValidationError(
                    "E18",
                    detail=(
                        f"ledger row {row_idx} window_seconds "
                        f"{window_seconds} is not positive"
                    ),
                )

            try:
                review_sequence = int(review_sequence_raw)
            except ValueError:
                raise Stage19ValidationError(
                    "E18",
                    detail=(
                        f"ledger row {row_idx} review_sequence "
                        f"{review_sequence_raw!r} is not an integer"
                    ),
                ) from None
            if review_sequence <= 0:
                raise Stage19ValidationError(
                    "E18",
                    detail=(
                        f"ledger row {row_idx} review_sequence "
                        f"{review_sequence} is not positive"
                    ),
                )

            if review_label not in LABELS:
                raise Stage19ValidationError(
                    "E18",
                    detail=(
                        f"ledger row {row_idx} review_label "
                        f"{review_label!r} not in LABELS"
                    ),
                )

            try:
                datetime.strptime(review_timestamp_utc, _RUN_TIMESTAMP_FORMAT)
            except ValueError:
                raise Stage19ValidationError(
                    "E18",
                    detail=(
                        f"ledger row {row_idx} review_timestamp_utc "
                        f"{review_timestamp_utc!r} not in "
                        f"YYYY-MM-DDTHH:MM:SSZ form"
                    ),
                ) from None

            rows.append(LedgerRow(
                stage19_run_id=stage19_run_id,
                ledger_row_id=ledger_row_id,
                stage18_run_id=stage18_run_id,
                policy_hash=policy_hash,
                rule_id=rule_id,
                window_seconds=window_seconds,
                operator_id=operator_id,
                review_sequence=review_sequence,
                review_label=review_label,
                review_notes=review_notes,
                review_timestamp_utc=review_timestamp_utc,
                stage18_classification=stage18_classification,
                stage17_label_preserved=stage17_label_preserved,
            ))

    return rows, manifest_dict


__all__ = [
    "OperatorInputRow",
    "ReviewMatrixIndex",
    "ReviewMatrixRecord",
    "Stage18ManifestData",
    "read_operator_input",
    "read_prior_ledger",
    "read_stage18_manifest",
    "read_stage18_review_matrix",
]

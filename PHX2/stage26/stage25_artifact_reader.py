"""Stage 26.1 Stage 25 artifact reader (pure / deterministic / read-only).

Every entrypoint here opens Stage 25 artifact files in binary mode,
parses them with the stdlib ``json`` module, and projects each
parsed object into a Stage 26.1 input record from
``PHX2.stage26.models``. The reader:

  * NEVER writes to a Stage 25 artifact file.
  * NEVER mutates a Stage 25 artifact file's mtime / atime.
  * NEVER joins records across artifacts (no by-mint joins).
  * NEVER aggregates / classifies / dedupes / normalizes.
  * NEVER coerces ``None`` to ``0`` / ``""`` / a default.
  * NEVER upgrades a Stage 25 truth-class token.
  * NEVER synthesizes fake measured peak / ATH / migration fields.
  * NEVER reads the process environment.
  * NEVER opens a network / DB / messaging connection.
  * NEVER defines a CLI entrypoint.

Entrypoints (mirror the Stage 26.0 spec-lock §6.1):

  * ``read_stage25_manifest(stage25_dir) -> Stage25ManifestInput``
  * ``read_stage25_summary(stage25_dir) -> Stage25SummaryInput``
  * ``read_migration_observations(stage25_dir)
        -> tuple[MigrationObservationInput, ...]``
  * ``read_migration_measurements(stage25_dir)
        -> tuple[MigrationMeasurementInput, ...]``
  * ``read_price_window_observations(stage25_dir)
        -> tuple[PriceWindowObservationInput, ...]``
  * ``read_ath_candidates(stage25_dir)
        -> tuple[ATHCandidateInput, ...]``
  * ``read_source_reconciliations(stage25_dir)
        -> tuple[SourceReconciliationInput, ...]``
  * ``read_ath_measurements(stage25_dir)
        -> tuple[ATHMeasurementInput, ...]``
  * ``read_measurement_rejections(stage25_dir)
        -> tuple[MeasurementRejectionInput, ...]``

The lower-level helpers (``_sha256_of_bytes`` /
``_load_jsonl_rows`` / ``_project_*``) are deliberately exposed
under ``__all__`` so the validator
(``stage25_artifact_validation.py``) can re-use them without re-
opening files.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import MappingProxyType
from typing import Mapping

from PHX2.stage26.errors import (
    Stage26ManifestError,
    Stage26ReaderError,
    Stage26SchemaError,
)
from PHX2.stage26.constants import (
    STG26_CAL_ARTIFACT_MISSING_REQUIRED,
    STG26_CAL_ARTIFACT_SCHEMA_INVALID,
    STG26_CAL_MANIFEST_HASH_SELF_INVALID,
    STG26_CAL_MANIFEST_NOT_FOUND,
    STG26_CAL_MANIFEST_SCHEMA_INVALID,
    STG26_CAL_RECORD_NULL_AS_ZERO_VIOLATION,
    STG26_CAL_RECORD_SCHEMA_INVALID,
    STG26_CAL_RECORD_TRUTH_CLASS_INVALID,
)
from PHX2.stage26.models import (
    ATHCandidateInput,
    ATHMeasurementInput,
    MeasurementRejectionInput,
    MigrationMeasurementInput,
    MigrationObservationInput,
    PriceWindowObservationInput,
    SourceReconciliationInput,
    Stage25ManifestFileEntryInput,
    Stage25ManifestInput,
    Stage25Stage24ManifestPinInput,
    Stage25SummaryInput,
)
from PHX2.stage26.stage25_schema_whitelist import (
    ATH_CANDIDATE_KINDS,
    CONFIDENCE_LEVELS,
    MEASUREMENT_FAMILIES,
    MEASUREMENT_FAMILY_ATH,
    MEASUREMENT_FAMILY_MIGRATION,
    MEASUREMENT_STATUSES,
    MEASUREMENT_STATUS_MEASURED,
    PRICE_WINDOW_KINDS,
    QUOTE_DENOMINATIONS,
    RECONCILIATION_STATUSES,
    REJECTION_REASONS,
    SELF_REFERENTIAL_MANIFEST_BYTE_COUNT,
    SELF_REFERENTIAL_MANIFEST_ROW_COUNT,
    SELF_REFERENTIAL_MANIFEST_SHA256,
    SOURCE_FAMILIES,
    SOURCE_STATUSES,
    STAGE25_ATH_CANDIDATES_FILENAME,
    STAGE25_ATH_MEASUREMENTS_FILENAME,
    STAGE25_MANIFEST_FILENAME,
    STAGE25_MEASUREMENT_REJECTIONS_FILENAME,
    STAGE25_MIGRATION_MEASUREMENTS_FILENAME,
    STAGE25_MIGRATION_OBSERVATIONS_FILENAME,
    STAGE25_PRICE_WINDOW_OBSERVATIONS_FILENAME,
    STAGE25_SOURCE_RECONCILIATIONS_FILENAME,
    STAGE25_SUMMARY_FILENAME,
)


# ---------------------------------------------------------------------------
# Locked per-artifact key sets
# ---------------------------------------------------------------------------


_MIGRATION_OBSERVATION_KEYS: frozenset[str] = frozenset({
    "token_mint",
    "source_family",
    "source_status",
    "observed_at_utc",
    "slot",
    "block_time",
    "migration_signature",
    "migration_pool",
    "provider_id",
    "reason_codes",
    "evidence",
    "input_missing_fields",
    "observation_hash",
})


_MIGRATION_MEASUREMENT_KEYS: frozenset[str] = frozenset({
    "measurement_family",
    "measurement_status",
    "confidence_level",
    "reconciliation_status",
    "token_mint",
    "schema_version",
    "threshold_version",
    "measurer_name",
    "measurer_version",
    "consolidated_slot",
    "consolidated_block_time",
    "reconciled_signature",
    "selected_source_family",
    "contributing_source_count",
    "reason_codes",
    "numeric_features",
    "evidence",
    "input_missing_fields",
    "measurement_hash",
})


_PRICE_WINDOW_OBSERVATION_KEYS: frozenset[str] = frozenset({
    "token_mint",
    "source_family",
    "source_status",
    "window_kind",
    "observed_at_utc",
    "slot",
    "block_time",
    "price",
    "quote_denomination",
    "reason_codes",
    "evidence",
    "observation_hash",
})


_ATH_CANDIDATE_KEYS: frozenset[str] = frozenset({
    "token_mint",
    "source_family",
    "source_status",
    "candidate_kind",
    "confidence_level",
    "peak_observed_at_utc",
    "peak_slot",
    "peak_block_time",
    "peak_price",
    "quote_denomination",
    "reason_codes",
    "evidence",
    "input_missing_fields",
    "candidate_hash",
})


_SOURCE_RECONCILIATION_KEYS: frozenset[str] = frozenset({
    "measurement_family",
    "reconciliation_status",
    "confidence_level",
    "token_mint",
    "source_families",
    "contributing_source_count",
    "disagreeing_source_count",
    "disagreement_metric",
    "reason_codes",
    "evidence",
    "reconciliation_hash",
})


_ATH_MEASUREMENT_KEYS: frozenset[str] = frozenset({
    "measurement_family",
    "measurement_status",
    "confidence_level",
    "reconciliation_status",
    "token_mint",
    "schema_version",
    "threshold_version",
    "measurer_name",
    "measurer_version",
    "consolidated_peak_slot",
    "consolidated_peak_block_time",
    "consolidated_peak_price",
    "quote_denomination",
    "peak_source_family",
    "reconciled_peak_observed_at_utc",
    "time_to_peak_seconds",
    "contributing_source_count",
    "reason_codes",
    "numeric_features",
    "evidence",
    "input_missing_fields",
    "measurement_hash",
})


_MEASUREMENT_REJECTION_KEYS: frozenset[str] = frozenset({
    "rejection_reason",
    "token_mint",
    "source_family",
    "detail",
    "reason_codes",
})


_MANIFEST_KEYS: frozenset[str] = frozenset({
    "stage_name",
    "stage_version",
    "schema_version",
    "observe_only_mode",
    "redaction_confirmed",
    "manifest_kind",
    "files",
    "upstream_stage24_pin",
    "created_at_utc",
    "runner_name",
    "runner_version",
    "writer_name",
    "writer_version",
})


_MANIFEST_FILE_ENTRY_KEYS: frozenset[str] = frozenset({
    "file_basename",
    "sha256",
    "row_count",
    "byte_count",
})


_MANIFEST_UPSTREAM_PIN_KEYS: frozenset[str] = frozenset({
    "upstream_manifest_basename",
    "upstream_manifest_sha256",
})


_SUMMARY_KEYS: frozenset[str] = frozenset({
    "stage_name",
    "stage_version",
    "schema_version",
    "summary_version",
    "observe_only_mode",
    "created_at_utc",
    "observed_token_count",
    "row_counts",
    "migration_observation_source_family_counts",
    "migration_observation_source_status_counts",
    "migration_measurement_status_counts",
    "migration_measurement_confidence_counts",
    "migration_measurement_reconciliation_counts",
    "price_window_kind_counts",
    "price_window_source_status_counts",
    "ath_candidate_kind_counts",
    "ath_candidate_confidence_counts",
    "ath_candidate_source_family_counts",
    "ath_candidate_source_status_counts",
    "source_reconciliation_status_counts",
    "source_reconciliation_confidence_counts",
    "ath_measurement_status_counts",
    "ath_measurement_confidence_counts",
    "ath_measurement_reconciliation_counts",
    "rejection_reason_counts",
})


# ---------------------------------------------------------------------------
# Low-level file / hash helpers (pure)
# ---------------------------------------------------------------------------


def _read_file_bytes(path: Path) -> bytes:
    """Return the bytes of ``path``. Pure read; no write / mtime change."""
    with path.open("rb") as handle:
        return handle.read()


def _sha256_of_bytes(data: bytes) -> str:
    """Return the SHA-256 hex digest of ``data``."""
    return hashlib.sha256(data).hexdigest()


def _count_non_blank_lines(data: bytes) -> int:
    """Count non-blank lines in ``data``.

    Mirrors the Stage 25 writer's "non-blank line" projection rule:
    a line is non-blank when its UTF-8 decode strips to a non-empty
    string. The empty bytes object has zero non-blank lines.
    """
    if data == b"":
        return 0
    text = data.decode("utf-8")
    count = 0
    for line in text.split("\n"):
        if line.strip() != "":
            count += 1
    return count


def _project_jsonl_rows(
    *,
    artifact_basename: str,
    data: bytes,
) -> tuple[Mapping[str, object], ...]:
    """Parse JSONL bytes into a tuple of parsed objects.

    Skips blank lines (same rule as ``_count_non_blank_lines``).
    Raises ``Stage26SchemaError`` on malformed JSON or non-object
    rows.
    """
    if data == b"":
        return ()
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise Stage26SchemaError(
            f"{artifact_basename}: bytes are not valid UTF-8: {exc!s}",
            error_code=STG26_CAL_ARTIFACT_SCHEMA_INVALID,
        ) from exc
    rows: list[Mapping[str, object]] = []
    for index, line in enumerate(text.split("\n")):
        if line.strip() == "":
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as exc:
            raise Stage26SchemaError(
                f"{artifact_basename} row {index}: invalid JSON: {exc!s}",
                error_code=STG26_CAL_ARTIFACT_SCHEMA_INVALID,
            ) from exc
        if not isinstance(obj, dict):
            raise Stage26SchemaError(
                f"{artifact_basename} row {index}: JSONL row must be a "
                f"JSON object, got {type(obj).__name__}",
                error_code=STG26_CAL_ARTIFACT_SCHEMA_INVALID,
            )
        rows.append(obj)
    return tuple(rows)


def _parse_json_bytes(
    *,
    artifact_basename: str,
    data: bytes,
) -> Mapping[str, object]:
    """Parse a JSON object from bytes.

    Raises ``Stage26SchemaError`` on invalid JSON or non-object
    top-level.
    """
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise Stage26SchemaError(
            f"{artifact_basename}: bytes are not valid UTF-8: {exc!s}",
            error_code=STG26_CAL_ARTIFACT_SCHEMA_INVALID,
        ) from exc
    try:
        obj = json.loads(text)
    except json.JSONDecodeError as exc:
        raise Stage26SchemaError(
            f"{artifact_basename}: invalid JSON: {exc!s}",
            error_code=STG26_CAL_ARTIFACT_SCHEMA_INVALID,
        ) from exc
    if not isinstance(obj, dict):
        raise Stage26SchemaError(
            f"{artifact_basename}: top-level JSON must be an object, "
            f"got {type(obj).__name__}",
            error_code=STG26_CAL_ARTIFACT_SCHEMA_INVALID,
        )
    return obj


def _require_exact_key_set(
    *,
    artifact_basename: str,
    record_index: int,
    actual_keys: frozenset[str],
    expected_keys: frozenset[str],
) -> None:
    """Raise ``Stage26SchemaError`` if ``actual_keys != expected_keys``."""
    missing = expected_keys - actual_keys
    extra = actual_keys - expected_keys
    if missing:
        raise Stage26SchemaError(
            f"{artifact_basename} row {record_index}: missing required "
            f"field(s) {sorted(missing)}",
            error_code=STG26_CAL_RECORD_SCHEMA_INVALID,
        )
    if extra:
        raise Stage26SchemaError(
            f"{artifact_basename} row {record_index}: unexpected extra "
            f"field(s) {sorted(extra)}",
            error_code=STG26_CAL_RECORD_SCHEMA_INVALID,
        )


def _require_str(
    *,
    artifact_basename: str,
    record_index: int,
    field_name: str,
    value: object,
) -> str:
    if not isinstance(value, str):
        raise Stage26SchemaError(
            f"{artifact_basename} row {record_index}: field {field_name!r} "
            f"must be a string, got {type(value).__name__}",
            error_code=STG26_CAL_RECORD_SCHEMA_INVALID,
        )
    return value


def _require_int(
    *,
    artifact_basename: str,
    record_index: int,
    field_name: str,
    value: object,
) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise Stage26SchemaError(
            f"{artifact_basename} row {record_index}: field {field_name!r} "
            f"must be a strict int, got {type(value).__name__}",
            error_code=STG26_CAL_RECORD_SCHEMA_INVALID,
        )
    return value


def _require_optional_int(
    *,
    artifact_basename: str,
    record_index: int,
    field_name: str,
    value: object,
) -> "int | None":
    if value is None:
        return None
    return _require_int(
        artifact_basename=artifact_basename,
        record_index=record_index,
        field_name=field_name,
        value=value,
    )


def _require_str_tuple(
    *,
    artifact_basename: str,
    record_index: int,
    field_name: str,
    value: object,
) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise Stage26SchemaError(
            f"{artifact_basename} row {record_index}: field {field_name!r} "
            f"must be a JSON array, got {type(value).__name__}",
            error_code=STG26_CAL_RECORD_SCHEMA_INVALID,
        )
    out: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str):
            raise Stage26SchemaError(
                f"{artifact_basename} row {record_index}: field "
                f"{field_name!r}[{index}] must be a string, got "
                f"{type(item).__name__}",
                error_code=STG26_CAL_RECORD_SCHEMA_INVALID,
            )
        out.append(item)
    return tuple(out)


def _require_mapping(
    *,
    artifact_basename: str,
    record_index: int,
    field_name: str,
    value: object,
) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise Stage26SchemaError(
            f"{artifact_basename} row {record_index}: field {field_name!r} "
            f"must be a JSON object, got {type(value).__name__}",
            error_code=STG26_CAL_RECORD_SCHEMA_INVALID,
        )
    for key in value.keys():
        if not isinstance(key, str):
            raise Stage26SchemaError(
                f"{artifact_basename} row {record_index}: field "
                f"{field_name!r} has a non-string key {key!r}",
                error_code=STG26_CAL_RECORD_SCHEMA_INVALID,
            )
    return MappingProxyType(dict(value))


def _require_closed_set(
    *,
    artifact_basename: str,
    record_index: int,
    field_name: str,
    value: str,
    members: tuple[str, ...],
    truth_class_check: bool = False,
) -> str:
    if value not in members:
        code = (
            STG26_CAL_RECORD_TRUTH_CLASS_INVALID
            if truth_class_check
            else STG26_CAL_RECORD_SCHEMA_INVALID
        )
        raise Stage26SchemaError(
            f"{artifact_basename} row {record_index}: field {field_name!r} "
            f"value {value!r} is not a member of the locked closed set",
            error_code=code,
        )
    return value


def _require_closed_set_or_empty(
    *,
    artifact_basename: str,
    record_index: int,
    field_name: str,
    value: str,
    members: tuple[str, ...],
) -> str:
    if value == "":
        return value
    return _require_closed_set(
        artifact_basename=artifact_basename,
        record_index=record_index,
        field_name=field_name,
        value=value,
        members=members,
    )


# ---------------------------------------------------------------------------
# Per-row projectors
# ---------------------------------------------------------------------------


def _project_migration_observation(
    *,
    record_index: int,
    obj: Mapping[str, object],
) -> MigrationObservationInput:
    basename = STAGE25_MIGRATION_OBSERVATIONS_FILENAME
    _require_exact_key_set(
        artifact_basename=basename,
        record_index=record_index,
        actual_keys=frozenset(obj.keys()),
        expected_keys=_MIGRATION_OBSERVATION_KEYS,
    )
    return MigrationObservationInput(
        token_mint=_require_str(
            artifact_basename=basename,
            record_index=record_index,
            field_name="token_mint",
            value=obj["token_mint"],
        ),
        source_family=_require_closed_set(
            artifact_basename=basename,
            record_index=record_index,
            field_name="source_family",
            value=_require_str(
                artifact_basename=basename,
                record_index=record_index,
                field_name="source_family",
                value=obj["source_family"],
            ),
            members=SOURCE_FAMILIES,
        ),
        source_status=_require_closed_set(
            artifact_basename=basename,
            record_index=record_index,
            field_name="source_status",
            value=_require_str(
                artifact_basename=basename,
                record_index=record_index,
                field_name="source_status",
                value=obj["source_status"],
            ),
            members=SOURCE_STATUSES,
        ),
        observed_at_utc=_require_str(
            artifact_basename=basename,
            record_index=record_index,
            field_name="observed_at_utc",
            value=obj["observed_at_utc"],
        ),
        slot=_require_int(
            artifact_basename=basename,
            record_index=record_index,
            field_name="slot",
            value=obj["slot"],
        ),
        block_time=_require_int(
            artifact_basename=basename,
            record_index=record_index,
            field_name="block_time",
            value=obj["block_time"],
        ),
        migration_signature=_require_str(
            artifact_basename=basename,
            record_index=record_index,
            field_name="migration_signature",
            value=obj["migration_signature"],
        ),
        migration_pool=_require_str(
            artifact_basename=basename,
            record_index=record_index,
            field_name="migration_pool",
            value=obj["migration_pool"],
        ),
        provider_id=_require_str(
            artifact_basename=basename,
            record_index=record_index,
            field_name="provider_id",
            value=obj["provider_id"],
        ),
        reason_codes=_require_str_tuple(
            artifact_basename=basename,
            record_index=record_index,
            field_name="reason_codes",
            value=obj["reason_codes"],
        ),
        evidence=_require_mapping(
            artifact_basename=basename,
            record_index=record_index,
            field_name="evidence",
            value=obj["evidence"],
        ),
        input_missing_fields=_require_str_tuple(
            artifact_basename=basename,
            record_index=record_index,
            field_name="input_missing_fields",
            value=obj["input_missing_fields"],
        ),
        observation_hash=_require_str(
            artifact_basename=basename,
            record_index=record_index,
            field_name="observation_hash",
            value=obj["observation_hash"],
        ),
    )


def _project_migration_measurement(
    *,
    record_index: int,
    obj: Mapping[str, object],
) -> MigrationMeasurementInput:
    basename = STAGE25_MIGRATION_MEASUREMENTS_FILENAME
    _require_exact_key_set(
        artifact_basename=basename,
        record_index=record_index,
        actual_keys=frozenset(obj.keys()),
        expected_keys=_MIGRATION_MEASUREMENT_KEYS,
    )
    measurement_family = _require_closed_set(
        artifact_basename=basename,
        record_index=record_index,
        field_name="measurement_family",
        value=_require_str(
            artifact_basename=basename,
            record_index=record_index,
            field_name="measurement_family",
            value=obj["measurement_family"],
        ),
        members=MEASUREMENT_FAMILIES,
    )
    if measurement_family != MEASUREMENT_FAMILY_MIGRATION:
        raise Stage26SchemaError(
            f"{basename} row {record_index}: measurement_family must be "
            f"{MEASUREMENT_FAMILY_MIGRATION!r}, got {measurement_family!r}",
            error_code=STG26_CAL_RECORD_SCHEMA_INVALID,
        )
    measurement_status = _require_closed_set(
        artifact_basename=basename,
        record_index=record_index,
        field_name="measurement_status",
        value=_require_str(
            artifact_basename=basename,
            record_index=record_index,
            field_name="measurement_status",
            value=obj["measurement_status"],
        ),
        members=MEASUREMENT_STATUSES,
        truth_class_check=True,
    )
    consolidated_slot = _require_int(
        artifact_basename=basename,
        record_index=record_index,
        field_name="consolidated_slot",
        value=obj["consolidated_slot"],
    )
    consolidated_block_time = _require_int(
        artifact_basename=basename,
        record_index=record_index,
        field_name="consolidated_block_time",
        value=obj["consolidated_block_time"],
    )
    reconciled_signature = _require_str(
        artifact_basename=basename,
        record_index=record_index,
        field_name="reconciled_signature",
        value=obj["reconciled_signature"],
    )
    selected_source_family = _require_closed_set_or_empty(
        artifact_basename=basename,
        record_index=record_index,
        field_name="selected_source_family",
        value=_require_str(
            artifact_basename=basename,
            record_index=record_index,
            field_name="selected_source_family",
            value=obj["selected_source_family"],
        ),
        members=SOURCE_FAMILIES,
    )
    if measurement_status == MEASUREMENT_STATUS_MEASURED:
        if (
            reconciled_signature == ""
            or selected_source_family == ""
            or consolidated_slot < 0
            or consolidated_block_time < 0
        ):
            raise Stage26SchemaError(
                f"{basename} row {record_index}: MEASURED migration "
                "measurement must carry reconciled_signature, "
                "selected_source_family, and non-negative consolidated "
                "slot / block_time",
                error_code=STG26_CAL_RECORD_NULL_AS_ZERO_VIOLATION,
            )
    else:
        if (
            reconciled_signature != ""
            or selected_source_family != ""
            or consolidated_slot != -1
            or consolidated_block_time != -1
        ):
            raise Stage26SchemaError(
                f"{basename} row {record_index}: non-MEASURED migration "
                "measurement must carry empty reconciled_signature / "
                "selected_source_family and -1 consolidated slot / "
                "block_time sentinel",
                error_code=STG26_CAL_RECORD_NULL_AS_ZERO_VIOLATION,
            )
    return MigrationMeasurementInput(
        measurement_family=measurement_family,
        measurement_status=measurement_status,
        confidence_level=_require_closed_set(
            artifact_basename=basename,
            record_index=record_index,
            field_name="confidence_level",
            value=_require_str(
                artifact_basename=basename,
                record_index=record_index,
                field_name="confidence_level",
                value=obj["confidence_level"],
            ),
            members=CONFIDENCE_LEVELS,
        ),
        reconciliation_status=_require_closed_set(
            artifact_basename=basename,
            record_index=record_index,
            field_name="reconciliation_status",
            value=_require_str(
                artifact_basename=basename,
                record_index=record_index,
                field_name="reconciliation_status",
                value=obj["reconciliation_status"],
            ),
            members=RECONCILIATION_STATUSES,
        ),
        token_mint=_require_str(
            artifact_basename=basename,
            record_index=record_index,
            field_name="token_mint",
            value=obj["token_mint"],
        ),
        schema_version=_require_str(
            artifact_basename=basename,
            record_index=record_index,
            field_name="schema_version",
            value=obj["schema_version"],
        ),
        threshold_version=_require_str(
            artifact_basename=basename,
            record_index=record_index,
            field_name="threshold_version",
            value=obj["threshold_version"],
        ),
        measurer_name=_require_str(
            artifact_basename=basename,
            record_index=record_index,
            field_name="measurer_name",
            value=obj["measurer_name"],
        ),
        measurer_version=_require_str(
            artifact_basename=basename,
            record_index=record_index,
            field_name="measurer_version",
            value=obj["measurer_version"],
        ),
        consolidated_slot=consolidated_slot,
        consolidated_block_time=consolidated_block_time,
        reconciled_signature=reconciled_signature,
        selected_source_family=selected_source_family,
        contributing_source_count=_require_int(
            artifact_basename=basename,
            record_index=record_index,
            field_name="contributing_source_count",
            value=obj["contributing_source_count"],
        ),
        reason_codes=_require_str_tuple(
            artifact_basename=basename,
            record_index=record_index,
            field_name="reason_codes",
            value=obj["reason_codes"],
        ),
        numeric_features=_require_mapping(
            artifact_basename=basename,
            record_index=record_index,
            field_name="numeric_features",
            value=obj["numeric_features"],
        ),
        evidence=_require_mapping(
            artifact_basename=basename,
            record_index=record_index,
            field_name="evidence",
            value=obj["evidence"],
        ),
        input_missing_fields=_require_str_tuple(
            artifact_basename=basename,
            record_index=record_index,
            field_name="input_missing_fields",
            value=obj["input_missing_fields"],
        ),
        measurement_hash=_require_str(
            artifact_basename=basename,
            record_index=record_index,
            field_name="measurement_hash",
            value=obj["measurement_hash"],
        ),
    )


def _project_price_window_observation(
    *,
    record_index: int,
    obj: Mapping[str, object],
) -> PriceWindowObservationInput:
    basename = STAGE25_PRICE_WINDOW_OBSERVATIONS_FILENAME
    _require_exact_key_set(
        artifact_basename=basename,
        record_index=record_index,
        actual_keys=frozenset(obj.keys()),
        expected_keys=_PRICE_WINDOW_OBSERVATION_KEYS,
    )
    return PriceWindowObservationInput(
        token_mint=_require_str(
            artifact_basename=basename,
            record_index=record_index,
            field_name="token_mint",
            value=obj["token_mint"],
        ),
        source_family=_require_closed_set(
            artifact_basename=basename,
            record_index=record_index,
            field_name="source_family",
            value=_require_str(
                artifact_basename=basename,
                record_index=record_index,
                field_name="source_family",
                value=obj["source_family"],
            ),
            members=SOURCE_FAMILIES,
        ),
        source_status=_require_closed_set(
            artifact_basename=basename,
            record_index=record_index,
            field_name="source_status",
            value=_require_str(
                artifact_basename=basename,
                record_index=record_index,
                field_name="source_status",
                value=obj["source_status"],
            ),
            members=SOURCE_STATUSES,
        ),
        window_kind=_require_closed_set(
            artifact_basename=basename,
            record_index=record_index,
            field_name="window_kind",
            value=_require_str(
                artifact_basename=basename,
                record_index=record_index,
                field_name="window_kind",
                value=obj["window_kind"],
            ),
            members=PRICE_WINDOW_KINDS,
        ),
        observed_at_utc=_require_str(
            artifact_basename=basename,
            record_index=record_index,
            field_name="observed_at_utc",
            value=obj["observed_at_utc"],
        ),
        slot=_require_int(
            artifact_basename=basename,
            record_index=record_index,
            field_name="slot",
            value=obj["slot"],
        ),
        block_time=_require_int(
            artifact_basename=basename,
            record_index=record_index,
            field_name="block_time",
            value=obj["block_time"],
        ),
        price=_require_optional_int(
            artifact_basename=basename,
            record_index=record_index,
            field_name="price",
            value=obj["price"],
        ),
        quote_denomination=_require_closed_set(
            artifact_basename=basename,
            record_index=record_index,
            field_name="quote_denomination",
            value=_require_str(
                artifact_basename=basename,
                record_index=record_index,
                field_name="quote_denomination",
                value=obj["quote_denomination"],
            ),
            members=QUOTE_DENOMINATIONS,
        ),
        reason_codes=_require_str_tuple(
            artifact_basename=basename,
            record_index=record_index,
            field_name="reason_codes",
            value=obj["reason_codes"],
        ),
        evidence=_require_mapping(
            artifact_basename=basename,
            record_index=record_index,
            field_name="evidence",
            value=obj["evidence"],
        ),
        observation_hash=_require_str(
            artifact_basename=basename,
            record_index=record_index,
            field_name="observation_hash",
            value=obj["observation_hash"],
        ),
    )


def _project_ath_candidate(
    *,
    record_index: int,
    obj: Mapping[str, object],
) -> ATHCandidateInput:
    basename = STAGE25_ATH_CANDIDATES_FILENAME
    _require_exact_key_set(
        artifact_basename=basename,
        record_index=record_index,
        actual_keys=frozenset(obj.keys()),
        expected_keys=_ATH_CANDIDATE_KEYS,
    )
    return ATHCandidateInput(
        token_mint=_require_str(
            artifact_basename=basename,
            record_index=record_index,
            field_name="token_mint",
            value=obj["token_mint"],
        ),
        source_family=_require_closed_set(
            artifact_basename=basename,
            record_index=record_index,
            field_name="source_family",
            value=_require_str(
                artifact_basename=basename,
                record_index=record_index,
                field_name="source_family",
                value=obj["source_family"],
            ),
            members=SOURCE_FAMILIES,
        ),
        source_status=_require_closed_set(
            artifact_basename=basename,
            record_index=record_index,
            field_name="source_status",
            value=_require_str(
                artifact_basename=basename,
                record_index=record_index,
                field_name="source_status",
                value=obj["source_status"],
            ),
            members=SOURCE_STATUSES,
        ),
        candidate_kind=_require_closed_set(
            artifact_basename=basename,
            record_index=record_index,
            field_name="candidate_kind",
            value=_require_str(
                artifact_basename=basename,
                record_index=record_index,
                field_name="candidate_kind",
                value=obj["candidate_kind"],
            ),
            members=ATH_CANDIDATE_KINDS,
        ),
        confidence_level=_require_closed_set(
            artifact_basename=basename,
            record_index=record_index,
            field_name="confidence_level",
            value=_require_str(
                artifact_basename=basename,
                record_index=record_index,
                field_name="confidence_level",
                value=obj["confidence_level"],
            ),
            members=CONFIDENCE_LEVELS,
        ),
        peak_observed_at_utc=_require_str(
            artifact_basename=basename,
            record_index=record_index,
            field_name="peak_observed_at_utc",
            value=obj["peak_observed_at_utc"],
        ),
        peak_slot=_require_int(
            artifact_basename=basename,
            record_index=record_index,
            field_name="peak_slot",
            value=obj["peak_slot"],
        ),
        peak_block_time=_require_int(
            artifact_basename=basename,
            record_index=record_index,
            field_name="peak_block_time",
            value=obj["peak_block_time"],
        ),
        peak_price=_require_optional_int(
            artifact_basename=basename,
            record_index=record_index,
            field_name="peak_price",
            value=obj["peak_price"],
        ),
        quote_denomination=_require_closed_set(
            artifact_basename=basename,
            record_index=record_index,
            field_name="quote_denomination",
            value=_require_str(
                artifact_basename=basename,
                record_index=record_index,
                field_name="quote_denomination",
                value=obj["quote_denomination"],
            ),
            members=QUOTE_DENOMINATIONS,
        ),
        reason_codes=_require_str_tuple(
            artifact_basename=basename,
            record_index=record_index,
            field_name="reason_codes",
            value=obj["reason_codes"],
        ),
        evidence=_require_mapping(
            artifact_basename=basename,
            record_index=record_index,
            field_name="evidence",
            value=obj["evidence"],
        ),
        input_missing_fields=_require_str_tuple(
            artifact_basename=basename,
            record_index=record_index,
            field_name="input_missing_fields",
            value=obj["input_missing_fields"],
        ),
        candidate_hash=_require_str(
            artifact_basename=basename,
            record_index=record_index,
            field_name="candidate_hash",
            value=obj["candidate_hash"],
        ),
    )


def _project_source_reconciliation(
    *,
    record_index: int,
    obj: Mapping[str, object],
) -> SourceReconciliationInput:
    basename = STAGE25_SOURCE_RECONCILIATIONS_FILENAME
    _require_exact_key_set(
        artifact_basename=basename,
        record_index=record_index,
        actual_keys=frozenset(obj.keys()),
        expected_keys=_SOURCE_RECONCILIATION_KEYS,
    )
    measurement_family = _require_closed_set(
        artifact_basename=basename,
        record_index=record_index,
        field_name="measurement_family",
        value=_require_str(
            artifact_basename=basename,
            record_index=record_index,
            field_name="measurement_family",
            value=obj["measurement_family"],
        ),
        members=MEASUREMENT_FAMILIES,
    )
    if measurement_family != MEASUREMENT_FAMILY_ATH:
        raise Stage26SchemaError(
            f"{basename} row {record_index}: measurement_family must be "
            f"{MEASUREMENT_FAMILY_ATH!r}, got {measurement_family!r}",
            error_code=STG26_CAL_RECORD_SCHEMA_INVALID,
        )
    raw_source_families = _require_str_tuple(
        artifact_basename=basename,
        record_index=record_index,
        field_name="source_families",
        value=obj["source_families"],
    )
    for entry in raw_source_families:
        if entry not in SOURCE_FAMILIES:
            raise Stage26SchemaError(
                f"{basename} row {record_index}: source_families entry "
                f"{entry!r} is not a member of the locked SOURCE_FAMILIES "
                "closed set",
                error_code=STG26_CAL_RECORD_SCHEMA_INVALID,
            )
    raw_disagreement_metric = obj["disagreement_metric"]
    if raw_disagreement_metric is None:
        disagreement_metric: "Mapping[str, object] | None" = None
    else:
        disagreement_metric = _require_mapping(
            artifact_basename=basename,
            record_index=record_index,
            field_name="disagreement_metric",
            value=raw_disagreement_metric,
        )
    return SourceReconciliationInput(
        measurement_family=measurement_family,
        reconciliation_status=_require_closed_set(
            artifact_basename=basename,
            record_index=record_index,
            field_name="reconciliation_status",
            value=_require_str(
                artifact_basename=basename,
                record_index=record_index,
                field_name="reconciliation_status",
                value=obj["reconciliation_status"],
            ),
            members=RECONCILIATION_STATUSES,
        ),
        confidence_level=_require_closed_set(
            artifact_basename=basename,
            record_index=record_index,
            field_name="confidence_level",
            value=_require_str(
                artifact_basename=basename,
                record_index=record_index,
                field_name="confidence_level",
                value=obj["confidence_level"],
            ),
            members=CONFIDENCE_LEVELS,
        ),
        token_mint=_require_str(
            artifact_basename=basename,
            record_index=record_index,
            field_name="token_mint",
            value=obj["token_mint"],
        ),
        source_families=raw_source_families,
        contributing_source_count=_require_int(
            artifact_basename=basename,
            record_index=record_index,
            field_name="contributing_source_count",
            value=obj["contributing_source_count"],
        ),
        disagreeing_source_count=_require_int(
            artifact_basename=basename,
            record_index=record_index,
            field_name="disagreeing_source_count",
            value=obj["disagreeing_source_count"],
        ),
        disagreement_metric=disagreement_metric,
        reason_codes=_require_str_tuple(
            artifact_basename=basename,
            record_index=record_index,
            field_name="reason_codes",
            value=obj["reason_codes"],
        ),
        evidence=_require_mapping(
            artifact_basename=basename,
            record_index=record_index,
            field_name="evidence",
            value=obj["evidence"],
        ),
        reconciliation_hash=_require_str(
            artifact_basename=basename,
            record_index=record_index,
            field_name="reconciliation_hash",
            value=obj["reconciliation_hash"],
        ),
    )


def _project_ath_measurement(
    *,
    record_index: int,
    obj: Mapping[str, object],
) -> ATHMeasurementInput:
    basename = STAGE25_ATH_MEASUREMENTS_FILENAME
    _require_exact_key_set(
        artifact_basename=basename,
        record_index=record_index,
        actual_keys=frozenset(obj.keys()),
        expected_keys=_ATH_MEASUREMENT_KEYS,
    )
    measurement_family = _require_closed_set(
        artifact_basename=basename,
        record_index=record_index,
        field_name="measurement_family",
        value=_require_str(
            artifact_basename=basename,
            record_index=record_index,
            field_name="measurement_family",
            value=obj["measurement_family"],
        ),
        members=MEASUREMENT_FAMILIES,
    )
    if measurement_family != MEASUREMENT_FAMILY_ATH:
        raise Stage26SchemaError(
            f"{basename} row {record_index}: measurement_family must be "
            f"{MEASUREMENT_FAMILY_ATH!r}, got {measurement_family!r}",
            error_code=STG26_CAL_RECORD_SCHEMA_INVALID,
        )
    measurement_status = _require_closed_set(
        artifact_basename=basename,
        record_index=record_index,
        field_name="measurement_status",
        value=_require_str(
            artifact_basename=basename,
            record_index=record_index,
            field_name="measurement_status",
            value=obj["measurement_status"],
        ),
        members=MEASUREMENT_STATUSES,
        truth_class_check=True,
    )
    consolidated_peak_slot = _require_int(
        artifact_basename=basename,
        record_index=record_index,
        field_name="consolidated_peak_slot",
        value=obj["consolidated_peak_slot"],
    )
    consolidated_peak_block_time = _require_int(
        artifact_basename=basename,
        record_index=record_index,
        field_name="consolidated_peak_block_time",
        value=obj["consolidated_peak_block_time"],
    )
    consolidated_peak_price = _require_optional_int(
        artifact_basename=basename,
        record_index=record_index,
        field_name="consolidated_peak_price",
        value=obj["consolidated_peak_price"],
    )
    peak_source_family = _require_closed_set_or_empty(
        artifact_basename=basename,
        record_index=record_index,
        field_name="peak_source_family",
        value=_require_str(
            artifact_basename=basename,
            record_index=record_index,
            field_name="peak_source_family",
            value=obj["peak_source_family"],
        ),
        members=SOURCE_FAMILIES,
    )
    reconciled_peak_observed_at_utc = _require_str(
        artifact_basename=basename,
        record_index=record_index,
        field_name="reconciled_peak_observed_at_utc",
        value=obj["reconciled_peak_observed_at_utc"],
    )
    if measurement_status == MEASUREMENT_STATUS_MEASURED:
        if (
            consolidated_peak_slot < 0
            or consolidated_peak_block_time < 0
            or consolidated_peak_price is None
            or peak_source_family == ""
            or reconciled_peak_observed_at_utc == ""
        ):
            raise Stage26SchemaError(
                f"{basename} row {record_index}: MEASURED ATH measurement "
                "must carry non-negative peak slot / block_time, non-null "
                "peak_price, non-empty peak_source_family, and non-empty "
                "reconciled_peak_observed_at_utc",
                error_code=STG26_CAL_RECORD_NULL_AS_ZERO_VIOLATION,
            )
    else:
        if (
            consolidated_peak_slot != -1
            or consolidated_peak_block_time != -1
            or consolidated_peak_price is not None
            or peak_source_family != ""
            or reconciled_peak_observed_at_utc != ""
        ):
            raise Stage26SchemaError(
                f"{basename} row {record_index}: non-MEASURED ATH "
                "measurement must carry -1 peak slot / block_time, null "
                "peak_price, empty peak_source_family, and empty "
                "reconciled_peak_observed_at_utc",
                error_code=STG26_CAL_RECORD_NULL_AS_ZERO_VIOLATION,
            )
    return ATHMeasurementInput(
        measurement_family=measurement_family,
        measurement_status=measurement_status,
        confidence_level=_require_closed_set(
            artifact_basename=basename,
            record_index=record_index,
            field_name="confidence_level",
            value=_require_str(
                artifact_basename=basename,
                record_index=record_index,
                field_name="confidence_level",
                value=obj["confidence_level"],
            ),
            members=CONFIDENCE_LEVELS,
        ),
        reconciliation_status=_require_closed_set(
            artifact_basename=basename,
            record_index=record_index,
            field_name="reconciliation_status",
            value=_require_str(
                artifact_basename=basename,
                record_index=record_index,
                field_name="reconciliation_status",
                value=obj["reconciliation_status"],
            ),
            members=RECONCILIATION_STATUSES,
        ),
        token_mint=_require_str(
            artifact_basename=basename,
            record_index=record_index,
            field_name="token_mint",
            value=obj["token_mint"],
        ),
        schema_version=_require_str(
            artifact_basename=basename,
            record_index=record_index,
            field_name="schema_version",
            value=obj["schema_version"],
        ),
        threshold_version=_require_str(
            artifact_basename=basename,
            record_index=record_index,
            field_name="threshold_version",
            value=obj["threshold_version"],
        ),
        measurer_name=_require_str(
            artifact_basename=basename,
            record_index=record_index,
            field_name="measurer_name",
            value=obj["measurer_name"],
        ),
        measurer_version=_require_str(
            artifact_basename=basename,
            record_index=record_index,
            field_name="measurer_version",
            value=obj["measurer_version"],
        ),
        consolidated_peak_slot=consolidated_peak_slot,
        consolidated_peak_block_time=consolidated_peak_block_time,
        consolidated_peak_price=consolidated_peak_price,
        quote_denomination=_require_closed_set(
            artifact_basename=basename,
            record_index=record_index,
            field_name="quote_denomination",
            value=_require_str(
                artifact_basename=basename,
                record_index=record_index,
                field_name="quote_denomination",
                value=obj["quote_denomination"],
            ),
            members=QUOTE_DENOMINATIONS,
        ),
        peak_source_family=peak_source_family,
        reconciled_peak_observed_at_utc=reconciled_peak_observed_at_utc,
        time_to_peak_seconds=_require_optional_int(
            artifact_basename=basename,
            record_index=record_index,
            field_name="time_to_peak_seconds",
            value=obj["time_to_peak_seconds"],
        ),
        contributing_source_count=_require_int(
            artifact_basename=basename,
            record_index=record_index,
            field_name="contributing_source_count",
            value=obj["contributing_source_count"],
        ),
        reason_codes=_require_str_tuple(
            artifact_basename=basename,
            record_index=record_index,
            field_name="reason_codes",
            value=obj["reason_codes"],
        ),
        numeric_features=_require_mapping(
            artifact_basename=basename,
            record_index=record_index,
            field_name="numeric_features",
            value=obj["numeric_features"],
        ),
        evidence=_require_mapping(
            artifact_basename=basename,
            record_index=record_index,
            field_name="evidence",
            value=obj["evidence"],
        ),
        input_missing_fields=_require_str_tuple(
            artifact_basename=basename,
            record_index=record_index,
            field_name="input_missing_fields",
            value=obj["input_missing_fields"],
        ),
        measurement_hash=_require_str(
            artifact_basename=basename,
            record_index=record_index,
            field_name="measurement_hash",
            value=obj["measurement_hash"],
        ),
    )


def _project_measurement_rejection(
    *,
    record_index: int,
    obj: Mapping[str, object],
) -> MeasurementRejectionInput:
    basename = STAGE25_MEASUREMENT_REJECTIONS_FILENAME
    _require_exact_key_set(
        artifact_basename=basename,
        record_index=record_index,
        actual_keys=frozenset(obj.keys()),
        expected_keys=_MEASUREMENT_REJECTION_KEYS,
    )
    return MeasurementRejectionInput(
        rejection_reason=_require_closed_set(
            artifact_basename=basename,
            record_index=record_index,
            field_name="rejection_reason",
            value=_require_str(
                artifact_basename=basename,
                record_index=record_index,
                field_name="rejection_reason",
                value=obj["rejection_reason"],
            ),
            members=REJECTION_REASONS,
        ),
        token_mint=_require_str(
            artifact_basename=basename,
            record_index=record_index,
            field_name="token_mint",
            value=obj["token_mint"],
        ),
        source_family=_require_closed_set_or_empty(
            artifact_basename=basename,
            record_index=record_index,
            field_name="source_family",
            value=_require_str(
                artifact_basename=basename,
                record_index=record_index,
                field_name="source_family",
                value=obj["source_family"],
            ),
            members=SOURCE_FAMILIES,
        ),
        detail=_require_str(
            artifact_basename=basename,
            record_index=record_index,
            field_name="detail",
            value=obj["detail"],
        ),
        reason_codes=_require_str_tuple(
            artifact_basename=basename,
            record_index=record_index,
            field_name="reason_codes",
            value=obj["reason_codes"],
        ),
    )


# ---------------------------------------------------------------------------
# Manifest / summary projectors
# ---------------------------------------------------------------------------


def _project_manifest_file_entry(
    *,
    entry_index: int,
    obj: Mapping[str, object],
) -> Stage25ManifestFileEntryInput:
    basename = STAGE25_MANIFEST_FILENAME
    _require_exact_key_set(
        artifact_basename=basename,
        record_index=entry_index,
        actual_keys=frozenset(obj.keys()),
        expected_keys=_MANIFEST_FILE_ENTRY_KEYS,
    )
    file_basename = _require_str(
        artifact_basename=basename,
        record_index=entry_index,
        field_name="file_basename",
        value=obj["file_basename"],
    )
    sha256 = _require_str(
        artifact_basename=basename,
        record_index=entry_index,
        field_name="sha256",
        value=obj["sha256"],
    )
    row_count = _require_int(
        artifact_basename=basename,
        record_index=entry_index,
        field_name="row_count",
        value=obj["row_count"],
    )
    byte_count = _require_int(
        artifact_basename=basename,
        record_index=entry_index,
        field_name="byte_count",
        value=obj["byte_count"],
    )
    if file_basename == STAGE25_MANIFEST_FILENAME:
        if (
            sha256 != SELF_REFERENTIAL_MANIFEST_SHA256
            or byte_count != SELF_REFERENTIAL_MANIFEST_BYTE_COUNT
            or row_count != SELF_REFERENTIAL_MANIFEST_ROW_COUNT
        ):
            raise Stage26ManifestError(
                f"{basename} self-entry must carry the locked Stage 25 "
                "self-referential sentinel sha256 / byte_count / row_count",
                error_code=STG26_CAL_MANIFEST_HASH_SELF_INVALID,
            )
    return Stage25ManifestFileEntryInput(
        file_basename=file_basename,
        sha256=sha256,
        row_count=row_count,
        byte_count=byte_count,
    )


def _project_manifest(
    obj: Mapping[str, object],
) -> Stage25ManifestInput:
    basename = STAGE25_MANIFEST_FILENAME
    actual_keys = frozenset(obj.keys())
    missing = _MANIFEST_KEYS - actual_keys
    extra = actual_keys - _MANIFEST_KEYS
    if missing or extra:
        raise Stage26ManifestError(
            f"{basename}: manifest top-level keys must equal the locked "
            f"set. missing={sorted(missing)} extra={sorted(extra)}",
            error_code=STG26_CAL_MANIFEST_SCHEMA_INVALID,
        )
    files_raw = obj["files"]
    if not isinstance(files_raw, list):
        raise Stage26ManifestError(
            f"{basename}: top-level 'files' must be a JSON array, got "
            f"{type(files_raw).__name__}",
            error_code=STG26_CAL_MANIFEST_SCHEMA_INVALID,
        )
    entries: list[Stage25ManifestFileEntryInput] = []
    for index, raw_entry in enumerate(files_raw):
        if not isinstance(raw_entry, dict):
            raise Stage26ManifestError(
                f"{basename}: files[{index}] must be a JSON object, got "
                f"{type(raw_entry).__name__}",
                error_code=STG26_CAL_MANIFEST_SCHEMA_INVALID,
            )
        entries.append(
            _project_manifest_file_entry(
                entry_index=index,
                obj=raw_entry,
            )
        )
    raw_pin = obj["upstream_stage24_pin"]
    if raw_pin is None:
        pin: "Stage25Stage24ManifestPinInput | None" = None
    else:
        if not isinstance(raw_pin, dict):
            raise Stage26ManifestError(
                f"{basename}: upstream_stage24_pin must be null or a JSON "
                f"object, got {type(raw_pin).__name__}",
                error_code=STG26_CAL_MANIFEST_SCHEMA_INVALID,
            )
        pin_keys = frozenset(raw_pin.keys())
        missing_pin = _MANIFEST_UPSTREAM_PIN_KEYS - pin_keys
        extra_pin = pin_keys - _MANIFEST_UPSTREAM_PIN_KEYS
        if missing_pin or extra_pin:
            raise Stage26ManifestError(
                f"{basename}: upstream_stage24_pin keys must equal the "
                f"locked pair. missing={sorted(missing_pin)} "
                f"extra={sorted(extra_pin)}",
                error_code=STG26_CAL_MANIFEST_SCHEMA_INVALID,
            )
        upstream_basename_value = raw_pin["upstream_manifest_basename"]
        upstream_sha256_value = raw_pin["upstream_manifest_sha256"]
        if not isinstance(upstream_basename_value, str):
            raise Stage26ManifestError(
                f"{basename}: upstream_manifest_basename must be a string",
                error_code=STG26_CAL_MANIFEST_SCHEMA_INVALID,
            )
        if not isinstance(upstream_sha256_value, str):
            raise Stage26ManifestError(
                f"{basename}: upstream_manifest_sha256 must be a string",
                error_code=STG26_CAL_MANIFEST_SCHEMA_INVALID,
            )
        pin = Stage25Stage24ManifestPinInput(
            upstream_manifest_basename=upstream_basename_value,
            upstream_manifest_sha256=upstream_sha256_value,
        )
    for field_name in (
        "stage_name",
        "stage_version",
        "schema_version",
        "observe_only_mode",
        "redaction_confirmed",
        "manifest_kind",
        "created_at_utc",
        "runner_name",
        "runner_version",
        "writer_name",
        "writer_version",
    ):
        if not isinstance(obj[field_name], str):
            raise Stage26ManifestError(
                f"{basename}: {field_name!r} must be a string, got "
                f"{type(obj[field_name]).__name__}",
                error_code=STG26_CAL_MANIFEST_SCHEMA_INVALID,
            )
    return Stage25ManifestInput(
        stage_name=obj["stage_name"],  # type: ignore[arg-type]
        stage_version=obj["stage_version"],  # type: ignore[arg-type]
        schema_version=obj["schema_version"],  # type: ignore[arg-type]
        observe_only_mode=obj["observe_only_mode"],  # type: ignore[arg-type]
        redaction_confirmed=obj["redaction_confirmed"],  # type: ignore[arg-type]
        manifest_kind=obj["manifest_kind"],  # type: ignore[arg-type]
        files=tuple(entries),
        upstream_stage24_pin=pin,
        created_at_utc=obj["created_at_utc"],  # type: ignore[arg-type]
        runner_name=obj["runner_name"],  # type: ignore[arg-type]
        runner_version=obj["runner_version"],  # type: ignore[arg-type]
        writer_name=obj["writer_name"],  # type: ignore[arg-type]
        writer_version=obj["writer_version"],  # type: ignore[arg-type]
    )


def _require_int_count_mapping(
    *,
    artifact_basename: str,
    field_name: str,
    value: object,
) -> Mapping[str, int]:
    if not isinstance(value, dict):
        raise Stage26SchemaError(
            f"{artifact_basename}: field {field_name!r} must be a JSON "
            f"object, got {type(value).__name__}",
            error_code=STG26_CAL_ARTIFACT_SCHEMA_INVALID,
        )
    out: dict[str, int] = {}
    for key, item in value.items():
        if not isinstance(key, str):
            raise Stage26SchemaError(
                f"{artifact_basename}: field {field_name!r} has a "
                f"non-string key {key!r}",
                error_code=STG26_CAL_ARTIFACT_SCHEMA_INVALID,
            )
        if isinstance(item, bool) or not isinstance(item, int):
            raise Stage26SchemaError(
                f"{artifact_basename}: field {field_name!r}[{key!r}] must "
                f"be a strict int, got {type(item).__name__}",
                error_code=STG26_CAL_ARTIFACT_SCHEMA_INVALID,
            )
        out[key] = item
    return MappingProxyType(out)


def _project_summary(obj: Mapping[str, object]) -> Stage25SummaryInput:
    basename = STAGE25_SUMMARY_FILENAME
    actual_keys = frozenset(obj.keys())
    missing = _SUMMARY_KEYS - actual_keys
    extra = actual_keys - _SUMMARY_KEYS
    if missing or extra:
        raise Stage26SchemaError(
            f"{basename}: summary top-level keys must equal the locked "
            f"set. missing={sorted(missing)} extra={sorted(extra)}",
            error_code=STG26_CAL_ARTIFACT_SCHEMA_INVALID,
        )
    for str_field in (
        "stage_name",
        "stage_version",
        "schema_version",
        "summary_version",
        "observe_only_mode",
        "created_at_utc",
    ):
        if not isinstance(obj[str_field], str):
            raise Stage26SchemaError(
                f"{basename}: {str_field!r} must be a string",
                error_code=STG26_CAL_ARTIFACT_SCHEMA_INVALID,
            )
    observed_token_count = obj["observed_token_count"]
    if isinstance(observed_token_count, bool) or not isinstance(
        observed_token_count, int
    ):
        raise Stage26SchemaError(
            f"{basename}: observed_token_count must be a strict int",
            error_code=STG26_CAL_ARTIFACT_SCHEMA_INVALID,
        )
    count_field_names = (
        "row_counts",
        "migration_observation_source_family_counts",
        "migration_observation_source_status_counts",
        "migration_measurement_status_counts",
        "migration_measurement_confidence_counts",
        "migration_measurement_reconciliation_counts",
        "price_window_kind_counts",
        "price_window_source_status_counts",
        "ath_candidate_kind_counts",
        "ath_candidate_confidence_counts",
        "ath_candidate_source_family_counts",
        "ath_candidate_source_status_counts",
        "source_reconciliation_status_counts",
        "source_reconciliation_confidence_counts",
        "ath_measurement_status_counts",
        "ath_measurement_confidence_counts",
        "ath_measurement_reconciliation_counts",
        "rejection_reason_counts",
    )
    count_mappings: dict[str, Mapping[str, int]] = {}
    for field_name in count_field_names:
        count_mappings[field_name] = _require_int_count_mapping(
            artifact_basename=basename,
            field_name=field_name,
            value=obj[field_name],
        )
    return Stage25SummaryInput(
        stage_name=obj["stage_name"],  # type: ignore[arg-type]
        stage_version=obj["stage_version"],  # type: ignore[arg-type]
        schema_version=obj["schema_version"],  # type: ignore[arg-type]
        summary_version=obj["summary_version"],  # type: ignore[arg-type]
        observe_only_mode=obj["observe_only_mode"],  # type: ignore[arg-type]
        created_at_utc=obj["created_at_utc"],  # type: ignore[arg-type]
        observed_token_count=observed_token_count,
        row_counts=count_mappings["row_counts"],
        migration_observation_source_family_counts=count_mappings[
            "migration_observation_source_family_counts"
        ],
        migration_observation_source_status_counts=count_mappings[
            "migration_observation_source_status_counts"
        ],
        migration_measurement_status_counts=count_mappings[
            "migration_measurement_status_counts"
        ],
        migration_measurement_confidence_counts=count_mappings[
            "migration_measurement_confidence_counts"
        ],
        migration_measurement_reconciliation_counts=count_mappings[
            "migration_measurement_reconciliation_counts"
        ],
        price_window_kind_counts=count_mappings["price_window_kind_counts"],
        price_window_source_status_counts=count_mappings[
            "price_window_source_status_counts"
        ],
        ath_candidate_kind_counts=count_mappings["ath_candidate_kind_counts"],
        ath_candidate_confidence_counts=count_mappings[
            "ath_candidate_confidence_counts"
        ],
        ath_candidate_source_family_counts=count_mappings[
            "ath_candidate_source_family_counts"
        ],
        ath_candidate_source_status_counts=count_mappings[
            "ath_candidate_source_status_counts"
        ],
        source_reconciliation_status_counts=count_mappings[
            "source_reconciliation_status_counts"
        ],
        source_reconciliation_confidence_counts=count_mappings[
            "source_reconciliation_confidence_counts"
        ],
        ath_measurement_status_counts=count_mappings[
            "ath_measurement_status_counts"
        ],
        ath_measurement_confidence_counts=count_mappings[
            "ath_measurement_confidence_counts"
        ],
        ath_measurement_reconciliation_counts=count_mappings[
            "ath_measurement_reconciliation_counts"
        ],
        rejection_reason_counts=count_mappings["rejection_reason_counts"],
    )


# ---------------------------------------------------------------------------
# Public reader entrypoints
# ---------------------------------------------------------------------------


def _resolve_artifact_path(stage25_dir: Path, basename: str) -> Path:
    return stage25_dir / basename


def _require_file_present(path: Path, basename: str) -> None:
    if not path.exists():
        raise Stage26ReaderError(
            f"{basename}: required Stage 25 artifact not found at "
            f"{path.name!r}",
            error_code=STG26_CAL_ARTIFACT_MISSING_REQUIRED,
        )
    if not path.is_file():
        raise Stage26ReaderError(
            f"{basename}: path is not a regular file: {path.name!r}",
            error_code=STG26_CAL_ARTIFACT_MISSING_REQUIRED,
        )


def read_stage25_manifest(stage25_dir: Path) -> Stage25ManifestInput:
    """Read and project ``stage25_manifest.json``.

    Raises ``Stage26ManifestError`` if the manifest is missing,
    cannot be parsed, has the wrong top-level shape, or carries an
    invalid self-entry sentinel.
    """
    path = _resolve_artifact_path(stage25_dir, STAGE25_MANIFEST_FILENAME)
    if not path.exists():
        raise Stage26ManifestError(
            f"{STAGE25_MANIFEST_FILENAME}: Stage 25 manifest not found at "
            f"{path.name!r}",
            error_code=STG26_CAL_MANIFEST_NOT_FOUND,
        )
    if not path.is_file():
        raise Stage26ManifestError(
            f"{STAGE25_MANIFEST_FILENAME}: manifest path is not a regular "
            f"file: {path.name!r}",
            error_code=STG26_CAL_MANIFEST_NOT_FOUND,
        )
    data = _read_file_bytes(path)
    obj = _parse_json_bytes(
        artifact_basename=STAGE25_MANIFEST_FILENAME,
        data=data,
    )
    return _project_manifest(obj)


def read_stage25_summary(stage25_dir: Path) -> Stage25SummaryInput:
    """Read and project ``stage25_summary.json``."""
    path = _resolve_artifact_path(stage25_dir, STAGE25_SUMMARY_FILENAME)
    _require_file_present(path, STAGE25_SUMMARY_FILENAME)
    data = _read_file_bytes(path)
    obj = _parse_json_bytes(
        artifact_basename=STAGE25_SUMMARY_FILENAME,
        data=data,
    )
    return _project_summary(obj)


def _read_jsonl(
    *,
    stage25_dir: Path,
    basename: str,
) -> tuple[Mapping[str, object], ...]:
    path = _resolve_artifact_path(stage25_dir, basename)
    _require_file_present(path, basename)
    data = _read_file_bytes(path)
    return _project_jsonl_rows(artifact_basename=basename, data=data)


def read_migration_observations(
    stage25_dir: Path,
) -> tuple[MigrationObservationInput, ...]:
    rows = _read_jsonl(
        stage25_dir=stage25_dir,
        basename=STAGE25_MIGRATION_OBSERVATIONS_FILENAME,
    )
    return tuple(
        _project_migration_observation(record_index=index, obj=obj)
        for index, obj in enumerate(rows)
    )


def read_migration_measurements(
    stage25_dir: Path,
) -> tuple[MigrationMeasurementInput, ...]:
    rows = _read_jsonl(
        stage25_dir=stage25_dir,
        basename=STAGE25_MIGRATION_MEASUREMENTS_FILENAME,
    )
    return tuple(
        _project_migration_measurement(record_index=index, obj=obj)
        for index, obj in enumerate(rows)
    )


def read_price_window_observations(
    stage25_dir: Path,
) -> tuple[PriceWindowObservationInput, ...]:
    rows = _read_jsonl(
        stage25_dir=stage25_dir,
        basename=STAGE25_PRICE_WINDOW_OBSERVATIONS_FILENAME,
    )
    return tuple(
        _project_price_window_observation(record_index=index, obj=obj)
        for index, obj in enumerate(rows)
    )


def read_ath_candidates(
    stage25_dir: Path,
) -> tuple[ATHCandidateInput, ...]:
    rows = _read_jsonl(
        stage25_dir=stage25_dir,
        basename=STAGE25_ATH_CANDIDATES_FILENAME,
    )
    return tuple(
        _project_ath_candidate(record_index=index, obj=obj)
        for index, obj in enumerate(rows)
    )


def read_source_reconciliations(
    stage25_dir: Path,
) -> tuple[SourceReconciliationInput, ...]:
    rows = _read_jsonl(
        stage25_dir=stage25_dir,
        basename=STAGE25_SOURCE_RECONCILIATIONS_FILENAME,
    )
    return tuple(
        _project_source_reconciliation(record_index=index, obj=obj)
        for index, obj in enumerate(rows)
    )


def read_ath_measurements(
    stage25_dir: Path,
) -> tuple[ATHMeasurementInput, ...]:
    rows = _read_jsonl(
        stage25_dir=stage25_dir,
        basename=STAGE25_ATH_MEASUREMENTS_FILENAME,
    )
    return tuple(
        _project_ath_measurement(record_index=index, obj=obj)
        for index, obj in enumerate(rows)
    )


def read_measurement_rejections(
    stage25_dir: Path,
) -> tuple[MeasurementRejectionInput, ...]:
    rows = _read_jsonl(
        stage25_dir=stage25_dir,
        basename=STAGE25_MEASUREMENT_REJECTIONS_FILENAME,
    )
    return tuple(
        _project_measurement_rejection(record_index=index, obj=obj)
        for index, obj in enumerate(rows)
    )


__all__ = [
    "read_ath_candidates",
    "read_ath_measurements",
    "read_measurement_rejections",
    "read_migration_measurements",
    "read_migration_observations",
    "read_price_window_observations",
    "read_source_reconciliations",
    "read_stage25_manifest",
    "read_stage25_summary",
]

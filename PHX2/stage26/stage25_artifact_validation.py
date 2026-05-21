"""Stage 26.1 Stage 25 artifact-set validator.

The validator inspects every file the Stage 25 manifest declares and
emits a structured ``ArtifactValidationReport``. The validator NEVER
mutates a Stage 25 artifact, NEVER decides denominator inclusion /
exclusion, NEVER labels a row as "bad outcome", and NEVER corrects
a Stage 25 measurement-truth token. It reports validation FACTS
only.

The validator surfaces:

  * manifest-level validation (manifest present, schema, redaction
    token, observe-only mode, self-entry sentinel);
  * per-file byte-level validation (file present, sha256 match,
    byte_count match, row_count match for JSONL artifacts);
  * per-file row-level schema validation (each row projects
    successfully via the Stage 26.1 reader's per-row projector).

Manifest-level failures that prevent any per-file validation from
running (e.g. manifest missing entirely) are raised as
``Stage26ManifestError``. Per-file failures are captured as
``ArtifactValidationEntry`` records in the returned report.
"""

from __future__ import annotations

from pathlib import Path

from PHX2.stage26.constants import (
    ARTIFACT_VALIDATION_STATUS_FILE_MISSING,
    ARTIFACT_VALIDATION_STATUS_FILE_NOT_REGULAR,
    ARTIFACT_VALIDATION_STATUS_MANIFEST_BYTE_COUNT_MISMATCH,
    ARTIFACT_VALIDATION_STATUS_MANIFEST_HASH_MISMATCH,
    ARTIFACT_VALIDATION_STATUS_MANIFEST_ROW_COUNT_MISMATCH,
    ARTIFACT_VALIDATION_STATUS_RECORD_NULL_AS_ZERO_VIOLATION,
    ARTIFACT_VALIDATION_STATUS_RECORD_SCHEMA_INVALID,
    ARTIFACT_VALIDATION_STATUS_RECORD_TRUTH_CLASS_INVALID,
    ARTIFACT_VALIDATION_STATUS_SCHEMA_INVALID,
    ARTIFACT_VALIDATION_STATUS_VALIDATED,
    STG26_CAL_ARTIFACT_BYTE_COUNT_MISMATCH,
    STG26_CAL_ARTIFACT_HASH_MISMATCH,
    STG26_CAL_ARTIFACT_MISSING_REQUIRED,
    STG26_CAL_ARTIFACT_ROW_COUNT_MISMATCH,
    STG26_CAL_MANIFEST_SCHEMA_INVALID,
)
from PHX2.stage26.errors import (
    Stage26ManifestError,
    Stage26SchemaError,
)
from PHX2.stage26.models import (
    ArtifactValidationEntry,
    ArtifactValidationReport,
    Stage25ManifestInput,
)
from PHX2.stage26.stage25_artifact_reader import (
    _count_non_blank_lines,
    _parse_json_bytes,
    _project_ath_candidate,
    _project_ath_measurement,
    _project_jsonl_rows,
    _project_measurement_rejection,
    _project_migration_measurement,
    _project_migration_observation,
    _project_price_window_observation,
    _project_source_reconciliation,
    _project_summary,
    _read_file_bytes,
    _sha256_of_bytes,
    read_stage25_manifest,
)
from PHX2.stage26.stage25_schema_whitelist import (
    OBSERVE_ONLY_MODE,
    REDACTION_CONFIRMED_TOKEN,
    SELF_REFERENTIAL_MANIFEST_BYTE_COUNT,
    SELF_REFERENTIAL_MANIFEST_ROW_COUNT,
    SELF_REFERENTIAL_MANIFEST_SHA256,
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


# Required artifacts that the manifest MUST declare. The reader treats
# the manifest as authoritative -- if the manifest does not declare a
# basename here, the validator records a manifest-schema entry.
_REQUIRED_ARTIFACT_BASENAMES: tuple[str, ...] = (
    STAGE25_MIGRATION_OBSERVATIONS_FILENAME,
    STAGE25_MIGRATION_MEASUREMENTS_FILENAME,
    STAGE25_PRICE_WINDOW_OBSERVATIONS_FILENAME,
    STAGE25_ATH_CANDIDATES_FILENAME,
    STAGE25_SOURCE_RECONCILIATIONS_FILENAME,
    STAGE25_ATH_MEASUREMENTS_FILENAME,
    STAGE25_MEASUREMENT_REJECTIONS_FILENAME,
    STAGE25_SUMMARY_FILENAME,
    STAGE25_MANIFEST_FILENAME,
)


# Per-row projector dispatch table (only artifacts whose rows we project).
def _project_jsonl_rows_for_artifact(
    *,
    artifact_basename: str,
    data: bytes,
) -> None:
    rows = _project_jsonl_rows(
        artifact_basename=artifact_basename,
        data=data,
    )
    if artifact_basename == STAGE25_MIGRATION_OBSERVATIONS_FILENAME:
        for index, obj in enumerate(rows):
            _project_migration_observation(record_index=index, obj=obj)
    elif artifact_basename == STAGE25_MIGRATION_MEASUREMENTS_FILENAME:
        for index, obj in enumerate(rows):
            _project_migration_measurement(record_index=index, obj=obj)
    elif artifact_basename == STAGE25_PRICE_WINDOW_OBSERVATIONS_FILENAME:
        for index, obj in enumerate(rows):
            _project_price_window_observation(
                record_index=index, obj=obj
            )
    elif artifact_basename == STAGE25_ATH_CANDIDATES_FILENAME:
        for index, obj in enumerate(rows):
            _project_ath_candidate(record_index=index, obj=obj)
    elif artifact_basename == STAGE25_SOURCE_RECONCILIATIONS_FILENAME:
        for index, obj in enumerate(rows):
            _project_source_reconciliation(record_index=index, obj=obj)
    elif artifact_basename == STAGE25_ATH_MEASUREMENTS_FILENAME:
        for index, obj in enumerate(rows):
            _project_ath_measurement(record_index=index, obj=obj)
    elif artifact_basename == STAGE25_MEASUREMENT_REJECTIONS_FILENAME:
        for index, obj in enumerate(rows):
            _project_measurement_rejection(record_index=index, obj=obj)


# ---------------------------------------------------------------------------
# Validation entries
# ---------------------------------------------------------------------------


def _validated_entry(artifact_basename: str) -> ArtifactValidationEntry:
    return ArtifactValidationEntry(
        artifact_basename=artifact_basename,
        status=ARTIFACT_VALIDATION_STATUS_VALIDATED,
        detail="",
        error_code="",
    )


def _status_for_schema_error(error_code: str) -> str:
    if error_code == "STG26_CAL_RECORD_TRUTH_CLASS_INVALID":
        return ARTIFACT_VALIDATION_STATUS_RECORD_TRUTH_CLASS_INVALID
    if error_code == "STG26_CAL_RECORD_NULL_AS_ZERO_VIOLATION":
        return ARTIFACT_VALIDATION_STATUS_RECORD_NULL_AS_ZERO_VIOLATION
    if error_code == "STG26_CAL_RECORD_SCHEMA_INVALID":
        return ARTIFACT_VALIDATION_STATUS_RECORD_SCHEMA_INVALID
    return ARTIFACT_VALIDATION_STATUS_SCHEMA_INVALID


def _validate_jsonl_artifact(
    *,
    stage25_dir: Path,
    artifact_basename: str,
    declared_sha256: str,
    declared_row_count: int,
    declared_byte_count: int,
) -> ArtifactValidationEntry:
    path = stage25_dir / artifact_basename
    if not path.exists():
        return ArtifactValidationEntry(
            artifact_basename=artifact_basename,
            status=ARTIFACT_VALIDATION_STATUS_FILE_MISSING,
            detail=f"{artifact_basename}: not found on disk",
            error_code=STG26_CAL_ARTIFACT_MISSING_REQUIRED,
        )
    if not path.is_file():
        return ArtifactValidationEntry(
            artifact_basename=artifact_basename,
            status=ARTIFACT_VALIDATION_STATUS_FILE_NOT_REGULAR,
            detail=f"{artifact_basename}: path is not a regular file",
            error_code=STG26_CAL_ARTIFACT_MISSING_REQUIRED,
        )
    data = _read_file_bytes(path)
    actual_byte_count = len(data)
    if actual_byte_count != declared_byte_count:
        return ArtifactValidationEntry(
            artifact_basename=artifact_basename,
            status=ARTIFACT_VALIDATION_STATUS_MANIFEST_BYTE_COUNT_MISMATCH,
            detail=(
                f"{artifact_basename}: declared byte_count "
                f"{declared_byte_count} != actual {actual_byte_count}"
            ),
            error_code=STG26_CAL_ARTIFACT_BYTE_COUNT_MISMATCH,
        )
    actual_sha256 = _sha256_of_bytes(data)
    if actual_sha256 != declared_sha256:
        return ArtifactValidationEntry(
            artifact_basename=artifact_basename,
            status=ARTIFACT_VALIDATION_STATUS_MANIFEST_HASH_MISMATCH,
            detail=(
                f"{artifact_basename}: declared sha256 != actual sha256"
            ),
            error_code=STG26_CAL_ARTIFACT_HASH_MISMATCH,
        )
    actual_row_count = _count_non_blank_lines(data)
    if actual_row_count != declared_row_count:
        return ArtifactValidationEntry(
            artifact_basename=artifact_basename,
            status=ARTIFACT_VALIDATION_STATUS_MANIFEST_ROW_COUNT_MISMATCH,
            detail=(
                f"{artifact_basename}: declared row_count "
                f"{declared_row_count} != actual {actual_row_count}"
            ),
            error_code=STG26_CAL_ARTIFACT_ROW_COUNT_MISMATCH,
        )
    try:
        _project_jsonl_rows_for_artifact(
            artifact_basename=artifact_basename,
            data=data,
        )
    except Stage26SchemaError as exc:
        return ArtifactValidationEntry(
            artifact_basename=artifact_basename,
            status=_status_for_schema_error(exc.error_code),
            detail=str(exc),
            error_code=exc.error_code,
        )
    return _validated_entry(artifact_basename)


def _validate_summary_artifact(
    *,
    stage25_dir: Path,
    declared_sha256: str,
    declared_byte_count: int,
) -> ArtifactValidationEntry:
    path = stage25_dir / STAGE25_SUMMARY_FILENAME
    if not path.exists():
        return ArtifactValidationEntry(
            artifact_basename=STAGE25_SUMMARY_FILENAME,
            status=ARTIFACT_VALIDATION_STATUS_FILE_MISSING,
            detail=f"{STAGE25_SUMMARY_FILENAME}: not found on disk",
            error_code=STG26_CAL_ARTIFACT_MISSING_REQUIRED,
        )
    if not path.is_file():
        return ArtifactValidationEntry(
            artifact_basename=STAGE25_SUMMARY_FILENAME,
            status=ARTIFACT_VALIDATION_STATUS_FILE_NOT_REGULAR,
            detail=f"{STAGE25_SUMMARY_FILENAME}: path is not a regular file",
            error_code=STG26_CAL_ARTIFACT_MISSING_REQUIRED,
        )
    data = _read_file_bytes(path)
    actual_byte_count = len(data)
    if actual_byte_count != declared_byte_count:
        return ArtifactValidationEntry(
            artifact_basename=STAGE25_SUMMARY_FILENAME,
            status=ARTIFACT_VALIDATION_STATUS_MANIFEST_BYTE_COUNT_MISMATCH,
            detail=(
                f"{STAGE25_SUMMARY_FILENAME}: declared byte_count "
                f"{declared_byte_count} != actual {actual_byte_count}"
            ),
            error_code=STG26_CAL_ARTIFACT_BYTE_COUNT_MISMATCH,
        )
    actual_sha256 = _sha256_of_bytes(data)
    if actual_sha256 != declared_sha256:
        return ArtifactValidationEntry(
            artifact_basename=STAGE25_SUMMARY_FILENAME,
            status=ARTIFACT_VALIDATION_STATUS_MANIFEST_HASH_MISMATCH,
            detail=(
                f"{STAGE25_SUMMARY_FILENAME}: declared sha256 != actual "
                "sha256"
            ),
            error_code=STG26_CAL_ARTIFACT_HASH_MISMATCH,
        )
    try:
        obj = _parse_json_bytes(
            artifact_basename=STAGE25_SUMMARY_FILENAME,
            data=data,
        )
        _project_summary(obj)
    except Stage26SchemaError as exc:
        return ArtifactValidationEntry(
            artifact_basename=STAGE25_SUMMARY_FILENAME,
            status=_status_for_schema_error(exc.error_code),
            detail=str(exc),
            error_code=exc.error_code,
        )
    return _validated_entry(STAGE25_SUMMARY_FILENAME)


def _validate_manifest_self_entry(
    manifest: Stage25ManifestInput,
) -> ArtifactValidationEntry:
    self_entry = None
    for entry in manifest.files:
        if entry.file_basename == STAGE25_MANIFEST_FILENAME:
            self_entry = entry
            break
    if self_entry is None:
        return ArtifactValidationEntry(
            artifact_basename=STAGE25_MANIFEST_FILENAME,
            status=ARTIFACT_VALIDATION_STATUS_SCHEMA_INVALID,
            detail=(
                f"{STAGE25_MANIFEST_FILENAME}: manifest does not list "
                "itself as a file entry"
            ),
            error_code=STG26_CAL_MANIFEST_SCHEMA_INVALID,
        )
    if (
        self_entry.sha256 != SELF_REFERENTIAL_MANIFEST_SHA256
        or self_entry.byte_count != SELF_REFERENTIAL_MANIFEST_BYTE_COUNT
        or self_entry.row_count != SELF_REFERENTIAL_MANIFEST_ROW_COUNT
    ):
        return ArtifactValidationEntry(
            artifact_basename=STAGE25_MANIFEST_FILENAME,
            status=ARTIFACT_VALIDATION_STATUS_SCHEMA_INVALID,
            detail=(
                f"{STAGE25_MANIFEST_FILENAME}: self-entry must carry the "
                "locked sentinel sha256 / byte_count / row_count"
            ),
            error_code=STG26_CAL_MANIFEST_SCHEMA_INVALID,
        )
    return _validated_entry(STAGE25_MANIFEST_FILENAME)


def _validate_manifest_tokens(
    manifest: Stage25ManifestInput,
) -> ArtifactValidationEntry:
    if manifest.observe_only_mode != OBSERVE_ONLY_MODE:
        return ArtifactValidationEntry(
            artifact_basename=STAGE25_MANIFEST_FILENAME,
            status=ARTIFACT_VALIDATION_STATUS_SCHEMA_INVALID,
            detail=(
                f"{STAGE25_MANIFEST_FILENAME}: observe_only_mode must equal "
                f"the locked Stage 25 token {OBSERVE_ONLY_MODE!r}"
            ),
            error_code=STG26_CAL_MANIFEST_SCHEMA_INVALID,
        )
    if manifest.redaction_confirmed not in (
        "",
        REDACTION_CONFIRMED_TOKEN,
    ):
        return ArtifactValidationEntry(
            artifact_basename=STAGE25_MANIFEST_FILENAME,
            status=ARTIFACT_VALIDATION_STATUS_SCHEMA_INVALID,
            detail=(
                f"{STAGE25_MANIFEST_FILENAME}: redaction_confirmed must be "
                "the locked token or the empty string"
            ),
            error_code=STG26_CAL_MANIFEST_SCHEMA_INVALID,
        )
    if manifest.manifest_kind != "artifact":
        return ArtifactValidationEntry(
            artifact_basename=STAGE25_MANIFEST_FILENAME,
            status=ARTIFACT_VALIDATION_STATUS_SCHEMA_INVALID,
            detail=(
                f"{STAGE25_MANIFEST_FILENAME}: manifest_kind must equal "
                "'artifact' for a Stage 25 artifact manifest"
            ),
            error_code=STG26_CAL_MANIFEST_SCHEMA_INVALID,
        )
    return _validated_entry(STAGE25_MANIFEST_FILENAME)


def _check_manifest_declares_required(
    manifest: Stage25ManifestInput,
) -> tuple[ArtifactValidationEntry, ...]:
    declared = {entry.file_basename for entry in manifest.files}
    missing_entries: list[ArtifactValidationEntry] = []
    for required in _REQUIRED_ARTIFACT_BASENAMES:
        if required not in declared:
            missing_entries.append(
                ArtifactValidationEntry(
                    artifact_basename=required,
                    status=ARTIFACT_VALIDATION_STATUS_SCHEMA_INVALID,
                    detail=(
                        f"{required}: required artifact not declared in "
                        f"{STAGE25_MANIFEST_FILENAME}"
                    ),
                    error_code=STG26_CAL_MANIFEST_SCHEMA_INVALID,
                )
            )
    return tuple(missing_entries)


def validate_stage25_artifact_set(
    stage25_dir: Path,
) -> ArtifactValidationReport:
    """Validate every Stage 25 artifact the manifest declares.

    Returns an ``ArtifactValidationReport``. Raises
    ``Stage26ManifestError`` if the manifest itself cannot be loaded.
    Per-file failures are captured as report entries; the validator
    NEVER raises on a per-file failure.
    """
    manifest = read_stage25_manifest(stage25_dir)

    entries: list[ArtifactValidationEntry] = []

    tokens_entry = _validate_manifest_tokens(manifest)
    self_entry_entry = _validate_manifest_self_entry(manifest)
    required_entries = _check_manifest_declares_required(manifest)

    by_basename: dict[str, ArtifactValidationEntry] = {}

    if tokens_entry.status != ARTIFACT_VALIDATION_STATUS_VALIDATED:
        by_basename[tokens_entry.artifact_basename] = tokens_entry
    if self_entry_entry.status != ARTIFACT_VALIDATION_STATUS_VALIDATED:
        by_basename.setdefault(
            self_entry_entry.artifact_basename, self_entry_entry
        )

    for entry in required_entries:
        by_basename.setdefault(entry.artifact_basename, entry)

    for file_entry in manifest.files:
        basename = file_entry.file_basename
        if basename in by_basename:
            continue
        if basename == STAGE25_MANIFEST_FILENAME:
            by_basename[basename] = _validated_entry(basename)
            continue
        if basename == STAGE25_SUMMARY_FILENAME:
            by_basename[basename] = _validate_summary_artifact(
                stage25_dir=stage25_dir,
                declared_sha256=file_entry.sha256,
                declared_byte_count=file_entry.byte_count,
            )
            continue
        if basename in _REQUIRED_ARTIFACT_BASENAMES and basename.endswith(
            ".jsonl"
        ):
            by_basename[basename] = _validate_jsonl_artifact(
                stage25_dir=stage25_dir,
                artifact_basename=basename,
                declared_sha256=file_entry.sha256,
                declared_row_count=file_entry.row_count,
                declared_byte_count=file_entry.byte_count,
            )
            continue
        # Manifest declared a basename Stage 26.1 does not recognize.
        by_basename[basename] = ArtifactValidationEntry(
            artifact_basename=basename,
            status=ARTIFACT_VALIDATION_STATUS_SCHEMA_INVALID,
            detail=(
                f"{basename}: manifest declares a Stage 25 artifact "
                "basename Stage 26.1 does not recognize"
            ),
            error_code=STG26_CAL_MANIFEST_SCHEMA_INVALID,
        )

    for basename in _REQUIRED_ARTIFACT_BASENAMES:
        if basename in by_basename:
            entries.append(by_basename[basename])
        else:
            # Manifest did not declare the required artifact; the
            # missing-required entry was added above. This branch is
            # defensive -- it ensures every required basename appears
            # exactly once in the final report.
            entries.append(
                ArtifactValidationEntry(
                    artifact_basename=basename,
                    status=ARTIFACT_VALIDATION_STATUS_SCHEMA_INVALID,
                    detail=(
                        f"{basename}: required artifact missing from "
                        "manifest"
                    ),
                    error_code=STG26_CAL_MANIFEST_SCHEMA_INVALID,
                )
            )

    ok = all(
        entry.status == ARTIFACT_VALIDATION_STATUS_VALIDATED
        for entry in entries
    )
    return ArtifactValidationReport(entries=tuple(entries), ok=ok)


__all__ = [
    "Stage26ManifestError",
    "validate_stage25_artifact_set",
]

"""Stage 26.1 calibration-input contracts (high-level orchestrator).

Public entrypoints:

  * ``load_stage25_artifact_set(stage25_dir) -> Stage25ArtifactSet``
    Read-only load of every Stage 25 artifact the manifest declares
    into typed Stage 26.1 input records. Raises
    ``Stage26ValidationError`` if the validator's report contains any
    non-``VALIDATED`` entry; raises ``Stage26ManifestError`` if the
    manifest itself cannot be loaded.

  * ``load_stage26_calibration_input_set(stage25_dir)
        -> Stage26CalibrationInputSet``
    Wraps ``load_stage25_artifact_set`` with the Stage 26.1
    calibration-input version axis. Returns the high-level
    ``Stage26CalibrationInputSet`` bundle Stage 26.2+ will consume.

Both entrypoints:

  * NEVER write to a Stage 25 artifact file.
  * NEVER mutate a Stage 25 artifact file's mtime / atime.
  * NEVER assign a denominator-eligibility decision to a row.
  * NEVER build a calibration cohort.
  * NEVER generate a threshold or policy candidate.
  * NEVER read the process environment.
  * NEVER open a network / DB / messaging connection.
  * NEVER define a CLI entrypoint.

The orchestrator pins the consumed Stage 25 manifest by
``(basename, sha256)`` only -- a Stage 26 / Stage 25 convention
mirror of the Stage 24 / Stage 25 pin discipline. Downstream Stage
26.x sub-stages carry the pin forward verbatim.
"""

from __future__ import annotations

from pathlib import Path

from PHX2.stage26.constants import (
    STAGE26_CALIBRATION_INPUT_VERSION,
    STG26_CAL_ARTIFACT_SCHEMA_INVALID,
)
from PHX2.stage26.errors import Stage26ValidationError
from PHX2.stage26.models import (
    Stage25ArtifactReference,
    Stage25ArtifactSet,
    Stage26CalibrationInputSet,
    Stage26ReaderResult,
)
from PHX2.stage26.stage25_artifact_reader import (
    _read_file_bytes,
    _sha256_of_bytes,
    read_ath_candidates,
    read_ath_measurements,
    read_measurement_rejections,
    read_migration_measurements,
    read_migration_observations,
    read_price_window_observations,
    read_source_reconciliations,
    read_stage25_manifest,
    read_stage25_summary,
)
from PHX2.stage26.stage25_artifact_validation import (
    validate_stage25_artifact_set,
)
from PHX2.stage26.stage25_schema_whitelist import (
    SELF_REFERENTIAL_MANIFEST_SHA256,
    STAGE25_MANIFEST_FILENAME,
)


def _compute_manifest_pin(
    stage25_dir: Path,
) -> Stage25ArtifactReference:
    """Compute the ``(basename, sha256)`` pin for the Stage 25 manifest.

    The validator has already verified the manifest exists and parses;
    this helper opens the bytes and computes the live sha256. The
    manifest self-entry's sentinel sha256 is the locked Stage 25
    write-time convention; the pin uses the live digest of the
    actual on-disk bytes.
    """
    path = stage25_dir / STAGE25_MANIFEST_FILENAME
    data = _read_file_bytes(path)
    return Stage25ArtifactReference(
        artifact_basename=STAGE25_MANIFEST_FILENAME,
        artifact_sha256=_sha256_of_bytes(data),
    )


def _per_artifact_pins(
    *,
    stage25_dir: Path,
    file_entries: tuple[object, ...],
) -> tuple[Stage25ArtifactReference, ...]:
    """Build per-artifact (basename, sha256) pins from manifest entries.

    The Stage 25 manifest self-entry's sha256 is the locked sentinel;
    Stage 26.1 records that pin verbatim (the sentinel is NOT
    promoted to a live digest, since the live manifest digest is
    captured separately on ``Stage25ArtifactSet.stage25_manifest_pin``).
    """
    pins: list[Stage25ArtifactReference] = []
    for entry in file_entries:
        basename = entry.file_basename  # type: ignore[attr-defined]
        sha256 = entry.sha256  # type: ignore[attr-defined]
        pins.append(
            Stage25ArtifactReference(
                artifact_basename=basename,
                artifact_sha256=sha256,
            )
        )
    # Stable order: lexicographic by basename.
    pins.sort(key=lambda pin: pin.artifact_basename)
    return tuple(pins)


def load_stage25_artifact_set(
    stage25_dir: Path,
) -> Stage25ArtifactSet:
    """Load and validate the complete Stage 25 artifact set.

    Internally:

      1. Calls ``validate_stage25_artifact_set``. Raises
         ``Stage26ValidationError`` (carrying the report) if any
         entry is non-``VALIDATED``.
      2. Re-reads each artifact via the per-artifact ``read_*``
         functions to assemble the typed bundle.
      3. Records the Stage 25 manifest pin as
         ``(basename, sha256)`` only (mirror of the Stage 24 / Stage
         25 pin convention).

    The function is deterministic: identical Stage 25 directories
    produce equal ``Stage25ArtifactSet`` instances.
    """
    report = validate_stage25_artifact_set(stage25_dir)
    if not report.ok:
        raise Stage26ValidationError(
            (
                "Stage 26.1 validation rejected the Stage 25 artifact "
                "set; see report for per-artifact entries"
            ),
            error_code=STG26_CAL_ARTIFACT_SCHEMA_INVALID,
            report=report,
        )

    manifest = read_stage25_manifest(stage25_dir)
    summary = read_stage25_summary(stage25_dir)
    migration_observations = read_migration_observations(stage25_dir)
    migration_measurements = read_migration_measurements(stage25_dir)
    price_window_observations = read_price_window_observations(stage25_dir)
    ath_candidates = read_ath_candidates(stage25_dir)
    source_reconciliations = read_source_reconciliations(stage25_dir)
    ath_measurements = read_ath_measurements(stage25_dir)
    measurement_rejections = read_measurement_rejections(stage25_dir)

    manifest_pin = _compute_manifest_pin(stage25_dir)
    per_artifact_pin_tuple = _per_artifact_pins(
        stage25_dir=stage25_dir,
        file_entries=manifest.files,
    )

    return Stage25ArtifactSet(
        manifest=manifest,
        summary=summary,
        migration_observations=migration_observations,
        migration_measurements=migration_measurements,
        price_window_observations=price_window_observations,
        ath_candidates=ath_candidates,
        source_reconciliations=source_reconciliations,
        ath_measurements=ath_measurements,
        measurement_rejections=measurement_rejections,
        stage25_manifest_pin=manifest_pin,
        per_artifact_pins=per_artifact_pin_tuple,
    )


def load_stage26_calibration_input_set(
    stage25_dir: Path,
) -> Stage26CalibrationInputSet:
    """Load a complete Stage 26.1 calibration-input bundle.

    Wraps the validated, typed Stage 25 artifact set with the Stage
    26.1 calibration-input version axis and the live Stage 25
    manifest pin. Returns the immutable
    ``Stage26CalibrationInputSet`` bundle Stage 26.2+ will consume.
    """
    report = validate_stage25_artifact_set(stage25_dir)
    if not report.ok:
        raise Stage26ValidationError(
            (
                "Stage 26.1 validation rejected the Stage 25 artifact "
                "set; see report for per-artifact entries"
            ),
            error_code=STG26_CAL_ARTIFACT_SCHEMA_INVALID,
            report=report,
        )
    artifact_set = load_stage25_artifact_set(stage25_dir)
    reader_result = Stage26ReaderResult(
        artifact_set=artifact_set,
        validation_report=report,
    )
    # The manifest pin on the bundle mirrors the live (basename,
    # sha256) computed at load time. The pin on the inner
    # artifact_set is the same value; it is recorded on the outer
    # bundle for the locked Stage 26.1 contract surface so Stage
    # 26.x consumers do not need to walk inside the reader_result
    # to find the upstream pin.
    return Stage26CalibrationInputSet(
        stage26_calibration_input_version=STAGE26_CALIBRATION_INPUT_VERSION,
        stage25_manifest_pin=artifact_set.stage25_manifest_pin,
        reader_result=reader_result,
    )


# Sanity check: the live Stage 25 manifest pin must not coincidentally
# equal the locked self-referential sentinel string. The Stage 25
# closure-audit test asserts the sentinel is not a 64-char lowercase
# hex digest, so a real sha256 digest never equals the sentinel; this
# helper is exposed for downstream code that wants to assert the
# invariant locally.
def manifest_pin_is_live_digest(
    pin: Stage25ArtifactReference,
) -> bool:
    """Return ``True`` iff ``pin.artifact_sha256`` is a real digest.

    "Real digest" means: 64-character lowercase hex string and not
    equal to the locked Stage 25 self-referential sentinel. Useful
    for callers that want to assert the live manifest pin was
    computed from on-disk bytes rather than carried over from the
    self-entry sentinel.
    """
    sha = pin.artifact_sha256
    if sha == SELF_REFERENTIAL_MANIFEST_SHA256:
        return False
    if len(sha) != 64:
        return False
    return all(ch in "0123456789abcdef" for ch in sha)


__all__ = [
    "load_stage25_artifact_set",
    "load_stage26_calibration_input_set",
    "manifest_pin_is_live_digest",
]

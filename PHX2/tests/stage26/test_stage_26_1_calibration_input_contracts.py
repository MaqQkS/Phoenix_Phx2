"""Stage 26.1 calibration-input contracts orchestrator tests."""

from __future__ import annotations

import pytest

from PHX2.stage25.constants import (
    STAGE25_ATH_CANDIDATES_FILENAME,
    STAGE25_MANIFEST_FILENAME,
)
from PHX2.stage26.calibration_input_contracts import (
    load_stage25_artifact_set,
    load_stage26_calibration_input_set,
    manifest_pin_is_live_digest,
)
from PHX2.stage26.constants import (
    STAGE26_CALIBRATION_INPUT_VERSION,
)
from PHX2.stage26.errors import (
    Stage26ManifestError,
    Stage26ValidationError,
)
from PHX2.stage26.models import (
    Stage25ArtifactReference,
    Stage25ArtifactSet,
    Stage26CalibrationInputSet,
    Stage26ReaderResult,
)
from PHX2.tests.stage26.fixtures.builders import (
    SELF_REFERENTIAL_MANIFEST_SHA256,
    write_default_valid_stage25_dir,
    write_empty_stage25_dir,
    write_stage25_dir,
)


def _default_payloads() -> dict[str, bytes]:
    from PHX2.tests.stage26.fixtures.builders import (
        _default_artifact_payloads,
    )

    return _default_artifact_payloads()


def test_load_artifact_set_returns_typed_bundle(tmp_path):
    stage25_dir = write_default_valid_stage25_dir(tmp_path)
    artifact_set = load_stage25_artifact_set(stage25_dir)
    assert isinstance(artifact_set, Stage25ArtifactSet)
    assert artifact_set.manifest.stage_name == "stage25"
    assert artifact_set.summary.stage_name == "stage25"


def test_load_artifact_set_pins_manifest_by_basename_and_sha256(tmp_path):
    stage25_dir = write_default_valid_stage25_dir(tmp_path)
    artifact_set = load_stage25_artifact_set(stage25_dir)
    pin = artifact_set.stage25_manifest_pin
    assert isinstance(pin, Stage25ArtifactReference)
    assert pin.artifact_basename == STAGE25_MANIFEST_FILENAME
    assert manifest_pin_is_live_digest(pin) is True
    # The pin is the LIVE digest, not the self-referential sentinel.
    assert pin.artifact_sha256 != SELF_REFERENTIAL_MANIFEST_SHA256
    # Sanity: also a 64-char hex digest.
    assert len(pin.artifact_sha256) == 64


def test_load_artifact_set_records_per_artifact_pins(tmp_path):
    stage25_dir = write_default_valid_stage25_dir(tmp_path)
    artifact_set = load_stage25_artifact_set(stage25_dir)
    # One pin per manifest entry, sorted by basename.
    basenames = [pin.artifact_basename for pin in artifact_set.per_artifact_pins]
    assert basenames == sorted(basenames)
    assert len(basenames) == 9


def test_load_artifact_set_raises_validation_error_on_bad_dir(tmp_path):
    stage25_dir = write_default_valid_stage25_dir(tmp_path)
    (stage25_dir / STAGE25_ATH_CANDIDATES_FILENAME).unlink()
    with pytest.raises(Stage26ValidationError) as exc_info:
        load_stage25_artifact_set(stage25_dir)
    # The error carries the report so callers can inspect.
    assert exc_info.value.report is not None
    assert exc_info.value.error_code.startswith("STG26_CAL_")


def test_load_artifact_set_is_deterministic_across_repeated_loads(tmp_path):
    stage25_dir = write_default_valid_stage25_dir(tmp_path)
    first = load_stage25_artifact_set(stage25_dir)
    second = load_stage25_artifact_set(stage25_dir)
    assert first == second, (
        "Stage 26.1 load_stage25_artifact_set must be deterministic across "
        "repeated invocations"
    )


def test_load_artifact_set_does_not_mutate_artifact_mtimes(tmp_path):
    stage25_dir = write_default_valid_stage25_dir(tmp_path)
    mtimes_before = {
        p.name: p.stat().st_mtime_ns for p in stage25_dir.iterdir()
    }
    load_stage25_artifact_set(stage25_dir)
    mtimes_after = {
        p.name: p.stat().st_mtime_ns for p in stage25_dir.iterdir()
    }
    assert mtimes_before == mtimes_after


def test_load_calibration_input_set_wraps_with_version_axis(tmp_path):
    stage25_dir = write_default_valid_stage25_dir(tmp_path)
    bundle = load_stage26_calibration_input_set(stage25_dir)
    assert isinstance(bundle, Stage26CalibrationInputSet)
    assert (
        bundle.stage26_calibration_input_version
        == STAGE26_CALIBRATION_INPUT_VERSION
    )
    assert isinstance(bundle.reader_result, Stage26ReaderResult)
    assert isinstance(bundle.reader_result.artifact_set, Stage25ArtifactSet)
    # The outer-bundle pin and the inner artifact-set pin agree.
    assert bundle.stage25_manifest_pin == (
        bundle.reader_result.artifact_set.stage25_manifest_pin
    )


def test_load_calibration_input_set_includes_validation_report(tmp_path):
    stage25_dir = write_default_valid_stage25_dir(tmp_path)
    bundle = load_stage26_calibration_input_set(stage25_dir)
    report = bundle.reader_result.validation_report
    assert report.ok is True


def test_load_calibration_input_set_raises_on_invalid_dir(tmp_path):
    stage25_dir = tmp_path / "stage25"
    stage25_dir.mkdir()
    with pytest.raises(Stage26ManifestError):
        load_stage26_calibration_input_set(stage25_dir)


def test_load_handles_empty_stage25_dir_with_zero_row_counts(tmp_path):
    stage25_dir = write_empty_stage25_dir(tmp_path)
    artifact_set = load_stage25_artifact_set(stage25_dir)
    assert artifact_set.migration_observations == ()
    assert artifact_set.ath_measurements == ()


def test_manifest_pin_is_live_digest_rejects_sentinel_and_non_hex():
    pin_sentinel = Stage25ArtifactReference(
        artifact_basename=STAGE25_MANIFEST_FILENAME,
        artifact_sha256=SELF_REFERENTIAL_MANIFEST_SHA256,
    )
    assert manifest_pin_is_live_digest(pin_sentinel) is False
    pin_short = Stage25ArtifactReference(
        artifact_basename=STAGE25_MANIFEST_FILENAME,
        artifact_sha256="abc",
    )
    assert manifest_pin_is_live_digest(pin_short) is False
    pin_upper = Stage25ArtifactReference(
        artifact_basename=STAGE25_MANIFEST_FILENAME,
        artifact_sha256="A" * 64,
    )
    # The sentinel guard accepts lowercase hex only.
    assert manifest_pin_is_live_digest(pin_upper) is False
    pin_live = Stage25ArtifactReference(
        artifact_basename=STAGE25_MANIFEST_FILENAME,
        artifact_sha256="0123456789abcdef" * 4,
    )
    assert manifest_pin_is_live_digest(pin_live) is True

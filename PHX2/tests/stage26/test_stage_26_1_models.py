"""Stage 26.1 model immutability + field-order tests."""

from __future__ import annotations

import pytest

from PHX2.stage26 import models as m


_MODEL_NAMES: tuple[str, ...] = (
    "ATHCandidateInput",
    "ATHMeasurementInput",
    "ArtifactValidationEntry",
    "ArtifactValidationReport",
    "MeasurementRejectionInput",
    "MigrationMeasurementInput",
    "MigrationObservationInput",
    "PriceWindowObservationInput",
    "SourceReconciliationInput",
    "Stage25ArtifactReference",
    "Stage25ArtifactSet",
    "Stage25ManifestFileEntryInput",
    "Stage25ManifestInput",
    "Stage25Stage24ManifestPinInput",
    "Stage25SummaryInput",
    "Stage26CalibrationInputSet",
    "Stage26ReaderResult",
)


@pytest.mark.parametrize("name", _MODEL_NAMES)
def test_model_is_namedtuple_subclass(name):
    cls = getattr(m, name)
    # NamedTuple subclasses inherit from tuple and have _fields.
    assert issubclass(cls, tuple), f"{name} must subclass tuple"
    assert hasattr(cls, "_fields"), f"{name} must expose _fields"
    assert isinstance(cls._fields, tuple)
    assert cls._fields != ()


@pytest.mark.parametrize("name", _MODEL_NAMES)
def test_model_fields_are_unique(name):
    cls = getattr(m, name)
    assert len(cls._fields) == len(set(cls._fields))


def test_artifact_validation_entry_field_order_locked():
    assert m.ArtifactValidationEntry._fields == (
        "artifact_basename",
        "status",
        "detail",
        "error_code",
    )


def test_artifact_validation_report_field_order_locked():
    assert m.ArtifactValidationReport._fields == ("entries", "ok")


def test_stage25_artifact_reference_field_order_locked():
    assert m.Stage25ArtifactReference._fields == (
        "artifact_basename",
        "artifact_sha256",
    )


def test_stage26_calibration_input_set_field_order_locked():
    assert m.Stage26CalibrationInputSet._fields == (
        "stage26_calibration_input_version",
        "stage25_manifest_pin",
        "reader_result",
    )


def test_model_instance_attribute_assignment_raises():
    """NamedTuple instances are immutable: attribute assignment must fail."""
    entry = m.ArtifactValidationEntry(
        artifact_basename="x",
        status="VALIDATED",
        detail="",
        error_code="",
    )
    with pytest.raises(AttributeError):
        entry.detail = "mutated"  # type: ignore[misc]


def test_migration_observation_input_field_order_mirrors_writer():
    """Field order mirrors the Stage 25 writer's serialization order."""
    assert m.MigrationObservationInput._fields == (
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
    )


def test_ath_measurement_input_field_order_mirrors_writer():
    assert m.ATHMeasurementInput._fields == (
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
    )


def test_no_model_carries_denominator_field():
    for name in _MODEL_NAMES:
        cls = getattr(m, name)
        for field in cls._fields:
            assert "denominator" not in field.lower(), (
                f"{name}.{field}: Stage 26.1 must not carry denominator "
                "fields; denominator semantics are Stage 26.2"
            )


def test_no_model_carries_approval_field():
    for name in _MODEL_NAMES:
        cls = getattr(m, name)
        for field in cls._fields:
            for forbidden in (
                "approval",
                "approved_by",
                "approval_state",
            ):
                assert forbidden not in field.lower(), (
                    f"{name}.{field}: approval vocabulary forbidden in "
                    "Stage 26.1"
                )

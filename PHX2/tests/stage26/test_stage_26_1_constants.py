"""Stage 26.1 constants tests.

Pins the Stage 26.1 locked closed-set vocabularies, the Stage 26.1
version axes, and the typed-error code surface. Stage 26.1 callers
rely on every closed set being a deterministic tuple of upper-case
ASCII tokens with no duplicates.
"""

from __future__ import annotations

import pytest

from PHX2.stage25.constants import MEASUREMENT_STATUSES
from PHX2.stage26 import constants as c


_CLOSED_SET_NAMES: tuple[str, ...] = (
    "CALIBRATION_INPUT_KINDS",
    "MEASUREMENT_TRUTH_CLASSES",
    "ARTIFACT_VALIDATION_STATUSES",
    "EXCLUSION_REASONS",
    "STAGE26_ERROR_CODES",
)


@pytest.mark.parametrize("name", _CLOSED_SET_NAMES)
def test_closed_set_is_tuple_of_strings(name):
    members = getattr(c, name)
    assert isinstance(members, tuple), f"{name} must be a tuple"
    assert members != (), f"{name} must be non-empty"
    for member in members:
        assert isinstance(member, str), f"{name} element must be str"
        assert member != "", f"{name} carries an empty string"


@pytest.mark.parametrize("name", _CLOSED_SET_NAMES)
def test_closed_set_has_no_duplicates(name):
    members = getattr(c, name)
    assert len(members) == len(set(members)), (
        f"{name} contains duplicate tokens: {sorted(members)}"
    )


@pytest.mark.parametrize("name", _CLOSED_SET_NAMES)
def test_closed_set_tokens_are_uppercase_ascii(name):
    members = getattr(c, name)
    for member in members:
        assert member == member.upper(), (
            f"{name} token {member!r} must be uppercase"
        )
        assert member.isascii(), (
            f"{name} token {member!r} must be ASCII-only"
        )


def test_measurement_truth_classes_equals_stage25_measurement_statuses():
    """Stage 26 must NEVER add / remove / rename a measurement truth class.

    The MEASUREMENT_TRUTH_CLASSES tuple is the verbatim Stage 25
    MEASUREMENT_STATUSES tuple imported through the locked schema
    whitelist.
    """
    assert c.MEASUREMENT_TRUTH_CLASSES == MEASUREMENT_STATUSES


def test_calibration_input_kinds_carries_every_stage25_artifact_kind():
    """One kind per Stage 25 artifact projection plus manifest + summary."""
    expected = {
        c.CALIBRATION_INPUT_KIND_MIGRATION_OBSERVATION,
        c.CALIBRATION_INPUT_KIND_MIGRATION_MEASUREMENT,
        c.CALIBRATION_INPUT_KIND_PRICE_WINDOW_OBSERVATION,
        c.CALIBRATION_INPUT_KIND_ATH_CANDIDATE,
        c.CALIBRATION_INPUT_KIND_SOURCE_RECONCILIATION,
        c.CALIBRATION_INPUT_KIND_ATH_MEASUREMENT,
        c.CALIBRATION_INPUT_KIND_MEASUREMENT_REJECTION,
        c.CALIBRATION_INPUT_KIND_SUMMARY,
        c.CALIBRATION_INPUT_KIND_MANIFEST,
    }
    assert set(c.CALIBRATION_INPUT_KINDS) == expected
    assert len(c.CALIBRATION_INPUT_KINDS) == 9


def test_calibration_input_kind_by_artifact_basename_covers_every_artifact():
    from PHX2.stage25.constants import STAGE25_ARTIFACT_FILENAMES

    declared = {
        basename for basename, _ in c.CALIBRATION_INPUT_KIND_BY_ARTIFACT_BASENAME
    }
    assert declared == set(STAGE25_ARTIFACT_FILENAMES)
    kinds = {kind for _, kind in c.CALIBRATION_INPUT_KIND_BY_ARTIFACT_BASENAME}
    assert kinds == set(c.CALIBRATION_INPUT_KINDS)


def test_artifact_validation_statuses_includes_validated_and_failure_tokens():
    required = {
        "VALIDATED",
        "FILE_MISSING",
        "FILE_NOT_REGULAR",
        "MANIFEST_HASH_MISMATCH",
        "MANIFEST_BYTE_COUNT_MISMATCH",
        "MANIFEST_ROW_COUNT_MISMATCH",
        "SCHEMA_INVALID",
        "UNEXPECTED_EXTRA_FIELD",
        "RECORD_SCHEMA_INVALID",
        "RECORD_TRUTH_CLASS_INVALID",
        "RECORD_NULL_AS_ZERO_VIOLATION",
        "REFERENTIAL_LINK_BROKEN",
    }
    assert set(c.ARTIFACT_VALIDATION_STATUSES) == required


def test_every_error_code_has_stg26_cal_prefix():
    for code in c.STAGE26_ERROR_CODES:
        assert code.startswith("STG26_CAL_"), (
            f"error code {code!r} must use the locked STG26_CAL_ prefix"
        )


def test_stage26_version_axes_are_locked_strings():
    assert c.STAGE26_NAME == "stage26"
    assert c.STAGE26_MINOR_VERSION == "26.1"
    assert c.STAGE26_STAGE_VERSION == c.STAGE26_MINOR_VERSION
    assert c.STAGE26_CALIBRATION_INPUT_VERSION == (
        "stage26_calibration_input_v0"
    )
    assert c.STAGE26_OBSERVE_ONLY_MODE == "observe_only"


def test_no_denominator_status_vocabulary_declared():
    for name in dir(c):
        lower = name.lower()
        assert "denominator" not in lower, (
            f"Stage 26.1 must not declare denominator vocabulary "
            f"(found {name!r}); denominator semantics belong to 26.2"
        )


def test_no_cohort_or_threshold_or_policy_vocabulary_declared():
    for name in dir(c):
        lower = name.lower()
        for forbidden in ("cohort", "threshold", "policy_candidate", "approval"):
            assert forbidden not in lower, (
                f"Stage 26.1 must not declare {forbidden!r} vocabulary "
                f"(found {name!r}); reserved for later sub-stages"
            )


def test_exclusion_reasons_carry_validation_shaped_names_only():
    """Stage 26.1 exclusion_reason vocabulary is validation-shaped only.

    The names must read as "this row failed manifest-level / schema-
    level validation", not as "this row is denominator-ineligible".
    """
    for reason in c.EXCLUSION_REASONS:
        assert reason.isupper()
        # Validation-shaped tokens reference MANIFEST / RECORD / SCHEMA /
        # REFERENTIAL outcomes.
        validation_shapes = (
            "MANIFEST",
            "RECORD",
            "REFERENTIAL",
            "SCHEMA",
        )
        assert any(shape in reason for shape in validation_shapes), (
            f"exclusion reason {reason!r} should be a validation-shaped "
            "token; eligibility-shaped tokens belong to Stage 26.2"
        )

"""Tests for Stage 20 constants module (20.1.A).

Covers:
  * Version string locks.
  * Label-to-state mapping (size, key set, immutability, value
    coverage).
  * SAFE_FOR_LIVE_DISPATCH invariant.
  * Closed-set membership of EligibilityErrorCode and
    EligibilityWarningCode enums.
"""

from __future__ import annotations

import pytest

from PHX2.stage20.constants import (
    CONSUMER_CONTRACT_VERSION,
    EligibilityErrorCode,
    EligibilityWarningCode,
    LABEL_TO_STATE_MAPPING_V0,
    MAPPING_VERSION,
    PreviewEligibilityState,
    SAFE_FOR_LIVE_DISPATCH,
    STAGE19_REVIEW_LABELS,
    STAGE20_VERSION,
    STALENESS_THRESHOLD_DAYS,
)


def test_version_constants_match_locked_values():
    assert STAGE20_VERSION == "stage20_v0_observe_only"
    assert CONSUMER_CONTRACT_VERSION == "stage20_to_stage21_v0"
    assert MAPPING_VERSION == "v0"
    assert STALENESS_THRESHOLD_DAYS == 30


def test_safe_for_live_dispatch_is_false():
    assert SAFE_FOR_LIVE_DISPATCH is False


def test_label_mapping_has_exactly_six_entries():
    assert len(LABEL_TO_STATE_MAPPING_V0) == 6


def test_label_mapping_keys_match_locked_stage19_label_set():
    assert set(LABEL_TO_STATE_MAPPING_V0.keys()) == set(STAGE19_REVIEW_LABELS)


def test_label_mapping_is_immutable():
    with pytest.raises(TypeError):
        LABEL_TO_STATE_MAPPING_V0["NEW_LABEL"] = (
            PreviewEligibilityState.PREVIEW_EXCLUDED
        )


def test_all_four_eligibility_states_reachable_from_mapping():
    states_reached = set(LABEL_TO_STATE_MAPPING_V0.values())
    assert states_reached == {
        PreviewEligibilityState.PREVIEW_EXCLUDED,
        PreviewEligibilityState.PREVIEW_NEEDS_MORE_DATA,
        PreviewEligibilityState.PREVIEW_OBSERVE_ONLY,
        PreviewEligibilityState.PREVIEW_ELIGIBLE,
    }


def test_eligibility_error_code_enum_contains_all_locked_codes():
    expected = {
        "E2001", "E2002", "E2003", "E2004", "E2005", "E2006",
        "E2007", "E2008", "E2009",
        "E2010", "E2011", "E2012", "E2013", "E2014", "E2015",
        "E2016", "E2017",
        "E2020", "E2021", "E2022", "E2023", "E2024", "E2025",
        # Stage 20.3 additions (the slot before E2027 is intentionally
        # skipped and asserted absent by test_no_forbidden_artifacts).
        "E2027", "E2028", "E2029",
    }
    actual = {member.value for member in EligibilityErrorCode}
    assert actual == expected


def test_eligibility_warning_code_enum_contains_all_locked_codes():
    expected = {"W2001", "W2002", "W2003", "W2004", "W2005", "W2006", "W2007"}
    actual = {member.value for member in EligibilityWarningCode}
    assert actual == expected

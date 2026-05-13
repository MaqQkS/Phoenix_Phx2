"""Phase 2: locked safety-surface constants and match helpers."""

from __future__ import annotations

import pytest

from PHX2.stage16a.errors import Stage16AError
from PHX2.stage16a.safety import (
    ALLOWED_FILTER_LABELS,
    ALLOWED_TIER_SCOPES,
    EXPECTED_RUNTIME_SAFETY_SURFACE,
    EXPECTED_STAGE15_DRAFT_SAFETY_SURFACE,
    EXPECTED_STAGE15_SAFETY_SURFACE,
    REQUIRED_PREDICATE_KEYS_RUNTIME,
    REQUIRED_PREDICATE_KEYS_STAGE15,
    assert_exact_match,
    assert_subset_match,
)


# ---------------------------------------------------------------------------
# Locked constants
# ---------------------------------------------------------------------------


def test_stage15_manifest_safety_surface_locked() -> None:
    expected = {
        "hard_block_allowed": False,
        "safe_for_live_enforcement": False,
        "safe_for_hard_blocking": False,
        "runtime_consumable": False,
        "observe_only_runtime_consumable": False,
        "safe_for_observe_only_wiring": True,
        "enforcement_mode": "NONE",
    }
    assert dict(EXPECTED_STAGE15_SAFETY_SURFACE) == expected


def test_stage15_draft_safety_surface_locked() -> None:
    expected = {
        "hard_block_allowed": False,
        "safe_for_live_enforcement": False,
        "safe_for_hard_blocking": False,
        "runtime_consumable": False,
        "observe_only_runtime_consumable": False,
        "safe_for_observe_only_wiring": True,
        "enforcement_mode": "NONE",
        "intended_action_set": ("LOG_WOULD_BLOCK",),
        "approval_status": "OPERATOR_APPROVED_DRAFT",
    }
    assert dict(EXPECTED_STAGE15_DRAFT_SAFETY_SURFACE) == expected


def test_runtime_safety_surface_locked() -> None:
    expected = {
        "enforcement_mode": "OBSERVE_ONLY",
        "hard_block_allowed": False,
        "safe_for_live_enforcement": False,
        "safe_for_hard_blocking": False,
        "runtime_consumable": True,
        "observe_only_runtime_consumable": True,
        "allowed_action_set": ("LOG_WOULD_BLOCK",),
    }
    assert dict(EXPECTED_RUNTIME_SAFETY_SURFACE) == expected


def test_allowed_tier_scopes_locked() -> None:
    assert ALLOWED_TIER_SCOPES == frozenset({"T1", "T2", "T3"})


def test_allowed_filter_labels_locked() -> None:
    assert ALLOWED_FILTER_LABELS == frozenset({
        "NORMAL",
        "ELEVATED",
        "SUSPICIOUS",
        "SCAM_LIKELY",
        "UNKNOWN",
    })


def test_predicate_key_sets_match_five_key_lock() -> None:
    five_keys = frozenset({
        "tier_scope",
        "filter_name",
        "filter_version",
        "filter_label",
        "threshold_version",
    })
    assert REQUIRED_PREDICATE_KEYS_STAGE15 == five_keys
    assert REQUIRED_PREDICATE_KEYS_RUNTIME == five_keys


# ---------------------------------------------------------------------------
# Subset-match helper (Stage 15 input)
# ---------------------------------------------------------------------------


def test_subset_match_passes_when_actual_carries_extras() -> None:
    expected = {"a": 1, "b": 2}
    actual = {"a": 1, "b": 2, "runtime_consumable_scope": "none"}
    assert_subset_match(expected, actual, code="L08")


def test_subset_match_passes_on_exact() -> None:
    expected = {"a": 1, "b": 2}
    actual = {"a": 1, "b": 2}
    assert_subset_match(expected, actual, code="L08")


def test_subset_match_raises_on_missing_key() -> None:
    with pytest.raises(Stage16AError) as info:
        assert_subset_match({"a": 1}, {"b": 2}, code="L08")
    assert info.value.code == "L08"
    assert "'a'" in info.value.detail


def test_subset_match_raises_on_value_mismatch() -> None:
    with pytest.raises(Stage16AError) as info:
        assert_subset_match({"a": 1}, {"a": 2}, code="L08")
    assert info.value.code == "L08"
    assert "'a'" in info.value.detail


# ---------------------------------------------------------------------------
# Exact-match helper (Stage 16A runtime)
# ---------------------------------------------------------------------------


def test_exact_match_passes_on_exact() -> None:
    expected = {"a": 1, "b": 2}
    actual = {"a": 1, "b": 2}
    assert_exact_match(expected, actual, code="R03")


def test_exact_match_rejects_extras() -> None:
    with pytest.raises(Stage16AError) as info:
        assert_exact_match({"a": 1}, {"a": 1, "extra": 99}, code="R03")
    assert info.value.code == "R03"
    assert "extra" in info.value.detail


def test_exact_match_rejects_missing() -> None:
    with pytest.raises(Stage16AError) as info:
        assert_exact_match({"a": 1, "b": 2}, {"a": 1}, code="R03")
    assert info.value.code == "R03"
    assert "'b'" in info.value.detail


def test_exact_match_rejects_value_mismatch() -> None:
    with pytest.raises(Stage16AError) as info:
        assert_exact_match({"a": 1}, {"a": 2}, code="R03")
    assert info.value.code == "R03"


def test_exact_match_normalizes_list_to_tuple() -> None:
    """JSON-loaded lists must compare equal to tuple constants."""

    expected = {"allowed_action_set": ("LOG_WOULD_BLOCK",)}
    actual_from_json = {"allowed_action_set": ["LOG_WOULD_BLOCK"]}
    assert_exact_match(expected, actual_from_json, code="R03")


def test_runtime_safety_surface_matches_loaded_runtime_artifact_shape() -> None:
    """A JSON-loaded runtime safety_surface (with list-form allowed_action_set)
    must pass exact-match against EXPECTED_RUNTIME_SAFETY_SURFACE."""

    loaded = {
        "enforcement_mode": "OBSERVE_ONLY",
        "hard_block_allowed": False,
        "safe_for_live_enforcement": False,
        "safe_for_hard_blocking": False,
        "runtime_consumable": True,
        "observe_only_runtime_consumable": True,
        "allowed_action_set": ["LOG_WOULD_BLOCK"],
    }
    assert_exact_match(EXPECTED_RUNTIME_SAFETY_SURFACE, loaded, code="R03")

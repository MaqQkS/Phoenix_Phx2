"""Stage 15 PHASE 3 safety-gate invariant tests.

The safety gate is the single source of truth for the artifact-level
safety surface (runtime_consumable=false, hard_block_allowed=false,
intended_action_set=["LOG_WOULD_BLOCK"], etc.). These tests assert the
constants don't drift and that ``assert_draft_safety_invariants`` rejects
any draft that violates them.
"""

from __future__ import annotations

import pytest

from PHX2.stage15 import safety_gate as sg


def _valid_draft() -> dict:
    return {
        "runtime_consumable": False,
        "observe_only_runtime_consumable": False,
        "hard_block_allowed": False,
        "safe_for_live_enforcement": False,
        "safe_for_hard_blocking": False,
        "safe_for_observe_only_wiring": True,
        "enforcement_mode": "NONE",
        "intended_action_set": ["LOG_WOULD_BLOCK"],
        "rules": [
            {
                "rule_id": "r1",
                "operator_decision": "APPROVE_OBSERVE_ONLY",
                "hard_block_allowed": False,
                "intended_action_if_wired": "LOG_WOULD_BLOCK",
            }
        ],
    }


def test_safety_surface_constants_are_locked() -> None:
    assert sg.SAFETY_SURFACE["runtime_consumable"] is False
    assert sg.SAFETY_SURFACE["observe_only_runtime_consumable"] is False
    assert sg.SAFETY_SURFACE["hard_block_allowed"] is False
    assert sg.SAFETY_SURFACE["safe_for_live_enforcement"] is False
    assert sg.SAFETY_SURFACE["safe_for_hard_blocking"] is False
    assert sg.SAFETY_SURFACE["enforcement_mode"] == "NONE"
    assert sg.SAFETY_SURFACE["intended_action_set"] == ("LOG_WOULD_BLOCK",)


def test_rule_intended_action_is_locked() -> None:
    assert sg.RULE_INTENDED_ACTION == "LOG_WOULD_BLOCK"
    assert sg.RULE_HARD_BLOCK_ALLOWED is False


def test_manifest_status_values_are_closed() -> None:
    assert sg.MANIFEST_STATUS_VALUES == frozenset(
        {"APPROVED_DRAFT_WRITTEN", "VALIDATION_FAILED"}
    )


def test_assert_draft_safety_invariants_passes_valid() -> None:
    sg.assert_draft_safety_invariants(_valid_draft())


@pytest.mark.parametrize(
    "field, bad_value",
    [
        ("runtime_consumable", True),
        ("observe_only_runtime_consumable", True),
        ("hard_block_allowed", True),
        ("safe_for_live_enforcement", True),
        ("safe_for_hard_blocking", True),
    ],
)
def test_top_level_safety_invariant_violations(field, bad_value) -> None:
    draft = _valid_draft()
    draft[field] = bad_value
    with pytest.raises(AssertionError):
        sg.assert_draft_safety_invariants(draft)


def test_safe_for_observe_only_wiring_must_be_true_in_draft() -> None:
    draft = _valid_draft()
    draft["safe_for_observe_only_wiring"] = False
    with pytest.raises(AssertionError):
        sg.assert_draft_safety_invariants(draft)


def test_enforcement_mode_must_be_NONE() -> None:
    draft = _valid_draft()
    draft["enforcement_mode"] = "HARD_BLOCK"
    with pytest.raises(AssertionError):
        sg.assert_draft_safety_invariants(draft)


def test_intended_action_set_must_be_exact_list() -> None:
    draft = _valid_draft()
    draft["intended_action_set"] = ["LOG_WOULD_BLOCK", "HARD_BLOCK"]
    with pytest.raises(AssertionError):
        sg.assert_draft_safety_invariants(draft)


def test_rule_hard_block_must_be_false() -> None:
    draft = _valid_draft()
    draft["rules"][0]["hard_block_allowed"] = True
    with pytest.raises(AssertionError):
        sg.assert_draft_safety_invariants(draft)


def test_rule_intended_action_if_wired_must_be_log_would_block() -> None:
    draft = _valid_draft()
    draft["rules"][0]["intended_action_if_wired"] = "HARD_BLOCK"
    with pytest.raises(AssertionError):
        sg.assert_draft_safety_invariants(draft)


def test_only_approve_observe_only_rules_in_draft() -> None:
    """The writer never includes non-APPROVED rules, but the safety
    gate also checks defensively in case of regression."""

    draft = _valid_draft()
    draft["rules"][0]["operator_decision"] = "REJECT"
    with pytest.raises(AssertionError):
        sg.assert_draft_safety_invariants(draft)

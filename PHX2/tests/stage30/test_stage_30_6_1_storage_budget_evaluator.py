"""Stage 30.6.1 storage-budget evaluator tests.

Pure offline behavioral tests for ``evaluate_storage_budget``. No live
calls, no env reads, no filesystem writes, no actual-disk reads. The
caller supplies every disk-used percentage.

Pinned behavior:

  * OK below the soft threshold,
  * SOFT_ALARM at exactly the soft threshold and within [soft, hard),
  * HARD_STOP at exactly the hard threshold and above,
  * fail-closed INVALID_INPUT for a missing / non-number / non-finite /
    out-of-range disk percentage,
  * fail-closed INVALID_INPUT for a non-numeric / out-of-range /
    inverted policy threshold,
  * custom-policy classification,
  * determinism (equal inputs -> equal decisions),
  * ``runtime_consumable`` hard-locked ``False`` (never claims a live
    write executed),
  * totality (never raises for bad observation / policy input).
"""

from __future__ import annotations

import math
import types

import pytest

from PHX2.stage30.stage30_6_storage_budget_evaluator import (
    evaluate_storage_budget,
)
from PHX2.stage30.stage30_6_storage_budget_models import (
    ALLOW_WRITES,
    ALLOW_WRITES_WITH_WARNING,
    INVALID_INPUT_REFUSE_WRITES,
    REFUSE_NEW_WRITES,
    STAGE30_6_1_STORAGE_BUDGET_SCHEMA_VERSION,
    STORAGE_BUDGET_HARD_STOP,
    STORAGE_BUDGET_INVALID_INPUT,
    STORAGE_BUDGET_OK,
    STORAGE_BUDGET_REASON_HARD_STOP_REACHED,
    STORAGE_BUDGET_REASON_INVALID_DISK_USED_PCT_MISSING,
    STORAGE_BUDGET_REASON_INVALID_DISK_USED_PCT_NOT_FINITE,
    STORAGE_BUDGET_REASON_INVALID_DISK_USED_PCT_NOT_NUMBER,
    STORAGE_BUDGET_REASON_INVALID_DISK_USED_PCT_OUT_OF_RANGE,
    STORAGE_BUDGET_REASON_INVALID_POLICY_SOFT_GE_HARD,
    STORAGE_BUDGET_REASON_INVALID_POLICY_THRESHOLD_NOT_NUMERIC,
    STORAGE_BUDGET_REASON_INVALID_POLICY_THRESHOLD_OUT_OF_RANGE,
    STORAGE_BUDGET_REASON_OK_BELOW_SOFT_ALARM,
    STORAGE_BUDGET_REASON_SOFT_ALARM_REACHED,
    STORAGE_BUDGET_SOFT_ALARM,
    Stage30_6StorageBudgetObservation,
    Stage30_6StorageBudgetPolicy,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _obs(disk_used_pct: object) -> Stage30_6StorageBudgetObservation:
    return Stage30_6StorageBudgetObservation(
        disk_used_pct=disk_used_pct  # type: ignore[arg-type]
    )


def _evaluate(disk_used_pct: object, policy: object = None):
    return evaluate_storage_budget(_obs(disk_used_pct), policy)


# ---------------------------------------------------------------------------
# 1. OK below the soft threshold (default policy 65 / 90)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("disk", [0.0, 0, 10.0, 50.0, 64.0, 64.999])
def test_ok_below_soft(disk: object) -> None:
    decision = _evaluate(disk)
    assert decision.status == STORAGE_BUDGET_OK
    assert decision.action == ALLOW_WRITES
    assert decision.should_allow_new_writes is True
    assert decision.should_emit_operator_warning is False
    assert decision.reason == STORAGE_BUDGET_REASON_OK_BELOW_SOFT_ALARM
    assert decision.runtime_consumable is False
    assert decision.soft_alarm_used_pct == 65.0
    assert decision.hard_stop_used_pct == 90.0
    assert decision.policy_version == (
        "stage30_6_storage_budget_policy_v0"
    )
    assert decision.schema_version == (
        STAGE30_6_1_STORAGE_BUDGET_SCHEMA_VERSION
    )


# ---------------------------------------------------------------------------
# 2. SOFT_ALARM at exactly 65.0 and within [65, 90)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("disk", [65.0, 65, 65.001, 70.0, 89.0, 89.999])
def test_soft_alarm_in_band(disk: object) -> None:
    decision = _evaluate(disk)
    assert decision.status == STORAGE_BUDGET_SOFT_ALARM
    assert decision.action == ALLOW_WRITES_WITH_WARNING
    assert decision.should_allow_new_writes is True
    assert decision.should_emit_operator_warning is True
    assert decision.reason == STORAGE_BUDGET_REASON_SOFT_ALARM_REACHED
    assert decision.runtime_consumable is False


def test_soft_alarm_at_exactly_65() -> None:
    decision = _evaluate(65.0)
    assert decision.status == STORAGE_BUDGET_SOFT_ALARM
    assert decision.disk_used_pct == 65.0


# ---------------------------------------------------------------------------
# 3. HARD_STOP at exactly 90.0 and above
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("disk", [90.0, 90, 90.001, 95.0, 99.999, 100.0])
def test_hard_stop_in_band(disk: object) -> None:
    decision = _evaluate(disk)
    assert decision.status == STORAGE_BUDGET_HARD_STOP
    assert decision.action == REFUSE_NEW_WRITES
    assert decision.should_allow_new_writes is False
    assert decision.should_emit_operator_warning is True
    assert decision.reason == STORAGE_BUDGET_REASON_HARD_STOP_REACHED
    assert decision.runtime_consumable is False


def test_hard_stop_at_exactly_90() -> None:
    decision = _evaluate(90.0)
    assert decision.status == STORAGE_BUDGET_HARD_STOP
    assert decision.disk_used_pct == 90.0


# ---------------------------------------------------------------------------
# 4. Boundary precision (the gaps are exact, no rounding)
# ---------------------------------------------------------------------------


def test_boundary_just_below_soft_is_ok() -> None:
    assert _evaluate(64.9999999).status == STORAGE_BUDGET_OK


def test_boundary_just_below_hard_is_soft() -> None:
    assert _evaluate(89.9999999).status == STORAGE_BUDGET_SOFT_ALARM


def test_boundary_just_above_hard_is_hard() -> None:
    assert _evaluate(90.0000001).status == STORAGE_BUDGET_HARD_STOP


# ---------------------------------------------------------------------------
# 5. Invalid disk-used percentage fails closed
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "disk, reason_token",
    [
        (None, STORAGE_BUDGET_REASON_INVALID_DISK_USED_PCT_MISSING),
        ("80", STORAGE_BUDGET_REASON_INVALID_DISK_USED_PCT_NOT_NUMBER),
        (
            ["x"],
            STORAGE_BUDGET_REASON_INVALID_DISK_USED_PCT_NOT_NUMBER,
        ),
        (True, STORAGE_BUDGET_REASON_INVALID_DISK_USED_PCT_NOT_NUMBER),
        (
            float("nan"),
            STORAGE_BUDGET_REASON_INVALID_DISK_USED_PCT_NOT_FINITE,
        ),
        (
            float("inf"),
            STORAGE_BUDGET_REASON_INVALID_DISK_USED_PCT_NOT_FINITE,
        ),
        (
            float("-inf"),
            STORAGE_BUDGET_REASON_INVALID_DISK_USED_PCT_NOT_FINITE,
        ),
        (
            -0.0001,
            STORAGE_BUDGET_REASON_INVALID_DISK_USED_PCT_OUT_OF_RANGE,
        ),
        (
            -5.0,
            STORAGE_BUDGET_REASON_INVALID_DISK_USED_PCT_OUT_OF_RANGE,
        ),
        (
            100.0001,
            STORAGE_BUDGET_REASON_INVALID_DISK_USED_PCT_OUT_OF_RANGE,
        ),
        (
            101.0,
            STORAGE_BUDGET_REASON_INVALID_DISK_USED_PCT_OUT_OF_RANGE,
        ),
    ],
)
def test_invalid_disk_pct_fails_closed(
    disk: object, reason_token: str
) -> None:
    decision = _evaluate(disk)
    assert decision.status == STORAGE_BUDGET_INVALID_INPUT
    assert decision.action == INVALID_INPUT_REFUSE_WRITES
    assert decision.should_allow_new_writes is False
    assert decision.should_emit_operator_warning is True
    assert decision.reason == reason_token
    assert decision.runtime_consumable is False


def test_invalid_disk_echo_is_none_for_unrepresentable() -> None:
    # missing / non-number / non-finite echo None for disk_used_pct.
    for disk in (None, "80", float("nan"), float("inf")):
        decision = _evaluate(disk)
        assert decision.disk_used_pct is None


def test_out_of_range_echoes_the_observed_value() -> None:
    # An out-of-range but finite value is still echoed for operator
    # visibility.
    decision = _evaluate(101.0)
    assert decision.disk_used_pct == 101.0
    decision_neg = _evaluate(-5.0)
    assert decision_neg.disk_used_pct == -5.0


def test_huge_int_disk_pct_fails_closed_without_overflow() -> None:
    # A very large int cannot be represented as a float; the evaluator
    # must NOT raise OverflowError -- it fails closed (out of range) and
    # echoes None.
    decision = _evaluate(10 ** 400)
    assert decision.status == STORAGE_BUDGET_INVALID_INPUT
    assert decision.reason == (
        STORAGE_BUDGET_REASON_INVALID_DISK_USED_PCT_OUT_OF_RANGE
    )
    assert decision.disk_used_pct is None


# ---------------------------------------------------------------------------
# 6. Invalid policy fails closed
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "soft, hard, reason_token",
    [
        (90.0, 65.0, STORAGE_BUDGET_REASON_INVALID_POLICY_SOFT_GE_HARD),
        (70.0, 70.0, STORAGE_BUDGET_REASON_INVALID_POLICY_SOFT_GE_HARD),
        (
            -1.0,
            90.0,
            STORAGE_BUDGET_REASON_INVALID_POLICY_THRESHOLD_OUT_OF_RANGE,
        ),
        (
            65.0,
            101.0,
            STORAGE_BUDGET_REASON_INVALID_POLICY_THRESHOLD_OUT_OF_RANGE,
        ),
        (
            "x",
            90.0,
            STORAGE_BUDGET_REASON_INVALID_POLICY_THRESHOLD_NOT_NUMERIC,
        ),
        (
            65.0,
            None,
            STORAGE_BUDGET_REASON_INVALID_POLICY_THRESHOLD_NOT_NUMERIC,
        ),
        (
            float("nan"),
            90.0,
            STORAGE_BUDGET_REASON_INVALID_POLICY_THRESHOLD_NOT_NUMERIC,
        ),
        (
            True,
            90.0,
            STORAGE_BUDGET_REASON_INVALID_POLICY_THRESHOLD_NOT_NUMERIC,
        ),
    ],
)
def test_invalid_policy_fails_closed(
    soft: object, hard: object, reason_token: str
) -> None:
    policy = Stage30_6StorageBudgetPolicy(
        soft_alarm_used_pct=soft,  # type: ignore[arg-type]
        hard_stop_used_pct=hard,  # type: ignore[arg-type]
    )
    decision = _evaluate(50.0, policy)
    assert decision.status == STORAGE_BUDGET_INVALID_INPUT
    assert decision.action == INVALID_INPUT_REFUSE_WRITES
    assert decision.should_allow_new_writes is False
    assert decision.should_emit_operator_warning is True
    assert decision.reason == reason_token
    assert decision.runtime_consumable is False


def test_invalid_policy_still_echoes_valid_disk_value() -> None:
    policy = Stage30_6StorageBudgetPolicy(
        soft_alarm_used_pct=90.0, hard_stop_used_pct=65.0
    )
    decision = _evaluate(40.0, policy)
    assert decision.status == STORAGE_BUDGET_INVALID_INPUT
    # the disk value was a fine number, so it is still echoed.
    assert decision.disk_used_pct == 40.0


# ---------------------------------------------------------------------------
# 7. Custom valid policy classification
# ---------------------------------------------------------------------------


def test_custom_policy_classification() -> None:
    policy = Stage30_6StorageBudgetPolicy(
        soft_alarm_used_pct=50.0,
        hard_stop_used_pct=80.0,
        policy_version="custom_v1",
    )
    assert _evaluate(40.0, policy).status == STORAGE_BUDGET_OK
    assert _evaluate(50.0, policy).status == STORAGE_BUDGET_SOFT_ALARM
    assert _evaluate(79.999, policy).status == STORAGE_BUDGET_SOFT_ALARM
    assert _evaluate(80.0, policy).status == STORAGE_BUDGET_HARD_STOP
    assert _evaluate(95.0, policy).status == STORAGE_BUDGET_HARD_STOP
    # the custom policy version is echoed onto the decision.
    assert _evaluate(40.0, policy).policy_version == "custom_v1"


# ---------------------------------------------------------------------------
# 8. Default policy + duck-typed inputs
# ---------------------------------------------------------------------------


def test_default_policy_used_when_none() -> None:
    decision = evaluate_storage_budget(_obs(70.0), None)
    assert decision.status == STORAGE_BUDGET_SOFT_ALARM
    assert decision.soft_alarm_used_pct == 65.0
    assert decision.hard_stop_used_pct == 90.0


def test_duck_typed_namespace_observation_and_policy() -> None:
    obs = types.SimpleNamespace(disk_used_pct=55.0)
    policy = types.SimpleNamespace(
        soft_alarm_used_pct=50.0,
        hard_stop_used_pct=80.0,
        policy_version="ns_policy",
    )
    decision = evaluate_storage_budget(obs, policy)
    assert decision.status == STORAGE_BUDGET_SOFT_ALARM
    assert decision.policy_version == "ns_policy"


def test_none_observation_fails_closed_missing() -> None:
    decision = evaluate_storage_budget(None)
    assert decision.status == STORAGE_BUDGET_INVALID_INPUT
    assert decision.reason == (
        STORAGE_BUDGET_REASON_INVALID_DISK_USED_PCT_MISSING
    )


def test_attribute_less_observation_fails_closed_missing() -> None:
    decision = evaluate_storage_budget(object())
    assert decision.status == STORAGE_BUDGET_INVALID_INPUT
    assert decision.reason == (
        STORAGE_BUDGET_REASON_INVALID_DISK_USED_PCT_MISSING
    )


def test_non_string_policy_version_echoes_none() -> None:
    policy = types.SimpleNamespace(
        soft_alarm_used_pct=65.0,
        hard_stop_used_pct=90.0,
        policy_version=123,
    )
    decision = evaluate_storage_budget(_obs(10.0), policy)
    assert decision.status == STORAGE_BUDGET_OK
    assert decision.policy_version is None


# ---------------------------------------------------------------------------
# 9. Determinism + totality
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "disk", [10.0, 65.0, 90.0, None, "x", -1.0, 101.0]
)
def test_deterministic_repeated_evaluation(disk: object) -> None:
    first = _evaluate(disk)
    second = _evaluate(disk)
    assert first == second


def test_runtime_consumable_false_on_every_branch() -> None:
    for disk in (10.0, 65.0, 90.0, None, "x", float("nan"), -1.0, 101.0):
        assert _evaluate(disk).runtime_consumable is False


def test_evaluator_never_raises_on_garbage() -> None:
    garbage_observations = [
        None,
        object(),
        types.SimpleNamespace(),
        types.SimpleNamespace(disk_used_pct=object()),
        _obs(complex(1, 2)),
        _obs([1, 2, 3]),
    ]
    for obs in garbage_observations:
        decision = evaluate_storage_budget(obs)
        assert decision.status == STORAGE_BUDGET_INVALID_INPUT
        assert decision.should_allow_new_writes is False


def test_every_decision_is_closed_set() -> None:
    # Sweep a range of disk values and confirm every produced decision
    # carries closed-set status / action / reason and the schema
    # version (the decision constructor would have raised otherwise).
    for disk in (-10.0, 0.0, 30.0, 65.0, 75.0, 90.0, 150.0):
        decision = _evaluate(disk)
        assert decision.schema_version == (
            STAGE30_6_1_STORAGE_BUDGET_SCHEMA_VERSION
        )
        assert math.isfinite(decision.soft_alarm_used_pct or 0.0)

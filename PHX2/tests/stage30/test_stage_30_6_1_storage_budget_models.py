"""Stage 30.6.1 storage-budget model tests.

Pure offline unit tests for the Stage 30.6.1 closed-set vocabularies
and the policy / observation / decision shapes. No live calls, no env
reads, no filesystem writes, no actual-disk reads.

Pinned contract:

  * minor / schema / policy version + default-threshold + bound
    constants,
  * the status / action / reason closed sets + their predicates,
  * the Policy / Observation lenient carriers (no construction-time
    raise, even for an inverted / out-of-range threshold or a bad
    disk-used percentage),
  * the Decision validated output (construction-time closed-set
    validation; ``runtime_consumable`` hard-locked ``False``),
  * the forbidden-field-name guard + the field-name helpers,
  * the closed-set error type.
"""

from __future__ import annotations

import dataclasses
import math

import pytest

from PHX2.stage30.stage30_6_storage_budget_models import (
    ALLOW_WRITES,
    ALLOW_WRITES_WITH_WARNING,
    FORBIDDEN_RECORD_FIELD_NAMES,
    INVALID_INPUT_REFUSE_WRITES,
    REFUSE_NEW_WRITES,
    STAGE30_6_1_MINOR_VERSION,
    STAGE30_6_1_STORAGE_BUDGET_POLICY_VERSION,
    STAGE30_6_1_STORAGE_BUDGET_SCHEMA_VERSION,
    STORAGE_BUDGET_ACTION_VALUES,
    STORAGE_BUDGET_DEFAULT_HARD_STOP_USED_PCT,
    STORAGE_BUDGET_DEFAULT_SOFT_ALARM_USED_PCT,
    STORAGE_BUDGET_HARD_STOP,
    STORAGE_BUDGET_INVALID_INPUT,
    STORAGE_BUDGET_MAX_USED_PCT,
    STORAGE_BUDGET_MIN_USED_PCT,
    STORAGE_BUDGET_OK,
    STORAGE_BUDGET_REASON_HARD_STOP_REACHED,
    STORAGE_BUDGET_REASON_OK_BELOW_SOFT_ALARM,
    STORAGE_BUDGET_REASON_SOFT_ALARM_REACHED,
    STORAGE_BUDGET_REASON_VALUES,
    STORAGE_BUDGET_SOFT_ALARM,
    STORAGE_BUDGET_STATUS_VALUES,
    Stage30_6StorageBudgetDecision,
    Stage30_6StorageBudgetError,
    Stage30_6StorageBudgetObservation,
    Stage30_6StorageBudgetPolicy,
    decision_field_names,
    is_finite_real,
    is_forbidden_record_field_name,
    is_storage_budget_action_value,
    is_storage_budget_reason_value,
    is_storage_budget_status_value,
    observation_field_names,
    policy_field_names,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _valid_decision(**overrides: object) -> Stage30_6StorageBudgetDecision:
    kwargs = dict(
        schema_version=STAGE30_6_1_STORAGE_BUDGET_SCHEMA_VERSION,
        status=STORAGE_BUDGET_OK,
        action=ALLOW_WRITES,
        should_allow_new_writes=True,
        should_emit_operator_warning=False,
        reason=STORAGE_BUDGET_REASON_OK_BELOW_SOFT_ALARM,
        disk_used_pct=10.0,
        soft_alarm_used_pct=65.0,
        hard_stop_used_pct=90.0,
        policy_version="pv",
        runtime_consumable=False,
    )
    kwargs.update(overrides)
    return Stage30_6StorageBudgetDecision(**kwargs)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# 1. Version / default / bound constants
# ---------------------------------------------------------------------------


def test_versions_pinned() -> None:
    assert STAGE30_6_1_MINOR_VERSION == "30.6.1"
    assert STAGE30_6_1_STORAGE_BUDGET_SCHEMA_VERSION == (
        "stage30_6_1_v0_storage_budget"
    )
    assert STAGE30_6_1_STORAGE_BUDGET_POLICY_VERSION == (
        "stage30_6_storage_budget_policy_v0"
    )


def test_default_thresholds_and_bounds_pinned() -> None:
    assert STORAGE_BUDGET_DEFAULT_SOFT_ALARM_USED_PCT == 65.0
    assert STORAGE_BUDGET_DEFAULT_HARD_STOP_USED_PCT == 90.0
    assert STORAGE_BUDGET_MIN_USED_PCT == 0.0
    assert STORAGE_BUDGET_MAX_USED_PCT == 100.0


# ---------------------------------------------------------------------------
# 2. Closed sets + predicates
# ---------------------------------------------------------------------------


def test_status_closed_set_pinned() -> None:
    assert STORAGE_BUDGET_STATUS_VALUES == (
        "STORAGE_BUDGET_OK",
        "STORAGE_BUDGET_SOFT_ALARM",
        "STORAGE_BUDGET_HARD_STOP",
        "STORAGE_BUDGET_INVALID_INPUT",
    )
    for token in STORAGE_BUDGET_STATUS_VALUES:
        assert is_storage_budget_status_value(token)
    assert not is_storage_budget_status_value("STORAGE_BUDGET_MAYBE")
    assert not is_storage_budget_status_value(None)
    assert not is_storage_budget_status_value(1)


def test_action_closed_set_pinned() -> None:
    assert STORAGE_BUDGET_ACTION_VALUES == (
        "ALLOW_WRITES",
        "ALLOW_WRITES_WITH_WARNING",
        "REFUSE_NEW_WRITES",
        "INVALID_INPUT_REFUSE_WRITES",
    )
    for token in STORAGE_BUDGET_ACTION_VALUES:
        assert is_storage_budget_action_value(token)
    assert not is_storage_budget_action_value("ALLOW")
    assert not is_storage_budget_action_value(None)


def test_reason_closed_set_pinned() -> None:
    assert STORAGE_BUDGET_REASON_VALUES == (
        "OK_BELOW_SOFT_ALARM",
        "SOFT_ALARM_REACHED",
        "HARD_STOP_REACHED",
        "INVALID_DISK_USED_PCT_MISSING",
        "INVALID_DISK_USED_PCT_NOT_NUMBER",
        "INVALID_DISK_USED_PCT_NOT_FINITE",
        "INVALID_DISK_USED_PCT_OUT_OF_RANGE",
        "INVALID_POLICY_THRESHOLD_NOT_NUMERIC",
        "INVALID_POLICY_THRESHOLD_OUT_OF_RANGE",
        "INVALID_POLICY_SOFT_GE_HARD",
    )
    for token in STORAGE_BUDGET_REASON_VALUES:
        assert is_storage_budget_reason_value(token)
    assert not is_storage_budget_reason_value("WHATEVER")
    assert not is_storage_budget_reason_value(None)


def test_status_action_reason_sets_have_no_duplicates() -> None:
    for values in (
        STORAGE_BUDGET_STATUS_VALUES,
        STORAGE_BUDGET_ACTION_VALUES,
        STORAGE_BUDGET_REASON_VALUES,
    ):
        assert len(values) == len(set(values))


# ---------------------------------------------------------------------------
# 3. is_finite_real numeric helper
# ---------------------------------------------------------------------------


def test_is_finite_real() -> None:
    assert is_finite_real(0)
    assert is_finite_real(65)
    assert is_finite_real(65.0)
    assert is_finite_real(-3)
    assert is_finite_real(10 ** 400)  # very large int is still finite
    assert not is_finite_real(True)  # bool must never pass as a number
    assert not is_finite_real(False)
    assert not is_finite_real(float("nan"))
    assert not is_finite_real(float("inf"))
    assert not is_finite_real(float("-inf"))
    assert not is_finite_real("65")
    assert not is_finite_real(None)


# ---------------------------------------------------------------------------
# 4. Policy is a lenient carrier
# ---------------------------------------------------------------------------


def test_default_policy_uses_default_thresholds() -> None:
    policy = Stage30_6StorageBudgetPolicy()
    assert policy.soft_alarm_used_pct == 65.0
    assert policy.hard_stop_used_pct == 90.0
    assert policy.policy_version == (
        "stage30_6_storage_budget_policy_v0"
    )


def test_valid_custom_policy_construction() -> None:
    policy = Stage30_6StorageBudgetPolicy(
        soft_alarm_used_pct=50.0,
        hard_stop_used_pct=80.0,
        policy_version="custom_v1",
    )
    assert policy.soft_alarm_used_pct == 50.0
    assert policy.hard_stop_used_pct == 80.0
    assert policy.policy_version == "custom_v1"


def test_policy_is_lenient_does_not_raise_on_bad_thresholds() -> None:
    # Inverted, out-of-range, equal, and non-numeric thresholds are all
    # tolerated at construction; the evaluator fails closed instead.
    Stage30_6StorageBudgetPolicy(
        soft_alarm_used_pct=90.0, hard_stop_used_pct=65.0
    )
    Stage30_6StorageBudgetPolicy(
        soft_alarm_used_pct=70.0, hard_stop_used_pct=70.0
    )
    Stage30_6StorageBudgetPolicy(
        soft_alarm_used_pct=-5.0, hard_stop_used_pct=150.0
    )
    Stage30_6StorageBudgetPolicy(
        soft_alarm_used_pct="x",  # type: ignore[arg-type]
        hard_stop_used_pct=None,  # type: ignore[arg-type]
    )


def test_policy_is_frozen() -> None:
    policy = Stage30_6StorageBudgetPolicy()
    with pytest.raises(dataclasses.FrozenInstanceError):
        policy.soft_alarm_used_pct = 1.0  # type: ignore[misc]


# ---------------------------------------------------------------------------
# 5. Observation is a lenient carrier
# ---------------------------------------------------------------------------


def test_default_observation_is_all_none() -> None:
    obs = Stage30_6StorageBudgetObservation()
    assert obs.disk_used_pct is None
    assert obs.total_bytes is None
    assert obs.free_bytes is None
    assert obs.observed_at_utc is None
    assert obs.source_label is None


def test_observation_with_values() -> None:
    obs = Stage30_6StorageBudgetObservation(
        disk_used_pct=42.5,
        total_bytes=1000,
        free_bytes=600,
        observed_at_utc="2026-05-29T00:00:00Z",
        source_label="operator_supplied",
    )
    assert obs.disk_used_pct == 42.5
    assert obs.total_bytes == 1000
    assert obs.free_bytes == 600
    assert obs.observed_at_utc == "2026-05-29T00:00:00Z"
    assert obs.source_label == "operator_supplied"


def test_observation_is_lenient_does_not_raise_on_bad_disk_pct() -> None:
    # None / non-number / NaN / out-of-range disk values are tolerated
    # at construction; the evaluator fails closed instead.
    Stage30_6StorageBudgetObservation(disk_used_pct=None)
    Stage30_6StorageBudgetObservation(
        disk_used_pct="oops"  # type: ignore[arg-type]
    )
    Stage30_6StorageBudgetObservation(disk_used_pct=float("nan"))
    Stage30_6StorageBudgetObservation(disk_used_pct=-1.0)
    Stage30_6StorageBudgetObservation(disk_used_pct=101.0)


def test_observation_is_frozen() -> None:
    obs = Stage30_6StorageBudgetObservation(disk_used_pct=10.0)
    with pytest.raises(dataclasses.FrozenInstanceError):
        obs.disk_used_pct = 20.0  # type: ignore[misc]


# ---------------------------------------------------------------------------
# 6. Decision is the validated output
# ---------------------------------------------------------------------------


def test_valid_decision_construction() -> None:
    decision = _valid_decision()
    assert decision.status == STORAGE_BUDGET_OK
    assert decision.action == ALLOW_WRITES
    assert decision.should_allow_new_writes is True
    assert decision.should_emit_operator_warning is False
    assert decision.reason == STORAGE_BUDGET_REASON_OK_BELOW_SOFT_ALARM
    assert decision.runtime_consumable is False


def test_decision_is_frozen() -> None:
    decision = _valid_decision()
    with pytest.raises(dataclasses.FrozenInstanceError):
        decision.status = STORAGE_BUDGET_HARD_STOP  # type: ignore[misc]


def test_decision_allows_none_echoes() -> None:
    decision = _valid_decision(
        status=STORAGE_BUDGET_INVALID_INPUT,
        action=INVALID_INPUT_REFUSE_WRITES,
        should_allow_new_writes=False,
        should_emit_operator_warning=True,
        reason="INVALID_DISK_USED_PCT_MISSING",
        disk_used_pct=None,
        soft_alarm_used_pct=None,
        hard_stop_used_pct=None,
        policy_version=None,
    )
    assert decision.disk_used_pct is None
    assert decision.policy_version is None


@pytest.mark.parametrize(
    "overrides, reason_token",
    [
        ({"schema_version": ""}, "SCHEMA_VERSION_INVALID"),
        ({"schema_version": 123}, "SCHEMA_VERSION_INVALID"),
        ({"status": "NOPE"}, "STATUS_INVALID"),
        ({"action": "NOPE"}, "ACTION_INVALID"),
        (
            {"should_allow_new_writes": "yes"},
            "SHOULD_ALLOW_NEW_WRITES_NOT_BOOL",
        ),
        (
            {"should_emit_operator_warning": 1},
            "SHOULD_EMIT_OPERATOR_WARNING_NOT_BOOL",
        ),
        ({"reason": "NOPE"}, "REASON_INVALID"),
        ({"disk_used_pct": float("nan")}, "DISK_USED_PCT_INVALID"),
        ({"disk_used_pct": "10"}, "DISK_USED_PCT_INVALID"),
        (
            {"soft_alarm_used_pct": float("inf")},
            "SOFT_ALARM_USED_PCT_INVALID",
        ),
        (
            {"hard_stop_used_pct": float("inf")},
            "HARD_STOP_USED_PCT_INVALID",
        ),
        ({"policy_version": 123}, "POLICY_VERSION_INVALID"),
        ({"runtime_consumable": 0}, "RUNTIME_CONSUMABLE_NOT_BOOL"),
        (
            {"runtime_consumable": True},
            "RUNTIME_CONSUMABLE_MUST_BE_FALSE",
        ),
    ],
)
def test_decision_rejects_invalid_construction(
    overrides: dict, reason_token: str
) -> None:
    with pytest.raises(Stage30_6StorageBudgetError) as excinfo:
        _valid_decision(**overrides)
    assert excinfo.value.reason == reason_token


def test_decision_rejects_bool_disk_pct() -> None:
    # bool is an int subclass but must never be accepted as a percent.
    with pytest.raises(Stage30_6StorageBudgetError) as excinfo:
        _valid_decision(disk_used_pct=True)
    assert excinfo.value.reason == "DISK_USED_PCT_INVALID"


# ---------------------------------------------------------------------------
# 7. Forbidden-field guard + field-name helpers
# ---------------------------------------------------------------------------


def test_forbidden_field_name_guard() -> None:
    assert is_forbidden_record_field_name("api_" + "key")
    assert is_forbidden_record_field_name("raw_payload")
    assert is_forbidden_record_field_name("web" + "hook_url")
    assert is_forbidden_record_field_name("discord")
    assert not is_forbidden_record_field_name("disk_used_pct")
    assert not is_forbidden_record_field_name("soft_alarm_used_pct")
    assert not is_forbidden_record_field_name("policy_version")
    assert not is_forbidden_record_field_name(None)
    assert len(FORBIDDEN_RECORD_FIELD_NAMES) >= 20


def test_actual_field_names_are_not_forbidden() -> None:
    for name in (
        policy_field_names()
        + observation_field_names()
        + decision_field_names()
    ):
        assert not is_forbidden_record_field_name(name), (
            f"Stage 30.6.1 field name {name!r} is forbidden-class"
        )


def test_field_name_helpers() -> None:
    assert policy_field_names() == (
        "soft_alarm_used_pct",
        "hard_stop_used_pct",
        "policy_version",
    )
    assert observation_field_names() == (
        "disk_used_pct",
        "total_bytes",
        "free_bytes",
        "observed_at_utc",
        "source_label",
    )
    assert decision_field_names() == (
        "schema_version",
        "status",
        "action",
        "should_allow_new_writes",
        "should_emit_operator_warning",
        "reason",
        "disk_used_pct",
        "soft_alarm_used_pct",
        "hard_stop_used_pct",
        "policy_version",
        "runtime_consumable",
    )


def test_decision_carries_no_execution_claim_field() -> None:
    # The decision is a recommendation; no field may claim a write
    # actually executed.
    for name in decision_field_names():
        lower = name.lower()
        assert "executed" not in lower
        assert "did_write" not in lower
        assert "written" not in lower


# ---------------------------------------------------------------------------
# 8. Error type
# ---------------------------------------------------------------------------


def test_error_is_exception_with_reason() -> None:
    assert issubclass(Stage30_6StorageBudgetError, Exception)
    err = Stage30_6StorageBudgetError("MY_REASON")
    assert err.reason == "MY_REASON"
    assert "MY_REASON" in str(err)


def test_unused_token_imports_are_consistent() -> None:
    # Defensive: the status / action tokens imported here line up with
    # the closed-set tuples (guards against an accidental rename drift).
    assert STORAGE_BUDGET_SOFT_ALARM in STORAGE_BUDGET_STATUS_VALUES
    assert STORAGE_BUDGET_HARD_STOP in STORAGE_BUDGET_STATUS_VALUES
    assert ALLOW_WRITES_WITH_WARNING in STORAGE_BUDGET_ACTION_VALUES
    assert REFUSE_NEW_WRITES in STORAGE_BUDGET_ACTION_VALUES
    assert (
        STORAGE_BUDGET_REASON_SOFT_ALARM_REACHED
        in STORAGE_BUDGET_REASON_VALUES
    )
    assert (
        STORAGE_BUDGET_REASON_HARD_STOP_REACHED
        in STORAGE_BUDGET_REASON_VALUES
    )
    assert math.isfinite(1.0)

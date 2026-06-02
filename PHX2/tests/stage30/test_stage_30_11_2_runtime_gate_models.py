"""Stage 30.11.2 runtime gate seam models unit tests.

Pins the four frozen Stage 30.11.2 runtime models (the bounded-runtime config,
the per-candidate runtime outcome, the rolled-up runtime summary, the fake
dispatch acknowledgement result): their field names + order, their
immutability, their field-name helpers, the closed-set runtime decision /
reason vocabularies, the not-evaluated sentinel, the config validator (positive
runtime / positive candidate cap / non-negative dispatch cap; fail closed
otherwise), the minor version, and the runtime gate schema version. Fake /
offline only; no live call, no provider, no Discord, no env read, no wall-clock
read.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from decimal import Decimal

import pytest

from PHX2.stage30.stage30_11_2_runtime_gate_models import (
    RUNTIME_DECISION_DISPATCHED_AFTER_DIP_GATE_PASS,
    RUNTIME_DECISION_INVALID_RUNTIME_INPUT,
    RUNTIME_DECISION_STOPPED_BY_CANDIDATE_CAP,
    RUNTIME_DECISION_STOPPED_BY_DISPATCH_CAP,
    RUNTIME_DECISION_STOPPED_BY_RUNTIME_SECONDS,
    RUNTIME_DECISION_SUPPRESSED_BY_BRIDGE,
    RUNTIME_DECISION_SUPPRESSED_BY_DIP_GATE,
    RUNTIME_REASON_BRIDGE_SKIPPED_OR_INVALID,
    RUNTIME_REASON_CANDIDATE_CAP_REACHED,
    RUNTIME_REASON_DIP_GATE_SKIPPED,
    RUNTIME_REASON_DISPATCH_CAP_REACHED,
    RUNTIME_REASON_INVALID_CONFIG_OR_INPUT,
    RUNTIME_REASON_PASS_TO_FAKE_DISPATCH,
    RUNTIME_REASON_RUNTIME_SECONDS_REACHED,
    STAGE30_11_2_MINOR_VERSION,
    STAGE30_11_2_NOT_EVALUATED,
    STAGE30_11_2_RUNTIME_DECISIONS,
    STAGE30_11_2_RUNTIME_DISPATCH_DECISION,
    STAGE30_11_2_RUNTIME_DISPATCH_REASON,
    STAGE30_11_2_RUNTIME_GATE_SCHEMA_VERSION,
    STAGE30_11_2_RUNTIME_REASONS,
    Stage30_11FakeDispatchResult,
    Stage30_11RuntimeGateCandidateOutcome,
    Stage30_11RuntimeGateConfig,
    Stage30_11RuntimeGateSummary,
    fake_dispatch_result_field_names,
    is_runtime_decision,
    is_runtime_reason,
    is_valid_runtime_gate_config,
    runtime_gate_candidate_outcome_field_names,
    runtime_gate_config_field_names,
    runtime_gate_summary_field_names,
)


def _config(
    *,
    max_runtime_seconds=Decimal("60"),
    max_candidates=5,
    max_dispatches=1,
) -> Stage30_11RuntimeGateConfig:
    return Stage30_11RuntimeGateConfig(
        max_runtime_seconds=max_runtime_seconds,
        max_candidates=max_candidates,
        max_dispatches=max_dispatches,
        created_at_utc="2026-01-01T00:00:00Z",
    )


def _outcome() -> Stage30_11RuntimeGateCandidateOutcome:
    return Stage30_11RuntimeGateCandidateOutcome(
        candidate_id="cand-1",
        token_mint="mint-1",
        bridge_decision="BRIDGED_TO_LIVE_GATE_INPUT",
        gate_decision="PASS_TO_DISPATCH",
        runtime_decision=RUNTIME_DECISION_DISPATCHED_AFTER_DIP_GATE_PASS,
        runtime_reason=RUNTIME_REASON_PASS_TO_FAKE_DISPATCH,
        dispatch_attempted=True,
        dispatch_accepted=True,
        created_at_utc="2026-01-02T00:00:00Z",
    )


def _summary() -> Stage30_11RuntimeGateSummary:
    return Stage30_11RuntimeGateSummary(
        candidates_seen=5,
        bridged=2,
        gate_passed=1,
        dispatch_attempted=1,
        dispatch_accepted=1,
        suppressed_by_bridge=3,
        suppressed_by_gate=1,
        stopped_by_candidate_cap=0,
        stopped_by_dispatch_cap=0,
        stopped_by_runtime_seconds=0,
        invalid_inputs=1,
        created_at_utc="2026-01-01T00:00:00Z",
    )


def _result() -> Stage30_11FakeDispatchResult:
    return Stage30_11FakeDispatchResult(
        accepted=True,
        candidate_id="cand-1",
        token_mint="mint-1",
        created_at_utc="2026-01-01T00:00:00Z",
    )


# ---------------------------------------------------------------------------
# Version + schema identity
# ---------------------------------------------------------------------------


def test_minor_version_pinned() -> None:
    assert STAGE30_11_2_MINOR_VERSION == "30.11.2"


def test_runtime_gate_schema_version_pinned() -> None:
    assert STAGE30_11_2_RUNTIME_GATE_SCHEMA_VERSION == (
        "stage30_11_2_v0_runtime_gate_seam"
    )


# ---------------------------------------------------------------------------
# Closed-set decisions + reasons
# ---------------------------------------------------------------------------


def test_runtime_decisions_are_the_closed_set() -> None:
    assert STAGE30_11_2_RUNTIME_DECISIONS == (
        "DISPATCHED_AFTER_DIP_GATE_PASS",
        "SUPPRESSED_BY_BRIDGE",
        "SUPPRESSED_BY_DIP_GATE",
        "STOPPED_BY_CANDIDATE_CAP",
        "STOPPED_BY_DISPATCH_CAP",
        "STOPPED_BY_RUNTIME_SECONDS",
        "INVALID_RUNTIME_INPUT",
    )
    assert STAGE30_11_2_RUNTIME_DISPATCH_DECISION == (
        "DISPATCHED_AFTER_DIP_GATE_PASS"
    )
    # The token constants equal the closed-set values verbatim.
    assert RUNTIME_DECISION_DISPATCHED_AFTER_DIP_GATE_PASS == (
        "DISPATCHED_AFTER_DIP_GATE_PASS"
    )
    assert RUNTIME_DECISION_SUPPRESSED_BY_BRIDGE == "SUPPRESSED_BY_BRIDGE"
    assert RUNTIME_DECISION_SUPPRESSED_BY_DIP_GATE == "SUPPRESSED_BY_DIP_GATE"
    assert RUNTIME_DECISION_STOPPED_BY_CANDIDATE_CAP == (
        "STOPPED_BY_CANDIDATE_CAP"
    )
    assert RUNTIME_DECISION_STOPPED_BY_DISPATCH_CAP == (
        "STOPPED_BY_DISPATCH_CAP"
    )
    assert RUNTIME_DECISION_STOPPED_BY_RUNTIME_SECONDS == (
        "STOPPED_BY_RUNTIME_SECONDS"
    )
    assert RUNTIME_DECISION_INVALID_RUNTIME_INPUT == "INVALID_RUNTIME_INPUT"


def test_runtime_reasons_are_the_closed_set() -> None:
    assert STAGE30_11_2_RUNTIME_REASONS == (
        "PASS_TO_FAKE_DISPATCH",
        "BRIDGE_SKIPPED_OR_INVALID",
        "DIP_GATE_SKIPPED",
        "CANDIDATE_CAP_REACHED",
        "DISPATCH_CAP_REACHED",
        "RUNTIME_SECONDS_REACHED",
        "INVALID_CONFIG_OR_INPUT",
    )
    assert STAGE30_11_2_RUNTIME_DISPATCH_REASON == "PASS_TO_FAKE_DISPATCH"
    assert RUNTIME_REASON_PASS_TO_FAKE_DISPATCH == "PASS_TO_FAKE_DISPATCH"
    assert RUNTIME_REASON_BRIDGE_SKIPPED_OR_INVALID == (
        "BRIDGE_SKIPPED_OR_INVALID"
    )
    assert RUNTIME_REASON_DIP_GATE_SKIPPED == "DIP_GATE_SKIPPED"
    assert RUNTIME_REASON_CANDIDATE_CAP_REACHED == "CANDIDATE_CAP_REACHED"
    assert RUNTIME_REASON_DISPATCH_CAP_REACHED == "DISPATCH_CAP_REACHED"
    assert RUNTIME_REASON_RUNTIME_SECONDS_REACHED == "RUNTIME_SECONDS_REACHED"
    assert RUNTIME_REASON_INVALID_CONFIG_OR_INPUT == "INVALID_CONFIG_OR_INPUT"


def test_decisions_and_reasons_have_seven_members_each() -> None:
    assert len(STAGE30_11_2_RUNTIME_DECISIONS) == 7
    assert len(STAGE30_11_2_RUNTIME_REASONS) == 7
    assert len(set(STAGE30_11_2_RUNTIME_DECISIONS)) == 7
    assert len(set(STAGE30_11_2_RUNTIME_REASONS)) == 7


def test_is_runtime_decision_is_total_and_closed() -> None:
    for decision in STAGE30_11_2_RUNTIME_DECISIONS:
        assert is_runtime_decision(decision)
    for bad in ("PASS_TO_DISPATCH", "NOT_EVALUATED", "", "dispatched", None, 7):
        assert not is_runtime_decision(bad)


def test_is_runtime_reason_is_total_and_closed() -> None:
    for reason in STAGE30_11_2_RUNTIME_REASONS:
        assert is_runtime_reason(reason)
    for bad in ("ELIGIBLE_DIP", "NOT_EVALUATED", "", "pass", None, 7):
        assert not is_runtime_reason(bad)


def test_not_evaluated_sentinel_is_not_a_decision_or_reason() -> None:
    assert STAGE30_11_2_NOT_EVALUATED == "NOT_EVALUATED"
    # The sentinel must never be mistaken for a real verdict.
    assert not is_runtime_decision(STAGE30_11_2_NOT_EVALUATED)
    assert not is_runtime_reason(STAGE30_11_2_NOT_EVALUATED)
    assert STAGE30_11_2_NOT_EVALUATED not in STAGE30_11_2_RUNTIME_DECISIONS


# ---------------------------------------------------------------------------
# Config validator (fail closed)
# ---------------------------------------------------------------------------


def test_valid_config_passes() -> None:
    assert is_valid_runtime_gate_config(_config())
    # max_dispatches == 0 is a valid (nonnegative) bounded config.
    assert is_valid_runtime_gate_config(_config(max_dispatches=0))
    # int seconds also accepted.
    assert is_valid_runtime_gate_config(_config(max_runtime_seconds=60))


def test_invalid_config_fails_closed() -> None:
    # Non-positive wall-clock bound.
    assert not is_valid_runtime_gate_config(
        _config(max_runtime_seconds=Decimal("0"))
    )
    assert not is_valid_runtime_gate_config(
        _config(max_runtime_seconds=Decimal("-1"))
    )
    # Non-positive candidate cap.
    assert not is_valid_runtime_gate_config(_config(max_candidates=0))
    assert not is_valid_runtime_gate_config(_config(max_candidates=-1))
    # Negative dispatch cap.
    assert not is_valid_runtime_gate_config(_config(max_dispatches=-1))
    # Wrong types / bools.
    assert not is_valid_runtime_gate_config(_config(max_candidates=True))
    assert not is_valid_runtime_gate_config(_config(max_dispatches=True))
    assert not is_valid_runtime_gate_config(
        _config(max_runtime_seconds=True)
    )
    assert not is_valid_runtime_gate_config(
        _config(max_candidates=Decimal("5"))
    )
    # Non-config objects.
    for bad in (None, "config", 7, {"max_candidates": 1}, object()):
        assert not is_valid_runtime_gate_config(bad)


# ---------------------------------------------------------------------------
# Config validator -- non-finite / float / total (fail closed, never raises)
# ---------------------------------------------------------------------------
#
# The audit-suggested malformed numeric values: non-finite Decimals (incl. the
# SIGNALING ``sNaN``, which would raise ``decimal.InvalidOperation`` on a naive
# ``> 0`` comparison), the non-finite floats, and the bools. The validator must
# reject every one of them WITHOUT any exception escaping, for EACH numeric
# field independently.
_NON_FINITE_DECIMALS = (
    Decimal("NaN"),
    Decimal("sNaN"),
    Decimal("Infinity"),
    Decimal("-Infinity"),
)
_NON_FINITE_FLOATS = (float("nan"), float("inf"), float("-inf"))
_AUDIT_BAD_NUMERIC_VALUES = (
    _NON_FINITE_DECIMALS + _NON_FINITE_FLOATS + (True, False)
)


@pytest.mark.parametrize("bad", _AUDIT_BAD_NUMERIC_VALUES)
def test_non_finite_max_runtime_seconds_is_invalid(bad) -> None:
    # A non-finite Decimal / float / bool wall-clock bound is rejected and the
    # validator stays TOTAL (no InvalidOperation / TypeError / ValueError).
    assert is_valid_runtime_gate_config(
        _config(max_runtime_seconds=bad)
    ) is False


@pytest.mark.parametrize("bad", _AUDIT_BAD_NUMERIC_VALUES)
def test_non_finite_max_candidates_is_invalid(bad) -> None:
    # ``max_candidates`` accepts only a positive ``int``; a non-finite Decimal /
    # float / bool is rejected by ``isinstance`` (it never reaches a comparison).
    assert is_valid_runtime_gate_config(_config(max_candidates=bad)) is False


@pytest.mark.parametrize("bad", _AUDIT_BAD_NUMERIC_VALUES)
def test_non_finite_max_dispatches_is_invalid(bad) -> None:
    # ``max_dispatches`` accepts only a non-negative ``int``; a non-finite
    # Decimal / float / bool is rejected without a comparison.
    assert is_valid_runtime_gate_config(_config(max_dispatches=bad)) is False


def test_infinity_is_not_accepted_as_a_positive_bound() -> None:
    # A positive ``> 0`` Decimal Infinity must NOT be accepted (it would defeat
    # the deterministic max_runtime_seconds bound).
    assert is_valid_runtime_gate_config(
        _config(max_runtime_seconds=Decimal("Infinity"))
    ) is False


def test_validator_is_total_and_returns_bool_for_all_audit_cases() -> None:
    # Across every numeric field, the validator returns a real ``bool`` and
    # never raises for any audit-suggested malformed value. A finite positive
    # baseline still validates True.
    assert is_valid_runtime_gate_config(_config()) is True
    for bad in _AUDIT_BAD_NUMERIC_VALUES:
        for cfg in (
            _config(max_runtime_seconds=bad),
            _config(max_candidates=bad),
            _config(max_dispatches=bad),
        ):
            result = is_valid_runtime_gate_config(cfg)
            assert isinstance(result, bool)
            assert result is False


# ---------------------------------------------------------------------------
# Field names (order matters)
# ---------------------------------------------------------------------------


def test_config_field_names() -> None:
    assert runtime_gate_config_field_names() == (
        "max_runtime_seconds",
        "max_candidates",
        "max_dispatches",
        "created_at_utc",
    )


def test_outcome_field_names() -> None:
    assert runtime_gate_candidate_outcome_field_names() == (
        "candidate_id",
        "token_mint",
        "bridge_decision",
        "gate_decision",
        "runtime_decision",
        "runtime_reason",
        "dispatch_attempted",
        "dispatch_accepted",
        "created_at_utc",
    )


def test_summary_field_names() -> None:
    assert runtime_gate_summary_field_names() == (
        "candidates_seen",
        "bridged",
        "gate_passed",
        "dispatch_attempted",
        "dispatch_accepted",
        "suppressed_by_bridge",
        "suppressed_by_gate",
        "stopped_by_candidate_cap",
        "stopped_by_dispatch_cap",
        "stopped_by_runtime_seconds",
        "invalid_inputs",
        "created_at_utc",
    )


def test_fake_dispatch_result_field_names() -> None:
    assert fake_dispatch_result_field_names() == (
        "accepted",
        "candidate_id",
        "token_mint",
        "created_at_utc",
    )


def test_no_secret_or_payload_field_names() -> None:
    all_fields = (
        runtime_gate_config_field_names()
        + runtime_gate_candidate_outcome_field_names()
        + runtime_gate_summary_field_names()
        + fake_dispatch_result_field_names()
    )
    for name in all_fields:
        lower = name.lower()
        for forbidden in (
            "webhook",
            "api_key",
            "bearer",
            "authorization",
            "secret",
            "raw_payload",
            "getenv",
            "environ",
            "url",
            "host",
        ):
            assert forbidden not in lower, (
                f"Stage 30.11.2 field {name!r} carries forbidden substring "
                f"{forbidden!r}"
            )


# ---------------------------------------------------------------------------
# Construction echoes
# ---------------------------------------------------------------------------


def test_config_echoes_fields() -> None:
    cfg = _config(max_runtime_seconds=Decimal("90"), max_candidates=7, max_dispatches=2)
    assert cfg.max_runtime_seconds == Decimal("90")
    assert cfg.max_candidates == 7
    assert cfg.max_dispatches == 2
    assert cfg.created_at_utc == "2026-01-01T00:00:00Z"


def test_outcome_echoes_fields() -> None:
    out = _outcome()
    assert out.candidate_id == "cand-1"
    assert out.token_mint == "mint-1"
    assert out.runtime_decision == "DISPATCHED_AFTER_DIP_GATE_PASS"
    assert out.runtime_reason == "PASS_TO_FAKE_DISPATCH"
    assert out.dispatch_attempted is True
    assert out.dispatch_accepted is True


def test_summary_echoes_counts() -> None:
    summary = _summary()
    assert summary.candidates_seen == 5
    assert summary.bridged == 2
    assert summary.gate_passed == 1
    assert summary.dispatch_attempted == 1
    assert summary.dispatch_accepted == 1
    assert summary.suppressed_by_bridge == 3
    assert summary.suppressed_by_gate == 1
    assert summary.invalid_inputs == 1
    assert summary.stopped_by_candidate_cap == 0
    assert summary.stopped_by_dispatch_cap == 0
    assert summary.stopped_by_runtime_seconds == 0


def test_fake_result_echoes_fields() -> None:
    result = _result()
    assert result.accepted is True
    assert result.candidate_id == "cand-1"
    assert result.token_mint == "mint-1"
    assert result.created_at_utc == "2026-01-01T00:00:00Z"


# ---------------------------------------------------------------------------
# Immutability
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "model", [_config(), _outcome(), _summary(), _result()]
)
def test_models_are_frozen(model: object) -> None:
    # A frozen dataclass raises FrozenInstanceError on any attribute set.
    with pytest.raises(FrozenInstanceError):
        setattr(model, "created_at_utc", "mutated")

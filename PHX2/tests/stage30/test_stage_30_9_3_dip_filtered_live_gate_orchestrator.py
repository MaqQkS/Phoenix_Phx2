"""Stage 30.9.3 dip-filtered live gate orchestrator unit tests.

Pins the bounded orchestrator behavior: only ``PASS_TO_DISPATCH`` candidates
reserve a dispatch / call the injected sink; ``SKIP_BEFORE_DISPATCH`` /
``INVALID_INPUT`` candidates are suppressed BEFORE reservation (never reserved,
never handed to the sink); the dispatch / private-send / evaluation caps are
honored; there is NO bypass path on which the sink is called for a non-pass
candidate; and the result's transport-safety negatives are always 0. Fake /
offline only; the dispatch sink is an in-memory fake -- no live call, no
provider, no Discord, no env read.
"""

from __future__ import annotations

from decimal import Decimal
from typing import List, Tuple

from PHX2.stage30.stage30_9_3_dip_filtered_live_gate_models import (
    Stage30_9_3LiveGateDecision,
    Stage30_9_3LiveGateInput,
)
from PHX2.stage30.stage30_9_3_dip_filtered_live_gate_orchestrator import (
    run_dip_filtered_live_gate_integration,
)

_CREATED_AT: str = "2026-01-01T00:00:00Z"
_RESULT_AT: str = "2026-01-01T00:05:00Z"


class _RecordingSink:
    def __init__(self) -> None:
        self.calls: List[Stage30_9_3LiveGateDecision] = []

    def __call__(self, decision: Stage30_9_3LiveGateDecision) -> None:
        self.calls.append(decision)


class _PassOnlySink:
    """A sink that fails the test if it is ever handed a non-pass decision."""

    def __init__(self) -> None:
        self.calls: List[Stage30_9_3LiveGateDecision] = []

    def __call__(self, decision: Stage30_9_3LiveGateDecision) -> None:
        assert decision.gate_decision == "PASS_TO_DISPATCH", (
            "the dispatch sink must NEVER be called for a non-pass candidate; "
            f"got {decision.gate_decision!r}"
        )
        assert decision.dispatch_reservation_allowed is True
        self.calls.append(decision)


def _mk(**overrides: object) -> Stage30_9_3LiveGateInput:
    base = dict(
        candidate_id="cand-1",
        token_mint="mint-1",
        tier_token="Tier 1",
        drawdown_from_ath=Decimal("0.55"),
        migration_status="PRESENT",
        ath_status="PRESENT",
        market_context_status="PRESENT",
        current_market_cap_usd=Decimal("12345.67"),
        post_migration_ath_verified=True,
        candidate_ref="ref",
        created_at_utc=_CREATED_AT,
    )
    base.update(overrides)
    return Stage30_9_3LiveGateInput(**base)  # type: ignore[arg-type]


def _dip(n: int) -> Stage30_9_3LiveGateInput:
    return _mk(candidate_id=f"dip-{n}", token_mint=f"mint-dip-{n}")


def _non_dip(n: int) -> Stage30_9_3LiveGateInput:
    return _mk(
        candidate_id=f"skip-{n}",
        token_mint=f"mint-skip-{n}",
        tier_token="Tier Unknown",
    )


def _invalid(n: int) -> Stage30_9_3LiveGateInput:
    return _mk(candidate_id="", token_mint=f"mint-invalid-{n}")


def _run(
    live_inputs: Tuple[Stage30_9_3LiveGateInput, ...],
    *,
    sink: object,
    max_candidates_evaluated: int = 16,
    max_dispatches: int = 1,
    max_private_discord_sends: int = 1,
):
    return run_dip_filtered_live_gate_integration(
        live_inputs=live_inputs,
        dispatch_sink=sink,  # type: ignore[arg-type]
        max_candidates_evaluated=max_candidates_evaluated,
        max_dispatches=max_dispatches,
        max_private_discord_sends=max_private_discord_sends,
        created_at_utc=_RESULT_AT,
    )


# ---------------------------------------------------------------------------
# Single eligible dip -> one dispatch
# ---------------------------------------------------------------------------


def test_single_dip_reserves_and_calls_sink_once() -> None:
    sink = _RecordingSink()
    decisions, result = _run((_dip(1),), sink=sink)
    assert len(sink.calls) == 1
    assert result.candidates_passed_gate == 1
    assert result.dispatch_attempts_reserved == 1
    assert result.would_send_private_discord_count == 1
    assert result.candidates_skipped_before_dispatch == 0
    assert result.invalid_inputs == 0
    assert len(decisions) == 1
    assert decisions[0].gate_decision == "PASS_TO_DISPATCH"
    assert result.created_at_utc == _RESULT_AT


# ---------------------------------------------------------------------------
# Non-dip / invalid -> suppressed before dispatch, sink not called
# ---------------------------------------------------------------------------


def test_non_dip_skips_before_dispatch_no_sink() -> None:
    sink = _RecordingSink()
    decisions, result = _run((_non_dip(1),), sink=sink)
    assert sink.calls == []
    assert result.candidates_passed_gate == 0
    assert result.candidates_skipped_before_dispatch == 1
    assert result.dispatch_attempts_reserved == 0
    assert result.would_send_private_discord_count == 0
    assert decisions[0].gate_decision == "SKIP_BEFORE_DISPATCH"
    assert decisions[0].suppressed_before_dispatch_reservation is True


def test_invalid_skips_before_dispatch_no_sink() -> None:
    sink = _RecordingSink()
    decisions, result = _run((_invalid(1),), sink=sink)
    assert sink.calls == []
    assert result.candidates_passed_gate == 0
    assert result.invalid_inputs == 1
    assert result.dispatch_attempts_reserved == 0
    assert result.would_send_private_discord_count == 0
    assert decisions[0].gate_decision == "INVALID_INPUT"


# ---------------------------------------------------------------------------
# Dispatch cap of 1 stops after the first passed candidate
# ---------------------------------------------------------------------------


def test_dispatch_cap_of_one_stops_after_first_pass() -> None:
    sink = _RecordingSink()
    # Three eligible dips, but max_dispatches=1: only the first is dispatched
    # and the run stops (the other two are never evaluated).
    decisions, result = _run(
        (_dip(1), _dip(2), _dip(3)), sink=sink, max_dispatches=1
    )
    assert len(sink.calls) == 1
    assert result.dispatch_attempts_reserved == 1
    assert result.would_send_private_discord_count == 1
    assert result.candidates_passed_gate == 1
    assert result.candidates_seen == 1
    assert result.candidates_evaluated == 1
    assert len(decisions) == 1


def test_private_send_cap_of_one_stops_after_first_pass() -> None:
    sink = _RecordingSink()
    # A generous dispatch cap but a private-send cap of 1 must still stop after
    # the first eligible dip.
    _decisions, result = _run(
        (_dip(1), _dip(2), _dip(3)),
        sink=sink,
        max_dispatches=9,
        max_private_discord_sends=1,
    )
    assert len(sink.calls) == 1
    assert result.would_send_private_discord_count == 1
    assert result.dispatch_attempts_reserved == 1


# ---------------------------------------------------------------------------
# Skips/invalid before the dip are all evaluated; one dip dispatched
# ---------------------------------------------------------------------------


def test_mixed_stream_skips_then_one_dispatch() -> None:
    sink = _PassOnlySink()
    stream = (_non_dip(1), _invalid(1), _non_dip(2), _dip(1))
    _decisions, result = _run(stream, sink=sink, max_dispatches=1)
    # The two non-dips + one invalid are evaluated and suppressed; then the dip
    # passes, dispatches once, and the run stops.
    assert len(sink.calls) == 1
    assert result.candidates_seen == 4
    assert result.candidates_evaluated == 4
    assert result.candidates_passed_gate == 1
    assert result.candidates_skipped_before_dispatch == 2
    assert result.invalid_inputs == 1
    assert result.dispatch_attempts_reserved == 1
    assert result.would_send_private_discord_count == 1


# ---------------------------------------------------------------------------
# No-dip stream -> zero dispatch (NO_DIP_FOUND_BUT_SAFE)
# ---------------------------------------------------------------------------


def test_no_dip_stream_zero_dispatch_all_suppressed() -> None:
    sink = _PassOnlySink()
    stream = (_non_dip(1), _non_dip(2), _non_dip(3), _invalid(1))
    _decisions, result = _run(stream, sink=sink, max_dispatches=1)
    assert sink.calls == []
    assert result.candidates_passed_gate == 0
    assert result.candidates_skipped_before_dispatch == 3
    assert result.invalid_inputs == 1
    assert result.dispatch_attempts_reserved == 0
    assert result.would_send_private_discord_count == 0


# ---------------------------------------------------------------------------
# Evaluation cap
# ---------------------------------------------------------------------------


def test_max_candidates_evaluated_cap_stops_evaluation() -> None:
    sink = _RecordingSink()
    # Five non-dips but a cap of 2: only two are evaluated.
    stream = tuple(_non_dip(n) for n in range(5))
    _decisions, result = _run(
        stream, sink=sink, max_candidates_evaluated=2, max_dispatches=1
    )
    assert result.candidates_seen == 2
    assert result.candidates_evaluated == 2
    assert result.candidates_skipped_before_dispatch == 2
    assert result.dispatch_attempts_reserved == 0


# ---------------------------------------------------------------------------
# Result invariants: transport-safety negatives always 0
# ---------------------------------------------------------------------------


def test_result_transport_safety_counts_always_zero() -> None:
    sink = _RecordingSink()
    stream = (_dip(1), _non_dip(1), _invalid(1))
    _decisions, result = _run(stream, sink=sink, max_dispatches=9)
    assert result.dispatch_failures_recorded == 0
    assert result.transport_veto_count == 0
    assert result.payload_refused_count == 0
    # would_send equals reserved equals the number of sink calls.
    assert (
        result.would_send_private_discord_count
        == result.dispatch_attempts_reserved
        == len(sink.calls)
    )


def test_empty_stream_is_safe_zero() -> None:
    sink = _RecordingSink()
    decisions, result = _run(tuple(), sink=sink)
    assert decisions == tuple()
    assert result.candidates_seen == 0
    assert result.candidates_evaluated == 0
    assert result.dispatch_attempts_reserved == 0
    assert result.would_send_private_discord_count == 0
    assert sink.calls == []

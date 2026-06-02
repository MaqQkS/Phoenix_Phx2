"""Stage 30.11.2 runtime gate seam behavior tests.

Pins the pure, bounded, fail-closed runtime seam:

  * a valid dip-context candidate bridges, passes the committed dip gate, and is
    the ONLY candidate the injected fake dispatch sink is called for
    (DISPATCHED_AFTER_DIP_GATE_PASS / PASS_TO_FAKE_DISPATCH),
  * a valid NON-dip candidate bridges but is suppressed BEFORE dispatch
    (SUPPRESSED_BY_DIP_GATE; the sink is never called),
  * a missing-context candidate is suppressed by the bridge
    (SUPPRESSED_BY_BRIDGE; the sink is never called),
  * a malformed candidate fails closed (SUPPRESSED_BY_BRIDGE + invalid input;
    the sink is never called),
  * a non-conforming stream item fails closed (INVALID_RUNTIME_INPUT; the sink
    is never called, no exception escapes),
  * the dispatch / candidate / wall-clock bounds each stop the run cleanly with a
    single STOPPED outcome,
  * the wall-clock bound is enforced via the INJECTED clock only,
  * an invalid config fails closed by raising BEFORE any dispatch, and
  * the seam reserves no real dispatch and sends no Discord.

Fake / offline only; no live call, no provider, no Discord, no env read, no
wall-clock read (the clock is injected).
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from PHX2.stage30.stage30_9_3_dip_filtered_live_gate_models import (
    Stage30_9_3LiveGateInput,
)
from PHX2.stage30.stage30_11_1_live_candidate_bridge_models import (
    Stage30_11LiveCandidateSnapshot,
)
from PHX2.stage30.stage30_11_2_fake_runtime_gate_proof import (
    Stage30_11RecordingFakeDispatchSink,
    make_constant_clock,
    make_sequence_clock,
)
from PHX2.stage30.stage30_11_2_runtime_gate_models import (
    Stage30_11RuntimeGateCandidateOutcome,
    Stage30_11RuntimeGateConfig,
    Stage30_11RuntimeGateSummary,
)
from PHX2.stage30.stage30_11_2_runtime_gate_seam import (
    Stage30_11RuntimeGateError,
    run_stage30_11_runtime_gate_seam,
)


_CREATED_AT: str = "2026-02-02T00:00:00Z"
_SNAPSHOT_CLOCK: str = "2026-01-01T00:00:00Z"


def _snapshot(
    *,
    candidate_id: str = "cand-1",
    token_mint: str = "mint-1",
    tier_hint=None,
    drawdown_from_ath=Decimal("0.55"),
    migration_status="PRESENT",
    ath_status="PRESENT",
    market_context_status="PRESENT",
    current_market_cap_usd=Decimal("12345.67"),
    post_migration_ath_verified=True,
    source_ref="ref-1",
) -> Stage30_11LiveCandidateSnapshot:
    return Stage30_11LiveCandidateSnapshot(
        candidate_id=candidate_id,
        token_mint=token_mint,
        pair_type="SOL",
        tier_hint=tier_hint,
        drawdown_from_ath=drawdown_from_ath,
        migration_status=migration_status,
        ath_status=ath_status,
        market_context_status=market_context_status,
        current_market_cap_usd=current_market_cap_usd,
        post_migration_ath_verified=post_migration_ath_verified,
        source_ref=source_ref,
        created_at_utc=_SNAPSHOT_CLOCK,
    )


def _config(
    *,
    max_runtime_seconds=Decimal("3600"),
    max_candidates=100,
    max_dispatches=100,
) -> Stage30_11RuntimeGateConfig:
    return Stage30_11RuntimeGateConfig(
        max_runtime_seconds=max_runtime_seconds,
        max_candidates=max_candidates,
        max_dispatches=max_dispatches,
        created_at_utc=_CREATED_AT,
    )


class _RaisingSink:
    """A dispatch sink that fails the test if it is ever called. Used to PROVE
    that non-PASS candidates never reach the sink.
    """

    def __call__(
        self, gate_input: Stage30_9_3LiveGateInput
    ) -> Stage30_9_3LiveGateInput:
        raise AssertionError(
            "dispatch sink must NOT be called for a non-PASS candidate"
        )


class _CountingClock:
    """A constant injected clock that counts how many times it was sampled."""

    def __init__(self, value: Decimal) -> None:
        self._value = value
        self.calls = 0

    def __call__(self) -> Decimal:
        self.calls += 1
        return self._value


def _run(candidates, *, config=None, sink=None, now_seconds=None):
    cfg = config if config is not None else _config()
    the_sink = (
        sink
        if sink is not None
        else Stage30_11RecordingFakeDispatchSink(created_at_utc=_CREATED_AT)
    )
    clock = now_seconds if now_seconds is not None else make_constant_clock(Decimal(0))
    outcomes, summary = run_stage30_11_runtime_gate_seam(
        candidates,
        config=cfg,
        dispatch_sink=the_sink,
        now_seconds=clock,
        created_at_utc=_CREATED_AT,
    )
    return outcomes, summary, the_sink


# ---------------------------------------------------------------------------
# 1. Return shape
# ---------------------------------------------------------------------------


def test_returns_outcomes_tuple_and_summary() -> None:
    outcomes, summary, _sink = _run((_snapshot(tier_hint="Tier 1"),))
    assert isinstance(outcomes, tuple)
    assert all(
        isinstance(o, Stage30_11RuntimeGateCandidateOutcome) for o in outcomes
    )
    assert isinstance(summary, Stage30_11RuntimeGateSummary)
    assert summary.created_at_utc == _CREATED_AT


def test_empty_stream_yields_empty_outcomes_and_zero_summary() -> None:
    outcomes, summary, sink = _run((), sink=_RaisingSink())
    assert outcomes == ()
    assert summary.candidates_seen == 0
    assert summary.bridged == 0
    assert summary.dispatch_attempted == 0
    assert summary.invalid_inputs == 0


# ---------------------------------------------------------------------------
# 2. Valid dip candidate -> the ONLY dispatch
# ---------------------------------------------------------------------------


def test_valid_dip_candidate_dispatches_once() -> None:
    sink = Stage30_11RecordingFakeDispatchSink(created_at_utc=_CREATED_AT)
    outcomes, summary, _sink = _run(
        (_snapshot(candidate_id="dip", token_mint="m-dip", tier_hint="Tier 1"),),
        sink=sink,
    )
    assert len(outcomes) == 1
    out = outcomes[0]
    assert out.runtime_decision == "DISPATCHED_AFTER_DIP_GATE_PASS"
    assert out.runtime_reason == "PASS_TO_FAKE_DISPATCH"
    assert out.bridge_decision == "BRIDGED_TO_LIVE_GATE_INPUT"
    assert out.gate_decision == "PASS_TO_DISPATCH"
    assert out.dispatch_attempted is True
    assert out.dispatch_accepted is True
    assert out.candidate_id == "dip"
    # The sink was called exactly once, with the bridged candidate's identity.
    assert sink.attempted == 1
    assert sink.accepted == 1
    assert sink.candidate_ids == ["dip"]
    assert sink.token_mints == ["m-dip"]
    assert summary.gate_passed == 1
    assert summary.dispatch_attempted == 1
    assert summary.dispatch_accepted == 1


def test_rejecting_sink_records_attempt_but_not_accept() -> None:
    sink = Stage30_11RecordingFakeDispatchSink(
        created_at_utc=_CREATED_AT, accept=False
    )
    outcomes, summary, _sink = _run(
        (_snapshot(tier_hint="Tier 1"),), sink=sink
    )
    out = outcomes[0]
    assert out.runtime_decision == "DISPATCHED_AFTER_DIP_GATE_PASS"
    assert out.dispatch_attempted is True
    assert out.dispatch_accepted is False
    assert summary.dispatch_attempted == 1
    assert summary.dispatch_accepted == 0
    assert sink.attempted == 1
    assert sink.accepted == 0


# ---------------------------------------------------------------------------
# 3. Non-dip / bridge-skip / invalid / non-snapshot never dispatch
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "tier_hint", ["Tier Unknown", "Tier Not Applicable", None]
)
def test_non_dip_candidate_suppressed_by_gate_no_dispatch(tier_hint) -> None:
    # A bridged but non-dip candidate (Tier Unknown / Not Applicable / no tier)
    # is suppressed BEFORE the sink; the raising sink proves the sink is never
    # called. (The committed gate rules every numbered tier an eligible dip, so
    # only the unknown / not-applicable / absent tiers skip.)
    outcomes, summary, _sink = _run(
        (_snapshot(tier_hint=tier_hint),), sink=_RaisingSink()
    )
    out = outcomes[0]
    assert out.runtime_decision == "SUPPRESSED_BY_DIP_GATE"
    assert out.runtime_reason == "DIP_GATE_SKIPPED"
    assert out.bridge_decision == "BRIDGED_TO_LIVE_GATE_INPUT"
    assert out.gate_decision != "PASS_TO_DISPATCH"
    assert out.dispatch_attempted is False
    assert out.dispatch_accepted is False
    assert summary.bridged == 1
    assert summary.gate_passed == 0
    assert summary.suppressed_by_gate == 1
    assert summary.dispatch_attempted == 0


def test_missing_context_suppressed_by_bridge_no_dispatch() -> None:
    for kwargs in (
        {"ath_status": None},
        {"migration_status": None},
        {"market_context_status": None},
    ):
        outcomes, summary, _sink = _run(
            (_snapshot(**kwargs),), sink=_RaisingSink()
        )
        out = outcomes[0]
        assert out.runtime_decision == "SUPPRESSED_BY_BRIDGE"
        assert out.runtime_reason == "BRIDGE_SKIPPED_OR_INVALID"
        assert out.bridge_decision == "SKIPPED_MISSING_REQUIRED_CONTEXT"
        assert out.gate_decision == "NOT_EVALUATED"
        assert out.dispatch_attempted is False
        assert summary.suppressed_by_bridge == 1
        assert summary.bridged == 0
        assert summary.invalid_inputs == 0


def test_malformed_candidate_suppressed_by_bridge_and_invalid() -> None:
    for kwargs in ({"candidate_id": ""}, {"token_mint": "   "}):
        outcomes, summary, _sink = _run(
            (_snapshot(**kwargs),), sink=_RaisingSink()
        )
        out = outcomes[0]
        assert out.runtime_decision == "SUPPRESSED_BY_BRIDGE"
        assert out.bridge_decision == "INVALID_BRIDGE_INPUT"
        assert out.dispatch_attempted is False
        # A bridge-invalid candidate is both suppressed-by-bridge AND an
        # invalid input.
        assert summary.suppressed_by_bridge == 1
        assert summary.invalid_inputs == 1
        assert summary.bridged == 0


def test_non_snapshot_stream_item_is_invalid_runtime_input_no_dispatch() -> None:
    outcomes, summary, _sink = _run(
        ("not-a-snapshot", 7, None), sink=_RaisingSink()
    )
    assert [o.runtime_decision for o in outcomes] == [
        "INVALID_RUNTIME_INPUT",
        "INVALID_RUNTIME_INPUT",
        "INVALID_RUNTIME_INPUT",
    ]
    for out in outcomes:
        assert out.runtime_reason == "INVALID_CONFIG_OR_INPUT"
        assert out.bridge_decision == "NOT_EVALUATED"
        assert out.gate_decision == "NOT_EVALUATED"
        assert out.candidate_id == ""
        assert out.token_mint == ""
        assert out.dispatch_attempted is False
    assert summary.candidates_seen == 3
    assert summary.invalid_inputs == 3
    assert summary.bridged == 0
    assert summary.dispatch_attempted == 0


# ---------------------------------------------------------------------------
# 4. Mixed stream accounting (the baseline partition)
# ---------------------------------------------------------------------------


def _mixed_stream():
    return (
        _snapshot(candidate_id="dip", token_mint="m-dip", tier_hint="Tier 1"),
        _snapshot(candidate_id="non", token_mint="m-non", tier_hint="Tier Unknown"),
        _snapshot(candidate_id="no-ath", token_mint="m-no-ath", ath_status=None),
        _snapshot(candidate_id="no-mig", token_mint="m-no-mig", migration_status=None),
        _snapshot(candidate_id="", token_mint="m-bad"),
    )


def test_mixed_stream_partition_and_single_dispatch() -> None:
    sink = Stage30_11RecordingFakeDispatchSink(created_at_utc=_CREATED_AT)
    outcomes, summary, _sink = _run(_mixed_stream(), sink=sink)
    assert [o.runtime_decision for o in outcomes] == [
        "DISPATCHED_AFTER_DIP_GATE_PASS",
        "SUPPRESSED_BY_DIP_GATE",
        "SUPPRESSED_BY_BRIDGE",
        "SUPPRESSED_BY_BRIDGE",
        "SUPPRESSED_BY_BRIDGE",
    ]
    assert summary.candidates_seen == 5
    assert summary.bridged == 2
    assert summary.gate_passed == 1
    assert summary.dispatch_attempted == 1
    assert summary.dispatch_accepted == 1
    assert summary.suppressed_by_bridge == 3
    assert summary.suppressed_by_gate == 1
    assert summary.invalid_inputs == 1
    # Partition invariants.
    assert summary.bridged + summary.suppressed_by_bridge == summary.candidates_seen
    assert summary.gate_passed + summary.suppressed_by_gate == summary.bridged
    # Exactly one dispatch, only the dip.
    assert sink.attempted == 1
    assert sink.candidate_ids == ["dip"]


# ---------------------------------------------------------------------------
# 5. Bounds: dispatch cap / candidate cap / wall-clock (injected clock)
# ---------------------------------------------------------------------------


def test_max_dispatches_stops_after_first_pass() -> None:
    sink = Stage30_11RecordingFakeDispatchSink(created_at_utc=_CREATED_AT)
    outcomes, summary, _sink = _run(
        _mixed_stream(), config=_config(max_dispatches=1), sink=sink
    )
    # The dip dispatches; the next candidate trips the dispatch cap and stops.
    assert outcomes[0].runtime_decision == "DISPATCHED_AFTER_DIP_GATE_PASS"
    assert outcomes[-1].runtime_decision == "STOPPED_BY_DISPATCH_CAP"
    assert outcomes[-1].runtime_reason == "DISPATCH_CAP_REACHED"
    assert summary.stopped_by_dispatch_cap == 1
    assert summary.stopped_by_candidate_cap == 0
    assert summary.stopped_by_runtime_seconds == 0
    assert summary.dispatch_attempted == 1
    # The cut-off candidate is NOT counted in candidates_seen.
    assert summary.candidates_seen == 1
    assert sink.attempted == 1


def test_max_candidates_stops_after_two_candidates() -> None:
    outcomes, summary, _sink = _run(
        _mixed_stream(), config=_config(max_candidates=2)
    )
    assert outcomes[-1].runtime_decision == "STOPPED_BY_CANDIDATE_CAP"
    assert outcomes[-1].runtime_reason == "CANDIDATE_CAP_REACHED"
    assert summary.stopped_by_candidate_cap == 1
    assert summary.candidates_seen == 2
    # Two were evaluated (dip dispatched, non-dip suppressed); the third stopped.
    assert summary.dispatch_attempted == 1
    assert summary.suppressed_by_gate == 1


def test_max_runtime_seconds_stops_via_injected_clock() -> None:
    # Clock reports 0 at start + 0 for cand1 + 0 for cand2, then 100 for cand3.
    clock = make_sequence_clock(
        (Decimal(0), Decimal(0), Decimal(0), Decimal(100))
    )
    outcomes, summary, _sink = _run(
        _mixed_stream(),
        config=_config(max_runtime_seconds=Decimal("60")),
        now_seconds=clock,
    )
    assert outcomes[-1].runtime_decision == "STOPPED_BY_RUNTIME_SECONDS"
    assert outcomes[-1].runtime_reason == "RUNTIME_SECONDS_REACHED"
    assert summary.stopped_by_runtime_seconds == 1
    assert summary.stopped_by_candidate_cap == 0
    assert summary.stopped_by_dispatch_cap == 0
    # Two candidates evaluated before the wall-clock bound elapsed.
    assert summary.candidates_seen == 2


def test_runtime_bound_uses_injected_clock_not_a_wall_clock() -> None:
    # The seam samples ONLY the injected clock; a counting clock proves it is
    # read (start sample + one per evaluated candidate) and that processing is
    # driven by it.
    clock = _CountingClock(Decimal(0))
    outcomes, summary, _sink = _run(
        _mixed_stream(), config=_config(), now_seconds=clock
    )
    # start sample (1) + one per evaluated candidate (5) = 6, no stop.
    assert clock.calls == summary.candidates_seen + 1
    assert summary.stopped_by_runtime_seconds == 0


def test_runtime_bound_can_stop_before_any_candidate() -> None:
    # If the clock is already past the bound at the first check, the first
    # candidate is the cut-off (nothing is evaluated, nothing dispatches).
    clock = make_sequence_clock((Decimal(0), Decimal(999)))
    outcomes, summary, _sink = _run(
        _mixed_stream(),
        config=_config(max_runtime_seconds=Decimal("60")),
        now_seconds=clock,
        sink=_RaisingSink(),
    )
    assert len(outcomes) == 1
    assert outcomes[0].runtime_decision == "STOPPED_BY_RUNTIME_SECONDS"
    assert summary.candidates_seen == 0
    assert summary.dispatch_attempted == 0


# ---------------------------------------------------------------------------
# 6. Invalid config fails closed (raises before any dispatch)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "config",
    [
        _config(max_runtime_seconds=Decimal("0")),
        _config(max_runtime_seconds=Decimal("-5")),
        _config(max_candidates=0),
        _config(max_dispatches=-1),
    ],
)
def test_invalid_config_raises_and_never_dispatches(config) -> None:
    sink = _RaisingSink()
    with pytest.raises(Stage30_11RuntimeGateError) as exc:
        run_stage30_11_runtime_gate_seam(
            _mixed_stream(),
            config=config,
            dispatch_sink=sink,
            now_seconds=make_constant_clock(Decimal(0)),
            created_at_utc=_CREATED_AT,
        )
    assert exc.value.reason == "INVALID_CONFIG_OR_INPUT"


def test_non_config_object_raises() -> None:
    with pytest.raises(Stage30_11RuntimeGateError):
        run_stage30_11_runtime_gate_seam(
            (_snapshot(tier_hint="Tier 1"),),
            config="not-a-config",
            dispatch_sink=_RaisingSink(),
            now_seconds=make_constant_clock(Decimal(0)),
            created_at_utc=_CREATED_AT,
        )


@pytest.mark.parametrize(
    "bad",
    [
        Decimal("NaN"),
        Decimal("sNaN"),
        Decimal("Infinity"),
        Decimal("-Infinity"),
    ],
)
def test_non_finite_runtime_config_raises_before_any_dispatch(bad) -> None:
    # A non-finite wall-clock bound is an invalid config: the seam fails closed
    # by raising BEFORE any bridge / gate / sink touch. A recording sink proves
    # it was never called (no decimal.InvalidOperation escapes from validation).
    sink = Stage30_11RecordingFakeDispatchSink(created_at_utc=_CREATED_AT)
    with pytest.raises(Stage30_11RuntimeGateError) as exc:
        run_stage30_11_runtime_gate_seam(
            _mixed_stream(),
            config=_config(max_runtime_seconds=bad),
            dispatch_sink=sink,
            now_seconds=make_constant_clock(Decimal(0)),
            created_at_utc=_CREATED_AT,
        )
    assert exc.value.reason == "INVALID_CONFIG_OR_INPUT"
    assert sink.attempted == 0
    assert sink.accepted == 0


# ---------------------------------------------------------------------------
# 7. Determinism
# ---------------------------------------------------------------------------


def test_seam_is_deterministic() -> None:
    outcomes_a, summary_a, _a = _run(_mixed_stream())
    outcomes_b, summary_b, _b = _run(_mixed_stream())
    assert outcomes_a == outcomes_b
    assert summary_a == summary_b

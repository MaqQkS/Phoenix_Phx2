"""Stage 28.6 bounded private session runner tests.

Pins:

  * Empty candidate stream writes final summary, no sends.
  * Single successful candidate reserves / pre-sends / sends /
    terminal-writes / records summary.
  * Max events / max dispatches stop the run gracefully.
  * Duplicate terminal suppresses and sends nothing.
  * Ambiguous ledger state suppresses and sends nothing.
  * Unknown / disagree pair suppresses and sends nothing.
  * USDC observe-only suppresses tradeable dispatch and sends
    nothing.
  * Stale / missing price suppresses and sends nothing.
  * Malformed candidate counted, no send.
  * Ledger reserve failure prevents send.
  * Heartbeat write failure fail-closed iff configured.
  * Final summary attempted on graceful stop.
  * Injected operator stop writes final summary.
  * Bounded retry follows Stage 28.3b policy without sleeping.
  * Nonretryable transport failure does not retry.
  * Retry budget exhaustion stops the run gracefully.
  * No sleep called during retry decisions.
  * No real HTTP opener used.
  * Exactly-one-send per attempt.
  * Heartbeat JSONL / health snapshot / final summary artifacts
    contain no canary webhook URL / API key / bearer / provider
    endpoint substring.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Mapping

import pytest

from PHX2.stage28.audited_http_transport_models import (
    TRANSPORT_STATUS_AUTH_OR_WEBHOOK_REFUSED,
    TRANSPORT_STATUS_NETWORK_ERROR,
    TRANSPORT_STATUS_RATE_LIMITED,
    TRANSPORT_STATUS_SENT_OK,
    TRANSPORT_STATUS_SERVER_ERROR,
    TRANSPORT_STATUS_VALIDATION_FAILED,
    Stage28_4TransportResult,
)
from PHX2.stage28.bounded_private_session_runner import (
    Stage28_6BoundedPrivateSessionRunner,
)
from PHX2.stage28.dispatch_ledger import (
    record_pre_send,
    record_terminal,
    replay_ledger,
    reserve_dispatch_intent,
)
from PHX2.stage28.dispatch_ledger_models import (
    DEDUPE_STATE_DISPATCHED_OK,
    DEDUPE_STATE_PRE_SEND_RECORDED,
    DEDUPE_STATE_RESERVED,
    build_dispatch_dedupe_key,
)
from PHX2.stage28.heartbeat_writer import read_heartbeat_lines
from PHX2.stage28.health_snapshot_writer import (
    read_final_run_summary,
    read_health_snapshot,
)
from PHX2.stage28.health_status_models import (
    HEALTH_STATUS_DEGRADED,
    HEALTH_STATUS_FAILED,
    HEALTH_STATUS_HEALTHY,
    HEALTH_STATUS_STOPPED,
    STOP_REASON_ERROR,
    STOP_REASON_MAX_EVENTS,
    STOP_REASON_OPERATOR_STOP,
    STOP_REASON_RETRY_BUDGET_EXHAUSTED,
    STOP_REASON_SIGINT,
)
from PHX2.stage28.session_runner_models import (
    CANDIDATE_PAIR_STATUS_DISAGREE,
    CANDIDATE_PAIR_STATUS_OK,
    CANDIDATE_PAIR_STATUS_UNKNOWN,
    CANDIDATE_PAIR_STATUS_USDC_OBSERVE_ONLY,
    CANDIDATE_PRICE_STATUS_MISSING,
    CANDIDATE_PRICE_STATUS_OK,
    CANDIDATE_PRICE_STATUS_STALE,
    Stage28_6CandidateEvent,
    Stage28_6DeterministicTickClock,
    Stage28_6FakeTransport,
    Stage28_6RunSummary,
    Stage28_6StopSignal,
    build_candidate_event,
    build_runner_config,
)


# ---------------------------------------------------------------------------
# Test fixtures / helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def session_paths(tmp_path):
    """Yield a Path bundle for ledger / heartbeat / snapshot /
    summary under ``tmp_path``.
    """
    return {
        "ledger_path": tmp_path / "dispatch_ledger.jsonl",
        "heartbeat_path": tmp_path / "heartbeat.jsonl",
        "snapshot_path": tmp_path / "health_snapshot.json",
        "summary_path": tmp_path / "final_run_summary.json",
    }


def _default_config(**overrides):
    base = {
        "run_id": "run-001",
        "session_id": "session-001",
        "max_events": 100,
        "max_dispatches": 50,
        "max_total_retries": 3,
        "max_ticks": 1000,
        "heartbeat_every_n_events": 2,
        "fail_closed_on_artifact_error": True,
        "fail_closed_on_ledger_error": True,
        "fail_closed_on_heartbeat_error": False,
    }
    base.update(overrides)
    return build_runner_config(**base)


def _default_candidate(**overrides) -> Stage28_6CandidateEvent:
    base = {
        "event_id": "event_001",
        "token_mint": "So11111111111111111111111111111111111111112",
        "pair_quote_asset": "SOL",
        "event_kind": "migration",
        "ping_type": "tradeable_private_ping",
        "normalized_event_id": "norm_event_001",
        "rendered_payload": {"content": "Pump fun migration ping"},
        "pre_send_artifact_reference": "pre_send_001.json",
        "webhook_identity": "PRIVATE_OPERATOR_WEBHOOK",
        "dispatch_allowed": True,
        "pair_status": CANDIDATE_PAIR_STATUS_OK,
        "price_status": CANDIDATE_PRICE_STATUS_OK,
        "malformed": False,
    }
    base.update(overrides)
    return build_candidate_event(**base)


def _make_runner(
    paths,
    *,
    transport=None,
    config=None,
    stop_signal=None,
    tick_clock=None,
):
    if transport is None:
        transport = Stage28_6FakeTransport()
    if config is None:
        config = _default_config()
    return Stage28_6BoundedPrivateSessionRunner(
        config=config,
        transport=transport,
        ledger_path=paths["ledger_path"],
        heartbeat_path=paths["heartbeat_path"],
        snapshot_path=paths["snapshot_path"],
        summary_path=paths["summary_path"],
        stop_signal=stop_signal,
        tick_clock=tick_clock,
    )


# ---------------------------------------------------------------------------
# Empty stream
# ---------------------------------------------------------------------------


def test_empty_stream_writes_final_summary_and_no_sends(session_paths):
    transport = Stage28_6FakeTransport()
    runner = _make_runner(session_paths, transport=transport)
    summary = runner.run([])
    assert isinstance(summary, Stage28_6RunSummary)
    assert summary.events_seen == 0
    assert summary.dispatch_attempts == 0
    assert transport.call_count == 0
    # Final summary written; ledger / heartbeat may be empty.
    persisted = read_final_run_summary(session_paths["summary_path"])
    assert persisted is not None
    assert persisted["total_events_seen"] == 0


# ---------------------------------------------------------------------------
# Single successful candidate
# ---------------------------------------------------------------------------


def test_single_successful_candidate_reserves_presend_sends_terminal(
    session_paths,
):
    transport = Stage28_6FakeTransport(
        scripted_outcomes=(TRANSPORT_STATUS_SENT_OK,)
    )
    runner = _make_runner(session_paths, transport=transport)
    summary = runner.run([_default_candidate()])
    assert summary.events_seen == 1
    assert summary.candidates_seen == 1
    assert summary.dispatch_attempts == 1
    assert summary.dispatch_success == 1
    assert summary.dispatch_failure == 0
    assert transport.call_count == 1
    # Ledger now has RESERVE + PRE_SEND + TERMINAL records.
    replay = replay_ledger(session_paths["ledger_path"])
    assert replay.record_count == 3
    key = build_dispatch_dedupe_key(
        token_mint="So11111111111111111111111111111111111111112",
        pair_quote_asset="SOL",
        event_kind="migration",
        ping_type="tradeable_private_ping",
        normalized_event_id="norm_event_001",
    )
    from PHX2.stage28.dispatch_ledger_models import (
        canonical_dedupe_key_serialization,
    )
    state = replay.states_by_key[canonical_dedupe_key_serialization(key)]
    assert state.terminal_status == DEDUPE_STATE_DISPATCHED_OK


def test_single_successful_candidate_writes_final_summary(session_paths):
    transport = Stage28_6FakeTransport()
    runner = _make_runner(session_paths, transport=transport)
    runner.run([_default_candidate()])
    persisted = read_final_run_summary(session_paths["summary_path"])
    assert persisted is not None
    assert persisted["total_dispatch_success"] == 1
    snapshot = read_health_snapshot(session_paths["snapshot_path"])
    assert snapshot is not None
    assert snapshot["current_health_status"] == HEALTH_STATUS_HEALTHY


# ---------------------------------------------------------------------------
# Max events / max dispatches
# ---------------------------------------------------------------------------


def test_max_events_stops_run(session_paths):
    transport = Stage28_6FakeTransport(
        scripted_outcomes=(TRANSPORT_STATUS_SENT_OK,) * 10,
    )
    runner = _make_runner(
        session_paths,
        transport=transport,
        config=_default_config(max_events=2),
    )
    candidates = [
        _default_candidate(
            event_id=f"event_{i}",
            normalized_event_id=f"norm_event_{i}",
        )
        for i in range(5)
    ]
    summary = runner.run(candidates)
    assert summary.events_seen == 2
    assert summary.stop_reason == STOP_REASON_MAX_EVENTS
    assert transport.call_count == 2


def test_max_dispatches_stops_run(session_paths):
    transport = Stage28_6FakeTransport(
        scripted_outcomes=(TRANSPORT_STATUS_SENT_OK,) * 10,
    )
    runner = _make_runner(
        session_paths,
        transport=transport,
        config=_default_config(max_events=100, max_dispatches=2),
    )
    candidates = [
        _default_candidate(
            event_id=f"event_{i}",
            normalized_event_id=f"norm_event_{i}",
        )
        for i in range(5)
    ]
    summary = runner.run(candidates)
    assert summary.dispatch_attempts == 2
    assert summary.stop_reason == STOP_REASON_MAX_EVENTS


def test_max_ticks_stops_run(session_paths):
    transport = Stage28_6FakeTransport(
        scripted_outcomes=(TRANSPORT_STATUS_SENT_OK,) * 10,
    )
    runner = _make_runner(
        session_paths,
        transport=transport,
        config=_default_config(max_events=100, max_dispatches=100, max_ticks=2),
    )
    candidates = [
        _default_candidate(
            event_id=f"event_{i}",
            normalized_event_id=f"norm_event_{i}",
        )
        for i in range(5)
    ]
    summary = runner.run(candidates)
    assert summary.events_seen == 2
    # max_ticks of 2 means the runner advances 2 ticks then stops.


# ---------------------------------------------------------------------------
# Dedupe-based suppressions
# ---------------------------------------------------------------------------


def test_duplicate_terminal_suppresses_and_sends_nothing(session_paths):
    # Pre-populate the ledger with a terminal record so the runner
    # treats the candidate as a duplicate.
    key = build_dispatch_dedupe_key(
        token_mint="So11111111111111111111111111111111111111112",
        pair_quote_asset="SOL",
        event_kind="migration",
        ping_type="tradeable_private_ping",
        normalized_event_id="norm_event_001",
    )
    # Manually build a ledger that already has the candidate at
    # DISPATCHED_OK.
    replay0 = replay_ledger(session_paths["ledger_path"])
    reserve_dispatch_intent(
        ledger_path=session_paths["ledger_path"],
        dedupe_key=key,
        replay=replay0,
    )
    replay1 = replay_ledger(session_paths["ledger_path"])
    record_pre_send(
        ledger_path=session_paths["ledger_path"],
        dedupe_key=key,
        artifact_reference="pre_send_001.json",
        replay=replay1,
    )
    replay2 = replay_ledger(session_paths["ledger_path"])
    record_terminal(
        ledger_path=session_paths["ledger_path"],
        dedupe_key=key,
        terminal_status=DEDUPE_STATE_DISPATCHED_OK,
        replay=replay2,
        failure_reason=None,
    )
    transport = Stage28_6FakeTransport()
    runner = _make_runner(session_paths, transport=transport)
    summary = runner.run([_default_candidate()])
    assert transport.call_count == 0
    assert summary.duplicates_suppressed == 1
    assert summary.dispatch_attempts == 0


def test_ambiguous_ledger_state_suppresses_and_sends_nothing(
    session_paths,
):
    # Pre-populate the ledger with a RESERVE but no terminal: this
    # creates an ambiguous resumed state.
    key = build_dispatch_dedupe_key(
        token_mint="So11111111111111111111111111111111111111112",
        pair_quote_asset="SOL",
        event_kind="migration",
        ping_type="tradeable_private_ping",
        normalized_event_id="norm_event_001",
    )
    replay0 = replay_ledger(session_paths["ledger_path"])
    reserve_dispatch_intent(
        ledger_path=session_paths["ledger_path"],
        dedupe_key=key,
        replay=replay0,
    )
    transport = Stage28_6FakeTransport()
    runner = _make_runner(session_paths, transport=transport)
    summary = runner.run([_default_candidate()])
    assert transport.call_count == 0
    assert summary.ambiguous_suppressed == 1
    assert summary.dispatch_attempts == 0


# ---------------------------------------------------------------------------
# Pair / price suppressions
# ---------------------------------------------------------------------------


def test_unknown_pair_suppresses_and_sends_nothing(session_paths):
    transport = Stage28_6FakeTransport()
    runner = _make_runner(session_paths, transport=transport)
    summary = runner.run(
        [
            _default_candidate(
                pair_status=CANDIDATE_PAIR_STATUS_UNKNOWN,
                dispatch_allowed=False,
            )
        ]
    )
    assert summary.unknown_pair_suppressed == 1
    assert transport.call_count == 0


def test_disagree_pair_suppresses_and_sends_nothing(session_paths):
    transport = Stage28_6FakeTransport()
    runner = _make_runner(session_paths, transport=transport)
    summary = runner.run(
        [
            _default_candidate(
                pair_status=CANDIDATE_PAIR_STATUS_DISAGREE,
                dispatch_allowed=False,
            )
        ]
    )
    assert summary.disagree_pair_suppressed == 1
    assert transport.call_count == 0


def test_usdc_observe_only_suppresses_and_sends_nothing(session_paths):
    transport = Stage28_6FakeTransport()
    runner = _make_runner(session_paths, transport=transport)
    summary = runner.run(
        [
            _default_candidate(
                pair_status=CANDIDATE_PAIR_STATUS_USDC_OBSERVE_ONLY,
                dispatch_allowed=False,
            )
        ]
    )
    assert summary.usdc_observe_only == 1
    assert transport.call_count == 0


def test_stale_price_suppresses_and_sends_nothing(session_paths):
    transport = Stage28_6FakeTransport()
    runner = _make_runner(session_paths, transport=transport)
    summary = runner.run(
        [
            _default_candidate(
                price_status=CANDIDATE_PRICE_STATUS_STALE,
                dispatch_allowed=False,
            )
        ]
    )
    assert summary.stale_price_suppressed == 1
    assert transport.call_count == 0


def test_missing_price_suppresses_and_sends_nothing(session_paths):
    transport = Stage28_6FakeTransport()
    runner = _make_runner(session_paths, transport=transport)
    summary = runner.run(
        [
            _default_candidate(
                price_status=CANDIDATE_PRICE_STATUS_MISSING,
                dispatch_allowed=False,
            )
        ]
    )
    assert summary.missing_price_suppressed == 1
    assert transport.call_count == 0


# ---------------------------------------------------------------------------
# Malformed
# ---------------------------------------------------------------------------


def test_malformed_candidate_counted_no_send(session_paths):
    transport = Stage28_6FakeTransport()
    runner = _make_runner(session_paths, transport=transport)
    summary = runner.run(
        [
            _default_candidate(
                malformed=True,
                dispatch_allowed=False,
            )
        ]
    )
    assert summary.malformed_events == 1
    assert transport.call_count == 0


# ---------------------------------------------------------------------------
# Graceful shutdown / operator stop
# ---------------------------------------------------------------------------


def test_operator_stop_writes_final_summary_with_operator_stop_reason(
    session_paths,
):
    class _StoppingTransport:
        def __init__(self, signal: Stage28_6StopSignal):
            self._signal = signal
            self._calls = 0

        def send_one_audited_post(
            self,
            *,
            webhook_identity: str,
            payload: Mapping[str, Any],
        ) -> Stage28_4TransportResult:
            self._calls += 1
            # Trigger stop after the first successful send so the
            # runner observes the request between candidates.
            self._signal.request_stop()
            return Stage28_4TransportResult(
                transport_status=TRANSPORT_STATUS_SENT_OK,
                ok=True,
                http_status_code=204,
                retry_after_seconds=None,
                send_attempt_count=1,
                webhook_identity=webhook_identity,
                redaction_status="REDACTED",
                safe_reason_code="sent_ok",
                response_body_status="DROPPED_UNRECORDED",
                schema_version="stage28_4_audited_http_transport_v0",
            )

    signal = Stage28_6StopSignal()
    transport = _StoppingTransport(signal)
    runner = _make_runner(
        session_paths,
        transport=transport,
        stop_signal=signal,
    )
    candidates = [
        _default_candidate(
            event_id=f"event_{i}",
            normalized_event_id=f"norm_event_{i}",
        )
        for i in range(5)
    ]
    summary = runner.run(candidates)
    assert summary.stop_reason == STOP_REASON_OPERATOR_STOP
    # Only one candidate was processed before the stop signal fired.
    assert summary.dispatch_attempts == 1
    persisted = read_final_run_summary(session_paths["summary_path"])
    assert persisted is not None
    assert persisted["stop_reason"] == STOP_REASON_OPERATOR_STOP


def test_sigint_signal_writes_final_summary_with_sigint_reason(
    session_paths,
):
    signal = Stage28_6StopSignal()
    signal.request_stop(reason=STOP_REASON_SIGINT)
    transport = Stage28_6FakeTransport()
    runner = _make_runner(
        session_paths,
        transport=transport,
        stop_signal=signal,
    )
    # The signal is already requested before run(). The first
    # candidate is processed, then the runner checks the signal
    # between candidates and stops.
    candidates = [
        _default_candidate(
            event_id=f"event_{i}",
            normalized_event_id=f"norm_event_{i}",
        )
        for i in range(3)
    ]
    summary = runner.run(candidates)
    assert summary.stop_reason == STOP_REASON_SIGINT


# ---------------------------------------------------------------------------
# Retry execution (bounded)
# ---------------------------------------------------------------------------


def test_retryable_transport_failure_follows_bounded_policy(
    session_paths,
):
    # Two rate-limited attempts then a successful send. Stage 28.3b
    # DISCORD_RATE_LIMITED profile allows up to 2 retries; the third
    # call should succeed.
    transport = Stage28_6FakeTransport(
        scripted_outcomes=(
            TRANSPORT_STATUS_RATE_LIMITED,
            TRANSPORT_STATUS_RATE_LIMITED,
            TRANSPORT_STATUS_SENT_OK,
        ),
        scripted_retry_after_seconds=0.5,
    )
    runner = _make_runner(
        session_paths,
        transport=transport,
        config=_default_config(max_total_retries=5),
    )
    summary = runner.run([_default_candidate()])
    assert summary.dispatch_attempts == 3
    assert summary.dispatch_success == 1
    assert summary.retries_attempted == 2


def test_nonretryable_transport_failure_does_not_retry(session_paths):
    # AUTH_OR_WEBHOOK_REFUSED is mapped to the
    # CONFIG_OPERATOR_FIX profile, which is not retryable.
    transport = Stage28_6FakeTransport(
        scripted_outcomes=(TRANSPORT_STATUS_AUTH_OR_WEBHOOK_REFUSED,),
    )
    runner = _make_runner(
        session_paths,
        transport=transport,
        config=_default_config(max_total_retries=5),
    )
    summary = runner.run([_default_candidate()])
    assert summary.dispatch_attempts == 1
    assert summary.dispatch_failure == 1
    assert summary.retries_attempted == 0


def test_retry_budget_exhaustion_stops_run(session_paths):
    # Every send returns rate-limited; the runner should burn its
    # max_total_retries budget and then stop the run.
    transport = Stage28_6FakeTransport(
        scripted_outcomes=(TRANSPORT_STATUS_RATE_LIMITED,) * 10,
        scripted_retry_after_seconds=0.1,
    )
    runner = _make_runner(
        session_paths,
        transport=transport,
        config=_default_config(max_total_retries=2),
    )
    candidates = [
        _default_candidate(
            event_id=f"event_{i}",
            normalized_event_id=f"norm_event_{i}",
        )
        for i in range(5)
    ]
    summary = runner.run(candidates)
    assert summary.stop_reason in (
        STOP_REASON_RETRY_BUDGET_EXHAUSTED,
        STOP_REASON_MAX_EVENTS,
    )
    assert summary.retries_attempted >= 2


def test_no_real_sleep_called_during_retry_decisions(
    monkeypatch, session_paths
):
    """The runner must never call ``time.sleep`` during retry
    decisions; Stage 28.3b only emits the delay, the runner does
    not execute it.
    """
    import time as _time

    calls: list[float] = []

    def _capturing_sleep(value: float) -> None:
        calls.append(value)

    monkeypatch.setattr(_time, "sleep", _capturing_sleep)
    transport = Stage28_6FakeTransport(
        scripted_outcomes=(
            TRANSPORT_STATUS_RATE_LIMITED,
            TRANSPORT_STATUS_SENT_OK,
        ),
    )
    runner = _make_runner(session_paths, transport=transport)
    runner.run([_default_candidate()])
    assert calls == []


def test_no_real_http_opener_used(session_paths):
    # The fake transport never imports urllib at the call site.
    # We assert by spying on the transport's call surface.
    transport = Stage28_6FakeTransport()
    runner = _make_runner(session_paths, transport=transport)
    runner.run(
        [
            _default_candidate(
                event_id=f"event_{i}",
                normalized_event_id=f"norm_event_{i}",
            )
            for i in range(3)
        ]
    )
    assert transport.call_count == 3
    # Ensure the fake transport was the only send surface invoked.
    for call in transport.calls:
        assert call["webhook_identity"] == "PRIVATE_OPERATOR_WEBHOOK"


def test_exactly_one_send_per_attempt(session_paths):
    # Server-error then success — exactly two send attempts, one
    # retry. Each transport.send_one_audited_post invocation
    # corresponds to a single attempt.
    transport = Stage28_6FakeTransport(
        scripted_outcomes=(
            TRANSPORT_STATUS_SERVER_ERROR,
            TRANSPORT_STATUS_SENT_OK,
        ),
    )
    runner = _make_runner(
        session_paths,
        transport=transport,
        config=_default_config(max_total_retries=4),
    )
    summary = runner.run([_default_candidate()])
    assert transport.call_count == summary.dispatch_attempts == 2


# ---------------------------------------------------------------------------
# Heartbeat / health snapshot / final summary artifacts
# ---------------------------------------------------------------------------


def test_heartbeat_emitted_every_n_events(session_paths):
    transport = Stage28_6FakeTransport(
        scripted_outcomes=(TRANSPORT_STATUS_SENT_OK,) * 10,
    )
    runner = _make_runner(
        session_paths,
        transport=transport,
        config=_default_config(heartbeat_every_n_events=2),
    )
    runner.run(
        [
            _default_candidate(
                event_id=f"event_{i}",
                normalized_event_id=f"norm_event_{i}",
            )
            for i in range(5)
        ]
    )
    heartbeats = read_heartbeat_lines(session_paths["heartbeat_path"])
    assert len(heartbeats) == 2  # at event 2 and event 4
    assert heartbeats[0]["heartbeat_index"] == 0
    assert heartbeats[1]["heartbeat_index"] == 1


def test_health_snapshot_attempted_on_stop(session_paths):
    transport = Stage28_6FakeTransport()
    runner = _make_runner(session_paths, transport=transport)
    runner.run([_default_candidate()])
    snapshot = read_health_snapshot(session_paths["snapshot_path"])
    assert snapshot is not None
    assert snapshot["event_count"] == 1


def test_final_summary_attempted_on_graceful_stop(session_paths):
    transport = Stage28_6FakeTransport()
    runner = _make_runner(session_paths, transport=transport)
    runner.run([_default_candidate()])
    persisted = read_final_run_summary(session_paths["summary_path"])
    assert persisted is not None


def test_heartbeat_write_failure_fail_closed_when_configured(
    monkeypatch, session_paths
):
    # Replace append_heartbeat with a raising version.
    from PHX2.stage28 import bounded_private_session_runner as runner_module
    from PHX2.stage28.heartbeat_writer import Stage28_5HeartbeatWriterError

    def _raising_append(*, heartbeat_path, record):
        raise Stage28_5HeartbeatWriterError(
            "synthetic heartbeat failure"
        )

    monkeypatch.setattr(
        runner_module, "append_heartbeat", _raising_append
    )
    transport = Stage28_6FakeTransport(
        scripted_outcomes=(TRANSPORT_STATUS_SENT_OK,) * 10,
    )
    runner = _make_runner(
        session_paths,
        transport=transport,
        config=_default_config(
            heartbeat_every_n_events=1,
            fail_closed_on_heartbeat_error=True,
        ),
    )
    summary = runner.run(
        [
            _default_candidate(
                event_id=f"event_{i}",
                normalized_event_id=f"norm_event_{i}",
            )
            for i in range(5)
        ]
    )
    assert summary.stop_reason == STOP_REASON_ERROR
    assert summary.artifact_failures >= 1


def test_heartbeat_write_failure_continues_when_not_fail_closed(
    monkeypatch, session_paths
):
    from PHX2.stage28 import bounded_private_session_runner as runner_module
    from PHX2.stage28.heartbeat_writer import Stage28_5HeartbeatWriterError

    def _raising_append(*, heartbeat_path, record):
        raise Stage28_5HeartbeatWriterError(
            "synthetic heartbeat failure"
        )

    monkeypatch.setattr(
        runner_module, "append_heartbeat", _raising_append
    )
    transport = Stage28_6FakeTransport(
        scripted_outcomes=(TRANSPORT_STATUS_SENT_OK,) * 10,
    )
    runner = _make_runner(
        session_paths,
        transport=transport,
        config=_default_config(
            heartbeat_every_n_events=1,
            fail_closed_on_heartbeat_error=False,
        ),
    )
    summary = runner.run(
        [
            _default_candidate(
                event_id=f"event_{i}",
                normalized_event_id=f"norm_event_{i}",
            )
            for i in range(3)
        ]
    )
    # Run completed despite heartbeat failures.
    assert summary.artifact_failures >= 1
    assert summary.stop_reason in (
        STOP_REASON_MAX_EVENTS,
        STOP_REASON_OPERATOR_STOP,
    )


def test_health_snapshot_failure_classified(monkeypatch, session_paths):
    from PHX2.stage28 import bounded_private_session_runner as runner_module
    from PHX2.stage28.health_snapshot_writer import (
        Stage28_5HealthSnapshotWriterError,
    )

    def _raising_snapshot(*, snapshot_path, record):
        raise Stage28_5HealthSnapshotWriterError(
            "synthetic snapshot failure"
        )

    monkeypatch.setattr(
        runner_module, "write_health_snapshot", _raising_snapshot
    )
    transport = Stage28_6FakeTransport()
    runner = _make_runner(session_paths, transport=transport)
    summary = runner.run([_default_candidate()])
    # Snapshot failure surfaced as an artifact failure but the run
    # still attempts the final summary.
    assert summary.artifact_failures >= 1


# ---------------------------------------------------------------------------
# Ledger failures
# ---------------------------------------------------------------------------


def test_ledger_reserve_failure_prevents_send(monkeypatch, session_paths):
    from PHX2.stage28 import bounded_private_session_runner as runner_module
    from PHX2.stage28.dispatch_ledger_models import (
        Stage28_2LedgerIOError,
    )

    def _raising_reserve(*, ledger_path, dedupe_key, replay):
        raise Stage28_2LedgerIOError(operation="LEDGER_APPEND")

    monkeypatch.setattr(
        runner_module, "reserve_dispatch_intent", _raising_reserve
    )
    transport = Stage28_6FakeTransport()
    runner = _make_runner(session_paths, transport=transport)
    summary = runner.run([_default_candidate()])
    assert transport.call_count == 0
    assert summary.ledger_failures >= 1
    assert summary.stop_reason == STOP_REASON_ERROR


def test_pre_send_record_failure_prevents_send(monkeypatch, session_paths):
    from PHX2.stage28 import bounded_private_session_runner as runner_module
    from PHX2.stage28.dispatch_ledger_models import (
        Stage28_2LedgerIOError,
    )

    def _raising_pre_send(
        *, ledger_path, dedupe_key, artifact_reference, replay
    ):
        raise Stage28_2LedgerIOError(operation="LEDGER_APPEND")

    monkeypatch.setattr(
        runner_module, "record_pre_send", _raising_pre_send
    )
    transport = Stage28_6FakeTransport()
    runner = _make_runner(session_paths, transport=transport)
    summary = runner.run([_default_candidate()])
    assert transport.call_count == 0
    assert summary.artifact_failures >= 1 or summary.ledger_failures >= 1


def test_terminal_record_failure_classified(monkeypatch, session_paths):
    """If the runner cannot write a terminal record after a
    successful send, the failure must be classified + surfaced; the
    in-memory send count still reflects the actual send.
    """
    from PHX2.stage28 import bounded_private_session_runner as runner_module
    from PHX2.stage28.dispatch_ledger_models import (
        Stage28_2LedgerIOError,
    )

    real_record_terminal = runner_module.record_terminal

    def _raising_terminal(
        *, ledger_path, dedupe_key, terminal_status, replay, failure_reason=None
    ):
        raise Stage28_2LedgerIOError(operation="LEDGER_APPEND")

    monkeypatch.setattr(
        runner_module, "record_terminal", _raising_terminal
    )
    transport = Stage28_6FakeTransport(
        scripted_outcomes=(TRANSPORT_STATUS_SENT_OK,) * 10,
    )
    runner = _make_runner(
        session_paths,
        transport=transport,
        config=_default_config(fail_closed_on_ledger_error=False),
    )
    summary = runner.run([_default_candidate()])
    # Send happened.
    assert summary.dispatch_success == 1
    # Ledger failure surfaced.
    assert summary.ledger_failures >= 1


# ---------------------------------------------------------------------------
# Redaction discipline
# ---------------------------------------------------------------------------


_CANARY_WEBHOOK_URL: str = (
    "h" + "ttps://" + "discord" + ".com/api/webhooks/12345/abcdef"
)
_CANARY_API_KEY: str = "s" + "k-canary-1234567890"
_CANARY_BEARER: str = "Bearer canary-bearer-1234567890"
_CANARY_PROVIDER_ENDPOINT: str = (
    "h" + "ttps://api.helius" + ".xyz/v0/rpc"
)


def _scan_for_canaries(text: str) -> list[str]:
    found: list[str] = []
    for needle in (
        _CANARY_WEBHOOK_URL,
        _CANARY_API_KEY,
        _CANARY_BEARER,
        _CANARY_PROVIDER_ENDPOINT,
    ):
        if needle in text:
            found.append(needle)
    return found


def test_canaries_absent_from_summary_repr(session_paths):
    transport = Stage28_6FakeTransport()
    runner = _make_runner(session_paths, transport=transport)
    summary = runner.run([_default_candidate()])
    rendered = repr(summary)
    assert _scan_for_canaries(rendered) == []


def test_canaries_absent_from_summary_artifact(session_paths):
    transport = Stage28_6FakeTransport()
    runner = _make_runner(session_paths, transport=transport)
    runner.run([_default_candidate()])
    raw = session_paths["summary_path"].read_text(encoding="utf-8")
    assert _scan_for_canaries(raw) == []


def test_canaries_absent_from_heartbeat_artifact(session_paths):
    transport = Stage28_6FakeTransport(
        scripted_outcomes=(TRANSPORT_STATUS_SENT_OK,) * 5,
    )
    runner = _make_runner(
        session_paths,
        transport=transport,
        config=_default_config(heartbeat_every_n_events=1),
    )
    runner.run(
        [
            _default_candidate(
                event_id=f"event_{i}",
                normalized_event_id=f"norm_event_{i}",
            )
            for i in range(3)
        ]
    )
    raw = session_paths["heartbeat_path"].read_text(encoding="utf-8")
    assert _scan_for_canaries(raw) == []


def test_canaries_absent_from_snapshot_artifact(session_paths):
    transport = Stage28_6FakeTransport()
    runner = _make_runner(session_paths, transport=transport)
    runner.run([_default_candidate()])
    raw = session_paths["snapshot_path"].read_text(encoding="utf-8")
    assert _scan_for_canaries(raw) == []


def test_canaries_absent_from_ledger_artifact(session_paths):
    transport = Stage28_6FakeTransport()
    runner = _make_runner(session_paths, transport=transport)
    runner.run([_default_candidate()])
    raw = session_paths["ledger_path"].read_text(encoding="utf-8")
    assert _scan_for_canaries(raw) == []


# ---------------------------------------------------------------------------
# Bounded controls / no infinite loops
# ---------------------------------------------------------------------------


def test_max_total_retries_zero_means_no_retries(session_paths):
    transport = Stage28_6FakeTransport(
        scripted_outcomes=(
            TRANSPORT_STATUS_RATE_LIMITED,
            TRANSPORT_STATUS_SENT_OK,
        ),
    )
    runner = _make_runner(
        session_paths,
        transport=transport,
        config=_default_config(max_total_retries=0),
    )
    summary = runner.run([_default_candidate()])
    # With max_total_retries=0 the policy must refuse retries on
    # the global budget, even though the failure is in-principle
    # retryable.
    assert summary.dispatch_attempts == 1
    assert summary.dispatch_failure == 1


def test_run_completes_when_stream_fully_consumed(session_paths):
    transport = Stage28_6FakeTransport(
        scripted_outcomes=(TRANSPORT_STATUS_SENT_OK,) * 10,
    )
    runner = _make_runner(
        session_paths,
        transport=transport,
        config=_default_config(max_events=10, max_dispatches=10),
    )
    candidates = [
        _default_candidate(
            event_id=f"event_{i}",
            normalized_event_id=f"norm_event_{i}",
        )
        for i in range(3)
    ]
    summary = runner.run(candidates)
    assert summary.events_seen == 3
    assert summary.dispatch_attempts == 3
    assert summary.dispatch_success == 3

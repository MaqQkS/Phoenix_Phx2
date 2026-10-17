"""Persistent bounded-backoff reconnect: policy invariants + live-loop proofs.

The defect this closes: the Helius source stopped permanently after five
consecutive transport failures (``STREAM_FAILED`` / ``RECONNECTS_EXHAUSTED``),
so an outage longer than five attempts ended continuous discovery for the rest
of the run with nothing but a stopped stream to show for it.

Every simulation named by the discovery policy is here: 1 transient failure,
5 transient failures, 20 transient failures followed by success, authentication
rejection, operator shutdown during backoff, reconnect success and backoff
reset, duplicate-notification replay after reconnect, and exact-gap recovery
after reconnect.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, List

import pytest

from PHX2.free_tier_producer import helius_source as source
from PHX2.free_tier_producer import reconnect_policy as rp
from PHX2.free_tier_producer import source_continuity as continuity
from PHX2.tests.test_helius_shadow_source import (
    _Connection,
    _ConnectSequence,
    _FakeWebSocket,
    _notification,
)


def _config(**overrides):
    """Source config with an explicitly chosen ladder (no hidden default)."""

    values = {
        "HELIUS_API_KEY": "unit-test-secret",
        "HELIUS_RPC_URL": "https://mainnet.helius-rpc.com/",
        "HELIUS_WS_URL": "wss://mainnet.helius-rpc.com/",
    }
    return source.load_helius_source_config(environ=values, **overrides)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


class _AuthError(Exception):
    """A provider rejection carrying the HTTP status the source classifies."""

    def __init__(self, status_code: int) -> None:
        super().__init__("rejected")
        self.status_code = status_code


class _BoundedConnectSequence(_ConnectSequence):
    """``_ConnectSequence`` that cannot livelock a test.

    Persistent reconnect means a raising connect factory is retried FOREVER --
    correct in production, fatal for a test whose scripted sequence ran out.
    Exhaustion therefore raises ``CancelledError``, a ``BaseException`` the
    source's ``except Exception`` reconnect handler deliberately does not
    catch, so the loop terminates instead of spinning.
    """

    def __call__(self, url, **kwargs):
        if not self.connections:
            raise asyncio.CancelledError("connect sequence exhausted")
        return super().__call__(url, **kwargs)


def _policy(**overrides) -> rp.PersistentReconnectPolicy:
    values: dict = {"rand_fn": lambda: 0.0}
    values.update(overrides)
    return rp.PersistentReconnectPolicy(**values)


def _source(*, tracker=None, gap_recoverer=None, connect_fn=None,
            sleeps: List[float] | None = None, **config_overrides):
    async def _sleep(seconds: float) -> None:
        if sleeps is not None:
            sleeps.append(float(seconds))
        await asyncio.sleep(0)

    return source.HeliusEnhancedWssSource(
        config=_config(**config_overrides),
        continuity=tracker,
        gap_recoverer=gap_recoverer,
        connect_fn=connect_fn,
        now_fn=lambda: "2026-07-31T00:00:00Z",
        sleep_fn=_sleep,
        rand_fn=lambda: 0.0,
    )


def _ok_socket(*, request_id: int, subscription_id: int, slot: int,
               signature_byte: int, trailing=()) -> _FakeWebSocket:
    return _FakeWebSocket((
        {"jsonrpc": "2.0", "id": request_id, "result": subscription_id},
        _notification(subscription_id=subscription_id, slot=slot,
                      signature_byte=signature_byte),
        *trailing,
    ))


# ---------------------------------------------------------------------------
# policy: ladder, jitter, cap
# ---------------------------------------------------------------------------


def test_ladder_is_the_required_shape_and_caps_near_sixty_seconds() -> None:
    assert rp.RECONNECT_LADDER_SECONDS == (1.0, 2.0, 5.0, 10.0, 30.0, 60.0)
    assert rp.RECONNECT_MAX_DELAY_SECONDS == 60.0
    policy = _policy()
    observed = [policy.base_delay_for(index) for index in range(10)]
    assert observed[:6] == [1.0, 2.0, 5.0, 10.0, 30.0, 60.0]
    # Beyond the ladder every delay stays pinned at the cap.
    assert observed[6:] == [60.0, 60.0, 60.0, 60.0]
    assert max(observed) <= rp.RECONNECT_MAX_DELAY_SECONDS


def test_there_is_no_attempt_ceiling() -> None:
    policy = _policy()
    for _ in range(500):
        decision = policy.decide(failure_class=rp.FAILURE_TRANSIENT)
        assert decision.action == rp.ACTION_RECONNECT
    assert policy.consecutive_failures == 500
    assert policy.snapshot()["attempt_ceiling"] is None


def test_jitter_is_additive_and_bounded() -> None:
    draws = iter([0.0, 0.5, 1.0, 0.25])
    policy = _policy(rand_fn=lambda: next(draws))
    seen = []
    for _ in range(4):
        decision = policy.decide(failure_class=rp.FAILURE_TRANSIENT)
        seen.append(decision)
    for decision in seen:
        assert decision.jitter_seconds >= 0.0
        assert decision.jitter_seconds <= (
            decision.base_delay_seconds * rp.RECONNECT_JITTER_FRACTION)
        assert decision.delay_seconds == pytest.approx(
            decision.base_delay_seconds + decision.jitter_seconds)
        assert decision.delay_seconds <= rp.RECONNECT_MAX_DELAY_SECONDS * (
            1.0 + rp.RECONNECT_JITTER_FRACTION)
    # Same base, different jitter: the storm-avoidance property.
    assert seen[0].jitter_seconds != seen[1].jitter_seconds


def test_authentication_is_classified_separately_and_never_retried() -> None:
    policy = _policy()
    decision = policy.decide(failure_class=rp.FAILURE_AUTHENTICATION)
    assert decision.action == rp.ACTION_STOP_AUTHENTICATION
    assert decision.failure_class == rp.FAILURE_AUTHENTICATION
    assert decision.delay_seconds == 0.0
    assert decision.should_reconnect is False
    # It did not consume a backoff step: it is not an outage.
    assert policy.consecutive_failures == 0


def test_only_auth_and_integrity_may_reach_the_circuit_breaker() -> None:
    policy = _policy()
    transient = policy.decide(failure_class=rp.FAILURE_TRANSIENT)
    assert transient.circuit_eligible is False
    assert policy.decide(
        failure_class=rp.FAILURE_AUTHENTICATION).circuit_eligible is True
    assert policy.decide(
        failure_class=rp.FAILURE_INTEGRITY).circuit_eligible is True
    assert policy.decide(shutdown_requested=True).circuit_eligible is False


def test_unknown_error_tokens_default_to_transient_not_to_giving_up() -> None:
    assert rp.classify_reconnect_failure(
        "TRANSPORT_ERROR") == rp.FAILURE_TRANSIENT
    assert rp.classify_reconnect_failure(
        "SOMETHING_NEW") == rp.FAILURE_TRANSIENT
    assert rp.classify_reconnect_failure(
        "AUTH_FAILURE") == rp.FAILURE_AUTHENTICATION
    assert rp.classify_reconnect_failure(
        "BAD_CONFIG", integrity_tokens=("BAD_CONFIG",)) == rp.FAILURE_INTEGRITY


def test_sustained_connection_resets_backoff_and_flapping_does_not() -> None:
    policy = _policy()
    for _ in range(4):
        policy.decide(failure_class=rp.FAILURE_TRANSIENT)
    assert policy.consecutive_failures == 4

    # Flap: connected for 5s, well under the healthy threshold.
    policy.note_connection_established(at_epoch=1_000.0)
    assert policy.note_connection_closed(at_epoch=1_005.0) is False
    assert policy.consecutive_failures == 4
    assert policy.decide(
        failure_class=rp.FAILURE_TRANSIENT).base_delay_seconds == 30.0

    # Sustained: connected for longer than the healthy threshold.
    policy.note_connection_established(at_epoch=2_000.0)
    assert policy.note_connection_closed(
        at_epoch=2_000.0 + rp.HEALTHY_CONNECTION_SECONDS) is True
    assert policy.consecutive_failures == 0
    assert policy.decide(
        failure_class=rp.FAILURE_TRANSIENT).base_delay_seconds == 1.0
    assert policy.backoff_resets_total == 1
    assert policy.sustained_connections_total == 1


def test_policy_snapshot_is_numbers_and_closed_set_tokens_only() -> None:
    policy = _policy()
    policy.decide(failure_class=rp.FAILURE_TRANSIENT)
    snapshot = policy.snapshot()
    assert snapshot["persistent"] is True
    assert snapshot["last_failure_class"] in rp.RECONNECT_FAILURE_CLASSES
    assert snapshot["last_action"] in rp.RECONNECT_ACTIONS
    # Serializable and free of any provider text.
    body = json.dumps(snapshot, sort_keys=True)
    for needle in ("helius", "birdeye", "chainstack", "://"):
        assert needle not in body.lower()


def test_configuration_errors_fail_closed() -> None:
    with pytest.raises(rp.ReconnectPolicyConfigurationError):
        rp.PersistentReconnectPolicy(ladder=())
    with pytest.raises(rp.ReconnectPolicyConfigurationError):
        rp.PersistentReconnectPolicy(ladder=(5.0, 1.0))
    with pytest.raises(rp.ReconnectPolicyConfigurationError):
        rp.PersistentReconnectPolicy(jitter_fraction=1.5)
    with pytest.raises(rp.ReconnectPolicyConfigurationError):
        rp.PersistentReconnectPolicy(max_delay_seconds=10_000.0)


# ---------------------------------------------------------------------------
# the named simulations, driven through the real source loop
# ---------------------------------------------------------------------------


def _run_failures(count: int, *, tracker=None):
    """``count`` transient failures, then a socket that delivers one event."""

    sleeps: List[float] = []
    failures = [_Connection(error=OSError("transport")) for _ in range(count)]
    # Request ids advance only on a SUCCESSFUL connection, so the one socket
    # that opens sees id 1 (subscribe) and id 2 (unsubscribe) regardless of how
    # many attempts failed before it.
    good = _Connection(_ok_socket(
        request_id=1, subscription_id=90, slot=500, signature_byte=21,
        trailing=({"jsonrpc": "2.0", "id": 2, "result": True},)))
    adapter = _source(
        tracker=tracker,
        connect_fn=_BoundedConnectSequence(*failures, good),
        sleeps=sleeps,
        reconnect_backoff_seconds=(1.0, 2.0, 5.0, 10.0, 30.0, 60.0),
    )
    events = list(adapter.iter_events(max_events=1))
    return adapter, events, sleeps


def test_one_transient_failure_then_success() -> None:
    adapter, events, sleeps = _run_failures(1)
    assert len(events) == 1
    assert adapter.metrics.reconnects == 1
    assert sleeps == [1.0]
    assert adapter.status != source.STREAM_FAILED
    assert adapter.metrics.last_error != source.ERROR_RECONNECTS_EXHAUSTED


def test_five_transient_failures_do_not_exhaust_the_source() -> None:
    """The exact count that used to be terminal."""

    adapter, events, sleeps = _run_failures(5)
    assert len(events) == 1
    assert adapter.metrics.reconnects == 5
    assert sleeps == [1.0, 2.0, 5.0, 10.0, 30.0]
    assert adapter.status != source.STREAM_FAILED
    assert adapter.last_refusal_reason != source.ERROR_RECONNECTS_EXHAUSTED


def test_twenty_transient_failures_then_success() -> None:
    adapter, events, sleeps = _run_failures(20)
    assert len(events) == 1
    assert adapter.metrics.reconnects == 20
    assert len(sleeps) == 20
    # Ladder, then capped near 60s for every later attempt.
    assert sleeps[:6] == [1.0, 2.0, 5.0, 10.0, 30.0, 60.0]
    assert set(sleeps[6:]) == {60.0}
    assert max(sleeps) <= source.DEFAULT_RECONNECT_MAX_DELAY_SECONDS
    assert adapter.status != source.STREAM_FAILED


def test_authentication_rejection_stops_immediately_and_is_labelled() -> None:
    sleeps: List[float] = []
    adapter = _source(
        connect_fn=_BoundedConnectSequence(_Connection(error=_AuthError(401))),
        sleeps=sleeps,
        reconnect_backoff_seconds=(1.0, 2.0, 5.0),
    )
    assert list(adapter.iter_events(max_events=1)) == []
    assert adapter.status == source.STREAM_AUTH_FAILED
    assert adapter.last_refusal_reason == source.ERROR_AUTH
    assert adapter.metrics.reconnects == 0
    assert sleeps == []            # never backed off; auth is not an outage
    decision = adapter.last_reconnect_decision
    assert decision.action == rp.ACTION_STOP_AUTHENTICATION
    assert decision.failure_class == rp.FAILURE_AUTHENTICATION


def test_operator_shutdown_during_backoff_exits_promptly() -> None:
    """A stop that lands mid-backoff must not wait out the remaining delay."""

    entered = asyncio.Event()

    class _BlockingConnect:
        def __init__(self, adapter_box) -> None:
            self.adapter_box = adapter_box
            self.calls = 0

        def __call__(self, url, **kwargs):
            self.calls += 1
            return _Connection(error=OSError("transport"))

    box: dict = {}
    connect = _BlockingConnect(box)

    async def _drive() -> tuple:
        slept: List[float] = []

        async def _sleep(seconds: float) -> None:
            slept.append(float(seconds))
            entered.set()
            # A real 60-second backoff. The stop event must cut it short.
            await asyncio.sleep(60.0)

        adapter = source.HeliusEnhancedWssSource(
            config=_config(reconnect_backoff_seconds=(60.0,)),
            connect_fn=connect,
            now_fn=lambda: "2026-07-31T00:00:00Z",
            sleep_fn=_sleep,
            rand_fn=lambda: 0.0,
        )
        box["adapter"] = adapter

        async def _stop_soon() -> None:
            await entered.wait()
            adapter.request_graceful_close()

        stopper = asyncio.ensure_future(_stop_soon())
        collected = []
        async for event in adapter.iter_events_async(max_events=5):
            collected.append(event)
        await stopper
        return adapter, collected, slept

    adapter, collected, slept = asyncio.run(
        asyncio.wait_for(_drive(), timeout=10.0))
    assert collected == []
    assert slept == [60.0]          # the delay was ENTERED ...
    assert connect.calls == 1       # ... and never waited out
    assert adapter.status not in (source.STREAM_FAILED,)


def test_reconnect_success_resets_the_backoff_ladder() -> None:
    """Two outages separated by a sustained connection restart the ladder."""

    policy = _policy()
    for _ in range(3):
        policy.decide(failure_class=rp.FAILURE_TRANSIENT)
    assert policy.base_delay_for(policy.consecutive_failures) == 10.0
    policy.note_connection_established(at_epoch=0.0)
    policy.note_connection_closed(at_epoch=3_600.0)
    assert policy.consecutive_failures == 0
    first_after_reset = policy.decide(failure_class=rp.FAILURE_TRANSIENT)
    assert first_after_reset.base_delay_seconds == 1.0
    assert policy.snapshot()["backoff_resets_total"] == 1


def test_duplicate_notification_replay_after_reconnect_yields_once() -> None:
    """The SAME signature redelivered on the new socket is suppressed."""

    tracker = continuity.SourceContinuityTracker()
    first = _FakeWebSocket((
        {"jsonrpc": "2.0", "id": 1, "result": 41},
        _notification(subscription_id=41, slot=700, signature_byte=31),
        OSError("disconnect"),
    ))
    # Identical slot AND signature: an exact replay of what was already seen.
    second = _FakeWebSocket((
        {"jsonrpc": "2.0", "id": 2, "result": 42},
        _notification(subscription_id=42, slot=700, signature_byte=31),
        _notification(subscription_id=42, slot=701, signature_byte=32),
        {"jsonrpc": "2.0", "id": 3, "result": True},
    ))
    adapter = _source(
        tracker=tracker,
        connect_fn=_BoundedConnectSequence(_Connection(first), _Connection(second)),
        reconnect_backoff_seconds=(0.0,),
    )
    events = list(adapter.iter_events(max_events=2))
    signatures = [event.provider_event_id for event in events]
    assert len(signatures) == len(set(signatures))
    assert adapter.metrics.duplicate_signatures == 1
    # And the replayed row still proved its slot: no gap was invented.
    assert tracker.snapshot()["gap_detected_total"] == 0


def test_no_duplicate_subscription_after_reconnect() -> None:
    """Each socket receives exactly one subscribe request, with a fresh id."""

    first = _FakeWebSocket((
        {"jsonrpc": "2.0", "id": 1, "result": 51},
        _notification(subscription_id=51, slot=800, signature_byte=41),
        OSError("disconnect"),
    ))
    second = _FakeWebSocket((
        {"jsonrpc": "2.0", "id": 2, "result": 52},
        _notification(subscription_id=52, slot=801, signature_byte=42),
        {"jsonrpc": "2.0", "id": 3, "result": True},
    ))
    adapter = _source(
        connect_fn=_BoundedConnectSequence(_Connection(first), _Connection(second)),
        reconnect_backoff_seconds=(0.0,),
    )
    assert len(list(adapter.iter_events(max_events=2))) == 2
    subscribes_first = [item for item in first.sent
                        if item.get("method") == "transactionSubscribe"]
    subscribes_second = [item for item in second.sent
                         if item.get("method") == "transactionSubscribe"]
    assert len(subscribes_first) == 1
    assert len(subscribes_second) == 1
    assert subscribes_first[0]["id"] != subscribes_second[0]["id"]
    assert source.tight_filter_is_locked(subscribes_second[0])


def test_exact_gap_recovery_after_reconnect_requests_only_the_gap() -> None:
    class _Recoverer:
        def __init__(self) -> None:
            self.calls: List[dict] = []

        def recover(self, **kwargs) -> Any:
            self.calls.append(dict(kwargs))
            return type("Outcome", (), {
                "coverage_status": "COMPLETE",
                "complete_range_proven": True,
                "migrations": (),
                "metrics": {"estimated_credits": 10},
                "recovered_signatures": (),
                "recovered_slots": (),
                "migration_types": (),
            })()

    tracker = continuity.SourceContinuityTracker()
    recoverer = _Recoverer()
    first = _FakeWebSocket((
        {"jsonrpc": "2.0", "id": 1, "result": 61},
        _notification(subscription_id=61, slot=900, signature_byte=51),
        OSError("disconnect"),
    ))
    second = _FakeWebSocket((
        {"jsonrpc": "2.0", "id": 2, "result": 62},
        _notification(subscription_id=62, slot=910, signature_byte=52),
        {"jsonrpc": "2.0", "id": 3, "result": True},
    ))
    adapter = _source(
        tracker=tracker,
        gap_recoverer=recoverer,
        connect_fn=_BoundedConnectSequence(_Connection(first), _Connection(second)),
        reconnect_backoff_seconds=(0.0,),
    )
    assert len(list(adapter.iter_events(max_events=2))) == 2
    assert len(recoverer.calls) == 1
    # EXACTLY the missing interval -- never a widened window, never history.
    assert recoverer.calls[0]["gap_from_slot"] == 901
    assert recoverer.calls[0]["gap_to_slot"] == 909
    assert adapter.metrics.gap_recovery_attempts == 1
    assert adapter.metrics.gap_recovery_completed == 1
    assert adapter.gap_recovery_degraded is False


def test_a_bounded_retry_asks_only_for_the_unproven_remainder() -> None:
    """A retry after a partial recovery must never re-request proven ground."""

    tracker = continuity.SourceContinuityTracker(
        now_fn=lambda: "2026-07-31T00:00:00Z", max_recovery_attempts=3)
    tracker.note_slot(1_000, processed=True, durable=True)
    tracker.note_disconnect(reason_class=continuity.REASON_PROVIDER_ERROR)
    gap = tracker.note_slot(1_011, processed=True)
    assert (gap.gap_from_slot, gap.gap_to_slot) == (1_001, 1_010)

    adapter = _source(tracker=tracker, gap_recoverer=object(),
                      reconnect_backoff_seconds=(0.0,))
    adapter._pending_gap = gap

    first = adapter._next_recoverable_gap()
    assert (first.gap_from_slot, first.gap_to_slot) == (1_001, 1_010)

    # A partial answer proved the FRONT of the range.
    tracker.mark_recovery_requested(gap.gap_id, 1_001)
    tracker.apply_recovered_range(1_001, 1_005)

    retry = adapter._next_recoverable_gap()
    assert retry is not None
    assert retry.gap_id == gap.gap_id
    assert (retry.gap_from_slot, retry.gap_to_slot) == (1_006, 1_010)

    # Once the remainder is proven there is nothing left to ask for.
    tracker.apply_recovered_range(1_006, 1_010)
    assert adapter._next_recoverable_gap() is None
    assert tracker.continuity_state() == continuity.NO_GAP


def test_a_gap_out_of_attempts_stops_being_requested_and_reads_degraded(
) -> None:
    tracker = continuity.SourceContinuityTracker(
        now_fn=lambda: "2026-07-31T00:00:00Z", max_recovery_attempts=2)
    tracker.note_slot(2_000, processed=True, durable=True)
    tracker.note_disconnect(reason_class=continuity.REASON_PROVIDER_ERROR)
    gap = tracker.note_slot(2_020, processed=True)

    adapter = _source(tracker=tracker, gap_recoverer=object(),
                      reconnect_backoff_seconds=(0.0,))
    for _ in range(2):
        target = adapter._next_recoverable_gap()
        assert target is not None
        tracker.mark_recovery_requested(target.gap_id, target.gap_from_slot)
        tracker.mark_recovery_failed(
            target.gap_id, reason=continuity.FAILURE_HTTP_PROVIDER)

    assert adapter._next_recoverable_gap() is None
    assert adapter.gap_recovery_degraded is True
    assert adapter.diagnostic_snapshot()["gap_recovery_degraded"] is True


def test_persistent_reconnect_is_the_production_default() -> None:
    config = _config()
    # No ceiling is expressed as ``max_reconnects is None``; there is no second
    # flag that could disagree with it.
    assert config.max_reconnects is None
    assert config.persistent_reconnect is True
    assert config.reconnect_max_delay_seconds == 60.0
    assert 0.0 < config.reconnect_jitter_fraction <= 1.0
    assert source.DEFAULT_RECONNECT_BACKOFF_SECONDS == (
        rp.RECONNECT_LADDER_SECONDS)
    assert "<REDACTED>" in repr(config)


def test_an_explicit_ceiling_is_still_honoured_exactly() -> None:
    """A bounded caller (e.g. a one-shot connectivity probe) must stay bounded.

    Regression guard: making the production default unbounded must not turn a
    caller that explicitly asked for N reconnects into an infinite retry loop
    against an exhausted connect sequence.
    """

    bounded = _config(max_reconnects=0)
    assert bounded.persistent_reconnect is False

    sleeps: List[float] = []
    adapter = _source(
        connect_fn=_BoundedConnectSequence(
            _Connection(error=OSError("transport"))),
        sleeps=sleeps,
        max_reconnects=0,
        reconnect_backoff_seconds=(0.0,),
    )
    assert list(adapter.iter_events(max_events=1)) == []
    assert adapter.status == source.STREAM_FAILED
    assert adapter.last_refusal_reason == source.ERROR_RECONNECTS_EXHAUSTED
    assert adapter.metrics.reconnects == 0
    assert sleeps == []

    # A ceiling of two allows exactly two reconnects, then stops.
    two = _source(
        connect_fn=_BoundedConnectSequence(
            *[_Connection(error=OSError("transport")) for _ in range(3)]),
        max_reconnects=2,
        reconnect_backoff_seconds=(0.0,),
    )
    assert list(two.iter_events(max_events=1)) == []
    assert two.metrics.reconnects == 2
    assert two.status == source.STREAM_FAILED


def test_an_out_of_range_ceiling_fails_closed() -> None:
    for bad in (-1, 21, True, "5", 1.5):
        with pytest.raises(source.HeliusSourceConfigurationError):
            _config(max_reconnects=bad)


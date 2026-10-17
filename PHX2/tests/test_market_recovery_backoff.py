"""PHX2-E2E-004 — recoverable market-readiness backoff.

Deterministic, offline, fake-provider proofs that exhausting the initial
market-readiness grace period enters a bounded, observable, recoverable
``MARKET_RECOVERY_BACKOFF`` state instead of the old permanent
``MARKET_UNAVAILABLE``/``MARKET_TERMINAL`` that returned terminal forever and
never called the fetch function again.

No live run, no provider/transport connection, no real ledger.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from PHX2.free_tier_producer.paid_market_readiness import (
    GRACE_EXHAUSTION_ATTEMPTS,
    GRACE_EXHAUSTION_BOTH,
    GRACE_EXHAUSTION_TIME,
    LEGACY_TERMINAL_MIGRATED,
    LEGACY_TERMINAL_UNCLASSIFIED,
    MARKET_INDEXING,
    MARKET_INVALID,
    MARKET_READY,
    MARKET_RECOVERY_BACKOFF,
    MARKET_STALE,
    MARKET_UNAVAILABLE,
    PaidMarketReadinessConfig,
    PaidMarketReadinessTracker,
    RECOVERY_BACKOFF_NOT_DUE,
    classify_legacy_market_state,
)
from PHX2.free_tier_producer.compat.build30_watchlist import (
    WATCH_ACTIVATED_WAITING,
    WATCH_EXPIRED,
    WATCH_PENDING_1_20X,
    WatchEntry,
    Watchlist,
    is_active_watch_state,
    is_terminal_watch_state,
)
from PHX2.stage30.stage30_11_15_ping_dedupe_ledger import InMemoryPingDedupeLedger
from PHX2.tests import test_ath_activation_risk_regression as fixture


BASE = "2026-07-15T12:00:00Z"
MINT = "A" * 40 + "pump"
OTHER = "B" * 40 + "pump"


def iso_at(base_iso: str, seconds: float) -> str:
    """ISO-8601 UTC ``seconds`` after ``base_iso`` (fractional seconds allowed)."""

    d = datetime.fromisoformat(base_iso.replace("Z", "+00:00")) + timedelta(
        seconds=seconds)
    return d.astimezone(timezone.utc).isoformat()


class Clock:
    def __init__(self, value: str = BASE) -> None:
        self.value = value

    def __call__(self) -> str:
        return self.value

    def set(self, value: str) -> None:
        self.value = value

    def advance(self, seconds: float, base: str = BASE) -> None:
        self.value = iso_at(base, seconds)


class Provider:
    """A counting fake provider whose behavior can be swapped mid-test."""

    def __init__(self, builder) -> None:
        self.calls = 0
        self.builder = builder

    def __call__(self, at: str):
        self.calls += 1
        attempt = dict(self.builder(at))
        attempt.setdefault("attempt_at_utc", at)
        return attempt


def indexing(at):  # transient: provider not indexed yet
    return {"price_value": None, "mc_value": None, "lp_value": None,
            "all_present": False, "provider_market_state": MARKET_INDEXING,
            "provider_reason_code": "PROVIDER_NOT_INDEXED"}


def rate_limited(at):  # HTTP 429 -> transient
    return {"price_value": None, "mc_value": None, "lp_value": None,
            "all_present": False, "provider_market_state": MARKET_INDEXING,
            "provider_reason_code": "HTTP_429_RATE_LIMITED"}


def timeout(at):  # network timeout -> transient
    return {"price_value": None, "mc_value": None, "lp_value": None,
            "all_present": False, "provider_market_state": MARKET_INDEXING,
            "provider_reason_code": "PROVIDER_TIMEOUT"}


def server_5xx(at):  # provider 5xx -> transient
    return {"price_value": None, "mc_value": None, "lp_value": None,
            "all_present": False, "provider_market_state": MARKET_INDEXING,
            "provider_reason_code": "PROVIDER_HTTP_503"}


def incomplete(at):  # price+lp present, MC missing -> transient incomplete
    return {"price_value": "1", "mc_value": None, "lp_value": "9000",
            "all_present": False, "provider_market_state": MARKET_INDEXING,
            "provider_reason_code": "MARKET_CAP_MISSING"}


def stale(at):  # provider-classified stale (non-transient, own cadence)
    return {"price_value": "1", "mc_value": "50000", "lp_value": "9000",
            "all_present": False, "provider_market_state": MARKET_STALE,
            "provider_reason_code": "PROVIDER_STALE"}


def invalid(at):  # provider-classified invalid (non-transient)
    return {"price_value": None, "mc_value": "50000", "lp_value": "9000",
            "all_present": False, "provider_market_state": MARKET_INVALID,
            "provider_reason_code": "PRICE_INVALID"}


def wrong_mint(at):  # requested mint's fields simply never arrive -> not ready
    return {"price_value": None, "mc_value": None, "lp_value": None,
            "all_present": False, "provider_market_state": MARKET_INDEXING,
            "provider_reason_code": "MINT_NOT_FOUND"}


def malformed(at):  # non-finite/malformed values -> not all_present
    return {"price_value": "NaN", "mc_value": "Infinity", "lp_value": None,
            "all_present": False, "provider_market_state": MARKET_INVALID,
            "provider_reason_code": "NONFINITE_VALUES"}


def healthy(at, mc="50000", price="1", lp="9000", ts=None):
    return {"price_value": price, "mc_value": mc, "lp_value": lp,
            "all_present": True, "provider_market_state": MARKET_READY,
            "provider_reason_code": "REQUIRED_FIELDS_FRESH",
            "provider_timestamp_utc": ts or at}


def _resolve(tracker, provider, clock, mint=MINT, migration=None):
    return tracker.resolve(
        mint, migration_time_utc=migration, now_iso_fn=clock,
        fetch_attempt_fn=provider)


def _drive_to_recovery_by_attempts(tracker, provider, clock, attempts, mint=MINT):
    """Fire ``attempts`` transient attempts at a single frozen timestamp
    (retry_backoff must be 0 so each attempt is immediately due)."""

    res = None
    for _ in range(attempts):
        res = _resolve(tracker, provider, clock, mint=mint, migration=clock())
    return res


# ---------------------------------------------------------------------------
# 1 / 2 — exact audit hostile probe: recovery instead of permanent terminal.
# ---------------------------------------------------------------------------
def test_exact_audit_hostile_probe_recovers_after_provider_heals():
    # Default production thresholds (30 attempts / 1800s). The audit reproduced:
    #   reason_after_transient_limit = MARKET_GRACE_EXHAUSTED
    #   state_after_transient_limit  = MARKET_UNAVAILABLE
    #   basis_when_provider_recovers = MARKET_TERMINAL
    #   healthy_fetch_calls          = 0
    # After the fix, grace exhaustion is recovery backoff and a healthy fetch IS
    # performed once the recovery probe is due.
    cfg = PaidMarketReadinessConfig()  # 30 / 1800
    tracker = PaidMarketReadinessTracker(cfg)
    provider = Provider(indexing)
    clock = Clock(BASE)

    first = _resolve(tracker, provider, clock, migration=BASE)
    assert first["market_state"] == MARKET_INDEXING

    # Advance past the 1,800s grace window and attempt again -> exhaustion.
    clock.advance(1800, BASE)
    exhausted = _resolve(tracker, provider, clock)
    assert exhausted["market_state"] == MARKET_RECOVERY_BACKOFF   # not MARKET_UNAVAILABLE
    assert exhausted["market_state"] != MARKET_UNAVAILABLE
    assert exhausted["basis"] != "MARKET_TERMINAL"
    assert exhausted["market_grace_exhaustion_reason"] == GRACE_EXHAUSTION_TIME
    assert exhausted["market_next_recovery_probe_at_utc"] is not None
    healthy_calls_before = 0

    # Provider heals. Before the probe is due the healthy provider is NOT called.
    provider.builder = lambda at: healthy(at)
    clock.advance(1800 + 30, BASE)  # still < probe due (probe at 1800+60)
    not_due = _resolve(tracker, provider, clock)
    assert not_due["market_state"] == MARKET_RECOVERY_BACKOFF
    assert not_due["market_reason_code"] == RECOVERY_BACKOFF_NOT_DUE
    assert provider.calls == 2  # unchanged: no healthy fetch yet

    # At/after the probe timestamp the healthy provider IS fetched exactly once.
    clock.advance(1800 + 60, BASE)
    recovered = _resolve(tracker, provider, clock)
    assert recovered["market_state"] == MARKET_READY
    assert recovered["all_present"] is True
    healthy_fetch_calls = provider.calls - 2
    assert healthy_fetch_calls == 1          # audit reproduced 0; fix -> 1
    counters = tracker.snapshot()["counters"]
    assert counters["market_terminal_candidate_state_reached"] == 0
    assert counters["market_recovery_succeeded"] == 1


# ---------------------------------------------------------------------------
# 3 — attempt-limit exhaustion enters recovery backoff.
# ---------------------------------------------------------------------------
def test_attempt_limit_exhaustion_enters_recovery_backoff():
    tracker = PaidMarketReadinessTracker(PaidMarketReadinessConfig(
        retry_backoff_seconds=(0.0,), max_transient_attempts=30,
        indexing_grace_seconds=1_000_000.0))  # time can't drive it
    provider = Provider(indexing)
    clock = Clock(BASE)
    res = _drive_to_recovery_by_attempts(tracker, provider, clock, 30, mint=MINT)
    assert res["market_state"] == MARKET_RECOVERY_BACKOFF
    assert res["market_reason_code"] == GRACE_EXHAUSTION_ATTEMPTS
    assert provider.calls == 30


# ---------------------------------------------------------------------------
# 4 — time-limit exhaustion enters recovery backoff.
# ---------------------------------------------------------------------------
def test_time_limit_exhaustion_enters_recovery_backoff():
    tracker = PaidMarketReadinessTracker(PaidMarketReadinessConfig(
        retry_backoff_seconds=(0.0,), max_transient_attempts=1_000_000,
        indexing_grace_seconds=1800.0))
    provider = Provider(indexing)
    clock = Clock(BASE)
    _resolve(tracker, provider, clock, migration=BASE)
    clock.advance(1800, BASE)
    res = _resolve(tracker, provider, clock)
    assert res["market_state"] == MARKET_RECOVERY_BACKOFF
    assert res["market_reason_code"] == GRACE_EXHAUSTION_TIME


# ---------------------------------------------------------------------------
# 5 — both exhaustion conditions reported when both apply.
# ---------------------------------------------------------------------------
def test_both_exhaustion_conditions_reported():
    tracker = PaidMarketReadinessTracker(PaidMarketReadinessConfig(
        retry_backoff_seconds=(0.0,), max_transient_attempts=2,
        indexing_grace_seconds=1800.0))
    provider = Provider(indexing)
    clock = Clock(BASE)
    _resolve(tracker, provider, clock, migration=BASE)  # attempt 1
    clock.advance(1800, BASE)                           # time exhausted too
    res = _resolve(tracker, provider, clock)            # attempt 2 -> both
    assert res["market_state"] == MARKET_RECOVERY_BACKOFF
    assert res["market_reason_code"] == GRACE_EXHAUSTION_BOTH


# ---------------------------------------------------------------------------
# 10 / 11 / 12 — provider call gating around the recovery probe timestamp.
# ---------------------------------------------------------------------------
def test_provider_not_called_before_probe_and_once_when_due():
    tracker = PaidMarketReadinessTracker(PaidMarketReadinessConfig(
        retry_backoff_seconds=(0.0,), max_transient_attempts=1))
    provider = Provider(indexing)
    clock = Clock(BASE)
    res = _resolve(tracker, provider, clock, migration=BASE)  # exhausts at attempt 1
    assert res["market_state"] == MARKET_RECOVERY_BACKOFF
    calls_at_entry = provider.calls  # 1

    # 10/11 — before due: no fetch, explicit temporary reason.
    for offset in (1, 30, 59):
        clock.advance(offset, BASE)
        r = _resolve(tracker, provider, clock)
        assert r["market_reason_code"] == RECOVERY_BACKOFF_NOT_DUE
        assert r["market_provider_fetch_performed"] is False
    assert provider.calls == calls_at_entry

    # 12 — exactly one fetch when due.
    clock.advance(60, BASE)
    r = _resolve(tracker, provider, clock)
    assert r["market_provider_fetch_performed"] is True
    assert provider.calls == calls_at_entry + 1
    assert tracker.snapshot()["counters"]["market_recovery_probe_attempted"] == 1


# ---------------------------------------------------------------------------
# 13 / 14 / 15 / 16 — successful recovery contract.
# ---------------------------------------------------------------------------
def test_successful_recovery_resets_state_keeps_history_no_reseed():
    tracker = PaidMarketReadinessTracker(PaidMarketReadinessConfig(
        retry_backoff_seconds=(0.0,), max_transient_attempts=1))
    provider = Provider(indexing)
    clock = Clock(BASE)
    _resolve(tracker, provider, clock, migration=BASE)      # -> recovery backoff
    # One failed probe to accrue recovery history, then heal.
    clock.advance(60, BASE)
    _resolve(tracker, provider, clock)                      # failed probe #1
    provider.builder = lambda at: healthy(at)
    clock.advance(60 + 120, BASE)                           # due for probe #2
    recovered = _resolve(tracker, provider, clock)

    # 13 — restored to READY on complete fresh data.
    assert recovered["market_state"] == MARKET_READY
    assert recovered["all_present"] is True
    assert recovered["current_market_cap_usd"] == "50000"
    # 14 — active failure/backoff state reset.
    assert recovered["market_recovery_backoff_seconds"] == 0.0
    assert recovered["market_recovery_attempt_count"] == 0
    assert recovered["market_consecutive_failure_count"] == 0
    assert recovered["market_next_recovery_probe_at_utc"] is None
    assert recovered["market_recovered_at_utc"] is not None
    # 15 — historical telemetry preserved (spent recovery attempts archived).
    per_mint = tracker.snapshot()["per_mint"][0]
    assert per_mint["recovery_active"] is False
    assert any(t["to"] == MARKET_RECOVERY_BACKOFF
               for t in per_mint["transitions"])  # the failure history remains
    # 16 — same mint recovered in place; no reseed / new tracking slot.
    snap = tracker.snapshot()
    assert snap["tracked"] == 1
    assert snap["by_state"] == {MARKET_READY: 1}


# ---------------------------------------------------------------------------
# A later transient failure after recovery begins a FRESH grace cycle (the grace
# anchor is reset on recovery success) rather than immediately re-exhausting.
# ---------------------------------------------------------------------------
def test_later_transient_failure_after_recovery_starts_fresh_grace_cycle():
    tracker = PaidMarketReadinessTracker(PaidMarketReadinessConfig(
        retry_backoff_seconds=(0.0,), max_transient_attempts=30,
        indexing_grace_seconds=1800.0, ready_refresh_seconds=0.0))
    provider = Provider(indexing)
    clock = Clock(BASE)
    _resolve(tracker, provider, clock, migration=BASE)   # attempt 1 @ BASE
    clock.advance(1800, BASE)
    r = _resolve(tracker, provider, clock)               # time-exhaust -> recovery
    assert r["market_reason_code"] == GRACE_EXHAUSTION_TIME
    provider.builder = lambda at: healthy(at)
    clock.advance(1860, BASE)
    assert _resolve(tracker, provider, clock)["market_state"] == MARKET_READY

    # A later transient failure does not re-exhaust from the OLD migration anchor.
    provider.builder = indexing
    clock.advance(1860, BASE)
    fresh = _resolve(tracker, provider, clock)
    assert fresh["market_state"] == MARKET_INDEXING
    assert fresh["market_normal_attempt_count"] == 1
    # It takes another full grace window from the reset anchor to re-exhaust.
    clock.advance(1860 + 1799, BASE)
    assert _resolve(tracker, provider, clock)["market_state"] == MARKET_INDEXING
    clock.advance(1860 + 1800, BASE)
    assert _resolve(tracker, provider, clock)["market_state"] == MARKET_RECOVERY_BACKOFF


# ---------------------------------------------------------------------------
# 21 / 22 / 23 / 24 — failed probe scheduling + bounded doubling + cap.
# ---------------------------------------------------------------------------
def test_recovery_backoff_doubles_deterministically_and_caps():
    tracker = PaidMarketReadinessTracker(PaidMarketReadinessConfig(
        retry_backoff_seconds=(0.0,), max_transient_attempts=1,
        recovery_initial_delay_seconds=60.0, recovery_backoff_multiplier=2.0,
        recovery_max_delay_seconds=900.0))
    provider = Provider(indexing)
    clock = Clock(BASE)
    entered = _resolve(tracker, provider, clock, migration=BASE)
    assert entered["market_recovery_backoff_seconds"] == 60.0  # initial

    # Sequence of scheduled delays across failed probes: 60,120,240,480,900,900.
    expected = [120.0, 240.0, 480.0, 900.0, 900.0]
    cumulative = 0.0
    prev_delay = 60.0
    observed = []
    for _ in expected:
        cumulative += prev_delay  # advance to the current probe's due time
        clock.advance(cumulative, BASE)
        r = _resolve(tracker, provider, clock)
        assert r["market_state"] == MARKET_RECOVERY_BACKOFF  # 24 — still recoverable
        observed.append(r["market_recovery_backoff_seconds"])
        prev_delay = r["market_recovery_backoff_seconds"]
    assert observed == expected                    # 22 doubling, 23 cap at 900
    # 21 — each failed probe scheduled the next probe timestamp.
    assert tracker.snapshot()["counters"]["market_recovery_probe_failed"] == len(expected)


# ---------------------------------------------------------------------------
# 25 / 26 / 27 / 29 — transient failure classes reach recovery and heal.
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("builder", (
    rate_limited, timeout, incomplete, server_5xx))
def test_transient_failure_classes_reach_recovery_and_heal(builder):
    tracker = PaidMarketReadinessTracker(PaidMarketReadinessConfig(
        retry_backoff_seconds=(0.0,), max_transient_attempts=1))
    provider = Provider(builder)
    clock = Clock(BASE)
    res = _resolve(tracker, provider, clock, migration=BASE)  # exhaust on attempt 1
    assert res["market_state"] == MARKET_RECOVERY_BACKOFF
    provider.builder = lambda at: healthy(at)
    clock.advance(60, BASE)
    healed = _resolve(tracker, provider, clock)
    assert healed["market_state"] == MARKET_READY


# ---------------------------------------------------------------------------
# 28 — stale/invalid classes are non-transient: they never terminalize, keep
# their own retry cadence, and heal to READY on a later valid tick.
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(("builder", "state"), (
    (stale, MARKET_STALE), (invalid, MARKET_INVALID)))
def test_stale_and_invalid_never_terminalize_and_recover(builder, state):
    tracker = PaidMarketReadinessTracker(PaidMarketReadinessConfig(
        retry_backoff_seconds=(0.0,), max_transient_attempts=1,
        stale_refresh_seconds=0.0, invalid_refresh_seconds=0.0))
    provider = Provider(builder)
    clock = Clock(BASE)
    for _ in range(5):
        r = _resolve(tracker, provider, clock, migration=BASE)
        assert r["market_state"] == state           # stays recoverable, never
        assert r["market_state"] != MARKET_UNAVAILABLE   # permanently terminal
    provider.builder = lambda at: healthy(at)
    healed = _resolve(tracker, provider, clock)
    assert healed["market_state"] == MARKET_READY
    assert tracker.snapshot()["counters"]["market_terminal_candidate_state_reached"] == 0


# ---------------------------------------------------------------------------
# 30 — global config/auth failure is not converted to per-mint retry.
# ---------------------------------------------------------------------------
def test_global_config_failure_is_refused_not_per_mint_retry():
    # A structurally invalid runtime configuration is refused at construction
    # (its existing global owner), never silently turned into an infinite
    # per-mint readiness retry loop.
    with pytest.raises(ValueError):
        PaidMarketReadinessConfig(indexing_grace_seconds=0)
    with pytest.raises(ValueError):
        PaidMarketReadinessConfig(max_transient_attempts=0)
    # Provider authorization failures are owned by the stream/session layer
    # (STREAM_STATUS_AUTH_FAILED) and never routed through this per-mint tracker.
    from PHX2.free_tier_producer.paid_provider import STREAM_STATUS_AUTH_FAILED
    assert STREAM_STATUS_AUTH_FAILED == "AUTH_FAILED"


# ---------------------------------------------------------------------------
# 31 / 32 / 33 — recovery success requires complete fresh actionable data.
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("builder", (
    incomplete, wrong_mint, malformed, stale, invalid))
def test_incomplete_wrong_mint_or_malformed_is_not_recovery_success(builder):
    tracker = PaidMarketReadinessTracker(PaidMarketReadinessConfig(
        retry_backoff_seconds=(0.0,), max_transient_attempts=1))
    provider = Provider(indexing)
    clock = Clock(BASE)
    _resolve(tracker, provider, clock, migration=BASE)  # -> recovery backoff
    provider.builder = builder
    clock.advance(60, BASE)  # probe due
    res = _resolve(tracker, provider, clock)
    assert res["market_state"] == MARKET_RECOVERY_BACKOFF  # NOT recovered
    assert res["all_present"] is False
    assert tracker.snapshot()["counters"]["market_recovery_succeeded"] == 0


# ---------------------------------------------------------------------------
# 38 / 39 / 40 — multi-candidate independence + single fetch per due tick.
# ---------------------------------------------------------------------------
def test_two_candidates_have_independent_recovery_schedules():
    tracker = PaidMarketReadinessTracker(PaidMarketReadinessConfig(
        retry_backoff_seconds=(0.0,), max_transient_attempts=1))
    clock = Clock(BASE)
    pa, pb = Provider(indexing), Provider(indexing)
    ra = _resolve(tracker, pa, clock, mint=MINT, migration=BASE)
    # B is seeded 100s later, so its probe schedule is offset from A's.
    clock.advance(100, BASE)
    rb = _resolve(tracker, pb, clock, mint=OTHER, migration=iso_at(BASE, 100))
    assert ra["market_state"] == rb["market_state"] == MARKET_RECOVERY_BACKOFF
    assert (ra["market_next_recovery_probe_at_utc"]
            != rb["market_next_recovery_probe_at_utc"])  # 38 independent

    # 39 — A recovers; B is untouched and stays in recovery backoff.
    pa.builder = lambda at: healthy(at)
    clock.advance(60, BASE)  # A's probe due; B's is not (due at 100+60)
    a_recovered = _resolve(tracker, pa, clock, mint=MINT)
    assert a_recovered["market_state"] == MARKET_READY
    b_state = next(r for r in tracker.snapshot()["per_mint"]
                   if r["token_mint"] == OTHER)
    assert b_state["market_state"] == MARKET_RECOVERY_BACKOFF
    assert b_state["recovery_active"] is True


def test_multiple_calls_at_same_due_timestamp_fetch_once():
    tracker = PaidMarketReadinessTracker(PaidMarketReadinessConfig(
        retry_backoff_seconds=(0.0,), max_transient_attempts=1))
    provider = Provider(indexing)
    clock = Clock(BASE)
    _resolve(tracker, provider, clock, migration=BASE)  # -> recovery
    calls_before = provider.calls
    clock.advance(60, BASE)  # due
    # First call at due probes; a second call at the SAME timestamp must not
    # re-fetch (a failed probe reschedules to a strictly later time).
    _resolve(tracker, provider, clock)
    _resolve(tracker, provider, clock)
    assert provider.calls == calls_before + 1


# ---------------------------------------------------------------------------
# Boundary — attempt count 29 / 30 / 31.
# ---------------------------------------------------------------------------
def test_attempt_count_boundary_29_then_30():
    tracker = PaidMarketReadinessTracker(PaidMarketReadinessConfig(
        retry_backoff_seconds=(0.0,), max_transient_attempts=30,
        indexing_grace_seconds=1_000_000.0))
    provider = Provider(indexing)
    clock = Clock(BASE)
    r29 = _drive_to_recovery_by_attempts(tracker, provider, clock, 29)
    assert r29["market_state"] == MARKET_INDEXING          # 29: not yet
    r30 = _resolve(tracker, provider, clock)               # 30th attempt
    assert r30["market_state"] == MARKET_RECOVERY_BACKOFF  # 30: exhausted
    # A 31st normal transient attempt cannot occur — the mint is now recovery
    # backoff and gated by the probe timestamp, not the aggressive schedule.
    r31 = _resolve(tracker, provider, clock)
    assert r31["market_reason_code"] == RECOVERY_BACKOFF_NOT_DUE
    assert provider.calls == 30


# ---------------------------------------------------------------------------
# Boundary — elapsed grace 1799 / 1800 / 1801 seconds.
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(("elapsed", "expect_recovery"), (
    (1799, False), (1800, True), (1801, True)))
def test_grace_time_boundary(elapsed, expect_recovery):
    tracker = PaidMarketReadinessTracker(PaidMarketReadinessConfig(
        retry_backoff_seconds=(0.0,), max_transient_attempts=1_000_000,
        indexing_grace_seconds=1800.0))
    provider = Provider(indexing)
    clock = Clock(BASE)
    _resolve(tracker, provider, clock, migration=BASE)
    clock.advance(elapsed, BASE)
    res = _resolve(tracker, provider, clock)
    if expect_recovery:
        assert res["market_state"] == MARKET_RECOVERY_BACKOFF
    else:
        assert res["market_state"] == MARKET_INDEXING


# ---------------------------------------------------------------------------
# Boundary — recovery due one microsecond before / at / after due.
# ---------------------------------------------------------------------------
def test_recovery_due_microsecond_boundary():
    tracker = PaidMarketReadinessTracker(PaidMarketReadinessConfig(
        retry_backoff_seconds=(0.0,), max_transient_attempts=1))
    provider = Provider(indexing)
    clock = Clock(BASE)
    _resolve(tracker, provider, clock, migration=BASE)  # exhaust at BASE -> probe at +60s
    calls_at_entry = provider.calls

    clock.set(iso_at(BASE, 60 - 1e-6))                  # 1us before due
    r = _resolve(tracker, provider, clock)
    assert r["market_reason_code"] == RECOVERY_BACKOFF_NOT_DUE
    assert provider.calls == calls_at_entry

    clock.set(iso_at(BASE, 60))                         # exactly due
    r = _resolve(tracker, provider, clock)
    assert r["market_provider_fetch_performed"] is True
    assert provider.calls == calls_at_entry + 1


# ---------------------------------------------------------------------------
# 6 / 7 / 8 / 9 — watch entry stays active, capacity-holding, non-terminal, and
# survives a checkpoint round trip while in recovery backoff.
# ---------------------------------------------------------------------------
def _recovery_entry(status=WATCH_ACTIVATED_WAITING, mint=MINT):
    return WatchEntry(
        token_mint=mint, candidate_id="rec", migration_time_utc=BASE,
        source_ref="proof", seeded_at_utc=BASE, status=status,
        last_observed_at_utc=iso_at(BASE, 300),
        market_state=MARKET_RECOVERY_BACKOFF,
        market_reason_code=RECOVERY_BACKOFF_NOT_DUE,
        next_market_refresh_at_utc=iso_at(BASE, 360))


def test_recovery_entry_is_active_capacity_holding_and_not_terminal_history(tmp_path):
    wl = Watchlist(max_size=4, terminal_history_path=tmp_path / "th.jsonl")
    entry = _recovery_entry()
    wl._entries[entry.token_mint] = entry
    assert is_active_watch_state(entry.status)        # 6/7 active, holds a slot
    assert not is_terminal_watch_state(entry.status)  # 8 not terminal
    assert wl.active_count() == 1
    assert wl.terminal_history_count() == 0
    s = wl.summary()
    assert s["market_recovery_backoff"] == 1
    assert s["active"] == 1


def test_recovery_state_survives_active_checkpoint_round_trip(tmp_path):
    wl = Watchlist(max_size=4, terminal_history_path=tmp_path / "th.jsonl")
    entry = _recovery_entry()
    wl._entries[entry.token_mint] = entry
    path = tmp_path / "watch_state.jsonl"
    wl.persist(path)
    restored = Watchlist.load(path, max_size=4,
                              terminal_history_path=tmp_path / "th2.jsonl")
    got = restored.get(entry.token_mint)
    assert got is not None
    assert got.market_state == MARKET_RECOVERY_BACKOFF     # 9 round-trips
    assert got.next_market_refresh_at_utc == iso_at(BASE, 360)
    assert restored.active_count() == 1
    assert restored.terminal_history_count() == 0


# ---------------------------------------------------------------------------
# 34 / 35 — a recovery candidate expires normally, archives, releases capacity.
# ---------------------------------------------------------------------------
def test_recovery_candidate_expires_normally_and_releases_capacity(tmp_path):
    wl = Watchlist(max_size=1, terminal_history_path=tmp_path / "th.jsonl")
    entry = _recovery_entry(status=WATCH_PENDING_1_20X)
    wl._entries[entry.token_mint] = entry
    assert wl.active_count() == 1
    expired = wl.expire_stale_entries(
        now_age_seconds_fn=lambda _seeded: 999999.0,
        max_age_seconds=1, max_rechecks=999999, now_utc=iso_at(BASE, 999999))
    assert len(expired) == 1
    assert expired[0].status == WATCH_EXPIRED             # explicit terminal reason
    assert wl.active_count() == 0                         # slot released
    assert wl.terminal_history_count() == 1               # archived


# ---------------------------------------------------------------------------
# 36 / 37 — legacy MARKET_TERMINAL migration on restore.
# ---------------------------------------------------------------------------
def test_legacy_transient_market_terminal_restores_as_recovery_backoff(tmp_path):
    # A fully-baselined candidate whose persisted market-readiness was left
    # permanently terminal by the old code (MARKET_UNAVAILABLE / grace-exhausted).
    entry = fixture._entry()
    assert entry.status == WATCH_PENDING_1_20X
    entry.market_state = MARKET_UNAVAILABLE
    entry.market_reason_code = "MARKET_GRACE_EXHAUSTED"
    entry.last_observed_at_utc = iso_at(BASE, 500)
    wl = Watchlist(); wl._entries[entry.token_mint] = entry
    path = tmp_path / "watch_state.jsonl"
    wl.persist(path)
    restored = Watchlist.load(path, now_utc=iso_at(BASE, 3600))
    got = restored.get(entry.token_mint)
    assert got is not None
    # Market readiness restored as recoverable backoff (never permanently dead).
    assert got.market_state == MARKET_RECOVERY_BACKOFF
    assert got.market_reason_code == LEGACY_TERMINAL_MIGRATED
    assert got.market_legacy_terminal_migrated is True
    assert got.next_market_refresh_at_utc == "2026-07-15T13:01:00Z"  # now + 60s
    # Candidate/baseline state preserved; not archived; still active.
    assert got.status == WATCH_PENDING_1_20X
    assert got.migration_market_cap_usd == fixture.BASELINE
    assert got.activation_target_market_cap_usd == fixture.TARGET
    assert restored.active_count() == 1
    assert restored.terminal_history_count() == 0
    assert restored.summary()["market_legacy_terminal_migrated"] == 1


def test_ambiguous_legacy_market_terminal_fails_closed_visibly(tmp_path):
    entry = WatchEntry(
        token_mint=MINT, candidate_id="ambig", migration_time_utc=BASE,
        source_ref="proof", seeded_at_utc=BASE, status=WATCH_ACTIVATED_WAITING,
        market_state=MARKET_UNAVAILABLE, market_reason_code="SOME_UNKNOWN_REASON")
    wl = Watchlist(); wl._entries[MINT] = entry
    path = tmp_path / "watch_state.jsonl"
    wl.persist(path)
    restored = Watchlist.load(path, now_utc=iso_at(BASE, 3600))
    got = restored.get(MINT)
    assert got is not None
    # Not guessed into recovery: preserved terminal state, visibly flagged.
    assert got.market_state == MARKET_UNAVAILABLE
    assert got.market_reason_code == LEGACY_TERMINAL_UNCLASSIFIED
    assert got.market_legacy_terminal_migrated is False
    assert restored.summary()["market_legacy_terminal_unclassified"] == 1


def test_classify_legacy_market_state_unit():
    assert classify_legacy_market_state(
        MARKET_UNAVAILABLE, "MARKET_GRACE_EXHAUSTED") == (True, LEGACY_TERMINAL_MIGRATED)
    assert classify_legacy_market_state(
        MARKET_UNAVAILABLE, GRACE_EXHAUSTION_ATTEMPTS) == (True, LEGACY_TERMINAL_MIGRATED)
    assert classify_legacy_market_state(
        MARKET_UNAVAILABLE, "MYSTERY") == (False, LEGACY_TERMINAL_UNCLASSIFIED)
    assert classify_legacy_market_state(MARKET_UNAVAILABLE, None) == (
        False, LEGACY_TERMINAL_UNCLASSIFIED)
    assert classify_legacy_market_state(MARKET_READY, "x") == (False, "")


# ---------------------------------------------------------------------------
# Restart seeding — a restored recovery candidate does not immediately hammer
# the provider (the tracker is seeded from its persisted probe time).
# ---------------------------------------------------------------------------
def test_seeded_recovery_state_does_not_hammer_provider_before_due():
    tracker = PaidMarketReadinessTracker(PaidMarketReadinessConfig(
        retry_backoff_seconds=(0.0,), max_transient_attempts=1))
    ok = tracker.seed_recovery_state(
        MINT, now_iso=iso_at(BASE, 3600),
        next_recovery_probe_at_utc=iso_at(BASE, 3660), legacy_migrated=True)
    assert ok is True
    provider = Provider(indexing)
    clock = Clock(iso_at(BASE, 3600))
    r = _resolve(tracker, provider, clock)
    assert r["market_state"] == MARKET_RECOVERY_BACKOFF
    assert r["market_reason_code"] == RECOVERY_BACKOFF_NOT_DUE
    assert provider.calls == 0  # not due -> no immediate fetch
    assert tracker.snapshot()["counters"]["market_legacy_terminal_migrated"] == 1
    # When due it probes and can recover.
    provider.builder = lambda at: healthy(at)
    clock.set(iso_at(BASE, 3660))
    r = _resolve(tracker, provider, clock)
    assert r["market_state"] == MARKET_READY
    assert provider.calls == 1


def test_deadline_scheduler_failures_reuse_recovery_backoff_and_due_policy():
    tracker = PaidMarketReadinessTracker(PaidMarketReadinessConfig(
        retry_backoff_seconds=(0.0,), max_transient_attempts=1,
        recovery_initial_delay_seconds=60.0))
    failed = {
        "price_value": None, "mc_value": None, "lp_value": None,
        "provider_market_state": MARKET_INDEXING,
        "provider_reason_code": "PROVIDER_TIMEOUT", "all_present": False,
    }
    first = tracker.observe_scheduled_attempt(
        MINT, migration_time_utc=BASE, now_iso=BASE, attempt=failed)
    assert first["market_state"] == MARKET_RECOVERY_BACKOFF
    assert first["next_market_refresh_at_utc"] == "2026-07-15T12:01:00Z"
    before = tracker.snapshot()["per_mint"][0]["attempt_count"]
    early = tracker.observe_scheduled_attempt(
        MINT, migration_time_utc=BASE, now_iso=iso_at(BASE, 30), attempt=failed)
    assert early["market_reason_code"] == RECOVERY_BACKOFF_NOT_DUE
    assert tracker.snapshot()["per_mint"][0]["attempt_count"] == before


def test_parallel_field_failure_does_not_advance_normal_retry_backoff_twice():
    tracker = PaidMarketReadinessTracker(PaidMarketReadinessConfig(
        retry_backoff_seconds=(10.0,), max_transient_attempts=30))
    failed = {
        "price_value": None, "mc_value": None, "lp_value": None,
        "provider_market_state": MARKET_INDEXING,
        "provider_reason_code": "PROVIDER_TIMEOUT", "all_present": False,
    }
    first = tracker.observe_scheduled_attempt(
        MINT, migration_time_utc=BASE, now_iso=BASE, attempt=failed)
    second = tracker.observe_scheduled_attempt(
        MINT, migration_time_utc=BASE, now_iso=BASE, attempt=failed)
    assert first["market_attempt_count"] == 1
    assert second["market_attempt_count"] == 1
    assert second["next_market_refresh_at_utc"] == "2026-07-15T12:00:10Z"


def test_deadline_scheduler_complete_late_result_recovers_without_recrossing():
    tracker = PaidMarketReadinessTracker(PaidMarketReadinessConfig(
        retry_backoff_seconds=(0.0,), max_transient_attempts=1))
    failed = {
        "provider_market_state": MARKET_INDEXING,
        "provider_reason_code": "PROVIDER_5XX", "all_present": False,
    }
    tracker.observe_scheduled_attempt(
        MINT, migration_time_utc=BASE, now_iso=BASE, attempt=failed)
    recovered = tracker.observe_scheduled_attempt(
        MINT, migration_time_utc=BASE, now_iso=iso_at(BASE, 1),
        attempt={
            "price_value": "1", "mc_value": "100", "lp_value": "5000",
            "provider_timestamp_utc": iso_at(BASE, 1),
            "provider_market_state": MARKET_READY, "all_present": True,
        })
    assert recovered["market_state"] == MARKET_READY
    assert recovered["all_present"] is True
    assert tracker.snapshot()["counters"]["market_recovery_succeeded"] == 1


# ---------------------------------------------------------------------------
# 17 / 18 / 19 / 20 — activation-latch compatibility across recovery.
# ---------------------------------------------------------------------------
def _observe_missing(entry, central_ath, *, at=fixture.ACTED_AT):
    return entry.observe_market(
        current_market_cap_usd=None, current_price=None, current_supply=None,
        provider_timestamp_utc=None, observed_at_utc=at,
        observation_source="PAID_MARKET_PRIMARY", max_age_seconds=120,
        central_ath=central_ath, pumpswap_reserve=None)


def _recover_tracker_for(mint, *, recovered_builder):
    """Exhaust a tracker for ``mint`` and recover it via ``recovered_builder``.
    Returns the recovered readiness context (all_present=True)."""

    tracker = PaidMarketReadinessTracker(PaidMarketReadinessConfig(
        retry_backoff_seconds=(0.0,), max_transient_attempts=1))
    provider = Provider(indexing)
    clock = Clock(BASE)
    _resolve(tracker, provider, clock, mint=mint, migration=BASE)  # -> recovery
    provider.builder = recovered_builder
    clock.advance(60, BASE)  # probe due
    return _resolve(tracker, provider, clock, mint=mint)


def test_recovered_activation_needs_no_recrossing_and_enters_dip_watch():
    entry = fixture._entry()
    crossing = fixture._central_evidence(fixture.ACTIVATING_HIGH)
    activated = _observe_missing(entry, crossing)
    assert activated["reason"] == WATCH_ACTIVATED_WAITING
    assert entry.activation_latched is True
    latched_digest = entry.activation_proof_digest

    # Market readiness recovers with a genuinely-later fresh observation.
    recovered = _recover_tracker_for(
        fixture.MINT,
        recovered_builder=lambda at: healthy(
            at, mc=fixture.TIER1_MC,
            price=fixture._price_for_market_cap(fixture.TIER1_MC),
            ts=fixture.TIER1_AT))
    assert recovered["market_state"] == MARKET_READY

    latest = fixture._central_evidence(
        fixture.LATEST_ATH, event_at=fixture.LATEST_ATH_AT,
        ingested_at=fixture.LATEST_INGESTED_AT)
    tier = entry.observe_market(
        current_market_cap_usd=recovered["current_market_cap_usd"],
        current_price=recovered["current_price"],
        current_supply="1000000000",
        provider_timestamp_utc=recovered["provider_timestamp_utc"],
        observed_at_utc=fixture.TIER1_AT,
        observation_source="PAID_MARKET_PRIMARY", max_age_seconds=120,
        central_ath=latest)
    # 17 — no second 1.20x crossing; activation evidence unchanged, still latched.
    assert tier["just_activated"] is False
    assert entry.activation_latched is True
    assert entry.activation_evidence_market_cap_usd == fixture.ACTIVATING_HIGH
    assert entry.activation_proof_digest == latched_digest
    # 18 — recovered activated candidate enters ACTIVE_DIP_WATCH.
    assert tier["eligible"] is True
    from PHX2.free_tier_producer.compat.build30_watchlist import WATCH_ACTIVE_DIP
    assert entry.status == WATCH_ACTIVE_DIP


def test_recovered_activation_projects_tier1_on_later_valid_tick(tmp_path):
    entry = fixture._entry()
    crossing = fixture._central_evidence(fixture.ACTIVATING_HIGH)
    _observe_missing(entry, crossing)
    assert entry.activation_latched is True
    # Recovery restores market readiness for the mint.
    recovered = _recover_tracker_for(
        fixture.MINT, recovered_builder=lambda at: healthy(at, ts=fixture.TIER1_AT))
    assert recovered["market_state"] == MARKET_READY

    latest = fixture._central_evidence(
        fixture.LATEST_ATH, event_at=fixture.LATEST_ATH_AT,
        ingested_at=fixture.LATEST_INGESTED_AT)
    ledger = InMemoryPingDedupeLedger()
    guard = fixture._FakeGuard()
    tier1, _ = fixture._run_fake_tier(
        entry=entry, current_mc=fixture.TIER1_MC, at=fixture.TIER1_AT,
        central_ath=latest, ledger=ledger, guard=guard, tmp_path=tmp_path)
    # 19 — a later valid tick projects Tier 1 after recovery.
    assert tier1["per_candidate"][0]["compose_tier"] == "Tier 1"
    assert entry.activation_latched is True
    assert entry.activation_evidence_market_cap_usd == fixture.ACTIVATING_HIGH


def test_recovery_observation_cannot_replay_the_activation_crossing_tick():
    entry = fixture._entry()
    crossing = fixture._central_evidence(fixture.ACTIVATING_HIGH)
    _observe_missing(entry, crossing)
    original_digest = entry.activation_proof_digest

    # Recovery yields a fresh READY observation whose provider timestamp is NOT
    # genuinely later than the activation crossing (equal to the crossing event).
    recovered = _recover_tracker_for(
        fixture.MINT,
        recovered_builder=lambda at: healthy(
            at, mc=fixture.TIER1_MC,
            price=fixture._price_for_market_cap(fixture.TIER1_MC),
            ts=fixture.HIGH_AT))
    assert recovered["market_state"] == MARKET_READY

    result = entry.observe_market(
        current_market_cap_usd=recovered["current_market_cap_usd"],
        current_price=recovered["current_price"], current_supply="1000000000",
        provider_timestamp_utc=recovered["provider_timestamp_utc"],  # HIGH_AT
        observed_at_utc=fixture.ACTED_AT,
        observation_source="PAID_MARKET_PRIMARY", max_age_seconds=120,
        central_ath=None)
    # 20 — the recovery observation cannot replay the crossing tick; it is not a
    # later dip and it never re-fires activation or mutates the proof.
    assert result["eligible"] is False
    assert result["reason"] == "ACTIVATION_LATER_MARKET_TICK_REQUIRED"
    assert result["just_activated"] is False
    assert entry.activation_latched is True
    assert entry.activation_proof_digest == original_digest


# ---------------------------------------------------------------------------
# 41 / 42 / 43 — a recovery-backoff candidate composes/reserves/sends nothing.
# ---------------------------------------------------------------------------
class _RecoveryBackoffSidecar:
    def resolve(self, mint, **kwargs):
        return {
            "current_price": None, "current_market_cap_usd": None,
            "liquidity_usd": None,
            "market_context_fetched_at_utc": fixture.ACTED_AT,
            "provider_timestamp_utc": None, "all_present": False,
            "market_state": MARKET_RECOVERY_BACKOFF,
            "market_reason_code": RECOVERY_BACKOFF_NOT_DUE,
            "basis": MARKET_RECOVERY_BACKOFF, "attempts": [],
            "central_ath": {}, "pumpswap_reserve": {},
            "next_market_refresh_at_utc": iso_at(fixture.ACTED_AT, 60),
            "market_attempt_count": 5,
        }


class _ForbiddenGuard:
    calls = 0

    def authorize_and_dispatch(self, *a, **k):
        self.calls += 1
        raise AssertionError("recovery-backoff candidate reached delivery")


def test_recovery_backoff_generates_no_compose_reservation_or_ledger_row():
    from datetime import datetime as _dt
    from decimal import Decimal
    ledger = InMemoryPingDedupeLedger()
    guard = _ForbiddenGuard()

    def activation_gate(candidate, context):
        # Activated & tier-eligible so control reaches the market-readiness gate.
        return {"activation": {"activation_latched": True}, "eligible": True}

    result = fixture.producer_session.sess.run_cap1_candidates(
        [{"token_mint": MINT, "candidate_id": "rec",
          "migration_time_utc": fixture.ACTED_AT}],
        sidecar=_RecoveryBackoffSidecar(),
        ath_transport=None, ath_endpoint_secret=None,
        now_utc=_dt.fromisoformat(fixture.ACTED_AT.replace("Z", "+00:00")),
        now_seconds=lambda: Decimal(0), now_iso_fn=lambda: fixture.ACTED_AT,
        sleep_fn=lambda _s: None, ledger=ledger, guard=guard,
        authorization=object(), created_at_utc=fixture.ACTED_AT,
        activation_gate_fn=activation_gate)
    rec = result["per_candidate"][0]
    assert result["outcome"] == "ZERO_SEND"
    assert rec["market_state"] == MARKET_RECOVERY_BACKOFF
    assert rec["reason"] == "NO_SEND_MARKET_RECOVERY_BACKOFF"
    assert rec.get("compose_decision") is None        # 41 no compose
    assert result["sent_attempt"] is None
    assert len(ledger._state) == 0                     # 42/43 no reservation/row
    assert guard.calls == 0

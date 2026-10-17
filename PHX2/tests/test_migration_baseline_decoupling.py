"""Baseline observation decoupled from send authorization (Part 4).

The investigated defect: baseline capture only existed at seed time or inside
the security-gated engine, so all 28 tracked candidates stayed
PENDING_BASELINE forever (market_calls=0 for activation) while the pricing
tail burned 2,903 ungated market calls.  These tests pin the corrected seam:
pricing-tail observations feed the centralized watch state for every tracked
mint — including security-blocked candidates — with NO compose, NO reserve,
NO ledger mutation, NO transport, and the crossing tick still send-blocked.
"""

from datetime import datetime, timezone
from decimal import Decimal

from PHX2.free_tier_producer import free_tier_session as producer_session
from PHX2.free_tier_producer.compat.build30_watchlist import (
    BASELINE_CAPTURED,
    BASELINE_PENDING,
    WATCH_ACTIVE_DIP,
    WATCH_PENDING_1_20X,
    WATCH_PENDING_BASELINE,
    Watchlist,
)


MINT = "EkNbQMQYpd4JET5FpZrqbdkYdHXeqocZcBByJpFWpump"
NOW = "2026-07-17T12:00:00Z"
LATER = "2026-07-17T12:01:00Z"
LATEST = "2026-07-17T12:02:00Z"
STALE_TS = "2026-07-17T11:00:00Z"


def _seeded_watchlist():
    watchlist = Watchlist(max_size=4)
    entry = watchlist.seed(
        {"token_mint": MINT, "candidate_id": "cand-1",
         "migration_time_utc": NOW, "source_ref": "ref-1"},
        seeded_at_utc=NOW)
    assert entry is not None and entry.status == WATCH_PENDING_BASELINE
    return watchlist, entry


def _market(mc, *, at=NOW):
    return {
        "current_market_cap_usd": mc,
        "current_price": "0.0001",
        "supply_at_observation": "1000000000",
        "provider_timestamp_utc": at,
        "fetched_at_utc": at,
    }


def _observe(watchlist, market, *, now_iso=NOW, source="PAID_MARKET_PRIMARY",
             events=None):
    return producer_session.observe_watchlist_baseline(
        watchlist=watchlist, mint=MINT, market=market,
        observation_source=source, max_age_seconds=120.0, now_iso=now_iso,
        on_activation_event=(events.append if events is not None else None))


def test_fresh_observation_captures_the_immutable_baseline_once():
    watchlist, entry = _seeded_watchlist()
    events = []
    observed = _observe(watchlist, _market("100"), events=events)
    assert observed is not None
    assert entry.migration_baseline_status == BASELINE_CAPTURED
    assert entry.status == WATCH_PENDING_1_20X
    assert entry.migration_market_cap_usd == "100"
    assert entry.activation_target_market_cap_usd == "120.00"
    assert any(event.get("event") == "BASELINE_CAPTURED" for event in events)
    # A later, different observation can never rewrite the immutable baseline.
    _observe(watchlist, _market("90", at=LATER), now_iso=LATER)
    assert entry.migration_market_cap_usd == "100"


def test_crossing_tick_is_send_blocked_and_next_fresh_observation_is_eligible():
    watchlist, entry = _seeded_watchlist()
    _observe(watchlist, _market("100"))
    crossing = _observe(watchlist, _market("125", at=LATER), now_iso=LATER)
    assert crossing["just_activated"] is True
    assert crossing["eligible"] is False              # crossing-tick-send block
    assert entry.status == WATCH_ACTIVE_DIP
    following = _observe(watchlist, _market("126", at=LATEST), now_iso=LATEST)
    assert following["just_activated"] is False
    assert following["eligible"] is True
    assert entry.is_dip_active()


def test_stale_observation_never_captures_a_baseline():
    watchlist, entry = _seeded_watchlist()
    observed = _observe(watchlist, _market("100", at=STALE_TS))
    assert observed["eligible"] is False
    assert entry.migration_baseline_status == BASELINE_PENDING
    assert entry.status == WATCH_PENDING_BASELINE


def test_non_paid_primary_source_keeps_the_existing_pending_posture():
    watchlist, entry = _seeded_watchlist()
    observed = _observe(watchlist, _market("100"), source="NON_PAID_PRIMARY")
    assert observed["eligible"] is False
    assert entry.migration_baseline_status == BASELINE_PENDING


def test_inactive_or_unknown_entries_and_bad_markets_are_ignored():
    watchlist, entry = _seeded_watchlist()
    entry.status = "SEND_ATTEMPTED"
    assert _observe(watchlist, _market("100")) is None
    assert producer_session.observe_watchlist_baseline(
        watchlist=watchlist, mint="missing", market=_market("100"),
        observation_source="PAID_MARKET_PRIMARY", max_age_seconds=120.0,
        now_iso=NOW) is None
    assert producer_session.observe_watchlist_baseline(
        watchlist=watchlist, mint=MINT, market=None,
        observation_source="PAID_MARKET_PRIMARY", max_age_seconds=120.0,
        now_iso=NOW) is None


def test_activation_event_sink_errors_never_break_the_observation():
    watchlist, entry = _seeded_watchlist()

    def _explode(_record):
        raise RuntimeError("sink down")

    observed = producer_session.observe_watchlist_baseline(
        watchlist=watchlist, mint=MINT, market=_market("100"),
        observation_source="PAID_MARKET_PRIMARY", max_age_seconds=120.0,
        now_iso=NOW, on_activation_event=_explode)
    assert observed is not None
    assert entry.migration_baseline_status == BASELINE_CAPTURED


# ---------------------------------------------------------------------------
# Runner level: security-blocked candidates observe but never compose/send
# ---------------------------------------------------------------------------


def test_security_blocked_candidate_baselines_and_activates_without_any_send():
    watchlist, entry = _seeded_watchlist()
    clock = {"mono": 0.0}
    activation_events = []
    security_calls = {"count": 0}
    market_observations = iter([
        ("100", NOW), ("125", LATER), ("126", LATEST)])

    def security_decision_fn(_entry):
        security_calls["count"] += 1
        return None            # -> SECURITY_DECISION_PROOF_MISSING hard block

    def run_engine(_candidates, **_kwargs):
        raise AssertionError(
            "security-blocked candidates must never reach the engine")

    def on_cycle(**_kwargs):
        # The production session performs exactly this observation on the
        # pricing-tail path each tick; blocked candidates still observe.
        observation = next(market_observations, None)
        if observation is not None:
            mc, observed_at = observation
            producer_session.observe_watchlist_baseline(
                watchlist=watchlist, mint=MINT,
                market=_market(mc, at=observed_at),
                observation_source="PAID_MARKET_PRIMARY",
                max_age_seconds=120.0, now_iso=observed_at,
                on_activation_event=activation_events.append)

    def sleep_fn(seconds):
        clock["mono"] += float(seconds)

    result = producer_session.run_production_live_watch(
        watchlist=watchlist,
        axiom_source=producer_session.axiomgate.NullAxiomFeeSource(),
        axiom_config=producer_session._strict_axiom_config(),
        sidecar_factory=lambda _tick: None,
        ath_transport=object(),
        ath_endpoint_secret=object(),
        ledger=object(),
        guard_factory=object,
        authorization=object(),
        now_dt_fn=lambda: datetime(2026, 7, 17, 12, tzinfo=timezone.utc),
        now_iso_fn=lambda: NOW,
        now_seconds=lambda: Decimal(0),
        sleep_fn=sleep_fn,
        monotonic_fn=lambda: clock["mono"],
        bounds=producer_session.ProductionBounds(
            recheck_interval_seconds=1.0,
            max_candidate_age_seconds=3600,
            max_rechecks_per_candidate=100,
            max_total_ticks=3,
        ),
        run_cap1_candidates_fn=run_engine,
        ledger_line_count_fn=lambda: 0,
        security_decision_fn=security_decision_fn,
        on_cycle=on_cycle,
    )

    # The security gate blocked every tick and the engine never ran...
    assert security_calls["count"] == 3
    assert result["security_blocked_count"] == 3
    assert result["security_allowed_count"] == 0
    assert result["outcome"] == "ZERO_SEND"
    assert result["sends"] == 0
    assert result["send_records"] == []
    assert result["total_ledger_delta"] == 0        # NO ledger mutation
    assert result["ledger_consistent"] is True

    # ...yet the blocked candidate still captured its immutable baseline and
    # proved the 1.20x crossing from later fresh observations.
    assert entry.migration_baseline_status == BASELINE_CAPTURED
    assert entry.migration_market_cap_usd == "100"
    assert entry.status == WATCH_ACTIVE_DIP
    assert entry.is_dip_active()
    kinds = [event.get("event") for event in activation_events]
    assert "BASELINE_CAPTURED" in kinds
    assert "ACTIVATED" in kinds
    assert "ACTIVE_DIP_WATCH" in kinds

    # Compose-time enforcement is still fail-closed for this mint: without a
    # bound ALLOW decision the security proof gate returns a block reason.
    from PHX2.free_tier_producer.scam_policy import (
        SECURITY_DECISION_PROOF_MISSING,
        SecurityDecisionIndex,
    )
    assert SecurityDecisionIndex().proof_gate(MINT) == SECURITY_DECISION_PROOF_MISSING

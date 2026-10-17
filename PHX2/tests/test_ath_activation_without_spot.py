"""Offline PHX2-E2E-003 regression: ATH activation is independent of spot readiness."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from decimal import Decimal
import json

import pytest

from PHX2.dashboard.adapter import build_candidate_rows, load_producer
from PHX2.free_tier_producer.ath_state import (
    ATH_EVIDENCE_SCHEMA_VERSION,
    CentralAthStateStore,
    SOURCE_PAID_CURRENT,
    SOURCE_PAID_OHLCV,
    SOURCE_PUMPSWAP_EVENT,
)
from PHX2.free_tier_producer.compat.build30_watchlist import (
    WATCH_ACTIVATED_WAITING,
    WATCH_ACTIVE_DIP,
    Watchlist,
    activation_proof_is_durable,
    activation_proof_is_eligible,
    is_active_watch_state,
    is_schedulable_watch_state,
)
from PHX2.stage30.stage30_11_15_ping_dedupe_ledger import InMemoryPingDedupeLedger
from PHX2.paper_trading.pricing import normalize_record
from PHX2.tests import test_ath_activation_risk_regression as fixture


def _observe_missing(entry, central_ath, *, at=fixture.ACTED_AT, reserve=None):
    return entry.observe_market(
        current_market_cap_usd=None,
        current_price=None,
        current_supply=None,
        provider_timestamp_utc=None,
        observed_at_utc=at,
        observation_source="PAID_MARKET_PRIMARY",
        max_age_seconds=120,
        central_ath=central_ath,
        pumpswap_reserve=reserve,
    )


def test_exact_audit_probe_activates_without_spot_then_exact_41vh_tier1_is_actionable(
    tmp_path,
):
    entry = fixture._entry()
    crossing = fixture._central_evidence(fixture.ACTIVATING_HIGH)

    activated = _observe_missing(entry, crossing)
    proof = activated["activation"]
    assert activated["just_activated"] is True
    assert activated["eligible"] is False
    assert activated["reason"] == WATCH_ACTIVATED_WAITING
    assert entry.status == WATCH_ACTIVATED_WAITING
    assert proof["activation_proven"] is True
    assert proof["activation_latched"] is True
    assert proof["activation_waiting_for_fresh_market"] is True
    assert proof["activation_current_market_required_for_tier"] is True
    assert proof["activation_evidence_market_cap_usd"] == fixture.ACTIVATING_HIGH
    assert proof["activated_at_utc"] == fixture.ACTED_AT
    assert proof["activation_evidence_event_at_utc"] == fixture.HIGH_AT
    assert proof["activation_source_evidence_digest"] == crossing[
        "ath_evidence_digest"]
    assert proof["activation_observation_seal_digest"] == crossing[
        "ath_observation_seal_digest"]
    assert activation_proof_is_durable(proof)
    assert not activation_proof_is_eligible(proof)
    assert is_active_watch_state(entry.status)
    assert is_schedulable_watch_state(entry.status)
    counters = [event.get("activation_counter") for event in activated["events"]]
    assert "activation_proven_by_ohlcv_high" in counters
    assert "activation_proven_without_current_spot" in counters
    assert "activation_waiting_for_fresh_market" in counters

    latest = fixture._central_evidence(
        fixture.LATEST_ATH,
        event_at=fixture.LATEST_ATH_AT,
        ingested_at=fixture.LATEST_INGESTED_AT,
    )
    ledger = InMemoryPingDedupeLedger()
    guard = fixture._FakeGuard()
    tier1, security = fixture._run_fake_tier(
        entry=entry,
        current_mc=fixture.TIER1_MC,
        at=fixture.TIER1_AT,
        central_ath=latest,
        ledger=ledger,
        guard=guard,
        tmp_path=tmp_path,
    )
    assert tier1["outcome"] == "ONE_SEND_COMMITTED"
    assert tier1["per_candidate"][0]["compose_tier"] == "Tier 1"
    assert tier1["per_candidate"][0]["market_context"]["risk_assessment"][
        "risk_label"] == "RISK_MEDIUM"
    assert security.compose_allowed is True
    assert entry.status == WATCH_ACTIVE_DIP
    assert activation_proof_is_eligible(entry)
    assert len(ledger._state) == 1
    assert len(guard.calls) == 1

    tier2, _ = fixture._run_fake_tier(
        entry=entry,
        current_mc=fixture.TIER2_MC,
        at=fixture.TIER2_AT,
        central_ath=latest,
        ledger=ledger,
        guard=guard,
        tmp_path=tmp_path,
    )
    assert tier2["outcome"] == "ONE_SEND_COMMITTED"
    assert tier2["per_candidate"][0]["compose_tier"] == "Tier 2"
    assert len(ledger._state) == 2
    assert len(guard.calls) == 2


class _MissingSidecar:
    def __init__(self, central_ath):
        self.central_ath = dict(central_ath)

    def resolve(self, mint, **kwargs):
        return {
            "current_price": None,
            "current_market_cap_usd": None,
            "liquidity_usd": None,
            "market_context_fetched_at_utc": fixture.ACTED_AT,
            "provider_timestamp_utc": None,
            "all_present": False,
            "market_state": "MARKET_INCOMPLETE",
            "market_reason_code": "CURRENT_MARKET_MISSING",
            "basis": "MARKET_INCOMPLETE",
            "attempts": [],
            "central_ath": dict(self.central_ath),
            "pumpswap_reserve": {"reserve_trusted_for_routing": False},
        }


class _ForbiddenGuard:
    calls = 0

    def authorize_and_dispatch(self, *args, **kwargs):
        self.calls += 1
        raise AssertionError("activation-only observation reached delivery")


def test_missing_spot_activation_reaches_no_tier_compose_reservation_or_delivery():
    entry = fixture._entry()
    central = fixture._central_evidence(fixture.ACTIVATING_HIGH)
    guard = _ForbiddenGuard()
    ledger = InMemoryPingDedupeLedger()

    def activation_gate(candidate, context):
        return _observe_missing(entry, context["central_ath"])

    result = fixture.producer_session.sess.run_cap1_candidates(
        [entry.to_candidate()],
        sidecar=_MissingSidecar(central),
        ath_transport=None,
        ath_endpoint_secret=None,
        now_utc=datetime.fromisoformat(fixture.ACTED_AT.replace("Z", "+00:00")),
        now_seconds=lambda: Decimal(0),
        now_iso_fn=lambda: fixture.ACTED_AT,
        sleep_fn=lambda _seconds: None,
        ledger=ledger,
        guard=guard,
        authorization=object(),
        created_at_utc=fixture.ACTED_AT,
        activation_gate_fn=activation_gate,
    )
    record = result["per_candidate"][0]
    assert result["outcome"] == "ZERO_SEND"
    assert record["reason"] == "NO_SEND_ACTIVATED_WAITING_FOR_FRESH_MARKET"
    assert record.get("compose_decision") is None
    assert result["sent_attempt"] is None
    assert len(ledger._state) == 0
    assert guard.calls == 0


def test_waiting_and_crossing_digest_survive_restart_and_equal_reobservation(tmp_path):
    entry = fixture._entry()
    central = fixture._central_evidence(fixture.ACTIVATING_HIGH)
    first = _observe_missing(entry, central)
    crossing_digest = entry.activation_crossing_tick_digest
    proof_digest = entry.activation_proof_digest

    watchlist = Watchlist()
    watchlist._entries[fixture.MINT] = entry
    path = tmp_path / "watch_state.jsonl"
    watchlist.persist(path)
    restored_watchlist = Watchlist.load(path)
    restored = restored_watchlist.get(fixture.MINT)
    assert restored is not None
    assert restored.status == WATCH_ACTIVATED_WAITING
    assert restored.activation_crossing_tick_digest == crossing_digest
    assert restored.activation_proof_digest == proof_digest
    assert restored_watchlist.active_count() == 1
    assert restored_watchlist.terminal_history_count() == 0

    replay = _observe_missing(restored, central)
    assert replay["eligible"] is False
    assert replay["just_activated"] is False
    assert restored.activation_crossing_tick_digest == crossing_digest
    assert restored.activation_proof_digest == proof_digest
    assert not any(event.get("event") == "ACTIVATED" for event in replay["events"])
    assert first["activation"]["activation_proof_digest"] == proof_digest


def test_missing_or_stale_spot_never_clears_latched_activation():
    entry = fixture._entry()
    _observe_missing(entry, fixture._central_evidence(fixture.ACTIVATING_HIGH))
    original = entry.activation_proof_digest

    missing = _observe_missing(entry, None, at="2026-07-18T20:10:40Z")
    assert missing["reason"] == WATCH_ACTIVATED_WAITING
    stale = entry.observe_market(
        current_market_cap_usd=fixture.TIER1_MC,
        current_price=fixture._price_for_market_cap(fixture.TIER1_MC),
        current_supply="1000000000",
        provider_timestamp_utc="2026-07-18T20:10:00Z",
        observed_at_utc=fixture.TIER1_AT,
        observation_source="PAID_MARKET_PRIMARY",
        max_age_seconds=120,
        central_ath=None,
    )
    assert stale["eligible"] is False
    assert entry.activation_latched is True
    assert entry.activation_proven is True
    assert entry.activation_proof_digest == original


@pytest.mark.parametrize(("provider_at", "reason"), (
    (fixture.HIGH_AT, "ACTIVATION_LATER_MARKET_TICK_REQUIRED"),
    (fixture.ACTED_AT, "ACTIVATION_LATER_MARKET_TICK_REQUIRED"),
))
def test_spot_at_or_before_activation_ordering_boundary_is_not_a_later_dip(
    provider_at, reason,
):
    entry = fixture._entry()
    _observe_missing(entry, fixture._central_evidence(fixture.ACTIVATING_HIGH))
    result = fixture._observe(
        entry,
        market_cap=fixture.TIER1_MC,
        provider_at=provider_at,
        acted_at=fixture.ACTED_AT,
        central_ath=None,
    )
    assert result["eligible"] is False
    assert result["reason"] == reason
    assert entry.activation_latched is True


@pytest.mark.parametrize("mutation", (
    "wrong_candidate", "invalid_source_digest", "invalid_seal",
    "unsupported_schema", "infinity", "fresh_ingest_old_event",
))
def test_additional_central_activation_negatives_fail_closed(mutation):
    entry = fixture._entry()
    evidence = fixture._central_evidence(fixture.ACTIVATING_HIGH)
    at = fixture.ACTED_AT
    if mutation == "wrong_candidate":
        evidence["candidate_id"] = "different-candidate"
    elif mutation == "invalid_source_digest":
        evidence["ath_evidence_digest"] = "1" * 64
        evidence["ath_source_evidence_digest"] = "1" * 64
    elif mutation == "invalid_seal":
        evidence["ath_observation_seal_digest"] = "2" * 64
    elif mutation == "unsupported_schema":
        evidence["ath_evidence_version"] = "unsupported"
        evidence["ath_source_evidence_version"] = "unsupported"
    elif mutation == "infinity":
        evidence = fixture._central_evidence("Infinity")
    elif mutation == "fresh_ingest_old_event":
        at = "2026-07-18T20:12:30Z"
        evidence = fixture._central_evidence(
            fixture.ACTIVATING_HIGH,
            event_at="2026-07-18T20:09:00Z",
            ingested_at=at,
        )
    result = _observe_missing(entry, evidence, at=at)
    assert result["eligible"] is False
    assert result["just_activated"] is False
    assert entry.status != WATCH_ACTIVATED_WAITING
    assert entry.activation_latched is False


def test_reserve_source_requires_routing_trust_even_without_spot():
    central = fixture._central_evidence(
        fixture.ACTIVATING_HIGH, source=SOURCE_PUMPSWAP_EVENT)
    blocked = fixture._entry()
    assert not _observe_missing(
        blocked, central,
        reserve={"reserve_trusted_for_routing": False})["just_activated"]
    assert not blocked.activation_latched

    trusted = fixture._entry()
    accepted = _observe_missing(
        trusted, central,
        reserve={"reserve_trusted_for_routing": True})
    assert accepted["just_activated"]
    assert trusted.status == WATCH_ACTIVATED_WAITING
    assert trusted.activation_latched


def test_trusted_paid_current_central_evidence_activates_without_spot():
    entry = fixture._entry()
    evidence = fixture._central_evidence(
        fixture.ACTIVATING_HIGH, source=SOURCE_PAID_CURRENT)
    result = _observe_missing(entry, evidence)
    assert result["just_activated"] is True
    assert entry.status == WATCH_ACTIVATED_WAITING
    assert entry.activation_evidence_source == SOURCE_PAID_CURRENT
    assert any(
        event.get("activation_counter") == "activation_proven_by_current_price"
        for event in result["events"])


def test_equal_authoritative_reobservation_refreshes_only_the_ingestion_seal():
    store = CentralAthStateStore()
    assert store.observe_provider_current(
        mint=fixture.MINT,
        price_usd=fixture._price_for_market_cap(fixture.ACTIVATING_HIGH),
        market_cap_usd=fixture.ACTIVATING_HIGH,
        supply_at_observation="1000000000",
        observed_at=fixture.HIGH_AT,
        confirmed=True,
        ingested_at="2026-07-18T20:10:01Z",
    )
    first = store.snapshot(fixture.MINT)
    assert first is not None
    assert store.observe_provider_current(
        mint=fixture.MINT,
        price_usd=fixture._price_for_market_cap(fixture.ACTIVATING_HIGH),
        market_cap_usd=fixture.ACTIVATING_HIGH,
        supply_at_observation="1000000000",
        observed_at=fixture.HIGH_AT,
        confirmed=True,
        ingested_at=fixture.ACTED_AT,
    )
    second = store.snapshot(fixture.MINT)
    assert second is not None
    assert second["ath_market_cap"] == first["ath_market_cap"]
    assert second["ath_price"] == first["ath_price"]
    assert second["ath_timestamp"] == first["ath_timestamp"]
    assert second["ath_evidence_digest"] == first["ath_evidence_digest"]
    assert second["ath_observation_seal_digest"] != first[
        "ath_observation_seal_digest"]
    assert second["ath_ingested_at_utc"] == fixture.ACTED_AT
    assert second["ath_equal_evidence_reobserved_count"] == 1
    assert store.stats()["ath_equal_evidence_reobserved"] == 1


@pytest.mark.parametrize(("source", "event_at"), (
    (SOURCE_PAID_CURRENT, "2026-07-18T20:10:30Z"),
    (SOURCE_PAID_OHLCV, fixture.HIGH_AT),
))
def test_equal_value_with_different_source_identity_is_not_a_seal_refresh(
    source, event_at,
):
    store = CentralAthStateStore()
    store.observe_provider_current(
        mint=fixture.MINT,
        price_usd=fixture._price_for_market_cap(fixture.ACTIVATING_HIGH),
        market_cap_usd=fixture.ACTIVATING_HIGH,
        supply_at_observation="1000000000",
        observed_at=fixture.HIGH_AT,
        confirmed=True,
        ingested_at="2026-07-18T20:10:01Z",
    )
    before = store.snapshot(fixture.MINT)
    assert before is not None
    if source == SOURCE_PAID_CURRENT:
        changed = store.observe_provider_current(
            mint=fixture.MINT,
            price_usd=fixture._price_for_market_cap(fixture.ACTIVATING_HIGH),
            market_cap_usd=fixture.ACTIVATING_HIGH,
            supply_at_observation="1000000000",
            observed_at=event_at,
            confirmed=True,
            ingested_at=fixture.ACTED_AT,
        )
    else:
        # A different source is represented directly as a valid central proof;
        # source identity must differ even when value and event time are equal.
        other = fixture._central_evidence(
            fixture.ACTIVATING_HIGH, source=source, event_at=event_at)
        changed = other["ath_evidence_digest"] == before["ath_evidence_digest"]
    after = store.snapshot(fixture.MINT)
    assert after is not None
    assert changed is False
    assert after["ath_equal_evidence_reobserved_count"] == 0
    assert after["ath_observation_seal_digest"] == before[
        "ath_observation_seal_digest"]


def test_waiting_candidate_consumes_active_capacity_and_never_enters_terminal_history(
    tmp_path,
):
    watchlist = Watchlist(
        max_size=1, terminal_history_path=tmp_path / "terminal.jsonl")
    entry = watchlist.seed(
        fixture._entry().to_candidate(), seeded_at_utc=fixture.BASELINE_AT)
    assert entry is not None
    # The candidate copied through to_candidate carries its captured baseline.
    # Seed a fresh exact fixture if an older projection omitted baseline scalars.
    if entry.migration_baseline_status != "CAPTURED":
        watchlist = Watchlist(
            max_size=1, terminal_history_path=tmp_path / "terminal.jsonl")
        entry = watchlist.seed({
            "token_mint": fixture.MINT,
            "candidate_id": "capacity-waiting",
            "migration_time_utc": fixture.BASELINE_AT,
            "source_ref": "synthetic-proof",
            "migration_market_cap_usd": fixture.BASELINE,
            "migration_market_cap_source": "GRPC_EVENT",
            "migration_market_cap_observed_at_utc": fixture.BASELINE_AT,
            "migration_market_cap_price": fixture._price_for_market_cap(
                fixture.BASELINE),
            "migration_supply_at_observation": "1000000000",
        }, seeded_at_utc=fixture.BASELINE_AT)
    assert entry is not None
    _observe_missing(entry, fixture._central_evidence(fixture.ACTIVATING_HIGH))
    assert watchlist.active_count() == 1
    assert watchlist.summary()["activated_waiting_for_fresh_market"] == 1
    assert watchlist.terminal_history_count() == 0
    rejected = watchlist.seed({
        "token_mint": fixture.OTHER_MINT,
        "candidate_id": "candidate-129-equivalent",
    }, seeded_at_utc=fixture.ACTED_AT)
    assert rejected is None
    assert watchlist.summary()["capacity_rejections"] == 1


def test_dashboard_paper_and_watch_summary_agree_on_activated_waiting_state(tmp_path):
    entry = fixture._entry()
    central = fixture._central_evidence(fixture.ACTIVATING_HIGH)
    _observe_missing(entry, central)
    producer_dir = tmp_path / "producer"
    producer_dir.mkdir()
    (producer_dir / "watch_state.jsonl").write_text(
        json.dumps(asdict(entry), sort_keys=True) + "\n", encoding="utf-8")
    (producer_dir / "ath_state.json").write_text(json.dumps({
        "schema_version": "phx2_central_ath_v1",
        "artifact_kind": "CENTRAL_ATH_PUBLIC_STATE",
        "updated_at": fixture.ACTED_AT,
        "mints": {fixture.MINT: central},
    }, sort_keys=True) + "\n", encoding="utf-8")
    now = datetime.fromisoformat(fixture.ACTED_AT.replace("Z", "+00:00"))
    row = build_candidate_rows(load_producer(producer_dir, now), now)[0]
    assert row["stage"] == WATCH_ACTIVATED_WAITING
    assert row["activationState"] == WATCH_ACTIVATED_WAITING
    assert row["activationEligible"] is False
    assert row["activationProven"] is True
    assert row["activationLatched"] is True
    assert row["activationWaitingForFreshMarket"] is True
    assert row["activationCurrentMarketRequiredForTier"] is True
    assert row["activationObservationSealDigest"] == central[
        "ath_observation_seal_digest"]

    paper = normalize_record({
        "kind": "BUILD30_CANDIDATE_RECHECK",
        "token_mint": fixture.MINT,
        "candidate_id": entry.candidate_id,
        "status": entry.status,
        "observed_at_utc": fixture.ACTED_AT,
        "activation": entry.activation_snapshot(),
        "central_ath": central,
    })
    assert paper is not None
    assert paper.extra["activation"]["activation_proven"] is True
    assert paper.extra["activation"]["activation_waiting_for_fresh_market"] is True
    assert paper.extra["activation"]["activation_state"] == WATCH_ACTIVATED_WAITING

    summary = Watchlist()
    summary._entries[fixture.MINT] = entry
    assert summary.summary()["activated_waiting_for_fresh_market"] == 1
    assert summary.summary()["pending_1_20x"] == 0

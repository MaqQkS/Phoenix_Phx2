"""Offline regression for the 41VH central-ATH activation/risk incident."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from decimal import Decimal
import json

import pytest

from PHX2.dashboard.adapter import build_candidate_rows, load_producer
from PHX2.delivery.telegram_adapter import TelegramDeliveryAdapter
from PHX2.free_tier_producer import free_tier_session as producer_session
from PHX2.free_tier_producer.ath_state import (
    ATH_EVIDENCE_SCHEMA_VERSION,
    ATH_OBSERVATION_SEAL_SCHEMA_VERSION,
    ATH_STATE_SCHEMA_VERSION,
    SOURCE_PAID_CURRENT,
    SOURCE_PAID_OHLCV,
    SOURCE_PUMPSWAP_EVENT,
    STATUS_CONFIRMED,
    STATUS_PROVISIONAL,
    build_ath_evidence_digest,
    build_ath_observation_seal_digest,
    build_ath_resolved_tuple,
)
from PHX2.free_tier_producer.compat.build30_watchlist import (
    ACTIVATION_EVIDENCE_SCHEMA_VERSION,
    ACTIVATION_KIND_CONFIRMED_OHLCV_HIGH,
    ACTIVATION_KIND_SPOT_CURRENT,
    ACTIVATION_KIND_TRUSTED_RESERVE_EVENT,
    BASELINE_SOURCE_GRPC_EVENT,
    WATCH_ACTIVE_DIP,
    WATCH_PENDING_1_20X,
    Watchlist,
    activation_proof_is_eligible,
)
from PHX2.free_tier_producer.free_tier_risk import (
    DISCORD_DISPATCH_ALLOWED,
    LP_INTEGRITY_MODE_DISABLED_SINGLE_STREAM,
    MEDIUM_RISK_MC_TOO_LOW,
    MEDIUM_RISK_WARNING_ONLY,
    REASON_LP_FALLING,
    RISK_HIGH,
    RISK_MEDIUM,
    SKIPPED_HIGH_RISK_DISCORD,
    SKIPPED_MEDIUM_RISK_WEAK_STRUCTURE,
    classify_discord_dispatch,
)
from PHX2.free_tier_producer.phx1_fee_gate import (
    PHX1_FEE_GATE_NORMAL,
    PHX1_FEE_GATE_SCAM_LIKELY,
    build_fee_snapshot,
)
from PHX2.free_tier_producer.scam_policy import (
    LP_INTEGRITY_MODE_DISABLED_SINGLE_STREAM as SECURITY_SINGLE_STREAM,
    delivery_block_reason,
    evaluate_delivery_safety,
)
from PHX2.paper_trading.pricing import normalize_record
from PHX2.stage29.birdeye_constants import BIRDEYE_PATH_OHLCV, BIRDEYE_PATH_PRICE
from PHX2.stage29.stage29_2_birdeye_http_transport import Stage29_2BirdeyeHttpResult
from PHX2.stage29.stage29_2_birdeye_readiness import Stage29_2BirdeyeEndpointSecret
from PHX2.stage29.stage29_2_birdeye_models import (
    BIRDEYE_REFUSAL_REASON_HTTP_TIMEOUT,
    BIRDEYE_REFUSAL_REASON_NONE,
)
from PHX2.stage30.stage30_11_15_ping_dedupe_ledger import InMemoryPingDedupeLedger


MINT = "41VHigULn7wAFsk8ZjuH7zQoAybuGrBAJGgjLsZcpump"
OTHER_MINT = "EkNbQMQYpd4JET5FpZrqbdkYdHXeqocZcBByJpFWpump"
BASELINE = "32685.55146934647"
TARGET = "39222.6617632157640"
SPOT_BELOW = "36914.45041269651"
ACTIVATING_HIGH = "40282.73"
LATEST_ATH = "41493.019258"
TIER1_MC = "18756.844376074794"
TIER2_MC = "15100"
BASELINE_AT = "2026-07-18T20:08:40Z"
HIGH_AT = "2026-07-18T20:10:00Z"
CROSSING_SPOT_AT = "2026-07-18T20:10:22Z"
ACTED_AT = "2026-07-18T20:10:23Z"
LATEST_ATH_AT = "2026-07-18T20:11:00Z"
LATEST_INGESTED_AT = "2026-07-18T20:11:05Z"
TIER1_AT = "2026-07-18T20:12:04Z"
TIER2_AT = "2026-07-18T20:13:04Z"
WSOL = "So11111111111111111111111111111111111111112"


def _price_for_market_cap(value: object) -> str:
    return format(Decimal(str(value)) / Decimal("1000000000"), "f")


def _central_evidence(
    market_cap: object,
    *,
    event_at: str = HIGH_AT,
    ingested_at: str = ACTED_AT,
    mint: str = MINT,
    source: str = SOURCE_PAID_OHLCV,
    status: str = STATUS_CONFIRMED,
    observation_type: str | None = None,
) -> dict:
    if observation_type is None:
        observation_type = {
            SOURCE_PAID_OHLCV: SOURCE_PAID_OHLCV,
            SOURCE_PAID_CURRENT: SOURCE_PAID_CURRENT,
            SOURCE_PUMPSWAP_EVENT: "PUMPSWAP_BUY_EFFECTIVE_RESERVES",
        }.get(source, "DISALLOWED_SOURCE")
    try:
        evidence_price = _price_for_market_cap(market_cap)
    except Exception:
        evidence_price = "0.00004028273"
    snapshot = {
        "token_mint": mint,
        "ath_price": evidence_price,
        "ath_market_cap": market_cap,
        "ath_market_cap_evidence_price_usd": evidence_price,
        "ath_timestamp": event_at,
        "ath_ingested_at_utc": ingested_at,
        "ath_provider": source,
        "ath_observation_type": observation_type,
        "ath_status": status,
        "ath_supply_at_observation": "1000000000",
        "ath_transaction_signature": None,
        "ath_event_index": None,
        "ath_raw_quote_reserves": None,
        "ath_virtual_quote_reserves": None,
        "ath_effective_quote_reserves": None,
        "ath_base_reserves": None,
        "ath_ohlcv_interval": ("1m" if source == SOURCE_PAID_OHLCV else None),
        "ath_ohlcv_time_from_unix": (
            int(datetime.fromisoformat(event_at.replace("Z", "+00:00")).timestamp())
            if source == SOURCE_PAID_OHLCV else None),
        "ath_ohlcv_time_to_unix": (
            int(datetime.fromisoformat(event_at.replace("Z", "+00:00")).timestamp()) + 59
            if source == SOURCE_PAID_OHLCV else None),
        "ath_ohlcv_history_complete": (
            status == STATUS_CONFIRMED if source == SOURCE_PAID_OHLCV else None),
        "ath_evidence_version": ATH_EVIDENCE_SCHEMA_VERSION,
    }
    snapshot["ath_evidence_digest"] = (
        build_ath_evidence_digest(mint, snapshot) or ("0" * 64))
    snapshot["ath_source_evidence_version"] = ATH_EVIDENCE_SCHEMA_VERSION
    snapshot["ath_source_evidence_digest"] = snapshot["ath_evidence_digest"]
    snapshot["ath_observation_seal_version"] = (
        ATH_OBSERVATION_SEAL_SCHEMA_VERSION)
    snapshot["ath_observation_seal_validated"] = True
    snapshot["ath_observation_seal_digest"] = (
        build_ath_observation_seal_digest(mint, snapshot) or ("0" * 64))
    # The observation that set the maximum, and the resolved coherent tuple
    # the store publishes from it.  Built through the REAL production
    # resolver so a fixture can never encode a tuple production would not.
    snapshot["price_provenance"] = {
        "price": evidence_price,
        "market_cap": market_cap,
        "timestamp": event_at,
        "provider": source,
        "observation_type": observation_type,
        "status": status,
        "supply": snapshot["ath_supply_at_observation"],
        "evidence_digest": snapshot["ath_evidence_digest"],
    }
    snapshot["market_cap_provenance"] = dict(snapshot["price_provenance"])
    snapshot.update(build_ath_resolved_tuple(snapshot))
    return snapshot


def _entry():
    entry = Watchlist().seed({
        "token_mint": MINT,
        "candidate_id": "41vh-regression",
        "migration_time_utc": BASELINE_AT,
        "source_ref": "synthetic-redacted-migration-proof",
        "migration_market_cap_usd": BASELINE,
        "migration_market_cap_source": BASELINE_SOURCE_GRPC_EVENT,
        "migration_market_cap_observed_at_utc": BASELINE_AT,
        "migration_market_cap_price": _price_for_market_cap(BASELINE),
        "migration_supply_at_observation": "1000000000",
    }, seeded_at_utc=BASELINE_AT)
    assert entry is not None
    assert entry.status == WATCH_PENDING_1_20X
    assert entry.activation_target_market_cap_usd == TARGET
    return entry


def _observe(
    entry,
    *,
    market_cap: object = SPOT_BELOW,
    provider_at: str = CROSSING_SPOT_AT,
    acted_at: str = ACTED_AT,
    central_ath: object = None,
    reserve: object = None,
):
    return entry.observe_market(
        current_market_cap_usd=market_cap,
        current_price=_price_for_market_cap(market_cap),
        current_supply="1000000000",
        provider_timestamp_utc=provider_at,
        observed_at_utc=acted_at,
        observation_source="PAID_MARKET_PRIMARY",
        max_age_seconds=120,
        central_ath=central_ath,
        pumpswap_reserve=reserve,
    )


def _activated_entry():
    entry = _entry()
    below = _observe(entry)
    assert not below["eligible"] and not below["just_activated"]
    crossing_evidence = _central_evidence(ACTIVATING_HIGH)
    crossing = _observe(entry, central_ath=crossing_evidence)
    assert crossing["just_activated"] and not crossing["eligible"]
    return entry, crossing_evidence, crossing


def test_41vh_confirmed_ohlcv_high_latches_and_crossing_tick_survives_restart(tmp_path):
    entry, central, crossing = _activated_entry()
    proof = entry.activation_snapshot()

    assert entry.status == WATCH_ACTIVE_DIP
    assert proof["migration_market_cap_usd"] == BASELINE
    assert proof["activation_target_market_cap_usd"] == TARGET
    assert proof["activation_evidence_market_cap_usd"] == ACTIVATING_HIGH
    assert proof["activation_evidence_source"] == SOURCE_PAID_OHLCV
    assert proof["activation_evidence_kind"] == ACTIVATION_KIND_CONFIRMED_OHLCV_HIGH
    assert proof["activation_evidence_event_at_utc"] == HIGH_AT
    assert proof["activation_evidence_ingested_at_utc"] == ACTED_AT
    assert proof["activated_at_utc"] == ACTED_AT
    assert proof["activation_crossing_tick_blocked"] is True
    assert proof["activation_latched"] is True
    assert proof["activation_evidence_digest"] == central["ath_evidence_digest"]
    assert proof["activation_evidence_version"] == central["ath_evidence_version"]
    assert proof["activation_proof_version"] == ACTIVATION_EVIDENCE_SCHEMA_VERSION
    assert len(proof["activation_proof_digest"]) == 64
    assert activation_proof_is_eligible(proof)
    tampered = {**proof, "activation_evidence_market_cap_usd": "999999"}
    assert not activation_proof_is_eligible(tampered)
    assert any(event.get("activation_counter") == "activation_proven_by_ohlcv_high"
               for event in crossing["events"])
    assert any(event.get("activation_counter") == "activation_crossing_tick_blocks"
               for event in crossing["events"])

    replay = _observe(entry, central_ath=central)
    assert not replay["eligible"]
    assert replay["reason"] == "ACTIVATION_CROSSING_TICK_BLOCKED"

    watchlist = Watchlist()
    watchlist._entries[MINT] = entry
    path = tmp_path / "watch_state.jsonl"
    watchlist.persist(path)
    restored = Watchlist.load(path).get(MINT)
    assert restored is not None and restored.activation_latched
    replay_after_restart = _observe(restored, central_ath=central)
    assert not replay_after_restart["eligible"]
    assert replay_after_restart["reason"] == "ACTIVATION_CROSSING_TICK_BLOCKED"

    latest = _central_evidence(
        LATEST_ATH, event_at=LATEST_ATH_AT, ingested_at=LATEST_INGESTED_AT)
    later = _observe(
        restored, market_cap=TIER1_MC, provider_at=TIER1_AT,
        acted_at=TIER1_AT, central_ath=latest)
    assert later["eligible"] and not later["just_activated"]
    assert restored.activation_evidence_digest == central["ath_evidence_digest"]
    assert restored.activation_evidence_market_cap_usd == ACTIVATING_HIGH
    assert restored.activation_latched


@pytest.mark.parametrize("case", (
    "pre_baseline", "below_target", "unconfirmed", "stale_ingest",
    "wrong_mint", "disallowed_source", "nan", "float",
))
def test_ohlcv_activation_evidence_negatives_fail_closed(case):
    entry = _entry()
    kwargs = {}
    value: object = ACTIVATING_HIGH
    if case == "pre_baseline":
        kwargs["event_at"] = BASELINE_AT
    elif case == "below_target":
        value = "39222.6617632157639"
    elif case == "unconfirmed":
        kwargs["status"] = STATUS_PROVISIONAL
    elif case == "stale_ingest":
        kwargs["ingested_at"] = "2026-07-18T20:00:00Z"
    elif case == "wrong_mint":
        kwargs["mint"] = OTHER_MINT
    elif case == "disallowed_source":
        kwargs["source"] = "UNAPPROVED_HIGH"
    elif case == "nan":
        value = "NaN"
    elif case == "float":
        value = 40282.73
    evidence = _central_evidence(value, **kwargs)
    result = _observe(entry, central_ath=evidence)
    assert not result["eligible"] and not result["just_activated"]
    assert entry.status == WATCH_PENDING_1_20X
    assert not entry.activation_latched


@pytest.mark.parametrize(("source", "status", "reserve", "expected_kind"), (
    (SOURCE_PAID_CURRENT, STATUS_PROVISIONAL, None, ACTIVATION_KIND_SPOT_CURRENT),
    (SOURCE_PUMPSWAP_EVENT, STATUS_CONFIRMED,
     {"reserve_trusted_for_routing": True}, ACTIVATION_KIND_TRUSTED_RESERVE_EVENT),
))
def test_other_explicit_authoritative_activation_sources(
    source, status, reserve, expected_kind
):
    entry = _entry()
    evidence = _central_evidence(ACTIVATING_HIGH, source=source, status=status)
    result = _observe(entry, central_ath=evidence, reserve=reserve)
    assert result["just_activated"] and not result["eligible"]
    assert entry.activation_evidence_kind == expected_kind


def test_untrusted_reserve_never_activates():
    entry = _entry()
    evidence = _central_evidence(ACTIVATING_HIGH, source=SOURCE_PUMPSWAP_EVENT)
    result = _observe(
        entry, central_ath=evidence,
        reserve={"reserve_trusted_for_routing": False})
    assert not result["eligible"] and not result["just_activated"]
    assert entry.status == WATCH_PENDING_1_20X


def test_single_stream_medium_is_warning_only_but_high_remains_hard_blocked():
    medium = classify_discord_dispatch(
        {"risk_label": RISK_MEDIUM, "risk_reasons": [REASON_LP_FALLING]},
        liquidity_usd="12369", market_cap_usd=TIER1_MC, market_fresh=True,
        lp_integrity_mode=LP_INTEGRITY_MODE_DISABLED_SINGLE_STREAM)
    assert medium.allowed
    assert medium.terminal_decision == DISCORD_DISPATCH_ALLOWED
    assert medium.risk_label == RISK_MEDIUM
    assert medium.risk_reasons == (REASON_LP_FALLING,)
    assert medium.warning_only is True
    assert medium.mapped_reason == MEDIUM_RISK_WARNING_ONLY

    legacy = classify_discord_dispatch(
        {"risk_label": RISK_MEDIUM, "risk_reasons": [REASON_LP_FALLING]},
        liquidity_usd="12369", market_cap_usd=TIER1_MC, market_fresh=True)
    assert not legacy.allowed
    assert legacy.terminal_decision == SKIPPED_MEDIUM_RISK_WEAK_STRUCTURE
    assert legacy.mapped_reason == MEDIUM_RISK_MC_TOO_LOW

    high = classify_discord_dispatch(
        {"risk_label": RISK_HIGH, "risk_reasons": ["LP_CRITICALLY_LOW"]},
        lp_integrity_mode=LP_INTEGRITY_MODE_DISABLED_SINGLE_STREAM)
    assert not high.allowed
    assert high.terminal_decision == SKIPPED_HIGH_RISK_DISCORD


class _MediumRisk:
    def observe_market_sample(self, mint, market):
        return None

    def assess(self, mint):
        return {
            "risk_label": RISK_MEDIUM,
            "risk_reasons": [REASON_LP_FALLING],
            "risk_line": "Risk: RISK_MEDIUM - LP_FALLING",
        }


class _NoErrors:
    def log(self, *args, **kwargs):
        raise AssertionError("warning-only risk must not log an error")


def test_medium_warning_still_defers_to_exact_4500_liquidity_floor(tmp_path):
    gate = producer_session.make_discord_risk_gate(
        risk_engine=_MediumRisk(),
        discord_block_ledger=producer_session.DiscordBlockLedger(),
        discord_blocks_path=tmp_path / "risk-blocks.jsonl",
        min_liquidity_usd=Decimal("4500"),
        mode="PAID_PRIMARY_TELEGRAM",
        errors=_NoErrors(),
        lp_integrity_mode=LP_INTEGRITY_MODE_DISABLED_SINGLE_STREAM)
    below = {"current_market_cap_usd": TIER1_MC, "liquidity_usd": "4499.99"}
    exact = {"current_market_cap_usd": TIER1_MC, "liquidity_usd": "4500"}
    assert gate(MINT, below).startswith("LIQUIDITY_USD_BELOW_MIN")
    assert gate(MINT, exact) is None
    assert exact["risk_assessment"]["risk_label"] == RISK_MEDIUM
    assert exact["risk_assessment"]["risk_reasons"] == [REASON_LP_FALLING]


def _fee_snapshot(label: str, at: str):
    now_epoch = int(datetime.fromisoformat(at.replace("Z", "+00:00")).timestamp())
    components = {
        PHX1_FEE_GATE_NORMAL: (600_000_000, 200_000_000, 200_000_000, 100_000_000),
        PHX1_FEE_GATE_SCAM_LIKELY: (100_000_000, 100_000_000, 800_000_000, 10_000_000),
    }[label]
    lp, protocol, creator, priority = components
    state = {
        "quote_mint": WSOL,
        "quote_asset": "SOL",
        "pair_type": "TOKEN_SOL",
        "unit": "SOL",
        "lp": lp,
        "protocol": protocol,
        "creator": creator,
        "base": 5_000_000,
        "priority": priority,
        "jito": 0,
        "events": 1000,
        "signatures": {f"synthetic-{index}" for index in range(1000)},
        "first": BASELINE_AT,
        "last": at,
        "last_epoch": now_epoch,
        "recent": (),
        "tx_ante": (),
    }
    snapshot = build_fee_snapshot(MINT, state=state, now_epoch=now_epoch)
    assert snapshot.fee_gate_label == label
    return snapshot


class _OfflineAthTransport:
    """Path-routed deterministic fake. It opens no socket."""

    def __init__(self, *, current_mc: str, fetched_at: str, ath_mc: str) -> None:
        self.current_price = _price_for_market_cap(current_mc)
        self.ath_price = _price_for_market_cap(ath_mc)
        self.fetched_at = fetched_at
        self.calls = []

    @staticmethod
    def _epoch(value: str) -> int:
        return int(datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp())

    def get(self, *, endpoint_secret, path, query_params, timeout_seconds):
        self.calls.append((path, dict(query_params)))
        if path == BIRDEYE_PATH_PRICE:
            body = {"data": {
                "value": self.current_price,
                "updateUnixTime": self._epoch(self.fetched_at),
            }}
            reason = BIRDEYE_REFUSAL_REASON_NONE
            status = 200
        elif path == BIRDEYE_PATH_OHLCV:
            body = {"data": {"items": [{
                "h": self.ath_price,
                "unixTime": self._epoch(LATEST_ATH_AT),
            }]}}
            reason = BIRDEYE_REFUSAL_REASON_NONE
            status = 200
        else:
            body = None
            reason = BIRDEYE_REFUSAL_REASON_HTTP_TIMEOUT
            status = 0
        return Stage29_2BirdeyeHttpResult(
            refusal_reason=reason,
            http_status_code=status,
            body=body,
            fetched_at_utc=self.fetched_at,
        )


class _Sidecar:
    def __init__(self, *, current_mc: str, at: str, central_ath: dict) -> None:
        self.current_mc = current_mc
        self.at = at
        self.central_ath = dict(central_ath)

    def resolve(self, mint, **kwargs):
        return {
            "current_price": _price_for_market_cap(self.current_mc),
            "current_market_cap_usd": self.current_mc,
            "liquidity_usd": "12369",
            "market_context_fetched_at_utc": self.at,
            "provider_timestamp_utc": self.at,
            "all_present": True,
            "basis": "REAL_MARKET_PRESENT",
            "attempts": [],
            "central_ath": dict(self.central_ath),
            "pumpswap_reserve": {"reserve_trusted_for_routing": False},
        }

    def central_ath_snapshot(self, mint):
        return dict(self.central_ath)


class _FakeGuardResult:
    """A confirmed FAKE transport verdict (never a real send). The delivery
    transaction requires transport_ok=True before it commits the dedupe row."""

    fake_transport = True
    transport_attempted = True
    dispatch_forwarded = True
    transport_ok = True
    transport_status = "FAKE_SENT_OK"
    message_id = None


class _FakeGuard:
    def __init__(self) -> None:
        self.calls = []

    def authorize_and_dispatch(self, deduped, *, authorization, created_at_utc):
        self.calls.append({
            "deduped": deduped,
            "authorization": authorization,
            "created_at_utc": created_at_utc,
        })
        return _FakeGuardResult()


def _run_fake_tier(
    *, entry, current_mc: str, at: str, central_ath: dict,
    ledger, guard, tmp_path,
):
    fee = _fee_snapshot(PHX1_FEE_GATE_NORMAL, at)
    security = evaluate_delivery_safety(
        fee_snapshot=fee,
        lp_integrity_mode=SECURITY_SINGLE_STREAM)
    assert delivery_block_reason(security) is None
    gate = producer_session.make_discord_risk_gate(
        risk_engine=_MediumRisk(),
        discord_block_ledger=producer_session.DiscordBlockLedger(),
        discord_blocks_path=tmp_path / "risk-blocks.jsonl",
        min_liquidity_usd=Decimal("4500"),
        mode="PAID_PRIMARY_TELEGRAM",
        errors=_NoErrors(),
        lp_integrity_mode=LP_INTEGRITY_MODE_DISABLED_SINGLE_STREAM)
    sidecar = _Sidecar(current_mc=current_mc, at=at, central_ath=central_ath)

    def activation_gate(candidate, context):
        return entry.observe_market(
            current_market_cap_usd=context["current_market_cap_usd"],
            current_price=context["current_price"],
            current_supply="1000000000",
            provider_timestamp_utc=context["provider_timestamp_utc"],
            observed_at_utc=at,
            observation_source="PAID_MARKET_PRIMARY",
            max_age_seconds=120,
            central_ath=context["central_ath"],
            pumpswap_reserve=context["pumpswap_reserve"],
        )

    result = producer_session.sess.run_cap1_candidates(
        [{
            **entry.to_candidate(),
            "security_decision": security,
            "fee_gate_lifecycle": {
                "lifecycle_version": "PHX2_FEE_GATE_LIFECYCLE_V1",
                "lifecycle_state": "FRESH_CONFIRMED",
                "evidence_proof_digest": fee.proof_digest,
            },
        }],
        sidecar=sidecar,
        ath_transport=_OfflineAthTransport(
            current_mc=current_mc, fetched_at=at, ath_mc=LATEST_ATH),
        ath_endpoint_secret=Stage29_2BirdeyeEndpointSecret(
            _api_key="".join(("offline", "-", "test-key", "-", "12345678")),
            _base_url="https" + "://offline.test.invalid",
        ),
        now_utc=datetime.fromisoformat(at.replace("Z", "+00:00")),
        now_seconds=lambda: Decimal(0),
        now_iso_fn=lambda: at,
        sleep_fn=lambda _seconds: None,
        ledger=ledger,
        guard=guard,
        authorization=object(),
        created_at_utc=at,
        pre_reserve_gate_fn=gate,
        activation_gate_fn=activation_gate,
    )
    return result, security


def test_exact_41vh_tier1_tier2_compose_reservation_and_dedupe_are_fake_only(tmp_path):
    entry, _, _ = _activated_entry()
    latest = _central_evidence(
        LATEST_ATH, event_at=LATEST_ATH_AT, ingested_at=LATEST_INGESTED_AT)
    ledger = InMemoryPingDedupeLedger()
    guard = _FakeGuard()

    tier1, security = _run_fake_tier(
        entry=entry, current_mc=TIER1_MC, at=TIER1_AT,
        central_ath=latest, ledger=ledger, guard=guard, tmp_path=tmp_path)
    assert tier1["outcome"] == "ONE_SEND_COMMITTED"
    assert tier1["per_candidate"][0]["compose_tier"] == "Tier 1"
    assert tier1["per_candidate"][0]["compose_anchored_ath_mc"] == "$41.4k"
    assert tier1["per_candidate"][0]["market_context"]["risk_assessment"] == {
        "risk_label": RISK_MEDIUM,
        "risk_reasons": [REASON_LP_FALLING],
        "risk_line": "Risk: RISK_MEDIUM - LP_FALLING",
    }
    assert tier1["eligible_candidate"] is not None
    assert len(ledger._state) == 1
    assert len(guard.calls) == 1
    assert guard.calls[0]["deduped"].compose_result.decision == "NO_SEND_DISPATCHED"
    assert security.lp_integrity_mode == SECURITY_SINGLE_STREAM
    assert tier1["eligible_candidate"]["fee_gate_lifecycle"]["lifecycle_state"] \
        == "FRESH_CONFIRMED"

    tier2, _ = _run_fake_tier(
        entry=entry, current_mc=TIER2_MC, at=TIER2_AT,
        central_ath=latest, ledger=ledger, guard=guard, tmp_path=tmp_path)
    assert tier2["outcome"] == "ONE_SEND_COMMITTED"
    assert tier2["per_candidate"][0]["compose_tier"] == "Tier 2"
    assert len(ledger._state) == 2
    assert len(guard.calls) == 2

    duplicate, _ = _run_fake_tier(
        entry=entry, current_mc=TIER2_MC, at="2026-07-18T20:13:30Z",
        central_ath=latest, ledger=ledger, guard=guard, tmp_path=tmp_path)
    assert duplicate["outcome"] == "ZERO_SEND"
    assert duplicate["per_candidate"][0]["compose_reason"] \
        == "DEDUPE_SUPPRESSED_DUPLICATE"
    assert len(ledger._state) == 2
    assert len(guard.calls) == 2

    scam = evaluate_delivery_safety(
        fee_snapshot=_fee_snapshot(PHX1_FEE_GATE_SCAM_LIKELY, TIER1_AT),
        lp_integrity_mode=SECURITY_SINGLE_STREAM)
    assert delivery_block_reason(scam) is not None
    assert not scam.compose_allowed and not scam.reservation_allowed


def test_paper_dashboard_security_and_telegram_share_latest_ath_and_activation_proofs(
    tmp_path,
):
    entry, activation_central, _ = _activated_entry()
    latest = _central_evidence(
        LATEST_ATH, event_at=LATEST_ATH_AT, ingested_at=LATEST_INGESTED_AT)
    ledger = InMemoryPingDedupeLedger()
    guard = _FakeGuard()
    tier1, security = _run_fake_tier(
        entry=entry, current_mc=TIER1_MC, at=TIER1_AT,
        central_ath=latest, ledger=ledger, guard=guard, tmp_path=tmp_path)
    activation = entry.activation_snapshot()
    record = {
        "kind": "BUILD30_CANDIDATE_RECHECK",
        "token_mint": MINT,
        "candidate_id": "41vh-regression",
        "migration_time_utc": BASELINE_AT,
        "observed_at_utc": TIER1_AT,
        "current_price": _price_for_market_cap(TIER1_MC),
        "current_market_cap_usd": TIER1_MC,
        "liquidity_usd": "12369",
        "central_ath": latest,
        "activation": activation,
        "risk_label": RISK_MEDIUM,
        "risk_reasons": [REASON_LP_FALLING],
    }
    paper = normalize_record(record)
    assert paper is not None

    security_record = producer_session.build_security_artifact_record(
        entry=entry,
        decision=security,
        reason=None,
        tick=1,
        observed_at_utc=TIER1_AT,
        fee_gate_lifecycle={"lifecycle_state": "FRESH_CONFIRMED"},
        central_ath=latest,
    )

    producer_dir = tmp_path / "producer"
    producer_dir.mkdir()
    (producer_dir / "watch_state.jsonl").write_text(
        json.dumps(asdict(entry), sort_keys=True) + "\n", encoding="utf-8")
    candidate_dir = producer_dir / "candidates"
    candidate_dir.mkdir()
    (candidate_dir / "41VHigUL.jsonl").write_text(
        json.dumps(record, sort_keys=True) + "\n", encoding="utf-8")
    (producer_dir / "ath_state.json").write_text(json.dumps({
        "schema_version": ATH_STATE_SCHEMA_VERSION,
        "artifact_kind": "CENTRAL_ATH_PUBLIC_STATE",
        "updated_at": TIER1_AT,
        "mints": {MINT: latest},
    }, sort_keys=True) + "\n", encoding="utf-8")
    now = datetime.fromisoformat(TIER1_AT.replace("Z", "+00:00"))
    dashboard_row = build_candidate_rows(load_producer(producer_dir, now), now)[0]

    compose_result = tier1["sent_attempt"]["deduped"].compose_result
    adapter = TelegramDeliveryAdapter(object(), console_sink=None)
    adapter.bind_delivery(
        body=compose_result.dispatched_body,
        mint=MINT,
        composed_snapshot=compose_result.snapshot,
        delivery_context={
            "candidate": {
                "migration_time_utc": BASELINE_AT,
                "fee_gate_lifecycle": {
                    "lifecycle_version": "PHX2_FEE_GATE_LIFECYCLE_V1",
                    "lifecycle_state": "FRESH_CONFIRMED",
                    "evidence_proof_digest": security.fee_snapshot.proof_digest,
                },
            },
            "market_context": {
                "current_market_cap_usd": TIER1_MC,
                "liquidity_usd": "12369",
                "central_ath": latest,
                "risk_assessment": {
                    "risk_label": RISK_MEDIUM,
                    "risk_reasons": [REASON_LP_FALLING],
                },
            },
            "activation": activation,
            "security_decision": security,
            "volume_classifier": "UNKNOWN (SYNTHETIC_FIXTURE)",
            "liquidity_quality": "UNKNOWN (SYNTHETIC_FIXTURE)",
        },
        created_at_utc=TIER1_AT,
    )
    telegram = adapter.last_compose_artifact
    assert telegram is not None
    # 2026-07-28 remediation (2026-07-29 final cleanup): the risk line
    # renders operator wording only; the raw label/reason tokens stay in the
    # compose artifact's source proofs.
    assert "Risk: Medium — LP falling" in adapter._composed.text
    assert "RISK_MEDIUM" not in adapter._composed.text
    assert telegram["source_proofs"]["risk_reasons"] == [REASON_LP_FALLING]

    central_digest = latest["ath_evidence_digest"]
    activation_digest = activation_central["ath_evidence_digest"]
    activation_proof_digest = activation["activation_proof_digest"]
    assert paper.extra["central_ath"]["ath_evidence_digest"] == central_digest
    assert security_record["central_ath"]["ath_evidence_digest"] == central_digest
    assert dashboard_row["athEvidenceDigest"] == central_digest
    assert telegram["source_proofs"]["central_ath_evidence_digest"] == central_digest

    assert paper.extra["activation"]["activation_evidence_digest"] == activation_digest
    assert security_record["activation"]["activation_evidence_digest"] == activation_digest
    assert dashboard_row["activationEvidenceDigest"] == activation_digest
    assert telegram["source_proofs"]["activation_evidence_digest"] == activation_digest
    assert paper.extra["activation"]["activation_proof_digest"] \
        == activation_proof_digest
    assert security_record["activation"]["activation_proof_digest"] \
        == activation_proof_digest
    assert dashboard_row["activationProofDigest"] == activation_proof_digest
    assert telegram["source_proofs"]["activation_proof_digest"] \
        == activation_proof_digest
    assert telegram["source_proofs"]["risk_label"] == RISK_MEDIUM
    assert telegram["source_proofs"]["risk_reasons"] == [REASON_LP_FALLING]

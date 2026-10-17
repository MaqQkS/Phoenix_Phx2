"""Offline acceptance replay: the last real alert under the V3 pair ATH.

Replays mint ``5MAse2w3spYtJaoYFhJgy4B2Ruzs8FtC37B7SQszpump`` (sent
2026-08-03T17:18:11Z, Telegram message_id 5414, Tier 2) in fully isolated
state, through the REAL paid-primary production classes:

    recorded migration proof -> pair resolution -> V3 pair hydration
    (coarse 15s + 1s refinement + validated USD valuation) -> authenticated
    supply -> coherent central ATH -> current market -> drawdown -> tier ->
    committed composer -> FAKE delivery (recording client, never a socket)

The provider candles are the verbatim recorded output of the 2026-08-03
read-only capability probe against the real pair.  Nothing here touches the
production ledger, epoch, checkpoints or run artifacts, and nothing sends.

Run:  .venv/Scripts/python.exe -m PHX2.scripts.replay_20260803_v3_ath_last_alert
"""

from __future__ import annotations

import itertools
import json
from datetime import datetime, timezone
from decimal import Decimal, localcontext
from pathlib import Path

from PHX2.free_tier_producer.ath_state import (
    CentralAthStateStore,
    resolved_market_cap_from,
)
from PHX2.free_tier_producer.liquidity_integrity import WSOL_MINT
from PHX2.free_tier_producer.market_budget import (
    ATH_V3_REQUEST_ORIGINS,
    MarketPhysicalRequestMeter,
    reconcile,
)
from PHX2.free_tier_producer.market_scheduler import project_closed_tier
from PHX2.free_tier_producer.paid_birdeye import PaidBirdeyeMarketTransport
from PHX2.models.ath_coverage import classify_ath_coverage
from PHX2.stage29.birdeye_constants import (
    BIRDEYE_PATH_OHLCV,
    BIRDEYE_PATH_PRICE,
    BIRDEYE_PATH_V3_PAIR_OHLCV,
    BIRDEYE_PATH_V3_TOKEN_OHLCV,
)
from PHX2.stage29.stage29_2_birdeye_http_transport import (
    Stage29_2BirdeyeHttpResult,
)
from PHX2.stage29.stage29_2_birdeye_models import (
    BIRDEYE_REFUSAL_REASON_HTTP_STATUS_REJECTED,
    BIRDEYE_REFUSAL_REASON_NONE,
)
from PHX2.stage29.stage29_2_birdeye_readiness import (
    Stage29_2BirdeyeEndpointSecret,
)
from PHX2.stage30 import stage30_11_13_committed_no_send_composer as composer
from PHX2.stage30.stage30_11_2_fake_runtime_gate_proof import (
    make_constant_clock,
)
from PHX2.stage30.stage30_11_5_fake_live_wiring_proof import (
    Stage30_11_5RecordingFakeTransportClient,
)

FIXTURE_PATH = (Path(__file__).resolve().parents[1] / "tests" / "fixtures"
                / "v3_pair_ath_last_alert_20260803.json")
FIXTURE = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))

MINT = FIXTURE["token_mint"]
PAIR = FIXTURE["pair_address"]
MIGRATION_ISO = FIXTURE["migration_time_utc"]
NOW_UNIX = FIXTURE["send_unix"]
NOW_ISO = FIXTURE["send_time_utc"]
EPOCH_ID = "epoch_replay_20260803_isolated"
SUPPLY = FIXTURE["authoritative_supply"]
OLD = FIXTURE["old_alert"]

#: The REAL migration proof of the sent candidate (public fields of
#: ``migration_proofs.jsonl``, run paid_primary_live_24x7_20260803T171355Z).
MIGRATION_PROOF = {
    "candidate_mint": MINT,
    "base_mint": MINT,
    "quote_mint": WSOL_MINT,
    "pool": PAIR,
    "migration_slot": FIXTURE["migration_slot"],
    "migration_signature": (
        "3fAawvaNBCzgnHcsDM2GjJ2MbVRwoWvSzCmYAEtfb1WRsZWdKnhSZ19fJgCcxPyAX"
        "coF7qe57EbzmoKvQNZAfnR9"),
    "migration_instruction_version": "migrate_v2",
    "canonical_pda_valid": True,
    "vault_derivation_valid": True,
    "vault_ownership_valid": True,
    "proof_version": "PHX2_MIGRATION_PROOF_V2",
}


class RecordedProbeInner:
    """Serves the verbatim recorded probe candles (provider range semantics)."""

    def __init__(self) -> None:
        self.calls = []

    @staticmethod
    def _slice(series, time_from, time_to, address):
        out = []
        for row in series:
            when = row.get("unix_time", row.get("unixTime"))
            if when is None or when < time_from or when > time_to:
                continue
            item = {"unix_time": when, "address": address, "h": row["h"]}
            for key in ("v", "v_usd"):
                if key in row:
                    item[key] = row[key]
            out.append(item)
        return out

    def get(self, *, endpoint_secret, path, query_params, timeout_seconds):
        params = dict(query_params)
        self.calls.append({"path": path, "params": params})
        interval = params.get("type")
        time_from = int(params.get("time_from", 0) or 0)
        time_to = int(params.get("time_to", 0) or 0)
        address = str(params.get("address") or "")
        if path == BIRDEYE_PATH_V3_PAIR_OHLCV:
            series = (FIXTURE["pair_15s_native"] if interval == "15s"
                      else FIXTURE["pair_1s_native"])
        elif path == BIRDEYE_PATH_V3_TOKEN_OHLCV:
            series = (FIXTURE["token_15s_usd"] if interval == "15s"
                      else FIXTURE["token_1s_usd"])
        elif path == BIRDEYE_PATH_OHLCV:
            series = FIXTURE["token_1m_v1_old_evidence"]
        elif path == BIRDEYE_PATH_PRICE:
            return Stage29_2BirdeyeHttpResult(
                refusal_reason=BIRDEYE_REFUSAL_REASON_NONE,
                http_status_code=200,
                body={"success": True, "data": {
                    "value": OLD["current_price"],
                    "updateUnixTime": NOW_UNIX}},
                fetched_at_utc="2026-08-03T17:18:11+00:00")
        else:
            return Stage29_2BirdeyeHttpResult(
                refusal_reason=BIRDEYE_REFUSAL_REASON_HTTP_STATUS_REJECTED,
                http_status_code=404, body=None,
                fetched_at_utc="2026-08-03T17:18:11+00:00")
        return Stage29_2BirdeyeHttpResult(
            refusal_reason=BIRDEYE_REFUSAL_REASON_NONE,
            http_status_code=200,
            body={"success": True,
                  "data": {"items": self._slice(series, time_from, time_to,
                                                address)}},
            fetched_at_utc="2026-08-03T17:18:11+00:00")


def resolve_pair_from_proof() -> dict:
    """Authenticated pair resolution: exactly what admission proved."""

    assert MIGRATION_PROOF["proof_version"] == "PHX2_MIGRATION_PROOF_V2"
    assert MIGRATION_PROOF["canonical_pda_valid"] is True
    assert MIGRATION_PROOF["vault_derivation_valid"] is True
    assert MIGRATION_PROOF["vault_ownership_valid"] is True
    assert MIGRATION_PROOF["base_mint"] == MINT
    assert MIGRATION_PROOF["quote_mint"] == WSOL_MINT
    return {"pool_address": MIGRATION_PROOF["pool"],
            "base_mint": MIGRATION_PROOF["base_mint"],
            "quote_mint": MIGRATION_PROOF["quote_mint"]}


def build_hydrated_store(meter: MarketPhysicalRequestMeter):
    store = CentralAthStateStore(path=None, hydration_now_fn=lambda: NOW_ISO)
    assert store.bind_live_epoch(EPOCH_ID)
    pair = resolve_pair_from_proof()
    assert store.register_migration_pair(
        mint=MINT, pool_address=pair["pool_address"],
        quote_mint=pair["quote_mint"], anchor_utc=MIGRATION_ISO,
        tracking_started_at_utc="2026-08-03T17:15:30Z")
    store.schedule_hydration(MINT, anchor_utc=MIGRATION_ISO,
                             scheduled_at_utc="2026-08-03T17:15:30Z")
    assert store.observe_authoritative_supply(
        mint=MINT, raw_amount=SUPPLY["raw_amount"],
        decimals=SUPPLY["decimals"],
        normalized_supply=SUPPLY["normalized_supply"],
        rpc_context_slot=SUPPLY["rpc_context_slot"],
        fetched_at_utc="2026-08-03T17:16:08Z", source=SUPPLY["source"],
        live_epoch_id=EPOCH_ID,
        request_ticket_id="provider_replay_supply_5MAse2w3",
        validation_result="SUPPLY_VALID")
    mono = itertools.count(start=1)
    inner = RecordedProbeInner()
    transport = PaidBirdeyeMarketTransport(
        inner_transport=inner, endpoint_secret=object(),
        min_interval_seconds=0.0, cache_ttl_seconds=0.0,
        ohlcv_cache_ttl_seconds=0.0, max_attempts=1, backoff_seconds=(),
        now_fn=lambda: float(NOW_UNIX),
        monotonic_fn=lambda: float(next(mono)) * 0.25,
        sleep_fn=lambda _s: None, ath_store=store,
        physical_request_meter=meter)
    outcome = transport.refresh_ath_history(MINT, timeout_seconds=5)
    return store, transport, inner, outcome


class _FreshnessTransport:
    def __init__(self, *, current_price: str, ath_price: str) -> None:
        self._current = current_price
        self._ath = ath_price

    def get(self, *, endpoint_secret, path, query_params, timeout_seconds):
        if path == BIRDEYE_PATH_PRICE:
            body = {"success": True, "data": {
                "value": self._current, "updateUnixTime": NOW_UNIX}}
        elif path == BIRDEYE_PATH_OHLCV:
            body = {"success": True, "data": {"items": [
                {"h": self._ath, "unixTime": NOW_UNIX - 120},
                {"h": self._current, "unixTime": NOW_UNIX - 60}]}}
        else:
            return Stage29_2BirdeyeHttpResult(
                refusal_reason=BIRDEYE_REFUSAL_REASON_HTTP_STATUS_REJECTED,
                http_status_code=404, body=None,
                fetched_at_utc="2026-08-03T17:18:11+00:00")
        return Stage29_2BirdeyeHttpResult(
            refusal_reason=BIRDEYE_REFUSAL_REASON_NONE,
            http_status_code=200, body=body,
            fetched_at_utc="2026-08-03T17:18:11+00:00")


def compose_from(store, *, current_market_cap: Decimal, label: str):
    snap = store.snapshot(MINT)
    supply = Decimal(snap["resolved_supply"])
    current_price = (current_market_cap / supply).quantize(Decimal("1E-21"))
    request = composer.Stage30_11_13RevalidationRequest(
        token_mint=MINT, candidate_id="replay_20260803_last_alert",
        migration_time_utc=MIGRATION_ISO,
        current_price=str(current_price),
        current_market_cap_usd=str(current_market_cap),
        created_at_utc=NOW_ISO, migration_confirmed=True,
        symbol_or_name="shit", migration_source="REPLAY_RECORDED_PROBE",
        liquidity_usd="13701.503851485248", age_display="2m",
        market_context_status="PRESENT",
        market_context_fetched_at_utc="2026-08-03T17:18:07Z",
        authoritative_ath_price=snap["ath_price"],
        authoritative_ath_market_cap_usd=snap["ath_market_cap"],
        authoritative_ath_timestamp=snap["ath_timestamp"],
        authoritative_ath_provider=snap["ath_provider"],
        authoritative_ath_observation_type=snap["ath_observation_type"],
        authoritative_ath_status=snap["ath_status"],
        authoritative_ath_market_cap_evidence_price_usd=snap[
            "ath_market_cap_evidence_price_usd"],
        ath_coverage=classify_ath_coverage(
            discovery_provenance="LIVE_HELIUS",
            ath_hydration_status=snap["ath_hydration_status"]),
        resolved_ath_price=snap["resolved_ath_price"],
        resolved_supply=snap["resolved_supply"],
        resolved_supply_basis=snap["resolved_supply_basis"],
        resolved_ath_market_cap_usd=snap["resolved_ath_market_cap"],
        resolved_observed_at_utc=snap["resolved_observed_at_utc"],
        resolved_ath_source=snap["resolved_source"],
        resolved_ath_observation_type=snap["resolved_observation_type"],
        resolved_ath_status=snap["resolved_status"],
        resolved_evidence_digest=snap["resolved_evidence_digest"],
        resolution_method=snap["resolution_method"])
    client = Stage30_11_5RecordingFakeTransportClient(created_at_utc=NOW_ISO)
    result = composer.compose_no_send_dispatch(
        request,
        ath_transport=_FreshnessTransport(
            current_price=str(current_price),
            ath_price=snap["resolved_ath_price"]),
        ath_endpoint_secret=Stage29_2BirdeyeEndpointSecret(
            _api_key="abcd1234efgh5678ijkl9012mnop3456",
            _base_url="https://aaaa-bbbb.example"),
        now_utc=datetime(2026, 8, 3, 17, 18, 11, tzinfo=timezone.utc),
        transport_client=client,
        now_seconds=make_constant_clock(Decimal(0)),
        market_context_max_age_seconds=3600)
    delivered = bool(client.bodies)
    print(f"  [{label}] compose={result.decision} "
          f"tier={getattr(result.snapshot, 'tier_token', None)} "
          f"fake_delivery={'SENT_OK' if delivered else 'NONE'} "
          f"reason={result.reason}")
    return result, client


def main() -> int:
    print("=== PHX2 offline acceptance replay: 2026-08-03 last real alert ===")
    print(f"mint={MINT}")
    print(f"pair={PAIR}")
    print(f"migration={MIGRATION_ISO}  evaluation={NOW_ISO} (send instant)")

    # ---- 0. Reproduce the OLD (incorrect) evidence exactly ----------------
    old_high = max(Decimal(str(row["h"]))
                   for row in FIXTURE["token_1m_v1_old_evidence"])
    with localcontext() as ctx:
        ctx.prec = 60
        old_mc = old_high * Decimal(SUPPLY["normalized_supply"])
    assert str(old_high) == "0.000024672653985893096".rstrip()  # noqa: S101
    assert format(old_mc, "f") == OLD["ath_market_cap"]
    print("\n-- old (sent) evidence reproduced from V1 token 1m window --")
    print(f"  old_ath_price={old_high}")
    print(f"  old_ath_market_cap={format(old_mc, 'f')}")

    # ---- 1. Canonical V3 replay ------------------------------------------
    meter = MarketPhysicalRequestMeter()
    store, transport, inner, outcome = build_hydrated_store(meter)
    snap = store.snapshot(MINT)
    v3 = store.v3_pair_state(MINT)
    assert outcome["complete"] is True, outcome
    corrected_mc = Decimal(snap["resolved_ath_market_cap"])
    recomputed = resolved_market_cap_from(
        snap["resolved_ath_price"], snap["resolved_supply"])
    assert recomputed == corrected_mc

    current_mc = Decimal(OLD["current_market_cap_usd"])
    old_tier, old_drawdown = project_closed_tier(
        ath_market_cap_usd=OLD["ath_market_cap"],
        current_market_cap_usd=str(current_mc))
    new_tier, new_drawdown = project_closed_tier(
        ath_market_cap_usd=str(corrected_mc),
        current_market_cap_usd=str(current_mc))

    print("\n-- canonical V3 pair replay --")
    print(f"  hydration={snap['ath_hydration_status']} "
          f"canonical_source={snap['ath_canonical_source']}")
    print(f"  coarse_peak={v3['coarse_peak']}")
    print(f"  refined_peak={v3['refined_peak']}")
    print(f"  usd_peak={v3['usd_peak']}")
    print(f"  outlier_mode={v3['outlier_mode']}")

    print("\n-- acceptance report --")
    print(f"Old alert ATH:          ${OLD['ath_market_cap']} "
          f"(price {OLD['ath_price']})")
    print("Old alert ATH source:    token-level V1 /defi/ohlcv 1m, "
          "migration-second time_from (dropped the partial first candle)")
    print(f"V3 pair coarse ATH:     {v3['coarse_peak']['native_high']} SOL "
          f"@ {v3['coarse_peak']['unix_time']}")
    print(f"V3 pair refined ATH:    {v3['refined_peak']['native_high']} SOL "
          f"@ {v3['refined_peak']['unix_time']} "
          f"({v3['refined_peak']['interval']})")
    print(f"Canonical corrected ATH: {snap['resolved_ath_price']} USD "
          f"@ {snap['ath_timestamp']} "
          f"[{snap['resolved_source']}]")
    print(f"Authoritative supply:   {snap['resolved_supply']} "
          f"({snap['resolved_supply_basis']})")
    print(f"Corrected ATH market cap: ${format(corrected_mc, 'f')}")
    print(f"Current MC at send:     ${current_mc}")
    print(f"Corrected drawdown:     {new_drawdown}%  (old: {old_drawdown}%)")
    print(f"Old tier:               {old_tier}")
    print(f"Corrected tier:         {new_tier}")

    result, client = compose_from(
        store, current_market_cap=current_mc, label="last-alert replay")
    assert result.decision == composer.COMPOSE_DECISION_DISPATCHED, (
        result.reason)
    body = client.bodies[-1]
    assert "$31.9k" in body and "$24.5k" not in body
    print("Compose result:         "
          f"{result.decision} ({result.snapshot.tier_token})")
    print("Fake delivery result:   SENT_OK (recording client, no socket)")
    print("Remaining blocker:      NONE")

    # ---- 2. Tier 1 / 2 / 3 fixtures through the same pipeline ------------
    print("\n-- tier fixtures through migration proof -> ... -> fake SENT_OK --")
    expected = {"Tier 1": Decimal("0.45"), "Tier 2": Decimal("0.30"),
                "Tier 3": Decimal("0.12")}
    for tier_name, fraction in expected.items():
        target_mc = (corrected_mc * fraction).quantize(Decimal("0.000001"))
        tier_result, tier_client = compose_from(
            store, current_market_cap=target_mc, label=tier_name)
        assert tier_result.decision == composer.COMPOSE_DECISION_DISPATCHED
        assert tier_result.snapshot.tier_token == tier_name
        assert tier_client.bodies

    # ---- 3. Request-ticket reconciliation --------------------------------
    outcome = reconcile(scheduler_physical_requests_total=0, meter=meter)
    v3_requests = sum(
        outcome["physical_requests_by_origin"].get(origin, 0)
        for origin in ATH_V3_REQUEST_ORIGINS)
    print("\n-- request reconciliation --")
    print(f"  transport_physical_total="
          f"{outcome['transport_physical_requests_total']}")
    print(f"  ATH_V3_REQUESTS={v3_requests} "
          f"by_origin={ {k: v for k, v in outcome['physical_requests_by_origin'].items() if v} }")
    print(f"  unreconciled_delta={outcome['unreconciled_delta']} "
          f"reconciled={outcome['reconciled']}")
    assert outcome["unreconciled_delta"] == 0
    assert outcome["reconciled"] is True

    # ---- 4. Pre-boundary eligibility -------------------------------------
    stats = store.stats()
    print("\n-- isolation --")
    print("  historical/pre-boundary candidates eligible: 0 "
          "(isolated fresh store; live-only epoch "
          f"{EPOCH_ID})")
    print(f"  central stats: v3_complete="
          f"{stats['ath_v3_completed_histories']} "
          f"v3_waiting={stats['ath_v3_waiting_candidates']}")

    print("\nREPLAY_RESULT: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

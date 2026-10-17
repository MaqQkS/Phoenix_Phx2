"""free_tier_selftest.py — OFFLINE selftest for the PHX2 live free-tier producer bundle.

No socket, no network, no env requirement, no real ledger, no Discord, no send. Fake urlopen /
clocks / temp dirs only. Proves:

  * the free-tier transport translates public pools/candles JSON into the committed Birdeye body
    shapes the committed price / market-context / anchored-ATH sources parse,
  * the committed cap-1 engine (pump gate -> market -> composer dip gate -> dedupe reserve ->
    30.11.16 guard) runs end-to-end over the free transport and records a WOULD-PING with the
    no-send recording transport (nothing send-capable constructed),
  * the proven production watch loop drives the same wiring to a clean stop with consistent
    ledger/artifact state,
  * every artifact stream the producer writes normalizes into committed paper-engine snapshots
    (PHX2.paper_trading.pricing.normalize_record) — the paper-compat contract,
  * safety rails: forbidden ledger/out paths refuse, the discord arm gate refuses on every missing
    piece, no-send env hardening drops send-capable vars, and the redaction scanner passes over a
    full artifact set (and would catch a provider-name leak).
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import traceback
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_SELF = str(Path(__file__).resolve().parent)
if _SELF not in sys.path:
    sys.path.insert(0, _SELF)

import free_tier_session as fts                    # noqa: E402  (bootstraps all sys.paths)
from free_tier_market_transport import (           # noqa: E402
    FreeTierMarketTransport, build_free_tier_endpoint_secret,
)
from free_tier_no_send_transport import (          # noqa: E402
    NO_SEND_TRANSPORT_STATUS, FreeTierRecordingNoSendTransport,
)
from free_tier_pricing_tail import (                # noqa: E402
    TAIL_ORIGIN_WATCHLIST, TAIL_ORIGIN_WOULD_PING, FreeTierPricingTail,
)
from free_tier_credit_budget import (               # noqa: E402
    BUDGET_STOP_GETTRANSACTION, BUDGET_STOP_PREFIX, BUDGET_STOP_RATE_LIMIT_429,
    BUDGET_STOP_RPC_SOURCE_DEGRADED, BUDGET_STOP_SEND_CAP, BUDGET_STOP_WS_NOTIFICATIONS,
    BUDGET_STOP_WS_SOURCE_DEGRADED, RAW_WS_CAP_NOTE,
    FreeTierBudgetExhausted, FreeTierCreditBudget, FreeTierCreditBudgetCaps,
    rewrite_result_for_budget_stop, verdict_for_budget_stop,
)
from free_tier_polling_discovery import (           # noqa: E402
    CREATE_POOL_LOG_MARKER, FreeTierPollingCaps, FreeTierPollingDiscovery,
)
from free_tier_risk import (                         # noqa: E402
    HOLDER_SCAN_ENABLED, REASON_LIQUIDITY_COLLAPSE, REASON_LP_THIN,
    REASON_MARKET_INCOMPLETE_REPEATED, REASON_MARKET_REFRESH_FAILING,
    REASON_MARKET_STALE, REASON_MARKET_UNAVAILABLE_PERSISTENT, REASON_NO_MARKET_DATA,
    REASON_POOL_HOT_EARLY, REASON_POOL_TOO_HOT, REASON_PRICE_SPIKE_DUMP,
    RISK_HIGH, RISK_LINE_APPENDED, RISK_LINE_BODY_MISMATCH, RISK_LINE_NO_BINDING,
    RISK_LINE_TOO_LONG, RISK_LOW, RISK_MEDIUM, RISK_UNKNOWN, UNKNOWN_SIGNALS_ALWAYS,
    FreeTierRiskEngine, FreeTierRiskLineTransport, format_risk_line,
    classify_discord_dispatch, DiscordRiskDecision, DISCORD_DISPATCH_ALLOWED,
    LP_INTEGRITY_MODE_DISABLED_SINGLE_STREAM, MEDIUM_RISK_WARNING_ONLY,
    SKIPPED_HIGH_RISK_DISCORD, SKIPPED_MEDIUM_RISK_WEAK_STRUCTURE,
    HIGH_RISK_TOO_HOT, HIGH_RISK_LIQUIDITY_COLLAPSE,
    MEDIUM_RISK_LP_TOO_LOW, MEDIUM_RISK_MC_TOO_LOW, MEDIUM_RISK_MARKET_NOT_FRESH,
)

import build29_cap1_compose_send as cs             # noqa: E402
import build29_cap1_ledger as ledgerlib            # noqa: E402
import build29_cap1_session as sess                # noqa: E402
import build30_session as b30s                     # noqa: E402
from build29_cap1_market_sidecar import Cap1MarketCaps, Cap1MarketSidecar  # noqa: E402
from build30_watchlist import (                     # noqa: E402
    ACTIVATION_EVIDENCE_SCHEMA_VERSION, ACTIVATION_EVIDENCE_SPOT_VERSION,
    ACTIVATION_KIND_LEGACY_MIGRATION,
    ACTIVATION_KIND_SPOT_CURRENT, Watchlist,
    activation_proof_is_durable, activation_proof_is_eligible,
    build_activation_evidence_digest, build_activation_spot_evidence_digest,
    build_migration_baseline_digest,
)
from PHX2.free_tier_producer.ath_state import (     # noqa: E402
    ATH_OBSERVATION_SEAL_SCHEMA_VERSION, CentralAthStateStore,
    build_ath_observation_seal_digest,
)
import production_live_artifacts as artifacts      # noqa: E402
import production_live_axiom_gate as axiomgate     # noqa: E402
from production_live_runner import (               # noqa: E402
    ProductionBounds, production_postflight_verdict, run_production_live_watch,
)

from PHX2.stage29.birdeye_constants import (       # noqa: E402
    BIRDEYE_PATH_OHLCV, BIRDEYE_PATH_PRICE, BIRDEYE_PATH_TOKEN_OVERVIEW,
)
from PHX2.stage29.stage29_2_birdeye_models import (  # noqa: E402
    BIRDEYE_REFUSAL_REASON_NONE,
)
from PHX2.stage30.stage30_11_13_fake_composer_proof import (  # noqa: E402
    PROOF_CURRENT_PRICE, PROOF_LATER_LOWER, PROOF_LIQUIDITY_USD,
    PROOF_MARKET_CAP_USD, PROOF_PEAK_ATH,
)
from PHX2.stage30.stage30_11_2_fake_runtime_gate_proof import make_constant_clock  # noqa: E402
from PHX2.stage30.stage30_11_15_ping_dedupe_ledger import JsonlPingDedupeLedger  # noqa: E402
from PHX2.paper_trading.pricing import normalize_record  # noqa: E402

MINT = "FreeTierProof1111111111111111111111111pump"
POOL = "PoolFreeTierProof111111111111111111111111"
_PEAK_OFFSET_S = 50
_LOWER_OFFSET_S = 4550
_NOW_OFFSET_S = 89550


def _selftest_activation_gate(_candidate, _context):
    """Explicit proven-active fixture for legacy send-lineage selftests.

    Migration lifecycle behavior itself is covered by test_migration_activation;
    these existing checks isolate downstream market/risk/dedupe/transport behavior.
    """
    proof = {
        "token_mint": MINT,
        "candidate_id": "selftest-activation-proof",
        "migration_time_utc": "2026-07-15T23:59:59Z",
        "migration_market_cap_usd": "100",
        "migration_market_cap_source": "GRPC_EVENT",
        "migration_market_cap_observed_at_utc": "2026-07-15T23:59:59Z",
        "migration_market_cap_price": "0.0000001",
        "migration_supply_at_observation": "1000000000",
        "migration_baseline_status": "CAPTURED",
        "activation_multiplier": "1.20",
        "activation_target_market_cap_usd": "120.00",
        "activation_state": "ACTIVE_DIP_WATCH",
        "activated_at_utc": "2026-07-16T00:00:01Z",
        "activation_observation_source": "PAID_MARKET_PRIMARY",
        "activation_current_market_cap_usd": "120.00",
        "activation_observation_fresh": True,
        "activation_proven": True,
        "activation_evidence_source": "PAID_MARKET_PRIMARY",
        "activation_evidence_market_cap_usd": "120.00",
        "activation_evidence_event_at_utc": "2026-07-16T00:00:00Z",
        "activation_evidence_ingested_at_utc": "2026-07-16T00:00:01Z",
        "activation_evidence_version": ACTIVATION_EVIDENCE_SPOT_VERSION,
        "activation_proof_version": ACTIVATION_EVIDENCE_SCHEMA_VERSION,
        "activation_evidence_kind": ACTIVATION_KIND_SPOT_CURRENT,
        "activation_crossing_tick_digest": "b" * 64,
        "activation_crossing_tick_blocked": True,
        "activation_latched": True,
    }
    proof["activation_evidence_digest"] = build_activation_spot_evidence_digest(
        mint=MINT, market_cap=Decimal("120.00"),
        event_at_utc=proof["activation_evidence_event_at_utc"],
        source=proof["activation_evidence_source"],
    )
    proof["activation_source_evidence_digest"] = proof["activation_evidence_digest"]
    proof["migration_baseline_digest_version"] = "phx2_migration_baseline_digest_v1"
    proof["migration_baseline_digest"] = build_migration_baseline_digest(
        token_mint=MINT, candidate_id=proof["candidate_id"],
        market_cap_usd=proof["migration_market_cap_usd"],
        observed_at_utc=proof["migration_market_cap_observed_at_utc"],
        source=proof["migration_market_cap_source"],
        price=proof["migration_market_cap_price"],
        supply=proof["migration_supply_at_observation"])
    proof["activation_observation_seal_version"] = (
        ATH_OBSERVATION_SEAL_SCHEMA_VERSION)
    proof["activation_observation_seal_digest"] = build_ath_observation_seal_digest(
        MINT, {
            "ath_evidence_digest": proof["activation_evidence_digest"],
            "ath_ingested_at_utc": proof["activation_evidence_ingested_at_utc"],
            "ath_observation_seal_validated": True,
        })
    proof["activation_proof_digest"] = build_activation_evidence_digest(
        token_mint=MINT,
        candidate_id=proof["candidate_id"],
        migration_baseline_digest=proof["migration_baseline_digest"],
        migration_market_cap_usd=proof["migration_market_cap_usd"],
        migration_market_cap_observed_at_utc=(
            proof["migration_market_cap_observed_at_utc"]),
        activation_target_market_cap_usd=proof["activation_target_market_cap_usd"],
        activation_evidence_market_cap_usd=proof["activation_evidence_market_cap_usd"],
        activation_evidence_event_at_utc=proof["activation_evidence_event_at_utc"],
        activation_evidence_ingested_at_utc=proof["activation_evidence_ingested_at_utc"],
        activated_at_utc=proof["activated_at_utc"],
        activation_evidence_source=proof["activation_evidence_source"],
        activation_evidence_kind=proof["activation_evidence_kind"],
        activation_source_evidence_digest=proof["activation_evidence_digest"],
        activation_source_evidence_version=proof["activation_evidence_version"],
        activation_observation_seal_digest=(
            proof["activation_observation_seal_digest"]),
        activation_observation_seal_version=(
            proof["activation_observation_seal_version"]),
        activation_crossing_tick_digest=proof["activation_crossing_tick_digest"],
    )
    return {"activation": proof, "eligible": True, "just_activated": False,
            "events": [], "reason": "ACTIVE_DIP_WATCH"}


def _run_activated_candidates(candidates, **kwargs):
    kwargs["activation_gate_fn"] = _selftest_activation_gate
    return sess.run_cap1_candidates(candidates, **kwargs)


def _z(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def make_fake_urlopen(*, anchor: datetime, mc_key: str = "marketCap",
                      include_pairs: bool = True, http_status: int = 200,
                      calls: Optional[List[str]] = None):
    """Canned free-provider bodies derived from the committed PROOF constants, anchored at the
    candidate's migration moment (the proven Stage 30.14.0 dispatch scenario shape)."""
    peak_ts = int((anchor + timedelta(seconds=_PEAK_OFFSET_S)).timestamp())
    lower_ts = int((anchor + timedelta(seconds=_LOWER_OFFSET_S)).timestamp())

    def fake_urlopen(url: str, timeout_seconds: float) -> Tuple[int, bytes]:
        if calls is not None:
            calls.append(url)
        if http_status != 200:
            return http_status, b"{}"
        if "dexscreener" in url:
            if not include_pairs:
                return 200, json.dumps({"pairs": None}).encode("utf-8")
            pair = {
                "chainId": "solana", "dexId": "pumpswap", "pairAddress": POOL,
                "priceUsd": PROOF_CURRENT_PRICE,
                "liquidity": {"usd": float(PROOF_LIQUIDITY_USD)},
                mc_key: float(PROOF_MARKET_CAP_USD),
            }
            shallow = {"chainId": "solana", "dexId": "x", "pairAddress": "Other",
                       "priceUsd": "1", "liquidity": {"usd": 5.0}, "marketCap": 1.0}
            return 200, json.dumps({"pairs": [shallow, pair]}).encode("utf-8")
        if "geckoterminal" in url:
            rows = [
                [peak_ts, "0.0000005", PROOF_PEAK_ATH, "0.0000001", "0.0000004", "1000"],
                [lower_ts, "0.0000004", PROOF_LATER_LOWER, "0.0000001", "0.0000002", "500"],
            ]
            return 200, json.dumps(
                {"data": {"attributes": {"ohlcv_list": rows}}}).encode("utf-8")
        return 404, b"{}"

    return fake_urlopen


def make_transport(fake_urlopen, **kw) -> FreeTierMarketTransport:
    return FreeTierMarketTransport(
        urlopen_fn=fake_urlopen, sleep_fn=lambda _s: None, **kw)


# --------------------------------------------------------------------------- harness


_RESULTS: List[Tuple[str, bool, str]] = []


def check(name: str, fn) -> None:
    try:
        fn()
        _RESULTS.append((name, True, ""))
    except Exception as exc:
        _RESULTS.append((name, False, f"{type(exc).__name__}: {exc}"))
        if os.environ.get("FREE_TIER_SELFTEST_TRACE"):
            traceback.print_exc()


def expect(cond: bool, msg: str) -> None:
    if not cond:
        raise AssertionError(msg)


# --------------------------------------------------------------------------- transport tests


def t_secret_shape():
    from PHX2.stage29.birdeye_constants import is_safe_api_key, is_safe_base_url
    secret = build_free_tier_endpoint_secret()
    expect(is_safe_api_key(secret._api_key), "placeholder key shape invalid")
    expect(is_safe_base_url(secret._base_url), "placeholder base url shape invalid")


def _get(transport, path, params):
    return transport.get(endpoint_secret=build_free_tier_endpoint_secret(), path=path,
                         query_params=params, timeout_seconds=10)


def t_price_translation():
    anchor = datetime.now(timezone.utc) - timedelta(seconds=_NOW_OFFSET_S)
    tr = make_transport(make_fake_urlopen(anchor=anchor))
    res = _get(tr, BIRDEYE_PATH_PRICE, {"address": MINT})
    expect(res.refusal_reason == BIRDEYE_REFUSAL_REASON_NONE, "price refused")
    expect(res.body["data"]["value"] == PROOF_CURRENT_PRICE, "price value wrong")


def t_price_via_committed_source():
    from PHX2.stage29.stage29_2_birdeye_price_source import Stage29_2BirdeyePriceSource
    anchor = datetime.now(timezone.utc) - timedelta(seconds=_NOW_OFFSET_S)
    tr = make_transport(make_fake_urlopen(anchor=anchor))
    src = Stage29_2BirdeyePriceSource(
        transport=tr, endpoint_secret=build_free_tier_endpoint_secret(), timeout_seconds=10)
    snap = src.fetch_snapshot(base_mint=MINT)
    expect(snap.price_value == PROOF_CURRENT_PRICE, f"committed source got {snap.price_value}")


def t_overview_via_committed_source():
    from PHX2.stage30.stage30_4_3_market_context_birdeye_source import (
        Stage30_4_3BirdeyeMarketContextSource,
    )
    from PHX2.stage30.stage30_4_compact_market_context_adapter import project_market_context
    anchor = datetime.now(timezone.utc) - timedelta(seconds=_NOW_OFFSET_S)
    tr = make_transport(make_fake_urlopen(anchor=anchor))
    src = Stage30_4_3BirdeyeMarketContextSource(
        transport=tr, endpoint_secret=build_free_tier_endpoint_secret(), timeout_seconds=10)
    record = project_market_context(session_id=None, run_id=None, candidate_id=None,
                                    token_mint=MINT, created_at_utc=_z(datetime.now(timezone.utc)),
                                    source=src)
    expect(record.market_cap_usd_value is not None, "mc missing via committed source")
    expect(record.liquidity_usd_value is not None, "lp missing via committed source")


def t_overview_fdv_fallback():
    anchor = datetime.now(timezone.utc) - timedelta(seconds=_NOW_OFFSET_S)
    tr = make_transport(make_fake_urlopen(anchor=anchor, mc_key="fdv"))
    res = _get(tr, BIRDEYE_PATH_TOKEN_OVERVIEW, {"address": MINT})
    expect(res.body["data"].get("marketCap") == float(PROOF_MARKET_CAP_USD),
           "fdv fallback did not populate marketCap")


def t_no_pairs_is_missing_not_refusal():
    anchor = datetime.now(timezone.utc) - timedelta(seconds=_NOW_OFFSET_S)
    tr = make_transport(make_fake_urlopen(anchor=anchor, include_pairs=False))
    res = _get(tr, BIRDEYE_PATH_PRICE, {"address": MINT})
    expect(res.refusal_reason == BIRDEYE_REFUSAL_REASON_NONE, "no-pool should not refuse")
    expect(res.body["data"] is None, "no-pool should carry no data axis")


def t_http_error_is_refusal():
    anchor = datetime.now(timezone.utc) - timedelta(seconds=_NOW_OFFSET_S)
    tr = make_transport(make_fake_urlopen(anchor=anchor, http_status=500))
    res = _get(tr, BIRDEYE_PATH_OHLCV, {"address": MINT, "type": "15m",
                                        "time_from": "1", "time_to": "2"})
    expect(res.refusal_reason != BIRDEYE_REFUSAL_REASON_NONE, "http 500 must refuse ohlcv")


def t_ohlcv_window_filter_and_shape():
    anchor = datetime.now(timezone.utc) - timedelta(seconds=_NOW_OFFSET_S)
    now_unix = int((anchor + timedelta(seconds=_NOW_OFFSET_S)).timestamp())
    mig_unix = int(anchor.timestamp())
    tr = make_transport(make_fake_urlopen(anchor=anchor))
    res = _get(tr, BIRDEYE_PATH_OHLCV, {"address": MINT, "type": "15m",
                                        "time_from": str(mig_unix), "time_to": str(now_unix)})
    items = res.body["data"]["items"]
    expect(len(items) == 2, f"expected 2 in-window candles, got {len(items)}")
    highs = {i["h"] for i in items}
    expect(float(PROOF_PEAK_ATH) in {float(h) for h in highs}, "peak high missing")
    # A window that excludes the peak keeps only the later candle.
    res2 = _get(tr, BIRDEYE_PATH_OHLCV, {"address": MINT, "type": "15m",
                                         "time_from": str(mig_unix + 3600),
                                         "time_to": str(now_unix)})
    expect(len(res2.body["data"]["items"]) == 1, "window filter failed")


def t_ohlcv_uses_committed_ath_selection():
    from PHX2.stage29.stage29_2_birdeye_ath_source import (
        fetch_birdeye_ath_snapshot_migration_anchored,
    )
    anchor = datetime.now(timezone.utc) - timedelta(seconds=_NOW_OFFSET_S)
    now_unix = int((anchor + timedelta(seconds=_NOW_OFFSET_S)).timestamp())
    tr = make_transport(make_fake_urlopen(anchor=anchor))
    snap = fetch_birdeye_ath_snapshot_migration_anchored(
        base_mint=MINT, transport=tr, endpoint_secret=build_free_tier_endpoint_secret(),
        timeout_seconds=10, time_from_unix=int(anchor.timestamp()), time_to_unix=now_unix,
        migration_timestamp_utc=_z(anchor))
    expect(snap.ath_value is not None and float(snap.ath_value) == float(PROOF_PEAK_ATH),
           f"anchored ATH wrong: {snap.ath_value}")
    expect(snap.window_starts_post_migration is True, "window flag not post-migration")


def t_budget_cap_refuses():
    anchor = datetime.now(timezone.utc) - timedelta(seconds=_NOW_OFFSET_S)
    tr = make_transport(make_fake_urlopen(anchor=anchor), max_calls_total=0)
    res = _get(tr, BIRDEYE_PATH_PRICE, {"address": MINT})
    expect(res.body is None or res.body.get("data") is None, "capped call must yield no data")
    expect(tr.stats()["capped"] >= 1, "cap counter did not advance")


def t_pair_cache_single_fetch():
    anchor = datetime.now(timezone.utc) - timedelta(seconds=_NOW_OFFSET_S)
    calls: List[str] = []
    tr = make_transport(make_fake_urlopen(anchor=anchor, calls=calls))
    _get(tr, BIRDEYE_PATH_PRICE, {"address": MINT})
    _get(tr, BIRDEYE_PATH_TOKEN_OVERVIEW, {"address": MINT})
    pairs_calls = [c for c in calls if "dexscreener" in c]
    expect(len(pairs_calls) == 1, f"expected 1 pairs lookup, got {len(pairs_calls)}")


def t_fallback_consulted_on_refusal():
    class _FakeFallback:
        def __init__(self):
            self.calls = 0

        def get(self, **kw):
            self.calls += 1
            from PHX2.stage29.stage29_2_birdeye_http_transport import Stage29_2BirdeyeHttpResult
            return Stage29_2BirdeyeHttpResult(
                refusal_reason=BIRDEYE_REFUSAL_REASON_NONE, http_status_code=200,
                body={"success": True, "data": {"value": "1.5", "updateUnixTime": 1}},
                fetched_at_utc="2026-01-01T00:00:00Z")

    anchor = datetime.now(timezone.utc) - timedelta(seconds=_NOW_OFFSET_S)
    fb = _FakeFallback()
    tr = make_transport(make_fake_urlopen(anchor=anchor, http_status=500),
                        fallback_transport=fb)
    res = _get(tr, BIRDEYE_PATH_OHLCV, {"address": MINT, "type": "15m",
                                        "time_from": "1", "time_to": "2"})
    expect(fb.calls == 1, "fallback not consulted")
    expect(res.refusal_reason == BIRDEYE_REFUSAL_REASON_NONE, "fallback result not returned")


def t_simple_market_helper():
    anchor = datetime.now(timezone.utc) - timedelta(seconds=_NOW_OFFSET_S)
    tr = make_transport(make_fake_urlopen(anchor=anchor))
    m = tr.fetch_simple_market(MINT)
    expect(m is not None and m["current_price"] == PROOF_CURRENT_PRICE, "helper price wrong")
    expect("current_market_cap_usd" in m and "liquidity_usd" in m, "helper mc/lp missing")


# --------------------------------------------------------------------------- no-send transport


def t_no_send_transport_records():
    recorded: List[Dict[str, Any]] = []
    tr = FreeTierRecordingNoSendTransport(
        on_record=recorded.append, now_iso_fn=lambda: "2026-01-01T00:00:00Z")
    res = tr.send_one_audited_post(webhook_identity="private_operator",
                                   payload={"content": "PHOENIX would-ping body"})
    expect(res.ok is True and res.transport_status == NO_SEND_TRANSPORT_STATUS, "verdict wrong")
    expect(len(recorded) == 1 and recorded[0]["real_send"] is False, "record missing")
    expect(recorded[0]["content_text"] == "PHOENIX would-ping body", "content not recorded")
    expect(tr.real_send_capable is False and tr.fake_only is True, "markers wrong")


def t_no_send_transport_rejects_bad_payload():
    tr = FreeTierRecordingNoSendTransport(
        on_record=lambda _r: None, now_iso_fn=lambda: "2026-01-01T00:00:00Z")
    for bad in (None, "text", {}, {"content": ""}, {"content": 7}):
        try:
            tr.send_one_audited_post(webhook_identity="x", payload=bad)
            raise AssertionError(f"payload {bad!r} accepted")
        except ValueError:
            pass


# --------------------------------------------------------------------------- committed-engine e2e


def _e2e_engine(tmp: Path) -> Dict[str, Any]:
    anchor = datetime.now(timezone.utc) - timedelta(seconds=_NOW_OFFSET_S)
    tr = make_transport(make_fake_urlopen(anchor=anchor))
    secret = build_free_tier_endpoint_secret()
    sidecar = Cap1MarketSidecar(
        transport=tr, endpoint_secret=secret, timeout_seconds=10, enabled=True,
        caps=Cap1MarketCaps(max_delayed_refresh_seconds=0, max_calls_per_token=4,
                            max_calls_total=64))
    ledger_path = tmp / "ping_dedupe.jsonl"
    ledger_path.write_text("", encoding="utf-8")
    bodies: List[Dict[str, Any]] = []
    guard_transport = FreeTierRecordingNoSendTransport(
        on_record=bodies.append, now_iso_fn=lambda: _z(datetime.now(timezone.utc)))
    now_iso = _z(datetime.now(timezone.utc))
    out = _run_activated_candidates(
        [{"token_mint": MINT, "candidate_id": "ft_" + MINT[:8],
          "migration_time_utc": _z(anchor), "source_ref": None, "symbol_or_name": None}],
        sidecar=sidecar, ath_transport=tr, ath_endpoint_secret=secret,
        now_utc=datetime.now(timezone.utc), now_seconds=make_constant_clock(Decimal(0)),
        now_iso_fn=lambda: _z(datetime.now(timezone.utc)), sleep_fn=lambda _s: None,
        ledger=JsonlPingDedupeLedger(path=ledger_path),
        guard=cs.make_guard(transport=guard_transport),
        authorization=cs.build_authorization(
            confirm_token=fts.LOCKED_CONFIRM_TOKEN, operator_label="SELFTEST",
            authorization_reason="SELFTEST_NO_SEND", created_at_utc=now_iso),
        created_at_utc=now_iso, pump_required=True)
    out["_bodies"] = bodies
    out["_ledger_lines"] = len([ln for ln in ledger_path.read_text(encoding="utf-8").splitlines()
                                if ln.strip()])
    return out


def t_e2e_would_ping_dispatches():
    with tempfile.TemporaryDirectory() as td:
        out = _e2e_engine(Path(td))
        expect(out["outcome"] == "ONE_SEND_COMMITTED", f"outcome={out['outcome']} "
               f"per_candidate={out['per_candidate']}")
        rec = out["per_candidate"][0]
        expect(rec["reason"] == "SENT_OK_COMMITTED", f"reason={rec['reason']}")
        expect(rec.get("compose_tier") is not None, "compose_tier missing")
        expect(rec.get("compose_anchored_ath_mc") is not None, "anchored ath mc missing")
        expect(out["_ledger_lines"] == 1, f"ledger lines={out['_ledger_lines']}")
        expect(len(out["_bodies"]) == 1, "would-ping body not recorded")
        sr = out["sent_attempt"]["send_result"]
        expect(getattr(sr, "dispatch_forwarded", False) is True, "guard did not forward")
        expect(getattr(sr, "transport_ok", None) is True, "recording verdict not ok")


def t_e2e_non_pump_dropped():
    with tempfile.TemporaryDirectory() as td:
        anchor = datetime.now(timezone.utc) - timedelta(seconds=_NOW_OFFSET_S)
        tr = make_transport(make_fake_urlopen(anchor=anchor))
        secret = build_free_tier_endpoint_secret()
        sidecar = Cap1MarketSidecar(transport=tr, endpoint_secret=secret, timeout_seconds=10,
                                    enabled=True, caps=Cap1MarketCaps())
        ledger_path = Path(td) / "l.jsonl"
        ledger_path.write_text("", encoding="utf-8")
        out = _run_activated_candidates(
            [{"token_mint": "NotAPumpMint111111111111111111111111ABCD",
              "candidate_id": "x", "migration_time_utc": _z(anchor),
              "source_ref": None, "symbol_or_name": None}],
            sidecar=sidecar, ath_transport=tr, ath_endpoint_secret=secret,
            now_utc=datetime.now(timezone.utc), now_seconds=make_constant_clock(Decimal(0)),
            now_iso_fn=lambda: _z(datetime.now(timezone.utc)), sleep_fn=lambda _s: None,
            ledger=JsonlPingDedupeLedger(path=ledger_path), guard=None, authorization=None,
            created_at_utc=_z(datetime.now(timezone.utc)), pump_required=True)
        expect(out["outcome"] == "ZERO_SEND", "non-pump must not dispatch")
        expect(out["per_candidate"][0]["reason"] == "NOT_PUMP_SUFFIX", "wrong reason")


def t_e2e_liquidity_floor_blocks():
    from production_live_runner import liquidity_floor_block_reason
    reason = liquidity_floor_block_reason(MINT, {"liquidity_usd": "100.5"},
                                          min_liquidity_usd=Decimal("4500"))
    expect(reason is not None and reason.startswith("LIQUIDITY_USD_BELOW_MIN"), "floor not applied")
    ok = liquidity_floor_block_reason(MINT, {"liquidity_usd": PROOF_LIQUIDITY_USD},
                                      min_liquidity_usd=Decimal("4500"))
    expect(ok is None, "proof LP must pass the floor")


# --------------------------------------------------------------------------- watch-loop smoke


def _run_loop_smoke(tmp: Path, budget: Optional[FreeTierCreditBudget] = None,
                    max_total_ticks: int = 2) -> Tuple[Dict[str, Any], Path]:
    anchor = datetime.now(timezone.utc) - timedelta(seconds=_NOW_OFFSET_S)
    out_dir = tmp / "out"
    out_dir.mkdir()
    ledger_path = tmp / "ping_dedupe.jsonl"
    ledger_path.write_text("", encoding="utf-8")

    tr = make_transport(make_fake_urlopen(anchor=anchor))
    secret = build_free_tier_endpoint_secret()
    bodies_path = out_dir / fts.WOULD_PING_BODIES_BASENAME
    would_ping_path = out_dir / fts.WOULD_PING_BASENAME
    guard_transport = FreeTierRecordingNoSendTransport(
        on_record=lambda rec: fts._append_jsonl(bodies_path, rec),
        now_iso_fn=lambda: _z(datetime.now(timezone.utc)))

    def sidecar_factory(_cycle: int) -> Cap1MarketSidecar:
        return Cap1MarketSidecar(transport=tr, endpoint_secret=secret, timeout_seconds=10,
                                 enabled=True, caps=Cap1MarketCaps(
                                     max_delayed_refresh_seconds=0, max_calls_per_token=4,
                                     max_calls_total=64))

    seeded = {"done": False}

    def discovery_fn():
        if seeded["done"]:
            return []
        seeded["done"] = True
        return [{"token_mint": MINT, "candidate_id": "ft_" + MINT[:8],
                 "migration_time_utc": _z(anchor), "source_ref": None, "symbol_or_name": None}]

    def on_candidate_record(*, rec, entry, cycle, observed_at_utc, ledger_touched,
                            transport_attempted, axiom=None):
        record = artifacts.build_candidate_recheck_record(
            rec=rec, entry=entry, cycle=cycle, observed_at_utc=observed_at_utc,
            ledger_touched=ledger_touched, transport_attempted=transport_attempted, axiom=None)
        artifacts.append_candidate_jsonl(str(out_dir), rec.get("token_mint", ""), record)
        if rec.get("reason") == "SENT_OK_COMMITTED":
            mc = rec.get("market_context") or {}
            fts._append_jsonl(would_ping_path, {
                "kind": "FREE_TIER_WOULD_PING", "token_mint": rec.get("token_mint", ""),
                "candidate_id": getattr(entry, "candidate_id", None),
                "observed_at_utc": observed_at_utc, "tick": cycle,
                "market_context": {
                    "current_price": mc.get("current_price"),
                    "current_market_cap_usd": mc.get("current_market_cap_usd"),
                    "liquidity_usd": mc.get("liquidity_usd"),
                    "market_context_fetched_at_utc": mc.get("market_context_fetched_at_utc"),
                },
                "compose_tier": rec.get("compose_tier"),
                "compose_drawdown_pct": rec.get("compose_drawdown_pct"),
                "compose_anchored_ath_mc": rec.get("compose_anchored_ath_mc"),
                "producer_mode": "FREE_TIER_NO_SEND", "real_send_attempted": False,
            })

    def on_send_record(**kw):
        record = artifacts.build_send_attempt_record(**kw)
        record = {**record, "kind": "FREE_TIER_WOULD_PING_ATTEMPT",
                  "producer_mode": "FREE_TIER_NO_SEND", "real_send": False}
        artifacts.append_send_jsonl(str(out_dir), record)
        if budget is not None:
            budget.record_send_attempt(sent_ok=bool(record.get("sent_ok")))
        return record

    def on_cycle(**_kw):
        if budget is not None:
            budget.observe_market(tr.stats())
            budget.check_and_raise()

    def on_heartbeat(hb):
        artifacts.append_heartbeat_jsonl(str(out_dir), hb)
        artifacts.write_json(str(out_dir), fts.PRODUCER_HEARTBEAT_BASENAME, hb)

    mono = {"t": 0.0}

    def fake_monotonic() -> float:
        return mono["t"]

    def fake_sleep(s: float) -> None:
        mono["t"] += max(float(s), 0.0)

    now_iso = lambda: _z(datetime.now(timezone.utc))  # noqa: E731

    result = run_production_live_watch(
        watchlist=Watchlist(max_size=16),
        axiom_source=axiomgate.NullAxiomFeeSource(),
        axiom_config=fts._strict_axiom_config(),
        sidecar_factory=sidecar_factory, ath_transport=tr, ath_endpoint_secret=secret,
        ledger=JsonlPingDedupeLedger(path=ledger_path),
        guard_factory=lambda: cs.make_guard(transport=guard_transport),
        authorization=cs.build_authorization(
            confirm_token=fts.LOCKED_CONFIRM_TOKEN, operator_label="SELFTEST",
            authorization_reason="SELFTEST_LOOP", created_at_utc=now_iso()),
        now_dt_fn=lambda: datetime.now(timezone.utc), now_iso_fn=now_iso,
        now_seconds=make_constant_clock(Decimal(0)),
        sleep_fn=fake_sleep, monotonic_fn=fake_monotonic,
        bounds=ProductionBounds(
            recheck_interval_seconds=1.0, max_candidate_age_seconds=999999,
            max_rechecks_per_candidate=999, max_runtime_seconds=999999.0,
            max_watchlist_size=16, queue_pressure_max=16, max_market_calls_total=999999,
            reseed_interval_seconds=999999.0, max_reseeds=0,
            min_seconds_between_sends=300.0, max_consecutive_source_failures=3,
            max_consecutive_throttles=5, max_total_ticks=int(max_total_ticks)),
        run_cap1_candidates_fn=_run_activated_candidates,
        ledger_line_count_fn=b30s._ledger_line_count_fn(str(ledger_path)),
        discovery_fn=discovery_fn, on_axiom_record=None,
        on_candidate_record=on_candidate_record, on_send_record=on_send_record,
        on_cycle=on_cycle,
        redaction_scan_fn=lambda: artifacts.run_redaction_scan(str(out_dir)),
        watch_state_path=str(out_dir / "watch_state.jsonl"),
        on_heartbeat=on_heartbeat, require_axiom_pass=False)
    return result, out_dir


def t_loop_smoke_clean_stop_one_would_ping():
    with tempfile.TemporaryDirectory() as td:
        result, out_dir = _run_loop_smoke(Path(td))
        expect(result["sends"] == 1, f"sends={result['sends']}")
        expect(result["total_ledger_delta"] == 1, "ledger delta != 1")
        expect(result["ledger_consistent"] is True, "ledger inconsistent")
        expect(result["stop_reason"] == "TICK_BUDGET", f"stop={result['stop_reason']}")
        verdict = production_postflight_verdict(result)
        expect(verdict["postflight_ok"] is True and verdict["exit_code"] == 0,
               f"verdict={verdict}")
        for rel in ("sends.jsonl", fts.WOULD_PING_BASENAME, fts.WOULD_PING_BODIES_BASENAME,
                    "watch_state.jsonl", "heartbeat.jsonl", fts.PRODUCER_HEARTBEAT_BASENAME,
                    "candidates/" + MINT[:8] + ".jsonl"):
            expect((out_dir / rel).exists(), f"missing artifact {rel}")
        scan = artifacts.run_redaction_scan(str(out_dir))
        expect(scan["redaction_status"] == "REDACTED" and scan["total_unsafe_hits"] == 0,
               f"redaction failed: {scan['per_file_hits']}")
        expect(scan["positive_control_ok"] is True, "positive control failed")


def t_loop_artifacts_normalize_for_paper_engine():
    with tempfile.TemporaryDirectory() as td:
        _result, out_dir = _run_loop_smoke(Path(td))
        cand_file = out_dir / "candidates" / (MINT[:8] + ".jsonl")
        lines = [json.loads(ln) for ln in cand_file.read_text(encoding="utf-8").splitlines()]
        send_line = next(ln for ln in lines if ln.get("rejection_reason") == "SENT_OK_COMMITTED")
        snap = normalize_record(send_line, str(cand_file), 1)
        expect(snap is not None and snap.mint == MINT, "recheck record did not normalize")
        expect(snap.price_usd is not None and snap.market_cap_usd is not None
               and snap.liquidity_usd is not None, "recheck snapshot lost price/mc/lp")
        expect(snap.tier is not None, f"tier not normalized: {send_line.get('compose_tier')}")
        expect(snap.ath_market_cap_usd is not None, "anchored ATH MC not normalized")
        wp_line = json.loads((out_dir / fts.WOULD_PING_BASENAME)
                             .read_text(encoding="utf-8").splitlines()[0])
        wp_snap = normalize_record(wp_line, "would_ping_records.jsonl", 1)
        expect(wp_snap is not None and wp_snap.mint == MINT
               and wp_snap.market_cap_usd is not None, "would-ping record did not normalize")
        send_rec = json.loads((out_dir / "sends.jsonl")
                              .read_text(encoding="utf-8").splitlines()[0])
        s_snap = normalize_record(send_rec, "sends.jsonl", 1)
        expect(s_snap is not None and s_snap.mint == MINT, "send record did not normalize")
        body_rec = json.loads((out_dir / fts.WOULD_PING_BODIES_BASENAME)
                              .read_text(encoding="utf-8").splitlines()[0])
        expect(normalize_record(body_rec, "b.jsonl", 1) is None,
               "body record must NOT become a paper snapshot")
        hb_rec = json.loads((out_dir / "heartbeat.jsonl")
                            .read_text(encoding="utf-8").splitlines()[0])
        expect(normalize_record(hb_rec, "h.jsonl", 1) is None,
               "heartbeat must NOT become a paper snapshot")


# --------------------------------------------------------------------------- pricing tail


def t_pricing_tail_records_and_normalizes():
    with tempfile.TemporaryDirectory() as td:
        clock = {"t": 1000.0}
        tail = FreeTierPricingTail(
            out_dir=td,
            fetch_market_fn=lambda _m: {"current_price": PROOF_CURRENT_PRICE,
                                        "current_market_cap_usd": PROOF_MARKET_CAP_USD,
                                        "liquidity_usd": PROOF_LIQUIDITY_USD,
                                        "fetched_at_utc": "2026-01-01T00:00:00Z"},
            now_epoch_fn=lambda: clock["t"], max_tracked=2, max_tail_age_seconds=100.0)
        expect(tail.track(MINT, ath_market_cap_display="$68.0K", tier_at_ping="TIER_3"),
               "track refused")
        appended = tail.poll("2026-01-01T00:00:01Z")
        expect(appended == 1, f"appended={appended}")
        rec = json.loads((Path(td) / "pricing_tail.jsonl")
                         .read_text(encoding="utf-8").splitlines()[0])
        snap = normalize_record(rec, "pricing_tail.jsonl", 1)
        expect(snap is not None and snap.mint == MINT and snap.price_usd is not None,
               "tail record did not normalize")
        expect(snap.ath_market_cap_usd is not None, "tail ATH did not normalize")


def t_pricing_tail_bounds():
    with tempfile.TemporaryDirectory() as td:
        clock = {"t": 0.0}
        tail = FreeTierPricingTail(out_dir=td, fetch_market_fn=lambda _m: None,
                                   now_epoch_fn=lambda: clock["t"],
                                   max_tracked=1, max_tail_age_seconds=50.0)
        expect(tail.track("A" * 40 + "pump"), "first track refused")
        expect(not tail.track("B" * 40 + "pump"), "bound not enforced")
        clock["t"] = 60.0
        tail.poll("2026-01-01T00:00:00Z")
        expect(tail.summary()["tracked"] == 0, "expiry not enforced")
        expect(tail.track("B" * 40 + "pump"), "slot not freed after expiry")


# --------------------------------------------------------------------------- safety rails


def t_forbidden_paths_refuse():
    expect(fts.path_is_forbidden(r"C:\Users\BalaC\phx2_one_send_ceremony\ping_dedupe.jsonl"),
           "old ceremony ledger not protected")
    expect(fts.path_is_forbidden(r"C:\Users\BalaC\phx2_production_private_live\out\x"),
           "production tree not protected")
    expect(fts.path_is_forbidden(r"C:\Users\BalaC\phx2_capped_one_send_ceremony"),
           "capped ceremony tree not protected")
    expect(not fts.path_is_forbidden(fts.LEDGER_DEFAULT), "new ledger wrongly refused")
    expect(not fts.path_is_forbidden(fts.OUT_DIR_DEFAULT), "new out dir wrongly refused")


def t_no_send_env_hardening():
    saved = {k: os.environ.get(k) for k in (fts.ENV_WEBHOOK,) + fts._BIRDEYE_ENV_KEYS}
    try:
        os.environ[fts.ENV_WEBHOOK] = "x"
        for k in fts._BIRDEYE_ENV_KEYS:
            os.environ[k] = "x"
        removed = fts.harden_no_send_env(allow_birdeye_fallback=False)
        expect(removed == 1 + len(fts._BIRDEYE_ENV_KEYS), f"removed={removed}")
        expect(fts.ENV_WEBHOOK not in os.environ, "webhook survived hardening")
        os.environ[fts.ENV_WEBHOOK] = "x"
        for k in fts._BIRDEYE_ENV_KEYS:
            os.environ[k] = "x"
        removed = fts.harden_no_send_env(allow_birdeye_fallback=True)
        expect(removed == 1 and all(k in os.environ for k in fts._BIRDEYE_ENV_KEYS),
               "fallback keys must survive when fallback allowed")
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def t_discord_arm_gate_refusals():
    with tempfile.TemporaryDirectory() as td:
        ledger = Path(td) / "ping_dedupe.jsonl"
        ledger.write_text("", encoding="utf-8")
        triple = ledgerlib.compute_baseline(str(ledger))
        baseline = triple.as_token()

        class A:  # minimal args carrier
            ack_live_free_tier = True
            i_understand_this_can_send = True
            confirm_token = fts.LOCKED_CONFIRM_TOKEN
            require_baseline = baseline
            ledger_path = str(ledger)

        saved = os.environ.get(fts.ENV_WEBHOOK)
        try:
            os.environ[fts.ENV_WEBHOOK] = "present"
            expect(fts.verify_discord_arm(A()) is None, "full gate should arm")
            a = A(); a.ack_live_free_tier = False
            expect("ACK" in (fts.verify_discord_arm(a) or ""), "missing ack not refused")
            a = A(); a.i_understand_this_can_send = False
            expect("ACK" in (fts.verify_discord_arm(a) or ""), "missing consent not refused")
            a = A(); a.confirm_token = "wrong"
            expect(fts.verify_discord_arm(a) == "CONFIRM_TOKEN_MISMATCH", "token not checked")
            a = A(); a.require_baseline = None
            expect(fts.verify_discord_arm(a) == "MISSING_REQUIRE_BASELINE", "baseline optional?")
            a = A(); a.require_baseline = "0" * 64 + ":1:1"
            expect(fts.verify_discord_arm(a) == "BASELINE_MISMATCH", "stale baseline accepted")
            os.environ.pop(fts.ENV_WEBHOOK, None)
            expect(fts.verify_discord_arm(A()) == "WEBHOOK_MISSING", "webhook not required")
        finally:
            if saved is None:
                os.environ.pop(fts.ENV_WEBHOOK, None)
            else:
                os.environ[fts.ENV_WEBHOOK] = saved


def t_provider_name_is_a_caught_needle():
    expect(not artifacts.scan_value_safe("api.dexscr" + "eener.com"),
           "provider hostname must be a caught needle")
    expect(not artifacts.scan_value_safe("bir" + "deye label"),
           "keyed-provider name must be a caught needle")
    expect(artifacts.scan_value_safe("FREE_TIER_MARKET basis REAL_MARKET_PRESENT"),
           "closed-set labels must be safe")


def t_error_ledger_shape():
    with tempfile.TemporaryDirectory() as td:
        el = fts.ErrorLedger(td)
        el.log("discovery", RuntimeError("boom with " + "https" + "://secret"))
        rec = json.loads((Path(td) / fts.ERRORS_BASENAME)
                         .read_text(encoding="utf-8").splitlines()[0])
        expect(rec["kind"] == "FREE_TIER_PRODUCER_ERROR" and rec["error_type"] == "RuntimeError",
               "error record malformed")
        expect("note" not in rec or "://" not in rec.get("note", ""), "error note leaked")
        expect(normalize_record(rec, "errors.jsonl", 1) is None,
               "error record must not become a paper snapshot")


def t_dedupe_suppresses_second_would_ping():
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        out1 = _e2e_engine(tmp)
        expect(out1["outcome"] == "ONE_SEND_COMMITTED", "first pass should commit")
        # Second pass over the SAME ledger: the first pass CONFIRMED delivery and
        # committed the successful-send row -> the duplicate suppresses.
        anchor = datetime.now(timezone.utc) - timedelta(seconds=_NOW_OFFSET_S)
        tr = make_transport(make_fake_urlopen(anchor=anchor))
        secret = build_free_tier_endpoint_secret()
        sidecar = Cap1MarketSidecar(transport=tr, endpoint_secret=secret, timeout_seconds=10,
                                    enabled=True, caps=Cap1MarketCaps())
        out2 = _run_activated_candidates(
            [{"token_mint": MINT, "candidate_id": "ft2", "migration_time_utc": _z(anchor),
              "source_ref": None, "symbol_or_name": None}],
            sidecar=sidecar, ath_transport=tr, ath_endpoint_secret=secret,
            now_utc=datetime.now(timezone.utc), now_seconds=make_constant_clock(Decimal(0)),
            now_iso_fn=lambda: _z(datetime.now(timezone.utc)), sleep_fn=lambda _s: None,
            ledger=JsonlPingDedupeLedger(path=tmp / "ping_dedupe.jsonl"),
            guard=None, authorization=None,
            created_at_utc=_z(datetime.now(timezone.utc)), pump_required=True)
        expect(out2["outcome"] == "ZERO_SEND", "dedupe did not suppress the second would-ping")
        lines = [ln for ln in (tmp / "ping_dedupe.jsonl")
                 .read_text(encoding="utf-8").splitlines() if ln.strip()]
        expect(len(lines) == 1, f"ledger grew on suppressed pass: {len(lines)}")


# --------------------------------------------------------------------------- credit budget


def _mk_budget(ws_exhaustion_latches: bool = True, **caps) -> FreeTierCreditBudget:
    base = dict(max_sends_per_run=3, max_raw_ws_notifications_total=120000, max_seed_windows=120,
                max_candidates_total=400, max_gettransaction_total=1024,
                max_market_requests_total=5000, max_429_total=5, max_consecutive_ws_errors=2,
                max_rpc_errors_total=12, max_polls_total=5000)
    base.update(caps)
    return FreeTierCreditBudget(FreeTierCreditBudgetCaps(**base), discord_enabled=False,
                                ws_exhaustion_latches=ws_exhaustion_latches)


def t_budget_send_cap_latches_and_raises():
    b = _mk_budget(max_sends_per_run=2)
    b.record_send_attempt(sent_ok=True)
    expect(not b.stop_requested, "stopped before the cap")
    b.check_and_raise()  # must NOT raise yet
    b.record_send_attempt(sent_ok=True)
    expect(b.stop_requested and b.stop_reason == BUDGET_STOP_SEND_CAP,
           f"send cap did not latch: {b.stop_reason}")
    try:
        b.check_and_raise()
        expect(False, "check_and_raise did not raise")
    except FreeTierBudgetExhausted as exc:
        expect(exc.reason == BUDGET_STOP_SEND_CAP, f"wrong raise reason {exc.reason}")
    snap = b.snapshot()
    for key in ("ws_notifications_seen", "seed_windows", "candidate_count", "would_ping_count",
                "private_ping_count", "market_requests", "429_count"):
        expect(key in snap, f"snapshot missing operator counter {key}")
    expect(snap["would_ping_count"] == 2 and snap["private_ping_count"] == 0,
           "no-send mode must report would-pings, not private pings")


def t_budget_window_allowance_shrinks_and_blocks():
    b = _mk_budget(max_raw_ws_notifications_total=100, max_gettransaction_total=30)
    a1 = b.window_allowance(per_window_notifications=80, per_window_gettransaction=64)
    expect(a1 == {"max_notifications": 80, "max_gettransaction": 30}, f"a1={a1}")
    b.record_window({"notifications_seen": 80, "gettransaction_fetches": 4}, accepted=2)
    a2 = b.window_allowance(per_window_notifications=80, per_window_gettransaction=64)
    expect(a2 == {"max_notifications": 20, "max_gettransaction": 26}, f"a2={a2}")
    b.record_window({"notifications_seen": 20, "gettransaction_fetches": 1}, accepted=0)
    expect(b.stop_requested and b.stop_reason == BUDGET_STOP_WS_NOTIFICATIONS,
           f"notification ceiling did not latch: {b.stop_reason}")
    expect(b.window_allowance(per_window_notifications=80,
                              per_window_gettransaction=64) is None,
           "exhausted budget still granted a window")
    expect(b.windows_blocked_by_budget == 1, "blocked-window counter not kept")
    expect(b.seed_windows == 2 and b.ws_notifications_seen == 100 and b.candidates_accepted == 2,
           "cumulative counters wrong")


def t_budget_throttle_tripwires():
    # 429 is a DEGRADATION signal, not a stop (2026-07-31 restart-state
    # remediation). Crossing max_429_total marks the provider degraded for the
    # health surface; it must never stop a producer whose other sources are
    # healthy, because the forced restart is what destroys candidate state.
    b = _mk_budget(max_429_total=2)
    b.observe_market({"http_calls_total": 10, "http_429": 1})
    expect(not b.rate_limit_degraded, "429 degradation marked early")
    expect(not b.stop_requested, "429 must never latch a stop")
    b.observe_market({"http_calls_total": 12, "http_429": 2})
    expect(b.rate_limit_degraded, "sustained 429 not marked degraded")
    expect(not b.stop_requested and b.stop_reason is None,
           f"429 must never stop the producer: {b.stop_reason}")
    expect(b.snapshot()["rate_limit"]["degraded"] is True,
           "429 degradation missing from the artifact snapshot")

    b2 = _mk_budget(max_consecutive_ws_errors=2)
    b2.record_window({"ws_error": True}, accepted=0)
    b2.record_window({"ws_error": False}, accepted=0)   # good window resets the streak
    b2.record_window({"ws_error": True}, accepted=0)
    expect(not b2.stop_requested, "non-consecutive ws errors tripped")
    b2.record_window({"ws_error": True}, accepted=0)
    expect(b2.stop_requested and b2.stop_reason == BUDGET_STOP_WS_SOURCE_DEGRADED,
           f"consecutive ws-error tripwire missed: {b2.stop_reason}")
    expect(b2.ws_error_windows == 3, "ws error window count wrong")

    b3 = _mk_budget(max_rpc_errors_total=3)
    b3.record_window({"rpc_errors": 2}, accepted=0)
    b3.record_window({"rpc_errors": 1}, accepted=0)
    expect(b3.stop_requested and b3.stop_reason == BUDGET_STOP_RPC_SOURCE_DEGRADED,
           f"rpc-error tripwire missed: {b3.stop_reason}")


def t_market_transport_counts_429():
    tr = make_transport(lambda _u, _t: (429, b""))
    res = tr.get(endpoint_secret=build_free_tier_endpoint_secret(), path=BIRDEYE_PATH_PRICE,
                 query_params={"address": MINT}, timeout_seconds=5)
    expect(res.refusal_reason != BIRDEYE_REFUSAL_REASON_NONE, "429 must be a refusal")
    stats = tr.stats()
    expect(stats["http_429"] == 1 and stats["http_errors"] == 1,
           f"429 not counted precisely: {stats}")


def t_budget_rewrite_and_verdict():
    ok_invariants = {"ledger_state_known": True, "artifact_state_known": True,
                     "ledger_consistent": True, "redaction_ok": True}
    b = _mk_budget(max_sends_per_run=1)
    b.record_send_attempt(sent_ok=True)
    runnerish = {"outcome": "SENDS_PERFORMED", "stop_reason": "UNEXPECTED_EXCEPTION",
                 "exception_type": "FreeTierBudgetExhausted", **ok_invariants,
                 "total_ledger_delta": 1, "reserve_count": 1, "sent_ok_count": 1}
    rewritten, tripped = rewrite_result_for_budget_stop(runnerish, b)
    expect(tripped and rewritten["stop_reason"] == BUDGET_STOP_PREFIX + BUDGET_STOP_SEND_CAP,
           f"rewrite failed: {rewritten['stop_reason']}")
    expect(rewritten["exception_type"] is None and rewritten["budget_stop"] is True,
           "rewrite fields wrong")
    verdict = verdict_for_budget_stop(production_postflight_verdict(rewritten), rewritten)
    expect(verdict["postflight_ok"] is True and verdict["exit_code"] == 0
           and verdict["budget_stop"] is True, f"budget verdict not clean: {verdict}")

    # A REAL unexpected exception must NOT be relabeled, even with a latched budget.
    real_exc = {**runnerish, "exception_type": "ValueError"}
    same, tripped2 = rewrite_result_for_budget_stop(real_exc, b)
    expect(not tripped2 and same["stop_reason"] == "UNEXPECTED_EXCEPTION",
           "real exception was relabeled")

    # A budget stop with a violated invariant must stay a nonzero investigate-me exit.
    dirty = {**runnerish, "redaction_ok": False}
    dirty_rw, _ = rewrite_result_for_budget_stop(dirty, b)
    dirty_verdict = verdict_for_budget_stop(production_postflight_verdict(dirty_rw), dirty_rw)
    expect(dirty_verdict["exit_code"] != 0, "violated invariant produced exit 0")


def t_loop_budget_send_cap_end_to_end():
    with tempfile.TemporaryDirectory() as td:
        b = _mk_budget(max_sends_per_run=1)
        result, out_dir = _run_loop_smoke(Path(td), budget=b, max_total_ticks=6)
        expect(result["sends"] == 1, f"sends={result['sends']}")
        expect(result["stop_reason"] == "UNEXPECTED_EXCEPTION"
               and result["exception_type"] == "FreeTierBudgetExhausted",
               f"budget raise did not stop the runner: {result['stop_reason']}")
        rewritten, tripped = rewrite_result_for_budget_stop(result, b)
        expect(tripped and rewritten["stop_reason"] == BUDGET_STOP_PREFIX + BUDGET_STOP_SEND_CAP,
               f"loop budget stop not relabeled: {rewritten['stop_reason']}")
        expect(rewritten["total_ledger_delta"] == 1 and rewritten["ledger_consistent"] is True,
               "ledger not consistent at budget stop")
        verdict = verdict_for_budget_stop(production_postflight_verdict(rewritten), rewritten)
        expect(verdict["postflight_ok"] is True and verdict["exit_code"] == 0,
               f"loop budget verdict not clean: {verdict}")
        expect(b.snapshot()["would_ping_count"] == 1, "budget send counter wrong")
        scan = artifacts.run_redaction_scan(str(out_dir))
        expect(scan["redaction_status"] == "REDACTED" and scan["total_unsafe_hits"] == 0,
               "redaction failed in budget-stop loop")


# --------------------------------------------------------------------------- main


# --------------------------------------------------------------------------- pump-suffix guard


class _Boom:
    """Sentinel that fails the test on ANY attribute access — proves a code path
    never touched market enrichment / ATH / ledger / guard / transport objects."""

    def __init__(self, label: str) -> None:
        object.__setattr__(self, "_boom_label", label)

    def __getattr__(self, name: str):
        raise AssertionError(
            f"forbidden touch: {object.__getattribute__(self, '_boom_label')}.{name}")


REAL_PUMP_MINT = "EkNbQMQYpd4JET5FpZrqbdkYdHXeqocZcBByJpFWpump"


def t_pump_guard_suffix_semantics():
    ok = fts._is_pump_mint
    expect(ok(REAL_PUMP_MINT) is True, "real pump-suffix mint must pass")
    expect(ok("B" * 40 + "pump") is True, "synthetic pump-suffix mint must pass")
    expect(ok("A" * 44) is False, "non-pump mint must fail")
    expect(ok("AAApumpBBBB") is False, "'pump' in the middle must fail")
    expect(ok("pumpAAAA") is False, "'pump' prefix must fail")
    expect(ok("A" * 40 + "PUMP") is False, "suffix match is exact/case-sensitive")
    expect(ok("") is False, "empty string must fail")
    expect(ok(None) is False, "None must fail")
    expect(ok(123) is False, "non-string must fail")
    expect(ok(b"AAAApump") is False, "bytes must fail (str only)")


def t_pump_guard_checks_actual_mint_not_pool_or_logs():
    pool_ending_pump = "P" * 40 + "pump"
    cands = [
        {   # pool address + provenance + log text all scream "pump", but the
            # ACTUAL token mint does not end with it -> must drop
            "token_mint": "A" * 44,
            "pool_address": pool_ending_pump,
            "source_ref": "helius:sig:pumppumppump:slot:1",
            "log_text": "Program log: Instruction: CreatePool pump",
            "candidate_id": "cap1_AAAAAAAA",
        },
        {   # actual mint ends with pump; pool does NOT -> accepted
            "token_mint": "B" * 40 + "pump",
            "pool_address": "Q" * 44,
            "candidate_id": "cap1_BBBBBBBB",
        },
    ]
    accepted, dropped = fts.guard_pump_suffix_candidates(cands)
    expect(len(accepted) == 1 and accepted[0]["token_mint"] == "B" * 40 + "pump",
           f"accepted={accepted!r}")
    expect(len(dropped) == 1 and dropped[0]["token_mint"] == "A" * 44,
           "pool/log 'pump' text must never rescue a non-pump token mint")


def t_pump_guard_drops_malformed_candidates_safely():
    accepted, dropped = fts.guard_pump_suffix_candidates(
        [None, "not-a-dict", {}, {"token_mint": ""}, {"token_mint": None},
         {"token_mint": 42}, {"token_mint": "C" * 40 + "pump"}])
    expect(len(accepted) == 1 and accepted[0]["token_mint"] == "C" * 40 + "pump",
           f"only the pump candidate may pass: {accepted!r}")
    expect(len(dropped) == 6, f"malformed candidates must drop safely: {len(dropped)}")
    accepted2, dropped2 = fts.guard_pump_suffix_candidates(None)
    expect(accepted2 == [] and dropped2 == [], "None input must yield empty split")


def t_pump_guard_non_pump_never_reaches_watchlist_or_watch_state():
    cands = [
        {"token_mint": "B" * 40 + "pump", "candidate_id": "cap1_BBBBBBBB",
         "migration_time_utc": "2026-01-01T00:00:00Z", "source_ref": "helius:sig:b:slot:2"},
        {"token_mint": "A" * 44, "candidate_id": "cap1_AAAAAAAA",
         "migration_time_utc": "2026-01-01T00:00:00Z", "source_ref": "helius:sig:a:slot:1"},
    ]
    accepted, dropped = fts.guard_pump_suffix_candidates(cands)
    expect(len(dropped) == 1, "non-pump candidate must be guard-dropped")
    wl = Watchlist(max_size=8)
    for cand in accepted:   # mirrors the producer: ONLY guarded candidates are seeded
        wl.seed(cand, seeded_at_utc="2026-01-01T00:00:01Z")
    summary = wl.summary()
    expect(summary["total"] == 1, f"watchlist must hold only the pump mint: {summary}")
    expect("DROPPED_NON_PUMP" not in (summary.get("by_status") or {}),
           f"guard-dropped mints must never appear in watch_state: {summary}")
    with tempfile.TemporaryDirectory() as td:
        ws_path = Path(td) / "watch_state.jsonl"
        wl.persist(ws_path)
        text = ws_path.read_text(encoding="utf-8")
        expect(("B" * 40 + "pump") in text, "pump mint must persist to watch_state")
        # watch_state.jsonl + candidates/*.jsonl are the paper engine's inputs —
        # absence here IS the no-paper-snapshot guarantee.
        expect(("A" * 44) not in text,
               "non-pump mint must never enter watch_state / paper tracking")


def t_watchlist_capacity_counts_active_only_and_archives_terminal():
    # PHX2-E2E-002: capacity bounds concurrently ACTIVE candidates; terminal
    # history is archived durably and never exhausts the lifetime process.
    with tempfile.TemporaryDirectory() as td:
        history = Path(td) / "watch_terminal_history.jsonl"
        wl = Watchlist(max_size=2, terminal_history_path=history)
        for i in range(2):
            entry, outcome = wl.seed_with_outcome(
                {"token_mint": f"CapSelf{i:02d}pump", "candidate_id": f"c{i}"},
                seeded_at_utc="2026-01-01T00:00:01Z")
            expect(entry is not None and outcome == "ADMITTED",
                   f"seed {i} outcome={outcome!r}")
        blocked, outcome = wl.seed_with_outcome(
            {"token_mint": "CapSelf99pump", "candidate_id": "c99"},
            seeded_at_utc="2026-01-01T00:00:02Z")
        expect(blocked is None and outcome == "ACTIVE_WATCH_CAPACITY_REACHED",
               f"full ACTIVE watchlist must reject explicitly: {outcome!r}")
        expired = wl.expire_stale_entries(
            now_age_seconds_fn=lambda _s: 999999.0, max_age_seconds=1,
            max_rechecks=999999, now_utc="2026-01-01T01:00:00Z")
        expect(len(expired) == 2, f"expired={len(expired)}")
        summary = wl.summary()
        expect(summary["active"] == 0 and summary["terminal_history"] == 2,
               f"terminal history must not consume active capacity: {summary}")
        expect(summary["watchlist_count"] == 0,
               "WATCHLIST_COUNT must report the active/tracked count")
        entry, outcome = wl.seed_with_outcome(
            {"token_mint": "CapSelf99pump", "candidate_id": "c99"},
            seeded_at_utc="2026-01-01T01:00:01Z")
        expect(entry is not None and outcome == "ADMITTED",
               f"slot must be reusable after terminal archive: {outcome!r}")
        lines = [ln for ln in history.read_text(encoding="utf-8").splitlines()
                 if ln.strip()]
        expect(len(lines) == 2, "terminal history rows must be durably archived")


def t_checkpoint_corrupt_both_quarantines_not_empty():
    # PHX2-E2E-005: an existing checkpoint with invalid content is NEVER
    # treated as "no checkpoint exists". Corrupt primary+backup quarantines:
    # no empty healthy state, no admissions, no rewrite of the evidence.
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        watch = base / "watch_state.jsonl"
        watch.write_text("{not-json\n", encoding="utf-8")
        (base / "watch_state.jsonl.bak").write_text("{not-json\n", encoding="utf-8")
        wl = Watchlist.load(watch, max_size=8,
                            terminal_history_path=base / "th.jsonl")
        expect(wl.checkpoint_quarantined, "corrupt both must quarantine")
        expect(wl.summary()["checkpoint_status"] == "CHECKPOINT_QUARANTINED",
               "summary must expose the quarantine, not an empty watchlist")
        blocked, outcome = wl.seed_with_outcome(
            {"token_mint": "Q" * 40 + "pump", "candidate_id": "q"},
            seeded_at_utc="2026-01-01T00:00:00Z")
        expect(blocked is None and outcome == "CHECKPOINT_QUARANTINED",
               f"quarantined watchlist must refuse admission: {outcome!r}")
        wl.persist(watch)
        expect(watch.read_text(encoding="utf-8") == "{not-json\n",
               "quarantine must preserve the corrupt evidence unchanged")
        ath_dir = base / "ath"
        ath_dir.mkdir()
        (ath_dir / "ath_state.json").write_text("{not-json\n", encoding="utf-8")
        (ath_dir / "ath_state_checkpoint.json").write_text(
            "{not-json\n", encoding="utf-8")
        store = CentralAthStateStore(ath_dir)
        expect(store.checkpoint_quarantined, "corrupt ATH pair must quarantine")
        expect(len(store.all_snapshots()) == 0
               and store.checkpoint.checkpoint_status == "CHECKPOINT_QUARANTINED",
               "quarantined ATH must expose zero AUTHORIZED records + status")
        expect(not store.observe_provider_current(
            mint="Q" * 40 + "pump", price_usd="1", market_cap_usd="5",
            observed_at="2026-01-01T00:00:00Z"),
            "quarantined ATH store must refuse observations")


def t_stream_cursor_survives_restart_and_suppresses_replay_overlap():
    # PHX2-E2E-008: the durable resume position must outlive the process and
    # recognise a replayed event by exact identity. In-memory dedupe cannot:
    # a restart clears it, and a replayed migration would look brand new.
    from PHX2.free_tier_producer.stream_cursor import (
        CURSOR_PRIMARY_BASENAME, STREAM_SOURCE_YELLOWSTONE, build_cursor_store,
        build_stream_event_identity, compute_subscription_identity_digest,
    )
    digest = compute_subscription_identity_digest(
        source_kind=STREAM_SOURCE_YELLOWSTONE, commitment="CONFIRMED",
        transaction_filter_name="stage29_3_pumpswap",
        account_include=["PSwapProgram"], program_id="PSwapProgram",
        migration_versions_supported=["migrate", "migrate_v2"],
        decoder_schema_version="v1")
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        first = build_cursor_store(state_dir=base,
                                   subscription_identity_digest=digest)
        expect(first.load().checkpoint_status == "CHECKPOINT_NOT_FOUND",
               "a genuinely new state dir must report NOT_FOUND")
        expect(first.resume_from_slot() is None,
               "no committed position means no resume request")
        one = build_stream_event_identity(
            slot=500, signature="SigOne", transaction_index=0,
            migration_version="migrate_v2", mint="A" * 40 + "pump", pool="P1")
        two = build_stream_event_identity(
            slot=500, signature="SigTwo", transaction_index=1,
            migration_version="migrate", mint="B" * 40 + "pump", pool="P2")
        expect(one != two,
               "two migrations in ONE slot must have distinct identities")
        first.commit_event(slot=500, identity=one, signature="SigOne")
        first.commit_event(slot=500, identity=two, signature="SigTwo")
        first.mark_disconnect()

        # a brand-new process over the same state directory
        restarted = build_cursor_store(state_dir=base,
                                       subscription_identity_digest=digest)
        restarted.load()
        expect(restarted.resume_from_slot() == 500,
               "restart must resume from the durable slot, not the live head")
        expect(restarted.is_duplicate(one) and restarted.is_duplicate(two),
               "both boundary-slot identities must survive the restart")
        expect(restarted.state.recovery_required,
               "an unresolved gap must still be claimed after a restart")
        expect(restarted.snapshot()["grpc_gap_unresolved"] is True,
               "the unresolved gap must be observable")

        # a changed subscription must NOT blindly reuse the old position
        changed = build_cursor_store(state_dir=base,
                                     subscription_identity_digest="d" * 64)
        changed.load()
        expect(changed.subscription_identity_matches is False,
               "a changed subscription identity must be detected")
        expect(changed.resume_from_slot() is None,
               "identity mismatch must refuse a blind resume")

        # corrupt BOTH generations: quarantine + write lockdown, never "new"
        primary = base / CURSOR_PRIMARY_BASENAME
        primary.write_text("{not-json\n", encoding="utf-8")
        Path(str(primary) + ".bak").write_text("{not-json\n", encoding="utf-8")
        broken = build_cursor_store(state_dir=base,
                                    subscription_identity_digest=digest)
        result = broken.load()
        expect(result.checkpoint_status == "CHECKPOINT_QUARANTINED",
               "a corrupt cursor pair must quarantine")
        expect(result.checkpoint_files_found is True,
               "corrupt is NEVER the same observable state as missing")
        expect(broken.resume_from_slot() is None,
               "a quarantined cursor must not hand out a resume position")
        try:
            broken.persist()
            raise AssertionError("quarantined cursor must refuse to persist")
        except Exception as exc:
            expect(type(exc).__name__ == "StreamCursorWriteError",
                   f"expected a cursor write refusal, got {type(exc).__name__}")
        expect(primary.read_text(encoding="utf-8") == "{not-json\n",
               "quarantine must preserve the corrupt evidence unchanged")


def t_stream_cursor_reconnect_requests_replay_not_the_live_head():
    # PHX2-E2E-008: the reconnect request must carry the resume position.
    # Before the fix every reconnect rebuilt an identical tip-anchored
    # request, so the provider legitimately restarted at the live head and
    # every slot in between was never delivered at all.
    from PHX2.stage29.stage29_3_hint_aware_event_source import (
        build_pumpswap_subscribe_request,
    )
    tip = build_pumpswap_subscribe_request()
    expect(tip.HasField("from_slot") is False,
           "a genuinely new subscription carries no resume position")
    resumed = build_pumpswap_subscribe_request(from_slot=987654)
    expect(resumed.HasField("from_slot") and resumed.from_slot == 987654,
           "a reconnect must carry the exact durable resume slot")
    expect(resumed.commitment == tip.commitment,
           "resuming must not change the subscription's commitment")
    for name, tx_filter in resumed.transactions.items():
        expect(tx_filter.vote is False and tx_filter.failed is False,
               f"resume must not widen the {name} filter")
    for bad in (-1, True, "100"):
        try:
            build_pumpswap_subscribe_request(from_slot=bad)
            raise AssertionError(f"from_slot={bad!r} must be refused")
        except ValueError:
            pass


def t_stream_cursor_holds_when_the_downstream_handoff_is_not_durable():
    # PHX2-E2E-008 ordering invariant: the position advances only AFTER the
    # event is recoverable downstream. The reverse ordering (cursor committed,
    # handoff lost) must be impossible by construction.
    from PHX2.free_tier_producer.stream_cursor import (
        STREAM_SOURCE_YELLOWSTONE, build_cursor_store,
        compute_subscription_identity_digest,
    )
    digest = compute_subscription_identity_digest(
        source_kind=STREAM_SOURCE_YELLOWSTONE, commitment="CONFIRMED",
        transaction_filter_name="stage29_3_pumpswap",
        account_include=["PSwapProgram"], program_id="PSwapProgram",
        migration_versions_supported=["migrate", "migrate_v2"],
        decoder_schema_version="v1")
    with tempfile.TemporaryDirectory() as td:
        store = build_cursor_store(state_dir=Path(td),
                                   subscription_identity_digest=digest)
        store.load()
        store.commit_event(slot=100, identity="100|A|-|-|-|-|-|-|-",
                           signature="A")
        expect(store.resume_from_slot() == 100, "first commit must advance")
        # a replayed event BELOW the committed position must never rewind it
        store.commit_event(slot=90, identity="90|B|-|-|-|-|-|-|-",
                           signature="B", replayed=True)
        expect(store.resume_from_slot() == 100,
               "the durable position must never regress on replay overlap")
        expect(store.state.replayed_event_count == 1,
               "replayed events must be counted exactly once")
        snapshot = store.snapshot()
        text = json.dumps(snapshot, sort_keys=True).lower()
        # Assembled in pieces so THIS source file carries no danger needle of
        # its own (the same discipline the production scanner uses for its
        # positive control): a bare needle here would trip source-level
        # boundary scans on a file that holds no secret at all.
        needles = ("x-" + "token", "author" + "ization", "bear" + "er",
                   "https" + "://", "api-" + "key")
        for needle in needles:
            expect(needle not in text,
                   f"cursor telemetry must stay redaction-safe: {needle}")


def t_checkpoint_legacy_activation_migrates_and_requires_fresh_tick():
    # PHX2-E2E-005: a legacy ACTIVE_DIP_WATCH checkpoint (no current proof
    # fields) migrates to an authenticated legacy activation proof instead of
    # downgrading to PENDING_1_20X; the migration tick can never compose.
    mint = "LegacySelf0000000000000000000000000000pump"
    legacy = {
        "token_mint": mint, "candidate_id": "legacy_c1",
        "migration_time_utc": "2026-01-01T00:00:00Z", "source_ref": "proof",
        "seeded_at_utc": "2026-01-01T00:00:05Z", "status": "ACTIVE_DIP_WATCH",
        "migration_baseline_status": "CAPTURED",
        "migration_market_cap_usd": "100", "migration_market_cap_price": "0.0001",
        "migration_market_cap_source": "PAID_MARKET_PRIMARY_FALLBACK",
        "migration_market_cap_observed_at_utc": "2026-01-01T00:00:10Z",
        "activation_multiplier": "1.20",
        "activation_target_market_cap_usd": "120.00",
        "activated_at_utc": "2026-01-01T00:01:00Z",
        "activation_observation_source": "PAID_MARKET_PRIMARY",
        "activation_current_market_cap_usd": "130",
        "activation_observation_fresh": True, "activation_proven": True,
    }
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        watch = base / "watch_state.jsonl"
        watch.write_text(json.dumps(legacy) + "\n", encoding="utf-8")
        wl = Watchlist.load(watch, max_size=8,
                            terminal_history_path=base / "th.jsonl",
                            now_utc="2026-01-02T00:00:00Z")
        entry = wl.get(mint)
        expect(entry is not None
               and entry.status == "ACTIVATED_WAITING_FOR_FRESH_MARKET",
               f"legacy activation must migrate, not downgrade: "
               f"{None if entry is None else entry.status!r}")
        expect(entry.activation_evidence_kind == ACTIVATION_KIND_LEGACY_MIGRATION,
               "migrated proof must be explicitly legacy-derived")
        expect(activation_proof_is_durable(entry),
               "migrated proof must validate durably")
        expect(not activation_proof_is_eligible(entry),
               "migration tick must NEVER be compose/reserve/send eligible")
        reloaded = Watchlist.load(watch, max_size=8,
                                  terminal_history_path=base / "th2.jsonl")
        expect(reloaded.checkpoint.checkpoint_status
               in ("CHECKPOINT_PRIMARY_OK", "CHECKPOINT_PRIMARY_AND_BACKUP_OK"),
               "migration must install the current authenticated schema")
        expect(activation_proof_is_durable(reloaded.get(mint)),
               "migrated activation must survive a second restart")


def t_checkpoint_tampered_lower_ath_never_restores():
    # PHX2-E2E-005: a tampered lower ATH with a zeroed digest must never
    # restore — the valid backup generation wins, else quarantine.
    mint = "TamperSelf0000000000000000000000000000pump"
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        store = CentralAthStateStore(base)
        expect(store.observe_provider_current(
            mint=mint, price_usd="0.00005", market_cap_usd="50000",
            observed_at="2026-01-01T00:00:00Z", confirmed=True),
            "seed observation refused")
        expect(store.observe_provider_current(
            mint=mint, price_usd="0.000051", market_cap_usd="51000",
            observed_at="2026-01-01T00:01:00Z", confirmed=True),
            "second observation refused")   # rotates a valid backup generation
        tampered = {
            "schema_version": "phx2_central_ath_v1",
            "artifact_kind": "CENTRAL_ATH_RESTART_CHECKPOINT",
            "updated_at": "2026-01-01T00:02:00Z",
            "mints": {mint: {
                "ath_price": "0.000001", "ath_market_cap": "1000",
                "ath_timestamp": "2026-01-01T00:02:00Z",
                "ath_provider": "PAID_CURRENT_PRICE",
                "ath_observation_type": "PAID_CURRENT_PRICE",
                "ath_status": "CONFIRMED",
                "ath_evidence_version": "phx2_central_ath_evidence_v2",
                "ath_evidence_digest": "0" * 64,
                "ath_ingested_at_utc": "2026-01-01T00:02:01Z",
            }},
        }
        (base / "ath_state_checkpoint.json").write_text(
            json.dumps(tampered), encoding="utf-8")
        recovered = CentralAthStateStore(base)
        snap = recovered.snapshot(mint)
        expect(snap is not None and snap["ath_market_cap"] in ("50000", "51000"),
               f"tampered 1000 must never restore: {None if snap is None else snap['ath_market_cap']!r}")
        expect(recovered.checkpoint.checkpoint_status
               != "CHECKPOINT_NOT_FOUND", "tamper must be visible")
        # with NO valid generation left, quarantine — never the tampered value
        lone = base / "lone"
        lone.mkdir()
        (lone / "ath_state_checkpoint.json").write_text(
            json.dumps(tampered), encoding="utf-8")
        q = CentralAthStateStore(lone)
        expect(q.checkpoint_quarantined and q.snapshot(mint) is None,
               "tampered-only state must quarantine, not restore 1000")


def t_pump_guard_non_pump_never_enriches_reserves_or_pings():
    out = _run_activated_candidates(
        [{"token_mint": "A" * 44, "candidate_id": "cap1_AAAAAAAA"}],
        sidecar=_Boom("market_sidecar"),          # any touch = market enrichment -> fail
        ath_transport=_Boom("ath_transport"),
        ath_endpoint_secret=_Boom("ath_endpoint_secret"),
        now_utc=_Boom("now_utc"),
        now_seconds=_Boom("now_seconds"),
        now_iso_fn=lambda: "2026-01-01T00:00:00Z",
        sleep_fn=lambda _s: None,
        ledger=_Boom("dedupe_ledger"),            # any touch = reserve attempt -> fail
        guard=_Boom("send_guard"),                # any touch = send path -> fail
        authorization=_Boom("authorization"),
        created_at_utc="2026-01-01T00:00:00Z",
    )
    per = out.get("per_candidate") or []
    expect(len(per) == 1 and per[0].get("reason") == "NOT_PUMP_SUFFIX",
           f"engine must refuse non-pump BEFORE enrichment: {per!r}")
    expect(out.get("sent_attempt") is None, "no send attempt may exist for non-pump")
    expect(out.get("outcome") == "ZERO_SEND", f"outcome={out.get('outcome')!r}")


# --------------------------------------------------------------------------- raw-WS semantics + profiles


def t_raw_ws_cap_is_raw_message_cap_not_credits():
    caps = FreeTierCreditBudgetCaps(max_raw_ws_notifications_total=777)
    expect(caps.max_ws_notifications_total == 777, "legacy read alias broken")
    d = caps.to_dict()
    expect(d["max_raw_ws_notifications_total"] == 777
           and d["max_ws_notifications_total"] == 777,
           "to_dict must carry canonical + legacy alias")
    b = FreeTierCreditBudget(caps, discord_enabled=False)
    snap = b.snapshot()
    expect(snap["raw_ws_notifications_seen"] == snap["ws_notifications_seen"] == 0,
           "raw alias counter missing")
    expect(snap["raw_ws_notifications_are_not_helius_credits"] is True,
           "not-credits marker missing from snapshot")
    expect(snap["raw_ws_cap_note"] == RAW_WS_CAP_NOTE and "credit" in RAW_WS_CAP_NOTE.lower(),
           "raw cap note missing/weak")
    expect(artifacts.scan_value_safe(RAW_WS_CAP_NOTE), "raw cap note must be redaction-safe")


def _profile_args(profile=None, discovery_mode=None, **explicit):
    class _A:
        pass
    a = _A()
    a.profile = profile
    a.discovery_mode = discovery_mode
    for key in fts.PROFILE_BASE_DEFAULTS:
        setattr(a, key, explicit.get(key))
    return a


def t_profiles_live_2h_does_not_use_old_raw_cap():
    eff = fts.resolve_effective_settings(_profile_args("live_2h"))
    expect(eff["max_raw_ws_notifications_total"] >= 1_800_000,
           f"live_2h raw cap too small: {eff['max_raw_ws_notifications_total']}")
    expect(eff["max_raw_ws_notifications_total"] != 120000,
           "live_2h must not keep the old 120000 raw cap")
    expect(eff["max_runtime_seconds"] == 7200.0, "live_2h runtime wrong")
    eff4 = fts.resolve_effective_settings(_profile_args("live_4h"))
    expect(eff4["max_raw_ws_notifications_total"] >= 3_600_000
           and eff4["max_runtime_seconds"] == 14400.0, "live_4h profile wrong")
    effs = fts.resolve_effective_settings(_profile_args("short_test_10m"))
    expect(effs["max_runtime_seconds"] == 600.0, "short_test_10m runtime wrong")
    # Protective caps survive in every profile.
    for eff_x in (eff, eff4, effs):
        for key in ("max_runtime_seconds", "max_429_total", "max_rpc_errors_total",
                    "max_gettransaction_total", "max_market_requests_total",
                    "max_sends_per_run"):
            expect(eff_x[key] is not None and eff_x[key] > 0, f"protective cap {key} lost")


def t_profiles_explicit_flag_wins_and_bad_profile_refused():
    eff = fts.resolve_effective_settings(
        _profile_args("live_2h", max_raw_ws_notifications_total=123456,
                      reseed_interval_seconds=99.0))
    expect(eff["max_raw_ws_notifications_total"] == 123456, "explicit raw cap must win")
    expect(eff["reseed_interval_seconds"] == 99.0, "explicit reseed must win")
    # Mode-aware reseed defaults when neither flag nor profile sets one.
    expect(fts.resolve_effective_settings(_profile_args())["reseed_interval_seconds"] == 240.0,
           "ws reseed default wrong")
    expect(fts.resolve_effective_settings(
        _profile_args(discovery_mode="polling"))["reseed_interval_seconds"] == 60.0,
        "polling reseed default wrong")
    expect(fts.resolve_effective_settings(
        _profile_args(discovery_mode="hybrid"))["reseed_interval_seconds"] == 120.0,
        "hybrid reseed default wrong")
    try:
        fts.resolve_effective_settings(_profile_args("nonsense_profile"))
        expect(False, "unknown profile accepted")
    except ValueError:
        pass
    try:
        fts.resolve_effective_settings(_profile_args(discovery_mode="carrier-pigeon"))
        expect(False, "unknown discovery mode accepted")
    except ValueError:
        pass


def t_hybrid_ws_exhaustion_downgrades_not_stops():
    b = _mk_budget(ws_exhaustion_latches=False, max_raw_ws_notifications_total=100)
    b.record_window({"notifications_seen": 100}, accepted=0)
    expect(not b.stop_requested,
           "HYBRID: crossing the raw-WS cap must NOT latch a run stop")
    expect(b.window_allowance(per_window_notifications=10, per_window_gettransaction=10) is None,
           "HYBRID: exhausted raw-WS budget must still refuse new WS windows")
    expect(not b.stop_requested, "HYBRID: refused WS window must not latch a stop")
    expect(b.raw_ws_remaining() == 0, "raw_ws_remaining wrong")
    allowance = b.polling_allowance(per_poll_gettransaction=4)
    expect(allowance == {"max_gettransaction": 4},
           "polling must continue after WS budget exhaustion in HYBRID")
    # ws mode keeps the legacy latch.
    b2 = _mk_budget(max_raw_ws_notifications_total=100)
    b2.record_window({"notifications_seen": 100}, accepted=0)
    expect(b2.stop_requested and b2.stop_reason == BUDGET_STOP_WS_NOTIFICATIONS,
           "ws mode must keep latching on raw-WS exhaustion")


def t_profiles_low_credit_polling_by_default():
    eff = fts.resolve_effective_settings(_profile_args("live_2h_low_credit"))
    live2h = fts.resolve_effective_settings(_profile_args("live_2h"))
    # 1) polling by default (no broad WS firehose) — the core credit lever.
    expect(eff["discovery_mode"] == "polling",
           f"low_credit must default to polling, got {eff['discovery_mode']!r}")
    expect(eff["max_runtime_seconds"] == 7200.0, "low_credit runtime must stay 7200")
    # 2) tighter than live_2h on every Helius/market spend lever.
    expect(eff["max_gettransaction_total"] < live2h["max_gettransaction_total"],
           "low_credit getTransaction cap must be lower than live_2h")
    expect(eff["max_raw_ws_notifications_total"] <= 120000,
           "low_credit raw-WS cap must stay small (firehose off by default)")
    expect(eff["max_polls_total"] < live2h["max_polls_total"],
           "low_credit poll cap must bound cumulative getSignaturesForAddress volume")
    expect(eff["poll_pools_per_cycle"] < 8 and eff["poll_max_gettransaction_per_cycle"] < 8,
           "low_credit must bound per-poll pools + getTransaction")
    expect(eff["poll_sig_page_limit"] < 1000, "low_credit must shrink the getSig page size")
    expect(eff["max_market_requests_total"] < live2h["max_market_requests_total"],
           "low_credit market-request cap must be bounded")
    expect(eff["market_refresh_max_calls_per_token"] < 4,
           "low_credit market refresh must be bounded")
    # 3) safety posture preserved: a real send cap and a low 429 tripwire survive.
    expect(eff["max_sends_per_run"] >= 1 and eff["max_429_total"] <= 8,
           "low_credit must keep a safe send cap and a low 429 tripwire")
    # 4) an explicit --discovery-mode still beats the profile's polling default.
    forced = fts.resolve_effective_settings(
        _profile_args("live_2h_low_credit", discovery_mode="ws"))
    expect(forced["discovery_mode"] == "ws", "explicit --discovery-mode must beat profile mode")


def t_profiles_hybrid_thin_shape():
    eff = fts.resolve_effective_settings(_profile_args("live_2h_hybrid_thin"))
    live2h = fts.resolve_effective_settings(_profile_args("live_2h"))
    expect(eff["discovery_mode"] == "hybrid", "hybrid_thin must default to hybrid")
    expect(eff["max_raw_ws_notifications_total"] < live2h["max_raw_ws_notifications_total"],
           "hybrid_thin raw-WS budget must be far smaller than live_2h")
    expect(eff["ws_window_every_n_reseeds"] > 1,
           "hybrid_thin must open WS windows only occasionally (every Nth reseed, N>1)")
    expect(eff["max_runtime_seconds"] == 7200.0, "hybrid_thin runtime must stay 7200")


# --------------------------------------------------------------------------- polling discovery


from PHX2.tests.stage29._stage_29_5_7_helius_fixtures import (  # noqa: E402
    make_migration_envelope,
)

POLL_PUMP_MINT = "B" * 40 + "pump"
POLL_NON_PUMP_MINT = "N" * 44
POOL_A = "P" * 40 + "AAAA"
POOL_B = "Q" * 40 + "BBBB"
SIG_A = "SigA" + "1" * 84
SIG_B = "SigB" + "2" * 84


def _gt_listing_body(pools):
    return json.dumps({"data": [
        {"id": "solana_" + p["pool"], "type": "pool",
         "attributes": {"address": p["pool"],
                        "pool_created_at": p.get("created")
                        or _z(datetime.now(timezone.utc))},
         "relationships": {
             "base_token": {"data": {"id": "solana_" + p["base"], "type": "token"}},
             "dex": {"data": {"id": p.get("dex", "pumpswap"), "type": "dex"}}}}
        for p in pools]}).encode("utf-8")


class _FakePollingNet:
    """Canned listing + RPC endpoints for the poller (no socket)."""

    def __init__(self, pools, sig_pages, txs, *, listing_status=200, rpc_status=200):
        self.pools = pools
        self.sig_pages = sig_pages
        self.txs = txs
        self.listing_status = listing_status
        self.rpc_status = rpc_status
        self.listing_calls = 0
        self.rpc_calls = []

    def urlopen(self, url, timeout):
        self.listing_calls += 1
        if self.listing_status != 200:
            return self.listing_status, b""
        return 200, _gt_listing_body(self.pools)

    def rpc_post(self, rpc_url, method, params, timeout):
        self.rpc_calls.append((method, params[0]))
        if self.rpc_status != 200:
            return self.rpc_status, None
        if method == "getSignaturesForAddress":
            return 200, list(self.sig_pages.get(params[0], []))
        if method == "getTransaction":
            return 200, self.txs.get(params[0])
        return 200, None


def _mk_poller(net, tmp=None, **caps):
    base = dict(max_pools_per_poll=8, sig_page_limit=1000,
                max_gettransaction_per_poll=8, max_pool_age_seconds=1800)
    base.update(caps)
    return FreeTierPollingDiscovery(
        rpc_url="rpc-held-privately", caps=FreeTierPollingCaps(**base),
        urlopen_fn=net.urlopen, rpc_post_fn=net.rpc_post,
        state_path=(str(Path(tmp) / "polling_seen.jsonl") if tmp else None))


def t_polling_extracts_actual_mint_not_pool_or_log_text():
    # Pool address does NOT end in pump; the create_pool BASE mint does. The candidate mint must
    # be the normalizer-extracted BASE mint — never the pool / listing / log text.
    env = make_migration_envelope(base_mint=POLL_PUMP_MINT, pool=POOL_A, signature=SIG_A)
    net = _FakePollingNet(
        pools=[{"pool": POOL_A, "base": POLL_PUMP_MINT}],
        sig_pages={POOL_A: [{"signature": SIG_A, "err": None}]},
        txs={SIG_A: env})
    out = _mk_poller(net).poll(created_at_utc="2026-07-10T00:00:00Z",
                               max_gettransaction_allowance=8)
    stats = out["stats"]
    expect(stats["create_pool_candidates"] == 1 and stats["transactions_fetched"] == 1,
           f"polling stats wrong: {stats}")
    cands = out["candidates"]
    expect(len(cands) == 1 and cands[0]["token_mint"] == POLL_PUMP_MINT,
           f"extracted mint wrong: {cands!r}")
    expect(cands[0]["token_mint"] != POOL_A, "pool address must never be the candidate mint")
    expect(cands[0].get("migration_time_utc"), "migration time missing from polled candidate")
    # Inverse: pool ends 'pump' but the ACTUAL base mint does not -> the extraction still returns
    # the real (non-pump) mint, and the strict guard drops it before any watchlist.
    pool_pumpish = "R" * 40 + "pump"
    sig2 = "SigC" + "3" * 84
    env2 = make_migration_envelope(base_mint=POLL_NON_PUMP_MINT, pool=pool_pumpish,
                                   signature=sig2)
    net2 = _FakePollingNet(
        pools=[{"pool": pool_pumpish, "base": POLL_NON_PUMP_MINT}],
        sig_pages={pool_pumpish: [{"signature": sig2, "err": None}]},
        txs={sig2: env2})
    # listing pre-check OFF so the chain extraction itself is what proves the mint.
    out2 = FreeTierPollingDiscovery(
        rpc_url="rpc-held-privately", caps=FreeTierPollingCaps(),
        urlopen_fn=net2.urlopen, rpc_post_fn=net2.rpc_post,
        listing_pump_suffix_precheck=False).poll(
            created_at_utc="2026-07-10T00:00:00Z", max_gettransaction_allowance=8)
    cands2 = out2["candidates"]
    expect(len(cands2) == 1 and cands2[0]["token_mint"] == POLL_NON_PUMP_MINT,
           f"non-pump extraction wrong: {cands2!r}")
    accepted, dropped = fts.guard_pump_suffix_candidates(cands2)
    expect(accepted == [] and len(dropped) == 1,
           "pump guard must drop the pump-named-pool/non-pump-mint candidate pre-watchlist")


def t_polling_dedupes_signatures_and_pools_durably():
    env = make_migration_envelope(base_mint=POLL_PUMP_MINT, pool=POOL_A, signature=SIG_A)
    with tempfile.TemporaryDirectory() as td:
        net = _FakePollingNet(
            pools=[{"pool": POOL_A, "base": POLL_PUMP_MINT}],
            sig_pages={POOL_A: [{"signature": SIG_A, "err": None}]},
            txs={SIG_A: env})
        poller = _mk_poller(net, tmp=td)
        out1 = poller.poll(created_at_utc="2026-07-10T00:00:00Z",
                           max_gettransaction_allowance=8)
        expect(len(out1["candidates"]) == 1, "first poll must yield the candidate")
        out2 = poller.poll(created_at_utc="2026-07-10T00:01:00Z",
                           max_gettransaction_allowance=8)
        s2 = out2["stats"]
        expect(out2["candidates"] == [] and s2["pools_new"] == 0
               and s2["signatures_new"] == 0 and s2["transactions_fetched"] == 0,
               f"second poll must dedupe entirely: {s2}")
        tx_calls = [c for c in net.rpc_calls if c[0] == "getTransaction"]
        expect(len(tx_calls) == 1, f"creation tx fetched more than once: {tx_calls}")
        # Restart-safe: a NEW poller over the same state file stays deduped.
        net2 = _FakePollingNet(
            pools=[{"pool": POOL_A, "base": POLL_PUMP_MINT}],
            sig_pages={POOL_A: [{"signature": SIG_A, "err": None}]},
            txs={SIG_A: env})
        poller2 = _mk_poller(net2, tmp=td)
        out3 = poller2.poll(created_at_utc="2026-07-10T00:02:00Z",
                            max_gettransaction_allowance=8)
        expect(out3["candidates"] == [] and out3["stats"]["transactions_fetched"] == 0,
               "dedupe state must survive a restart")
        for line in (Path(td) / "polling_seen.jsonl").read_text(
                encoding="utf-8").splitlines():
            expect(artifacts.scan_value_safe(line), f"polling_seen line unsafe: {line[:40]}")


def t_polling_respects_gettransaction_caps():
    pools = []
    sig_pages = {}
    txs = {}
    for i in range(5):
        pool = f"Pool{i}" + "X" * 38
        sig = f"Sig{i}" + "Y" * 84
        pools.append({"pool": pool, "base": POLL_PUMP_MINT})
        sig_pages[pool] = [{"signature": sig, "err": None}]
        txs[sig] = make_migration_envelope(base_mint=POLL_PUMP_MINT, pool=pool, signature=sig)
    net = _FakePollingNet(pools=pools, sig_pages=sig_pages, txs=txs)
    out = _mk_poller(net).poll(created_at_utc="2026-07-10T00:00:00Z",
                               max_gettransaction_allowance=2)
    expect(out["stats"]["transactions_fetched"] <= 2,
           f"allowance not respected: {out['stats']}")
    net2 = _FakePollingNet(pools=pools, sig_pages=sig_pages, txs=txs)
    out2 = _mk_poller(net2, max_gettransaction_per_poll=1).poll(
        created_at_utc="2026-07-10T00:00:00Z", max_gettransaction_allowance=10)
    expect(out2["stats"]["transactions_fetched"] <= 1,
           f"per-poll cap not respected: {out2['stats']}")
    # Cumulative run budget: record_poll folds into the SHARED getTransaction budget and the
    # allowance shrinks to the remainder, then latches.
    b = _mk_budget(max_gettransaction_total=3)
    b.record_poll(out["stats"], accepted=len(out["candidates"]), guard_dropped=0)
    allowance = b.polling_allowance(per_poll_gettransaction=8)
    expect(allowance == {"max_gettransaction": 1},
           f"cumulative polling allowance wrong: {allowance}")
    b.record_poll({"transactions_fetched": 1}, accepted=0, guard_dropped=0)
    expect(b.stop_requested and b.stop_reason == BUDGET_STOP_GETTRANSACTION,
           f"gettransaction ceiling did not latch via polling: {b.stop_reason}")
    expect(b.polling_allowance(per_poll_gettransaction=8) is None,
           "exhausted polling budget still granted a poll")


def t_polling_429_and_errors_trip_budget():
    net = _FakePollingNet(pools=[{"pool": POOL_A, "base": POLL_PUMP_MINT}],
                          sig_pages={}, txs={}, rpc_status=429)
    out = _mk_poller(net).poll(created_at_utc="2026-07-10T00:00:00Z",
                               max_gettransaction_allowance=8)
    expect(out["stats"]["polling_429"] >= 1, f"429 not counted: {out['stats']}")
    b = _mk_budget(max_429_total=1)
    b.record_poll(out["stats"], accepted=0, guard_dropped=0)
    # Polling 429s enter the DISCOVERY-scoped bounded backoff and mark the
    # shared degradation, but never stop the run (2026-07-31 remediation).
    expect(b.rate_limit_degraded,
           f"polling 429 not marked degraded: {b.snapshot()['rate_limit']}")
    expect(not b.stop_requested and b.stop_reason is None,
           f"polling 429 must never stop the producer: {b.stop_reason}")
    expect(b.polling_backoff.throttles_total >= 1,
           "polling 429 did not enter provider-scoped backoff")
    expect(b.market_backoff.throttles_total == 0,
           "polling 429 leaked into the market provider's backoff")
    # Listing-side 429 counts too.
    net2 = _FakePollingNet(pools=[], sig_pages={}, txs={}, listing_status=429)
    out2 = _mk_poller(net2).poll(created_at_utc="2026-07-10T00:00:00Z",
                                 max_gettransaction_allowance=8)
    expect(out2["stats"]["polling_429"] == 1 and out2["stats"]["polling_errors"] == 1,
           f"listing 429 not counted: {out2['stats']}")


def t_polling_too_hot_and_unindexed_pools_are_bounded():
    # Full signature page -> oldest not provably the creation tx -> skipped for good.
    hot_sigs = [{"signature": f"S{i}" + "H" * 84, "err": None} for i in range(2)]
    net = _FakePollingNet(pools=[{"pool": POOL_A, "base": POLL_PUMP_MINT}],
                          sig_pages={POOL_A: hot_sigs}, txs={})
    poller = _mk_poller(net, sig_page_limit=2)
    out = poller.poll(created_at_utc="2026-07-10T00:00:00Z", max_gettransaction_allowance=8)
    expect(out["stats"]["pools_skipped_too_hot"] == 1
           and out["stats"]["transactions_fetched"] == 0,
           f"too-hot pool not skipped: {out['stats']}")
    # Unindexed (empty page) pools retry a bounded number of polls, then give up.
    net2 = _FakePollingNet(pools=[{"pool": POOL_B, "base": POLL_PUMP_MINT}],
                           sig_pages={POOL_B: []}, txs={})
    poller2 = _mk_poller(net2, max_attempts_per_pool=2)
    out_a = poller2.poll(created_at_utc="2026-07-10T00:00:00Z", max_gettransaction_allowance=8)
    expect(out_a["stats"]["pools_gave_up"] == 0, "gave up too early")
    out_b = poller2.poll(created_at_utc="2026-07-10T00:01:00Z", max_gettransaction_allowance=8)
    expect(out_b["stats"]["pools_gave_up"] == 1, f"no bounded give-up: {out_b['stats']}")
    out_c = poller2.poll(created_at_utc="2026-07-10T00:02:00Z", max_gettransaction_allowance=8)
    expect(out_c["stats"]["pools_new"] == 0, "gave-up pool re-listed")


def t_polling_window_record_and_snapshot_are_redaction_safe():
    env = make_migration_envelope(base_mint=POLL_PUMP_MINT, pool=POOL_A, signature=SIG_A)
    net = _FakePollingNet(pools=[{"pool": POOL_A, "base": POLL_PUMP_MINT}],
                          sig_pages={POOL_A: [{"signature": SIG_A, "err": None}]},
                          txs={SIG_A: env})
    out = _mk_poller(net).poll(created_at_utc="2026-07-10T00:00:00Z",
                               max_gettransaction_allowance=8)
    window = {
        "kind": "FREE_TIER_DISCOVERY_WINDOW", "discovery_source": "POLLING",
        "discovery_mode": "POLLING", "window_ended_at_utc": "2026-07-10T00:00:00Z",
        "accepted_candidates": len(out["candidates"]),
        **{k: v for k, v in out["stats"].items()
           if isinstance(v, (int, bool, str)) or v is None},
    }
    expect(artifacts.scan_value_safe(json.dumps(window, sort_keys=True)),
           "polling window record must pass the danger-needle scan")
    b = _mk_budget()
    b.record_poll(out["stats"], accepted=len(out["candidates"]), guard_dropped=0)
    snap = b.snapshot()
    poll_block = snap.get("polling") or {}
    for key in ("poll_count", "signatures_seen", "signatures_new", "transactions_fetched",
                "create_pool_candidates", "pump_suffix_accepted", "non_pump_guard_dropped",
                "polling_errors", "polling_429"):
        expect(key in poll_block, f"budget polling snapshot missing {key}")
    expect(poll_block["poll_count"] == 1 and poll_block["pump_suffix_accepted"] == 1,
           f"polling snapshot counters wrong: {poll_block}")
    expect(artifacts.scan_value_safe(json.dumps(snap, sort_keys=True)),
           "budget snapshot with polling block must be redaction-safe")


def t_discovery_routing_polling_only_never_opens_ws():
    # route_discovery holds the hard invariant: in polling mode the WS opener is NEVER called, so
    # no logsSubscribe socket opens and the raw-WS counter stays 0 across the whole run.
    b = _mk_budget()
    ws_calls = {"n": 0}

    def ws_fn():
        ws_calls["n"] += 1
        b.record_window({"notifications_seen": 40000}, accepted=0)   # would move the raw-WS meter
        return [{"token_mint": "W" * 40 + "pump"}]

    def poll_fn():
        b.record_poll({"poll_count": 1, "transactions_fetched": 1, "signatures_seen": 5},
                      accepted=0, guard_dropped=0)
        return [{"token_mint": "P" * 40 + "pump"}]

    for i in range(1, 11):
        fts.route_discovery(
            discovery_mode="polling", reseed_index=i, ws_window_every_n_reseeds=1,
            ws_discover_fn=ws_fn, poll_discover_fn=poll_fn,
            ws_budget_remaining=b.raw_ws_remaining(), ws_windows_open=b.seed_windows,
            max_seed_windows=b.caps.max_seed_windows)
    expect(ws_calls["n"] == 0, "polling-only opened a WS window")
    snap = b.snapshot()
    expect(snap["raw_ws_notifications_seen"] == 0,
           f"polling-only raw-WS counter must stay 0, got {snap['raw_ws_notifications_seen']}")
    expect(snap["seed_windows"] == 0, "polling-only must open zero seed windows")
    expect(snap["polling"]["poll_count"] == 10, "polling must have run on every reseed")


def t_discovery_routing_hybrid_opens_ws_and_downgrades():
    seen = {"ws": 0, "poll": 0, "skip": 0}

    def ws_fn():
        seen["ws"] += 1
        return [{"token_mint": "W" * 40 + "pump"}]

    def poll_fn():
        seen["poll"] += 1
        return []

    # healthy budget: a WS window opens only every 3rd reseed; polling runs every reseed.
    for i in range(1, 7):
        fts.route_discovery(discovery_mode="hybrid", reseed_index=i, ws_window_every_n_reseeds=3,
                            ws_discover_fn=ws_fn, poll_discover_fn=poll_fn,
                            ws_budget_remaining=999999, ws_windows_open=0, max_seed_windows=40)
    expect(seen["ws"] == 2 and seen["poll"] == 6, f"hybrid WS cadence wrong: {seen}")
    # raw-WS budget spent: WS never opens, the downgrade callback fires, polling continues.
    seen.update(ws=0, poll=0, skip=0)
    for i in range(1, 4):
        fts.route_discovery(discovery_mode="hybrid", reseed_index=i, ws_window_every_n_reseeds=1,
                            ws_discover_fn=ws_fn, poll_discover_fn=poll_fn,
                            ws_budget_remaining=0, ws_windows_open=0, max_seed_windows=40,
                            on_ws_skipped=lambda: seen.__setitem__("skip", seen["skip"] + 1))
    expect(seen["ws"] == 0 and seen["poll"] == 3 and seen["skip"] == 3,
           f"hybrid downgrade wrong: {seen}")


def t_polling_backend_only_posts_read_rpc_never_subscribe():
    # The polling backend structurally cannot open a stream: it only ever POSTs the surgical
    # getSignaturesForAddress -> getTransaction read pair; no *Subscribe method is ever sent.
    env = make_migration_envelope(base_mint=POLL_PUMP_MINT, pool=POOL_A, signature=SIG_A)
    net = _FakePollingNet(pools=[{"pool": POOL_A, "base": POLL_PUMP_MINT}],
                          sig_pages={POOL_A: [{"signature": SIG_A, "err": None}]},
                          txs={SIG_A: env})
    _mk_poller(net).poll(created_at_utc="2026-07-10T00:00:00Z", max_gettransaction_allowance=8)
    methods = {m for (m, _p) in net.rpc_calls}
    expect(methods <= {"getSignaturesForAddress", "getTransaction"},
           f"polling backend posted an unexpected RPC method: {methods}")
    expect(not any("ubscribe" in m for m in methods),
           f"polling backend must NEVER open a *Subscribe stream: {methods}")
    expect("getSignaturesForAddress" in methods and "getTransaction" in methods,
           "polling backend must use the surgical getSig -> getTransaction read path")


# --------------------------------------------------------------------------- market refresh + freshness


def t_market_refresh_retries_fresh_mint_missing_lp():
    # First pairs lookup: price+MC present, NO liquidity (the observed EkNb… failure shape).
    # The bounded escalating refresh must retry past the pair-cache TTL and recover LP.
    calls = {"pairs": 0}

    def urlopen(url, timeout):
        if "dexscreener" in url:
            calls["pairs"] += 1
            pair = {"chainId": "solana", "dexId": "pumpswap", "pairAddress": POOL,
                    "priceUsd": PROOF_CURRENT_PRICE,
                    "marketCap": float(PROOF_MARKET_CAP_USD)}
            if calls["pairs"] >= 2:
                pair["liquidity"] = {"usd": float(PROOF_LIQUIDITY_USD)}
            return 200, json.dumps({"pairs": [pair]}).encode("utf-8")
        return 200, json.dumps({"data": {"attributes": {"ohlcv_list": []}}}).encode("utf-8")

    clock = {"mono": 0.0, "wall": datetime.now(timezone.utc)}

    def fake_sleep(s):
        clock["mono"] += max(float(s), 0.0)
        clock["wall"] = clock["wall"] + timedelta(seconds=max(float(s), 0.0))

    tr = FreeTierMarketTransport(
        urlopen_fn=urlopen, sleep_fn=fake_sleep, monotonic_fn=lambda: clock["mono"],
        pair_cache_ttl_seconds=5.0)
    sidecar = Cap1MarketSidecar(
        transport=tr, endpoint_secret=build_free_tier_endpoint_secret(), timeout_seconds=10,
        enabled=True, caps=Cap1MarketCaps(max_delayed_refresh_seconds=60,
                                          max_calls_per_token=4, max_calls_total=64))
    res = sidecar.resolve(MINT, migration_time_utc=_z(clock["wall"]),
                          now_iso_fn=lambda: _z(clock["wall"]), sleep_fn=fake_sleep)
    expect(res["attempts"][0]["basis"] == "REAL_MARKET_INCOMPLETE",
           f"first attempt should be incomplete: {res['attempts'][0]}")
    expect(len(res["attempts"]) >= 2, "no delayed refresh attempt happened")
    expect(res["all_present"] is True and res["liquidity_usd"] is not None,
           f"delayed refresh did not recover LP: {res}")
    # The old single-attempt mode stays available (knob = 0).
    calls["pairs"] = 0
    tr2 = FreeTierMarketTransport(
        urlopen_fn=urlopen, sleep_fn=fake_sleep, monotonic_fn=lambda: clock["mono"],
        pair_cache_ttl_seconds=5.0)
    sidecar0 = Cap1MarketSidecar(
        transport=tr2, endpoint_secret=build_free_tier_endpoint_secret(), timeout_seconds=10,
        enabled=True, caps=Cap1MarketCaps(max_delayed_refresh_seconds=0,
                                          max_calls_per_token=4, max_calls_total=64))
    res0 = sidecar0.resolve(MINT, migration_time_utc=_z(clock["wall"]),
                            now_iso_fn=lambda: _z(clock["wall"]), sleep_fn=fake_sleep)
    expect(len(res0["attempts"]) == 1 and res0["all_present"] is False,
           "delay=0 must restore the single-attempt behavior")


def t_tail_tracks_watchlist_mints_and_reports_freshness():
    with tempfile.TemporaryDirectory() as td:
        clock = {"t": 1000.0}
        good = "G" * 40 + "pump"
        dead = "D" * 40 + "pump"

        def fetch(mint):
            if mint == good:
                return {"current_price": PROOF_CURRENT_PRICE,
                        "current_market_cap_usd": PROOF_MARKET_CAP_USD,
                        "liquidity_usd": PROOF_LIQUIDITY_USD,
                        "fetched_at_utc": "2026-01-01T00:00:00Z"}
            return None

        tail = FreeTierPricingTail(
            out_dir=td, fetch_market_fn=fetch, now_epoch_fn=lambda: clock["t"],
            max_tracked=8, max_tail_age_seconds=10000.0, min_poll_interval_seconds=60.0)
        expect(tail.track(good, origin=TAIL_ORIGIN_WATCHLIST), "watchlist track refused")
        expect(tail.track(dead, origin=TAIL_ORIGIN_WATCHLIST), "watchlist track refused")
        appended = tail.poll("2026-01-01T00:00:01Z")
        expect(appended == 1, f"watchlist mint not tailed without a would-ping: {appended}")
        rec = json.loads((Path(td) / "pricing_tail.jsonl")
                         .read_text(encoding="utf-8").splitlines()[0])
        expect(rec["token_mint"] == good and rec["tail_origin"] == TAIL_ORIGIN_WATCHLIST,
               f"tail record origin wrong: {rec}")
        snap = normalize_record(rec, "pricing_tail.jsonl", 1)
        expect(snap is not None and snap.mint == good and snap.price_usd is not None,
               "watchlist tail record must normalize for the paper engine")
        fresh = tail.market_freshness()
        expect(fresh["market_data_fresh_count"] == 1
               and fresh["market_unavailable_count"] == 1
               and fresh["market_data_stale_count"] == 0,
               f"freshness counts wrong: {fresh}")
        expect(fresh["last_successful_market_refresh_at"] == "2026-01-01T00:00:01Z",
               "last successful refresh missing")
        expect(fresh["last_market_error"] == "FETCH_MISS", "closed-set last error missing")
        expect(artifacts.scan_value_safe(json.dumps(fresh, sort_keys=True)),
               "freshness block must be redaction-safe")
        # Per-mint poll interval gates spend: an immediate re-poll fetches nothing…
        expect(tail.poll("2026-01-01T00:00:02Z") == 0, "min poll interval not enforced")
        # …and a due re-poll refreshes again; a mint whose feed dies goes STALE (not silent).
        clock["t"] += 61.0
        expect(tail.poll("2026-01-01T00:01:02Z") == 1, "due re-poll did not refresh")
        clock["t"] += 400.0
        fresh2 = tail.market_freshness()
        expect(fresh2["market_data_stale_count"] == 1,
               f"stale detection wrong: {fresh2}")
        # A would-ping upgrade keeps history but switches origin.
        expect(tail.track(good, ath_market_cap_display="$68.0K", tier_at_ping="TIER_3",
                          origin=TAIL_ORIGIN_WOULD_PING), "upgrade track refused")
        expect(tail.market_freshness()["per_mint"][0]["origin"] in (
            TAIL_ORIGIN_WOULD_PING, TAIL_ORIGIN_WATCHLIST), "per-mint origin missing")
        expect(tail.summary()["tracked_by_origin"].get(TAIL_ORIGIN_WOULD_PING) == 1,
               f"origin upgrade lost: {tail.summary()}")


def t_stale_market_context_blocks_dispatch():
    # A sidecar that returns price/MC/LP all PRESENT but FETCHED long ago must never dispatch:
    # the committed composer market-freshness gate (Stage 30.11.14) fails closed.
    class _StaleSidecar:
        def resolve(self, mint, *, migration_time_utc, now_iso_fn, sleep_fn):
            return {
                "current_price": PROOF_CURRENT_PRICE,
                "current_market_cap_usd": PROOF_MARKET_CAP_USD,
                "liquidity_usd": PROOF_LIQUIDITY_USD,
                "market_context_fetched_at_utc": "2026-01-01T00:00:00Z",   # ancient
                "all_present": True, "basis": "REAL_MARKET_PRESENT", "attempts": [],
            }

        def stats(self):
            return {"market_attempts_total": 1}

    anchor = datetime.now(timezone.utc) - timedelta(seconds=_NOW_OFFSET_S)
    tr = make_transport(make_fake_urlopen(anchor=anchor))
    with tempfile.TemporaryDirectory() as td:
        ledger_path = Path(td) / "l.jsonl"
        ledger_path.write_text("", encoding="utf-8")
        bodies: List[Dict[str, Any]] = []
        guard_transport = FreeTierRecordingNoSendTransport(
            on_record=bodies.append, now_iso_fn=lambda: _z(datetime.now(timezone.utc)))
        now_iso = _z(datetime.now(timezone.utc))
        out = _run_activated_candidates(
            [{"token_mint": MINT, "candidate_id": "stale_1",
              "migration_time_utc": _z(anchor), "source_ref": None, "symbol_or_name": None}],
            sidecar=_StaleSidecar(), ath_transport=tr,
            ath_endpoint_secret=build_free_tier_endpoint_secret(),
            now_utc=datetime.now(timezone.utc), now_seconds=make_constant_clock(Decimal(0)),
            now_iso_fn=lambda: _z(datetime.now(timezone.utc)), sleep_fn=lambda _s: None,
            ledger=JsonlPingDedupeLedger(path=ledger_path),
            guard=cs.make_guard(transport=guard_transport),
            authorization=cs.build_authorization(
                confirm_token=fts.LOCKED_CONFIRM_TOKEN, operator_label="SELFTEST",
                authorization_reason="SELFTEST_STALE", created_at_utc=now_iso),
            created_at_utc=now_iso, pump_required=True)
        expect(out["outcome"] == "ZERO_SEND",
               f"stale market context dispatched: {out['per_candidate']}")
        expect(out["per_candidate"][0]["reason"] not in (
            "SEND_ATTEMPTED", "SENT_OK_COMMITTED"),
            "stale market context must never reach a send/commit")
        expect(bodies == [], "no body may be recorded for stale market context")
        lines = [ln for ln in ledger_path.read_text(encoding="utf-8").splitlines()
                 if ln.strip()]
        expect(lines == [], "stale market context must not reserve a ledger line")


# --------------------------------------------------------------------------- risk layer (2026-07-11)


RISK_MINT = "RiskProofMint111111111111111111111111111pump"


def _risk_engine(start: float = 1_000_000.0):
    clock = {"t": float(start)}
    engine = FreeTierRiskEngine(now_epoch_fn=lambda: clock["t"])
    return engine, clock


def _market(price="1.0", lp="50000", mc="100000"):
    return {"current_price": price, "liquidity_usd": lp, "current_market_cap_usd": mc}


def t_risk_classifier_label_paths():
    # UNKNOWN before any observation (and honest reason).
    eng, clock = _risk_engine()
    a = eng.assess(RISK_MINT)
    expect(a["risk_label"] == RISK_UNKNOWN and a["risk_reasons"] == [REASON_NO_MARKET_DATA],
           f"pre-data assess wrong: {a}")
    # LOW on healthy samples (price + LP present, no red flag).
    eng.observe_seed(RISK_MINT, migration_time_utc="2026-07-11T00:00:00Z")
    eng.observe_market_sample(RISK_MINT, _market())
    clock["t"] += 60
    eng.observe_market_sample(RISK_MINT, _market(price="1.05"))
    a = eng.assess(RISK_MINT)
    expect(a["risk_label"] == RISK_LOW and a["risk_reasons"] == [],
           f"healthy assess wrong: {a}")
    expect(a["risk_line"] == "Risk: LOW", f"low line wrong: {a['risk_line']}")
    # MEDIUM on thin LP.
    eng2, _c2 = _risk_engine()
    eng2.observe_market_sample(RISK_MINT, _market(lp="5000"))
    a2 = eng2.assess(RISK_MINT)
    expect(a2["risk_label"] == RISK_MEDIUM and REASON_LP_THIN in a2["risk_reasons"],
           f"thin-LP assess wrong: {a2}")
    # HIGH on LP collapse (peak 50k -> 8k is an 84% drop).
    eng3, c3 = _risk_engine()
    eng3.observe_market_sample(RISK_MINT, _market())
    c3["t"] += 120
    eng3.observe_market_sample(RISK_MINT, _market(lp="8000"))
    a3 = eng3.assess(RISK_MINT)
    expect(a3["risk_label"] == RISK_HIGH
           and REASON_LIQUIDITY_COLLAPSE in a3["risk_reasons"],
           f"collapse assess wrong: {a3}")
    expect(a3["risk_line"].startswith("Risk: HIGH — "), f"high line wrong: {a3['risk_line']}")
    # HIGH on spike-then-dump (1.0 -> 4.0 -> 1.2 with healthy LP).
    eng4, c4 = _risk_engine()
    for price in ("1.0", "4.0", "1.2"):
        eng4.observe_market_sample(RISK_MINT, _market(price=price))
        c4["t"] += 30
    a4 = eng4.assess(RISK_MINT)
    expect(a4["risk_label"] == RISK_HIGH
           and REASON_PRICE_SPIKE_DUMP in a4["risk_reasons"],
           f"spike-dump assess wrong: {a4}")


def t_risk_missing_holder_bundle_data_is_unknown_not_high():
    # Holder / bundler-account signals are UNKNOWN on every assessment — they never
    # push a label toward HIGH, and a mint with NO data stays UNKNOWN (not HIGH).
    eng, _clock = _risk_engine()
    a = eng.assess(RISK_MINT)
    expect(a["risk_label"] == RISK_UNKNOWN, "no-data mint must be UNKNOWN, never HIGH")
    expect(list(a["risk_unknown_signals"]) == list(UNKNOWN_SIGNALS_ALWAYS),
           f"unknown signals wrong: {a['risk_unknown_signals']}")
    eng.observe_market_sample(RISK_MINT, _market())
    a2 = eng.assess(RISK_MINT)
    expect(a2["risk_label"] == RISK_LOW
           and list(a2["risk_unknown_signals"]) == list(UNKNOWN_SIGNALS_ALWAYS),
           "healthy mint stays LOW with holder/bundle signals reported UNKNOWN")
    expect(HOLDER_SCAN_ENABLED is False, "holder scan must be OFF (no scan exists)")
    expect(a2["holder_scan_enabled"] is False, "assessment must pin holder_scan_enabled")
    # No expensive-scan capability exists in the module AT ALL: no HTTP/RPC/WS import
    # and no account-scan RPC method name anywhere in its source.
    src = (Path(fts.FREE_TIER_ROOT) / "free_tier_risk.py").read_text(encoding="utf-8")
    for needle in ("urllib", "websocket", "requests", "http.client",
                   "getProgramAccounts", "getTokenLargestAccounts", "getTokenAccounts"):
        expect(needle not in src, f"free_tier_risk.py must not carry scan capability: {needle}")


def t_risk_market_quality_signals():
    # Consecutive refresh misses AFTER data existed -> MEDIUM (refresh failing).
    eng, _c = _risk_engine()
    eng.observe_market_sample(RISK_MINT, _market())
    for _ in range(3):
        eng.observe_market_sample(RISK_MINT, None)
    a = eng.assess(RISK_MINT)
    expect(a["risk_label"] == RISK_MEDIUM
           and REASON_MARKET_REFRESH_FAILING in a["risk_reasons"],
           f"refresh-failing wrong: {a}")
    # Persistent unavailability with ZERO successes ever -> HIGH.
    eng2, _c2 = _risk_engine()
    for _ in range(5):
        eng2.observe_market_sample(RISK_MINT, None)
    a2 = eng2.assess(RISK_MINT)
    expect(a2["risk_label"] == RISK_HIGH
           and REASON_MARKET_UNAVAILABLE_PERSISTENT in a2["risk_reasons"],
           f"persistent-unavailable wrong: {a2}")
    # Repeated MARKET_UNAVAILABLE rechecks -> MEDIUM (incomplete repeated).
    eng3, _c3 = _risk_engine()
    for _ in range(3):
        eng3.observe_recheck(RISK_MINT, reason="NO_SEND_MARKET_UNAVAILABLE")
    a3 = eng3.assess(RISK_MINT)
    expect(REASON_MARKET_INCOMPLETE_REPEATED in a3["risk_reasons"],
           f"incomplete-repeated wrong: {a3}")
    # Stale newest sample (age > 300s) -> MEDIUM MARKET_STALE.
    eng4, c4 = _risk_engine()
    eng4.observe_market_sample(RISK_MINT, _market())
    c4["t"] += 400
    a4 = eng4.assess(RISK_MINT)
    expect(a4["risk_label"] == RISK_MEDIUM and REASON_MARKET_STALE in a4["risk_reasons"],
           f"stale wrong: {a4}")


def t_risk_too_hot_discovery_signal():
    eng, _c = _risk_engine()
    eng.observe_seed(RISK_MINT, discovery_sig_count=460)
    eng.observe_market_sample(RISK_MINT, _market())
    a = eng.assess(RISK_MINT)
    expect(a["risk_label"] == RISK_HIGH and REASON_POOL_TOO_HOT in a["risk_reasons"],
           f"too-hot high wrong: {a}")
    eng2, _c2 = _risk_engine()
    eng2.observe_seed(RISK_MINT, discovery_sig_count=300)
    eng2.observe_market_sample(RISK_MINT, _market())
    a2 = eng2.assess(RISK_MINT)
    expect(a2["risk_label"] == RISK_MEDIUM and REASON_POOL_HOT_EARLY in a2["risk_reasons"],
           f"hot-early medium wrong: {a2}")
    eng3, _c3 = _risk_engine()
    eng3.observe_seed(RISK_MINT, discovery_sig_count=100)
    eng3.observe_market_sample(RISK_MINT, _market())
    a3 = eng3.assess(RISK_MINT)
    expect(a3["risk_label"] == RISK_LOW, f"calm sig count must not flag: {a3}")


class _CountingInnerTransport:
    fake_only = True
    real_send_capable = False

    def __init__(self) -> None:
        self.payloads: List[Dict[str, Any]] = []

    def send_one_audited_post(self, *, webhook_identity, payload):
        self.payloads.append(dict(payload))
        return type("V", (), {"ok": True, "transport_status": "NO_SEND_RECORDED"})()


def t_risk_line_transport_warn_only_append():
    inner = _CountingInnerTransport()
    line = "Risk: HIGH — spike-dump / thin LP"
    tr = FreeTierRiskLineTransport(inner=inner, risk_line_fn=lambda _m: line)
    body = "PHOENIX ping body\nCA: " + RISK_MINT
    # No binding -> forwarded unmodified (send NEVER blocked).
    tr.send_one_audited_post(webhook_identity="op", payload={"content": body})
    expect(inner.payloads[0]["content"] == body, "unbound send must pass through")
    expect(tr.last_decision["status"] == RISK_LINE_NO_BINDING, "status wrong (no binding)")
    # Bound + exact body match -> ONE line appended; binding consumed one-shot.
    tr.bind_body(body=body, mint=RISK_MINT)
    tr.send_one_audited_post(webhook_identity="op", payload={"content": body})
    expect(inner.payloads[1]["content"] == body + "\n" + line, "risk line not appended")
    expect(tr.last_decision["status"] == RISK_LINE_APPENDED and tr.appends_count == 1,
           f"append decision wrong: {tr.last_decision}")
    tr.send_one_audited_post(webhook_identity="op", payload={"content": body})
    expect(inner.payloads[2]["content"] == body, "stale binding must not annotate later send")
    # Bound but body MISMATCH -> forwarded unmodified.
    tr.bind_body(body=body, mint=RISK_MINT)
    tr.send_one_audited_post(webhook_identity="op", payload={"content": "other body"})
    expect(inner.payloads[3]["content"] == "other body"
           and tr.last_decision["status"] == RISK_LINE_BODY_MISMATCH, "mismatch must no-op")
    # Near-limit body -> append skipped (never exceeds Discord limit), still forwarded.
    big = "x" * 1995
    tr.bind_body(body=big, mint=RISK_MINT)
    tr.send_one_audited_post(webhook_identity="op", payload={"content": big})
    expect(inner.payloads[4]["content"] == big
           and tr.last_decision["status"] == RISK_LINE_TOO_LONG, "oversize must skip append")
    # A RAISING risk_line_fn can never block the send.
    def _boom(_m):
        raise RuntimeError("boom")
    tr2 = FreeTierRiskLineTransport(inner=inner, risk_line_fn=_boom)
    tr2.bind_body(body=body, mint=RISK_MINT)
    tr2.send_one_audited_post(webhook_identity="op", payload={"content": body})
    expect(inner.payloads[5]["content"] == body, "risk-line failure must not alter the send")
    expect(len(inner.payloads) == 6, "every send must reach the inner transport")
    # Duck-type passthrough keeps the inner transport's declared capabilities visible.
    expect(tr.fake_only is True and tr.real_send_capable is False,
           "wrapper must not hide inner capability attributes")


def t_risk_line_reaches_would_ping_body_e2e():
    # Same committed compose->guard->transport chain as t_e2e_would_ping_dispatches, but the
    # guard's transport is the risk wrapper and the compose display seam
    # (axiom_fee_appender.bind_body) arms it — the recorded WOULD-PING body must carry the
    # risk line, and the send chain must be unaffected (RISK_HIGH warns, never blocks).
    line = "Risk: HIGH — liquidity collapse / market stale"
    with tempfile.TemporaryDirectory() as td:
        anchor = datetime.now(timezone.utc) - timedelta(seconds=_NOW_OFFSET_S)
        tr = make_transport(make_fake_urlopen(anchor=anchor))
        secret = build_free_tier_endpoint_secret()
        sidecar = Cap1MarketSidecar(
            transport=tr, endpoint_secret=secret, timeout_seconds=10, enabled=True,
            caps=Cap1MarketCaps(max_delayed_refresh_seconds=0, max_calls_per_token=4,
                                max_calls_total=64))
        ledger_path = Path(td) / "ping_dedupe.jsonl"
        ledger_path.write_text("", encoding="utf-8")
        bodies: List[Dict[str, Any]] = []
        recorder = FreeTierRecordingNoSendTransport(
            on_record=bodies.append, now_iso_fn=lambda: _z(datetime.now(timezone.utc)))
        risk_transport = FreeTierRiskLineTransport(inner=recorder,
                                                   risk_line_fn=lambda _m: line)
        now_iso = _z(datetime.now(timezone.utc))
        out = _run_activated_candidates(
            [{"token_mint": MINT, "candidate_id": "ft_" + MINT[:8],
              "migration_time_utc": _z(anchor), "source_ref": None,
              "symbol_or_name": None}],
            sidecar=sidecar, ath_transport=tr, ath_endpoint_secret=secret,
            now_utc=datetime.now(timezone.utc), now_seconds=make_constant_clock(Decimal(0)),
            now_iso_fn=lambda: _z(datetime.now(timezone.utc)), sleep_fn=lambda _s: None,
            ledger=JsonlPingDedupeLedger(path=ledger_path),
            guard=cs.make_guard(transport=risk_transport),
            authorization=cs.build_authorization(
                confirm_token=fts.LOCKED_CONFIRM_TOKEN, operator_label="SELFTEST",
                authorization_reason="SELFTEST_RISK_LINE", created_at_utc=now_iso),
            created_at_utc=now_iso, pump_required=True,
            axiom_fee_appender=risk_transport)
        expect(out["outcome"] == "ONE_SEND_COMMITTED",
               f"risk annotation must not change dispatch: {out['per_candidate']}")
        expect(len(bodies) == 1, "would-ping body not recorded through the risk wrapper")
        content = bodies[0]["content_text"]
        expect(content.endswith("\n" + line),
               f"risk line missing from recorded body tail: {content[-120:]!r}")
        expect(risk_transport.appends_count == 1
               and risk_transport.last_decision["status"] == RISK_LINE_APPENDED,
               f"append decision wrong: {risk_transport.last_decision}")


def t_risk_artifacts_redaction_safe():
    eng, _c = _risk_engine()
    eng.observe_seed(RISK_MINT, discovery_sig_count=500,
                     migration_time_utc="2026-07-11T00:00:00Z")
    for _ in range(3):
        eng.observe_market_sample(RISK_MINT, None)
    eng.observe_market_sample(RISK_MINT, _market(lp="500"))
    assessment = eng.assess(RISK_MINT)
    for blob in (json.dumps(assessment, sort_keys=True),
                 json.dumps(eng.summary(), sort_keys=True),
                 format_risk_line(RISK_HIGH, list(assessment["risk_reasons"])),
                 format_risk_line(RISK_UNKNOWN, [])):
        expect(artifacts.scan_value_safe(blob), f"risk blob unsafe: {blob[:80]!r}")


def t_polling_attaches_discovery_sig_count():
    env = make_migration_envelope(base_mint=POLL_PUMP_MINT, pool=POOL_A, signature=SIG_A)
    page = [{"signature": "SigNew" + "9" * 82, "err": None},
            {"signature": "SigMid" + "8" * 82, "err": None},
            {"signature": SIG_A, "err": None}]          # oldest row = creation tx
    net = _FakePollingNet(pools=[{"pool": POOL_A, "base": POLL_PUMP_MINT}],
                          sig_pages={POOL_A: page}, txs={SIG_A: env})
    out = _mk_poller(net).poll(created_at_utc="2026-07-11T00:00:00Z",
                               max_gettransaction_allowance=8)
    cands = out["candidates"]
    expect(len(cands) == 1, f"expected one candidate: {cands!r}")
    expect(cands[0].get("discovery_sig_count") == 3,
           f"discovery_sig_count wrong: {cands[0]!r}")
    ref = str(cands[0].get("source_ref") or "")
    expect(ref.startswith("helius:sig:"), f"source_ref shape changed: {ref!r}")


def t_hybrid_thin_profile_is_not_full_firehose():
    thin = fts.resolve_effective_settings(_profile_args("live_2h_hybrid_thin"))
    full = fts.resolve_effective_settings(_profile_args("live_2h"))
    expect(thin["discovery_mode"] == "hybrid", "hybrid_thin must pin hybrid")
    expect(thin["max_raw_ws_notifications_total"] == 400000
           and full["max_raw_ws_notifications_total"] == 2000000,
           "hybrid_thin raw-WS budget must be 400k vs live_2h's 2.0M")
    expect(thin["ws_window_every_n_reseeds"] == 5,
           "hybrid_thin must open a WS window only every 5th reseed")
    expect(thin["max_seed_windows"] == 12 and full["max_seed_windows"] == 40,
           "hybrid_thin seed windows must be far below live_2h")
    expect(thin["poll_pools_per_cycle"] == 6 and thin["poll_sig_page_limit"] == 500
           and thin["poll_max_gettransaction_per_cycle"] == 6,
           "hybrid_thin must keep the low-credit per-poll bounds")
    expect(thin["max_polls_total"] == 300 and thin["max_gettransaction_total"] == 768,
           "hybrid_thin cumulative polling caps wrong")
    expect(thin["market_refresh_max_calls_per_token"] == 3,
           "hybrid_thin must keep the bounded market refresh")


# ------------------------------------------------ private-Discord dispatch risk gate (2026-07-12)


class _FakeErrors:
    """Minimal ErrorLedger stand-in for the gate factory (counts calls, never writes/raises)."""

    def __init__(self) -> None:
        self.count = 0

    def log(self, *_a: Any, **_k: Any) -> None:
        self.count += 1


class _FreshSidecar:
    """Present + freshly-fetched market context (gate reached; freshness passes)."""

    def __init__(self, lp: str = "20000", mc: str = "70000", price: str = "0.00007406") -> None:
        self._lp, self._mc, self._price = lp, mc, price

    def resolve(self, mint, *, migration_time_utc, now_iso_fn, sleep_fn):
        return {"current_price": self._price, "current_market_cap_usd": self._mc,
                "liquidity_usd": self._lp,
                "market_context_fetched_at_utc": _z(datetime.now(timezone.utc)),
                "all_present": True, "basis": "REAL_MARKET_PRESENT", "attempts": []}

    def stats(self):
        return {"market_attempts_total": 1}


def _run_gate_seam(td: Path, *, sig_count: int, use_real_sidecar: bool = True) -> Dict[str, Any]:
    """Drive the EXACT production gate through run_cap1_candidates for MINT, with a risk engine
    seeded to ``sig_count`` (>=450 => too-hot HIGH; 250..449 => hot-early MEDIUM; small => LOW).
    Returns the outcome + the durable ledger lines, recorded transport bodies, and block ledger."""
    anchor = datetime.now(timezone.utc) - timedelta(seconds=_NOW_OFFSET_S)
    tr = make_transport(make_fake_urlopen(anchor=anchor))
    secret = build_free_tier_endpoint_secret()
    if use_real_sidecar:
        sidecar: Any = Cap1MarketSidecar(
            transport=tr, endpoint_secret=secret, timeout_seconds=10, enabled=True,
            caps=Cap1MarketCaps(max_delayed_refresh_seconds=0, max_calls_per_token=4,
                                max_calls_total=64))
    else:
        sidecar = _FreshSidecar()
    eng = FreeTierRiskEngine(now_epoch_fn=lambda: 1_000_000.0)
    eng.observe_seed(MINT, migration_time_utc=_z(anchor), discovery_source="POLLING",
                     discovery_sig_count=sig_count)
    led = fts.DiscordBlockLedger()
    blocks_path = td / "discord_blocks.jsonl"
    errs = _FakeErrors()
    gate = fts.make_discord_risk_gate(
        risk_engine=eng, discord_block_ledger=led, discord_blocks_path=blocks_path,
        min_liquidity_usd=Decimal("4500"), mode="FREE_TIER_PRIVATE_DISCORD", errors=errs)
    ledger_path = td / "l.jsonl"
    ledger_path.write_text("", encoding="utf-8")
    bodies: List[Dict[str, Any]] = []
    guard_transport = FreeTierRecordingNoSendTransport(
        on_record=bodies.append, now_iso_fn=lambda: _z(datetime.now(timezone.utc)))
    now_iso = _z(datetime.now(timezone.utc))
    out = _run_activated_candidates(
        [{"token_mint": MINT, "candidate_id": "gate_1", "migration_time_utc": _z(anchor),
          "source_ref": None, "symbol_or_name": None}],
        sidecar=sidecar, ath_transport=tr, ath_endpoint_secret=secret,
        now_utc=datetime.now(timezone.utc), now_seconds=make_constant_clock(Decimal(0)),
        now_iso_fn=lambda: _z(datetime.now(timezone.utc)), sleep_fn=lambda _s: None,
        ledger=JsonlPingDedupeLedger(path=ledger_path),
        guard=cs.make_guard(transport=guard_transport),
        authorization=cs.build_authorization(
            confirm_token=fts.LOCKED_CONFIRM_TOKEN, operator_label="SELFTEST",
            authorization_reason="SELFTEST_GATE", created_at_utc=now_iso),
        created_at_utc=now_iso, pump_required=True, pre_reserve_gate_fn=gate)
    lines = [ln for ln in ledger_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    return {"out": out, "lines": lines, "bodies": bodies, "led": led,
            "blocks_path": blocks_path, "errs": errs}


def _gate_only(td: Path, *, sig_count: int):
    """Build a gate + seeded engine for DIRECT gate(mint, ctx) calls (no run loop)."""
    eng = FreeTierRiskEngine(now_epoch_fn=lambda: 1_000_000.0)
    eng.observe_seed(MINT, discovery_sig_count=sig_count)
    led = fts.DiscordBlockLedger()
    gate = fts.make_discord_risk_gate(
        risk_engine=eng, discord_block_ledger=led, discord_blocks_path=td / "b.jsonl",
        min_liquidity_usd=Decimal("4500"), mode="SELFTEST", errors=_FakeErrors())
    return gate, led


def _fresh_ctx(**over: Any) -> Dict[str, Any]:
    ctx = {"current_price": "0.001", "current_market_cap_usd": "45000", "liquidity_usd": "15000",
           "basis": "REAL_MARKET_PRESENT",
           "market_context_fetched_at_utc": _z(datetime.now(timezone.utc))}
    ctx.update(over)
    return ctx


def t_discord_policy_label_table():
    # Pure policy across labels + structure (no engine, no run loop).
    d = classify_discord_dispatch({"risk_label": RISK_HIGH, "risk_reasons": [REASON_POOL_TOO_HOT]})
    expect(not d.allowed and d.terminal_decision == SKIPPED_HIGH_RISK_DISCORD
           and d.mapped_reason == HIGH_RISK_TOO_HOT, f"HIGH policy wrong: {d}")
    d = classify_discord_dispatch({"risk_label": RISK_HIGH, "risk_reasons": [REASON_LIQUIDITY_COLLAPSE]})
    expect(d.mapped_reason == HIGH_RISK_LIQUIDITY_COLLAPSE, f"HIGH collapse map wrong: {d}")
    d = classify_discord_dispatch({"risk_label": RISK_MEDIUM, "risk_reasons": [REASON_LP_THIN]},
                                  liquidity_usd="12000", market_cap_usd="45000", market_fresh=True)
    expect(d.allowed and d.terminal_decision == DISCORD_DISPATCH_ALLOWED, f"strong MED wrong: {d}")
    for lp, mc, fresh, want in (("8000", "45000", True, MEDIUM_RISK_LP_TOO_LOW),
                                ("12000", "20000", True, MEDIUM_RISK_MC_TOO_LOW),
                                ("12000", "45000", False, MEDIUM_RISK_MARKET_NOT_FRESH)):
        d = classify_discord_dispatch({"risk_label": RISK_MEDIUM, "risk_reasons": [REASON_LP_THIN]},
                                      liquidity_usd=lp, market_cap_usd=mc, market_fresh=fresh)
        expect(not d.allowed and d.terminal_decision == SKIPPED_MEDIUM_RISK_WEAK_STRUCTURE
               and d.mapped_reason == want, f"weak MED ({lp},{mc},{fresh}) wrong: {d}")
    for lbl in (RISK_LOW, RISK_UNKNOWN):
        d = classify_discord_dispatch({"risk_label": lbl, "risk_reasons": []},
                                      liquidity_usd="1", market_cap_usd="1", market_fresh=False)
        expect(d.allowed, f"{lbl} must be allowed even with weak structure: {d}")


def t_single_stream_medium_is_warning_only_high_still_blocks():
    medium = classify_discord_dispatch(
        {"risk_label": RISK_MEDIUM, "risk_reasons": [REASON_LP_THIN]},
        liquidity_usd="4500", market_cap_usd="20000", market_fresh=True,
        lp_integrity_mode=LP_INTEGRITY_MODE_DISABLED_SINGLE_STREAM,
    )
    expect(medium.allowed and medium.warning_only
           and medium.mapped_reason == MEDIUM_RISK_WARNING_ONLY,
           f"single-stream MEDIUM must be warning-only: {medium}")
    high = classify_discord_dispatch(
        {"risk_label": RISK_HIGH, "risk_reasons": [REASON_POOL_TOO_HOT]},
        liquidity_usd="20000", market_cap_usd="70000", market_fresh=True,
        lp_integrity_mode=LP_INTEGRITY_MODE_DISABLED_SINGLE_STREAM,
    )
    expect(not high.allowed and high.terminal_decision == SKIPPED_HIGH_RISK_DISCORD,
           f"single-stream HIGH must remain blocked: {high}")


def t_discord_gate_high_risk_blocks_before_reserve_and_send():
    # THE proof: a would-otherwise-SEND market (real sidecar) that is RISK_HIGH (too-hot) is blocked
    # at the pre-reserve gate — no ledger reserve, no transport body, no send-cap consume.
    with tempfile.TemporaryDirectory() as td:
        r = _run_gate_seam(Path(td), sig_count=500)     # >=450 => POOL_TOO_HOT => RISK_HIGH
        expect(r["out"]["outcome"] == "ZERO_SEND", f"HIGH dispatched: {r['out']['per_candidate']}")
        rec = r["out"]["per_candidate"][0]
        expect(rec["reason"] == SKIPPED_HIGH_RISK_DISCORD, f"reason={rec['reason']}")
        expect(r["out"].get("sent_attempt") is None, "HIGH must not create a send attempt (no cap)")
        expect(r["lines"] == [], "HIGH must NOT reserve a durable ledger line")
        expect(r["bodies"] == [], "HIGH must NOT reach the webhook/recording transport")
        snap = r["led"].snapshot()
        expect(snap["high_risk_discord_block_count"] == 1
               and snap["medium_risk_structure_block_count"] == 0, f"counts wrong: {snap}")
        expect(snap["high_risk_block_reason_counts"].get(HIGH_RISK_TOO_HOT) == 1, f"reason: {snap}")
        blk = [json.loads(ln) for ln in r["blocks_path"].read_text(encoding="utf-8").splitlines()
               if ln.strip()]
        expect(len(blk) == 1 and blk[0]["terminal_decision"] == SKIPPED_HIGH_RISK_DISCORD
               and blk[0]["mapped_reason"] == HIGH_RISK_TOO_HOT
               and blk[0]["risk_label"] == RISK_HIGH, f"block artifact wrong: {blk}")
        expect(r["errs"].count == 0, "no gate error expected")


def t_discord_gate_allows_low_risk_send_end_to_end():
    # Control for the block test: the SAME market that would-send, when NOT high-risk (RISK_LOW),
    # passes the gate and reserves + reaches the transport exactly like the baseline path.
    with tempfile.TemporaryDirectory() as td:
        r = _run_gate_seam(Path(td), sig_count=10)      # no too-hot; healthy market => RISK_LOW
        expect(r["out"]["outcome"] == "ONE_SEND_COMMITTED", f"LOW must dispatch: {r['out']['per_candidate']}")
        expect(r["out"]["per_candidate"][0]["reason"] == "SENT_OK_COMMITTED", "LOW must reach SENT_OK_COMMITTED")
        expect(len(r["lines"]) == 1, "LOW must commit exactly one ledger line")
        expect(len(r["bodies"]) == 1, "LOW must reach the transport")
        snap = r["led"].snapshot()
        expect(snap["high_risk_discord_block_count"] == 0
               and snap["medium_risk_structure_block_count"] == 0, f"no block expected: {snap}")


def t_discord_gate_strong_medium_allowed():
    with tempfile.TemporaryDirectory() as td:
        gate, led = _gate_only(Path(td), sig_count=300)      # 250..449 => POOL_HOT_EARLY => MEDIUM
        r = gate(MINT, _fresh_ctx(liquidity_usd="15000", current_market_cap_usd="45000"))
        expect(r is None, f"strong MEDIUM must pass risk gate AND floor: got {r!r}")
        expect(led.snapshot()["medium_risk_structure_block_count"] == 0, "no medium block expected")


def t_discord_gate_weak_medium_blocks_with_reasons():
    for over, want in (({"liquidity_usd": "8000"}, MEDIUM_RISK_LP_TOO_LOW),
                       ({"current_market_cap_usd": "20000"}, MEDIUM_RISK_MC_TOO_LOW),
                       ({"market_context_fetched_at_utc": "2020-01-01T00:00:00Z"},
                        MEDIUM_RISK_MARKET_NOT_FRESH)):
        with tempfile.TemporaryDirectory() as td:
            gate, led = _gate_only(Path(td), sig_count=300)
            r = gate(MINT, _fresh_ctx(**over))
            expect(r == SKIPPED_MEDIUM_RISK_WEAK_STRUCTURE, f"want block for {over}, got {r!r}")
            snap = led.snapshot()
            expect(snap["medium_risk_structure_block_count"] == 1
                   and snap["medium_risk_block_reason_counts"].get(want) == 1,
                   f"reason wrong for {over}: {snap}")
            expect(snap["high_risk_discord_block_count"] == 0, "weak MEDIUM is not a HIGH block")


def t_discord_gate_unknown_not_auto_blocked():
    # UNKNOWN (no holder/bundle data) is allowed by policy even with weak structure ...
    d = classify_discord_dispatch({"risk_label": RISK_UNKNOWN, "risk_reasons": [REASON_NO_MARKET_DATA]},
                                  liquidity_usd="10", market_cap_usd="10", market_fresh=False)
    expect(d.allowed and d.terminal_decision == DISCORD_DISPATCH_ALLOWED,
           f"UNKNOWN must not be auto-blocked: {d}")
    # ... and a benign (unseeded) mint with a valid market passes the gate (returns None).
    with tempfile.TemporaryDirectory() as td:
        gate, led = _gate_only(Path(td), sig_count=0)
        r = gate(MINT, _fresh_ctx())
        expect(r is None, f"benign LOW/UNKNOWN mint must pass the gate: {r!r}")
        expect(led.snapshot()["high_risk_discord_block_count"] == 0, "no block for benign mint")


def t_discord_block_ledger_distinct_counts_and_reasons():
    led = fts.DiscordBlockLedger()
    dh = DiscordRiskDecision(False, SKIPPED_HIGH_RISK_DISCORD, RISK_HIGH, (), HIGH_RISK_TOO_HOT)
    expect(led.record(dh, "MintA") is True, "first block is new")
    expect(led.record(dh, "MintA") is False, "same mint must not recount")
    expect(led.record(dh, "MintB") is True, "distinct mint is new")
    dm = DiscordRiskDecision(False, SKIPPED_MEDIUM_RISK_WEAK_STRUCTURE, RISK_MEDIUM, (),
                             MEDIUM_RISK_LP_TOO_LOW)
    expect(led.record(dm, "MintC") is True, "medium block is new")
    snap = led.snapshot()
    expect(snap["high_risk_discord_block_count"] == 2, f"high distinct wrong: {snap}")
    expect(snap["medium_risk_structure_block_count"] == 1, f"medium distinct wrong: {snap}")
    expect(snap["high_risk_block_reason_counts"].get(HIGH_RISK_TOO_HOT) == 2, f"high reason: {snap}")
    expect(snap["medium_risk_block_reason_counts"].get(MEDIUM_RISK_LP_TOO_LOW) == 1, f"med reason: {snap}")
    expect(set(snap["high_risk_blocked_mints"]) == {"MintA", "MintB"}, f"mints: {snap}")


def t_p1_capacity_formula_refuses_legacy_and_accepts_production() -> None:
    """PHX2-E2E-006: the structural capacity proof is deterministic offline.

    The legacy serialized shape (2 workers, 1.05 s global spacing) must be
    refused for 128 candidates at the 15 s objective; the production shape
    the session builds by default must be achievable, and the session-level
    refusal helper must agree with the scheduler-level formula.
    """

    from PHX2.free_tier_producer.market_scheduler import (
        P1_CAPACITY_UNACHIEVABLE as _UNACHIEVABLE,
        MarketSchedulerConfig as _Config,
        evaluate_p1_capacity as _evaluate,
        production_p1_scheduler_fields as _fields,
    )
    legacy = _evaluate(_Config(), active_candidates=128)
    expect(legacy["p1_capacity_achievable"] is False,
           f"legacy shape must refuse: {legacy}")
    expect(legacy["refusal_reason"] == _UNACHIEVABLE,
           f"refusal token wrong: {legacy}")
    expect(legacy["calculated_worst_case_bound_seconds"] > 100.0,
           f"legacy bound must report the ~133 s floor: {legacy}")
    values = _fields()
    production = _evaluate(_Config(
        worker_count=values["worker_count"],
        max_inflight=values["max_inflight"],
        provider_min_interval_seconds=values["provider_min_interval_seconds"],
        p1_deadline_seconds=values["p1_deadline_seconds"],
        healthy_response_budget_seconds=values["healthy_response_budget_seconds"],
        dispatch_overhead_budget_seconds=values["dispatch_overhead_budget_seconds"],
        p1_max_attempts=values["p1_max_attempts"],
        p1_request_timeout_seconds=values["p1_request_timeout_seconds"],
        p1_reserved_workers=values["p1_reserved_workers"],
    ), active_candidates=128)
    expect(production["p1_capacity_achievable"] is True,
           f"production shape must be achievable: {production}")
    expect(production["calculated_worst_case_bound_seconds"] <= 15.0,
           f"production bound must fit the deadline: {production}")


def t_p1_session_capacity_helper_matches_scheduler_formula() -> None:
    """The session refusal helper and the runtime scheduler share one config."""

    import argparse

    from PHX2.free_tier_producer import free_tier_session as _session

    parser = argparse.ArgumentParser()
    _session._add_args(parser)
    args = parser.parse_args([])
    verdict = _session.evaluate_session_p1_capacity(args)
    expect(verdict["p1_capacity_achievable"] is True,
           f"default session configuration must be achievable: {verdict}")
    config = _session.build_production_market_scheduler_config(args)
    expect(config.worker_count == verdict["configured_worker_count"],
           "formula and runtime scheduler must share the configuration source")
    expect(config.provider_min_interval_seconds == (
        verdict["request_start_spacing_seconds"]),
        "spacing must come from the same source")


def t_market_scheduler_config_schema_fails_closed() -> None:
    """F-1: the legacy TTL/SLO + backlog schema refuses at construction.

    Every TTL/SLO field must be a finite real numeric > 0 and
    backlog_high_fraction must sit in (0, 1]; bool, non-finite and
    non-numeric shapes refuse with the closed-set tokens.  The refusal
    happens inside ``__post_init__`` — an invalid operator flag can never
    reach a provider, scheduler worker, socket or ledger object.
    """

    from PHX2.free_tier_producer.market_scheduler import (
        MarketSchedulerConfig as _Config,
        TTL_SLO_CONFIG_FIELDS as _FIELDS,
    )
    expect(len(_FIELDS) == 12, f"closed set must hold 12 fields: {_FIELDS}")
    for field_name, bad_value in (
            ("price_active_ttl_seconds", -5.0),
            ("grpc_max_age_seconds", -1.0),
            ("overview_active_ttl_seconds", float("nan")),
            ("heartbeat_jitter_slo_seconds", 0.0),
            ("recovery_schedule_slo_seconds", True),
    ):
        try:
            _Config(**{field_name: bad_value})
        except ValueError as exc:
            expect(str(exc) == f"market_scheduler_ttl_invalid:{field_name}",
                   f"token wrong for {field_name}: {exc}")
        else:
            expect(False, f"{field_name}={bad_value!r} must refuse")
    for bad_fraction in (0.0, 1.01, float("inf"), True):
        try:
            _Config(backlog_high_fraction=bad_fraction)
        except ValueError as exc:
            expect(str(exc) == "market_scheduler_backlog_fraction_invalid",
                   f"fraction token wrong: {exc}")
        else:
            expect(False, f"backlog_high_fraction={bad_fraction!r} must refuse")
    expect(_Config().backlog_high_fraction == 0.75,
           "legacy defaults must still construct unchanged")
    expect(_Config(backlog_high_fraction=1.0).backlog_high_fraction == 1.0,
           "the (0, 1] upper boundary must remain accepted")
    expect(_Config(price_active_ttl_seconds=0.05
                   ).price_active_ttl_seconds == 0.05,
           "small positive TTLs must remain accepted and unmutated")


def main() -> int:
    tests = [
        ("secret_shape", t_secret_shape),
        ("price_translation", t_price_translation),
        ("price_via_committed_source", t_price_via_committed_source),
        ("overview_via_committed_source", t_overview_via_committed_source),
        ("overview_fdv_fallback", t_overview_fdv_fallback),
        ("no_pairs_is_missing_not_refusal", t_no_pairs_is_missing_not_refusal),
        ("http_error_is_refusal", t_http_error_is_refusal),
        ("ohlcv_window_filter_and_shape", t_ohlcv_window_filter_and_shape),
        ("ohlcv_committed_ath_selection", t_ohlcv_uses_committed_ath_selection),
        ("budget_cap_refuses", t_budget_cap_refuses),
        ("pair_cache_single_fetch", t_pair_cache_single_fetch),
        ("fallback_consulted_on_refusal", t_fallback_consulted_on_refusal),
        ("simple_market_helper", t_simple_market_helper),
        ("no_send_transport_records", t_no_send_transport_records),
        ("no_send_transport_rejects_bad_payload", t_no_send_transport_rejects_bad_payload),
        ("e2e_would_ping_dispatches", t_e2e_would_ping_dispatches),
        ("e2e_non_pump_dropped", t_e2e_non_pump_dropped),
        ("e2e_liquidity_floor_blocks", t_e2e_liquidity_floor_blocks),
        ("loop_smoke_clean_stop_one_would_ping", t_loop_smoke_clean_stop_one_would_ping),
        ("loop_artifacts_normalize_for_paper_engine", t_loop_artifacts_normalize_for_paper_engine),
        ("pricing_tail_records_and_normalizes", t_pricing_tail_records_and_normalizes),
        ("pricing_tail_bounds", t_pricing_tail_bounds),
        ("forbidden_paths_refuse", t_forbidden_paths_refuse),
        ("no_send_env_hardening", t_no_send_env_hardening),
        ("discord_arm_gate_refusals", t_discord_arm_gate_refusals),
        ("provider_name_is_a_caught_needle", t_provider_name_is_a_caught_needle),
        ("error_ledger_shape", t_error_ledger_shape),
        ("dedupe_suppresses_second_would_ping", t_dedupe_suppresses_second_would_ping),
        ("budget_send_cap_latches_and_raises", t_budget_send_cap_latches_and_raises),
        ("budget_window_allowance_shrinks_and_blocks",
         t_budget_window_allowance_shrinks_and_blocks),
        ("budget_throttle_tripwires", t_budget_throttle_tripwires),
        ("market_transport_counts_429", t_market_transport_counts_429),
        ("budget_rewrite_and_verdict", t_budget_rewrite_and_verdict),
        ("loop_budget_send_cap_end_to_end", t_loop_budget_send_cap_end_to_end),
        ("pump_guard_suffix_semantics", t_pump_guard_suffix_semantics),
        ("pump_guard_checks_actual_mint_not_pool_or_logs",
         t_pump_guard_checks_actual_mint_not_pool_or_logs),
        ("pump_guard_drops_malformed_candidates_safely",
         t_pump_guard_drops_malformed_candidates_safely),
        ("pump_guard_non_pump_never_reaches_watchlist_or_watch_state",
         t_pump_guard_non_pump_never_reaches_watchlist_or_watch_state),
        ("pump_guard_non_pump_never_enriches_reserves_or_pings",
         t_pump_guard_non_pump_never_enriches_reserves_or_pings),
        ("watchlist_capacity_counts_active_only_and_archives_terminal",
         t_watchlist_capacity_counts_active_only_and_archives_terminal),
        # --- authenticated checkpoints (PHX2-E2E-005) ---
        ("checkpoint_corrupt_both_quarantines_not_empty",
         t_checkpoint_corrupt_both_quarantines_not_empty),
        ("checkpoint_legacy_activation_migrates_and_requires_fresh_tick",
         t_checkpoint_legacy_activation_migrates_and_requires_fresh_tick),
        ("checkpoint_tampered_lower_ath_never_restores",
         t_checkpoint_tampered_lower_ath_never_restores),
        # --- durable stream cursor + reconnect replay (PHX2-E2E-008) ---
        ("stream_cursor_survives_restart_and_suppresses_replay_overlap",
         t_stream_cursor_survives_restart_and_suppresses_replay_overlap),
        ("stream_cursor_reconnect_requests_replay_not_the_live_head",
         t_stream_cursor_reconnect_requests_replay_not_the_live_head),
        ("stream_cursor_holds_when_the_downstream_handoff_is_not_durable",
         t_stream_cursor_holds_when_the_downstream_handoff_is_not_durable),
        ("raw_ws_cap_is_raw_message_cap_not_credits",
         t_raw_ws_cap_is_raw_message_cap_not_credits),
        ("profiles_live_2h_does_not_use_old_raw_cap",
         t_profiles_live_2h_does_not_use_old_raw_cap),
        ("profiles_explicit_flag_wins_and_bad_profile_refused",
         t_profiles_explicit_flag_wins_and_bad_profile_refused),
        ("hybrid_ws_exhaustion_downgrades_not_stops",
         t_hybrid_ws_exhaustion_downgrades_not_stops),
        ("profiles_low_credit_polling_by_default", t_profiles_low_credit_polling_by_default),
        ("profiles_hybrid_thin_shape", t_profiles_hybrid_thin_shape),
        ("polling_extracts_actual_mint_not_pool_or_log_text",
         t_polling_extracts_actual_mint_not_pool_or_log_text),
        ("polling_dedupes_signatures_and_pools_durably",
         t_polling_dedupes_signatures_and_pools_durably),
        ("polling_respects_gettransaction_caps", t_polling_respects_gettransaction_caps),
        ("polling_429_and_errors_trip_budget", t_polling_429_and_errors_trip_budget),
        ("polling_too_hot_and_unindexed_pools_are_bounded",
         t_polling_too_hot_and_unindexed_pools_are_bounded),
        ("polling_window_record_and_snapshot_are_redaction_safe",
         t_polling_window_record_and_snapshot_are_redaction_safe),
        ("discovery_routing_polling_only_never_opens_ws",
         t_discovery_routing_polling_only_never_opens_ws),
        ("discovery_routing_hybrid_opens_ws_and_downgrades",
         t_discovery_routing_hybrid_opens_ws_and_downgrades),
        ("polling_backend_only_posts_read_rpc_never_subscribe",
         t_polling_backend_only_posts_read_rpc_never_subscribe),
        ("market_refresh_retries_fresh_mint_missing_lp",
         t_market_refresh_retries_fresh_mint_missing_lp),
        ("tail_tracks_watchlist_mints_and_reports_freshness",
         t_tail_tracks_watchlist_mints_and_reports_freshness),
        ("stale_market_context_blocks_dispatch", t_stale_market_context_blocks_dispatch),
        ("risk_classifier_label_paths", t_risk_classifier_label_paths),
        ("risk_missing_holder_bundle_data_is_unknown_not_high",
         t_risk_missing_holder_bundle_data_is_unknown_not_high),
        ("risk_market_quality_signals", t_risk_market_quality_signals),
        ("risk_too_hot_discovery_signal", t_risk_too_hot_discovery_signal),
        ("risk_line_transport_warn_only_append", t_risk_line_transport_warn_only_append),
        ("risk_line_reaches_would_ping_body_e2e", t_risk_line_reaches_would_ping_body_e2e),
        ("risk_artifacts_redaction_safe", t_risk_artifacts_redaction_safe),
        ("polling_attaches_discovery_sig_count", t_polling_attaches_discovery_sig_count),
        ("hybrid_thin_profile_is_not_full_firehose",
         t_hybrid_thin_profile_is_not_full_firehose),
        # --- private-Discord dispatch risk gate (2026-07-12) ---
        ("discord_policy_label_table", t_discord_policy_label_table),
        ("single_stream_medium_is_warning_only_high_still_blocks",
         t_single_stream_medium_is_warning_only_high_still_blocks),
        ("discord_gate_high_risk_blocks_before_reserve_and_send",
         t_discord_gate_high_risk_blocks_before_reserve_and_send),
        ("discord_gate_allows_low_risk_send_end_to_end",
         t_discord_gate_allows_low_risk_send_end_to_end),
        ("discord_gate_strong_medium_allowed", t_discord_gate_strong_medium_allowed),
        ("discord_gate_weak_medium_blocks_with_reasons",
         t_discord_gate_weak_medium_blocks_with_reasons),
        ("discord_gate_unknown_not_auto_blocked", t_discord_gate_unknown_not_auto_blocked),
        ("discord_block_ledger_distinct_counts_and_reasons",
         t_discord_block_ledger_distinct_counts_and_reasons),
        ("p1_capacity_formula_refuses_legacy_and_accepts_production",
         t_p1_capacity_formula_refuses_legacy_and_accepts_production),
        ("p1_session_capacity_helper_matches_scheduler_formula",
         t_p1_session_capacity_helper_matches_scheduler_formula),
        ("market_scheduler_config_schema_fails_closed",
         t_market_scheduler_config_schema_fails_closed),
    ]
    for name, fn in tests:
        check(name, fn)
    passed = sum(1 for _n, ok, _e in _RESULTS if ok)
    for name, ok, err in _RESULTS:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + ("" if ok else f" -> {err}"))
    print(f"FREE-TIER SELFTEST: {passed}/{len(_RESULTS)} passed "
          f"(offline; no socket, no send, no durable-ledger mutation)")
    return 0 if passed == len(_RESULTS) else 1


if __name__ == "__main__":
    raise SystemExit(main())

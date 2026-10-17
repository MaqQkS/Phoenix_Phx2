"""Build 30 cap-1 forward-watch — session runner + modes + arm gate + CLI.

OUT-OF-REPO operator glue. Modes: --selftest (offline) | --check-wiring (construct live components,
NO send/reserve) | --preflight (reuse Build 29 readiness, no socket/RPC/GET/send/mutation) | --run
(ARMED bounded forward-watch: seed-once -> recheck loop -> ONE guarded private send iff a watched
candidate enters the committed eligible dip band; live never default).

Preserves the audited send path EXACTLY:
  compose_and_maybe_send -> compose_no_send_dispatch_deduped -> Stage30_11_16RealPrivateTransportGuard
  -> Stage28_9PrivateWebhookTransport(audited_transport=Stage28_4AuditedHttpTransport) -> durable
  JsonlPingDedupeLedger.
Does NOT use the broken bundle helper make_real_private_transport(...). Webhook URL is read from env
and injected; NEVER printed. Seed-once-then-watch (no interleaved re-seed in this build).
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, Optional

_HERE = Path(__file__).resolve().parent
_BUNDLE = str(_HERE)
_REPO = str(_HERE.parents[2])
_SELF = str(_HERE)
for _p in (_REPO, _BUNDLE, _SELF):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# Build 29 bundle (read-only reuse of the audited send path + helpers).
import build29_cap1_compose_send as cs        # noqa: E402
import build29_cap1_ledger as ledgerlib       # noqa: E402
import build29_cap1_session as sess           # noqa: E402
from build29_cap1_market_sidecar import Cap1MarketCaps, Cap1MarketSidecar  # noqa: E402

# Build 30 modules.
import build30_artifacts as art30             # noqa: E402
from build30_forward_watch import WatchBounds, run_forward_watch  # noqa: E402
from build30_watchlist import Watchlist       # noqa: E402

# Committed PHX2 (read-only).
from PHX2.stage30.stage30_11_2_fake_runtime_gate_proof import make_constant_clock  # noqa: E402

ENV_WEBHOOK = sess.ENV_WEBHOOK                       # PHX2_STAGE21_DISCORD_WEBHOOK_URL
LOCKED_CONFIRM_TOKEN = cs.STAGE30_11_16_AUTHORIZATION_CONFIRM_TOKEN

DURABLE_LEDGER_DEFAULT = r"C:\Users\BalaC\phx2_one_send_ceremony\ping_dedupe.jsonl"
ENV_FILE_DEFAULT = r"C:\Users\BalaC\Documents\phx2.env"
_OUT_ROOT = r"C:\Users\BalaC\phx2_build30_cap1_forward_watch\out"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _utc_now_dt() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _default_out_dir() -> str:
    return str(Path(_OUT_ROOT) / ("b30_watch_" + _utc_now_dt().strftime("%Y%m%dT%H%M%SZ")))


def _readiness_timeout(default: int = 10) -> int:
    try:
        from PHX2.stage29.stage29_2_birdeye_readiness import detect_stage29_2_birdeye_readiness
        t = getattr(detect_stage29_2_birdeye_readiness(), "timeout_seconds", None)
        return int(t) if isinstance(t, int) and t > 0 else default
    except Exception:
        return default


def _ledger_line_count_fn(ledger_path: str) -> Any:
    def _f() -> int:
        triple = ledgerlib.compute_baseline(ledger_path)
        return triple.line_count if triple is not None else 0
    return _f


def _make_real_market_factory(timeout_seconds: int):
    """Return (sidecar_factory, ath_transport, ath_endpoint_secret). A FRESH single-fetch sidecar
    per recheck cycle (max_delayed_refresh_seconds=0 → one immediate price/MC/LP fetch; the loop
    interval provides the over-time refresh). The SAME real transport+secret feed the ATH anchor."""
    from PHX2.stage29.stage29_2_birdeye_http_transport import Stage29_2BirdeyeUrlibTransport
    from PHX2.stage29.stage29_2_birdeye_readiness import build_endpoint_secret_from_env
    transport = Stage29_2BirdeyeUrlibTransport()
    secret = build_endpoint_secret_from_env()  # raises if env not ready

    def sidecar_factory(_cycle: int) -> Cap1MarketSidecar:
        return Cap1MarketSidecar(
            transport=transport, endpoint_secret=secret, timeout_seconds=timeout_seconds,
            enabled=True,
            caps=Cap1MarketCaps(max_delayed_refresh_seconds=0, max_calls_per_token=4,
                                max_calls_total=256),
        )

    return sidecar_factory, transport, secret


def _build_real_private_transport(webhook_url: str, webhook_identity: Optional[str],
                                  timeout_seconds: float):
    """Construct the REAL private transport CORRECTLY (the bundle's make_real_private_transport
    omits the required audited_transport=). URL bound privately; NEVER printed. No network at build."""
    from PHX2.stage28.audited_http_transport import Stage28_4AuditedHttpTransport
    from PHX2.stage28.live_provider_session_transport import Stage28_9PrivateWebhookTransport
    from PHX2.stage28.audited_http_transport_models import WEBHOOK_IDENTITY_PRIVATE_OPERATOR
    audited = Stage28_4AuditedHttpTransport(timeout_seconds=float(timeout_seconds))
    return Stage28_9PrivateWebhookTransport(
        audited_transport=audited, webhook_url=webhook_url,
        webhook_identity=webhook_identity or WEBHOOK_IDENTITY_PRIVATE_OPERATOR,
    )


def _discover_candidates(*, key: str, url: str, caps) -> Dict[str, Any]:
    """Real read-only Helius discovery via committed build26 run_capture -> _record_to_candidate."""
    from build26_evidence_capture import (
        RealLogsSource, RealTxFetcher, run_capture, _utc_now_iso as _b26_iso,
    )
    now_fn = time.monotonic
    created_at = _b26_iso()
    logs_source = RealLogsSource(api_key=key, caps=caps, now_fn=now_fn)
    tx_fetcher = RealTxFetcher(rpc_url=url, caps=caps)
    res = run_capture(logs_source, tx_fetcher, caps, created_at=created_at,
                      clock_observed=created_at, now_fn=now_fn)
    records = list(getattr(res.run, "evidence_records", ()) or ())
    candidates = [c for c in (sess._record_to_candidate(r) for r in records) if c]
    return {"candidates": candidates, "stats": res.stats, "evidence_record_count": len(records)}


def _capture_caps(args):
    from build26_evidence_capture import CaptureCaps
    accepted = min(10, max(1, int(args.max_accepted)))  # committed CaptureCaps bound [1,10]
    return CaptureCaps(
        max_runtime_seconds=float(args.max_seed_runtime),
        max_logs_notifications=int(args.max_notifications),
        max_gettransaction_fetches=int(args.max_gettransaction),
        max_seed=accepted, max_accepted_evidence=accepted,
    )


def _bounds_from_args(args) -> WatchBounds:
    return WatchBounds(
        recheck_interval_seconds=float(args.watch_recheck_interval_seconds),
        max_candidate_age_seconds=int(args.watch_max_candidate_age_seconds),
        max_rechecks_per_candidate=int(args.watch_max_rechecks_per_candidate),
        max_runtime_seconds=float(args.watch_max_total_runtime_seconds),
        max_watchlist_size=int(args.watch_max_watchlist_size),
        max_market_calls_total=int(args.watch_max_market_calls_total),
        max_real_sends=int(args.max_real_sends),
    )


# ---------------------------------------------------------------------------
# Mode: --check-wiring  (construct live components; NO send, NO reserve, NO network)
# ---------------------------------------------------------------------------


def run_check_wiring(args) -> int:
    n = sess.load_env_file(args.env)
    scrubbed = sess.scrub_unrelated_env()
    print(f"check-wiring env: loaded {n} vars; scrubbed {scrubbed} unrelated (webhook kept); "
          f"values NEVER printed.")
    ok = True
    try:
        timeout_seconds = _readiness_timeout(default=10)
        sidecar_factory, mkt_transport, _secret = _make_real_market_factory(timeout_seconds)
        _ = sidecar_factory(1)
        print(f"market: sidecar_factory_ok=True ath_transport_constructed=True "
              f"timeout_seconds={timeout_seconds}")
    except Exception as exc:
        ok = False
        print(f"market: constructed=False ({type(exc).__name__})")
    webhook_present = bool((os.environ.get(ENV_WEBHOOK) or "").strip())
    try:
        rt = _build_real_private_transport(os.environ.get(ENV_WEBHOOK) or "",
                                           args.webhook_identity, float(_readiness_timeout()))
        guard = cs.make_guard(transport=rt)
        print(f"real_transport: constructed=True webhook_present={webhook_present} "
              f"guard_constructed={guard is not None} (URL never printed)")
    except Exception as exc:
        ok = False
        print(f"real_transport/guard: constructed=False webhook_present={webhook_present} "
              f"({type(exc).__name__})")
    try:
        from PHX2.stage30.stage30_11_16_real_send_models import is_real_send_authorization
        auth = cs.build_authorization(
            confirm_token=LOCKED_CONFIRM_TOKEN, operator_label=args.operator_label or "PHX2_CAP1_OPERATOR",
            authorization_reason=args.authorization_reason or "CAP1_ONE_PRIVATE_OPERATOR_SEND",
            created_at_utc=_iso(_utc_now_dt()),
        )
        print(f"authorization: constructed=True valid={bool(is_real_send_authorization(auth))}")
    except Exception as exc:
        ok = False
        print(f"authorization: constructed=False ({type(exc).__name__})")
    try:
        from PHX2.stage30.stage30_11_15_ping_dedupe_ledger import JsonlPingDedupeLedger
        _ = JsonlPingDedupeLedger(path=Path(args.ledger_path))  # read-only replay; NO write
        triple = ledgerlib.compute_baseline(args.ledger_path)
        req = ledgerlib.parse_require_baseline(args.require_baseline) if args.require_baseline else None
        matches = ledgerlib.baseline_matches(triple, req) if (triple and req) else None
        bl = (f"{triple.sha256}:{triple.size_bytes}:{triple.line_count}") if triple else "MISSING"
        print(f"durable_ledger: opened_readonly=True baseline={bl} matches_require_baseline={matches}")
    except Exception as exc:
        ok = False
        print(f"durable_ledger: opened_readonly=False ({type(exc).__name__})")
    print(f"check-wiring: made NO network call, performed NO send, did NOT mutate the ledger, "
          f"printed NO secret. WIRING_OK={ok}")
    return 0 if ok else 1


# ---------------------------------------------------------------------------
# Mode: --run  (ARMED bounded forward-watch — authored; fired only on explicit approval)
# ---------------------------------------------------------------------------


def _sent_ok(send_result: Any) -> bool:
    return bool(send_result is not None
                and getattr(send_result, "dispatch_forwarded", False)
                and getattr(send_result, "transport_ok", None) is True)


def run_armed_forward_watch(args) -> int:
    n = sess.load_env_file(args.env)
    scrubbed = sess.scrub_unrelated_env()
    print(f"env: loaded {n} vars; scrubbed {scrubbed} unrelated (webhook kept); values NEVER printed.")

    if not args.ack:
        print(f"[refused] a live cap-1 run requires {sess.ACK_FLAG}.")
        return 2
    if int(args.max_real_sends) != 1:
        print("[refused] --max-real-sends must be exactly 1 for cap-1.")
        return 2
    refusal = sess._verify_arm(args)
    if refusal is not None:
        print(f"[refused-arm] {refusal} — no send, no ledger mutation.")
        return 2

    before = ledgerlib.compute_baseline(args.ledger_path)
    if before is None:
        print("[refused-arm] durable ledger missing at arm time.")
        return 2

    out_dir = args.out_dir or _default_out_dir()
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    watch_state_path = str(Path(out_dir) / "watch_state.jsonl")  # SEPARATE from the durable ledger
    print(f"out_dir: {out_dir}")

    key = os.environ.get("HELIUS_API_KEY")
    url = os.environ.get("HELIUS_RPC_URL")
    if not (key and key.strip() and url and url.strip()):
        print("[refused-arm] Helius env missing.")
        return 2

    # Seed-once (bounded discovery window). One live surface at a time: WS closes after seeding.
    print("[live] seed: read-only Helius discovery window starting (no send/arm/ledger yet)...")
    disc = _discover_candidates(key=key, url=url, caps=_capture_caps(args))
    bounds = _bounds_from_args(args)
    watchlist = Watchlist(max_size=bounds.max_watchlist_size)
    seeded_at = _iso(_utc_now_dt())
    for cand in disc["candidates"]:
        watchlist.seed(cand, seeded_at_utc=seeded_at)
    print(f"[live] seed done: evidence_records={disc['evidence_record_count']} "
          f"seeded={len(watchlist.all_entries())} active={len(watchlist.active_entries())}")

    timeout_seconds = _readiness_timeout(default=10)
    sidecar_factory, mkt_transport, mkt_secret = _make_real_market_factory(timeout_seconds)
    from PHX2.stage30.stage30_11_15_ping_dedupe_ledger import JsonlPingDedupeLedger
    durable = JsonlPingDedupeLedger(path=Path(args.ledger_path))
    real_transport = _build_real_private_transport(
        os.environ.get(ENV_WEBHOOK) or "", args.webhook_identity, float(timeout_seconds))
    authorization = cs.build_authorization(
        confirm_token=args.confirm_token, operator_label=args.operator_label or "PHX2_CAP1_OPERATOR",
        authorization_reason=args.authorization_reason or "CAP1_ONE_PRIVATE_OPERATOR_SEND",
        created_at_utc=seeded_at,
    )

    def _sink(*, rec, entry, cycle, observed_at_utc, ledger_touched, transport_attempted):
        record = art30.build_candidate_recheck_record(
            rec=rec, entry=entry, cycle=cycle, observed_at_utc=observed_at_utc,
            ledger_touched=ledger_touched, transport_attempted=transport_attempted)
        art30.append_candidate_jsonl(out_dir, rec.get("token_mint", ""), record)

    print("[live] watch loop starting (recheck every "
          f"{int(bounds.recheck_interval_seconds)}s; stop on one send / runtime / empty)...")
    res = run_forward_watch(
        watchlist=watchlist, sidecar_factory=sidecar_factory,
        ath_transport=mkt_transport, ath_endpoint_secret=mkt_secret,
        ledger=durable, guard_factory=lambda: cs.make_guard(transport=real_transport),
        authorization=authorization, now_dt_fn=_utc_now_dt, now_iso_fn=sess._utc_now_iso,
        now_seconds=make_constant_clock(Decimal(0)), sleep_fn=time.sleep, monotonic_fn=time.monotonic,
        bounds=bounds, run_cap1_candidates_fn=sess.run_cap1_candidates,
        ledger_line_count_fn=_ledger_line_count_fn(args.ledger_path),
        on_candidate_record=_sink, watch_state_path=watch_state_path,
    )

    after = ledgerlib.compute_baseline(args.ledger_path)
    delta = ledgerlib.line_count_delta(before, after)
    return _finish_and_report(res=res, before=before, after=after, delta=delta, out_dir=out_dir,
                              disc=disc, args=args)


def _finish_and_report(*, res, before, after, delta, out_dir, disc, args) -> int:
    sent = res.get("sent_attempt") or {}
    send_result = sent.get("send_result")
    transport_attempted = bool(getattr(send_result, "transport_attempted", False)) if send_result else False
    dispatch_forwarded = bool(getattr(send_result, "dispatch_forwarded", False)) if send_result else False
    transport_ok = getattr(send_result, "transport_ok", None) if send_result else None
    cap_consumed = bool(getattr(send_result, "cap_consumed", False)) if send_result else False
    sent_ok = _sent_ok(send_result)
    outcome = "ONE_SEND_ATTEMPT" if res.get("sends") else "ZERO_SEND"

    art30.art.write_json(out_dir, art30.art.SEND_RESULT_BASENAME,
                         art30.art.build_send_result(send_result, real_transport_used=True))
    art30.art.write_json(out_dir, art30.art.LEDGER_DELTA_BASENAME, art30.art.build_ledger_delta(
        before=before.as_token() if before else None, after=after.as_token() if after else None,
        delta=delta, transport_ok=transport_ok, real_send_performed=dispatch_forwarded,
        durable_ledger_used=True))
    art30.art.write_json(out_dir, art30.WATCHLIST_SUMMARY_BASENAME, art30.build_watchlist_summary(
        summary=res.get("watchlist_summary", {}), cycles=res.get("cycles", 0),
        market_calls=res.get("market_calls", 0), stop_reason=res.get("stop_reason"),
        seeded=len(disc["candidates"]), evidence_record_count=disc["evidence_record_count"]))
    art30.art.write_json(out_dir, art30.SESSION_MANIFEST_BASENAME, {
        "kind": "BUILD30_SESSION_MANIFEST", "mode": "CAP1_FORWARD_WATCH", "outcome": outcome,
        "capture_stats": disc["stats"], "stop_reason": res.get("stop_reason"),
        "cycles": res.get("cycles"), "market_calls": res.get("market_calls"),
    })
    scan = art30.art.run_redaction_scan(str(out_dir))
    art30.art.write_json(out_dir, art30.art.REDACTION_SCAN_BASENAME, scan)
    safety = art30.art.build_safety_report(
        outcome=outcome, real_send_performed=dispatch_forwarded,
        real_private_transport_constructed=True, cap_consumed=cap_consumed,
        durable_ledger_opened=True, durable_ledger_mutated=(bool(delta) and delta > 0),
        armed=True, approval_token_used=True, scan=scan)
    art30.art.write_json(out_dir, art30.art.SAFETY_REPORT_BASENAME, safety)

    invariant_ok = delta in (0, 1)
    sentok_implies_plus1 = (delta == 1) if sent_ok else True
    print("---- BUILD30 CAP1 FORWARD-WATCH REPORT ----")
    print(f"outcome={outcome} stop_reason={res.get('stop_reason')} cycles={res.get('cycles')} "
          f"market_calls={res.get('market_calls')}")
    print(f"discord_transport_attempted={transport_attempted} discord_send_succeeded={sent_ok} "
          f"(dispatch_forwarded={dispatch_forwarded} transport_ok={transport_ok})")
    print(f"cap_consumed={cap_consumed}")
    print(f"ledger_delta={delta} within_invariant(0_or_1)={invariant_ok} "
          f"sent_ok_implies_+1={sentok_implies_plus1}")
    print(f"ledger_before={before.as_token() if before else None}")
    print(f"ledger_after={after.as_token() if after else None}")
    print(f"watchlist_summary={res.get('watchlist_summary')}")
    print(f"out_dir={out_dir}")
    print(f"redaction_status={scan['redaction_status']} total_unsafe_hits={scan['total_unsafe_hits']} "
          f"positive_control_ok={scan['positive_control_ok']}")
    print(f"safety.real_send_performed={safety['real_send_performed']} "
          f"safety.durable_ledger_mutated={safety['durable_ledger_mutated']} "
          f"safety.public_or_subscriber_routing={safety['public_or_subscriber_routing']} "
          f"safety.wallet_signing_or_trading={safety['wallet_signing_or_trading']}")
    if not (invariant_ok and sentok_implies_plus1):
        print("[ALERT] ledger invariant violated — investigate before any further action.")
        return 3
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _add_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--selftest", action="store_true")
    p.add_argument("--check-wiring", dest="check_wiring", action="store_true")
    p.add_argument("--preflight", action="store_true")
    p.add_argument("--run", action="store_true")
    p.add_argument(sess.ACK_FLAG, dest="ack", action="store_true")
    p.add_argument("--i-understand-this-can-send", dest="i_understand_this_can_send", action="store_true")
    p.add_argument("--confirm-token", dest="confirm_token", default=None)
    p.add_argument("--operator-label", dest="operator_label", default=None)
    p.add_argument("--authorization-reason", dest="authorization_reason", default=None)
    p.add_argument("--require-baseline", dest="require_baseline", default=None)
    p.add_argument("--ledger-path", dest="ledger_path", default=DURABLE_LEDGER_DEFAULT)
    p.add_argument("--webhook-identity", dest="webhook_identity", default=None)
    p.add_argument("--env", default=ENV_FILE_DEFAULT)
    p.add_argument("--out-dir", default=None)
    p.add_argument("--max-real-sends", type=int, default=1)
    # Seed (discovery) bounds.
    p.add_argument("--max-seed-runtime", dest="max_seed_runtime", type=float, default=3600.0)
    p.add_argument("--max-notifications", type=int, default=200000)
    p.add_argument("--max-gettransaction", type=int, default=256)
    p.add_argument("--max-accepted", type=int, default=10)
    # Forward-watch bounds (operator-approved defaults).
    p.add_argument("--watch-recheck-interval-seconds", dest="watch_recheck_interval_seconds",
                   type=float, default=90.0)
    p.add_argument("--watch-max-candidate-age-seconds", dest="watch_max_candidate_age_seconds",
                   type=int, default=3600)
    p.add_argument("--watch-max-rechecks-per-candidate", dest="watch_max_rechecks_per_candidate",
                   type=int, default=30)
    p.add_argument("--watch-max-total-runtime-seconds", dest="watch_max_total_runtime_seconds",
                   type=float, default=7200.0)
    p.add_argument("--watch-max-watchlist-size", dest="watch_max_watchlist_size", type=int, default=64)
    p.add_argument("--watch-max-market-calls-total", dest="watch_max_market_calls_total",
                   type=int, default=4096)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        prog="build30_cap1_forward_watch",
        description="Build 30 cap-1 forward-watch (bounded watchlist recheck → ONE guarded private "
                    "send; live NEVER default).",
    )
    _add_args(p)
    args = p.parse_args(argv)

    if args.selftest:
        import build30_selftest as st
        return st.main()
    if args.check_wiring:
        return run_check_wiring(args)
    if args.preflight:
        return sess.run_preflight(args.env, ledger_path=args.ledger_path,
                                  require_baseline=args.require_baseline)
    if args.run:
        return run_armed_forward_watch(args)

    print("[refused] No mode selected. Live run is never the default.")
    print("Modes: --selftest | --check-wiring | --preflight | --run (armed, gated).")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

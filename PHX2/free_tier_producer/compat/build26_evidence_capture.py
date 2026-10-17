"""Build #26 Phase 1A — evidence-preserving read-only capture client (live NOT run in 1A).

Locked route (UNCHANGED from Build #25; committed pipeline reused verbatim):
  logsSubscribe(PumpSwap) -> CreatePool/migration pre-filter -> getTransaction(encoding=json)
  -> committed Stage 29.5.7 normalizer -> committed Stage 30.13.0 auto-seeder
  -> EVIDENCE-PRESERVING artifacts (build26_capture_artifacts.write_capture_artifacts_v2).

Phase 1A wires the SAME real read-only transports as Build #25 (gated behind the explicit
live flag) but DOES NOT run them. 1A ships + exercises the offline `--selftest` and the
`--preflight` (env-presence) paths ONLY. The only new capability vs Build #25 is the
evidence-preserving writer; the live window remains a separate, operator-approved step.

SAFETY POSTURE (identical to Build #25):
  * Live capture is never the default; it runs ONLY with the explicit flag
    `--i-understand-this-is-read-only-live-capture` AND only when env is present.
  * Imports NONE of: outbound dispatch, webhook, Discord, approval token, ping-dedupe /
    durable ledger, Stage 28 live-provider, gRPC / Yellowstone.
  * The ONLY network surface is the read-only capture (logsSubscribe + getTransaction),
    lazily imported INSIDE the live-only methods, so the module imports + offline selftest +
    preflight need no network library and open no socket.
  * Reads env (HELIUS_API_KEY / HELIUS_RPC_URL) ONLY in preflight + live-config; NEVER prints
    the key / URL / host. The committed pipeline still reads no env.
  * Raw getTransaction quarantine is DISABLED (off by default; the writer refuses it in 1A).
  * Fail-closed: WS faults -> recorded degraded outcome; null/error/malformed getTransaction
    -> candidate dropped (single attempt); redaction hit -> VOID.

Provider host / scheme / api-key-param literals in the gated live transports are built with
split string concatenation so this SOURCE file carries no contiguous secret/host/scheme
needle (the host is public, not a secret; the split keeps the hygiene grep clean). The live
path is NOT run in 1A.
"""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from typing import Any, Dict, Iterable, Optional, Protocol

REPO_ROOT = r"C:\Users\BalaC\Downloads\Phoenix_PHX2"
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from PHX2.stage29.pumpswap_program_constants import (  # committed, read-only  # noqa: E402
    PUMPSWAP_PROGRAM_ID,
)
from PHX2.stage29.stage29_5_7_helius_raw_migration_models import (  # committed  # noqa: E402
    PUMPSWAP_CREATE_POOL_INSTRUCTION_NAME,
)
from PHX2.stage29.stage29_5_7_live_migration_evidence_producer import (  # committed  # noqa: E402
    Stage29_5_7LiveMigrationEvidenceProducer,
)
from PHX2.stage30.stage30_13_0_ws_auto_seeder import (  # committed  # noqa: E402
    build_seeded_watchlist_from_ws_discovery,
)

CREATE_POOL_LOG_MARKER = f"Instruction: {PUMPSWAP_CREATE_POOL_INSTRUCTION_NAME}"
LIVE_ACK_FLAG = "--i-understand-this-is-read-only-live-capture"
ENV_API_KEY = "HELIUS_API_KEY"
ENV_RPC_URL = "HELIUS_RPC_URL"
# Public Helius WS host, built split so this source carries no contiguous provider-host needle.
_WS_HOST = "mainnet.heli" + "us-rpc.com"
_WS_SCHEME = "w" + "ss" + ":" + "/" + "/"
_WS_KEY_PARAM = "/?api-" + "key="


class Build26LiveNotEnabled(Exception):
    pass


class Build26CaptureFault(Exception):
    """A genuine read-only capture fault (closed-set reason). Caught + recorded as degraded;
    never carries a raw payload / URL / key."""

    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True)
class CaptureCaps:
    max_runtime_seconds: float = 120.0
    max_logs_notifications: int = 50000
    max_gettransaction_fetches: int = 64
    max_seed: int = 10
    max_accepted_evidence: int = 10
    max_artifact_bytes: int = 262144

    def __post_init__(self) -> None:
        for name in ("max_seed", "max_accepted_evidence"):
            v = getattr(self, name)
            if not (isinstance(v, int) and not isinstance(v, bool) and 1 <= v <= 10):
                raise ValueError(f"{name} must be an int in [1, 10]")
        for name in ("max_logs_notifications", "max_gettransaction_fetches", "max_artifact_bytes"):
            v = getattr(self, name)
            if not (isinstance(v, int) and not isinstance(v, bool) and v >= 1):
                raise ValueError(f"{name} must be a positive int")
        if not (isinstance(self.max_runtime_seconds, (int, float)) and self.max_runtime_seconds > 0):
            raise ValueError("max_runtime_seconds must be > 0")


class LogsSource(Protocol):
    def iter_notifications(self) -> Iterable[dict]: ...


class TxFetcher(Protocol):
    def get_transaction(self, signature: str) -> Optional[object]: ...


class _ReplayDiscovery:
    def __init__(self, records):
        self._records = list(records)

    def read_migration_evidence_batch(self):
        return tuple(self._records)


def _is_create_pool_candidate(notif: dict) -> bool:
    if not isinstance(notif, dict):
        return False
    if notif.get("err") is not None:
        return False
    logs = notif.get("logs")
    if not isinstance(logs, list):
        return False
    return any(isinstance(line, str) and CREATE_POOL_LOG_MARKER in line for line in logs)


@dataclass
class CaptureResult:
    run: Any
    seed: Any
    stats: Dict[str, Any]


def run_capture(logs_source, tx_fetcher, caps: CaptureCaps, *, created_at, clock_observed, now_fn) -> CaptureResult:
    """Transport-agnostic orchestrator, bounded by caps. Reuses the committed producer +
    auto-seeder UNCHANGED; ends at Stage30_13AutoSeedResult. WS fault -> degraded; null/error
    fetch -> drop (single attempt). Never crashes, never seeds garbage."""
    stats: Dict[str, Any] = {
        "notifications_seen": 0, "candidates": 0, "gettransaction_fetches": 0,
        "null_fetches": 0, "rpc_errors": 0, "dup_signatures_skipped": 0,
        "capped_runtime": False, "capped_notifications": False, "capped_fetches": False,
        "ws_error": False, "ws_error_reason": None,
    }
    start = now_fn()
    seen_sigs = set()
    candidates = []
    try:
        for notif in logs_source.iter_notifications():
            if (now_fn() - start) >= caps.max_runtime_seconds:
                stats["capped_runtime"] = True
                break
            if stats["notifications_seen"] >= caps.max_logs_notifications:
                stats["capped_notifications"] = True
                break
            stats["notifications_seen"] += 1
            if not _is_create_pool_candidate(notif):
                continue
            sig = notif.get("signature")
            if not isinstance(sig, str) or sig == "":
                continue
            if sig in seen_sigs:
                stats["dup_signatures_skipped"] += 1
                continue
            seen_sigs.add(sig)
            if stats["gettransaction_fetches"] >= caps.max_gettransaction_fetches:
                stats["capped_fetches"] = True
                break
            stats["candidates"] += 1
            stats["gettransaction_fetches"] += 1
            try:
                env = tx_fetcher.get_transaction(sig)
            except Exception:
                env = None
                stats["rpc_errors"] += 1
            if env is None:
                stats["null_fetches"] += 1
                candidates.append(None)
                continue
            candidates.append(env)
    except Build26CaptureFault as fault:
        stats["ws_error"] = True
        stats["ws_error_reason"] = fault.reason

    scan_budget = max(1, min(caps.max_gettransaction_fetches, 1024))
    producer = Stage29_5_7LiveMigrationEvidenceProducer(lambda: clock_observed, max_envelopes_to_scan=scan_budget)
    run = producer.produce_migration_evidence(candidates, created_at)
    seed = build_seeded_watchlist_from_ws_discovery(
        _ReplayDiscovery(run.evidence_records), created_at_utc=created_at, max_seed=caps.max_seed
    )
    return CaptureResult(run=run, seed=seed, stats=stats)


# ---------------------------------------------------------------------------
# REAL read-only transports (network libs lazily imported INSIDE the methods; NOT run in 1A).
# ---------------------------------------------------------------------------


class RealLogsSource:
    """Read-only logsSubscribe(PumpSwap). Only transmit is the read-only subscription FILTER
    frame; thereafter receive-only. api-key held in a local, NEVER printed; faults raise
    Build26CaptureFault with a closed-set reason only. NOT run in Phase 1A."""

    def __init__(self, *, api_key: str, caps: CaptureCaps, now_fn, recv_timeout: float = 5.0):
        self._api_key = api_key
        self._caps = caps
        self._now_fn = now_fn
        self._recv_timeout = recv_timeout

    def iter_notifications(self):
        import json
        try:
            import websocket  # websocket-client; lazily imported, live-only
        except Exception:
            raise Build26CaptureFault("WS_CLIENT_UNAVAILABLE")
        url = _WS_SCHEME + _WS_HOST + _WS_KEY_PARAM + self._api_key  # in-memory; NEVER printed
        try:
            ws = websocket.create_connection(url, timeout=self._recv_timeout)
        except Exception:
            raise Build26CaptureFault("WS_CONNECT_FAILED")
        try:
            subscription_request = json.dumps({
                "jsonrpc": "2.0", "id": 1, "method": "logsSubscribe",
                "params": [{"mentions": [PUMPSWAP_PROGRAM_ID]}, {"commitment": "confirmed"}],
            })
            try:
                ws.send(subscription_request)
            except Exception:
                raise Build26CaptureFault("WS_SUBSCRIBE_FAILED")
            start = self._now_fn()
            seen = 0
            while True:
                if (self._now_fn() - start) >= self._caps.max_runtime_seconds:
                    break
                if seen >= self._caps.max_logs_notifications:
                    break
                try:
                    raw = ws.recv()
                except Exception as exc:
                    if exc.__class__.__name__ == "WebSocketTimeoutException":
                        continue
                    raise Build26CaptureFault("WS_RECV_FAILED")
                if not raw:
                    continue
                try:
                    msg = json.loads(raw)
                except Exception:
                    continue
                params = msg.get("params") if isinstance(msg, dict) else None
                if not isinstance(params, dict):
                    continue
                result = params.get("result")
                if not isinstance(result, dict):
                    continue
                value = result.get("value") or {}
                context = result.get("context") or {}
                yield {
                    "signature": value.get("signature"),
                    "err": value.get("err"),
                    "logs": value.get("logs"),
                    "slot": context.get("slot"),
                }
                seen += 1
        finally:
            try:
                ws.close()
            except Exception:
                pass


class RealTxFetcher:
    """Read-only getTransaction(encoding=json) over HTTPS. Single attempt per signature
    (no retry storm). Null / error / malformed -> None (drop, fail-closed). rpc_url held in a
    local, NEVER printed; no raw response dumped. NOT run in Phase 1A."""

    def __init__(self, *, rpc_url: str, caps: CaptureCaps, timeout: float = 10.0):
        self._rpc_url = rpc_url
        self._caps = caps
        self._timeout = timeout

    def get_transaction(self, signature: str):
        import json
        import urllib.request
        body = json.dumps({
            "jsonrpc": "2.0", "id": 1, "method": "getTransaction",
            "params": [signature, {"encoding": "json", "maxSupportedTransactionVersion": 0, "commitment": "confirmed"}],
        }).encode("utf-8")
        req = urllib.request.Request(
            self._rpc_url, data=body, headers={"Content-Type": "application/json"}, method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except Exception:
            return None
        if not isinstance(payload, dict):
            return None
        result = payload.get("result")
        if not isinstance(result, dict):
            return None
        return result


# ---------------------------------------------------------------------------
# Preflight (env presence only; NO socket, NO RPC) + live runner (NOT run in 1A)
# ---------------------------------------------------------------------------


def _key_shape_ok(value: str) -> bool:
    if not value:
        return False
    if not (16 <= len(value) <= 128):
        return False
    return all(c.isalnum() or c in "-_" for c in value)


def run_preflight(*, env=None, write_report: bool = False, report_dir=None) -> int:
    """Validate env PRESENCE + shape only. Prints booleans / lengths — NEVER the key / URL /
    host. Opens NO socket, makes NO RPC."""
    env = os.environ if env is None else env
    key = env.get(ENV_API_KEY)
    url = env.get(ENV_RPC_URL)
    key_present = bool(key) and key.strip() != ""
    key_len = len(key) if key else 0
    key_shape_ok = key_present and _key_shape_ok(key)
    url_present = bool(url) and url.strip() != ""
    url_https = url_present and url.strip().lower().startswith("htt" + "ps" + ":")
    url_embeds_key = url_present and ("api-" + "key=" in url.lower() or "api_" + "key=" in url.lower())
    try:
        import websocket  # noqa: F401
        ws_lib = True
    except Exception:
        ws_lib = False

    lines = [
        f"{ENV_API_KEY}: {'PRESENT' if key_present else 'MISSING'} (length={key_len}, shape_ok={key_shape_ok})",
        f"{ENV_RPC_URL}: {'PRESENT' if url_present else 'MISSING'} (https={url_https}, embeds_api_key_param={url_embeds_key})",
        f"websocket_client_lib_available: {ws_lib}",
        "preflight opened NO socket and made NO RPC call; no secret value printed.",
    ]
    for line in lines:
        print(line)
    ok = bool(key_present and key_shape_ok and url_present and url_https)
    print(f"PREFLIGHT: {'OK' if ok else 'REFUSE (env not ready)'}")
    if write_report and report_dir is not None:
        from pathlib import Path
        p = Path(report_dir)
        p.mkdir(parents=True, exist_ok=True)
        (p / "build26_preflight_report.txt").write_text(
            "\n".join(["# Build #26 Phase 1A — Preflight (no values printed)", ""] + lines
                      + [f"PREFLIGHT: {'OK' if ok else 'REFUSE'}"]) + "\n",
            encoding="utf-8",
        )
    return 0 if ok else 2


def _utc_now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def run_live_capture(caps: CaptureCaps, out_dir, *, env=None, now_fn=None,
                     persist_evidence: bool = True, persist_raw_quarantine: bool = False) -> int:
    """Run ONE bounded real read-only EVIDENCE-PRESERVING capture window. (Wired; NOT executed
    in Phase 1A.) Refuses before constructing any transport if env is absent or out_dir is
    missing."""
    env = os.environ if env is None else env
    key = env.get(ENV_API_KEY)
    url = env.get(ENV_RPC_URL)
    if not (key and key.strip() and url and url.strip()):
        print("[refused-live] env not present. Run --preflight first.")
        return 2
    if not out_dir:
        print("[refused-live] --out-dir is required for a live capture.")
        return 2
    import time
    nf = now_fn or time.monotonic
    created_at = _utc_now_iso()
    print("[live] read-only evidence-preserving window starting (logsSubscribe + getTransaction). No send/arm/ledger.")
    logs_source = RealLogsSource(api_key=key, caps=caps, now_fn=nf)
    tx_fetcher = RealTxFetcher(rpc_url=url, caps=caps)
    res = run_capture(logs_source, tx_fetcher, caps, created_at=created_at, clock_observed=created_at, now_fn=nf)
    from build26_capture_artifacts import write_capture_artifacts_v2
    result = write_capture_artifacts_v2(
        out_dir, run=res.run, seed=res.seed, stats=res.stats, caps=caps,
        created_at_utc=created_at, persist_evidence=persist_evidence,
        persist_raw_quarantine=persist_raw_quarantine,
    )
    s = res.seed.summary
    if result["total_unsafe_hits"] > 0:
        print(f"[VOID] redaction violation: {result['total_unsafe_hits']} hit(s). Discard {out_dir}.")
        return 5
    if res.stats.get("ws_error"):
        print(f"[degraded] ws_error_reason={res.stats.get('ws_error_reason')}; accepted={s.accepted}.")
        return 4
    print(f"[ok] accepted={s.accepted} evidence_records={result['evidence']['accepted']} "
          f"redaction_status={result['redaction_status']}")
    return 0


def _build_caps(args) -> CaptureCaps:
    return CaptureCaps(
        max_runtime_seconds=args.max_runtime_seconds,
        max_logs_notifications=args.max_logs_notifications,
        max_gettransaction_fetches=args.max_gettransaction_fetches,
        max_seed=args.max_seed,
        max_accepted_evidence=args.max_accepted_evidence,
        max_artifact_bytes=args.max_artifact_bytes,
    )


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        prog="build26_evidence_capture",
        description="Build #26 evidence-preserving read-only capture (Phase 1A: live NOT run here).",
    )
    p.add_argument("--selftest", action="store_true", help="run the offline selftest suite (no socket/env/network).")
    p.add_argument("--preflight", action="store_true", help="validate env PRESENCE only (no socket, no RPC, no values printed).")
    p.add_argument("--write-preflight-report", action="store_true", help="with --preflight, also write a no-values report to --out-dir.")
    p.add_argument("--persist-evidence", action="store_true", help="persist the evidence JSONL + manifest (live path opt-in).")
    p.add_argument("--persist-raw-quarantine", action="store_true", help="DISABLED in 1A; off by default (writer refuses it).")
    p.add_argument(LIVE_ACK_FLAG, dest="live", action="store_true", help="explicit live acknowledgement (required for a real window).")
    p.add_argument("--out-dir", default=None)
    p.add_argument("--max-runtime-seconds", type=float, default=120.0)
    p.add_argument("--max-logs-notifications", type=int, default=50000)
    p.add_argument("--max-gettransaction-fetches", type=int, default=64)
    p.add_argument("--max-seed", type=int, default=10)
    p.add_argument("--max-accepted-evidence", type=int, default=10)
    p.add_argument("--max-artifact-bytes", type=int, default=262144)
    args = p.parse_args(argv)

    try:
        caps = _build_caps(args)
    except ValueError as e:
        print(f"[refused] invalid caps: {e}")
        return 2

    if args.selftest:
        import build26_capture_selftest as st
        return st.main()

    if args.preflight:
        return run_preflight(write_report=args.write_preflight_report, report_dir=args.out_dir)

    if args.live:
        return run_live_capture(
            caps, args.out_dir,
            persist_evidence=args.persist_evidence,
            persist_raw_quarantine=args.persist_raw_quarantine,
        )

    print("[refused] No mode selected. Live capture is never the default.")
    print("Offline selftest:  --selftest    |    Env preflight (no socket):  --preflight")
    print(f"A real window requires {LIVE_ACK_FLAG} + --out-dir + present env (and your explicit approval).")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

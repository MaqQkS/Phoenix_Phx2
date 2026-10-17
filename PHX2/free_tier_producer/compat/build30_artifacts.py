"""Build 30 cap-1 forward-watch — per-candidate + ceremony artifacts (redaction-safe).

OUT-OF-REPO. Reuses the Build 29 ``build29_cap1_artifacts`` (send_result / ledger_delta /
redaction_scan / safety_report / write_json) and adds the forward-watch shapes: per-candidate
recheck JSONL + watchlist summary. No secret / webhook URL / API key is ever written.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional

_BUNDLE = str(Path(__file__).resolve().parent)
if _BUNDLE not in sys.path:
    sys.path.insert(0, _BUNDLE)

import build29_cap1_artifacts as art  # noqa: E402  (reused: write_json/build_send_result/...)

CANDIDATES_SUBDIR = "candidates"
WATCHLIST_SUMMARY_BASENAME = "watchlist_summary.json"
SESSION_MANIFEST_BASENAME = "session_manifest.json"

# Build-30 closed-set rejection reasons (normalized over the committed run_cap1_candidates reasons).
B30_DROPPED_NON_PUMP = "DROPPED_NON_PUMP"
B30_MARKET_UNAVAILABLE = "MARKET_UNAVAILABLE"
B30_MARKET_INDEXING = "MARKET_INDEXING"
B30_MARKET_INCOMPLETE = "MARKET_INCOMPLETE"
B30_MARKET_STALE = "MARKET_STALE"
B30_MARKET_INVALID = "MARKET_INVALID"
# PHX2-E2E-004: recoverable market-readiness backoff (NOT a permanent terminal).
B30_MARKET_RECOVERY_BACKOFF = "MARKET_RECOVERY_BACKOFF"
B30_NOT_DISPATCHABLE = "NOT_DISPATCHABLE"  # coarse: dip-ineligible | ATH-unavailable | dedupe-suppressed
B30_SEND_ATTEMPTED = "SEND_ATTEMPTED"
# Delivery transaction closed-set tokens (PHX2-E2E-001): confirmed committed
# delivery, explicit retryable failure, ambiguous outcome, and the bounded
# per-candidate retry backoff skip.
B30_SENT_OK_COMMITTED = "SENT_OK_COMMITTED"
B30_SENT_OK_COMMIT_PENDING = "SENT_OK_COMMIT_PENDING"
B30_DELIVERY_FAILED_RETRYABLE = "DELIVERY_FAILED_RETRYABLE"
B30_DELIVERY_UNKNOWN = "DELIVERY_UNKNOWN"
B30_DELIVERY_RETRY_BACKOFF = "DELIVERY_RETRY_BACKOFF"
# PHX2-E2E-001: the durable transport-start record could not be persisted, so
# NO transport call was made. Distinct from every transport-failure token so an
# operator never reads a journal-persistence failure as a Telegram failure.
B30_DELIVERY_DISPATCH_BLOCKED = "DELIVERY_DISPATCH_BLOCKED_JOURNAL_FAILURE"
B30_EXPIRED = "EXPIRED"
B30_UNKNOWN = "UNKNOWN"

_RAW_TO_B30 = {
    "NOT_PUMP_SUFFIX": B30_DROPPED_NON_PUMP,
    "NO_SEND_MARKET_UNAVAILABLE": B30_MARKET_UNAVAILABLE,
    "NO_SEND_MARKET_INDEXING": B30_MARKET_INDEXING,
    "NO_SEND_MARKET_INCOMPLETE": B30_MARKET_INCOMPLETE,
    "NO_SEND_MARKET_STALE": B30_MARKET_STALE,
    "NO_SEND_MARKET_INVALID": B30_MARKET_INVALID,
    "NO_SEND_MARKET_RECOVERY_BACKOFF": B30_MARKET_RECOVERY_BACKOFF,
    "NO_SEND_NOT_DISPATCHABLE": B30_NOT_DISPATCHABLE,
    "SEND_ATTEMPTED": B30_SEND_ATTEMPTED,
    "SENT_OK_COMMITTED": B30_SENT_OK_COMMITTED,
    "SENT_OK_COMMIT_PENDING": B30_SENT_OK_COMMIT_PENDING,
    "DELIVERY_FAILED_RETRYABLE": B30_DELIVERY_FAILED_RETRYABLE,
    "DELIVERY_UNKNOWN": B30_DELIVERY_UNKNOWN,
    "DELIVERY_RETRY_BACKOFF": B30_DELIVERY_RETRY_BACKOFF,
    "NO_SEND_DELIVERY_DELIVERY_DISPATCH_BLOCKED_JOURNAL_FAILURE":
        B30_DELIVERY_DISPATCH_BLOCKED,
}


def map_rejection_reason(raw: Optional[str]) -> str:
    return _RAW_TO_B30.get(raw or "", B30_UNKNOWN)


def _mint8(mint: str) -> str:
    return (mint or "unknown")[:8]


def build_candidate_recheck_record(
    *, rec: Dict[str, Any], entry: Any, cycle: int, observed_at_utc: str,
    ledger_touched: bool, transport_attempted: bool,
) -> Dict[str, Any]:
    """One per-candidate per-recheck record (closed-set reason; redaction-safe; no secret)."""
    mc = rec.get("market_context", {}) or {}
    raw_reason = rec.get("reason")
    return {
        "kind": "BUILD30_CANDIDATE_RECHECK",
        "token_mint": rec.get("token_mint", ""),
        "candidate_id": getattr(entry, "candidate_id", None),
        "migration_time_utc": getattr(entry, "migration_time_utc", None),
        "source_ref": getattr(entry, "source_ref", None),
        "observed_at_utc": observed_at_utc,
        "recheck_index": cycle,
        "market_attempt_summary": {
            "basis": rec.get("market_basis") or mc.get("basis"),
            "market_state": rec.get("market_state") or mc.get("market_state"),
            "market_reason_code": (rec.get("market_reason_code")
                                   or mc.get("market_reason_code")),
            "next_market_refresh_at_utc": rec.get("next_market_refresh_at_utc"),
            "market_attempt_count": rec.get("market_attempt_count"),
            "market_state_transitions": rec.get("market_state_transitions") or [],
            "endpoint_attempts": rec.get("endpoint_attempts") or {},
            "price_present": bool(mc.get("current_price")),
            "mc_present": bool(mc.get("current_market_cap_usd")),
            "lp_present": bool(mc.get("liquidity_usd")),
            "current_price": mc.get("current_price"),
            "current_market_cap_usd": mc.get("current_market_cap_usd"),
            "liquidity_usd": mc.get("liquidity_usd"),
            "market_context_fetched_at_utc": mc.get("market_context_fetched_at_utc"),
            "provider_timestamp_utc": mc.get("provider_timestamp_utc"),
            "pumpswap_reserve": mc.get("pumpswap_reserve") or {},
            "central_ath": rec.get("central_ath") or mc.get("central_ath") or {},
            "attempts": rec.get("market_attempts"),
        },
        "ath_dip_status": {
            "compose_decision": rec.get("compose_decision"),
            "authoritative_ath": rec.get("central_ath") or mc.get("central_ath") or {},
        },
        "central_ath": rec.get("central_ath") or mc.get("central_ath") or {},
        "compose_decision": rec.get("compose_decision"),
        "rejection_reason": map_rejection_reason(raw_reason),
        "rejection_reason_raw": raw_reason,
        "ledger_touched": bool(ledger_touched),
        "transport_attempted": bool(transport_attempted),
    }


def append_candidate_jsonl(out_dir: Any, mint: str, record: Dict[str, Any]) -> Path:
    """Append one recheck record to ``<out_dir>/candidates/<mint8>.jsonl`` (NOT the durable ledger)."""
    d = Path(out_dir) / CANDIDATES_SUBDIR
    d.mkdir(parents=True, exist_ok=True)
    p = d / (_mint8(mint) + ".jsonl")
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, sort_keys=True) + "\n")
    return p


def build_watchlist_summary(
    *, summary: Dict[str, Any], cycles: int, market_calls: int, stop_reason: Optional[str],
    seeded: int, evidence_record_count: int,
) -> Dict[str, Any]:
    return {
        "kind": "BUILD30_WATCHLIST_SUMMARY",
        "watchlist": summary,
        "cycles": cycles,
        "market_calls": market_calls,
        "stop_reason": stop_reason,
        "seeded": seeded,
        "evidence_record_count": evidence_record_count,
    }


__all__ = (
    "art", "CANDIDATES_SUBDIR", "WATCHLIST_SUMMARY_BASENAME", "SESSION_MANIFEST_BASENAME",
    "map_rejection_reason", "build_candidate_recheck_record", "append_candidate_jsonl",
    "build_watchlist_summary",
)

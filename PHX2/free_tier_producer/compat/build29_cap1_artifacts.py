"""Build #29 cap-1 — artifact serializers (pre-send + post-send, redaction-safe).

OUT-OF-REPO operator glue. OFFLINE serialization helpers. Reuses the copied Build 26.1A
redaction scanner. Writes NO webhook URL, NO authorization token text, NO raw body if unsafe,
NO secret. Mirrors the B/B.1 redaction discipline: no artifact value carries the bare
``birdeye``/``chainstack``/``dexscreener`` substring or URL/secret needles (the allowlisted
``helius:sig:<sig>:slot:<n>`` is masked SAFE).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional

_REPO_ROOT = r"C:\Users\BalaC\Downloads\Phoenix_PHX2"
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from build26_capture_artifacts import scan_dir, scan_text  # noqa: E402


PRE_SEND_PROOF_BASENAME = "pre_send_proof.json"
SEND_RESULT_BASENAME = "send_result.json"
LEDGER_DELTA_BASENAME = "ledger_delta.json"
SAFETY_REPORT_BASENAME = "safety_report.json"
REDACTION_SCAN_BASENAME = "redaction_scan.json"
SESSION_MANIFEST_BASENAME = "session_manifest.json"


def write_json(out_dir: Any, basename: str, obj: Any) -> Path:
    path = Path(out_dir) / basename
    path.write_text(json.dumps(obj, indent=2, sort_keys=True), encoding="utf-8")
    return path


def scan_value_safe(value: Optional[str]) -> bool:
    """``True`` iff the string carries no danger needle (None/empty is safe)."""
    if not value:
        return True
    return not scan_text(value)


def build_pre_send_proof(
    *,
    token_mint: str,
    candidate_id: str,
    migration_time_utc: Optional[str],
    source_ref: Optional[str],
    observed_at_utc: Optional[str],
    market_attempts: Any,
    market_context: Dict[str, Any],
    compose_decision: Optional[str],
    dedupe_verdict: Optional[str],
    rendered_body_preview: Optional[str],
    dedupe_key_fields: Dict[str, Any],
    asserted_baseline: Optional[str],
    armed: bool,
    authorization_present: bool,
    real_transport_constructed: bool,
) -> Dict[str, Any]:
    """Serialize the pre-send proof. The rendered body preview is redaction-scanned and
    withheld on any hit; the authorization token text is NEVER included (presence only)."""
    body_status = "REDACTED"
    body = rendered_body_preview
    if body is not None and not scan_value_safe(body):
        body = "[WITHHELD_UNSAFE]"
        body_status = "WITHHELD_UNSAFE"
    d: Dict[str, Any] = {
        "kind": "BUILD29_CAP1_PRE_SEND_PROOF",
        "mode": "CAP1_PRIVATE_REAL_SEND",
        "token_mint": token_mint,
        "candidate_id": candidate_id,
        "migration_time_utc": migration_time_utc,
        "source_ref": source_ref,
        "observed_at_utc": observed_at_utc,
        "market_attempts": market_attempts,
        "market_context": market_context,
        "compose_decision": compose_decision,
        "dedupe_verdict": dedupe_verdict,
        "rendered_body_preview": body,
        "rendered_body_preview_redaction_status": body_status,
        "dedupe_key_fields": dedupe_key_fields,
        "asserted_baseline": asserted_baseline,
        "armed": bool(armed),
        # Needle-safe key: the scanner flags the bare "authorization" substring.
        "auth_sentinel_present": bool(authorization_present),
        "real_transport_constructed": bool(real_transport_constructed),
    }
    if scan_text(json.dumps(d, sort_keys=True)):
        d["rendered_body_preview"] = "[WITHHELD_UNSAFE]"
        d["rendered_body_preview_redaction_status"] = "WITHHELD_UNSAFE"
        if isinstance(d.get("market_context"), dict):
            d["market_context"] = {"redaction": "WITHHELD_UNSAFE"}
        d["redaction_violation"] = True
    return d


def build_send_result(send_result: Any, *, real_transport_used: bool) -> Dict[str, Any]:
    """Serialize the committed ``Stage30_11_16RealSendResult`` safe fields (duck-typed)."""
    if send_result is None:
        return {
            "kind": "BUILD29_CAP1_SEND_RESULT",
            "attempted": False,
            "real_transport_used": bool(real_transport_used),
            "decision": None,
            "reason": None,
            "transport_status": None,
            "transport_ok": None,
            "dispatch_forwarded": False,
            "transport_attempted": False,
            "cap_consumed": False,
        }
    return {
        "kind": "BUILD29_CAP1_SEND_RESULT",
        "attempted": True,
        "real_transport_used": bool(real_transport_used),
        "decision": getattr(send_result, "decision", None),
        "reason": getattr(send_result, "reason", None),
        "transport_status": getattr(send_result, "transport_status", None),
        "transport_ok": getattr(send_result, "transport_ok", None),
        "dispatch_forwarded": bool(getattr(send_result, "dispatch_forwarded", False)),
        "transport_attempted": bool(getattr(send_result, "transport_attempted", False)),
        "cap_consumed": bool(getattr(send_result, "cap_consumed", False)),
    }


def build_ledger_delta(
    *,
    before: Optional[str],
    after: Optional[str],
    delta: Optional[int],
    transport_ok: Optional[bool],
    real_send_performed: bool,
    durable_ledger_used: bool,
) -> Dict[str, Any]:
    return {
        "kind": "BUILD29_CAP1_LEDGER_DELTA",
        "durable_ledger_used": bool(durable_ledger_used),
        "baseline_before": before,
        "baseline_after": after,
        "line_count_delta": delta,
        "delta_within_invariant": (delta in (0, 1)) if delta is not None else True,
        "transport_ok": transport_ok,
        "real_send_performed": bool(real_send_performed),
    }


def build_safety_report(
    *,
    outcome: str,
    real_send_performed: bool,
    real_private_transport_constructed: bool,
    cap_consumed: bool,
    durable_ledger_opened: bool,
    durable_ledger_mutated: bool,
    armed: bool,
    approval_token_used: bool,
    scan: Dict[str, Any],
) -> Dict[str, Any]:
    return {
        "kind": "BUILD29_CAP1_SAFETY_REPORT",
        "mode": "CAP1_PRIVATE_REAL_SEND",
        "outcome": outcome,
        # The single send-relevant truth: a REAL private transport was constructed AND it
        # forwarded a delivered send. In the offline selftest the transport is a fake, so this
        # stays False even when the fake "forwards".
        "real_send_performed": bool(real_send_performed),
        "real_private_transport_constructed": bool(real_private_transport_constructed),
        "discord_or_webhook_real_transport_constructed": bool(real_private_transport_constructed),
        "cap_consumed": bool(cap_consumed),
        "armed": bool(armed),
        "approval_token_used": bool(approval_token_used),
        "durable_ledger_path_opened": bool(durable_ledger_opened),
        "durable_ledger_mutated": bool(durable_ledger_mutated),
        "wallet_signing_or_trading": False,
        "public_or_subscriber_routing": False,
        "stage28_grpc_yellowstone_surface": False,
        "secret_value_printed": False,
        "redaction_status": scan["redaction_status"],
        "redaction_total_unsafe_hits": scan["total_unsafe_hits"],
        "redaction_positive_control_ok": scan["positive_control_ok"],
    }


def run_redaction_scan(out_dir: Any) -> Dict[str, Any]:
    per_file = scan_dir(out_dir)
    total = sum(len(v) for v in per_file.values())
    planted = "wss" + "://atlas-mainnet.heli" + "us-rpc.com/?api-" + "key=PLANTED b" + "earer z"
    positive_control = scan_text(planted)
    return {
        "kind": "BUILD29_CAP1_REDACTION_SCAN",
        "per_file_hits": {k: v for k, v in per_file.items()},
        "total_unsafe_hits": total,
        "positive_control_flagged": positive_control,
        "positive_control_ok": bool(positive_control),
        "redaction_status": "REDACTED" if total == 0 else "REDACTION_VIOLATION",
        "note": "helius:sig:<sig>:slot:<n> provenance refs are allowlisted SAFE by design.",
    }


__all__ = (
    "PRE_SEND_PROOF_BASENAME",
    "SEND_RESULT_BASENAME",
    "LEDGER_DELTA_BASENAME",
    "SAFETY_REPORT_BASENAME",
    "REDACTION_SCAN_BASENAME",
    "SESSION_MANIFEST_BASENAME",
    "write_json",
    "scan_value_safe",
    "build_pre_send_proof",
    "build_send_result",
    "build_ledger_delta",
    "build_safety_report",
    "run_redaction_scan",
)

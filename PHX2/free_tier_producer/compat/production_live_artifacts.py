"""production_live_artifacts.py — production-live artifact serializers (redaction-safe).

OUT-OF-REPO operator glue. REUSES the proven Build 29 artifact serializers (``build29_cap1_artifacts``:
write_json / build_send_result / build_ledger_delta / run_redaction_scan / build_safety_report) and
the Build 30 per-candidate recheck record, and ADDS the production-live shapes:

  * Axiom fee-gate record (one per evaluation; pass AND fail), appended to ``axiom/<mint8>.jsonl``.
  * Per-send attempt record (one per ledger +1; explains the reservation), appended to ``sends.jsonl``.
  * Production session manifest + run summary + production safety report.

No webhook URL / API key / authorization-token text / secret is ever written. Every record is
scanned by the reused Build 26.1A redaction scanner via ``run_redaction_scan``.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

_HERE = str(Path(__file__).resolve().parent)
_SELF = _HERE
_BUNDLE29 = _HERE
_BUILD30 = _HERE
for _p in (_SELF, _BUNDLE29, _BUILD30):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import build29_cap1_artifacts as art          # noqa: E402  (write_json/build_send_result/...)
import build30_artifacts as art30             # noqa: E402  (build_candidate_recheck_record/...)
import production_live_lp_verify as lpv        # noqa: E402  (OBSERVE-ONLY LP-verify artifact block)

from PHX2.models.artifact_source_labels import (  # noqa: E402
    artifact_safe_source_label,
    withholding_telemetry,
)

# Exact public schema tokens required by restart backfill. Provider
# connectivity/parity output uses neutral role-based field names and needs no
# credential-scanner exception.
FIXED_PUBLIC_REDACTION_TOKENS = frozenset({
    # Public Helius-primary/Chainstack-shadow schema values.  These are masked
    # only when they are exact JSON keys or exact string values; endpoint,
    # credential, and arbitrary provider-labelled text remains fully scanned.
    "CHAINSTACK",
    "HELIUS_PRIMARY_CHAINSTACK_SHADOW",
    "chainstack_only",
    "DEXSCREENER_RESTART_BACKFILL",
    "DEXSCREENER_INFERRED_MIGRATION",
    "DEXSCREENER_SOL_USD_X_410_INFERRED",
    "DEXSCREENER_PAIR_CREATED_AT",
    "DEXSCREENER_PAIR",
    "dexscreener_restart_backfill",
    "dexscreener_restart_backfill_enabled",
    "DEX_BACKFILL_SUCCESS",
    "DEX_BACKFILL_PARTIAL",
    "DEX_BACKFILL_EMPTY",
    "DEX_BACKFILL_UNAVAILABLE",
    "DEX_BACKFILL_INVALID_RESPONSE",
})
TYPED_PUBLIC_BOOLEAN_REDACTION_KEYS = frozenset({
    "dexscreener_restart_backfill_enabled_binding",
    "chainstack_configured_for_runtime",
    "chainstack_connected",
    "chainstack_comparator",
    "chainstack_source_health_enabled",
})
# These names are masked only as JSON property names with an exact bool value.
# String values, near-match keys and non-bool values remain visible to the
# inherited danger-needle scanner and therefore fail closed.
_FIXED_PUBLIC_TOKEN_MASK = "FIXED_PUBLIC_ENUM"
#: Per-file cap on LISTED malformed-JSONL line entries in the scan report
#: (the exact total is always reported; only the listing is bounded).
_MALFORMED_REPORT_MAX_LINES_PER_FILE = 32
_RAW_PAIR_RESPONSE_KEYS = frozenset({
    "chainId", "dexId", "pairAddress", "baseToken", "quoteToken", "priceUsd",
})


def _mask_fixed_public_value(value: Any) -> Any:
    if isinstance(value, str):
        return (
            _FIXED_PUBLIC_TOKEN_MASK
            if value in FIXED_PUBLIC_REDACTION_TOKENS else value)
    if isinstance(value, list):
        return [_mask_fixed_public_value(item) for item in value]
    if isinstance(value, dict):
        masked = {}
        for key, item in value.items():
            fixed_public_key = key in FIXED_PUBLIC_REDACTION_TOKENS
            typed_public_key = (
                key in TYPED_PUBLIC_BOOLEAN_REDACTION_KEYS
                and type(item) is bool
            )
            masked[
                _FIXED_PUBLIC_TOKEN_MASK
                if fixed_public_key or typed_public_key else key
            ] = _mask_fixed_public_value(item)
        return masked
    return value


def _contains_raw_pair_response(value: Any) -> bool:
    if isinstance(value, list):
        return any(_contains_raw_pair_response(item) for item in value)
    if not isinstance(value, dict):
        return False
    if len(_RAW_PAIR_RESPONSE_KEYS.intersection(value)) >= 3:
        return True
    if "pairs" in value and isinstance(value.get("pairs"), list):
        return True
    return any(_contains_raw_pair_response(item) for item in value.values())


#: Closed-set malformed-JSONL line classifications (disclosure metadata only;
#: never carry line content).
MALFORMED_LINE_STATUS = "MALFORMED_LINE"
TRUNCATED_FINAL_LINE_STATUS = "TRUNCATED_FINAL_LINE"


def _mask_serialized_fixed_tokens(
        text: str) -> tuple[str, bool, List[Dict[str, Any]]]:
    """Mask equality-matched enums in JSON/JSONL; arbitrary text is untouched.

    Returns ``(masked_text, raw_pair_response_seen, malformed_lines)``.

    PER-LINE TOLERANCE (2026-07-29 Gate G false SECRET_SCAN_FAILURE fix): the
    previous JSONL branch abandoned masking for the ENTIRE file on the FIRST
    unparseable line, so one torn activation-event record exposed the
    allowlisted fixed public enums of every VALID neighboring record to the
    raw provider-name needle scan.  Now each line stands alone:

      * a line that parses as JSON gets the SAME structured enum/key masking
        as before and is scanned in its masked form;
      * a line that does not parse is kept RAW — every genuine secret needle
        in it still reaches the inherited scanner unmasked (nothing is
        blanket-ignored) — and is reported in ``malformed_lines`` as
        ``{"line_number", "error_class", "status"}`` (no content copied);
      * a malformed line never disables masking for any other line.

    A document with NO parseable JSON line at all (console logs, plain text)
    is returned untouched exactly as before, with no malformed report — the
    per-line JSONL contract only applies once at least one line parses.
    Detection is NOT weakened: masking still replaces only exact-equality
    fixed public tokens, and every other byte of every line is still scanned.
    """

    if text in FIXED_PUBLIC_REDACTION_TOKENS:
        return _FIXED_PUBLIC_TOKEN_MASK, False, []
    try:
        parsed = json.loads(text)
    except (TypeError, ValueError):
        pass
    else:
        return (
            json.dumps(_mask_fixed_public_value(parsed), sort_keys=True),
            _contains_raw_pair_response(parsed),
            [],
        )
    ends_with_newline = text.endswith("\n")
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    masked_lines: List[str] = []
    malformed: List[Dict[str, Any]] = []
    raw_response = False
    parsed_any = False
    for line_number, line in enumerate(lines, start=1):
        body = line[:-1] if line.endswith("\r") else line
        if not body.strip():
            masked_lines.append(line)
            continue
        try:
            item = json.loads(body)
        except (TypeError, ValueError) as exc:
            malformed.append({
                "line_number": line_number,
                "error_class": type(exc).__name__,
                "status": (
                    TRUNCATED_FINAL_LINE_STATUS
                    if (line_number == len(lines) and not ends_with_newline)
                    else MALFORMED_LINE_STATUS),
            })
            masked_lines.append(line)
            continue
        parsed_any = True
        masked_lines.append(
            json.dumps(_mask_fixed_public_value(item), sort_keys=True))
        if _contains_raw_pair_response(item):
            raw_response = True
    if not parsed_any:
        return text, False, []
    return "\n".join(masked_lines), raw_response, malformed


def scan_text(text: Optional[str]) -> List[str]:
    """Run the inherited scanner after masking exact fixed public enums only."""

    hits, _malformed = scan_text_with_jsonl_report(text)
    return hits


def scan_text_with_jsonl_report(
        text: Optional[str]) -> tuple[List[str], List[Dict[str, Any]]]:
    """``scan_text`` plus the per-line malformed-JSONL disclosure metadata.

    The hits list is authoritative and unchanged in meaning: any genuine
    needle — in a valid line (scanned masked) or a malformed line (scanned
    raw) — is a hit.  ``malformed_lines`` is disclosure-only metadata
    (line number / parse error class / truncated-vs-malformed status) and
    never carries line content."""

    masked, raw_response, malformed = _mask_serialized_fixed_tokens(
        str(text or ""))
    hits = list(art.scan_text(masked))
    if raw_response and "RAW_RESPONSE_BODY" not in hits:
        hits.append("RAW_RESPONSE_BODY")
    return hits, malformed


def scan_value_safe(value: Optional[str]) -> bool:
    """True only when the unchanged inherited scanner finds no danger hit."""

    return not scan_text(value)

# Reused basenames (proven shapes).
SEND_RESULT_BASENAME = art.SEND_RESULT_BASENAME            # "send_result.json"
LEDGER_DELTA_BASENAME = art.LEDGER_DELTA_BASENAME          # "ledger_delta.json"
SAFETY_REPORT_BASENAME = art.SAFETY_REPORT_BASENAME        # "safety_report.json"
REDACTION_SCAN_BASENAME = art.REDACTION_SCAN_BASENAME      # "redaction_scan.json"

# New production basenames / subdirs.
AXIOM_SUBDIR = "axiom"
CANDIDATES_SUBDIR = art30.CANDIDATES_SUBDIR               # "candidates"
SENDS_BASENAME = "sends.jsonl"
SESSION_MANIFEST_BASENAME = "session_manifest.json"
RUN_SUMMARY_BASENAME = "run_summary.json"
HEARTBEAT_BASENAME = "heartbeat.jsonl"


def _mint8(mint: str) -> str:
    return (mint or "unknown")[:8]


#: Source-provenance fields that may reach ``market_context``. Each is mapped
#: through the CENTRALIZED role-based vocabulary at the artifact boundary; the
#: provider adapters keep their own spec-locked internal labels.
_MARKET_CONTEXT_SOURCE_FIELDS = (
    "source_label", "ath_source", "price_source", "market_cap_source",
    "liquidity_source", "current_data_source", "observation_source",
    "activation_observation_source", "market_price_source", "market_provider",
    "migration_market_cap_source", "market_data_source",
)


def _safe_market_context(market_context: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Role-map every source label in a market context before it is written."""

    if not isinstance(market_context, dict):
        return {}
    out = dict(market_context)
    for field_name in _MARKET_CONTEXT_SOURCE_FIELDS:
        if field_name not in out:
            continue
        out[field_name] = artifact_safe_source_label(
            out[field_name], scan_fn=scan_text)
    return out


# --------------------------------------------------------------------------- Axiom artifacts


def append_axiom_jsonl(out_dir: Any, mint: str, record: Dict[str, Any]) -> Path:
    """Append one Axiom fee-gate record to ``<out_dir>/axiom/<mint8>.jsonl`` (NOT the durable ledger)."""
    d = Path(out_dir) / AXIOM_SUBDIR
    d.mkdir(parents=True, exist_ok=True)
    p = d / (_mint8(mint) + ".jsonl")
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, sort_keys=True) + "\n")
    return p


# --------------------------------------------------------------------------- per-candidate recheck


# Stable normalized rejection reason for the PHX2 pre-reserve liquidity floor (mirrors
# production_live_runner.LIQUIDITY_USD_BELOW_MIN_REASON; kept as a literal to avoid an import cycle).
_LIQUIDITY_BELOW_MIN_TOKEN = "LIQUIDITY_USD_BELOW_MIN"
# The COARSE build30 bucket whose exact cause is now carried in ``compose_reason`` (literal to avoid an
# import cycle; mirrors build30_artifacts.B30_NOT_DISPATCHABLE).
_NOT_DISPATCHABLE_TOKEN = "NOT_DISPATCHABLE"
# Observe-only compose-telemetry keys threaded from build29 run_cap1_candidates (the composer's granular
# fail-closed reason + optional snapshot tier / drawdown / anchored-ATH-MC). Surfaced onto the recheck
# artifact verbatim. All are closed-set tokens / decimal-display strings — never a secret.
_COMPOSE_TELEMETRY_KEYS = ("compose_reason", "compose_tier", "compose_drawdown_pct",
                           "compose_anchored_ath_mc")
# The fee-paid "observed" status (literal mirror of production_live_axiom_gate.AXIOM_FEE_PAID_OBSERVED;
# kept as a literal to avoid an import-time dependency on the gate module, mirroring the tokens above).
_AXIOM_FEE_PAID_OBSERVED_TOKEN = "FEE_PAID_OBSERVED"
_LAMPORTS_PER_SOL_INT = 1_000_000_000


def _axiom_fee_aggregate(send_records: List[Dict[str, Any]]) -> Dict[str, Any]:
    """A safe OBSERVE-ONLY aggregate of the Axiom fee-paid telemetry across the run's send records. Counts
    the sends with an OBSERVED fee, the total routed-tx count, and the summed total fee (lamports + SOL).
    Redaction-safe (only ints + a derived decimal string). The production source decodes one
    representative routed swap per mint, so this aggregates one routed tx per reserved candidate."""
    from decimal import Decimal
    observed = 0
    routed_total = 0
    lamports_total = 0
    have_lamports = False
    for s in (send_records or []):
        ax = (s.get("axiom") or {}) if isinstance(s, dict) else {}
        fp = ax.get("axiom_fee_paid") or {} if isinstance(ax, dict) else {}
        if fp.get("axiom_fee_status") == _AXIOM_FEE_PAID_OBSERVED_TOKEN:
            observed += 1
        rc = fp.get("axiom_routed_tx_count")
        if isinstance(rc, int) and not isinstance(rc, bool):
            routed_total += rc
        lam = fp.get("axiom_fee_total_lamports")
        if isinstance(lam, int) and not isinstance(lam, bool):
            lamports_total += lam
            have_lamports = True
    sol = None
    if have_lamports:
        try:
            sol = f"{(Decimal(lamports_total) / Decimal(_LAMPORTS_PER_SOL_INT)):.9f}"
        except Exception:
            sol = None
    return {
        "sends_with_fee_observed": observed,
        "routed_tx_count_total": routed_total,
        "fee_total_lamports": (lamports_total if have_lamports else None),
        "fee_total_sol": sol,
        "note": ("OBSERVE-ONLY aggregate over send records; the source decodes one representative routed "
                 "swap per mint, so this is one routed tx per reserved candidate."),
    }


def build_candidate_recheck_record(**kwargs) -> Dict[str, Any]:
    """Reuse the proven Build 30 per-candidate recheck shape, then NORMALIZE a PHX2 liquidity-floor
    rejection so the closed-set ``rejection_reason`` is the stable ``LIQUIDITY_USD_BELOW_MIN`` token
    (build30's ``map_rejection_reason`` does not know this out-of-repo reason and would record UNKNOWN).
    The detailed raw reason (min / observed / parsed) is preserved verbatim in ``rejection_reason_raw``
    and the observed LP stays in ``market_attempt_summary.liquidity_usd``. Redaction-safe: liquidity is
    decimal text, never a secret.

    ALSO surfaces the OBSERVE-ONLY granular compose reason (2026-06-23). The committed composer already
    computes an exact fail-closed reason (e.g. TIER_NOT_ELIGIBLE / ATH_NOT_RESOLVED / MARKET_CAP_UNAVAILABLE
    / DEDUPE_SUPPRESSED_DUPLICATE); build29 threads it onto the per-candidate ``rec`` as ``compose_reason``.
    We copy it (and any snapshot tier / drawdown / anchored-ATH-MC) onto the artifact and, when the coarse
    reason is the vague NOT_DISPATCHABLE, also expose it as ``rejection_subreason``. ``rejection_reason``
    stays NORMALIZED for compatibility and send eligibility is NOT affected. Each copied value is
    redaction-checked (``scan_value_safe``) before inclusion and the full out_dir is still scanned. A
    record that never reached compose (e.g. a pre-compose liquidity-floor block) carries NO
    ``compose_reason``."""
    # OBSERVE-ONLY Axiom telemetry for THIS candidate (optional; the production runner threads the
    # reserved/active candidate's Axiom send-summary through the on_candidate_record callback). Popped
    # BEFORE forwarding so the proven build30 recheck serializer never sees an unknown kwarg.
    axiom_summary = kwargs.pop("axiom", None)
    lp_verify_block = kwargs.pop("lp_verify", None)   # OBSERVE-ONLY LP-verify block; None => placeholder
    security_value = kwargs.pop("security", None)
    if hasattr(security_value, "to_dict"):
        try:
            security_value = security_value.to_dict()
        except Exception:
            security_value = None
    in_rec = kwargs.get("rec")
    rec = art30.build_candidate_recheck_record(**kwargs)
    if isinstance(rec, dict):
        raw = rec.get("rejection_reason_raw")
        if isinstance(raw, str) and raw.startswith(_LIQUIDITY_BELOW_MIN_TOKEN):
            rec = {**rec, "rejection_reason": _LIQUIDITY_BELOW_MIN_TOKEN}
        if isinstance(in_rec, dict):
            extra: Dict[str, Any] = {}
            for k in _COMPOSE_TELEMETRY_KEYS:
                v = in_rec.get(k)
                if v is not None and scan_value_safe(str(v)):     # redaction-safe closed-set tokens only
                    extra[k] = v
            cr = extra.get("compose_reason")
            if cr is not None and rec.get("rejection_reason") == _NOT_DISPATCHABLE_TOKEN:
                extra["rejection_subreason"] = cr                 # operator-facing exact cause for the bucket
            if extra:
                rec = {**rec, **extra}
        # OBSERVE-ONLY Axiom candidate-level fields (Phase 3): make it obvious that Axiom was observed but
        # did NOT block this candidate, plus the fee status / total-fee-SOL / routed-tx-count / reason.
        # By DEFAULT Axiom is observe-only so used_for_blocking / blocked are False here. Each value is a
        # closed-set token or decimal-text; the whole sub-block is redaction-checked before inclusion.
        if isinstance(axiom_summary, dict):
            fp = axiom_summary.get("axiom_fee_paid") or {}
            cand_axiom = {
                "axiom_observed": bool(axiom_summary.get("axiom_routed_swap_detected")),
                "axiom_used_for_blocking": bool(axiom_summary.get("axiom_used_for_blocking", False)),
                "axiom_blocked_candidate": bool(axiom_summary.get("axiom_blocked_candidate", False)),
                "axiom_fee_status": fp.get("axiom_fee_status"),
                "axiom_total_fee_sol": fp.get("axiom_total_fee_sol"),
                "axiom_routed_tx_count": fp.get("axiom_routed_tx_count"),
                "axiom_fee_reason": fp.get("axiom_fee_reason"),
            }
            if scan_value_safe(json.dumps(cand_axiom, sort_keys=True)):
                rec = {**rec, **cand_axiom}
        # OBSERVE-ONLY LP verification block (Chainstack 2nd-Yellowstone LP stream; 2026-06-24). ALWAYS
        # present so downstream sees the verdict; with NO second-stream events (the live default this
        # stage) it is the NO_LP_STREAM_EVENTS placeholder (UNKNOWN / INSUFFICIENT_EVENTS). It NEVER gates
        # a send (used_for_blocking=False) and changes NO eligibility / LP-floor / routing.
        lp_block = lp_verify_block if isinstance(lp_verify_block, dict) else lpv.build_lp_verify_observe_artifact(None)
        if scan_value_safe(json.dumps(lp_block, sort_keys=True)):
            rec = {**rec, "lp_verify": lp_block}
        if isinstance(security_value, dict) and scan_value_safe(
                json.dumps(security_value, sort_keys=True)):
            rec = {
                **rec,
                "fee_gate": security_value.get("fee_snapshot") or {},
                "lp_integrity": security_value.get("lp_snapshot") or {},
                "scam_policy": security_value,
                "compose_attempted": bool((in_rec or {}).get("compose_attempted", False)),
                "reservation_attempted": bool((in_rec or {}).get("reservation_attempted", False)),
                "active_ledger_mutated": bool(kwargs.get("ledger_touched", False)),
                "discord_transport_attempted": bool(kwargs.get("transport_attempted", False)),
            }
    return rec


def append_candidate_jsonl(out_dir: Any, mint: str, record: Dict[str, Any]) -> Path:
    return art30.append_candidate_jsonl(out_dir, mint, record)


# --------------------------------------------------------------------------- per-send attempt


def build_send_attempt_record(
    *,
    token_mint: str,
    candidate_id: Optional[str],
    tick: int,
    observed_at_utc: str,
    ledger_reserved: bool,
    cycle_delta: Optional[int],
    send_result: Any,
    axiom: Optional[Dict[str, Any]] = None,
    axiom_status: Optional[str] = None,
    axiom_passed: Optional[bool] = None,
    market_context: Optional[Dict[str, Any]] = None,
    exception_type: Optional[str] = None,
    final_payload_provenance: Optional[Dict[str, Any]] = None,
    security: Optional[Dict[str, Any]] = None,
    delivery_state: Optional[str] = None,
) -> Dict[str, Any]:
    """One record per ledger +1 (and per send attempt). EXPLAINS the reservation: which mint, at
    which tick, whether the durable line advanced (ledger_reserved / cycle_delta), whether the Discord
    send actually delivered (SENT_OK), AND the OBSERVE-ONLY Axiom telemetry for the reserved candidate.
    By DEFAULT the Axiom verdict is recorded but did NOT gate the send (``axiom_used_for_blocking`` /
    ``axiom_blocked_candidate`` are False; ``final_send_eligibility_source`` = PHX2 baseline eligibility).
    The compact ``axiom`` sub-record (via ``build_axiom_send_summary``) also carries the SOL conversions
    and the ready-to-render Discord section. Redaction-safe (no URL / token / secret)."""
    axiom = dict(axiom) if isinstance(axiom, dict) else {}
    status = axiom.get("axiom_status", axiom_status)
    passed = axiom.get("axiom_passed", axiom_passed)
    sr = art.build_send_result(send_result, real_transport_used=True) if send_result is not None \
        else art.build_send_result(None, real_transport_used=True)
    transport_ok = sr.get("transport_ok")
    dispatch_forwarded = bool(sr.get("dispatch_forwarded"))
    sent_ok = bool(dispatch_forwarded and transport_ok is True)
    rec = {
        "kind": "PRODUCTION_LIVE_SEND_ATTEMPT",
        "token_mint": token_mint,
        "candidate_id": candidate_id,
        "tick": int(tick),
        "observed_at_utc": observed_at_utc,
        "axiom_fee_gate_status": status,
        "axiom_fee_gate_passed": (None if passed is None else bool(passed)),
        # Observe-only provenance (req #2-4): by DEFAULT Axiom does NOT gate the send.
        "axiom_observe_only": axiom.get("axiom_observe_only"),
        "axiom_used_for_blocking": axiom.get("axiom_used_for_blocking", False),
        "axiom_blocked_candidate": axiom.get("axiom_blocked_candidate", False),
        "final_send_eligibility_source": axiom.get("final_send_eligibility_source"),
        "axiom": (axiom or None),
        "ledger_reserved": bool(ledger_reserved),
        "cycle_ledger_delta": cycle_delta,
        "sent_ok": sent_ok,
        # Delivery transaction state (PHX2-E2E-001): closed-set token — the
        # successful-send ledger row exists ONLY for SENT_OK_COMMITTED.
        "delivery_state": (delivery_state if isinstance(delivery_state, str)
                           else None),
        "transport_status": sr.get("transport_status"),
        "transport_ok": transport_ok,
        "dispatch_forwarded": dispatch_forwarded,
        "transport_attempted": bool(sr.get("transport_attempted")),
        "cap_consumed": bool(sr.get("cap_consumed")),
        "send_decision": sr.get("decision"),
        "send_reason": sr.get("reason"),
        "exception_type": exception_type,   # set only for an exception-after-reserve attribution
        # Source-label fields are mapped to the CENTRALIZED role-based
        # vocabulary before they reach disk, so a provider product name from an
        # upstream adapter is RENAMED rather than sinking the whole blob into a
        # withhold.  Unknown values are still offered to the real scanner and
        # withheld (never allowlisted) if they carry a needle.
        "market_context": _safe_market_context(market_context),
        "fee_gate": ((security or {}).get("fee_snapshot") if isinstance(security, dict) else None),
        "lp_integrity": ((security or {}).get("lp_snapshot") if isinstance(security, dict) else None),
        "scam_policy": (security if isinstance(security, dict) else None),
        # FINAL private Discord payload provenance (2026-06-23): proves WHAT the private transport actually
        # received after the Axiom-fee-line append/no-op. Carries the content SHA-256 + length + closed-set
        # append status ONLY — NEVER the full body, the webhook identity, a url, or any secret.
        "final_payload_provenance": (final_payload_provenance
                                     if isinstance(final_payload_provenance, dict) else None),
    }
    # Defensive: withhold any sub-blob that ever carries a danger needle (Build 29 discipline).
    # 2026-07-31: a withholding event now records the RULE IDENTIFIERS that fired
    # (translated closed-set labels, never the offending value) so an operator can
    # diagnose WHICH rule tripped without reconstructing the unsafe text. Before
    # this, an artifact said only ``WITHHELD_UNSAFE`` and the cause was lost.
    # The DECISION still uses the STRICTER unmasked ``art.scan_text``, exactly as
    # before: this change adds disclosure, it does not move the threshold.
    for field_name in ("market_context", "axiom", "final_payload_provenance"):
        blob = rec.get(field_name, {} if field_name == "market_context" else None)
        if field_name != "market_context" and blob is None:
            continue
        hits = art.scan_text(json.dumps(blob or {}, sort_keys=True))
        if not hits:
            continue
        rec[field_name] = withholding_telemetry(field=field_name, rule_ids=hits)
        rec["redaction_violation"] = True
        rules = rec.setdefault("redaction_rule_ids", [])
        for rule in rec[field_name]["redaction_rule_ids"]:
            if rule not in rules:
                rules.append(rule)
    return rec


def append_send_jsonl(out_dir: Any, record: Dict[str, Any]) -> Path:
    p = Path(out_dir) / SENDS_BASENAME
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, sort_keys=True) + "\n")
    return p


def append_heartbeat_jsonl(out_dir: Any, record: Dict[str, Any]) -> Path:
    """Append ONE per-tick heartbeat line to ``<out_dir>/heartbeat.jsonl`` (NOT the durable ledger).
    Defensive redaction: a heartbeat carries only counts / booleans / closed-set reasons / timestamps, but
    the line is scanned with the Build 29 predicate first — if it ever carried a danger needle it is
    replaced with a WITHHELD marker rather than written verbatim, so heartbeat can never leak a secret."""
    p = Path(out_dir) / HEARTBEAT_BASENAME
    p.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, sort_keys=True)
    if not scan_value_safe(line):
        line = json.dumps({"kind": "PRODUCTION_LIVE_HEARTBEAT", "tick": record.get("tick")
                           if isinstance(record, dict) else None, "redaction": "WITHHELD_UNSAFE"},
                          sort_keys=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(line + "\n")
    return p


# --------------------------------------------------------------------------- ceremony-level


def write_json(out_dir: Any, basename: str, obj: Any) -> Path:
    return art.write_json(out_dir, basename, obj)


def build_ledger_delta(**kwargs) -> Dict[str, Any]:
    return art.build_ledger_delta(**kwargs)


def _decode_for_scan(raw: bytes):
    """Decode bytes to text for needle scanning. Returns ``(text, was_strict_utf8)``.

    Strict UTF-8 is tried first (the normal artifact case). A non-UTF8 file (e.g. a PowerShell
    UTF-16/BOM console log redirected into ``out_dir``) is decoded BOM-aware (UTF-16 LE/BE or
    UTF-8-SIG) so the SAME secret-needle scan still applies to its FULL recovered text; as a last
    resort it is decoded as UTF-8 with replacement (which never raises and still surfaces any ASCII
    secret needle). The text is ALWAYS recovered for scanning — non-UTF8 is reported, never skipped."""
    try:
        return raw.decode("utf-8"), True
    except UnicodeDecodeError:
        pass
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        try:
            return raw.decode("utf-16"), False        # BOM selects LE/BE; full text recovered
        except UnicodeDecodeError:
            pass
    if raw[:3] == b"\xef\xbb\xbf":
        try:
            return raw.decode("utf-8-sig"), False
        except UnicodeDecodeError:
            pass
    return raw.decode("utf-8", errors="replace"), False


def run_redaction_scan(out_dir: Any) -> Dict[str, Any]:
    """Redaction scan over EVERY file in ``out_dir``, robust to non-UTF8 files WITHOUT weakening secret
    safety (2026-06-22 fix).

    The proven Build 26/29 scanner read each file as strict UTF-8, so a non-UTF8 file in ``out_dir`` —
    e.g. a PowerShell-redirected ``console.log`` / ``console.err`` written as UTF-16 LE (BOM
    ``0xFF 0xFE``) — raised ``UnicodeDecodeError`` and crashed the (unguarded) postflight scan, losing
    every session artifact. This wrapper reuses the SAME danger-needle scanner (``art.scan_text`` +
    allowlist) and the SAME positive control, but reads each file defensively: every file (UTF8 or not)
    is decoded and needle-scanned, non-UTF8 files are recorded in ``non_utf8_files`` (never silently
    ignored), and a file that cannot be read at ALL fails the scan CLOSED. Output keys are a SUPERSET of
    the proven scan (redaction_status / total_unsafe_hits / positive_control_ok preserved verbatim)."""
    root = Path(out_dir)
    report_name = getattr(art, "_SCAN_REPORT_NAME", "build26_capture_redaction_scan.txt")
    # Never self-scan the scanner's OWN output reports. By construction they serialize the danger-needle
    # vocabulary (``per_file_hits`` / ``positive_control_flagged``), so scanning one self-flags with the
    # positive-control needles even though NO real secret is present (window_04 2026-06-23: a REUSED out_dir
    # held a prior ``redaction_scan.json`` whose positive-control categories/needles — including "://",
    # "WEBSOCKET_URL", "helius-rpc", "atlas-mainnet", "api-key", and "bearer" — tripped the per-tick
    # secret breaker). These reports can carry NO
    # real secret: their only string content is fixed needle TOKENS, artifact filenames, counts, booleans,
    # and a const note. The legacy Build26 ``.txt`` report was already excluded; the production
    # ``redaction_scan.json`` (this function's own result) is excluded the SAME way. Every real artifact is
    # still fully scanned and the in-memory positive control still runs — detection is NOT weakened.
    scan_report_names = {report_name, getattr(art, "REDACTION_SCAN_BASENAME", "redaction_scan.json")}
    per_file: Dict[str, List[str]] = {}
    non_utf8: List[str] = []
    read_errors: Dict[str, str] = {}
    vanished_files: List[str] = []
    malformed_jsonl: Dict[str, Dict[str, Any]] = {}
    malformed_jsonl_total = 0
    for p in sorted(root.rglob("*")):
        if not p.is_file() or p.name in scan_report_names:
            continue
        rel = str(p.relative_to(root))
        # A live producer atomically replaces checkpoint files (write tmp ->
        # os.replace) while this per-tick scan walks the tree, so a listed
        # path can vanish or be transiently share-locked between rglob and
        # read.  A bounded retry distinguishes that ordinary Windows race
        # from a genuinely unreadable file: a path that no longer EXISTS has
        # no content to prove and is recorded separately (never a violation);
        # a path that persists unreadable still fails the scan closed.
        # (2026-07-27: one such transient flipped a whole run to
        # SECRET_SCAN_FAILURE with zero needle hits.)
        raw = None
        last_error: Optional[str] = None
        for attempt in range(3):
            try:
                raw = p.read_bytes()
                last_error = None
                break
            except FileNotFoundError:
                last_error = "FileNotFoundError"
                if not p.exists():
                    break
            except Exception as exc:
                last_error = type(exc).__name__
            if attempt < 2:
                time.sleep(0.05)
        if raw is None:
            if last_error == "FileNotFoundError" and not p.exists():
                vanished_files.append(rel)
            else:
                read_errors[rel] = last_error or "UNKNOWN_READ_ERROR"
            continue
        text, was_utf8 = _decode_for_scan(raw)
        if not was_utf8:
            non_utf8.append(rel)
        hits, malformed_lines = scan_text_with_jsonl_report(text)
        per_file[rel] = hits
        if malformed_lines and p.name.lower().endswith(".jsonl"):
            # Disclosure-only evidence of torn/malformed JSONL records
            # (line number + parse error class + truncated/malformed status;
            # NEVER line content). A malformed line alone is NOT a needle
            # hit and never flips redaction_status by itself — a genuine
            # secret inside one is still scanned raw and hits above.
            malformed_jsonl_total += len(malformed_lines)
            malformed_jsonl[rel] = {
                "total": len(malformed_lines),
                "listed": min(len(malformed_lines),
                              _MALFORMED_REPORT_MAX_LINES_PER_FILE),
                "lines": malformed_lines[
                    :_MALFORMED_REPORT_MAX_LINES_PER_FILE],
            }
    total = sum(len(v) for v in per_file.values())
    # SAME positive control as the proven scanner (assembled in pieces so THIS source carries no needle).
    # The trailing synthetic header proves the context-aware AUTHORIZATION_HEADER
    # rule fires in every runtime scan (2026-07-18 false-positive fix); the
    # trailing synthetic Telegram bot token proves the TELEGRAM_BOT_TOKEN rule
    # fires in every runtime scan (2026-07-20 residual re-audit, L-4).
    planted = ("wss" + "://atlas-mainnet.heli" + "us-rpc.com/?api-" + "key=PLANTED b" + "earer z"
               + " Authoriz" + "ation: PLANTED-credential"
               + " bot" + "1234567:" + "PLANTED" + ("d" * 28))
    positive_control = art.scan_text(planted)
    # A non-UTF8 file alone is NOT a violation (we successfully scanned its recovered text); only an
    # actual needle hit or an UNREADABLE file (content unprovable) fails the scan closed.  A file
    # that VANISHED mid-scan (atomic checkpoint replacement) has no content to prove -- its
    # replacement target is scanned on this same walk -- and is disclosed, not a violation.
    redacted = (total == 0 and not read_errors)
    return {
        "kind": "BUILD29_CAP1_REDACTION_SCAN",
        "per_file_hits": per_file,
        "total_unsafe_hits": total,
        "positive_control_flagged": positive_control,
        "positive_control_ok": bool(positive_control),
        "redaction_status": "REDACTED" if redacted else "REDACTION_VIOLATION",
        "non_utf8_files": sorted(non_utf8),
        "scan_non_utf8": bool(non_utf8),
        "read_errors": read_errors,
        "vanished_files": sorted(vanished_files),
        "malformed_jsonl_lines": malformed_jsonl,
        "malformed_jsonl_line_total": malformed_jsonl_total,
        "robust_decode": True,
        "note": ("helius:sig:<sig>:slot:<n> provenance refs are allowlisted SAFE; non-UTF8 files are "
                 "BOM-aware decoded (UTF-16/UTF-8-SIG, else UTF-8/replace), STILL needle-scanned, and "
                 "listed in non_utf8_files; an unreadable file fails the scan closed; the scanner's own "
                 "report files (redaction_scan.json + the legacy build26 .txt) are excluded from self-scan "
                 "(they carry only needle-token vocabulary, never a real secret); JSONL files are masked "
                 "and scanned PER LINE — a malformed line is scanned raw, disclosed in "
                 "malformed_jsonl_lines (line number + error class only), and never disables the fixed "
                 "public enum masking of valid neighboring lines."),
    }


def build_send_result(send_result: Any, *, real_transport_used: bool) -> Dict[str, Any]:
    return art.build_send_result(send_result, real_transport_used=real_transport_used)


def build_production_safety_report(
    *,
    outcome: str,
    stop_reason: Optional[str],
    real_send_performed: bool,
    real_private_transport_constructed: bool,
    sends: int,
    durable_ledger_opened: bool,
    durable_ledger_mutated: bool,
    total_ledger_delta: Optional[int],
    armed: bool,
    approval_token_used: bool,
    axiom_source: str,
    axiom_gate_enabled: bool,
    scan: Dict[str, Any],
    axiom_observe_only: bool = True,
    axiom_used_for_blocking: bool = False,
    interrupted: bool = False,
    postflight_complete: bool = True,
) -> Dict[str, Any]:
    """Production safety report. Same load-bearing safety booleans as the proven Build 29 report
    (no public/subscriber routing, no wallet/signing/trading, no secret printed) PLUS the
    production-mode facts: no total send cap, Axiom gate state, total ledger delta, stop reason.

    Axiom is OBSERVE-ONLY by default (2026-06-22): it decodes + reports BEFORE reserve/send but does NOT
    gate the candidate (``axiom_observe_only=True``, ``axiom_blocks_send=False``). The opt-in hard gate
    sets ``axiom_used_for_blocking=True``."""
    return {
        "kind": "PRODUCTION_LIVE_SAFETY_REPORT",
        "mode": "PRODUCTION_PRIVATE_LIVE",
        "outcome": outcome,
        "stop_reason": stop_reason,
        # Interrupt provenance (2026-06-26): an operator-interrupted run is recorded honestly and is NOT a
        # full PASS. ``postflight_complete`` is True once this report + scan + ledger delta were written.
        "interrupted": bool(interrupted),
        "postflight_complete": bool(postflight_complete),
        "total_send_cap": None,                       # NO fixed total ping cap (by design)
        "sends_performed": int(sends),
        "real_send_performed": bool(real_send_performed),
        "real_private_transport_constructed": bool(real_private_transport_constructed),
        "axiom_fee_gate_enabled": bool(axiom_gate_enabled),
        "axiom_fee_gate_runs_before_reserve_and_send": True,
        "axiom_observe_only": bool(axiom_observe_only),
        "axiom_used_for_blocking": bool(axiom_used_for_blocking),
        "axiom_blocks_send": bool(axiom_used_for_blocking),
        "axiom_final_send_eligibility_source": (
            "AXIOM_PASS_REQUIRED" if axiom_used_for_blocking else "PHX2_BASELINE_ELIGIBILITY"),
        "axiom_fee_source": axiom_source,
        "durable_ledger_path_opened": bool(durable_ledger_opened),
        "durable_ledger_mutated": bool(durable_ledger_mutated),
        "total_ledger_delta": total_ledger_delta,
        "armed": bool(armed),
        "approval_token_used": bool(approval_token_used),
        "private_operator_route_only": True,
        "public_or_subscriber_routing": False,
        "wallet_signing_or_trading": False,
        "stage28_grpc_yellowstone_surface": False,
        "secret_value_printed": False,
        "redaction_status": scan["redaction_status"],
        "redaction_total_unsafe_hits": scan["total_unsafe_hits"],
        "redaction_positive_control_ok": scan["positive_control_ok"],
    }


def build_session_manifest(
    *,
    mode: str,
    outcome: str,
    stop_reason: Optional[str],
    ticks: int,
    sends: int,
    reseeds: int,
    market_calls: int,
    bounds: Dict[str, Any],
    head_expected: Optional[str],
    head_actual: Optional[str],
    head_ok: Optional[bool] = None,
    interrupted: bool = False,
) -> Dict[str, Any]:
    computed_ok = (head_expected == head_actual) if (head_expected and head_actual) else None
    return {
        "kind": "PRODUCTION_LIVE_SESSION_MANIFEST",
        "mode": mode,
        "outcome": outcome,
        "stop_reason": stop_reason,
        "interrupted": bool(interrupted),
        "ticks": ticks,
        "sends": sends,
        "reseeds": reseeds,
        "market_calls": market_calls,
        "no_total_send_cap": True,
        "bounds": bounds,
        "head_expected": head_expected,
        "head_actual": head_actual,
        "head_ok": head_ok if head_ok is not None else computed_ok,
        "repo_head_expected": head_expected,
        "repo_head_actual": head_actual,
        "repo_head_unchanged": computed_ok,
    }


def build_run_summary(
    *,
    outcome: str,
    stop_reason: Optional[str],
    ticks: int,
    sends: int,
    reseeds: int,
    market_calls: int,
    total_ledger_delta: Optional[int],
    baseline_before: Optional[str],
    baseline_after: Optional[str],
    send_records: List[Dict[str, Any]],
    watchlist_summary: Dict[str, Any],
    axiom_pass_count: int,
    axiom_fail_count: int,
    interrupted: bool = False,
    partial: bool = False,
) -> Dict[str, Any]:
    reserving = [s for s in send_records if s.get("ledger_reserved")]
    sent_ok = [s for s in send_records if s.get("sent_ok")]
    return {
        "kind": "PRODUCTION_LIVE_RUN_SUMMARY",
        "outcome": outcome,
        "stop_reason": stop_reason,
        # 2026-06-26 observability: ``partial`` = a mid-run periodic snapshot (run still in flight);
        # ``interrupted`` = the run was operator-interrupted (Ctrl+C) rather than reaching a clean boundary.
        "partial": bool(partial),
        "interrupted": bool(interrupted),
        "ticks": ticks,
        "sends": sends,
        "reseeds": reseeds,
        "market_calls": market_calls,
        "total_ledger_delta": total_ledger_delta,
        "baseline_before": baseline_before,
        "baseline_after": baseline_after,
        "reserve_count": len(reserving),
        "sent_ok_count": len(sent_ok),
        "every_reserve_has_send_artifact": (
            None if total_ledger_delta is None else (len(reserving) == total_ledger_delta)
        ),
        "axiom_pass_count": int(axiom_pass_count),
        "axiom_fail_count": int(axiom_fail_count),
        "axiom_fee_paid_aggregate": _axiom_fee_aggregate(send_records),
        "watchlist_summary": watchlist_summary,
        "send_records": send_records,
    }


__all__ = (
    "SEND_RESULT_BASENAME", "LEDGER_DELTA_BASENAME", "SAFETY_REPORT_BASENAME",
    "REDACTION_SCAN_BASENAME", "AXIOM_SUBDIR", "CANDIDATES_SUBDIR", "SENDS_BASENAME",
    "SESSION_MANIFEST_BASENAME", "RUN_SUMMARY_BASENAME", "HEARTBEAT_BASENAME",
    "append_axiom_jsonl", "build_candidate_recheck_record", "append_candidate_jsonl",
    "build_send_attempt_record", "append_send_jsonl", "append_heartbeat_jsonl",
    "write_json", "build_ledger_delta", "run_redaction_scan", "build_send_result", "scan_value_safe",
    "build_production_safety_report", "build_session_manifest", "build_run_summary",
)

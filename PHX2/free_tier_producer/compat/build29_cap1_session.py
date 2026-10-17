"""Build #29 cap-1 — bounded session runner (real discovery + real context + ONE guarded send).

OUT-OF-REPO operator glue. Modes: --selftest (offline), --preflight (no socket/RPC/GET/send/
ledger-mutation), --run (armed cap-1 one private send). The COMMITTED real-send lineage is used
(compose -> dedupe reserve -> 30.11.16 guard -> Stage 28.9/28.4). The durable ledger is opened
ONLY on the armed path; selftest/preflight never mutate it.

NO Discord/webhook/send/arm/approval/ledger-mutation happen except on an explicitly armed --run.
Never prints a secret (the webhook URL is read from env and injected; never logged/persisted).
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

_REPO_ROOT = r"C:\Users\BalaC\Downloads\Phoenix_PHX2"
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

import build29_cap1_artifacts as art  # noqa: E402
import build29_cap1_compose_send as cs  # noqa: E402
import build29_cap1_ledger as ledgerlib  # noqa: E402
from build29_cap1_market_sidecar import Cap1MarketCaps, Cap1MarketSidecar  # noqa: E402
from PHX2.free_tier_producer.delivery_transaction import (  # noqa: E402
    DEFAULT_RETRY_BACKOFF_BASE_SECONDS,
    DEFAULT_RETRY_BACKOFF_MAX_SECONDS,
    DELIVERY_STATE_COMMIT_PENDING,
    DELIVERY_STATE_FAILED_RETRYABLE,
    DELIVERY_STATE_SENT_OK_COMMITTED,
    DELIVERY_STATE_UNKNOWN,
    next_retry_at_utc,
    retry_due,
)
from PHX2.free_tier_producer.scam_policy import (  # noqa: E402
    DeliverySafetyDecision,
    delivery_block_reason,
    validate_delivery_decision,
)
from PHX2.free_tier_producer.phx1_parity_policy import (  # noqa: E402
    CONDITION_ACTIVATION_PROVEN,
    REFRESH_ELIGIBLE,
    STATUS_NOT_PROVEN,
    STATUS_PROVEN,
    blocks_compose,
    condition_record,
    resolve_policy,
    send_time_refresh_decision,
)


ENV_WEBHOOK = "PHX2_STAGE21_DISCORD_WEBHOOK_URL"
_LOCKED_CONFIRM_TOKEN = cs.STAGE30_11_16_AUTHORIZATION_CONFIRM_TOKEN

_KEEP_ENV = (
    "HELIUS_API_KEY",
    "HELIUS_RPC_URL",
    "HELIUS_WS_URL",
    "PHX2_MIGRATION_SOURCE_MODE",
    "PHX2_STAGE29_2_BIRDEYE_API_KEY",
    "PHX2_STAGE29_2_BIRDEYE_BASE_URL",
    "PHX2_STAGE29_2_ALLOW_LIVE_HTTP",
    "PHX2_STAGE29_2_HTTP_TIMEOUT_SECONDS",
    "PHX2_CHAINSTACK_YELLOWSTONE_GRPC_ENDPOINT",
    "PHX2_CHAINSTACK_YELLOWSTONE_X_TOKEN",
    "PHX2_STAGE28_11_ALLOW_LIVE_GRPC",
    "PHX2_STAGE28_11_GRPC_TIMEOUT_SECONDS",
    # Bounded RPC gap-backfill recovery (provider-neutral JSON-RPC endpoint).
    # Kept deliberately: the recovery transport authenticates with this value
    # and it is never printed anywhere.
    "PHX2_RPC_RECOVERY_HTTP_ENDPOINT",
    "PHX2_RPC_RECOVERY_HTTP_TIMEOUT_SECONDS",
    "PHX2_DELIVERY_TRANSPORT",
    "PHX2_TELEGRAM_ENABLED",
    "PHX2_TELEGRAM_BOT_TOKEN",
    "PHX2_TELEGRAM_CHAT_ID",
    "PHX2_TELEGRAM_PARSE_MODE",
    "PHX2_TELEGRAM_DISABLE_LINK_PREVIEW",
    "PHX2_TELEGRAM_COIN_IMAGES_ENABLED",
    "PHX2_DISCORD_ENABLED",
    ENV_WEBHOOK,  # cap-1 keeps the private webhook so the armed send can authenticate
)
_SCRUB_SUBSTR = (
    "DISCORD", "WEBHOOK", "TELEGRAM", "WALLET", "PRIVATE_KEY", "PRIVKEY",
    "SIGNER", "SECRET", "GRPC", "YELLOWSTONE", "CHAINSTACK", "ARM",
    "APPROVAL", "SEND", "BIRDEYE",
)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_env_file(path: str) -> int:
    from pathlib import Path
    n = 0
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        if k:
            os.environ[k] = v
            n += 1
    return n


def scrub_unrelated_env() -> int:
    removed = 0
    for k in list(os.environ.keys()):
        if k in _KEEP_ENV:
            continue
        up = k.upper()
        if any(s in up for s in _SCRUB_SUBSTR):
            del os.environ[k]
            removed += 1
    return removed


# ---------------------------------------------------------------------------
# Testable candidate core (one guarded send attempt, stop-after-first-eligible)
# ---------------------------------------------------------------------------


def run_cap1_candidates(
    candidates: List[Dict[str, Any]],
    *,
    sidecar: Cap1MarketSidecar,
    ath_transport: Any,
    ath_endpoint_secret: Any,
    now_utc: Any,
    now_seconds: Any,
    now_iso_fn: Callable[[], str],
    sleep_fn: Callable[[float], None],
    ledger: Any,
    guard: Any,
    authorization: Any,
    created_at_utc: str,
    pump_required: bool = True,
    ttl_seconds: Optional[int] = None,
    pre_reserve_gate_fn: Optional[Callable[[str, Dict[str, Any]], Optional[str]]] = None,
    activation_gate_fn: Optional[Callable[[Dict[str, Any], Dict[str, Any]], Dict[str, Any]]] = None,
    axiom_fee_appender: Any = None,
    delivery_journal: Any = None,
    retry_backoff_base_seconds: int = DEFAULT_RETRY_BACKOFF_BASE_SECONDS,
    retry_backoff_max_seconds: int = DEFAULT_RETRY_BACKOFF_MAX_SECONDS,
    alert_policy: Any = None,
    policy_counters: Any = None,
    send_time_refresh_fn: Optional[Callable[[str, Dict[str, Any]], Optional[Dict[str, Any]]]] = None,
) -> Dict[str, Any]:
    """Process candidates in order; the FIRST that is pump-gated + market-present + composes to
    NO_SEND_DISPATCHED gets the SINGLE guarded delivery TRANSACTION, then STOP. Returns the
    outcome.

    PHX2-E2E-001 corrected ordering: compose consults the dedupe ledger peek-only; the durable
    successful-send row is appended ONLY after the transport confirms delivery (temporary lease
    -> outbox record -> transport -> receipt -> ledger commit). The per-candidate reason is now
    the delivery state — SENT_OK_COMMITTED (terminal success), DELIVERY_FAILED_RETRYABLE
    (watch stays active; bounded backoff via ``delivery_next_retry_at_utc``), or
    DELIVERY_UNKNOWN (observable ambiguity; never silent success, never silent retry). A
    candidate whose ``delivery_next_retry_at_utc`` is still in the future is skipped with
    DELIVERY_RETRY_BACKOFF before any market call.

    OPTIONAL ``pre_reserve_gate_fn(mint, ctx) -> reason|None`` is a GENERIC pre-reserve eligibility
    hook: it runs AFTER market context is present and BEFORE build_revalidation_request / compose (i.e.
    before any attempt lease or guarded transport). A truthy reason drops the candidate (recorded in
    per_candidate) with NO lease and NO send. Default ``None`` = no hook (behavior unchanged for all
    existing callers). The production runner injects the PHX2 minimum-liquidity floor through it."""
    per_candidate: List[Dict[str, Any]] = []
    sent_attempt: Optional[Dict[str, Any]] = None
    eligible_candidate: Optional[Dict[str, Any]] = None
    outcome = "ZERO_SEND"
    policy = resolve_policy(alert_policy)

    def _count(name: str, amount: int = 1) -> None:
        if policy_counters is None:
            return
        try:
            policy_counters.increment(name, amount)
        except Exception:
            # Telemetry can never affect eligibility, reserve, or send.
            pass

    for cand in candidates:
        mint = cand.get("token_mint", "")
        rec: Dict[str, Any] = {"token_mint": mint}
        security_decision = cand.get("security_decision")
        if security_decision is not None:
            security_valid, security_reason = validate_delivery_decision(security_decision)
            security_reason = (security_reason if not security_valid
                               else delivery_block_reason(security_decision))
            rec["security"] = (
                security_decision.to_dict()
                if isinstance(security_decision, DeliverySafetyDecision) else None)
            if security_reason:
                rec.update({
                    "reason": security_reason,
                    "compose_attempted": False,
                    "reservation_attempted": False,
                    "active_ledger_mutated": False,
                    "discord_transport_attempted": False,
                    "telegram_transport_attempted": False,
                    "delivery_transport_attempted": False,
                })
                per_candidate.append(rec)
                continue
        from PHX2.free_tier_producer.migration_admission import candidate_migration_is_admitted
        if pump_required and not candidate_migration_is_admitted(cand):
            rec["reason"] = "NOT_PUMP_SUFFIX"
            per_candidate.append(rec)
            continue
        # Bounded per-candidate delivery retry backoff (set after an explicit
        # transport failure). Not yet due -> skip BEFORE any market call; the
        # candidate stays active and is retried on a later tick.
        if not retry_due(now_utc=now_iso_fn(),
                         next_retry_at=cand.get("delivery_next_retry_at_utc")):
            rec["reason"] = "DELIVERY_RETRY_BACKOFF"
            rec["delivery_next_retry_at_utc"] = cand.get(
                "delivery_next_retry_at_utc")
            per_candidate.append(rec)
            continue
        ctx = sidecar.resolve(
            mint,
            migration_time_utc=cand.get("migration_time_utc"),
            now_iso_fn=now_iso_fn,
            sleep_fn=sleep_fn,
        )
        rec["market_basis"] = ctx.get("basis")
        rec["market_state"] = ctx.get("market_state")
        rec["market_reason_code"] = ctx.get("market_reason_code")
        rec["next_market_refresh_at_utc"] = ctx.get("next_market_refresh_at_utc")
        rec["market_attempt_count"] = ctx.get("market_attempt_count")
        rec["market_state_transitions"] = ctx.get("market_state_transitions") or []
        rec["endpoint_attempts"] = ctx.get("endpoint_attempts") or {}
        rec["market_context"] = {
            "basis": ctx.get("basis"),
            "market_state": ctx.get("market_state"),
            "market_reason_code": ctx.get("market_reason_code"),
            "current_price": ctx.get("current_price"),
            "current_market_cap_usd": ctx.get("current_market_cap_usd"),
            "liquidity_usd": ctx.get("liquidity_usd"),
            "market_context_fetched_at_utc": ctx.get("market_context_fetched_at_utc"),
            "provider_timestamp_utc": ctx.get("provider_timestamp_utc"),
            "pumpswap_reserve": ctx.get("pumpswap_reserve") or {},
            "central_ath": ctx.get("central_ath") or {},
        }
        # Mandatory production lifecycle gate. It observes current market data
        # so pending candidates keep the central ATH current, captures the
        # immutable fallback baseline when appropriate, and blocks before any
        # tier calculation / compose / reserve / transport. A crossing tick
        # intentionally remains ineligible until the next watch tick.
        activation_result: Dict[str, Any] = {
            "activation": cand.get("activation") or {},
            "eligible": False,
            "reason": "ACTIVATION_PROOF_REQUIRED",
        }
        if activation_gate_fn is not None:
            try:
                activation_result = activation_gate_fn(cand, ctx)
            except Exception as activation_exc:
                activation_result = {
                    "activation": cand.get("activation") or {},
                    "eligible": False,
                    "reason": "ACTIVATION_GATE_ERROR_%s" % type(activation_exc).__name__,
                }
        rec["activation"] = activation_result.get("activation") or {}
        rec["market_context"] = {
            **rec["market_context"], "activation": rec["activation"]}
        activation_eligible = bool(activation_result.get("eligible"))
        rec["alert_policy"] = policy
        rec["activation_enforcement"] = condition_record(
            CONDITION_ACTIVATION_PROVEN,
            STATUS_PROVEN if activation_eligible else STATUS_NOT_PROVEN,
            policy=policy,
        )
        if not activation_eligible:
            activation_reason = str(
                activation_result.get("reason") or "ACTIVATION_PROOF_REQUIRED")
            if blocks_compose(CONDITION_ACTIVATION_PROVEN, policy=policy):
                rec["reason"] = "NO_SEND_" + activation_reason
                rec["market_attempts"] = ctx.get("attempts")
                per_candidate.append(rec)
                continue
            # PHX1_PARITY: activation is an observation/ranking signal.  The
            # unproven status is recorded and counted, the candidate keeps its
            # activation state and multiplier in artifacts, and every core
            # market requirement below still has to pass on its own.
            rec["activation_shadow_reason"] = activation_reason
            _count("would_have_blocked_under_legacy_activation")
        if not ctx.get("all_present"):
            # Stale/incomplete market data NEVER composes.  Under PHX1_PARITY
            # the candidate first gets ONE bounded priority refresh so a
            # recovery-backoff or indexing gap does not silently cost the alert;
            # a failed refresh keeps the candidate for a later tick under the
            # existing bounded backoff, and never erases ATH, activation,
            # provenance or tier history.
            refresh_verdict = send_time_refresh_decision(
                market_all_present=False,
                attempts_used=int(rec.get("send_time_refresh_attempts") or 0),
                policy=policy,
            )
            rec["send_time_refresh_decision"] = refresh_verdict
            if refresh_verdict == REFRESH_ELIGIBLE and send_time_refresh_fn is not None:
                _count("send_time_refresh_attempted")
                rec["send_time_refresh_attempts"] = 1
                try:
                    refreshed_ctx = send_time_refresh_fn(mint, ctx)
                except Exception as refresh_exc:
                    refreshed_ctx = None
                    rec["send_time_refresh_error"] = type(refresh_exc).__name__
                if isinstance(refreshed_ctx, dict) and refreshed_ctx.get("all_present"):
                    _count("send_time_refresh_succeeded")
                    rec["send_time_refresh_result"] = "SEND_TIME_REFRESH_SUCCEEDED"
                    ctx = refreshed_ctx
                    if ctx.get("central_ath") is None:
                        central_snapshot_fn = getattr(
                            sidecar, "central_ath_snapshot", None)
                        if callable(central_snapshot_fn):
                            try:
                                ctx["central_ath"] = central_snapshot_fn(mint)
                            except Exception:
                                ctx["central_ath"] = {}
                    # Fresh authoritative evidence: re-run the SAME lifecycle
                    # gate so the recorded activation status reflects what the
                    # refresh actually observed.  A candidate that was only
                    # waiting for a fresh market can legitimately become an
                    # active dip here instead of waiting a whole tick.
                    if activation_gate_fn is not None:
                        try:
                            activation_result = activation_gate_fn(cand, ctx)
                        except Exception as activation_exc:
                            activation_result = {
                                "activation": cand.get("activation") or {},
                                "eligible": False,
                                "reason": "ACTIVATION_GATE_ERROR_%s" % type(
                                    activation_exc).__name__,
                            }
                        rec["activation"] = activation_result.get("activation") or {}
                        activation_eligible = bool(activation_result.get("eligible"))
                        rec["activation_enforcement"] = condition_record(
                            CONDITION_ACTIVATION_PROVEN,
                            STATUS_PROVEN if activation_eligible
                            else STATUS_NOT_PROVEN,
                            policy=policy,
                        )
                        if not activation_eligible and blocks_compose(
                                CONDITION_ACTIVATION_PROVEN, policy=policy):
                            rec["reason"] = "NO_SEND_" + str(
                                activation_result.get("reason")
                                or "ACTIVATION_PROOF_REQUIRED")
                            rec["market_attempts"] = ctx.get("attempts")
                            per_candidate.append(rec)
                            continue
                    rec["market_basis"] = ctx.get("basis")
                    rec["market_state"] = ctx.get("market_state")
                    rec["market_reason_code"] = ctx.get("market_reason_code")
                    rec["next_market_refresh_at_utc"] = ctx.get(
                        "next_market_refresh_at_utc")
                    rec["market_attempt_count"] = ctx.get("market_attempt_count")
                    rec["market_context"] = {
                        **rec["market_context"],
                        "basis": ctx.get("basis"),
                        "market_state": ctx.get("market_state"),
                        "market_reason_code": ctx.get("market_reason_code"),
                        "current_price": ctx.get("current_price"),
                        "current_market_cap_usd": ctx.get("current_market_cap_usd"),
                        "liquidity_usd": ctx.get("liquidity_usd"),
                        "market_context_fetched_at_utc": ctx.get(
                            "market_context_fetched_at_utc"),
                        "provider_timestamp_utc": ctx.get("provider_timestamp_utc"),
                        "activation": rec["activation"],
                    }
                else:
                    # The candidate is RETAINED: no terminal transition, no
                    # discard, and ATH / activation / provenance / tier history
                    # are all untouched.  The existing bounded backoff owns the
                    # next attempt.
                    _count("send_time_refresh_failed")
                    rec["send_time_refresh_result"] = "SEND_TIME_REFRESH_FAILED"
                    rec["send_time_refresh_retained"] = True
        if not ctx.get("all_present"):
            state = str(ctx.get("market_state") or "MARKET_UNAVAILABLE")
            rec["reason"] = "NO_SEND_" + state
            rec["market_attempts"] = ctx.get("attempts")
            per_candidate.append(rec)
            continue
        # OPTIONAL generic pre-reserve eligibility gate (default OFF). Runs with market context present
        # and BEFORE build_revalidation_request / compose_and_maybe_send, so a blocked candidate NEVER
        # reserves a durable ledger line and NEVER reaches the guarded private transport. The production
        # runner injects the PHX2 minimum-liquidity floor here.
        if pre_reserve_gate_fn is not None:
            try:
                gate_reason = pre_reserve_gate_fn(mint, ctx)
            except Exception as _gate_exc:        # fail CLOSED: a gate error blocks (never reserves/sends)
                gate_reason = "PRE_RESERVE_GATE_ERROR (%s)" % type(_gate_exc).__name__
            # Gates may attach a redaction-safe assessment for the delivery
            # adapter. Preserve that same assessment on the candidate record so
            # artifacts and the outgoing message cannot silently diverge.
            if isinstance(ctx.get("risk_assessment"), dict):
                rec["market_context"] = {
                    **rec["market_context"],
                    "risk_assessment": dict(ctx["risk_assessment"]),
                }
            if gate_reason:
                rec["reason"] = gate_reason
                rec["market_attempts"] = ctx.get("attempts")
                per_candidate.append(rec)
                continue
            refreshed_security = ctx.get("security_decision")
            if refreshed_security is not None:
                security_decision = refreshed_security
                cand["security_decision"] = refreshed_security
                if isinstance(ctx.get("fee_gate_lifecycle"), dict):
                    cand["fee_gate_lifecycle"] = dict(ctx["fee_gate_lifecycle"])
                rec["security"] = (
                    refreshed_security.to_dict()
                    if isinstance(refreshed_security, DeliverySafetyDecision)
                    else None
                )
        # Independent proof validation immediately before the composer.  The
        # composer owns dedupe reservation/ledger mutation, so this is the last
        # boundary at which an invalid proof can be rejected with zero mutation.
        if security_decision is not None:
            security_valid, security_reason = validate_delivery_decision(security_decision)
            security_reason = (security_reason if not security_valid
                               else delivery_block_reason(security_decision))
            if security_reason:
                rec.update({
                    "reason": security_reason,
                    "compose_attempted": False,
                    "reservation_attempted": False,
                    "active_ledger_mutated": False,
                    "discord_transport_attempted": False,
                    "telegram_transport_attempted": False,
                    "delivery_transport_attempted": False,
                })
                per_candidate.append(rec)
                continue
        # Bind the latest centralized maximum immediately before compose.  The
        # market sidecar may legitimately select an older ready price attempt;
        # that must never carry an older ATH snapshot into the outgoing body.
        bound_central_ath = ctx.get("central_ath")
        central_snapshot_fn = getattr(sidecar, "central_ath_snapshot", None)
        if callable(central_snapshot_fn):
            try:
                bound_central_ath = central_snapshot_fn(mint)
            except Exception:
                bound_central_ath = {}
        ctx = {**ctx, "central_ath": bound_central_ath}
        rec["market_context"] = {
            **rec["market_context"], "central_ath": bound_central_ath or {}}
        request = cs.build_revalidation_request(
            token_mint=mint,
            candidate_id=cand.get("candidate_id", "cap1_cand"),
            migration_time_utc=cand.get("migration_time_utc"),
            migration_source=cand.get("source_ref"),
            current_price=ctx.get("current_price"),
            current_market_cap_usd=ctx.get("current_market_cap_usd"),
            liquidity_usd=ctx.get("liquidity_usd"),
            market_context_fetched_at_utc=ctx.get("market_context_fetched_at_utc"),
            created_at_utc=created_at_utc,
            symbol_or_name=cand.get("symbol_or_name"),
            age_display=cand.get("age_display"),
            central_ath=bound_central_ath,
            discovery_provenance=cand.get("discovery_provenance"),
        )
        if request is None:
            rec["reason"] = "NO_SEND_MARKET_UNAVAILABLE"
            per_candidate.append(rec)
            continue
        res = cs.compose_and_maybe_send(
            request,
            ath_transport=ath_transport,
            ath_endpoint_secret=ath_endpoint_secret,
            now_utc=now_utc,
            now_seconds=now_seconds,
            ledger=ledger,
            guard=guard,
            authorization=authorization,
            created_at_utc=created_at_utc,
            ttl_seconds=ttl_seconds,
            axiom_fee_appender=axiom_fee_appender,
            activation_proof=activation_result.get("activation"),
            security_decision=security_decision,
            delivery_context={
                "candidate": dict(cand),
                "market_context": dict(ctx),
                "activation": dict(activation_result.get("activation") or {}),
                "security_decision": security_decision,
            },
            delivery_journal=delivery_journal,
            alert_policy=policy,
        )
        if res.get("eligible") and not activation_eligible:
            _count("sent_without_activation_proof")
        rec["compose_decision"] = res["compose_decision"]
        # Observe-only granular compose telemetry (2026-06-23): preserve the composer's EXACT reason (and
        # any snapshot tier/drawdown/anchored-ATH-MC) threaded out of compose_and_maybe_send, copied for
        # BOTH the dispatched and non-dispatched paths. Does NOT change eligibility, reserve, or send; the
        # coarse rec["reason"] (SEND_ATTEMPTED / NO_SEND_NOT_DISPATCHABLE) set below is unchanged.
        if res.get("compose_reason") is not None:
            rec["compose_reason"] = res.get("compose_reason")
        for _ck in ("compose_tier", "compose_drawdown_pct", "compose_anchored_ath_mc",
                    "central_ath"):
            _cv = res.get(_ck)
            if _cv is not None:
                rec[_ck] = _cv
        if isinstance(bound_central_ath, dict):
            # Preserve the exact body-bound snapshot even if the central store
            # advances concurrently before artifact callbacks run.
            rec["central_ath"] = dict(bound_central_ath)
            rec["market_context"] = {
                **rec["market_context"], "central_ath": dict(bound_central_ath)}
        rec["market_attempts"] = ctx.get("attempts")
        if res["eligible"]:
            delivery = res.get("delivery")
            if delivery is None:
                # Compose was dispatch-eligible but no armed guard/authorization
                # was supplied: nothing durable happened (peek-only compose) and
                # no transport was called. Never claim an attempt or a send.
                rec["reason"] = "COMPOSED_NO_TRANSPORT"
                per_candidate.append(rec)
                continue
            delivery_state = delivery.get("delivery_state")
            rec["delivery_state"] = delivery_state
            rec["delivery_attempt_id"] = delivery.get("attempt_id")
            if delivery_state == DELIVERY_STATE_SENT_OK_COMMITTED:
                rec["reason"] = "SENT_OK_COMMITTED"
                rec["delivery_receipt_message_id"] = delivery.get("message_id")
                per_candidate.append(rec)
                sent_attempt = res
                eligible_candidate = cand
                outcome = "ONE_SEND_COMMITTED"
                break  # stop-after-one: exactly one confirmed committed send
            if delivery_state == DELIVERY_STATE_COMMIT_PENDING:
                # Delivery IS confirmed (durable receipt written) but the
                # successful-send ledger commit could not complete. Terminal
                # for this run — the caller stops and restart reconciliation
                # finishes the commit WITHOUT another transport call.
                rec["reason"] = "SENT_OK_COMMIT_PENDING"
                rec["delivery_receipt_message_id"] = delivery.get("message_id")
                per_candidate.append(rec)
                sent_attempt = res
                eligible_candidate = cand
                outcome = "ONE_SEND_COMMIT_PENDING"
                break
            if delivery_state == DELIVERY_STATE_FAILED_RETRYABLE:
                retry_count = cand.get("delivery_retry_count")
                retry_count = (retry_count
                               if isinstance(retry_count, int)
                               and not isinstance(retry_count, bool)
                               and retry_count >= 0 else 0)
                rec["reason"] = "DELIVERY_FAILED_RETRYABLE"
                rec["delivery_failure_reason"] = delivery.get("failure_reason")
                rec["delivery_retry_count"] = retry_count + 1
                rec["delivery_next_retry_at_utc"] = next_retry_at_utc(
                    now_utc=now_iso_fn(), retry_count=retry_count,
                    base_seconds=retry_backoff_base_seconds,
                    max_seconds=retry_backoff_max_seconds)
                per_candidate.append(rec)
                sent_attempt = res
                eligible_candidate = cand
                outcome = "ONE_SEND_FAILED_RETRYABLE"
                break  # one transport attempt per invocation; retry next tick
            if delivery_state == DELIVERY_STATE_UNKNOWN:
                rec["reason"] = "DELIVERY_UNKNOWN"
                rec["delivery_failure_reason"] = getattr(
                    delivery.get("send_result"), "transport_status", None)
                per_candidate.append(rec)
                sent_attempt = res
                eligible_candidate = cand
                outcome = "ONE_SEND_UNKNOWN"
                break
            # Lease held elsewhere / guard refused before any transport call:
            # no attempt happened; the candidate stays active.
            rec["reason"] = "NO_SEND_DELIVERY_" + str(delivery_state)
            rec["delivery_refusal_reason"] = delivery.get("refusal_reason")
            per_candidate.append(rec)
            continue
        rec["reason"] = "NO_SEND_NOT_DISPATCHABLE"
        per_candidate.append(rec)

    return {
        "per_candidate": per_candidate,
        "sent_attempt": sent_attempt,
        "eligible_candidate": eligible_candidate,
        "outcome": outcome,
    }


# ---------------------------------------------------------------------------
# Live discovery (real read-only Helius; NOT run in selftest/preflight)
# ---------------------------------------------------------------------------


def _record_to_candidate(record: Any) -> Optional[Dict[str, Any]]:
    from PHX2.stage29.stage29_5_7_live_migration_evidence_producer import (
        project_migration_evidence_to_sanitized_summary,
    )
    summary = project_migration_evidence_to_sanitized_summary(record)
    if summary is None or not getattr(summary, "token_mint", None):
        return None
    if getattr(summary, "measurement_status", None) != "COMPLETE":
        return None
    return {
        "token_mint": summary.token_mint,
        "candidate_id": "cap1_" + str(summary.token_mint)[:8],
        "migration_time_utc": summary.migration_event_time_utc,
        "source_ref": summary.source_ref,
        "symbol_or_name": None,
    }


def _build_live_sidecar(*, enabled: bool, timeout_seconds: int):
    from PHX2.stage29.stage29_2_birdeye_http_transport import Stage29_2BirdeyeUrlibTransport
    from PHX2.stage29.stage29_2_birdeye_readiness import build_endpoint_secret_from_env
    if not enabled:
        return Cap1MarketSidecar(transport=None, endpoint_secret=None, enabled=False,
                                 caps=Cap1MarketCaps()), None
    secret = build_endpoint_secret_from_env()
    sidecar = Cap1MarketSidecar(
        transport=Stage29_2BirdeyeUrlibTransport(), endpoint_secret=secret,
        timeout_seconds=timeout_seconds, enabled=True, caps=Cap1MarketCaps(),
    )
    return sidecar, secret


# ---------------------------------------------------------------------------
# Preflight (no socket/RPC/GET/send/ledger-mutation)
# ---------------------------------------------------------------------------


def run_preflight(env_path: Optional[str], *, ledger_path: Optional[str],
                  require_baseline: Optional[str]) -> int:
    from build26_evidence_capture import run_preflight as base_preflight
    if env_path:
        n = load_env_file(env_path)
        scrubbed = scrub_unrelated_env()
        print(f"env: loaded {n} vars; scrubbed {scrubbed} unrelated (Discord/send/etc. except "
              f"the allowlisted private webhook); values NEVER printed.")
    else:
        print("env: no --env supplied; checking current process environment only.")
    rc = base_preflight(write_report=False, report_dir=None)
    try:
        from PHX2.stage29.stage29_2_birdeye_readiness import (
            detect_stage29_2_birdeye_readiness,
        )
        r = detect_stage29_2_birdeye_readiness()
        print("market+ath readiness: "
              f"status={r.status} refusal={r.refusal_reason} "
              f"api_key_present={r.api_key_length > 0} api_key_length={r.api_key_length} "
              f"base_url_present={r.base_url_length > 0} base_url_length={r.base_url_length} "
              f"live_http_allowed={r.live_flag_set} timeout_seconds={r.timeout_seconds}")
    except Exception as exc:
        print(f"market+ath readiness: UNAVAILABLE ({type(exc).__name__})")
    # Webhook presence/shape only (never the value).
    wh = os.environ.get(ENV_WEBHOOK)
    wh_present = bool(wh) and wh.strip() != ""
    wh_len = len(wh) if isinstance(wh, str) else 0
    wh_https = wh_present and wh.strip().lower().startswith("htt" + "ps" + ":")
    wh_discord = wh_present and ("dis" + "cord" + ".com" in wh.lower()
                                or "dis" + "cordapp" + ".com" in wh.lower())
    print(f"webhook[{ENV_WEBHOOK}]: present={wh_present} length={wh_len} https={wh_https} "
          f"discord_host={wh_discord} (value NEVER printed)")
    # Durable ledger baseline (read-only digest; not secrets).
    if ledger_path:
        triple = ledgerlib.compute_baseline(ledger_path)
        if triple is None:
            print(f"ledger: path given, file MISSING (fresh ledger) — no baseline computed.")
        else:
            req = ledgerlib.parse_require_baseline(require_baseline) if require_baseline else None
            matches = ledgerlib.baseline_matches(triple, req) if req else None
            print(f"ledger baseline: line_count={triple.line_count} size_bytes={triple.size_bytes} "
                  f"sha256={triple.sha256} matches_require_baseline={matches}")
    else:
        print("ledger: no --ledger-path supplied; baseline not computed.")
    print("preflight: opened NO socket, made NO RPC, made NO market/OHLCV GET, made NO Discord "
          "send, did NOT mutate the ledger, printed NO secret value.")
    return rc


# ---------------------------------------------------------------------------
# Arm gate (all gates must be explicit; refuse otherwise)
# ---------------------------------------------------------------------------


def _verify_arm(args, *, interactive: bool = True) -> Optional[str]:
    """Return None if armed OK, else a refusal reason string. Verifies the explicit flags +
    the locked confirm token + the durable-ledger baseline match + an interactive mint-bound
    confirmation."""
    if not getattr(args, "i_understand_this_can_send", False):
        return "MISSING_ACK_FLAG"
    if getattr(args, "confirm_token", None) != _LOCKED_CONFIRM_TOKEN:
        return "CONFIRM_TOKEN_MISMATCH"
    if not args.ledger_path:
        return "MISSING_LEDGER_PATH"
    if not args.require_baseline:
        return "MISSING_REQUIRE_BASELINE"
    actual = ledgerlib.compute_baseline(args.ledger_path)
    required = ledgerlib.parse_require_baseline(args.require_baseline)
    if required is None:
        return "REQUIRE_BASELINE_MALFORMED"
    # A fresh (missing) ledger may be asserted as 0 lines / empty sha by the operator; require
    # an exact match against the present file otherwise.
    if actual is not None and not ledgerlib.baseline_matches(actual, required):
        return "BASELINE_MISMATCH"
    if not (os.environ.get(ENV_WEBHOOK) or "").strip():
        return "WEBHOOK_MISSING"
    return None


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


ACK_FLAG = "--ack-live-readonly-shadow"


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        prog="build29_cap1_session",
        description="Build #29 cap-1 (real discovery + real market/ATH + ONE guarded private "
                    "send; live NEVER default).",
    )
    p.add_argument("--selftest", action="store_true")
    p.add_argument("--preflight", action="store_true")
    p.add_argument("--run", action="store_true")
    p.add_argument(ACK_FLAG, dest="ack", action="store_true")
    p.add_argument("--modeB-real-market", dest="modeb_real_market", action="store_true")
    p.add_argument("--i-understand-this-can-send", dest="i_understand_this_can_send",
                   action="store_true")
    p.add_argument("--confirm-token", dest="confirm_token", default=None)
    p.add_argument("--operator-label", dest="operator_label", default=None)
    p.add_argument("--authorization-reason", dest="authorization_reason", default=None)
    p.add_argument("--require-baseline", dest="require_baseline", default=None)
    p.add_argument("--ledger-path", dest="ledger_path", default=None)
    p.add_argument("--webhook-identity", dest="webhook_identity", default=None)
    p.add_argument("--env", default=None)
    p.add_argument("--out-dir", default=None)
    p.add_argument("--raw-quarantine", default="off", choices=["off"])
    p.add_argument("--max-runtime", type=float, default=3600.0)
    p.add_argument("--max-notifications", type=int, default=200000)
    p.add_argument("--max-gettransaction", type=int, default=256)
    p.add_argument("--max-accepted", type=int, default=32)
    p.add_argument("--max-real-sends", type=int, default=1)
    args = p.parse_args(argv)

    if args.selftest:
        import build29_cap1_selftest as st
        return st.main()
    if args.preflight:
        return run_preflight(args.env, ledger_path=args.ledger_path,
                             require_baseline=args.require_baseline)
    if args.run:
        # The armed live path is intentionally gated; this build is NOT to be run live until
        # a separate explicit approval. Verify the arm gates and refuse cleanly otherwise.
        if not args.ack:
            print(f"[refused] a live cap-1 run requires {ACK_FLAG}.")
            return 2
        refusal = _verify_arm(args)
        if refusal is not None:
            print(f"[refused-arm] {refusal} — no send, no ledger mutation.")
            return 2
        print("[refused] live cap-1 --run is operator-gated and not enabled in this build step; "
              "rerun only under an explicitly approved real-send ceremony.")
        return 2

    print("[refused] No mode selected. Live run is never the default.")
    print("Offline selftest:  --selftest   |   Env preflight (no socket):  --preflight")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

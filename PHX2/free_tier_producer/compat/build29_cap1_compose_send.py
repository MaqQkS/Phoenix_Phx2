"""Build #29 cap-1 — compose + (guarded) one real send.

OUT-OF-REPO operator glue. Wires the COMMITTED real-send lineage:

    Stage30_11_13RevalidationRequest (built from real migration evidence + the cap-1 market
        sidecar's real price/MC/LP)
      -> compose_no_send_dispatch_deduped(..., ledger=...)   # dip gate + anchored ATH/OHLCV
         over the injected ath_transport; dedupe RESERVE happens HERE (reserve-before-send),
         the compose's own dispatch is the committed FAKE recording client (never a real send)
      -> Stage30_11_15DedupedComposeResult
      -> (only if compose decision == NO_SEND_DISPATCHED, i.e. dispatchable + reserved)
         Stage30_11_16RealPrivateTransportGuard.authorize_and_dispatch(...)  # ONE real send

Track-1/B.1 fake-attestation is NOT used. The COMPOSE step always uses the committed FAKE
recording transport client (the composer enforces fake-only). The REAL private transport
(Stage 28.9 -> Stage 28.4) is constructed ONLY for the 30.11.16 guard, ONLY on the armed path.

Discipline: never prints a secret (the webhook URL is read by the runner and injected into the
real transport; it is never logged/persisted here). No durable ledger is constructed in this
module — the caller passes the ledger (InMemory/temp in selftest; durable only when armed).
"""

from __future__ import annotations

import sys
from typing import Any, Dict, Optional

_REPO_ROOT = r"C:\Users\BalaC\Downloads\Phoenix_PHX2"
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from PHX2.stage30.stage30_11_13_committed_no_send_composer import (  # committed  # noqa: E402
    COMPOSE_DECISION_DISPATCHED,
    Stage30_11_13RevalidationRequest,
)
from PHX2.stage30.stage30_11_15_no_send_dedupe_guard import (  # committed  # noqa: E402
    compose_no_send_dispatch_deduped,
    derive_ping_dedupe_key,
)
from PHX2.stage30.stage30_11_15_ping_dedupe_ledger import (  # committed  # noqa: E402
    PeekOnlyPingDedupeLedgerView,
)
from PHX2.stage30.stage30_11_15_ping_dedupe_models import (  # committed  # noqa: E402
    STAGE30_11_15_DEFAULT_TTL_SECONDS,
)
from PHX2.free_tier_producer.delivery_transaction import (  # noqa: E402
    DEFAULT_ATTEMPT_LEASE_SECONDS,
    DeliveryAttemptJournal,
    execute_guarded_delivery,
)
from PHX2.stage30.stage30_11_5_fake_live_wiring_proof import (  # committed  # noqa: E402
    Stage30_11_5RecordingFakeTransportClient,
)
from PHX2.stage30.stage30_11_16_real_send_models import (  # committed  # noqa: E402
    STAGE30_11_16_AUTHORIZATION_CONFIRM_TOKEN,
    Stage30_11_16RealSendAuthorization,
)
from PHX2.stage30.stage30_11_16_real_private_transport_guard import (  # committed  # noqa: E402
    make_stage30_11_16_real_private_transport_guard,
)
from build30_watchlist import activation_proof_is_eligible  # noqa: E402
from PHX2.models.ath_coverage import (  # noqa: E402
    ath_coverage_is_complete,
    classify_ath_coverage,
)
from PHX2.free_tier_producer.scam_policy import (  # noqa: E402
    DeliverySafetyDecision,
    SECURITY_DECISION_PROOF_INCONSISTENT,
    delivery_block_reason,
    validate_delivery_decision,
)
from PHX2.free_tier_producer.phx1_parity_policy import (  # noqa: E402
    CONDITION_ACTIVATION_PROVEN,
    STATUS_NOT_PROVEN,
    STATUS_PROVEN,
    blocks_compose,
    condition_record,
    resolve_policy,
)


def build_revalidation_request(
    *,
    token_mint: str,
    candidate_id: str,
    migration_time_utc: str,
    migration_source: Optional[str],
    current_price: Optional[str],
    current_market_cap_usd: Optional[str],
    liquidity_usd: Optional[str],
    market_context_fetched_at_utc: Optional[str],
    created_at_utc: str,
    symbol_or_name: Optional[str] = None,
    age_display: Optional[str] = None,
    central_ath: Optional[Dict[str, Any]] = None,
    discovery_provenance: Optional[str] = None,
) -> Optional[Stage30_11_13RevalidationRequest]:
    """Build the committed request from real inputs, or ``None`` if the required positive
    market values are missing (the runner then records NO_SEND_MARKET_UNAVAILABLE without
    composing). Never fabricates a value.

    ``ath_coverage`` is classified HERE, from the candidate's discovery
    provenance plus the hydration status the central ATH store publishes with
    its maximum, so the compose gate and the rendered body can never disagree
    about whether the post-migration history is complete."""
    if not (current_price and current_market_cap_usd and liquidity_usd):
        return None
    return Stage30_11_13RevalidationRequest(
        token_mint=token_mint,
        candidate_id=candidate_id,
        migration_time_utc=migration_time_utc,
        current_price=current_price,
        current_market_cap_usd=current_market_cap_usd,
        created_at_utc=created_at_utc,
        migration_confirmed=True,
        symbol_or_name=symbol_or_name,
        migration_source=migration_source,
        liquidity_usd=liquidity_usd,
        age_display=age_display,
        market_context_status="PRESENT",
        market_context_fetched_at_utc=market_context_fetched_at_utc,
        authoritative_ath_price=(central_ath or {}).get("ath_price"),
        authoritative_ath_market_cap_usd=(central_ath or {}).get("ath_market_cap"),
        authoritative_ath_timestamp=(central_ath or {}).get("ath_timestamp"),
        authoritative_ath_provider=(central_ath or {}).get("ath_provider"),
        authoritative_ath_observation_type=(central_ath or {}).get(
            "ath_observation_type"),
        authoritative_ath_status=(central_ath or {}).get("ath_status"),
        authoritative_ath_transaction_signature=(central_ath or {}).get(
            "ath_transaction_signature"),
        authoritative_ath_market_cap_evidence_price_usd=(central_ath or {}).get(
            "ath_market_cap_evidence_price_usd"),
        # The resolved coherent ATH observation.  Passed through verbatim
        # from the central store; the composer -- not this builder -- owns
        # every validation of it.
        resolved_ath_price=(central_ath or {}).get("resolved_ath_price"),
        resolved_supply=(central_ath or {}).get("resolved_supply"),
        resolved_supply_basis=(central_ath or {}).get("resolved_supply_basis"),
        resolved_ath_market_cap_usd=(central_ath or {}).get(
            "resolved_ath_market_cap"),
        resolved_observed_at_utc=(central_ath or {}).get(
            "resolved_observed_at_utc"),
        resolved_ath_source=(central_ath or {}).get("resolved_source"),
        resolved_ath_observation_type=(central_ath or {}).get(
            "resolved_observation_type"),
        resolved_ath_status=(central_ath or {}).get("resolved_status"),
        resolved_evidence_digest=(central_ath or {}).get(
            "resolved_evidence_digest"),
        resolution_method=(central_ath or {}).get("resolution_method"),
        # Coverage is classified only when the CENTRAL ATH contract is in play
        # (the paid runtime).  Without it there is no store maximum being
        # claimed and the legacy anchored-OHLCV path governs, which already
        # requires its own post-migration verification.
        ath_coverage=(
            classify_ath_coverage(
                discovery_provenance=discovery_provenance,
                ath_hydration_status=central_ath.get("ath_hydration_status"),
            ) if central_ath else None),
        allow_legacy_inferred_ath_market_cap=(central_ath is None),
    )


def build_authorization(
    *,
    confirm_token: str,
    operator_label: str,
    authorization_reason: str,
    created_at_utc: str,
) -> Stage30_11_16RealSendAuthorization:
    """Build the committed authorization sentinel. ``authorized=True`` + the operator-supplied
    ``confirm_token`` (must equal the locked phrase to pass the guard's dual gate)."""
    return Stage30_11_16RealSendAuthorization(
        authorized=True,
        confirm_token=confirm_token,
        operator_label=operator_label,
        authorization_reason=authorization_reason,
        created_at_utc=created_at_utc,
    )


def make_real_private_transport(*, webhook_url: str, webhook_identity: str):
    """Construct the committed real private webhook transport (Stage 28.9 -> Stage 28.4).
    Called ONLY on the armed path. The URL is injected here and NEVER logged/persisted."""
    from PHX2.stage28.live_provider_session_transport import (
        Stage28_9PrivateWebhookTransport,
    )
    return Stage28_9PrivateWebhookTransport(
        webhook_url=webhook_url, webhook_identity=webhook_identity
    )


def make_recording_fake_transport_client(created_at_utc: str):
    """The committed FAKE recording dispatch client the COMPOSE step requires (never a real
    send; the composer fails closed on a non-fake client)."""
    return Stage30_11_5RecordingFakeTransportClient(created_at_utc=created_at_utc)


def compose_and_maybe_send(
    request: Any,
    *,
    ath_transport: Any,
    ath_endpoint_secret: Any,
    now_utc: Any,
    now_seconds: Any,
    ledger: Any,
    guard: Any,
    authorization: Any,
    created_at_utc: str,
    ttl_seconds: Optional[int] = None,
    axiom_fee_appender: Any = None,
    activation_proof: Optional[Dict[str, Any]] = None,
    security_decision: Any = None,
    delivery_context: Optional[Dict[str, Any]] = None,
    delivery_journal: Any = None,
    attempt_lease_seconds: int = DEFAULT_ATTEMPT_LEASE_SECONDS,
    alert_policy: Any = None,
) -> Dict[str, Any]:
    """Compose ONE candidate behind the cross-run dedupe guard, then — only if the compose
    decision is ``NO_SEND_DISPATCHED`` (dispatchable + dedupe-allowed) and a guard +
    authorization are supplied — run the single guarded delivery TRANSACTION.

    PHX2-E2E-001 correction: the compose step consults the dedupe ledger through a
    PEEK-ONLY view (duplicates still suppress; NOTHING durable is appended). The durable
    successful-send row is appended by the delivery transaction ONLY after the transport
    confirms ``transport_ok=True`` (temporary lease -> outbox record -> transport ->
    receipt -> ledger commit). An explicit transport failure releases the lease and stays
    retryable; an ambiguous outcome becomes observable DELIVERY_UNKNOWN. The returned dict
    carries ``delivery`` (state/attempt/receipt facts) beside the legacy fields."""
    # Independent fee/LP proof guard.  It executes before the committed
    # composer and therefore before dedupe reservation / ledger mutation.
    if security_decision is not None:
        security_valid, security_reason = validate_delivery_decision(security_decision)
        security_reason = (security_reason if not security_valid
                           else delivery_block_reason(security_decision))
        if security_reason:
            return {
                "deduped": None,
                "compose_decision": None,
                "compose_reason": security_reason,
                "compose_tier": None,
                "compose_drawdown_pct": None,
                "compose_anchored_ath_mc": None,
                "dedupe_outcome": None,
                "eligible": False,
                "send_result": None,
                "central_ath": {},
                "activation": dict(activation_proof or {}),
                "security": (security_decision.to_dict()
                             if isinstance(security_decision, DeliverySafetyDecision) else None),
            }
        context_security = (
            delivery_context.get("security_decision")
            if isinstance(delivery_context, dict) else None
        )
        if context_security is not None and context_security is not security_decision:
            return {
                "deduped": None,
                "compose_decision": None,
                "compose_reason": SECURITY_DECISION_PROOF_INCONSISTENT,
                "compose_tier": None,
                "compose_drawdown_pct": None,
                "compose_anchored_ath_mc": None,
                "dedupe_outcome": None,
                "eligible": False,
                "send_result": None,
                "central_ath": {},
                "activation": dict(activation_proof or {}),
                "security": security_decision.to_dict(),
            }
    # Independent post-migration ATH coverage gate. It executes BEFORE the
    # composer — and before the lifecycle gate below, because coverage is a
    # property of the EVIDENCE rather than of the candidate's state — so a
    # candidate whose migration-anchored history is still hydrating never
    # reaches compose, never calculates a final drawdown, never reserves a
    # dedupe line and never reaches a transport. The candidate is left
    # untouched and stays retryable; the central ATH store owns the bounded
    # retry schedule.
    if getattr(request, "ath_coverage", None) is not None \
            and not ath_coverage_is_complete(request.ath_coverage):
        return {
            "deduped": None,
            "compose_decision": None,
            "compose_reason": "ATH_COVERAGE_INCOMPLETE",
            "compose_tier": None,
            "compose_drawdown_pct": None,
            "compose_anchored_ath_mc": None,
            "dedupe_outcome": None,
            "eligible": False,
            "send_result": None,
            "central_ath": {},
            "activation": dict(activation_proof or {}),
            "ath_coverage": request.ath_coverage,
        }
    # Independent final lifecycle guard. It executes before the committed
    # composer (and therefore before tier calculation and dedupe reservation)
    # and before the real private transport guard.
    #
    # Under PHX1_PARITY activation is an observation/ranking signal rather than
    # a Telegram prerequisite: the status is still computed and recorded, but a
    # candidate that never proved its 1.20x crossing is no longer refused here.
    # Nothing is granted BY the proof under that policy, so a forged proof can
    # buy nothing either; every core market requirement above and below this
    # point stays exactly as committed.
    _policy = resolve_policy(alert_policy)
    _activation_eligible = activation_proof_is_eligible(
        activation_proof, policy=_policy)
    _activation_enforcement = condition_record(
        CONDITION_ACTIVATION_PROVEN,
        STATUS_PROVEN if _activation_eligible else STATUS_NOT_PROVEN,
        policy=_policy,
    )
    if not _activation_eligible and blocks_compose(
            CONDITION_ACTIVATION_PROVEN, policy=_policy):
        return {
            "deduped": None,
            "compose_decision": None,
            "compose_reason": "ACTIVATION_PROOF_REQUIRED",
            "compose_tier": None,
            "compose_drawdown_pct": None,
            "compose_anchored_ath_mc": None,
            "dedupe_outcome": None,
            "eligible": False,
            "send_result": None,
            "central_ath": {},
            "activation": dict(activation_proof or {}),
            "alert_policy": _policy,
            "activation_enforcement": _activation_enforcement,
        }
    fake_client = make_recording_fake_transport_client(created_at_utc)
    ttl_kwargs = {} if ttl_seconds is None else {"ttl_seconds": ttl_seconds}
    # PHX2-E2E-001: compose consults the dedupe ledger PEEK-ONLY. A duplicate
    # within TTL still suppresses, but no durable row is appended here — the
    # successful-send row is written only after confirmed delivery below.
    deduped = compose_no_send_dispatch_deduped(
        request,
        ath_transport=ath_transport,
        ath_endpoint_secret=ath_endpoint_secret,
        now_utc=now_utc,
        transport_client=fake_client,
        now_seconds=now_seconds,
        ledger=PeekOnlyPingDedupeLedgerView(ledger) if ledger is not None else None,
        **ttl_kwargs,
    )
    compose_result = getattr(deduped, "compose_result", None)
    decision = getattr(compose_result, "decision", None)
    eligible = decision == COMPOSE_DECISION_DISPATCHED  # snapshot built + dedupe allowed (peek)

    send_result = None
    delivery: Optional[Dict[str, Any]] = None
    if eligible and guard is not None and authorization is not None:
        # Second, independent integrity check immediately before the private
        # transport.  It revalidates the same immutable proof and does not
        # recalculate a verdict from display text.
        if security_decision is not None:
            security_valid, security_reason = validate_delivery_decision(security_decision)
            security_reason = (security_reason if not security_valid
                               else delivery_block_reason(security_decision))
            if security_reason:
                return {
                    "deduped": deduped,
                    "compose_decision": decision,
                    "compose_reason": security_reason,
                    "compose_tier": getattr(getattr(compose_result, "snapshot", None), "tier_token", None),
                    "compose_drawdown_pct": getattr(getattr(compose_result, "snapshot", None), "fractional_drop_pct", None),
                    "compose_anchored_ath_mc": getattr(getattr(compose_result, "snapshot", None), "ath_market_cap_display", None),
                    "dedupe_outcome": getattr(deduped, "dedupe_outcome", None),
                    "eligible": False,
                    "send_result": None,
                    "central_ath": {},
                    "activation": dict(activation_proof or {}),
                    "security": (security_decision.to_dict()
                                 if isinstance(security_decision, DeliverySafetyDecision) else None),
                }
        # OBSERVE-ONLY display seam (2026-06-23): arm the optional Axiom-fee-appending transport with the
        # EXACT dispatched body bound to THIS request's mint, right before the guarded send. The appender
        # then appends the mint-bound "Axiom Fees" line to payload["content"] ONLY on an exact body match.
        # Wrapped so a display-arming error can NEVER affect eligibility, the reserve, or the send; the
        # binding is asserted here (mint never parsed from the body downstream).
        if axiom_fee_appender is not None:
            _dispatched_body = getattr(compose_result, "dispatched_body", None)
            if getattr(axiom_fee_appender, "requires_bound_delivery", False):
                try:
                    axiom_fee_appender.bind_delivery(
                        body=_dispatched_body,
                        mint=getattr(request, "token_mint", None),
                        composed_snapshot=getattr(compose_result, "snapshot", None),
                        delivery_context=dict(delivery_context or {}),
                        created_at_utc=created_at_utc,
                    )
                except Exception:
                    # Required-bound transports fail closed when unbound.  The
                    # guarded call still returns a classified attempt result,
                    # but the adapter must not forward the legacy body.
                    pass
            else:
                try:
                    axiom_fee_appender.bind_body(
                        body=_dispatched_body, mint=getattr(request, "token_mint", None)
                    )
                except Exception:
                    pass
        # PHX2-E2E-001 corrected ordering: temporary attempt lease + outbox
        # record -> transport -> classify -> receipt -> ONE successful-send
        # ledger row -> commit. Explicit failure releases the lease (stays
        # retryable); an ambiguous outcome parks as observable DELIVERY_UNKNOWN.
        dedupe_key = derive_ping_dedupe_key(
            getattr(compose_result, "snapshot", None))
        journal = (delivery_journal if delivery_journal is not None
                   else DeliveryAttemptJournal(path=None))
        delivery = execute_guarded_delivery(
            deduped=deduped,
            guard=guard,
            authorization=authorization,
            created_at_utc=created_at_utc,
            journal=journal,
            ledger=ledger,
            dedupe_key=dedupe_key,
            snapshot_body=getattr(compose_result, "dispatched_body", None),
            ttl_seconds=(ttl_seconds if ttl_seconds is not None
                         else STAGE30_11_15_DEFAULT_TTL_SECONDS),
            lease_seconds=attempt_lease_seconds,
            delivery_evidence=axiom_fee_appender,
        )
        send_result = delivery.get("send_result")
    # Observe-only telemetry (2026-06-23): surface the GRANULAR compose reason already computed by the
    # committed composer so a non-dispatched candidate is explainable downstream instead of collapsing to
    # the coarse NO_SEND_NOT_DISPATCHABLE. Pure read of the existing result — changes NO eligibility,
    # reserve, or send behavior (``eligible`` above is unchanged: decision == COMPOSE_DECISION_DISPATCHED).
    # The optional tier/drawdown/anchored-ATH-MC fields exist ONLY on a built snapshot (a dispatch-eligible
    # or dedupe-suppressed result) and are emitted as JSON-safe strings; they are None for an early
    # fail-closed rejection (where the composer attaches no snapshot).
    compose_result_reason = getattr(compose_result, "reason", None)
    composed_snapshot = getattr(compose_result, "snapshot", None)
    return {
        "deduped": deduped,
        "compose_decision": decision,
        "compose_reason": compose_result_reason,
        "compose_tier": getattr(composed_snapshot, "tier_token", None),
        "compose_drawdown_pct": getattr(composed_snapshot, "fractional_drop_pct", None),
        "compose_anchored_ath_mc": getattr(composed_snapshot, "ath_market_cap_display", None),
        "dedupe_outcome": getattr(deduped, "dedupe_outcome", None),
        "eligible": eligible,
        "send_result": send_result,
        "delivery": delivery,
        "central_ath": {
            "ath_price": getattr(request, "authoritative_ath_price", None),
            "ath_market_cap": getattr(
                request, "authoritative_ath_market_cap_usd", None),
            "ath_timestamp": getattr(request, "authoritative_ath_timestamp", None),
            "ath_provider": getattr(request, "authoritative_ath_provider", None),
            "ath_observation_type": getattr(
                request, "authoritative_ath_observation_type", None),
            "ath_status": getattr(request, "authoritative_ath_status", None),
            "ath_transaction_signature": getattr(
                request, "authoritative_ath_transaction_signature", None),
            # The resolved observation the tier and body were actually
            # bound to, echoed so every send/candidate artifact records it.
            "resolved_ath_price": getattr(request, "resolved_ath_price", None),
            "resolved_supply": getattr(request, "resolved_supply", None),
            "resolved_supply_basis": getattr(
                request, "resolved_supply_basis", None),
            "resolved_ath_market_cap": getattr(
                request, "resolved_ath_market_cap_usd", None),
            "resolved_observed_at_utc": getattr(
                request, "resolved_observed_at_utc", None),
            "resolution_method": getattr(request, "resolution_method", None),
        },
        # Under PHX1_PARITY a candidate may legitimately reach here with NO
        # activation proof at all, so this must tolerate None (it used to be
        # guaranteed non-None by the hard gate above).
        "activation": dict(activation_proof or {}),
        "security": (security_decision.to_dict()
                     if isinstance(security_decision, DeliverySafetyDecision) else None),
        "alert_policy": _policy,
        "activation_enforcement": _activation_enforcement,
        "activation_proof_present": bool(_activation_eligible),
    }


def make_guard(*, transport: Any):
    """Build the committed cap-1 real-send guard over the (real or fake) private transport."""
    return make_stage30_11_16_real_private_transport_guard(transport=transport)


__all__ = (
    "COMPOSE_DECISION_DISPATCHED",
    "STAGE30_11_16_AUTHORIZATION_CONFIRM_TOKEN",
    "build_revalidation_request",
    "build_authorization",
    "make_real_private_transport",
    "make_recording_fake_transport_client",
    "make_guard",
    "compose_and_maybe_send",
)

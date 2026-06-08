"""Stage 30.11.16 real private transport guard (no-send by default).

The pure, stateful, one-shot GUARD that sits BETWEEN the committed Stage 30.11.15
deduped no-send compose result and an INJECTED Stage 28-shaped audited private
transport. It is the separate, explicitly operator-authorized seam the prior
controlled ceremonies described but never built in code -- and it is no-send by
default: with no transport injected it only RECORDS a would-send; a real send
happens only when the ceremony injects a real audited transport AND supplies a
valid authorization sentinel.

    a committed Stage 30.11.15 ``Stage30_11_15DedupedComposeResult``
      + an explicit ``Stage30_11_16RealSendAuthorization`` sentinel
      + a private-only ``Stage30_11_16TransportTarget`` (locked at construction)
      + an OPTIONAL injected duck-typed private transport (``None`` by default)
      -> a fail-closed gate chain (cap -> authorization -> deduped-result +
         real-compose-result provenance -> dedupe allowed -> compose dispatched
         -> real-snapshot provenance -> body present -> private-only target
         identity -> minimal ``{"content": body}`` payload)
      -> consume the one-shot cap (burn-on-attempt) and EITHER record a would-send
         (no transport) OR forward EXACTLY ONE ``send_one_audited_post`` to the
         injected transport
      -> a redaction-safe ``Stage30_11_16RealSendResult``

The guard reuses the existing audited private transport (the Stage 28.4 audited
HTTP primitive wrapped by the Stage 28.9 private webhook wrapper) WITHOUT
importing Stage 28: the ceremony INJECTS that wrapper as a duck-typed
``send_one_audited_post(webhook_identity=..., payload=...)`` transport. The guard
reads the returned verdict duck-typed (``ok`` / ``transport_status``); it NEVER
fabricates success and NEVER echoes a url / body / exception text / secret.

Cap policy -- BURN-ON-ATTEMPT. The one-shot cap is consumed the moment every gate
passes, BEFORE the would-send / forward decision. If the injected transport
raises AFTER the cap is consumed, the guard returns ``TRANSPORT_EXCEPTION``, the
cap REMAINS consumed, and the same guard instance never retries -- a fail-safe
against an accidental double-send. A second gate-passing call on the same guard
returns ``CAP_EXHAUSTED``. A gate that FAILS does NOT consume the cap (a
misconfiguration can be corrected and retried with a fresh, still-armed guard).

Because a ``Stage30_11_15DedupedComposeResult`` whose ``compose_result`` is a REAL
committed Stage 30.11.13 ``Stage30_11_13ComposeResult`` -- decision
``NO_SEND_DISPATCHED``, a REAL ``Stage30_11_13ComposedSnapshot``, and an
``allowed`` ``Stage30_11_15PingDedupeOutcome`` -- can ONLY be produced by the
committed composer AFTER it passed anchored ATH, the stale current-price guard,
market-context freshness, the frozen snapshot gate/body binding, the ATH
market-cap computation, AND the cross-run dedupe reserve, requiring that exact
TYPED shape makes the guard inherit ALL of those upstream guarantees -- it
re-derives none of them and touches no ledger (no double reserve). The
``compose_result`` and its ``snapshot`` are isinstance-checked against the
committed Stage 30.11.13 dataclasses (and the ``dedupe_outcome`` against the
committed Stage 30.11.15 type), NOT merely duck-read, so a forged inner object --
a plain object spoofing a ``NO_SEND_DISPATCHED`` decision, an ``object()``
snapshot, and a ``"[FORGED BODY]"`` -- can NOT be wrapped in a genuine deduped
result and forwarded.

This module builds the guard ONLY. It reads NO process environment, opens NO
network connection, opens NO database, writes NO file, reserves NO dispatch,
sends NO message itself, signs nothing, trades nothing, and edits NO composer /
dedupe / ATH-anchoring / market-freshness / Stage 30.12 renderer / tier-band
file. The real one-send ceremony remains a SEPARATE, explicitly
operator-authorized step this slice does not run.

Discipline:

  * Stdlib only (``typing``).
  * Imports ONLY the Stage 30.11.16 models sibling + the committed Stage 30.11.15
    deduped-result / dedupe-outcome types + the committed Stage 30.11.13
    compose-result / composed-snapshot dataclasses (to TYPE-CHECK -- not merely
    duck-read -- the consumed compose result and its frozen snapshot, so a forged
    inner object can NOT be wrapped in a real deduped result and forwarded). No
    Stage 21-29 import; in particular NO Stage 28 transport import -- the real
    audited transport is ALWAYS injected duck-typed. The committed dispatched
    compose-decision token is still mirrored BY VALUE in the models sibling
    (``STAGE30_11_16_REQUIRED_COMPOSE_DECISION``), so the composer's string
    constant is not imported just to read a value; only its dataclasses are
    imported, for provenance type checks that stay inside the Stage 30 family.
  * No ``os.environ`` / ``os.getenv`` access; no env read.
  * No network, no HTTP, no gRPC, no WebSocket, no socket.
  * No database / SQLite, no zstd / compression, no default storage root.
  * No url, host, webhook destination, wallet / signing, trading, or public /
    subscriber routing reference.
  * No PHX1 import. No ``time`` / ``datetime`` import; ``created_at_utc`` is
    caller-injected.
  * No module-level Call node (no implicit I/O at import time; the default
    private-operator target is built by a factory CALLED at construction time,
    never a module-level constant).
"""

from __future__ import annotations

from typing import Any, Mapping, Optional, Protocol, runtime_checkable

from PHX2.stage30.stage30_11_13_committed_no_send_composer import (
    Stage30_11_13ComposedSnapshot,
    Stage30_11_13ComposeResult,
)
from PHX2.stage30.stage30_11_15_no_send_dedupe_guard import (
    Stage30_11_15DedupedComposeResult,
)
from PHX2.stage30.stage30_11_15_ping_dedupe_models import (
    Stage30_11_15PingDedupeOutcome,
)
from PHX2.stage30.stage30_11_16_real_send_models import (
    REAL_SEND_DECISION_FORWARDED_TO_TRANSPORT,
    REAL_SEND_DECISION_REFUSED,
    REAL_SEND_DECISION_WOULD_SEND_NO_TRANSPORT,
    REAL_SEND_REASON_BODY_MISSING,
    REAL_SEND_REASON_CAP_EXHAUSTED,
    REAL_SEND_REASON_COMPOSE_NOT_DISPATCHED,
    REAL_SEND_REASON_DEDUPE_NOT_ALLOWED,
    REAL_SEND_REASON_FORBIDDEN_PAYLOAD_FIELD,
    REAL_SEND_REASON_FORWARDED_ONE_PRIVATE_OPERATOR_MESSAGE,
    REAL_SEND_REASON_INVALID_AUTHORIZATION_TYPE,
    REAL_SEND_REASON_INVALID_COMPOSE_RESULT,
    REAL_SEND_REASON_INVALID_SNAPSHOT_PROVENANCE,
    REAL_SEND_REASON_INVALID_TARGET_IDENTITY,
    REAL_SEND_REASON_NOT_AUTHORIZED,
    REAL_SEND_REASON_SNAPSHOT_MISSING,
    REAL_SEND_REASON_TRANSPORT_EXCEPTION,
    REAL_SEND_REASON_WOULD_SEND_RECORDED_NO_TRANSPORT,
    STAGE30_11_16_MAX_DISPATCHES,
    STAGE30_11_16_PAYLOAD_CONTENT_KEY,
    STAGE30_11_16_PRIVATE_OPERATOR_IDENTITY,
    STAGE30_11_16_PRIVATE_OPERATOR_VISIBILITY,
    STAGE30_11_16_REDACTED_UNSAFE_ID,
    STAGE30_11_16_REDACTED_UNSAFE_IDENTITY,
    STAGE30_11_16_REDACTION_STATUS_REDACTED,
    STAGE30_11_16_REQUIRED_COMPOSE_DECISION,
    Stage30_11_16RealSendAuthorization,
    Stage30_11_16RealSendResult,
    Stage30_11_16TransportTarget,
    is_minimal_content_payload,
    is_nonblank_str,
    is_real_send_authorization,
    is_safe_echo_id,
    is_safe_operator_token,
    is_valid_transport_target,
)


# ---------------------------------------------------------------------------
# Injected transport protocol (the Stage 28.9 wrapper SHAPE; duck-typed)
# ---------------------------------------------------------------------------


@runtime_checkable
class Stage30_11_16PrivateTransport(Protocol):
    """The duck-typed private transport the guard forwards to.

    Exactly the Stage 28.9 private webhook wrapper SHAPE: one method,
    ``send_one_audited_post(*, webhook_identity, payload)``, returning a verdict
    the guard reads duck-typed (``ok`` / ``transport_status``). The real
    ``Stage28_9PrivateWebhookTransport`` over a real ``Stage28_4AuditedHttpTransport``
    satisfies this protocol; a Stage 30.11.16 recording FAKE satisfies it too. The
    real webhook is bound INSIDE the implementation, never passed here.
    """

    def send_one_audited_post(
        self, *, webhook_identity: str, payload: Mapping[str, Any]
    ) -> Any:
        ...


# ---------------------------------------------------------------------------
# Default private-operator target factory (CALLED at construction time)
# ---------------------------------------------------------------------------


def make_default_private_operator_target() -> Stage30_11_16TransportTarget:
    """Build the default private-only transport target (the locked private
    operator identity + visibility). Called at guard construction time -- NOT a
    module-level constant (no top-level Call). Pure.
    """
    return Stage30_11_16TransportTarget(
        webhook_identity=STAGE30_11_16_PRIVATE_OPERATOR_IDENTITY,
        visibility=STAGE30_11_16_PRIVATE_OPERATOR_VISIBILITY,
    )


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def _echo_id(value: object) -> str:
    """Return a safe-to-echo label for a consumed-result id (token mint /
    candidate id).

    Echoes the id ONLY when it is a safe-echo id (``is_safe_echo_id`` rejects any
    newline / control char / whitespace / path / url / quote character, or an
    over-long value); a PRESENT-but-unsafe id becomes the locked
    ``STAGE30_11_16_REDACTED_UNSAFE_ID`` placeholder; an absent / non-string id
    becomes ``""``. So a forged id can NEVER inject raw text into the result
    record (or its repr). Pure / total; never raises.
    """
    if not isinstance(value, str) or value == "":
        return ""
    if is_safe_echo_id(value):
        return value
    return STAGE30_11_16_REDACTED_UNSAFE_ID


def _safe_ids(deduped_result: object) -> "tuple[str, str]":
    """Return the ``(token_mint, candidate_id)`` echoed from the consumed deduped
    result's ``compose_result``, each SANITIZED to a safe-echo id (the locked
    redacted-unsafe placeholder when present-but-unsafe, ``""`` when unreadable).
    Pure / total; never raises -- so a refusal BEFORE the result is validated
    still echoes only safe ids.
    """
    if not isinstance(deduped_result, Stage30_11_15DedupedComposeResult):
        return "", ""
    compose_result = getattr(deduped_result, "compose_result", None)
    if compose_result is None:
        return "", ""
    return (
        _echo_id(getattr(compose_result, "token_mint", None)),
        _echo_id(getattr(compose_result, "candidate_id", None)),
    )


def _safe_identity_echo(target: object) -> str:
    """Return a safe-to-echo webhook identity label for a target.

    Echoes the target's identity label ONLY when it is a safe operator token
    (``is_safe_operator_token`` rejects any url-shaped / dotted / slashed value);
    otherwise returns the locked redacted-unsafe placeholder. So a malformed
    identity can never reach the result record. Pure / total; never raises.
    """
    identity = getattr(target, "webhook_identity", None)
    if is_safe_operator_token(identity):
        return identity
    return STAGE30_11_16_REDACTED_UNSAFE_IDENTITY


# ---------------------------------------------------------------------------
# The guard (stateful; one-shot, burn-on-attempt cap)
# ---------------------------------------------------------------------------


class Stage30_11_16RealPrivateTransportGuard:
    """A stateful, one-shot real private transport guard.

    Construct with an OPTIONAL duck-typed private transport (``None`` by default
    -- the no-send default) and a private-only target (the locked private
    operator target by default). Each ``authorize_and_dispatch`` call runs the
    fail-closed gate chain and, only if every gate passes, consumes the one-shot
    cap (burn-on-attempt) and EITHER records a would-send (no transport) OR
    forwards exactly one ``send_one_audited_post`` to the injected transport.
    """

    def __init__(
        self,
        *,
        transport: Optional[Stage30_11_16PrivateTransport] = None,
        target: Optional[Stage30_11_16TransportTarget] = None,
    ) -> None:
        self._transport: Optional[Stage30_11_16PrivateTransport] = transport
        self._target: Stage30_11_16TransportTarget = (
            target if target is not None
            else make_default_private_operator_target()
        )
        self._cap_consumed: bool = False
        self._forwarded_call_count: int = 0

    @property
    def dispatch_cap(self) -> int:
        """The locked one-shot dispatch cap (``1``)."""
        return STAGE30_11_16_MAX_DISPATCHES

    @property
    def cap_consumed(self) -> bool:
        """``True`` once a gate-passing call has consumed the one-shot cap."""
        return self._cap_consumed

    @property
    def forwarded_call_count(self) -> int:
        """The number of times the guard reached the injected transport (a
        forward attempt, including one that raised). Proves exactly-once.
        """
        return self._forwarded_call_count

    @property
    def target(self) -> Stage30_11_16TransportTarget:
        """The private-only transport target bound at construction."""
        return self._target

    def authorize_and_dispatch(
        self,
        deduped_result: Any,
        *,
        authorization: Any,
        created_at_utc: str,
    ) -> Stage30_11_16RealSendResult:
        """Run the fail-closed gate chain over ``deduped_result`` and, only if
        every gate passes, consume the one-shot cap and record a would-send (no
        transport) or forward exactly one private operator message.

        Returns a redaction-safe ``Stage30_11_16RealSendResult``; never raises
        (an injected-transport exception is caught and mapped to a redacted
        ``TRANSPORT_EXCEPTION`` refusal). ``KeyboardInterrupt`` / ``SystemExit``
        are NOT swallowed.
        """
        # ---- 1. one-shot cap already consumed -> refuse (transport untouched) --
        if self._cap_consumed:
            return self._build(
                deduped_result,
                decision=REAL_SEND_DECISION_REFUSED,
                reason=REAL_SEND_REASON_CAP_EXHAUSTED,
                dispatch_forwarded=False,
                transport_attempted=False,
                transport_status=None,
                transport_ok=None,
                cap_consumed=True,
                created_at_utc=created_at_utc,
            )

        # ---- 2. explicit operator authorization sentinel ----------------------
        if authorization is None:
            return self._build(
                deduped_result,
                decision=REAL_SEND_DECISION_REFUSED,
                reason=REAL_SEND_REASON_NOT_AUTHORIZED,
                dispatch_forwarded=False,
                transport_attempted=False,
                transport_status=None,
                transport_ok=None,
                cap_consumed=False,
                created_at_utc=created_at_utc,
            )
        if not isinstance(authorization, Stage30_11_16RealSendAuthorization):
            return self._build(
                deduped_result,
                decision=REAL_SEND_DECISION_REFUSED,
                reason=REAL_SEND_REASON_INVALID_AUTHORIZATION_TYPE,
                dispatch_forwarded=False,
                transport_attempted=False,
                transport_status=None,
                transport_ok=None,
                cap_consumed=False,
                created_at_utc=created_at_utc,
            )
        if not is_real_send_authorization(authorization):
            return self._build(
                deduped_result,
                decision=REAL_SEND_DECISION_REFUSED,
                reason=REAL_SEND_REASON_NOT_AUTHORIZED,
                dispatch_forwarded=False,
                transport_attempted=False,
                transport_status=None,
                transport_ok=None,
                cap_consumed=False,
                created_at_utc=created_at_utc,
            )

        # ---- 3. consumed deduped compose result shape + PROVENANCE ------------
        #         The wrapper must be the committed Stage 30.11.15 deduped result
        #         AND its inner ``compose_result`` must be a REAL committed Stage
        #         30.11.13 ``Stage30_11_13ComposeResult`` -- NOT merely a
        #         duck-typed object that happens to carry a ``decision`` /
        #         ``snapshot`` / ``dispatched_body``. This is the first provenance
        #         gate: a forged inner object (with a spoofed
        #         ``NO_SEND_DISPATCHED`` decision, an ``object()`` snapshot, and a
        #         ``"[FORGED BODY]"``) wrapped in a genuine deduped result fails
        #         closed HERE, so only output proven to come from the real
        #         composer is ever forwarded. ``isinstance(None, ...)`` is False,
        #         so a missing inner result is caught by the same gate.
        if not isinstance(deduped_result, Stage30_11_15DedupedComposeResult):
            return self._build(
                deduped_result,
                decision=REAL_SEND_DECISION_REFUSED,
                reason=REAL_SEND_REASON_INVALID_COMPOSE_RESULT,
                dispatch_forwarded=False,
                transport_attempted=False,
                transport_status=None,
                transport_ok=None,
                cap_consumed=False,
                created_at_utc=created_at_utc,
            )
        compose_result = getattr(deduped_result, "compose_result", None)
        if not isinstance(compose_result, Stage30_11_13ComposeResult):
            return self._build(
                deduped_result,
                decision=REAL_SEND_DECISION_REFUSED,
                reason=REAL_SEND_REASON_INVALID_COMPOSE_RESULT,
                dispatch_forwarded=False,
                transport_attempted=False,
                transport_status=None,
                transport_ok=None,
                cap_consumed=False,
                created_at_utc=created_at_utc,
            )

        # ---- 4. dedupe outcome must be ALLOWED --------------------------------
        dedupe_outcome = getattr(deduped_result, "dedupe_outcome", None)
        if (
            not isinstance(dedupe_outcome, Stage30_11_15PingDedupeOutcome)
            or dedupe_outcome.allowed is not True
        ):
            return self._build(
                deduped_result,
                decision=REAL_SEND_DECISION_REFUSED,
                reason=REAL_SEND_REASON_DEDUPE_NOT_ALLOWED,
                dispatch_forwarded=False,
                transport_attempted=False,
                transport_status=None,
                transport_ok=None,
                cap_consumed=False,
                created_at_utc=created_at_utc,
            )

        # ---- 5. compose decision must be NO_SEND_DISPATCHED -------------------
        if (
            getattr(compose_result, "decision", None)
            != STAGE30_11_16_REQUIRED_COMPOSE_DECISION
        ):
            return self._build(
                deduped_result,
                decision=REAL_SEND_DECISION_REFUSED,
                reason=REAL_SEND_REASON_COMPOSE_NOT_DISPATCHED,
                dispatch_forwarded=False,
                transport_attempted=False,
                transport_status=None,
                transport_ok=None,
                cap_consumed=False,
                created_at_utc=created_at_utc,
            )

        # ---- 6. the frozen snapshot must EXIST and carry PROVENANCE -----------
        #         The second provenance gate: the snapshot must be a REAL
        #         committed Stage 30.11.13 ``Stage30_11_13ComposedSnapshot``. A
        #         missing snapshot (``None``) fails closed as SNAPSHOT_MISSING; a
        #         snapshot that is PRESENT but is a forged / wrong-type object
        #         (e.g. ``object()``) fails closed as INVALID_SNAPSHOT_PROVENANCE
        #         -- it can never be forwarded as if it were the real frozen
        #         snapshot the composer bound the body to.
        snapshot = getattr(compose_result, "snapshot", None)
        if snapshot is None:
            return self._build(
                deduped_result,
                decision=REAL_SEND_DECISION_REFUSED,
                reason=REAL_SEND_REASON_SNAPSHOT_MISSING,
                dispatch_forwarded=False,
                transport_attempted=False,
                transport_status=None,
                transport_ok=None,
                cap_consumed=False,
                created_at_utc=created_at_utc,
            )
        if not isinstance(snapshot, Stage30_11_13ComposedSnapshot):
            return self._build(
                deduped_result,
                decision=REAL_SEND_DECISION_REFUSED,
                reason=REAL_SEND_REASON_INVALID_SNAPSHOT_PROVENANCE,
                dispatch_forwarded=False,
                transport_attempted=False,
                transport_status=None,
                transport_ok=None,
                cap_consumed=False,
                created_at_utc=created_at_utc,
            )

        # ---- 7. the dispatched body must be non-blank -------------------------
        body = getattr(compose_result, "dispatched_body", None)
        if not is_nonblank_str(body):
            return self._build(
                deduped_result,
                decision=REAL_SEND_DECISION_REFUSED,
                reason=REAL_SEND_REASON_BODY_MISSING,
                dispatch_forwarded=False,
                transport_attempted=False,
                transport_status=None,
                transport_ok=None,
                cap_consumed=False,
                created_at_utc=created_at_utc,
            )

        # ---- 8. the target must be the private-only operator identity ---------
        if not is_valid_transport_target(self._target):
            return self._build(
                deduped_result,
                decision=REAL_SEND_DECISION_REFUSED,
                reason=REAL_SEND_REASON_INVALID_TARGET_IDENTITY,
                dispatch_forwarded=False,
                transport_attempted=False,
                transport_status=None,
                transport_ok=None,
                cap_consumed=False,
                created_at_utc=created_at_utc,
            )

        # ---- 9./10. build + validate the minimal payload ----------------------
        payload = {STAGE30_11_16_PAYLOAD_CONTENT_KEY: body}
        if not is_minimal_content_payload(payload):
            return self._build(
                deduped_result,
                decision=REAL_SEND_DECISION_REFUSED,
                reason=REAL_SEND_REASON_FORBIDDEN_PAYLOAD_FIELD,
                dispatch_forwarded=False,
                transport_attempted=False,
                transport_status=None,
                transport_ok=None,
                cap_consumed=False,
                created_at_utc=created_at_utc,
            )

        # ---- 11. BURN-ON-ATTEMPT: consume the one-shot cap BEFORE the would-send
        #          / forward decision, so a transport that raises can never be
        #          retried into a double-send. -------------------------------
        self._cap_consumed = True

        # ---- 12. no transport injected -> record a would-send (no-send default)
        if self._transport is None:
            return self._build(
                deduped_result,
                decision=REAL_SEND_DECISION_WOULD_SEND_NO_TRANSPORT,
                reason=REAL_SEND_REASON_WOULD_SEND_RECORDED_NO_TRANSPORT,
                dispatch_forwarded=False,
                transport_attempted=False,
                transport_status=None,
                transport_ok=None,
                cap_consumed=True,
                created_at_utc=created_at_utc,
            )

        # ---- 13. forward EXACTLY ONE audited post to the injected transport ---
        self._forwarded_call_count += 1
        try:
            transport_result = self._transport.send_one_audited_post(
                webhook_identity=self._target.webhook_identity,
                payload=payload,
            )
        except Exception:
            # ---- 14. the transport raised: fail closed, redacted (no exception
            #          text retained -- it could carry a transport secret). The
            #          cap REMAINS consumed; the same guard never retries.
            return self._build(
                deduped_result,
                decision=REAL_SEND_DECISION_REFUSED,
                reason=REAL_SEND_REASON_TRANSPORT_EXCEPTION,
                dispatch_forwarded=False,
                transport_attempted=True,
                transport_status=None,
                transport_ok=None,
                cap_consumed=True,
                created_at_utc=created_at_utc,
            )

        # The forward completed. Read the verdict DUCK-TYPED; NEVER fabricate
        # success -- a non-bool ok / non-str status maps to ``None``, and a
        # transport that reports a failure status surfaces verbatim.
        status = getattr(transport_result, "transport_status", None)
        ok = getattr(transport_result, "ok", None)
        return self._build(
            deduped_result,
            decision=REAL_SEND_DECISION_FORWARDED_TO_TRANSPORT,
            reason=REAL_SEND_REASON_FORWARDED_ONE_PRIVATE_OPERATOR_MESSAGE,
            dispatch_forwarded=True,
            transport_attempted=True,
            transport_status=status if isinstance(status, str) else None,
            transport_ok=ok if isinstance(ok, bool) else None,
            cap_consumed=True,
            created_at_utc=created_at_utc,
        )

    def _build(
        self,
        deduped_result: object,
        *,
        decision: str,
        reason: str,
        dispatch_forwarded: bool,
        transport_attempted: bool,
        transport_status: Optional[str],
        transport_ok: Optional[bool],
        cap_consumed: bool,
        created_at_utc: str,
    ) -> Stage30_11_16RealSendResult:
        token_mint, candidate_id = _safe_ids(deduped_result)
        return Stage30_11_16RealSendResult(
            decision=decision,
            reason=reason,
            token_mint=token_mint,
            candidate_id=candidate_id,
            dispatch_forwarded=dispatch_forwarded,
            transport_attempted=transport_attempted,
            transport_status=transport_status,
            transport_ok=transport_ok,
            webhook_identity=_safe_identity_echo(self._target),
            cap_consumed=cap_consumed,
            redaction_status=STAGE30_11_16_REDACTION_STATUS_REDACTED,
            created_at_utc=created_at_utc,
        )


def make_stage30_11_16_real_private_transport_guard(
    *,
    transport: Optional[Stage30_11_16PrivateTransport] = None,
    target: Optional[Stage30_11_16TransportTarget] = None,
) -> Stage30_11_16RealPrivateTransportGuard:
    """Build a Stage 30.11.16 real private transport guard.

    ``transport`` defaults to ``None`` (the no-send default -- a gate-passing call
    records a would-send, nothing is reached); ``target`` defaults to the locked
    private-operator target. The real audited transport is injected ONLY at the
    separate operator-authorized ceremony.
    """
    return Stage30_11_16RealPrivateTransportGuard(
        transport=transport, target=target
    )


__all__ = (
    "Stage30_11_16PrivateTransport",
    "make_default_private_operator_target",
    "Stage30_11_16RealPrivateTransportGuard",
    "make_stage30_11_16_real_private_transport_guard",
)

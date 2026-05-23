"""Stage 27.7b controlled one-ping live smoke dispatch.

Stage 27.7b ships the controlled one-ping live smoke dispatch
boundary. The dispatch:

  * accepts EXACTLY ONE rendered Stage 27.5 private ping payload
    per call (multi-payload / batch dispatch is REFUSED with the
    ``REFUSED_MULTIPLE_PAYLOADS`` status),
  * requires Stage 27.1 mode authority to resolve to
    ``LIVE_ALLOWED`` (the two-factor LIVE authorization composite),
  * requires the explicit operator ``operator_live_request=True``
    cross-check argument,
  * requires the explicit ``smoke_dispatch_request=True`` argument,
  * supports a ``DRY_RUN`` mode that never calls the transport,
  * supports a ``LIVE_SEND`` mode that calls the injected transport
    once,
  * REFUSES UNKNOWN / DISAGREE pairs in any mode (returning
    ``REFUSED_SUPPRESSED_PAIR``),
  * REFUSES USDC pairs that do not carry the
    ``RENDERED_OBSERVE_ONLY`` render-status warning,
  * REFUSES SOL pairs that did not land on the
    ``EXISTING_SOL_LANE`` (defensive belt-and-braces),
  * NEVER reads the process environment,
  * NEVER opens a network connection itself; the transport is
    injected,
  * NEVER stores the webhook URL on the returned dispatch result
    record.

Stage 27.7b dispatch invariants:

  * one smoke run sends at most one ping,
  * multi-ping live dispatch is refused,
  * batch dispatch is refused,
  * public routing is absent,
  * subscriber routing is absent,
  * paid tier routing is absent,
  * retry loops are absent,
  * daemon / background-worker behaviour is absent,
  * scheduler / queue behaviour is absent,
  * Stage 26 candidate policy enforcement is absent,
  * Stage 29 enforcement is absent.

This module imports only stdlib (``typing``) plus Stage 27.2 /
27.5 / 27.6 / 27.7b production modules. It does NOT import Stage
21-26 production code, does NOT import Stage 27.1 production code,
does NOT import any network / RPC / messaging / DB / scheduler /
secrets-management library, does NOT read the process environment,
does NOT define a CLI surface, and contains no top-level I/O.

The Stage 27.1 ``LIVE_MODE_AUTHORITY_LIVE_ALLOWED`` literal is
mirrored here as ``LIVE_MODE_AUTHORITY_LIVE_ALLOWED`` so the Stage
27.7b dispatch boundary does NOT import Stage 27.1 production code
(the Stage 27.7a boundary discipline carries forward).
"""

from __future__ import annotations

from typing import Optional, Sequence

from PHX2.stage27.bounded_tradeable_ping_runner import (
    LIVE_AUTHORITY_LIVE_ALLOWED as _LIVE_AUTHORITY_LIVE_ALLOWED,
)
from PHX2.stage27.pair_detection_constants import (
    CALIBRATION_LANE_EXISTING_SOL_LANE,
    PAIR_DETECTION_STATUS_DISAGREE,
    PAIR_DETECTION_STATUS_UNRESOLVED,
    QUOTE_ASSET_SOL,
    QUOTE_ASSET_UNKNOWN,
    QUOTE_ASSET_USDC,
)
from PHX2.stage27.private_discord_models import (
    DISPATCH_MODE_DRY_RUN,
    DISPATCH_MODE_LIVE_SEND,
    DISPATCH_MODE_VALUES,
    DISPATCH_REASON_DRY_RUN_MODE,
    DISPATCH_REASON_LIVE_AUTHORITY_NOT_ALLOWED,
    DISPATCH_REASON_MULTIPLE_PAYLOADS_REFUSED,
    DISPATCH_REASON_NO_PAYLOAD_PROVIDED,
    DISPATCH_REASON_OPERATOR_LIVE_REQUEST_MISSING,
    DISPATCH_REASON_PAIR_SOL_NOT_ON_EXISTING_LANE,
    DISPATCH_REASON_PAIR_SUPPRESS_DISAGREE,
    DISPATCH_REASON_PAIR_SUPPRESS_UNKNOWN,
    DISPATCH_REASON_PAIR_USDC_REQUIRES_OBSERVE_ONLY,
    DISPATCH_REASON_SMOKE_DISPATCH_REQUEST_MISSING,
    DISPATCH_REASON_UNKNOWN_DISPATCH_MODE,
    DISPATCH_REASON_WEBHOOK_IDENTITY_MISSING,
    DISPATCH_REASON_WEBHOOK_URL_MISSING,
    DISPATCH_STATUS_DRY_RUN_NOT_SENT,
    DISPATCH_STATUS_REFUSED_MISSING_WEBHOOK,
    DISPATCH_STATUS_REFUSED_MULTIPLE_PAYLOADS,
    DISPATCH_STATUS_REFUSED_NOT_LIVE,
    DISPATCH_STATUS_REFUSED_SUPPRESSED_PAIR,
    DISPATCH_STATUS_REFUSED_UNAUTHORIZED_MODE,
    NO_PAYLOAD_SENTINEL,
    REDACTION_STATUS_REDACTED,
    STAGE27_7B_DISPATCH_RESULT_SCHEMA_VERSION,
    Stage27_7bDispatchResultRecord,
)
from PHX2.stage27.private_discord_sender import (
    Stage27_7bDiscordTransport,
    Stage27_7bDispatchClock,
    send_one_private_ping,
)
from PHX2.stage27.private_ping_models import (
    PrivatePingPayloadRecord,
    RENDER_STATUS_RENDERED_OBSERVE_ONLY,
)


# ---------------------------------------------------------------------------
# Mirrored Stage 27.1 token (defensive: Stage 27.7b does NOT import 27.1)
# ---------------------------------------------------------------------------


LIVE_MODE_AUTHORITY_LIVE_ALLOWED: str = _LIVE_AUTHORITY_LIVE_ALLOWED


# ---------------------------------------------------------------------------
# One-ping smoke bound (locked)
# ---------------------------------------------------------------------------


# Stage 27.7b sends AT MOST one private ping per dispatch call. The
# dispatch refuses any ``payloads`` argument whose length is not
# exactly 1.
STAGE27_7B_MAX_PAYLOADS_PER_DISPATCH: int = 1


# ---------------------------------------------------------------------------
# Refusal-result builder
# ---------------------------------------------------------------------------


def _build_refusal_result(
    *,
    dispatch_status: str,
    dispatch_reason: str,
    dispatch_mode: str,
    webhook_identity: str,
    payload: Optional[PrivatePingPayloadRecord],
    run_id: Optional[str],
    session_id: Optional[str],
    sent_at_utc: str,
) -> Stage27_7bDispatchResultRecord:
    if payload is None:
        ping_id = NO_PAYLOAD_SENTINEL
        pair_quote_asset = NO_PAYLOAD_SENTINEL
        render_status = NO_PAYLOAD_SENTINEL
    else:
        ping_id = payload.ping_id
        pair_quote_asset = payload.quote_asset
        render_status = payload.render_status

    return Stage27_7bDispatchResultRecord(
        dispatch_status=dispatch_status,
        dispatch_reason=dispatch_reason,
        dispatch_mode=dispatch_mode,
        webhook_identity=webhook_identity,
        ping_id=ping_id,
        run_id=run_id,
        session_id=session_id,
        sent_at_utc=sent_at_utc,
        transport_status_code=None,
        redaction_status=REDACTION_STATUS_REDACTED,
        schema_version=STAGE27_7B_DISPATCH_RESULT_SCHEMA_VERSION,
        pair_quote_asset=pair_quote_asset,
        render_status=render_status,
    )


# ---------------------------------------------------------------------------
# Pair-aware refusal helpers
# ---------------------------------------------------------------------------


def _pair_refusal_for_payload(
    payload: PrivatePingPayloadRecord,
) -> Optional[tuple[str, str]]:
    """Return ``(dispatch_status, dispatch_reason)`` if the pair refuses live send.

    Returns ``None`` when the pair is allowed to send (subject to all
    other gates passing). Pure / deterministic.

    Rules:

      * UNKNOWN quote asset OR ``pair_detection_status=UNRESOLVED``
        -> ``REFUSED_SUPPRESSED_PAIR`` /
        ``PAIR_SUPPRESS_UNKNOWN``.
      * ``pair_detection_status=DISAGREE`` ->
        ``REFUSED_SUPPRESSED_PAIR`` / ``PAIR_SUPPRESS_DISAGREE``.
      * USDC quote asset WITHOUT
        ``render_status=RENDERED_OBSERVE_ONLY`` ->
        ``REFUSED_SUPPRESSED_PAIR`` /
        ``PAIR_USDC_REQUIRES_OBSERVE_ONLY``.
      * SOL quote asset NOT on the
        ``EXISTING_SOL_LANE`` calibration lane ->
        ``REFUSED_SUPPRESSED_PAIR`` /
        ``PAIR_SOL_NOT_ON_EXISTING_LANE`` (defensive belt-and-braces;
        Stage 27.2 / 27.5 already gate this upstream).
    """
    if (
        payload.quote_asset == QUOTE_ASSET_UNKNOWN
        or payload.pair_detection_status
        == PAIR_DETECTION_STATUS_UNRESOLVED
    ):
        return (
            DISPATCH_STATUS_REFUSED_SUPPRESSED_PAIR,
            DISPATCH_REASON_PAIR_SUPPRESS_UNKNOWN,
        )

    if (
        payload.pair_detection_status
        == PAIR_DETECTION_STATUS_DISAGREE
    ):
        return (
            DISPATCH_STATUS_REFUSED_SUPPRESSED_PAIR,
            DISPATCH_REASON_PAIR_SUPPRESS_DISAGREE,
        )

    if payload.quote_asset == QUOTE_ASSET_USDC:
        if (
            payload.render_status
            != RENDER_STATUS_RENDERED_OBSERVE_ONLY
        ):
            return (
                DISPATCH_STATUS_REFUSED_SUPPRESSED_PAIR,
                DISPATCH_REASON_PAIR_USDC_REQUIRES_OBSERVE_ONLY,
            )
        return None

    if payload.quote_asset == QUOTE_ASSET_SOL:
        # Defensive: SOL must never have landed on a non-SOL lane.
        # Stage 27.2 / 27.5 enforce this upstream; we re-check here
        # so a future refactor cannot silently widen.
        if (
            payload.calibration_lane
            != CALIBRATION_LANE_EXISTING_SOL_LANE
        ):
            return (
                DISPATCH_STATUS_REFUSED_SUPPRESSED_PAIR,
                DISPATCH_REASON_PAIR_SOL_NOT_ON_EXISTING_LANE,
            )
        return None

    # Any other quote_asset value (none expected at Stage 27.7b) is
    # treated as an UNKNOWN-pair refusal.
    return (
        DISPATCH_STATUS_REFUSED_SUPPRESSED_PAIR,
        DISPATCH_REASON_PAIR_SUPPRESS_UNKNOWN,
    )


# ---------------------------------------------------------------------------
# Webhook-identity safety
# ---------------------------------------------------------------------------


def _webhook_identity_or_missing(webhook_identity: object) -> str:
    """Return ``webhook_identity`` when it is a non-empty string;
    otherwise the ``"<missing>"`` literal.

    Stamping the literal keeps the dispatch result record schema-
    stable (every field is a string) without ever populating the
    raw URL anywhere.
    """
    if isinstance(webhook_identity, str) and webhook_identity != "":
        return webhook_identity
    return "<missing>"


# ---------------------------------------------------------------------------
# Public dispatch entrypoint
# ---------------------------------------------------------------------------


def dispatch_one_private_ping_smoke(
    payloads: Sequence[PrivatePingPayloadRecord],
    *,
    webhook_url: str,
    webhook_identity: str,
    transport: Stage27_7bDiscordTransport,
    clock: Stage27_7bDispatchClock,
    live_mode_authority: str,
    operator_live_request: bool,
    smoke_dispatch_request: bool,
    dispatch_mode: str = DISPATCH_MODE_DRY_RUN,
    run_id: Optional[str] = None,
    session_id: Optional[str] = None,
) -> Stage27_7bDispatchResultRecord:
    """Dispatch a controlled one-ping private Discord smoke.

    Pure-shape orchestrator. Fail-closed gate order:

      1. Reject ``payloads`` whose length is not exactly 1
         (``REFUSED_MULTIPLE_PAYLOADS``).
      2. Pair-aware refusal (UNKNOWN / DISAGREE always refuse;
         USDC requires the ``RENDERED_OBSERVE_ONLY`` warning;
         SOL must be on the ``EXISTING_SOL_LANE``). Pair refusal
         applies in BOTH ``DRY_RUN`` and ``LIVE_SEND`` so the
         operator can see the same suppression verdict either way.
      3. Reject an unknown ``dispatch_mode`` token
         (``REFUSED_UNAUTHORIZED_MODE`` /
         ``UNKNOWN_DISPATCH_MODE``).
      4. ``DRY_RUN`` short-circuit -> ``DRY_RUN_NOT_SENT`` (no
         transport call).
      5. ``LIVE_SEND``: enforce all three live-auth factors --
         ``live_mode_authority`` must equal ``LIVE_ALLOWED``,
         ``operator_live_request`` must be ``True``,
         ``smoke_dispatch_request`` must be ``True``. Each missing
         factor returns the matching closed-set refusal.
      6. ``LIVE_SEND``: enforce non-empty ``webhook_identity`` and
         ``webhook_url`` (``REFUSED_MISSING_WEBHOOK``).
      7. All gates pass -> call ``send_one_private_ping(...)``.

    The dispatch NEVER stores ``webhook_url`` on the returned record
    and NEVER includes it in any error / log-style output.

    Arguments mirror the natural Stage 27.7b operator script:

      * ``payloads``                  -- a sequence of EXACTLY ONE
                                         Stage 27.5
                                         ``PrivatePingPayloadRecord``.
      * ``webhook_url``               -- raw operator webhook URL;
                                         not stored on the result.
      * ``webhook_identity``          -- safe-to-display webhook
                                         label.
      * ``transport``                 -- injected
                                         ``Stage27_7bDiscordTransport``;
                                         tests pass
                                         ``Stage27_7bFakeDiscordTransport``.
      * ``clock``                     -- injected
                                         ``Stage27_7bDispatchClock``.
      * ``live_mode_authority``       -- Stage 27.1 LIVE-mode
                                         authority token (mirrored).
      * ``operator_live_request``     -- second explicit operator
                                         cross-check factor.
      * ``smoke_dispatch_request``    -- third explicit smoke gating
                                         factor.
      * ``dispatch_mode``             -- ``DRY_RUN`` (default) or
                                         ``LIVE_SEND``.
      * ``run_id`` / ``session_id``   -- caller-supplied; ``None``
                                         when not attached.
    """
    safe_identity = _webhook_identity_or_missing(webhook_identity)
    sent_at_utc = clock.now_utc_iso()

    # Gate 1: payload count.
    if not isinstance(payloads, (list, tuple)):
        # A scalar caller mistake is treated as a multi-payload
        # refusal (defensive). The caller must pass a sequence
        # containing exactly one payload.
        return _build_refusal_result(
            dispatch_status=(
                DISPATCH_STATUS_REFUSED_MULTIPLE_PAYLOADS
            ),
            dispatch_reason=(
                DISPATCH_REASON_MULTIPLE_PAYLOADS_REFUSED
            ),
            dispatch_mode=dispatch_mode,
            webhook_identity=safe_identity,
            payload=None,
            run_id=run_id,
            session_id=session_id,
            sent_at_utc=sent_at_utc,
        )

    if len(payloads) == 0:
        return _build_refusal_result(
            dispatch_status=(
                DISPATCH_STATUS_REFUSED_MULTIPLE_PAYLOADS
            ),
            dispatch_reason=DISPATCH_REASON_NO_PAYLOAD_PROVIDED,
            dispatch_mode=dispatch_mode,
            webhook_identity=safe_identity,
            payload=None,
            run_id=run_id,
            session_id=session_id,
            sent_at_utc=sent_at_utc,
        )

    if len(payloads) > STAGE27_7B_MAX_PAYLOADS_PER_DISPATCH:
        return _build_refusal_result(
            dispatch_status=(
                DISPATCH_STATUS_REFUSED_MULTIPLE_PAYLOADS
            ),
            dispatch_reason=(
                DISPATCH_REASON_MULTIPLE_PAYLOADS_REFUSED
            ),
            dispatch_mode=dispatch_mode,
            webhook_identity=safe_identity,
            payload=None,
            run_id=run_id,
            session_id=session_id,
            sent_at_utc=sent_at_utc,
        )

    payload = payloads[0]
    if not isinstance(payload, PrivatePingPayloadRecord):
        return _build_refusal_result(
            dispatch_status=(
                DISPATCH_STATUS_REFUSED_MULTIPLE_PAYLOADS
            ),
            dispatch_reason=DISPATCH_REASON_NO_PAYLOAD_PROVIDED,
            dispatch_mode=dispatch_mode,
            webhook_identity=safe_identity,
            payload=None,
            run_id=run_id,
            session_id=session_id,
            sent_at_utc=sent_at_utc,
        )

    # Gate 2: pair-aware refusal (applies in both DRY_RUN and
    # LIVE_SEND modes).
    pair_refusal = _pair_refusal_for_payload(payload)
    if pair_refusal is not None:
        status, reason = pair_refusal
        return _build_refusal_result(
            dispatch_status=status,
            dispatch_reason=reason,
            dispatch_mode=dispatch_mode,
            webhook_identity=safe_identity,
            payload=payload,
            run_id=run_id,
            session_id=session_id,
            sent_at_utc=sent_at_utc,
        )

    # Gate 3: known dispatch_mode token.
    if dispatch_mode not in DISPATCH_MODE_VALUES:
        return _build_refusal_result(
            dispatch_status=(
                DISPATCH_STATUS_REFUSED_UNAUTHORIZED_MODE
            ),
            dispatch_reason=DISPATCH_REASON_UNKNOWN_DISPATCH_MODE,
            dispatch_mode=str(dispatch_mode),
            webhook_identity=safe_identity,
            payload=payload,
            run_id=run_id,
            session_id=session_id,
            sent_at_utc=sent_at_utc,
        )

    # Gate 4: DRY_RUN short-circuit.
    if dispatch_mode == DISPATCH_MODE_DRY_RUN:
        return _build_refusal_result(
            dispatch_status=DISPATCH_STATUS_DRY_RUN_NOT_SENT,
            dispatch_reason=DISPATCH_REASON_DRY_RUN_MODE,
            dispatch_mode=DISPATCH_MODE_DRY_RUN,
            webhook_identity=safe_identity,
            payload=payload,
            run_id=run_id,
            session_id=session_id,
            sent_at_utc=sent_at_utc,
        )

    # Gate 5: live-auth factors. All three must pass.
    if live_mode_authority != LIVE_MODE_AUTHORITY_LIVE_ALLOWED:
        return _build_refusal_result(
            dispatch_status=DISPATCH_STATUS_REFUSED_NOT_LIVE,
            dispatch_reason=(
                DISPATCH_REASON_LIVE_AUTHORITY_NOT_ALLOWED
            ),
            dispatch_mode=DISPATCH_MODE_LIVE_SEND,
            webhook_identity=safe_identity,
            payload=payload,
            run_id=run_id,
            session_id=session_id,
            sent_at_utc=sent_at_utc,
        )

    if not (operator_live_request is True):
        return _build_refusal_result(
            dispatch_status=(
                DISPATCH_STATUS_REFUSED_UNAUTHORIZED_MODE
            ),
            dispatch_reason=(
                DISPATCH_REASON_OPERATOR_LIVE_REQUEST_MISSING
            ),
            dispatch_mode=DISPATCH_MODE_LIVE_SEND,
            webhook_identity=safe_identity,
            payload=payload,
            run_id=run_id,
            session_id=session_id,
            sent_at_utc=sent_at_utc,
        )

    if not (smoke_dispatch_request is True):
        return _build_refusal_result(
            dispatch_status=(
                DISPATCH_STATUS_REFUSED_UNAUTHORIZED_MODE
            ),
            dispatch_reason=(
                DISPATCH_REASON_SMOKE_DISPATCH_REQUEST_MISSING
            ),
            dispatch_mode=DISPATCH_MODE_LIVE_SEND,
            webhook_identity=safe_identity,
            payload=payload,
            run_id=run_id,
            session_id=session_id,
            sent_at_utc=sent_at_utc,
        )

    # Gate 6: webhook identity + url shape.
    if (
        not isinstance(webhook_identity, str)
        or webhook_identity == ""
    ):
        return _build_refusal_result(
            dispatch_status=(
                DISPATCH_STATUS_REFUSED_MISSING_WEBHOOK
            ),
            dispatch_reason=(
                DISPATCH_REASON_WEBHOOK_IDENTITY_MISSING
            ),
            dispatch_mode=DISPATCH_MODE_LIVE_SEND,
            webhook_identity="<missing>",
            payload=payload,
            run_id=run_id,
            session_id=session_id,
            sent_at_utc=sent_at_utc,
        )

    if not isinstance(webhook_url, str) or webhook_url == "":
        return _build_refusal_result(
            dispatch_status=(
                DISPATCH_STATUS_REFUSED_MISSING_WEBHOOK
            ),
            dispatch_reason=DISPATCH_REASON_WEBHOOK_URL_MISSING,
            dispatch_mode=DISPATCH_MODE_LIVE_SEND,
            webhook_identity=safe_identity,
            payload=payload,
            run_id=run_id,
            session_id=session_id,
            sent_at_utc=sent_at_utc,
        )

    # Gate 7: every gate passed -> call the sender.
    return send_one_private_ping(
        payload,
        webhook_url=webhook_url,
        webhook_identity=safe_identity,
        transport=transport,
        clock=clock,
        run_id=run_id,
        session_id=session_id,
    )


__all__ = (
    "LIVE_MODE_AUTHORITY_LIVE_ALLOWED",
    "STAGE27_7B_MAX_PAYLOADS_PER_DISPATCH",
    "dispatch_one_private_ping_smoke",
)

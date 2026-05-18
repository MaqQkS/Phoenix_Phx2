"""Stage 21.3C private Discord transport boundary (offline-only).

This module ships the typed boundary between the Stage 21
dispatcher and a future real Discord webhook client. Stage
21.3C is offline-only: no live network behaviour, no real HTTP
client, no orchestrator, no first smoke ping. Those concerns
land in Stage 21.4 (runner / first private smoke ping) and
Stage 22 (retries / dedupe / raw archive / quarantine).

The transport:

  * accepts an injected client implementing
    ``DiscordWebhookClientProtocol`` whose ``post_webhook``
    method receives only the safe rendered body and a
    deterministic idempotency token -- never the raw webhook
    URL, never the SecretRef fingerprint, never any secret
    value;
  * gates ``send`` through four checks in a fixed order:

      1. ``assert_transport_dispatch_safety`` -- the existing
         Stage 21 transport-contract guard;
      2. ``evaluate_live_readiness`` -- the Stage 21.3A
         live-readiness gate composed over Stage 21.1
         ``Stage21Config`` plus the four 21.3A fields;
      3. ``webhook_ref.present`` -- the SecretRef presence flag
         for the operator-supplied webhook slot;
      4. ``OperatorAllowlist`` -- fail-closed empty / missing
         recipient refusal;

  * uses a locked closed-set rejection-reason vocabulary
    (``STAGE21_3C_REJECTION_REASONS``);
  * fails closed and silent on any client exception -- the
    raw client exception ``str`` / ``repr`` / ``args`` are
    NEVER surfaced into the ``TransportResult``;
  * NEVER retries. A future Stage 22 retry layer would sit
    BETWEEN the transport and the runner.

Per locked operator decision Q1 the transport does NOT
materialize the raw webhook URL anywhere. The URL is owned by
the injected real client, which the future Stage 21.4 runner
will construct from the SecretRef snapshot held in
Stage21Config. The transport stores only the SecretRef
presence/attestation metadata.

Per locked operator decision Q2 the transport surfaces a
single ``readiness_not_ready`` bucket for any readiness
failure. Specific readiness sub-reasons remain non-secret
tokens, but are not propagated into ``TransportResult`` --
keeping the transport result vocabulary narrow.

Per locked operator decision Q3 the idempotency token is a
deterministic sha256-derived hex string built from safe
non-secret payload fields only. The token carries no random
source, no clock, no webhook URL, no SecretRef fingerprint,
no raw secret value, and the recipient / body text appear
only via their sha256 hashes (never the raw strings).

Per locked operator decision Q4 there are NO live tests in
Stage 21.3C: no ``stage21_live`` marker, no env-gated real
send, no real HTTP client, no requests / httpx / aiohttp /
discord.py / discord / telegram integration. Stage 21.4 owns
the first real private smoke ping.

Module invariants:

  * does NOT import any network / RPC / messaging / HTTP /
    DB / scheduler / secrets-management library;
  * does NOT read ``os.environ`` / ``os.getenv``;
  * does NOT import Phoenix1, PHX2.stage17..20 runtime, any
    PHX2 runtime layer, ``fake_provider`` / ``fake_transport``
    / ``live_path_simulator`` / ``provider_adapter_helius``;
  * has NO retry, NO backoff, NO dedupe, NO archive, NO
    orchestrator / runner / scheduler behaviour;
  * has NO subscriber / public / paid routing;
  * carries NO URL literal in source.
"""

from __future__ import annotations

import hashlib
from typing import NamedTuple, Protocol

from PHX2.stage21.allowlist import OperatorAllowlist
from PHX2.stage21.live_secrets_boundary import (
    Stage21LiveReadinessConfig,
    evaluate_live_readiness,
)
from PHX2.stage21.secret_redaction import SecretRef
from PHX2.stage21.transport_contracts import (
    TransportPayload,
    TransportResult,
    assert_transport_dispatch_safety,
)


# ---------------------------------------------------------------------------
# Locked Stage 21.3C closed-set rejection reasons
# ---------------------------------------------------------------------------
#
# Each constant maps to exactly one refusal branch in
# ``DiscordPrivateTransport.send``. The closed set is locked by
# ``STAGE21_3C_REJECTION_REASONS`` and pinned in the Stage 21.3C
# boundary test so a future drift requires an explicit operator
# decision.


REJECTION_REASON_READINESS_NOT_READY: str = "readiness_not_ready"
REJECTION_REASON_RECIPIENT_NOT_IN_ALLOWLIST: str = (
    "recipient_not_in_allowlist"
)
REJECTION_REASON_DISPATCH_SAFETY_REJECTED: str = (
    "dispatch_safety_rejected"
)
REJECTION_REASON_WEBHOOK_NOT_PRESENT: str = "webhook_not_present"
REJECTION_REASON_CLIENT_POST_FAILED: str = "client_post_failed"
REJECTION_REASON_UPSTREAM_NON_2XX: str = "upstream_non_2xx"


STAGE21_3C_REJECTION_REASONS: tuple[str, ...] = (
    REJECTION_REASON_READINESS_NOT_READY,
    REJECTION_REASON_RECIPIENT_NOT_IN_ALLOWLIST,
    REJECTION_REASON_DISPATCH_SAFETY_REJECTED,
    REJECTION_REASON_WEBHOOK_NOT_PRESENT,
    REJECTION_REASON_CLIENT_POST_FAILED,
    REJECTION_REASON_UPSTREAM_NON_2XX,
)


# ---------------------------------------------------------------------------
# Idempotency token derivation constants
# ---------------------------------------------------------------------------
#
# Stage 21.3C derives the idempotency token deterministically
# from sha256 hashes of safe non-secret payload fields. The
# token has no random source, no clock, no webhook URL, no
# SecretRef fingerprint, and no raw secret value.


_IDEMPOTENCY_TOKEN_PREFIX: str = "phx2-stage21-3c-idempotency-v1"
_IDEMPOTENCY_TOKEN_HEX_LENGTH: int = 32


# ---------------------------------------------------------------------------
# Module-local error hierarchy
# ---------------------------------------------------------------------------
#
# Rooted at plain ``Exception`` (mirrors Stage 21.3A decoder Q3
# and Stage 21.3B adapter Q3 decisions). Used only at
# construction time for None-argument rejection.
# ``DiscordTransportClientError`` is the local exception type
# raised internally when the injected client raises during
# ``post_webhook``; it is caught locally and converted to a
# ``client_post_failed`` ``TransportResult`` -- never propagated
# to the caller.


class DiscordTransportError(Exception):
    """Base error for Stage 21.3C Discord private transport violations.

    Raised only at construction time when one of the four
    required collaborators (``client`` / ``readiness`` /
    ``webhook_ref`` / ``allowlist``) is ``None``. The
    ``send`` method does NOT raise on any normal refusal path;
    every refusal surfaces via ``TransportResult.rejection_reason``
    with a locked closed-set token.
    """


class DiscordTransportClientError(DiscordTransportError):
    """Internal sanitized-error type for an injected-client failure.

    The Stage 21.3C transport catches every ``Exception`` raised
    by the injected client during ``post_webhook`` and surfaces
    only a ``client_post_failed`` rejection. The raw client
    exception ``str`` / ``repr`` / ``args`` (which may carry the
    raw response body, URL, token, API key, or webhook URL) are
    never propagated. This type exists so a future Stage 21.4
    caller that wants to integrate the transport into a broader
    retry / observability layer can distinguish client failures
    from contract violations without recovering the raw
    exception.
    """


# ---------------------------------------------------------------------------
# Injected-client protocol
# ---------------------------------------------------------------------------


class DiscordPostOutcome(NamedTuple):
    """Outcome record returned by ``DiscordWebhookClientProtocol.post_webhook``.

    Fields:
      * ``accepted``            -- True iff the upstream returned
                                   a 2xx response. The transport
                                   surfaces ``upstream_non_2xx``
                                   on any False outcome.
      * ``status_class``        -- short non-secret bucket label
                                   such as ``"2xx"`` / ``"4xx"``
                                   / ``"5xx"``. Not propagated into
                                   ``TransportResult``; provided so
                                   the future Stage 21.4 runner can
                                   record the bucket in its own
                                   telemetry.
      * ``upstream_error_type`` -- short non-secret error-type
                                   label such as ``"timeout"`` /
                                   ``"rate_limit"`` / ``""``. Same
                                   handling as ``status_class``.

    The contract is that ``status_class`` / ``upstream_error_type``
    never carry secret material -- they are operator-typed bucket
    labels chosen from a small closed vocabulary.
    """

    accepted: bool
    status_class: str
    upstream_error_type: str


class DiscordWebhookClientProtocol(Protocol):
    """Duck-typed contract for the injected real webhook client.

    The transport calls exactly one method on the client. The
    client owns the raw webhook URL (constructed outside the
    transport from a SecretRef snapshot held in Stage21Config)
    and is responsible for the actual HTTP POST. The transport
    NEVER passes the webhook URL into ``post_webhook`` -- per
    locked operator decision Q1 the transport carries only the
    SecretRef presence/attestation metadata and never the raw
    URL.

    Stage 21.3C ships only this Protocol and the offline-only
    transport boundary. The future real client lands in Stage
    21.4 with the live runner; Stage 21.3C tests inject
    deterministic in-memory fakes that record every call.

    The method receives only:
      * ``body_text``         -- the rendered private-preview
                                 body text already carrying the
                                 locked marker tokens;
      * ``idempotency_token`` -- a deterministic non-secret
                                 token derived from sha256
                                 hashes of safe payload fields.
    """

    def post_webhook(
        self,
        *,
        body_text: str,
        idempotency_token: str,
    ) -> DiscordPostOutcome: ...


# ---------------------------------------------------------------------------
# Stage 21.3C private Discord transport
# ---------------------------------------------------------------------------


class DiscordPrivateTransport:
    """Stage 21.3C private Discord transport (boundary-only, offline).

    Construct with four keyword-only collaborators:

      * ``client``      -- injected ``DiscordWebhookClientProtocol``
                           implementation. Stage 21.3C tests inject
                           deterministic in-memory fakes; Stage
                           21.4 will inject a real HTTP client
                           constructed from the SecretRef snapshot.
      * ``readiness``   -- a ``Stage21LiveReadinessConfig`` snapshot
                           (the composition of Stage 21.1
                           ``Stage21Config`` plus the four 21.3A
                           live-readiness fields). The transport
                           evaluates readiness via
                           ``evaluate_live_readiness`` on EVERY
                           ``send`` and fails closed on any
                           ``ready=False`` outcome.
      * ``webhook_ref`` -- the ``SecretRef`` for the webhook URL
                           slot. The transport reads only
                           ``webhook_ref.present`` -- the raw URL
                           is never materialized inside the
                           transport.
      * ``allowlist``   -- the ``OperatorAllowlist``. The transport
                           refuses any send when the allowlist is
                           fail-closed (empty) or when the
                           recipient is not in the allowlist.

    Construction rejects ``None`` for any of the four with
    ``DiscordTransportError``.

    ``send`` is the only public method. It satisfies the
    ``Stage21Transport`` Protocol and returns a ``TransportResult``
    carrying one of the locked ``STAGE21_3C_REJECTION_REASONS``
    tokens on refusal. ``send`` does NOT raise on any normal
    refusal path.

    ``__repr__`` echoes ONLY the transport class name and the
    client's TYPE name. It does NOT echo:
      * the webhook URL or its SecretRef fingerprint;
      * the readiness config fields;
      * the allowlist recipients;
      * the client's ``repr``;
      * any secret value.

    The transport is offline-only in Stage 21.3C. It does NOT
    retry, NOT deduplicate, NOT archive, NOT persist, NOT read
    the environment, and NOT import any network / messaging /
    RPC library. Those concerns belong to Stage 21.4 (runner /
    first smoke ping) and Stage 22 (retries / dedupe / raw
    archive / quarantine).
    """

    def __init__(
        self,
        *,
        client: DiscordWebhookClientProtocol,
        readiness: Stage21LiveReadinessConfig,
        webhook_ref: SecretRef,
        allowlist: OperatorAllowlist,
    ) -> None:
        if client is None:
            raise DiscordTransportError(
                "DiscordPrivateTransport requires a non-None client"
            )
        if readiness is None:
            raise DiscordTransportError(
                "DiscordPrivateTransport requires a non-None readiness"
            )
        if webhook_ref is None:
            raise DiscordTransportError(
                "DiscordPrivateTransport requires a non-None webhook_ref"
            )
        if allowlist is None:
            raise DiscordTransportError(
                "DiscordPrivateTransport requires a non-None allowlist"
            )
        self._client: DiscordWebhookClientProtocol = client
        self._readiness: Stage21LiveReadinessConfig = readiness
        self._webhook_ref: SecretRef = webhook_ref
        self._allowlist: OperatorAllowlist = allowlist

    def __repr__(self) -> str:
        return (
            "DiscordPrivateTransport(client_type="
            f"{type(self._client).__name__!r})"
        )

    def send(self, payload: TransportPayload) -> TransportResult:
        """Send (or refuse) one private-preview payload.

        Returns a ``TransportResult`` with ``dispatched=True``
        ONLY when every Stage 21.3C gate passes AND the injected
        client reports the upstream accepted the post. Otherwise
        returns ``dispatched=False`` with one of the locked
        ``STAGE21_3C_REJECTION_REASONS`` tokens.

        The send sequence:

          1. ``assert_transport_dispatch_safety`` -- any rejection
             here surfaces as ``dispatch_safety_rejected``. Per
             locked operator decision Q2 the specific sub-reason
             from the helper is NOT propagated; the transport
             surfaces a single bucket so the result vocabulary
             stays narrow.
          2. ``evaluate_live_readiness`` -- any ``ready=False``
             surfaces as ``readiness_not_ready``. Same Q2 reasoning.
          3. ``webhook_ref.present`` -- a False (empty SecretRef)
             surfaces as ``webhook_not_present``.
          4. allowlist -- fail-closed or missing-recipient
             surfaces as ``recipient_not_in_allowlist``.
          5. derive the deterministic idempotency token (sha256
             of safe non-secret fields only -- never the raw
             recipient / body text / webhook URL / fingerprint).
          6. invoke ``self._client.post_webhook(body_text=...,
             idempotency_token=...)``. The transport does NOT
             pass the webhook URL into the client method.
          7. any client exception -> ``client_post_failed``. The
             raw exception ``str`` / ``repr`` / ``args`` are
             NEVER surfaced. The transport does NOT retry.
          8. ``outcome.accepted is False`` ->
             ``upstream_non_2xx``. The response body / raw status
             are NEVER surfaced.
          9. accepted -> ``dispatched=True`` with the empty
             rejection_reason.
        """
        allowed, _ = assert_transport_dispatch_safety(payload)
        if not allowed:
            return TransportResult(
                dispatched=False,
                rejection_reason=(
                    REJECTION_REASON_DISPATCH_SAFETY_REJECTED
                ),
                recipient=payload.recipient,
            )

        readiness_result = evaluate_live_readiness(self._readiness)
        if not readiness_result.ready:
            return TransportResult(
                dispatched=False,
                rejection_reason=REJECTION_REASON_READINESS_NOT_READY,
                recipient=payload.recipient,
            )

        if not self._webhook_ref.present:
            return TransportResult(
                dispatched=False,
                rejection_reason=REJECTION_REASON_WEBHOOK_NOT_PRESENT,
                recipient=payload.recipient,
            )

        if (
            self._allowlist.fail_closed
            or not self._allowlist.contains(payload.recipient)
        ):
            return TransportResult(
                dispatched=False,
                rejection_reason=(
                    REJECTION_REASON_RECIPIENT_NOT_IN_ALLOWLIST
                ),
                recipient=payload.recipient,
            )

        idempotency_token = _derive_idempotency_token(payload)

        try:
            outcome = self._client.post_webhook(
                body_text=payload.body_text,
                idempotency_token=idempotency_token,
            )
        except Exception:
            # Per locked operator decision the transport NEVER
            # propagates the raw client exception. The raw
            # ``str`` / ``repr`` / ``args`` may carry the
            # response body / URL / token / secret -- we discard
            # all of it and surface only the closed-set
            # rejection token.
            return TransportResult(
                dispatched=False,
                rejection_reason=REJECTION_REASON_CLIENT_POST_FAILED,
                recipient=payload.recipient,
            )

        if not outcome.accepted:
            # Stage 21.3C does NOT retry. A future Stage 22
            # retry layer would sit between the transport and
            # the runner; the transport itself is single-shot.
            return TransportResult(
                dispatched=False,
                rejection_reason=REJECTION_REASON_UPSTREAM_NON_2XX,
                recipient=payload.recipient,
            )

        return TransportResult(
            dispatched=True,
            rejection_reason="",
            recipient=payload.recipient,
        )


# ---------------------------------------------------------------------------
# Deterministic idempotency token derivation
# ---------------------------------------------------------------------------


def _derive_idempotency_token(payload: TransportPayload) -> str:
    """Build a deterministic, non-secret idempotency token.

    The token is derived from sha256 hashes of safe non-secret
    payload fields only:

      * the recipient (folded in as its sha256 digest -- never
        as the raw string);
      * the body text (folded in as its sha256 digest -- never
        as the raw string);
      * the locked private-preview marker presence flag.

    The token uses NO random source, NO clock, NO webhook URL,
    NO SecretRef fingerprint, and NO raw secret value. Two
    transports given the SAME payload produce the SAME token;
    any difference in recipient / body / marker yields a
    different token.

    The output is a 32-char lowercase hex prefix of a sha256
    digest. The prefix length is operator-typed; collisions
    over a single private-preview run are negligible.
    """
    recipient_digest = hashlib.sha256(
        payload.recipient.encode("utf-8")
    ).hexdigest()
    body_digest = hashlib.sha256(
        payload.body_text.encode("utf-8")
    ).hexdigest()
    marker_flag = (
        "1" if payload.private_preview_marker_present else "0"
    )
    material = (
        f"{_IDEMPOTENCY_TOKEN_PREFIX}"
        f"|recipient={recipient_digest}"
        f"|body={body_digest}"
        f"|marker={marker_flag}"
    )
    return hashlib.sha256(
        material.encode("utf-8")
    ).hexdigest()[:_IDEMPOTENCY_TOKEN_HEX_LENGTH]


__all__ = [
    "DiscordPostOutcome",
    "DiscordPrivateTransport",
    "DiscordTransportClientError",
    "DiscordTransportError",
    "DiscordWebhookClientProtocol",
    "REJECTION_REASON_CLIENT_POST_FAILED",
    "REJECTION_REASON_DISPATCH_SAFETY_REJECTED",
    "REJECTION_REASON_READINESS_NOT_READY",
    "REJECTION_REASON_RECIPIENT_NOT_IN_ALLOWLIST",
    "REJECTION_REASON_UPSTREAM_NON_2XX",
    "REJECTION_REASON_WEBHOOK_NOT_PRESENT",
    "STAGE21_3C_REJECTION_REASONS",
]

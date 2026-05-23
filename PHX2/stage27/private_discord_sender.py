"""Stage 27.7b private operator-only Discord sender boundary.

Stage 27.7b ships the private operator-only Discord sender. The
sender:

  * accepts an injected webhook URL or an injected fake transport,
  * sends exactly ONE already-rendered Stage 27.5 private ping
    payload per call,
  * supports a fake transport in tests (the default test path uses
    ``Stage27_7bFakeDiscordTransport``),
  * NEVER reads the process environment directly,
  * NEVER exposes the webhook URL in ``repr()`` / ``str()`` / error
    strings / log-style output,
  * returns a typed Stage 27.7b dispatch result record,
  * preserves the upstream Stage 27.5 provenance IDs on the result.

The sender does NOT:

  * implement channel / user / subscriber routing,
  * implement paid tier routing,
  * implement Telegram / X-social / public routing,
  * persist any state across dispatches,
  * batch multiple payloads (each call is exactly one payload),
  * decide trading verdicts,
  * enforce Stage 26 candidate policies.

The real HTTP transport is intentionally isolated in
``Stage27_7bRealHttpDiscordTransport``. Stage 27.7b tests never
import / instantiate / call that transport; the default test path
uses ``Stage27_7bFakeDiscordTransport``. The Stage 27.7b boundary
tests assert no other Stage 27.7b module imports a network library.

This module imports only stdlib (``typing``) plus Stage 27.5 / 27.7b
production modules. It does NOT import Stage 21-26 production code,
does NOT import Stage 27.1 production code, does NOT import any
network / RPC / messaging / DB / scheduler / secrets-management
library at module scope, does NOT read the process environment,
does NOT define a CLI surface, and contains no top-level I/O.
"""

from __future__ import annotations

from typing import NamedTuple, Optional, Protocol

from PHX2.stage27.private_discord_models import (
    DISPATCH_MODE_DRY_RUN,
    DISPATCH_MODE_LIVE_SEND,
    DISPATCH_MODE_VALUES,
    DISPATCH_REASON_LIVE_SEND_OK,
    DISPATCH_REASON_TRANSPORT_EXCEPTION,
    DISPATCH_REASON_TRANSPORT_NON_SUCCESS,
    DISPATCH_REASON_WEBHOOK_IDENTITY_MISSING,
    DISPATCH_REASON_WEBHOOK_IDENTITY_UNSAFE,
    DISPATCH_REASON_WEBHOOK_URL_MISSING,
    DISPATCH_STATUS_REFUSED_MISSING_WEBHOOK,
    DISPATCH_STATUS_SENT,
    DISPATCH_STATUS_TRANSPORT_ERROR,
    REDACTION_STATUS_REDACTED,
    STAGE27_7B_DISPATCH_RESULT_SCHEMA_VERSION,
    Stage27_7bDispatchResultRecord,
    WEBHOOK_IDENTITY_REDACTED_UNSAFE,
    is_unsafe_webhook_identity,
)
from PHX2.stage27.private_ping_models import (
    PrivatePingPayloadRecord,
)


# ---------------------------------------------------------------------------
# Stage 27.7b dispatch clock protocol
# ---------------------------------------------------------------------------


class Stage27_7bDispatchClock(Protocol):
    """Minimal clock surface used by the Stage 27.7b sender.

    Implementations must return an ISO-8601 UTC timestamp string.
    Stage 27.7b keeps the clock interface deliberately tiny so tests
    can inject a ``FrozenStage27_7bDispatchClock``.
    """

    def now_utc_iso(self) -> str:
        ...


class FrozenStage27_7bDispatchClock(NamedTuple):
    """Deterministic ``Stage27_7bDispatchClock`` for tests.

    Construct with an explicit ISO-8601 UTC string; every
    ``now_utc_iso()`` call returns that exact value.
    """

    frozen_iso: str

    def now_utc_iso(self) -> str:
        return self.frozen_iso


# ---------------------------------------------------------------------------
# Transport protocol + immutable transport result
# ---------------------------------------------------------------------------


class Stage27_7bTransportResult(NamedTuple):
    """Immutable result returned by a Stage 27.7b Discord transport.

    Fields:

      * ``status_code``         -- numeric transport status. For the
                                   fake transport this is whatever
                                   the test fixture configured (e.g.
                                   ``200`` for happy path, ``500`` for
                                   simulated failure).
      * ``ok``                  -- ``True`` iff the transport
                                   considered the call successful.
                                   The fake transport sets this based
                                   on its configured status code; the
                                   real transport sets it based on
                                   the HTTP status class.
      * ``transport_error_kind`` -- short closed-set token describing
                                    a transport-side failure when
                                    ``ok`` is ``False`` (e.g.
                                    ``"NON_SUCCESS_STATUS"``);
                                    ``None`` when ``ok`` is ``True``.

    The record carries NO raw webhook URL, NO request body, NO
    response body, NO header value -- only the small closed surface
    above.
    """

    status_code: Optional[int]
    ok: bool
    transport_error_kind: Optional[str]


class Stage27_7bDiscordTransport(Protocol):
    """Minimal Stage 27.7b Discord transport surface.

    A transport implements exactly one method:
    ``send_one_payload(webhook_url, body_text) -> Stage27_7bTransportResult``.

    The transport NEVER exposes the webhook URL it was handed back
    on its result; the URL is the property of the caller. The
    transport is allowed to raise ``Stage27_7bTransportError`` on
    catastrophic failures; the Stage 27.7b sender translates those
    into a typed ``TRANSPORT_ERROR`` dispatch result without ever
    propagating the raw URL into the error message.
    """

    def send_one_payload(
        self,
        webhook_url: str,
        body_text: str,
    ) -> Stage27_7bTransportResult:
        ...


class Stage27_7bTransportError(Exception):
    """Raised by a Stage 27.7b transport on a catastrophic failure.

    Stage 27.7b transports must NEVER include the raw webhook URL
    in the error message. Carries only:

      * ``kind``               -- short closed-set token describing
                                  the failure (e.g.
                                  ``"NETWORK_ERROR"``).
      * ``status_code``        -- optional numeric status code if the
                                  failure was a structured non-success
                                  response.
    """

    def __init__(
        self,
        kind: str,
        *,
        status_code: Optional[int] = None,
    ) -> None:
        self.kind: str = kind
        self.status_code: Optional[int] = status_code
        msg = f"Stage 27.7b transport error: kind={kind!r}"
        if status_code is not None:
            msg += f" status_code={status_code}"
        super().__init__(msg)


# ---------------------------------------------------------------------------
# Fake transport (default test path)
# ---------------------------------------------------------------------------


class _FakeCallRecord(NamedTuple):
    """Per-call record kept by ``Stage27_7bFakeDiscordTransport``.

    Tests inspect this record to assert the sender passed the
    expected webhook URL and body text. The record is kept in the
    fake transport, NOT on the Stage 27.7b dispatch result. The
    dispatch result still never carries the raw URL.
    """

    webhook_url: str
    body_text: str


class Stage27_7bFakeDiscordTransport:
    """Deterministic fake Stage 27.7b Discord transport.

    Records each ``send_one_payload(...)`` call so tests can assert
    the expected arguments were passed. The default behaviour is a
    successful ``200`` response; tests can pass
    ``configured_status_code=500`` (or any other non-200) to simulate
    transport failure, and ``raise_exception_kind`` to simulate a
    transport-level exception.

    The fake transport NEVER opens a network connection, NEVER reads
    the process environment, and NEVER imports a network library.
    """

    def __init__(
        self,
        *,
        configured_status_code: int = 200,
        raise_exception_kind: Optional[str] = None,
    ) -> None:
        self._configured_status_code: int = configured_status_code
        self._raise_exception_kind: Optional[str] = (
            raise_exception_kind
        )
        self._calls: list[_FakeCallRecord] = []

    @property
    def calls(self) -> tuple[_FakeCallRecord, ...]:
        """Return the recorded send calls in invocation order."""
        return tuple(self._calls)

    @property
    def call_count(self) -> int:
        return len(self._calls)

    def send_one_payload(
        self,
        webhook_url: str,
        body_text: str,
    ) -> Stage27_7bTransportResult:
        # Record the call FIRST so tests can inspect even when the
        # transport then raises.
        self._calls.append(
            _FakeCallRecord(
                webhook_url=webhook_url,
                body_text=body_text,
            )
        )
        if self._raise_exception_kind is not None:
            raise Stage27_7bTransportError(
                kind=self._raise_exception_kind
            )
        if self._configured_status_code != 200:
            return Stage27_7bTransportResult(
                status_code=self._configured_status_code,
                ok=False,
                transport_error_kind="NON_SUCCESS_STATUS",
            )
        return Stage27_7bTransportResult(
            status_code=self._configured_status_code,
            ok=True,
            transport_error_kind=None,
        )


# ---------------------------------------------------------------------------
# Real HTTP transport surface (isolated; not used in tests)
# ---------------------------------------------------------------------------


class Stage27_7bRealHttpDiscordTransport:
    """Real HTTP Stage 27.7b Discord transport surface.

    This class is the ISOLATED real-network transport surface. Stage
    27.7b tests never instantiate or call it. The body intentionally
    raises ``NotImplementedError`` at call time so a test or
    misconfigured operator path that accidentally lands here gets a
    clean, redacted error rather than a silent live call.

    A real operator-driven smoke is expected to either:

      * inject an alternative production transport implementation
        that the operator audited, or
      * subclass / replace this transport's
        ``send_one_payload`` method on a one-off basis.

    The class itself does NOT import ``requests`` / ``httpx`` /
    ``aiohttp`` / ``urllib3`` -- Stage 27.7b production source MUST
    NOT import a network library. The actual HTTP call must be
    injected from outside the Stage 27 tree at the time of an
    explicitly authorized live smoke.
    """

    def send_one_payload(
        self,
        webhook_url: str,
        body_text: str,
    ) -> Stage27_7bTransportResult:
        raise NotImplementedError(
            "Stage27_7bRealHttpDiscordTransport must be replaced "
            "with an operator-audited implementation before any "
            "live smoke; the Stage 27.7b production source does "
            "not import a network library."
        )


# ---------------------------------------------------------------------------
# Sender error type
# ---------------------------------------------------------------------------


class Stage27_7bSenderArgumentError(Exception):
    """Raised by the Stage 27.7b sender on an invalid call shape.

    Stage 27.7b argument errors NEVER carry the raw webhook URL. The
    error message references only:

      * the argument NAME that failed validation,
      * a short closed-set reason token,
      * a length-style diagnostic when useful.

    This error is raised for argument-shape problems the dispatch
    layer would normally translate to typed refusals (e.g. a
    non-string ``webhook_url``). Tests assert the message has no URL
    substring.
    """

    def __init__(
        self,
        argument_name: str,
        reason: str,
        *,
        value_length: Optional[int] = None,
    ) -> None:
        self.argument_name: str = argument_name
        self.reason: str = reason
        self.value_length: Optional[int] = value_length
        msg = (
            f"Stage 27.7b sender argument error: "
            f"name={argument_name!r} reason={reason!r}"
        )
        if value_length is not None:
            msg += f" length={value_length}"
        super().__init__(msg)


# ---------------------------------------------------------------------------
# Sender helper: redacted dispatch result builders
# ---------------------------------------------------------------------------


def _no_url_substring(message: object) -> bool:
    """Return ``True`` iff ``message`` is not a string. Pure helper.

    Stage 27.7b never substring-scans an error message for the
    webhook URL at runtime; the discipline is enforced by NEVER
    storing the URL on a record / error in the first place. This
    helper is here so module callers can do a defensive belt-and-
    braces check (``assert _no_url_substring(str(exc))``) if they
    want.
    """
    return not isinstance(message, str)


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
    no_payload_sentinel: str,
) -> Stage27_7bDispatchResultRecord:
    """Construct a Stage 27.7b refusal / not-sent dispatch result.

    The transport_status_code is always ``None`` on refusal. The
    webhook_identity is stamped on the result (it's the safe-to-
    display label, NOT the URL). The payload fields are echoed when
    a payload exists; otherwise the ``<no_payload>`` sentinel is
    stamped.
    """
    if payload is None:
        ping_id = no_payload_sentinel
        pair_quote_asset = no_payload_sentinel
        render_status = no_payload_sentinel
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
# Public sender entrypoint
# ---------------------------------------------------------------------------


def send_one_private_ping(
    payload: PrivatePingPayloadRecord,
    *,
    webhook_url: str,
    webhook_identity: str,
    transport: Stage27_7bDiscordTransport,
    clock: Stage27_7bDispatchClock,
    run_id: Optional[str] = None,
    session_id: Optional[str] = None,
) -> Stage27_7bDispatchResultRecord:
    """Send exactly ONE rendered Stage 27.5 private ping payload.

    Pure-shape function: validates argument shape, calls the injected
    transport with the injected webhook URL and the payload's
    deterministic plain-text body, translates the transport result
    into a typed Stage 27.7b dispatch result record.

    Stage 27.7b sender invariants:

      * accepts ONE ``payload`` (a ``PrivatePingPayloadRecord``);
        batch / multi-payload dispatch lives in the Stage 27.7b
        dispatch layer (and is refused there with
        ``REFUSED_MULTIPLE_PAYLOADS``),
      * NEVER reads ``os.environ``,
      * NEVER opens a network connection itself; the transport is
        injected,
      * NEVER stores ``webhook_url`` on the returned record,
      * NEVER includes ``webhook_url`` in any raised exception
        message,
      * stamps ``sent_at_utc`` from the injected clock,
      * returns a typed Stage 27.7b dispatch result record carrying
        only safe-to-display fields.

    Arguments:

      * ``payload``           -- a Stage 27.5
                                 ``PrivatePingPayloadRecord``. Must
                                 be the exact NamedTuple type.
      * ``webhook_url``       -- the raw webhook URL string. Not
                                 stored on any returned record. Not
                                 echoed in any error message. Must be
                                 a non-empty string.
      * ``webhook_identity``  -- safe-to-display webhook identity
                                 label (e.g.
                                 ``"PRIVATE_OPERATOR_WEBHOOK"``).
                                 Must be a non-empty string.
      * ``transport``         -- a Stage 27.7b transport satisfying
                                 ``Stage27_7bDiscordTransport``. Test
                                 fixtures pass
                                 ``Stage27_7bFakeDiscordTransport``.
      * ``clock``             -- a Stage 27.7b dispatch clock
                                 satisfying ``Stage27_7bDispatchClock``.
      * ``run_id`` /
        ``session_id``        -- caller-supplied; ``None`` when not
                                 attached.

    Returns a ``Stage27_7bDispatchResultRecord``.
    """
    if not isinstance(payload, PrivatePingPayloadRecord):
        raise Stage27_7bSenderArgumentError(
            argument_name="payload",
            reason="NOT_PRIVATE_PING_PAYLOAD_RECORD",
        )
    if not isinstance(webhook_identity, str) or webhook_identity == "":
        # Construct a typed refusal result rather than raising; the
        # dispatch layer will normally pre-validate this. The sender
        # mirrors the typed refusal so a direct caller still gets a
        # clean result.
        return _build_refusal_result(
            dispatch_status=DISPATCH_STATUS_REFUSED_MISSING_WEBHOOK,
            dispatch_reason=DISPATCH_REASON_WEBHOOK_IDENTITY_MISSING,
            dispatch_mode=DISPATCH_MODE_LIVE_SEND,
            webhook_identity="<missing>",
            payload=payload,
            run_id=run_id,
            session_id=session_id,
            sent_at_utc=clock.now_utc_iso(),
            no_payload_sentinel="<no_payload>",
        )
    if is_unsafe_webhook_identity(webhook_identity):
        # Stage 27.7b remediation: defense-in-depth. The dispatch
        # layer normally pre-validates this, but a direct sender
        # caller (e.g. a test that bypasses the dispatch) must also
        # get a clean refusal rather than a leaked URL on the
        # result. The caller-supplied identity is NEVER echoed; the
        # locked redacted placeholder is stamped instead.
        return _build_refusal_result(
            dispatch_status=DISPATCH_STATUS_REFUSED_MISSING_WEBHOOK,
            dispatch_reason=DISPATCH_REASON_WEBHOOK_IDENTITY_UNSAFE,
            dispatch_mode=DISPATCH_MODE_LIVE_SEND,
            webhook_identity=WEBHOOK_IDENTITY_REDACTED_UNSAFE,
            payload=payload,
            run_id=run_id,
            session_id=session_id,
            sent_at_utc=clock.now_utc_iso(),
            no_payload_sentinel="<no_payload>",
        )
    if not isinstance(webhook_url, str) or webhook_url == "":
        return _build_refusal_result(
            dispatch_status=DISPATCH_STATUS_REFUSED_MISSING_WEBHOOK,
            dispatch_reason=DISPATCH_REASON_WEBHOOK_URL_MISSING,
            dispatch_mode=DISPATCH_MODE_LIVE_SEND,
            webhook_identity=webhook_identity,
            payload=payload,
            run_id=run_id,
            session_id=session_id,
            sent_at_utc=clock.now_utc_iso(),
            no_payload_sentinel="<no_payload>",
        )

    sent_at_utc = clock.now_utc_iso()

    try:
        transport_result = transport.send_one_payload(
            webhook_url, payload.body_text
        )
    except Stage27_7bTransportError as exc:
        # Stage 27.7b transport errors NEVER carry the URL; the
        # dispatch result mirrors only the closed-set kind via the
        # closed-set ``TRANSPORT_EXCEPTION`` reason code.
        return Stage27_7bDispatchResultRecord(
            dispatch_status=DISPATCH_STATUS_TRANSPORT_ERROR,
            dispatch_reason=DISPATCH_REASON_TRANSPORT_EXCEPTION,
            dispatch_mode=DISPATCH_MODE_LIVE_SEND,
            webhook_identity=webhook_identity,
            ping_id=payload.ping_id,
            run_id=run_id,
            session_id=session_id,
            sent_at_utc=sent_at_utc,
            transport_status_code=exc.status_code,
            redaction_status=REDACTION_STATUS_REDACTED,
            schema_version=(
                STAGE27_7B_DISPATCH_RESULT_SCHEMA_VERSION
            ),
            pair_quote_asset=payload.quote_asset,
            render_status=payload.render_status,
        )

    if not transport_result.ok:
        return Stage27_7bDispatchResultRecord(
            dispatch_status=DISPATCH_STATUS_TRANSPORT_ERROR,
            dispatch_reason=DISPATCH_REASON_TRANSPORT_NON_SUCCESS,
            dispatch_mode=DISPATCH_MODE_LIVE_SEND,
            webhook_identity=webhook_identity,
            ping_id=payload.ping_id,
            run_id=run_id,
            session_id=session_id,
            sent_at_utc=sent_at_utc,
            transport_status_code=transport_result.status_code,
            redaction_status=REDACTION_STATUS_REDACTED,
            schema_version=(
                STAGE27_7B_DISPATCH_RESULT_SCHEMA_VERSION
            ),
            pair_quote_asset=payload.quote_asset,
            render_status=payload.render_status,
        )

    return Stage27_7bDispatchResultRecord(
        dispatch_status=DISPATCH_STATUS_SENT,
        dispatch_reason=DISPATCH_REASON_LIVE_SEND_OK,
        dispatch_mode=DISPATCH_MODE_LIVE_SEND,
        webhook_identity=webhook_identity,
        ping_id=payload.ping_id,
        run_id=run_id,
        session_id=session_id,
        sent_at_utc=sent_at_utc,
        transport_status_code=transport_result.status_code,
        redaction_status=REDACTION_STATUS_REDACTED,
        schema_version=STAGE27_7B_DISPATCH_RESULT_SCHEMA_VERSION,
        pair_quote_asset=payload.quote_asset,
        render_status=payload.render_status,
    )


__all__ = (
    "Stage27_7bDispatchClock",
    "FrozenStage27_7bDispatchClock",
    "Stage27_7bTransportResult",
    "Stage27_7bDiscordTransport",
    "Stage27_7bTransportError",
    "Stage27_7bFakeDiscordTransport",
    "Stage27_7bRealHttpDiscordTransport",
    "Stage27_7bSenderArgumentError",
    "send_one_private_ping",
    "DISPATCH_MODE_DRY_RUN",
    "DISPATCH_MODE_LIVE_SEND",
    "DISPATCH_MODE_VALUES",
)

"""Stage 30.11.5 private transport adapter boundary.

The pure, offline TRANSPORT ADAPTER that conforms to the committed Stage 30.11.3
private sink transport protocol -- ``Callable[[Stage30_11PrivateSinkRequest],
Stage30_11PrivateSinkResult]`` -- by rendering a SAFE private operator payload
from the sink request and handing it to an INJECTED low-level transport client.
It is the real-transport BOUNDARY the Stage 30.11.3 private sink injects as its
``transport``:

    a committed Stage 30.11.3 ``Stage30_11PrivateSinkRequest`` (the
    ``PASS_TO_DISPATCH`` candidate the runtime seam reached)
      -> validate ALL required request fields (fail closed on a wrong type /
         blank id / blank body / blank timestamp / wrong source stage /
         wrong-typed optional; the transport client is NOT called)
      -> render a Stage 30.11.5 ``Stage30_11_5PrivateOperatorPayload`` (a SAFE
         operator body + ids + provenance; NO destination of its own)
      -> hand the payload to the INJECTED transport client (a FAKE in this slice)
         inside a fail-closed guard (a client exception is caught and swallowed,
         never escaping)
      -> map the client's verdict into a committed Stage 30.11.3
         ``Stage30_11PrivateSinkResult``: an ACCEPT requires the client to confirm
         the would-deliver (the closed accept status AND the same candidate id /
         token mint); anything else is a clean transport-failed

This adapter is the seam the prior controlled live ceremony lacked between the
committed Stage 30.11.3 private sink and the REAL private operator transport:
the real audited transport / Discord client is the thing that would perform a
real send, and it is ALWAYS INJECTED -- this module defines none, imports none,
references no transport destination, and reads no env. The real private compact
dispatch / Discord send is a SEPARATE, explicitly operator-authorized step Stage
30.11.5 does not build; in THIS slice the injected client is ALWAYS an in-memory
recording FAKE, and a client accept is a RECORDED would-deliver, NEVER a real
send.

The adapter NEVER opens a network connection, NEVER reads the process
environment (it NEVER reads ``PHX2_PRIVATE_DISCORD_WEBHOOK_URL`` or any other
env var), NEVER reads a wall clock (``created_at_utc`` is caller-injected),
NEVER sends Discord, NEVER reserves a real dispatch / performs a real send,
NEVER writes a file, runs NO daemon / background loop, and edits NO Stage 28 /
Stage 29 / Stage 30.3 / Stage 30.4 production file. It composes the committed
Stage 30.11.3 request / result types (the permitted Stage 30.11 scope expansion)
plus an injected fake transport client; nothing more.

Discipline:

  * Stdlib only (``typing``).
  * Imports only the Stage 30.11.5 models sibling + the committed Stage 30.11.3
    private-sink-models sibling (for the request / result types + the closed-set
    sink vocabulary the adapter normalizes into). No other PHX2 module; no Stage
    21-29 / Stage 30.3 / Stage 30.4 orchestrator / Stage 28 suppression / live
    runner / provider / real transport / Discord import.
  * No ``os.environ`` / ``os.getenv`` access; no env read.
  * No network, no HTTP, no gRPC, no WebSocket, no socket.
  * No database / SQLite, no zstd / compression, no default storage root.
  * No live provider, transport-destination, or request-metadata reference.
  * No PHX1 import. No ``time`` / ``datetime`` import; timestamps are
    caller-injected.
"""

from __future__ import annotations

from typing import Callable

from PHX2.stage30.stage30_11_3_private_sink_models import (
    PRIVATE_SINK_DECISION_ACCEPTED,
    PRIVATE_SINK_DECISION_REJECTED_INVALID_INPUT,
    PRIVATE_SINK_DECISION_TRANSPORT_FAILED,
    PRIVATE_SINK_REASON_FAKE_TRANSPORT_REJECTED,
    PRIVATE_SINK_REASON_INVALID_SINK_INPUT,
    PRIVATE_SINK_REASON_WOULD_SEND_PRIVATE_OPERATOR_MESSAGE,
    STAGE30_11_3_SOURCE_STAGE,
    Stage30_11PrivateSinkRequest,
    Stage30_11PrivateSinkResult,
    is_nonblank_str,
)
from PHX2.stage30.stage30_11_5_live_wiring_models import (
    STAGE30_11_5_SOURCE_STAGE,
    STAGE30_11_5_TRANSPORT_ACCEPT_STATUS,
    Stage30_11_5PrivateOperatorPayload,
    Stage30_11_5TransportClientResult,
)


# The injected low-level transport client: a callable that, given a rendered
# private operator payload, returns a ``Stage30_11_5TransportClientResult``
# verdict. In this slice it is ALWAYS an in-memory recording FAKE (the real
# audited private transport is a SEPARATE, operator-authorized step Stage 30.11.5
# does not build). The adapter calls it from a SINGLE call site, ONLY for a
# well-shaped request.
Stage30_11_5PrivateTransportClient = Callable[
    [Stage30_11_5PrivateOperatorPayload], Stage30_11_5TransportClientResult
]


# The adapter the factory returns: a callable conforming to the committed Stage
# 30.11.3 transport protocol (request -> result). This is the type the committed
# Stage 30.11.3 private sink injects as its ``transport``.
Stage30_11_5PrivateTransport = Callable[
    [Stage30_11PrivateSinkRequest], Stage30_11PrivateSinkResult
]


# ---------------------------------------------------------------------------
# Module-local exception (caller-shape failure)
# ---------------------------------------------------------------------------


class Stage30_11_5PrivateTransportAdapterError(Exception):
    """Closed-set Stage 30.11.5 private transport adapter error.

    Raised ONLY for a caller-shape failure a pure builder cannot run with -- a
    ``request`` that is not a ``Stage30_11PrivateSinkRequest`` handed directly to
    ``build_private_operator_payload`` (there is no request to render). The
    adapter callable the factory returns NEVER raises for a malformed request: it
    fails closed to a ``PRIVATE_SINK_REJECTED_INVALID_INPUT`` result BEFORE
    touching the transport client. Carries only a closed-set reason token; never a
    raw payload or any secret value.
    """

    def __init__(self, reason: str) -> None:
        self.reason: str = reason
        super().__init__(
            f"Stage 30.11.5 private transport adapter error: reason={reason!r}"
        )


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def _safe_ids(request: object) -> "tuple[str, str]":
    """Return ``(candidate_id, token_mint)`` for ``request`` if it is a sink
    request, else ``("", "")``. Pure / total; never raises.
    """
    if isinstance(request, Stage30_11PrivateSinkRequest):
        candidate_id = (
            request.candidate_id
            if isinstance(request.candidate_id, str)
            else ""
        )
        token_mint = (
            request.token_mint if isinstance(request.token_mint, str) else ""
        )
        return candidate_id, token_mint
    return "", ""


def _optional_str_ok(value: object) -> bool:
    """Return ``True`` iff ``value`` is ``None`` or a ``str``.

    Pure / total; never raises. The ``candidate_ref`` / ``tier_token`` request
    fields are ``Optional[str]`` in the committed Stage 30.11.3 contract, so
    ``None`` is valid -- but a present value of a wrong type (an ``int``, a list)
    is a malformed request the adapter must reject. (This is a SHAPE check only;
    it never requires those optionals to be non-blank, so it rejects no valid
    committed request shape.)
    """
    return value is None or isinstance(value, str)


def _is_valid_request(request: object) -> bool:
    """Return ``True`` iff ``request`` is a usable
    ``Stage30_11PrivateSinkRequest`` whose REQUIRED fields are all well-shaped.

    Pure / total; never raises. A request reaches this adapter ONLY from the
    committed Stage 30.11.3 private sink, which stamps every field; this guard
    fails closed on a malformed request BEFORE rendering a payload or calling the
    transport client. Required (each a non-blank ``str``): ``candidate_id``,
    ``token_mint``, ``compact_body`` (the rendered operator body), and
    ``created_at_utc``. ``source_stage`` must equal the committed Stage 30.11.3
    source-stage provenance token (``STAGE30_11_3_SOURCE_STAGE``) -- the only
    committed producer of a sink request. The ``Optional[str]`` ``candidate_ref``
    / ``tier_token`` must be ``None`` or a ``str`` (a shape check; not required to
    be non-blank, so no valid committed shape is rejected).
    """
    return (
        isinstance(request, Stage30_11PrivateSinkRequest)
        and is_nonblank_str(request.candidate_id)
        and is_nonblank_str(request.token_mint)
        and is_nonblank_str(request.compact_body)
        and is_nonblank_str(request.created_at_utc)
        and request.source_stage == STAGE30_11_3_SOURCE_STAGE
        and _optional_str_ok(request.candidate_ref)
        and _optional_str_ok(request.tier_token)
    )


def _client_result_accepted(
    result: object, *, candidate_id: str, token_mint: str
) -> bool:
    """Return ``True`` iff the injected client CONFIRMED the would-deliver for the
    SAME candidate the adapter handed it.

    Pure / total; never raises. An accept requires ALL of: ``result`` is a
    ``Stage30_11_5TransportClientResult``, ``result.accepted`` is exactly ``True``,
    ``result.transport_status`` is the closed accept status
    (``STAGE30_11_5_TRANSPORT_ACCEPT_STATUS`` --
    ``WOULD_DELIVER_PRIVATE_OPERATOR_MESSAGE``), AND the result's echoed
    ``candidate_id`` / ``token_mint`` match the request's. Any other return (a
    wrong type, a falsey flag, a rejected / mismatched status, or a mismatched
    identity) fails closed to ``False`` -- so a client that says ``accepted=True``
    with a rejected status, or that confirms a DIFFERENT candidate, is a clean
    transport-failed, never a spurious accept.
    """
    return (
        isinstance(result, Stage30_11_5TransportClientResult)
        and result.accepted is True
        and result.transport_status == STAGE30_11_5_TRANSPORT_ACCEPT_STATUS
        and result.candidate_id == candidate_id
        and result.token_mint == token_mint
    )


def _transport_failed_result(
    *,
    candidate_id: str,
    token_mint: str,
    created_at_utc: str,
) -> Stage30_11PrivateSinkResult:
    """Build the closed-set transport-failed result.

    Pure; no I/O. The single fail-closed result the adapter returns when the
    injected client RAISED (caught and swallowed -- no exception text is retained,
    as it could carry a transport secret), returned an odd value, or did not
    CONFIRM the would-deliver. It is NEVER a real transport failure and NEVER a
    real send: ``transport_attempted`` is ``True`` (the client was reached) and
    ``transport_accepted`` is ``False``.
    """
    return Stage30_11PrivateSinkResult(
        candidate_id=candidate_id,
        token_mint=token_mint,
        sink_decision=PRIVATE_SINK_DECISION_TRANSPORT_FAILED,
        sink_reason=PRIVATE_SINK_REASON_FAKE_TRANSPORT_REJECTED,
        transport_attempted=True,
        transport_accepted=False,
        created_at_utc=created_at_utc,
    )


# ---------------------------------------------------------------------------
# Pure builder: sink request -> private operator payload
# ---------------------------------------------------------------------------


def build_private_operator_payload(
    request: Stage30_11PrivateSinkRequest,
    *,
    created_at_utc: str,
) -> Stage30_11_5PrivateOperatorPayload:
    """Render the SAFE private operator payload from a committed Stage 30.11.3
    sink request.

    Pure / deterministic / no I/O, no provider call, no transport call. Echoes the
    request's safe-shape ids + optional candidate ref + display tier token,
    carries the request's already-rendered compact body as the operator body, and
    stamps the Stage 30.11.5 source-stage provenance token. Carries NO destination
    of its own (the real transport client supplies any destination, injected, at
    ceremony time). Raises ``Stage30_11_5PrivateTransportAdapterError`` only when
    handed a non-request record (a caller-shape failure with no request to
    render).
    """
    if not isinstance(request, Stage30_11PrivateSinkRequest):
        raise Stage30_11_5PrivateTransportAdapterError(
            "INVALID_SINK_REQUEST_RECORD_TYPE"
        )
    return Stage30_11_5PrivateOperatorPayload(
        candidate_id=request.candidate_id,
        token_mint=request.token_mint,
        candidate_ref=request.candidate_ref,
        tier_token=request.tier_token,
        body=request.compact_body,
        source_stage=STAGE30_11_5_SOURCE_STAGE,
        created_at_utc=created_at_utc,
    )


# ---------------------------------------------------------------------------
# Private transport adapter factory (the Stage 30.11.3 transport boundary)
# ---------------------------------------------------------------------------


def make_stage30_11_5_private_transport_adapter(
    *,
    transport_client: Stage30_11_5PrivateTransportClient,
    created_at_utc: str,
) -> Stage30_11_5PrivateTransport:
    """Build a Stage 30.11.3-conforming transport adapter parameterized by an
    INJECTED low-level transport client.

    The returned callable accepts a committed Stage 30.11.3
    ``Stage30_11PrivateSinkRequest`` (the ``PASS_TO_DISPATCH`` candidate the Stage
    30.11.3 private sink reached) and returns a ``Stage30_11PrivateSinkResult``:

      * a request that is not a usable ``Stage30_11PrivateSinkRequest`` or whose
        REQUIRED fields are malformed (a wrong type / blank id / blank body /
        blank timestamp / wrong source stage / wrong-typed optional) fails closed
        to ``PRIVATE_SINK_REJECTED_INVALID_INPUT`` WITHOUT calling the transport
        client (``transport_attempted`` is ``False``);
      * otherwise the SAFE private operator payload is rendered and handed to the
        INJECTED transport client inside a fail-closed guard:
          - the client RAISES -> the exception is caught and swallowed (no
            exception text retained, as it could carry a transport secret) ->
            ``PRIVATE_SINK_TRANSPORT_FAILED``;
          - the client CONFIRMS the would-deliver (a
            ``Stage30_11_5TransportClientResult`` with ``accepted is True``, the
            closed accept status, AND the SAME candidate id / token mint) ->
            ``PRIVATE_SINK_ACCEPTED`` (reason
            ``WOULD_SEND_PRIVATE_OPERATOR_MESSAGE``);
          - any other return (a wrong type, a falsey flag, a rejected / mismatched
            status, or a mismatched identity) -> ``PRIVATE_SINK_TRANSPORT_FAILED``
            (reason ``FAKE_TRANSPORT_REJECTED``).
        In every client-reached branch ``transport_attempted`` is ``True``.

    Pure / deterministic apart from the injected client's recording side effects;
    reads no env, no clock, no network; reserves no real dispatch, sends no
    Discord, writes no file, lets no client exception escape. The transport client
    is the ONLY call site that leaves this adapter, and it is ALWAYS injected. The
    returned callable plugs directly into the committed Stage 30.11.3
    ``make_stage30_11_private_dispatch_sink(transport=...)`` boundary.
    """

    def _transport_adapter(
        request: Stage30_11PrivateSinkRequest,
    ) -> Stage30_11PrivateSinkResult:
        if not _is_valid_request(request):
            candidate_id, token_mint = _safe_ids(request)
            return Stage30_11PrivateSinkResult(
                candidate_id=candidate_id,
                token_mint=token_mint,
                sink_decision=PRIVATE_SINK_DECISION_REJECTED_INVALID_INPUT,
                sink_reason=PRIVATE_SINK_REASON_INVALID_SINK_INPUT,
                transport_attempted=False,
                transport_accepted=False,
                created_at_utc=created_at_utc,
            )

        payload = build_private_operator_payload(
            request, created_at_utc=created_at_utc
        )
        try:
            client_result = transport_client(payload)
        except Exception:
            # The injected client raised: fail closed. No exception escapes and no
            # exception text is retained (it could carry a transport secret). The
            # client WAS reached, so this is a transport-failed, never an invalid
            # input. ``KeyboardInterrupt`` / ``SystemExit`` (``BaseException``) are
            # NOT swallowed.
            return _transport_failed_result(
                candidate_id=request.candidate_id,
                token_mint=request.token_mint,
                created_at_utc=created_at_utc,
            )
        if _client_result_accepted(
            client_result,
            candidate_id=request.candidate_id,
            token_mint=request.token_mint,
        ):
            return Stage30_11PrivateSinkResult(
                candidate_id=request.candidate_id,
                token_mint=request.token_mint,
                sink_decision=PRIVATE_SINK_DECISION_ACCEPTED,
                sink_reason=(
                    PRIVATE_SINK_REASON_WOULD_SEND_PRIVATE_OPERATOR_MESSAGE
                ),
                transport_attempted=True,
                transport_accepted=True,
                created_at_utc=created_at_utc,
            )
        return _transport_failed_result(
            candidate_id=request.candidate_id,
            token_mint=request.token_mint,
            created_at_utc=created_at_utc,
        )

    return _transport_adapter


__all__ = (
    "Stage30_11_5PrivateTransportClient",
    "Stage30_11_5PrivateTransport",
    "Stage30_11_5PrivateTransportAdapterError",
    "build_private_operator_payload",
    "make_stage30_11_5_private_transport_adapter",
)

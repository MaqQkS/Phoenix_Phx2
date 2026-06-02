"""Stage 30.11.3 private sink adapter.

The pure, offline ADAPTER that exposes the private sink boundary the Stage
30.11.2 runtime seam reaches ONLY behind a committed dip-gate
``PASS_TO_DISPATCH``. It translates a committed Stage 30.9.3
``Stage30_9_3LiveGateInput`` into the adapter-side private sink REQUEST shape
and hands that request to an INJECTED transport callable -- proven, in THIS
slice, with an in-memory recording FAKE transport only:

    a committed Stage 30.9.3 ``Stage30_9_3LiveGateInput`` (the
    ``PASS_TO_DISPATCH`` candidate)
      -> validate the input shape (fail closed on a wrong record type / blank
         id)
      -> build the compact operator body via the INJECTED builder
      -> build a Stage 30.11.3 ``Stage30_11PrivateSinkRequest``
      -> hand the request to the INJECTED transport (a FAKE in this slice)
      -> a Stage 30.11.3 ``Stage30_11PrivateSinkResult`` (normalized into the
         closed sink vocabulary)

There is NO real transport here. The transport is ALWAYS injected; this module
defines none, imports none, and reads no env. The real private compact dispatch
/ Discord send is a SEPARATE, explicitly operator-authorized step Stage 30.11.3
does not build.

Stage 30.11.2 runtime seam compatibility (the narrowest option). The committed
Stage 30.11.2 seam's injected ``dispatch_sink`` is typed to return a
``Stage30_11FakeDispatchResult`` (the seam reads ``result.accepted`` only when
``isinstance(result, Stage30_11FakeDispatchResult)``). The private sink defined
here returns the RICHER Stage 30.11.3 ``Stage30_11PrivateSinkResult`` (which
also pins ``sink_decision`` / ``sink_reason`` / ``transport_attempted`` /
``transport_accepted``). Rather than edit the committed seam or weaken the
private sink result, ``make_runtime_seam_compatible_sink`` wraps the private
sink in a thin pure converter that maps its result onto a
``Stage30_11FakeDispatchResult`` for the seam -- so the committed seam stays
untouched AND the rich result survives for the direct sink proof.

The adapter NEVER fetches market data, NEVER opens a network connection, NEVER
reads the process environment, NEVER reads a wall clock (``created_at_utc`` is
caller-injected), NEVER sends Discord, NEVER reserves a real dispatch / performs
a real send, NEVER performs a transport-layer veto, NEVER writes a file, runs NO
daemon / background loop, and edits NO Stage 28 / Stage 29 / Stage 30.3 / Stage
30.4 production file. It composes the committed Stage 30.9.3 gate-input type +
the committed Stage 30.11.2 fake-dispatch-result type (the permitted Stage 30.11
scope expansion) plus an injected fake transport / builder; nothing more.

Discipline:

  * Stdlib only (``typing``).
  * Imports only the Stage 30.11.3 models sibling + the committed Stage 30.9.3
    gate-models sibling (for the ``Stage30_9_3LiveGateInput`` input type) + the
    committed Stage 30.11.2 runtime-gate-models sibling (for the
    ``Stage30_11FakeDispatchResult`` seam-compat result type). No other PHX2
    module; no Stage 21-29 / Stage 30.3 / Stage 30.4 orchestrator / Stage 28
    suppression / live runner / provider / real transport / Discord import.
  * No ``os.environ`` / ``os.getenv`` access; no env read.
  * No network, no HTTP, no gRPC, no WebSocket, no socket.
  * No database / SQLite, no zstd / compression, no default storage root.
  * No live provider, transport-destination, or request-metadata reference.
  * No PHX1 import. No ``time`` / ``datetime`` import; timestamps are
    caller-injected.
"""

from __future__ import annotations

from typing import Callable, Iterable

from PHX2.stage30.stage30_9_3_dip_filtered_live_gate_models import (
    Stage30_9_3LiveGateInput,
)
from PHX2.stage30.stage30_11_2_runtime_gate_models import (
    Stage30_11FakeDispatchResult,
)
from PHX2.stage30.stage30_11_3_private_sink_models import (
    PRIVATE_SINK_DECISION_ACCEPTED,
    PRIVATE_SINK_DECISION_REJECTED_INVALID_INPUT,
    PRIVATE_SINK_DECISION_TRANSPORT_FAILED,
    PRIVATE_SINK_REASON_FAKE_TRANSPORT_REJECTED,
    PRIVATE_SINK_REASON_INVALID_SINK_INPUT,
    PRIVATE_SINK_REASON_WOULD_SEND_PRIVATE_OPERATOR_MESSAGE,
    STAGE30_11_3_SOURCE_STAGE,
    Stage30_11PrivateSinkProofSummary,
    Stage30_11PrivateSinkRequest,
    Stage30_11PrivateSinkResult,
    is_nonblank_str,
)


# The injected transport: a callable that, given a built private sink request,
# returns a ``Stage30_11PrivateSinkResult`` verdict. In this slice it is ALWAYS
# an in-memory recording FAKE transport (the real private compact dispatch path
# is a SEPARATE, operator-authorized step Stage 30.11.3 does not build).
Stage30_11PrivateTransport = Callable[
    [Stage30_11PrivateSinkRequest], Stage30_11PrivateSinkResult
]


# The injected compact body builder: a callable that renders a SAFE compact
# operator body from the gate input. ``build_default_compact_body`` is the safe
# self-contained default; a caller may inject another (no committed renderer is
# imported here, so no Stage 28 / 29 render / transport surface is reached).
Stage30_11CompactBodyBuilder = Callable[[Stage30_9_3LiveGateInput], str]


# The private dispatch sink the factory returns: a callable that, given a
# ``PASS_TO_DISPATCH`` gate input, returns a ``Stage30_11PrivateSinkResult``.
Stage30_11PrivateDispatchSink = Callable[
    [Stage30_9_3LiveGateInput], Stage30_11PrivateSinkResult
]


# The seam-compatible dispatch sink the wrapper returns: a callable that, given
# a gate input, returns a ``Stage30_11FakeDispatchResult`` (the type the
# committed Stage 30.11.2 runtime seam reads).
Stage30_11SeamDispatchSink = Callable[
    [Stage30_9_3LiveGateInput], Stage30_11FakeDispatchResult
]


# The safe compact-body header + missing-field placeholder (display strings
# only; never a secret / host / transport destination).
STAGE30_11_3_COMPACT_BODY_HEADER: str = "[STAGE 30.11.3 PRIVATE OPERATOR PING]"
_MISSING_FIELD_PLACEHOLDER: str = "NA"


# ---------------------------------------------------------------------------
# Module-local exception (caller-shape failure)
# ---------------------------------------------------------------------------


class Stage30_11PrivateSinkAdapterError(Exception):
    """Closed-set Stage 30.11.3 private sink adapter error.

    Raised ONLY for a caller-shape failure a pure builder cannot run with -- a
    ``gate_input`` that is not a ``Stage30_9_3LiveGateInput`` handed directly to
    ``build_default_compact_body`` / ``build_private_sink_request_from_gate_input``
    (there is no assembled candidate to translate). The private dispatch sink
    NEVER raises for a malformed input: it fails closed to a
    ``PRIVATE_SINK_REJECTED_INVALID_INPUT`` result BEFORE touching the
    transport. Carries only a closed-set reason token; never a raw payload or
    any secret value.
    """

    def __init__(self, reason: str) -> None:
        self.reason: str = reason
        super().__init__(
            f"Stage 30.11.3 private sink adapter error: reason={reason!r}"
        )


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def _safe_ids(gate_input: object) -> "tuple[str, str]":
    """Return ``(candidate_id, token_mint)`` for ``gate_input`` if it is a gate
    input, else ``("", "")``. Pure / total; never raises.
    """
    if isinstance(gate_input, Stage30_9_3LiveGateInput):
        candidate_id = (
            gate_input.candidate_id
            if isinstance(gate_input.candidate_id, str)
            else ""
        )
        token_mint = (
            gate_input.token_mint
            if isinstance(gate_input.token_mint, str)
            else ""
        )
        return candidate_id, token_mint
    return "", ""


def _is_valid_gate_input(gate_input: object) -> bool:
    """Return ``True`` iff ``gate_input`` is a usable ``Stage30_9_3LiveGateInput``
    with a non-blank candidate id AND token mint. Pure / total; never raises.
    """
    return (
        isinstance(gate_input, Stage30_9_3LiveGateInput)
        and is_nonblank_str(gate_input.candidate_id)
        and is_nonblank_str(gate_input.token_mint)
    )


def _fmt_optional(value: object) -> str:
    """Render an optional scalar as a safe display string (the missing-field
    placeholder for ``None``). Pure / total; never raises.
    """
    if value is None:
        return _MISSING_FIELD_PLACEHOLDER
    return str(value)


def _transport_accepted(result: object) -> bool:
    """Return ``True`` iff the injected transport returned a well-shaped
    ``Stage30_11PrivateSinkResult`` whose ``transport_accepted`` is truthy.

    Pure / total; never raises. Any other return (a wrong type, a falsey flag)
    fails closed to ``False`` -- so an odd transport return is a clean
    transport-failed, never a spurious accept.
    """
    return (
        isinstance(result, Stage30_11PrivateSinkResult)
        and bool(result.transport_accepted)
    )


# ---------------------------------------------------------------------------
# Pure builders
# ---------------------------------------------------------------------------


def build_default_compact_body(gate_input: Stage30_9_3LiveGateInput) -> str:
    """Build the SAFE default compact operator body from a gate input.

    Pure / deterministic / no I/O, no provider call. Renders ONLY safe scalar
    fields (ids, display tier token, drawdown magnitude, current market cap)
    into a compact operator-readable string; it imports NO committed renderer
    and reaches NO Stage 28 / 29 render / transport surface, so it carries no
    secret, no host, and no transport destination. Raises
    ``Stage30_11PrivateSinkAdapterError`` only when handed a non-gate-input
    record (a caller-shape failure).
    """
    if not isinstance(gate_input, Stage30_9_3LiveGateInput):
        raise Stage30_11PrivateSinkAdapterError("INVALID_GATE_INPUT_RECORD_TYPE")
    tier_token = (
        gate_input.tier_token
        if is_nonblank_str(gate_input.tier_token)
        else _MISSING_FIELD_PLACEHOLDER
    )
    return (
        f"{STAGE30_11_3_COMPACT_BODY_HEADER} "
        f"candidate={gate_input.candidate_id} "
        f"mint={gate_input.token_mint} "
        f"tier={tier_token} "
        f"drawdown_from_ath={_fmt_optional(gate_input.drawdown_from_ath)} "
        f"current_market_cap_usd="
        f"{_fmt_optional(gate_input.current_market_cap_usd)}"
    )


def build_private_sink_request_from_gate_input(
    gate_input: Stage30_9_3LiveGateInput,
    *,
    compact_body: str,
    created_at_utc: str,
) -> Stage30_11PrivateSinkRequest:
    """Build the adapter-side private sink request from a gate input.

    Pure / deterministic / no I/O, no provider call, no transport call. Echoes
    the gate input's safe-shape ids + optional candidate ref + display tier
    token, carries the caller-supplied rendered compact body + timestamp, and
    stamps the Stage 30.11.3 source-stage provenance token. Raises
    ``Stage30_11PrivateSinkAdapterError`` only when handed a non-gate-input
    record (a caller-shape failure with no assembled candidate to translate).
    """
    if not isinstance(gate_input, Stage30_9_3LiveGateInput):
        raise Stage30_11PrivateSinkAdapterError("INVALID_GATE_INPUT_RECORD_TYPE")
    return Stage30_11PrivateSinkRequest(
        candidate_id=gate_input.candidate_id,
        token_mint=gate_input.token_mint,
        candidate_ref=gate_input.candidate_ref,
        tier_token=gate_input.tier_token,
        compact_body=compact_body,
        created_at_utc=created_at_utc,
        source_stage=STAGE30_11_3_SOURCE_STAGE,
    )


# ---------------------------------------------------------------------------
# Private dispatch sink factory (the boundary the runtime seam reaches)
# ---------------------------------------------------------------------------


def make_stage30_11_private_dispatch_sink(
    *,
    transport: Stage30_11PrivateTransport,
    compact_body_builder: Stage30_11CompactBodyBuilder = build_default_compact_body,
    created_at_utc: str,
) -> Stage30_11PrivateDispatchSink:
    """Build a private dispatch sink parameterized by an INJECTED transport +
    compact body builder.

    The returned callable accepts a committed Stage 30.9.3
    ``Stage30_9_3LiveGateInput`` (the ``PASS_TO_DISPATCH`` candidate the Stage
    30.11.2 runtime seam reached) and returns a
    ``Stage30_11PrivateSinkResult``:

      * an input that is not a usable ``Stage30_9_3LiveGateInput`` (a wrong
        record type / blank id) fails closed to
        ``PRIVATE_SINK_REJECTED_INVALID_INPUT`` WITHOUT calling the transport
        (``transport_attempted`` is ``False``);
      * otherwise the compact body is built via the injected builder, a
        ``Stage30_11PrivateSinkRequest`` is built, and the request is handed to
        the INJECTED transport -- an accepted attempt yields
        ``PRIVATE_SINK_ACCEPTED`` (reason
        ``WOULD_SEND_PRIVATE_OPERATOR_MESSAGE``); a rejected attempt yields
        ``PRIVATE_SINK_TRANSPORT_FAILED`` (reason ``FAKE_TRANSPORT_REJECTED``).
        Either way ``transport_attempted`` is ``True``.

    Pure / deterministic apart from the injected transport's recording side
    effects; reads no env, no clock, no network; reserves no real dispatch,
    sends no Discord, writes no file. The transport is the ONLY call site that
    leaves this adapter, and it is ALWAYS injected.
    """

    def _private_dispatch_sink(
        gate_input: Stage30_9_3LiveGateInput,
    ) -> Stage30_11PrivateSinkResult:
        if not _is_valid_gate_input(gate_input):
            candidate_id, token_mint = _safe_ids(gate_input)
            return Stage30_11PrivateSinkResult(
                candidate_id=candidate_id,
                token_mint=token_mint,
                sink_decision=PRIVATE_SINK_DECISION_REJECTED_INVALID_INPUT,
                sink_reason=PRIVATE_SINK_REASON_INVALID_SINK_INPUT,
                transport_attempted=False,
                transport_accepted=False,
                created_at_utc=created_at_utc,
            )

        compact_body = compact_body_builder(gate_input)
        request = build_private_sink_request_from_gate_input(
            gate_input,
            compact_body=compact_body,
            created_at_utc=created_at_utc,
        )
        transport_result = transport(request)
        if _transport_accepted(transport_result):
            return Stage30_11PrivateSinkResult(
                candidate_id=gate_input.candidate_id,
                token_mint=gate_input.token_mint,
                sink_decision=PRIVATE_SINK_DECISION_ACCEPTED,
                sink_reason=(
                    PRIVATE_SINK_REASON_WOULD_SEND_PRIVATE_OPERATOR_MESSAGE
                ),
                transport_attempted=True,
                transport_accepted=True,
                created_at_utc=created_at_utc,
            )
        return Stage30_11PrivateSinkResult(
            candidate_id=gate_input.candidate_id,
            token_mint=gate_input.token_mint,
            sink_decision=PRIVATE_SINK_DECISION_TRANSPORT_FAILED,
            sink_reason=PRIVATE_SINK_REASON_FAKE_TRANSPORT_REJECTED,
            transport_attempted=True,
            transport_accepted=False,
            created_at_utc=created_at_utc,
        )

    return _private_dispatch_sink


# ---------------------------------------------------------------------------
# Stage 30.11.2 runtime seam compatibility wrapper (option B; narrowest)
# ---------------------------------------------------------------------------


def make_runtime_seam_compatible_sink(
    *,
    private_sink: Stage30_11PrivateDispatchSink,
    created_at_utc: str,
) -> Stage30_11SeamDispatchSink:
    """Wrap a private dispatch sink so the committed Stage 30.11.2 runtime seam
    can inject it directly.

    The committed seam reads ``result.accepted`` ONLY when ``isinstance(result,
    Stage30_11FakeDispatchResult)``. This thin pure converter calls the rich
    ``private_sink`` and maps its ``Stage30_11PrivateSinkResult`` onto a
    ``Stage30_11FakeDispatchResult`` (``accepted`` is ``True`` ONLY for a
    ``PRIVATE_SINK_ACCEPTED`` result whose ``transport_accepted`` holds). It
    edits NO committed seam / model and preserves the rich result for the direct
    sink proof. Pure apart from the wrapped sink's injected transport side
    effects; reads no env, no clock, no network.
    """

    def _seam_dispatch_sink(
        gate_input: Stage30_9_3LiveGateInput,
    ) -> Stage30_11FakeDispatchResult:
        result = private_sink(gate_input)
        if isinstance(result, Stage30_11PrivateSinkResult):
            accepted = (
                result.sink_decision == PRIVATE_SINK_DECISION_ACCEPTED
                and bool(result.transport_accepted)
            )
            candidate_id = result.candidate_id
            token_mint = result.token_mint
        else:
            accepted = False
            candidate_id, token_mint = _safe_ids(gate_input)
        return Stage30_11FakeDispatchResult(
            accepted=accepted,
            candidate_id=candidate_id,
            token_mint=token_mint,
            created_at_utc=created_at_utc,
        )

    return _seam_dispatch_sink


# ---------------------------------------------------------------------------
# Pure fold: private sink results -> proof summary
# ---------------------------------------------------------------------------


def summarize_private_sink_results(
    results: Iterable[Stage30_11PrivateSinkResult],
    *,
    created_at_utc: str,
) -> Stage30_11PrivateSinkProofSummary:
    """Fold an iterable of private sink results into a proof summary.

    Pure / deterministic / no I/O. Counts the closed-set sink decisions plus the
    transport-attempted / transport-accepted axes; a non-conforming item is
    skipped (it is not a ``Stage30_11PrivateSinkResult``). ``created_at_utc`` is
    caller-injected.
    """
    requests_seen = 0
    accepted = 0
    rejected_invalid = 0
    transport_failed = 0
    transport_attempted = 0
    transport_accepted = 0
    for result in results:
        if not isinstance(result, Stage30_11PrivateSinkResult):
            continue
        requests_seen += 1
        if result.sink_decision == PRIVATE_SINK_DECISION_ACCEPTED:
            accepted += 1
        elif (
            result.sink_decision == PRIVATE_SINK_DECISION_REJECTED_INVALID_INPUT
        ):
            rejected_invalid += 1
        elif result.sink_decision == PRIVATE_SINK_DECISION_TRANSPORT_FAILED:
            transport_failed += 1
        if result.transport_attempted:
            transport_attempted += 1
        if result.transport_accepted:
            transport_accepted += 1
    return Stage30_11PrivateSinkProofSummary(
        requests_seen=requests_seen,
        accepted=accepted,
        rejected_invalid=rejected_invalid,
        transport_failed=transport_failed,
        transport_attempted=transport_attempted,
        transport_accepted=transport_accepted,
        created_at_utc=created_at_utc,
    )


__all__ = (
    "Stage30_11PrivateTransport",
    "Stage30_11CompactBodyBuilder",
    "Stage30_11PrivateDispatchSink",
    "Stage30_11SeamDispatchSink",
    "STAGE30_11_3_COMPACT_BODY_HEADER",
    "Stage30_11PrivateSinkAdapterError",
    "build_default_compact_body",
    "build_private_sink_request_from_gate_input",
    "make_stage30_11_private_dispatch_sink",
    "make_runtime_seam_compatible_sink",
    "summarize_private_sink_results",
)

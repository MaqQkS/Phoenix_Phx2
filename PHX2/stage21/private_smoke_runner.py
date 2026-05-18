"""Stage 21.4 private smoke runner (offline-only).

This module wires the Stage 21.3 boundaries into the first
single-shot controlled private smoke ping path:

  injected provider adapter
    -> NormalizedLiveEvent (already decoded inside the adapter)
    -> tiny 21.4 TransportPayload builder
    -> injected Stage21Transport.send(...)
    -> Stage21PrivateSmokeResult

Stage 21.4 scope (locked, narrow):

  * Single-shot. No loop, no scheduler, no daemon, no sleep.
    The runner calls the adapter once with ``max_results=1``
    and the transport at most once. ``max_events > 1`` is
    allowed as a parameter but the runner still fails closed
    when the adapter returns more events than were requested.
  * No retries, no backoff, no dedupe, no archive, no
    quarantine. Those concerns belong to Stage 22.
  * No DB write, no manifest write, no file artifact, no
    ledger persistence.
  * No public / subscriber / paid routing -- the runner
    forwards a private-preview marker (``True``) and the
    locked dispatch flag (``False``) only.
  * No real HTTP / RPC / messaging client. The runner
    accepts the provider adapter and the transport via
    dependency injection; the caller (operator scratch
    script) constructs the real client out of band.
  * No reuse of the Stage 21.2 ``PrivatePreviewPingPayload``.
    That type carries the fake-path stage label ``"21.2"`` and
    the locked dispatch target ``"fake_private_transport"``.
    Stage 21.4 emits its own minimal body text from the
    safe NormalizedLiveEvent fields.

Per locked operator decision (Stage 21.4 plan §4) the smoke-run
gate is the existing Stage 21.3A readiness gate -- there is NO
separate ``PHX2_STAGE21_SMOKE_RUN_ENABLED`` env var. Single-shot
behaviour is enforced by the ``max_events`` parameter, not by
an env flag. The Stage 21 env-read boundary stays at
``PHX2/stage21/config.py`` alone.

Per locked operator decision (Stage 21.4 plan §9) Stage 21.4 is
offline-only. No ``stage21_live`` marker, no env-gated live
test, no committed CLI. The first real private smoke ping is
operator-driven from a scratch script that imports
``run_one_private_smoke_ping`` and injects the real adapter and
transport instances.

Module invariants (boundary-tested):

  * does NOT import any network / RPC / messaging / HTTP /
    DB / scheduler / secrets-management library;
  * does NOT read ``os.environ`` / ``os.getenv``;
  * does NOT import Phoenix1, PHX2.stage17..20, any
    PHX2 runtime layer, ``fake_provider`` /
    ``fake_transport`` / ``live_path_simulator``, or the
    Stage 21.3B Helius adapter (the runner depends on its
    own ``Stage21ProviderAdapter`` Protocol);
  * has NO retry / backoff / dedupe / archive / quarantine /
    scheduler / daemon / orchestrator vocabulary;
  * has NO subscriber / public / paid routing;
  * carries NO raw URL literal;
  * does NOT construct ``HeliusProviderAdapter`` or
    ``DiscordPrivateTransport`` -- both come in via
    dependency injection.
"""

from __future__ import annotations

from typing import NamedTuple, Protocol, Sequence

from PHX2.stage21.live_secrets_boundary import (
    Stage21LiveReadinessConfig,
    evaluate_live_readiness,
)
from PHX2.stage21.normalized_events import NormalizedLiveEvent
from PHX2.stage21.transport_contracts import (
    Stage21Transport,
    TransportPayload,
    TransportResult,
)


# ---------------------------------------------------------------------------
# Locked Stage 21.4 skipped-reason vocabulary
# ---------------------------------------------------------------------------
#
# Each constant maps to exactly one short-circuit branch in
# ``run_one_private_smoke_ping``. The closed set is locked by
# ``STAGE21_4_SKIPPED_REASONS`` and pinned in the Stage 21.4
# boundary test so a future drift requires an explicit operator
# decision.
#
# ``skipped_reason`` is the empty string on the happy path
# (the runner reached ``transport.send``); the transport's own
# rejection reason rides in ``transport_reason``.


SKIPPED_REASON_READINESS_NOT_READY: str = "readiness_not_ready"
SKIPPED_REASON_PROVIDER_FETCH_FAILED: str = "provider_fetch_failed"
SKIPPED_REASON_PROVIDER_RETURNED_ZERO_EVENTS: str = (
    "provider_returned_zero_events"
)
SKIPPED_REASON_PROVIDER_RETURNED_TOO_MANY: str = (
    "provider_returned_too_many"
)


STAGE21_4_SKIPPED_REASONS: tuple[str, ...] = (
    SKIPPED_REASON_READINESS_NOT_READY,
    SKIPPED_REASON_PROVIDER_FETCH_FAILED,
    SKIPPED_REASON_PROVIDER_RETURNED_ZERO_EVENTS,
    SKIPPED_REASON_PROVIDER_RETURNED_TOO_MANY,
)


# ---------------------------------------------------------------------------
# Locked Stage 21.4 smoke-label and default cap
# ---------------------------------------------------------------------------


# Stage label embedded in the Stage 21.4 smoke body text. Kept
# as a local Stage 21.4 constant rather than reusing the Stage
# 21.2 ``STAGE21_2_STAGE_LABEL`` so the live smoke body never
# carries the fake-path label.
STAGE21_4_SMOKE_LABEL: str = "21.4"


# Default single-shot cap. The runner asks the adapter for at
# most one event and fails closed if more are returned.
DEFAULT_MAX_EVENTS: int = 1


# ---------------------------------------------------------------------------
# Module-local error hierarchy
# ---------------------------------------------------------------------------
#
# Rooted at plain ``Exception`` (mirrors the Stage 21.3A decoder,
# Stage 21.3B adapter, and Stage 21.3C transport decisions). Used
# only at runner-entry argument validation; ``send`` paths do NOT
# raise. The Stage 21 central ``Stage21Error`` registry is NOT
# extended.


class Stage21RunnerError(Exception):
    """Base error for Stage 21.4 runner construction-time violations.

    Raised only by ``run_one_private_smoke_ping`` when one of the
    required keyword arguments is ``None`` / empty / non-positive.
    The runner does NOT raise on any normal refusal path; every
    refusal surfaces via ``Stage21PrivateSmokeResult.skipped_reason``
    (closed set) or ``Stage21PrivateSmokeResult.transport_reason``
    (echo of the transport result).
    """


# ---------------------------------------------------------------------------
# Injected provider-adapter Protocol
# ---------------------------------------------------------------------------


class Stage21ProviderAdapter(Protocol):
    """Duck-typed contract for an injected provider adapter.

    The runner depends on this Protocol rather than on the Stage
    21.3B ``HeliusProviderAdapter`` concrete type. The Stage 21.3B
    adapter satisfies the Protocol structurally (same method
    signature). Stage 21.4 tests inject in-memory fakes; the
    operator scratch recipe constructs the real
    ``HeliusProviderAdapter`` outside this module and passes it
    in here.

    The runner calls exactly one method on the adapter
    (``fetch_normalized_events``) and treats the result as an
    immutable ``Sequence`` of already-decoded
    ``NormalizedLiveEvent`` records. The adapter is responsible
    for any actual RPC / gRPC / HTTP / decoder work.
    """

    def fetch_normalized_events(
        self,
        *,
        cursor: object = None,
        max_results: int = 0,
    ) -> Sequence[NormalizedLiveEvent]: ...


# ---------------------------------------------------------------------------
# Frozen result record
# ---------------------------------------------------------------------------


class Stage21PrivateSmokeResult(NamedTuple):
    """Frozen, secret-safe outcome of one Stage 21.4 smoke-run call.

    Every field is a non-secret primitive or a closed-set token.
    No raw payload, no webhook URL, no provider response body,
    no exception message ever rides on this record. ``repr`` is
    the NamedTuple default and is safe by construction.

    Fields:

      * ``attempted``           -- True iff the runner reached
                                   ``transport.send``. False on
                                   every short-circuit branch
                                   above the send call.
      * ``sent``                -- True iff the transport reported
                                   the upstream accepted the send.
                                   False on every refusal path.
      * ``skipped_reason``      -- One of ``STAGE21_4_SKIPPED_REASONS``
                                   when the runner short-circuited
                                   before ``transport.send``;
                                   empty string when the runner
                                   reached the send call (the
                                   transport's own reason lives in
                                   ``transport_reason``).
      * ``transport_reason``    -- Echo of
                                   ``TransportResult.rejection_reason``
                                   when ``attempted`` is True;
                                   empty string otherwise.
      * ``provider_event_count`` -- Number of events the adapter
                                   returned. ``0`` on every
                                   short-circuit above the
                                   adapter call.
      * ``normalized_event_id`` -- The ``event_id`` of the event
                                   the runner forwarded to the
                                   transport. Empty string when
                                   no event was forwarded.
      * ``recipient``           -- Echo of the input recipient.
                                   Always present so the caller
                                   can correlate the result back
                                   to the requested target.
    """

    attempted: bool
    sent: bool
    skipped_reason: str
    transport_reason: str
    provider_event_count: int
    normalized_event_id: str
    recipient: str


# ---------------------------------------------------------------------------
# Private TransportPayload builder
# ---------------------------------------------------------------------------


def _build_smoke_transport_payload(
    event: NormalizedLiveEvent,
    *,
    recipient: str,
) -> TransportPayload:
    """Build a Stage 21.4 ``TransportPayload`` from a normalized event.

    The body text carries only safe non-secret
    ``NormalizedLiveEvent`` fields: the locked Stage 21.4 smoke
    label, ``event_type``, ``mint``, ``event_id``, and
    ``observed_at_utc``. It does NOT embed ``signature`` (~88-char
    base58 string -- noisy in operator-visible bodies and unneeded
    for the smoke path), ``decoded_fields`` / ``payload_summary``
    (raw chain data -- a Stage 22 archive concern), ``slot``
    (irrelevant for the smoke ping), or any URL / SecretRef /
    fingerprint.

    The locked private-preview marker is ``True``. The locked
    dispatch flag is ``False``. The dispatch-safety guard inside
    ``DiscordPrivateTransport.send`` re-asserts both before the
    injected client is invoked.
    """
    body_text = (
        f"[Stage {STAGE21_4_SMOKE_LABEL} private-preview smoke] "
        f"{event.event_type} for {event.mint}"
        f" | event_id={event.event_id}"
        f" observed_at_utc={event.observed_at_utc}"
    )
    return TransportPayload(
        recipient=recipient,
        body_text=body_text,
        private_preview_marker_present=True,
        safe_for_public_dispatch=False,
    )


# ---------------------------------------------------------------------------
# Public runner entry point
# ---------------------------------------------------------------------------


def run_one_private_smoke_ping(
    *,
    provider_adapter: Stage21ProviderAdapter,
    transport: Stage21Transport,
    readiness: Stage21LiveReadinessConfig,
    recipient: str,
    max_events: int = DEFAULT_MAX_EVENTS,
    cursor: object = None,
) -> Stage21PrivateSmokeResult:
    """Run exactly one controlled private smoke ping.

    Gate sequence (each step short-circuits on failure):

      1. Construction-time argument validation. ``None`` / empty
         / non-positive inputs raise ``Stage21RunnerError`` --
         these are caller-side contract violations, not refusals.
      2. Readiness pre-check. ``evaluate_live_readiness(readiness)``
         must report ``ready=True``; otherwise the runner returns
         ``skipped_reason=readiness_not_ready`` BEFORE the adapter
         is invoked. This prevents a real provider fetch from
         happening on a half-configured gate.
      3. Provider fetch. ``provider_adapter.fetch_normalized_events(
         cursor=cursor, max_results=max_events)`` is wrapped in a
         bare ``except Exception``. Any exception is discarded
         entirely (no ``str(exc)`` / ``repr(exc)`` / ``exc.args``
         / ``type(exc).__name__`` is propagated -- the adapter's
         exception may carry a raw URL / token / response body)
         and the runner returns
         ``skipped_reason=provider_fetch_failed``.
      4. Event-count guard. ``len(events) == 0`` returns
         ``skipped_reason=provider_returned_zero_events``.
         ``len(events) > max_events`` fails closed with
         ``skipped_reason=provider_returned_too_many``; the runner
         does NOT slice and send the first event when more were
         returned, so the operator sees the over-fetch instead of
         silent truncation.
      5. Transport send. ``transport.send(payload)`` is invoked
         exactly once. The transport contract is that ``send``
         never raises on a normal refusal -- it returns a
         ``TransportResult`` with ``dispatched=False`` and a
         closed-set rejection reason. The runner therefore does
         NOT wrap the send in ``try / except``; an exception here
         is a contract violation worth surfacing to the operator.

    Returns a ``Stage21PrivateSmokeResult`` carrying the runner
    outcome. The result is non-secret by construction (no raw
    payload, no webhook URL, no fingerprint, no exception
    message). ``repr(result)`` is safe.

    The runner has no clock, no sleep, no loop, no retry. It is
    synchronous, single-shot, and idempotent over identical input.
    """
    if provider_adapter is None:
        raise Stage21RunnerError(
            "run_one_private_smoke_ping requires a non-None "
            "provider_adapter"
        )
    if transport is None:
        raise Stage21RunnerError(
            "run_one_private_smoke_ping requires a non-None transport"
        )
    if readiness is None:
        raise Stage21RunnerError(
            "run_one_private_smoke_ping requires a non-None readiness"
        )
    if not isinstance(recipient, str) or recipient == "":
        raise Stage21RunnerError(
            "run_one_private_smoke_ping requires a non-empty "
            "recipient string"
        )
    if (
        isinstance(max_events, bool)
        or not isinstance(max_events, int)
        or max_events < 1
    ):
        raise Stage21RunnerError(
            "run_one_private_smoke_ping requires max_events to be a "
            "positive int (>= 1)"
        )

    # Readiness pre-check: every Stage 21.3A precondition must
    # hold BEFORE the adapter is invoked.
    readiness_result = evaluate_live_readiness(readiness)
    if not readiness_result.ready:
        return Stage21PrivateSmokeResult(
            attempted=False,
            sent=False,
            skipped_reason=SKIPPED_REASON_READINESS_NOT_READY,
            transport_reason="",
            provider_event_count=0,
            normalized_event_id="",
            recipient=recipient,
        )

    # Provider fetch with sanitized exception handling. The
    # adapter's exception may carry a raw URL / API key / response
    # body; ALL of it is discarded. The runner surfaces only the
    # closed-set ``provider_fetch_failed`` token.
    try:
        events = provider_adapter.fetch_normalized_events(
            cursor=cursor,
            max_results=max_events,
        )
    except Exception:
        return Stage21PrivateSmokeResult(
            attempted=False,
            sent=False,
            skipped_reason=SKIPPED_REASON_PROVIDER_FETCH_FAILED,
            transport_reason="",
            provider_event_count=0,
            normalized_event_id="",
            recipient=recipient,
        )

    event_count = len(events)
    if event_count == 0:
        return Stage21PrivateSmokeResult(
            attempted=False,
            sent=False,
            skipped_reason=(
                SKIPPED_REASON_PROVIDER_RETURNED_ZERO_EVENTS
            ),
            transport_reason="",
            provider_event_count=0,
            normalized_event_id="",
            recipient=recipient,
        )
    if event_count > max_events:
        # Fail closed: do NOT slice and forward the first event.
        # The operator should know the adapter over-fetched so a
        # latent batching bug surfaces immediately.
        return Stage21PrivateSmokeResult(
            attempted=False,
            sent=False,
            skipped_reason=SKIPPED_REASON_PROVIDER_RETURNED_TOO_MANY,
            transport_reason="",
            provider_event_count=event_count,
            normalized_event_id="",
            recipient=recipient,
        )

    event = events[0]
    payload = _build_smoke_transport_payload(event, recipient=recipient)

    # Transport exceptions are NOT caught. The Stage 21.3C
    # transport contract is that ``send`` never raises on refusal
    # -- every refusal surfaces via ``TransportResult``. An
    # exception here is a contract violation worth surfacing to
    # the operator rather than silently swallowing.
    transport_result: TransportResult = transport.send(payload)

    return Stage21PrivateSmokeResult(
        attempted=True,
        sent=transport_result.dispatched,
        skipped_reason="",
        transport_reason=transport_result.rejection_reason,
        provider_event_count=event_count,
        normalized_event_id=event.event_id,
        recipient=recipient,
    )


__all__ = [
    "DEFAULT_MAX_EVENTS",
    "SKIPPED_REASON_PROVIDER_FETCH_FAILED",
    "SKIPPED_REASON_PROVIDER_RETURNED_TOO_MANY",
    "SKIPPED_REASON_PROVIDER_RETURNED_ZERO_EVENTS",
    "SKIPPED_REASON_READINESS_NOT_READY",
    "STAGE21_4_SKIPPED_REASONS",
    "STAGE21_4_SMOKE_LABEL",
    "Stage21PrivateSmokeResult",
    "Stage21ProviderAdapter",
    "Stage21RunnerError",
    "run_one_private_smoke_ping",
]

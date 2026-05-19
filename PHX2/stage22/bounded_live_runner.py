"""Stage 22.5 bounded private ingest runner.

One-shot bounded core runner that composes the Stage 22 ingest
seam:

  * provider fetch (caller-supplied dependency-injected callable),
  * decode isolation + raw capture + provider failure isolation
    via the Stage 22.4 ``handle_provider_batch`` helper,
  * dedupe via the Stage 22.1 ``DedupeLedger`` Protocol,
  * private transport via the Stage 22.5 ``Stage22PrivateTransport``
    Protocol.

The runner returns a single ``Stage22IngestResult`` per call. It
performs no retries, no reconnect, no sleep, no backoff, no
file I/O, no environment reads, no network calls, no clock
reads. Every collateral collaborator is injected; the Stage 21
adapter / decoder / transport surfaces reach this module only
through caller-supplied callables and Protocols.

Bounded behaviour at 22.5:

  * One-shot fetch (``max_provider_attempts`` MUST be ``1``).
  * Optional ``max_events`` cap truncates the provider response
    tuple BEFORE ``handle_provider_batch`` runs, so
    ``events_received`` counts only events the helper actually
    processed.
  * Optional ``max_dispatches`` cap counts only successful
    dispatches; refused dispatches do not consume the cap.
  * Optional ``stop_after_first_dispatch`` flag breaks the
    per-envelope loop after the first ``dispatched=True``
    transport outcome; a refused outcome does NOT trigger the
    break.

Dedupe semantics (Stage 22.2):

  * ``new`` -> dispatch; on dispatched=True call
    ``mark_dispatched``; on dispatched=False record a transport
    refusal and skip mark_dispatched.
  * ``duplicate_already_dispatched`` -> skip dispatch entirely;
    do not call mark_dispatched.
  * ``duplicate_not_yet_dispatched`` -> dispatch; on
    dispatched=True call mark_dispatched; on dispatched=False
    record a transport refusal and skip mark_dispatched.
  * ``ledger_unavailable`` -> fail closed for that envelope:
    skip dispatch, skip mark_dispatched, do NOT count as
    transport refusal, continue the batch.

Outcome mapping (Stage 22.1 ``INGEST_RUNNER_OUTCOMES``):

  * readiness_check_fn returns False                 -> readiness_not_ready
  * fetch_outcome.ok=False                            -> provider_failed
  * fetch_outcome.ok=True and zero events received   -> provider_returned_zero
  * non-zero received, all malformed (none normalized) -> all_malformed
  * events_dispatched > 0                             -> ok
  * events_normalized > 0, no dispatch, no refusal    -> all_duplicates
  * events_normalized > 0, refusal observed, no dispatch -> transport_refused
  * fallback                                          -> ok

``max_attempts_exhausted`` is NOT emitted by Stage 22.5; the
runner pins ``max_provider_attempts == 1`` and the retry
execution layer is deferred to Stage 22.6.

This module imports only standard-library helpers (``typing``,
``collections.abc``) plus the Stage 22 contracts, errors, and
the Stage 22.4 batch helper. It does NOT import any Stage 21
module; the Stage 21 ``NormalizedLiveEvent`` type reaches this
seam transitively via ``PHX2.stage22.ingest_contracts``.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Callable

from PHX2.stage22.constants import (
    INGEST_OUTCOME_ALL_DUPLICATES,
    INGEST_OUTCOME_ALL_MALFORMED,
    INGEST_OUTCOME_OK,
    INGEST_OUTCOME_PROVIDER_FAILED,
    INGEST_OUTCOME_PROVIDER_RETURNED_ZERO,
    INGEST_OUTCOME_READINESS_NOT_READY,
    INGEST_OUTCOME_TRANSPORT_REFUSED,
    DEDUPE_OUTCOME_DUPLICATE_ALREADY_DISPATCHED,
    DEDUPE_OUTCOME_DUPLICATE_NOT_YET_DISPATCHED,
    DEDUPE_OUTCOME_LEDGER_UNAVAILABLE,
    DEDUPE_OUTCOME_NEW,
)
from PHX2.stage22.errors import Stage22RunnerError
from PHX2.stage22.failure_handling import handle_provider_batch
from PHX2.stage22.ingest_contracts import (
    DedupeLedger,
    IngestEventEnvelope,
    NormalizedLiveEvent,
    ProviderFetchOutcome,
    RawCaptureWriter,
    Stage22DispatchOutcome,
    Stage22IngestResult,
    Stage22PrivateTransport,
)


# ---------------------------------------------------------------------------
# Argument validation
# ---------------------------------------------------------------------------


def _is_strict_int(value: object) -> bool:
    """Return True iff value is an int and NOT a bool.

    ``bool`` is a subclass of ``int`` in Python; the Stage 22.5
    runner rejects ``True`` / ``False`` for the
    ``max_provider_attempts`` / ``max_events`` / ``max_dispatches``
    arguments so a stray truthy flag cannot silently coerce to
    ``1`` / ``0``.
    """
    return isinstance(value, int) and not isinstance(value, bool)


def _validate_required_str(*, field_name: str, value: object) -> None:
    if not isinstance(value, str):
        raise Stage22RunnerError(
            f"runner argument {field_name!r} must be a string"
        )
    if value == "":
        raise Stage22RunnerError(
            f"runner argument {field_name!r} must be a non-empty string"
        )


def _validate_required_callable(*, field_name: str, value: object) -> None:
    if value is None:
        raise Stage22RunnerError(
            f"runner argument {field_name!r} must not be None"
        )
    if not callable(value):
        raise Stage22RunnerError(
            f"runner argument {field_name!r} must be callable"
        )


def _validate_required_collaborator(
    *,
    field_name: str,
    value: object,
) -> None:
    if value is None:
        raise Stage22RunnerError(
            f"runner argument {field_name!r} must not be None"
        )


def _validate_optional_positive_int(
    *,
    field_name: str,
    value: object,
) -> None:
    """Validate an optional ``max_*`` cap argument.

    ``None`` is the disabled sentinel. A provided value must be
    a strict positive int (``bool`` rejected, ``<= 0`` rejected).
    """
    if value is None:
        return
    if not _is_strict_int(value):
        raise Stage22RunnerError(
            f"runner argument {field_name!r} must be a strict int "
            "(bool is not accepted)"
        )
    if value <= 0:
        raise Stage22RunnerError(
            f"runner argument {field_name!r} must be >= 1"
        )


# ---------------------------------------------------------------------------
# Provider failure result helper
# ---------------------------------------------------------------------------


def _build_provider_failed_result(
    *,
    provider_id: str,
    last_failure_label: str,
) -> Stage22IngestResult:
    return Stage22IngestResult(
        outcome=INGEST_OUTCOME_PROVIDER_FAILED,
        events_received=0,
        events_normalized=0,
        events_malformed=0,
        events_new=0,
        events_dispatched=0,
        events_transport_refused=0,
        provider_attempts=1,
        last_failure_label=last_failure_label,
        provider_id=provider_id,
    )


def _build_readiness_not_ready_result(
    *,
    provider_id: str,
) -> Stage22IngestResult:
    return Stage22IngestResult(
        outcome=INGEST_OUTCOME_READINESS_NOT_READY,
        events_received=0,
        events_normalized=0,
        events_malformed=0,
        events_new=0,
        events_dispatched=0,
        events_transport_refused=0,
        provider_attempts=0,
        last_failure_label="",
        provider_id=provider_id,
    )


# ---------------------------------------------------------------------------
# Provider fetch truncation
# ---------------------------------------------------------------------------


def _truncate_fetch_outcome(
    *,
    fetch_outcome: ProviderFetchOutcome,
    max_events: int | None,
) -> ProviderFetchOutcome:
    """Return a (possibly) truncated copy of ``fetch_outcome``.

    Truncation applies only to the ``responses`` tuple, and only
    when ``max_events`` is provided AND the tuple length exceeds
    it. The other fields pass through unchanged. The Stage 22.4
    batch helper consumes the truncated outcome so
    ``events_received`` reflects only the events the runner
    actually processed.
    """
    if max_events is None:
        return fetch_outcome
    if len(fetch_outcome.responses) <= max_events:
        return fetch_outcome
    return ProviderFetchOutcome(
        ok=fetch_outcome.ok,
        responses=tuple(fetch_outcome.responses[:max_events]),
        status_class=fetch_outcome.status_class,
        upstream_error_type=fetch_outcome.upstream_error_type,
        provider_attempt_index=fetch_outcome.provider_attempt_index,
    )


# ---------------------------------------------------------------------------
# Outcome mapping helper
# ---------------------------------------------------------------------------


def _map_success_outcome(
    *,
    events_received: int,
    events_normalized: int,
    events_dispatched: int,
    events_transport_refused: int,
    batch_outcome: str,
) -> str:
    """Decide the top-level outcome for a success-path batch.

    Called only when the fetch was OK. Mirrors the design's
    locked outcome priority:

      * provider_returned_zero (no events received)
      * all_malformed (events received, none normalized)
      * ok (at least one dispatched)
      * transport_refused (no dispatch, at least one refusal)
      * all_duplicates (no dispatch, no refusal, normalized > 0)
      * ok (fallback)
    """
    if events_received == 0:
        return INGEST_OUTCOME_PROVIDER_RETURNED_ZERO
    if events_normalized == 0:
        return INGEST_OUTCOME_ALL_MALFORMED
    if events_dispatched > 0:
        return INGEST_OUTCOME_OK
    if events_transport_refused > 0:
        return INGEST_OUTCOME_TRANSPORT_REFUSED
    # No dispatch, no refusal, but normalized events present:
    # every surviving normalized envelope was a duplicate that
    # the ledger reported as already dispatched, or hit
    # ``ledger_unavailable`` and was skipped. Stage 22.5 maps
    # both shapes onto ``all_duplicates`` because the runner's
    # observable behaviour is identical (zero dispatch, zero
    # refusal).
    if batch_outcome == INGEST_OUTCOME_OK:
        return INGEST_OUTCOME_ALL_DUPLICATES
    # The Stage 22.4 helper would have surfaced
    # ``all_malformed`` above; ``ok`` is the only fallthrough
    # value here.
    return INGEST_OUTCOME_OK


# ---------------------------------------------------------------------------
# Per-envelope dedupe + dispatch
# ---------------------------------------------------------------------------


def _process_one_envelope(
    *,
    envelope: IngestEventEnvelope,
    dedupe_ledger: DedupeLedger,
    private_transport: Stage22PrivateTransport,
) -> tuple[int, int, int, bool]:
    """Process one envelope through dedupe + dispatch.

    Returns the four-tuple ``(new_delta, dispatched_delta,
    refused_delta, dispatched_now)`` for the bounded runner's
    accumulators.

    Semantics:

      * ``dedupe_ledger.check_and_record`` is called exactly once
        per envelope. The Stage 22.1 contract guarantees the
        call is atomic.
      * Outcome ``new`` -> ``new_delta=1`` and the envelope is
        dispatched. On dispatched=True: ``mark_dispatched`` is
        called and ``dispatched_delta=1``. On dispatched=False:
        ``refused_delta=1`` and ``mark_dispatched`` is NOT
        called.
      * Outcome ``duplicate_already_dispatched`` -> all deltas
        are zero, no dispatch, no mark_dispatched.
      * Outcome ``duplicate_not_yet_dispatched`` -> ``new_delta``
        stays zero (the envelope is not new) but the envelope IS
        dispatched. dispatched / refused accounting mirrors the
        ``new`` branch.
      * Outcome ``ledger_unavailable`` -> all deltas zero; the
        envelope is NOT dispatched and NOT marked. The batch
        continues with the next envelope.

    Any exception raised by ``dedupe_ledger``, ``private_transport``,
    or ``mark_dispatched`` propagates unchanged: the runner
    treats these as fatal contract violations.
    """
    dedupe_outcome = dedupe_ledger.check_and_record(
        key=envelope.ingest_key,
    )
    outcome_token = dedupe_outcome.outcome

    if outcome_token == DEDUPE_OUTCOME_DUPLICATE_ALREADY_DISPATCHED:
        return (0, 0, 0, False)

    if outcome_token == DEDUPE_OUTCOME_LEDGER_UNAVAILABLE:
        return (0, 0, 0, False)

    new_delta = 1 if outcome_token == DEDUPE_OUTCOME_NEW else 0
    if outcome_token not in (
        DEDUPE_OUTCOME_NEW,
        DEDUPE_OUTCOME_DUPLICATE_NOT_YET_DISPATCHED,
    ):
        # Defensive: the Stage 22.1 closed set has no other
        # token but a fake / future ledger implementation could
        # drift. Treat any unknown outcome as a hard contract
        # violation.
        raise Stage22RunnerError(
            "dedupe_ledger.check_and_record returned an "
            "out-of-contract outcome token"
        )

    dispatch_outcome = private_transport.dispatch(envelope=envelope)
    if not isinstance(dispatch_outcome, Stage22DispatchOutcome):
        raise Stage22RunnerError(
            "private_transport.dispatch must return a Stage22DispatchOutcome"
        )
    if dispatch_outcome.dispatched:
        dedupe_ledger.mark_dispatched(key=envelope.ingest_key)
        return (new_delta, 1, 0, True)
    return (new_delta, 0, 1, False)


# ---------------------------------------------------------------------------
# Public runner
# ---------------------------------------------------------------------------


def run_bounded_private_ingest(
    *,
    provider_id: str,
    chain: str,
    observed_at_utc: str,
    received_at_utc: str,
    failed_at_utc: str,
    readiness_check_fn: Callable[[], bool],
    fetch_outcome_fn: Callable[[int], ProviderFetchOutcome],
    decode_event_fn: Callable[[Mapping[str, object]], NormalizedLiveEvent],
    classify_decode_error_fn: Callable[[BaseException], str],
    raw_capture_writer: RawCaptureWriter,
    dedupe_ledger: DedupeLedger,
    private_transport: Stage22PrivateTransport,
    max_provider_attempts: int = 1,
    max_events: int | None = None,
    max_dispatches: int | None = None,
    stop_after_first_dispatch: bool = False,
) -> Stage22IngestResult:
    """Run one bounded private ingest pass.

    Keyword-only arguments. See the module docstring for the
    full semantics, outcome priority, and dedupe rules.

    Raises ``Stage22RunnerError`` on any argument validation
    failure (notably ``max_provider_attempts != 1``). All other
    exceptions from injected collaborators (provider fetch,
    decoder, classifier, capture writer, dedupe ledger,
    transport) propagate unchanged.
    """
    # --- Argument validation -------------------------------------------------
    _validate_required_str(field_name="provider_id", value=provider_id)
    _validate_required_str(field_name="chain", value=chain)
    _validate_required_str(
        field_name="observed_at_utc", value=observed_at_utc
    )
    _validate_required_str(
        field_name="received_at_utc", value=received_at_utc
    )
    _validate_required_str(field_name="failed_at_utc", value=failed_at_utc)
    _validate_required_callable(
        field_name="readiness_check_fn", value=readiness_check_fn
    )
    _validate_required_callable(
        field_name="fetch_outcome_fn", value=fetch_outcome_fn
    )
    _validate_required_callable(
        field_name="decode_event_fn", value=decode_event_fn
    )
    _validate_required_callable(
        field_name="classify_decode_error_fn",
        value=classify_decode_error_fn,
    )
    _validate_required_collaborator(
        field_name="raw_capture_writer", value=raw_capture_writer
    )
    _validate_required_collaborator(
        field_name="dedupe_ledger", value=dedupe_ledger
    )
    _validate_required_collaborator(
        field_name="private_transport", value=private_transport
    )

    if not _is_strict_int(max_provider_attempts):
        raise Stage22RunnerError(
            "runner argument 'max_provider_attempts' must be a strict int "
            "(bool is not accepted)"
        )
    if max_provider_attempts != 1:
        raise Stage22RunnerError(
            "runner argument 'max_provider_attempts' must equal 1 in "
            "Stage 22.5 (retry execution is deferred to Stage 22.6)"
        )
    _validate_optional_positive_int(
        field_name="max_events", value=max_events
    )
    _validate_optional_positive_int(
        field_name="max_dispatches", value=max_dispatches
    )
    if not isinstance(stop_after_first_dispatch, bool):
        raise Stage22RunnerError(
            "runner argument 'stop_after_first_dispatch' must be a bool"
        )

    # --- Readiness gate ------------------------------------------------------
    if not readiness_check_fn():
        return _build_readiness_not_ready_result(provider_id=provider_id)

    # --- Provider fetch ------------------------------------------------------
    fetch_outcome = fetch_outcome_fn(0)
    if not isinstance(fetch_outcome, ProviderFetchOutcome):
        raise Stage22RunnerError(
            "fetch_outcome_fn must return a ProviderFetchOutcome"
        )

    # --- max_events truncation (success path only) --------------------------
    if fetch_outcome.ok:
        effective_outcome = _truncate_fetch_outcome(
            fetch_outcome=fetch_outcome,
            max_events=max_events,
        )
    else:
        # Provider failure: max_events does not apply. The Stage
        # 22.4 helper rejects a non-empty responses tuple on a
        # failed fetch as a contract violation.
        effective_outcome = fetch_outcome

    # --- Batch isolation -----------------------------------------------------
    batch_result = handle_provider_batch(
        provider_id=provider_id,
        chain=chain,
        fetch_outcome=effective_outcome,
        observed_at_utc=observed_at_utc,
        received_at_utc=received_at_utc,
        failed_at_utc=failed_at_utc,
        decode_event_fn=decode_event_fn,
        classify_decode_error_fn=classify_decode_error_fn,
        raw_capture_writer=raw_capture_writer,
    )

    if not fetch_outcome.ok:
        return _build_provider_failed_result(
            provider_id=provider_id,
            last_failure_label=batch_result.last_failure_label,
        )

    # --- Per-envelope dedupe + dispatch -------------------------------------
    events_received = batch_result.events_received
    events_normalized = batch_result.events_normalized
    events_malformed = batch_result.events_malformed
    events_new = 0
    events_dispatched = 0
    events_transport_refused = 0

    for envelope in batch_result.envelopes:
        if (
            max_dispatches is not None
            and events_dispatched >= max_dispatches
        ):
            break
        new_delta, dispatched_delta, refused_delta, dispatched_now = (
            _process_one_envelope(
                envelope=envelope,
                dedupe_ledger=dedupe_ledger,
                private_transport=private_transport,
            )
        )
        events_new += new_delta
        events_dispatched += dispatched_delta
        events_transport_refused += refused_delta
        if dispatched_now and stop_after_first_dispatch:
            break

    outcome = _map_success_outcome(
        events_received=events_received,
        events_normalized=events_normalized,
        events_dispatched=events_dispatched,
        events_transport_refused=events_transport_refused,
        batch_outcome=batch_result.outcome,
    )

    return Stage22IngestResult(
        outcome=outcome,
        events_received=events_received,
        events_normalized=events_normalized,
        events_malformed=events_malformed,
        events_new=events_new,
        events_dispatched=events_dispatched,
        events_transport_refused=events_transport_refused,
        provider_attempts=1,
        last_failure_label="",
        provider_id=provider_id,
    )


__all__ = [
    "run_bounded_private_ingest",
]

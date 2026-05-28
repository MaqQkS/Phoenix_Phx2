"""Stage 30.3B compact private runtime session orchestrator.

Stage 30.3B is the narrow parallel orchestrator that plugs the
Stage 30.3A compact-body transport wrapper + Stage 30.3A
candidate-context recorder into the existing Stage 28.9 private
live provider session adapter, without modifying any Stage 21-29
or Stage 30.3A production module.

On each call the orchestrator:

  * wraps the caller-injected ``inner_candidate_assembler`` with
    a Stage 30.3A ``Stage30_3CompactCandidateContextRecorder`` so
    every Stage 27.6 candidate record produced by the inner
    assembler is captured onto a duck-typed Stage 30.3 recorded
    entry (the recorder forwards the inner record byte-for-byte
    so Stage 28.9's downstream Stage 27.6 -> Stage 28.6 mapper
    still sees the verbatim Stage 27.6 shape),

  * optionally wraps the caller-injected ``inner_transport``
    with the caller-supplied
    ``private_migration_context_injector`` (the operator-owned
    Stage 29.5.6 wrapper). The orchestrator duck-types the
    injector via ``wrap_transport(inner_transport)`` so this
    module imports NO Stage 29 module by name. When no injector
    is supplied the orchestrator uses ``inner_transport`` as-is,

  * wraps the result with the Stage 30.3A
    ``Stage30_3CompactBodyTransportWrapper`` so each
    ``send_one_audited_post`` consumes the most recent Stage
    30.3 recorded entry, projects it onto a Stage 30.1 tier
    decision plus a Stage 30.2 compact ping snapshot, replaces
    the caller-supplied ``payload["content"]`` with the rendered
    compact body, writes the Stage 30.1 / Stage 30.2 / Stage
    30.3 JSONL artifact lines, and forwards a fresh
    ``dict(payload)`` copy through the optional Stage 29.5.6
    layer + the inner transport,

  * delegates to
    ``run_stage28_9_live_provider_session(...)`` (the
    already-closed Stage 28.9 orchestrator) with the wrapped
    recorder injected as ``candidate_assembler`` and the wrapped
    transport injected as ``transport``,

  * projects per-outcome counters off the wrapper's
    ``calls_received`` and ``outcomes_count(token)`` axes for
    every Stage 30.3 ``COMPACT_OUTCOME_*`` token, sums the
    ``FAILED_*`` tokens into ``compact_renders_failed``, and
    returns a Stage30_3CompactRuntimeSessionResult bundling the
    Stage 28.9 session result, the per-outcome counters, the
    recorded-entries count, and the wrapper-order tuple.

Stage 30.3B exercises the wrapper stack OFFLINE-ONLY:

  * No env reads. ``os.environ`` / ``os.getenv`` / ``os.environb``
    are never touched here.
  * No direct network library import. The orchestrator does NOT
    construct a real provider client; the operator supplies the
    provider event source (or a fake test source).
  * No live Discord. No real gRPC / HTTP / WebSocket. No
    operator-channel send.
  * No Stage 29 module imported by name (the optional Stage
    29.5.6 injector is duck-typed via ``wrap_transport``).
  * The webhook URL is NEVER copied onto a Stage 30.3 record,
    artifact line, or session result.

Discipline:

  * Stdlib only (``typing`` / ``pathlib``).
  * Stage 28 / Stage 30 sibling modules imported read-only via
    the documented Stage 30.3B import allowlist.
  * No URL host literal, no API-key literal, no bearer-token
    literal, no authorization-header literal.
  * No PHX1 import. No legacy phoenix-1 import path.
  * No top-level Call (no implicit I/O at import time).
"""

from __future__ import annotations

from pathlib import Path
from typing import NamedTuple, Optional, Tuple

from PHX2.stage28.live_provider_session_adapter import (
    run_stage28_9_live_provider_session,
)
from PHX2.stage28.live_provider_session_models import (
    Stage28_9LiveProviderSessionConfig,
    Stage28_9LiveProviderSessionResult,
)
from PHX2.stage30.stage30_3_compact_body_transport_wrapper import (
    Stage30_3CompactBodyTransportWrapper,
)
from PHX2.stage30.stage30_3_compact_candidate_context_recorder import (
    Stage30_3CompactCandidateContextRecorder,
)
from PHX2.stage30.stage30_3_compact_runtime_models import (
    COMPACT_OUTCOME_FAILED_CAP,
    COMPACT_OUTCOME_FAILED_COMPACT_RENDER,
    COMPACT_OUTCOME_FAILED_EXCEPTION,
    COMPACT_OUTCOME_FAILED_INPUT_SHAPE,
    COMPACT_OUTCOME_FAILED_SNAPSHOT_WRITE,
    COMPACT_OUTCOME_FAILED_TIER_DECISION,
    COMPACT_OUTCOME_RENDERED,
    COMPACT_OUTCOME_SKIPPED_NOT_TIERABLE,
    Stage30_3CompactRuntimeContext,
    Stage30_3CompactRuntimeError,
)


# ---------------------------------------------------------------------------
# Stage 30.3 compact runtime session result
# ---------------------------------------------------------------------------


class Stage30_3CompactRuntimeSessionResult(NamedTuple):
    """Immutable Stage 30.3 compact runtime session result.

    Bundles the Stage 28.9 session result with the Stage 30.3
    wrapper's per-outcome counters and the Stage 30.3 recorder's
    captured-entries count. Carries no raw provider payload, no
    webhook URL, no API key, no bearer token, no authorization
    header. The Stage 28.9 session result already enforces its own
    redaction-safe shape; the Stage 30.3 counters and the wrapper
    order tuple are closed-set integers / closed-set tokens by
    construction.

    Fields:

      * ``session_result``             -- the Stage 28.9 session
                                          result returned by
                                          ``run_stage28_9_live_provider_session``.
      * ``compact_renders_attempted``  -- number of
                                          ``send_one_audited_post``
                                          calls observed by the
                                          Stage 30.3 wrapper.
      * ``compact_renders_succeeded``  -- count of
                                          ``COMPACT_OUTCOME_RENDERED``
                                          outcomes.
      * ``compact_renders_failed``     -- sum of every
                                          ``COMPACT_OUTCOME_FAILED_*``
                                          outcome.
      * ``compact_renders_skipped``    -- count of
                                          ``COMPACT_OUTCOME_SKIPPED_NOT_TIERABLE``
                                          outcomes.
      * ``recorded_entries_count``     -- number of entries the
                                          Stage 30.3 recorder
                                          captured.
      * ``wrapper_order``              -- caller-supplied closed-
                                          set wrapper-order tuple
                                          (preserved verbatim).
    """

    session_result: Stage28_9LiveProviderSessionResult
    compact_renders_attempted: int
    compact_renders_succeeded: int
    compact_renders_failed: int
    compact_renders_skipped: int
    recorded_entries_count: int
    wrapper_order: Tuple[str, ...]


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


def run_stage30_3_compact_runtime_session(
    *,
    session_config: Stage28_9LiveProviderSessionConfig,
    provider_event_source: object,
    inner_candidate_assembler: object,
    inner_transport: object,
    output_dir: Path,
    private_webhook_url: str,
    live_env_ready: bool,
    live_operator_request: bool,
    compact_runtime_context: Stage30_3CompactRuntimeContext,
    clock: object,
    wrapper_order: Tuple[str, ...],
    private_migration_context_injector: Optional[object] = None,
    stop_signal: Optional[object] = None,
) -> Stage30_3CompactRuntimeSessionResult:
    """Drive one Stage 30.3B compact private runtime session.

    The orchestrator:

      * validates the Stage 30.3 wrapper-order tuple BEFORE
        building any wrapper (so an invalid order surfaces a
        ``Stage30_3CompactRuntimeError("WRAPPER_ORDER_INVALID")``
        without ever calling the provider source, the inner
        assembler, or the inner transport),
      * wraps ``inner_candidate_assembler`` with a Stage 30.3
        recorder bound to ``clock``,
      * optionally chains the caller-supplied
        ``private_migration_context_injector`` over
        ``inner_transport`` via duck-typed
        ``wrap_transport(inner_transport)`` (the orchestrator
        imports zero Stage 29 modules; the injector type is
        validated only at call time),
      * wraps the resulting transport with a Stage 30.3 compact
        body transport wrapper bound to ``compact_runtime_context``,
        ``clock``, and ``wrapper_order``,
      * delegates to ``run_stage28_9_live_provider_session(...)``
        with the wrapped recorder + wrapped transport,
      * projects per-outcome counters off the wrapper's public
        ``calls_received`` + ``outcomes_count(...)`` axes,
      * returns a ``Stage30_3CompactRuntimeSessionResult``
        bundling the Stage 28.9 session result, the per-outcome
        counters, the recorder's captured-entries count, and the
        caller-supplied ``wrapper_order``.

    The orchestrator never opens a network connection, never reads
    the process environment, never sleeps, never schedules, never
    batches, and never bypasses the Stage 28.9 readiness gate
    (the readiness check runs INSIDE
    ``run_stage28_9_live_provider_session``).
    """
    if not isinstance(wrapper_order, tuple):
        raise Stage30_3CompactRuntimeError("WRAPPER_ORDER_INVALID")
    if len(wrapper_order) == 0:
        raise Stage30_3CompactRuntimeError("WRAPPER_ORDER_INVALID")

    recorder = Stage30_3CompactCandidateContextRecorder(
        inner_assembler=inner_candidate_assembler,
        clock=clock,
    )

    if private_migration_context_injector is not None:
        wrap_transport_fn = getattr(
            private_migration_context_injector,
            "wrap_transport",
            None,
        )
        if not callable(wrap_transport_fn):
            raise Stage30_3CompactRuntimeError(
                "MIGRATION_CONTEXT_INJECTOR_INVALID"
            )
        chained_transport: object = wrap_transport_fn(inner_transport)
    else:
        chained_transport = inner_transport

    compact_transport = Stage30_3CompactBodyTransportWrapper(
        inner_transport=chained_transport,
        recorder=recorder,
        context=compact_runtime_context,
        clock=clock,
        wrapper_order=wrapper_order,
    )

    session_result = run_stage28_9_live_provider_session(
        config=session_config,
        provider_event_source=provider_event_source,
        candidate_assembler=recorder,
        transport=compact_transport,
        output_dir=output_dir,
        private_webhook_url=private_webhook_url,
        live_env_ready=live_env_ready,
        live_operator_request=live_operator_request,
        stop_signal=stop_signal,
    )

    attempted = compact_transport.calls_received
    succeeded = compact_transport.outcomes_count(
        COMPACT_OUTCOME_RENDERED
    )
    skipped = compact_transport.outcomes_count(
        COMPACT_OUTCOME_SKIPPED_NOT_TIERABLE
    )
    failed = (
        compact_transport.outcomes_count(
            COMPACT_OUTCOME_FAILED_INPUT_SHAPE
        )
        + compact_transport.outcomes_count(
            COMPACT_OUTCOME_FAILED_TIER_DECISION
        )
        + compact_transport.outcomes_count(
            COMPACT_OUTCOME_FAILED_COMPACT_RENDER
        )
        + compact_transport.outcomes_count(COMPACT_OUTCOME_FAILED_CAP)
        + compact_transport.outcomes_count(
            COMPACT_OUTCOME_FAILED_SNAPSHOT_WRITE
        )
        + compact_transport.outcomes_count(
            COMPACT_OUTCOME_FAILED_EXCEPTION
        )
    )
    recorded_entries_count = len(recorder.recorded_entries)

    return Stage30_3CompactRuntimeSessionResult(
        session_result=session_result,
        compact_renders_attempted=attempted,
        compact_renders_succeeded=succeeded,
        compact_renders_failed=failed,
        compact_renders_skipped=skipped,
        recorded_entries_count=recorded_entries_count,
        wrapper_order=wrapper_order,
    )


__all__ = (
    "Stage30_3CompactRuntimeSessionResult",
    "run_stage30_3_compact_runtime_session",
)

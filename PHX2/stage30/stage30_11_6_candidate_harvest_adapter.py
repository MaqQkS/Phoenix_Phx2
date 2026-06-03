"""Stage 30.11.6 real candidate source / harvest adapter.

The pure, offline HARVEST ADAPTER that is the narrowest remaining blocker before
the controlled live ceremony can actually run: it drives an INJECTED committed
candidate assembler over a bounded event source, CAPTURES each assembled
candidate record, and PROJECTS it into the Stage 30.11.5 flat projection shape --
WITHOUT ever invoking the old ungated Stage 28.9 / Stage 29.3 dispatch path:

    a bounded source of normalized events (fakes / offline in this slice)
      -> for each event (a single BOUNDED for-loop; AT MOST ``max_harvest``):
           -> call the INJECTED assembler's ``assemble(event, candidate_id=...)``
              (the committed ``Stage28_9CandidateAssembler.assemble`` protocol by
              structure) -- a raise / empty return is a clean
              ``SKIPPED_ASSEMBLY_FAILED`` (no candidate)
           -> flatten the captured record to safe scalars via the INJECTED record
              flattener (the deep committed live candidate RECORD -> flat
              safe-scalar fields; the Stage 27 / 28 / 29-specific extraction lives
              in the injected flattener AT THE CEREMONY BOUNDARY, never in this
              committed slice)
           -> validate + project via the committed Stage 30.11.6 projection
              adapter -- a missing / malformed field is a clean
              ``SKIPPED_PROJECTION_REJECTED`` (no candidate)
           -> on success accumulate a ``Stage30_11_6CandidateProjection``
      -> a ``Stage30_11_6HarvestResult`` whose ``candidate_source`` is a tuple of
         flat projections the committed Stage 30.11.5 bounded runner consumes

The CORE requirement this slice fixes: harvest an assembled candidate WITHOUT
invoking the old ungated dispatch path. The committed live assembly path
(``run_stage28_9_live_provider_session``) FUSES candidate assembly with the Stage
28.6 runner + transport dispatch and returns only counters; this adapter instead
drives ONLY the ``assemble`` boundary (which the committed Stage 28.9 adapter
already exposes as a separable protocol) and NEVER constructs a Stage 28.6 runner,
a transport, a dispatch sink, a webhook, or any send surface -- so an old ungated
dispatch is STRUCTURALLY impossible here, not merely unused. The harvested
``candidate_source`` is the INPUT the committed Stage 30.11.5 bounded runner (and
behind it the committed Stage 30.11.1 bridge + Stage 30.9.3 dip gate + Stage
30.11.3 private sink) gate -- harvesting it is never a bypass of them.

The adapter NEVER fetches market data, NEVER opens a network connection, NEVER
reads the process environment, NEVER reads a wall clock (``created_at_utc`` is
caller-injected), NEVER reserves a dispatch / performs a send, NEVER sends
Discord, NEVER writes a file, runs NO daemon / ``while`` loop, retains NO captured
deep record on its result (the record is captured transiently and only its
flattened safe scalars survive), and edits NO Stage 27 / Stage 28 / Stage 29 /
Stage 30.3 / Stage 30.4 production file. It composes ONLY the Stage 30.11.6 models
+ projection-adapter siblings plus the INJECTED assembler / record flattener;
nothing more. In THIS slice the injected assembler / flattener are ALWAYS FAKES --
the real committed assembler binding is a SEPARATE, operator-authorized ceremony
step Stage 30.11.6 does not build.

Discipline:

  * Stdlib only (``typing``).
  * Imports ONLY the Stage 30.11.6 candidate-source-models + projection-adapter
    siblings. No other PHX2 module; no Stage 21-29 (incl. the committed Stage 28.9
    live provider session adapter, the nested Stage 27 / 28 / 29 live candidate
    record, Stage 28 suppression, Stage 29 live provider) / Stage 30.3 / Stage
    30.4 orchestrator / live runner / provider / transport / dispatch import.
  * No ``os.environ`` / ``os.getenv`` access; no env read.
  * No network, no HTTP, no gRPC, no WebSocket, no socket.
  * No database / SQLite, no zstd / compression, no default storage root.
  * No live provider, transport-destination, dispatch sink, or request-metadata
    reference.
  * No PHX1 import. No ``time`` / ``datetime`` import; the runtime clock is not
    read and timestamps are caller-injected.
"""

from __future__ import annotations

from typing import (
    Callable,
    Iterable,
    List,
    Protocol,
    runtime_checkable,
)

from PHX2.stage30.stage30_11_6_candidate_source_models import (
    HARVEST_DECISION_HARVESTED,
    HARVEST_DECISION_SKIPPED_ASSEMBLY_FAILED,
    HARVEST_DECISION_SKIPPED_PROJECTION_REJECTED,
    HARVEST_REASON_ASSEMBLY_RAISED_OR_EMPTY,
    HARVEST_REASON_PROJECTION_FAILED_CLOSED,
    HARVEST_REASON_READY_FOR_LIVE_RUNNER,
    PROJECTION_DECISION_PROJECTED,
    PROJECTION_DECISION_REJECTED_INVALID_SHAPE,
    PROJECTION_REASON_INVALID_FIELD_SHAPE,
    STAGE30_11_6_DEFAULT_CANDIDATE_ID_PREFIX,
    STAGE30_11_6_DEFAULT_MAX_HARVEST,
    STAGE30_11_6_MAX_HARVEST_HARD_CAP,
    STAGE30_11_6_NOT_PROJECTED,
    Stage30_11_6CandidateHarvestOutcome,
    Stage30_11_6CandidateProjection,
    Stage30_11_6HarvestResult,
    Stage30_11_6HarvestSummary,
)
from PHX2.stage30.stage30_11_6_stage29_projection_adapter import (
    project_harvested_candidate,
)


# ---------------------------------------------------------------------------
# Injected boundary types
# ---------------------------------------------------------------------------


@runtime_checkable
class Stage30_11_6CandidateAssembler(Protocol):
    """The INJECTED candidate assembler the harvest adapter drives.

    A structural match for the committed Stage 28.9
    ``Stage28_9CandidateAssembler`` protocol -- a single method
    ``assemble(normalized_event, *, candidate_id) -> object`` that returns ONE
    assembled candidate record for the supplied normalized event. The harvest
    adapter calls ONLY this method; it NEVER reaches a dispatch / transport / runner
    surface. In THIS slice the injected assembler is ALWAYS a FAKE; at the
    operator-authorized ceremony the committed ``Stage28_9DefaultCandidateAssembler``
    (or a fake) is injected directly -- the harvest adapter imports neither it nor
    any Stage 27 / 28 / 29 record type (the assembler is duck-typed as ``object``).
    """

    def assemble(
        self, normalized_event: object, *, candidate_id: str
    ) -> object:
        ...


# The INJECTED record flattener: a callable that reduces ONE captured assembled
# candidate record (the deeply-nested committed Stage 27 / 28 / 29 live candidate
# record at the ceremony, a fake in this slice) to a flat safe-scalar projection
# the Stage 30.11.6 projection adapter reads by field name -- a flat MAPPING /
# dict OR an attribute-bearing object whose keys / attributes are the Stage
# 30.11.5 projection field names. The Stage 27 / 28 / 29-specific extraction lives
# HERE, INJECTED, AT THE CEREMONY BOUNDARY (an out-of-repo, operator-authorized
# step) so THIS committed slice imports NO Stage 21-29 record type. A flattener
# raise is a clean ``SKIPPED_PROJECTION_REJECTED`` (no candidate).
Stage30_11_6RecordFlattener = Callable[[object], object]


# ---------------------------------------------------------------------------
# Module-local exception (caller-shape failure)
# ---------------------------------------------------------------------------


class Stage30_11_6CandidateHarvestError(Exception):
    """Closed-set Stage 30.11.6 candidate harvest error.

    Raised ONLY for a caller-shape failure the harvest adapter cannot run with --
    a ``max_harvest`` that is not a positive ``int`` within the HARD harvest cap
    (``1 <= max_harvest <= STAGE30_11_6_MAX_HARVEST_HARD_CAP``): an out-of-bounds
    harvest budget would make the bounded harvest undefined, so the adapter fails
    closed BEFORE driving the assembler over any event. Degraded per-event
    outcomes never raise; a raising assembler / flattener and a malformed record
    fail closed to a clean skip. Carries only a closed-set reason token; never a
    raw record or any secret value.
    """

    def __init__(self, reason: str) -> None:
        self.reason: str = reason
        super().__init__(
            f"Stage 30.11.6 candidate harvest error: reason={reason!r}"
        )


# ---------------------------------------------------------------------------
# Bounded-harvest config helper
# ---------------------------------------------------------------------------


def is_within_harvest_cap(max_harvest: object) -> bool:
    """Return ``True`` iff ``max_harvest`` is a positive ``int`` within the HARD
    harvest cap (``1 <= max_harvest <= STAGE30_11_6_MAX_HARVEST_HARD_CAP``).

    Pure / TOTAL; never raises. A non-int, a ``bool`` (``True`` / ``False`` are
    not budgets), a non-positive value, or a value above the hard cap fails closed
    to ``False`` -- so a harvest can never be parameterized to pull more than the
    committed Stage 30.11.5 ``max_candidates <= 10`` ceiling allows.
    """
    if isinstance(max_harvest, bool):
        return False
    if not isinstance(max_harvest, int):
        return False
    return 1 <= max_harvest <= STAGE30_11_6_MAX_HARVEST_HARD_CAP


# ---------------------------------------------------------------------------
# Pure per-event outcome builders
# ---------------------------------------------------------------------------


def _assembly_failed_outcome(
    *, created_at_utc: str
) -> Stage30_11_6CandidateHarvestOutcome:
    """Build a clean ``SKIPPED_ASSEMBLY_FAILED`` outcome (the injected assembler
    raised / returned no record; no record captured, so no identity / projection).
    Pure; no I/O.
    """
    return Stage30_11_6CandidateHarvestOutcome(
        candidate_id="",
        token_mint="",
        harvest_decision=HARVEST_DECISION_SKIPPED_ASSEMBLY_FAILED,
        harvest_reason=HARVEST_REASON_ASSEMBLY_RAISED_OR_EMPTY,
        projection_decision=STAGE30_11_6_NOT_PROJECTED,
        projection_reason=STAGE30_11_6_NOT_PROJECTED,
        rejected_field="",
        created_at_utc=created_at_utc,
    )


def _flatten_failed_outcome(
    *, created_at_utc: str
) -> Stage30_11_6CandidateHarvestOutcome:
    """Build a clean ``SKIPPED_PROJECTION_REJECTED`` outcome for a captured record
    whose injected flattener RAISED (the record could not be reduced to safe
    scalars). Pure; no I/O. No safe identity is readable, so it is echoed as ``""``;
    the projection tokens name an invalid field shape with no specific field.
    """
    return Stage30_11_6CandidateHarvestOutcome(
        candidate_id="",
        token_mint="",
        harvest_decision=HARVEST_DECISION_SKIPPED_PROJECTION_REJECTED,
        harvest_reason=HARVEST_REASON_PROJECTION_FAILED_CLOSED,
        projection_decision=PROJECTION_DECISION_REJECTED_INVALID_SHAPE,
        projection_reason=PROJECTION_REASON_INVALID_FIELD_SHAPE,
        rejected_field="",
        created_at_utc=created_at_utc,
    )


# ---------------------------------------------------------------------------
# Public harvest adapter
# ---------------------------------------------------------------------------


def harvest_live_candidates(
    events: Iterable[object],
    *,
    assembler: Stage30_11_6CandidateAssembler,
    record_flattener: Stage30_11_6RecordFlattener,
    created_at_utc: str,
    max_harvest: int = STAGE30_11_6_DEFAULT_MAX_HARVEST,
    candidate_id_prefix: str = STAGE30_11_6_DEFAULT_CANDIDATE_ID_PREFIX,
) -> Stage30_11_6HarvestResult:
    """Harvest AT MOST ``max_harvest`` assembled candidates from ``events`` into a
    Stage 30.11.5-ready ``candidate_source``.

    Pure / deterministic apart from the injected assembler / flattener's own
    behavior; reads no env, no clock, no network (``created_at_utc`` is injected);
    reserves no dispatch, sends no Discord, writes no file, runs no daemon /
    ``while`` loop, and NEVER constructs a transport / dispatch sink / runner -- so
    the old ungated dispatch path can never be reached.

    Fail closed first: if ``max_harvest`` is not a positive ``int`` within the HARD
    cap the adapter raises ``Stage30_11_6CandidateHarvestError`` BEFORE driving the
    assembler over any event.

    Otherwise it pulls AT MOST ``max_harvest`` events (a single BOUNDED for-loop;
    it stops at the cap), and for each event:

      * stamps a deterministic run-scoped ``candidate_id``
        (``f"{candidate_id_prefix}{index:06d}"``) and calls the INJECTED
        ``assembler.assemble(event, candidate_id=...)`` inside a fail-closed guard
        -- a raise (or a ``None`` / non-record return) is a clean
        ``SKIPPED_ASSEMBLY_FAILED`` and yields NO candidate;
      * flattens the captured record to safe scalars via the INJECTED
        ``record_flattener`` inside a fail-closed guard -- a raise is a clean
        ``SKIPPED_PROJECTION_REJECTED`` and yields NO candidate;
      * validates + projects the flat fields via the committed Stage 30.11.6
        projection adapter -- a missing / malformed required field is a clean
        ``SKIPPED_PROJECTION_REJECTED`` and yields NO candidate, so a malformed
        candidate never reaches the Stage 30.11.5 transport;
      * on a clean projection accumulates the built
        ``Stage30_11_6CandidateProjection`` into the ``candidate_source``.

    The captured record is held transiently and only its flattened safe scalars
    survive onto the result; the deep record is never retained. ``KeyboardInterrupt``
    / ``SystemExit`` (``BaseException``) are NOT swallowed.
    """
    if not is_within_harvest_cap(max_harvest):
        # Fail closed on an out-of-bounds harvest budget: drive nothing, harvest
        # nothing. A caller-shape failure, not a per-event failure.
        raise Stage30_11_6CandidateHarvestError("INVALID_MAX_HARVEST")

    outcomes: List[Stage30_11_6CandidateHarvestOutcome] = []
    candidate_source: List[Stage30_11_6CandidateProjection] = []
    events_seen = 0
    skipped_assembly_failed = 0
    skipped_projection_rejected = 0

    for event in events:
        if events_seen >= max_harvest:
            break
        candidate_id = f"{candidate_id_prefix}{events_seen:06d}"
        events_seen += 1

        # ---- Drive the injected assembler boundary (capture, never dispatch) ----
        try:
            record = assembler.assemble(event, candidate_id=candidate_id)
        except Exception:
            # The injected assembler raised: a clean SKIPPED_ASSEMBLY_FAILED. No
            # record captured, so no projection is attempted. (A custom assembler
            # may raise; the committed Stage 27 chain is itself error-tolerant.)
            outcomes.append(
                _assembly_failed_outcome(created_at_utc=created_at_utc)
            )
            skipped_assembly_failed += 1
            continue
        if record is None:
            outcomes.append(
                _assembly_failed_outcome(created_at_utc=created_at_utc)
            )
            skipped_assembly_failed += 1
            continue

        # ---- Flatten the captured record to safe scalars (injected) ----
        try:
            flat_fields = record_flattener(record)
        except Exception:
            # The injected flattener raised: the captured record could not be
            # reduced to safe scalars -> a clean SKIPPED_PROJECTION_REJECTED.
            outcomes.append(
                _flatten_failed_outcome(created_at_utc=created_at_utc)
            )
            skipped_projection_rejected += 1
            continue

        # ---- Validate + project the flat fields (fail closed) ----
        projection_result = project_harvested_candidate(
            flat_fields, created_at_utc=created_at_utc
        )
        if (
            projection_result.projection_decision
            == PROJECTION_DECISION_PROJECTED
            and projection_result.projection is not None
        ):
            candidate_source.append(projection_result.projection)
            outcomes.append(
                Stage30_11_6CandidateHarvestOutcome(
                    candidate_id=projection_result.candidate_id,
                    token_mint=projection_result.token_mint,
                    harvest_decision=HARVEST_DECISION_HARVESTED,
                    harvest_reason=HARVEST_REASON_READY_FOR_LIVE_RUNNER,
                    projection_decision=(
                        projection_result.projection_decision
                    ),
                    projection_reason=projection_result.projection_reason,
                    rejected_field=projection_result.rejected_field,
                    created_at_utc=created_at_utc,
                )
            )
            continue

        # A captured record whose flat fields failed the fail-closed projection:
        # a clean SKIPPED_PROJECTION_REJECTED. It never becomes a candidate, so it
        # never reaches the Stage 30.11.5 runner / transport.
        outcomes.append(
            Stage30_11_6CandidateHarvestOutcome(
                candidate_id=projection_result.candidate_id,
                token_mint=projection_result.token_mint,
                harvest_decision=(
                    HARVEST_DECISION_SKIPPED_PROJECTION_REJECTED
                ),
                harvest_reason=HARVEST_REASON_PROJECTION_FAILED_CLOSED,
                projection_decision=projection_result.projection_decision,
                projection_reason=projection_result.projection_reason,
                rejected_field=projection_result.rejected_field,
                created_at_utc=created_at_utc,
            )
        )
        skipped_projection_rejected += 1

    summary = Stage30_11_6HarvestSummary(
        events_seen=events_seen,
        harvested=len(candidate_source),
        skipped_assembly_failed=skipped_assembly_failed,
        skipped_projection_rejected=skipped_projection_rejected,
        created_at_utc=created_at_utc,
    )
    return Stage30_11_6HarvestResult(
        outcomes=tuple(outcomes),
        candidate_source=tuple(candidate_source),
        summary=summary,
        created_at_utc=created_at_utc,
    )


__all__ = (
    "Stage30_11_6CandidateAssembler",
    "Stage30_11_6RecordFlattener",
    "Stage30_11_6CandidateHarvestError",
    "is_within_harvest_cap",
    "harvest_live_candidates",
)

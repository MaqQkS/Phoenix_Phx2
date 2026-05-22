"""Stage 27.6 live candidate assembler.

Pure / deterministic glue layer that chains the Stage 27.3 provider-
ingest composition, the Stage 27.4 measurement-context assembler,
the Stage 27.5 private-ping renderer / provenance builder, and the
Stage 27.5 dry-run artifact writer into a single deterministic
candidate package.

Stage 27.6 candidate assembly NEVER:

  * opens a network connection,
  * imports a Discord / Telegram / X-social / messaging library,
  * imports a network / RPC / DB / scheduler library,
  * reads the process environment,
  * persists a dedupe ledger,
  * enforces Stage 26 candidate policies,
  * promotes UNKNOWN / DISAGREE / USDC into the existing SOL
    calibration lane,
  * decides a trading verdict,
  * widens the closed-set vocabularies emitted by Stage 27.2 / 27.3
    / 27.4 / 27.5.

The assembler accepts a single ``ProviderIngestInputRecord`` (the
Stage 27.3 input shape -- tests synthesize these from fake provider
events) plus the injected source / clock / output-root surface and
returns one immutable ``Stage27_6LiveCandidateRecord``.

Closed-set ``candidate_status`` vocabulary (closed set):

  * ``ASSEMBLED``                 -- composition + measurement +
                                     render succeeded. No dry-run
                                     artifact was written because
                                     the caller passed
                                     ``write_artifacts=False``.
  * ``RENDERED_DRY_RUN``          -- composition + measurement +
                                     render + artifact write all
                                     succeeded for a SOL / USDC
                                     candidate.
  * ``SKIPPED_DUPLICATE``         -- run-local dedupe already saw
                                     this event in the current run.
  * ``SKIPPED_UNSUPPORTED_EVENT`` -- Stage 27.3 composition skipped
                                     the event (unsupported event
                                     kind).
  * ``SKIPPED_MISSING_TOKEN``     -- Stage 27.3 composition skipped
                                     the event (missing token mint
                                     on a supported event kind).
  * ``SUPPRESSED_UNKNOWN_PAIR``   -- Stage 27.2 classified UNKNOWN
                                     (or quote_asset UNKNOWN, or
                                     pair_detection UNRESOLVED).
                                     The dry-run ping is rendered
                                     SUPPRESSED but NEVER enters the
                                     existing SOL calibration lane.
  * ``SUPPRESSED_DISAGREE_PAIR``  -- Stage 27.2 classified DISAGREE.
                                     Same handling as UNKNOWN.
  * ``ARTIFACT_WRITE_FAILED``     -- the Stage 27.5 writer raised a
                                     typed ``Stage27_5ArtifactWriteError``
                                     subclass; the candidate carries
                                     the failure reason and NEVER
                                     becomes a successful live-ready
                                     verdict.
  * ``ERROR``                     -- any other unexpected failure;
                                     the candidate carries a typed
                                     reason and NEVER becomes a
                                     successful live-ready verdict.

This module imports only stdlib (``pathlib`` / ``typing``) plus
Stage 27.2, Stage 27.3, Stage 27.4, Stage 27.5, and Stage 27.6
production modules. It does NOT import Stage 21-26 production code,
does NOT import Stage 27.1 production code, does NOT import any
network / RPC / messaging / DB / scheduler / secrets-management
library, does NOT read the process environment, does NOT define a
CLI surface, and contains no top-level I/O.
"""

from __future__ import annotations

from pathlib import Path
from typing import NamedTuple, Optional

from PHX2.stage27.live_dedupe import (
    Stage27_6DedupeKey,
    Stage27_6RunLocalDedupe,
    make_dedupe_key,
)
from PHX2.stage27.live_measurement_context import (
    LiveMeasurementContextRecord,
    assemble_measurement_context,
)
from PHX2.stage27.live_provider_composition import (
    compose_provider_ingest_event,
)
from PHX2.stage27.pair_detection_constants import (
    PAIR_DETECTION_STATUS_DISAGREE,
)
from PHX2.stage27.price_ath_context_reader import (
    AthContextSource,
    MigrationContextSource,
    PriceContextSource,
    Stage27_4Clock,
    read_ath_context,
    read_migration_context,
    read_price_context,
)
from PHX2.stage27.private_ping_artifact_writer import (
    Stage27_5ArtifactWriteError,
    default_payload_filename,
    default_provenance_filename,
    write_dry_run_artifact_pair,
)
from PHX2.stage27.private_ping_models import (
    PingProvenanceArtifactRecord,
    PrivatePingPayloadRecord,
)
from PHX2.stage27.private_ping_provenance import (
    Stage27_5Clock,
    build_ping_provenance_artifact,
)
from PHX2.stage27.private_ping_renderer import (
    render_private_ping,
)
from PHX2.stage27.provider_ingest_models import (
    COMPOSITION_STATUS_CLASSIFIED_DISAGREE,
    COMPOSITION_STATUS_CLASSIFIED_UNKNOWN,
    COMPOSITION_STATUS_COMPOSED,
    COMPOSITION_STATUS_ERROR,
    COMPOSITION_STATUS_SKIPPED_MISSING_TOKEN,
    COMPOSITION_STATUS_SKIPPED_UNSUPPORTED_EVENT,
    ProviderIngestInputRecord,
    ProviderIngestOutputRecord,
)


# ---------------------------------------------------------------------------
# Stage 27.6 version axes
# ---------------------------------------------------------------------------


STAGE27_6_MINOR_VERSION: str = "27.6"
STAGE27_6_CANDIDATE_SCHEMA_VERSION: str = (
    "stage27_v0_live_candidate"
)


# ---------------------------------------------------------------------------
# candidate_status closed set
# ---------------------------------------------------------------------------


CANDIDATE_STATUS_ASSEMBLED: str = "ASSEMBLED"
CANDIDATE_STATUS_RENDERED_DRY_RUN: str = "RENDERED_DRY_RUN"
CANDIDATE_STATUS_SKIPPED_DUPLICATE: str = "SKIPPED_DUPLICATE"
CANDIDATE_STATUS_SKIPPED_UNSUPPORTED_EVENT: str = (
    "SKIPPED_UNSUPPORTED_EVENT"
)
CANDIDATE_STATUS_SKIPPED_MISSING_TOKEN: str = (
    "SKIPPED_MISSING_TOKEN"
)
CANDIDATE_STATUS_SUPPRESSED_UNKNOWN_PAIR: str = (
    "SUPPRESSED_UNKNOWN_PAIR"
)
CANDIDATE_STATUS_SUPPRESSED_DISAGREE_PAIR: str = (
    "SUPPRESSED_DISAGREE_PAIR"
)
CANDIDATE_STATUS_ARTIFACT_WRITE_FAILED: str = (
    "ARTIFACT_WRITE_FAILED"
)
CANDIDATE_STATUS_ERROR: str = "ERROR"


CANDIDATE_STATUS_VALUES: tuple[str, ...] = (
    CANDIDATE_STATUS_ASSEMBLED,
    CANDIDATE_STATUS_RENDERED_DRY_RUN,
    CANDIDATE_STATUS_SKIPPED_DUPLICATE,
    CANDIDATE_STATUS_SKIPPED_UNSUPPORTED_EVENT,
    CANDIDATE_STATUS_SKIPPED_MISSING_TOKEN,
    CANDIDATE_STATUS_SUPPRESSED_UNKNOWN_PAIR,
    CANDIDATE_STATUS_SUPPRESSED_DISAGREE_PAIR,
    CANDIDATE_STATUS_ARTIFACT_WRITE_FAILED,
    CANDIDATE_STATUS_ERROR,
)


# ---------------------------------------------------------------------------
# candidate_reason closed set
# ---------------------------------------------------------------------------


CANDIDATE_REASON_OK: str = "OK"
CANDIDATE_REASON_DUPLICATE_RUN_LOCAL: str = "DUPLICATE_RUN_LOCAL"
CANDIDATE_REASON_UNSUPPORTED_EVENT_KIND: str = (
    "UNSUPPORTED_EVENT_KIND"
)
CANDIDATE_REASON_MISSING_TOKEN_MINT: str = "MISSING_TOKEN_MINT"
CANDIDATE_REASON_UNKNOWN_PAIR_LIVE_SUPPRESSED: str = (
    "UNKNOWN_PAIR_LIVE_SUPPRESSED"
)
CANDIDATE_REASON_DISAGREE_PAIR_LIVE_SUPPRESSED: str = (
    "DISAGREE_PAIR_LIVE_SUPPRESSED"
)
CANDIDATE_REASON_RENDERED_OK: str = "RENDERED_OK"
CANDIDATE_REASON_RENDERED_WITH_WARNINGS: str = (
    "RENDERED_WITH_WARNINGS"
)
CANDIDATE_REASON_USDC_OBSERVE_ONLY: str = "USDC_OBSERVE_ONLY"
CANDIDATE_REASON_ARTIFACT_WRITE_REFUSED_UNSAFE_PATH: str = (
    "ARTIFACT_WRITE_REFUSED_UNSAFE_PATH"
)
CANDIDATE_REASON_ARTIFACT_WRITE_FAILED: str = (
    "ARTIFACT_WRITE_FAILED"
)
CANDIDATE_REASON_COMPOSITION_ERROR: str = "COMPOSITION_ERROR"
CANDIDATE_REASON_UNEXPECTED_ERROR: str = "UNEXPECTED_ERROR"


CANDIDATE_REASON_VALUES: tuple[str, ...] = (
    CANDIDATE_REASON_OK,
    CANDIDATE_REASON_DUPLICATE_RUN_LOCAL,
    CANDIDATE_REASON_UNSUPPORTED_EVENT_KIND,
    CANDIDATE_REASON_MISSING_TOKEN_MINT,
    CANDIDATE_REASON_UNKNOWN_PAIR_LIVE_SUPPRESSED,
    CANDIDATE_REASON_DISAGREE_PAIR_LIVE_SUPPRESSED,
    CANDIDATE_REASON_RENDERED_OK,
    CANDIDATE_REASON_RENDERED_WITH_WARNINGS,
    CANDIDATE_REASON_USDC_OBSERVE_ONLY,
    CANDIDATE_REASON_ARTIFACT_WRITE_REFUSED_UNSAFE_PATH,
    CANDIDATE_REASON_ARTIFACT_WRITE_FAILED,
    CANDIDATE_REASON_COMPOSITION_ERROR,
    CANDIDATE_REASON_UNEXPECTED_ERROR,
)


# ---------------------------------------------------------------------------
# Stage 27.6 sources bundle (injected at the boundary)
# ---------------------------------------------------------------------------


class Stage27_6Sources(NamedTuple):
    """Immutable bundle of injected Stage 27.6 boundary dependencies.

    Fields:

      * ``price_source``                 -- fulfils
                                            ``PriceContextSource``.
      * ``ath_source``                   -- fulfils
                                            ``AthContextSource``.
      * ``migration_source``             -- fulfils
                                            ``MigrationContextSource``.
      * ``stage27_4_clock``              -- fulfils
                                            ``Stage27_4Clock``.
      * ``stage27_5_clock``              -- fulfils
                                            ``Stage27_5Clock``.
      * ``price_staleness_threshold_seconds`` -- forwarded to
                                            ``read_price_context``.

    Stage 27.6 NEVER imports a real price / ATH / migration source.
    Real sources live OUTSIDE Stage 27.6 (Stage 27.7+ provider
    adapters). Tests synthesize deterministic fakes that fulfil the
    Stage 27.4 Protocol surface.
    """

    price_source: PriceContextSource
    ath_source: AthContextSource
    migration_source: MigrationContextSource
    stage27_4_clock: Stage27_4Clock
    stage27_5_clock: Stage27_5Clock
    price_staleness_threshold_seconds: int


# ---------------------------------------------------------------------------
# Stage 27.6 live candidate record
# ---------------------------------------------------------------------------


class Stage27_6LiveCandidateRecord(NamedTuple):
    """Immutable Stage 27.6 live candidate package.

    Carries the full deterministic chain output for a single event:
    the Stage 27.3 composition output, the Stage 27.4 measurement
    context (when one was attached), the Stage 27.5 rendered ping
    payload (when one was rendered), the Stage 27.5 provenance
    artifact (when one was built), the resolved dry-run artifact
    paths (when artifacts were written), the dedupe key (when one
    was constructed), and the closed-set
    ``candidate_status`` / ``candidate_reason`` verdict.

    Fields:

      * ``candidate_id``               -- caller-supplied stable
                                          candidate identifier.
                                          Tests pass deterministic
                                          ids; real callers may pass
                                          a Stage 27.1 run-scoped id.
      * ``run_id``                     -- caller-supplied; ``None``
                                          when not attached yet.
      * ``session_id``                 -- caller-supplied; ``None``
                                          when not attached yet.
      * ``candidate_schema_version``   -- locked Stage 27.6 schema
                                          version string.
      * ``candidate_status``           -- closed-set
                                          ``CANDIDATE_STATUS`` token.
      * ``candidate_reason``           -- closed-set
                                          ``CANDIDATE_REASON`` token.
      * ``ingest_output``              -- Stage 27.3 composition
                                          output for the event;
                                          always populated.
      * ``measurement_context``        -- Stage 27.4 combined
                                          measurement context;
                                          ``None`` when the chain
                                          skipped before measurement
                                          (duplicate / unsupported /
                                          missing token).
      * ``rendered_ping``              -- Stage 27.5 private ping
                                          payload; ``None`` when no
                                          render was attempted.
      * ``provenance_artifact``        -- Stage 27.5 provenance
                                          artifact record; ``None``
                                          when no provenance was
                                          built.
      * ``payload_artifact_path``      -- absolute ``Path`` to the
                                          written payload artifact;
                                          ``None`` when no write was
                                          attempted (or the write
                                          failed).
      * ``provenance_artifact_path``   -- absolute ``Path`` to the
                                          written provenance
                                          artifact; ``None`` when no
                                          write was attempted (or
                                          the write failed).
      * ``dedupe_key``                 -- the
                                          ``Stage27_6DedupeKey`` used
                                          for the dedupe lookup;
                                          ``None`` only when the
                                          chain bailed before the
                                          dedupe step (an
                                          unexpected-error case).
      * ``write_attempted``            -- ``True`` iff the assembler
                                          tried to write artifacts
                                          (i.e. the caller passed
                                          ``write_artifacts=True``
                                          and the chain reached the
                                          writer).
    """

    candidate_id: str
    run_id: Optional[str]
    session_id: Optional[str]
    candidate_schema_version: str
    candidate_status: str
    candidate_reason: str
    ingest_output: ProviderIngestOutputRecord
    measurement_context: Optional[LiveMeasurementContextRecord]
    rendered_ping: Optional[PrivatePingPayloadRecord]
    provenance_artifact: Optional[PingProvenanceArtifactRecord]
    payload_artifact_path: Optional[Path]
    provenance_artifact_path: Optional[Path]
    dedupe_key: Optional[Stage27_6DedupeKey]
    write_attempted: bool


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _build_measurement_context(
    ingest_output: ProviderIngestOutputRecord,
    sources: Stage27_6Sources,
) -> LiveMeasurementContextRecord:
    """Run the Stage 27.4 readers and assemble the combined context.

    Stage 27.4 readers already translate expected source failures
    into typed ``SOURCE_ERROR`` records, so this helper never
    catches a generic ``Exception`` itself -- a non-typed source
    failure should propagate to the assembler's outer try / except
    and surface as ``CANDIDATE_STATUS_ERROR``.
    """
    price_context = read_price_context(
        sources.price_source,
        ingest_output,
        clock=sources.stage27_4_clock,
        staleness_threshold_seconds=(
            sources.price_staleness_threshold_seconds
        ),
    )
    migration_context = read_migration_context(
        sources.migration_source,
        ingest_output,
        clock=sources.stage27_4_clock,
    )
    ath_context = read_ath_context(
        sources.ath_source,
        ingest_output,
        migration_record=migration_context,
        current_price_record=price_context,
    )
    return assemble_measurement_context(
        ingest_output,
        price_context,
        ath_context,
        migration_context,
    )


def _terminal_status_for_composition(
    ingest_output: ProviderIngestOutputRecord,
) -> Optional[tuple[str, str]]:
    """Return ``(status, reason)`` iff composition is non-COMPOSED.

    Composed outputs return ``None`` so the assembler proceeds to
    measurement / rendering. Stage 27.3 ``CLASSIFIED_UNKNOWN`` and
    ``CLASSIFIED_DISAGREE`` are NOT short-circuited here: the
    Stage 27.4 measurement context still attaches a record, the
    Stage 27.5 renderer still produces a SUPPRESSED ping payload,
    and the Stage 27.6 candidate carries that artifact through with
    a ``SUPPRESSED_*`` candidate_status. UNKNOWN / DISAGREE never
    become a successful live-ready verdict.
    """
    cs = ingest_output.composition_status
    if cs == COMPOSITION_STATUS_SKIPPED_UNSUPPORTED_EVENT:
        return (
            CANDIDATE_STATUS_SKIPPED_UNSUPPORTED_EVENT,
            CANDIDATE_REASON_UNSUPPORTED_EVENT_KIND,
        )
    if cs == COMPOSITION_STATUS_SKIPPED_MISSING_TOKEN:
        return (
            CANDIDATE_STATUS_SKIPPED_MISSING_TOKEN,
            CANDIDATE_REASON_MISSING_TOKEN_MINT,
        )
    if cs == COMPOSITION_STATUS_ERROR:
        return (
            CANDIDATE_STATUS_ERROR,
            CANDIDATE_REASON_COMPOSITION_ERROR,
        )
    return None


def _classify_rendered_candidate(
    ingest_output: ProviderIngestOutputRecord,
    rendered: PrivatePingPayloadRecord,
) -> tuple[str, str]:
    """Map a Stage 27.5 render verdict to a Stage 27.6 candidate
    status / reason.

    UNKNOWN / DISAGREE pairs are SUPPRESSED candidates regardless of
    whether the renderer wrote anything; SOL / USDC pairs are
    RENDERED_DRY_RUN. Stage 27.6 NEVER promotes UNKNOWN / DISAGREE
    to a successful live-ready verdict.
    """
    cs = ingest_output.composition_status
    if cs == COMPOSITION_STATUS_CLASSIFIED_DISAGREE or (
        ingest_output.pair_detection_status
        == PAIR_DETECTION_STATUS_DISAGREE
    ):
        return (
            CANDIDATE_STATUS_SUPPRESSED_DISAGREE_PAIR,
            CANDIDATE_REASON_DISAGREE_PAIR_LIVE_SUPPRESSED,
        )
    if cs == COMPOSITION_STATUS_CLASSIFIED_UNKNOWN:
        return (
            CANDIDATE_STATUS_SUPPRESSED_UNKNOWN_PAIR,
            CANDIDATE_REASON_UNKNOWN_PAIR_LIVE_SUPPRESSED,
        )
    # Composed (SOL or USDC). Pick the candidate_reason from the
    # Stage 27.5 render verdict.
    from PHX2.stage27.private_ping_models import (
        RENDER_STATUS_RENDERED,
        RENDER_STATUS_RENDERED_OBSERVE_ONLY,
        RENDER_STATUS_RENDERED_WITH_WARNINGS,
    )

    if rendered.render_status == RENDER_STATUS_RENDERED:
        return (
            CANDIDATE_STATUS_RENDERED_DRY_RUN,
            CANDIDATE_REASON_RENDERED_OK,
        )
    if (
        rendered.render_status
        == RENDER_STATUS_RENDERED_OBSERVE_ONLY
    ):
        return (
            CANDIDATE_STATUS_RENDERED_DRY_RUN,
            CANDIDATE_REASON_USDC_OBSERVE_ONLY,
        )
    if (
        rendered.render_status
        == RENDER_STATUS_RENDERED_WITH_WARNINGS
    ):
        return (
            CANDIDATE_STATUS_RENDERED_DRY_RUN,
            CANDIDATE_REASON_RENDERED_WITH_WARNINGS,
        )
    # Any other render status (RENDERED_SUPPRESSED / RENDERED_UNSUPPORTED)
    # on a COMPOSED ingest output is a defensive fallback to
    # SUPPRESSED_UNKNOWN_PAIR -- the upstream Stage 27.5 renderer
    # only emits these on a non-COMPOSED chain, so this branch is
    # not expected to fire in practice.
    return (
        CANDIDATE_STATUS_SUPPRESSED_UNKNOWN_PAIR,
        CANDIDATE_REASON_UNKNOWN_PAIR_LIVE_SUPPRESSED,
    )


# ---------------------------------------------------------------------------
# Public assembler
# ---------------------------------------------------------------------------


def assemble_live_candidate(
    ingest_input: ProviderIngestInputRecord,
    sources: Stage27_6Sources,
    dedupe: Stage27_6RunLocalDedupe,
    *,
    candidate_id: str,
    output_root: Optional[Path] = None,
    run_id: Optional[str] = None,
    session_id: Optional[str] = None,
    ping_id: Optional[str] = None,
    write_artifacts: bool = True,
) -> Stage27_6LiveCandidateRecord:
    """Chain Stage 27.3 -> 27.4 -> 27.5 for a single ingest input.

    Returns one immutable ``Stage27_6LiveCandidateRecord``. The
    function never raises a Stage 27.3 / 27.4 / 27.5 typed error to
    the caller -- every typed failure resolves to a closed-set
    candidate_status + candidate_reason so the bounded runner's
    per-event loop never crashes.

    Argument discipline:

      * ``ingest_input``     -- a ``ProviderIngestInputRecord``
                                synthesized by the caller; tests
                                synthesize fakes directly, real
                                callers may run the Stage 27.3
                                adapter first.
      * ``sources``          -- injected Stage 27.4 source / clock
                                bundle plus the Stage 27.5 clock.
      * ``dedupe``           -- run-local dedupe ledger. The
                                assembler records the dedupe key
                                exactly once per non-duplicate
                                event; a duplicate is short-
                                circuited.
      * ``candidate_id``     -- caller-supplied non-empty string.
      * ``output_root``      -- pre-existing directory under which
                                Stage 27.5 dry-run artifacts are
                                written. Required when
                                ``write_artifacts=True``.
      * ``run_id``           -- caller-supplied; forwarded to the
                                Stage 27.5 renderer / provenance
                                builder. ``None`` when not attached.
      * ``session_id``       -- as above.
      * ``ping_id``          -- caller-supplied stable ping id;
                                defaults to ``candidate_id`` when
                                ``None`` so the dry-run filename
                                stays deterministic.
      * ``write_artifacts``  -- ``True`` to write the Stage 27.5
                                dry-run artifact pair, ``False`` to
                                skip the writer entirely (the chain
                                still composes / measures / renders
                                / builds provenance, but the
                                candidate_status stays ``ASSEMBLED``).

    Pure / deterministic except for:

      * the injected Stage 27.4 / 27.5 clock reads,
      * the injected Stage 27.4 source reads,
      * the single ``Path.write_bytes`` per artifact when
        ``write_artifacts=True``.
    """
    if not isinstance(ingest_input, ProviderIngestInputRecord):
        raise TypeError(
            "assemble_live_candidate requires a "
            "ProviderIngestInputRecord"
        )
    if not isinstance(sources, Stage27_6Sources):
        raise TypeError(
            "assemble_live_candidate requires a Stage27_6Sources"
        )
    if not isinstance(dedupe, Stage27_6RunLocalDedupe):
        raise TypeError(
            "assemble_live_candidate requires a "
            "Stage27_6RunLocalDedupe"
        )
    if not isinstance(candidate_id, str) or candidate_id == "":
        raise ValueError(
            "assemble_live_candidate requires a non-empty "
            "candidate_id"
        )
    if write_artifacts and output_root is None:
        raise ValueError(
            "assemble_live_candidate requires output_root when "
            "write_artifacts=True"
        )
    chosen_ping_id = ping_id if ping_id is not None else candidate_id

    try:
        ingest_output = compose_provider_ingest_event(ingest_input)
    except Exception:
        return Stage27_6LiveCandidateRecord(
            candidate_id=candidate_id,
            run_id=run_id,
            session_id=session_id,
            candidate_schema_version=(
                STAGE27_6_CANDIDATE_SCHEMA_VERSION
            ),
            candidate_status=CANDIDATE_STATUS_ERROR,
            candidate_reason=CANDIDATE_REASON_COMPOSITION_ERROR,
            ingest_output=_empty_ingest_output_placeholder(
                ingest_input
            ),
            measurement_context=None,
            rendered_ping=None,
            provenance_artifact=None,
            payload_artifact_path=None,
            provenance_artifact_path=None,
            dedupe_key=None,
            write_attempted=False,
        )

    dedupe_key = make_dedupe_key(
        token_mint=ingest_output.token_mint,
        pair_type=ingest_output.pair_pair_type,
        event_kind=ingest_output.event_kind,
        normalized_event_id=ingest_output.normalized_event_id,
        provider_event_id=ingest_output.provider_event_id,
    )
    if dedupe.is_duplicate(dedupe_key):
        return Stage27_6LiveCandidateRecord(
            candidate_id=candidate_id,
            run_id=run_id,
            session_id=session_id,
            candidate_schema_version=(
                STAGE27_6_CANDIDATE_SCHEMA_VERSION
            ),
            candidate_status=CANDIDATE_STATUS_SKIPPED_DUPLICATE,
            candidate_reason=CANDIDATE_REASON_DUPLICATE_RUN_LOCAL,
            ingest_output=ingest_output,
            measurement_context=None,
            rendered_ping=None,
            provenance_artifact=None,
            payload_artifact_path=None,
            provenance_artifact_path=None,
            dedupe_key=dedupe_key,
            write_attempted=False,
        )

    terminal = _terminal_status_for_composition(ingest_output)
    if terminal is not None:
        dedupe.record(dedupe_key)
        return Stage27_6LiveCandidateRecord(
            candidate_id=candidate_id,
            run_id=run_id,
            session_id=session_id,
            candidate_schema_version=(
                STAGE27_6_CANDIDATE_SCHEMA_VERSION
            ),
            candidate_status=terminal[0],
            candidate_reason=terminal[1],
            ingest_output=ingest_output,
            measurement_context=None,
            rendered_ping=None,
            provenance_artifact=None,
            payload_artifact_path=None,
            provenance_artifact_path=None,
            dedupe_key=dedupe_key,
            write_attempted=False,
        )

    try:
        measurement_context = _build_measurement_context(
            ingest_output, sources
        )
    except Exception:
        dedupe.record(dedupe_key)
        return Stage27_6LiveCandidateRecord(
            candidate_id=candidate_id,
            run_id=run_id,
            session_id=session_id,
            candidate_schema_version=(
                STAGE27_6_CANDIDATE_SCHEMA_VERSION
            ),
            candidate_status=CANDIDATE_STATUS_ERROR,
            candidate_reason=CANDIDATE_REASON_UNEXPECTED_ERROR,
            ingest_output=ingest_output,
            measurement_context=None,
            rendered_ping=None,
            provenance_artifact=None,
            payload_artifact_path=None,
            provenance_artifact_path=None,
            dedupe_key=dedupe_key,
            write_attempted=False,
        )

    try:
        rendered = render_private_ping(
            measurement_context,
            ping_id=chosen_ping_id,
            run_id=run_id,
            session_id=session_id,
        )
    except Exception:
        dedupe.record(dedupe_key)
        return Stage27_6LiveCandidateRecord(
            candidate_id=candidate_id,
            run_id=run_id,
            session_id=session_id,
            candidate_schema_version=(
                STAGE27_6_CANDIDATE_SCHEMA_VERSION
            ),
            candidate_status=CANDIDATE_STATUS_ERROR,
            candidate_reason=CANDIDATE_REASON_UNEXPECTED_ERROR,
            ingest_output=ingest_output,
            measurement_context=measurement_context,
            rendered_ping=None,
            provenance_artifact=None,
            payload_artifact_path=None,
            provenance_artifact_path=None,
            dedupe_key=dedupe_key,
            write_attempted=False,
        )

    try:
        provenance = build_ping_provenance_artifact(
            rendered, sources.stage27_5_clock
        )
    except Exception:
        dedupe.record(dedupe_key)
        return Stage27_6LiveCandidateRecord(
            candidate_id=candidate_id,
            run_id=run_id,
            session_id=session_id,
            candidate_schema_version=(
                STAGE27_6_CANDIDATE_SCHEMA_VERSION
            ),
            candidate_status=CANDIDATE_STATUS_ERROR,
            candidate_reason=CANDIDATE_REASON_UNEXPECTED_ERROR,
            ingest_output=ingest_output,
            measurement_context=measurement_context,
            rendered_ping=rendered,
            provenance_artifact=None,
            payload_artifact_path=None,
            provenance_artifact_path=None,
            dedupe_key=dedupe_key,
            write_attempted=False,
        )

    classified_status, classified_reason = (
        _classify_rendered_candidate(ingest_output, rendered)
    )

    if not write_artifacts:
        dedupe.record(dedupe_key)
        # SOL / USDC ASSEMBLED states (write_artifacts=False) collapse
        # to ASSEMBLED. SUPPRESSED_* / SKIPPED_* statuses keep their
        # terminal classification even when no artifact is written.
        if classified_status == CANDIDATE_STATUS_RENDERED_DRY_RUN:
            final_status = CANDIDATE_STATUS_ASSEMBLED
            final_reason = classified_reason
        else:
            final_status = classified_status
            final_reason = classified_reason
        return Stage27_6LiveCandidateRecord(
            candidate_id=candidate_id,
            run_id=run_id,
            session_id=session_id,
            candidate_schema_version=(
                STAGE27_6_CANDIDATE_SCHEMA_VERSION
            ),
            candidate_status=final_status,
            candidate_reason=final_reason,
            ingest_output=ingest_output,
            measurement_context=measurement_context,
            rendered_ping=rendered,
            provenance_artifact=provenance,
            payload_artifact_path=None,
            provenance_artifact_path=None,
            dedupe_key=dedupe_key,
            write_attempted=False,
        )

    # Record before writing so a later writer-failure path does not
    # leave the dedupe ledger inconsistent with the seen-events set.
    dedupe.record(dedupe_key)

    try:
        payload_filename = default_payload_filename(
            rendered.ping_id
        )
        provenance_filename = default_provenance_filename(
            rendered.ping_id
        )
        payload_path, provenance_path = write_dry_run_artifact_pair(
            rendered,
            provenance,
            output_root,  # type: ignore[arg-type]
            payload_filename=payload_filename,
            provenance_filename=provenance_filename,
            overwrite=False,
        )
    except Stage27_5ArtifactWriteError:
        return Stage27_6LiveCandidateRecord(
            candidate_id=candidate_id,
            run_id=run_id,
            session_id=session_id,
            candidate_schema_version=(
                STAGE27_6_CANDIDATE_SCHEMA_VERSION
            ),
            candidate_status=CANDIDATE_STATUS_ARTIFACT_WRITE_FAILED,
            candidate_reason=CANDIDATE_REASON_ARTIFACT_WRITE_FAILED,
            ingest_output=ingest_output,
            measurement_context=measurement_context,
            rendered_ping=rendered,
            provenance_artifact=provenance,
            payload_artifact_path=None,
            provenance_artifact_path=None,
            dedupe_key=dedupe_key,
            write_attempted=True,
        )
    except Exception:
        return Stage27_6LiveCandidateRecord(
            candidate_id=candidate_id,
            run_id=run_id,
            session_id=session_id,
            candidate_schema_version=(
                STAGE27_6_CANDIDATE_SCHEMA_VERSION
            ),
            candidate_status=CANDIDATE_STATUS_ERROR,
            candidate_reason=CANDIDATE_REASON_UNEXPECTED_ERROR,
            ingest_output=ingest_output,
            measurement_context=measurement_context,
            rendered_ping=rendered,
            provenance_artifact=provenance,
            payload_artifact_path=None,
            provenance_artifact_path=None,
            dedupe_key=dedupe_key,
            write_attempted=True,
        )

    # Final terminal status: SUPPRESSED_* / SKIPPED_* keep their
    # classification even after a successful write so an UNKNOWN /
    # DISAGREE candidate never gets relabelled as a successful live-
    # ready candidate.
    return Stage27_6LiveCandidateRecord(
        candidate_id=candidate_id,
        run_id=run_id,
        session_id=session_id,
        candidate_schema_version=(
            STAGE27_6_CANDIDATE_SCHEMA_VERSION
        ),
        candidate_status=classified_status,
        candidate_reason=classified_reason,
        ingest_output=ingest_output,
        measurement_context=measurement_context,
        rendered_ping=rendered,
        provenance_artifact=provenance,
        payload_artifact_path=payload_path,
        provenance_artifact_path=provenance_path,
        dedupe_key=dedupe_key,
        write_attempted=True,
    )


def _empty_ingest_output_placeholder(
    ingest_input: ProviderIngestInputRecord,
) -> ProviderIngestOutputRecord:
    """Return a placeholder Stage 27.3 output for an unexpected error.

    Only used in the defensive ``compose_provider_ingest_event``
    failure branch. The Stage 27.3 composer is itself pure /
    deterministic and does not raise on bad event_kind / missing
    token; this placeholder exists so the candidate record always
    carries a non-``None`` ``ingest_output`` field.
    """
    from PHX2.stage27.pair_detection_constants import (
        BONDING_CURVE_VERSION_UNKNOWN,
        CALIBRATION_LANE_UNKNOWN_PAIR_OBSERVE_ONLY,
        LIVE_POLICY_LIVE_SUPPRESS_UNKNOWN,
        PAIR_DETECTION_CONFIDENCE_NONE,
        PAIR_DETECTION_REASON_NO_EVIDENCE,
        PAIR_DETECTION_STATUS_UNRESOLVED,
        PAIR_TYPE_UNKNOWN,
        QUOTE_ASSET_UNKNOWN,
    )
    from PHX2.stage27.provider_ingest_models import (
        COMPOSITION_REASON_INVALID_INPUT_SHAPE,
        STAGE27_3_SCHEMA_VERSION,
    )

    return ProviderIngestOutputRecord(
        provider_id=ingest_input.provider_id,
        provider_event_id=ingest_input.provider_event_id,
        normalized_event_id=ingest_input.normalized_event_id,
        event_kind=ingest_input.event_kind,
        observed_at_utc=ingest_input.observed_at_utc,
        token_mint=ingest_input.token_mint,
        quote_mint=ingest_input.quote_mint,
        pair_quote_asset=QUOTE_ASSET_UNKNOWN,
        pair_pair_type=PAIR_TYPE_UNKNOWN,
        pair_bonding_curve_version=BONDING_CURVE_VERSION_UNKNOWN,
        pair_detection_status=PAIR_DETECTION_STATUS_UNRESOLVED,
        pair_detection_confidence=PAIR_DETECTION_CONFIDENCE_NONE,
        pair_detection_reason=PAIR_DETECTION_REASON_NO_EVIDENCE,
        pair_live_policy=LIVE_POLICY_LIVE_SUPPRESS_UNKNOWN,
        pair_calibration_lane=(
            CALIBRATION_LANE_UNKNOWN_PAIR_OBSERVE_ONLY
        ),
        raw_capture_ref=ingest_input.raw_capture_ref,
        source_summary=ingest_input.source_summary,
        composition_status=COMPOSITION_STATUS_ERROR,
        composition_reason=COMPOSITION_REASON_INVALID_INPUT_SHAPE,
        schema_version=STAGE27_3_SCHEMA_VERSION,
    )

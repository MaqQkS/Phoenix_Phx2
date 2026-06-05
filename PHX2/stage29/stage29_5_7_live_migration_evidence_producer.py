"""Stage 29.5.7 live migration evidence producer + projection.

The bounded, offline PRODUCER that drives the Stage 29.5.7
normalizer over a sequence of raw Helius confirmed-transaction
envelopes and the pure PROJECTION that maps a proven PRESENT
Stage 29.5 migration evidence record onto the sanitized per-mint
summary the committed Stage 30.11.9 / Stage 30.11.8 seam
consumes.

The producer is the operator's live-capture entry point: at the
SEPARATE, explicitly operator-authorized ceremony, an
out-of-repo wrapper feeds harvested live raw envelopes (from a
real Helius WebSocket / RPC capture) into
:meth:`Stage29_5_7LiveMigrationEvidenceProducer.produce_migration_evidence`
and reads back the proven PRESENT evidence records + their
sanitized COMPLETE / SAFE / trailing-``Z`` summaries. In THIS
slice the envelopes are INJECTED (an offline fixture or the
operator's capture); the producer NEVER opens a connection.

The projection :func:`project_migration_evidence_to_sanitized_summary`
maps a PRESENT record's axes onto the Stage 30.11.9 evidence
field names BY VALUE (``base_mint`` -> ``token_mint``;
``migration_timestamp_utc`` -> ``migration_event_time_utc``;
``source_event_ref`` -> ``source_ref``), stamps
``measurement_status=COMPLETE`` (a proven on-chain ``create_pool``
migration is a COMPLETE migration measurement) +
``redaction_status=SAFE`` (the evidence carries only public chain
data) + an explicit empty ``warnings=()``, and carries the
migration anchor VERBATIM (never reformatted). It maps to COMPLETE
ONLY when every required evidence field exists (the full quartet +
a populated anchor + slot + signature + source ref); any
incomplete / non-PRESENT record fails closed to ``None``. The
ATH / drawdown dimension is judged SEPARATELY and LATER by the
Stage 30.11.7 enrichment, so this COMPLETE summary alone never
reaches transport.

This slice imports NO Stage 30 module: the sanitized summary is
the Stage-29.5.7-owned adaptation target whose field names mirror
the Stage 30.11.9 record BY VALUE, so the operator wrapper (or the
composition test) feeds it to the committed Stage 30.11.9
``build_evidence_record_from_sanitized_projection`` mapper at the
ceremony boundary -- exactly as the Stage 30.11.7 / 30.11.8 / 30.5.3
seams plug their real sources in by value.

Discipline:

  * Stdlib only (``typing``). No ``datetime`` / ``time`` (the clock
    is caller-injected; the anchor is record-carried).
  * Imports ONLY the Stage 29.5 migration-models module, the Stage
    29.5.7 models sibling, and the Stage 29.5.7 normalizer sibling.
    No Stage 30 import. No Stage 21-28 import. No Stage 29.3 / 29.4
    import.
  * No ``os.environ`` / ``os.getenv`` access; no env read.
  * No network, no HTTP, no gRPC, no WebSocket, no socket. The
    envelopes are INJECTED.
  * No module-body Call (no implicit I/O at import time; only the
    ``@dataclass(...)`` decorators).
  * No legacy pre-PHX2 import path.
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from typing import Callable, Iterable, List, Optional, Tuple

from PHX2.stage29.stage29_5_migration_models import (
    MIGRATION_STATUS_PRESENT,
    Stage29_5MigrationEvidenceRecord,
)
from PHX2.stage29.stage29_5_7_helius_raw_migration_models import (
    NORMALIZATION_OUTCOME_MIGRATION_PROVEN,
    STAGE29_5_7_MEASUREMENT_STATUS_COMPLETE,
    STAGE29_5_7_REDACTION_STATUS_SAFE,
    Stage29_5_7MigrationNormalizationResult,
    Stage29_5_7SanitizedMigrationEvidenceSummary,
    is_nonblank_str,
    is_nonneg_int,
)
from PHX2.stage29.stage29_5_7_helius_raw_migration_normalizer import (
    normalize_helius_raw_migration_envelope,
)


# ---------------------------------------------------------------------------
# Producer bounds
# ---------------------------------------------------------------------------


STAGE29_5_7_PRODUCER_DEFAULT_MAX_ENVELOPES_TO_SCAN: int = 64
STAGE29_5_7_PRODUCER_HARD_MAX_ENVELOPES_TO_SCAN: int = 1024


# ---------------------------------------------------------------------------
# Pure projection: PRESENT Stage 29.5 evidence -> sanitized COMPLETE summary
# ---------------------------------------------------------------------------


def project_migration_evidence_to_sanitized_summary(
    record: object,
) -> Optional[Stage29_5_7SanitizedMigrationEvidenceSummary]:
    """Map a PRESENT Stage 29.5 migration evidence record onto a sanitized
    COMPLETE / SAFE / trailing-``Z`` / explicit-empty-warnings summary, or fail
    closed to ``None``.

    Pure / total; never raises. FABRICATES nothing and NEVER cleans a bad value
    into a good one. Emits a ``measurement_status=COMPLETE`` summary ONLY when the
    record is a genuine PRESENT reading with EVERY required evidence field
    populated:

      * a ``Stage29_5MigrationEvidenceRecord`` with
        ``migration_status == PRESENT``;
      * the full quartet (``base_mint`` / ``pool_account`` /
        ``pool_program_id`` / ``quote_mint``) populated;
      * a populated ``migration_timestamp_utc`` (carried VERBATIM as the anchor --
        never reformatted, so a non-trailing-``Z`` anchor stays exactly as recorded
        and the Stage 30.11.8 confirmation rejects it);
      * a populated ``migration_slot`` (a proven on-chain migration carries its
        slot);
      * a non-blank ``migration_signature`` + ``source_event_ref`` (provenance).

    Any non-``Stage29_5MigrationEvidenceRecord``, any non-PRESENT status, or any
    missing required field -> ``None`` (no confirmable summary). The summary's
    ``warnings`` is an explicit ``()`` (a proven complete migration has no
    anomaly); ``measurement_status`` is ``COMPLETE`` and ``redaction_status`` is
    ``SAFE`` (the evidence carries only public chain data). The ATH / drawdown
    dimension is judged LATER by the Stage 30.11.7 enrichment.
    """
    if not isinstance(record, Stage29_5MigrationEvidenceRecord):
        return None
    if record.migration_status != MIGRATION_STATUS_PRESENT:
        return None
    if record.base_mint is None or not is_nonblank_str(record.base_mint):
        return None
    if record.pool_account is None:
        return None
    if record.pool_program_id is None:
        return None
    if record.quote_mint is None:
        return None
    if not is_nonblank_str(record.migration_timestamp_utc):
        return None
    if not is_nonneg_int(record.migration_slot):
        return None
    if not is_nonblank_str(record.migration_signature):
        return None
    if not is_nonblank_str(record.source_event_ref):
        return None
    return Stage29_5_7SanitizedMigrationEvidenceSummary(
        token_mint=record.base_mint,
        measurement_status=STAGE29_5_7_MEASUREMENT_STATUS_COMPLETE,
        # Carry the migration anchor VERBATIM; never reformat a non-Z anchor into
        # a passing one (the Stage 30.11.8 confirmation owns the trailing-Z check).
        migration_event_time_utc=record.migration_timestamp_utc,
        warnings=(),
        redaction_status=STAGE29_5_7_REDACTION_STATUS_SAFE,
        source_ref=record.source_event_ref,
    )


# ---------------------------------------------------------------------------
# Producer proof tally + run-result models
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Stage29_5_7ProducerSummary:
    """Immutable Stage 29.5.7 producer proof tally.

    A passive summary of one bounded production pass. Counts only; carries a
    caller-injected timestamp.

      * ``envelopes_seen``     -- raw envelopes taken from the bounded source.
      * ``migrations_proven``  -- count that normalized to a PRESENT migration.
      * ``rejected``           -- count that failed closed (no evidence).
      * ``created_at_utc``     -- caller-injected ISO-8601 UTC timestamp.
    """

    envelopes_seen: int
    migrations_proven: int
    rejected: int
    created_at_utc: str


@dataclass(frozen=True)
class Stage29_5_7ProducerRunResult:
    """Immutable Stage 29.5.7 bounded production run result.

    The producer emits exactly one of these per bounded pass. It carries the
    ordered per-envelope normalization results, the proven PRESENT evidence
    records, their sanitized COMPLETE summaries, and the rolled-up summary tally.

      * ``outcomes``            -- the ordered per-envelope normalization results.
      * ``evidence_records``    -- the proven PRESENT Stage 29.5 evidence records.
      * ``sanitized_summaries`` -- the projected sanitized COMPLETE / SAFE
                                   summaries (Stage 30.11.9 shape BY VALUE).
      * ``summary``             -- the embedded ``Stage29_5_7ProducerSummary``.
      * ``created_at_utc``      -- caller-injected ISO-8601 UTC timestamp; NEVER a
                                   wall-clock read.
    """

    outcomes: Tuple[Stage29_5_7MigrationNormalizationResult, ...]
    evidence_records: Tuple[Stage29_5MigrationEvidenceRecord, ...]
    sanitized_summaries: Tuple[
        Stage29_5_7SanitizedMigrationEvidenceSummary, ...
    ]
    summary: Stage29_5_7ProducerSummary
    created_at_utc: str


# ---------------------------------------------------------------------------
# Public bounded producer
# ---------------------------------------------------------------------------


class Stage29_5_7LiveMigrationEvidenceProducer:
    """Bounded live migration evidence producer over injected raw envelopes.

    Construction takes:

      * an injected ``clock`` callable returning a UTC-shaped ISO-8601 string for
        each envelope's ``observed_at_utc`` stamp (the producer never reads a
        wall clock itself);
      * an optional ``max_envelopes_to_scan`` budget (default 64, capped at
        1024).

    :meth:`produce_migration_evidence` pulls AT MOST ``max_envelopes_to_scan``
    raw envelopes from the injected source, normalizes each via the Stage 29.5.7
    normalizer, collects the proven PRESENT evidence records + their sanitized
    COMPLETE summaries, tallies proven / rejected, and rolls up the counts.

    The producer reserves no dispatch, calls no transport, sends no private
    message, writes no file, reads no env / network, and NEVER constructs a
    runner / transport / dispatch sink -- so it can never reach a send surface.
    Producing evidence is never a bypass of the committed Stage 30.11.8
    confirmation / Stage 30.11.7 enrichment / Stage 30.9.3 dip gate; the
    confirmation still judges each summary, and the Stage 30.11.7 adapter still
    checks the ATH / drawdown dimension LATER.
    """

    __slots__ = ("_clock", "_max_envelopes_to_scan")

    def __init__(
        self,
        clock: Callable[[], str],
        max_envelopes_to_scan: int = (
            STAGE29_5_7_PRODUCER_DEFAULT_MAX_ENVELOPES_TO_SCAN
        ),
    ) -> None:
        if not callable(clock):
            raise ValueError(
                "Stage29_5_7LiveMigrationEvidenceProducer clock must be "
                "callable"
            )
        if (
            isinstance(max_envelopes_to_scan, bool)
            or not isinstance(max_envelopes_to_scan, int)
            or max_envelopes_to_scan < 1
            or max_envelopes_to_scan
            > STAGE29_5_7_PRODUCER_HARD_MAX_ENVELOPES_TO_SCAN
        ):
            raise ValueError(
                "Stage29_5_7LiveMigrationEvidenceProducer "
                "max_envelopes_to_scan must be an int in "
                f"[1, {STAGE29_5_7_PRODUCER_HARD_MAX_ENVELOPES_TO_SCAN}]"
            )
        self._clock: Callable[[], str] = clock
        self._max_envelopes_to_scan: int = max_envelopes_to_scan

    @property
    def max_envelopes_to_scan(self) -> int:
        """Return the bounded scan budget."""
        return self._max_envelopes_to_scan

    def produce_migration_evidence(
        self,
        envelopes: Iterable[object],
        created_at_utc: str,
    ) -> Stage29_5_7ProducerRunResult:
        """Scan AT MOST ``max_envelopes_to_scan`` raw envelopes and produce the
        proven migration evidence + sanitized summaries.

        Pure / deterministic apart from the injected clock's behavior. Never
        raises for a malformed envelope (each fails closed via the normalizer).
        ``created_at_utc`` stamps the run result; each envelope's
        ``observed_at_utc`` comes from ``clock()``.
        """
        outcomes: List[Stage29_5_7MigrationNormalizationResult] = []
        evidence_records: List[Stage29_5MigrationEvidenceRecord] = []
        sanitized_summaries: List[
            Stage29_5_7SanitizedMigrationEvidenceSummary
        ] = []
        envelopes_seen = 0
        migrations_proven = 0
        rejected = 0

        for envelope in envelopes:
            if envelopes_seen >= self._max_envelopes_to_scan:
                break
            envelopes_seen += 1
            observed_at_utc = self._clock()
            result = normalize_helius_raw_migration_envelope(
                envelope, observed_at_utc
            )
            outcomes.append(result)
            if (
                result.outcome == NORMALIZATION_OUTCOME_MIGRATION_PROVEN
                and result.evidence_record is not None
            ):
                migrations_proven += 1
                evidence_records.append(result.evidence_record)
                summary = project_migration_evidence_to_sanitized_summary(
                    result.evidence_record
                )
                if summary is not None:
                    sanitized_summaries.append(summary)
            else:
                rejected += 1

        producer_summary = Stage29_5_7ProducerSummary(
            envelopes_seen=envelopes_seen,
            migrations_proven=migrations_proven,
            rejected=rejected,
            created_at_utc=created_at_utc,
        )
        return Stage29_5_7ProducerRunResult(
            outcomes=tuple(outcomes),
            evidence_records=tuple(evidence_records),
            sanitized_summaries=tuple(sanitized_summaries),
            summary=producer_summary,
            created_at_utc=created_at_utc,
        )


# ---------------------------------------------------------------------------
# Field-name helpers (pure; read dataclass field names)
# ---------------------------------------------------------------------------


def producer_summary_field_names() -> Tuple[str, ...]:
    """Return the producer summary field names as a tuple."""
    return tuple(f.name for f in fields(Stage29_5_7ProducerSummary))


def producer_run_result_field_names() -> Tuple[str, ...]:
    """Return the producer run-result field names as a tuple."""
    return tuple(f.name for f in fields(Stage29_5_7ProducerRunResult))


__all__ = (
    "STAGE29_5_7_PRODUCER_DEFAULT_MAX_ENVELOPES_TO_SCAN",
    "STAGE29_5_7_PRODUCER_HARD_MAX_ENVELOPES_TO_SCAN",
    "project_migration_evidence_to_sanitized_summary",
    "Stage29_5_7ProducerSummary",
    "Stage29_5_7ProducerRunResult",
    "Stage29_5_7LiveMigrationEvidenceProducer",
    "producer_summary_field_names",
    "producer_run_result_field_names",
)

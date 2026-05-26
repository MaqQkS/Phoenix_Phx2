"""Stage 29.5.2 offline integration proof composition module.

Stage 29.5.2 closes the offline composition gap between the
Stage 29.5 migration evidence join layer + private ping context
projection and a Stage 29.3-shaped candidate context, without
opening any live transport and without wiring the composition
into the Stage 29.3 or Stage 29.4 runtime path.

The Stage 29.5.2 composition is exercised exclusively via the
Stage 29.5.2 test surface. The Stage 29.3 mode-3 orchestrator
continues to inject ``Stage29_3NoMigrationEvidenceSource`` and
does not consume this composition at runtime; the Stage 29.5
boundary test pin
``test_stage29_3_mode3_uses_stage29_5_projection_or_explicitly_marks_not_integrated``
remains green by construction (this file edits no Stage 29.3
production source). Likewise the Stage 29.4 soak orchestrator's
pass-entrypoint contract is unchanged; threading the projection
through a soak pass is deferred to Stage 29.5.3.

Composition data flow:

  candidate axes
    + synthetic migration evidence records (test fixtures only)
    + synthetic / fake Stage 27.4 ATH context (test fixtures only)
    + deterministic clock + optional time window
       -> join_candidate_to_migration_evidence()
       -> project_private_ping_migration_context()
       -> Stage29_5_2OfflineIntegrationResult

The single public function ``run_stage29_5_2_offline_integration``
is pure: same inputs => same output. It never mutates its inputs.
It only raises ``ValueError`` for caller-shape violations (e.g.
wrong record type, non-callable clock); valid join + projection
inputs always produce a closed-set result.

Discipline:

  * No env reads. ``os.environ`` / ``os.getenv`` / ``os.environb``
    are never touched.
  * No outbound network. No urllib / requests / httpx / aiohttp /
    websockets / websocket / http.client / socket / grpc / asyncio
    import.
  * No third-party runtime dependency. Imports only stdlib
    (``dataclasses`` / ``typing``) plus the Stage 29.5 join +
    projection + models surfaces and the Stage 27.4 ATH context
    NamedTuple read-only.
  * No top-level Call (no implicit I/O at import time).
  * No PHX1 import.
  * No Stage 21..26 import.
  * No Stage 28 import.
  * No Stage 29.1 / 29.2 / 29.3 / 29.4 import.
  * No Discord / Telegram / X / social / webhook / Helius /
    Chainstack / Birdeye / Dexscreener / Pump.fun reference.
  * No enforcement / routing / trading / wallet / signer surface.
  * No new env name. No new third-party runtime dependency.
  * ``filter_enforcement_status`` flows through verbatim from the
    Stage 29.5 projection -- the composition never overrides the
    locked ``NOT_ACTIVE_STAGE_29_PENDING`` token.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional, Sequence, Tuple

from PHX2.stage27.price_ath_context_models import (
    AthContextRecord,
)
from PHX2.stage29.stage29_5_candidate_to_migration_join import (
    Stage29_5CandidateAxes,
    join_candidate_to_migration_evidence,
)
from PHX2.stage29.stage29_5_migration_models import (
    FILTER_ENFORCEMENT_STATUS_NOT_ACTIVE_STAGE_29_PENDING,
    REDACTION_STATUS_SAFE,
    Stage29_5MigrationEvidenceRecord,
    Stage29_5MigrationJoinRecord,
    Stage29_5PrivatePingMigrationContext,
)
from PHX2.stage29.stage29_5_private_ping_context_projection import (
    project_private_ping_migration_context,
)


# ---------------------------------------------------------------------------
# Stage 29.5.2 schema version pin
# ---------------------------------------------------------------------------


STAGE29_5_2_OFFLINE_INTEGRATION_SCHEMA_VERSION: str = (
    "stage29_5_2_v0_offline_integration"
)


# ---------------------------------------------------------------------------
# Stage 29.5.2 error type (thin; never raised out of the public
# function on valid inputs)
# ---------------------------------------------------------------------------


class Stage29_5_2OfflineIntegrationError(ValueError):
    """Raised on caller-shape violations only.

    The Stage 29.5 join and projection are pure functions that
    return closed-set verdicts for every valid input pair; the
    composition layer therefore never re-raises a domain error
    from the join or the projection.

    This subclass exists solely so caller-shape violations at the
    composition boundary can be distinguished from underlying
    Stage 29.5 join / projection ``ValueError`` instances. The
    composition function does NOT catch the underlying records'
    own ``ValueError`` validators; those still propagate
    unchanged.
    """


# ---------------------------------------------------------------------------
# Stage 29.5.2 offline integration result record
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Stage29_5_2OfflineIntegrationResult:
    """Immutable Stage 29.5.2 offline integration result.

    Echoes the candidate axes the caller supplied, the
    Stage 29.5 join verdict, and the Stage 29.5 private ping
    migration context projection. Carries no extra dispatch
    surface, no router fields, no trading / signer fields, no
    webhook URL, no raw payload, no secret.

    The record is read-only audit material; the composition layer
    is observational only and never gates dispatch.

    Validators enforce:

      * ``candidate_axes_echoed`` is a Stage29_5CandidateAxes.
      * ``join_record`` is a Stage29_5MigrationJoinRecord.
      * ``private_ping_context`` is a
        Stage29_5PrivatePingMigrationContext.
      * ``filter_enforcement_status`` is the locked
        ``NOT_ACTIVE_STAGE_29_PENDING`` token (echoed from the
        projection -- the composition never overrides it).
      * ``redaction_status`` is the closed-set ``SAFE`` token
        (the composition never carries raw payloads / secrets,
        so the record is always SAFE).
      * ``schema_version`` is the locked Stage 29.5.2 version
        string.
    """

    candidate_axes_echoed: Stage29_5CandidateAxes
    join_record: Stage29_5MigrationJoinRecord
    private_ping_context: Stage29_5PrivatePingMigrationContext
    filter_enforcement_status: str
    redaction_status: str
    schema_version: str = (
        STAGE29_5_2_OFFLINE_INTEGRATION_SCHEMA_VERSION
    )

    def __post_init__(self) -> None:
        if not isinstance(
            self.candidate_axes_echoed, Stage29_5CandidateAxes
        ):
            raise Stage29_5_2OfflineIntegrationError(
                "Stage29_5_2OfflineIntegrationResult."
                "candidate_axes_echoed must be a "
                "Stage29_5CandidateAxes instance"
            )
        if not isinstance(
            self.join_record, Stage29_5MigrationJoinRecord
        ):
            raise Stage29_5_2OfflineIntegrationError(
                "Stage29_5_2OfflineIntegrationResult."
                "join_record must be a "
                "Stage29_5MigrationJoinRecord instance"
            )
        if not isinstance(
            self.private_ping_context,
            Stage29_5PrivatePingMigrationContext,
        ):
            raise Stage29_5_2OfflineIntegrationError(
                "Stage29_5_2OfflineIntegrationResult."
                "private_ping_context must be a "
                "Stage29_5PrivatePingMigrationContext instance"
            )
        if (
            self.filter_enforcement_status
            != FILTER_ENFORCEMENT_STATUS_NOT_ACTIVE_STAGE_29_PENDING
        ):
            raise Stage29_5_2OfflineIntegrationError(
                "Stage29_5_2OfflineIntegrationResult."
                "filter_enforcement_status is locked to "
                "NOT_ACTIVE_STAGE_29_PENDING; got "
                f"{self.filter_enforcement_status!r}"
            )
        if self.redaction_status != REDACTION_STATUS_SAFE:
            raise Stage29_5_2OfflineIntegrationError(
                "Stage29_5_2OfflineIntegrationResult."
                "redaction_status must be SAFE; got "
                f"{self.redaction_status!r}"
            )
        if (
            self.schema_version
            != STAGE29_5_2_OFFLINE_INTEGRATION_SCHEMA_VERSION
        ):
            raise Stage29_5_2OfflineIntegrationError(
                "Stage29_5_2OfflineIntegrationResult."
                "schema_version is locked; got "
                f"{self.schema_version!r}"
            )
        # The projection itself locks its own
        # filter_enforcement_status; cross-check that the locked
        # token survived the composition (the composition copies
        # the projection's enforcement token verbatim, so this is
        # a defensive equality pin).
        if (
            self.private_ping_context.filter_enforcement_status
            != self.filter_enforcement_status
        ):
            raise Stage29_5_2OfflineIntegrationError(
                "Stage29_5_2OfflineIntegrationResult."
                "private_ping_context.filter_enforcement_status "
                "must equal the result's "
                "filter_enforcement_status"
            )


# ---------------------------------------------------------------------------
# Stage 29.5.2 offline composition entry point
# ---------------------------------------------------------------------------


def run_stage29_5_2_offline_integration(
    *,
    candidate_axes: Stage29_5CandidateAxes,
    evidence_records: Sequence[
        Stage29_5MigrationEvidenceRecord
    ],
    ath_context: Optional[AthContextRecord],
    clock: Callable[[], str],
    time_window_start_utc: Optional[str] = None,
    time_window_end_utc: Optional[str] = None,
    expected_pool_program_id: Optional[str] = None,
) -> Stage29_5_2OfflineIntegrationResult:
    """Run one Stage 29.5.2 offline integration composition pass.

    Composes the Stage 29.5 candidate-to-migration join + Stage
    29.5 private ping migration context projection over the
    caller-supplied candidate axes, synthetic migration evidence
    sequence, optional Stage 27.4 ATH context record, and a
    deterministic clock.

    Returns a :class:`Stage29_5_2OfflineIntegrationResult`
    carrying the candidate axes echoed, the join verdict, the
    projection, the locked enforcement token, the SAFE redaction
    token, and the Stage 29.5.2 schema version.

    The function:

      * NEVER opens a network connection.
      * NEVER reads ``os.environ`` / ``os.getenv`` / ``os.environb``.
      * NEVER dispatches a private webhook / Discord / Telegram /
        X / social message.
      * NEVER activates Stage 26 / Stage 29 enforcement.
      * NEVER touches a wallet / private-key / signer surface.
      * NEVER sizes or executes a trade.
      * NEVER mutates its inputs (the Stage 29.5 join + projection
        are themselves pure; this composition wraps them without
        side effects).

    Raises:

      * :class:`Stage29_5_2OfflineIntegrationError` on caller-
        shape violations (wrong record type, non-callable clock,
        non-sequence ``evidence_records``).
      * ``ValueError`` from the underlying Stage 29.5 join /
        projection validators when an axis string is malformed,
        time window strings are malformed, or the clock returns a
        non-UTC-shaped string.
    """
    if not isinstance(candidate_axes, Stage29_5CandidateAxes):
        raise Stage29_5_2OfflineIntegrationError(
            "candidate_axes must be a Stage29_5CandidateAxes "
            "instance"
        )
    if isinstance(evidence_records, (str, bytes, bytearray)):
        raise Stage29_5_2OfflineIntegrationError(
            "evidence_records must be a sequence of "
            "Stage29_5MigrationEvidenceRecord; got a "
            f"{type(evidence_records).__name__} which is not a "
            "valid sequence shape"
        )
    try:
        evidence_tuple: Tuple[
            Stage29_5MigrationEvidenceRecord, ...
        ] = tuple(evidence_records)
    except TypeError as exc:
        raise Stage29_5_2OfflineIntegrationError(
            "evidence_records must be iterable"
        ) from exc
    for record in evidence_tuple:
        if not isinstance(
            record, Stage29_5MigrationEvidenceRecord
        ):
            raise Stage29_5_2OfflineIntegrationError(
                "evidence_records entries must each be "
                "Stage29_5MigrationEvidenceRecord instances; "
                f"got {type(record).__name__}"
            )
    if ath_context is not None and not isinstance(
        ath_context, AthContextRecord
    ):
        raise Stage29_5_2OfflineIntegrationError(
            "ath_context must be an AthContextRecord or None"
        )
    if not callable(clock):
        raise Stage29_5_2OfflineIntegrationError(
            "clock must be callable"
        )
    join_record = join_candidate_to_migration_evidence(
        candidate_axes=candidate_axes,
        evidence_records=evidence_tuple,
        clock=clock,
        time_window_start_utc=time_window_start_utc,
        time_window_end_utc=time_window_end_utc,
        expected_pool_program_id=expected_pool_program_id,
    )
    private_ping_context = (
        project_private_ping_migration_context(
            join_record=join_record,
            ath_context=ath_context,
            clock=clock,
        )
    )
    return Stage29_5_2OfflineIntegrationResult(
        candidate_axes_echoed=candidate_axes,
        join_record=join_record,
        private_ping_context=private_ping_context,
        filter_enforcement_status=(
            private_ping_context.filter_enforcement_status
        ),
        redaction_status=REDACTION_STATUS_SAFE,
    )


__all__ = (
    "STAGE29_5_2_OFFLINE_INTEGRATION_SCHEMA_VERSION",
    "Stage29_5_2OfflineIntegrationError",
    "Stage29_5_2OfflineIntegrationResult",
    "run_stage29_5_2_offline_integration",
)

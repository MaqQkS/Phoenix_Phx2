"""Stage 29.5.4 migration context source adapter.

Stage 29.5.4 unlocks one Stage 29.5.3 forbidden surface: direct,
opt-in injection of a Stage 29.5-shaped migration context source
into the Stage 29.3 private tradeable ping path. The Stage 27.6
candidate assembler today calls ``read_migration_snapshot(mint)``
on a Stage 27.4 ``MigrationContextSource`` Protocol instance; the
Stage 29.3 default injects ``Stage29_3NoMigrationEvidenceSource``
which always returns a deterministic ``MIGRATION_SOURCE_UNKNOWN``
snapshot. This adapter is an OPT-IN alternative the operator may
pass via the Stage 29.3 ``run_stage29_3_first_private_tradeable_smoke``
``migration_source`` kwarg.

The adapter wraps the existing Stage 29.5.2 offline integration
``run_stage29_5_2_offline_integration``: on each
``read_migration_snapshot(token_mint)`` call the adapter:

  1. validates ``token_mint`` against the Stage 29.5 safe-shape
     mint check; unsafe shapes degrade to a
     ``MIGRATION_SOURCE_UNKNOWN`` snapshot (NEVER raises);
  2. builds a ``Stage29_5CandidateAxes`` carrying ``base_mint``
     only (pool / quote axes wildcarded);
  3. fetches the Stage 29.5 evidence sequence via the
     operator-supplied ``evidence_provider``;
  4. fetches an optional Stage 27.4 ``AthContextRecord`` via the
     operator-supplied ``ath_context_provider``;
  5. runs ``run_stage29_5_2_offline_integration(...)``;
  6. projects the result onto a Stage 27.4 ``MigrationSourceSnapshot``
     using a closed-set, deliberately-conservative mapping (see
     the behavior matrix below).

Behavior matrix (closed-set; pinned by the Stage 29.5.4 test
surface):

  * ``COMPLETE`` + projection.migration_source in
    ``{HELIUS_WS, STAGE29_MIGRATION_ARTIFACT}`` + non-None
    ``migration_timestamp_utc``
      -> populated ``MigrationSourceSnapshot`` with
         ``migration_source = ON_CHAIN_MIGRATION_EVENT``,
         ``migration_event_id`` and ``source_event_ref`` echoed
         from the first matched evidence record (deterministic
         order set by the Stage 29.5 join layer),
         ``migration_timestamp_utc`` from the projection,
         ``raw_capture_ref = None`` (no raw payload ever carried).
  * ``COMPLETE`` with ``migration_source = SYNTHETIC_TEST_ONLY``
      -> ``MIGRATION_SOURCE_UNKNOWN`` snapshot (no spurious
         authority promotion for synthetic fixtures).
  * ``PARTIAL_MIGRATION_PRESENT``
      -> ``MIGRATION_SOURCE_UNKNOWN`` snapshot (the adapter NEVER
         surfaces half-valid migration timestamps as
         authoritative).
  * ``MISSING_MIGRATION`` / ``INVALID_MIGRATION`` /
    ``CONFLICTING_MIGRATION``
      -> ``MIGRATION_SOURCE_UNKNOWN`` snapshot.
  * Any internal exception (provider failure, integration
    caller-shape violation, projection validator failure, clock
    returning a malformed string)
      -> ``MIGRATION_SOURCE_UNKNOWN`` snapshot. ``read_migration_snapshot``
         is non-raising by contract: a Stage 29.5-aware adapter
         must never block Stage 27.6 / Stage 28.9 dispatch.

The adapter does NOT activate enforcement; the projection's
locked ``filter_enforcement_status = NOT_ACTIVE_STAGE_29_PENDING``
token flows through the offline integration unchanged. The
adapter does NOT modify Stage 29.3, Stage 29.4, or any Stage 29.5
production module. The adapter is consumed BY Stage 29.3 mode-3
when the operator explicitly passes an instance via the
``migration_source`` kwarg; default Stage 29.3 mode-3 continues
to inject ``Stage29_3NoMigrationEvidenceSource``.

Discipline:

  * No env reads. ``os.environ`` / ``os.getenv`` / ``os.environb``
    are never touched.
  * No outbound network. No urllib / requests / httpx / aiohttp /
    websockets / websocket / http.client / socket / grpc /
    asyncio import.
  * No third-party runtime dependency. Imports only stdlib
    (``typing``) plus the Stage 27.4 migration context vocabulary,
    the Stage 27.4 ``MigrationSourceSnapshot`` / ``AthContextRecord``
    NamedTuple shapes, the Stage 29.5 migration models, the
    Stage 29.5 join input ``Stage29_5CandidateAxes``, and the
    Stage 29.5.2 offline integration entrypoint.
  * No top-level Call (no implicit I/O at import time). The only
    module-body Call admitted is ``@dataclass(...)`` on class
    decorators; this module ships zero ``@dataclass`` classes
    and zero module-body Calls.
  * No Discord / Telegram / X / social / webhook / Helius /
    Chainstack / Birdeye / Dexscreener / Pump.fun reference.
  * No enforcement / routing / trading / wallet / signer surface.
  * No new env name. No new third-party runtime dependency.
  * No PHX1 import. No legacy phoenix-1 import path.
"""

from __future__ import annotations

from typing import (
    Callable,
    Optional,
    Protocol,
    Sequence,
    Tuple,
)

from PHX2.stage27.migration_context_models import (
    MIGRATION_SOURCE_ON_CHAIN_MIGRATION_EVENT,
    MIGRATION_SOURCE_UNKNOWN,
)
from PHX2.stage27.price_ath_context_models import (
    AthContextRecord,
)
from PHX2.stage27.price_ath_context_reader import (
    MigrationSourceSnapshot,
)
from PHX2.stage29.stage29_5_2_offline_integration import (
    Stage29_5_2OfflineIntegrationResult,
    run_stage29_5_2_offline_integration,
)
from PHX2.stage29.stage29_5_candidate_to_migration_join import (
    Stage29_5CandidateAxes,
)
from PHX2.stage29.stage29_5_migration_models import (
    MEASUREMENT_STATUS_COMPLETE,
    MIGRATION_SOURCE_HELIUS_WS,
    MIGRATION_SOURCE_STAGE29_MIGRATION_ARTIFACT,
    Stage29_5MigrationEvidenceRecord,
    is_safe_mint_or_pool_string,
)


# ---------------------------------------------------------------------------
# Stage 29.5.4 schema version pin
# ---------------------------------------------------------------------------


STAGE29_5_4_MIGRATION_CONTEXT_SOURCE_ADAPTER_SCHEMA_VERSION: str = (
    "stage29_5_4_v0_migration_context_source_adapter"
)


# ---------------------------------------------------------------------------
# Stage 29.5 -> Stage 27.4 trusted source mapping
# ---------------------------------------------------------------------------
#
# Stage 29.5 evidence migration_source closed-set:
#   * HELIUS_WS                  -- on-chain Pump AMM migration
#                                   captured via Helius WebSocket
#                                   (real provenance).
#   * STAGE29_MIGRATION_ARTIFACT -- on-chain migration captured
#                                   in a Stage 29.5 artifact file
#                                   (real provenance).
#   * SYNTHETIC_TEST_ONLY        -- test-only token; NEVER admitted
#                                   on the trusted mapping.
#   * UNKNOWN                    -- no provenance; NEVER admitted.
#
# The adapter promotes HELIUS_WS and STAGE29_MIGRATION_ARTIFACT to
# Stage 27.4 ``ON_CHAIN_MIGRATION_EVENT`` only on the COMPLETE
# branch. SYNTHETIC_TEST_ONLY and UNKNOWN always degrade to
# ``MIGRATION_SOURCE_UNKNOWN`` regardless of measurement status.


_STAGE29_5_TRUSTED_MIGRATION_SOURCES: Tuple[str, ...] = (
    MIGRATION_SOURCE_HELIUS_WS,
    MIGRATION_SOURCE_STAGE29_MIGRATION_ARTIFACT,
)


# ---------------------------------------------------------------------------
# Protocol surfaces (operator-supplied)
# ---------------------------------------------------------------------------


class Stage29_5_4MigrationEvidenceProvider(Protocol):
    """Operator-supplied callable returning the Stage 29.5
    migration evidence sequence for a single candidate ``token_mint``.

    Implementations may consult an in-memory list of evidence
    (test fixtures), a Stage 29.5 artifact reader's output, a
    Stage 29.5 Helius WS adapter's pre-captured records, or any
    other source the operator has wired upstream. The adapter
    calls this provider exactly once per
    ``read_migration_snapshot(token_mint)`` invocation.

    Implementations MUST return a sequence of
    ``Stage29_5MigrationEvidenceRecord`` instances (possibly
    empty). Exceptions raised by implementations are caught by
    the adapter and degrade to a ``MIGRATION_SOURCE_UNKNOWN``
    snapshot.
    """

    def __call__(
        self, token_mint: str,
    ) -> Sequence[Stage29_5MigrationEvidenceRecord]: ...


class Stage29_5_4AthContextProvider(Protocol):
    """Operator-supplied callable returning an optional Stage 27.4
    ``AthContextRecord`` for a single candidate ``token_mint``.

    Implementations may consult a Stage 27.4 ATH context reader
    over a Stage 29.2 Birdeye source, an offline ATH fixture, or
    any other source the operator has wired upstream. The adapter
    calls this provider exactly once per
    ``read_migration_snapshot(token_mint)`` invocation.

    Returning ``None`` is admitted and indicates the adapter has
    no ATH context for the mint; the Stage 29.5 projection will
    set ``post_migration_ath_verified = None`` in that case.
    Exceptions raised by implementations are caught by the
    adapter and degrade to a ``MIGRATION_SOURCE_UNKNOWN`` snapshot.
    """

    def __call__(
        self, token_mint: str,
    ) -> Optional[AthContextRecord]: ...


# ---------------------------------------------------------------------------
# Adapter class (Stage 27.4 ``MigrationContextSource`` Protocol)
# ---------------------------------------------------------------------------


class Stage29_5_4MigrationContextSourceAdapter:
    """Stage 27.4 ``MigrationContextSource`` Protocol adapter that
    bridges the Stage 29.5.2 offline integration into the Stage
    29.3 mode-3 private tradeable ping path.

    The adapter is OPT-IN: Stage 29.3 mode-3 only consumes it when
    the operator explicitly passes an instance via the
    ``run_stage29_3_first_private_tradeable_smoke`` ``migration_source``
    kwarg. Stage 29.3 default behavior remains
    ``Stage29_3NoMigrationEvidenceSource()``.

    The adapter is non-raising on ``read_migration_snapshot``:
    every internal exception (provider failure, offline
    integration caller-shape failure, projection validator
    failure, clock returning a malformed string) is caught and
    degrades to a deterministic ``MIGRATION_SOURCE_UNKNOWN``
    snapshot. This satisfies the Stage 27.6 candidate assembler's
    expectation that ``read_migration_snapshot`` never raises
    (the assembler's ``read_migration_context`` would otherwise
    surface ``CANDIDATE_STATUS_ERROR``).
    """

    __slots__ = (
        "_evidence_provider",
        "_ath_context_provider",
        "_clock",
        "_time_window_start_utc",
        "_time_window_end_utc",
        "_expected_pool_program_id",
    )

    def __init__(
        self,
        *,
        evidence_provider: Stage29_5_4MigrationEvidenceProvider,
        ath_context_provider: Stage29_5_4AthContextProvider,
        clock: Callable[[], str],
        time_window_start_utc: Optional[str] = None,
        time_window_end_utc: Optional[str] = None,
        expected_pool_program_id: Optional[str] = None,
    ) -> None:
        if not callable(evidence_provider):
            raise TypeError(
                "Stage29_5_4MigrationContextSourceAdapter."
                "evidence_provider must be callable"
            )
        if not callable(ath_context_provider):
            raise TypeError(
                "Stage29_5_4MigrationContextSourceAdapter."
                "ath_context_provider must be callable"
            )
        if not callable(clock):
            raise TypeError(
                "Stage29_5_4MigrationContextSourceAdapter."
                "clock must be callable"
            )
        if time_window_start_utc is not None and not isinstance(
            time_window_start_utc, str,
        ):
            raise TypeError(
                "Stage29_5_4MigrationContextSourceAdapter."
                "time_window_start_utc must be str or None"
            )
        if time_window_end_utc is not None and not isinstance(
            time_window_end_utc, str,
        ):
            raise TypeError(
                "Stage29_5_4MigrationContextSourceAdapter."
                "time_window_end_utc must be str or None"
            )
        if (
            expected_pool_program_id is not None
            and not isinstance(expected_pool_program_id, str)
        ):
            raise TypeError(
                "Stage29_5_4MigrationContextSourceAdapter."
                "expected_pool_program_id must be str or None"
            )
        self._evidence_provider = evidence_provider
        self._ath_context_provider = ath_context_provider
        self._clock = clock
        self._time_window_start_utc = time_window_start_utc
        self._time_window_end_utc = time_window_end_utc
        self._expected_pool_program_id = expected_pool_program_id

    def read_migration_snapshot(
        self, token_mint: str,
    ) -> MigrationSourceSnapshot:
        """Return a Stage 27.4 ``MigrationSourceSnapshot`` derived
        from the Stage 29.5.2 offline integration of the
        operator-supplied evidence + ATH context for ``token_mint``.

        Non-raising. All exceptions degrade to a deterministic
        ``MIGRATION_SOURCE_UNKNOWN`` snapshot.
        """
        try:
            return self._compute_snapshot(token_mint)
        except Exception:
            return _build_unknown_snapshot()

    # -----------------------------------------------------------------
    # Internal helpers
    # -----------------------------------------------------------------

    def _compute_snapshot(
        self, token_mint: object,
    ) -> MigrationSourceSnapshot:
        if not is_safe_mint_or_pool_string(token_mint):
            return _build_unknown_snapshot()
        # ``token_mint`` is a safe-shape printable string of
        # length 32..64 from this point on.
        candidate_axes = Stage29_5CandidateAxes(
            base_mint=token_mint,
        )
        evidence_sequence = self._evidence_provider(token_mint)
        ath_context = self._ath_context_provider(token_mint)
        result = run_stage29_5_2_offline_integration(
            candidate_axes=candidate_axes,
            evidence_records=evidence_sequence,
            ath_context=ath_context,
            clock=self._clock,
            time_window_start_utc=self._time_window_start_utc,
            time_window_end_utc=self._time_window_end_utc,
            expected_pool_program_id=(
                self._expected_pool_program_id
            ),
        )
        return _project_result_to_snapshot(result)


# ---------------------------------------------------------------------------
# Module-private projection helpers
# ---------------------------------------------------------------------------


def _build_unknown_snapshot() -> MigrationSourceSnapshot:
    """Return the canonical Stage 27.4 ``MIGRATION_SOURCE_UNKNOWN``
    snapshot (every optional slot ``None``).
    """
    return MigrationSourceSnapshot(
        migration_event_id=None,
        migration_timestamp_utc=None,
        migration_source=MIGRATION_SOURCE_UNKNOWN,
        source_event_ref=None,
        raw_capture_ref=None,
    )


def _project_result_to_snapshot(
    result: Stage29_5_2OfflineIntegrationResult,
) -> MigrationSourceSnapshot:
    """Map a Stage 29.5.2 offline integration result onto a Stage
    27.4 ``MigrationSourceSnapshot`` using the Stage 29.5.4
    closed-set behavior matrix.

    Returns the canonical ``MIGRATION_SOURCE_UNKNOWN`` snapshot for
    every measurement-status branch except ``COMPLETE`` with a
    trusted Stage 29.5 ``migration_source`` and a non-None
    ``migration_timestamp_utc``. NEVER surfaces a half-valid
    timestamp as authoritative.
    """
    projection = result.private_ping_context
    if projection.measurement_status != MEASUREMENT_STATUS_COMPLETE:
        return _build_unknown_snapshot()
    if (
        projection.migration_source
        not in _STAGE29_5_TRUSTED_MIGRATION_SOURCES
    ):
        return _build_unknown_snapshot()
    if projection.migration_timestamp_utc is None:
        # Defensive: a COMPLETE projection should always carry the
        # timestamp, but the adapter is the last gate before the
        # Stage 27.4 reader sees the snapshot and we must NEVER
        # surface a half-valid migration timestamp as
        # authoritative.
        return _build_unknown_snapshot()
    migration_event_id: Optional[str] = None
    source_event_ref: Optional[str] = None
    matched = result.join_record.matched_evidence
    if matched:
        first = matched[0]
        migration_event_id = first.migration_signature
        source_event_ref = first.source_event_ref
    return MigrationSourceSnapshot(
        migration_event_id=migration_event_id,
        migration_timestamp_utc=(
            projection.migration_timestamp_utc
        ),
        migration_source=(
            MIGRATION_SOURCE_ON_CHAIN_MIGRATION_EVENT
        ),
        source_event_ref=source_event_ref,
        raw_capture_ref=None,
    )


# ---------------------------------------------------------------------------
# Public surface
# ---------------------------------------------------------------------------


__all__ = (
    "STAGE29_5_4_MIGRATION_CONTEXT_SOURCE_ADAPTER_SCHEMA_VERSION",
    "Stage29_5_4MigrationEvidenceProvider",
    "Stage29_5_4AthContextProvider",
    "Stage29_5_4MigrationContextSourceAdapter",
)

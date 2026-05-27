"""Stage 29.5.5 migration context recorder.

The Stage 29.5.5 recording adapter implements the Stage 27.4
``MigrationContextSource`` Protocol with the same constructor
shape as the Stage 29.5.4 adapter, plus an OPTIONAL renderer
callable. On each ``read_migration_snapshot(token_mint)`` call
the recorder runs in TWO ISOLATED PHASES:

Phase 1 (snapshot computation) -- may degrade to UNKNOWN:

  1. validates ``token_mint`` against the Stage 29.5 safe-shape
     mint check; unsafe shapes degrade to a
     ``MIGRATION_SOURCE_UNKNOWN`` snapshot (NEVER raises and
     NEVER records an entry);
  2. builds a ``Stage29_5CandidateAxes`` carrying ``base_mint``
     only (pool / quote axes wildcarded);
  3. fetches the Stage 29.5 evidence sequence via the operator-
     supplied ``evidence_provider``;
  4. fetches an optional Stage 27.4 ``AthContextRecord`` via the
     operator-supplied ``ath_context_provider``;
  5. runs ``run_stage29_5_2_offline_integration(...)`` to
     compute the Stage 29.5
     ``Stage29_5PrivatePingMigrationContext`` projection;
  6. projects the result onto a Stage 27.4
     ``MigrationSourceSnapshot`` using the SAME closed-set
     mapping the Stage 29.5.4 adapter uses (COMPLETE + trusted
     migration_source + non-None migration_timestamp_utc ->
     populated ON_CHAIN_MIGRATION_EVENT snapshot; everything
     else -> MIGRATION_SOURCE_UNKNOWN snapshot).

Phase 2 (rendering + recording) -- side-channel only,
NEVER alters the Phase 1 snapshot:

  When a ``renderer`` callable is wired into the recorder's
  constructor AND Phase 1 produced a usable projection, the
  recorder renders the projection AND records a
  ``Stage29_5_5RecordedRenderEntry`` on the recorder's
  in-memory ``_recorded_entries`` list. Any Phase 2 failure
  (renderer raising, renderer returning a non-block, rendered
  block failing the closed-set / forbidden-substring
  validator, clock returning a non-UTC string for
  ``recorded_at_utc``, or any other exception) is SWALLOWED:

    * the Phase 1 snapshot is returned to the caller UNCHANGED,
    * no partial / unsafe entry is appended to
      ``_recorded_entries``,
    * no exception escapes the recorder.

Phase 1 failures (provider raising, offline integration
caller-shape violation, projection validator failure, clock
returning a malformed string for the projection's
``observed_at_utc``) still degrade to a deterministic
``MIGRATION_SOURCE_UNKNOWN`` snapshot and skip Phase 2
entirely.

When the operator omits ``renderer`` (the kwarg defaults to
``None``), the recorder skips Phase 2 entirely and behaves
byte-equivalently to a Stage 29.5.4 adapter on the Stage 27.4
snapshot axis (records ZERO entries). This satisfies the Stage
29.5.5 spec-lock requirement "Rendered migration context
should be computed/recorded only when explicitly passed."

Discipline:

  * No env reads. ``os.environ`` / ``os.getenv`` /
    ``os.environb`` are never touched.
  * No outbound network. No urllib / requests / httpx / aiohttp
    / websockets / websocket / http.client / socket / grpc /
    asyncio import.
  * Stdlib only (``typing``) plus the Stage 27.4 migration
    context vocabulary / ``MigrationSourceSnapshot`` /
    ``AthContextRecord``, the Stage 29.5 migration models +
    join input + offline integration entrypoint, and the Stage
    29.5.5 render models + renderer.
  * No top-level Call (no implicit I/O at import time). The
    only admitted module-body Call shape is ``@dataclass(...)``
    and this module ships zero ``@dataclass`` classes.
  * No legacy import path.
  * No Discord / Telegram / X / social / webhook / Helius /
    Chainstack / Birdeye / Pump.fun reference.
  * No enforcement / routing / trading / wallet / signer surface.
  * No new env name. No new third-party runtime dependency.
"""

from __future__ import annotations

from typing import (
    Callable,
    List,
    Optional,
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
    Stage29_5PrivatePingMigrationContext,
    is_safe_iso8601_utc_string,
    is_safe_mint_or_pool_string,
)
from PHX2.stage29.stage29_5_5_render_models import (
    Stage29_5_5RecordedRenderEntry,
    Stage29_5_5RenderedMigrationContextBlock,
    stage29_5_5_rendered_block_is_safe_for_serialization,
)


# ---------------------------------------------------------------------------
# Stage 29.5.5 schema version pin
# ---------------------------------------------------------------------------


STAGE29_5_5_MIGRATION_CONTEXT_RECORDER_SCHEMA_VERSION: str = (
    "stage29_5_5_v0_migration_context_recorder"
)


# ---------------------------------------------------------------------------
# Stage 29.5 -> Stage 27.4 trusted source mapping (mirrors the
# Stage 29.5.4 adapter's mapping verbatim).
# ---------------------------------------------------------------------------


_STAGE29_5_TRUSTED_MIGRATION_SOURCES: Tuple[str, ...] = (
    MIGRATION_SOURCE_HELIUS_WS,
    MIGRATION_SOURCE_STAGE29_MIGRATION_ARTIFACT,
)


# ---------------------------------------------------------------------------
# Recorder class (Stage 27.4 ``MigrationContextSource`` Protocol)
# ---------------------------------------------------------------------------


class Stage29_5_5MigrationContextRecorder:
    """Stage 27.4 ``MigrationContextSource`` Protocol recording
    adapter that bridges the Stage 29.5.2 offline integration
    into the Stage 29.3 mode-3 private tradeable ping path AND
    records a Stage 29.5.5 rendered migration context block per
    candidate when a renderer is wired into the constructor.

    The recorder is OPT-IN: Stage 29.3 mode-3 only consumes a
    recorder instance when the operator explicitly passes one
    via the existing Stage 29.5.4 ``migration_source`` kwarg on
    ``run_stage29_3_first_private_tradeable_smoke``. Stage 29.3
    default behavior (no kwarg) remains
    ``Stage29_3NoMigrationEvidenceSource()``.

    The recorder is non-raising on
    ``read_migration_snapshot``: every internal exception is
    caught and degrades to a deterministic
    ``MIGRATION_SOURCE_UNKNOWN`` snapshot.

    When the operator constructs the recorder WITHOUT a
    renderer (``renderer=None``), the recorder behaves byte-
    equivalently to a Stage 29.5.4 adapter on the Stage 27.4
    snapshot axis and records ZERO entries.
    """

    __slots__ = (
        "_evidence_provider",
        "_ath_context_provider",
        "_clock",
        "_renderer",
        "_time_window_start_utc",
        "_time_window_end_utc",
        "_expected_pool_program_id",
        "_recorded_entries",
    )

    def __init__(
        self,
        *,
        evidence_provider: Callable[
            [str], Sequence[Stage29_5MigrationEvidenceRecord]
        ],
        ath_context_provider: Callable[
            [str], Optional[AthContextRecord]
        ],
        clock: Callable[[], str],
        renderer: Optional[
            Callable[
                [Stage29_5PrivatePingMigrationContext],
                Stage29_5_5RenderedMigrationContextBlock,
            ]
        ] = None,
        time_window_start_utc: Optional[str] = None,
        time_window_end_utc: Optional[str] = None,
        expected_pool_program_id: Optional[str] = None,
    ) -> None:
        if not callable(evidence_provider):
            raise TypeError(
                "Stage29_5_5MigrationContextRecorder."
                "evidence_provider must be callable"
            )
        if not callable(ath_context_provider):
            raise TypeError(
                "Stage29_5_5MigrationContextRecorder."
                "ath_context_provider must be callable"
            )
        if not callable(clock):
            raise TypeError(
                "Stage29_5_5MigrationContextRecorder."
                "clock must be callable"
            )
        if renderer is not None and not callable(renderer):
            raise TypeError(
                "Stage29_5_5MigrationContextRecorder."
                "renderer must be callable or None"
            )
        if time_window_start_utc is not None and not isinstance(
            time_window_start_utc, str,
        ):
            raise TypeError(
                "Stage29_5_5MigrationContextRecorder."
                "time_window_start_utc must be str or None"
            )
        if time_window_end_utc is not None and not isinstance(
            time_window_end_utc, str,
        ):
            raise TypeError(
                "Stage29_5_5MigrationContextRecorder."
                "time_window_end_utc must be str or None"
            )
        if (
            expected_pool_program_id is not None
            and not isinstance(expected_pool_program_id, str)
        ):
            raise TypeError(
                "Stage29_5_5MigrationContextRecorder."
                "expected_pool_program_id must be str or None"
            )
        self._evidence_provider = evidence_provider
        self._ath_context_provider = ath_context_provider
        self._clock = clock
        self._renderer = renderer
        self._time_window_start_utc = time_window_start_utc
        self._time_window_end_utc = time_window_end_utc
        self._expected_pool_program_id = expected_pool_program_id
        self._recorded_entries: List[
            Stage29_5_5RecordedRenderEntry
        ] = []

    # -----------------------------------------------------------------
    # Stage 27.4 MigrationContextSource Protocol surface
    # -----------------------------------------------------------------

    def read_migration_snapshot(
        self, token_mint: str,
    ) -> MigrationSourceSnapshot:
        """Return a Stage 27.4 ``MigrationSourceSnapshot``
        derived from the Stage 29.5.2 offline integration of the
        operator-supplied evidence + ATH context for
        ``token_mint``; ADDITIONALLY when a renderer is wired
        into the recorder AND the snapshot computation
        succeeded, render the Stage 29.5 projection and record
        an entry capturing the projection + rendered block +
        projected snapshot.

        Non-raising. Runs in two ISOLATED phases:

          * Phase 1 (snapshot computation): any exception (bad
            mint shape, provider failure, offline integration
            caller-shape violation, projection validator
            rejection, clock returning a malformed string for
            ``observed_at_utc``) degrades the snapshot to
            ``MIGRATION_SOURCE_UNKNOWN`` AND skips Phase 2.
          * Phase 2 (side-channel render + record): any
            exception (renderer raising, renderer returning a
            wrong type, rendered block carrying a forbidden
            substring, clock returning a non-UTC string for
            ``recorded_at_utc``, ANY other failure) is
            SWALLOWED. The Phase 1 snapshot is returned
            UNCHANGED; no partial entry is appended; no
            exception escapes the recorder.

        Phase 2 NEVER alters Phase 1's snapshot return value:
        a renderer/recording failure on a trusted COMPLETE
        projection still surfaces the populated
        ``ON_CHAIN_MIGRATION_EVENT`` snapshot the Stage 29.5.4
        adapter would have produced for the same inputs.
        """
        # Phase 1 -- compute the snapshot. Any failure degrades
        # to UNKNOWN AND skips Phase 2 entirely.
        try:
            snapshot, projection = self._compute_snapshot(
                token_mint,
            )
        except Exception:
            return _build_unknown_snapshot()
        # Phase 2 -- render + record. Any failure is swallowed
        # WITHOUT altering the Phase 1 snapshot.
        if self._renderer is not None and projection is not None:
            try:
                self._render_and_record(
                    token_mint=token_mint,
                    projection=projection,
                    snapshot=snapshot,
                )
            except Exception:
                # Side-channel render/record failure must NEVER
                # alter the Stage 27.4 snapshot returned to the
                # Stage 27.6 candidate assembler. Silently skip
                # appending an entry for this call.
                pass
        return snapshot

    # -----------------------------------------------------------------
    # Stage 29.5.5 recorder-specific surface
    # -----------------------------------------------------------------

    @property
    def recorded_entries(
        self,
    ) -> Tuple[Stage29_5_5RecordedRenderEntry, ...]:
        """Return the recorded entries as an immutable tuple.

        When the recorder was constructed without a renderer,
        this tuple is always empty. When the recorder was
        constructed with a renderer, the tuple grows by one
        entry per successful render+record (Phase 2) execution;
        calls whose Phase 1 degrades to UNKNOWN OR whose Phase
        2 raises do NOT append an entry.
        """
        return tuple(self._recorded_entries)

    # -----------------------------------------------------------------
    # Internal helpers
    # -----------------------------------------------------------------

    def _compute_snapshot(
        self, token_mint: object,
    ) -> Tuple[
        MigrationSourceSnapshot,
        Optional[Stage29_5PrivatePingMigrationContext],
    ]:
        """Phase 1 -- compute the Stage 27.4 snapshot and, when
        available, return the Stage 29.5 projection alongside it
        for the optional Phase 2 render+record path.

        Returns ``(unknown_snapshot, None)`` on unsafe-shape
        ``token_mint`` (Phase 2 must be skipped in that case).
        Raises on any provider / offline-integration /
        projection-validator failure; ``read_migration_snapshot``
        catches the exception and degrades to UNKNOWN.
        """
        if not is_safe_mint_or_pool_string(token_mint):
            return (_build_unknown_snapshot(), None)
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
        snapshot = _project_result_to_snapshot(result)
        return (snapshot, result.private_ping_context)

    def _render_and_record(
        self,
        *,
        token_mint: str,
        projection: Stage29_5PrivatePingMigrationContext,
        snapshot: MigrationSourceSnapshot,
    ) -> None:
        """Phase 2 -- render the Stage 29.5 projection via the
        operator-wired renderer and append a recorded entry on
        success. Raises on any failure; the caller catches the
        exception and preserves the Phase 1 snapshot unchanged.
        """
        if self._renderer is None:
            # Defensive: the caller already gated on renderer
            # being not None; this branch is unreachable but
            # documents the invariant.
            return
        rendered_block = self._renderer(projection)
        if not isinstance(
            rendered_block,
            Stage29_5_5RenderedMigrationContextBlock,
        ):
            raise TypeError(
                "Stage29_5_5MigrationContextRecorder: "
                "renderer must return a "
                "Stage29_5_5RenderedMigrationContextBlock"
            )
        # Defense in depth -- the rendered block's
        # ``__post_init__`` already runs the full validation at
        # CONSTRUCTION time, but a malicious renderer may return
        # a freshly-constructed safe block and then mutate any
        # field via ``object.__setattr__`` AFTER construction.
        # ``stage29_5_5_rendered_block_is_safe_for_serialization``
        # re-runs EVERY ``__post_init__`` check (closed-set
        # tokens, echoed Stage 29.5 closed-set tokens, pinned
        # exact-value strings, pinned booleans, observed_at_utc
        # safe-shape, body_text non-emptiness, free-form types)
        # AND additionally re-scans EVERY string field that
        # reaches the side-channel JSON serializer for Stage
        # 29.5.5 forbidden substrings. The same shared helper is
        # called by the Stage 29.5.5 side-channel writer
        # immediately before serialization, so a post-recording
        # mutation cannot reach the artifact JSON either.
        if not stage29_5_5_rendered_block_is_safe_for_serialization(
            rendered_block,
        ):
            raise ValueError(
                "Stage29_5_5MigrationContextRecorder: rendered "
                "block failed full validation (closed-set / "
                "pinned-value / forbidden-substring check) "
                "immediately before recording; refusing to "
                "append a redaction-unsafe entry"
            )
        recorded_at_utc = self._clock()
        if not is_safe_iso8601_utc_string(recorded_at_utc):
            raise ValueError(
                "Stage29_5_5MigrationContextRecorder: "
                "clock returned a non-UTC-shaped string "
                "for recorded_at_utc"
            )
        entry = Stage29_5_5RecordedRenderEntry(
            token_mint=token_mint,
            projection=projection,
            rendered_block=rendered_block,
            snapshot=snapshot,
            recorded_at_utc=recorded_at_utc,
        )
        self._recorded_entries.append(entry)


# ---------------------------------------------------------------------------
# Module-private projection helpers (mirror the Stage 29.5.4
# adapter's mapping verbatim)
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
    """Map a Stage 29.5.2 offline integration result onto a
    Stage 27.4 ``MigrationSourceSnapshot`` using the same
    closed-set conservative mapping the Stage 29.5.4 adapter
    uses.

    Returns the canonical ``MIGRATION_SOURCE_UNKNOWN`` snapshot
    for every measurement-status branch except ``COMPLETE`` with
    a trusted Stage 29.5 ``migration_source`` and a non-None
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
    "STAGE29_5_5_MIGRATION_CONTEXT_RECORDER_SCHEMA_VERSION",
    "Stage29_5_5MigrationContextRecorder",
)

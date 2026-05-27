"""Stage 29.5.5 migration context recorder tests.

Pins:

  * The recorder rejects non-callable evidence_provider /
    ath_context_provider / clock with ``TypeError``.
  * The recorder rejects a non-callable, non-None ``renderer``
    with ``TypeError``.
  * The recorder rejects non-string time-window / pool-program
    args with ``TypeError``.
  * ``read_migration_snapshot`` is non-raising on every input.
  * Phase 1 failures (provider raise, clock returns bad
    ``observed_at_utc``, unsafe-shape token_mint) degrade to a
    Stage 27.4 ``MIGRATION_SOURCE_UNKNOWN`` snapshot.
  * Phase 2 failures (renderer raises, renderer returns a
    wrong type, rendered block fails forbidden-substring
    validation, clock returns bad ``recorded_at_utc``) NEVER
    alter the Phase 1 snapshot -- the trusted snapshot the
    Stage 29.5.4 adapter would have produced flows through
    UNCHANGED; no entry is appended.
  * Unsafe-shape ``token_mint`` -> UNKNOWN snapshot, ZERO
    entries recorded.
  * COMPLETE + trusted source + non-None timestamp ->
    ON_CHAIN_MIGRATION_EVENT snapshot (mirrors Stage 29.5.4
    adapter mapping).
  * COMPLETE + SYNTHETIC_TEST_ONLY -> UNKNOWN snapshot.
  * COMPLETE + UNKNOWN -> UNKNOWN snapshot.
  * Non-COMPLETE (PARTIAL / MISSING / INVALID / CONFLICTING) ->
    UNKNOWN snapshot.
  * When ``renderer is None``, the recorder records ZERO
    entries regardless of how many ``read_migration_snapshot``
    calls happen.
  * When ``renderer`` is wired, each successful Phase 2
    rendering appends exactly ONE entry to the recorder's
    ``recorded_entries`` tuple.
  * Recorded entries carry the projection, rendered block, and
    snapshot fields the recorder computed for that call.
  * ``recorded_entries`` returns an immutable tuple.
  * Failed reads (provider raises, etc.) do NOT append an
    entry.
"""

from __future__ import annotations

from typing import Optional, Sequence

import pytest

from PHX2.stage27.price_ath_context_models import (
    AthContextRecord,
)
from PHX2.stage27.price_ath_context_reader import (
    MigrationSourceSnapshot,
)
from PHX2.stage29.stage29_5_migration_models import (
    MIGRATION_SOURCE_HELIUS_WS,
    MIGRATION_SOURCE_STAGE29_MIGRATION_ARTIFACT,
    MIGRATION_SOURCE_SYNTHETIC_TEST_ONLY,
    MIGRATION_SOURCE_UNKNOWN_STAGE29_5,
    MIGRATION_STATUS_MISSING,
    MIGRATION_STATUS_PRESENT,
    Stage29_5MigrationEvidenceRecord,
)
from PHX2.stage29.stage29_5_5_migration_context_recorder import (
    STAGE29_5_5_MIGRATION_CONTEXT_RECORDER_SCHEMA_VERSION,
    Stage29_5_5MigrationContextRecorder,
)
from PHX2.stage29.stage29_5_5_private_discord_migration_context_renderer import (
    render_private_discord_migration_context_block,
)
from PHX2.stage29.stage29_5_5_render_models import (
    Stage29_5_5RecordedRenderEntry,
    Stage29_5_5RenderedMigrationContextBlock,
)


_OBSERVED_AT: str = "2026-01-01T00:00:00+00:00"
_MIGRATION_TS: str = "2026-01-01T00:00:05+00:00"
_BASE_MINT: str = "TestBaseMintAAAA1111111111111111111111111A"
_POOL_ACCOUNT: str = (
    "TestPoolXXXXXXX3333333333333333333333333X"
)
_POOL_PROGRAM_ID: str = (
    "PoolProgramIDDDDDDD22222222222222222222222D"
)
_QUOTE_MINT: str = (
    "QuoteMintEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEE"
)


def _present_helius_ws_evidence(
    *, token_mint: str = _BASE_MINT,
) -> Stage29_5MigrationEvidenceRecord:
    return Stage29_5MigrationEvidenceRecord(
        migration_status=MIGRATION_STATUS_PRESENT,
        migration_source=MIGRATION_SOURCE_HELIUS_WS,
        base_mint=token_mint,
        pool_account=_POOL_ACCOUNT,
        pool_program_id=_POOL_PROGRAM_ID,
        quote_mint=_QUOTE_MINT,
        migration_timestamp_utc=_MIGRATION_TS,
        migration_slot=12345,
        migration_signature=(
            "Sig" + "X" * 60
        ),
        observed_at_utc=_OBSERVED_AT,
        source_event_ref="evt-001",
    )


def _missing_evidence() -> Stage29_5MigrationEvidenceRecord:
    return Stage29_5MigrationEvidenceRecord(
        migration_status=MIGRATION_STATUS_MISSING,
        migration_source=MIGRATION_SOURCE_UNKNOWN_STAGE29_5,
        base_mint=None,
        pool_account=None,
        pool_program_id=None,
        quote_mint=None,
        migration_timestamp_utc=None,
        migration_slot=None,
        migration_signature=None,
        observed_at_utc=_OBSERVED_AT,
        source_event_ref=None,
    )


def _present_artifact_evidence(
    *, token_mint: str = _BASE_MINT,
) -> Stage29_5MigrationEvidenceRecord:
    return Stage29_5MigrationEvidenceRecord(
        migration_status=MIGRATION_STATUS_PRESENT,
        migration_source=(
            MIGRATION_SOURCE_STAGE29_MIGRATION_ARTIFACT
        ),
        base_mint=token_mint,
        pool_account=_POOL_ACCOUNT,
        pool_program_id=_POOL_PROGRAM_ID,
        quote_mint=_QUOTE_MINT,
        migration_timestamp_utc=_MIGRATION_TS,
        migration_slot=23456,
        migration_signature=(
            "Sig" + "Y" * 60
        ),
        observed_at_utc=_OBSERVED_AT,
        source_event_ref="evt-002",
    )


def _present_synthetic_evidence(
    *, token_mint: str = _BASE_MINT,
) -> Stage29_5MigrationEvidenceRecord:
    return Stage29_5MigrationEvidenceRecord(
        migration_status=MIGRATION_STATUS_PRESENT,
        migration_source=(
            MIGRATION_SOURCE_SYNTHETIC_TEST_ONLY
        ),
        base_mint=token_mint,
        pool_account=_POOL_ACCOUNT,
        pool_program_id=_POOL_PROGRAM_ID,
        quote_mint=_QUOTE_MINT,
        migration_timestamp_utc=_MIGRATION_TS,
        migration_slot=34567,
        migration_signature=(
            "Sig" + "Z" * 60
        ),
        observed_at_utc=_OBSERVED_AT,
        source_event_ref="evt-003",
    )


def _ath_context_post_migration_only(
    *, token_mint: str = _BASE_MINT,
) -> AthContextRecord:
    return AthContextRecord(
        token_mint=token_mint,
        pair_type="SOL_PAIR",
        quote_asset="SOL",
        ath_value="123.45",
        ath_unit="SOL",
        ath_source="birdeye",
        ath_observed_at_utc=(
            "2026-01-01T00:01:00+00:00"
        ),
        ath_since_migration_status=(
            "POST_MIGRATION_ONLY"
        ),
        drawdown_from_ath="0.1",
        drawdown_unit="ratio",
        drawdown_basis="last_price",
        ath_status="PRESENT",
        ath_reason="OK",
        schema_version="stage27_4_v0_ath_context",
    )


def _clock_factory(*timestamps: str):
    """Return a Callable that yields each given timestamp in
    order. Useful when we want to control the recorded_at_utc
    vs the projection observed_at_utc.
    """
    iterator = iter(timestamps)

    def clock() -> str:
        try:
            return next(iterator)
        except StopIteration:
            return timestamps[-1] if timestamps else (
                _OBSERVED_AT
            )

    return clock


def _build_recorder(
    *,
    evidence: Sequence[
        Stage29_5MigrationEvidenceRecord
    ] = (),
    ath_context: Optional[AthContextRecord] = None,
    with_renderer: bool = True,
    clock_timestamps: Sequence[str] = (
        _OBSERVED_AT,
        _OBSERVED_AT,
        _OBSERVED_AT,
        _OBSERVED_AT,
    ),
) -> Stage29_5_5MigrationContextRecorder:
    def evidence_provider(
        token_mint: str,
    ) -> Sequence[Stage29_5MigrationEvidenceRecord]:
        return tuple(evidence)

    def ath_context_provider(
        token_mint: str,
    ) -> Optional[AthContextRecord]:
        return ath_context

    return Stage29_5_5MigrationContextRecorder(
        evidence_provider=evidence_provider,
        ath_context_provider=ath_context_provider,
        clock=_clock_factory(*clock_timestamps),
        renderer=(
            render_private_discord_migration_context_block
            if with_renderer
            else None
        ),
    )


# ---------------------------------------------------------------------------
# Schema version
# ---------------------------------------------------------------------------


def test_recorder_schema_version_pin() -> None:
    assert (
        STAGE29_5_5_MIGRATION_CONTEXT_RECORDER_SCHEMA_VERSION
        == "stage29_5_5_v0_migration_context_recorder"
    )


# ---------------------------------------------------------------------------
# Constructor validation
# ---------------------------------------------------------------------------


def test_rejects_non_callable_evidence_provider() -> None:
    with pytest.raises(TypeError):
        Stage29_5_5MigrationContextRecorder(
            evidence_provider="not callable",  # type: ignore[arg-type]
            ath_context_provider=lambda m: None,
            clock=lambda: _OBSERVED_AT,
        )


def test_rejects_non_callable_ath_context_provider() -> None:
    with pytest.raises(TypeError):
        Stage29_5_5MigrationContextRecorder(
            evidence_provider=lambda m: (),
            ath_context_provider="not callable",  # type: ignore[arg-type]
            clock=lambda: _OBSERVED_AT,
        )


def test_rejects_non_callable_clock() -> None:
    with pytest.raises(TypeError):
        Stage29_5_5MigrationContextRecorder(
            evidence_provider=lambda m: (),
            ath_context_provider=lambda m: None,
            clock="not callable",  # type: ignore[arg-type]
        )


def test_rejects_non_callable_non_none_renderer() -> None:
    with pytest.raises(TypeError):
        Stage29_5_5MigrationContextRecorder(
            evidence_provider=lambda m: (),
            ath_context_provider=lambda m: None,
            clock=lambda: _OBSERVED_AT,
            renderer="not callable",  # type: ignore[arg-type]
        )


def test_accepts_none_renderer() -> None:
    rec = Stage29_5_5MigrationContextRecorder(
        evidence_provider=lambda m: (),
        ath_context_provider=lambda m: None,
        clock=lambda: _OBSERVED_AT,
        renderer=None,
    )
    assert rec.recorded_entries == ()


def test_rejects_non_string_time_window_start() -> None:
    with pytest.raises(TypeError):
        Stage29_5_5MigrationContextRecorder(
            evidence_provider=lambda m: (),
            ath_context_provider=lambda m: None,
            clock=lambda: _OBSERVED_AT,
            time_window_start_utc=12345,  # type: ignore[arg-type]
        )


def test_rejects_non_string_time_window_end() -> None:
    with pytest.raises(TypeError):
        Stage29_5_5MigrationContextRecorder(
            evidence_provider=lambda m: (),
            ath_context_provider=lambda m: None,
            clock=lambda: _OBSERVED_AT,
            time_window_end_utc=12345,  # type: ignore[arg-type]
        )


def test_rejects_non_string_expected_pool_program_id() -> None:
    with pytest.raises(TypeError):
        Stage29_5_5MigrationContextRecorder(
            evidence_provider=lambda m: (),
            ath_context_provider=lambda m: None,
            clock=lambda: _OBSERVED_AT,
            expected_pool_program_id=12345,  # type: ignore[arg-type]
        )


# ---------------------------------------------------------------------------
# read_migration_snapshot non-raising contract
# ---------------------------------------------------------------------------


def test_read_migration_snapshot_never_raises_on_unsafe_mint() -> None:
    rec = _build_recorder(with_renderer=True)
    snapshot = rec.read_migration_snapshot("short")
    assert snapshot.migration_source == "UNKNOWN"
    assert rec.recorded_entries == ()


def test_read_migration_snapshot_never_raises_on_provider_error() -> None:
    def evidence_provider(token_mint: str):
        raise RuntimeError("provider boom")

    rec = Stage29_5_5MigrationContextRecorder(
        evidence_provider=evidence_provider,
        ath_context_provider=lambda m: None,
        clock=lambda: _OBSERVED_AT,
        renderer=(
            render_private_discord_migration_context_block
        ),
    )
    snapshot = rec.read_migration_snapshot(_BASE_MINT)
    assert snapshot.migration_source == "UNKNOWN"
    assert rec.recorded_entries == ()


def test_read_migration_snapshot_never_raises_on_clock_error() -> None:
    def bad_clock():
        return "not-a-utc-string"

    rec = Stage29_5_5MigrationContextRecorder(
        evidence_provider=lambda m: (
            _present_helius_ws_evidence(),
        ),
        ath_context_provider=(
            lambda m: _ath_context_post_migration_only()
        ),
        clock=bad_clock,
        renderer=(
            render_private_discord_migration_context_block
        ),
    )
    snapshot = rec.read_migration_snapshot(_BASE_MINT)
    assert snapshot.migration_source == "UNKNOWN"
    assert rec.recorded_entries == ()


def test_read_migration_snapshot_never_raises_on_renderer_error() -> None:
    """Renderer failure is a Phase 2 (side-channel) failure that
    MUST NOT alter the Phase 1 snapshot. With trusted COMPLETE
    evidence, the Stage 27.4 snapshot stays
    ``ON_CHAIN_MIGRATION_EVENT`` even when the operator-supplied
    renderer raises.
    """
    def bad_renderer(projection):
        raise RuntimeError("renderer boom")

    rec = Stage29_5_5MigrationContextRecorder(
        evidence_provider=lambda m: (
            _present_helius_ws_evidence(),
        ),
        ath_context_provider=(
            lambda m: _ath_context_post_migration_only()
        ),
        clock=lambda: _OBSERVED_AT,
        renderer=bad_renderer,
    )
    snapshot = rec.read_migration_snapshot(_BASE_MINT)
    # Phase 1 succeeded -> trusted snapshot preserved. Phase 2
    # raised inside the renderer -> swallowed; no entry appended.
    assert (
        snapshot.migration_source
        == "ON_CHAIN_MIGRATION_EVENT"
    )
    assert snapshot.migration_timestamp_utc == _MIGRATION_TS
    assert rec.recorded_entries == ()


def test_read_migration_snapshot_never_raises_on_renderer_returning_wrong_type() -> None:
    """Renderer returning a non-block object is a Phase 2
    failure: the Phase 1 snapshot survives unchanged; no entry
    is appended.
    """
    def bad_renderer(projection) -> object:
        return "not-a-block"

    rec = Stage29_5_5MigrationContextRecorder(
        evidence_provider=lambda m: (
            _present_helius_ws_evidence(),
        ),
        ath_context_provider=(
            lambda m: _ath_context_post_migration_only()
        ),
        clock=lambda: _OBSERVED_AT,
        renderer=bad_renderer,
    )
    snapshot = rec.read_migration_snapshot(_BASE_MINT)
    assert (
        snapshot.migration_source
        == "ON_CHAIN_MIGRATION_EVENT"
    )
    assert snapshot.migration_timestamp_utc == _MIGRATION_TS
    assert rec.recorded_entries == ()


# ---------------------------------------------------------------------------
# Snapshot projection mapping (mirrors Stage 29.5.4 adapter)
# ---------------------------------------------------------------------------


def test_complete_helius_ws_produces_on_chain_event_snapshot() -> None:
    rec = _build_recorder(
        evidence=(_present_helius_ws_evidence(),),
        ath_context=_ath_context_post_migration_only(),
        with_renderer=True,
    )
    snapshot = rec.read_migration_snapshot(_BASE_MINT)
    assert (
        snapshot.migration_source
        == "ON_CHAIN_MIGRATION_EVENT"
    )
    assert snapshot.migration_timestamp_utc == _MIGRATION_TS


def test_complete_artifact_produces_on_chain_event_snapshot() -> None:
    rec = _build_recorder(
        evidence=(_present_artifact_evidence(),),
        ath_context=_ath_context_post_migration_only(),
        with_renderer=True,
    )
    snapshot = rec.read_migration_snapshot(_BASE_MINT)
    assert (
        snapshot.migration_source
        == "ON_CHAIN_MIGRATION_EVENT"
    )


def test_complete_synthetic_produces_unknown_snapshot() -> None:
    rec = _build_recorder(
        evidence=(_present_synthetic_evidence(),),
        ath_context=_ath_context_post_migration_only(),
        with_renderer=True,
    )
    snapshot = rec.read_migration_snapshot(_BASE_MINT)
    assert snapshot.migration_source == "UNKNOWN"


def test_missing_produces_unknown_snapshot() -> None:
    rec = _build_recorder(
        evidence=(_missing_evidence(),),
        ath_context=None,
        with_renderer=True,
    )
    snapshot = rec.read_migration_snapshot(_BASE_MINT)
    assert snapshot.migration_source == "UNKNOWN"


def test_no_evidence_produces_unknown_snapshot() -> None:
    rec = _build_recorder(
        evidence=(),
        ath_context=None,
        with_renderer=True,
    )
    snapshot = rec.read_migration_snapshot(_BASE_MINT)
    assert snapshot.migration_source == "UNKNOWN"


# ---------------------------------------------------------------------------
# Recording behavior gated on renderer presence
# ---------------------------------------------------------------------------


def test_recorder_without_renderer_records_zero_entries() -> None:
    rec = _build_recorder(
        evidence=(_present_helius_ws_evidence(),),
        ath_context=_ath_context_post_migration_only(),
        with_renderer=False,
    )
    snapshot = rec.read_migration_snapshot(_BASE_MINT)
    assert (
        snapshot.migration_source
        == "ON_CHAIN_MIGRATION_EVENT"
    )
    assert rec.recorded_entries == ()


def test_recorder_with_renderer_records_one_entry_per_call() -> None:
    rec = _build_recorder(
        evidence=(_present_helius_ws_evidence(),),
        ath_context=_ath_context_post_migration_only(),
        with_renderer=True,
    )
    rec.read_migration_snapshot(_BASE_MINT)
    assert len(rec.recorded_entries) == 1
    rec.read_migration_snapshot(_BASE_MINT)
    assert len(rec.recorded_entries) == 2


def test_recorded_entry_carries_projection_block_and_snapshot() -> None:
    rec = _build_recorder(
        evidence=(_present_helius_ws_evidence(),),
        ath_context=_ath_context_post_migration_only(),
        with_renderer=True,
    )
    rec.read_migration_snapshot(_BASE_MINT)
    entries = rec.recorded_entries
    assert len(entries) == 1
    entry = entries[0]
    assert isinstance(entry, Stage29_5_5RecordedRenderEntry)
    assert entry.token_mint == _BASE_MINT
    assert isinstance(
        entry.rendered_block,
        Stage29_5_5RenderedMigrationContextBlock,
    )
    assert isinstance(entry.snapshot, MigrationSourceSnapshot)


def test_recorded_entries_returns_tuple() -> None:
    rec = _build_recorder(
        evidence=(_present_helius_ws_evidence(),),
        ath_context=_ath_context_post_migration_only(),
        with_renderer=True,
    )
    rec.read_migration_snapshot(_BASE_MINT)
    entries = rec.recorded_entries
    assert isinstance(entries, tuple)


def test_recorded_entries_property_is_immutable_view() -> None:
    rec = _build_recorder(
        evidence=(_present_helius_ws_evidence(),),
        ath_context=_ath_context_post_migration_only(),
        with_renderer=True,
    )
    rec.read_migration_snapshot(_BASE_MINT)
    first_view = rec.recorded_entries
    assert len(first_view) == 1
    # Make another call; the previously-captured tuple is
    # unchanged because tuples are immutable, but the property
    # always returns a fresh snapshot.
    rec.read_migration_snapshot(_BASE_MINT)
    assert len(first_view) == 1
    assert len(rec.recorded_entries) == 2


def test_failed_reads_do_not_append_entries() -> None:
    # First call succeeds, second call has provider raise.
    call_count = {"n": 0}

    def evidence_provider(token_mint: str):
        call_count["n"] += 1
        if call_count["n"] == 2:
            raise RuntimeError("second call boom")
        return (_present_helius_ws_evidence(),)

    rec = Stage29_5_5MigrationContextRecorder(
        evidence_provider=evidence_provider,
        ath_context_provider=(
            lambda m: _ath_context_post_migration_only()
        ),
        clock=lambda: _OBSERVED_AT,
        renderer=(
            render_private_discord_migration_context_block
        ),
    )
    rec.read_migration_snapshot(_BASE_MINT)
    rec.read_migration_snapshot(_BASE_MINT)  # raises -> UNKNOWN
    rec.read_migration_snapshot(_BASE_MINT)  # succeeds
    # Two successful reads -> two entries.
    assert len(rec.recorded_entries) == 2


# ---------------------------------------------------------------------------
# Phase 2 isolation: renderer / recording failure preserves Phase
# 1 snapshot
# ---------------------------------------------------------------------------


def test_renderer_failure_preserves_live_snapshot() -> None:
    """A renderer that raises on a trusted COMPLETE projection
    MUST NOT degrade the returned Stage 27.4 snapshot. The
    snapshot the Stage 29.5.4 adapter would have produced for the
    same inputs flows through unchanged; no entry is appended.
    """
    def boom_renderer(projection):
        raise RuntimeError("side-channel renderer failure")

    rec = Stage29_5_5MigrationContextRecorder(
        evidence_provider=lambda m: (
            _present_helius_ws_evidence(),
        ),
        ath_context_provider=(
            lambda m: _ath_context_post_migration_only()
        ),
        clock=lambda: _OBSERVED_AT,
        renderer=boom_renderer,
    )
    snapshot = rec.read_migration_snapshot(_BASE_MINT)
    assert (
        snapshot.migration_source
        == "ON_CHAIN_MIGRATION_EVENT"
    )
    assert snapshot.migration_timestamp_utc == _MIGRATION_TS
    assert rec.recorded_entries == ()


def test_renderer_failure_preserves_live_snapshot_matches_no_renderer_path() -> None:
    """The trusted snapshot a recorder with a raising renderer
    returns MUST byte-match the snapshot a recorder with
    ``renderer=None`` returns for the same inputs (= the Stage
    29.5.4 adapter's snapshot for the same evidence).
    """
    def boom_renderer(projection):
        raise RuntimeError("renderer boom")

    rec_with_renderer = Stage29_5_5MigrationContextRecorder(
        evidence_provider=lambda m: (
            _present_helius_ws_evidence(),
        ),
        ath_context_provider=(
            lambda m: _ath_context_post_migration_only()
        ),
        clock=lambda: _OBSERVED_AT,
        renderer=boom_renderer,
    )
    rec_without_renderer = Stage29_5_5MigrationContextRecorder(
        evidence_provider=lambda m: (
            _present_helius_ws_evidence(),
        ),
        ath_context_provider=(
            lambda m: _ath_context_post_migration_only()
        ),
        clock=lambda: _OBSERVED_AT,
        renderer=None,
    )
    snap_a = rec_with_renderer.read_migration_snapshot(
        _BASE_MINT,
    )
    snap_b = rec_without_renderer.read_migration_snapshot(
        _BASE_MINT,
    )
    assert snap_a == snap_b
    assert rec_with_renderer.recorded_entries == ()
    assert rec_without_renderer.recorded_entries == ()


def test_recording_failure_preserves_live_snapshot() -> None:
    """A Phase 2 failure DOWNSTREAM of the renderer (here:
    a clock that returns a bad ``recorded_at_utc`` on the FIRST
    Phase 2 call, after the projection's ``observed_at_utc`` was
    already set in Phase 1) MUST preserve the Phase 1 snapshot
    unchanged AND skip appending the entry.

    The Stage 29.5 join layer calls the clock once for
    ``joined_at_utc`` and the projection layer calls the clock
    once for ``observed_at_utc`` (= two Phase 1 calls); Phase 2
    then calls the clock once for ``recorded_at_utc``. A
    counting clock that returns valid UTC strings on calls 1 + 2
    and a bad string on call 3 isolates Phase 2 from Phase 1.
    """
    state = {"n": 0}

    def split_clock():
        state["n"] += 1
        if state["n"] <= 2:
            return _OBSERVED_AT
        return "not-a-utc-shaped-string"

    rec = Stage29_5_5MigrationContextRecorder(
        evidence_provider=lambda m: (
            _present_helius_ws_evidence(),
        ),
        ath_context_provider=(
            lambda m: _ath_context_post_migration_only()
        ),
        clock=split_clock,
        renderer=(
            render_private_discord_migration_context_block
        ),
    )
    snapshot = rec.read_migration_snapshot(_BASE_MINT)
    # Phase 1 used the first two clock values (valid) and
    # succeeded. Phase 2 used the third clock value (invalid
    # recorded_at_utc) and silently failed -> snapshot preserved,
    # no entry.
    assert (
        snapshot.migration_source
        == "ON_CHAIN_MIGRATION_EVENT"
    )
    assert snapshot.migration_timestamp_utc == _MIGRATION_TS
    assert rec.recorded_entries == ()


def test_renderer_returning_unsafe_block_preserves_live_snapshot() -> None:
    """A custom renderer that returns a Stage 29.5.5 block
    instance carrying a forbidden substring in ``body_text``
    cannot reach ``recorded_entries``. The Stage 29.5.5
    dataclass validator raises ``ValueError`` at construction
    time; the recorder catches it as a Phase 2 failure and
    preserves the Phase 1 snapshot unchanged.
    """
    def renderer_with_forbidden_body(projection):
        # Use the real renderer's output as a base, then try to
        # smuggle a forbidden substring via a doctored block.
        # Direct construction with a forbidden substring fails
        # at __post_init__; the recorder catches the ValueError.
        base = render_private_discord_migration_context_block(
            projection,
        )
        return Stage29_5_5RenderedMigrationContextBlock(
            migration_evidence_status_display=(
                base.migration_evidence_status_display
            ),
            migration_evidence_source_trust_display=(
                base.migration_evidence_source_trust_display
            ),
            post_migration_ath_verified_display=(
                base.post_migration_ath_verified_display
            ),
            migration_timestamp_utc_display=(
                base.migration_timestamp_utc_display
            ),
            migration_slot_display=(
                base.migration_slot_display
            ),
            migration_source_token=(
                base.migration_source_token
            ),
            join_status_echoed_token=(
                base.join_status_echoed_token
            ),
            warnings_display=base.warnings_display,
            redaction_status=base.redaction_status,
            filter_enforcement_status=(
                base.filter_enforcement_status
            ),
            observed_at_utc=base.observed_at_utc,
            informational_only=True,
            not_a_trading_verdict=True,
            body_text=(
                base.body_text
                + "\n"
                + "leaked: "
                + "h" + "ttps://example" + ".com/webhook"
            ),
        )

    rec = Stage29_5_5MigrationContextRecorder(
        evidence_provider=lambda m: (
            _present_helius_ws_evidence(),
        ),
        ath_context_provider=(
            lambda m: _ath_context_post_migration_only()
        ),
        clock=lambda: _OBSERVED_AT,
        renderer=renderer_with_forbidden_body,
    )
    snapshot = rec.read_migration_snapshot(_BASE_MINT)
    assert (
        snapshot.migration_source
        == "ON_CHAIN_MIGRATION_EVENT"
    )
    assert rec.recorded_entries == ()


# ---------------------------------------------------------------------------
# Phase 2 isolation: object.__setattr__ mutation of a freshly-
# constructed safe block must NEVER reach recorded_entries.
# ---------------------------------------------------------------------------


def _mutating_renderer(*, field_name: str, replacement: object):
    """Return a renderer that produces a Stage 29.5.5 block via
    the real renderer, then mutates ``field_name`` to
    ``replacement`` via ``object.__setattr__`` to bypass the
    frozen-dataclass guard.
    """
    def renderer(projection):
        block = render_private_discord_migration_context_block(
            projection,
        )
        object.__setattr__(block, field_name, replacement)
        return block

    return renderer


def test_mutated_rendered_block_closed_set_field_is_not_recorded() -> None:
    """A custom renderer that mutates a closed-set token field
    (``migration_source_token`` /
    ``migration_evidence_source_trust_display``) AFTER
    construction to a string containing a forbidden URL host /
    webhook substring MUST be caught by the recorder's full
    validator. The Phase 1 trusted snapshot survives; no entry
    is appended.
    """
    malicious_value = (
        "h" + "ttps://discord" + ".com/api/webhooks/x"
    )
    for field_name in (
        "migration_source_token",
        "migration_evidence_source_trust_display",
    ):
        renderer = _mutating_renderer(
            field_name=field_name,
            replacement=malicious_value,
        )
        rec = Stage29_5_5MigrationContextRecorder(
            evidence_provider=lambda m: (
                _present_helius_ws_evidence(),
            ),
            ath_context_provider=(
                lambda m: _ath_context_post_migration_only()
            ),
            clock=lambda: _OBSERVED_AT,
            renderer=renderer,
        )
        snapshot = rec.read_migration_snapshot(_BASE_MINT)
        assert (
            snapshot.migration_source
            == "ON_CHAIN_MIGRATION_EVENT"
        ), (
            f"Mutation of {field_name!r} via object.__setattr__ "
            f"must not degrade the Stage 27.4 snapshot"
        )
        assert snapshot.migration_timestamp_utc == _MIGRATION_TS
        assert rec.recorded_entries == (), (
            f"Mutation of {field_name!r} must prevent the "
            f"recorder from appending an unsafe entry"
        )


def test_mutated_rendered_block_pinned_status_field_is_not_recorded() -> None:
    """A custom renderer that mutates a pinned exact-value
    status field (``redaction_status`` /
    ``filter_enforcement_status``) AFTER construction to a non-
    locked value MUST be caught by the recorder's full
    validator. The Phase 1 snapshot survives; no entry is
    appended.
    """
    test_matrix = (
        ("redaction_status", "REDACTED"),
        (
            "filter_enforcement_status",
            "ENFORCEMENT_ACTIVE_STAGE_29_LIVE",
        ),
    )
    for field_name, replacement in test_matrix:
        renderer = _mutating_renderer(
            field_name=field_name,
            replacement=replacement,
        )
        rec = Stage29_5_5MigrationContextRecorder(
            evidence_provider=lambda m: (
                _present_helius_ws_evidence(),
            ),
            ath_context_provider=(
                lambda m: _ath_context_post_migration_only()
            ),
            clock=lambda: _OBSERVED_AT,
            renderer=renderer,
        )
        snapshot = rec.read_migration_snapshot(_BASE_MINT)
        assert (
            snapshot.migration_source
            == "ON_CHAIN_MIGRATION_EVENT"
        ), (
            f"Mutation of {field_name!r} via object.__setattr__ "
            f"must not degrade the Stage 27.4 snapshot"
        )
        assert rec.recorded_entries == (), (
            f"Mutation of {field_name!r} to {replacement!r} "
            f"must prevent recording"
        )


def test_mutated_rendered_block_boolean_flag_is_not_recorded() -> None:
    """A custom renderer that mutates a pinned boolean flag
    (``informational_only`` / ``not_a_trading_verdict``) AFTER
    construction to ``False`` MUST be caught by the recorder's
    full validator. The Phase 1 snapshot survives; no entry is
    appended.
    """
    for field_name in (
        "informational_only",
        "not_a_trading_verdict",
    ):
        renderer = _mutating_renderer(
            field_name=field_name,
            replacement=False,
        )
        rec = Stage29_5_5MigrationContextRecorder(
            evidence_provider=lambda m: (
                _present_helius_ws_evidence(),
            ),
            ath_context_provider=(
                lambda m: _ath_context_post_migration_only()
            ),
            clock=lambda: _OBSERVED_AT,
            renderer=renderer,
        )
        snapshot = rec.read_migration_snapshot(_BASE_MINT)
        assert (
            snapshot.migration_source
            == "ON_CHAIN_MIGRATION_EVENT"
        ), (
            f"Mutation of {field_name!r} via object.__setattr__ "
            f"must not degrade the Stage 27.4 snapshot"
        )
        assert rec.recorded_entries == (), (
            f"Mutation of {field_name!r} to False must prevent "
            f"recording"
        )


def test_mutated_rendered_block_schema_version_is_not_recorded() -> None:
    """A custom renderer that mutates ``schema_version`` AFTER
    construction to a non-locked string MUST be caught by the
    recorder's full validator.
    """
    renderer = _mutating_renderer(
        field_name="schema_version",
        replacement="stage29_5_5_v0_forged_block",
    )
    rec = Stage29_5_5MigrationContextRecorder(
        evidence_provider=lambda m: (
            _present_helius_ws_evidence(),
        ),
        ath_context_provider=(
            lambda m: _ath_context_post_migration_only()
        ),
        clock=lambda: _OBSERVED_AT,
        renderer=renderer,
    )
    snapshot = rec.read_migration_snapshot(_BASE_MINT)
    assert (
        snapshot.migration_source
        == "ON_CHAIN_MIGRATION_EVENT"
    )
    assert rec.recorded_entries == ()


# ---------------------------------------------------------------------------
# Slot semantics: __slots__ on the class
# ---------------------------------------------------------------------------


def test_recorder_class_defines_slots() -> None:
    assert hasattr(
        Stage29_5_5MigrationContextRecorder, "__slots__",
    )

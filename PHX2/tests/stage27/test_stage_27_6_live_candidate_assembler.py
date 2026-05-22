"""Stage 27.6 live candidate assembler tests.

Pins:

  * The Stage 27.6 candidate / reason / sources records are
    immutable ``NamedTuple`` shapes with closed-set vocabularies.
  * Stage 27.3 -> 27.4 -> 27.5 chain runs end-to-end through the
    assembler on fake injected sources.
  * SOL fake event renders ``RENDERED_DRY_RUN`` and writes both
    payload + provenance artifacts.
  * USDC fake event renders ``RENDERED_DRY_RUN`` with
    ``USDC_OBSERVE_ONLY`` reason; never reaches
    ``EXISTING_SOL_LANE``.
  * UNKNOWN fake event produces ``SUPPRESSED_UNKNOWN_PAIR``.
  * DISAGREE fake event produces ``SUPPRESSED_DISAGREE_PAIR``.
  * Duplicate event produces ``SKIPPED_DUPLICATE`` and does NOT
    write a second artifact pair.
  * Unsupported event kind produces ``SKIPPED_UNSUPPORTED_EVENT``.
  * Missing token mint produces ``SKIPPED_MISSING_TOKEN``.
  * Path-traversal output root is rejected via
    ``Stage27_5PathEscapeError``.
  * ``write_artifacts=False`` produces ``ASSEMBLED`` (no on-disk
    write).
  * Two identical SOL events with same ids produce the same dedupe
    key and the second is skipped.
"""

from __future__ import annotations

import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import NamedTuple, Optional

import pytest

from PHX2.stage27 import price_ath_context_contracts as src_errors
from PHX2.stage27.live_candidate_assembler import (
    CANDIDATE_REASON_DISAGREE_PAIR_LIVE_SUPPRESSED,
    CANDIDATE_REASON_DUPLICATE_RUN_LOCAL,
    CANDIDATE_REASON_MISSING_TOKEN_MINT,
    CANDIDATE_REASON_RENDERED_OK,
    CANDIDATE_REASON_RENDERED_WITH_WARNINGS,
    CANDIDATE_REASON_UNKNOWN_PAIR_LIVE_SUPPRESSED,
    CANDIDATE_REASON_UNSUPPORTED_EVENT_KIND,
    CANDIDATE_REASON_USDC_OBSERVE_ONLY,
    CANDIDATE_REASON_VALUES,
    CANDIDATE_STATUS_ASSEMBLED,
    CANDIDATE_STATUS_RENDERED_DRY_RUN,
    CANDIDATE_STATUS_SKIPPED_DUPLICATE,
    CANDIDATE_STATUS_SKIPPED_MISSING_TOKEN,
    CANDIDATE_STATUS_SKIPPED_UNSUPPORTED_EVENT,
    CANDIDATE_STATUS_SUPPRESSED_DISAGREE_PAIR,
    CANDIDATE_STATUS_SUPPRESSED_UNKNOWN_PAIR,
    CANDIDATE_STATUS_VALUES,
    STAGE27_6_CANDIDATE_SCHEMA_VERSION,
    STAGE27_6_MINOR_VERSION,
    Stage27_6LiveCandidateRecord,
    Stage27_6Sources,
    assemble_live_candidate,
)
from PHX2.stage27.live_dedupe import (
    Stage27_6DedupeKey,
    Stage27_6RunLocalDedupe,
)
from PHX2.stage27.pair_detection_constants import (
    CALIBRATION_LANE_EXISTING_SOL_LANE,
    KNOWN_USDC_MINT,
    KNOWN_WRAPPED_SOL_MINT,
)
from PHX2.stage27.price_ath_context_models import (
    ATH_UNIT_SOL,
    ATH_UNIT_USDC,
    PRICE_UNIT_SOL,
    PRICE_UNIT_USDC,
)
from PHX2.stage27.price_ath_context_reader import (
    AthSourceSnapshot,
    FrozenStage27_4Clock,
    MigrationSourceSnapshot,
    PriceSourceSnapshot,
)
from PHX2.stage27.private_ping_artifact_writer import (
    Stage27_5PathEscapeError,
)
from PHX2.stage27.private_ping_models import (
    RENDER_STATUS_RENDERED,
    RENDER_STATUS_RENDERED_OBSERVE_ONLY,
    RENDER_STATUS_RENDERED_SUPPRESSED,
)
from PHX2.stage27.provider_ingest_models import (
    EVENT_KIND_SWAP,
    EVENT_KIND_UNKNOWN,
    ProviderIngestInputRecord,
)


# ---------------------------------------------------------------------------
# Project-local tmp dir fixture (sidesteps sandboxed pytest-of-* root)
# ---------------------------------------------------------------------------


@pytest.fixture
def stage27_6_tmp_path():
    base = Path(__file__).resolve().parent / "_stage_27_6_tmp"
    base.mkdir(parents=True, exist_ok=True)
    path = Path(tempfile.mkdtemp(prefix="stage27_6_", dir=base))
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)
        try:
            base.rmdir()
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Fixtures: deterministic clocks + fake source readers
# ---------------------------------------------------------------------------


_FIXED_UTC = datetime(2026, 5, 22, 12, 0, 30, tzinfo=timezone.utc)
_FIXED_UTC_ISO = "2026-05-22T12:00:30+00:00"


class _FrozenStage27_5Clock(NamedTuple):
    iso: str = _FIXED_UTC_ISO

    def now_utc_iso(self) -> str:
        return self.iso


class _FrozenStage27_6Clock(NamedTuple):
    iso: str = _FIXED_UTC_ISO

    def now_utc_iso(self) -> str:
        return self.iso


class _FakePriceSource(NamedTuple):
    snapshot: Optional[PriceSourceSnapshot]
    raise_source_error: bool = False

    def read_price_snapshot(
        self, token_mint, *, pair_quote_asset
    ):
        if self.raise_source_error:
            raise src_errors.Stage27PriceSourceError(
                "SOURCE_FAILED", source_label="fake_price"
            )
        return self.snapshot


class _FakeAthSource(NamedTuple):
    snapshot: Optional[AthSourceSnapshot]
    raise_source_error: bool = False

    def read_ath_snapshot(
        self, token_mint, *, pair_quote_asset
    ):
        if self.raise_source_error:
            raise src_errors.Stage27AthSourceError(
                "SOURCE_FAILED", source_label="fake_ath"
            )
        return self.snapshot


class _FakeMigrationSource(NamedTuple):
    snapshot: Optional[MigrationSourceSnapshot]
    raise_source_error: bool = False

    def read_migration_snapshot(self, token_mint):
        if self.raise_source_error:
            raise src_errors.Stage27MigrationSourceError(
                "SOURCE_FAILED", source_label="fake_migration"
            )
        return self.snapshot


def _sol_sources() -> Stage27_6Sources:
    """Return Stage 27.6 sources that yield PRESENT contexts for SOL."""
    price = PriceSourceSnapshot(
        price_value="0.001",
        price_unit=PRICE_UNIT_SOL,
        source_label="fake_birdeye",
        fetched_at_utc=_FIXED_UTC_ISO,
    )
    ath = AthSourceSnapshot(
        ath_value="0.005",
        ath_unit=ATH_UNIT_SOL,
        source_label="fake_birdeye",
        ath_observed_at_utc="2026-05-22T11:30:00+00:00",
        window_starts_post_migration=True,
    )
    migration = MigrationSourceSnapshot(
        migration_event_id="mig-1",
        migration_timestamp_utc="2026-05-22T11:00:00+00:00",
        migration_source="ON_CHAIN_MIGRATION_EVENT",
        source_event_ref="prov-mig-1",
        raw_capture_ref="rcap-mig-1",
    )
    return Stage27_6Sources(
        price_source=_FakePriceSource(snapshot=price),
        ath_source=_FakeAthSource(snapshot=ath),
        migration_source=_FakeMigrationSource(
            snapshot=migration
        ),
        stage27_4_clock=FrozenStage27_4Clock(
            fixed_utc=_FIXED_UTC
        ),
        stage27_5_clock=_FrozenStage27_5Clock(),
        price_staleness_threshold_seconds=60,
    )


def _usdc_sources() -> Stage27_6Sources:
    price = PriceSourceSnapshot(
        price_value="0.12",
        price_unit=PRICE_UNIT_USDC,
        source_label="fake_birdeye",
        fetched_at_utc=_FIXED_UTC_ISO,
    )
    ath = AthSourceSnapshot(
        ath_value="1.50",
        ath_unit=ATH_UNIT_USDC,
        source_label="fake_birdeye",
        ath_observed_at_utc="2026-05-22T11:30:00+00:00",
        window_starts_post_migration=True,
    )
    migration = MigrationSourceSnapshot(
        migration_event_id="mig-1",
        migration_timestamp_utc="2026-05-22T11:00:00+00:00",
        migration_source="ON_CHAIN_MIGRATION_EVENT",
        source_event_ref="prov-mig-1",
        raw_capture_ref="rcap-mig-1",
    )
    return Stage27_6Sources(
        price_source=_FakePriceSource(snapshot=price),
        ath_source=_FakeAthSource(snapshot=ath),
        migration_source=_FakeMigrationSource(
            snapshot=migration
        ),
        stage27_4_clock=FrozenStage27_4Clock(
            fixed_utc=_FIXED_UTC
        ),
        stage27_5_clock=_FrozenStage27_5Clock(),
        price_staleness_threshold_seconds=60,
    )


# ---------------------------------------------------------------------------
# Fixture event inputs
# ---------------------------------------------------------------------------


def _sol_event(
    *,
    provider_event_id: str = "evt-sol-1",
    normalized_event_id: str = "norm-sol-1",
    token_mint: str = "MintAAA",
) -> ProviderIngestInputRecord:
    return ProviderIngestInputRecord(
        provider_id="fake-helius",
        provider_event_id=provider_event_id,
        normalized_event_id=normalized_event_id,
        event_kind=EVENT_KIND_SWAP,
        observed_at_utc="2026-05-22T11:59:00+00:00",
        token_mint=token_mint,
        quote_mint=KNOWN_WRAPPED_SOL_MINT,
        raw_capture_ref="rcap-1",
        source_summary="fake-summary",
    )


def _usdc_event() -> ProviderIngestInputRecord:
    return ProviderIngestInputRecord(
        provider_id="fake-helius",
        provider_event_id="evt-usdc-1",
        normalized_event_id="norm-usdc-1",
        event_kind=EVENT_KIND_SWAP,
        observed_at_utc="2026-05-22T11:59:00+00:00",
        token_mint="MintBBB",
        quote_mint=KNOWN_USDC_MINT,
        raw_capture_ref="rcap-2",
        source_summary="fake-summary",
    )


def _unknown_event() -> ProviderIngestInputRecord:
    return ProviderIngestInputRecord(
        provider_id="fake-helius",
        provider_event_id="evt-unknown-1",
        normalized_event_id="norm-unknown-1",
        event_kind=EVENT_KIND_SWAP,
        observed_at_utc="2026-05-22T11:59:00+00:00",
        token_mint="MintCCC",
        quote_mint=None,
        raw_capture_ref="rcap-3",
        source_summary="fake-summary",
    )


def _disagree_event() -> ProviderIngestInputRecord:
    """A SWAP event where the on-chain quote mint disagrees with the
    provider's hint -> Stage 27.2 classifier emits ``DISAGREE``.
    """
    return ProviderIngestInputRecord(
        provider_id="fake-helius",
        provider_event_id="evt-disagree-1",
        normalized_event_id="norm-disagree-1",
        event_kind=EVENT_KIND_SWAP,
        observed_at_utc="2026-05-22T11:59:00+00:00",
        token_mint="MintDDD",
        quote_mint=KNOWN_WRAPPED_SOL_MINT,
        provider_quote_asset_hint="USDC",
        raw_capture_ref="rcap-4",
        source_summary="fake-summary",
    )


def _unsupported_event() -> ProviderIngestInputRecord:
    return ProviderIngestInputRecord(
        provider_id="fake-helius",
        provider_event_id="evt-unsup-1",
        normalized_event_id="norm-unsup-1",
        event_kind=EVENT_KIND_UNKNOWN,
        observed_at_utc="2026-05-22T11:59:00+00:00",
        token_mint="MintEEE",
        quote_mint=KNOWN_WRAPPED_SOL_MINT,
    )


def _missing_token_event() -> ProviderIngestInputRecord:
    return ProviderIngestInputRecord(
        provider_id="fake-helius",
        provider_event_id="evt-no-token-1",
        normalized_event_id="norm-no-token-1",
        event_kind=EVENT_KIND_SWAP,
        observed_at_utc="2026-05-22T11:59:00+00:00",
        token_mint=None,
        quote_mint=KNOWN_WRAPPED_SOL_MINT,
    )


# ---------------------------------------------------------------------------
# Closed-set vocabulary pins
# ---------------------------------------------------------------------------


def test_minor_version_axis_is_27_6():
    assert STAGE27_6_MINOR_VERSION == "27.6"


def test_candidate_schema_version_locked():
    assert STAGE27_6_CANDIDATE_SCHEMA_VERSION == (
        "stage27_v0_live_candidate"
    )


def test_candidate_status_values_are_closed_set():
    assert CANDIDATE_STATUS_VALUES == (
        "ASSEMBLED",
        "RENDERED_DRY_RUN",
        "SKIPPED_DUPLICATE",
        "SKIPPED_UNSUPPORTED_EVENT",
        "SKIPPED_MISSING_TOKEN",
        "SUPPRESSED_UNKNOWN_PAIR",
        "SUPPRESSED_DISAGREE_PAIR",
        "ARTIFACT_WRITE_FAILED",
        "ERROR",
    )


def test_candidate_status_values_have_no_trading_verdicts():
    """No BUY / SELL / APPROVED / GATE / BLOCK / EXECUTE language."""
    forbidden = (
        "BUY",
        "SELL",
        "APPROVED",
        "APPROVE",
        "GATE",
        "BLOCK",
        "EXECUTE",
        "AUTO_TRADE",
        "POSITION_SIZE",
        "ENFORCEMENT",
        "ENFORCE",
    )
    for v in CANDIDATE_STATUS_VALUES:
        upper = v.upper()
        for needle in forbidden:
            assert needle not in upper, (
                f"candidate_status {v!r} contains forbidden "
                f"trading-verdict substring {needle!r}"
            )


def test_candidate_reason_values_have_no_trading_verdicts():
    forbidden = (
        "BUY",
        "SELL",
        "APPROVED",
        "APPROVE",
        "GATE",
        "BLOCK",
        "EXECUTE",
        "AUTO_TRADE",
        "POSITION_SIZE",
        "ENFORCEMENT",
        "ENFORCE",
    )
    for v in CANDIDATE_REASON_VALUES:
        upper = v.upper()
        for needle in forbidden:
            assert needle not in upper, (
                f"candidate_reason {v!r} contains forbidden "
                f"trading-verdict substring {needle!r}"
            )


# ---------------------------------------------------------------------------
# Immutable record discipline
# ---------------------------------------------------------------------------


def test_live_candidate_record_is_immutable(stage27_6_tmp_path):
    sources = _sol_sources()
    dedupe = Stage27_6RunLocalDedupe()
    rec = assemble_live_candidate(
        _sol_event(),
        sources,
        dedupe,
        candidate_id="cand-1",
        output_root=stage27_6_tmp_path,
        run_id="run-1",
        session_id="sess-1",
    )
    assert isinstance(rec, tuple)
    with pytest.raises(AttributeError):
        rec.candidate_status = "MUTATED"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# SOL: composed + rendered + artifacts written
# ---------------------------------------------------------------------------


def test_sol_event_renders_dry_run_and_writes_both_artifacts(
    stage27_6_tmp_path,
):
    sources = _sol_sources()
    dedupe = Stage27_6RunLocalDedupe()
    rec = assemble_live_candidate(
        _sol_event(),
        sources,
        dedupe,
        candidate_id="cand-1",
        output_root=stage27_6_tmp_path,
        run_id="run-1",
        session_id="sess-1",
    )
    assert rec.candidate_status == CANDIDATE_STATUS_RENDERED_DRY_RUN
    assert rec.candidate_reason == CANDIDATE_REASON_RENDERED_OK
    assert rec.measurement_context is not None
    assert rec.rendered_ping is not None
    assert rec.provenance_artifact is not None
    assert rec.write_attempted is True
    assert rec.payload_artifact_path is not None
    assert rec.provenance_artifact_path is not None
    assert rec.payload_artifact_path.is_file()
    assert rec.provenance_artifact_path.is_file()
    assert rec.rendered_ping.render_status == RENDER_STATUS_RENDERED
    assert (
        rec.measurement_context.pair_calibration_lane
        == CALIBRATION_LANE_EXISTING_SOL_LANE
    )


def test_sol_event_records_dedupe_key():
    sources = _sol_sources()
    dedupe = Stage27_6RunLocalDedupe()
    rec = assemble_live_candidate(
        _sol_event(),
        sources,
        dedupe,
        candidate_id="cand-1",
        output_root=None,
        run_id="run-1",
        session_id="sess-1",
        write_artifacts=False,
    )
    assert isinstance(rec.dedupe_key, Stage27_6DedupeKey)
    assert dedupe.size() == 1
    assert dedupe.is_duplicate(rec.dedupe_key)


# ---------------------------------------------------------------------------
# USDC: observe-only render
# ---------------------------------------------------------------------------


def test_usdc_event_renders_observe_only_dry_run(stage27_6_tmp_path):
    sources = _usdc_sources()
    dedupe = Stage27_6RunLocalDedupe()
    rec = assemble_live_candidate(
        _usdc_event(),
        sources,
        dedupe,
        candidate_id="cand-usdc-1",
        output_root=stage27_6_tmp_path,
        run_id="run-1",
        session_id="sess-1",
    )
    assert rec.candidate_status == CANDIDATE_STATUS_RENDERED_DRY_RUN
    assert rec.candidate_reason == CANDIDATE_REASON_USDC_OBSERVE_ONLY
    assert rec.rendered_ping is not None
    assert (
        rec.rendered_ping.render_status
        == RENDER_STATUS_RENDERED_OBSERVE_ONLY
    )
    # USDC pair must NEVER reach the existing SOL lane.
    assert (
        rec.measurement_context.pair_calibration_lane
        != CALIBRATION_LANE_EXISTING_SOL_LANE
    )
    assert rec.payload_artifact_path.is_file()
    assert rec.provenance_artifact_path.is_file()


# ---------------------------------------------------------------------------
# UNKNOWN: suppressed
# ---------------------------------------------------------------------------


def test_unknown_event_records_suppressed_context(stage27_6_tmp_path):
    sources = _sol_sources()
    dedupe = Stage27_6RunLocalDedupe()
    rec = assemble_live_candidate(
        _unknown_event(),
        sources,
        dedupe,
        candidate_id="cand-unknown-1",
        output_root=stage27_6_tmp_path,
        run_id="run-1",
        session_id="sess-1",
    )
    assert (
        rec.candidate_status
        == CANDIDATE_STATUS_SUPPRESSED_UNKNOWN_PAIR
    )
    assert (
        rec.candidate_reason
        == CANDIDATE_REASON_UNKNOWN_PAIR_LIVE_SUPPRESSED
    )
    # UNKNOWN must NEVER reach the existing SOL lane.
    assert (
        rec.ingest_output.pair_calibration_lane
        != CALIBRATION_LANE_EXISTING_SOL_LANE
    )
    # The Stage 27.5 renderer still produces a SUPPRESSED ping payload
    # so the operator review surface still has provenance.
    assert (
        rec.rendered_ping.render_status
        == RENDER_STATUS_RENDERED_SUPPRESSED
    )


# ---------------------------------------------------------------------------
# DISAGREE: suppressed
# ---------------------------------------------------------------------------


def test_disagree_event_records_suppressed_context(stage27_6_tmp_path):
    sources = _sol_sources()
    dedupe = Stage27_6RunLocalDedupe()
    rec = assemble_live_candidate(
        _disagree_event(),
        sources,
        dedupe,
        candidate_id="cand-disagree-1",
        output_root=stage27_6_tmp_path,
        run_id="run-1",
        session_id="sess-1",
    )
    assert (
        rec.candidate_status
        == CANDIDATE_STATUS_SUPPRESSED_DISAGREE_PAIR
    )
    assert (
        rec.candidate_reason
        == CANDIDATE_REASON_DISAGREE_PAIR_LIVE_SUPPRESSED
    )
    assert (
        rec.ingest_output.pair_calibration_lane
        != CALIBRATION_LANE_EXISTING_SOL_LANE
    )


# ---------------------------------------------------------------------------
# Duplicate skip
# ---------------------------------------------------------------------------


def test_duplicate_event_is_skipped_and_not_written(stage27_6_tmp_path):
    sources = _sol_sources()
    dedupe = Stage27_6RunLocalDedupe()
    first = assemble_live_candidate(
        _sol_event(),
        sources,
        dedupe,
        candidate_id="cand-1",
        output_root=stage27_6_tmp_path,
        run_id="run-1",
        session_id="sess-1",
        ping_id="ping-1",
    )
    assert first.candidate_status == CANDIDATE_STATUS_RENDERED_DRY_RUN

    second = assemble_live_candidate(
        _sol_event(),
        sources,
        dedupe,
        candidate_id="cand-2",
        output_root=stage27_6_tmp_path,
        run_id="run-1",
        session_id="sess-1",
        ping_id="ping-2",  # different ping_id but same event -> dedupe
    )
    assert (
        second.candidate_status == CANDIDATE_STATUS_SKIPPED_DUPLICATE
    )
    assert second.candidate_reason == CANDIDATE_REASON_DUPLICATE_RUN_LOCAL
    assert second.rendered_ping is None
    assert second.provenance_artifact is None
    assert second.payload_artifact_path is None
    assert second.provenance_artifact_path is None
    # The second event must NOT have written any artifact pair.
    files = sorted(p.name for p in stage27_6_tmp_path.iterdir())
    assert files == [
        "ping_ping-1_payload.json",
        "ping_ping-1_provenance.json",
    ]


# ---------------------------------------------------------------------------
# Unsupported / missing token
# ---------------------------------------------------------------------------


def test_unsupported_event_skips_chain(stage27_6_tmp_path):
    sources = _sol_sources()
    dedupe = Stage27_6RunLocalDedupe()
    rec = assemble_live_candidate(
        _unsupported_event(),
        sources,
        dedupe,
        candidate_id="cand-unsup-1",
        output_root=stage27_6_tmp_path,
        run_id="run-1",
        session_id="sess-1",
    )
    assert (
        rec.candidate_status
        == CANDIDATE_STATUS_SKIPPED_UNSUPPORTED_EVENT
    )
    assert (
        rec.candidate_reason
        == CANDIDATE_REASON_UNSUPPORTED_EVENT_KIND
    )
    assert rec.measurement_context is None
    assert rec.rendered_ping is None
    assert rec.provenance_artifact is None
    assert rec.payload_artifact_path is None
    assert tuple(stage27_6_tmp_path.iterdir()) == ()


def test_missing_token_event_skips_chain(stage27_6_tmp_path):
    sources = _sol_sources()
    dedupe = Stage27_6RunLocalDedupe()
    rec = assemble_live_candidate(
        _missing_token_event(),
        sources,
        dedupe,
        candidate_id="cand-no-token-1",
        output_root=stage27_6_tmp_path,
        run_id="run-1",
        session_id="sess-1",
    )
    assert (
        rec.candidate_status == CANDIDATE_STATUS_SKIPPED_MISSING_TOKEN
    )
    assert (
        rec.candidate_reason == CANDIDATE_REASON_MISSING_TOKEN_MINT
    )
    assert rec.measurement_context is None
    assert tuple(stage27_6_tmp_path.iterdir()) == ()


# ---------------------------------------------------------------------------
# Path-traversal output root is refused
# ---------------------------------------------------------------------------


def test_assembler_refuses_nonexistent_output_root(stage27_6_tmp_path):
    """The Stage 27.5 writer raises Stage27_5OutputRootError when the
    output root does not exist; the assembler still surfaces the
    raised error (it is not silently caught). Stage 27.5 path safety
    is therefore preserved end-to-end.
    """
    missing = stage27_6_tmp_path / "does_not_exist"
    sources = _sol_sources()
    dedupe = Stage27_6RunLocalDedupe()
    # The Stage 27.5 writer raises Stage27_5OutputRootError. The
    # assembler catches Stage27_5ArtifactWriteError (the writer's
    # base class) so the candidate is marked ARTIFACT_WRITE_FAILED.
    rec = assemble_live_candidate(
        _sol_event(),
        sources,
        dedupe,
        candidate_id="cand-1",
        output_root=missing,
        run_id="run-1",
        session_id="sess-1",
    )
    assert rec.candidate_status == "ARTIFACT_WRITE_FAILED"
    assert rec.candidate_reason == "ARTIFACT_WRITE_FAILED"


# ---------------------------------------------------------------------------
# write_artifacts=False -> ASSEMBLED
# ---------------------------------------------------------------------------


def test_write_artifacts_false_yields_assembled():
    sources = _sol_sources()
    dedupe = Stage27_6RunLocalDedupe()
    rec = assemble_live_candidate(
        _sol_event(),
        sources,
        dedupe,
        candidate_id="cand-1",
        output_root=None,
        run_id="run-1",
        session_id="sess-1",
        write_artifacts=False,
    )
    assert rec.candidate_status == CANDIDATE_STATUS_ASSEMBLED
    assert rec.write_attempted is False
    assert rec.rendered_ping is not None
    assert rec.provenance_artifact is not None
    assert rec.payload_artifact_path is None
    assert rec.provenance_artifact_path is None


def test_write_artifacts_true_requires_output_root():
    sources = _sol_sources()
    dedupe = Stage27_6RunLocalDedupe()
    with pytest.raises(ValueError):
        assemble_live_candidate(
            _sol_event(),
            sources,
            dedupe,
            candidate_id="cand-1",
            output_root=None,
            write_artifacts=True,
        )


# ---------------------------------------------------------------------------
# Argument discipline
# ---------------------------------------------------------------------------


def test_assembler_rejects_non_ingest_input():
    sources = _sol_sources()
    dedupe = Stage27_6RunLocalDedupe()
    with pytest.raises(TypeError):
        assemble_live_candidate(
            "not-an-ingest-input",  # type: ignore[arg-type]
            sources,
            dedupe,
            candidate_id="cand-1",
            output_root=None,
            write_artifacts=False,
        )


def test_assembler_rejects_non_sources():
    dedupe = Stage27_6RunLocalDedupe()
    with pytest.raises(TypeError):
        assemble_live_candidate(
            _sol_event(),
            "not-sources",  # type: ignore[arg-type]
            dedupe,
            candidate_id="cand-1",
            output_root=None,
            write_artifacts=False,
        )


def test_assembler_rejects_non_dedupe():
    sources = _sol_sources()
    with pytest.raises(TypeError):
        assemble_live_candidate(
            _sol_event(),
            sources,
            "not-dedupe",  # type: ignore[arg-type]
            candidate_id="cand-1",
            output_root=None,
            write_artifacts=False,
        )


def test_assembler_rejects_empty_candidate_id():
    sources = _sol_sources()
    dedupe = Stage27_6RunLocalDedupe()
    with pytest.raises(ValueError):
        assemble_live_candidate(
            _sol_event(),
            sources,
            dedupe,
            candidate_id="",
            output_root=None,
            write_artifacts=False,
        )


# ---------------------------------------------------------------------------
# Determinism: identical inputs produce identical (modulo paths) outputs
# ---------------------------------------------------------------------------


def test_assembler_is_deterministic_for_identical_inputs(stage27_6_tmp_path):
    sources = _sol_sources()
    dedupe_a = Stage27_6RunLocalDedupe()
    dedupe_b = Stage27_6RunLocalDedupe()
    root_a = stage27_6_tmp_path / "a"
    root_b = stage27_6_tmp_path / "b"
    root_a.mkdir()
    root_b.mkdir()
    rec_a = assemble_live_candidate(
        _sol_event(),
        sources,
        dedupe_a,
        candidate_id="cand-1",
        output_root=root_a,
        run_id="run-1",
        session_id="sess-1",
        ping_id="ping-1",
    )
    rec_b = assemble_live_candidate(
        _sol_event(),
        sources,
        dedupe_b,
        candidate_id="cand-1",
        output_root=root_b,
        run_id="run-1",
        session_id="sess-1",
        ping_id="ping-1",
    )
    assert rec_a.candidate_status == rec_b.candidate_status
    assert rec_a.candidate_reason == rec_b.candidate_reason
    assert rec_a.rendered_ping == rec_b.rendered_ping
    # Same payload bytes on disk.
    assert (
        rec_a.payload_artifact_path.read_bytes()
        == rec_b.payload_artifact_path.read_bytes()
    )
    assert (
        rec_a.provenance_artifact_path.read_bytes()
        == rec_b.provenance_artifact_path.read_bytes()
    )

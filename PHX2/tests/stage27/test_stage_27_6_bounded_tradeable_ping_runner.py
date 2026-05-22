"""Stage 27.6 bounded dry-run runner tests.

Pins:

  * Runner refuses to start when ``max_events`` and ``max_pings``
    are both ``None``.
  * Runner refuses when either bound is non-positive.
  * Runner stops at ``max_events``.
  * Runner stops at ``max_pings``.
  * Runner short-circuits to ``LIVE_REFUSED`` when given
    ``live_mode_authority="LIVE_ALLOWED"``.
  * LIVE_REFUSED summary records counts of zero.
  * Runner counts duplicates / unknown / disagree / unsupported /
    missing-token outputs deterministically.
  * Runner writes the dry-run artifact pair only for
    ``RENDERED_DRY_RUN`` candidates.
  * Runner optionally writes the Stage 27.6 run-summary artifact.
  * Run-summary writer refuses path-traversal filenames.
  * Run summary canonical JSON is deterministic.
  * Two identical runs produce identical run summaries (modulo
    wall-clock).
  * Runner never opens a network connection / never calls Discord
    (no transport surface exists in this module).
"""

from __future__ import annotations

import json
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import NamedTuple, Optional

import pytest

from PHX2.stage27 import price_ath_context_contracts as src_errors
from PHX2.stage27.bounded_tradeable_ping_runner import (
    LIVE_AUTHORITY_DRY_RUN,
    LIVE_AUTHORITY_LIVE_ALLOWED,
    LIVE_AUTHORITY_LIVE_REFUSED,
    RUN_MODE_DRY_RUN,
    RUN_MODE_LIVE_REFUSED,
    RUN_MODE_VALUES,
    STAGE27_6_RUN_SUMMARY_SCHEMA_VERSION,
    STOP_REASON_INPUT_EXHAUSTED,
    STOP_REASON_LIVE_MODE_REFUSED,
    STOP_REASON_MAX_EVENTS_REACHED,
    STOP_REASON_MAX_PINGS_REACHED,
    STOP_REASON_VALUES,
    Stage27_6BoundedDryRunRunResult,
    Stage27_6LiveModeRefusedError,
    Stage27_6RunnerBoundsError,
    Stage27_6RunSummaryRecord,
    canonical_run_summary_json,
    default_run_summary_filename,
    run_bounded_dry_run,
    write_run_summary_artifact,
)
from PHX2.stage27.live_candidate_assembler import (
    CANDIDATE_STATUS_RENDERED_DRY_RUN,
    CANDIDATE_STATUS_SKIPPED_DUPLICATE,
    CANDIDATE_STATUS_SKIPPED_MISSING_TOKEN,
    CANDIDATE_STATUS_SKIPPED_UNSUPPORTED_EVENT,
    CANDIDATE_STATUS_SUPPRESSED_DISAGREE_PAIR,
    CANDIDATE_STATUS_SUPPRESSED_UNKNOWN_PAIR,
    STAGE27_6_CANDIDATE_SCHEMA_VERSION,
    Stage27_6Sources,
)
from PHX2.stage27.pair_detection_constants import (
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
    Stage27_5FilenameError,
    Stage27_5OutputRootError,
    Stage27_5PathEscapeError,
)
from PHX2.stage27.provider_ingest_models import (
    EVENT_KIND_SWAP,
    EVENT_KIND_UNKNOWN,
    ProviderIngestInputRecord,
)


# ---------------------------------------------------------------------------
# Project-local tmp dir fixture
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
# Deterministic fixtures
# ---------------------------------------------------------------------------


_FIXED_UTC = datetime(2026, 5, 22, 12, 0, 30, tzinfo=timezone.utc)
_FIXED_UTC_ISO = "2026-05-22T12:00:30+00:00"


class _FrozenClockISO(NamedTuple):
    iso: str = _FIXED_UTC_ISO

    def now_utc_iso(self) -> str:
        return self.iso


class _PairAwarePriceSource:
    """Returns a PRESENT snapshot whose unit matches the pair."""

    def read_price_snapshot(
        self, token_mint, *, pair_quote_asset
    ):
        if pair_quote_asset == "USDC":
            return PriceSourceSnapshot(
                price_value="0.12",
                price_unit=PRICE_UNIT_USDC,
                source_label="fake_birdeye",
                fetched_at_utc=_FIXED_UTC_ISO,
            )
        return PriceSourceSnapshot(
            price_value="0.001",
            price_unit=PRICE_UNIT_SOL,
            source_label="fake_birdeye",
            fetched_at_utc=_FIXED_UTC_ISO,
        )


class _PairAwareAthSource:
    def read_ath_snapshot(
        self, token_mint, *, pair_quote_asset
    ):
        if pair_quote_asset == "USDC":
            return AthSourceSnapshot(
                ath_value="1.50",
                ath_unit=ATH_UNIT_USDC,
                source_label="fake_birdeye",
                ath_observed_at_utc=(
                    "2026-05-22T11:30:00+00:00"
                ),
                window_starts_post_migration=True,
            )
        return AthSourceSnapshot(
            ath_value="0.005",
            ath_unit=ATH_UNIT_SOL,
            source_label="fake_birdeye",
            ath_observed_at_utc="2026-05-22T11:30:00+00:00",
            window_starts_post_migration=True,
        )


class _FakeMigrationSource:
    def read_migration_snapshot(self, token_mint):
        return MigrationSourceSnapshot(
            migration_event_id="mig-1",
            migration_timestamp_utc=(
                "2026-05-22T11:00:00+00:00"
            ),
            migration_source="ON_CHAIN_MIGRATION_EVENT",
            source_event_ref="prov-mig-1",
            raw_capture_ref="rcap-mig-1",
        )


def _sol_sources() -> Stage27_6Sources:
    return Stage27_6Sources(
        price_source=_PairAwarePriceSource(),
        ath_source=_PairAwareAthSource(),
        migration_source=_FakeMigrationSource(),
        stage27_4_clock=FrozenStage27_4Clock(fixed_utc=_FIXED_UTC),
        stage27_5_clock=_FrozenClockISO(),
        price_staleness_threshold_seconds=60,
    )


def _sol_event(
    *, idx: int = 0, token_mint: str = "MintAAA"
) -> ProviderIngestInputRecord:
    return ProviderIngestInputRecord(
        provider_id="fake-helius",
        provider_event_id=f"evt-sol-{idx}",
        normalized_event_id=f"norm-sol-{idx}",
        event_kind=EVENT_KIND_SWAP,
        observed_at_utc="2026-05-22T11:59:00+00:00",
        token_mint=token_mint,
        quote_mint=KNOWN_WRAPPED_SOL_MINT,
        raw_capture_ref=f"rcap-{idx}",
        source_summary="fake-summary",
    )


def _usdc_event(idx: int = 0) -> ProviderIngestInputRecord:
    return ProviderIngestInputRecord(
        provider_id="fake-helius",
        provider_event_id=f"evt-usdc-{idx}",
        normalized_event_id=f"norm-usdc-{idx}",
        event_kind=EVENT_KIND_SWAP,
        observed_at_utc="2026-05-22T11:59:00+00:00",
        token_mint=f"MintUSDC{idx}",
        quote_mint=KNOWN_USDC_MINT,
        raw_capture_ref=f"rcap-{idx}",
    )


def _unknown_event(idx: int = 0) -> ProviderIngestInputRecord:
    return ProviderIngestInputRecord(
        provider_id="fake-helius",
        provider_event_id=f"evt-unk-{idx}",
        normalized_event_id=f"norm-unk-{idx}",
        event_kind=EVENT_KIND_SWAP,
        observed_at_utc="2026-05-22T11:59:00+00:00",
        token_mint=f"MintU{idx}",
        quote_mint=None,
        raw_capture_ref=f"rcap-{idx}",
    )


def _disagree_event(idx: int = 0) -> ProviderIngestInputRecord:
    return ProviderIngestInputRecord(
        provider_id="fake-helius",
        provider_event_id=f"evt-dis-{idx}",
        normalized_event_id=f"norm-dis-{idx}",
        event_kind=EVENT_KIND_SWAP,
        observed_at_utc="2026-05-22T11:59:00+00:00",
        token_mint=f"MintD{idx}",
        quote_mint=KNOWN_WRAPPED_SOL_MINT,
        provider_quote_asset_hint="USDC",
        raw_capture_ref=f"rcap-{idx}",
    )


def _unsupported_event(idx: int = 0) -> ProviderIngestInputRecord:
    return ProviderIngestInputRecord(
        provider_id="fake-helius",
        provider_event_id=f"evt-unsup-{idx}",
        normalized_event_id=f"norm-unsup-{idx}",
        event_kind=EVENT_KIND_UNKNOWN,
        observed_at_utc="2026-05-22T11:59:00+00:00",
        token_mint=f"MintX{idx}",
        quote_mint=KNOWN_WRAPPED_SOL_MINT,
    )


def _missing_token_event(idx: int = 0) -> ProviderIngestInputRecord:
    return ProviderIngestInputRecord(
        provider_id="fake-helius",
        provider_event_id=f"evt-nt-{idx}",
        normalized_event_id=f"norm-nt-{idx}",
        event_kind=EVENT_KIND_SWAP,
        observed_at_utc="2026-05-22T11:59:00+00:00",
        token_mint=None,
        quote_mint=KNOWN_WRAPPED_SOL_MINT,
    )


# ---------------------------------------------------------------------------
# Closed-set vocabulary pins
# ---------------------------------------------------------------------------


def test_run_summary_schema_version_locked():
    assert STAGE27_6_RUN_SUMMARY_SCHEMA_VERSION == (
        "stage27_v0_run_summary"
    )


def test_run_mode_values():
    assert RUN_MODE_VALUES == ("DRY_RUN", "LIVE_REFUSED")


def test_stop_reason_values():
    assert STOP_REASON_VALUES == (
        "INPUT_EXHAUSTED",
        "MAX_EVENTS_REACHED",
        "MAX_PINGS_REACHED",
        "LIVE_MODE_REFUSED",
    )


def test_live_authority_constants_match_stage_27_1_tokens():
    """Stage 27.6 mirrors Stage 27.1's authority tokens by value
    without importing Stage 27.1 production code.
    """
    assert LIVE_AUTHORITY_DRY_RUN == "DRY_RUN"
    assert LIVE_AUTHORITY_LIVE_REFUSED == "LIVE_REFUSED"
    assert LIVE_AUTHORITY_LIVE_ALLOWED == "LIVE_ALLOWED"


# ---------------------------------------------------------------------------
# Bounds validation
# ---------------------------------------------------------------------------


def test_runner_refuses_both_bounds_none():
    sources = _sol_sources()
    with pytest.raises(Stage27_6RunnerBoundsError):
        run_bounded_dry_run(
            iter([_sol_event()]),
            sources,
            clock=_FrozenClockISO(),
            max_events=None,
            max_pings=None,
            write_artifacts=False,
        )


def test_runner_refuses_non_positive_max_events():
    sources = _sol_sources()
    with pytest.raises(Stage27_6RunnerBoundsError):
        run_bounded_dry_run(
            iter([]),
            sources,
            clock=_FrozenClockISO(),
            max_events=0,
            write_artifacts=False,
        )
    with pytest.raises(Stage27_6RunnerBoundsError):
        run_bounded_dry_run(
            iter([]),
            sources,
            clock=_FrozenClockISO(),
            max_events=-1,
            write_artifacts=False,
        )


def test_runner_refuses_non_positive_max_pings():
    sources = _sol_sources()
    with pytest.raises(Stage27_6RunnerBoundsError):
        run_bounded_dry_run(
            iter([]),
            sources,
            clock=_FrozenClockISO(),
            max_pings=0,
            write_artifacts=False,
        )


def test_runner_refuses_bool_bounds():
    """``True`` / ``False`` must not satisfy the positive-int check."""
    sources = _sol_sources()
    with pytest.raises(Stage27_6RunnerBoundsError):
        run_bounded_dry_run(
            iter([]),
            sources,
            clock=_FrozenClockISO(),
            max_events=True,  # type: ignore[arg-type]
            write_artifacts=False,
        )


def test_runner_requires_output_root_when_write_artifacts_true():
    sources = _sol_sources()
    with pytest.raises(Stage27_6RunnerBoundsError):
        run_bounded_dry_run(
            iter([_sol_event()]),
            sources,
            clock=_FrozenClockISO(),
            max_events=1,
            output_root=None,
            write_artifacts=True,
        )


# ---------------------------------------------------------------------------
# Live mode refusal
# ---------------------------------------------------------------------------


def test_runner_refuses_live_allowed_authority(stage27_6_tmp_path):
    sources = _sol_sources()
    result = run_bounded_dry_run(
        iter([_sol_event()]),
        sources,
        clock=_FrozenClockISO(),
        output_root=stage27_6_tmp_path,
        max_events=10,
        live_mode_authority=LIVE_AUTHORITY_LIVE_ALLOWED,
        write_artifacts=True,
    )
    assert isinstance(result, Stage27_6BoundedDryRunRunResult)
    assert result.summary.mode == RUN_MODE_LIVE_REFUSED
    assert result.summary.stop_reason == STOP_REASON_LIVE_MODE_REFUSED
    # No event was processed, no artifact was written.
    assert result.candidates == ()
    assert result.summary.events_seen == 0
    assert result.summary.pings_rendered == 0
    assert result.summary.artifacts_written == 0
    assert tuple(stage27_6_tmp_path.iterdir()) == ()


def test_runner_optionally_raises_on_live_refused(stage27_6_tmp_path):
    sources = _sol_sources()
    with pytest.raises(Stage27_6LiveModeRefusedError):
        run_bounded_dry_run(
            iter([_sol_event()]),
            sources,
            clock=_FrozenClockISO(),
            output_root=stage27_6_tmp_path,
            max_events=10,
            live_mode_authority=LIVE_AUTHORITY_LIVE_ALLOWED,
            write_artifacts=True,
            raise_on_live_refused=True,
        )


def test_runner_runs_dry_for_non_live_authority(stage27_6_tmp_path):
    sources = _sol_sources()
    for authority in (
        LIVE_AUTHORITY_DRY_RUN,
        LIVE_AUTHORITY_LIVE_REFUSED,
        "ARBITRARY_DEFAULT",
    ):
        result = run_bounded_dry_run(
            iter([_sol_event(idx=hash(authority) % 10)]),
            sources,
            clock=_FrozenClockISO(),
            output_root=stage27_6_tmp_path,
            max_events=10,
            live_mode_authority=authority,
            write_artifacts=False,
        )
        assert result.summary.mode == RUN_MODE_DRY_RUN


# ---------------------------------------------------------------------------
# max_events stop
# ---------------------------------------------------------------------------


def test_runner_stops_at_max_events(stage27_6_tmp_path):
    sources = _sol_sources()
    events = [_sol_event(idx=i) for i in range(10)]
    result = run_bounded_dry_run(
        iter(events),
        sources,
        clock=_FrozenClockISO(),
        output_root=stage27_6_tmp_path,
        max_events=3,
        write_artifacts=True,
    )
    assert result.summary.events_seen == 3
    assert result.summary.stop_reason == STOP_REASON_MAX_EVENTS_REACHED
    assert len(result.candidates) == 3


# ---------------------------------------------------------------------------
# max_pings stop
# ---------------------------------------------------------------------------


def test_runner_stops_at_max_pings(stage27_6_tmp_path):
    sources = _sol_sources()
    # Mix SOL (renders) + UNKNOWN (suppressed) so events_seen >
    # pings_rendered. The runner should stop after pings_rendered
    # hits max_pings, not after events_seen.
    events = []
    for i in range(10):
        events.append(_unknown_event(idx=i))
        events.append(_sol_event(idx=i, token_mint=f"MintAAA{i}"))
    result = run_bounded_dry_run(
        iter(events),
        sources,
        clock=_FrozenClockISO(),
        output_root=stage27_6_tmp_path,
        max_pings=2,
        write_artifacts=True,
    )
    assert result.summary.pings_rendered == 2
    assert result.summary.stop_reason == STOP_REASON_MAX_PINGS_REACHED


# ---------------------------------------------------------------------------
# Deterministic counters
# ---------------------------------------------------------------------------


def test_runner_counts_all_categories(stage27_6_tmp_path):
    """Mix every event class and check the run summary counters."""
    sources = _sol_sources()
    events = [
        _sol_event(idx=1, token_mint="MintA1"),
        _sol_event(idx=1, token_mint="MintA1"),  # duplicate
        _usdc_event(idx=2),
        _unknown_event(idx=3),
        _disagree_event(idx=4),
        _unsupported_event(idx=5),
        _missing_token_event(idx=6),
    ]
    result = run_bounded_dry_run(
        iter(events),
        sources,
        clock=_FrozenClockISO(),
        output_root=stage27_6_tmp_path,
        max_events=100,
        write_artifacts=True,
    )
    assert result.summary.events_seen == 7
    assert result.summary.pings_rendered == 2  # SOL + USDC
    # 2 per render: SOL + USDC + UNKNOWN + DISAGREE = 4 candidates
    # persist a payload + provenance pair = 8 files.
    assert result.summary.artifacts_written == 8
    assert result.summary.duplicates_skipped == 1
    assert result.summary.unknown_suppressed == 1
    assert result.summary.disagree_suppressed == 1
    assert result.summary.unsupported_skipped == 2  # unsup + missing
    assert result.summary.artifact_write_failures == 0
    assert result.summary.errors == 0
    assert result.summary.stop_reason == STOP_REASON_INPUT_EXHAUSTED
    # The candidate statuses also pin the per-event verdicts.
    statuses = tuple(
        c.candidate_status for c in result.candidates
    )
    assert statuses == (
        CANDIDATE_STATUS_RENDERED_DRY_RUN,
        CANDIDATE_STATUS_SKIPPED_DUPLICATE,
        CANDIDATE_STATUS_RENDERED_DRY_RUN,
        CANDIDATE_STATUS_SUPPRESSED_UNKNOWN_PAIR,
        CANDIDATE_STATUS_SUPPRESSED_DISAGREE_PAIR,
        CANDIDATE_STATUS_SKIPPED_UNSUPPORTED_EVENT,
        CANDIDATE_STATUS_SKIPPED_MISSING_TOKEN,
    )


def test_runner_records_events_composed_count(stage27_6_tmp_path):
    sources = _sol_sources()
    events = [
        _sol_event(idx=1),
        _usdc_event(idx=2),
        _unknown_event(idx=3),
        _disagree_event(idx=4),
        _unsupported_event(idx=5),
    ]
    result = run_bounded_dry_run(
        iter(events),
        sources,
        clock=_FrozenClockISO(),
        output_root=stage27_6_tmp_path,
        max_events=100,
        write_artifacts=True,
    )
    # SOL + USDC composition_status is COMPOSED; UNKNOWN /
    # DISAGREE / UNSUPPORTED are not.
    assert result.summary.events_composed == 2


# ---------------------------------------------------------------------------
# Artifact-write counters
# ---------------------------------------------------------------------------


def test_runner_does_not_write_for_skipped_events(
    stage27_6_tmp_path,
):
    """SKIPPED_* candidates (no composition) never reach the writer.

    SUPPRESSED_* candidates (UNKNOWN / DISAGREE) DO render a Stage
    27.5 SUPPRESSED payload and persist an artifact pair so the
    operator has full provenance for the suppression decision; that
    case is exercised separately.
    """
    sources = _sol_sources()
    events = [
        _unsupported_event(idx=3),
        _missing_token_event(idx=4),
    ]
    result = run_bounded_dry_run(
        iter(events),
        sources,
        clock=_FrozenClockISO(),
        output_root=stage27_6_tmp_path,
        max_events=100,
        write_artifacts=True,
    )
    assert result.summary.artifacts_written == 0
    # The tmp dir is empty of dry-run artifacts.
    assert tuple(stage27_6_tmp_path.iterdir()) == ()


def test_runner_writes_for_suppressed_candidates(
    stage27_6_tmp_path,
):
    """UNKNOWN / DISAGREE candidates persist a SUPPRESSED dry-run
    artifact for operator review (Stage 27.5 renderer produces a
    SUPPRESSED ping payload; the writer persists it).
    """
    sources = _sol_sources()
    events = [
        _unknown_event(idx=1),
        _disagree_event(idx=2),
    ]
    result = run_bounded_dry_run(
        iter(events),
        sources,
        clock=_FrozenClockISO(),
        output_root=stage27_6_tmp_path,
        max_events=100,
        write_artifacts=True,
    )
    # SUPPRESSED candidates are NOT counted in pings_rendered (only
    # RENDERED_DRY_RUN is), but their artifact files ARE persisted.
    assert result.summary.pings_rendered == 0
    assert result.summary.unknown_suppressed == 1
    assert result.summary.disagree_suppressed == 1
    assert result.summary.artifacts_written == 4
    files = sorted(p.name for p in stage27_6_tmp_path.iterdir())
    assert len(files) == 4
    # Every persisted file is a Stage 27.5 dry-run artifact filename.
    for name in files:
        assert name.startswith("ping_")
        assert name.endswith((
            "_payload.json",
            "_provenance.json",
        ))


# ---------------------------------------------------------------------------
# Run summary canonical JSON / writer
# ---------------------------------------------------------------------------


def test_canonical_run_summary_json_is_stable(stage27_6_tmp_path):
    sources = _sol_sources()
    result = run_bounded_dry_run(
        iter([_sol_event(idx=1)]),
        sources,
        clock=_FrozenClockISO(),
        output_root=stage27_6_tmp_path,
        max_events=10,
        run_id="run-1",
        session_id="sess-1",
        write_artifacts=False,
    )
    a = canonical_run_summary_json(result.summary)
    b = canonical_run_summary_json(result.summary)
    assert a == b
    # JSON is parseable.
    parsed = json.loads(a)
    assert parsed["mode"] == RUN_MODE_DRY_RUN
    assert parsed["schema_version"] == (
        STAGE27_6_RUN_SUMMARY_SCHEMA_VERSION
    )
    assert parsed["candidate_schema_version"] == (
        STAGE27_6_CANDIDATE_SCHEMA_VERSION
    )


def test_default_run_summary_filename_handles_none():
    assert (
        default_run_summary_filename(None)
        == "run_unknown_summary.json"
    )
    assert default_run_summary_filename("") == (
        "run_unknown_summary.json"
    )
    assert default_run_summary_filename("abc") == (
        "run_abc_summary.json"
    )


def test_runner_writes_summary_artifact(stage27_6_tmp_path):
    sources = _sol_sources()
    result = run_bounded_dry_run(
        iter([_sol_event(idx=1)]),
        sources,
        clock=_FrozenClockISO(),
        output_root=stage27_6_tmp_path,
        max_events=10,
        run_id="run-1",
        session_id="sess-1",
        write_artifacts=True,
        write_summary_artifact=True,
    )
    assert result.summary.mode == RUN_MODE_DRY_RUN
    summary_path = (
        stage27_6_tmp_path / "run_run-1_summary.json"
    )
    assert summary_path.is_file()
    parsed = json.loads(
        summary_path.read_text(encoding="utf-8")
    )
    assert parsed["run_id"] == "run-1"
    assert parsed["session_id"] == "sess-1"
    assert parsed["pings_rendered"] == 1


def test_write_run_summary_artifact_refuses_path_traversal(
    stage27_6_tmp_path,
):
    summary = Stage27_6RunSummaryRecord(
        run_id="run-x",
        session_id=None,
        mode=RUN_MODE_DRY_RUN,
        events_seen=0,
        events_composed=0,
        candidates_assembled=0,
        pings_rendered=0,
        artifacts_written=0,
        duplicates_skipped=0,
        unknown_suppressed=0,
        disagree_suppressed=0,
        unsupported_skipped=0,
        artifact_write_failures=0,
        errors=0,
        started_at_utc=_FIXED_UTC_ISO,
        finished_at_utc=_FIXED_UTC_ISO,
        schema_version=STAGE27_6_RUN_SUMMARY_SCHEMA_VERSION,
        candidate_schema_version=(
            STAGE27_6_CANDIDATE_SCHEMA_VERSION
        ),
        stop_reason=STOP_REASON_INPUT_EXHAUSTED,
    )
    with pytest.raises(Stage27_5FilenameError):
        write_run_summary_artifact(
            summary, stage27_6_tmp_path, "../escape.json"
        )
    with pytest.raises(Stage27_5FilenameError):
        write_run_summary_artifact(
            summary, stage27_6_tmp_path, ".."
        )
    with pytest.raises(Stage27_5FilenameError):
        write_run_summary_artifact(
            summary, stage27_6_tmp_path, "a\\b.json"
        )


def test_write_run_summary_artifact_refuses_missing_root():
    summary = Stage27_6RunSummaryRecord(
        run_id="run-x",
        session_id=None,
        mode=RUN_MODE_DRY_RUN,
        events_seen=0,
        events_composed=0,
        candidates_assembled=0,
        pings_rendered=0,
        artifacts_written=0,
        duplicates_skipped=0,
        unknown_suppressed=0,
        disagree_suppressed=0,
        unsupported_skipped=0,
        artifact_write_failures=0,
        errors=0,
        started_at_utc=_FIXED_UTC_ISO,
        finished_at_utc=_FIXED_UTC_ISO,
        schema_version=STAGE27_6_RUN_SUMMARY_SCHEMA_VERSION,
        candidate_schema_version=(
            STAGE27_6_CANDIDATE_SCHEMA_VERSION
        ),
        stop_reason=STOP_REASON_INPUT_EXHAUSTED,
    )
    with pytest.raises(Stage27_5OutputRootError):
        write_run_summary_artifact(
            summary,
            Path("Z:/non_existent_path_for_stage27_6_test"),
        )


# ---------------------------------------------------------------------------
# Run summary determinism
# ---------------------------------------------------------------------------


def test_two_identical_runs_produce_equal_summaries(
    stage27_6_tmp_path,
):
    sources = _sol_sources()
    events = [_sol_event(idx=1)]

    result_a = run_bounded_dry_run(
        iter(events),
        sources,
        clock=_FrozenClockISO(),
        output_root=stage27_6_tmp_path / "a",
        max_events=10,
        run_id="run-1",
        session_id="sess-1",
        write_artifacts=False,
    )

    # Stage 27.6 path resolution requires the output_root to exist,
    # so create it first for the test.
    (stage27_6_tmp_path / "a").mkdir(exist_ok=True)
    result_a = run_bounded_dry_run(
        iter(events),
        sources,
        clock=_FrozenClockISO(),
        output_root=None,
        max_events=10,
        run_id="run-1",
        session_id="sess-1",
        write_artifacts=False,
    )

    result_b = run_bounded_dry_run(
        iter([_sol_event(idx=1)]),
        sources,
        clock=_FrozenClockISO(),
        output_root=None,
        max_events=10,
        run_id="run-1",
        session_id="sess-1",
        write_artifacts=False,
    )

    assert canonical_run_summary_json(
        result_a.summary
    ) == canonical_run_summary_json(result_b.summary)


# ---------------------------------------------------------------------------
# No transport surface
# ---------------------------------------------------------------------------


def test_runner_module_has_no_discord_transport():
    """Defensive: Stage 27.6 must not import any Discord client or
    webhook surface anywhere in the runner module's namespace.
    """
    import PHX2.stage27.bounded_tradeable_ping_runner as runner_mod

    forbidden = (
        "discord",
        "webhook",
        "send_message",
        "post_to_discord",
        "discord_client",
        "telegram",
        "tweepy",
    )
    for name in dir(runner_mod):
        lower = name.lower()
        for needle in forbidden:
            assert needle not in lower, (
                f"runner module attribute {name!r} contains "
                f"forbidden substring {needle!r}"
            )


def test_runner_module_has_no_network_import():
    """The runner module imports only stdlib + Stage 27 production."""
    import PHX2.stage27.bounded_tradeable_ping_runner as runner_mod
    import inspect

    source = inspect.getsource(runner_mod)
    for needle in (
        "import requests",
        "import httpx",
        "import aiohttp",
        "import urllib3",
        "import websockets",
        "import grpc",
        "import discord",
        "from discord",
        "from telegram",
    ):
        assert needle not in source, (
            f"runner module must not contain {needle!r}"
        )

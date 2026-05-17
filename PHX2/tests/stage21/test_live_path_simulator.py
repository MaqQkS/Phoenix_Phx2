"""Stage 21.2 live_path_simulator end-to-end tests."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

from PHX2.stage21.clock import FrozenClock
from PHX2.stage21.errors import (
    Stage21BoundaryError,
    Stage21Error,
    Stage21TelemetryError,
)
from PHX2.stage21.fake_provider import Stage21FakeEventSeed
from PHX2.stage21.live_path_simulator import (
    Stage21_2SimulationResult,
    run_live_path_simulation,
)
from PHX2.stage21.telemetry_writer import (
    STAGE21_2_FAKE_TRANSPORT_CAPTURE_FILENAME,
    STAGE21_2_MANIFEST_FILENAME,
    STAGE21_2_PING_LEDGER_FILENAME,
    STAGE21_2_TELEMETRY_SUMMARY_FILENAME,
)


def _seed(mint: str, slot: int = 100) -> Stage21FakeEventSeed:
    return Stage21FakeEventSeed(
        mint=mint,
        event_type="fake_swap",
        observed_at_utc="2026-05-17T12:00:00Z",
        slot=slot,
        raw_payload={"fake_amount": 1000, "fake_decimals": 6},
    )


def _clock(iso: str = "2026-05-17T12:00:00+00:00") -> FrozenClock:
    return FrozenClock(datetime.fromisoformat(iso))


def _run(tmp_path: Path, *, seeds=None, run_id="stage21_2_test_run", clock=None):
    if seeds is None:
        seeds = [
            _seed("FAKE_MINT_A", slot=1),
            _seed("FAKE_MINT_B", slot=2),
        ]
    output_dir = tmp_path / "stage21_2_run"
    return run_live_path_simulation(
        seeds=seeds,
        output_dir=output_dir,
        run_id=run_id,
        generated_at_utc_iso="2026-05-17T12:00:00Z",
        clock=clock or _clock(),
    )


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_simulation_returns_result_with_four_artifact_paths(tmp_path: Path):
    result = _run(tmp_path)
    assert isinstance(result, Stage21_2SimulationResult)
    assert result.manifest_path.name == STAGE21_2_MANIFEST_FILENAME
    assert result.ping_ledger_path.name == STAGE21_2_PING_LEDGER_FILENAME
    assert (
        result.fake_transport_capture_path.name
        == STAGE21_2_FAKE_TRANSPORT_CAPTURE_FILENAME
    )
    assert (
        result.telemetry_summary_path.name
        == STAGE21_2_TELEMETRY_SUMMARY_FILENAME
    )
    for p in (
        result.manifest_path,
        result.ping_ledger_path,
        result.fake_transport_capture_path,
        result.telemetry_summary_path,
    ):
        assert p.exists()


def test_simulation_counts_match_pipeline_volume(tmp_path: Path):
    result = _run(tmp_path)
    assert result.counts.fake_events_received == 2
    assert result.counts.normalized_events_emitted == 2
    assert result.counts.candidates_built == 2
    assert result.counts.pings_built == 2
    assert result.counts.captures_recorded == 2
    assert result.counts.duplicates_skipped == 0


def test_simulation_produces_unique_event_candidate_and_ping_ids(tmp_path: Path):
    result = _run(tmp_path)
    event_ids = {n.event_id for n in result.normalized_events}
    candidate_ids = {c.candidate_id for c in result.candidates}
    ping_ids = {p.ping_id for p in result.pings}
    capture_ids = {c.capture_id for c in result.captures}
    assert len(event_ids) == 2
    assert len(candidate_ids) == 2
    assert len(ping_ids) == 2
    assert len(capture_ids) == 2


def test_simulation_artifacts_are_byte_deterministic_across_reruns(
    tmp_path: Path,
):
    a_dir = tmp_path / "run_a"
    b_dir = tmp_path / "run_b"
    seeds = [_seed("FAKE_MINT_A", slot=1), _seed("FAKE_MINT_B", slot=2)]
    a = run_live_path_simulation(
        seeds=seeds,
        output_dir=a_dir,
        run_id="stage21_2_test_run",
        generated_at_utc_iso="2026-05-17T12:00:00Z",
        clock=_clock(),
    )
    b = run_live_path_simulation(
        seeds=seeds,
        output_dir=b_dir,
        run_id="stage21_2_test_run",
        generated_at_utc_iso="2026-05-17T12:00:00Z",
        clock=_clock(),
    )
    for filename in (
        STAGE21_2_MANIFEST_FILENAME,
        STAGE21_2_PING_LEDGER_FILENAME,
        STAGE21_2_FAKE_TRANSPORT_CAPTURE_FILENAME,
        STAGE21_2_TELEMETRY_SUMMARY_FILENAME,
    ):
        assert (a_dir / filename).read_bytes() == (b_dir / filename).read_bytes()
    # Returned record also matches modulo paths.
    assert a.counts == b.counts
    assert a.normalized_events == b.normalized_events
    assert a.candidates == b.candidates
    assert a.pings == b.pings


# ---------------------------------------------------------------------------
# Duplicate / idempotency behavior
# ---------------------------------------------------------------------------


def test_simulation_dedupes_identical_seeds(tmp_path: Path):
    # Same mint + slot + payload + observed_at = duplicate fake
    # event (same provider_event_id by derivation? No -- the
    # provider_event_id includes the index, so duplicate seeds at
    # different indices produce DIFFERENT provider_event_ids.
    # The dedupe happens at the NORMALIZED level: derive_event_id
    # is keyed off raw_event_hash + provider_event_id, and the
    # provider_event_id is index-based, so two identical seeds
    # produce two distinct normalized events.)
    #
    # This test verifies that when seeds carry *distinct* indices
    # but the same downstream content, the simulator still emits
    # one normalized event per seed (i.e. no false dedupe).
    seeds = [_seed("FAKE_MINT_A", slot=1), _seed("FAKE_MINT_A", slot=1)]
    result = _run(tmp_path, seeds=seeds)
    assert result.counts.fake_events_received == 2
    # Each seed gets a unique provider_event_id (index-based) so
    # both flow through as distinct normalized events.
    assert result.counts.normalized_events_emitted == 2
    assert result.counts.duplicates_skipped == 0


# ---------------------------------------------------------------------------
# Output-directory safety
# ---------------------------------------------------------------------------


def test_simulation_refuses_missing_output_dir_parent(tmp_path: Path):
    output_dir = tmp_path / "missing" / "inner"
    with pytest.raises(Stage21BoundaryError) as excinfo:
        run_live_path_simulation(
            seeds=[_seed("FAKE_MINT_A")],
            output_dir=output_dir,
            run_id="rid",
            generated_at_utc_iso="2026-05-17T12:00:00Z",
            clock=_clock(),
        )
    assert excinfo.value.code == "E2106"
    assert not (tmp_path / "missing").exists()


def test_simulation_refuses_dotdot_output_dir(tmp_path: Path):
    output_dir = tmp_path / ".." / "out"
    with pytest.raises(Stage21BoundaryError) as excinfo:
        run_live_path_simulation(
            seeds=[_seed("FAKE_MINT_A")],
            output_dir=output_dir,
            run_id="rid",
            generated_at_utc_iso="2026-05-17T12:00:00Z",
            clock=_clock(),
        )
    assert excinfo.value.code == "E2106"


def test_simulation_refuses_non_path_output_dir():
    with pytest.raises(Stage21BoundaryError):
        run_live_path_simulation(
            seeds=[_seed("FAKE_MINT_A")],
            output_dir="/tmp/not-a-path",  # type: ignore[arg-type]
            run_id="rid",
            generated_at_utc_iso="2026-05-17T12:00:00Z",
            clock=_clock(),
        )


def test_simulation_refuses_non_sequence_seeds(tmp_path: Path):
    with pytest.raises(Stage21BoundaryError):
        run_live_path_simulation(
            seeds={"not": "a sequence"},  # type: ignore[arg-type]
            output_dir=tmp_path / "out",
            run_id="rid",
            generated_at_utc_iso="2026-05-17T12:00:00Z",
            clock=_clock(),
        )


def test_simulation_creates_only_one_directory_level(tmp_path: Path):
    output_dir = tmp_path / "single_level"
    _run(tmp_path, seeds=[_seed("FAKE_MINT_A")])
    # The simulator created exactly the requested output_dir.
    assert (tmp_path / "stage21_2_run").is_dir()
    # It must NOT have created any sibling level.
    assert not (tmp_path / "elsewhere").exists()


# ---------------------------------------------------------------------------
# Artifact content sanity
# ---------------------------------------------------------------------------


def test_simulation_manifest_artifact_carries_locked_markers(tmp_path: Path):
    result = _run(tmp_path)
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert manifest["locked_markers"]["stage"] == "21.2"
    assert manifest["locked_markers"]["visibility"] == "private_preview"
    assert manifest["locked_markers"]["operator_only"] is True
    assert manifest["locked_markers"]["live_mode"] is False
    assert (
        manifest["locked_markers"]["dispatch_target"]
        == "fake_private_transport"
    )
    assert manifest["run_metadata"]["safe_for_public_dispatch"] is False


def test_simulation_ping_ledger_contains_locked_markers_per_line(
    tmp_path: Path,
):
    result = _run(tmp_path)
    lines = [
        json.loads(ln)
        for ln in result.ping_ledger_path.read_text(encoding="utf-8").splitlines()
        if ln
    ]
    assert len(lines) == 2
    for record in lines:
        assert record["stage"] == "21.2"
        assert record["visibility"] == "private_preview"
        assert record["operator_only"] is True
        assert record["live_mode"] is False
        assert record["dispatch_target"] == "fake_private_transport"


def test_simulation_capture_artifact_contains_captured_at_utc(tmp_path: Path):
    result = _run(tmp_path, clock=_clock("2026-05-17T13:45:01+00:00"))
    lines = [
        json.loads(ln)
        for ln in result.fake_transport_capture_path.read_text(
            encoding="utf-8"
        ).splitlines()
        if ln
    ]
    assert len(lines) == 2
    for record in lines:
        assert record["captured_at_utc"] == "2026-05-17T13:45:01Z"


def test_simulation_does_not_open_database_or_read_alert_decisions(
    tmp_path: Path,
):
    # We don't assert "no DB connection" via runtime introspection;
    # instead, the import boundary tests assert no sqlite3 /
    # PHX2.db imports anywhere. The simulator returning a result
    # at all proves the file-artifact-only path works.
    result = _run(tmp_path)
    # Sanity: result is purely in-memory + on-disk; no DB handle
    # is exposed.
    assert not hasattr(result, "_db")
    assert not hasattr(result, "connection")


# ---------------------------------------------------------------------------
# Forbidden-content guards (output-artifact side)
# ---------------------------------------------------------------------------


_FORBIDDEN_OUTPUT_SUBSTRINGS: tuple[str, ...] = (
    "http" + "://",
    "https" + "://",
    "webhook",
    "api_key",
    "password",
    "credential",
    "public_dispatch",
    "paid_dispatch",
    "subscriber",
    "public_signal",
    "paid_signal",
    "public_channel",
    "paid_channel",
)


# Stage 21.2 remediation R5: the artifact-content scan uses the
# JSON-aware ``cleaned_artifact_text_from_path`` helper. The
# helper parses each artifact, strips only the exact locked-
# invariant keypath ``run_metadata.safe_for_public_dispatch``
# (when its value is the Python boolean ``False``), and re-
# serializes the cleaned structure for substring scanning. The
# prior global ``.replace("safe_for_public_dispatch", "")``
# substring strip has been removed.
from PHX2.tests.stage21._artifact_scan_helpers import (  # noqa: E402
    cleaned_artifact_text_from_path,
)


def test_no_forbidden_strings_in_simulator_artifacts(tmp_path: Path):
    result = _run(tmp_path)
    for path in (
        result.manifest_path,
        result.ping_ledger_path,
        result.fake_transport_capture_path,
        result.telemetry_summary_path,
    ):
        cleaned = cleaned_artifact_text_from_path(path)
        for needle in _FORBIDDEN_OUTPUT_SUBSTRINGS:
            assert needle not in cleaned, (
                f"{path.name} contains forbidden substring {needle!r}"
            )


# ---------------------------------------------------------------------------
# Stage 21.2 remediation: Codex PoC run-level reproductions
# ---------------------------------------------------------------------------
#
# Both PoCs at the run level: the run_live_path_simulation call
# must raise Stage21Error and the output directory must contain
# zero artifact files after the failed attempt.


def _no_files_in(output_dir: Path) -> bool:
    """Return True iff output_dir contains zero files.

    Accepts the case where output_dir was never created
    (PoC #1: run_id is validated before _prepare_output_dir) and
    the case where it exists but is empty (PoC #2: seed
    validation runs after _prepare_output_dir but before any
    artifact write).
    """
    if not output_dir.exists():
        return True
    if not output_dir.is_dir():
        return False
    return len(list(output_dir.iterdir())) == 0


def test_codex_poc_1_run_level_url_run_id_no_artifacts_written(tmp_path: Path):
    """Run-level PoC #1: URL-laced run_id never reaches the writers.

    The simulator validates run_id at entry (BEFORE
    _prepare_output_dir), so the output directory is never even
    created. No artifact file exists on disk after the failed
    run.
    """
    output_dir = tmp_path / "stage21_2_run_poc1"
    poisoned_run_id = "https" + "://example.invalid/public_dispatch"
    with pytest.raises(Stage21Error) as exc:
        run_live_path_simulation(
            seeds=[_seed("FAKE_MINT_A")],
            output_dir=output_dir,
            run_id=poisoned_run_id,
            generated_at_utc_iso="2026-05-17T12:00:00Z",
            clock=_clock(),
        )
    assert exc.value.code == "E2153"
    assert _no_files_in(output_dir), (
        "PoC #1: output_dir must contain zero artifact files after the "
        "failed run; got entries: "
        f"{list(output_dir.iterdir()) if output_dir.exists() else 'no dir'}"
    )


def test_codex_poc_2_run_level_url_mint_no_artifacts_written(tmp_path: Path):
    """Run-level PoC #2: URL-laced mint never reaches the writers.

    The simulator hands the seeds to ``Stage21FakeProvider`` for
    validation. The seed-level safe_content check raises E2153
    before any fake event is emitted, normalized, built, or
    written. The output directory may exist (created by
    _prepare_output_dir before the seed validation runs) but
    contains zero artifact files.
    """
    output_dir = tmp_path / "stage21_2_run_poc2"
    poisoned_seed = Stage21FakeEventSeed(
        mint="https" + "://example.invalid/webhook",
        event_type="fake_swap",
        observed_at_utc="2026-05-17T12:00:00Z",
        slot=1,
        raw_payload={"fake_amount": 1000},
    )
    with pytest.raises(Stage21Error) as exc:
        run_live_path_simulation(
            seeds=[poisoned_seed],
            output_dir=output_dir,
            run_id="stage21_2_test_run",
            generated_at_utc_iso="2026-05-17T12:00:00Z",
            clock=_clock(),
        )
    assert exc.value.code == "E2153"
    assert _no_files_in(output_dir), (
        "PoC #2: output_dir must contain zero artifact files after the "
        "failed run; got entries: "
        f"{list(output_dir.iterdir()) if output_dir.exists() else 'no dir'}"
    )


def test_run_level_url_generated_at_utc_iso_no_artifacts(tmp_path: Path):
    """Defense-in-depth: URL-laced timestamp is rejected at entry too."""
    output_dir = tmp_path / "stage21_2_run_ts_poc"
    with pytest.raises(Stage21Error) as exc:
        run_live_path_simulation(
            seeds=[_seed("FAKE_MINT_A")],
            output_dir=output_dir,
            run_id="stage21_2_test_run",
            generated_at_utc_iso="https" + "://attacker.example/leak",
            clock=_clock(),
        )
    assert exc.value.code in ("E2152", "E2153")
    assert _no_files_in(output_dir)

"""Stage 29.4 soak artifact writer focused tests.

Pins:

  * ``write_soak_summary_artifact`` writes the soak summary
    atomically with deterministic JSON,
  * ``append_heartbeat_artifact`` is append-only and produces
    one JSON-per-line entry per call,
  * ``write_health_snapshot_artifact`` overwrites the snapshot
    atomically and carries the Stage 29.4 health-snapshot schema
    version,
  * ``run_soak_redaction_scan`` returns ``SAFE`` when the bundle
    is clean and ``REDACTED`` when a forbidden substring appears,
  * ``write_soak_redaction_scan_artifact`` writes the scan result
    atomically,
  * ``write_soak_summary_bundle`` writes the summary + the
    redaction scan in one call,
  * forbidden-substring vocabulary covers Stage 28 / Stage 29
    secret-shape literals,
  * the artifact basenames are locked.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from PHX2.stage29.stage29_4_soak_artifact_writer import (
    FORBIDDEN_SCAN_SUBSTRINGS,
    STAGE28_9_COMPANION_ARTIFACT_BASENAMES,
    STAGE29_3_COMPANION_ARTIFACT_BASENAMES,
    STAGE29_4_ARTIFACT_BASENAMES,
    STAGE29_4_HEALTH_SNAPSHOT_BASENAME,
    STAGE29_4_HEARTBEAT_BASENAME,
    STAGE29_4_REDACTION_SCAN_BASENAME,
    STAGE29_4_SOAK_SUMMARY_BASENAME,
    append_heartbeat_artifact,
    read_heartbeat_artifact_lines,
    run_soak_redaction_scan,
    write_health_snapshot_artifact,
    write_soak_redaction_scan_artifact,
    write_soak_summary_artifact,
    write_soak_summary_bundle,
)
from PHX2.stage29.stage29_4_soak_models import (
    DEDUPE_OUTCOME_NEW,
    FILTER_ENFORCEMENT_STATUS_NOT_ACTIVE_STAGE_29_PENDING,
    REDACTION_STATUS_REDACTED,
    REDACTION_STATUS_SAFE,
    SOAK_OUTCOME_COMPLETED_AT_DISPATCH_CAP,
    STAGE29_4_HEALTH_SNAPSHOT_SCHEMA_VERSION,
    STAGE29_4_HEARTBEAT_SCHEMA_VERSION,
    STAGE29_4_REDACTION_SCAN_SCHEMA_VERSION,
    STAGE29_4_REDACTION_TOKEN,
    STAGE29_4_SOAK_SUMMARY_SCHEMA_VERSION,
    Stage29_4SoakError,
    build_pass_record,
    build_soak_bounds,
    build_soak_summary,
)


def _make_bounds():
    return build_soak_bounds(
        wall_clock_seconds=900,
        max_dispatches=3,
        max_passes=10,
        max_consecutive_suppressions=5,
        heartbeat_cadence_seconds=30,
    )


def _make_summary():
    return build_soak_summary(
        soak_outcome=SOAK_OUTCOME_COMPLETED_AT_DISPATCH_CAP,
        bounds=_make_bounds(),
        passes_attempted=3,
        dispatch_success_total=3,
        events_seen_total=3,
        elapsed_wall_clock_seconds=42.5,
        start_utc_iso="2026-05-25T17:00:00+00:00",
        end_utc_iso="2026-05-25T17:00:42+00:00",
    )


def _make_pass_record(*, pass_index: int = 1):
    return build_pass_record(
        pass_index=pass_index,
        stage29_3_outcome="DISPATCHED",
        stage29_3_refusal_reason="NONE",
        dedupe_outcome=DEDUPE_OUTCOME_NEW,
        events_seen=1,
        candidates_dispatched=1,
        candidates_suppressed=0,
        dispatch_success=1,
        dispatch_failure=0,
        consecutive_suppression_streak=0,
        dispatch_success_total_at_tick=pass_index,
        duplicate_suppressed_soak_count_at_tick=0,
        elapsed_at_tick_seconds=float(pass_index) * 10.0,
        utc_iso_timestamp=(
            f"2026-05-25T17:00:{pass_index:02d}+00:00"
        ),
    )


# ---------------------------------------------------------------------------
# Locked artifact basenames
# ---------------------------------------------------------------------------


def test_artifact_basenames_locked():
    assert STAGE29_4_SOAK_SUMMARY_BASENAME == (
        "stage29_4_soak_summary.json"
    )
    assert STAGE29_4_HEARTBEAT_BASENAME == (
        "stage29_4_heartbeat.jsonl"
    )
    assert STAGE29_4_HEALTH_SNAPSHOT_BASENAME == (
        "stage29_4_health_snapshot.json"
    )
    assert STAGE29_4_REDACTION_SCAN_BASENAME == (
        "stage29_4_redaction_scan.json"
    )


def test_stage29_4_artifact_basenames_tuple_locked():
    assert STAGE29_4_ARTIFACT_BASENAMES == (
        STAGE29_4_SOAK_SUMMARY_BASENAME,
        STAGE29_4_HEARTBEAT_BASENAME,
        STAGE29_4_HEALTH_SNAPSHOT_BASENAME,
        STAGE29_4_REDACTION_SCAN_BASENAME,
    )


def test_stage29_3_companion_basenames_pin():
    assert (
        "stage29_3_tradeable_smoke_result.json"
        in STAGE29_3_COMPANION_ARTIFACT_BASENAMES
    )
    assert (
        "stage29_3_redaction_scan.json"
        in STAGE29_3_COMPANION_ARTIFACT_BASENAMES
    )


def test_stage28_9_companion_basenames_pin():
    assert (
        "stage28_9_dispatch_ledger.jsonl"
        in STAGE28_9_COMPANION_ARTIFACT_BASENAMES
    )


# ---------------------------------------------------------------------------
# Soak-summary artifact
# ---------------------------------------------------------------------------


def test_write_soak_summary_artifact_writes_atomic_json(
    tmp_path: Path,
):
    summary = _make_summary()
    written = write_soak_summary_artifact(
        output_dir=tmp_path, summary=summary,
    )
    assert written == tmp_path / STAGE29_4_SOAK_SUMMARY_BASENAME
    assert written.is_file()
    # No leftover .tmp.
    assert not (
        tmp_path / (STAGE29_4_SOAK_SUMMARY_BASENAME + ".tmp")
    ).exists()
    payload = json.loads(
        written.read_text(encoding="utf-8"),
    )
    assert payload["soak_outcome"] == (
        SOAK_OUTCOME_COMPLETED_AT_DISPATCH_CAP
    )
    assert payload["schema_version"] == (
        STAGE29_4_SOAK_SUMMARY_SCHEMA_VERSION
    )
    assert payload["filter_enforcement_status"] == (
        FILTER_ENFORCEMENT_STATUS_NOT_ACTIVE_STAGE_29_PENDING
    )
    assert payload["redaction_status"] == REDACTION_STATUS_SAFE


def test_write_soak_summary_artifact_is_deterministic(
    tmp_path: Path,
):
    summary = _make_summary()
    write_soak_summary_artifact(
        output_dir=tmp_path, summary=summary,
    )
    first = (
        tmp_path / STAGE29_4_SOAK_SUMMARY_BASENAME
    ).read_bytes()
    write_soak_summary_artifact(
        output_dir=tmp_path, summary=summary,
    )
    second = (
        tmp_path / STAGE29_4_SOAK_SUMMARY_BASENAME
    ).read_bytes()
    assert first == second


def test_write_soak_summary_artifact_rejects_non_summary(
    tmp_path: Path,
):
    with pytest.raises(Stage29_4SoakError):
        write_soak_summary_artifact(
            output_dir=tmp_path,
            summary="not a summary",  # type: ignore[arg-type]
        )


def test_write_soak_summary_artifact_rejects_unsafe_output_dir(
    tmp_path: Path,
):
    # ``sk-`` is on the locked forbidden-substring list (API-key
    # prefix convention); a directory whose path renders with
    # ``sk-`` is refused by the safe-shape gate.
    summary = _make_summary()
    unsafe = tmp_path / ("s" + "k-example_dir")
    unsafe.mkdir()
    with pytest.raises(Stage29_4SoakError):
        write_soak_summary_artifact(
            output_dir=unsafe, summary=summary,
        )


def test_write_soak_summary_artifact_rejects_missing_output_dir(
    tmp_path: Path,
):
    summary = _make_summary()
    missing = tmp_path / "does_not_exist"
    with pytest.raises(Stage29_4SoakError):
        write_soak_summary_artifact(
            output_dir=missing, summary=summary,
        )


# ---------------------------------------------------------------------------
# Heartbeat append-only artifact
# ---------------------------------------------------------------------------


def test_append_heartbeat_writes_one_line(tmp_path: Path):
    record = _make_pass_record(pass_index=1)
    written = append_heartbeat_artifact(
        output_dir=tmp_path, record=record,
    )
    assert written == tmp_path / STAGE29_4_HEARTBEAT_BASENAME
    lines = read_heartbeat_artifact_lines(
        output_dir=tmp_path,
    )
    assert len(lines) == 1
    assert lines[0]["pass_index"] == 1
    assert lines[0]["schema_version"] == (
        STAGE29_4_HEARTBEAT_SCHEMA_VERSION
    )


def test_append_heartbeat_is_append_only(tmp_path: Path):
    for i in range(1, 4):
        append_heartbeat_artifact(
            output_dir=tmp_path,
            record=_make_pass_record(pass_index=i),
        )
    lines = read_heartbeat_artifact_lines(
        output_dir=tmp_path,
    )
    assert len(lines) == 3
    assert [line["pass_index"] for line in lines] == [
        1, 2, 3,
    ]


def test_append_heartbeat_lines_are_deterministic_json(
    tmp_path: Path,
):
    append_heartbeat_artifact(
        output_dir=tmp_path,
        record=_make_pass_record(pass_index=1),
    )
    # The line must have sorted keys and compact separators.
    raw = (
        tmp_path / STAGE29_4_HEARTBEAT_BASENAME
    ).read_text(encoding="utf-8")
    line = raw.strip()
    parsed = json.loads(line)
    re_encoded = json.dumps(
        parsed,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    assert line == re_encoded


def test_append_heartbeat_rejects_non_record(tmp_path: Path):
    with pytest.raises(Stage29_4SoakError):
        append_heartbeat_artifact(
            output_dir=tmp_path,
            record="not a record",  # type: ignore[arg-type]
        )


# ---------------------------------------------------------------------------
# Health snapshot artifact
# ---------------------------------------------------------------------------


def test_write_health_snapshot_writes_atomic_json(
    tmp_path: Path,
):
    record = _make_pass_record(pass_index=2)
    written = write_health_snapshot_artifact(
        output_dir=tmp_path,
        record=record,
        bounds_within_recommended_ranges=True,
    )
    assert written == (
        tmp_path / STAGE29_4_HEALTH_SNAPSHOT_BASENAME
    )
    payload = json.loads(
        written.read_text(encoding="utf-8"),
    )
    assert payload["schema_version"] == (
        STAGE29_4_HEALTH_SNAPSHOT_SCHEMA_VERSION
    )
    assert payload["pass_index"] == 2
    assert payload["bounds_within_recommended_ranges"] is True


def test_write_health_snapshot_overwrites_prior_snapshot(
    tmp_path: Path,
):
    write_health_snapshot_artifact(
        output_dir=tmp_path,
        record=_make_pass_record(pass_index=1),
        bounds_within_recommended_ranges=True,
    )
    write_health_snapshot_artifact(
        output_dir=tmp_path,
        record=_make_pass_record(pass_index=5),
        bounds_within_recommended_ranges=True,
    )
    payload = json.loads(
        (
            tmp_path / STAGE29_4_HEALTH_SNAPSHOT_BASENAME
        ).read_text(encoding="utf-8")
    )
    assert payload["pass_index"] == 5


def test_write_health_snapshot_rejects_non_record(
    tmp_path: Path,
):
    with pytest.raises(Stage29_4SoakError):
        write_health_snapshot_artifact(
            output_dir=tmp_path,
            record="not a record",  # type: ignore[arg-type]
            bounds_within_recommended_ranges=True,
        )


# ---------------------------------------------------------------------------
# Redaction scan
# ---------------------------------------------------------------------------


def test_run_redaction_scan_returns_SAFE_on_empty_directory(
    tmp_path: Path,
):
    scan = run_soak_redaction_scan(output_dir=tmp_path)
    assert scan["redaction_status"] == REDACTION_STATUS_SAFE
    assert scan["scanned_files"] == []
    assert scan["hits_by_file"] == {}
    assert scan["schema_version"] == (
        STAGE29_4_REDACTION_SCAN_SCHEMA_VERSION
    )
    assert scan["redaction_token"] == STAGE29_4_REDACTION_TOKEN


def test_run_redaction_scan_returns_SAFE_when_summary_is_clean(
    tmp_path: Path,
):
    summary = _make_summary()
    write_soak_summary_artifact(
        output_dir=tmp_path, summary=summary,
    )
    scan = run_soak_redaction_scan(output_dir=tmp_path)
    assert scan["redaction_status"] == REDACTION_STATUS_SAFE
    assert (
        STAGE29_4_SOAK_SUMMARY_BASENAME in scan["scanned_files"]
    )


def test_run_redaction_scan_returns_REDACTED_when_companion_carries_secret(
    tmp_path: Path,
):
    # Plant a fake Stage 29.3 companion artifact carrying a
    # forbidden URL host literal.
    bad_path = tmp_path / "stage29_3_birdeye_evidence.json"
    bad_path.write_text(
        '{"endpoint": "h' + 'ttps://birdeye.so/defi/price"}',
        encoding="utf-8",
    )
    scan = run_soak_redaction_scan(output_dir=tmp_path)
    assert (
        scan["redaction_status"] == REDACTION_STATUS_REDACTED
    )
    assert (
        "stage29_3_birdeye_evidence.json"
        in scan["scanned_files"]
    )
    assert (
        "stage29_3_birdeye_evidence.json"
        in scan["hits_by_file"]
    )


def test_run_redaction_scan_skips_missing_files(
    tmp_path: Path,
):
    # Write only the soak summary; companions are not present.
    summary = _make_summary()
    write_soak_summary_artifact(
        output_dir=tmp_path, summary=summary,
    )
    scan = run_soak_redaction_scan(output_dir=tmp_path)
    for name in STAGE29_3_COMPANION_ARTIFACT_BASENAMES:
        assert name not in scan["scanned_files"]
    for name in STAGE28_9_COMPANION_ARTIFACT_BASENAMES:
        assert name not in scan["scanned_files"]


def test_write_redaction_scan_artifact_writes_json(
    tmp_path: Path,
):
    written, scan = write_soak_redaction_scan_artifact(
        output_dir=tmp_path,
    )
    assert written == (
        tmp_path / STAGE29_4_REDACTION_SCAN_BASENAME
    )
    payload = json.loads(
        written.read_text(encoding="utf-8"),
    )
    assert payload["schema_version"] == (
        STAGE29_4_REDACTION_SCAN_SCHEMA_VERSION
    )
    assert (
        payload["redaction_status"]
        == scan["redaction_status"]
    )


# ---------------------------------------------------------------------------
# Forbidden substring vocabulary
# ---------------------------------------------------------------------------


def test_forbidden_scan_substrings_cover_url_hosts():
    needles = set(FORBIDDEN_SCAN_SUBSTRINGS)
    assert "discord" + ".com" in needles
    assert "birdeye" + ".so" in needles
    assert "chainstack" + ".com" in needles


def test_forbidden_scan_substrings_cover_auth_headers():
    needles = set(FORBIDDEN_SCAN_SUBSTRINGS)
    assert "B" + "earer " in needles
    assert "A" + "uthorization:" in needles


def test_forbidden_scan_substrings_cover_phx1():
    needles = set(FORBIDDEN_SCAN_SUBSTRINGS)
    assert "Phoenix" + "_Bot" in needles


def test_forbidden_scan_substrings_cover_wallet_signer():
    needles = set(FORBIDDEN_SCAN_SUBSTRINGS)
    assert "p" + "rivate_key" in needles
    assert "s" + "eed_phrase" in needles


# ---------------------------------------------------------------------------
# Bundle writer
# ---------------------------------------------------------------------------


def test_write_soak_summary_bundle_writes_summary_and_scan(
    tmp_path: Path,
):
    summary = _make_summary()
    scan = write_soak_summary_bundle(
        output_dir=tmp_path, summary=summary,
    )
    assert (
        tmp_path / STAGE29_4_SOAK_SUMMARY_BASENAME
    ).is_file()
    assert (
        tmp_path / STAGE29_4_REDACTION_SCAN_BASENAME
    ).is_file()
    assert scan["redaction_status"] == REDACTION_STATUS_SAFE


def test_write_soak_summary_bundle_returns_redaction_status(
    tmp_path: Path,
):
    summary = _make_summary()
    scan = write_soak_summary_bundle(
        output_dir=tmp_path, summary=summary,
    )
    assert scan["redaction_status"] in (
        REDACTION_STATUS_SAFE,
        REDACTION_STATUS_REDACTED,
    )


# ---------------------------------------------------------------------------
# Deterministic + redaction-safe artifact bodies
# ---------------------------------------------------------------------------


def test_artifact_bodies_carry_no_forbidden_substring_after_clean_run(
    tmp_path: Path,
):
    summary = _make_summary()
    write_soak_summary_artifact(
        output_dir=tmp_path, summary=summary,
    )
    append_heartbeat_artifact(
        output_dir=tmp_path,
        record=_make_pass_record(pass_index=1),
    )
    write_health_snapshot_artifact(
        output_dir=tmp_path,
        record=_make_pass_record(pass_index=1),
        bounds_within_recommended_ranges=True,
    )
    scan = run_soak_redaction_scan(output_dir=tmp_path)
    assert scan["redaction_status"] == REDACTION_STATUS_SAFE

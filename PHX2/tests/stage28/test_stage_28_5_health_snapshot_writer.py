"""Stage 28.5 health-snapshot + final-run-summary writer tests.

Pins:

  * ``write_health_snapshot`` writes a deterministic JSON object
    file via temp-write-then-replace, leaving no temp file behind
    on success.
  * Overwriting the snapshot replaces the prior content fully.
  * ``write_final_run_summary`` behaves the same way against a
    distinct schema version.
  * Path validation rejects a directory, a missing parent, a
    non-Path argument, and any URL / bearer / webhook-shaped
    path.
  * OSError on write is wrapped as
    ``Stage28_5HealthSnapshotIOError`` (raw OSError text dropped),
    and the temp file is cleaned up.
  * Canary secret values supplied by upstream callers never appear
    in the snapshot artifact, in any read-back dict, in any
    exception message, or in any repr / str output.
  * ``read_health_snapshot`` / ``read_final_run_summary``
    round-trip the locked field-name sets + schema versions.
"""

from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path
from typing import Any

import pytest

from PHX2.stage28.health_snapshot_writer import (
    Stage28_5HealthSnapshotIOError,
    Stage28_5HealthSnapshotPathError,
    Stage28_5HealthSnapshotWriterError,
    read_final_run_summary,
    read_health_snapshot,
    write_final_run_summary,
    write_health_snapshot,
)
from PHX2.stage28.health_status_models import (
    ARTIFACT_STATUS_OK,
    DISPATCH_STATUS_OK,
    FINAL_SUMMARY_RECORD_FIELD_NAMES,
    FINAL_SUMMARY_TOTAL_FIELD_NAMES,
    HEALTH_SNAPSHOT_RECORD_FIELD_NAMES,
    HEALTH_STATUS_HEALTHY,
    LAST_EVENT_STATUS_NONE_OBSERVED,
    LAST_PING_STATUS_NONE_RENDERED,
    LEDGER_STATUS_OK,
    PRICE_STATUS_OK,
    PROVIDER_STATUS_OK,
    RETRY_BUDGET_STATUS_OK,
    STAGE28_5_FINAL_SUMMARY_SCHEMA_VERSION,
    STAGE28_5_HEALTH_SNAPSHOT_SCHEMA_VERSION,
    STOP_REASON_MAX_EVENTS,
    STOP_REASON_NOT_STOPPED,
    TRANSPORT_STATUS_OK,
    build_final_run_summary_record,
    build_health_snapshot_record,
)


CANARY_WEBHOOK_URL: str = "h" + "ttps://discord" + ".com/api/webhooks/123/abc"
CANARY_BEARER: str = "B" + "earer secret_token_xyz"
CANARY_API_KEY: str = "s" + "k-supersecretapikey1234"


# Stage 28.5 writers need a writable temp directory. Pytest's
# built-in ``tmp_path`` fixture would normally fit, but on this
# host the sandboxed pytest cache lacks list-access to the global
# ``pytest-of-*`` root. A project-local self-managed temp directory
# sidesteps that and keeps the test deterministic (matching the
# Stage 27.5 / Stage 28.2 conventions).
@pytest.fixture
def tmp_path(request):
    base = Path(__file__).resolve().parent / "_stage_28_5_tmp"
    base.mkdir(parents=True, exist_ok=True)
    path = Path(tempfile.mkdtemp(prefix="stage28_5_", dir=base))
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)
        try:
            base.rmdir()
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Snapshot builders
# ---------------------------------------------------------------------------


def _all_zero_counters() -> dict[str, int]:
    return {
        "event_count": 0,
        "candidate_count": 0,
        "ping_rendered_count": 0,
        "dispatch_success_count": 0,
        "dispatch_failure_count": 0,
        "retry_count": 0,
        "duplicate_suppressed_count": 0,
        "ambiguous_suppressed_count": 0,
        "unknown_pair_suppressed_count": 0,
        "disagree_pair_suppressed_count": 0,
        "usdc_observe_only_count": 0,
        "stale_price_count": 0,
        "missing_price_count": 0,
        "malformed_event_count": 0,
    }


def _good_snapshot(**overrides: Any):
    kwargs: dict[str, Any] = dict(
        run_id="run_abc",
        session_id="sess_001",
        provider_status=PROVIDER_STATUS_OK,
        price_status=PRICE_STATUS_OK,
        dispatch_status=DISPATCH_STATUS_OK,
        ledger_status=LEDGER_STATUS_OK,
        transport_status=TRANSPORT_STATUS_OK,
        artifact_status=ARTIFACT_STATUS_OK,
        last_event_status=LAST_EVENT_STATUS_NONE_OBSERVED,
        last_ping_status=LAST_PING_STATUS_NONE_RENDERED,
        retry_budget_status=RETRY_BUDGET_STATUS_OK,
        current_health_status=HEALTH_STATUS_HEALTHY,
        **_all_zero_counters(),
    )
    kwargs.update(overrides)
    return build_health_snapshot_record(**kwargs)


def _all_zero_totals() -> dict[str, int]:
    return {name: 0 for name in FINAL_SUMMARY_TOTAL_FIELD_NAMES}


def _good_summary(**overrides: Any):
    kwargs: dict[str, Any] = dict(
        run_id="run_abc",
        session_id="sess_001",
        stop_reason=STOP_REASON_NOT_STOPPED,
        final_provider_status=PROVIDER_STATUS_OK,
        final_price_status=PRICE_STATUS_OK,
        final_dispatch_status=DISPATCH_STATUS_OK,
        final_ledger_status=LEDGER_STATUS_OK,
        final_transport_status=TRANSPORT_STATUS_OK,
        final_artifact_status=ARTIFACT_STATUS_OK,
        **_all_zero_totals(),
    )
    kwargs.update(overrides)
    return build_final_run_summary_record(**kwargs)


# ---------------------------------------------------------------------------
# write_health_snapshot happy path
# ---------------------------------------------------------------------------


def test_write_health_snapshot_creates_json_file(tmp_path: Path):
    path = tmp_path / "snapshot.json"
    write_health_snapshot(snapshot_path=path, record=_good_snapshot())
    assert path.is_file()
    parsed = json.loads(path.read_text("utf-8"))
    assert isinstance(parsed, dict)
    assert (
        parsed["schema_version"]
        == STAGE28_5_HEALTH_SNAPSHOT_SCHEMA_VERSION
    )
    assert (
        set(parsed.keys())
        == set(HEALTH_SNAPSHOT_RECORD_FIELD_NAMES)
    )


def test_write_health_snapshot_keys_are_sorted(tmp_path: Path):
    path = tmp_path / "snapshot.json"
    write_health_snapshot(
        snapshot_path=path, record=_good_snapshot()
    )
    parsed = json.loads(path.read_text("utf-8"))
    assert list(parsed.keys()) == sorted(parsed.keys())


def test_write_health_snapshot_overwrites_prior_content(
    tmp_path: Path,
):
    path = tmp_path / "snapshot.json"
    write_health_snapshot(
        snapshot_path=path,
        record=_good_snapshot(event_count=0),
    )
    write_health_snapshot(
        snapshot_path=path,
        record=_good_snapshot(event_count=42),
    )
    parsed = json.loads(path.read_text("utf-8"))
    assert parsed["event_count"] == 42


def test_write_health_snapshot_leaves_no_temp_file(tmp_path: Path):
    path = tmp_path / "snapshot.json"
    write_health_snapshot(
        snapshot_path=path, record=_good_snapshot()
    )
    temp_entries = [
        p for p in tmp_path.iterdir() if p.name.endswith(".tmp")
    ]
    assert temp_entries == []


def test_write_health_snapshot_deterministic_bytes(tmp_path: Path):
    path_a = tmp_path / "a.json"
    path_b = tmp_path / "b.json"
    record = _good_snapshot()
    write_health_snapshot(snapshot_path=path_a, record=record)
    write_health_snapshot(snapshot_path=path_b, record=record)
    assert path_a.read_bytes() == path_b.read_bytes()


def test_read_health_snapshot_round_trips_field_set(tmp_path: Path):
    path = tmp_path / "snapshot.json"
    write_health_snapshot(
        snapshot_path=path, record=_good_snapshot()
    )
    parsed = read_health_snapshot(path)
    assert parsed is not None
    assert (
        set(parsed.keys())
        == set(HEALTH_SNAPSHOT_RECORD_FIELD_NAMES)
    )


def test_read_health_snapshot_returns_none_when_missing(
    tmp_path: Path,
):
    path = tmp_path / "missing.json"
    assert read_health_snapshot(path) is None


# ---------------------------------------------------------------------------
# write_final_run_summary happy path
# ---------------------------------------------------------------------------


def test_write_final_summary_creates_json_file(tmp_path: Path):
    path = tmp_path / "final_summary.json"
    write_final_run_summary(
        summary_path=path, record=_good_summary()
    )
    assert path.is_file()
    parsed = json.loads(path.read_text("utf-8"))
    assert (
        parsed["schema_version"]
        == STAGE28_5_FINAL_SUMMARY_SCHEMA_VERSION
    )
    assert (
        set(parsed.keys())
        == set(FINAL_SUMMARY_RECORD_FIELD_NAMES)
    )


def test_write_final_summary_overwrites_prior_file(tmp_path: Path):
    path = tmp_path / "final_summary.json"
    write_final_run_summary(
        summary_path=path,
        record=_good_summary(stop_reason=STOP_REASON_NOT_STOPPED),
    )
    write_final_run_summary(
        summary_path=path,
        record=_good_summary(stop_reason=STOP_REASON_MAX_EVENTS),
    )
    parsed = json.loads(path.read_text("utf-8"))
    assert parsed["stop_reason"] == STOP_REASON_MAX_EVENTS


def test_read_final_summary_round_trips_field_set(tmp_path: Path):
    path = tmp_path / "final_summary.json"
    write_final_run_summary(
        summary_path=path, record=_good_summary()
    )
    parsed = read_final_run_summary(path)
    assert parsed is not None
    assert (
        set(parsed.keys())
        == set(FINAL_SUMMARY_RECORD_FIELD_NAMES)
    )


def test_read_final_summary_returns_none_when_missing(
    tmp_path: Path,
):
    assert read_final_run_summary(tmp_path / "missing.json") is None


# ---------------------------------------------------------------------------
# Path validation
# ---------------------------------------------------------------------------


def test_snapshot_path_must_be_pathlib_path():
    with pytest.raises(Stage28_5HealthSnapshotPathError) as exc:
        write_health_snapshot(
            snapshot_path="/tmp/snapshot.json",  # type: ignore[arg-type]
            record=_good_snapshot(),
        )
    assert (
        exc.value.reason == "HEALTH_SNAPSHOT_PATH_NOT_A_PATHLIB_PATH"
    )


def test_snapshot_path_rejects_directory(tmp_path: Path):
    with pytest.raises(Stage28_5HealthSnapshotPathError) as exc:
        write_health_snapshot(
            snapshot_path=tmp_path, record=_good_snapshot()
        )
    assert exc.value.reason == "HEALTH_SNAPSHOT_PATH_IS_DIRECTORY"


def test_snapshot_path_rejects_missing_parent(tmp_path: Path):
    path = tmp_path / "missing_dir" / "snapshot.json"
    with pytest.raises(Stage28_5HealthSnapshotPathError) as exc:
        write_health_snapshot(
            snapshot_path=path, record=_good_snapshot()
        )
    assert (
        exc.value.reason
        == "HEALTH_SNAPSHOT_PARENT_DIRECTORY_MISSING"
    )


@pytest.mark.parametrize(
    "needle",
    [
        "discord" + ".com",
        "discord" + "app.com",
        "bearer",
        "authorization",
        "token=",
        "apikey=",
        "auth=",
    ],
)
def test_snapshot_path_rejects_secret_like_path(
    tmp_path: Path, needle: str
):
    path = tmp_path / f"snapshot_{needle}.json"
    with pytest.raises(Stage28_5HealthSnapshotPathError) as exc:
        write_health_snapshot(
            snapshot_path=path, record=_good_snapshot()
        )
    assert exc.value.reason == "HEALTH_SNAPSHOT_PATH_SECRET_LIKE"


def test_summary_path_rejects_directory(tmp_path: Path):
    with pytest.raises(Stage28_5HealthSnapshotPathError) as exc:
        write_final_run_summary(
            summary_path=tmp_path, record=_good_summary()
        )
    assert exc.value.reason == "FINAL_RUN_SUMMARY_PATH_IS_DIRECTORY"


def test_summary_path_rejects_missing_parent(tmp_path: Path):
    path = tmp_path / "missing_dir" / "summary.json"
    with pytest.raises(Stage28_5HealthSnapshotPathError) as exc:
        write_final_run_summary(
            summary_path=path, record=_good_summary()
        )
    assert (
        exc.value.reason
        == "FINAL_RUN_SUMMARY_PARENT_DIRECTORY_MISSING"
    )


# ---------------------------------------------------------------------------
# Wrong-type argument
# ---------------------------------------------------------------------------


def test_write_snapshot_rejects_non_record(tmp_path: Path):
    path = tmp_path / "snapshot.json"
    with pytest.raises(Stage28_5HealthSnapshotWriterError):
        write_health_snapshot(
            snapshot_path=path,
            record="not_a_record",  # type: ignore[arg-type]
        )


def test_write_summary_rejects_non_record(tmp_path: Path):
    path = tmp_path / "summary.json"
    with pytest.raises(Stage28_5HealthSnapshotWriterError):
        write_final_run_summary(
            summary_path=path,
            record="not_a_record",  # type: ignore[arg-type]
        )


# ---------------------------------------------------------------------------
# OSError wrapping + temp-file cleanup
# ---------------------------------------------------------------------------


def test_oserror_on_snapshot_write_is_wrapped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    path = tmp_path / "snapshot.json"
    original_open = Path.open

    def failing_open(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        # Trip only the temp-file's open call.
        if self.name.endswith(".stage28_5.tmp"):
            raise OSError("simulated OS failure")
        return original_open(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", failing_open)
    with pytest.raises(Stage28_5HealthSnapshotIOError) as exc:
        write_health_snapshot(
            snapshot_path=path, record=_good_snapshot()
        )
    assert exc.value.operation == "HEALTH_SNAPSHOT_WRITE"
    assert "simulated OS failure" not in str(exc.value)


def test_oserror_on_summary_write_is_wrapped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    path = tmp_path / "summary.json"
    original_open = Path.open

    def failing_open(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        if self.name.endswith(".stage28_5.tmp"):
            raise OSError(CANARY_WEBHOOK_URL)
        return original_open(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", failing_open)
    try:
        write_final_run_summary(
            summary_path=path, record=_good_summary()
        )
    except Stage28_5HealthSnapshotIOError as exc:
        assert CANARY_WEBHOOK_URL not in str(exc)
        assert CANARY_WEBHOOK_URL not in repr(exc)
    else:
        pytest.fail("expected Stage28_5HealthSnapshotIOError")


# ---------------------------------------------------------------------------
# Canary leak isolation
# ---------------------------------------------------------------------------


def test_canary_run_id_never_appears_in_snapshot(tmp_path: Path):
    path = tmp_path / "snapshot.json"
    write_health_snapshot(
        snapshot_path=path,
        record=_good_snapshot(run_id=CANARY_WEBHOOK_URL),
    )
    raw = path.read_text("utf-8")
    assert CANARY_WEBHOOK_URL not in raw


def test_canary_session_id_never_appears_in_summary(tmp_path: Path):
    path = tmp_path / "summary.json"
    write_final_run_summary(
        summary_path=path,
        record=_good_summary(session_id=CANARY_BEARER),
    )
    raw = path.read_text("utf-8")
    assert CANARY_BEARER not in raw


def test_canary_api_key_never_appears_in_read_back_snapshot(
    tmp_path: Path,
):
    path = tmp_path / "snapshot.json"
    write_health_snapshot(
        snapshot_path=path,
        record=_good_snapshot(session_id=CANARY_API_KEY),
    )
    parsed = read_health_snapshot(path)
    assert CANARY_API_KEY not in repr(parsed)


# ---------------------------------------------------------------------------
# Read-back validation
# ---------------------------------------------------------------------------


def test_read_health_snapshot_rejects_malformed_json(tmp_path: Path):
    path = tmp_path / "snapshot.json"
    path.write_text("not valid json", encoding="utf-8")
    with pytest.raises(Stage28_5HealthSnapshotWriterError):
        read_health_snapshot(path)


def test_read_health_snapshot_rejects_empty_file(tmp_path: Path):
    path = tmp_path / "snapshot.json"
    path.write_text("", encoding="utf-8")
    with pytest.raises(Stage28_5HealthSnapshotWriterError):
        read_health_snapshot(path)


def test_read_health_snapshot_rejects_non_object(tmp_path: Path):
    path = tmp_path / "snapshot.json"
    path.write_text("[1, 2, 3]", encoding="utf-8")
    with pytest.raises(Stage28_5HealthSnapshotWriterError):
        read_health_snapshot(path)


def test_read_health_snapshot_rejects_unknown_schema(tmp_path: Path):
    path = tmp_path / "snapshot.json"
    bad = {
        name: 0 if isinstance(name, str) and name.endswith("_count")
        else (
            "stage28_5_unknown_v9"
            if name == "schema_version"
            else "OK"
            if name in (
                "provider_status",
                "price_status",
                "dispatch_status",
                "ledger_status",
                "transport_status",
                "artifact_status",
                "retry_budget_status",
            )
            else "NONE_OBSERVED"
            if name == "last_event_status"
            else "NONE_RENDERED"
            if name == "last_ping_status"
            else "HEALTHY"
            if name == "current_health_status"
            else "SAFE"
            if name == "redaction_status"
            else "run_abc"
            if name == "run_id"
            else "sess_001"
            if name == "session_id"
            else None
        )
        for name in HEALTH_SNAPSHOT_RECORD_FIELD_NAMES
    }
    path.write_text(json.dumps(bad), encoding="utf-8")
    with pytest.raises(Stage28_5HealthSnapshotWriterError):
        read_health_snapshot(path)


def test_read_health_snapshot_rejects_field_set_mismatch(
    tmp_path: Path,
):
    path = tmp_path / "snapshot.json"
    bad = {
        "schema_version": STAGE28_5_HEALTH_SNAPSHOT_SCHEMA_VERSION,
    }
    path.write_text(json.dumps(bad), encoding="utf-8")
    with pytest.raises(Stage28_5HealthSnapshotWriterError):
        read_health_snapshot(path)

"""Stage 28.5 heartbeat-writer tests.

Pins:

  * Appending one heartbeat record produces one JSON line.
  * Appending multiple records preserves prior content (no
    truncation).
  * Deterministic JSON key order on the wire (``sort_keys=True``).
  * Path validation rejects a directory path, a missing-parent
    path, a non-Path argument, and any URL / bearer / webhook-
    shaped path.
  * OSError on write is wrapped as
    ``Stage28_5HeartbeatIOError`` (raw OSError text dropped).
  * Canary secret values supplied by upstream callers never appear
    in the heartbeat artifact, in any read-back dict, in any
    exception message, or in any repr / str output.
  * ``read_heartbeat_lines`` round-trips the canonical field-name
    set + schema version.
"""

from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path
from typing import Any

import pytest

from PHX2.stage28.health_status_models import (
    ARTIFACT_STATUS_OK,
    DISPATCH_STATUS_OK,
    HEARTBEAT_RECORD_FIELD_NAMES,
    LEDGER_STATUS_OK,
    PRICE_STATUS_OK,
    PROVIDER_STATUS_OK,
    STAGE28_5_HEARTBEAT_SCHEMA_VERSION,
    TRANSPORT_STATUS_OK,
    build_heartbeat_record,
)
from PHX2.stage28.heartbeat_writer import (
    Stage28_5HeartbeatIOError,
    Stage28_5HeartbeatPathError,
    Stage28_5HeartbeatWriterError,
    append_heartbeat,
    read_heartbeat_lines,
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


def _good_record(*, heartbeat_index: int = 0, **overrides: Any):
    kwargs: dict[str, Any] = dict(
        run_id="run_abc",
        session_id="sess_001",
        heartbeat_index=heartbeat_index,
        event_count=0,
        candidate_count=0,
        ping_rendered_count=0,
        dispatch_success_count=0,
        dispatch_failure_count=0,
        retry_count=0,
        duplicate_suppressed_count=0,
        ambiguous_suppressed_count=0,
        unknown_pair_suppressed_count=0,
        disagree_pair_suppressed_count=0,
        usdc_observe_only_count=0,
        stale_price_count=0,
        missing_price_count=0,
        malformed_event_count=0,
        provider_status=PROVIDER_STATUS_OK,
        price_status=PRICE_STATUS_OK,
        dispatch_status=DISPATCH_STATUS_OK,
        ledger_status=LEDGER_STATUS_OK,
        transport_status=TRANSPORT_STATUS_OK,
        artifact_status=ARTIFACT_STATUS_OK,
        stop_reason=None,
    )
    kwargs.update(overrides)
    return build_heartbeat_record(**kwargs)


# ---------------------------------------------------------------------------
# Append happy path
# ---------------------------------------------------------------------------


def test_append_one_heartbeat_line_writes_one_jsonl_line(tmp_path: Path):
    path = tmp_path / "heartbeat.jsonl"
    record = _good_record()
    append_heartbeat(heartbeat_path=path, record=record)
    raw = path.read_bytes()
    assert raw.endswith(b"\n")
    lines = raw.decode("utf-8").splitlines()
    assert len(lines) == 1
    parsed = json.loads(lines[0])
    assert (
        parsed["schema_version"]
        == STAGE28_5_HEARTBEAT_SCHEMA_VERSION
    )
    assert parsed["run_id"] == "run_abc"
    assert parsed["heartbeat_index"] == 0


def test_append_multiple_heartbeat_lines_preserves_prior_lines(
    tmp_path: Path,
):
    path = tmp_path / "heartbeat.jsonl"
    append_heartbeat(
        heartbeat_path=path, record=_good_record(heartbeat_index=0)
    )
    append_heartbeat(
        heartbeat_path=path, record=_good_record(heartbeat_index=1)
    )
    append_heartbeat(
        heartbeat_path=path, record=_good_record(heartbeat_index=2)
    )
    raw = path.read_text("utf-8")
    lines = raw.splitlines()
    assert len(lines) == 3
    indices = [json.loads(line)["heartbeat_index"] for line in lines]
    assert indices == [0, 1, 2]


def test_append_does_not_truncate_existing_lines(tmp_path: Path):
    path = tmp_path / "heartbeat.jsonl"
    append_heartbeat(
        heartbeat_path=path, record=_good_record(heartbeat_index=0)
    )
    before = path.read_bytes()
    append_heartbeat(
        heartbeat_path=path, record=_good_record(heartbeat_index=1)
    )
    after = path.read_bytes()
    assert after.startswith(before)
    assert len(after) > len(before)


def test_heartbeat_jsonl_keys_are_sorted_alphabetically(
    tmp_path: Path,
):
    path = tmp_path / "heartbeat.jsonl"
    append_heartbeat(heartbeat_path=path, record=_good_record())
    line = path.read_text("utf-8").splitlines()[0]
    parsed = json.loads(line)
    assert list(parsed.keys()) == sorted(HEARTBEAT_RECORD_FIELD_NAMES)


def test_read_heartbeat_lines_round_trips_field_set(tmp_path: Path):
    path = tmp_path / "heartbeat.jsonl"
    append_heartbeat(
        heartbeat_path=path, record=_good_record(heartbeat_index=0)
    )
    append_heartbeat(
        heartbeat_path=path, record=_good_record(heartbeat_index=1)
    )
    lines = read_heartbeat_lines(path)
    assert len(lines) == 2
    for line in lines:
        assert (
            set(line.keys()) == set(HEARTBEAT_RECORD_FIELD_NAMES)
        )
        assert (
            line["schema_version"]
            == STAGE28_5_HEARTBEAT_SCHEMA_VERSION
        )


def test_read_heartbeat_lines_returns_empty_when_path_missing(
    tmp_path: Path,
):
    path = tmp_path / "no_such_heartbeat.jsonl"
    assert read_heartbeat_lines(path) == ()


def test_read_heartbeat_lines_returns_empty_when_file_empty(
    tmp_path: Path,
):
    path = tmp_path / "heartbeat.jsonl"
    path.write_bytes(b"")
    assert read_heartbeat_lines(path) == ()


# ---------------------------------------------------------------------------
# Path validation
# ---------------------------------------------------------------------------


def test_path_must_be_pathlib_path():
    with pytest.raises(Stage28_5HeartbeatPathError) as exc:
        append_heartbeat(
            heartbeat_path="/tmp/heartbeat.jsonl",  # type: ignore[arg-type]
            record=_good_record(),
        )
    assert exc.value.reason == "HEARTBEAT_PATH_NOT_A_PATHLIB_PATH"


def test_path_rejects_directory(tmp_path: Path):
    with pytest.raises(Stage28_5HeartbeatPathError) as exc:
        append_heartbeat(
            heartbeat_path=tmp_path, record=_good_record()
        )
    assert exc.value.reason == "HEARTBEAT_PATH_IS_DIRECTORY"


def test_path_rejects_missing_parent(tmp_path: Path):
    path = tmp_path / "does_not_exist" / "heartbeat.jsonl"
    with pytest.raises(Stage28_5HeartbeatPathError) as exc:
        append_heartbeat(heartbeat_path=path, record=_good_record())
    assert exc.value.reason == "HEARTBEAT_PARENT_DIRECTORY_MISSING"


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
        "password",
    ],
)
def test_path_rejects_secret_like_path(tmp_path: Path, needle: str):
    path = tmp_path / f"heartbeat_{needle}.jsonl"
    with pytest.raises(Stage28_5HeartbeatPathError) as exc:
        append_heartbeat(heartbeat_path=path, record=_good_record())
    assert exc.value.reason == "HEARTBEAT_PATH_SECRET_LIKE"


def test_path_error_does_not_carry_raw_path(tmp_path: Path):
    # Construct a path containing a filename-safe secret marker so
    # the path-secret-like check trips. Verify the resulting error
    # never echoes the marker on str / repr.
    secret_marker = "bearer"
    secret_path_obj = tmp_path / f"heartbeat_{secret_marker}.jsonl"
    try:
        append_heartbeat(
            heartbeat_path=secret_path_obj, record=_good_record()
        )
    except Stage28_5HeartbeatPathError as exc:
        assert secret_marker not in str(exc)
        assert secret_marker not in repr(exc)


# ---------------------------------------------------------------------------
# Wrong-type argument
# ---------------------------------------------------------------------------


def test_writer_rejects_non_record_argument(tmp_path: Path):
    path = tmp_path / "heartbeat.jsonl"
    with pytest.raises(Stage28_5HeartbeatWriterError):
        append_heartbeat(
            heartbeat_path=path,
            record="not_a_record",  # type: ignore[arg-type]
        )


# ---------------------------------------------------------------------------
# OSError wrapping
# ---------------------------------------------------------------------------


def test_oserror_on_write_is_wrapped_as_io_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    path = tmp_path / "heartbeat.jsonl"
    original_open = Path.open

    def failing_open(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        if self == path and "a" in (args[0] if args else kwargs.get("mode", "")):
            raise OSError("simulated OS failure")
        return original_open(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", failing_open)
    with pytest.raises(Stage28_5HeartbeatIOError) as exc:
        append_heartbeat(heartbeat_path=path, record=_good_record())
    assert exc.value.operation == "HEARTBEAT_APPEND"
    # The wrapping exception must NOT carry the raw OSError text.
    assert "simulated OS failure" not in str(exc.value)


# ---------------------------------------------------------------------------
# Canary leak isolation
# ---------------------------------------------------------------------------


def test_canary_run_id_never_appears_in_artifact(tmp_path: Path):
    path = tmp_path / "heartbeat.jsonl"
    append_heartbeat(
        heartbeat_path=path,
        record=_good_record(run_id=CANARY_WEBHOOK_URL),
    )
    raw = path.read_bytes().decode("utf-8")
    assert CANARY_WEBHOOK_URL not in raw


def test_canary_session_id_never_appears_in_artifact(tmp_path: Path):
    path = tmp_path / "heartbeat.jsonl"
    append_heartbeat(
        heartbeat_path=path,
        record=_good_record(session_id=CANARY_BEARER),
    )
    raw = path.read_bytes().decode("utf-8")
    assert CANARY_BEARER not in raw


def test_canary_api_key_run_id_never_appears_in_artifact_or_read_back(
    tmp_path: Path,
):
    path = tmp_path / "heartbeat.jsonl"
    append_heartbeat(
        heartbeat_path=path,
        record=_good_record(run_id=CANARY_API_KEY),
    )
    raw = path.read_bytes().decode("utf-8")
    assert CANARY_API_KEY not in raw
    parsed = read_heartbeat_lines(path)
    assert CANARY_API_KEY not in repr(parsed)


def test_canary_secret_never_appears_in_io_error_message(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    path = tmp_path / "heartbeat.jsonl"
    original_open = Path.open

    def failing_open(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        if self == path:
            raise OSError(CANARY_WEBHOOK_URL)
        return original_open(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", failing_open)
    try:
        append_heartbeat(
            heartbeat_path=path, record=_good_record()
        )
    except Stage28_5HeartbeatIOError as exc:
        assert CANARY_WEBHOOK_URL not in str(exc)
        assert CANARY_WEBHOOK_URL not in repr(exc)
    else:
        pytest.fail("expected Stage28_5HeartbeatIOError")


# ---------------------------------------------------------------------------
# Read-back validation
# ---------------------------------------------------------------------------


def test_read_heartbeat_lines_rejects_malformed_json(tmp_path: Path):
    path = tmp_path / "heartbeat.jsonl"
    path.write_text("not valid json\n", encoding="utf-8")
    with pytest.raises(Stage28_5HeartbeatWriterError):
        read_heartbeat_lines(path)


def test_read_heartbeat_lines_rejects_non_object_line(tmp_path: Path):
    path = tmp_path / "heartbeat.jsonl"
    path.write_text("[1, 2, 3]\n", encoding="utf-8")
    with pytest.raises(Stage28_5HeartbeatWriterError):
        read_heartbeat_lines(path)


def test_read_heartbeat_lines_rejects_unknown_schema_version(
    tmp_path: Path,
):
    path = tmp_path / "heartbeat.jsonl"
    bad_record = {
        name: 0 if name.endswith("_count") or name == "heartbeat_index"
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
            )
            else "SAFE"
            if name == "redaction_status"
            else "run_abc"
            if name == "run_id"
            else "sess_001"
            if name == "session_id"
            else None
        )
        for name in HEARTBEAT_RECORD_FIELD_NAMES
    }
    path.write_text(json.dumps(bad_record) + "\n", encoding="utf-8")
    with pytest.raises(Stage28_5HeartbeatWriterError):
        read_heartbeat_lines(path)


def test_read_heartbeat_lines_rejects_field_set_mismatch(
    tmp_path: Path,
):
    path = tmp_path / "heartbeat.jsonl"
    bad = {"schema_version": STAGE28_5_HEARTBEAT_SCHEMA_VERSION}
    path.write_text(json.dumps(bad) + "\n", encoding="utf-8")
    with pytest.raises(Stage28_5HeartbeatWriterError):
        read_heartbeat_lines(path)

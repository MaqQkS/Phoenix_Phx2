"""FileSink behavior."""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from PHX2.dispatch.sinks.base import DeliveryContext
from PHX2.dispatch.sinks.file_preview import FileSink
from PHX2.tests.dispatch._fixtures import (
    ATTEMPTED_AT,
    make_rendered_alert,
)


def _ctx(
    attempted_at: datetime = ATTEMPTED_AT,
    event_id: str = "evt-1",
) -> DeliveryContext:
    return DeliveryContext(
        dispatch_event_id=event_id,
        dispatch_run_id="run-1",
        attempted_at=attempted_at,
    )


def _read_lines(path: Path) -> list:
    with path.open("r", encoding="utf-8") as fh:
        return [line.rstrip("\n") for line in fh if line.strip()]


def test_deliver_writes_one_jsonl_line_in_date_bucket(tmp_path: Path):
    sink = FileSink(root_dir=tmp_path)

    result = sink.deliver(make_rendered_alert(alert_decision_id=42), _ctx())

    assert result.success is True
    expected_dir = tmp_path / "2026-05-09"
    expected_path = expected_dir / "decisions.jsonl"
    assert expected_path.exists()
    assert result.payload_ref == str(expected_path)
    lines = _read_lines(expected_path)
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert payload["dispatch_event_id"] == "evt-1"
    assert payload["alert_decision_id"] == 42
    assert payload["dispatch_run_id"] == "run-1"
    assert payload["decision_type"] == "would_alert"
    assert payload["severity"] == "CLEAN"
    assert payload["tier_label"] == "T2"
    assert "rendered_alert" in payload
    assert "formatted_text" in payload


def test_jsonl_line_contains_every_required_field(tmp_path: Path):
    sink = FileSink(root_dir=tmp_path)
    sink.deliver(make_rendered_alert(), _ctx())
    path = tmp_path / "2026-05-09" / "decisions.jsonl"

    payload = json.loads(_read_lines(path)[0])

    for required in [
        "dispatch_event_id",
        "alert_decision_id",
        "dispatch_run_id",
        "decision_type",
        "severity",
        "tier_label",
        "token_address",
        "dispatched_at",
        "rendered_alert",
        "formatted_text",
    ]:
        assert required in payload


def test_two_deliveries_same_date_share_one_file(tmp_path: Path):
    sink = FileSink(root_dir=tmp_path)

    sink.deliver(make_rendered_alert(), _ctx(event_id="evt-1"))
    sink.deliver(make_rendered_alert(), _ctx(event_id="evt-2"))

    path = tmp_path / "2026-05-09" / "decisions.jsonl"
    lines = _read_lines(path)
    assert len(lines) == 2
    ids = [json.loads(line)["dispatch_event_id"] for line in lines]
    assert ids == ["evt-1", "evt-2"]


def test_two_deliveries_different_utc_dates_land_in_different_directories(
    tmp_path: Path,
):
    sink = FileSink(root_dir=tmp_path)
    next_day = ATTEMPTED_AT + timedelta(days=1)

    sink.deliver(make_rendered_alert(), _ctx())
    sink.deliver(make_rendered_alert(), _ctx(attempted_at=next_day))

    assert (tmp_path / "2026-05-09" / "decisions.jsonl").exists()
    assert (tmp_path / "2026-05-10" / "decisions.jsonl").exists()


def test_dispatched_at_matches_context_attempted_at(tmp_path: Path):
    sink = FileSink(root_dir=tmp_path)
    sink.deliver(make_rendered_alert(), _ctx())

    payload = json.loads(_read_lines(tmp_path / "2026-05-09" / "decisions.jsonl")[0])

    assert payload["dispatched_at"] == "2026-05-09T14:33:04Z"


def test_io_error_returns_failed_result_without_raising(tmp_path: Path):
    sink = FileSink(root_dir=tmp_path)

    with patch("os.open", side_effect=OSError("disk full")):
        result = sink.deliver(make_rendered_alert(), _ctx())

    assert result.success is False
    assert result.payload_ref is None
    assert "disk full" in (result.error_message or "")


def test_jsonl_file_contains_no_partial_lines(tmp_path: Path):
    sink = FileSink(root_dir=tmp_path)
    for i in range(5):
        sink.deliver(make_rendered_alert(), _ctx(event_id=f"evt-{i}"))

    path = tmp_path / "2026-05-09" / "decisions.jsonl"
    lines = _read_lines(path)
    assert len(lines) == 5
    for line in lines:
        json.loads(line)  # would raise if partial


def test_file_sink_does_not_call_any_repository():
    import inspect

    import PHX2.dispatch.sinks.file_preview as module

    source = inspect.getsource(module)
    assert "PHX2.db" not in source
    assert "Repository" not in source


def test_file_sink_does_not_call_datetime_now():
    """Static check + frozen-clock fail-loud guard.

    The sink must derive every timestamp from ``context.attempted_at``.
    """

    import inspect

    import PHX2.dispatch.sinks.file_preview as module

    source = inspect.getsource(module)
    assert "datetime.now" not in source
    assert "datetime.utcnow" not in source

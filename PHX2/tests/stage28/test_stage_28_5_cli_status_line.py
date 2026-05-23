"""Stage 28.5 CLI status-line tests.

Pins:

  * Formatter is pure: returns a string, does not print, does not
    open any file, does not read the environment.
  * Formatted line is a single line: no embedded newline / carriage
    return.
  * Formatted line starts with the locked Stage 28.5 prefix.
  * Formatted line carries the safe run / session identifiers, the
    aggregate health status, the closed-set status fields, the
    operator-visible counters, the closed-set stop reason, and the
    closed-set redaction status.
  * Formatter is deterministic: same model maps to same string.
  * Formatter never echoes a canary secret value (the model
    builder redacted the unsafe value before the formatter is
    called).
  * Formatter rejects non-model arguments and unknown schema
    versions.
"""

from __future__ import annotations

import io
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

import pytest


# Stage 28.5 CLI tests rarely touch the filesystem, but the
# ``test_format_does_no_filesystem_io`` test monkeypatches
# ``Path.open`` to confirm the formatter never opens files. We
# also use a project-local tmp_path fixture for consistency with
# the other Stage 28.5 test files.
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

from PHX2.stage28.cli_status_line import (
    CLI_STATUS_LINE_PREFIX,
    Stage28_5CliStatusLineError,
    format_cli_status_line,
)
from PHX2.stage28.health_status_models import (
    ARTIFACT_STATUS_OK,
    DISPATCH_STATUS_OK,
    HEALTH_STATUS_HEALTHY,
    LEDGER_STATUS_OK,
    PRICE_STATUS_OK,
    PROVIDER_STATUS_OK,
    REDACTION_STATUS_REDACTED,
    REDACTION_STATUS_SAFE,
    SAFE_RUN_ID_REDACTED,
    STAGE28_5_CLI_STATUS_SCHEMA_VERSION,
    STOP_REASON_MAX_EVENTS,
    STOP_REASON_NOT_STOPPED,
    TRANSPORT_STATUS_OK,
    build_cli_status_line_model,
)


CANARY_WEBHOOK_URL: str = "h" + "ttps://discord" + ".com/api/webhooks/123/abc"
CANARY_BEARER: str = "B" + "earer secret_token_xyz"
CANARY_API_KEY: str = "s" + "k-supersecretapikey1234"


def _good_kwargs(**overrides: Any) -> dict[str, Any]:
    kwargs: dict[str, Any] = dict(
        run_id="run_abc",
        session_id="sess_001",
        health_status=HEALTH_STATUS_HEALTHY,
        provider_status=PROVIDER_STATUS_OK,
        price_status=PRICE_STATUS_OK,
        dispatch_status=DISPATCH_STATUS_OK,
        ledger_status=LEDGER_STATUS_OK,
        transport_status=TRANSPORT_STATUS_OK,
        artifact_status=ARTIFACT_STATUS_OK,
        event_count=12,
        ping_rendered_count=3,
        dispatch_success_count=2,
        dispatch_failure_count=1,
        retry_count=4,
        duplicate_suppressed_count=5,
        ambiguous_suppressed_count=6,
        unknown_pair_suppressed_count=7,
        disagree_pair_suppressed_count=8,
        usdc_observe_only_count=9,
        stale_price_count=10,
        missing_price_count=11,
        malformed_event_count=13,
        stop_reason=STOP_REASON_NOT_STOPPED,
    )
    kwargs.update(overrides)
    return kwargs


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_format_returns_str():
    model = build_cli_status_line_model(**_good_kwargs())
    line = format_cli_status_line(model)
    assert isinstance(line, str)


def test_format_starts_with_locked_prefix():
    model = build_cli_status_line_model(**_good_kwargs())
    line = format_cli_status_line(model)
    assert line.startswith(CLI_STATUS_LINE_PREFIX)


def test_format_carries_run_and_session_ids():
    model = build_cli_status_line_model(**_good_kwargs())
    line = format_cli_status_line(model)
    assert "run=run_abc" in line
    assert "sess=sess_001" in line


def test_format_carries_all_closed_set_statuses():
    model = build_cli_status_line_model(**_good_kwargs())
    line = format_cli_status_line(model)
    assert "health=HEALTHY" in line
    assert "provider=OK" in line
    assert "price=OK" in line
    assert "dispatch=OK" in line
    assert "ledger=OK" in line
    assert "transport=OK" in line
    assert "artifact=OK" in line
    assert "stop=NOT_STOPPED" in line
    assert "redaction=SAFE" in line


def test_format_carries_all_counters_with_safe_labels():
    model = build_cli_status_line_model(**_good_kwargs())
    line = format_cli_status_line(model)
    assert "events=12" in line
    assert "pings=3" in line
    assert "dispatch_ok=2" in line
    assert "dispatch_fail=1" in line
    assert "retries=4" in line
    assert "dup_sup=5" in line
    assert "amb_sup=6" in line
    assert "unk_pair_sup=7" in line
    assert "dis_pair_sup=8" in line
    assert "usdc_obs=9" in line
    assert "stale=10" in line
    assert "missing=11" in line
    assert "malformed=13" in line


def test_format_is_single_line_no_newline_or_cr():
    model = build_cli_status_line_model(**_good_kwargs())
    line = format_cli_status_line(model)
    assert "\n" not in line
    assert "\r" not in line


def test_format_is_deterministic():
    kwargs = _good_kwargs()
    model_a = build_cli_status_line_model(**kwargs)
    model_b = build_cli_status_line_model(**kwargs)
    assert (
        format_cli_status_line(model_a)
        == format_cli_status_line(model_b)
    )


def test_format_does_not_print(
    capsys: pytest.CaptureFixture[str],
):
    model = build_cli_status_line_model(**_good_kwargs())
    format_cli_status_line(model)
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""


def test_format_alternate_stop_reason():
    model = build_cli_status_line_model(
        **_good_kwargs(stop_reason=STOP_REASON_MAX_EVENTS)
    )
    line = format_cli_status_line(model)
    assert "stop=MAX_EVENTS" in line


# ---------------------------------------------------------------------------
# Canary leak isolation
# ---------------------------------------------------------------------------


def test_format_does_not_leak_canary_run_id():
    model = build_cli_status_line_model(
        **_good_kwargs(run_id=CANARY_WEBHOOK_URL)
    )
    line = format_cli_status_line(model)
    assert CANARY_WEBHOOK_URL not in line
    assert SAFE_RUN_ID_REDACTED in line
    assert f"redaction={REDACTION_STATUS_REDACTED}" in line


def test_format_does_not_leak_canary_session_id():
    model = build_cli_status_line_model(
        **_good_kwargs(session_id=CANARY_BEARER)
    )
    line = format_cli_status_line(model)
    assert CANARY_BEARER not in line


def test_format_does_not_leak_canary_api_key():
    model = build_cli_status_line_model(
        **_good_kwargs(run_id=CANARY_API_KEY)
    )
    line = format_cli_status_line(model)
    assert CANARY_API_KEY not in line


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


def test_format_rejects_non_model_argument():
    with pytest.raises(Stage28_5CliStatusLineError) as exc:
        format_cli_status_line("not_a_model")  # type: ignore[arg-type]
    assert exc.value.reason == "NOT_A_CLI_STATUS_LINE_MODEL"


def test_format_rejects_unknown_schema_version():
    model = build_cli_status_line_model(**_good_kwargs())
    bad = model._replace(schema_version="stage28_5_unknown_v9")
    with pytest.raises(Stage28_5CliStatusLineError) as exc:
        format_cli_status_line(bad)
    assert exc.value.reason == "UNKNOWN_CLI_STATUS_SCHEMA_VERSION"


def test_format_does_no_filesystem_io(
    tmp_path, monkeypatch: pytest.MonkeyPatch
):
    """Sanity: the formatter never opens a file."""
    from pathlib import Path

    original_open = Path.open
    calls: list[Path] = []

    def tracking_open(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        calls.append(self)
        return original_open(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", tracking_open)
    model = build_cli_status_line_model(**_good_kwargs())
    format_cli_status_line(model)
    assert calls == []


def test_format_does_not_write_stdout_directly(
    monkeypatch: pytest.MonkeyPatch,
):
    """Sanity: the formatter must not write to ``sys.stdout``."""
    sink = io.StringIO()
    monkeypatch.setattr(sys, "stdout", sink)
    model = build_cli_status_line_model(**_good_kwargs())
    format_cli_status_line(model)
    assert sink.getvalue() == ""


# ---------------------------------------------------------------------------
# Field-order is locked: schema version must be the locked literal
# ---------------------------------------------------------------------------


def test_model_schema_version_is_the_locked_literal():
    model = build_cli_status_line_model(**_good_kwargs())
    assert (
        model.schema_version
        == STAGE28_5_CLI_STATUS_SCHEMA_VERSION
        == "stage28_5_cli_status_v0"
    )


def test_format_redaction_field_carries_safe_when_inputs_safe():
    model = build_cli_status_line_model(**_good_kwargs())
    line = format_cli_status_line(model)
    assert f"redaction={REDACTION_STATUS_SAFE}" in line

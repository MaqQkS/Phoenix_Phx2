"""ConsoleSink behavior."""

import io

import pytest

from PHX2.dispatch.sinks.base import DeliveryContext
from PHX2.dispatch.sinks.console import ConsoleSink
from PHX2.renderers.rendered_alert import DRY_RUN_BANNER, Severity
from PHX2.tests.dispatch._fixtures import (
    ATTEMPTED_AT,
    make_rendered_alert,
    make_rendered_block,
    make_rendered_error,
    make_rendered_skip,
)


def _context(event_id: str = "evt-abc") -> DeliveryContext:
    return DeliveryContext(
        dispatch_event_id=event_id,
        dispatch_run_id="run-1",
        attempted_at=ATTEMPTED_AT,
    )


def test_deliver_returns_success_and_writes_formatted_text():
    stream = io.StringIO()
    sink = ConsoleSink(stream=stream)

    result = sink.deliver(make_rendered_alert(), _context())

    assert result.success is True
    assert result.payload_ref is None
    assert result.error_message is None
    assert "WOULD_ALERT" in stream.getvalue()


def test_output_contains_dry_run_banner_twice():
    stream = io.StringIO()
    sink = ConsoleSink(stream=stream)

    sink.deliver(make_rendered_alert(), _context())

    assert stream.getvalue().count(DRY_RUN_BANNER) == 2


def test_header_contains_dispatch_event_id_and_decision_type_and_severity():
    stream = io.StringIO()
    sink = ConsoleSink(stream=stream)

    sink.deliver(make_rendered_alert(severity=Severity.PARTIAL), _context("evt-xyz"))

    output = stream.getvalue()
    first_line = output.splitlines()[0]
    assert first_line.startswith("=== DISPATCH evt-xyz")
    assert "would_alert" in first_line
    assert "PARTIAL" in first_line
    # token symbol or address_short
    assert "7xKp...mLq" in first_line


def test_header_timestamp_matches_context_attempted_at():
    stream = io.StringIO()
    sink = ConsoleSink(stream=stream)

    sink.deliver(make_rendered_alert(), _context())

    first_line = stream.getvalue().splitlines()[0]
    # ATTEMPTED_AT is 2026-05-09T14:33:04+00:00 -> ISO 8601 with Z
    assert "2026-05-09T14:33:04Z" in first_line


@pytest.mark.parametrize(
    "rendered_factory",
    [
        make_rendered_alert,
        make_rendered_skip,
        make_rendered_block,
        make_rendered_error,
    ],
)
def test_deliver_does_not_raise_for_any_decision_type(rendered_factory):
    stream = io.StringIO()
    sink = ConsoleSink(stream=stream)

    result = sink.deliver(rendered_factory(), _context())

    assert result.success is True


def test_console_sink_does_not_call_any_repository():
    """Static check: sink imports nothing from PHX2.db."""

    import inspect

    import PHX2.dispatch.sinks.console as module

    source = inspect.getsource(module)
    assert "PHX2.db" not in source
    assert "Repository" not in source

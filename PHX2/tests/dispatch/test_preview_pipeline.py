"""PreviewPipeline orchestration."""

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from PHX2.dispatch.preview_pipeline import PreviewPipeline
from PHX2.tests.dispatch._fixtures import make_rendered_alert


def test_handle_runs_assemble_then_render_then_dispatch_in_order():
    assembler = MagicMock()
    renderer = MagicMock()
    dispatcher = MagicMock()
    rendered = make_rendered_alert()
    rendering_context = object()
    assembler.assemble.return_value = rendering_context
    renderer.render.return_value = rendered
    decision = object()
    as_of = datetime(2026, 5, 9, 14, 33, 4, tzinfo=timezone.utc)

    pipeline = PreviewPipeline(assembler, renderer, dispatcher)
    pipeline.handle(decision, as_of, alert_decision_id=42)

    assembler.assemble.assert_called_once_with(decision, as_of, 42)
    renderer.render.assert_called_once_with(rendering_context)
    dispatcher.dispatch.assert_called_once_with(rendered, 42)


def test_pipeline_does_not_catch_exceptions_from_collaborators():
    assembler = MagicMock()
    renderer = MagicMock()
    dispatcher = MagicMock()
    assembler.assemble.side_effect = RuntimeError("assemble failed")

    pipeline = PreviewPipeline(assembler, renderer, dispatcher)

    with pytest.raises(RuntimeError, match="assemble failed"):
        pipeline.handle(
            object(),
            datetime(2026, 5, 9, tzinfo=timezone.utc),
            alert_decision_id=1,
        )

    renderer.render.assert_not_called()
    dispatcher.dispatch.assert_not_called()


def test_pipeline_propagates_renderer_exception():
    assembler = MagicMock()
    renderer = MagicMock()
    dispatcher = MagicMock()
    assembler.assemble.return_value = object()
    renderer.render.side_effect = ValueError("render failed")

    pipeline = PreviewPipeline(assembler, renderer, dispatcher)

    with pytest.raises(ValueError, match="render failed"):
        pipeline.handle(
            object(),
            datetime(2026, 5, 9, tzinfo=timezone.utc),
            alert_decision_id=1,
        )

    dispatcher.dispatch.assert_not_called()

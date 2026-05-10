"""PHX2 renderer module.

The renderer turns an :class:`PHX2.models.AlertDecision` (plus its associated
snapshot context) into a structured :class:`PHX2.renderers.rendered_alert.RenderedAlert`,
which adapters then format for a particular output channel.

Only :class:`PHX2.renderers.context.RenderingContextAssembler` is permitted to
import repositories. The renderer and its adapters are pure functions over
pure data.
"""

from PHX2.renderers.alert_renderer import AlertRenderer
from PHX2.renderers.context import RenderingContext, RenderingContextAssembler
from PHX2.renderers.rendered_alert import (
    DRY_RUN_BANNER,
    RenderedAlert,
    Severity,
    derive_severity,
)
from PHX2.renderers.telegram_renderer import TelegramRenderer

__all__ = [
    "AlertRenderer",
    "DRY_RUN_BANNER",
    "RenderedAlert",
    "RenderingContext",
    "RenderingContextAssembler",
    "Severity",
    "TelegramRenderer",
    "derive_severity",
]

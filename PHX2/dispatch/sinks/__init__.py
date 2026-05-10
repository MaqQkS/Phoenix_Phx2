"""Sinks consume :class:`RenderedAlert` and emit it to a single destination.

Each sink owns its formatting adapter (e.g. ConsoleSink and FileSink both use
PlainTextAdapter, DiscordSink uses DiscordEmbedAdapter). Sinks never read the
clock — the dispatcher provides ``DeliveryContext.attempted_at`` for any
timestamp use.
"""

from PHX2.dispatch.sinks.base import DeliveryContext, DeliveryResult, Sink
from PHX2.dispatch.sinks.console import ConsoleSink
from PHX2.dispatch.sinks.discord import DiscordSink
from PHX2.dispatch.sinks.file_preview import FileSink

__all__ = [
    "ConsoleSink",
    "DeliveryContext",
    "DeliveryResult",
    "DiscordSink",
    "FileSink",
    "Sink",
]

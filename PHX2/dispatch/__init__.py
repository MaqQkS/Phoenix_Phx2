"""PHX2 dispatch layer (Stages 8B and 8C).

The dispatcher routes already-rendered alerts to configured sinks and records
each attempt in the ``dispatch_events`` audit table. The pipeline orchestrator
wires the renderer (Stage 8A) to the dispatcher; sinks own their adapters.

Stage 8B added the dispatcher, the audit pipeline, ConsoleSink, and FileSink
— all in-process. Stage 8C adds DiscordSink (private-preview webhook) plus
the :mod:`PHX2.dispatch.transport` HttpClient Protocol that the sink depends
on. Dispatcher, PreviewPipeline, RenderedAlert, AlertRenderer, and the
Stage 8B sinks are unchanged.
"""

from PHX2.dispatch.dispatcher import Dispatcher
from PHX2.dispatch.preview_pipeline import PreviewPipeline
from PHX2.dispatch.routing import RoutingConfig, resolve_sinks
from PHX2.dispatch.sinks.base import DeliveryContext, DeliveryResult, Sink
from PHX2.dispatch.sinks.console import ConsoleSink
from PHX2.dispatch.sinks.discord import DiscordSink
from PHX2.dispatch.sinks.file_preview import FileSink
from PHX2.dispatch.transport.http_client import HttpClient, HttpResponse

__all__ = [
    "ConsoleSink",
    "DeliveryContext",
    "DeliveryResult",
    "DiscordSink",
    "Dispatcher",
    "FileSink",
    "HttpClient",
    "HttpResponse",
    "PreviewPipeline",
    "RoutingConfig",
    "Sink",
    "resolve_sinks",
]

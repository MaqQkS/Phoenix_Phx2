"""Sink protocol and supporting dataclasses.

A sink consumes one :class:`RenderedAlert` and writes it to one destination.
Sinks must self-handle errors: ``deliver`` returns a :class:`DeliveryResult`
with ``success=False`` rather than raising. The dispatcher additionally guards
``deliver`` with a try/except as defense in depth.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Protocol

from PHX2.renderers.rendered_alert import RenderedAlert


@dataclass(frozen=True)
class DeliveryResult:
    """Outcome of a single ``Sink.deliver`` call."""

    success: bool
    payload_ref: Optional[str]
    error_message: Optional[str]


@dataclass(frozen=True)
class DeliveryContext:
    """Per-attempt context passed by the dispatcher to a sink.

    ``attempted_at`` is always UTC. Sinks must use it instead of reading the
    clock themselves so that all rows and artifacts share one timestamp.

    The ``alert_decision_id`` is no longer carried here — it is a structural
    field on :class:`RenderedAlert`, populated by the renderer from
    ``RenderingContext.alert_decision_id``. Sinks read it from the rendered
    alert rather than the delivery context.
    """

    dispatch_event_id: str
    dispatch_run_id: str
    attempted_at: datetime


class Sink(Protocol):
    """Contract a dispatcher target must satisfy.

    ``name`` is the unique identifier the dispatcher uses for routing lookup
    and for the ``target`` column in the audit row.
    """

    name: str

    def deliver(
        self,
        rendered: RenderedAlert,
        context: DeliveryContext,
    ) -> DeliveryResult: ...

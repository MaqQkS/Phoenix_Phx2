"""Console sink: format with PlainTextAdapter and write to stdout."""

import sys
from typing import TextIO

from PHX2.dispatch.sinks.base import DeliveryContext, DeliveryResult
from PHX2.renderers.adapters.plain_text import PlainTextAdapter
from PHX2.renderers.rendered_alert import RenderedAlert


class ConsoleSink:
    """Write the formatted alert to stdout, no persistent artifact.

    The header timestamp is taken from ``context.attempted_at`` so this sink
    never reads the wall clock. Tests can pass a different ``stream`` to
    capture output.
    """

    name = "console"

    def __init__(self, stream: TextIO | None = None) -> None:
        self._stream = stream if stream is not None else sys.stdout
        self._adapter = PlainTextAdapter()

    def deliver(
        self,
        rendered: RenderedAlert,
        context: DeliveryContext,
    ) -> DeliveryResult:
        try:
            tier = rendered.tier_label or "-"
            address_short = rendered.token_section.get("address_short", "?")
            timestamp = context.attempted_at.isoformat().replace("+00:00", "Z")
            header = (
                f"=== DISPATCH {context.dispatch_event_id} | "
                f"{rendered.decision_type} | {tier} | "
                f"{rendered.severity.name} | {address_short} | {timestamp} ==="
            )
            body = self._adapter.format(rendered)
            self._stream.write(header + "\n")
            self._stream.write(body + "\n")
            self._stream.flush()
        except Exception as exc:
            return DeliveryResult(
                success=False,
                payload_ref=None,
                error_message=f"{type(exc).__name__}: {exc}",
            )
        return DeliveryResult(success=True, payload_ref=None, error_message=None)

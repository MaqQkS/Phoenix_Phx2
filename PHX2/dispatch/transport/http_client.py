"""HTTP transport Protocol used by sinks that POST to remote endpoints.

The Protocol exists so :class:`PHX2.dispatch.sinks.discord.DiscordSink` can
accept any callable-shaped HTTP client. Tests pass a fake; production wiring
passes a real implementation. The sink itself never imports ``requests`` or
any other HTTP library.
"""

from dataclasses import dataclass
from typing import Dict, Protocol


@dataclass(frozen=True)
class HttpResponse:
    """A single HTTP response surfaced to a sink.

    ``headers`` is a plain ``dict[str, str]``. Case-insensitive lookup is the
    caller's responsibility — the sink probes a small set of known header
    spellings (``Retry-After``, ``retry-after``, ``X-RateLimit-Reset-After``).
    """

    status_code: int
    text: str
    headers: Dict[str, str]


class HttpClient(Protocol):
    """Minimal HTTP client contract: one POST per call, JSON body, timeout."""

    def post(self, url: str, json: dict, timeout: float) -> HttpResponse: ...

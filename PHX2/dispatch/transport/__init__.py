"""Transport abstractions for dispatch sinks.

The :class:`HttpClient` Protocol and :class:`HttpResponse` dataclass let sinks
that need to talk over HTTP (e.g., the Discord sink in 8C) depend on an
injected client rather than a concrete library. Tests inject fakes; production
wiring injects a thin wrapper around ``requests`` or ``httpx``.

Stage 8C does not ship a concrete production implementation — that is the
wiring layer's responsibility, kept outside this module so the dispatch tree
stays free of network dependencies.
"""

from PHX2.dispatch.transport.http_client import HttpClient, HttpResponse

__all__ = ["HttpClient", "HttpResponse"]

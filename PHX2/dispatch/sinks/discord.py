"""Discord private-preview sink: POST one rendered alert to a webhook.

The sink delivers an already-rendered alert to one Discord webhook in a single
POST attempt. It does not retry, queue, or back off. If Discord rejects,
fails, or rate-limits the request, the sink returns a
:class:`DeliveryResult` with ``success=False`` and a structured
``error_message`` — and never raises.

The webhook URL is constructor-injected and is never written to dispatch
events, JSONL, log lines, or error messages. The sink does not import any
HTTP library directly; the real HTTP path is provided by an injected
:class:`HttpClient`.
"""

import re
from typing import Optional

from PHX2.dispatch.sinks.base import DeliveryContext, DeliveryResult
from PHX2.dispatch.transport.http_client import HttpClient
from PHX2.renderers.adapters.discord import DiscordEmbedAdapter
from PHX2.renderers.rendered_alert import RenderedAlert


_RETRY_AFTER_HEADERS = ("Retry-After", "retry-after", "X-RateLimit-Reset-After")

SNIPPET_LIMIT = 200
URL_REDACTION_TOKEN = "[REDACTED_URL]"
_WEBHOOK_PATTERN = re.compile(
    r"https?://discord(?:app)?\.com/api/webhooks/\d+/[A-Za-z0-9_-]+"
)


def _sanitize_response_snippet(text: str, webhook_url: str) -> str:
    if not text:
        return ""
    sanitized = text.replace(webhook_url, URL_REDACTION_TOKEN)
    sanitized = _WEBHOOK_PATTERN.sub(URL_REDACTION_TOKEN, sanitized)
    sanitized = "".join(ch for ch in sanitized if ch.isprintable() or ch in " \t")
    return sanitized[:SNIPPET_LIMIT]


class DiscordSink:
    """Send one Discord webhook message per dispatch.

    ``webhook_url`` is treated as a secret: the sink never writes it into
    return values or log output. Tests must verify this invariant explicitly.
    """

    name = "discord_private_preview"

    def __init__(
        self,
        webhook_url: str,
        http_client: HttpClient,
        username: str = "PHX2 Preview",
        timeout_seconds: float = 5.0,
        adapter: Optional[DiscordEmbedAdapter] = None,
    ) -> None:
        self._webhook_url = webhook_url
        self._http_client = http_client
        self._username = username
        self._timeout_seconds = timeout_seconds
        self._adapter = adapter or DiscordEmbedAdapter()

    def deliver(
        self,
        rendered: RenderedAlert,
        context: DeliveryContext,
    ) -> DeliveryResult:
        embed = self._adapter.format(rendered)
        if embed.get("_payload_too_large"):
            length = embed.get("original_length", 0)
            return DeliveryResult(
                success=False,
                payload_ref=None,
                error_message=f"payload_too_large_after_truncation:length={length}",
            )

        payload = {"username": self._username, "embeds": [embed]}

        try:
            response = self._http_client.post(
                self._webhook_url,
                json=payload,
                timeout=self._timeout_seconds,
            )
        except Exception as exc:
            return DeliveryResult(
                success=False,
                payload_ref=None,
                error_message=f"network_error:{type(exc).__name__}",
            )

        return _map_response_to_result(response, self._webhook_url)


def _map_response_to_result(response, webhook_url: str) -> DeliveryResult:
    status = response.status_code
    if 200 <= status < 300:
        return DeliveryResult(success=True, payload_ref=None, error_message=None)
    if status == 429:
        retry_after = _extract_retry_after(response.headers)
        return DeliveryResult(
            success=False,
            payload_ref=None,
            error_message=f"rate_limited:retry_after={retry_after}",
        )
    snippet = _sanitize_response_snippet(response.text or "", webhook_url)
    if snippet:
        error_message = f"discord_error:status={status}:body={snippet}"
    else:
        error_message = f"discord_error:status={status}"
    return DeliveryResult(
        success=False,
        payload_ref=None,
        error_message=error_message,
    )


def _extract_retry_after(headers) -> str:
    if not headers:
        return "unknown"
    for key in _RETRY_AFTER_HEADERS:
        if key in headers:
            return str(headers[key])
    return "unknown"

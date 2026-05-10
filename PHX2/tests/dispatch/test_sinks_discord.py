"""DiscordSink behavior."""

from dataclasses import replace
from typing import List, Optional

import pytest

from PHX2.dispatch.sinks.base import DeliveryContext
from PHX2.dispatch.sinks.discord import DiscordSink
from PHX2.dispatch.transport.http_client import HttpResponse
from PHX2.renderers.adapters.discord import (
    DiscordEmbedAdapter,
    FIELD_VALUE_LIMIT,
)
from PHX2.renderers.rendered_alert import Severity

from PHX2.tests.dispatch._fixtures import (
    ATTEMPTED_AT,
    make_rendered_alert,
    make_rendered_block,
    make_rendered_error,
    make_rendered_skip,
)


PLACEHOLDER_URL = "https://example.invalid/webhook"


class FakeHttpClient:
    """Records every post() call and returns a canned response (or raises)."""

    def __init__(
        self,
        response: Optional[HttpResponse] = None,
        raise_exc: Optional[Exception] = None,
    ) -> None:
        self.post_calls: List[dict] = []
        self._response = response
        self._raise = raise_exc

    def post(self, url: str, json: dict, timeout: float) -> HttpResponse:
        self.post_calls.append({"url": url, "json": json, "timeout": timeout})
        if self._raise is not None:
            raise self._raise
        if self._response is None:
            return HttpResponse(status_code=200, text="", headers={})
        return self._response


def _context(event_id: str = "evt-abc") -> DeliveryContext:
    return DeliveryContext(
        dispatch_event_id=event_id,
        dispatch_run_id="run-1",
        attempted_at=ATTEMPTED_AT,
    )


# ---- success paths ------------------------------------------------------


def test_200_returns_success():
    client = FakeHttpClient(response=HttpResponse(200, "ok", {}))
    sink = DiscordSink(webhook_url=PLACEHOLDER_URL, http_client=client)

    result = sink.deliver(make_rendered_alert(), _context())

    assert result.success is True
    assert result.payload_ref is None
    assert result.error_message is None


def test_204_returns_success():
    client = FakeHttpClient(response=HttpResponse(204, "", {}))
    sink = DiscordSink(webhook_url=PLACEHOLDER_URL, http_client=client)

    result = sink.deliver(make_rendered_alert(), _context())

    assert result.success is True


def test_post_call_uses_constructor_webhook_url():
    client = FakeHttpClient(response=HttpResponse(204, "", {}))
    sink = DiscordSink(webhook_url=PLACEHOLDER_URL, http_client=client)

    sink.deliver(make_rendered_alert(), _context())

    assert len(client.post_calls) == 1
    assert client.post_calls[0]["url"] == PLACEHOLDER_URL


def test_post_payload_contains_username_and_embeds():
    client = FakeHttpClient(response=HttpResponse(204, "", {}))
    sink = DiscordSink(webhook_url=PLACEHOLDER_URL, http_client=client)

    sink.deliver(make_rendered_alert(), _context())

    payload = client.post_calls[0]["json"]
    assert "username" in payload
    assert "embeds" in payload
    assert isinstance(payload["embeds"], list)
    assert len(payload["embeds"]) == 1


def test_embed_in_payload_matches_adapter_output():
    rendered = make_rendered_alert()
    expected_embed = DiscordEmbedAdapter().format(rendered)

    client = FakeHttpClient(response=HttpResponse(204, "", {}))
    sink = DiscordSink(webhook_url=PLACEHOLDER_URL, http_client=client)

    sink.deliver(rendered, _context())

    assert client.post_calls[0]["json"]["embeds"][0] == expected_embed


def test_default_username_appears_in_payload():
    client = FakeHttpClient(response=HttpResponse(204, "", {}))
    sink = DiscordSink(webhook_url=PLACEHOLDER_URL, http_client=client)

    sink.deliver(make_rendered_alert(), _context())

    assert client.post_calls[0]["json"]["username"] == "PHX2 Preview"


def test_custom_username_appears_in_payload():
    client = FakeHttpClient(response=HttpResponse(204, "", {}))
    sink = DiscordSink(
        webhook_url=PLACEHOLDER_URL,
        http_client=client,
        username="Custom",
    )

    sink.deliver(make_rendered_alert(), _context())

    assert client.post_calls[0]["json"]["username"] == "Custom"


def test_default_timeout_forwarded_to_http_client():
    client = FakeHttpClient(response=HttpResponse(204, "", {}))
    sink = DiscordSink(webhook_url=PLACEHOLDER_URL, http_client=client)

    sink.deliver(make_rendered_alert(), _context())

    assert client.post_calls[0]["timeout"] == 5.0


def test_custom_timeout_forwarded_to_http_client():
    client = FakeHttpClient(response=HttpResponse(204, "", {}))
    sink = DiscordSink(
        webhook_url=PLACEHOLDER_URL,
        http_client=client,
        timeout_seconds=10.0,
    )

    sink.deliver(make_rendered_alert(), _context())

    assert client.post_calls[0]["timeout"] == 10.0


def test_payload_ref_is_none_on_success():
    client = FakeHttpClient(response=HttpResponse(200, "ok", {}))
    sink = DiscordSink(webhook_url=PLACEHOLDER_URL, http_client=client)

    result = sink.deliver(make_rendered_alert(), _context())

    assert result.payload_ref is None


# ---- 429 rate limit handling -------------------------------------------


def test_429_with_retry_after_extracts_value():
    client = FakeHttpClient(
        response=HttpResponse(429, "rate limited", {"Retry-After": "5"})
    )
    sink = DiscordSink(webhook_url=PLACEHOLDER_URL, http_client=client)

    result = sink.deliver(make_rendered_alert(), _context())

    assert len(client.post_calls) == 1, "DiscordSink must make exactly one POST attempt"
    assert result.success is False
    assert result.error_message == "rate_limited:retry_after=5"
    assert result.payload_ref is None


def test_429_with_lowercase_retry_after_extracts_value():
    client = FakeHttpClient(
        response=HttpResponse(429, "rate limited", {"retry-after": "10"})
    )
    sink = DiscordSink(webhook_url=PLACEHOLDER_URL, http_client=client)

    result = sink.deliver(make_rendered_alert(), _context())

    assert len(client.post_calls) == 1, "DiscordSink must make exactly one POST attempt"
    assert result.error_message == "rate_limited:retry_after=10"


def test_429_with_x_ratelimit_reset_after_extracts_value():
    client = FakeHttpClient(
        response=HttpResponse(429, "rate limited", {"X-RateLimit-Reset-After": "0.5"})
    )
    sink = DiscordSink(webhook_url=PLACEHOLDER_URL, http_client=client)

    result = sink.deliver(make_rendered_alert(), _context())

    assert len(client.post_calls) == 1, "DiscordSink must make exactly one POST attempt"
    assert result.error_message == "rate_limited:retry_after=0.5"


def test_429_without_any_retry_after_header_uses_unknown():
    client = FakeHttpClient(response=HttpResponse(429, "rate limited", {}))
    sink = DiscordSink(webhook_url=PLACEHOLDER_URL, http_client=client)

    result = sink.deliver(make_rendered_alert(), _context())

    assert len(client.post_calls) == 1, "DiscordSink must make exactly one POST attempt"
    assert result.error_message == "rate_limited:retry_after=unknown"


def test_429_url_does_not_appear_in_error_message():
    client = FakeHttpClient(
        response=HttpResponse(429, "rate limited", {"Retry-After": "5"})
    )
    sink = DiscordSink(webhook_url=PLACEHOLDER_URL, http_client=client)

    result = sink.deliver(make_rendered_alert(), _context())

    assert len(client.post_calls) == 1, "DiscordSink must make exactly one POST attempt"
    assert PLACEHOLDER_URL not in (result.error_message or "")


# ---- non-2xx error handling --------------------------------------------


def test_500_returns_failure_with_status_in_message():
    client = FakeHttpClient(response=HttpResponse(500, "server error", {}))
    sink = DiscordSink(webhook_url=PLACEHOLDER_URL, http_client=client)

    result = sink.deliver(make_rendered_alert(), _context())

    assert len(client.post_calls) == 1, "DiscordSink must make exactly one POST attempt"
    assert result.success is False
    assert (result.error_message or "").startswith("discord_error:status=500")
    assert result.payload_ref is None


def test_400_returns_failure_with_status_in_message():
    client = FakeHttpClient(
        response=HttpResponse(400, "{ not valid json", {})
    )
    sink = DiscordSink(webhook_url=PLACEHOLDER_URL, http_client=client)

    result = sink.deliver(make_rendered_alert(), _context())

    assert len(client.post_calls) == 1, "DiscordSink must make exactly one POST attempt"
    assert result.success is False
    assert result.error_message.startswith("discord_error:status=400")
    assert ":body={ not valid json" in result.error_message


def test_500_url_does_not_appear_in_error_message():
    client = FakeHttpClient(response=HttpResponse(500, "server error", {}))
    sink = DiscordSink(webhook_url=PLACEHOLDER_URL, http_client=client)

    result = sink.deliver(make_rendered_alert(), _context())

    assert len(client.post_calls) == 1, "DiscordSink must make exactly one POST attempt"
    assert PLACEHOLDER_URL not in (result.error_message or "")


def test_500_returns_failure_with_status_and_body_snippet():
    client = FakeHttpClient(response=HttpResponse(500, "server error", {}))
    sink = DiscordSink(webhook_url=PLACEHOLDER_URL, http_client=client)

    result = sink.deliver(make_rendered_alert(), _context())

    assert result.success is False
    assert result.error_message == "discord_error:status=500:body=server error"


def test_400_with_json_body_includes_body_in_error_message():
    body = '{"message":"Embed field name too long"}'
    client = FakeHttpClient(response=HttpResponse(400, body, {}))
    sink = DiscordSink(webhook_url=PLACEHOLDER_URL, http_client=client)

    result = sink.deliver(make_rendered_alert(), _context())

    assert result.success is False
    assert "status=400" in (result.error_message or "")
    assert "Embed field name too long" in (result.error_message or "")


def test_500_response_body_with_constructor_webhook_url_is_redacted():
    # URL is split to avoid matching test_static_webhook_leak's pattern.
    secret_url = "https://discord" + ".com/api/webhooks/123456789/secret-tenant-A-token"
    body = f"upstream error from {secret_url} please retry"
    client = FakeHttpClient(response=HttpResponse(500, body, {}))
    sink = DiscordSink(webhook_url=secret_url, http_client=client)

    result = sink.deliver(make_rendered_alert(), _context())

    assert result.success is False
    assert secret_url not in (result.error_message or "")
    assert "[REDACTED_URL]" in (result.error_message or "")


def test_400_response_body_with_other_tenant_webhook_url_is_redacted():
    other_tenant_url = "https://discord" + ".com/api/webhooks/987654321/other-tenant-token"
    body = f'{{"hint":"forwarded by {other_tenant_url}"}}'
    client = FakeHttpClient(response=HttpResponse(400, body, {}))
    sink = DiscordSink(webhook_url=PLACEHOLDER_URL, http_client=client)

    result = sink.deliver(make_rendered_alert(), _context())

    assert result.success is False
    assert other_tenant_url not in (result.error_message or "")
    assert "[REDACTED_URL]" in (result.error_message or "")


def test_400_with_empty_body_omits_body_suffix():
    client = FakeHttpClient(response=HttpResponse(400, "", {}))
    sink = DiscordSink(webhook_url=PLACEHOLDER_URL, http_client=client)

    result = sink.deliver(make_rendered_alert(), _context())

    assert result.success is False
    assert result.error_message == "discord_error:status=400"


def test_400_with_oversized_body_truncates_to_snippet_limit():
    from PHX2.dispatch.sinks.discord import SNIPPET_LIMIT

    body = "X" * (SNIPPET_LIMIT * 3)
    client = FakeHttpClient(response=HttpResponse(400, body, {}))
    sink = DiscordSink(webhook_url=PLACEHOLDER_URL, http_client=client)

    result = sink.deliver(make_rendered_alert(), _context())

    assert result.success is False
    prefix = "discord_error:status=400:body="
    assert (result.error_message or "").startswith(prefix)
    body_part = (result.error_message or "")[len(prefix):]
    assert len(body_part) == SNIPPET_LIMIT
    assert body_part == "X" * SNIPPET_LIMIT


# ---- network errors ----------------------------------------------------


def test_timeout_error_returns_network_error():
    client = FakeHttpClient(raise_exc=TimeoutError("slow"))
    sink = DiscordSink(webhook_url=PLACEHOLDER_URL, http_client=client)

    result = sink.deliver(make_rendered_alert(), _context())

    assert len(client.post_calls) == 1, "DiscordSink must make exactly one POST attempt"
    assert result.success is False
    assert result.error_message == "network_error:TimeoutError"
    assert result.payload_ref is None


def test_connection_error_returns_network_error():
    client = FakeHttpClient(raise_exc=ConnectionError("refused"))
    sink = DiscordSink(webhook_url=PLACEHOLDER_URL, http_client=client)

    result = sink.deliver(make_rendered_alert(), _context())

    assert len(client.post_calls) == 1, "DiscordSink must make exactly one POST attempt"
    assert result.success is False
    assert result.error_message == "network_error:ConnectionError"


def test_unexpected_exception_returns_network_error():
    class WeirdError(Exception):
        pass

    client = FakeHttpClient(raise_exc=WeirdError("unknown"))
    sink = DiscordSink(webhook_url=PLACEHOLDER_URL, http_client=client)

    result = sink.deliver(make_rendered_alert(), _context())

    assert len(client.post_calls) == 1, "DiscordSink must make exactly one POST attempt"
    assert result.success is False
    assert result.error_message == "network_error:WeirdError"


def test_network_error_url_does_not_appear_in_error_message():
    client = FakeHttpClient(raise_exc=TimeoutError("slow"))
    sink = DiscordSink(webhook_url=PLACEHOLDER_URL, http_client=client)

    result = sink.deliver(make_rendered_alert(), _context())

    assert len(client.post_calls) == 1, "DiscordSink must make exactly one POST attempt"
    assert PLACEHOLDER_URL not in (result.error_message or "")


# ---- never raises ------------------------------------------------------


@pytest.mark.parametrize(
    "client_factory",
    [
        lambda: FakeHttpClient(response=HttpResponse(200, "", {})),
        lambda: FakeHttpClient(response=HttpResponse(204, "", {})),
        lambda: FakeHttpClient(
            response=HttpResponse(429, "", {"Retry-After": "1"})
        ),
        lambda: FakeHttpClient(response=HttpResponse(429, "", {})),
        lambda: FakeHttpClient(response=HttpResponse(400, "", {})),
        lambda: FakeHttpClient(response=HttpResponse(500, "", {})),
        lambda: FakeHttpClient(raise_exc=TimeoutError("t")),
        lambda: FakeHttpClient(raise_exc=ConnectionError("c")),
        lambda: FakeHttpClient(raise_exc=RuntimeError("r")),
    ],
)
def test_deliver_never_raises(client_factory):
    sink = DiscordSink(webhook_url=PLACEHOLDER_URL, http_client=client_factory())
    # Should not raise.
    sink.deliver(make_rendered_alert(), _context())


@pytest.mark.parametrize(
    "rendered_factory",
    [
        make_rendered_alert,
        make_rendered_skip,
        make_rendered_block,
        make_rendered_error,
    ],
)
def test_deliver_handles_all_rendered_alert_shapes(rendered_factory):
    client = FakeHttpClient(response=HttpResponse(204, "", {}))
    sink = DiscordSink(webhook_url=PLACEHOLDER_URL, http_client=client)

    result = sink.deliver(rendered_factory(), _context())

    assert result.success is True


# ---- payload too large --------------------------------------------------


def test_oversized_payload_returns_failure_without_posting():
    rendered = make_rendered_alert()
    huge_value = "X" * (FIELD_VALUE_LIMIT - 20)
    rendered = replace(
        rendered,
        token_section={**rendered.token_section, "address": huge_value},
        market_section={
            **rendered.market_section,
            "current_mc": huge_value,
            "ath_mc": huge_value,
        },
        ath_section={**rendered.ath_section, "source": huge_value},
        field_section={**rendered.field_section, "lp_floor_label": huge_value},
        clock_section={**rendered.clock_section, "token_age": huge_value},
        missing_section=[huge_value],
    )

    client = FakeHttpClient(response=HttpResponse(204, "", {}))
    sink = DiscordSink(webhook_url=PLACEHOLDER_URL, http_client=client)

    result = sink.deliver(rendered, _context())

    assert result.success is False
    assert (result.error_message or "").startswith(
        "payload_too_large_after_truncation:length="
    )
    assert client.post_calls == []  # NO post attempted


# ---- url leak: parametrized over every error scenario ------------------


@pytest.mark.parametrize(
    "client_factory",
    [
        lambda: FakeHttpClient(
            response=HttpResponse(429, "", {"Retry-After": "1"})
        ),
        lambda: FakeHttpClient(response=HttpResponse(429, "", {})),
        lambda: FakeHttpClient(response=HttpResponse(400, "", {})),
        lambda: FakeHttpClient(response=HttpResponse(500, "", {})),
        lambda: FakeHttpClient(raise_exc=TimeoutError("t")),
        lambda: FakeHttpClient(raise_exc=ConnectionError("c")),
        lambda: FakeHttpClient(raise_exc=RuntimeError("r")),
    ],
)
def test_webhook_url_never_appears_in_any_failure_message(client_factory):
    secret_url = "https://example.invalid/super-secret-webhook-token-XYZ"
    client = client_factory()
    sink = DiscordSink(webhook_url=secret_url, http_client=client)

    result = sink.deliver(make_rendered_alert(), _context())

    assert result.success is False
    assert len(client.post_calls) == 1, "DiscordSink must make exactly one POST attempt"
    assert secret_url not in (result.error_message or "")
    assert result.payload_ref is None


def test_payload_too_large_does_not_leak_webhook_url():
    secret_url = "https://example.invalid/super-secret-webhook-token-XYZ"
    rendered = make_rendered_alert()
    huge_value = "X" * (FIELD_VALUE_LIMIT - 20)
    rendered = replace(
        rendered,
        token_section={**rendered.token_section, "address": huge_value},
        market_section={
            **rendered.market_section,
            "current_mc": huge_value,
            "ath_mc": huge_value,
        },
        ath_section={**rendered.ath_section, "source": huge_value},
        field_section={**rendered.field_section, "lp_floor_label": huge_value},
        clock_section={**rendered.clock_section, "token_age": huge_value},
        missing_section=[huge_value],
    )

    client = FakeHttpClient(response=HttpResponse(204, "", {}))
    sink = DiscordSink(webhook_url=secret_url, http_client=client)

    result = sink.deliver(rendered, _context())

    assert result.success is False
    assert client.post_calls == []  # adapter rejects payload before HTTP call
    assert secret_url not in (result.error_message or "")
    assert result.payload_ref is None


# ---- name --------------------------------------------------------------


def test_sink_name_matches_routing_target():
    client = FakeHttpClient(response=HttpResponse(204, "", {}))
    sink = DiscordSink(webhook_url=PLACEHOLDER_URL, http_client=client)
    assert sink.name == "discord_private_preview"


# ---- adapter injection -------------------------------------------------


def test_custom_adapter_is_used():
    class StubAdapter:
        def format(self, rendered):
            return {"author": {"name": "stub"}, "title": "stub", "fields": []}

    client = FakeHttpClient(response=HttpResponse(204, "", {}))
    sink = DiscordSink(
        webhook_url=PLACEHOLDER_URL,
        http_client=client,
        adapter=StubAdapter(),
    )

    sink.deliver(make_rendered_alert(), _context())

    assert client.post_calls[0]["json"]["embeds"][0] == {
        "author": {"name": "stub"},
        "title": "stub",
        "fields": [],
    }

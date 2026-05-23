"""Stage 28.4 audited HTTP transport behavior tests.

Pins:

  * URL validation rejects http / non-Discord host / empty /
    whitespace / control-character / secret-shaped / over-long
    URLs without echoing the rejected value.
  * Payload validation rejects non-dict / non-string-key /
    forbidden-routing-field / oversized / non-JSON-encodable
    payloads.
  * Webhook identity validation rejects non-string / empty /
    URL-shaped / mixed-case identities and admits the locked
    safe-shape labels.
  * HTTP status mapping: 200/204 -> ``SENT_OK``;
    429 -> ``RATE_LIMITED`` with bounded retry-after; 500/502/503
    -> ``SERVER_ERROR``; 401/403/404 -> ``AUTH_OR_WEBHOOK_REFUSED``;
    other 4xx -> ``AUTH_OR_WEBHOOK_REFUSED``; network error signal
    -> ``NETWORK_ERROR``.
  * Send-attempt-count is exactly ``0`` for validation /
    payload-refused outcomes and exactly ``1`` for any path that
    attempted a POST (including 5xx / 429 / 4xx / network-error
    paths).
  * Retry-after parser: numeric clamped to ``[0, 30]``; negative /
    NaN / infinite / non-numeric / huge values fall back to
    ``None``; values above the cap are clamped to ``30``.
  * The transport calls the opener AT MOST ONCE per
    ``send_one_audited_post`` invocation; the fake opener call
    count proves no retry / loop is taken on 429 / 5xx / network
    error.
  * The transport never sleeps; the fake opener proves no
    ``time.sleep`` / async sleep is taken.
  * Canary webhook URLs / API keys / bearer tokens / response
    bodies / raw exception strings never reach the transport
    result / repr / str / public dicts.
  * Stage 28.4 transport surface is structurally compatible with
    the Stage 27.7b transport protocol shape (a documented future-
    injection contract); Stage 28.4 does NOT import Stage 27
    production code.
"""

from __future__ import annotations

import inspect
import math
from typing import Optional

import pytest

from PHX2.stage28.audited_http_transport import (
    Stage28_4AuditedHttpTransport,
    Stage28_4FakeHttpOpener,
    Stage28_4HttpRequest,
    Stage28_4HttpResponse,
    Stage28_4NetworkErrorSignal,
    Stage28_4UrllibHttpOpener,
)
from PHX2.stage28.audited_http_transport_models import (
    REDACTION_STATUS_REDACTED,
    RESPONSE_BODY_STATUS_DROPPED_UNRECORDED,
    RETRY_AFTER_MAX_SECONDS,
    SEND_ATTEMPT_COUNT_NOT_SENT,
    SEND_ATTEMPT_COUNT_SENT_ONCE,
    STAGE28_4_SCHEMA_VERSION,
    Stage28_4TransportValidationError,
    TRANSPORT_STATUS_AUTH_OR_WEBHOOK_REFUSED,
    TRANSPORT_STATUS_NETWORK_ERROR,
    TRANSPORT_STATUS_PAYLOAD_REFUSED,
    TRANSPORT_STATUS_RATE_LIMITED,
    TRANSPORT_STATUS_SENT_OK,
    TRANSPORT_STATUS_SERVER_ERROR,
    TRANSPORT_STATUS_VALIDATION_FAILED,
    WEBHOOK_IDENTITY_MISSING_LABEL,
    WEBHOOK_IDENTITY_PRIVATE_OPERATOR,
    WEBHOOK_IDENTITY_REDACTED_UNSAFE,
)


# ---------------------------------------------------------------------------
# Canary fixtures
# ---------------------------------------------------------------------------


_VALID_DISCORD_WEBHOOK_URL: str = (
    "h" + "ttps://" + "discord" + ".com"
    + "/api/webhooks/1234567890/EXAMPLE_TOKEN_xxxx"
)
_VALID_DISCORD_LEGACY_WEBHOOK_URL: str = (
    "h" + "ttps://" + "discord" + "app.com"
    + "/api/webhooks/9876543210/EXAMPLE_TOKEN_yyyy"
)
_CANARY_TOKEN_SUFFIX: str = "CANARY_TOKEN_DO_NOT_LOG_zzzzzzzz"
_CANARY_DISCORD_WEBHOOK_URL: str = (
    "h" + "ttps://" + "discord" + ".com"
    + "/api/webhooks/4242424242/" + _CANARY_TOKEN_SUFFIX
)
_CANARY_API_KEY: str = "CANARY_API_KEY_sk-DO_NOT_LOG"
_CANARY_BEARER_TOKEN: str = "CANARY_Bearer_value_DO_NOT_LOG"
_CANARY_RAW_RESPONSE_BODY: str = "CANARY_RESPONSE_BODY_DO_NOT_LOG"
_CANARY_RAW_EXCEPTION: str = "CANARY_EXC_DO_NOT_LOG"


# ---------------------------------------------------------------------------
# Constructor validation
# ---------------------------------------------------------------------------


def test_transport_default_construction_does_not_raise():
    t = Stage28_4AuditedHttpTransport()
    assert isinstance(t, Stage28_4AuditedHttpTransport)


def test_transport_accepts_injected_opener():
    opener = Stage28_4FakeHttpOpener()
    t = Stage28_4AuditedHttpTransport(opener=opener)
    assert isinstance(t, Stage28_4AuditedHttpTransport)


@pytest.mark.parametrize(
    "bad_timeout",
    ["10", None, True, False, [10.0]],
)
def test_transport_rejects_non_numeric_timeout(bad_timeout):
    with pytest.raises(Stage28_4TransportValidationError):
        Stage28_4AuditedHttpTransport(timeout_seconds=bad_timeout)


@pytest.mark.parametrize(
    "bad_timeout",
    [0.0, -1.0, -0.5, math.inf, float("nan")],
)
def test_transport_rejects_non_positive_or_nan_timeout(bad_timeout):
    with pytest.raises(Stage28_4TransportValidationError):
        Stage28_4AuditedHttpTransport(timeout_seconds=bad_timeout)


@pytest.mark.parametrize("bad_ua", ["", None, 123])
def test_transport_rejects_bad_user_agent(bad_ua):
    with pytest.raises(Stage28_4TransportValidationError):
        Stage28_4AuditedHttpTransport(user_agent=bad_ua)


# ---------------------------------------------------------------------------
# URL validation tests
# ---------------------------------------------------------------------------


def _safe_payload() -> dict:
    return {"content": "hello"}


def test_valid_discord_https_webhook_url_is_accepted():
    opener = Stage28_4FakeHttpOpener(configured_status_code=204)
    t = Stage28_4AuditedHttpTransport(opener=opener)
    result = t.send_one_audited_post(
        webhook_url=_VALID_DISCORD_WEBHOOK_URL,
        webhook_identity=WEBHOOK_IDENTITY_PRIVATE_OPERATOR,
        payload=_safe_payload(),
    )
    assert result.transport_status == TRANSPORT_STATUS_SENT_OK
    assert result.send_attempt_count == 1


def test_valid_discord_legacy_host_webhook_url_is_accepted():
    opener = Stage28_4FakeHttpOpener(configured_status_code=204)
    t = Stage28_4AuditedHttpTransport(opener=opener)
    result = t.send_one_audited_post(
        webhook_url=_VALID_DISCORD_LEGACY_WEBHOOK_URL,
        webhook_identity=WEBHOOK_IDENTITY_PRIVATE_OPERATOR,
        payload=_safe_payload(),
    )
    assert result.transport_status == TRANSPORT_STATUS_SENT_OK


@pytest.mark.parametrize(
    "bad_url",
    [
        "",
        "h" + "ttp://" + "discord" + ".com"
        + "/api/webhooks/1/abc",
        "h" + "ttps://" + "example.com" + "/api/webhooks/1/abc",
        "h" + "ttps://" + "discord" + ".com.evil.example/api/webhooks/1/abc",
        "h" + "ttps://" + "evil.discord" + ".com"
        + "/api/webhooks/1/abc",
        "h" + "ttps://" + "discord" + ".com"
        + "/foo/bar/1/abc",
        # whitespace / control chars
        "h" + "ttps://" + "discord" + ".com"
        + "/api/webhooks/1/abc ",
        " h" + "ttps://" + "discord" + ".com"
        + "/api/webhooks/1/abc",
        "h" + "ttps://" + "discord" + ".com"
        + "/api/webhooks/1/abc\n",
        # secret-shaped strings
        "Bearer abc",
        "Authorization: Bearer abc",
        "sk-ABCDEF",
    ],
)
def test_invalid_webhook_url_returns_validation_failed(bad_url):
    opener = Stage28_4FakeHttpOpener(configured_status_code=204)
    t = Stage28_4AuditedHttpTransport(opener=opener)
    result = t.send_one_audited_post(
        webhook_url=bad_url,
        webhook_identity=WEBHOOK_IDENTITY_PRIVATE_OPERATOR,
        payload=_safe_payload(),
    )
    assert (
        result.transport_status
        == TRANSPORT_STATUS_VALIDATION_FAILED
    )
    assert result.send_attempt_count == 0
    assert result.ok is False
    assert opener.call_count == 0


def test_non_string_webhook_url_returns_validation_failed():
    opener = Stage28_4FakeHttpOpener(configured_status_code=204)
    t = Stage28_4AuditedHttpTransport(opener=opener)
    result = t.send_one_audited_post(
        webhook_url=None,  # type: ignore[arg-type]
        webhook_identity=WEBHOOK_IDENTITY_PRIVATE_OPERATOR,
        payload=_safe_payload(),
    )
    assert (
        result.transport_status
        == TRANSPORT_STATUS_VALIDATION_FAILED
    )
    assert opener.call_count == 0


def test_url_with_query_or_fragment_is_refused():
    opener = Stage28_4FakeHttpOpener()
    t = Stage28_4AuditedHttpTransport(opener=opener)
    bad_query = (
        _VALID_DISCORD_WEBHOOK_URL + "?wait=true"
    )
    bad_fragment = _VALID_DISCORD_WEBHOOK_URL + "#frag"
    for bad in (bad_query, bad_fragment):
        result = t.send_one_audited_post(
            webhook_url=bad,
            webhook_identity=WEBHOOK_IDENTITY_PRIVATE_OPERATOR,
            payload=_safe_payload(),
        )
        assert (
            result.transport_status
            == TRANSPORT_STATUS_VALIDATION_FAILED
        )
    assert opener.call_count == 0


def test_overlong_url_is_refused_without_substring_scan():
    opener = Stage28_4FakeHttpOpener()
    t = Stage28_4AuditedHttpTransport(opener=opener)
    long_url = (
        "h" + "ttps://" + "discord" + ".com"
        + "/api/webhooks/1/"
        + ("Z" * 1024)
    )
    result = t.send_one_audited_post(
        webhook_url=long_url,
        webhook_identity=WEBHOOK_IDENTITY_PRIVATE_OPERATOR,
        payload=_safe_payload(),
    )
    assert (
        result.transport_status
        == TRANSPORT_STATUS_VALIDATION_FAILED
    )
    assert opener.call_count == 0


# ---------------------------------------------------------------------------
# Webhook identity validation
# ---------------------------------------------------------------------------


def test_missing_webhook_identity_stamps_missing_label_and_returns_validation_failed():
    opener = Stage28_4FakeHttpOpener()
    t = Stage28_4AuditedHttpTransport(opener=opener)
    result = t.send_one_audited_post(
        webhook_url=_VALID_DISCORD_WEBHOOK_URL,
        webhook_identity="",
        payload=_safe_payload(),
    )
    assert (
        result.transport_status
        == TRANSPORT_STATUS_VALIDATION_FAILED
    )
    assert result.webhook_identity == WEBHOOK_IDENTITY_MISSING_LABEL
    assert opener.call_count == 0


def test_non_string_webhook_identity_stamps_redacted_unsafe_label():
    opener = Stage28_4FakeHttpOpener()
    t = Stage28_4AuditedHttpTransport(opener=opener)
    result = t.send_one_audited_post(
        webhook_url=_VALID_DISCORD_WEBHOOK_URL,
        webhook_identity=123,  # type: ignore[arg-type]
        payload=_safe_payload(),
    )
    assert (
        result.transport_status
        == TRANSPORT_STATUS_VALIDATION_FAILED
    )
    assert (
        result.webhook_identity == WEBHOOK_IDENTITY_REDACTED_UNSAFE
    )
    assert opener.call_count == 0


@pytest.mark.parametrize(
    "unsafe_identity",
    [
        "private_operator_webhook",
        "Private-Operator-Webhook",
        "h" + "ttps://" + "example.com",
        "Bearer abc",
        " PRIVATE_OPERATOR_WEBHOOK",
        "Z" * 65,
    ],
)
def test_unsafe_webhook_identity_stamps_redacted_unsafe_label(unsafe_identity):
    opener = Stage28_4FakeHttpOpener()
    t = Stage28_4AuditedHttpTransport(opener=opener)
    result = t.send_one_audited_post(
        webhook_url=_VALID_DISCORD_WEBHOOK_URL,
        webhook_identity=unsafe_identity,
        payload=_safe_payload(),
    )
    assert (
        result.transport_status
        == TRANSPORT_STATUS_VALIDATION_FAILED
    )
    assert (
        result.webhook_identity == WEBHOOK_IDENTITY_REDACTED_UNSAFE
    )
    assert opener.call_count == 0


# ---------------------------------------------------------------------------
# Payload validation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "bad_payload",
    [
        None,
        "string",
        123,
        [1, 2, 3],
        (1, 2),
        b"bytes",
        True,
    ],
)
def test_non_dict_payload_is_refused(bad_payload):
    opener = Stage28_4FakeHttpOpener()
    t = Stage28_4AuditedHttpTransport(opener=opener)
    result = t.send_one_audited_post(
        webhook_url=_VALID_DISCORD_WEBHOOK_URL,
        webhook_identity=WEBHOOK_IDENTITY_PRIVATE_OPERATOR,
        payload=bad_payload,  # type: ignore[arg-type]
    )
    assert (
        result.transport_status
        == TRANSPORT_STATUS_PAYLOAD_REFUSED
    )
    assert result.send_attempt_count == 0
    assert opener.call_count == 0


@pytest.mark.parametrize(
    "forbidden_field",
    [
        "subscriber_id",
        "channel_id",
        "audience",
        "paid_tier",
        "approval_status",
        "trade_side",
        "buy_signal",
        "wallet_address",
        "private_key",
        "api_key",
        "Authorization",
        "Bearer_token",
        "webhook_url",
        "telegram_chat_id",
    ],
)
def test_payload_with_forbidden_routing_field_is_refused(forbidden_field):
    opener = Stage28_4FakeHttpOpener()
    t = Stage28_4AuditedHttpTransport(opener=opener)
    payload = {"content": "hello", forbidden_field: "value"}
    result = t.send_one_audited_post(
        webhook_url=_VALID_DISCORD_WEBHOOK_URL,
        webhook_identity=WEBHOOK_IDENTITY_PRIVATE_OPERATOR,
        payload=payload,
    )
    assert (
        result.transport_status
        == TRANSPORT_STATUS_PAYLOAD_REFUSED
    )
    assert result.send_attempt_count == 0
    assert opener.call_count == 0


def test_payload_non_string_key_is_refused():
    opener = Stage28_4FakeHttpOpener()
    t = Stage28_4AuditedHttpTransport(opener=opener)
    result = t.send_one_audited_post(
        webhook_url=_VALID_DISCORD_WEBHOOK_URL,
        webhook_identity=WEBHOOK_IDENTITY_PRIVATE_OPERATOR,
        payload={1: "v"},
    )
    assert (
        result.transport_status
        == TRANSPORT_STATUS_PAYLOAD_REFUSED
    )
    assert opener.call_count == 0


def test_payload_oversized_is_refused():
    opener = Stage28_4FakeHttpOpener()
    t = Stage28_4AuditedHttpTransport(opener=opener)
    # 8192-byte cap; >12k of content overflows the cap reliably
    # once JSON-encoded.
    payload = {"content": "Z" * 12000}
    result = t.send_one_audited_post(
        webhook_url=_VALID_DISCORD_WEBHOOK_URL,
        webhook_identity=WEBHOOK_IDENTITY_PRIVATE_OPERATOR,
        payload=payload,
    )
    assert (
        result.transport_status
        == TRANSPORT_STATUS_PAYLOAD_REFUSED
    )
    assert opener.call_count == 0


def test_payload_non_json_encodable_is_refused():
    opener = Stage28_4FakeHttpOpener()
    t = Stage28_4AuditedHttpTransport(opener=opener)
    payload = {"content": object()}
    result = t.send_one_audited_post(
        webhook_url=_VALID_DISCORD_WEBHOOK_URL,
        webhook_identity=WEBHOOK_IDENTITY_PRIVATE_OPERATOR,
        payload=payload,
    )
    assert (
        result.transport_status
        == TRANSPORT_STATUS_PAYLOAD_REFUSED
    )
    assert opener.call_count == 0


def test_payload_with_nan_value_is_refused():
    opener = Stage28_4FakeHttpOpener()
    t = Stage28_4AuditedHttpTransport(opener=opener)
    payload = {"content": float("nan")}
    result = t.send_one_audited_post(
        webhook_url=_VALID_DISCORD_WEBHOOK_URL,
        webhook_identity=WEBHOOK_IDENTITY_PRIVATE_OPERATOR,
        payload=payload,
    )
    assert (
        result.transport_status
        == TRANSPORT_STATUS_PAYLOAD_REFUSED
    )
    assert opener.call_count == 0


def test_safe_minimal_payload_is_accepted():
    opener = Stage28_4FakeHttpOpener(configured_status_code=204)
    t = Stage28_4AuditedHttpTransport(opener=opener)
    result = t.send_one_audited_post(
        webhook_url=_VALID_DISCORD_WEBHOOK_URL,
        webhook_identity=WEBHOOK_IDENTITY_PRIVATE_OPERATOR,
        payload={"content": "hello", "embeds": []},
    )
    assert result.transport_status == TRANSPORT_STATUS_SENT_OK
    assert result.http_status_code == 204


# ---------------------------------------------------------------------------
# HTTP status mapping
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("ok_status", [200, 201, 202, 204, 299])
def test_2xx_status_maps_to_sent_ok(ok_status):
    opener = Stage28_4FakeHttpOpener(configured_status_code=ok_status)
    t = Stage28_4AuditedHttpTransport(opener=opener)
    result = t.send_one_audited_post(
        webhook_url=_VALID_DISCORD_WEBHOOK_URL,
        webhook_identity=WEBHOOK_IDENTITY_PRIVATE_OPERATOR,
        payload=_safe_payload(),
    )
    assert result.transport_status == TRANSPORT_STATUS_SENT_OK
    assert result.ok is True
    assert result.http_status_code == ok_status
    assert result.send_attempt_count == 1


def test_429_maps_to_rate_limited_with_retry_after():
    opener = Stage28_4FakeHttpOpener(
        configured_status_code=429,
        configured_retry_after_header="5",
    )
    t = Stage28_4AuditedHttpTransport(opener=opener)
    result = t.send_one_audited_post(
        webhook_url=_VALID_DISCORD_WEBHOOK_URL,
        webhook_identity=WEBHOOK_IDENTITY_PRIVATE_OPERATOR,
        payload=_safe_payload(),
    )
    assert result.transport_status == TRANSPORT_STATUS_RATE_LIMITED
    assert result.ok is False
    assert result.http_status_code == 429
    assert result.retry_after_seconds == 5.0
    assert result.send_attempt_count == 1


def test_429_retry_after_huge_value_is_capped():
    opener = Stage28_4FakeHttpOpener(
        configured_status_code=429,
        configured_retry_after_header="999999",
    )
    t = Stage28_4AuditedHttpTransport(opener=opener)
    result = t.send_one_audited_post(
        webhook_url=_VALID_DISCORD_WEBHOOK_URL,
        webhook_identity=WEBHOOK_IDENTITY_PRIVATE_OPERATOR,
        payload=_safe_payload(),
    )
    assert result.retry_after_seconds == RETRY_AFTER_MAX_SECONDS


@pytest.mark.parametrize(
    "bad_header",
    [None, "", "  ", "abc", "-1", "nan", "inf", "-inf"],
)
def test_429_unparseable_retry_after_falls_back_to_none(bad_header):
    opener = Stage28_4FakeHttpOpener(
        configured_status_code=429,
        configured_retry_after_header=bad_header,
    )
    t = Stage28_4AuditedHttpTransport(opener=opener)
    result = t.send_one_audited_post(
        webhook_url=_VALID_DISCORD_WEBHOOK_URL,
        webhook_identity=WEBHOOK_IDENTITY_PRIVATE_OPERATOR,
        payload=_safe_payload(),
    )
    assert result.transport_status == TRANSPORT_STATUS_RATE_LIMITED
    assert result.retry_after_seconds is None


@pytest.mark.parametrize("server_status", [500, 502, 503, 504, 599])
def test_5xx_maps_to_server_error(server_status):
    opener = Stage28_4FakeHttpOpener(
        configured_status_code=server_status
    )
    t = Stage28_4AuditedHttpTransport(opener=opener)
    result = t.send_one_audited_post(
        webhook_url=_VALID_DISCORD_WEBHOOK_URL,
        webhook_identity=WEBHOOK_IDENTITY_PRIVATE_OPERATOR,
        payload=_safe_payload(),
    )
    assert result.transport_status == TRANSPORT_STATUS_SERVER_ERROR
    assert result.ok is False
    assert result.http_status_code == server_status
    assert result.send_attempt_count == 1
    assert result.retry_after_seconds is None


@pytest.mark.parametrize("auth_status", [401, 403, 404])
def test_auth_refused_maps_to_auth_or_webhook_refused(auth_status):
    opener = Stage28_4FakeHttpOpener(
        configured_status_code=auth_status
    )
    t = Stage28_4AuditedHttpTransport(opener=opener)
    result = t.send_one_audited_post(
        webhook_url=_VALID_DISCORD_WEBHOOK_URL,
        webhook_identity=WEBHOOK_IDENTITY_PRIVATE_OPERATOR,
        payload=_safe_payload(),
    )
    assert (
        result.transport_status
        == TRANSPORT_STATUS_AUTH_OR_WEBHOOK_REFUSED
    )
    assert result.http_status_code == auth_status
    assert result.send_attempt_count == 1


@pytest.mark.parametrize("other_4xx", [400, 405, 410, 415, 422])
def test_other_4xx_also_maps_to_auth_or_webhook_refused(other_4xx):
    opener = Stage28_4FakeHttpOpener(
        configured_status_code=other_4xx
    )
    t = Stage28_4AuditedHttpTransport(opener=opener)
    result = t.send_one_audited_post(
        webhook_url=_VALID_DISCORD_WEBHOOK_URL,
        webhook_identity=WEBHOOK_IDENTITY_PRIVATE_OPERATOR,
        payload=_safe_payload(),
    )
    assert (
        result.transport_status
        == TRANSPORT_STATUS_AUTH_OR_WEBHOOK_REFUSED
    )
    assert result.send_attempt_count == 1


def test_network_error_signal_maps_to_network_error():
    opener = Stage28_4FakeHttpOpener(
        raise_network_error_kind="DNS_RESOLUTION_FAILED"
    )
    t = Stage28_4AuditedHttpTransport(opener=opener)
    result = t.send_one_audited_post(
        webhook_url=_VALID_DISCORD_WEBHOOK_URL,
        webhook_identity=WEBHOOK_IDENTITY_PRIVATE_OPERATOR,
        payload=_safe_payload(),
    )
    assert result.transport_status == TRANSPORT_STATUS_NETWORK_ERROR
    assert result.ok is False
    assert result.http_status_code is None
    assert result.send_attempt_count == 1


def test_malformed_opener_response_is_treated_as_network_error():
    class _MalformedOpener:
        def open(self, request):
            return "not a Stage28_4HttpResponse"

    t = Stage28_4AuditedHttpTransport(opener=_MalformedOpener())
    result = t.send_one_audited_post(
        webhook_url=_VALID_DISCORD_WEBHOOK_URL,
        webhook_identity=WEBHOOK_IDENTITY_PRIVATE_OPERATOR,
        payload=_safe_payload(),
    )
    assert result.transport_status == TRANSPORT_STATUS_NETWORK_ERROR
    assert result.send_attempt_count == 1


# ---------------------------------------------------------------------------
# Exactly-one-send semantics + no retry / no sleep / no loop
# ---------------------------------------------------------------------------


def test_send_attempts_at_most_one_call_per_invocation_on_2xx():
    opener = Stage28_4FakeHttpOpener(configured_status_code=204)
    t = Stage28_4AuditedHttpTransport(opener=opener)
    t.send_one_audited_post(
        webhook_url=_VALID_DISCORD_WEBHOOK_URL,
        webhook_identity=WEBHOOK_IDENTITY_PRIVATE_OPERATOR,
        payload=_safe_payload(),
    )
    assert opener.call_count == 1


def test_send_attempts_at_most_one_call_per_invocation_on_429():
    opener = Stage28_4FakeHttpOpener(
        configured_status_code=429,
        configured_retry_after_header="2",
    )
    t = Stage28_4AuditedHttpTransport(opener=opener)
    t.send_one_audited_post(
        webhook_url=_VALID_DISCORD_WEBHOOK_URL,
        webhook_identity=WEBHOOK_IDENTITY_PRIVATE_OPERATOR,
        payload=_safe_payload(),
    )
    assert opener.call_count == 1


@pytest.mark.parametrize("status_code", [500, 502, 503, 401, 403, 404, 422])
def test_send_attempts_at_most_one_call_per_invocation_on_error_paths(status_code):
    opener = Stage28_4FakeHttpOpener(
        configured_status_code=status_code
    )
    t = Stage28_4AuditedHttpTransport(opener=opener)
    t.send_one_audited_post(
        webhook_url=_VALID_DISCORD_WEBHOOK_URL,
        webhook_identity=WEBHOOK_IDENTITY_PRIVATE_OPERATOR,
        payload=_safe_payload(),
    )
    assert opener.call_count == 1


def test_send_attempts_at_most_one_call_per_invocation_on_network_error():
    opener = Stage28_4FakeHttpOpener(
        raise_network_error_kind="CONNECTION_REFUSED"
    )
    t = Stage28_4AuditedHttpTransport(opener=opener)
    t.send_one_audited_post(
        webhook_url=_VALID_DISCORD_WEBHOOK_URL,
        webhook_identity=WEBHOOK_IDENTITY_PRIVATE_OPERATOR,
        payload=_safe_payload(),
    )
    assert opener.call_count == 1


def test_send_does_not_call_opener_on_validation_failure():
    opener = Stage28_4FakeHttpOpener()
    t = Stage28_4AuditedHttpTransport(opener=opener)
    t.send_one_audited_post(
        webhook_url="not a url",
        webhook_identity=WEBHOOK_IDENTITY_PRIVATE_OPERATOR,
        payload=_safe_payload(),
    )
    assert opener.call_count == 0


def test_multiple_independent_calls_each_emit_exactly_one_post():
    opener = Stage28_4FakeHttpOpener(configured_status_code=204)
    t = Stage28_4AuditedHttpTransport(opener=opener)
    for _ in range(3):
        t.send_one_audited_post(
            webhook_url=_VALID_DISCORD_WEBHOOK_URL,
            webhook_identity=WEBHOOK_IDENTITY_PRIVATE_OPERATOR,
            payload=_safe_payload(),
        )
    assert opener.call_count == 3


# ---------------------------------------------------------------------------
# Request shape: minimal headers, no caller-supplied secret headers
# ---------------------------------------------------------------------------


def test_request_carries_minimal_closed_set_headers():
    opener = Stage28_4FakeHttpOpener(configured_status_code=204)
    t = Stage28_4AuditedHttpTransport(opener=opener)
    t.send_one_audited_post(
        webhook_url=_VALID_DISCORD_WEBHOOK_URL,
        webhook_identity=WEBHOOK_IDENTITY_PRIVATE_OPERATOR,
        payload=_safe_payload(),
    )
    call = opener.calls[0]
    header_names = {name for name, _ in call.headers}
    assert header_names == {
        "Content-Type",
        "User-Agent",
        "Accept",
    }
    header_map = dict(call.headers)
    assert header_map["Content-Type"] == "application/json"


def test_request_uses_post_method():
    opener = Stage28_4FakeHttpOpener(configured_status_code=204)
    t = Stage28_4AuditedHttpTransport(opener=opener)
    t.send_one_audited_post(
        webhook_url=_VALID_DISCORD_WEBHOOK_URL,
        webhook_identity=WEBHOOK_IDENTITY_PRIVATE_OPERATOR,
        payload=_safe_payload(),
    )
    call = opener.calls[0]
    assert call.method == "POST"


def test_request_uses_validated_webhook_url():
    opener = Stage28_4FakeHttpOpener(configured_status_code=204)
    t = Stage28_4AuditedHttpTransport(opener=opener)
    t.send_one_audited_post(
        webhook_url=_VALID_DISCORD_WEBHOOK_URL,
        webhook_identity=WEBHOOK_IDENTITY_PRIVATE_OPERATOR,
        payload=_safe_payload(),
    )
    call = opener.calls[0]
    assert call.url == _VALID_DISCORD_WEBHOOK_URL


def test_request_body_is_utf8_json_bytes():
    opener = Stage28_4FakeHttpOpener(configured_status_code=204)
    t = Stage28_4AuditedHttpTransport(opener=opener)
    t.send_one_audited_post(
        webhook_url=_VALID_DISCORD_WEBHOOK_URL,
        webhook_identity=WEBHOOK_IDENTITY_PRIVATE_OPERATOR,
        payload={"content": "hello"},
    )
    call = opener.calls[0]
    assert isinstance(call.body_bytes, bytes)
    assert call.body_bytes.decode("utf-8") == '{"content":"hello"}'


# ---------------------------------------------------------------------------
# Redaction: result / repr / str do not leak canary inputs
# ---------------------------------------------------------------------------


def _assert_no_canary(text: str) -> None:
    for needle in (
        _CANARY_DISCORD_WEBHOOK_URL,
        _CANARY_TOKEN_SUFFIX,
        _CANARY_API_KEY,
        _CANARY_BEARER_TOKEN,
        _CANARY_RAW_RESPONSE_BODY,
        _CANARY_RAW_EXCEPTION,
    ):
        assert needle not in text, (
            f"Stage 28.4 surface leaked canary {needle!r}"
        )


def test_result_repr_does_not_leak_canary_url_or_token():
    opener = Stage28_4FakeHttpOpener(configured_status_code=204)
    t = Stage28_4AuditedHttpTransport(opener=opener)
    result = t.send_one_audited_post(
        webhook_url=_CANARY_DISCORD_WEBHOOK_URL,
        webhook_identity=WEBHOOK_IDENTITY_PRIVATE_OPERATOR,
        payload=_safe_payload(),
    )
    _assert_no_canary(repr(result))
    _assert_no_canary(str(result))


def test_result_asdict_does_not_leak_canary_url():
    opener = Stage28_4FakeHttpOpener(configured_status_code=204)
    t = Stage28_4AuditedHttpTransport(opener=opener)
    result = t.send_one_audited_post(
        webhook_url=_CANARY_DISCORD_WEBHOOK_URL,
        webhook_identity=WEBHOOK_IDENTITY_PRIVATE_OPERATOR,
        payload=_safe_payload(),
    )
    for value in dict(result._asdict()).values():
        _assert_no_canary(repr(value))


def test_validation_failed_result_does_not_leak_canary_url():
    opener = Stage28_4FakeHttpOpener()
    t = Stage28_4AuditedHttpTransport(opener=opener)
    bad_url = _CANARY_DISCORD_WEBHOOK_URL + "?evil"
    result = t.send_one_audited_post(
        webhook_url=bad_url,
        webhook_identity=WEBHOOK_IDENTITY_PRIVATE_OPERATOR,
        payload=_safe_payload(),
    )
    _assert_no_canary(repr(result))


def test_network_error_path_does_not_leak_canary_exception_text():
    class _CanaryRaisingOpener:
        def open(self, request):
            # The opener may carry a canary in its OWN exception
            # message; the transport must catch it and emit a
            # redaction-safe NETWORK_ERROR result without echoing
            # the message.
            raise Stage28_4NetworkErrorSignal(
                kind=_CANARY_RAW_EXCEPTION
            )

    t = Stage28_4AuditedHttpTransport(opener=_CanaryRaisingOpener())
    result = t.send_one_audited_post(
        webhook_url=_CANARY_DISCORD_WEBHOOK_URL,
        webhook_identity=WEBHOOK_IDENTITY_PRIVATE_OPERATOR,
        payload=_safe_payload(),
    )
    assert result.transport_status == TRANSPORT_STATUS_NETWORK_ERROR
    _assert_no_canary(repr(result))


def test_validation_error_message_does_not_leak_canary_url():
    # Construct the validation error explicitly with a synthetic
    # field/reason; the message must not echo any canary value.
    exc = Stage28_4TransportValidationError(
        field_name="webhook_url",
        reason="URL_NOT_PRIVATE_DISCORD_WEBHOOK",
    )
    _assert_no_canary(repr(exc))
    _assert_no_canary(str(exc))


# ---------------------------------------------------------------------------
# Result invariants
# ---------------------------------------------------------------------------


def test_all_results_carry_redacted_status_on_happy_path():
    opener = Stage28_4FakeHttpOpener(configured_status_code=204)
    t = Stage28_4AuditedHttpTransport(opener=opener)
    result = t.send_one_audited_post(
        webhook_url=_VALID_DISCORD_WEBHOOK_URL,
        webhook_identity=WEBHOOK_IDENTITY_PRIVATE_OPERATOR,
        payload=_safe_payload(),
    )
    assert result.redaction_status == REDACTION_STATUS_REDACTED


def test_all_results_carry_dropped_unrecorded_response_body_status():
    for status in (204, 429, 500, 401):
        opener = Stage28_4FakeHttpOpener(
            configured_status_code=status
        )
        t = Stage28_4AuditedHttpTransport(opener=opener)
        result = t.send_one_audited_post(
            webhook_url=_VALID_DISCORD_WEBHOOK_URL,
            webhook_identity=WEBHOOK_IDENTITY_PRIVATE_OPERATOR,
            payload=_safe_payload(),
        )
        assert (
            result.response_body_status
            == RESPONSE_BODY_STATUS_DROPPED_UNRECORDED
        )


def test_all_results_carry_schema_version_locked():
    opener = Stage28_4FakeHttpOpener(configured_status_code=204)
    t = Stage28_4AuditedHttpTransport(opener=opener)
    result = t.send_one_audited_post(
        webhook_url=_VALID_DISCORD_WEBHOOK_URL,
        webhook_identity=WEBHOOK_IDENTITY_PRIVATE_OPERATOR,
        payload=_safe_payload(),
    )
    assert result.schema_version == STAGE28_4_SCHEMA_VERSION


def test_send_attempt_count_only_zero_or_one_for_every_branch():
    cases = [
        (204, None, False),
        (429, "1", False),
        (500, None, False),
        (401, None, False),
        (422, None, False),
    ]
    for status_code, retry_after, _ in cases:
        opener = Stage28_4FakeHttpOpener(
            configured_status_code=status_code,
            configured_retry_after_header=retry_after,
        )
        t = Stage28_4AuditedHttpTransport(opener=opener)
        result = t.send_one_audited_post(
            webhook_url=_VALID_DISCORD_WEBHOOK_URL,
            webhook_identity=WEBHOOK_IDENTITY_PRIVATE_OPERATOR,
            payload=_safe_payload(),
        )
        assert result.send_attempt_count in (0, 1)


# ---------------------------------------------------------------------------
# Stage 27.7b structural-compatibility documentation contract
# ---------------------------------------------------------------------------


def test_transport_exposes_send_one_audited_post_with_keyword_only_args():
    sig = inspect.signature(
        Stage28_4AuditedHttpTransport.send_one_audited_post
    )
    params = list(sig.parameters.values())
    # First parameter is ``self``.
    assert params[0].name == "self"
    keyword_only_names = {
        p.name
        for p in params[1:]
        if p.kind == inspect.Parameter.KEYWORD_ONLY
    }
    assert {
        "webhook_url",
        "webhook_identity",
        "payload",
    }.issubset(keyword_only_names)


def test_transport_send_method_shape_matches_stage_27_7b_protocol():
    """Stage 28.4 transport's send method must take a ``webhook_url``
    string and return a transport result with at least the locked
    closed-set field names (``ok`` / ``http_status_code``). This
    test pins the documented structural-compatibility contract.

    Stage 28.4 deliberately does NOT import Stage 27 production
    code; the runtime structural-compatibility check exists so a
    future Stage 28 substage can wrap a
    ``Stage28_4AuditedHttpTransport`` in an adapter that satisfies
    the Stage 27.7b transport protocol.
    """
    opener = Stage28_4FakeHttpOpener(configured_status_code=204)
    t = Stage28_4AuditedHttpTransport(opener=opener)
    result = t.send_one_audited_post(
        webhook_url=_VALID_DISCORD_WEBHOOK_URL,
        webhook_identity=WEBHOOK_IDENTITY_PRIVATE_OPERATOR,
        payload=_safe_payload(),
    )
    # The Stage 27.7b transport result shape is
    # ``(status_code, ok, transport_error_kind)``. The Stage 28.4
    # result carries equivalents under closer names:
    # ``http_status_code`` + ``ok`` + ``transport_status``.
    field_names = set(result._fields)
    assert "ok" in field_names
    assert "http_status_code" in field_names
    assert "transport_status" in field_names


# ---------------------------------------------------------------------------
# Urllib opener wiring: defensive shape pin only (no live HTTP)
# ---------------------------------------------------------------------------


def test_urllib_opener_is_constructible_without_ssl_context_arg():
    opener = Stage28_4UrllibHttpOpener()
    assert isinstance(opener, Stage28_4UrllibHttpOpener)


def test_urllib_opener_open_method_exists_and_accepts_request_object():
    """Defensive existence pin only; this test does NOT call the
    real urlopen (Stage 28.4 must never attempt a live HTTP send
    from the test suite). The transport tests above prove the
    request shape with the fake opener instead.
    """
    sig = inspect.signature(Stage28_4UrllibHttpOpener.open)
    param_names = list(sig.parameters.keys())
    assert param_names[0] == "self"
    assert param_names[1] == "request"


# ---------------------------------------------------------------------------
# No sleep / time.sleep / asyncio.sleep proven by side-effect free fake
# ---------------------------------------------------------------------------


def test_send_does_not_block_or_sleep_on_429():
    """Stage 28.4 never sleeps on 429; the fake opener returns
    immediately and the transport classifies + returns. If a sleep
    were added the test would slow down dramatically because the
    fake opener returns a Retry-After of 30 seconds.
    """
    opener = Stage28_4FakeHttpOpener(
        configured_status_code=429,
        configured_retry_after_header="30",
    )
    t = Stage28_4AuditedHttpTransport(opener=opener)
    result = t.send_one_audited_post(
        webhook_url=_VALID_DISCORD_WEBHOOK_URL,
        webhook_identity=WEBHOOK_IDENTITY_PRIVATE_OPERATOR,
        payload=_safe_payload(),
    )
    # If a real sleep was taken the test would be slower than the
    # pytest-internal timing; the assertion below is structural,
    # the proof is that the test does not hang.
    assert result.retry_after_seconds == 30.0
    assert opener.call_count == 1

from __future__ import annotations

import json
import socket
from urllib.parse import parse_qs

import pytest

from PHX2.delivery.telegram_composer import TELEGRAM_INTERNAL_MAX_CHARACTERS
from PHX2.delivery.telegram_config import TelegramConfig
from PHX2.delivery.telegram_transport import (
    AUTHENTICATION_FAILED,
    CHAT_NOT_FOUND,
    MALFORMED_RESPONSE,
    MESSAGE_REJECTED,
    MESSAGE_TOO_LONG,
    RATE_LIMITED,
    SENT_OK,
    TIMEOUT,
    TelegramTransport,
)


TOKEN = "123456:ABCDEFGHIJKLMNOPQRSTUVWXYZ_abcd"
CHAT = "-1001234567890"


def _config() -> TelegramConfig:
    return TelegramConfig(
        transport="telegram",
        telegram_enabled=True,
        bot_token=TOKEN,
        chat_id=CHAT,
    )


class FakeSocket:
    def __init__(self):
        self.timeout = None

    def settimeout(self, value):
        self.timeout = value


class FakeResponse:
    def __init__(self, status, payload):
        self.status = status
        self.payload = payload

    def read(self):
        if isinstance(self.payload, bytes):
            return self.payload
        return json.dumps(self.payload).encode("utf-8")


class FakeConnection:
    def __init__(self, response=None, *, connect_error=None):
        self.response = response
        self.connect_error = connect_error
        self.sock = FakeSocket()
        self.request_record = None
        self.closed = False

    def connect(self):
        if self.connect_error is not None:
            raise self.connect_error

    def request(self, method, path, *, body, headers):
        self.request_record = (method, path, body, headers)

    def getresponse(self):
        return self.response

    def close(self):
        self.closed = True


class ConnectionScript:
    def __init__(self, *connections):
        self.connections = list(connections)
        self.calls = []

    def __call__(self, host, timeout):
        self.calls.append((host, timeout))
        return self.connections.pop(0)


def _transport(script, **kwargs):
    return TelegramTransport(
        _config(),
        connection_factory=script,
        sleep_fn=kwargs.pop("sleep_fn", lambda _: None),
        utc_now_fn=lambda: "2026-07-16T12:00:00Z",
        **kwargs,
    )


def test_send_message_payload_html_preview_disable_and_success_message_id():
    connection = FakeConnection(FakeResponse(
        200, {"ok": True, "result": {"message_id": 714}}))
    script = ConnectionScript(connection)
    result = _transport(script, max_retries=0).send_html("<b>PHOENIX</b>")

    assert result.ok is True and result.transport_status == SENT_OK
    assert result.message_id == 714 and result.send_attempt_count == 1
    method, path, raw_body, headers = connection.request_record
    fields = parse_qs(raw_body.decode("utf-8"))
    assert method == "POST" and path == f"/bot{TOKEN}/sendMessage"
    assert fields == {
        "chat_id": [CHAT],
        "text": ["<b>PHOENIX</b>"],
        "parse_mode": ["HTML"],
        "link_preview_options": ['{"is_disabled":true}'],
    }
    assert headers["Content-Type"].startswith("application/x-www-form-urlencoded")
    assert connection.sock.timeout == 10.0 and connection.closed is True
    assert result.evidence() == {
        "transport": "TELEGRAM",
        "message_id": 714,
        "destination_alias": "PHOENIX_CHANNEL",
        "attempted_at_utc": "2026-07-16T12:00:00Z",
        "delivered_at_utc": "2026-07-16T12:00:00Z",
        "result": SENT_OK,
        "retry_count": 0,
        "safe_error_category": None,
    }


@pytest.mark.parametrize(
    ("status", "payload", "expected"),
    (
        (200, {"ok": False, "error_code": 400, "description": "bad request"},
         MESSAGE_REJECTED),
        (401, {"ok": False, "error_code": 401}, AUTHENTICATION_FAILED),
        (400, {"ok": False, "error_code": 400, "description": "Bad Request: chat not found"},
         CHAT_NOT_FOUND),
    ),
)
def test_api_failures_are_classified_without_sent_ok(status, payload, expected):
    script = ConnectionScript(FakeConnection(FakeResponse(status, payload)))
    result = _transport(script, max_retries=0).send_html("Phoenix")
    assert result.ok is False and result.transport_status == expected
    assert result.message_id is None and result.delivered_at_utc is None


def test_rate_limit_retries_are_bounded_then_capture_success():
    sleeps = []
    script = ConnectionScript(
        FakeConnection(FakeResponse(429, {"ok": False, "error_code": 429})),
        FakeConnection(FakeResponse(429, {"ok": False, "error_code": 429})),
        FakeConnection(FakeResponse(200, {"ok": True, "result": {"message_id": 9}})),
    )
    result = _transport(
        script, max_retries=2, retry_delay_seconds=0.25,
        sleep_fn=sleeps.append,
    ).send_html("Phoenix")
    assert result.transport_status == SENT_OK and result.message_id == 9
    assert result.retry_count == 2 and result.send_attempt_count == 3
    assert sleeps == [0.25, 0.25] and len(script.calls) == 3


def test_rate_limit_stays_failure_after_bounded_retry():
    script = ConnectionScript(*(
        FakeConnection(FakeResponse(429, {"ok": False, "error_code": 429}))
        for _ in range(2)
    ))
    result = _transport(script, max_retries=1).send_html("Phoenix")
    assert result.transport_status == RATE_LIMITED and not result.ok
    assert result.send_attempt_count == 2 and result.retry_count == 1


def test_network_timeout_and_malformed_response_fail_closed():
    timeout = _transport(
        ConnectionScript(FakeConnection(connect_error=socket.timeout())),
        max_retries=0,
    ).send_html("Phoenix")
    malformed = _transport(
        ConnectionScript(FakeConnection(FakeResponse(200, b"not-json"))),
        max_retries=0,
    ).send_html("Phoenix")
    assert timeout.transport_status == TIMEOUT and not timeout.ok
    assert malformed.transport_status == MALFORMED_RESPONSE and not malformed.ok


def test_length_fails_before_request_and_no_secret_enters_evidence_or_repr():
    script = ConnectionScript()
    transport = _transport(script, max_retries=0)
    result = transport.send_html("x" * (TELEGRAM_INTERNAL_MAX_CHARACTERS + 1))
    assert result.transport_status == MESSAGE_TOO_LONG
    assert result.send_attempt_count == 0 and script.calls == []
    safe_output = repr(result) + repr(result.evidence()) + repr(transport)
    assert TOKEN not in safe_output and CHAT not in safe_output

"""Stage 29.2 HTTP transport pin tests.

Pins:
  * the HTTP transport ``Protocol`` shape,
  * the ``Stage29_2BirdeyeHttpResult`` closed-set validator,
  * the urllib transport's URL build / header injection /
    status / timeout / JSON parsing branches by monkeypatching
    ``urlopen``.
"""

from __future__ import annotations

import io
from contextlib import contextmanager
from typing import Mapping

import pytest

from PHX2.stage29 import (
    stage29_2_birdeye_http_transport as T,
)
from PHX2.stage29.birdeye_constants import (
    BIRDEYE_PATH_OHLCV,
    BIRDEYE_PATH_PRICE,
)
from PHX2.stage29.stage29_2_birdeye_models import (
    BIRDEYE_REFUSAL_REASON_BODY_MALFORMED,
    BIRDEYE_REFUSAL_REASON_HTTP_FAILED,
    BIRDEYE_REFUSAL_REASON_HTTP_STATUS_REJECTED,
    BIRDEYE_REFUSAL_REASON_HTTP_SUCCESS_FALSE,
    BIRDEYE_REFUSAL_REASON_HTTP_TIMEOUT,
    BIRDEYE_REFUSAL_REASON_NONE,
    Stage29_2BirdeyeError,
)
from PHX2.stage29.stage29_2_birdeye_readiness import (
    Stage29_2BirdeyeEndpointSecret,
)


GOOD_KEY = "abcd1234efgh5678ijkl9012mnop3456"
GOOD_URL = "https://aaaa-bbbb.example"


def _secret():
    return Stage29_2BirdeyeEndpointSecret(
        _api_key=GOOD_KEY,
        _base_url=GOOD_URL,
    )


# ---------------------------------------------------------------------------
# Stage29_2BirdeyeHttpResult validator
# ---------------------------------------------------------------------------


def test_http_result_rejects_unknown_refusal():
    with pytest.raises(Stage29_2BirdeyeError):
        T.Stage29_2BirdeyeHttpResult(
            refusal_reason="unknown",
            http_status_code=200,
            body={},
            fetched_at_utc="2026-05-25T00:00:00+00:00",
        )


def test_http_result_rejects_negative_status_code():
    with pytest.raises(Stage29_2BirdeyeError):
        T.Stage29_2BirdeyeHttpResult(
            refusal_reason=BIRDEYE_REFUSAL_REASON_NONE,
            http_status_code=-1,
            body={},
            fetched_at_utc="2026-05-25T00:00:00+00:00",
        )


def test_http_result_rejects_non_dict_body():
    with pytest.raises(Stage29_2BirdeyeError):
        T.Stage29_2BirdeyeHttpResult(
            refusal_reason=BIRDEYE_REFUSAL_REASON_NONE,
            http_status_code=200,
            body=[1, 2, 3],  # type: ignore[arg-type]
            fetched_at_utc="2026-05-25T00:00:00+00:00",
        )


def test_http_result_rejects_bool_status_code():
    with pytest.raises(Stage29_2BirdeyeError):
        T.Stage29_2BirdeyeHttpResult(
            refusal_reason=BIRDEYE_REFUSAL_REASON_NONE,
            http_status_code=True,  # bool subclasses int
            body={},
            fetched_at_utc="2026-05-25T00:00:00+00:00",
        )


# ---------------------------------------------------------------------------
# Stage29_2BirdeyeUrlibTransport — monkeypatched branches
# ---------------------------------------------------------------------------


@contextmanager
def _patched_urlopen(monkeypatch, fake_urlopen):
    monkeypatch.setattr(T, "urlopen", fake_urlopen)
    try:
        yield
    finally:
        pass


def _fake_response(status: int, body_bytes: bytes):
    class _Resp:
        def __init__(self, status_code, body):
            self.status = status_code
            self._body = body

        def read(self):
            return self._body

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    return _Resp(status, body_bytes)


def test_urlopen_200_with_value_returns_none_refusal(monkeypatch):
    captured: dict[str, object] = {}

    def fake_urlopen(req, timeout=None):
        captured["url"] = req.full_url
        captured["method"] = req.get_method()
        # Capture headers without raising
        for name in (
            "X-Api-Key", "X-Api-Key".lower(),
            "X-api-key",
            "x-chain",
            "Accept",
            "User-agent",
        ):
            try:
                captured[name] = req.get_header(name)
            except Exception:
                pass
        return _fake_response(
            200, b'{"success": true, "data": {"value": 0.5}}'
        )

    with _patched_urlopen(monkeypatch, fake_urlopen):
        transport = T.Stage29_2BirdeyeUrlibTransport()
        result = transport.get(
            endpoint_secret=_secret(),
            path=BIRDEYE_PATH_PRICE,
            query_params={"address": "abc"},
            timeout_seconds=10,
        )
    assert result.refusal_reason == BIRDEYE_REFUSAL_REASON_NONE
    assert result.http_status_code == 200
    assert result.body == {"success": True, "data": {"value": 0.5}}
    # URL built against the operator-supplied base URL
    assert captured["url"].startswith(
        GOOD_URL + BIRDEYE_PATH_PRICE + "?"
    )
    assert "address=abc" in captured["url"]
    # Method is GET only
    assert captured["method"] == "GET"


def test_urlopen_200_success_false_maps_to_refusal(monkeypatch):
    def fake_urlopen(req, timeout=None):
        return _fake_response(
            200, b'{"success": false, "data": null}'
        )

    with _patched_urlopen(monkeypatch, fake_urlopen):
        transport = T.Stage29_2BirdeyeUrlibTransport()
        result = transport.get(
            endpoint_secret=_secret(),
            path=BIRDEYE_PATH_PRICE,
            query_params={"address": "abc"},
            timeout_seconds=10,
        )
    assert result.refusal_reason == (
        BIRDEYE_REFUSAL_REASON_HTTP_SUCCESS_FALSE
    )
    assert result.http_status_code == 200


def test_urlopen_4xx_maps_to_status_rejected(monkeypatch):
    def fake_urlopen(req, timeout=None):
        from urllib.error import HTTPError
        raise HTTPError(
            req.full_url, 429, "Too Many Requests", {}, None
        )

    with _patched_urlopen(monkeypatch, fake_urlopen):
        transport = T.Stage29_2BirdeyeUrlibTransport()
        result = transport.get(
            endpoint_secret=_secret(),
            path=BIRDEYE_PATH_PRICE,
            query_params={"address": "abc"},
            timeout_seconds=10,
        )
    assert result.refusal_reason == (
        BIRDEYE_REFUSAL_REASON_HTTP_STATUS_REJECTED
    )
    assert result.http_status_code == 429


def test_urlopen_timeout_maps_to_http_timeout(monkeypatch):
    def fake_urlopen(req, timeout=None):
        raise TimeoutError("read timed out")

    with _patched_urlopen(monkeypatch, fake_urlopen):
        transport = T.Stage29_2BirdeyeUrlibTransport()
        result = transport.get(
            endpoint_secret=_secret(),
            path=BIRDEYE_PATH_PRICE,
            query_params={"address": "abc"},
            timeout_seconds=5,
        )
    assert result.refusal_reason == (
        BIRDEYE_REFUSAL_REASON_HTTP_TIMEOUT
    )


def test_urlopen_url_error_maps_to_http_failed(monkeypatch):
    def fake_urlopen(req, timeout=None):
        from urllib.error import URLError
        raise URLError("dns failure")

    with _patched_urlopen(monkeypatch, fake_urlopen):
        transport = T.Stage29_2BirdeyeUrlibTransport()
        result = transport.get(
            endpoint_secret=_secret(),
            path=BIRDEYE_PATH_PRICE,
            query_params={"address": "abc"},
            timeout_seconds=10,
        )
    assert result.refusal_reason == (
        BIRDEYE_REFUSAL_REASON_HTTP_FAILED
    )


def test_urlopen_url_error_timed_out_string_maps_to_timeout(
    monkeypatch,
):
    def fake_urlopen(req, timeout=None):
        from urllib.error import URLError
        raise URLError("operation timed out")

    with _patched_urlopen(monkeypatch, fake_urlopen):
        transport = T.Stage29_2BirdeyeUrlibTransport()
        result = transport.get(
            endpoint_secret=_secret(),
            path=BIRDEYE_PATH_PRICE,
            query_params={"address": "abc"},
            timeout_seconds=10,
        )
    assert result.refusal_reason == (
        BIRDEYE_REFUSAL_REASON_HTTP_TIMEOUT
    )


def test_urlopen_malformed_json_maps_to_body_malformed(
    monkeypatch,
):
    def fake_urlopen(req, timeout=None):
        return _fake_response(200, b"<html>not json</html>")

    with _patched_urlopen(monkeypatch, fake_urlopen):
        transport = T.Stage29_2BirdeyeUrlibTransport()
        result = transport.get(
            endpoint_secret=_secret(),
            path=BIRDEYE_PATH_PRICE,
            query_params={"address": "abc"},
            timeout_seconds=10,
        )
    assert result.refusal_reason == (
        BIRDEYE_REFUSAL_REASON_BODY_MALFORMED
    )


def test_urlopen_non_dict_top_level_maps_to_body_malformed(
    monkeypatch,
):
    def fake_urlopen(req, timeout=None):
        return _fake_response(200, b'[1, 2, 3]')

    with _patched_urlopen(monkeypatch, fake_urlopen):
        transport = T.Stage29_2BirdeyeUrlibTransport()
        result = transport.get(
            endpoint_secret=_secret(),
            path=BIRDEYE_PATH_PRICE,
            query_params={"address": "abc"},
            timeout_seconds=10,
        )
    assert result.refusal_reason == (
        BIRDEYE_REFUSAL_REASON_BODY_MALFORMED
    )


def test_urlopen_500_with_valid_json_maps_to_status_rejected(
    monkeypatch,
):
    def fake_urlopen(req, timeout=None):
        return _fake_response(
            500, b'{"success": false}'
        )

    with _patched_urlopen(monkeypatch, fake_urlopen):
        transport = T.Stage29_2BirdeyeUrlibTransport()
        result = transport.get(
            endpoint_secret=_secret(),
            path=BIRDEYE_PATH_PRICE,
            query_params={"address": "abc"},
            timeout_seconds=10,
        )
    assert result.refusal_reason == (
        BIRDEYE_REFUSAL_REASON_HTTP_STATUS_REJECTED
    )
    assert result.http_status_code == 500


def test_transport_rejects_unsupported_path():
    transport = T.Stage29_2BirdeyeUrlibTransport()
    result = transport.get(
        endpoint_secret=_secret(),
        path="/defi/history_price",  # explicitly NOT allowed
        query_params={"address": "abc"},
        timeout_seconds=10,
    )
    assert result.refusal_reason == (
        BIRDEYE_REFUSAL_REASON_HTTP_FAILED
    )


def test_transport_rejects_unsafe_timeout():
    transport = T.Stage29_2BirdeyeUrlibTransport()
    result = transport.get(
        endpoint_secret=_secret(),
        path=BIRDEYE_PATH_PRICE,
        query_params={"address": "abc"},
        timeout_seconds=0,
    )
    assert result.refusal_reason == (
        BIRDEYE_REFUSAL_REASON_HTTP_FAILED
    )


def test_transport_headers_carry_x_chain_solana(monkeypatch):
    captured_headers: dict[str, object] = {}

    def fake_urlopen(req, timeout=None):
        # urllib lowercases header names internally
        captured_headers["x-chain"] = req.get_header("X-chain")
        captured_headers["X-Api-Key"] = req.get_header(
            "X-api-key"
        )
        captured_headers["Accept"] = req.get_header("Accept")
        return _fake_response(
            200, b'{"success": true, "data": {"value": 1}}'
        )

    with _patched_urlopen(monkeypatch, fake_urlopen):
        transport = T.Stage29_2BirdeyeUrlibTransport()
        transport.get(
            endpoint_secret=_secret(),
            path=BIRDEYE_PATH_PRICE,
            query_params={"address": "abc"},
            timeout_seconds=10,
        )
    assert captured_headers["x-chain"] == "solana"
    assert captured_headers["X-Api-Key"] == GOOD_KEY
    assert captured_headers["Accept"] == "application/json"


def test_transport_method_is_get_only(monkeypatch):
    captured: dict[str, object] = {}

    def fake_urlopen(req, timeout=None):
        captured["method"] = req.get_method()
        return _fake_response(
            200, b'{"success": true, "data": {"value": 1}}'
        )

    with _patched_urlopen(monkeypatch, fake_urlopen):
        transport = T.Stage29_2BirdeyeUrlibTransport()
        transport.get(
            endpoint_secret=_secret(),
            path=BIRDEYE_PATH_OHLCV,
            query_params={
                "address": "abc",
                "type": "15m",
                "time_from": "0",
                "time_to": "1000",
            },
            timeout_seconds=10,
        )
    assert captured["method"] == "GET"

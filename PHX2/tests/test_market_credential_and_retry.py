"""Blocker B regression: market credential classification, retry bounds,
mandatory startup gate, and failure observability.

The 2026-07-30 canary recorded ``http_calls_total=48 / http_errors=48 /
retries=32 / http_429=0``.  Every one was an HTTP 401, but it surfaced
downstream as ``PROVIDER_MALFORMED`` with ``http_status_class: null`` in the
artifacts, so nothing could explain it.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import pytest

from PHX2.free_tier_producer.market_credential_check import (
    MARKET_CREDENTIAL_PROBE_MINT,
    validate_market_credential,
)
from PHX2.free_tier_producer.paid_birdeye import PaidBirdeyeMarketTransport
from PHX2.models.market_credential import (
    MARKET_CREDENTIAL_INVALID,
    MARKET_CREDENTIAL_MISSING,
    MARKET_CREDENTIAL_SCHEMA_INVALID,
    MARKET_CREDENTIAL_UNAUTHORIZED,
    MARKET_CREDENTIAL_UNVERIFIED,
    MARKET_CREDENTIAL_VALID,
    classify_market_credential_status,
    is_fatal_market_credential_status,
    is_permanent_market_auth_status,
)
from PHX2.stage29.birdeye_constants import (
    BIRDEYE_PATH_PRICE, BIRDEYE_PATH_TOKEN_OVERVIEW,
)
from PHX2.stage29.stage29_2_birdeye_models import (
    BIRDEYE_REFUSAL_REASON_HTTP_STATUS_REJECTED,
    BIRDEYE_REFUSAL_REASON_NONE,
)

MINT = "7YttLkHDoNj9wyDur5U4DqA4AwT3N8X9psJf7GmZpump"


class _Result:
    def __init__(self, *, status: int, body: Optional[dict],
                 refusal: str) -> None:
        self.http_status_code = status
        self.body = body
        self.refusal_reason = refusal
        self.fetched_at_utc = "2026-07-30T19:00:00Z"


def _ok(body: dict) -> _Result:
    return _Result(status=200, body=body,
                   refusal=BIRDEYE_REFUSAL_REASON_NONE)


def _rejected(status: int) -> _Result:
    return _Result(status=status, body=None,
                   refusal=BIRDEYE_REFUSAL_REASON_HTTP_STATUS_REJECTED)


class _Secret:
    def __init__(self, key: str = "k" * 32) -> None:
        self._key = key

    def reveal_api_key(self) -> str:
        return self._key

    def reveal_base_url(self) -> str:
        return "https://market.invalid"


class _RecordingTransport:
    """Inner transport stub that records every call it receives."""

    def __init__(self, responses: Dict[str, Any]) -> None:
        self.responses = responses
        self.calls: List[str] = []

    def get(self, *, endpoint_secret, path, query_params, timeout_seconds):
        self.calls.append(path)
        value = self.responses.get(path, self.responses.get("*"))
        return value() if callable(value) else value


# --------------------------------------------------------------- classification

@pytest.mark.parametrize("status,expected", [
    (401, MARKET_CREDENTIAL_INVALID),
    (403, MARKET_CREDENTIAL_UNAUTHORIZED),
    (400, None), (404, None), (429, None), (500, None), (200, None),
])
def test_status_classification_is_exact(status, expected) -> None:
    assert classify_market_credential_status(status) == expected


def test_only_401_and_403_are_permanent() -> None:
    assert is_permanent_market_auth_status(401)
    assert is_permanent_market_auth_status(403)
    for status in (200, 400, 404, 429, 500, 503, None, "x"):
        assert not is_permanent_market_auth_status(status)


def test_fatal_statuses_refuse_startup() -> None:
    for status in (MARKET_CREDENTIAL_INVALID, MARKET_CREDENTIAL_UNAUTHORIZED,
                   MARKET_CREDENTIAL_MISSING, MARKET_CREDENTIAL_SCHEMA_INVALID):
        assert is_fatal_market_credential_status(status)
    # An inconclusive check is NOT a credential verdict and must not be fatal.
    assert not is_fatal_market_credential_status(MARKET_CREDENTIAL_UNVERIFIED)
    assert not is_fatal_market_credential_status(MARKET_CREDENTIAL_VALID)


# ------------------------------------------------------- mandatory startup gate

def test_valid_credential_passes_the_gate() -> None:
    tr = _RecordingTransport({"*": _ok({"success": True,
                                        "data": {"value": 1.23}})})
    v = validate_market_credential(transport=tr, endpoint_secret=_Secret())
    assert v["credential_status"] == MARKET_CREDENTIAL_VALID
    assert v["http_status_code"] == 200
    assert v["fatal"] is False
    assert v["attempts"] == 1
    assert tr.calls == [BIRDEYE_PATH_PRICE]


def test_401_is_invalid_credential_and_fatal() -> None:
    tr = _RecordingTransport({"*": _rejected(401)})
    v = validate_market_credential(transport=tr, endpoint_secret=_Secret())
    assert v["credential_status"] == MARKET_CREDENTIAL_INVALID
    assert v["http_status_code"] == 401
    assert v["fatal"] is True


def test_403_is_unauthorized_credential_and_fatal() -> None:
    tr = _RecordingTransport({"*": _rejected(403)})
    v = validate_market_credential(transport=tr, endpoint_secret=_Secret())
    assert v["credential_status"] == MARKET_CREDENTIAL_UNAUTHORIZED
    assert v["fatal"] is True


def test_missing_credential_is_fatal_without_any_request() -> None:
    tr = _RecordingTransport({"*": _ok({"success": True, "data": {"value": 1}})})
    v = validate_market_credential(transport=tr, endpoint_secret=_Secret(""))
    assert v["credential_status"] == MARKET_CREDENTIAL_MISSING
    assert v["fatal"] is True
    assert tr.calls == []


def test_gate_never_retries() -> None:
    tr = _RecordingTransport({"*": _rejected(401)})
    validate_market_credential(transport=tr, endpoint_secret=_Secret())
    assert len(tr.calls) == 1


@pytest.mark.parametrize("body", [
    None, {}, {"success": False}, {"success": True, "data": None},
    {"success": True, "data": {}},
])
def test_200_with_bad_schema_is_fatal(body) -> None:
    tr = _RecordingTransport({"*": _Result(
        status=200, body=body, refusal=BIRDEYE_REFUSAL_REASON_NONE)})
    v = validate_market_credential(transport=tr, endpoint_secret=_Secret())
    assert v["credential_status"] == MARKET_CREDENTIAL_SCHEMA_INVALID
    assert v["fatal"] is True


@pytest.mark.parametrize("status", [404, 429, 500, 503])
def test_non_credential_status_is_inconclusive_not_fatal(status) -> None:
    tr = _RecordingTransport({"*": _rejected(status)})
    v = validate_market_credential(transport=tr, endpoint_secret=_Secret())
    assert v["credential_status"] == MARKET_CREDENTIAL_UNVERIFIED
    assert v["fatal"] is False


def test_transport_exception_is_inconclusive() -> None:
    class _Boom:
        def get(self, **_kw):
            raise RuntimeError("connreset")

    v = validate_market_credential(transport=_Boom(), endpoint_secret=_Secret())
    assert v["credential_status"] == MARKET_CREDENTIAL_UNVERIFIED
    assert v["fatal"] is False


def test_verdict_carries_no_secret_material() -> None:
    tr = _RecordingTransport({"*": _rejected(401)})
    v = validate_market_credential(
        transport=tr, endpoint_secret=_Secret("SUPERSECRETKEYVALUE0123456789ab"))
    blob = repr(v)
    assert "SUPERSECRETKEYVALUE" not in blob
    assert "market.invalid" not in blob
    assert "://" not in blob
    assert v["probe_mint"] == MARKET_CREDENTIAL_PROBE_MINT


# --------------------------------------------------------------- retry bounding

def _transport(responses, **kw) -> PaidBirdeyeMarketTransport:
    return PaidBirdeyeMarketTransport(
        inner_transport=_RecordingTransport(responses),
        endpoint_secret=_Secret(),
        min_interval_seconds=0, cache_ttl_seconds=0,
        max_attempts=kw.pop("max_attempts", 4), **kw)


def test_permanent_401_is_not_retried() -> None:
    inner = _RecordingTransport({"*": _rejected(401)})
    tr = PaidBirdeyeMarketTransport(
        inner_transport=inner, endpoint_secret=_Secret(),
        min_interval_seconds=0, cache_ttl_seconds=0, max_attempts=4)
    tr.fetch_price_plane(MINT, timeout_seconds=5)
    stats = tr.stats()
    assert len(inner.calls) == 1, inner.calls
    assert stats["retries"] == 0
    assert stats["http_auth_failures"] == 1
    assert stats["auth_retries_skipped"] == 3
    assert stats["last_auth_status_class"] == MARKET_CREDENTIAL_INVALID


def test_permanent_403_is_not_retried() -> None:
    inner = _RecordingTransport({"*": _rejected(403)})
    tr = PaidBirdeyeMarketTransport(
        inner_transport=inner, endpoint_secret=_Secret(),
        min_interval_seconds=0, cache_ttl_seconds=0, max_attempts=4)
    tr.fetch_price_plane(MINT, timeout_seconds=5)
    assert len(inner.calls) == 1
    assert tr.stats()["last_auth_status_class"] == MARKET_CREDENTIAL_UNAUTHORIZED


def test_retryable_status_still_uses_bounded_backoff() -> None:
    inner = _RecordingTransport({"*": _rejected(500)})
    tr = PaidBirdeyeMarketTransport(
        inner_transport=inner, endpoint_secret=_Secret(),
        min_interval_seconds=0, cache_ttl_seconds=0, max_attempts=3)
    tr.fetch_price_plane(MINT, timeout_seconds=5)
    stats = tr.stats()
    assert len(inner.calls) == 3, inner.calls
    assert stats["retries"] == 2
    assert stats["http_auth_failures"] == 0
    assert stats["last_auth_status_class"] is None


# --------------------------------------------------------------- classification
# A credential failure must NEVER be reported as a malformed provider payload.

def test_401_downstream_reason_is_credential_not_malformed() -> None:
    inner = _RecordingTransport({"*": _rejected(401)})
    tr = PaidBirdeyeMarketTransport(
        inner_transport=inner, endpoint_secret=_Secret(),
        min_interval_seconds=0, cache_ttl_seconds=0, max_attempts=1)
    out = tr.fetch_price_plane(MINT, timeout_seconds=5)
    reason = out["_market_failure_reason"]
    assert reason == "PROVIDER_" + MARKET_CREDENTIAL_INVALID
    assert reason != "PROVIDER_MALFORMED"


def test_403_downstream_reason_is_credential_not_malformed() -> None:
    inner = _RecordingTransport({"*": _rejected(403)})
    tr = PaidBirdeyeMarketTransport(
        inner_transport=inner, endpoint_secret=_Secret(),
        min_interval_seconds=0, cache_ttl_seconds=0, max_attempts=1)
    out = tr.fetch_overview_plane(MINT, timeout_seconds=5)
    assert out["_market_failure_reason"] == (
        "PROVIDER_" + MARKET_CREDENTIAL_UNAUTHORIZED)


def test_400_remains_a_request_rejection_not_a_credential_verdict() -> None:
    inner = _RecordingTransport({"*": _rejected(400)})
    tr = PaidBirdeyeMarketTransport(
        inner_transport=inner, endpoint_secret=_Secret(),
        min_interval_seconds=0, cache_ttl_seconds=0, max_attempts=1)
    tr.fetch_price_plane(MINT, timeout_seconds=5)
    diag = tr.market_diagnostic(MINT)
    assert diag["market_reason_code"] == "PROVIDER_REQUEST_REJECTED"


def test_diagnostic_reason_distinguishes_401_from_403() -> None:
    for status, expected in ((401, MARKET_CREDENTIAL_INVALID),
                             (403, MARKET_CREDENTIAL_UNAUTHORIZED)):
        inner = _RecordingTransport({"*": _rejected(status)})
        tr = PaidBirdeyeMarketTransport(
            inner_transport=inner, endpoint_secret=_Secret(),
            min_interval_seconds=0, cache_ttl_seconds=0, max_attempts=1)
        tr.fetch_price_plane(MINT, timeout_seconds=5)
        diag = tr.market_diagnostic(MINT)
        assert diag["market_reason_code"] == "PROVIDER_" + expected


def test_429_is_still_rate_limit_and_5xx_still_5xx() -> None:
    for status, expected in ((429, "PROVIDER_RATE_LIMIT"),
                             (503, "PROVIDER_5XX")):
        inner = _RecordingTransport({"*": _rejected(status)})
        tr = PaidBirdeyeMarketTransport(
            inner_transport=inner, endpoint_secret=_Secret(),
            min_interval_seconds=0, cache_ttl_seconds=0, max_attempts=1)
        out = tr.fetch_price_plane(MINT, timeout_seconds=5)
        assert out["_market_failure_reason"] == expected


# ------------------------------------------------------- valid responses hydrate

def test_valid_responses_populate_price_mc_and_liquidity() -> None:
    inner = _RecordingTransport({
        BIRDEYE_PATH_PRICE: _ok({"success": True,
                                 "data": {"value": 0.000021,
                                          "updateUnixTime": 1785436800}}),
        BIRDEYE_PATH_TOKEN_OVERVIEW: _ok({
            "success": True,
            "data": {"mc": 21000.0, "liquidity": 8400.0}}),
    })
    # Pin the clock to the fixture's observation time so the freshness gate
    # (which correctly refuses stale prices) is not what is under test here.
    tr = PaidBirdeyeMarketTransport(
        inner_transport=inner, endpoint_secret=_Secret(),
        min_interval_seconds=0, cache_ttl_seconds=0, max_attempts=1,
        now_fn=lambda: 1785436800.0)
    price = tr.fetch_price_plane(MINT, timeout_seconds=5)
    assert price.get("_market_failure_reason") is None
    assert price["current_price"] is not None
    overview = tr.fetch_overview_plane(MINT, timeout_seconds=5)
    assert overview.get("_market_failure_reason") is None
    assert overview["current_market_cap_usd"] is not None
    assert overview["liquidity_usd"] is not None
    stats = tr.stats()
    assert stats["http_errors"] == 0
    assert stats["http_auth_failures"] == 0
    assert stats["last_auth_status_class"] is None

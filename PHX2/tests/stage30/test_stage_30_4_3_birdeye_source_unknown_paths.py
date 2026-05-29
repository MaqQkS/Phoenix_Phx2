"""Stage 30.4.3 Birdeye source: unknown / None-yielding read paths.

A fake Stage 29.2 transport returning a canned
``Stage29_2BirdeyeHttpResult`` drives the Stage 30.4.3 bridge. The
bridge's ``read`` MUST return ``None`` (the Stage 30.4.1 adapter
resolves ``None`` to Unknown / UNAVAILABLE) for every degraded
transport outcome:

  * transport refusal (``refusal_reason`` != ``NONE``),
  * missing body (``body is None``),
  * missing ``data`` key,
  * non-dict ``data``.

Fake transport only. No live call, no env, no secret reveal.
"""

from __future__ import annotations

from typing import Mapping

from PHX2.stage29.stage29_2_birdeye_http_transport import (
    Stage29_2BirdeyeHttpResult,
)
from PHX2.stage29.stage29_2_birdeye_models import (
    BIRDEYE_REFUSAL_REASON_BODY_MALFORMED,
    BIRDEYE_REFUSAL_REASON_HTTP_STATUS_REJECTED,
    BIRDEYE_REFUSAL_REASON_HTTP_TIMEOUT,
    BIRDEYE_REFUSAL_REASON_NONE,
)
from PHX2.stage29.stage29_2_birdeye_readiness import (
    Stage29_2BirdeyeEndpointSecret,
)
from PHX2.stage30.stage30_4_3_market_context_birdeye_source import (
    Stage30_4_3BirdeyeMarketContextSource,
)


_VALID_MINT: str = "So11111111111111111111111111111111111111112"
_OBSERVED_TS: str = "2026-05-28T11:59:30Z"


def _endpoint_secret() -> Stage29_2BirdeyeEndpointSecret:
    return Stage29_2BirdeyeEndpointSecret(
        _api_key="a" * 20,
        _base_url="https://host.example.fake",
    )


class _FakeTransport:
    """Fake Stage 29.2 transport. Returns a fixed canned result and
    records every call. No network, no env, no secret reveal.
    """

    def __init__(self, result: Stage29_2BirdeyeHttpResult) -> None:
        self._result = result
        self.calls: list = []

    def get(
        self,
        *,
        endpoint_secret: Stage29_2BirdeyeEndpointSecret,
        path: str,
        query_params: Mapping[str, str],
        timeout_seconds: int,
    ) -> Stage29_2BirdeyeHttpResult:
        self.calls.append(
            (path, dict(query_params), timeout_seconds)
        )
        return self._result


def _source(
    result: Stage29_2BirdeyeHttpResult,
) -> Stage30_4_3BirdeyeMarketContextSource:
    return Stage30_4_3BirdeyeMarketContextSource(
        transport=_FakeTransport(result),
        endpoint_secret=_endpoint_secret(),
        timeout_seconds=30,
    )


# ---------------------------------------------------------------------------
# Transport refusal -> None
# ---------------------------------------------------------------------------


def test_transport_timeout_refusal_returns_none() -> None:
    result = Stage29_2BirdeyeHttpResult(
        refusal_reason=BIRDEYE_REFUSAL_REASON_HTTP_TIMEOUT,
        http_status_code=0,
        body=None,
        fetched_at_utc=_OBSERVED_TS,
    )
    assert _source(result).read(_VALID_MINT) is None


def test_transport_status_rejected_refusal_returns_none() -> None:
    # Even with a body present, a non-NONE refusal short-circuits.
    result = Stage29_2BirdeyeHttpResult(
        refusal_reason=BIRDEYE_REFUSAL_REASON_HTTP_STATUS_REJECTED,
        http_status_code=429,
        body={"data": {"mc": 83000, "liquidity": 27000}},
        fetched_at_utc=_OBSERVED_TS,
    )
    assert _source(result).read(_VALID_MINT) is None


def test_transport_body_malformed_refusal_returns_none() -> None:
    result = Stage29_2BirdeyeHttpResult(
        refusal_reason=BIRDEYE_REFUSAL_REASON_BODY_MALFORMED,
        http_status_code=200,
        body=None,
        fetched_at_utc=_OBSERVED_TS,
    )
    assert _source(result).read(_VALID_MINT) is None


# ---------------------------------------------------------------------------
# Missing body -> None
# ---------------------------------------------------------------------------


def test_missing_body_returns_none() -> None:
    # Defensive: refusal NONE paired with a None body. The transport
    # would not normally pair these, but the bridge guards anyway.
    result = Stage29_2BirdeyeHttpResult(
        refusal_reason=BIRDEYE_REFUSAL_REASON_NONE,
        http_status_code=200,
        body=None,
        fetched_at_utc=_OBSERVED_TS,
    )
    assert _source(result).read(_VALID_MINT) is None


# ---------------------------------------------------------------------------
# Missing / non-dict data -> None
# ---------------------------------------------------------------------------


def test_missing_data_key_returns_none() -> None:
    result = Stage29_2BirdeyeHttpResult(
        refusal_reason=BIRDEYE_REFUSAL_REASON_NONE,
        http_status_code=200,
        body={"success": True},
        fetched_at_utc=_OBSERVED_TS,
    )
    assert _source(result).read(_VALID_MINT) is None


def test_non_dict_data_returns_none() -> None:
    for bad_data in ([], "x", 123, 4.5, None, True):
        result = Stage29_2BirdeyeHttpResult(
            refusal_reason=BIRDEYE_REFUSAL_REASON_NONE,
            http_status_code=200,
            body={"data": bad_data},
            fetched_at_utc=_OBSERVED_TS,
        )
        assert _source(result).read(_VALID_MINT) is None, (
            f"data={bad_data!r} must yield a None reading"
        )


def test_empty_dict_data_yields_reading_with_unknowns() -> None:
    # An empty ``data`` dict is a valid (if empty) snapshot: the
    # bridge returns a reading with MC / LP both None (Unknown), not
    # a None reading.
    result = Stage29_2BirdeyeHttpResult(
        refusal_reason=BIRDEYE_REFUSAL_REASON_NONE,
        http_status_code=200,
        body={"data": {}},
        fetched_at_utc=_OBSERVED_TS,
    )
    reading = _source(result).read(_VALID_MINT)
    assert reading is not None
    assert reading.market_cap_usd_value is None
    assert reading.liquidity_usd_value is None

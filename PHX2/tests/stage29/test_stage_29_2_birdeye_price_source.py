"""Stage 29.2 Birdeye price source adapter pin tests.

Drives every branch (PRESENT / MISSING / SOURCE_ERROR) of the
``fetch_birdeye_price_snapshot`` helper + the Stage 27.4
``PriceContextSource`` Protocol implementation via a fake HTTP
transport. Confirms Stage 29.2 NEVER fabricates a price.
"""

from __future__ import annotations

from typing import Mapping

import pytest

from PHX2.stage27.price_ath_context_contracts import (
    Stage27PriceSourceError,
)
from PHX2.stage27.price_ath_context_reader import (
    PriceSourceSnapshot,
)
from PHX2.stage29.birdeye_constants import (
    BIRDEYE_PATH_PRICE,
    BIRDEYE_PRICE_SOURCE_LABEL,
    BIRDEYE_REPORTING_UNIT_USD,
)
from PHX2.stage29.stage29_2_birdeye_http_transport import (
    Stage29_2BirdeyeHttpResult,
    Stage29_2BirdeyeHttpTransport,
)
from PHX2.stage29.stage29_2_birdeye_models import (
    BIRDEYE_FRESHNESS_STATUS_FRESH,
    BIRDEYE_FRESHNESS_STATUS_UNKNOWN,
    BIRDEYE_PRICE_STATUS_MISSING,
    BIRDEYE_PRICE_STATUS_PRESENT,
    BIRDEYE_PRICE_STATUS_SOURCE_ERROR,
    BIRDEYE_REFUSAL_REASON_BODY_MALFORMED,
    BIRDEYE_REFUSAL_REASON_HTTP_STATUS_REJECTED,
    BIRDEYE_REFUSAL_REASON_HTTP_TIMEOUT,
    BIRDEYE_REFUSAL_REASON_NONE,
    Stage29_2BirdeyeError,
)
from PHX2.stage29.stage29_2_birdeye_price_source import (
    Stage29_2BirdeyePriceSource,
    fetch_birdeye_price_snapshot,
)
from PHX2.stage29.stage29_2_birdeye_readiness import (
    Stage29_2BirdeyeEndpointSecret,
)


GOOD_MINT = "So11111111111111111111111111111111111111112"
GOOD_KEY = "abcd1234efgh5678ijkl9012mnop3456"
GOOD_URL = "https://aaaa-bbbb.example"


def _secret():
    return Stage29_2BirdeyeEndpointSecret(
        _api_key=GOOD_KEY,
        _base_url=GOOD_URL,
    )


class FakeTransport(Stage29_2BirdeyeHttpTransport):
    def __init__(
        self, result: Stage29_2BirdeyeHttpResult
    ) -> None:
        self._result = result
        self.calls: list[dict] = []

    def get(
        self,
        *,
        endpoint_secret: Stage29_2BirdeyeEndpointSecret,
        path: str,
        query_params: Mapping[str, str],
        timeout_seconds: int,
    ) -> Stage29_2BirdeyeHttpResult:
        self.calls.append(
            {
                "path": path,
                "query_params": dict(query_params),
                "timeout_seconds": timeout_seconds,
            }
        )
        return self._result


def _ok_result(body: dict) -> Stage29_2BirdeyeHttpResult:
    return Stage29_2BirdeyeHttpResult(
        refusal_reason=BIRDEYE_REFUSAL_REASON_NONE,
        http_status_code=200,
        body=body,
        fetched_at_utc="2026-05-25T12:00:00+00:00",
    )


def _err_result(
    refusal: str, status_code: int = 0
) -> Stage29_2BirdeyeHttpResult:
    return Stage29_2BirdeyeHttpResult(
        refusal_reason=refusal,
        http_status_code=status_code,
        body=None,
        fetched_at_utc="2026-05-25T12:00:00+00:00",
    )


# ---------------------------------------------------------------------------
# fetch_birdeye_price_snapshot
# ---------------------------------------------------------------------------


def test_present_path():
    transport = FakeTransport(
        _ok_result(
            {
                "success": True,
                "data": {
                    "value": 0.5,
                    "updateUnixTime": 1716638400,
                },
            }
        )
    )
    snap = fetch_birdeye_price_snapshot(
        base_mint=GOOD_MINT,
        transport=transport,
        endpoint_secret=_secret(),
        timeout_seconds=10,
    )
    assert (
        snap.birdeye_price_status == BIRDEYE_PRICE_STATUS_PRESENT
    )
    assert snap.price_value == "0.5"
    assert snap.price_unit == BIRDEYE_REPORTING_UNIT_USD
    assert snap.source_label == BIRDEYE_PRICE_SOURCE_LABEL
    assert snap.fetched_at_utc == "2026-05-25T12:00:00+00:00"
    assert snap.upstream_update_unix_time == 1716638400
    assert (
        snap.birdeye_freshness_status
        == BIRDEYE_FRESHNESS_STATUS_FRESH
    )
    # Confirm transport called with expected path
    assert transport.calls[0]["path"] == BIRDEYE_PATH_PRICE
    assert transport.calls[0]["query_params"] == {
        "address": GOOD_MINT,
    }


def test_present_path_with_string_value():
    transport = FakeTransport(
        _ok_result(
            {
                "success": True,
                "data": {"value": "0.00012345"},
            }
        )
    )
    snap = fetch_birdeye_price_snapshot(
        base_mint=GOOD_MINT,
        transport=transport,
        endpoint_secret=_secret(),
        timeout_seconds=10,
    )
    assert snap.price_value == "0.00012345"


def test_present_path_with_int_value():
    transport = FakeTransport(
        _ok_result(
            {"success": True, "data": {"value": 5}}
        )
    )
    snap = fetch_birdeye_price_snapshot(
        base_mint=GOOD_MINT,
        transport=transport,
        endpoint_secret=_secret(),
        timeout_seconds=10,
    )
    assert snap.price_value == "5"


def test_missing_value_path_in_body():
    transport = FakeTransport(
        _ok_result({"success": True, "data": {}})
    )
    snap = fetch_birdeye_price_snapshot(
        base_mint=GOOD_MINT,
        transport=transport,
        endpoint_secret=_secret(),
        timeout_seconds=10,
    )
    assert (
        snap.birdeye_price_status == BIRDEYE_PRICE_STATUS_MISSING
    )
    assert snap.price_value is None  # no invention


def test_missing_value_path_value_is_null():
    transport = FakeTransport(
        _ok_result(
            {"success": True, "data": {"value": None}}
        )
    )
    snap = fetch_birdeye_price_snapshot(
        base_mint=GOOD_MINT,
        transport=transport,
        endpoint_secret=_secret(),
        timeout_seconds=10,
    )
    assert (
        snap.birdeye_price_status == BIRDEYE_PRICE_STATUS_MISSING
    )
    assert snap.price_value is None


def test_missing_value_path_bool_value_rejected():
    # JSON booleans must NEVER project to a numeric price.
    transport = FakeTransport(
        _ok_result(
            {"success": True, "data": {"value": True}}
        )
    )
    snap = fetch_birdeye_price_snapshot(
        base_mint=GOOD_MINT,
        transport=transport,
        endpoint_secret=_secret(),
        timeout_seconds=10,
    )
    assert (
        snap.birdeye_price_status == BIRDEYE_PRICE_STATUS_MISSING
    )
    assert snap.price_value is None


def test_missing_value_path_negative_value_rejected():
    transport = FakeTransport(
        _ok_result(
            {"success": True, "data": {"value": -1.0}}
        )
    )
    snap = fetch_birdeye_price_snapshot(
        base_mint=GOOD_MINT,
        transport=transport,
        endpoint_secret=_secret(),
        timeout_seconds=10,
    )
    assert (
        snap.birdeye_price_status == BIRDEYE_PRICE_STATUS_MISSING
    )
    assert snap.price_value is None


def test_missing_data_object():
    transport = FakeTransport(
        _ok_result({"success": True})
    )
    snap = fetch_birdeye_price_snapshot(
        base_mint=GOOD_MINT,
        transport=transport,
        endpoint_secret=_secret(),
        timeout_seconds=10,
    )
    assert (
        snap.birdeye_price_status == BIRDEYE_PRICE_STATUS_MISSING
    )
    assert snap.price_value is None


def test_source_error_on_http_status_rejected():
    transport = FakeTransport(
        _err_result(
            BIRDEYE_REFUSAL_REASON_HTTP_STATUS_REJECTED, 429
        )
    )
    snap = fetch_birdeye_price_snapshot(
        base_mint=GOOD_MINT,
        transport=transport,
        endpoint_secret=_secret(),
        timeout_seconds=10,
    )
    assert (
        snap.birdeye_price_status
        == BIRDEYE_PRICE_STATUS_SOURCE_ERROR
    )
    assert snap.price_value is None  # no invention


def test_source_error_on_http_timeout():
    transport = FakeTransport(
        _err_result(BIRDEYE_REFUSAL_REASON_HTTP_TIMEOUT)
    )
    snap = fetch_birdeye_price_snapshot(
        base_mint=GOOD_MINT,
        transport=transport,
        endpoint_secret=_secret(),
        timeout_seconds=10,
    )
    assert (
        snap.birdeye_price_status
        == BIRDEYE_PRICE_STATUS_SOURCE_ERROR
    )


def test_source_error_on_body_malformed():
    transport = FakeTransport(
        _err_result(BIRDEYE_REFUSAL_REASON_BODY_MALFORMED, 200)
    )
    snap = fetch_birdeye_price_snapshot(
        base_mint=GOOD_MINT,
        transport=transport,
        endpoint_secret=_secret(),
        timeout_seconds=10,
    )
    assert (
        snap.birdeye_price_status
        == BIRDEYE_PRICE_STATUS_SOURCE_ERROR
    )


def test_source_error_on_unsafe_mint():
    transport = FakeTransport(
        _ok_result(
            {"success": True, "data": {"value": 0.5}}
        )
    )
    snap = fetch_birdeye_price_snapshot(
        base_mint="short",
        transport=transport,
        endpoint_secret=_secret(),
        timeout_seconds=10,
    )
    assert (
        snap.birdeye_price_status
        == BIRDEYE_PRICE_STATUS_SOURCE_ERROR
    )
    # Transport must NOT have been called
    assert transport.calls == []


def test_source_error_on_unsafe_timeout():
    transport = FakeTransport(
        _ok_result(
            {"success": True, "data": {"value": 0.5}}
        )
    )
    snap = fetch_birdeye_price_snapshot(
        base_mint=GOOD_MINT,
        transport=transport,
        endpoint_secret=_secret(),
        timeout_seconds=0,
    )
    assert (
        snap.birdeye_price_status
        == BIRDEYE_PRICE_STATUS_SOURCE_ERROR
    )
    assert transport.calls == []


# ---------------------------------------------------------------------------
# Stage27.4 PriceContextSource Protocol behaviour
# ---------------------------------------------------------------------------


def test_protocol_returns_price_source_snapshot_on_present():
    transport = FakeTransport(
        _ok_result(
            {"success": True, "data": {"value": 0.5}}
        )
    )
    src = Stage29_2BirdeyePriceSource(
        transport=transport,
        endpoint_secret=_secret(),
        timeout_seconds=10,
    )
    snap = src.read_price_snapshot(
        GOOD_MINT, pair_quote_asset="SOL"
    )
    assert isinstance(snap, PriceSourceSnapshot)
    assert snap.price_value == "0.5"
    assert snap.price_unit == "USD"
    assert snap.source_label == "birdeye_defi_price"


def test_protocol_returns_snapshot_with_none_on_missing():
    transport = FakeTransport(
        _ok_result({"success": True, "data": {}})
    )
    src = Stage29_2BirdeyePriceSource(
        transport=transport,
        endpoint_secret=_secret(),
        timeout_seconds=10,
    )
    snap = src.read_price_snapshot(
        GOOD_MINT, pair_quote_asset="SOL"
    )
    assert isinstance(snap, PriceSourceSnapshot)
    assert snap.price_value is None
    # Stage 27.4 reader maps this to UNAVAILABLE / SOURCE_RETURNED_NONE


def test_protocol_raises_on_source_error():
    transport = FakeTransport(
        _err_result(
            BIRDEYE_REFUSAL_REASON_HTTP_STATUS_REJECTED, 429
        )
    )
    src = Stage29_2BirdeyePriceSource(
        transport=transport,
        endpoint_secret=_secret(),
        timeout_seconds=10,
    )
    with pytest.raises(Stage27PriceSourceError) as exc:
        src.read_price_snapshot(
            GOOD_MINT, pair_quote_asset="SOL"
        )
    assert exc.value.reason == "SOURCE_FAILED"
    # Raw response body / API key NEVER appear in the exception
    assert GOOD_KEY not in str(exc.value)
    assert GOOD_URL not in str(exc.value)


def test_protocol_rejects_invalid_secret_at_construct():
    with pytest.raises(Stage29_2BirdeyeError):
        Stage29_2BirdeyePriceSource(
            transport=FakeTransport(
                _ok_result({"success": True})
            ),
            endpoint_secret="not-a-secret",  # type: ignore[arg-type]
            timeout_seconds=10,
        )


def test_protocol_rejects_unsafe_timeout_at_construct():
    with pytest.raises(Stage29_2BirdeyeError):
        Stage29_2BirdeyePriceSource(
            transport=FakeTransport(
                _ok_result({"success": True})
            ),
            endpoint_secret=_secret(),
            timeout_seconds=0,
        )


# ---------------------------------------------------------------------------
# No-invention discipline: assert ALL refusal-bearing paths
# carry price_value=None.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "body,expected_status",
    [
        ({"success": True}, BIRDEYE_PRICE_STATUS_MISSING),
        ({"success": True, "data": None}, BIRDEYE_PRICE_STATUS_MISSING),
        (
            {"success": True, "data": {"value": None}},
            BIRDEYE_PRICE_STATUS_MISSING,
        ),
        (
            {"success": True, "data": {"value": ""}},
            BIRDEYE_PRICE_STATUS_MISSING,
        ),
        (
            {"success": True, "data": {"value": "notnumeric"}},
            BIRDEYE_PRICE_STATUS_MISSING,
        ),
    ],
)
def test_every_missing_branch_has_none_value(
    body, expected_status
):
    transport = FakeTransport(_ok_result(body))
    snap = fetch_birdeye_price_snapshot(
        base_mint=GOOD_MINT,
        transport=transport,
        endpoint_secret=_secret(),
        timeout_seconds=10,
    )
    assert snap.birdeye_price_status == expected_status
    assert snap.price_value is None

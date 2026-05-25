"""Stage 29.2 Birdeye ATH source adapter pin tests.

Drives every branch (PRESENT / MISSING / SOURCE_ERROR) of the
``fetch_birdeye_ath_snapshot`` helper + the Stage 27.4
``AthContextSource`` Protocol implementation. Confirms:

  * ATH is taken from ``max(items[].h)``,
  * ``ath_observed_at_utc`` is the unixTime of the candle with
    the max high,
  * ``window_starts_post_migration`` is True iff the caller
    supplies a migration timestamp that is <= time_from.
  * Stage 29.2 NEVER fabricates an ATH value.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Mapping

import pytest

from PHX2.stage27.price_ath_context_contracts import (
    Stage27AthSourceError,
)
from PHX2.stage27.price_ath_context_reader import (
    AthSourceSnapshot,
)
from PHX2.stage29.birdeye_constants import (
    BIRDEYE_OHLCV_SOURCE_LABEL,
    BIRDEYE_PATH_OHLCV,
    BIRDEYE_REPORTING_UNIT_USD,
)
from PHX2.stage29.stage29_2_birdeye_ath_source import (
    Stage29_2BirdeyeAthSource,
    fetch_birdeye_ath_snapshot,
)
from PHX2.stage29.stage29_2_birdeye_http_transport import (
    Stage29_2BirdeyeHttpResult,
    Stage29_2BirdeyeHttpTransport,
)
from PHX2.stage29.stage29_2_birdeye_models import (
    BIRDEYE_ATH_STATUS_MISSING,
    BIRDEYE_ATH_STATUS_PRESENT,
    BIRDEYE_ATH_STATUS_SOURCE_ERROR,
    BIRDEYE_FRESHNESS_STATUS_FRESH,
    BIRDEYE_REFUSAL_REASON_BODY_MALFORMED,
    BIRDEYE_REFUSAL_REASON_HTTP_STATUS_REJECTED,
    BIRDEYE_REFUSAL_REASON_HTTP_TIMEOUT,
    BIRDEYE_REFUSAL_REASON_NONE,
    Stage29_2BirdeyeError,
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


# Frozen now to keep tests deterministic across time_from/time_to.
FROZEN_NOW = datetime(2026, 5, 25, 12, 0, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# PRESENT path: max(items[].h)
# ---------------------------------------------------------------------------


def test_present_picks_max_high():
    body = {
        "success": True,
        "data": {
            "items": [
                {"h": 0.1, "unixTime": 1716000000},
                {"h": 0.8, "unixTime": 1716010000},  # max
                {"h": 0.3, "unixTime": 1716020000},
            ]
        },
    }
    transport = FakeTransport(_ok_result(body))
    snap = fetch_birdeye_ath_snapshot(
        base_mint=GOOD_MINT,
        transport=transport,
        endpoint_secret=_secret(),
        timeout_seconds=10,
        lookback_hours=24,
        ohlcv_type="15m",
        now_utc=FROZEN_NOW,
    )
    assert snap.birdeye_ath_status == BIRDEYE_ATH_STATUS_PRESENT
    assert snap.ath_value == "0.8"
    assert snap.ath_unit == BIRDEYE_REPORTING_UNIT_USD
    assert snap.source_label == BIRDEYE_OHLCV_SOURCE_LABEL
    assert snap.items_count == 3
    # Observed-at should be the unixTime of the max candle
    expected_iso = datetime.fromtimestamp(
        1716010000, tz=timezone.utc
    ).isoformat()
    assert snap.ath_observed_at_utc == expected_iso


def test_present_with_string_high_values():
    body = {
        "success": True,
        "data": {
            "items": [
                {"h": "0.10", "unixTime": 1716000000},
                {"h": "0.85", "unixTime": 1716010000},
                {"h": "0.30", "unixTime": 1716020000},
            ]
        },
    }
    transport = FakeTransport(_ok_result(body))
    snap = fetch_birdeye_ath_snapshot(
        base_mint=GOOD_MINT,
        transport=transport,
        endpoint_secret=_secret(),
        timeout_seconds=10,
        lookback_hours=24,
        ohlcv_type="15m",
        now_utc=FROZEN_NOW,
    )
    assert snap.ath_value == "0.85"


def test_query_params_built_correctly():
    body = {
        "success": True,
        "data": {
            "items": [
                {"h": 0.5, "unixTime": 1716010000},
            ]
        },
    }
    transport = FakeTransport(_ok_result(body))
    fetch_birdeye_ath_snapshot(
        base_mint=GOOD_MINT,
        transport=transport,
        endpoint_secret=_secret(),
        timeout_seconds=10,
        lookback_hours=24,
        ohlcv_type="15m",
        now_utc=FROZEN_NOW,
    )
    call = transport.calls[0]
    assert call["path"] == BIRDEYE_PATH_OHLCV
    assert call["query_params"]["address"] == GOOD_MINT
    assert call["query_params"]["type"] == "15m"
    # time_to from FROZEN_NOW, time_from = time_to - 24*3600
    expected_to = int(FROZEN_NOW.timestamp())
    assert call["query_params"]["time_to"] == str(expected_to)
    assert call["query_params"]["time_from"] == str(
        expected_to - 24 * 3600
    )


# ---------------------------------------------------------------------------
# window_starts_post_migration logic
# ---------------------------------------------------------------------------


def test_window_starts_post_migration_true_when_after():
    body = {
        "success": True,
        "data": {
            "items": [
                {"h": 0.5, "unixTime": 1716010000},
            ]
        },
    }
    transport = FakeTransport(_ok_result(body))
    # FROZEN_NOW = 2026-05-25 12:00:00 UTC, lookback 24h, so
    # time_from = 2026-05-24 12:00:00 UTC = unix 1748174400.
    # Migration = 2026-05-23 12:00:00 UTC (one day before
    # time_from) -> True.
    snap = fetch_birdeye_ath_snapshot(
        base_mint=GOOD_MINT,
        transport=transport,
        endpoint_secret=_secret(),
        timeout_seconds=10,
        lookback_hours=24,
        ohlcv_type="15m",
        now_utc=FROZEN_NOW,
        migration_timestamp_utc="2026-05-23T12:00:00+00:00",
    )
    assert snap.window_starts_post_migration is True


def test_window_starts_post_migration_false_when_before():
    body = {
        "success": True,
        "data": {
            "items": [
                {"h": 0.5, "unixTime": 1716010000},
            ]
        },
    }
    transport = FakeTransport(_ok_result(body))
    # Migration AFTER time_from (between time_from and now) ->
    # the lookback window starts BEFORE the migration, so the
    # ATH may include pre-migration wicks -> False.
    snap = fetch_birdeye_ath_snapshot(
        base_mint=GOOD_MINT,
        transport=transport,
        endpoint_secret=_secret(),
        timeout_seconds=10,
        lookback_hours=24,
        ohlcv_type="15m",
        now_utc=FROZEN_NOW,
        migration_timestamp_utc="2026-05-25T00:00:00+00:00",
    )
    assert snap.window_starts_post_migration is False


def test_window_starts_post_migration_none_when_not_supplied():
    body = {
        "success": True,
        "data": {
            "items": [
                {"h": 0.5, "unixTime": 1716010000},
            ]
        },
    }
    transport = FakeTransport(_ok_result(body))
    snap = fetch_birdeye_ath_snapshot(
        base_mint=GOOD_MINT,
        transport=transport,
        endpoint_secret=_secret(),
        timeout_seconds=10,
        lookback_hours=24,
        ohlcv_type="15m",
        now_utc=FROZEN_NOW,
        migration_timestamp_utc=None,
    )
    assert snap.window_starts_post_migration is None


def test_window_starts_post_migration_none_when_malformed():
    body = {
        "success": True,
        "data": {
            "items": [
                {"h": 0.5, "unixTime": 1716010000},
            ]
        },
    }
    transport = FakeTransport(_ok_result(body))
    snap = fetch_birdeye_ath_snapshot(
        base_mint=GOOD_MINT,
        transport=transport,
        endpoint_secret=_secret(),
        timeout_seconds=10,
        lookback_hours=24,
        ohlcv_type="15m",
        now_utc=FROZEN_NOW,
        migration_timestamp_utc="not-an-iso-timestamp",
    )
    assert snap.window_starts_post_migration is None


# ---------------------------------------------------------------------------
# MISSING paths
# ---------------------------------------------------------------------------


def test_missing_on_empty_items():
    transport = FakeTransport(
        _ok_result({"success": True, "data": {"items": []}})
    )
    snap = fetch_birdeye_ath_snapshot(
        base_mint=GOOD_MINT,
        transport=transport,
        endpoint_secret=_secret(),
        timeout_seconds=10,
        lookback_hours=24,
        ohlcv_type="15m",
        now_utc=FROZEN_NOW,
    )
    assert snap.birdeye_ath_status == BIRDEYE_ATH_STATUS_MISSING
    assert snap.ath_value is None
    assert snap.items_count == 0


def test_missing_when_data_missing():
    transport = FakeTransport(
        _ok_result({"success": True})
    )
    snap = fetch_birdeye_ath_snapshot(
        base_mint=GOOD_MINT,
        transport=transport,
        endpoint_secret=_secret(),
        timeout_seconds=10,
        lookback_hours=24,
        ohlcv_type="15m",
        now_utc=FROZEN_NOW,
    )
    assert snap.birdeye_ath_status == BIRDEYE_ATH_STATUS_MISSING
    assert snap.ath_value is None


def test_missing_when_items_not_a_list():
    transport = FakeTransport(
        _ok_result(
            {"success": True, "data": {"items": "not-a-list"}}
        )
    )
    snap = fetch_birdeye_ath_snapshot(
        base_mint=GOOD_MINT,
        transport=transport,
        endpoint_secret=_secret(),
        timeout_seconds=10,
        lookback_hours=24,
        ohlcv_type="15m",
        now_utc=FROZEN_NOW,
    )
    assert snap.birdeye_ath_status == BIRDEYE_ATH_STATUS_MISSING


def test_missing_when_no_parseable_high():
    transport = FakeTransport(
        _ok_result(
            {
                "success": True,
                "data": {
                    "items": [
                        {"h": None, "unixTime": 1716000000},
                        {"h": "nan", "unixTime": 1716010000},
                        {"h": -1.0, "unixTime": 1716020000},
                    ]
                },
            }
        )
    )
    snap = fetch_birdeye_ath_snapshot(
        base_mint=GOOD_MINT,
        transport=transport,
        endpoint_secret=_secret(),
        timeout_seconds=10,
        lookback_hours=24,
        ohlcv_type="15m",
        now_utc=FROZEN_NOW,
    )
    assert snap.birdeye_ath_status == BIRDEYE_ATH_STATUS_MISSING
    assert snap.ath_value is None
    assert snap.items_count == 3  # three considered, zero used


# ---------------------------------------------------------------------------
# SOURCE_ERROR paths
# ---------------------------------------------------------------------------


def test_source_error_on_http_status_rejected():
    transport = FakeTransport(
        _err_result(
            BIRDEYE_REFUSAL_REASON_HTTP_STATUS_REJECTED, 429
        )
    )
    snap = fetch_birdeye_ath_snapshot(
        base_mint=GOOD_MINT,
        transport=transport,
        endpoint_secret=_secret(),
        timeout_seconds=10,
        lookback_hours=24,
        ohlcv_type="15m",
        now_utc=FROZEN_NOW,
    )
    assert (
        snap.birdeye_ath_status
        == BIRDEYE_ATH_STATUS_SOURCE_ERROR
    )
    assert snap.ath_value is None


def test_source_error_on_http_timeout():
    transport = FakeTransport(
        _err_result(BIRDEYE_REFUSAL_REASON_HTTP_TIMEOUT)
    )
    snap = fetch_birdeye_ath_snapshot(
        base_mint=GOOD_MINT,
        transport=transport,
        endpoint_secret=_secret(),
        timeout_seconds=10,
        lookback_hours=24,
        ohlcv_type="15m",
        now_utc=FROZEN_NOW,
    )
    assert (
        snap.birdeye_ath_status
        == BIRDEYE_ATH_STATUS_SOURCE_ERROR
    )


def test_source_error_on_unsafe_mint():
    transport = FakeTransport(
        _ok_result(
            {"success": True, "data": {"items": []}}
        )
    )
    snap = fetch_birdeye_ath_snapshot(
        base_mint="bad",
        transport=transport,
        endpoint_secret=_secret(),
        timeout_seconds=10,
        lookback_hours=24,
        ohlcv_type="15m",
        now_utc=FROZEN_NOW,
    )
    assert (
        snap.birdeye_ath_status
        == BIRDEYE_ATH_STATUS_SOURCE_ERROR
    )
    assert transport.calls == []


def test_source_error_on_invalid_ohlcv_type():
    transport = FakeTransport(
        _ok_result(
            {"success": True, "data": {"items": []}}
        )
    )
    snap = fetch_birdeye_ath_snapshot(
        base_mint=GOOD_MINT,
        transport=transport,
        endpoint_secret=_secret(),
        timeout_seconds=10,
        lookback_hours=24,
        ohlcv_type="hourly",  # not allowed
        now_utc=FROZEN_NOW,
    )
    assert (
        snap.birdeye_ath_status
        == BIRDEYE_ATH_STATUS_SOURCE_ERROR
    )


def test_source_error_on_invalid_lookback():
    transport = FakeTransport(
        _ok_result(
            {"success": True, "data": {"items": []}}
        )
    )
    snap = fetch_birdeye_ath_snapshot(
        base_mint=GOOD_MINT,
        transport=transport,
        endpoint_secret=_secret(),
        timeout_seconds=10,
        lookback_hours=0,
        ohlcv_type="15m",
        now_utc=FROZEN_NOW,
    )
    assert (
        snap.birdeye_ath_status
        == BIRDEYE_ATH_STATUS_SOURCE_ERROR
    )


# ---------------------------------------------------------------------------
# Stage27.4 AthContextSource Protocol behaviour
# ---------------------------------------------------------------------------


def test_protocol_returns_ath_source_snapshot_on_present():
    body = {
        "success": True,
        "data": {
            "items": [
                {"h": 0.5, "unixTime": 1716010000},
            ]
        },
    }
    transport = FakeTransport(_ok_result(body))
    src = Stage29_2BirdeyeAthSource(
        transport=transport,
        endpoint_secret=_secret(),
        timeout_seconds=10,
        lookback_hours=24,
        ohlcv_type="15m",
        migration_timestamp_utc=None,
    )
    snap = src.read_ath_snapshot(
        GOOD_MINT, pair_quote_asset="SOL"
    )
    assert isinstance(snap, AthSourceSnapshot)
    assert snap.ath_value == "0.5"
    assert snap.ath_unit == "USD"
    assert snap.source_label == "birdeye_defi_ohlcv"
    assert snap.window_starts_post_migration is None


def test_protocol_raises_on_source_error():
    transport = FakeTransport(
        _err_result(
            BIRDEYE_REFUSAL_REASON_HTTP_STATUS_REJECTED, 500
        )
    )
    src = Stage29_2BirdeyeAthSource(
        transport=transport,
        endpoint_secret=_secret(),
        timeout_seconds=10,
        lookback_hours=24,
    )
    with pytest.raises(Stage27AthSourceError) as exc:
        src.read_ath_snapshot(
            GOOD_MINT, pair_quote_asset="SOL"
        )
    assert exc.value.reason == "SOURCE_FAILED"
    assert GOOD_KEY not in str(exc.value)
    assert GOOD_URL not in str(exc.value)


def test_protocol_returns_none_value_on_missing():
    transport = FakeTransport(
        _ok_result({"success": True, "data": {"items": []}})
    )
    src = Stage29_2BirdeyeAthSource(
        transport=transport,
        endpoint_secret=_secret(),
        timeout_seconds=10,
        lookback_hours=24,
    )
    snap = src.read_ath_snapshot(
        GOOD_MINT, pair_quote_asset="SOL"
    )
    assert isinstance(snap, AthSourceSnapshot)
    assert snap.ath_value is None


def test_protocol_rejects_invalid_lookback_at_construct():
    with pytest.raises(Stage29_2BirdeyeError):
        Stage29_2BirdeyeAthSource(
            transport=FakeTransport(
                _ok_result({"success": True})
            ),
            endpoint_secret=_secret(),
            timeout_seconds=10,
            lookback_hours=0,
        )


def test_protocol_rejects_unknown_ohlcv_type_at_construct():
    with pytest.raises(Stage29_2BirdeyeError):
        Stage29_2BirdeyeAthSource(
            transport=FakeTransport(
                _ok_result({"success": True})
            ),
            endpoint_secret=_secret(),
            timeout_seconds=10,
            lookback_hours=24,
            ohlcv_type="hourly",
        )

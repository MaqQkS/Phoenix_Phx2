"""Stage 30.4.1 adapter present-path tests with a fake source.

A fake source that returns a valid
``Stage30_4MarketContextSourceReading`` MUST produce a record with:

  * MC / LP KNOWN with preformatted compact displays.
  * Net deferred (UNKNOWN) unless the fake supplies a valid Net
    value with a closed-set basis.
  * source_status PRESENT, source_reason SOURCE_PRESENT (or the
    fake's overriding closed-set reason).
  * runtime_consumable False (hard-locked in 30.4.1).
"""

from __future__ import annotations

from typing import Optional

from PHX2.stage30.stage30_4_compact_market_context_adapter import (
    project_market_context,
)
from PHX2.stage30.stage30_4_compact_market_context_models import (
    NET_FLOW_BASIS_BUY_SELL_USD_DELTA_24H,
    NET_FLOW_BASIS_UNKNOWN,
    SOURCE_REASON_SOURCE_PRESENT,
    SOURCE_STATUS_PRESENT,
    STATUS_KNOWN,
    STATUS_UNKNOWN,
)
from PHX2.stage30.stage30_4_compact_market_context_source_protocol import (
    Stage30_4MarketContextSourceReading,
)


_VALID_TS: str = "2026-05-28T12:00:00Z"
_OBSERVED_TS: str = "2026-05-28T11:59:30Z"


# ---------------------------------------------------------------------------
# Fake offline source
# ---------------------------------------------------------------------------


class _FakeFixedReadingSource:
    """Fake offline source. Returns a fixed reading on every read.
    No network, no env, no live secret.
    """

    def __init__(
        self, reading: Optional[Stage30_4MarketContextSourceReading]
    ) -> None:
        self._reading = reading
        self.reads: list = []

    def read(
        self, token_mint: str
    ) -> Optional[Stage30_4MarketContextSourceReading]:
        self.reads.append(token_mint)
        return self._reading


# ---------------------------------------------------------------------------
# Present path: MC + LP only
# ---------------------------------------------------------------------------


def test_present_path_mc_and_lp_only() -> None:
    reading = Stage30_4MarketContextSourceReading(
        market_cap_usd_value="83000",
        liquidity_usd_value="27000",
        net_flow_usd_value=None,
        net_flow_basis=NET_FLOW_BASIS_UNKNOWN,
        source_label="birdeye_token_overview",
        observed_at_utc=_OBSERVED_TS,
        stale=False,
        source_reason=None,
    )
    source = _FakeFixedReadingSource(reading)

    rec = project_market_context(
        session_id="sess-A",
        run_id="run-A",
        candidate_id="cand-A",
        token_mint="abcd...wxyz",
        created_at_utc=_VALID_TS,
        source=source,
    )

    assert rec.market_cap_usd_status == STATUS_KNOWN
    assert rec.market_cap_usd_value == "83000"
    assert rec.market_cap_display == "$83k"

    assert rec.liquidity_usd_status == STATUS_KNOWN
    assert rec.liquidity_usd_value == "27000"
    assert rec.liquidity_display == "$27k"

    # Net deferred / Unknown by default.
    assert rec.net_flow_status == STATUS_UNKNOWN
    assert rec.net_flow_usd_value is None
    assert rec.net_flow_display is None
    assert rec.net_flow_basis == NET_FLOW_BASIS_UNKNOWN

    assert rec.source_label == "birdeye_token_overview"
    assert rec.source_status == SOURCE_STATUS_PRESENT
    assert rec.source_reason == SOURCE_REASON_SOURCE_PRESENT
    assert rec.runtime_consumable is False


def test_present_path_records_the_supplied_token_label() -> None:
    reading = Stage30_4MarketContextSourceReading(
        market_cap_usd_value="100",
        liquidity_usd_value=None,
        net_flow_usd_value=None,
        net_flow_basis=NET_FLOW_BASIS_UNKNOWN,
        source_label="birdeye_token_overview",
        observed_at_utc=_OBSERVED_TS,
        stale=False,
        source_reason=None,
    )
    source = _FakeFixedReadingSource(reading)
    rec = project_market_context(
        session_id=None,
        run_id=None,
        candidate_id=None,
        token_mint="ABCD...WXYZ",
        created_at_utc=_VALID_TS,
        source=source,
    )
    assert rec.token_label == "ABCD...WXYZ"
    assert source.reads == ["ABCD...WXYZ"]


# ---------------------------------------------------------------------------
# Present path: MC only (LP missing, Net deferred)
# ---------------------------------------------------------------------------


def test_present_path_mc_only_lp_missing() -> None:
    reading = Stage30_4MarketContextSourceReading(
        market_cap_usd_value="1200000",
        liquidity_usd_value=None,
        net_flow_usd_value=None,
        net_flow_basis=NET_FLOW_BASIS_UNKNOWN,
        source_label="birdeye_token_overview",
        observed_at_utc=_OBSERVED_TS,
        stale=False,
        source_reason=None,
    )
    source = _FakeFixedReadingSource(reading)
    rec = project_market_context(
        session_id=None,
        run_id=None,
        candidate_id=None,
        token_mint="abcd...wxyz",
        created_at_utc=_VALID_TS,
        source=source,
    )

    assert rec.market_cap_usd_status == STATUS_KNOWN
    assert rec.market_cap_display == "$1.2M"
    assert rec.liquidity_usd_status == STATUS_UNKNOWN
    assert rec.liquidity_display is None
    assert rec.net_flow_status == STATUS_UNKNOWN
    assert rec.net_flow_basis == NET_FLOW_BASIS_UNKNOWN


# ---------------------------------------------------------------------------
# Present path: net flow with valid basis
# ---------------------------------------------------------------------------


def test_present_path_with_valid_net_flow_buy_sell_basis() -> None:
    reading = Stage30_4MarketContextSourceReading(
        market_cap_usd_value="83000",
        liquidity_usd_value="27000",
        net_flow_usd_value="12000",
        net_flow_basis=NET_FLOW_BASIS_BUY_SELL_USD_DELTA_24H,
        source_label="birdeye_trade_data",
        observed_at_utc=_OBSERVED_TS,
        stale=False,
        source_reason=None,
    )
    source = _FakeFixedReadingSource(reading)
    rec = project_market_context(
        session_id=None,
        run_id=None,
        candidate_id=None,
        token_mint="abcd...wxyz",
        created_at_utc=_VALID_TS,
        source=source,
    )
    assert rec.net_flow_status == STATUS_KNOWN
    assert rec.net_flow_usd_value == "12000"
    assert rec.net_flow_display == "+$12k buys"
    assert rec.net_flow_basis == NET_FLOW_BASIS_BUY_SELL_USD_DELTA_24H
    assert rec.source_status == SOURCE_STATUS_PRESENT


def test_present_path_with_negative_net_flow() -> None:
    reading = Stage30_4MarketContextSourceReading(
        market_cap_usd_value=None,
        liquidity_usd_value=None,
        net_flow_usd_value="-8000",
        net_flow_basis=NET_FLOW_BASIS_BUY_SELL_USD_DELTA_24H,
        source_label="birdeye_trade_data",
        observed_at_utc=_OBSERVED_TS,
        stale=False,
        source_reason=None,
    )
    source = _FakeFixedReadingSource(reading)
    rec = project_market_context(
        session_id=None,
        run_id=None,
        candidate_id=None,
        token_mint="abcd...wxyz",
        created_at_utc=_VALID_TS,
        source=source,
    )
    assert rec.net_flow_status == STATUS_KNOWN
    assert rec.net_flow_usd_value == "-8000"
    assert rec.net_flow_display == "-$8k sells"


def test_present_path_with_known_zero_net_flow() -> None:
    reading = Stage30_4MarketContextSourceReading(
        market_cap_usd_value=None,
        liquidity_usd_value=None,
        net_flow_usd_value="0",
        net_flow_basis=NET_FLOW_BASIS_BUY_SELL_USD_DELTA_24H,
        source_label="birdeye_trade_data",
        observed_at_utc=_OBSERVED_TS,
        stale=False,
        source_reason=None,
    )
    source = _FakeFixedReadingSource(reading)
    rec = project_market_context(
        session_id=None,
        run_id=None,
        candidate_id=None,
        token_mint="abcd...wxyz",
        created_at_utc=_VALID_TS,
        source=source,
    )
    assert rec.net_flow_status == STATUS_KNOWN
    assert rec.net_flow_usd_value == "0"
    assert rec.net_flow_display == "$0 flat"


# ---------------------------------------------------------------------------
# Present path: never converts Unknown to $0
# ---------------------------------------------------------------------------


def test_present_path_never_converts_unknown_to_zero() -> None:
    """When MC / LP / Net are None on the reading, the projected
    record must carry Unknown (None display), NEVER ``$0``.
    """
    reading = Stage30_4MarketContextSourceReading(
        market_cap_usd_value=None,
        liquidity_usd_value=None,
        net_flow_usd_value=None,
        net_flow_basis=NET_FLOW_BASIS_UNKNOWN,
        source_label="birdeye_token_overview",
        observed_at_utc=_OBSERVED_TS,
        stale=False,
        source_reason=None,
    )
    source = _FakeFixedReadingSource(reading)
    rec = project_market_context(
        session_id=None,
        run_id=None,
        candidate_id=None,
        token_mint="abcd...wxyz",
        created_at_utc=_VALID_TS,
        source=source,
    )
    assert rec.market_cap_display is None
    assert rec.liquidity_display is None
    assert rec.net_flow_display is None
    assert rec.market_cap_usd_value is None
    assert rec.liquidity_usd_value is None
    assert rec.net_flow_usd_value is None


# ---------------------------------------------------------------------------
# Present path: source returning None reading -> UNAVAILABLE
# ---------------------------------------------------------------------------


def test_present_path_source_returns_none_reading() -> None:
    source = _FakeFixedReadingSource(None)
    rec = project_market_context(
        session_id=None,
        run_id=None,
        candidate_id=None,
        token_mint="abcd...wxyz",
        created_at_utc=_VALID_TS,
        source=source,
    )
    assert rec.market_cap_usd_status == STATUS_UNKNOWN
    assert rec.liquidity_usd_status == STATUS_UNKNOWN
    assert rec.net_flow_status == STATUS_UNKNOWN
    assert rec.source_status == "UNAVAILABLE"


# ---------------------------------------------------------------------------
# Present path: runtime_consumable hard-locked False
# ---------------------------------------------------------------------------


def test_present_path_runtime_consumable_locked_false() -> None:
    reading = Stage30_4MarketContextSourceReading(
        market_cap_usd_value="83000",
        liquidity_usd_value="27000",
        net_flow_usd_value="12000",
        net_flow_basis=NET_FLOW_BASIS_BUY_SELL_USD_DELTA_24H,
        source_label="birdeye_token_overview",
        observed_at_utc=_OBSERVED_TS,
        stale=False,
        source_reason=None,
    )
    source = _FakeFixedReadingSource(reading)
    rec = project_market_context(
        session_id=None,
        run_id=None,
        candidate_id=None,
        token_mint="abcd...wxyz",
        created_at_utc=_VALID_TS,
        source=source,
    )
    assert rec.runtime_consumable is False

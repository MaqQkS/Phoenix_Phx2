"""Stage 30.4.1 adapter error + stale path tests.

A fake source that emits invalid MC / LP / Net values must yield
per-slot ERROR with display None. A fake source that flags itself
``stale=True`` must yield per-slot STALE with display None for any
slot that carried a value; missing slots stay UNKNOWN.
"""

from __future__ import annotations

from typing import Optional

from PHX2.stage30.stage30_4_compact_market_context_adapter import (
    project_market_context,
)
from PHX2.stage30.stage30_4_compact_market_context_models import (
    NET_FLOW_BASIS_BUY_SELL_USD_DELTA_24H,
    NET_FLOW_BASIS_UNKNOWN,
    SOURCE_REASON_MC_VALUE_INVALID,
    SOURCE_REASON_LP_VALUE_INVALID,
    SOURCE_REASON_NET_VALUE_INVALID,
    SOURCE_REASON_SOURCE_BASIS_INVALID,
    SOURCE_REASON_SOURCE_OBSERVATION_TIMESTAMP_MALFORMED,
    SOURCE_REASON_SOURCE_REASON_MALFORMED,
    SOURCE_REASON_SOURCE_STALE,
    SOURCE_STATUS_ERROR,
    SOURCE_STATUS_STALE,
    STATUS_ERROR,
    STATUS_KNOWN,
    STATUS_STALE,
    STATUS_UNKNOWN,
)
from PHX2.stage30.stage30_4_compact_market_context_source_protocol import (
    Stage30_4MarketContextSourceReading,
)


_VALID_TS: str = "2026-05-28T12:00:00Z"
_OBSERVED_TS: str = "2026-05-28T11:59:30Z"


class _FakeFixedReadingSource:
    def __init__(
        self, reading: Optional[Stage30_4MarketContextSourceReading]
    ) -> None:
        self._reading = reading

    def read(
        self, token_mint: str
    ) -> Optional[Stage30_4MarketContextSourceReading]:
        return self._reading


# ---------------------------------------------------------------------------
# Invalid MC value (non-decimal-text)
# ---------------------------------------------------------------------------


def test_invalid_mc_value_yields_error_status_and_none_display() -> None:
    reading = Stage30_4MarketContextSourceReading(
        market_cap_usd_value="not_a_number",
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
        session_id=None,
        run_id=None,
        candidate_id=None,
        token_mint="abcd...wxyz",
        created_at_utc=_VALID_TS,
        source=source,
    )
    assert rec.market_cap_usd_status == STATUS_ERROR
    assert rec.market_cap_usd_value is None
    assert rec.market_cap_display is None
    assert rec.liquidity_usd_status == STATUS_KNOWN
    assert rec.liquidity_display == "$27k"
    assert rec.source_status == SOURCE_STATUS_ERROR
    assert rec.source_reason == SOURCE_REASON_MC_VALUE_INVALID


def test_invalid_lp_value_yields_error_status() -> None:
    reading = Stage30_4MarketContextSourceReading(
        market_cap_usd_value="83000",
        liquidity_usd_value="1e6",
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
    assert rec.market_cap_display == "$83k"
    assert rec.liquidity_usd_status == STATUS_ERROR
    assert rec.liquidity_display is None
    assert rec.source_status == SOURCE_STATUS_ERROR
    assert rec.source_reason == SOURCE_REASON_LP_VALUE_INVALID


def test_invalid_net_value_yields_error_status() -> None:
    reading = Stage30_4MarketContextSourceReading(
        market_cap_usd_value=None,
        liquidity_usd_value=None,
        net_flow_usd_value="NaN",
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
    assert rec.net_flow_status == STATUS_ERROR
    assert rec.net_flow_display is None
    assert rec.net_flow_usd_value is None
    assert rec.source_status == SOURCE_STATUS_ERROR
    assert rec.source_reason == SOURCE_REASON_NET_VALUE_INVALID


def test_invalid_negative_mc_yields_error_status() -> None:
    """Unsigned MC is non-negative; ``"-1000"`` must fail the
    pattern and route to ERROR.
    """
    reading = Stage30_4MarketContextSourceReading(
        market_cap_usd_value="-1000",
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
    assert rec.market_cap_usd_status == STATUS_ERROR
    assert rec.source_reason == SOURCE_REASON_MC_VALUE_INVALID


def test_invalid_negative_zero_net_yields_error_status() -> None:
    """``"-0"`` is rejected by the signed validator (mirrors the
    formatter's policy).
    """
    reading = Stage30_4MarketContextSourceReading(
        market_cap_usd_value=None,
        liquidity_usd_value=None,
        net_flow_usd_value="-0",
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
    assert rec.net_flow_status == STATUS_ERROR
    assert rec.source_reason == SOURCE_REASON_NET_VALUE_INVALID


def test_non_string_value_yields_error_status() -> None:
    """A non-``str`` value supplied for any slot is invalid."""
    reading = Stage30_4MarketContextSourceReading(
        market_cap_usd_value=83000,  # type: ignore[arg-type]
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
    assert rec.market_cap_usd_status == STATUS_ERROR
    assert rec.source_reason == SOURCE_REASON_MC_VALUE_INVALID


# ---------------------------------------------------------------------------
# Stale source
# ---------------------------------------------------------------------------


def test_stale_source_yields_stale_status_for_value_bearing_slots() -> None:
    reading = Stage30_4MarketContextSourceReading(
        market_cap_usd_value="83000",
        liquidity_usd_value="27000",
        net_flow_usd_value=None,
        net_flow_basis=NET_FLOW_BASIS_UNKNOWN,
        source_label="birdeye_token_overview",
        observed_at_utc=_OBSERVED_TS,
        stale=True,
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
    # Stale display is deterministic: None.
    assert rec.market_cap_usd_status == STATUS_STALE
    assert rec.market_cap_usd_value == "83000"
    assert rec.market_cap_display is None
    assert rec.liquidity_usd_status == STATUS_STALE
    assert rec.liquidity_usd_value == "27000"
    assert rec.liquidity_display is None
    # Missing slots stay UNKNOWN even when source is stale.
    assert rec.net_flow_status == STATUS_UNKNOWN
    assert rec.net_flow_display is None

    assert rec.source_status == SOURCE_STATUS_STALE
    assert rec.source_reason == SOURCE_REASON_SOURCE_STALE


def test_stale_source_with_no_values_remains_unknown_per_slot() -> None:
    reading = Stage30_4MarketContextSourceReading(
        market_cap_usd_value=None,
        liquidity_usd_value=None,
        net_flow_usd_value=None,
        net_flow_basis=NET_FLOW_BASIS_UNKNOWN,
        source_label="birdeye_token_overview",
        observed_at_utc=_OBSERVED_TS,
        stale=True,
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
    assert rec.market_cap_usd_status == STATUS_UNKNOWN
    assert rec.liquidity_usd_status == STATUS_UNKNOWN
    assert rec.net_flow_status == STATUS_UNKNOWN
    assert rec.market_cap_display is None
    assert rec.liquidity_display is None
    assert rec.net_flow_display is None
    assert rec.source_status == SOURCE_STATUS_STALE
    assert rec.source_reason == SOURCE_REASON_SOURCE_STALE


# ---------------------------------------------------------------------------
# Invalid basis token
# ---------------------------------------------------------------------------


def test_invalid_basis_token_yields_error_and_falls_back_to_unknown() -> None:
    reading = Stage30_4MarketContextSourceReading(
        market_cap_usd_value="83000",
        liquidity_usd_value=None,
        net_flow_usd_value=None,
        net_flow_basis="some_unsupported_basis",
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
    assert rec.net_flow_basis == NET_FLOW_BASIS_UNKNOWN
    assert rec.source_status == SOURCE_STATUS_ERROR
    assert rec.source_reason == SOURCE_REASON_SOURCE_BASIS_INVALID


# ---------------------------------------------------------------------------
# Invalid observed_at_utc
# ---------------------------------------------------------------------------


def test_invalid_observed_at_utc_yields_error_status() -> None:
    reading = Stage30_4MarketContextSourceReading(
        market_cap_usd_value="83000",
        liquidity_usd_value=None,
        net_flow_usd_value=None,
        net_flow_basis=NET_FLOW_BASIS_UNKNOWN,
        source_label="birdeye_token_overview",
        observed_at_utc="not a timestamp",
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
    assert rec.source_status == SOURCE_STATUS_ERROR
    assert rec.source_reason == (
        SOURCE_REASON_SOURCE_OBSERVATION_TIMESTAMP_MALFORMED
    )
    # The MC value still validated, so it remains KNOWN with display.
    assert rec.market_cap_usd_status == STATUS_KNOWN


# ---------------------------------------------------------------------------
# Off-closed-set source_reason on the reading
# ---------------------------------------------------------------------------


def test_off_closed_set_source_reason_falls_back_to_malformed() -> None:
    reading = Stage30_4MarketContextSourceReading(
        market_cap_usd_value=None,
        liquidity_usd_value=None,
        net_flow_usd_value=None,
        net_flow_basis=NET_FLOW_BASIS_UNKNOWN,
        source_label="birdeye_token_overview",
        observed_at_utc=_OBSERVED_TS,
        stale=False,
        source_reason="FREEFORM_REASON_NOT_ON_CLOSED_SET",
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
    assert rec.source_status == SOURCE_STATUS_ERROR
    assert rec.source_reason == SOURCE_REASON_SOURCE_REASON_MALFORMED


# ---------------------------------------------------------------------------
# Reason precedence (MC > LP > Net > basis > observed_at > reason
#                   > stale > caller > present)
# ---------------------------------------------------------------------------


def test_reason_precedence_mc_over_lp_over_net() -> None:
    reading = Stage30_4MarketContextSourceReading(
        market_cap_usd_value="bad_mc",
        liquidity_usd_value="bad_lp",
        net_flow_usd_value="bad_net",
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
    # MC error takes precedence over LP / Net errors.
    assert rec.source_reason == SOURCE_REASON_MC_VALUE_INVALID


# ---------------------------------------------------------------------------
# Runtime-consumable hard-locked False even on error / stale paths
# ---------------------------------------------------------------------------


def test_runtime_consumable_false_on_error_path() -> None:
    reading = Stage30_4MarketContextSourceReading(
        market_cap_usd_value="bad",
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
    assert rec.runtime_consumable is False


def test_runtime_consumable_false_on_stale_path() -> None:
    reading = Stage30_4MarketContextSourceReading(
        market_cap_usd_value="83000",
        liquidity_usd_value=None,
        net_flow_usd_value=None,
        net_flow_basis=NET_FLOW_BASIS_UNKNOWN,
        source_label="birdeye_token_overview",
        observed_at_utc=_OBSERVED_TS,
        stale=True,
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

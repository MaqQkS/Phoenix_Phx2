"""Stage 30.4.3 Birdeye source: present-path mapping + end-to-end render.

A fake Stage 29.2 transport returns a canned token-overview snapshot.
The Stage 30.4.3 bridge maps the snapshot onto a Stage 30.4.1
reading; the Stage 30.4.1 adapter projects the reading onto a compact
market-context record; the Stage 30.2 renderer renders the record's
displays into the compact ping body.

Pins:

  * mc / liquidity present -> canonical decimal text,
  * marketCap / liquidityUsd spelling works,
  * market_cap / liquidity_usd spelling works,
  * float + string values canonicalize,
  * MC present / LP missing -> MC known, LP Unknown,
  * LP present / MC missing -> LP known, MC Unknown,
  * zero preserved as "0",
  * source_label / observed_at_utc / stale / source_reason / net
    deferred fields,
  * the transport is called with the token-overview path + address,
  * end-to-end: data.mc=83000 + data.liquidity=27000 renders
    ``MC: $83k`` / ``LP: $27k`` / ``Net: Unknown``.

Fake transport only. No live call, no env, no Discord.
"""

from __future__ import annotations

from typing import Mapping, Optional

from PHX2.stage29.stage29_2_birdeye_http_transport import (
    Stage29_2BirdeyeHttpResult,
)
from PHX2.stage29.stage29_2_birdeye_models import (
    BIRDEYE_REFUSAL_REASON_NONE,
)
from PHX2.stage29.stage29_2_birdeye_readiness import (
    Stage29_2BirdeyeEndpointSecret,
)
from PHX2.stage30.compact_ping_models import (
    CompactPingInputRecord,
    DISPLAY_UNKNOWN,
)
from PHX2.stage30.compact_ping_renderer import render_compact_ping
from PHX2.stage30.stage30_4_3_market_context_birdeye_source import (
    STAGE30_4_3_BIRDEYE_SOURCE_LABEL,
    Stage30_4_3BirdeyeMarketContextSource,
)
from PHX2.stage30.stage30_4_compact_market_context_adapter import (
    project_market_context,
)
from PHX2.stage30.stage30_4_compact_market_context_models import (
    NET_FLOW_BASIS_UNKNOWN,
    SOURCE_REASON_SOURCE_PRESENT,
    SOURCE_STATUS_PRESENT,
    STATUS_KNOWN,
    STATUS_UNKNOWN,
)
from PHX2.stage30.tier_decision_models import (
    BASIS_PRICE,
    STAGE30_1_TIER_DECISION_SCHEMA_VERSION,
    TIER_REASON_TIER_1_IN_BAND,
    TIER_TOKEN_TIER_1,
    TierDecisionRecord,
)


_VALID_MINT: str = "So11111111111111111111111111111111111111112"
_OBSERVED_TS: str = "2026-05-28T11:59:30Z"
_VALID_TS: str = "2026-05-28T12:00:00Z"


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


def _result(body: Optional[dict]) -> Stage29_2BirdeyeHttpResult:
    return Stage29_2BirdeyeHttpResult(
        refusal_reason=BIRDEYE_REFUSAL_REASON_NONE,
        http_status_code=200,
        body=body,
        fetched_at_utc=_OBSERVED_TS,
    )


def _transport(body: Optional[dict]) -> _FakeTransport:
    return _FakeTransport(_result(body))


def _source(
    transport: _FakeTransport,
) -> Stage30_4_3BirdeyeMarketContextSource:
    return Stage30_4_3BirdeyeMarketContextSource(
        transport=transport,
        endpoint_secret=_endpoint_secret(),
        timeout_seconds=30,
    )


def _read(body: Optional[dict]):
    return _source(_transport(body)).read(_VALID_MINT)


def _project(body: Optional[dict]):
    source = _source(_transport(body))
    return project_market_context(
        session_id=None,
        run_id=None,
        candidate_id=None,
        token_mint=_VALID_MINT,
        created_at_utc=_VALID_TS,
        source=source,
    )


# ---------------------------------------------------------------------------
# Reading-level: MC + LP present, canonical text + envelope fields
# ---------------------------------------------------------------------------


def test_mc_and_liquidity_present_canonical_text() -> None:
    transport = _transport({"data": {"mc": 83000, "liquidity": 27000}})
    reading = _source(transport).read(_VALID_MINT)
    assert reading is not None
    assert reading.market_cap_usd_value == "83000"
    assert reading.liquidity_usd_value == "27000"
    # Net deferred at Stage 30.4.3.
    assert reading.net_flow_usd_value is None
    assert reading.net_flow_basis == NET_FLOW_BASIS_UNKNOWN
    # Envelope fields.
    assert reading.source_label == "birdeye_token_overview"
    assert reading.source_label == STAGE30_4_3_BIRDEYE_SOURCE_LABEL
    assert reading.observed_at_utc == _OBSERVED_TS
    assert reading.stale is False
    assert reading.source_reason is None
    # The bridge calls the transport once, at the token-overview path,
    # with the address query param and the configured timeout.
    assert transport.calls == [
        ("/defi/token_overview", {"address": _VALID_MINT}, 30)
    ]


def test_float_values_canonicalize() -> None:
    reading = _read({"data": {"mc": 83000.0, "liquidity": 27000.5}})
    assert reading is not None
    assert reading.market_cap_usd_value == "83000"
    assert reading.liquidity_usd_value == "27000.5"


def test_string_values_canonicalize() -> None:
    reading = _read({"data": {"mc": "83000", "liquidity": "27000"}})
    assert reading is not None
    assert reading.market_cap_usd_value == "83000"
    assert reading.liquidity_usd_value == "27000"


# ---------------------------------------------------------------------------
# Reading-level: alternate field spellings
# ---------------------------------------------------------------------------


def test_marketcap_liquidityusd_spelling_works() -> None:
    reading = _read(
        {"data": {"marketCap": 83000, "liquidityUsd": 27000}}
    )
    assert reading is not None
    assert reading.market_cap_usd_value == "83000"
    assert reading.liquidity_usd_value == "27000"


def test_market_cap_liquidity_usd_spelling_works() -> None:
    reading = _read(
        {"data": {"market_cap": 83000, "liquidity_usd": 27000}}
    )
    assert reading is not None
    assert reading.market_cap_usd_value == "83000"
    assert reading.liquidity_usd_value == "27000"


# ---------------------------------------------------------------------------
# Reading-level: zero preserved
# ---------------------------------------------------------------------------


def test_zero_preserved_as_string_zero() -> None:
    reading = _read({"data": {"mc": 0, "liquidity": 0}})
    assert reading is not None
    assert reading.market_cap_usd_value == "0"
    assert reading.liquidity_usd_value == "0"


# ---------------------------------------------------------------------------
# Adapter-level: MC present / LP missing and the mirror case
# ---------------------------------------------------------------------------


def test_mc_present_lp_missing_through_adapter() -> None:
    rec = _project({"data": {"mc": 83000}})
    assert rec.market_cap_usd_status == STATUS_KNOWN
    assert rec.market_cap_display == "$83k"
    assert rec.liquidity_usd_status == STATUS_UNKNOWN
    assert rec.liquidity_display is None
    assert rec.net_flow_status == STATUS_UNKNOWN
    assert rec.source_status == SOURCE_STATUS_PRESENT
    assert rec.source_reason == SOURCE_REASON_SOURCE_PRESENT
    assert rec.source_label == "birdeye_token_overview"


def test_lp_present_mc_missing_through_adapter() -> None:
    rec = _project({"data": {"liquidity": 27000}})
    assert rec.liquidity_usd_status == STATUS_KNOWN
    assert rec.liquidity_display == "$27k"
    assert rec.market_cap_usd_status == STATUS_UNKNOWN
    assert rec.market_cap_display is None
    assert rec.net_flow_status == STATUS_UNKNOWN


# ---------------------------------------------------------------------------
# End-to-end: bridge -> adapter -> Stage 30.2 renderer
# ---------------------------------------------------------------------------


def _tier_decision() -> TierDecisionRecord:
    """A clean in-band Tier 1 decision: no tier-reason warning so the
    rendered body carries no Notes section that could obscure the
    MC / LP / Net lines.
    """
    return TierDecisionRecord(
        schema_version=STAGE30_1_TIER_DECISION_SCHEMA_VERSION,
        session_id=None,
        ping_id=None,
        candidate_id=None,
        mint=None,
        basis=BASIS_PRICE,
        drawdown_from_ath_raw="-0.55",
        drop_positive="0.55",
        ath_status="PRESENT",
        ath_since_migration_status="PRESENT",
        migration_status="PRESENT",
        tier_token=TIER_TOKEN_TIER_1,
        tier_reason=TIER_REASON_TIER_1_IN_BAND,
        created_at_utc=_VALID_TS,
    )


def test_end_to_end_render_mc_83k_lp_27k_net_unknown() -> None:
    rec = _project({"data": {"mc": 83000, "liquidity": 27000}})
    # Sanity: the bridge + adapter produced the expected compact
    # displays before we hand them to the renderer.
    assert rec.market_cap_display == "$83k"
    assert rec.liquidity_display == "$27k"
    assert rec.net_flow_display is None

    input_record = CompactPingInputRecord(
        tier_decision=_tier_decision(),
        mint=_VALID_MINT,
        symbol="PHX",
        current_mc_text=rec.market_cap_display,
        ath_mc_text=None,
        migration_mc_text=None,
        lp_text=rec.liquidity_display,
        # Net deferred: None renders as the Unknown sentinel.
        net_flow_text=rec.net_flow_display,
        age_since_migration_seconds=None,
        price_status="PRESENT",
        session_id=None,
        ping_id=None,
        candidate_id=None,
        created_at_utc=_VALID_TS,
    )
    snapshot = render_compact_ping(input_record)
    body = snapshot.body_text

    assert "MC: $83k" in body
    assert "LP: $27k" in body
    assert f"Net: {DISPLAY_UNKNOWN}" in body
    assert "Net: Unknown" in body
    # The rendered displays echo on the snapshot fields too.
    assert snapshot.current_mc_display == "$83k"
    assert snapshot.lp_display == "$27k"
    assert snapshot.net_flow_display == DISPLAY_UNKNOWN

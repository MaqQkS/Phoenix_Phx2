"""Stage 30.4.3 Birdeye source: partial + present-but-bad values.

Stage 30.4.3 policy: a present-but-bad provider value (boolean,
``NaN``, infinity, negative, malformed string) becomes ``None`` on
the reading. The Stage 30.4.1 adapter then resolves the slot to
``UNKNOWN`` -- NEVER ``ERROR``, NEVER ``0``. A genuine zero stays
``"0"`` (covered in the present-path suite). Partial snapshots (one
good field, one bad) keep the good field KNOWN and the bad field
Unknown.

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
from PHX2.stage30.stage30_4_3_market_context_birdeye_source import (
    Stage30_4_3BirdeyeMarketContextSource,
)
from PHX2.stage30.stage30_4_compact_market_context_adapter import (
    project_market_context,
)
from PHX2.stage30.stage30_4_compact_market_context_models import (
    SOURCE_STATUS_PRESENT,
    STATUS_ERROR,
    STATUS_KNOWN,
    STATUS_UNKNOWN,
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
    """Fake Stage 29.2 transport returning a fixed canned result."""

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


def _source(body: Optional[dict]) -> Stage30_4_3BirdeyeMarketContextSource:
    result = Stage29_2BirdeyeHttpResult(
        refusal_reason=BIRDEYE_REFUSAL_REASON_NONE,
        http_status_code=200,
        body=body,
        fetched_at_utc=_OBSERVED_TS,
    )
    return Stage30_4_3BirdeyeMarketContextSource(
        transport=_FakeTransport(result),
        endpoint_secret=_endpoint_secret(),
        timeout_seconds=30,
    )


def _read(body: Optional[dict]):
    return _source(body).read(_VALID_MINT)


def _project(body: Optional[dict]):
    return project_market_context(
        session_id=None,
        run_id=None,
        candidate_id=None,
        token_mint=_VALID_MINT,
        created_at_utc=_VALID_TS,
        source=_source(body),
    )


# ---------------------------------------------------------------------------
# Reading-level: present-but-bad collapses to None
# ---------------------------------------------------------------------------


def test_bool_values_rejected_to_none() -> None:
    reading = _read({"data": {"mc": True, "liquidity": False}})
    assert reading is not None
    assert reading.market_cap_usd_value is None
    assert reading.liquidity_usd_value is None


def test_nan_and_infinity_rejected_to_none() -> None:
    for bad in (float("nan"), float("inf"), float("-inf")):
        reading = _read({"data": {"mc": bad, "liquidity": bad}})
        assert reading is not None
        assert reading.market_cap_usd_value is None, (
            f"mc={bad!r} must be rejected to None"
        )
        assert reading.liquidity_usd_value is None, (
            f"liquidity={bad!r} must be rejected to None"
        )


def test_negative_values_rejected_to_none() -> None:
    reading = _read({"data": {"mc": -100, "liquidity": -0.5}})
    assert reading is not None
    assert reading.market_cap_usd_value is None
    assert reading.liquidity_usd_value is None


def test_negative_string_rejected_to_none() -> None:
    reading = _read({"data": {"mc": "-100", "liquidity": "-1.5"}})
    assert reading is not None
    assert reading.market_cap_usd_value is None
    assert reading.liquidity_usd_value is None


def test_malformed_strings_rejected_to_none() -> None:
    reading = _read(
        {"data": {"mc": "not_a_number", "liquidity": "1,000"}}
    )
    assert reading is not None
    assert reading.market_cap_usd_value is None
    assert reading.liquidity_usd_value is None


def test_non_numeric_types_rejected_to_none() -> None:
    reading = _read(
        {"data": {"mc": [83000], "liquidity": {"v": 27000}}}
    )
    assert reading is not None
    assert reading.market_cap_usd_value is None
    assert reading.liquidity_usd_value is None


# ---------------------------------------------------------------------------
# Reading-level: partial (one good, one bad)
# ---------------------------------------------------------------------------


def test_partial_reading_mc_good_lp_bad() -> None:
    reading = _read({"data": {"mc": 83000, "liquidity": True}})
    assert reading is not None
    assert reading.market_cap_usd_value == "83000"
    assert reading.liquidity_usd_value is None


def test_partial_reading_mc_bad_lp_good() -> None:
    reading = _read({"data": {"mc": float("nan"), "liquidity": 27000}})
    assert reading is not None
    assert reading.market_cap_usd_value is None
    assert reading.liquidity_usd_value == "27000"


# ---------------------------------------------------------------------------
# Adapter-level: bad values resolve to UNKNOWN, never ERROR
# ---------------------------------------------------------------------------


def test_bad_values_resolve_to_unknown_not_error() -> None:
    rec = _project(
        {"data": {"mc": float("nan"), "liquidity": "garbage"}}
    )
    assert rec.market_cap_usd_status == STATUS_UNKNOWN
    assert rec.liquidity_usd_status == STATUS_UNKNOWN
    assert rec.market_cap_usd_status != STATUS_ERROR
    assert rec.liquidity_usd_status != STATUS_ERROR
    # Displays must be None (Unknown), never "$0".
    assert rec.market_cap_display is None
    assert rec.liquidity_display is None
    # A reading WAS emitted (valid shape), so the source is PRESENT.
    assert rec.source_status == SOURCE_STATUS_PRESENT


def test_partial_bad_through_adapter_keeps_good_field_known() -> None:
    rec = _project(
        {"data": {"mc": 83000, "liquidity": float("inf")}}
    )
    assert rec.market_cap_usd_status == STATUS_KNOWN
    assert rec.market_cap_display == "$83k"
    assert rec.liquidity_usd_status == STATUS_UNKNOWN
    assert rec.liquidity_usd_status != STATUS_ERROR
    assert rec.liquidity_display is None

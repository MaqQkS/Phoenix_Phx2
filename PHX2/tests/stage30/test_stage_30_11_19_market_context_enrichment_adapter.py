"""Stage 30.11.19 market-context enrichment adapter Layer-0 tests.

Offline / pure only. Proves the committed adapter's Layer-0 enrichment: a usable
reading fills the coherent market-context bundle (current_market_cap_usd,
liquidity_usd, market_context_fetched_at_utc, market_context_status=PRESENT) on a
COPY of the base fact while carrying current_price + migration_time_utc UNCHANGED
(``ENRICHED``); a non-facts base, an absent / wrong-shape / stale reading, or a
missing / invalid MC / LP / observed-at fails closed to the precise closed-set
``SKIPPED_*`` token with ``enriched_facts=None``; and an out-of-caps session config
fails closed before any base fact is scanned.

No live call, no provider, no network, no env read, no send.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

import pytest

from PHX2.stage30.stage30_11_17_operator_curated_candidate_list_models import (
    Stage30_11_17SessionConfig,
)
from PHX2.stage30.stage30_11_18_harvested_facts_models import (
    Stage30_11_18HarvestedCandidateFacts,
)
from PHX2.stage30.stage30_11_19_market_context_enrichment_models import (
    ENRICHMENT_DECISION_ENRICHED,
    ENRICHMENT_DECISION_SKIPPED_INVALID_LIQUIDITY_USD,
    ENRICHMENT_DECISION_SKIPPED_INVALID_MARKET_CAP,
    ENRICHMENT_DECISION_SKIPPED_INVALID_OBSERVED_AT,
    ENRICHMENT_DECISION_SKIPPED_MISSING_LIQUIDITY_USD,
    ENRICHMENT_DECISION_SKIPPED_MISSING_MARKET_CAP,
    ENRICHMENT_DECISION_SKIPPED_MISSING_OBSERVED_AT,
    ENRICHMENT_DECISION_SKIPPED_NO_MARKET_CONTEXT_READING,
    ENRICHMENT_DECISION_SKIPPED_NOT_A_MARKET_CONTEXT_READING,
    ENRICHMENT_DECISION_SKIPPED_NOT_BASE_FACTS,
    ENRICHMENT_DECISION_SKIPPED_STALE_MARKET_CONTEXT,
)
from PHX2.stage30.stage30_11_19_market_context_enrichment_adapter import (
    Stage30_11_19MarketContextEnrichmentError,
    enrich_facts_with_market_context,
    run_stage30_11_19_enriched_session,
)


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _FakeReading:
    market_cap_usd_value: Optional[str]
    liquidity_usd_value: Optional[str]
    observed_at_utc: Optional[str]
    stale: bool


@dataclass(frozen=True)
class _WrongShapeReading:
    # Missing the required market-context attrs.
    foo: str


class _FakeSource:
    def __init__(self, reading: Any) -> None:
        self._reading = reading

    def read(self, token_mint: str) -> Any:
        return self._reading


class _RaisingSource:
    def read(self, token_mint: str) -> Any:
        raise RuntimeError("boom")


_GOOD_MINT: str = "Et9km9VRfjeeowsMR1YmjR1GhxXHBatAEVhggxYVfaNe"
_GOOD_CID: str = "stage30_11_19_cand_dip"
_GOOD_MIGRATION: str = "2026-06-06T06:14:10Z"
_GOOD_PRICE: str = "0.000003053202401565669"
_GOOD_CREATED: str = "2026-06-07T07:06:40Z"

_READING_MC: str = "9100"
_READING_LP: str = "6900"
_READING_OBSERVED: str = "2026-06-07T07:05:40Z"


def _base_facts(**overrides) -> Stage30_11_18HarvestedCandidateFacts:
    # The market fields carry distinct PLACEHOLDER values so an ENRICHED result
    # proves they were OVERWRITTEN from the reading.
    base = dict(
        token_mint=_GOOD_MINT,
        candidate_id=_GOOD_CID,
        migration_time_utc=_GOOD_MIGRATION,
        current_price=_GOOD_PRICE,
        current_market_cap_usd="1",
        liquidity_usd="1",
        market_context_status="UNKNOWN",
        market_context_fetched_at_utc="2020-01-01T00:00:00Z",
        created_at_utc=_GOOD_CREATED,
        symbol_or_name="PHX",
        migration_source="src_ref",
        age_display="~24h",
    )
    base.update(overrides)
    return Stage30_11_18HarvestedCandidateFacts(**base)


def _good_reading() -> _FakeReading:
    return _FakeReading(
        market_cap_usd_value=_READING_MC,
        liquidity_usd_value=_READING_LP,
        observed_at_utc=_READING_OBSERVED,
        stale=False,
    )


# ---------------------------------------------------------------------------
# 1. ENRICHED fills the coherent bundle; price + migration carried unchanged
# ---------------------------------------------------------------------------


def test_enriched_fills_bundle_and_carries_price_migration_unchanged() -> None:
    result = enrich_facts_with_market_context(
        _base_facts(), market_context_source=_FakeSource(_good_reading())
    )
    assert result.decision == ENRICHMENT_DECISION_ENRICHED
    enriched = result.enriched_facts
    assert isinstance(enriched, Stage30_11_18HarvestedCandidateFacts)
    # The four market fields are overwritten from the reading.
    assert enriched.current_market_cap_usd == _READING_MC
    assert enriched.liquidity_usd == _READING_LP
    assert enriched.market_context_fetched_at_utc == _READING_OBSERVED
    assert enriched.market_context_status == "PRESENT"
    # Everything else (especially price + migration time) is carried unchanged.
    assert enriched.current_price == _GOOD_PRICE
    assert enriched.migration_time_utc == _GOOD_MIGRATION
    assert enriched.token_mint == _GOOD_MINT
    assert enriched.candidate_id == _GOOD_CID
    assert enriched.symbol_or_name == "PHX"
    assert enriched.migration_source == "src_ref"
    assert enriched.age_display == "~24h"


# ---------------------------------------------------------------------------
# 2. Every closed-set Layer-0 skip token (first failing check wins)
# ---------------------------------------------------------------------------


def test_skipped_not_base_facts() -> None:
    result = enrich_facts_with_market_context(
        "not a facts record", market_context_source=_FakeSource(_good_reading())
    )
    assert result.decision == ENRICHMENT_DECISION_SKIPPED_NOT_BASE_FACTS
    assert result.enriched_facts is None


def test_skipped_no_reading_when_source_returns_none() -> None:
    result = enrich_facts_with_market_context(
        _base_facts(), market_context_source=_FakeSource(None)
    )
    assert result.decision == (
        ENRICHMENT_DECISION_SKIPPED_NO_MARKET_CONTEXT_READING
    )
    assert result.enriched_facts is None


def test_skipped_no_reading_when_source_raises() -> None:
    result = enrich_facts_with_market_context(
        _base_facts(), market_context_source=_RaisingSource()
    )
    assert result.decision == (
        ENRICHMENT_DECISION_SKIPPED_NO_MARKET_CONTEXT_READING
    )


def test_skipped_not_a_reading_on_wrong_shape() -> None:
    result = enrich_facts_with_market_context(
        _base_facts(),
        market_context_source=_FakeSource(_WrongShapeReading(foo="x")),
    )
    assert result.decision == (
        ENRICHMENT_DECISION_SKIPPED_NOT_A_MARKET_CONTEXT_READING
    )


def test_skipped_stale() -> None:
    reading = _FakeReading(
        market_cap_usd_value=_READING_MC,
        liquidity_usd_value=_READING_LP,
        observed_at_utc=_READING_OBSERVED,
        stale=True,
    )
    result = enrich_facts_with_market_context(
        _base_facts(), market_context_source=_FakeSource(reading)
    )
    assert result.decision == ENRICHMENT_DECISION_SKIPPED_STALE_MARKET_CONTEXT


def test_layer0_missing_and_invalid_tokens() -> None:
    cases = (
        (
            _FakeReading(None, _READING_LP, _READING_OBSERVED, False),
            ENRICHMENT_DECISION_SKIPPED_MISSING_MARKET_CAP,
        ),
        (
            _FakeReading("0", _READING_LP, _READING_OBSERVED, False),
            ENRICHMENT_DECISION_SKIPPED_INVALID_MARKET_CAP,
        ),
        (
            _FakeReading(_READING_MC, None, _READING_OBSERVED, False),
            ENRICHMENT_DECISION_SKIPPED_MISSING_LIQUIDITY_USD,
        ),
        (
            _FakeReading(_READING_MC, "abc", _READING_OBSERVED, False),
            ENRICHMENT_DECISION_SKIPPED_INVALID_LIQUIDITY_USD,
        ),
        (
            _FakeReading(_READING_MC, _READING_LP, "", False),
            ENRICHMENT_DECISION_SKIPPED_MISSING_OBSERVED_AT,
        ),
        (
            _FakeReading(_READING_MC, _READING_LP, "nope", False),
            ENRICHMENT_DECISION_SKIPPED_INVALID_OBSERVED_AT,
        ),
    )
    for reading, expected in cases:
        result = enrich_facts_with_market_context(
            _base_facts(), market_context_source=_FakeSource(reading)
        )
        assert result.decision == expected, (reading, result.decision)
        assert result.enriched_facts is None


# ---------------------------------------------------------------------------
# 3. The session fails closed before scanning on an out-of-caps config
# ---------------------------------------------------------------------------


def test_run_session_raises_on_invalid_config() -> None:
    bad_config = Stage30_11_17SessionConfig(
        max_candidates=999,
        max_compositions=1,
        created_at_utc=_GOOD_CREATED,
    )
    with pytest.raises(Stage30_11_19MarketContextEnrichmentError):
        run_stage30_11_19_enriched_session(
            [],
            market_context_source=_FakeSource(_good_reading()),
            config=bad_config,
            ledger=None,
            ath_transport=None,
            ath_endpoint_secret=None,
            now_utc=None,
            transport_client=None,
            now_seconds=None,
        )

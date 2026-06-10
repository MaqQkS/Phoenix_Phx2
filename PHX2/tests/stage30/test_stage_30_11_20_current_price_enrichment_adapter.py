"""Stage 30.11.20 current-price enrichment adapter Layer-0 tests.

Offline / pure only. Proves the committed adapter's Layer-0 enrichment: a usable
PRESENT price snapshot overwrites ONLY ``current_price`` on a COPY of the base fact
while carrying ``market_context_fetched_at_utc`` + ``migration_time_utc`` + every
other field UNCHANGED (``ENRICHED``); a non-facts base, an absent / wrong-shape
snapshot, a SOURCE_ERROR / MISSING / unrecognized status, or a missing / invalid /
non-positive price value / fetched-at fails closed to the precise closed-set
``SKIPPED_*`` token with ``enriched_facts=None``; and an out-of-caps session config
fails closed before any base fact is scanned (the price source is never called).

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
from PHX2.stage30.stage30_11_20_current_price_enrichment_models import (
    PRICE_ENRICHMENT_DECISION_ENRICHED,
    PRICE_ENRICHMENT_DECISION_SKIPPED_INVALID_PRICE_FETCHED_AT,
    PRICE_ENRICHMENT_DECISION_SKIPPED_INVALID_PRICE_VALUE,
    PRICE_ENRICHMENT_DECISION_SKIPPED_MISSING_PRICE_FETCHED_AT,
    PRICE_ENRICHMENT_DECISION_SKIPPED_MISSING_PRICE_VALUE,
    PRICE_ENRICHMENT_DECISION_SKIPPED_NO_PRICE_READING,
    PRICE_ENRICHMENT_DECISION_SKIPPED_NOT_A_PRICE_READING,
    PRICE_ENRICHMENT_DECISION_SKIPPED_NOT_BASE_FACTS,
    PRICE_ENRICHMENT_DECISION_SKIPPED_PRICE_MISSING,
    PRICE_ENRICHMENT_DECISION_SKIPPED_PRICE_SOURCE_ERROR,
    PRICE_ENRICHMENT_DECISION_SKIPPED_PRICE_STATUS_UNRECOGNIZED,
)
from PHX2.stage30.stage30_11_20_current_price_enrichment_adapter import (
    Stage30_11_20CurrentPriceEnrichmentError,
    enrich_facts_with_current_price,
    run_stage30_11_20_price_enriched_session,
)


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _FakeSnapshot:
    price_value: Optional[str]
    birdeye_price_status: str
    fetched_at_utc: Optional[str]


@dataclass(frozen=True)
class _WrongShapeSnapshot:
    # Missing the required price-snapshot attrs.
    foo: str


class _FakePriceSource:
    """Duck-typed fake exposing the NATIVE committed surface:
    ``fetch_snapshot(*, base_mint)``.
    """

    def __init__(self, snapshot: Any) -> None:
        self._snapshot = snapshot
        self.calls: int = 0

    def fetch_snapshot(self, *, base_mint: str) -> Any:
        self.calls += 1
        return self._snapshot


class _RaisingPriceSource:
    def fetch_snapshot(self, *, base_mint: str) -> Any:
        raise RuntimeError("boom")


class _NoMethodSource:
    # No fetch_snapshot surface at all.
    pass


_GOOD_MINT: str = "Et9km9VRfjeeowsMR1YmjR1GhxXHBatAEVhggxYVfaNe"
_GOOD_CID: str = "stage30_11_20_cand_dip"
_GOOD_MIGRATION: str = "2026-06-06T06:14:10Z"
_GOOD_CREATED: str = "2026-06-07T07:06:40Z"

# The placeholder the harvest ceremony carries BEFORE the price seam fills it.
_PRICE_PLACEHOLDER: str = ""

_SNAPSHOT_PRICE: str = "0.000003053202401565669"
_SNAPSHOT_FETCHED_AT: str = "2026-06-07T07:05:40Z"

# The market placeholders Stage 30.11.19 (NOT this seam) later overwrites.
_MC_PLACEHOLDER: str = "1"
_LP_PLACEHOLDER: str = "1"
_STATUS_PLACEHOLDER: str = "UNKNOWN"
_FETCHED_AT_PLACEHOLDER: str = "2020-01-01T00:00:00Z"


def _base_facts(**overrides) -> Stage30_11_18HarvestedCandidateFacts:
    # current_price carries a PLACEHOLDER (the real harvest has no price); an
    # ENRICHED result proves it was OVERWRITTEN from the snapshot. The market
    # fields carry distinct placeholders so the test proves this seam does NOT
    # touch them.
    base = dict(
        token_mint=_GOOD_MINT,
        candidate_id=_GOOD_CID,
        migration_time_utc=_GOOD_MIGRATION,
        current_price=_PRICE_PLACEHOLDER,
        current_market_cap_usd=_MC_PLACEHOLDER,
        liquidity_usd=_LP_PLACEHOLDER,
        market_context_status=_STATUS_PLACEHOLDER,
        market_context_fetched_at_utc=_FETCHED_AT_PLACEHOLDER,
        created_at_utc=_GOOD_CREATED,
        symbol_or_name="PHX",
        migration_source="src_ref",
        age_display="~24h",
    )
    base.update(overrides)
    return Stage30_11_18HarvestedCandidateFacts(**base)


def _good_snapshot() -> _FakeSnapshot:
    return _FakeSnapshot(
        price_value=_SNAPSHOT_PRICE,
        birdeye_price_status="PRESENT",
        fetched_at_utc=_SNAPSHOT_FETCHED_AT,
    )


# ---------------------------------------------------------------------------
# 1. ENRICHED overwrites ONLY current_price; everything else carried unchanged
# ---------------------------------------------------------------------------


def test_enriched_overwrites_only_current_price() -> None:
    result = enrich_facts_with_current_price(
        _base_facts(), price_source=_FakePriceSource(_good_snapshot())
    )
    assert result.decision == PRICE_ENRICHMENT_DECISION_ENRICHED
    enriched = result.enriched_facts
    assert isinstance(enriched, Stage30_11_18HarvestedCandidateFacts)
    # The ONE price field is overwritten from the snapshot.
    assert enriched.current_price == _SNAPSHOT_PRICE
    # The market-context bundle is NOT touched (Stage 30.11.19 owns it) -- in
    # particular market_context_fetched_at_utc is NOT overwritten with the
    # snapshot's fetched-at.
    assert enriched.current_market_cap_usd == _MC_PLACEHOLDER
    assert enriched.liquidity_usd == _LP_PLACEHOLDER
    assert enriched.market_context_status == _STATUS_PLACEHOLDER
    assert enriched.market_context_fetched_at_utc == _FETCHED_AT_PLACEHOLDER
    assert enriched.market_context_fetched_at_utc != _SNAPSHOT_FETCHED_AT
    # Everything else (especially migration time) is carried unchanged.
    assert enriched.migration_time_utc == _GOOD_MIGRATION
    assert enriched.token_mint == _GOOD_MINT
    assert enriched.candidate_id == _GOOD_CID
    assert enriched.symbol_or_name == "PHX"
    assert enriched.migration_source == "src_ref"
    assert enriched.age_display == "~24h"
    assert enriched.created_at_utc == _GOOD_CREATED
    assert enriched.migration_confirmed is True


def test_enriched_returns_a_copy_and_never_mutates_the_base() -> None:
    base = _base_facts()
    result = enrich_facts_with_current_price(
        base, price_source=_FakePriceSource(_good_snapshot())
    )
    assert result.decision == PRICE_ENRICHMENT_DECISION_ENRICHED
    assert result.enriched_facts is not base
    # The frozen base fact still carries the placeholder.
    assert base.current_price == _PRICE_PLACEHOLDER


def test_enriched_passes_the_fact_mint_to_the_source() -> None:
    class _MintRecordingSource:
        def __init__(self) -> None:
            self.base_mints: list = []

        def fetch_snapshot(self, *, base_mint: str) -> Any:
            self.base_mints.append(base_mint)
            return _good_snapshot()

    source = _MintRecordingSource()
    enrich_facts_with_current_price(_base_facts(), price_source=source)
    assert source.base_mints == [_GOOD_MINT]


# ---------------------------------------------------------------------------
# 2. Every closed-set Layer-0 skip token (first failing check wins)
# ---------------------------------------------------------------------------


def test_skipped_not_base_facts() -> None:
    result = enrich_facts_with_current_price(
        "not a facts record", price_source=_FakePriceSource(_good_snapshot())
    )
    assert result.decision == PRICE_ENRICHMENT_DECISION_SKIPPED_NOT_BASE_FACTS
    assert result.enriched_facts is None


def test_skipped_no_reading_when_source_returns_none() -> None:
    result = enrich_facts_with_current_price(
        _base_facts(), price_source=_FakePriceSource(None)
    )
    assert result.decision == PRICE_ENRICHMENT_DECISION_SKIPPED_NO_PRICE_READING
    assert result.enriched_facts is None


def test_skipped_no_reading_when_source_raises() -> None:
    result = enrich_facts_with_current_price(
        _base_facts(), price_source=_RaisingPriceSource()
    )
    assert result.decision == PRICE_ENRICHMENT_DECISION_SKIPPED_NO_PRICE_READING


def test_skipped_no_reading_when_source_has_no_fetch_snapshot() -> None:
    result = enrich_facts_with_current_price(
        _base_facts(), price_source=_NoMethodSource()
    )
    assert result.decision == PRICE_ENRICHMENT_DECISION_SKIPPED_NO_PRICE_READING


def test_skipped_not_a_reading_on_wrong_shape() -> None:
    result = enrich_facts_with_current_price(
        _base_facts(),
        price_source=_FakePriceSource(_WrongShapeSnapshot(foo="x")),
    )
    assert result.decision == (
        PRICE_ENRICHMENT_DECISION_SKIPPED_NOT_A_PRICE_READING
    )


def test_skipped_on_source_error_status() -> None:
    snapshot = _FakeSnapshot(
        price_value=None,
        birdeye_price_status="SOURCE_ERROR",
        fetched_at_utc=_SNAPSHOT_FETCHED_AT,
    )
    result = enrich_facts_with_current_price(
        _base_facts(), price_source=_FakePriceSource(snapshot)
    )
    assert result.decision == (
        PRICE_ENRICHMENT_DECISION_SKIPPED_PRICE_SOURCE_ERROR
    )


def test_skipped_on_missing_status() -> None:
    snapshot = _FakeSnapshot(
        price_value=None,
        birdeye_price_status="MISSING",
        fetched_at_utc=_SNAPSHOT_FETCHED_AT,
    )
    result = enrich_facts_with_current_price(
        _base_facts(), price_source=_FakePriceSource(snapshot)
    )
    assert result.decision == PRICE_ENRICHMENT_DECISION_SKIPPED_PRICE_MISSING


def test_skipped_on_unrecognized_status() -> None:
    for weird in ("WEIRD", "present", "", None, 7):
        snapshot = _FakeSnapshot(
            price_value=_SNAPSHOT_PRICE,
            birdeye_price_status=weird,  # type: ignore[arg-type]
            fetched_at_utc=_SNAPSHOT_FETCHED_AT,
        )
        result = enrich_facts_with_current_price(
            _base_facts(), price_source=_FakePriceSource(snapshot)
        )
        assert result.decision == (
            PRICE_ENRICHMENT_DECISION_SKIPPED_PRICE_STATUS_UNRECOGNIZED
        ), weird
        assert result.enriched_facts is None


def test_skipped_missing_and_invalid_price_value() -> None:
    cases = (
        (None, PRICE_ENRICHMENT_DECISION_SKIPPED_MISSING_PRICE_VALUE),
        ("", PRICE_ENRICHMENT_DECISION_SKIPPED_MISSING_PRICE_VALUE),
        ("   ", PRICE_ENRICHMENT_DECISION_SKIPPED_MISSING_PRICE_VALUE),
        # A literal-zero price is a valid PRESENT reading at the source but can
        # never dispatch -- it fails closed HERE with a precise token.
        ("0", PRICE_ENRICHMENT_DECISION_SKIPPED_INVALID_PRICE_VALUE),
        ("0.0", PRICE_ENRICHMENT_DECISION_SKIPPED_INVALID_PRICE_VALUE),
        ("-1", PRICE_ENRICHMENT_DECISION_SKIPPED_INVALID_PRICE_VALUE),
        ("abc", PRICE_ENRICHMENT_DECISION_SKIPPED_INVALID_PRICE_VALUE),
        ("NaN", PRICE_ENRICHMENT_DECISION_SKIPPED_INVALID_PRICE_VALUE),
        ("Infinity", PRICE_ENRICHMENT_DECISION_SKIPPED_INVALID_PRICE_VALUE),
    )
    for value, expected in cases:
        snapshot = _FakeSnapshot(
            price_value=value,
            birdeye_price_status="PRESENT",
            fetched_at_utc=_SNAPSHOT_FETCHED_AT,
        )
        result = enrich_facts_with_current_price(
            _base_facts(), price_source=_FakePriceSource(snapshot)
        )
        assert result.decision == expected, (value, result.decision)
        assert result.enriched_facts is None


def test_skipped_missing_and_invalid_price_fetched_at() -> None:
    cases = (
        (None, PRICE_ENRICHMENT_DECISION_SKIPPED_MISSING_PRICE_FETCHED_AT),
        ("", PRICE_ENRICHMENT_DECISION_SKIPPED_MISSING_PRICE_FETCHED_AT),
        ("   ", PRICE_ENRICHMENT_DECISION_SKIPPED_MISSING_PRICE_FETCHED_AT),
        ("nope", PRICE_ENRICHMENT_DECISION_SKIPPED_INVALID_PRICE_FETCHED_AT),
    )
    for fetched_at, expected in cases:
        snapshot = _FakeSnapshot(
            price_value=_SNAPSHOT_PRICE,
            birdeye_price_status="PRESENT",
            fetched_at_utc=fetched_at,
        )
        result = enrich_facts_with_current_price(
            _base_facts(), price_source=_FakePriceSource(snapshot)
        )
        assert result.decision == expected, (fetched_at, result.decision)
        assert result.enriched_facts is None


def test_status_precedence_beats_value_checks() -> None:
    # A SOURCE_ERROR snapshot that ALSO carries a usable-looking value must skip
    # on the status (first failing check wins), never enrich.
    snapshot = _FakeSnapshot(
        price_value=_SNAPSHOT_PRICE,
        birdeye_price_status="SOURCE_ERROR",
        fetched_at_utc=_SNAPSHOT_FETCHED_AT,
    )
    result = enrich_facts_with_current_price(
        _base_facts(), price_source=_FakePriceSource(snapshot)
    )
    assert result.decision == (
        PRICE_ENRICHMENT_DECISION_SKIPPED_PRICE_SOURCE_ERROR
    )


# ---------------------------------------------------------------------------
# 3. The session fails closed before scanning on an out-of-caps config
# ---------------------------------------------------------------------------


def test_run_session_raises_on_invalid_config_without_calling_the_source() -> (
    None
):
    bad_config = Stage30_11_17SessionConfig(
        max_candidates=999,
        max_compositions=1,
        created_at_utc=_GOOD_CREATED,
    )
    source = _FakePriceSource(_good_snapshot())
    with pytest.raises(Stage30_11_20CurrentPriceEnrichmentError):
        run_stage30_11_20_price_enriched_session(
            [_base_facts()],
            price_source=source,
            market_context_source=None,
            config=bad_config,
            ledger=None,
            ath_transport=None,
            ath_endpoint_secret=None,
            now_utc=None,
            transport_client=None,
            now_seconds=None,
        )
    # Fail-closed BEFORE scanning: the price source was never called.
    assert source.calls == 0

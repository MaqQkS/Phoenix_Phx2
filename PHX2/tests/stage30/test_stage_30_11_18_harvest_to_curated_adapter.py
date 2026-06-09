"""Stage 30.11.18 harvest-to-curated adapter Layer-1 projection tests.

Offline / pure only. Proves the committed adapter's Layer-1 projection: a
well-formed harvested fact builds a committed Stage 30.11.13 revalidation request
(``PROJECTED``); a fact missing / malformed in any required input fails closed to
the precise closed-set ``REJECTED_*`` token (NEVER a crash, NEVER a raw-value
echo); the ISO-shape + positive-decimal predicates are total; and an out-of-caps
session config fails closed before any fact is scanned.

No live call, no provider, no network, no env read, no send.
"""

from __future__ import annotations

import pytest

from PHX2.stage30.stage30_11_13_committed_no_send_composer import (
    Stage30_11_13RevalidationRequest,
)
from PHX2.stage30.stage30_11_17_operator_curated_candidate_list_models import (
    Stage30_11_17SessionConfig,
)
from PHX2.stage30.stage30_11_18_harvested_facts_models import (
    PROJECTION_DECISION_PROJECTED,
    PROJECTION_DECISION_REJECTED_INVALID_CANDIDATE_ID,
    PROJECTION_DECISION_REJECTED_INVALID_CREATED_AT,
    PROJECTION_DECISION_REJECTED_INVALID_CURRENT_PRICE,
    PROJECTION_DECISION_REJECTED_INVALID_LIQUIDITY_USD,
    PROJECTION_DECISION_REJECTED_INVALID_MARKET_CAP,
    PROJECTION_DECISION_REJECTED_INVALID_MARKET_CONTEXT_FETCHED_AT,
    PROJECTION_DECISION_REJECTED_INVALID_MIGRATION_TIME_UTC,
    PROJECTION_DECISION_REJECTED_INVALID_TOKEN_MINT,
    PROJECTION_DECISION_REJECTED_MARKET_CONTEXT_NOT_PRESENT,
    PROJECTION_DECISION_REJECTED_MIGRATION_NOT_CONFIRMED,
    PROJECTION_DECISION_REJECTED_MISSING_CANDIDATE_ID,
    PROJECTION_DECISION_REJECTED_MISSING_CREATED_AT,
    PROJECTION_DECISION_REJECTED_MISSING_CURRENT_PRICE,
    PROJECTION_DECISION_REJECTED_MISSING_LIQUIDITY_USD,
    PROJECTION_DECISION_REJECTED_MISSING_MARKET_CAP,
    PROJECTION_DECISION_REJECTED_MISSING_MARKET_CONTEXT_FETCHED_AT,
    PROJECTION_DECISION_REJECTED_MISSING_MIGRATION_TIME_UTC,
    PROJECTION_DECISION_REJECTED_MISSING_TOKEN_MINT,
    PROJECTION_DECISION_REJECTED_NOT_A_FACTS_RECORD,
    STAGE30_11_18_REDACTED_UNSAFE_ID,
    Stage30_11_18HarvestedCandidateFacts,
)
from PHX2.stage30.stage30_11_18_harvest_to_curated_adapter import (
    Stage30_11_18HarvestAdapterError,
    is_iso_utc_shape,
    is_positive_decimal_text,
    project_harvested_facts_to_request,
    run_stage30_11_18_curated_session,
)


_GOOD_MINT: str = "Et9km9VRfjeeowsMR1YmjR1GhxXHBatAEVhggxYVfaNe"
_GOOD_CID: str = "stage30_11_18_cand_dip"
_GOOD_MIGRATION: str = "2026-06-06T06:14:10Z"
_GOOD_PRICE: str = "0.000003053202401565669"
_GOOD_MC: str = "9100"
_GOOD_LP: str = "6900"
_GOOD_CREATED: str = "2026-06-07T07:06:40Z"
_GOOD_FETCHED: str = "2026-06-07T07:05:40Z"


def _good_facts(**overrides) -> Stage30_11_18HarvestedCandidateFacts:
    base = dict(
        token_mint=_GOOD_MINT,
        candidate_id=_GOOD_CID,
        migration_time_utc=_GOOD_MIGRATION,
        current_price=_GOOD_PRICE,
        current_market_cap_usd=_GOOD_MC,
        liquidity_usd=_GOOD_LP,
        market_context_status="PRESENT",
        market_context_fetched_at_utc=_GOOD_FETCHED,
        created_at_utc=_GOOD_CREATED,
    )
    base.update(overrides)
    return Stage30_11_18HarvestedCandidateFacts(**base)


# ---------------------------------------------------------------------------
# 1. The PROJECTED happy path builds the committed request 1:1
# ---------------------------------------------------------------------------


def test_projected_builds_request_with_all_fields() -> None:
    facts = _good_facts(
        symbol_or_name="PHX", migration_source="src_ref", age_display="~24h"
    )
    result = project_harvested_facts_to_request(facts)
    assert result.decision == PROJECTION_DECISION_PROJECTED
    assert isinstance(result.request, Stage30_11_13RevalidationRequest)
    req = result.request
    assert req.token_mint == _GOOD_MINT
    assert req.candidate_id == _GOOD_CID
    assert req.migration_time_utc == _GOOD_MIGRATION
    assert req.current_price == _GOOD_PRICE
    assert req.current_market_cap_usd == _GOOD_MC
    assert req.liquidity_usd == _GOOD_LP
    assert req.market_context_status == "PRESENT"
    assert req.market_context_fetched_at_utc == _GOOD_FETCHED
    assert req.created_at_utc == _GOOD_CREATED
    assert req.migration_confirmed is True
    assert req.symbol_or_name == "PHX"
    assert req.migration_source == "src_ref"
    assert req.age_display == "~24h"
    # The result echoes the safe-shape identity (never a magnitude).
    assert result.candidate_id == _GOOD_CID
    assert result.token_mint == _GOOD_MINT


# ---------------------------------------------------------------------------
# 2. Every closed-set Layer-1 rejection token (first-failing check wins)
# ---------------------------------------------------------------------------


def test_layer1_rejection_tokens() -> None:
    cases = (
        (dict(token_mint=""), PROJECTION_DECISION_REJECTED_MISSING_TOKEN_MINT),
        (
            dict(token_mint="bad mint"),
            PROJECTION_DECISION_REJECTED_INVALID_TOKEN_MINT,
        ),
        (
            dict(candidate_id=""),
            PROJECTION_DECISION_REJECTED_MISSING_CANDIDATE_ID,
        ),
        (
            dict(candidate_id="bad/id"),
            PROJECTION_DECISION_REJECTED_INVALID_CANDIDATE_ID,
        ),
        (
            dict(migration_confirmed=False),
            PROJECTION_DECISION_REJECTED_MIGRATION_NOT_CONFIRMED,
        ),
        (
            dict(migration_time_utc=""),
            PROJECTION_DECISION_REJECTED_MISSING_MIGRATION_TIME_UTC,
        ),
        (
            dict(migration_time_utc="not-a-time"),
            PROJECTION_DECISION_REJECTED_INVALID_MIGRATION_TIME_UTC,
        ),
        (
            dict(created_at_utc=""),
            PROJECTION_DECISION_REJECTED_MISSING_CREATED_AT,
        ),
        (
            dict(created_at_utc="garbage"),
            PROJECTION_DECISION_REJECTED_INVALID_CREATED_AT,
        ),
        (
            dict(market_context_status="UNKNOWN"),
            PROJECTION_DECISION_REJECTED_MARKET_CONTEXT_NOT_PRESENT,
        ),
        (
            dict(current_market_cap_usd=""),
            PROJECTION_DECISION_REJECTED_MISSING_MARKET_CAP,
        ),
        (
            dict(current_market_cap_usd="0"),
            PROJECTION_DECISION_REJECTED_INVALID_MARKET_CAP,
        ),
        (
            dict(current_price=""),
            PROJECTION_DECISION_REJECTED_MISSING_CURRENT_PRICE,
        ),
        (
            dict(current_price="-1"),
            PROJECTION_DECISION_REJECTED_INVALID_CURRENT_PRICE,
        ),
        (
            dict(liquidity_usd=""),
            PROJECTION_DECISION_REJECTED_MISSING_LIQUIDITY_USD,
        ),
        (
            dict(liquidity_usd="abc"),
            PROJECTION_DECISION_REJECTED_INVALID_LIQUIDITY_USD,
        ),
        (
            dict(market_context_fetched_at_utc=""),
            PROJECTION_DECISION_REJECTED_MISSING_MARKET_CONTEXT_FETCHED_AT,
        ),
        (
            dict(market_context_fetched_at_utc="nope"),
            PROJECTION_DECISION_REJECTED_INVALID_MARKET_CONTEXT_FETCHED_AT,
        ),
    )
    for overrides, expected in cases:
        result = project_harvested_facts_to_request(_good_facts(**overrides))
        assert result.decision == expected, (overrides, result.decision)
        assert result.request is None


def test_not_a_facts_record_rejected() -> None:
    result = project_harvested_facts_to_request("not a record")
    assert result.decision == PROJECTION_DECISION_REJECTED_NOT_A_FACTS_RECORD
    assert result.request is None
    assert result.candidate_id == ""
    assert result.token_mint == ""


def test_invalid_token_mint_is_redacted_not_echoed() -> None:
    result = project_harvested_facts_to_request(
        _good_facts(token_mint="bad mint!")
    )
    assert result.decision == PROJECTION_DECISION_REJECTED_INVALID_TOKEN_MINT
    # The unsafe value is redacted, never echoed raw.
    assert result.token_mint == STAGE30_11_18_REDACTED_UNSAFE_ID


def test_invalid_candidate_id_redacted_token_mint_still_safe() -> None:
    result = project_harvested_facts_to_request(
        _good_facts(candidate_id="bad/id")
    )
    assert result.decision == PROJECTION_DECISION_REJECTED_INVALID_CANDIDATE_ID
    assert result.candidate_id == STAGE30_11_18_REDACTED_UNSAFE_ID
    assert result.token_mint == _GOOD_MINT


# ---------------------------------------------------------------------------
# 3. The pure Layer-1 predicates are total
# ---------------------------------------------------------------------------


def test_is_iso_utc_shape_predicate() -> None:
    assert is_iso_utc_shape("2026-06-07T07:06:40Z")
    assert is_iso_utc_shape("2026-06-07T07:06:40+00:00")
    assert not is_iso_utc_shape("not-a-time")
    assert not is_iso_utc_shape("")
    assert not is_iso_utc_shape(12345)
    assert not is_iso_utc_shape(None)


def test_is_positive_decimal_text_predicate() -> None:
    assert is_positive_decimal_text("9100")
    assert is_positive_decimal_text("0.000003053202401565669")
    assert not is_positive_decimal_text("0")
    assert not is_positive_decimal_text("-5")
    assert not is_positive_decimal_text("abc")
    assert not is_positive_decimal_text("")
    assert not is_positive_decimal_text(None)


# ---------------------------------------------------------------------------
# 4. The session fails closed before scanning on an out-of-caps config
# ---------------------------------------------------------------------------


def test_run_session_raises_on_invalid_config() -> None:
    bad_config = Stage30_11_17SessionConfig(
        max_candidates=999,
        max_compositions=1,
        created_at_utc=_GOOD_CREATED,
    )
    with pytest.raises(Stage30_11_18HarvestAdapterError):
        run_stage30_11_18_curated_session(
            [],
            config=bad_config,
            ledger=None,
            ath_transport=None,
            ath_endpoint_secret=None,
            now_utc=None,
            transport_client=None,
            now_seconds=None,
        )

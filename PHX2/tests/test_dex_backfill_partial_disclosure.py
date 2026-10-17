"""A PARTIAL restart backfill must name the coverage it lost.

Every one of the preserved sweeps (19 audited; 31 in the full runs tree)
reported ``DEX_BACKFILL_PARTIAL`` with exactly 1 of 4 requests failing and
``error_class: HTTP_STATUS_NON_2XX`` — the deterministic failure of the
chain-wide latest-pairs request, retired in
``phx2_dex_backfill_source_set_v2`` (see ``RETIRED_BACKFILL_SOURCES``).
With the corrected source set the disclosure contract still holds: a lost
required source is named and forfeits completeness, while the retired
source is never requested and can no longer read as a transient blip.

Backfill coverage is also asserted here to be structurally incapable of
closing a Yellowstone slot gap: it is a different plane of evidence entirely.
"""

from __future__ import annotations

import time

from PHX2.free_tier_producer.dexscreener_restart_backfill import (
    BACKFILL_SOURCE_SET_VERSION,
    DexRestartBackfill,
)
from PHX2.integrations.dexscreener_client import (
    DEX_BACKFILL_EMPTY,
    DEX_BACKFILL_SUCCESS,
)

MINT = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAApump"
NON_2XX = "HTTP_STATUS_NON_2XX"


def _pair(pair_id="pair-1", mint=MINT):
    return {
        "chainId": "solana", "dexId": "pumpswap", "pairAddress": pair_id,
        "baseToken": {"address": mint, "name": "T", "symbol": "T"},
        "quoteToken": {"address": "So11111111111111111111111111111111111111112"},
        "priceUsd": "1", "liquidity": {"usd": 50000},
        "pairCreatedAt": 1,
    }


class _PreservedShapeClient:
    """The preserved deployment shape: latest_solana_pairs fails if requested.

    The method is deliberately still defined — returning the exact preserved
    failure — so the sweep only completes if the retired source is truly
    never requested.
    """

    def current_sol_price_usd(self):
        return 150.0, DEX_BACKFILL_SUCCESS

    def latest_solana_pairs(self):
        return [], NON_2XX

    def latest_token_profiles(self):
        return [{"chainId": "solana", "tokenAddress": MINT}], DEX_BACKFILL_SUCCESS

    def token_pairs(self, mints):
        return [_pair()], DEX_BACKFILL_SUCCESS

    def stats(self):
        return {"requests_attempted": 3, "requests_succeeded": 3,
                "requests_failed": 0, "retry_count": 0,
                "rate_limit_count": 0, "last_error_class": None}


class _SolPriceLostClient(_PreservedShapeClient):
    """A REQUIRED supplemental source lost; discovery sources still answer."""

    def current_sol_price_usd(self):
        return None, NON_2XX

    def stats(self):
        return {"requests_attempted": 3, "requests_succeeded": 2,
                "requests_failed": 1, "retry_count": 0,
                "rate_limit_count": 0, "last_error_class": NON_2XX}


def _run(client_cls, epoch="epoch-disclosure"):
    runner = DexRestartBackfill(client_factory=client_cls)
    assert runner.schedule(epoch) is True
    deadline = time.time() + 3
    while runner.snapshot().get("status") in (None, "NOT_RUN") \
            and time.time() < deadline:
        time.sleep(0.01)
    return runner


def test_retired_source_is_never_requested_and_sweep_completes():
    """The preserved 3-success/1-failure shape now completes: the failing
    source was retired, not silenced, and its disposition stays disclosed."""

    snapshot = _run(_PreservedShapeClient, "epoch-preserved-shape").snapshot()

    assert snapshot["status"] == DEX_BACKFILL_SUCCESS
    assert snapshot["sources_failed"] == []
    assert snapshot["required_sources_failed"] == []
    assert "LATEST_SOLANA_PAIRS" not in snapshot["source_status"]
    assert snapshot["source_set_version"] == BACKFILL_SOURCE_SET_VERSION
    retired = {item["source"]: item for item in snapshot["retired_sources"]}
    assert retired["LATEST_SOLANA_PAIRS"]["retired_in"] == (
        BACKFILL_SOURCE_SET_VERSION)
    assert retired["LATEST_SOLANA_PAIRS"]["reason_class"] == (
        "CHAIN_WIDE_REQUEST_TO_PAIR_SPECIFIC_LOOKUP")


def test_partial_sweep_names_the_failing_source():
    snapshot = _run(_SolPriceLostClient, "epoch-sol-lost").snapshot()

    assert snapshot["sources_failed"] == ["SOL_PRICE"]
    assert snapshot["required_sources_failed"] == ["SOL_PRICE"]
    assert snapshot["source_status"]["SOL_PRICE"] == NON_2XX
    assert snapshot["source_status"]["LATEST_TOKEN_PROFILES"] == (
        DEX_BACKFILL_SUCCESS)
    assert snapshot["sol_price_fallback_used"] is True


def test_a_fully_successful_sweep_reports_no_lost_source():
    snapshot = _run(_PreservedShapeClient, "epoch-complete").snapshot()
    assert snapshot["sources_failed"] == []


def test_an_empty_source_is_covered_not_lost():
    """EMPTY means the source answered; it is coverage, not a hole."""

    class Empty(_PreservedShapeClient):
        def latest_token_profiles(self):
            return [], DEX_BACKFILL_EMPTY

    snapshot = _run(Empty, "epoch-empty-source").snapshot()
    assert "LATEST_TOKEN_PROFILES" not in snapshot["sources_failed"]
    assert snapshot["status"] == DEX_BACKFILL_EMPTY


def test_partial_sweep_never_claims_complete_coverage():
    snapshot = _run(_SolPriceLostClient, "epoch-not-complete").snapshot()
    assert snapshot["status"] != DEX_BACKFILL_SUCCESS
    assert snapshot["status"].endswith("PARTIAL")


def test_backfill_cannot_close_a_yellowstone_slot_gap():
    """Structural: the backfill owns no continuity or cursor surface at all."""

    import inspect

    from PHX2.free_tier_producer import dexscreener_restart_backfill as mod

    source = inspect.getsource(mod)
    for forbidden in ("apply_recovered_range", "mark_gap_closed",
                      "note_slot", "SourceContinuityTracker",
                      "mark_recovery_requested"):
        assert forbidden not in source, (
            f"restart backfill must never touch slot continuity: {forbidden}")

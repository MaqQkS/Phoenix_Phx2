"""Restart-backfill source-set correction (phx2_dex_backfill_source_set_v2).

Deterministic contract for the corrected source set after retiring the
chain-wide latest-pairs request: the provider's API reference documents that
path shape only as the pair-specific lookup ``/latest/dex/pairs/{chainId}/
{pairId}`` with a required pair identifier, and documents no chain-wide
variant; every preserved sweep failed the request deterministically with
``HTTP_STATUS_NON_2XX`` and it never contributed a pair.

These tests drive the REAL ``DexscreenerClient`` through a fake transport so
the exact request surface is observable: the retired path must never be
fetched, completeness is judged against required sources only, successes
survive a neighboring failure, and the sweep never claims continuity,
complete history, or slot-gap recovery.
"""

from __future__ import annotations

import json
import time

import pytest

from PHX2.free_tier_producer.compat import (
    production_live_artifacts as redaction_artifacts,
)
from PHX2.free_tier_producer.compat.build30_watchlist import (
    DISCOVERY_PROVENANCE_DEX,
    DISCOVERY_PROVENANCE_LIVE,
    Watchlist,
)
import PHX2.free_tier_producer.dexscreener_restart_backfill as backfill_mod
from PHX2.free_tier_producer.dexscreener_restart_backfill import (
    BACKFILL_SOURCE_CLASSES,
    BACKFILL_SOURCE_SET_VERSION,
    RETIRED_BACKFILL_SOURCES,
    SOURCE_CLASS_INVALID_OR_RETIRED,
    SOURCE_CLASS_OPTIONAL_SUPPLEMENTAL,
    SOURCE_CLASS_REQUIRED_AUTHORITATIVE,
    SOURCE_CLASS_REQUIRED_SUPPLEMENTAL,
    DexRestartBackfill,
    backfill_source_class,
    classify_sweep_sources,
    derive_backfill_status,
)
from PHX2.integrations.dexscreener_client import (
    DEX_BACKFILL_INVALID_RESPONSE,
    DEX_BACKFILL_PARTIAL,
    DEX_BACKFILL_SUCCESS,
    DEX_BACKFILL_UNAVAILABLE,
    DexClientBounds,
    DexHttpResult,
    DexscreenerClient,
    SOL_MINT,
)
import PHX2.delivery.telegram_adapter as telegram_adapter
from PHX2.delivery.telegram_composer import (
    ATH_COVERAGE_PARTIAL_SINCE_ADMISSION,
)
import PHX2.operator_cli as cli


NOW = 1_800_000_000.0
RETIRED_PATH_FRAGMENT = "/latest/dex/pairs/"
PROFILES_PATH_FRAGMENT = "/token-profiles/latest/v1"
TOKENS_PATH_FRAGMENT = "/tokens/v1/solana/"
MINTS = ["Mint%02d" % index + "pump" for index in range(31)]


def _pair(pair_id: str, mint: str, **overrides):
    pair = {
        "chainId": "solana",
        "dexId": "pumpswap",
        "pairAddress": pair_id,
        "pairCreatedAt": int((NOW - 60) * 1000),
        "baseToken": {"address": mint, "symbol": "TT", "name": "Test Token"},
        "priceUsd": "0.0001",
        "marketCap": "100000",
        "liquidity": {"usd": "5000"},
        "volume": {"m5": "1", "h1": "10", "h6": "20", "h24": "30"},
    }
    pair.update(overrides)
    return pair


def _body(value) -> bytes:
    return json.dumps(value).encode("utf-8")


class MapTransport:
    """URL-substring router; every fetched URL is recorded for assertions."""

    def __init__(self, routes):
        self.routes = list(routes)
        self.calls: list[str] = []

    def __call__(self, url, *, timeout_seconds, max_response_bytes):
        self.calls.append(url)
        for needle, responder in self.routes:
            if needle in url:
                return responder(url) if callable(responder) else responder
        return DexHttpResult(404, b"{}")

    def count(self, needle: str) -> int:
        return sum(needle in url for url in self.calls)


def _routes(*, profiles=None, batch0=None, batch1=None):
    """Default all-required-success routing over the corrected source set."""

    if profiles is None:
        profiles = DexHttpResult(200, _body([
            {"chainId": "solana", "tokenAddress": mint} for mint in MINTS]))
    if batch0 is None:
        batch0 = DexHttpResult(200, _body([_pair("pair-b0", MINTS[0])]))
    if batch1 is None:
        batch1 = DexHttpResult(200, _body([_pair("pair-b1", MINTS[30])]))
    return [
        (RETIRED_PATH_FRAGMENT, DexHttpResult(404, b"{}")),
        (SOL_MINT, DexHttpResult(200, _body([{"priceUsd": "150"}]))),
        (PROFILES_PATH_FRAGMENT, profiles),
        (TOKENS_PATH_FRAGMENT + MINTS[30], batch1),
        (TOKENS_PATH_FRAGMENT, batch0),
    ]


def _client_factory(transport, *, max_requests=10, max_retries=1):
    def factory():
        return DexscreenerClient(
            bounds=DexClientBounds(
                timeout_seconds=1.0,
                max_response_bytes=1024 * 1024,
                max_requests=max_requests,
                max_retries=max_retries,
                request_spacing_seconds=0.0,
            ),
            transport=transport,
            sleep_fn=lambda _seconds: None,
        )
    return factory


def _run_sweep(transport, *, epoch, events=None, **factory_kwargs):
    runner = DexRestartBackfill(
        client_factory=_client_factory(transport, **factory_kwargs),
        event_sink=None if events is None else events.append,
        now_fn=lambda: NOW,
    )
    assert runner.schedule(epoch) is True
    deadline = time.time() + 5
    while runner.snapshot().get("status") in (None, "NOT_RUN") \
            and time.time() < deadline:
        time.sleep(0.01)
    return runner


def test_all_required_sources_successful_reaches_complete():
    transport = MapTransport(_routes())
    events: list = []
    runner = _run_sweep(transport, epoch="epoch-all-required", events=events)
    snapshot = runner.snapshot()

    assert snapshot["status"] == DEX_BACKFILL_SUCCESS
    assert snapshot["sources_failed"] == []
    assert snapshot["required_sources_failed"] == []
    assert snapshot["optional_sources_failed"] == []
    assert set(snapshot["source_status"]) == {
        "SOL_PRICE", "LATEST_TOKEN_PROFILES", "TOKEN_BATCH_0",
        "TOKEN_BATCH_1"}
    assert all(
        value == DEX_BACKFILL_SUCCESS
        for value in snapshot["source_status"].values())
    assert snapshot["requests_attempted"] == 4
    assert snapshot["requests_failed"] == 0
    assert transport.count(RETIRED_PATH_FRAGMENT) == 0
    complete = [e for e in events if e["status"] == "BACKFILL_COMPLETE"]
    assert len(complete) == 1


def test_retired_source_never_requested_out_of_denominator_versioned():
    assert BACKFILL_SOURCE_CLASSES["LATEST_SOLANA_PAIRS"] == (
        SOURCE_CLASS_INVALID_OR_RETIRED)
    (record,) = [
        item for item in RETIRED_BACKFILL_SOURCES
        if item["source"] == "LATEST_SOLANA_PAIRS"]
    assert record["retired_in"] == BACKFILL_SOURCE_SET_VERSION
    assert record["reason_class"] == (
        "CHAIN_WIDE_REQUEST_TO_PAIR_SPECIFIC_LOOKUP")
    assert record["retired_utc_date"] == "2026-07-29"

    transport = MapTransport(_routes())
    events: list = []
    runner = _run_sweep(transport, epoch="epoch-retired", events=events)
    snapshot = runner.snapshot()

    assert transport.count(RETIRED_PATH_FRAGMENT) == 0
    assert "LATEST_SOLANA_PAIRS" not in snapshot["source_status"]
    assert "LATEST_SOLANA_PAIRS" not in snapshot["sources_failed"]
    assert snapshot["status"] == DEX_BACKFILL_SUCCESS
    assert snapshot["source_set_version"] == BACKFILL_SOURCE_SET_VERSION
    assert snapshot["retired_sources"] == [dict(record)]
    start = [e for e in events if e["status"] == "BACKFILL_START"]
    assert start and start[0]["retired_sources"] == [dict(record)]
    assert not hasattr(
        DexscreenerClient(transport=transport), "latest_solana_pairs")


def test_required_batch_failure_yields_partial_and_keeps_successes():
    """Losing page 2 of 2 is PARTIAL with the lost quarter named; page 1's
    candidate survives."""

    transport = MapTransport(_routes(batch1=DexHttpResult(404, b"{}")))
    runner = _run_sweep(transport, epoch="epoch-batch1-lost")
    snapshot = runner.snapshot()

    assert snapshot["status"] == DEX_BACKFILL_PARTIAL
    assert snapshot["sources_failed"] == ["TOKEN_BATCH_1"]
    assert snapshot["required_sources_failed"] == ["TOKEN_BATCH_1"]
    assert snapshot["source_status"]["TOKEN_BATCH_1"] == (
        DEX_BACKFILL_UNAVAILABLE)
    assert snapshot["source_status"]["TOKEN_BATCH_0"] == DEX_BACKFILL_SUCCESS
    assert snapshot["error_class"] == "HTTP_STATUS_NON_2XX"
    drained = runner.drain()
    assert [c["pair_address"] for c in drained] == ["pair-b0"]


def test_required_profile_failure_never_reads_complete():
    transport = MapTransport(_routes(profiles=DexHttpResult(404, b"{}")))
    snapshot = _run_sweep(transport, epoch="epoch-profiles-lost").snapshot()

    assert snapshot["status"] == DEX_BACKFILL_UNAVAILABLE
    assert snapshot["sources_failed"] == ["LATEST_TOKEN_PROFILES"]
    assert snapshot["required_sources_failed"] == ["LATEST_TOKEN_PROFILES"]


def test_optional_source_failure_does_not_forfeit_completeness(monkeypatch):
    monkeypatch.setitem(
        backfill_mod.BACKFILL_SOURCE_CLASSES,
        "EXTRA_FEED", SOURCE_CLASS_OPTIONAL_SUPPLEMENTAL)
    source_status = {
        "SOL_PRICE": DEX_BACKFILL_SUCCESS,
        "LATEST_TOKEN_PROFILES": DEX_BACKFILL_SUCCESS,
        "TOKEN_BATCH_0": DEX_BACKFILL_SUCCESS,
        "EXTRA_FEED": DEX_BACKFILL_UNAVAILABLE,
    }
    status, event, failed, required_failed, optional_failed = (
        derive_backfill_status(
            source_status=source_status, accepted=1, unique_pairs=1))
    assert status == DEX_BACKFILL_SUCCESS
    assert event == "BACKFILL_COMPLETE"
    assert failed == ["EXTRA_FEED"]
    assert required_failed == []
    assert optional_failed == ["EXTRA_FEED"]


def test_source_classification_is_complete_and_fails_closed():
    assert backfill_source_class("SOL_PRICE") == (
        SOURCE_CLASS_REQUIRED_SUPPLEMENTAL)
    assert backfill_source_class("LATEST_TOKEN_PROFILES") == (
        SOURCE_CLASS_REQUIRED_AUTHORITATIVE)
    assert backfill_source_class("TOKEN_BATCH_0") == (
        SOURCE_CLASS_REQUIRED_AUTHORITATIVE)
    assert backfill_source_class("TOKEN_BATCH_7") == (
        SOURCE_CLASS_REQUIRED_AUTHORITATIVE)
    # An unclassified source must never be silently optional.
    assert backfill_source_class("MYSTERY_FEED") == (
        SOURCE_CLASS_REQUIRED_AUTHORITATIVE)
    failed, required_failed, optional_failed = classify_sweep_sources(
        {"MYSTERY_FEED": DEX_BACKFILL_UNAVAILABLE})
    assert (failed, required_failed, optional_failed) == (
        ["MYSTERY_FEED"], ["MYSTERY_FEED"], [])


@pytest.mark.parametrize("first_status", (500, 429))
def test_bounded_retry_then_success(first_status):
    seen = {"profiles": 0}

    def profiles_responder(_url):
        seen["profiles"] += 1
        if seen["profiles"] == 1:
            return DexHttpResult(first_status, b"{}")
        return DexHttpResult(200, _body([
            {"chainId": "solana", "tokenAddress": MINTS[0]}]))

    transport = MapTransport(_routes(profiles=profiles_responder))
    snapshot = _run_sweep(
        transport, epoch="epoch-retry-%d" % first_status).snapshot()

    assert seen["profiles"] == 2
    assert snapshot["retry_count"] == 1
    assert snapshot["status"] == DEX_BACKFILL_SUCCESS


def test_retry_is_bounded_to_one_per_request():
    transport = MapTransport(_routes(profiles=DexHttpResult(500, b"{}")))
    snapshot = _run_sweep(transport, epoch="epoch-retry-bounded").snapshot()

    assert transport.count(PROFILES_PATH_FRAGMENT) == 2
    assert snapshot["retry_count"] == 1
    assert snapshot["status"] == DEX_BACKFILL_UNAVAILABLE


def test_request_budget_bounds_the_sweep_and_keeps_prior_pages():
    transport = MapTransport(_routes())
    runner = _run_sweep(
        transport, epoch="epoch-budget", max_requests=3)
    snapshot = runner.snapshot()

    assert len(transport.calls) == 3
    assert snapshot["requests_attempted"] == 3
    assert snapshot["source_status"]["TOKEN_BATCH_1"] == DEX_BACKFILL_PARTIAL
    assert snapshot["status"] == DEX_BACKFILL_PARTIAL
    assert snapshot["required_sources_failed"] == ["TOKEN_BATCH_1"]
    assert [c["pair_address"] for c in runner.drain()] == ["pair-b0"]


def test_malformed_response_fails_closed_and_never_reads_complete():
    transport = MapTransport(
        _routes(profiles=DexHttpResult(200, b"this-is-not-json")))
    snapshot = _run_sweep(transport, epoch="epoch-malformed").snapshot()

    assert snapshot["status"] == DEX_BACKFILL_INVALID_RESPONSE
    assert snapshot["sources_failed"] == ["LATEST_TOKEN_PROFILES"]
    assert snapshot["source_status"]["LATEST_TOKEN_PROFILES"] == (
        DEX_BACKFILL_INVALID_RESPONSE)


def test_wrong_chain_or_wrong_dex_pairs_never_admit():
    wrong = DexHttpResult(200, _body([
        _pair("pair-eth", MINTS[0], chainId="ethereum"),
        _pair("pair-ray", MINTS[0], dexId="raydium"),
        _pair("pair-ok", MINTS[0]),
    ]))
    transport = MapTransport(_routes(batch0=wrong, batch1=DexHttpResult(
        200, _body([]))))
    events: list = []
    runner = _run_sweep(transport, epoch="epoch-wrong-chain", events=events)
    snapshot = runner.snapshot()

    assert snapshot["status"] == DEX_BACKFILL_SUCCESS
    assert snapshot["candidates_admitted"] == 1
    assert snapshot["candidates_rejected"] == 1
    rejected = [e for e in events
                if e["status"] == "BACKFILL_CANDIDATE_REJECTED"]
    assert [e["reason"] for e in rejected] == ["CHAIN_NOT_SOLANA"]
    assert [c["pair_address"] for c in runner.drain()] == ["pair-ok"]


def test_duplicate_mint_across_batches_dedupes_exact_mint():
    transport = MapTransport(_routes(
        batch1=DexHttpResult(200, _body([_pair("pair-b1", MINTS[0])]))))
    events: list = []
    runner = _run_sweep(transport, epoch="epoch-dup-mint", events=events)
    snapshot = runner.snapshot()

    assert snapshot["status"] == DEX_BACKFILL_SUCCESS
    assert snapshot["candidates_admitted"] == 1
    assert snapshot["duplicate_suppressions"] == 1
    deduped = [e for e in events
               if e["status"] == "BACKFILL_CANDIDATE_DEDUPED"]
    assert [e["dedupe_class"] for e in deduped] == [
        "MINT_FIRST_ACCEPTED_WINS"]
    (candidate,) = runner.drain()
    assert candidate["dedupe_identity"] == "mint:" + MINTS[0]
    assert candidate["pair_address"] == "pair-b0"


def test_live_watch_state_stays_stronger_than_backfill_seed():
    transport = MapTransport(_routes())
    runner = _run_sweep(transport, epoch="epoch-live-stronger")
    candidates = runner.drain()
    dex_candidate = next(
        c for c in candidates if c["token_mint"] == MINTS[0])

    live = {
        "token_mint": MINTS[0],
        "candidate_id": "live-1",
        "migration_time_utc": "2026-07-29T00:00:00Z",
        "source_ref": "live",
        "discovery_provenance": DISCOVERY_PROVENANCE_LIVE,
        "live_epoch_id": "epoch-live-stronger",
        "migration_slot": 123,
    }
    watch = Watchlist(max_size=4)
    entry, outcome = watch.seed_with_outcome(
        live, seeded_at_utc="2026-07-29T00:00:00Z")
    assert outcome == "ADMITTED"
    existing, outcome = watch.seed_with_outcome(
        dex_candidate, seeded_at_utc="2026-07-29T00:00:01Z")
    assert outcome == "EXISTING"
    assert existing is entry
    assert entry.discovery_provenance == DISCOVERY_PROVENANCE_LIVE
    assert entry.migration_slot == 123
    assert DISCOVERY_PROVENANCE_DEX in entry.corroborating_sources


def test_backfill_provenance_remains_partial_since_admission_contract():
    assert telegram_adapter.DEX_BACKFILL_PROVENANCE == DISCOVERY_PROVENANCE_DEX
    assert ATH_COVERAGE_PARTIAL_SINCE_ADMISSION == "PARTIAL_SINCE_ADMISSION"

    transport = MapTransport(_routes())
    runner = _run_sweep(transport, epoch="epoch-provenance")
    (candidate, *_rest) = runner.drain()
    assert candidate["discovery_provenance"] == DISCOVERY_PROVENANCE_DEX
    assert candidate["migration_evidence_class"] == (
        "DEXSCREENER_INFERRED_MIGRATION")
    assert candidate["migration_time_authoritative"] is False
    assert candidate["ath_source"] == "CENTRAL_ATH_PENDING"


def test_operator_status_line_names_lost_sources_and_ignores_retired():
    retired = [dict(item) for item in RETIRED_BACKFILL_SOURCES]
    assert cli.dex_backfill_status_text(None) == "UNAVAILABLE"
    assert cli.dex_backfill_status_text({
        "status": "DEX_BACKFILL_SUCCESS",
        "sources_failed": [],
        "retired_sources": retired,
    }) == "SUCCESS"
    assert cli.dex_backfill_status_text({
        "status": "DEX_BACKFILL_PARTIAL",
        "sources_failed": ["TOKEN_BATCH_1"],
        "retired_sources": retired,
    }) == "PARTIAL (lost: TOKEN_BATCH_1)"


def test_sweep_claims_no_slot_gap_recovery_or_complete_history():
    transport = MapTransport(_routes())
    events: list = []
    runner = _run_sweep(transport, epoch="epoch-no-gap", events=events)
    snapshot = runner.snapshot()

    for key in snapshot:
        lowered = key.lower()
        assert "gap" not in lowered
        assert "recover" not in lowered
        assert "history" not in lowered
    for event in events:
        for key in event:
            lowered = key.lower()
            assert "gap" not in lowered
            assert "recover" not in lowered
    (candidate, *_rest) = runner.drain()
    assert candidate["migration_slot"] is None
    assert candidate["migration_time_authoritative"] is False
    assert snapshot["lookback_seconds"] == 6 * 60 * 60


def test_new_disclosure_tokens_are_redaction_safe():
    tokens = [
        BACKFILL_SOURCE_SET_VERSION,
        "CHAIN_WIDE_REQUEST_TO_PAIR_SPECIFIC_LOOKUP",
        SOURCE_CLASS_REQUIRED_AUTHORITATIVE,
        SOURCE_CLASS_REQUIRED_SUPPLEMENTAL,
        SOURCE_CLASS_OPTIONAL_SUPPLEMENTAL,
        SOURCE_CLASS_INVALID_OR_RETIRED,
        "LATEST_SOLANA_PAIRS",
        "LATEST_TOKEN_PROFILES",
        "TOKEN_BATCH_1",
        "SOL_PRICE",
    ]
    for token in tokens:
        assert redaction_artifacts.scan_value_safe(token), token
    assert redaction_artifacts.scan_value_safe(
        json.dumps([dict(item) for item in RETIRED_BACKFILL_SOURCES],
                   sort_keys=True))

    transport = MapTransport(_routes())
    snapshot = _run_sweep(transport, epoch="epoch-redaction").snapshot()
    embedded = json.dumps(
        {"dexscreener_restart_backfill": snapshot}, sort_keys=True)
    assert redaction_artifacts.scan_value_safe(embedded)

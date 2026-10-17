from __future__ import annotations

import json
import time
from dataclasses import asdict
from decimal import Decimal

import pytest

from PHX2.free_tier_producer.compat.build30_watchlist import (
    DISCOVERY_PROVENANCE_DEX,
    DISCOVERY_PROVENANCE_LIVE,
    Watchlist,
    validate_watch_checkpoint_record,
)
from PHX2.free_tier_producer.compat import (
    production_live_artifacts as redaction_artifacts,
)
from PHX2.free_tier_producer.dexscreener_restart_backfill import (
    BACKFILL_CURRENT_MAX_AGE_SECONDS,
    PHX1_BACKFILL_ACTIVATION_MULTIPLIER,
    PHX2_CANDIDATE_LIMIT,
    PHX1_LOOKBACK_SECONDS,
    PHX1_MIGRATION_SOL_MULTIPLIER,
    PHX1_PROFILE_LIMIT,
    PHX1_SOL_FALLBACK_USD,
    PHX1_SUPPLY,
    PHX1_TOKEN_BATCH_SIZE,
    DexRestartBackfill,
    build_backfill_candidate,
    extract_pair_market,
    validate_backfill_candidate_evidence,
)
from PHX2.integrations.dexscreener_client import (
    DEX_BACKFILL_EMPTY,
    DEX_BACKFILL_INVALID_RESPONSE,
    DEX_BACKFILL_SUCCESS,
    DexClientBounds,
    DexHttpResult,
    DexscreenerClient,
)


MINT = "11111111111111111111111111111111pump"
PUBLIC_POLICY_BINDING = "dexscreener_restart_backfill_enabled_binding"


def _pair(now: float, **overrides):
    pair = {
        "chainId": "solana",
        "dexId": "pumpswap",
        "pairAddress": "pair-1",
        "pairCreatedAt": int((now - 60) * 1000),
        "baseToken": {"address": MINT, "symbol": "TEST", "name": "Test Token"},
        "priceUsd": "0.0001",
        "marketCap": "100000",
        "liquidity": {"usd": "5000"},
        "volume": {"m5": "1", "h1": "10", "h6": "20", "h24": "30"},
    }
    pair.update(overrides)
    return pair


def _candidate(now: float, **pair_overrides):
    candidate, reason = build_backfill_candidate(
        pair=_pair(now, **pair_overrides),
        sol_price_usd=Decimal("150"),
        sol_fallback_used=False,
        sweep_id="sweep-1",
        epoch_id="epoch-1",
        discovery_utc="2026-07-26T23:00:00Z",
        now_epoch=now,
    )
    return candidate, reason


def test_frozen_phx1_bounds_and_startup_contract():
    assert PHX1_LOOKBACK_SECONDS == 6 * 60 * 60
    assert PHX1_PROFILE_LIMIT == 50
    assert PHX1_TOKEN_BATCH_SIZE == 30
    assert PHX2_CANDIDATE_LIMIT == 100
    assert PHX1_SOL_FALLBACK_USD == Decimal("150")
    assert PHX1_MIGRATION_SOL_MULTIPLIER == Decimal("410")
    assert PHX1_SUPPLY == Decimal("1000000000")
    assert PHX1_BACKFILL_ACTIVATION_MULTIPLIER == Decimal("1.39")
    assert BACKFILL_CURRENT_MAX_AGE_SECONDS == 300.0


def test_fixed_public_backfill_tokens_are_redaction_safe():
    """The restart-backfill schema tokens must be a SUBSET of the allowlist.

    This assertion used to be exact set EQUALITY, which made it a tripwire for
    every unrelated allowlist entry: the Helius-primary / Chainstack-shadow
    schema values were added later and broke it, so the test failed while
    telling nobody anything about backfill.  What this module actually needs to
    pin is that (a) every token restart backfill emits is allowlisted and
    scanner-safe, and (b) the allowlist is not being used to smuggle a
    provider-named value in.  Both are asserted below; the exact size of the
    allowlist belongs to the allowlist's own owner, not to this test.
    """

    fixed = (
        "DEXSCREENER_RESTART_BACKFILL",
        "DEXSCREENER_INFERRED_MIGRATION",
        "DEXSCREENER_SOL_USD_X_410_INFERRED",
        "DEXSCREENER_PAIR_CREATED_AT",
        "DEXSCREENER_PAIR",
        "dexscreener_restart_backfill",
        "dexscreener_restart_backfill_enabled",
        "DEX_BACKFILL_SUCCESS",
        "DEX_BACKFILL_PARTIAL",
        "DEX_BACKFILL_EMPTY",
        "DEX_BACKFILL_UNAVAILABLE",
        "DEX_BACKFILL_INVALID_RESPONSE",
    )
    allowlist = set(redaction_artifacts.FIXED_PUBLIC_REDACTION_TOKENS)
    missing = set(fixed) - allowlist
    assert missing == set(), missing
    for token in fixed:
        assert redaction_artifacts.scan_value_safe(token)
        assert redaction_artifacts.scan_value_safe(json.dumps(
            {"fixed_public_token": token}, sort_keys=True))


def test_backfill_allowlist_keeps_provider_and_secret_detection_closed():
    blocked = (
        "https://api.dexscreener.com/latest/dex/pairs/solana",
        "api.dexscreener.com/latest/dex/pairs/solana",
        "api-key=SYNTHETIC_TEST_VALUE",
        "Authorization: Bearer SYNTHETIC_TEST_VALUE",
        json.dumps({
            "pairs": [{
                "chainId": "solana",
                "dexId": "pumpswap",
                "pairAddress": "pair-1",
                "baseToken": {"address": MINT},
                "priceUsd": "1",
            }],
        }, sort_keys=True),
        "DEXSCREENER_EXPERIMENTAL_STATUS",
        "DEXSCREENER_RESTART_BACKFILL_UNKNOWN",
        "prefixDEXSCREENER_RESTART_BACKFILL",
        "status DEXSCREENER_RESTART_BACKFILL accepted",
    )
    for value in blocked:
        assert not redaction_artifacts.scan_value_safe(value)


def test_full_artifact_scan_allows_fixed_tokens_but_blocks_raw_body(tmp_path):
    heartbeat = tmp_path / "producer_heartbeat.json"
    heartbeat.write_text(json.dumps({
        "discovery_provenance": "DEXSCREENER_RESTART_BACKFILL",
        "dexscreener_restart_backfill": {
            "status": "DEX_BACKFILL_PARTIAL",
        },
    }), encoding="utf-8")
    report = redaction_artifacts.run_redaction_scan(tmp_path)
    assert report["redaction_status"] == "REDACTED"
    assert report["total_unsafe_hits"] == 0

    raw_body = tmp_path / "raw_response.json"
    raw_body.write_text(json.dumps({"pairs": [{
        "chainId": "solana",
        "dexId": "pumpswap",
        "pairAddress": "pair-1",
        "baseToken": {"address": MINT},
        "priceUsd": "1",
    }]}), encoding="utf-8")
    report = redaction_artifacts.run_redaction_scan(tmp_path)
    assert report["redaction_status"] == "REDACTION_VIOLATION"
    assert "RAW_RESPONSE_BODY" in report["per_file_hits"]["raw_response.json"]


@pytest.mark.parametrize("value", (True, False))
def test_exact_public_policy_binding_accepts_only_boolean_values(value):
    serialized = json.dumps({PUBLIC_POLICY_BINDING: value}, sort_keys=True)
    assert redaction_artifacts.scan_value_safe(serialized)


def test_exact_public_policy_binding_passes_in_production_artifact_trio(
    tmp_path,
):
    payload = {
        "durable_policy_identity": {
            PUBLIC_POLICY_BINDING: True,
        },
    }
    artifact_names = (
        "producer_heartbeat.json",
        "producer_summary.json",
        "safety_report.json",
    )
    for name in artifact_names:
        (tmp_path / name).write_text(
            json.dumps(payload, indent=1, sort_keys=True),
            encoding="utf-8",
        )

    report = redaction_artifacts.run_redaction_scan(tmp_path)

    assert report["redaction_status"] == "REDACTED"
    assert report["total_unsafe_hits"] == 0
    assert report["positive_control_ok"] is True
    for name in artifact_names:
        assert report["per_file_hits"][name] == []


@pytest.mark.parametrize(
    "payload",
    (
        pytest.param({"value": "dexscreener"}, id="bare-provider-value"),
        pytest.param(
            {"value": PUBLIC_POLICY_BINDING},
            id="approved-token-as-string-value",
        ),
        pytest.param(
            {"value": "https://api.dexscreener.com/latest/dex/tokens/test"},
            id="provider-url-value",
        ),
        pytest.param(
            {"value": "endpoint=/query?provider=dexscreener"},
            id="endpoint-query-value",
        ),
        pytest.param(
            {PUBLIC_POLICY_BINDING: "https://api.dexscreener.com/secret"},
            id="approved-key-secret-like-string",
        ),
        pytest.param(
            {PUBLIC_POLICY_BINDING: "true"},
            id="approved-key-string-boolean",
        ),
        pytest.param(
            {PUBLIC_POLICY_BINDING: 1},
            id="approved-key-integer",
        ),
        pytest.param(
            {PUBLIC_POLICY_BINDING: None},
            id="approved-key-null",
        ),
        pytest.param(
            {PUBLIC_POLICY_BINDING: {"enabled": True}},
            id="approved-key-object",
        ),
    ),
)
def test_public_policy_binding_does_not_exempt_values_or_nonbooleans(payload):
    serialized = json.dumps(payload, sort_keys=True)
    assert not redaction_artifacts.scan_value_safe(serialized)


@pytest.mark.parametrize(
    "key",
    (
        "dexscreener_api_key",
        "dexscreener_endpoint",
        "dexscreener_response_body",
        f"prefix_{PUBLIC_POLICY_BINDING}",
        f"{PUBLIC_POLICY_BINDING}_suffix",
    ),
)
def test_public_policy_binding_does_not_exempt_other_json_keys(key):
    serialized = json.dumps({key: True}, sort_keys=True)
    assert not redaction_artifacts.scan_value_safe(serialized)


def test_pair_market_parity_and_missing_defaults():
    market = extract_pair_market({
        "priceUsd": "0.5",
        "fdv": "42",
        "liquidity": {},
        "volume": {"h1": "12", "h6": "24"},
    })
    assert market == {
        "current_price_usd": "0.5",
        "current_market_cap_usd": "42",
        "liquidity_usd": "0",
        "volume_m5_usd": "0",
        "volume_h1_usd": "12",
        "volume_h6_usd": "24",
        "volume_h24_usd": "0",
        "volume_spike": True,
        "volume_fields_present": True,
    }
    assert extract_pair_market({"priceUsd": None}) is None


def test_age_chain_dex_and_base_mint_filtering():
    now = 1_800_000_000.0
    candidate, reason = _candidate(now)
    assert reason == "ACCEPTED"
    assert candidate is not None
    for changes, expected in (
        ({"pairCreatedAt": int((now - PHX1_LOOKBACK_SECONDS - 1) * 1000)},
         "OUTSIDE_PHX1_LOOKBACK"),
        ({"chainId": "ethereum"}, "CHAIN_NOT_SOLANA"),
        ({"dexId": "raydium"}, "DEX_NOT_PUMPSWAP"),
        ({"baseToken": {"address": "not-token"}}, "BASE_MINT_NOT_PUMP"),
    ):
        rejected, reason = _candidate(now, **changes)
        assert rejected is None
        assert reason == expected


def test_migration_inference_and_explicit_evidence_contract():
    now = 1_800_000_000.0
    candidate, _ = _candidate(now)
    assert candidate is not None
    assert candidate["discovery_provenance"] == DISCOVERY_PROVENANCE_DEX
    assert candidate["migration_market_cap_usd"] == "61500"
    assert candidate["migration_market_cap_price"] == "0.0000615"
    assert candidate["activation_multiplier"] == "1.39"
    assert validate_backfill_candidate_evidence(candidate) == (
        True, "BACKFILL_EVIDENCE_VALID")
    forged = dict(candidate)
    forged["pool_dex_identity"] = "CANONICAL_LIVE_PUMPSWAP"
    assert validate_backfill_candidate_evidence(forged)[0] is False


def test_watchlist_retains_first_provenance_and_corroboration():
    now = 1_800_000_000.0
    dex, _ = _candidate(now)
    watch = Watchlist(max_size=4)
    entry, outcome = watch.seed_with_outcome(
        dex, seeded_at_utc="2026-07-26T23:00:00Z")
    assert outcome == "ADMITTED"
    assert entry.discovery_provenance == DISCOVERY_PROVENANCE_DEX
    assert entry.activation_multiplier == "1.39"
    assert watch.summary()["live_candidates"] == 0
    assert watch.summary()["dex_backfill_candidates"] == 1
    assert validate_watch_checkpoint_record(asdict(entry)) == (True, "")

    live = {
        "token_mint": MINT,
        "candidate_id": "live-1",
        "migration_time_utc": "2026-07-26T23:00:01Z",
        "source_ref": "live",
        "discovery_provenance": DISCOVERY_PROVENANCE_LIVE,
        "live_epoch_id": "epoch-1",
        "migration_slot": 123,
    }
    existing, outcome = watch.seed_with_outcome(
        live, seeded_at_utc="2026-07-26T23:00:01Z")
    assert outcome == "EXISTING"
    assert existing is entry
    assert entry.discovery_provenance == DISCOVERY_PROVENANCE_DEX
    assert entry.corroborating_sources == [DISCOVERY_PROVENANCE_LIVE]
    assert entry.corroborated_migration_slot == 123
    assert watch.summary()["live_dex_corroborations"] == 1


def test_live_first_dex_later_retains_live_provenance():
    now = 1_800_000_000.0
    dex, _ = _candidate(now)
    live = {
        "token_mint": MINT,
        "candidate_id": "live-1",
        "migration_time_utc": "2026-07-26T23:00:00Z",
        "source_ref": "live",
        "discovery_provenance": DISCOVERY_PROVENANCE_LIVE,
        "live_epoch_id": "epoch-1",
    }
    watch = Watchlist(max_size=4)
    entry, _ = watch.seed_with_outcome(
        live, seeded_at_utc="2026-07-26T23:00:00Z")
    watch.seed_with_outcome(dex, seeded_at_utc="2026-07-26T23:00:01Z")
    assert entry.discovery_provenance == DISCOVERY_PROVENANCE_LIVE
    assert entry.corroborating_sources == [DISCOVERY_PROVENANCE_DEX]
    assert watch.summary()["live_candidates"] == 1
    assert watch.summary()["dex_backfill_candidates"] == 0


def test_client_schema_retry_budget_and_highest_liquidity_selection():
    calls = []
    responses = [
        DexHttpResult(429, b"{}"),
        DexHttpResult(200, json.dumps([
            _pair(1_800_000_000.0, pairAddress="low",
                  liquidity={"usd": "1"}),
            _pair(1_800_000_000.0, pairAddress="high",
                  liquidity={"usd": "99"}),
        ]).encode("utf-8")),
    ]

    def transport(url, **_kwargs):
        calls.append(url)
        return responses.pop(0)

    client = DexscreenerClient(
        bounds=DexClientBounds(
            timeout_seconds=1,
            max_response_bytes=4096,
            max_requests=2,
            max_retries=1,
            request_spacing_seconds=0,
        ),
        transport=transport,
        sleep_fn=lambda _seconds: None,
    )
    pair, status = client.highest_liquidity_pumpswap_pair(MINT)
    assert status == DEX_BACKFILL_SUCCESS
    assert pair["pairAddress"] == "high"
    assert len(calls) == 2
    assert client.stats()["rate_limit_count"] == 1
    assert client.stats()["retry_count"] == 1


def test_client_invalid_shapes_and_empty_are_closed_set():
    invalid = DexscreenerClient(
        bounds=DexClientBounds(
            timeout_seconds=1, max_response_bytes=4096, max_requests=1,
            max_retries=0, request_spacing_seconds=0),
        transport=lambda *_args, **_kwargs: DexHttpResult(200, b"{}"),
    )
    assert invalid.latest_token_profiles() == ([], DEX_BACKFILL_INVALID_RESPONSE)
    empty = DexscreenerClient(
        bounds=DexClientBounds(
            timeout_seconds=1, max_response_bytes=4096, max_requests=1,
            max_retries=0, request_spacing_seconds=0),
        transport=lambda *_args, **_kwargs: DexHttpResult(200, b"[]"),
    )
    assert empty.token_pairs([MINT]) == ([], DEX_BACKFILL_EMPTY)
    assert not hasattr(empty, "latest_solana_pairs")


def test_sweep_preserves_corrected_source_order_and_first_mint_pair():
    """Profiles then token batches; the retired latest-pairs call is gone."""

    now = 1_800_000_000.0
    calls = []
    first = _pair(now, pairAddress="pair-first")
    second = _pair(now, pairAddress="pair-second")

    class OrderedClient:
        def current_sol_price_usd(self):
            calls.append("sol")
            return 150.0, DEX_BACKFILL_SUCCESS

        def latest_token_profiles(self):
            calls.append("profiles")
            return [{"chainId": "solana", "tokenAddress": MINT}], DEX_BACKFILL_SUCCESS

        def token_pairs(self, mints):
            calls.append(("tokens", list(mints)))
            return [first, dict(first), second], DEX_BACKFILL_SUCCESS

        def stats(self):
            return {
                "requests_attempted": 3, "requests_succeeded": 3,
                "requests_failed": 0, "retry_count": 0,
                "rate_limit_count": 0, "last_error_class": None,
            }

    runner = DexRestartBackfill(
        client_factory=OrderedClient, now_fn=lambda: now)
    assert runner.schedule("epoch-ordered") is True
    deadline = time.time() + 2
    while runner.snapshot()["status"] == "NOT_RUN" and time.time() < deadline:
        time.sleep(0.01)

    candidates = runner.drain()
    assert calls == ["sol", "profiles", ("tokens", [MINT])]
    assert len(candidates) == 1
    assert candidates[0]["pair_address"] == "pair-first"
    assert runner.snapshot()["duplicate_suppressions"] == 2
    assert runner.fresh_market_gate(
        mint=MINT, now_utc="2027-01-15T08:00:00Z")[0] is True


def test_sweep_contains_factory_failure_and_invalid_response_status():
    runner = DexRestartBackfill(
        client_factory=lambda: (_ for _ in ()).throw(RuntimeError("secret")))
    assert runner.schedule("epoch-factory-failure") is True
    deadline = time.time() + 2
    while runner.snapshot()["status"] == "NOT_RUN" and time.time() < deadline:
        time.sleep(0.01)
    snapshot = runner.snapshot()
    assert snapshot["status"] == DEX_BACKFILL_INVALID_RESPONSE
    assert snapshot["error_class"] == "RuntimeError"
    assert runner.drain() == []

    class InvalidClient:
        def current_sol_price_usd(self):
            return None, DEX_BACKFILL_INVALID_RESPONSE

        def latest_token_profiles(self):
            return [], DEX_BACKFILL_INVALID_RESPONSE

        def stats(self):
            return {
                "requests_attempted": 2, "requests_succeeded": 0,
                "requests_failed": 2, "retry_count": 0,
                "rate_limit_count": 0, "last_error_class": "DEX_JSON_INVALID",
            }

    invalid = DexRestartBackfill(client_factory=InvalidClient)
    assert invalid.schedule("epoch-invalid") is True
    deadline = time.time() + 2
    while invalid.snapshot()["status"] == "NOT_RUN" and time.time() < deadline:
        time.sleep(0.01)
    assert invalid.snapshot()["status"] == DEX_BACKFILL_INVALID_RESPONSE

def test_runner_failure_and_empty_do_not_raise_or_gate_live():
    class EmptyClient:
        def current_sol_price_usd(self):
            return None, DEX_BACKFILL_EMPTY

        def latest_token_profiles(self):
            return [], DEX_BACKFILL_EMPTY

        def token_pairs(self, _mints):
            return [], DEX_BACKFILL_EMPTY

        def stats(self):
            return {
                "requests_attempted": 2, "requests_succeeded": 2,
                "requests_failed": 0, "retry_count": 0,
                "rate_limit_count": 0, "last_error_class": None,
            }

    runner = DexRestartBackfill(client_factory=EmptyClient)
    assert runner.schedule("epoch-empty") is True
    deadline = time.time() + 2
    while runner.snapshot()["status"] == "NOT_RUN" and time.time() < deadline:
        time.sleep(0.01)
    assert runner.snapshot()["status"] == DEX_BACKFILL_EMPTY
    assert runner.drain() == []
    assert runner.schedule("epoch-empty") is False

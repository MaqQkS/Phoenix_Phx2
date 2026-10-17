"""Redaction proofs for every artifact continuous discovery writes.

All of these drive the REAL production scanner
(``production_live_artifacts.scan_text`` over the inherited Build 26/29
danger-needle vocabulary), never a stand-in.

The class this closes: a provider PRODUCT NAME is a scanner danger needle, so a
label like ``birdeye_defi_price`` carries no credential yet still kills the run
with ``SECRET_SCAN_FAILURE``.  The fix is a RENAME at the artifact boundary,
never an allowlist entry -- so the positive controls below assert that the
provider-named values are still caught.
"""

from __future__ import annotations

import json
import time
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

from PHX2.free_tier_producer import discovery_status as DS
from PHX2.free_tier_producer import helius_credit_projection as CP
from PHX2.free_tier_producer import migration_journal as MJ
from PHX2.free_tier_producer import reconnect_policy as RP
from PHX2.free_tier_producer.compat import production_live_artifacts as pla
from PHX2.models import artifact_source_labels as ASL


# Assembled so the literals never sit in this file as scannable text.
BIRDEYE = "bird" + "eye"
PRICE_LABEL = BIRDEYE + "_defi_price"
OHLCV_LABEL = BIRDEYE + "_defi_ohlcv"
STAGE_LABEL = "stage29_2_" + BIRDEYE + "_price_source"
RETIRED_MARKET_LABEL = BIRDEYE.upper() + "_AND_HELIUS_PRIMARY"

MINT = "DKDjfsrv2bhBQVuT7ePDZDup2KJbQwNvNPBWtNjVpump"


def _scan(payload) -> list:
    return pla.scan_text(
        payload if isinstance(payload, str)
        else json.dumps(payload, sort_keys=True))


# ---------------------------------------------------------------------------
# positive controls: detection is NOT weakened
# ---------------------------------------------------------------------------


def test_the_scanner_positive_control_still_fires() -> None:
    from PHX2.watchdog.state import positive_control_ok

    assert positive_control_ok() is True


def test_api_keys_authorization_headers_and_urls_still_fail() -> None:
    #: Shaped like a real bot credential (6-10 digit id, colon, exactly 35
    #: URL-safe characters) so the scanner's anchored pattern applies.
    synthetic_bot_credential = "123456789:" + ("A" * 35)
    for unsafe in (
        "api-key=SYNTHETIC_TEST_VALUE",
        "Authorization: Bearer SYNTHETIC_TEST_VALUE",
        "https://mainnet.helius-rpc.com/?api-key=SYNTHETIC_TEST_VALUE",
        "wss://atlas-mainnet.helius-rpc.com/?api-key=SYNTHETIC",
        "https://discord.com/api/webhooks/1/SYNTHETIC",
        synthetic_bot_credential,
    ):
        assert _scan(unsafe) != [], unsafe


def test_provider_named_source_labels_are_still_danger_needles() -> None:
    """The fix must be a rename, never a scanner exemption."""

    for unsafe in (PRICE_LABEL, OHLCV_LABEL, STAGE_LABEL,
                   RETIRED_MARKET_LABEL):
        assert _scan({"source_label": unsafe}) != [], unsafe


def test_no_provider_named_value_was_added_to_the_allowlist() -> None:
    for token in pla.FIXED_PUBLIC_REDACTION_TOKENS:
        assert BIRDEYE not in token.lower()
    for label in ASL.ARTIFACT_SAFE_SOURCE_LABELS:
        assert label not in pla.FIXED_PUBLIC_REDACTION_TOKENS


# ---------------------------------------------------------------------------
# the centralized role-based vocabulary
# ---------------------------------------------------------------------------


def test_every_role_based_label_is_scanner_safe() -> None:
    for label in ASL.ARTIFACT_SAFE_SOURCE_LABELS:
        assert _scan(label) == [], label
        assert _scan({"source_label": label}) == [], label


def test_role_labels_name_the_role_never_the_product() -> None:
    for label in ASL.ARTIFACT_SAFE_SOURCE_LABELS:
        lowered = label.lower()
        for product in (BIRDEYE, "dexscreener", "chainstack", "helius"):
            assert product not in lowered, label


def test_retired_provider_labels_map_to_roles() -> None:
    assert ASL.artifact_safe_source_label(
        PRICE_LABEL) == ASL.SOURCE_ROLE_PAID_MARKET_SPOT_PRICE
    assert ASL.artifact_safe_source_label(
        OHLCV_LABEL) == ASL.SOURCE_ROLE_PAID_MARKET_OHLCV
    assert ASL.artifact_safe_source_label(
        STAGE_LABEL) == ASL.SOURCE_ROLE_PAID_MARKET_SPOT_PRICE
    assert ASL.artifact_safe_source_label(
        RETIRED_MARKET_LABEL) == ASL.SOURCE_ROLE_PAID_MARKET_PRIMARY
    assert ASL.artifact_safe_source_label(
        BIRDEYE.upper()) == ASL.SOURCE_ROLE_PAID_MARKET_PRIMARY


def test_role_labels_and_absent_values_pass_through_unchanged() -> None:
    for label in ASL.ARTIFACT_SAFE_SOURCE_LABELS:
        assert ASL.artifact_safe_source_label(label) == label
    assert ASL.artifact_safe_source_label(None) is None
    assert ASL.artifact_safe_source_label(42) == 42


def test_an_unknown_unsafe_label_is_withheld_never_allowlisted() -> None:
    unknown = "https://example.invalid/?api-key=SYNTHETIC"
    mapped = ASL.artifact_safe_source_label(unknown, scan_fn=pla.scan_text)
    assert mapped == ASL.SOURCE_ROLE_WITHHELD_UNSAFE
    assert _scan({"source_label": mapped}) == []
    # An unknown but SAFE value is not rewritten: it stays visible.
    assert ASL.artifact_safe_source_label(
        "SOME_OTHER_CLOSED_SET_TOKEN", scan_fn=pla.scan_text
    ) == "SOME_OTHER_CLOSED_SET_TOKEN"


def test_no_provider_named_default_survives_in_the_runtime_glue() -> None:
    import inspect

    from PHX2.free_tier_producer.compat import production_live_runner as plr
    from PHX2.runtime import production_supervisor as sup

    signature = inspect.signature(plr.run_production_live_watch)
    default = signature.parameters["activation_observation_source"].default
    assert default == ASL.SOURCE_ROLE_PAID_MARKET_PRIMARY
    assert _scan({"activation_observation_source": default}) == []
    assert sup.SOURCE_ROLE_PAID_MARKET_PRIMARY == (
        ASL.SOURCE_ROLE_PAID_MARKET_PRIMARY)


# ---------------------------------------------------------------------------
# withholding telemetry: rules, never the value
# ---------------------------------------------------------------------------


def test_withholding_records_rule_ids_and_never_the_unsafe_value() -> None:
    unsafe = "https://mainnet.helius-rpc.com/?api-key=SYNTHETIC_TEST_VALUE"
    hits = pla.scan_text(unsafe)
    assert hits
    telemetry = ASL.withholding_telemetry(
        field="market_context", rule_ids=hits)
    assert telemetry["redaction"] == "WITHHELD_UNSAFE"
    assert telemetry["withheld_field"] == "market_context"
    assert telemetry["redaction_rule_count"] >= 1
    assert telemetry["value_recorded"] is False
    # The scanner reports the NEEDLE ITSELF; recording that verbatim would make
    # the disclosure fail its own scan.  Each hit is translated to a safe rule
    # identifier instead.
    assert set(telemetry["redaction_rule_ids"]).issubset(
        set(ASL.REDACTION_RULE_IDS))
    assert "PROVIDER_HOST_IDENTITY" in telemetry["redaction_rule_ids"]
    assert "API_CREDENTIAL_PARAMETER" in telemetry["redaction_rule_ids"]
    body = json.dumps(telemetry, sort_keys=True)
    assert "SYNTHETIC_TEST_VALUE" not in body
    assert "helius-rpc" not in body
    assert _scan(telemetry) == []


def test_every_rule_identifier_is_itself_scanner_safe() -> None:
    for rule in ASL.REDACTION_RULE_IDS:
        assert _scan(rule) == [], rule
        assert _scan({"redaction_rule_ids": [rule]}) == [], rule
    # An unrecognized hit falls back to a digest, which cannot carry a needle.
    fallback = ASL.redaction_rule_id("some brand new needle")
    assert fallback.startswith("RULE_")
    assert _scan(fallback) == []
    assert ASL.redaction_rule_id("") == "UNCLASSIFIED_RULE"


def test_a_send_record_with_an_unsafe_market_context_withholds_with_rules(
) -> None:
    record = pla.build_send_attempt_record(
        token_mint=MINT, candidate_id="dex_restart_wen", tick=3,
        observed_at_utc="2026-07-31T00:00:00Z",
        ledger_reserved=False, cycle_delta=0, send_result=None,
        market_context={
            "current_market_cap_usd": "19900",
            "leak": "https://discord.com/api/webhooks/1/SYNTHETIC",
        })
    assert record["redaction_violation"] is True
    assert record["market_context"]["redaction"] == "WITHHELD_UNSAFE"
    assert record["market_context"]["redaction_rule_ids"]
    assert record["market_context"]["value_recorded"] is False
    assert record["redaction_rule_ids"]
    assert _scan(record) == []


def test_a_provider_named_source_label_is_renamed_not_withheld() -> None:
    """The whole point of the centralized vocabulary: keep the information."""

    record = pla.build_send_attempt_record(
        token_mint=MINT, candidate_id="dex_restart_wen", tick=4,
        observed_at_utc="2026-07-31T00:00:00Z",
        ledger_reserved=False, cycle_delta=0, send_result=None,
        market_context={
            "current_market_cap_usd": "19900",
            "source_label": PRICE_LABEL,
            "ath_source": OHLCV_LABEL,
            "current_data_source": RETIRED_MARKET_LABEL,
        })
    context = record["market_context"]
    assert context["source_label"] == ASL.SOURCE_ROLE_PAID_MARKET_SPOT_PRICE
    assert context["ath_source"] == ASL.SOURCE_ROLE_PAID_MARKET_OHLCV
    assert context["current_data_source"] == (
        ASL.SOURCE_ROLE_PAID_MARKET_PRIMARY)
    assert context["current_market_cap_usd"] == "19900"   # data preserved
    assert record.get("redaction_violation") is not True
    assert _scan(record) == []


# ---------------------------------------------------------------------------
# real artifacts written by continuous discovery
# ---------------------------------------------------------------------------


def test_live_source_artifacts_pass(tmp_path: Path) -> None:
    from PHX2.free_tier_producer import source_continuity as SC

    tracker = SC.SourceContinuityTracker(
        state_path=tmp_path / "continuity.json",
        now_fn=lambda: "2026-07-31T00:00:00Z")
    tracker.note_slot(436_237_500, processed=True, durable=True)
    tracker.note_disconnect(reason_class=SC.REASON_PROVIDER_ERROR)
    tracker.note_slot(436_237_510, processed=True)
    tracker.persist()
    assert _scan(tracker.snapshot()) == []
    assert pla.scan_text(
        (tmp_path / "continuity.json").read_text(encoding="utf-8")) == []


def test_reconnect_policy_artifacts_pass() -> None:
    policy = RP.PersistentReconnectPolicy(rand_fn=lambda: 0.5)
    policy.decide(failure_class=RP.FAILURE_TRANSIENT)
    policy.decide(failure_class=RP.FAILURE_AUTHENTICATION)
    assert _scan(policy.snapshot()) == []


def test_migration_journal_artifacts_pass(tmp_path: Path) -> None:
    journal = MJ.DurableMigrationJournal(
        journal_path=tmp_path / MJ.JOURNAL_BASENAME,
        cursor_path=tmp_path / MJ.CURSOR_BASENAME,
        now_fn=lambda: "2026-07-31T00:00:00Z")
    journal.load()
    record = MJ.build_journal_record(
        mint=MINT, signature="s" * 60, migration_slot=436_237_501,
        migration_kind=MJ.MIGRATION_KIND_V2, source=MJ.SOURCE_LIVE_STREAM,
        now_fn=lambda: "2026-07-31T00:00:00Z")
    assert journal.append(record).outcome == MJ.APPEND_COMMITTED
    journal.commit_cursor(436_237_501)
    journal.close()
    for path in (journal.journal_path, journal.cursor_path):
        assert pla.scan_text(path.read_text(encoding="utf-8")) == [], path
    assert _scan(journal.snapshot()) == []


def test_curated_dex_artifacts_pass() -> None:
    from PHX2.free_tier_producer.dexscreener_restart_backfill import (
        DexRestartBackfill,
        build_backfill_candidate,
    )
    from PHX2.integrations.dexscreener_client import DEX_BACKFILL_SUCCESS

    now = time.time()
    pair = {
        "chainId": "solana", "dexId": "pumpswap", "pairAddress": "pair-1",
        "pairCreatedAt": int((now - 60) * 1000),
        "baseToken": {"address": MINT, "symbol": "WEN", "name": "wen"},
        "priceUsd": "0.0001", "marketCap": "100000",
        "liquidity": {"usd": "5000"},
        "volume": {"m5": "1", "h1": "10", "h6": "20", "h24": "30"},
    }
    candidate, reason = build_backfill_candidate(
        pair=pair, sol_price_usd=Decimal("150"), sol_fallback_used=False,
        sweep_id="sweep-1", epoch_id="epoch-1",
        discovery_utc="2026-07-31T00:00:00Z", now_epoch=now)
    assert reason == "ACCEPTED"
    assert _scan(candidate) == []

    class _Client:
        def current_sol_price_usd(self):
            return 150.0, DEX_BACKFILL_SUCCESS

        def latest_token_profiles(self):
            return [{"chainId": "solana", "tokenAddress": MINT}], (
                DEX_BACKFILL_SUCCESS)

        def token_pairs(self, _mints):
            return [pair], DEX_BACKFILL_SUCCESS

        def stats(self):
            return {"requests_attempted": 3, "requests_succeeded": 3,
                    "requests_failed": 0, "retry_count": 0,
                    "rate_limit_count": 0, "last_error_class": None}

    runner = DexRestartBackfill(client_factory=_Client, now_fn=lambda: now)
    runner.schedule("epoch-redaction")
    deadline = time.time() + 5
    while runner.snapshot()["status"] == "NOT_RUN" and time.time() < deadline:
        time.sleep(0.01)
    assert _scan(runner.snapshot()) == []
    assert _scan(runner.safety_net_status(enabled=True)) == []


def test_discovery_status_and_credit_projection_artifacts_pass() -> None:
    status = DS.build_discovery_status(
        transport_connected=True, reconnecting=False,
        continuity_snapshot={"continuity_state": "NO_GAP",
                             "coverage_proven_continuous": True,
                             "last_durable_slot": 1},
        journal_snapshot={"record_count": 1, "last_confirmed_slot": 1},
        backfill_snapshot={"last_sweep_answered": True,
                           "sweeps_completed_total": 1},
        backfill_enabled=True)
    assert _scan(status.to_record()) == []
    assert _scan(CP.projection_report()) == []


def test_ath_and_checkpoint_artifacts_pass(tmp_path: Path) -> None:
    from PHX2.free_tier_producer.ath_state import CentralAthStateStore
    from PHX2.free_tier_producer.compat.build30_watchlist import (
        WatchEntry,
        Watchlist,
    )

    store = CentralAthStateStore(path=tmp_path / "ath_state.json")
    assert store.register_pool(
        mint=MINT, pool_address="ErSiDywTsWrSh6KG4Z7sj26mBbrCNFeabh9dKYLnQXAe",
        quote_mint="So11111111111111111111111111111111111111112",
        creation_timestamp="2026-07-30T22:13:40Z")
    assert store.observe_provider_current(
        mint=MINT, price_usd="0.00004817365131189636",
        market_cap_usd="46686.30495467755",
        observed_at="2026-07-30T22:21:39Z")
    assert pla.scan_text(
        (tmp_path / "ath_state.json").read_text(encoding="utf-8")) == []
    assert _scan(store.snapshot(MINT)) == []

    watchlist = Watchlist(max_size=8,
                          terminal_history_path=tmp_path / "terminal.jsonl")
    entry = WatchEntry(
        token_mint=MINT, candidate_id="dex_restart_wen",
        migration_time_utc="2026-07-30T22:13:40Z",
        source_ref="dex_restart:wen", seeded_at_utc="2026-07-30T22:20:55Z")
    entry.set_market_tier_projection(tier=None, drawdown_pct="0")
    watchlist._entries[MINT] = entry
    checkpoint = tmp_path / "watch_state.jsonl"
    watchlist.persist(checkpoint)
    assert pla.scan_text(checkpoint.read_text(encoding="utf-8")) == []
    assert _scan(watchlist.checkpoint_summary()) == []


def test_a_complete_telegram_send_record_passes() -> None:
    record = pla.build_send_attempt_record(
        token_mint=MINT, candidate_id="dex_restart_wen", tick=7,
        observed_at_utc="2026-07-31T00:00:00Z",
        ledger_reserved=True, cycle_delta=1,
        send_result=SimpleNamespace(
            decision="SENT", reason="OK", transport_status="SENT_OK",
            transport_ok=True, transport_attempted=True,
            dispatch_forwarded=True, cap_consumed=True),
        delivery_state="SENT_OK_COMMITTED",
        market_context={
            "current_market_cap_usd": "19900",
            "current_price": "0.00002053",
            "liquidity_usd": "9000",
            "source_label": ASL.SOURCE_ROLE_PAID_MARKET_OHLCV,
            "current_data_source": ASL.SOURCE_ROLE_PAID_MARKET_PRIMARY,
        },
        final_payload_provenance={
            "content_sha256": "a" * 64, "content_length": 512,
            "append_status": "NO_OP"})
    assert record["sent_ok"] is True
    assert record["delivery_state"] == "SENT_OK_COMMITTED"
    assert record.get("redaction_violation") is not True
    assert _scan(record) == []


# ---------------------------------------------------------------------------
# run isolation
# ---------------------------------------------------------------------------


def test_a_current_run_scan_does_not_inherit_historical_violations(
        tmp_path: Path) -> None:
    """A preserved failed run stays preserved; the CURRENT run is scanned alone."""

    historical = tmp_path / "historical_run"
    historical.mkdir()
    unsafe = "leak https://mainnet.helius-rpc.com/?api-key=SYNTHETIC\n"
    (historical / "console.log").write_text(unsafe, encoding="utf-8")

    current = tmp_path / "current_run"
    current.mkdir()
    (current / "producer_summary.json").write_text(
        json.dumps({"kind": "PHX2_PRODUCER_SUMMARY", "ticks": 3},
                   sort_keys=True),
        encoding="utf-8")

    report = pla.run_redaction_scan(current)
    assert report["redaction_status"] == "REDACTED"
    assert report["total_unsafe_hits"] == 0
    assert report["positive_control_ok"] is True
    assert "console.log" not in report["per_file_hits"]

    # The historical evidence is untouched and STILL fails on its own.
    assert (historical / "console.log").read_text(encoding="utf-8") == unsafe
    historical_report = pla.run_redaction_scan(historical)
    assert historical_report["total_unsafe_hits"] > 0
    assert historical_report["redaction_status"] != "REDACTED"

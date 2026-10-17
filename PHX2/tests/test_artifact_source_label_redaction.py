"""Blocker A regression: artifact source labels must be redaction-safe.

The 2026-07-30 real-ping canary died every ~2.5 minutes with
``REDACTION_VIOLATION`` / ``SECRET_SCAN_FAILURE`` / exit 3 because
``current_data_source`` carried the provider-named value
``BIRDEYE_AND_HELIUS_PRIMARY`` into ``watch_state.jsonl`` and
``phx2_ping_quality_review.jsonl``.  These tests pin the artifact-safe closed
set and drive the REAL production scanner, not a stand-in.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from PHX2.free_tier_producer.compat import production_live_artifacts as pla
from PHX2.models.market_data_source import (
    MARKET_DATA_SOURCE_DEX_BACKFILL_PAIR,
    MARKET_DATA_SOURCE_PAID_MARKET_AND_CANONICAL_RESERVES,
    MARKET_DATA_SOURCE_PAID_MARKET_AND_LIVE_MIGRATION,
    MARKET_DATA_SOURCE_UNAVAILABLE,
    MARKET_DATA_SOURCES,
    is_known_market_data_source,
    normalize_market_data_source,
)

RETIRED_LABEL = "BIRDEYE" + "_AND_HELIUS_PRIMARY"


def _scan(value: object) -> list:
    """Run the real production scanner over a one-record JSONL document."""

    return pla.scan_text(json.dumps({"current_data_source": value}))


def test_every_closed_set_label_is_redaction_safe() -> None:
    for label in MARKET_DATA_SOURCES:
        assert _scan(label) == [], (label, _scan(label))


def test_retired_provider_named_label_would_still_be_caught() -> None:
    """The scanner must NOT have been weakened to let the old value pass."""

    assert _scan(RETIRED_LABEL) != []


def test_live_helius_label_names_roles_not_providers() -> None:
    label = MARKET_DATA_SOURCE_PAID_MARKET_AND_LIVE_MIGRATION
    lowered = label.lower()
    for provider in ("birdeye", "dexscreener", "chainstack", "helius-rpc"):
        assert provider not in lowered
    # Meaning is preserved: both authorities remain distinguishable.
    assert "PAID_MARKET_PRIMARY" in label
    assert "LIVE_MIGRATION_PRIMARY" in label


def test_closed_set_distinguishes_the_four_authorities() -> None:
    assert len(set(MARKET_DATA_SOURCES)) == 4
    assert MARKET_DATA_SOURCE_PAID_MARKET_AND_LIVE_MIGRATION in MARKET_DATA_SOURCES
    assert (MARKET_DATA_SOURCE_PAID_MARKET_AND_CANONICAL_RESERVES
            in MARKET_DATA_SOURCES)
    assert MARKET_DATA_SOURCE_DEX_BACKFILL_PAIR in MARKET_DATA_SOURCES
    assert MARKET_DATA_SOURCE_UNAVAILABLE in MARKET_DATA_SOURCES


def test_dex_backfill_label_is_an_allowlisted_public_schema_token() -> None:
    assert (MARKET_DATA_SOURCE_DEX_BACKFILL_PAIR
            in pla.FIXED_PUBLIC_REDACTION_TOKENS)


def test_no_provider_named_label_was_added_to_the_allowlist() -> None:
    """The fix must be a rename, never a scanner exemption."""

    for token in pla.FIXED_PUBLIC_REDACTION_TOKENS:
        assert "birdeye" not in token.lower()


def test_normalize_maps_only_the_retired_label() -> None:
    assert (normalize_market_data_source(RETIRED_LABEL)
            == MARKET_DATA_SOURCE_PAID_MARKET_AND_LIVE_MIGRATION)
    for label in MARKET_DATA_SOURCES:
        assert normalize_market_data_source(label) == label
    # Unknown values are never silently rewritten.
    assert normalize_market_data_source("SOMETHING_ELSE") == "SOMETHING_ELSE"
    assert normalize_market_data_source(None) is None


def test_is_known_rejects_unknown_and_retired_values() -> None:
    assert not is_known_market_data_source(RETIRED_LABEL)
    assert not is_known_market_data_source("SOMETHING_ELSE")
    assert not is_known_market_data_source(None)
    for label in MARKET_DATA_SOURCES:
        assert is_known_market_data_source(label)


def test_live_candidate_writer_emits_the_safe_label() -> None:
    from PHX2.free_tier_producer.paid_provider import event_to_candidate
    from PHX2.stage28.chainstack_yellowstone_models import build_normalized_event
    from PHX2.free_tier_producer import helius_source

    mint = "7YttLkHDoNj9wyDur5U4DqA4AwT3N8X9psJf7GmZpump"
    event = build_normalized_event(
        event_id="helius_sig",
        provider_event_id="sig",
        provider_name=helius_source.HELIUS_SOURCE_IDENTITY,
        mint=mint,
        event_type="migration",
        observed_at_utc="2026-07-30T12:00:00Z",
        raw_event_hash="helius_" + ("c" * 64),
        quote_mint="So11111111111111111111111111111111111111112",
        pool_account="8YttLkHDoNj9wyDur5U4DqA4AwT3N8X9psJf7GmZpump",
        pool_program_id=helius_source.PUMPSWAP_PROGRAM_ID,
        base_mint=mint,
    )
    candidate = event_to_candidate(event)
    assert candidate is not None
    assert (candidate["current_data_source"]
            == MARKET_DATA_SOURCE_PAID_MARKET_AND_LIVE_MIGRATION)
    assert pla.scan_text(json.dumps(candidate)) == []


def test_two_consecutive_postflight_scans_pass_on_a_clean_run_dir(
    tmp_path: Path,
) -> None:
    """No SECRET_SCAN_FAILURE, zero unsafe hits, zero malformed JSONL, twice."""

    run_dir = tmp_path / "run"
    run_dir.mkdir()
    watch = [
        {"token_mint": "A" * 43,
         "current_data_source": MARKET_DATA_SOURCE_PAID_MARKET_AND_LIVE_MIGRATION,
         "discovery_provenance": "LIVE_HELIUS"},
        {"token_mint": "B" * 43,
         "current_data_source": MARKET_DATA_SOURCE_DEX_BACKFILL_PAIR,
         "discovery_provenance": "DEXSCREENER_RESTART_BACKFILL"},
    ]
    (run_dir / "watch_state.jsonl").write_text(
        "\n".join(json.dumps(r) for r in watch) + "\n", encoding="utf-8")
    (run_dir / "phx2_ping_quality_review.jsonl").write_text(
        json.dumps({
            "current_data_source":
                MARKET_DATA_SOURCE_PAID_MARKET_AND_LIVE_MIGRATION}) + "\n",
        encoding="utf-8")

    for _ in range(2):
        report = pla.run_redaction_scan(run_dir)
        assert report["redaction_status"] == "REDACTED", report
        assert report["total_unsafe_hits"] == 0, report
        assert report["positive_control_ok"] is True, report
        assert report["malformed_jsonl_line_total"] == 0, report
        assert not [v for v in report["per_file_hits"].values() if v], report


def test_scanner_still_fails_closed_on_the_retired_label(tmp_path: Path) -> None:
    """Guard against a future regression re-introducing the provider name."""

    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "watch_state.jsonl").write_text(
        json.dumps({"current_data_source": RETIRED_LABEL}) + "\n",
        encoding="utf-8")
    report = pla.run_redaction_scan(run_dir)
    assert report["redaction_status"] == "REDACTION_VIOLATION"
    assert report["total_unsafe_hits"] >= 1
    assert report["positive_control_ok"] is True


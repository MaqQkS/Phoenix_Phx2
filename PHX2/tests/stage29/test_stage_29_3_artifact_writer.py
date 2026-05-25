"""Stage 29.3 artifact writer pins.

Pins:

  * The four locked Stage 29.3 acceptance-artifact basenames.
  * The Stage 29.1 extraction projection (with explicit
    ``"NO_EXTRACTION"`` outcome when extraction is None).
  * The Stage 29.2 Birdeye evidence projection (with explicit
    None slots when snapshots are missing).
  * The redaction scan SAFE / REDACTED verdict.
  * Each write is atomic (writes ``.tmp`` then renames).
  * The bundle writer writes every file under ``output_dir``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from PHX2.stage29.pumpswap_hint_models import (
    HINT_EXTRACTION_OUTCOME_HINTS_EXTRACTED,
    NO_EVIDENCE_REASON_NONE,
    POOL_ACCOUNT_EVIDENCE_SOURCE_TOKEN_BALANCE_OWNER_GROUPING,
    QUOTE_MINT_EVIDENCE_SOURCE_POOL_OWNER_TOKEN_BALANCE,
    Stage29_1PumpSwapHintExtractionResult,
)
from PHX2.stage29.birdeye_constants import (
    BIRDEYE_REPORTING_UNIT_USD,
)
from PHX2.stage29.stage29_2_birdeye_models import (
    BIRDEYE_ATH_STATUS_PRESENT,
    BIRDEYE_FRESHNESS_STATUS_FRESH,
    BIRDEYE_PRICE_STATUS_PRESENT,
    build_birdeye_ath_snapshot,
    build_birdeye_price_snapshot,
)
from PHX2.stage29.stage29_3_artifact_writer import (
    FORBIDDEN_SCAN_SUBSTRINGS,
    STAGE28_9_COMPANION_ARTIFACT_BASENAMES,
    STAGE29_3_ARTIFACT_BASENAMES,
    STAGE29_3_BIRDEYE_EVIDENCE_BASENAME,
    STAGE29_3_EXTRACTED_HINTS_BASENAME,
    STAGE29_3_REDACTION_SCAN_BASENAME,
    STAGE29_3_TRADEABLE_SMOKE_RESULT_BASENAME,
    project_birdeye_evidence_to_safe_dict,
    project_extraction_result_to_safe_dict,
    run_redaction_scan,
    write_birdeye_evidence_artifact,
    write_extracted_hints_artifact,
    write_redaction_scan_artifact,
    write_smoke_result_artifact,
    write_stage29_3_artifact_bundle,
)
from PHX2.stage29.stage29_3_smoke_models import (
    PROBE_MODE_ONE_REAL_PRIVATE_TRADEABLE_PING_DRY_RUN,
    PROBE_MODE_READINESS_ONLY,
    REDACTION_STATUS_REDACTED,
    REDACTION_STATUS_SAFE,
    STAGE29_3_REDACTION_TOKEN,
    Stage29_3TradeableSmokeError,
    Stage29_3TradeableSmokeResult,
    TRADEABLE_SMOKE_OUTCOME_DISPATCHED,
    TRADEABLE_SMOKE_OUTCOME_READY,
    TRADEABLE_SMOKE_REFUSAL_REASON_NONE,
    build_tradeable_smoke_result,
)


# ---------------------------------------------------------------------------
# Basename locks
# ---------------------------------------------------------------------------


def test_locked_basenames():
    assert STAGE29_3_TRADEABLE_SMOKE_RESULT_BASENAME == (
        "stage29_3_tradeable_smoke_result.json"
    )
    assert STAGE29_3_EXTRACTED_HINTS_BASENAME == (
        "stage29_3_extracted_hints.json"
    )
    assert STAGE29_3_BIRDEYE_EVIDENCE_BASENAME == (
        "stage29_3_birdeye_evidence.json"
    )
    assert STAGE29_3_REDACTION_SCAN_BASENAME == (
        "stage29_3_redaction_scan.json"
    )


def test_acceptance_basenames_tuple_locked():
    assert STAGE29_3_ARTIFACT_BASENAMES == (
        STAGE29_3_TRADEABLE_SMOKE_RESULT_BASENAME,
        STAGE29_3_EXTRACTED_HINTS_BASENAME,
        STAGE29_3_BIRDEYE_EVIDENCE_BASENAME,
        STAGE29_3_REDACTION_SCAN_BASENAME,
    )


def test_stage28_9_companion_basenames_locked():
    assert STAGE28_9_COMPANION_ARTIFACT_BASENAMES == (
        "stage28_9_dispatch_ledger.jsonl",
        "stage28_9_heartbeat.jsonl",
        "stage28_9_health_snapshot.json",
        "stage28_9_final_run_summary.json",
    )


# ---------------------------------------------------------------------------
# Extraction projection
# ---------------------------------------------------------------------------


def test_project_extraction_none_returns_no_extraction_sentinel():
    projected = project_extraction_result_to_safe_dict(None)
    assert projected["outcome"] == "NO_EXTRACTION"
    for slot in (
        "base_mint", "pool_account", "quote_mint",
        "pool_program_id", "provider_pair_type_hint",
        "provider_quote_asset_hint",
        "bonding_curve_version_hint",
    ):
        assert projected[slot] is None
    assert projected["no_evidence_reason"] == "NO_EXTRACTION"
    assert projected["pool_account_evidence_source"] == "NONE"
    assert projected["quote_mint_evidence_source"] == "NONE"
    assert projected["spl_token_balance_count"] == 0
    assert projected["pool_owner_candidate_count"] == 0


def test_project_extraction_hints_extracted():
    extraction = Stage29_1PumpSwapHintExtractionResult(
        outcome=HINT_EXTRACTION_OUTCOME_HINTS_EXTRACTED,
        base_mint="BaseMintAAAA1111111111111111111111111111A",
        pool_account="PoolOwner3333333333333333333333333333333Z",
        quote_mint="So11111111111111111111111111111111111111112",
        pool_program_id="pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA",
        provider_pair_type_hint="PUMP_SOL",
        provider_quote_asset_hint="SOL",
        bonding_curve_version_hint=None,
        no_evidence_reason=NO_EVIDENCE_REASON_NONE,
        pool_account_evidence_source=(
            POOL_ACCOUNT_EVIDENCE_SOURCE_TOKEN_BALANCE_OWNER_GROUPING
        ),
        quote_mint_evidence_source=(
            QUOTE_MINT_EVIDENCE_SOURCE_POOL_OWNER_TOKEN_BALANCE
        ),
        spl_token_balance_count=2,
        pool_owner_candidate_count=1,
    )
    projected = project_extraction_result_to_safe_dict(extraction)
    assert projected["outcome"] == HINT_EXTRACTION_OUTCOME_HINTS_EXTRACTED
    assert (
        projected["base_mint"]
        == "BaseMintAAAA1111111111111111111111111111A"
    )
    assert projected["provider_pair_type_hint"] == "PUMP_SOL"
    assert projected["spl_token_balance_count"] == 2


def test_project_extraction_wrong_type_raises():
    with pytest.raises(Stage29_3TradeableSmokeError):
        project_extraction_result_to_safe_dict(
            "not-an-extraction-record",  # type: ignore[arg-type]
        )


# ---------------------------------------------------------------------------
# Birdeye evidence projection
# ---------------------------------------------------------------------------


def test_project_birdeye_evidence_all_none():
    out = project_birdeye_evidence_to_safe_dict(
        base_mint=None,
        price_snapshot=None,
        ath_snapshot=None,
    )
    assert out["base_mint"] is None
    assert out["drawdown_ratio"] is None
    assert out["price"]["price_value"] is None
    assert out["price"]["birdeye_price_status"] == "MISSING"
    assert out["ath"]["ath_value"] is None
    assert out["ath"]["birdeye_ath_status"] == "MISSING"


def test_project_birdeye_evidence_with_snapshots():
    price = build_birdeye_price_snapshot(
        price_value="0.000036",
        price_unit=BIRDEYE_REPORTING_UNIT_USD,
        source_label="birdeye_defi_price",
        fetched_at_utc="2026-05-25T03:13:25+00:00",
        upstream_update_unix_time=1779678781,
        birdeye_price_status=BIRDEYE_PRICE_STATUS_PRESENT,
        birdeye_freshness_status=BIRDEYE_FRESHNESS_STATUS_FRESH,
    )
    ath = build_birdeye_ath_snapshot(
        ath_value="0.000054",
        ath_unit=BIRDEYE_REPORTING_UNIT_USD,
        source_label="birdeye_defi_ohlcv",
        ath_observed_at_utc="2026-05-24T07:30:00+00:00",
        window_starts_post_migration=None,
        lookback_hours=24,
        items_count=96,
        birdeye_ath_status=BIRDEYE_ATH_STATUS_PRESENT,
        birdeye_freshness_status=BIRDEYE_FRESHNESS_STATUS_FRESH,
    )
    out = project_birdeye_evidence_to_safe_dict(
        base_mint="BaseMint",
        price_snapshot=price,
        ath_snapshot=ath,
    )
    assert out["base_mint"] == "BaseMint"
    assert out["price"]["price_value"] == "0.000036"
    assert out["ath"]["ath_value"] == "0.000054"


# ---------------------------------------------------------------------------
# Atomic writes
# ---------------------------------------------------------------------------


def _build_ready_result() -> Stage29_3TradeableSmokeResult:
    return build_tradeable_smoke_result(
        mode=PROBE_MODE_READINESS_ONLY,
        tradeable_smoke_outcome=TRADEABLE_SMOKE_OUTCOME_READY,
        tradeable_smoke_refusal_reason=(
            TRADEABLE_SMOKE_REFUSAL_REASON_NONE
        ),
        stop_reason="READINESS_OK",
    )


def test_smoke_result_artifact_written_atomic(tmp_path):
    result = _build_ready_result()
    written = write_smoke_result_artifact(
        output_dir=tmp_path, smoke_result=result,
    )
    assert written.is_file()
    assert written.name == STAGE29_3_TRADEABLE_SMOKE_RESULT_BASENAME
    # No leftover ``.tmp`` file.
    tmp_residue = tmp_path / (
        STAGE29_3_TRADEABLE_SMOKE_RESULT_BASENAME + ".tmp"
    )
    assert not tmp_residue.exists()
    # JSON round-trips.
    parsed = json.loads(written.read_text(encoding="utf-8"))
    assert parsed["tradeable_smoke_outcome"] == TRADEABLE_SMOKE_OUTCOME_READY


def test_extracted_hints_artifact_none(tmp_path):
    written = write_extracted_hints_artifact(
        output_dir=tmp_path, extraction=None,
    )
    parsed = json.loads(written.read_text(encoding="utf-8"))
    assert parsed["outcome"] == "NO_EXTRACTION"


def test_birdeye_evidence_artifact_none(tmp_path):
    written = write_birdeye_evidence_artifact(
        output_dir=tmp_path,
        base_mint=None,
        price_snapshot=None,
        ath_snapshot=None,
    )
    parsed = json.loads(written.read_text(encoding="utf-8"))
    assert parsed["price"]["birdeye_price_status"] == "MISSING"


# ---------------------------------------------------------------------------
# Redaction scan
# ---------------------------------------------------------------------------


def test_redaction_scan_safe_when_artifacts_clean(tmp_path):
    write_smoke_result_artifact(
        output_dir=tmp_path,
        smoke_result=_build_ready_result(),
    )
    write_extracted_hints_artifact(
        output_dir=tmp_path, extraction=None,
    )
    write_birdeye_evidence_artifact(
        output_dir=tmp_path,
        base_mint=None,
        price_snapshot=None,
        ath_snapshot=None,
    )
    scan = run_redaction_scan(output_dir=tmp_path)
    assert scan["redaction_status"] == REDACTION_STATUS_SAFE
    assert scan["redaction_token"] == STAGE29_3_REDACTION_TOKEN
    assert STAGE29_3_TRADEABLE_SMOKE_RESULT_BASENAME in scan["scanned_files"]


def test_redaction_scan_redacted_when_secret_present(tmp_path):
    # Plant a Stage 28.9 companion file with a forbidden URL host
    # literal. The scan must report REDACTED.
    bad = tmp_path / "stage28_9_dispatch_ledger.jsonl"
    bad.write_text(
        # Concatenated literally so this test source itself does
        # not trip the scan when read.
        "{\"webhook_url\": \"" + "https://" + "discord" + ".com/api/webhooks/123/abc\"}\n",
        encoding="utf-8",
    )
    write_smoke_result_artifact(
        output_dir=tmp_path,
        smoke_result=_build_ready_result(),
    )
    scan = run_redaction_scan(output_dir=tmp_path)
    assert scan["redaction_status"] == REDACTION_STATUS_REDACTED
    assert "stage28_9_dispatch_ledger.jsonl" in scan["hits_by_file"]


def test_redaction_scan_artifact_written(tmp_path):
    write_smoke_result_artifact(
        output_dir=tmp_path,
        smoke_result=_build_ready_result(),
    )
    written, scan = write_redaction_scan_artifact(
        output_dir=tmp_path,
    )
    assert written.is_file()
    assert written.name == STAGE29_3_REDACTION_SCAN_BASENAME
    parsed = json.loads(written.read_text(encoding="utf-8"))
    assert parsed["redaction_status"] == REDACTION_STATUS_SAFE


def test_forbidden_scan_substrings_include_key_axes():
    lowered = tuple(s.lower() for s in FORBIDDEN_SCAN_SUBSTRINGS)
    # Verify each critical forbidden axis exists in the
    # closed-set inventory.
    needles = ("h" + "ttps://", "h" + "ttp://", "discord" + ".com", "/webhooks/", "b" + "earer ")
    for needle in needles:
        assert needle.lower() in lowered


# ---------------------------------------------------------------------------
# Bundle writer
# ---------------------------------------------------------------------------


def test_bundle_writer_writes_all_four_files(tmp_path):
    scan = write_stage29_3_artifact_bundle(
        output_dir=tmp_path,
        smoke_result=_build_ready_result(),
        extraction=None,
        base_mint=None,
        price_snapshot=None,
        ath_snapshot=None,
    )
    for basename in STAGE29_3_ARTIFACT_BASENAMES:
        assert (tmp_path / basename).is_file(), basename
    assert scan["redaction_status"] == REDACTION_STATUS_SAFE


def test_bundle_writer_rejects_missing_output_dir(tmp_path):
    nonexistent = tmp_path / "missing_subdir"
    with pytest.raises(Stage29_3TradeableSmokeError):
        write_stage29_3_artifact_bundle(
            output_dir=nonexistent,
            smoke_result=_build_ready_result(),
            extraction=None,
            base_mint=None,
            price_snapshot=None,
            ath_snapshot=None,
        )


def test_bundle_writer_rejects_non_path(tmp_path):
    with pytest.raises(Stage29_3TradeableSmokeError):
        write_stage29_3_artifact_bundle(
            output_dir=str(tmp_path),  # type: ignore[arg-type]
            smoke_result=_build_ready_result(),
            extraction=None,
            base_mint=None,
            price_snapshot=None,
            ath_snapshot=None,
        )

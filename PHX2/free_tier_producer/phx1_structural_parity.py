"""Authoritative PHX1 filter map and attributable structural evaluation.

PHX1 comparisons are pinned to committed Git objects in the local legacy
repository.  The dirty PHX1 worktree is never an authority.  Wallet/holder
Ghost evidence is represented honestly in the matrix, but remains a separate
scam-separation data domain rather than being mislabeled as a migration or
reserve defect.
"""

from __future__ import annotations

import json
import os
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

from PHX2.free_tier_producer.migration_admission import (
    validate_migration_proof,
)
from PHX2.free_tier_producer.phx1_fee_gate import (
    PHX1_FEE_GATE_SCAM_LIKELY,
    fee_gate_block_reason,
    validate_fee_snapshot,
)


PHX1_REPOSITORY = r"C:\Users\BalaC\Downloads\Phoenix_Bot"
PHX1_COMMIT = "318e359084d8711256747ae0fe307303d1b526d1"
PHX1_COMMIT_SUBJECT = "fix: preserve transaction-level PumpSwap ATH peaks"
PHX1_CONFIG_SOURCE = "config.yaml"

PARITY_EXACT = "EXACT"
PARITY_INTENTIONAL_CHANGE = "INTENTIONAL_CHANGE"
PARITY_DEGRADED_DATA = "DEGRADED_DATA"
PARITY_NOT_IMPLEMENTED = "NOT_IMPLEMENTED"
PARITY_STATUSES = frozenset(
    {
        PARITY_EXACT,
        PARITY_INTENTIONAL_CHANGE,
        PARITY_DEGRADED_DATA,
        PARITY_NOT_IMPLEMENTED,
    }
)

RESULT_PASS = "PASS"
RESULT_HARD_BLOCK = "HARD_BLOCK"
RESULT_WARN = "WARN"
RESULT_OBSERVE_ONLY = "OBSERVE_ONLY"
RESULT_DATA_UNAVAILABLE = "DATA_UNAVAILABLE"
FILTER_RESULTS = frozenset(
    {
        RESULT_PASS,
        RESULT_HARD_BLOCK,
        RESULT_WARN,
        RESULT_OBSERVE_ONLY,
        RESULT_DATA_UNAVAILABLE,
    }
)

STRUCTURAL_GATE_PASS = "PASS"
STRUCTURAL_GATE_HARD_BLOCK = "HARD_BLOCK"

PHX1_LP_MIN_USD = Decimal("8000")
PHX1_LP_WARN_USD = Decimal("12000")
PHX1_MARKET_MAX_AGE_SECONDS = Decimal("300")
PHX1_INSPECTION_MIN_BUY_USD = Decimal("10000")
PHX1_INSPECTION_MAX_SELL_BUY_RATIO = Decimal("0.07")
PHX1_INSPECTION_MIN_EVENTS = 3


def _decimal(value: object) -> Optional[Decimal]:
    if value is None or isinstance(value, bool) or isinstance(value, float):
        return None
    try:
        result = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None
    return result if result.is_finite() else None


def parity_matrix() -> Dict[str, Any]:
    """Return the complete pinned PHX1-to-PHX2 filter matrix."""

    identity = {
        "repository_path": PHX1_REPOSITORY,
        "commit": PHX1_COMMIT,
        "commit_subject": PHX1_COMMIT_SUBJECT,
        "configuration_source": PHX1_CONFIG_SOURCE,
        "authority_method": "git show <commit>:<path>",
        "dirty_worktree_used": False,
    }
    rows: List[Dict[str, Any]] = [
        {
            "phx1_filter_name": "fee_gate_v2_score",
            "phx1_repository_commit": PHX1_COMMIT,
            "phx1_source_module": "filters/fee_gate.py",
            "phx2_source_module": (
                "PHX2/free_tier_producer/phx1_fee_gate.py"
            ),
            "input_fields": [
                "total_fee",
                "lp_fee",
                "protocol_fee",
                "creator_fee",
                "bribes",
                "distinct_transaction_count",
                "event_count",
            ],
            "data_source": "canonical PumpSwap transaction fee events",
            "threshold": {
                "bribes_pct_hard": "2.81",
                "bribes_pct_soft": "5.0",
                "creator_dom_hi": "0.70",
                "tx_count_min": 500,
                "suspicious_min": 3,
                "scam_likely_min": 4,
            },
            "comparison_operator": "<,<,>=,<; score >=",
            "missing_data_behavior": (
                "score returns Normal/insufficient_data; alert gate treats "
                "empty evidence as a transient block"
            ),
            "fail_open_or_closed": "closed at the alert gate",
            "classification": "block",
            "reason_token": "PHX1_FEE_GATE_SCAM_LIKELY",
            "parity_status": PARITY_EXACT,
            "tests": [
                "test_phx1_fee_gate_parity.py",
                "test_fee_gate_lifecycle.py",
                "test_primary_stream_fee_ingestion.py",
            ],
            "acceptance_domain": "C1_STRUCTURAL",
        },
        {
            "phx1_filter_name": "fee_gate_no_data",
            "phx1_repository_commit": PHX1_COMMIT,
            "phx1_source_module": "modules/alert_gate.py",
            "phx2_source_module": (
                "PHX2/free_tier_producer/phx1_structural_parity.py"
            ),
            "input_fields": ["fee_snapshot"],
            "data_source": "fee-gate lifecycle snapshot",
            "threshold": "snapshot empty or proof unavailable",
            "comparison_operator": "is_empty",
            "missing_data_behavior": "transient hard block; token remains open",
            "fail_open_or_closed": "closed",
            "classification": "block",
            "reason_token": "PHX1_FEE_GATE_NO_DATA",
            "parity_status": PARITY_EXACT,
            "tests": ["test_migration_census_tracker.py"],
            "acceptance_domain": "C1_STRUCTURAL",
        },
        {
            "phx1_filter_name": "lp_floor",
            "phx1_repository_commit": PHX1_COMMIT,
            "phx1_source_module": "filters/lp_floor.py",
            "phx2_source_module": (
                "PHX2/free_tier_producer/phx1_structural_parity.py"
            ),
            "input_fields": ["liquidity_usd"],
            "data_source": "candidate liquidity evidence",
            "threshold": {
                "low_below_usd": "8000",
                "thin_below_usd": "12000",
            },
            "comparison_operator": "<",
            "missing_data_behavior": "LOW/no_lp_data label",
            "fail_open_or_closed": "observe-only in authoritative PHX1",
            "classification": "observe",
            "reason_token": "PHX1_LP_LOW_OR_THIN",
            "parity_status": PARITY_EXACT,
            "tests": ["test_migration_census_tracker.py"],
            "acceptance_domain": "C1_STRUCTURAL",
        },
        {
            "phx1_filter_name": "inspection_bundle_wash_v2",
            "phx1_repository_commit": PHX1_COMMIT,
            "phx1_source_module": "modules/inspection_gate.py",
            "phx2_source_module": (
                "PHX2/free_tier_producer/phx1_structural_parity.py"
            ),
            "input_fields": [
                "migration_window_buy_usd",
                "migration_window_sell_usd",
                "migration_window_event_count",
            ],
            "data_source": "first PumpSwap-event migration window",
            "threshold": {
                "window_slots": 5,
                "min_buy_usd": "10000",
                "max_sell_buy_ratio": "0.07",
                "min_events": 3,
            },
            "comparison_operator": ">= and <",
            "missing_data_behavior": "CHECK_FAILED/THIN_DATA label",
            "fail_open_or_closed": "observe-only in authoritative PHX1",
            "classification": "observe",
            "reason_token": "PHX1_BUNDLE_WASH_LIKELY",
            "parity_status": PARITY_EXACT,
            "tests": ["test_migration_census_tracker.py"],
            "acceptance_domain": "C1_STRUCTURAL",
        },
        {
            "phx1_filter_name": "holder_ghost_v2",
            "phx1_repository_commit": PHX1_COMMIT,
            "phx1_source_module": "holder_filter.py; main.py",
            "phx2_source_module": None,
            "input_fields": [
                "top-holder wallet classification",
                "wallet SOL balances",
                "funding-balance clusters",
            ],
            "data_source": "holder snapshot plus wallet balance RPC",
            "threshold": {
                "block_wallets": 8,
                "block_clusters": 4,
                "low_sol_wallets": 30,
                "low_sol_cutoff": "0.1",
            },
            "comparison_operator": ">=",
            "missing_data_behavior": "no Ghost verdict; PHX1 proceeds",
            "fail_open_or_closed": "open on unavailable snapshot",
            "classification": "block when evidence exists",
            "reason_token": "PHX1_GHOST_BLOCK",
            "parity_status": PARITY_DEGRADED_DATA,
            "tests": ["test_migration_census_tracker.py"],
            "acceptance_domain": "C2_SCAM_SEPARATION",
            "scope_note": (
                "wallet/holder clustering is explicitly outside this "
                "remediation's implementation scope"
            ),
        },
        {
            "phx1_filter_name": "market_data_freshness",
            "phx1_repository_commit": PHX1_COMMIT,
            "phx1_source_module": "modules/alert_trigger.py; config.yaml",
            "phx2_source_module": (
                "PHX2/free_tier_producer/phx1_structural_parity.py"
            ),
            "input_fields": ["market_observation_age_seconds"],
            "data_source": "candidate market observation timestamp",
            "threshold": "300",
            "comparison_operator": "<=",
            "missing_data_behavior": "skip alert",
            "fail_open_or_closed": "closed",
            "classification": "block",
            "reason_token": "PHX1_MARKET_DATA_STALE",
            "parity_status": PARITY_EXACT,
            "tests": ["test_migration_census_tracker.py"],
            "acceptance_domain": "C1_STRUCTURAL",
        },
        {
            "phx1_filter_name": "migration_proof",
            "phx1_repository_commit": PHX1_COMMIT,
            "phx1_source_module": "modules/migration_ws.py",
            "phx2_source_module": (
                "PHX2/free_tier_producer/migration_admission.py"
            ),
            "input_fields": [
                "migrate CPI ancestry",
                "canonical pool PDA",
                "vault derivation and ownership",
                "mint binding",
            ],
            "data_source": "successful canonical migration transaction",
            "threshold": "all proof invariants true",
            "comparison_operator": "all",
            "missing_data_behavior": "PHX2 rejects; PHX1 had no equivalent seal",
            "fail_open_or_closed": "closed",
            "classification": "block",
            "reason_token": "CANONICAL_MIGRATION_PROOF_REQUIRED",
            "parity_status": PARITY_INTENTIONAL_CHANGE,
            "tests": [
                "test_migration_admission.py",
                "test_migrate_v2_genuine_migrations.py",
            ],
            "acceptance_domain": "C1_STRUCTURAL",
            "intentional_change": "PHX2 is strictly stronger",
        },
        {
            "phx1_filter_name": "activation_threshold",
            "phx1_repository_commit": PHX1_COMMIT,
            "phx1_source_module": "config.yaml; modules/price_tracker.py",
            "phx2_source_module": (
                "PHX2/free_tier_producer/migration_census.py"
            ),
            "input_fields": ["canonical reserve market cap"],
            "data_source": "canonical PumpSwap effective reserves",
            "threshold": {"PHX1": "1.39", "remediation_contract": "1.20"},
            "comparison_operator": ">=",
            "missing_data_behavior": "remain pending or explicit data gap",
            "fail_open_or_closed": "closed",
            "classification": "block until reached",
            "reason_token": "PENDING_1_20X",
            "parity_status": PARITY_INTENTIONAL_CHANGE,
            "tests": ["test_migration_census_tracker.py"],
            "acceptance_domain": "B_TRACKER",
            "intentional_change": "explicit remediation requirement",
        },
        {
            "phx1_filter_name": "duplicate_suppression",
            "phx1_repository_commit": PHX1_COMMIT,
            "phx1_source_module": "database.py; modules/alert_trigger.py",
            "phx2_source_module": (
                "PHX2/free_tier_producer/migration_census.py"
            ),
            "input_fields": ["canonical migration identity"],
            "data_source": "authenticated census",
            "threshold": "one application per identity",
            "comparison_operator": "== 1",
            "missing_data_behavior": "refuse application",
            "fail_open_or_closed": "closed",
            "classification": "block duplicate",
            "reason_token": "DUPLICATE_MIGRATION_SUPPRESSED",
            "parity_status": PARITY_INTENTIONAL_CHANGE,
            "tests": ["test_migration_census_tracker.py"],
            "acceptance_domain": "A_MIGRATION_COMPLETENESS",
            "intentional_change": "PHX2 uses a stronger canonical identity",
        },
        {
            "phx1_filter_name": "ath_drawdown_consistency",
            "phx1_repository_commit": PHX1_COMMIT,
            "phx1_source_module": (
                "modules/ath_state.py; modules/alert_trigger.py"
            ),
            "phx2_source_module": (
                "PHX2/free_tier_producer/ath_state.py"
            ),
            "input_fields": ["canonical ATH", "current reserve price"],
            "data_source": "central ATH and canonical reserves",
            "threshold": "current <= ATH; tier ranges are downstream",
            "comparison_operator": "<=",
            "missing_data_behavior": "no actionable drawdown",
            "fail_open_or_closed": "closed",
            "classification": "warn/block downstream",
            "reason_token": "ATH_DRAWDOWN_INCONSISTENT",
            "parity_status": PARITY_INTENTIONAL_CHANGE,
            "tests": [
                "test_central_ath_state.py",
                "test_ath_activation_risk_regression.py",
            ],
            "acceptance_domain": "C1_STRUCTURAL",
            "intentional_change": "PHX2 uses sealed central ATH evidence",
        },
    ]
    return {
        "schema_version": "phx2_phx1_filter_parity_matrix_v1",
        "authoritative_phx1_source": identity,
        "rows": rows,
    }


def _result(
    name: str,
    status: str,
    reason: str,
    *,
    evidence: Optional[Mapping[str, Any]] = None,
    acceptance_domain: str = "C1_STRUCTURAL",
) -> Dict[str, Any]:
    if status not in FILTER_RESULTS:
        raise ValueError("FILTER_RESULT_INVALID")
    return {
        "filter_name": name,
        "result": status,
        "reason_token": reason,
        "evidence": dict(evidence or {}),
        "acceptance_domain": acceptance_domain,
    }


def evaluate_structural_filters(
    *,
    migration_proof: object,
    fee_snapshot: object = None,
    liquidity_usd: object = None,
    inspection_evidence: Optional[Mapping[str, Any]] = None,
    market_observation_age_seconds: object = None,
    duplicate_application_count: int = 1,
    ath_drawdown_consistent: Optional[bool] = None,
    holder_ghost_evidence: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Evaluate every pinned PHX1 row with attributable results."""

    results: List[Dict[str, Any]] = []
    proof_valid, proof_reason = validate_migration_proof(migration_proof)
    results.append(
        _result(
            "migration_proof",
            RESULT_PASS if proof_valid else RESULT_HARD_BLOCK,
            (
                "CANONICAL_MIGRATION_PROOF_VALID"
                if proof_valid
                else str(proof_reason or "CANONICAL_MIGRATION_PROOF_REQUIRED")
            ),
        )
    )

    fee_valid, fee_reason = validate_fee_snapshot(fee_snapshot)
    fee_missing = fee_snapshot is None or not fee_valid
    results.append(
        _result(
            "fee_gate_no_data",
            RESULT_HARD_BLOCK if fee_missing else RESULT_PASS,
            (
                "PHX1_FEE_GATE_NO_DATA"
                if fee_missing
                else "PHX1_FEE_GATE_EVIDENCE_PRESENT"
            ),
            evidence={"validation_reason": fee_reason},
        )
    )
    if fee_missing:
        results.append(
            _result(
                "fee_gate_v2_score",
                RESULT_DATA_UNAVAILABLE,
                "PHX1_FEE_GATE_SCORE_UNAVAILABLE",
                evidence={"validation_reason": fee_reason},
            )
        )
    else:
        block = fee_gate_block_reason(fee_snapshot)
        label = getattr(fee_snapshot, "fee_gate_label", None)
        results.append(
            _result(
                "fee_gate_v2_score",
                RESULT_HARD_BLOCK if block else RESULT_PASS,
                block or "PHX1_FEE_GATE_PASS",
                evidence={"label": label},
            )
        )

    liquidity = _decimal(liquidity_usd)
    if liquidity is None or liquidity <= 0:
        results.append(
            _result(
                "lp_floor",
                RESULT_DATA_UNAVAILABLE,
                "PHX1_LP_NO_DATA",
            )
        )
    elif liquidity < PHX1_LP_MIN_USD:
        results.append(
            _result(
                "lp_floor",
                RESULT_OBSERVE_ONLY,
                "PHX1_LP_LOW",
                evidence={"liquidity_usd": format(liquidity, "f")},
            )
        )
    elif liquidity < PHX1_LP_WARN_USD:
        results.append(
            _result(
                "lp_floor",
                RESULT_OBSERVE_ONLY,
                "PHX1_LP_THIN",
                evidence={"liquidity_usd": format(liquidity, "f")},
            )
        )
    else:
        results.append(
            _result(
                "lp_floor",
                RESULT_PASS,
                "PHX1_LP_OK",
                evidence={"liquidity_usd": format(liquidity, "f")},
            )
        )

    inspection = (
        dict(inspection_evidence)
        if isinstance(inspection_evidence, Mapping)
        else None
    )
    if inspection is None:
        results.append(
            _result(
                "inspection_bundle_wash_v2",
                RESULT_DATA_UNAVAILABLE,
                "PHX1_INSPECTION_DATA_UNAVAILABLE",
            )
        )
    else:
        buy = _decimal(inspection.get("buy_usd"))
        sell = _decimal(inspection.get("sell_usd"))
        events = inspection.get("event_count")
        if (
            buy is None
            or sell is None
            or isinstance(events, bool)
            or not isinstance(events, int)
        ):
            inspection_status = RESULT_DATA_UNAVAILABLE
            inspection_reason = "PHX1_INSPECTION_CHECK_FAILED"
        elif events < PHX1_INSPECTION_MIN_EVENTS:
            inspection_status = RESULT_OBSERVE_ONLY
            inspection_reason = "PHX1_INSPECTION_THIN_DATA"
        else:
            ratio = sell / buy if buy > 0 else Decimal(0)
            likely = (
                buy >= PHX1_INSPECTION_MIN_BUY_USD
                and ratio < PHX1_INSPECTION_MAX_SELL_BUY_RATIO
            )
            inspection_status = (
                RESULT_OBSERVE_ONLY if likely else RESULT_PASS
            )
            inspection_reason = (
                "PHX1_BUNDLE_WASH_LIKELY"
                if likely
                else "PHX1_INSPECTION_CLEAN"
            )
        results.append(
            _result(
                "inspection_bundle_wash_v2",
                inspection_status,
                inspection_reason,
            )
        )

    age = _decimal(market_observation_age_seconds)
    if age is None:
        results.append(
            _result(
                "market_data_freshness",
                RESULT_HARD_BLOCK,
                "PHX1_MARKET_DATA_MISSING",
            )
        )
    elif age < 0 or age > PHX1_MARKET_MAX_AGE_SECONDS:
        results.append(
            _result(
                "market_data_freshness",
                RESULT_HARD_BLOCK,
                "PHX1_MARKET_DATA_STALE",
                evidence={"age_seconds": format(age, "f")},
            )
        )
    else:
        results.append(
            _result(
                "market_data_freshness",
                RESULT_PASS,
                "PHX1_MARKET_DATA_FRESH",
                evidence={"age_seconds": format(age, "f")},
            )
        )

    duplicate_ok = (
        isinstance(duplicate_application_count, int)
        and not isinstance(duplicate_application_count, bool)
        and duplicate_application_count == 1
    )
    results.append(
        _result(
            "duplicate_suppression",
            RESULT_PASS if duplicate_ok else RESULT_HARD_BLOCK,
            (
                "DUPLICATE_APPLICATION_COUNT_ONE"
                if duplicate_ok
                else "DUPLICATE_MIGRATION_APPLICATION"
            ),
            evidence={"application_count": duplicate_application_count},
        )
    )

    if ath_drawdown_consistent is None:
        results.append(
            _result(
                "ath_drawdown_consistency",
                RESULT_DATA_UNAVAILABLE,
                "ATH_DRAWDOWN_DATA_UNAVAILABLE",
            )
        )
    else:
        results.append(
            _result(
                "ath_drawdown_consistency",
                RESULT_PASS if ath_drawdown_consistent else RESULT_WARN,
                (
                    "ATH_DRAWDOWN_CONSISTENT"
                    if ath_drawdown_consistent
                    else "ATH_DRAWDOWN_INCONSISTENT"
                ),
            )
        )

    if holder_ghost_evidence is None:
        results.append(
            _result(
                "holder_ghost_v2",
                RESULT_DATA_UNAVAILABLE,
                "PHX1_GHOST_DATA_UNAVAILABLE",
                acceptance_domain="C2_SCAM_SEPARATION",
            )
        )
    else:
        verdict = str(holder_ghost_evidence.get("verdict") or "")
        results.append(
            _result(
                "holder_ghost_v2",
                RESULT_HARD_BLOCK if verdict == "block" else RESULT_PASS,
                (
                    "PHX1_GHOST_BLOCK"
                    if verdict == "block"
                    else "PHX1_GHOST_PASS"
                ),
                acceptance_domain="C2_SCAM_SEPARATION",
            )
        )

    c1_hard_blocks = [
        item["reason_token"]
        for item in results
        if item["acceptance_domain"] == "C1_STRUCTURAL"
        and item["result"] == RESULT_HARD_BLOCK
    ]
    return {
        "schema_version": "phx2_phx1_structural_filter_results_v1",
        "authoritative_phx1_commit": PHX1_COMMIT,
        "results": results,
        "final_structural_gate": (
            STRUCTURAL_GATE_HARD_BLOCK
            if c1_hard_blocks
            else STRUCTURAL_GATE_PASS
        ),
        "hard_block_reasons": c1_hard_blocks,
    }


def write_parity_matrix(path: object) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp = destination.with_name(destination.name + ".tmp")
    with temp.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(
            parity_matrix(),
            handle,
            sort_keys=True,
            separators=(",", ":"),
        )
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temp, destination)


__all__ = (
    "PHX1_REPOSITORY",
    "PHX1_COMMIT",
    "PHX1_COMMIT_SUBJECT",
    "PARITY_EXACT",
    "PARITY_INTENTIONAL_CHANGE",
    "PARITY_DEGRADED_DATA",
    "PARITY_NOT_IMPLEMENTED",
    "RESULT_PASS",
    "RESULT_HARD_BLOCK",
    "RESULT_WARN",
    "RESULT_OBSERVE_ONLY",
    "RESULT_DATA_UNAVAILABLE",
    "STRUCTURAL_GATE_PASS",
    "STRUCTURAL_GATE_HARD_BLOCK",
    "parity_matrix",
    "evaluate_structural_filters",
    "write_parity_matrix",
)

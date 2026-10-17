"""Evaluate frozen PHX1 structural parity on retained labels and holdout."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from dataclasses import fields
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from PHX2.free_tier_producer.migration_admission import (  # noqa: E402
    MigrationProofStore,
)
from PHX2.free_tier_producer.phx1_fee_gate import (  # noqa: E402
    FeeGateSnapshot,
)
from PHX2.free_tier_producer.phx1_structural_parity import (  # noqa: E402
    PHX1_COMMIT,
    RESULT_HARD_BLOCK,
    evaluate_structural_filters,
    write_parity_matrix,
)
from PHX2.free_tier_producer.phx1_structural_policy import (  # noqa: E402
    PHX1_STRUCTURAL_POLICY_CLI_VALUES,
    policy_metadata_for_filter_results,
)


_TUPLE_FIELDS = {
    "missing_data_reasons",
    "stale_data_reasons",
    "malformed_data_reasons",
    "insufficient_sample_reasons",
    "fee_gate_reasons",
}


def _canonical_json(value: Mapping[str, Any]) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    values: List[Dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        value = json.loads(line)
        if isinstance(value, dict):
            values.append(value)
    return values


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        _canonical_json(value) + "\n", encoding="utf-8", newline="\n"
    )
    os.replace(temporary, path)


def _write_jsonl(path: Path, values: Iterable[Mapping[str, Any]]) -> None:
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        "".join(_canonical_json(value) + "\n" for value in values),
        encoding="utf-8",
        newline="\n",
    )
    os.replace(temporary, path)


def _fee_snapshot(value: object) -> Optional[FeeGateSnapshot]:
    if not isinstance(value, Mapping):
        return None
    names = {field.name for field in fields(FeeGateSnapshot)}
    if set(value) != names:
        return None
    projected = dict(value)
    for name in _TUPLE_FIELDS:
        raw = projected.get(name)
        if not isinstance(raw, list):
            return None
        projected[name] = tuple(str(item) for item in raw)
    try:
        return FeeGateSnapshot(**projected)
    except (TypeError, ValueError):
        return None


def _parse_utc(value: object) -> Optional[datetime]:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _decimal(value: object) -> Optional[Decimal]:
    if value is None or isinstance(value, bool) or isinstance(value, float):
        return None
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return result if result.is_finite() else None


def _latest_for(
    rows: Iterable[Mapping[str, Any]], mint: str
) -> Optional[Dict[str, Any]]:
    matches = [
        dict(row)
        for row in rows
        if row.get("token_mint") == mint
        or row.get("candidate_mint") == mint
        or row.get("mint") == mint
    ]
    return matches[-1] if matches else None


def _market_age(row: Optional[Mapping[str, Any]]) -> Optional[str]:
    if not row:
        return None
    fetched = _parse_utc(row.get("market_context_fetched_at_utc"))
    observed = _parse_utc(row.get("observed_at_utc"))
    if fetched is None or observed is None:
        return None
    age = Decimal(str(max(0.0, (observed - fetched).total_seconds())))
    return format(age, "f")


def _ath_consistent(row: Optional[Mapping[str, Any]]) -> Optional[bool]:
    if not row:
        return None
    current = _decimal(row.get("current_market_cap_usd"))
    ath = _decimal(row.get("ath_market_cap_usd"))
    if current is None or ath is None or current <= 0 or ath <= 0:
        return None
    return current <= ath


def _tracker_map(path: Optional[Path]) -> Dict[str, Dict[str, Any]]:
    if path is None:
        return {}
    return {
        str(row["mint"]): row
        for row in _read_jsonl(path)
        if isinstance(row.get("mint"), str)
    }


def _evaluate_source(
    *,
    source_dir: Path,
    labeled_mints: Mapping[str, str],
    trackers: Mapping[str, Mapping[str, Any]],
    frozen_matrix_digest: str,
    phx1_structural_policy: str,
) -> List[Dict[str, Any]]:
    proof_store = MigrationProofStore(source_dir / "migration_proofs.jsonl")
    security = _read_jsonl(source_dir / "security_decisions.jsonl")
    pricing = _read_jsonl(source_dir / "pricing_tail.jsonl")
    output: List[Dict[str, Any]] = []
    for mint, label in labeled_mints.items():
        proof = proof_store.get(mint)
        security_row = _latest_for(security, mint)
        fee_raw = (
            (security_row.get("decision") or {}).get("fee_snapshot")
            if security_row
            and isinstance(security_row.get("decision"), Mapping)
            else None
        )
        snapshot = _fee_snapshot(fee_raw)
        pricing_row = _latest_for(pricing, mint)
        tracker = dict(trackers.get(mint) or {})
        structural = evaluate_structural_filters(
            migration_proof=proof,
            fee_snapshot=snapshot,
            liquidity_usd=(
                pricing_row.get("liquidity_usd") if pricing_row else None
            ),
            inspection_evidence=None,
            market_observation_age_seconds=_market_age(pricing_row),
            duplicate_application_count=1,
            ath_drawdown_consistent=_ath_consistent(pricing_row),
            holder_ghost_evidence=None,
        )
        unavailable = [
            result["reason_token"]
            for result in structural["results"]
            if result["result"] == "DATA_UNAVAILABLE"
        ]
        policy_metadata = policy_metadata_for_filter_results(
            structural["results"],
            policy_mode=phx1_structural_policy,
        )
        output.append(
            {
                "record_kind": "PHX2_FROZEN_PHX1_REGRESSION_RESULT",
                "label": label,
                "mint": mint,
                "canonical_migration_found": proof is not None,
                "canonical_1_20x_outcome": (
                    tracker.get("outcome")
                    or "CANONICAL_RESERVE_TRACKER_EVIDENCE_UNAVAILABLE"
                ),
                "canonical_1_20x_reached": (
                    tracker.get("outcome") == "REACHED_1_20X"
                ),
                "structural_filter_results": structural["results"],
                "final_structural_gate": structural[
                    "final_structural_gate"
                ],
                "hard_block_reasons": structural["hard_block_reasons"],
                "unavailable_evidence": unavailable,
                **policy_metadata,
                "authoritative_phx1_commit": PHX1_COMMIT,
                "frozen_parity_matrix_sha256": frozen_matrix_digest,
            }
        )
    return output


def _recover_stage8_holdout_mint(stage8_dir: Path) -> str:
    sends = _read_jsonl(stage8_dir / "sends.jsonl")
    mints = {
        str(row.get("token_mint"))
        for row in sends
        if row.get("sent_ok") is True
        and isinstance(row.get("token_mint"), str)
        and row.get("token_mint")
    }
    if len(mints) != 1:
        raise ValueError("STAGE8_HOLDOUT_MINT_NOT_UNIQUE")
    return next(iter(mints))


def run(args: argparse.Namespace) -> int:
    artifact_dir = Path(args.artifact_dir)
    artifact_dir.mkdir(parents=True, exist_ok=True)
    matrix_path = artifact_dir / "phx1_filter_parity_matrix.json"
    # Freeze matrix and thresholds before the holdout mint is even recovered.
    write_parity_matrix(matrix_path)
    frozen_digest = _sha256_file(matrix_path)

    labels = {
        mint: "MANIPULATED_COORDINATED"
        for mint in args.manipulated_mint
    }
    labels[str(args.organic_mint)] = "ORGANIC_CONTROL"
    trackers = _tracker_map(
        Path(args.tracker_outcomes) if args.tracker_outcomes else None
    )
    five = _evaluate_source(
        source_dir=Path(args.stage7_out),
        labeled_mints=labels,
        trackers=trackers,
        frozen_matrix_digest=frozen_digest,
        phx1_structural_policy=getattr(args, "phx1_structural_policy", "enforce"),
    )
    manipulated = [
        row for row in five if row["label"] == "MANIPULATED_COORDINATED"
    ]
    organic = next(row for row in five if row["label"] == "ORGANIC_CONTROL")
    manipulated_blocked = sum(
        row["final_structural_gate"] == RESULT_HARD_BLOCK
        for row in manipulated
    )
    desired = (
        manipulated_blocked == len(manipulated)
        and organic["final_structural_gate"] != RESULT_HARD_BLOCK
    )
    five_summary = {
        "kind": "PHX2_FIVE_TOKEN_LABELED_REGRESSION",
        "authoritative_phx1_commit": PHX1_COMMIT,
        "frozen_parity_matrix_sha256": frozen_digest,
        "manipulated_labels_total": len(manipulated),
        "manipulated_hard_blocked": manipulated_blocked,
        "organic_control_hard_blocked": (
            organic["final_structural_gate"] == RESULT_HARD_BLOCK
        ),
        "desired_four_versus_one_separation": desired,
        "classification": (
            "PHX1_SCAM_SEPARATION_READY"
            if desired
            else "PHX1_SCAM_SEPARATION_REQUIRES_ADDITIONAL_DATA"
        ),
        "missing_evidence_families": [
            "wallet funding",
            "holder clusters",
            "transfers",
            "side-pool history",
            "pool-addressed volume",
            "buyer/seller identity",
        ],
    }

    holdout_mint = _recover_stage8_holdout_mint(
        Path(args.stage8_artifacts)
    )
    holdout = _evaluate_source(
        source_dir=Path(args.stage8_artifacts),
        labeled_mints={holdout_mint: "STAGE8_HOLDOUT"},
        trackers=trackers,
        frozen_matrix_digest=frozen_digest,
        phx1_structural_policy=getattr(args, "phx1_structural_policy", "enforce"),
    )[0]
    holdout_record = {
        "kind": "PHX2_STAGE8_HOLDOUT_EVALUATION",
        "parity_frozen_before_holdout": True,
        "frozen_parity_matrix_sha256": frozen_digest,
        "result": holdout,
        "threshold_tuning_after_holdout": False,
    }

    _write_jsonl(artifact_dir / "phx1_filter_results.jsonl", five + [holdout])
    _write_json(artifact_dir / "five_token_regression.json", five_summary)
    _write_json(artifact_dir / "stage8_holdout.json", holdout_record)
    _write_json(
        artifact_dir / "phx1_filter_summary.json",
        {
            "kind": "PHX2_PHX1_FILTER_SUMMARY",
            "authoritative_phx1_commit": PHX1_COMMIT,
            "frozen_parity_matrix_sha256": frozen_digest,
            "evaluated_records": len(five) + 1,
            "five_token_regression": five_summary,
            "stage8_holdout_evaluated_after_freeze": True,
        },
    )
    print(five_summary["classification"])
    print(
        f"manipulated_blocked={manipulated_blocked}/{len(manipulated)} "
        f"organic_blocked={five_summary['organic_control_hard_blocked']} "
        "holdout_evaluated_after_freeze=True"
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage7-out", required=True)
    parser.add_argument("--stage8-artifacts", required=True)
    parser.add_argument("--artifact-dir", required=True)
    parser.add_argument("--manipulated-mint", action="append", required=True)
    parser.add_argument("--organic-mint", required=True)
    parser.add_argument("--tracker-outcomes")
    parser.add_argument(
        "--phx1-structural-policy",
        choices=list(PHX1_STRUCTURAL_POLICY_CLI_VALUES),
        default="enforce",
    )
    return parser


if __name__ == "__main__":
    raise SystemExit(run(build_parser().parse_args()))

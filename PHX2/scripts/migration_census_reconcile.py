"""Confirmed-RPC migration census reconciliation (read-only chain access).

This operator tool loads only the active repository ``.env`` through the
production loader, removes every delivery credential from the process
environment, and performs bounded confirmed-block reconciliation.  It never
constructs a delivery transport and never opens a Yellowstone connection.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

_REPO = Path(__file__).resolve().parents[2]
_PRODUCER = _REPO / "PHX2" / "free_tier_producer"
_COMPAT = _PRODUCER / "compat"
for _path in (_REPO, _PRODUCER, _COMPAT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from PHX2.free_tier_producer import free_tier_session as session  # noqa: E402
from PHX2.free_tier_producer.migration_admission import (  # noqa: E402
    MigrationProofStore,
    build_migration_admission_config,
)
from PHX2.free_tier_producer.migration_census import (  # noqa: E402
    MigrationCensusError,
    MigrationCensusStore,
)
from PHX2.free_tier_producer.migration_reconciliation import (  # noqa: E402
    ConfirmedMigrationReconciler,
    MigrationReconciliationStore,
)
from PHX2.free_tier_producer.phx1_structural_parity import (  # noqa: E402
    write_parity_matrix,
)
from PHX2.free_tier_producer.pumpswap_reserves import (  # noqa: E402
    PumpSwapReserveIndex,
)
from PHX2.free_tier_producer.rpc_gap_recovery import (  # noqa: E402
    GAP_RECOVERY_MODE_RPC_BACKFILL,
    RpcGapRecoveryConfig,
    build_rpc_transport_from_env,
)


def _remove_delivery_environment() -> int:
    removed = session.harden_no_send_env(
        allow_birdeye_fallback=False, allow_paid_provider=True
    )
    blocked_terms = (
        "DISCORD",
        "TELEGRAM",
        "WEBHOOK",
        "WALLET",
        "PRIVATE_KEY",
        "PRIVKEY",
        "SIGNER",
    )
    for key in list(os.environ):
        if any(term in key.upper() for term in blocked_terms):
            os.environ.pop(key, None)
            removed += 1
    return removed


def _canonical_reserve_sink(
    census: MigrationCensusStore, payload: Dict[str, Any]
) -> bool:
    result = census.observe_canonical_reserve(
        mint=str(payload["mint"]),
        pool=str(payload["pool_address"]),
        slot=int(payload["slot"]),
        observed_at_utc=str(payload["source_timestamp"]),
        raw_quote_reserves=payload["raw_quote_reserves"],
        virtual_quote_reserves=payload["virtual_quote_reserves"],
        effective_quote_reserves_value=payload[
            "effective_quote_reserves"
        ],
        base_reserves=payload["base_reserves"],
        base_supply=payload["base_supply"],
        base_decimals=int(payload["base_decimals"]),
        quote_decimals=int(payload["quote_decimals"]),
        source_evidence_digest=str(payload["source_evidence_digest"]),
    )
    accepted = bool(result.get("accepted")) or result.get("reason") in (
        "TRACKER_TERMINAL",
        "AFTER_WATCH_DEADLINE",
        "DUPLICATE_RESERVE_OBSERVATION",
    )
    if not accepted:
        raise MigrationCensusError(
            str(result.get("reason") or "RESERVE_OBSERVER_REFUSED")
        )
    return True


def _write_json(path: Path, value: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    os.replace(temporary, path)


def run(args: argparse.Namespace) -> int:
    active_env = Path(args.env).resolve()
    if active_env != (_REPO / ".env").resolve():
        print("REFUSED:ACTIVE_REPOSITORY_ENV_REQUIRED")
        return 2
    session.sess.load_env_file(str(active_env))
    removed = _remove_delivery_environment()
    rpc_post = build_rpc_transport_from_env()
    if rpc_post is None:
        print("REFUSED:CONFIRMED_RPC_TRANSPORT_MISSING")
        return 2

    state_dir = Path(args.state_dir)
    artifact_dir = Path(args.artifact_dir)
    state_dir.mkdir(parents=True, exist_ok=True)
    artifact_dir.mkdir(parents=True, exist_ok=True)

    census = MigrationCensusStore(
        state_dir=state_dir,
        artifact_dir=artifact_dir,
        watch_expiry_seconds=int(args.watch_expiry_seconds),
    )
    census_load = census.load()
    reconciliation = MigrationReconciliationStore(
        state_dir=state_dir, artifact_dir=artifact_dir
    )
    reconciliation_load = reconciliation.load()
    if census.quarantined or reconciliation.quarantined:
        print("REFUSED:AUTHENTICATED_RECONCILIATION_STATE_QUARANTINED")
        return 2

    proof_store = MigrationProofStore(
        artifact_dir / "migration_proofs.jsonl"
    )
    reserve_index = PumpSwapReserveIndex(
        proof_store=proof_store,
        canonical_observer_allow_historical=True,
    )
    reserve_index.add_canonical_reserve_observer(
        lambda payload: _canonical_reserve_sink(census, payload)
    )
    admission_config = build_migration_admission_config(os.environ)
    config = RpcGapRecoveryConfig(
        mode=GAP_RECOVERY_MODE_RPC_BACKFILL,
        authoritative_commitment="confirmed",
        max_gap_slots=int(args.chunk_slots),
        max_produced_blocks=int(args.max_produced_blocks),
        max_transactions=int(args.max_transactions),
        max_backfill_runtime_seconds=float(args.max_runtime_seconds),
        max_rpc_requests=int(args.max_rpc_requests),
        max_retries_per_request=int(args.max_retries_per_request),
        max_consecutive_rpc_failures=int(
            args.max_consecutive_rpc_failures
        ),
        max_http_429_responses=int(args.max_http_429),
        rpc_request_spacing_seconds=float(args.request_spacing_seconds),
        rpc_concurrency=1,
    )
    runner = ConfirmedMigrationReconciler(
        config=config,
        reconciliation_store=reconciliation,
        census_store=census,
        proof_store=proof_store,
        reserve_index=reserve_index,
        rpc_post_fn=rpc_post,
        admission_config=admission_config,
        admit_new_migrations=not bool(args.existing_census_only),
    )
    result = runner.reconcile_range(
        start_slot=int(args.start_slot), end_slot=int(args.end_slot)
    )
    horizons_finalized = 0
    chunks = result.get("chunks") or []
    coverage_block_time = (
        chunks[-1].get("last_completed_block_time") if chunks else None
    )
    if (
        result["completion_status"] == "COMPLETE"
        and isinstance(coverage_block_time, int)
        and not isinstance(coverage_block_time, bool)
    ):
        horizons_finalized = census.finalize_complete_horizons(
            coverage_through_utc=datetime.fromtimestamp(
                coverage_block_time, tz=timezone.utc
            ).strftime("%Y-%m-%dT%H:%M:%SZ")
        )
    write_parity_matrix(artifact_dir / "phx1_filter_parity_matrix.json")
    safe_summary = {
        "kind": "PHX2_MIGRATION_RECONCILIATION_RUN",
        "commitment": "confirmed",
        "existing_census_only": bool(args.existing_census_only),
        "range_start": int(args.start_slot),
        "range_end": int(args.end_slot),
        "completion_status": result["completion_status"],
        "reconciliation_watermark": result[
            "reconciliation_watermark"
        ],
        "produced_blocks_total": result["produced_blocks_total"],
        "completed_blocks_total": result["completed_blocks_total"],
        "unresolved_blocks_total": result["unresolved_blocks_total"],
        "canonical_migrations_found": result[
            "canonical_migrations_found"
        ],
        "duplicate_migrations_suppressed": result[
            "duplicate_migrations_suppressed"
        ],
        "census": census.summary(),
        "reconciliation": reconciliation.summary(),
        "coverage_last_completed_block_time": coverage_block_time,
        "coverage_proven_horizons_finalized": horizons_finalized,
        "delivery_environment_entries_removed": removed,
        "maximum_send_capable_transports": 0,
        "delivery_attempts": 0,
        "real_sends": 0,
        "canonical_reserve_observer_failure_reason": (
            reserve_index.last_required_observer_failure_reason()
        ),
        "census_checkpoint_restored": bool(
            census_load.checkpoint_files_found
        ),
        "reconciliation_checkpoint_restored": bool(
            reconciliation_load.checkpoint_files_found
        ),
    }
    _write_json(
        artifact_dir / "migration_reconciliation_run_summary.json",
        safe_summary,
    )
    print(
        "RECONCILIATION_"
        + (
            "COMPLETE"
            if result["completion_status"] == "COMPLETE"
            else "UNRESOLVED"
        )
    )
    print(
        "range="
        f"{args.start_slot}-{args.end_slot} "
        f"watermark={result['reconciliation_watermark']} "
        f"produced={result['produced_blocks_total']} "
        f"completed={result['completed_blocks_total']} "
        f"unresolved={result['unresolved_blocks_total']} "
        f"census={census.summary()['census_records']}"
    )
    return 0 if result["completion_status"] == "COMPLETE" else 3


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--env", required=True)
    parser.add_argument("--state-dir", required=True)
    parser.add_argument("--artifact-dir", required=True)
    parser.add_argument("--start-slot", type=int, required=True)
    parser.add_argument("--end-slot", type=int, required=True)
    parser.add_argument("--watch-expiry-seconds", type=int, default=3600)
    parser.add_argument("--chunk-slots", type=int, default=1800)
    parser.add_argument("--max-produced-blocks", type=int, default=1600)
    parser.add_argument("--max-transactions", type=int, default=4_000_000)
    parser.add_argument("--max-runtime-seconds", type=float, default=1800)
    parser.add_argument("--max-rpc-requests", type=int, default=4096)
    parser.add_argument("--max-retries-per-request", type=int, default=3)
    parser.add_argument(
        "--max-consecutive-rpc-failures", type=int, default=8
    )
    parser.add_argument("--max-http-429", type=int, default=24)
    parser.add_argument("--request-spacing-seconds", type=float, default=0.25)
    parser.add_argument(
        "--existing-census-only",
        action="store_true",
        help=(
            "Track canonical reserves only for proofs already present in the "
            "proof store; do not admit migrations outside the frozen census."
        ),
    )
    return parser


if __name__ == "__main__":
    raise SystemExit(run(build_parser().parse_args()))

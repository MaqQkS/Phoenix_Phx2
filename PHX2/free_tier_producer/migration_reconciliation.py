"""Resumable confirmed-block migration reconciliation.

Confirmed RPC is the authoritative produced-block coverage source.  Total
ranges are split into bounded chunks derived from the existing 1,800-slot
recovery limit.  A reconciliation watermark advances only after every produced
block in a chunk has been fetched, inspected and its census mutations have
been durably committed.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Tuple

from PHX2.free_tier_producer import checkpoint_envelope as _cpe
from PHX2.free_tier_producer.durable_state import AuthenticatedSingletonStore
from PHX2.free_tier_producer.migration_admission import (
    MigrationAdmissionConfig,
    MigrationProofStore,
    evaluate_migration_admission,
)
from PHX2.free_tier_producer.migration_census import (
    DISCOVERY_SOURCE_RPC_RECONCILIATION,
    MigrationCensusStore,
)
from PHX2.free_tier_producer.pumpswap_reserves import (
    PumpSwapReserveIndex,
    ingest_reserve_events_from_update,
)
from PHX2.free_tier_producer.rpc_gap_recovery import (
    RpcBackfillBoundExceeded,
    RpcGapRecoveryConfig,
    SolanaRpcBackfillAdapter,
    build_subscribe_update_from_rpc_transaction,
    rpc_transaction_mentions_program,
)
from PHX2.stage29.pumpswap_program_constants import PUMPSWAP_PROGRAM_ID


CHECKPOINT_KIND_MIGRATION_RECONCILIATION = (
    "PHX2_MIGRATION_RECONCILIATION"
)
MIGRATION_RECONCILIATION_SCHEMA_V1 = (
    "phx2_migration_reconciliation_v1"
)
MIGRATION_RECONCILIATION_RECORD_KIND = (
    "PHX2_MIGRATION_RECONCILIATION_STATE"
)
MIGRATION_RECONCILIATION_CHECKPOINT_BASENAME = (
    "migration_reconciliation_checkpoint.json"
)
MIGRATION_RECONCILIATION_COVERAGE_BASENAME = (
    "migration_reconciliation_coverage.jsonl"
)
MIGRATION_RECONCILIATION_SUMMARY_BASENAME = (
    "migration_reconciliation_summary.json"
)

CHUNK_COMPLETE = "COMPLETE"
CHUNK_UNRESOLVED = "UNRESOLVED"
CHUNK_INTERRUPTED = "INTERRUPTED"
CHUNK_STATUSES = frozenset(
    {CHUNK_COMPLETE, CHUNK_UNRESOLVED, CHUNK_INTERRUPTED}
)

DEFAULT_RECONCILIATION_CHUNK_SLOTS = 1800


class MigrationReconciliationError(RuntimeError):
    """A chunk could not prove complete produced-block coverage."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def _canonical_json(value: Mapping[str, Any]) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _sha256(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def reconciliation_range_identity(
    start_slot: int, end_slot: int, commitment: str
) -> str:
    return _sha256(
        {
            "identity_version": "phx2_reconciliation_range_v1",
            "start_slot": int(start_slot),
            "end_slot": int(end_slot),
            "commitment": str(commitment),
        }
    )


def plan_reconciliation_chunks(
    *,
    start_slot: int,
    end_slot: int,
    chunk_slots: int = DEFAULT_RECONCILIATION_CHUNK_SLOTS,
) -> Tuple[Tuple[int, int], ...]:
    for name, value in (
        ("start_slot", start_slot),
        ("end_slot", end_slot),
        ("chunk_slots", chunk_slots),
    ):
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"{name.upper()}_INVALID")
    if start_slot < 0 or end_slot < start_slot or chunk_slots <= 0:
        raise ValueError("RECONCILIATION_RANGE_INVALID")
    ranges: List[Tuple[int, int]] = []
    cursor = int(start_slot)
    while cursor <= end_slot:
        chunk_end = min(int(end_slot), cursor + int(chunk_slots) - 1)
        ranges.append((cursor, chunk_end))
        cursor = chunk_end + 1
    return tuple(ranges)


def _range_record(
    start_slot: int, end_slot: int, commitment: str
) -> Dict[str, Any]:
    return {
        "range_identity": reconciliation_range_identity(
            start_slot, end_slot, commitment
        ),
        "range_start": int(start_slot),
        "range_end": int(end_slot),
        "commitment": str(commitment),
        "reconciliation_watermark": int(start_slot) - 1,
        "chunks": [],
        "produced_blocks_total": 0,
        "completed_blocks_total": 0,
        "explicitly_unavailable_blocks_total": 0,
        "unresolved_blocks_total": 0,
        "canonical_migrations_found": 0,
        "duplicate_migrations_suppressed": 0,
        "rpc_request_count": 0,
        "rpc_retry_count": 0,
        "rpc_rate_limit_count": 0,
        "rpc_timeout_count": 0,
        "rpc_error_count": 0,
        "completion_status": "PENDING",
        "last_error": None,
    }


def validate_reconciliation_state(
    record: Mapping[str, Any],
) -> Tuple[bool, str]:
    if record.get("record_kind") != MIGRATION_RECONCILIATION_RECORD_KIND:
        return False, _cpe.QUARANTINE_KIND_INVALID
    ranges = record.get("ranges")
    if not isinstance(ranges, list):
        return False, _cpe.QUARANTINE_CROSS_CONSISTENCY_INVALID
    identities: set[str] = set()
    for item in ranges:
        if not isinstance(item, Mapping):
            return False, _cpe.QUARANTINE_CROSS_CONSISTENCY_INVALID
        identity = item.get("range_identity")
        start = item.get("range_start")
        end = item.get("range_end")
        watermark = item.get("reconciliation_watermark")
        if (
            not _cpe.is_sha256_digest(identity)
            or identity in identities
            or isinstance(start, bool)
            or not isinstance(start, int)
            or start < 0
            or isinstance(end, bool)
            or not isinstance(end, int)
            or end < start
            or isinstance(watermark, bool)
            or not isinstance(watermark, int)
            or watermark < start - 1
            or watermark > end
        ):
            return False, _cpe.QUARANTINE_NUMERIC_INVALID
        identities.add(str(identity))
        chunks = item.get("chunks")
        if not isinstance(chunks, list):
            return False, _cpe.QUARANTINE_CROSS_CONSISTENCY_INVALID
        previous_end = start - 1
        for chunk in chunks:
            if not isinstance(chunk, Mapping):
                return False, _cpe.QUARANTINE_CROSS_CONSISTENCY_INVALID
            chunk_start = chunk.get("range_start")
            chunk_end = chunk.get("range_end")
            if (
                chunk.get("completion_status") != CHUNK_COMPLETE
                or isinstance(chunk_start, bool)
                or not isinstance(chunk_start, int)
                or chunk_start != previous_end + 1
            ):
                return False, _cpe.QUARANTINE_CROSS_CONSISTENCY_INVALID
            if (
                isinstance(chunk_end, bool)
                or not isinstance(chunk_end, int)
                or chunk_end < chunk_start
                or chunk_end > end
            ):
                return False, _cpe.QUARANTINE_NUMERIC_INVALID
            previous_end = chunk_end
        if chunks and previous_end != watermark:
            return False, _cpe.QUARANTINE_CROSS_CONSISTENCY_INVALID
        if not chunks and watermark != start - 1:
            return False, _cpe.QUARANTINE_CROSS_CONSISTENCY_INVALID
    if not _cpe.record_digest_is_valid(
        CHECKPOINT_KIND_MIGRATION_RECONCILIATION, record
    ):
        return False, _cpe.QUARANTINE_RECORD_DIGEST_INVALID
    return True, ""


def reconciliation_state_identity(
    record: Mapping[str, Any],
) -> Tuple[str]:
    if record.get("record_kind") != MIGRATION_RECONCILIATION_RECORD_KIND:
        raise ValueError("MIGRATION_RECONCILIATION_RECORD_KIND_INVALID")
    return (MIGRATION_RECONCILIATION_RECORD_KIND,)


class MigrationReconciliationStore(AuthenticatedSingletonStore):
    checkpoint_kind = CHECKPOINT_KIND_MIGRATION_RECONCILIATION
    schema_version = MIGRATION_RECONCILIATION_SCHEMA_V1
    record_kind = MIGRATION_RECONCILIATION_RECORD_KIND

    def __init__(
        self,
        *,
        state_dir: object,
        artifact_dir: Optional[object] = None,
        basename: str = MIGRATION_RECONCILIATION_CHECKPOINT_BASENAME,
    ) -> None:
        super().__init__(primary_path=Path(state_dir) / basename)
        self._artifact_dir = (
            Path(artifact_dir) if artifact_dir is not None else None
        )
        self._ranges: Dict[str, Dict[str, Any]] = {}
        self._mutation_lock = threading.RLock()

    def classify(self, path: object) -> _cpe.FileClassification:
        return _cpe.classify_checkpoint_file(
            path,
            kind=self.checkpoint_kind,
            supported_schema_versions=(self.schema_version,),
            record_validator=validate_reconciliation_state,
            identity_fn=reconciliation_state_identity,
        )

    def restore_record(self, record: Mapping[str, Any]) -> None:
        self._ranges = {
            str(item["range_identity"]): dict(item)
            for item in record.get("ranges") or []
        }

    def current_record(self) -> Dict[str, Any]:
        return {
            "record_kind": MIGRATION_RECONCILIATION_RECORD_KIND,
            "ranges": sorted(
                (dict(item) for item in self._ranges.values()),
                key=lambda item: (
                    int(item["range_start"]),
                    int(item["range_end"]),
                    str(item["range_identity"]),
                ),
            ),
        }

    def ensure_range(
        self, *, start_slot: int, end_slot: int, commitment: str
    ) -> Dict[str, Any]:
        identity = reconciliation_range_identity(
            start_slot, end_slot, commitment
        )
        with self._mutation_lock, self._lock:
            if identity not in self._ranges:
                self._ranges[identity] = _range_record(
                    start_slot, end_slot, commitment
                )
                self._persist_all_locked()
            return dict(self._ranges[identity])

    def commit_chunk(
        self,
        *,
        range_identity: str,
        chunk: Mapping[str, Any],
    ) -> None:
        if chunk.get("completion_status") != CHUNK_COMPLETE:
            raise MigrationReconciliationError(
                "UNRESOLVED_CHUNK_CANNOT_ADVANCE_WATERMARK"
            )
        if int(chunk.get("unresolved_blocks") or 0) != 0:
            raise MigrationReconciliationError(
                "UNRESOLVED_BLOCK_PREVENTS_CHUNK_COMMIT"
            )
        with self._mutation_lock, self._lock:
            current = dict(self._ranges[range_identity])
            expected_start = int(current["reconciliation_watermark"]) + 1
            if int(chunk["range_start"]) != expected_start:
                raise MigrationReconciliationError(
                    "RECONCILIATION_CHUNK_NOT_CONTIGUOUS"
                )
            completed = [dict(item) for item in current["chunks"]]
            completed.append(dict(chunk))
            current["chunks"] = completed
            current["reconciliation_watermark"] = int(chunk["range_end"])
            for target, source in (
                ("produced_blocks_total", "produced_blocks"),
                ("completed_blocks_total", "completed_blocks"),
                (
                    "explicitly_unavailable_blocks_total",
                    "explicitly_unavailable_blocks",
                ),
                (
                    "unresolved_blocks_total",
                    "unresolved_blocks",
                ),
                (
                    "canonical_migrations_found",
                    "canonical_migrations_found",
                ),
                (
                    "duplicate_migrations_suppressed",
                    "duplicate_migrations_suppressed",
                ),
                ("rpc_request_count", "rpc_request_count"),
                ("rpc_retry_count", "rpc_retry_count"),
                ("rpc_rate_limit_count", "rpc_rate_limit_count"),
                ("rpc_timeout_count", "rpc_timeout_count"),
                ("rpc_error_count", "rpc_error_count"),
            ):
                current[target] = int(current[target]) + int(
                    chunk.get(source) or 0
                )
            current["last_error"] = None
            current["completion_status"] = (
                "COMPLETE"
                if int(current["reconciliation_watermark"])
                == int(current["range_end"])
                else "IN_PROGRESS"
            )
            self._ranges[range_identity] = current
            self._persist_all_locked()

    def note_unresolved(
        self, *, range_identity: str, reason: str
    ) -> None:
        with self._mutation_lock, self._lock:
            current = dict(self._ranges[range_identity])
            current["completion_status"] = "UNRESOLVED"
            current["last_error"] = str(reason)
            self._ranges[range_identity] = current
            self._persist_all_locked()

    def range_record(self, range_identity: str) -> Dict[str, Any]:
        with self._lock:
            return dict(self._ranges[range_identity])

    def records(self) -> Tuple[Dict[str, Any], ...]:
        with self._lock:
            return tuple(
                dict(item)
                for item in sorted(
                    self._ranges.values(),
                    key=lambda item: (
                        int(item["range_start"]),
                        int(item["range_end"]),
                    ),
                )
            )

    def summary(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "range_count": len(self._ranges),
                "complete_ranges": sum(
                    1
                    for item in self._ranges.values()
                    if item["completion_status"] == "COMPLETE"
                ),
                "produced_blocks_total": sum(
                    int(item["produced_blocks_total"])
                    for item in self._ranges.values()
                ),
                "completed_blocks_total": sum(
                    int(item["completed_blocks_total"])
                    for item in self._ranges.values()
                ),
                "unresolved_blocks_total": sum(
                    int(item["unresolved_blocks_total"])
                    for item in self._ranges.values()
                ),
                "canonical_migrations_found": sum(
                    int(item["canonical_migrations_found"])
                    for item in self._ranges.values()
                ),
                "duplicate_migrations_suppressed": sum(
                    int(item["duplicate_migrations_suppressed"])
                    for item in self._ranges.values()
                ),
                "checkpoint_generation": self.generation,
                "checkpoint_quarantined": self.quarantined,
            }

    def _persist_all_locked(self) -> None:
        self._persist_record_locked(self.current_record())
        if self._artifact_dir is None:
            return
        self._artifact_dir.mkdir(parents=True, exist_ok=True)
        coverage_path = (
            self._artifact_dir
            / MIGRATION_RECONCILIATION_COVERAGE_BASENAME
        )
        summary_path = (
            self._artifact_dir
            / MIGRATION_RECONCILIATION_SUMMARY_BASENAME
        )
        records = self.records()
        coverage = (
            "\n".join(_canonical_json(item) for item in records) + "\n"
            if records
            else ""
        )
        _atomic_write(coverage_path, coverage)
        _atomic_write(
            summary_path, _canonical_json(self.summary()) + "\n"
        )


def _atomic_write(path: Path, text: str) -> None:
    temp = path.with_name(path.name + ".tmp")
    with temp.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temp, path)


class ConfirmedMigrationReconciler:
    """Synchronous bounded-chunk reconciler with cooperative interruption."""

    def __init__(
        self,
        *,
        config: RpcGapRecoveryConfig,
        reconciliation_store: MigrationReconciliationStore,
        census_store: MigrationCensusStore,
        proof_store: MigrationProofStore,
        reserve_index: PumpSwapReserveIndex,
        rpc_post_fn: Callable[..., Tuple[int, Optional[Dict[str, Any]]]],
        rpc_timeout_seconds: float = 20.0,
        stop_requested_fn: Optional[Callable[[], bool]] = None,
        monotonic_fn: Callable[[], float] = time.monotonic,
        sleep_fn: Callable[[float], None] = time.sleep,
        rejection_sink: Optional[Callable[[Dict[str, Any]], None]] = None,
        admission_config: Optional[MigrationAdmissionConfig] = None,
        admit_new_migrations: bool = True,
    ) -> None:
        if config.authoritative_commitment not in ("confirmed", "finalized"):
            raise ValueError("RECONCILIATION_COMMITMENT_INVALID")
        self._config = config
        self._store = reconciliation_store
        self._census = census_store
        self._proof_store = proof_store
        self._reserve_index = reserve_index
        self._rpc_post = rpc_post_fn
        self._rpc_timeout = float(rpc_timeout_seconds)
        self._stop_requested = stop_requested_fn or (lambda: False)
        self._monotonic = monotonic_fn
        self._sleep = sleep_fn
        self._rejection_sink = rejection_sink
        self._admission_config = admission_config
        self._admit_new_migrations = bool(admit_new_migrations)

    def reconcile_range(
        self, *, start_slot: int, end_slot: int
    ) -> Dict[str, Any]:
        commitment = str(self._config.authoritative_commitment)
        state = self._store.ensure_range(
            start_slot=start_slot,
            end_slot=end_slot,
            commitment=commitment,
        )
        range_identity = str(state["range_identity"])
        watermark = int(state["reconciliation_watermark"])
        next_slot = max(int(start_slot), watermark + 1)
        if next_slot > int(end_slot):
            return self._store.range_record(range_identity)
        chunks = plan_reconciliation_chunks(
            start_slot=next_slot,
            end_slot=int(end_slot),
            chunk_slots=min(
                int(self._config.max_gap_slots),
                int(self._config.max_produced_blocks),
            ),
        )
        previous_slot: Optional[int] = None
        previous_hash: Optional[str] = None
        completed = state.get("chunks") or []
        if completed:
            last = completed[-1]
            previous_slot = last.get("last_produced_slot")
            previous_hash = last.get("last_completed_blockhash")

        for chunk_start, chunk_end in chunks:
            if self._stop_requested():
                self._store.note_unresolved(
                    range_identity=range_identity,
                    reason="RECONCILIATION_INTERRUPTED",
                )
                return self._store.range_record(range_identity)
            adapter = SolanaRpcBackfillAdapter(
                rpc_post_fn=self._rpc_post,
                config=self._config,
                timeout_seconds=self._rpc_timeout,
                monotonic_fn=self._monotonic,
                sleep_fn=self._sleep,
            )
            chunk_started = self._monotonic()
            chunk_record: Dict[str, Any] = {
                "range_start": int(chunk_start),
                "range_end": int(chunk_end),
                "commitment": commitment,
                "produced_blocks": 0,
                "completed_blocks": 0,
                "explicitly_unavailable_blocks": 0,
                "unresolved_blocks": 0,
                "canonical_migrations_found": 0,
                "duplicate_migrations_suppressed": 0,
                "transactions_scanned": 0,
                "transactions_relevant": 0,
                "transactions_rejected": 0,
                "last_produced_slot": previous_slot,
                "last_completed_blockhash": previous_hash,
                "last_completed_block_time": None,
                "reconciliation_watermark_before": int(chunk_start) - 1,
                "reconciliation_watermark_after": None,
                "checkpoint_generation_before": self._store.generation,
                "checkpoint_generation_after": None,
                "completion_status": CHUNK_UNRESOLVED,
                "admit_new_migrations": self._admit_new_migrations,
                "runtime_ms": 0,
            }
            try:
                produced = adapter.get_blocks(
                    start_slot=chunk_start,
                    end_slot=chunk_end,
                    commitment=commitment,
                )
                if len(produced) > int(
                    self._config.max_produced_blocks
                ):
                    raise MigrationReconciliationError(
                        "RECONCILIATION_CHUNK_BLOCK_LIMIT_EXCEEDED"
                    )
                chunk_record["produced_blocks"] = len(produced)
                for block_slot in produced:
                    if self._stop_requested():
                        raise MigrationReconciliationError(
                            "RECONCILIATION_INTERRUPTED"
                        )
                    if (
                        self._monotonic() - chunk_started
                        > float(
                            self._config.max_backfill_runtime_seconds
                        )
                    ):
                        raise MigrationReconciliationError(
                            "RECONCILIATION_CHUNK_RUNTIME_EXCEEDED"
                        )
                    block = adapter.get_block(
                        slot=block_slot, commitment=commitment
                    )
                    if previous_slot is not None:
                        if int(block.get("parentSlot", -1)) != int(
                            previous_slot
                        ):
                            raise MigrationReconciliationError(
                                "RECONCILIATION_FORK_INCONSISTENT"
                            )
                        if (
                            previous_hash is not None
                            and str(block.get("previousBlockhash"))
                            != str(previous_hash)
                        ):
                            raise MigrationReconciliationError(
                                "RECONCILIATION_FORK_INCONSISTENT"
                            )
                    block_time = block.get("blockTime")
                    transactions = block.get("transactions") or []
                    for tx_index, tx_json in enumerate(transactions):
                        chunk_record["transactions_scanned"] += 1
                        if int(chunk_record["transactions_scanned"]) > int(
                            self._config.max_transactions
                        ):
                            raise MigrationReconciliationError(
                                "RECONCILIATION_CHUNK_TRANSACTION_LIMIT_EXCEEDED"
                            )
                        if not rpc_transaction_mentions_program(
                            tx_json, PUMPSWAP_PROGRAM_ID
                        ):
                            continue
                        chunk_record["transactions_relevant"] += 1
                        meta = (
                            tx_json.get("meta")
                            if isinstance(tx_json, Mapping)
                            else None
                        )
                        if (
                            not isinstance(meta, Mapping)
                            or meta.get("err") is not None
                        ):
                            chunk_record["transactions_rejected"] += 1
                            continue
                        update = build_subscribe_update_from_rpc_transaction(
                            slot=block_slot,
                            block_time=(
                                block_time
                                if isinstance(block_time, int)
                                and not isinstance(block_time, bool)
                                else None
                            ),
                            transaction_index=tx_index,
                            tx_json=tx_json,
                        )
                        if update is None:
                            chunk_record["transactions_rejected"] += 1
                            continue
                        observed_at = (
                            _cpe.utc_now_iso()
                            if not isinstance(block_time, int)
                            else time.strftime(
                                "%Y-%m-%dT%H:%M:%SZ",
                                time.gmtime(block_time),
                            )
                        )
                        decision = None
                        if self._admit_new_migrations:
                            decision = evaluate_migration_admission(
                                update,
                                config=self._admission_config,
                                observed_at_utc=observed_at,
                            )
                        if decision is not None and decision.admitted:
                            proof = decision.proof
                            assert proof is not None
                            self._proof_store.seal_and_store(proof)
                            result = self._census.register_migration(
                                proof,
                                discovery_source=(
                                    DISCOVERY_SOURCE_RPC_RECONCILIATION
                                ),
                                migration_block_time=(
                                    block_time
                                    if isinstance(block_time, int)
                                    else None
                                ),
                                reconciliation_range=(
                                    int(chunk_start),
                                    int(chunk_end),
                                ),
                                first_seen_utc=observed_at,
                            )
                            if result["inserted"]:
                                chunk_record[
                                    "canonical_migrations_found"
                                ] += 1
                            else:
                                chunk_record[
                                    "duplicate_migrations_suppressed"
                                ] += 1
                            self._reserve_index.register_pool(
                                pool_address=proof.pool,
                                base_mint=proof.base_mint,
                                quote_mint=proof.quote_mint,
                                creation_timestamp=observed_at,
                            )
                        elif (
                            decision is not None
                            and self._rejection_sink is not None
                        ):
                            self._rejection_sink(
                                decision.diagnostic_record()
                            )
                        ingest_reserve_events_from_update(
                            update, reserve_index=self._reserve_index
                        )
                        consume_failure = getattr(
                            self._reserve_index,
                            "consume_required_observer_failure", None,
                        )
                        if callable(consume_failure) and consume_failure():
                            raise MigrationReconciliationError(
                                "MIGRATION_CENSUS_RESERVE_COMMIT_FAILED"
                            )
                    chunk_record["completed_blocks"] += 1
                    previous_slot = int(block_slot)
                    previous_hash = str(block.get("blockhash"))
                    chunk_record["last_produced_slot"] = previous_slot
                    chunk_record[
                        "last_completed_blockhash"
                    ] = previous_hash
                    chunk_record["last_completed_block_time"] = (
                        int(block_time)
                        if isinstance(block_time, int)
                        and not isinstance(block_time, bool)
                        else None
                    )
                counters = adapter.counters()
                chunk_record.update(
                    {
                        "rpc_request_count": counters[
                            "rpc_request_count"
                        ],
                        "rpc_retry_count": counters["rpc_retry_count"],
                        "rpc_rate_limit_count": counters[
                            "rpc_429_count"
                        ],
                        "rpc_timeout_count": counters[
                            "rpc_timeout_count"
                        ],
                        "rpc_error_count": counters["rpc_error_count"],
                        "reconciliation_watermark_after": int(chunk_end),
                        "completion_status": CHUNK_COMPLETE,
                        "runtime_ms": int(
                            (self._monotonic() - chunk_started) * 1000
                        ),
                    }
                )
                self._store.commit_chunk(
                    range_identity=range_identity, chunk=chunk_record
                )
            except (
                RpcBackfillBoundExceeded,
                MigrationReconciliationError,
            ) as exc:
                reason = getattr(exc, "reason", str(exc))
                self._store.note_unresolved(
                    range_identity=range_identity, reason=reason
                )
                return self._store.range_record(range_identity)
        return self._store.range_record(range_identity)


__all__ = (
    "CHECKPOINT_KIND_MIGRATION_RECONCILIATION",
    "MIGRATION_RECONCILIATION_SCHEMA_V1",
    "MIGRATION_RECONCILIATION_RECORD_KIND",
    "MIGRATION_RECONCILIATION_CHECKPOINT_BASENAME",
    "MIGRATION_RECONCILIATION_COVERAGE_BASENAME",
    "MIGRATION_RECONCILIATION_SUMMARY_BASENAME",
    "DEFAULT_RECONCILIATION_CHUNK_SLOTS",
    "CHUNK_COMPLETE",
    "CHUNK_UNRESOLVED",
    "CHUNK_INTERRUPTED",
    "MigrationReconciliationError",
    "reconciliation_range_identity",
    "plan_reconciliation_chunks",
    "MigrationReconciliationStore",
    "ConfirmedMigrationReconciler",
    "validate_reconciliation_state",
)

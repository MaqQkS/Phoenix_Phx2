"""Differential equivalence + throughput benchmark for confirmed-RPC application.

Offline only. The fixture is served from memory, so what is measured is the
CPU-side recovery application path -- prefilter, JSON decode, worker scan,
worker-result validation, parent canonical ordering and parent application
into isolated temporary census/tracker/recovery stores with normal contiguous
checkpointing.  Historical RPC network time, Telegram, Discord and real ledger
I/O are excluded because none of them exist here: no socket is opened, no
delivery transport is constructed and no real ledger path is touched.

Three implementations are exercised over the IDENTICAL fixture:

``reference``
    The unmodified serial implementation loaded from a git blob (by default
    the parent commit of this change). This is the behaviour the parallel path
    must reproduce, not a re-transcription of it.
``serial``
    The current implementation with ``rpc_apply_processes = 1``.
``parallel``
    The current implementation with a bounded worker process pool.

Equivalence is proven per applied transaction (slot, transaction index,
signature, serialized update digest, per-transaction migration/reserve/fee/
duplicate/rejection deltas), per admitted candidate, per admission rejection,
over the final recovery snapshot, over the final reserve/fee index contents
and over the final contiguous committed slot.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import shutil
import statistics
import subprocess
import sys
import time
from dataclasses import is_dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple

REFERENCE_MODULE_NAME = "phx2_reference_rpc_gap_recovery"
REFERENCE_SOURCE_PATH = "PHX2/free_tier_producer/rpc_gap_recovery.py"


# ---------------------------------------------------------------------------
# deterministic digesting
# ---------------------------------------------------------------------------

def stable(value: Any) -> Any:
    """Canonicalise any value into something ``json.dumps`` orders stably."""

    if isinstance(value, Decimal):
        return f"D:{value.normalize():f}"
    if isinstance(value, bytes):
        return "b:" + hashlib.sha256(value).hexdigest()
    if is_dataclass(value) and not isinstance(value, type):
        return {"@": type(value).__name__,
                **{k: stable(v) for k, v in sorted(vars(value).items())}}
    if isinstance(value, Mapping):
        return {str(k): stable(v) for k, v in sorted(
            value.items(), key=lambda kv: str(kv[0]))}
    if isinstance(value, (list, tuple)):
        return [stable(item) for item in value]
    if isinstance(value, set):
        return sorted(str(item) for item in value)
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if hasattr(value, "__dict__"):
        return {"@": type(value).__name__,
                **{k: stable(v) for k, v in sorted(vars(value).items())
                   if not k.startswith("_lock")}}
    return repr(value)


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(
        stable(value), sort_keys=True, default=str).encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# fixture
# ---------------------------------------------------------------------------

class Fixture:
    """The sanitized real sample, fully resident in memory."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.manifest = json.loads(
            (root / "FIXTURE_MANIFEST.json").read_text(encoding="utf-8"))
        self.payloads: Dict[int, bytes] = {}
        self.results: Dict[int, Dict[str, Any]] = {}
        for entry in self.manifest["blocks"]:
            slot = int(entry["slot"])
            payload = (root / "blocks" / f"{slot}.json").read_bytes()
            self.payloads[slot] = payload
            self.results[slot] = json.loads(payload.decode("utf-8"))["result"]
        self.windows: Dict[int, List[int]] = {}
        for entry in self.manifest["blocks"]:
            self.windows.setdefault(
                int(entry["window_index"]), []).append(int(entry["slot"]))
        for slots in self.windows.values():
            slots.sort()

    def window_slots(self, indices: Optional[List[int]] = None) -> List[List[int]]:
        keys = sorted(self.windows) if indices is None else list(indices)
        return [self.windows[key] for key in keys]

    def contiguity_ok(self, slots: List[int]) -> bool:
        for previous, current in zip(slots, slots[1:]):
            if int(self.results[current].get("parentSlot", -1)) != previous:
                return False
        return True

    def overlap_target(self, slots: List[int], program_id: str
                       ) -> Tuple[int, str, int]:
        """Last applicable relevant transaction of the last block in the pass."""

        from PHX2.free_tier_producer.rpc_gap_recovery import (
            build_subscribe_update_from_rpc_transaction,
            rpc_transaction_mentions_program,
        )

        slot = slots[-1]
        chosen: Optional[Tuple[int, str, int]] = None
        for index, tx in enumerate(self.results[slot].get("transactions") or []):
            if not rpc_transaction_mentions_program(tx, program_id):
                continue
            meta = tx.get("meta")
            if not isinstance(meta, Mapping) or meta.get("err") is not None:
                continue
            signatures = (tx.get("transaction") or {}).get("signatures")
            if not isinstance(signatures, list) or not signatures:
                continue
            if build_subscribe_update_from_rpc_transaction(
                    slot=slot, block_time=None, transaction_index=index,
                    tx_json=tx) is None:
                continue
            chosen = (slot, str(signatures[0]), index)
        if chosen is None:
            raise SystemExit(
                f"fixture window ending at slot {slot} has no applicable "
                "relevant transaction to use as an overlap target")
        return chosen


class FixtureTransport:
    """In-memory JSON-RPC transport. No socket, no endpoint, no credential."""

    def __init__(self, fixture: Fixture, slots: List[int], *,
                 raw_capable: bool) -> None:
        self._fixture = fixture
        self._slots = list(slots)
        self._slot_set = set(self._slots)
        self.request_count = 0
        if raw_capable:
            self.supports_raw_bodies = True

    def __call__(self, method: str, params: List[Any], _timeout: float,
                 raw: bool = False) -> Tuple[int, Any]:
        self.request_count += 1
        if method == "getSlot":
            return 200, {"result": self._slots[-1] + 32}
        if method == "getBlocks":
            start, end = int(params[0]), int(params[1])
            return 200, {"result": [s for s in self._slots
                                    if start <= s <= end]}
        if method == "getBlock":
            slot = int(params[0])
            if slot not in self._slot_set:
                return 200, {"error": {"code": -32007, "message": "skipped"}}
            if raw:
                return 200, self._fixture.payloads[slot]
            return 200, {"result": self._fixture.results[slot]}
        return 200, {"error": {"code": -32601, "message": "unknown"}}


# ---------------------------------------------------------------------------
# reference module (unmodified serial implementation from a git blob)
# ---------------------------------------------------------------------------

def load_reference_module(repo_root: Path, revision: str, work_dir: Path):
    blob = subprocess.run(
        ["git", "-C", str(repo_root), "show",
         f"{revision}:{REFERENCE_SOURCE_PATH}"],
        capture_output=True, check=True).stdout
    work_dir.mkdir(parents=True, exist_ok=True)
    path = work_dir / f"{REFERENCE_MODULE_NAME}.py"
    path.write_bytes(blob)
    spec = importlib.util.spec_from_file_location(REFERENCE_MODULE_NAME, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[REFERENCE_MODULE_NAME] = module
    spec.loader.exec_module(module)
    return module, hashlib.sha256(blob).hexdigest()


# ---------------------------------------------------------------------------
# one application pass
# ---------------------------------------------------------------------------

def run_pass(*, module: Any, fixture: Fixture, slots: List[int],
             state_root: Path, processes: int, queue_bound: int,
             batch_size: int, concurrency: int, checkpoint_every: int,
             worker_timeout: float) -> Dict[str, Any]:
    """One complete recovery application pass into ISOLATED temporary state."""

    from PHX2.free_tier_producer import stream_cursor as sc
    from PHX2.free_tier_producer.paid_grpc_source import (
        build_transaction_skip_identity,
    )
    from PHX2.free_tier_producer.phx1_fee_gate import FeeEvidenceIndex
    from PHX2.free_tier_producer.pumpswap_reserves import PumpSwapReserveIndex
    from PHX2.stage29.pumpswap_program_constants import PUMPSWAP_PROGRAM_ID

    identity_digest = sc.compute_subscription_identity_digest(
        source_kind=sc.STREAM_SOURCE_YELLOWSTONE,
        commitment="CONFIRMED",
        transaction_filter_name="phx2_pumpswap_transactions",
        account_include=[PUMPSWAP_PROGRAM_ID],
        program_id=PUMPSWAP_PROGRAM_ID,
        migration_versions_supported=("migrate", "migrate_v2"),
        decoder_schema_version=sc.STREAM_CURSOR_SCHEMA_V1,
    )
    if state_root.exists():
        shutil.rmtree(state_root)
    state_root.mkdir(parents=True)

    boundary = slots[0] - 1
    boundary_sig = "S1gFixtureBoundary"
    # The cursor is configured EXACTLY as the canonical launchers configure it
    # (32 commits / 0.5 s batched persistence). Benchmarking with the pre-fix
    # flush-every-event default would measure checkpoint I/O, not the
    # application throughput this change is about.
    cursor = sc.build_cursor_store(
        state_dir=state_root, subscription_identity_digest=identity_digest,
        persist_batch_max_events=32, persist_batch_max_seconds=0.5)
    cursor.load()
    cursor.commit_event(
        slot=boundary,
        identity=sc.build_stream_event_identity(
            slot=boundary, signature=boundary_sig, transaction_index=0),
        signature=boundary_sig)
    cursor.mark_disconnect()
    cursor.begin_stream_attempt(requested_from_slot=boundary)
    cursor.mark_replay_retention_exceeded()

    config_kwargs = dict(
        mode=module.GAP_RECOVERY_MODE_RPC_BACKFILL,
        authoritative_commitment="confirmed",
        rpc_request_spacing_seconds=0.0000001,
        max_commitment_wait_seconds=5.0,
        max_overlap_wait_seconds=5.0,
        rpc_concurrency=int(concurrency),
        checkpoint_every_blocks=int(checkpoint_every),
        max_backfill_runtime_seconds=3600.0,
    )
    if "rpc_apply_processes" in module.RpcGapRecoveryConfig.__dataclass_fields__:
        config_kwargs.update(
            rpc_apply_processes=int(processes),
            rpc_apply_queue_bound=int(queue_bound),
            rpc_apply_batch_size=int(batch_size),
            rpc_worker_timeout_seconds=float(worker_timeout),
        )
    config = module.RpcGapRecoveryConfig(**config_kwargs)

    recovery_store = module.RpcGapRecoveryStore(state_dir=state_root)
    recovery_store.load()
    buffer = module.QuarantinedLiveBuffer(
        state_dir=state_root, subscription_identity_digest=identity_digest,
        max_events=config.max_quarantine_events,
        max_bytes=config.max_quarantine_bytes,
        max_age_seconds=config.max_quarantine_age_seconds)
    buffer.load()

    reserve_index = PumpSwapReserveIndex(
        canonical_observer_allow_historical=True)
    fee_index = FeeEvidenceIndex()
    rejections: List[Dict[str, Any]] = []
    transport = FixtureTransport(
        fixture, slots, raw_capable=(int(processes) > 1))

    coordinator = module.RpcGapBackfillCoordinator(
        config=config, recovery_store=recovery_store,
        quarantine_buffer=buffer,
        subscription_identity_digest=identity_digest,
        rpc_post_fn=transport,
        reserve_index=reserve_index, fee_index=fee_index,
        admission_sink=lambda record: rejections.append(dict(record)),
        sleep_fn=lambda _s: None)

    target_slot, target_sig, target_index = fixture.overlap_target(
        slots, PUMPSWAP_PROGRAM_ID)
    ok, detail = coordinator.begin_or_resume_episode(
        cursor_store=cursor,
        entry_classification=module.ENTRY_REPLAY_REFUSED_OUT_OF_RANGE)
    if not ok:
        raise SystemExit(f"episode refused: {detail}")
    coordinator.begin_quarantine_segment()
    coordinator.note_observed_transaction(
        slot=target_slot, signature=target_sig,
        transaction_index=target_index,
        skip_identity=build_transaction_skip_identity(
            target_slot, target_sig, target_index),
        attempt_generation=int(cursor.state.attempt_generation))

    trace: List[List[Any]] = []
    candidates: List[Dict[str, Any]] = []
    original = coordinator._process_bridged_update

    def _traced(*, update, slot, signature, transaction_index,
                apply_candidate_fn, counters):
        before = dict(counters)
        outcome = original(
            update=update, slot=slot, signature=signature,
            transaction_index=transaction_index,
            apply_candidate_fn=apply_candidate_fn, counters=counters)
        trace.append([
            int(slot), int(transaction_index), str(signature),
            hashlib.sha256(update.SerializeToString()).hexdigest(),
            outcome,
            counters["migrations"] - before["migrations"],
            counters["reserve_events"] - before["reserve_events"],
            counters["fee_events"] - before["fee_events"],
            counters["duplicates"] - before["duplicates"],
            counters["rejected"] - before["rejected"],
        ])
        return outcome

    coordinator._process_bridged_update = _traced

    started = time.perf_counter()
    proven = coordinator.run_backfill(
        apply_candidate_fn=lambda candidate: (
            candidates.append(dict(candidate)) or True))
    elapsed = time.perf_counter() - started

    snapshot = coordinator.snapshot()
    # ``recovery_config`` is the echo of the INPUT configuration (worker count,
    # queue bound, batch size) and necessarily differs between the serial and
    # parallel passes; it is reported separately rather than digested, because
    # equivalence is a claim about OUTCOMES, not about the knobs. Wall-clock
    # and timestamp fields are excluded for the same reason.
    # Wall-clock telemetry is excluded for the same reason: a faster pass
    # reports a smaller elapsed age for the same buffered entry, which is the
    # measurement succeeding, not the outcome changing.
    def _wall_clock(key: str) -> bool:
        return (key.endswith("_at_utc") or key.endswith("_age_seconds")
                or key.endswith("_runtime_ms") or key.endswith("_seconds"))

    interesting = {
        key: snapshot.get(key) for key in sorted(snapshot)
        if key not in ("catchup", "envelope_digest", "recovery_config")
        and not _wall_clock(key)}
    wall_clock_fields = sorted(
        key for key in snapshot if _wall_clock(key))
    shared_config = {
        key: value
        for key, value in (snapshot.get("recovery_config") or {}).items()
        if not key.startswith(("rpc_apply_", "rpc_worker_"))}
    outcome = {
        "proven": bool(proven),
        "recovery_state": coordinator.state(),
        "terminal_reason": coordinator.terminal_reason(),
        "paused_reason": coordinator.pause_reason(),
        "last_completed_slot": recovery_store.state.last_completed_slot,
        "last_completed_blockhash": recovery_store.state.last_completed_blockhash,
        "produced_blocks_total": recovery_store.state.produced_blocks_total,
        "produced_blocks_completed": (
            recovery_store.state.produced_blocks_completed),
        "skipped_slots_total": recovery_store.state.skipped_slots_total,
        "transactions_scanned": recovery_store.state.transactions_scanned,
        "transactions_relevant": recovery_store.state.transactions_relevant,
        "transactions_rejected": recovery_store.state.transactions_rejected,
        "duplicate_events_suppressed": (
            recovery_store.state.duplicate_events_suppressed),
        "migration_events_recovered": (
            recovery_store.state.migration_events_recovered),
        "reserve_events_recovered": (
            recovery_store.state.reserve_events_recovered),
        "fee_events_recovered": recovery_store.state.fee_events_recovered,
        "overlap_proof_state": recovery_store.state.overlap_proof_state,
        "overlap_skip_identity": recovery_store.state.overlap_skip_identity,
        "cursor_terminal": bool(cursor.is_terminal()),
        "cursor_last_durable_slot": cursor.state.last_durable_slot,
        "cursor_last_durable_identity": cursor.state.last_durable_event_identity,
        "cursor_recovery_generation": cursor.state.recovery_generation,
        "cursor_recovery_status": cursor.state.recovery_status,
        "cursor_overlap_proven_generation": (
            cursor.state.overlap_proven_generation),
        "cursor_replayed_event_count": cursor.state.replayed_event_count,
        "cursor_duplicate_replay_count": cursor.state.duplicate_replay_count,
        "snapshot_subset": interesting,
        "shared_config": shared_config,
        "excluded_wall_clock_fields": wall_clock_fields,
    }
    equivalence = {
        "outcome": outcome,
        "trace": trace,
        "candidates": candidates,
        "rejections": rejections,
        "reserve_index": getattr(reserve_index, "_by_mint", {}),
        "fee_index": getattr(fee_index, "_by_mint", {}),
    }
    ordering_violations = sum(
        1 for a, b in zip(trace, trace[1:])
        if (b[0], b[1]) <= (a[0], a[1]))
    applied_slots = [row[0] for row in trace]
    return {
        "elapsed_seconds": elapsed,
        "blocks": len(slots),
        "applied_transactions": len(trace),
        "ordering_violations": ordering_violations,
        "distinct_applied_slots": len(set(applied_slots)),
        "duplicate_migration_applications": (
            len([row for row in trace if row[5] > 1])),
        "duplicate_candidate_applications": (
            len(candidates) - len({
                (c.get("mint"), c.get("signature"), c.get("slot"))
                for c in candidates}) if candidates else 0),
        "candidates": len(candidates),
        "rejections": len(rejections),
        "digest": digest(equivalence),
        "outcome": outcome,
        "equivalence": equivalence,
        "rpc_requests": transport.request_count,
    }


# ---------------------------------------------------------------------------
# driver
# ---------------------------------------------------------------------------

def peak_rss_mb() -> Optional[float]:
    try:
        import ctypes
        import ctypes.wintypes as wt

        class _COUNTERS(ctypes.Structure):
            _fields_ = [("cb", wt.DWORD), ("PageFaultCount", wt.DWORD),
                        ("PeakWorkingSetSize", ctypes.c_size_t),
                        ("WorkingSetSize", ctypes.c_size_t),
                        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                        ("PagefileUsage", ctypes.c_size_t),
                        ("PeakPagefileUsage", ctypes.c_size_t)]

        counters = _COUNTERS()
        counters.cb = ctypes.sizeof(_COUNTERS)
        ctypes.windll.psapi.GetProcessMemoryInfo(
            ctypes.windll.kernel32.GetCurrentProcess(),
            ctypes.byref(counters), counters.cb)
        return round(counters.PeakWorkingSetSize / (1024 * 1024), 2)
    except Exception:
        return None


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", required=True)
    parser.add_argument("--state-root", required=True,
                        help="isolated temp state root (outside the repo)")
    parser.add_argument("--out", required=True, help="JSON result path")
    parser.add_argument("--reference-revision", default="HEAD")
    parser.add_argument("--processes", type=int, default=0)
    parser.add_argument("--queue-bound", type=int, default=8)
    parser.add_argument("--batch-size", type=int, default=4)
    parser.add_argument("--concurrency", type=int, default=12)
    parser.add_argument("--checkpoint-every", type=int, default=64)
    parser.add_argument("--worker-timeout", type=float, default=120.0)
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument("--windows", type=int, nargs="*", default=None)
    parser.add_argument("--skip-reference", action="store_true")
    args = parser.parse_args(argv)

    repo_root = Path(__file__).resolve().parents[2]
    state_root = Path(args.state_root).resolve()
    try:
        state_root.relative_to(repo_root)
    except ValueError:
        pass
    else:
        print("REFUSED: state root is inside the repository")
        return 2

    from PHX2.free_tier_producer import rpc_gap_recovery as current
    from PHX2.free_tier_producer.rpc_block_pool import default_apply_processes

    processes = int(args.processes) or default_apply_processes()
    fixture = Fixture(Path(args.fixture).resolve())
    windows = fixture.window_slots(args.windows)
    contiguity = [fixture.contiguity_ok(slots) for slots in windows]
    if not all(contiguity):
        print("REFUSED: fixture windows are not parent-chain contiguous")
        return 2

    reference_module = None
    reference_sha = None
    if not args.skip_reference:
        reference_module, reference_sha = load_reference_module(
            repo_root, args.reference_revision, state_root / "_reference")

    def _run_all(module: Any, label: str, procs: int) -> Dict[str, Any]:
        merged_digests: List[str] = []
        totals = {"blocks": 0, "applied_transactions": 0,
                  "ordering_violations": 0,
                  "duplicate_migration_applications": 0,
                  "duplicate_candidate_applications": 0,
                  "candidates": 0, "rejections": 0}
        elapsed = 0.0
        outcomes = []
        for index, slots in enumerate(windows):
            result = run_pass(
                module=module, fixture=fixture, slots=slots,
                state_root=state_root / f"{label}_w{index}",
                processes=procs, queue_bound=int(args.queue_bound),
                batch_size=int(args.batch_size),
                concurrency=int(args.concurrency),
                checkpoint_every=int(args.checkpoint_every),
                worker_timeout=float(args.worker_timeout))
            merged_digests.append(result["digest"])
            elapsed += result["elapsed_seconds"]
            for key in totals:
                totals[key] += result[key]
            outcomes.append(result["outcome"])
        return {
            "label": label, "processes": procs,
            "elapsed_seconds": round(elapsed, 4),
            "blocks_per_second": round(totals["blocks"] / elapsed, 4)
            if elapsed > 0 else 0.0,
            "window_digests": merged_digests,
            "digest": digest(merged_digests),
            "totals": totals,
            "outcomes": outcomes,
        }

    report: Dict[str, Any] = {
        "fixture_manifest_sha256": hashlib.sha256(
            (Path(args.fixture) / "FIXTURE_MANIFEST.json").read_bytes()
        ).hexdigest(),
        "fixture_blocks": sum(len(slots) for slots in windows),
        "fixture_transactions": fixture.manifest["total_transactions"],
        "fixture_relevant_transactions": (
            fixture.manifest["total_relevant_transactions"]),
        "fixture_bytes": fixture.manifest["total_sanitized_bytes"],
        "windows": [len(slots) for slots in windows],
        "window_contiguous": contiguity,
        "reference_revision": args.reference_revision,
        "reference_blob_sha256": reference_sha,
        "configuration": {
            "processes": processes, "queue_bound": int(args.queue_bound),
            "batch_size": int(args.batch_size),
            "concurrency": int(args.concurrency),
            "checkpoint_every_blocks": int(args.checkpoint_every),
            "worker_timeout_seconds": float(args.worker_timeout),
            "cpu_count": os.cpu_count(),
        },
    }

    # ---- differential -----------------------------------------------------
    differential: Dict[str, Any] = {}
    if reference_module is not None:
        differential["reference"] = _run_all(reference_module, "reference", 1)
    differential["serial"] = _run_all(current, "serial", 1)
    differential["parallel"] = _run_all(current, "parallel", processes)
    report["differential"] = {
        key: {k: v for k, v in value.items() if k != "outcomes"}
        for key, value in differential.items()}
    baseline = differential.get("reference") or differential["serial"]
    matches = {
        name: value["digest"] == baseline["digest"]
        for name, value in differential.items()}
    report["serial_parallel_exact_match"] = bool(
        matches.get("parallel") and matches.get("serial", True))
    report["differential_matches"] = matches
    if not report["serial_parallel_exact_match"]:
        for name, value in differential.items():
            for index, (a, b) in enumerate(zip(
                    baseline["window_digests"], value["window_digests"])):
                if a != b:
                    report.setdefault("mismatched_windows", []).append(
                        {"implementation": name, "window": index})
    report["differential_result"] = (
        "SERIAL_PARALLEL_EXACT_MATCH"
        if report["serial_parallel_exact_match"] else "MISMATCH")

    # ---- benchmark --------------------------------------------------------
    runs: List[Dict[str, Any]] = []
    for index in range(int(args.runs) + 1):
        pass_result = _run_all(current, f"bench{index}", processes)
        record = {
            "run": index,
            "warmup": index == 0,
            "elapsed_seconds": pass_result["elapsed_seconds"],
            "blocks": pass_result["totals"]["blocks"],
            "blocks_per_second": pass_result["blocks_per_second"],
            "transactions_per_second": round(
                fixture.manifest["total_transactions"]
                / pass_result["elapsed_seconds"], 1)
            if pass_result["elapsed_seconds"] > 0 else 0.0,
            "digest": pass_result["digest"],
            "digest_matches_baseline": (
                pass_result["digest"] == baseline["digest"]),
            "ordering_violations": (
                pass_result["totals"]["ordering_violations"]),
            "duplicate_migration_applications": (
                pass_result["totals"]["duplicate_migration_applications"]),
            "duplicate_candidate_applications": (
                pass_result["totals"]["duplicate_candidate_applications"]),
            "peak_parent_rss_mb": peak_rss_mb(),
        }
        runs.append(record)
        print(f"run {index}{' (warmup)' if index == 0 else ''}: "
              f"{record['blocks_per_second']} blk/s "
              f"digest_ok={record['digest_matches_baseline']}")
    timed = [record for record in runs if not record["warmup"]]
    rates = sorted(record["blocks_per_second"] for record in timed)
    report["benchmark_runs"] = runs
    report["median_blocks_per_second"] = statistics.median(rates)
    report["p10_blocks_per_second"] = rates[
        max(0, int(round(0.10 * (len(rates) - 1))))]
    report["min_blocks_per_second"] = rates[0]
    report["max_blocks_per_second"] = rates[-1]
    report["chain_growth_blocks_per_second"] = 2.5
    report["chain_growth_margin_blocks_per_second"] = round(
        report["median_blocks_per_second"] - 2.5, 4)
    report["all_runs_digest_match"] = all(
        record["digest_matches_baseline"] for record in runs)
    report["total_ordering_violations"] = sum(
        record["ordering_violations"] for record in runs)
    report["total_duplicate_migration_applications"] = sum(
        record["duplicate_migration_applications"] for record in runs)
    report["total_duplicate_candidate_applications"] = sum(
        record["duplicate_candidate_applications"] for record in runs)
    report["acceptance"] = {
        "median_ge_8_0": report["median_blocks_per_second"] >= 8.0,
        "p10_ge_5_0": report["p10_blocks_per_second"] >= 5.0,
        "min_gt_3_5": report["min_blocks_per_second"] > 3.5,
        "exact_match": report["serial_parallel_exact_match"],
        "zero_ordering_violations": report["total_ordering_violations"] == 0,
        "zero_duplicate_migrations": (
            report["total_duplicate_migration_applications"] == 0),
        "zero_duplicate_candidates": (
            report["total_duplicate_candidate_applications"] == 0),
        "all_runs_digest_match": report["all_runs_digest_match"],
    }
    report["accepted"] = all(report["acceptance"].values())

    Path(args.out).write_text(
        json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(json.dumps({
        "differential_result": report["differential_result"],
        "median_blocks_per_second": report["median_blocks_per_second"],
        "p10_blocks_per_second": report["p10_blocks_per_second"],
        "min_blocks_per_second": report["min_blocks_per_second"],
        "accepted": report["accepted"],
        "acceptance": report["acceptance"],
    }, indent=2))
    return 0 if report["accepted"] else 1


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    raise SystemExit(main())

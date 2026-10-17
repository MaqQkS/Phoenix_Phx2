"""Capture ONE bounded historical confirmed-RPC block fixture, then sanitize it.

Read-only historical RPC only. This tool opens no Yellowstone stream, no
WebSocket, no gRPC channel, no delivery transport and no ledger; it signs
nothing and trades nothing. It exists because prior recovery evidence
preserved metrics but not raw block payloads, which left the application
throughput defect unbenchmarkable offline.

Slot selection is FROZEN and does not look at block contents: four fixed
windows are anchored at 0/4, 1/4, 2/4 and 3/4 of the configured historical
range, and each window takes the first ``--window-blocks`` produced slots that
``getBlocks`` reports for a fixed enumeration span. Blocks are never chosen
for containing migrations, and the capture is never repeated to make a
benchmark look better.

Sanitization replaces every transaction signature with a deterministic
pseudonym that still base58-decodes to 64 bytes, so the production decoder
accepts it unchanged. Everything the application path reads -- ordering,
account keys, instructions, inner instructions, log messages, token balances,
owners, program ids, block identity, density -- is preserved exactly.

Usage (the fixture directory MUST live outside the repository):

    python -m PHX2.scripts.capture_rpc_block_fixture --out C:\\tmp\\phx2_fix_x
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple

SANITIZATION_VERSION = "PHX2_RPC_FIXTURE_SANITIZATION_V1"
DEFAULT_RANGE_START = 435087769
DEFAULT_RANGE_END = 435231678
DEFAULT_WINDOWS = 4
DEFAULT_WINDOW_BLOCKS = 128
#: Slots enumerated per window to find ``window_blocks`` produced slots. Mainnet
#: produces a block for most slots, so this is generous headroom, and it is a
#: FIXED span so the selection cannot drift with observed density.
WINDOW_ENUMERATION_SPAN = 400
MINIMUM_ACCEPTABLE_BLOCKS = 384


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _load_env_file(path: Path) -> Dict[str, str]:
    values: Dict[str, str] = {}
    if not path.is_file():
        return values
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def _pseudonymous_signature(original: str, salt: str) -> str:
    from PHX2.free_tier_producer.paid_grpc_source import _base58_encode

    digest = hashlib.sha512(
        (salt + "|" + original).encode("utf-8")).digest()[:64]
    return _base58_encode(digest)


def _sanitize_result(
    result: Mapping[str, Any], *, salt: str, mapping: Dict[str, str],
) -> Dict[str, Any]:
    """Replace signatures in place-preserving order; touch nothing else."""

    sanitized = dict(result)
    transactions = []
    for tx in result.get("transactions") or []:
        if not isinstance(tx, Mapping):
            transactions.append(tx)
            continue
        tx_copy = dict(tx)
        body = tx.get("transaction")
        if isinstance(body, Mapping):
            body_copy = dict(body)
            signatures = body.get("signatures")
            if isinstance(signatures, list):
                replaced = []
                for signature in signatures:
                    if not isinstance(signature, str) or not signature:
                        replaced.append(signature)
                        continue
                    pseudonym = mapping.get(signature)
                    if pseudonym is None:
                        pseudonym = _pseudonymous_signature(signature, salt)
                        mapping[signature] = pseudonym
                    replaced.append(pseudonym)
                body_copy["signatures"] = replaced
            tx_copy["transaction"] = body_copy
        transactions.append(tx_copy)
    sanitized["transactions"] = transactions
    return sanitized


def _count_relevant(result: Mapping[str, Any], program_id: str) -> Tuple[int, int]:
    from PHX2.free_tier_producer.rpc_gap_recovery import (
        rpc_transaction_mentions_program,
    )

    transactions = result.get("transactions") or []
    relevant = 0
    for tx in transactions:
        if rpc_transaction_mentions_program(tx, program_id):
            relevant += 1
    return len(transactions), relevant


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True,
                        help="fixture directory (MUST be outside the repo)")
    parser.add_argument("--range-start", type=int, default=DEFAULT_RANGE_START)
    parser.add_argument("--range-end", type=int, default=DEFAULT_RANGE_END)
    parser.add_argument("--windows", type=int, default=DEFAULT_WINDOWS)
    parser.add_argument("--window-blocks", type=int,
                        default=DEFAULT_WINDOW_BLOCKS)
    parser.add_argument("--concurrency", type=int, default=8)
    parser.add_argument("--spacing-seconds", type=float, default=0.10)
    parser.add_argument("--env-file", default=None)
    args = parser.parse_args(argv)

    repo_root = Path(__file__).resolve().parents[2]
    out_dir = Path(args.out).resolve()
    try:
        out_dir.relative_to(repo_root)
    except ValueError:
        pass
    else:
        print("REFUSED: fixture directory is inside the repository")
        return 2

    from PHX2.free_tier_producer.rpc_gap_recovery import (
        AUTHORITATIVE_COMMITMENTS,
        GAP_RECOVERY_MODE_RPC_BACKFILL,
        RpcGapRecoveryConfig,
        SolanaRpcBackfillAdapter,
        build_rpc_transport_from_env,
    )
    from PHX2.stage29.pumpswap_program_constants import PUMPSWAP_PROGRAM_ID

    env: Optional[Mapping[str, str]] = None
    if args.env_file:
        env = _load_env_file(Path(args.env_file))
    transport = build_rpc_transport_from_env(env)
    if transport is None:
        print("REFUSED: RPC recovery endpoint absent")
        return 2

    config = RpcGapRecoveryConfig(
        mode=GAP_RECOVERY_MODE_RPC_BACKFILL,
        authoritative_commitment=AUTHORITATIVE_COMMITMENTS[0],
        rpc_request_spacing_seconds=float(args.spacing_seconds),
        rpc_concurrency=int(args.concurrency),
        max_rpc_requests=4096,
    )
    adapter = SolanaRpcBackfillAdapter(
        rpc_post_fn=transport, config=config, timeout_seconds=30.0)
    commitment = AUTHORITATIVE_COMMITMENTS[0]

    span = int(args.range_end) - int(args.range_start)
    if span <= 0 or args.windows <= 0 or args.window_blocks <= 0:
        print("REFUSED: invalid range/window configuration")
        return 2

    started = time.monotonic()
    out_dir.mkdir(parents=True, exist_ok=True)
    raw_dir = out_dir / "raw"
    blocks_dir = out_dir / "blocks"
    raw_dir.mkdir(exist_ok=True)
    blocks_dir.mkdir(exist_ok=True)

    windows: List[Dict[str, Any]] = []
    selected: List[Tuple[int, int]] = []  # (window_index, slot)
    for index in range(int(args.windows)):
        anchor = int(args.range_start) + (span * index) // int(args.windows)
        enum_end = min(int(args.range_end),
                       anchor + WINDOW_ENUMERATION_SPAN - 1)
        produced = adapter.get_blocks(
            start_slot=anchor, end_slot=enum_end, commitment=commitment)
        chosen = produced[:int(args.window_blocks)]
        windows.append({
            "window_index": index,
            "enumeration_start_slot": anchor,
            "enumeration_end_slot": enum_end,
            "produced_in_span": len(produced),
            "selected_blocks": len(chosen),
            "first_slot": chosen[0] if chosen else None,
            "last_slot": chosen[-1] if chosen else None,
            "contiguous_produced": chosen == produced[:len(chosen)],
        })
        for slot in chosen:
            selected.append((index, slot))
        print(f"window {index}: anchor={anchor} produced={len(produced)} "
              f"selected={len(chosen)}")

    print(f"selected {len(selected)} produced slots; fetching payloads")

    def _fetch(item: Tuple[int, int]) -> Tuple[int, int, Optional[bytes], str]:
        window_index, slot = item
        try:
            payload = adapter.get_block_payload(slot=slot,
                                                commitment=commitment)
            return window_index, slot, payload, "OK"
        except Exception as exc:  # noqa: BLE001 -- classification only
            return window_index, slot, None, type(exc).__name__

    fetched: Dict[int, Tuple[int, bytes]] = {}
    failures: List[Dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=int(args.concurrency)) as pool:
        for window_index, slot, payload, status in pool.map(_fetch, selected):
            if payload is None:
                failures.append({"slot": slot, "status": status})
                continue
            fetched[slot] = (window_index, payload)
            (raw_dir / f"{slot}.json").write_bytes(payload)

    print(f"fetched {len(fetched)} / {len(selected)} "
          f"(failures {len(failures)})")

    if len(fetched) < MINIMUM_ACCEPTABLE_BLOCKS:
        (out_dir / "CAPTURE_FAILED.json").write_text(json.dumps({
            "captured": len(fetched), "selected": len(selected),
            "failures": failures[:64],
            "rpc_counters": adapter.counters(),
        }, indent=2), encoding="utf-8")
        print("EVIDENCE_INSUFFICIENT")
        return 3

    salt = SANITIZATION_VERSION
    mapping: Dict[str, str] = {}
    entries: List[Dict[str, Any]] = []
    total_transactions = 0
    total_relevant = 0
    total_bytes = 0
    program_occurrences = 0
    for slot in sorted(fetched):
        window_index, payload = fetched[slot]
        body = json.loads(payload.decode("utf-8"))
        result = body.get("result")
        if not isinstance(result, dict):
            failures.append({"slot": slot, "status": "RESULT_NOT_OBJECT"})
            continue
        sanitized_result = _sanitize_result(result, salt=salt, mapping=mapping)
        sanitized_body = {"jsonrpc": "2.0", "result": sanitized_result,
                          "id": 1}
        sanitized_bytes = json.dumps(
            sanitized_body, separators=(",", ":"),
            ensure_ascii=False).encode("utf-8")
        transactions, relevant = _count_relevant(
            sanitized_result, PUMPSWAP_PROGRAM_ID)
        occurrences = sanitized_bytes.count(PUMPSWAP_PROGRAM_ID.encode("ascii"))
        (blocks_dir / f"{slot}.json").write_bytes(sanitized_bytes)
        entries.append({
            "slot": slot,
            "window_index": window_index,
            "sanitized_sha256": hashlib.sha256(sanitized_bytes).hexdigest(),
            "sanitized_bytes": len(sanitized_bytes),
            "raw_bytes": len(payload),
            "transaction_count": transactions,
            "relevant_transaction_count": relevant,
            "program_occurrences": occurrences,
            "parent_slot": sanitized_result.get("parentSlot"),
        })
        total_transactions += transactions
        total_relevant += relevant
        total_bytes += len(sanitized_bytes)
        program_occurrences += occurrences

    manifest = {
        "fixture_kind": "PHX2_CONFIRMED_RPC_BLOCK_APPLICATION_FIXTURE",
        "sanitization_version": SANITIZATION_VERSION,
        "capture_utc": _utc_stamp(),
        "provider_mode": "CONFIRMED_RPC_HISTORICAL_READ_ONLY",
        "commitment": commitment,
        "encoding": "json/full/maxSupportedTransactionVersion=0/rewards=false",
        "slot_selection_method": {
            "range_start": int(args.range_start),
            "range_end": int(args.range_end),
            "windows": int(args.windows),
            "window_blocks": int(args.window_blocks),
            "enumeration_span": WINDOW_ENUMERATION_SPAN,
            "rule": ("anchor_i = range_start + (span * i) // windows; take the "
                     "first window_blocks produced slots getBlocks reports for "
                     "[anchor_i, anchor_i + enumeration_span - 1]"),
            "content_based_selection": False,
        },
        "windows": windows,
        "block_count": len(entries),
        "slot_list": [entry["slot"] for entry in entries],
        "total_transactions": total_transactions,
        "total_relevant_transactions": total_relevant,
        "relevant_density_pct": (
            round(100.0 * total_relevant / total_transactions, 4)
            if total_transactions else 0.0),
        "mean_transactions_per_block": (
            round(total_transactions / len(entries), 3) if entries else 0.0),
        "total_sanitized_bytes": total_bytes,
        "program_occurrence_total": program_occurrences,
        "relevant_program_id": PUMPSWAP_PROGRAM_ID,
        "signature_pseudonyms": len(mapping),
        "capture_failures": len(failures),
        "rpc_request_count": int(adapter.request_count),
        "rpc_retry_count": int(adapter.retry_count),
        "rpc_timeout_count": int(adapter.timeout_count),
        "rpc_429_count": int(adapter.http_429_count),
        "rpc_error_count": int(adapter.error_count),
        "capture_elapsed_seconds": round(time.monotonic() - started, 3),
        "blocks": entries,
    }
    manifest_bytes = json.dumps(manifest, indent=2).encode("utf-8")
    (out_dir / "FIXTURE_MANIFEST.json").write_bytes(manifest_bytes)

    # Verify the sanitized fixture is complete and deterministic BEFORE the
    # unsanitized capture material is destroyed.
    verified = 0
    for entry in entries:
        path = blocks_dir / f"{entry['slot']}.json"
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != entry["sanitized_sha256"]:
            print(f"VERIFY FAILED for slot {entry['slot']}")
            return 4
        verified += 1
    print(f"verified {verified} sanitized blocks")

    removed = 0
    for path in raw_dir.glob("*.json"):
        path.unlink()
        removed += 1
    raw_dir.rmdir()
    print(f"deleted {removed} unsanitized raw responses")

    print(json.dumps({
        "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "manifest_bytes": len(manifest_bytes),
        "block_count": len(entries),
        "total_transactions": total_transactions,
        "total_relevant_transactions": total_relevant,
        "rpc_request_count": int(adapter.request_count),
        "rpc_429_count": int(adapter.http_429_count),
        "rpc_error_count": int(adapter.error_count),
    }, indent=2))
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    raise SystemExit(main())

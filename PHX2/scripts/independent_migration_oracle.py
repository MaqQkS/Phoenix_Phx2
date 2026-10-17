"""Independent confirmed-block canonical Pump migration oracle.

Recognition operates directly on Solana ``getBlock`` JSON.  It does not call
the production migration-admission, census, reconciliation, or subscribe-
update conversion functions.  Only deterministic PDA primitives are shared.
No raw transaction, response body, endpoint, or signature is written.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import struct
import sys
import time
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

_REPO = Path(__file__).resolve().parents[2]
_PRODUCER = _REPO / "PHX2" / "free_tier_producer"
_COMPAT = _PRODUCER / "compat"
for _path in (_REPO, _PRODUCER, _COMPAT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from PHX2.free_tier_producer import free_tier_session as session  # noqa: E402
from PHX2.free_tier_producer.liquidity_integrity import (  # noqa: E402
    derive_associated_token_address,
    derive_pool_address,
)
from PHX2.free_tier_producer.rpc_gap_recovery import (  # noqa: E402
    build_rpc_transport_from_env,
)


# Independently pinned public program/layout literals.
PUMPFUN_PROGRAM_ID = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
PUMPSWAP_PROGRAM_ID = "pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA"
SYSTEM_PROGRAM_ID = "11111111111111111111111111111111"
TOKEN_PROGRAM_ID = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
TOKEN_2022_PROGRAM_ID = "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"
TOKEN_PROGRAM_IDS = frozenset({TOKEN_PROGRAM_ID, TOKEN_2022_PROGRAM_ID})
ASSOCIATED_TOKEN_PROGRAM_ID = (
    "ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL"
)
WSOL_MINT = "So11111111111111111111111111111111111111112"

CREATE_POOL_DISCRIMINATOR = bytes((233, 146, 209, 142, 207, 104, 64, 188))
MIGRATE_DISCRIMINATORS = {
    bytes((155, 234, 231, 146, 236, 158, 162, 30)): "migrate",
    bytes((187, 203, 18, 31, 206, 237, 254, 41)): "migrate_v2",
}
CREATE_POOL_ACCOUNT_COUNT = 18
CREATE_POOL_DATA_MIN_LEN = 26
CREATE_POOL_IDX_POOL = 0
CREATE_POOL_IDX_CREATOR = 2
CREATE_POOL_IDX_BASE_MINT = 3
CREATE_POOL_IDX_QUOTE_MINT = 4
CREATE_POOL_IDX_BASE_VAULT = 9
CREATE_POOL_IDX_QUOTE_VAULT = 10

_B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


class OracleError(RuntimeError):
    pass


def _b58decode(value: object) -> bytes:
    if not isinstance(value, str) or not value:
        raise ValueError("BASE58_INVALID")
    number = 0
    for char in value:
        digit = _B58.find(char)
        if digit < 0:
            raise ValueError("BASE58_INVALID")
        number = number * 58 + digit
    zeros = len(value) - len(value.lstrip("1"))
    body = (
        number.to_bytes((number.bit_length() + 7) // 8, "big")
        if number
        else b""
    )
    return b"\x00" * zeros + body


def _canonical_json(value: Mapping[str, Any]) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _sha256(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _migration_identity(
    *,
    mint: str,
    pool: str,
    slot: int,
    signature: str,
    outer_index: int,
    inner_index: int,
    flattened_index: int,
    version: str,
) -> str:
    return _sha256(
        {
            "identity_version": "phx2_canonical_migration_identity_v1",
            "mint": mint,
            "pool": pool,
            "migration_slot": int(slot),
            "migration_signature": signature,
            "outer_instruction_index": int(outer_index),
            "inner_instruction_index": int(inner_index),
            "flattened_instruction_index": int(flattened_index),
            "migration_version": version,
        }
    )


def _key_text(value: object) -> Optional[str]:
    if isinstance(value, str) and value:
        return value
    if isinstance(value, Mapping):
        pubkey = value.get("pubkey")
        return pubkey if isinstance(pubkey, str) and pubkey else None
    return None


def _account_keys(
    message: Mapping[str, Any], meta: Mapping[str, Any]
) -> List[str]:
    keys = [
        key
        for key in (_key_text(item) for item in message.get("accountKeys") or [])
        if key is not None
    ]
    loaded = meta.get("loadedAddresses")
    if isinstance(loaded, Mapping):
        for axis in ("writable", "readonly"):
            keys.extend(
                key
                for key in (
                    _key_text(item) for item in loaded.get(axis) or []
                )
                if key is not None
            )
    return keys


def _compiled_instruction(
    value: object, keys: Sequence[str]
) -> Optional[Dict[str, Any]]:
    if not isinstance(value, Mapping):
        return None
    program_index = value.get("programIdIndex")
    accounts = value.get("accounts")
    data = value.get("data")
    if (
        isinstance(program_index, bool)
        or not isinstance(program_index, int)
        or not 0 <= program_index < len(keys)
        or not isinstance(accounts, list)
        or not all(
            isinstance(item, int) and not isinstance(item, bool)
            for item in accounts
        )
        or not isinstance(data, str)
    ):
        return None
    try:
        decoded = _b58decode(data)
    except ValueError:
        return None
    stack = value.get("stackHeight")
    if isinstance(stack, bool) or not isinstance(stack, int) or stack <= 0:
        stack = None
    return {
        "program": keys[program_index],
        "accounts": list(accounts),
        "data": decoded,
        "stack_height": stack,
    }


def _version_for(data: bytes) -> Optional[str]:
    return MIGRATE_DISCRIMINATORS.get(bytes(data[:8])) if len(data) >= 8 else None


def _ancestry_version(
    *,
    top: Optional[Mapping[str, Any]],
    inner: Sequence[Mapping[str, Any]],
    inner_index: int,
) -> Optional[str]:
    if top and top["program"] == PUMPFUN_PROGRAM_ID:
        version = _version_for(top["data"])
        if version:
            return version
    site_height = inner[inner_index].get("stack_height")
    if not isinstance(site_height, int):
        return None
    for candidate_index in range(inner_index - 1, -1, -1):
        candidate = inner[candidate_index]
        height = candidate.get("stack_height")
        if not isinstance(height, int) or height >= site_height:
            continue
        if any(
            isinstance(item.get("stack_height"), int)
            and item["stack_height"] <= height
            for item in inner[candidate_index + 1 : inner_index]
        ):
            continue
        if candidate["program"] != PUMPFUN_PROGRAM_ID:
            return None
        return _version_for(candidate["data"])
    return None


def _token_balances(
    entries: object, keys: Sequence[str]
) -> Dict[str, Dict[str, Any]]:
    result: Dict[str, Dict[str, Any]] = {}
    if not isinstance(entries, list):
        return result
    for item in entries:
        if not isinstance(item, Mapping):
            continue
        index = item.get("accountIndex")
        ui = item.get("uiTokenAmount")
        if (
            isinstance(index, bool)
            or not isinstance(index, int)
            or not 0 <= index < len(keys)
            or not isinstance(ui, Mapping)
        ):
            continue
        amount_text = ui.get("amount")
        decimals = ui.get("decimals")
        try:
            amount = int(amount_text)
        except (TypeError, ValueError):
            continue
        result[keys[index]] = {
            "mint": item.get("mint"),
            "owner": item.get("owner"),
            "amount": amount,
            "decimals": decimals,
        }
    return result


def _recognize_transaction(
    *,
    tx_json: object,
    slot: int,
    block_time: Optional[int],
    min_quote_deposit_sol: Decimal,
) -> List[Dict[str, Any]]:
    if not isinstance(tx_json, Mapping):
        return []
    meta = tx_json.get("meta")
    tx = tx_json.get("transaction")
    if (
        not isinstance(meta, Mapping)
        or meta.get("err") is not None
        or not isinstance(tx, Mapping)
    ):
        return []
    message = tx.get("message")
    signatures = tx.get("signatures")
    if (
        not isinstance(message, Mapping)
        or not isinstance(signatures, list)
        or not signatures
        or not isinstance(signatures[0], str)
    ):
        return []
    signature = signatures[0]
    keys = _account_keys(message, meta)
    top_raw = message.get("instructions")
    if not isinstance(top_raw, list):
        return []
    top = [_compiled_instruction(item, keys) for item in top_raw]
    if any(item is None for item in top):
        return []
    top_instructions: List[Mapping[str, Any]] = [
        item for item in top if item is not None
    ]
    if any(
        item["program"] == PUMPSWAP_PROGRAM_ID
        and item["data"].startswith(CREATE_POOL_DISCRIMINATOR)
        for item in top_instructions
    ):
        return []

    pre = _token_balances(meta.get("preTokenBalances"), keys)
    post = _token_balances(meta.get("postTokenBalances"), keys)
    recognized: List[Dict[str, Any]] = []
    flattened = len(top_instructions)
    groups = meta.get("innerInstructions")
    if not isinstance(groups, list):
        return []
    for group in groups:
        if not isinstance(group, Mapping):
            continue
        outer_index = group.get("index")
        raw_inner = group.get("instructions")
        if (
            isinstance(outer_index, bool)
            or not isinstance(outer_index, int)
            or not 0 <= outer_index < len(top_instructions)
            or not isinstance(raw_inner, list)
        ):
            continue
        parsed_inner = [_compiled_instruction(item, keys) for item in raw_inner]
        if any(item is None for item in parsed_inner):
            flattened += len(raw_inner)
            continue
        inner: List[Mapping[str, Any]] = [
            item for item in parsed_inner if item is not None
        ]
        for inner_index, instruction in enumerate(inner):
            flattened_index = flattened + inner_index
            if not (
                instruction["program"] == PUMPSWAP_PROGRAM_ID
                and instruction["data"].startswith(
                    CREATE_POOL_DISCRIMINATOR
                )
            ):
                continue
            version = _ancestry_version(
                top=top_instructions[outer_index],
                inner=inner,
                inner_index=inner_index,
            )
            if version is None:
                continue
            accounts = instruction["accounts"]
            data = instruction["data"]
            if (
                len(accounts) < CREATE_POOL_ACCOUNT_COUNT
                or len(data) < CREATE_POOL_DATA_MIN_LEN
                or any(not 0 <= index < len(keys) for index in accounts)
            ):
                continue
            resolved = [keys[index] for index in accounts]
            pool = resolved[CREATE_POOL_IDX_POOL]
            creator = resolved[CREATE_POOL_IDX_CREATOR]
            mint_a = resolved[CREATE_POOL_IDX_BASE_MINT]
            mint_b = resolved[CREATE_POOL_IDX_QUOTE_MINT]
            base_vault_a = resolved[CREATE_POOL_IDX_BASE_VAULT]
            quote_vault_a = resolved[CREATE_POOL_IDX_QUOTE_VAULT]
            base_token_program = resolved[13]
            quote_token_program = resolved[14]
            fixed = (
                resolved[11] == SYSTEM_PROGRAM_ID
                and resolved[12] == TOKEN_2022_PROGRAM_ID
                and base_token_program in TOKEN_PROGRAM_IDS
                and quote_token_program in TOKEN_PROGRAM_IDS
                and resolved[15] == ASSOCIATED_TOKEN_PROGRAM_ID
                and resolved[17] == PUMPSWAP_PROGRAM_ID
            )
            if not fixed:
                continue
            if (mint_a == WSOL_MINT) == (mint_b == WSOL_MINT):
                continue
            if mint_a == WSOL_MINT:
                base_mint, quote_mint = mint_b, mint_a
                base_vault, quote_vault = quote_vault_a, base_vault_a
                base_token_program, quote_token_program = (
                    quote_token_program,
                    base_token_program,
                )
            else:
                base_mint, quote_mint = mint_a, mint_b
                base_vault, quote_vault = base_vault_a, quote_vault_a
            try:
                index_arg = struct.unpack_from("<H", data, 8)[0]
                canonical_pool = derive_pool_address(
                    index=index_arg,
                    creator=creator,
                    base_mint=mint_a,
                    quote_mint=mint_b,
                )
                canonical_base_vault = derive_associated_token_address(
                    owner=pool,
                    token_program=base_token_program,
                    mint=base_mint,
                    associated_program=ASSOCIATED_TOKEN_PROGRAM_ID,
                )
                canonical_quote_vault = derive_associated_token_address(
                    owner=pool,
                    token_program=quote_token_program,
                    mint=quote_mint,
                    associated_program=ASSOCIATED_TOKEN_PROGRAM_ID,
                )
            except ValueError:
                continue
            if (
                pool != canonical_pool
                or base_vault != canonical_base_vault
                or quote_vault != canonical_quote_vault
            ):
                continue
            base_post = post.get(base_vault, {})
            quote_post = post.get(quote_vault, {})
            if (
                base_post.get("owner") != pool
                or quote_post.get("owner") != pool
                or (
                    base_post.get("mint") is not None
                    and base_post.get("mint") != base_mint
                )
                or (
                    quote_post.get("mint") is not None
                    and quote_post.get("mint") != quote_mint
                )
            ):
                continue
            quote_post_amount = quote_post.get("amount")
            quote_pre_amount = pre.get(quote_vault, {}).get("amount", 0)
            quote_decimals = quote_post.get("decimals")
            if (
                not isinstance(quote_post_amount, int)
                or not isinstance(quote_pre_amount, int)
                or quote_decimals != 9
            ):
                continue
            quote_delta = quote_post_amount - quote_pre_amount
            if (
                quote_delta <= 0
                or Decimal(quote_delta) / Decimal(1_000_000_000)
                < min_quote_deposit_sol
            ):
                continue
            identity = _migration_identity(
                mint=base_mint,
                pool=pool,
                slot=slot,
                signature=signature,
                outer_index=outer_index,
                inner_index=inner_index,
                flattened_index=flattened_index,
                version=version,
            )
            recognized.append(
                {
                    "record_kind": "PHX2_INDEPENDENT_CANONICAL_MIGRATION",
                    "census_identity": identity,
                    "mint": base_mint,
                    "canonical_pool": pool,
                    "migration_slot": int(slot),
                    "migration_block_time": block_time,
                    "migration_version": version,
                    "migration_signature_digest": hashlib.sha256(
                        signature.encode("utf-8")
                    ).hexdigest(),
                    "outer_instruction_index": int(outer_index),
                    "inner_instruction_index": int(inner_index),
                    "flattened_instruction_index": int(flattened_index),
                    "canonical_pda_result": True,
                    "vault_derivation_result": True,
                    "vault_ownership_result": True,
                }
            )
        flattened += len(inner)
    return recognized


def _remove_delivery_environment() -> int:
    removed = session.harden_no_send_env(
        allow_birdeye_fallback=False, allow_paid_provider=True
    )
    for key in list(os.environ):
        if any(
            term in key.upper()
            for term in (
                "DISCORD",
                "TELEGRAM",
                "WEBHOOK",
                "WALLET",
                "PRIVATE_KEY",
                "PRIVKEY",
                "SIGNER",
            )
        ):
            os.environ.pop(key, None)
            removed += 1
    return removed


class IndependentRpc:
    def __init__(
        self,
        post,
        *,
        max_requests: int,
        max_retries: int,
        spacing_seconds: float,
        timeout_seconds: float,
    ) -> None:
        self._post = post
        self.max_requests = int(max_requests)
        self.max_retries = int(max_retries)
        self.spacing = float(spacing_seconds)
        self.timeout = float(timeout_seconds)
        self.requests = 0
        self.retries = 0
        self.rate_limits = 0
        self.timeouts = 0
        self.errors = 0

    def call(self, method: str, params: List[Any]) -> Any:
        for attempt in range(self.max_retries + 1):
            if self.requests >= self.max_requests:
                raise OracleError("ORACLE_RPC_REQUEST_LIMIT_EXCEEDED")
            if self.requests and self.spacing > 0:
                time.sleep(self.spacing)
            self.requests += 1
            status, body = self._post(method, params, self.timeout)
            if status == 200 and isinstance(body, Mapping):
                if "error" in body:
                    self.errors += 1
                    raise OracleError("ORACLE_RPC_RESULT_ERROR")
                return body.get("result")
            if status == 429:
                self.rate_limits += 1
            elif status == 0:
                self.timeouts += 1
            else:
                self.errors += 1
            if attempt >= self.max_retries:
                raise OracleError("ORACLE_RPC_RETRIES_EXHAUSTED")
            self.retries += 1
            time.sleep(min(2.0, 0.25 * (2**attempt)))
        raise OracleError("ORACLE_RPC_UNREACHABLE")

    def counters(self) -> Dict[str, int]:
        return {
            "rpc_request_count": self.requests,
            "rpc_retry_count": self.retries,
            "rpc_rate_limit_count": self.rate_limits,
            "rpc_timeout_count": self.timeouts,
            "rpc_error_count": self.errors,
        }


def _read_census(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    rows: List[Dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            value = json.loads(line)
            if isinstance(value, dict):
                rows.append(value)
    return rows


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        _canonical_json(value) + "\n", encoding="utf-8", newline="\n"
    )
    os.replace(temporary, path)


def _write_jsonl(path: Path, values: Iterable[Mapping[str, Any]]) -> None:
    text = "".join(_canonical_json(value) + "\n" for value in values)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(text, encoding="utf-8", newline="\n")
    os.replace(temporary, path)


def run(args: argparse.Namespace) -> int:
    active_env = Path(args.env).resolve()
    if active_env != (_REPO / ".env").resolve():
        print("REFUSED:ACTIVE_REPOSITORY_ENV_REQUIRED")
        return 2
    session.sess.load_env_file(str(active_env))
    removed = _remove_delivery_environment()
    post = build_rpc_transport_from_env()
    if post is None:
        print("REFUSED:CONFIRMED_RPC_TRANSPORT_MISSING")
        return 2
    threshold_text = os.environ.get(
        "PHX2_MIGRATION_MIN_QUOTE_DEPOSIT_SOL", "50"
    )
    try:
        threshold = Decimal(threshold_text)
    except (InvalidOperation, ValueError):
        print("REFUSED:MIGRATION_DEPOSIT_THRESHOLD_INVALID")
        return 2
    if not threshold.is_finite() or threshold < 0:
        print("REFUSED:MIGRATION_DEPOSIT_THRESHOLD_INVALID")
        return 2

    start = int(args.start_slot)
    end = int(args.end_slot)
    if start < 0 or end < start:
        print("REFUSED:ORACLE_RANGE_INVALID")
        return 2
    artifact_dir = Path(args.artifact_dir)
    artifact_dir.mkdir(parents=True, exist_ok=True)
    rpc = IndependentRpc(
        post,
        max_requests=int(args.max_rpc_requests),
        max_retries=int(args.max_retries_per_request),
        spacing_seconds=float(args.request_spacing_seconds),
        timeout_seconds=float(args.timeout_seconds),
    )
    produced: List[int] = []
    chunks: List[Dict[str, Any]] = []
    cursor = start
    while cursor <= end:
        chunk_end = min(end, cursor + int(args.chunk_slots) - 1)
        result = rpc.call(
            "getBlocks",
            [
                cursor,
                chunk_end,
                {"commitment": "confirmed"},
            ],
        )
        if not isinstance(result, list) or not all(
            isinstance(slot, int) and not isinstance(slot, bool)
            for slot in result
        ):
            raise OracleError("ORACLE_GETBLOCKS_RESULT_INVALID")
        produced.extend(result)
        chunks.append(
            {
                "range_start": cursor,
                "range_end": chunk_end,
                "commitment": "confirmed",
                "produced_blocks": len(result),
                "completion_status": "ENUMERATED",
            }
        )
        cursor = chunk_end + 1

    migrations: List[Dict[str, Any]] = []
    unresolved: List[int] = []
    inspected = 0
    previous_slot: Optional[int] = None
    previous_hash: Optional[str] = None
    for slot in produced:
        try:
            block = rpc.call(
                "getBlock",
                [
                    slot,
                    {
                        "commitment": "confirmed",
                        "encoding": "json",
                        "transactionDetails": "full",
                        "rewards": False,
                        "maxSupportedTransactionVersion": 0,
                    },
                ],
            )
        except OracleError:
            unresolved.append(slot)
            continue
        if not isinstance(block, Mapping):
            unresolved.append(slot)
            continue
        if previous_slot is not None and (
            block.get("parentSlot") != previous_slot
            or (
                previous_hash is not None
                and block.get("previousBlockhash") != previous_hash
            )
        ):
            raise OracleError("ORACLE_FORK_INCONSISTENT")
        block_time = block.get("blockTime")
        transactions = block.get("transactions")
        if not isinstance(transactions, list):
            unresolved.append(slot)
            continue
        for tx_json in transactions:
            migrations.extend(
                _recognize_transaction(
                    tx_json=tx_json,
                    slot=slot,
                    block_time=(
                        block_time
                        if isinstance(block_time, int)
                        and not isinstance(block_time, bool)
                        else None
                    ),
                    min_quote_deposit_sol=threshold,
                )
            )
        inspected += 1
        previous_slot = slot
        previous_hash = (
            str(block.get("blockhash"))
            if isinstance(block.get("blockhash"), str)
            else None
        )

    identity_counts: Dict[str, int] = {}
    for row in migrations:
        identity = str(row["census_identity"])
        identity_counts[identity] = identity_counts.get(identity, 0) + 1
    duplicate_oracle = sum(count - 1 for count in identity_counts.values())
    unique_migrations = {
        str(row["census_identity"]): row for row in migrations
    }
    census = _read_census(Path(args.census_path))
    census_counts: Dict[str, int] = {}
    for row in census:
        identity = str(row.get("census_identity") or "")
        census_counts[identity] = census_counts.get(identity, 0) + 1
    oracle_ids = set(unique_migrations)
    census_ids = {identity for identity in census_counts if identity}
    missing = sorted(oracle_ids - census_ids)
    unexpected = sorted(census_ids - oracle_ids)
    duplicate_census = sum(count - 1 for count in census_counts.values())
    source_counts = {"LIVE_GRPC": 0, "RPC_RECONCILIATION": 0, "BOTH": 0}
    for row in census:
        source = row.get("discovery_source")
        if source in source_counts:
            source_counts[source] += 1

    summary = {
        "kind": "PHX2_INDEPENDENT_CONFIRMED_BLOCK_MIGRATION_ORACLE",
        "oracle_implementation": (
            "RAW_GETBLOCK_JSON_INDEPENDENT_RECOGNIZER_V1"
        ),
        "production_admission_called": False,
        "production_census_called": False,
        "production_reconciliation_called": False,
        "commitment": "confirmed",
        "range_start": start,
        "range_end": end,
        "produced_blocks_total": len(produced),
        "produced_blocks_inspected": inspected,
        "explicitly_unavailable_blocks": 0,
        "skipped_nonproduced_slots": (end - start + 1) - len(produced),
        "unresolved_blocks": len(unresolved),
        "canonical_migrations_by_independent_scan": len(oracle_ids),
        "live_only": source_counts["LIVE_GRPC"],
        "reconciliation_only": source_counts["RPC_RECONCILIATION"],
        "found_by_both": source_counts["BOTH"],
        "missing_from_census": len(missing),
        "unexpected_in_census": len(unexpected),
        "duplicate_oracle_identities": duplicate_oracle,
        "duplicate_census_identities": duplicate_census,
        "oracle_identity_digests": sorted(oracle_ids),
        "missing_identity_digests": missing,
        "unexpected_identity_digests": unexpected,
        "chunks": chunks,
        **rpc.counters(),
        "delivery_environment_entries_removed": removed,
        "maximum_send_capable_transports": 0,
        "delivery_attempts": 0,
        "real_sends": 0,
        "verdict": (
            "INDEPENDENT_ORACLE_MATCH"
            if (
                not unresolved
                and not missing
                and not unexpected
                and duplicate_oracle == 0
                and duplicate_census == 0
                and inspected == len(produced)
            )
            else "INDEPENDENT_ORACLE_MISMATCH"
        ),
    }
    _write_jsonl(
        artifact_dir / "independent_migration_oracle_migrations.jsonl",
        unique_migrations.values(),
    )
    _write_json(
        artifact_dir / "independent_migration_oracle_summary.json",
        summary,
    )
    print(summary["verdict"])
    print(
        f"range={start}-{end} produced={len(produced)} "
        f"inspected={inspected} unresolved={len(unresolved)} "
        f"migrations={len(oracle_ids)} missing={len(missing)} "
        f"duplicates={duplicate_census}"
    )
    return 0 if summary["verdict"] == "INDEPENDENT_ORACLE_MATCH" else 3


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--env", required=True)
    parser.add_argument("--artifact-dir", required=True)
    parser.add_argument("--census-path", required=True)
    parser.add_argument("--start-slot", type=int, required=True)
    parser.add_argument("--end-slot", type=int, required=True)
    parser.add_argument("--chunk-slots", type=int, default=1500)
    parser.add_argument("--max-rpc-requests", type=int, default=12000)
    parser.add_argument("--max-retries-per-request", type=int, default=3)
    parser.add_argument("--request-spacing-seconds", type=float, default=0.25)
    parser.add_argument("--timeout-seconds", type=float, default=20.0)
    return parser


if __name__ == "__main__":
    try:
        raise SystemExit(run(build_parser().parse_args()))
    except OracleError as exc:
        print(f"INDEPENDENT_ORACLE_UNRESOLVED:{exc}")
        raise SystemExit(3)

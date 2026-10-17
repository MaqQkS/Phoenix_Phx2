"""Standalone Helius Developer replacement proof helpers.

This module is deliberately outside every production runtime path.  It can:

* load only the four Helius values from an explicitly supplied environment file;
* construct authenticated HTTP/WSS URLs without exposing them through repr;
* build and validate the documented ``transactionSubscribe`` contract;
* adapt Helius JSON transaction envelopes into PHX2's existing migration
  decoder input shape;
* account for uncompressed notification bytes and documented credits;
* perform bounded, no-send HTTP/WSS capability and comparison probes.

It cannot start PHX2, construct Telegram/Discord transports, or write the
production ledger/state.  Full provider transaction bodies remain in memory
only for the duration of decoding and are never returned by the public probe
results.
"""

from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, Iterable, Mapping, MutableMapping, Optional, Sequence
from urllib import error as urllib_error
from urllib import parse as urllib_parse
from urllib import request as urllib_request

from PHX2.free_tier_producer.migration_admission import (
    MIGRATION_VERSION_V1,
    MIGRATION_VERSION_V2,
    PUMPFUN_PROGRAM_ID,
    TransactionExecutionStatus,
    classify_transaction_execution_status,
    evaluate_migration_admission,
)
from PHX2.stage29.pumpswap_program_constants import PUMPSWAP_PROGRAM_ID
from PHX2.config.secret_env import load_secret_environment


HELIUS_ENV_NAMES = (
    "HELIUS_API_KEY",
    "HELIUS_RPC_URL",
    "HELIUS_WS_URL",
    "HELIUS_GRPC_ENDPOINT",
)

HELIUS_HTTP_AVAILABLE = "HELIUS_HTTP_AVAILABLE"
HELIUS_WSS_AVAILABLE = "HELIUS_WSS_AVAILABLE"
AUTH_FAILURE = "AUTH_FAILURE"
PLAN_FORBIDDEN = "PLAN_FORBIDDEN"
RATE_LIMITED = "RATE_LIMITED"
PROTOCOL_INVALID = "PROTOCOL_INVALID"
NETWORK_FAILURE = "NETWORK_FAILURE"

FILTER_CONTROL = "CONTROL"
FILTER_TIGHT = "TIGHT"

CLASS_MIGRATE = MIGRATION_VERSION_V1
CLASS_MIGRATE_V2 = MIGRATION_VERSION_V2
CLASS_NON_MIGRATION = "non_migration"
CLASS_DECODE_FAILURE = "decode_failure"

STREAM_CREDITS_PER_100KB = 2
STREAM_BILLING_BYTES = 100_000
DEVELOPER_MONTHLY_CREDITS = 10_000_000
GTFA_FULL_MIN_CREDITS = 10
GTFA_FULL_RESULTS_PER_CREDIT_BLOCK = 100

DEFAULT_MAX_RAW_BYTES = 256_000_000
DEFAULT_PING_INTERVAL_SECONDS = 30
DEFAULT_PING_TIMEOUT_SECONDS = 20


class ProbeConfigurationError(ValueError):
    """The explicit probe configuration is missing or unsafe."""


class ProbeProtocolError(RuntimeError):
    """A provider response violates the expected bounded probe contract."""


class _SecretString:
    """String wrapper whose repr/str never reveals its value."""

    __slots__ = ("_value",)

    def __init__(self, value: str) -> None:
        self._value = str(value)

    def reveal(self) -> str:
        return self._value

    def __bool__(self) -> bool:
        return bool(self._value)

    def __repr__(self) -> str:
        return "<REDACTED>"

    def __str__(self) -> str:
        return "<REDACTED>"


@dataclass(frozen=True)
class HeliusProbeConfig:
    """Secret-bearing configuration with a redaction-safe representation."""

    api_key: _SecretString = field(repr=False)
    rpc_base_url: _SecretString = field(repr=False)
    ws_base_url: _SecretString = field(repr=False)
    legacy_grpc_endpoint_present: bool

    def __repr__(self) -> str:
        return (
            "HeliusProbeConfig("
            "api_key=<REDACTED>, rpc_base_url=<REDACTED>, "
            "ws_base_url=<REDACTED>, "
            f"legacy_grpc_endpoint_present={self.legacy_grpc_endpoint_present})"
        )

    def sanitized_presence(self) -> Dict[str, str]:
        return {
            "HELIUS_API_KEY": "PRESENT",
            "HELIUS_RPC_URL": "PRESENT",
            "HELIUS_WS_URL": "PRESENT",
            "HELIUS_GRPC_ENDPOINT": (
                "PRESENT_LEGACY_IGNORED"
                if self.legacy_grpc_endpoint_present
                else "MISSING"
            ),
        }


def load_helius_probe_config(
    *,
    env_path: Optional[Path] = None,
    environ: Optional[Mapping[str, str]] = None,
) -> HeliusProbeConfig:
    """Load Helius settings with process env precedence and validate bases.

    Only the four Helius names are read from ``env_path``.  Values are never
    logged, interpolated, or placed into exception messages.
    """

    values = load_secret_environment(
        env_path=env_path,
        names=HELIUS_ENV_NAMES,
        environ=environ,
    )
    required = ("HELIUS_API_KEY", "HELIUS_RPC_URL", "HELIUS_WS_URL")
    if any(not values.get(name, "").strip() for name in required):
        raise ProbeConfigurationError("required Helius probe setting is missing")
    key = values["HELIUS_API_KEY"].strip()
    rpc = values["HELIUS_RPC_URL"].strip()
    wss = values["HELIUS_WS_URL"].strip()
    _validate_base_url(rpc, expected_scheme="https", api_key=key)
    _validate_base_url(wss, expected_scheme="wss", api_key=key)
    return HeliusProbeConfig(
        api_key=_SecretString(key),
        rpc_base_url=_SecretString(rpc),
        ws_base_url=_SecretString(wss),
        legacy_grpc_endpoint_present=bool(
            values.get("HELIUS_GRPC_ENDPOINT", "").strip()
        ),
    )


def _validate_base_url(
    base_url: str, *, expected_scheme: str, api_key: str
) -> None:
    try:
        parsed = urllib_parse.urlsplit(base_url)
    except ValueError as exc:
        raise ProbeConfigurationError("Helius base URL is invalid") from exc
    if (
        parsed.scheme.lower() != expected_scheme
        or not parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise ProbeConfigurationError("Helius base URL contract is unsafe")
    if api_key and api_key in base_url:
        raise ProbeConfigurationError("Helius base URL embeds the configured key")


def build_authenticated_url(
    base_url: str, api_key: str, *, expected_scheme: str
) -> str:
    """Append the Helius key internally after enforcing a query-free base."""

    _validate_base_url(base_url, expected_scheme=expected_scheme, api_key=api_key)
    parsed = urllib_parse.urlsplit(base_url)
    return urllib_parse.urlunsplit(
        (parsed.scheme, parsed.netloc, parsed.path or "/", "api-key=" + api_key, "")
    )


def redact_url(value: object) -> str:
    """Return a URL with userinfo/query/fragment removed."""

    if not isinstance(value, str):
        return "<REDACTED_URL>"
    try:
        parsed = urllib_parse.urlsplit(value)
    except ValueError:
        return "<REDACTED_URL>"
    if not parsed.scheme or not parsed.hostname:
        return "<REDACTED_URL>"
    port = f":{parsed.port}" if parsed.port is not None else ""
    return urllib_parse.urlunsplit(
        (parsed.scheme, f"{parsed.hostname}{port}", parsed.path or "/", "", "")
    )


def redact_text(text: object, *, secrets: Sequence[str] = ()) -> str:
    """Best-effort redaction for exception/status text at output boundaries."""

    out = str(text)
    for secret in secrets:
        if secret:
            out = out.replace(secret, "<REDACTED>")
    # Remove complete HTTP/WSS URLs, including any query strings.
    words = out.split()
    safe_words = []
    for word in words:
        trimmed = word.strip("\"'(),[]{}")
        if trimmed.startswith(("https://", "wss://", "http://", "ws://")):
            safe_words.append(word.replace(trimmed, redact_url(trimmed)))
        else:
            safe_words.append(word)
    return " ".join(safe_words)


def build_transaction_subscribe_request(
    *,
    request_id: int,
    filter_label: str,
    pump_program_id: str = PUMPFUN_PROGRAM_ID,
    pumpswap_program_id: str = PUMPSWAP_PROGRAM_ID,
) -> Dict[str, object]:
    """Build the documented confirmed/full transaction subscription."""

    if filter_label == FILTER_CONTROL:
        transaction_filter: Dict[str, object] = {
            "failed": False,
            "vote": False,
            "accountInclude": [pump_program_id],
        }
    elif filter_label == FILTER_TIGHT:
        transaction_filter = {
            "failed": False,
            "vote": False,
            "accountRequired": [pump_program_id, pumpswap_program_id],
        }
    else:
        raise ValueError("unknown Helius comparison filter")
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": "transactionSubscribe",
        "params": [
            transaction_filter,
            {
                "commitment": "confirmed",
                "encoding": "jsonParsed",
                "transactionDetails": "full",
                "showRewards": False,
                "maxSupportedTransactionVersion": 0,
            },
        ],
    }


def validate_numeric_subscription_response(
    response: object, *, request_id: int
) -> int:
    if not isinstance(response, Mapping):
        raise ProbeProtocolError("subscription response is not an object")
    if response.get("jsonrpc") != "2.0" or response.get("id") != request_id:
        raise ProbeProtocolError("subscription response identity mismatch")
    if "error" in response:
        raise ProbeProtocolError("subscription rejected")
    result = response.get("result")
    if isinstance(result, bool) or not isinstance(result, (int, float)):
        raise ProbeProtocolError("subscription id is not numeric")
    if isinstance(result, float) and not result.is_integer():
        raise ProbeProtocolError("subscription id is not an integer")
    return int(result)


def build_transaction_unsubscribe_request(
    *, request_id: int, subscription_id: int
) -> Dict[str, object]:
    if isinstance(subscription_id, bool) or not isinstance(subscription_id, int):
        raise ValueError("subscription_id must be an int")
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": "transactionUnsubscribe",
        "params": [subscription_id],
    }


def validate_unsubscribe_response(response: object, *, request_id: int) -> bool:
    return bool(
        isinstance(response, Mapping)
        and response.get("jsonrpc") == "2.0"
        and response.get("id") == request_id
        and response.get("result") is True
        and "error" not in response
    )


def uncompressed_json_bytes(raw_message: object) -> int:
    if isinstance(raw_message, bytes):
        return len(raw_message)
    if isinstance(raw_message, str):
        return len(raw_message.encode("utf-8"))
    return len(
        json.dumps(
            raw_message, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")
    )


def estimated_stream_credits(byte_count: int) -> float:
    if isinstance(byte_count, bool) or not isinstance(byte_count, int) or byte_count < 0:
        raise ValueError("byte_count must be a non-negative int")
    return byte_count * STREAM_CREDITS_PER_100KB / STREAM_BILLING_BYTES


def billing_granule_upper_bound(byte_count: int) -> int:
    if byte_count == 0:
        return 0
    return math.ceil(byte_count / STREAM_BILLING_BYTES) * STREAM_CREDITS_PER_100KB


def gtfa_full_credits(returned_transactions: int) -> int:
    if (
        isinstance(returned_transactions, bool)
        or not isinstance(returned_transactions, int)
        or returned_transactions < 0
    ):
        raise ValueError("returned_transactions must be a non-negative int")
    return max(
        GTFA_FULL_MIN_CREDITS,
        math.ceil(returned_transactions / GTFA_FULL_RESULTS_PER_CREDIT_BLOCK)
        * GTFA_FULL_MIN_CREDITS,
    )


def build_slot_bounded_gtfa_request(
    *,
    request_id: int,
    address: str,
    slot_gte: int,
    slot_lte: int,
    limit: int,
    pagination_token: Optional[str] = None,
) -> Dict[str, object]:
    if (
        isinstance(slot_gte, bool)
        or isinstance(slot_lte, bool)
        or not isinstance(slot_gte, int)
        or not isinstance(slot_lte, int)
        or slot_gte < 0
        or slot_lte < slot_gte
    ):
        raise ValueError("slot range is invalid")
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
        raise ValueError("full transaction page limit must be in [1, 100]")
    options: Dict[str, object] = {
        "transactionDetails": "full",
        "encoding": "json",
        "maxSupportedTransactionVersion": 0,
        "sortOrder": "asc",
        "commitment": "confirmed",
        "limit": limit,
        "filters": {
            "slot": {"gte": slot_gte, "lte": slot_lte},
            "status": "succeeded",
            "tokenAccounts": "none",
        },
    }
    if pagination_token:
        options["paginationToken"] = pagination_token
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": "getTransactionsForAddress",
        "params": [address, options],
    }


def _b58decode_checked(
    value: object, *, expected_length: Optional[int] = None
) -> bytes:
    if not isinstance(value, str) or not value:
        raise ProbeProtocolError("base58 value is missing")
    alphabet = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
    number = 0
    for char in value:
        digit = alphabet.find(char)
        if digit < 0:
            raise ProbeProtocolError("base58 value is invalid")
        number = number * 58 + digit
    zeros = len(value) - len(value.lstrip("1"))
    body = (
        number.to_bytes((number.bit_length() + 7) // 8, "big")
        if number
        else b""
    )
    decoded = b"\x00" * zeros + body
    if expected_length is not None and len(decoded) != expected_length:
        raise ProbeProtocolError("base58 value length is invalid")
    return decoded


def _account_key_text(value: object) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, Mapping) and isinstance(value.get("pubkey"), str):
        return str(value["pubkey"])
    raise ProbeProtocolError("account key shape is invalid")


def _instruction_namespace(
    instruction: object,
    *,
    key_texts: MutableMapping[str, int],
    ordered_keys: list[str],
) -> SimpleNamespace:
    if not isinstance(instruction, Mapping):
        raise ProbeProtocolError("instruction shape is invalid")

    def key_index(key: str) -> int:
        if key not in key_texts:
            key_texts[key] = len(ordered_keys)
            ordered_keys.append(key)
        return key_texts[key]

    program_index = instruction.get("programIdIndex")
    if isinstance(program_index, bool) or not isinstance(program_index, int):
        program_id = instruction.get("programId")
        if not isinstance(program_id, str):
            raise ProbeProtocolError("instruction program is unresolved")
        program_index = key_index(program_id)

    accounts_raw = instruction.get("accounts", [])
    if not isinstance(accounts_raw, list):
        raise ProbeProtocolError("instruction accounts are invalid")
    account_indices: list[int] = []
    for account in accounts_raw:
        if isinstance(account, bool):
            raise ProbeProtocolError("instruction account index is invalid")
        if isinstance(account, int):
            if not 0 <= account <= 255:
                raise ProbeProtocolError("instruction account index is out of range")
            account_indices.append(account)
        elif isinstance(account, str):
            index = key_index(account)
            if index > 255:
                raise ProbeProtocolError("resolved account index is out of range")
            account_indices.append(index)
        else:
            raise ProbeProtocolError("instruction account is unresolved")

    data = instruction.get("data", "")
    data_bytes = _b58decode_checked(data) if data else b""
    namespace = SimpleNamespace(
        program_id_index=program_index,
        accounts=bytes(account_indices),
        data=data_bytes,
    )
    stack_height = instruction.get("stackHeight")
    if isinstance(stack_height, int) and not isinstance(stack_height, bool):
        namespace.stack_height = stack_height
    return namespace


def _token_balance_namespace(balance: object) -> SimpleNamespace:
    if not isinstance(balance, Mapping):
        raise ProbeProtocolError("token balance shape is invalid")
    token_amount = balance.get("uiTokenAmount")
    if not isinstance(token_amount, Mapping):
        token_amount = {}
    return SimpleNamespace(
        account_index=balance.get("accountIndex"),
        owner=balance.get("owner"),
        mint=balance.get("mint"),
        ui_token_amount=SimpleNamespace(
            amount=token_amount.get("amount"),
            decimals=token_amount.get("decimals"),
        ),
    )


def helius_envelope_to_decoder_update(envelope: object) -> SimpleNamespace:
    """Adapt WSS/gTFA JSON into the existing PHX2 migration decoder shape."""

    if not isinstance(envelope, Mapping):
        raise ProbeProtocolError("transaction envelope is not an object")
    slot = envelope.get("slot")
    if isinstance(slot, bool) or not isinstance(slot, int) or slot < 0:
        raise ProbeProtocolError("transaction slot is missing")

    transaction_container = envelope.get("transaction")
    meta: object
    transaction: object
    if (
        isinstance(transaction_container, Mapping)
        and isinstance(transaction_container.get("transaction"), Mapping)
        and isinstance(transaction_container.get("meta"), Mapping)
    ):
        transaction = transaction_container["transaction"]
        meta = transaction_container["meta"]
    elif isinstance(transaction_container, Mapping) and isinstance(
        envelope.get("meta"), Mapping
    ):
        transaction = transaction_container
        meta = envelope["meta"]
    else:
        raise ProbeProtocolError("transaction or meta is missing")
    if not isinstance(transaction, Mapping) or not isinstance(meta, Mapping):
        raise ProbeProtocolError("transaction or meta is malformed")
    message = transaction.get("message")
    if not isinstance(message, Mapping):
        raise ProbeProtocolError("transaction message is missing")
    signatures = transaction.get("signatures")
    signature = envelope.get("signature")
    if not isinstance(signature, str):
        if isinstance(signatures, list) and signatures and isinstance(signatures[0], str):
            signature = signatures[0]
        else:
            raise ProbeProtocolError("transaction signature is missing")

    raw_keys = message.get("accountKeys")
    if not isinstance(raw_keys, list) or not raw_keys:
        raise ProbeProtocolError("transaction account keys are missing")
    ordered_keys = [_account_key_text(value) for value in raw_keys]
    key_texts: Dict[str, int] = {
        value: index for index, value in enumerate(ordered_keys)
    }
    instructions_raw = message.get("instructions")
    if not isinstance(instructions_raw, list):
        raise ProbeProtocolError("transaction instructions are missing")
    instructions = [
        _instruction_namespace(
            instruction, key_texts=key_texts, ordered_keys=ordered_keys
        )
        for instruction in instructions_raw
    ]

    inner_groups = []
    inner_raw = meta.get("innerInstructions", [])
    if not isinstance(inner_raw, list):
        raise ProbeProtocolError("inner instructions are malformed")
    for group in inner_raw:
        if not isinstance(group, Mapping) or not isinstance(
            group.get("instructions"), list
        ):
            raise ProbeProtocolError("inner instruction group is malformed")
        inner_groups.append(
            SimpleNamespace(
                index=group.get("index"),
                instructions=[
                    _instruction_namespace(
                        instruction,
                        key_texts=key_texts,
                        ordered_keys=ordered_keys,
                    )
                    for instruction in group["instructions"]
                ],
            )
        )

    account_key_objects_include_loaded = any(
        isinstance(value, Mapping) and value.get("source") == "lookupTable"
        for value in raw_keys
    )
    loaded = meta.get("loadedAddresses", {})
    if not isinstance(loaded, Mapping):
        loaded = {}
    loaded_writable = [] if account_key_objects_include_loaded else [
        _b58decode_checked(value, expected_length=32)
        for value in loaded.get("writable", [])
    ]
    loaded_readonly = [] if account_key_objects_include_loaded else [
        _b58decode_checked(value, expected_length=32)
        for value in loaded.get("readonly", [])
    ]

    meta_namespace = SimpleNamespace(
        err=None,
        log_messages=list(meta.get("logMessages") or []),
        loaded_writable_addresses=loaded_writable,
        loaded_readonly_addresses=loaded_readonly,
        inner_instructions=inner_groups,
        pre_token_balances=[
            _token_balance_namespace(item)
            for item in (meta.get("preTokenBalances") or [])
        ],
        post_token_balances=[
            _token_balance_namespace(item)
            for item in (meta.get("postTokenBalances") or [])
        ],
    )
    if meta.get("err") is not None:
        meta_namespace.err = SimpleNamespace(err=b"\x01")

    # ``ordered_keys`` may have been extended while adapting jsonParsed custom
    # instructions.  The resulting indices are now identical to the namespace.
    message_namespace = SimpleNamespace(
        account_keys=[
            _b58decode_checked(value, expected_length=32)
            for value in ordered_keys
        ],
        instructions=instructions,
        header=SimpleNamespace(num_required_signatures=1),
    )
    tx_info = SimpleNamespace(
        signature=_b58decode_checked(signature, expected_length=64),
        transaction=SimpleNamespace(message=message_namespace),
        meta=meta_namespace,
    )
    update = SimpleNamespace(
        transaction=SimpleNamespace(slot=slot, transaction=tx_info)
    )
    update.HasField = lambda name: name == "transaction"
    return update


def resolved_update_account_texts(update: object) -> tuple[str, ...]:
    """Return public account keys (static + loaded) from a decoder update."""

    try:
        tx_info = update.transaction.transaction
        message = tx_info.transaction.message
        meta = tx_info.meta
        keys = list(message.account_keys)
        keys.extend(list(getattr(meta, "loaded_writable_addresses", ()) or ()))
        keys.extend(list(getattr(meta, "loaded_readonly_addresses", ()) or ()))
    except Exception:
        return ()
    # The production helper is private by design; base58 round-tripping through
    # the public decoder keeps this standalone probe independent of that helper.
    out = []
    for raw in keys:
        out.append(_b58encode(bytes(raw)))
    return tuple(out)


def offline_filter_match(
    update: object, *, filter_label: str
) -> bool:
    """Model documented server filters over one authoritative fixture."""

    if getattr(update, "is_vote", False) is True:
        return False
    try:
        meta = update.transaction.transaction.meta
    except Exception:
        return False
    if classify_transaction_execution_status(meta) is not (
        TransactionExecutionStatus.SUCCESS
    ):
        return False
    keys = set(resolved_update_account_texts(update))
    if filter_label == FILTER_CONTROL:
        return PUMPFUN_PROGRAM_ID in keys
    if filter_label == FILTER_TIGHT:
        return PUMPFUN_PROGRAM_ID in keys and PUMPSWAP_PROGRAM_ID in keys
    raise ValueError("unknown Helius comparison filter")


@dataclass(frozen=True)
class LocalClassification:
    classification: str
    reject_reason: Optional[str]
    slot: Optional[int]
    signature_hash: Optional[str]
    signature: Optional[str] = field(default=None, repr=False)


def signature_hash(signature: str) -> str:
    return hashlib.sha256(signature.encode("ascii")).hexdigest()[:20]


def _b58encode(value: bytes) -> str:
    alphabet = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
    number = int.from_bytes(value, "big")
    encoded = ""
    while number:
        number, remainder = divmod(number, 58)
        encoded = alphabet[remainder] + encoded
    leading = len(value) - len(value.lstrip(b"\0"))
    return "1" * leading + (encoded or ("" if leading else "1"))


def _update_source_identity(update: object) -> tuple[Optional[int], Optional[str]]:
    try:
        wrapper = update.transaction
        tx_info = wrapper.transaction
        slot = int(wrapper.slot)
        signature = _b58encode(bytes(tx_info.signature))
    except Exception:
        return None, None
    return slot, signature


def classify_decoder_update(update: object) -> LocalClassification:
    """Make the current PHX2 decoder the final migration authority."""

    source_slot, source_signature = _update_source_identity(update)
    decision = evaluate_migration_admission(update)
    if decision is None:
        return LocalClassification(
            classification=CLASS_NON_MIGRATION,
            reject_reason=None,
            slot=source_slot,
            signature_hash=(
                signature_hash(source_signature) if source_signature else None
            ),
            signature=source_signature,
        )
    sig = decision.transaction_signature or source_signature
    if decision.admitted and decision.migration_version in (
        CLASS_MIGRATE,
        CLASS_MIGRATE_V2,
    ):
        return LocalClassification(
            classification=str(decision.migration_version),
            reject_reason=None,
            slot=decision.slot,
            signature_hash=signature_hash(sig) if sig else None,
            signature=sig,
        )
    return LocalClassification(
        classification=CLASS_DECODE_FAILURE,
        reject_reason=(
            ",".join(decision.reason_codes)
            if decision.reason_codes
            else "MIGRATION_REJECTED"
        ),
        slot=decision.slot,
        signature_hash=signature_hash(sig) if sig else None,
        signature=sig,
    )


def classify_helius_envelope(envelope: object) -> LocalClassification:
    try:
        update = helius_envelope_to_decoder_update(envelope)
    except ProbeProtocolError as exc:
        slot = (
            envelope.get("slot")
            if isinstance(envelope, Mapping)
            and isinstance(envelope.get("slot"), int)
            and not isinstance(envelope.get("slot"), bool)
            else None
        )
        sig = (
            envelope.get("signature")
            if isinstance(envelope, Mapping)
            and isinstance(envelope.get("signature"), str)
            else None
        )
        return LocalClassification(
            classification=CLASS_DECODE_FAILURE,
            reject_reason=str(exc),
            slot=slot,
            signature_hash=signature_hash(sig) if sig else None,
            signature=sig,
        )
    return classify_decoder_update(update)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _provider_error_classification(
    *, status: Optional[int] = None, message: str = ""
) -> str:
    lowered = message.lower()
    if status == 401 or "unauthorized" in lowered or "invalid api key" in lowered:
        return AUTH_FAILURE
    if status == 403 or "forbidden" in lowered or "upgrade" in lowered:
        return PLAN_FORBIDDEN
    if status == 429 or "rate limit" in lowered or "too many requests" in lowered:
        return RATE_LIMITED
    if status is not None and 400 <= status < 500:
        return PROTOCOL_INVALID
    return NETWORK_FAILURE


@dataclass(frozen=True)
class CapabilityResult:
    verdict: str
    latency_ms: int
    jsonrpc_shape_valid: bool
    subscription_numeric: bool = False
    unsubscribed: bool = False
    keepalive_ok: bool = False
    sanitized_error: Optional[str] = None


def http_json_rpc_call(
    config: HeliusProbeConfig,
    payload: Mapping[str, object],
    *,
    timeout_seconds: float = 15.0,
) -> tuple[int, Mapping[str, object], int]:
    """One authenticated JSON-RPC call.  The completed URL is never returned."""

    from time import monotonic

    url = build_authenticated_url(
        config.rpc_base_url.reveal(),
        config.api_key.reveal(),
        expected_scheme="https",
    )
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    req = urllib_request.Request(
        url,
        data=body,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    started = monotonic()
    try:
        with urllib_request.urlopen(req, timeout=timeout_seconds) as response:
            status = int(response.status)
            raw = response.read()
    finally:
        # Drop the only local completed-URL reference as soon as the request
        # finishes; callers receive status/body/latency only.
        url = ""
    latency_ms = max(0, round((monotonic() - started) * 1000))
    parsed = json.loads(raw)
    if not isinstance(parsed, Mapping):
        raise ProbeProtocolError("JSON-RPC response is not an object")
    return status, parsed, latency_ms


def run_http_capability_probe(config: HeliusProbeConfig) -> CapabilityResult:
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "getHealth",
        "params": [],
    }
    try:
        status, response, latency = http_json_rpc_call(config, payload)
    except urllib_error.HTTPError as exc:
        verdict = _provider_error_classification(status=int(exc.code))
        return CapabilityResult(verdict, 0, False, sanitized_error=verdict)
    except (urllib_error.URLError, TimeoutError, OSError) as exc:
        verdict = _provider_error_classification(message=type(exc).__name__)
        return CapabilityResult(verdict, 0, False, sanitized_error=verdict)
    except (json.JSONDecodeError, ProbeProtocolError):
        return CapabilityResult(PROTOCOL_INVALID, 0, False, sanitized_error=PROTOCOL_INVALID)
    shape = (
        status == 200
        and response.get("jsonrpc") == "2.0"
        and response.get("id") == 1
        and ("result" in response or "error" in response)
    )
    if not shape:
        return CapabilityResult(PROTOCOL_INVALID, latency, False)
    if "error" in response:
        error_obj = response.get("error")
        message = (
            str(error_obj.get("message", ""))
            if isinstance(error_obj, Mapping)
            else ""
        )
        verdict = _provider_error_classification(message=message)
        return CapabilityResult(verdict, latency, True, sanitized_error=verdict)
    return CapabilityResult(HELIUS_HTTP_AVAILABLE, latency, True)


async def _recv_response_for_id(
    websocket: Any, *, request_id: int, timeout_seconds: float
) -> Mapping[str, object]:
    deadline = asyncio.get_running_loop().time() + timeout_seconds
    while True:
        remaining = deadline - asyncio.get_running_loop().time()
        if remaining <= 0:
            raise TimeoutError("JSON-RPC response timed out")
        raw = await asyncio.wait_for(websocket.recv(), timeout=remaining)
        parsed = json.loads(raw)
        if isinstance(parsed, Mapping) and parsed.get("id") == request_id:
            return parsed


async def run_wss_capability_probe(
    config: HeliusProbeConfig,
) -> CapabilityResult:
    """Connect, ping, subscribe, validate, unsubscribe, and close."""

    from time import monotonic
    import websockets

    url = build_authenticated_url(
        config.ws_base_url.reveal(),
        config.api_key.reveal(),
        expected_scheme="wss",
    )
    started = monotonic()
    try:
        async with websockets.connect(
            url,
            open_timeout=15,
            close_timeout=10,
            ping_interval=None,
            max_size=16 * 1024 * 1024,
        ) as websocket:
            url = ""
            await send_keepalive(websocket)
            keepalive_ok = True
            request_id = 101
            await websocket.send(
                json.dumps(
                    build_transaction_subscribe_request(
                        request_id=request_id, filter_label=FILTER_TIGHT
                    ),
                    separators=(",", ":"),
                )
            )
            response = await _recv_response_for_id(
                websocket, request_id=request_id, timeout_seconds=15
            )
            subscription_id = validate_numeric_subscription_response(
                response, request_id=request_id
            )
            unsubscribe_id = 102
            await websocket.send(
                json.dumps(
                    build_transaction_unsubscribe_request(
                        request_id=unsubscribe_id,
                        subscription_id=subscription_id,
                    ),
                    separators=(",", ":"),
                )
            )
            unsub_response = await _recv_response_for_id(
                websocket, request_id=unsubscribe_id, timeout_seconds=15
            )
            unsubscribed = validate_unsubscribe_response(
                unsub_response, request_id=unsubscribe_id
            )
        latency = max(0, round((monotonic() - started) * 1000))
        if not unsubscribed:
            return CapabilityResult(
                PROTOCOL_INVALID,
                latency,
                True,
                subscription_numeric=True,
                keepalive_ok=keepalive_ok,
            )
        return CapabilityResult(
            HELIUS_WSS_AVAILABLE,
            latency,
            True,
            subscription_numeric=True,
            unsubscribed=True,
            keepalive_ok=keepalive_ok,
        )
    except Exception as exc:
        # Never surface exception text: handshake errors can contain the URL.
        name = type(exc).__name__
        status = getattr(exc, "status_code", None)
        verdict = _provider_error_classification(status=status, message=name)
        if isinstance(exc, ProbeProtocolError):
            verdict = PROTOCOL_INVALID
        return CapabilityResult(verdict, 0, False, sanitized_error=verdict)
    finally:
        url = ""


async def send_keepalive(
    websocket: Any, *, timeout_seconds: float = DEFAULT_PING_TIMEOUT_SECONDS
) -> None:
    """Send one protocol ping and require its pong within the safe timeout."""

    pong_waiter = await websocket.ping()
    await asyncio.wait_for(pong_waiter, timeout=timeout_seconds)


@dataclass
class FilterMetrics:
    notifications: int = 0
    raw_bytes: int = 0
    migrate: int = 0
    migrate_v2: int = 0
    non_migration: int = 0
    decode_failures: int = 0
    reject_reasons: Dict[str, int] = field(default_factory=dict)
    migration_signature_hashes: set[str] = field(default_factory=set)

    def record(
        self, *, raw_bytes: int, classification: LocalClassification
    ) -> None:
        self.notifications += 1
        self.raw_bytes += raw_bytes
        if classification.classification == CLASS_MIGRATE:
            self.migrate += 1
        elif classification.classification == CLASS_MIGRATE_V2:
            self.migrate_v2 += 1
        elif classification.classification == CLASS_NON_MIGRATION:
            self.non_migration += 1
        else:
            self.decode_failures += 1
            reason = classification.reject_reason or "UNKNOWN_DECODE_FAILURE"
            self.reject_reasons[reason] = self.reject_reasons.get(reason, 0) + 1
        if (
            classification.classification in (CLASS_MIGRATE, CLASS_MIGRATE_V2)
            and classification.signature_hash
        ):
            self.migration_signature_hashes.add(
                classification.signature_hash
            )

    def sanitized_dict(self) -> Dict[str, object]:
        migrations = self.migrate + self.migrate_v2
        return {
            "notifications": self.notifications,
            "raw_uncompressed_bytes": self.raw_bytes,
            "migrate": self.migrate,
            "migrate_v2": self.migrate_v2,
            "valid_migrations": migrations,
            "non_migration": self.non_migration,
            "decode_failures": self.decode_failures,
            "decode_failure_reasons": dict(sorted(self.reject_reasons.items())),
            "bytes_per_migration": (
                self.raw_bytes / migrations if migrations else None
            ),
            "estimated_credits": estimated_stream_credits(self.raw_bytes),
            "billing_granule_upper_bound": billing_granule_upper_bound(
                self.raw_bytes
            ),
        }


@dataclass(frozen=True)
class SanitizedNotificationEvidence:
    subscription_label: str
    slot: Optional[int]
    signature_hash: Optional[str]
    received_at_utc: str
    raw_uncompressed_json_bytes: int
    local_instruction_classification: str
    reject_reason: Optional[str]


@dataclass(frozen=True)
class LiveComparisonResult:
    verdict: str
    elapsed_seconds: float
    raw_byte_ceiling: int
    stopped_by_byte_ceiling: bool
    reconnects: int
    control: Mapping[str, object]
    tight: Mapping[str, object]
    migrations_missed_by_tight: tuple[str, ...]
    tight_byte_reduction_percent: Optional[float]
    tight_credit_reduction_percent: Optional[float]
    evidence: tuple[SanitizedNotificationEvidence, ...]
    sanitized_error: Optional[str] = None


async def _subscribe_pair(
    websocket: Any, *, generation: int
) -> tuple[Dict[int, str], tuple[object, ...]]:
    """Subscribe both filters together and retain interleaved notifications."""

    request_labels: Dict[int, str] = {}
    responses: Dict[int, Mapping[str, object]] = {}
    pending_notifications: list[object] = []
    for offset, label in enumerate((FILTER_CONTROL, FILTER_TIGHT), start=1):
        request_id = generation * 100 + offset
        request_labels[request_id] = label
        await websocket.send(
            json.dumps(
                build_transaction_subscribe_request(
                    request_id=request_id, filter_label=label
                ),
                separators=(",", ":"),
            )
        )
    deadline = asyncio.get_running_loop().time() + 15
    while len(responses) < len(request_labels):
        remaining = deadline - asyncio.get_running_loop().time()
        if remaining <= 0:
            raise TimeoutError("subscription responses timed out")
        raw = await asyncio.wait_for(websocket.recv(), timeout=remaining)
        try:
            parsed = json.loads(raw)
        except (json.JSONDecodeError, UnicodeDecodeError):
            pending_notifications.append(raw)
            continue
        response_id = parsed.get("id") if isinstance(parsed, Mapping) else None
        if (
            isinstance(response_id, int)
            and not isinstance(response_id, bool)
            and response_id in request_labels
        ):
            responses[response_id] = parsed
        else:
            pending_notifications.append(raw)

    mapping: Dict[int, str] = {}
    for request_id, label in request_labels.items():
        subscription_id = validate_numeric_subscription_response(
            responses[request_id], request_id=request_id
        )
        mapping[subscription_id] = label
    if len(mapping) != 2:
        raise ProbeProtocolError("subscription ids are not distinct")
    return mapping, tuple(pending_notifications)


async def _unsubscribe_pair(
    websocket: Any, mapping: Mapping[int, str], *, generation: int
) -> None:
    for offset, subscription_id in enumerate(tuple(mapping), start=1):
        request_id = generation * 100 + 50 + offset
        await websocket.send(
            json.dumps(
                build_transaction_unsubscribe_request(
                    request_id=request_id,
                    subscription_id=subscription_id,
                ),
                separators=(",", ":"),
            )
        )
        response = await _recv_response_for_id(
            websocket, request_id=request_id, timeout_seconds=10
        )
        if not validate_unsubscribe_response(response, request_id=request_id):
            raise ProbeProtocolError("unsubscribe failed")


async def run_live_comparison(
    config: HeliusProbeConfig,
    *,
    duration_seconds: int,
    max_raw_bytes: int = DEFAULT_MAX_RAW_BYTES,
    max_reconnects: int = 2,
) -> LiveComparisonResult:
    """Run one bounded, two-subscription, no-send live comparison."""

    import websockets

    if (
        isinstance(duration_seconds, bool)
        or not isinstance(duration_seconds, int)
        or not 1 <= duration_seconds <= 3600
    ):
        raise ValueError("duration_seconds must be in [1, 3600]")
    if (
        isinstance(max_raw_bytes, bool)
        or not isinstance(max_raw_bytes, int)
        or max_raw_bytes < 1
    ):
        raise ValueError("max_raw_bytes must be positive")

    url = build_authenticated_url(
        config.ws_base_url.reveal(),
        config.api_key.reveal(),
        expected_scheme="wss",
    )
    loop = asyncio.get_running_loop()
    started = loop.time()
    deadline = started + duration_seconds
    metrics = {
        FILTER_CONTROL: FilterMetrics(),
        FILTER_TIGHT: FilterMetrics(),
    }
    evidence: list[SanitizedNotificationEvidence] = []
    reconnects = 0
    generation = 0
    stopped_by_ceiling = False
    sanitized_error: Optional[str] = None
    verdict = HELIUS_WSS_AVAILABLE

    def record_notification(
        raw: object, subscription_map: Mapping[int, str]
    ) -> None:
        byte_count = uncompressed_json_bytes(raw)
        try:
            message = json.loads(raw)
        except (json.JSONDecodeError, UnicodeDecodeError, TypeError):
            return
        if not isinstance(message, Mapping):
            return
        params = message.get("params")
        if not isinstance(params, Mapping):
            return
        subscription_id = params.get("subscription")
        label = subscription_map.get(subscription_id)
        if label is None:
            # Current-generation mapping only: stale ids are ignored.
            return
        envelope = params.get("result")
        classification = classify_helius_envelope(envelope)
        metrics[label].record(
            raw_bytes=byte_count, classification=classification
        )
        evidence.append(
            SanitizedNotificationEvidence(
                subscription_label=label,
                slot=classification.slot,
                signature_hash=classification.signature_hash,
                received_at_utc=_utc_now(),
                raw_uncompressed_json_bytes=byte_count,
                local_instruction_classification=(
                    classification.classification
                ),
                reject_reason=classification.reject_reason,
            )
        )

    while loop.time() < deadline:
        generation += 1
        try:
            async with websockets.connect(
                url,
                open_timeout=15,
                close_timeout=10,
                ping_interval=DEFAULT_PING_INTERVAL_SECONDS,
                ping_timeout=DEFAULT_PING_TIMEOUT_SECONDS,
                max_size=32 * 1024 * 1024,
            ) as websocket:
                subscription_map, pending_notifications = await _subscribe_pair(
                    websocket, generation=generation
                )
                for pending in pending_notifications:
                    record_notification(pending, subscription_map)
                while loop.time() < deadline:
                    total_bytes = sum(item.raw_bytes for item in metrics.values())
                    if total_bytes >= max_raw_bytes:
                        stopped_by_ceiling = True
                        break
                    remaining = deadline - loop.time()
                    try:
                        raw = await asyncio.wait_for(
                            websocket.recv(), timeout=min(remaining, 35)
                        )
                    except asyncio.TimeoutError:
                        pong = await websocket.ping()
                        await asyncio.wait_for(
                            pong, timeout=DEFAULT_PING_TIMEOUT_SECONDS
                        )
                        continue
                    record_notification(raw, subscription_map)
                await _unsubscribe_pair(
                    websocket, subscription_map, generation=generation
                )
                if stopped_by_ceiling or loop.time() >= deadline:
                    break
        except Exception as exc:
            reconnects += 1
            if reconnects > max_reconnects:
                status = getattr(exc, "status_code", None)
                verdict = (
                    PROTOCOL_INVALID
                    if isinstance(exc, ProbeProtocolError)
                    else _provider_error_classification(
                        status=status, message=type(exc).__name__
                    )
                )
                sanitized_error = verdict
                break
            await asyncio.sleep(min(2**reconnects, 5))

    url = ""
    elapsed = max(0.0, loop.time() - started)
    control = metrics[FILTER_CONTROL]
    tight = metrics[FILTER_TIGHT]
    missed = tuple(
        sorted(
            control.migration_signature_hashes
            - tight.migration_signature_hashes
        )
    )
    byte_reduction = (
        (control.raw_bytes - tight.raw_bytes) * 100 / control.raw_bytes
        if control.raw_bytes
        else None
    )
    credit_control = estimated_stream_credits(control.raw_bytes)
    credit_tight = estimated_stream_credits(tight.raw_bytes)
    credit_reduction = (
        (credit_control - credit_tight) * 100 / credit_control
        if credit_control
        else None
    )
    return LiveComparisonResult(
        verdict=verdict,
        elapsed_seconds=elapsed,
        raw_byte_ceiling=max_raw_bytes,
        stopped_by_byte_ceiling=stopped_by_ceiling,
        reconnects=reconnects,
        control=control.sanitized_dict(),
        tight=tight.sanitized_dict(),
        migrations_missed_by_tight=missed,
        tight_byte_reduction_percent=byte_reduction,
        tight_credit_reduction_percent=credit_reduction,
        evidence=tuple(evidence),
        sanitized_error=sanitized_error,
    )


def project_credits(
    *, byte_count: int, elapsed_seconds: float, recovery_credits_monthly: int = 0
) -> Dict[str, float]:
    if elapsed_seconds <= 0:
        raise ValueError("elapsed_seconds must be positive")
    observed_credits = estimated_stream_credits(byte_count)
    per_minute = observed_credits * 60 / elapsed_seconds
    per_hour = per_minute * 60
    per_day = per_hour * 24
    per_30_days = per_day * 30 + recovery_credits_monthly
    return {
        "observed_stream_credits": observed_credits,
        "credits_per_minute": per_minute,
        "credits_per_hour": per_hour,
        "projected_credits_per_day": per_day,
        "projected_credits_per_30_days": per_30_days,
        "developer_quota_percent": (
            per_30_days * 100 / DEVELOPER_MONTHLY_CREDITS
        ),
        "developer_headroom_remaining": (
            DEVELOPER_MONTHLY_CREDITS - per_30_days
        ),
    }


def _entry_signature(entry: object) -> Optional[str]:
    if not isinstance(entry, Mapping):
        return None
    direct = entry.get("signature")
    if isinstance(direct, str) and direct:
        return direct
    transaction = entry.get("transaction")
    if isinstance(transaction, Mapping):
        signatures = transaction.get("signatures")
        if (
            isinstance(signatures, list)
            and signatures
            and isinstance(signatures[0], str)
            and signatures[0]
        ):
            return signatures[0]
    return None


def recovery_entry_identity(entry: object) -> Optional[tuple[int, int, str]]:
    if not isinstance(entry, Mapping):
        return None
    slot = entry.get("slot")
    index = entry.get("transactionIndex", -1)
    signature = _entry_signature(entry)
    if (
        isinstance(slot, bool)
        or not isinstance(slot, int)
        or slot < 0
        or isinstance(index, bool)
        or not isinstance(index, int)
        or index < -1
        or signature is None
    ):
        return None
    return slot, index, signature


def validate_gtfa_page(
    response: object,
    *,
    request_id: int,
    slot_gte: int,
    slot_lte: int,
) -> tuple[list[Mapping[str, object]], int, Optional[str]]:
    """Validate one page and reject any server result outside the local bound."""

    if (
        not isinstance(response, Mapping)
        or response.get("jsonrpc") != "2.0"
        or response.get("id") != request_id
        or "error" in response
    ):
        raise ProbeProtocolError("getTransactionsForAddress response is invalid")
    result = response.get("result")
    if not isinstance(result, Mapping) or not isinstance(result.get("data"), list):
        raise ProbeProtocolError("getTransactionsForAddress result is invalid")
    accepted: list[Mapping[str, object]] = []
    rejected = 0
    for entry in result["data"]:
        if not isinstance(entry, Mapping):
            rejected += 1
            continue
        slot = entry.get("slot")
        if (
            isinstance(slot, bool)
            or not isinstance(slot, int)
            or not slot_gte <= slot <= slot_lte
        ):
            rejected += 1
            continue
        accepted.append(entry)
    token = result.get("paginationToken")
    if token is not None and (not isinstance(token, str) or not token):
        raise ProbeProtocolError("pagination token is invalid")
    return accepted, rejected, token


def dedupe_recovery_entries(
    entries: Iterable[Mapping[str, object]],
) -> tuple[list[Mapping[str, object]], int]:
    """Stable idempotence by exact signature."""

    seen: set[str] = set()
    unique: list[Mapping[str, object]] = []
    duplicates = 0
    for entry in entries:
        signature = _entry_signature(entry)
        if signature is None:
            continue
        if signature in seen:
            duplicates += 1
            continue
        seen.add(signature)
        unique.append(entry)
    return unique, duplicates


def gtfa_page_identity(entries: Iterable[Mapping[str, object]]) -> tuple[
    tuple[int, int, str], ...
]:
    identities = []
    for entry in entries:
        identity = recovery_entry_identity(entry)
        if identity is None:
            raise ProbeProtocolError("recovery entry identity is malformed")
        identities.append(identity)
    return tuple(identities)


@dataclass(frozen=True)
class RecoveryRangeResult:
    verdict: str
    slot_gte: int
    slot_lte: int
    request_count: int
    page_count: int
    result_count: int
    unique_result_count: int
    duplicate_results_suppressed: int
    wrong_slot_results_rejected: int
    pagination_deterministic: bool
    pagination_exhausted: bool
    bounded: bool
    migrations_decoded: int
    migrate: int
    migrate_v2: int
    decode_failures: int
    known_signature_returned: Optional[bool]
    known_slot_matched: Optional[bool]
    known_decoder_parity: Optional[bool]
    estimated_credits: int
    signature_hashes: tuple[str, ...]
    sanitized_error: Optional[str] = None


def run_slot_range_recovery(
    config: HeliusProbeConfig,
    *,
    address: str,
    slot_gte: int,
    slot_lte: int,
    page_size: int,
    max_pages: int,
    known_signature: Optional[str] = None,
    repeat_first_page: bool = True,
) -> RecoveryRangeResult:
    """Bounded exact-slot recovery through Helius ``getTransactionsForAddress``."""

    if (
        isinstance(max_pages, bool)
        or not isinstance(max_pages, int)
        or not 1 <= max_pages <= 20
    ):
        raise ValueError("max_pages must be in [1, 20]")
    all_entries: list[Mapping[str, object]] = []
    request_count = 0
    page_count = 0
    wrong_slot = 0
    pagination_deterministic = True
    pagination_exhausted = False
    token: Optional[str] = None
    first_identity: Optional[tuple[tuple[int, int, str], ...]] = None
    estimated_credits_total = 0

    try:
        for page_index in range(max_pages):
            request_id = 7000 + page_index
            request = build_slot_bounded_gtfa_request(
                request_id=request_id,
                address=address,
                slot_gte=slot_gte,
                slot_lte=slot_lte,
                limit=page_size,
                pagination_token=token,
            )
            _status, response, _latency = http_json_rpc_call(config, request)
            request_count += 1
            accepted, rejected, next_token = validate_gtfa_page(
                response,
                request_id=request_id,
                slot_gte=slot_gte,
                slot_lte=slot_lte,
            )
            estimated_credits_total += gtfa_full_credits(len(accepted) + rejected)
            wrong_slot += rejected
            page_count += 1
            identity = gtfa_page_identity(accepted)
            if page_index == 0:
                first_identity = identity
                if repeat_first_page:
                    repeat_request = build_slot_bounded_gtfa_request(
                        request_id=request_id + 100,
                        address=address,
                        slot_gte=slot_gte,
                        slot_lte=slot_lte,
                        limit=page_size,
                    )
                    _status2, repeated, _latency2 = http_json_rpc_call(
                        config, repeat_request
                    )
                    request_count += 1
                    repeated_entries, repeated_rejected, repeated_token = (
                        validate_gtfa_page(
                            repeated,
                            request_id=request_id + 100,
                            slot_gte=slot_gte,
                            slot_lte=slot_lte,
                        )
                    )
                    estimated_credits_total += gtfa_full_credits(
                        len(repeated_entries) + repeated_rejected
                    )
                    wrong_slot += repeated_rejected
                    pagination_deterministic = bool(
                        gtfa_page_identity(repeated_entries) == first_identity
                        and repeated_token == next_token
                    )
                    # Include the repeated page so idempotence is proved by the
                    # same stable dedupe path used for reconnect overlap.
                    all_entries.extend(repeated_entries)
            all_entries.extend(accepted)
            token = next_token
            if token is None:
                pagination_exhausted = True
                break
    except urllib_error.HTTPError as exc:
        verdict = _provider_error_classification(status=int(exc.code))
        return RecoveryRangeResult(
            verdict=verdict,
            slot_gte=slot_gte,
            slot_lte=slot_lte,
            request_count=request_count,
            page_count=page_count,
            result_count=len(all_entries),
            unique_result_count=0,
            duplicate_results_suppressed=0,
            wrong_slot_results_rejected=wrong_slot,
            pagination_deterministic=False,
            pagination_exhausted=False,
            bounded=True,
            migrations_decoded=0,
            migrate=0,
            migrate_v2=0,
            decode_failures=0,
            known_signature_returned=None,
            known_slot_matched=None,
            known_decoder_parity=None,
            estimated_credits=estimated_credits_total,
            signature_hashes=(),
            sanitized_error=verdict,
        )
    except (
        urllib_error.URLError,
        TimeoutError,
        OSError,
        json.JSONDecodeError,
        ProbeProtocolError,
    ) as exc:
        verdict = (
            PROTOCOL_INVALID
            if isinstance(exc, (json.JSONDecodeError, ProbeProtocolError))
            else NETWORK_FAILURE
        )
        return RecoveryRangeResult(
            verdict=verdict,
            slot_gte=slot_gte,
            slot_lte=slot_lte,
            request_count=request_count,
            page_count=page_count,
            result_count=len(all_entries),
            unique_result_count=0,
            duplicate_results_suppressed=0,
            wrong_slot_results_rejected=wrong_slot,
            pagination_deterministic=False,
            pagination_exhausted=False,
            bounded=True,
            migrations_decoded=0,
            migrate=0,
            migrate_v2=0,
            decode_failures=0,
            known_signature_returned=None,
            known_slot_matched=None,
            known_decoder_parity=None,
            estimated_credits=estimated_credits_total,
            signature_hashes=(),
            sanitized_error=verdict,
        )

    unique, duplicates = dedupe_recovery_entries(all_entries)
    migrate = 0
    migrate_v2 = 0
    failures = 0
    hashes = []
    known_returned = None if known_signature is None else False
    known_slot_matched = None if known_signature is None else False
    known_decoder_parity = None if known_signature is None else False
    for entry in unique:
        signature = _entry_signature(entry)
        if signature:
            hashes.append(signature_hash(signature))
        classification = classify_helius_envelope(entry)
        if classification.classification == CLASS_MIGRATE:
            migrate += 1
        elif classification.classification == CLASS_MIGRATE_V2:
            migrate_v2 += 1
        elif classification.classification == CLASS_DECODE_FAILURE:
            failures += 1
        if known_signature is not None and signature == known_signature:
            known_returned = True
            known_slot_matched = entry.get("slot") in range(
                slot_gte, slot_lte + 1
            )
            known_decoder_parity = classification.classification in (
                CLASS_MIGRATE,
                CLASS_MIGRATE_V2,
            )
    return RecoveryRangeResult(
        verdict=HELIUS_HTTP_AVAILABLE,
        slot_gte=slot_gte,
        slot_lte=slot_lte,
        request_count=request_count,
        page_count=page_count,
        result_count=len(all_entries),
        unique_result_count=len(unique),
        duplicate_results_suppressed=duplicates,
        wrong_slot_results_rejected=wrong_slot,
        pagination_deterministic=pagination_deterministic,
        pagination_exhausted=pagination_exhausted,
        bounded=page_count <= max_pages and request_count <= max_pages + 1,
        migrations_decoded=migrate + migrate_v2,
        migrate=migrate,
        migrate_v2=migrate_v2,
        decode_failures=failures,
        known_signature_returned=known_returned,
        known_slot_matched=known_slot_matched,
        known_decoder_parity=known_decoder_parity,
        estimated_credits=estimated_credits_total,
        signature_hashes=tuple(hashes),
    )


def dataclass_to_sanitized_dict(value: object) -> Dict[str, object]:
    """Serialize only public result dataclasses, never secret configuration."""

    if isinstance(value, HeliusProbeConfig):
        raise ValueError("secret configuration is not serializable")
    return asdict(value)


__all__ = (
    "AUTH_FAILURE",
    "CapabilityResult",
    "CLASS_DECODE_FAILURE",
    "CLASS_MIGRATE",
    "CLASS_MIGRATE_V2",
    "CLASS_NON_MIGRATION",
    "DEFAULT_MAX_RAW_BYTES",
    "DEVELOPER_MONTHLY_CREDITS",
    "FILTER_CONTROL",
    "FILTER_TIGHT",
    "HELIUS_HTTP_AVAILABLE",
    "HELIUS_WSS_AVAILABLE",
    "HeliusProbeConfig",
    "LiveComparisonResult",
    "LocalClassification",
    "NETWORK_FAILURE",
    "PLAN_FORBIDDEN",
    "PROTOCOL_INVALID",
    "ProbeConfigurationError",
    "ProbeProtocolError",
    "RATE_LIMITED",
    "billing_granule_upper_bound",
    "build_authenticated_url",
    "build_slot_bounded_gtfa_request",
    "build_transaction_subscribe_request",
    "build_transaction_unsubscribe_request",
    "classify_decoder_update",
    "classify_helius_envelope",
    "dataclass_to_sanitized_dict",
    "estimated_stream_credits",
    "gtfa_full_credits",
    "helius_envelope_to_decoder_update",
    "http_json_rpc_call",
    "load_helius_probe_config",
    "offline_filter_match",
    "project_credits",
    "recovery_entry_identity",
    "redact_text",
    "redact_url",
    "resolved_update_account_texts",
    "run_http_capability_probe",
    "run_live_comparison",
    "run_slot_range_recovery",
    "run_wss_capability_probe",
    "send_keepalive",
    "signature_hash",
    "uncompressed_json_bytes",
    "validate_gtfa_page",
    "validate_numeric_subscription_response",
    "validate_unsubscribe_response",
)

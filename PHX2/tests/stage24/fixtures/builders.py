"""Synthetic Stage 24 test fixture builders (foundation only at 24.1).

These helpers build deterministic, secret-free synthetic Stage
24 records used by the Stage 24 test suite. No live provider
payloads are checked into the repository; the fixtures are
constructed from short non-secret literals.

The builders are intentionally simple wrappers around the
Stage 24 production model and input-reader surfaces so the
test suite exercises the same closed-set validation and
projection paths the production runner / decoder implementations
will exercise in 24.2+.

Stage 24.2 / 24.3 / 24.4 / 24.5 will add decoder-result builders
alongside their decoders. Stage 24.1 ships only the synthetic
``Stage24ExecutionInput`` and decoded-tx-JSONL-row builders.
"""

from __future__ import annotations

from types import MappingProxyType
from typing import Mapping

from PHX2.stage24.constants import (
    DEFAULT_SCHEMA_VERSION,
    INPUT_KIND_SYNTHETIC_DECODED_TX_JSONL,
)
from PHX2.stage24.models import (
    Stage24ExecutionInput,
    compute_execution_input_hash_from_projection,
)


# ---------------------------------------------------------------------------
# Injected-clock literal
# ---------------------------------------------------------------------------


FIXED_CLOCK_UTC: str = "2026-01-01T00:00:00Z"


# ---------------------------------------------------------------------------
# Minimal synthetic Stage24ExecutionInput
# ---------------------------------------------------------------------------


def _frozen_empty_mapping() -> Mapping[str, object]:
    return MappingProxyType({})


def make_execution_input(
    *,
    signature: str = "sig_fixture_001",
    slot: int = 250_000_000,
    slot_unix_time: int = 1_750_000_000,
    observed_at_utc: str = FIXED_CLOCK_UTC,
    provider_id: str = "fake_provider",
    transaction_status: str = "success",
    account_keys: tuple[str, ...] = (
        "AccountA1111111111111111111111111111111111",
        "AccountB2222222222222222222222222222222222",
    ),
    top_level_instructions: tuple[Mapping[str, object], ...] | None = None,
    inner_instructions: tuple[Mapping[str, object], ...] | None = None,
    pre_balances: tuple[int, ...] = (10_000_000, 5_000_000),
    post_balances: tuple[int, ...] = (9_995_000, 5_000_000),
    pre_token_balances: tuple[Mapping[str, object], ...] | None = None,
    post_token_balances: tuple[Mapping[str, object], ...] | None = None,
    log_messages: tuple[str, ...] = (
        "Program log: synthetic fixture",
    ),
    meta: Mapping[str, object] | None = None,
    missing_fields: tuple[str, ...] = (),
    input_kind: str = INPUT_KIND_SYNTHETIC_DECODED_TX_JSONL,
) -> Stage24ExecutionInput:
    """Build a synthetic ``Stage24ExecutionInput`` with safe defaults.

    All defaults are short non-secret strings / integers; the
    builder is deterministic so two invocations with the same
    arguments produce byte-identical records (including the
    derived ``payload_hash`` and ``input_id`` fields).
    """
    top_instructions = (
        top_level_instructions
        if top_level_instructions is not None
        else (
            MappingProxyType(
                {
                    "program_id": "ComputeBudget111111111111111111111111111111",
                    "accounts": [],
                    "data": "synthetic_data_001",
                }
            ),
        )
    )
    inner = (
        inner_instructions if inner_instructions is not None else ()
    )
    pre_tok = (
        pre_token_balances if pre_token_balances is not None else ()
    )
    post_tok = (
        post_token_balances if post_token_balances is not None else ()
    )
    meta_mapping = meta if meta is not None else _frozen_empty_mapping()
    payload_hash = compute_execution_input_hash_from_projection(
        input_kind=input_kind,
        schema_version=DEFAULT_SCHEMA_VERSION,
        signature=signature,
        slot=slot,
        slot_unix_time=slot_unix_time,
        observed_at_utc=observed_at_utc,
        provider_id=provider_id,
        transaction_status=transaction_status,
        account_keys=account_keys,
        top_level_instructions=top_instructions,
        inner_instructions=inner,
        pre_balances=pre_balances,
        post_balances=post_balances,
        pre_token_balances=pre_tok,
        post_token_balances=post_tok,
        log_messages=log_messages,
        meta=meta_mapping,
        missing_fields=missing_fields,
    )
    input_id = (
        signature if signature != "" else "tx_synth_" + payload_hash[:24]
    )
    return Stage24ExecutionInput(
        input_id=input_id,
        input_kind=input_kind,
        schema_version=DEFAULT_SCHEMA_VERSION,
        signature=signature,
        slot=slot,
        slot_unix_time=slot_unix_time,
        observed_at_utc=observed_at_utc,
        provider_id=provider_id,
        transaction_status=transaction_status,
        account_keys=account_keys,
        top_level_instructions=top_instructions,
        inner_instructions=inner,
        pre_balances=pre_balances,
        post_balances=post_balances,
        pre_token_balances=pre_tok,
        post_token_balances=post_tok,
        log_messages=log_messages,
        meta=meta_mapping,
        payload_hash=payload_hash,
        missing_fields=missing_fields,
    )


# ---------------------------------------------------------------------------
# Decoded-tx JSONL row builders
# ---------------------------------------------------------------------------


def make_top_level_instruction(
    *,
    program_id: str = "ComputeBudget111111111111111111111111111111",
    accounts: tuple[str, ...] = (),
    data: str = "synthetic_data_001",
) -> dict[str, object]:
    """Build a top-level instruction record for a synthetic input row."""
    return {
        "program_id": program_id,
        "accounts": list(accounts),
        "data": data,
    }


def make_inner_instruction(
    *,
    program_id: str = "11111111111111111111111111111111",
    accounts: tuple[str, ...] = (),
    data: str = "synthetic_inner_001",
) -> dict[str, object]:
    """Build an inner instruction record for a synthetic input row."""
    return {
        "program_id": program_id,
        "accounts": list(accounts),
        "data": data,
    }


def make_decoded_tx_row(
    *,
    signature: str = "sig_row_001",
    slot: int = 250_000_001,
    slot_unix_time: int = 1_750_000_001,
    observed_at_utc: str = FIXED_CLOCK_UTC,
    provider_id: str = "fake_provider",
    transaction_status: str = "success",
    account_keys: tuple[str, ...] = (
        "AccountA1111111111111111111111111111111111",
    ),
    top_level_instructions: tuple[dict[str, object], ...] | None = None,
    inner_instructions: tuple[dict[str, object], ...] | None = None,
    pre_balances: tuple[int, ...] = (10_000_000,),
    post_balances: tuple[int, ...] = (9_995_000,),
    pre_token_balances: tuple[dict[str, object], ...] = (),
    post_token_balances: tuple[dict[str, object], ...] = (),
    log_messages: tuple[str, ...] = (
        "Program log: synthetic row",
    ),
    meta: dict[str, object] | None = None,
) -> dict[str, object]:
    """Build a Stage 24-shaped decoded-tx JSONL row as a plain dict.

    Tests serialize the dict via ``json.dumps`` and write it to a
    JSONL file for the input-reader tests. The dict carries only
    short non-secret literals.
    """
    if top_level_instructions is None:
        top_level_instructions = (make_top_level_instruction(),)
    if inner_instructions is None:
        inner_instructions = ()
    if meta is None:
        meta = {"fee": 5000}
    return {
        "signature": signature,
        "slot": slot,
        "slot_unix_time": slot_unix_time,
        "observed_at_utc": observed_at_utc,
        "provider_id": provider_id,
        "transaction_status": transaction_status,
        "account_keys": list(account_keys),
        "top_level_instructions": list(top_level_instructions),
        "inner_instructions": list(inner_instructions),
        "pre_balances": list(pre_balances),
        "post_balances": list(post_balances),
        "pre_token_balances": list(pre_token_balances),
        "post_token_balances": list(post_token_balances),
        "log_messages": list(log_messages),
        "meta": meta,
    }


# ---------------------------------------------------------------------------
# Intentionally malformed / leaky rows for the input reader tests
# ---------------------------------------------------------------------------


def make_row_with_secret_field_name() -> dict[str, object]:
    """Build a row that carries a forbidden secret-bearing field name.

    The reader must reject this row. The field name carries the
    secret-bearing substring at the top level so the reader's
    first-pass field-name scan catches it.
    """
    base = make_decoded_tx_row(signature="sig_secret_field_001")
    base["api_key"] = "fake_value_001"
    return base


def make_row_with_url_value() -> dict[str, object]:
    """Build a row whose ``provider_id`` carries a URL substring.

    The reader must reject this row at the value-scan step.
    """
    return make_decoded_tx_row(
        signature="sig_url_value_001",
        provider_id="ht" + "tps://fake-rpc.example/path",
    )


def make_row_with_long_hex_credential() -> dict[str, object]:
    """Build a row carrying a 64-hex-char credential-shape token value.

    The reader's long-hex-run check rejects this row.
    """
    return make_decoded_tx_row(
        signature="sig_hex_001",
        observed_at_utc=("a" * 64),
    )


def make_row_with_nested_secret_key() -> dict[str, object]:
    """Build a row whose ``meta`` mapping carries a nested secret-bearing key.

    The reader's recursive value scan rejects this row when the
    nested ``authorization`` key is detected.
    """
    return make_decoded_tx_row(
        signature="sig_nested_secret_001",
        meta={"fee": 5000, "authorization": "fake"},
    )


__all__ = [
    "FIXED_CLOCK_UTC",
    "make_decoded_tx_row",
    "make_execution_input",
    "make_inner_instruction",
    "make_row_with_long_hex_credential",
    "make_row_with_nested_secret_key",
    "make_row_with_secret_field_name",
    "make_row_with_url_value",
    "make_top_level_instruction",
]

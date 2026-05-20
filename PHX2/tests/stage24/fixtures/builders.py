"""Synthetic Stage 24 test fixture builders.

These helpers build deterministic, secret-free synthetic Stage
24 records used by the Stage 24 test suite. No live provider
payloads are checked into the repository; the fixtures are
constructed from short non-secret literals.

The builders are intentionally simple wrappers around the
Stage 24 production model and input-reader surfaces so the
test suite exercises the same closed-set validation and
projection paths the production runner / decoder implementations
will exercise in 24.2+.

Stage 24.2 added the ComputeBudget instruction-data builders
(``encode_compute_budget_*``) used by the compute-budget and
priority-fee decoder tests. Stage 24.3 / 24.4 / 24.5 will add
decoder-result builders alongside their decoders.
"""

from __future__ import annotations

import base64
from types import MappingProxyType
from typing import Mapping

from PHX2.stage24.constants import (
    ACTIVE_AXIOM_ROUTER_PROGRAM_IDS,
    DEFAULT_SCHEMA_VERSION,
    DEPRECATED_AXIOM_ROUTER_PROGRAM_IDS,
    INPUT_KIND_SYNTHETIC_DECODED_TX_JSONL,
    KNOWN_JITO_TIP_ACCOUNTS,
    SYSTEM_PROGRAM_ID,
    TOKEN_PROGRAM_ID,
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


# ---------------------------------------------------------------------------
# Stage 24.2 ComputeBudget instruction-data builders
# ---------------------------------------------------------------------------
#
# Each helper returns a base64-encoded instruction-data string
# in the canonical Stage 24 instruction-data format: the first
# decoded byte is the ComputeBudget tag (0 / 1 / 2 / 3) and the
# following bytes are the little-endian u32 / u64 fields
# documented in the public Solana ComputeBudget program reference.
# The helpers do NOT touch a Solana SDK; the encoding is
# expressed in pure stdlib ``int.to_bytes`` calls.


_COMPUTE_BUDGET_TAG_REQUEST_UNITS_DEPRECATED: int = 0
_COMPUTE_BUDGET_TAG_REQUEST_HEAP_FRAME: int = 1
_COMPUTE_BUDGET_TAG_SET_COMPUTE_UNIT_LIMIT: int = 2
_COMPUTE_BUDGET_TAG_SET_COMPUTE_UNIT_PRICE: int = 3


def encode_compute_budget_set_unit_limit_data(*, units: int) -> str:
    """Return base64-encoded ``SetComputeUnitLimit(units)`` data."""
    payload = bytes(
        [_COMPUTE_BUDGET_TAG_SET_COMPUTE_UNIT_LIMIT]
    ) + units.to_bytes(4, "little")
    return base64.b64encode(payload).decode("ascii")


def encode_compute_budget_set_unit_price_data(
    *, micro_lamports_per_compute_unit: int
) -> str:
    """Return base64-encoded ``SetComputeUnitPrice(price)`` data."""
    payload = bytes(
        [_COMPUTE_BUDGET_TAG_SET_COMPUTE_UNIT_PRICE]
    ) + micro_lamports_per_compute_unit.to_bytes(8, "little")
    return base64.b64encode(payload).decode("ascii")


def encode_compute_budget_request_heap_frame_data(
    *, heap_frame_bytes: int
) -> str:
    """Return base64-encoded ``RequestHeapFrame(bytes)`` data."""
    payload = bytes(
        [_COMPUTE_BUDGET_TAG_REQUEST_HEAP_FRAME]
    ) + heap_frame_bytes.to_bytes(4, "little")
    return base64.b64encode(payload).decode("ascii")


def encode_compute_budget_request_units_deprecated_data(
    *,
    requested_units: int,
    additional_fee_lamports: int,
) -> str:
    """Return base64-encoded legacy ``RequestUnitsDeprecated(...)`` data."""
    payload = (
        bytes([_COMPUTE_BUDGET_TAG_REQUEST_UNITS_DEPRECATED])
        + requested_units.to_bytes(4, "little")
        + additional_fee_lamports.to_bytes(4, "little")
    )
    return base64.b64encode(payload).decode("ascii")


def encode_compute_budget_unknown_tag_data(
    *, tag: int, body: bytes = b""
) -> str:
    """Return base64-encoded ComputeBudget data carrying an unknown tag.

    The decoder rejects unknown tags as ``DECODE_FAILED``. Used
    by the negative-case Stage 24.2 tests.
    """
    payload = bytes([tag]) + body
    return base64.b64encode(payload).decode("ascii")


def encode_compute_budget_malformed_short_body_data() -> str:
    """Return base64-encoded ComputeBudget data with a too-short body.

    Tag 2 (``SetComputeUnitLimit``) expects 4 bytes of body but
    this builder returns 3 bytes. Used by the malformed-body
    Stage 24.2 test.
    """
    payload = bytes([_COMPUTE_BUDGET_TAG_SET_COMPUTE_UNIT_LIMIT]) + bytes(
        [0x00, 0x00, 0x00]
    )
    return base64.b64encode(payload).decode("ascii")


def encode_compute_budget_empty_data() -> str:
    """Return a base64 encoding of zero bytes (no tag, no body)."""
    return base64.b64encode(b"").decode("ascii")


def make_compute_budget_set_unit_limit_instruction(
    *,
    units: int,
    accounts: tuple[str, ...] = (),
) -> dict[str, object]:
    """Build a top-level ``SetComputeUnitLimit`` instruction record."""
    return make_top_level_instruction(
        program_id="ComputeBudget111111111111111111111111111111",
        accounts=accounts,
        data=encode_compute_budget_set_unit_limit_data(units=units),
    )


def make_compute_budget_set_unit_price_instruction(
    *,
    micro_lamports_per_compute_unit: int,
    accounts: tuple[str, ...] = (),
) -> dict[str, object]:
    """Build a top-level ``SetComputeUnitPrice`` instruction record."""
    return make_top_level_instruction(
        program_id="ComputeBudget111111111111111111111111111111",
        accounts=accounts,
        data=encode_compute_budget_set_unit_price_data(
            micro_lamports_per_compute_unit=(
                micro_lamports_per_compute_unit
            ),
        ),
    )


def make_compute_budget_request_heap_frame_instruction(
    *,
    heap_frame_bytes: int,
    accounts: tuple[str, ...] = (),
) -> dict[str, object]:
    """Build a top-level ``RequestHeapFrame`` instruction record."""
    return make_top_level_instruction(
        program_id="ComputeBudget111111111111111111111111111111",
        accounts=accounts,
        data=encode_compute_budget_request_heap_frame_data(
            heap_frame_bytes=heap_frame_bytes,
        ),
    )


def make_compute_budget_request_units_deprecated_instruction(
    *,
    requested_units: int,
    additional_fee_lamports: int,
    accounts: tuple[str, ...] = (),
) -> dict[str, object]:
    """Build a top-level legacy ``RequestUnitsDeprecated`` instruction record."""
    return make_top_level_instruction(
        program_id="ComputeBudget111111111111111111111111111111",
        accounts=accounts,
        data=encode_compute_budget_request_units_deprecated_data(
            requested_units=requested_units,
            additional_fee_lamports=additional_fee_lamports,
        ),
    )


def make_non_compute_budget_instruction(
    *,
    program_id: str = "11111111111111111111111111111111",
    accounts: tuple[str, ...] = (),
    data: str = "",
) -> dict[str, object]:
    """Build an instruction record for a non-ComputeBudget program.

    Default ``data`` is empty so the value-shape leak detector
    does not reject the row. Used by tests that need a non-
    ComputeBudget instruction alongside a ComputeBudget one.
    """
    return make_top_level_instruction(
        program_id=program_id,
        accounts=accounts,
        data=data,
    )


# ---------------------------------------------------------------------------
# Stage 24.3 System Program transfer instruction-data builders
# ---------------------------------------------------------------------------
#
# The System Program ``Transfer`` instruction layout is:
#   * 4 bytes: u32 little-endian instruction tag (= 2 for Transfer)
#   * 8 bytes: u64 little-endian lamports
# Total 12 bytes. The helpers below encode that layout via pure
# stdlib ``int.to_bytes`` calls; no Solana SDK is touched.


_SYSTEM_PROGRAM_TAG_CREATE_ACCOUNT: int = 0
_SYSTEM_PROGRAM_TAG_ASSIGN: int = 1
_SYSTEM_PROGRAM_TAG_TRANSFER: int = 2


def make_system_transfer_instruction_data(*, lamports: int) -> str:
    """Return base64-encoded System Program ``Transfer(lamports)`` data."""
    payload = (
        _SYSTEM_PROGRAM_TAG_TRANSFER.to_bytes(4, "little")
        + lamports.to_bytes(8, "little")
    )
    return base64.b64encode(payload).decode("ascii")


def make_system_transfer_instruction(
    *,
    lamports: int,
    destination: str,
    source: str = "AccountSource11111111111111111111111111111",
) -> dict[str, object]:
    """Build a top-level System Program ``Transfer`` instruction record.

    ``accounts`` is encoded as direct base58 pubkey strings in
    Stage 24-shaped decoded-tx JSONL fixtures (mirroring the
    ComputeBudget fixtures' string-account convention).
    Position 0 is the source, position 1 is the destination, per
    the public System Program Transfer layout.
    """
    return make_top_level_instruction(
        program_id=SYSTEM_PROGRAM_ID,
        accounts=(source, destination),
        data=make_system_transfer_instruction_data(lamports=lamports),
    )


def make_jito_tip_instruction(
    *,
    lamports: int = 10_000,
    tip_account: str | None = None,
    source: str = "AccountSource11111111111111111111111111111",
) -> dict[str, object]:
    """Build a top-level System Program transfer to a known Jito tip account.

    Defaults to the first locked Jito tip account so callers do
    not have to know the literal pubkeys. Raises ``RuntimeError``
    if the tip-account tuple is empty (which would mean Stage 24
    constants regressed).
    """
    if tip_account is None:
        if not KNOWN_JITO_TIP_ACCOUNTS:
            raise RuntimeError(
                "KNOWN_JITO_TIP_ACCOUNTS is empty; cannot build a tip "
                "instruction with a default destination."
            )
        tip_account = KNOWN_JITO_TIP_ACCOUNTS[0]
    return make_system_transfer_instruction(
        lamports=lamports,
        destination=tip_account,
        source=source,
    )


def make_non_tip_system_transfer_instruction(
    *,
    lamports: int = 1_000,
    destination: str = "NonTipAccount11111111111111111111111111111",
    source: str = "AccountSource11111111111111111111111111111",
) -> dict[str, object]:
    """Build a top-level System Program transfer to a non-tip account."""
    return make_system_transfer_instruction(
        lamports=lamports,
        destination=destination,
        source=source,
    )


def make_system_program_unknown_tag_data(
    *,
    tag: int,
    body: bytes = b"",
) -> str:
    """Return base64-encoded System Program data carrying an unknown tag.

    The instruction tag is encoded as a u32 little-endian (matching
    the System Program layout). Used by tests that need a System
    Program instruction whose tag is NOT ``Transfer``.
    """
    payload = tag.to_bytes(4, "little") + body
    return base64.b64encode(payload).decode("ascii")


def make_system_program_non_transfer_instruction(
    *,
    tag: int = _SYSTEM_PROGRAM_TAG_CREATE_ACCOUNT,
    body: bytes = b"",
    accounts: tuple[str, ...] = (),
) -> dict[str, object]:
    """Build a top-level System Program instruction with a non-Transfer tag."""
    return make_top_level_instruction(
        program_id=SYSTEM_PROGRAM_ID,
        accounts=accounts,
        data=make_system_program_unknown_tag_data(tag=tag, body=body),
    )


def make_malformed_system_transfer_instruction(
    *,
    destination: str | None = None,
    source: str = "AccountSource11111111111111111111111111111",
) -> dict[str, object]:
    """Build a System Program transfer instruction with a too-short body.

    Tag bytes claim ``Transfer`` (u32=2) but only 3 lamport bytes
    follow, instead of the required 8. The decoder must fail
    closed as ``DECODE_FAILED`` / ``MALFORMED``.
    """
    if destination is None:
        destination = (
            KNOWN_JITO_TIP_ACCOUNTS[0]
            if KNOWN_JITO_TIP_ACCOUNTS
            else "DefaultDestination11111111111111111111111"
        )
    payload = (
        _SYSTEM_PROGRAM_TAG_TRANSFER.to_bytes(4, "little") + bytes([0, 0, 0])
    )
    data_str = base64.b64encode(payload).decode("ascii")
    return make_top_level_instruction(
        program_id=SYSTEM_PROGRAM_ID,
        accounts=(source, destination),
        data=data_str,
    )


def make_inner_jito_tip_instruction(
    *,
    lamports: int = 5_000,
    tip_account: str | None = None,
    source: str = "AccountSource11111111111111111111111111111",
) -> dict[str, object]:
    """Build an inner (CPI) System Program transfer to a Jito tip account.

    Shape matches the top-level builder; the only difference is
    that the caller places the record into ``inner_instructions``
    on the ``Stage24ExecutionInput``.
    """
    if tip_account is None:
        if not KNOWN_JITO_TIP_ACCOUNTS:
            raise RuntimeError(
                "KNOWN_JITO_TIP_ACCOUNTS is empty; cannot build a tip "
                "instruction with a default destination."
            )
        tip_account = KNOWN_JITO_TIP_ACCOUNTS[0]
    return make_inner_instruction(
        program_id=SYSTEM_PROGRAM_ID,
        accounts=(source, tip_account),
        data=make_system_transfer_instruction_data(lamports=lamports),
    )


def make_inner_non_tip_system_transfer_instruction(
    *,
    lamports: int = 750,
    destination: str = "InnerNonTip11111111111111111111111111111",
    source: str = "AccountSource11111111111111111111111111111",
) -> dict[str, object]:
    """Build an inner (CPI) System Program transfer to a non-tip account."""
    return make_inner_instruction(
        program_id=SYSTEM_PROGRAM_ID,
        accounts=(source, destination),
        data=make_system_transfer_instruction_data(lamports=lamports),
    )


# ---------------------------------------------------------------------------
# Stage 24.4 router-fee candidate fixture builders
# ---------------------------------------------------------------------------
#
# Each helper builds a synthetic instruction record or execution
# input that exercises the Stage 24.4 router-fee candidate
# scaffold. Stage 24.4 does NOT decode router or global-fee
# amounts; it only detects router program IDs, classifies the
# route family, and surfaces wrapped-swap / inner-transfer
# evidence. The fixtures therefore do not need real router
# instruction data -- empty ``data`` strings are fine and keep
# the redaction-shape detector happy.


def make_axiom_trading_program_1_instruction(
    *,
    accounts: tuple[str, ...] = (),
    data: str = "",
) -> dict[str, object]:
    """Build a top-level Axiom Trading Program 1 instruction.

    Maps to ``route_family = AXIOM_TRADING_PROGRAM_1`` at the
    Stage 24.4 decoder.
    """
    return make_top_level_instruction(
        program_id=ACTIVE_AXIOM_ROUTER_PROGRAM_IDS[0],
        accounts=accounts,
        data=data,
    )


def make_axiom_flashx8_instruction(
    *,
    accounts: tuple[str, ...] = (),
    data: str = "",
) -> dict[str, object]:
    """Build a top-level Axiom FLASHX8 instruction.

    Maps to ``route_family = AXIOM_FLASHX8`` at the Stage 24.4
    decoder.
    """
    return make_top_level_instruction(
        program_id=ACTIVE_AXIOM_ROUTER_PROGRAM_IDS[1],
        accounts=accounts,
        data=data,
    )


def make_deprecated_axiom_instruction(
    *,
    deprecated_index: int = 0,
    accounts: tuple[str, ...] = (),
    data: str = "",
) -> dict[str, object]:
    """Build a top-level deprecated Axiom router instruction.

    ``deprecated_index`` selects which of the two deprecated
    Axiom program IDs in
    ``DEPRECATED_AXIOM_ROUTER_PROGRAM_IDS`` to use. The Stage
    24.4 decoder maps both deprecated IDs to
    ``route_family = DEPRECATED_AXIOM`` with
    ``decoder_status = UNSUPPORTED``.
    """
    if not DEPRECATED_AXIOM_ROUTER_PROGRAM_IDS:
        raise RuntimeError(
            "DEPRECATED_AXIOM_ROUTER_PROGRAM_IDS is empty; cannot build "
            "a deprecated Axiom instruction."
        )
    if (
        deprecated_index < 0
        or deprecated_index >= len(DEPRECATED_AXIOM_ROUTER_PROGRAM_IDS)
    ):
        raise IndexError(
            "deprecated_index out of range for "
            "DEPRECATED_AXIOM_ROUTER_PROGRAM_IDS"
        )
    return make_top_level_instruction(
        program_id=DEPRECATED_AXIOM_ROUTER_PROGRAM_IDS[deprecated_index],
        accounts=accounts,
        data=data,
    )


def make_router_like_execution_input(
    *,
    top_level_instructions: tuple[Mapping[str, object], ...],
    inner_instructions: tuple[Mapping[str, object], ...] = (),
    signature: str = "sig_router_fixture_001",
    account_keys: tuple[str, ...] = (
        "AccountA1111111111111111111111111111111111",
        "AccountB2222222222222222222222222222222222",
    ),
) -> Stage24ExecutionInput:
    """Build a ``Stage24ExecutionInput`` shaped like a router transaction.

    Used by the Stage 24.4 tests to feed router / wrapped-swap
    candidate scenarios into the decoder.
    """
    return make_execution_input(
        signature=signature,
        account_keys=account_keys,
        top_level_instructions=top_level_instructions,
        inner_instructions=inner_instructions,
    )


def make_inner_system_transfer_under_router(
    *,
    lamports: int = 5_000,
    destination: str = "InnerRouterDest1111111111111111111111111",
    source: str = "AccountSource11111111111111111111111111111",
) -> dict[str, object]:
    """Build an inner (CPI) System Program transfer beneath a router.

    Shape-equivalent to ``make_inner_non_tip_system_transfer_instruction``;
    re-exported under a router-flavoured name so Stage 24.4 tests
    read clearly.
    """
    return make_inner_instruction(
        program_id=SYSTEM_PROGRAM_ID,
        accounts=(source, destination),
        data=make_system_transfer_instruction_data(lamports=lamports),
    )


def make_inner_token_transfer_under_router(
    *,
    accounts: tuple[str, ...] = (
        "TokenSource1111111111111111111111111111111",
        "TokenDest11111111111111111111111111111111",
    ),
    data: str = "",
) -> dict[str, object]:
    """Build an inner (CPI) Token Program instruction beneath a router.

    Stage 24.4 does NOT decode token-transfer instruction bytes;
    the candidate scaffold only matches on the inner
    instruction's program_id. The ``data`` field can therefore be
    empty.
    """
    return make_inner_instruction(
        program_id=TOKEN_PROGRAM_ID,
        accounts=accounts,
        data=data,
    )


def make_wrapped_swap_candidate_execution_input(
    *,
    route_family_index: int = 1,
    extra_inner_token_transfer: bool = False,
) -> Stage24ExecutionInput:
    """Build an execution input with a wrapped-swap candidate shape.

    Active router top-level instruction plus an inner System
    Program transfer. ``route_family_index = 0`` selects Axiom
    Trading Program 1; ``= 1`` selects FLASHX8. When
    ``extra_inner_token_transfer`` is True an additional inner
    Token Program instruction is added so tests can assert on
    both inner candidate types.
    """
    if route_family_index == 0:
        router_instr = make_axiom_trading_program_1_instruction()
    else:
        router_instr = make_axiom_flashx8_instruction()
    inner: tuple[Mapping[str, object], ...] = (
        make_inner_system_transfer_under_router(),
    )
    if extra_inner_token_transfer:
        inner = inner + (make_inner_token_transfer_under_router(),)
    return make_router_like_execution_input(
        top_level_instructions=(router_instr,),
        inner_instructions=inner,
    )


__all__ = [
    "FIXED_CLOCK_UTC",
    "encode_compute_budget_empty_data",
    "encode_compute_budget_malformed_short_body_data",
    "encode_compute_budget_request_heap_frame_data",
    "encode_compute_budget_request_units_deprecated_data",
    "encode_compute_budget_set_unit_limit_data",
    "encode_compute_budget_set_unit_price_data",
    "encode_compute_budget_unknown_tag_data",
    "make_axiom_flashx8_instruction",
    "make_axiom_trading_program_1_instruction",
    "make_compute_budget_request_heap_frame_instruction",
    "make_compute_budget_request_units_deprecated_instruction",
    "make_compute_budget_set_unit_limit_instruction",
    "make_compute_budget_set_unit_price_instruction",
    "make_decoded_tx_row",
    "make_deprecated_axiom_instruction",
    "make_execution_input",
    "make_inner_instruction",
    "make_inner_jito_tip_instruction",
    "make_inner_non_tip_system_transfer_instruction",
    "make_inner_system_transfer_under_router",
    "make_inner_token_transfer_under_router",
    "make_jito_tip_instruction",
    "make_malformed_system_transfer_instruction",
    "make_non_compute_budget_instruction",
    "make_non_tip_system_transfer_instruction",
    "make_router_like_execution_input",
    "make_row_with_long_hex_credential",
    "make_row_with_nested_secret_key",
    "make_row_with_secret_field_name",
    "make_row_with_url_value",
    "make_system_program_non_transfer_instruction",
    "make_system_program_unknown_tag_data",
    "make_system_transfer_instruction",
    "make_system_transfer_instruction_data",
    "make_top_level_instruction",
    "make_wrapped_swap_candidate_execution_input",
]

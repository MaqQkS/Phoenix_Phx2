"""Stage 24 immutable models and deterministic hash helpers (foundation only at 24.1).

This module ships the typed ``NamedTuple`` records that every
Stage 24.2+ decoder / runner / artifact writer must satisfy,
plus the canonical-JSON deterministic hash helpers used to
derive ``payload_hash`` / ``result_hash`` / ``primitive_hash``.

Records:

  * ``Stage24ExecutionInput``         -- normalized transaction-level
                                         observation snapshot
                                         projected from a Stage 24-
                                         shaped decoded-tx JSONL row.
  * ``Stage24ComputeBudgetResult``    -- per-tx ComputeBudget decoder
                                         output. Carries unit_limit /
                                         unit_price.
  * ``Stage24PriorityFeeResult``      -- per-tx priority-fee result
                                         derived from
                                         ``Stage24ComputeBudgetResult``.
  * ``Stage24JitoTipResult``          -- per-tx Jito-tip decoder
                                         output. Carries tip_account /
                                         amount_lamports.
  * ``Stage24RouterFeeResult``        -- per-tx router / global-fee
                                         result. Carries
                                         program_id /
                                         instruction_location /
                                         (amount_lamports OR
                                         (amount_token, mint)).
                                         Single type spans both
                                         24.4 candidates and 24.5
                                         decoded.
  * ``Stage24ExecutionQualityResult`` -- per-tx inclusion /
                                         landing-quality primitive.
  * ``Stage24ExecutionPrimitive``     -- the unified per-primitive
                                         disk record. The disk-shape
                                         every decoder eventually
                                         feeds into.
  * ``Stage24RunnerResult``           -- immutable wrapper bundling
                                         all per-decoder result tuples
                                         plus aggregated counts.

Hashing:

  * ``canonical_json``                  -- canonical UTF-8 JSON
                                           encoding (sorted keys, no
                                           whitespace).
  * ``stage24_hash``                    -- sha256 hex of a canonical
                                           JSON encoding of an
                                           arbitrary canonicalizable
                                           value.
  * ``compute_execution_input_hash``    -- input-canonical hash for a
                                           ``Stage24ExecutionInput``.
  * ``compute_result_hash``             -- canonical hash over the
                                           result body (decoder-output
                                           hash).
  * ``compute_primitive_hash``          -- canonical hash over the
                                           unified
                                           ``Stage24ExecutionPrimitive``
                                           body.

Design notes:

  * All records are ``NamedTuple`` so they are immutable, hashable
    by value, and trivially serializable. ``setattr`` raises.
  * Hashes are derived from a canonical-JSON encoding with sorted
    keys, so dict ordering does not affect the hash.
  * Unstable runtime-only fields (``created_at_utc``) are NOT
    included in any hash.
  * ``amount_lamports`` / ``amount_token`` / ``unit_limit`` /
    ``unit_price_microlamports`` are ``int | None``. Stage 24
    NEVER coerces ``None`` to ``0`` -- ``None`` records "we did
    not decode the amount" and is honestly distinct from a
    decoded zero.

This module imports only stdlib (``hashlib`` / ``json`` /
``math``) plus the Stage 24 constants and errors. It does NOT
import any network / RPC / messaging / DB / scheduler /
secrets-management library, does NOT read the process
environment, does NOT define a CLI surface, and contains no
top-level I/O. It does NOT import Stage 21 / Stage 22 / Stage
23 modules.
"""

from __future__ import annotations

import hashlib
import json
import math
from typing import Mapping, NamedTuple, Optional

from PHX2.stage24.constants import (
    CONFIDENCE_LEVELS,
    DATA_STATUSES,
    DECODER_STATUSES,
    FEE_SOURCES,
    INSTRUCTION_LOCATIONS,
    PRIMITIVE_FAMILIES,
    ROUTE_FAMILIES,
)
from PHX2.stage24.errors import Stage24ContractError


# ---------------------------------------------------------------------------
# Stage24ExecutionInput
# ---------------------------------------------------------------------------


class Stage24ExecutionInput(NamedTuple):
    """Normalized transaction-level observation snapshot.

    Stage 24 reads Stage 24-shaped decoded-tx JSONL artifacts;
    the input reader projects a single JSONL row into this
    immutable record. Every field is either a closed-set token,
    a short non-secret string, an int, or a deterministic tuple
    / mapping of safe scalar values.

    Fields:

      * ``input_id``               -- short stable identifier for the
                                      input row. Derived from the
                                      payload hash so two runs over
                                      the same input emit the same id.
      * ``input_kind``             -- one of ``INPUT_KINDS``.
      * ``schema_version``         -- locked
                                      ``DEFAULT_SCHEMA_VERSION`` token.
      * ``signature``              -- Solana transaction signature
                                      when present; empty string when
                                      absent.
      * ``slot``                   -- slot number when present; ``-1``
                                      sentinel when absent.
      * ``slot_unix_time``         -- Unix-seconds time the slot was
                                      processed when present; ``-1``
                                      sentinel when absent. Mirrors
                                      the Solana RPC ``blockTime``
                                      field but is named so the
                                      Stage 24 boundary scanner does
                                      not confuse the blockchain
                                      ``block`` noun with the
                                      enforcement-action ``block``
                                      verb forbidden in Stage 24.
      * ``observed_at_utc``        -- ISO-8601 UTC string carried
                                      from the upstream artifact. May
                                      be the empty string.
      * ``provider_id``            -- short non-secret operator label
                                      (e.g. ``"helius"``). Required
                                      non-empty.
      * ``transaction_status``     -- short non-secret string token
                                      describing transaction status
                                      (``"success"`` / ``"err"`` /
                                      ``""``). Not a closed set --
                                      this is upstream provider
                                      text projected verbatim.
      * ``account_keys``           -- tuple of Solana account public
                                      keys (base58 strings).
      * ``top_level_instructions`` -- tuple of mapping records, one
                                      per top-level transaction
                                      instruction. Each mapping carries
                                      at minimum ``program_id`` /
                                      ``accounts`` / ``data`` fields;
                                      Stage 24.1 does NOT validate the
                                      instruction layout.
      * ``inner_instructions``     -- tuple of mapping records, one
                                      per inner (CPI) instruction.
      * ``pre_balances``           -- tuple of int lamport balances
                                      before the transaction.
      * ``post_balances``          -- tuple of int lamport balances
                                      after the transaction.
      * ``pre_token_balances``     -- tuple of mapping records, one
                                      per per-account-pre token
                                      balance.
      * ``post_token_balances``    -- tuple of mapping records, one
                                      per per-account-post token
                                      balance.
      * ``log_messages``           -- tuple of program-log strings
                                      emitted by the transaction.
      * ``meta``                   -- frozen flat mapping carrying
                                      upstream metadata fields the
                                      reader projected. Stage 24.1
                                      does NOT validate this further.
      * ``payload_hash``           -- deterministic SHA-256 hex of
                                      the canonical-JSON projection
                                      of the input row.
      * ``missing_fields``         -- sorted tuple of preserved-field
                                      concept names absent from the
                                      upstream row. The reader
                                      populates this so downstream
                                      decoders can reason about input
                                      completeness without re-checking
                                      source absence.
    """

    input_id: str
    input_kind: str
    schema_version: str
    signature: str
    slot: int
    slot_unix_time: int
    observed_at_utc: str
    provider_id: str
    transaction_status: str
    account_keys: tuple[str, ...]
    top_level_instructions: tuple[Mapping[str, object], ...]
    inner_instructions: tuple[Mapping[str, object], ...]
    pre_balances: tuple[int, ...]
    post_balances: tuple[int, ...]
    pre_token_balances: tuple[Mapping[str, object], ...]
    post_token_balances: tuple[Mapping[str, object], ...]
    log_messages: tuple[str, ...]
    meta: Mapping[str, object]
    payload_hash: str
    missing_fields: tuple[str, ...]


# ---------------------------------------------------------------------------
# Stage24ComputeBudgetResult
# ---------------------------------------------------------------------------


class Stage24ComputeBudgetResult(NamedTuple):
    """Per-transaction ComputeBudget decoder result.

    Stage 24.2 will fill in the decoder logic. Stage 24.1 ships
    the record shape only.

    Closed-set semantics:

      * ``primitive_family`` -- always ``"COMPUTE_BUDGET"``.
      * ``fee_source``       -- ``"PRIORITY_FEE"`` when the
                                ComputeBudget instructions carry
                                priority-fee evidence; ``"UNKNOWN"``
                                otherwise.

    Decoder-specific fields:

      * ``unit_limit``               -- decoded compute-unit-limit
                                       value when present; ``None``
                                       otherwise. NEVER ``0`` as a
                                       stand-in for unknown.
      * ``unit_price_microlamports`` -- decoded compute-unit-price
                                       (microlamports per CU) when
                                       present; ``None`` otherwise.
    """

    primitive_family: str
    decoder_name: str
    decoder_version: str
    threshold_version: str
    decoder_status: str
    data_status: str
    confidence_level: str
    fee_source: str
    route_family: str
    instruction_location: str
    program_id: str
    unit_limit: Optional[int]
    unit_price_microlamports: Optional[int]
    reason_codes: tuple[str, ...]
    numeric_features: Mapping[str, object]
    evidence: Mapping[str, object]
    input_missing_fields: tuple[str, ...]
    result_hash: str


# ---------------------------------------------------------------------------
# Stage24PriorityFeeResult
# ---------------------------------------------------------------------------


class Stage24PriorityFeeResult(NamedTuple):
    """Per-transaction priority-fee result.

    Derived from a ``Stage24ComputeBudgetResult`` by computing
    ``unit_limit * unit_price_microlamports / 1_000_000`` when
    both inputs are present. Stage 24.2 will fill in the
    derivation; Stage 24.1 ships the record shape only.

    Closed-set semantics:

      * ``primitive_family`` -- always ``"PRIORITY_FEE"``.
      * ``fee_source``       -- always ``"PRIORITY_FEE"`` when
                                decoded; ``"UNKNOWN"`` otherwise.
    """

    primitive_family: str
    decoder_name: str
    decoder_version: str
    threshold_version: str
    decoder_status: str
    data_status: str
    confidence_level: str
    fee_source: str
    route_family: str
    instruction_location: str
    program_id: str
    amount_lamports: Optional[int]
    unit_limit: Optional[int]
    unit_price_microlamports: Optional[int]
    reason_codes: tuple[str, ...]
    numeric_features: Mapping[str, object]
    evidence: Mapping[str, object]
    input_missing_fields: tuple[str, ...]
    result_hash: str


# ---------------------------------------------------------------------------
# Stage24JitoTipResult
# ---------------------------------------------------------------------------


class Stage24JitoTipResult(NamedTuple):
    """Per-transaction Jito-tip decoder result.

    Stage 24.3 will fill in the decoder logic against the known
    Jito tip accounts. Stage 24.1 ships the record shape only.

    Closed-set semantics:

      * ``primitive_family`` -- always ``"JITO_TIP"``.
      * ``fee_source``       -- ``"JITO_TIP"`` when fully decoded;
                                ``"JITO_TIP_CANDIDATE"`` when only
                                the program / account is recognized;
                                ``"UNKNOWN"`` otherwise.

    Decoder-specific fields:

      * ``tip_account``    -- the Jito tip account observed; empty
                              string when no tip account is
                              identified.
      * ``amount_lamports`` -- the decoded tip amount in lamports;
                              ``None`` when not decoded. NEVER ``0``
                              as a stand-in for unknown.
    """

    primitive_family: str
    decoder_name: str
    decoder_version: str
    threshold_version: str
    decoder_status: str
    data_status: str
    confidence_level: str
    fee_source: str
    route_family: str
    instruction_location: str
    program_id: str
    tip_account: str
    amount_lamports: Optional[int]
    reason_codes: tuple[str, ...]
    numeric_features: Mapping[str, object]
    evidence: Mapping[str, object]
    input_missing_fields: tuple[str, ...]
    result_hash: str


# ---------------------------------------------------------------------------
# Stage24RouterFeeResult
# ---------------------------------------------------------------------------


class Stage24RouterFeeResult(NamedTuple):
    """Per-transaction router / global-fee result.

    Single record type spans both Stage 24.4 candidates and
    Stage 24.5 decoded outputs. The discriminator is
    ``decoder_status``:

      * ``DECODE_UNCONFIRMED`` -- 24.4 candidate. ``amount_lamports``
                                  and ``amount_token`` MUST be ``None``;
                                  ``fee_source`` MUST be one of the
                                  ``*_CANDIDATE`` tokens.
      * ``DECODED``            -- 24.5 confirmed decode. At least one
                                  of ``amount_lamports`` /
                                  ``amount_token`` MUST be a non-
                                  negative integer; ``fee_source``
                                  MUST be a non-candidate token.

    Stage 24.1 ships the record shape only; no decoder constructs
    instances of it.
    """

    primitive_family: str
    decoder_name: str
    decoder_version: str
    threshold_version: str
    decoder_status: str
    data_status: str
    confidence_level: str
    fee_source: str
    route_family: str
    instruction_location: str
    program_id: str
    amount_lamports: Optional[int]
    amount_token: Optional[int]
    mint: str
    reason_codes: tuple[str, ...]
    numeric_features: Mapping[str, object]
    evidence: Mapping[str, object]
    input_missing_fields: tuple[str, ...]
    result_hash: str


# ---------------------------------------------------------------------------
# Stage24ExecutionQualityResult
# ---------------------------------------------------------------------------


class Stage24ExecutionQualityResult(NamedTuple):
    """Per-transaction execution-quality (inclusion / landing) result.

    Stage 24.6 will fill in the runner that composes execution
    quality from upstream fields. Stage 24.1 ships the record
    shape only.

    Closed-set semantics:

      * ``primitive_family`` -- always ``"EXECUTION_QUALITY"``.
      * ``fee_source``       -- always ``"UNKNOWN"`` for execution
                                quality (execution quality is not a
                                fee axis).

    Decoder-specific fields:

      * ``landed``                          -- ``True`` /
                                              ``False`` / ``None``.
                                              ``None`` when the upstream
                                              observation did not carry
                                              enough information to
                                              decide.
      * ``landed_slot``                     -- slot the tx landed in;
                                              ``-1`` when not decoded.
      * ``submitted_slot``                  -- slot the tx was
                                              submitted in; ``-1`` when
                                              not recorded.
      * ``slot_delta``                      -- ``landed_slot -
                                              submitted_slot`` when
                                              both are known; ``None``
                                              otherwise.
      * ``realized_priority_fee_lamports``  -- realized priority fee;
                                              ``None`` when not
                                              decoded.
      * ``realized_jito_tip_lamports``      -- realized Jito tip;
                                              ``None`` when not
                                              decoded.
      * ``realized_router_fee_lamports``    -- realized router /
                                              global-fee amount;
                                              ``None`` when not
                                              decoded. NEVER
                                              fabricated from a
                                              candidate.
      * ``error_code``                      -- short non-secret error
                                              token when the tx
                                              failed; empty string
                                              otherwise. NEVER the raw
                                              RPC exception message.
    """

    primitive_family: str
    decoder_name: str
    decoder_version: str
    threshold_version: str
    decoder_status: str
    data_status: str
    confidence_level: str
    fee_source: str
    route_family: str
    landed: Optional[bool]
    landed_slot: int
    submitted_slot: int
    slot_delta: Optional[int]
    realized_priority_fee_lamports: Optional[int]
    realized_jito_tip_lamports: Optional[int]
    realized_router_fee_lamports: Optional[int]
    error_code: str
    reason_codes: tuple[str, ...]
    numeric_features: Mapping[str, object]
    evidence: Mapping[str, object]
    input_missing_fields: tuple[str, ...]
    result_hash: str


# ---------------------------------------------------------------------------
# Stage24ExecutionPrimitive
# ---------------------------------------------------------------------------


class Stage24ExecutionPrimitive(NamedTuple):
    """Unified per-primitive disk record.

    The disk-shape every Stage 24 decoder eventually feeds into.
    Stage 24.6 runner flattens per-decoder result tuples into a
    tuple of these records. Stage 24.1 ships the record shape
    only; no runner constructs instances of it.
    """

    tx_signature: str
    slot: int
    provider_id: str
    observed_at_utc: str
    primitive_family: str
    fee_source: str
    decoder_status: str
    data_status: str
    confidence_level: str
    route_family: str
    instruction_location: str
    program_id: str
    amount_lamports: Optional[int]
    amount_token: Optional[int]
    mint: str
    unit_price_microlamports: Optional[int]
    unit_limit: Optional[int]
    reason_codes: tuple[str, ...]
    numeric_features: Mapping[str, object]
    evidence: Mapping[str, object]
    missing_features: tuple[str, ...]
    input_hash: str
    primitive_hash: str
    created_at_utc: str


# ---------------------------------------------------------------------------
# Stage24RunnerResult
# ---------------------------------------------------------------------------


class Stage24RunnerResult(NamedTuple):
    """Immutable wrapper bundling all per-decoder result tuples.

    Stage 24.6 runner constructs this from a tuple of
    ``Stage24ExecutionInput`` records and the per-family decoder
    outputs. Stage 24.1 ships the record shape only.
    """

    compute_budget_results: tuple[Stage24ComputeBudgetResult, ...]
    priority_fee_results: tuple[Stage24PriorityFeeResult, ...]
    jito_tip_results: tuple[Stage24JitoTipResult, ...]
    router_fee_results: tuple[Stage24RouterFeeResult, ...]
    execution_quality_results: tuple[Stage24ExecutionQualityResult, ...]
    execution_primitives: tuple[Stage24ExecutionPrimitive, ...]
    input_count: int
    input_rejection_count: int
    created_at_utc: str


# ---------------------------------------------------------------------------
# Closed-set helpers
# ---------------------------------------------------------------------------


def assert_primitive_family_in_closed_set(primitive_family: str) -> None:
    if primitive_family not in PRIMITIVE_FAMILIES:
        raise Stage24ContractError(
            f"primitive_family {primitive_family!r} is not a closed-set "
            "Stage 24 primitive_family"
        )


def assert_decoder_status_in_closed_set(decoder_status: str) -> None:
    if decoder_status not in DECODER_STATUSES:
        raise Stage24ContractError(
            f"decoder_status {decoder_status!r} is not a closed-set "
            "Stage 24 decoder_status"
        )


def assert_data_status_in_closed_set(data_status: str) -> None:
    if data_status not in DATA_STATUSES:
        raise Stage24ContractError(
            f"data_status {data_status!r} is not a closed-set Stage 24 "
            "data_status"
        )


def assert_confidence_level_in_closed_set(confidence_level: str) -> None:
    if confidence_level not in CONFIDENCE_LEVELS:
        raise Stage24ContractError(
            f"confidence_level {confidence_level!r} is not a closed-set "
            "Stage 24 confidence_level"
        )


def assert_fee_source_in_closed_set(fee_source: str) -> None:
    if fee_source not in FEE_SOURCES:
        raise Stage24ContractError(
            f"fee_source {fee_source!r} is not a closed-set Stage 24 "
            "fee_source"
        )


def assert_route_family_in_closed_set(route_family: str) -> None:
    if route_family not in ROUTE_FAMILIES:
        raise Stage24ContractError(
            f"route_family {route_family!r} is not a closed-set Stage 24 "
            "route_family"
        )


def assert_instruction_location_in_closed_set(instruction_location: str) -> None:
    if instruction_location not in INSTRUCTION_LOCATIONS:
        raise Stage24ContractError(
            f"instruction_location {instruction_location!r} is not a "
            "closed-set Stage 24 instruction_location"
        )


def assert_optional_non_negative_int(
    *,
    field_name: str,
    value: object,
) -> None:
    """Raise ``Stage24ContractError`` unless ``value`` is ``None`` or a
    non-negative ``int`` (excluding ``bool``).

    Stage 24's amount fields encode "unknown" as ``None`` and a
    decoded amount as a non-negative int. A negative value is a
    contract violation; ``0`` is permitted only as a real decoded
    zero (never as a stand-in for unknown).
    """
    if value is None:
        return
    if isinstance(value, bool):
        raise Stage24ContractError(
            f"{field_name}: bool is not a valid optional non-negative int"
        )
    if not isinstance(value, int):
        raise Stage24ContractError(
            f"{field_name}: expected int or None, got "
            f"{type(value).__name__}"
        )
    if value < 0:
        raise Stage24ContractError(
            f"{field_name}: must be >= 0 or None"
        )


# ---------------------------------------------------------------------------
# Canonical-JSON / hash helpers
# ---------------------------------------------------------------------------


def _canonicalize(value: object) -> object:
    """Reduce ``value`` to a json.dumps-able shape with deterministic ordering.

    Supported value types:

      * ``str`` / ``int`` / ``bool`` / ``None``
      * ``float`` (must be finite)
      * ``list`` / ``tuple``      -- canonicalized element-wise;
                                     emitted as a list.
      * ``Mapping``               -- canonicalized recursively;
                                     emitted as a dict with sorted
                                     keys. Keys must be strings.

    Any other type raises ``Stage24ContractError``.

    NaN / Infinity / -Infinity raise: they cannot round-trip
    through strict JSON.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise Stage24ContractError(
                "non-finite float (NaN / Infinity) cannot be canonicalized"
            )
        return value
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, (list, tuple)):
        return [_canonicalize(item) for item in value]
    if isinstance(value, Mapping):
        out: dict[str, object] = {}
        for key, val in value.items():
            if not isinstance(key, str):
                raise Stage24ContractError(
                    "canonicalize requires string mapping keys; got "
                    f"{type(key).__name__}"
                )
            out[key] = _canonicalize(val)
        return out
    raise Stage24ContractError(
        f"canonicalize cannot encode type {type(value).__name__}"
    )


def canonical_json(value: object) -> str:
    """Return the canonical JSON encoding of ``value``.

    Canonical form: sorted keys, no whitespace separators,
    ASCII-safe (non-ASCII characters are escaped via the JSON
    ``\\uXXXX`` form).
    """
    reduced = _canonicalize(value)
    return json.dumps(
        reduced,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )


def stage24_hash(value: object) -> str:
    """Return the sha256 hex digest of ``canonical_json(value)``."""
    encoded = canonical_json(value).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


# ---------------------------------------------------------------------------
# Stage 24 input / result hash builders
# ---------------------------------------------------------------------------


def _execution_input_canonical_body(
    execution_input: Stage24ExecutionInput,
) -> dict[str, object]:
    """Build the canonical body that ``payload_hash`` covers.

    The body covers the input identity projection. The
    ``payload_hash`` field itself is NOT included (it would be a
    self-reference). The ``input_id`` field is ALSO NOT included
    because it is derived from the payload_hash itself when the
    upstream row carries no signature -- including it would
    create a circular hash dependency.
    """
    return {
        "input_kind": execution_input.input_kind,
        "schema_version": execution_input.schema_version,
        "signature": execution_input.signature,
        "slot": execution_input.slot,
        "slot_unix_time": execution_input.slot_unix_time,
        "observed_at_utc": execution_input.observed_at_utc,
        "provider_id": execution_input.provider_id,
        "transaction_status": execution_input.transaction_status,
        "account_keys": list(execution_input.account_keys),
        "top_level_instructions": [
            _canonicalize(item)
            for item in execution_input.top_level_instructions
        ],
        "inner_instructions": [
            _canonicalize(item)
            for item in execution_input.inner_instructions
        ],
        "pre_balances": list(execution_input.pre_balances),
        "post_balances": list(execution_input.post_balances),
        "pre_token_balances": [
            _canonicalize(item)
            for item in execution_input.pre_token_balances
        ],
        "post_token_balances": [
            _canonicalize(item)
            for item in execution_input.post_token_balances
        ],
        "log_messages": list(execution_input.log_messages),
        "meta": _canonicalize(execution_input.meta),
        "missing_fields": list(execution_input.missing_fields),
    }


def compute_execution_input_hash(
    execution_input: Stage24ExecutionInput,
) -> str:
    """Return the deterministic ``payload_hash`` for ``execution_input``."""
    return stage24_hash(_execution_input_canonical_body(execution_input))


def compute_execution_input_hash_from_projection(
    *,
    input_kind: str,
    schema_version: str,
    signature: str,
    slot: int,
    slot_unix_time: int,
    observed_at_utc: str,
    provider_id: str,
    transaction_status: str,
    account_keys: tuple[str, ...],
    top_level_instructions: tuple[Mapping[str, object], ...],
    inner_instructions: tuple[Mapping[str, object], ...],
    pre_balances: tuple[int, ...],
    post_balances: tuple[int, ...],
    pre_token_balances: tuple[Mapping[str, object], ...],
    post_token_balances: tuple[Mapping[str, object], ...],
    log_messages: tuple[str, ...],
    meta: Mapping[str, object],
    missing_fields: tuple[str, ...],
) -> str:
    """Compute the payload hash from a projection without building the record.

    Used by the input reader to derive a payload hash before
    instantiating the ``Stage24ExecutionInput``. The ``input_id``
    field is intentionally NOT included in the hash body: when
    the upstream row carries no signature, ``input_id`` is itself
    derived from this hash, so including it would be circular.
    """
    body: dict[str, object] = {
        "input_kind": input_kind,
        "schema_version": schema_version,
        "signature": signature,
        "slot": slot,
        "slot_unix_time": slot_unix_time,
        "observed_at_utc": observed_at_utc,
        "provider_id": provider_id,
        "transaction_status": transaction_status,
        "account_keys": list(account_keys),
        "top_level_instructions": [
            _canonicalize(item) for item in top_level_instructions
        ],
        "inner_instructions": [
            _canonicalize(item) for item in inner_instructions
        ],
        "pre_balances": list(pre_balances),
        "post_balances": list(post_balances),
        "pre_token_balances": [
            _canonicalize(item) for item in pre_token_balances
        ],
        "post_token_balances": [
            _canonicalize(item) for item in post_token_balances
        ],
        "log_messages": list(log_messages),
        "meta": _canonicalize(meta),
        "missing_fields": list(missing_fields),
    }
    return stage24_hash(body)


def compute_result_hash(
    *,
    primitive_family: str,
    decoder_name: str,
    decoder_version: str,
    threshold_version: str,
    decoder_status: str,
    data_status: str,
    confidence_level: str,
    fee_source: str,
    route_family: str,
    extra: Mapping[str, object],
) -> str:
    """Return the deterministic ``result_hash`` for a per-decoder result.

    ``extra`` carries the decoder-specific body fields (e.g.
    ``unit_limit`` / ``tip_account`` / ``amount_lamports``).
    Stage 24's result hash binds the shared decoder metadata
    plus the decoder-specific body so two different decoders
    producing the same body never collide on a single hash.
    """
    body: dict[str, object] = {
        "primitive_family": primitive_family,
        "decoder_name": decoder_name,
        "decoder_version": decoder_version,
        "threshold_version": threshold_version,
        "decoder_status": decoder_status,
        "data_status": data_status,
        "confidence_level": confidence_level,
        "fee_source": fee_source,
        "route_family": route_family,
        "extra": _canonicalize(extra),
    }
    return stage24_hash(body)


def compute_primitive_hash(
    primitive: Stage24ExecutionPrimitive,
) -> str:
    """Return the deterministic ``primitive_hash`` for a unified primitive.

    The body excludes ``observed_at_utc`` / ``created_at_utc`` /
    ``primitive_hash`` itself so the hash is stable across runs
    that share the same logical primitive but different wall-clock
    times.
    """
    body: dict[str, object] = {
        "tx_signature": primitive.tx_signature,
        "slot": primitive.slot,
        "provider_id": primitive.provider_id,
        "primitive_family": primitive.primitive_family,
        "fee_source": primitive.fee_source,
        "decoder_status": primitive.decoder_status,
        "data_status": primitive.data_status,
        "confidence_level": primitive.confidence_level,
        "route_family": primitive.route_family,
        "instruction_location": primitive.instruction_location,
        "program_id": primitive.program_id,
        "amount_lamports": primitive.amount_lamports,
        "amount_token": primitive.amount_token,
        "mint": primitive.mint,
        "unit_price_microlamports": primitive.unit_price_microlamports,
        "unit_limit": primitive.unit_limit,
        "reason_codes": list(primitive.reason_codes),
        "numeric_features": _canonicalize(primitive.numeric_features),
        "evidence": _canonicalize(primitive.evidence),
        "missing_features": list(primitive.missing_features),
        "input_hash": primitive.input_hash,
    }
    return stage24_hash(body)


# ---------------------------------------------------------------------------
# Validating builders
# ---------------------------------------------------------------------------


def _require_non_empty_string(field_name: str, value: object) -> None:
    if not isinstance(value, str) or value == "":
        raise Stage24ContractError(
            f"{field_name} must be a non-empty string"
        )


def _require_tuple_of_strings(
    field_name: str,
    value: object,
) -> None:
    if not isinstance(value, tuple):
        raise Stage24ContractError(f"{field_name} must be a tuple")
    for item in value:
        if not isinstance(item, str) or item == "":
            raise Stage24ContractError(
                f"each {field_name} item must be a non-empty string"
            )


def _require_mapping(field_name: str, value: object) -> None:
    if not isinstance(value, Mapping):
        raise Stage24ContractError(
            f"{field_name} must be a mapping"
        )


def build_compute_budget_result(
    *,
    decoder_name: str,
    decoder_version: str,
    threshold_version: str,
    decoder_status: str,
    data_status: str,
    confidence_level: str,
    fee_source: str,
    route_family: str,
    instruction_location: str,
    program_id: str,
    unit_limit: Optional[int],
    unit_price_microlamports: Optional[int],
    reason_codes: tuple[str, ...],
    numeric_features: Mapping[str, object],
    evidence: Mapping[str, object],
    input_missing_fields: tuple[str, ...],
) -> Stage24ComputeBudgetResult:
    """Build a ``Stage24ComputeBudgetResult`` with closed-set validation."""
    _require_non_empty_string("decoder_name", decoder_name)
    _require_non_empty_string("decoder_version", decoder_version)
    _require_non_empty_string("threshold_version", threshold_version)
    assert_decoder_status_in_closed_set(decoder_status)
    assert_data_status_in_closed_set(data_status)
    assert_confidence_level_in_closed_set(confidence_level)
    assert_fee_source_in_closed_set(fee_source)
    assert_route_family_in_closed_set(route_family)
    assert_instruction_location_in_closed_set(instruction_location)
    if not isinstance(program_id, str):
        raise Stage24ContractError("program_id must be a string")
    assert_optional_non_negative_int(
        field_name="unit_limit", value=unit_limit
    )
    assert_optional_non_negative_int(
        field_name="unit_price_microlamports",
        value=unit_price_microlamports,
    )
    _require_tuple_of_strings("reason_codes", reason_codes)
    _require_mapping("numeric_features", numeric_features)
    _require_mapping("evidence", evidence)
    if not isinstance(input_missing_fields, tuple):
        raise Stage24ContractError(
            "input_missing_fields must be a tuple"
        )
    _require_tuple_of_strings("input_missing_fields", input_missing_fields)
    primitive_family = "COMPUTE_BUDGET"
    result_hash = compute_result_hash(
        primitive_family=primitive_family,
        decoder_name=decoder_name,
        decoder_version=decoder_version,
        threshold_version=threshold_version,
        decoder_status=decoder_status,
        data_status=data_status,
        confidence_level=confidence_level,
        fee_source=fee_source,
        route_family=route_family,
        extra={
            "instruction_location": instruction_location,
            "program_id": program_id,
            "unit_limit": unit_limit,
            "unit_price_microlamports": unit_price_microlamports,
            "reason_codes": list(reason_codes),
            "numeric_features": _canonicalize(numeric_features),
            "evidence": _canonicalize(evidence),
            "input_missing_fields": list(input_missing_fields),
        },
    )
    return Stage24ComputeBudgetResult(
        primitive_family=primitive_family,
        decoder_name=decoder_name,
        decoder_version=decoder_version,
        threshold_version=threshold_version,
        decoder_status=decoder_status,
        data_status=data_status,
        confidence_level=confidence_level,
        fee_source=fee_source,
        route_family=route_family,
        instruction_location=instruction_location,
        program_id=program_id,
        unit_limit=unit_limit,
        unit_price_microlamports=unit_price_microlamports,
        reason_codes=reason_codes,
        numeric_features=numeric_features,
        evidence=evidence,
        input_missing_fields=input_missing_fields,
        result_hash=result_hash,
    )


def build_priority_fee_result(
    *,
    decoder_name: str,
    decoder_version: str,
    threshold_version: str,
    decoder_status: str,
    data_status: str,
    confidence_level: str,
    fee_source: str,
    route_family: str,
    instruction_location: str,
    program_id: str,
    amount_lamports: Optional[int],
    unit_limit: Optional[int],
    unit_price_microlamports: Optional[int],
    reason_codes: tuple[str, ...],
    numeric_features: Mapping[str, object],
    evidence: Mapping[str, object],
    input_missing_fields: tuple[str, ...],
) -> Stage24PriorityFeeResult:
    """Build a ``Stage24PriorityFeeResult`` with closed-set validation."""
    _require_non_empty_string("decoder_name", decoder_name)
    _require_non_empty_string("decoder_version", decoder_version)
    _require_non_empty_string("threshold_version", threshold_version)
    assert_decoder_status_in_closed_set(decoder_status)
    assert_data_status_in_closed_set(data_status)
    assert_confidence_level_in_closed_set(confidence_level)
    assert_fee_source_in_closed_set(fee_source)
    assert_route_family_in_closed_set(route_family)
    assert_instruction_location_in_closed_set(instruction_location)
    if not isinstance(program_id, str):
        raise Stage24ContractError("program_id must be a string")
    assert_optional_non_negative_int(
        field_name="amount_lamports", value=amount_lamports
    )
    assert_optional_non_negative_int(
        field_name="unit_limit", value=unit_limit
    )
    assert_optional_non_negative_int(
        field_name="unit_price_microlamports",
        value=unit_price_microlamports,
    )
    _require_tuple_of_strings("reason_codes", reason_codes)
    _require_mapping("numeric_features", numeric_features)
    _require_mapping("evidence", evidence)
    if not isinstance(input_missing_fields, tuple):
        raise Stage24ContractError(
            "input_missing_fields must be a tuple"
        )
    _require_tuple_of_strings("input_missing_fields", input_missing_fields)
    primitive_family = "PRIORITY_FEE"
    result_hash = compute_result_hash(
        primitive_family=primitive_family,
        decoder_name=decoder_name,
        decoder_version=decoder_version,
        threshold_version=threshold_version,
        decoder_status=decoder_status,
        data_status=data_status,
        confidence_level=confidence_level,
        fee_source=fee_source,
        route_family=route_family,
        extra={
            "instruction_location": instruction_location,
            "program_id": program_id,
            "amount_lamports": amount_lamports,
            "unit_limit": unit_limit,
            "unit_price_microlamports": unit_price_microlamports,
            "reason_codes": list(reason_codes),
            "numeric_features": _canonicalize(numeric_features),
            "evidence": _canonicalize(evidence),
            "input_missing_fields": list(input_missing_fields),
        },
    )
    return Stage24PriorityFeeResult(
        primitive_family=primitive_family,
        decoder_name=decoder_name,
        decoder_version=decoder_version,
        threshold_version=threshold_version,
        decoder_status=decoder_status,
        data_status=data_status,
        confidence_level=confidence_level,
        fee_source=fee_source,
        route_family=route_family,
        instruction_location=instruction_location,
        program_id=program_id,
        amount_lamports=amount_lamports,
        unit_limit=unit_limit,
        unit_price_microlamports=unit_price_microlamports,
        reason_codes=reason_codes,
        numeric_features=numeric_features,
        evidence=evidence,
        input_missing_fields=input_missing_fields,
        result_hash=result_hash,
    )


def build_jito_tip_result(
    *,
    decoder_name: str,
    decoder_version: str,
    threshold_version: str,
    decoder_status: str,
    data_status: str,
    confidence_level: str,
    fee_source: str,
    route_family: str,
    instruction_location: str,
    program_id: str,
    tip_account: str,
    amount_lamports: Optional[int],
    reason_codes: tuple[str, ...],
    numeric_features: Mapping[str, object],
    evidence: Mapping[str, object],
    input_missing_fields: tuple[str, ...],
) -> Stage24JitoTipResult:
    """Build a ``Stage24JitoTipResult`` with closed-set validation."""
    _require_non_empty_string("decoder_name", decoder_name)
    _require_non_empty_string("decoder_version", decoder_version)
    _require_non_empty_string("threshold_version", threshold_version)
    assert_decoder_status_in_closed_set(decoder_status)
    assert_data_status_in_closed_set(data_status)
    assert_confidence_level_in_closed_set(confidence_level)
    assert_fee_source_in_closed_set(fee_source)
    assert_route_family_in_closed_set(route_family)
    assert_instruction_location_in_closed_set(instruction_location)
    if not isinstance(program_id, str):
        raise Stage24ContractError("program_id must be a string")
    if not isinstance(tip_account, str):
        raise Stage24ContractError("tip_account must be a string")
    assert_optional_non_negative_int(
        field_name="amount_lamports", value=amount_lamports
    )
    _require_tuple_of_strings("reason_codes", reason_codes)
    _require_mapping("numeric_features", numeric_features)
    _require_mapping("evidence", evidence)
    if not isinstance(input_missing_fields, tuple):
        raise Stage24ContractError(
            "input_missing_fields must be a tuple"
        )
    _require_tuple_of_strings("input_missing_fields", input_missing_fields)
    primitive_family = "JITO_TIP"
    result_hash = compute_result_hash(
        primitive_family=primitive_family,
        decoder_name=decoder_name,
        decoder_version=decoder_version,
        threshold_version=threshold_version,
        decoder_status=decoder_status,
        data_status=data_status,
        confidence_level=confidence_level,
        fee_source=fee_source,
        route_family=route_family,
        extra={
            "instruction_location": instruction_location,
            "program_id": program_id,
            "tip_account": tip_account,
            "amount_lamports": amount_lamports,
            "reason_codes": list(reason_codes),
            "numeric_features": _canonicalize(numeric_features),
            "evidence": _canonicalize(evidence),
            "input_missing_fields": list(input_missing_fields),
        },
    )
    return Stage24JitoTipResult(
        primitive_family=primitive_family,
        decoder_name=decoder_name,
        decoder_version=decoder_version,
        threshold_version=threshold_version,
        decoder_status=decoder_status,
        data_status=data_status,
        confidence_level=confidence_level,
        fee_source=fee_source,
        route_family=route_family,
        instruction_location=instruction_location,
        program_id=program_id,
        tip_account=tip_account,
        amount_lamports=amount_lamports,
        reason_codes=reason_codes,
        numeric_features=numeric_features,
        evidence=evidence,
        input_missing_fields=input_missing_fields,
        result_hash=result_hash,
    )


def build_router_fee_result(
    *,
    decoder_name: str,
    decoder_version: str,
    threshold_version: str,
    decoder_status: str,
    data_status: str,
    confidence_level: str,
    fee_source: str,
    route_family: str,
    instruction_location: str,
    program_id: str,
    amount_lamports: Optional[int],
    amount_token: Optional[int],
    mint: str,
    reason_codes: tuple[str, ...],
    numeric_features: Mapping[str, object],
    evidence: Mapping[str, object],
    input_missing_fields: tuple[str, ...],
) -> Stage24RouterFeeResult:
    """Build a ``Stage24RouterFeeResult`` with closed-set validation.

    Validates closed sets, string shapes, and optional non-negative
    int amounts. Stage-specific invariants (e.g. Stage 24.4 must
    keep ``amount_lamports`` ``None`` for every router-fee path)
    are enforced by the calling decoder, not by this helper -- the
    same ``Stage24RouterFeeResult`` type spans both Stage 24.4
    candidates and the eventual Stage 24.5 confirmed decoder.
    """
    _require_non_empty_string("decoder_name", decoder_name)
    _require_non_empty_string("decoder_version", decoder_version)
    _require_non_empty_string("threshold_version", threshold_version)
    assert_decoder_status_in_closed_set(decoder_status)
    assert_data_status_in_closed_set(data_status)
    assert_confidence_level_in_closed_set(confidence_level)
    assert_fee_source_in_closed_set(fee_source)
    assert_route_family_in_closed_set(route_family)
    assert_instruction_location_in_closed_set(instruction_location)
    if not isinstance(program_id, str):
        raise Stage24ContractError("program_id must be a string")
    if not isinstance(mint, str):
        raise Stage24ContractError("mint must be a string")
    assert_optional_non_negative_int(
        field_name="amount_lamports", value=amount_lamports
    )
    assert_optional_non_negative_int(
        field_name="amount_token", value=amount_token
    )
    _require_tuple_of_strings("reason_codes", reason_codes)
    _require_mapping("numeric_features", numeric_features)
    _require_mapping("evidence", evidence)
    if not isinstance(input_missing_fields, tuple):
        raise Stage24ContractError(
            "input_missing_fields must be a tuple"
        )
    _require_tuple_of_strings("input_missing_fields", input_missing_fields)
    primitive_family = "ROUTER_FEE"
    result_hash = compute_result_hash(
        primitive_family=primitive_family,
        decoder_name=decoder_name,
        decoder_version=decoder_version,
        threshold_version=threshold_version,
        decoder_status=decoder_status,
        data_status=data_status,
        confidence_level=confidence_level,
        fee_source=fee_source,
        route_family=route_family,
        extra={
            "instruction_location": instruction_location,
            "program_id": program_id,
            "amount_lamports": amount_lamports,
            "amount_token": amount_token,
            "mint": mint,
            "reason_codes": list(reason_codes),
            "numeric_features": _canonicalize(numeric_features),
            "evidence": _canonicalize(evidence),
            "input_missing_fields": list(input_missing_fields),
        },
    )
    return Stage24RouterFeeResult(
        primitive_family=primitive_family,
        decoder_name=decoder_name,
        decoder_version=decoder_version,
        threshold_version=threshold_version,
        decoder_status=decoder_status,
        data_status=data_status,
        confidence_level=confidence_level,
        fee_source=fee_source,
        route_family=route_family,
        instruction_location=instruction_location,
        program_id=program_id,
        amount_lamports=amount_lamports,
        amount_token=amount_token,
        mint=mint,
        reason_codes=reason_codes,
        numeric_features=numeric_features,
        evidence=evidence,
        input_missing_fields=input_missing_fields,
        result_hash=result_hash,
    )


__all__ = [
    "Stage24ComputeBudgetResult",
    "Stage24ExecutionInput",
    "Stage24ExecutionPrimitive",
    "Stage24ExecutionQualityResult",
    "Stage24JitoTipResult",
    "Stage24PriorityFeeResult",
    "Stage24RouterFeeResult",
    "Stage24RunnerResult",
    "assert_confidence_level_in_closed_set",
    "assert_data_status_in_closed_set",
    "assert_decoder_status_in_closed_set",
    "assert_fee_source_in_closed_set",
    "assert_instruction_location_in_closed_set",
    "assert_optional_non_negative_int",
    "assert_primitive_family_in_closed_set",
    "assert_route_family_in_closed_set",
    "build_compute_budget_result",
    "build_jito_tip_result",
    "build_priority_fee_result",
    "build_router_fee_result",
    "canonical_json",
    "compute_execution_input_hash",
    "compute_execution_input_hash_from_projection",
    "compute_primitive_hash",
    "compute_result_hash",
    "stage24_hash",
]

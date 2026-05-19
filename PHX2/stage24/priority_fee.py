"""Stage 24.2 priority-fee primitive decoder.

Derives a per-transaction priority-fee primitive from:

  * the upstream ComputeBudget decoder output
    (``compute_unit_limit`` / ``micro_lamports_per_compute_unit``),
  * ``compute_units_consumed`` from the upstream observation's
    ``meta`` mapping when present,
  * optionally ``fee`` (the upstream total meta fee) for evidence
    only.

This decoder NEVER calls a Solana SDK, parses raw instruction
bytes, or contacts a network endpoint. It composes the
ComputeBudget decoder result with meta fields the Stage 24.1
input reader has already projected.

Honesty rules (mirrors Stage 24 brainstorm doc Section 14):

  * No compute-unit price observed (ComputeBudget absent OR
    ComputeBudget decoded but no ``SetComputeUnitPrice``
    instruction): ``decoder_status = ABSENT``,
    ``amount_lamports = None``. Never zero as a stand-in.

  * Compute-unit price observed but ``compute_units_consumed``
    missing: ``decoder_status = PARTIAL``,
    ``amount_lamports = None``. The price is recorded; the
    realized fee is not derivable.

  * Compute-unit price and ``compute_units_consumed`` both
    observed: ``decoder_status = DECODED``,
    ``amount_lamports = ceil(price * consumed / 1_000_000)``.
    The value is recorded as estimated in
    ``priority_fee_estimated_lamports`` (numeric features). The
    observed-realized variant ``priority_fee_observed_lamports``
    remains ``None`` because Stage 24 cannot separate base fee
    from priority fee without sanctioned upstream evidence.

  * ComputeBudget decoder returned ``DECODE_FAILED``:
    ``decoder_status = DECODE_FAILED``, ``amount_lamports = None``.
    Do not propagate a fee value from a malformed compute-budget
    observation.

  * ComputeBudget decoder returned ``DECODE_UNCONFIRMED`` (two or
    more ``SetComputeUnitPrice`` instructions): ``decoder_status =
    DECODE_UNCONFIRMED``, ``amount_lamports = None``. The price
    is ambiguous; the decoder refuses to pick one.

Reuse contract:

  * This module imports ``decode_compute_budget`` from
    ``PHX2.stage24.compute_budget`` and reuses its output. It
    does NOT re-parse instruction bytes.

This module imports only stdlib (``types`` / ``typing``) plus
the Stage 24 constants, models, and the ComputeBudget decoder.
It does NOT import Stage 21 / Stage 22 / Stage 23 modules; it
does NOT import any network / RPC / messaging / DB / scheduler /
secrets-management library; it does NOT read the process
environment; it does NOT define a CLI surface; and it contains
no top-level I/O.
"""

from __future__ import annotations

from types import MappingProxyType
from typing import Mapping

from PHX2.stage24.compute_budget import (
    COMPUTE_BUDGET_DECODER_NAME,
    DATA_ENCODING_BASE64,
    REASON_COMPUTE_BUDGET_MALFORMED_DATA,
    REASON_COMPUTE_BUDGET_UNKNOWN_TAG,
    REASON_MULTIPLE_COMPUTE_UNIT_PRICE_INSTRUCTIONS,
    decode_compute_budget,
)
from PHX2.stage24.constants import (
    COMPUTE_BUDGET_PROGRAM_ID,
    CONFIDENCE_LEVEL_HIGH,
    CONFIDENCE_LEVEL_LOW,
    CONFIDENCE_LEVEL_MEDIUM,
    CONFIDENCE_LEVEL_NONE,
    DATA_STATUS_COMPLETE,
    DATA_STATUS_MALFORMED,
    DATA_STATUS_MISSING,
    DATA_STATUS_PARTIAL,
    DECODER_STATUS_ABSENT,
    DECODER_STATUS_DECODED,
    DECODER_STATUS_DECODE_FAILED,
    DECODER_STATUS_DECODE_UNCONFIRMED,
    DECODER_STATUS_PARTIAL,
    DEFAULT_THRESHOLD_VERSION,
    FEE_SOURCE_PRIORITY_FEE,
    FEE_SOURCE_UNKNOWN,
    INSTRUCTION_LOCATION_TOP_LEVEL,
    INSTRUCTION_LOCATION_UNKNOWN,
    ROUTE_FAMILY_NO_ROUTER_DETECTED,
)
from PHX2.stage24.models import (
    Stage24ComputeBudgetResult,
    Stage24ExecutionInput,
    Stage24PriorityFeeResult,
    build_priority_fee_result,
)


# ---------------------------------------------------------------------------
# Decoder identity
# ---------------------------------------------------------------------------


PRIORITY_FEE_DECODER_NAME: str = "priority_fee_v0"
PRIORITY_FEE_DECODER_VERSION: str = "stage24_v0_priority_fee"


# ---------------------------------------------------------------------------
# Microlamports-per-CU lamport conversion divisor
# ---------------------------------------------------------------------------
#
# The Solana priority fee formula divides
# (micro_lamports_per_compute_unit * compute_units_consumed) by
# 1_000_000 (one million microlamports = one lamport). Stage 24
# applies a ceiling division to match the Solana runtime, which
# rounds the fee up to the nearest lamport.


MICROLAMPORTS_PER_LAMPORT: int = 1_000_000


# ---------------------------------------------------------------------------
# Meta-field key names the priority-fee decoder consumes
# ---------------------------------------------------------------------------


META_KEY_COMPUTE_UNITS_CONSUMED: str = "compute_units_consumed"
META_KEY_FEE: str = "fee"


# ---------------------------------------------------------------------------
# Reason codes
# ---------------------------------------------------------------------------


REASON_PRIORITY_FEE_PRICE_ABSENT: str = "PRIORITY_FEE_PRICE_ABSENT"
REASON_PRIORITY_FEE_PRICE_PRESENT: str = "PRIORITY_FEE_PRICE_PRESENT"
REASON_PRIORITY_FEE_CONSUMED_UNITS_MISSING: str = (
    "PRIORITY_FEE_CONSUMED_UNITS_MISSING"
)
REASON_PRIORITY_FEE_ESTIMATED_FROM_UNIT_PRICE_AND_CONSUMED_UNITS: str = (
    "PRIORITY_FEE_ESTIMATED_FROM_UNIT_PRICE_AND_CONSUMED_UNITS"
)
REASON_PRIORITY_FEE_COMPUTE_BUDGET_DECODE_FAILED: str = (
    "PRIORITY_FEE_COMPUTE_BUDGET_DECODE_FAILED"
)
REASON_PRIORITY_FEE_COMPUTE_BUDGET_AMBIGUOUS_PRICE: str = (
    "PRIORITY_FEE_COMPUTE_BUDGET_AMBIGUOUS_PRICE"
)
REASON_PRIORITY_FEE_META_FEE_OBSERVED: str = (
    "PRIORITY_FEE_META_FEE_OBSERVED"
)


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _project_meta_non_negative_int(
    *,
    meta: Mapping[str, object],
    key: str,
) -> int | None:
    """Return ``meta[key]`` if it is a non-negative ``int`` (not bool); else None.

    The Stage 24.1 input reader projects meta verbatim, so the
    decoder verifies the int shape here before using a value.
    Booleans are rejected because Python treats ``True == 1``.
    """
    raw = meta.get(key)
    if raw is None:
        return None
    if isinstance(raw, bool):
        return None
    if not isinstance(raw, int):
        return None
    if raw < 0:
        return None
    return raw


def _ceil_div_microlamports_to_lamports(
    *,
    micro_lamports_total: int,
) -> int:
    """Ceiling-divide a microlamport total to a lamport total.

    Pure integer arithmetic; no float intermediate. Matches the
    Solana runtime's rounding behavior on priority-fee charging.
    """
    return (
        micro_lamports_total + MICROLAMPORTS_PER_LAMPORT - 1
    ) // MICROLAMPORTS_PER_LAMPORT


# ---------------------------------------------------------------------------
# Public decoder
# ---------------------------------------------------------------------------


def decode_priority_fee(
    execution_input: Stage24ExecutionInput,
) -> Stage24PriorityFeeResult:
    """Decode the priority-fee primitive for one transaction.

    Pure function: depends only on ``execution_input``. Composes
    the ComputeBudget decoder's output with the upstream
    ``meta.compute_units_consumed`` field when present.
    """
    compute_budget_result = decode_compute_budget(execution_input)
    return derive_priority_fee_from_compute_budget(
        execution_input=execution_input,
        compute_budget_result=compute_budget_result,
    )


def derive_priority_fee_from_compute_budget(
    *,
    execution_input: Stage24ExecutionInput,
    compute_budget_result: Stage24ComputeBudgetResult,
) -> Stage24PriorityFeeResult:
    """Derive a priority-fee result from a pre-computed ComputeBudget result.

    Exposed as a public function so a future Stage 24.6 runner
    can decode compute-budget once and reuse the result across
    decoders without re-parsing instruction bytes.
    """
    consumed_units = _project_meta_non_negative_int(
        meta=execution_input.meta,
        key=META_KEY_COMPUTE_UNITS_CONSUMED,
    )
    meta_fee_lamports = _project_meta_non_negative_int(
        meta=execution_input.meta,
        key=META_KEY_FEE,
    )

    compute_budget_status = compute_budget_result.decoder_status
    price = compute_budget_result.unit_price_microlamports
    limit = compute_budget_result.unit_limit

    base_numeric_features: dict[str, object] = {
        "compute_unit_limit": limit,
        "micro_lamports_per_compute_unit": price,
        "compute_units_consumed": consumed_units,
        "priority_fee_estimated_lamports": None,
        "priority_fee_observed_lamports": None,
        "meta_fee_lamports": meta_fee_lamports,
    }

    base_evidence: dict[str, object] = {
        "compute_budget_decoder_status": compute_budget_status,
        "compute_budget_result_hash": compute_budget_result.result_hash,
        "compute_budget_reason_codes": list(
            compute_budget_result.reason_codes
        ),
        "program_id": COMPUTE_BUDGET_PROGRAM_ID,
        "data_encoding": DATA_ENCODING_BASE64,
        "upstream_decoder_name": COMPUTE_BUDGET_DECODER_NAME,
        "compute_units_consumed_present": consumed_units is not None,
        "meta_fee_lamports_present": meta_fee_lamports is not None,
    }

    if compute_budget_status == DECODER_STATUS_DECODE_FAILED:
        return _build_priority_fee_compute_budget_decode_failed(
            execution_input=execution_input,
            base_numeric_features=base_numeric_features,
            base_evidence=base_evidence,
            compute_budget_reason_codes=compute_budget_result.reason_codes,
            meta_fee_lamports=meta_fee_lamports,
        )

    if compute_budget_status == DECODER_STATUS_DECODE_UNCONFIRMED:
        return _build_priority_fee_compute_budget_ambiguous_price(
            execution_input=execution_input,
            base_numeric_features=base_numeric_features,
            base_evidence=base_evidence,
            unit_limit=limit,
            meta_fee_lamports=meta_fee_lamports,
        )

    if price is None:
        return _build_priority_fee_price_absent(
            execution_input=execution_input,
            base_numeric_features=base_numeric_features,
            base_evidence=base_evidence,
            unit_limit=limit,
            meta_fee_lamports=meta_fee_lamports,
        )

    if consumed_units is None:
        return _build_priority_fee_consumed_units_missing(
            execution_input=execution_input,
            base_numeric_features=base_numeric_features,
            base_evidence=base_evidence,
            unit_limit=limit,
            unit_price_microlamports=price,
            meta_fee_lamports=meta_fee_lamports,
        )

    micro_lamports_total = price * consumed_units
    estimated_lamports = _ceil_div_microlamports_to_lamports(
        micro_lamports_total=micro_lamports_total,
    )

    return _build_priority_fee_decoded(
        execution_input=execution_input,
        base_numeric_features=base_numeric_features,
        base_evidence=base_evidence,
        unit_limit=limit,
        unit_price_microlamports=price,
        consumed_units=consumed_units,
        estimated_lamports=estimated_lamports,
        micro_lamports_total=micro_lamports_total,
        meta_fee_lamports=meta_fee_lamports,
    )


# ---------------------------------------------------------------------------
# Result builders
# ---------------------------------------------------------------------------


def _build_priority_fee_compute_budget_decode_failed(
    *,
    execution_input: Stage24ExecutionInput,
    base_numeric_features: dict[str, object],
    base_evidence: dict[str, object],
    compute_budget_reason_codes: tuple[str, ...],
    meta_fee_lamports: int | None,
) -> Stage24PriorityFeeResult:
    reasons: list[str] = [REASON_PRIORITY_FEE_COMPUTE_BUDGET_DECODE_FAILED]
    if REASON_COMPUTE_BUDGET_UNKNOWN_TAG in compute_budget_reason_codes:
        reasons.append(REASON_COMPUTE_BUDGET_UNKNOWN_TAG)
    if REASON_COMPUTE_BUDGET_MALFORMED_DATA in compute_budget_reason_codes:
        reasons.append(REASON_COMPUTE_BUDGET_MALFORMED_DATA)
    if meta_fee_lamports is not None:
        reasons.append(REASON_PRIORITY_FEE_META_FEE_OBSERVED)
    return build_priority_fee_result(
        decoder_name=PRIORITY_FEE_DECODER_NAME,
        decoder_version=PRIORITY_FEE_DECODER_VERSION,
        threshold_version=DEFAULT_THRESHOLD_VERSION,
        decoder_status=DECODER_STATUS_DECODE_FAILED,
        data_status=DATA_STATUS_MALFORMED,
        confidence_level=CONFIDENCE_LEVEL_NONE,
        fee_source=FEE_SOURCE_UNKNOWN,
        route_family=ROUTE_FAMILY_NO_ROUTER_DETECTED,
        instruction_location=INSTRUCTION_LOCATION_UNKNOWN,
        program_id=COMPUTE_BUDGET_PROGRAM_ID,
        amount_lamports=None,
        unit_limit=None,
        unit_price_microlamports=None,
        reason_codes=tuple(reasons),
        numeric_features=MappingProxyType(dict(base_numeric_features)),
        evidence=MappingProxyType(dict(base_evidence)),
        input_missing_fields=execution_input.missing_fields,
    )


def _build_priority_fee_compute_budget_ambiguous_price(
    *,
    execution_input: Stage24ExecutionInput,
    base_numeric_features: dict[str, object],
    base_evidence: dict[str, object],
    unit_limit: int | None,
    meta_fee_lamports: int | None,
) -> Stage24PriorityFeeResult:
    reasons: list[str] = [
        REASON_PRIORITY_FEE_COMPUTE_BUDGET_AMBIGUOUS_PRICE,
        REASON_MULTIPLE_COMPUTE_UNIT_PRICE_INSTRUCTIONS,
    ]
    if meta_fee_lamports is not None:
        reasons.append(REASON_PRIORITY_FEE_META_FEE_OBSERVED)
    # We did observe priority-fee evidence (multiple price
    # instructions), so fee_source reflects that. The
    # decoder_status surfaces the ambiguity.
    return build_priority_fee_result(
        decoder_name=PRIORITY_FEE_DECODER_NAME,
        decoder_version=PRIORITY_FEE_DECODER_VERSION,
        threshold_version=DEFAULT_THRESHOLD_VERSION,
        decoder_status=DECODER_STATUS_DECODE_UNCONFIRMED,
        data_status=DATA_STATUS_PARTIAL,
        confidence_level=CONFIDENCE_LEVEL_LOW,
        fee_source=FEE_SOURCE_PRIORITY_FEE,
        route_family=ROUTE_FAMILY_NO_ROUTER_DETECTED,
        instruction_location=INSTRUCTION_LOCATION_TOP_LEVEL,
        program_id=COMPUTE_BUDGET_PROGRAM_ID,
        amount_lamports=None,
        unit_limit=unit_limit,
        unit_price_microlamports=None,
        reason_codes=tuple(reasons),
        numeric_features=MappingProxyType(dict(base_numeric_features)),
        evidence=MappingProxyType(dict(base_evidence)),
        input_missing_fields=execution_input.missing_fields,
    )


def _build_priority_fee_price_absent(
    *,
    execution_input: Stage24ExecutionInput,
    base_numeric_features: dict[str, object],
    base_evidence: dict[str, object],
    unit_limit: int | None,
    meta_fee_lamports: int | None,
) -> Stage24PriorityFeeResult:
    reasons: list[str] = [REASON_PRIORITY_FEE_PRICE_ABSENT]
    if meta_fee_lamports is not None:
        reasons.append(REASON_PRIORITY_FEE_META_FEE_OBSERVED)
    instruction_location = (
        INSTRUCTION_LOCATION_TOP_LEVEL
        if unit_limit is not None
        else INSTRUCTION_LOCATION_UNKNOWN
    )
    return build_priority_fee_result(
        decoder_name=PRIORITY_FEE_DECODER_NAME,
        decoder_version=PRIORITY_FEE_DECODER_VERSION,
        threshold_version=DEFAULT_THRESHOLD_VERSION,
        decoder_status=DECODER_STATUS_ABSENT,
        data_status=DATA_STATUS_MISSING,
        confidence_level=CONFIDENCE_LEVEL_NONE,
        fee_source=FEE_SOURCE_UNKNOWN,
        route_family=ROUTE_FAMILY_NO_ROUTER_DETECTED,
        instruction_location=instruction_location,
        program_id="" if unit_limit is None else COMPUTE_BUDGET_PROGRAM_ID,
        amount_lamports=None,
        unit_limit=unit_limit,
        unit_price_microlamports=None,
        reason_codes=tuple(reasons),
        numeric_features=MappingProxyType(dict(base_numeric_features)),
        evidence=MappingProxyType(dict(base_evidence)),
        input_missing_fields=execution_input.missing_fields,
    )


def _build_priority_fee_consumed_units_missing(
    *,
    execution_input: Stage24ExecutionInput,
    base_numeric_features: dict[str, object],
    base_evidence: dict[str, object],
    unit_limit: int | None,
    unit_price_microlamports: int,
    meta_fee_lamports: int | None,
) -> Stage24PriorityFeeResult:
    reasons: list[str] = [
        REASON_PRIORITY_FEE_PRICE_PRESENT,
        REASON_PRIORITY_FEE_CONSUMED_UNITS_MISSING,
    ]
    if meta_fee_lamports is not None:
        reasons.append(REASON_PRIORITY_FEE_META_FEE_OBSERVED)
    return build_priority_fee_result(
        decoder_name=PRIORITY_FEE_DECODER_NAME,
        decoder_version=PRIORITY_FEE_DECODER_VERSION,
        threshold_version=DEFAULT_THRESHOLD_VERSION,
        decoder_status=DECODER_STATUS_PARTIAL,
        data_status=DATA_STATUS_PARTIAL,
        confidence_level=CONFIDENCE_LEVEL_MEDIUM,
        fee_source=FEE_SOURCE_PRIORITY_FEE,
        route_family=ROUTE_FAMILY_NO_ROUTER_DETECTED,
        instruction_location=INSTRUCTION_LOCATION_TOP_LEVEL,
        program_id=COMPUTE_BUDGET_PROGRAM_ID,
        amount_lamports=None,
        unit_limit=unit_limit,
        unit_price_microlamports=unit_price_microlamports,
        reason_codes=tuple(reasons),
        numeric_features=MappingProxyType(dict(base_numeric_features)),
        evidence=MappingProxyType(dict(base_evidence)),
        input_missing_fields=execution_input.missing_fields,
    )


def _build_priority_fee_decoded(
    *,
    execution_input: Stage24ExecutionInput,
    base_numeric_features: dict[str, object],
    base_evidence: dict[str, object],
    unit_limit: int | None,
    unit_price_microlamports: int,
    consumed_units: int,
    estimated_lamports: int,
    micro_lamports_total: int,
    meta_fee_lamports: int | None,
) -> Stage24PriorityFeeResult:
    reasons: list[str] = [
        REASON_PRIORITY_FEE_PRICE_PRESENT,
        REASON_PRIORITY_FEE_ESTIMATED_FROM_UNIT_PRICE_AND_CONSUMED_UNITS,
    ]
    if meta_fee_lamports is not None:
        reasons.append(REASON_PRIORITY_FEE_META_FEE_OBSERVED)

    numeric_features = dict(base_numeric_features)
    numeric_features["priority_fee_estimated_lamports"] = estimated_lamports
    numeric_features["priority_fee_microlamports_total"] = (
        micro_lamports_total
    )

    evidence = dict(base_evidence)
    evidence["priority_fee_estimation_divisor_microlamports"] = (
        MICROLAMPORTS_PER_LAMPORT
    )
    evidence["priority_fee_estimation_rounding"] = "ceiling"

    return build_priority_fee_result(
        decoder_name=PRIORITY_FEE_DECODER_NAME,
        decoder_version=PRIORITY_FEE_DECODER_VERSION,
        threshold_version=DEFAULT_THRESHOLD_VERSION,
        decoder_status=DECODER_STATUS_DECODED,
        data_status=DATA_STATUS_COMPLETE,
        confidence_level=CONFIDENCE_LEVEL_HIGH,
        fee_source=FEE_SOURCE_PRIORITY_FEE,
        route_family=ROUTE_FAMILY_NO_ROUTER_DETECTED,
        instruction_location=INSTRUCTION_LOCATION_TOP_LEVEL,
        program_id=COMPUTE_BUDGET_PROGRAM_ID,
        amount_lamports=estimated_lamports,
        unit_limit=unit_limit,
        unit_price_microlamports=unit_price_microlamports,
        reason_codes=tuple(reasons),
        numeric_features=MappingProxyType(numeric_features),
        evidence=MappingProxyType(evidence),
        input_missing_fields=execution_input.missing_fields,
    )


__all__ = [
    "META_KEY_COMPUTE_UNITS_CONSUMED",
    "META_KEY_FEE",
    "MICROLAMPORTS_PER_LAMPORT",
    "PRIORITY_FEE_DECODER_NAME",
    "PRIORITY_FEE_DECODER_VERSION",
    "REASON_PRIORITY_FEE_COMPUTE_BUDGET_AMBIGUOUS_PRICE",
    "REASON_PRIORITY_FEE_COMPUTE_BUDGET_DECODE_FAILED",
    "REASON_PRIORITY_FEE_CONSUMED_UNITS_MISSING",
    "REASON_PRIORITY_FEE_ESTIMATED_FROM_UNIT_PRICE_AND_CONSUMED_UNITS",
    "REASON_PRIORITY_FEE_META_FEE_OBSERVED",
    "REASON_PRIORITY_FEE_PRICE_ABSENT",
    "REASON_PRIORITY_FEE_PRICE_PRESENT",
    "decode_priority_fee",
    "derive_priority_fee_from_compute_budget",
]

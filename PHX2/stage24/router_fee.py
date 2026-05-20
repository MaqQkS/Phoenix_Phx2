"""Stage 24.4 router / global-fee candidate scaffold.

This module is the Stage 24.4 router-fee detector. It is a
**candidate-only** scaffold: it recognizes active and deprecated
Axiom router program IDs, classifies a transaction's
``route_family``, surfaces wrapped-swap and inner-call evidence
as numeric features, but NEVER emits a decoded router/global
fee amount. Confirmed router/global-fee decoding lands at
Stage 24.5, and only if sanitized real or synthetic fixtures
prove the layout.

Scope (Stage 24.4):

  * Detect active Axiom router program IDs in
    ``execution_input.top_level_instructions``.
  * Detect deprecated Axiom router program IDs.
  * Detect inner System Program transfer candidates.
  * Detect inner Token Program transfer candidates.
  * Detect top-level System Program transfers that appear after
    a router instruction (the wrapped-swap fee-line shape).
  * Classify a wrapped-swap candidate (active router + an inner
    transfer-shaped instruction).
  * Emit a ``Stage24RouterFeeResult`` carrying:

        - the recognized ``route_family``,
        - a candidate ``fee_source``
          (``AXIOM_GLOBAL_FEE_CANDIDATE`` or
          ``ROUTER_FEE_CANDIDATE``),
        - a ``decoder_status`` in
          ``{DECODE_UNCONFIRMED, UNSUPPORTED, ABSENT}``,
        - ``amount_lamports = None`` always,
        - per-case reason codes in a deterministic canonical
          order,
        - candidate-only numeric features explicitly named
          ``*_candidate_*`` so downstream readers see them as
          research evidence, not decoded measurements.

Out of scope:

  * Decoded router/global-fee amount extraction (Stage 24.5).
  * Wrapped-swap inner-call layout decoding.
  * Calibration / enforcement candidate selection.
  * Runner / artifact writer / public-channel dispatch.
  * Network / RPC calls. Stage 24 is observe-only.

Honesty rules (mirrors Stage 24 brainstorm doc Section 8):

  * No active or deprecated router program ID:

        decoder_status = ABSENT, data_status = MISSING,
        route_family = NO_ROUTER_DETECTED,
        fee_source = UNKNOWN, amount_lamports = None.

  * Deprecated Axiom router program ID only:

        decoder_status = UNSUPPORTED, data_status = UNSUPPORTED,
        route_family = DEPRECATED_AXIOM,
        fee_source = ROUTER_FEE_CANDIDATE,
        amount_lamports = None.

  * Active Axiom router program ID (single):

        decoder_status = DECODE_UNCONFIRMED, data_status = PARTIAL,
        route_family = AXIOM_TRADING_PROGRAM_1 or AXIOM_FLASHX8,
        fee_source = AXIOM_GLOBAL_FEE_CANDIDATE,
        amount_lamports = None.

  * Multiple active routers in one transaction:

        decoder_status = DECODE_UNCONFIRMED, data_status = PARTIAL,
        route_family = first observed active program,
        fee_source = AXIOM_GLOBAL_FEE_CANDIDATE,
        amount_lamports = None,
        plus MULTIPLE_ROUTER_INSTRUCTIONS_DETECTED reason.

  * Wrapped-swap evidence (active router + inner transfer-shaped
    instruction): WRAPPED_SWAP_CANDIDATE_DETECTED reason added
    and a ``wrapped_swap_candidate`` boolean placed in numeric
    features.

This module imports only stdlib (``types`` / ``typing``) plus
the Stage 24 constants and models. It does NOT import Stage 21
/ Stage 22 / Stage 23 modules; it does NOT import any network /
RPC / messaging / DB / scheduler / secrets-management library;
it does NOT read the process environment; it does NOT define a
CLI surface; and it contains no top-level I/O.
"""

from __future__ import annotations

from types import MappingProxyType
from typing import Mapping

from PHX2.stage24.constants import (
    ACTIVE_AXIOM_ROUTER_PROGRAM_IDS,
    CONFIDENCE_LEVEL_LOW,
    CONFIDENCE_LEVEL_NONE,
    DATA_STATUS_MISSING,
    DATA_STATUS_PARTIAL,
    DATA_STATUS_UNSUPPORTED,
    DECODER_STATUS_ABSENT,
    DECODER_STATUS_DECODE_UNCONFIRMED,
    DECODER_STATUS_UNSUPPORTED,
    DEFAULT_THRESHOLD_VERSION,
    DEPRECATED_AXIOM_ROUTER_PROGRAM_IDS,
    FEE_SOURCE_AXIOM_GLOBAL_FEE_CANDIDATE,
    FEE_SOURCE_ROUTER_FEE_CANDIDATE,
    FEE_SOURCE_UNKNOWN,
    INSTRUCTION_LOCATION_TOP_LEVEL,
    INSTRUCTION_LOCATION_UNKNOWN,
    ROUTE_FAMILY_AXIOM_FLASHX8,
    ROUTE_FAMILY_AXIOM_TRADING_PROGRAM_1,
    ROUTE_FAMILY_DEPRECATED_AXIOM,
    ROUTE_FAMILY_NO_ROUTER_DETECTED,
    SYSTEM_PROGRAM_ID,
    TOKEN_PROGRAM_ID,
)
from PHX2.stage24.models import (
    Stage24ExecutionInput,
    Stage24RouterFeeResult,
    build_router_fee_result,
)


# ---------------------------------------------------------------------------
# Decoder identity
# ---------------------------------------------------------------------------


ROUTER_FEE_DECODER_NAME: str = "router_fee_candidate_v0"
ROUTER_FEE_DECODER_VERSION: str = "stage24_v0_router_fee_candidate"


# ---------------------------------------------------------------------------
# Program-id -> route-family mapping
# ---------------------------------------------------------------------------
#
# Bound by position to the ACTIVE_AXIOM_ROUTER_PROGRAM_IDS tuple
# in PHX2/stage24/constants.py. The constants closed-set test
# pins the tuple ordering (index 0 = Trading Program 1, index 1
# = FLASHX8), so building the mapping by index is stable and
# does not duplicate the literal pubkey strings.


_AXIOM_TRADING_PROGRAM_1_ID: str = ACTIVE_AXIOM_ROUTER_PROGRAM_IDS[0]
_AXIOM_FLASHX8_PROGRAM_ID: str = ACTIVE_AXIOM_ROUTER_PROGRAM_IDS[1]


_PROGRAM_ID_TO_ROUTE_FAMILY: Mapping[str, str] = MappingProxyType(
    {
        _AXIOM_TRADING_PROGRAM_1_ID: ROUTE_FAMILY_AXIOM_TRADING_PROGRAM_1,
        _AXIOM_FLASHX8_PROGRAM_ID: ROUTE_FAMILY_AXIOM_FLASHX8,
    }
)


# ---------------------------------------------------------------------------
# Reason codes
# ---------------------------------------------------------------------------


REASON_ROUTER_FEE_NO_ROUTER_DETECTED: str = (
    "ROUTER_FEE_NO_ROUTER_DETECTED"
)
REASON_AXIOM_TRADING_PROGRAM_1_DETECTED: str = (
    "AXIOM_TRADING_PROGRAM_1_DETECTED"
)
REASON_AXIOM_FLASHX8_DETECTED: str = "AXIOM_FLASHX8_DETECTED"
REASON_DEPRECATED_AXIOM_ROUTER_DETECTED: str = (
    "DEPRECATED_AXIOM_ROUTER_DETECTED"
)
REASON_MULTIPLE_ROUTER_INSTRUCTIONS_DETECTED: str = (
    "MULTIPLE_ROUTER_INSTRUCTIONS_DETECTED"
)
REASON_ROUTER_FEE_CANDIDATE_ONLY: str = "ROUTER_FEE_CANDIDATE_ONLY"
REASON_ROUTER_FEE_DECODE_UNCONFIRMED: str = (
    "ROUTER_FEE_DECODE_UNCONFIRMED"
)
REASON_WRAPPED_SWAP_CANDIDATE_DETECTED: str = (
    "WRAPPED_SWAP_CANDIDATE_DETECTED"
)
REASON_INNER_SYSTEM_TRANSFER_CANDIDATE_PRESENT: str = (
    "INNER_SYSTEM_TRANSFER_CANDIDATE_PRESENT"
)
REASON_INNER_TOKEN_TRANSFER_CANDIDATE_PRESENT: str = (
    "INNER_TOKEN_TRANSFER_CANDIDATE_PRESENT"
)
REASON_TOP_LEVEL_SYSTEM_TRANSFER_AFTER_ROUTER_PRESENT: str = (
    "TOP_LEVEL_SYSTEM_TRANSFER_AFTER_ROUTER_PRESENT"
)
REASON_ROUTER_FEE_AMOUNT_NOT_DECODED_IN_24_4: str = (
    "ROUTER_FEE_AMOUNT_NOT_DECODED_IN_24_4"
)


# Canonical reason ordering for deterministic emission. Reasons
# present in this tuple are emitted in this order; any reason not
# listed here trails the canonical block sorted alphabetically.
_REASON_ORDER: tuple[str, ...] = (
    REASON_ROUTER_FEE_NO_ROUTER_DETECTED,
    REASON_DEPRECATED_AXIOM_ROUTER_DETECTED,
    REASON_AXIOM_TRADING_PROGRAM_1_DETECTED,
    REASON_AXIOM_FLASHX8_DETECTED,
    REASON_MULTIPLE_ROUTER_INSTRUCTIONS_DETECTED,
    REASON_WRAPPED_SWAP_CANDIDATE_DETECTED,
    REASON_INNER_SYSTEM_TRANSFER_CANDIDATE_PRESENT,
    REASON_INNER_TOKEN_TRANSFER_CANDIDATE_PRESENT,
    REASON_TOP_LEVEL_SYSTEM_TRANSFER_AFTER_ROUTER_PRESENT,
    REASON_ROUTER_FEE_CANDIDATE_ONLY,
    REASON_ROUTER_FEE_DECODE_UNCONFIRMED,
    REASON_ROUTER_FEE_AMOUNT_NOT_DECODED_IN_24_4,
)


def _order_reasons(reasons: list[str]) -> tuple[str, ...]:
    """Deterministically order reason codes per ``_REASON_ORDER``."""
    seen = {r for r in reasons}
    canonical = [r for r in _REASON_ORDER if r in seen]
    extras = sorted(r for r in seen if r not in _REASON_ORDER)
    return tuple(canonical + extras)


# ---------------------------------------------------------------------------
# Per-instruction inspection helpers
# ---------------------------------------------------------------------------


def _program_id_of(instr: object) -> str:
    """Return the ``program_id`` string of an instruction record, or ``""``."""
    if not isinstance(instr, Mapping):
        return ""
    pid = instr.get("program_id")
    if not isinstance(pid, str):
        return ""
    return pid


def _classify_router_program(program_id: str) -> str:
    """Return ``"active"`` / ``"deprecated"`` / ``""`` for a program id.

    Only Axiom program IDs map to ``"active"`` or ``"deprecated"``.
    Any other program ID returns the empty string.
    """
    if program_id in ACTIVE_AXIOM_ROUTER_PROGRAM_IDS:
        return "active"
    if program_id in DEPRECATED_AXIOM_ROUTER_PROGRAM_IDS:
        return "deprecated"
    return ""


# ---------------------------------------------------------------------------
# Public decoder
# ---------------------------------------------------------------------------


def decode_router_fee_candidate(
    execution_input: Stage24ExecutionInput,
) -> Stage24RouterFeeResult:
    """Detect router-fee candidates in one transaction.

    Pure function: depends only on ``execution_input``. Returns a
    ``Stage24RouterFeeResult`` with ``amount_lamports = None``,
    ``amount_token = None``, and a ``decoder_status`` other than
    ``DECODED``. Stage 24.4 surfaces evidence; it does not
    confirm a router/global fee.
    """
    top_instructions = execution_input.top_level_instructions
    inner_instructions = execution_input.inner_instructions

    active_router_hits: list[tuple[int, str]] = []
    deprecated_router_hits: list[tuple[int, str]] = []
    for idx, instr in enumerate(top_instructions):
        pid = _program_id_of(instr)
        kind = _classify_router_program(pid)
        if kind == "active":
            active_router_hits.append((idx, pid))
        elif kind == "deprecated":
            deprecated_router_hits.append((idx, pid))

    inner_system_transfer_candidate_count = sum(
        1
        for instr in inner_instructions
        if _program_id_of(instr) == SYSTEM_PROGRAM_ID
    )
    inner_token_transfer_candidate_count = sum(
        1
        for instr in inner_instructions
        if _program_id_of(instr) == TOKEN_PROGRAM_ID
    )

    first_active_router_index = (
        active_router_hits[0][0] if active_router_hits else None
    )
    top_level_system_transfer_after_router_count = 0
    if first_active_router_index is not None:
        for idx, instr in enumerate(top_instructions):
            if idx <= first_active_router_index:
                continue
            if _program_id_of(instr) == SYSTEM_PROGRAM_ID:
                top_level_system_transfer_after_router_count += 1

    wrapped_swap_candidate = bool(active_router_hits) and (
        inner_system_transfer_candidate_count > 0
        or inner_token_transfer_candidate_count > 0
    )

    if not active_router_hits and not deprecated_router_hits:
        return _build_no_router_result(
            execution_input=execution_input,
            inner_instruction_count=len(inner_instructions),
            inner_system_transfer_candidate_count=(
                inner_system_transfer_candidate_count
            ),
            inner_token_transfer_candidate_count=(
                inner_token_transfer_candidate_count
            ),
        )

    if active_router_hits:
        return _build_active_router_candidate_result(
            execution_input=execution_input,
            active_router_hits=active_router_hits,
            deprecated_router_hits=deprecated_router_hits,
            inner_instruction_count=len(inner_instructions),
            inner_system_transfer_candidate_count=(
                inner_system_transfer_candidate_count
            ),
            inner_token_transfer_candidate_count=(
                inner_token_transfer_candidate_count
            ),
            top_level_system_transfer_after_router_count=(
                top_level_system_transfer_after_router_count
            ),
            wrapped_swap_candidate=wrapped_swap_candidate,
        )

    return _build_deprecated_router_result(
        execution_input=execution_input,
        deprecated_router_hits=deprecated_router_hits,
        inner_instruction_count=len(inner_instructions),
        inner_system_transfer_candidate_count=(
            inner_system_transfer_candidate_count
        ),
        inner_token_transfer_candidate_count=(
            inner_token_transfer_candidate_count
        ),
    )


# ---------------------------------------------------------------------------
# Numeric-feature / evidence builders
# ---------------------------------------------------------------------------


def _build_base_numeric_features(
    *,
    active_router_hits: list[tuple[int, str]],
    deprecated_router_hits: list[tuple[int, str]],
    inner_instruction_count: int,
    inner_system_transfer_candidate_count: int,
    inner_token_transfer_candidate_count: int,
    top_level_system_transfer_after_router_count: int,
    wrapped_swap_candidate: bool,
) -> dict[str, object]:
    router_fee_candidate_count = (
        len(active_router_hits) + len(deprecated_router_hits)
    )
    if active_router_hits:
        router_instruction_index: int | None = active_router_hits[0][0]
    elif deprecated_router_hits:
        router_instruction_index = deprecated_router_hits[0][0]
    else:
        router_instruction_index = None
    return {
        "top_level_router_present": bool(active_router_hits),
        "deprecated_router_present": bool(deprecated_router_hits),
        "router_instruction_index": router_instruction_index,
        "active_router_instruction_count": len(active_router_hits),
        "deprecated_router_instruction_count": len(deprecated_router_hits),
        "inner_instruction_count": inner_instruction_count,
        "inner_system_transfer_candidate_count": (
            inner_system_transfer_candidate_count
        ),
        "inner_token_transfer_candidate_count": (
            inner_token_transfer_candidate_count
        ),
        "top_level_system_transfer_after_router_candidate_count": (
            top_level_system_transfer_after_router_count
        ),
        "wrapped_swap_candidate": wrapped_swap_candidate,
        "router_fee_candidate_count": router_fee_candidate_count,
    }


def _build_base_evidence(
    *,
    active_router_hits: list[tuple[int, str]],
    deprecated_router_hits: list[tuple[int, str]],
) -> dict[str, object]:
    active_program_ids_seen = sorted(
        {pid for _, pid in active_router_hits}
    )
    deprecated_program_ids_seen = sorted(
        {pid for _, pid in deprecated_router_hits}
    )
    active_router_instruction_indexes = sorted(
        idx for idx, _ in active_router_hits
    )
    deprecated_router_instruction_indexes = sorted(
        idx for idx, _ in deprecated_router_hits
    )
    return {
        "active_router_program_ids_seen": active_program_ids_seen,
        "deprecated_router_program_ids_seen": (
            deprecated_program_ids_seen
        ),
        "active_router_instruction_indexes": (
            active_router_instruction_indexes
        ),
        "deprecated_router_instruction_indexes": (
            deprecated_router_instruction_indexes
        ),
    }


# ---------------------------------------------------------------------------
# Result builders
# ---------------------------------------------------------------------------


def _build_no_router_result(
    *,
    execution_input: Stage24ExecutionInput,
    inner_instruction_count: int,
    inner_system_transfer_candidate_count: int,
    inner_token_transfer_candidate_count: int,
) -> Stage24RouterFeeResult:
    reasons: list[str] = [
        REASON_ROUTER_FEE_NO_ROUTER_DETECTED,
        REASON_ROUTER_FEE_AMOUNT_NOT_DECODED_IN_24_4,
    ]
    numeric_features = _build_base_numeric_features(
        active_router_hits=[],
        deprecated_router_hits=[],
        inner_instruction_count=inner_instruction_count,
        inner_system_transfer_candidate_count=(
            inner_system_transfer_candidate_count
        ),
        inner_token_transfer_candidate_count=(
            inner_token_transfer_candidate_count
        ),
        top_level_system_transfer_after_router_count=0,
        wrapped_swap_candidate=False,
    )
    evidence = _build_base_evidence(
        active_router_hits=[],
        deprecated_router_hits=[],
    )
    return build_router_fee_result(
        decoder_name=ROUTER_FEE_DECODER_NAME,
        decoder_version=ROUTER_FEE_DECODER_VERSION,
        threshold_version=DEFAULT_THRESHOLD_VERSION,
        decoder_status=DECODER_STATUS_ABSENT,
        data_status=DATA_STATUS_MISSING,
        confidence_level=CONFIDENCE_LEVEL_NONE,
        fee_source=FEE_SOURCE_UNKNOWN,
        route_family=ROUTE_FAMILY_NO_ROUTER_DETECTED,
        instruction_location=INSTRUCTION_LOCATION_UNKNOWN,
        program_id="",
        amount_lamports=None,
        amount_token=None,
        mint="",
        reason_codes=_order_reasons(reasons),
        numeric_features=MappingProxyType(numeric_features),
        evidence=MappingProxyType(evidence),
        input_missing_fields=execution_input.missing_fields,
    )


def _build_deprecated_router_result(
    *,
    execution_input: Stage24ExecutionInput,
    deprecated_router_hits: list[tuple[int, str]],
    inner_instruction_count: int,
    inner_system_transfer_candidate_count: int,
    inner_token_transfer_candidate_count: int,
) -> Stage24RouterFeeResult:
    reasons: list[str] = [
        REASON_DEPRECATED_AXIOM_ROUTER_DETECTED,
        REASON_ROUTER_FEE_CANDIDATE_ONLY,
        REASON_ROUTER_FEE_AMOUNT_NOT_DECODED_IN_24_4,
    ]
    if inner_system_transfer_candidate_count > 0:
        reasons.append(REASON_INNER_SYSTEM_TRANSFER_CANDIDATE_PRESENT)
    if inner_token_transfer_candidate_count > 0:
        reasons.append(REASON_INNER_TOKEN_TRANSFER_CANDIDATE_PRESENT)
    if len(deprecated_router_hits) >= 2:
        reasons.append(REASON_MULTIPLE_ROUTER_INSTRUCTIONS_DETECTED)
    numeric_features = _build_base_numeric_features(
        active_router_hits=[],
        deprecated_router_hits=deprecated_router_hits,
        inner_instruction_count=inner_instruction_count,
        inner_system_transfer_candidate_count=(
            inner_system_transfer_candidate_count
        ),
        inner_token_transfer_candidate_count=(
            inner_token_transfer_candidate_count
        ),
        top_level_system_transfer_after_router_count=0,
        wrapped_swap_candidate=False,
    )
    evidence = _build_base_evidence(
        active_router_hits=[],
        deprecated_router_hits=deprecated_router_hits,
    )
    deprecated_first_idx, deprecated_first_pid = deprecated_router_hits[0]
    evidence["router_program_id"] = deprecated_first_pid
    evidence["router_instruction_index"] = deprecated_first_idx
    return build_router_fee_result(
        decoder_name=ROUTER_FEE_DECODER_NAME,
        decoder_version=ROUTER_FEE_DECODER_VERSION,
        threshold_version=DEFAULT_THRESHOLD_VERSION,
        decoder_status=DECODER_STATUS_UNSUPPORTED,
        data_status=DATA_STATUS_UNSUPPORTED,
        confidence_level=CONFIDENCE_LEVEL_NONE,
        fee_source=FEE_SOURCE_ROUTER_FEE_CANDIDATE,
        route_family=ROUTE_FAMILY_DEPRECATED_AXIOM,
        instruction_location=INSTRUCTION_LOCATION_TOP_LEVEL,
        program_id=deprecated_first_pid,
        amount_lamports=None,
        amount_token=None,
        mint="",
        reason_codes=_order_reasons(reasons),
        numeric_features=MappingProxyType(numeric_features),
        evidence=MappingProxyType(evidence),
        input_missing_fields=execution_input.missing_fields,
    )


def _build_active_router_candidate_result(
    *,
    execution_input: Stage24ExecutionInput,
    active_router_hits: list[tuple[int, str]],
    deprecated_router_hits: list[tuple[int, str]],
    inner_instruction_count: int,
    inner_system_transfer_candidate_count: int,
    inner_token_transfer_candidate_count: int,
    top_level_system_transfer_after_router_count: int,
    wrapped_swap_candidate: bool,
) -> Stage24RouterFeeResult:
    first_active_idx, first_active_pid = active_router_hits[0]
    primary_route_family = _PROGRAM_ID_TO_ROUTE_FAMILY[first_active_pid]

    reasons: list[str] = [REASON_ROUTER_FEE_DECODE_UNCONFIRMED]
    seen_families: set[str] = set()
    for _, pid in active_router_hits:
        family = _PROGRAM_ID_TO_ROUTE_FAMILY[pid]
        if family in seen_families:
            continue
        seen_families.add(family)
        if family == ROUTE_FAMILY_AXIOM_TRADING_PROGRAM_1:
            reasons.append(REASON_AXIOM_TRADING_PROGRAM_1_DETECTED)
        elif family == ROUTE_FAMILY_AXIOM_FLASHX8:
            reasons.append(REASON_AXIOM_FLASHX8_DETECTED)
    if deprecated_router_hits:
        reasons.append(REASON_DEPRECATED_AXIOM_ROUTER_DETECTED)
    if len(active_router_hits) >= 2:
        reasons.append(REASON_MULTIPLE_ROUTER_INSTRUCTIONS_DETECTED)
    if wrapped_swap_candidate:
        reasons.append(REASON_WRAPPED_SWAP_CANDIDATE_DETECTED)
    if inner_system_transfer_candidate_count > 0:
        reasons.append(REASON_INNER_SYSTEM_TRANSFER_CANDIDATE_PRESENT)
    if inner_token_transfer_candidate_count > 0:
        reasons.append(REASON_INNER_TOKEN_TRANSFER_CANDIDATE_PRESENT)
    if top_level_system_transfer_after_router_count > 0:
        reasons.append(
            REASON_TOP_LEVEL_SYSTEM_TRANSFER_AFTER_ROUTER_PRESENT
        )
    reasons.append(REASON_ROUTER_FEE_CANDIDATE_ONLY)
    reasons.append(REASON_ROUTER_FEE_AMOUNT_NOT_DECODED_IN_24_4)

    numeric_features = _build_base_numeric_features(
        active_router_hits=active_router_hits,
        deprecated_router_hits=deprecated_router_hits,
        inner_instruction_count=inner_instruction_count,
        inner_system_transfer_candidate_count=(
            inner_system_transfer_candidate_count
        ),
        inner_token_transfer_candidate_count=(
            inner_token_transfer_candidate_count
        ),
        top_level_system_transfer_after_router_count=(
            top_level_system_transfer_after_router_count
        ),
        wrapped_swap_candidate=wrapped_swap_candidate,
    )
    numeric_features["router_instruction_index"] = first_active_idx

    evidence = _build_base_evidence(
        active_router_hits=active_router_hits,
        deprecated_router_hits=deprecated_router_hits,
    )
    evidence["primary_route_family"] = primary_route_family
    evidence["router_program_id"] = first_active_pid
    evidence["router_instruction_index"] = first_active_idx

    return build_router_fee_result(
        decoder_name=ROUTER_FEE_DECODER_NAME,
        decoder_version=ROUTER_FEE_DECODER_VERSION,
        threshold_version=DEFAULT_THRESHOLD_VERSION,
        decoder_status=DECODER_STATUS_DECODE_UNCONFIRMED,
        data_status=DATA_STATUS_PARTIAL,
        confidence_level=CONFIDENCE_LEVEL_LOW,
        fee_source=FEE_SOURCE_AXIOM_GLOBAL_FEE_CANDIDATE,
        route_family=primary_route_family,
        instruction_location=INSTRUCTION_LOCATION_TOP_LEVEL,
        program_id=first_active_pid,
        amount_lamports=None,
        amount_token=None,
        mint="",
        reason_codes=_order_reasons(reasons),
        numeric_features=MappingProxyType(numeric_features),
        evidence=MappingProxyType(evidence),
        input_missing_fields=execution_input.missing_fields,
    )


__all__ = [
    "REASON_AXIOM_FLASHX8_DETECTED",
    "REASON_AXIOM_TRADING_PROGRAM_1_DETECTED",
    "REASON_DEPRECATED_AXIOM_ROUTER_DETECTED",
    "REASON_INNER_SYSTEM_TRANSFER_CANDIDATE_PRESENT",
    "REASON_INNER_TOKEN_TRANSFER_CANDIDATE_PRESENT",
    "REASON_MULTIPLE_ROUTER_INSTRUCTIONS_DETECTED",
    "REASON_ROUTER_FEE_AMOUNT_NOT_DECODED_IN_24_4",
    "REASON_ROUTER_FEE_CANDIDATE_ONLY",
    "REASON_ROUTER_FEE_DECODE_UNCONFIRMED",
    "REASON_ROUTER_FEE_NO_ROUTER_DETECTED",
    "REASON_TOP_LEVEL_SYSTEM_TRANSFER_AFTER_ROUTER_PRESENT",
    "REASON_WRAPPED_SWAP_CANDIDATE_DETECTED",
    "ROUTER_FEE_DECODER_NAME",
    "ROUTER_FEE_DECODER_VERSION",
    "decode_router_fee_candidate",
]

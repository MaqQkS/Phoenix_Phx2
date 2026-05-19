"""Stage 24.2 ComputeBudget program instruction decoder.

This module decodes top-level ComputeBudget program instructions
present in a Stage 24-shaped transaction observation
(``Stage24ExecutionInput``). It is the first real Stage 24
decoder; Stage 24.1 shipped the contracts, constants, and model
records this module operates on.

Scope:

  * Reads ``execution_input.top_level_instructions`` and matches
    on ``program_id == COMPUTE_BUDGET_PROGRAM_ID``.
  * Recognizes the four canonical ComputeBudget instruction
    tags:

        tag 0 - ``RequestUnitsDeprecated`` (legacy)
        tag 1 - ``RequestHeapFrame``
        tag 2 - ``SetComputeUnitLimit``
        tag 3 - ``SetComputeUnitPrice``

  * Returns a ``Stage24ComputeBudgetResult`` carrying the decoded
    unit limit / unit price (micro-lamports per CU) when they
    were observed, plus per-tag evidence and counts.

Out of scope:

  * Inner CPI ComputeBudget instructions. The decoder records
    that they were present in evidence and reason codes but does
    NOT decode their data (Stage 24's compute-budget contract is
    top-level only, matching how the Solana runtime treats
    ComputeBudget directives).
  * Jito tip / router / global-fee decoders. Those land in later
    Stage 24 sub-stages.

Encoding convention:

  * Instruction ``data`` is treated as a base64-encoded string.
    The first byte of the decoded bytes is the ComputeBudget
    tag; subsequent bytes are the little-endian u32 / u64 fields
    documented in the public Solana ComputeBudget program
    reference. Stage 24.2 commits to base64 as the canonical
    Stage 24 instruction-data encoding; the decoder does not
    fall back to other encodings.

Honesty rules (mirrors Stage 24 brainstorm doc Section 14):

  * No ComputeBudget instruction at all:

        decoder_status = ABSENT, data_status = MISSING.

  * One or more ComputeBudget instructions, but at least one
    unknown tag or malformed data:

        decoder_status = DECODE_FAILED, data_status = MALFORMED.

    No ``unit_limit`` / ``unit_price_microlamports`` is exposed
    even if some other instruction parsed successfully -- the
    overall observation is suspect.

  * Two or more ``SetComputeUnitPrice`` instructions:

        decoder_status = DECODE_UNCONFIRMED, data_status = PARTIAL.

    ``unit_price_microlamports`` is set to ``None`` because the
    price is ambiguous; every observed price is recorded in
    evidence.

  * Two or more ``SetComputeUnitLimit`` instructions:

        last-write-wins (matches Solana runtime semantics).

    Reason code
    ``MULTIPLE_COMPUTE_UNIT_LIMIT_INSTRUCTIONS_LAST_WRITE_WINS``
    is added so downstream callers can detect the rewrite.

  * Otherwise:

        decoder_status = DECODED.

This module imports only stdlib (``base64`` / ``binascii`` /
``types`` / ``typing``) plus the Stage 24 constants and models.
It does NOT import Stage 21 / Stage 22 / Stage 23 modules; it
does NOT import any network / RPC / messaging / DB / scheduler /
secrets-management library; it does NOT read the process
environment; it does NOT define a CLI surface; and it contains
no top-level I/O.
"""

from __future__ import annotations

import base64
import binascii
from types import MappingProxyType
from typing import Mapping

from PHX2.stage24.constants import (
    COMPUTE_BUDGET_PROGRAM_ID,
    CONFIDENCE_LEVEL_HIGH,
    CONFIDENCE_LEVEL_LOW,
    CONFIDENCE_LEVEL_NONE,
    DATA_STATUS_COMPLETE,
    DATA_STATUS_MALFORMED,
    DATA_STATUS_MISSING,
    DATA_STATUS_PARTIAL,
    DECODER_STATUS_ABSENT,
    DECODER_STATUS_DECODED,
    DECODER_STATUS_DECODE_FAILED,
    DECODER_STATUS_DECODE_UNCONFIRMED,
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
    build_compute_budget_result,
)


# ---------------------------------------------------------------------------
# Decoder identity
# ---------------------------------------------------------------------------


COMPUTE_BUDGET_DECODER_NAME: str = "compute_budget_v0"
COMPUTE_BUDGET_DECODER_VERSION: str = "stage24_v0_compute_budget"


# ---------------------------------------------------------------------------
# Instruction-data encoding
# ---------------------------------------------------------------------------
#
# Stage 24 reads decoded-tx JSONL with each instruction's data
# field encoded as a base64 string. Stage 24.2 locks base64 as
# the canonical Stage 24 instruction-data encoding; the boundary
# tests assert no decoder imports an external base58 / Solana
# SDK helper.


DATA_ENCODING_BASE64: str = "base64"


# ---------------------------------------------------------------------------
# ComputeBudget tag literals
# ---------------------------------------------------------------------------


TAG_REQUEST_UNITS_DEPRECATED: int = 0
TAG_REQUEST_HEAP_FRAME: int = 1
TAG_SET_COMPUTE_UNIT_LIMIT: int = 2
TAG_SET_COMPUTE_UNIT_PRICE: int = 3


# Locked tag -> short non-secret name. Recorded in evidence so
# downstream readers can interpret ``tags_seen`` without
# re-deriving the mapping.
TAG_NAME_BY_TAG: Mapping[int, str] = MappingProxyType(
    {
        TAG_REQUEST_UNITS_DEPRECATED: "REQUEST_UNITS_DEPRECATED",
        TAG_REQUEST_HEAP_FRAME: "REQUEST_HEAP_FRAME",
        TAG_SET_COMPUTE_UNIT_LIMIT: "SET_COMPUTE_UNIT_LIMIT",
        TAG_SET_COMPUTE_UNIT_PRICE: "SET_COMPUTE_UNIT_PRICE",
    }
)


# ---------------------------------------------------------------------------
# Reason codes (local to the ComputeBudget decoder)
# ---------------------------------------------------------------------------


REASON_COMPUTE_BUDGET_ABSENT: str = "COMPUTE_BUDGET_ABSENT"
REASON_COMPUTE_BUDGET_DECODED: str = "COMPUTE_BUDGET_DECODED"
REASON_COMPUTE_UNIT_LIMIT_DECODED: str = "COMPUTE_UNIT_LIMIT_DECODED"
REASON_COMPUTE_UNIT_PRICE_DECODED: str = "COMPUTE_UNIT_PRICE_DECODED"
REASON_COMPUTE_BUDGET_HEAP_FRAME_DECODED: str = (
    "COMPUTE_BUDGET_HEAP_FRAME_DECODED"
)
REASON_COMPUTE_BUDGET_LEGACY_REQUEST_UNITS_DEPRECATED: str = (
    "COMPUTE_BUDGET_LEGACY_REQUEST_UNITS_DEPRECATED"
)
REASON_COMPUTE_BUDGET_UNKNOWN_TAG: str = "COMPUTE_BUDGET_UNKNOWN_TAG"
REASON_COMPUTE_BUDGET_MALFORMED_DATA: str = (
    "COMPUTE_BUDGET_MALFORMED_DATA"
)
REASON_MULTIPLE_COMPUTE_UNIT_LIMIT_INSTRUCTIONS_LAST_WRITE_WINS: str = (
    "MULTIPLE_COMPUTE_UNIT_LIMIT_INSTRUCTIONS_LAST_WRITE_WINS"
)
REASON_MULTIPLE_COMPUTE_UNIT_PRICE_INSTRUCTIONS: str = (
    "MULTIPLE_COMPUTE_UNIT_PRICE_INSTRUCTIONS"
)
REASON_COMPUTE_BUDGET_INNER_INSTRUCTIONS_PRESENT: str = (
    "COMPUTE_BUDGET_INNER_INSTRUCTIONS_PRESENT"
)


# Internal parse-error tokens. Not exposed in the public API;
# only used to discriminate failure modes between the parser and
# the result builders.
_PARSE_ERROR_EMPTY_DATA: str = "empty_data"
_PARSE_ERROR_NON_STRING_DATA: str = "non_string_data"
_PARSE_ERROR_BASE64_DECODE_FAILED: str = "base64_decode_failed"
_PARSE_ERROR_UNKNOWN_TAG: str = "unknown_tag"
_PARSE_ERROR_MALFORMED_BODY_LENGTH: str = "malformed_body_length"


_MALFORMED_ERROR_KINDS: frozenset[str] = frozenset(
    {
        _PARSE_ERROR_EMPTY_DATA,
        _PARSE_ERROR_NON_STRING_DATA,
        _PARSE_ERROR_BASE64_DECODE_FAILED,
        _PARSE_ERROR_MALFORMED_BODY_LENGTH,
    }
)


# ---------------------------------------------------------------------------
# Private parse helpers
# ---------------------------------------------------------------------------


def _safe_b64_decode(data_str: str) -> bytes | None:
    """Return the bytes decoded from a base64 string, or ``None`` on failure.

    Uses ``base64.b64decode(..., validate=True)`` so non-base64
    characters (including the underscore in synthetic fixture
    placeholders) fail closed rather than silently truncating.
    """
    try:
        return base64.b64decode(data_str, validate=True)
    except (ValueError, binascii.Error):
        return None


def _parse_instruction_bytes(raw: bytes) -> dict[str, object]:
    """Parse a single ComputeBudget instruction's decoded bytes.

    Returns a dict carrying:

      * ``ok``     -- True on a successful parse; False otherwise.
      * ``tag``    -- the recognized tag (int) or None for the
                      empty-data case.
      * ``fields`` -- per-tag decoded fields when ``ok`` is True;
                      empty dict otherwise.
      * ``error``  -- a private parse-error token; empty string on
                      success.
    """
    if len(raw) == 0:
        return {
            "ok": False,
            "tag": None,
            "fields": {},
            "error": _PARSE_ERROR_EMPTY_DATA,
        }
    tag = raw[0]
    body = raw[1:]
    if tag == TAG_REQUEST_UNITS_DEPRECATED:
        if len(body) != 8:
            return {
                "ok": False,
                "tag": tag,
                "fields": {},
                "error": _PARSE_ERROR_MALFORMED_BODY_LENGTH,
            }
        return {
            "ok": True,
            "tag": tag,
            "fields": {
                "deprecated_requested_units": int.from_bytes(
                    body[0:4], "little"
                ),
                "deprecated_additional_fee_lamports": int.from_bytes(
                    body[4:8], "little"
                ),
            },
            "error": "",
        }
    if tag == TAG_REQUEST_HEAP_FRAME:
        if len(body) != 4:
            return {
                "ok": False,
                "tag": tag,
                "fields": {},
                "error": _PARSE_ERROR_MALFORMED_BODY_LENGTH,
            }
        return {
            "ok": True,
            "tag": tag,
            "fields": {
                "heap_frame_bytes": int.from_bytes(body[0:4], "little"),
            },
            "error": "",
        }
    if tag == TAG_SET_COMPUTE_UNIT_LIMIT:
        if len(body) != 4:
            return {
                "ok": False,
                "tag": tag,
                "fields": {},
                "error": _PARSE_ERROR_MALFORMED_BODY_LENGTH,
            }
        return {
            "ok": True,
            "tag": tag,
            "fields": {
                "compute_unit_limit": int.from_bytes(body[0:4], "little"),
            },
            "error": "",
        }
    if tag == TAG_SET_COMPUTE_UNIT_PRICE:
        if len(body) != 8:
            return {
                "ok": False,
                "tag": tag,
                "fields": {},
                "error": _PARSE_ERROR_MALFORMED_BODY_LENGTH,
            }
        return {
            "ok": True,
            "tag": tag,
            "fields": {
                "micro_lamports_per_compute_unit": int.from_bytes(
                    body[0:8], "little"
                ),
            },
            "error": "",
        }
    return {
        "ok": False,
        "tag": tag,
        "fields": {},
        "error": _PARSE_ERROR_UNKNOWN_TAG,
    }


def _is_compute_budget_instruction(instr: object) -> bool:
    if not isinstance(instr, Mapping):
        return False
    return instr.get("program_id") == COMPUTE_BUDGET_PROGRAM_ID


def _coerce_data_field(instr: Mapping[str, object]) -> object:
    return instr.get("data", "")


# ---------------------------------------------------------------------------
# Public decoder
# ---------------------------------------------------------------------------


def decode_compute_budget(
    execution_input: Stage24ExecutionInput,
) -> Stage24ComputeBudgetResult:
    """Decode the ComputeBudget program instructions for one transaction.

    Pure function: depends only on ``execution_input``. No side
    effects, no network, no env reads.
    """
    top_compute_budget_entries: list[tuple[int, Mapping[str, object]]] = []
    for index, instr in enumerate(execution_input.top_level_instructions):
        if _is_compute_budget_instruction(instr):
            top_compute_budget_entries.append((index, instr))

    inner_compute_budget_instruction_count = sum(
        1
        for instr in execution_input.inner_instructions
        if _is_compute_budget_instruction(instr)
    )

    if not top_compute_budget_entries:
        return _build_absent_result(
            execution_input=execution_input,
            inner_compute_budget_instruction_count=(
                inner_compute_budget_instruction_count
            ),
        )

    parsed_entries: list[dict[str, object]] = []
    for index, instr in top_compute_budget_entries:
        data_field = _coerce_data_field(instr)
        if not isinstance(data_field, str):
            parsed_entries.append(
                {
                    "idx": index,
                    "ok": False,
                    "tag": None,
                    "fields": {},
                    "error": _PARSE_ERROR_NON_STRING_DATA,
                }
            )
            continue
        raw_bytes = _safe_b64_decode(data_field)
        if raw_bytes is None:
            parsed_entries.append(
                {
                    "idx": index,
                    "ok": False,
                    "tag": None,
                    "fields": {},
                    "error": _PARSE_ERROR_BASE64_DECODE_FAILED,
                }
            )
            continue
        info = _parse_instruction_bytes(raw_bytes)
        info["idx"] = index
        parsed_entries.append(info)

    has_unknown_tag = any(
        not e["ok"] and e["error"] == _PARSE_ERROR_UNKNOWN_TAG
        for e in parsed_entries
    )
    has_malformed = any(
        not e["ok"] and e["error"] in _MALFORMED_ERROR_KINDS
        for e in parsed_entries
    )

    if has_unknown_tag or has_malformed:
        return _build_decode_failed_result(
            execution_input=execution_input,
            parsed_entries=parsed_entries,
            inner_compute_budget_instruction_count=(
                inner_compute_budget_instruction_count
            ),
            has_unknown_tag=has_unknown_tag,
            has_malformed=has_malformed,
        )

    return _build_decoded_result(
        execution_input=execution_input,
        parsed_entries=parsed_entries,
        inner_compute_budget_instruction_count=(
            inner_compute_budget_instruction_count
        ),
    )


# ---------------------------------------------------------------------------
# Result builders
# ---------------------------------------------------------------------------


def _build_absent_result(
    *,
    execution_input: Stage24ExecutionInput,
    inner_compute_budget_instruction_count: int,
) -> Stage24ComputeBudgetResult:
    reasons: list[str] = [REASON_COMPUTE_BUDGET_ABSENT]
    if inner_compute_budget_instruction_count > 0:
        reasons.append(REASON_COMPUTE_BUDGET_INNER_INSTRUCTIONS_PRESENT)
    numeric_features: dict[str, object] = {
        "compute_budget_instruction_count": 0,
        "compute_unit_limit_instruction_count": 0,
        "compute_unit_price_instruction_count": 0,
        "inner_compute_budget_instruction_count": (
            inner_compute_budget_instruction_count
        ),
    }
    evidence: dict[str, object] = {
        "top_level_instruction_indexes": [],
        "tags_seen": [],
        "tag_names_seen": [],
        "program_id": COMPUTE_BUDGET_PROGRAM_ID,
        "data_encoding": DATA_ENCODING_BASE64,
        "inner_compute_budget_instruction_count": (
            inner_compute_budget_instruction_count
        ),
    }
    return build_compute_budget_result(
        decoder_name=COMPUTE_BUDGET_DECODER_NAME,
        decoder_version=COMPUTE_BUDGET_DECODER_VERSION,
        threshold_version=DEFAULT_THRESHOLD_VERSION,
        decoder_status=DECODER_STATUS_ABSENT,
        data_status=DATA_STATUS_MISSING,
        confidence_level=CONFIDENCE_LEVEL_NONE,
        fee_source=FEE_SOURCE_UNKNOWN,
        route_family=ROUTE_FAMILY_NO_ROUTER_DETECTED,
        instruction_location=INSTRUCTION_LOCATION_UNKNOWN,
        program_id="",
        unit_limit=None,
        unit_price_microlamports=None,
        reason_codes=tuple(reasons),
        numeric_features=MappingProxyType(numeric_features),
        evidence=MappingProxyType(evidence),
        input_missing_fields=execution_input.missing_fields,
    )


def _build_decode_failed_result(
    *,
    execution_input: Stage24ExecutionInput,
    parsed_entries: list[dict[str, object]],
    inner_compute_budget_instruction_count: int,
    has_unknown_tag: bool,
    has_malformed: bool,
) -> Stage24ComputeBudgetResult:
    reasons: list[str] = []
    if has_unknown_tag:
        reasons.append(REASON_COMPUTE_BUDGET_UNKNOWN_TAG)
    if has_malformed:
        reasons.append(REASON_COMPUTE_BUDGET_MALFORMED_DATA)
    if inner_compute_budget_instruction_count > 0:
        reasons.append(REASON_COMPUTE_BUDGET_INNER_INSTRUCTIONS_PRESENT)

    successful_limit_entries = [
        e
        for e in parsed_entries
        if e["ok"] and e["tag"] == TAG_SET_COMPUTE_UNIT_LIMIT
    ]
    successful_price_entries = [
        e
        for e in parsed_entries
        if e["ok"] and e["tag"] == TAG_SET_COMPUTE_UNIT_PRICE
    ]
    malformed_count = sum(1 for e in parsed_entries if not e["ok"])

    tags_seen_set: set[int] = {
        e["tag"]
        for e in parsed_entries
        if isinstance(e["tag"], int)
    }
    tag_names_seen = sorted(
        TAG_NAME_BY_TAG[t]
        for t in tags_seen_set
        if t in TAG_NAME_BY_TAG
    )
    unknown_tags_seen = sorted(
        t for t in tags_seen_set if t not in TAG_NAME_BY_TAG
    )
    error_kinds_seen = sorted(
        {
            str(e["error"])
            for e in parsed_entries
            if not e["ok"] and isinstance(e.get("error"), str)
        }
    )

    numeric_features: dict[str, object] = {
        "compute_budget_instruction_count": len(parsed_entries),
        "compute_unit_limit_instruction_count": len(
            successful_limit_entries
        ),
        "compute_unit_price_instruction_count": len(
            successful_price_entries
        ),
        "inner_compute_budget_instruction_count": (
            inner_compute_budget_instruction_count
        ),
        "malformed_instruction_count": malformed_count,
    }
    evidence: dict[str, object] = {
        "top_level_instruction_indexes": [e["idx"] for e in parsed_entries],
        "tags_seen": sorted(tags_seen_set),
        "tag_names_seen": tag_names_seen,
        "unknown_tags_seen": unknown_tags_seen,
        "errors_seen": error_kinds_seen,
        "program_id": COMPUTE_BUDGET_PROGRAM_ID,
        "data_encoding": DATA_ENCODING_BASE64,
        "inner_compute_budget_instruction_count": (
            inner_compute_budget_instruction_count
        ),
    }
    return build_compute_budget_result(
        decoder_name=COMPUTE_BUDGET_DECODER_NAME,
        decoder_version=COMPUTE_BUDGET_DECODER_VERSION,
        threshold_version=DEFAULT_THRESHOLD_VERSION,
        decoder_status=DECODER_STATUS_DECODE_FAILED,
        data_status=DATA_STATUS_MALFORMED,
        confidence_level=CONFIDENCE_LEVEL_NONE,
        fee_source=FEE_SOURCE_UNKNOWN,
        route_family=ROUTE_FAMILY_NO_ROUTER_DETECTED,
        instruction_location=INSTRUCTION_LOCATION_TOP_LEVEL,
        program_id=COMPUTE_BUDGET_PROGRAM_ID,
        unit_limit=None,
        unit_price_microlamports=None,
        reason_codes=tuple(reasons),
        numeric_features=MappingProxyType(numeric_features),
        evidence=MappingProxyType(evidence),
        input_missing_fields=execution_input.missing_fields,
    )


def _build_decoded_result(
    *,
    execution_input: Stage24ExecutionInput,
    parsed_entries: list[dict[str, object]],
    inner_compute_budget_instruction_count: int,
) -> Stage24ComputeBudgetResult:
    limit_entries = [
        e for e in parsed_entries if e["tag"] == TAG_SET_COMPUTE_UNIT_LIMIT
    ]
    price_entries = [
        e for e in parsed_entries if e["tag"] == TAG_SET_COMPUTE_UNIT_PRICE
    ]
    heap_entries = [
        e for e in parsed_entries if e["tag"] == TAG_REQUEST_HEAP_FRAME
    ]
    deprecated_entries = [
        e
        for e in parsed_entries
        if e["tag"] == TAG_REQUEST_UNITS_DEPRECATED
    ]

    # Policy: last-write-wins for compute_unit_limit; ambiguity
    # surfaces as DECODE_UNCONFIRMED for compute_unit_price.
    chosen_limit: int | None
    if limit_entries:
        last_limit_fields = limit_entries[-1]["fields"]
        assert isinstance(last_limit_fields, Mapping)
        chosen_limit = int(last_limit_fields["compute_unit_limit"])
    else:
        chosen_limit = None

    chosen_price: int | None
    if len(price_entries) == 1:
        only_price_fields = price_entries[0]["fields"]
        assert isinstance(only_price_fields, Mapping)
        chosen_price = int(
            only_price_fields["micro_lamports_per_compute_unit"]
        )
    else:
        chosen_price = None

    if len(price_entries) >= 2:
        decoder_status = DECODER_STATUS_DECODE_UNCONFIRMED
        data_status = DATA_STATUS_PARTIAL
        confidence_level = CONFIDENCE_LEVEL_LOW
    else:
        decoder_status = DECODER_STATUS_DECODED
        data_status = DATA_STATUS_COMPLETE
        confidence_level = CONFIDENCE_LEVEL_HIGH

    fee_source = (
        FEE_SOURCE_PRIORITY_FEE if price_entries else FEE_SOURCE_UNKNOWN
    )

    reasons: list[str] = [REASON_COMPUTE_BUDGET_DECODED]
    if chosen_limit is not None:
        reasons.append(REASON_COMPUTE_UNIT_LIMIT_DECODED)
    if chosen_price is not None:
        reasons.append(REASON_COMPUTE_UNIT_PRICE_DECODED)
    if heap_entries:
        reasons.append(REASON_COMPUTE_BUDGET_HEAP_FRAME_DECODED)
    if deprecated_entries:
        reasons.append(
            REASON_COMPUTE_BUDGET_LEGACY_REQUEST_UNITS_DEPRECATED
        )
    if len(limit_entries) >= 2:
        reasons.append(
            REASON_MULTIPLE_COMPUTE_UNIT_LIMIT_INSTRUCTIONS_LAST_WRITE_WINS
        )
    if len(price_entries) >= 2:
        reasons.append(REASON_MULTIPLE_COMPUTE_UNIT_PRICE_INSTRUCTIONS)
    if inner_compute_budget_instruction_count > 0:
        reasons.append(REASON_COMPUTE_BUDGET_INNER_INSTRUCTIONS_PRESENT)

    tags_seen_set: set[int] = {
        e["tag"] for e in parsed_entries if isinstance(e["tag"], int)
    }
    tag_names_seen = sorted(
        TAG_NAME_BY_TAG[t]
        for t in tags_seen_set
        if t in TAG_NAME_BY_TAG
    )

    numeric_features: dict[str, object] = {
        "compute_budget_instruction_count": len(parsed_entries),
        "compute_unit_limit_instruction_count": len(limit_entries),
        "compute_unit_price_instruction_count": len(price_entries),
        "inner_compute_budget_instruction_count": (
            inner_compute_budget_instruction_count
        ),
    }
    if chosen_limit is not None:
        numeric_features["compute_unit_limit"] = chosen_limit
    if chosen_price is not None:
        numeric_features["micro_lamports_per_compute_unit"] = chosen_price
    if heap_entries:
        last_heap_fields = heap_entries[-1]["fields"]
        assert isinstance(last_heap_fields, Mapping)
        numeric_features["heap_frame_bytes"] = int(
            last_heap_fields["heap_frame_bytes"]
        )
    if deprecated_entries:
        last_dep_fields = deprecated_entries[-1]["fields"]
        assert isinstance(last_dep_fields, Mapping)
        numeric_features["deprecated_requested_units"] = int(
            last_dep_fields["deprecated_requested_units"]
        )
        numeric_features["deprecated_additional_fee_lamports"] = int(
            last_dep_fields["deprecated_additional_fee_lamports"]
        )

    evidence: dict[str, object] = {
        "top_level_instruction_indexes": [e["idx"] for e in parsed_entries],
        "tags_seen": sorted(tags_seen_set),
        "tag_names_seen": tag_names_seen,
        "program_id": COMPUTE_BUDGET_PROGRAM_ID,
        "data_encoding": DATA_ENCODING_BASE64,
        "inner_compute_budget_instruction_count": (
            inner_compute_budget_instruction_count
        ),
    }
    if len(limit_entries) >= 2:
        evidence["compute_unit_limit_values_observed"] = [
            int(_fields_of(e)["compute_unit_limit"]) for e in limit_entries
        ]
    if len(price_entries) >= 2:
        evidence["compute_unit_price_values_observed"] = [
            int(_fields_of(e)["micro_lamports_per_compute_unit"])
            for e in price_entries
        ]

    return build_compute_budget_result(
        decoder_name=COMPUTE_BUDGET_DECODER_NAME,
        decoder_version=COMPUTE_BUDGET_DECODER_VERSION,
        threshold_version=DEFAULT_THRESHOLD_VERSION,
        decoder_status=decoder_status,
        data_status=data_status,
        confidence_level=confidence_level,
        fee_source=fee_source,
        route_family=ROUTE_FAMILY_NO_ROUTER_DETECTED,
        instruction_location=INSTRUCTION_LOCATION_TOP_LEVEL,
        program_id=COMPUTE_BUDGET_PROGRAM_ID,
        unit_limit=chosen_limit,
        unit_price_microlamports=chosen_price,
        reason_codes=tuple(reasons),
        numeric_features=MappingProxyType(numeric_features),
        evidence=MappingProxyType(evidence),
        input_missing_fields=execution_input.missing_fields,
    )


def _fields_of(entry: dict[str, object]) -> Mapping[str, object]:
    """Type-narrowing accessor for the per-entry ``fields`` mapping."""
    fields = entry["fields"]
    assert isinstance(fields, Mapping)
    return fields


__all__ = [
    "COMPUTE_BUDGET_DECODER_NAME",
    "COMPUTE_BUDGET_DECODER_VERSION",
    "DATA_ENCODING_BASE64",
    "REASON_COMPUTE_BUDGET_ABSENT",
    "REASON_COMPUTE_BUDGET_DECODED",
    "REASON_COMPUTE_BUDGET_HEAP_FRAME_DECODED",
    "REASON_COMPUTE_BUDGET_INNER_INSTRUCTIONS_PRESENT",
    "REASON_COMPUTE_BUDGET_LEGACY_REQUEST_UNITS_DEPRECATED",
    "REASON_COMPUTE_BUDGET_MALFORMED_DATA",
    "REASON_COMPUTE_BUDGET_UNKNOWN_TAG",
    "REASON_COMPUTE_UNIT_LIMIT_DECODED",
    "REASON_COMPUTE_UNIT_PRICE_DECODED",
    "REASON_MULTIPLE_COMPUTE_UNIT_LIMIT_INSTRUCTIONS_LAST_WRITE_WINS",
    "REASON_MULTIPLE_COMPUTE_UNIT_PRICE_INSTRUCTIONS",
    "TAG_NAME_BY_TAG",
    "TAG_REQUEST_HEAP_FRAME",
    "TAG_REQUEST_UNITS_DEPRECATED",
    "TAG_SET_COMPUTE_UNIT_LIMIT",
    "TAG_SET_COMPUTE_UNIT_PRICE",
    "decode_compute_budget",
]

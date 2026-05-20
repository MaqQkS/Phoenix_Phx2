"""Stage 24.3 Jito-tip primitive decoder.

This module decodes per-transaction Jito tip evidence from a
Stage 24-shaped transaction observation
(``Stage24ExecutionInput``). It is the third real Stage 24
decoder; Stage 24.2 shipped the compute-budget / priority-fee
pair this module sits alongside.

Scope:

  * Reads ``execution_input.top_level_instructions`` and
    recognizes System Program ``Transfer`` instructions whose
    decoded destination account is a member of
    ``KNOWN_JITO_TIP_ACCOUNTS``.
  * Also walks ``execution_input.inner_instructions`` to surface
    inner-CPI tip candidates as evidence only (never as a
    confirmed decode).
  * Returns a ``Stage24JitoTipResult`` carrying the decoded tip
    amount (lamports), the destination tip account, the
    instruction index, and per-case reason codes.

Out of scope:

  * Router / global-fee decoding (Stage 24.4 / 24.5).
  * Execution-quality (Stage 24.6).
  * Network calls. No Jito client, no RPC, no websocket.
  * Solana SDK imports. Instruction bytes are decoded with
    stdlib ``base64`` + ``int.from_bytes`` only.

Encoding convention:

  * Instruction ``data`` is treated as a base64-encoded string.
    The first 4 bytes of the decoded bytes form a little-endian
    u32 System Program instruction tag; the Transfer tag is
    ``2``. The following 8 bytes are the u64 little-endian
    lamport amount. Total expected length: 12 bytes.
  * ``accounts`` on a Stage 24-shaped instruction record is a
    list whose entries are either base58 pubkey strings (used
    directly) or non-negative integer indexes into
    ``execution_input.account_keys`` (used to resolve a pubkey).
    Anything else makes the instruction's destination
    unresolvable for the tip decoder.

Honesty rules (mirrors Stage 24 brainstorm doc Section 14):

  * No System Program transfer to a known Jito tip account in
    the top-level instruction list:

        decoder_status = ABSENT, data_status = MISSING (or
        NOT_APPLICABLE when the input has no top-level
        instructions at all), amount_lamports = None.

  * Exactly one top-level System Program transfer to a known
    Jito tip account, with a well-formed Transfer body and a
    resolvable destination:

        decoder_status = DECODED, data_status = COMPLETE,
        confidence_level = HIGH, fee_source = JITO_TIP,
        amount_lamports = <decoded lamports>.

  * Two or more top-level System Program transfers to known
    Jito tip accounts:

        decoder_status = DECODE_UNCONFIRMED, data_status =
        PARTIAL, amount_lamports = None. The Stage 24 decoder
        does not silently sum tips; ambiguity is surfaced via a
        ``MULTIPLE_JITO_TIP_CANDIDATES`` reason and per-candidate
        evidence.

  * An inner-CPI System Program transfer to a known Jito tip
    account is surfaced as evidence (``JITO_TIP_INNER_CANDIDATE
    _PRESENT``). It never headline-decodes the Jito tip.

  * A System Program transfer to a non-tip destination is
    ignored for headline purposes; a single
    ``SYSTEM_TRANSFER_NON_TIP_IGNORED`` evidence reason is added
    when at least one such transfer is observed.

  * A System Program instruction whose decoded data shape is
    consistent with the Transfer layout (tag = 2) but whose body
    length is wrong fails closed as
    ``decoder_status=DECODE_FAILED`` / ``data_status=MALFORMED``
    with reason ``JITO_TIP_MALFORMED_TRANSFER``. Non-Transfer
    System Program instructions (e.g. CreateAccount, Assign) are
    ignored rather than failed closed.

  * If ``execution_input.transaction_status`` clearly indicates
    a failed transaction, the decoder refuses to claim a paid
    tip. Status falls back to ``NOT_APPLICABLE`` (no tip
    candidate observed) or ``PARTIAL`` (tip candidate observed
    but landing not guaranteed). ``amount_lamports`` is ``None``
    in both cases. Reason ``JITO_TIP_TX_FAILED`` is added.

  * If ``KNOWN_JITO_TIP_ACCOUNTS`` is empty (constants drift),
    the decoder fails closed with
    ``decoder_status=UNSUPPORTED`` / ``data_status=UNSUPPORTED``
    and reason ``JITO_TIP_ACCOUNTS_UNCONFIGURED``. No decoded
    amount is ever emitted in this case.

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
    CONFIDENCE_LEVEL_HIGH,
    CONFIDENCE_LEVEL_LOW,
    CONFIDENCE_LEVEL_NONE,
    DATA_STATUS_COMPLETE,
    DATA_STATUS_MALFORMED,
    DATA_STATUS_MISSING,
    DATA_STATUS_NOT_APPLICABLE,
    DATA_STATUS_PARTIAL,
    DATA_STATUS_UNSUPPORTED,
    DECODER_STATUS_ABSENT,
    DECODER_STATUS_DECODED,
    DECODER_STATUS_DECODE_FAILED,
    DECODER_STATUS_DECODE_UNCONFIRMED,
    DECODER_STATUS_NOT_APPLICABLE,
    DECODER_STATUS_PARTIAL,
    DECODER_STATUS_UNSUPPORTED,
    DEFAULT_THRESHOLD_VERSION,
    FEE_SOURCE_JITO_TIP,
    FEE_SOURCE_JITO_TIP_CANDIDATE,
    FEE_SOURCE_UNKNOWN,
    INSTRUCTION_LOCATION_INNER,
    INSTRUCTION_LOCATION_TOP_LEVEL,
    INSTRUCTION_LOCATION_UNKNOWN,
    KNOWN_JITO_TIP_ACCOUNTS,
    ROUTE_FAMILY_NO_ROUTER_DETECTED,
    SYSTEM_PROGRAM_ID,
)
from PHX2.stage24.models import (
    Stage24ExecutionInput,
    Stage24JitoTipResult,
    build_jito_tip_result,
)


# ---------------------------------------------------------------------------
# Decoder identity
# ---------------------------------------------------------------------------


JITO_TIP_DECODER_NAME: str = "jito_tip_v0"
JITO_TIP_DECODER_VERSION: str = "stage24_v0_jito_tip"


# ---------------------------------------------------------------------------
# Instruction-data encoding / layout literals
# ---------------------------------------------------------------------------


DATA_ENCODING_BASE64: str = "base64"


# System Program ``Transfer`` instruction discriminator (u32 little-
# endian) and expected body width.
SYSTEM_PROGRAM_TRANSFER_TAG: int = 2
SYSTEM_PROGRAM_TAG_BYTE_WIDTH: int = 4
SYSTEM_PROGRAM_TRANSFER_LAMPORTS_BYTE_WIDTH: int = 8
SYSTEM_PROGRAM_TRANSFER_TOTAL_BYTE_WIDTH: int = (
    SYSTEM_PROGRAM_TAG_BYTE_WIDTH
    + SYSTEM_PROGRAM_TRANSFER_LAMPORTS_BYTE_WIDTH
)


# Per the System Program Transfer layout, ``accounts[0]`` is the
# funding (source) account and ``accounts[1]`` is the recipient
# (destination) account.
SYSTEM_PROGRAM_TRANSFER_SOURCE_ACCOUNT_INDEX: int = 0
SYSTEM_PROGRAM_TRANSFER_DESTINATION_ACCOUNT_INDEX: int = 1


# Locked set of ``transaction_status`` values Stage 24 treats as a
# clearly-failed transaction. Comparison is case-insensitive.
_FAILED_TRANSACTION_STATUS_TOKENS: frozenset[str] = frozenset(
    {"err", "error", "failed", "failure"}
)


# ---------------------------------------------------------------------------
# Reason codes
# ---------------------------------------------------------------------------


REASON_JITO_TIP_ABSENT: str = "JITO_TIP_ABSENT"
REASON_JITO_TIP_DECODED: str = "JITO_TIP_DECODED"
REASON_JITO_TIP_INNER_CANDIDATE_PRESENT: str = (
    "JITO_TIP_INNER_CANDIDATE_PRESENT"
)
REASON_MULTIPLE_JITO_TIP_CANDIDATES: str = "MULTIPLE_JITO_TIP_CANDIDATES"
REASON_JITO_TIP_MALFORMED_TRANSFER: str = "JITO_TIP_MALFORMED_TRANSFER"
REASON_SYSTEM_TRANSFER_NON_TIP_IGNORED: str = (
    "SYSTEM_TRANSFER_NON_TIP_IGNORED"
)
REASON_JITO_TIP_TX_FAILED: str = "JITO_TIP_TX_FAILED"
REASON_JITO_TIP_ACCOUNTS_UNCONFIGURED: str = (
    "JITO_TIP_ACCOUNTS_UNCONFIGURED"
)
REASON_JITO_TIP_NO_TOP_LEVEL_INSTRUCTIONS: str = (
    "JITO_TIP_NO_TOP_LEVEL_INSTRUCTIONS"
)


# Internal parse-error tokens (mirrors the compute-budget decoder
# discipline). Not part of the public API.
_PARSE_ERROR_NON_MAPPING: str = "non_mapping_instruction"
_PARSE_ERROR_NON_STRING_DATA: str = "non_string_data"
_PARSE_ERROR_BASE64_DECODE_FAILED: str = "base64_decode_failed"
_PARSE_ERROR_EMPTY_DATA: str = "empty_data"
_PARSE_ERROR_DATA_TOO_SHORT_FOR_TAG: str = "data_too_short_for_tag"
_PARSE_ERROR_MALFORMED_TRANSFER_BODY: str = "malformed_transfer_body"
_PARSE_ERROR_NON_TRANSFER_TAG: str = "non_transfer_tag"
_PARSE_ERROR_UNRESOLVABLE_DESTINATION: str = "unresolvable_destination"


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _safe_b64_decode(data_str: str) -> bytes | None:
    """Return the bytes decoded from a base64 string, or ``None`` on failure."""
    try:
        return base64.b64decode(data_str, validate=True)
    except (ValueError, binascii.Error):
        return None


def _is_system_program_instruction(instr: object) -> bool:
    if not isinstance(instr, Mapping):
        return False
    return instr.get("program_id") == SYSTEM_PROGRAM_ID


def _resolve_destination_account(
    *,
    instr: Mapping[str, object],
    account_keys: tuple[str, ...],
) -> str | None:
    """Resolve the Transfer destination pubkey from instruction accounts.

    ``accounts`` may carry either base58 pubkey strings (used
    directly) or int indexes into ``account_keys``. Returns
    ``None`` when the destination cannot be resolved.
    """
    accounts_raw = instr.get("accounts")
    if not isinstance(accounts_raw, (list, tuple)):
        return None
    dest_idx = SYSTEM_PROGRAM_TRANSFER_DESTINATION_ACCOUNT_INDEX
    if len(accounts_raw) <= dest_idx:
        return None
    entry = accounts_raw[dest_idx]
    if isinstance(entry, bool):
        return None
    if isinstance(entry, int):
        if entry < 0 or entry >= len(account_keys):
            return None
        return account_keys[entry]
    if isinstance(entry, str) and entry != "":
        return entry
    return None


def _resolve_source_account(
    *,
    instr: Mapping[str, object],
    account_keys: tuple[str, ...],
) -> str | None:
    """Resolve the Transfer source pubkey from instruction accounts."""
    accounts_raw = instr.get("accounts")
    if not isinstance(accounts_raw, (list, tuple)):
        return None
    src_idx = SYSTEM_PROGRAM_TRANSFER_SOURCE_ACCOUNT_INDEX
    if len(accounts_raw) <= src_idx:
        return None
    entry = accounts_raw[src_idx]
    if isinstance(entry, bool):
        return None
    if isinstance(entry, int):
        if entry < 0 or entry >= len(account_keys):
            return None
        return account_keys[entry]
    if isinstance(entry, str) and entry != "":
        return entry
    return None


def _account_index(
    *,
    instr: Mapping[str, object],
    account_keys: tuple[str, ...],
    position: int,
) -> int | None:
    """Return the int index of the account at ``position`` in account_keys.

    If the entry is a string pubkey, returns the matching index in
    ``account_keys`` if present, else ``-1`` to indicate the pubkey
    was directly provided but not in the message account list.
    Returns ``None`` when no entry exists at that position.
    """
    accounts_raw = instr.get("accounts")
    if not isinstance(accounts_raw, (list, tuple)):
        return None
    if len(accounts_raw) <= position:
        return None
    entry = accounts_raw[position]
    if isinstance(entry, bool):
        return None
    if isinstance(entry, int):
        if entry < 0 or entry >= len(account_keys):
            return -1
        return entry
    if isinstance(entry, str) and entry != "":
        try:
            return account_keys.index(entry)
        except ValueError:
            return -1
    return None


def _parse_system_transfer_data(raw: bytes) -> dict[str, object]:
    """Parse a System Program instruction's decoded bytes.

    Returns a dict carrying:

      * ``ok``       -- True on a successful Transfer parse.
      * ``tag``      -- the recognized u32 tag, or ``None`` when
                        the data is too short to carry one.
      * ``lamports`` -- decoded lamport amount on a successful
                        Transfer parse.
      * ``error``    -- a private parse-error token; empty on
                        success.
    """
    if len(raw) == 0:
        return {
            "ok": False,
            "tag": None,
            "lamports": None,
            "error": _PARSE_ERROR_EMPTY_DATA,
        }
    if len(raw) < SYSTEM_PROGRAM_TAG_BYTE_WIDTH:
        return {
            "ok": False,
            "tag": None,
            "lamports": None,
            "error": _PARSE_ERROR_DATA_TOO_SHORT_FOR_TAG,
        }
    tag = int.from_bytes(raw[:SYSTEM_PROGRAM_TAG_BYTE_WIDTH], "little")
    body = raw[SYSTEM_PROGRAM_TAG_BYTE_WIDTH:]
    if tag != SYSTEM_PROGRAM_TRANSFER_TAG:
        return {
            "ok": False,
            "tag": tag,
            "lamports": None,
            "error": _PARSE_ERROR_NON_TRANSFER_TAG,
        }
    if len(body) != SYSTEM_PROGRAM_TRANSFER_LAMPORTS_BYTE_WIDTH:
        return {
            "ok": False,
            "tag": tag,
            "lamports": None,
            "error": _PARSE_ERROR_MALFORMED_TRANSFER_BODY,
        }
    lamports = int.from_bytes(body, "little")
    return {
        "ok": True,
        "tag": tag,
        "lamports": lamports,
        "error": "",
    }


def _transaction_clearly_failed(transaction_status: str) -> bool:
    if not isinstance(transaction_status, str):
        return False
    return transaction_status.strip().lower() in _FAILED_TRANSACTION_STATUS_TOKENS


# ---------------------------------------------------------------------------
# Per-instruction analysis
# ---------------------------------------------------------------------------


def _analyze_system_transfer_instruction(
    *,
    instr: Mapping[str, object],
    instruction_index: int,
    account_keys: tuple[str, ...],
) -> dict[str, object]:
    """Build a per-instruction analysis record.

    The record carries everything the result builder needs to
    decide DECODED / DECODE_UNCONFIRMED / DECODE_FAILED / ignore
    semantics without re-parsing the bytes.
    """
    base: dict[str, object] = {
        "instruction_index": instruction_index,
        "is_system_program": False,
        "is_transfer": False,
        "is_malformed_transfer_shape": False,
        "destination": None,
        "destination_account_index": None,
        "source": None,
        "source_account_index": None,
        "tip_destination_matched": False,
        "lamports": None,
        "tag": None,
        "parse_error": "",
    }
    if not isinstance(instr, Mapping):
        base["parse_error"] = _PARSE_ERROR_NON_MAPPING
        return base
    if instr.get("program_id") != SYSTEM_PROGRAM_ID:
        return base
    base["is_system_program"] = True

    data_field = instr.get("data", "")
    if not isinstance(data_field, str):
        base["parse_error"] = _PARSE_ERROR_NON_STRING_DATA
        return base
    raw_bytes = _safe_b64_decode(data_field)
    if raw_bytes is None:
        base["parse_error"] = _PARSE_ERROR_BASE64_DECODE_FAILED
        return base
    parsed = _parse_system_transfer_data(raw_bytes)
    base["tag"] = parsed["tag"]

    parsed_error = parsed["error"]
    parsed_tag = parsed["tag"]
    if not parsed["ok"]:
        # Distinguish "looks like a Transfer but malformed body"
        # from "not a Transfer instruction".
        if (
            parsed_tag == SYSTEM_PROGRAM_TRANSFER_TAG
            and parsed_error == _PARSE_ERROR_MALFORMED_TRANSFER_BODY
        ):
            base["is_malformed_transfer_shape"] = True
            base["parse_error"] = _PARSE_ERROR_MALFORMED_TRANSFER_BODY
            return base
        base["parse_error"] = (
            parsed_error
            if isinstance(parsed_error, str)
            else _PARSE_ERROR_NON_TRANSFER_TAG
        )
        return base

    base["is_transfer"] = True
    base["lamports"] = parsed["lamports"]
    destination = _resolve_destination_account(
        instr=instr, account_keys=account_keys
    )
    source = _resolve_source_account(
        instr=instr, account_keys=account_keys
    )
    base["destination"] = destination
    base["source"] = source
    base["destination_account_index"] = _account_index(
        instr=instr,
        account_keys=account_keys,
        position=SYSTEM_PROGRAM_TRANSFER_DESTINATION_ACCOUNT_INDEX,
    )
    base["source_account_index"] = _account_index(
        instr=instr,
        account_keys=account_keys,
        position=SYSTEM_PROGRAM_TRANSFER_SOURCE_ACCOUNT_INDEX,
    )
    if destination is None:
        base["parse_error"] = _PARSE_ERROR_UNRESOLVABLE_DESTINATION
        return base
    base["tip_destination_matched"] = (
        destination in KNOWN_JITO_TIP_ACCOUNTS
    )
    return base


# ---------------------------------------------------------------------------
# Public decoder
# ---------------------------------------------------------------------------


def decode_jito_tip(
    execution_input: Stage24ExecutionInput,
) -> Stage24JitoTipResult:
    """Decode the Jito-tip primitive for one transaction.

    Pure function: depends only on ``execution_input``. No side
    effects, no network, no env reads.
    """
    if not KNOWN_JITO_TIP_ACCOUNTS:
        return _build_accounts_unconfigured_result(
            execution_input=execution_input,
        )

    account_keys = execution_input.account_keys
    top_analyses = [
        _analyze_system_transfer_instruction(
            instr=instr,
            instruction_index=idx,
            account_keys=account_keys,
        )
        for idx, instr in enumerate(execution_input.top_level_instructions)
    ]
    inner_analyses = [
        _analyze_system_transfer_instruction(
            instr=instr,
            instruction_index=idx,
            account_keys=account_keys,
        )
        for idx, instr in enumerate(execution_input.inner_instructions)
    ]

    failed_tx = _transaction_clearly_failed(
        execution_input.transaction_status
    )

    if failed_tx:
        return _build_failed_tx_result(
            execution_input=execution_input,
            top_analyses=top_analyses,
            inner_analyses=inner_analyses,
        )

    top_tip_candidates = [
        a for a in top_analyses if bool(a.get("tip_destination_matched"))
    ]
    top_malformed = [
        a for a in top_analyses if bool(a.get("is_malformed_transfer_shape"))
    ]
    inner_tip_candidates = [
        a for a in inner_analyses if bool(a.get("tip_destination_matched"))
    ]

    if top_malformed and not top_tip_candidates:
        return _build_malformed_result(
            execution_input=execution_input,
            top_analyses=top_analyses,
            inner_analyses=inner_analyses,
        )

    if len(top_tip_candidates) >= 2:
        return _build_multiple_tip_candidates_result(
            execution_input=execution_input,
            top_analyses=top_analyses,
            inner_analyses=inner_analyses,
            top_tip_candidates=top_tip_candidates,
        )

    if len(top_tip_candidates) == 1:
        return _build_decoded_result(
            execution_input=execution_input,
            top_analyses=top_analyses,
            inner_analyses=inner_analyses,
            tip_analysis=top_tip_candidates[0],
            inner_tip_candidates=inner_tip_candidates,
        )

    return _build_absent_result(
        execution_input=execution_input,
        top_analyses=top_analyses,
        inner_analyses=inner_analyses,
        inner_tip_candidates=inner_tip_candidates,
    )


# ---------------------------------------------------------------------------
# Result builders
# ---------------------------------------------------------------------------


def _count_system_transfer_instructions(
    analyses: list[dict[str, object]],
) -> int:
    return sum(1 for a in analyses if bool(a.get("is_transfer")))


def _count_system_program_instructions(
    analyses: list[dict[str, object]],
) -> int:
    return sum(1 for a in analyses if bool(a.get("is_system_program")))


def _has_non_tip_system_transfer(
    analyses: list[dict[str, object]],
) -> bool:
    for a in analyses:
        if bool(a.get("is_transfer")) and not bool(
            a.get("tip_destination_matched")
        ):
            return True
    return False


def _build_base_numeric_features(
    *,
    top_analyses: list[dict[str, object]],
    inner_analyses: list[dict[str, object]],
) -> dict[str, object]:
    top_tip_count = sum(
        1 for a in top_analyses if bool(a.get("tip_destination_matched"))
    )
    inner_tip_count = sum(
        1 for a in inner_analyses if bool(a.get("tip_destination_matched"))
    )
    return {
        "jito_tip_lamports": None,
        "jito_tip_candidate_count": top_tip_count + inner_tip_count,
        "top_level_jito_tip_candidate_count": top_tip_count,
        "inner_jito_tip_candidate_count": inner_tip_count,
        "system_transfer_instruction_count": (
            _count_system_transfer_instructions(top_analyses)
        ),
        "system_program_instruction_count": (
            _count_system_program_instructions(top_analyses)
        ),
        "tip_destination_account_index": None,
        "tip_source_account_index": None,
    }


def _build_base_evidence(
    *,
    top_analyses: list[dict[str, object]],
    inner_analyses: list[dict[str, object]],
) -> dict[str, object]:
    return {
        "program_id": SYSTEM_PROGRAM_ID,
        "data_encoding": DATA_ENCODING_BASE64,
        "top_level_system_transfer_indexes": sorted(
            int(a["instruction_index"])
            for a in top_analyses
            if bool(a.get("is_transfer"))
        ),
        "inner_system_transfer_indexes": sorted(
            int(a["instruction_index"])
            for a in inner_analyses
            if bool(a.get("is_transfer"))
        ),
        "top_level_tip_candidate_indexes": sorted(
            int(a["instruction_index"])
            for a in top_analyses
            if bool(a.get("tip_destination_matched"))
        ),
        "inner_tip_candidate_indexes": sorted(
            int(a["instruction_index"])
            for a in inner_analyses
            if bool(a.get("tip_destination_matched"))
        ),
    }


def _build_accounts_unconfigured_result(
    *,
    execution_input: Stage24ExecutionInput,
) -> Stage24JitoTipResult:
    reasons: tuple[str, ...] = (REASON_JITO_TIP_ACCOUNTS_UNCONFIGURED,)
    numeric_features: dict[str, object] = {
        "jito_tip_lamports": None,
        "jito_tip_candidate_count": 0,
        "top_level_jito_tip_candidate_count": 0,
        "inner_jito_tip_candidate_count": 0,
        "system_transfer_instruction_count": 0,
        "system_program_instruction_count": 0,
        "tip_destination_account_index": None,
        "tip_source_account_index": None,
    }
    evidence: dict[str, object] = {
        "program_id": SYSTEM_PROGRAM_ID,
        "data_encoding": DATA_ENCODING_BASE64,
        "known_tip_account_count": 0,
    }
    return build_jito_tip_result(
        decoder_name=JITO_TIP_DECODER_NAME,
        decoder_version=JITO_TIP_DECODER_VERSION,
        threshold_version=DEFAULT_THRESHOLD_VERSION,
        decoder_status=DECODER_STATUS_UNSUPPORTED,
        data_status=DATA_STATUS_UNSUPPORTED,
        confidence_level=CONFIDENCE_LEVEL_NONE,
        fee_source=FEE_SOURCE_UNKNOWN,
        route_family=ROUTE_FAMILY_NO_ROUTER_DETECTED,
        instruction_location=INSTRUCTION_LOCATION_UNKNOWN,
        program_id="",
        tip_account="",
        amount_lamports=None,
        reason_codes=reasons,
        numeric_features=MappingProxyType(numeric_features),
        evidence=MappingProxyType(evidence),
        input_missing_fields=execution_input.missing_fields,
    )


def _build_failed_tx_result(
    *,
    execution_input: Stage24ExecutionInput,
    top_analyses: list[dict[str, object]],
    inner_analyses: list[dict[str, object]],
) -> Stage24JitoTipResult:
    top_tip_candidates = [
        a for a in top_analyses if bool(a.get("tip_destination_matched"))
    ]
    inner_tip_candidates = [
        a for a in inner_analyses if bool(a.get("tip_destination_matched"))
    ]
    any_candidate = bool(top_tip_candidates) or bool(inner_tip_candidates)

    numeric_features = _build_base_numeric_features(
        top_analyses=top_analyses, inner_analyses=inner_analyses
    )
    evidence = _build_base_evidence(
        top_analyses=top_analyses, inner_analyses=inner_analyses
    )
    evidence["transaction_status"] = execution_input.transaction_status

    reasons: list[str] = [REASON_JITO_TIP_TX_FAILED]
    if any_candidate:
        decoder_status = DECODER_STATUS_PARTIAL
        data_status = DATA_STATUS_PARTIAL
        confidence_level = CONFIDENCE_LEVEL_LOW
        fee_source = FEE_SOURCE_JITO_TIP_CANDIDATE
    else:
        decoder_status = DECODER_STATUS_NOT_APPLICABLE
        data_status = DATA_STATUS_NOT_APPLICABLE
        confidence_level = CONFIDENCE_LEVEL_NONE
        fee_source = FEE_SOURCE_UNKNOWN

    if inner_tip_candidates:
        reasons.append(REASON_JITO_TIP_INNER_CANDIDATE_PRESENT)
    if len(top_tip_candidates) >= 2:
        reasons.append(REASON_MULTIPLE_JITO_TIP_CANDIDATES)
    if _has_non_tip_system_transfer(top_analyses):
        reasons.append(REASON_SYSTEM_TRANSFER_NON_TIP_IGNORED)

    instruction_location = (
        INSTRUCTION_LOCATION_TOP_LEVEL
        if top_tip_candidates
        else (
            INSTRUCTION_LOCATION_INNER
            if inner_tip_candidates
            else INSTRUCTION_LOCATION_UNKNOWN
        )
    )
    program_id = SYSTEM_PROGRAM_ID if any_candidate else ""

    return build_jito_tip_result(
        decoder_name=JITO_TIP_DECODER_NAME,
        decoder_version=JITO_TIP_DECODER_VERSION,
        threshold_version=DEFAULT_THRESHOLD_VERSION,
        decoder_status=decoder_status,
        data_status=data_status,
        confidence_level=confidence_level,
        fee_source=fee_source,
        route_family=ROUTE_FAMILY_NO_ROUTER_DETECTED,
        instruction_location=instruction_location,
        program_id=program_id,
        tip_account="",
        amount_lamports=None,
        reason_codes=tuple(reasons),
        numeric_features=MappingProxyType(numeric_features),
        evidence=MappingProxyType(evidence),
        input_missing_fields=execution_input.missing_fields,
    )


def _build_absent_result(
    *,
    execution_input: Stage24ExecutionInput,
    top_analyses: list[dict[str, object]],
    inner_analyses: list[dict[str, object]],
    inner_tip_candidates: list[dict[str, object]],
) -> Stage24JitoTipResult:
    reasons: list[str] = [REASON_JITO_TIP_ABSENT]
    if not execution_input.top_level_instructions:
        reasons.append(REASON_JITO_TIP_NO_TOP_LEVEL_INSTRUCTIONS)
        data_status = DATA_STATUS_NOT_APPLICABLE
    else:
        data_status = DATA_STATUS_MISSING
    if inner_tip_candidates:
        reasons.append(REASON_JITO_TIP_INNER_CANDIDATE_PRESENT)
    if _has_non_tip_system_transfer(top_analyses):
        reasons.append(REASON_SYSTEM_TRANSFER_NON_TIP_IGNORED)

    numeric_features = _build_base_numeric_features(
        top_analyses=top_analyses, inner_analyses=inner_analyses
    )
    evidence = _build_base_evidence(
        top_analyses=top_analyses, inner_analyses=inner_analyses
    )

    fee_source = (
        FEE_SOURCE_JITO_TIP_CANDIDATE
        if inner_tip_candidates
        else FEE_SOURCE_UNKNOWN
    )
    instruction_location = (
        INSTRUCTION_LOCATION_INNER
        if inner_tip_candidates
        else INSTRUCTION_LOCATION_UNKNOWN
    )
    program_id = SYSTEM_PROGRAM_ID if inner_tip_candidates else ""

    return build_jito_tip_result(
        decoder_name=JITO_TIP_DECODER_NAME,
        decoder_version=JITO_TIP_DECODER_VERSION,
        threshold_version=DEFAULT_THRESHOLD_VERSION,
        decoder_status=DECODER_STATUS_ABSENT,
        data_status=data_status,
        confidence_level=CONFIDENCE_LEVEL_NONE,
        fee_source=fee_source,
        route_family=ROUTE_FAMILY_NO_ROUTER_DETECTED,
        instruction_location=instruction_location,
        program_id=program_id,
        tip_account="",
        amount_lamports=None,
        reason_codes=tuple(reasons),
        numeric_features=MappingProxyType(numeric_features),
        evidence=MappingProxyType(evidence),
        input_missing_fields=execution_input.missing_fields,
    )


def _build_malformed_result(
    *,
    execution_input: Stage24ExecutionInput,
    top_analyses: list[dict[str, object]],
    inner_analyses: list[dict[str, object]],
) -> Stage24JitoTipResult:
    inner_tip_candidates = [
        a for a in inner_analyses if bool(a.get("tip_destination_matched"))
    ]
    reasons: list[str] = [REASON_JITO_TIP_MALFORMED_TRANSFER]
    if inner_tip_candidates:
        reasons.append(REASON_JITO_TIP_INNER_CANDIDATE_PRESENT)
    if _has_non_tip_system_transfer(top_analyses):
        reasons.append(REASON_SYSTEM_TRANSFER_NON_TIP_IGNORED)

    numeric_features = _build_base_numeric_features(
        top_analyses=top_analyses, inner_analyses=inner_analyses
    )
    malformed_indexes = sorted(
        int(a["instruction_index"])
        for a in top_analyses
        if bool(a.get("is_malformed_transfer_shape"))
    )
    numeric_features["malformed_transfer_instruction_count"] = len(
        malformed_indexes
    )

    evidence = _build_base_evidence(
        top_analyses=top_analyses, inner_analyses=inner_analyses
    )
    evidence["malformed_transfer_indexes"] = malformed_indexes

    return build_jito_tip_result(
        decoder_name=JITO_TIP_DECODER_NAME,
        decoder_version=JITO_TIP_DECODER_VERSION,
        threshold_version=DEFAULT_THRESHOLD_VERSION,
        decoder_status=DECODER_STATUS_DECODE_FAILED,
        data_status=DATA_STATUS_MALFORMED,
        confidence_level=CONFIDENCE_LEVEL_NONE,
        fee_source=FEE_SOURCE_UNKNOWN,
        route_family=ROUTE_FAMILY_NO_ROUTER_DETECTED,
        instruction_location=INSTRUCTION_LOCATION_TOP_LEVEL,
        program_id=SYSTEM_PROGRAM_ID,
        tip_account="",
        amount_lamports=None,
        reason_codes=tuple(reasons),
        numeric_features=MappingProxyType(numeric_features),
        evidence=MappingProxyType(evidence),
        input_missing_fields=execution_input.missing_fields,
    )


def _build_multiple_tip_candidates_result(
    *,
    execution_input: Stage24ExecutionInput,
    top_analyses: list[dict[str, object]],
    inner_analyses: list[dict[str, object]],
    top_tip_candidates: list[dict[str, object]],
) -> Stage24JitoTipResult:
    inner_tip_candidates = [
        a for a in inner_analyses if bool(a.get("tip_destination_matched"))
    ]
    reasons: list[str] = [REASON_MULTIPLE_JITO_TIP_CANDIDATES]
    if inner_tip_candidates:
        reasons.append(REASON_JITO_TIP_INNER_CANDIDATE_PRESENT)
    if _has_non_tip_system_transfer(top_analyses):
        reasons.append(REASON_SYSTEM_TRANSFER_NON_TIP_IGNORED)

    numeric_features = _build_base_numeric_features(
        top_analyses=top_analyses, inner_analyses=inner_analyses
    )
    candidate_lamports = [
        int(a["lamports"])
        for a in top_tip_candidates
        if isinstance(a.get("lamports"), int)
    ]
    numeric_features["jito_tip_candidate_lamports_min"] = (
        min(candidate_lamports) if candidate_lamports else None
    )
    numeric_features["jito_tip_candidate_lamports_max"] = (
        max(candidate_lamports) if candidate_lamports else None
    )

    evidence = _build_base_evidence(
        top_analyses=top_analyses, inner_analyses=inner_analyses
    )
    evidence["candidate_tip_accounts"] = sorted(
        {
            str(a["destination"])
            for a in top_tip_candidates
            if isinstance(a.get("destination"), str)
        }
    )
    evidence["candidate_lamports_per_index"] = sorted(
        [
            [int(a["instruction_index"]), int(a["lamports"])]
            for a in top_tip_candidates
            if isinstance(a.get("lamports"), int)
        ]
    )

    return build_jito_tip_result(
        decoder_name=JITO_TIP_DECODER_NAME,
        decoder_version=JITO_TIP_DECODER_VERSION,
        threshold_version=DEFAULT_THRESHOLD_VERSION,
        decoder_status=DECODER_STATUS_DECODE_UNCONFIRMED,
        data_status=DATA_STATUS_PARTIAL,
        confidence_level=CONFIDENCE_LEVEL_LOW,
        fee_source=FEE_SOURCE_JITO_TIP_CANDIDATE,
        route_family=ROUTE_FAMILY_NO_ROUTER_DETECTED,
        instruction_location=INSTRUCTION_LOCATION_TOP_LEVEL,
        program_id=SYSTEM_PROGRAM_ID,
        tip_account="",
        amount_lamports=None,
        reason_codes=tuple(reasons),
        numeric_features=MappingProxyType(numeric_features),
        evidence=MappingProxyType(evidence),
        input_missing_fields=execution_input.missing_fields,
    )


def _build_decoded_result(
    *,
    execution_input: Stage24ExecutionInput,
    top_analyses: list[dict[str, object]],
    inner_analyses: list[dict[str, object]],
    tip_analysis: dict[str, object],
    inner_tip_candidates: list[dict[str, object]],
) -> Stage24JitoTipResult:
    reasons: list[str] = [REASON_JITO_TIP_DECODED]
    if inner_tip_candidates:
        reasons.append(REASON_JITO_TIP_INNER_CANDIDATE_PRESENT)
    if _has_non_tip_system_transfer(top_analyses):
        reasons.append(REASON_SYSTEM_TRANSFER_NON_TIP_IGNORED)

    lamports_obj = tip_analysis.get("lamports")
    assert isinstance(lamports_obj, int)
    tip_account_obj = tip_analysis.get("destination")
    assert isinstance(tip_account_obj, str)

    numeric_features = _build_base_numeric_features(
        top_analyses=top_analyses, inner_analyses=inner_analyses
    )
    numeric_features["jito_tip_lamports"] = lamports_obj
    dest_index = tip_analysis.get("destination_account_index")
    source_index = tip_analysis.get("source_account_index")
    if isinstance(dest_index, int):
        numeric_features["tip_destination_account_index"] = dest_index
    if isinstance(source_index, int):
        numeric_features["tip_source_account_index"] = source_index

    evidence = _build_base_evidence(
        top_analyses=top_analyses, inner_analyses=inner_analyses
    )
    evidence["tip_account"] = tip_account_obj
    evidence["tip_instruction_index"] = int(
        tip_analysis["instruction_index"]
    )
    source_obj = tip_analysis.get("source")
    if isinstance(source_obj, str) and source_obj != "":
        evidence["tip_source_account"] = source_obj

    return build_jito_tip_result(
        decoder_name=JITO_TIP_DECODER_NAME,
        decoder_version=JITO_TIP_DECODER_VERSION,
        threshold_version=DEFAULT_THRESHOLD_VERSION,
        decoder_status=DECODER_STATUS_DECODED,
        data_status=DATA_STATUS_COMPLETE,
        confidence_level=CONFIDENCE_LEVEL_HIGH,
        fee_source=FEE_SOURCE_JITO_TIP,
        route_family=ROUTE_FAMILY_NO_ROUTER_DETECTED,
        instruction_location=INSTRUCTION_LOCATION_TOP_LEVEL,
        program_id=SYSTEM_PROGRAM_ID,
        tip_account=tip_account_obj,
        amount_lamports=lamports_obj,
        reason_codes=tuple(reasons),
        numeric_features=MappingProxyType(numeric_features),
        evidence=MappingProxyType(evidence),
        input_missing_fields=execution_input.missing_fields,
    )


__all__ = [
    "DATA_ENCODING_BASE64",
    "JITO_TIP_DECODER_NAME",
    "JITO_TIP_DECODER_VERSION",
    "REASON_JITO_TIP_ABSENT",
    "REASON_JITO_TIP_ACCOUNTS_UNCONFIGURED",
    "REASON_JITO_TIP_DECODED",
    "REASON_JITO_TIP_INNER_CANDIDATE_PRESENT",
    "REASON_JITO_TIP_MALFORMED_TRANSFER",
    "REASON_JITO_TIP_NO_TOP_LEVEL_INSTRUCTIONS",
    "REASON_JITO_TIP_TX_FAILED",
    "REASON_MULTIPLE_JITO_TIP_CANDIDATES",
    "REASON_SYSTEM_TRANSFER_NON_TIP_IGNORED",
    "SYSTEM_PROGRAM_TAG_BYTE_WIDTH",
    "SYSTEM_PROGRAM_TRANSFER_DESTINATION_ACCOUNT_INDEX",
    "SYSTEM_PROGRAM_TRANSFER_LAMPORTS_BYTE_WIDTH",
    "SYSTEM_PROGRAM_TRANSFER_SOURCE_ACCOUNT_INDEX",
    "SYSTEM_PROGRAM_TRANSFER_TAG",
    "SYSTEM_PROGRAM_TRANSFER_TOTAL_BYTE_WIDTH",
    "decode_jito_tip",
]

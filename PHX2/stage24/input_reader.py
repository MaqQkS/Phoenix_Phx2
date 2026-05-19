"""Stage 24 input reader (foundation only at 24.1).

Reads Stage 24-shaped decoded-tx JSONL artifacts from operator-
supplied paths and projects each row into an immutable
``Stage24ExecutionInput``.

Supported input shapes for 24.1:

  * Stage 24-shaped decoded-tx JSONL (``input_kind ==
    "decoded_tx_jsonl"``). One Solana decoded transaction per
    JSONL row, with Stage 24-normalized field names
    (``top_level_instructions`` / ``inner_instructions`` /
    ``pre_balances`` / ``post_balances`` / ``pre_token_balances``
    / ``post_token_balances`` / ``log_messages`` / ``meta`` /
    ``account_keys`` / ``slot_unix_time``).
  * Synthetic Stage 24-shaped decoded-tx JSONL (``input_kind ==
    "synthetic_decoded_tx_jsonl"``). Same shape; sourced from
    Stage 24 fixture builders.
  * Sanitized real Stage 24-shaped decoded-tx JSONL
    (``input_kind == "sanitized_real_decoded_tx_jsonl"``). Same
    shape; sourced from redacted real fixtures. Stage 24.5
    introduces the first real fixture; Stage 24.1 ships the kind
    as a recognized closed-set token only.

Reader behavior (locked at 24.1):

  * No hardcoded path. The reader's entrypoint takes a caller-
    supplied ``pathlib.Path``.
  * No network calls. No env reads. No repo writes. No mutation
    of input artifacts.
  * Deterministic row ordering: rows are emitted in file order
    (first line first, last line last). Blank trailing lines
    are ignored; intra-file blank lines raise
    ``Stage24InputError``.
  * Missing file: ``Stage24InputError``.
  * Path is a directory: ``Stage24InputError``.
  * Unknown ``input_kind``: ``Stage24InputError``.
  * Malformed JSON / non-object line: ``Stage24InputError``.
  * Forbidden field-name substring on the row (recursively):
    ``Stage24InputError``.
  * Forbidden value substring (URL / webhook host / long-hex
    credential shape) on a row's string value: ``Stage24InputError``.
  * Stage 24.1 does NOT parse Solana instruction bytes. Each
    instruction in ``top_level_instructions`` / ``inner_instructions``
    is preserved verbatim as a frozen mapping. Stage 24.2+
    decoders parse the instruction layout.
  * List fields (``account_keys`` / ``*_instructions`` /
    ``*_balances`` / ``log_messages``) are converted to tuples
    for ``NamedTuple`` immutability.
  * Optional fields absent on the upstream row are NOT
    fabricated. The reader populates
    ``Stage24ExecutionInput.missing_fields`` with the sorted
    tuple of absent preserved-concept names so downstream
    decoders can reason about input completeness.

This module imports only stdlib (``json`` / ``pathlib`` /
``types``) plus the Stage 24 constants / errors / models. It
does NOT import Stage 21 / Stage 22 / Stage 23 modules; Stage
22 raw capture is only source material for an externally-
produced Stage 24-shaped JSONL, never a direct import. It does
NOT import any network / RPC / messaging / DB / scheduler /
secrets-management library, does NOT read the process
environment, does NOT define a CLI surface, and contains no
top-level I/O.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import MappingProxyType
from typing import Mapping

from PHX2.stage24.constants import (
    DEFAULT_SCHEMA_VERSION,
    INPUT_KINDS,
    STAGE24_FORBIDDEN_INPUT_FIELD_SUBSTRINGS,
    STAGE24_FORBIDDEN_INPUT_VALUE_SUBSTRINGS,
    STAGE24_LONG_HEX_RUN_MIN_LEN,
)
from PHX2.stage24.errors import Stage24InputError
from PHX2.stage24.models import (
    Stage24ExecutionInput,
    compute_execution_input_hash_from_projection,
)


# ---------------------------------------------------------------------------
# Module-private shape constants
# ---------------------------------------------------------------------------


_HEX_CHARS: str = "0123456789abcdefABCDEF"

# Sentinel value the reader uses for the ``slot`` and
# ``slot_unix_time`` fields of a ``Stage24ExecutionInput`` when
# the upstream row did not carry the field. ``-1`` is invalid
# as a real slot or Unix-seconds value and is locked here so
# callers can detect "value was absent" without an Optional[int]
# (which would break the deterministic-hash contract on
# Stage24ExecutionInput).
_SLOT_ABSENT_SENTINEL: int = -1


# Stage 24 preserved-input concepts. Each entry is
# (concept_name, source_aliases_tuple). A concept is missing only
# when EVERY alias listed for that concept is absent from the
# row. Locked at 24.1.
_INPUT_CONCEPT_ALIASES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("provider_id", ("provider_id",)),
    ("signature", ("signature",)),
    ("slot", ("slot",)),
    ("slot_unix_time", ("slot_unix_time",)),
    ("observed_at_utc", ("observed_at_utc",)),
    ("transaction_status", ("transaction_status",)),
    ("account_keys", ("account_keys",)),
    ("top_level_instructions", ("top_level_instructions",)),
    ("inner_instructions", ("inner_instructions",)),
    ("pre_balances", ("pre_balances",)),
    ("post_balances", ("post_balances",)),
    ("pre_token_balances", ("pre_token_balances",)),
    ("post_token_balances", ("post_token_balances",)),
    ("log_messages", ("log_messages",)),
    ("meta", ("meta",)),
)


# ---------------------------------------------------------------------------
# Field-name / value safety
# ---------------------------------------------------------------------------


def _field_name_is_secret_bearing(name: str) -> bool:
    lower = name.lower()
    for forbidden in STAGE24_FORBIDDEN_INPUT_FIELD_SUBSTRINGS:
        if forbidden in lower:
            return True
    return False


def _has_long_hex_run(s: str) -> bool:
    """Return True iff s contains a run of >= STAGE24_LONG_HEX_RUN_MIN_LEN
    hex characters (mixed-case).
    """
    run = 0
    for ch in s:
        if ch in _HEX_CHARS:
            run += 1
            if run >= STAGE24_LONG_HEX_RUN_MIN_LEN:
                return True
        else:
            run = 0
    return False


def _string_value_carries_leak_shape(value: str) -> bool:
    lower = value.lower()
    for forbidden in STAGE24_FORBIDDEN_INPUT_VALUE_SUBSTRINGS:
        if forbidden in lower:
            return True
    if _has_long_hex_run(value):
        return True
    return False


def stage24_value_carries_leak_shape(value: object) -> bool:
    """Public Stage 24 secret-shape detector for STRING VALUES.

    Mirrors the input reader's per-value sanitiser so callers
    that bypass the reader (the Stage 24.6 artifact writer in
    particular, when a caller constructs a Stage 24 record
    directly) can re-run the same scan over user-controllable
    string values before serialising them to disk.

    Returns ``True`` if ``value`` is a string that carries any
    of:

      * a URL / webhook host substring from
        ``STAGE24_FORBIDDEN_INPUT_VALUE_SUBSTRINGS``;
      * a run of >= ``STAGE24_LONG_HEX_RUN_MIN_LEN`` hex-class
        characters (token / credential shape);
      * an env-style sensitive substring from
        ``STAGE24_FORBIDDEN_INPUT_FIELD_SUBSTRINGS`` embedded
        in the value (e.g. ``"api_key"``, ``"webhook"``,
        ``"password"``).

    Returns ``False`` for non-string values; the writer scans
    user-controllable string fields, and non-string artifact
    values (closed-set integers, sorted reason-code tuples,
    writer-computed SHA-256 hashes) are never sent through this
    function.
    """
    if not isinstance(value, str):
        return False
    if _string_value_carries_leak_shape(value):
        return True
    lower = value.lower()
    for forbidden in STAGE24_FORBIDDEN_INPUT_FIELD_SUBSTRINGS:
        if forbidden in lower:
            return True
    return False


def _scan_value_recursively(
    *,
    value: object,
    line_index: int,
    field_path: str,
) -> None:
    """Recursively scan ``value`` for leak shapes.

    Raises ``Stage24InputError`` when any string value carries
    a leak-shape substring or any mapping key carries a forbidden
    field-name substring.
    """
    if isinstance(value, str):
        if _string_value_carries_leak_shape(value):
            raise Stage24InputError(
                f"line {line_index}: field {field_path!r} value carries a "
                "leak-shape substring"
            )
        return
    if isinstance(value, Mapping):
        for key, nested in value.items():
            if not isinstance(key, str):
                raise Stage24InputError(
                    f"line {line_index}: field {field_path!r} has a "
                    "non-string nested key"
                )
            if _field_name_is_secret_bearing(key):
                raise Stage24InputError(
                    f"line {line_index}: nested field {key!r} under "
                    f"{field_path!r} carries a forbidden secret-bearing "
                    "substring"
                )
            _scan_value_recursively(
                value=nested,
                line_index=line_index,
                field_path=f"{field_path}.{key}",
            )
        return
    if isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _scan_value_recursively(
                value=item,
                line_index=line_index,
                field_path=f"{field_path}[{index}]",
            )
        return
    # Primitive scalars (int / bool / float / None) need no scan.


# ---------------------------------------------------------------------------
# Path / file boundary
# ---------------------------------------------------------------------------


def _require_path_is_existing_file(path: Path) -> None:
    if not path.exists():
        raise Stage24InputError(
            f"input path does not exist: {path.name!r}"
        )
    if path.is_dir():
        raise Stage24InputError(
            f"input path is a directory; expected a file: {path.name!r}"
        )
    if not path.is_file():
        raise Stage24InputError(
            f"input path is not a regular file: {path.name!r}"
        )


def _require_input_kind(input_kind: str) -> None:
    if input_kind not in INPUT_KINDS:
        raise Stage24InputError(
            f"input_kind {input_kind!r} is not a Stage 24 input kind"
        )


# ---------------------------------------------------------------------------
# Row-level projection
# ---------------------------------------------------------------------------


def _require_row_is_mapping(
    *,
    row: object,
    line_index: int,
) -> Mapping[str, object]:
    if not isinstance(row, dict):
        raise Stage24InputError(
            f"line {line_index}: not a JSON object"
        )
    return row


def _scan_row_top_level_field_names(
    *,
    row: Mapping[str, object],
    line_index: int,
) -> None:
    for key in row.keys():
        if not isinstance(key, str):
            raise Stage24InputError(
                f"line {line_index}: non-string field name"
            )
        if _field_name_is_secret_bearing(key):
            raise Stage24InputError(
                f"line {line_index}: forbidden secret-bearing field "
                f"name {key!r}"
            )


def _scan_row_values_recursively(
    *,
    row: Mapping[str, object],
    line_index: int,
) -> None:
    for key, value in row.items():
        _scan_value_recursively(
            value=value,
            line_index=line_index,
            field_path=key,
        )


def _project_string(
    *,
    row: Mapping[str, object],
    key: str,
    line_index: int,
) -> str:
    raw = row.get(key)
    if raw is None:
        return ""
    if not isinstance(raw, str):
        raise Stage24InputError(
            f"line {line_index}: field {key!r} must be a string when "
            "present"
        )
    return raw


def _project_int_with_sentinel(
    *,
    row: Mapping[str, object],
    key: str,
    line_index: int,
) -> int:
    raw = row.get(key)
    if raw is None:
        return _SLOT_ABSENT_SENTINEL
    if isinstance(raw, bool):
        raise Stage24InputError(
            f"line {line_index}: field {key!r} must be an int, not a bool"
        )
    if not isinstance(raw, int):
        raise Stage24InputError(
            f"line {line_index}: field {key!r} must be an int when present"
        )
    return raw


def _project_tuple_of_strings(
    *,
    row: Mapping[str, object],
    key: str,
    line_index: int,
) -> tuple[str, ...]:
    raw = row.get(key)
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise Stage24InputError(
            f"line {line_index}: field {key!r} must be a list when present"
        )
    out: list[str] = []
    for index, item in enumerate(raw):
        if not isinstance(item, str):
            raise Stage24InputError(
                f"line {line_index}: field {key!r}[{index}] must be a "
                "string"
            )
        out.append(item)
    return tuple(out)


def _project_tuple_of_ints(
    *,
    row: Mapping[str, object],
    key: str,
    line_index: int,
) -> tuple[int, ...]:
    raw = row.get(key)
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise Stage24InputError(
            f"line {line_index}: field {key!r} must be a list when present"
        )
    out: list[int] = []
    for index, item in enumerate(raw):
        if isinstance(item, bool):
            raise Stage24InputError(
                f"line {line_index}: field {key!r}[{index}] must be an "
                "int, not a bool"
            )
        if not isinstance(item, int):
            raise Stage24InputError(
                f"line {line_index}: field {key!r}[{index}] must be an int"
            )
        out.append(item)
    return tuple(out)


def _freeze_mapping(value: Mapping[str, object]) -> Mapping[str, object]:
    return MappingProxyType(dict(value))


def _project_tuple_of_mappings(
    *,
    row: Mapping[str, object],
    key: str,
    line_index: int,
) -> tuple[Mapping[str, object], ...]:
    raw = row.get(key)
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise Stage24InputError(
            f"line {line_index}: field {key!r} must be a list when present"
        )
    out: list[Mapping[str, object]] = []
    for index, item in enumerate(raw):
        if not isinstance(item, Mapping):
            raise Stage24InputError(
                f"line {line_index}: field {key!r}[{index}] must be an "
                "object"
            )
        out.append(_freeze_mapping(item))
    return tuple(out)


def _project_meta(
    *,
    row: Mapping[str, object],
    line_index: int,
) -> Mapping[str, object]:
    raw = row.get("meta")
    if raw is None:
        return MappingProxyType({})
    if not isinstance(raw, Mapping):
        raise Stage24InputError(
            f"line {line_index}: field 'meta' must be an object when present"
        )
    return _freeze_mapping(raw)


def _compute_missing_concepts(
    *,
    row: Mapping[str, object],
) -> tuple[str, ...]:
    missing: list[str] = []
    for concept_name, aliases in _INPUT_CONCEPT_ALIASES:
        if not any(alias in row for alias in aliases):
            missing.append(concept_name)
    return tuple(sorted(missing))


def _derive_input_id(
    *,
    signature: str,
    payload_hash: str,
) -> str:
    if signature != "":
        return signature
    return "tx_synth_" + payload_hash[:24]


def _build_execution_input_from_row(
    *,
    row: Mapping[str, object],
    line_index: int,
    input_kind: str,
) -> Stage24ExecutionInput:
    signature = _project_string(row=row, key="signature", line_index=line_index)
    slot = _project_int_with_sentinel(
        row=row, key="slot", line_index=line_index
    )
    slot_unix_time = _project_int_with_sentinel(
        row=row, key="slot_unix_time", line_index=line_index
    )
    observed_at_utc = _project_string(
        row=row, key="observed_at_utc", line_index=line_index
    )
    provider_id = _project_string(
        row=row, key="provider_id", line_index=line_index
    )
    transaction_status = _project_string(
        row=row, key="transaction_status", line_index=line_index
    )
    account_keys = _project_tuple_of_strings(
        row=row, key="account_keys", line_index=line_index
    )
    top_level_instructions = _project_tuple_of_mappings(
        row=row, key="top_level_instructions", line_index=line_index
    )
    inner_instructions = _project_tuple_of_mappings(
        row=row, key="inner_instructions", line_index=line_index
    )
    pre_balances = _project_tuple_of_ints(
        row=row, key="pre_balances", line_index=line_index
    )
    post_balances = _project_tuple_of_ints(
        row=row, key="post_balances", line_index=line_index
    )
    pre_token_balances = _project_tuple_of_mappings(
        row=row, key="pre_token_balances", line_index=line_index
    )
    post_token_balances = _project_tuple_of_mappings(
        row=row, key="post_token_balances", line_index=line_index
    )
    log_messages = _project_tuple_of_strings(
        row=row, key="log_messages", line_index=line_index
    )
    meta = _project_meta(row=row, line_index=line_index)
    missing_fields = _compute_missing_concepts(row=row)

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
        top_level_instructions=top_level_instructions,
        inner_instructions=inner_instructions,
        pre_balances=pre_balances,
        post_balances=post_balances,
        pre_token_balances=pre_token_balances,
        post_token_balances=post_token_balances,
        log_messages=log_messages,
        meta=meta,
        missing_fields=missing_fields,
    )
    input_id = _derive_input_id(
        signature=signature, payload_hash=payload_hash
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
        top_level_instructions=top_level_instructions,
        inner_instructions=inner_instructions,
        pre_balances=pre_balances,
        post_balances=post_balances,
        pre_token_balances=pre_token_balances,
        post_token_balances=post_token_balances,
        log_messages=log_messages,
        meta=meta,
        payload_hash=payload_hash,
        missing_fields=missing_fields,
    )


# ---------------------------------------------------------------------------
# Public entrypoint
# ---------------------------------------------------------------------------


def read_stage24_tx_jsonl(
    *,
    path: Path,
    input_kind: str,
) -> tuple[Stage24ExecutionInput, ...]:
    """Read a Stage 24-shaped decoded-tx JSONL artifact.

    The reader emits one ``Stage24ExecutionInput`` per non-blank
    JSONL line in file order.

    Parameters:

      * ``path``       -- operator-supplied ``pathlib.Path`` to a
                          JSONL file. Required. Missing path,
                          directory path, and non-regular-file
                          path each raise ``Stage24InputError``.
      * ``input_kind`` -- one of ``INPUT_KINDS``.

    Returns a tuple of ``Stage24ExecutionInput`` records in file
    order. The returned tuple may be empty for an empty file.
    """
    _require_input_kind(input_kind)
    _require_path_is_existing_file(path)
    raw = path.read_text(encoding="utf-8")
    return tuple(_iter_inputs(raw=raw, input_kind=input_kind))


def _iter_inputs(
    *,
    raw: str,
    input_kind: str,
) -> list[Stage24ExecutionInput]:
    out: list[Stage24ExecutionInput] = []
    # Trim trailing newlines so a file that is empty or that
    # contains only end-of-file newline characters reduces to the
    # empty string and yields zero inputs. Intra-file blank lines
    # remain detectable because the rstrip only removes a
    # contiguous trailing newline run.
    stripped = raw.rstrip("\n")
    if stripped == "":
        return out
    lines = stripped.split("\n")
    for index, line in enumerate(lines, start=1):
        if line == "":
            raise Stage24InputError(
                f"line {index}: intra-file blank line"
            )
        try:
            parsed = json.loads(line)
        except ValueError as exc:
            raise Stage24InputError(
                f"line {index}: malformed JSON"
            ) from exc
        row = _require_row_is_mapping(row=parsed, line_index=index)
        _scan_row_top_level_field_names(row=row, line_index=index)
        _scan_row_values_recursively(row=row, line_index=index)
        out.append(
            _build_execution_input_from_row(
                row=row,
                line_index=index,
                input_kind=input_kind,
            )
        )
    return out


__all__ = [
    "read_stage24_tx_jsonl",
    "stage24_value_carries_leak_shape",
]

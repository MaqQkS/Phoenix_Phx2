"""Stage 25 input reader (foundation only at 25.1).

Reads Stage 25-shaped migration-observation and price-observation
JSONL artifacts from operator-supplied paths and projects each
row into an immutable ``Stage25MigrationObservation`` or
``Stage25PriceObservation``.

Supported input shapes for 25.1 (see ``INPUT_KINDS`` in
``PHX2/stage25/constants.py``):

  * ``migration_observations_jsonl``
  * ``price_observations_jsonl``
  * ``synthetic_migration_observations_jsonl``
  * ``synthetic_price_observations_jsonl``
  * ``sanitized_real_migration_observations_jsonl``
  * ``sanitized_real_price_observations_jsonl``

Reader behavior (locked at 25.1):

  * No hardcoded path. Entry points take a caller-supplied
    ``pathlib.Path``.
  * No network calls. No env reads. No repo writes. No mutation of
    input artifacts.
  * Deterministic row ordering: rows are emitted in file order.
    Trailing blank lines are ignored; intra-file blank lines
    raise ``Stage25InputError``.
  * Missing file / directory path / non-regular-file path:
    ``Stage25InputError``.
  * Unknown ``input_kind``: ``Stage25InputError``.
  * Malformed JSON / non-object line: ``Stage25InputError``.
  * Forbidden field-name substring (recursively): ``Stage25InputError``.
  * Forbidden value substring / long-hex credential shape (recursively):
    ``Stage25InputError``.
  * Required fields (``token_mint`` / ``provider_id``) absent on a
    row: ``Stage25InputError``.
  * Stage 25.1 is contracts-only: the reader does NOT run any
    semantic invariant beyond closed-set / shape / secret checks.
    The missing-fields tuple records absent optional concepts so
    future measurers can reason about completeness without
    re-checking source absence.

This module imports only stdlib (``json`` / ``pathlib`` /
``types``) plus the Stage 25 constants / errors / models. It does
NOT import Stage 21 / Stage 22 / Stage 23 / Stage 24 production
modules, does NOT import any network / RPC / messaging / DB /
scheduler / secrets-management library, does NOT read the
process environment, does NOT define a CLI surface, and contains
no top-level I/O.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import MappingProxyType
from typing import Mapping, Optional

from PHX2.stage25.constants import (
    DEFAULT_SCHEMA_VERSION,
    INPUT_KINDS,
    MIGRATION_OBSERVATION_INPUT_KINDS,
    PRICE_OBSERVATION_INPUT_KINDS,
    QUOTE_DENOMINATION_UNKNOWN_QUOTE,
    SOURCE_FAMILY_UNKNOWN_SOURCE,
    SOURCE_STATUS_ABSENT,
    STAGE25_FORBIDDEN_INPUT_FIELD_SUBSTRINGS,
    STAGE25_FORBIDDEN_INPUT_VALUE_SUBSTRINGS,
    STAGE25_LONG_HEX_RUN_MIN_LEN,
)
from PHX2.stage25.errors import Stage25ContractError, Stage25InputError
from PHX2.stage25.models import (
    Stage25MigrationObservation,
    Stage25PriceObservation,
    build_migration_observation,
    build_price_observation,
)


# ---------------------------------------------------------------------------
# Module-private shape constants
# ---------------------------------------------------------------------------


_HEX_CHARS: str = "0123456789abcdefABCDEF"

# Sentinel value the reader uses for slot / block_time fields when
# the upstream row did not carry the field. ``-1`` is invalid as a
# real slot or Unix-seconds value and is locked here so callers can
# detect "value was absent" without an Optional[int] (which would
# break the deterministic-hash contract on observation records).
_SLOT_ABSENT_SENTINEL: int = -1


# Stage 25 preserved migration-observation concepts. Each entry is
# (concept_name, source_aliases_tuple). A concept is missing only
# when every alias listed for that concept is absent from the row.
_MIGRATION_INPUT_CONCEPT_ALIASES: tuple[
    tuple[str, tuple[str, ...]], ...
] = (
    ("token_mint", ("token_mint",)),
    ("source_family", ("source_family",)),
    ("source_status", ("source_status",)),
    ("observed_at_utc", ("observed_at_utc",)),
    ("slot", ("slot",)),
    ("block_time", ("block_time",)),
    ("migration_signature", ("migration_signature",)),
    ("migration_pool", ("migration_pool",)),
    ("provider_id", ("provider_id",)),
    ("reason_codes", ("reason_codes",)),
    ("evidence", ("evidence",)),
)


_PRICE_INPUT_CONCEPT_ALIASES: tuple[
    tuple[str, tuple[str, ...]], ...
] = (
    ("token_mint", ("token_mint",)),
    ("source_family", ("source_family",)),
    ("source_status", ("source_status",)),
    ("observed_at_utc", ("observed_at_utc",)),
    ("slot", ("slot",)),
    ("block_time", ("block_time",)),
    ("price", ("price",)),
    ("quote_denomination", ("quote_denomination",)),
    ("provider_id", ("provider_id",)),
    ("reason_codes", ("reason_codes",)),
    ("evidence", ("evidence",)),
)


# ---------------------------------------------------------------------------
# Field-name / value safety
# ---------------------------------------------------------------------------


def _field_name_is_secret_bearing(name: str) -> bool:
    lower = name.lower()
    for forbidden in STAGE25_FORBIDDEN_INPUT_FIELD_SUBSTRINGS:
        if forbidden in lower:
            return True
    return False


def _has_long_hex_run(s: str) -> bool:
    """Return True iff ``s`` contains a run of >=
    ``STAGE25_LONG_HEX_RUN_MIN_LEN`` hex characters (mixed-case).
    """
    run = 0
    for ch in s:
        if ch in _HEX_CHARS:
            run += 1
            if run >= STAGE25_LONG_HEX_RUN_MIN_LEN:
                return True
        else:
            run = 0
    return False


def _string_value_carries_leak_shape(value: str) -> bool:
    lower = value.lower()
    for forbidden in STAGE25_FORBIDDEN_INPUT_VALUE_SUBSTRINGS:
        if forbidden in lower:
            return True
    if _has_long_hex_run(value):
        return True
    return False


def stage25_value_carries_leak_shape(value: object) -> bool:
    """Public Stage 25 secret-shape detector for STRING VALUES.

    Mirrors the input reader's per-value sanitiser so callers that
    bypass the reader can re-run the same scan over user-controllable
    string values before serialising them to disk.

    Returns ``True`` if ``value`` is a string that carries any of:

      * a URL / webhook host substring from
        ``STAGE25_FORBIDDEN_INPUT_VALUE_SUBSTRINGS``;
      * a run of >= ``STAGE25_LONG_HEX_RUN_MIN_LEN`` hex-class
        characters (token / credential shape);
      * an env-style sensitive substring from
        ``STAGE25_FORBIDDEN_INPUT_FIELD_SUBSTRINGS`` embedded in
        the value (e.g. ``"api_key"``, ``"webhook"``,
        ``"password"``).

    Returns ``False`` for non-string values.
    """
    if not isinstance(value, str):
        return False
    if _string_value_carries_leak_shape(value):
        return True
    lower = value.lower()
    for forbidden in STAGE25_FORBIDDEN_INPUT_FIELD_SUBSTRINGS:
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

    Raises ``Stage25InputError`` when any string value carries a
    leak-shape substring or any mapping key carries a forbidden
    field-name substring.
    """
    if isinstance(value, str):
        if _string_value_carries_leak_shape(value):
            raise Stage25InputError(
                f"line {line_index}: field {field_path!r} value carries a "
                "leak-shape substring"
            )
        return
    if isinstance(value, Mapping):
        for key, nested in value.items():
            if not isinstance(key, str):
                raise Stage25InputError(
                    f"line {line_index}: field {field_path!r} has a "
                    "non-string nested key"
                )
            if _field_name_is_secret_bearing(key):
                raise Stage25InputError(
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
        raise Stage25InputError(
            f"input path does not exist: {path.name!r}"
        )
    if path.is_dir():
        raise Stage25InputError(
            f"input path is a directory; expected a file: {path.name!r}"
        )
    if not path.is_file():
        raise Stage25InputError(
            f"input path is not a regular file: {path.name!r}"
        )


def _require_input_kind(input_kind: str) -> None:
    if input_kind not in INPUT_KINDS:
        raise Stage25InputError(
            f"input_kind {input_kind!r} is not a Stage 25 input kind"
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
        raise Stage25InputError(
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
            raise Stage25InputError(
                f"line {line_index}: non-string field name"
            )
        if _field_name_is_secret_bearing(key):
            raise Stage25InputError(
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


def _project_string_optional(
    *,
    row: Mapping[str, object],
    key: str,
    line_index: int,
) -> str:
    raw = row.get(key)
    if raw is None:
        return ""
    if not isinstance(raw, str):
        raise Stage25InputError(
            f"line {line_index}: field {key!r} must be a string when "
            "present"
        )
    return raw


def _project_string_required(
    *,
    row: Mapping[str, object],
    key: str,
    line_index: int,
) -> str:
    raw = row.get(key)
    if raw is None:
        raise Stage25InputError(
            f"line {line_index}: required field {key!r} is absent"
        )
    if not isinstance(raw, str) or raw == "":
        raise Stage25InputError(
            f"line {line_index}: required field {key!r} must be a "
            "non-empty string"
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
        raise Stage25InputError(
            f"line {line_index}: field {key!r} must be an int, not a bool"
        )
    if not isinstance(raw, int):
        raise Stage25InputError(
            f"line {line_index}: field {key!r} must be an int when present"
        )
    return raw


def _project_optional_non_negative_int(
    *,
    row: Mapping[str, object],
    key: str,
    line_index: int,
) -> Optional[int]:
    raw = row.get(key)
    if raw is None:
        return None
    if isinstance(raw, bool):
        raise Stage25InputError(
            f"line {line_index}: field {key!r} must be an int, not a bool"
        )
    if not isinstance(raw, int):
        raise Stage25InputError(
            f"line {line_index}: field {key!r} must be an int when present"
        )
    if raw < 0:
        raise Stage25InputError(
            f"line {line_index}: field {key!r} must be >= 0 when present"
        )
    return raw


def _project_tuple_of_strings_optional(
    *,
    row: Mapping[str, object],
    key: str,
    line_index: int,
) -> tuple[str, ...]:
    raw = row.get(key)
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise Stage25InputError(
            f"line {line_index}: field {key!r} must be a list when present"
        )
    out: list[str] = []
    for index, item in enumerate(raw):
        if not isinstance(item, str) or item == "":
            raise Stage25InputError(
                f"line {line_index}: field {key!r}[{index}] must be a "
                "non-empty string"
            )
        out.append(item)
    return tuple(out)


def _freeze_mapping(value: Mapping[str, object]) -> Mapping[str, object]:
    return MappingProxyType(dict(value))


def _project_evidence(
    *,
    row: Mapping[str, object],
    line_index: int,
) -> Mapping[str, object]:
    raw = row.get("evidence")
    if raw is None:
        return MappingProxyType({})
    if not isinstance(raw, Mapping):
        raise Stage25InputError(
            f"line {line_index}: field 'evidence' must be an object when "
            "present"
        )
    return _freeze_mapping(raw)


def _project_string_with_default(
    *,
    row: Mapping[str, object],
    key: str,
    line_index: int,
    default: str,
) -> str:
    raw = row.get(key)
    if raw is None:
        return default
    if not isinstance(raw, str) or raw == "":
        raise Stage25InputError(
            f"line {line_index}: field {key!r} must be a non-empty string "
            "when present"
        )
    return raw


def _compute_missing_concepts(
    *,
    row: Mapping[str, object],
    concept_aliases: tuple[tuple[str, tuple[str, ...]], ...],
) -> tuple[str, ...]:
    missing: list[str] = []
    for concept_name, aliases in concept_aliases:
        if not any(alias in row for alias in aliases):
            missing.append(concept_name)
    return tuple(sorted(missing))


# ---------------------------------------------------------------------------
# Per-kind row builders
# ---------------------------------------------------------------------------


def _build_migration_observation_from_row(
    *,
    row: Mapping[str, object],
    line_index: int,
) -> Stage25MigrationObservation:
    token_mint = _project_string_required(
        row=row, key="token_mint", line_index=line_index
    )
    provider_id = _project_string_required(
        row=row, key="provider_id", line_index=line_index
    )
    source_family = _project_string_with_default(
        row=row,
        key="source_family",
        line_index=line_index,
        default=SOURCE_FAMILY_UNKNOWN_SOURCE,
    )
    source_status = _project_string_with_default(
        row=row,
        key="source_status",
        line_index=line_index,
        default=SOURCE_STATUS_ABSENT,
    )
    observed_at_utc = _project_string_optional(
        row=row, key="observed_at_utc", line_index=line_index
    )
    slot = _project_int_with_sentinel(
        row=row, key="slot", line_index=line_index
    )
    block_time = _project_int_with_sentinel(
        row=row, key="block_time", line_index=line_index
    )
    migration_signature = _project_string_optional(
        row=row, key="migration_signature", line_index=line_index
    )
    migration_pool = _project_string_optional(
        row=row, key="migration_pool", line_index=line_index
    )
    reason_codes = _project_tuple_of_strings_optional(
        row=row, key="reason_codes", line_index=line_index
    )
    evidence = _project_evidence(row=row, line_index=line_index)
    missing_fields = _compute_missing_concepts(
        row=row, concept_aliases=_MIGRATION_INPUT_CONCEPT_ALIASES
    )

    try:
        return build_migration_observation(
            token_mint=token_mint,
            source_family=source_family,
            source_status=source_status,
            observed_at_utc=observed_at_utc,
            slot=slot,
            block_time=block_time,
            migration_signature=migration_signature,
            migration_pool=migration_pool,
            provider_id=provider_id,
            reason_codes=reason_codes,
            evidence=evidence,
            input_missing_fields=missing_fields,
        )
    except Stage25ContractError as exc:
        raise Stage25InputError(
            f"line {line_index}: migration observation rejected by model "
            f"validator: {exc}"
        ) from exc


def _build_price_observation_from_row(
    *,
    row: Mapping[str, object],
    line_index: int,
) -> Stage25PriceObservation:
    token_mint = _project_string_required(
        row=row, key="token_mint", line_index=line_index
    )
    provider_id = _project_string_required(
        row=row, key="provider_id", line_index=line_index
    )
    source_family = _project_string_with_default(
        row=row,
        key="source_family",
        line_index=line_index,
        default=SOURCE_FAMILY_UNKNOWN_SOURCE,
    )
    source_status = _project_string_with_default(
        row=row,
        key="source_status",
        line_index=line_index,
        default=SOURCE_STATUS_ABSENT,
    )
    observed_at_utc = _project_string_optional(
        row=row, key="observed_at_utc", line_index=line_index
    )
    slot = _project_int_with_sentinel(
        row=row, key="slot", line_index=line_index
    )
    block_time = _project_int_with_sentinel(
        row=row, key="block_time", line_index=line_index
    )
    price = _project_optional_non_negative_int(
        row=row, key="price", line_index=line_index
    )
    quote_denomination = _project_string_with_default(
        row=row,
        key="quote_denomination",
        line_index=line_index,
        default=QUOTE_DENOMINATION_UNKNOWN_QUOTE,
    )
    reason_codes = _project_tuple_of_strings_optional(
        row=row, key="reason_codes", line_index=line_index
    )
    evidence = _project_evidence(row=row, line_index=line_index)
    missing_fields = _compute_missing_concepts(
        row=row, concept_aliases=_PRICE_INPUT_CONCEPT_ALIASES
    )

    try:
        return build_price_observation(
            token_mint=token_mint,
            source_family=source_family,
            source_status=source_status,
            observed_at_utc=observed_at_utc,
            slot=slot,
            block_time=block_time,
            price=price,
            quote_denomination=quote_denomination,
            provider_id=provider_id,
            reason_codes=reason_codes,
            evidence=evidence,
            input_missing_fields=missing_fields,
        )
    except Stage25ContractError as exc:
        raise Stage25InputError(
            f"line {line_index}: price observation rejected by model "
            f"validator: {exc}"
        ) from exc


# ---------------------------------------------------------------------------
# Public entrypoints
# ---------------------------------------------------------------------------


def read_stage25_migration_observations_jsonl(
    *,
    path: Path,
    input_kind: str,
) -> tuple[Stage25MigrationObservation, ...]:
    """Read a Stage 25-shaped migration-observation JSONL artifact.

    Emits one ``Stage25MigrationObservation`` per non-blank JSONL
    line in file order.

    Parameters:

      * ``path``       -- operator-supplied ``pathlib.Path`` to the
                          JSONL file. Required. Missing /
                          directory / non-regular-file paths each
                          raise ``Stage25InputError``.
      * ``input_kind`` -- one of ``MIGRATION_OBSERVATION_INPUT_KINDS``.
                          Any other kind raises ``Stage25InputError``.

    Returns a tuple of ``Stage25MigrationObservation`` records in
    file order. The returned tuple may be empty for an empty file.
    """
    _require_input_kind(input_kind)
    if input_kind not in MIGRATION_OBSERVATION_INPUT_KINDS:
        raise Stage25InputError(
            f"input_kind {input_kind!r} is not a Stage 25 migration "
            "observation input kind"
        )
    _require_path_is_existing_file(path)
    raw = path.read_text(encoding="utf-8")
    return tuple(_iter_migration_observations(raw=raw))


def read_stage25_price_observations_jsonl(
    *,
    path: Path,
    input_kind: str,
) -> tuple[Stage25PriceObservation, ...]:
    """Read a Stage 25-shaped price-observation JSONL artifact.

    Emits one ``Stage25PriceObservation`` per non-blank JSONL line
    in file order.

    Parameters:

      * ``path``       -- operator-supplied ``pathlib.Path`` to the
                          JSONL file.
      * ``input_kind`` -- one of ``PRICE_OBSERVATION_INPUT_KINDS``.

    Returns a tuple of ``Stage25PriceObservation`` records in file
    order. The returned tuple may be empty for an empty file.
    """
    _require_input_kind(input_kind)
    if input_kind not in PRICE_OBSERVATION_INPUT_KINDS:
        raise Stage25InputError(
            f"input_kind {input_kind!r} is not a Stage 25 price "
            "observation input kind"
        )
    _require_path_is_existing_file(path)
    raw = path.read_text(encoding="utf-8")
    return tuple(_iter_price_observations(raw=raw))


def stage25_input_default_schema_version() -> str:
    """Return the locked Stage 25 default input schema version.

    Convenience for callers that want to record the schema version
    they used to read inputs without re-importing the constants
    module directly.
    """
    return DEFAULT_SCHEMA_VERSION


def _iter_migration_observations(
    *,
    raw: str,
) -> list[Stage25MigrationObservation]:
    out: list[Stage25MigrationObservation] = []
    stripped = raw.rstrip("\n")
    if stripped == "":
        return out
    lines = stripped.split("\n")
    for index, line in enumerate(lines, start=1):
        if line == "":
            raise Stage25InputError(
                f"line {index}: intra-file blank line"
            )
        try:
            parsed = json.loads(line)
        except ValueError as exc:
            raise Stage25InputError(
                f"line {index}: malformed JSON"
            ) from exc
        row = _require_row_is_mapping(row=parsed, line_index=index)
        _scan_row_top_level_field_names(row=row, line_index=index)
        _scan_row_values_recursively(row=row, line_index=index)
        out.append(
            _build_migration_observation_from_row(
                row=row, line_index=index
            )
        )
    return out


def _iter_price_observations(
    *,
    raw: str,
) -> list[Stage25PriceObservation]:
    out: list[Stage25PriceObservation] = []
    stripped = raw.rstrip("\n")
    if stripped == "":
        return out
    lines = stripped.split("\n")
    for index, line in enumerate(lines, start=1):
        if line == "":
            raise Stage25InputError(
                f"line {index}: intra-file blank line"
            )
        try:
            parsed = json.loads(line)
        except ValueError as exc:
            raise Stage25InputError(
                f"line {index}: malformed JSON"
            ) from exc
        row = _require_row_is_mapping(row=parsed, line_index=index)
        _scan_row_top_level_field_names(row=row, line_index=index)
        _scan_row_values_recursively(row=row, line_index=index)
        out.append(
            _build_price_observation_from_row(
                row=row, line_index=index
            )
        )
    return out


__all__ = [
    "read_stage25_migration_observations_jsonl",
    "read_stage25_price_observations_jsonl",
    "stage25_input_default_schema_version",
    "stage25_value_carries_leak_shape",
]

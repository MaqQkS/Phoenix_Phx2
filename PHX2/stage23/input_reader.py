"""Stage 23 input reader (foundation only at 23.1).

Reads Stage 22-shaped JSONL artifacts from operator-supplied
paths and projects each row into an immutable
``Stage23FilterInput``.

Supported input shapes for 23.1:

  * ``raw_capture.jsonl``-style files (Stage 22.3 raw capture
    writer output -- ``normalized_event`` / ``malformed_event`` /
    ``provider_failure`` lines). 23.1 projects only the
    ``normalized_event`` lines.
  * ``dedupe.jsonl``-style files (Stage 22.2 dedupe ledger
    output -- ``seen`` / ``dispatched`` lines). 23.1 projects
    each line as a thin input record (no payload summary).
  * Small synthetic JSONL fixtures with the same field
    vocabulary as the Stage 22 records (for offline filter
    tests in Stage 23.2+).

Reader behavior (locked at 23.1):

  * No hardcoded path. The reader's entrypoints take a
    caller-supplied ``pathlib.Path``.
  * No network calls. No env reads. No repo writes. No mutation
    of input artifacts.
  * Deterministic row ordering: rows are emitted in file order
    (first line first, last line last). Blank trailing lines
    are ignored; intra-file blank lines raise
    ``Stage23InputError``.
  * Missing file: ``Stage23InputError``.
  * Path is a directory: ``Stage23InputError``.
  * Malformed JSON / non-object line: ``Stage23InputError``.
  * Forbidden field-name substring on the row: ``Stage23InputError``.
  * Forbidden value substring on a preserved field's value:
    ``Stage23InputError``.
  * Optional primitives absent on the upstream row are NOT
    fabricated. The reader populates ``Stage23FilterInput.missing_fields``
    with the absent preserved-field names so downstream filters
    can reason about completeness.

This module imports only stdlib (``json`` / ``pathlib``) plus
the Stage 23 constants / errors / models. It does NOT import
Stage 21 or Stage 22 modules; the Stage 22 artifact shape is
read by field-name only. It does NOT import any network / RPC
/ messaging / DB / scheduler / secrets-management library, does
NOT read the process environment, does NOT define a CLI surface,
and contains no top-level I/O.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import MappingProxyType
from typing import Mapping

from PHX2.stage23.constants import (
    INPUT_KIND_DEDUPE,
    INPUT_KIND_RAW_CAPTURE,
    INPUT_KIND_SYNTHETIC,
    INPUT_KINDS,
    INPUT_PRESERVED_FIELDS,
    STAGE23_FORBIDDEN_INPUT_FIELD_SUBSTRINGS,
    STAGE23_FORBIDDEN_INPUT_VALUE_SUBSTRINGS,
    STAGE23_LONG_HEX_RUN_MIN_LEN,
    STAGE23_LONG_TOKENISH_MIN_LEN,
)
from PHX2.stage23.errors import Stage23InputError
from PHX2.stage23.models import Stage23FilterInput


# ---------------------------------------------------------------------------
# Module-private shape constants
# ---------------------------------------------------------------------------


_HEX_CHARS: str = "0123456789abcdefABCDEF"
_TOKEN_SHAPE_EXTRA_CHARS: str = "+=_-"

# Sentinel value the reader uses for the ``slot`` field of a
# ``Stage23FilterInput`` when the upstream row did not carry a
# slot. ``-1`` is invalid as a real slot value and is locked
# here so callers can detect "slot was absent" without an
# Optional[int] (which would break the deterministic-hash
# contract on Stage23FilterInput).
_SLOT_ABSENT_SENTINEL: int = -1


# ---------------------------------------------------------------------------
# Leak shape detectors
# ---------------------------------------------------------------------------


def _looks_like_token_payload(s: str) -> bool:
    """Return True iff s has the mixed-content shape of a secret token.

    Mirrors the ``_looks_like_a_token_payload`` heuristic in
    the Stage 22 capture writer's sanitiser: at least one ASCII
    letter AND at least one digit, with alphanumeric content
    covering >= 80% of the string.
    """
    if s == "":
        return False
    has_letter = False
    has_digit = False
    alphanumeric = 0
    for ch in s:
        if ch.isalpha():
            has_letter = True
        if ch.isdigit():
            has_digit = True
        if ch.isalnum():
            alphanumeric += 1
    if not (has_letter and has_digit):
        return False
    return alphanumeric / len(s) >= 0.8


def _has_long_hex_run(s: str) -> bool:
    """Return True iff s contains a run of >= STAGE23_LONG_HEX_RUN_MIN_LEN
    hex characters (mixed-case).
    """
    run = 0
    for ch in s:
        if ch in _HEX_CHARS:
            run += 1
            if run >= STAGE23_LONG_HEX_RUN_MIN_LEN:
                return True
        else:
            run = 0
    return False


def _has_long_tokenish_run(s: str) -> bool:
    """Return True iff s contains a maximal run of token-shape characters
    of length >= STAGE23_LONG_TOKENISH_MIN_LEN that passes the
    mixed-content density heuristic.
    """
    candidate = ""
    for ch in s:
        if ch.isalnum() or ch in _TOKEN_SHAPE_EXTRA_CHARS:
            candidate += ch
        else:
            if (
                len(candidate) >= STAGE23_LONG_TOKENISH_MIN_LEN
                and _looks_like_token_payload(candidate)
            ):
                return True
            candidate = ""
    if (
        len(candidate) >= STAGE23_LONG_TOKENISH_MIN_LEN
        and _looks_like_token_payload(candidate)
    ):
        return True
    return False


# ---------------------------------------------------------------------------
# Field-name / value safety
# ---------------------------------------------------------------------------


def _field_name_is_secret_bearing(name: str) -> bool:
    lower = name.lower()
    for forbidden in STAGE23_FORBIDDEN_INPUT_FIELD_SUBSTRINGS:
        if forbidden in lower:
            return True
    return False


def _string_value_carries_leak_shape(value: str) -> bool:
    lower = value.lower()
    for forbidden in STAGE23_FORBIDDEN_INPUT_VALUE_SUBSTRINGS:
        if forbidden in lower:
            return True
    if _has_long_hex_run(value):
        return True
    if _has_long_tokenish_run(value):
        return True
    return False


def _is_safe_scalar_value(value: object) -> bool:
    """Return True iff ``value`` is a safe scalar for a preserved field
    (after string-value leak-shape sanitisation has already passed).

    Allowed: ``str`` / ``int`` (excluding ``bool``) / ``float`` /
    ``bool`` / ``None``. Mappings are handled separately for
    ``payload_summary``.
    """
    if isinstance(value, bool):
        return True
    if isinstance(value, int):
        return True
    if isinstance(value, float):
        return True
    if value is None:
        return True
    if isinstance(value, str):
        return True
    return False


# ---------------------------------------------------------------------------
# Path / file boundary
# ---------------------------------------------------------------------------


def _require_path_is_existing_file(path: Path) -> None:
    if not path.exists():
        raise Stage23InputError(
            f"input path does not exist: {path.name!r}"
        )
    if path.is_dir():
        raise Stage23InputError(
            f"input path is a directory; expected a file: {path.name!r}"
        )
    if not path.is_file():
        raise Stage23InputError(
            f"input path is not a regular file: {path.name!r}"
        )


def _require_input_kind(input_kind: str) -> None:
    if input_kind not in INPUT_KINDS:
        raise Stage23InputError(
            f"input_kind {input_kind!r} is not a Stage 23 input kind"
        )


# ---------------------------------------------------------------------------
# Row-level projection
# ---------------------------------------------------------------------------


def _validate_row_shape_and_safety(
    *,
    row: object,
    line_index: int,
) -> Mapping[str, object]:
    """Validate that ``row`` is a JSON object whose field names are not
    secret-bearing and whose string values do not carry leak shapes.

    Returns the row as a mapping (a plain dict view of the
    parsed JSON object). Raises ``Stage23InputError`` on any
    violation.
    """
    if not isinstance(row, dict):
        raise Stage23InputError(
            f"line {line_index}: not a JSON object"
        )
    for key in row.keys():
        if not isinstance(key, str):
            raise Stage23InputError(
                f"line {line_index}: non-string field name"
            )
        if _field_name_is_secret_bearing(key):
            raise Stage23InputError(
                f"line {line_index}: forbidden secret-bearing field "
                f"name {key!r}"
            )
    return row


def _project_preserved_fields(
    *,
    row: Mapping[str, object],
    line_index: int,
) -> tuple[dict[str, object], tuple[str, ...]]:
    """Project the preserved-field subset out of ``row``.

    Returns ``(values, missing_fields)`` where ``values`` is a
    plain dict containing only the preserved fields the row
    carries with safe scalar values, and ``missing_fields`` is a
    sorted tuple of CONCEPT names absent from the row. A concept
    backed by multiple source field aliases (e.g.
    ``observed_at_utc`` <- ``observed_at_utc`` / ``received_at_utc``)
    is marked missing only when EVERY alias is absent; mirroring
    the Stage 23.0 design rule that an upstream artifact carrying
    a fallback field counts as a present concept.

    Raises ``Stage23InputError`` for preserved-field values that
    are unsafe scalars, unsupported types, or carry leak shapes.
    """
    values: dict[str, object] = {}
    for field in INPUT_PRESERVED_FIELDS:
        if field not in row:
            continue
        value = row[field]
        if field == "payload_summary":
            if not isinstance(value, Mapping):
                raise Stage23InputError(
                    f"line {line_index}: payload_summary must be a mapping"
                )
            safe_payload = _project_payload_summary(
                payload=value,
                line_index=line_index,
            )
            values[field] = safe_payload
            continue
        if not _is_safe_scalar_value(value):
            raise Stage23InputError(
                f"line {line_index}: preserved field {field!r} has "
                f"unsupported value type {type(value).__name__}"
            )
        if isinstance(value, str) and _string_value_carries_leak_shape(value):
            raise Stage23InputError(
                f"line {line_index}: preserved field {field!r} value "
                "carries a leak-shape substring"
            )
        values[field] = value
    missing = _compute_missing_concepts(values=values)
    return values, missing


# Concept-level missing-fields tracking. Each concept is keyed by
# its canonical name; the tuple of source aliases lists the
# upstream-artifact field names the reader will accept as
# evidence the concept is present.
_INPUT_CONCEPT_ALIASES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("provider_id", ("provider_id",)),
    ("event_id", ("event_id",)),
    ("captured_event_id", ("captured_event_id",)),
    ("token_mint", ("token_mint", "mint")),
    ("slot", ("slot",)),
    ("signature", ("signature",)),
    ("observed_at_utc", ("observed_at_utc", "received_at_utc")),
    ("payload_summary", ("payload_summary",)),
)


def _compute_missing_concepts(
    *,
    values: Mapping[str, object],
) -> tuple[str, ...]:
    """Return the sorted tuple of concept names absent from ``values``.

    A concept is absent only when EVERY alias listed for that
    concept in ``_INPUT_CONCEPT_ALIASES`` is missing from
    ``values``.
    """
    missing: list[str] = []
    for concept_name, aliases in _INPUT_CONCEPT_ALIASES:
        if not any(alias in values for alias in aliases):
            missing.append(concept_name)
    return tuple(sorted(missing))


def _project_payload_summary(
    *,
    payload: Mapping[str, object],
    line_index: int,
) -> Mapping[str, object]:
    """Validate and project a payload_summary mapping.

    The reader does NOT re-validate every Stage 22 sanitiser rule
    (the Stage 22.3 writer already enforced those at write time).
    The reader DOES re-validate the redaction rules: forbidden
    field-name substrings, forbidden URL-shape values, long hex /
    token-shape runs. This is the second line of defense behind
    the Stage 22 writer.

    Returns a frozen ``MappingProxyType`` view over a copy of the
    payload's flat structure. Nested mappings are rejected
    (payload_summary must remain flat at the Stage 23 ingest
    boundary).
    """
    out: dict[str, object] = {}
    for key, value in payload.items():
        if not isinstance(key, str):
            raise Stage23InputError(
                f"line {line_index}: payload_summary key is not a string"
            )
        if _field_name_is_secret_bearing(key):
            raise Stage23InputError(
                f"line {line_index}: payload_summary key {key!r} carries "
                "a forbidden secret-bearing substring"
            )
        if not _is_safe_scalar_value(value):
            raise Stage23InputError(
                f"line {line_index}: payload_summary value at key {key!r} "
                f"has unsupported type {type(value).__name__}"
            )
        if isinstance(value, str) and _string_value_carries_leak_shape(value):
            raise Stage23InputError(
                f"line {line_index}: payload_summary value at key {key!r} "
                "carries a leak-shape substring"
            )
        out[key] = value
    return MappingProxyType(out)


def _build_filter_input_from_values(
    *,
    values: Mapping[str, object],
    missing_fields: tuple[str, ...],
) -> Stage23FilterInput:
    """Build a ``Stage23FilterInput`` from a projected-values mapping.

    Optional primitives absent in the source row produce empty
    strings (for string fields) or the slot-absent sentinel
    (``_SLOT_ABSENT_SENTINEL``) for the integer field.
    ``missing_fields`` is preserved so downstream filters can
    distinguish "value was an explicit empty string" from "value
    was absent from the upstream artifact".
    """
    raw_slot = values.get("slot")
    if raw_slot is None:
        slot_value: int = _SLOT_ABSENT_SENTINEL
    elif isinstance(raw_slot, bool):
        slot_value = _SLOT_ABSENT_SENTINEL
    elif isinstance(raw_slot, int):
        slot_value = raw_slot
    else:
        slot_value = _SLOT_ABSENT_SENTINEL

    payload = values.get("payload_summary")
    if not isinstance(payload, Mapping):
        payload = MappingProxyType({})

    token_mint = _string_or_empty(values, "token_mint", "mint")
    provider_id = _string_or_empty(values, "provider_id")
    event_id = _string_or_empty(values, "event_id")
    captured_event_id = _string_or_empty(values, "captured_event_id")
    observed_at_utc = _string_or_empty(
        values, "observed_at_utc", "received_at_utc"
    )
    signature = _string_or_empty(values, "signature")

    return Stage23FilterInput(
        token_mint=token_mint,
        provider_id=provider_id,
        event_id=event_id,
        captured_event_id=captured_event_id,
        observed_at_utc=observed_at_utc,
        slot=slot_value,
        signature=signature,
        payload_summary=payload,
        missing_fields=missing_fields,
    )


def _string_or_empty(
    values: Mapping[str, object],
    primary: str,
    fallback: str = "",
) -> str:
    """Return the string value at ``primary`` (or ``fallback`` if absent),
    otherwise the empty string. Non-string values yield the empty
    string -- the upstream shape validator already rejected unsafe
    types; this helper only collapses the primary / fallback
    lookup to a string.
    """
    candidate = values.get(primary)
    if isinstance(candidate, str):
        return candidate
    if fallback:
        candidate = values.get(fallback)
        if isinstance(candidate, str):
            return candidate
    return ""


# ---------------------------------------------------------------------------
# Public entrypoint
# ---------------------------------------------------------------------------


def read_stage22_jsonl(
    *,
    path: Path,
    input_kind: str,
) -> tuple[Stage23FilterInput, ...]:
    """Read a Stage 22-shaped JSONL artifact and return projected inputs.

    The reader emits one ``Stage23FilterInput`` per non-blank
    JSONL line in file order. Provider-failure / malformed-event
    lines from a Stage 22.3 capture file are NOT projected as
    Stage 23 inputs (they have no normalized event content);
    Stage 23.1 returns a record only when the row carries at
    least the ``provider_id`` field (the minimum sanity check
    for a Stage 22-shaped row).

    Parameters:

      * ``path``       -- operator-supplied ``pathlib.Path`` to a
                          JSONL file. Required. Missing path,
                          directory path, and non-regular-file
                          path each raise ``Stage23InputError``.
      * ``input_kind`` -- one of ``INPUT_KINDS``. The reader uses
                          this to discriminate provider-failure
                          and malformed-event lines from
                          ``raw_capture.jsonl``-style files vs
                          ``dedupe.jsonl``-style files.

    Returns a tuple of ``Stage23FilterInput`` records in file
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
) -> list[Stage23FilterInput]:
    out: list[Stage23FilterInput] = []
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
            raise Stage23InputError(
                f"line {index}: intra-file blank line"
            )
        try:
            parsed = json.loads(line)
        except ValueError as exc:
            raise Stage23InputError(
                f"line {index}: malformed JSON"
            ) from exc
        row = _validate_row_shape_and_safety(
            row=parsed,
            line_index=index,
        )
        if not _row_is_projectable(row=row, input_kind=input_kind):
            continue
        values, missing_fields = _project_preserved_fields(
            row=row,
            line_index=index,
        )
        if "provider_id" not in values:
            # No usable provenance; the upstream row is too thin
            # to be a Stage 23 input. The reader silently skips
            # rather than raising because Stage 22.3 raw-capture
            # files legitimately mix record types; only the
            # ``normalized_event`` family carries provider_id +
            # mint + event content.
            continue
        out.append(
            _build_filter_input_from_values(
                values=values,
                missing_fields=missing_fields,
            )
        )
    return out


def _row_is_projectable(
    *,
    row: Mapping[str, object],
    input_kind: str,
) -> bool:
    """Return True iff ``row`` is a Stage 23-projectable line for the
    given ``input_kind``.

    For ``raw_capture`` files, only ``normalized_event`` lines
    are projected; ``provider_failure`` and ``malformed_event``
    lines are skipped.
    For ``dedupe`` files, only ``seen`` lines are projected;
    ``dispatched`` lines are skipped.
    For ``synthetic`` files, every row that passes shape
    validation is projected.
    """
    record_type = row.get("record_type")
    if input_kind == INPUT_KIND_RAW_CAPTURE:
        if record_type is None:
            return True
        return record_type == "normalized_event"
    if input_kind == INPUT_KIND_DEDUPE:
        if record_type is None:
            return True
        return record_type == "seen"
    if input_kind == INPUT_KIND_SYNTHETIC:
        return True
    # Unreachable: _require_input_kind already validated.
    return False


__all__ = [
    "read_stage22_jsonl",
]

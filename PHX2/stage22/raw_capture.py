"""Stage 22.3 raw event / log capture writer implementations.

Two implementations of the Stage 22.1 ``RawCaptureWriter``
Protocol:

  * ``InMemoryRawCaptureWriter`` -- no I/O, deterministic. The
    future bounded runner's offline unit suite drives this
    implementation directly. Records are kept in chronological
    order and exposed via immutable read-only snapshot accessors.
  * ``JsonlRawCaptureWriter``    -- append-only JSONL capture
    writer with cross-run replay validation. Operator supplies a
    ``pathlib.Path``; the parent directory must already exist;
    the writer never calls ``mkdir`` / ``unlink`` / ``rename`` /
    ``replace`` / ``glob`` / ``iterdir`` / ``rmdir`` and never
    imports ``shutil``.

Three record families, discriminated by a ``record_type`` field
in one append-only JSONL stream:

  * ``normalized_event``   -- sanitized projection of an
                              ``IngestEventEnvelope``.
  * ``malformed_event``    -- sanitized projection of a
                              ``MalformedEventRecord``.
  * ``provider_failure``   -- sanitized projection of a
                              ``ProviderFailureRecord``.

Both writers share the same validation rules via the
module-private helpers. Every contract violation -- bad record
shape, unsafe payload_summary key or value, write failure,
malformed replay line -- raises ``Stage22CaptureContractError``.
No silent redaction; no soft-fail outcome token; the second line
of defense rejects rather than sanitising in place.

The capture writer is the post-decision evidence channel:

  * The bounded runner (future Stage 22.5) makes a send decision
    based on the dedupe ledger outcome, then captures evidence
    from the event / failure / decode outcome.
  * A capture write failure surfaces as an exception; the runner
    is responsible for propagating or aborting (unlike the
    Stage 22.2 ledger which returns a soft-fail token because
    ledger output GATES the send decision).
  * No timestamp is ever generated inside this module. Every
    timestamp on the wire comes from the caller-supplied
    envelope or record (``received_at_utc`` / ``failed_at_utc``
    / ``observed_at_utc``).

Replay semantics for the JSONL writer:

  * Missing file with existing parent -> empty state, ready to
    write.
  * Missing parent directory -> ``Stage22CaptureContractError``.
  * Empty existing file -> empty state.
  * Path traversal segment (``..``) -> rejected at construction.
  * Path exists but is not a regular file -> rejected.
  * Malformed JSON line / record with a field set that is not
    exactly the per-record-type required tuple / non-string or
    non-int field value / unknown schema_version / unknown
    record_type / empty required non-empty field / closed-set
    violation / unsafe payload_summary content / blank line ->
    ``Stage22CaptureContractError``.

Single-writer assumption: the operator is responsible for not
pointing two processes at the same path concurrently.

This module imports only stdlib (``json`` / ``os`` /
``pathlib``) plus the Stage 22 contracts. It does NOT import
any network / RPC / messaging / DB / scheduler / secrets
library, does NOT read the process environment, does NOT
define a CLI surface, does NOT import Stage 21 directly (the
``NormalizedLiveEvent`` typing arrives transitively via
``IngestEventEnvelope.event``), and contains no top-level I/O.
"""

from __future__ import annotations

import json
import math
import os
from collections.abc import Mapping
from pathlib import Path

from PHX2.stage22.constants import (
    CAPTURE_FORBIDDEN_SECRET_KEY_SUBSTRINGS,
    CAPTURE_FORBIDDEN_URL_SUBSTRINGS,
    CAPTURE_LONG_HEX_RUN_MIN_LEN,
    CAPTURE_LONG_TOKENISH_MIN_LEN,
    CAPTURE_MALFORMED_EVENT_REQUIRED_FIELDS,
    CAPTURE_MALFORMED_EVENT_REQUIRED_NON_EMPTY_STRING_FIELDS,
    CAPTURE_NORMALIZED_EVENT_REQUIRED_FIELDS,
    CAPTURE_NORMALIZED_EVENT_REQUIRED_INT_FIELDS,
    CAPTURE_NORMALIZED_EVENT_REQUIRED_NON_EMPTY_STRING_FIELDS,
    CAPTURE_PAYLOAD_SUMMARY_MAX_KEY_LEN,
    CAPTURE_PAYLOAD_SUMMARY_MAX_KEYS,
    CAPTURE_PAYLOAD_SUMMARY_MAX_STRING_LEN,
    CAPTURE_PROVIDER_FAILURE_REQUIRED_FIELDS,
    CAPTURE_PROVIDER_FAILURE_REQUIRED_INT_FIELDS,
    CAPTURE_PROVIDER_FAILURE_REQUIRED_NON_EMPTY_STRING_FIELDS,
    CAPTURE_RECORD_TYPE_MALFORMED_EVENT,
    CAPTURE_RECORD_TYPE_NORMALIZED_EVENT,
    CAPTURE_RECORD_TYPE_PROVIDER_FAILURE,
    CAPTURE_RECORD_TYPES,
    MALFORMED_EVENT_REASONS,
    PROVIDER_FAILURE_LABELS,
    STAGE22_CAPTURE_RECORD_SCHEMA_VERSION,
    STATUS_CLASS_SUCCESS,
    STATUS_CLASSES,
    UPSTREAM_ERROR_TYPES,
)
from PHX2.stage22.errors import Stage22CaptureContractError
from PHX2.stage22.ingest_contracts import (
    IngestEventEnvelope,
    MalformedEventRecord,
    ProviderFailureRecord,
)


# ---------------------------------------------------------------------------
# Module-private constants
# ---------------------------------------------------------------------------
#
# Inlined-shape constants for the sanitizer helpers. Kept as
# plain strings so the module has no top-level frozenset / set
# constructor calls.


_HEX_CHARS: str = "0123456789abcdefABCDEF"
_TOKEN_SHAPE_EXTRA_CHARS: str = "+=_-"


# Mapping from record_type to the locked required-field tuple.
# Used by the replay decoder to look up the expected field set
# in O(1) without a long if / elif chain.

_REQUIRED_FIELDS_BY_RECORD_TYPE: dict[str, tuple[str, ...]] = {
    CAPTURE_RECORD_TYPE_NORMALIZED_EVENT: (
        CAPTURE_NORMALIZED_EVENT_REQUIRED_FIELDS
    ),
    CAPTURE_RECORD_TYPE_MALFORMED_EVENT: (
        CAPTURE_MALFORMED_EVENT_REQUIRED_FIELDS
    ),
    CAPTURE_RECORD_TYPE_PROVIDER_FAILURE: (
        CAPTURE_PROVIDER_FAILURE_REQUIRED_FIELDS
    ),
}


# ---------------------------------------------------------------------------
# Strict-int helper
# ---------------------------------------------------------------------------


def _is_strict_int(value: object) -> bool:
    """Return True iff value is an int and NOT a bool.

    bool is a subclass of int in Python; treating True / False
    as a legitimate slot or provider_attempt_index would be a
    silent type coercion. This helper enforces the strict-int
    rule used on every top-level int field in a capture record.
    """
    return isinstance(value, int) and not isinstance(value, bool)


# ---------------------------------------------------------------------------
# Long-token leak shape detectors
# ---------------------------------------------------------------------------


def _looks_like_token_payload(s: str) -> bool:
    """Return True iff s has the mixed-content shape of a secret token.

    Mirrors the ``_looks_like_a_token_payload`` heuristic in
    ``test_no_secret_leaks.py``: at least one letter AND at
    least one digit, with alphanumeric content covering >= 80%
    of the string. Pure-letter runs (identifier names) and
    pure-punctuation runs do not pass.
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
    """Return True iff s contains a run of >= CAPTURE_LONG_HEX_RUN_MIN_LEN
    hex characters (mixed-case).
    """
    run = 0
    for ch in s:
        if ch in _HEX_CHARS:
            run += 1
            if run >= CAPTURE_LONG_HEX_RUN_MIN_LEN:
                return True
        else:
            run = 0
    return False


def _has_long_tokenish_run(s: str) -> bool:
    """Return True iff s contains a maximal run of token-shape characters
    of length >= CAPTURE_LONG_TOKENISH_MIN_LEN that passes the
    mixed-content density heuristic.
    """
    candidate = ""
    for ch in s:
        if ch.isalnum() or ch in _TOKEN_SHAPE_EXTRA_CHARS:
            candidate += ch
        else:
            if (
                len(candidate) >= CAPTURE_LONG_TOKENISH_MIN_LEN
                and _looks_like_token_payload(candidate)
            ):
                return True
            candidate = ""
    if (
        len(candidate) >= CAPTURE_LONG_TOKENISH_MIN_LEN
        and _looks_like_token_payload(candidate)
    ):
        return True
    return False


# ---------------------------------------------------------------------------
# Payload_summary sanitiser
# ---------------------------------------------------------------------------


def _validate_payload_summary_key(key: object) -> str:
    """Validate a single payload_summary key or raise.

    Required shape:

      * non-empty string
      * length <= CAPTURE_PAYLOAD_SUMMARY_MAX_KEY_LEN
      * first character lowercase ASCII letter
      * remaining characters lowercase ASCII letter / digit / ``_``
      * no forbidden secret-bearing substring (case-insensitive)
    """
    if not isinstance(key, str):
        raise Stage22CaptureContractError(
            "payload_summary key is not a string"
        )
    if key == "":
        raise Stage22CaptureContractError(
            "payload_summary key is empty"
        )
    if len(key) > CAPTURE_PAYLOAD_SUMMARY_MAX_KEY_LEN:
        raise Stage22CaptureContractError(
            "payload_summary key exceeds max length"
        )
    first = key[0]
    if not (first.isalpha() and first.islower() and first.isascii()):
        raise Stage22CaptureContractError(
            "payload_summary key does not start with a lowercase ASCII "
            "letter"
        )
    for ch in key:
        if not (
            (ch.isalpha() and ch.islower() and ch.isascii())
            or ch.isdigit()
            or ch == "_"
        ):
            raise Stage22CaptureContractError(
                "payload_summary key contains a disallowed character"
            )
    lowered = key.lower()
    for forbidden in CAPTURE_FORBIDDEN_SECRET_KEY_SUBSTRINGS:
        if forbidden in lowered:
            raise Stage22CaptureContractError(
                "payload_summary key contains a forbidden secret-bearing "
                "substring"
            )
    return key


def _validate_payload_summary_value(
    *,
    key: str,
    value: object,
) -> object:
    """Validate a single payload_summary value or raise.

    Allowed value types: str, int, float, bool, None. Any other
    type (bytes, list, tuple, set, dict, Mapping, custom class)
    is rejected -- nested mappings and sequences in particular
    are rejected so payload_summary stays flat.

    Float values must additionally be finite: ``NaN`` /
    ``Infinity`` / ``-Infinity`` are rejected because (a) they
    cannot round-trip through strict JSON and (b) they have no
    legitimate place in a sanitised evidence record.

    String values are additionally rejected for length overflow,
    forbidden URL substrings, long hex runs, and long token-shape
    runs.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise Stage22CaptureContractError(
                f"payload_summary value at key {key!r} is a non-finite "
                "float (NaN or Infinity)"
            )
        return value
    if value is None:
        return value
    if isinstance(value, str):
        if len(value) > CAPTURE_PAYLOAD_SUMMARY_MAX_STRING_LEN:
            raise Stage22CaptureContractError(
                f"payload_summary value at key {key!r} exceeds max length"
            )
        lowered = value.lower()
        for needle in CAPTURE_FORBIDDEN_URL_SUBSTRINGS:
            if needle in lowered:
                raise Stage22CaptureContractError(
                    f"payload_summary value at key {key!r} contains a "
                    "forbidden URL-shape substring"
                )
        if _has_long_hex_run(value):
            raise Stage22CaptureContractError(
                f"payload_summary value at key {key!r} contains a long "
                "hex run"
            )
        if _has_long_tokenish_run(value):
            raise Stage22CaptureContractError(
                f"payload_summary value at key {key!r} contains a long "
                "token-shape run"
            )
        return value
    raise Stage22CaptureContractError(
        f"payload_summary value at key {key!r} has unsupported type "
        f"{type(value).__name__}"
    )


def _validate_payload_summary(value: object) -> dict[str, object]:
    """Validate the whole payload_summary mapping or raise.

    Required shape:

      * a ``Mapping`` (``dict`` or ``MappingProxyType`` --
        Stage 21 freezes payload_summary into ``MappingProxyType``
        via ``normalize_fake_event`` / ``decode_provider_event``;
        the writer accepts either and copies into a plain dict
        internally for serialisation).
      * length <= ``CAPTURE_PAYLOAD_SUMMARY_MAX_KEYS``.
      * every key passes ``_validate_payload_summary_key``.
      * every value passes ``_validate_payload_summary_value``.

    Returns a freshly-built ``dict`` with the validated key /
    value pairs. The original mapping is NOT mutated; even when
    it is a plain dict, the writer builds its own dict so the
    caller's structure remains untouched.
    """
    if not isinstance(value, Mapping):
        raise Stage22CaptureContractError(
            "payload_summary must be a Mapping"
        )
    if len(value) > CAPTURE_PAYLOAD_SUMMARY_MAX_KEYS:
        raise Stage22CaptureContractError(
            "payload_summary exceeds max key count"
        )
    out: dict[str, object] = {}
    for raw_key, raw_value in value.items():
        validated_key = _validate_payload_summary_key(raw_key)
        validated_value = _validate_payload_summary_value(
            key=validated_key,
            value=raw_value,
        )
        out[validated_key] = validated_value
    return out


# ---------------------------------------------------------------------------
# Record builders
# ---------------------------------------------------------------------------


def _build_normalized_event_record(
    *,
    envelope: IngestEventEnvelope,
) -> dict[str, object]:
    """Build a canonical normalized_event JSON record from an envelope.

    Validates every required field, recursively sanitises
    payload_summary, and returns a freshly-built dict. Raises
    ``Stage22CaptureContractError`` on any contract violation.
    """
    event = envelope.event
    key = envelope.ingest_key
    if not isinstance(envelope.received_at_utc, str):
        raise Stage22CaptureContractError(
            "envelope.received_at_utc must be a string"
        )
    if envelope.received_at_utc == "":
        raise Stage22CaptureContractError(
            "envelope.received_at_utc must be non-empty"
        )
    if not _is_strict_int(envelope.provider_attempt_index):
        raise Stage22CaptureContractError(
            "envelope.provider_attempt_index must be a strict int "
            "(bool is not accepted)"
        )
    if envelope.provider_attempt_index < 0:
        raise Stage22CaptureContractError(
            "envelope.provider_attempt_index must be >= 0"
        )
    if not _is_strict_int(event.slot):
        raise Stage22CaptureContractError(
            "event.slot must be a strict int (bool is not accepted)"
        )
    if event.slot < 0:
        raise Stage22CaptureContractError(
            "event.slot must be >= 0"
        )
    string_fields: dict[str, object] = {
        "provider_id": key.provider_id,
        "chain": key.chain,
        "event_id": key.event_id,
        "raw_event_hash": key.raw_event_hash,
        "event_type": event.event_type,
        "source_kind": event.source_kind,
        "mint": event.mint,
        "signature": event.signature,
    }
    for field_name, field_value in string_fields.items():
        if not isinstance(field_value, str):
            raise Stage22CaptureContractError(
                f"normalized_event field {field_name!r} must be a string"
            )
        if field_value == "":
            raise Stage22CaptureContractError(
                f"normalized_event field {field_name!r} must be non-empty"
            )
    if not isinstance(key.provider_event_id, str):
        raise Stage22CaptureContractError(
            "normalized_event field 'provider_event_id' must be a string"
        )
    validated_payload = _validate_payload_summary(event.payload_summary)
    return {
        "schema_version": STAGE22_CAPTURE_RECORD_SCHEMA_VERSION,
        "record_type": CAPTURE_RECORD_TYPE_NORMALIZED_EVENT,
        "provider_id": key.provider_id,
        "chain": key.chain,
        "event_id": key.event_id,
        "provider_event_id": key.provider_event_id,
        "raw_event_hash": key.raw_event_hash,
        "received_at_utc": envelope.received_at_utc,
        "provider_attempt_index": envelope.provider_attempt_index,
        "event_type": event.event_type,
        "source_kind": event.source_kind,
        "mint": event.mint,
        "slot": event.slot,
        "signature": event.signature,
        "payload_summary": validated_payload,
    }


def _build_malformed_event_record(
    *,
    record: MalformedEventRecord,
) -> dict[str, object]:
    """Build a canonical malformed_event JSON record from a record.

    Validates every required field and returns a freshly-built
    dict. Raises ``Stage22CaptureContractError`` on any contract
    violation.
    """
    string_fields: dict[str, object] = {
        "provider_id": record.provider_id,
        "reason": record.reason,
        "failed_at_utc": record.failed_at_utc,
        "raw_event_hash": record.raw_event_hash,
    }
    for field_name, field_value in string_fields.items():
        if not isinstance(field_value, str):
            raise Stage22CaptureContractError(
                f"malformed_event field {field_name!r} must be a string"
            )
        if field_value == "":
            raise Stage22CaptureContractError(
                f"malformed_event field {field_name!r} must be non-empty"
            )
    if not isinstance(record.provider_event_id, str):
        raise Stage22CaptureContractError(
            "malformed_event field 'provider_event_id' must be a string"
        )
    if record.reason not in MALFORMED_EVENT_REASONS:
        raise Stage22CaptureContractError(
            "malformed_event field 'reason' is not in MALFORMED_EVENT_REASONS"
        )
    return {
        "schema_version": STAGE22_CAPTURE_RECORD_SCHEMA_VERSION,
        "record_type": CAPTURE_RECORD_TYPE_MALFORMED_EVENT,
        "provider_id": record.provider_id,
        "provider_event_id": record.provider_event_id,
        "reason": record.reason,
        "failed_at_utc": record.failed_at_utc,
        "raw_event_hash": record.raw_event_hash,
    }


def _build_provider_failure_record(
    *,
    record: ProviderFailureRecord,
) -> dict[str, object]:
    """Build a canonical provider_failure JSON record from a record.

    Validates every required field and returns a freshly-built
    dict. Raises ``Stage22CaptureContractError`` on any contract
    violation. ``status_class`` cannot be ``'success'`` and
    ``upstream_error_type`` cannot be empty -- those values are
    reserved for ok=True outcomes that have no place in a
    provider_failure record.
    """
    if not _is_strict_int(record.provider_attempt_index):
        raise Stage22CaptureContractError(
            "provider_failure field 'provider_attempt_index' must be a "
            "strict int (bool is not accepted)"
        )
    if record.provider_attempt_index < 0:
        raise Stage22CaptureContractError(
            "provider_failure field 'provider_attempt_index' must be >= 0"
        )
    string_fields: dict[str, object] = {
        "provider_id": record.provider_id,
        "failure_label": record.failure_label,
        "status_class": record.status_class,
        "upstream_error_type": record.upstream_error_type,
        "observed_at_utc": record.observed_at_utc,
    }
    for field_name, field_value in string_fields.items():
        if not isinstance(field_value, str):
            raise Stage22CaptureContractError(
                f"provider_failure field {field_name!r} must be a string"
            )
        if field_value == "":
            raise Stage22CaptureContractError(
                f"provider_failure field {field_name!r} must be non-empty"
            )
    if record.failure_label not in PROVIDER_FAILURE_LABELS:
        raise Stage22CaptureContractError(
            "provider_failure field 'failure_label' is not in "
            "PROVIDER_FAILURE_LABELS"
        )
    if record.status_class not in STATUS_CLASSES:
        raise Stage22CaptureContractError(
            "provider_failure field 'status_class' is not in "
            "STATUS_CLASSES"
        )
    if record.status_class == STATUS_CLASS_SUCCESS:
        raise Stage22CaptureContractError(
            "provider_failure 'status_class' cannot be 'success' "
            "(reserved for ok=True outcomes)"
        )
    if record.upstream_error_type not in UPSTREAM_ERROR_TYPES:
        raise Stage22CaptureContractError(
            "provider_failure field 'upstream_error_type' is not in "
            "UPSTREAM_ERROR_TYPES"
        )
    return {
        "schema_version": STAGE22_CAPTURE_RECORD_SCHEMA_VERSION,
        "record_type": CAPTURE_RECORD_TYPE_PROVIDER_FAILURE,
        "provider_id": record.provider_id,
        "failure_label": record.failure_label,
        "status_class": record.status_class,
        "upstream_error_type": record.upstream_error_type,
        "provider_attempt_index": record.provider_attempt_index,
        "observed_at_utc": record.observed_at_utc,
    }


# ---------------------------------------------------------------------------
# Serialisation / decoding
# ---------------------------------------------------------------------------


def _serialize_record(*, record: dict[str, object]) -> str:
    """Canonical JSON serialisation: sorted keys, compact separators.

    Strict JSON only: ``allow_nan=False`` prevents NaN /
    Infinity / -Infinity from emitting (Python's ``json`` module
    would otherwise produce the non-standard JS-style tokens that
    break strict parsers). No trailing newline; the caller
    appends it at write time so the line / newline pair is a
    single atomic write boundary.
    """
    return json.dumps(
        record,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _decode_record(*, raw: str, line_no: int) -> dict[str, object]:
    """Decode and fully validate a single JSONL line.

    Returns the validated dict on success. Raises
    ``Stage22CaptureContractError`` on any contract violation:
    invalid JSON, non-object JSON, unknown schema_version,
    unknown record_type, missing required field, unexpected
    extra field, non-string-when-string-required, non-int-
    when-int-required, negative int, empty-when-non-empty-
    required, closed-set violation, unsafe payload_summary.
    """
    try:
        decoded = json.loads(raw)
    except ValueError:
        raise Stage22CaptureContractError(
            f"capture line {line_no} is not valid JSON"
        )
    if not isinstance(decoded, dict):
        raise Stage22CaptureContractError(
            f"capture line {line_no} is not a JSON object"
        )
    schema_version = decoded.get("schema_version")
    if schema_version != STAGE22_CAPTURE_RECORD_SCHEMA_VERSION:
        raise Stage22CaptureContractError(
            f"capture line {line_no} has unknown schema_version"
        )
    record_type = decoded.get("record_type")
    if record_type not in CAPTURE_RECORD_TYPES:
        raise Stage22CaptureContractError(
            f"capture line {line_no} has unknown record_type"
        )
    expected_fields = _REQUIRED_FIELDS_BY_RECORD_TYPE[record_type]
    actual = set(decoded.keys())
    expected = set(expected_fields)
    if actual != expected:
        extras = sorted(actual - expected)
        missing = sorted(expected - actual)
        raise Stage22CaptureContractError(
            f"capture line {line_no} has an unexpected field set "
            f"(extras={extras}, missing={missing})"
        )
    if record_type == CAPTURE_RECORD_TYPE_NORMALIZED_EVENT:
        _validate_normalized_event_dict(decoded=decoded, line_no=line_no)
    elif record_type == CAPTURE_RECORD_TYPE_MALFORMED_EVENT:
        _validate_malformed_event_dict(decoded=decoded, line_no=line_no)
    else:
        _validate_provider_failure_dict(decoded=decoded, line_no=line_no)
    return decoded


def _validate_normalized_event_dict(
    *,
    decoded: dict[str, object],
    line_no: int,
) -> None:
    for field in CAPTURE_NORMALIZED_EVENT_REQUIRED_NON_EMPTY_STRING_FIELDS:
        value = decoded[field]
        if not isinstance(value, str):
            raise Stage22CaptureContractError(
                f"capture line {line_no} field {field!r} is not a string"
            )
        if value == "":
            raise Stage22CaptureContractError(
                f"capture line {line_no} field {field!r} is empty"
            )
    if not isinstance(decoded["provider_event_id"], str):
        raise Stage22CaptureContractError(
            f"capture line {line_no} field 'provider_event_id' is not a "
            "string"
        )
    for field in CAPTURE_NORMALIZED_EVENT_REQUIRED_INT_FIELDS:
        value = decoded[field]
        if not _is_strict_int(value):
            raise Stage22CaptureContractError(
                f"capture line {line_no} field {field!r} is not a strict int"
            )
        if value < 0:  # type: ignore[operator]
            raise Stage22CaptureContractError(
                f"capture line {line_no} field {field!r} is negative"
            )
    payload = decoded["payload_summary"]
    if not isinstance(payload, dict):
        raise Stage22CaptureContractError(
            f"capture line {line_no} field 'payload_summary' is not a "
            "JSON object"
        )
    _validate_payload_summary(payload)


def _validate_malformed_event_dict(
    *,
    decoded: dict[str, object],
    line_no: int,
) -> None:
    for field in CAPTURE_MALFORMED_EVENT_REQUIRED_NON_EMPTY_STRING_FIELDS:
        value = decoded[field]
        if not isinstance(value, str):
            raise Stage22CaptureContractError(
                f"capture line {line_no} field {field!r} is not a string"
            )
        if value == "":
            raise Stage22CaptureContractError(
                f"capture line {line_no} field {field!r} is empty"
            )
    if not isinstance(decoded["provider_event_id"], str):
        raise Stage22CaptureContractError(
            f"capture line {line_no} field 'provider_event_id' is not a "
            "string"
        )
    if decoded["reason"] not in MALFORMED_EVENT_REASONS:
        raise Stage22CaptureContractError(
            f"capture line {line_no} field 'reason' is not in "
            "MALFORMED_EVENT_REASONS"
        )


def _validate_provider_failure_dict(
    *,
    decoded: dict[str, object],
    line_no: int,
) -> None:
    for field in CAPTURE_PROVIDER_FAILURE_REQUIRED_NON_EMPTY_STRING_FIELDS:
        value = decoded[field]
        if not isinstance(value, str):
            raise Stage22CaptureContractError(
                f"capture line {line_no} field {field!r} is not a string"
            )
        if value == "":
            raise Stage22CaptureContractError(
                f"capture line {line_no} field {field!r} is empty"
            )
    for field in CAPTURE_PROVIDER_FAILURE_REQUIRED_INT_FIELDS:
        value = decoded[field]
        if not _is_strict_int(value):
            raise Stage22CaptureContractError(
                f"capture line {line_no} field {field!r} is not a strict int"
            )
        if value < 0:  # type: ignore[operator]
            raise Stage22CaptureContractError(
                f"capture line {line_no} field {field!r} is negative"
            )
    if decoded["failure_label"] not in PROVIDER_FAILURE_LABELS:
        raise Stage22CaptureContractError(
            f"capture line {line_no} field 'failure_label' is not in "
            "PROVIDER_FAILURE_LABELS"
        )
    if decoded["status_class"] not in STATUS_CLASSES:
        raise Stage22CaptureContractError(
            f"capture line {line_no} field 'status_class' is not in "
            "STATUS_CLASSES"
        )
    if decoded["status_class"] == STATUS_CLASS_SUCCESS:
        raise Stage22CaptureContractError(
            f"capture line {line_no} field 'status_class' is 'success' "
            "(incoherent for provider_failure)"
        )
    if decoded["upstream_error_type"] not in UPSTREAM_ERROR_TYPES:
        raise Stage22CaptureContractError(
            f"capture line {line_no} field 'upstream_error_type' is not in "
            "UPSTREAM_ERROR_TYPES"
        )


# ---------------------------------------------------------------------------
# Snapshot helper
# ---------------------------------------------------------------------------


def _snapshot_copy(record: dict[str, object]) -> dict[str, object]:
    """Build a fresh shallow + payload-summary copy of a record.

    The outer dict is copied; if a ``payload_summary`` field is
    present, its inner dict is also copied. payload_summary
    values are immutable primitives (str / int / float / bool /
    None) so no deeper copy is needed for safety.
    """
    out: dict[str, object] = dict(record)
    payload = out.get("payload_summary")
    if isinstance(payload, dict):
        out["payload_summary"] = dict(payload)
    return out


# ---------------------------------------------------------------------------
# InMemoryRawCaptureWriter
# ---------------------------------------------------------------------------


class InMemoryRawCaptureWriter:
    """In-memory ``RawCaptureWriter`` implementation.

    No I/O. Records are stored in chronological order across
    all three record families; per-family read-only snapshot
    accessors are exposed for tests and offline runner
    simulation. The validation rules are identical to
    ``JsonlRawCaptureWriter`` -- the same module-private helpers
    are used so protocol parity is structural.
    """

    def __init__(self) -> None:
        self._records: list[dict[str, object]] = []

    def capture(self, *, envelope: IngestEventEnvelope) -> None:
        record = _build_normalized_event_record(envelope=envelope)
        self._records.append(record)

    def capture_malformed(
        self,
        *,
        record: MalformedEventRecord,
    ) -> None:
        built = _build_malformed_event_record(record=record)
        self._records.append(built)

    def capture_provider_failure(
        self,
        *,
        record: ProviderFailureRecord,
    ) -> None:
        built = _build_provider_failure_record(record=record)
        self._records.append(built)

    def captured_all(self) -> tuple[dict[str, object], ...]:
        """Return all captured records in chronological order.

        Each returned dict is a fresh copy; mutating it does
        not affect the writer's internal state. Across record
        families, chronological insertion order is preserved.
        """
        return tuple(_snapshot_copy(r) for r in self._records)

    def captured_normalized_events(
        self,
    ) -> tuple[dict[str, object], ...]:
        """Return all normalized_event records in chronological order."""
        return tuple(
            _snapshot_copy(r)
            for r in self._records
            if r["record_type"] == CAPTURE_RECORD_TYPE_NORMALIZED_EVENT
        )

    def captured_malformed_events(
        self,
    ) -> tuple[dict[str, object], ...]:
        """Return all malformed_event records in chronological order."""
        return tuple(
            _snapshot_copy(r)
            for r in self._records
            if r["record_type"] == CAPTURE_RECORD_TYPE_MALFORMED_EVENT
        )

    def captured_provider_failures(
        self,
    ) -> tuple[dict[str, object], ...]:
        """Return all provider_failure records in chronological order."""
        return tuple(
            _snapshot_copy(r)
            for r in self._records
            if r["record_type"] == CAPTURE_RECORD_TYPE_PROVIDER_FAILURE
        )


# ---------------------------------------------------------------------------
# JsonlRawCaptureWriter
# ---------------------------------------------------------------------------


class JsonlRawCaptureWriter:
    """Append-only JSONL ``RawCaptureWriter`` implementation.

    Operator supplies a ``pathlib.Path``. The parent directory
    must already exist; the writer never calls ``mkdir`` /
    ``unlink`` / ``rename`` / ``replace`` / ``glob`` /
    ``iterdir`` / ``rmdir`` and never imports ``shutil``.

    On construction the writer replays the existing file (if
    any) and validates every line through the same
    per-record-type decoder used at write time. A
    contract-violating line raises
    ``Stage22CaptureContractError`` from the constructor.

    Path discipline:

      * ``path`` must be a ``pathlib.Path``.
      * ``..`` segments anywhere in ``path.parts`` are rejected.
      * The parent directory must already exist.
      * If ``path`` exists it must be a regular file.

    Failure modes:

      * Replay sees a contract-violating line -> raise.
      * Write OSError -> raise ``Stage22CaptureContractError``.
      * Sanitiser / shape rejection on capture -> raise
        ``Stage22CaptureContractError`` (no soft-fail outcome).

    Single-writer assumption: the operator is responsible for
    not pointing two processes at the same path concurrently.
    The writer fsyncs after each line so individual records are
    durable, but cross-process coordination is out of scope.
    """

    def __init__(self, *, path: Path) -> None:
        if not isinstance(path, Path):
            raise Stage22CaptureContractError(
                "JsonlRawCaptureWriter requires a pathlib.Path"
            )
        if ".." in path.parts:
            raise Stage22CaptureContractError(
                "capture path must not contain '..' path traversal "
                "segments"
            )
        parent = path.parent
        if not parent.exists() or not parent.is_dir():
            raise Stage22CaptureContractError(
                "capture path parent directory does not exist "
                "(the writer never creates directories)"
            )
        if path.exists() and not path.is_file():
            raise Stage22CaptureContractError(
                "capture path exists but is not a regular file"
            )
        self._path: Path = path
        self._replay()

    def _replay(self) -> None:
        if not self._path.exists():
            return
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                for line_no, raw in enumerate(f, start=1):
                    stripped = raw.rstrip("\n")
                    if stripped == "":
                        raise Stage22CaptureContractError(
                            f"capture line {line_no} is blank"
                        )
                    _decode_record(raw=stripped, line_no=line_no)
        except OSError:
            # Any open / read OSError during replay is a hard
            # contract violation: the file exists but we cannot
            # consume it. Surface as Stage22CaptureContractError
            # rather than leaking the raw OSError.
            raise Stage22CaptureContractError(
                "capture replay read failed"
            )

    def _append_record(self, *, record: dict[str, object]) -> None:
        line = _serialize_record(record=record)
        try:
            with open(self._path, "a", encoding="utf-8") as f:
                f.write(line)
                f.write("\n")
                f.flush()
                os.fsync(f.fileno())
        except OSError:
            raise Stage22CaptureContractError(
                "capture write failed"
            )

    def capture(self, *, envelope: IngestEventEnvelope) -> None:
        record = _build_normalized_event_record(envelope=envelope)
        self._append_record(record=record)

    def capture_malformed(
        self,
        *,
        record: MalformedEventRecord,
    ) -> None:
        built = _build_malformed_event_record(record=record)
        self._append_record(record=built)

    def capture_provider_failure(
        self,
        *,
        record: ProviderFailureRecord,
    ) -> None:
        built = _build_provider_failure_record(record=record)
        self._append_record(record=built)


__all__ = [
    "InMemoryRawCaptureWriter",
    "JsonlRawCaptureWriter",
]

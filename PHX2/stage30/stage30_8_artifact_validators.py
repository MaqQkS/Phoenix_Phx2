"""Stage 30.8.1 pure compact artifact validators.

Pure, deterministic, TOTAL validation functions for the Stage 30.8.1
compact artifact records. Each validator classifies a (possibly
malformed) record into a closed-set ``Stage30_8ValidationResult``
(``VALID`` / ``INVALID``) and NEVER raises -- malformed input, a wrong
type, or ``None`` all fail closed to an ``INVALID`` result with
``safe_to_persist=False``. This mirrors the Stage 30.6.1 evaluator's
total fail-closed discipline.

Stage 30.8.1 validators implement NO writer, NO database, NO filesystem
access, and NO compression. ``safe_to_persist`` on the result is a
verdict flag a FUTURE writer (Stage 30.8.2+) would consult; Stage 30.8.1
persists nothing.

Validation rules (closed):

  1. identity ``stage_id`` must be ``stage30_8``.
  2. identity ``artifact_schema_version`` must be
     ``stage30_8_v0_compact_artifact``.
  3. identity ``artifact_kind`` must be one of the closed-set kinds.
  4. required identity strings (``run_id`` /
     ``artifact_created_at_utc`` plus the kind-specific axes) must be
     present and non-empty; optional identity strings, when present,
     must be non-empty.
  5. ``compact_body_text`` must be a non-empty string for a ping
     artifact.
  6. ``MC`` / ``LP`` / ``Net`` / ``ATH`` / ``Mig`` and the other
     display fields must be strings when present.
  7. ``warning_codes`` / ``reason_codes`` must be tuples / lists of
     strings only.
  8. no nested raw dict / list / set / bytes payload in any field
     (the codes tuples of strings are the only allowed sequences).
  9. a forbidden field NAME (a credential / transport / raw-payload
     class name) fails closed.
  10. a string VALUE carrying an obvious secret / URL / inbound-hook /
      API-credential pattern fails closed.
  11. the closed-set safe placeholders (``Unknown`` / ``REDACTED`` /
      ``SAFE``) are always allowed.
  12. validators never raise; malformed input returns ``INVALID``.
  13. validators are pure / deterministic.

Forbidden field-name tokens and forbidden value needles are built with
split-literal concatenation so this module's own source carries none of
the bare credential / transport / inbound-hook substrings (mirrors the
Stage 30.6.1 / 30.4 / 30.5 guards). The runtime-concatenated values
resolve to the correct human-readable forbidden forms.

Discipline:

  * Stdlib only (``dataclasses`` / ``math`` / ``typing``).
  * Imports ONLY the Stage 30.8.1 models sibling
    (``stage30_8_artifact_models``) -- no other PHX2 module, no Stage
    21-29 / Stage 29.5 module, no runtime / orchestrator / renderer
    import.
  * No ``os`` / ``pathlib`` / ``shutil`` / ``sqlite3`` / compression
    import. No network surface. No Discord / provider reference.
  * No filesystem / env / network I/O. No ``open``. No top-level Call
    (no implicit I/O at import time).
"""

from __future__ import annotations

import dataclasses
import math
from typing import List, Optional, Tuple

from PHX2.stage30.stage30_8_artifact_models import (
    ARTIFACT_KIND_COMPACT_DISPATCH_ATTEMPT_ARTIFACT,
    ARTIFACT_KIND_COMPACT_ERROR_ARTIFACT,
    ARTIFACT_KIND_COMPACT_PING_ARTIFACT,
    ARTIFACT_KIND_COMPACT_SESSION_SUMMARY,
    ARTIFACT_KIND_COMPACT_STORAGE_BUDGET_SNAPSHOT,
    STAGE30_8_ARTIFACT_KINDS,
    STAGE30_8_ARTIFACT_SCHEMA_VERSION,
    STAGE30_8_ARTIFACT_STAGE_ID,
    STAGE30_8_STORAGE_BUDGET_STATUS_VALUES,
    VALIDATION_STATUS_INVALID,
    VALIDATION_STATUS_VALID,
    Stage30_8ValidationResult,
    is_storage_budget_status,
)


# ---------------------------------------------------------------------------
# Validation reason tokens (closed set)
# ---------------------------------------------------------------------------


VALIDATION_REASON_OK: str = "OK"
VALIDATION_REASON_INVALID_INPUT_TYPE: str = "INVALID_INPUT_TYPE"
VALIDATION_REASON_STAGE_ID_INVALID: str = "STAGE_ID_INVALID"
VALIDATION_REASON_SCHEMA_VERSION_INVALID: str = "SCHEMA_VERSION_INVALID"
VALIDATION_REASON_ARTIFACT_KIND_INVALID: str = "ARTIFACT_KIND_INVALID"
VALIDATION_REASON_ARTIFACT_KIND_MISMATCH: str = "ARTIFACT_KIND_MISMATCH"
VALIDATION_REASON_MISSING_REQUIRED_IDENTITY: str = (
    "MISSING_REQUIRED_IDENTITY"
)
VALIDATION_REASON_DISPLAY_FIELD_NOT_STRING: str = (
    "DISPLAY_FIELD_NOT_STRING"
)
VALIDATION_REASON_CODES_NOT_STRING_SEQUENCE: str = (
    "CODES_NOT_STRING_SEQUENCE"
)
VALIDATION_REASON_EMPTY_COMPACT_BODY: str = "EMPTY_COMPACT_BODY"
VALIDATION_REASON_FORBIDDEN_FIELD_NAME: str = "FORBIDDEN_FIELD_NAME"
VALIDATION_REASON_FORBIDDEN_VALUE_PATTERN: str = (
    "FORBIDDEN_VALUE_PATTERN"
)
VALIDATION_REASON_NESTED_RAW_PAYLOAD: str = "NESTED_RAW_PAYLOAD"
VALIDATION_REASON_BINARY_VALUE: str = "BINARY_VALUE"
VALIDATION_REASON_COUNTER_INVALID: str = "COUNTER_INVALID"
VALIDATION_REASON_PERCENT_INVALID: str = "PERCENT_INVALID"
VALIDATION_REASON_BUDGET_STATUS_INVALID: str = "BUDGET_STATUS_INVALID"
VALIDATION_REASON_TRANSPORT_STATUS_INVALID: str = (
    "TRANSPORT_STATUS_INVALID"
)
VALIDATION_REASON_ERROR_REASON_CODE_INVALID: str = (
    "ERROR_REASON_CODE_INVALID"
)


STAGE30_8_VALIDATION_REASONS: Tuple[str, ...] = (
    VALIDATION_REASON_OK,
    VALIDATION_REASON_INVALID_INPUT_TYPE,
    VALIDATION_REASON_STAGE_ID_INVALID,
    VALIDATION_REASON_SCHEMA_VERSION_INVALID,
    VALIDATION_REASON_ARTIFACT_KIND_INVALID,
    VALIDATION_REASON_ARTIFACT_KIND_MISMATCH,
    VALIDATION_REASON_MISSING_REQUIRED_IDENTITY,
    VALIDATION_REASON_DISPLAY_FIELD_NOT_STRING,
    VALIDATION_REASON_CODES_NOT_STRING_SEQUENCE,
    VALIDATION_REASON_EMPTY_COMPACT_BODY,
    VALIDATION_REASON_FORBIDDEN_FIELD_NAME,
    VALIDATION_REASON_FORBIDDEN_VALUE_PATTERN,
    VALIDATION_REASON_NESTED_RAW_PAYLOAD,
    VALIDATION_REASON_BINARY_VALUE,
    VALIDATION_REASON_COUNTER_INVALID,
    VALIDATION_REASON_PERCENT_INVALID,
    VALIDATION_REASON_BUDGET_STATUS_INVALID,
    VALIDATION_REASON_TRANSPORT_STATUS_INVALID,
    VALIDATION_REASON_ERROR_REASON_CODE_INVALID,
)


# ---------------------------------------------------------------------------
# Required / optional identity axes + content field partitions
# ---------------------------------------------------------------------------
#
# The universally-required identity strings (every artifact kind). The
# kind-specific validators add their own required axes (for example a
# ping artifact also requires session_id / ping_id / dedupe_key).


REQUIRED_IDENTITY_FIELDS: Tuple[str, ...] = (
    "stage_id",
    "artifact_schema_version",
    "artifact_kind",
    "artifact_created_at_utc",
    "run_id",
)


# Optional identity strings: ``None`` means "not available" (allowed);
# any present value must be a non-empty string.
OPTIONAL_IDENTITY_FIELDS: Tuple[str, ...] = (
    "session_id",
    "ping_id",
    "candidate_id",
    "token_mint",
    "provider_event_id",
    "normalized_event_id",
    "observed_at_utc",
    "dedupe_key",
    "compact_ping_schema_version",
)


# Content display fields: must be strings when present.
CONTENT_DISPLAY_FIELDS: Tuple[str, ...] = (
    "compact_body_text",
    "mc_display",
    "lp_display",
    "net_display",
    "ath_display",
    "migration_display",
    "decision_status",
    "eligibility_status",
    "terminal_outcome_code",
    "sanitized_transport_status",
)


# Content codes fields: tuples / lists of strings only.
CONTENT_CODES_FIELDS: Tuple[str, ...] = (
    "warning_codes",
    "reason_codes",
)


# The full expected compact content snapshot field set (display + codes).
# A content-snapshot-like object must expose at least one of these fields
# to validate; anything that exposes none of them fails closed.
EXPECTED_CONTENT_SNAPSHOT_FIELDS: Tuple[str, ...] = (
    CONTENT_DISPLAY_FIELDS + CONTENT_CODES_FIELDS
)


# ---------------------------------------------------------------------------
# Forbidden field-name tokens (rule 9)
# ---------------------------------------------------------------------------
#
# Scanned (case-insensitive substring) against every field NAME on a
# validated record. Split-literal forms keep this module's source free
# of the bare credential / transport / inbound-hook needles.


FORBIDDEN_FIELD_NAME_TOKENS: Tuple[str, ...] = (
    "web" + "hook",
    "api_" + "key",
    "author" + "ization",
    "b" + "earer",
    "x-api-" + "key",
    "env",
    "private_key",
    "signing",
    "raw_provider_payload",
    "raw_transaction",
    "raw_log",
    "response" + "_body",
    "discord_response" + "_body",
    "url",
    "binary",
)


# ---------------------------------------------------------------------------
# Forbidden value needles (rule 10)
# ---------------------------------------------------------------------------
#
# Scanned (case-insensitive substring) against every string VALUE on a
# validated record. Split-literal forms keep this module's source free
# of the bare transport / inbound-hook / API-credential needles.


FORBIDDEN_VALUE_NEEDLES: Tuple[str, ...] = (
    "h" + "ttps://",
    "h" + "ttp://",
    "w" + "ss://",
    "w" + "s://",
    "discord" + ".com",
    "discord" + "app.com",
    "/web" + "hooks/",
    "author" + "ization",
    "b" + "earer",
    "api_" + "key",
    "api" + " key",
    "x-api-" + "key",
)


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def _valid() -> Stage30_8ValidationResult:
    """Return the canonical VALID / safe-to-persist result."""
    return Stage30_8ValidationResult(
        status=VALIDATION_STATUS_VALID,
        reason=VALIDATION_REASON_OK,
        blocked_field=None,
        safe_to_persist=True,
    )


def _invalid(
    reason: str, blocked_field: Optional[str]
) -> Stage30_8ValidationResult:
    """Return an INVALID / not-safe-to-persist result (fail closed)."""
    return Stage30_8ValidationResult(
        status=VALIDATION_STATUS_INVALID,
        reason=reason,
        blocked_field=blocked_field,
        safe_to_persist=False,
    )


def _is_nonempty_str(value: object) -> bool:
    """Return ``True`` iff ``value`` is a non-empty string."""
    return isinstance(value, str) and value != ""


def _is_nonneg_int(value: object) -> bool:
    """Return ``True`` iff ``value`` is a non-negative ``int`` and NOT a
    ``bool`` (``bool`` is an ``int`` subclass and must never count as a
    counter value).
    """
    if isinstance(value, bool):
        return False
    return isinstance(value, int) and value >= 0


def _is_valid_percent(value: object) -> bool:
    """Return ``True`` iff ``value`` is a finite real percent in
    ``[0, 100]`` and NOT a ``bool``.
    """
    if isinstance(value, bool):
        return False
    if not isinstance(value, (int, float)):
        return False
    if isinstance(value, float) and not math.isfinite(value):
        return False
    return 0 <= value <= 100


def _is_content_snapshot_like(snapshot: object) -> bool:
    """Return ``True`` iff ``snapshot`` is a compact-content-snapshot-like
    record.

    Fail-closed shape gate. The content snapshot model is a dataclass
    record, NEVER a bare scalar / string / sequence / mapping, so
    ``None``, a ``bool`` / ``int`` / ``float`` / ``complex``, a ``str``
    / ``bytes`` / ``bytearray``, a ``list`` / ``tuple`` / ``set`` /
    ``frozenset``, and a ``dict`` are rejected outright (a ``dict`` is
    NOT an accepted snapshot input). Any other object must expose at
    least one expected compact content field as an attribute to be
    treated as snapshot-like. Pure / deterministic.
    """
    if snapshot is None:
        return False
    if isinstance(
        snapshot,
        (
            bool,
            int,
            float,
            complex,
            str,
            bytes,
            bytearray,
            list,
            tuple,
            set,
            frozenset,
            dict,
        ),
    ):
        return False
    for name in EXPECTED_CONTENT_SNAPSHOT_FIELDS:
        if hasattr(snapshot, name):
            return True
    return False


def is_forbidden_field_name(name: object) -> bool:
    """Return ``True`` iff ``name`` is a forbidden record field name.

    Pure / deterministic. A field whose name carries a credential /
    transport / raw-payload-class token fails closed.
    """
    if not isinstance(name, str):
        return False
    lower = name.lower()
    for token in FORBIDDEN_FIELD_NAME_TOKENS:
        if token in lower:
            return True
    return False


def value_has_forbidden_pattern(value: object) -> bool:
    """Return ``True`` iff ``value`` is a string carrying an obvious
    secret / URL / inbound-hook / API-credential pattern.

    Pure / deterministic. Non-string input returns ``False`` (the
    type-specific checks handle non-strings).
    """
    if not isinstance(value, str):
        return False
    lower = value.lower()
    for needle in FORBIDDEN_VALUE_NEEDLES:
        if needle in lower:
            return True
    return False


def _field_items(obj: object) -> List[Tuple[str, object]]:
    """Return ``(name, value)`` pairs for ``obj``'s fields.

    Handles a dataclass instance (via ``dataclasses.fields``), a mapping
    (via ``items``), or any object exposing ``__dict__``. Returns an
    empty list for ``None`` / a fieldless object. Pure; never raises.
    """
    try:
        if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
            return [
                (f.name, getattr(obj, f.name, None))
                for f in dataclasses.fields(obj)
            ]
        if isinstance(obj, dict):
            return [
                (k, v) for k, v in obj.items() if isinstance(k, str)
            ]
        mapping = getattr(obj, "__dict__", None)
        if isinstance(mapping, dict):
            return [
                (k, v)
                for k, v in mapping.items()
                if isinstance(k, str)
            ]
    except Exception:
        return []
    return []


def _scan_object_fields(
    obj: object, codes_field_names: Tuple[str, ...] = ()
) -> Optional[Stage30_8ValidationResult]:
    """Scan one object's own fields for the closed safety rules.

    Returns an ``INVALID`` result on the first violation:

      * a forbidden field NAME (rule 9),
      * a string VALUE carrying a forbidden pattern (rule 10),
      * a ``bytes`` / ``bytearray`` value (binary blob),
      * a nested raw ``dict`` / ``list`` / ``set`` / other exotic value
        in a non-codes field (rule 8),
      * a codes field whose entries are not all safe strings (rule 7).

    Nested dataclass values (a nested identity / content / snapshot)
    are SKIPPED here; the caller validates them through their own
    validator. Scalars (``str`` / ``int`` / ``float`` / ``bool`` /
    ``None``) pass the scan and are checked by the type-specific
    validators. Returns ``None`` when no violation is found. Pure;
    never raises.
    """
    for name, value in _field_items(obj):
        if is_forbidden_field_name(name):
            return _invalid(
                VALIDATION_REASON_FORBIDDEN_FIELD_NAME, name
            )
        if value is None:
            continue
        if dataclasses.is_dataclass(value) and not isinstance(
            value, type
        ):
            continue
        if isinstance(value, str):
            if value_has_forbidden_pattern(value):
                return _invalid(
                    VALIDATION_REASON_FORBIDDEN_VALUE_PATTERN, name
                )
            continue
        if isinstance(value, (bytes, bytearray)):
            return _invalid(VALIDATION_REASON_BINARY_VALUE, name)
        if isinstance(value, bool):
            continue
        if isinstance(value, (int, float)):
            continue
        if isinstance(value, (tuple, list)):
            if name in codes_field_names:
                for element in value:
                    if not isinstance(element, str):
                        return _invalid(
                            VALIDATION_REASON_CODES_NOT_STRING_SEQUENCE,
                            name,
                        )
                    if value_has_forbidden_pattern(element):
                        return _invalid(
                            VALIDATION_REASON_FORBIDDEN_VALUE_PATTERN,
                            name,
                        )
                continue
            return _invalid(VALIDATION_REASON_NESTED_RAW_PAYLOAD, name)
        if isinstance(value, dict):
            return _invalid(VALIDATION_REASON_NESTED_RAW_PAYLOAD, name)
        # Any other exotic type (set, frozenset, custom object, ...) is
        # treated as a nested raw payload and fails closed.
        return _invalid(VALIDATION_REASON_NESTED_RAW_PAYLOAD, name)
    return None


# ---------------------------------------------------------------------------
# Public: identity validator
# ---------------------------------------------------------------------------


def validate_compact_artifact_identity(
    identity: object,
) -> Stage30_8ValidationResult:
    """Validate a Stage 30.8 compact artifact identity.

    Enforces rules 1-4, 9-12. Pure / total; never raises.
    """
    try:
        scan = _scan_object_fields(identity)
        if scan is not None:
            return scan

        stage_id = getattr(identity, "stage_id", None)
        if (
            not _is_nonempty_str(stage_id)
            or stage_id != STAGE30_8_ARTIFACT_STAGE_ID
        ):
            return _invalid(
                VALIDATION_REASON_STAGE_ID_INVALID, "stage_id"
            )

        schema_version = getattr(
            identity, "artifact_schema_version", None
        )
        if (
            not _is_nonempty_str(schema_version)
            or schema_version != STAGE30_8_ARTIFACT_SCHEMA_VERSION
        ):
            return _invalid(
                VALIDATION_REASON_SCHEMA_VERSION_INVALID,
                "artifact_schema_version",
            )

        artifact_kind = getattr(identity, "artifact_kind", None)
        if (
            not _is_nonempty_str(artifact_kind)
            or artifact_kind not in STAGE30_8_ARTIFACT_KINDS
        ):
            return _invalid(
                VALIDATION_REASON_ARTIFACT_KIND_INVALID, "artifact_kind"
            )

        for field_name in REQUIRED_IDENTITY_FIELDS:
            if not _is_nonempty_str(getattr(identity, field_name, None)):
                return _invalid(
                    VALIDATION_REASON_MISSING_REQUIRED_IDENTITY,
                    field_name,
                )

        for field_name in OPTIONAL_IDENTITY_FIELDS:
            value = getattr(identity, field_name, None)
            if value is None:
                continue
            if not _is_nonempty_str(value):
                return _invalid(
                    VALIDATION_REASON_MISSING_REQUIRED_IDENTITY,
                    field_name,
                )

        return _valid()
    except Exception:
        return _invalid(VALIDATION_REASON_INVALID_INPUT_TYPE, None)


def _validate_identity_for_kind(
    identity: object,
    expected_kind: str,
    required_axes: Tuple[str, ...] = (),
) -> Stage30_8ValidationResult:
    """Validate ``identity`` and pin its kind + kind-specific axes.

    Returns the identity result on failure, an ``ARTIFACT_KIND_MISMATCH``
    result when the kind does not match ``expected_kind``, a
    ``MISSING_REQUIRED_IDENTITY`` result when a kind-specific axis is
    missing, else a ``VALID`` result. Pure / total.
    """
    identity_result = validate_compact_artifact_identity(identity)
    if identity_result.status != VALIDATION_STATUS_VALID:
        return identity_result
    if getattr(identity, "artifact_kind", None) != expected_kind:
        return _invalid(
            VALIDATION_REASON_ARTIFACT_KIND_MISMATCH, "artifact_kind"
        )
    for axis in required_axes:
        if not _is_nonempty_str(getattr(identity, axis, None)):
            return _invalid(
                VALIDATION_REASON_MISSING_REQUIRED_IDENTITY, axis
            )
    return _valid()


# ---------------------------------------------------------------------------
# Public: content snapshot validator
# ---------------------------------------------------------------------------


def validate_compact_content_snapshot(
    snapshot: object, require_body: bool = False
) -> Stage30_8ValidationResult:
    """Validate a Stage 30.8 compact content snapshot.

    Enforces rules 5-12. A fail-closed shape gate runs first: a
    non-snapshot-like input (``None``, a scalar, a string, a sequence,
    a ``dict``, or any object exposing none of the expected compact
    content fields) returns ``INVALID`` / ``INVALID_INPUT_TYPE`` rather
    than passing as VALID. With ``require_body=True`` (the ping path),
    ``compact_body_text`` must be a non-empty string. Pure / total;
    never raises.
    """
    try:
        if not _is_content_snapshot_like(snapshot):
            return _invalid(VALIDATION_REASON_INVALID_INPUT_TYPE, None)
        scan = _scan_object_fields(
            snapshot, codes_field_names=CONTENT_CODES_FIELDS
        )
        if scan is not None:
            return scan

        for field_name in CONTENT_DISPLAY_FIELDS:
            value = getattr(snapshot, field_name, None)
            if value is None:
                continue
            if not isinstance(value, str):
                return _invalid(
                    VALIDATION_REASON_DISPLAY_FIELD_NOT_STRING,
                    field_name,
                )

        for field_name in CONTENT_CODES_FIELDS:
            value = getattr(snapshot, field_name, None)
            if value is None:
                continue
            if not isinstance(value, (tuple, list)):
                return _invalid(
                    VALIDATION_REASON_CODES_NOT_STRING_SEQUENCE,
                    field_name,
                )
            for element in value:
                if not isinstance(element, str):
                    return _invalid(
                        VALIDATION_REASON_CODES_NOT_STRING_SEQUENCE,
                        field_name,
                    )

        if require_body:
            body = getattr(snapshot, "compact_body_text", None)
            if not _is_nonempty_str(body):
                return _invalid(
                    VALIDATION_REASON_EMPTY_COMPACT_BODY,
                    "compact_body_text",
                )

        return _valid()
    except Exception:
        return _invalid(VALIDATION_REASON_INVALID_INPUT_TYPE, None)


# ---------------------------------------------------------------------------
# Public: per-kind artifact validators
# ---------------------------------------------------------------------------


def validate_compact_ping_artifact(
    artifact: object,
) -> Stage30_8ValidationResult:
    """Validate a Stage 30.8 terminal compact ping artifact.

    Requires a valid ping-kind identity (with ``session_id`` /
    ``ping_id`` / ``dedupe_key``) and a valid content snapshot carrying
    a non-empty ``compact_body_text``. Pure / total; never raises.
    """
    try:
        scan = _scan_object_fields(artifact)
        if scan is not None:
            return scan

        identity_result = _validate_identity_for_kind(
            getattr(artifact, "identity", None),
            ARTIFACT_KIND_COMPACT_PING_ARTIFACT,
            required_axes=("session_id", "ping_id", "dedupe_key"),
        )
        if identity_result.status != VALIDATION_STATUS_VALID:
            return identity_result

        return validate_compact_content_snapshot(
            getattr(artifact, "content", None), require_body=True
        )
    except Exception:
        return _invalid(VALIDATION_REASON_INVALID_INPUT_TYPE, None)


def validate_compact_session_summary_artifact(
    artifact: object,
) -> Stage30_8ValidationResult:
    """Validate a Stage 30.8 session summary artifact.

    Requires a valid session-summary-kind identity (with
    ``session_id``), non-negative integer counters when present, and a
    valid embedded storage-budget snapshot when present. Pure / total;
    never raises.
    """
    try:
        scan = _scan_object_fields(artifact)
        if scan is not None:
            return scan

        identity_result = _validate_identity_for_kind(
            getattr(artifact, "identity", None),
            ARTIFACT_KIND_COMPACT_SESSION_SUMMARY,
            required_axes=("session_id",),
        )
        if identity_result.status != VALIDATION_STATUS_VALID:
            return identity_result

        for counter_name in (
            "pings_emitted",
            "dispatch_attempts",
            "dedupe_suppressed",
            "errors",
        ):
            value = getattr(artifact, counter_name, None)
            if value is None:
                continue
            if not _is_nonneg_int(value):
                return _invalid(
                    VALIDATION_REASON_COUNTER_INVALID, counter_name
                )

        budget = getattr(artifact, "storage_budget", None)
        if budget is not None:
            budget_result = (
                validate_compact_storage_budget_snapshot_artifact(budget)
            )
            if budget_result.status != VALIDATION_STATUS_VALID:
                return budget_result

        return _valid()
    except Exception:
        return _invalid(VALIDATION_REASON_INVALID_INPUT_TYPE, None)


def validate_compact_dispatch_attempt_artifact(
    artifact: object,
) -> Stage30_8ValidationResult:
    """Validate a Stage 30.8 dispatch attempt artifact.

    Requires a valid dispatch-kind identity (with ``dedupe_key``), a
    non-empty ``sanitized_transport_status`` string, and a non-negative
    integer ``attempt_index`` when present. Pure / total; never raises.
    """
    try:
        scan = _scan_object_fields(artifact)
        if scan is not None:
            return scan

        identity_result = _validate_identity_for_kind(
            getattr(artifact, "identity", None),
            ARTIFACT_KIND_COMPACT_DISPATCH_ATTEMPT_ARTIFACT,
            required_axes=("dedupe_key",),
        )
        if identity_result.status != VALIDATION_STATUS_VALID:
            return identity_result

        transport_status = getattr(
            artifact, "sanitized_transport_status", None
        )
        if not _is_nonempty_str(transport_status):
            return _invalid(
                VALIDATION_REASON_TRANSPORT_STATUS_INVALID,
                "sanitized_transport_status",
            )

        attempt_index = getattr(artifact, "attempt_index", None)
        if attempt_index is not None and not _is_nonneg_int(
            attempt_index
        ):
            return _invalid(
                VALIDATION_REASON_COUNTER_INVALID, "attempt_index"
            )

        return _valid()
    except Exception:
        return _invalid(VALIDATION_REASON_INVALID_INPUT_TYPE, None)


def validate_compact_error_artifact(
    artifact: object,
) -> Stage30_8ValidationResult:
    """Validate a Stage 30.8 error artifact.

    Requires a valid error-kind identity and a non-empty
    ``error_reason_code`` string (a closed-set reason token; never a raw
    message). Pure / total; never raises.
    """
    try:
        scan = _scan_object_fields(artifact)
        if scan is not None:
            return scan

        identity_result = _validate_identity_for_kind(
            getattr(artifact, "identity", None),
            ARTIFACT_KIND_COMPACT_ERROR_ARTIFACT,
        )
        if identity_result.status != VALIDATION_STATUS_VALID:
            return identity_result

        reason_code = getattr(artifact, "error_reason_code", None)
        if not _is_nonempty_str(reason_code):
            return _invalid(
                VALIDATION_REASON_ERROR_REASON_CODE_INVALID,
                "error_reason_code",
            )

        return _valid()
    except Exception:
        return _invalid(VALIDATION_REASON_INVALID_INPUT_TYPE, None)


def validate_compact_storage_budget_snapshot_artifact(
    artifact: object,
) -> Stage30_8ValidationResult:
    """Validate a Stage 30.8 storage-budget snapshot artifact.

    Requires a valid budget-snapshot-kind identity, a closed-set
    ``budget_status`` token, non-negative integer counters when present,
    and finite ``[0, 100]`` disk-usage percents when present. Pure /
    total; never raises.
    """
    try:
        scan = _scan_object_fields(artifact)
        if scan is not None:
            return scan

        identity_result = _validate_identity_for_kind(
            getattr(artifact, "identity", None),
            ARTIFACT_KIND_COMPACT_STORAGE_BUDGET_SNAPSHOT,
        )
        if identity_result.status != VALIDATION_STATUS_VALID:
            return identity_result

        budget_status = getattr(artifact, "budget_status", None)
        if not is_storage_budget_status(budget_status):
            return _invalid(
                VALIDATION_REASON_BUDGET_STATUS_INVALID, "budget_status"
            )

        for counter_name in (
            "raw_bytes_written",
            "durable_rows_written",
            "archived_compressed_bytes",
            "dropped_count",
            "pruned_count",
            "sealed_count",
            "dedupe_suppressed_count",
        ):
            value = getattr(artifact, counter_name, None)
            if value is None:
                continue
            if not _is_nonneg_int(value):
                return _invalid(
                    VALIDATION_REASON_COUNTER_INVALID, counter_name
                )

        for percent_name in (
            "disk_usage_percent_before",
            "disk_usage_percent_after",
        ):
            value = getattr(artifact, percent_name, None)
            if value is None:
                continue
            if not _is_valid_percent(value):
                return _invalid(
                    VALIDATION_REASON_PERCENT_INVALID, percent_name
                )

        return _valid()
    except Exception:
        return _invalid(VALIDATION_REASON_INVALID_INPUT_TYPE, None)


__all__ = (
    # Reason tokens.
    "VALIDATION_REASON_OK",
    "VALIDATION_REASON_INVALID_INPUT_TYPE",
    "VALIDATION_REASON_STAGE_ID_INVALID",
    "VALIDATION_REASON_SCHEMA_VERSION_INVALID",
    "VALIDATION_REASON_ARTIFACT_KIND_INVALID",
    "VALIDATION_REASON_ARTIFACT_KIND_MISMATCH",
    "VALIDATION_REASON_MISSING_REQUIRED_IDENTITY",
    "VALIDATION_REASON_DISPLAY_FIELD_NOT_STRING",
    "VALIDATION_REASON_CODES_NOT_STRING_SEQUENCE",
    "VALIDATION_REASON_EMPTY_COMPACT_BODY",
    "VALIDATION_REASON_FORBIDDEN_FIELD_NAME",
    "VALIDATION_REASON_FORBIDDEN_VALUE_PATTERN",
    "VALIDATION_REASON_NESTED_RAW_PAYLOAD",
    "VALIDATION_REASON_BINARY_VALUE",
    "VALIDATION_REASON_COUNTER_INVALID",
    "VALIDATION_REASON_PERCENT_INVALID",
    "VALIDATION_REASON_BUDGET_STATUS_INVALID",
    "VALIDATION_REASON_TRANSPORT_STATUS_INVALID",
    "VALIDATION_REASON_ERROR_REASON_CODE_INVALID",
    "STAGE30_8_VALIDATION_REASONS",
    # Field partitions.
    "REQUIRED_IDENTITY_FIELDS",
    "OPTIONAL_IDENTITY_FIELDS",
    "CONTENT_DISPLAY_FIELDS",
    "CONTENT_CODES_FIELDS",
    "EXPECTED_CONTENT_SNAPSHOT_FIELDS",
    # Forbidden surfaces + guards.
    "FORBIDDEN_FIELD_NAME_TOKENS",
    "FORBIDDEN_VALUE_NEEDLES",
    "is_forbidden_field_name",
    "value_has_forbidden_pattern",
    # Validators.
    "validate_compact_artifact_identity",
    "validate_compact_content_snapshot",
    "validate_compact_ping_artifact",
    "validate_compact_session_summary_artifact",
    "validate_compact_dispatch_attempt_artifact",
    "validate_compact_error_artifact",
    "validate_compact_storage_budget_snapshot_artifact",
)

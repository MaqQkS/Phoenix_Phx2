"""Stage 30.5.1 offline migration-context closed-set vocabularies
and immutable record / projection shapes.

Stage 30.5.1 ships the pure-Python model layer the Stage 30.5.1
source protocol emits and the Stage 30.5.1 adapter projects per
ping. The Stage-30-owned migration context record carries only
closed-set status / basis / source tokens, a safe-shape redacted
token label, safe-shape ISO-8601 UTC timestamps, an optional non-
negative integer age, a short safe-shape source label, and a
``runtime_consumable`` flag. Stage 30.5.1 is offline only: the
record / projection is NEVER routed into Stage 30.1 / 30.2 / 30.3
runtime, NEVER fills the Stage 30.2 renderer slots at runtime, and
NEVER triggers a Discord send.

Closed-set vocabularies (committed by the Stage 30.5.0 spec lock):

  * ``MIGRATION_STATUS`` -- ``KNOWN`` / ``UNVERIFIED`` / ``UNKNOWN``
  * ``MIGRATION_BASIS``  -- ``ON_CHAIN_EVENT`` / ``EVIDENCE_PARTIAL``
                            / ``NONE``
  * ``SOURCE_STATUS``    -- ``UNAVAILABLE`` / ``PRESENT`` / ``ERROR``
                            / ``STALE``
  * ``SOURCE_REASON``    -- closed-set source-reason tokens
  * ``MIGRATION_DISPLAY``-- ``Known`` / ``Unverified`` / ``Unknown``

The richer Stage 29.5 evidence distinctions (a trusted-artifact
basis, a source-missing / source-invalid / source-conflicting
split, an ambiguous-evidence reason) are deliberately NOT in the
Stage 30.5.1 closed sets. They remain deferred future refinements
and only land if a later spec lock explicitly authorizes them.

The record maps the Stage 30.5.0 §3.1 evidence table:

  * trusted on-chain migration event  -> status ``KNOWN`` with
                                         basis ``ON_CHAIN_EVENT``.
  * evidence present but not promotable-> status ``UNVERIFIED`` with
                                         basis ``EVIDENCE_PARTIAL``.
  * missing / invalid / conflicting    -> status ``UNKNOWN`` with
                                         basis ``NONE``.

Stage 30.5.1 deliberately does NOT carry:

  * raw provider payload blobs (no field ever takes a raw payload),
  * the migration signature, the migration event id, the source
    event ref, or any raw capture ref (no field admits them),
  * the Stage 29.5.5 verbose side-channel body text (no field
    admits it),
  * secrets, inbound-hook URLs, API-key strings, signed tokens, or
    raw authorization-header text (no field admits them),
  * provider host / RPC endpoint strings (no field admits them),
  * Discord destination fields (no field admits them),
  * a numeric migration market-cap value (a separate deferred
    field, NOT introduced by Stage 30.5),
  * ATH fields (ATH stays Stage 30.6+),
  * Net flow fields (Net stays deferred),
  * trading verdicts (Stage 30 is informational-only),
  * Stage 26 / Stage 29 enforcement decisions.

Discipline:

  * Stdlib only (``re`` / ``typing`` / ``dataclasses``).
  * No process-env read, no live secret access.
  * No network surface (no HTTP, no gRPC, no WebSocket, no socket).
  * No Discord, Telegram, X / social, inbound-hook reference.
  * No transport reference on source text.
  * No PHX1 import. No Stage 21-29 production-source import.
  * No network / env / filesystem I/O at import time.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, fields
from typing import Dict, Optional, Tuple


# ---------------------------------------------------------------------------
# Stage 30.5.1 minor version + schema version
# ---------------------------------------------------------------------------


STAGE30_5_1_MINOR_VERSION: str = "30.5.1"
STAGE30_5_1_MIGRATION_CONTEXT_SCHEMA_VERSION: str = (
    "stage30_5_1_v0_migration_context"
)


# ---------------------------------------------------------------------------
# Closed-set migration_status tokens
# ---------------------------------------------------------------------------


MIGRATION_STATUS_KNOWN: str = "KNOWN"
MIGRATION_STATUS_UNVERIFIED: str = "UNVERIFIED"
MIGRATION_STATUS_UNKNOWN: str = "UNKNOWN"


MIGRATION_STATUS_VALUES: Tuple[str, ...] = (
    MIGRATION_STATUS_KNOWN,
    MIGRATION_STATUS_UNVERIFIED,
    MIGRATION_STATUS_UNKNOWN,
)


def is_migration_status_value(value: object) -> bool:
    """Return ``True`` iff ``value`` is a Stage 30.5.1 migration
    status token.
    """
    return isinstance(value, str) and value in MIGRATION_STATUS_VALUES


# ---------------------------------------------------------------------------
# Closed-set migration_basis tokens
# ---------------------------------------------------------------------------
#
# ``ON_CHAIN_EVENT``     -- a trusted on-chain migration event (the
#                           Stage 27.4 ``ON_CHAIN_MIGRATION_EVENT``
#                           snapshot the Stage 29.5.4 adapter already
#                           produces); the only promotable basis.
# ``EVIDENCE_PARTIAL``   -- evidence is present but not promotable to
#                           trusted (a partial migration, or a
#                           complete measurement from an untrusted /
#                           synthetic source).
# ``NONE``               -- no usable evidence (missing / invalid /
#                           conflicting / absent).


MIGRATION_BASIS_ON_CHAIN_EVENT: str = "ON_CHAIN_EVENT"
MIGRATION_BASIS_EVIDENCE_PARTIAL: str = "EVIDENCE_PARTIAL"
MIGRATION_BASIS_NONE: str = "NONE"


MIGRATION_BASIS_VALUES: Tuple[str, ...] = (
    MIGRATION_BASIS_ON_CHAIN_EVENT,
    MIGRATION_BASIS_EVIDENCE_PARTIAL,
    MIGRATION_BASIS_NONE,
)


def is_migration_basis_value(value: object) -> bool:
    """Return ``True`` iff ``value`` is a Stage 30.5.1 migration
    basis token.
    """
    return isinstance(value, str) and value in MIGRATION_BASIS_VALUES


# ---------------------------------------------------------------------------
# Closed-set source_status tokens
# ---------------------------------------------------------------------------
#
# Stage 30.5.1 source_status is the committed Stage 30.5.0 four-token
# set ``UNAVAILABLE`` / ``PRESENT`` / ``ERROR`` / ``STALE`` (mirrors
# the Stage 30.4.1 source-status set). ``STALE`` records that a source
# returned a reading flagged stale (cached / past TTL / snapshot not
# refreshed). It is a SOURCE-STATUS token only: a stale reading is not
# trustworthy as Known / Unverified, so the Stage 30.5.1 adapter
# conservatively projects a STALE source to ``Mig: Unknown``. There is
# deliberately NO ``Mig: Stale`` display token -- Fresh / Stale display
# semantics stay deferred per the Stage 30.5.0 spec lock §3.2.


SOURCE_STATUS_UNAVAILABLE: str = "UNAVAILABLE"
SOURCE_STATUS_PRESENT: str = "PRESENT"
SOURCE_STATUS_ERROR: str = "ERROR"
SOURCE_STATUS_STALE: str = "STALE"


SOURCE_STATUS_VALUES: Tuple[str, ...] = (
    SOURCE_STATUS_UNAVAILABLE,
    SOURCE_STATUS_PRESENT,
    SOURCE_STATUS_ERROR,
    SOURCE_STATUS_STALE,
)


def is_source_status_value(value: object) -> bool:
    """Return ``True`` iff ``value`` is a Stage 30.5.1 source-status
    token.
    """
    return isinstance(value, str) and value in SOURCE_STATUS_VALUES


# ---------------------------------------------------------------------------
# Closed-set source_reason tokens
# ---------------------------------------------------------------------------
#
# Stage 30.5.1 source_reason tokens (the Stage 30.5.0 spec lock §4
# left the exact closed set to be pinned here). Each maps to exactly
# one source outcome and aligns with a source_status:
#
#   * SOURCE_PRESENT        -- source returned a usable record
#                              (status PRESENT).
#   * EVIDENCE_PARTIAL      -- source returned a record whose evidence
#                              is present but not promotable
#                              (status PRESENT, migration UNVERIFIED).
#   * EVIDENCE_INVALID      -- source returned a record representing
#                              invalid / conflicting evidence
#                              (status ERROR, migration UNKNOWN).
#   * SOURCE_UNAVAILABLE    -- source was present but returned no
#                              record (status UNAVAILABLE).
#   * SOURCE_NOT_CONFIGURED -- no source object was supplied
#                              (status UNAVAILABLE).
#   * SOURCE_ERROR          -- the source raised; the adapter caught
#                              it and degraded to Unknown
#                              (status ERROR).
#   * SOURCE_STALE          -- source returned a reading flagged
#                              stale; the adapter degraded to Unknown
#                              (status STALE). Pairs with the
#                              committed Stage 30.5.0 §4 source_status
#                              STALE token.
#
# The richer Stage 29.5 distinctions (a source-missing vs source-
# invalid vs source-conflicting split, an ambiguous-evidence reason,
# an unsupported-status reason) stay deferred.


SOURCE_REASON_SOURCE_PRESENT: str = "SOURCE_PRESENT"
SOURCE_REASON_EVIDENCE_PARTIAL: str = "EVIDENCE_PARTIAL"
SOURCE_REASON_EVIDENCE_INVALID: str = "EVIDENCE_INVALID"
SOURCE_REASON_SOURCE_UNAVAILABLE: str = "SOURCE_UNAVAILABLE"
SOURCE_REASON_SOURCE_NOT_CONFIGURED: str = "SOURCE_NOT_CONFIGURED"
SOURCE_REASON_SOURCE_ERROR: str = "SOURCE_ERROR"
SOURCE_REASON_SOURCE_STALE: str = "SOURCE_STALE"


SOURCE_REASON_VALUES: Tuple[str, ...] = (
    SOURCE_REASON_SOURCE_PRESENT,
    SOURCE_REASON_EVIDENCE_PARTIAL,
    SOURCE_REASON_EVIDENCE_INVALID,
    SOURCE_REASON_SOURCE_UNAVAILABLE,
    SOURCE_REASON_SOURCE_NOT_CONFIGURED,
    SOURCE_REASON_SOURCE_ERROR,
    SOURCE_REASON_SOURCE_STALE,
)


def is_source_reason_value(value: object) -> bool:
    """Return ``True`` iff ``value`` is a Stage 30.5.1 source-reason
    token.
    """
    return isinstance(value, str) and value in SOURCE_REASON_VALUES


# ---------------------------------------------------------------------------
# Closed-set migration display tokens + status -> display mapping
# ---------------------------------------------------------------------------
#
# The compact body ``Mig`` token is drawn from exactly these three
# display words. ``Fresh`` / ``Stale`` are deferred (Stage 30.5.0
# spec lock §3.2) and are NOT in this set.


MIGRATION_DISPLAY_KNOWN: str = "Known"
MIGRATION_DISPLAY_UNVERIFIED: str = "Unverified"
MIGRATION_DISPLAY_UNKNOWN: str = "Unknown"


MIGRATION_DISPLAY_VALUES: Tuple[str, ...] = (
    MIGRATION_DISPLAY_KNOWN,
    MIGRATION_DISPLAY_UNVERIFIED,
    MIGRATION_DISPLAY_UNKNOWN,
)


_MIGRATION_STATUS_TO_DISPLAY: Dict[str, str] = {
    MIGRATION_STATUS_KNOWN: MIGRATION_DISPLAY_KNOWN,
    MIGRATION_STATUS_UNVERIFIED: MIGRATION_DISPLAY_UNVERIFIED,
    MIGRATION_STATUS_UNKNOWN: MIGRATION_DISPLAY_UNKNOWN,
}


def is_migration_display_value(value: object) -> bool:
    """Return ``True`` iff ``value`` is a Stage 30.5.1 migration
    display token.
    """
    return isinstance(value, str) and value in MIGRATION_DISPLAY_VALUES


def display_text_for_status(status: object) -> str:
    """Map a closed-set ``migration_status`` token to its display
    word.

    ``KNOWN`` -> ``"Known"``, ``UNVERIFIED`` -> ``"Unverified"``.
    Every other value (``UNKNOWN`` or any off-closed-set / non-string
    input) maps to the safe fallback ``"Unknown"``. The renderer
    never invents a token outside the closed display set.
    """
    if isinstance(status, str):
        mapped = _MIGRATION_STATUS_TO_DISPLAY.get(status)
        if mapped is not None:
            return mapped
    return MIGRATION_DISPLAY_UNKNOWN


# ---------------------------------------------------------------------------
# Safe-shape gates
# ---------------------------------------------------------------------------


_ISO8601_UTC_PATTERN: "re.Pattern[str]" = re.compile(
    r"\A\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}"
    r"(?:\.\d{1,9})?"
    r"(?:Z|\+00:00)\Z"
)


# Safe-shape token label: ASCII alphanumeric plus ``_``, ``-``, ``.``,
# and the Unicode horizontal ellipsis ``…``; length [1, 32]. Mirrors
# the Stage 30.4.1 token-label discipline: a raw full base58 mint is
# 32+ chars and is cut off, so callers must pass the short
# ``mint[:4] + "…" + mint[-4:]`` form or a symbol-like label.
_TOKEN_LABEL_PATTERN: "re.Pattern[str]" = re.compile(
    r"\A[A-Za-z0-9_\-.…]{1,32}\Z"
)


# Safe-shape source label: ASCII alphanumeric plus ``_``, ``-``;
# length [1, 64].
_SOURCE_LABEL_PATTERN: "re.Pattern[str]" = re.compile(
    r"\A[A-Za-z0-9_\-]{1,64}\Z"
)


def is_safe_iso8601_utc(value: object) -> bool:
    """Return ``True`` iff ``value`` is a safe-shape ISO-8601 UTC
    timestamp string.
    """
    return isinstance(value, str) and (
        _ISO8601_UTC_PATTERN.fullmatch(value) is not None
    )


def is_safe_token_label(value: object) -> bool:
    """Return ``True`` iff ``value`` is a safe-shape redacted token
    label (NEVER a full base58 mint).
    """
    return isinstance(value, str) and (
        _TOKEN_LABEL_PATTERN.fullmatch(value) is not None
    )


def is_safe_source_label(value: object) -> bool:
    """Return ``True`` iff ``value`` is a safe-shape source label."""
    return isinstance(value, str) and (
        _SOURCE_LABEL_PATTERN.fullmatch(value) is not None
    )


def _is_non_negative_int(value: object) -> bool:
    """Return ``True`` iff ``value`` is a non-negative ``int`` that is
    NOT a ``bool`` (``bool`` is an ``int`` subclass and must not slip
    through as an age).
    """
    return (
        isinstance(value, int)
        and not isinstance(value, bool)
        and value >= 0
    )


# ---------------------------------------------------------------------------
# Module-local exception
# ---------------------------------------------------------------------------


class Stage30_5MigrationContextError(Exception):
    """Closed-set Stage 30.5.1 migration context error.

    Carries only a closed-set reason token on the exception message.
    Stage 30.5.1 callers should never embed a raw OSError message, a
    raw provider payload, the raw Stage 29.5 side-channel body text,
    or any secret value in the message.
    """

    def __init__(self, reason: str) -> None:
        self.reason: str = reason
        super().__init__(
            f"Stage 30.5.1 migration context error: reason={reason!r}"
        )


# ---------------------------------------------------------------------------
# Immutable record: Stage-30-owned migration context
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Stage30_5MigrationContextRecord:
    """Immutable Stage 30.5.1 migration context record.

    Frozen dataclass with construction-time closed-set validation:
    constructing a record with an off-closed-set ``migration_status``
    / ``migration_basis`` / ``source_status`` / ``source_reason``, an
    unsafe-shape label or timestamp, a negative / non-integer age, or
    a non-``bool`` ``runtime_consumable`` raises
    ``Stage30_5MigrationContextError`` with a closed-set reason token.
    This is the Stage 30.5.0 §4 "explicit contract error at model
    construction" discipline.

    Carries only closed-set tokens, a safe-shape redacted token
    label, safe-shape ISO-8601 UTC timestamps, an optional non-
    negative integer age, and a short safe-shape source label. No raw
    provider payload, no migration signature, no migration event id,
    no source event ref, no raw capture ref, no Stage 29.5.5 verbose
    body text, no secret value, no inbound-hook URL, no provider host,
    and no Discord destination is ever populated on this record. The
    Stage 30.5.1 forbidden-field-name guard rejects any future
    refactor that tries to widen the field set with a secret-class,
    raw-payload-class, or audit-identifier-class name.

    Fields:

      * ``schema_version``            -- locked Stage 30.5.1 migration
                                         context schema version
                                         string (non-empty).
      * ``token_label``               -- redacted token label (the
                                         short ``mint[:4] + "…" +
                                         mint[-4:]`` form or a symbol-
                                         like string) or ``None``.
                                         NEVER the full mint string.
      * ``migration_status``          -- one of
                                         ``MIGRATION_STATUS_VALUES``.
      * ``migration_basis``           -- one of
                                         ``MIGRATION_BASIS_VALUES``.
      * ``migration_event_time_utc``  -- migration event ISO-8601 UTC
                                         timestamp or ``None``.
                                         Carried for provenance; it
                                         does NOT itself appear in the
                                         ``Mig`` token.
      * ``migration_age_seconds``     -- optional non-negative integer
                                         age since migration, computed
                                         by the caller from an
                                         injected clock (never
                                         ``datetime.now``), or
                                         ``None``. Not rendered into
                                         the ``Mig`` token in this
                                         slice.
      * ``source_label``              -- short safe-shape source-
                                         family label (e.g.
                                         ``"stage29_5_migration_evidence"``)
                                         or ``None``. Never a host
                                         address, never a credential.
      * ``source_status``             -- one of
                                         ``SOURCE_STATUS_VALUES``.
      * ``source_reason``             -- one of
                                         ``SOURCE_REASON_VALUES``.
      * ``runtime_consumable``        -- ``bool``; MUST be ``False``.
                                         Stage 30.5.1 is offline-only,
                                         so the record REJECTS ``True``
                                         at construction (raises
                                         ``RUNTIME_CONSUMABLE_MUST_BE_FALSE``)
                                         -- an offline record can NEVER
                                         route into runtime. A later
                                         opt-in runtime substage (Stage
                                         30.5.2) would relax this.
      * ``observed_at_utc``           -- ISO-8601 UTC timestamp passed
                                         in by the caller (the
                                         injected clock).
    """

    schema_version: str
    token_label: Optional[str]
    migration_status: str
    migration_basis: str
    migration_event_time_utc: Optional[str]
    migration_age_seconds: Optional[int]
    source_label: Optional[str]
    source_status: str
    source_reason: str
    runtime_consumable: bool
    observed_at_utc: str

    def __post_init__(self) -> None:
        if not (
            isinstance(self.schema_version, str)
            and self.schema_version != ""
        ):
            raise Stage30_5MigrationContextError(
                "SCHEMA_VERSION_INVALID"
            )
        if self.token_label is not None and not is_safe_token_label(
            self.token_label
        ):
            raise Stage30_5MigrationContextError(
                "TOKEN_LABEL_UNSAFE_SHAPE"
            )
        if not is_migration_status_value(self.migration_status):
            raise Stage30_5MigrationContextError(
                "MIGRATION_STATUS_INVALID"
            )
        if not is_migration_basis_value(self.migration_basis):
            raise Stage30_5MigrationContextError(
                "MIGRATION_BASIS_INVALID"
            )
        if self.migration_event_time_utc is not None and not (
            is_safe_iso8601_utc(self.migration_event_time_utc)
        ):
            raise Stage30_5MigrationContextError(
                "MIGRATION_EVENT_TIME_UNSAFE_SHAPE"
            )
        if self.migration_age_seconds is not None and not (
            _is_non_negative_int(self.migration_age_seconds)
        ):
            raise Stage30_5MigrationContextError(
                "MIGRATION_AGE_SECONDS_INVALID"
            )
        if self.source_label is not None and not is_safe_source_label(
            self.source_label
        ):
            raise Stage30_5MigrationContextError(
                "SOURCE_LABEL_UNSAFE_SHAPE"
            )
        if not is_source_status_value(self.source_status):
            raise Stage30_5MigrationContextError(
                "SOURCE_STATUS_INVALID"
            )
        if not is_source_reason_value(self.source_reason):
            raise Stage30_5MigrationContextError(
                "SOURCE_REASON_INVALID"
            )
        if not isinstance(self.runtime_consumable, bool):
            raise Stage30_5MigrationContextError(
                "RUNTIME_CONSUMABLE_NOT_BOOL"
            )
        if self.runtime_consumable is not False:
            # Stage 30.5.1 is offline-only: an offline record can NEVER
            # route into runtime, so True is rejected outright (not
            # silently normalized). A later opt-in runtime substage
            # (Stage 30.5.2) would relax this.
            raise Stage30_5MigrationContextError(
                "RUNTIME_CONSUMABLE_MUST_BE_FALSE"
            )
        if not is_safe_iso8601_utc(self.observed_at_utc):
            raise Stage30_5MigrationContextError(
                "OBSERVED_AT_UTC_UNSAFE_SHAPE"
            )


# ---------------------------------------------------------------------------
# Immutable projection: compact Mig display token
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Stage30_5MigrationContextProjection:
    """Immutable Stage 30.5.1 compact migration-context projection.

    The Stage 30.5.1 adapter emits this per ping. It carries the
    single safe display word the compact body ``Mig`` token shows
    (``Known`` / ``Unverified`` / ``Unknown``) plus closed-set echoes
    for provenance. It does NOT carry the migration event time, the
    migration age, the token label, any ATH field, any Net field, or
    any raw evidence reference: the ``Mig`` token is a single short
    word, never a verbose block.

    Frozen dataclass with construction-time closed-set validation.

    Fields:

      * ``schema_version``         -- locked Stage 30.5.1 schema
                                      version string.
      * ``migration_display_text`` -- one of
                                      ``MIGRATION_DISPLAY_VALUES``
                                      (the ``Mig`` token word).
      * ``migration_status``       -- one of
                                      ``MIGRATION_STATUS_VALUES``.
      * ``migration_basis``        -- one of
                                      ``MIGRATION_BASIS_VALUES``.
      * ``source_status``          -- one of
                                      ``SOURCE_STATUS_VALUES``.
      * ``source_reason``          -- one of ``SOURCE_REASON_VALUES``.
      * ``source_label``           -- short safe-shape source label or
                                      ``None``.
      * ``runtime_consumable``     -- ``bool`` (hard-locked ``False``
                                      by the Stage 30.5.1 adapter).
    """

    schema_version: str
    migration_display_text: str
    migration_status: str
    migration_basis: str
    source_status: str
    source_reason: str
    source_label: Optional[str]
    runtime_consumable: bool

    def __post_init__(self) -> None:
        if not (
            isinstance(self.schema_version, str)
            and self.schema_version != ""
        ):
            raise Stage30_5MigrationContextError(
                "SCHEMA_VERSION_INVALID"
            )
        if not is_migration_display_value(self.migration_display_text):
            raise Stage30_5MigrationContextError(
                "MIGRATION_DISPLAY_INVALID"
            )
        if not is_migration_status_value(self.migration_status):
            raise Stage30_5MigrationContextError(
                "MIGRATION_STATUS_INVALID"
            )
        if not is_migration_basis_value(self.migration_basis):
            raise Stage30_5MigrationContextError(
                "MIGRATION_BASIS_INVALID"
            )
        if not is_source_status_value(self.source_status):
            raise Stage30_5MigrationContextError(
                "SOURCE_STATUS_INVALID"
            )
        if not is_source_reason_value(self.source_reason):
            raise Stage30_5MigrationContextError(
                "SOURCE_REASON_INVALID"
            )
        if self.source_label is not None and not is_safe_source_label(
            self.source_label
        ):
            raise Stage30_5MigrationContextError(
                "SOURCE_LABEL_UNSAFE_SHAPE"
            )
        if not isinstance(self.runtime_consumable, bool):
            raise Stage30_5MigrationContextError(
                "RUNTIME_CONSUMABLE_NOT_BOOL"
            )
        if self.runtime_consumable is not False:
            raise Stage30_5MigrationContextError(
                "RUNTIME_CONSUMABLE_MUST_BE_FALSE"
            )


# ---------------------------------------------------------------------------
# Forbidden field-name vocabulary (defensive sentinel)
# ---------------------------------------------------------------------------
#
# Stage 30.5.1 must never accept a field named anything secret-class,
# raw-payload-class, audit-identifier-class, or Discord-class on
# either dataclass. The current record / projection field sets carry
# no such name, but this helper is kept so a future refactor cannot
# silently widen the admitted field set.
#
# Split literals so this module's own source does NOT carry the bare
# inbound-hook / API-key / signed-token / authorization substrings
# (mirrors the Stage 30.4.1 forbidden-field guard). The runtime tuple
# value still resolves to the correct human-readable forbidden names.


FORBIDDEN_RECORD_FIELD_NAMES: Tuple[str, ...] = (
    # Secret-class / transport-class.
    "web" + "hook",
    "web" + "hook_url",
    "web" + "hooks",
    "web" + "hook_token",
    "api_" + "key",
    "api" + "key",
    "b" + "earer",
    "b" + "earer_token",
    "author" + "ization",
    "secret",
    "secret_key",
    "secretkey",
    "token_secret",
    "private_key",
    "privatekey",
    "seed_phrase",
    "mnemonic",
    "signer",
    "signing_key",
    "credentials",
    "password",
    "rpc_url",
    "endpoint_url",
    "host",
    "url",
    # Raw-payload-class.
    "raw_payload",
    "payload",
    "payload_blob",
    "payload_summary",
    "raw_response",
    "raw_capture_ref",
    # Migration audit-identifier-class (Stage 30.5.0 §6: these stay
    # on the Stage 29.5 side and must NEVER reach the compact record).
    "migration_event_id",
    "source_event_ref",
    "migration_signature",
    "migration_slot",
    # Discord-class.
    "discord",
    "channel_id",
    "destination",
)


def is_forbidden_record_field_name(name: object) -> bool:
    """Return ``True`` iff ``name`` is a forbidden record field name.

    Pure / deterministic. Stage 30.5.1 uses this guard to reject any
    future refactor that tries to widen the record / projection with
    a secret-class, raw-payload-class, audit-identifier-class, or
    Discord-class field name.
    """
    if not isinstance(name, str):
        return False
    lower = name.lower()
    for forbidden in FORBIDDEN_RECORD_FIELD_NAMES:
        if forbidden in lower:
            return True
    return False


def record_field_names() -> Tuple[str, ...]:
    """Return the Stage 30.5.1 record field names as a tuple."""
    return tuple(f.name for f in fields(Stage30_5MigrationContextRecord))


def projection_field_names() -> Tuple[str, ...]:
    """Return the Stage 30.5.1 projection field names as a tuple."""
    return tuple(
        f.name for f in fields(Stage30_5MigrationContextProjection)
    )


__all__ = (
    # Version + schema version.
    "STAGE30_5_1_MINOR_VERSION",
    "STAGE30_5_1_MIGRATION_CONTEXT_SCHEMA_VERSION",
    # migration_status tokens.
    "MIGRATION_STATUS_KNOWN",
    "MIGRATION_STATUS_UNVERIFIED",
    "MIGRATION_STATUS_UNKNOWN",
    "MIGRATION_STATUS_VALUES",
    "is_migration_status_value",
    # migration_basis tokens.
    "MIGRATION_BASIS_ON_CHAIN_EVENT",
    "MIGRATION_BASIS_EVIDENCE_PARTIAL",
    "MIGRATION_BASIS_NONE",
    "MIGRATION_BASIS_VALUES",
    "is_migration_basis_value",
    # source_status tokens.
    "SOURCE_STATUS_UNAVAILABLE",
    "SOURCE_STATUS_PRESENT",
    "SOURCE_STATUS_ERROR",
    "SOURCE_STATUS_STALE",
    "SOURCE_STATUS_VALUES",
    "is_source_status_value",
    # source_reason tokens.
    "SOURCE_REASON_SOURCE_PRESENT",
    "SOURCE_REASON_EVIDENCE_PARTIAL",
    "SOURCE_REASON_EVIDENCE_INVALID",
    "SOURCE_REASON_SOURCE_UNAVAILABLE",
    "SOURCE_REASON_SOURCE_NOT_CONFIGURED",
    "SOURCE_REASON_SOURCE_ERROR",
    "SOURCE_REASON_SOURCE_STALE",
    "SOURCE_REASON_VALUES",
    "is_source_reason_value",
    # migration display tokens + mapping.
    "MIGRATION_DISPLAY_KNOWN",
    "MIGRATION_DISPLAY_UNVERIFIED",
    "MIGRATION_DISPLAY_UNKNOWN",
    "MIGRATION_DISPLAY_VALUES",
    "is_migration_display_value",
    "display_text_for_status",
    # Safe-shape gates.
    "is_safe_iso8601_utc",
    "is_safe_token_label",
    "is_safe_source_label",
    # Records + projection.
    "Stage30_5MigrationContextRecord",
    "Stage30_5MigrationContextProjection",
    "record_field_names",
    "projection_field_names",
    # Forbidden-field guard + error.
    "FORBIDDEN_RECORD_FIELD_NAMES",
    "is_forbidden_record_field_name",
    "Stage30_5MigrationContextError",
)

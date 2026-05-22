"""Stage 27.4 migration context closed-set vocabularies and
immutable record shape.

Stage 27.4 ships the in-memory model layer for the migration
context record that decorates a Stage 27.3 provider-ingest
composition output. The record carries only closed-set tokens and
safe-to-display canonical fields.

Closed-set vocabularies:

  * ``MIGRATION_STATUS``    -- ``PRESENT`` / ``MISSING`` /
                               ``UNTRUSTED`` / ``UNSUPPORTED_PAIR`` /
                               ``SOURCE_ERROR``
  * ``MIGRATION_REASON``    -- closed-set reason codes describing
                               the resolution path.

Stage 27.4 deliberately does NOT carry:

  * raw migration provider payload blobs (no field ever takes a
    raw payload),
  * secrets, webhook URLs, API keys (no field admits them),
  * Stage 26 policy decisions (Stage 26 is review-only).

This module imports only stdlib (``typing``). It does NOT import
Stage 21-26 production code, does NOT import Stage 27.1 production
code, does NOT import any network / RPC / messaging / DB /
scheduler / secrets-management library, does NOT read the process
environment, does NOT define a CLI surface, and contains no
top-level I/O.
"""

from __future__ import annotations

from typing import NamedTuple, Optional


# ---------------------------------------------------------------------------
# Stage 27.4 migration schema version
# ---------------------------------------------------------------------------


STAGE27_4_MIGRATION_SCHEMA_VERSION: str = (
    "stage27_v0_migration_context"
)


# ---------------------------------------------------------------------------
# migration_status closed set
# ---------------------------------------------------------------------------


MIGRATION_STATUS_PRESENT: str = "PRESENT"
MIGRATION_STATUS_MISSING: str = "MISSING"
MIGRATION_STATUS_UNTRUSTED: str = "UNTRUSTED"
MIGRATION_STATUS_UNSUPPORTED_PAIR: str = "UNSUPPORTED_PAIR"
MIGRATION_STATUS_SOURCE_ERROR: str = "SOURCE_ERROR"

MIGRATION_STATUS_VALUES: tuple[str, ...] = (
    MIGRATION_STATUS_PRESENT,
    MIGRATION_STATUS_MISSING,
    MIGRATION_STATUS_UNTRUSTED,
    MIGRATION_STATUS_UNSUPPORTED_PAIR,
    MIGRATION_STATUS_SOURCE_ERROR,
)


# ---------------------------------------------------------------------------
# migration_reason closed set
# ---------------------------------------------------------------------------


MIGRATION_REASON_OK: str = "OK"
MIGRATION_REASON_NO_MIGRATION_EVENT: str = "NO_MIGRATION_EVENT"
MIGRATION_REASON_MISSING_TIMESTAMP: str = "MISSING_TIMESTAMP"
MIGRATION_REASON_MALFORMED_TIMESTAMP: str = "MALFORMED_TIMESTAMP"
MIGRATION_REASON_SOURCE_FAILED: str = "SOURCE_FAILED"
MIGRATION_REASON_SOURCE_NOT_TRUSTED: str = "SOURCE_NOT_TRUSTED"
MIGRATION_REASON_UNKNOWN_PAIR_OBSERVE_ONLY: str = (
    "UNKNOWN_PAIR_OBSERVE_ONLY"
)
MIGRATION_REASON_DISAGREE_PAIR_OBSERVE_ONLY: str = (
    "DISAGREE_PAIR_OBSERVE_ONLY"
)
MIGRATION_REASON_INVALID_SOURCE_SNAPSHOT: str = (
    "INVALID_SOURCE_SNAPSHOT"
)

MIGRATION_REASON_VALUES: tuple[str, ...] = (
    MIGRATION_REASON_OK,
    MIGRATION_REASON_NO_MIGRATION_EVENT,
    MIGRATION_REASON_MISSING_TIMESTAMP,
    MIGRATION_REASON_MALFORMED_TIMESTAMP,
    MIGRATION_REASON_SOURCE_FAILED,
    MIGRATION_REASON_SOURCE_NOT_TRUSTED,
    MIGRATION_REASON_UNKNOWN_PAIR_OBSERVE_ONLY,
    MIGRATION_REASON_DISAGREE_PAIR_OBSERVE_ONLY,
    MIGRATION_REASON_INVALID_SOURCE_SNAPSHOT,
)


# ---------------------------------------------------------------------------
# Migration source-trust tiers (closed set, safe-to-display labels)
# ---------------------------------------------------------------------------
#
# Stage 27.4 records WHICH upstream gave the migration timestamp so
# downstream review can decide whether to trust it. The token set
# is closed; arbitrary upstream labels are not admitted.


MIGRATION_SOURCE_ON_CHAIN_MIGRATION_EVENT: str = (
    "ON_CHAIN_MIGRATION_EVENT"
)
MIGRATION_SOURCE_PROVIDER_ENRICHED: str = "PROVIDER_ENRICHED"
MIGRATION_SOURCE_OPERATOR_OVERRIDE: str = "OPERATOR_OVERRIDE"
MIGRATION_SOURCE_UNKNOWN: str = "UNKNOWN"

MIGRATION_SOURCE_VALUES: tuple[str, ...] = (
    MIGRATION_SOURCE_ON_CHAIN_MIGRATION_EVENT,
    MIGRATION_SOURCE_PROVIDER_ENRICHED,
    MIGRATION_SOURCE_OPERATOR_OVERRIDE,
    MIGRATION_SOURCE_UNKNOWN,
)


# Migration sources Stage 27.4 treats as trusted enough to populate
# a ``PRESENT`` status. Anything else falls through to ``UNTRUSTED``
# even when a timestamp is supplied.
MIGRATION_SOURCES_TRUSTED: tuple[str, ...] = (
    MIGRATION_SOURCE_ON_CHAIN_MIGRATION_EVENT,
    MIGRATION_SOURCE_OPERATOR_OVERRIDE,
)


# ---------------------------------------------------------------------------
# Immutable record: migration context
# ---------------------------------------------------------------------------


class MigrationContextRecord(NamedTuple):
    """Immutable Stage 27.4 migration context record.

    Carries only closed-set tokens and safe-to-display canonical
    fields. No raw provider payload blob, no secret value, no
    webhook URL is ever populated on this record.

    Fields:

      * ``token_mint``                       -- copied from the
                                                composition input.
      * ``pair_type``                        -- Stage 27.2 closed-set
                                                ``PAIR_TYPE`` verdict.
      * ``quote_asset``                      -- Stage 27.2 closed-set
                                                ``QUOTE_ASSET`` verdict.
      * ``migration_event_id``               -- safe-to-display
                                                migration event id;
                                                ``None`` when missing.
      * ``migration_timestamp_utc``          -- ISO-8601 UTC migration
                                                timestamp; ``None``
                                                when missing.
      * ``migration_source``                 -- one of
                                                ``MIGRATION_SOURCE_VALUES``.
      * ``migration_status``                 -- one of
                                                ``MIGRATION_STATUS_VALUES``.
      * ``migration_reason``                 -- one of
                                                ``MIGRATION_REASON_VALUES``.
      * ``age_since_migration_seconds``      -- non-negative integer
                                                seconds between the
                                                migration timestamp
                                                and the injected
                                                clock; ``None`` when
                                                either side is
                                                missing or untrusted.
      * ``observed_at_utc``                  -- ISO-8601 UTC clock
                                                wall time at which
                                                Stage 27.4 derived
                                                this record (clock-
                                                driven, not
                                                ``datetime.now()``).
      * ``source_event_ref``                 -- short safe-to-display
                                                provenance reference
                                                pointing at the
                                                upstream migration
                                                event row / artifact;
                                                ``None`` when missing.
      * ``raw_capture_ref``                  -- short safe-to-display
                                                provenance reference
                                                pointing at the
                                                upstream raw capture;
                                                ``None`` when missing.
                                                NEVER a raw payload
                                                blob.
      * ``schema_version``                   -- locked Stage 27.4
                                                migration schema
                                                version string.
    """

    token_mint: Optional[str]
    pair_type: str
    quote_asset: str
    migration_event_id: Optional[str]
    migration_timestamp_utc: Optional[str]
    migration_source: str
    migration_status: str
    migration_reason: str
    age_since_migration_seconds: Optional[int]
    observed_at_utc: Optional[str]
    source_event_ref: Optional[str]
    raw_capture_ref: Optional[str]
    schema_version: str

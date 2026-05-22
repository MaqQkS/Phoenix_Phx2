"""Stage 27.4 price + ATH context closed-set vocabularies and
immutable record shapes.

Stage 27.4 ships the in-memory model layer for the price and
all-time-high (ATH) context records that decorate a Stage 27.3
provider-ingest composition output. The records carry only
closed-set tokens and safe-to-display canonical fields.

Closed-set vocabularies:

  * ``PRICE_STATUS``                  -- ``PRESENT`` / ``STALE`` /
                                         ``UNAVAILABLE`` /
                                         ``UNSUPPORTED_PAIR`` /
                                         ``SOURCE_ERROR``
  * ``PRICE_UNIT``                    -- ``SOL`` / ``USDC`` / ``USD`` /
                                         ``UNKNOWN``
  * ``PRICE_REASON``                  -- closed-set reason codes
                                         describing the resolution
                                         path.
  * ``ATH_STATUS``                    -- ``PRESENT`` / ``STALE`` /
                                         ``UNAVAILABLE`` /
                                         ``NOT_APPLICABLE`` /
                                         ``UNSUPPORTED_PAIR`` /
                                         ``SOURCE_ERROR``
  * ``ATH_UNIT``                      -- ``SOL`` / ``USDC`` / ``USD`` /
                                         ``UNKNOWN``
  * ``ATH_SINCE_MIGRATION_STATUS``    -- ``POST_MIGRATION_ONLY`` /
                                         ``MAY_INCLUDE_PRE_MIGRATION``
                                         / ``UNKNOWN`` /
                                         ``NOT_APPLICABLE``
  * ``ATH_REASON``                    -- closed-set reason codes.
  * ``DRAWDOWN_BASIS``                -- ``FROM_POST_MIGRATION_ATH`` /
                                         ``NOT_APPLICABLE`` /
                                         ``UNKNOWN``

Stage 27.4 deliberately does NOT carry:

  * raw price / ATH provider payload blobs (no field ever takes a
    raw payload),
  * secrets, webhook URLs, API keys (no field admits them),
  * Stage 26 policy decisions (Stage 26 is review-only),
  * floating-point price / ATH values used as "unknown" sentinels
    (numeric values are canonical decimal text strings; missing
    values are ``None``, never ``0.0``).

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
# Stage 27.4 version axes
# ---------------------------------------------------------------------------


STAGE27_4_MINOR_VERSION: str = "27.4"
STAGE27_4_PRICE_ATH_SCHEMA_VERSION: str = (
    "stage27_v0_price_ath_context"
)


# ---------------------------------------------------------------------------
# price_status closed set
# ---------------------------------------------------------------------------


PRICE_STATUS_PRESENT: str = "PRESENT"
PRICE_STATUS_STALE: str = "STALE"
PRICE_STATUS_UNAVAILABLE: str = "UNAVAILABLE"
PRICE_STATUS_UNSUPPORTED_PAIR: str = "UNSUPPORTED_PAIR"
PRICE_STATUS_SOURCE_ERROR: str = "SOURCE_ERROR"

PRICE_STATUS_VALUES: tuple[str, ...] = (
    PRICE_STATUS_PRESENT,
    PRICE_STATUS_STALE,
    PRICE_STATUS_UNAVAILABLE,
    PRICE_STATUS_UNSUPPORTED_PAIR,
    PRICE_STATUS_SOURCE_ERROR,
)


# ---------------------------------------------------------------------------
# price_unit closed set
# ---------------------------------------------------------------------------


PRICE_UNIT_SOL: str = "SOL"
PRICE_UNIT_USDC: str = "USDC"
PRICE_UNIT_USD: str = "USD"
PRICE_UNIT_UNKNOWN: str = "UNKNOWN"

PRICE_UNIT_VALUES: tuple[str, ...] = (
    PRICE_UNIT_SOL,
    PRICE_UNIT_USDC,
    PRICE_UNIT_USD,
    PRICE_UNIT_UNKNOWN,
)


# ---------------------------------------------------------------------------
# price_reason closed set
# ---------------------------------------------------------------------------


PRICE_REASON_OK: str = "OK"
PRICE_REASON_STALE_THRESHOLD_EXCEEDED: str = (
    "STALE_THRESHOLD_EXCEEDED"
)
PRICE_REASON_SOURCE_RETURNED_NONE: str = "SOURCE_RETURNED_NONE"
PRICE_REASON_SOURCE_FAILED: str = "SOURCE_FAILED"
PRICE_REASON_UNSUPPORTED_QUOTE_ASSET: str = (
    "UNSUPPORTED_QUOTE_ASSET"
)
PRICE_REASON_UNKNOWN_PAIR_OBSERVE_ONLY: str = (
    "UNKNOWN_PAIR_OBSERVE_ONLY"
)
PRICE_REASON_DISAGREE_PAIR_OBSERVE_ONLY: str = (
    "DISAGREE_PAIR_OBSERVE_ONLY"
)
PRICE_REASON_USDC_OBSERVE_ONLY: str = "USDC_OBSERVE_ONLY"
PRICE_REASON_INVALID_SOURCE_SNAPSHOT: str = (
    "INVALID_SOURCE_SNAPSHOT"
)

PRICE_REASON_VALUES: tuple[str, ...] = (
    PRICE_REASON_OK,
    PRICE_REASON_STALE_THRESHOLD_EXCEEDED,
    PRICE_REASON_SOURCE_RETURNED_NONE,
    PRICE_REASON_SOURCE_FAILED,
    PRICE_REASON_UNSUPPORTED_QUOTE_ASSET,
    PRICE_REASON_UNKNOWN_PAIR_OBSERVE_ONLY,
    PRICE_REASON_DISAGREE_PAIR_OBSERVE_ONLY,
    PRICE_REASON_USDC_OBSERVE_ONLY,
    PRICE_REASON_INVALID_SOURCE_SNAPSHOT,
)


# ---------------------------------------------------------------------------
# ath_status closed set
# ---------------------------------------------------------------------------


ATH_STATUS_PRESENT: str = "PRESENT"
ATH_STATUS_STALE: str = "STALE"
ATH_STATUS_UNAVAILABLE: str = "UNAVAILABLE"
ATH_STATUS_NOT_APPLICABLE: str = "NOT_APPLICABLE"
ATH_STATUS_UNSUPPORTED_PAIR: str = "UNSUPPORTED_PAIR"
ATH_STATUS_SOURCE_ERROR: str = "SOURCE_ERROR"

ATH_STATUS_VALUES: tuple[str, ...] = (
    ATH_STATUS_PRESENT,
    ATH_STATUS_STALE,
    ATH_STATUS_UNAVAILABLE,
    ATH_STATUS_NOT_APPLICABLE,
    ATH_STATUS_UNSUPPORTED_PAIR,
    ATH_STATUS_SOURCE_ERROR,
)


# ---------------------------------------------------------------------------
# ath_unit closed set
# ---------------------------------------------------------------------------


ATH_UNIT_SOL: str = "SOL"
ATH_UNIT_USDC: str = "USDC"
ATH_UNIT_USD: str = "USD"
ATH_UNIT_UNKNOWN: str = "UNKNOWN"

ATH_UNIT_VALUES: tuple[str, ...] = (
    ATH_UNIT_SOL,
    ATH_UNIT_USDC,
    ATH_UNIT_USD,
    ATH_UNIT_UNKNOWN,
)


# ---------------------------------------------------------------------------
# ath_since_migration_status closed set
# ---------------------------------------------------------------------------
#
# Stage 27.4 explicitly distinguishes between an ATH that is known
# to be drawn only from post-migration observations and an ATH that
# may still include pre-migration wick data. Pre-migration data
# must never be silently merged into a "post-migration ATH" claim.


ATH_SINCE_MIGRATION_STATUS_POST_MIGRATION_ONLY: str = (
    "POST_MIGRATION_ONLY"
)
ATH_SINCE_MIGRATION_STATUS_MAY_INCLUDE_PRE_MIGRATION: str = (
    "MAY_INCLUDE_PRE_MIGRATION"
)
ATH_SINCE_MIGRATION_STATUS_UNKNOWN: str = "UNKNOWN"
ATH_SINCE_MIGRATION_STATUS_NOT_APPLICABLE: str = "NOT_APPLICABLE"

ATH_SINCE_MIGRATION_STATUS_VALUES: tuple[str, ...] = (
    ATH_SINCE_MIGRATION_STATUS_POST_MIGRATION_ONLY,
    ATH_SINCE_MIGRATION_STATUS_MAY_INCLUDE_PRE_MIGRATION,
    ATH_SINCE_MIGRATION_STATUS_UNKNOWN,
    ATH_SINCE_MIGRATION_STATUS_NOT_APPLICABLE,
)


# ---------------------------------------------------------------------------
# ath_reason closed set
# ---------------------------------------------------------------------------


ATH_REASON_OK: str = "OK"
ATH_REASON_NO_OBSERVATIONS: str = "NO_OBSERVATIONS"
ATH_REASON_PRE_MIGRATION_DATA_REJECTED: str = (
    "PRE_MIGRATION_DATA_REJECTED"
)
ATH_REASON_SOURCE_FAILED: str = "SOURCE_FAILED"
ATH_REASON_UNSUPPORTED_QUOTE_ASSET: str = (
    "UNSUPPORTED_QUOTE_ASSET"
)
ATH_REASON_UNKNOWN_PAIR_OBSERVE_ONLY: str = (
    "UNKNOWN_PAIR_OBSERVE_ONLY"
)
ATH_REASON_DISAGREE_PAIR_OBSERVE_ONLY: str = (
    "DISAGREE_PAIR_OBSERVE_ONLY"
)
ATH_REASON_USDC_OBSERVE_ONLY: str = "USDC_OBSERVE_ONLY"
ATH_REASON_NOT_APPLICABLE: str = "NOT_APPLICABLE"
ATH_REASON_INVALID_SOURCE_SNAPSHOT: str = (
    "INVALID_SOURCE_SNAPSHOT"
)

ATH_REASON_VALUES: tuple[str, ...] = (
    ATH_REASON_OK,
    ATH_REASON_NO_OBSERVATIONS,
    ATH_REASON_PRE_MIGRATION_DATA_REJECTED,
    ATH_REASON_SOURCE_FAILED,
    ATH_REASON_UNSUPPORTED_QUOTE_ASSET,
    ATH_REASON_UNKNOWN_PAIR_OBSERVE_ONLY,
    ATH_REASON_DISAGREE_PAIR_OBSERVE_ONLY,
    ATH_REASON_USDC_OBSERVE_ONLY,
    ATH_REASON_NOT_APPLICABLE,
    ATH_REASON_INVALID_SOURCE_SNAPSHOT,
)


# ---------------------------------------------------------------------------
# drawdown_basis closed set
# ---------------------------------------------------------------------------


DRAWDOWN_BASIS_FROM_POST_MIGRATION_ATH: str = (
    "FROM_POST_MIGRATION_ATH"
)
DRAWDOWN_BASIS_NOT_APPLICABLE: str = "NOT_APPLICABLE"
DRAWDOWN_BASIS_UNKNOWN: str = "UNKNOWN"

DRAWDOWN_BASIS_VALUES: tuple[str, ...] = (
    DRAWDOWN_BASIS_FROM_POST_MIGRATION_ATH,
    DRAWDOWN_BASIS_NOT_APPLICABLE,
    DRAWDOWN_BASIS_UNKNOWN,
)


# ---------------------------------------------------------------------------
# Immutable record: price context
# ---------------------------------------------------------------------------


class PriceContextRecord(NamedTuple):
    """Immutable Stage 27.4 price context record.

    Carries only closed-set tokens and safe-to-display canonical
    fields. No raw provider payload blob, no secret value, no
    webhook URL is ever populated on this record.

    Fields:

      * ``token_mint``              -- copied from the composition
                                       input.
      * ``pair_type``               -- Stage 27.2 closed-set
                                       ``PAIR_TYPE`` verdict.
      * ``quote_asset``             -- Stage 27.2 closed-set
                                       ``QUOTE_ASSET`` verdict.
      * ``quote_mint``              -- copied from the composition
                                       input. NEVER promoted to SOL
                                       when missing or UNKNOWN.
      * ``price_value``             -- canonical decimal-text price
                                       value (e.g. ``"0.00012345"``);
                                       ``None`` when the price is
                                       missing. Stage 27.4 never
                                       uses ``0.0`` as a missing
                                       sentinel.
      * ``price_unit``              -- one of ``PRICE_UNIT_VALUES``.
      * ``price_source``            -- short safe-to-display source
                                       label (e.g. ``"birdeye"``);
                                       no API key, webhook URL, or
                                       raw payload.
      * ``fetched_at_utc``          -- ISO-8601 UTC timestamp at
                                       which the upstream source
                                       fetched the price.
      * ``observed_at_utc``         -- ISO-8601 UTC timestamp at
                                       which Stage 27.4 observed
                                       the price (the clock-driven
                                       wall time used for staleness).
      * ``staleness_seconds``       -- non-negative integer seconds
                                       between ``fetched_at_utc``
                                       and ``observed_at_utc``;
                                       ``None`` when either side is
                                       missing.
      * ``price_status``            -- one of ``PRICE_STATUS_VALUES``.
      * ``price_reason``            -- one of ``PRICE_REASON_VALUES``.
      * ``schema_version``          -- locked Stage 27.4 price/ATH
                                       schema version string.
    """

    token_mint: Optional[str]
    pair_type: str
    quote_asset: str
    quote_mint: Optional[str]
    price_value: Optional[str]
    price_unit: str
    price_source: Optional[str]
    fetched_at_utc: Optional[str]
    observed_at_utc: Optional[str]
    staleness_seconds: Optional[int]
    price_status: str
    price_reason: str
    schema_version: str


# ---------------------------------------------------------------------------
# Immutable record: ATH context
# ---------------------------------------------------------------------------


class AthContextRecord(NamedTuple):
    """Immutable Stage 27.4 ATH (all-time-high) context record.

    Carries only closed-set tokens and safe-to-display canonical
    fields. No raw provider payload blob, no secret value, no
    webhook URL is ever populated on this record.

    Fields:

      * ``token_mint``                  -- copied from the composition
                                           input.
      * ``pair_type``                   -- Stage 27.2 closed-set
                                           ``PAIR_TYPE`` verdict.
      * ``quote_asset``                 -- Stage 27.2 closed-set
                                           ``QUOTE_ASSET`` verdict.
      * ``ath_value``                   -- canonical decimal-text ATH
                                           value; ``None`` when the
                                           ATH is missing. Stage 27.4
                                           never uses ``0.0`` as a
                                           missing sentinel.
      * ``ath_unit``                    -- one of ``ATH_UNIT_VALUES``.
      * ``ath_source``                  -- short safe-to-display source
                                           label.
      * ``ath_observed_at_utc``         -- ISO-8601 UTC timestamp at
                                           which the upstream source
                                           observed the ATH peak.
      * ``ath_since_migration_status``  -- one of
                                           ``ATH_SINCE_MIGRATION_STATUS_VALUES``.
                                           Pre-migration wick data
                                           must never be merged into
                                           a ``POST_MIGRATION_ONLY``
                                           claim.
      * ``drawdown_from_ath``           -- canonical decimal-text
                                           drawdown amount; ``None``
                                           when not computed.
      * ``drawdown_unit``               -- one of ``ATH_UNIT_VALUES``.
                                           Same currency as
                                           ``ath_unit`` for the
                                           POST_MIGRATION_ONLY case.
      * ``drawdown_basis``              -- one of
                                           ``DRAWDOWN_BASIS_VALUES``.
      * ``ath_status``                  -- one of ``ATH_STATUS_VALUES``.
      * ``ath_reason``                  -- one of ``ATH_REASON_VALUES``.
      * ``schema_version``              -- locked Stage 27.4 price/ATH
                                           schema version string.
    """

    token_mint: Optional[str]
    pair_type: str
    quote_asset: str
    ath_value: Optional[str]
    ath_unit: str
    ath_source: Optional[str]
    ath_observed_at_utc: Optional[str]
    ath_since_migration_status: str
    drawdown_from_ath: Optional[str]
    drawdown_unit: str
    drawdown_basis: str
    ath_status: str
    ath_reason: str
    schema_version: str


# ---------------------------------------------------------------------------
# Forbidden field-name vocabulary (defensive sentinel)
# ---------------------------------------------------------------------------
#
# Stage 27.4 must never accept a field named anything secret-class
# or raw-payload-class on its snapshot inputs. The Stage 27.4 source
# snapshots in ``price_ath_context_reader`` have no such fields, but
# this helper is kept so a future refactor cannot silently widen the
# admitted field set.


FORBIDDEN_SNAPSHOT_FIELD_NAMES: tuple[str, ...] = (
    "raw_payload",
    "raw_payload_blob",
    "payload",
    "payload_summary",
    "secret",
    "api_key",
    "apikey",
    "token_secret",
    "webhook",
    "webhook_url",
    "private_key",
    "credentials",
    "bearer_token",
)


def is_forbidden_snapshot_field_name(name: object) -> bool:
    """Return ``True`` iff ``name`` is a forbidden snapshot field name.

    Pure / deterministic. Stage 27.4 uses this to reject any caller
    who tries to smuggle a raw payload blob into a source snapshot.
    """
    if not isinstance(name, str):
        return False
    lower = name.lower()
    for forbidden in FORBIDDEN_SNAPSHOT_FIELD_NAMES:
        if forbidden in lower:
            return True
    return False

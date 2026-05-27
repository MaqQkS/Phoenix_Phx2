"""Stage 30.1 tier decision closed-set vocabularies and immutable
record shape.

Stage 30.1 ships the pure-Python model layer for the tier decision
record the Stage 30.1 projector emits per ping. The record carries
only closed-set tokens, safe-shape opaque identifier echoes, and the
canonical decimal-text drop value the projector classified. The
record is the input to the Stage 30.1 JSONL artifact writer and the
future Stage 30.2 compact private ping renderer.

Closed-set vocabularies:

  * ``TIER_TOKEN``    -- ``Tier 1`` / ``Tier 2`` / ``Tier 3`` /
                         ``Tier Unknown`` / ``Tier Not Applicable``
  * ``TIER_REASON``   -- closed-set reason tokens that explain WHY
                         the projector chose the tier token, covering
                         Tier Not Applicable (migration / pre-
                         migration ATH), Tier Unknown (degraded
                         inputs, in-gap drop, graveyard drop), and
                         the three in-band Tier 1 / 2 / 3 reasons.
  * ``BASIS``         -- ``price-basis`` / ``mc-basis``.

Stage 30.1 deliberately does NOT carry:

  * raw provider payload blobs (no field ever takes a raw payload),
  * secrets, webhook URLs, API keys, bearer tokens, authorization
    headers (no field admits them),
  * trading verdicts (the Stage 30 spec forbids any trading-verdict
    substring on rendered output; the tier decision record is
    structurally upstream of that scan but never carries a verdict
    by construction),
  * Stage 26 / Stage 29 enforcement decisions (Stage 30 is
    informational-only).

Discipline:

  * Stdlib only (``typing``).
  * No ``os.environ`` / ``os.getenv`` / ``os.environb`` access.
  * No network, no HTTP, no gRPC, no WebSocket, no socket.
  * No Discord, Telegram, X / social, webhook, Helius, Chainstack,
    Birdeye, Dexscreener, Pump.fun reference.
  * No PHX1 import. No legacy phoenix-1 import path.
  * No Stage 21-29 production-source modification.
  * No top-level Call (no implicit I/O at import time).
"""

from __future__ import annotations

from typing import NamedTuple, Optional


# ---------------------------------------------------------------------------
# Stage 30.1 schema version + locked artifact basename
# ---------------------------------------------------------------------------


STAGE30_1_MINOR_VERSION: str = "30.1"
STAGE30_1_TIER_DECISION_SCHEMA_VERSION: str = (
    "stage30_1_v0_tier_decision"
)
STAGE30_1_TIER_DECISION_ARTIFACT_BASENAME: str = (
    "stage30_1_tier_decisions.jsonl"
)


# ---------------------------------------------------------------------------
# tier_token closed set
# ---------------------------------------------------------------------------
#
# The tier tokens are the bare strings the Stage 30.2 compact renderer
# wraps with ``[`` / ``]`` brackets in the compact ping header. The
# tier model itself NEVER emits a bracketed form; the bracket prefix
# is a renderer concern. The tier model also NEVER emits any synonym
# or short form (no ``T1`` / ``T-1`` / ``Tier1``).


TIER_TOKEN_TIER_1: str = "Tier 1"
TIER_TOKEN_TIER_2: str = "Tier 2"
TIER_TOKEN_TIER_3: str = "Tier 3"
TIER_TOKEN_TIER_UNKNOWN: str = "Tier Unknown"
TIER_TOKEN_TIER_NOT_APPLICABLE: str = "Tier Not Applicable"


TIER_TOKEN_VALUES: tuple[str, ...] = (
    TIER_TOKEN_TIER_1,
    TIER_TOKEN_TIER_2,
    TIER_TOKEN_TIER_3,
    TIER_TOKEN_TIER_UNKNOWN,
    TIER_TOKEN_TIER_NOT_APPLICABLE,
)


def is_tier_token_value(value: object) -> bool:
    """Return ``True`` iff ``value`` is a Stage 30.1 tier token."""
    return isinstance(value, str) and value in TIER_TOKEN_VALUES


# ---------------------------------------------------------------------------
# tier_reason closed set
# ---------------------------------------------------------------------------
#
# Reason tokens carry the operator-readable explanation for the chosen
# tier. The model emits exactly one reason per decision. The reason
# family is partitioned into:
#
#   * Tier Not Applicable family (NA_*)
#   * Tier Unknown family (UNKNOWN_*)
#   * In-band family (TIER_<n>_IN_BAND)
#
# The reason token is independent of the tier token in the sense that
# downstream consumers may show only the tier OR only the reason OR
# both. The projector NEVER emits a tier token / reason token pair
# that disagrees (e.g. ``Tier 1`` with ``NA_MIGRATION_MISSING``).


# Tier Not Applicable family
TIER_REASON_NA_MIGRATION_MISSING: str = (
    "NA_MIGRATION_MISSING"
)
TIER_REASON_NA_MIGRATION_UNTRUSTED: str = (
    "NA_MIGRATION_UNTRUSTED"
)
TIER_REASON_NA_MIGRATION_UNSUPPORTED_PAIR: str = (
    "NA_MIGRATION_UNSUPPORTED_PAIR"
)
TIER_REASON_NA_MIGRATION_SOURCE_ERROR: str = (
    "NA_MIGRATION_SOURCE_ERROR"
)
TIER_REASON_NA_ATH_MAY_INCLUDE_PRE_MIGRATION: str = (
    "NA_ATH_MAY_INCLUDE_PRE_MIGRATION"
)


# Tier Unknown family (degraded inputs)
TIER_REASON_UNKNOWN_ATH_NOT_PRESENT: str = (
    "UNKNOWN_ATH_NOT_PRESENT"
)
TIER_REASON_UNKNOWN_DRAWDOWN_MISSING: str = (
    "UNKNOWN_DRAWDOWN_MISSING"
)
TIER_REASON_UNKNOWN_DRAWDOWN_MALFORMED: str = (
    "UNKNOWN_DRAWDOWN_MALFORMED"
)


# Tier Unknown family (out-of-band drop)
TIER_REASON_UNKNOWN_BELOW_TIER_1: str = (
    "UNKNOWN_BELOW_TIER_1"
)
TIER_REASON_UNKNOWN_IN_GAP_T1_T2: str = (
    "UNKNOWN_IN_GAP_T1_T2"
)
TIER_REASON_UNKNOWN_IN_GAP_T2_T3: str = (
    "UNKNOWN_IN_GAP_T2_T3"
)
TIER_REASON_UNKNOWN_GRAVEYARD: str = (
    "UNKNOWN_GRAVEYARD"
)


# In-band family
TIER_REASON_TIER_1_IN_BAND: str = "TIER_1_IN_BAND"
TIER_REASON_TIER_2_IN_BAND: str = "TIER_2_IN_BAND"
TIER_REASON_TIER_3_IN_BAND: str = "TIER_3_IN_BAND"


TIER_REASON_VALUES: tuple[str, ...] = (
    TIER_REASON_NA_MIGRATION_MISSING,
    TIER_REASON_NA_MIGRATION_UNTRUSTED,
    TIER_REASON_NA_MIGRATION_UNSUPPORTED_PAIR,
    TIER_REASON_NA_MIGRATION_SOURCE_ERROR,
    TIER_REASON_NA_ATH_MAY_INCLUDE_PRE_MIGRATION,
    TIER_REASON_UNKNOWN_ATH_NOT_PRESENT,
    TIER_REASON_UNKNOWN_DRAWDOWN_MISSING,
    TIER_REASON_UNKNOWN_DRAWDOWN_MALFORMED,
    TIER_REASON_UNKNOWN_BELOW_TIER_1,
    TIER_REASON_UNKNOWN_IN_GAP_T1_T2,
    TIER_REASON_UNKNOWN_IN_GAP_T2_T3,
    TIER_REASON_UNKNOWN_GRAVEYARD,
    TIER_REASON_TIER_1_IN_BAND,
    TIER_REASON_TIER_2_IN_BAND,
    TIER_REASON_TIER_3_IN_BAND,
)


def is_tier_reason_value(value: object) -> bool:
    """Return ``True`` iff ``value`` is a Stage 30.1 tier reason."""
    return isinstance(value, str) and value in TIER_REASON_VALUES


# ---------------------------------------------------------------------------
# basis closed set
# ---------------------------------------------------------------------------
#
# Stage 30.1 records WHICH basis the projector classified against.
# Stage 30.1 itself does not fetch MC data; it trusts the caller-
# supplied drawdown_from_ath value. The basis token is informational
# only; it lets the operator see whether the displayed tier was
# computed against a price-basis drawdown or a market-cap-basis
# drawdown when a future Stage 30.4 adapter lands.


BASIS_PRICE: str = "price-basis"
BASIS_MC: str = "mc-basis"


BASIS_VALUES: tuple[str, ...] = (
    BASIS_PRICE,
    BASIS_MC,
)


def is_basis_value(value: object) -> bool:
    """Return ``True`` iff ``value`` is a Stage 30.1 basis token."""
    return isinstance(value, str) and value in BASIS_VALUES


# ---------------------------------------------------------------------------
# Immutable record: tier decision
# ---------------------------------------------------------------------------


class TierDecisionRecord(NamedTuple):
    """Immutable Stage 30.1 tier decision record.

    Carries only closed-set tokens, safe-shape opaque identifier
    echoes, canonical decimal-text values, and ISO-8601 UTC
    timestamps. No raw provider payload blob, no secret value, no
    webhook URL, no API key, no bearer token, no authorization
    header is ever populated on this record by the projector. The
    Stage 30.1 forbidden-field-name guard rejects any future
    refactor that tries to widen the field set with a secret-class
    or raw-payload-class name.

    Fields:

      * ``schema_version``                  -- locked Stage 30.1 tier
                                               decision schema version
                                               string.
      * ``session_id``                      -- safe-shape opaque
                                               session identifier or
                                               ``None``.
      * ``ping_id``                         -- safe-shape opaque ping
                                               identifier or ``None``.
      * ``candidate_id``                    -- safe-shape opaque
                                               candidate identifier or
                                               ``None``.
      * ``mint``                            -- safe-shape base58 mint
                                               or ``None`` when not
                                               supplied or unsafe-
                                               shape.
      * ``basis``                           -- one of
                                               ``BASIS_VALUES``.
      * ``drawdown_from_ath_raw``           -- echoed canonical
                                               decimal-text drawdown
                                               value from the Stage
                                               27.4 ATH context
                                               record, or ``None``
                                               when missing / unsafe
                                               for echo.
      * ``drop_positive``                   -- canonical decimal-text
                                               positive drop value
                                               (``abs`` of the parsed
                                               drawdown), or ``None``
                                               when the drawdown was
                                               missing / malformed /
                                               unparseable AND when
                                               an earlier safety
                                               status short-circuited
                                               before parse.
      * ``ath_status``                      -- echoed Stage 27.4
                                               ``ATH_STATUS`` token
                                               (or ``UNAVAILABLE``
                                               when no ATH record was
                                               supplied).
      * ``ath_since_migration_status``      -- echoed Stage 27.4
                                               ``ATH_SINCE_MIGRATION_STATUS``
                                               token (or ``UNKNOWN``
                                               when no ATH record was
                                               supplied).
      * ``migration_status``                -- echoed Stage 27.4
                                               ``MIGRATION_STATUS``
                                               token (or ``MISSING``
                                               when no migration
                                               record was supplied).
      * ``tier_token``                      -- one of
                                               ``TIER_TOKEN_VALUES``.
      * ``tier_reason``                     -- one of
                                               ``TIER_REASON_VALUES``.
      * ``created_at_utc``                  -- ISO-8601 UTC timestamp
                                               passed in by the
                                               caller (the injected
                                               clock); never derived
                                               from ``datetime.now``.
    """

    schema_version: str
    session_id: Optional[str]
    ping_id: Optional[str]
    candidate_id: Optional[str]
    mint: Optional[str]
    basis: str
    drawdown_from_ath_raw: Optional[str]
    drop_positive: Optional[str]
    ath_status: str
    ath_since_migration_status: str
    migration_status: str
    tier_token: str
    tier_reason: str
    created_at_utc: str


# ---------------------------------------------------------------------------
# Forbidden field-name vocabulary (defensive sentinel)
# ---------------------------------------------------------------------------
#
# Stage 30.1 must never accept a field named anything secret-class or
# raw-payload-class on its tier decision record. The current
# ``TierDecisionRecord._fields`` set has no such name, but this helper
# is kept so a future refactor cannot silently widen the admitted
# field set.


FORBIDDEN_RECORD_FIELD_NAMES: tuple[str, ...] = (
    "webhook",
    "webhook_url",
    "webhooks",
    "api_key",
    "apikey",
    "bearer",
    "bearer_token",
    "authorization",
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
    "raw_payload",
    "payload",
    "payload_blob",
    "payload_summary",
    "migration_event_id",
    "raw_capture_ref",
    "source_event_ref",
)


def is_forbidden_record_field_name(name: object) -> bool:
    """Return ``True`` iff ``name`` is a forbidden record field name.

    Pure / deterministic. Stage 30.1 uses this guard to reject any
    future refactor that tries to widen the tier decision record
    with a secret-class or raw-payload-class field name.
    """
    if not isinstance(name, str):
        return False
    lower = name.lower()
    for forbidden in FORBIDDEN_RECORD_FIELD_NAMES:
        if forbidden in lower:
            return True
    return False


# ---------------------------------------------------------------------------
# Module-local exception
# ---------------------------------------------------------------------------


class Stage30_1TierDecisionError(Exception):
    """Closed-set Stage 30.1 tier decision error.

    Carries only a closed-set reason token on the exception message.
    Stage 30.1 callers should never embed a raw OSError message, a
    raw provider payload, or any secret value in the message.
    """

    def __init__(self, reason: str) -> None:
        self.reason: str = reason
        super().__init__(
            f"Stage 30.1 tier decision error: reason={reason!r}"
        )


__all__ = (
    # Version + locked artifact basename.
    "STAGE30_1_MINOR_VERSION",
    "STAGE30_1_TIER_DECISION_SCHEMA_VERSION",
    "STAGE30_1_TIER_DECISION_ARTIFACT_BASENAME",
    # Tier tokens.
    "TIER_TOKEN_TIER_1",
    "TIER_TOKEN_TIER_2",
    "TIER_TOKEN_TIER_3",
    "TIER_TOKEN_TIER_UNKNOWN",
    "TIER_TOKEN_TIER_NOT_APPLICABLE",
    "TIER_TOKEN_VALUES",
    "is_tier_token_value",
    # Tier reasons.
    "TIER_REASON_NA_MIGRATION_MISSING",
    "TIER_REASON_NA_MIGRATION_UNTRUSTED",
    "TIER_REASON_NA_MIGRATION_UNSUPPORTED_PAIR",
    "TIER_REASON_NA_MIGRATION_SOURCE_ERROR",
    "TIER_REASON_NA_ATH_MAY_INCLUDE_PRE_MIGRATION",
    "TIER_REASON_UNKNOWN_ATH_NOT_PRESENT",
    "TIER_REASON_UNKNOWN_DRAWDOWN_MISSING",
    "TIER_REASON_UNKNOWN_DRAWDOWN_MALFORMED",
    "TIER_REASON_UNKNOWN_BELOW_TIER_1",
    "TIER_REASON_UNKNOWN_IN_GAP_T1_T2",
    "TIER_REASON_UNKNOWN_IN_GAP_T2_T3",
    "TIER_REASON_UNKNOWN_GRAVEYARD",
    "TIER_REASON_TIER_1_IN_BAND",
    "TIER_REASON_TIER_2_IN_BAND",
    "TIER_REASON_TIER_3_IN_BAND",
    "TIER_REASON_VALUES",
    "is_tier_reason_value",
    # Basis tokens.
    "BASIS_PRICE",
    "BASIS_MC",
    "BASIS_VALUES",
    "is_basis_value",
    # Record + forbidden-field guard + error.
    "TierDecisionRecord",
    "FORBIDDEN_RECORD_FIELD_NAMES",
    "is_forbidden_record_field_name",
    "Stage30_1TierDecisionError",
)

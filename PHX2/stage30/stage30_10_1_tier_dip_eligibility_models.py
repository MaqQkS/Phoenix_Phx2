"""Stage 30.10.1 compact tier-dip eligibility models.

Stage 30.10.1 ships the passive, pure, stdlib-only model layer for the
offline compact tier-dip eligibility classifier (Stage 30.10): the explicit
fail-closed policy object, the per-candidate evaluation input, the
per-candidate eligibility audit record, and the closed-set decision /
reason / tier-code vocabularies they all share, plus the pure normalization
+ safe-shape helpers the classifier composes.

This module is the MODEL layer ONLY. It implements NO classifier (that is
``stage30_10_1_tier_dip_eligibility_classifier``), wires into NO runtime,
makes NO live provider call, sends NO Discord message, reads NO process
environment, opens NO network connection, opens NO database, writes NO
file, and edits NO Stage 28 suppression / Stage 30.3 / Stage 30.4 runtime
orchestrator. Stage 30.10.1 is fake / offline only.

The eligibility brain decides, per candidate:

  * SEND   -- only a true tier-dip opportunity (``Tier 1`` / ``Tier 2`` /
    ``Tier 3`` with the post-migration ATH / migration / current market
    context all present and a drawdown available), and
  * SKIP   -- everything else: ``Tier Unknown`` / ``Tier Not Applicable``,
    a missing ATH / migration / market context / current market cap /
    drawdown, a policy-excluded tier, an unrecognized tier (fail closed),
    or an invalid evaluation input.

The default policy is fail-closed: ``ELIGIBLE_DIP`` is the ONLY send-allowed
decision; every other decision is a clean no-send. No candidate with a
missing / degraded / unrecognized signal can ever become ``ELIGIBLE_DIP``.

Closed-set vocabularies pinned here (each mirrors the Stage 30.10.0 spec
lock / manifest BY VALUE; this module imports no Stage 30.10 manifest and no
Stage 30.1 / Stage 27.4 module):

  * eligibility decision -- ``ELIGIBLE_DIP`` / ``SKIPPED_NOT_DIP`` /
    ``SKIPPED_TIER_UNKNOWN`` / ``SKIPPED_TIER_NOT_APPLICABLE`` /
    ``SKIPPED_MISSING_ATH`` / ``SKIPPED_MISSING_MIGRATION`` /
    ``SKIPPED_MISSING_MARKET_CONTEXT`` / ``INVALID_INPUT``.
  * eligibility reason -- ``TIER_ALLOWED`` / ``TIER_NOT_ALLOWED`` /
    ``TIER_UNKNOWN`` / ``TIER_NOT_APPLICABLE`` / ``MISSING_ATH`` /
    ``MISSING_MIGRATION`` / ``MISSING_DRAWDOWN`` / ``MISSING_MARKET_CONTEXT``
    / ``MISSING_CURRENT_MARKET_CAP`` / ``PRE_MIGRATION_ATH_NOT_ALLOWED`` /
    ``INVALID_CANDIDATE_ID`` / ``INVALID_TOKEN_MINT`` /
    ``INVALID_CREATED_AT_UTC`` / ``INVALID_POLICY``.
  * internal tier code -- ``TIER_1`` / ``TIER_2`` / ``TIER_3`` /
    ``TIER_UNKNOWN`` / ``TIER_NOT_APPLICABLE`` (the closed set the
    ``Tier N`` display tokens normalize into).
  * the ``PRESENT`` status token migration / ATH / market context all use
    (mirrors the Stage 27.4 ``MIGRATION_STATUS_PRESENT`` /
    ``ATH_STATUS_PRESENT`` and the Stage 30.4 ``SOURCE_STATUS_PRESENT``
    values BY VALUE; this module imports no Stage 27 / Stage 30.4 module).

Discipline:

  * Stdlib only (``dataclasses`` / ``decimal`` / ``re`` / ``typing``).
  * Imports NO PHX2 module (mirrors the Stage 30.1 / 30.9.1 model modules;
    the closed-set values are mirrored BY VALUE).
  * No ``os.environ`` / ``os.getenv`` / ``os.environb`` access; no env read.
  * No network, no HTTP, no gRPC, no WebSocket, no socket.
  * No database / SQLite, no zstd / compression, no default storage root.
  * No live provider, transport-destination, or request-metadata reference
    (held to the same redaction hygiene as the Stage 30.10.0 spec lock).
  * No PHX1 import. No Stage 21-29 production import.
  * ``created_at_utc`` is caller-injected; the model NEVER reads a wall
    clock (no ``datetime.now``).
  * The only module-level Call nodes are the pure ``re.compile`` of the
    ISO-8601 pattern and the construction of the all-default fail-closed
    policy constant -- neither performs any I/O at import time.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, fields
from decimal import Decimal
from typing import Optional, Tuple


# ---------------------------------------------------------------------------
# Minor version
# ---------------------------------------------------------------------------


STAGE30_10_1_MINOR_VERSION: str = "30.10.1"


# ---------------------------------------------------------------------------
# Closed-set: eligibility decision
# ---------------------------------------------------------------------------
#
# Exactly one decision token per evaluated candidate. ``ELIGIBLE_DIP`` is the
# only send-allowed decision; every other token is a no-send. Mirrors the
# Stage 30.10.0 ``STAGE30_10_ELIGIBILITY_DECISIONS`` closed set BY VALUE.


DECISION_ELIGIBLE_DIP: str = "ELIGIBLE_DIP"
DECISION_SKIPPED_NOT_DIP: str = "SKIPPED_NOT_DIP"
DECISION_SKIPPED_TIER_UNKNOWN: str = "SKIPPED_TIER_UNKNOWN"
DECISION_SKIPPED_TIER_NOT_APPLICABLE: str = "SKIPPED_TIER_NOT_APPLICABLE"
DECISION_SKIPPED_MISSING_ATH: str = "SKIPPED_MISSING_ATH"
DECISION_SKIPPED_MISSING_MIGRATION: str = "SKIPPED_MISSING_MIGRATION"
DECISION_SKIPPED_MISSING_MARKET_CONTEXT: str = "SKIPPED_MISSING_MARKET_CONTEXT"
DECISION_INVALID_INPUT: str = "INVALID_INPUT"


STAGE30_10_1_ELIGIBILITY_DECISIONS: Tuple[str, ...] = (
    DECISION_ELIGIBLE_DIP,
    DECISION_SKIPPED_NOT_DIP,
    DECISION_SKIPPED_TIER_UNKNOWN,
    DECISION_SKIPPED_TIER_NOT_APPLICABLE,
    DECISION_SKIPPED_MISSING_ATH,
    DECISION_SKIPPED_MISSING_MIGRATION,
    DECISION_SKIPPED_MISSING_MARKET_CONTEXT,
    DECISION_INVALID_INPUT,
)


# The single send-allowed decision token.
STAGE30_10_1_SEND_ALLOWED_DECISION: str = DECISION_ELIGIBLE_DIP


def is_eligibility_decision(value: object) -> bool:
    """Return ``True`` iff ``value`` is a closed-set eligibility decision.

    Pure / total; never raises.
    """
    return (
        isinstance(value, str)
        and value in STAGE30_10_1_ELIGIBILITY_DECISIONS
    )


# ---------------------------------------------------------------------------
# Closed-set: eligibility reason
# ---------------------------------------------------------------------------
#
# Exactly one reason token per decision, explaining WHY the classifier chose
# the decision. ``TIER_ALLOWED`` is the only reason that accompanies
# ``ELIGIBLE_DIP``; every other reason accompanies a no-send decision.


REASON_TIER_ALLOWED: str = "TIER_ALLOWED"
REASON_TIER_NOT_ALLOWED: str = "TIER_NOT_ALLOWED"
REASON_TIER_UNKNOWN: str = "TIER_UNKNOWN"
REASON_TIER_NOT_APPLICABLE: str = "TIER_NOT_APPLICABLE"
REASON_MISSING_ATH: str = "MISSING_ATH"
REASON_MISSING_MIGRATION: str = "MISSING_MIGRATION"
REASON_MISSING_DRAWDOWN: str = "MISSING_DRAWDOWN"
REASON_MISSING_MARKET_CONTEXT: str = "MISSING_MARKET_CONTEXT"
REASON_MISSING_CURRENT_MARKET_CAP: str = "MISSING_CURRENT_MARKET_CAP"
REASON_PRE_MIGRATION_ATH_NOT_ALLOWED: str = "PRE_MIGRATION_ATH_NOT_ALLOWED"
REASON_INVALID_CANDIDATE_ID: str = "INVALID_CANDIDATE_ID"
REASON_INVALID_TOKEN_MINT: str = "INVALID_TOKEN_MINT"
REASON_INVALID_CREATED_AT_UTC: str = "INVALID_CREATED_AT_UTC"
REASON_INVALID_POLICY: str = "INVALID_POLICY"


STAGE30_10_1_ELIGIBILITY_REASONS: Tuple[str, ...] = (
    REASON_TIER_ALLOWED,
    REASON_TIER_NOT_ALLOWED,
    REASON_TIER_UNKNOWN,
    REASON_TIER_NOT_APPLICABLE,
    REASON_MISSING_ATH,
    REASON_MISSING_MIGRATION,
    REASON_MISSING_DRAWDOWN,
    REASON_MISSING_MARKET_CONTEXT,
    REASON_MISSING_CURRENT_MARKET_CAP,
    REASON_PRE_MIGRATION_ATH_NOT_ALLOWED,
    REASON_INVALID_CANDIDATE_ID,
    REASON_INVALID_TOKEN_MINT,
    REASON_INVALID_CREATED_AT_UTC,
    REASON_INVALID_POLICY,
)


def is_eligibility_reason(value: object) -> bool:
    """Return ``True`` iff ``value`` is a closed-set eligibility reason.

    Pure / total; never raises.
    """
    return (
        isinstance(value, str)
        and value in STAGE30_10_1_ELIGIBILITY_REASONS
    )


# ---------------------------------------------------------------------------
# Closed-set: internal tier code + display-token normalization
# ---------------------------------------------------------------------------
#
# The classifier works in the closed-set internal tier codes below. The
# Stage 30.1 ``tier_token`` display values (``Tier 1`` / ``Tier 2`` /
# ``Tier 3`` / ``Tier Unknown`` / ``Tier Not Applicable``) and the already-
# normalized codes both normalize into exactly one code via an EXPLICIT
# lookup table -- never via fuzzy matching. An unrecognized token normalizes
# to ``None`` (the classifier fails closed on it; it never treats an unknown
# token as eligible).


TIER_CODE_TIER_1: str = "TIER_1"
TIER_CODE_TIER_2: str = "TIER_2"
TIER_CODE_TIER_3: str = "TIER_3"
TIER_CODE_TIER_UNKNOWN: str = "TIER_UNKNOWN"
TIER_CODE_TIER_NOT_APPLICABLE: str = "TIER_NOT_APPLICABLE"


STAGE30_10_1_TIER_CODE_VALUES: Tuple[str, ...] = (
    TIER_CODE_TIER_1,
    TIER_CODE_TIER_2,
    TIER_CODE_TIER_3,
    TIER_CODE_TIER_UNKNOWN,
    TIER_CODE_TIER_NOT_APPLICABLE,
)


# The in-band tier codes a fail-closed policy may allow (the default
# ``allowed_tiers``). ``Tier Unknown`` / ``Tier Not Applicable`` are NEVER
# allowable.
STAGE30_10_1_ALLOWED_TIER_CODES: Tuple[str, ...] = (
    TIER_CODE_TIER_1,
    TIER_CODE_TIER_2,
    TIER_CODE_TIER_3,
)


# Explicit display-token + code normalization table (no fuzzy matching). The
# Stage 30.1 display tokens and the already-normalized codes map onto exactly
# one internal code.
_TIER_TOKEN_NORMALIZATION = {
    "Tier 1": TIER_CODE_TIER_1,
    "Tier 2": TIER_CODE_TIER_2,
    "Tier 3": TIER_CODE_TIER_3,
    "Tier Unknown": TIER_CODE_TIER_UNKNOWN,
    "Tier Not Applicable": TIER_CODE_TIER_NOT_APPLICABLE,
    TIER_CODE_TIER_1: TIER_CODE_TIER_1,
    TIER_CODE_TIER_2: TIER_CODE_TIER_2,
    TIER_CODE_TIER_3: TIER_CODE_TIER_3,
    TIER_CODE_TIER_UNKNOWN: TIER_CODE_TIER_UNKNOWN,
    TIER_CODE_TIER_NOT_APPLICABLE: TIER_CODE_TIER_NOT_APPLICABLE,
}


def normalize_tier_token(value: object) -> Optional[str]:
    """Return the closed-set internal tier code for ``value``, else ``None``.

    Maps the Stage 30.1 ``Tier N`` display tokens and the already-normalized
    ``TIER_*`` codes onto exactly one of ``STAGE30_10_1_TIER_CODE_VALUES``
    via an EXPLICIT lookup table. Any unrecognized / non-string / ``None``
    token returns ``None`` (the classifier fails closed on it; it is NEVER
    silently treated as eligible). Pure / total; never raises and never uses
    fuzzy matching.
    """
    if not isinstance(value, str):
        return None
    return _TIER_TOKEN_NORMALIZATION.get(value)


# ---------------------------------------------------------------------------
# Status tokens (migration / ATH / market context all use ``PRESENT``)
# ---------------------------------------------------------------------------
#
# Mirrors the Stage 27.4 ``MIGRATION_STATUS_PRESENT`` / ``ATH_STATUS_PRESENT``
# and the Stage 30.4 ``SOURCE_STATUS_PRESENT`` values BY VALUE (this module
# imports no Stage 27 / Stage 30.4 module). A status is "present" iff it is
# exactly this token; anything else (a degraded token, ``None``, a non-string)
# is treated as not-present and fails closed.


MIGRATION_STATUS_PRESENT: str = "PRESENT"
ATH_STATUS_PRESENT: str = "PRESENT"
MARKET_CONTEXT_STATUS_PRESENT: str = "PRESENT"


def is_present_status(value: object, present_token: str) -> bool:
    """Return ``True`` iff ``value`` exactly equals ``present_token``.

    Pure / total; never raises. Used by the classifier to decide whether the
    migration / ATH / market context status is present.
    """
    return isinstance(value, str) and value == present_token


# ---------------------------------------------------------------------------
# Drawdown magnitude safe-shape validation
# ---------------------------------------------------------------------------
#
# The ``drawdown_from_ath`` magnitude must be a usable, FINITE ``Decimal``.
# Python does not enforce type annotations at runtime, so a malformed
# non-``None`` value (a non-``Decimal`` such as a ``str`` / ``float`` /
# arbitrary object, or a non-finite ``Decimal`` such as ``NaN`` /
# ``Infinity`` / ``-Infinity``) must fail closed and can NEVER reach an
# eligible decision. The sign and zero do NOT by themselves disqualify a
# drawdown: a finite signed / zero ``Decimal`` is structurally valid
# (mirroring the Stage 30.1 projector's signed decimal-text echo), and
# eligibility then hinges on the tier token.


def is_finite_decimal(value: object) -> bool:
    """Return ``True`` iff ``value`` is a finite ``Decimal``.

    A missing (``None``), non-``Decimal`` (``str`` / ``float`` / other), or
    non-finite ``Decimal`` (``NaN`` / ``Infinity`` / ``-Infinity``) value is
    NOT a finite ``Decimal``. A finite signed or zero ``Decimal`` IS finite.
    Pure / total; never raises and never coerces via ``float``.
    """
    return isinstance(value, Decimal) and value.is_finite()


# ---------------------------------------------------------------------------
# created_at_utc safe-shape validation
# ---------------------------------------------------------------------------
#
# ``created_at_utc`` is caller-injected (never a wall-clock read). The model
# gates it against a strict ISO-8601 UTC pattern so a blank / malformed value
# -- or a stray URL / secret-shape substring -- can never ride through into a
# persisted eligibility record. Mirrors the Stage 30.1 projector's
# ``_SAFE_ISO8601_UTC_PATTERN``.


_SAFE_ISO8601_UTC_PATTERN: "re.Pattern[str]" = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$"
)


def is_safe_created_at_utc(value: object) -> bool:
    """Return ``True`` iff ``value`` is a safe-shape ISO-8601 UTC string.

    Accepts ``YYYY-MM-DDTHH:MM:SS[.fff]Z``. Rejects a non-string, an empty /
    blank string, and any value carrying a character outside the strict
    pattern. Pure / total; never raises and never reads a clock.
    """
    if not isinstance(value, str):
        return False
    return _SAFE_ISO8601_UTC_PATTERN.fullmatch(value) is not None


# ---------------------------------------------------------------------------
# Immutable model: fail-closed dip eligibility policy
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Stage30_10DipEligibilityPolicy:
    """Immutable, EXPLICIT fail-closed compact tier-dip eligibility policy.

    A passive config carrier (never a hidden env read). The default is the
    locked Stage 30.10.0 fail-closed stance: allow only ``Tier 1`` /
    ``Tier 2`` / ``Tier 3``; require the post-migration ATH, the migration
    context, and the current market context; and fail closed on any unknown /
    unrecognized tier.

      * ``allowed_tiers``                  -- the in-band tier codes a
                                              candidate must match to be
                                              eligible (a subset of
                                              ``STAGE30_10_1_ALLOWED_TIER_CODES``).
      * ``require_post_migration_ath``     -- require a verified post-
                                              migration ATH; suppress
                                              otherwise.
      * ``require_migration_present``      -- require a present migration
                                              context; suppress otherwise.
      * ``require_current_market_context`` -- require a present market
                                              context + a positive current
                                              market cap; suppress otherwise.
      * ``fail_closed_on_unknown``         -- the declared fail-closed
                                              posture for an unrecognized
                                              tier. The classifier NEVER
                                              fails open regardless of this
                                              flag; with it set the
                                              unrecognized-tier skip is
                                              recorded as
                                              ``SKIPPED_TIER_UNKNOWN``.
    """

    allowed_tiers: Tuple[str, ...] = (
        TIER_CODE_TIER_1,
        TIER_CODE_TIER_2,
        TIER_CODE_TIER_3,
    )
    require_post_migration_ath: bool = True
    require_migration_present: bool = True
    require_current_market_context: bool = True
    fail_closed_on_unknown: bool = True


# The locked default fail-closed policy (a pure all-default construction; no
# I/O at import time).
DEFAULT_STAGE30_10_DIP_ELIGIBILITY_POLICY: Stage30_10DipEligibilityPolicy = (
    Stage30_10DipEligibilityPolicy()
)


def is_valid_policy(policy: object) -> bool:
    """Return ``True`` iff ``policy`` is a well-formed eligibility policy.

    A valid policy is a ``Stage30_10DipEligibilityPolicy`` whose
    ``allowed_tiers`` is a tuple drawn entirely from
    ``STAGE30_10_1_ALLOWED_TIER_CODES`` (``Tier Unknown`` / ``Tier Not
    Applicable`` are never allowable) and whose four boolean axes are all
    ``bool``. Pure / total; never raises. The classifier classifies an
    invalid policy as ``INVALID_INPUT`` / ``INVALID_POLICY`` (a no-send).
    """
    if not isinstance(policy, Stage30_10DipEligibilityPolicy):
        return False
    if not isinstance(policy.allowed_tiers, tuple):
        return False
    for tier in policy.allowed_tiers:
        if tier not in STAGE30_10_1_ALLOWED_TIER_CODES:
            return False
    for flag in (
        policy.require_post_migration_ath,
        policy.require_migration_present,
        policy.require_current_market_context,
        policy.fail_closed_on_unknown,
    ):
        if not isinstance(flag, bool):
            return False
    return True


# ---------------------------------------------------------------------------
# Immutable model: per-candidate evaluation input
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Stage30_10DipEligibilityInput:
    """Immutable per-candidate compact tier-dip eligibility evaluation input.

    A passive carrier of the signals the classifier consults. Carries only
    safe scalars: opaque ids, closed-set status tokens / display tier token,
    ``Decimal`` magnitudes, an optional verified flag, and a caller-injected
    ISO-8601 UTC timestamp. No secret, no raw payload, no host, no transport
    destination.

      * ``candidate_id``                -- the safe-shape candidate id.
      * ``token_mint``                  -- the safe-shape token mint.
      * ``tier_token``                  -- the Stage 30.1 tier token (display
                                           ``Tier N`` form or the normalized
                                           code), or ``None``.
      * ``drawdown_from_ath``           -- the drawdown magnitude as a
                                           ``Decimal``, or ``None`` when
                                           unavailable.
      * ``migration_status``            -- the migration status token, or
                                           ``None``.
      * ``ath_status``                  -- the ATH status token, or ``None``.
      * ``market_context_status``       -- the current market context status
                                           token, or ``None``.
      * ``current_market_cap_usd``      -- the current market cap as a
                                           ``Decimal``, or ``None``.
      * ``post_migration_ath_verified`` -- whether the ATH is verified to be
                                           post-migration (``True`` /
                                           ``False`` / ``None``).
      * ``created_at_utc``              -- a caller-injected ISO-8601 UTC
                                           timestamp; NEVER a wall-clock read.
    """

    candidate_id: str
    token_mint: str
    tier_token: Optional[str]
    drawdown_from_ath: Optional[Decimal]
    migration_status: Optional[str]
    ath_status: Optional[str]
    market_context_status: Optional[str]
    current_market_cap_usd: Optional[Decimal]
    post_migration_ath_verified: Optional[bool]
    created_at_utc: str


# ---------------------------------------------------------------------------
# Immutable model: per-candidate eligibility audit record
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Stage30_10DipEligibilityRecord:
    """Immutable per-candidate compact tier-dip eligibility audit record.

    The classifier emits exactly one of these per evaluated candidate. It
    echoes the decision-relevant input signals and pins the classifier's
    closed-set ``decision`` / ``reason`` plus the boolean ``send_allowed``
    (``True`` only for ``ELIGIBLE_DIP``). Carries only safe scalars; no
    secret, no raw payload, no host, no transport destination, no env value.

      * ``candidate_id`` / ``token_mint``       -- echoed safe-shape ids.
      * ``tier_token``                          -- echoed Stage 30.1 tier
                                                   token.
      * ``drawdown_from_ath``                   -- echoed drawdown magnitude
                                                   (``Decimal`` or ``None``).
      * ``migration_status`` / ``ath_status`` / ``market_context_status``
                                                -- echoed status tokens.
      * ``current_market_cap_usd``              -- echoed current market cap
                                                   (``Decimal`` or ``None``).
      * ``post_migration_ath_verified``         -- echoed verified flag.
      * ``decision``                            -- one of
                                                   ``STAGE30_10_1_ELIGIBILITY_DECISIONS``.
      * ``reason``                              -- one of
                                                   ``STAGE30_10_1_ELIGIBILITY_REASONS``.
      * ``send_allowed``                        -- ``True`` iff ``decision``
                                                   is ``ELIGIBLE_DIP``.
      * ``created_at_utc``                      -- echoed caller-injected
                                                   ISO-8601 UTC timestamp.
    """

    candidate_id: str
    token_mint: str
    tier_token: Optional[str]
    drawdown_from_ath: Optional[Decimal]
    migration_status: Optional[str]
    ath_status: Optional[str]
    market_context_status: Optional[str]
    current_market_cap_usd: Optional[Decimal]
    post_migration_ath_verified: Optional[bool]
    decision: str
    reason: str
    send_allowed: bool
    created_at_utc: str


# ---------------------------------------------------------------------------
# Field-name helpers (pure; read dataclass field names)
# ---------------------------------------------------------------------------


def policy_field_names() -> Tuple[str, ...]:
    """Return the policy field names as a tuple."""
    return tuple(f.name for f in fields(Stage30_10DipEligibilityPolicy))


def input_field_names() -> Tuple[str, ...]:
    """Return the evaluation input field names as a tuple."""
    return tuple(f.name for f in fields(Stage30_10DipEligibilityInput))


def record_field_names() -> Tuple[str, ...]:
    """Return the eligibility audit record field names as a tuple."""
    return tuple(f.name for f in fields(Stage30_10DipEligibilityRecord))


__all__ = (
    # Minor version.
    "STAGE30_10_1_MINOR_VERSION",
    # Eligibility decisions.
    "DECISION_ELIGIBLE_DIP",
    "DECISION_SKIPPED_NOT_DIP",
    "DECISION_SKIPPED_TIER_UNKNOWN",
    "DECISION_SKIPPED_TIER_NOT_APPLICABLE",
    "DECISION_SKIPPED_MISSING_ATH",
    "DECISION_SKIPPED_MISSING_MIGRATION",
    "DECISION_SKIPPED_MISSING_MARKET_CONTEXT",
    "DECISION_INVALID_INPUT",
    "STAGE30_10_1_ELIGIBILITY_DECISIONS",
    "STAGE30_10_1_SEND_ALLOWED_DECISION",
    "is_eligibility_decision",
    # Eligibility reasons.
    "REASON_TIER_ALLOWED",
    "REASON_TIER_NOT_ALLOWED",
    "REASON_TIER_UNKNOWN",
    "REASON_TIER_NOT_APPLICABLE",
    "REASON_MISSING_ATH",
    "REASON_MISSING_MIGRATION",
    "REASON_MISSING_DRAWDOWN",
    "REASON_MISSING_MARKET_CONTEXT",
    "REASON_MISSING_CURRENT_MARKET_CAP",
    "REASON_PRE_MIGRATION_ATH_NOT_ALLOWED",
    "REASON_INVALID_CANDIDATE_ID",
    "REASON_INVALID_TOKEN_MINT",
    "REASON_INVALID_CREATED_AT_UTC",
    "REASON_INVALID_POLICY",
    "STAGE30_10_1_ELIGIBILITY_REASONS",
    "is_eligibility_reason",
    # Tier codes + normalization.
    "TIER_CODE_TIER_1",
    "TIER_CODE_TIER_2",
    "TIER_CODE_TIER_3",
    "TIER_CODE_TIER_UNKNOWN",
    "TIER_CODE_TIER_NOT_APPLICABLE",
    "STAGE30_10_1_TIER_CODE_VALUES",
    "STAGE30_10_1_ALLOWED_TIER_CODES",
    "normalize_tier_token",
    # Status tokens + present check.
    "MIGRATION_STATUS_PRESENT",
    "ATH_STATUS_PRESENT",
    "MARKET_CONTEXT_STATUS_PRESENT",
    "is_present_status",
    # Drawdown magnitude safe-shape validation.
    "is_finite_decimal",
    # created_at_utc safe-shape validation.
    "is_safe_created_at_utc",
    # Policy + records + helpers.
    "Stage30_10DipEligibilityPolicy",
    "DEFAULT_STAGE30_10_DIP_ELIGIBILITY_POLICY",
    "is_valid_policy",
    "Stage30_10DipEligibilityInput",
    "Stage30_10DipEligibilityRecord",
    "policy_field_names",
    "input_field_names",
    "record_field_names",
)

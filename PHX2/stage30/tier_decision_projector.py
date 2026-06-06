"""Stage 30.1 tier decision projector.

Pure projector that maps a Stage 27.4 ``AthContextRecord`` +
``MigrationContextRecord`` pair (plus a caller-supplied basis token
and an injected clock) to a single Stage 30.1
``TierDecisionRecord``. The projector NEVER fetches MC, NEVER opens
a network connection, NEVER reads the process environment, NEVER
calls ``datetime.now`` (the clock is caller-supplied), and NEVER
mutates its inputs.

Deterministic decision precedence (top-down, first match wins):

  1. ``migration_status != PRESENT``  -> ``Tier Not Applicable``
     with a closed-set ``NA_MIGRATION_*`` reason.
  2. ``ath_record is None`` (with migration PRESENT) -> ``Tier
     Unknown`` / ``UNKNOWN_ATH_NOT_PRESENT``.
  3. ``ath_since_migration_status == MAY_INCLUDE_PRE_MIGRATION`` ->
     ``Tier Not Applicable`` /
     ``NA_ATH_MAY_INCLUDE_PRE_MIGRATION``.
  4. ``ath_status != PRESENT`` -> ``Tier Unknown`` /
     ``UNKNOWN_ATH_NOT_PRESENT``.
  5. ``drawdown_from_ath is None`` -> ``Tier Unknown`` /
     ``UNKNOWN_DRAWDOWN_MISSING``.
  6. ``drawdown_from_ath`` fails the strict regex / Decimal parse /
     finiteness check -> ``Tier Unknown`` /
     ``UNKNOWN_DRAWDOWN_MALFORMED``.
  7. ``ath_value`` is missing / blank / malformed / non-finite / zero /
     negative (so the fractional drop has no safe denominator) ->
     ``Tier Unknown`` / ``UNKNOWN_ATH_VALUE_INVALID``.
  8. Band classification on the FRACTIONAL drop
     ``frac = abs(drawdown_from_ath) / ath_value``, evaluated by EXACT Decimal
     CROSS-MULTIPLICATION (compare the exact absolute drop against
     ``ath_value * boundary``) -- NEVER a context-rounded quotient, which could
     round a just-below-boundary value up into a band. ``drawdown_from_ath`` is
     the ABSOLUTE ``ATH - current_price`` delta Stage 27.4 emits (same currency
     as ``ath_value``) and is UNCHANGED, still echoed as the absolute
     ``drawdown_from_ath_raw``:
     - ``frac <  0.50``                  -> ``UNKNOWN_BELOW_TIER_1``
     - ``0.50 <= frac <= 0.60``          -> ``TIER_1_IN_BAND``
     - ``0.60 <  frac <  0.62``          -> ``UNKNOWN_IN_GAP_T1_T2``
     - ``0.62 <= frac <= 0.80``          -> ``TIER_2_IN_BAND``
     - ``0.80 <  frac <  0.82``          -> ``UNKNOWN_IN_GAP_T2_T3``
     - ``0.82 <= frac <= 0.95``          -> ``TIER_3_IN_BAND``
     - ``frac >  0.95``                  -> ``UNKNOWN_GRAVEYARD``

The band check uses ``Decimal`` exclusively; ``float`` is NEVER
introduced. The absolute drop is taken with ``copy_abs`` (no context
rounding), the band edges are computed exactly, and the projector NEVER
rounds across a boundary and NEVER divides (so it NEVER divides by zero;
a non-positive ``ath_value`` fails closed above).

Caller-shape failures (invalid ``basis`` token, non-string /
unsafe-shape ``created_at_utc``, ``ath_record`` not a
``AthContextRecord``, ``migration_record`` not a
``MigrationContextRecord``) raise ``Stage30_1TierDecisionError``
with a closed-set reason token. Degraded inputs (missing record,
missing drawdown, malformed drawdown, degraded ATH / migration
status) DO NOT raise; they produce a deterministic
``TierDecisionRecord`` with the appropriate tier / reason pair.

Discipline:

  * Stdlib only (``re`` / ``decimal`` / ``typing``).
  * Stage 27.4 model modules imported read-only (no Stage 27 file
    is modified).
  * No ``os.environ`` / ``os.getenv`` / ``os.environb`` access.
  * No network, no HTTP, no gRPC, no WebSocket, no socket.
  * No Discord, Telegram, X / social, webhook, Helius, Chainstack,
    Birdeye, Dexscreener, Pump.fun reference.
  * No PHX1 import. No legacy phoenix-1 import path.
  * No Stage 21-29 production-source modification.
  * No top-level Call (no implicit I/O at import time).
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation, localcontext
from typing import Optional

from PHX2.stage27.migration_context_models import (
    MIGRATION_STATUS_MISSING,
    MIGRATION_STATUS_PRESENT,
    MIGRATION_STATUS_SOURCE_ERROR,
    MIGRATION_STATUS_UNSUPPORTED_PAIR,
    MIGRATION_STATUS_UNTRUSTED,
    MigrationContextRecord,
)
from PHX2.stage27.price_ath_context_models import (
    ATH_SINCE_MIGRATION_STATUS_MAY_INCLUDE_PRE_MIGRATION,
    ATH_SINCE_MIGRATION_STATUS_UNKNOWN,
    ATH_STATUS_PRESENT,
    ATH_STATUS_UNAVAILABLE,
    AthContextRecord,
)
from PHX2.stage30.tier_decision_models import (
    BASIS_VALUES,
    STAGE30_1_TIER_DECISION_SCHEMA_VERSION,
    Stage30_1TierDecisionError,
    TierDecisionRecord,
    TIER_REASON_NA_ATH_MAY_INCLUDE_PRE_MIGRATION,
    TIER_REASON_NA_MIGRATION_MISSING,
    TIER_REASON_NA_MIGRATION_SOURCE_ERROR,
    TIER_REASON_NA_MIGRATION_UNSUPPORTED_PAIR,
    TIER_REASON_NA_MIGRATION_UNTRUSTED,
    TIER_REASON_TIER_1_IN_BAND,
    TIER_REASON_TIER_2_IN_BAND,
    TIER_REASON_TIER_3_IN_BAND,
    TIER_REASON_UNKNOWN_ATH_NOT_PRESENT,
    TIER_REASON_UNKNOWN_ATH_VALUE_INVALID,
    TIER_REASON_UNKNOWN_BELOW_TIER_1,
    TIER_REASON_UNKNOWN_DRAWDOWN_MALFORMED,
    TIER_REASON_UNKNOWN_DRAWDOWN_MISSING,
    TIER_REASON_UNKNOWN_GRAVEYARD,
    TIER_REASON_UNKNOWN_IN_GAP_T1_T2,
    TIER_REASON_UNKNOWN_IN_GAP_T2_T3,
    TIER_TOKEN_TIER_1,
    TIER_TOKEN_TIER_2,
    TIER_TOKEN_TIER_3,
    TIER_TOKEN_TIER_NOT_APPLICABLE,
    TIER_TOKEN_TIER_UNKNOWN,
    is_basis_value,
)


# ---------------------------------------------------------------------------
# Band constants (Decimal, never float)
# ---------------------------------------------------------------------------


_BAND_T1_LOW: Decimal = Decimal("0.50")
_BAND_T1_HIGH: Decimal = Decimal("0.60")
_BAND_T2_LOW: Decimal = Decimal("0.62")
_BAND_T2_HIGH: Decimal = Decimal("0.80")
_BAND_T3_LOW: Decimal = Decimal("0.82")
_BAND_T3_HIGH: Decimal = Decimal("0.95")


# ---------------------------------------------------------------------------
# Strict canonical decimal-text pattern + safe identifier shape
# ---------------------------------------------------------------------------
#
# The strict pattern rejects:
#
#   * leading '+'  (e.g. "+0.50")
#   * leading '.' (e.g. ".5")
#   * trailing '.' (e.g. "5.")
#   * scientific notation (e.g. "0.5e0")
#   * non-finite literals ("NaN", "Infinity", "-Infinity")
#   * whitespace anywhere
#   * empty string
#   * non-string types
#
# Accepts the canonical Stage 27.4 emit shape ``\d+(\.\d+)?`` and the
# leading-minus signed shape ``-\d+(\.\d+)?``. Stage 27.4 itself emits
# only non-negative canonical decimal text under the current reader
# implementation; the projector still defensively takes ``abs`` before
# the band check.


_STRICT_DECIMAL_TEXT_PATTERN: "re.Pattern[str]" = re.compile(
    r"^-?\d+(\.\d+)?$"
)


_SAFE_ISO8601_UTC_PATTERN: "re.Pattern[str]" = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$"
)


# Solana base58 alphabet (no 0, no O, no I, no l).
_BASE58_ALPHABET: frozenset = frozenset(
    "123456789ABCDEFGHJKLMNPQRSTUVWXYZ"
    "abcdefghijkmnopqrstuvwxyz"
)


_MIN_SAFE_MINT_LENGTH: int = 32
_MAX_SAFE_MINT_LENGTH: int = 64


# Identifier alphabet (ping_id / candidate_id / session_id):
# printable ASCII alphanumerics + a small allowlist of separators.
# Excludes whitespace, slashes, equals signs, colons, and the rest of
# the URL / auth / env-name shape characters by construction.
_SAFE_IDENTIFIER_ALPHABET: frozenset = frozenset(
    "abcdefghijklmnopqrstuvwxyz"
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    "0123456789_-."
)


_MIN_SAFE_IDENTIFIER_LENGTH: int = 1
_MAX_SAFE_IDENTIFIER_LENGTH: int = 64


# Decimal-echo allowlist: the only chars that may appear in an echoed
# drawdown_from_ath value. A safe echo MUST be a string of length
# [1, 64] whose every character is in this alphabet. Anything else
# (URL / auth / wallet-shape input) is redacted to ``None``.
_SAFE_DRAWDOWN_ECHO_ALPHABET: frozenset = frozenset("0123456789+-.")


_MIN_SAFE_DRAWDOWN_ECHO_LENGTH: int = 1
_MAX_SAFE_DRAWDOWN_ECHO_LENGTH: int = 64


# ---------------------------------------------------------------------------
# Safe-shape helpers
# ---------------------------------------------------------------------------


def _is_strict_decimal_text(value: object) -> bool:
    """Return ``True`` iff ``value`` is a string that matches the
    Stage 30.1 strict canonical decimal-text pattern.
    """
    if not isinstance(value, str):
        return False
    return _STRICT_DECIMAL_TEXT_PATTERN.fullmatch(value) is not None


def _positive_finite_decimal_or_none(value: object) -> Optional[Decimal]:
    """Return a finite, strictly-positive ``Decimal`` parsed from a strict
    canonical decimal-text ``value``, or ``None``.

    Pure / total; never raises. ``None`` is returned for a missing (``None``),
    blank, non-string, malformed, scientific-notation, non-finite
    (``NaN`` / ``Infinity``), zero, or negative value -- i.e. for every input
    that cannot serve as a safe strictly-positive denominator. Used to gate the
    ``ath_value`` the fractional-drawdown band divides by, so a bad ATH value
    fails the tier closed to ``Tier Unknown`` and the projector NEVER divides by
    zero.
    """
    if not _is_strict_decimal_text(value):
        return None
    try:
        parsed = Decimal(value)  # type: ignore[arg-type]
    except (InvalidOperation, ValueError, ArithmeticError, TypeError):
        return None
    if not parsed.is_finite():
        return None
    if parsed <= 0:
        return None
    return parsed


def _is_safe_iso8601_utc_text(value: object) -> bool:
    """Return ``True`` iff ``value`` matches a strict ISO-8601 UTC
    pattern ``YYYY-MM-DDTHH:MM:SS[.fff]Z``.

    Defensive lightweight check; the projector uses this to gate
    ``created_at_utc`` so a stray URL substring cannot ride through.
    """
    if not isinstance(value, str):
        return False
    return _SAFE_ISO8601_UTC_PATTERN.fullmatch(value) is not None


def _sanitize_identifier(value: object) -> Optional[str]:
    """Return ``value`` if it passes the Stage 30.1 safe-shape
    identifier check, else ``None``.

    The allowlist is intentionally narrow: printable ASCII alphanum +
    ``_`` / ``-`` / ``.`` in length range [1, 64]. Any value
    containing whitespace, a slash, an equals sign, a colon, a
    quote, an at-sign, an ampersand, or any other character outside
    the allowlist redacts to ``None``.
    """
    if not isinstance(value, str):
        return None
    n = len(value)
    if n < _MIN_SAFE_IDENTIFIER_LENGTH:
        return None
    if n > _MAX_SAFE_IDENTIFIER_LENGTH:
        return None
    for ch in value:
        if ch not in _SAFE_IDENTIFIER_ALPHABET:
            return None
    return value


def _sanitize_mint(value: object) -> Optional[str]:
    """Return ``value`` if it passes the Stage 30.1 safe-shape mint
    check (Solana base58, length [32, 64]), else ``None``.
    """
    if not isinstance(value, str):
        return None
    n = len(value)
    if n < _MIN_SAFE_MINT_LENGTH:
        return None
    if n > _MAX_SAFE_MINT_LENGTH:
        return None
    for ch in value:
        if ch not in _BASE58_ALPHABET:
            return None
    return value


def _safe_drawdown_text_echo(value: object) -> Optional[str]:
    """Return ``value`` verbatim if it is a safe-shape decimal echo;
    otherwise ``None``.

    The echo is preserved even for non-canonical decimal text (e.g.
    ``"+0.50"`` / ``".5"`` / ``"5."``) so the operator can audit WHY
    the projector classified the input as ``UNKNOWN_DRAWDOWN_MALFORMED``.
    The allowlist rejects anything containing a character outside
    ``[0-9+\\-.]`` (URLs, auth headers, secret-shape strings all
    redact to ``None``).
    """
    if value is None:
        return None
    if not isinstance(value, str):
        return None
    n = len(value)
    if n < _MIN_SAFE_DRAWDOWN_ECHO_LENGTH:
        return None
    if n > _MAX_SAFE_DRAWDOWN_ECHO_LENGTH:
        return None
    for ch in value:
        if ch not in _SAFE_DRAWDOWN_ECHO_ALPHABET:
            return None
    return value


# ---------------------------------------------------------------------------
# Migration status -> NA reason mapping
# ---------------------------------------------------------------------------


_MIGRATION_STATUS_TO_NA_REASON: dict = {
    MIGRATION_STATUS_MISSING: (
        TIER_REASON_NA_MIGRATION_MISSING
    ),
    MIGRATION_STATUS_UNTRUSTED: (
        TIER_REASON_NA_MIGRATION_UNTRUSTED
    ),
    MIGRATION_STATUS_UNSUPPORTED_PAIR: (
        TIER_REASON_NA_MIGRATION_UNSUPPORTED_PAIR
    ),
    MIGRATION_STATUS_SOURCE_ERROR: (
        TIER_REASON_NA_MIGRATION_SOURCE_ERROR
    ),
}


def _migration_status_to_na_reason(status: object) -> str:
    """Map a Stage 27.4 migration status to the matching Tier Not
    Applicable reason token.

    Falls back to ``NA_MIGRATION_MISSING`` for any non-PRESENT value
    that does not appear in the mapping (defensive; the Stage 27.4
    closed set is small and known, but a future Stage 27 extension
    must not silently widen Stage 30.1's reason set).
    """
    if isinstance(status, str) and status in _MIGRATION_STATUS_TO_NA_REASON:
        return _MIGRATION_STATUS_TO_NA_REASON[status]
    return TIER_REASON_NA_MIGRATION_MISSING


# ---------------------------------------------------------------------------
# Public projector
# ---------------------------------------------------------------------------


def decide_tier(
    *,
    ath_record: Optional[AthContextRecord],
    migration_record: Optional[MigrationContextRecord],
    basis: str,
    created_at_utc: str,
    ping_id: Optional[str] = None,
    candidate_id: Optional[str] = None,
    session_id: Optional[str] = None,
    mint: Optional[str] = None,
) -> TierDecisionRecord:
    """Project the inputs onto a Stage 30.1 ``TierDecisionRecord``.

    Pure / deterministic / no I/O. Identical inputs always produce a
    byte-identical record (``NamedTuple`` equality).

    Raises ``Stage30_1TierDecisionError`` on caller-shape failures
    (invalid ``basis``, unsafe-shape ``created_at_utc``, non-record
    typed ``ath_record`` / ``migration_record``). Degraded inputs
    (missing record, missing drawdown, malformed drawdown, degraded
    ATH / migration status) DO NOT raise; they produce a
    deterministic ``TierDecisionRecord`` with the appropriate tier
    token + reason token pair.
    """
    # ---- Caller-shape validation ----
    if not is_basis_value(basis):
        raise Stage30_1TierDecisionError("BASIS_INVALID")
    if not _is_safe_iso8601_utc_text(created_at_utc):
        raise Stage30_1TierDecisionError(
            "CREATED_AT_UTC_NOT_SAFE_ISO8601"
        )
    if ath_record is not None and not isinstance(
        ath_record, AthContextRecord
    ):
        raise Stage30_1TierDecisionError(
            "ATH_RECORD_INVALID_TYPE"
        )
    if migration_record is not None and not isinstance(
        migration_record, MigrationContextRecord
    ):
        raise Stage30_1TierDecisionError(
            "MIGRATION_RECORD_INVALID_TYPE"
        )

    # ---- Sanitize optional identifiers ----
    safe_session_id = _sanitize_identifier(session_id)
    safe_ping_id = _sanitize_identifier(ping_id)
    safe_candidate_id = _sanitize_identifier(candidate_id)
    safe_mint = _sanitize_mint(mint)

    # ---- Extract closed-set inputs (with explicit fallbacks) ----
    if migration_record is None:
        migration_status: str = MIGRATION_STATUS_MISSING
    else:
        migration_status = migration_record.migration_status

    if ath_record is None:
        ath_status: str = ATH_STATUS_UNAVAILABLE
        ath_since_migration_status: str = (
            ATH_SINCE_MIGRATION_STATUS_UNKNOWN
        )
        raw_drawdown: Optional[str] = None
        raw_ath_value: Optional[str] = None
    else:
        ath_status = ath_record.ath_status
        ath_since_migration_status = (
            ath_record.ath_since_migration_status
        )
        raw_drawdown = ath_record.drawdown_from_ath
        raw_ath_value = ath_record.ath_value

    safe_drawdown_echo = _safe_drawdown_text_echo(raw_drawdown)

    # ---- Step 1: migration check ----
    if migration_status != MIGRATION_STATUS_PRESENT:
        return TierDecisionRecord(
            schema_version=STAGE30_1_TIER_DECISION_SCHEMA_VERSION,
            session_id=safe_session_id,
            ping_id=safe_ping_id,
            candidate_id=safe_candidate_id,
            mint=safe_mint,
            basis=basis,
            drawdown_from_ath_raw=safe_drawdown_echo,
            drop_positive=None,
            ath_status=ath_status,
            ath_since_migration_status=ath_since_migration_status,
            migration_status=migration_status,
            tier_token=TIER_TOKEN_TIER_NOT_APPLICABLE,
            tier_reason=_migration_status_to_na_reason(
                migration_status
            ),
            created_at_utc=created_at_utc,
        )

    # From here, migration_status is PRESENT.

    # ---- Step 2: ATH record missing -> Tier Unknown ----
    if ath_record is None:
        return TierDecisionRecord(
            schema_version=STAGE30_1_TIER_DECISION_SCHEMA_VERSION,
            session_id=safe_session_id,
            ping_id=safe_ping_id,
            candidate_id=safe_candidate_id,
            mint=safe_mint,
            basis=basis,
            drawdown_from_ath_raw=safe_drawdown_echo,
            drop_positive=None,
            ath_status=ath_status,
            ath_since_migration_status=ath_since_migration_status,
            migration_status=migration_status,
            tier_token=TIER_TOKEN_TIER_UNKNOWN,
            tier_reason=TIER_REASON_UNKNOWN_ATH_NOT_PRESENT,
            created_at_utc=created_at_utc,
        )

    # ---- Step 3: ATH may include pre-migration -> Tier NA ----
    if ath_since_migration_status == (
        ATH_SINCE_MIGRATION_STATUS_MAY_INCLUDE_PRE_MIGRATION
    ):
        return TierDecisionRecord(
            schema_version=STAGE30_1_TIER_DECISION_SCHEMA_VERSION,
            session_id=safe_session_id,
            ping_id=safe_ping_id,
            candidate_id=safe_candidate_id,
            mint=safe_mint,
            basis=basis,
            drawdown_from_ath_raw=safe_drawdown_echo,
            drop_positive=None,
            ath_status=ath_status,
            ath_since_migration_status=ath_since_migration_status,
            migration_status=migration_status,
            tier_token=TIER_TOKEN_TIER_NOT_APPLICABLE,
            tier_reason=(
                TIER_REASON_NA_ATH_MAY_INCLUDE_PRE_MIGRATION
            ),
            created_at_utc=created_at_utc,
        )

    # ---- Step 4: ATH status not PRESENT -> Tier Unknown ----
    if ath_status != ATH_STATUS_PRESENT:
        return TierDecisionRecord(
            schema_version=STAGE30_1_TIER_DECISION_SCHEMA_VERSION,
            session_id=safe_session_id,
            ping_id=safe_ping_id,
            candidate_id=safe_candidate_id,
            mint=safe_mint,
            basis=basis,
            drawdown_from_ath_raw=safe_drawdown_echo,
            drop_positive=None,
            ath_status=ath_status,
            ath_since_migration_status=ath_since_migration_status,
            migration_status=migration_status,
            tier_token=TIER_TOKEN_TIER_UNKNOWN,
            tier_reason=TIER_REASON_UNKNOWN_ATH_NOT_PRESENT,
            created_at_utc=created_at_utc,
        )

    # ---- Step 5: drawdown missing -> Tier Unknown ----
    if raw_drawdown is None:
        return TierDecisionRecord(
            schema_version=STAGE30_1_TIER_DECISION_SCHEMA_VERSION,
            session_id=safe_session_id,
            ping_id=safe_ping_id,
            candidate_id=safe_candidate_id,
            mint=safe_mint,
            basis=basis,
            drawdown_from_ath_raw=None,
            drop_positive=None,
            ath_status=ath_status,
            ath_since_migration_status=ath_since_migration_status,
            migration_status=migration_status,
            tier_token=TIER_TOKEN_TIER_UNKNOWN,
            tier_reason=TIER_REASON_UNKNOWN_DRAWDOWN_MISSING,
            created_at_utc=created_at_utc,
        )

    # ---- Step 6: drawdown malformed -> Tier Unknown ----
    if not _is_strict_decimal_text(raw_drawdown):
        return TierDecisionRecord(
            schema_version=STAGE30_1_TIER_DECISION_SCHEMA_VERSION,
            session_id=safe_session_id,
            ping_id=safe_ping_id,
            candidate_id=safe_candidate_id,
            mint=safe_mint,
            basis=basis,
            drawdown_from_ath_raw=safe_drawdown_echo,
            drop_positive=None,
            ath_status=ath_status,
            ath_since_migration_status=ath_since_migration_status,
            migration_status=migration_status,
            tier_token=TIER_TOKEN_TIER_UNKNOWN,
            tier_reason=TIER_REASON_UNKNOWN_DRAWDOWN_MALFORMED,
            created_at_utc=created_at_utc,
        )

    try:
        signed = Decimal(raw_drawdown)
    except (InvalidOperation, ValueError, ArithmeticError, TypeError):
        return TierDecisionRecord(
            schema_version=STAGE30_1_TIER_DECISION_SCHEMA_VERSION,
            session_id=safe_session_id,
            ping_id=safe_ping_id,
            candidate_id=safe_candidate_id,
            mint=safe_mint,
            basis=basis,
            drawdown_from_ath_raw=safe_drawdown_echo,
            drop_positive=None,
            ath_status=ath_status,
            ath_since_migration_status=ath_since_migration_status,
            migration_status=migration_status,
            tier_token=TIER_TOKEN_TIER_UNKNOWN,
            tier_reason=TIER_REASON_UNKNOWN_DRAWDOWN_MALFORMED,
            created_at_utc=created_at_utc,
        )

    if not signed.is_finite():
        return TierDecisionRecord(
            schema_version=STAGE30_1_TIER_DECISION_SCHEMA_VERSION,
            session_id=safe_session_id,
            ping_id=safe_ping_id,
            candidate_id=safe_candidate_id,
            mint=safe_mint,
            basis=basis,
            drawdown_from_ath_raw=safe_drawdown_echo,
            drop_positive=None,
            ath_status=ath_status,
            ath_since_migration_status=ath_since_migration_status,
            migration_status=migration_status,
            tier_token=TIER_TOKEN_TIER_UNKNOWN,
            tier_reason=TIER_REASON_UNKNOWN_DRAWDOWN_MALFORMED,
            created_at_utc=created_at_utc,
        )

    # ---- Step 7: ath_value must be a safe strictly-positive denominator ----
    #
    # Stage 27.4 emits ``drawdown_from_ath`` as an ABSOLUTE price delta
    # (``ATH - current_price``) in the ATH's own currency. The Stage 30.1 tier
    # bands (0.50..0.95, graveyard above 0.95) are FRACTIONAL drop bands, so the
    # tier MUST classify the fraction ``abs(drawdown) / ath_value`` -- NOT the
    # absolute delta (which would push every sub-dollar / memecoin token below
    # Tier 1). ``drawdown_from_ath`` itself stays the absolute USD delta (echoed
    # unchanged as ``drawdown_from_ath_raw``); only the BAND INPUT is the
    # fraction. A missing / blank / malformed / non-finite / zero / negative
    # ``ath_value`` cannot be a safe denominator -> fail closed (NEVER /0).
    #
    # ``copy_abs`` (NOT ``abs``) so a long-precision drawdown is NEVER rounded to
    # the context precision: the absolute value is preserved EXACTLY for the
    # display echo and the exact band comparison below.
    drop = signed.copy_abs()
    ath_value_dec = _positive_finite_decimal_or_none(raw_ath_value)
    if ath_value_dec is None:
        return TierDecisionRecord(
            schema_version=STAGE30_1_TIER_DECISION_SCHEMA_VERSION,
            session_id=safe_session_id,
            ping_id=safe_ping_id,
            candidate_id=safe_candidate_id,
            mint=safe_mint,
            basis=basis,
            drawdown_from_ath_raw=safe_drawdown_echo,
            drop_positive=None,
            ath_status=ath_status,
            ath_since_migration_status=ath_since_migration_status,
            migration_status=migration_status,
            tier_token=TIER_TOKEN_TIER_UNKNOWN,
            tier_reason=TIER_REASON_UNKNOWN_ATH_VALUE_INVALID,
            created_at_utc=created_at_utc,
        )

    # ``drop_positive`` stays the EXACT absolute drop (no context rounding);
    # only the band CLASSIFICATION is fractional. The absolute delta is also
    # echoed as ``drawdown_from_ath_raw``.
    drop_positive_text = format(drop, "f")

    # ---- Step 8: band classification via EXACT Decimal cross-multiplication ----
    #
    # The bands are fractional (``frac = drop / ath_value``), but computing the
    # quotient under the Decimal context can ROUND a value just below a boundary
    # UP into the band (e.g. ``1.8599..99 / 3`` rounds to ``0.6200..00`` and
    # mis-bands a gap value as Tier 2). So instead of a rounded quotient we
    # compare the EXACT absolute drop against the band edges
    # ``ath_value * boundary``. ``ath_value`` is strictly positive, so the
    # inequality directions are identical to the quotient form. The edge products
    # are computed at precision high enough that the multiplications are exact;
    # Decimal comparisons themselves never round. Boundaries are UNCHANGED.
    with localcontext() as ctx:
        edge_prec = len(ath_value_dec.as_tuple().digits) + 6
        if ctx.prec < edge_prec:
            ctx.prec = edge_prec
        edge_t1_low = ath_value_dec * _BAND_T1_LOW
        edge_t1_high = ath_value_dec * _BAND_T1_HIGH
        edge_t2_low = ath_value_dec * _BAND_T2_LOW
        edge_t2_high = ath_value_dec * _BAND_T2_HIGH
        edge_t3_low = ath_value_dec * _BAND_T3_LOW
        edge_t3_high = ath_value_dec * _BAND_T3_HIGH

    if drop < edge_t1_low:
        tier_token = TIER_TOKEN_TIER_UNKNOWN
        tier_reason = TIER_REASON_UNKNOWN_BELOW_TIER_1
    elif drop <= edge_t1_high:
        tier_token = TIER_TOKEN_TIER_1
        tier_reason = TIER_REASON_TIER_1_IN_BAND
    elif drop < edge_t2_low:
        tier_token = TIER_TOKEN_TIER_UNKNOWN
        tier_reason = TIER_REASON_UNKNOWN_IN_GAP_T1_T2
    elif drop <= edge_t2_high:
        tier_token = TIER_TOKEN_TIER_2
        tier_reason = TIER_REASON_TIER_2_IN_BAND
    elif drop < edge_t3_low:
        tier_token = TIER_TOKEN_TIER_UNKNOWN
        tier_reason = TIER_REASON_UNKNOWN_IN_GAP_T2_T3
    elif drop <= edge_t3_high:
        tier_token = TIER_TOKEN_TIER_3
        tier_reason = TIER_REASON_TIER_3_IN_BAND
    else:
        tier_token = TIER_TOKEN_TIER_UNKNOWN
        tier_reason = TIER_REASON_UNKNOWN_GRAVEYARD

    return TierDecisionRecord(
        schema_version=STAGE30_1_TIER_DECISION_SCHEMA_VERSION,
        session_id=safe_session_id,
        ping_id=safe_ping_id,
        candidate_id=safe_candidate_id,
        mint=safe_mint,
        basis=basis,
        drawdown_from_ath_raw=safe_drawdown_echo,
        drop_positive=drop_positive_text,
        ath_status=ath_status,
        ath_since_migration_status=ath_since_migration_status,
        migration_status=migration_status,
        tier_token=tier_token,
        tier_reason=tier_reason,
        created_at_utc=created_at_utc,
    )


__all__ = (
    "decide_tier",
)

"""Stage 30.7.1 pure offline ATH-context projection adapter.

Pure deterministic function ``project_ath_context(evidence,
market_context_unit)`` that turns caller-supplied sanitized ATH
evidence into a Stage-30-owned ``Stage30_7AthContextProjection``
carrying the single safe compact ``ATH`` display string (a ``$Y``
value or the literal ``Unknown``). This is the Stage 30.7 ATH brain:
the deterministic projection logic that lands BEFORE any runtime
wiring, any provider call, any drawdown / tier recomputation, and any
Discord send.

The adapter NEVER opens a network connection, NEVER reads the process
environment, NEVER touches the filesystem, NEVER calls a provider,
NEVER calls ``datetime.now``, NEVER mutates its inputs, NEVER
recomputes a drawdown / tier, NEVER routes data into Stage 30.1 /
30.2 / 30.3 runtime, and NEVER triggers a transport send. It is
TOTAL: it never raises for bad evidence. Any invalid / missing /
untrusted / unit-incompatible / redaction-unsafe / off-closed-set
input fails closed to an ``ATH_UNKNOWN`` projection whose display is
the literal ``Unknown`` -- it NEVER fabricates a peak. ``runtime_consumable``
is hard-locked ``False`` on every projection.

Decision order (Stage 30.7.0 spec lock §5 / §6 / §7):

  1. Source dominance. A non-PRESENT source status
     (``UNAVAILABLE`` / ``ERROR`` / ``STALE`` / ``CONFLICTING``), an
     off-closed-set / missing source status, or malformed evidence
     degrades to ``Unknown`` REGARDLESS of any claimed value.
  2. Redaction. A non-``True`` ``redaction_safe`` -- an explicit
     non-``True`` value OR a missing redaction proof on malformed
     duck-typed evidence -- degrades to ``Unknown`` (fail closed; a
     missing redaction proof is never trusted).
  3. Value. Missing / non-numeric / non-finite / non-positive degrades
     to ``Unknown``.
  4. Unit. An unrecognized / ``UNKNOWN`` / display-deferred unit, or a
     unit that disagrees with the market context unit, degrades to
     ``Unknown`` (never mixing USD and SOL).
  5. Basis. A price-derived basis is never promoted to ``ATH_KNOWN``
     (it is at most ``ATH_UNVERIFIED`` and still displays ``Unknown``
     in this slice); an absent / off-set basis degrades to ``Unknown``.
     Only a PRESENT source + positive finite value + compatible USD
     unit + observed-market-cap basis yields ``ATH_KNOWN`` and a
     compact ``$Y`` display.

Only an ``ATH_KNOWN`` projection is trusted for a future drawdown /
tier anchor (``should_trust_for_drawdown=True``); Stage 30.7.1 itself
recomputes NO drawdown / tier.

Discipline:

  * Stdlib only (``decimal`` / ``math`` / ``re`` / ``typing``).
  * Stage 30.7.1 sibling module ``stage30_7_ath_context_models``
    imported read-only.
  * No ``os`` import, no env read, no ``pathlib`` / ``shutil`` /
    ``sqlite3`` / zstd import, no provider / network / Discord import.
  * No PHX1 import. No Stage 21-29 production-source import.
  * No compact renderer / model / orchestrator import (the projection
    does NOT wire into runtime in this slice).
  * No network / env / filesystem I/O at import time.
"""

from __future__ import annotations

import math
import re
from decimal import (
    Decimal,
    InvalidOperation,
    ROUND_DOWN,
)
from typing import Optional, Tuple

from PHX2.stage30.stage30_7_ath_context_models import (
    ATH_BASIS_MARKET_CAP_OBSERVED,
    ATH_BASIS_NONE,
    ATH_BASIS_PRICE_DERIVED,
    ATH_DISPLAY_UNKNOWN,
    ATH_REASON_KNOWN_USD_MARKET_CAP,
    ATH_REASON_UNKNOWN_INVALID_INPUT,
    ATH_REASON_UNKNOWN_REDACTION_UNSAFE,
    ATH_REASON_UNKNOWN_SOURCE_CONFLICTING,
    ATH_REASON_UNKNOWN_SOURCE_ERROR,
    ATH_REASON_UNKNOWN_SOURCE_STALE,
    ATH_REASON_UNKNOWN_SOURCE_UNAVAILABLE,
    ATH_REASON_UNKNOWN_UNIT_INCOMPATIBLE,
    ATH_REASON_UNKNOWN_UNIT_UNSUPPORTED,
    ATH_REASON_UNKNOWN_VALUE_MISSING,
    ATH_REASON_UNKNOWN_VALUE_NON_POSITIVE,
    ATH_REASON_UNKNOWN_VALUE_NOT_FINITE,
    ATH_REASON_UNKNOWN_VALUE_NOT_NUMERIC,
    ATH_REASON_UNVERIFIED_PRICE_DERIVED,
    ATH_SOURCE_STATUS_CONFLICTING,
    ATH_SOURCE_STATUS_ERROR,
    ATH_SOURCE_STATUS_PRESENT,
    ATH_SOURCE_STATUS_STALE,
    ATH_SOURCE_STATUS_UNAVAILABLE,
    ATH_STATUS_KNOWN,
    ATH_STATUS_UNKNOWN,
    ATH_STATUS_UNVERIFIED,
    ATH_UNIT_SOL,
    ATH_UNIT_UNKNOWN,
    ATH_UNIT_USD,
    STAGE30_7_1_ATH_CONTEXT_PROJECTION_VERSION,
    STAGE30_7_1_ATH_CONTEXT_SCHEMA_VERSION,
    STAGE30_7_1_DEFAULT_MARKET_CONTEXT_UNIT,
    Stage30_7AthContextProjection,
)


# ---------------------------------------------------------------------------
# Strict decimal-text gate + magnitude constants
# ---------------------------------------------------------------------------
#
# A decimal-text value string is one or more ASCII digits, optionally
# with a single leading ``-`` sign, optionally followed by a single
# ``.`` and one or more ASCII digits. Leading ``+``, leading / trailing
# whitespace, multiple signs / dots, ``E`` / ``e`` scientific notation,
# hex / octal / binary prefixes, underscores, and ``NaN`` / ``Infinity``
# literals are all rejected (they classify as VALUE_NOT_NUMERIC). A
# leading ``-`` is accepted by the pattern so a negative value classifies
# as VALUE_NON_POSITIVE rather than VALUE_NOT_NUMERIC.


_SIGNED_DECIMAL_TEXT_PATTERN: "re.Pattern[str]" = re.compile(
    r"\A-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?\Z"
)


_ONE_THOUSAND: Decimal = Decimal("1000")
_ONE_MILLION: Decimal = Decimal("1000000")


# ---------------------------------------------------------------------------
# Internal: classify the candidate ATH value (fail closed)
# ---------------------------------------------------------------------------


def _classify_ath_value(
    value: object,
) -> Tuple[Optional[Decimal], Optional[str]]:
    """Classify a candidate ATH value into a positive finite
    ``Decimal`` or a closed-set failure reason token.

    Returns ``(decimal, None)`` on success or ``(None, reason)`` where
    ``reason`` is one of the value-class ``ATH_REASON_*`` tokens
    (MISSING / NOT_NUMERIC / NOT_FINITE / NON_POSITIVE). Pure / total:
    never raises. ``bool`` is rejected as non-numeric (``bool`` is an
    ``int`` subclass and must never be accepted as an ATH value).
    """
    if value is None:
        return None, ATH_REASON_UNKNOWN_VALUE_MISSING
    if isinstance(value, bool):
        return None, ATH_REASON_UNKNOWN_VALUE_NOT_NUMERIC
    if isinstance(value, int):
        parsed = Decimal(value)
    elif isinstance(value, float):
        if not math.isfinite(value):
            return None, ATH_REASON_UNKNOWN_VALUE_NOT_FINITE
        try:
            parsed = Decimal(str(value))
        except (InvalidOperation, ValueError, ArithmeticError, TypeError):
            return None, ATH_REASON_UNKNOWN_VALUE_NOT_NUMERIC
    elif isinstance(value, Decimal):
        if not value.is_finite():
            return None, ATH_REASON_UNKNOWN_VALUE_NOT_FINITE
        parsed = value
    elif isinstance(value, str):
        if _SIGNED_DECIMAL_TEXT_PATTERN.fullmatch(value) is None:
            return None, ATH_REASON_UNKNOWN_VALUE_NOT_NUMERIC
        try:
            parsed = Decimal(value)
        except (InvalidOperation, ValueError, ArithmeticError, TypeError):
            return None, ATH_REASON_UNKNOWN_VALUE_NOT_NUMERIC
        if not parsed.is_finite():
            return None, ATH_REASON_UNKNOWN_VALUE_NOT_FINITE
    else:
        return None, ATH_REASON_UNKNOWN_VALUE_NOT_NUMERIC

    if parsed <= 0:
        return None, ATH_REASON_UNKNOWN_VALUE_NON_POSITIVE
    return parsed, None


# ---------------------------------------------------------------------------
# Internal: canonical decimal-text echo + compact USD formatter
# ---------------------------------------------------------------------------


def _canonical_decimal_text(value: Decimal) -> str:
    """Return a plain (non-scientific) canonical decimal-text echo of a
    finite ``Decimal`` (e.g. ``Decimal("12345.0")`` -> ``"12345.0"``).
    """
    return format(value, "f")


def _format_known_usd_compact(magnitude: Decimal) -> str:
    """Return the compact ``$Y`` USD display string for a positive
    finite ``Decimal`` magnitude.

    Matches the existing Stage 30.4.1 compact MC / LP formatting (so a
    displayed ATH renders consistently next to the displayed ``MC`` on
    the same compact line): truncating (``ROUND_DOWN``) magnitude
    buckets with a lowercase ``k`` thousands suffix and an uppercase
    ``M`` millions suffix, one decimal place only when the truncated
    tenths digit is non-zero.

      * ``27``        -> ``"$27"``
      * ``999``       -> ``"$999"``
      * ``1000``      -> ``"$1k"``
      * ``12345``     -> ``"$12.3k"``
      * ``83000``     -> ``"$83k"``
      * ``999999``    -> ``"$999.9k"``
      * ``1000000``   -> ``"$1M"``
      * ``1234567``   -> ``"$1.2M"``

    Truncation is used so a partial value is never rounded up into the
    next bucket (Stage 30 never overstates a magnitude). Caller must
    pass a positive finite ``Decimal`` (validated by
    ``_classify_ath_value``); the helper does not re-check.
    """
    if magnitude < _ONE_THOUSAND:
        truncated_int = magnitude.to_integral_value(rounding=ROUND_DOWN)
        return f"${int(truncated_int)}"
    if magnitude < _ONE_MILLION:
        thousands = magnitude / _ONE_THOUSAND
        truncated_tenth = thousands.quantize(
            Decimal("0.1"), rounding=ROUND_DOWN
        )
        if truncated_tenth == truncated_tenth.to_integral_value():
            int_part = int(
                truncated_tenth.to_integral_value(rounding=ROUND_DOWN)
            )
            return f"${int_part}k"
        return f"${truncated_tenth}k"
    millions = magnitude / _ONE_MILLION
    truncated_tenth = millions.quantize(
        Decimal("0.1"), rounding=ROUND_DOWN
    )
    if truncated_tenth == truncated_tenth.to_integral_value():
        int_part = int(
            truncated_tenth.to_integral_value(rounding=ROUND_DOWN)
        )
        return f"${int_part}M"
    return f"${truncated_tenth}M"


# ---------------------------------------------------------------------------
# Internal: projection builders
# ---------------------------------------------------------------------------


def _unknown(
    *,
    reason: str,
    source_status: str,
    ath_unit: str = ATH_UNIT_UNKNOWN,
    basis: str = ATH_BASIS_NONE,
) -> Stage30_7AthContextProjection:
    """Build a safe ``ATH_UNKNOWN`` projection (compact display
    ``Unknown``, no value echo, not trusted for drawdown / display).
    ``runtime_consumable`` is hard-locked ``False``.
    """
    return Stage30_7AthContextProjection(
        schema_version=STAGE30_7_1_ATH_CONTEXT_SCHEMA_VERSION,
        ath_status=ATH_STATUS_UNKNOWN,
        source_status=source_status,
        ath_unit=ath_unit,
        basis=basis,
        ath_value=None,
        ath_display_text=ATH_DISPLAY_UNKNOWN,
        reason=reason,
        should_display_value=False,
        should_trust_for_drawdown=False,
        projection_version=STAGE30_7_1_ATH_CONTEXT_PROJECTION_VERSION,
        runtime_consumable=False,
    )


def _unverified_price_derived(
    *,
    ath_value_text: str,
) -> Stage30_7AthContextProjection:
    """Build an ``ATH_UNVERIFIED`` projection for a price-derived ATH.

    Provenance only: the value echo is preserved, but the compact
    display is ``Unknown`` (an unverified ATH has no trustworthy value
    to display) and it is NOT trusted for a drawdown / tier anchor. A
    price-derived ATH market cap assumes a supply that may not match the
    supply at the historical peak, so it is never promoted to
    ``ATH_KNOWN`` in this slice.
    """
    return Stage30_7AthContextProjection(
        schema_version=STAGE30_7_1_ATH_CONTEXT_SCHEMA_VERSION,
        ath_status=ATH_STATUS_UNVERIFIED,
        source_status=ATH_SOURCE_STATUS_PRESENT,
        ath_unit=ATH_UNIT_USD,
        basis=ATH_BASIS_PRICE_DERIVED,
        ath_value=ath_value_text,
        ath_display_text=ATH_DISPLAY_UNKNOWN,
        reason=ATH_REASON_UNVERIFIED_PRICE_DERIVED,
        should_display_value=False,
        should_trust_for_drawdown=False,
        projection_version=STAGE30_7_1_ATH_CONTEXT_PROJECTION_VERSION,
        runtime_consumable=False,
    )


def _known_usd_market_cap(
    *,
    ath_value_text: str,
    ath_display_text: str,
) -> Stage30_7AthContextProjection:
    """Build the trusted ``ATH_KNOWN`` projection: a compact ``$Y`` USD
    display from an observed-market-cap basis, trusted for a future
    drawdown / tier anchor.
    """
    return Stage30_7AthContextProjection(
        schema_version=STAGE30_7_1_ATH_CONTEXT_SCHEMA_VERSION,
        ath_status=ATH_STATUS_KNOWN,
        source_status=ATH_SOURCE_STATUS_PRESENT,
        ath_unit=ATH_UNIT_USD,
        basis=ATH_BASIS_MARKET_CAP_OBSERVED,
        ath_value=ath_value_text,
        ath_display_text=ath_display_text,
        reason=ATH_REASON_KNOWN_USD_MARKET_CAP,
        should_display_value=True,
        should_trust_for_drawdown=True,
        projection_version=STAGE30_7_1_ATH_CONTEXT_PROJECTION_VERSION,
        runtime_consumable=False,
    )


# ---------------------------------------------------------------------------
# Internal: the projection logic (may read evidence via getattr)
# ---------------------------------------------------------------------------


def _project(
    evidence: object,
    market_context_unit: object,
) -> Stage30_7AthContextProjection:
    raw_source_status = getattr(evidence, "source_status", None)
    # Default to None (NOT True): malformed duck-typed evidence that
    # omits a redaction proof must NOT be trusted -- a missing
    # redaction_safe fails closed at step 2 below, exactly like an
    # explicit non-True value.
    raw_redaction_safe = getattr(evidence, "redaction_safe", None)
    raw_value = getattr(evidence, "ath_value", None)
    raw_unit = getattr(evidence, "ath_unit", None)
    raw_basis = getattr(evidence, "basis", None)

    # ----- 1. Source dominance ------------------------------------------
    # A non-PRESENT source status dominates any claimed value. An
    # off-closed-set / missing / non-str source status is invalid input.
    if raw_source_status == ATH_SOURCE_STATUS_PRESENT:
        pass
    elif raw_source_status == ATH_SOURCE_STATUS_UNAVAILABLE:
        return _unknown(
            reason=ATH_REASON_UNKNOWN_SOURCE_UNAVAILABLE,
            source_status=ATH_SOURCE_STATUS_UNAVAILABLE,
        )
    elif raw_source_status == ATH_SOURCE_STATUS_ERROR:
        return _unknown(
            reason=ATH_REASON_UNKNOWN_SOURCE_ERROR,
            source_status=ATH_SOURCE_STATUS_ERROR,
        )
    elif raw_source_status == ATH_SOURCE_STATUS_STALE:
        return _unknown(
            reason=ATH_REASON_UNKNOWN_SOURCE_STALE,
            source_status=ATH_SOURCE_STATUS_STALE,
        )
    elif raw_source_status == ATH_SOURCE_STATUS_CONFLICTING:
        return _unknown(
            reason=ATH_REASON_UNKNOWN_SOURCE_CONFLICTING,
            source_status=ATH_SOURCE_STATUS_CONFLICTING,
        )
    else:
        return _unknown(
            reason=ATH_REASON_UNKNOWN_INVALID_INPUT,
            source_status=ATH_SOURCE_STATUS_UNAVAILABLE,
        )

    # Source is PRESENT from here on.
    # ----- 2. Redaction safety ------------------------------------------
    # Anything other than exactly True -- an explicit False / non-bool
    # value OR a missing redaction proof (resolved to None above) --
    # fails closed: a missing redaction proof is never trusted.
    if raw_redaction_safe is not True:
        return _unknown(
            reason=ATH_REASON_UNKNOWN_REDACTION_UNSAFE,
            source_status=ATH_SOURCE_STATUS_PRESENT,
        )

    # ----- 3. Value validity (fail closed) ------------------------------
    value_dec, value_reason = _classify_ath_value(raw_value)
    if value_reason is not None:
        return _unknown(
            reason=value_reason,
            source_status=ATH_SOURCE_STATUS_PRESENT,
        )

    # ----- 4. Unit safety -----------------------------------------------
    # 4a. Unit must be a recognized currency token (USD / SOL), never
    #     UNKNOWN / unrecognized.
    if raw_unit not in (ATH_UNIT_USD, ATH_UNIT_SOL):
        return _unknown(
            reason=ATH_REASON_UNKNOWN_UNIT_UNSUPPORTED,
            source_status=ATH_SOURCE_STATUS_PRESENT,
        )
    # 4b. Unit must share the market-context currency basis (never mix
    #     USD and SOL).
    if raw_unit != market_context_unit:
        return _unknown(
            reason=ATH_REASON_UNKNOWN_UNIT_INCOMPATIBLE,
            source_status=ATH_SOURCE_STATUS_PRESENT,
        )
    # 4c. Unit must be displayable in this slice. USD is the only
    #     displayable basis; a SOL ATH display is deferred to a later
    #     substage.
    if raw_unit != ATH_UNIT_USD:
        return _unknown(
            reason=ATH_REASON_UNKNOWN_UNIT_UNSUPPORTED,
            source_status=ATH_SOURCE_STATUS_PRESENT,
        )

    # raw_unit == USD == market_context_unit; value_dec is a positive
    # finite Decimal.
    value_text = _canonical_decimal_text(value_dec)

    # ----- 5. Basis (honesty axis) --------------------------------------
    if raw_basis == ATH_BASIS_PRICE_DERIVED:
        # Never promoted to ATH_KNOWN: a current-supply price-derived ATH
        # market cap is honesty-limited.
        return _unverified_price_derived(ath_value_text=value_text)
    if raw_basis == ATH_BASIS_MARKET_CAP_OBSERVED:
        return _known_usd_market_cap(
            ath_value_text=value_text,
            ath_display_text=_format_known_usd_compact(value_dec),
        )
    # ATH_BASIS_NONE / off-closed-set basis: a positive USD value with no
    # supporting observed / price-derived basis is internally
    # inconsistent => invalid input => Unknown.
    return _unknown(
        reason=ATH_REASON_UNKNOWN_INVALID_INPUT,
        source_status=ATH_SOURCE_STATUS_PRESENT,
    )


# ---------------------------------------------------------------------------
# Public: project_ath_context
# ---------------------------------------------------------------------------


def project_ath_context(
    evidence: object,
    market_context_unit: str = STAGE30_7_1_DEFAULT_MARKET_CONTEXT_UNIT,
) -> Stage30_7AthContextProjection:
    """Project caller-supplied sanitized ATH evidence into a Stage-30-
    owned compact ATH-context projection.

    Pure / deterministic / total. NEVER reads the process environment,
    NEVER touches the filesystem or network, NEVER calls a provider,
    NEVER calls ``datetime.now``, NEVER recomputes a drawdown / tier,
    and NEVER routes into runtime. NEVER raises for bad evidence: any
    invalid / missing / untrusted / unit-incompatible / redaction-unsafe
    / off-closed-set input fails closed to an ``ATH_UNKNOWN`` projection
    whose compact display is the literal ``Unknown`` (it NEVER fabricates
    a peak). ``runtime_consumable`` is hard-locked ``False`` on every
    projection.

    ``market_context_unit`` is the currency basis of the displayed
    ``MC`` (default ``USD``). The displayed ATH must share that basis; a
    ``SOL`` evidence unit against a ``USD`` market context (or vice
    versa) degrades to ``Unknown`` rather than silently mixing units.

    Identical inputs always produce a byte-identical projection record
    (``dataclass`` equality and the display string are both fully
    derived from the input).
    """
    try:
        return _project(evidence, market_context_unit)
    except Exception:  # noqa: BLE001 - any failure => Unknown (fail closed)
        return _unknown(
            reason=ATH_REASON_UNKNOWN_INVALID_INPUT,
            source_status=ATH_SOURCE_STATUS_UNAVAILABLE,
        )


__all__ = (
    "project_ath_context",
)

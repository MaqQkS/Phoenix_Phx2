"""Stage 30.2 compact private ping renderer.

Pure projector that turns a Stage 30.2 ``CompactPingInputRecord``
into a Stage 30.2 ``CompactPingSnapshotRecord``. The snapshot
carries the rendered compact body string plus every operator-visible
display field plus the warning lines plus the safe-shape opaque
identifier echoes. The renderer NEVER fetches MC / LP / volume,
NEVER opens a network connection, NEVER reads the process
environment, NEVER calls ``datetime.now`` (the clock is caller-
supplied), NEVER mutates its inputs, NEVER recomputes tier bands
(it echoes ``tier_decision.tier_token`` / ``tier_decision.tier_reason``
verbatim), NEVER fabricates MC / LP / volume / supply (missing
fields render as the literal ``DISPLAY_UNKNOWN``).

Rendered body shape (no warnings case):

    🔥 PHOENIX — <symbol-or-mint-short> [<tier_token>]
    <full-mint-or-Unknown>

    🧠 State
    • MC: <X> | ATH: <X> | Mig: <X>
    • Drop: <X> | Age: <X> | Net: <X>
    • LP: <X>
    • Basis: <basis-token>

Rendered body shape (with warnings, at most two):

    🔥 PHOENIX — <symbol-or-mint-short> [<tier_token>]
    <full-mint-or-Unknown>

    🧠 State
    • MC: <X> | ATH: <X> | Mig: <X>
    • Drop: <X> | Age: <X> | Net: <X>
    • LP: <X>
    • Basis: <basis-token>

    ⚠ Notes
    • <warning-line>
    • <warning-line>

The ``Drop`` label denotes the CURRENT drawdown from ATH at ping
time (derived from ``TierDecisionRecord.drop_positive``). It is
NOT a historical floor / minimum-drawdown tracker; PHX2 does not
yet track an observed floor, and using the ``Floor`` label would
mis-promise that.

The ``Net`` label denotes operator-readable net buy / sell flow.
Until a net-flow source ships, callers pass ``None`` and the
renderer emits ``Unknown``. The renderer NEVER renders ``0`` /
``0.0`` / empty string / a fabricated estimate for missing
fields.

Caller-shape failures (non-``CompactPingInputRecord`` input, non-
``TierDecisionRecord`` ``tier_decision``, unsafe-shape
``created_at_utc``, negative or wrong-type
``age_since_migration_seconds``, display text carrying a forbidden
trading-verdict / URL / auth / secret substring) raise
``Stage30_2CompactPingError`` with a closed-set reason token.
Degraded inputs (missing mint, unsafe-shape mint, missing symbol,
unsafe-shape symbol, missing display text, missing age) do NOT
raise; they fall back to ``DISPLAY_UNKNOWN`` (or the mint-short
fallback for the symbol slot).

Discipline:

  * Stdlib only (``re`` / ``decimal`` / ``typing``).
  * Stage 30.1 ``TierDecisionRecord`` imported read-only via the
    Stage 30.1 models module (NOT the projector). The renderer does
    not import the Stage 30.1 band constants.
  * Stage 30.2 sibling module ``compact_ping_models`` imported.
  * No ``os.environ`` / ``os.getenv`` / ``os.environb`` access.
  * No network, no HTTP, no gRPC, no WebSocket, no socket.
  * No Discord, Telegram, X / social, webhook, Helius, Chainstack,
    Birdeye, Dexscreener, Pump.fun reference.
  * No PHX1 import. No legacy phoenix-1 import path.
  * No Stage 21-29 production-source modification.
"""

from __future__ import annotations

import re
from decimal import (
    Decimal,
    InvalidOperation,
    ROUND_DOWN,
    ROUND_HALF_EVEN,
)
from typing import Optional, Tuple

from PHX2.stage30.compact_ping_models import (
    CompactPingInputRecord,
    CompactPingSnapshotRecord,
    DISPLAY_UNKNOWN,
    STAGE30_2_BODY_CHAR_HARD_CAP,
    STAGE30_2_COMPACT_PING_SCHEMA_VERSION,
    Stage30_2CompactPingError,
)
from PHX2.stage30.tier_decision_models import TierDecisionRecord


# ---------------------------------------------------------------------------
# Forbidden display-text / body substrings
# ---------------------------------------------------------------------------
#
# Concatenated literals so this module's own source does NOT carry the
# canonical trading-verdict / URL / webhook / API-key substrings
# (mirrors the Stage 30.1 artifact writer pattern). The renderer
# scans every caller-supplied display text field BEFORE rendering and
# raises ``Stage30_2CompactPingError(DISPLAY_TEXT_FORBIDDEN_SUBSTRING)``
# on any match. The needles below are already lowercased; the scan
# lowercases the input.
#
# Per the Stage 30 spec lock §4: ``SAFE`` is intentionally NOT in
# the trading-verdict needle set. Stage 30 artifacts and the
# Stage 30 redaction scan use ``SAFE`` as a closed-set status
# token, and Stage 30.2 must not collide with that usage. A
# compound trading-verdict phrase such as ``SAFE BUY`` is still
# rejected because ``BUY`` remains in the needle set; the
# ``SAFE`` carve-out applies only when ``SAFE`` appears WITHOUT a
# paired forbidden trading-verdict substring.


_FORBIDDEN_TRADING_VERDICT_NEEDLES_LOWER: Tuple[str, ...] = (
    "b" + "uy",
    "s" + "ell",
    "a" + "pproved",
    "g" + "ate",
    "b" + "lock",
    "e" + "nforcement",
    "e" + "xecute",
    "p" + "osition",
    "a" + "uto-trade",
)


_FORBIDDEN_URL_AUTH_NEEDLES_LOWER: Tuple[str, ...] = (
    "h" + "ttp://",
    "h" + "ttps://",
    "w" + "s://",
    "w" + "ss://",
    "discord" + ".com",
    "discord" + "app.com",
    "/webhooks/",
    "b" + "earer ",
    "a" + "uthorization:",
    "s" + "k-",
    "p" + "k-",
)


def _contains_forbidden_substring(value: str) -> bool:
    """Return ``True`` iff ``value`` carries a forbidden trading-
    verdict or URL / auth / secret substring (case-insensitive).
    """
    lower = value.lower()
    for needle in _FORBIDDEN_TRADING_VERDICT_NEEDLES_LOWER:
        if needle in lower:
            return True
    for needle in _FORBIDDEN_URL_AUTH_NEEDLES_LOWER:
        if needle in lower:
            return True
    return False


# ---------------------------------------------------------------------------
# Safe-shape regexes + alphabets
# ---------------------------------------------------------------------------
#
# Reproduced (not imported) from the Stage 30.1 projector's shape
# helpers so this renderer does NOT depend on the Stage 30.1
# projector.


_SAFE_ISO8601_UTC_PATTERN: "re.Pattern[str]" = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$"
)


_STRICT_DECIMAL_TEXT_PATTERN: "re.Pattern[str]" = re.compile(
    r"^-?\d+(\.\d+)?$"
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
_SAFE_IDENTIFIER_ALPHABET: frozenset = frozenset(
    "abcdefghijklmnopqrstuvwxyz"
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    "0123456789_-."
)


_MIN_SAFE_IDENTIFIER_LENGTH: int = 1
_MAX_SAFE_IDENTIFIER_LENGTH: int = 64


# Symbol alphabet: same allowlist as identifiers but length [1, 16]
# so a symbol can never be confused with a long opaque id.
_SAFE_SYMBOL_ALPHABET: frozenset = _SAFE_IDENTIFIER_ALPHABET


_MIN_SAFE_SYMBOL_LENGTH: int = 1
_MAX_SAFE_SYMBOL_LENGTH: int = 16


# ---------------------------------------------------------------------------
# Safe-shape helpers
# ---------------------------------------------------------------------------


def _is_safe_iso8601_utc_text(value: object) -> bool:
    if not isinstance(value, str):
        return False
    return _SAFE_ISO8601_UTC_PATTERN.fullmatch(value) is not None


def _sanitize_mint(value: object) -> Optional[str]:
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


def _sanitize_identifier(value: object) -> Optional[str]:
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


def _sanitize_symbol(value: object) -> Optional[str]:
    if not isinstance(value, str):
        return None
    n = len(value)
    if n < _MIN_SAFE_SYMBOL_LENGTH:
        return None
    if n > _MAX_SAFE_SYMBOL_LENGTH:
        return None
    for ch in value:
        if ch not in _SAFE_SYMBOL_ALPHABET:
            return None
    return value


# ---------------------------------------------------------------------------
# Display projectors (text / age / floor)
# ---------------------------------------------------------------------------


def _resolve_text_display(value: Optional[str]) -> str:
    """Return ``value`` if it is a non-empty string, else
    ``DISPLAY_UNKNOWN``.

    NEVER returns ``"0"`` / ``"0.0"`` / empty string / a fabricated
    estimate.
    """
    if not isinstance(value, str):
        return DISPLAY_UNKNOWN
    if value == "":
        return DISPLAY_UNKNOWN
    return value


def _shorten_mint(mint: str) -> str:
    """Return ``mint[:4] + "…" + mint[-4:]``.

    Caller must pass a mint that has already passed
    ``_sanitize_mint`` (length [32, 64], base58 alphabet).
    """
    return mint[:4] + "…" + mint[-4:]


def _format_age_seconds(seconds: Optional[int]) -> str:
    """Return the operator-readable age display string.

      * ``None``                       -> ``DISPLAY_UNKNOWN``
      * ``< 60``                       -> ``"<n>s"`` (integer seconds)
      * ``< 3600``                     -> ``"<n>m"`` (integer minutes,
                                          floor-divided)
      * ``< 172800`` (< 48h)           -> ``"<x.y>h"`` (one decimal,
                                          ``ROUND_HALF_EVEN``)
      * ``>= 172800``                  -> ``"<x.y>d"`` (one decimal,
                                          ``ROUND_HALF_EVEN``)

    Caller-shape validation in ``render_compact_ping`` rejects
    negative / non-int input before this helper is called; the
    helper does not re-check.
    """
    if seconds is None:
        return DISPLAY_UNKNOWN
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        minutes = seconds // 60
        return f"{minutes}m"
    if seconds < 172800:
        hours = (
            Decimal(seconds) / Decimal(3600)
        ).quantize(Decimal("0.1"), rounding=ROUND_HALF_EVEN)
        return f"{hours}h"
    days = (
        Decimal(seconds) / Decimal(86400)
    ).quantize(Decimal("0.1"), rounding=ROUND_HALF_EVEN)
    return f"{days}d"


def _format_drop_percent(drop_positive_text: Optional[str]) -> str:
    """Return the operator-readable drop (drawdown from ATH) display
    string.

    Maps the Stage 30.1 ``drop_positive`` canonical decimal text to
    a signed integer percent string (e.g. ``"0.82"`` -> ``"-82%"``)
    using ``ROUND_DOWN`` semantics: ``"0.555"`` -> ``"-55%"`` (no
    rounding up). When the value is missing, malformed, or non-
    finite, returns ``DISPLAY_UNKNOWN``.

    The visible body label is ``Drop`` (NOT ``Floor``).
    """
    if drop_positive_text is None:
        return DISPLAY_UNKNOWN
    if not isinstance(drop_positive_text, str):
        return DISPLAY_UNKNOWN
    if _STRICT_DECIMAL_TEXT_PATTERN.fullmatch(
        drop_positive_text
    ) is None:
        return DISPLAY_UNKNOWN
    try:
        drop = Decimal(drop_positive_text)
    except (InvalidOperation, ValueError, ArithmeticError, TypeError):
        return DISPLAY_UNKNOWN
    if not drop.is_finite():
        return DISPLAY_UNKNOWN
    drop = abs(drop)
    pct_value = (drop * Decimal(100)).to_integral_value(
        rounding=ROUND_DOWN
    )
    return f"-{int(pct_value)}%"


# ---------------------------------------------------------------------------
# Warning emission (tier_reason + price_status -> closed-set lines)
# ---------------------------------------------------------------------------
#
# Each tier_reason maps to at most one short warning line. The
# three in-band reasons (TIER_1_IN_BAND / TIER_2_IN_BAND /
# TIER_3_IN_BAND) map to ``None`` -- no warning. Each price_status
# value maps to at most one short warning line. ``PRESENT`` /
# ``UNSUPPORTED_PAIR`` / ``None`` / unknown value map to ``None``.


_TIER_REASON_TO_WARNING: dict = {
    "UNKNOWN_DRAWDOWN_MISSING": (
        "Tier Unknown: drawdown missing"
    ),
    "UNKNOWN_DRAWDOWN_MALFORMED": (
        "Tier Unknown: drawdown malformed"
    ),
    "UNKNOWN_BELOW_TIER_1": (
        "Tier Unknown: below tier 1"
    ),
    "UNKNOWN_IN_GAP_T1_T2": (
        "Tier Unknown: in gap (T1-T2)"
    ),
    "UNKNOWN_IN_GAP_T2_T3": (
        "Tier Unknown: in gap (T2-T3)"
    ),
    "UNKNOWN_GRAVEYARD": (
        "Tier Unknown: graveyard (drop > 0.95)"
    ),
    "UNKNOWN_ATH_NOT_PRESENT": (
        "Tier Unknown: ATH not present"
    ),
    "NA_MIGRATION_MISSING": (
        "Tier Not Applicable: migration missing"
    ),
    "NA_MIGRATION_UNTRUSTED": (
        "Tier Not Applicable: migration untrusted"
    ),
    "NA_MIGRATION_UNSUPPORTED_PAIR": (
        "Tier Not Applicable: unsupported pair"
    ),
    "NA_MIGRATION_SOURCE_ERROR": (
        "Tier Not Applicable: migration source error"
    ),
    "NA_ATH_MAY_INCLUDE_PRE_MIGRATION": (
        "Tier Not Applicable: ATH may include pre-migration"
    ),
    "TIER_1_IN_BAND": None,
    "TIER_2_IN_BAND": None,
    "TIER_3_IN_BAND": None,
}


_PRICE_STATUS_TO_WARNING: dict = {
    "STALE": "Price degraded: stale",
    "SOURCE_ERROR": "Price degraded: source error",
    "UNAVAILABLE": "Price degraded: unavailable",
    "PRESENT": None,
    "UNSUPPORTED_PAIR": None,
}


def _build_warnings(
    tier_reason: str,
    price_status: Optional[str],
) -> Tuple[str, ...]:
    """Return the ordered tuple of warning lines (0..2).

    Order: tier_reason warning (at most one), then price_status
    warning (at most one). Unknown tier_reason / price_status
    values silently produce no warning (defense in depth: the
    renderer never emits a warning for a value it does not
    recognise).
    """
    lines: list = []
    tier_warning = _TIER_REASON_TO_WARNING.get(tier_reason)
    if isinstance(tier_warning, str):
        lines.append(tier_warning)
    if isinstance(price_status, str):
        price_warning = _PRICE_STATUS_TO_WARNING.get(price_status)
        if isinstance(price_warning, str):
            lines.append(price_warning)
    return tuple(lines)


# ---------------------------------------------------------------------------
# Body assembly
# ---------------------------------------------------------------------------


def _build_body_text(
    *,
    symbol_display: str,
    tier_token: str,
    mint_display: str,
    current_mc_display: str,
    ath_mc_display: str,
    migration_mc_display: str,
    drop_percent_display: str,
    age_display: str,
    net_flow_display: str,
    lp_display: str,
    basis: str,
    warnings: Tuple[str, ...],
) -> str:
    lines: list = [
        f"\U0001f525 PHOENIX — {symbol_display} [{tier_token}]",
        mint_display,
        "",
        "\U0001f9e0 State",
        (
            f"• MC: {current_mc_display} | "
            f"ATH: {ath_mc_display} | "
            f"Mig: {migration_mc_display}"
        ),
        (
            f"• Drop: {drop_percent_display} | "
            f"Age: {age_display} | "
            f"Net: {net_flow_display}"
        ),
        f"• LP: {lp_display}",
        f"• Basis: {basis}",
    ]
    if warnings:
        lines.append("")
        lines.append("⚠ Notes")
        for warning in warnings:
            lines.append(f"• {warning}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Public renderer
# ---------------------------------------------------------------------------


def render_compact_ping(
    input_record: CompactPingInputRecord,
) -> CompactPingSnapshotRecord:
    """Render a Stage 30.2 compact private ping snapshot.

    Pure / deterministic. Identical inputs always produce a
    byte-identical snapshot record (``NamedTuple`` equality and the
    string body are both fully derived from the input).

    Raises ``Stage30_2CompactPingError`` on caller-shape failures
    (non-``CompactPingInputRecord`` input, non-``TierDecisionRecord``
    ``tier_decision``, unsafe-shape ``created_at_utc``, negative
    or wrong-type ``age_since_migration_seconds``, display text
    carrying a forbidden trading-verdict / URL / auth / secret
    substring). Degraded inputs (missing mint, unsafe-shape mint,
    missing symbol, unsafe-shape symbol, missing display text,
    missing age) do NOT raise; they fall back to ``DISPLAY_UNKNOWN``.
    """
    # ---- Caller-shape validation ----
    if not isinstance(input_record, CompactPingInputRecord):
        raise Stage30_2CompactPingError("INPUT_INVALID_TYPE")
    if not isinstance(
        input_record.tier_decision, TierDecisionRecord
    ):
        raise Stage30_2CompactPingError(
            "TIER_DECISION_INVALID_TYPE"
        )
    if not _is_safe_iso8601_utc_text(
        input_record.created_at_utc
    ):
        raise Stage30_2CompactPingError(
            "CREATED_AT_UTC_NOT_SAFE_ISO8601"
        )
    age_value = input_record.age_since_migration_seconds
    if age_value is not None:
        if isinstance(age_value, bool):
            raise Stage30_2CompactPingError(
                "AGE_SECONDS_INVALID_TYPE"
            )
        if not isinstance(age_value, int):
            raise Stage30_2CompactPingError(
                "AGE_SECONDS_INVALID_TYPE"
            )
        if age_value < 0:
            raise Stage30_2CompactPingError(
                "AGE_SECONDS_NEGATIVE"
            )

    # ---- Display-text forbidden-substring scan ----
    # Symbol and the five MC / ATH / Mig / LP / Net display fields
    # all flow through verbatim to the body when shape-safe and
    # non-empty. The scan rejects any caller-supplied text carrying
    # a forbidden trading-verdict / URL / auth / secret substring
    # (case-insensitive). Non-string / ``None`` inputs are skipped
    # (they render as ``DISPLAY_UNKNOWN``).
    for candidate in (
        input_record.symbol,
        input_record.current_mc_text,
        input_record.ath_mc_text,
        input_record.migration_mc_text,
        input_record.lp_text,
        input_record.net_flow_text,
    ):
        if isinstance(candidate, str) and candidate != "":
            if _contains_forbidden_substring(candidate):
                raise Stage30_2CompactPingError(
                    "DISPLAY_TEXT_FORBIDDEN_SUBSTRING"
                )

    # ---- Sanitize optional identifiers and labels ----
    safe_session_id = _sanitize_identifier(
        input_record.session_id
    )
    safe_ping_id = _sanitize_identifier(input_record.ping_id)
    safe_candidate_id = _sanitize_identifier(
        input_record.candidate_id
    )
    safe_mint = _sanitize_mint(input_record.mint)
    safe_symbol = _sanitize_symbol(input_record.symbol)

    # ---- Resolve display strings ----
    mint_display = (
        safe_mint if safe_mint is not None else DISPLAY_UNKNOWN
    )
    if safe_symbol is not None:
        symbol_display = safe_symbol
    elif safe_mint is not None:
        symbol_display = _shorten_mint(safe_mint)
    else:
        symbol_display = DISPLAY_UNKNOWN

    current_mc_display = _resolve_text_display(
        input_record.current_mc_text
    )
    ath_mc_display = _resolve_text_display(
        input_record.ath_mc_text
    )
    migration_mc_display = _resolve_text_display(
        input_record.migration_mc_text
    )
    lp_display = _resolve_text_display(input_record.lp_text)
    net_flow_display = _resolve_text_display(
        input_record.net_flow_text
    )
    age_display = _format_age_seconds(
        input_record.age_since_migration_seconds
    )
    drop_percent_display = _format_drop_percent(
        input_record.tier_decision.drop_positive
    )

    # ---- Resolve warning lines (0..2) ----
    warnings = _build_warnings(
        input_record.tier_decision.tier_reason,
        input_record.price_status,
    )

    # ---- Assemble body ----
    body_text = _build_body_text(
        symbol_display=symbol_display,
        tier_token=input_record.tier_decision.tier_token,
        mint_display=mint_display,
        current_mc_display=current_mc_display,
        ath_mc_display=ath_mc_display,
        migration_mc_display=migration_mc_display,
        drop_percent_display=drop_percent_display,
        age_display=age_display,
        net_flow_display=net_flow_display,
        lp_display=lp_display,
        basis=input_record.tier_decision.basis,
        warnings=warnings,
    )

    body_length = len(body_text)
    if body_length > STAGE30_2_BODY_CHAR_HARD_CAP:
        raise Stage30_2CompactPingError(
            "BODY_EXCEEDS_HARD_CAP"
        )

    # ---- Assemble snapshot ----
    return CompactPingSnapshotRecord(
        schema_version=STAGE30_2_COMPACT_PING_SCHEMA_VERSION,
        session_id=safe_session_id,
        ping_id=safe_ping_id,
        candidate_id=safe_candidate_id,
        mint=safe_mint,
        symbol=safe_symbol,
        tier_token=input_record.tier_decision.tier_token,
        tier_reason=input_record.tier_decision.tier_reason,
        basis=input_record.tier_decision.basis,
        drawdown_from_ath_raw=(
            input_record.tier_decision.drawdown_from_ath_raw
        ),
        drop_positive=input_record.tier_decision.drop_positive,
        ath_status=input_record.tier_decision.ath_status,
        ath_since_migration_status=(
            input_record.tier_decision.ath_since_migration_status
        ),
        migration_status=(
            input_record.tier_decision.migration_status
        ),
        price_status=input_record.price_status,
        current_mc_display=current_mc_display,
        ath_mc_display=ath_mc_display,
        migration_mc_display=migration_mc_display,
        drop_percent_display=drop_percent_display,
        age_display=age_display,
        lp_display=lp_display,
        net_flow_display=net_flow_display,
        warnings=warnings,
        body_text=body_text,
        body_length_chars=body_length,
        created_at_utc=input_record.created_at_utc,
    )


__all__ = (
    "render_compact_ping",
)

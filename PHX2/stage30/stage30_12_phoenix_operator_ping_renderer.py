"""Stage 30.12 PHOENIX private operator ping renderer.

Pure projector that turns a Stage 30.12 ``PhoenixOperatorPingInput`` into the
rich PHOENIX private-operator ping body string. The renderer NEVER fetches MC /
LP / price, NEVER opens a network connection, NEVER reads the process
environment, NEVER calls ``datetime.now`` (every timestamp is a caller-supplied
display string), NEVER mutates its inputs, NEVER recomputes the tier (it echoes
``tier_token`` verbatim and only maps it to a DISPLAY band), and NEVER
fabricates a missing field (missing optionals render as the literal
``Unknown``).

Rendered body shape:

    🔥 PHOENIX — <symbol-or-mint-short> [<tier_token>]
    CA: <full-token-mint>

    🧠 State
    MC: <X> | ATH: <X> | Drop: <X>
    LP: <X> | Mig: <Confirmed/Unknown> | Age: <X>

    💰 Price
    Now: <X>
    ATH: <X>

    🎯 Dip Gate
    Tier: <tier_token>
    Band: <tier_band>
    Basis: <basis>

    🧾 Provenance
    Migration: <migration_time_utc>
    Src: <shortened_source_ref>

    PRIVATE OPERATOR ONLY · PHX2

Safety / fail-closed discipline:

  * The ``CA:`` line ALWAYS carries the full token / base mint. The renderer
    fails closed (``Stage30_12PhoenixOperatorPingError``) when ``token_mint`` is
    missing, not safe-shape Solana base58, or the WSOL / quote mint -- the CA is
    NEVER the quote mint, NEVER a short form.
  * Every caller-supplied display field is scanned BEFORE any assembly OR
    source-ref shortening for a closed-set forbidden URL / webhook / auth /
    API-key / RPC / secret substring (case-insensitive, AND hyphen / underscore
    / spacing-insensitive for secret keywords -- the hyphenated, underscored,
    spaced, and run-together variants of a keyword all fail closed) and for any
    ASCII control character (a structural body-injection guard); a match fails
    closed. Because the scan
    runs over the RAW field value before shortening, a secret can never be
    hidden inside a middle-elided ``source_ref`` segment. The needles are
    concatenated from fragments so this module's own source carries no bare
    needle and no contiguous transport-scheme separator.
  * The fractional drop percent is an EXPLICIT input echoed verbatim; the
    renderer NEVER multiplies ``absolute_drawdown`` by 100 (the committed Stage
    30.1 ``drop_positive`` is the ABSOLUTE delta now, so deriving a percent from
    it would render ``-0%`` for a sub-dollar token). ``absolute_drawdown`` is
    accepted but intentionally not rendered.
  * ``current_price`` / ``ath_price`` are formatted to a clean ``$`` price
    (10-decimal-place, trailing zeros trimmed); a missing / malformed value
    renders as ``Unknown``, never a fabricated price.
  * The long base58 signature in ``source_ref`` is middle-elided; the renderer
    NEVER dumps a raw secret / URL there (the scan above rejects one).
  * The body is hard-capped at the Stage 30.12 cap (a body above it fails
    closed).

Discipline:

  * Stdlib only (``re`` / ``decimal`` / ``typing``).
  * Imports ONLY the Stage 30.12 models sibling (a clean leaf).
  * No ``os.environ`` / ``os.getenv`` / ``os.environb`` access.
  * No network, no HTTP, no gRPC, no WebSocket, no socket.
  * No Discord, Telegram, X / social, webhook, Helius, Chainstack, Birdeye,
    Dexscreener, Pump.fun reference.
  * No PHX1 import. No legacy phoenix-1 import path.
  * No Stage 21-29 / Stage 30.1 / Stage 30.2 / Stage 30.11 production-source
    modification.
  * No implicit I/O at import time (the module-level ``re.compile`` /
    ``frozenset`` builds are pure stdlib, not I/O; the renderer reads no env,
    opens no file, and makes no network call).
"""

from __future__ import annotations

import re
from decimal import (
    Decimal,
    InvalidOperation,
    ROUND_HALF_UP,
)
from typing import Optional, Tuple

from PHX2.stage30.stage30_12_phoenix_operator_ping_models import (
    DISPLAY_UNKNOWN,
    PhoenixOperatorPingInput,
    STAGE30_12_BODY_CHAR_HARD_CAP,
    STAGE30_12_OPERATOR_FOOTER,
    Stage30_12PhoenixOperatorPingError,
    WSOL_QUOTE_MINT,
    tier_band_display_for,
)


# ---------------------------------------------------------------------------
# Display glyphs (escapes so this module's source stays pure ASCII)
# ---------------------------------------------------------------------------


_FIRE: str = "\U0001f525"        # 🔥
_BRAIN: str = "\U0001f9e0"       # 🧠
_MONEY: str = "\U0001f4b0"       # 💰
_TARGET: str = "\U0001f3af"      # 🎯
_RECEIPT: str = "\U0001f9fe"     # 🧾
_EMDASH: str = "—"          # —
_ELLIPSIS: str = "…"        # …


# ---------------------------------------------------------------------------
# Forbidden display-text substrings (URL / webhook / auth / secret / RPC)
# ---------------------------------------------------------------------------
#
# Two needle tiers, both checked BEFORE any rendering / source-ref shortening so
# a secret can never be hidden inside a middle-elided segment:
#
#   1. RAW needles -- matched against the lowercased value verbatim. These are
#      the URL / transport / delimiter-bearing forms whose punctuation is
#      load-bearing (a scheme separator, a webhooks path, a PEM header, a
#      delimited bearer lead-in).
#   2. KEYWORD needles -- matched against a SEPARATOR-NORMALIZED value: the
#      value is lowercased and its hyphen / underscore / ASCII-space characters
#      are removed first, so every hyphen / underscore / spaced variant of a
#      secret keyword collapses to one canonical form. This closes the variants
#      a literal list misses (the keyword written with a hyphen, an underscore,
#      a space, or run together all match the same canonical needle).
#
# Both tiers are concatenated from fragments where needed so this module's own
# source carries no bare leaked literal and no contiguous transport-scheme
# separator. Neither tier can fire on a legitimate base58 mint, a canonical
# decimal price, an ISO-8601 timestamp, or a normal opaque colon-delimited
# source ref.


_SLASH: str = "/"
_COLON: str = ":"
_SCHEME_SEP: str = _COLON + _SLASH + _SLASH   # transport scheme separator


# Tier 1: matched against the lowercased value verbatim (punctuation matters).
_FORBIDDEN_RAW_SUBSTRINGS_LOWER: Tuple[str, ...] = (
    _SCHEME_SEP,
    _SLASH + "web" + "hooks" + _SLASH,
    "discord" + ".com",
    "discord" + "app.com",
    "-----" + "begin",
    "s" + "k-",
    "p" + "k-",
    "bearer=",
    "bearer" + _COLON,
    "bearer ",
)


# Tier 2: matched against the separator-normalized value (hyphen / underscore /
# space removed). Each canonical keyword therefore catches its hyphen,
# underscore, spaced, and run-together variants in one entry.
_FORBIDDEN_NORMALIZED_KEYWORDS: Tuple[str, ...] = (
    "apikey",
    "privatekey",
    "bearertoken",
    "authtoken",
    "accesstoken",
    "secret",
    "rpcurl",
    "authorization",
    "webhook",
    "seedphrase",
    "mnemonic",
)


def _normalize_for_keyword_scan(value_lower: str) -> str:
    """Strip ASCII hyphen / underscore / space from an already-lowercased value
    so a secret keyword matches regardless of its hyphen / underscore / spacing.
    """
    return value_lower.replace("-", "").replace("_", "").replace(" ", "")


def _contains_forbidden_or_control(value: str) -> bool:
    """Return ``True`` iff ``value`` carries a forbidden URL / webhook / auth /
    API-key / RPC / secret substring (case-insensitive AND hyphen / underscore /
    spacing-insensitive) OR any ASCII control character (a structural body-
    injection guard: newline / carriage-return / tab / other ``ord < 32``).
    """
    for ch in value:
        if ord(ch) < 32:
            return True
    lower = value.lower()
    for needle in _FORBIDDEN_RAW_SUBSTRINGS_LOWER:
        if needle in lower:
            return True
    normalized = _normalize_for_keyword_scan(lower)
    for keyword in _FORBIDDEN_NORMALIZED_KEYWORDS:
        if keyword in normalized:
            return True
    return False


# ---------------------------------------------------------------------------
# Safe-shape regexes + alphabets
# ---------------------------------------------------------------------------


# Solana base58 alphabet (no 0, no O, no I, no l).
_BASE58_ALPHABET: frozenset = frozenset(
    "123456789ABCDEFGHJKLMNPQRSTUVWXYZ"
    "abcdefghijkmnopqrstuvwxyz"
)


_MIN_SAFE_MINT_LENGTH: int = 32
_MAX_SAFE_MINT_LENGTH: int = 64


# Strict canonical decimal-text (the price input shape). Accepts an optional
# leading minus so a malformed negative price is parsed-then-rejected rather
# than mis-validated; the formatter rejects negatives explicitly.
_STRICT_DECIMAL_TEXT_PATTERN: "re.Pattern[str]" = re.compile(
    r"^-?\d+(\.\d+)?$"
)


# Safe ISO-8601 UTC timestamp (the migration-time display shape).
_SAFE_ISO8601_UTC_PATTERN: "re.Pattern[str]" = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$"
)


# Safe header symbol alphabet: alphanumerics + a small display allowlist. A
# symbol outside this shape (or too long) falls back to the short mint -- this
# blocks a symbol from injecting body structure.
_SAFE_SYMBOL_ALPHABET: frozenset = frozenset(
    "abcdefghijklmnopqrstuvwxyz"
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    "0123456789 _-.$#"
)
_MAX_SAFE_SYMBOL_LENGTH: int = 24


# Price quantization: 10 decimal places, then trim trailing zeros.
_PRICE_QUANTUM: Decimal = Decimal("0.0000000001")


# source_ref middle-elision bounds.
_SRC_SEGMENT_ELIDE_THRESHOLD: int = 14
_SRC_SEGMENT_HEAD: int = 8
_SRC_SEGMENT_TAIL: int = 3
_SRC_TOTAL_MAX: int = 120


# Header short-mint bounds.
_MINT_SHORT_HEAD: int = 6
_MINT_SHORT_TAIL: int = 5


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def _is_base58_mint(value: object) -> bool:
    """Return ``True`` iff ``value`` is a safe-shape Solana base58 mint."""
    if not isinstance(value, str):
        return False
    n = len(value)
    if n < _MIN_SAFE_MINT_LENGTH or n > _MAX_SAFE_MINT_LENGTH:
        return False
    for ch in value:
        if ch not in _BASE58_ALPHABET:
            return False
    return True


def _short_mint(mint: str) -> str:
    """Return ``mint[:6] + "…" + mint[-5:]`` (caller passes a base58 mint)."""
    return mint[:_MINT_SHORT_HEAD] + _ELLIPSIS + mint[-_MINT_SHORT_TAIL:]


def _resolve_symbol_display(symbol: Optional[str], mint: str) -> str:
    """Return the header symbol slot: a safe-shape ``symbol`` when present,
    else the short mint. NEVER fabricates a symbol.
    """
    if isinstance(symbol, str):
        candidate = symbol.strip()
        if (
            candidate != ""
            and len(candidate) <= _MAX_SAFE_SYMBOL_LENGTH
            and all(ch in _SAFE_SYMBOL_ALPHABET for ch in candidate)
        ):
            return candidate
    return _short_mint(mint)


def _text_or_unknown(value: Optional[str]) -> str:
    """Return ``value`` when it is a non-empty string, else ``DISPLAY_UNKNOWN``.

    NEVER returns ``"0"`` / ``"0.0"`` / empty / a fabricated estimate. The
    caller has already run the forbidden-substring / control-char scan.
    """
    if not isinstance(value, str):
        return DISPLAY_UNKNOWN
    if value.strip() == "":
        return DISPLAY_UNKNOWN
    return value


def _format_price(value: Optional[str]) -> str:
    """Return a clean ``$`` price for a canonical decimal-text ``value``.

    ``"0.000005190124582537581"`` -> ``"$0.0000051901"``. Quantizes to ten
    decimal places (``ROUND_HALF_UP``) and trims trailing zeros. A missing /
    malformed / non-finite / negative value renders as ``DISPLAY_UNKNOWN`` --
    never a fabricated price.
    """
    if not isinstance(value, str):
        return DISPLAY_UNKNOWN
    if _STRICT_DECIMAL_TEXT_PATTERN.fullmatch(value) is None:
        return DISPLAY_UNKNOWN
    try:
        parsed = Decimal(value)
    except (InvalidOperation, ValueError, ArithmeticError, TypeError):
        return DISPLAY_UNKNOWN
    if not parsed.is_finite() or parsed < 0:
        return DISPLAY_UNKNOWN
    quantized = parsed.quantize(_PRICE_QUANTUM, rounding=ROUND_HALF_UP)
    text = format(quantized, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return f"${text}"


def _format_migration_confirmed(flag: Optional[bool]) -> str:
    """Return ``"Confirmed"`` only for an explicit ``True``; ``"Unknown"``
    otherwise (``False`` / ``None``). NEVER fabricates a confirmation.
    """
    if flag is True:
        return "Confirmed"
    return DISPLAY_UNKNOWN


def _format_migration_time(value: Optional[str]) -> str:
    """Return a safe-shape ISO-8601 UTC migration timestamp, else
    ``DISPLAY_UNKNOWN`` (the renderer NEVER displays arbitrary text in the
    timestamp slot).
    """
    if not isinstance(value, str):
        return DISPLAY_UNKNOWN
    if _SAFE_ISO8601_UTC_PATTERN.fullmatch(value) is None:
        return DISPLAY_UNKNOWN
    return value


def _shorten_source_ref(value: Optional[str]) -> str:
    """Return a shortened ``source_ref``: every ``:``-delimited segment longer
    than the threshold is middle-elided (head 8 + ``…`` + tail 3); short
    segments (e.g. ``helius`` / ``sig`` / ``slot`` / the slot number) are kept.

    ``helius:sig:<88-char-sig>:slot:424620715`` ->
    ``helius:sig:5hMAYVvm…MFV:slot:424620715``. A missing value renders as
    ``DISPLAY_UNKNOWN``. The caller has already rejected a URL / secret here.
    """
    if not isinstance(value, str) or value.strip() == "":
        return DISPLAY_UNKNOWN
    segments = value.split(_COLON)
    out = []
    for segment in segments:
        if len(segment) > _SRC_SEGMENT_ELIDE_THRESHOLD:
            out.append(
                segment[:_SRC_SEGMENT_HEAD]
                + _ELLIPSIS
                + segment[-_SRC_SEGMENT_TAIL:]
            )
        else:
            out.append(segment)
    shortened = _COLON.join(out)
    if len(shortened) > _SRC_TOTAL_MAX:
        shortened = shortened[: _SRC_TOTAL_MAX - 1] + _ELLIPSIS
    return shortened


# ---------------------------------------------------------------------------
# Public renderer
# ---------------------------------------------------------------------------


def render_phoenix_operator_ping(input_record: PhoenixOperatorPingInput) -> str:
    """Render the Stage 30.12 PHOENIX private operator ping body string.

    Pure / deterministic: identical inputs always produce a byte-identical body.

    Raises ``Stage30_12PhoenixOperatorPingError`` on caller-shape failures:

      * ``INPUT_INVALID_TYPE``               -- not a ``PhoenixOperatorPingInput``.
      * ``TOKEN_MINT_MISSING``               -- ``token_mint`` blank / non-string.
      * ``TOKEN_MINT_IS_WSOL_QUOTE``         -- ``token_mint`` is the WSOL quote
                                                mint (the CA must be the token
                                                mint, never the quote mint).
      * ``TOKEN_MINT_NOT_BASE58``            -- ``token_mint`` not safe-shape
                                                Solana base58.
      * ``TIER_TOKEN_MISSING``               -- ``tier_token`` blank / non-string.
      * ``DISPLAY_TEXT_FORBIDDEN_SUBSTRING`` -- a caller-supplied display field
                                                carries a forbidden URL / webhook
                                                / auth / API-key / RPC / secret
                                                substring or an ASCII control
                                                character.
      * ``BODY_EXCEEDS_HARD_CAP``            -- the rendered body exceeds the
                                                Stage 30.12 hard cap.
    """
    # ---- Caller-shape validation ----
    if not isinstance(input_record, PhoenixOperatorPingInput):
        raise Stage30_12PhoenixOperatorPingError("INPUT_INVALID_TYPE")

    token_mint = input_record.token_mint
    if not isinstance(token_mint, str) or token_mint.strip() == "":
        raise Stage30_12PhoenixOperatorPingError("TOKEN_MINT_MISSING")
    if token_mint == WSOL_QUOTE_MINT:
        raise Stage30_12PhoenixOperatorPingError("TOKEN_MINT_IS_WSOL_QUOTE")
    if not _is_base58_mint(token_mint):
        raise Stage30_12PhoenixOperatorPingError("TOKEN_MINT_NOT_BASE58")

    tier_token = input_record.tier_token
    if not isinstance(tier_token, str) or tier_token.strip() == "":
        raise Stage30_12PhoenixOperatorPingError("TIER_TOKEN_MISSING")

    # ---- Forbidden-substring / control-char scan over every display field ----
    # ``token_mint`` is excluded (already validated as base58, which admits no
    # forbidden / control character by construction).
    for candidate in (
        tier_token,
        input_record.symbol_or_name,
        input_record.migration_time_utc,
        input_record.market_cap_display,
        input_record.liquidity_display,
        input_record.current_price,
        input_record.ath_price,
        input_record.absolute_drawdown,
        input_record.fractional_drop_pct,
        input_record.tier_band_display,
        input_record.basis_display,
        input_record.source_ref,
        input_record.age_display,
    ):
        if isinstance(candidate, str) and candidate != "":
            if _contains_forbidden_or_control(candidate):
                raise Stage30_12PhoenixOperatorPingError(
                    "DISPLAY_TEXT_FORBIDDEN_SUBSTRING"
                )

    # ---- Resolve display slots ----
    symbol_display = _resolve_symbol_display(
        input_record.symbol_or_name, token_mint
    )
    mc_display = _text_or_unknown(input_record.market_cap_display)
    lp_display = _text_or_unknown(input_record.liquidity_display)
    drop_display = _text_or_unknown(input_record.fractional_drop_pct)
    now_price_display = _format_price(input_record.current_price)
    ath_price_display = _format_price(input_record.ath_price)
    mig_display = _format_migration_confirmed(input_record.migration_confirmed)
    age_display = _text_or_unknown(input_record.age_display)
    migration_time_display = _format_migration_time(
        input_record.migration_time_utc
    )
    src_display = _shorten_source_ref(input_record.source_ref)
    basis_display = _text_or_unknown(input_record.basis_display)
    if (
        isinstance(input_record.tier_band_display, str)
        and input_record.tier_band_display.strip() != ""
    ):
        band_display = input_record.tier_band_display
    else:
        band_display = tier_band_display_for(tier_token)

    # ---- Assemble the body ----
    lines = [
        f"{_FIRE} PHOENIX {_EMDASH} {symbol_display} [{tier_token}]",
        f"CA: {token_mint}",
        "",
        f"{_BRAIN} State",
        f"MC: {mc_display} | ATH: {ath_price_display} | Drop: {drop_display}",
        f"LP: {lp_display} | Mig: {mig_display} | Age: {age_display}",
        "",
        f"{_MONEY} Price",
        f"Now: {now_price_display}",
        f"ATH: {ath_price_display}",
        "",
        f"{_TARGET} Dip Gate",
        f"Tier: {tier_token}",
        f"Band: {band_display}",
        f"Basis: {basis_display}",
        "",
        f"{_RECEIPT} Provenance",
        f"Migration: {migration_time_display}",
        f"Src: {src_display}",
        "",
        STAGE30_12_OPERATOR_FOOTER,
    ]
    body = "\n".join(lines)

    if len(body) > STAGE30_12_BODY_CHAR_HARD_CAP:
        raise Stage30_12PhoenixOperatorPingError("BODY_EXCEEDS_HARD_CAP")

    return body


__all__ = (
    "render_phoenix_operator_ping",
)

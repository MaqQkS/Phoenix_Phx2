"""Stage 29.2 Birdeye program-pinned constants.

Stage 29.2 owns a small, locked surface of program-pinned
constants used by the Stage 29.2 Birdeye price / ATH adapter:

  * endpoint paths (``/defi/price`` for current price,
    ``/defi/ohlcv`` for ATH from candle highs),
  * HTTP header names (``X-API-KEY``, ``x-chain``, ``accept``),
  * Stage 29.2 hardcoded chain value (``solana``) -- Stage 29.2
    is Solana-only by construction; the chain is NOT operator-
    overridable and NOT env-driven,
  * default OHLCV candle resolution (``15m``) + the closed-set
    allowed resolutions,
  * default HTTP timeout (seconds) + default lookback hours,
  * safe-shape regex constants used by the readiness module to
    validate the operator-supplied base URL + API key strings,
  * Stage 29.2 minor / schema version pins.

Stage 29.2 deliberately ships NO URL host literal anywhere in
production source. The Birdeye base URL is operator-supplied via
``PHX2_STAGE29_2_BIRDEYE_BASE_URL`` and the readiness module is
the SOLE Stage 29.2 production site that reads any env name.
The Stage 29.2 boundary scan asserts no Birdeye URL host
substring exists in any Stage 29.2 production file.

This module imports ONLY stdlib (``typing``). It does NOT import:

  * Stage 21-28 production code beyond what Stage 29.2 wraps,
  * any network / RPC / messaging / DB / scheduler / secrets /
    wallet / trading / Discord / Telegram / X / dotenv / keyring
    library,
  * ``os`` / the process environment,
  * any PHX1 / legacy Phoenix-1 source tree module.

Discipline:

  * No env reads.
  * No network.
  * No top-level Call (no implicit I/O at import time).
  * No raw API-key-looking literal substring anywhere.
  * No URL host literal (the base URL host is env-supplied; the
    boundary scan forbids the Birdeye host substring in
    production source).
"""

from __future__ import annotations

from typing import Final


# ---------------------------------------------------------------------------
# Stage 29.2 version axes
# ---------------------------------------------------------------------------


STAGE29_2_MINOR_VERSION: Final[str] = "29.2"
STAGE29_2_BIRDEYE_SNAPSHOT_SCHEMA_VERSION: Final[str] = (
    "stage29_2_birdeye_snapshot_v0"
)
STAGE29_2_BIRDEYE_EVIDENCE_SCHEMA_VERSION: Final[str] = (
    "stage29_2_birdeye_evidence_v0"
)
STAGE29_2_BIRDEYE_PROBE_SCHEMA_VERSION: Final[str] = (
    "stage29_2_birdeye_probe_v0"
)
STAGE29_2_BIRDEYE_READINESS_SCHEMA_VERSION: Final[str] = (
    "stage29_2_birdeye_readiness_v0"
)


# ---------------------------------------------------------------------------
# Stage 29.2 redaction token (distinct from Stage 27 / 28.x / 29.1)
# ---------------------------------------------------------------------------


STAGE29_2_REDACTION_TOKEN: Final[str] = "<<STAGE29_2_REDACTED>>"


# ---------------------------------------------------------------------------
# Stage 29.2 endpoint paths
# ---------------------------------------------------------------------------
#
# Locked at exactly these three paths (price + ohlcv for the Stage
# 29.2 price/ATH adapter; token_overview for the Stage 30.4.3
# compact market-context bridge). Any further endpoint expansion
# requires an explicitly-authorized Stage 29.x / 30.x substage. The
# paths are path-only (no host literal); the operator-supplied base
# URL is concatenated by the HTTP transport.


BIRDEYE_PATH_PRICE: Final[str] = "/defi/price"
BIRDEYE_PATH_OHLCV: Final[str] = "/defi/ohlcv"
# Stage 30.4.3 token-overview source path. Birdeye's token-overview
# endpoint returns the current market-cap + liquidity snapshot the
# Stage 30.4 compact market-context bridge reads. Path-only (no host
# literal); the operator-supplied base URL is concatenated by the
# HTTP transport. Stage 29.2 owns the allowed-path surface; the
# Stage 30.4 bridge owns the mapping into compact market context.
BIRDEYE_PATH_TOKEN_OVERVIEW: Final[str] = "/defi/token_overview"


BIRDEYE_ALLOWED_PATHS: Final[tuple[str, ...]] = (
    BIRDEYE_PATH_PRICE,
    BIRDEYE_PATH_OHLCV,
    BIRDEYE_PATH_TOKEN_OVERVIEW,
)


# ---------------------------------------------------------------------------
# Stage 29.2 HTTP method
# ---------------------------------------------------------------------------


BIRDEYE_HTTP_METHOD_GET: Final[str] = "GET"


# ---------------------------------------------------------------------------
# Stage 29.2 HTTP header names + values
# ---------------------------------------------------------------------------
#
# The ``X-API-KEY`` header carries the operator's Birdeye API key.
# The ``x-chain`` header is HARDCODED to ``solana``; Stage 29.2 is
# Solana-only by construction. The ``accept`` header pins
# ``application/json`` so a Birdeye misconfiguration cannot send
# back HTML or another content type that Stage 29.2 cannot parse.


BIRDEYE_HEADER_X_API_KEY: Final[str] = "X-API-KEY"
BIRDEYE_HEADER_X_CHAIN: Final[str] = "x-chain"
BIRDEYE_HEADER_ACCEPT: Final[str] = "accept"


BIRDEYE_X_CHAIN_VALUE_SOLANA: Final[str] = "solana"
BIRDEYE_ACCEPT_VALUE_JSON: Final[str] = "application/json"


# Stage 29.2 user-agent identifier. Carries no version-info that
# would leak environment details; just a fixed Stage-29.2-pinned
# label so Birdeye's audit log can distinguish Stage 29.2 traffic.
BIRDEYE_USER_AGENT: Final[str] = "phx2-stage29-2/1"


# ---------------------------------------------------------------------------
# Stage 29.2 OHLCV candle-resolution closed set
# ---------------------------------------------------------------------------


BIRDEYE_OHLCV_TYPE_1M: Final[str] = "1m"
BIRDEYE_OHLCV_TYPE_3M: Final[str] = "3m"
BIRDEYE_OHLCV_TYPE_5M: Final[str] = "5m"
BIRDEYE_OHLCV_TYPE_15M: Final[str] = "15m"
BIRDEYE_OHLCV_TYPE_30M: Final[str] = "30m"
BIRDEYE_OHLCV_TYPE_1H: Final[str] = "1H"
BIRDEYE_OHLCV_TYPE_2H: Final[str] = "2H"
BIRDEYE_OHLCV_TYPE_4H: Final[str] = "4H"
BIRDEYE_OHLCV_TYPE_6H: Final[str] = "6H"
BIRDEYE_OHLCV_TYPE_8H: Final[str] = "8H"
BIRDEYE_OHLCV_TYPE_12H: Final[str] = "12H"
BIRDEYE_OHLCV_TYPE_1D: Final[str] = "1D"
BIRDEYE_OHLCV_TYPE_3D: Final[str] = "3D"
BIRDEYE_OHLCV_TYPE_1W: Final[str] = "1W"
BIRDEYE_OHLCV_TYPE_1MONTH: Final[str] = "1M"


BIRDEYE_OHLCV_TYPE_ALLOWED: Final[tuple[str, ...]] = (
    BIRDEYE_OHLCV_TYPE_1M,
    BIRDEYE_OHLCV_TYPE_3M,
    BIRDEYE_OHLCV_TYPE_5M,
    BIRDEYE_OHLCV_TYPE_15M,
    BIRDEYE_OHLCV_TYPE_30M,
    BIRDEYE_OHLCV_TYPE_1H,
    BIRDEYE_OHLCV_TYPE_2H,
    BIRDEYE_OHLCV_TYPE_4H,
    BIRDEYE_OHLCV_TYPE_6H,
    BIRDEYE_OHLCV_TYPE_8H,
    BIRDEYE_OHLCV_TYPE_12H,
    BIRDEYE_OHLCV_TYPE_1D,
    BIRDEYE_OHLCV_TYPE_3D,
    BIRDEYE_OHLCV_TYPE_1W,
    BIRDEYE_OHLCV_TYPE_1MONTH,
)


BIRDEYE_DEFAULT_OHLCV_TYPE: Final[str] = BIRDEYE_OHLCV_TYPE_15M


def is_allowed_ohlcv_type(value: object) -> bool:
    """Return ``True`` iff ``value`` is a known Stage 29.2 OHLCV
    candle resolution token.

    Pure / deterministic.
    """
    return (
        isinstance(value, str)
        and value in BIRDEYE_OHLCV_TYPE_ALLOWED
    )


# ---------------------------------------------------------------------------
# Stage 29.2 bounded defaults
# ---------------------------------------------------------------------------


DEFAULT_HTTP_TIMEOUT_SECONDS: Final[int] = 30
MIN_HTTP_TIMEOUT_SECONDS: Final[int] = 1
MAX_HTTP_TIMEOUT_SECONDS: Final[int] = 600


DEFAULT_LOOKBACK_HOURS: Final[int] = 24
MIN_LOOKBACK_HOURS: Final[int] = 1
MAX_LOOKBACK_HOURS: Final[int] = 168  # 7 days


# Stage 29.2 mode-3 probe budget. The probe makes at most two
# outbound requests (one ``/defi/price`` + one ``/defi/ohlcv``);
# mode-2 makes exactly one. No retries.
STAGE29_2_PROBE_MAX_REQUESTS: Final[int] = 2


# ---------------------------------------------------------------------------
# Stage 29.2 safe-shape validators
# ---------------------------------------------------------------------------
#
# Stage 29.2 carries NO regex literals in production source. The
# validators below are explicit Python loops over a small allow
# character class. Same approach as Stage 28.11's safe-shape
# validators.


BIRDEYE_BASE_URL_MIN_LENGTH: Final[int] = 12
BIRDEYE_BASE_URL_MAX_LENGTH: Final[int] = 256
BIRDEYE_BASE_URL_REQUIRED_PREFIX: Final[str] = "https://"
BIRDEYE_BASE_URL_ALLOWED_CHARS: Final[frozenset[str]] = frozenset(
    "abcdefghijklmnopqrstuvwxyz"
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    "0123456789"
    ".-_:/"
)


BIRDEYE_API_KEY_MIN_LENGTH: Final[int] = 16
BIRDEYE_API_KEY_MAX_LENGTH: Final[int] = 256
BIRDEYE_API_KEY_ALLOWED_CHARS: Final[frozenset[str]] = frozenset(
    "abcdefghijklmnopqrstuvwxyz"
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    "0123456789"
    "-_"
)


BIRDEYE_MINT_MIN_LENGTH: Final[int] = 32
BIRDEYE_MINT_MAX_LENGTH: Final[int] = 64
BIRDEYE_MINT_ALLOWED_CHARS: Final[frozenset[str]] = frozenset(
    "abcdefghijklmnopqrstuvwxyz"
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    "0123456789"
)


def is_safe_base_url(value: object) -> bool:
    """Return ``True`` iff ``value`` is a safe-shape Birdeye base
    URL: ``https://``-prefixed, bounded length, only the allowed
    URL character class. NEVER inspects whether the host is
    Birdeye -- the readiness module pins the value via the env
    boundary; this check is shape-only.
    """
    if not isinstance(value, str):
        return False
    n = len(value)
    if n < BIRDEYE_BASE_URL_MIN_LENGTH:
        return False
    if n > BIRDEYE_BASE_URL_MAX_LENGTH:
        return False
    if not value.startswith(BIRDEYE_BASE_URL_REQUIRED_PREFIX):
        return False
    if value.endswith("/"):
        # Reject trailing slash; concatenation with path constants
        # already provides the leading slash.
        return False
    for ch in value:
        if ch not in BIRDEYE_BASE_URL_ALLOWED_CHARS:
            return False
    return True


def is_safe_api_key(value: object) -> bool:
    """Return ``True`` iff ``value`` is a safe-shape Birdeye API
    key. Stage 29.2 NEVER echoes the raw value on any public
    surface; this validator is the only Stage 29.2 site that
    inspects character-class shape.
    """
    if not isinstance(value, str):
        return False
    n = len(value)
    if n < BIRDEYE_API_KEY_MIN_LENGTH:
        return False
    if n > BIRDEYE_API_KEY_MAX_LENGTH:
        return False
    for ch in value:
        if ch not in BIRDEYE_API_KEY_ALLOWED_CHARS:
            return False
    return True


def is_safe_mint(value: object) -> bool:
    """Return ``True`` iff ``value`` is a safe-shape Solana mint
    string. Stage 29.2 does NOT base58-decode; it only enforces
    the character-class allow-list + length bounds. The upstream
    Stage 29.1 hint extractor is the authoritative mint shape
    source.
    """
    if not isinstance(value, str):
        return False
    n = len(value)
    if n < BIRDEYE_MINT_MIN_LENGTH:
        return False
    if n > BIRDEYE_MINT_MAX_LENGTH:
        return False
    for ch in value:
        if ch not in BIRDEYE_MINT_ALLOWED_CHARS:
            return False
    return True


def is_safe_timeout_seconds(value: object) -> bool:
    """Return ``True`` iff ``value`` is a safe int timeout in
    seconds within Stage 29.2's bounded range.
    """
    if isinstance(value, bool):
        return False
    if not isinstance(value, int):
        return False
    if value < MIN_HTTP_TIMEOUT_SECONDS:
        return False
    if value > MAX_HTTP_TIMEOUT_SECONDS:
        return False
    return True


def is_safe_lookback_hours(value: object) -> bool:
    """Return ``True`` iff ``value`` is a safe int lookback in
    hours within Stage 29.2's bounded range.
    """
    if isinstance(value, bool):
        return False
    if not isinstance(value, int):
        return False
    if value < MIN_LOOKBACK_HOURS:
        return False
    if value > MAX_LOOKBACK_HOURS:
        return False
    return True


# ---------------------------------------------------------------------------
# Stage 29.2 safe source labels (echoed on snapshots; redaction-safe)
# ---------------------------------------------------------------------------


BIRDEYE_PRICE_SOURCE_LABEL: Final[str] = "birdeye_defi_price"
BIRDEYE_OHLCV_SOURCE_LABEL: Final[str] = "birdeye_defi_ohlcv"


# ---------------------------------------------------------------------------
# Stage 29.2 known quote-asset unit
# ---------------------------------------------------------------------------
#
# Stage 29.2 reports prices in USD (Birdeye's default ``currency``).
# The Stage 27.4 ATH context reader admits ``USD`` as a fallback
# unit via ``ATH_UNIT_USD`` even when the pair quote asset is SOL,
# matching Birdeye's natural reporting unit.


BIRDEYE_REPORTING_UNIT_USD: Final[str] = "USD"


__all__ = (
    "STAGE29_2_MINOR_VERSION",
    "STAGE29_2_BIRDEYE_SNAPSHOT_SCHEMA_VERSION",
    "STAGE29_2_BIRDEYE_EVIDENCE_SCHEMA_VERSION",
    "STAGE29_2_BIRDEYE_PROBE_SCHEMA_VERSION",
    "STAGE29_2_BIRDEYE_READINESS_SCHEMA_VERSION",
    "STAGE29_2_REDACTION_TOKEN",
    "BIRDEYE_PATH_PRICE",
    "BIRDEYE_PATH_OHLCV",
    "BIRDEYE_PATH_TOKEN_OVERVIEW",
    "BIRDEYE_ALLOWED_PATHS",
    "BIRDEYE_HTTP_METHOD_GET",
    "BIRDEYE_HEADER_X_API_KEY",
    "BIRDEYE_HEADER_X_CHAIN",
    "BIRDEYE_HEADER_ACCEPT",
    "BIRDEYE_X_CHAIN_VALUE_SOLANA",
    "BIRDEYE_ACCEPT_VALUE_JSON",
    "BIRDEYE_USER_AGENT",
    "BIRDEYE_OHLCV_TYPE_1M",
    "BIRDEYE_OHLCV_TYPE_3M",
    "BIRDEYE_OHLCV_TYPE_5M",
    "BIRDEYE_OHLCV_TYPE_15M",
    "BIRDEYE_OHLCV_TYPE_30M",
    "BIRDEYE_OHLCV_TYPE_1H",
    "BIRDEYE_OHLCV_TYPE_2H",
    "BIRDEYE_OHLCV_TYPE_4H",
    "BIRDEYE_OHLCV_TYPE_6H",
    "BIRDEYE_OHLCV_TYPE_8H",
    "BIRDEYE_OHLCV_TYPE_12H",
    "BIRDEYE_OHLCV_TYPE_1D",
    "BIRDEYE_OHLCV_TYPE_3D",
    "BIRDEYE_OHLCV_TYPE_1W",
    "BIRDEYE_OHLCV_TYPE_1MONTH",
    "BIRDEYE_OHLCV_TYPE_ALLOWED",
    "BIRDEYE_DEFAULT_OHLCV_TYPE",
    "is_allowed_ohlcv_type",
    "DEFAULT_HTTP_TIMEOUT_SECONDS",
    "MIN_HTTP_TIMEOUT_SECONDS",
    "MAX_HTTP_TIMEOUT_SECONDS",
    "DEFAULT_LOOKBACK_HOURS",
    "MIN_LOOKBACK_HOURS",
    "MAX_LOOKBACK_HOURS",
    "STAGE29_2_PROBE_MAX_REQUESTS",
    "BIRDEYE_BASE_URL_MIN_LENGTH",
    "BIRDEYE_BASE_URL_MAX_LENGTH",
    "BIRDEYE_BASE_URL_REQUIRED_PREFIX",
    "BIRDEYE_BASE_URL_ALLOWED_CHARS",
    "BIRDEYE_API_KEY_MIN_LENGTH",
    "BIRDEYE_API_KEY_MAX_LENGTH",
    "BIRDEYE_API_KEY_ALLOWED_CHARS",
    "BIRDEYE_MINT_MIN_LENGTH",
    "BIRDEYE_MINT_MAX_LENGTH",
    "BIRDEYE_MINT_ALLOWED_CHARS",
    "is_safe_base_url",
    "is_safe_api_key",
    "is_safe_mint",
    "is_safe_timeout_seconds",
    "is_safe_lookback_hours",
    "BIRDEYE_PRICE_SOURCE_LABEL",
    "BIRDEYE_OHLCV_SOURCE_LABEL",
    "BIRDEYE_REPORTING_UNIT_USD",
)

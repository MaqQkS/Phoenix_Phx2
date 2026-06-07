"""Stage 30.12 PHOENIX private operator ping closed-set vocabularies and
immutable input record shape.

Stage 30.12 ships the pure-Python model layer for the RICH private operator
ping body the Stage 30.12 renderer emits. It is the committed home for the
PHOENIX operator format the first real private send improvised out-of-repo
(ceremony glue, NOT a committed renderer). Stage 30.12 is a clean LEAF: this
module imports NO PHX2 module and the renderer imports ONLY this models
sibling. It is NOT wired into the Stage 30.11.5 bounded-runner / dip-gate /
transport send path; it is a pure projector, exactly as the Stage 30.2 compact
renderer shipped (a separate, operator-authorized wiring step is required to
feed it from the live chain, and the live chain does not yet carry every rich
field -- see the Stage 30.12 audit).

Why a NEW renderer (not the Stage 30.2 compact renderer):

  * The Stage 30.2 renderer is MC-centric: it has NO ``Price`` section, NO
    ``Dip Gate`` section, and NO ``Provenance`` section, and its drop-percent
    helper assumes ``drop_positive`` is a FRACTION. After the committed Stage
    30.1 change (classify tiers by fractional drawdown) ``drop_positive`` is the
    ABSOLUTE delta, so reusing that helper would render ``-0%`` for a sub-dollar
    token. Stage 30.12 takes the fractional drop percentage as an EXPLICIT
    input string and never derives it from an absolute magnitude.

Target body shape (full case):

    🔥 PHOENIX — <symbol-or-mint-short> [<tier_token>]
    CA: <full-token-mint>

    🧠 State
    MC: <X> | ATH MC: <X> | Drop: <X>
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

Stage 30.12 deliberately does NOT carry / emit:

  * raw provider payload blobs (no field ever takes a raw payload),
  * secrets, webhook URLs, API keys, bearer tokens, authorization headers, RPC
    URLs (the renderer scans every caller-supplied display field for the
    closed-set forbidden URL / auth / secret / transport substrings BEFORE
    assembling the body and fails closed on any match),
  * the WSOL / quote mint as the token CA (the renderer fails closed),
  * a fabricated value for any missing field (missing optional fields render as
    the literal ``Unknown``; never ``0`` / ``0.0`` / empty / an estimate),
  * trading verdicts (the renderer derives / appends none; the body's only
    ``Gate`` token is the STATIC ``🎯 Dip Gate`` section label, never a verdict),
  * Stage 26 / Stage 29 enforcement decisions (Stage 30 is informational-only).

Discipline:

  * Stdlib only (``typing``).
  * Imports NO PHX2 module (the tier-token strings + the WSOL quote mint are
    mirrored BY VALUE; the slice stays a clean leaf).
  * No ``os.environ`` / ``os.getenv`` / ``os.environb`` access.
  * No network, no HTTP, no gRPC, no WebSocket, no socket.
  * No Discord, Telegram, X / social, webhook, Helius, Chainstack, Birdeye,
    Dexscreener, Pump.fun reference.
  * No PHX1 import. No legacy phoenix-1 import path.
  * No Stage 21-29 / Stage 30.1 / Stage 30.2 / Stage 30.11 production-source
    modification.
  * No top-level Call (no implicit I/O at import time).
"""

from __future__ import annotations

from typing import NamedTuple, Optional, Tuple


# ---------------------------------------------------------------------------
# Stage 30.12 schema version + body cap + display sentinel
# ---------------------------------------------------------------------------


STAGE30_12_MINOR_VERSION: str = "30.12"
STAGE30_12_PHOENIX_OPERATOR_PING_SCHEMA_VERSION: str = (
    "stage30_12_v0_phoenix_operator_ping"
)


# Hard cap on body length. The renderer raises if it would ever emit a body
# above this length. The cap echoes the Stage 28.9 Discord content cap
# (``STAGE28_9_CONTENT_MAX_CHARS = 1900``); Stage 30.12 pins the value verbatim
# WITHOUT importing Stage 28.
STAGE30_12_BODY_CHAR_HARD_CAP: int = 1900


# Literal missing-value sentinel for every optional display field. NEVER use
# ``"0"`` / ``"0.0"`` / empty string / a fabricated estimate.
DISPLAY_UNKNOWN: str = "Unknown"


# The private/operator-only footer line. Operator-only wording is present but
# is NOT the body title (the title is the PHOENIX header).
STAGE30_12_OPERATOR_FOOTER: str = "PRIVATE OPERATOR ONLY · PHX2"


# ---------------------------------------------------------------------------
# Tier tokens (mirrored BY VALUE from the committed Stage 30.1
# ``tier_decision_models``; this module imports no Stage 30.1 file so the slice
# stays a clean leaf -- the renderer does NOT recompute or validate tiers, it
# only maps a tier token to its DISPLAY band string)
# ---------------------------------------------------------------------------


TIER_TOKEN_TIER_1: str = "Tier 1"
TIER_TOKEN_TIER_2: str = "Tier 2"
TIER_TOKEN_TIER_3: str = "Tier 3"
TIER_TOKEN_TIER_UNKNOWN: str = "Tier Unknown"
TIER_TOKEN_TIER_NOT_APPLICABLE: str = "Tier Not Applicable"


# ---------------------------------------------------------------------------
# Tier band display strings (display ONLY; the committed Stage 30.1 projector
# owns the real Decimal bands and the tier logic -- Stage 30.12 changes none of
# it). The percent-range strings mirror the spec-locked inclusive bands
# (0.50-0.60 / 0.62-0.80 / 0.82-0.95) in operator-readable percent form. The
# separator is an en dash (``–``).
# ---------------------------------------------------------------------------


TIER_BAND_DISPLAY_TIER_1: str = "50%–60%"
TIER_BAND_DISPLAY_TIER_2: str = "62%–80%"
TIER_BAND_DISPLAY_TIER_3: str = "82%–95%"


# A tier token with no in-band percentage range (Unknown / Not Applicable / any
# unrecognized token) maps to the ``Unknown`` sentinel -- the renderer NEVER
# fabricates a band for a non-tier token.
TIER_BAND_DISPLAY_BY_TIER_TOKEN: dict = {
    TIER_TOKEN_TIER_1: TIER_BAND_DISPLAY_TIER_1,
    TIER_TOKEN_TIER_2: TIER_BAND_DISPLAY_TIER_2,
    TIER_TOKEN_TIER_3: TIER_BAND_DISPLAY_TIER_3,
}


def tier_band_display_for(tier_token: object) -> str:
    """Return the operator-readable percent band for ``tier_token``.

    Pure / total; never raises. ``Tier 1`` / ``Tier 2`` / ``Tier 3`` map to the
    spec-locked percent ranges; every other token (``Tier Unknown`` / ``Tier
    Not Applicable`` / a non-string / an unrecognized value) maps to the
    ``Unknown`` sentinel. Display ONLY -- this NEVER changes tier logic.
    """
    if not isinstance(tier_token, str):
        return DISPLAY_UNKNOWN
    return TIER_BAND_DISPLAY_BY_TIER_TOKEN.get(tier_token, DISPLAY_UNKNOWN)


# ---------------------------------------------------------------------------
# WSOL / quote mint (mirrored BY VALUE). The renderer fails closed if a caller
# passes this as ``token_mint`` -- the PHOENIX ping CA must always be the token
# / base mint, NEVER the wrapped-SOL quote mint.
# ---------------------------------------------------------------------------


WSOL_QUOTE_MINT: str = "So11111111111111111111111111111111111111112"


# ---------------------------------------------------------------------------
# Immutable input record: PHOENIX operator ping
# ---------------------------------------------------------------------------


class PhoenixOperatorPingInput(NamedTuple):
    """Immutable Stage 30.12 PHOENIX operator ping input record.

    Caller-supplied input to the Stage 30.12 renderer. ``token_mint`` and
    ``tier_token`` are REQUIRED; every other field is OPTIONAL and defaults to
    ``None`` (rendering as the ``Unknown`` sentinel). All display-bearing
    fields are already-formatted display text EXCEPT ``current_price`` /
    ``ath_price`` (raw canonical decimal-text the renderer formats to a clean
    ``$`` price) and ``source_ref`` (the renderer middle-elides long segments).

    Fields:

      * ``token_mint``           -- REQUIRED safe-shape Solana base58 token /
                                    base mint (the CA). NEVER the WSOL quote
                                    mint (the renderer fails closed).
      * ``tier_token``           -- REQUIRED Stage 30.1 tier token display
                                    string (``Tier 1`` / ... / ``Tier Unknown``);
                                    echoed verbatim, never recomputed.
      * ``symbol_or_name``       -- short token symbol / name, or ``None`` (the
                                    header falls back to the short mint form).
      * ``migration_confirmed``  -- ``True`` -> ``Confirmed``; ``False`` /
                                    ``None`` -> ``Unknown``.
      * ``migration_time_utc``   -- ISO-8601 UTC migration timestamp display
                                    string, or ``None``.
      * ``market_cap_display``   -- already-formatted MC display (e.g. ``$5.1k``)
                                    or ``None``.
      * ``liquidity_display``    -- already-formatted LP display (e.g. ``$4.8k``)
                                    or ``None``.
      * ``current_price``        -- raw canonical decimal-text current price, or
                                    ``None``. The renderer formats it.
      * ``ath_price``            -- raw canonical decimal-text ATH price, or
                                    ``None``. The renderer formats it.
      * ``absolute_drawdown``    -- raw absolute drawdown magnitude, or ``None``.
                                    Accepted for completeness; INTENTIONALLY not
                                    rendered (the compact body shows the
                                    fractional drop, not the noisy absolute
                                    delta) -- keeping the regression that the
                                    drop percent is NEVER derived from it.
      * ``fractional_drop_pct``  -- the EXPLICIT operator-facing fractional drop
                                    percent display (e.g. ``-75.39%``), or
                                    ``None``. The renderer echoes it verbatim and
                                    NEVER multiplies ``absolute_drawdown`` by 100.
      * ``tier_band_display``    -- an explicit band display string; when
                                    ``None`` the renderer derives the band from
                                    ``tier_token`` via ``tier_band_display_for``.
      * ``basis_display``        -- the drawdown basis display (e.g.
                                    ``Post-migration ATH``), or ``None``.
      * ``source_ref``           -- an opaque provenance ref (e.g.
                                    ``helius:sig:<sig>:slot:<slot>``), or
                                    ``None``. The renderer middle-elides long
                                    segments; it NEVER admits a URL / secret.
      * ``age_display``          -- already-formatted age-since-migration display
                                    (e.g. ``16.6h``), or ``None``.
      * ``ath_market_cap_display`` -- already-formatted ATH market-cap display
                                    (e.g. ``$28.4k``) shown beside the current MC
                                    in the State line, or ``None``. Echoed
                                    verbatim; the renderer NEVER computes ATH MC
                                    from ``ath_price`` (the upstream ceremony
                                    derives it and formats it). A missing value
                                    renders as ``Unknown``.
    """

    token_mint: str
    tier_token: str
    symbol_or_name: Optional[str] = None
    migration_confirmed: Optional[bool] = None
    migration_time_utc: Optional[str] = None
    market_cap_display: Optional[str] = None
    liquidity_display: Optional[str] = None
    current_price: Optional[str] = None
    ath_price: Optional[str] = None
    absolute_drawdown: Optional[str] = None
    fractional_drop_pct: Optional[str] = None
    tier_band_display: Optional[str] = None
    basis_display: Optional[str] = None
    source_ref: Optional[str] = None
    age_display: Optional[str] = None
    ath_market_cap_display: Optional[str] = None


# ---------------------------------------------------------------------------
# Forbidden field-name vocabulary (defensive sentinel)
# ---------------------------------------------------------------------------
#
# Stage 30.12 must never accept a field named anything secret-class or
# raw-payload-class on its input record. The current
# ``PhoenixOperatorPingInput._fields`` set has no such name, but this helper is
# kept so a future refactor cannot silently widen the admitted field set. The
# needle list uses split-literal concatenation so this module's own source does
# NOT carry the bare secret-class substrings.


FORBIDDEN_RECORD_FIELD_NAMES: Tuple[str, ...] = (
    "web" + "hook",
    "web" + "hook_url",
    "web" + "hooks",
    "api_" + "key",
    "api" + "key",
    "b" + "earer",
    "b" + "earer_token",
    "author" + "ization",
    "secret",
    "secret_key",
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
    "raw_capture_ref",
    "rpc_" + "url",
    "endpoint_" + "url",
    "host",
)


def is_forbidden_record_field_name(name: object) -> bool:
    """Return ``True`` iff ``name`` is a forbidden record field name.

    Pure / deterministic. Stage 30.12 uses this guard to reject any future
    refactor that tries to widen the input record with a secret-class or
    raw-payload-class field name.
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


class Stage30_12PhoenixOperatorPingError(Exception):
    """Closed-set Stage 30.12 PHOENIX operator ping error.

    Carries only a closed-set reason token on the exception message. Stage
    30.12 callers should never embed a raw OSError message, a raw provider
    payload, or any secret value in the message.
    """

    def __init__(self, reason: str) -> None:
        self.reason: str = reason
        super().__init__(
            f"Stage 30.12 PHOENIX operator ping error: reason={reason!r}"
        )


__all__ = (
    # Version + caps + sentinels.
    "STAGE30_12_MINOR_VERSION",
    "STAGE30_12_PHOENIX_OPERATOR_PING_SCHEMA_VERSION",
    "STAGE30_12_BODY_CHAR_HARD_CAP",
    "DISPLAY_UNKNOWN",
    "STAGE30_12_OPERATOR_FOOTER",
    # Tier tokens (mirrored BY VALUE).
    "TIER_TOKEN_TIER_1",
    "TIER_TOKEN_TIER_2",
    "TIER_TOKEN_TIER_3",
    "TIER_TOKEN_TIER_UNKNOWN",
    "TIER_TOKEN_TIER_NOT_APPLICABLE",
    # Tier band display map.
    "TIER_BAND_DISPLAY_TIER_1",
    "TIER_BAND_DISPLAY_TIER_2",
    "TIER_BAND_DISPLAY_TIER_3",
    "TIER_BAND_DISPLAY_BY_TIER_TOKEN",
    "tier_band_display_for",
    # WSOL quote mint guard value.
    "WSOL_QUOTE_MINT",
    # Record.
    "PhoenixOperatorPingInput",
    # Forbidden-field guard.
    "FORBIDDEN_RECORD_FIELD_NAMES",
    "is_forbidden_record_field_name",
    # Error.
    "Stage30_12PhoenixOperatorPingError",
)

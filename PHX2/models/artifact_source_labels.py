"""Centralized ROLE-based, artifact-safe source labels.

WHY THIS EXISTS
---------------
Every artifact PHX2 writes is scanned by the production credential scanner, and
a provider PRODUCT NAME is one of its danger needles.  A label like
``birdeye_defi_price`` carries no credential, but it fails the scan, and a
failed scan is a run-killer: the 2026-07-30 canary died every ~2.5 minutes
because one such value (``BIRDEYE_AND_HELIUS_PRIMARY``) reached
``watch_state.jsonl``.  That value was renamed; this module closes the class.

The rule is simple and applies at the ARTIFACT BOUNDARY, not inside a provider
adapter: a persisted label may name the ROLE a source plays, never the product
behind it.  Provider adapters keep their own internal spec-locked labels (e.g.
the Stage 29.2 price/OHLCV snapshot labels); this module maps them to a
role-based token at the moment they would cross into a scanned artifact.

WHAT THIS IS NOT
----------------
It is NOT a scanner exemption.  Nothing here is added to
``FIXED_PUBLIC_REDACTION_TOKENS``; the provider-named values remain danger
needles and would still fail a scan if they leaked.  This module RENAMES, and
for an unknown value that the scanner rejects it WITHHOLDS -- it never
allowlists.
"""

from __future__ import annotations

from typing import Any, Dict, Mapping, Optional, Tuple

# -- role-based artifact-safe source labels (closed set) --------------------
#: Paid market-data authority, spot price surface.
SOURCE_ROLE_PAID_MARKET_SPOT_PRICE = "PAID_MARKET_SPOT_PRICE"
#: Paid market-data authority, historical candle (OHLCV) surface.
SOURCE_ROLE_PAID_MARKET_OHLCV = "PAID_MARKET_OHLCV"
#: Paid market-data authority, unspecified/aggregate surface.
SOURCE_ROLE_PAID_MARKET_PRIMARY = "PAID_MARKET_PRIMARY"
#: Non-paid market path (free-tier / fallback).
SOURCE_ROLE_NON_PAID_PRIMARY = "NON_PAID_PRIMARY"
#: Authoritative live migration source (the one owned WSS stream).
SOURCE_ROLE_LIVE_MIGRATION_PRIMARY = "LIVE_MIGRATION_PRIMARY"
#: Bounded exact-range HTTP recovery of a proven slot gap.
SOURCE_ROLE_EXACT_GAP_RECOVERY = "EXACT_GAP_RECOVERY"
#: Curated best-effort DEX safety net.
SOURCE_ROLE_CURATED_SAFETY_NET = "CURATED_SAFETY_NET"
#: Canonical on-chain pool-reserve evidence.
SOURCE_ROLE_CANONICAL_RESERVES = "CANONICAL_RESERVES"
#: Required source evidence could not be obtained.
SOURCE_ROLE_UNAVAILABLE = "MARKET_SOURCE_UNAVAILABLE"
#: A value that is neither a known role nor safely publishable.  Used by the
#: withholding path so an artifact records THAT a label was withheld without
#: recording the label.
SOURCE_ROLE_WITHHELD_UNSAFE = "SOURCE_LABEL_WITHHELD_UNSAFE"

ARTIFACT_SAFE_SOURCE_LABELS: Tuple[str, ...] = (
    SOURCE_ROLE_PAID_MARKET_SPOT_PRICE,
    SOURCE_ROLE_PAID_MARKET_OHLCV,
    SOURCE_ROLE_PAID_MARKET_PRIMARY,
    SOURCE_ROLE_NON_PAID_PRIMARY,
    SOURCE_ROLE_LIVE_MIGRATION_PRIMARY,
    SOURCE_ROLE_EXACT_GAP_RECOVERY,
    SOURCE_ROLE_CURATED_SAFETY_NET,
    SOURCE_ROLE_CANONICAL_RESERVES,
    SOURCE_ROLE_UNAVAILABLE,
    SOURCE_ROLE_WITHHELD_UNSAFE,
)

#: Retired provider-named label -> role-based replacement.  PRIVATE: this is a
#: migration table, never serialized into an artifact.  Keys are matched
#: case-insensitively after stripping.
_RETIRED_SOURCE_LABEL_ALIASES: Dict[str, str] = {
    # Stage 29.2 provider snapshot labels.
    "birdeye_defi_price": SOURCE_ROLE_PAID_MARKET_SPOT_PRICE,
    "birdeye_defi_ohlcv": SOURCE_ROLE_PAID_MARKET_OHLCV,
    # Bare provider family / product names used as observation sources.
    "birdeye": SOURCE_ROLE_PAID_MARKET_PRIMARY,
    "birdeye_primary": SOURCE_ROLE_PAID_MARKET_PRIMARY,
    "birdeye_and_helius_primary": SOURCE_ROLE_PAID_MARKET_PRIMARY,
    "chainstack": SOURCE_ROLE_LIVE_MIGRATION_PRIMARY,
    "helius": SOURCE_ROLE_LIVE_MIGRATION_PRIMARY,
    "helius_primary": SOURCE_ROLE_LIVE_MIGRATION_PRIMARY,
    "helius_enhanced_wss": SOURCE_ROLE_LIVE_MIGRATION_PRIMARY,
    "helius_enhanced_http": SOURCE_ROLE_EXACT_GAP_RECOVERY,
}

#: Provider-named PREFIXES whose whole family is retired from artifacts.  Any
#: label starting with one of these maps to the paired role.
_RETIRED_SOURCE_LABEL_PREFIXES: Tuple[Tuple[str, str], ...] = (
    ("stage29_2_birdeye_ohlcv", SOURCE_ROLE_PAID_MARKET_OHLCV),
    ("stage29_2_birdeye_price", SOURCE_ROLE_PAID_MARKET_SPOT_PRICE),
    ("stage29_2_birdeye", SOURCE_ROLE_PAID_MARKET_PRIMARY),
    ("birdeye_defi_ohlcv", SOURCE_ROLE_PAID_MARKET_OHLCV),
    ("birdeye_defi_price", SOURCE_ROLE_PAID_MARKET_SPOT_PRICE),
    ("birdeye", SOURCE_ROLE_PAID_MARKET_PRIMARY),
)


def is_artifact_safe_source_label(value: object) -> bool:
    """True only for exact members of the role-based closed set."""

    return value in ARTIFACT_SAFE_SOURCE_LABELS


def artifact_safe_source_label(
    value: object,
    *,
    scan_fn: Optional[Any] = None,
    default: str = SOURCE_ROLE_WITHHELD_UNSAFE,
) -> Optional[str]:
    """Map one source label to its artifact-safe role token.

    Resolution order:

    1. ``None`` and non-strings pass through unchanged -- absence is not a leak
       and coercing a non-string would hide a schema bug.
    2. An exact role-based token passes through unchanged.
    3. A known retired provider label (exact, then prefix, case-insensitive)
       maps to its role.
    4. Otherwise, when ``scan_fn`` is supplied, the value is offered to the
       REAL scanner: safe values pass through unchanged (so unrelated
       closed-set tokens keep working), and a value the scanner rejects is
       replaced by ``default`` -- withheld, never allowlisted.
    5. With no ``scan_fn`` an unknown value passes through unchanged, so it
       stays visible to the artifact scanner rather than being silently
       rewritten.
    """

    if value is None or not isinstance(value, str):
        return value  # type: ignore[return-value]
    if is_artifact_safe_source_label(value):
        return value
    key = value.strip().lower()
    mapped = _RETIRED_SOURCE_LABEL_ALIASES.get(key)
    if mapped is not None:
        return mapped
    for prefix, role in _RETIRED_SOURCE_LABEL_PREFIXES:
        if key.startswith(prefix):
            return role
    if scan_fn is None:
        return value
    try:
        hits = scan_fn(value)
    except Exception:
        return default
    return value if not hits else default


# -- safe rule identifiers ---------------------------------------------------
#
# The inherited production scanner reports the DANGER NEEDLE ITSELF (``://``,
# ``api-key``, ``helius-rpc``, ...), so writing its raw output into an artifact
# would make the disclosure record fail the very scan it is disclosing.  Each
# needle is therefore translated to a stable identifier that names the RULE and
# contains no needle of its own; anything unrecognized falls back to a digest,
# which is safe by construction.
_REDACTION_RULE_IDS: Dict[str, str] = {
    "://": "URL_SCHEME",
    "websocket_url": "WEBSOCKET_ADDRESS",
    "http_url": "HTTP_ADDRESS",
    "authorization_header": "AUTH_HEADER_CREDENTIAL",
    "telegram_bot_token": "DELIVERY_BOT_CREDENTIAL",
    "helius-rpc": "PROVIDER_HOST_IDENTITY",
    "helius.dev": "PROVIDER_HOST_IDENTITY",
    "atlas-mainnet": "PROVIDER_HOST_IDENTITY",
    "api-key": "API_CREDENTIAL_PARAMETER",
    "api_key": "API_CREDENTIAL_PARAMETER",
    "apikey": "API_CREDENTIAL_PARAMETER",
    "x-api-key": "API_CREDENTIAL_PARAMETER",
    "x-token": "API_CREDENTIAL_PARAMETER",
    "bearer": "AUTH_SCHEME_CREDENTIAL",
    "/webhooks/": "DELIVERY_HOOK_IDENTITY",
    "discord.com": "DELIVERY_HOST_IDENTITY",
    "discordapp": "DELIVERY_HOST_IDENTITY",
    "api.telegram.org": "DELIVERY_HOST_IDENTITY",
    "chainstack": "PROVIDER_PRODUCT_NAME",
    "birdeye": "PROVIDER_PRODUCT_NAME",
    "dexscreener": "PROVIDER_PRODUCT_NAME",
    "raw_body": "RAW_RESPONSE_CONTENT",
    "response_body": "RAW_RESPONSE_CONTENT",
    "raw_response_body": "RAW_RESPONSE_CONTENT",
}

#: Every identifier the table can produce.  A test asserts each is scanner-safe.
REDACTION_RULE_IDS: Tuple[str, ...] = tuple(
    sorted(set(_REDACTION_RULE_IDS.values())))


def redaction_rule_id(hit: object) -> str:
    """One artifact-safe identifier for a scanner hit.

    Exact match first, then substring (the scanner reports both category names
    and raw needles), then a digest fallback so an identifier this table has
    never seen still cannot carry the needle it describes.
    """

    key = str(hit or "").strip().lower()
    if not key:
        return "UNCLASSIFIED_RULE"
    mapped = _REDACTION_RULE_IDS.get(key)
    if mapped is not None:
        return mapped
    for needle, rule in _REDACTION_RULE_IDS.items():
        if needle in key:
            return rule
    import hashlib

    return "RULE_" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:12]


def withholding_telemetry(
    *,
    field: str,
    rule_ids: Any,
    replacement: str = SOURCE_ROLE_WITHHELD_UNSAFE,
) -> Dict[str, Any]:
    """Disclosure record for one withheld value: RULES only, never the value.

    Before this existed an artifact said only ``WITHHELD_UNSAFE`` and an
    operator had no way to learn which rule fired without re-deriving the
    unsafe value by hand.  Now the record names the rules -- translated through
    :func:`redaction_rule_id`, so the disclosure itself is scanner-safe -- and
    states explicitly that the value was not recorded.
    """

    safe_rules: list = []
    for item in (rule_ids or ()):
        rule = redaction_rule_id(item)
        if rule not in safe_rules:
            safe_rules.append(rule)
    # The field NAME is caller-supplied, so it is sanitized the same way: a
    # name that happens to contain a needle is replaced by its rule id.
    field_name = str(field)[:64]
    lowered = field_name.lower()
    if any(needle in lowered for needle in _REDACTION_RULE_IDS):
        field_name = redaction_rule_id(field_name)
    return {
        "redaction": "WITHHELD_UNSAFE",
        "withheld_field": field_name,
        "redaction_rule_ids": safe_rules[:16],
        "redaction_rule_count": len(safe_rules),
        "replacement_label": str(replacement),
        # Stated explicitly so nobody later "fixes" the missing value.
        "value_recorded": False,
    }


def sanitize_source_labels(
    payload: Mapping[str, Any],
    *,
    fields: Any = (
        "source_label", "ath_source", "price_source", "market_cap_source",
        "liquidity_source", "activation_observation_source",
        "observation_source", "market_price_source", "market_provider",
    ),
    scan_fn: Optional[Any] = None,
) -> Dict[str, Any]:
    """Return ``payload`` with every known source-label field made safe."""

    if not isinstance(payload, Mapping):
        return {}
    out = dict(payload)
    for field in fields or ():
        if field not in out:
            continue
        out[field] = artifact_safe_source_label(out[field], scan_fn=scan_fn)
    return out


__all__ = (
    "ARTIFACT_SAFE_SOURCE_LABELS",
    "REDACTION_RULE_IDS",
    "redaction_rule_id",
    "SOURCE_ROLE_CANONICAL_RESERVES",
    "SOURCE_ROLE_CURATED_SAFETY_NET",
    "SOURCE_ROLE_EXACT_GAP_RECOVERY",
    "SOURCE_ROLE_LIVE_MIGRATION_PRIMARY",
    "SOURCE_ROLE_NON_PAID_PRIMARY",
    "SOURCE_ROLE_PAID_MARKET_OHLCV",
    "SOURCE_ROLE_PAID_MARKET_PRIMARY",
    "SOURCE_ROLE_PAID_MARKET_SPOT_PRICE",
    "SOURCE_ROLE_UNAVAILABLE",
    "SOURCE_ROLE_WITHHELD_UNSAFE",
    "artifact_safe_source_label",
    "is_artifact_safe_source_label",
    "sanitize_source_labels",
    "withholding_telemetry",
)

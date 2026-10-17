"""Paper-side risk contract: labels, skip categories, and tolerant parsers.

The free-tier producer tags its candidate/would-ping/pricing artifacts with a lightweight
scam/bundle risk assessment (``risk_label`` + ``risk_reasons`` — closed-set string tokens).
This module is the paper engine's side of that contract:

* validated label constants (RISK_LOW / RISK_MEDIUM / RISK_HIGH / RISK_UNKNOWN),
* the closed-set HIGH-risk paper skip categories the engine records when it refuses an entry,
* tolerant parsers for artifact fields (unknown/malformed values collapse to ``None`` / ``[]``,
  never to RISK_HIGH — absence of data must never be treated as danger).

Honesty note: the producer cannot see holder / bundler account distribution on the free tier,
so a missing label means UNKNOWN. UNKNOWN does not block entries by default; only RISK_HIGH
does (and only for strategies that did not opt into high risk).
"""

from __future__ import annotations

from typing import Any, List, Optional

RISK_LOW = "RISK_LOW"
RISK_MEDIUM = "RISK_MEDIUM"
RISK_HIGH = "RISK_HIGH"
RISK_UNKNOWN = "RISK_UNKNOWN"
RISK_LABELS = (RISK_LOW, RISK_MEDIUM, RISK_HIGH, RISK_UNKNOWN)

# Closed-set skip categories recorded on a SKIPPED_HIGH_RISK position (reason_closed).
SKIP_HIGH_RISK_SCAM_BUNDLE = "HIGH_RISK_SCAM_BUNDLE"
SKIP_HIGH_RISK_LIQUIDITY_COLLAPSE = "HIGH_RISK_LIQUIDITY_COLLAPSE"
SKIP_HIGH_RISK_MARKET_STALE = "HIGH_RISK_MARKET_STALE"
SKIP_HIGH_RISK_TOO_HOT = "HIGH_RISK_TOO_HOT"
HIGH_RISK_SKIP_REASONS = (
    SKIP_HIGH_RISK_SCAM_BUNDLE,
    SKIP_HIGH_RISK_LIQUIDITY_COLLAPSE,
    SKIP_HIGH_RISK_MARKET_STALE,
    SKIP_HIGH_RISK_TOO_HOT,
)

# Producer reason tokens this module understands for categorization (a superset is fine —
# unknown tokens fall into the SCAM_BUNDLE catch-all category).
_LIQUIDITY_REASONS = frozenset({"LIQUIDITY_COLLAPSE", "LP_CRITICALLY_LOW"})
_TOO_HOT_REASONS = frozenset({"POOL_TOO_HOT", "POOL_HOT_EARLY_ACTIVITY"})
_MARKET_STALE_REASONS = frozenset({
    "MARKET_UNAVAILABLE_PERSISTENT", "MARKET_STALE", "MARKET_REFRESH_FAILING",
    "MARKET_INCOMPLETE_REPEATED",
})

# Market-quality reason tokens a conservative strategy treats as "market not fresh/strong".
MARKET_QUALITY_REASONS = frozenset(_MARKET_STALE_REASONS | {"LP_MISSING"})

# Engine-added reason when the paper book itself already watched this mint rug.
REASON_PAPER_RUG_HISTORY = "PAPER_RUG_HISTORY"


def parse_risk_label(value: Any) -> Optional[str]:
    """Validated risk label from an artifact field; anything else -> None (== UNKNOWN).
    Malformed input NEVER becomes RISK_HIGH."""
    if isinstance(value, str) and value.strip().upper() in RISK_LABELS:
        return value.strip().upper()
    return None


def parse_risk_reasons(value: Any) -> List[str]:
    """Tolerant list-of-token parse (strings only, bounded, order-preserving de-dupe)."""
    if not isinstance(value, (list, tuple)):
        return []
    out: List[str] = []
    seen = set()
    for item in value:
        if isinstance(item, str) and item.strip():
            token = item.strip()
            if token not in seen:
                seen.add(token)
                out.append(token)
        if len(out) >= 8:
            break
    return out


def high_risk_skip_reason(reasons: Any) -> str:
    """Map a HIGH assessment's reason tokens to the closed-set paper skip category.
    Priority: liquidity collapse > too-hot > market stale > scam/bundle catch-all."""
    tokens = set(parse_risk_reasons(reasons))
    if tokens & _LIQUIDITY_REASONS:
        return SKIP_HIGH_RISK_LIQUIDITY_COLLAPSE
    if tokens & _TOO_HOT_REASONS:
        return SKIP_HIGH_RISK_TOO_HOT
    if tokens & _MARKET_STALE_REASONS:
        return SKIP_HIGH_RISK_MARKET_STALE
    return SKIP_HIGH_RISK_SCAM_BUNDLE


__all__ = [
    "RISK_LOW",
    "RISK_MEDIUM",
    "RISK_HIGH",
    "RISK_UNKNOWN",
    "RISK_LABELS",
    "SKIP_HIGH_RISK_SCAM_BUNDLE",
    "SKIP_HIGH_RISK_LIQUIDITY_COLLAPSE",
    "SKIP_HIGH_RISK_MARKET_STALE",
    "SKIP_HIGH_RISK_TOO_HOT",
    "HIGH_RISK_SKIP_REASONS",
    "MARKET_QUALITY_REASONS",
    "REASON_PAPER_RUG_HISTORY",
    "parse_risk_label",
    "parse_risk_reasons",
    "high_risk_skip_reason",
]

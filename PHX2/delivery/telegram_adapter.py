"""Bind the final Telegram ping to PHX2's centralized delivery evidence."""

from __future__ import annotations

from .telegram_presentation import compose_discovery_alert

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import hashlib
import unicodedata
from typing import Any, Callable, Dict, Mapping, Optional, Tuple

from .global_fee_support import (
    FEE_SUPPORT_MANIPULATED,
    FEE_SUPPORT_TELEGRAM_LABEL_MANIPULATED,
    evaluate_global_fee_support,
)
from .telegram_composer import (
    FIELD_UNAVAILABLE_DISPLAY,
    BuilderReadStatement,
    TelegramComposeResult,
    TelegramMessageTooLong,
    TelegramPingData,
    compose_telegram_ping,
)
from .telegram_transport import (
    MESSAGE_REJECTED,
    MESSAGE_TOO_LONG,
    SENT_OK,
    TelegramTransport,
    TelegramTransportResult,
)


UNKNOWN_ANTE_REASON = "FEE_EVIDENCE_UNAVAILABLE"
UNKNOWN_PARTICIPATION_PACE_REASON = "PARTICIPATION_OBSERVATION_WINDOW_UNAVAILABLE"
BUILDER_NO_RULE_REASON = "NO_APPROVED_BUILDER_READ_RULE_MATCHED"
RISK_ASSESSMENT_UNAVAILABLE_REASON = "RISK_ASSESSMENT_UNAVAILABLE"
MESSAGE_LENGTH_LIMIT_EXCEEDED = "MESSAGE_LENGTH_LIMIT_EXCEEDED"
VOLUME_INSUFFICIENT_REASON = "CANONICAL_SWAP_SAMPLE_INSUFFICIENT"
VOLUME_INVALID_REASON = "CANONICAL_VOLUME_EVIDENCE_INVALID"
#: Artifact-only reason prefix for an omitted Global Fees line; the suffix is
#: the closed-set canonical status (e.g. ``GLOBAL_FEES_STALE``).
GLOBAL_FEES_REASON_PREFIX = "GLOBAL_FEES_"
GLOBAL_FEES_DISPLAY_MAX_AGE_SECONDS = 300
GLOBAL_FEES_MAX_FUTURE_SKEW_SECONDS = 5
LIQUIDITY_DATA_UNAVAILABLE_REASON = "FRESH_MATCHING_ACTUAL_RESERVES_UNAVAILABLE"
LIQUIDITY_QUALITY_NOT_SCORED_REASON = (
    "NO_APPROVED_LIQUIDITY_QUALITY_RULE")
ANTE_SHAPE_NO_RULE_REASON = "NO_APPROVED_ANTE_SHAPE_RULE"
ANTE_SHAPE_INSUFFICIENT_REASON = "ANTE_SHAPE_SAMPLE_INSUFFICIENT"
CENTRAL_ATH_UNAVAILABLE_REASON = "CENTRAL_ATH_UNAVAILABLE"
MIGRATION_MC_UNAVAILABLE_REASON = "IMMUTABLE_MIGRATION_MC_UNAVAILABLE"
ATH_FLOOR_UNAVAILABLE_REASON = "ATH_FLOOR_UNAVAILABLE"
#: Artifact-only reason when the PHX1 fee evidence window is missing, stale,
#: malformed, or insufficient — the affected Telegram metrics are withheld
#: (never rendered as authentic zeroes).
FEE_EVIDENCE_INVALID_REASON = "FEE_GATE_EVIDENCE_UNAVAILABLE"
STRUCTURE_READ_UNAVAILABLE_REASON = "STRUCTURE_READ_UNAVAILABLE"
ACTUAL_LIQUIDITY_MAX_AGE_SECONDS = 300
QUOTE_PRICE_MAX_SKEW_SECONDS = 30

TOKEN_METADATA_CANONICAL_LIVE = "CANONICAL_LIVE_METADATA"
TOKEN_METADATA_DEX_BACKFILL = "DEXSCREENER_RESTART_BACKFILL"
TOKEN_METADATA_VALIDATED_CACHE = "VALIDATED_METADATA_CACHE"
TOKEN_METADATA_UNAVAILABLE = "TOKEN_METADATA_UNAVAILABLE"
# Centralized closed-set provenance contract: LIVE_YELLOWSTONE and LIVE_HELIUS
# are equal-authority live provenances at the delivery boundary.
from PHX2.models.discovery_provenance import (  # noqa: E402
    LIVE_DISCOVERY_PROVENANCES,
    DISCOVERY_PROVENANCE_DEX_BACKFILL as DEX_BACKFILL_PROVENANCE,
    DISCOVERY_PROVENANCE_LIVE_HELIUS as HELIUS_DISCOVERY_PROVENANCE,
    DISCOVERY_PROVENANCE_LIVE_YELLOWSTONE as LIVE_DISCOVERY_PROVENANCE,
)
from PHX2.models.ath_coverage import (  # noqa: E402
    ATH_COVERAGE_PARTIAL_SINCE_ADMISSION,
    ATH_COVERAGE_UNKNOWN,
    ath_coverage_is_complete as _ath_coverage_is_complete,
    classify_ath_coverage,
)
from PHX2.free_tier_producer.phx1_parity_policy import (  # noqa: E402
    STATUS_COMPLETE as _PARITY_STATUS_COMPLETE,
    STATUS_FRESH as _PARITY_STATUS_FRESH,
    STATUS_INCOMPLETE as _PARITY_STATUS_INCOMPLETE,
    STATUS_NOT_PROVEN as _PARITY_STATUS_NOT_PROVEN,
    STATUS_PROVEN as _PARITY_STATUS_PROVEN,
    STATUS_STALE as _PARITY_STATUS_STALE,
    current_alert_policy as _current_alert_policy,
    observability_matrix as _observability_matrix,
)
TOKEN_NAME_MAX_CHARACTERS = 64
TOKEN_TICKER_MAX_CHARACTERS = 16
UNKNOWN_TOKEN_DISPLAY = "Unknown Token"

#: Risk reasons that are internal repeat-diagnostics, never operator wording.
#: They stay intact in the compose artifact's source proofs and in the risk
#: engine's own artifacts; only the Telegram risk line filters them.
RISK_REASONS_INTERNAL_ONLY = frozenset({"MARKET_INCOMPLETE_REPEATED"})

#: Operator display for the risk classification labels; raw ``RISK_*`` enums
#: never render.
RISK_LABEL_TELEGRAM_DISPLAY = {
    "RISK_LOW": "Low",
    "RISK_MEDIUM": "Medium",
    "RISK_HIGH": "High",
}

#: Telegram display phrases for genuine risk reasons (mirrors the approved
#: closed set in ``free_tier_risk._REASON_DISPLAY``; no new classification).
#: A reason outside this map is internal/unapproved and stays artifact-only.
RISK_REASON_TELEGRAM_DISPLAY = {
    "LIQUIDITY_COLLAPSE": "liquidity collapse",
    "LP_CRITICALLY_LOW": "LP critically low",
    "PRICE_SPIKE_DUMP": "spike-dump",
    "EARLY_EXTREME_DRAWDOWN": "early extreme drawdown",
    "MARKET_UNAVAILABLE_PERSISTENT": "market unavailable",
    "POOL_TOO_HOT": "too-hot pool",
    "LP_THIN": "thin LP",
    "LP_FALLING": "LP falling",
    "LP_MISSING": "LP missing",
    "MARKET_STALE": "market stale",
    "MARKET_REFRESH_FAILING": "market refresh failing",
    "EARLY_VOLATILITY": "early volatility",
    "POOL_HOT_EARLY_ACTIVITY": "hot early activity",
    "NO_MARKET_DATA": "insufficient data",
}

#: Concise operator phrases for the compact SHADOW BLOCK policy line, keyed by
#: the approved structured shadow reason tokens (closed set from
#: ``phx1_structural_policy.SHADOWABLE_STRUCTURAL_REASON_TOKENS``).  Order is
#: the display priority when several reasons are present.
SHADOW_REASON_TELEGRAM_DISPLAY = (
    ("PHX2_FEE_LIFECYCLE_DURABLE_SCAM_LOCK", "durable scam lock"),
    ("PHX1_FEE_GATE_SCAM_LIKELY", "fee gate scam likely"),
    ("PHX1_GHOST_BLOCK", "ghost filter block"),
    ("PHX2_FEE_LIFECYCLE_IMMATURE", "fee lifecycle immature"),
    ("PHX2_FEE_LIFECYCLE_PROVISIONAL", "fee lifecycle provisional"),
    ("PHX2_FEE_LIFECYCLE_TEMPORARILY_STALE", "fee lifecycle stale"),
    ("PHX1_FEE_GATE_DATA_STALE", "fee data stale"),
    ("PHX1_FEE_GATE_INSUFFICIENT_SAMPLE", "fee gate sample insufficient"),
    ("PHX1_FEE_GATE_PROOF_MISSING", "fee gate proof missing"),
    ("PHX1_FEE_GATE_PAIR_UNCALIBRATED", "fee gate pair uncalibrated"),
    ("PHX1_FEE_GATE_NO_DATA", "fee gate no data"),
)

#: Operator display for the closed PHX1 fee-gate labels; anything outside
#: this map (including ``UNKNOWN``) withholds the Fee Gate value.
FEE_GATE_LABEL_TELEGRAM_DISPLAY = {
    "Normal": "Normal",
    "Elevated": "Elevated",
    "Suspicious": "Suspicious",
    "SCAM Likely": "Scam Likely",
}

#: Approved operator phrases for the Structure ``Read`` line, keyed by the
#: lower-cased structure-read source token.  An unmapped token stays
#: artifact-only and the line is omitted.
STRUCTURE_READ_TELEGRAM_DISPLAY = {
    "sticky_lock": "sticky lock",
    "balanced_fees": "balanced fees",
    "thin_sample": "thin sample",
    "bribes_starved": "bribes starved",
    "bribes_low": "bribes low",
    "creator_dom_hi": "creator dominance high",
    "insufficient_data": "insufficient data",
    "phx1_fee_gate_scam_likely": "scam likely",
    "phx1_fee_gate_data_invalid": "fee data invalid",
    "phx1_fee_gate_data_stale": "fee data stale",
    "phx1_fee_gate_insufficient_sample": "fee sample insufficient",
    "phx1_fee_gate_proof_missing": "fee proof missing",
    "phx1_fee_gate_proof_inconsistent": "fee proof inconsistent",
    "phx1_fee_gate_pair_uncalibrated": "pair uncalibrated",
}


def _decimal(value: object) -> Optional[Decimal]:
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return parsed if parsed.is_finite() else None


def _trim(value: Decimal, places: int = 2) -> str:
    quantum = Decimal(1).scaleb(-places)
    text = format(value.quantize(quantum, rounding=ROUND_HALF_UP), "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def _fixed(value: object, places: int) -> Optional[str]:
    """Fixed-point text, or ``None`` when the value is unavailable — the
    internal reason travels through ``field_reason_codes`` only, never
    through a rendered fallback string."""

    parsed = _decimal(value)
    if parsed is None:
        return None
    return format(parsed.quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP), "f")


def _compact_usd(value: object) -> Optional[str]:
    parsed = _decimal(value)
    if parsed is None or parsed < 0:
        return None
    if parsed >= Decimal("1000000"):
        return f"${_trim(parsed / Decimal('1000000'), 1)}m"
    if parsed >= Decimal("1000"):
        return f"${_trim(parsed / Decimal('1000'), 1)}k"
    return f"${_trim(parsed, 0)}"


def _compact_signed_usd(value: object) -> Optional[str]:
    parsed = _decimal(value)
    if parsed is None:
        return None
    sign = "+" if parsed > 0 else ("-" if parsed < 0 else "")
    unsigned = _compact_usd(abs(parsed))
    return None if unsigned is None else sign + unsigned


def _percent(value: object, *, fraction: bool = False) -> Optional[str]:
    parsed = _decimal(value)
    if parsed is None:
        return None
    if fraction:
        parsed *= Decimal(100)
    return f"{_trim(parsed, 1)}%"


def _integer(value: object, *, commas: bool = False) -> Optional[str]:
    parsed = _decimal(value)
    if parsed is None:
        return None
    integer = int(parsed.quantize(Decimal(1), rounding=ROUND_HALF_UP))
    return f"{integer:,}" if commas else str(integer)


def _parse_utc(value: object) -> Optional[datetime]:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def _raw_text(value: object) -> Optional[str]:
    """Loss-free artifact projection of one raw telemetry value."""

    return None if value is None else str(value)


def _canonical_volume_display(
    candidate: Mapping[str, Any], mint: str
) -> Tuple[str, Optional[Mapping[str, Any]], Optional[str]]:
    """Operator display for canonical 5m volume.

    Unavailable or invalid canonical evidence renders ``—``; the exact internal
    reason travels only through the returned reason code (artifact surface).
    """

    snapshot = candidate.get("canonical_volume_5m")
    if not isinstance(snapshot, Mapping) or snapshot.get("mint") != mint:
        return (
            FIELD_UNAVAILABLE_DISPLAY,
            None,
            VOLUME_INSUFFICIENT_REASON,
        )
    if snapshot.get("status") == "INSUFFICIENT_DATA":
        return (
            FIELD_UNAVAILABLE_DISPLAY,
            snapshot,
            VOLUME_INSUFFICIENT_REASON,
        )
    gross = _decimal(snapshot.get("gross_volume_usd"))
    net = _compact_signed_usd(snapshot.get("net_quote_flow_usd"))
    samples = snapshot.get("sample_count")
    gross_display = _compact_usd(gross)
    if not (
        snapshot.get("status") == "VALID"
        and snapshot.get("observe_only") is True
        and snapshot.get("window_seconds") == 300
        and gross is not None and gross >= 0
        and gross_display is not None
        and net is not None
        and isinstance(samples, int) and not isinstance(samples, bool)
        and samples > 0
    ):
        return FIELD_UNAVAILABLE_DISPLAY, snapshot, VOLUME_INVALID_REASON
    return (
        f"{gross_display} gross | {net} net (n={samples})",
        snapshot,
        None,
    )


def _compact_sol(value: Decimal) -> str:
    """Compact SOL amount: plain decimal notation only, no stray precision.

    ``0.004`` / ``0.12`` / ``1.8`` / ``14.8`` / ``125`` / ``1,240`` — two
    significant digits below 1, one decimal place from 1 to 100, whole
    comma-grouped numbers beyond.
    """

    if value >= Decimal("100"):
        integer = int(value.quantize(Decimal(1), rounding=ROUND_HALF_UP))
        return f"{integer:,}"
    if value >= 1:
        return _trim(value, 1)
    if value == 0:
        return "0"
    quantum = Decimal(1).scaleb(value.adjusted() - 1)
    text = format(value.quantize(quantum, rounding=ROUND_HALF_UP), "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def _global_fees_display(
    candidate: Mapping[str, Any], mint: str, now_utc: str
) -> Tuple[str, Optional[Mapping[str, Any]], Optional[str]]:
    """Operator display for observe-only all-time Global Fees (SOL).

    Renders ONLY a canonical snapshot that is exact-mint bound, status
    ``VALID``, value-revalidated, and display-fresh at compose time; every
    other state returns an empty display (the line is omitted entirely) with
    the closed-set reason on the artifact surface.  Never fetches.
    """

    snapshot = candidate.get("global_fees")
    if not isinstance(snapshot, Mapping) or snapshot.get(
            "token_mint") != mint:
        return "", None, GLOBAL_FEES_REASON_PREFIX + "NOT_REQUESTED"
    status = snapshot.get("global_fees_status")
    if not isinstance(status, str) or not status.strip():
        return "", snapshot, GLOBAL_FEES_REASON_PREFIX + "NOT_REQUESTED"
    if status != "VALID":
        return "", snapshot, GLOBAL_FEES_REASON_PREFIX + status
    if snapshot.get("global_fees_interval") != "alltime":
        return "", snapshot, GLOBAL_FEES_REASON_PREFIX + "VALUE_INVALID"
    value = _decimal(snapshot.get("global_fees_paid_sol"))
    if value is None or value < 0:
        return "", snapshot, GLOBAL_FEES_REASON_PREFIX + "VALUE_INVALID"
    observed = _parse_utc(snapshot.get("global_fees_observed_at_utc"))
    now = _parse_utc(now_utc)
    if observed is None or now is None or not (
            -GLOBAL_FEES_MAX_FUTURE_SKEW_SECONDS
            <= (now - observed).total_seconds()
            <= GLOBAL_FEES_DISPLAY_MAX_AGE_SECONDS):
        # Display-only fail-closed staleness re-check bound to the compose
        # timestamp itself (a stored snapshot may have been stamped earlier).
        return "", snapshot, GLOBAL_FEES_REASON_PREFIX + "STALE"
    return f"{_compact_sol(value)} SOL", snapshot, None


def _actual_liquidity_display(
    *,
    mint: str,
    candidate: Mapping[str, Any],
    market: Mapping[str, Any],
    now_utc: str,
) -> Tuple[str, str, str, Optional[Decimal], Optional[str]]:
    """Verify and format actual vault TVL; virtual reserves never enter it."""

    reserve = market.get("pumpswap_reserve")
    reserve = reserve if isinstance(reserve, Mapping) else {}
    artifact = reserve.get("reserve_artifact")
    artifact = artifact if isinstance(artifact, Mapping) else {}
    observed = _parse_utc(artifact.get("observation_timestamp"))
    quote_observed = _parse_utc(reserve.get("quote_price_observed_at_utc"))
    now = _parse_utc(now_utc)
    candidate_pair = candidate.get("pair_address")
    pair_matches = (
        not isinstance(candidate_pair, str)
        or not candidate_pair
        or artifact.get("pool_address") == candidate_pair)
    try:
        raw_quote = int(str(artifact.get("raw_quote_reserves")))
        virtual_quote = int(str(artifact.get("virtual_quote_reserves")))
        effective_quote = int(str(artifact.get("effective_quote_reserves")))
        base_reserves = int(str(artifact.get("base_reserves")))
        quote_decimals = int(artifact.get("quote_decimals"))
        base_decimals = int(artifact.get("base_decimals"))
    except (TypeError, ValueError):
        raw_quote = virtual_quote = effective_quote = base_reserves = -1
        quote_decimals = base_decimals = -1
    quote_price = _decimal(reserve.get("quote_price_usd"))
    base_price = _decimal(market.get("current_price"))
    stated_quote = _decimal(reserve.get("actual_quote_liquidity_usd"))
    stated_token = _decimal(reserve.get("actual_token_liquidity_usd"))
    stated_total = _decimal(reserve.get("actual_pool_tvl_usd"))
    timestamp_ok = bool(
        observed is not None and quote_observed is not None and now is not None
        and -5 <= (now - observed).total_seconds()
        <= ACTUAL_LIQUIDITY_MAX_AGE_SECONDS
        and abs((quote_observed - observed).total_seconds())
        <= QUOTE_PRICE_MAX_SKEW_SECONDS)
    identity_ok = bool(
        reserve.get("reserve_validation_status") == "VALID"
        and artifact.get("base_mint") == mint
        and pair_matches)
    definition_ok = bool(
        reserve.get("actual_liquidity_definition")
        == "REAL_QUOTE_VAULT_PLUS_REAL_BASE_VAULT_AT_ACCEPTED_CURRENT_PRICE"
        and reserve.get("quote_side_liquidity_definition")
        == "REAL_QUOTE_VAULT_ONLY")
    numeric_ok = bool(
        raw_quote >= 0 and base_reserves > 0
        and 0 <= quote_decimals <= 255 and 0 <= base_decimals <= 255
        and raw_quote + virtual_quote == effective_quote
        and quote_price is not None and quote_price > 0
        and base_price is not None and base_price > 0
        and stated_quote is not None and stated_token is not None
        and stated_total is not None)
    if numeric_ok:
        calculated_quote = (
            Decimal(raw_quote) / (Decimal(10) ** quote_decimals)
        ) * quote_price
        calculated_token = (
            Decimal(base_reserves) / (Decimal(10) ** base_decimals)
        ) * base_price
        numeric_ok = bool(
            calculated_quote == stated_quote
            and calculated_token == stated_token
            and stated_quote + stated_token == stated_total)
    total_display = _compact_usd(stated_total)
    quote_display = _compact_usd(stated_quote)
    if not (timestamp_ok and identity_ok and definition_ok and numeric_ok
            and total_display is not None and quote_display is not None):
        # The internal reason code travels only through the artifact surface;
        # the operator body renders the unavailable marker.
        return (
            FIELD_UNAVAILABLE_DISPLAY,
            FIELD_UNAVAILABLE_DISPLAY,
            "UNAVAILABLE",
            None,
            LIQUIDITY_DATA_UNAVAILABLE_REASON,
        )
    return (
        total_display,
        quote_display,
        "TOTAL_ACTUAL_POOL_TVL",
        stated_total,
        None,
    )


def _age_minutes(migration_time: object, now_utc: object) -> Optional[int]:
    migration = _parse_utc(migration_time)
    now = _parse_utc(now_utc)
    if migration is None or now is None or now < migration:
        return None
    return int((now - migration).total_seconds() // 60)


def _token_age_seconds(migration_time: object, now_utc: object) -> Optional[float]:
    migration = _parse_utc(migration_time)
    now = _parse_utc(now_utc)
    if migration is None or now is None or now < migration:
        return None
    return round((now - migration).total_seconds(), 3)


def format_age_minutes(age_minutes: int) -> str:
    """Unambiguous compact age; lowercase ``m`` always means minutes."""

    if isinstance(age_minutes, bool) or not isinstance(age_minutes, int) \
            or age_minutes < 0:
        raise ValueError("AGE_MINUTES_INVALID")
    days, day_remainder = divmod(age_minutes, 24 * 60)
    hours, minutes = divmod(day_remainder, 60)
    parts = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if minutes or not parts:
        parts.append(f"{minutes}m")
    return " ".join(parts)


def _sanitize_metadata(value: object, *, limit: int) -> Optional[str]:
    if not isinstance(value, str):
        return None
    normalized = unicodedata.normalize("NFC", value)
    without_controls = "".join(
        char for char in normalized
        if not unicodedata.category(char).startswith("C"))
    safe = " ".join(without_controls.split()).strip()
    if not safe or safe.upper() in ("???", "UNKNOWN", "N/A", "NULL"):
        return None
    bounded = safe[:max(1, int(limit))].strip()
    return bounded or None


def _metadata_identity(
    entry: Mapping[str, Any],
    *,
    source: str,
) -> Tuple[str, str]:
    name = _sanitize_metadata(
        entry.get("token_name", entry.get("name")),
        limit=TOKEN_NAME_MAX_CHARACTERS,
    )
    ticker = _sanitize_metadata(
        entry.get(
            "token_symbol",
            entry.get("symbol", entry.get("ticker", entry.get("symbol_or_name")))),
        limit=TOKEN_TICKER_MAX_CHARACTERS,
    )
    if name is not None and ticker == name:
        # Dexscreener's accepted adapter uses ``symbol_or_name`` as an explicit
        # fallback when no symbol exists.  Do not present the name as a ticker.
        ticker = None
    if ticker is not None:
        ticker = ticker.lstrip("$").strip() or None
    if name and ticker:
        return f"{name} (${ticker})", source
    if ticker:
        return f"${ticker}", source
    if name:
        return name, source
    return UNKNOWN_TOKEN_DISPLAY, TOKEN_METADATA_UNAVAILABLE


def _entry_matches_mint(entry: object, mint: str) -> bool:
    if not isinstance(entry, Mapping):
        return False
    entry_mint = entry.get("token_mint", entry.get("mint"))
    return isinstance(entry_mint, str) and entry_mint == mint


def resolve_token_identity(
    *,
    mint: str,
    candidate: Mapping[str, Any],
    delivery_context: Mapping[str, Any],
) -> Tuple[str, str]:
    """Resolve already-held metadata without any send-time network request."""

    canonical = delivery_context.get("canonical_token_metadata")
    if not isinstance(canonical, Mapping):
        canonical = candidate.get("canonical_token_metadata")
    if _entry_matches_mint(canonical, mint) and (
        canonical.get("authenticated") is True
        or canonical.get("validated") is True
    ):
        identity, source = _metadata_identity(
            canonical, source=TOKEN_METADATA_CANONICAL_LIVE)
        if source != TOKEN_METADATA_UNAVAILABLE:
            return identity, source

    if candidate.get("discovery_provenance") in LIVE_DISCOVERY_PROVENANCES \
            and _entry_matches_mint(candidate, mint):
        identity, source = _metadata_identity(
            candidate, source=TOKEN_METADATA_CANONICAL_LIVE)
        if source != TOKEN_METADATA_UNAVAILABLE:
            return identity, source

    if candidate.get("discovery_provenance") == DEX_BACKFILL_PROVENANCE \
            and _entry_matches_mint(candidate, mint):
        identity, source = _metadata_identity(
            candidate, source=TOKEN_METADATA_DEX_BACKFILL)
        if source != TOKEN_METADATA_UNAVAILABLE:
            return identity, source

    cache = delivery_context.get("validated_metadata_cache")
    cache_entry: object = None
    if isinstance(cache, Mapping):
        cache_entry = cache.get(mint)
        if cache_entry is None and _entry_matches_mint(cache, mint):
            cache_entry = cache
    if _entry_matches_mint(cache_entry, mint) \
            and cache_entry.get("validated") is True:
        candidate_pair = candidate.get("pair_address")
        cache_pair = cache_entry.get("pair_address")
        pair_matches = (
            cache_pair is None
            or candidate_pair is None
            or cache_pair == candidate_pair)
        if pair_matches:
            identity, source = _metadata_identity(
                cache_entry, source=TOKEN_METADATA_VALIDATED_CACHE)
            if source != TOKEN_METADATA_UNAVAILABLE:
                return identity, source

    return UNKNOWN_TOKEN_DISPLAY, TOKEN_METADATA_UNAVAILABLE


def _tier_number(token: object) -> Optional[int]:
    text = str(token or "")
    if text in ("Tier 1", "Tier 2", "Tier 3"):
        return int(text[-1])
    return None


def _width(p25: object, p75: object) -> Optional[Decimal]:
    low = _decimal(p25)
    high = _decimal(p75)
    if low is None or high is None or low <= 0 or high < low:
        return None
    return high / low


def _floor(current: object, ath: object) -> Optional[Decimal]:
    current_value = _decimal(current)
    ath_value = _decimal(ath)
    if current_value is None or ath_value is None or current_value < 0 or ath_value <= 0:
        return None
    return ((current_value / ath_value) - Decimal(1)) * Decimal(100)


def _observation_minutes(first: object, last: object) -> Optional[Decimal]:
    start = _parse_utc(first)
    end = _parse_utc(last)
    if start is None or end is None or end <= start:
        return None
    return Decimal(str((end - start).total_seconds())) / Decimal(60)


def _fee_evidence_valid(fee: Any) -> bool:
    """True iff the PHX1 fee snapshot holds an authentic measured window.

    An unknown snapshot (missing/stale/malformed/insufficient evidence)
    carries synthetic zero totals, a ``None`` score, and no observation
    window; none of its values may render as authentic measurements.
    """

    score = getattr(fee, "fee_gate_score", None)
    if isinstance(score, bool) or not isinstance(score, int):
        return False
    event_count = getattr(fee, "event_count", None)
    if isinstance(event_count, bool) or not isinstance(event_count, int) \
            or event_count <= 0:
        return False
    if not getattr(fee, "first_observed_at_utc", None) \
            or not getattr(fee, "last_observed_at_utc", None):
        return False
    for category in (
        "missing_data_reasons", "stale_data_reasons",
        "malformed_data_reasons", "insufficient_sample_reasons",
    ):
        if tuple(getattr(fee, category, ()) or ()):
            return False
    return True


def _structure_read(fee: Any) -> Tuple[str, Optional[str]]:
    """``(operator_phrase, source_token)`` for the Structure ``Read`` line.

    Only approved phrases render; an unmapped or absent source token yields
    an empty display and stays artifact-only.
    """

    reasons = tuple(getattr(fee, "fee_gate_reasons", ()) or ())
    if "sticky_lock" in reasons:
        token = "sticky_lock"
    elif bool(getattr(fee, "balanced_fees", False)):
        token = "balanced_fees"
    elif reasons:
        token = str(reasons[0]).lower()
    else:
        return "", None
    return STRUCTURE_READ_TELEGRAM_DISPLAY.get(token, ""), token


def _risk_warning(value: object) -> str:
    """Operator-readable risk line; empty string means the line is omitted.

    Only genuine MEDIUM/HIGH classifications render, always as operator
    wording ("Medium — LP falling") — never the raw ``RISK_*`` enum.
    Internal repeat diagnostics (``RISK_REASONS_INTERNAL_ONLY``) and
    unapproved reason tokens stay artifact-only — the raw label and full
    reason list are preserved in the compose artifact's source proofs
    unchanged.  If every reason is internal, only the classification word
    renders.
    """

    risk = value if isinstance(value, Mapping) else {}
    label = risk.get("risk_label")
    if label not in ("RISK_MEDIUM", "RISK_HIGH"):
        return ""
    display_label = RISK_LABEL_TELEGRAM_DISPLAY[label]
    displayable = []
    for reason in (risk.get("risk_reasons") or ()):
        if not isinstance(reason, str) or not reason.strip():
            continue
        phrase = RISK_REASON_TELEGRAM_DISPLAY.get(reason.strip())
        if phrase is not None:
            displayable.append(phrase)
    if displayable:
        return f"{display_label} — " + ", ".join(displayable)
    return display_label


def _policy_reason_display(shadow_reasons: Tuple[str, ...]) -> str:
    """Pick the single concise phrase for the compact SHADOW BLOCK line."""

    present = {reason for reason in shadow_reasons if isinstance(reason, str)}
    for token, phrase in SHADOW_REASON_TELEGRAM_DISPLAY:
        if token in present:
            return phrase
    return "structural shadow block"


def _builder_read(
    *,
    fee: Any,
    lp: Any,
    liquidity: Optional[Decimal],
    floor: Optional[Decimal],
    shape_5m: str,
) -> Tuple[BuilderReadStatement, ...]:
    """Approved builder statements only; no placeholder sentence exists —
    an empty tuple omits the section and the no-match reason is recorded in
    ``field_reason_codes``."""

    statements = []
    fee_reasons = tuple(getattr(fee, "fee_gate_reasons", ()) or ())
    lp_reasons = tuple(getattr(lp, "lp_integrity_reasons", ()) or ())
    pace = _decimal(getattr(fee, "event_pace_per_minute", None))
    label = str(getattr(fee, "fee_gate_label", ""))

    if "sticky_lock" in fee_reasons:
        statements.append(BuilderReadStatement(
            "Late-sequence stress state", ("FEE_GATE_STICKY_LOCK",)))
    if pace is not None and pace >= Decimal("5") and label in (
        "Elevated", "Suspicious", "SCAM_LIKELY"
    ):
        statements.append(BuilderReadStatement(
            "Attention present, structure requires caution",
            ("EVENT_PACE_ATTENTION_PRESENT", f"FEE_GATE_{label.upper()}"),
        ))
    elif pace is not None and pace < Decimal("1"):
        statements.append(BuilderReadStatement(
            "Attention is weak", ("EVENT_PACE_ATTENTION_WEAK",)))
    if liquidity is not None and liquidity < Decimal("10000") \
            and floor is not None and floor <= Decimal("-70"):
        statements.append(BuilderReadStatement(
            "Pool is highly fragile, collapse risk is severe",
            ("LIQUIDITY_BELOW_10000", "ATH_DRAWDOWN_AT_LEAST_70_PERCENT"),
        ))
    elif liquidity is not None and liquidity < Decimal("10000"):
        statements.append(BuilderReadStatement(
            "Pool is highly fragile", ("LIQUIDITY_BELOW_10000",)))
    elif floor is not None and floor <= Decimal("-70"):
        statements.append(BuilderReadStatement(
            "Collapse risk is severe", ("ATH_DRAWDOWN_AT_LEAST_70_PERCENT",)))
    if "SECONDARY_POOL_OBSERVED" in lp_reasons:
        statements.append(BuilderReadStatement(
            "Secondary-pool concern is present", ("SECONDARY_POOL_OBSERVED",)))
    if "MULTIPLE_ADDS_NEAR_MIGRATION" in lp_reasons:
        statements.append(BuilderReadStatement(
            "Multiple liquidity adds occurred near migration",
            ("MULTIPLE_ADDS_NEAR_MIGRATION",)))
    if not statements and shape_5m == "ORGANIC":
        statements.append(BuilderReadStatement(
            "Payer structure reads organic", ("ANTE_SHAPE_5M_RULE_5",)))
    if not statements and shape_5m == "AMBIGUOUS":
        statements.append(BuilderReadStatement(
            "Payer structure remains ambiguous", ("ANTE_SHAPE_5M_RULE_6",)))
    return tuple(statements[:5])


def _add_reason(
    field_reasons: Dict[str, Tuple[str, ...]], key: str, *tokens: str
) -> None:
    existing = field_reasons.get(key, ())
    merged = existing + tuple(
        token for token in tokens if token not in existing)
    if merged:
        field_reasons[key] = merged


def _participation_artifact(
    fee: Any,
    *,
    participation_pace: Optional[Decimal],
    observation_minutes: Optional[Decimal],
    fee_evidence_valid: bool,
) -> Dict[str, Any]:
    """Full raw Participation telemetry for the compose artifact.

    Participation no longer renders in Telegram (presentation-only removal);
    every raw value, the observation window, and the evidence status stay
    here and in the sealed fee snapshot the source proofs reference.
    """

    return {
        "total_fees_sol": _raw_text(getattr(fee, "total_fees", None)),
        "lp_fees_sol": _raw_text(getattr(fee, "lp_fees", None)),
        "protocol_fees_sol": _raw_text(getattr(fee, "protocol_fees", None)),
        "creator_fees_sol": _raw_text(getattr(fee, "creator_fees", None)),
        "participation_pace_sol_per_minute": (
            None if participation_pace is None
            else format(participation_pace, "f")),
        "observation_window_minutes": (
            None if observation_minutes is None
            else format(observation_minutes, "f")),
        "event_pace_per_minute": _raw_text(
            getattr(fee, "event_pace_per_minute", None)),
        "event_count": getattr(fee, "event_count", None),
        "first_observed_at_utc": getattr(fee, "first_observed_at_utc", None),
        "last_observed_at_utc": getattr(fee, "last_observed_at_utc", None),
        "fee_evidence_valid": bool(fee_evidence_valid),
        "rendered_in_telegram": False,
    }


def _structure_evidence_artifact(
    fee: Any, *, fee_evidence_valid: bool
) -> Dict[str, Any]:
    """Raw Structure inputs the operator body now summarizes or withholds."""

    _read_display, read_token = _structure_read(fee)
    return {
        "fee_gate_label": _raw_text(getattr(fee, "fee_gate_label", None)),
        "fee_gate_score": getattr(fee, "fee_gate_score", None),
        "fee_gate_reasons": [
            str(reason)
            for reason in (getattr(fee, "fee_gate_reasons", ()) or ())],
        "fee_evidence_valid": bool(fee_evidence_valid),
        "bribe_share_pct": _raw_text(getattr(fee, "bribe_share_pct", None)),
        "creator_share": _raw_text(getattr(fee, "creator_share", None)),
        "bribes_per_transaction": _raw_text(
            getattr(fee, "bribes_per_transaction", None)),
        "structure_read_source": read_token,
    }


def build_ping_data(
    *,
    mint: str,
    composed_snapshot: Any,
    delivery_context: Mapping[str, Any],
    now_utc: str,
) -> TelegramPingData:
    candidate = delivery_context.get("candidate")
    candidate = candidate if isinstance(candidate, Mapping) else {}
    market = delivery_context.get("market_context")
    market = market if isinstance(market, Mapping) else {}
    risk_assessment = market.get("risk_assessment")
    activation = delivery_context.get("activation")
    activation = activation if isinstance(activation, Mapping) else {}
    security = delivery_context.get("security_decision")
    fee = getattr(security, "fee_snapshot", None)
    lp = getattr(security, "lp_snapshot", None)
    lp_mode = getattr(security, "lp_integrity_mode", None)
    lp_disabled = lp is None and lp_mode == "DISABLED_SINGLE_STREAM"
    if fee is None or (lp is None and not lp_disabled):
        raise ValueError("CENTRAL_SECURITY_SNAPSHOT_REQUIRED")
    if str(getattr(fee, "candidate_mint", "")) != mint \
            or (lp is not None and str(getattr(lp, "candidate_mint", "")) != mint):
        raise ValueError("CENTRAL_SECURITY_IDENTITY_MISMATCH")
    if str(getattr(composed_snapshot, "token_mint", "")) != mint:
        raise ValueError("CENTRAL_COMPOSE_IDENTITY_MISMATCH")

    tier = _tier_number(getattr(composed_snapshot, "tier_token", None))
    if tier is None:
        raise ValueError("CENTRAL_TIER_REQUIRED")
    age_minutes = _age_minutes(candidate.get("migration_time_utc"), now_utc)
    if age_minutes is None:
        raise ValueError("CENTRAL_MIGRATION_TIME_REQUIRED")
    token_identity, token_metadata_source = resolve_token_identity(
        mint=mint,
        candidate=candidate,
        delivery_context=delivery_context,
    )

    current_mc = market.get("current_market_cap_usd")
    snapshot_mc = _decimal(getattr(composed_snapshot, "current_market_cap_usd", None))
    if snapshot_mc is None or snapshot_mc != _decimal(current_mc):
        raise ValueError("CENTRAL_MARKET_CAP_MISMATCH")
    central_ath = market.get("central_ath")
    central_ath = central_ath if isinstance(central_ath, Mapping) else {}
    # The body must render the market cap OF the ATH price observation the
    # tier was computed on.  The raw ``ath_market_cap`` arm is maximized
    # independently of ``ath_price``, so rendering it beside a
    # price-derived tier is exactly the self-contradicting alert the
    # composer refuses to build.  Prefer the resolved observation; fall
    # back to the raw arm only for a record that carries no resolved tuple
    # (legacy/offline callers), never to "fix up" a resolved one.
    resolved_ath_mc = central_ath.get("resolved_ath_market_cap")
    ath_mc = (resolved_ath_mc if resolved_ath_mc is not None
              else central_ath.get("ath_market_cap"))
    migration_mc = activation.get("migration_market_cap_usd")
    (
        liquidity_display,
        quote_liquidity_display,
        liquidity_basis,
        liquidity_value,
        liquidity_reason,
    ) = _actual_liquidity_display(
        mint=mint,
        candidate=candidate,
        market=market,
        now_utc=now_utc,
    )
    floor_value = _floor(current_mc, ath_mc)
    fee_evidence_valid = _fee_evidence_valid(fee)
    fee_reason_tokens = tuple(
        str(reason)
        for reason in (getattr(fee, "fee_gate_reasons", ()) or ()))
    total = _decimal(getattr(fee, "total_fees", None))
    observation_minutes = _observation_minutes(
        getattr(fee, "first_observed_at_utc", None),
        getattr(fee, "last_observed_at_utc", None),
    )
    participation_pace = (
        total / observation_minutes
        if total is not None and observation_minutes is not None
        else None
    )

    field_reasons: Dict[str, Tuple[str, ...]] = {}
    if participation_pace is None:
        # Artifact-only: Participation never renders, but the pace telemetry
        # keeps its unavailability disclosure for review streams.
        _add_reason(field_reasons, "participation_pace",
                    UNKNOWN_PARTICIPATION_PACE_REASON)

    market_cap = _compact_usd(current_mc) or FIELD_UNAVAILABLE_DISPLAY
    post_migration_ath = _compact_usd(ath_mc)
    if post_migration_ath is None:
        post_migration_ath = FIELD_UNAVAILABLE_DISPLAY
        _add_reason(field_reasons, "post_migration_ath",
                    CENTRAL_ATH_UNAVAILABLE_REASON)
    migration_market_cap = _compact_usd(migration_mc)
    if migration_market_cap is None:
        migration_market_cap = FIELD_UNAVAILABLE_DISPLAY
        _add_reason(field_reasons, "migration_market_cap",
                    MIGRATION_MC_UNAVAILABLE_REASON)
    if floor_value is None:
        floor_display = FIELD_UNAVAILABLE_DISPLAY
        _add_reason(field_reasons, "floor", ATH_FLOOR_UNAVAILABLE_REASON)
    else:
        floor_display = f"{_trim(floor_value, 0)}%"

    volume, _volume_snapshot, volume_reason = _canonical_volume_display(
        candidate, mint)
    if volume_reason:
        _add_reason(field_reasons, "volume", volume_reason)
    global_fees_display, _global_fees_snapshot, global_fees_reason = (
        _global_fees_display(candidate, mint, now_utc))
    if global_fees_reason:
        _add_reason(field_reasons, "global_fees", global_fees_reason)
    # Observe-only Global Fee Support v1: same canonical inputs, pure Decimal
    # evaluation, no effect on eligibility or dispatch.  Only a conclusive
    # MANIPULATED result labels an already-rendered Global Fees line.
    fee_support = evaluate_global_fee_support(
        mint=mint,
        global_fees_snapshot=candidate.get("global_fees"),
        market_cap_usd=current_mc,
        market_cap_observed_at_utc=market.get("market_context_fetched_at_utc"),
        now_utc=now_utc,
        token_age_seconds=_token_age_seconds(
            candidate.get("migration_time_utc"), now_utc),
    )
    rendered_support_label: Optional[str] = None
    if global_fees_display \
            and fee_support.classification == FEE_SUPPORT_MANIPULATED:
        rendered_support_label = FEE_SUPPORT_TELEGRAM_LABEL_MANIPULATED
        global_fees_display = (
            f"{global_fees_display} ({rendered_support_label})")
    global_fee_support_artifact = fee_support.to_artifact(
        rendered_label=rendered_support_label,
        rendered_in_telegram=bool(global_fees_display),
    )
    if liquidity_reason:
        _add_reason(field_reasons, "liquidity", liquidity_reason)
        _add_reason(field_reasons, "quote_side_liquidity", liquidity_reason)
    quality = "NOT SCORED (NO APPROVED LIQUIDITY QUALITY RULE)"
    _add_reason(field_reasons, "liquidity_quality",
                LIQUIDITY_QUALITY_NOT_SCORED_REASON)
    risk_mapping = (risk_assessment
                    if isinstance(risk_assessment, Mapping) else {})
    if risk_mapping.get("risk_label") not in (
        "RISK_LOW", "RISK_MEDIUM", "RISK_HIGH", "RISK_UNKNOWN"
    ):
        _add_reason(field_reasons, "risk", RISK_ASSESSMENT_UNAVAILABLE_REASON)

    # ---- fee-evidence-gated Structure metrics --------------------------
    fee_gate_label = ""
    fee_gate_score = ""
    raw_label = getattr(fee, "fee_gate_label", None)
    label_display = FEE_GATE_LABEL_TELEGRAM_DISPLAY.get(
        raw_label if isinstance(raw_label, str) else "")
    score_display = _integer(getattr(fee, "fee_gate_score", None))
    if fee_evidence_valid and label_display and score_display is not None:
        fee_gate_label = label_display
        fee_gate_score = score_display
    else:
        _add_reason(field_reasons, "fee_gate",
                    *(fee_reason_tokens or (FEE_EVIDENCE_INVALID_REASON,)))

    bribes_amm_pct = ""
    creator_pct = ""
    bribes_per_tx_lamports = ""
    if fee_evidence_valid:
        bribes_per_tx = _decimal(getattr(fee, "bribes_per_transaction", None))
        bribes_lamports = (
            bribes_per_tx * Decimal("1000000000")
            if bribes_per_tx is not None else None)
        bribes_display = _percent(getattr(fee, "bribe_share_pct", None))
        creator_display = _percent(
            getattr(fee, "creator_share", None), fraction=True)
        lamports_display = _integer(bribes_lamports, commas=True)
        if bribes_display is not None and creator_display is not None \
                and lamports_display is not None:
            # One shared evidence window: the three shares render together
            # or not at all.
            bribes_amm_pct = bribes_display
            creator_pct = creator_display
            bribes_per_tx_lamports = lamports_display
        else:
            _add_reason(field_reasons, "fee_breakdown",
                        FEE_EVIDENCE_INVALID_REASON)
    else:
        _add_reason(field_reasons, "fee_breakdown",
                    *(fee_reason_tokens or (FEE_EVIDENCE_INVALID_REASON,)))

    structure_read, structure_read_token = _structure_read(fee)
    if not structure_read:
        _add_reason(
            field_reasons, "structure_read",
            structure_read_token or STRUCTURE_READ_UNAVAILABLE_REASON)

    # ---- Ante groups (observe-only) ------------------------------------
    ante_last20_median = _fixed(getattr(fee, "ante_last20_median", None), 6)
    ante_last20_p25 = _fixed(getattr(fee, "ante_last20_p25", None), 6)
    ante_last20_p75 = _fixed(getattr(fee, "ante_last20_p75", None), 6)
    if None in (ante_last20_median, ante_last20_p25, ante_last20_p75):
        ante_last20_median = ante_last20_p25 = ante_last20_p75 = ""
        _add_reason(field_reasons, "ante_last20", UNKNOWN_ANTE_REASON)
    ante_5m_median = _fixed(getattr(fee, "ante_5m_median", None), 6)
    ante_5m_sample_count = _integer(getattr(fee, "ante_5m_sample_count", None))
    if ante_5m_median is None or ante_5m_sample_count is None:
        ante_5m_median = ""
        ante_5m_sample_count = ""
        _add_reason(field_reasons, "ante_5m", UNKNOWN_ANTE_REASON)
    base_coverage = _percent(
        getattr(fee, "ante_5m_base_fee_coverage", None), fraction=True)
    if base_coverage is None:
        base_coverage = ""
        _add_reason(field_reasons, "base_fee_coverage", UNKNOWN_ANTE_REASON)
    width20 = _width(
        getattr(fee, "ante_last20_p25", None),
        getattr(fee, "ante_last20_p75", None),
    )
    width5 = _width(
        getattr(fee, "ante_5m_p25", None),
        getattr(fee, "ante_5m_p75", None),
    )
    if width20 is None and width5 is None:
        _add_reason(field_reasons, "ante_widths", UNKNOWN_ANTE_REASON)
    priority_median = _integer(
        getattr(fee, "priority_fee_median_lamports", None), commas=True)
    priority_samples = _integer(
        getattr(fee, "priority_fee_sample_count", None))
    if priority_median is None or priority_samples is None:
        priority_median = ""
        priority_samples = ""
        _add_reason(field_reasons, "priority_fee_median_lamports",
                    UNKNOWN_ANTE_REASON)

    shape5 = getattr(fee, "ante_5m_shape", None)
    rule5 = getattr(fee, "ante_5m_shape_rule", None)
    if not isinstance(shape5, str) or not shape5.strip() \
            or not isinstance(rule5, str) or not rule5.strip():
        shape5_count = _decimal(getattr(fee, "ante_5m_sample_count", None))
        if shape5_count is None or shape5_count <= 0:
            shape5 = "INSUFFICIENT SAMPLE"
            _add_reason(field_reasons, "shape_5m",
                        ANTE_SHAPE_INSUFFICIENT_REASON)
        else:
            shape5 = "NO APPROVED SHAPE RULE"
            _add_reason(field_reasons, "shape_5m", ANTE_SHAPE_NO_RULE_REASON)
        rule5 = "N/A"
    shape20 = getattr(fee, "ante_last20_shape", None)
    rule20 = getattr(fee, "ante_last20_shape_rule", None)
    if not isinstance(shape20, str) or not shape20.strip() \
            or not isinstance(rule20, str) or not rule20.strip():
        shape20_count = _decimal(
            getattr(fee, "ante_last20_sample_count", None))
        if shape20_count is None or shape20_count <= 0:
            shape20 = "INSUFFICIENT SAMPLE"
            _add_reason(field_reasons, "shape_last20",
                        ANTE_SHAPE_INSUFFICIENT_REASON)
        else:
            shape20 = "NO APPROVED SHAPE RULE"
            _add_reason(field_reasons, "shape_last20",
                        ANTE_SHAPE_NO_RULE_REASON)
        rule20 = "N/A"

    composite = "PASS" if str(getattr(security, "verdict", "")) == "ALLOW" \
        else str(getattr(security, "verdict", "UNKNOWN"))
    builder = _builder_read(
        fee=fee,
        lp=lp,
        liquidity=liquidity_value,
        floor=floor_value,
        shape_5m=shape5,
    )
    if not builder:
        _add_reason(field_reasons, "builder_read", BUILDER_NO_RULE_REASON)
    # Evidence-coverage provenance (2026-07-27): a restart-backfill admission
    # has observations only since its admission; its displayed maximum must
    # never claim to be the complete post-migration ATH.
    provenance_raw = candidate.get("discovery_provenance")
    # Coverage is classified by the SHARED send-path contract, so the rendered
    # disclosure and the compose gate can never disagree: a restart-backfill
    # admission whose migration-anchored OHLCV history has been hydrated and
    # verified renders as complete, and one still hydrating cannot reach this
    # renderer at all (the composer refuses it).
    ath_coverage = classify_ath_coverage(
        discovery_provenance=provenance_raw,
        ath_hydration_status=central_ath.get("ath_hydration_status"),
    )
    if provenance_raw == LIVE_DISCOVERY_PROVENANCE:
        discovery_provenance = "LIVE"
    elif provenance_raw == HELIUS_DISCOVERY_PROVENANCE:
        # Equal-authority live provenance with its own stable closed-set
        # rendering token; never rewritten to the Yellowstone token.
        discovery_provenance = "HELIUS_LIVE"
    elif provenance_raw == DEX_BACKFILL_PROVENANCE:
        discovery_provenance = DEX_BACKFILL_PROVENANCE
    else:
        discovery_provenance = "UNKNOWN"
    if ath_coverage == ATH_COVERAGE_PARTIAL_SINCE_ADMISSION:
        _add_reason(field_reasons, "post_migration_ath",
                    "ATH_COVERAGE_PARTIAL_SINCE_ADMISSION")
    elif ath_coverage == ATH_COVERAGE_UNKNOWN:
        _add_reason(field_reasons, "post_migration_ath",
                    "ATH_COVERAGE_UNKNOWN")

    return TelegramPingData(
        token_mint=mint,
        token_identity=token_identity,
        token_metadata_source=token_metadata_source,
        age_minutes=age_minutes,
        age_display=format_age_minutes(age_minutes),
        tier=tier,
        market_cap=market_cap,
        post_migration_ath=post_migration_ath,
        migration_market_cap=migration_market_cap,
        floor=floor_display,
        volume=volume,
        global_fees_display=global_fees_display,
        liquidity=liquidity_display,
        quote_side_liquidity=quote_liquidity_display,
        liquidity_basis=liquidity_basis,
        liquidity_quality=quality,
        fee_gate_label=fee_gate_label,
        fee_gate_score=fee_gate_score,
        lp_integrity=("DISABLED" if lp_disabled
                      else str(getattr(lp, "lp_integrity", "UNKNOWN"))),
        composite_verdict=composite,
        bribes_amm_pct=bribes_amm_pct,
        creator_pct=creator_pct,
        bribes_per_tx_lamports=bribes_per_tx_lamports,
        structure_read=structure_read,
        ante_last20_median=ante_last20_median,
        ante_last20_p25=ante_last20_p25,
        ante_last20_p75=ante_last20_p75,
        ante_5m_median=ante_5m_median,
        ante_5m_sample_count=ante_5m_sample_count,
        base_fee_coverage=base_coverage,
        ante_last20_width=(
            _trim(width20, 1) if width20 is not None else ""),
        ante_5m_width=(
            _trim(width5, 1) if width5 is not None else ""),
        priority_fee_median_lamports=priority_median,
        priority_fee_sample_count=priority_samples,
        shape_5m=shape5,
        shape_5m_rule=rule5,
        shape_last20=shape20,
        shape_last20_rule=rule20,
        builder_read=builder,
        risk_warning=_risk_warning(risk_assessment),
        policy_reason_display=_policy_reason_display(tuple(getattr(
            security, "shadow_warning_reason_tokens", ()) or ())),
        field_reason_codes=field_reasons,
        global_fee_support=global_fee_support_artifact,
        discovery_provenance=discovery_provenance,
        ath_coverage=ath_coverage,
        phx1_structural_policy_mode=str(getattr(
            security, "phx1_structural_policy", "ENFORCE")),
        original_phx1_structural_verdict=str(getattr(
            security, "original_phx1_structural_verdict", "PASS")),
        effective_phx1_policy_verdict=str(getattr(
            security, "effective_phx1_policy_verdict", "PASS")),
        shadow_warning_reasons=tuple(getattr(
            security, "shadow_warning_reason_tokens", ()) or ()),
        organicity_status=str(getattr(
            security, "organicity_status", "UNVERIFIED")),
        manual_review_required=bool(getattr(
            security, "manual_review_required", False)),
    )


class TelegramDeliveryAdapter:
    """Exact-body binder between the existing guard and Telegram transport."""

    requires_bound_delivery = True

    def __init__(
        self,
        transport: TelegramTransport,
        *,
        compose_sink: Optional[Callable[[Mapping[str, Any]], None]] = None,
        attempt_sink: Optional[Callable[[Mapping[str, Any]], None]] = None,
        console_sink: Optional[Callable[[str], None]] = print,
        logo_resolver: Optional[Callable[[str], object]] = None,
    ) -> None:
        self._transport = transport
        self._compose_sink = compose_sink
        self._attempt_sink = attempt_sink
        self._console_sink = console_sink
        self._logo_resolver = logo_resolver
        self._bound_body: Optional[str] = None
        self._bound_mint: Optional[str] = None
        self._composed: Optional[TelegramComposeResult] = None
        self._compose_failure: Optional[str] = None
        self._bound_created_at_utc: Optional[str] = None
        self._shadow_warning_expected = False
        self.last_result: Optional[TelegramTransportResult] = None
        self.last_compose_artifact: Optional[dict[str, Any]] = None

    def bind_delivery(
        self,
        *,
        body: object,
        mint: object,
        composed_snapshot: Any,
        delivery_context: Mapping[str, Any],
        created_at_utc: str,
    ) -> None:
        self._bound_body = body if isinstance(body, str) else None
        self._bound_mint = mint if isinstance(mint, str) else None
        self._composed = None
        self._compose_failure = None
        self._bound_created_at_utc = created_at_utc
        self._shadow_warning_expected = False
        self.last_compose_artifact = None
        if self._console_sink is not None and self._bound_mint:
            self._console_sink(f"[PING] COMPOSE_STARTED mint={self._bound_mint}")
        try:
            if self._bound_body is None or self._bound_mint is None:
                raise ValueError("TELEGRAM_BINDING_INVALID")
            data = build_ping_data(
                mint=self._bound_mint,
                composed_snapshot=composed_snapshot,
                delivery_context=delivery_context,
                now_utc=created_at_utc,
            )
            self._shadow_warning_expected = data.manual_review_required
            self._composed = compose_discovery_alert(data)
            security = delivery_context.get("security_decision")
            fee = getattr(security, "fee_snapshot", None)
            fee_evidence_valid = _fee_evidence_valid(fee)
            total = _decimal(getattr(fee, "total_fees", None))
            observation_minutes = _observation_minutes(
                getattr(fee, "first_observed_at_utc", None),
                getattr(fee, "last_observed_at_utc", None),
            )
            participation_pace = (
                total / observation_minutes
                if total is not None and observation_minutes is not None
                else None
            )
            market = delivery_context.get("market_context")
            market = market if isinstance(market, Mapping) else {}
            central = market.get("central_ath")
            central = central if isinstance(central, Mapping) else {}
            activation = delivery_context.get("activation")
            activation = activation if isinstance(activation, Mapping) else {}
            candidate_context = delivery_context.get("candidate")
            candidate_context = (candidate_context
                                 if isinstance(candidate_context, Mapping) else {})
            lifecycle = candidate_context.get("fee_gate_lifecycle")
            lifecycle = lifecycle if isinstance(lifecycle, Mapping) else {}
            reserve_mapping = (
                dict(market.get("pumpswap_reserve"))
                if isinstance(market.get("pumpswap_reserve"), Mapping) else {})
            metadata_state = candidate_context.get("canonical_token_metadata")
            metadata_state = (dict(metadata_state)
                              if isinstance(metadata_state, Mapping) else {})
            self.last_compose_artifact = {
                "kind": "PHX2_TELEGRAM_COMPOSE",
                "presentation_version": "PHX1_COMPACT_V1",
                "alert_kind": "DISCOVERY_ALERT",
                "inline_buttons": False,
                "transport": "TELEGRAM",
                "token_mint": self._bound_mint,
                "token_identity": data.token_identity,
                "token_metadata_source": data.token_metadata_source,
                "discovery_provenance": data.discovery_provenance,
                "ath_coverage": data.ath_coverage,
                "token_metadata": {
                    "token_name": metadata_state.get("token_name"),
                    "token_symbol": metadata_state.get("token_symbol"),
                    "metadata_status": metadata_state.get("metadata_status"),
                    "metadata_source": metadata_state.get("metadata_source"),
                    "metadata_first_requested_at": metadata_state.get(
                        "metadata_first_requested_at"),
                    "metadata_resolved_at": metadata_state.get(
                        "metadata_resolved_at"),
                    "metadata_attempt_count": metadata_state.get(
                        "metadata_attempt_count"),
                    "metadata_failure_reason": metadata_state.get(
                        "metadata_failure_reason"),
                    "metadata_pending_at_compose": bool(
                        metadata_state.get("metadata_status") == "PENDING"),
                },
                "tier": data.tier,
                "age_minutes": data.age_minutes,
                "age_display": data.age_display,
                "observe_only_telemetry": {
                    "canonical_volume_5m": dict(
                        candidate_context.get("canonical_volume_5m") or {}),
                    # Full Global Fees provenance (status, interval, source,
                    # endpoint, freshness, failure reason, regression
                    # disclosure) plus whether the body actually rendered it.
                    "global_fees": dict(
                        candidate_context.get("global_fees") or {}),
                    "global_fees_rendered": bool(data.global_fees_display),
                    # Observe-only Global Fee Support v1: rule version, exact
                    # formula inputs, both observation timestamps, the
                    # classification, and what the body rendered.
                    "global_fee_support": dict(data.global_fee_support),
                    # Full raw Participation telemetry — presentation-only
                    # removal from the body (2026-07-29); nothing is dropped
                    # from the artifact surface.
                    "participation": _participation_artifact(
                        fee,
                        participation_pace=participation_pace,
                        observation_minutes=observation_minutes,
                        fee_evidence_valid=fee_evidence_valid,
                    ),
                    # Raw Structure evidence behind the summarized/withheld
                    # operator lines (label, score, reasons, shares, read).
                    "structure_evidence": _structure_evidence_artifact(
                        fee, fee_evidence_valid=fee_evidence_valid),
                    "lp_integrity": data.lp_integrity,
                    "composite_verdict": data.composite_verdict,
                    "liquidity_basis": data.liquidity_basis,
                    "actual_pool_tvl_usd": reserve_mapping.get(
                        "actual_pool_tvl_usd"),
                    "actual_quote_liquidity_usd": reserve_mapping.get(
                        "actual_quote_liquidity_usd"),
                    "provider_liquidity_usd": market.get("liquidity_usd"),
                    # Full exact-pair reserve evidence (raw vault observations,
                    # timestamps, freshness inputs, validation status) so the
                    # artifact keeps everything the body no longer shows.
                    "pumpswap_reserve": reserve_mapping,
                    "liquidity_quality_reason": (
                        LIQUIDITY_QUALITY_NOT_SCORED_REASON),
                },
                "composed_at_utc": created_at_utc,
                "rendered_character_count": self._composed.rendered_character_count,
                "text_sha256": hashlib.sha256(
                    self._composed.text.encode("utf-8")).hexdigest(),
                "builder_read": [
                    {"statement": statement.text,
                     "reason_codes": list(statement.reason_codes)}
                    for statement in data.builder_read
                ],
                "field_reason_codes": {
                    key: list(values)
                    for key, values in self._composed.field_reason_codes.items()
                },
                # Closed-set presentation status per operator-surface field
                # (AVAILABLE / UNAVAILABLE / NOT_APPLICABLE / HIDDEN_INTERNAL).
                "field_presentation": dict(self._composed.field_presentation),
                "phx1_structural_policy": {
                    "policy_mode": data.phx1_structural_policy_mode,
                    "original_phx1_structural_verdict": (
                        data.original_phx1_structural_verdict),
                    "effective_phx1_policy_verdict": (
                        data.effective_phx1_policy_verdict),
                    "shadow_warning_reason_tokens": list(
                        data.shadow_warning_reasons),
                    "organicity_status": data.organicity_status,
                    "manual_review_required": data.manual_review_required,
                    "policy_digest": getattr(
                        security, "phx1_policy_digest", None),
                },
                # Enforcement is read from the policy matrix, never inferred
                # from the status text, so a SHADOW condition can never be
                # rendered as a blocker.
                "alert_policy": _current_alert_policy(),
                "alert_policy_enforcement": _observability_matrix(
                    activation_status=(
                        _PARITY_STATUS_PROVEN
                        if activation.get("activation_proven")
                        else _PARITY_STATUS_NOT_PROVEN),
                    fee_lifecycle_status=lifecycle.get("lifecycle_state"),
                    ath_coverage_status=(
                        _PARITY_STATUS_COMPLETE
                        if _ath_coverage_is_complete(data.ath_coverage)
                        else _PARITY_STATUS_INCOMPLETE),
                    # Reaching compose at all means the committed composer
                    # already enforced its freshness ceiling on this context.
                    market_freshness_status=_PARITY_STATUS_FRESH,
                    policy=_current_alert_policy(),
                ),
                "source_proofs": {
                    "security_decision_digest": getattr(security, "proof_digest", None),
                    "phx1_policy_digest": getattr(
                        security, "phx1_policy_digest", None),
                    "fee_gate_digest": getattr(
                        getattr(security, "fee_snapshot", None), "proof_digest", None),
                    "lp_integrity_digest": getattr(
                        getattr(security, "lp_snapshot", None), "proof_digest", None),
                    "fee_gate_lifecycle_version": lifecycle.get("lifecycle_version"),
                    "fee_gate_lifecycle_state": lifecycle.get("lifecycle_state"),
                    "fee_gate_lifecycle_evidence_digest": lifecycle.get(
                        "evidence_proof_digest"),
                    "central_ath_market_cap": central.get("ath_market_cap"),
                    "central_ath_evidence_digest": central.get("ath_evidence_digest"),
                    "central_ath_evidence_version": central.get("ath_evidence_version"),
                    # The RESOLVED observation the rendered market cap and the
                    # composed tier were both bound to, recorded beside the raw
                    # arm so an audit can tell exactly which value was used.
                    "central_ath_resolved_market_cap": central.get(
                        "resolved_ath_market_cap"),
                    "central_ath_resolved_price": central.get(
                        "resolved_ath_price"),
                    "central_ath_resolved_supply_basis": central.get(
                        "resolved_supply_basis"),
                    "central_ath_resolution_method": central.get(
                        "resolution_method"),
                    "migration_market_cap_usd": activation.get("migration_market_cap_usd"),
                    "migration_baseline_digest": activation.get(
                        "migration_baseline_digest"),
                    "activation_state": activation.get("activation_state"),
                    "activation_evidence_source": activation.get(
                        "activation_evidence_source"),
                    "activation_evidence_market_cap_usd": activation.get(
                        "activation_evidence_market_cap_usd"),
                    "activation_evidence_event_at_utc": activation.get(
                        "activation_evidence_event_at_utc"),
                    "activation_evidence_ingested_at_utc": activation.get(
                        "activation_evidence_ingested_at_utc"),
                    "activation_evidence_digest": activation.get(
                        "activation_evidence_digest"),
                    "activation_evidence_version": activation.get(
                        "activation_evidence_version"),
                    "activation_source_evidence_digest": activation.get(
                        "activation_source_evidence_digest"),
                    "activation_observation_seal_digest": activation.get(
                        "activation_observation_seal_digest"),
                    "activation_observation_seal_version": activation.get(
                        "activation_observation_seal_version"),
                    "activation_proof_digest": activation.get(
                        "activation_proof_digest"),
                    "activation_proof_version": activation.get(
                        "activation_proof_version"),
                    "activation_evidence_kind": activation.get("activation_evidence_kind"),
                    "activation_crossing_tick_digest": activation.get(
                        "activation_crossing_tick_digest"),
                    "activation_crossing_tick_blocked": bool(activation.get(
                        "activation_crossing_tick_blocked")),
                    "activation_latched": bool(activation.get("activation_latched")),
                    "risk_label": ((market.get("risk_assessment") or {}).get("risk_label")
                                   if isinstance(market.get("risk_assessment"), Mapping)
                                   else None),
                    "risk_reasons": (list((market.get("risk_assessment") or {}).get(
                        "risk_reasons") or ())
                        if isinstance(market.get("risk_assessment"), Mapping) else []),
                },
            }
            if self._compose_sink is not None:
                self._compose_sink(self.last_compose_artifact)
        except TelegramMessageTooLong:
            self._compose_failure = (
                MESSAGE_LENGTH_LIMIT_EXCEEDED
                if self._shadow_warning_expected else MESSAGE_TOO_LONG)
        except Exception:
            self._compose_failure = MESSAGE_REJECTED

    def bind_body(self, *, body: object, mint: object) -> None:
        """Legacy display binder is deliberately not sufficient for Telegram."""

        if self._bound_body != body or self._bound_mint != mint:
            self._compose_failure = MESSAGE_REJECTED

    def send_one_audited_post(
        self, *, webhook_identity: Optional[str], payload: Mapping[str, Any]
    ) -> TelegramTransportResult:
        del webhook_identity
        body = payload.get("content") if isinstance(payload, Mapping) else None
        if body != self._bound_body or self._bound_mint is None:
            self._compose_failure = MESSAGE_REJECTED
        if self._compose_failure == MESSAGE_LENGTH_LIMIT_EXCEEDED:
            result = TelegramTransportResult(
                ok=False,
                transport_status=MESSAGE_LENGTH_LIMIT_EXCEEDED,
                message_id=None,
                destination_alias="PHOENIX_CHANNEL",
                attempted_at_utc=(
                    self._bound_created_at_utc
                    or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
                ),
                delivered_at_utc=None,
                retry_count=0,
                safe_error_category=MESSAGE_LENGTH_LIMIT_EXCEEDED,
                send_attempt_count=0,
            )
        elif self._compose_failure == MESSAGE_TOO_LONG:
            result = self._transport.send_html("x" * 3901)
        elif self._compose_failure or self._composed is None:
            result = self._transport.send_html("")
        else:
            if self._console_sink is not None:
                self._console_sink(
                    f"[TELEGRAM] ATTEMPT mint={self._bound_mint} chat=PHOENIX_CHANNEL")
            logo = None
            if self._logo_resolver is not None:
                try:
                    logo = self._logo_resolver(self._bound_mint)
                except Exception:
                    pass  # optional presentation must not block a valid alert
            send_alert = getattr(self._transport, "send_alert", None)
            if callable(send_alert):
                result = send_alert(self._composed.text, logo_url=logo)
            else:
                result = self._transport.send_html(self._composed.text)
        self.last_result = result
        evidence = {**result.evidence(), "token_mint": self._bound_mint}
        if self._attempt_sink is not None:
            self._attempt_sink(evidence)
        if self._console_sink is not None:
            if result.transport_status == SENT_OK:
                self._console_sink(
                    f"[TELEGRAM] SENT_OK mint={self._bound_mint} "
                    f"message_id={result.message_id}")
            else:
                self._console_sink(
                    f"[TELEGRAM] FAILED mint={self._bound_mint} "
                    f"reason={result.transport_status}")
        return result

    def close(self) -> None:
        self._transport.close()


__all__ = (
    "UNKNOWN_ANTE_REASON",
    "UNKNOWN_PARTICIPATION_PACE_REASON",
    "BUILDER_NO_RULE_REASON",
    "MESSAGE_LENGTH_LIMIT_EXCEEDED",
    "VOLUME_INSUFFICIENT_REASON",
    "VOLUME_INVALID_REASON",
    "LIQUIDITY_DATA_UNAVAILABLE_REASON",
    "LIQUIDITY_QUALITY_NOT_SCORED_REASON",
    "ANTE_SHAPE_NO_RULE_REASON",
    "ANTE_SHAPE_INSUFFICIENT_REASON",
    "CENTRAL_ATH_UNAVAILABLE_REASON",
    "MIGRATION_MC_UNAVAILABLE_REASON",
    "ATH_FLOOR_UNAVAILABLE_REASON",
    "FEE_EVIDENCE_INVALID_REASON",
    "STRUCTURE_READ_UNAVAILABLE_REASON",
    "UNKNOWN_TOKEN_DISPLAY",
    "RISK_REASONS_INTERNAL_ONLY",
    "RISK_LABEL_TELEGRAM_DISPLAY",
    "RISK_REASON_TELEGRAM_DISPLAY",
    "SHADOW_REASON_TELEGRAM_DISPLAY",
    "FEE_GATE_LABEL_TELEGRAM_DISPLAY",
    "STRUCTURE_READ_TELEGRAM_DISPLAY",
    "format_age_minutes",
    "resolve_token_identity",
    "TelegramDeliveryAdapter",
    "build_ping_data",
)

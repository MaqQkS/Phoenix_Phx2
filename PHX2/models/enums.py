"""Shared PHX2 enums."""

from enum import Enum


class DataStatus(str, Enum):
    """Data completeness status for PHX2 records."""

    OK = "ok"
    PARTIAL = "partial"
    MISSING = "missing"
    NO_EVENTS = "no_events"
    DATA_LIMITED = "data_limited"
    SOURCE_UNAVAILABLE = "source_unavailable"
    ERROR = "error"


class ATHStatus(str, Enum):
    """Lifecycle status for ATH truth."""

    UNKNOWN = "unknown"
    PROVISIONAL = "provisional"
    SEEDED = "seeded"
    RESEEDED = "reseeded"
    CONFIRMED = "confirmed"
    DATA_LIMITED = "data_limited"
    STALE = "stale"
    INVALID = "invalid"


class ATHConfidence(str, Enum):
    """Confidence level for an ATH value."""

    UNKNOWN = "unknown"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    FINAL = "final"


class ATHEventType(str, Enum):
    """ATH event or mutation type."""

    ATH_RAISED = "ath_raised"
    ATH_NO_CHANGE = "ath_no_change"
    ATH_CONFIDENCE_CHANGED = "ath_confidence_changed"
    ATH_REJECTED_LOWER = "ath_rejected_lower"
    ATH_REJECTED_INVALID = "ath_rejected_invalid"
    ATH_DATA_LIMITED = "ath_data_limited"
    ATH_SOURCE_CONFLICT = "ath_source_conflict"
    ATH_CORRECTION = "ath_correction"


class DecisionType(str, Enum):
    """High-level alert decision result."""

    WOULD_ALERT = "would_alert"
    SKIP = "skip"
    BLOCK = "block"
    ERROR = "error"


class DecisionReason(str, Enum):
    """Canonical alert decision reason."""

    WOULD_ALERT = "would_alert"
    PRICE_STALE = "price_stale"
    ATH_UNKNOWN = "ath_unknown"
    ATH_DATA_LIMITED = "ath_data_limited"
    ATH_CONFIDENCE_TOO_LOW = "ath_confidence_too_low"
    MIN_PUMP_NOT_MET = "min_pump_not_met"
    TIER_GAP = "tier_gap"
    DUPLICATE_TIER = "duplicate_tier"
    FILTER_BLOCKED = "filter_blocked"
    DRAWDOWN_BELOW_FIRST_TIER = "drawdown_below_first_tier"
    DRAWDOWN_BEYOND_MAX_TIER = "drawdown_beyond_max_tier"
    MISSING_MIGRATION_PRICE = "missing_migration_price"
    MISSING_CURRENT_PRICE = "missing_current_price"
    TOKEN_NOT_ACTIVE = "token_not_active"
    TOKEN_NOT_FOUND = "token_not_found"
    MISSING_PRICE_OBSERVATION = "missing_price_observation"
    MISSING_ATH = "missing_ath"
    MISSING_PUMP_MULTIPLE = "missing_pump_multiple"
    MISSING_DRAWDOWN = "missing_drawdown"
    LOWER_OR_EQUAL_TIER_ALREADY_ALERTED = "lower_or_equal_tier_already_alerted"
    INVALID_CURRENT_PRICE = "invalid_current_price"
    INVALID_MIGRATION_PRICE = "invalid_migration_price"
    POLICY_DISABLED = "policy_disabled"
    COOLDOWN_ACTIVE = "cooldown_active"
    ERROR = "error"


class DispatchMode(str, Enum):
    """Allowed future alert dispatch modes."""

    DISABLED = "disabled"
    FILE_PREVIEW = "file_preview"
    CONSOLE = "console"
    TELEGRAM_PRIVATE = "telegram_private"
    DISCORD_PRIVATE = "discord_private"
    TELEGRAM_LIVE = "telegram_live"
    DISCORD_LIVE = "discord_live"
    MULTI = "multi"

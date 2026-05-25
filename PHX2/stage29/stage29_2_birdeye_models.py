"""Stage 29.2 Birdeye snapshot + evidence models.

Closed-set vocabularies + immutable record shapes used by the
Stage 29.2 Birdeye price / ATH adapter. The two snapshot
dataclasses (``Stage29_2BirdeyePriceSnapshot`` and
``Stage29_2BirdeyeAthSnapshot``) are designed to be projected
into the existing Stage 27.4 ``PriceSourceSnapshot`` /
``AthSourceSnapshot`` NamedTuples at the source-adapter
boundary, so the existing Stage 27.4 reader can consume Stage
29.2 evidence without any Stage 27 production change.

Closed-set vocabularies (names reserved by Stage 29.0 §13):

  * ``birdeye_price_status``  -- ``PRESENT`` / ``MISSING`` /
                                  ``STALE`` / ``SOURCE_ERROR``
  * ``birdeye_ath_status``    -- ``PRESENT`` / ``MISSING`` /
                                  ``STALE`` / ``SOURCE_ERROR``
  * ``birdeye_freshness_status`` -- ``FRESH`` / ``STALE`` /
                                     ``UNKNOWN``
  * ``birdeye_refusal_reason`` -- the closed-set refusal token
                                   set carried on every Stage
                                   29.2 error / snapshot rejection
                                   path.

Stage 29.2 deliberately does NOT carry:

  * a raw Birdeye API key,
  * a raw Birdeye HTTP response body,
  * a raw HTTP traceback,
  * a webhook URL or any host literal,
  * a wallet / private-key / signer field,
  * a floating-point price / ATH value used as a missing
    sentinel (numeric values are canonical decimal text strings;
    missing values are ``None``, never ``0.0``).

This module imports ONLY stdlib (``dataclasses`` / ``typing``)
plus the Stage 29.2 constants module. It does NOT import:

  * Stage 21-28 production code,
  * any network / RPC / messaging / DB / scheduler / secrets /
    wallet / trading / Discord / Telegram / X / dotenv / keyring
    library,
  * ``os`` / the process environment,
  * any PHX1 / legacy Phoenix-1 source tree module.

Discipline:

  * No env reads.
  * No network.
  * No top-level Call (no implicit I/O at import time).
  * Snapshot records validate every closed-set token at
    ``__post_init__`` so the closed-set contract cannot be
    bypassed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from PHX2.stage29.birdeye_constants import (
    STAGE29_2_BIRDEYE_EVIDENCE_SCHEMA_VERSION,
    STAGE29_2_BIRDEYE_SNAPSHOT_SCHEMA_VERSION,
)


# ---------------------------------------------------------------------------
# Closed-set: birdeye_price_status
# ---------------------------------------------------------------------------


BIRDEYE_PRICE_STATUS_PRESENT: str = "PRESENT"
BIRDEYE_PRICE_STATUS_MISSING: str = "MISSING"
BIRDEYE_PRICE_STATUS_STALE: str = "STALE"
BIRDEYE_PRICE_STATUS_SOURCE_ERROR: str = "SOURCE_ERROR"


BIRDEYE_PRICE_STATUS_VALUES: tuple[str, ...] = (
    BIRDEYE_PRICE_STATUS_PRESENT,
    BIRDEYE_PRICE_STATUS_MISSING,
    BIRDEYE_PRICE_STATUS_STALE,
    BIRDEYE_PRICE_STATUS_SOURCE_ERROR,
)


def is_birdeye_price_status_value(value: object) -> bool:
    return (
        isinstance(value, str)
        and value in BIRDEYE_PRICE_STATUS_VALUES
    )


# ---------------------------------------------------------------------------
# Closed-set: birdeye_ath_status
# ---------------------------------------------------------------------------


BIRDEYE_ATH_STATUS_PRESENT: str = "PRESENT"
BIRDEYE_ATH_STATUS_MISSING: str = "MISSING"
BIRDEYE_ATH_STATUS_STALE: str = "STALE"
BIRDEYE_ATH_STATUS_SOURCE_ERROR: str = "SOURCE_ERROR"


BIRDEYE_ATH_STATUS_VALUES: tuple[str, ...] = (
    BIRDEYE_ATH_STATUS_PRESENT,
    BIRDEYE_ATH_STATUS_MISSING,
    BIRDEYE_ATH_STATUS_STALE,
    BIRDEYE_ATH_STATUS_SOURCE_ERROR,
)


def is_birdeye_ath_status_value(value: object) -> bool:
    return (
        isinstance(value, str)
        and value in BIRDEYE_ATH_STATUS_VALUES
    )


# ---------------------------------------------------------------------------
# Closed-set: birdeye_freshness_status
# ---------------------------------------------------------------------------


BIRDEYE_FRESHNESS_STATUS_FRESH: str = "FRESH"
BIRDEYE_FRESHNESS_STATUS_STALE: str = "STALE"
BIRDEYE_FRESHNESS_STATUS_UNKNOWN: str = "UNKNOWN"


BIRDEYE_FRESHNESS_STATUS_VALUES: tuple[str, ...] = (
    BIRDEYE_FRESHNESS_STATUS_FRESH,
    BIRDEYE_FRESHNESS_STATUS_STALE,
    BIRDEYE_FRESHNESS_STATUS_UNKNOWN,
)


def is_birdeye_freshness_status_value(value: object) -> bool:
    return (
        isinstance(value, str)
        and value in BIRDEYE_FRESHNESS_STATUS_VALUES
    )


# ---------------------------------------------------------------------------
# Closed-set: birdeye_refusal_reason
# ---------------------------------------------------------------------------


BIRDEYE_REFUSAL_REASON_NONE: str = "NONE"
BIRDEYE_REFUSAL_REASON_ENDPOINT_MISSING: str = "ENDPOINT_MISSING"
BIRDEYE_REFUSAL_REASON_ENDPOINT_UNSAFE: str = "ENDPOINT_UNSAFE"
BIRDEYE_REFUSAL_REASON_API_KEY_MISSING: str = "API_KEY_MISSING"
BIRDEYE_REFUSAL_REASON_API_KEY_UNSAFE: str = "API_KEY_UNSAFE"
BIRDEYE_REFUSAL_REASON_LIVE_FLAG_NOT_SET: str = (
    "LIVE_FLAG_NOT_SET"
)
BIRDEYE_REFUSAL_REASON_TIMEOUT_INVALID: str = "TIMEOUT_INVALID"
BIRDEYE_REFUSAL_REASON_HTTP_FAILED: str = "HTTP_FAILED"
BIRDEYE_REFUSAL_REASON_HTTP_TIMEOUT: str = "HTTP_TIMEOUT"
BIRDEYE_REFUSAL_REASON_HTTP_STATUS_REJECTED: str = (
    "HTTP_STATUS_REJECTED"
)
BIRDEYE_REFUSAL_REASON_HTTP_SUCCESS_FALSE: str = (
    "HTTP_SUCCESS_FALSE"
)
BIRDEYE_REFUSAL_REASON_BODY_MALFORMED: str = "BODY_MALFORMED"
BIRDEYE_REFUSAL_REASON_PRICE_MISSING_IN_BODY: str = (
    "PRICE_MISSING_IN_BODY"
)
BIRDEYE_REFUSAL_REASON_ATH_SERIES_EMPTY: str = "ATH_SERIES_EMPTY"
BIRDEYE_REFUSAL_REASON_MINT_REJECTED_SAFE_SHAPE: str = (
    "MINT_REJECTED_SAFE_SHAPE"
)
BIRDEYE_REFUSAL_REASON_BASE_URL_REJECTED: str = (
    "BASE_URL_REJECTED"
)
BIRDEYE_REFUSAL_REASON_LOOKBACK_INVALID: str = "LOOKBACK_INVALID"
BIRDEYE_REFUSAL_REASON_OHLCV_TYPE_INVALID: str = (
    "OHLCV_TYPE_INVALID"
)
BIRDEYE_REFUSAL_REASON_MODE_INVALID: str = "MODE_INVALID"
BIRDEYE_REFUSAL_REASON_TRANSPORT_FACTORY_NOT_CALLABLE: str = (
    "TRANSPORT_FACTORY_NOT_CALLABLE"
)


BIRDEYE_REFUSAL_REASON_VALUES: tuple[str, ...] = (
    BIRDEYE_REFUSAL_REASON_NONE,
    BIRDEYE_REFUSAL_REASON_ENDPOINT_MISSING,
    BIRDEYE_REFUSAL_REASON_ENDPOINT_UNSAFE,
    BIRDEYE_REFUSAL_REASON_API_KEY_MISSING,
    BIRDEYE_REFUSAL_REASON_API_KEY_UNSAFE,
    BIRDEYE_REFUSAL_REASON_LIVE_FLAG_NOT_SET,
    BIRDEYE_REFUSAL_REASON_TIMEOUT_INVALID,
    BIRDEYE_REFUSAL_REASON_HTTP_FAILED,
    BIRDEYE_REFUSAL_REASON_HTTP_TIMEOUT,
    BIRDEYE_REFUSAL_REASON_HTTP_STATUS_REJECTED,
    BIRDEYE_REFUSAL_REASON_HTTP_SUCCESS_FALSE,
    BIRDEYE_REFUSAL_REASON_BODY_MALFORMED,
    BIRDEYE_REFUSAL_REASON_PRICE_MISSING_IN_BODY,
    BIRDEYE_REFUSAL_REASON_ATH_SERIES_EMPTY,
    BIRDEYE_REFUSAL_REASON_MINT_REJECTED_SAFE_SHAPE,
    BIRDEYE_REFUSAL_REASON_BASE_URL_REJECTED,
    BIRDEYE_REFUSAL_REASON_LOOKBACK_INVALID,
    BIRDEYE_REFUSAL_REASON_OHLCV_TYPE_INVALID,
    BIRDEYE_REFUSAL_REASON_MODE_INVALID,
    BIRDEYE_REFUSAL_REASON_TRANSPORT_FACTORY_NOT_CALLABLE,
)


def is_birdeye_refusal_reason_value(value: object) -> bool:
    return (
        isinstance(value, str)
        and value in BIRDEYE_REFUSAL_REASON_VALUES
    )


# ---------------------------------------------------------------------------
# Stage 29.2 module-local exception
# ---------------------------------------------------------------------------


class Stage29_2BirdeyeError(Exception):
    """Base type for every Stage 29.2 Birdeye model / snapshot /
    evidence validation error. Module-local; not a subclass of
    any central PHX2 error registry. The constructor NEVER
    carries a raw API key, raw base URL, raw response body, or
    raw HTTP traceback; callers pass only the closed-set reason
    token.
    """

    def __init__(self, reason: str) -> None:
        self.reason: str = reason
        super().__init__(
            f"Stage 29.2 Birdeye error: reason={reason!r}"
        )


# ---------------------------------------------------------------------------
# Stage29_2BirdeyePriceSnapshot
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Stage29_2BirdeyePriceSnapshot:
    """Immutable Stage 29.2 Birdeye price snapshot.

    Shape is compatible with the Stage 27.4 ``PriceSourceSnapshot``
    NamedTuple via ``to_price_source_snapshot_fields()``: the
    price source adapter projects this Stage 29.2 record into the
    Stage 27.4 contract at the boundary.

    Fields:

      * ``price_value`` -- canonical decimal-text price (e.g.
        ``"0.00012345"``); ``None`` when the upstream had nothing
        to report. Stage 29.2 NEVER uses ``0.0`` / ``"0"`` as a
        missing sentinel.
      * ``price_unit`` -- always ``"USD"`` for Stage 29.2's
        Birdeye reporting unit.
      * ``source_label`` -- safe-to-display label
        (``"birdeye_defi_price"``); never a URL, never a key.
      * ``fetched_at_utc`` -- ISO-8601 UTC timestamp of the
        HTTP response received-at moment (NOT
        ``data.updateUnixTime``; the latter is best-effort
        metadata at the probe layer).
      * ``upstream_update_unix_time`` -- the Birdeye
        ``data.updateUnixTime`` value when present, otherwise
        ``None``. Stage 29.2 NEVER fabricates this field.
      * ``birdeye_price_status`` -- closed-set status token.
      * ``birdeye_freshness_status`` -- closed-set freshness
        token.
      * ``schema_version`` -- locked Stage 29.2 snapshot schema
        version string.
    """

    price_value: Optional[str]
    price_unit: str
    source_label: Optional[str]
    fetched_at_utc: Optional[str]
    upstream_update_unix_time: Optional[int]
    birdeye_price_status: str
    birdeye_freshness_status: str
    schema_version: str

    def __post_init__(self) -> None:
        _validate_price_snapshot(self)


def _validate_price_snapshot(
    record: "Stage29_2BirdeyePriceSnapshot",
) -> None:
    if not is_birdeye_price_status_value(
        record.birdeye_price_status
    ):
        raise Stage29_2BirdeyeError(
            "PRICE_STATUS_NOT_CLOSED_SET"
        )
    if not is_birdeye_freshness_status_value(
        record.birdeye_freshness_status
    ):
        raise Stage29_2BirdeyeError(
            "FRESHNESS_STATUS_NOT_CLOSED_SET"
        )
    if not isinstance(record.price_unit, str):
        raise Stage29_2BirdeyeError("PRICE_UNIT_NOT_STR")
    if record.price_value is not None and not isinstance(
        record.price_value, str
    ):
        # Block floats entirely so a missing value is exactly
        # ``None`` and never ``0.0``.
        raise Stage29_2BirdeyeError(
            "PRICE_VALUE_NOT_STR_OR_NONE"
        )
    if record.source_label is not None and not isinstance(
        record.source_label, str
    ):
        raise Stage29_2BirdeyeError(
            "SOURCE_LABEL_NOT_STR_OR_NONE"
        )
    if record.fetched_at_utc is not None and not isinstance(
        record.fetched_at_utc, str
    ):
        raise Stage29_2BirdeyeError(
            "FETCHED_AT_UTC_NOT_STR_OR_NONE"
        )
    if record.upstream_update_unix_time is not None:
        if isinstance(record.upstream_update_unix_time, bool):
            raise Stage29_2BirdeyeError(
                "UPSTREAM_UPDATE_UNIX_TIME_NOT_INT_OR_NONE"
            )
        if not isinstance(
            record.upstream_update_unix_time, int
        ):
            raise Stage29_2BirdeyeError(
                "UPSTREAM_UPDATE_UNIX_TIME_NOT_INT_OR_NONE"
            )
        if record.upstream_update_unix_time < 0:
            raise Stage29_2BirdeyeError(
                "UPSTREAM_UPDATE_UNIX_TIME_NEGATIVE"
            )
    if not isinstance(record.schema_version, str):
        raise Stage29_2BirdeyeError(
            "SCHEMA_VERSION_NOT_STR"
        )
    if (
        record.birdeye_price_status
        == BIRDEYE_PRICE_STATUS_PRESENT
        and record.price_value is None
    ):
        raise Stage29_2BirdeyeError(
            "PRESENT_WITHOUT_PRICE_VALUE"
        )
    if (
        record.birdeye_price_status
        in (
            BIRDEYE_PRICE_STATUS_MISSING,
            BIRDEYE_PRICE_STATUS_SOURCE_ERROR,
        )
        and record.price_value is not None
    ):
        raise Stage29_2BirdeyeError(
            "MISSING_OR_ERROR_WITH_PRICE_VALUE"
        )


def build_birdeye_price_snapshot(
    *,
    price_value: Optional[str],
    price_unit: str,
    source_label: Optional[str],
    fetched_at_utc: Optional[str],
    upstream_update_unix_time: Optional[int],
    birdeye_price_status: str,
    birdeye_freshness_status: str,
) -> Stage29_2BirdeyePriceSnapshot:
    """Construct a validated ``Stage29_2BirdeyePriceSnapshot``."""
    return Stage29_2BirdeyePriceSnapshot(
        price_value=price_value,
        price_unit=price_unit,
        source_label=source_label,
        fetched_at_utc=fetched_at_utc,
        upstream_update_unix_time=upstream_update_unix_time,
        birdeye_price_status=birdeye_price_status,
        birdeye_freshness_status=birdeye_freshness_status,
        schema_version=STAGE29_2_BIRDEYE_SNAPSHOT_SCHEMA_VERSION,
    )


# ---------------------------------------------------------------------------
# Stage29_2BirdeyeAthSnapshot
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Stage29_2BirdeyeAthSnapshot:
    """Immutable Stage 29.2 Birdeye ATH snapshot.

    Shape is compatible with the Stage 27.4 ``AthSourceSnapshot``
    NamedTuple via ``to_ath_source_snapshot_fields()``.

    Fields:

      * ``ath_value`` -- canonical decimal-text ATH (from
        ``max(items[].h)`` of the bounded ``/defi/ohlcv``
        candle series); ``None`` when no observations are
        available.
      * ``ath_unit`` -- always ``"USD"``.
      * ``source_label`` -- safe-to-display label
        (``"birdeye_defi_ohlcv"``).
      * ``ath_observed_at_utc`` -- ISO-8601 UTC timestamp from
        the ``unixTime`` of the candle whose ``h`` is the
        observed max; ``None`` when no observations.
      * ``window_starts_post_migration`` -- ``True`` iff the
        caller-supplied lookback start was proven >= the
        Stage 29.1 migration evidence timestamp; ``False``
        when the caller cannot promise post-migration; ``None``
        when no migration evidence was supplied. Stage 29.2
        NEVER claims ``True`` without explicit caller-supplied
        proof.
      * ``lookback_hours`` -- the caller-supplied lookback
        window in hours; bounded by ``MIN_LOOKBACK_HOURS`` /
        ``MAX_LOOKBACK_HOURS``.
      * ``items_count`` -- safe counter of how many candles the
        bounded query returned. Stage 29.2 NEVER stores the raw
        items.
      * ``birdeye_ath_status`` -- closed-set status token.
      * ``birdeye_freshness_status`` -- closed-set freshness
        token.
      * ``schema_version`` -- locked Stage 29.2 snapshot schema
        version string.
    """

    ath_value: Optional[str]
    ath_unit: str
    source_label: Optional[str]
    ath_observed_at_utc: Optional[str]
    window_starts_post_migration: Optional[bool]
    lookback_hours: int
    items_count: int
    birdeye_ath_status: str
    birdeye_freshness_status: str
    schema_version: str

    def __post_init__(self) -> None:
        _validate_ath_snapshot(self)


def _validate_ath_snapshot(
    record: "Stage29_2BirdeyeAthSnapshot",
) -> None:
    if not is_birdeye_ath_status_value(
        record.birdeye_ath_status
    ):
        raise Stage29_2BirdeyeError(
            "ATH_STATUS_NOT_CLOSED_SET"
        )
    if not is_birdeye_freshness_status_value(
        record.birdeye_freshness_status
    ):
        raise Stage29_2BirdeyeError(
            "FRESHNESS_STATUS_NOT_CLOSED_SET"
        )
    if not isinstance(record.ath_unit, str):
        raise Stage29_2BirdeyeError("ATH_UNIT_NOT_STR")
    if record.ath_value is not None and not isinstance(
        record.ath_value, str
    ):
        raise Stage29_2BirdeyeError(
            "ATH_VALUE_NOT_STR_OR_NONE"
        )
    if record.source_label is not None and not isinstance(
        record.source_label, str
    ):
        raise Stage29_2BirdeyeError(
            "SOURCE_LABEL_NOT_STR_OR_NONE"
        )
    if record.ath_observed_at_utc is not None and not isinstance(
        record.ath_observed_at_utc, str
    ):
        raise Stage29_2BirdeyeError(
            "ATH_OBSERVED_AT_UTC_NOT_STR_OR_NONE"
        )
    if (
        record.window_starts_post_migration is not None
        and not isinstance(
            record.window_starts_post_migration, bool
        )
    ):
        raise Stage29_2BirdeyeError(
            "WINDOW_FLAG_NOT_BOOL_OR_NONE"
        )
    if (
        isinstance(record.lookback_hours, bool)
        or not isinstance(record.lookback_hours, int)
        or record.lookback_hours < 0
    ):
        raise Stage29_2BirdeyeError("LOOKBACK_HOURS_UNSAFE")
    if (
        isinstance(record.items_count, bool)
        or not isinstance(record.items_count, int)
        or record.items_count < 0
    ):
        raise Stage29_2BirdeyeError("ITEMS_COUNT_UNSAFE")
    if not isinstance(record.schema_version, str):
        raise Stage29_2BirdeyeError(
            "SCHEMA_VERSION_NOT_STR"
        )
    if (
        record.birdeye_ath_status == BIRDEYE_ATH_STATUS_PRESENT
        and record.ath_value is None
    ):
        raise Stage29_2BirdeyeError(
            "PRESENT_WITHOUT_ATH_VALUE"
        )
    if (
        record.birdeye_ath_status
        in (
            BIRDEYE_ATH_STATUS_MISSING,
            BIRDEYE_ATH_STATUS_SOURCE_ERROR,
        )
        and record.ath_value is not None
    ):
        raise Stage29_2BirdeyeError(
            "MISSING_OR_ERROR_WITH_ATH_VALUE"
        )


def build_birdeye_ath_snapshot(
    *,
    ath_value: Optional[str],
    ath_unit: str,
    source_label: Optional[str],
    ath_observed_at_utc: Optional[str],
    window_starts_post_migration: Optional[bool],
    lookback_hours: int,
    items_count: int,
    birdeye_ath_status: str,
    birdeye_freshness_status: str,
) -> Stage29_2BirdeyeAthSnapshot:
    """Construct a validated ``Stage29_2BirdeyeAthSnapshot``."""
    return Stage29_2BirdeyeAthSnapshot(
        ath_value=ath_value,
        ath_unit=ath_unit,
        source_label=source_label,
        ath_observed_at_utc=ath_observed_at_utc,
        window_starts_post_migration=(
            window_starts_post_migration
        ),
        lookback_hours=lookback_hours,
        items_count=items_count,
        birdeye_ath_status=birdeye_ath_status,
        birdeye_freshness_status=birdeye_freshness_status,
        schema_version=STAGE29_2_BIRDEYE_SNAPSHOT_SCHEMA_VERSION,
    )


# ---------------------------------------------------------------------------
# Stage29_2BirdeyeEvidenceRecord (composite for the probe artifact)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Stage29_2BirdeyeEvidenceRecord:
    """Immutable Stage 29.2 evidence record carrying both
    snapshots + a locally-computed drawdown ratio (telemetry
    only) + a no-invention audit verdict.

    Fields:

      * ``base_mint`` -- the mint string the operator-supplied
        Stage 29.1 evidence yielded.
      * ``price_snapshot`` -- the Stage 29.2 price snapshot.
      * ``ath_snapshot`` -- the Stage 29.2 ATH snapshot.
      * ``drawdown_ratio`` -- canonical decimal-text drawdown
        ratio (e.g. ``"-0.846"``) computed locally from
        (price, ATH). ``None`` when either snapshot is not
        ``PRESENT``, when units disagree, or when arithmetic
        fails. Stage 29.2 NEVER invents this value.
      * ``freshness_status`` -- overall closed-set freshness
        token derived from the two snapshot freshness statuses.
      * ``no_invention_audit`` -- closed-set ``PASSED`` /
        ``FAILED`` token. ``PASSED`` iff every refusal-bearing
        snapshot has ``None`` for its numeric value.
      * ``schema_version`` -- locked Stage 29.2 evidence schema
        version.
    """

    base_mint: str
    price_snapshot: Stage29_2BirdeyePriceSnapshot
    ath_snapshot: Stage29_2BirdeyeAthSnapshot
    drawdown_ratio: Optional[str]
    freshness_status: str
    no_invention_audit: str
    schema_version: str

    def __post_init__(self) -> None:
        _validate_evidence_record(self)


NO_INVENTION_AUDIT_PASSED: str = "PASSED"
NO_INVENTION_AUDIT_FAILED: str = "FAILED"


NO_INVENTION_AUDIT_VALUES: tuple[str, ...] = (
    NO_INVENTION_AUDIT_PASSED,
    NO_INVENTION_AUDIT_FAILED,
)


def is_no_invention_audit_value(value: object) -> bool:
    return (
        isinstance(value, str)
        and value in NO_INVENTION_AUDIT_VALUES
    )


def _validate_evidence_record(
    record: "Stage29_2BirdeyeEvidenceRecord",
) -> None:
    if not isinstance(record.base_mint, str):
        raise Stage29_2BirdeyeError("BASE_MINT_NOT_STR")
    if not isinstance(
        record.price_snapshot,
        Stage29_2BirdeyePriceSnapshot,
    ):
        raise Stage29_2BirdeyeError(
            "PRICE_SNAPSHOT_TYPE_INVALID"
        )
    if not isinstance(
        record.ath_snapshot, Stage29_2BirdeyeAthSnapshot
    ):
        raise Stage29_2BirdeyeError(
            "ATH_SNAPSHOT_TYPE_INVALID"
        )
    if record.drawdown_ratio is not None and not isinstance(
        record.drawdown_ratio, str
    ):
        raise Stage29_2BirdeyeError(
            "DRAWDOWN_RATIO_NOT_STR_OR_NONE"
        )
    if not is_birdeye_freshness_status_value(
        record.freshness_status
    ):
        raise Stage29_2BirdeyeError(
            "FRESHNESS_STATUS_NOT_CLOSED_SET"
        )
    if not is_no_invention_audit_value(
        record.no_invention_audit
    ):
        raise Stage29_2BirdeyeError(
            "NO_INVENTION_AUDIT_NOT_CLOSED_SET"
        )
    if not isinstance(record.schema_version, str):
        raise Stage29_2BirdeyeError("SCHEMA_VERSION_NOT_STR")


def build_birdeye_evidence_record(
    *,
    base_mint: str,
    price_snapshot: Stage29_2BirdeyePriceSnapshot,
    ath_snapshot: Stage29_2BirdeyeAthSnapshot,
    drawdown_ratio: Optional[str],
    freshness_status: str,
    no_invention_audit: str,
) -> Stage29_2BirdeyeEvidenceRecord:
    """Construct a validated ``Stage29_2BirdeyeEvidenceRecord``."""
    return Stage29_2BirdeyeEvidenceRecord(
        base_mint=base_mint,
        price_snapshot=price_snapshot,
        ath_snapshot=ath_snapshot,
        drawdown_ratio=drawdown_ratio,
        freshness_status=freshness_status,
        no_invention_audit=no_invention_audit,
        schema_version=STAGE29_2_BIRDEYE_EVIDENCE_SCHEMA_VERSION,
    )


__all__ = (
    "BIRDEYE_PRICE_STATUS_PRESENT",
    "BIRDEYE_PRICE_STATUS_MISSING",
    "BIRDEYE_PRICE_STATUS_STALE",
    "BIRDEYE_PRICE_STATUS_SOURCE_ERROR",
    "BIRDEYE_PRICE_STATUS_VALUES",
    "is_birdeye_price_status_value",
    "BIRDEYE_ATH_STATUS_PRESENT",
    "BIRDEYE_ATH_STATUS_MISSING",
    "BIRDEYE_ATH_STATUS_STALE",
    "BIRDEYE_ATH_STATUS_SOURCE_ERROR",
    "BIRDEYE_ATH_STATUS_VALUES",
    "is_birdeye_ath_status_value",
    "BIRDEYE_FRESHNESS_STATUS_FRESH",
    "BIRDEYE_FRESHNESS_STATUS_STALE",
    "BIRDEYE_FRESHNESS_STATUS_UNKNOWN",
    "BIRDEYE_FRESHNESS_STATUS_VALUES",
    "is_birdeye_freshness_status_value",
    "BIRDEYE_REFUSAL_REASON_NONE",
    "BIRDEYE_REFUSAL_REASON_ENDPOINT_MISSING",
    "BIRDEYE_REFUSAL_REASON_ENDPOINT_UNSAFE",
    "BIRDEYE_REFUSAL_REASON_API_KEY_MISSING",
    "BIRDEYE_REFUSAL_REASON_API_KEY_UNSAFE",
    "BIRDEYE_REFUSAL_REASON_LIVE_FLAG_NOT_SET",
    "BIRDEYE_REFUSAL_REASON_TIMEOUT_INVALID",
    "BIRDEYE_REFUSAL_REASON_HTTP_FAILED",
    "BIRDEYE_REFUSAL_REASON_HTTP_TIMEOUT",
    "BIRDEYE_REFUSAL_REASON_HTTP_STATUS_REJECTED",
    "BIRDEYE_REFUSAL_REASON_HTTP_SUCCESS_FALSE",
    "BIRDEYE_REFUSAL_REASON_BODY_MALFORMED",
    "BIRDEYE_REFUSAL_REASON_PRICE_MISSING_IN_BODY",
    "BIRDEYE_REFUSAL_REASON_ATH_SERIES_EMPTY",
    "BIRDEYE_REFUSAL_REASON_MINT_REJECTED_SAFE_SHAPE",
    "BIRDEYE_REFUSAL_REASON_BASE_URL_REJECTED",
    "BIRDEYE_REFUSAL_REASON_LOOKBACK_INVALID",
    "BIRDEYE_REFUSAL_REASON_OHLCV_TYPE_INVALID",
    "BIRDEYE_REFUSAL_REASON_MODE_INVALID",
    "BIRDEYE_REFUSAL_REASON_TRANSPORT_FACTORY_NOT_CALLABLE",
    "BIRDEYE_REFUSAL_REASON_VALUES",
    "is_birdeye_refusal_reason_value",
    "Stage29_2BirdeyeError",
    "Stage29_2BirdeyePriceSnapshot",
    "build_birdeye_price_snapshot",
    "Stage29_2BirdeyeAthSnapshot",
    "build_birdeye_ath_snapshot",
    "Stage29_2BirdeyeEvidenceRecord",
    "build_birdeye_evidence_record",
    "NO_INVENTION_AUDIT_PASSED",
    "NO_INVENTION_AUDIT_FAILED",
    "NO_INVENTION_AUDIT_VALUES",
    "is_no_invention_audit_value",
)

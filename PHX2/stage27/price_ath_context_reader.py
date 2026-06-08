"""Stage 27.4 price / ATH / migration context reader boundary.

Stage 27.4 defines the injectable Protocol surface for reading
price / ATH / migration snapshots and the deterministic functions
that translate a snapshot + a Stage 27.3 provider-ingest
composition output into an immutable Stage 27.4 context record.

Stage 27.4 deliberately does NOT:

  * open any provider connection,
  * call Helius / gRPC / Birdeye / Discord / Telegram / X-social,
  * read the process environment,
  * render a private ping,
  * send a private ping,
  * dedupe events,
  * run a runner,
  * enforce Stage 26 policy candidates,
  * accept a raw provider payload blob into a snapshot,
  * promote UNKNOWN / DISAGREE / USDC pair verdicts into the
    existing SOL calibration lane.

Source-boundary discipline:

  * Each Protocol method MUST return a closed-shape snapshot
    ``NamedTuple``; Stage 27.4 never reads a free-form dict from a
    real source at the model layer.
  * Real source implementations live OUTSIDE Stage 27.4 (e.g.
    Stage 27.5+ Birdeye / Helius adapters). Stage 27.4 only sees
    the snapshot.
  * Tests synthesize fakes that fulfil the Protocols using
    deterministic in-process data; tests must never reach a real
    network endpoint or read env values.

Clock discipline:

  * Stage 27.4 NEVER calls ``datetime.now()`` / ``time.time()``
    directly. Every wall-clock read goes through the injected
    ``Stage27_4Clock`` Protocol so tests can pin clock-dependent
    fields (``observed_at_utc``, ``staleness_seconds``,
    ``age_since_migration_seconds``).

This module imports only stdlib (``datetime`` / ``decimal`` /
``typing``) plus Stage 27.2, Stage 27.3, and Stage 27.4 production
modules. It does NOT import Stage 21-26 production code, does NOT
import Stage 27.1 production code, does NOT import any network /
RPC / messaging / DB / scheduler / secrets-management library,
does NOT read the process environment, does NOT define a CLI
surface, and contains no top-level I/O.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import NamedTuple, Optional, Protocol

from PHX2.stage27.migration_context_models import (
    MIGRATION_REASON_DISAGREE_PAIR_OBSERVE_ONLY,
    MIGRATION_REASON_INVALID_SOURCE_SNAPSHOT,
    MIGRATION_REASON_MALFORMED_TIMESTAMP,
    MIGRATION_REASON_MISSING_TIMESTAMP,
    MIGRATION_REASON_NO_MIGRATION_EVENT,
    MIGRATION_REASON_OK,
    MIGRATION_REASON_SOURCE_FAILED,
    MIGRATION_REASON_SOURCE_NOT_TRUSTED,
    MIGRATION_REASON_UNKNOWN_PAIR_OBSERVE_ONLY,
    MIGRATION_SOURCE_UNKNOWN,
    MIGRATION_SOURCE_VALUES,
    MIGRATION_SOURCES_TRUSTED,
    MIGRATION_STATUS_MISSING,
    MIGRATION_STATUS_PRESENT,
    MIGRATION_STATUS_SOURCE_ERROR,
    MIGRATION_STATUS_UNSUPPORTED_PAIR,
    MIGRATION_STATUS_UNTRUSTED,
    MigrationContextRecord,
    STAGE27_4_MIGRATION_SCHEMA_VERSION,
)
from PHX2.stage27.pair_detection_constants import (
    PAIR_DETECTION_STATUS_CONFIRMED,
    PAIR_DETECTION_STATUS_DISAGREE,
    PAIR_DETECTION_STATUS_PROVIDER_ONLY,
    PAIR_DETECTION_STATUS_UNRESOLVED,
    QUOTE_ASSET_SOL,
    QUOTE_ASSET_UNKNOWN,
    QUOTE_ASSET_USDC,
)
from PHX2.stage27.price_ath_context_contracts import (
    Stage27AthSourceError,
    Stage27MigrationSourceError,
    Stage27PriceSourceError,
)
from PHX2.stage27.price_ath_context_models import (
    ATH_REASON_DISAGREE_PAIR_OBSERVE_ONLY,
    ATH_REASON_INVALID_SOURCE_SNAPSHOT,
    ATH_REASON_NO_OBSERVATIONS,
    ATH_REASON_OK,
    ATH_REASON_PRE_MIGRATION_DATA_REJECTED,
    ATH_REASON_SOURCE_FAILED,
    ATH_REASON_UNKNOWN_PAIR_OBSERVE_ONLY,
    ATH_REASON_UNSUPPORTED_QUOTE_ASSET,
    ATH_REASON_USDC_OBSERVE_ONLY,
    ATH_SINCE_MIGRATION_STATUS_MAY_INCLUDE_PRE_MIGRATION,
    ATH_SINCE_MIGRATION_STATUS_NOT_APPLICABLE,
    ATH_SINCE_MIGRATION_STATUS_POST_MIGRATION_ONLY,
    ATH_SINCE_MIGRATION_STATUS_UNKNOWN,
    ATH_STATUS_PRESENT,
    ATH_STATUS_SOURCE_ERROR,
    ATH_STATUS_UNAVAILABLE,
    ATH_STATUS_UNSUPPORTED_PAIR,
    ATH_UNIT_UNKNOWN,
    ATH_UNIT_USD,
    ATH_UNIT_VALUES,
    AthContextRecord,
    DRAWDOWN_BASIS_FROM_POST_MIGRATION_ATH,
    DRAWDOWN_BASIS_NOT_APPLICABLE,
    DRAWDOWN_BASIS_UNKNOWN,
    PRICE_REASON_DISAGREE_PAIR_OBSERVE_ONLY,
    PRICE_REASON_INVALID_SOURCE_SNAPSHOT,
    PRICE_REASON_OK,
    PRICE_REASON_SOURCE_FAILED,
    PRICE_REASON_SOURCE_RETURNED_NONE,
    PRICE_REASON_STALE_THRESHOLD_EXCEEDED,
    PRICE_REASON_UNKNOWN_PAIR_OBSERVE_ONLY,
    PRICE_REASON_UNSUPPORTED_QUOTE_ASSET,
    PRICE_REASON_USDC_OBSERVE_ONLY,
    PRICE_STATUS_PRESENT,
    PRICE_STATUS_SOURCE_ERROR,
    PRICE_STATUS_STALE,
    PRICE_STATUS_UNAVAILABLE,
    PRICE_STATUS_UNSUPPORTED_PAIR,
    PRICE_UNIT_SOL,
    PRICE_UNIT_UNKNOWN,
    PRICE_UNIT_USD,
    PRICE_UNIT_USDC,
    PRICE_UNIT_VALUES,
    PriceContextRecord,
    STAGE27_4_PRICE_ATH_SCHEMA_VERSION,
)
from PHX2.stage27.provider_ingest_models import (
    ProviderIngestOutputRecord,
)


# ---------------------------------------------------------------------------
# Stage 27.4 clock Protocol
# ---------------------------------------------------------------------------


class Stage27_4Clock(Protocol):
    """Injectable clock boundary for Stage 27.4.

    The clock returns an aware UTC ``datetime``. Stage 27.4 NEVER
    calls ``datetime.now()`` / ``time.time()`` directly; every
    wall-clock read goes through this Protocol so tests can pin
    clock-dependent fields without monkeypatching stdlib.
    """

    def utc_now(self) -> datetime: ...


class FrozenStage27_4Clock(NamedTuple):
    """Deterministic clock that always returns a fixed UTC time.

    Used by Stage 27.4 tests to pin clock-dependent fields. Real
    callers may pass any object that fulfils ``Stage27_4Clock``.
    """

    fixed_utc: datetime

    def utc_now(self) -> datetime:
        return self.fixed_utc


# ---------------------------------------------------------------------------
# Stage 27.4 source snapshot shapes (closed; no raw payload field)
# ---------------------------------------------------------------------------


class PriceSourceSnapshot(NamedTuple):
    """Immutable price source snapshot.

    Carries only safe-to-display canonical fields projected from an
    upstream price source. No raw API payload, no secret, no
    webhook URL is admitted.

    Fields:

      * ``price_value``       -- canonical decimal-text price value;
                                 ``None`` when the upstream had
                                 nothing to report.
      * ``price_unit``        -- one of ``PRICE_UNIT_VALUES``.
      * ``source_label``      -- short safe-to-display source label.
      * ``fetched_at_utc``    -- ISO-8601 UTC fetch timestamp;
                                 ``None`` when upstream omitted it.
    """

    price_value: Optional[str]
    price_unit: str
    source_label: Optional[str]
    fetched_at_utc: Optional[str]


class AthSourceSnapshot(NamedTuple):
    """Immutable ATH source snapshot.

    Same redaction discipline as ``PriceSourceSnapshot``.

    Fields:

      * ``ath_value``                 -- canonical decimal-text ATH
                                         value; ``None`` when none.
      * ``ath_unit``                  -- one of ``ATH_UNIT_VALUES``.
      * ``source_label``              -- short safe-to-display label.
      * ``ath_observed_at_utc``       -- ISO-8601 UTC peak timestamp;
                                         ``None`` when missing.
      * ``window_starts_post_migration`` -- ``True`` iff the upstream
                                            window strictly starts
                                            at or after the migration
                                            event for the same token;
                                            ``False`` if the window
                                            may include pre-migration
                                            wick data; ``None`` when
                                            the upstream did not
                                            promise.
    """

    ath_value: Optional[str]
    ath_unit: str
    source_label: Optional[str]
    ath_observed_at_utc: Optional[str]
    window_starts_post_migration: Optional[bool]


class MigrationSourceSnapshot(NamedTuple):
    """Immutable migration source snapshot.

    Same redaction discipline as ``PriceSourceSnapshot``.

    Fields:

      * ``migration_event_id``     -- safe-to-display event id;
                                      ``None`` when missing.
      * ``migration_timestamp_utc`` -- ISO-8601 UTC migration
                                      timestamp; ``None`` when
                                      missing.
      * ``migration_source``       -- one of
                                      ``MIGRATION_SOURCE_VALUES``;
                                      defaults to UNKNOWN.
      * ``source_event_ref``       -- short safe-to-display upstream
                                      event reference; ``None`` when
                                      missing.
      * ``raw_capture_ref``        -- short safe-to-display upstream
                                      raw-capture reference; ``None``
                                      when missing. NEVER a payload
                                      blob.
    """

    migration_event_id: Optional[str]
    migration_timestamp_utc: Optional[str]
    migration_source: str
    source_event_ref: Optional[str]
    raw_capture_ref: Optional[str]


# ---------------------------------------------------------------------------
# Stage 27.4 source Protocols (injectable)
# ---------------------------------------------------------------------------


class PriceContextSource(Protocol):
    """Injectable boundary returning Stage 27.4 price snapshots.

    Real implementations live OUTSIDE Stage 27.4 (e.g. a Birdeye
    adapter in a later substage). Stage 27.4 only depends on this
    Protocol so tests can substitute deterministic fakes.

    Implementations MUST raise ``Stage27PriceSourceError`` for
    expected source failures and return a closed-shape
    ``PriceSourceSnapshot`` otherwise. Implementations MUST NOT
    raise raw library errors at the Stage 27.4 boundary.
    """

    def read_price_snapshot(
        self,
        token_mint: str,
        *,
        pair_quote_asset: str,
    ) -> PriceSourceSnapshot: ...


class AthContextSource(Protocol):
    """Injectable boundary returning Stage 27.4 ATH snapshots."""

    def read_ath_snapshot(
        self,
        token_mint: str,
        *,
        pair_quote_asset: str,
    ) -> AthSourceSnapshot: ...


class MigrationContextSource(Protocol):
    """Injectable boundary returning Stage 27.4 migration snapshots."""

    def read_migration_snapshot(
        self,
        token_mint: str,
    ) -> MigrationSourceSnapshot: ...


# ---------------------------------------------------------------------------
# Pair-aware helpers
# ---------------------------------------------------------------------------


def _pair_admits_trusted_sol_lane(
    ingest_output: ProviderIngestOutputRecord,
) -> bool:
    """Return ``True`` iff the pair verdict admits SOL-lane context.

    Locked rule: only ``CONFIRMED`` / ``PROVIDER_ONLY`` SOL verdicts
    map to SOL-lane trusted context. USDC, UNKNOWN, and DISAGREE
    NEVER promote to SOL-lane semantics.
    """
    if ingest_output.pair_quote_asset != QUOTE_ASSET_SOL:
        return False
    return ingest_output.pair_detection_status in (
        PAIR_DETECTION_STATUS_CONFIRMED,
        PAIR_DETECTION_STATUS_PROVIDER_ONLY,
    )


def _pair_admits_usdc_observe_only(
    ingest_output: ProviderIngestOutputRecord,
) -> bool:
    if ingest_output.pair_quote_asset != QUOTE_ASSET_USDC:
        return False
    return ingest_output.pair_detection_status in (
        PAIR_DETECTION_STATUS_CONFIRMED,
        PAIR_DETECTION_STATUS_PROVIDER_ONLY,
    )


def _expected_unit_for_quote_asset(quote_asset: str) -> str:
    """Return the natural Stage 27.4 ``price_unit`` / ``ath_unit``
    for a Stage 27.2 ``QUOTE_ASSET`` verdict.

    Pure / deterministic. Stage 27.4 NEVER silently promotes
    UNKNOWN to SOL.
    """
    if quote_asset == QUOTE_ASSET_SOL:
        return PRICE_UNIT_SOL
    if quote_asset == QUOTE_ASSET_USDC:
        return PRICE_UNIT_USDC
    return PRICE_UNIT_UNKNOWN


def _compute_seconds_between(
    earlier_utc: Optional[str],
    later_utc: Optional[str],
) -> Optional[int]:
    """Return non-negative integer seconds between two ISO-8601 UTC
    strings.

    Returns ``None`` when either side is missing or malformed.
    Stage 27.4 never returns a negative delta.
    """
    if not isinstance(earlier_utc, str) or earlier_utc == "":
        return None
    if not isinstance(later_utc, str) or later_utc == "":
        return None
    try:
        earlier = _parse_iso_utc(earlier_utc)
        later = _parse_iso_utc(later_utc)
    except ValueError:
        return None
    delta = (later - earlier).total_seconds()
    if delta < 0:
        delta = 0.0
    return int(delta)


def _parse_iso_utc(value: str) -> datetime:
    """Parse an ISO-8601 UTC timestamp into an aware ``datetime``.

    Accepts both ``"2026-05-22T12:34:56Z"`` and
    ``"2026-05-22T12:34:56+00:00"`` shapes. Raises ``ValueError``
    otherwise.
    """
    candidate = value
    if candidate.endswith("Z"):
        candidate = candidate[:-1] + "+00:00"
    parsed = datetime.fromisoformat(candidate)
    if parsed.tzinfo is None:
        raise ValueError("Stage 27.4 requires tz-aware UTC timestamps")
    return parsed.astimezone(timezone.utc)


def _iso_utc(value: datetime) -> str:
    """Render an aware UTC ``datetime`` as a canonical ISO-8601
    string ending in ``+00:00`` (Stage 27.4 NEVER emits naive
    timestamps).
    """
    aware = value.astimezone(timezone.utc)
    return aware.isoformat()


# ---------------------------------------------------------------------------
# Price context record builders
# ---------------------------------------------------------------------------


def build_unsupported_price_context(
    ingest_output: ProviderIngestOutputRecord,
    *,
    clock: Stage27_4Clock,
    reason: str,
) -> PriceContextRecord:
    """Build an ``UNSUPPORTED_PAIR`` Stage 27.4 price context record.

    Used when the pair verdict is UNKNOWN / DISAGREE: no trusted
    price context is promoted, but the record still carries the
    canonical pair fields and clock-driven ``observed_at_utc``.
    """
    return PriceContextRecord(
        token_mint=ingest_output.token_mint,
        pair_type=ingest_output.pair_pair_type,
        quote_asset=ingest_output.pair_quote_asset,
        quote_mint=ingest_output.quote_mint,
        price_value=None,
        price_unit=PRICE_UNIT_UNKNOWN,
        price_source=None,
        fetched_at_utc=None,
        observed_at_utc=_iso_utc(clock.utc_now()),
        staleness_seconds=None,
        price_status=PRICE_STATUS_UNSUPPORTED_PAIR,
        price_reason=reason,
        schema_version=STAGE27_4_PRICE_ATH_SCHEMA_VERSION,
    )


def build_price_context_record(
    snapshot: PriceSourceSnapshot,
    ingest_output: ProviderIngestOutputRecord,
    *,
    clock: Stage27_4Clock,
    staleness_threshold_seconds: int,
) -> PriceContextRecord:
    """Translate a deterministic ``PriceSourceSnapshot`` into a
    Stage 27.4 ``PriceContextRecord``.

    Pair-awareness rules (locked):

      * UNKNOWN pair        -> ``UNSUPPORTED_PAIR`` /
                                ``UNKNOWN_PAIR_OBSERVE_ONLY``.
      * DISAGREE pair       -> ``UNSUPPORTED_PAIR`` /
                                ``DISAGREE_PAIR_OBSERVE_ONLY``.
      * USDC observe-only   -> ``PRESENT`` USDC-lane record, but
                                ``price_unit`` stays USDC -- never
                                converted into SOL.
      * SOL CONFIRMED/PROV  -> trusted SOL-lane price record.

    Staleness rules:

      * ``staleness_seconds`` is computed from ``fetched_at_utc`` and
        clock-driven ``observed_at_utc``.
      * If ``staleness_seconds`` exceeds ``staleness_threshold_seconds``
        the status downgrades to ``STALE`` with reason
        ``STALE_THRESHOLD_EXCEEDED``.

    Missing-price rules:

      * ``snapshot.price_value is None`` -> ``UNAVAILABLE`` /
        ``SOURCE_RETURNED_NONE``. Stage 27.4 NEVER treats ``0.0`` /
        ``"0"`` as missing.
    """
    if (
        ingest_output.pair_detection_status
        == PAIR_DETECTION_STATUS_UNRESOLVED
    ):
        return build_unsupported_price_context(
            ingest_output,
            clock=clock,
            reason=PRICE_REASON_UNKNOWN_PAIR_OBSERVE_ONLY,
        )
    if (
        ingest_output.pair_detection_status
        == PAIR_DETECTION_STATUS_DISAGREE
    ):
        return build_unsupported_price_context(
            ingest_output,
            clock=clock,
            reason=PRICE_REASON_DISAGREE_PAIR_OBSERVE_ONLY,
        )
    if ingest_output.pair_quote_asset == QUOTE_ASSET_UNKNOWN:
        return build_unsupported_price_context(
            ingest_output,
            clock=clock,
            reason=PRICE_REASON_UNKNOWN_PAIR_OBSERVE_ONLY,
        )

    if not isinstance(snapshot, PriceSourceSnapshot):
        return PriceContextRecord(
            token_mint=ingest_output.token_mint,
            pair_type=ingest_output.pair_pair_type,
            quote_asset=ingest_output.pair_quote_asset,
            quote_mint=ingest_output.quote_mint,
            price_value=None,
            price_unit=PRICE_UNIT_UNKNOWN,
            price_source=None,
            fetched_at_utc=None,
            observed_at_utc=_iso_utc(clock.utc_now()),
            staleness_seconds=None,
            price_status=PRICE_STATUS_SOURCE_ERROR,
            price_reason=PRICE_REASON_INVALID_SOURCE_SNAPSHOT,
            schema_version=STAGE27_4_PRICE_ATH_SCHEMA_VERSION,
        )

    if snapshot.price_unit not in PRICE_UNIT_VALUES:
        return PriceContextRecord(
            token_mint=ingest_output.token_mint,
            pair_type=ingest_output.pair_pair_type,
            quote_asset=ingest_output.pair_quote_asset,
            quote_mint=ingest_output.quote_mint,
            price_value=None,
            price_unit=PRICE_UNIT_UNKNOWN,
            price_source=snapshot.source_label,
            fetched_at_utc=snapshot.fetched_at_utc,
            observed_at_utc=_iso_utc(clock.utc_now()),
            staleness_seconds=None,
            price_status=PRICE_STATUS_SOURCE_ERROR,
            price_reason=PRICE_REASON_INVALID_SOURCE_SNAPSHOT,
            schema_version=STAGE27_4_PRICE_ATH_SCHEMA_VERSION,
        )

    # Locked: USDC measurement lane must stay USDC; never converted
    # into SOL-lane assumptions. A SOL-pair snapshot reporting a
    # USDC unit (or vice versa) is rejected as an unsupported quote
    # asset. ``PRICE_UNIT_USD`` is admitted on any pair as a Birdeye-
    # compatible display unit -- SOL pair stays a SOL pair (the
    # ``quote_asset`` field is unchanged); only the display unit is
    # USD. The Stage 27.4 ATH path already admits ``ATH_UNIT_USD``
    # the same way.
    expected_unit = _expected_unit_for_quote_asset(
        ingest_output.pair_quote_asset
    )
    if (
        expected_unit != PRICE_UNIT_UNKNOWN
        and snapshot.price_unit != expected_unit
        and snapshot.price_unit != PRICE_UNIT_USD
    ):
        return PriceContextRecord(
            token_mint=ingest_output.token_mint,
            pair_type=ingest_output.pair_pair_type,
            quote_asset=ingest_output.pair_quote_asset,
            quote_mint=ingest_output.quote_mint,
            price_value=None,
            price_unit=snapshot.price_unit,
            price_source=snapshot.source_label,
            fetched_at_utc=snapshot.fetched_at_utc,
            observed_at_utc=_iso_utc(clock.utc_now()),
            staleness_seconds=None,
            price_status=PRICE_STATUS_UNSUPPORTED_PAIR,
            price_reason=PRICE_REASON_UNSUPPORTED_QUOTE_ASSET,
            schema_version=STAGE27_4_PRICE_ATH_SCHEMA_VERSION,
        )

    observed_iso = _iso_utc(clock.utc_now())
    if snapshot.price_value is None:
        return PriceContextRecord(
            token_mint=ingest_output.token_mint,
            pair_type=ingest_output.pair_pair_type,
            quote_asset=ingest_output.pair_quote_asset,
            quote_mint=ingest_output.quote_mint,
            price_value=None,
            price_unit=snapshot.price_unit,
            price_source=snapshot.source_label,
            fetched_at_utc=snapshot.fetched_at_utc,
            observed_at_utc=observed_iso,
            staleness_seconds=None,
            price_status=PRICE_STATUS_UNAVAILABLE,
            price_reason=PRICE_REASON_SOURCE_RETURNED_NONE,
            schema_version=STAGE27_4_PRICE_ATH_SCHEMA_VERSION,
        )

    staleness = _compute_seconds_between(
        snapshot.fetched_at_utc, observed_iso
    )
    if (
        staleness is not None
        and staleness > staleness_threshold_seconds
    ):
        return PriceContextRecord(
            token_mint=ingest_output.token_mint,
            pair_type=ingest_output.pair_pair_type,
            quote_asset=ingest_output.pair_quote_asset,
            quote_mint=ingest_output.quote_mint,
            price_value=snapshot.price_value,
            price_unit=snapshot.price_unit,
            price_source=snapshot.source_label,
            fetched_at_utc=snapshot.fetched_at_utc,
            observed_at_utc=observed_iso,
            staleness_seconds=staleness,
            price_status=PRICE_STATUS_STALE,
            price_reason=PRICE_REASON_STALE_THRESHOLD_EXCEEDED,
            schema_version=STAGE27_4_PRICE_ATH_SCHEMA_VERSION,
        )

    if _pair_admits_usdc_observe_only(ingest_output):
        present_reason = PRICE_REASON_USDC_OBSERVE_ONLY
    else:
        present_reason = PRICE_REASON_OK

    return PriceContextRecord(
        token_mint=ingest_output.token_mint,
        pair_type=ingest_output.pair_pair_type,
        quote_asset=ingest_output.pair_quote_asset,
        quote_mint=ingest_output.quote_mint,
        price_value=snapshot.price_value,
        price_unit=snapshot.price_unit,
        price_source=snapshot.source_label,
        fetched_at_utc=snapshot.fetched_at_utc,
        observed_at_utc=observed_iso,
        staleness_seconds=staleness,
        price_status=PRICE_STATUS_PRESENT,
        price_reason=present_reason,
        schema_version=STAGE27_4_PRICE_ATH_SCHEMA_VERSION,
    )


def read_price_context(
    source: PriceContextSource,
    ingest_output: ProviderIngestOutputRecord,
    *,
    clock: Stage27_4Clock,
    staleness_threshold_seconds: int,
) -> PriceContextRecord:
    """Read a Stage 27.4 price context record via an injected source.

    Translates expected source failures
    (``Stage27PriceSourceError``) into a ``SOURCE_ERROR`` record so
    the per-event loop never crashes.
    """
    if (
        ingest_output.token_mint is None
        or ingest_output.token_mint == ""
    ):
        return build_unsupported_price_context(
            ingest_output,
            clock=clock,
            reason=PRICE_REASON_UNKNOWN_PAIR_OBSERVE_ONLY,
        )
    try:
        snapshot = source.read_price_snapshot(
            ingest_output.token_mint,
            pair_quote_asset=ingest_output.pair_quote_asset,
        )
    except Stage27PriceSourceError:
        return PriceContextRecord(
            token_mint=ingest_output.token_mint,
            pair_type=ingest_output.pair_pair_type,
            quote_asset=ingest_output.pair_quote_asset,
            quote_mint=ingest_output.quote_mint,
            price_value=None,
            price_unit=PRICE_UNIT_UNKNOWN,
            price_source=None,
            fetched_at_utc=None,
            observed_at_utc=_iso_utc(clock.utc_now()),
            staleness_seconds=None,
            price_status=PRICE_STATUS_SOURCE_ERROR,
            price_reason=PRICE_REASON_SOURCE_FAILED,
            schema_version=STAGE27_4_PRICE_ATH_SCHEMA_VERSION,
        )
    return build_price_context_record(
        snapshot,
        ingest_output,
        clock=clock,
        staleness_threshold_seconds=staleness_threshold_seconds,
    )


# ---------------------------------------------------------------------------
# ATH context record builders
# ---------------------------------------------------------------------------


def build_unsupported_ath_context(
    ingest_output: ProviderIngestOutputRecord,
    *,
    reason: str,
) -> AthContextRecord:
    """Build an ``UNSUPPORTED_PAIR`` Stage 27.4 ATH context record.

    Used when the pair verdict is UNKNOWN / DISAGREE: no trusted
    ATH context is promoted, but the record still carries the
    canonical pair fields.
    """
    return AthContextRecord(
        token_mint=ingest_output.token_mint,
        pair_type=ingest_output.pair_pair_type,
        quote_asset=ingest_output.pair_quote_asset,
        ath_value=None,
        ath_unit=ATH_UNIT_UNKNOWN,
        ath_source=None,
        ath_observed_at_utc=None,
        ath_since_migration_status=(
            ATH_SINCE_MIGRATION_STATUS_NOT_APPLICABLE
        ),
        drawdown_from_ath=None,
        drawdown_unit=ATH_UNIT_UNKNOWN,
        drawdown_basis=DRAWDOWN_BASIS_NOT_APPLICABLE,
        ath_status=ATH_STATUS_UNSUPPORTED_PAIR,
        ath_reason=reason,
        schema_version=STAGE27_4_PRICE_ATH_SCHEMA_VERSION,
    )


def build_ath_context_record(
    snapshot: AthSourceSnapshot,
    ingest_output: ProviderIngestOutputRecord,
    *,
    migration_record: Optional[MigrationContextRecord] = None,
    current_price_record: Optional[PriceContextRecord] = None,
) -> AthContextRecord:
    """Translate a deterministic ``AthSourceSnapshot`` into a
    Stage 27.4 ``AthContextRecord``.

    Pair-awareness rules (locked):

      * UNKNOWN / DISAGREE pair -> ``UNSUPPORTED_PAIR``.
      * USDC pair               -> ATH snapshot is surfaced but
                                    flagged ``USDC_OBSERVE_ONLY``;
                                    USDC ATH must NEVER be re-used
                                    against the existing SOL
                                    calibration lane.
      * SOL CONFIRMED/PROV      -> trusted SOL-lane ATH record.

    Post-migration discipline:

      * If ``snapshot.window_starts_post_migration is True`` AND a
        present migration record is supplied, the ATH is recorded as
        ``POST_MIGRATION_ONLY``. Otherwise the ATH is recorded as
        ``MAY_INCLUDE_PRE_MIGRATION`` and the drawdown is NOT
        computed. Stage 27.4 NEVER claims POST_MIGRATION_ONLY when
        the underlying source did not promise it.

    Missing-ATH rules:

      * ``snapshot.ath_value is None`` -> ``UNAVAILABLE`` /
        ``NO_OBSERVATIONS``.
    """
    if (
        ingest_output.pair_detection_status
        == PAIR_DETECTION_STATUS_UNRESOLVED
    ):
        return build_unsupported_ath_context(
            ingest_output,
            reason=ATH_REASON_UNKNOWN_PAIR_OBSERVE_ONLY,
        )
    if (
        ingest_output.pair_detection_status
        == PAIR_DETECTION_STATUS_DISAGREE
    ):
        return build_unsupported_ath_context(
            ingest_output,
            reason=ATH_REASON_DISAGREE_PAIR_OBSERVE_ONLY,
        )
    if ingest_output.pair_quote_asset == QUOTE_ASSET_UNKNOWN:
        return build_unsupported_ath_context(
            ingest_output,
            reason=ATH_REASON_UNKNOWN_PAIR_OBSERVE_ONLY,
        )
    if _pair_admits_usdc_observe_only(ingest_output):
        usdc_ath_reason: Optional[str] = ATH_REASON_USDC_OBSERVE_ONLY
    else:
        usdc_ath_reason = None

    if not isinstance(snapshot, AthSourceSnapshot):
        return AthContextRecord(
            token_mint=ingest_output.token_mint,
            pair_type=ingest_output.pair_pair_type,
            quote_asset=ingest_output.pair_quote_asset,
            ath_value=None,
            ath_unit=ATH_UNIT_UNKNOWN,
            ath_source=None,
            ath_observed_at_utc=None,
            ath_since_migration_status=(
                ATH_SINCE_MIGRATION_STATUS_UNKNOWN
            ),
            drawdown_from_ath=None,
            drawdown_unit=ATH_UNIT_UNKNOWN,
            drawdown_basis=DRAWDOWN_BASIS_UNKNOWN,
            ath_status=ATH_STATUS_SOURCE_ERROR,
            ath_reason=ATH_REASON_INVALID_SOURCE_SNAPSHOT,
            schema_version=STAGE27_4_PRICE_ATH_SCHEMA_VERSION,
        )

    if snapshot.ath_unit not in ATH_UNIT_VALUES:
        return AthContextRecord(
            token_mint=ingest_output.token_mint,
            pair_type=ingest_output.pair_pair_type,
            quote_asset=ingest_output.pair_quote_asset,
            ath_value=None,
            ath_unit=ATH_UNIT_UNKNOWN,
            ath_source=snapshot.source_label,
            ath_observed_at_utc=snapshot.ath_observed_at_utc,
            ath_since_migration_status=(
                ATH_SINCE_MIGRATION_STATUS_UNKNOWN
            ),
            drawdown_from_ath=None,
            drawdown_unit=ATH_UNIT_UNKNOWN,
            drawdown_basis=DRAWDOWN_BASIS_UNKNOWN,
            ath_status=ATH_STATUS_SOURCE_ERROR,
            ath_reason=ATH_REASON_INVALID_SOURCE_SNAPSHOT,
            schema_version=STAGE27_4_PRICE_ATH_SCHEMA_VERSION,
        )

    expected_unit = _expected_unit_for_quote_asset(
        ingest_output.pair_quote_asset
    )
    if (
        expected_unit != PRICE_UNIT_UNKNOWN
        and snapshot.ath_unit != expected_unit
        and snapshot.ath_unit != ATH_UNIT_USD
    ):
        return AthContextRecord(
            token_mint=ingest_output.token_mint,
            pair_type=ingest_output.pair_pair_type,
            quote_asset=ingest_output.pair_quote_asset,
            ath_value=None,
            ath_unit=snapshot.ath_unit,
            ath_source=snapshot.source_label,
            ath_observed_at_utc=snapshot.ath_observed_at_utc,
            ath_since_migration_status=(
                ATH_SINCE_MIGRATION_STATUS_UNKNOWN
            ),
            drawdown_from_ath=None,
            drawdown_unit=snapshot.ath_unit,
            drawdown_basis=DRAWDOWN_BASIS_UNKNOWN,
            ath_status=ATH_STATUS_UNSUPPORTED_PAIR,
            ath_reason=ATH_REASON_UNSUPPORTED_QUOTE_ASSET,
            schema_version=STAGE27_4_PRICE_ATH_SCHEMA_VERSION,
        )

    if snapshot.ath_value is None:
        return AthContextRecord(
            token_mint=ingest_output.token_mint,
            pair_type=ingest_output.pair_pair_type,
            quote_asset=ingest_output.pair_quote_asset,
            ath_value=None,
            ath_unit=snapshot.ath_unit,
            ath_source=snapshot.source_label,
            ath_observed_at_utc=snapshot.ath_observed_at_utc,
            ath_since_migration_status=(
                ATH_SINCE_MIGRATION_STATUS_NOT_APPLICABLE
            ),
            drawdown_from_ath=None,
            drawdown_unit=snapshot.ath_unit,
            drawdown_basis=DRAWDOWN_BASIS_NOT_APPLICABLE,
            ath_status=ATH_STATUS_UNAVAILABLE,
            ath_reason=ATH_REASON_NO_OBSERVATIONS,
            schema_version=STAGE27_4_PRICE_ATH_SCHEMA_VERSION,
        )

    has_present_migration = (
        migration_record is not None
        and migration_record.migration_status
        == MIGRATION_STATUS_PRESENT
    )
    if (
        snapshot.window_starts_post_migration is True
        and has_present_migration
    ):
        since_status = (
            ATH_SINCE_MIGRATION_STATUS_POST_MIGRATION_ONLY
        )
        drawdown = _compute_drawdown(
            snapshot.ath_value,
            current_price_record,
            snapshot.ath_unit,
        )
        if drawdown is None:
            drawdown_basis = DRAWDOWN_BASIS_NOT_APPLICABLE
        else:
            drawdown_basis = DRAWDOWN_BASIS_FROM_POST_MIGRATION_ATH
        reason = (
            usdc_ath_reason
            if usdc_ath_reason is not None
            else ATH_REASON_OK
        )
        return AthContextRecord(
            token_mint=ingest_output.token_mint,
            pair_type=ingest_output.pair_pair_type,
            quote_asset=ingest_output.pair_quote_asset,
            ath_value=snapshot.ath_value,
            ath_unit=snapshot.ath_unit,
            ath_source=snapshot.source_label,
            ath_observed_at_utc=snapshot.ath_observed_at_utc,
            ath_since_migration_status=since_status,
            drawdown_from_ath=drawdown,
            drawdown_unit=snapshot.ath_unit,
            drawdown_basis=drawdown_basis,
            ath_status=ATH_STATUS_PRESENT,
            ath_reason=reason,
            schema_version=STAGE27_4_PRICE_ATH_SCHEMA_VERSION,
        )

    # Stage 27.4 refuses to claim POST_MIGRATION_ONLY without an
    # explicit upstream promise + a present migration record. The
    # ATH snapshot is still surfaced (so the operator review packet
    # can show "we saw an ATH but cannot promise it is strictly
    # post-migration"), but the drawdown is NOT computed.
    reason = (
        usdc_ath_reason
        if usdc_ath_reason is not None
        else ATH_REASON_PRE_MIGRATION_DATA_REJECTED
    )
    return AthContextRecord(
        token_mint=ingest_output.token_mint,
        pair_type=ingest_output.pair_pair_type,
        quote_asset=ingest_output.pair_quote_asset,
        ath_value=snapshot.ath_value,
        ath_unit=snapshot.ath_unit,
        ath_source=snapshot.source_label,
        ath_observed_at_utc=snapshot.ath_observed_at_utc,
        ath_since_migration_status=(
            ATH_SINCE_MIGRATION_STATUS_MAY_INCLUDE_PRE_MIGRATION
        ),
        drawdown_from_ath=None,
        drawdown_unit=snapshot.ath_unit,
        drawdown_basis=DRAWDOWN_BASIS_NOT_APPLICABLE,
        ath_status=ATH_STATUS_PRESENT,
        ath_reason=reason,
        schema_version=STAGE27_4_PRICE_ATH_SCHEMA_VERSION,
    )


def _compute_drawdown(
    ath_value: str,
    current_price_record: Optional[PriceContextRecord],
    ath_unit: str,
) -> Optional[str]:
    """Compute ``ath_value - current_price`` as canonical decimal text.

    The drawdown REQUIRES a ``PRICE_STATUS_PRESENT`` current price.
    A ``STALE`` current price preserves the ATH (the caller still
    surfaces ``ath_value`` and the post-migration window) but yields
    NO usable drawdown -- Stage 30.11.12 fails closed so a stale
    current price can never drive a drawdown / tier / private ping.

    Returns ``None`` when the current price is missing, NOT PRESENT
    (e.g. ``STALE`` / ``UNAVAILABLE`` / ``SOURCE_ERROR``), when units
    disagree, or when arithmetic fails. Pure / deterministic.
    """
    if current_price_record is None:
        return None
    if current_price_record.price_status != PRICE_STATUS_PRESENT:
        return None
    if current_price_record.price_value is None:
        return None
    if current_price_record.price_unit != ath_unit:
        return None
    try:
        ath_dec = Decimal(ath_value)
        cur_dec = Decimal(current_price_record.price_value)
    except (ValueError, ArithmeticError, TypeError):
        return None
    diff = ath_dec - cur_dec
    if diff < 0:
        diff = Decimal("0")
    return format(diff, "f")


def read_ath_context(
    source: AthContextSource,
    ingest_output: ProviderIngestOutputRecord,
    *,
    migration_record: Optional[MigrationContextRecord] = None,
    current_price_record: Optional[PriceContextRecord] = None,
) -> AthContextRecord:
    """Read a Stage 27.4 ATH context record via an injected source.

    Translates expected source failures (``Stage27AthSourceError``)
    into a ``SOURCE_ERROR`` record.
    """
    if (
        ingest_output.token_mint is None
        or ingest_output.token_mint == ""
    ):
        return build_unsupported_ath_context(
            ingest_output,
            reason=ATH_REASON_UNKNOWN_PAIR_OBSERVE_ONLY,
        )
    try:
        snapshot = source.read_ath_snapshot(
            ingest_output.token_mint,
            pair_quote_asset=ingest_output.pair_quote_asset,
        )
    except Stage27AthSourceError:
        return AthContextRecord(
            token_mint=ingest_output.token_mint,
            pair_type=ingest_output.pair_pair_type,
            quote_asset=ingest_output.pair_quote_asset,
            ath_value=None,
            ath_unit=ATH_UNIT_UNKNOWN,
            ath_source=None,
            ath_observed_at_utc=None,
            ath_since_migration_status=(
                ATH_SINCE_MIGRATION_STATUS_UNKNOWN
            ),
            drawdown_from_ath=None,
            drawdown_unit=ATH_UNIT_UNKNOWN,
            drawdown_basis=DRAWDOWN_BASIS_UNKNOWN,
            ath_status=ATH_STATUS_SOURCE_ERROR,
            ath_reason=ATH_REASON_SOURCE_FAILED,
            schema_version=STAGE27_4_PRICE_ATH_SCHEMA_VERSION,
        )
    return build_ath_context_record(
        snapshot,
        ingest_output,
        migration_record=migration_record,
        current_price_record=current_price_record,
    )


# ---------------------------------------------------------------------------
# Migration context record builders
# ---------------------------------------------------------------------------


def build_unsupported_migration_context(
    ingest_output: ProviderIngestOutputRecord,
    *,
    clock: Stage27_4Clock,
    reason: str,
) -> MigrationContextRecord:
    """Build an ``UNSUPPORTED_PAIR`` migration context record."""
    return MigrationContextRecord(
        token_mint=ingest_output.token_mint,
        pair_type=ingest_output.pair_pair_type,
        quote_asset=ingest_output.pair_quote_asset,
        migration_event_id=None,
        migration_timestamp_utc=None,
        migration_source=MIGRATION_SOURCE_UNKNOWN,
        migration_status=MIGRATION_STATUS_UNSUPPORTED_PAIR,
        migration_reason=reason,
        age_since_migration_seconds=None,
        observed_at_utc=_iso_utc(clock.utc_now()),
        source_event_ref=None,
        raw_capture_ref=None,
        schema_version=STAGE27_4_MIGRATION_SCHEMA_VERSION,
    )


def build_migration_context_record(
    snapshot: MigrationSourceSnapshot,
    ingest_output: ProviderIngestOutputRecord,
    *,
    clock: Stage27_4Clock,
) -> MigrationContextRecord:
    """Translate a deterministic ``MigrationSourceSnapshot`` into a
    Stage 27.4 ``MigrationContextRecord``.

    Pair-awareness rules:

      * UNKNOWN / DISAGREE pair -> ``UNSUPPORTED_PAIR``.

    Trust rules:

      * Trusted sources (on-chain migration event / operator
        override) with a parseable timestamp -> ``PRESENT``.
      * Untrusted source -> ``UNTRUSTED``.

    Missing-timestamp rules:

      * ``snapshot.migration_timestamp_utc is None`` -> ``MISSING`` /
        ``MISSING_TIMESTAMP``. The function MUST NOT crash.
    """
    if (
        ingest_output.pair_detection_status
        == PAIR_DETECTION_STATUS_UNRESOLVED
    ):
        return build_unsupported_migration_context(
            ingest_output,
            clock=clock,
            reason=MIGRATION_REASON_UNKNOWN_PAIR_OBSERVE_ONLY,
        )
    if (
        ingest_output.pair_detection_status
        == PAIR_DETECTION_STATUS_DISAGREE
    ):
        return build_unsupported_migration_context(
            ingest_output,
            clock=clock,
            reason=MIGRATION_REASON_DISAGREE_PAIR_OBSERVE_ONLY,
        )
    if ingest_output.pair_quote_asset == QUOTE_ASSET_UNKNOWN:
        return build_unsupported_migration_context(
            ingest_output,
            clock=clock,
            reason=MIGRATION_REASON_UNKNOWN_PAIR_OBSERVE_ONLY,
        )

    observed_iso = _iso_utc(clock.utc_now())

    if not isinstance(snapshot, MigrationSourceSnapshot):
        return MigrationContextRecord(
            token_mint=ingest_output.token_mint,
            pair_type=ingest_output.pair_pair_type,
            quote_asset=ingest_output.pair_quote_asset,
            migration_event_id=None,
            migration_timestamp_utc=None,
            migration_source=MIGRATION_SOURCE_UNKNOWN,
            migration_status=MIGRATION_STATUS_SOURCE_ERROR,
            migration_reason=(
                MIGRATION_REASON_INVALID_SOURCE_SNAPSHOT
            ),
            age_since_migration_seconds=None,
            observed_at_utc=observed_iso,
            source_event_ref=None,
            raw_capture_ref=None,
            schema_version=STAGE27_4_MIGRATION_SCHEMA_VERSION,
        )

    if snapshot.migration_source not in MIGRATION_SOURCE_VALUES:
        normalized_source = MIGRATION_SOURCE_UNKNOWN
    else:
        normalized_source = snapshot.migration_source

    if snapshot.migration_timestamp_utc is None:
        if snapshot.migration_event_id is None:
            reason = MIGRATION_REASON_NO_MIGRATION_EVENT
        else:
            reason = MIGRATION_REASON_MISSING_TIMESTAMP
        return MigrationContextRecord(
            token_mint=ingest_output.token_mint,
            pair_type=ingest_output.pair_pair_type,
            quote_asset=ingest_output.pair_quote_asset,
            migration_event_id=snapshot.migration_event_id,
            migration_timestamp_utc=None,
            migration_source=normalized_source,
            migration_status=MIGRATION_STATUS_MISSING,
            migration_reason=reason,
            age_since_migration_seconds=None,
            observed_at_utc=observed_iso,
            source_event_ref=snapshot.source_event_ref,
            raw_capture_ref=snapshot.raw_capture_ref,
            schema_version=STAGE27_4_MIGRATION_SCHEMA_VERSION,
        )

    try:
        _parse_iso_utc(snapshot.migration_timestamp_utc)
    except ValueError:
        return MigrationContextRecord(
            token_mint=ingest_output.token_mint,
            pair_type=ingest_output.pair_pair_type,
            quote_asset=ingest_output.pair_quote_asset,
            migration_event_id=snapshot.migration_event_id,
            migration_timestamp_utc=None,
            migration_source=normalized_source,
            migration_status=MIGRATION_STATUS_MISSING,
            migration_reason=MIGRATION_REASON_MALFORMED_TIMESTAMP,
            age_since_migration_seconds=None,
            observed_at_utc=observed_iso,
            source_event_ref=snapshot.source_event_ref,
            raw_capture_ref=snapshot.raw_capture_ref,
            schema_version=STAGE27_4_MIGRATION_SCHEMA_VERSION,
        )

    age = _compute_seconds_between(
        snapshot.migration_timestamp_utc, observed_iso
    )

    if normalized_source in MIGRATION_SOURCES_TRUSTED:
        status = MIGRATION_STATUS_PRESENT
        reason = MIGRATION_REASON_OK
    else:
        status = MIGRATION_STATUS_UNTRUSTED
        reason = MIGRATION_REASON_SOURCE_NOT_TRUSTED

    return MigrationContextRecord(
        token_mint=ingest_output.token_mint,
        pair_type=ingest_output.pair_pair_type,
        quote_asset=ingest_output.pair_quote_asset,
        migration_event_id=snapshot.migration_event_id,
        migration_timestamp_utc=snapshot.migration_timestamp_utc,
        migration_source=normalized_source,
        migration_status=status,
        migration_reason=reason,
        age_since_migration_seconds=age,
        observed_at_utc=observed_iso,
        source_event_ref=snapshot.source_event_ref,
        raw_capture_ref=snapshot.raw_capture_ref,
        schema_version=STAGE27_4_MIGRATION_SCHEMA_VERSION,
    )


def read_migration_context(
    source: MigrationContextSource,
    ingest_output: ProviderIngestOutputRecord,
    *,
    clock: Stage27_4Clock,
) -> MigrationContextRecord:
    """Read a Stage 27.4 migration context record via an injected
    source.

    Translates expected source failures
    (``Stage27MigrationSourceError``) into a ``SOURCE_ERROR``
    record.
    """
    if (
        ingest_output.token_mint is None
        or ingest_output.token_mint == ""
    ):
        return build_unsupported_migration_context(
            ingest_output,
            clock=clock,
            reason=MIGRATION_REASON_UNKNOWN_PAIR_OBSERVE_ONLY,
        )
    try:
        snapshot = source.read_migration_snapshot(
            ingest_output.token_mint,
        )
    except Stage27MigrationSourceError:
        return MigrationContextRecord(
            token_mint=ingest_output.token_mint,
            pair_type=ingest_output.pair_pair_type,
            quote_asset=ingest_output.pair_quote_asset,
            migration_event_id=None,
            migration_timestamp_utc=None,
            migration_source=MIGRATION_SOURCE_UNKNOWN,
            migration_status=MIGRATION_STATUS_SOURCE_ERROR,
            migration_reason=MIGRATION_REASON_SOURCE_FAILED,
            age_since_migration_seconds=None,
            observed_at_utc=_iso_utc(clock.utc_now()),
            source_event_ref=None,
            raw_capture_ref=None,
            schema_version=STAGE27_4_MIGRATION_SCHEMA_VERSION,
        )
    return build_migration_context_record(
        snapshot,
        ingest_output,
        clock=clock,
    )

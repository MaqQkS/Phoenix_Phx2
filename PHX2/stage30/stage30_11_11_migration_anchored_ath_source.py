"""Stage 30.11.11 migration-anchored ATH context source.

The committed REAL ATH context source the prior controlled ceremonies improvised
out-of-repo -- brought IN-repo so a live post-migration ATH can NEVER again clip
the first post-migration peak. The Stage 30 ATH-correctness audit surfaced the
defect: the out-of-repo source built the committed Stage 29.2 ATH source with a
SLIDING ``now - floor(elapsed_h)h`` window, so for a ~24.9h-old mint the window
started ~52 min AFTER migration and missed the real peak (the true ATH was ~2x
the reported one, flipping the tier from Tier 3 to Tier 2).

This source fixes that by ANCHORING the OHLCV window at the confirmed migration
moment:

    given a candidate ``token_mint`` + the committed Stage 30.11.8-confirmed
    ``migration_event_time_utc`` (the Stage 30.11.10 ATH-resolver contract)
      -> validate the anchor (missing / unparseable / in-future / non-positive
         window all fail closed)
      -> ``time_from = migration_unix`` (EXACTLY the migration moment; NEVER
         ``migration_unix - buffer`` -- a pre-buffer would flip the committed
         Stage 27.4 ``window_starts_post_migration`` flag to ``False`` and risk
         a pre-migration candle high contaminating the ATH), ``time_to = now``
      -> select the FINEST OHLCV candle interval whose candle count over
         ``[migration, now]`` fits the provider item cap (a coarser candle still
         carries the intracandle ``h``, so stepping up never loses the ATH
         MAGNITUDE; only timestamp precision); if NO interval can cover the full
         window, fail closed with ``ATH_UNVERIFIED_WINDOW_TOO_LONG`` -- NEVER
         silently truncate the start, NEVER fall back to a sliding window, NEVER
         accept partial coverage as a verified ATH
      -> fetch the anchored Stage 29.2 ATH snapshot + the Stage 29.2 current
         price, feed BOTH into the committed Stage 27.4 ``read_ath_context``
         (which records ``POST_MIGRATION_ONLY`` + a ``FROM_POST_MIGRATION_ATH``
         drawdown ONLY when the snapshot proves a post-migration window)
      -> return the committed Stage 27.4 ``AthContextRecord`` reading ONLY when
         it is PRESENT + POST_MIGRATION_ONLY + ``FROM_POST_MIGRATION_ATH`` with a
         drawdown; otherwise return ``None`` (a clean fail-closed the committed
         Stage 30.11.10 resolver maps to UNRESOLVED -> the Stage 30.11.7 ATH
         dimension fails -> the dip gate never PASSes -> no send)

The ``read_ath_context(token_mint, *, migration_event_time_utc)`` method conforms
to the committed Stage 30.11.10 ATH-context-source contract verbatim, so this
source drops into ``build_ath_resolver(ath_context_source=...)`` with NO Stage
30.11.10 edit. It RECOMPUTES no drawdown (the committed Stage 27.4
``_compute_drawdown`` owns that) and LOOSENS no post-migration verification.

Why this slice is NOT a clean leaf (the deliberate, audited Stage 30.11.11 import
expansion): unlike the leaf Stage 30.11.10 resolver -- which takes the ATH source
INJECTED and keeps the real Stage 27.4 / Stage 29.2 wiring out-of-repo -- Stage
30.11.11 IS that committed real source, so it imports the committed Stage 27.4
reader + Stage 29.2 sources DIRECTLY (read-only; it modifies none of them). The
low-level provider transport + the private endpoint secret are still INJECTED, so
this module reads NO process environment, opens NO network connection of its own,
and is fully offline-testable with a fake transport.

Discipline:

  * Stdlib only (``dataclasses`` / ``datetime`` / ``typing``). ``datetime`` is
    used to PARSE the caller-supplied anchor + the injected ``now``; the clock is
    INJECTED (``now_utc``), so this module NEVER calls ``datetime.now`` /
    ``utcnow`` (deterministic).
  * Imports ONLY the committed Stage 27.4 reader / contracts / models / migration
    / ingest / pair-detection siblings + the committed Stage 29.2 anchored ATH
    fetch / price source / models / constants. NO Stage 28, NO Stage 21-26, NO
    other Stage 30 module (NO Stage 30.12 renderer / display, NO Stage 30.11.5
    runner / transport), NO PHX1.
  * No ``os`` import; no environment read; no network / socket / gRPC / HTTP
    import (the transport is injected).
  * No Discord / webhook / wallet / signing / trading surface; no real send; no
    filesystem write; no while loop / daemon / thread; no top-level I/O.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional, Tuple

from PHX2.stage27.price_ath_context_contracts import (
    Stage27AthSourceError,
)
from PHX2.stage27.price_ath_context_models import (
    ATH_SINCE_MIGRATION_STATUS_POST_MIGRATION_ONLY,
    ATH_STATUS_PRESENT,
    ATH_STATUS_SOURCE_ERROR,
    ATH_STATUS_UNAVAILABLE,
    DRAWDOWN_BASIS_FROM_POST_MIGRATION_ATH,
)
from PHX2.stage27.price_ath_context_reader import (
    AthSourceSnapshot,
    read_ath_context as _read_ath_context_record,
    read_price_context as _read_price_context_record,
)
from PHX2.stage27.migration_context_models import (
    MIGRATION_REASON_OK,
    MIGRATION_SOURCE_ON_CHAIN_MIGRATION_EVENT,
    MIGRATION_STATUS_PRESENT,
    MigrationContextRecord,
    STAGE27_4_MIGRATION_SCHEMA_VERSION,
)
from PHX2.stage27.provider_ingest_models import (
    COMPOSITION_REASON_OK,
    COMPOSITION_STATUS_COMPOSED,
    EVENT_KIND_SWAP,
    ProviderIngestOutputRecord,
    STAGE27_3_SCHEMA_VERSION,
)
from PHX2.stage27.pair_detection_constants import (
    BONDING_CURVE_VERSION_SOL_LEGACY,
    CALIBRATION_LANE_EXISTING_SOL_LANE,
    KNOWN_WRAPPED_SOL_MINT,
    LIVE_POLICY_LIVE_ALLOWED,
    PAIR_DETECTION_CONFIDENCE_HIGH,
    PAIR_DETECTION_REASON_CONFIRMED_AGREEMENT,
    PAIR_DETECTION_STATUS_CONFIRMED,
    PAIR_TYPE_PUMP_SOL,
    QUOTE_ASSET_SOL,
)
from PHX2.stage29.birdeye_constants import (
    BIRDEYE_OHLCV_TYPE_1D,
    BIRDEYE_OHLCV_TYPE_1H,
    BIRDEYE_OHLCV_TYPE_1M,
    BIRDEYE_OHLCV_TYPE_4H,
    BIRDEYE_OHLCV_TYPE_5M,
    BIRDEYE_OHLCV_TYPE_15M,
    BIRDEYE_REPORTING_UNIT_USD,
)
from PHX2.stage29.stage29_2_birdeye_ath_source import (
    fetch_birdeye_ath_snapshot_migration_anchored,
)
from PHX2.stage29.stage29_2_birdeye_models import (
    BIRDEYE_ATH_STATUS_SOURCE_ERROR,
)
from PHX2.stage29.stage29_2_birdeye_price_source import (
    Stage29_2BirdeyePriceSource,
)


# ---------------------------------------------------------------------------
# Minor version + schema identity
# ---------------------------------------------------------------------------


STAGE30_11_11_MINOR_VERSION: str = "30.11.11"
STAGE30_11_11_ANCHORED_ATH_SCHEMA_VERSION: str = (
    "stage30_11_11_v0_migration_anchored_ath"
)
STAGE30_11_11_SOURCE_STAGE: str = "30.11.11"


# ---------------------------------------------------------------------------
# Provider OHLCV item cap + the finest-first interval ladder
# ---------------------------------------------------------------------------
#
# Birdeye's /defi/ohlcv returns a bounded number of candles per call. The source
# selects the FINEST interval whose candle count over [migration, now] fits this
# cap. A coarser candle's intracandle ``h`` still carries the peak MAGNITUDE, so
# stepping up the interval never loses the ATH value (only timestamp precision);
# it is the ANCHORED START that matters for not clipping the peak. If even the
# coarsest ladder rung cannot cover the window, the source fails closed
# (ATH_UNVERIFIED_WINDOW_TOO_LONG) rather than truncate the start.


STAGE30_11_11_OHLCV_MAX_ITEMS: int = 1000


# (ohlcv_type, candle_seconds), finest first. Each token is a committed Stage
# 29.2 allowed OHLCV resolution.
STAGE30_11_11_INTERVAL_LADDER: Tuple[Tuple[str, int], ...] = (
    (BIRDEYE_OHLCV_TYPE_1M, 60),
    (BIRDEYE_OHLCV_TYPE_5M, 300),
    (BIRDEYE_OHLCV_TYPE_15M, 900),
    (BIRDEYE_OHLCV_TYPE_1H, 3600),
    (BIRDEYE_OHLCV_TYPE_4H, 14400),
    (BIRDEYE_OHLCV_TYPE_1D, 86400),
)


# ---------------------------------------------------------------------------
# Closed-set anchored-ATH decision + reason tokens
# ---------------------------------------------------------------------------


ANCHORED_ATH_DECISION_RESOLVED: str = "RESOLVED_ANCHORED_ATH"
ANCHORED_ATH_DECISION_UNRESOLVED: str = "UNRESOLVED_ANCHORED_ATH"

STAGE30_11_11_ANCHORED_ATH_DECISIONS: Tuple[str, ...] = (
    ANCHORED_ATH_DECISION_RESOLVED,
    ANCHORED_ATH_DECISION_UNRESOLVED,
)


# The single passing reason (mirrors the committed Stage 30.11.10 pass reason BY
# VALUE) + the closed-set fail-closed reasons.
ANCHORED_ATH_REASON_RESOLVED_POST_MIGRATION_ATH: str = (
    "RESOLVED_POST_MIGRATION_ATH"
)
ANCHORED_ATH_REASON_BLANK_CANDIDATE_MINT: str = "BLANK_CANDIDATE_MINT"
ANCHORED_ATH_REASON_MISSING_MIGRATION_ANCHOR: str = (
    "MISSING_MIGRATION_ANCHOR"
)
ANCHORED_ATH_REASON_UNPARSEABLE_MIGRATION_ANCHOR: str = (
    "UNPARSEABLE_MIGRATION_ANCHOR"
)
ANCHORED_ATH_REASON_MIGRATION_ANCHOR_IN_FUTURE: str = (
    "MIGRATION_ANCHOR_IN_FUTURE"
)
ANCHORED_ATH_REASON_NON_POSITIVE_WINDOW: str = "NON_POSITIVE_WINDOW"
ANCHORED_ATH_REASON_WINDOW_TOO_LONG: str = (
    "ATH_UNVERIFIED_WINDOW_TOO_LONG"
)
ANCHORED_ATH_REASON_ATH_SOURCE_EMPTY: str = "ATH_SOURCE_EMPTY"
ANCHORED_ATH_REASON_ATH_SOURCE_ERROR: str = "ATH_SOURCE_ERROR"
ANCHORED_ATH_REASON_ATH_NOT_PRESENT: str = "ATH_NOT_PRESENT"
ANCHORED_ATH_REASON_NOT_POST_MIGRATION_ONLY: str = (
    "NOT_POST_MIGRATION_ONLY"
)
ANCHORED_ATH_REASON_MISSING_DRAWDOWN: str = "MISSING_DRAWDOWN"


STAGE30_11_11_ANCHORED_ATH_PASS_DECISION: str = ANCHORED_ATH_DECISION_RESOLVED
STAGE30_11_11_ANCHORED_ATH_PASS_REASON: str = (
    ANCHORED_ATH_REASON_RESOLVED_POST_MIGRATION_ATH
)


STAGE30_11_11_ANCHORED_ATH_REASONS: Tuple[str, ...] = (
    ANCHORED_ATH_REASON_RESOLVED_POST_MIGRATION_ATH,
    ANCHORED_ATH_REASON_BLANK_CANDIDATE_MINT,
    ANCHORED_ATH_REASON_MISSING_MIGRATION_ANCHOR,
    ANCHORED_ATH_REASON_UNPARSEABLE_MIGRATION_ANCHOR,
    ANCHORED_ATH_REASON_MIGRATION_ANCHOR_IN_FUTURE,
    ANCHORED_ATH_REASON_NON_POSITIVE_WINDOW,
    ANCHORED_ATH_REASON_WINDOW_TOO_LONG,
    ANCHORED_ATH_REASON_ATH_SOURCE_EMPTY,
    ANCHORED_ATH_REASON_ATH_SOURCE_ERROR,
    ANCHORED_ATH_REASON_ATH_NOT_PRESENT,
    ANCHORED_ATH_REASON_NOT_POST_MIGRATION_ONLY,
    ANCHORED_ATH_REASON_MISSING_DRAWDOWN,
)


# ---------------------------------------------------------------------------
# Immutable anchored-ATH result
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Stage30_11_11AnchoredAthResult:
    """Immutable per-candidate migration-anchored ATH result.

    Carries the resolved flag + closed-set decision / reason, the echoed mint,
    the anchored window (``time_from_unix`` = migration moment, ``time_to_unix``
    = now, ``span_seconds``, the selected ``ohlcv_type``), the resolved ATH
    value + drawdown + Stage 27.4 status echoes, and the committed Stage 27.4
    ``AthContextRecord`` reading (only when RESOLVED; ``None`` otherwise). Carries
    only safe scalars + the committed reading; no secret, no raw payload, no host,
    no transport destination.
    """

    resolved: bool
    decision: str
    reason: str
    token_mint: str
    time_from_unix: Optional[int]
    time_to_unix: Optional[int]
    span_seconds: Optional[int]
    ohlcv_type: Optional[str]
    ath_value: Optional[str]
    drawdown_from_ath: Optional[str]
    ath_status: Optional[str]
    ath_since_migration_status: Optional[str]
    drawdown_basis: Optional[str]
    reading: Any
    created_at_utc: str


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def select_anchored_ohlcv_type(
    span_seconds: int,
    *,
    max_items: int = STAGE30_11_11_OHLCV_MAX_ITEMS,
) -> Optional[str]:
    """Return the FINEST OHLCV interval whose candle count over a
    ``span_seconds`` window fits ``max_items``, or ``None`` when no ladder rung
    can cover the window (the caller then fails closed with
    ``ATH_UNVERIFIED_WINDOW_TOO_LONG``).

    Pure / total; never raises. A non-positive / non-int span returns ``None``.
    Candle count is ``span_seconds // candle_seconds + 1`` (inclusive of the
    final candle). Finest first, so the returned interval maximizes timestamp
    precision while still covering the full window in one bounded call.
    """
    if isinstance(span_seconds, bool) or not isinstance(span_seconds, int):
        return None
    if span_seconds <= 0:
        return None
    for ohlcv_type, candle_seconds in STAGE30_11_11_INTERVAL_LADDER:
        items_needed = span_seconds // candle_seconds + 1
        if items_needed <= max_items:
            return ohlcv_type
    return None


def _is_nonblank_str(value: object) -> bool:
    return isinstance(value, str) and value.strip() != ""


def _parse_iso_utc_to_unix(value: str) -> Optional[int]:
    """Parse an ISO-8601 UTC timestamp to an int unix second, or ``None`` when
    unparseable. Accepts a trailing ``Z`` or an explicit offset; a naive
    timestamp is treated as UTC. Pure; never raises.
    """
    candidate = value.strip()
    if candidate.endswith("Z"):
        candidate = candidate[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(candidate)
    except (ValueError, TypeError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return int(parsed.astimezone(timezone.utc).timestamp())


class _FixedClock:
    """A Stage 27.4 clock that returns the INJECTED ``now`` (never a wall-clock
    read), so the price-context staleness check + observed-at stamps are
    deterministic and this module never calls ``datetime.now``.
    """

    def __init__(self, now_utc: datetime) -> None:
        self._now_utc = now_utc

    def utc_now(self) -> datetime:
        return self._now_utc


def _build_ingest(token_mint: str, observed_at_utc: str) -> ProviderIngestOutputRecord:
    """Build a minimal confirmed PUMP_SOL Stage 27.3 ingest record for the mint
    (the shape the committed Stage 27.4 reader consumes). Pure; no I/O.
    """
    return ProviderIngestOutputRecord(
        provider_id="stage30_11_11_anchored_ath",
        provider_event_id="pe",
        normalized_event_id="ne",
        event_kind=EVENT_KIND_SWAP,
        observed_at_utc=observed_at_utc,
        token_mint=token_mint,
        quote_mint=KNOWN_WRAPPED_SOL_MINT,
        pair_quote_asset=QUOTE_ASSET_SOL,
        pair_pair_type=PAIR_TYPE_PUMP_SOL,
        pair_bonding_curve_version=BONDING_CURVE_VERSION_SOL_LEGACY,
        pair_detection_status=PAIR_DETECTION_STATUS_CONFIRMED,
        pair_detection_confidence=PAIR_DETECTION_CONFIDENCE_HIGH,
        pair_detection_reason=PAIR_DETECTION_REASON_CONFIRMED_AGREEMENT,
        pair_live_policy=LIVE_POLICY_LIVE_ALLOWED,
        pair_calibration_lane=CALIBRATION_LANE_EXISTING_SOL_LANE,
        raw_capture_ref="r",
        source_summary="s",
        composition_status=COMPOSITION_STATUS_COMPOSED,
        composition_reason=COMPOSITION_REASON_OK,
        schema_version=STAGE27_3_SCHEMA_VERSION,
    )


def _build_present_migration_context(
    token_mint: str, anchor_utc: str, observed_at_utc: str
) -> MigrationContextRecord:
    """Build a PRESENT on-chain-event Stage 27.4 migration context record from
    the committed confirmed anchor (so the Stage 27.4 reader records a
    POST_MIGRATION_ONLY ATH against it). Pure; no I/O.
    """
    return MigrationContextRecord(
        token_mint=token_mint,
        pair_type="PUMP_SOL",
        quote_asset="SOL",
        migration_event_id=None,
        migration_timestamp_utc=anchor_utc,
        migration_source=MIGRATION_SOURCE_ON_CHAIN_MIGRATION_EVENT,
        migration_status=MIGRATION_STATUS_PRESENT,
        migration_reason=MIGRATION_REASON_OK,
        age_since_migration_seconds=None,
        observed_at_utc=observed_at_utc,
        source_event_ref=None,
        raw_capture_ref=None,
        schema_version=STAGE27_4_MIGRATION_SCHEMA_VERSION,
    )


# ---------------------------------------------------------------------------
# Anchored Stage 27.4 ATH context source (the injected ATH snapshot reader)
# ---------------------------------------------------------------------------


class _AnchoredAthContextSource:
    """A Stage 27.4 ``AthContextSource`` whose ``read_ath_snapshot`` fetches the
    Stage 29.2 ATH over the EXPLICIT anchored ``[time_from_unix, time_to_unix]``
    window (committed ``fetch_birdeye_ath_snapshot_migration_anchored``). Raises
    ``Stage27AthSourceError`` on a SOURCE_ERROR snapshot (mirroring the committed
    ``Stage29_2BirdeyeAthSource`` boundary), so the Stage 27.4 reader records a
    SOURCE_ERROR ATH rather than crash.
    """

    def __init__(
        self,
        *,
        transport: Any,
        endpoint_secret: Any,
        timeout_seconds: int,
        time_from_unix: int,
        time_to_unix: int,
        ohlcv_type: str,
        migration_timestamp_utc: str,
    ) -> None:
        self._transport = transport
        self._endpoint_secret = endpoint_secret
        self._timeout_seconds = timeout_seconds
        self._time_from_unix = time_from_unix
        self._time_to_unix = time_to_unix
        self._ohlcv_type = ohlcv_type
        self._migration_timestamp_utc = migration_timestamp_utc

    def read_ath_snapshot(
        self,
        token_mint: str,
        *,
        pair_quote_asset: str,
    ) -> AthSourceSnapshot:
        _ = pair_quote_asset
        snapshot = fetch_birdeye_ath_snapshot_migration_anchored(
            base_mint=token_mint,
            transport=self._transport,
            endpoint_secret=self._endpoint_secret,
            timeout_seconds=self._timeout_seconds,
            time_from_unix=self._time_from_unix,
            time_to_unix=self._time_to_unix,
            ohlcv_type=self._ohlcv_type,
            migration_timestamp_utc=self._migration_timestamp_utc,
        )
        if snapshot.birdeye_ath_status == BIRDEYE_ATH_STATUS_SOURCE_ERROR:
            raise Stage27AthSourceError(
                reason="SOURCE_FAILED",
                source_label=snapshot.source_label,
            )
        return AthSourceSnapshot(
            ath_value=snapshot.ath_value,
            ath_unit=snapshot.ath_unit,
            source_label=snapshot.source_label,
            ath_observed_at_utc=snapshot.ath_observed_at_utc,
            window_starts_post_migration=(
                snapshot.window_starts_post_migration
            ),
        )


# ---------------------------------------------------------------------------
# Public migration-anchored ATH context source
# ---------------------------------------------------------------------------


class Stage30_11_11MigrationAnchoredAthContextSource:
    """The committed migration-anchored ATH context source.

    Conforms to the committed Stage 30.11.10 ATH-context-source contract:
    ``read_ath_context(token_mint, *, migration_event_time_utc) -> reading |
    None``. The injected low-level provider ``transport`` + private
    ``endpoint_secret`` are forwarded to the committed Stage 29.2 sources (a fake
    transport in tests; the real one at the operator-authorized ceremony); the
    ``now_utc`` clock is INJECTED, so this source reads no wall clock and no
    environment. It composes the committed Stage 29.2 anchored ATH fetch + price
    source + the committed Stage 27.4 reader; it RECOMPUTES no drawdown and
    LOOSENS no post-migration verification.
    """

    def __init__(
        self,
        *,
        transport: Any,
        endpoint_secret: Any,
        timeout_seconds: int,
        now_utc: datetime,
        ohlcv_max_items: int = STAGE30_11_11_OHLCV_MAX_ITEMS,
        staleness_threshold_seconds: int = 300,
    ) -> None:
        self._transport = transport
        self._endpoint_secret = endpoint_secret
        self._timeout_seconds = timeout_seconds
        self._now_utc = now_utc
        self._ohlcv_max_items = ohlcv_max_items
        self._staleness_threshold_seconds = staleness_threshold_seconds

    def _now_unix_and_iso(self) -> "Tuple[int, str]":
        now_utc = self._now_utc
        if now_utc.tzinfo is None:
            now_utc = now_utc.replace(tzinfo=timezone.utc)
        now_unix = int(now_utc.timestamp())
        now_iso = now_utc.astimezone(timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        return now_unix, now_iso

    def _unresolved(
        self,
        *,
        reason: str,
        token_mint: str,
        created_at_utc: str,
        time_from_unix: Optional[int] = None,
        time_to_unix: Optional[int] = None,
        span_seconds: Optional[int] = None,
        ohlcv_type: Optional[str] = None,
        reading: Any = None,
        ath_value: Optional[str] = None,
        drawdown_from_ath: Optional[str] = None,
        ath_status: Optional[str] = None,
        ath_since_migration_status: Optional[str] = None,
        drawdown_basis: Optional[str] = None,
    ) -> Stage30_11_11AnchoredAthResult:
        return Stage30_11_11AnchoredAthResult(
            resolved=False,
            decision=ANCHORED_ATH_DECISION_UNRESOLVED,
            reason=reason,
            token_mint=token_mint,
            time_from_unix=time_from_unix,
            time_to_unix=time_to_unix,
            span_seconds=span_seconds,
            ohlcv_type=ohlcv_type,
            ath_value=ath_value,
            drawdown_from_ath=drawdown_from_ath,
            ath_status=ath_status,
            ath_since_migration_status=ath_since_migration_status,
            drawdown_basis=drawdown_basis,
            reading=reading,
            created_at_utc=created_at_utc,
        )

    def resolve_anchored_ath(
        self,
        token_mint: str,
        migration_event_time_utc: object,
    ) -> Stage30_11_11AnchoredAthResult:
        """Resolve ONE candidate's migration-anchored ATH, returning a
        ``Stage30_11_11AnchoredAthResult``. Never raises (a SOURCE_ERROR /
        malformed reading fails closed to an UNRESOLVED result).

        Precedence (top-down, first failing check wins): blank mint -> missing
        anchor -> unparseable anchor -> anchor in future -> non-positive window
        -> window too long (no interval covers it) -> ATH source error / empty
        -> ATH not PRESENT -> not POST_MIGRATION_ONLY (window status OR basis) ->
        missing drawdown -> RESOLVED.
        """
        now_unix, now_iso = self._now_unix_and_iso()

        if not _is_nonblank_str(token_mint):
            return self._unresolved(
                reason=ANCHORED_ATH_REASON_BLANK_CANDIDATE_MINT,
                token_mint="",
                created_at_utc=now_iso,
            )
        mint: str = token_mint

        if not _is_nonblank_str(migration_event_time_utc):
            return self._unresolved(
                reason=ANCHORED_ATH_REASON_MISSING_MIGRATION_ANCHOR,
                token_mint=mint,
                created_at_utc=now_iso,
            )
        anchor: str = migration_event_time_utc  # type: ignore[assignment]

        migration_unix = _parse_iso_utc_to_unix(anchor)
        if migration_unix is None:
            return self._unresolved(
                reason=ANCHORED_ATH_REASON_UNPARSEABLE_MIGRATION_ANCHOR,
                token_mint=mint,
                created_at_utc=now_iso,
            )

        if migration_unix > now_unix:
            return self._unresolved(
                reason=ANCHORED_ATH_REASON_MIGRATION_ANCHOR_IN_FUTURE,
                token_mint=mint,
                created_at_utc=now_iso,
                time_from_unix=migration_unix,
                time_to_unix=now_unix,
            )

        span_seconds = now_unix - migration_unix
        if span_seconds <= 0:
            return self._unresolved(
                reason=ANCHORED_ATH_REASON_NON_POSITIVE_WINDOW,
                token_mint=mint,
                created_at_utc=now_iso,
                time_from_unix=migration_unix,
                time_to_unix=now_unix,
                span_seconds=span_seconds,
            )

        ohlcv_type = select_anchored_ohlcv_type(
            span_seconds, max_items=self._ohlcv_max_items
        )
        if ohlcv_type is None:
            return self._unresolved(
                reason=ANCHORED_ATH_REASON_WINDOW_TOO_LONG,
                token_mint=mint,
                created_at_utc=now_iso,
                time_from_unix=migration_unix,
                time_to_unix=now_unix,
                span_seconds=span_seconds,
            )

        # ---- Compose the committed Stage 27.4 chain over the anchored window ----
        ingest = _build_ingest(mint, now_iso)
        migration_record = _build_present_migration_context(
            mint, anchor, now_iso
        )
        price_source = Stage29_2BirdeyePriceSource(
            transport=self._transport,
            endpoint_secret=self._endpoint_secret,
            timeout_seconds=self._timeout_seconds,
        )
        ath_source = _AnchoredAthContextSource(
            transport=self._transport,
            endpoint_secret=self._endpoint_secret,
            timeout_seconds=self._timeout_seconds,
            time_from_unix=migration_unix,
            time_to_unix=now_unix,
            ohlcv_type=ohlcv_type,
            migration_timestamp_utc=anchor,
        )
        price_ctx = _read_price_context_record(
            price_source,
            ingest,
            clock=_FixedClock(self._now_utc),
            staleness_threshold_seconds=self._staleness_threshold_seconds,
        )
        reading = _read_ath_context_record(
            ath_source,
            ingest,
            migration_record=migration_record,
            current_price_record=price_ctx,
        )

        common = {
            "token_mint": mint,
            "created_at_utc": now_iso,
            "time_from_unix": migration_unix,
            "time_to_unix": now_unix,
            "span_seconds": span_seconds,
            "ohlcv_type": ohlcv_type,
            "reading": reading,
            "ath_value": reading.ath_value,
            "drawdown_from_ath": reading.drawdown_from_ath,
            "ath_status": reading.ath_status,
            "ath_since_migration_status": reading.ath_since_migration_status,
            "drawdown_basis": reading.drawdown_basis,
        }

        # ---- Verify PRESENT + POST_MIGRATION_ONLY + drawdown (fail closed) ----
        if reading.ath_status != ATH_STATUS_PRESENT:
            if reading.ath_status == ATH_STATUS_SOURCE_ERROR:
                reason = ANCHORED_ATH_REASON_ATH_SOURCE_ERROR
            elif reading.ath_status == ATH_STATUS_UNAVAILABLE:
                reason = ANCHORED_ATH_REASON_ATH_SOURCE_EMPTY
            else:
                reason = ANCHORED_ATH_REASON_ATH_NOT_PRESENT
            return self._unresolved(reason=reason, **common)

        post_migration_ok = (
            reading.ath_since_migration_status
            == ATH_SINCE_MIGRATION_STATUS_POST_MIGRATION_ONLY
            and reading.drawdown_basis
            == DRAWDOWN_BASIS_FROM_POST_MIGRATION_ATH
        )
        if not post_migration_ok:
            return self._unresolved(
                reason=ANCHORED_ATH_REASON_NOT_POST_MIGRATION_ONLY, **common
            )

        if reading.drawdown_from_ath is None:
            return self._unresolved(
                reason=ANCHORED_ATH_REASON_MISSING_DRAWDOWN, **common
            )

        return Stage30_11_11AnchoredAthResult(
            resolved=True,
            decision=ANCHORED_ATH_DECISION_RESOLVED,
            reason=ANCHORED_ATH_REASON_RESOLVED_POST_MIGRATION_ATH,
            token_mint=mint,
            time_from_unix=migration_unix,
            time_to_unix=now_unix,
            span_seconds=span_seconds,
            ohlcv_type=ohlcv_type,
            ath_value=reading.ath_value,
            drawdown_from_ath=reading.drawdown_from_ath,
            ath_status=reading.ath_status,
            ath_since_migration_status=reading.ath_since_migration_status,
            drawdown_basis=reading.drawdown_basis,
            reading=reading,
            created_at_utc=now_iso,
        )

    def read_ath_context(
        self,
        token_mint: str,
        *,
        migration_event_time_utc: str,
    ) -> Any:
        """The committed Stage 30.11.10 ATH-context-source contract: return the
        committed Stage 27.4 ``AthContextRecord`` reading ONLY when the anchored
        ATH is RESOLVED (PRESENT + POST_MIGRATION_ONLY + drawdown); otherwise
        return ``None`` (a clean fail-closed the Stage 30.11.10 resolver maps to
        UNRESOLVED).
        """
        result = self.resolve_anchored_ath(token_mint, migration_event_time_utc)
        return result.reading if result.resolved else None


def build_migration_anchored_ath_context_source(
    *,
    transport: Any,
    endpoint_secret: Any,
    timeout_seconds: int,
    now_utc: datetime,
    ohlcv_max_items: int = STAGE30_11_11_OHLCV_MAX_ITEMS,
    staleness_threshold_seconds: int = 300,
) -> Stage30_11_11MigrationAnchoredAthContextSource:
    """Build a committed migration-anchored ATH context source over the injected
    provider transport + private endpoint secret + injected ``now_utc`` clock.

    The returned object's ``read_ath_context(token_mint,
    migration_event_time_utc=...)`` drops directly into the committed Stage
    30.11.10 ``build_ath_resolver(ath_context_source=...)`` seam. Pure apart from
    the injected transport's own behavior; reads no env, no wall clock, no
    network of its own; sends nothing.
    """
    return Stage30_11_11MigrationAnchoredAthContextSource(
        transport=transport,
        endpoint_secret=endpoint_secret,
        timeout_seconds=timeout_seconds,
        now_utc=now_utc,
        ohlcv_max_items=ohlcv_max_items,
        staleness_threshold_seconds=staleness_threshold_seconds,
    )


__all__ = (
    "STAGE30_11_11_MINOR_VERSION",
    "STAGE30_11_11_ANCHORED_ATH_SCHEMA_VERSION",
    "STAGE30_11_11_SOURCE_STAGE",
    "STAGE30_11_11_OHLCV_MAX_ITEMS",
    "STAGE30_11_11_INTERVAL_LADDER",
    "ANCHORED_ATH_DECISION_RESOLVED",
    "ANCHORED_ATH_DECISION_UNRESOLVED",
    "STAGE30_11_11_ANCHORED_ATH_DECISIONS",
    "STAGE30_11_11_ANCHORED_ATH_PASS_DECISION",
    "STAGE30_11_11_ANCHORED_ATH_PASS_REASON",
    "STAGE30_11_11_ANCHORED_ATH_REASONS",
    "ANCHORED_ATH_REASON_RESOLVED_POST_MIGRATION_ATH",
    "ANCHORED_ATH_REASON_BLANK_CANDIDATE_MINT",
    "ANCHORED_ATH_REASON_MISSING_MIGRATION_ANCHOR",
    "ANCHORED_ATH_REASON_UNPARSEABLE_MIGRATION_ANCHOR",
    "ANCHORED_ATH_REASON_MIGRATION_ANCHOR_IN_FUTURE",
    "ANCHORED_ATH_REASON_NON_POSITIVE_WINDOW",
    "ANCHORED_ATH_REASON_WINDOW_TOO_LONG",
    "ANCHORED_ATH_REASON_ATH_SOURCE_EMPTY",
    "ANCHORED_ATH_REASON_ATH_SOURCE_ERROR",
    "ANCHORED_ATH_REASON_ATH_NOT_PRESENT",
    "ANCHORED_ATH_REASON_NOT_POST_MIGRATION_ONLY",
    "ANCHORED_ATH_REASON_MISSING_DRAWDOWN",
    "Stage30_11_11AnchoredAthResult",
    "select_anchored_ohlcv_type",
    "Stage30_11_11MigrationAnchoredAthContextSource",
    "build_migration_anchored_ath_context_source",
)

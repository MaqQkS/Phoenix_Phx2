"""OutcomeTrackingService.

Stage 9. Observe-only forward-return measurement layer for WOULD_ALERT
decisions. Single-table writer (outcome_windows). Reads alert_decisions and
price_observations; writes outcome_windows. Performs no rendering, dispatch,
filtering, scoring, classification, or network I/O. SKIP / BLOCK / ERROR
decisions are ignored entirely — no outcome_windows row is ever produced for
them.

The service is polling-based: ``track_for_decision`` and ``track_pending`` are
the entry points. There is no internal scheduler or background loop in v0.

Idempotency: for each (alert_decision_id, window_seconds) pair, a row is
written at most once. Re-runs surface as ALREADY_RECORDED with no DB write.
The unique index on (alert_decision_id, window_seconds) is the safety net
against races; an IntegrityError on insert is treated as ALREADY_RECORDED.
"""

import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from math import isfinite
from typing import Callable, List, Optional, Sequence, Tuple

from PHX2.config.settings import OutcomeWindowSettings
from PHX2.db.repositories import (
    AlertDecisionRepository,
    OutcomeWindowRepository,
    PriceObservationRepository,
)
from PHX2.models import (
    AlertDecision,
    DecisionType,
    OutcomeWindow,
    OutcomeWindowStatus,
    PriceObservation,
)
from PHX2.models.outcome_tracking_result import (
    BatchTrackingResult,
    DecisionTrackingResult,
    WindowProcessingResult,
)


logger = logging.getLogger(__name__)


CurrentTimeProvider = Callable[[], datetime]


def _default_current_time() -> datetime:
    return datetime.now(timezone.utc)


def _is_finite_positive(value: Optional[float]) -> bool:
    if value is None:
        return False
    try:
        n = float(value)
    except (TypeError, ValueError):
        return False
    return isfinite(n) and n > 0


@dataclass(frozen=True)
class OutcomeMetrics:
    """Result of pure metric computation for one window.

    The service maps this onto an OutcomeWindow row. Module-level so that
    metric tests can import and exercise it without spinning up a service or
    DB.
    """

    status: OutcomeWindowStatus
    observations_count: Optional[int]
    first_observation_time: Optional[datetime]
    last_observation_time: Optional[datetime]
    max_price: Optional[float]
    max_mcap: Optional[float]
    max_observation_time: Optional[datetime]
    min_price: Optional[float]
    min_mcap: Optional[float]
    min_observation_time: Optional[datetime]
    max_return_multiple: Optional[float]
    max_return_pct: Optional[float]
    min_return_multiple: Optional[float]
    min_return_pct: Optional[float]
    max_drawdown_from_peak_pct: Optional[float]
    time_to_max_return_seconds: Optional[float]
    hit_2x: Optional[bool]
    hit_3x: Optional[bool]
    hit_5x: Optional[bool]


_INVALID_ALERT_PRICE_METRICS = OutcomeMetrics(
    status=OutcomeWindowStatus.INVALID_ALERT_PRICE,
    observations_count=None,
    first_observation_time=None,
    last_observation_time=None,
    max_price=None,
    max_mcap=None,
    max_observation_time=None,
    min_price=None,
    min_mcap=None,
    min_observation_time=None,
    max_return_multiple=None,
    max_return_pct=None,
    min_return_multiple=None,
    min_return_pct=None,
    max_drawdown_from_peak_pct=None,
    time_to_max_return_seconds=None,
    hit_2x=None,
    hit_3x=None,
    hit_5x=None,
)


_NO_PRICE_DATA_METRICS = OutcomeMetrics(
    status=OutcomeWindowStatus.NO_PRICE_DATA,
    observations_count=0,
    first_observation_time=None,
    last_observation_time=None,
    max_price=None,
    max_mcap=None,
    max_observation_time=None,
    min_price=None,
    min_mcap=None,
    min_observation_time=None,
    max_return_multiple=None,
    max_return_pct=None,
    min_return_multiple=None,
    min_return_pct=None,
    max_drawdown_from_peak_pct=None,
    time_to_max_return_seconds=None,
    hit_2x=None,
    hit_3x=None,
    hit_5x=None,
)


def compute_outcome_metrics(
    observations: Sequence[PriceObservation],
    alert_price: Optional[float],
    window_start_time: datetime,
) -> OutcomeMetrics:
    """Pure metric computation for one outcome window.

    Returns the INVALID_ALERT_PRICE shape when ``alert_price`` is missing,
    zero, negative, or non-finite. Returns the NO_PRICE_DATA shape when
    ``observations`` is empty or contains no observations with a usable
    finite-positive price. Otherwise returns the COMPLETE shape with metrics
    computed over price-having observations.

    Tie-breaking: when multiple observations share the same maximum
    (or minimum) price, the first occurrence by ``observed_at`` wins. The
    caller must pass ``observations`` in chronological ASC order, which is
    what ``PriceObservationRepository.get_observations_in_range`` returns.
    """

    if not _is_finite_positive(alert_price):
        return _INVALID_ALERT_PRICE_METRICS

    if not observations:
        return _NO_PRICE_DATA_METRICS

    priced = [o for o in observations if _is_finite_positive(o.price)]
    if not priced:
        return _NO_PRICE_DATA_METRICS

    alert_price_f = float(alert_price)

    max_obs = priced[0]
    min_obs = priced[0]
    for obs in priced[1:]:
        if obs.price > max_obs.price:
            max_obs = obs
        if obs.price < min_obs.price:
            min_obs = obs

    max_price = float(max_obs.price)
    min_price = float(min_obs.price)
    max_return_multiple = max_price / alert_price_f
    max_return_pct = (max_return_multiple - 1.0) * 100.0
    min_return_multiple = min_price / alert_price_f
    min_return_pct = (min_return_multiple - 1.0) * 100.0

    peak_index = priced.index(max_obs)
    later_obs = [o for o in priced[peak_index + 1 :] if _is_finite_positive(o.price)]
    if not later_obs:
        max_drawdown_from_peak_pct = 0.0
    else:
        lowest_after_peak = min(float(o.price) for o in later_obs)
        max_drawdown_from_peak_pct = (
            (lowest_after_peak / max_price) - 1.0
        ) * 100.0

    time_to_max_return_seconds = (
        max_obs.observed_at - window_start_time
    ).total_seconds()

    return OutcomeMetrics(
        status=OutcomeWindowStatus.COMPLETE,
        observations_count=len(priced),
        first_observation_time=priced[0].observed_at,
        last_observation_time=priced[-1].observed_at,
        max_price=max_price,
        max_mcap=(
            float(max_obs.mcap) if _is_finite_positive(max_obs.mcap) else None
        ),
        max_observation_time=max_obs.observed_at,
        min_price=min_price,
        min_mcap=(
            float(min_obs.mcap) if _is_finite_positive(min_obs.mcap) else None
        ),
        min_observation_time=min_obs.observed_at,
        max_return_multiple=max_return_multiple,
        max_return_pct=max_return_pct,
        min_return_multiple=min_return_multiple,
        min_return_pct=min_return_pct,
        max_drawdown_from_peak_pct=max_drawdown_from_peak_pct,
        time_to_max_return_seconds=time_to_max_return_seconds,
        hit_2x=max_return_multiple >= 2.0,
        hit_3x=max_return_multiple >= 3.0,
        hit_5x=max_return_multiple >= 5.0,
    )


class OutcomeTrackingService:
    """The sole writer of PHX2 outcome_windows rows.

    The service is observe-only: it never mutates alert_decisions,
    price_observations, or any table other than outcome_windows. The
    AlertDecision row's ``current_price`` and ``current_mcap`` columns
    (populated by AlertEligibilityEngine) are read directly as the canonical
    snapshot — there is no re-resolution at tracking time and no mcap
    fallback for the denominator.
    """

    def __init__(
        self,
        alert_decision_repository: AlertDecisionRepository,
        price_observation_repository: PriceObservationRepository,
        outcome_window_repository: OutcomeWindowRepository,
        clock: CurrentTimeProvider = _default_current_time,
        window_seconds: Optional[Sequence[int]] = None,
    ) -> None:
        self.alert_decisions = alert_decision_repository
        self.price_observations = price_observation_repository
        self.outcome_windows = outcome_window_repository
        self._clock = clock
        if window_seconds is None:
            window_seconds = OutcomeWindowSettings().outcome_windows_seconds
        self.window_seconds: Tuple[int, ...] = tuple(window_seconds)

    def track_for_decision(
        self,
        alert_decision_id: int,
        as_of_time: Optional[datetime] = None,
    ) -> DecisionTrackingResult:
        as_of = as_of_time if as_of_time is not None else self._clock()
        decision = self.alert_decisions.get(alert_decision_id)
        if decision is None:
            return DecisionTrackingResult(
                alert_decision_id=alert_decision_id,
                window_results=(),
                error="alert_decision_not_found",
            )
        if (
            decision.decision_type != DecisionType.WOULD_ALERT
            or not decision.would_alert
        ):
            return DecisionTrackingResult(
                alert_decision_id=alert_decision_id,
                window_results=(),
                error="not a would_alert decision",
            )
        if decision.evaluated_at is None:
            return DecisionTrackingResult(
                alert_decision_id=alert_decision_id,
                window_results=(),
                error="alert_decision_missing_evaluated_at",
            )

        results: List[WindowProcessingResult] = []
        for window_seconds in self.window_seconds:
            try:
                result = self._process_window(
                    decision=decision,
                    alert_decision_id=alert_decision_id,
                    window_seconds=window_seconds,
                    as_of_time=as_of,
                )
            except Exception as exc:
                logger.error(
                    "outcome_window_processing_failed",
                    extra={
                        "alert_decision_id": alert_decision_id,
                        "window_seconds": window_seconds,
                    },
                    exc_info=exc,
                )
                # Per-window exceptions must not abort other windows. Map to
                # ERROR (service-only, never persisted) rather than the prior
                # WINDOW_NOT_ELAPSED — a real DB failure (lock timeout,
                # schema mismatch, logic bug) is not the same as a window
                # that has not yet matured, and counting it as such would
                # hide failures during batch backfill. The unique-constraint
                # race path is handled inside ``_insert_or_already_recorded``
                # via ``sqlite3.IntegrityError`` and resolves to
                # ALREADY_RECORDED before this handler ever sees it.
                result = WindowProcessingResult(
                    window_seconds=window_seconds,
                    status=OutcomeWindowStatus.ERROR,
                    reason=f"{type(exc).__name__}: {exc}",
                )
            results.append(result)
        return DecisionTrackingResult(
            alert_decision_id=alert_decision_id,
            window_results=tuple(results),
            error=None,
        )

    def track_pending(
        self,
        as_of_time: Optional[datetime] = None,
        limit: Optional[int] = None,
        offset: int = 0,
    ) -> BatchTrackingResult:
        as_of = as_of_time if as_of_time is not None else self._clock()
        # ``list_pending_would_alert_with_ids`` already filters to
        # decision_type='would_alert' AND would_alert=TRUE, so SKIP/BLOCK/
        # ERROR decisions never reach the service. Oldest-first is the
        # deterministic backfill order.
        page_limit = int(limit) if limit is not None else 1_000_000
        candidates = self.alert_decisions.list_pending_would_alert_with_ids(
            limit=page_limit, offset=offset
        )

        decision_results: List[DecisionTrackingResult] = []
        decisions_processed = 0
        rows_inserted = 0
        rows_skipped_already = 0
        rows_skipped_pending = 0
        rows_errored = 0

        for decision_id, _decision in candidates:
            decisions_processed += 1
            result = self.track_for_decision(decision_id, as_of_time=as_of)
            decision_results.append(result)
            for window_result in result.window_results:
                if window_result.status == OutcomeWindowStatus.ALREADY_RECORDED:
                    rows_skipped_already += 1
                elif window_result.status == OutcomeWindowStatus.WINDOW_NOT_ELAPSED:
                    rows_skipped_pending += 1
                elif window_result.status == OutcomeWindowStatus.ERROR:
                    rows_errored += 1
                elif window_result.outcome_window_id is not None:
                    rows_inserted += 1

        return BatchTrackingResult(
            decision_results=tuple(decision_results),
            decisions_processed=decisions_processed,
            decisions_skipped_non_would_alert=0,
            rows_inserted=rows_inserted,
            rows_skipped_already_recorded=rows_skipped_already,
            rows_skipped_window_not_elapsed=rows_skipped_pending,
            rows_errored=rows_errored,
        )

    def _process_window(
        self,
        *,
        decision: AlertDecision,
        alert_decision_id: int,
        window_seconds: int,
        as_of_time: datetime,
    ) -> WindowProcessingResult:
        existing = self.outcome_windows.get_by_decision_and_window(
            alert_decision_id, window_seconds
        )
        if existing is not None:
            return WindowProcessingResult(
                window_seconds=window_seconds,
                status=OutcomeWindowStatus.ALREADY_RECORDED,
                outcome_window_id=existing.id,
                reason=f"already_recorded:{existing.data_status.value}",
            )

        window_start = decision.evaluated_at
        window_end = window_start + timedelta(seconds=window_seconds)
        if as_of_time < window_end:
            return WindowProcessingResult(
                window_seconds=window_seconds,
                status=OutcomeWindowStatus.WINDOW_NOT_ELAPSED,
            )

        alert_price = decision.current_price
        alert_mcap = decision.current_mcap

        if not _is_finite_positive(alert_price):
            row = OutcomeWindow(
                alert_decision_id=alert_decision_id,
                token_address=decision.token_address,
                window_seconds=window_seconds,
                window_start_time=window_start,
                window_end_time=window_end,
                alert_price=alert_price,
                alert_mcap=alert_mcap,
                data_status=OutcomeWindowStatus.INVALID_ALERT_PRICE,
            )
            return self._insert_or_already_recorded(
                row, alert_decision_id, window_seconds
            )

        observations = self.price_observations.get_observations_in_range(
            decision.token_address, window_start, window_end
        )
        metrics = compute_outcome_metrics(
            observations, alert_price, window_start
        )
        row = OutcomeWindow(
            alert_decision_id=alert_decision_id,
            token_address=decision.token_address,
            window_seconds=window_seconds,
            window_start_time=window_start,
            window_end_time=window_end,
            alert_price=float(alert_price),
            alert_mcap=(
                float(alert_mcap) if _is_finite_positive(alert_mcap) else None
            ),
            max_price=metrics.max_price,
            max_mcap=metrics.max_mcap,
            max_observation_time=metrics.max_observation_time,
            min_price=metrics.min_price,
            min_mcap=metrics.min_mcap,
            min_observation_time=metrics.min_observation_time,
            max_return_multiple=metrics.max_return_multiple,
            max_return_pct=metrics.max_return_pct,
            min_return_multiple=metrics.min_return_multiple,
            min_return_pct=metrics.min_return_pct,
            max_drawdown_from_peak_pct=metrics.max_drawdown_from_peak_pct,
            time_to_max_return_seconds=metrics.time_to_max_return_seconds,
            hit_2x=metrics.hit_2x,
            hit_3x=metrics.hit_3x,
            hit_5x=metrics.hit_5x,
            observations_count=metrics.observations_count,
            first_observation_time=metrics.first_observation_time,
            last_observation_time=metrics.last_observation_time,
            data_status=metrics.status,
        )
        return self._insert_or_already_recorded(
            row, alert_decision_id, window_seconds
        )

    def _insert_or_already_recorded(
        self,
        row: OutcomeWindow,
        alert_decision_id: int,
        window_seconds: int,
    ) -> WindowProcessingResult:
        try:
            outcome_id = self.outcome_windows.insert(row)
        except sqlite3.IntegrityError:
            existing = self.outcome_windows.get_by_decision_and_window(
                alert_decision_id, window_seconds
            )
            if existing is None:
                # IntegrityError that is not the unique-row race; re-raise so
                # the caller can capture it.
                raise
            return WindowProcessingResult(
                window_seconds=window_seconds,
                status=OutcomeWindowStatus.ALREADY_RECORDED,
                outcome_window_id=existing.id,
                reason="unique_constraint_race",
            )
        return WindowProcessingResult(
            window_seconds=window_seconds,
            status=row.data_status,
            outcome_window_id=outcome_id,
        )

"""PHX2 fee/event window materialization service.

This service reads already-stored raw_pumpswap_events and writes only
fee_windows. It does not ingest raw events, derive field/score features, seed
ATH, evaluate alerts, mutate token state, open live streams, or send messages.
"""

from datetime import datetime, timedelta, timezone
from statistics import median
from typing import Callable, Iterable, List, Optional, Sequence

from PHX2.config.settings import FeatureWindowSettings
from PHX2.db.repositories import FeeWindowRepository, RawPumpSwapEventRepository
from PHX2.models import DataStatus, FeeWindow, RawPumpSwapEvent


CurrentTimeProvider = Callable[[], datetime]
DEFAULT_FEE_WINDOWS_SECONDS = tuple(FeatureWindowSettings().fee_windows_seconds)


def _default_current_time() -> datetime:
    return datetime.now(timezone.utc)


def _dedupe_reasons(reasons: Iterable[str]) -> List[str]:
    deduped: List[str] = []
    for reason in reasons:
        if reason not in deduped:
            deduped.append(reason)
    return deduped


def _event_time(event: RawPumpSwapEvent) -> datetime:
    return event.block_time or event.observed_at


def _sum_optional(values: Iterable[Optional[float]]) -> float:
    return sum(value if value is not None else 0.0 for value in values)


def _safe_share(numerator: float, denominator: float) -> Optional[float]:
    if denominator == 0:
        return None
    return numerator / denominator


class FeatureWindowService:
    """Owns PHX2 materialized PumpSwap fee/event windows."""

    def __init__(
        self,
        raw_pumpswap_events: RawPumpSwapEventRepository,
        fee_windows: FeeWindowRepository,
        current_time_provider: Optional[CurrentTimeProvider] = None,
    ) -> None:
        self.raw_pumpswap_events = raw_pumpswap_events
        self.fee_windows = fee_windows
        self.current_time_provider = current_time_provider or _default_current_time

    def materialize_fee_window(
        self,
        token_address: str,
        as_of_time: Optional[datetime],
        window_seconds: int,
    ) -> FeeWindow:
        """Aggregate raw PumpSwap events into one persisted fee window."""

        normalized_token = token_address.strip() if token_address else ""
        if not normalized_token:
            raise ValueError("token_address is required")
        if window_seconds <= 0:
            raise ValueError("window_seconds must be positive")

        effective_as_of_time = as_of_time or self.current_time_provider()
        start_time = effective_as_of_time - timedelta(seconds=window_seconds)
        events = self.raw_pumpswap_events.list_window(
            normalized_token,
            start_time,
            effective_as_of_time,
        )
        window = self._window_from_events(
            normalized_token,
            effective_as_of_time,
            window_seconds,
            events,
        )
        self.fee_windows.insert(window)
        return window

    def materialize_standard_windows(
        self,
        token_address: str,
        as_of_time: Optional[datetime],
        windows: Optional[Sequence[int]] = None,
    ) -> List[FeeWindow]:
        """Materialize the configured standard fee windows for one token."""

        window_seconds_values = list(windows or DEFAULT_FEE_WINDOWS_SECONDS)
        return [
            self.materialize_fee_window(token_address, as_of_time, window_seconds)
            for window_seconds in window_seconds_values
        ]

    def _window_from_events(
        self,
        token_address: str,
        as_of_time: datetime,
        window_seconds: int,
        events: List[RawPumpSwapEvent],
    ) -> FeeWindow:
        event_count = len(events)
        if event_count == 0:
            return FeeWindow(
                token_address=token_address,
                as_of_time=as_of_time,
                window_seconds=window_seconds,
                event_count=0,
                buy_count=0,
                sell_count=0,
                total_fee_sol=0.0,
                lp_fee_sol=0.0,
                protocol_fee_sol=0.0,
                creator_fee_sol=0.0,
                events_per_min=0.0,
                fees_per_min_sol=0.0,
                source_row_count=0,
                data_status=DataStatus.NO_EVENTS,
                missing_reasons=["no_raw_events_in_window"],
            )

        missing_reasons: List[str] = []
        event_types = [(event.event_type or "").strip().lower() for event in events]
        buy_count = sum(1 for event_type in event_types if event_type == "buy")
        sell_count = sum(1 for event_type in event_types if event_type == "sell")

        total_fee_sol = _sum_optional(event.total_fee_sol for event in events)
        lp_fee_sol = _sum_optional(event.lp_fee_sol for event in events)
        protocol_fee_sol = _sum_optional(event.protocol_fee_sol for event in events)
        creator_fee_sol = _sum_optional(event.creator_fee_sol for event in events)
        total_fee_per_event = [
            event.total_fee_sol if event.total_fee_sol is not None else 0.0
            for event in events
        ]

        has_missing_fee_fields = any(
            self._has_missing_fee_fields(event) for event in events
        )
        if has_missing_fee_fields:
            missing_reasons.append("fee_fields_missing")

        creator_fee_share = _safe_share(creator_fee_sol, total_fee_sol)
        lp_fee_share = _safe_share(lp_fee_sol, total_fee_sol)
        protocol_fee_share = _safe_share(protocol_fee_sol, total_fee_sol)
        if total_fee_sol == 0:
            missing_reasons.append("fee_share_denominator_zero")

        buy_sell_count_ratio = None
        if sell_count == 0:
            missing_reasons.append("buy_sell_ratio_denominator_zero")
        else:
            buy_sell_count_ratio = buy_count / sell_count

        buy_fee_sol = sum(
            fee
            for fee, event_type in zip(total_fee_per_event, event_types)
            if event_type == "buy"
        )
        sell_fee_sol = sum(
            fee
            for fee, event_type in zip(total_fee_per_event, event_types)
            if event_type == "sell"
        )
        buy_sell_fee_ratio = None
        if sell_fee_sol == 0:
            missing_reasons.append("buy_sell_fee_denominator_zero")
        else:
            buy_sell_fee_ratio = buy_fee_sol / sell_fee_sol

        minutes = window_seconds / 60
        event_times = [_event_time(event) for event in events]
        raw_ids = [event.id for event in events if event.id is not None]

        window = FeeWindow(
            token_address=token_address,
            as_of_time=as_of_time,
            window_seconds=window_seconds,
            pool_address=next(
                (event.pool_address for event in events if event.pool_address),
                None,
            ),
            first_event_time=min(event_times),
            last_event_time=max(event_times),
            event_count=event_count,
            buy_count=buy_count,
            sell_count=sell_count,
            total_fee_sol=total_fee_sol,
            lp_fee_sol=lp_fee_sol,
            protocol_fee_sol=protocol_fee_sol,
            creator_fee_sol=creator_fee_sol,
            creator_fee_share=creator_fee_share,
            lp_fee_share=lp_fee_share,
            protocol_fee_share=protocol_fee_share,
            avg_fee_per_event_sol=total_fee_sol / event_count,
            median_fee_per_event_sol=median(total_fee_per_event),
            max_fee_event_sol=max(total_fee_per_event),
            events_per_min=event_count / minutes,
            fees_per_min_sol=total_fee_sol / minutes,
            buy_sell_count_ratio=buy_sell_count_ratio,
            buy_sell_fee_ratio=buy_sell_fee_ratio,
            source_min_id=min(raw_ids) if raw_ids else None,
            source_max_id=max(raw_ids) if raw_ids else None,
            source_row_count=event_count,
            data_status=DataStatus.PARTIAL if has_missing_fee_fields else DataStatus.OK,
            missing_reasons=_dedupe_reasons(missing_reasons),
        )
        return window

    def _has_missing_fee_fields(self, event: RawPumpSwapEvent) -> bool:
        return any(
            value is None
            for value in (
                event.total_fee_sol,
                event.lp_fee_sol,
                event.protocol_fee_sol,
                event.creator_fee_sol,
            )
        )

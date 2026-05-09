"""PHX2 observe-only price curve capture service.

This service reads existing PHX2 token, price, and optional ATH state and
writes only price_curve_points. It does not implement curve templates,
deviation scoring, alert logic, ATH mutation, fee windows, live streams, or
message dispatch.
"""

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from typing import Callable, Iterable, List, Optional, Sequence

from PHX2.db.repositories import (
    AlertDecisionRepository,
    ATHRepository,
    PriceCurvePointRepository,
    PriceObservationRepository,
    TokenSequenceRepository,
)
from PHX2.models import ATHState, DataStatus, PriceCurvePoint, PriceObservation, TokenState


CurrentTimeProvider = Callable[[], datetime]
DEFAULT_MIGRATION_CURVE_BUCKETS_SECONDS = (
    0,
    15,
    30,
    60,
    120,
    180,
    300,
    600,
    900,
    1800,
    3600,
    7200,
    14400,
    86400,
)


def _default_current_time() -> datetime:
    return datetime.now(timezone.utc)


def _dedupe_reasons(reasons: Iterable[str]) -> List[str]:
    deduped: List[str] = []
    for reason in reasons:
        if reason not in deduped:
            deduped.append(reason)
    return deduped


def _safe_ratio(numerator: Optional[float], denominator: Optional[float]) -> Optional[float]:
    if numerator is None or denominator is None or denominator == 0:
        return None
    return numerator / denominator


def _return_from_normalized(
    normalized_price: Optional[float],
    normalized_mcap: Optional[float],
) -> Optional[float]:
    normalized_value = normalized_price if normalized_price is not None else normalized_mcap
    if normalized_value is None:
        return None
    return normalized_value - 1


class CurveCaptureService:
    """Owns PHX2 observe-only price curve point capture."""

    def __init__(
        self,
        token_sequence: TokenSequenceRepository,
        price_observations: PriceObservationRepository,
        price_curve_points: PriceCurvePointRepository,
        ath: Optional[ATHRepository] = None,
        alert_decisions: Optional[AlertDecisionRepository] = None,
        current_time_provider: Optional[CurrentTimeProvider] = None,
    ) -> None:
        self.token_sequence = token_sequence
        self.price_observations = price_observations
        self.price_curve_points = price_curve_points
        self.ath = ath
        self.alert_decisions = alert_decisions
        self.current_time_provider = current_time_provider or _default_current_time

    def capture_migration_curve_point(
        self,
        token_address: str,
        bucket_seconds: int,
        as_of_time: Optional[datetime] = None,
    ) -> PriceCurvePoint:
        """Capture one migration-anchored price curve point."""

        normalized_token = token_address.strip() if token_address else ""
        if not normalized_token:
            raise ValueError("token_address is required")
        if bucket_seconds < 0:
            raise ValueError("bucket_seconds must be non-negative")

        effective_as_of_time = as_of_time or self.current_time_provider()
        token_state = self.token_sequence.get(normalized_token)
        ath_state = self.ath.get_state(normalized_token) if self.ath else None
        point = self._migration_point(
            normalized_token,
            bucket_seconds,
            effective_as_of_time,
            token_state,
            ath_state,
        )
        point_id = self.price_curve_points.insert(point)
        return replace(point, id=point_id)

    def capture_standard_migration_curve_points(
        self,
        token_address: str,
        as_of_time: Optional[datetime] = None,
        buckets: Optional[Sequence[int]] = None,
    ) -> List[PriceCurvePoint]:
        """Capture the standard migration curve bucket set for one token."""

        bucket_values = list(buckets or DEFAULT_MIGRATION_CURVE_BUCKETS_SECONDS)
        effective_as_of_time = as_of_time or self.current_time_provider()
        return [
            self.capture_migration_curve_point(
                token_address,
                bucket_seconds,
                as_of_time=effective_as_of_time,
            )
            for bucket_seconds in bucket_values
        ]

    def _migration_point(
        self,
        token_address: str,
        bucket_seconds: int,
        as_of_time: datetime,
        token_state: Optional[TokenState],
        ath_state: Optional[ATHState],
    ) -> PriceCurvePoint:
        missing_reasons: List[str] = []

        migration_time = token_state.migration_time if token_state else None
        anchor_time = migration_time or as_of_time
        bucket_start_time = anchor_time
        bucket_end_time = anchor_time + timedelta(seconds=bucket_seconds)
        anchor_ref_id = token_state.last_migration_event_id if token_state else None
        anchor_key = (
            f"migration:{anchor_ref_id}"
            if anchor_ref_id is not None
            else f"migration:{token_address}"
        )

        if token_state is None:
            missing_reasons.append("token_state_missing")
        elif migration_time is None:
            missing_reasons.append("migration_time_missing")

        observation = self.price_observations.get_latest_at_or_before(
            token_address,
            bucket_end_time,
        )
        if observation is None:
            missing_reasons.append("price_observation_missing")

        if token_state is not None:
            if token_state.migration_price is None:
                missing_reasons.append("migration_price_missing")
            if token_state.migration_mcap is None:
                missing_reasons.append("migration_mcap_missing")

        if observation is not None:
            if observation.price is None:
                missing_reasons.append("price_missing")
            if observation.mcap is None:
                missing_reasons.append("mcap_missing")

        normalized_price = _safe_ratio(
            observation.price if observation else None,
            token_state.migration_price if token_state else None,
        )
        normalized_mcap = _safe_ratio(
            observation.mcap if observation else None,
            token_state.migration_mcap if token_state else None,
        )
        return_from_anchor = _return_from_normalized(normalized_price, normalized_mcap)
        drawdown_from_ath = self._drawdown_from_ath(observation, ath_state)

        return PriceCurvePoint(
            token_address=token_address,
            anchor_type="migration",
            anchor_key=anchor_key,
            anchor_time=anchor_time,
            anchor_ref_id=anchor_ref_id,
            bucket_seconds=bucket_seconds,
            bucket_start_time=bucket_start_time,
            bucket_end_time=bucket_end_time,
            observed_at=observation.observed_at if observation else None,
            price_observation_id=observation.id if observation else None,
            price=observation.price if observation else None,
            mcap=observation.mcap if observation else None,
            liquidity_usd=observation.liquidity_usd if observation else None,
            normalized_price=normalized_price,
            normalized_mcap=normalized_mcap,
            return_from_anchor=return_from_anchor,
            return_from_migration=return_from_anchor,
            drawdown_from_ath=drawdown_from_ath,
            age_since_migration_s=(
                (bucket_end_time - migration_time).total_seconds()
                if migration_time is not None
                else None
            ),
            time_since_ath_s=(
                (bucket_end_time - ath_state.ath_time).total_seconds()
                if ath_state is not None and ath_state.ath_time is not None
                else None
            ),
            data_status=self._data_status(token_state, observation, missing_reasons),
            missing_reasons=_dedupe_reasons(missing_reasons),
        )

    def _data_status(
        self,
        token_state: Optional[TokenState],
        observation: Optional[PriceObservation],
        missing_reasons: List[str],
    ) -> DataStatus:
        if token_state is None or observation is None:
            return DataStatus.MISSING
        if "migration_time_missing" in missing_reasons:
            return DataStatus.MISSING
        if missing_reasons:
            return DataStatus.PARTIAL
        if token_state.data_status == DataStatus.OK and observation.data_status == DataStatus.OK:
            return DataStatus.OK
        if observation.data_status == DataStatus.MISSING:
            return DataStatus.MISSING
        return DataStatus.PARTIAL

    def _drawdown_from_ath(
        self,
        observation: Optional[PriceObservation],
        ath_state: Optional[ATHState],
    ) -> Optional[float]:
        if observation is None or ath_state is None:
            return None
        if observation.price is not None and ath_state.ath_price not in (None, 0):
            return (ath_state.ath_price - observation.price) / ath_state.ath_price
        if observation.mcap is not None and ath_state.ath_mcap not in (None, 0):
            return (ath_state.ath_mcap - observation.mcap) / ath_state.ath_mcap
        return None

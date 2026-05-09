"""PHX2 ATH state service.

ATHService evaluates already-stored PHX2 price observations and writes only
ath_state plus ath_events. It does not call external price APIs, seed from
legacy Phoenix1 data, evaluate alerts, score tokens, or dispatch messages.
"""

from dataclasses import replace
from datetime import datetime, timezone
from math import isfinite
from typing import Callable, Iterable, List, Optional

from PHX2.db.repositories import ATHRepository, PriceObservationRepository
from PHX2.models import (
    ATHConfidence,
    ATHEvent,
    ATHEventType,
    ATHState,
    ATHStatus,
    DataStatus,
    PriceObservation,
)


CurrentTimeProvider = Callable[[], datetime]


def _default_current_time() -> datetime:
    return datetime.now(timezone.utc)


def _dedupe_reasons(reasons: Iterable[str]) -> List[str]:
    deduped: List[str] = []
    for reason in reasons:
        if reason not in deduped:
            deduped.append(reason)
    return deduped


def _is_positive_finite(value: Optional[float]) -> bool:
    if value is None:
        return False
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return False
    return isfinite(numeric) and numeric > 0


def _is_invalid_numeric(value: Optional[float]) -> bool:
    if value is None:
        return False
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return True
    return not isfinite(numeric) or numeric <= 0


class ATHService:
    """Owns PHX2 ATH truth and auditable ATH mutation events."""

    def __init__(
        self,
        ath: ATHRepository,
        price_observations: PriceObservationRepository,
        current_time_provider: Optional[CurrentTimeProvider] = None,
    ) -> None:
        self.ath = ath
        self.price_observations = price_observations
        self.current_time_provider = current_time_provider or _default_current_time

    def evaluate_price_observation(self, observation: PriceObservation) -> ATHState:
        """Evaluate one already-normalized price observation as an ATH candidate."""

        token_address = observation.token_address.strip() if observation.token_address else ""
        if not token_address:
            raise ValueError("PriceObservation.token_address is required")

        existing = self.ath.get_state(token_address)
        candidate_source = self._candidate_source(observation)
        candidate_time = observation.source_timestamp or observation.observed_at
        event_time = candidate_time or self.current_time_provider()
        missing_reasons = self._candidate_missing_reasons(observation, candidate_source)
        invalid_reasons = self._candidate_invalid_reasons(observation)

        if invalid_reasons:
            return self._record_rejected_candidate(
                token_address=token_address,
                observation=observation,
                existing=existing,
                event_time=event_time,
                candidate_source=candidate_source,
                mutation_type=ATHEventType.ATH_REJECTED_INVALID,
                reason="candidate_numeric_invalid",
                data_limited=True,
                event_data_status=DataStatus.ERROR,
                missing_reasons=_dedupe_reasons([*missing_reasons, *invalid_reasons]),
            )

        if not self._has_complete_numeric_candidate(observation):
            return self._record_rejected_candidate(
                token_address=token_address,
                observation=observation,
                existing=existing,
                event_time=event_time,
                candidate_source=candidate_source,
                mutation_type=ATHEventType.ATH_DATA_LIMITED,
                reason="candidate_price_or_mcap_missing",
                data_limited=True,
                event_data_status=DataStatus.DATA_LIMITED,
                missing_reasons=missing_reasons,
            )

        candidate_data_limited = bool(missing_reasons)
        if existing is None or not self._state_has_ath(existing):
            return self._record_ath_raise(
                token_address=token_address,
                observation=observation,
                existing=existing,
                event_time=event_time,
                ath_time=candidate_time,
                candidate_source=candidate_source,
                reason="first_valid_candidate",
                data_limited=candidate_data_limited,
                missing_reasons=missing_reasons,
            )

        if self._candidate_above_existing(observation, existing):
            return self._record_ath_raise(
                token_address=token_address,
                observation=observation,
                existing=existing,
                event_time=event_time,
                ath_time=candidate_time,
                candidate_source=candidate_source,
                reason="higher_candidate",
                data_limited=candidate_data_limited,
                missing_reasons=missing_reasons,
            )

        mutation_type = (
            ATHEventType.ATH_REJECTED_LOWER
            if self._candidate_below_existing(observation, existing)
            else ATHEventType.ATH_NO_CHANGE
        )
        reason = (
            "lower_candidate"
            if mutation_type == ATHEventType.ATH_REJECTED_LOWER
            else "candidate_matches_existing_ath"
        )
        return self._record_rejected_candidate(
            token_address=token_address,
            observation=observation,
            existing=existing,
            event_time=event_time,
            candidate_source=candidate_source,
            mutation_type=mutation_type,
            reason=reason,
            data_limited=candidate_data_limited,
            event_data_status=self._event_data_status(candidate_data_limited),
            missing_reasons=missing_reasons,
        )

    def rebuild_from_price_observations(
        self,
        token_address: str,
        limit: Optional[int] = None,
    ) -> ATHState:
        """Replay stored price observations in deterministic chronological order."""

        normalized_token = token_address.strip() if token_address else ""
        if not normalized_token:
            raise ValueError("token_address is required")

        observations = self.price_observations.list_by_token_chronological(
            normalized_token,
            limit=limit,
        )
        final_state = self.ath.get_state(normalized_token)
        for observation in observations:
            final_state = self.evaluate_price_observation(observation)
        return final_state or ATHState(token_address=normalized_token)

    def _record_ath_raise(
        self,
        *,
        token_address: str,
        observation: PriceObservation,
        existing: Optional[ATHState],
        event_time: datetime,
        ath_time: Optional[datetime],
        candidate_source: str,
        reason: str,
        data_limited: bool,
        missing_reasons: List[str],
    ) -> ATHState:
        status_after = self._raised_status(existing, candidate_source, data_limited)
        confidence_after = self._raised_confidence(existing, data_limited)
        state = ATHState(
            token_address=token_address,
            ath_price=observation.price,
            ath_mcap=observation.mcap,
            ath_time=ath_time,
            ath_status=status_after,
            ath_confidence=confidence_after,
            ath_source=candidate_source,
            data_status=self._state_data_status(data_limited),
            missing_reasons=missing_reasons,
        )
        event = self._candidate_event(
            token_address=token_address,
            observation=observation,
            existing=existing,
            event_time=event_time,
            candidate_source=candidate_source,
            new_ath_price=observation.price,
            new_ath_mcap=observation.mcap,
            status_after=status_after,
            confidence_after=confidence_after,
            mutation_type=ATHEventType.ATH_RAISED,
            reason=reason,
            accepted=True,
            data_limited=data_limited,
            data_status=self._event_data_status(data_limited),
            missing_reasons=missing_reasons,
        )
        return self._persist_event_and_state(token_address, event, state)

    def _record_rejected_candidate(
        self,
        *,
        token_address: str,
        observation: PriceObservation,
        existing: Optional[ATHState],
        event_time: datetime,
        candidate_source: str,
        mutation_type: ATHEventType,
        reason: str,
        data_limited: bool,
        event_data_status: DataStatus,
        missing_reasons: List[str],
    ) -> ATHState:
        state = existing or ATHState(
            token_address=token_address,
            data_status=event_data_status,
            missing_reasons=missing_reasons,
        )
        event = self._candidate_event(
            token_address=token_address,
            observation=observation,
            existing=existing,
            event_time=event_time,
            candidate_source=candidate_source,
            new_ath_price=state.ath_price,
            new_ath_mcap=state.ath_mcap,
            status_after=state.ath_status,
            confidence_after=state.ath_confidence,
            mutation_type=mutation_type,
            reason=reason,
            accepted=False,
            data_limited=data_limited,
            data_status=event_data_status,
            missing_reasons=missing_reasons,
        )
        return self._persist_event_and_state(token_address, event, state)

    def _candidate_event(
        self,
        *,
        token_address: str,
        observation: PriceObservation,
        existing: Optional[ATHState],
        event_time: datetime,
        candidate_source: str,
        new_ath_price: Optional[float],
        new_ath_mcap: Optional[float],
        status_after: ATHStatus,
        confidence_after: ATHConfidence,
        mutation_type: ATHEventType,
        reason: str,
        accepted: bool,
        data_limited: bool,
        data_status: DataStatus,
        missing_reasons: List[str],
    ) -> ATHEvent:
        return ATHEvent(
            token_address=token_address,
            event_time=event_time,
            price_observation_id=observation.id,
            candidate_price=observation.price,
            candidate_mcap=observation.mcap,
            candidate_source=candidate_source,
            prior_ath_price=existing.ath_price if existing else None,
            prior_ath_mcap=existing.ath_mcap if existing else None,
            new_ath_price=new_ath_price,
            new_ath_mcap=new_ath_mcap,
            status_before=existing.ath_status if existing else ATHStatus.UNKNOWN,
            status_after=status_after,
            confidence_before=(
                existing.ath_confidence if existing else ATHConfidence.UNKNOWN
            ),
            confidence_after=confidence_after,
            mutation_type=mutation_type,
            reason=reason,
            accepted=accepted,
            data_limited=data_limited,
            input_snapshot=observation.to_dict(),
            data_status=data_status,
            missing_reasons=missing_reasons,
        )

    def _persist_event_and_state(
        self,
        token_address: str,
        event: ATHEvent,
        state: ATHState,
    ) -> ATHState:
        with self.ath.connection.transaction():
            event_id = self.ath.insert_event(event)
            self.ath.upsert_state(replace(state, last_event_id=event_id))
        return self.ath.get_state(token_address) or replace(state, last_event_id=event_id)

    def _candidate_source(self, observation: PriceObservation) -> str:
        source = observation.source.strip() if observation.source else ""
        return source or "unknown"

    def _candidate_missing_reasons(
        self,
        observation: PriceObservation,
        candidate_source: str,
    ) -> List[str]:
        reasons = list(observation.missing_reasons)
        if observation.price is None:
            reasons.append("price_missing")
        if observation.mcap is None:
            reasons.append("mcap_missing")
        if observation.observed_at is None and observation.source_timestamp is None:
            reasons.append("ath_time_missing")
        if candidate_source == "unknown":
            reasons.append("source_missing")
        if observation.data_status != DataStatus.OK:
            reasons.append(f"observation_data_status_{observation.data_status.value}")
        return _dedupe_reasons(reasons)

    def _candidate_invalid_reasons(self, observation: PriceObservation) -> List[str]:
        reasons: List[str] = []
        if _is_invalid_numeric(observation.price):
            reasons.append("price_invalid")
        if _is_invalid_numeric(observation.mcap):
            reasons.append("mcap_invalid")
        return reasons

    def _has_complete_numeric_candidate(self, observation: PriceObservation) -> bool:
        return _is_positive_finite(observation.price) and _is_positive_finite(
            observation.mcap
        )

    def _state_has_ath(self, state: ATHState) -> bool:
        return _is_positive_finite(state.ath_price) or _is_positive_finite(state.ath_mcap)

    def _candidate_above_existing(
        self,
        observation: PriceObservation,
        existing: ATHState,
    ) -> bool:
        if not _is_positive_finite(existing.ath_price):
            return True
        if not _is_positive_finite(existing.ath_mcap):
            return True
        return bool(
            observation.price is not None
            and observation.mcap is not None
            and (
                observation.price > existing.ath_price
                or observation.mcap > existing.ath_mcap
            )
        )

    def _candidate_below_existing(
        self,
        observation: PriceObservation,
        existing: ATHState,
    ) -> bool:
        return bool(
            observation.price is not None
            and observation.mcap is not None
            and existing.ath_price is not None
            and existing.ath_mcap is not None
            and observation.price < existing.ath_price
            and observation.mcap < existing.ath_mcap
        )

    def _raised_status(
        self,
        existing: Optional[ATHState],
        candidate_source: str,
        data_limited: bool,
    ) -> ATHStatus:
        if data_limited:
            return ATHStatus.PROVISIONAL
        if existing is None or existing.ath_status == ATHStatus.UNKNOWN:
            return ATHStatus.SEEDED
        if existing.ath_status == ATHStatus.CONFIRMED:
            return ATHStatus.CONFIRMED
        if existing.ath_source == candidate_source:
            return ATHStatus.CONFIRMED
        return ATHStatus.SEEDED

    def _raised_confidence(
        self,
        existing: Optional[ATHState],
        data_limited: bool,
    ) -> ATHConfidence:
        if data_limited:
            return ATHConfidence.LOW
        if existing is not None and existing.ath_confidence == ATHConfidence.HIGH:
            return ATHConfidence.HIGH
        return ATHConfidence.MEDIUM

    def _state_data_status(self, data_limited: bool) -> DataStatus:
        return DataStatus.DATA_LIMITED if data_limited else DataStatus.OK

    def _event_data_status(self, data_limited: bool) -> DataStatus:
        return DataStatus.DATA_LIMITED if data_limited else DataStatus.OK

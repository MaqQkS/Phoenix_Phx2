"""PHX2 price observation intake service.

This service accepts already-normalized PriceObservation models and persists
only PHX2 price/token state. It does not call external APIs, poll live prices,
seed ATH, evaluate alerts, write raw PumpSwap events, or send messages.
"""

from dataclasses import replace
from datetime import datetime, timezone
from typing import Callable, List, Optional

from PHX2.db.repositories import PriceObservationRepository, TokenSequenceRepository
from PHX2.models import DataStatus, PriceObservation, TokenState


CurrentTimeProvider = Callable[[], datetime]


def _default_current_time() -> datetime:
    return datetime.now(timezone.utc)


def _dedupe_reasons(reasons: List[str]) -> List[str]:
    deduped: List[str] = []
    for reason in reasons:
        if reason not in deduped:
            deduped.append(reason)
    return deduped


class PriceService:
    """Owns PHX2 normalized price observation intake."""

    def __init__(
        self,
        price_observations: PriceObservationRepository,
        token_sequence: TokenSequenceRepository,
        current_time_provider: Optional[CurrentTimeProvider] = None,
    ) -> None:
        self.price_observations = price_observations
        self.token_sequence = token_sequence
        self.current_time_provider = current_time_provider or _default_current_time

    def ingest_price_observation(self, observation: PriceObservation) -> TokenState:
        """Persist a price observation and update token current price state."""

        token_address = observation.token_address.strip() if observation.token_address else ""
        if not token_address:
            raise ValueError("PriceObservation.token_address is required")

        existing = self.token_sequence.get(token_address)
        normalized_observation = self._normalized_observation(observation, token_address)
        with self.price_observations.connection.transaction():
            price_observation_id = self.price_observations.insert(normalized_observation)
            token_state = self._token_state_from_observation(
                normalized_observation,
                existing,
                price_observation_id,
            )
            self.token_sequence.upsert(token_state)
        return token_state

    def _normalized_observation(
        self,
        observation: PriceObservation,
        token_address: str,
    ) -> PriceObservation:
        missing_reasons = list(observation.missing_reasons)
        observed_at = observation.observed_at
        if observed_at is None:
            observed_at = self.current_time_provider()
            missing_reasons.append("observed_at_missing")

        source = observation.source.strip() if observation.source else ""
        if not source:
            source = "unknown"
            missing_reasons.append("source_missing")

        if observation.price is None:
            missing_reasons.append("price_missing")
        if observation.mcap is None:
            missing_reasons.append("mcap_missing")

        return replace(
            observation,
            token_address=token_address,
            observed_at=observed_at,
            source=source,
            data_status=self._observation_data_status(
                observation,
                _dedupe_reasons(missing_reasons),
            ),
            missing_reasons=_dedupe_reasons(missing_reasons),
        )

    def _observation_data_status(
        self,
        observation: PriceObservation,
        missing_reasons: List[str],
    ) -> DataStatus:
        if not missing_reasons and observation.data_status == DataStatus.OK:
            return DataStatus.OK
        if observation.price is None and observation.mcap is None:
            return DataStatus.MISSING
        return DataStatus.PARTIAL

    def _token_state_from_observation(
        self,
        observation: PriceObservation,
        existing: Optional[TokenState],
        price_observation_id: int,
    ) -> TokenState:
        missing_reasons = list(existing.missing_reasons) if existing else []
        if existing is None:
            missing_reasons.append("token_state_missing_before_price")
        missing_reasons.extend(observation.missing_reasons)
        missing_reasons = _dedupe_reasons(missing_reasons)

        current_price = (
            observation.price
            if observation.price is not None
            else existing.current_price if existing else None
        )
        current_mcap = (
            observation.mcap
            if observation.mcap is not None
            else existing.current_mcap if existing else None
        )

        return TokenState(
            token_address=observation.token_address,
            symbol=existing.symbol if existing else None,
            pool_address=existing.pool_address if existing else None,
            migration_time=existing.migration_time if existing else None,
            migration_source=existing.migration_source if existing else None,
            migration_price=existing.migration_price if existing else None,
            migration_mcap=existing.migration_mcap if existing else None,
            current_price=current_price,
            current_mcap=current_mcap,
            last_price_update=observation.observed_at,
            sequence_phase=existing.sequence_phase if existing else "price_observed",
            current_status=existing.current_status if existing else "tracking",
            last_alerted_tier=existing.last_alerted_tier if existing else None,
            last_migration_event_id=existing.last_migration_event_id if existing else None,
            last_price_observation_id=price_observation_id,
            data_status=self._token_data_status(existing, observation, missing_reasons),
            missing_reasons=missing_reasons,
        )

    def _token_data_status(
        self,
        existing: Optional[TokenState],
        observation: PriceObservation,
        missing_reasons: List[str],
    ) -> DataStatus:
        if not missing_reasons and observation.data_status == DataStatus.OK:
            return existing.data_status if existing else DataStatus.OK
        if existing is None and observation.price is None and observation.mcap is None:
            return DataStatus.MISSING
        if observation.price is None and observation.mcap is None:
            return DataStatus.MISSING
        return DataStatus.PARTIAL

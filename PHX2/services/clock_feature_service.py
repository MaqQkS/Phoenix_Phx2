"""PHX2 observe-only clock feature snapshot service.

This service reads existing PHX2 token, ATH, and fee-window timing state and
writes only clock_features. It does not mutate token state, write ATH/alerts,
derive scores, open live streams, or send messages.
"""

from dataclasses import replace
from datetime import datetime, timezone
from typing import Callable, Iterable, List, Optional

from PHX2.config.settings import FeatureWindowSettings
from PHX2.db.repositories import (
    AlertDecisionRepository,
    ATHRepository,
    ClockFeatureRepository,
    FeeWindowRepository,
    TokenSequenceRepository,
)
from PHX2.models import ATHState, ClockFeatures, DataStatus, FeeWindow, TokenState


CurrentTimeProvider = Callable[[], datetime]
STANDARD_FEE_WINDOWS_SECONDS = tuple(FeatureWindowSettings().fee_windows_seconds)
DEFAULT_CLOCK_FEATURE_VERSION = "clock_v0_observe_only"


def _default_current_time() -> datetime:
    return datetime.now(timezone.utc)


def _dedupe_reasons(reasons: Iterable[str]) -> List[str]:
    deduped: List[str] = []
    for reason in reasons:
        if reason not in deduped:
            deduped.append(reason)
    return deduped


def _seconds_between(start: Optional[datetime], end: Optional[datetime]) -> Optional[float]:
    if start is None or end is None:
        return None
    return (end - start).total_seconds()


class ClockFeatureService:
    """Owns PHX2 observe-only sequence timing snapshots."""

    def __init__(
        self,
        token_sequence: TokenSequenceRepository,
        clock_features: ClockFeatureRepository,
        ath: Optional[ATHRepository] = None,
        fee_windows: Optional[FeeWindowRepository] = None,
        alert_decisions: Optional[AlertDecisionRepository] = None,
        current_time_provider: Optional[CurrentTimeProvider] = None,
    ) -> None:
        self.token_sequence = token_sequence
        self.clock_features = clock_features
        self.ath = ath
        self.fee_windows = fee_windows
        self.alert_decisions = alert_decisions
        self.current_time_provider = current_time_provider or _default_current_time

    def build_clock_features(
        self,
        token_address: str,
        as_of_time: Optional[datetime],
        feature_version: str = DEFAULT_CLOCK_FEATURE_VERSION,
    ) -> ClockFeatures:
        """Build and persist one observe-only clock feature snapshot."""

        normalized_token = token_address.strip() if token_address else ""
        if not normalized_token:
            raise ValueError("token_address is required")

        effective_as_of_time = as_of_time or self.current_time_provider()
        token_state = self.token_sequence.get(normalized_token)
        ath_state = self.ath.get_state(normalized_token) if self.ath else None
        fee_window = self._fee_window_for_timing(normalized_token, effective_as_of_time)

        features = self._features_from_state(
            normalized_token,
            effective_as_of_time,
            feature_version,
            token_state,
            ath_state,
            fee_window,
        )
        feature_id = self.clock_features.insert(features)
        return replace(features, id=feature_id)

    def _features_from_state(
        self,
        token_address: str,
        as_of_time: datetime,
        feature_version: str,
        token_state: Optional[TokenState],
        ath_state: Optional[ATHState],
        fee_window: Optional[FeeWindow],
    ) -> ClockFeatures:
        missing_reasons: List[str] = []

        if token_state is None:
            missing_reasons.append("token_state_missing")
            if fee_window is None:
                missing_reasons.append("fee_window_timing_missing")
            return ClockFeatures(
                token_address=token_address,
                as_of_time=as_of_time,
                sequence_phase="unknown",
                phase_reason="token_state_missing",
                feature_version=feature_version,
                data_status=DataStatus.MISSING,
                missing_reasons=_dedupe_reasons(missing_reasons),
            )

        migration_time = token_state.migration_time
        if migration_time is None:
            missing_reasons.append("migration_time_missing")

        ath_time = ath_state.ath_time if ath_state else None
        if ath_state is None:
            missing_reasons.append("ath_state_missing")
        elif ath_time is None:
            missing_reasons.append("ath_time_missing")

        last_fee_event_time = fee_window.last_event_time if fee_window else None
        if last_fee_event_time is None:
            missing_reasons.append("fee_window_timing_missing")

        sequence_phase, phase_reason = self._sequence_phase(
            token_state,
            migration_time,
            ath_time,
            last_fee_event_time,
            as_of_time,
        )

        return ClockFeatures(
            token_address=token_address,
            as_of_time=as_of_time,
            migration_time=migration_time,
            age_since_migration_s=_seconds_between(migration_time, as_of_time),
            ath_time=ath_time,
            time_to_ath_s=_seconds_between(migration_time, ath_time),
            time_since_ath_s=_seconds_between(ath_time, as_of_time),
            last_fee_event_time=last_fee_event_time,
            time_since_last_fee_event_s=_seconds_between(
                last_fee_event_time,
                as_of_time,
            ),
            sequence_phase=sequence_phase,
            phase_reason=phase_reason,
            feature_version=feature_version,
            data_status=self._data_status(token_state, missing_reasons),
            missing_reasons=_dedupe_reasons(missing_reasons),
        )

    def _sequence_phase(
        self,
        token_state: TokenState,
        migration_time: Optional[datetime],
        ath_time: Optional[datetime],
        last_fee_event_time: Optional[datetime],
        as_of_time: datetime,
    ) -> tuple[str, str]:
        if migration_time is None:
            return "pre_migration", "migration_time_missing"
        if ath_time is None:
            if self._is_stale(last_fee_event_time, as_of_time):
                return "stale_data", "fee_window_timing_stale_or_missing"
            return "awaiting_ath", "ath_missing"
        if ath_time > as_of_time:
            return "ath_known", "ath_time_after_snapshot"
        if self._is_stale(last_fee_event_time, as_of_time):
            return "stale_data", "fee_window_timing_stale_or_missing"
        return "post_ath", "ath_time_present"

    def _is_stale(
        self,
        last_fee_event_time: Optional[datetime],
        as_of_time: datetime,
    ) -> bool:
        if last_fee_event_time is None:
            return False
        return (as_of_time - last_fee_event_time).total_seconds() > 3600

    def _data_status(
        self,
        token_state: TokenState,
        missing_reasons: List[str],
    ) -> DataStatus:
        if "migration_time_missing" in missing_reasons:
            return DataStatus.PARTIAL
        if not missing_reasons and token_state.data_status == DataStatus.OK:
            return DataStatus.OK
        if missing_reasons:
            return DataStatus.PARTIAL
        return token_state.data_status

    def _fee_window_for_timing(
        self,
        token_address: str,
        as_of_time: datetime,
    ) -> Optional[FeeWindow]:
        if self.fee_windows is None:
            return None

        exact_300s = self.fee_windows.get(token_address, as_of_time, 300)
        if exact_300s is not None and exact_300s.last_event_time is not None:
            return exact_300s

        all_windows = [
            window
            for window in self.fee_windows.list_by_token(token_address, limit=100)
            if window.window_seconds in STANDARD_FEE_WINDOWS_SECONDS
            and window.last_event_time is not None
        ]
        preferred_300s = [
            window for window in all_windows if window.window_seconds == 300
        ]
        if preferred_300s:
            return max(preferred_300s, key=self._fee_window_sort_key)
        if all_windows:
            return max(all_windows, key=self._fee_window_sort_key)
        return None

    def _fee_window_sort_key(self, window: FeeWindow) -> tuple[datetime, int]:
        sort_time = window.as_of_time or window.last_event_time
        if sort_time is None:
            sort_time = datetime.min.replace(tzinfo=timezone.utc)
        return sort_time, window.id or 0

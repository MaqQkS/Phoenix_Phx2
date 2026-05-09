"""PHX2 observe-only field feature snapshot service.

This service reads already-materialized fee_windows and writes only
field_features. It does not write fee windows, score/clock features, alerts,
ATH state, token state, open live streams, or send messages.
"""

from dataclasses import replace
from datetime import datetime, timezone
from typing import Callable, Dict, Iterable, List, Optional

from PHX2.config.settings import FeatureWindowSettings
from PHX2.db.repositories import (
    FeeWindowRepository,
    FieldFeatureRepository,
    PriceObservationRepository,
    TokenSequenceRepository,
)
from PHX2.models import DataStatus, FeeWindow, FieldFeatures


CurrentTimeProvider = Callable[[], datetime]
STANDARD_FEE_WINDOWS_SECONDS = tuple(FeatureWindowSettings().fee_windows_seconds)
DEFAULT_FIELD_FEATURE_VERSION = "field_v0_observe_only"


def _default_current_time() -> datetime:
    return datetime.now(timezone.utc)


def _dedupe_reasons(reasons: Iterable[str]) -> List[str]:
    deduped: List[str] = []
    for reason in reasons:
        if reason not in deduped:
            deduped.append(reason)
    return deduped


class FieldFeatureService:
    """Owns PHX2 environment and participation snapshots."""

    def __init__(
        self,
        fee_windows: FeeWindowRepository,
        field_features: FieldFeatureRepository,
        token_sequence: Optional[TokenSequenceRepository] = None,
        price_observations: Optional[PriceObservationRepository] = None,
        current_time_provider: Optional[CurrentTimeProvider] = None,
    ) -> None:
        self.fee_windows = fee_windows
        self.field_features = field_features
        self.token_sequence = token_sequence
        self.price_observations = price_observations
        self.current_time_provider = current_time_provider or _default_current_time

    def build_field_features(
        self,
        token_address: str,
        as_of_time: Optional[datetime],
        feature_version: str = DEFAULT_FIELD_FEATURE_VERSION,
    ) -> FieldFeatures:
        """Build and persist one observe-only field feature snapshot."""

        normalized_token = token_address.strip() if token_address else ""
        if not normalized_token:
            raise ValueError("token_address is required")
        effective_as_of_time = as_of_time or self.current_time_provider()

        windows = {
            window_seconds: self.fee_windows.get(
                normalized_token,
                effective_as_of_time,
                window_seconds,
            )
            for window_seconds in STANDARD_FEE_WINDOWS_SECONDS
        }
        source_300s = windows[300]
        missing_reasons = self._missing_reasons_for_windows(windows)

        features = FieldFeatures(
            token_address=normalized_token,
            as_of_time=effective_as_of_time,
            fee_window_60s_id=self._window_id(windows[60]),
            fee_window_300s_id=self._window_id(windows[300]),
            fee_window_900s_id=self._window_id(windows[900]),
            fee_window_1800s_id=self._window_id(windows[1800]),
            fee_window_3600s_id=self._window_id(windows[3600]),
            liquidity_usd=None,
            lp_floor_label=None,
            lp_fragility_score=None,
            fee_gate_label=None,
            fee_gate_score=None,
            ante_label_5m=None,
            ante_label_20sw=None,
            ghost_label=None,
            holder_label=None,
            event_pace_5m=source_300s.events_per_min if source_300s else None,
            fee_pace_5m_sol=source_300s.fees_per_min_sol if source_300s else None,
            creator_fee_share_5m=(
                source_300s.creator_fee_share if source_300s else None
            ),
            lp_fee_share_5m=source_300s.lp_fee_share if source_300s else None,
            protocol_fee_share_5m=(
                source_300s.protocol_fee_share if source_300s else None
            ),
            buy_sell_ratio_5m=(
                source_300s.buy_sell_count_ratio if source_300s else None
            ),
            raw_snapshot=self._raw_snapshot(windows),
            feature_version=feature_version,
            data_status=self._data_status_for_300s_window(source_300s),
            missing_reasons=_dedupe_reasons(missing_reasons),
        )
        feature_id = self.field_features.insert(features)
        return replace(features, id=feature_id)

    def _missing_reasons_for_windows(
        self,
        windows: Dict[int, Optional[FeeWindow]],
    ) -> List[str]:
        reasons: List[str] = []
        for window_seconds, window in windows.items():
            if window is None:
                reasons.append(f"fee_window_{window_seconds}s_missing")
                continue
            if window_seconds == 300:
                if window.data_status == DataStatus.PARTIAL:
                    reasons.append("fee_window_300s_partial")
                elif window.data_status == DataStatus.NO_EVENTS:
                    reasons.append("fee_window_300s_no_events")
        return reasons

    def _data_status_for_300s_window(
        self,
        window: Optional[FeeWindow],
    ) -> DataStatus:
        if window is None:
            return DataStatus.MISSING
        if window.data_status == DataStatus.NO_EVENTS:
            return DataStatus.NO_EVENTS
        if window.data_status == DataStatus.PARTIAL:
            return DataStatus.PARTIAL
        if window.data_status == DataStatus.OK:
            return DataStatus.OK
        return window.data_status

    def _raw_snapshot(
        self,
        windows: Dict[int, Optional[FeeWindow]],
    ) -> Dict[str, object]:
        source_300s = windows[300]
        snapshot: Dict[str, object] = {
            "fee_window_60s_id": self._window_id(windows[60]),
            "fee_window_300s_id": self._window_id(windows[300]),
            "fee_window_900s_id": self._window_id(windows[900]),
            "fee_window_1800s_id": self._window_id(windows[1800]),
            "fee_window_3600s_id": self._window_id(windows[3600]),
            "fee_window_300s_metrics": {},
        }
        if source_300s is not None:
            snapshot["fee_window_300s_metrics"] = {
                "events_per_min": source_300s.events_per_min,
                "fees_per_min_sol": source_300s.fees_per_min_sol,
                "creator_fee_share": source_300s.creator_fee_share,
                "lp_fee_share": source_300s.lp_fee_share,
                "protocol_fee_share": source_300s.protocol_fee_share,
                "buy_sell_count_ratio": source_300s.buy_sell_count_ratio,
                "data_status": source_300s.data_status.value,
                "missing_reasons": source_300s.missing_reasons,
            }
        return snapshot

    def _window_id(self, window: Optional[FeeWindow]) -> Optional[int]:
        return window.id if window is not None else None

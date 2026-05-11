"""DecisionFeatureSnapshotService.

Stage 11. Records one decision-time typed snapshot of upstream feature
state per WOULD_ALERT alert decision. Single-table writer
(``decision_score_features``).

Reads the seven upstream sources enumerated by Stage 11 Locked Design
Spec L5: ``alert_decisions``, ``token_sequence_state``, ``ath_state``
plus ``ath_events`` (via ATHRepository), ``field_features``,
``clock_features``, and ``fee_windows`` (via FK navigation from
field_features). Never reads ``filter_evaluations``, ``outcome_windows``,
``dispatch_events``, the legacy ``score_features`` table,
``price_observations``, ``raw_pumpswap_events``, or live infrastructure.

Stores measurement primitives only -- no scores, no labels, no policy
verdicts, no composites (L9, L10, L11). The substrate exists so Stage 12
can join ``alert_decisions x filter_evaluations x decision_score_features
x outcome_windows`` for outcome correlation analysis.

Default ``as_of_time`` policy is ``decision.evaluated_at``, NOT wall-clock
``now()``. This is a deliberate departure from Stage 9 / Stage 10 which
default to wall-clock; Stage 11 is a *decision-time* snapshot service so
the canonical default is decision time. ``current_time_provider`` is
reserved for the persisted ``created_at`` audit field.

Validation failures (decision not found / non-WOULD_ALERT / missing
``evaluated_at``) short-circuit before any upstream read and return a
result with ``error=<sentinel>`` and no DB write -- matching Stage 9 and
Stage 10 validation-failure semantics. Repository exceptions during
upstream reads PROPAGATE; only the documented missing-upstream
conditions become NULL columns plus missing-reason codes.
"""

import logging
import sqlite3
from dataclasses import replace
from datetime import datetime, timezone
from math import isfinite
from typing import Any, Callable, Dict, List, Optional, Tuple

from PHX2.db.repositories import (
    ATHRepository,
    AlertDecisionRepository,
    ClockFeatureRepository,
    DecisionScoreFeatureRepository,
    FeeWindowRepository,
    FieldFeatureRepository,
    TokenSequenceRepository,
)
from PHX2.models import (
    ATHState,
    AlertDecision,
    ClockFeatures,
    DataStatus,
    DecisionFeatureSnapshotResult,
    DecisionScoreFeatures,
    DecisionType,
    FeeWindow,
    FieldFeatures,
    TokenState,
)
from PHX2.models.decision_feature_snapshot_result import (
    ERROR_ALERT_DECISION_NOT_FOUND,
    ERROR_DECISION_TIME_MISSING,
    ERROR_DECISION_TYPE_NOT_WOULD_ALERT,
)


__all__ = [
    "DecisionFeatureSnapshotService",
    "ERROR_ALERT_DECISION_NOT_FOUND",
    "ERROR_DECISION_TIME_MISSING",
    "ERROR_DECISION_TYPE_NOT_WOULD_ALERT",
    "derive_data_status",
]


logger = logging.getLogger(__name__)


CurrentTimeProvider = Callable[[], datetime]


# Auxiliary fee-window labels enumerated for source_snapshot_json.aux_windows.
# 5m (300s) is omitted because it is captured in typed columns.
_AUX_WINDOW_SECONDS: Tuple[int, ...] = (60, 900, 1800, 3600)


def _default_current_time() -> datetime:
    return datetime.now(timezone.utc)


def _is_unique_violation(exc: sqlite3.IntegrityError) -> bool:
    """True iff this IntegrityError is a SQLite UNIQUE-constraint failure.

    Matches the Stage 10 ``filter_evaluation_engine._is_unique_violation``
    convention so Stage 11 has the same UNIQUE-race-tolerance semantics.
    """

    return "UNIQUE constraint failed" in str(exc)


def _is_finite_positive(value: Optional[float]) -> bool:
    """True iff value is finite and strictly positive.

    Used for basis-validity checks: a basis group is valid when at
    least one of its (price, market_cap) inputs is finite and positive.
    Mirrors the Stage 9 ``_is_finite_positive`` convention.
    """

    if value is None:
        return False
    try:
        n = float(value)
    except (TypeError, ValueError):
        return False
    return isfinite(n) and n > 0


def _iso(value: Optional[datetime]) -> Optional[str]:
    if value is None:
        return None
    return value.isoformat()


def derive_data_status(
    *,
    alert_basis_valid: bool,
    ath_basis_valid: bool,
    migration_basis_valid: bool,
    field_features_present: bool,
    clock_features_present: bool,
    fee_window_300s_present: bool,
    token_sequence_state_present: bool,
) -> DataStatus:
    """Pure function deriving ``data_status`` from upstream-presence flags.

    Implements Stage 11 Locked Design Spec section 7.1:

    * **OK**: all three basis groups valid AND field_features row present
      AND clock_features row present AND fee_window_300s present AND
      token_sequence_state present (basis groups subsume token_sequence
      already; the explicit check is for safety).
    * **MISSING**: all three basis groups missing, OR both
      field_features AND clock_features absent. The row was created but
      lacks enough basis/context to be analytically useful.
    * **PARTIAL**: any other combination where at least one coarse
      upstream / basis is missing.

    Module-level so tests can exercise the classification boundaries
    without spinning up a service or repository registry.
    """

    invalid_basis_count = sum(
        1
        for valid in (
            alert_basis_valid,
            ath_basis_valid,
            migration_basis_valid,
        )
        if not valid
    )
    critical_upstream_missing = (
        not field_features_present
    ) and (
        not clock_features_present
    )
    if invalid_basis_count == 3 or critical_upstream_missing:
        return DataStatus.MISSING

    coarse_present = (
        invalid_basis_count > 0
        or not field_features_present
        or not clock_features_present
        or not fee_window_300s_present
        or not token_sequence_state_present
    )
    if coarse_present:
        return DataStatus.PARTIAL
    return DataStatus.OK


def _aux_window_payload(window: Optional[FeeWindow]) -> Optional[Dict[str, Any]]:
    """Build the per-window dict for ``source_snapshot.aux_windows``.

    Returns ``None`` when the source row was missing -- the caller omits
    the entry entirely from the aux_windows mapping (per spec §8.6,
    "Each entry is omitted if the source row is missing").
    """

    if window is None:
        return None
    return {
        "events_per_min": window.events_per_min,
        "fees_per_min_sol": window.fees_per_min_sol,
        "creator_fee_share": window.creator_fee_share,
        "lp_fee_share": window.lp_fee_share,
        "protocol_fee_share": window.protocol_fee_share,
        "buy_sell_count_ratio": window.buy_sell_count_ratio,
        "event_count": window.event_count,
        "data_status": window.data_status.value,
    }


def _extract_basis_flag(
    decision_snapshot: Dict[str, Any],
    *keys: str,
) -> Optional[str]:
    """Read a basis label from ``decision.key_feature_snapshot`` if present.

    Stage 7's ``alert_decisions.key_feature_snapshot_json`` may include
    explicit ``pump_multiple_basis`` / ``drawdown_basis`` markers under
    a few possible top-level keys. The function walks the candidate path
    list and returns the first ``"mcap" | "price"`` it finds, or None
    if no path is populated. Inferring the basis from which fields
    happen to be present is the caller's fallback (see
    ``_infer_basis_flags``).
    """

    for key in keys:
        value = decision_snapshot.get(key)
        if value in ("mcap", "price"):
            return value
    return None


def _infer_basis_flags(decision: AlertDecision) -> Dict[str, Optional[str]]:
    """Best-effort basis inference when the decision snapshot lacks them.

    Falls back to "mcap" if alert_market_cap is positive, else "price"
    if alert_price is positive, else None. Same inference for drawdown.
    Only used when ``decision.key_feature_snapshot`` does not record an
    explicit basis label.
    """

    snapshot = decision.key_feature_snapshot or {}
    pump_basis = _extract_basis_flag(
        snapshot, "pump_multiple_basis", "basis_pump_multiple"
    )
    drawdown_basis = _extract_basis_flag(
        snapshot, "drawdown_basis", "basis_drawdown"
    )
    if pump_basis is None:
        if _is_finite_positive(decision.current_mcap):
            pump_basis = "mcap"
        elif _is_finite_positive(decision.current_price):
            pump_basis = "price"
    if drawdown_basis is None:
        if _is_finite_positive(decision.current_mcap):
            drawdown_basis = "mcap"
        elif _is_finite_positive(decision.current_price):
            drawdown_basis = "price"
    return {
        "pump_multiple_basis": pump_basis,
        "drawdown_basis": drawdown_basis,
    }


class DecisionFeatureSnapshotService:
    """Stage 11. Sole writer of decision_score_features rows.

    Single-table writer. Accepts six read repositories plus one write
    repository at construction time -- the full ``RepositoryRegistry``
    is intentionally NOT injected. Read-isolation is enforced via the
    constructor surface: there is no FilterEvaluationRepository,
    OutcomeWindowRepository, DispatchEventRepository, ScoreFeatureRepository,
    PriceObservationRepository, or RawPumpSwapEventRepository in scope
    inside the service body, so accidental forbidden reads are caught at
    construction time as a missing dependency.

    Stores measurement primitives only. The service computes no scores,
    no risk aggregates, no composites, and no filter labels (L9, L10,
    L11 in the locked design spec). It does not read
    ``decision.filter_labels`` (currently always {} but this would
    constitute covert filter-evaluations coupling once that field is
    populated). It does not read or write the legacy abstract-score
    columns on alert_decisions (score_features_id, field_score,
    setup_score, clock_score, risk_score, composite_score).
    """

    SCHEMA_VERSION: str = "schema_v0"
    FEATURE_VERSION: str = "decision_features_v0_observe_only"
    SERVICE_NAME: str = "DecisionFeatureSnapshotService"

    def __init__(
        self,
        alert_decisions: AlertDecisionRepository,
        token_sequence: TokenSequenceRepository,
        ath: ATHRepository,
        field_features: FieldFeatureRepository,
        clock_features: ClockFeatureRepository,
        fee_windows: FeeWindowRepository,
        decision_score_features: DecisionScoreFeatureRepository,
        current_time_provider: Optional[CurrentTimeProvider] = None,
    ) -> None:
        self.alert_decisions = alert_decisions
        self.token_sequence = token_sequence
        self.ath = ath
        self.field_features = field_features
        self.clock_features = clock_features
        self.fee_windows = fee_windows
        self.decision_score_features = decision_score_features
        self.current_time_provider = (
            current_time_provider or _default_current_time
        )

    def snapshot_for_decision(
        self,
        alert_decision_id: int,
        as_of_time: Optional[datetime] = None,
    ) -> DecisionFeatureSnapshotResult:
        """Snapshot one alert decision into ``decision_score_features``.

        Validation order:

        1. Decision must exist.
        2. ``decision.decision_type`` must be WOULD_ALERT.
        3. ``decision.evaluated_at`` must be non-None.

        Each validation failure returns a result with the relevant
        sentinel ``error`` and no DB write.

        ``as_of_time`` defaults to ``decision.evaluated_at`` (NOT
        wall-clock now). The persisted ``created_at`` is taken from
        ``current_time_provider`` and is unrelated to ``as_of_time``.
        """

        decision = self.alert_decisions.get(alert_decision_id)
        if decision is None:
            return DecisionFeatureSnapshotResult(
                alert_decision_id=alert_decision_id,
                feature_version=self.FEATURE_VERSION,
                error=ERROR_ALERT_DECISION_NOT_FOUND,
            )
        if decision.decision_type != DecisionType.WOULD_ALERT:
            return DecisionFeatureSnapshotResult(
                alert_decision_id=alert_decision_id,
                feature_version=self.FEATURE_VERSION,
                error=ERROR_DECISION_TYPE_NOT_WOULD_ALERT,
            )
        if decision.evaluated_at is None:
            return DecisionFeatureSnapshotResult(
                alert_decision_id=alert_decision_id,
                feature_version=self.FEATURE_VERSION,
                error=ERROR_DECISION_TIME_MISSING,
            )

        effective_as_of_time = (
            as_of_time if as_of_time is not None else decision.evaluated_at
        )

        existing = self.decision_score_features.get_by_decision_and_version(
            alert_decision_id, self.FEATURE_VERSION
        )
        if existing is not None:
            return DecisionFeatureSnapshotResult(
                alert_decision_id=alert_decision_id,
                feature_version=self.FEATURE_VERSION,
                snapshot=existing,
                decision_score_features_id=existing.id,
                already_recorded=True,
                missing_reasons=existing.missing_reasons,
            )

        snapshot = self._build_snapshot(
            decision=decision,
            alert_decision_id=alert_decision_id,
            as_of_time=effective_as_of_time,
        )

        try:
            new_id = self.decision_score_features.insert(snapshot)
        except sqlite3.IntegrityError as exc:
            if not _is_unique_violation(exc):
                raise
            existing = (
                self.decision_score_features.get_by_decision_and_version(
                    alert_decision_id, self.FEATURE_VERSION
                )
            )
            if existing is None:
                # Genuine constraint violation that wasn't a race.
                raise
            logger.warning(
                "decision_score_features_unique_race",
                extra={
                    "alert_decision_id": alert_decision_id,
                    "feature_version": self.FEATURE_VERSION,
                },
            )
            return DecisionFeatureSnapshotResult(
                alert_decision_id=alert_decision_id,
                feature_version=self.FEATURE_VERSION,
                snapshot=existing,
                decision_score_features_id=existing.id,
                already_recorded=True,
                missing_reasons=existing.missing_reasons,
            )

        snapshot_with_id = replace(snapshot, id=new_id)
        return DecisionFeatureSnapshotResult(
            alert_decision_id=alert_decision_id,
            feature_version=self.FEATURE_VERSION,
            snapshot=snapshot_with_id,
            decision_score_features_id=new_id,
            already_recorded=False,
            missing_reasons=snapshot.missing_reasons,
        )

    # ------------------------------------------------------------------
    # Snapshot construction (internal)
    # ------------------------------------------------------------------

    def _build_snapshot(
        self,
        *,
        decision: AlertDecision,
        alert_decision_id: int,
        as_of_time: datetime,
    ) -> DecisionScoreFeatures:
        token_address = decision.token_address
        missing_reasons: List[str] = []

        # Per-upstream reads. Each upstream is loaded inside its own
        # narrowly-scoped read; a None return means "row absent" and
        # appends the appropriate missing-reason marker. Repository
        # exceptions are not caught -- they propagate to the caller as
        # genuine runtime failures, per spec section 11.
        token_state: Optional[TokenState] = self.token_sequence.get(
            token_address
        )
        if token_state is None:
            missing_reasons.append("token_sequence_state_missing")

        ath_state: Optional[ATHState] = self.ath.get_state_at_or_before(
            token_address, as_of_time
        )
        if ath_state is None:
            missing_reasons.append("ath_state_missing")

        field_features: Optional[FieldFeatures] = (
            self.field_features.get_latest_at_or_before(
                token_address, as_of_time
            )
        )
        if field_features is None:
            missing_reasons.append("field_features_missing")

        clock_features: Optional[ClockFeatures] = (
            self.clock_features.get_latest_at_or_before(
                token_address, as_of_time
            )
        )
        if clock_features is None:
            missing_reasons.append("clock_features_missing")

        # 5m fee window via FK navigation from field_features. Stage 11
        # uses ``fee_windows.get_by_id`` (the new ride-along method)
        # rather than ``fee_windows.get(token, as_of, 300)`` to avoid
        # depending on the field_features/fee_windows shared-as_of
        # invariant.
        fee_window_300s: Optional[FeeWindow] = None
        fee_window_300s_id = (
            field_features.fee_window_300s_id
            if field_features is not None
            else None
        )
        if fee_window_300s_id is None:
            missing_reasons.append("fee_window_300s_id_unset")
            missing_reasons.append("fee_window_300s_missing")
        else:
            fee_window_300s = self.fee_windows.get_by_id(fee_window_300s_id)
            if fee_window_300s is None:
                missing_reasons.append("fee_window_300s_missing")

        # Auxiliary fee windows (60s / 900s / 1800s / 3600s) for the
        # source_snapshot.aux_windows section. Each is independent: a
        # missing aux window only omits its entry, not any typed column.
        aux_fee_windows: Dict[str, Optional[FeeWindow]] = {}
        for window_seconds in _AUX_WINDOW_SECONDS:
            fk_attr = f"fee_window_{window_seconds}s_id"
            fk_value = (
                getattr(field_features, fk_attr)
                if field_features is not None
                else None
            )
            aux_fee_windows[f"{window_seconds}s"] = (
                self.fee_windows.get_by_id(fk_value)
                if fk_value is not None
                else None
            )

        # Decision context (denormalized at decision time for
        # self-contained reads).
        token_symbol = (
            token_state.symbol if token_state is not None else None
        )

        alert_price = decision.current_price
        alert_market_cap = decision.current_mcap
        if not _is_finite_positive(alert_price):
            missing_reasons.append("alert_price_missing")
        if not _is_finite_positive(alert_market_cap):
            missing_reasons.append("alert_market_cap_missing")
        alert_basis_valid = _is_finite_positive(
            alert_price
        ) or _is_finite_positive(alert_market_cap)
        if not alert_basis_valid:
            missing_reasons.append("alert_basis_missing")

        ath_price = ath_state.ath_price if ath_state is not None else None
        ath_market_cap = ath_state.ath_mcap if ath_state is not None else None
        ath_time = ath_state.ath_time if ath_state is not None else None
        if not _is_finite_positive(ath_price):
            missing_reasons.append("ath_price_missing")
        if not _is_finite_positive(ath_market_cap):
            missing_reasons.append("ath_market_cap_missing")
        if ath_time is None:
            missing_reasons.append("ath_time_missing")
        ath_basis_valid = _is_finite_positive(
            ath_price
        ) or _is_finite_positive(ath_market_cap)
        if not ath_basis_valid:
            missing_reasons.append("ath_basis_missing")

        migration_price = (
            token_state.migration_price if token_state is not None else None
        )
        migration_market_cap = (
            token_state.migration_mcap if token_state is not None else None
        )
        migration_time = (
            token_state.migration_time if token_state is not None else None
        )
        if not _is_finite_positive(migration_price):
            missing_reasons.append("migration_price_missing")
        if not _is_finite_positive(migration_market_cap):
            missing_reasons.append("migration_mcap_missing")
        migration_basis_valid = _is_finite_positive(
            migration_price
        ) or _is_finite_positive(migration_market_cap)
        if not migration_basis_valid:
            missing_reasons.append("migration_basis_missing")

        # liquidity_usd: informational fine code only. Per spec §7.2 it
        # does NOT degrade data_status to PARTIAL on its own, which is
        # naturally handled by ``derive_data_status`` (which only
        # consumes the coarse-tier flags below).
        liquidity_usd = (
            field_features.liquidity_usd
            if field_features is not None
            else None
        )
        if field_features is not None and liquidity_usd is None:
            missing_reasons.append("liquidity_usd_unpopulated")

        # Field 5m primitives.
        event_count_5m = (
            field_features.event_count_5m
            if field_features is not None
            else None
        )
        creator_fee_share_5m = (
            field_features.creator_fee_share_5m
            if field_features is not None
            else None
        )
        lp_fee_share_5m = (
            field_features.lp_fee_share_5m
            if field_features is not None
            else None
        )
        protocol_fee_share_5m = (
            field_features.protocol_fee_share_5m
            if field_features is not None
            else None
        )
        events_per_minute_5m = (
            field_features.event_pace_5m
            if field_features is not None
            else None
        )
        fees_per_minute_5m = (
            field_features.fee_pace_5m_sol
            if field_features is not None
            else None
        )

        # Fee 5m amounts (SOL-denominated) come from the 300s fee_window
        # row, not from field_features.
        total_fee_5m = (
            fee_window_300s.total_fee_sol
            if fee_window_300s is not None
            else None
        )
        lp_fee_5m = (
            fee_window_300s.lp_fee_sol
            if fee_window_300s is not None
            else None
        )
        protocol_fee_5m = (
            fee_window_300s.protocol_fee_sol
            if fee_window_300s is not None
            else None
        )
        creator_fee_5m = (
            fee_window_300s.creator_fee_sol
            if fee_window_300s is not None
            else None
        )
        fee_per_event_5m = (
            fee_window_300s.avg_fee_per_event_sol
            if fee_window_300s is not None
            else None
        )

        # Clock primitives.
        time_since_migration_seconds = (
            clock_features.age_since_migration_s
            if clock_features is not None
            else None
        )
        time_since_ath_seconds = (
            clock_features.time_since_ath_s
            if clock_features is not None
            else None
        )
        time_from_migration_to_ath_seconds = (
            clock_features.time_to_ath_s
            if clock_features is not None
            else None
        )

        # Tier and derived measurements (sourced from the decision row;
        # Stage 7 already snapshotted them).
        tier_index = decision.tier_index
        tier_name = decision.tier_name
        drop_from_ath = decision.drawdown_from_ath
        multiple_from_migration = decision.pump_multiple

        # Build source_snapshot per spec §8.
        snapshot_built_at = self.current_time_provider()
        envelope = {
            "service_name": self.SERVICE_NAME,
            "feature_version": self.FEATURE_VERSION,
            "schema_version": self.SCHEMA_VERSION,
            "snapshot_built_at": _iso(snapshot_built_at),
            "decision_time": _iso(decision.evaluated_at),
            "as_of_time": _iso(as_of_time),
        }
        upstream_refs: Dict[str, Any] = {
            "alert_decision_id": alert_decision_id,
            "price_observation_id": decision.price_observation_id,
            "ath_event_id": decision.ath_event_id,
            "ath_state_last_event_id": (
                ath_state.last_event_id if ath_state is not None else None
            ),
            "field_features_id": (
                field_features.id if field_features is not None else None
            ),
            "clock_features_id": (
                clock_features.id if clock_features is not None else None
            ),
            "fee_window_60s_id": (
                field_features.fee_window_60s_id
                if field_features is not None
                else None
            ),
            "fee_window_300s_id": fee_window_300s_id,
            "fee_window_900s_id": (
                field_features.fee_window_900s_id
                if field_features is not None
                else None
            ),
            "fee_window_1800s_id": (
                field_features.fee_window_1800s_id
                if field_features is not None
                else None
            ),
            "fee_window_3600s_id": (
                field_features.fee_window_3600s_id
                if field_features is not None
                else None
            ),
            "token_sequence_state_token_address": token_address,
        }
        ath_status_value = (
            decision.ath_status.value if decision.ath_status is not None else None
        )
        ath_confidence_value = (
            decision.ath_confidence.value
            if decision.ath_confidence is not None
            else None
        )
        ath_provenance: Dict[str, Any] = {
            "ath_status": ath_status_value,
            "ath_confidence": ath_confidence_value,
            "ath_source": decision.ath_source,
        }
        basis_flags: Dict[str, Any] = _infer_basis_flags(decision)

        aux_windows: Dict[str, Any] = {}
        for label, window in aux_fee_windows.items():
            payload = _aux_window_payload(window)
            if payload is not None:
                aux_windows[label] = payload

        clock_aux: Dict[str, Any] = {
            "last_fee_event_time": (
                _iso(clock_features.last_fee_event_time)
                if clock_features is not None
                else None
            ),
            "time_since_last_fee_event_s": (
                clock_features.time_since_last_fee_event_s
                if clock_features is not None
                else None
            ),
            "sequence_phase": (
                clock_features.sequence_phase
                if clock_features is not None
                else "unknown"
            ),
            "phase_reason": (
                clock_features.phase_reason
                if clock_features is not None
                else None
            ),
        }
        source_snapshot: Dict[str, Any] = {
            "envelope": envelope,
            "upstream_refs": upstream_refs,
            "ath_provenance": ath_provenance,
            "basis_flags": basis_flags,
            "aux_windows": aux_windows,
            "clock_aux": clock_aux,
        }

        data_status = derive_data_status(
            alert_basis_valid=alert_basis_valid,
            ath_basis_valid=ath_basis_valid,
            migration_basis_valid=migration_basis_valid,
            field_features_present=field_features is not None,
            clock_features_present=clock_features is not None,
            fee_window_300s_present=fee_window_300s is not None,
            token_sequence_state_present=token_state is not None,
        )

        return DecisionScoreFeatures(
            alert_decision_id=alert_decision_id,
            feature_version=self.FEATURE_VERSION,
            schema_version=self.SCHEMA_VERSION,
            token_address=token_address,
            token_symbol=token_symbol,
            decision_time=decision.evaluated_at,
            as_of_time=as_of_time,
            tier_index=tier_index,
            tier_name=tier_name,
            alert_price=alert_price,
            alert_market_cap=alert_market_cap,
            ath_price=ath_price,
            ath_market_cap=ath_market_cap,
            ath_time=ath_time,
            migration_price=migration_price,
            migration_market_cap=migration_market_cap,
            migration_time=migration_time,
            drop_from_ath=drop_from_ath,
            multiple_from_migration=multiple_from_migration,
            time_since_migration_seconds=time_since_migration_seconds,
            time_since_ath_seconds=time_since_ath_seconds,
            time_from_migration_to_ath_seconds=time_from_migration_to_ath_seconds,
            liquidity_usd=liquidity_usd,
            event_count_5m=event_count_5m,
            total_fee_5m=total_fee_5m,
            lp_fee_5m=lp_fee_5m,
            protocol_fee_5m=protocol_fee_5m,
            creator_fee_5m=creator_fee_5m,
            creator_fee_share_5m=creator_fee_share_5m,
            lp_fee_share_5m=lp_fee_share_5m,
            protocol_fee_share_5m=protocol_fee_share_5m,
            fee_per_event_5m=fee_per_event_5m,
            events_per_minute_5m=events_per_minute_5m,
            fees_per_minute_5m=fees_per_minute_5m,
            source_snapshot=source_snapshot,
            created_at=snapshot_built_at,
            data_status=data_status,
            missing_reasons=tuple(missing_reasons),
        )

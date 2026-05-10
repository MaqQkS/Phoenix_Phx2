"""AlertEligibilityEngine.

Stage 7. The sole owner of tier eligibility and "would this token alert" answers.
Reads existing PHX2 state (token_sequence, latest at-or-before price observation,
ATH state, optional field/clock features) and writes exactly one alert_decisions
row per evaluation. Performs no rendering, dispatch, network I/O, or writes to
any other PHX2 table.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from math import isfinite
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional, Tuple

from PHX2.db.repositories import (
    ATHRepository,
    AlertDecisionRepository,
    ClockFeatureRepository,
    FieldFeatureRepository,
    PriceObservationRepository,
    TokenSequenceRepository,
)

if TYPE_CHECKING:
    from PHX2.dispatch.preview_pipeline import PreviewPipeline


logger = logging.getLogger(__name__)
from PHX2.models import (
    ATHConfidence,
    ATHState,
    ATHStatus,
    AlertDecision,
    ClockFeatures,
    DataStatus,
    DecisionReason,
    DecisionType,
    FieldFeatures,
    PriceObservation,
    TokenState,
)


CurrentTimeProvider = Callable[[], datetime]


def _default_current_time() -> datetime:
    return datetime.now(timezone.utc)


_CRITICAL_MISSING_CODES = frozenset(
    {
        "token_not_found",
        "missing_price_observation",
        "missing_current_price",
        "invalid_current_price",
        "missing_migration_price",
        "invalid_migration_price",
        "missing_ath",
        "ath_unknown",
        "ath_data_limited",
        "missing_pump_multiple",
        "missing_drawdown",
        "invalid_ath_price",
    }
)

_PARTIAL_MISSING_CODES = frozenset(
    {
        "price_stale",
        "field_features_missing",
        "clock_features_missing",
        "ath_confidence_too_low",
    }
)


@dataclass(frozen=True)
class AlertTier:
    """One drawdown tier band."""

    tier_index: int
    tier_name: str
    drawdown_min: float
    drawdown_max: float
    min_inclusive: bool = True
    max_inclusive: bool = False

    def matches(self, drawdown: float) -> bool:
        lo_ok = (
            drawdown >= self.drawdown_min
            if self.min_inclusive
            else drawdown > self.drawdown_min
        )
        hi_ok = (
            drawdown <= self.drawdown_max
            if self.max_inclusive
            else drawdown < self.drawdown_max
        )
        return lo_ok and hi_ok

    def to_range_dict(self) -> Dict[str, Any]:
        return {
            "min": self.drawdown_min,
            "max": self.drawdown_max,
            "min_inclusive": self.min_inclusive,
            "max_inclusive": self.max_inclusive,
        }


@dataclass(frozen=True)
class AlertPolicy:
    """Tier eligibility policy. Frozen so tests can share one default safely."""

    policy_version: str = "alert_policy_v0_observe_only"
    enabled: bool = True
    min_pump_multiple: float = 1.30
    max_price_age_seconds: float = 300.0
    tiers: Tuple[AlertTier, ...] = (
        AlertTier(1, "T1", 0.55, 0.65, min_inclusive=True, max_inclusive=False),
        AlertTier(2, "T2", 0.65, 0.80, min_inclusive=True, max_inclusive=False),
        AlertTier(3, "T3", 0.80, 0.93, min_inclusive=True, max_inclusive=True),
    )

    def first_tier_min(self) -> Optional[float]:
        if not self.tiers:
            return None
        return self.tiers[0].drawdown_min

    def last_tier_max(self) -> Optional[float]:
        if not self.tiers:
            return None
        return self.tiers[-1].drawdown_max

    def last_tier_max_inclusive(self) -> bool:
        if not self.tiers:
            return False
        return self.tiers[-1].max_inclusive

    def match_tier(self, drawdown: float) -> Optional[AlertTier]:
        for tier in self.tiers:
            if tier.matches(drawdown):
                return tier
        return None


DEFAULT_ALERT_POLICY = AlertPolicy()


@dataclass
class _EvalContext:
    """Mutable working state assembled during one evaluation."""

    token_address: str
    evaluated_at: datetime
    token_state: Optional[TokenState] = None
    price_obs: Optional[PriceObservation] = None
    ath_state: Optional[ATHState] = None
    field_feat: Optional[FieldFeatures] = None
    clock_feat: Optional[ClockFeatures] = None
    pump_multiple: Optional[float] = None
    pump_basis: str = "missing"
    drawdown: Optional[float] = None
    drawdown_basis: str = "missing"
    price_age_seconds: Optional[float] = None
    matched_tier: Optional[AlertTier] = None
    optional_missing: List[str] = field(default_factory=list)


def _is_finite_positive(value: Any) -> bool:
    if value is None:
        return False
    try:
        n = float(value)
    except (TypeError, ValueError):
        return False
    return isfinite(n) and n > 0


def _is_invalid_numeric(value: Any) -> bool:
    """True only if value is present-but-bad (NaN, inf, <=0). None counts as missing."""

    if value is None:
        return False
    try:
        n = float(value)
    except (TypeError, ValueError):
        return True
    return not isfinite(n) or n <= 0


def _add_unique(collection: List[str], code: str) -> None:
    if code not in collection:
        collection.append(code)


def _derive_data_status(missing_reasons: List[str]) -> DataStatus:
    has_critical = any(code in _CRITICAL_MISSING_CODES for code in missing_reasons)
    if has_critical:
        return DataStatus.MISSING
    has_partial = any(code in _PARTIAL_MISSING_CODES for code in missing_reasons)
    if has_partial:
        return DataStatus.PARTIAL
    return DataStatus.OK


class AlertEligibilityEngine:
    """The sole writer of PHX2 alert_decisions rows."""

    def __init__(
        self,
        token_sequence: TokenSequenceRepository,
        price_observations: PriceObservationRepository,
        ath: ATHRepository,
        field_features: FieldFeatureRepository,
        clock_features: ClockFeatureRepository,
        alert_decisions: AlertDecisionRepository,
        policy: Optional[AlertPolicy] = None,
        current_time_provider: Optional[CurrentTimeProvider] = None,
        preview_pipeline: Optional["PreviewPipeline"] = None,
    ) -> None:
        self.token_sequence = token_sequence
        self.price_observations = price_observations
        self.ath = ath
        self.field_features = field_features
        self.clock_features = clock_features
        self.alert_decisions = alert_decisions
        self.policy = policy if policy is not None else DEFAULT_ALERT_POLICY
        self.current_time_provider = current_time_provider or _default_current_time
        self._preview_pipeline = preview_pipeline

    def evaluate_token(
        self,
        token_address: str,
        as_of_time: Optional[datetime] = None,
    ) -> AlertDecision:
        evaluated_at = as_of_time if as_of_time is not None else self.current_time_provider()
        try:
            return self._evaluate(token_address, evaluated_at)
        except Exception as exc:
            self._record_error_audit(token_address, evaluated_at, exc)
            raise

    def _evaluate(self, token_address: str, evaluated_at: datetime) -> AlertDecision:
        ctx = _EvalContext(token_address=token_address, evaluated_at=evaluated_at)

        # 1. policy disabled
        if not self.policy.enabled:
            return self._finalize(
                ctx,
                decision_type=DecisionType.BLOCK,
                primary_reason=DecisionReason.POLICY_DISABLED,
                extra_reasons=[],
                extra_missing=[],
            )

        # 2. token not found
        token_state = self.token_sequence.get(token_address)
        if token_state is None:
            return self._finalize(
                ctx,
                decision_type=DecisionType.SKIP,
                primary_reason=DecisionReason.TOKEN_NOT_FOUND,
                extra_reasons=[],
                extra_missing=["token_not_found"],
            )
        ctx.token_state = token_state

        # Read remaining state (best-effort; we still try to populate links even
        # when subsequent checks short-circuit).
        ctx.price_obs = self.price_observations.get_latest_at_or_before(
            token_address, evaluated_at
        )
        ctx.ath_state = self.ath.get_state_at_or_before(token_address, evaluated_at)
        ctx.field_feat = self.field_features.get_latest_at_or_before(
            token_address, evaluated_at
        )
        ctx.clock_feat = self.clock_features.get_latest_at_or_before(
            token_address, evaluated_at
        )

        if ctx.field_feat is None:
            _add_unique(ctx.optional_missing, "field_features_missing")
        if ctx.clock_feat is None:
            _add_unique(ctx.optional_missing, "clock_features_missing")

        # 3. missing price observation
        if ctx.price_obs is None:
            return self._finalize(
                ctx,
                decision_type=DecisionType.SKIP,
                primary_reason=DecisionReason.MISSING_PRICE_OBSERVATION,
                extra_reasons=[],
                extra_missing=["missing_price_observation"],
            )

        # 4. current price/mcap missing or invalid
        cur_price = ctx.price_obs.price
        cur_mcap = ctx.price_obs.mcap
        cur_price_invalid = _is_invalid_numeric(cur_price)
        cur_mcap_invalid = _is_invalid_numeric(cur_mcap)
        cur_price_ok = _is_finite_positive(cur_price)
        cur_mcap_ok = _is_finite_positive(cur_mcap)

        if not cur_price_ok and not cur_mcap_ok:
            if cur_price_invalid or cur_mcap_invalid:
                return self._finalize(
                    ctx,
                    decision_type=DecisionType.SKIP,
                    primary_reason=DecisionReason.INVALID_CURRENT_PRICE,
                    extra_reasons=[],
                    extra_missing=["invalid_current_price"],
                )
            return self._finalize(
                ctx,
                decision_type=DecisionType.SKIP,
                primary_reason=DecisionReason.MISSING_CURRENT_PRICE,
                extra_reasons=[],
                extra_missing=["missing_current_price"],
            )

        # 5. migration price/mcap missing or invalid
        mig_price = ctx.token_state.migration_price
        mig_mcap = ctx.token_state.migration_mcap
        mig_price_invalid = _is_invalid_numeric(mig_price)
        mig_mcap_invalid = _is_invalid_numeric(mig_mcap)
        mig_price_ok = _is_finite_positive(mig_price)
        mig_mcap_ok = _is_finite_positive(mig_mcap)

        if not mig_price_ok and not mig_mcap_ok:
            if mig_price_invalid or mig_mcap_invalid:
                return self._finalize(
                    ctx,
                    decision_type=DecisionType.SKIP,
                    primary_reason=DecisionReason.INVALID_MIGRATION_PRICE,
                    extra_reasons=[],
                    extra_missing=["invalid_migration_price"],
                )
            return self._finalize(
                ctx,
                decision_type=DecisionType.SKIP,
                primary_reason=DecisionReason.MISSING_MIGRATION_PRICE,
                extra_reasons=[],
                extra_missing=["missing_migration_price"],
            )

        # 6. ATH missing / unknown / data_limited
        if ctx.ath_state is None:
            return self._finalize(
                ctx,
                decision_type=DecisionType.SKIP,
                primary_reason=DecisionReason.MISSING_ATH,
                extra_reasons=[],
                extra_missing=["missing_ath"],
            )
        ath_status = ctx.ath_state.ath_status
        if ath_status == ATHStatus.UNKNOWN:
            return self._finalize(
                ctx,
                decision_type=DecisionType.SKIP,
                primary_reason=DecisionReason.ATH_UNKNOWN,
                extra_reasons=[],
                extra_missing=["ath_unknown"],
            )
        if ath_status == ATHStatus.DATA_LIMITED:
            return self._finalize(
                ctx,
                decision_type=DecisionType.SKIP,
                primary_reason=DecisionReason.ATH_DATA_LIMITED,
                extra_reasons=[],
                extra_missing=["ath_data_limited"],
            )

        # ATH confidence is a flag, not a blocker.
        if ctx.ath_state.ath_confidence == ATHConfidence.LOW:
            _add_unique(ctx.optional_missing, "ath_confidence_too_low")

        # Compute price_age_seconds from observation.observed_at.
        observed_at = ctx.price_obs.observed_at
        if observed_at is not None:
            ctx.price_age_seconds = (evaluated_at - observed_at).total_seconds()

        # Compute pump_multiple.
        if mig_mcap_ok and cur_mcap_ok:
            ctx.pump_multiple = float(cur_mcap) / float(mig_mcap)
            ctx.pump_basis = "mcap"
        elif mig_price_ok and cur_price_ok:
            ctx.pump_multiple = float(cur_price) / float(mig_price)
            ctx.pump_basis = "price"
        else:
            ctx.pump_multiple = None
            ctx.pump_basis = "missing"

        # Compute drawdown_from_ath.
        ath_price = ctx.ath_state.ath_price
        ath_mcap = ctx.ath_state.ath_mcap
        ath_price_ok = _is_finite_positive(ath_price)
        ath_mcap_ok = _is_finite_positive(ath_mcap)
        if _is_invalid_numeric(ath_price) or _is_invalid_numeric(ath_mcap):
            _add_unique(ctx.optional_missing, "invalid_ath_price")
        if ath_mcap_ok and cur_mcap_ok:
            ctx.drawdown = 1.0 - (float(cur_mcap) / float(ath_mcap))
            ctx.drawdown_basis = "mcap"
        elif ath_price_ok and cur_price_ok:
            ctx.drawdown = 1.0 - (float(cur_price) / float(ath_price))
            ctx.drawdown_basis = "price"
        else:
            ctx.drawdown = None
            ctx.drawdown_basis = "missing"

        # 7. price stale (price_age_seconds > max_price_age_seconds)
        if (
            ctx.price_age_seconds is not None
            and ctx.price_age_seconds > self.policy.max_price_age_seconds
        ):
            return self._finalize(
                ctx,
                decision_type=DecisionType.SKIP,
                primary_reason=DecisionReason.PRICE_STALE,
                extra_reasons=[],
                extra_missing=["price_stale"],
            )

        # 8. pump_multiple missing
        if ctx.pump_multiple is None:
            return self._finalize(
                ctx,
                decision_type=DecisionType.SKIP,
                primary_reason=DecisionReason.MISSING_PUMP_MULTIPLE,
                extra_reasons=[],
                extra_missing=["missing_pump_multiple"],
            )

        # 9. pump_multiple < min
        if ctx.pump_multiple < self.policy.min_pump_multiple:
            return self._finalize(
                ctx,
                decision_type=DecisionType.SKIP,
                primary_reason=DecisionReason.MIN_PUMP_NOT_MET,
                extra_reasons=[],
                extra_missing=[],
            )

        # 10. drawdown missing
        if ctx.drawdown is None:
            return self._finalize(
                ctx,
                decision_type=DecisionType.SKIP,
                primary_reason=DecisionReason.MISSING_DRAWDOWN,
                extra_reasons=[],
                extra_missing=["missing_drawdown"],
            )

        first_min = self.policy.first_tier_min()
        last_max = self.policy.last_tier_max()
        last_max_inclusive = self.policy.last_tier_max_inclusive()

        # 11. drawdown below first tier (strictly less than first_min)
        if first_min is not None and ctx.drawdown < first_min:
            return self._finalize(
                ctx,
                decision_type=DecisionType.SKIP,
                primary_reason=DecisionReason.DRAWDOWN_BELOW_FIRST_TIER,
                extra_reasons=[],
                extra_missing=[],
            )

        # 12. drawdown beyond max tier
        if last_max is not None:
            beyond_max = (
                ctx.drawdown > last_max
                if last_max_inclusive
                else ctx.drawdown >= last_max
            )
            if beyond_max:
                return self._finalize(
                    ctx,
                    decision_type=DecisionType.SKIP,
                    primary_reason=DecisionReason.DRAWDOWN_BEYOND_MAX_TIER,
                    extra_reasons=[],
                    extra_missing=[],
                )

        # 13. tier match
        ctx.matched_tier = self.policy.match_tier(ctx.drawdown)
        if ctx.matched_tier is None:
            # tier_gap — drawdown falls between configured tiers.
            return self._finalize(
                ctx,
                decision_type=DecisionType.SKIP,
                primary_reason=DecisionReason.TIER_GAP,
                extra_reasons=[],
                extra_missing=[],
            )

        # 14 / 15. duplicate-tier and tier-progression rules
        prior = self.alert_decisions.list_would_alerts_for_token(
            token_address, as_of_time=evaluated_at
        )
        prior_tier_indices = [
            d.tier_index for d in prior if d.tier_index is not None
        ]
        if prior_tier_indices:
            max_prior = max(prior_tier_indices)
            if max_prior == ctx.matched_tier.tier_index:
                return self._finalize(
                    ctx,
                    decision_type=DecisionType.SKIP,
                    primary_reason=DecisionReason.DUPLICATE_TIER,
                    extra_reasons=[],
                    extra_missing=[],
                )
            if max_prior > ctx.matched_tier.tier_index:
                return self._finalize(
                    ctx,
                    decision_type=DecisionType.SKIP,
                    primary_reason=DecisionReason.LOWER_OR_EQUAL_TIER_ALREADY_ALERTED,
                    extra_reasons=[],
                    extra_missing=[],
                )

        # 16. WOULD_ALERT
        return self._finalize(
            ctx,
            decision_type=DecisionType.WOULD_ALERT,
            primary_reason=DecisionReason.WOULD_ALERT,
            extra_reasons=[],
            extra_missing=[],
        )

    def _finalize(
        self,
        ctx: _EvalContext,
        *,
        decision_type: DecisionType,
        primary_reason: DecisionReason,
        extra_reasons: List[DecisionReason],
        extra_missing: List[str],
    ) -> AlertDecision:
        # Build reasons list with primary first.
        reasons: List[DecisionReason] = [primary_reason]
        for code in extra_reasons:
            if code not in reasons:
                reasons.append(code)

        # Build missing_reasons list (primary critical/partial code first, then
        # any optional flags collected during evaluation).
        missing_reasons: List[str] = []
        for code in extra_missing:
            _add_unique(missing_reasons, code)
        for code in ctx.optional_missing:
            _add_unique(missing_reasons, code)

        if decision_type == DecisionType.BLOCK:
            data_status = DataStatus.OK
        elif decision_type == DecisionType.WOULD_ALERT:
            data_status = (
                DataStatus.PARTIAL if missing_reasons else DataStatus.OK
            )
        else:
            data_status = _derive_data_status(missing_reasons)

        ath_state = ctx.ath_state
        ath_price = ath_state.ath_price if ath_state is not None else None
        ath_status = (
            ath_state.ath_status if ath_state is not None else ATHStatus.UNKNOWN
        )
        ath_confidence = (
            ath_state.ath_confidence
            if ath_state is not None
            else ATHConfidence.UNKNOWN
        )
        ath_source = ath_state.ath_source if ath_state is not None else None
        ath_event_id = ath_state.last_event_id if ath_state is not None else None

        price_observation_id = (
            ctx.price_obs.id if ctx.price_obs is not None else None
        )
        field_features_id = (
            ctx.field_feat.id if ctx.field_feat is not None else None
        )
        clock_features_id = (
            ctx.clock_feat.id if ctx.clock_feat is not None else None
        )

        tier_index = (
            ctx.matched_tier.tier_index if ctx.matched_tier is not None else None
        )
        tier_name = (
            ctx.matched_tier.tier_name if ctx.matched_tier is not None else None
        )

        tier_context = self._build_tier_context(ctx)
        key_feature_snapshot = self._build_feature_snapshot(
            ctx,
            ath_state=ath_state,
            price_observation_id=price_observation_id,
            field_features_id=field_features_id,
            clock_features_id=clock_features_id,
        )
        current_price = (
            ctx.price_obs.price if ctx.price_obs is not None else None
        )
        current_mcap = (
            ctx.price_obs.mcap if ctx.price_obs is not None else None
        )

        decision = AlertDecision(
            token_address=ctx.token_address,
            evaluated_at=ctx.evaluated_at,
            decision_type=decision_type,
            tier_index=tier_index,
            tier_name=tier_name,
            primary_reason=primary_reason,
            reasons=reasons,
            would_alert=decision_type == DecisionType.WOULD_ALERT,
            blocked=decision_type == DecisionType.BLOCK,
            skipped=decision_type == DecisionType.SKIP,
            price_observation_id=price_observation_id,
            ath_event_id=ath_event_id,
            field_features_id=field_features_id,
            score_features_id=None,
            clock_features_id=clock_features_id,
            field_score=None,
            setup_score=None,
            clock_score=None,
            risk_score=None,
            composite_score=None,
            ath_price=ath_price,
            ath_status=ath_status,
            ath_confidence=ath_confidence,
            ath_source=ath_source,
            price_age_seconds=ctx.price_age_seconds,
            pump_multiple=ctx.pump_multiple,
            drawdown_from_ath=ctx.drawdown,
            current_price=current_price,
            current_mcap=current_mcap,
            filter_labels={},
            tier_context=tier_context,
            key_feature_snapshot=key_feature_snapshot,
            policy_version=self.policy.policy_version,
            data_status=data_status,
            missing_reasons=missing_reasons,
        )
        decision_id = self.alert_decisions.insert(decision)
        if self._preview_pipeline is not None:
            try:
                self._preview_pipeline.handle(decision, ctx.evaluated_at, decision_id)
            except Exception as exc:
                logger.error("preview_pipeline_failed", exc_info=exc)
                # Never re-raise. Engine output must not depend on dispatcher state.
        return decision

    def _build_tier_context(self, ctx: _EvalContext) -> Dict[str, Any]:
        ranges: Dict[str, Dict[str, Any]] = {}
        for tier in self.policy.tiers:
            ranges[tier.tier_name] = tier.to_range_dict()
        return {
            "matched_tier": (
                ctx.matched_tier.tier_name
                if ctx.matched_tier is not None
                else None
            ),
            "tier_index": (
                ctx.matched_tier.tier_index
                if ctx.matched_tier is not None
                else None
            ),
            "drawdown": ctx.drawdown,
            "ranges": ranges,
        }

    def _build_feature_snapshot(
        self,
        ctx: _EvalContext,
        *,
        ath_state: Optional[ATHState],
        price_observation_id: Optional[int],
        field_features_id: Optional[int],
        clock_features_id: Optional[int],
    ) -> Dict[str, Any]:
        cur_price = ctx.price_obs.price if ctx.price_obs is not None else None
        cur_mcap = ctx.price_obs.mcap if ctx.price_obs is not None else None
        mig_price = (
            ctx.token_state.migration_price if ctx.token_state is not None else None
        )
        mig_mcap = (
            ctx.token_state.migration_mcap if ctx.token_state is not None else None
        )
        ath_price = ath_state.ath_price if ath_state is not None else None
        ath_mcap = ath_state.ath_mcap if ath_state is not None else None
        observed_at = ctx.price_obs.observed_at if ctx.price_obs is not None else None
        ath_status = ath_state.ath_status.value if ath_state is not None else None
        ath_confidence = (
            ath_state.ath_confidence.value if ath_state is not None else None
        )

        return {
            "current_price": cur_price,
            "current_mcap": cur_mcap,
            "migration_price": mig_price,
            "migration_mcap": mig_mcap,
            "ath_price": ath_price,
            "ath_mcap": ath_mcap,
            "pump_multiple_basis": ctx.pump_basis,
            "drawdown_basis": ctx.drawdown_basis,
            "price_observed_at": observed_at,
            "evaluation_time": ctx.evaluated_at,
            "price_observation_id": price_observation_id,
            "ath_event_id": (
                ath_state.last_event_id if ath_state is not None else None
            ),
            "ath_status": ath_status,
            "ath_confidence": ath_confidence,
            "price_age_seconds": ctx.price_age_seconds,
            "field_features_id": field_features_id,
            "clock_features_id": clock_features_id,
        }

    def _record_error_audit(
        self,
        token_address: str,
        evaluated_at: datetime,
        exc: BaseException,
    ) -> None:
        """Best-effort: write an ERROR audit row and route it through PreviewPipeline.

        The audit insert is best-effort; if it raises, the original engine
        exception is re-raised by the caller and no pipeline call is made.
        When the insert succeeds and a preview pipeline is attached, the
        ERROR row flows through the same pipeline as normal decisions so
        engine failures appear in dispatch_events / JSONL / console / Discord.
        Pipeline failures during error audit are logged but never re-raised:
        the original engine exception (the ``exc`` parameter) is what the
        caller sees, regardless of dispatcher state.
        """

        try:
            decision = AlertDecision(
                token_address=token_address,
                evaluated_at=evaluated_at,
                decision_type=DecisionType.ERROR,
                tier_index=None,
                tier_name=None,
                primary_reason=DecisionReason.ERROR,
                reasons=[DecisionReason.ERROR],
                would_alert=False,
                blocked=False,
                skipped=False,
                price_observation_id=None,
                ath_event_id=None,
                field_features_id=None,
                score_features_id=None,
                clock_features_id=None,
                field_score=None,
                setup_score=None,
                clock_score=None,
                risk_score=None,
                composite_score=None,
                ath_price=None,
                ath_status=ATHStatus.UNKNOWN,
                ath_confidence=ATHConfidence.UNKNOWN,
                ath_source=None,
                price_age_seconds=None,
                pump_multiple=None,
                drawdown_from_ath=None,
                filter_labels={},
                tier_context={},
                key_feature_snapshot={
                    "evaluation_time": evaluated_at,
                    "exception_type": type(exc).__name__,
                    "exception_message": str(exc),
                },
                policy_version=self.policy.policy_version,
                data_status=DataStatus.ERROR,
                missing_reasons=[
                    "error",
                    f"{type(exc).__name__}: {exc}",
                ],
            )
            decision_id = self.alert_decisions.insert(decision)
        except Exception:
            # Audit row is best-effort; the original exception is re-raised by
            # the caller.
            return

        if self._preview_pipeline is not None:
            try:
                self._preview_pipeline.handle(
                    decision, evaluated_at, decision_id
                )
            except Exception as pipeline_exc:
                logger.error(
                    "preview_pipeline_failed_in_error_audit",
                    exc_info=pipeline_exc,
                )
                # Never re-raise. The original engine exception must still
                # propagate from evaluate_token; pipeline failures here must
                # not interfere.

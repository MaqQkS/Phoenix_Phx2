"""Pure renderer that turns a :class:`RenderingContext` into a :class:`RenderedAlert`.

This module is a hard purity boundary: no I/O, no clock reads, no environment
access, no repository imports. Calling :meth:`AlertRenderer.render` twice with
the same context returns equal :class:`RenderedAlert` instances every time.
"""

from typing import Any, Dict, List, Optional

from PHX2.models import (
    AlertDecision,
    ATHConfidence,
    ATHEvent,
    ATHState,
    ClockFeatures,
    FieldFeatures,
    PriceObservation,
    TokenSequenceState,
)
from PHX2.models.enums import DecisionType
from PHX2.renderers.context import RenderingContext
from PHX2.renderers.formatters import (
    UNKNOWN,
    format_address_full,
    format_address_short,
    format_duration,
    format_mcap,
    format_percent,
    format_price_age,
    format_pump_multiple,
    format_string,
    format_timestamp,
)
from PHX2.renderers.rendered_alert import (
    DRY_RUN_BANNER,
    RenderedAlert,
    Severity,
    derive_severity,
)


class AlertRenderer:
    """Pure function — context in, :class:`RenderedAlert` out.

    The class wrapper exists so callers can hold a renderer instance for
    dependency injection, but :meth:`render` is stateless and could equally be
    a free function.
    """

    def render(self, context: RenderingContext) -> RenderedAlert:
        decision = context.alert_decision
        severity = derive_severity(decision.decision_type, decision.data_status)
        missing: List[str] = []

        token_section = self._build_token_section(context, missing)
        footer = self._build_footer(decision)

        if decision.decision_type == DecisionType.WOULD_ALERT:
            market_section = self._build_market_section(context, missing)
            ath_section = self._build_ath_section(context, missing)
            field_section = self._build_field_section(context, missing)
            clock_section = self._build_clock_section(context, missing)
        else:
            market_section = {}
            ath_section = {}
            field_section = {}
            clock_section = {}

        for code in decision.missing_reasons:
            _add_unique(missing, code)

        headline = self._build_headline(decision, severity)
        tier_label = decision.tier_name

        return RenderedAlert(
            banner=DRY_RUN_BANNER,
            severity=severity,
            decision_type=decision.decision_type.value,
            tier_label=tier_label,
            headline=headline,
            alert_decision_id=context.alert_decision_id,
            token_section=token_section,
            market_section=market_section,
            ath_section=ath_section,
            field_section=field_section,
            clock_section=clock_section,
            missing_section=sorted(missing),
            footer=footer,
        )

    def _build_headline(self, decision: AlertDecision, severity: Severity) -> str:
        type_label = decision.decision_type.value.upper()
        reason = decision.primary_reason.value
        if decision.decision_type == DecisionType.WOULD_ALERT:
            tier = decision.tier_name or UNKNOWN
            base = f"{type_label} — {tier}"
            if severity == Severity.PARTIAL:
                return f"{base} [PARTIAL DATA]"
            return base
        return f"{type_label} — {reason}"

    def _build_token_section(
        self,
        context: RenderingContext,
        missing: List[str],
    ) -> Dict[str, str]:
        decision = context.alert_decision
        token_state = context.token_sequence_state

        symbol = _coalesce_str(token_state.symbol if token_state else None)
        if symbol == UNKNOWN:
            _add_unique(missing, "token_symbol")

        address_full = format_address_full(decision.token_address)
        address_short = format_address_short(decision.token_address)
        if address_full == UNKNOWN:
            _add_unique(missing, "token_address")

        tier_value = decision.tier_name if decision.tier_name else UNKNOWN

        return {
            "symbol": symbol,
            "address": address_full,
            "address_short": address_short,
            "tier": tier_value,
            "primary_reason": decision.primary_reason.value,
        }

    def _build_market_section(
        self,
        context: RenderingContext,
        missing: List[str],
    ) -> Dict[str, str]:
        decision = context.alert_decision
        price = context.price_observation
        token_state = context.token_sequence_state

        current_mc = _format_or_track(
            price.mcap if price is not None else None,
            format_mcap,
            missing,
            "current_mcap",
        )
        migration_mc = _format_or_track(
            token_state.migration_mcap if token_state is not None else None,
            format_mcap,
            missing,
            "migration_mcap",
        )
        ath_mc = _format_or_track(
            _select_ath_mcap(context),
            format_mcap,
            missing,
            "ath_mcap",
        )
        drawdown = _format_or_track(
            decision.drawdown_from_ath,
            format_percent,
            missing,
            "drawdown_from_ath",
        )
        pump_mult = _format_or_track(
            decision.pump_multiple,
            format_pump_multiple,
            missing,
            "pump_multiple",
        )
        price_age = _format_or_track(
            decision.price_age_seconds,
            format_price_age,
            missing,
            "price_age_seconds",
        )
        basis = _coalesce_str(
            decision.tier_context.get("drawdown_basis")
            if isinstance(decision.tier_context, dict)
            else None
        )
        if basis == UNKNOWN:
            basis = _coalesce_str(
                decision.key_feature_snapshot.get("drawdown_basis")
                if isinstance(decision.key_feature_snapshot, dict)
                else None
            )
        if basis == UNKNOWN:
            _add_unique(missing, "calculation_basis")

        return {
            "current_mc": current_mc,
            "migration_mc": migration_mc,
            "ath_mc": ath_mc,
            "drawdown": drawdown,
            "pump_multiple": pump_mult,
            "price_age": price_age,
            "calculation_basis": basis,
        }

    def _build_ath_section(
        self,
        context: RenderingContext,
        missing: List[str],
    ) -> Dict[str, str]:
        decision = context.alert_decision
        ath_state = context.ath_state
        ath_event = context.ath_event

        status = decision.ath_status.value if decision.ath_status else UNKNOWN
        if not status or status == "unknown":
            _add_unique(missing, "ath_status")
            status_value = UNKNOWN
        else:
            status_value = status

        confidence = (
            decision.ath_confidence.value if decision.ath_confidence else UNKNOWN
        )
        if not confidence or decision.ath_confidence == ATHConfidence.UNKNOWN:
            _add_unique(missing, "ath_confidence")
            confidence_value = UNKNOWN
        else:
            confidence_value = confidence

        source = _coalesce_str(decision.ath_source)
        if source == UNKNOWN:
            source = _coalesce_str(ath_state.ath_source if ath_state else None)
        if source == UNKNOWN:
            _add_unique(missing, "ath_source")

        event_time_value: Any = ath_event.event_time if ath_event is not None else None
        if event_time_value is None and ath_state is not None:
            event_time_value = ath_state.ath_time
        event_time = format_timestamp(event_time_value)
        if event_time == UNKNOWN:
            _add_unique(missing, "ath_event_time")

        return {
            "status": status_value,
            "confidence": confidence_value,
            "source": source,
            "ath_event_time": event_time,
        }

    def _build_field_section(
        self,
        context: RenderingContext,
        missing: List[str],
    ) -> Dict[str, str]:
        features = context.field_features
        if features is None:
            _add_unique(missing, "field_features")
            return {
                "liquidity_usd": UNKNOWN,
                "lp_floor_label": UNKNOWN,
                "fee_gate_label": UNKNOWN,
                "ante_label_5m": UNKNOWN,
                "ghost_label": UNKNOWN,
                "holder_label": UNKNOWN,
            }

        liquidity = _format_or_track(
            features.liquidity_usd,
            format_mcap,
            missing,
            "field_features_liquidity_usd",
        )
        lp_floor = _coalesce_str(features.lp_floor_label)
        if lp_floor == UNKNOWN:
            _add_unique(missing, "field_features_lp_floor_label")
        fee_gate = _coalesce_str(features.fee_gate_label)
        if fee_gate == UNKNOWN:
            _add_unique(missing, "field_features_fee_gate_label")
        ante_5m = _coalesce_str(features.ante_label_5m)
        if ante_5m == UNKNOWN:
            _add_unique(missing, "field_features_ante_label_5m")
        ghost = _coalesce_str(features.ghost_label)
        if ghost == UNKNOWN:
            _add_unique(missing, "field_features_ghost_label")
        holder = _coalesce_str(features.holder_label)
        if holder == UNKNOWN:
            _add_unique(missing, "field_features_holder_label")

        return {
            "liquidity_usd": liquidity,
            "lp_floor_label": lp_floor,
            "fee_gate_label": fee_gate,
            "ante_label_5m": ante_5m,
            "ghost_label": ghost,
            "holder_label": holder,
        }

    def _build_clock_section(
        self,
        context: RenderingContext,
        missing: List[str],
    ) -> Dict[str, str]:
        token_state = context.token_sequence_state
        clock = context.clock_features
        ath_state = context.ath_state

        token_age_seconds = _seconds_between(
            context.as_of_time,
            token_state.migration_time if token_state is not None else None,
        )
        token_age = _format_or_track(
            token_age_seconds, format_duration, missing, "token_age"
        )

        time_since_migration_seconds = (
            clock.age_since_migration_s if clock is not None else None
        )
        if time_since_migration_seconds is None:
            time_since_migration_seconds = token_age_seconds
        time_since_migration = _format_or_track(
            time_since_migration_seconds,
            format_duration,
            missing,
            "time_since_migration",
        )

        time_since_ath_seconds = (
            clock.time_since_ath_s if clock is not None else None
        )
        if time_since_ath_seconds is None:
            time_since_ath_seconds = _seconds_between(
                context.as_of_time,
                ath_state.ath_time if ath_state is not None else None,
            )
        time_since_ath = _format_or_track(
            time_since_ath_seconds,
            format_duration,
            missing,
            "time_since_ath",
        )

        return {
            "token_age": token_age,
            "time_since_migration": time_since_migration,
            "time_since_ath": time_since_ath,
        }

    def _build_footer(self, decision: AlertDecision) -> Dict[str, str]:
        return {
            "policy_version": decision.policy_version or UNKNOWN,
            "evaluated_at": format_timestamp(decision.evaluated_at),
        }


def _add_unique(collection: List[str], code: str) -> None:
    if code not in collection:
        collection.append(code)


def _coalesce_str(value: Any) -> str:
    if value is None:
        return UNKNOWN
    if isinstance(value, str):
        if not value or value == "unknown":
            return UNKNOWN
        return value
    return str(value)


def _format_or_track(
    value: Any,
    formatter,
    missing: List[str],
    label: str,
) -> str:
    rendered = formatter(value)
    if rendered == UNKNOWN:
        _add_unique(missing, label)
    return rendered


def _seconds_between(later, earlier) -> Optional[float]:
    if later is None or earlier is None:
        return None
    try:
        return (later - earlier).total_seconds()
    except (TypeError, AttributeError):
        return None


def _select_ath_mcap(context: RenderingContext) -> Any:
    ath_state = context.ath_state
    if ath_state is not None and ath_state.ath_mcap is not None:
        return ath_state.ath_mcap
    ath_event = context.ath_event
    if ath_event is not None and ath_event.new_ath_mcap is not None:
        return ath_event.new_ath_mcap
    return None

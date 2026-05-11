"""FilterEvaluationEngine.

Stage 10. Records filter labels and scores around alert decisions
without coupling them to alert eligibility, renderer output, or
dispatch behavior. Single-table writer (filter_evaluations). Reads
alert_decisions and field_features.

Validation pattern mirrors Stage 9's OutcomeTrackingService:
caller-side errors (unknown decision_id, non-WOULD_ALERT decision_type)
return a DecisionFilterEvaluationResult with ``error`` populated and
empty ``results``; the service does not raise on these paths.
Per-filter exceptions are isolated into ERROR rows; one filter raising
does not prevent others from being evaluated.
"""

import logging
import sqlite3
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Sequence

from PHX2.db.repositories import (
    AlertDecisionRepository,
    FieldFeatureRepository,
    FilterEvaluationRepository,
)
from PHX2.filters.base import Filter, FilterContext
from PHX2.filters.fee_gate import FeeGateFilter
from PHX2.models import (
    DataStatus,
    DecisionFilterEvaluationResult,
    DecisionType,
    FilterLabel,
    FilterResult,
)


logger = logging.getLogger(__name__)


CurrentTimeProvider = Callable[[], datetime]


ERROR_ALERT_DECISION_NOT_FOUND = "alert_decision_not_found"
ERROR_DECISION_TYPE_NOT_WOULD_ALERT = "decision_type_not_would_alert"


def _default_current_time() -> datetime:
    return datetime.now(timezone.utc)


def _is_unique_violation(exc: sqlite3.IntegrityError) -> bool:
    """True iff this IntegrityError is a SQLite UNIQUE-constraint failure.

    SQLite's stable error prefix for unique-constraint violations is
    ``UNIQUE constraint failed:``. Other IntegrityError subclasses
    (CHECK, NOT NULL, FK) use different prefixes.
    """

    return "UNIQUE constraint failed" in str(exc)


def _build_empty_result(
    alert_decision_id: int,
    evaluated_at: datetime,
    total_filters: int,
    error: str,
) -> DecisionFilterEvaluationResult:
    """Result returned when validation fails before any filter runs."""

    return DecisionFilterEvaluationResult(
        alert_decision_id=alert_decision_id,
        evaluated_at=evaluated_at,
        results=[],
        total_filters=total_filters,
        completed_count=0,
        missing_inputs_count=0,
        error_count=0,
        already_recorded_count=0,
        error=error,
    )


def _build_error_result(
    filter_instance: Filter,
    context: FilterContext,
    exc: Exception,
) -> FilterResult:
    """Wrap an unexpected filter exception into an ERROR row."""

    truncated = str(exc)[:200]
    field_features_id = (
        context.field_features.id if context.field_features is not None else None
    )
    return FilterResult(
        token_address=context.token_address,
        filter_name=filter_instance.name,
        as_of_time=context.as_of_time,
        filter_version=filter_instance.filter_version,
        threshold_version=filter_instance.threshold_version,
        label=FilterLabel.UNKNOWN,
        score=None,
        would_block=False,
        policy_action="observe",
        reason=None,
        input_snapshot={
            "envelope": {
                "filter_name": filter_instance.name,
                "filter_version": filter_instance.filter_version,
                "threshold_version": filter_instance.threshold_version,
                "evaluated_at": context.as_of_time,
                "input_source_ids": {
                    "alert_decision_id": context.alert_decision_id,
                    "field_features_id": field_features_id,
                },
                "error_phase": "filter_evaluate",
            },
            "payload": {},
        },
        output_reason={
            "error": {
                "exception_class": type(exc).__name__,
                "message": truncated,
            },
            "known_limitations": list(filter_instance.known_limitations),
        },
        data_status=DataStatus.ERROR,
        missing_reasons=[],
        alert_decision_id=context.alert_decision_id,
    )


class FilterEvaluationEngine:
    """Records filter labels around alert decisions; never blocks alerts."""

    def __init__(
        self,
        alert_decisions: AlertDecisionRepository,
        field_features: FieldFeatureRepository,
        filter_evaluations: FilterEvaluationRepository,
        filters: Optional[Sequence[Filter]] = None,
        current_time_provider: Optional[CurrentTimeProvider] = None,
    ) -> None:
        self.alert_decisions = alert_decisions
        self.field_features = field_features
        self.filter_evaluations = filter_evaluations
        if filters is None:
            self.filters: tuple = (FeeGateFilter(),)
        else:
            self.filters = tuple(filters)
        self.current_time_provider = current_time_provider or _default_current_time

    def evaluate_for_decision(
        self,
        alert_decision_id: int,
        as_of_time: Optional[datetime] = None,
    ) -> DecisionFilterEvaluationResult:
        effective_as_of_time = (
            as_of_time if as_of_time is not None else self.current_time_provider()
        )

        decision = self.alert_decisions.get(alert_decision_id)
        if decision is None:
            return _build_empty_result(
                alert_decision_id=alert_decision_id,
                evaluated_at=effective_as_of_time,
                total_filters=len(self.filters),
                error=ERROR_ALERT_DECISION_NOT_FOUND,
            )

        if decision.decision_type != DecisionType.WOULD_ALERT:
            return _build_empty_result(
                alert_decision_id=alert_decision_id,
                evaluated_at=effective_as_of_time,
                total_filters=len(self.filters),
                error=ERROR_DECISION_TYPE_NOT_WOULD_ALERT,
            )

        snapshot = self.field_features.get_latest_at_or_before(
            decision.token_address, effective_as_of_time
        )

        context = FilterContext(
            alert_decision_id=alert_decision_id,
            token_address=decision.token_address,
            as_of_time=effective_as_of_time,
            alert_decision=decision,
            field_features=snapshot,
        )

        results: List[FilterResult] = []
        counts = {
            "completed": 0,
            "missing": 0,
            "error": 0,
            "already_recorded": 0,
        }
        seen_systemic_failure: Dict[str, bool] = {}

        for filter_instance in self.filters:
            self._evaluate_one_filter(
                filter_instance=filter_instance,
                context=context,
                results=results,
                counts=counts,
                seen_systemic_failure=seen_systemic_failure,
            )

        return DecisionFilterEvaluationResult(
            alert_decision_id=alert_decision_id,
            evaluated_at=effective_as_of_time,
            results=results,
            total_filters=len(self.filters),
            completed_count=counts["completed"],
            missing_inputs_count=counts["missing"],
            error_count=counts["error"],
            already_recorded_count=counts["already_recorded"],
            error=None,
        )

    def _evaluate_one_filter(
        self,
        *,
        filter_instance: Filter,
        context: FilterContext,
        results: List[FilterResult],
        counts: Dict[str, int],
        seen_systemic_failure: Dict[str, bool],
    ) -> None:
        try:
            if self.filter_evaluations.exists_for_decision(
                context.alert_decision_id,
                filter_instance.name,
                filter_instance.filter_version,
                filter_instance.threshold_version,
            ):
                counts["already_recorded"] += 1
                existing_rows = self.filter_evaluations.get_by_decision(
                    context.alert_decision_id
                )
                for row in existing_rows:
                    if (
                        row.filter_name == filter_instance.name
                        and row.filter_version == filter_instance.filter_version
                        and row.threshold_version == filter_instance.threshold_version
                    ):
                        results.append(row)
                return

            try:
                result = filter_instance.evaluate(context)
            except Exception as exc:
                result = _build_error_result(filter_instance, context, exc)
                logger.warning(
                    "filter_evaluate_raised",
                    extra={
                        "filter_name": filter_instance.name,
                        "filter_version": filter_instance.filter_version,
                        "alert_decision_id": context.alert_decision_id,
                        "exception_class": type(exc).__name__,
                    },
                )

            try:
                self.filter_evaluations.insert(result)
            except sqlite3.IntegrityError as exc:
                if _is_unique_violation(exc):
                    counts["already_recorded"] += 1
                    logger.warning(
                        "filter_evaluations_unique_race",
                        extra={
                            "filter_name": filter_instance.name,
                            "filter_version": filter_instance.filter_version,
                            "alert_decision_id": context.alert_decision_id,
                        },
                    )
                    return
                self._log_systemic_failure(
                    "filter_evaluations_insert_integrity_error",
                    exc,
                    filter_instance=filter_instance,
                    context=context,
                    seen=seen_systemic_failure,
                )
                counts["error"] += 1
                return
            except sqlite3.OperationalError as exc:
                self._log_systemic_failure(
                    "filter_evaluations_insert_operational_error",
                    exc,
                    filter_instance=filter_instance,
                    context=context,
                    seen=seen_systemic_failure,
                )
                counts["error"] += 1
                return

            if result.data_status == DataStatus.OK:
                counts["completed"] += 1
            elif result.data_status == DataStatus.MISSING:
                counts["missing"] += 1
            else:  # DataStatus.ERROR or any future status
                counts["error"] += 1
            results.append(result)

        except Exception as outer_exc:
            logger.error(
                "filter_evaluation_unexpected_failure",
                extra={
                    "filter_name": filter_instance.name,
                    "alert_decision_id": context.alert_decision_id,
                    "exception_class": type(outer_exc).__name__,
                },
                exc_info=outer_exc,
            )
            counts["error"] += 1

    @staticmethod
    def _log_systemic_failure(
        event_name: str,
        exc: Exception,
        *,
        filter_instance: Filter,
        context: FilterContext,
        seen: Dict[str, bool],
    ) -> None:
        key = f"{event_name}:{type(exc).__name__}:{str(exc)[:100]}"
        extra: Dict[str, Any] = {
            "filter_name": filter_instance.name,
            "filter_version": filter_instance.filter_version,
            "alert_decision_id": context.alert_decision_id,
            "exception_class": type(exc).__name__,
        }
        if key in seen:
            logger.debug(event_name, extra=extra)
        else:
            seen[key] = True
            logger.warning(event_name, extra=extra, exc_info=exc)

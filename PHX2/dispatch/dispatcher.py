"""Dispatcher: route rendered alerts to sinks and audit each attempt.

The dispatcher does not format or render. It consumes a
:class:`PHX2.renderers.rendered_alert.RenderedAlert` plus the integer
``alert_decision_id`` of the committed decision, looks up the configured sinks
for ``(decision_type, severity)``, and writes a two-phase audit row per
target (``pending`` → ``sent``/``failed``).

The dispatcher never raises into its caller.
"""

import logging
from datetime import datetime, timezone
from typing import Dict, Optional
from uuid import uuid4

from PHX2.dispatch.routing import RoutingConfig, resolve_sinks, validate_routing_config
from PHX2.dispatch.sinks.base import DeliveryContext, DeliveryResult, Sink
from PHX2.models.dispatch_event import DispatchEvent
from PHX2.renderers.rendered_alert import RenderedAlert

logger = logging.getLogger(__name__)


_NONE_TARGET = "(none)"
_VALID_MODES = frozenset({"active", "disabled"})


class Dispatcher:
    """Route already-rendered alerts to sinks and record each attempt."""

    def __init__(
        self,
        sinks: Dict[str, Sink],
        repository,
        routing_config: RoutingConfig,
        mode: str = "active",
        audit_undelivered: bool = True,
    ) -> None:
        if mode not in _VALID_MODES:
            raise ValueError(f"invalid mode: {mode!r}")
        self._sinks = sinks
        self._repo = repository
        self._routing = routing_config
        self._mode = mode
        self._audit_undelivered = audit_undelivered
        self._dispatch_run_id = uuid4().hex

        validate_routing_config(self._routing, set(self._sinks.keys()))

    @property
    def dispatch_run_id(self) -> str:
        return self._dispatch_run_id

    def dispatch(
        self,
        rendered: RenderedAlert,
        alert_decision_id: int,
    ) -> None:
        try:
            self._dispatch(rendered, alert_decision_id)
        except Exception as exc:
            # Defense in depth: never propagate to the pipeline/engine.
            logger.error("dispatcher_unhandled_error", exc_info=exc)

    def _dispatch(
        self,
        rendered: RenderedAlert,
        alert_decision_id: int,
    ) -> None:
        severity_name = rendered.severity.name

        if self._mode == "disabled":
            self._handle_no_targets(
                rendered,
                alert_decision_id,
                severity_name,
                reason="no_targets:disabled",
            )
            return

        targets = resolve_sinks(self._routing, rendered.decision_type, severity_name)
        if not targets:
            self._handle_no_targets(
                rendered,
                alert_decision_id,
                severity_name,
                reason="no_targets:unconfigured_route",
            )
            return

        for target in targets:
            self._dispatch_one(rendered, alert_decision_id, target, severity_name)

    def _handle_no_targets(
        self,
        rendered: RenderedAlert,
        alert_decision_id: int,
        severity_name: str,
        reason: str,
    ) -> None:
        if self._mode == "disabled" and not self._audit_undelivered:
            return
        if self._repo.exists_non_failed(alert_decision_id, _NONE_TARGET):
            return
        now = _utc_now()
        event = DispatchEvent(
            id=uuid4().hex,
            alert_decision_id=alert_decision_id,
            dispatch_run_id=self._dispatch_run_id,
            target=_NONE_TARGET,
            status="skipped",
            decision_type=rendered.decision_type,
            severity=severity_name,
            tier_label=rendered.tier_label,
            attempted_at=now,
            completed_at=now,
            payload_ref=None,
            error_message=reason,
        )
        try:
            self._repo.create(event)
        except Exception as exc:
            logger.error("dispatch_audit_create_failed", exc_info=exc)

    def _dispatch_one(
        self,
        rendered: RenderedAlert,
        alert_decision_id: int,
        target: str,
        severity_name: str,
    ) -> None:
        if target not in self._sinks:
            now = _utc_now()
            event = DispatchEvent(
                id=uuid4().hex,
                alert_decision_id=alert_decision_id,
                dispatch_run_id=self._dispatch_run_id,
                target=target,
                status="failed",
                decision_type=rendered.decision_type,
                severity=severity_name,
                tier_label=rendered.tier_label,
                attempted_at=now,
                completed_at=now,
                payload_ref=None,
                error_message=f"unknown_sink:{target}",
            )
            try:
                self._repo.create(event)
            except Exception as exc:
                logger.error("dispatch_audit_create_failed", exc_info=exc)
            return

        try:
            if self._repo.exists_non_failed(alert_decision_id, target):
                return
        except Exception as exc:
            logger.error("dispatcher_idempotency_check_failed", exc_info=exc)
            return

        sink = self._sinks[target]
        attempted_at = _utc_now()
        event_id = uuid4().hex
        pending = DispatchEvent(
            id=event_id,
            alert_decision_id=alert_decision_id,
            dispatch_run_id=self._dispatch_run_id,
            target=target,
            status="pending",
            decision_type=rendered.decision_type,
            severity=severity_name,
            tier_label=rendered.tier_label,
            attempted_at=attempted_at,
            completed_at=None,
            payload_ref=None,
            error_message=None,
        )
        try:
            self._repo.create(pending)
        except Exception as exc:
            logger.error("dispatch_audit_create_failed", exc_info=exc)
            return

        result = self._invoke_sink(
            sink, rendered, event_id, attempted_at
        )
        completed_at = _utc_now()

        if result.success:
            self._safe_update(
                event_id,
                status="sent",
                completed_at=completed_at,
                payload_ref=result.payload_ref,
                error_message=None,
            )
        else:
            self._safe_update(
                event_id,
                status="failed",
                completed_at=completed_at,
                payload_ref=None,
                error_message=result.error_message,
            )

    def _invoke_sink(
        self,
        sink: Sink,
        rendered: RenderedAlert,
        event_id: str,
        attempted_at: datetime,
    ) -> DeliveryResult:
        context = DeliveryContext(
            dispatch_event_id=event_id,
            dispatch_run_id=self._dispatch_run_id,
            attempted_at=attempted_at,
        )
        try:
            return sink.deliver(rendered, context)
        except Exception as exc:
            return DeliveryResult(
                success=False,
                payload_ref=None,
                error_message=f"{type(exc).__name__}: {exc}",
            )

    def _safe_update(
        self,
        event_id: str,
        *,
        status: str,
        completed_at: datetime,
        payload_ref: Optional[str],
        error_message: Optional[str],
    ) -> None:
        try:
            self._repo.update_status(
                event_id,
                status,
                completed_at,
                payload_ref,
                error_message,
            )
        except Exception as exc:
            logger.error("dispatch_audit_update_failed", exc_info=exc)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)

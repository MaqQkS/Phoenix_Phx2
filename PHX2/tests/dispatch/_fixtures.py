"""Shared fixtures for Stage 8B dispatch tests.

Pure factories — no I/O, no clock reads, no DB. Tests requiring a DB build one
in-memory via the helpers in ``test_engine_integration.py``.
"""

from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from PHX2.renderers.rendered_alert import (
    DRY_RUN_BANNER,
    RenderedAlert,
    Severity,
)


ATTEMPTED_AT = datetime(2026, 5, 9, 14, 33, 4, tzinfo=timezone.utc)
TOKEN_ADDRESS = "7xKp9aBcDeFgHiJkLmNoPqRsTuVwXyZ1234567890mLq"


def make_rendered_alert(
    *,
    decision_type: str = "would_alert",
    severity: Severity = Severity.CLEAN,
    tier_label: Optional[str] = "T2",
    headline: str = "WOULD_ALERT — T2",
    address_short: str = "7xKp...mLq",
    address: str = TOKEN_ADDRESS,
    alert_decision_id: Optional[int] = 1,
) -> RenderedAlert:
    return RenderedAlert(
        banner=DRY_RUN_BANNER,
        severity=severity,
        decision_type=decision_type,
        tier_label=tier_label,
        headline=headline,
        alert_decision_id=alert_decision_id,
        token_section={
            "symbol": "BONKINU",
            "address": address,
            "address_short": address_short,
            "tier": tier_label or "unknown",
            "primary_reason": "would_alert",
        },
        market_section={
            "current_mc": "$847k",
            "migration_mc": "$312k",
            "ath_mc": "$2.84M",
            "drawdown": "70.2%",
            "pump_multiple": "2.71x",
            "price_age": "2m22s",
            "calculation_basis": "mcap",
        },
        ath_section={
            "status": "confirmed",
            "confidence": "high",
            "source": "pumpswap_event",
            "ath_event_time": "2026-05-09T14:18:42+00:00",
        },
        field_section={
            "liquidity_usd": "$125k",
            "lp_floor_label": "ok",
            "fee_gate_label": "open",
            "ante_label_5m": "elevated",
            "ghost_label": "alive",
            "holder_label": "diverse",
        },
        clock_section={
            "token_age": "1h47m",
            "time_since_migration": "1h32m",
            "time_since_ath": "14m22s",
        },
        missing_section=[],
        footer={
            "policy_version": "alert_policy_v0_observe_only",
            "evaluated_at": "2026-05-09T14:33:04+00:00",
        },
    )


def make_rendered_skip(
    *,
    severity: Severity = Severity.INFO,
    alert_decision_id: Optional[int] = 1,
    missing_section: Optional[list] = None,
) -> RenderedAlert:
    return RenderedAlert(
        banner=DRY_RUN_BANNER,
        severity=severity,
        decision_type="skip",
        tier_label=None,
        headline="SKIP — price_stale",
        alert_decision_id=alert_decision_id,
        token_section={
            "symbol": "BONKINU",
            "address": TOKEN_ADDRESS,
            "address_short": "7xKp...mLq",
            "tier": "unknown",
            "primary_reason": "price_stale",
        },
        market_section={},
        ath_section={},
        field_section={},
        clock_section={},
        missing_section=["price_stale"] if missing_section is None else missing_section,
        footer={
            "policy_version": "alert_policy_v0_observe_only",
            "evaluated_at": "2026-05-09T14:33:04+00:00",
        },
    )


def make_rendered_block(
    *,
    alert_decision_id: Optional[int] = 1,
    missing_section: Optional[list] = None,
) -> RenderedAlert:
    return RenderedAlert(
        banner=DRY_RUN_BANNER,
        severity=Severity.INFO,
        decision_type="block",
        tier_label=None,
        headline="BLOCK — policy_disabled",
        alert_decision_id=alert_decision_id,
        token_section={
            "symbol": "BONKINU",
            "address": TOKEN_ADDRESS,
            "address_short": "7xKp...mLq",
            "tier": "unknown",
            "primary_reason": "policy_disabled",
        },
        market_section={},
        ath_section={},
        field_section={},
        clock_section={},
        missing_section=[] if missing_section is None else missing_section,
        footer={
            "policy_version": "alert_policy_v0_observe_only",
            "evaluated_at": "2026-05-09T14:33:04+00:00",
        },
    )


def make_rendered_error(
    *,
    alert_decision_id: Optional[int] = 1,
    missing_section: Optional[list] = None,
) -> RenderedAlert:
    return RenderedAlert(
        banner=DRY_RUN_BANNER,
        severity=Severity.ERROR,
        decision_type="error",
        tier_label=None,
        headline="ERROR — error",
        alert_decision_id=alert_decision_id,
        token_section={
            "symbol": "unknown",
            "address": TOKEN_ADDRESS,
            "address_short": "7xKp...mLq",
            "tier": "unknown",
            "primary_reason": "error",
        },
        market_section={},
        ath_section={},
        field_section={},
        clock_section={},
        missing_section=["error"] if missing_section is None else missing_section,
        footer={
            "policy_version": "alert_policy_v0_observe_only",
            "evaluated_at": "2026-05-09T14:33:04+00:00",
        },
    )


class FakeRepository:
    """In-memory replacement for DispatchEventRepository.

    Records every call so tests can assert ordering and content. Behaves like
    the real repository for the methods the dispatcher uses.
    """

    def __init__(self) -> None:
        self.events: dict = {}
        self.calls: list = []

    def create(self, event) -> None:
        self.calls.append(("create", event))
        self.events[event.id] = event

    def get_by_id(self, event_id: str):
        return self.events.get(event_id)

    def update_status(
        self,
        event_id: str,
        status: str,
        completed_at,
        payload_ref,
        error_message,
    ) -> None:
        self.calls.append(
            (
                "update_status",
                event_id,
                status,
                completed_at,
                payload_ref,
                error_message,
            )
        )
        prior = self.events[event_id]
        # Replicate frozen-dataclass semantics by constructing a new instance.
        from PHX2.models.dispatch_event import DispatchEvent

        self.events[event_id] = DispatchEvent(
            id=prior.id,
            alert_decision_id=prior.alert_decision_id,
            dispatch_run_id=prior.dispatch_run_id,
            target=prior.target,
            status=status,
            decision_type=prior.decision_type,
            severity=prior.severity,
            tier_label=prior.tier_label,
            attempted_at=prior.attempted_at,
            completed_at=completed_at,
            payload_ref=payload_ref,
            error_message=error_message,
        )

    def exists_non_failed(self, alert_decision_id: int, target: str) -> bool:
        for event in self.events.values():
            if (
                event.alert_decision_id == alert_decision_id
                and event.target == target
                and event.status != "failed"
            ):
                return True
        return False

    def list_by_decision(self, alert_decision_id: int):
        return [
            event
            for event in self.events.values()
            if event.alert_decision_id == alert_decision_id
        ]


class RecordingSink:
    """Sink that records calls and returns a configurable result."""

    def __init__(
        self,
        name: str,
        result=None,
        raise_exc: Optional[Exception] = None,
    ) -> None:
        self.name = name
        self._result = result
        self._raise = raise_exc
        self.calls: list = []

    def deliver(self, rendered, context):
        self.calls.append((rendered, context))
        if self._raise is not None:
            raise self._raise
        if self._result is not None:
            return self._result
        from PHX2.dispatch.sinks.base import DeliveryResult

        return DeliveryResult(success=True, payload_ref=None, error_message=None)

"""Stage 21 transport_contracts tests."""

from __future__ import annotations

import pytest

from PHX2.stage21.errors import Stage21TransportContractError
from PHX2.stage21.transport_contracts import (
    Stage21Transport,
    TransportPayload,
    TransportResult,
    assert_transport_dispatch_safety,
)


class _FakeTransport:
    """In-memory fake transport. Satisfies ``Stage21Transport``."""

    def __init__(self) -> None:
        self.recorded_sends: list[TransportPayload] = []

    def send(self, payload: TransportPayload) -> TransportResult:
        allowed, reason = assert_transport_dispatch_safety(payload)
        if not allowed:
            return TransportResult(
                dispatched=False,
                rejection_reason=reason,
                recipient=payload.recipient,
            )
        self.recorded_sends.append(payload)
        return TransportResult(
            dispatched=True,
            rejection_reason="",
            recipient=payload.recipient,
        )


def _safe_payload() -> TransportPayload:
    return TransportPayload(
        recipient="alice",
        body_text=(
            "PHX2 PRIVATE PREVIEW -- OPERATOR ONLY -- "
            "DO NOT FORWARD AS PUBLIC SIGNAL"
        ),
        private_preview_marker_present=True,
        safe_for_public_dispatch=False,
    )


def test_fake_transport_satisfies_protocol_without_network():
    fake = _FakeTransport()
    typed: Stage21Transport = fake
    result = typed.send(_safe_payload())
    assert result.dispatched is True
    assert result.recipient == "alice"
    assert result.rejection_reason == ""
    assert len(fake.recorded_sends) == 1


def test_assert_transport_dispatch_safety_passes_safe_payload():
    allowed, reason = assert_transport_dispatch_safety(_safe_payload())
    assert allowed is True
    assert reason == ""


def test_dispatch_safety_rejects_when_safe_for_public_dispatch_true():
    payload = _safe_payload()._replace(safe_for_public_dispatch=True)
    allowed, reason = assert_transport_dispatch_safety(payload)
    assert allowed is False
    assert reason == "safe_for_public_dispatch_true"


def test_dispatch_safety_rejects_when_marker_missing():
    payload = _safe_payload()._replace(
        private_preview_marker_present=False,
    )
    allowed, reason = assert_transport_dispatch_safety(payload)
    assert allowed is False
    assert reason == "private_preview_marker_missing"


def test_dispatch_safety_raises_on_wrong_input_type():
    with pytest.raises(Stage21TransportContractError) as excinfo:
        assert_transport_dispatch_safety("bad")  # type: ignore[arg-type]
    assert excinfo.value.code == "E2130"


def test_fake_transport_does_not_record_rejected_send():
    fake = _FakeTransport()
    unsafe = _safe_payload()._replace(safe_for_public_dispatch=True)
    result = fake.send(unsafe)
    assert result.dispatched is False
    assert result.rejection_reason == "safe_for_public_dispatch_true"
    assert fake.recorded_sends == []


def test_transport_payload_is_namedtuple_with_locked_fields():
    assert TransportPayload._fields == (
        "recipient",
        "body_text",
        "private_preview_marker_present",
        "safe_for_public_dispatch",
    )


def test_transport_result_is_namedtuple_with_locked_fields():
    assert TransportResult._fields == (
        "dispatched",
        "rejection_reason",
        "recipient",
    )

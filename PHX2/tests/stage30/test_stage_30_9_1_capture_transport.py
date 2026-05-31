"""Stage 30.9.1 capture transport tests.

Proves the thin innermost capture transport forwards verbatim to an
injected inner transport, returns the inner result unchanged, and records
a sanitized in-memory projection of each send (an immutable body snapshot,
the safe webhook identity, the sanitized inner status, and the optional
payload-metadata ids) in deterministic send order. Uses a fake inner
transport only; no live call, no Discord, no filesystem, no env.
"""

from __future__ import annotations

import pytest

from PHX2.stage30.stage30_9_artifact_bridge_models import (
    BRIDGE_STATUS_CAPTURED,
    SANITIZED_TRANSPORT_STATUS_SENT_OK,
    SANITIZED_TRANSPORT_STATUS_UNKNOWN,
    Stage30_9CaptureRecord,
)
from PHX2.stage30.stage30_9_capture_transport import (
    Stage30_9CaptureTransport,
    Stage30_9CaptureTransportError,
)


# ---------------------------------------------------------------------------
# Fakes (offline only)
# ---------------------------------------------------------------------------


class _FakeResult:
    """A minimal duck-typed transport result carrying only a closed-set
    ``transport_status`` token (mirrors the Stage 28.4 result shape).
    """

    def __init__(self, transport_status: str) -> None:
        self.transport_status = transport_status
        # A deliberately sensitive-looking attribute the capture transport
        # must NEVER read / copy onto a capture record.
        self.secret_destination = "h" + "ttps://example.invalid/secret"


class _FakeInnerTransport:
    """A deterministic fake inner transport. Records each call (the exact
    webhook identity + payload object) and returns a scripted result.
    """

    def __init__(self, scripted_statuses) -> None:
        self._statuses = list(scripted_statuses)
        self.calls = []

    def send_one_audited_post(self, *, webhook_identity, payload):
        index = len(self.calls)
        self.calls.append(
            {"webhook_identity": webhook_identity, "payload": payload}
        )
        status = (
            self._statuses[index]
            if index < len(self._statuses)
            else "SENT_OK"
        )
        return _FakeResult(status)


class _RaisingInnerTransport:
    """A fake inner transport that raises on send."""

    def send_one_audited_post(self, *, webhook_identity, payload):
        raise RuntimeError("inner transport boom")


_PRIVATE = "PRIVATE_OPERATOR_WEBHOOK"


# ---------------------------------------------------------------------------
# 1. Construction
# ---------------------------------------------------------------------------


def test_construction_rejects_inner_without_send_method() -> None:
    for bad in (object(), None, 123, "not-a-transport"):
        with pytest.raises(Stage30_9CaptureTransportError):
            Stage30_9CaptureTransport(inner_transport=bad)


def test_construction_accepts_duck_typed_inner() -> None:
    transport = Stage30_9CaptureTransport(
        inner_transport=_FakeInnerTransport(["SENT_OK"])
    )
    assert transport.capture_count == 0
    assert transport.records == ()


# ---------------------------------------------------------------------------
# 2. Forwards verbatim + returns the inner result verbatim
# ---------------------------------------------------------------------------


def test_forwards_payload_and_identity_verbatim() -> None:
    inner = _FakeInnerTransport(["SENT_OK"])
    transport = Stage30_9CaptureTransport(inner_transport=inner)
    payload = {"content": "compact body text"}

    result = transport.send_one_audited_post(
        webhook_identity=_PRIVATE, payload=payload
    )

    # Inner called exactly once.
    assert len(inner.calls) == 1
    # The EXACT payload object + identity were forwarded (object identity).
    assert inner.calls[0]["payload"] is payload
    assert inner.calls[0]["webhook_identity"] == _PRIVATE
    # The inner result is returned VERBATIM (object identity).
    assert isinstance(result, _FakeResult)
    assert result.transport_status == "SENT_OK"


def test_returns_inner_result_object_identity() -> None:
    sentinel = _FakeResult("SENT_OK")

    class _IdentityInner:
        def send_one_audited_post(self, *, webhook_identity, payload):
            return sentinel

    transport = Stage30_9CaptureTransport(inner_transport=_IdentityInner())
    out = transport.send_one_audited_post(
        webhook_identity=_PRIVATE, payload={"content": "x"}
    )
    assert out is sentinel


# ---------------------------------------------------------------------------
# 3. Records the sanitized projection
# ---------------------------------------------------------------------------


def test_records_exact_body_keys_identity_and_status() -> None:
    inner = _FakeInnerTransport(["SENT_OK"])
    transport = Stage30_9CaptureTransport(inner_transport=inner)
    transport.send_one_audited_post(
        webhook_identity=_PRIVATE,
        payload={"content": "exact compact body", "username": "x"},
    )
    (record,) = transport.records
    assert isinstance(record, Stage30_9CaptureRecord)
    assert record.capture_index == 0
    assert record.webhook_identity == _PRIVATE
    assert record.payload_body_text == "exact compact body"
    assert record.payload_keys == ("content", "username")
    assert record.sanitized_transport_status == "SENT_OK"


def test_records_payload_metadata_ids_when_present() -> None:
    inner = _FakeInnerTransport(["SENT_OK"])
    transport = Stage30_9CaptureTransport(inner_transport=inner)
    transport.send_one_audited_post(
        webhook_identity=_PRIVATE,
        payload={
            "content": "body",
            "candidate_id": "cand-1",
            "ping_id": "ping-1",
        },
    )
    (record,) = transport.records
    assert record.candidate_id == "cand-1"
    assert record.ping_id == "ping-1"


def test_records_absent_metadata_ids_as_none() -> None:
    inner = _FakeInnerTransport(["SENT_OK"])
    transport = Stage30_9CaptureTransport(inner_transport=inner)
    transport.send_one_audited_post(
        webhook_identity=_PRIVATE, payload={"content": "body"}
    )
    (record,) = transport.records
    assert record.candidate_id is None
    assert record.ping_id is None


def test_capture_record_does_not_carry_sensitive_inner_attribute() -> None:
    # The capture transport reads ONLY ``transport_status`` off the result;
    # the result's sensitive-looking attribute is never copied anywhere.
    inner = _FakeInnerTransport(["SENT_OK"])
    transport = Stage30_9CaptureTransport(inner_transport=inner)
    transport.send_one_audited_post(
        webhook_identity=_PRIVATE, payload={"content": "body"}
    )
    (record,) = transport.records
    assert not hasattr(record, "secret_destination")
    for value in (
        record.payload_body_text,
        record.sanitized_transport_status,
        record.webhook_identity,
    ):
        assert "://" not in (value or "")


# ---------------------------------------------------------------------------
# 4. Body snapshot is immutable to later payload mutation
# ---------------------------------------------------------------------------


def test_later_payload_mutation_does_not_change_capture_record() -> None:
    inner = _FakeInnerTransport(["SENT_OK"])
    transport = Stage30_9CaptureTransport(inner_transport=inner)
    payload = {"content": "original body"}
    transport.send_one_audited_post(
        webhook_identity=_PRIVATE, payload=payload
    )

    # Mutate the caller's payload AFTER the send.
    payload["content"] = "MUTATED"
    payload["extra"] = "added"

    (record,) = transport.records
    # The recorded body is the immutable snapshot taken at send time.
    assert record.payload_body_text == "original body"
    # The recorded keys are the snapshot taken at send time.
    assert record.payload_keys == ("content",)


# ---------------------------------------------------------------------------
# 5. Deterministic ordering + multiple sends + failed status captured
# ---------------------------------------------------------------------------


def test_deterministic_ordering_and_failed_status_captured() -> None:
    inner = _FakeInnerTransport(["SENT_OK", "RATE_LIMITED", "SERVER_ERROR"])
    transport = Stage30_9CaptureTransport(inner_transport=inner)
    for i in range(3):
        transport.send_one_audited_post(
            webhook_identity=_PRIVATE, payload={"content": f"body-{i}"}
        )

    records = transport.records
    assert transport.capture_count == 3
    # Capture indices are 0, 1, 2 in send order.
    assert [r.capture_index for r in records] == [0, 1, 2]
    assert [r.payload_body_text for r in records] == [
        "body-0",
        "body-1",
        "body-2",
    ]
    # The failed inner statuses are captured verbatim too.
    assert [r.sanitized_transport_status for r in records] == [
        "SENT_OK",
        "RATE_LIMITED",
        "SERVER_ERROR",
    ]


# ---------------------------------------------------------------------------
# 6. Batch summary
# ---------------------------------------------------------------------------


def test_batch_summary_reports_captured_status_and_records() -> None:
    inner = _FakeInnerTransport(["SENT_OK", "SENT_OK"])
    transport = Stage30_9CaptureTransport(inner_transport=inner)
    transport.send_one_audited_post(
        webhook_identity=_PRIVATE, payload={"content": "a"}
    )
    transport.send_one_audited_post(
        webhook_identity=_PRIVATE, payload={"content": "b"}
    )
    summary = transport.batch_summary()
    assert summary.status == BRIDGE_STATUS_CAPTURED
    assert summary.capture_count == 2
    assert summary.records == transport.records


# ---------------------------------------------------------------------------
# 7. Inner-transport exception propagates; the pre-send record survives
# ---------------------------------------------------------------------------


def test_inner_exception_propagates_and_records_pre_send() -> None:
    transport = Stage30_9CaptureTransport(
        inner_transport=_RaisingInnerTransport()
    )
    with pytest.raises(RuntimeError):
        transport.send_one_audited_post(
            webhook_identity=_PRIVATE, payload={"content": "body"}
        )
    # The pre-send capture record was recorded (the trail reflects the
    # attempt); its sanitized status stays None because no result returned.
    (record,) = transport.records
    assert record.capture_index == 0
    assert record.payload_body_text == "body"
    assert record.sanitized_transport_status is None


# ---------------------------------------------------------------------------
# 7b. Transport status is normalized into the closed sanitized set
# ---------------------------------------------------------------------------


def test_known_status_preserved() -> None:
    inner = _FakeInnerTransport(["SENT_OK"])
    transport = Stage30_9CaptureTransport(inner_transport=inner)
    transport.send_one_audited_post(
        webhook_identity=_PRIVATE, payload={"content": "a"}
    )
    assert transport.records[0].sanitized_transport_status == (
        SANITIZED_TRANSPORT_STATUS_SENT_OK
    )


def test_unknown_status_normalized_to_unknown() -> None:
    inner = _FakeInnerTransport(["TOTALLY_WEIRD_STATUS"])
    transport = Stage30_9CaptureTransport(inner_transport=inner)
    result = transport.send_one_audited_post(
        webhook_identity=_PRIVATE, payload={"content": "a"}
    )
    # The capture record stores the closed-set fallback...
    assert transport.records[0].sanitized_transport_status == (
        SANITIZED_TRANSPORT_STATUS_UNKNOWN
    )
    # ...but the inner result is still returned verbatim (raw status intact).
    assert result.transport_status == "TOTALLY_WEIRD_STATUS"


def test_blank_status_normalized_to_unknown() -> None:
    inner = _FakeInnerTransport([""])
    transport = Stage30_9CaptureTransport(inner_transport=inner)
    transport.send_one_audited_post(
        webhook_identity=_PRIVATE, payload={"content": "a"}
    )
    assert transport.records[0].sanitized_transport_status == (
        SANITIZED_TRANSPORT_STATUS_UNKNOWN
    )


def test_missing_status_attribute_normalized_to_unknown() -> None:
    sentinel = object()  # a result object with NO transport_status attribute

    class _NoStatusInner:
        def send_one_audited_post(self, *, webhook_identity, payload):
            return sentinel

    transport = Stage30_9CaptureTransport(inner_transport=_NoStatusInner())
    result = transport.send_one_audited_post(
        webhook_identity=_PRIVATE, payload={"content": "a"}
    )
    assert transport.records[0].sanitized_transport_status == (
        SANITIZED_TRANSPORT_STATUS_UNKNOWN
    )
    # The inner result is still returned verbatim (object identity).
    assert result is sentinel


# ---------------------------------------------------------------------------
# 8. Non-mapping payload is tolerated (no body / keys captured)
# ---------------------------------------------------------------------------


def test_non_mapping_payload_records_no_body() -> None:
    inner = _FakeInnerTransport(["SENT_OK"])
    transport = Stage30_9CaptureTransport(inner_transport=inner)
    transport.send_one_audited_post(
        webhook_identity=_PRIVATE, payload="not-a-mapping"
    )
    (record,) = transport.records
    assert record.payload_body_text is None
    assert record.payload_keys == ()
    # Still forwarded verbatim.
    assert inner.calls[0]["payload"] == "not-a-mapping"

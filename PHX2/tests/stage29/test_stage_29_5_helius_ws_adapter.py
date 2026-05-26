"""Stage 29.5 Helius WebSocket migration evidence adapter tests.

Offline tests only. The adapter is exercised exclusively against
a deterministic fake WebSocket transport. No real socket, no
real network, no third-party WebSocket library.

Pins:

  * The adapter consumes an injected
    :class:`Stage29_5WebSocketTransport` and never opens its own
    socket.
  * A well-formed Stage 29.5 migration message yields
    ``migration_status=PRESENT`` +
    ``migration_source=HELIUS_WS``.
  * A missing axis in an otherwise well-formed message yields
    ``migration_status=INVALID`` with the populated axes
    preserved and the missing axes set to ``None``.
  * Non-JSON / non-object / unsupported-kind payloads raise or
    are silently skipped per the documented contract.
  * The adapter NEVER emits ``migration_source=SYNTHETIC_TEST_ONLY``.
  * The adapter NEVER fabricates an axis.
  * The bounded ``max_messages_to_read`` budget caps the loop.
  * The injected transport is the sole source of bytes.
"""

from __future__ import annotations

import json
from typing import List, Optional

import pytest

from PHX2.stage29.stage29_5_helius_ws_adapter import (
    STAGE29_5_HELIUS_WS_DEFAULT_MAX_MESSAGES_TO_READ,
    STAGE29_5_HELIUS_WS_HARD_MAX_MESSAGES_TO_READ,
    STAGE29_5_HELIUS_WS_MIGRATION_KIND,
    Stage29_5HeliusWebSocketAdapter,
    Stage29_5WebSocketTransport,
    parse_helius_ws_migration_message,
)
from PHX2.stage29.stage29_5_migration_models import (
    MIGRATION_SOURCE_HELIUS_WS,
    MIGRATION_SOURCE_SYNTHETIC_TEST_ONLY,
    MIGRATION_SOURCE_UNKNOWN_STAGE29_5,
    MIGRATION_STATUS_INVALID,
    MIGRATION_STATUS_MISSING,
    MIGRATION_STATUS_PRESENT,
    REFUSAL_REASON_BUDGET_EXCEEDED,
    REFUSAL_REASON_MALFORMED_PAYLOAD,
    REFUSAL_REASON_UNSUPPORTED_KIND,
    Stage29_5MigrationEvidenceError,
)


# ---------------------------------------------------------------------------
# Fake fixtures
# ---------------------------------------------------------------------------


_SAFE_MINT_A: str = "M" * 44
_SAFE_POOL_A: str = "P" * 44
_SAFE_POOL_PROGRAM: str = "G" * 44
_SAFE_QUOTE: str = "Q" * 44
_SAFE_TIMESTAMP_A: str = "2026-05-25T00:00:00+00:00"
_SAFE_OBSERVED_AT: str = "2026-05-25T02:00:00+00:00"


def _well_formed_message() -> bytes:
    return json.dumps(
        {
            "kind": STAGE29_5_HELIUS_WS_MIGRATION_KIND,
            "base_mint": _SAFE_MINT_A,
            "pool_account": _SAFE_POOL_A,
            "pool_program_id": _SAFE_POOL_PROGRAM,
            "quote_mint": _SAFE_QUOTE,
            "migration_timestamp_utc": _SAFE_TIMESTAMP_A,
            "migration_slot": 123456,
            "migration_signature": "synth-sig-A",
            "source_event_ref": "synth-ref-A",
        }
    ).encode("utf-8")


class _FakeWebSocketTransport(Stage29_5WebSocketTransport):
    """In-memory fake. Yields preset bytes messages, then None."""

    def __init__(
        self, messages: List[Optional[bytes]]
    ) -> None:
        self._messages = list(messages)
        self.close_called: int = 0
        self.recv_called: int = 0

    def recv_one_message(
        self, timeout_seconds: float
    ) -> Optional[bytes]:
        self.recv_called += 1
        if not self._messages:
            return None
        head = self._messages.pop(0)
        return head

    def close(self) -> None:
        self.close_called += 1


def _fixed_clock() -> str:
    return _SAFE_OBSERVED_AT


# ---------------------------------------------------------------------------
# parse_helius_ws_migration_message
# ---------------------------------------------------------------------------


def test_parse_well_formed_message_yields_present_helius_ws():
    record = parse_helius_ws_migration_message(
        _well_formed_message(), _SAFE_OBSERVED_AT
    )
    assert record.migration_status == MIGRATION_STATUS_PRESENT
    assert (
        record.migration_source == MIGRATION_SOURCE_HELIUS_WS
    )
    assert record.base_mint == _SAFE_MINT_A
    assert record.pool_account == _SAFE_POOL_A
    assert record.pool_program_id == _SAFE_POOL_PROGRAM
    assert record.quote_mint == _SAFE_QUOTE
    assert (
        record.migration_timestamp_utc == _SAFE_TIMESTAMP_A
    )
    assert record.migration_slot == 123456
    assert record.migration_signature == "synth-sig-A"
    assert record.observed_at_utc == _SAFE_OBSERVED_AT


def test_parse_accepts_str_body():
    body = _well_formed_message().decode("utf-8")
    record = parse_helius_ws_migration_message(
        body, _SAFE_OBSERVED_AT
    )
    assert record.migration_status == MIGRATION_STATUS_PRESENT


def test_parse_message_missing_axis_yields_invalid():
    payload = {
        "kind": STAGE29_5_HELIUS_WS_MIGRATION_KIND,
        "base_mint": _SAFE_MINT_A,
        # pool_account intentionally omitted
        "pool_program_id": _SAFE_POOL_PROGRAM,
        "quote_mint": _SAFE_QUOTE,
        "migration_timestamp_utc": _SAFE_TIMESTAMP_A,
        "migration_slot": 1,
    }
    record = parse_helius_ws_migration_message(
        json.dumps(payload).encode("utf-8"),
        _SAFE_OBSERVED_AT,
    )
    assert record.migration_status == MIGRATION_STATUS_INVALID
    assert (
        record.migration_source == MIGRATION_SOURCE_HELIUS_WS
    )
    assert record.base_mint == _SAFE_MINT_A
    assert record.pool_account is None
    assert record.pool_program_id == _SAFE_POOL_PROGRAM


def test_parse_message_missing_timestamp_yields_invalid():
    payload = {
        "kind": STAGE29_5_HELIUS_WS_MIGRATION_KIND,
        "base_mint": _SAFE_MINT_A,
        "pool_account": _SAFE_POOL_A,
        "pool_program_id": _SAFE_POOL_PROGRAM,
        "quote_mint": _SAFE_QUOTE,
        # migration_timestamp_utc intentionally omitted
    }
    record = parse_helius_ws_migration_message(
        json.dumps(payload).encode("utf-8"),
        _SAFE_OBSERVED_AT,
    )
    assert record.migration_status == MIGRATION_STATUS_INVALID


def test_parse_message_unsafe_mint_shape_silently_dropped():
    payload = {
        "kind": STAGE29_5_HELIUS_WS_MIGRATION_KIND,
        "base_mint": "too_short",
        "pool_account": _SAFE_POOL_A,
        "pool_program_id": _SAFE_POOL_PROGRAM,
        "quote_mint": _SAFE_QUOTE,
        "migration_timestamp_utc": _SAFE_TIMESTAMP_A,
        "migration_slot": 1,
    }
    record = parse_helius_ws_migration_message(
        json.dumps(payload).encode("utf-8"),
        _SAFE_OBSERVED_AT,
    )
    assert record.migration_status == MIGRATION_STATUS_INVALID
    assert record.base_mint is None
    assert record.pool_account == _SAFE_POOL_A


def test_parse_message_local_offset_timestamp_dropped():
    payload = {
        "kind": STAGE29_5_HELIUS_WS_MIGRATION_KIND,
        "base_mint": _SAFE_MINT_A,
        "pool_account": _SAFE_POOL_A,
        "pool_program_id": _SAFE_POOL_PROGRAM,
        "quote_mint": _SAFE_QUOTE,
        "migration_timestamp_utc": "2026-05-25T00:00:00-05:00",
    }
    record = parse_helius_ws_migration_message(
        json.dumps(payload).encode("utf-8"),
        _SAFE_OBSERVED_AT,
    )
    assert record.migration_status == MIGRATION_STATUS_INVALID
    assert record.migration_timestamp_utc is None


def test_parse_non_object_body_raises_malformed():
    with pytest.raises(
        Stage29_5MigrationEvidenceError
    ) as excinfo:
        parse_helius_ws_migration_message(
            b'[1, 2, 3]', _SAFE_OBSERVED_AT
        )
    assert (
        excinfo.value.refusal_reason
        == REFUSAL_REASON_MALFORMED_PAYLOAD
    )


def test_parse_invalid_json_raises_malformed():
    with pytest.raises(
        Stage29_5MigrationEvidenceError
    ) as excinfo:
        parse_helius_ws_migration_message(
            b'{not-json', _SAFE_OBSERVED_AT
        )
    assert (
        excinfo.value.refusal_reason
        == REFUSAL_REASON_MALFORMED_PAYLOAD
    )


def test_parse_non_bytes_non_str_raises_malformed():
    with pytest.raises(
        Stage29_5MigrationEvidenceError
    ) as excinfo:
        parse_helius_ws_migration_message(
            12345, _SAFE_OBSERVED_AT  # type: ignore[arg-type]
        )
    assert (
        excinfo.value.refusal_reason
        == REFUSAL_REASON_MALFORMED_PAYLOAD
    )


def test_parse_unsupported_kind_raises():
    payload = json.dumps(
        {"kind": "NOT_A_MIGRATION"}
    ).encode("utf-8")
    with pytest.raises(
        Stage29_5MigrationEvidenceError
    ) as excinfo:
        parse_helius_ws_migration_message(
            payload, _SAFE_OBSERVED_AT
        )
    assert (
        excinfo.value.refusal_reason
        == REFUSAL_REASON_UNSUPPORTED_KIND
    )


def test_parse_rejects_unsafe_observed_at_utc():
    with pytest.raises(
        Stage29_5MigrationEvidenceError
    ) as excinfo:
        parse_helius_ws_migration_message(
            _well_formed_message(), "2026-05-25"
        )
    assert (
        excinfo.value.refusal_reason
        == REFUSAL_REASON_MALFORMED_PAYLOAD
    )


def test_parse_never_emits_synthetic_source():
    record = parse_helius_ws_migration_message(
        _well_formed_message(), _SAFE_OBSERVED_AT
    )
    assert (
        record.migration_source
        != MIGRATION_SOURCE_SYNTHETIC_TEST_ONLY
    )


# ---------------------------------------------------------------------------
# Stage29_5HeliusWebSocketAdapter
# ---------------------------------------------------------------------------


def test_adapter_reads_single_well_formed_message():
    transport = _FakeWebSocketTransport(
        [_well_formed_message()]
    )
    adapter = Stage29_5HeliusWebSocketAdapter(
        transport=transport,
        clock=_fixed_clock,
    )
    records = adapter.read_migration_evidence_batch()
    assert len(records) == 1
    assert (
        records[0].migration_status == MIGRATION_STATUS_PRESENT
    )
    assert (
        records[0].migration_source
        == MIGRATION_SOURCE_HELIUS_WS
    )


def test_adapter_stops_on_transport_timeout():
    transport = _FakeWebSocketTransport(
        [_well_formed_message(), None, _well_formed_message()]
    )
    adapter = Stage29_5HeliusWebSocketAdapter(
        transport=transport,
        clock=_fixed_clock,
    )
    records = adapter.read_migration_evidence_batch()
    # Stops at the first None — the third (well-formed) message
    # must NOT be reached.
    assert len(records) == 1


def test_adapter_skips_unsupported_kind_messages():
    transport = _FakeWebSocketTransport(
        [
            json.dumps(
                {"kind": "NOT_A_MIGRATION"}
            ).encode("utf-8"),
            _well_formed_message(),
        ]
    )
    adapter = Stage29_5HeliusWebSocketAdapter(
        transport=transport,
        clock=_fixed_clock,
    )
    records = adapter.read_migration_evidence_batch()
    assert len(records) == 1
    assert (
        records[0].migration_status == MIGRATION_STATUS_PRESENT
    )


def test_adapter_raises_on_malformed_payload():
    transport = _FakeWebSocketTransport(
        [b'{not-json']
    )
    adapter = Stage29_5HeliusWebSocketAdapter(
        transport=transport,
        clock=_fixed_clock,
    )
    with pytest.raises(
        Stage29_5MigrationEvidenceError
    ) as excinfo:
        adapter.read_migration_evidence_batch()
    assert (
        excinfo.value.refusal_reason
        == REFUSAL_REASON_MALFORMED_PAYLOAD
    )


def test_adapter_caps_messages_at_max():
    payloads = [_well_formed_message()] * 5
    transport = _FakeWebSocketTransport(payloads)
    adapter = Stage29_5HeliusWebSocketAdapter(
        transport=transport,
        clock=_fixed_clock,
        max_messages_to_read=2,
    )
    records = adapter.read_migration_evidence_batch()
    assert len(records) == 2
    assert transport.recv_called == 2


def test_adapter_emits_no_records_when_transport_empty():
    transport = _FakeWebSocketTransport([])
    adapter = Stage29_5HeliusWebSocketAdapter(
        transport=transport,
        clock=_fixed_clock,
    )
    records = adapter.read_migration_evidence_batch()
    assert records == ()


def test_adapter_include_missing_when_empty_emits_missing_record():
    transport = _FakeWebSocketTransport([])
    adapter = Stage29_5HeliusWebSocketAdapter(
        transport=transport,
        clock=_fixed_clock,
        include_missing_when_empty=True,
    )
    records = adapter.read_migration_evidence_batch()
    assert len(records) == 1
    assert (
        records[0].migration_status == MIGRATION_STATUS_MISSING
    )
    assert (
        records[0].migration_source
        == MIGRATION_SOURCE_UNKNOWN_STAGE29_5
    )


def test_adapter_rejects_zero_budget():
    transport = _FakeWebSocketTransport([])
    with pytest.raises(
        Stage29_5MigrationEvidenceError
    ) as excinfo:
        Stage29_5HeliusWebSocketAdapter(
            transport=transport,
            clock=_fixed_clock,
            max_messages_to_read=0,
        )
    assert (
        excinfo.value.refusal_reason
        == REFUSAL_REASON_BUDGET_EXCEEDED
    )


def test_adapter_rejects_over_hard_max_budget():
    transport = _FakeWebSocketTransport([])
    with pytest.raises(
        Stage29_5MigrationEvidenceError
    ) as excinfo:
        Stage29_5HeliusWebSocketAdapter(
            transport=transport,
            clock=_fixed_clock,
            max_messages_to_read=(
                STAGE29_5_HELIUS_WS_HARD_MAX_MESSAGES_TO_READ
                + 1
            ),
        )
    assert (
        excinfo.value.refusal_reason
        == REFUSAL_REASON_BUDGET_EXCEEDED
    )


def test_adapter_rejects_non_callable_clock():
    transport = _FakeWebSocketTransport([])
    with pytest.raises(
        Stage29_5MigrationEvidenceError
    ):
        Stage29_5HeliusWebSocketAdapter(
            transport=transport,
            clock="not-a-function",  # type: ignore[arg-type]
        )


def test_adapter_rejects_non_protocol_transport():
    with pytest.raises(
        Stage29_5MigrationEvidenceError
    ):
        Stage29_5HeliusWebSocketAdapter(
            transport=object(),  # type: ignore[arg-type]
            clock=_fixed_clock,
        )


def test_adapter_rejects_zero_timeout():
    transport = _FakeWebSocketTransport([])
    with pytest.raises(
        Stage29_5MigrationEvidenceError
    ):
        Stage29_5HeliusWebSocketAdapter(
            transport=transport,
            clock=_fixed_clock,
            per_message_timeout_seconds=0.0,
        )


def test_adapter_close_delegates_to_transport():
    transport = _FakeWebSocketTransport([])
    adapter = Stage29_5HeliusWebSocketAdapter(
        transport=transport,
        clock=_fixed_clock,
    )
    adapter.close()
    assert transport.close_called == 1


def test_adapter_never_emits_synthetic_source():
    transport = _FakeWebSocketTransport(
        [_well_formed_message()] * 3
    )
    adapter = Stage29_5HeliusWebSocketAdapter(
        transport=transport,
        clock=_fixed_clock,
    )
    records = adapter.read_migration_evidence_batch()
    for r in records:
        assert (
            r.migration_source
            != MIGRATION_SOURCE_SYNTHETIC_TEST_ONLY
        )


def test_adapter_default_max_matches_module_constant():
    transport = _FakeWebSocketTransport([])
    adapter = Stage29_5HeliusWebSocketAdapter(
        transport=transport,
        clock=_fixed_clock,
    )
    # Read no messages but verify the default cap was set.
    # The cap is verified via the internal attribute since the
    # adapter does not expose a public getter; this is a stable
    # invariant pinned by the spec lock.
    assert (
        adapter._max_messages_to_read
        == STAGE29_5_HELIUS_WS_DEFAULT_MAX_MESSAGES_TO_READ
    )


def test_adapter_clock_must_return_utc_shape():
    transport = _FakeWebSocketTransport(
        [_well_formed_message()]
    )

    def bad_clock() -> str:
        return "2026-05-25"

    adapter = Stage29_5HeliusWebSocketAdapter(
        transport=transport,
        clock=bad_clock,
    )
    with pytest.raises(
        Stage29_5MigrationEvidenceError
    ) as excinfo:
        adapter.read_migration_evidence_batch()
    assert (
        excinfo.value.refusal_reason
        == REFUSAL_REASON_MALFORMED_PAYLOAD
    )


def test_adapter_deterministic_for_same_input():
    payload = _well_formed_message()
    transport_a = _FakeWebSocketTransport([payload])
    transport_b = _FakeWebSocketTransport([payload])
    adapter_a = Stage29_5HeliusWebSocketAdapter(
        transport=transport_a,
        clock=_fixed_clock,
    )
    adapter_b = Stage29_5HeliusWebSocketAdapter(
        transport=transport_b,
        clock=_fixed_clock,
    )
    records_a = adapter_a.read_migration_evidence_batch()
    records_b = adapter_b.read_migration_evidence_batch()
    assert records_a == records_b

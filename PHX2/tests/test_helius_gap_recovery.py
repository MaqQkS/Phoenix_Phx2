"""Deterministic exact-slot Helius HTTP recovery tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from PHX2.free_tier_producer import helius_gap_recovery as recovery
from PHX2.free_tier_producer import helius_source
from PHX2.free_tier_producer import source_continuity as continuity
from PHX2.free_tier_producer.migration_admission import PUMPFUN_PROGRAM_ID
from PHX2.tests.test_helius_developer_shadow_probe import _update_to_helius
from PHX2.tests.test_migration_admission import build_pool_creation_update


def _source_config():
    return helius_source.load_helius_source_config(
        environ={
            "HELIUS_API_KEY": "unit-test-secret",
            "HELIUS_RPC_URL": "https://mainnet.helius-rpc.com/",
            "HELIUS_WS_URL": "wss://mainnet.helius-rpc.com/",
        }
    )


def _entry(*, slot: int, signature_byte: int, failed: bool = False) -> dict:
    update = build_pool_creation_update(failed=failed)
    update.transaction.slot = slot
    update.transaction.transaction.signature = bytes([signature_byte]) * 64
    return _update_to_helius(update)


def _response(request_id: int, rows, token=None) -> dict:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "result": {
            "data": list(rows),
            "paginationToken": token,
        },
    }


class _HttpSequence:
    def __init__(self, *responses) -> None:
        self.responses = list(responses)
        self.requests = []
        self.timeouts = []
        self.byte_ceilings = []

    def __call__(self, request, *, timeout_seconds, max_response_bytes):
        self.requests.append(request)
        self.timeouts.append(timeout_seconds)
        self.byte_ceilings.append(max_response_bytes)
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        if callable(response):
            return response(request)
        return response


def _open_gap(
    *,
    first: int = 100,
    reconnect: int = 102,
    state_path: Path | None = None,
):
    tracker = continuity.SourceContinuityTracker(
        state_path=state_path,
        now_fn=lambda: "2026-07-29T12:00:00Z",
    )
    tracker.note_slot(first, processed=True, durable=True)
    tracker.note_disconnect(
        reason_class=continuity.REASON_PROVIDER_DISCONNECT
    )
    tracker.note_slot(reconnect, processed=True, durable=True)
    gap = tracker.open_gaps()[0]
    return tracker, gap


def _recoverer(
    http,
    *,
    tracker=None,
    page_size=25,
    max_pages=5,
    max_results=125,
    max_credits=50,
    max_slot_span=50_000,
):
    return recovery.HeliusSlotGapRecoverer(
        source_config=_source_config(),
        recovery_config=recovery.HeliusRecoveryConfig(
            page_size=page_size,
            max_pages=max_pages,
            max_results=max_results,
            max_credits=max_credits,
            max_slot_span=max_slot_span,
        ),
        continuity=tracker,
        http_call=http,
        now_fn=lambda: "2026-07-29T12:00:00Z",
    )


def test_exact_request_contract_is_inclusive_succeeded_and_ascending() -> None:
    recoverer = _recoverer(_HttpSequence())
    request = recoverer.build_request(
        request_id=9000,
        gap_from_slot=101,
        gap_to_slot=103,
        limit=25,
        pagination_token=None,
    )
    assert request["method"] == "getTransactionsForAddress"
    assert request["params"][0] == PUMPFUN_PROGRAM_ID
    options = request["params"][1]
    assert options["sortOrder"] == "asc"
    assert options["commitment"] == "confirmed"
    assert options["filters"] == {
        "slot": {"gte": 101, "lte": 103},
        "status": "succeeded",
        "tokenAccounts": "none",
    }
    assert "paginationToken" not in options


def test_one_slot_complete_recovery_decodes_and_closes_gap() -> None:
    tracker, gap = _open_gap()
    http = _HttpSequence(
        lambda request: _response(
            request["id"],
            [_entry(slot=101, signature_byte=20)],
        )
    )
    outcome = _recoverer(http, tracker=tracker).recover(
        gap_id=gap.gap_id,
        gap_from_slot=gap.gap_from_slot,
        gap_to_slot=gap.gap_to_slot,
    )
    assert outcome.coverage_status == recovery.RECOVERY_COMPLETE
    assert outcome.complete_range_proven is True
    assert outcome.pagination_exhausted is True
    assert outcome.empty_range is False
    assert len(outcome.recovered_signatures) == 1
    assert outcome.recovered_slots == (101,)
    assert len(outcome.migrations) == 1
    assert outcome.migration_types == ("migrate",)
    assert outcome.migrations[0].provider_name == (
        helius_source.HELIUS_HTTP_SOURCE_IDENTITY
    )
    assert outcome.metrics["decoded_migrations"] == 1
    assert tracker.snapshot()["continuity_state"] == continuity.NO_GAP


def test_pagination_tokens_are_applied_deterministically() -> None:
    first = _entry(slot=101, signature_byte=21)
    second = _entry(slot=102, signature_byte=22)
    http = _HttpSequence(
        lambda request: _response(request["id"], [first], "page-2"),
        lambda request: _response(request["id"], [second], None),
    )
    outcome = _recoverer(http).recover(
        gap_id="gap_test",
        gap_from_slot=101,
        gap_to_slot=102,
    )
    assert outcome.coverage_status == recovery.RECOVERY_COMPLETE
    assert outcome.recovered_slots == (101, 102)
    assert outcome.metrics["requests"] == 2
    assert outcome.metrics["pages"] == 2
    assert "paginationToken" not in http.requests[0]["params"][1]
    assert http.requests[1]["params"][1]["paginationToken"] == "page-2"


def test_duplicate_http_rows_are_suppressed_by_exact_signature() -> None:
    row = _entry(slot=101, signature_byte=23)
    http = _HttpSequence(
        lambda request: _response(request["id"], [row], "again"),
        lambda request: _response(request["id"], [row], None),
    )
    outcome = _recoverer(http).recover(
        gap_id="gap_duplicate",
        gap_from_slot=101,
        gap_to_slot=101,
    )
    assert outcome.coverage_status == recovery.RECOVERY_COMPLETE
    assert len(outcome.recovered_signatures) == 1
    assert outcome.metrics["returned_rows"] == 2
    assert outcome.metrics["accepted_in_range_rows"] == 1
    assert outcome.metrics["duplicates"] == 1
    assert outcome.metrics["decoded_migrations"] == 1


def test_empty_range_closes_only_after_valid_exhaustion() -> None:
    tracker, gap = _open_gap()
    http = _HttpSequence(
        lambda request: _response(request["id"], [], None)
    )
    outcome = _recoverer(http, tracker=tracker).recover(
        gap_id=gap.gap_id,
        gap_from_slot=101,
        gap_to_slot=101,
    )
    assert outcome.coverage_status == recovery.RECOVERY_COMPLETE
    assert outcome.empty_range is True
    assert outcome.complete_range_proven is True
    assert outcome.metrics["returned_rows"] == 0
    assert outcome.metrics["estimated_credits"] == 10
    assert tracker.snapshot()["continuity_state"] == continuity.NO_GAP


def test_wrong_slot_rejection_keeps_gap_unresolved() -> None:
    tracker, gap = _open_gap()
    http = _HttpSequence(
        lambda request: _response(
            request["id"],
            [_entry(slot=999, signature_byte=24)],
            None,
        )
    )
    outcome = _recoverer(http, tracker=tracker).recover(
        gap_id=gap.gap_id,
        gap_from_slot=101,
        gap_to_slot=101,
    )
    assert outcome.coverage_status == recovery.RECOVERY_PARTIAL
    assert outcome.coverage_reason == (
        recovery.REASON_PROVIDER_ROWS_REJECTED
    )
    assert outcome.complete_range_proven is False
    assert outcome.metrics["wrong_slot_rows"] == 1
    assert tracker.snapshot()["continuity_state"] != continuity.NO_GAP


def test_failed_provider_row_is_rejected_even_with_succeeded_filter() -> None:
    http = _HttpSequence(
        lambda request: _response(
            request["id"],
            [_entry(slot=101, signature_byte=25, failed=True)],
            None,
        )
    )
    outcome = _recoverer(http).recover(
        gap_id="gap_failed_row",
        gap_from_slot=101,
        gap_to_slot=101,
    )
    assert outcome.coverage_status == recovery.RECOVERY_PARTIAL
    assert outcome.metrics["failed_rows"] == 1
    assert outcome.metrics["decoded_migrations"] == 0


def test_local_decode_incomplete_cannot_close_coverage() -> None:
    malformed = _entry(slot=101, signature_byte=32)
    malformed["transaction"]["message"] = {}
    http = _HttpSequence(
        lambda request: _response(request["id"], [malformed], None)
    )
    outcome = _recoverer(http).recover(
        gap_id="gap_decode_incomplete",
        gap_from_slot=101,
        gap_to_slot=101,
    )
    assert outcome.coverage_status == recovery.RECOVERY_PARTIAL
    assert outcome.coverage_reason == (
        recovery.REASON_LOCAL_DECODE_INCOMPLETE
    )
    assert outcome.complete_range_proven is False
    assert outcome.metrics["decoder_rejections"] == 1


def test_page_ceiling_returns_partial_results_without_closure() -> None:
    http = _HttpSequence(
        lambda request: _response(
            request["id"],
            [_entry(slot=101, signature_byte=26)],
            "more",
        )
    )
    outcome = _recoverer(http, max_pages=1).recover(
        gap_id="gap_page_ceiling",
        gap_from_slot=101,
        gap_to_slot=102,
    )
    assert outcome.coverage_status == recovery.RECOVERY_PARTIAL
    assert outcome.coverage_reason == recovery.REASON_PAGE_CEILING
    assert outcome.complete_range_proven is False
    assert outcome.metrics["requests"] == 1


def test_result_ceiling_stops_before_another_request() -> None:
    http = _HttpSequence(
        lambda request: _response(
            request["id"],
            [_entry(slot=101, signature_byte=27)],
            "more",
        )
    )
    outcome = _recoverer(
        http,
        page_size=1,
        max_results=1,
    ).recover(
        gap_id="gap_result_ceiling",
        gap_from_slot=101,
        gap_to_slot=102,
    )
    assert outcome.coverage_status == recovery.RECOVERY_PARTIAL
    assert outcome.coverage_reason == recovery.REASON_RESULT_CEILING
    assert outcome.metrics["requests"] == 1
    assert len(http.requests) == 1


def test_credit_ceiling_stops_before_overspend() -> None:
    http = _HttpSequence(
        lambda request: _response(
            request["id"],
            [_entry(slot=101, signature_byte=28)],
            "more",
        )
    )
    outcome = _recoverer(http, max_credits=10).recover(
        gap_id="gap_credit_ceiling",
        gap_from_slot=101,
        gap_to_slot=102,
    )
    assert outcome.coverage_status == recovery.RECOVERY_PARTIAL
    assert outcome.coverage_reason == recovery.REASON_CREDIT_CEILING
    assert outcome.metrics["estimated_credits"] == 10
    assert outcome.metrics["requests"] == 1


def test_large_gap_has_hard_span_ceiling_and_performs_no_request() -> None:
    http = _HttpSequence()
    outcome = _recoverer(http, max_slot_span=100).recover(
        gap_id="gap_large",
        gap_from_slot=100,
        gap_to_slot=200,
    )
    assert outcome.coverage_status == recovery.RECOVERY_FAILED
    assert outcome.coverage_reason == recovery.REASON_SLOT_SPAN_CEILING
    assert outcome.metrics["requests"] == 0
    assert http.requests == []


@pytest.mark.parametrize(
    "reason",
    (
        recovery.REASON_PROVIDER_AUTH,
        recovery.REASON_PROVIDER_RATE_LIMIT,
        recovery.REASON_PROVIDER_ERROR,
    ),
)
def test_provider_errors_are_visible_and_fail_closed(reason: str) -> None:
    http = _HttpSequence(recovery.HeliusRecoveryProviderError(reason))
    outcome = _recoverer(http).recover(
        gap_id="gap_provider",
        gap_from_slot=101,
        gap_to_slot=101,
    )
    assert outcome.coverage_status == recovery.RECOVERY_FAILED
    assert outcome.coverage_reason == reason
    assert outcome.complete_range_proven is False


def test_pagination_cycle_fails_closed() -> None:
    http = _HttpSequence(
        lambda request: _response(request["id"], [], "same"),
        lambda request: _response(request["id"], [], "same"),
    )
    outcome = _recoverer(http).recover(
        gap_id="gap_cycle",
        gap_from_slot=101,
        gap_to_slot=101,
    )
    assert outcome.coverage_status == recovery.RECOVERY_PARTIAL
    assert outcome.coverage_reason == recovery.REASON_PAGINATION_CYCLE
    assert outcome.complete_range_proven is False


def test_out_of_order_page_fails_closed() -> None:
    http = _HttpSequence(
        lambda request: _response(
            request["id"],
            [
                _entry(slot=102, signature_byte=29),
                _entry(slot=101, signature_byte=30),
            ],
            None,
        )
    )
    outcome = _recoverer(http).recover(
        gap_id="gap_order",
        gap_from_slot=101,
        gap_to_slot=102,
    )
    assert outcome.coverage_status == recovery.RECOVERY_PARTIAL
    assert outcome.coverage_reason == recovery.REASON_ORDER_INVALID


def test_partial_recovery_evidence_survives_restart(tmp_path: Path) -> None:
    state_path = tmp_path / "helius_continuity.json"
    tracker, gap = _open_gap(
        first=100,
        reconnect=103,
        state_path=state_path,
    )
    http = _HttpSequence(
        lambda request: _response(
            request["id"],
            [_entry(slot=101, signature_byte=31)],
            "more",
        )
    )
    outcome = _recoverer(
        http,
        tracker=tracker,
        max_pages=1,
    ).recover(
        gap_id=gap.gap_id,
        gap_from_slot=gap.gap_from_slot,
        gap_to_slot=gap.gap_to_slot,
    )
    assert outcome.coverage_status == recovery.RECOVERY_PARTIAL
    restored = continuity.SourceContinuityTracker(state_path=state_path)
    assert restored.load() is True
    restored_gap = restored.open_gaps()[0]
    assert restored_gap.recovery_coverage_status == (
        continuity.COVERAGE_PARTIAL
    )
    assert restored_gap.recovered_slots == [101]
    assert restored_gap.recovered_signatures == list(
        outcome.recovered_signatures
    )
    assert restored_gap.unresolved_ranges == [[101, 102]]


def test_http_recovery_module_has_no_transport_or_ledger_ownership() -> None:
    text = Path(recovery.__file__).read_text(encoding="utf-8").lower()
    for token in (
        "telegram_transport",
        "telegram_adapter",
        "delivery_transaction",
        "ping_dedupe.jsonl",
        "reserve_delivery",
    ):
        assert token not in text

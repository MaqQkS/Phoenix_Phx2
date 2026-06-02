"""Stage 30.11.3 private sink adapter tests.

Pins the pure / offline private sink adapter: the SAFE default compact body
builder, the gate-input -> private sink request builder, the private dispatch
sink factory (valid accept / invalid-blank / invalid-wrong-type / fake reject),
the Stage 30.11.2 runtime-seam compatibility wrapper, and the pure
results-to-summary fold. The transport is ALWAYS an injected in-memory fake;
no real transport, no Discord, no env read, no network.
"""

from __future__ import annotations

from decimal import Decimal
from typing import List, Optional, Tuple

import pytest

from PHX2.stage30.stage30_9_3_dip_filtered_live_gate_models import (
    Stage30_9_3LiveGateInput,
)
from PHX2.stage30.stage30_11_2_runtime_gate_models import (
    Stage30_11FakeDispatchResult,
)
from PHX2.stage30.stage30_11_3_private_sink_adapter import (
    STAGE30_11_3_COMPACT_BODY_HEADER,
    Stage30_11PrivateSinkAdapterError,
    build_default_compact_body,
    build_private_sink_request_from_gate_input,
    make_runtime_seam_compatible_sink,
    make_stage30_11_private_dispatch_sink,
    summarize_private_sink_results,
)
from PHX2.stage30.stage30_11_3_private_sink_models import (
    PRIVATE_SINK_DECISION_ACCEPTED,
    PRIVATE_SINK_DECISION_REJECTED_INVALID_INPUT,
    PRIVATE_SINK_DECISION_TRANSPORT_FAILED,
    PRIVATE_SINK_REASON_FAKE_TRANSPORT_REJECTED,
    PRIVATE_SINK_REASON_INVALID_SINK_INPUT,
    PRIVATE_SINK_REASON_WOULD_SEND_PRIVATE_OPERATOR_MESSAGE,
    STAGE30_11_3_SOURCE_STAGE,
    Stage30_11PrivateSinkRequest,
    Stage30_11PrivateSinkResult,
)


_CREATED_AT: str = "2026-01-01T00:00:00Z"


# ---------------------------------------------------------------------------
# Inline injected fake transport (recording; never sends, never network)
# ---------------------------------------------------------------------------


class _RecordingFakeTransport:
    def __init__(self, *, accept: bool = True) -> None:
        self._accept = accept
        self.calls: List[Stage30_11PrivateSinkRequest] = []

    def __call__(
        self, request: Stage30_11PrivateSinkRequest
    ) -> Stage30_11PrivateSinkResult:
        self.calls.append(request)
        return Stage30_11PrivateSinkResult(
            candidate_id=request.candidate_id,
            token_mint=request.token_mint,
            sink_decision=(
                PRIVATE_SINK_DECISION_ACCEPTED
                if self._accept
                else PRIVATE_SINK_DECISION_TRANSPORT_FAILED
            ),
            sink_reason=(
                PRIVATE_SINK_REASON_WOULD_SEND_PRIVATE_OPERATOR_MESSAGE
                if self._accept
                else PRIVATE_SINK_REASON_FAKE_TRANSPORT_REJECTED
            ),
            transport_attempted=True,
            transport_accepted=self._accept,
            created_at_utc=_CREATED_AT,
        )


def _gate_input(
    *,
    candidate_id: str = "cand-1",
    token_mint: str = "mint-1",
    tier_token: Optional[str] = "Tier 1",
    candidate_ref: Optional[str] = "ref-1",
) -> Stage30_9_3LiveGateInput:
    return Stage30_9_3LiveGateInput(
        candidate_id=candidate_id,
        token_mint=token_mint,
        tier_token=tier_token,
        drawdown_from_ath=Decimal("0.55"),
        migration_status="PRESENT",
        ath_status="PRESENT",
        market_context_status="PRESENT",
        current_market_cap_usd=Decimal("12345.67"),
        post_migration_ath_verified=True,
        candidate_ref=candidate_ref,
        created_at_utc=_CREATED_AT,
    )


# ---------------------------------------------------------------------------
# 1. build_default_compact_body
# ---------------------------------------------------------------------------


def test_default_compact_body_renders_safe_fields() -> None:
    body = build_default_compact_body(_gate_input())
    assert body.startswith(STAGE30_11_3_COMPACT_BODY_HEADER)
    assert "candidate=cand-1" in body
    assert "mint=mint-1" in body
    assert "tier=Tier 1" in body
    assert "drawdown_from_ath=0.55" in body
    assert "current_market_cap_usd=12345.67" in body
    # Safe display string only: no transport scheme literal.
    assert "://" not in body


def test_default_compact_body_uses_placeholder_for_missing_optionals() -> None:
    gate_input = Stage30_9_3LiveGateInput(
        candidate_id="cand-2",
        token_mint="mint-2",
        tier_token=None,
        drawdown_from_ath=None,
        migration_status="PRESENT",
        ath_status="PRESENT",
        market_context_status="PRESENT",
        current_market_cap_usd=None,
        post_migration_ath_verified=None,
        candidate_ref=None,
        created_at_utc=_CREATED_AT,
    )
    body = build_default_compact_body(gate_input)
    assert "tier=NA" in body
    assert "drawdown_from_ath=NA" in body
    assert "current_market_cap_usd=NA" in body


def test_default_compact_body_raises_on_wrong_type() -> None:
    with pytest.raises(Stage30_11PrivateSinkAdapterError):
        build_default_compact_body(object())  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# 2. build_private_sink_request_from_gate_input
# ---------------------------------------------------------------------------


def test_build_request_maps_fields_and_stamps_source_stage() -> None:
    request = build_private_sink_request_from_gate_input(
        _gate_input(), compact_body="BODY", created_at_utc=_CREATED_AT
    )
    assert isinstance(request, Stage30_11PrivateSinkRequest)
    assert request.candidate_id == "cand-1"
    assert request.token_mint == "mint-1"
    assert request.candidate_ref == "ref-1"
    assert request.tier_token == "Tier 1"
    assert request.compact_body == "BODY"
    assert request.created_at_utc == _CREATED_AT
    assert request.source_stage == STAGE30_11_3_SOURCE_STAGE


def test_build_request_raises_on_wrong_type() -> None:
    with pytest.raises(Stage30_11PrivateSinkAdapterError):
        build_private_sink_request_from_gate_input(
            object(),  # type: ignore[arg-type]
            compact_body="BODY",
            created_at_utc=_CREATED_AT,
        )


# ---------------------------------------------------------------------------
# 3. Private dispatch sink: valid accept
# ---------------------------------------------------------------------------


def test_sink_valid_input_accepting_transport_is_accepted() -> None:
    transport = _RecordingFakeTransport(accept=True)
    sink = make_stage30_11_private_dispatch_sink(
        transport=transport, created_at_utc=_CREATED_AT
    )
    result = sink(_gate_input())
    assert result.sink_decision == PRIVATE_SINK_DECISION_ACCEPTED
    assert result.sink_reason == (
        PRIVATE_SINK_REASON_WOULD_SEND_PRIVATE_OPERATOR_MESSAGE
    )
    assert result.transport_attempted is True
    assert result.transport_accepted is True
    assert result.candidate_id == "cand-1"
    assert result.token_mint == "mint-1"
    # The transport was called exactly once, with a well-formed request.
    assert len(transport.calls) == 1
    assert transport.calls[0].source_stage == STAGE30_11_3_SOURCE_STAGE
    assert transport.calls[0].compact_body.startswith(
        STAGE30_11_3_COMPACT_BODY_HEADER
    )


# ---------------------------------------------------------------------------
# 4. Private dispatch sink: invalid input never reaches transport
# ---------------------------------------------------------------------------


def test_sink_blank_candidate_id_is_rejected_without_transport() -> None:
    transport = _RecordingFakeTransport(accept=True)
    sink = make_stage30_11_private_dispatch_sink(
        transport=transport, created_at_utc=_CREATED_AT
    )
    result = sink(_gate_input(candidate_id=""))
    assert result.sink_decision == PRIVATE_SINK_DECISION_REJECTED_INVALID_INPUT
    assert result.sink_reason == PRIVATE_SINK_REASON_INVALID_SINK_INPUT
    assert result.transport_attempted is False
    assert result.transport_accepted is False
    assert transport.calls == []


def test_sink_blank_token_mint_is_rejected_without_transport() -> None:
    transport = _RecordingFakeTransport(accept=True)
    sink = make_stage30_11_private_dispatch_sink(
        transport=transport, created_at_utc=_CREATED_AT
    )
    result = sink(_gate_input(token_mint="   "))
    assert result.sink_decision == PRIVATE_SINK_DECISION_REJECTED_INVALID_INPUT
    assert result.transport_attempted is False
    assert transport.calls == []


def test_sink_wrong_record_type_is_rejected_without_transport() -> None:
    transport = _RecordingFakeTransport(accept=True)
    sink = make_stage30_11_private_dispatch_sink(
        transport=transport, created_at_utc=_CREATED_AT
    )
    result = sink(object())  # type: ignore[arg-type]
    assert result.sink_decision == PRIVATE_SINK_DECISION_REJECTED_INVALID_INPUT
    assert result.transport_attempted is False
    assert result.candidate_id == ""
    assert result.token_mint == ""
    assert transport.calls == []


# ---------------------------------------------------------------------------
# 5. Private dispatch sink: fake transport reject
# ---------------------------------------------------------------------------


def test_sink_valid_input_rejecting_transport_is_transport_failed() -> None:
    transport = _RecordingFakeTransport(accept=False)
    sink = make_stage30_11_private_dispatch_sink(
        transport=transport, created_at_utc=_CREATED_AT
    )
    result = sink(_gate_input())
    assert result.sink_decision == PRIVATE_SINK_DECISION_TRANSPORT_FAILED
    assert result.sink_reason == PRIVATE_SINK_REASON_FAKE_TRANSPORT_REJECTED
    assert result.transport_attempted is True
    assert result.transport_accepted is False
    assert len(transport.calls) == 1


# ---------------------------------------------------------------------------
# 6. Runtime seam compatibility wrapper
# ---------------------------------------------------------------------------


def test_seam_wrapper_returns_fake_dispatch_result_accepted() -> None:
    transport = _RecordingFakeTransport(accept=True)
    private_sink = make_stage30_11_private_dispatch_sink(
        transport=transport, created_at_utc=_CREATED_AT
    )
    seam_sink = make_runtime_seam_compatible_sink(
        private_sink=private_sink, created_at_utc=_CREATED_AT
    )
    result = seam_sink(_gate_input())
    assert isinstance(result, Stage30_11FakeDispatchResult)
    assert result.accepted is True
    assert result.candidate_id == "cand-1"
    assert result.token_mint == "mint-1"
    assert result.created_at_utc == _CREATED_AT


def test_seam_wrapper_maps_reject_to_not_accepted() -> None:
    transport = _RecordingFakeTransport(accept=False)
    private_sink = make_stage30_11_private_dispatch_sink(
        transport=transport, created_at_utc=_CREATED_AT
    )
    seam_sink = make_runtime_seam_compatible_sink(
        private_sink=private_sink, created_at_utc=_CREATED_AT
    )
    result = seam_sink(_gate_input())
    assert isinstance(result, Stage30_11FakeDispatchResult)
    assert result.accepted is False


def test_seam_wrapper_maps_invalid_to_not_accepted() -> None:
    transport = _RecordingFakeTransport(accept=True)
    private_sink = make_stage30_11_private_dispatch_sink(
        transport=transport, created_at_utc=_CREATED_AT
    )
    seam_sink = make_runtime_seam_compatible_sink(
        private_sink=private_sink, created_at_utc=_CREATED_AT
    )
    result = seam_sink(_gate_input(candidate_id=""))
    assert isinstance(result, Stage30_11FakeDispatchResult)
    assert result.accepted is False
    assert transport.calls == []


# ---------------------------------------------------------------------------
# 7. summarize_private_sink_results fold
# ---------------------------------------------------------------------------


def _result(decision: str, *, attempted: bool, accepted: bool) -> (
    Stage30_11PrivateSinkResult
):
    reason = {
        PRIVATE_SINK_DECISION_ACCEPTED: (
            PRIVATE_SINK_REASON_WOULD_SEND_PRIVATE_OPERATOR_MESSAGE
        ),
        PRIVATE_SINK_DECISION_REJECTED_INVALID_INPUT: (
            PRIVATE_SINK_REASON_INVALID_SINK_INPUT
        ),
        PRIVATE_SINK_DECISION_TRANSPORT_FAILED: (
            PRIVATE_SINK_REASON_FAKE_TRANSPORT_REJECTED
        ),
    }[decision]
    return Stage30_11PrivateSinkResult(
        candidate_id="c",
        token_mint="m",
        sink_decision=decision,
        sink_reason=reason,
        transport_attempted=attempted,
        transport_accepted=accepted,
        created_at_utc=_CREATED_AT,
    )


def test_summarize_counts_each_axis() -> None:
    results: Tuple[Stage30_11PrivateSinkResult, ...] = (
        _result(PRIVATE_SINK_DECISION_ACCEPTED, attempted=True, accepted=True),
        _result(
            PRIVATE_SINK_DECISION_REJECTED_INVALID_INPUT,
            attempted=False,
            accepted=False,
        ),
        _result(
            PRIVATE_SINK_DECISION_TRANSPORT_FAILED,
            attempted=True,
            accepted=False,
        ),
    )
    summary = summarize_private_sink_results(results, created_at_utc=_CREATED_AT)
    assert summary.requests_seen == 3
    assert summary.accepted == 1
    assert summary.rejected_invalid == 1
    assert summary.transport_failed == 1
    assert summary.transport_attempted == 2
    assert summary.transport_accepted == 1
    assert summary.created_at_utc == _CREATED_AT


def test_summarize_skips_non_conforming_items() -> None:
    results = (
        _result(PRIVATE_SINK_DECISION_ACCEPTED, attempted=True, accepted=True),
        object(),
        None,
    )
    summary = summarize_private_sink_results(
        results,  # type: ignore[arg-type]
        created_at_utc=_CREATED_AT,
    )
    assert summary.requests_seen == 1
    assert summary.accepted == 1

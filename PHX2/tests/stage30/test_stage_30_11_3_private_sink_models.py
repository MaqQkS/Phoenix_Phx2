"""Stage 30.11.3 private sink models tests.

Pins the passive Stage 30.11.3 private sink model layer: the minor version +
private sink schema version + source-stage token, the closed-set sink decision /
reason vocabularies + their membership predicates, the immutable (frozen)
request / result / proof-summary dataclasses + their field names, and the pure
safe-shape helper. Fakes / offline only; no live call, no provider, no Discord,
no env read.
"""

from __future__ import annotations

import dataclasses

import pytest

from PHX2.stage30.stage30_11_3_private_sink_models import (
    PRIVATE_SINK_DECISION_ACCEPTED,
    PRIVATE_SINK_DECISION_REJECTED_INVALID_INPUT,
    PRIVATE_SINK_DECISION_TRANSPORT_FAILED,
    PRIVATE_SINK_REASON_FAKE_TRANSPORT_REJECTED,
    PRIVATE_SINK_REASON_INVALID_SINK_INPUT,
    PRIVATE_SINK_REASON_WOULD_SEND_PRIVATE_OPERATOR_MESSAGE,
    STAGE30_11_3_MINOR_VERSION,
    STAGE30_11_3_PRIVATE_SINK_ACCEPT_DECISION,
    STAGE30_11_3_PRIVATE_SINK_ACCEPT_REASON,
    STAGE30_11_3_PRIVATE_SINK_DECISIONS,
    STAGE30_11_3_PRIVATE_SINK_REASONS,
    STAGE30_11_3_PRIVATE_SINK_SCHEMA_VERSION,
    STAGE30_11_3_SOURCE_STAGE,
    Stage30_11PrivateSinkProofSummary,
    Stage30_11PrivateSinkRequest,
    Stage30_11PrivateSinkResult,
    is_nonblank_str,
    is_private_sink_decision,
    is_private_sink_reason,
    private_sink_proof_summary_field_names,
    private_sink_request_field_names,
    private_sink_result_field_names,
)


# ---------------------------------------------------------------------------
# 1. Minor version + schema identity + source stage
# ---------------------------------------------------------------------------


def test_minor_version_pinned() -> None:
    assert STAGE30_11_3_MINOR_VERSION == "30.11.3"


def test_schema_version_pinned() -> None:
    assert STAGE30_11_3_PRIVATE_SINK_SCHEMA_VERSION == (
        "stage30_11_3_v0_private_sink_adapter"
    )


def test_source_stage_pinned() -> None:
    assert STAGE30_11_3_SOURCE_STAGE == "30.11.3"


# ---------------------------------------------------------------------------
# 2. Closed-set sink decisions
# ---------------------------------------------------------------------------


def test_sink_decisions_are_the_three_closed_tokens() -> None:
    assert STAGE30_11_3_PRIVATE_SINK_DECISIONS == (
        "PRIVATE_SINK_ACCEPTED",
        "PRIVATE_SINK_REJECTED_INVALID_INPUT",
        "PRIVATE_SINK_TRANSPORT_FAILED",
    )
    assert PRIVATE_SINK_DECISION_ACCEPTED == "PRIVATE_SINK_ACCEPTED"
    assert PRIVATE_SINK_DECISION_REJECTED_INVALID_INPUT == (
        "PRIVATE_SINK_REJECTED_INVALID_INPUT"
    )
    assert PRIVATE_SINK_DECISION_TRANSPORT_FAILED == (
        "PRIVATE_SINK_TRANSPORT_FAILED"
    )


def test_accept_decision_is_the_only_accept() -> None:
    assert STAGE30_11_3_PRIVATE_SINK_ACCEPT_DECISION == (
        PRIVATE_SINK_DECISION_ACCEPTED
    )
    assert STAGE30_11_3_PRIVATE_SINK_ACCEPT_DECISION in (
        STAGE30_11_3_PRIVATE_SINK_DECISIONS
    )


def test_is_private_sink_decision_is_total_and_closed() -> None:
    for token in STAGE30_11_3_PRIVATE_SINK_DECISIONS:
        assert is_private_sink_decision(token) is True
    for bad in ("", "private_sink_accepted", "ACCEPTED", None, 1, object()):
        assert is_private_sink_decision(bad) is False


def test_decisions_are_unique() -> None:
    assert len(set(STAGE30_11_3_PRIVATE_SINK_DECISIONS)) == 3


# ---------------------------------------------------------------------------
# 3. Closed-set sink reasons
# ---------------------------------------------------------------------------


def test_sink_reasons_are_the_three_closed_tokens() -> None:
    assert STAGE30_11_3_PRIVATE_SINK_REASONS == (
        "WOULD_SEND_PRIVATE_OPERATOR_MESSAGE",
        "INVALID_SINK_INPUT",
        "FAKE_TRANSPORT_REJECTED",
    )
    assert PRIVATE_SINK_REASON_WOULD_SEND_PRIVATE_OPERATOR_MESSAGE == (
        "WOULD_SEND_PRIVATE_OPERATOR_MESSAGE"
    )
    assert PRIVATE_SINK_REASON_INVALID_SINK_INPUT == "INVALID_SINK_INPUT"
    assert PRIVATE_SINK_REASON_FAKE_TRANSPORT_REJECTED == (
        "FAKE_TRANSPORT_REJECTED"
    )


def test_accept_reason_is_the_would_send() -> None:
    assert STAGE30_11_3_PRIVATE_SINK_ACCEPT_REASON == (
        PRIVATE_SINK_REASON_WOULD_SEND_PRIVATE_OPERATOR_MESSAGE
    )
    assert STAGE30_11_3_PRIVATE_SINK_ACCEPT_REASON in (
        STAGE30_11_3_PRIVATE_SINK_REASONS
    )


def test_is_private_sink_reason_is_total_and_closed() -> None:
    for token in STAGE30_11_3_PRIVATE_SINK_REASONS:
        assert is_private_sink_reason(token) is True
    for bad in ("", "would_send", "REAL_SEND", None, 1, object()):
        assert is_private_sink_reason(bad) is False


def test_reasons_are_unique() -> None:
    assert len(set(STAGE30_11_3_PRIVATE_SINK_REASONS)) == 3


# ---------------------------------------------------------------------------
# 4. is_nonblank_str helper (pure / total)
# ---------------------------------------------------------------------------


def test_is_nonblank_str_total() -> None:
    assert is_nonblank_str("cand-1") is True
    for bad in ("", "   ", "\t\n", None, 0, 1, object(), b"x"):
        assert is_nonblank_str(bad) is False


# ---------------------------------------------------------------------------
# 5. Frozen models + field names
# ---------------------------------------------------------------------------


def _request() -> Stage30_11PrivateSinkRequest:
    return Stage30_11PrivateSinkRequest(
        candidate_id="cand-1",
        token_mint="mint-1",
        candidate_ref="ref-1",
        tier_token="Tier 1",
        compact_body="body",
        created_at_utc="2026-01-01T00:00:00Z",
        source_stage=STAGE30_11_3_SOURCE_STAGE,
    )


def _result() -> Stage30_11PrivateSinkResult:
    return Stage30_11PrivateSinkResult(
        candidate_id="cand-1",
        token_mint="mint-1",
        sink_decision=PRIVATE_SINK_DECISION_ACCEPTED,
        sink_reason=PRIVATE_SINK_REASON_WOULD_SEND_PRIVATE_OPERATOR_MESSAGE,
        transport_attempted=True,
        transport_accepted=True,
        created_at_utc="2026-01-01T00:00:00Z",
    )


def _summary() -> Stage30_11PrivateSinkProofSummary:
    return Stage30_11PrivateSinkProofSummary(
        requests_seen=3,
        accepted=1,
        rejected_invalid=1,
        transport_failed=1,
        transport_attempted=2,
        transport_accepted=1,
        created_at_utc="2026-01-01T00:00:00Z",
    )


def test_request_fields_pinned() -> None:
    assert private_sink_request_field_names() == (
        "candidate_id",
        "token_mint",
        "candidate_ref",
        "tier_token",
        "compact_body",
        "created_at_utc",
        "source_stage",
    )


def test_result_fields_pinned() -> None:
    assert private_sink_result_field_names() == (
        "candidate_id",
        "token_mint",
        "sink_decision",
        "sink_reason",
        "transport_attempted",
        "transport_accepted",
        "created_at_utc",
    )


def test_summary_fields_pinned() -> None:
    assert private_sink_proof_summary_field_names() == (
        "requests_seen",
        "accepted",
        "rejected_invalid",
        "transport_failed",
        "transport_attempted",
        "transport_accepted",
        "created_at_utc",
    )


def test_request_is_frozen() -> None:
    request = _request()
    with pytest.raises(dataclasses.FrozenInstanceError):
        request.compact_body = "mutated"  # type: ignore[misc]


def test_result_is_frozen() -> None:
    result = _result()
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.transport_accepted = False  # type: ignore[misc]


def test_summary_is_frozen() -> None:
    summary = _summary()
    with pytest.raises(dataclasses.FrozenInstanceError):
        summary.accepted = 99  # type: ignore[misc]


def test_models_carry_no_secret_or_payload_field_names() -> None:
    all_fields = (
        private_sink_request_field_names()
        + private_sink_result_field_names()
        + private_sink_proof_summary_field_names()
    )
    for name in all_fields:
        lower = name.lower()
        for forbidden in (
            "webhook",
            "api_key",
            "bearer",
            "secret",
            "raw_payload",
            "getenv",
            "environ",
            "url",
            "host",
        ):
            assert forbidden not in lower, (
                f"Stage 30.11.3 field {name!r} carries forbidden substring "
                f"{forbidden!r}"
            )

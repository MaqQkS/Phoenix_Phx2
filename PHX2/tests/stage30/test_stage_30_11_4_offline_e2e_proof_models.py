"""Stage 30.11.4 offline end-to-end proof models tests.

Pins the passive Stage 30.11.4 end-to-end proof model layer: the minor version +
end-to-end proof schema version, the closed-set proof decision / reason
vocabularies + their membership predicates, the author-verified expected baseline
counts, the immutable (frozen) summary / result dataclasses + their field names,
and the pure safe-shape helper. Fakes / offline only; no live call, no provider,
no Discord, no env read.
"""

from __future__ import annotations

import dataclasses

import pytest

from PHX2.stage30.stage30_11_4_offline_e2e_proof_models import (
    OFFLINE_E2E_PROOF_FAILED,
    OFFLINE_E2E_PROOF_PASSED,
    PROOF_REASON_INVALID_PROOF_INPUT,
    PROOF_REASON_PASS_DIP_REACHED_FAKE_TRANSPORT_ONLY,
    PROOF_REASON_UNEXPECTED_E2E_COUNTS,
    PROOF_REASON_UNEXPECTED_TRANSPORT_ATTEMPT,
    STAGE30_11_4_EXPECTED_BRIDGE_SUCCESSES,
    STAGE30_11_4_EXPECTED_BRIDGE_SUPPRESSED,
    STAGE30_11_4_EXPECTED_CANDIDATES_SEEN,
    STAGE30_11_4_EXPECTED_DIP_CANDIDATE_ID,
    STAGE30_11_4_EXPECTED_DIP_TOKEN_MINT,
    STAGE30_11_4_EXPECTED_GATE_PASSES,
    STAGE30_11_4_EXPECTED_GATE_SUPPRESSED,
    STAGE30_11_4_EXPECTED_SINK_ACCEPTS,
    STAGE30_11_4_EXPECTED_SINK_ATTEMPTS,
    STAGE30_11_4_EXPECTED_SINK_FAILURES,
    STAGE30_11_4_EXPECTED_TRANSPORT_ACCEPTS,
    STAGE30_11_4_EXPECTED_TRANSPORT_ATTEMPTS,
    STAGE30_11_4_MINOR_VERSION,
    STAGE30_11_4_MIN_EXPECTED_CANDIDATES_SEEN,
    STAGE30_11_4_OFFLINE_E2E_PROOF_SCHEMA_VERSION,
    STAGE30_11_4_PROOF_DECISIONS,
    STAGE30_11_4_PROOF_PASS_DECISION,
    STAGE30_11_4_PROOF_PASS_REASON,
    STAGE30_11_4_PROOF_REASONS,
    Stage30_11OfflineE2EProofResult,
    Stage30_11OfflineE2EProofSummary,
    is_nonblank_str,
    is_offline_e2e_proof_decision,
    is_offline_e2e_proof_reason,
    offline_e2e_proof_result_field_names,
    offline_e2e_proof_summary_field_names,
)


# ---------------------------------------------------------------------------
# 1. Minor version + schema identity
# ---------------------------------------------------------------------------


def test_minor_version_pinned() -> None:
    assert STAGE30_11_4_MINOR_VERSION == "30.11.4"


def test_schema_version_pinned() -> None:
    assert STAGE30_11_4_OFFLINE_E2E_PROOF_SCHEMA_VERSION == (
        "stage30_11_4_v0_offline_e2e_proof"
    )


# ---------------------------------------------------------------------------
# 2. Closed-set proof decisions
# ---------------------------------------------------------------------------


def test_proof_decisions_are_the_two_closed_tokens() -> None:
    assert STAGE30_11_4_PROOF_DECISIONS == (
        "OFFLINE_E2E_PROOF_PASSED",
        "OFFLINE_E2E_PROOF_FAILED",
    )
    assert OFFLINE_E2E_PROOF_PASSED == "OFFLINE_E2E_PROOF_PASSED"
    assert OFFLINE_E2E_PROOF_FAILED == "OFFLINE_E2E_PROOF_FAILED"


def test_pass_decision_is_the_only_pass() -> None:
    assert STAGE30_11_4_PROOF_PASS_DECISION == OFFLINE_E2E_PROOF_PASSED
    assert STAGE30_11_4_PROOF_PASS_DECISION in STAGE30_11_4_PROOF_DECISIONS


def test_is_proof_decision_is_total_and_closed() -> None:
    for token in STAGE30_11_4_PROOF_DECISIONS:
        assert is_offline_e2e_proof_decision(token) is True
    for bad in ("", "offline_e2e_proof_passed", "PASSED", None, 1, object()):
        assert is_offline_e2e_proof_decision(bad) is False


def test_decisions_are_unique() -> None:
    assert len(set(STAGE30_11_4_PROOF_DECISIONS)) == 2


# ---------------------------------------------------------------------------
# 3. Closed-set proof reasons
# ---------------------------------------------------------------------------


def test_proof_reasons_are_the_four_closed_tokens() -> None:
    assert STAGE30_11_4_PROOF_REASONS == (
        "PASS_DIP_REACHED_FAKE_TRANSPORT_ONLY",
        "UNEXPECTED_E2E_COUNTS",
        "UNEXPECTED_TRANSPORT_ATTEMPT",
        "INVALID_PROOF_INPUT",
    )
    assert PROOF_REASON_PASS_DIP_REACHED_FAKE_TRANSPORT_ONLY == (
        "PASS_DIP_REACHED_FAKE_TRANSPORT_ONLY"
    )
    assert PROOF_REASON_UNEXPECTED_E2E_COUNTS == "UNEXPECTED_E2E_COUNTS"
    assert PROOF_REASON_UNEXPECTED_TRANSPORT_ATTEMPT == (
        "UNEXPECTED_TRANSPORT_ATTEMPT"
    )
    assert PROOF_REASON_INVALID_PROOF_INPUT == "INVALID_PROOF_INPUT"


def test_pass_reason_is_the_dip_reached_transport_only() -> None:
    assert STAGE30_11_4_PROOF_PASS_REASON == (
        PROOF_REASON_PASS_DIP_REACHED_FAKE_TRANSPORT_ONLY
    )
    assert STAGE30_11_4_PROOF_PASS_REASON in STAGE30_11_4_PROOF_REASONS


def test_is_proof_reason_is_total_and_closed() -> None:
    for token in STAGE30_11_4_PROOF_REASONS:
        assert is_offline_e2e_proof_reason(token) is True
    for bad in ("", "pass_dip", "REAL_SEND", None, 1, object()):
        assert is_offline_e2e_proof_reason(bad) is False


def test_reasons_are_unique() -> None:
    assert len(set(STAGE30_11_4_PROOF_REASONS)) == 4


# ---------------------------------------------------------------------------
# 4. Expected baseline counts
# ---------------------------------------------------------------------------


def test_expected_baseline_counts_pinned() -> None:
    assert STAGE30_11_4_MIN_EXPECTED_CANDIDATES_SEEN == 4
    assert STAGE30_11_4_EXPECTED_CANDIDATES_SEEN == 5
    assert STAGE30_11_4_EXPECTED_BRIDGE_SUCCESSES == 2
    assert STAGE30_11_4_EXPECTED_BRIDGE_SUPPRESSED == 3
    assert STAGE30_11_4_EXPECTED_GATE_PASSES == 1
    assert STAGE30_11_4_EXPECTED_GATE_SUPPRESSED == 1
    assert STAGE30_11_4_EXPECTED_SINK_ATTEMPTS == 1
    assert STAGE30_11_4_EXPECTED_SINK_ACCEPTS == 1
    assert STAGE30_11_4_EXPECTED_SINK_FAILURES == 0
    assert STAGE30_11_4_EXPECTED_TRANSPORT_ATTEMPTS == 1
    assert STAGE30_11_4_EXPECTED_TRANSPORT_ACCEPTS == 1
    assert STAGE30_11_4_EXPECTED_DIP_CANDIDATE_ID == "cand-tier1"
    assert STAGE30_11_4_EXPECTED_DIP_TOKEN_MINT == "mint-tier1"


def test_expected_counts_are_internally_consistent() -> None:
    # The single dip is the ONLY candidate that bridges + passes + dispatches +
    # reaches the transport, and the baseline candidate count satisfies the
    # four-scenario floor.
    assert STAGE30_11_4_EXPECTED_CANDIDATES_SEEN >= (
        STAGE30_11_4_MIN_EXPECTED_CANDIDATES_SEEN
    )
    assert (
        STAGE30_11_4_EXPECTED_GATE_PASSES
        == STAGE30_11_4_EXPECTED_SINK_ATTEMPTS
        == STAGE30_11_4_EXPECTED_TRANSPORT_ATTEMPTS
        == 1
    )
    assert (
        STAGE30_11_4_EXPECTED_SINK_ACCEPTS
        == STAGE30_11_4_EXPECTED_TRANSPORT_ACCEPTS
        == 1
    )
    assert STAGE30_11_4_EXPECTED_SINK_FAILURES == 0
    # bridged = gate-pass + gate-suppressed; the rest are bridge-suppressed.
    assert (
        STAGE30_11_4_EXPECTED_BRIDGE_SUCCESSES
        == STAGE30_11_4_EXPECTED_GATE_PASSES
        + STAGE30_11_4_EXPECTED_GATE_SUPPRESSED
    )
    assert (
        STAGE30_11_4_EXPECTED_BRIDGE_SUCCESSES
        + STAGE30_11_4_EXPECTED_BRIDGE_SUPPRESSED
        == STAGE30_11_4_EXPECTED_CANDIDATES_SEEN
    )


# ---------------------------------------------------------------------------
# 5. is_nonblank_str helper (pure / total)
# ---------------------------------------------------------------------------


def test_is_nonblank_str_total() -> None:
    assert is_nonblank_str("2026-01-01T00:00:00Z") is True
    for bad in ("", "   ", "\t\n", None, 0, 1, object(), b"x"):
        assert is_nonblank_str(bad) is False


# ---------------------------------------------------------------------------
# 6. Frozen models + field names
# ---------------------------------------------------------------------------


def _summary() -> Stage30_11OfflineE2EProofSummary:
    return Stage30_11OfflineE2EProofSummary(
        candidates_seen=5,
        bridge_successes=2,
        bridge_suppressed=3,
        gate_passes=1,
        gate_suppressed=1,
        sink_attempts=1,
        sink_accepts=1,
        sink_failures=0,
        transport_attempts=1,
        transport_accepts=1,
        runtime_stopped_by_candidate_cap=0,
        runtime_stopped_by_dispatch_cap=0,
        runtime_stopped_by_runtime_seconds=0,
        proof_decision=OFFLINE_E2E_PROOF_PASSED,
        proof_reason=PROOF_REASON_PASS_DIP_REACHED_FAKE_TRANSPORT_ONLY,
        created_at_utc="2026-01-01T00:00:00Z",
    )


def _result() -> Stage30_11OfflineE2EProofResult:
    return Stage30_11OfflineE2EProofResult(
        proof_decision=OFFLINE_E2E_PROOF_PASSED,
        proof_reason=PROOF_REASON_PASS_DIP_REACHED_FAKE_TRANSPORT_ONLY,
        summary=_summary(),
        runtime_outcomes=(),
        transport_candidate_ids=("cand-tier1",),
        transport_token_mints=("mint-tier1",),
        created_at_utc="2026-01-01T00:00:00Z",
    )


def test_summary_fields_pinned() -> None:
    assert offline_e2e_proof_summary_field_names() == (
        "candidates_seen",
        "bridge_successes",
        "bridge_suppressed",
        "gate_passes",
        "gate_suppressed",
        "sink_attempts",
        "sink_accepts",
        "sink_failures",
        "transport_attempts",
        "transport_accepts",
        "runtime_stopped_by_candidate_cap",
        "runtime_stopped_by_dispatch_cap",
        "runtime_stopped_by_runtime_seconds",
        "proof_decision",
        "proof_reason",
        "created_at_utc",
    )


def test_result_fields_pinned() -> None:
    assert offline_e2e_proof_result_field_names() == (
        "proof_decision",
        "proof_reason",
        "summary",
        "runtime_outcomes",
        "transport_candidate_ids",
        "transport_token_mints",
        "created_at_utc",
    )


def test_summary_is_frozen() -> None:
    summary = _summary()
    with pytest.raises(dataclasses.FrozenInstanceError):
        summary.sink_accepts = 99  # type: ignore[misc]


def test_result_is_frozen() -> None:
    result = _result()
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.proof_decision = OFFLINE_E2E_PROOF_FAILED  # type: ignore[misc]


def test_result_embeds_the_summary() -> None:
    result = _result()
    assert isinstance(result.summary, Stage30_11OfflineE2EProofSummary)
    assert result.summary.proof_decision == result.proof_decision
    assert result.summary.proof_reason == result.proof_reason


def test_models_carry_no_secret_or_payload_field_names() -> None:
    all_fields = (
        offline_e2e_proof_summary_field_names()
        + offline_e2e_proof_result_field_names()
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
                f"Stage 30.11.4 field {name!r} carries forbidden substring "
                f"{forbidden!r}"
            )

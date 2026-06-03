"""Stage 30.11.5 offline fake live wiring proof tests.

Proves the composed bounded run over the deterministic four-candidate fake source
behaves exactly as the author-verified baseline requires: four source items seen,
three assembled (the assembler-rejected candidate never becomes a snapshot),
three reach the committed seam, two bridge, one passes the committed dip gate, one
dispatch attempt + accept, and the INJECTED recording fake transport client
records EXACTLY one would-deliver -- for the dip (``cand-tier1`` / ``mint-tier1``)
ONLY. A rejecting fake client variant turns the dip into a clean transport-failed
with no accepts.

Fake / offline only. No live call, no provider, no Discord, no env read, no real
transport.
"""

from __future__ import annotations

from decimal import Decimal

from PHX2.stage30.stage30_11_2_fake_runtime_gate_proof import (
    make_constant_clock,
)
from PHX2.stage30.stage30_11_5_fake_live_wiring_proof import (
    Stage30_11_5RecordingFakeTransportClient,
    default_fake_live_wiring_source,
    run_stage30_11_5_fake_live_wiring_proof,
)
from PHX2.stage30.stage30_11_5_live_wiring_models import (
    STAGE30_11_5_EXPECTED_ASSEMBLED,
    STAGE30_11_5_EXPECTED_ASSEMBLY_REJECTED,
    STAGE30_11_5_EXPECTED_BRIDGED,
    STAGE30_11_5_EXPECTED_CANDIDATES_SEEN,
    STAGE30_11_5_EXPECTED_DIP_CANDIDATE_ID,
    STAGE30_11_5_EXPECTED_DIP_TOKEN_MINT,
    STAGE30_11_5_EXPECTED_DISPATCH_ACCEPTED,
    STAGE30_11_5_EXPECTED_DISPATCH_ATTEMPTED,
    STAGE30_11_5_EXPECTED_GATE_PASSED,
    STAGE30_11_5_EXPECTED_SOURCE_ITEMS_SEEN,
    STAGE30_11_5_EXPECTED_SUPPRESSED_BY_BRIDGE,
    STAGE30_11_5_EXPECTED_SUPPRESSED_BY_GATE,
    STAGE30_11_5_EXPECTED_TRANSPORT_ACCEPTS,
    STAGE30_11_5_EXPECTED_TRANSPORT_ATTEMPTS,
    TRANSPORT_STATUS_REJECTED,
    TRANSPORT_STATUS_WOULD_DELIVER,
)


# ---------------------------------------------------------------------------
# Default source shape
# ---------------------------------------------------------------------------


def test_default_source_is_four_distinct_projections() -> None:
    source = default_fake_live_wiring_source()
    assert len(source) == 4
    ids = [p["candidate_id"] for p in source]
    assert ids == ["cand-unknown", "cand-no-ath", "cand-tier1", "cand-invalid"]
    # The rejected projection omits the required market-cap field.
    invalid = source[3]
    assert "current_market_cap_usd" not in invalid


# ---------------------------------------------------------------------------
# Baseline run
# ---------------------------------------------------------------------------


def test_proof_matches_the_author_verified_baseline() -> None:
    result, client = run_stage30_11_5_fake_live_wiring_proof()
    s = result.summary
    assert s.source_items_seen == STAGE30_11_5_EXPECTED_SOURCE_ITEMS_SEEN
    assert s.assembled == STAGE30_11_5_EXPECTED_ASSEMBLED
    assert s.assembly_rejected == STAGE30_11_5_EXPECTED_ASSEMBLY_REJECTED
    assert s.candidates_seen == STAGE30_11_5_EXPECTED_CANDIDATES_SEEN
    assert s.bridged == STAGE30_11_5_EXPECTED_BRIDGED
    assert s.gate_passed == STAGE30_11_5_EXPECTED_GATE_PASSED
    assert s.dispatch_attempted == STAGE30_11_5_EXPECTED_DISPATCH_ATTEMPTED
    assert s.dispatch_accepted == STAGE30_11_5_EXPECTED_DISPATCH_ACCEPTED
    assert s.suppressed_by_bridge == STAGE30_11_5_EXPECTED_SUPPRESSED_BY_BRIDGE
    assert s.suppressed_by_gate == STAGE30_11_5_EXPECTED_SUPPRESSED_BY_GATE
    assert s.stopped_by_candidate_cap == 0
    assert s.stopped_by_dispatch_cap == 0
    assert s.stopped_by_runtime_seconds == 0


def test_proof_transport_reaches_the_dip_only() -> None:
    result, client = run_stage30_11_5_fake_live_wiring_proof()
    assert client.attempted == STAGE30_11_5_EXPECTED_TRANSPORT_ATTEMPTS == 1
    assert client.accepted == STAGE30_11_5_EXPECTED_TRANSPORT_ACCEPTS == 1
    assert client.rejected == 0
    assert client.candidate_ids == [STAGE30_11_5_EXPECTED_DIP_CANDIDATE_ID]
    assert client.token_mints == [STAGE30_11_5_EXPECTED_DIP_TOKEN_MINT]
    # The recorded body is a safe display string (no transport scheme).
    assert len(client.bodies) == 1
    assert "://" not in client.bodies[0]


def test_proof_runtime_outcomes_recorded() -> None:
    result, client = run_stage30_11_5_fake_live_wiring_proof()
    # Three snapshots reached the seam, so three runtime outcomes.
    assert len(result.runtime_outcomes) == 3
    # Four assembly outcomes (one per source item).
    assert len(result.assembly_outcomes) == 4


# ---------------------------------------------------------------------------
# Rejecting-client variant
# ---------------------------------------------------------------------------


def test_rejecting_client_turns_the_dip_into_transport_failed() -> None:
    client = Stage30_11_5RecordingFakeTransportClient(
        created_at_utc="2026-01-01T00:00:00Z",
        reject_candidate_ids=(STAGE30_11_5_EXPECTED_DIP_CANDIDATE_ID,),
    )
    result, returned = run_stage30_11_5_fake_live_wiring_proof(
        transport_client=client
    )
    assert returned is client
    # The dip still reached the transport (one attempt) but was rejected.
    assert client.attempted == 1
    assert client.accepted == 0
    assert client.rejected == 1
    # The dispatch was attempted but NOT accepted.
    assert result.summary.dispatch_attempted == 1
    assert result.summary.dispatch_accepted == 0


# ---------------------------------------------------------------------------
# Recording fake client unit behavior
# ---------------------------------------------------------------------------


def test_recording_fake_client_status_tokens() -> None:
    from PHX2.stage30.stage30_11_5_live_wiring_models import (
        Stage30_11_5PrivateOperatorPayload,
    )

    accept_client = Stage30_11_5RecordingFakeTransportClient(
        created_at_utc="2026-01-01T00:00:00Z"
    )
    payload = Stage30_11_5PrivateOperatorPayload(
        candidate_id="c",
        token_mint="m",
        candidate_ref=None,
        tier_token="Tier 1",
        body="b",
        source_stage="30.11.5",
        created_at_utc="2026-01-01T00:00:00Z",
    )
    accepted = accept_client(payload)
    assert accepted.accepted is True
    assert accepted.transport_status == TRANSPORT_STATUS_WOULD_DELIVER

    reject_client = Stage30_11_5RecordingFakeTransportClient(
        created_at_utc="2026-01-01T00:00:00Z", reject_candidate_ids=("c",)
    )
    rejected = reject_client(payload)
    assert rejected.accepted is False
    assert rejected.transport_status == TRANSPORT_STATUS_REJECTED


def test_proof_is_deterministic_under_constant_clock() -> None:
    a, _ = run_stage30_11_5_fake_live_wiring_proof(
        now_seconds=make_constant_clock(Decimal(0))
    )
    b, _ = run_stage30_11_5_fake_live_wiring_proof(
        now_seconds=make_constant_clock(Decimal(0))
    )
    assert a.summary == b.summary

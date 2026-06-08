"""Stage 30.11.16 fake real-send proof tests.

Offline only. Proves the committed fake real-send proof driver + the recording
fake private transport: a valid authorization + a genuine deduped
``NO_SEND_DISPATCHED`` result forwards EXACTLY ONE recorded would-send through the
FAKE transport with the exact ``{"content": body}`` payload, the default
authorization sentinel is valid, and the recording fake returns a duck-typed
verdict WITHOUT any real opener / network / env.

No real send, no network, no env read, no Stage 28 import.
"""

from __future__ import annotations

from decimal import Decimal

from PHX2.stage30.stage30_11_13_committed_no_send_composer import (
    COMPOSE_DECISION_DISPATCHED,
    COMPOSE_REASON_NO_SEND_DISPATCH_RECORDED,
    Stage30_11_13ComposedSnapshot,
    Stage30_11_13ComposeResult,
    Stage30_11_13GateBindingKey,
)
from PHX2.stage30.stage30_11_15_no_send_dedupe_guard import (
    Stage30_11_15DedupedComposeResult,
)
from PHX2.stage30.stage30_11_15_ping_dedupe_models import (
    DEDUPE_REASON_NEW_KEY,
    allowed_outcome,
)
from PHX2.stage30.stage30_11_16_fake_real_send_proof import (
    Stage30_11_16FakeRealSendProofResult,
    Stage30_11_16FakeTransportVerdict,
    Stage30_11_16RecordingFakePrivateTransport,
    default_real_send_authorization,
    run_stage30_11_16_fake_real_send_proof,
)
from PHX2.stage30.stage30_11_16_real_send_models import (
    REAL_SEND_DECISION_FORWARDED_TO_TRANSPORT,
    STAGE30_11_16_PRIVATE_OPERATOR_IDENTITY,
    is_real_send_authorization,
)


_BODY: str = "[PHOENIX OPERATOR PING] body"


_CREATED_AT: str = "2026-06-07T07:06:40Z"


def _real_snapshot() -> Stage30_11_13ComposedSnapshot:
    """A real (deterministic) committed Stage 30.11.13 composed snapshot.

    The guard now isinstance-checks the snapshot for committed-type provenance
    (it must be a real ``Stage30_11_13ComposedSnapshot``, never a bare
    ``object()``). The guard reads the snapshot's TYPE only; these field values
    are a deterministic dip-shaped placeholder.
    """
    binding = Stage30_11_13GateBindingKey(
        token_mint="mint",
        tier_token="Tier 1",
        drawdown_from_ath=Decimal("85"),
        current_market_cap_usd=Decimal("9100"),
        migration_status="PRESENT",
        ath_status="PRESENT",
        post_migration_ath_verified=True,
        created_at_utc=_CREATED_AT,
    )
    return Stage30_11_13ComposedSnapshot(
        token_mint="mint",
        candidate_id="cand",
        symbol_or_name="PHX",
        created_at_utc=_CREATED_AT,
        snapshot_id="snap-1",
        tier_token="Tier 1",
        drawdown_from_ath=Decimal("85"),
        current_market_cap_usd=Decimal("9100"),
        migration_status="PRESENT",
        ath_status="PRESENT",
        market_context_status="PRESENT",
        post_migration_ath_verified=True,
        market_context_fetched_at_utc="2026-06-07T07:05:40Z",
        market_context_max_age_seconds=300,
        market_context_freshness_status="FRESH",
        current_price="0.000003053",
        ath_price="0.000028368",
        liquidity_usd="6900",
        migration_confirmed=True,
        migration_time_utc="2026-06-06T06:14:10Z",
        migration_source="anchor",
        age_display="~24h",
        basis_display="PRICE",
        market_cap_display="$9.1K",
        liquidity_display="$6.9K",
        ath_market_cap_display="$84K",
        absolute_drawdown="85",
        fractional_drop_pct="85.00%",
        tier_band_display=None,
        ath_source_stage="stage30_11_11",
        time_from_unix=None,
        time_to_unix=None,
        ohlcv_type=None,
        span_seconds=None,
        ath_source_ref="anchor",
        gate_binding_key=binding,
    )


def _dispatched_deduped(body: str = _BODY) -> Stage30_11_15DedupedComposeResult:
    """A genuine deduped ``NO_SEND_DISPATCHED`` + allowed result built from the
    committed Stage 30.11.13 result + a REAL frozen snapshot (the guard
    isinstance-checks BOTH the compose result and the snapshot for committed-type
    provenance).
    """
    compose = Stage30_11_13ComposeResult(
        decision=COMPOSE_DECISION_DISPATCHED,
        reason=COMPOSE_REASON_NO_SEND_DISPATCH_RECORDED,
        token_mint="mint",
        candidate_id="cand",
        created_at_utc=_CREATED_AT,
        snapshot=_real_snapshot(),
        dispatched_body=body,
    )
    return Stage30_11_15DedupedComposeResult(
        compose_result=compose,
        dedupe_outcome=allowed_outcome(DEDUPE_REASON_NEW_KEY),
    )


# ---------------------------------------------------------------------------
# 1. The proof forwards exactly one would-send through the fake transport
# ---------------------------------------------------------------------------


def test_proof_forwards_exactly_one_would_send() -> None:
    proof = run_stage30_11_16_fake_real_send_proof(
        deduped_result=_dispatched_deduped()
    )
    assert isinstance(proof, Stage30_11_16FakeRealSendProofResult)
    assert proof.result.decision == REAL_SEND_DECISION_FORWARDED_TO_TRANSPORT
    assert proof.transport.call_count == 1
    assert proof.guard.forwarded_call_count == 1
    # exactly the minimal payload + the private operator identity.
    assert proof.transport.calls[0]["payload"] == {"content": _BODY}
    assert proof.transport.calls[0]["webhook_identity"] == (
        STAGE30_11_16_PRIVATE_OPERATOR_IDENTITY
    )


def test_proof_uses_a_recording_fake_not_a_real_opener() -> None:
    proof = run_stage30_11_16_fake_real_send_proof(
        deduped_result=_dispatched_deduped()
    )
    assert isinstance(
        proof.transport, Stage30_11_16RecordingFakePrivateTransport
    )


# ---------------------------------------------------------------------------
# 2. The default authorization sentinel is valid
# ---------------------------------------------------------------------------


def test_default_authorization_is_valid() -> None:
    auth = default_real_send_authorization(created_at_utc="2026-06-07T07:06:40Z")
    assert is_real_send_authorization(auth)


# ---------------------------------------------------------------------------
# 3. The recording fake transport: records + returns a duck-typed verdict
# ---------------------------------------------------------------------------


def test_recording_fake_records_and_returns_verdict() -> None:
    fake = Stage30_11_16RecordingFakePrivateTransport()
    verdict = fake.send_one_audited_post(
        webhook_identity="PRIVATE_OPERATOR_WEBHOOK", payload={"content": "hi"}
    )
    assert isinstance(verdict, Stage30_11_16FakeTransportVerdict)
    assert verdict.ok is True
    assert verdict.transport_status == "SENT_OK"
    assert verdict.send_attempt_count == 1
    assert fake.call_count == 1
    assert fake.calls[0]["payload"] == {"content": "hi"}


def test_recording_fake_scripted_failure_verdict() -> None:
    fake = Stage30_11_16RecordingFakePrivateTransport(
        scripted_ok=False, scripted_transport_status="RATE_LIMITED"
    )
    verdict = fake.send_one_audited_post(
        webhook_identity="PRIVATE_OPERATOR_WEBHOOK", payload={"content": "hi"}
    )
    assert verdict.ok is False
    assert verdict.transport_status == "RATE_LIMITED"


def test_recording_fake_raise_on_send_records_then_raises() -> None:
    fake = Stage30_11_16RecordingFakePrivateTransport(raise_on_send=True)
    raised = False
    try:
        fake.send_one_audited_post(
            webhook_identity="PRIVATE_OPERATOR_WEBHOOK",
            payload={"content": "hi"},
        )
    except RuntimeError:
        raised = True
    assert raised
    # The call was recorded before the raise (proves exactly-one accounting).
    assert fake.call_count == 1


def test_proof_with_injected_fake_failure_reflects_status() -> None:
    fake = Stage30_11_16RecordingFakePrivateTransport(
        scripted_ok=False, scripted_transport_status="SERVER_ERROR"
    )
    proof = run_stage30_11_16_fake_real_send_proof(
        deduped_result=_dispatched_deduped(), transport=fake
    )
    assert proof.result.decision == REAL_SEND_DECISION_FORWARDED_TO_TRANSPORT
    assert proof.result.transport_ok is False
    assert proof.result.transport_status == "SERVER_ERROR"
    assert fake.call_count == 1

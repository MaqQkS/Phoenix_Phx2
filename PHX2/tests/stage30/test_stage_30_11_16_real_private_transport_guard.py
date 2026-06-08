"""Stage 30.11.16 real private transport guard tests.

Offline only. Proves the no-send-by-default real private transport guard:

  * missing / wrong-type / invalid authorization cannot send (transport
    untouched);
  * a non-deduped / dedupe-not-allowed / not-NO_SEND_DISPATCHED / missing-snapshot
    / missing-body result cannot send;
  * a wrong / non-private target identity cannot send;
  * the no-transport default records a would-send and burns the one-shot cap;
  * an injected fake transport forwards EXACTLY ONE ``{"content": body}`` call;
  * a second gate-passing call returns CAP_EXHAUSTED (burn-on-attempt);
  * a refused call does NOT burn the cap (a corrected retry succeeds);
  * a transport that reports a failure status is reflected, never fabricated to
    success;
  * a transport that RAISES fails closed (TRANSPORT_EXCEPTION), redacted, with the
    cap still consumed and no retry;
  * a stale-market / duplicate-dedupe upstream rejection cannot send;
  * PROVENANCE: a forged inner compose_result (or a forged snapshot) wrapped in a
    REAL deduped result with an allowed dedupe outcome cannot send -- the guard
    isinstance-checks the committed Stage 30.11.13 compose-result + composed-
    snapshot dataclasses, so a duck-typed look-alike fails closed and nothing
    reaches the transport;
  * an unsafe echoed token_mint / candidate_id is redacted to a safe placeholder,
    never echoed raw into the result record.

The deduped compose results are built from the committed Stage 30.11.13 /
30.11.15 result types directly. The guard isinstance-checks the consumed
compose_result / snapshot / dedupe_outcome against the committed Stage 30
dataclasses (only the injected transport stays duck-typed); the composer's own
tests prove the composer produces these shapes. No real send, no network, no env
read, no wallet, no trading. No Stage 28 import.
"""

from __future__ import annotations

from decimal import Decimal

from PHX2.stage30.stage30_11_13_committed_no_send_composer import (
    COMPOSE_DECISION_DISPATCHED,
    COMPOSE_DECISION_REJECTED,
    COMPOSE_REASON_NO_SEND_DISPATCH_RECORDED,
    COMPOSE_REJECTED_DEDUPE_SUPPRESSED,
    COMPOSE_REJECTED_GATE_DID_NOT_PASS,
    COMPOSE_REJECTED_MARKET_CONTEXT_STALE,
    Stage30_11_13ComposedSnapshot,
    Stage30_11_13ComposeResult,
    Stage30_11_13GateBindingKey,
)
from PHX2.stage30.stage30_11_15_no_send_dedupe_guard import (
    Stage30_11_15DedupedComposeResult,
)
from PHX2.stage30.stage30_11_15_ping_dedupe_models import (
    DEDUPE_REASON_DUPLICATE_WITHIN_TTL,
    DEDUPE_REASON_LEDGER_UNAVAILABLE,
    DEDUPE_REASON_NEW_KEY,
    allowed_outcome,
    suppressed_outcome,
    unavailable_outcome,
)
from PHX2.stage30.stage30_11_16_fake_real_send_proof import (
    Stage30_11_16RecordingFakePrivateTransport,
    default_real_send_authorization,
)
from PHX2.stage30.stage30_11_16_real_private_transport_guard import (
    make_stage30_11_16_real_private_transport_guard,
)
from PHX2.stage30.stage30_11_16_real_send_models import (
    REAL_SEND_DECISION_FORWARDED_TO_TRANSPORT,
    REAL_SEND_DECISION_REFUSED,
    REAL_SEND_DECISION_WOULD_SEND_NO_TRANSPORT,
    REAL_SEND_REASON_BODY_MISSING,
    REAL_SEND_REASON_CAP_EXHAUSTED,
    REAL_SEND_REASON_COMPOSE_NOT_DISPATCHED,
    REAL_SEND_REASON_DEDUPE_NOT_ALLOWED,
    REAL_SEND_REASON_FORWARDED_ONE_PRIVATE_OPERATOR_MESSAGE,
    REAL_SEND_REASON_INVALID_AUTHORIZATION_TYPE,
    REAL_SEND_REASON_INVALID_COMPOSE_RESULT,
    REAL_SEND_REASON_INVALID_SNAPSHOT_PROVENANCE,
    REAL_SEND_REASON_INVALID_TARGET_IDENTITY,
    REAL_SEND_REASON_NOT_AUTHORIZED,
    REAL_SEND_REASON_SNAPSHOT_MISSING,
    REAL_SEND_REASON_TRANSPORT_EXCEPTION,
    REAL_SEND_REASON_WOULD_SEND_RECORDED_NO_TRANSPORT,
    STAGE30_11_16_PRIVATE_OPERATOR_IDENTITY,
    STAGE30_11_16_PRIVATE_OPERATOR_VISIBILITY,
    STAGE30_11_16_REDACTED_UNSAFE_ID,
    STAGE30_11_16_REDACTED_UNSAFE_IDENTITY,
    Stage30_11_16TransportTarget,
)


_MINT: str = "Et9km9VRfjeeowsMR1YmjR1GhxXHBatAEVhggxYVfaNe"
_CAND: str = "stage30_11_16_cand_dip"
_CREATED_AT: str = "2026-06-07T07:06:40Z"
_NOW: str = "2026-06-07T07:06:41Z"
_BODY: str = "[PHOENIX OPERATOR PING] mint=... tier=Tier 1 drop=85% MC=$9.1K"


def _binding_key() -> Stage30_11_13GateBindingKey:
    return Stage30_11_13GateBindingKey(
        token_mint=_MINT,
        tier_token="Tier 1",
        drawdown_from_ath=Decimal("85"),
        current_market_cap_usd=Decimal("9100"),
        migration_status="PRESENT",
        ath_status="PRESENT",
        post_migration_ath_verified=True,
        created_at_utc=_CREATED_AT,
    )


def _composed_snapshot() -> Stage30_11_13ComposedSnapshot:
    """A real (deterministic) committed Stage 30.11.13 composed snapshot.

    The guard treats the snapshot opaquely (it checks existence only); this builds
    the authentic type so the guard is proven to work with the real composer
    output shape.
    """
    return Stage30_11_13ComposedSnapshot(
        token_mint=_MINT,
        candidate_id=_CAND,
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
        gate_binding_key=_binding_key(),
    )


_SNAPSHOT: Stage30_11_13ComposedSnapshot = _composed_snapshot()
_ALLOWED = allowed_outcome(DEDUPE_REASON_NEW_KEY)
_SUPPRESSED = suppressed_outcome(DEDUPE_REASON_DUPLICATE_WITHIN_TTL)
_UNAVAILABLE = unavailable_outcome(DEDUPE_REASON_LEDGER_UNAVAILABLE)
_SENTINEL = object()


def _deduped(
    *,
    decision: str = COMPOSE_DECISION_DISPATCHED,
    reason: str = COMPOSE_REASON_NO_SEND_DISPATCH_RECORDED,
    snapshot: object = _SENTINEL,
    body=_BODY,
    dedupe_outcome=_ALLOWED,
    mint: str = _MINT,
    candidate_id: str = _CAND,
) -> Stage30_11_15DedupedComposeResult:
    snap = _SNAPSHOT if snapshot is _SENTINEL else snapshot
    compose = Stage30_11_13ComposeResult(
        decision=decision,
        reason=reason,
        token_mint=mint,
        candidate_id=candidate_id,
        created_at_utc=_CREATED_AT,
        snapshot=snap,
        dispatched_body=body,
    )
    return Stage30_11_15DedupedComposeResult(
        compose_result=compose, dedupe_outcome=dedupe_outcome
    )


def _auth():
    return default_real_send_authorization(created_at_utc=_NOW)


# ---------------------------------------------------------------------------
# 1-2. Authorization gates (missing / wrong type / invalid sentinel)
# ---------------------------------------------------------------------------


def test_missing_authorization_refuses_transport_untouched() -> None:
    fake = Stage30_11_16RecordingFakePrivateTransport()
    guard = make_stage30_11_16_real_private_transport_guard(transport=fake)
    out = guard.authorize_and_dispatch(
        _deduped(), authorization=None, created_at_utc=_NOW
    )
    assert out.decision == REAL_SEND_DECISION_REFUSED
    assert out.reason == REAL_SEND_REASON_NOT_AUTHORIZED
    assert out.transport_attempted is False
    assert out.cap_consumed is False
    assert fake.call_count == 0
    assert guard.cap_consumed is False


def test_wrong_authorization_type_refuses() -> None:
    fake = Stage30_11_16RecordingFakePrivateTransport()
    guard = make_stage30_11_16_real_private_transport_guard(transport=fake)
    out = guard.authorize_and_dispatch(
        _deduped(), authorization="not-a-sentinel", created_at_utc=_NOW
    )
    assert out.decision == REAL_SEND_DECISION_REFUSED
    assert out.reason == REAL_SEND_REASON_INVALID_AUTHORIZATION_TYPE
    assert fake.call_count == 0


def test_invalid_authorization_sentinel_refuses() -> None:
    # Right type but invalid (wrong confirm token) -> NOT_AUTHORIZED.
    bad = default_real_send_authorization(created_at_utc=_NOW)
    from dataclasses import replace

    tampered = replace(bad, confirm_token="WRONG_TOKEN")
    fake = Stage30_11_16RecordingFakePrivateTransport()
    guard = make_stage30_11_16_real_private_transport_guard(transport=fake)
    out = guard.authorize_and_dispatch(
        _deduped(), authorization=tampered, created_at_utc=_NOW
    )
    assert out.reason == REAL_SEND_REASON_NOT_AUTHORIZED
    assert fake.call_count == 0


# ---------------------------------------------------------------------------
# 3-7. Consumed deduped compose result gates
# ---------------------------------------------------------------------------


def test_non_deduped_result_refuses() -> None:
    guard = make_stage30_11_16_real_private_transport_guard()
    out = guard.authorize_and_dispatch(
        "not-a-deduped-result", authorization=_auth(), created_at_utc=_NOW
    )
    assert out.reason == REAL_SEND_REASON_INVALID_COMPOSE_RESULT


def test_deduped_result_with_no_compose_result_refuses() -> None:
    guard = make_stage30_11_16_real_private_transport_guard()
    empty = Stage30_11_15DedupedComposeResult(
        compose_result=None, dedupe_outcome=_UNAVAILABLE
    )
    out = guard.authorize_and_dispatch(
        empty, authorization=_auth(), created_at_utc=_NOW
    )
    assert out.reason == REAL_SEND_REASON_INVALID_COMPOSE_RESULT


def test_dedupe_outcome_not_allowed_refuses() -> None:
    guard = make_stage30_11_16_real_private_transport_guard()
    out = guard.authorize_and_dispatch(
        _deduped(dedupe_outcome=_SUPPRESSED),
        authorization=_auth(),
        created_at_utc=_NOW,
    )
    assert out.reason == REAL_SEND_REASON_DEDUPE_NOT_ALLOWED
    # A None / unavailable dedupe outcome is equally fail-closed.
    out_none = guard.authorize_and_dispatch(
        _deduped(dedupe_outcome=None), authorization=_auth(), created_at_utc=_NOW
    )
    assert out_none.reason == REAL_SEND_REASON_DEDUPE_NOT_ALLOWED


def test_compose_not_dispatched_refuses() -> None:
    # dedupe allowed, but compose decision is not NO_SEND_DISPATCHED.
    guard = make_stage30_11_16_real_private_transport_guard()
    out = guard.authorize_and_dispatch(
        _deduped(
            decision=COMPOSE_DECISION_REJECTED,
            reason=COMPOSE_REJECTED_GATE_DID_NOT_PASS,
            dedupe_outcome=_ALLOWED,
        ),
        authorization=_auth(),
        created_at_utc=_NOW,
    )
    assert out.reason == REAL_SEND_REASON_COMPOSE_NOT_DISPATCHED


def test_missing_snapshot_refuses() -> None:
    guard = make_stage30_11_16_real_private_transport_guard()
    out = guard.authorize_and_dispatch(
        _deduped(snapshot=None), authorization=_auth(), created_at_utc=_NOW
    )
    assert out.reason == REAL_SEND_REASON_SNAPSHOT_MISSING


def test_missing_or_blank_body_refuses() -> None:
    guard = make_stage30_11_16_real_private_transport_guard()
    for body in (None, "", "   "):
        out = guard.authorize_and_dispatch(
            _deduped(body=body), authorization=_auth(), created_at_utc=_NOW
        )
        assert out.reason == REAL_SEND_REASON_BODY_MISSING
        # none of these consumed the cap.
        assert guard.cap_consumed is False


# ---------------------------------------------------------------------------
# 8. No-transport default -> WOULD_SEND_NO_TRANSPORT (consumes cap)
# ---------------------------------------------------------------------------


def test_no_transport_default_records_would_send_and_burns_cap() -> None:
    guard = make_stage30_11_16_real_private_transport_guard()  # transport=None
    out = guard.authorize_and_dispatch(
        _deduped(), authorization=_auth(), created_at_utc=_NOW
    )
    assert out.decision == REAL_SEND_DECISION_WOULD_SEND_NO_TRANSPORT
    assert out.reason == REAL_SEND_REASON_WOULD_SEND_RECORDED_NO_TRANSPORT
    assert out.dispatch_forwarded is False
    assert out.transport_attempted is False
    assert out.transport_status is None
    assert out.transport_ok is None
    assert out.cap_consumed is True
    assert out.token_mint == _MINT
    assert out.candidate_id == _CAND
    assert out.webhook_identity == STAGE30_11_16_PRIVATE_OPERATOR_IDENTITY
    assert out.redaction_status == "REDACTED"
    assert guard.cap_consumed is True


# ---------------------------------------------------------------------------
# 9-11. Injected fake transport: forwards exactly once with exact payload
# ---------------------------------------------------------------------------


def test_fake_transport_forwards_exactly_once() -> None:
    fake = Stage30_11_16RecordingFakePrivateTransport()
    guard = make_stage30_11_16_real_private_transport_guard(transport=fake)
    out = guard.authorize_and_dispatch(
        _deduped(), authorization=_auth(), created_at_utc=_NOW
    )
    assert out.decision == REAL_SEND_DECISION_FORWARDED_TO_TRANSPORT
    assert out.reason == REAL_SEND_REASON_FORWARDED_ONE_PRIVATE_OPERATOR_MESSAGE
    assert out.dispatch_forwarded is True
    assert out.transport_attempted is True
    assert out.transport_status == "SENT_OK"
    assert out.transport_ok is True
    assert out.cap_consumed is True
    assert fake.call_count == 1
    assert guard.forwarded_call_count == 1


def test_second_valid_call_returns_cap_exhausted() -> None:
    fake = Stage30_11_16RecordingFakePrivateTransport()
    guard = make_stage30_11_16_real_private_transport_guard(transport=fake)
    first = guard.authorize_and_dispatch(
        _deduped(), authorization=_auth(), created_at_utc=_NOW
    )
    assert first.decision == REAL_SEND_DECISION_FORWARDED_TO_TRANSPORT
    second = guard.authorize_and_dispatch(
        _deduped(), authorization=_auth(), created_at_utc=_NOW
    )
    assert second.decision == REAL_SEND_DECISION_REFUSED
    assert second.reason == REAL_SEND_REASON_CAP_EXHAUSTED
    assert second.cap_consumed is True
    # The cap held: exactly one forward over the guard's lifetime.
    assert fake.call_count == 1
    assert guard.forwarded_call_count == 1


def test_forwarded_payload_is_exactly_content_body() -> None:
    fake = Stage30_11_16RecordingFakePrivateTransport()
    guard = make_stage30_11_16_real_private_transport_guard(transport=fake)
    guard.authorize_and_dispatch(
        _deduped(body="[EXACT BODY]"),
        authorization=_auth(),
        created_at_utc=_NOW,
    )
    assert fake.calls[0]["payload"] == {"content": "[EXACT BODY]"}
    assert fake.calls[0]["webhook_identity"] == (
        STAGE30_11_16_PRIVATE_OPERATOR_IDENTITY
    )


def test_refusal_does_not_burn_cap_then_retry_succeeds() -> None:
    fake = Stage30_11_16RecordingFakePrivateTransport()
    guard = make_stage30_11_16_real_private_transport_guard(transport=fake)
    refused = guard.authorize_and_dispatch(
        _deduped(), authorization=None, created_at_utc=_NOW
    )
    assert refused.reason == REAL_SEND_REASON_NOT_AUTHORIZED
    assert guard.cap_consumed is False
    # A corrected, authorized retry succeeds (the refusal did not burn the cap).
    ok = guard.authorize_and_dispatch(
        _deduped(), authorization=_auth(), created_at_utc=_NOW
    )
    assert ok.decision == REAL_SEND_DECISION_FORWARDED_TO_TRANSPORT
    assert fake.call_count == 1


# ---------------------------------------------------------------------------
# 12. Wrong / non-private target identity refuses
# ---------------------------------------------------------------------------


def test_wrong_target_identity_refuses() -> None:
    bad_target = Stage30_11_16TransportTarget(
        webhook_identity="PUBLIC_BROADCAST",
        visibility=STAGE30_11_16_PRIVATE_OPERATOR_VISIBILITY,
    )
    fake = Stage30_11_16RecordingFakePrivateTransport()
    guard = make_stage30_11_16_real_private_transport_guard(
        transport=fake, target=bad_target
    )
    out = guard.authorize_and_dispatch(
        _deduped(), authorization=_auth(), created_at_utc=_NOW
    )
    assert out.reason == REAL_SEND_REASON_INVALID_TARGET_IDENTITY
    assert fake.call_count == 0
    assert guard.cap_consumed is False


def test_wrong_target_visibility_refuses() -> None:
    bad_target = Stage30_11_16TransportTarget(
        webhook_identity=STAGE30_11_16_PRIVATE_OPERATOR_IDENTITY,
        visibility="PUBLIC",
    )
    guard = make_stage30_11_16_real_private_transport_guard(target=bad_target)
    out = guard.authorize_and_dispatch(
        _deduped(), authorization=_auth(), created_at_utc=_NOW
    )
    assert out.reason == REAL_SEND_REASON_INVALID_TARGET_IDENTITY


def test_unsafe_target_identity_is_redacted_in_result_echo() -> None:
    bad_target = Stage30_11_16TransportTarget(
        webhook_identity="bad/identity",  # url-shaped / slashed -> unsafe
        visibility=STAGE30_11_16_PRIVATE_OPERATOR_VISIBILITY,
    )
    guard = make_stage30_11_16_real_private_transport_guard(target=bad_target)
    out = guard.authorize_and_dispatch(
        _deduped(), authorization=_auth(), created_at_utc=_NOW
    )
    assert out.reason == REAL_SEND_REASON_INVALID_TARGET_IDENTITY
    assert out.webhook_identity == STAGE30_11_16_REDACTED_UNSAFE_IDENTITY
    assert "bad/identity" not in repr(out)


# ---------------------------------------------------------------------------
# 13. A transport failure status is reflected, never fabricated to success
# ---------------------------------------------------------------------------


def test_transport_failure_status_is_reflected_not_success() -> None:
    fake = Stage30_11_16RecordingFakePrivateTransport(
        scripted_ok=False, scripted_transport_status="VALIDATION_FAILED"
    )
    guard = make_stage30_11_16_real_private_transport_guard(transport=fake)
    out = guard.authorize_and_dispatch(
        _deduped(), authorization=_auth(), created_at_utc=_NOW
    )
    # The guard forwarded exactly one POST; it reports the transport's verdict
    # verbatim and never fabricates success.
    assert out.decision == REAL_SEND_DECISION_FORWARDED_TO_TRANSPORT
    assert out.transport_ok is False
    assert out.transport_status == "VALIDATION_FAILED"
    assert fake.call_count == 1


def test_transport_odd_return_maps_to_none_not_success() -> None:
    class _OddTransport:
        def send_one_audited_post(self, *, webhook_identity, payload):
            return "not-a-verdict"

    guard = make_stage30_11_16_real_private_transport_guard(
        transport=_OddTransport()
    )
    out = guard.authorize_and_dispatch(
        _deduped(), authorization=_auth(), created_at_utc=_NOW
    )
    assert out.decision == REAL_SEND_DECISION_FORWARDED_TO_TRANSPORT
    assert out.transport_ok is None
    assert out.transport_status is None


# ---------------------------------------------------------------------------
# 14. Transport exception -> fail closed, redacted, cap consumed, no retry
# ---------------------------------------------------------------------------


def test_transport_exception_fails_closed_redacted_cap_consumed() -> None:
    fake = Stage30_11_16RecordingFakePrivateTransport(raise_on_send=True)
    guard = make_stage30_11_16_real_private_transport_guard(transport=fake)
    out = guard.authorize_and_dispatch(
        _deduped(), authorization=_auth(), created_at_utc=_NOW
    )
    assert out.decision == REAL_SEND_DECISION_REFUSED
    assert out.reason == REAL_SEND_REASON_TRANSPORT_EXCEPTION
    assert out.dispatch_forwarded is False
    assert out.transport_attempted is True
    assert out.transport_status is None
    assert out.transport_ok is None
    assert out.cap_consumed is True
    # Redacted: no exception text / type leaks into the result.
    text = repr(out)
    assert "scripted failure" not in text
    assert "RuntimeError" not in text
    assert "boom" not in text
    # The cap remains consumed: the same guard never retries.
    assert guard.cap_consumed is True
    second = guard.authorize_and_dispatch(
        _deduped(), authorization=_auth(), created_at_utc=_NOW
    )
    assert second.reason == REAL_SEND_REASON_CAP_EXHAUSTED
    assert fake.call_count == 1  # recorded once, raised, never retried


# ---------------------------------------------------------------------------
# 15-16. Upstream stale-market / duplicate-dedupe rejections cannot send
# ---------------------------------------------------------------------------


def test_stale_market_compose_rejection_cannot_send() -> None:
    # A stale market context rejects in the composer BEFORE the dedupe guard
    # runs, so the deduped result carries a REJECTED compose + a None dedupe
    # outcome. The guard fails closed (no clean allowed dedupe outcome).
    fake = Stage30_11_16RecordingFakePrivateTransport()
    guard = make_stage30_11_16_real_private_transport_guard(transport=fake)
    out = guard.authorize_and_dispatch(
        _deduped(
            decision=COMPOSE_DECISION_REJECTED,
            reason=COMPOSE_REJECTED_MARKET_CONTEXT_STALE,
            snapshot=None,
            body=None,
            dedupe_outcome=None,
        ),
        authorization=_auth(),
        created_at_utc=_NOW,
    )
    assert out.decision == REAL_SEND_DECISION_REFUSED
    assert out.reason == REAL_SEND_REASON_DEDUPE_NOT_ALLOWED
    assert fake.call_count == 0


def test_duplicate_dedupe_suppressed_result_cannot_send() -> None:
    # A duplicate within TTL: the orchestrator rejects the compose with the
    # dedupe-suppressed reason and a SUPPRESSED dedupe outcome. The guard refuses.
    fake = Stage30_11_16RecordingFakePrivateTransport()
    guard = make_stage30_11_16_real_private_transport_guard(transport=fake)
    out = guard.authorize_and_dispatch(
        _deduped(
            decision=COMPOSE_DECISION_REJECTED,
            reason=COMPOSE_REJECTED_DEDUPE_SUPPRESSED,
            dedupe_outcome=_SUPPRESSED,
        ),
        authorization=_auth(),
        created_at_utc=_NOW,
    )
    assert out.decision == REAL_SEND_DECISION_REFUSED
    assert out.reason == REAL_SEND_REASON_DEDUPE_NOT_ALLOWED
    assert fake.call_count == 0


# ---------------------------------------------------------------------------
# 17. The forwarded result never echoes the body
# ---------------------------------------------------------------------------


def test_result_never_echoes_the_body() -> None:
    fake = Stage30_11_16RecordingFakePrivateTransport()
    guard = make_stage30_11_16_real_private_transport_guard(transport=fake)
    out = guard.authorize_and_dispatch(
        _deduped(body="[SECRET-LOOKING BODY ZZZ]"),
        authorization=_auth(),
        created_at_utc=_NOW,
    )
    assert out.decision == REAL_SEND_DECISION_FORWARDED_TO_TRANSPORT
    assert "ZZZ" not in repr(out)


# ---------------------------------------------------------------------------
# 18. PROVENANCE: a forged inner object wrapped in a REAL deduped result cannot
#     be forwarded (the guard isinstance-checks the committed Stage 30.11.13
#     compose-result + composed-snapshot dataclasses, not duck-typed look-alikes)
# ---------------------------------------------------------------------------


class _ForgedComposeResult:
    """A duck-typed look-alike that spoofs EVERY attribute the guard previously
    duck-read (decision / snapshot / dispatched_body / token_mint / candidate_id)
    -- but is NOT a real committed Stage 30.11.13 ``Stage30_11_13ComposeResult``.
    Wrapping it in a genuine ``Stage30_11_15DedupedComposeResult`` with an allowed
    dedupe outcome is the exact bypass Codex flagged.
    """

    def __init__(self) -> None:
        self.decision = COMPOSE_DECISION_DISPATCHED
        self.reason = COMPOSE_REASON_NO_SEND_DISPATCH_RECORDED
        self.token_mint = _MINT
        self.candidate_id = _CAND
        self.created_at_utc = _CREATED_AT
        self.snapshot = object()
        self.dispatched_body = "[FORGED BODY]"


def test_forged_inner_compose_result_in_real_wrapper_refuses() -> None:
    # A REAL Stage30_11_15DedupedComposeResult + an allowed dedupe outcome, but a
    # FORGED inner compose_result. The compose-result provenance gate fails closed
    # BEFORE the snapshot / body / payload are ever looked at -- nothing is
    # forwarded, the cap is untouched, and the forged body never reaches the
    # transport or the result record.
    forged = _ForgedComposeResult()
    deduped = Stage30_11_15DedupedComposeResult(
        compose_result=forged, dedupe_outcome=_ALLOWED
    )
    fake = Stage30_11_16RecordingFakePrivateTransport()
    guard = make_stage30_11_16_real_private_transport_guard(transport=fake)
    out = guard.authorize_and_dispatch(
        deduped, authorization=_auth(), created_at_utc=_NOW
    )
    assert out.decision == REAL_SEND_DECISION_REFUSED
    assert out.reason == REAL_SEND_REASON_INVALID_COMPOSE_RESULT
    assert out.transport_attempted is False
    assert out.dispatch_forwarded is False
    assert out.cap_consumed is False
    assert fake.call_count == 0
    assert guard.forwarded_call_count == 0
    assert guard.cap_consumed is False
    # The forged body / forged-snapshot marker never enters the result record.
    assert "[FORGED BODY]" not in repr(out)


def test_real_compose_result_with_forged_snapshot_refuses() -> None:
    # A REAL Stage30_11_13ComposeResult (so the compose-result provenance gate
    # passes) carrying a PRESENT but FORGED, wrong-type snapshot. The snapshot
    # provenance gate fails closed -- distinct from SNAPSHOT_MISSING (absent) --
    # and nothing is forwarded.
    compose = Stage30_11_13ComposeResult(
        decision=COMPOSE_DECISION_DISPATCHED,
        reason=COMPOSE_REASON_NO_SEND_DISPATCH_RECORDED,
        token_mint=_MINT,
        candidate_id=_CAND,
        created_at_utc=_CREATED_AT,
        snapshot=object(),  # present but NOT a real Stage30_11_13ComposedSnapshot
        dispatched_body=_BODY,
    )
    deduped = Stage30_11_15DedupedComposeResult(
        compose_result=compose, dedupe_outcome=_ALLOWED
    )
    fake = Stage30_11_16RecordingFakePrivateTransport()
    guard = make_stage30_11_16_real_private_transport_guard(transport=fake)
    out = guard.authorize_and_dispatch(
        deduped, authorization=_auth(), created_at_utc=_NOW
    )
    assert out.decision == REAL_SEND_DECISION_REFUSED
    assert out.reason == REAL_SEND_REASON_INVALID_SNAPSHOT_PROVENANCE
    assert out.transport_attempted is False
    assert out.dispatch_forwarded is False
    assert out.cap_consumed is False
    assert fake.call_count == 0
    assert guard.cap_consumed is False


def test_valid_real_compose_result_and_snapshot_still_forwards() -> None:
    # The happy path is preserved by the provenance gates: a genuine real Stage
    # 30.11.13 compose result with a real frozen snapshot + an allowed dedupe
    # outcome forwards EXACTLY ONE {"content": body} call under the fake transport.
    fake = Stage30_11_16RecordingFakePrivateTransport()
    guard = make_stage30_11_16_real_private_transport_guard(transport=fake)
    out = guard.authorize_and_dispatch(
        _deduped(), authorization=_auth(), created_at_utc=_NOW
    )
    assert out.decision == REAL_SEND_DECISION_FORWARDED_TO_TRANSPORT
    assert out.dispatch_forwarded is True
    assert out.cap_consumed is True
    assert fake.call_count == 1
    assert guard.forwarded_call_count == 1


# ---------------------------------------------------------------------------
# 19. Unsafe echoed ids are sanitized to a redacted placeholder (never raw)
# ---------------------------------------------------------------------------


def test_unsafe_token_mint_is_redacted_not_echoed_raw() -> None:
    # A token mint carrying a newline / injected content is redacted in the
    # result echo; the gate still passes (the guard re-derives no upstream
    # validation -- it only refuses to echo an unsafe id raw).
    unsafe_mint = "mint\n[INJECTED CONTENT]"
    guard = make_stage30_11_16_real_private_transport_guard()  # transport=None
    out = guard.authorize_and_dispatch(
        _deduped(mint=unsafe_mint), authorization=_auth(), created_at_utc=_NOW
    )
    assert out.decision == REAL_SEND_DECISION_WOULD_SEND_NO_TRANSPORT
    assert out.token_mint == STAGE30_11_16_REDACTED_UNSAFE_ID
    assert out.token_mint != unsafe_mint
    assert "\n" not in out.token_mint
    assert "[INJECTED CONTENT]" not in repr(out)


def test_unsafe_candidate_id_is_redacted_not_echoed_raw() -> None:
    unsafe_cand = "cand id/with spaces & ../traversal"
    guard = make_stage30_11_16_real_private_transport_guard()  # transport=None
    out = guard.authorize_and_dispatch(
        _deduped(candidate_id=unsafe_cand),
        authorization=_auth(),
        created_at_utc=_NOW,
    )
    assert out.decision == REAL_SEND_DECISION_WOULD_SEND_NO_TRANSPORT
    assert out.candidate_id == STAGE30_11_16_REDACTED_UNSAFE_ID
    assert " " not in out.candidate_id
    assert "../" not in repr(out)


def test_safe_real_ids_still_echoed_verbatim() -> None:
    # A base58 mint + an underscore candidate id are safe-echo ids: echoed as-is.
    guard = make_stage30_11_16_real_private_transport_guard()  # transport=None
    out = guard.authorize_and_dispatch(
        _deduped(), authorization=_auth(), created_at_utc=_NOW
    )
    assert out.token_mint == _MINT
    assert out.candidate_id == _CAND

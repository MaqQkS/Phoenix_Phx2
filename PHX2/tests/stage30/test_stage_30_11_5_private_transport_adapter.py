"""Stage 30.11.5 private transport adapter tests.

Proves the transport adapter conforms to the committed Stage 30.11.3 sink
transport protocol (request -> result) by rendering a SAFE private operator
payload from a sink request and handing it to an INJECTED fake transport client:
a well-shaped request whose payload the fake client accepts maps to
``PRIVATE_SINK_ACCEPTED`` (a recorded would-deliver), a rejected payload maps to
``PRIVATE_SINK_TRANSPORT_FAILED``, and an invalid request fails closed to
``PRIVATE_SINK_REJECTED_INVALID_INPUT`` WITHOUT calling the client. Proves the
rendered payload carries only safe scalars + the 30.11.5 source stage, the
builder raises on a wrong record type, and the adapter plugs directly into the
committed Stage 30.11.3 private dispatch sink factory.

Fake / offline only. No live call, no provider, no Discord, no env read, no real
transport.
"""

from __future__ import annotations

import pytest

from PHX2.stage30.stage30_9_3_dip_filtered_live_gate_models import (
    Stage30_9_3LiveGateInput,
)
from PHX2.stage30.stage30_11_3_private_sink_adapter import (
    make_stage30_11_private_dispatch_sink,
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
from PHX2.stage30.stage30_11_5_fake_live_wiring_proof import (
    Stage30_11_5RecordingFakeTransportClient,
)
from PHX2.stage30.stage30_11_5_live_wiring_models import (
    STAGE30_11_5_SOURCE_STAGE,
    STAGE30_11_5_TRANSPORT_ACCEPT_STATUS,
    TRANSPORT_STATUS_REJECTED,
    Stage30_11_5PrivateOperatorPayload,
    Stage30_11_5TransportClientResult,
)
from PHX2.stage30.stage30_11_5_private_transport_adapter import (
    Stage30_11_5PrivateTransportAdapterError,
    build_private_operator_payload,
    make_stage30_11_5_private_transport_adapter,
)


_CREATED_AT = "2026-01-01T00:00:00Z"


def _request(
    *, candidate_id: str = "cand-x", token_mint: str = "mint-x", **overrides
):
    base = dict(
        candidate_id=candidate_id,
        token_mint=token_mint,
        candidate_ref="ref-" + candidate_id,
        tier_token="Tier 1",
        compact_body="[BODY] candidate=" + candidate_id,
        created_at_utc=_CREATED_AT,
        source_stage=STAGE30_11_3_SOURCE_STAGE,
    )
    base.update(overrides)
    return Stage30_11PrivateSinkRequest(**base)


class _ScriptedClient:
    """A configurable fake transport client: records calls, then either raises a
    pre-set exception or returns a pre-set ``Stage30_11_5TransportClientResult``.
    Used to drive the fail-closed / mismatched-result paths. Sends nothing, reads
    no env, opens no network.
    """

    def __init__(self, *, result=None, raises=None) -> None:
        self.calls = 0
        self._result = result
        self._raises = raises

    def __call__(self, payload):
        self.calls += 1
        if self._raises is not None:
            raise self._raises
        return self._result


def _client_result(
    *, accepted=True, status=None, candidate_id="cand-x", token_mint="mint-x"
):
    return Stage30_11_5TransportClientResult(
        accepted=accepted,
        transport_status=(
            STAGE30_11_5_TRANSPORT_ACCEPT_STATUS if status is None else status
        ),
        candidate_id=candidate_id,
        token_mint=token_mint,
        created_at_utc=_CREATED_AT,
    )


def _gate_input(*, candidate_id: str = "cand-x", token_mint: str = "mint-x"):
    return Stage30_9_3LiveGateInput(
        candidate_id=candidate_id,
        token_mint=token_mint,
        tier_token="Tier 1",
        drawdown_from_ath=None,
        migration_status="PRESENT",
        ath_status="PRESENT",
        market_context_status="PRESENT",
        current_market_cap_usd=None,
        post_migration_ath_verified=True,
        candidate_ref="ref-" + candidate_id,
        created_at_utc=_CREATED_AT,
    )


# ---------------------------------------------------------------------------
# Payload rendering
# ---------------------------------------------------------------------------


def test_build_payload_renders_safe_fields() -> None:
    payload = build_private_operator_payload(
        _request(), created_at_utc=_CREATED_AT
    )
    assert isinstance(payload, Stage30_11_5PrivateOperatorPayload)
    assert payload.candidate_id == "cand-x"
    assert payload.token_mint == "mint-x"
    assert payload.candidate_ref == "ref-cand-x"
    assert payload.tier_token == "Tier 1"
    assert payload.body == "[BODY] candidate=cand-x"
    assert payload.source_stage == STAGE30_11_5_SOURCE_STAGE == "30.11.5"
    assert payload.created_at_utc == _CREATED_AT


def test_build_payload_raises_on_wrong_record_type() -> None:
    with pytest.raises(Stage30_11_5PrivateTransportAdapterError):
        build_private_operator_payload(object(), created_at_utc=_CREATED_AT)
    with pytest.raises(Stage30_11_5PrivateTransportAdapterError):
        build_private_operator_payload(None, created_at_utc=_CREATED_AT)


# ---------------------------------------------------------------------------
# Adapter accept / reject / invalid
# ---------------------------------------------------------------------------


def test_adapter_accept_maps_to_private_sink_accepted() -> None:
    client = Stage30_11_5RecordingFakeTransportClient(created_at_utc=_CREATED_AT)
    adapter = make_stage30_11_5_private_transport_adapter(
        transport_client=client, created_at_utc=_CREATED_AT
    )
    result = adapter(_request(candidate_id="cand-ok", token_mint="mint-ok"))
    assert isinstance(result, Stage30_11PrivateSinkResult)
    assert result.sink_decision == PRIVATE_SINK_DECISION_ACCEPTED
    assert result.sink_reason == (
        PRIVATE_SINK_REASON_WOULD_SEND_PRIVATE_OPERATOR_MESSAGE
    )
    assert result.transport_attempted is True
    assert result.transport_accepted is True
    assert result.candidate_id == "cand-ok"
    # The client was reached exactly once, with the request's ids + body.
    assert client.attempted == 1
    assert client.accepted == 1
    assert client.candidate_ids == ["cand-ok"]
    assert client.token_mints == ["mint-ok"]
    assert client.bodies == ["[BODY] candidate=cand-ok"]


def test_adapter_reject_maps_to_transport_failed() -> None:
    client = Stage30_11_5RecordingFakeTransportClient(
        created_at_utc=_CREATED_AT, reject_candidate_ids=("cand-no",)
    )
    adapter = make_stage30_11_5_private_transport_adapter(
        transport_client=client, created_at_utc=_CREATED_AT
    )
    result = adapter(_request(candidate_id="cand-no", token_mint="mint-no"))
    assert result.sink_decision == PRIVATE_SINK_DECISION_TRANSPORT_FAILED
    assert result.sink_reason == PRIVATE_SINK_REASON_FAKE_TRANSPORT_REJECTED
    assert result.transport_attempted is True
    assert result.transport_accepted is False
    # The client WAS reached (it is the one that rejected).
    assert client.attempted == 1
    assert client.rejected == 1


def test_adapter_invalid_request_fails_closed_without_calling_client() -> None:
    client = Stage30_11_5RecordingFakeTransportClient(created_at_utc=_CREATED_AT)
    adapter = make_stage30_11_5_private_transport_adapter(
        transport_client=client, created_at_utc=_CREATED_AT
    )
    # A wrong record type.
    result = adapter(object())  # type: ignore[arg-type]
    assert result.sink_decision == PRIVATE_SINK_DECISION_REJECTED_INVALID_INPUT
    assert result.sink_reason == PRIVATE_SINK_REASON_INVALID_SINK_INPUT
    assert result.transport_attempted is False
    assert result.transport_accepted is False
    # A blank-id request.
    blank = adapter(_request(candidate_id="   "))
    assert blank.sink_decision == PRIVATE_SINK_DECISION_REJECTED_INVALID_INPUT
    assert blank.transport_attempted is False
    # The client was NEVER reached.
    assert client.attempted == 0


def test_adapter_odd_client_return_is_clean_transport_failed() -> None:
    def _odd_client(payload):
        return "not-a-result"

    adapter = make_stage30_11_5_private_transport_adapter(
        transport_client=_odd_client, created_at_utc=_CREATED_AT
    )
    result = adapter(_request())
    assert result.sink_decision == PRIVATE_SINK_DECISION_TRANSPORT_FAILED
    assert result.transport_attempted is True
    assert result.transport_accepted is False


# ---------------------------------------------------------------------------
# Protocol conformance: plugs into the committed Stage 30.11.3 sink factory
# ---------------------------------------------------------------------------


def test_adapter_plugs_into_committed_private_dispatch_sink() -> None:
    # The adapter IS a Stage 30.11.3 transport: the committed private sink factory
    # injects it as ``transport`` and the whole sink reaches the fake client for a
    # PASS gate input.
    client = Stage30_11_5RecordingFakeTransportClient(created_at_utc=_CREATED_AT)
    adapter = make_stage30_11_5_private_transport_adapter(
        transport_client=client, created_at_utc=_CREATED_AT
    )
    sink = make_stage30_11_private_dispatch_sink(
        transport=adapter, created_at_utc=_CREATED_AT
    )
    result = sink(_gate_input(candidate_id="cand-dip", token_mint="mint-dip"))
    assert result.sink_decision == PRIVATE_SINK_DECISION_ACCEPTED
    assert result.transport_accepted is True
    assert client.candidate_ids == ["cand-dip"]
    assert client.token_mints == ["mint-dip"]


# ---------------------------------------------------------------------------
# Hardening: client exceptions fail closed (Codex Issue 1)
# ---------------------------------------------------------------------------


def test_client_exception_fails_closed() -> None:
    client = _ScriptedClient(raises=RuntimeError("boom-might-carry-a-secret"))
    adapter = make_stage30_11_5_private_transport_adapter(
        transport_client=client, created_at_utc=_CREATED_AT
    )
    # No exception escapes -- the adapter returns a clean transport-failed.
    result = adapter(_request())
    assert result.sink_decision == PRIVATE_SINK_DECISION_TRANSPORT_FAILED
    assert result.sink_reason == PRIVATE_SINK_REASON_FAKE_TRANSPORT_REJECTED
    assert result.transport_attempted is True
    assert result.transport_accepted is False
    # The client WAS reached (the failure happened inside it).
    assert client.calls == 1


def test_client_exception_text_is_not_leaked_into_result() -> None:
    secret = "PHX2-PRIVATE-TRANSPORT-SECRET-XYZ"
    client = _ScriptedClient(raises=RuntimeError(secret))
    adapter = make_stage30_11_5_private_transport_adapter(
        transport_client=client, created_at_utc=_CREATED_AT
    )
    result = adapter(_request())
    # The fail-closed result carries only safe scalars; no exception text.
    for value in (
        result.sink_decision,
        result.sink_reason,
        result.candidate_id,
        result.token_mint,
        result.created_at_utc,
    ):
        assert secret not in str(value)


# ---------------------------------------------------------------------------
# Hardening: accepted client result must confirm status + identity (Issue 2)
# ---------------------------------------------------------------------------


def test_accepted_true_with_rejected_status_fails_closed() -> None:
    client = _ScriptedClient(
        result=_client_result(accepted=True, status=TRANSPORT_STATUS_REJECTED)
    )
    adapter = make_stage30_11_5_private_transport_adapter(
        transport_client=client, created_at_utc=_CREATED_AT
    )
    result = adapter(_request())
    assert result.sink_decision == PRIVATE_SINK_DECISION_TRANSPORT_FAILED
    assert result.transport_accepted is False


def test_accepted_true_with_mismatched_candidate_id_fails_closed() -> None:
    client = _ScriptedClient(
        result=_client_result(accepted=True, candidate_id="OTHER")
    )
    adapter = make_stage30_11_5_private_transport_adapter(
        transport_client=client, created_at_utc=_CREATED_AT
    )
    result = adapter(_request(candidate_id="cand-x"))
    assert result.sink_decision == PRIVATE_SINK_DECISION_TRANSPORT_FAILED
    assert result.transport_accepted is False


def test_accepted_true_with_mismatched_token_mint_fails_closed() -> None:
    client = _ScriptedClient(
        result=_client_result(accepted=True, token_mint="OTHER-MINT")
    )
    adapter = make_stage30_11_5_private_transport_adapter(
        transport_client=client, created_at_utc=_CREATED_AT
    )
    result = adapter(_request(token_mint="mint-x"))
    assert result.sink_decision == PRIVATE_SINK_DECISION_TRANSPORT_FAILED
    assert result.transport_accepted is False


def test_accepted_truthy_but_not_true_fails_closed() -> None:
    # ``accepted`` must be exactly ``True`` -- a truthy non-bool does not accept.
    client = _ScriptedClient(
        result=_client_result(accepted=1)  # type: ignore[arg-type]
    )
    adapter = make_stage30_11_5_private_transport_adapter(
        transport_client=client, created_at_utc=_CREATED_AT
    )
    result = adapter(_request())
    assert result.sink_decision == PRIVATE_SINK_DECISION_TRANSPORT_FAILED


def test_confirmed_would_deliver_for_same_candidate_is_accepted() -> None:
    # The valid accept path still passes: accepted is True, the closed accept
    # status, and the SAME candidate id / token mint.
    client = _ScriptedClient(
        result=_client_result(
            accepted=True,
            status=STAGE30_11_5_TRANSPORT_ACCEPT_STATUS,
            candidate_id="cand-x",
            token_mint="mint-x",
        )
    )
    adapter = make_stage30_11_5_private_transport_adapter(
        transport_client=client, created_at_utc=_CREATED_AT
    )
    result = adapter(_request(candidate_id="cand-x", token_mint="mint-x"))
    assert result.sink_decision == PRIVATE_SINK_DECISION_ACCEPTED
    assert result.sink_reason == (
        PRIVATE_SINK_REASON_WOULD_SEND_PRIVATE_OPERATOR_MESSAGE
    )
    assert result.transport_attempted is True
    assert result.transport_accepted is True
    assert client.calls == 1


# ---------------------------------------------------------------------------
# Hardening: malformed required request fields fail before the client (Issue 3)
# ---------------------------------------------------------------------------


def test_blank_compact_body_fails_closed_before_client() -> None:
    client = _ScriptedClient(result=_client_result())
    adapter = make_stage30_11_5_private_transport_adapter(
        transport_client=client, created_at_utc=_CREATED_AT
    )
    for bad_body in ("", "   ", None, 123):
        result = adapter(_request(compact_body=bad_body))
        assert result.sink_decision == (
            PRIVATE_SINK_DECISION_REJECTED_INVALID_INPUT
        ), f"compact_body {bad_body!r} must be invalid"
        assert result.transport_attempted is False
        assert result.transport_accepted is False
    # The client was NEVER reached for any malformed body.
    assert client.calls == 0


def test_blank_created_at_fails_closed_before_client() -> None:
    client = _ScriptedClient(result=_client_result())
    adapter = make_stage30_11_5_private_transport_adapter(
        transport_client=client, created_at_utc=_CREATED_AT
    )
    result = adapter(_request(created_at_utc="   "))
    assert result.sink_decision == PRIVATE_SINK_DECISION_REJECTED_INVALID_INPUT
    assert result.transport_attempted is False
    assert client.calls == 0


def test_wrong_source_stage_fails_closed_before_client() -> None:
    client = _ScriptedClient(result=_client_result())
    adapter = make_stage30_11_5_private_transport_adapter(
        transport_client=client, created_at_utc=_CREATED_AT
    )
    # A request whose source stage is not the committed Stage 30.11.3 producer.
    for bad_source in ("30.11.5", "", "spoofed", None):
        result = adapter(_request(source_stage=bad_source))
        assert result.sink_decision == (
            PRIVATE_SINK_DECISION_REJECTED_INVALID_INPUT
        ), f"source_stage {bad_source!r} must be invalid"
        assert result.transport_attempted is False
    assert client.calls == 0


def test_wrong_typed_optional_fields_fail_closed_before_client() -> None:
    client = _ScriptedClient(result=_client_result())
    adapter = make_stage30_11_5_private_transport_adapter(
        transport_client=client, created_at_utc=_CREATED_AT
    )
    # candidate_ref / tier_token are Optional[str]: None is fine, a wrong type is
    # malformed.
    for field, bad in (
        ("candidate_ref", 999),
        ("tier_token", ["Tier 1"]),
    ):
        result = adapter(_request(**{field: bad}))
        assert result.sink_decision == (
            PRIVATE_SINK_DECISION_REJECTED_INVALID_INPUT
        ), f"{field} {bad!r} must be invalid"
        assert result.transport_attempted is False
    assert client.calls == 0


def test_none_optional_fields_are_accepted() -> None:
    # None candidate_ref / tier_token are valid (the Optional[str] contract).
    client = _ScriptedClient(result=_client_result())
    adapter = make_stage30_11_5_private_transport_adapter(
        transport_client=client, created_at_utc=_CREATED_AT
    )
    result = adapter(_request(candidate_ref=None, tier_token=None))
    assert result.sink_decision == PRIVATE_SINK_DECISION_ACCEPTED
    assert client.calls == 1

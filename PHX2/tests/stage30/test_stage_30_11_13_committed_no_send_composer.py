"""Stage 30.11.13 committed end-to-end no-send composer tests.

Offline / fake-provider only. Proves the committed composer binds the gate
decision and the PHOENIX body to ONE immutable revalidation snapshot, hard-
wires the Stage 30.11.11 migration-anchored ATH source, computes the ATH
market cap in committed code (fail closed when it cannot), and dispatches ONLY
through the committed Stage 30.11.5 recording FAKE transport -- no real send.

The stage29-shaped fake Birdeye transport lives HERE (a test may build a
provider fake); the committed Stage 30.11.13 proof is transport-agnostic and
imports no Stage 29 module.
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from decimal import Decimal
from typing import Mapping, Optional

import pytest

from PHX2.stage29.birdeye_constants import (
    BIRDEYE_PATH_OHLCV,
    BIRDEYE_PATH_PRICE,
)
from PHX2.stage29.stage29_2_birdeye_http_transport import (
    Stage29_2BirdeyeHttpResult,
    Stage29_2BirdeyeHttpTransport,
)
from PHX2.stage29.stage29_2_birdeye_models import (
    BIRDEYE_REFUSAL_REASON_HTTP_TIMEOUT,
    BIRDEYE_REFUSAL_REASON_NONE,
)
from PHX2.stage29.stage29_2_birdeye_readiness import (
    Stage29_2BirdeyeEndpointSecret,
)
from PHX2.stage30.stage30_11_13_committed_no_send_composer import (
    COMPOSE_DECISION_DISPATCHED,
    COMPOSE_DECISION_REJECTED,
    COMPOSE_REASON_NO_SEND_DISPATCH_RECORDED,
    COMPOSE_REJECTED_ATH_NOT_RESOLVED,
    COMPOSE_REJECTED_GATE_BODY_MISMATCH,
    COMPOSE_REJECTED_INVALID_REQUEST,
    COMPOSE_REJECTED_NON_FAKE_TRANSPORT,
    STAGE30_11_13_ATH_SOURCE_STAGE,
    Stage30_11_13ComposerError,
    compose_no_send_dispatch,
    make_snapshot_bound_body_builder,
)
from PHX2.stage30.stage30_11_13_fake_composer_proof import (
    PROOF_CREATED_AT,
    PROOF_CURRENT_PRICE,
    PROOF_LATER_LOWER,
    PROOF_MIGRATION_ANCHOR,
    PROOF_MINT,
    PROOF_PEAK_ATH,
    default_proof_request,
    run_stage30_11_13_fake_composer_proof,
)
from PHX2.stage30.stage30_11_2_fake_runtime_gate_proof import (
    make_constant_clock,
)
from PHX2.stage30.stage30_11_5_fake_live_wiring_proof import (
    Stage30_11_5RecordingFakeTransportClient,
)


_GOOD_KEY: str = "abcd1234efgh5678ijkl9012mnop3456"
_GOOD_URL: str = "https://aaaa-bbbb.example"
_FETCHED_AT: str = "2026-06-07T07:06:40+00:00"


def _now_utc() -> datetime:
    return datetime(2026, 6, 7, 7, 6, 40, tzinfo=timezone.utc)


def _unix(iso: str) -> int:
    return int(datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp())


def _price_body() -> dict:
    return {
        "success": True,
        "data": {
            "value": PROOF_CURRENT_PRICE,
            "updateUnixTime": int(_now_utc().timestamp()),
        },
    }


def _ohlcv_body_with_peak() -> dict:
    return {
        "success": True,
        "data": {
            "items": [
                {"h": PROOF_PEAK_ATH, "unixTime": _unix("2026-06-06T06:15:00Z")},
                {"h": PROOF_LATER_LOWER, "unixTime": _unix("2026-06-06T07:30:00Z")},
            ]
        },
    }


class FakeComposerBirdeyeTransport(Stage29_2BirdeyeHttpTransport):
    """Path-routed fake Birdeye transport: ``/defi/price`` -> the price body,
    ``/defi/ohlcv`` -> the anchored OHLCV body. Opens NO socket.
    """

    def __init__(self, *, fetched_at_utc: str = _FETCHED_AT) -> None:
        self._fetched_at_utc = fetched_at_utc
        self.calls: list = []

    def get(
        self,
        *,
        endpoint_secret: Stage29_2BirdeyeEndpointSecret,
        path: str,
        query_params: Mapping[str, str],
        timeout_seconds: int,
    ) -> Stage29_2BirdeyeHttpResult:
        self.calls.append({"path": path, "query_params": dict(query_params)})
        if path == BIRDEYE_PATH_PRICE:
            return Stage29_2BirdeyeHttpResult(
                refusal_reason=BIRDEYE_REFUSAL_REASON_NONE,
                http_status_code=200,
                body=_price_body(),
                fetched_at_utc=self._fetched_at_utc,
            )
        if path == BIRDEYE_PATH_OHLCV:
            return Stage29_2BirdeyeHttpResult(
                refusal_reason=BIRDEYE_REFUSAL_REASON_NONE,
                http_status_code=200,
                body=_ohlcv_body_with_peak(),
                fetched_at_utc=self._fetched_at_utc,
            )
        return Stage29_2BirdeyeHttpResult(
            refusal_reason=BIRDEYE_REFUSAL_REASON_HTTP_TIMEOUT,
            http_status_code=0,
            body=None,
            fetched_at_utc=self._fetched_at_utc,
        )


def _endpoint_secret() -> Stage29_2BirdeyeEndpointSecret:
    return Stage29_2BirdeyeEndpointSecret(_api_key=_GOOD_KEY, _base_url=_GOOD_URL)


def _run_proof(
    *,
    transport: Optional[FakeComposerBirdeyeTransport] = None,
    request=None,
    transport_client: Optional[Stage30_11_5RecordingFakeTransportClient] = None,
):
    return run_stage30_11_13_fake_composer_proof(
        ath_transport=FakeComposerBirdeyeTransport() if transport is None else transport,
        ath_endpoint_secret=_endpoint_secret(),
        now_utc=_now_utc(),
        now_seconds=make_constant_clock(Decimal(0)),
        request=request,
        transport_client=transport_client,
    )


def _compose(*, request, transport_client):
    return compose_no_send_dispatch(
        request,
        ath_transport=FakeComposerBirdeyeTransport(),
        ath_endpoint_secret=_endpoint_secret(),
        now_utc=_now_utc(),
        transport_client=transport_client,
        now_seconds=make_constant_clock(Decimal(0)),
    )


# ---------------------------------------------------------------------------
# A fake dispatched gate input for the binding tests (the shape the committed
# Stage 30.9.3 sink hands the snapshot-bound body builder).
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _FakeGateInput:
    token_mint: str
    tier_token: str
    drawdown_from_ath: Decimal
    current_market_cap_usd: Decimal
    migration_status: str
    ath_status: str
    post_migration_ath_verified: bool
    created_at_utc: str
    candidate_id: str = "cand"


def _matching_gate_input(snapshot) -> _FakeGateInput:
    key = snapshot.gate_binding_key
    return _FakeGateInput(
        token_mint=key.token_mint,
        tier_token=key.tier_token,
        drawdown_from_ath=key.drawdown_from_ath,
        current_market_cap_usd=key.current_market_cap_usd,
        migration_status=key.migration_status,
        ath_status=key.ath_status,
        post_migration_ath_verified=key.post_migration_ath_verified,
        created_at_utc=key.created_at_utc,
    )


def _dispatched_snapshot():
    result, _client = _run_proof()
    assert result.decision == COMPOSE_DECISION_DISPATCHED, result.reason
    assert result.snapshot is not None
    return result.snapshot


# ---------------------------------------------------------------------------
# 1. Happy path: one snapshot -> gate PASS -> snapshot-bound body -> fake send
# ---------------------------------------------------------------------------


def test_happy_path_one_snapshot_drives_gate_and_body_no_send() -> None:
    result, client = _run_proof()
    assert result.decision == COMPOSE_DECISION_DISPATCHED, result.reason
    assert result.reason == COMPOSE_REASON_NO_SEND_DISPATCH_RECORDED
    # Exactly one RECORDED would-send; NO real send.
    assert client.attempted == 1
    assert client.accepted == 1
    assert client.rejected == 0
    assert result.transport_attempts == 1
    assert result.transport_accepts == 1
    # The runner reached the transport for this candidate.
    assert result.run_result.summary.gate_passed == 1
    assert result.run_result.summary.dispatch_accepted == 1


def test_body_values_match_the_gate_snapshot() -> None:
    result, client = _run_proof()
    assert result.decision == COMPOSE_DECISION_DISPATCHED, result.reason
    snapshot = result.snapshot
    body = result.dispatched_body
    assert body is not None
    assert body == client.bodies[-1]
    # The State line carries the SAME tier / MC / ATH MC / drop the snapshot
    # bound -- the body is derived from the gate snapshot, not a stray context.
    assert f"[{snapshot.tier_token}]" in body
    assert f"Tier: {snapshot.tier_token}" in body
    assert f"MC: {snapshot.market_cap_display}" in body
    assert f"ATH MC: {snapshot.ath_market_cap_display}" in body
    assert snapshot.fractional_drop_pct in body
    assert f"CA: {snapshot.token_mint}" in body
    # ATH MC was computed (never an Unknown for a dispatch-eligible body).
    assert snapshot.ath_market_cap_display.startswith("$")
    assert "ATH MC: Unknown" not in body


def test_snapshot_records_stage30_11_11_anchored_ath_provenance() -> None:
    snapshot = _dispatched_snapshot()
    assert snapshot.ath_source_stage == STAGE30_11_13_ATH_SOURCE_STAGE
    assert snapshot.ath_source_stage == "stage30_11_11"
    # The anchored window provenance (NOT a sliding window) rode onto the snapshot.
    assert snapshot.time_from_unix is not None
    assert snapshot.time_to_unix is not None
    assert snapshot.ohlcv_type is not None
    assert snapshot.span_seconds is not None and snapshot.span_seconds > 0
    assert snapshot.time_from_unix < snapshot.time_to_unix


# ---------------------------------------------------------------------------
# 2. The old / sliding ATH source cannot be wired
# ---------------------------------------------------------------------------


def test_composer_exposes_no_arbitrary_ath_context_source_seam() -> None:
    # The composer takes a transport + endpoint secret + now clock and builds
    # the committed Stage 30.11.11 anchored source ITSELF; there is no generic
    # ``ath_context_source`` / ``ath_source`` parameter an old sliding source
    # could be injected through.
    params = set(inspect.signature(compose_no_send_dispatch).parameters)
    assert "ath_context_source" not in params
    assert "ath_source" not in params
    assert "ath_resolver" not in params
    assert "ath_transport" in params


# ---------------------------------------------------------------------------
# 3 + 4. Gate/body binding: a drifted gate input is rejected, not emitted
# ---------------------------------------------------------------------------


def test_snapshot_bound_body_builder_accepts_the_matching_gate_input() -> None:
    snapshot = _dispatched_snapshot()
    builder = make_snapshot_bound_body_builder(snapshot)
    body = builder(_matching_gate_input(snapshot))
    assert isinstance(body, str)
    assert f"[{snapshot.tier_token}]" in body


@pytest.mark.parametrize(
    "field,bad_value",
    [
        ("token_mint", "So11111111111111111111111111111111111111112"),
        ("tier_token", "Tier 1"),
        ("drawdown_from_ath", Decimal("0.123456")),
        ("current_market_cap_usd", Decimal("424242")),
        ("migration_status", "MISSING"),
        ("ath_status", "STALE"),
        ("post_migration_ath_verified", False),
        ("created_at_utc", "2099-01-01T00:00:00Z"),
    ],
)
def test_binding_rejects_any_changed_field(field, bad_value) -> None:
    snapshot = _dispatched_snapshot()
    builder = make_snapshot_bound_body_builder(snapshot)
    drifted = replace(_matching_gate_input(snapshot), **{field: bad_value})
    with pytest.raises(Stage30_11_13ComposerError) as excinfo:
        builder(drifted)
    assert excinfo.value.reason == COMPOSE_REJECTED_GATE_BODY_MISMATCH


def test_cached_body_from_snapshot_a_cannot_be_reused_for_snapshot_b() -> None:
    # Snapshot A (the default proof). Snapshot B differs (a different MC ->
    # different binding key). A's bound body builder must reject B's gate input.
    snapshot_a = _dispatched_snapshot()
    result_b, _client = _run_proof(
        request=default_proof_request(current_market_cap_usd="50000")
    )
    assert result_b.decision == COMPOSE_DECISION_DISPATCHED, result_b.reason
    snapshot_b = result_b.snapshot
    assert (
        snapshot_a.gate_binding_key.current_market_cap_usd
        != snapshot_b.gate_binding_key.current_market_cap_usd
    )
    builder_a = make_snapshot_bound_body_builder(snapshot_a)
    with pytest.raises(Stage30_11_13ComposerError):
        builder_a(_matching_gate_input(snapshot_b))


# ---------------------------------------------------------------------------
# 5. Missing ATH MC blocks dispatch
# ---------------------------------------------------------------------------


def test_invalid_current_price_blocks_dispatch_no_transport_attempt() -> None:
    client = Stage30_11_5RecordingFakeTransportClient(
        created_at_utc=PROOF_CREATED_AT
    )
    result = _compose(
        request=default_proof_request(current_price="0"),
        transport_client=client,
    )
    assert result.decision == COMPOSE_DECISION_REJECTED
    assert result.reason == COMPOSE_REJECTED_INVALID_REQUEST
    assert client.attempted == 0


def test_zero_market_cap_blocks_dispatch() -> None:
    result, client = _run_proof(
        request=default_proof_request(current_market_cap_usd="0")
    )
    assert result.decision == COMPOSE_DECISION_REJECTED
    assert result.reason == COMPOSE_REJECTED_INVALID_REQUEST
    assert client.attempted == 0


# ---------------------------------------------------------------------------
# 6. Stale current price path remains closed (Stage 30.11.12 behavior)
# ---------------------------------------------------------------------------


def test_stale_current_price_fails_closed_no_dispatch() -> None:
    # A price fetched far before now -> Stage 27.4 STALE -> Stage 30.11.12
    # withholds the drawdown -> Stage 30.11.11 cannot resolve -> composer rejects.
    stale_transport = FakeComposerBirdeyeTransport(
        fetched_at_utc="2026-06-07T06:00:00+00:00"
    )
    result, client = _run_proof(transport=stale_transport)
    assert result.decision == COMPOSE_DECISION_REJECTED
    assert result.reason == COMPOSE_REJECTED_ATH_NOT_RESOLVED
    assert client.attempted == 0


# ---------------------------------------------------------------------------
# 7. Fake transport only
# ---------------------------------------------------------------------------


def test_non_fake_transport_client_fails_closed_first() -> None:
    class _NotAFakeClient:
        def __call__(self, payload):  # pragma: no cover - never reached
            raise AssertionError("real transport must never be called")

    result = _compose(
        request=default_proof_request(),
        transport_client=_NotAFakeClient(),
    )
    assert result.decision == COMPOSE_DECISION_REJECTED
    assert result.reason == COMPOSE_REJECTED_NON_FAKE_TRANSPORT


def test_fake_transport_records_would_send_never_a_real_send() -> None:
    result, client = _run_proof()
    assert result.decision == COMPOSE_DECISION_DISPATCHED, result.reason
    # The recording fake client carries the recorded would-send for THIS mint;
    # it sends nothing.
    assert client.token_mints == [PROOF_MINT]
    assert len(client.bodies) == 1

"""Stage 30.11.15 composer-hook + deduped-orchestrator + fake-proof tests.

Offline / fake-provider only. Proves:

  * the committed Stage 30.11.13 composer's ``pre_dispatch_guard`` hook is
    default-off (``None`` preserves the exact prior no-send behavior), allows a
    dispatch on an ``allowed`` verdict, and fails CLOSED on a suppress /
    unavailable / raising guard -- NO runner call, NO body, transport_attempts 0;
  * the Stage 30.11.15 deduped orchestrator records a would-send on the first
    compose, suppresses an identical second compose (attempts 0), allows a
    changed tier / mint / expired TTL, persists across a simulated restart
    through a JSONL ledger on a temp path, and fails closed with no ledger;
  * the offline fake dedupe proof composes the same request twice over one
    in-memory ledger: first records a would-send, second is suppressed.

The stage29-shaped fake Birdeye transport lives HERE (a test may build a
provider fake). No real send, no network, no env read, no wallet, no trading.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Mapping, Optional

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
from PHX2.stage30.stage30_11_2_fake_runtime_gate_proof import (
    make_constant_clock,
)
from PHX2.stage30.stage30_11_5_fake_live_wiring_proof import (
    Stage30_11_5RecordingFakeTransportClient,
)
from PHX2.stage30.stage30_11_13_committed_no_send_composer import (
    COMPOSE_DECISION_DISPATCHED,
    COMPOSE_DECISION_REJECTED,
    COMPOSE_REJECTED_DEDUPE_SUPPRESSED,
    COMPOSE_REJECTED_DEDUPE_UNAVAILABLE,
    compose_no_send_dispatch,
)
from PHX2.stage30.stage30_11_13_fake_composer_proof import (
    PROOF_CREATED_AT,
    PROOF_CURRENT_PRICE,
    PROOF_LATER_LOWER,
    PROOF_MINT,
    PROOF_PEAK_ATH,
    default_proof_request,
)
from PHX2.stage30.stage30_11_15_ping_dedupe_ledger import (
    InMemoryPingDedupeLedger,
    JsonlPingDedupeLedger,
)
from PHX2.stage30.stage30_11_15_no_send_dedupe_guard import (
    Stage30_11_15DedupedComposeResult,
    compose_no_send_dispatch_deduped,
    make_no_send_dedupe_guard,
)
from PHX2.stage30.stage30_11_15_fake_dedupe_proof import (
    run_stage30_11_15_fake_dedupe_proof,
)
from PHX2.stage30.stage30_11_15_ping_dedupe_models import (
    DEDUPE_VERDICT_ALLOWED,
    DEDUPE_VERDICT_SUPPRESSED_DUPLICATE,
    DEDUPE_VERDICT_UNAVAILABLE,
)


_GOOD_KEY: str = "abcd1234efgh5678ijkl9012mnop3456"
_GOOD_URL: str = "https://aaaa-bbbb.example"
_FETCHED_AT: str = "2026-06-07T07:06:40+00:00"

from datetime import datetime, timezone  # noqa: E402  (test helper clock)


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
    """Path-routed fake Birdeye transport. Opens NO socket."""

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
        self.calls.append({"path": path})
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


def _rec_client() -> Stage30_11_5RecordingFakeTransportClient:
    return Stage30_11_5RecordingFakeTransportClient(created_at_utc=PROOF_CREATED_AT)


def _compose(*, request, transport_client, guard=None):
    return compose_no_send_dispatch(
        request,
        ath_transport=FakeComposerBirdeyeTransport(),
        ath_endpoint_secret=_endpoint_secret(),
        now_utc=_now_utc(),
        transport_client=transport_client,
        now_seconds=make_constant_clock(Decimal(0)),
        pre_dispatch_guard=guard,
    )


def _deduped(*, request=None, ledger, transport_client=None, **kwargs):
    return compose_no_send_dispatch_deduped(
        default_proof_request() if request is None else request,
        ath_transport=FakeComposerBirdeyeTransport(),
        ath_endpoint_secret=_endpoint_secret(),
        now_utc=_now_utc(),
        transport_client=_rec_client() if transport_client is None else transport_client,
        now_seconds=make_constant_clock(Decimal(0)),
        ledger=ledger,
        **kwargs,
    )


# ---------------------------------------------------------------------------
# Stub verdicts to exercise the composer hook in isolation (duck-typed)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _StubVerdict:
    allowed: bool
    unavailable: bool = False


def _stub_guard(verdict):
    def _guard(_snapshot):
        return verdict
    return _guard


def _raising_guard(_snapshot):
    raise RuntimeError("guard boom")


# ===========================================================================
# 1. Composer hook: default-off + allow + fail-closed paths
# ===========================================================================


def test_guard_none_preserves_existing_behavior() -> None:
    client = _rec_client()
    result = _compose(
        request=default_proof_request(), transport_client=client, guard=None
    )
    assert result.decision == COMPOSE_DECISION_DISPATCHED, result.reason
    assert client.attempted == 1
    assert result.transport_attempts == 1
    assert result.dispatched_body is not None


def test_guard_allow_verdict_dispatches() -> None:
    client = _rec_client()
    result = _compose(
        request=default_proof_request(),
        transport_client=client,
        guard=_stub_guard(_StubVerdict(allowed=True)),
    )
    assert result.decision == COMPOSE_DECISION_DISPATCHED, result.reason
    assert client.attempted == 1


def test_guard_suppress_verdict_blocks_runner_body_and_transport() -> None:
    client = _rec_client()
    result = _compose(
        request=default_proof_request(),
        transport_client=client,
        guard=_stub_guard(_StubVerdict(allowed=False, unavailable=False)),
    )
    assert result.decision == COMPOSE_DECISION_REJECTED
    assert result.reason == COMPOSE_REJECTED_DEDUPE_SUPPRESSED
    assert result.run_result is None
    assert result.dispatched_body is None
    assert result.transport_attempts == 0
    assert client.attempted == 0
    assert client.bodies == []
    # The snapshot was already built before the guard, so it is attached.
    assert result.snapshot is not None


def test_guard_unavailable_verdict_fails_closed() -> None:
    client = _rec_client()
    result = _compose(
        request=default_proof_request(),
        transport_client=client,
        guard=_stub_guard(_StubVerdict(allowed=False, unavailable=True)),
    )
    assert result.decision == COMPOSE_DECISION_REJECTED
    assert result.reason == COMPOSE_REJECTED_DEDUPE_UNAVAILABLE
    assert result.run_result is None
    assert result.dispatched_body is None
    assert result.transport_attempts == 0
    assert client.attempted == 0


def test_guard_that_raises_fails_closed_unavailable() -> None:
    client = _rec_client()
    result = _compose(
        request=default_proof_request(),
        transport_client=client,
        guard=_raising_guard,
    )
    assert result.decision == COMPOSE_DECISION_REJECTED
    assert result.reason == COMPOSE_REJECTED_DEDUPE_UNAVAILABLE
    assert result.transport_attempts == 0
    assert client.attempted == 0


# ===========================================================================
# 2. Deduped orchestrator
# ===========================================================================


def test_orchestrator_first_records_would_send() -> None:
    ledger = InMemoryPingDedupeLedger()
    client = _rec_client()
    result = _deduped(ledger=ledger, transport_client=client)
    assert isinstance(result, Stage30_11_15DedupedComposeResult)
    assert result.compose_result.decision == COMPOSE_DECISION_DISPATCHED, (
        result.compose_result.reason
    )
    assert client.attempted == 1
    assert result.dedupe_outcome.verdict == DEDUPE_VERDICT_ALLOWED


def test_orchestrator_second_identical_is_suppressed_attempts_zero() -> None:
    ledger = InMemoryPingDedupeLedger()
    first_client = _rec_client()
    _deduped(ledger=ledger, transport_client=first_client)
    second_client = _rec_client()
    second = _deduped(ledger=ledger, transport_client=second_client)
    assert second.compose_result.decision == COMPOSE_DECISION_REJECTED
    assert second.compose_result.reason == COMPOSE_REJECTED_DEDUPE_SUPPRESSED
    assert second.compose_result.transport_attempts == 0
    assert second.compose_result.dispatched_body is None
    assert second.compose_result.run_result is None
    assert second_client.attempted == 0
    assert second_client.bodies == []
    assert second.dedupe_outcome.verdict == DEDUPE_VERDICT_SUPPRESSED_DUPLICATE


# A second VALID, render-able base58 mint (not the WSOL / quote mint the Stage
# 30.12 renderer fails closed on): the proof mint with a changed prefix.
_OTHER_MINT: str = "Fx8km9VRfjeeowsMR1YmjR1GhxXHBatAEVhggxYVfaNe"


def test_orchestrator_different_mint_allows() -> None:
    # Reserve the default mint, then compose a DIFFERENT mint within TTL: a new
    # key -> allowed (robust; same drawdown / tier, only the identity differs).
    ledger = InMemoryPingDedupeLedger()
    first = _deduped(ledger=ledger)
    assert first.compose_result.decision == COMPOSE_DECISION_DISPATCHED
    diff = _deduped(ledger=ledger, request=_request_with_mint(_OTHER_MINT))
    assert diff.compose_result.decision == COMPOSE_DECISION_DISPATCHED, (
        diff.compose_result.reason
    )
    assert diff.dedupe_outcome.verdict == DEDUPE_VERDICT_ALLOWED


def test_orchestrator_changed_policy_version_allows() -> None:
    # The same snapshot under a BUMPED policy version is a new key -> allowed even
    # within TTL (the Stage 30.6 dedupe-contract policy axis; robust -- it does
    # not depend on tier thresholds). The per-axis re-key for tier / drawdown
    # band is proven at the guard + ledger level.
    ledger = InMemoryPingDedupeLedger()
    _deduped(ledger=ledger, policy_version="stage30_11_15_v0")
    bumped = _deduped(ledger=ledger, policy_version="stage30_11_15_v1")
    assert bumped.compose_result.decision == COMPOSE_DECISION_DISPATCHED, (
        bumped.compose_result.reason
    )
    assert bumped.dedupe_outcome.verdict == DEDUPE_VERDICT_ALLOWED


def test_orchestrator_expired_ttl_allows() -> None:
    ledger = InMemoryPingDedupeLedger()
    _deduped(ledger=ledger, ttl_seconds=1)
    # The composer's now is fixed (created_at fixed in the proof request), so to
    # age the reservation we drop the TTL to 0 on a second identical compose.
    out = _deduped(ledger=ledger, ttl_seconds=0)
    assert out.compose_result.decision == COMPOSE_DECISION_DISPATCHED, (
        out.compose_result.reason
    )


def test_orchestrator_no_ledger_fails_closed() -> None:
    client = _rec_client()
    result = _deduped(ledger=None, transport_client=client)
    assert result.compose_result is None
    assert result.dedupe_outcome.verdict == DEDUPE_VERDICT_UNAVAILABLE
    assert client.attempted == 0


def test_orchestrator_corrupt_jsonl_ledger_fails_closed(tmp_path) -> None:
    path = tmp_path / "ledger.jsonl"
    path.write_text("corrupt\n", encoding="utf-8")
    client = _rec_client()
    result = _deduped(
        ledger=JsonlPingDedupeLedger(path=path), transport_client=client
    )
    assert result.compose_result.decision == COMPOSE_DECISION_REJECTED
    assert result.compose_result.reason == COMPOSE_REJECTED_DEDUPE_UNAVAILABLE
    assert result.compose_result.transport_attempts == 0
    assert client.attempted == 0
    assert result.dedupe_outcome.verdict == DEDUPE_VERDICT_UNAVAILABLE


def test_orchestrator_jsonl_cross_run_suppresses(tmp_path) -> None:
    path = tmp_path / "ledger.jsonl"
    first = _deduped(ledger=JsonlPingDedupeLedger(path=path))
    assert first.compose_result.decision == COMPOSE_DECISION_DISPATCHED
    # Simulated restart: a NEW ledger instance over the SAME file.
    second_client = _rec_client()
    second = _deduped(
        ledger=JsonlPingDedupeLedger(path=path), transport_client=second_client
    )
    assert second.compose_result.decision == COMPOSE_DECISION_REJECTED
    assert second.compose_result.reason == COMPOSE_REJECTED_DEDUPE_SUPPRESSED
    assert second_client.attempted == 0


def _request_with_mint(mint: str):
    from dataclasses import replace
    return replace(default_proof_request(), token_mint=mint)


# ===========================================================================
# 3. The fake dedupe proof driver
# ===========================================================================


def test_fake_dedupe_proof_first_records_second_suppressed() -> None:
    result = run_stage30_11_15_fake_dedupe_proof(
        ath_transport=FakeComposerBirdeyeTransport(),
        ath_endpoint_secret=_endpoint_secret(),
        now_utc=_now_utc(),
        now_seconds=make_constant_clock(Decimal(0)),
    )
    assert result.first.compose_result.decision == COMPOSE_DECISION_DISPATCHED, (
        result.first.compose_result.reason
    )
    assert result.first_client.attempted == 1
    assert result.first_client.token_mints == [PROOF_MINT]

    assert result.second.compose_result.decision == COMPOSE_DECISION_REJECTED
    assert result.second.compose_result.reason == COMPOSE_REJECTED_DEDUPE_SUPPRESSED
    assert result.second.compose_result.transport_attempts == 0
    assert result.second_client.attempted == 0
    assert result.second_client.bodies == []
    assert result.second.dedupe_outcome.verdict == (
        DEDUPE_VERDICT_SUPPRESSED_DUPLICATE
    )


def test_fake_dedupe_proof_accepts_injected_jsonl_ledger(tmp_path) -> None:
    ledger = JsonlPingDedupeLedger(path=tmp_path / "ledger.jsonl")
    result = run_stage30_11_15_fake_dedupe_proof(
        ath_transport=FakeComposerBirdeyeTransport(),
        ath_endpoint_secret=_endpoint_secret(),
        now_utc=_now_utc(),
        now_seconds=make_constant_clock(Decimal(0)),
        ledger=ledger,
    )
    assert result.first.compose_result.decision == COMPOSE_DECISION_DISPATCHED
    assert result.second.compose_result.decision == COMPOSE_DECISION_REJECTED
    # The JSONL ledger recorded exactly one reservation.
    lines = [
        ln
        for ln in (tmp_path / "ledger.jsonl").read_text(
            encoding="utf-8"
        ).splitlines()
        if ln
    ]
    assert len(lines) == 1

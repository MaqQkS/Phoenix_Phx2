"""Stage 30.11.17 fake operator-curated compose session proof tests.

Offline / fake-provider only. Proves the thin committed proof driver runs an
injected operator-curated list through the bounded session over a default
in-memory ledger + a recording FAKE client, suppresses an in-run duplicate over
the ONE shared ledger, returns the ``(result, client, ledger)`` wrapper, and
accepts an injected JSONL ledger on a temp path -- all with NO real send.

The stage29-shaped fake Birdeye transport + the coherent curated list live HERE.
No real send, no network, no env read, no Stage 30.11.16 guard, no live provider.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal
from typing import Mapping

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
from PHX2.stage30.stage30_11_17_operator_curated_candidate_list_models import (
    ENTRY_OUTCOME_DEDUPE_BLOCKED,
    ENTRY_OUTCOME_DISPATCHED,
    STAGE30_11_17_REDACTION_STATUS_REDACTED,
    STOP_REASON_COMPLETED,
    Stage30_11_17OperatorCuratedCandidate,
)
from PHX2.stage30.stage30_11_17_fake_curated_session_proof import (
    Stage30_11_17FakeCuratedSessionProofResult,
    run_stage30_11_17_fake_curated_session_proof,
)


_OTHER_MINT: str = "Fx8km9VRfjeeowsMR1YmjR1GhxXHBatAEVhggxYVfaNe"
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
    """Path-routed (mint-agnostic) fake Birdeye transport. Opens NO socket."""

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


def _curated(request, label=None) -> Stage30_11_17OperatorCuratedCandidate:
    return Stage30_11_17OperatorCuratedCandidate(
        request=request, curated_label=label
    )


def _default_curated_list():
    # DISPATCHED + DEDUPE_BLOCKED (same mint) + DISPATCHED (other mint).
    return [
        _curated(default_proof_request(), "DIP_A"),
        _curated(default_proof_request(), "DIP_A_DUP"),
        _curated(replace(default_proof_request(), token_mint=_OTHER_MINT), "DIP_B"),
    ]


def _run_proof(candidates=None, **kwargs):
    return run_stage30_11_17_fake_curated_session_proof(
        _default_curated_list() if candidates is None else candidates,
        ath_transport=FakeComposerBirdeyeTransport(),
        ath_endpoint_secret=_endpoint_secret(),
        now_utc=_now_utc(),
        now_seconds=make_constant_clock(Decimal(0)),
        created_at_utc=PROOF_CREATED_AT,
        **kwargs,
    )


# ---------------------------------------------------------------------------
# 1. Default wiring: shared in-memory ledger + recording fake client
# ---------------------------------------------------------------------------


def test_proof_returns_wrapper_with_result_client_and_ledger() -> None:
    proof = _run_proof()
    assert isinstance(proof, Stage30_11_17FakeCuratedSessionProofResult)
    assert isinstance(proof.ledger, InMemoryPingDedupeLedger)
    assert isinstance(proof.client, Stage30_11_5RecordingFakeTransportClient)


def test_proof_default_session_dispatches_dedupes_and_completes() -> None:
    proof = _run_proof()
    result = proof.result
    assert result.stop_reason == STOP_REASON_COMPLETED
    assert result.candidates_seen == 3
    assert result.compositions_attempted == 3
    assert result.dispatched == 2
    assert result.dedupe_blocked == 1
    assert result.rejected == 0
    assert result.errors == 0
    assert result.would_send_recorded == 2
    assert result.redaction_status == STAGE30_11_17_REDACTION_STATUS_REDACTED
    outcomes = [e.outcome for e in result.events]
    assert outcomes == [
        ENTRY_OUTCOME_DISPATCHED,
        ENTRY_OUTCOME_DEDUPE_BLOCKED,
        ENTRY_OUTCOME_DISPATCHED,
    ]
    # The recording fake client saw exactly the two dispatched would-sends.
    assert proof.client.attempted == 2
    assert proof.client.token_mints == [PROOF_MINT, _OTHER_MINT]


# ---------------------------------------------------------------------------
# 2. Injected JSONL ledger on a temp path (never the operator ceremony path)
# ---------------------------------------------------------------------------


def test_proof_accepts_injected_jsonl_ledger(tmp_path) -> None:
    ledger = JsonlPingDedupeLedger(path=tmp_path / "ledger.jsonl")
    proof = _run_proof(ledger=ledger)
    assert proof.ledger is ledger
    assert proof.result.dispatched == 2
    assert proof.result.dedupe_blocked == 1
    # The JSONL ledger recorded exactly two reservations (one per distinct mint).
    lines = [
        ln
        for ln in (tmp_path / "ledger.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if ln
    ]
    assert len(lines) == 2


def test_proof_default_ledger_is_fresh_in_memory_each_run() -> None:
    # Two separate default runs do NOT share state (each builds a fresh ledger),
    # so the first entry dispatches in BOTH runs.
    first = _run_proof()
    second = _run_proof()
    assert first.result.dispatched == 2
    assert second.result.dispatched == 2
    assert first.ledger is not second.ledger

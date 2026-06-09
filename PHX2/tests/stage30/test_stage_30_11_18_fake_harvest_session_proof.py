"""Stage 30.11.18 fake harvested-facts curated session proof tests.

Offline / fake-provider only. Proves the thin committed proof driver runs an
injected harvested-facts list through the adapter over a default in-memory ledger +
a recording FAKE client: a well-formed fact projects into a committed revalidation
request and dispatches (a RECORDED would-send), a duplicate is suppressed over the
ONE shared ledger, a Layer-1-malformed fact is rejected at projection (never
reaching the composer), and the report rolls up the Layer-1 counts + the embedded
Stage 30.11.17 session result -- all with NO real send.

The stage29-shaped fake Birdeye transport + the coherent facts live HERE. No real
send, no network, no env read, no Stage 30.11.16 guard, no live provider.
"""

from __future__ import annotations

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
    PROOF_AGE_DISPLAY,
    PROOF_CANDIDATE_ID,
    PROOF_CREATED_AT,
    PROOF_CURRENT_PRICE,
    PROOF_LATER_LOWER,
    PROOF_LIQUIDITY_USD,
    PROOF_MARKET_CAP_USD,
    PROOF_MARKET_CONTEXT_STATUS,
    PROOF_MARKET_FETCHED_AT,
    PROOF_MIGRATION_ANCHOR,
    PROOF_MIGRATION_SOURCE,
    PROOF_MINT,
    PROOF_PEAK_ATH,
    PROOF_SYMBOL,
)
from PHX2.stage30.stage30_11_15_ping_dedupe_ledger import (
    InMemoryPingDedupeLedger,
    JsonlPingDedupeLedger,
)
from PHX2.stage30.stage30_11_17_operator_curated_candidate_list_models import (
    ENTRY_OUTCOME_DEDUPE_BLOCKED,
    ENTRY_OUTCOME_DISPATCHED,
    STOP_REASON_COMPLETED,
)
from PHX2.stage30.stage30_11_18_harvested_facts_models import (
    PROJECTION_DECISION_PROJECTED,
    PROJECTION_DECISION_REJECTED_MISSING_LIQUIDITY_USD,
    STAGE30_11_18_REDACTION_STATUS_REDACTED,
    Stage30_11_18HarvestedCandidateFacts,
    Stage30_11_18SessionReport,
)
from PHX2.stage30.stage30_11_18_fake_harvest_session_proof import (
    Stage30_11_18FakeHarvestSessionProofResult,
    run_stage30_11_18_fake_harvest_session_proof,
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
                {
                    "h": PROOF_LATER_LOWER,
                    "unixTime": _unix("2026-06-06T07:30:00Z"),
                },
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


def _facts(**overrides) -> Stage30_11_18HarvestedCandidateFacts:
    base = dict(
        token_mint=PROOF_MINT,
        candidate_id=PROOF_CANDIDATE_ID,
        migration_time_utc=PROOF_MIGRATION_ANCHOR,
        current_price=PROOF_CURRENT_PRICE,
        current_market_cap_usd=PROOF_MARKET_CAP_USD,
        liquidity_usd=PROOF_LIQUIDITY_USD,
        market_context_status=PROOF_MARKET_CONTEXT_STATUS,
        market_context_fetched_at_utc=PROOF_MARKET_FETCHED_AT,
        created_at_utc=PROOF_CREATED_AT,
        symbol_or_name=PROOF_SYMBOL,
        migration_source=PROOF_MIGRATION_SOURCE,
        age_display=PROOF_AGE_DISPLAY,
    )
    base.update(overrides)
    return Stage30_11_18HarvestedCandidateFacts(**base)


def _default_facts_list():
    # DISPATCHED + DEDUPE_BLOCKED (same mint) + DISPATCHED (other mint).
    return [
        _facts(),
        _facts(),
        _facts(token_mint=_OTHER_MINT),
    ]


def _run_proof(facts=None, **kwargs):
    return run_stage30_11_18_fake_harvest_session_proof(
        _default_facts_list() if facts is None else facts,
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


def test_proof_returns_wrapper_with_report_client_and_ledger() -> None:
    proof = _run_proof()
    assert isinstance(proof, Stage30_11_18FakeHarvestSessionProofResult)
    assert isinstance(proof.ledger, InMemoryPingDedupeLedger)
    assert isinstance(proof.client, Stage30_11_5RecordingFakeTransportClient)
    assert isinstance(proof.report, Stage30_11_18SessionReport)


def test_proof_projects_dispatches_dedupes_and_completes() -> None:
    proof = _run_proof()
    report = proof.report
    # Layer-1: all three facts projected into a committed request.
    assert report.facts_seen == 3
    assert report.projected == 3
    assert report.rejected_projection == 0
    assert all(
        e.decision == PROJECTION_DECISION_PROJECTED
        for e in report.projection_events
    )
    # Layer-2: the embedded Stage 30.11.17 session result.
    sr = report.session_result
    assert sr.stop_reason == STOP_REASON_COMPLETED
    assert sr.candidates_seen == 3
    assert sr.compositions_attempted == 3
    assert sr.dispatched == 2
    assert sr.dedupe_blocked == 1
    assert sr.rejected == 0
    assert sr.errors == 0
    assert sr.would_send_recorded == 2
    assert report.redaction_status == STAGE30_11_18_REDACTION_STATUS_REDACTED
    outcomes = [e.outcome for e in sr.events]
    assert outcomes == [
        ENTRY_OUTCOME_DISPATCHED,
        ENTRY_OUTCOME_DEDUPE_BLOCKED,
        ENTRY_OUTCOME_DISPATCHED,
    ]
    # The recording fake client saw exactly the two dispatched would-sends.
    assert proof.client.attempted == 2
    assert proof.client.token_mints == [PROOF_MINT, _OTHER_MINT]


# ---------------------------------------------------------------------------
# 2. Layer-1 rejection: a malformed fact never reaches the composer
# ---------------------------------------------------------------------------


def test_proof_layer1_rejects_malformed_fact_before_compose() -> None:
    facts = [_facts(), _facts(liquidity_usd="")]
    proof = _run_proof(facts)
    report = proof.report
    assert report.facts_seen == 2
    assert report.projected == 1
    assert report.rejected_projection == 1
    decisions = [e.decision for e in report.projection_events]
    assert PROJECTION_DECISION_PROJECTED in decisions
    assert PROJECTION_DECISION_REJECTED_MISSING_LIQUIDITY_USD in decisions
    # Only the projected fact reached the committed session.
    sr = report.session_result
    assert sr.candidates_seen == 1
    assert sr.dispatched == 1
    assert report.redaction_status == STAGE30_11_18_REDACTION_STATUS_REDACTED
    assert proof.client.attempted == 1


# ---------------------------------------------------------------------------
# 3. Injected JSONL ledger on a temp path (never the operator ceremony path)
# ---------------------------------------------------------------------------


def test_proof_accepts_injected_jsonl_ledger(tmp_path) -> None:
    ledger = JsonlPingDedupeLedger(path=tmp_path / "ledger.jsonl")
    proof = _run_proof(ledger=ledger)
    assert proof.ledger is ledger
    assert proof.report.session_result.dispatched == 2
    assert proof.report.session_result.dedupe_blocked == 1
    lines = [
        ln
        for ln in (tmp_path / "ledger.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if ln
    ]
    assert len(lines) == 2

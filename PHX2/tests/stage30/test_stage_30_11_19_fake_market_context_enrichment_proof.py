"""Stage 30.11.19 fake market-context enrichment proof tests.

Offline / fake-provider only. Proves the thin committed proof driver runs base
harvested facts through the enrichment adapter over the REAL committed Stage 30.4.3
token-overview market-context source (built HERE over a FAKE transport): a usable
token-overview reading enriches the MC/LP/fetched-at bundle and the enriched fact
projects + dispatches through the committed Stage 30.11.18 / 30.11.17 session; a
token-overview body WITHOUT liquidity fails closed to SKIPPED_MISSING_LIQUIDITY_USD
and is NOT forwarded -- all with NO real send.

The fake Birdeye transport (token-overview + price + ohlcv), the Stage 30.4.3
source, the clocks, and the base facts live HERE. No real send, no network, no env
read, no Stage 30.11.16 guard.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Mapping

from PHX2.stage29.birdeye_constants import (
    BIRDEYE_PATH_OHLCV,
    BIRDEYE_PATH_PRICE,
    BIRDEYE_PATH_TOKEN_OVERVIEW,
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
from PHX2.stage30.stage30_4_3_market_context_birdeye_source import (
    Stage30_4_3BirdeyeMarketContextSource,
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
    PROOF_MIGRATION_ANCHOR,
    PROOF_MIGRATION_SOURCE,
    PROOF_MINT,
    PROOF_PEAK_ATH,
    PROOF_SYMBOL,
)
from PHX2.stage30.stage30_11_15_ping_dedupe_ledger import (
    InMemoryPingDedupeLedger,
)
from PHX2.stage30.stage30_11_18_harvested_facts_models import (
    PROJECTION_DECISION_PROJECTED,
    Stage30_11_18HarvestedCandidateFacts,
)
from PHX2.stage30.stage30_11_19_market_context_enrichment_models import (
    ENRICHMENT_DECISION_ENRICHED,
    ENRICHMENT_DECISION_SKIPPED_MISSING_LIQUIDITY_USD,
    STAGE30_11_19_REDACTION_STATUS_REDACTED,
    Stage30_11_19EnrichmentSessionReport,
)
from PHX2.stage30.stage30_11_19_fake_market_context_enrichment_proof import (
    Stage30_11_19FakeEnrichmentSessionProofResult,
    run_stage30_11_19_fake_market_context_enrichment_proof,
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
                {
                    "h": PROOF_LATER_LOWER,
                    "unixTime": _unix("2026-06-06T07:30:00Z"),
                },
            ]
        },
    }


def _token_overview_body(*, with_liquidity: bool) -> dict:
    data = {"marketCap": int(PROOF_MARKET_CAP_USD)}
    if with_liquidity:
        data["liquidity"] = int(PROOF_LIQUIDITY_USD)
    return {"success": True, "data": data}


class FakeBirdeyeTransport(Stage29_2BirdeyeHttpTransport):
    """Path-routed fake transport serving token-overview + price + ohlcv. Opens
    NO socket. ``with_liquidity=False`` drops the token-overview liquidity field.
    """

    def __init__(
        self,
        *,
        with_liquidity: bool = True,
        fetched_at_utc: str = _FETCHED_AT,
    ) -> None:
        self._with_liquidity = with_liquidity
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
        if path == BIRDEYE_PATH_TOKEN_OVERVIEW:
            return self._ok(
                _token_overview_body(with_liquidity=self._with_liquidity)
            )
        if path == BIRDEYE_PATH_PRICE:
            return self._ok(_price_body())
        if path == BIRDEYE_PATH_OHLCV:
            return self._ok(_ohlcv_body_with_peak())
        return Stage29_2BirdeyeHttpResult(
            refusal_reason=BIRDEYE_REFUSAL_REASON_HTTP_TIMEOUT,
            http_status_code=0,
            body=None,
            fetched_at_utc=self._fetched_at_utc,
        )

    def _ok(self, body: dict) -> Stage29_2BirdeyeHttpResult:
        return Stage29_2BirdeyeHttpResult(
            refusal_reason=BIRDEYE_REFUSAL_REASON_NONE,
            http_status_code=200,
            body=body,
            fetched_at_utc=self._fetched_at_utc,
        )


def _endpoint_secret() -> Stage29_2BirdeyeEndpointSecret:
    return Stage29_2BirdeyeEndpointSecret(_api_key=_GOOD_KEY, _base_url=_GOOD_URL)


def _market_context_source(transport: FakeBirdeyeTransport):
    return Stage30_4_3BirdeyeMarketContextSource(
        transport=transport,
        endpoint_secret=_endpoint_secret(),
        timeout_seconds=10,
    )


def _base_facts(**overrides) -> Stage30_11_18HarvestedCandidateFacts:
    # The market fields are PLACEHOLDERS the enrichment overwrites from the
    # token-overview reading; current_price + migration_time are real.
    base = dict(
        token_mint=PROOF_MINT,
        candidate_id=PROOF_CANDIDATE_ID,
        migration_time_utc=PROOF_MIGRATION_ANCHOR,
        current_price=PROOF_CURRENT_PRICE,
        current_market_cap_usd="1",
        liquidity_usd="1",
        market_context_status="UNKNOWN",
        market_context_fetched_at_utc="2020-01-01T00:00:00Z",
        created_at_utc=PROOF_CREATED_AT,
        symbol_or_name=PROOF_SYMBOL,
        migration_source=PROOF_MIGRATION_SOURCE,
        age_display=PROOF_AGE_DISPLAY,
    )
    base.update(overrides)
    return Stage30_11_18HarvestedCandidateFacts(**base)


def _run_proof(base_facts_list, *, with_liquidity: bool = True, **kwargs):
    transport = FakeBirdeyeTransport(with_liquidity=with_liquidity)
    return run_stage30_11_19_fake_market_context_enrichment_proof(
        base_facts_list,
        market_context_source=_market_context_source(transport),
        ath_transport=transport,
        ath_endpoint_secret=_endpoint_secret(),
        now_utc=_now_utc(),
        now_seconds=make_constant_clock(Decimal(0)),
        created_at_utc=PROOF_CREATED_AT,
        **kwargs,
    )


# ---------------------------------------------------------------------------
# 1. Default wiring + happy path: enrich the bundle, project, dispatch
# ---------------------------------------------------------------------------


def test_proof_returns_wrapper() -> None:
    proof = _run_proof([_base_facts()])
    assert isinstance(proof, Stage30_11_19FakeEnrichmentSessionProofResult)
    assert isinstance(proof.ledger, InMemoryPingDedupeLedger)
    assert isinstance(proof.client, Stage30_11_5RecordingFakeTransportClient)
    assert isinstance(proof.report, Stage30_11_19EnrichmentSessionReport)


def test_proof_enriches_real_birdeye_reading_and_dispatches() -> None:
    proof = _run_proof([_base_facts()])
    report = proof.report
    # Layer-0: the token-overview reading enriched the one base fact.
    assert report.facts_seen == 1
    assert report.enriched == 1
    assert report.skipped == 0
    assert [e.decision for e in report.enrichment_events] == [
        ENRICHMENT_DECISION_ENRICHED
    ]
    # The embedded Stage 30.11.18 report projected + dispatched the enriched fact.
    downstream = report.downstream_report
    assert downstream.facts_seen == 1
    assert downstream.projected == 1
    assert downstream.rejected_projection == 0
    assert [e.decision for e in downstream.projection_events] == [
        PROJECTION_DECISION_PROJECTED
    ]
    assert downstream.session_result.dispatched == 1
    assert downstream.session_result.would_send_recorded == 1
    assert report.redaction_status == STAGE30_11_19_REDACTION_STATUS_REDACTED
    # The recording fake client saw exactly the one dispatched would-send.
    assert proof.client.attempted == 1
    assert proof.client.token_mints == [PROOF_MINT]


# ---------------------------------------------------------------------------
# 2. A token-overview body without liquidity skips and is NOT forwarded
# ---------------------------------------------------------------------------


def test_proof_skips_missing_liquidity_and_does_not_forward() -> None:
    proof = _run_proof([_base_facts()], with_liquidity=False)
    report = proof.report
    assert report.facts_seen == 1
    assert report.enriched == 0
    assert report.skipped == 1
    assert [e.decision for e in report.enrichment_events] == [
        ENRICHMENT_DECISION_SKIPPED_MISSING_LIQUIDITY_USD
    ]
    # The skipped fact was NOT forwarded -> the embedded session saw nothing.
    downstream = report.downstream_report
    assert downstream.facts_seen == 0
    assert downstream.session_result.dispatched == 0
    assert proof.client.attempted == 0
    assert report.redaction_status == STAGE30_11_19_REDACTION_STATUS_REDACTED

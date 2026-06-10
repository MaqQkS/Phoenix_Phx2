"""Stage 30.11.20 fake current-price enrichment proof tests.

Offline / fake-provider only. Proves the thin committed proof driver runs base
harvested facts through the current-price enrichment adapter over the REAL
committed Stage 29.2 price source (built HERE over a FAKE transport, injected
DIRECTLY with NO shim -- the locked key decision) plus the REAL committed Stage
30.4.3 token-overview market-context source over the SAME fake transport: a usable
``/defi/price`` body overwrites the ``current_price`` placeholder and the enriched
fact flows through the committed Stage 30.11.19 -> 30.11.18 -> 30.11.17 chain to a
RECORDED would-send; a missing / zero / refused price fails closed to the precise
SKIPPED_* token and is NOT forwarded -- all with NO real send.

The fake Birdeye transport (price + token-overview + ohlcv), the Stage 29.2 price
source, the Stage 30.4.3 source, the clocks, and the base facts live HERE. No real
send, no network, no env read, no Stage 30.11.16 guard.
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
from PHX2.stage29.stage29_2_birdeye_price_source import (
    Stage29_2BirdeyePriceSource,
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
)
from PHX2.stage30.stage30_11_20_current_price_enrichment_models import (
    PRICE_ENRICHMENT_DECISION_ENRICHED,
    PRICE_ENRICHMENT_DECISION_SKIPPED_INVALID_PRICE_VALUE,
    PRICE_ENRICHMENT_DECISION_SKIPPED_PRICE_MISSING,
    PRICE_ENRICHMENT_DECISION_SKIPPED_PRICE_SOURCE_ERROR,
    STAGE30_11_20_REDACTION_STATUS_REDACTED,
    Stage30_11_20PriceEnrichmentSessionReport,
)
from PHX2.stage30.stage30_11_20_current_price_enrichment_adapter import (
    enrich_facts_with_current_price,
)
from PHX2.stage30.stage30_11_20_fake_current_price_enrichment_proof import (
    Stage30_11_20FakePriceEnrichmentSessionProofResult,
    run_stage30_11_20_fake_current_price_enrichment_proof,
)


_GOOD_KEY: str = "abcd1234efgh5678ijkl9012mnop3456"
_GOOD_URL: str = "https://aaaa-bbbb.example"
_FETCHED_AT: str = "2026-06-07T07:06:40+00:00"

# The placeholder the harvest ceremony carries BEFORE the price seam fills it.
_PRICE_PLACEHOLDER: str = ""

# Price-path serving modes for the fake transport.
_PRICE_MODE_OK: str = "ok"            # string value -> PRESENT, usable
_PRICE_MODE_FLOAT: str = "float"      # float value -> PRESENT, full precision
_PRICE_MODE_ABSENT: str = "absent"    # no data.value -> MISSING
_PRICE_MODE_ZERO: str = "zero"        # value 0 -> PRESENT "0" (can never dispatch)
_PRICE_MODE_REFUSE: str = "refuse"    # transport refusal -> SOURCE_ERROR


def _now_utc() -> datetime:
    return datetime(2026, 6, 7, 7, 6, 40, tzinfo=timezone.utc)


def _unix(iso: str) -> int:
    return int(datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp())


def _price_body(mode: str) -> dict:
    if mode == _PRICE_MODE_ABSENT:
        return {"success": True, "data": {}}
    if mode == _PRICE_MODE_ZERO:
        value: object = 0
    elif mode == _PRICE_MODE_FLOAT:
        value = float(PROOF_CURRENT_PRICE)
    else:
        value = PROOF_CURRENT_PRICE
    return {
        "success": True,
        "data": {
            "value": value,
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
    """Path-routed fake transport serving price + token-overview + ohlcv. Opens
    NO socket. ``price_mode`` selects the ``/defi/price`` behavior;
    ``with_liquidity=False`` drops the token-overview liquidity field.
    """

    def __init__(
        self,
        *,
        price_mode: str = _PRICE_MODE_OK,
        with_liquidity: bool = True,
        fetched_at_utc: str = _FETCHED_AT,
    ) -> None:
        self._price_mode = price_mode
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
        if path == BIRDEYE_PATH_PRICE:
            if self._price_mode == _PRICE_MODE_REFUSE:
                return self._refused()
            return self._ok(_price_body(self._price_mode))
        if path == BIRDEYE_PATH_TOKEN_OVERVIEW:
            return self._ok(
                _token_overview_body(with_liquidity=self._with_liquidity)
            )
        if path == BIRDEYE_PATH_OHLCV:
            return self._ok(_ohlcv_body_with_peak())
        return self._refused()

    def _ok(self, body: dict) -> Stage29_2BirdeyeHttpResult:
        return Stage29_2BirdeyeHttpResult(
            refusal_reason=BIRDEYE_REFUSAL_REASON_NONE,
            http_status_code=200,
            body=body,
            fetched_at_utc=self._fetched_at_utc,
        )

    def _refused(self) -> Stage29_2BirdeyeHttpResult:
        return Stage29_2BirdeyeHttpResult(
            refusal_reason=BIRDEYE_REFUSAL_REASON_HTTP_TIMEOUT,
            http_status_code=0,
            body=None,
            fetched_at_utc=self._fetched_at_utc,
        )


def _endpoint_secret() -> Stage29_2BirdeyeEndpointSecret:
    return Stage29_2BirdeyeEndpointSecret(_api_key=_GOOD_KEY, _base_url=_GOOD_URL)


def _price_source(transport: FakeBirdeyeTransport) -> Stage29_2BirdeyePriceSource:
    # The COMMITTED real price source, injected DIRECTLY (no shim) -- the locked
    # Stage 30.11.20 key decision.
    return Stage29_2BirdeyePriceSource(
        transport=transport,
        endpoint_secret=_endpoint_secret(),
        timeout_seconds=10,
    )


def _market_context_source(transport: FakeBirdeyeTransport):
    return Stage30_4_3BirdeyeMarketContextSource(
        transport=transport,
        endpoint_secret=_endpoint_secret(),
        timeout_seconds=10,
    )


def _base_facts(**overrides) -> Stage30_11_18HarvestedCandidateFacts:
    # current_price carries the EMPTY placeholder (the real harvest has no price;
    # the seam under test fills it). The market fields are PLACEHOLDERS the
    # committed Stage 30.11.19 enrichment overwrites; migration_time is real.
    base = dict(
        token_mint=PROOF_MINT,
        candidate_id=PROOF_CANDIDATE_ID,
        migration_time_utc=PROOF_MIGRATION_ANCHOR,
        current_price=_PRICE_PLACEHOLDER,
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


def _run_proof(
    base_facts_list,
    *,
    price_mode: str = _PRICE_MODE_OK,
    with_liquidity: bool = True,
    **kwargs,
):
    transport = FakeBirdeyeTransport(
        price_mode=price_mode, with_liquidity=with_liquidity
    )
    return run_stage30_11_20_fake_current_price_enrichment_proof(
        base_facts_list,
        price_source=_price_source(transport),
        market_context_source=_market_context_source(transport),
        ath_transport=transport,
        ath_endpoint_secret=_endpoint_secret(),
        now_utc=_now_utc(),
        now_seconds=make_constant_clock(Decimal(0)),
        created_at_utc=PROOF_CREATED_AT,
        **kwargs,
    )


# ---------------------------------------------------------------------------
# 1. Default wiring + happy path: fill the price, enrich, project, dispatch
# ---------------------------------------------------------------------------


def test_proof_returns_wrapper() -> None:
    proof = _run_proof([_base_facts()])
    assert isinstance(proof, Stage30_11_20FakePriceEnrichmentSessionProofResult)
    assert isinstance(proof.ledger, InMemoryPingDedupeLedger)
    assert isinstance(proof.client, Stage30_11_5RecordingFakeTransportClient)
    assert isinstance(proof.report, Stage30_11_20PriceEnrichmentSessionReport)


def test_proof_fills_placeholder_price_and_dispatches_end_to_end() -> None:
    proof = _run_proof([_base_facts()])
    report = proof.report
    # Layer-0 (this seam): the real /defi/price read filled the placeholder.
    assert report.facts_seen == 1
    assert report.enriched == 1
    assert report.skipped == 0
    assert [e.decision for e in report.enrichment_events] == [
        PRICE_ENRICHMENT_DECISION_ENRICHED
    ]
    # The embedded Stage 30.11.19 report enriched the market-context bundle.
    downstream = report.downstream_report
    assert downstream.facts_seen == 1
    assert downstream.enriched == 1
    assert [e.decision for e in downstream.enrichment_events] == [
        ENRICHMENT_DECISION_ENRICHED
    ]
    # The embedded Stage 30.11.18 report projected + dispatched the fact.
    projected = downstream.downstream_report
    assert projected.facts_seen == 1
    assert projected.projected == 1
    assert projected.rejected_projection == 0
    assert [e.decision for e in projected.projection_events] == [
        PROJECTION_DECISION_PROJECTED
    ]
    assert projected.session_result.dispatched == 1
    assert projected.session_result.would_send_recorded == 1
    # ONE combined nested report, redacted at the top.
    assert report.redaction_status == STAGE30_11_20_REDACTION_STATUS_REDACTED
    # The recording fake client saw exactly the one dispatched would-send.
    assert proof.client.attempted == 1
    assert proof.client.token_mints == [PROOF_MINT]


def test_real_price_source_preserves_sub_micro_precision() -> None:
    # The /defi/price body serves the price as a FLOAT; the committed Stage 29.2
    # source canonicalizes it to full-precision decimal text and the enrichment
    # writes that text VERBATIM onto the facts copy.
    transport = FakeBirdeyeTransport(price_mode=_PRICE_MODE_FLOAT)
    result = enrich_facts_with_current_price(
        _base_facts(), price_source=_price_source(transport)
    )
    assert result.decision == PRICE_ENRICHMENT_DECISION_ENRICHED
    assert result.enriched_facts.current_price == PROOF_CURRENT_PRICE
    # Only the price changed; the market placeholders survive for Stage 30.11.19.
    assert result.enriched_facts.market_context_fetched_at_utc == (
        "2020-01-01T00:00:00Z"
    )


def test_proof_float_price_body_dispatches_end_to_end() -> None:
    proof = _run_proof([_base_facts()], price_mode=_PRICE_MODE_FLOAT)
    report = proof.report
    assert report.enriched == 1
    projected = report.downstream_report.downstream_report
    assert projected.session_result.dispatched == 1
    assert proof.client.attempted == 1


# ---------------------------------------------------------------------------
# 2. Unusable price reads fail closed and are NOT forwarded
# ---------------------------------------------------------------------------


def test_proof_skips_missing_price_and_does_not_forward() -> None:
    proof = _run_proof([_base_facts()], price_mode=_PRICE_MODE_ABSENT)
    report = proof.report
    assert report.facts_seen == 1
    assert report.enriched == 0
    assert report.skipped == 1
    assert [e.decision for e in report.enrichment_events] == [
        PRICE_ENRICHMENT_DECISION_SKIPPED_PRICE_MISSING
    ]
    # The skipped fact was NOT forwarded -> the embedded chain saw nothing.
    downstream = report.downstream_report
    assert downstream.facts_seen == 0
    assert downstream.downstream_report.facts_seen == 0
    assert downstream.downstream_report.session_result.dispatched == 0
    assert proof.client.attempted == 0
    assert report.redaction_status == STAGE30_11_20_REDACTION_STATUS_REDACTED


def test_proof_skips_refused_price_read_as_source_error() -> None:
    proof = _run_proof([_base_facts()], price_mode=_PRICE_MODE_REFUSE)
    report = proof.report
    assert report.enriched == 0
    assert [e.decision for e in report.enrichment_events] == [
        PRICE_ENRICHMENT_DECISION_SKIPPED_PRICE_SOURCE_ERROR
    ]
    assert report.downstream_report.facts_seen == 0
    assert proof.client.attempted == 0


def test_proof_skips_zero_price_as_invalid_value() -> None:
    # Stage 29.2 reports a literal-zero price as a valid PRESENT reading; it can
    # never dispatch, so the seam fails it closed with the precise token.
    proof = _run_proof([_base_facts()], price_mode=_PRICE_MODE_ZERO)
    report = proof.report
    assert report.enriched == 0
    assert [e.decision for e in report.enrichment_events] == [
        PRICE_ENRICHMENT_DECISION_SKIPPED_INVALID_PRICE_VALUE
    ]
    assert report.downstream_report.facts_seen == 0
    assert proof.client.attempted == 0


# ---------------------------------------------------------------------------
# 3. Chain order: a good price still fails closed downstream on a bad bundle
# ---------------------------------------------------------------------------


def test_proof_good_price_with_missing_liquidity_fails_at_stage_30_11_19() -> (
    None
):
    proof = _run_proof([_base_facts()], with_liquidity=False)
    report = proof.report
    # This seam enriched the price...
    assert report.enriched == 1
    assert [e.decision for e in report.enrichment_events] == [
        PRICE_ENRICHMENT_DECISION_ENRICHED
    ]
    # ...but the committed Stage 30.11.19 market-context layer failed closed on
    # the liquidity-less token-overview body, so nothing dispatched.
    downstream = report.downstream_report
    assert downstream.facts_seen == 1
    assert downstream.enriched == 0
    assert [e.decision for e in downstream.enrichment_events] == [
        ENRICHMENT_DECISION_SKIPPED_MISSING_LIQUIDITY_USD
    ]
    assert downstream.downstream_report.facts_seen == 0
    assert proof.client.attempted == 0
    assert report.redaction_status == STAGE30_11_20_REDACTION_STATUS_REDACTED


# ---------------------------------------------------------------------------
# 4. Mixed batch, in-run dedupe, and the bounded scan
# ---------------------------------------------------------------------------


def test_proof_mixed_batch_dispatches_only_the_usable_fact() -> None:
    other_mint = "So11111111111111111111111111111111111111112"

    class _SplitPriceTransport(FakeBirdeyeTransport):
        """Serves a usable price for PROOF_MINT and NO price value for the
        other mint, so one batch exercises ENRICHED + SKIPPED side by side.
        """

        def get(self, *, endpoint_secret, path, query_params, timeout_seconds):
            if (
                path == BIRDEYE_PATH_PRICE
                and query_params.get("address") != PROOF_MINT
            ):
                return self._ok(_price_body(_PRICE_MODE_ABSENT))
            return super().get(
                endpoint_secret=endpoint_secret,
                path=path,
                query_params=query_params,
                timeout_seconds=timeout_seconds,
            )

    transport = _SplitPriceTransport()
    proof = run_stage30_11_20_fake_current_price_enrichment_proof(
        [
            _base_facts(),
            _base_facts(
                token_mint=other_mint,
                candidate_id="stage30_11_20_cand_other",
            ),
        ],
        price_source=_price_source(transport),
        market_context_source=_market_context_source(transport),
        ath_transport=transport,
        ath_endpoint_secret=_endpoint_secret(),
        now_utc=_now_utc(),
        now_seconds=make_constant_clock(Decimal(0)),
        created_at_utc=PROOF_CREATED_AT,
    )
    report = proof.report
    assert report.facts_seen == 2
    assert report.enriched == 1
    assert report.skipped == 1
    assert [e.decision for e in report.enrichment_events] == [
        PRICE_ENRICHMENT_DECISION_ENRICHED,
        PRICE_ENRICHMENT_DECISION_SKIPPED_PRICE_MISSING,
    ]
    assert report.downstream_report.facts_seen == 1
    assert proof.client.attempted == 1
    assert proof.client.token_mints == [PROOF_MINT]


def test_proof_one_shared_ledger_blocks_the_in_run_duplicate() -> None:
    proof = _run_proof([_base_facts(), _base_facts()])
    report = proof.report
    # Both facts price-enriched...
    assert report.facts_seen == 2
    assert report.enriched == 2
    # ...both projected through the chain...
    projected = report.downstream_report.downstream_report
    assert projected.projected == 2
    # ...but the ONE shared dedupe ledger let only the FIRST dispatch.
    assert projected.session_result.dispatched == 1
    assert projected.session_result.dedupe_blocked == 1
    assert projected.session_result.would_send_recorded == 1
    assert proof.client.attempted == 1


def test_proof_scan_is_bounded_by_the_candidate_cap() -> None:
    proof = _run_proof([_base_facts() for _ in range(12)])
    report = proof.report
    # The default bounded config caps the scan at 10 facts.
    assert report.facts_seen == 10
    assert len(report.enrichment_events) == 10
    # Dedupe still allows only the first identical dispatch through.
    assert proof.client.attempted == 1


# ---------------------------------------------------------------------------
# 5. Injected config / ledger / client are honored
# ---------------------------------------------------------------------------


def test_proof_honors_injected_ledger_and_client() -> None:
    ledger = InMemoryPingDedupeLedger()
    client = Stage30_11_5RecordingFakeTransportClient(
        created_at_utc=PROOF_CREATED_AT
    )
    proof = _run_proof([_base_facts()], ledger=ledger, transport_client=client)
    assert proof.ledger is ledger
    assert proof.client is client
    assert client.attempted == 1
    # A second run over the SAME injected ledger is dedupe-blocked cross-run.
    proof_two = _run_proof([_base_facts()], ledger=ledger)
    projected_two = proof_two.report.downstream_report.downstream_report
    assert projected_two.session_result.dispatched == 0
    assert projected_two.session_result.dedupe_blocked == 1
    assert proof_two.client.attempted == 0

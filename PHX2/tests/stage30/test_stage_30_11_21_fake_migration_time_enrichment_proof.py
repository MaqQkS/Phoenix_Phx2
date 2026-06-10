"""Stage 30.11.21 fake migration-time enrichment proof tests.

Offline / fake-provider only. Proves the thin committed proof driver runs base
harvested facts through the migration-time enrichment adapter over the COMMITTED
Stage 30.11.9 mint-keyed migration evidence source (built HERE over a FAKE record
provider) -- and behind it the committed Stage 30.11.8 confirmation authority -- plus
the REAL committed Stage 29.2 price source + the REAL committed Stage 30.4.3
token-overview market-context source (both over a FAKE Birdeye transport): a
CONFIRMED migration fills the ``migration_time_utc=""`` placeholder with the confirmed
anchor and the enriched fact flows through the committed Stage 30.11.20 -> 30.11.19
-> 30.11.18 -> 30.11.17 chain to a RECORDED would-send; an unconfirmed migration
(missing / stale evidence) fails closed to the precise ``SKIPPED_*`` token and is NOT
forwarded -- all with NO real send.

The fake migration record provider + the committed Stage 30.11.9 source, the fake
Birdeye transport (price + token-overview + ohlcv), the Stage 29.2 price source, the
Stage 30.4.3 source, the clocks, and the base facts live HERE. No real send, no
network, no env read, no Stage 30.11.16 guard.
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
from PHX2.stage30.stage30_11_9_migration_evidence_source_adapter import (
    build_migration_evidence_source,
)
from PHX2.stage30.stage30_11_9_migration_evidence_source_models import (
    Stage30_11_9MigrationEvidenceRecord,
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
    ENRICHMENT_DECISION_ENRICHED as MC_ENRICHED,
)
from PHX2.stage30.stage30_11_20_current_price_enrichment_models import (
    PRICE_ENRICHMENT_DECISION_ENRICHED,
)
from PHX2.stage30.stage30_11_21_migration_time_enrichment_models import (
    MIGRATION_ENRICHMENT_DECISION_ENRICHED,
    MIGRATION_ENRICHMENT_DECISION_SKIPPED_MISSING_MIGRATION_EVIDENCE,
    MIGRATION_ENRICHMENT_DECISION_SKIPPED_STALE_MIGRATION_EVIDENCE,
    STAGE30_11_21_REDACTION_STATUS_REDACTED,
    Stage30_11_21MigrationEnrichmentSessionReport,
)
from PHX2.stage30.stage30_11_21_migration_time_enrichment_adapter import (
    enrich_facts_with_migration_time,
)
from PHX2.stage30.stage30_11_21_fake_migration_time_enrichment_proof import (
    Stage30_11_21FakeMigrationEnrichmentSessionProofResult,
    run_stage30_11_21_fake_migration_time_enrichment_proof,
)


_GOOD_KEY: str = "abcd1234efgh5678ijkl9012mnop3456"
_GOOD_URL: str = "https://aaaa-bbbb.example"
_FETCHED_AT: str = "2026-06-07T07:06:40+00:00"

# The placeholder the harvest ceremony carries BEFORE the migration seam fills it.
_MIGRATION_PLACEHOLDER: str = ""

# Evidence-source serving modes.
_EVIDENCE_MODE_OK: str = "ok"        # bound, COMPLETE, SAFE, fresh, valid anchor
_EVIDENCE_MODE_NONE: str = "none"    # no evidence for the mint -> MISSING
_EVIDENCE_MODE_STALE: str = "stale"  # COMPLETE but MIGRATION_STALE -> stale


def _now_utc() -> datetime:
    return datetime(2026, 6, 7, 7, 6, 40, tzinfo=timezone.utc)


def _unix(iso: str) -> int:
    return int(datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp())


# ---------------------------------------------------------------------------
# Committed Stage 30.11.9 migration evidence source over a FAKE record provider
# ---------------------------------------------------------------------------


def _migration_record(token_mint: str, *, stale: bool = False):
    return Stage30_11_9MigrationEvidenceRecord(
        token_mint=token_mint,
        measurement_status="COMPLETE",
        migration_event_time_utc=PROOF_MIGRATION_ANCHOR,
        warnings=("MIGRATION_STALE",) if stale else (),
        redaction_status="SAFE",
        source_ref=PROOF_MIGRATION_SOURCE,
    )


def _evidence_source(*, mode: str = _EVIDENCE_MODE_OK):
    def _provider(token_mint: object):
        if mode == _EVIDENCE_MODE_NONE:
            return None
        if mode == _EVIDENCE_MODE_STALE:
            return _migration_record(token_mint, stale=True)
        return _migration_record(token_mint)

    return build_migration_evidence_source(_provider)


# ---------------------------------------------------------------------------
# FAKE Birdeye transport (price + token-overview + ohlcv) -- as Stage 30.11.20
# ---------------------------------------------------------------------------


def _price_body() -> dict:
    return {
        "success": True,
        "data": {
            "value": float(PROOF_CURRENT_PRICE),
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


def _token_overview_body() -> dict:
    return {
        "success": True,
        "data": {
            "marketCap": int(PROOF_MARKET_CAP_USD),
            "liquidity": int(PROOF_LIQUIDITY_USD),
        },
    }


class FakeBirdeyeTransport(Stage29_2BirdeyeHttpTransport):
    """Path-routed fake transport serving price + token-overview + ohlcv. Opens NO
    socket.
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
        self.calls.append({"path": path})
        if path == BIRDEYE_PATH_PRICE:
            return self._ok(_price_body())
        if path == BIRDEYE_PATH_TOKEN_OVERVIEW:
            return self._ok(_token_overview_body())
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
    # migration_time_utc carries the EMPTY placeholder (the real harvest has no
    # migration anchor; the seam under test fills it from the confirmed evidence);
    # migration_confirmed=False proves the seam EARNS the confirmation. The price +
    # market fields are placeholders the committed Stage 30.11.20 / 30.11.19
    # enrichment fills.
    base = dict(
        token_mint=PROOF_MINT,
        candidate_id=PROOF_CANDIDATE_ID,
        migration_time_utc=_MIGRATION_PLACEHOLDER,
        current_price="",
        current_market_cap_usd="1",
        liquidity_usd="1",
        market_context_status="UNKNOWN",
        market_context_fetched_at_utc="2020-01-01T00:00:00Z",
        created_at_utc=PROOF_CREATED_AT,
        symbol_or_name=PROOF_SYMBOL,
        migration_source=None,
        age_display=PROOF_AGE_DISPLAY,
        migration_confirmed=False,
    )
    base.update(overrides)
    return Stage30_11_18HarvestedCandidateFacts(**base)


def _run_proof(base_facts_list, *, evidence_mode: str = _EVIDENCE_MODE_OK, **kwargs):
    transport = FakeBirdeyeTransport()
    return run_stage30_11_21_fake_migration_time_enrichment_proof(
        base_facts_list,
        evidence_source=_evidence_source(mode=evidence_mode),
        price_source=_price_source(transport),
        market_context_source=_market_context_source(transport),
        ath_transport=transport,
        ath_endpoint_secret=_endpoint_secret(),
        now_utc=_now_utc(),
        now_seconds=make_constant_clock(Decimal(0)),
        created_at_utc=PROOF_CREATED_AT,
        **kwargs,
    )


# Nested-report accessors (30.11.21 -> 30.11.20 -> 30.11.19 -> 30.11.18).
def _price_report(report):
    return report.downstream_report


def _mc_report(report):
    return report.downstream_report.downstream_report


def _projection_report(report):
    return report.downstream_report.downstream_report.downstream_report


# ---------------------------------------------------------------------------
# 1. Default wiring + happy path: confirm, fill the anchor, enrich, dispatch
# ---------------------------------------------------------------------------


def test_proof_returns_wrapper() -> None:
    proof = _run_proof([_base_facts()])
    assert isinstance(
        proof, Stage30_11_21FakeMigrationEnrichmentSessionProofResult
    )
    assert isinstance(proof.ledger, InMemoryPingDedupeLedger)
    assert isinstance(proof.client, Stage30_11_5RecordingFakeTransportClient)
    assert isinstance(
        proof.report, Stage30_11_21MigrationEnrichmentSessionReport
    )


def test_proof_confirms_fills_anchor_and_dispatches_end_to_end() -> None:
    proof = _run_proof([_base_facts()])
    report = proof.report
    # Layer-0 (this seam): the committed confirmation filled the anchor.
    assert report.facts_seen == 1
    assert report.enriched == 1
    assert report.skipped == 0
    assert [e.decision for e in report.enrichment_events] == [
        MIGRATION_ENRICHMENT_DECISION_ENRICHED
    ]
    # The embedded Stage 30.11.20 price layer enriched current_price.
    price = _price_report(report)
    assert price.facts_seen == 1
    assert price.enriched == 1
    assert [e.decision for e in price.enrichment_events] == [
        PRICE_ENRICHMENT_DECISION_ENRICHED
    ]
    # The embedded Stage 30.11.19 market-context layer enriched the bundle.
    mc = _mc_report(report)
    assert mc.facts_seen == 1
    assert mc.enriched == 1
    assert [e.decision for e in mc.enrichment_events] == [MC_ENRICHED]
    # The embedded Stage 30.11.18 layer projected + dispatched the fact.
    proj = _projection_report(report)
    assert proj.facts_seen == 1
    assert proj.projected == 1
    assert proj.rejected_projection == 0
    assert [e.decision for e in proj.projection_events] == [
        PROJECTION_DECISION_PROJECTED
    ]
    assert proj.session_result.dispatched == 1
    assert proj.session_result.would_send_recorded == 1
    # ONE combined nested report, redacted at the top.
    assert report.redaction_status == STAGE30_11_21_REDACTION_STATUS_REDACTED
    # The recording fake client saw exactly the one dispatched would-send.
    assert proof.client.attempted == 1
    assert proof.client.token_mints == [PROOF_MINT]


def test_confirmed_resolution_writes_the_anchor_onto_the_facts() -> None:
    # The unit seam: a CONFIRMED resolution fills migration_time_utc with the
    # confirmed anchor + earns migration_confirmed + carries the safe provenance.
    result = enrich_facts_with_migration_time(
        _base_facts(), evidence_source=_evidence_source()
    )
    assert result.decision == MIGRATION_ENRICHMENT_DECISION_ENRICHED
    enriched = result.enriched_facts
    assert enriched.migration_time_utc == PROOF_MIGRATION_ANCHOR
    assert enriched.migration_confirmed is True
    assert enriched.migration_source == PROOF_MIGRATION_SOURCE
    # The price placeholder is untouched here (Stage 30.11.20 fills it later).
    assert enriched.current_price == ""


# ---------------------------------------------------------------------------
# 2. Unconfirmed migrations fail closed and are NOT forwarded
# ---------------------------------------------------------------------------


def test_proof_skips_missing_evidence_and_does_not_forward() -> None:
    proof = _run_proof([_base_facts()], evidence_mode=_EVIDENCE_MODE_NONE)
    report = proof.report
    assert report.facts_seen == 1
    assert report.enriched == 0
    assert report.skipped == 1
    assert [e.decision for e in report.enrichment_events] == [
        MIGRATION_ENRICHMENT_DECISION_SKIPPED_MISSING_MIGRATION_EVIDENCE
    ]
    # The skipped fact was NOT forwarded -> the embedded chain saw nothing.
    assert _price_report(report).facts_seen == 0
    assert _mc_report(report).facts_seen == 0
    assert _projection_report(report).facts_seen == 0
    assert _projection_report(report).session_result.dispatched == 0
    assert proof.client.attempted == 0
    assert report.redaction_status == STAGE30_11_21_REDACTION_STATUS_REDACTED


def test_proof_skips_stale_migration_as_stale_token() -> None:
    proof = _run_proof([_base_facts()], evidence_mode=_EVIDENCE_MODE_STALE)
    report = proof.report
    assert report.enriched == 0
    assert [e.decision for e in report.enrichment_events] == [
        MIGRATION_ENRICHMENT_DECISION_SKIPPED_STALE_MIGRATION_EVIDENCE
    ]
    assert _price_report(report).facts_seen == 0
    assert proof.client.attempted == 0


# ---------------------------------------------------------------------------
# 3. Chain order: a confirmed migration still fails closed downstream on a bad
#    price body (proves 30.11.21 wraps 30.11.20)
# ---------------------------------------------------------------------------


def test_proof_confirmed_migration_with_bad_price_fails_at_stage_30_11_20() -> (
    None
):
    class _NoPriceTransport(FakeBirdeyeTransport):
        def get(self, *, endpoint_secret, path, query_params, timeout_seconds):
            if path == BIRDEYE_PATH_PRICE:
                # PRESENT body with no data.value -> Stage 29.2 MISSING price.
                return self._ok({"success": True, "data": {}})
            return super().get(
                endpoint_secret=endpoint_secret,
                path=path,
                query_params=query_params,
                timeout_seconds=timeout_seconds,
            )

    transport = _NoPriceTransport()
    proof = run_stage30_11_21_fake_migration_time_enrichment_proof(
        [_base_facts()],
        evidence_source=_evidence_source(),
        price_source=_price_source(transport),
        market_context_source=_market_context_source(transport),
        ath_transport=transport,
        ath_endpoint_secret=_endpoint_secret(),
        now_utc=_now_utc(),
        now_seconds=make_constant_clock(Decimal(0)),
        created_at_utc=PROOF_CREATED_AT,
    )
    report = proof.report
    # This seam confirmed + enriched the migration...
    assert report.enriched == 1
    assert [e.decision for e in report.enrichment_events] == [
        MIGRATION_ENRICHMENT_DECISION_ENRICHED
    ]
    # ...but the committed Stage 30.11.20 price layer failed closed on the
    # value-less /defi/price body, so nothing dispatched.
    price = _price_report(report)
    assert price.facts_seen == 1
    assert price.enriched == 0
    assert _mc_report(report).facts_seen == 0
    assert proof.client.attempted == 0
    assert report.redaction_status == STAGE30_11_21_REDACTION_STATUS_REDACTED


# ---------------------------------------------------------------------------
# 4. Mixed batch, in-run dedupe, and the bounded scan
# ---------------------------------------------------------------------------


def test_proof_mixed_batch_dispatches_only_the_confirmed_fact() -> None:
    other_mint = "So11111111111111111111111111111111111111112"

    # A provider that yields evidence ONLY for PROOF_MINT (the other mint has none).
    def _provider(token_mint: object):
        if token_mint == PROOF_MINT:
            return _migration_record(token_mint)
        return None

    transport = FakeBirdeyeTransport()
    proof = run_stage30_11_21_fake_migration_time_enrichment_proof(
        [
            _base_facts(),
            _base_facts(
                token_mint=other_mint,
                candidate_id="stage30_11_21_cand_other",
            ),
        ],
        evidence_source=build_migration_evidence_source(_provider),
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
        MIGRATION_ENRICHMENT_DECISION_ENRICHED,
        MIGRATION_ENRICHMENT_DECISION_SKIPPED_MISSING_MIGRATION_EVIDENCE,
    ]
    assert _price_report(report).facts_seen == 1
    assert proof.client.attempted == 1
    assert proof.client.token_mints == [PROOF_MINT]


def test_proof_one_shared_ledger_blocks_the_in_run_duplicate() -> None:
    proof = _run_proof([_base_facts(), _base_facts()])
    report = proof.report
    # Both facts confirmed + migration-enriched...
    assert report.facts_seen == 2
    assert report.enriched == 2
    # ...both projected through the chain...
    proj = _projection_report(report)
    assert proj.projected == 2
    # ...but the ONE shared dedupe ledger let only the FIRST dispatch.
    assert proj.session_result.dispatched == 1
    assert proj.session_result.dedupe_blocked == 1
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
# 5. Injected ledger / client are honored
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
    assert _projection_report(proof_two.report).session_result.dispatched == 0
    assert (
        _projection_report(proof_two.report).session_result.dedupe_blocked == 1
    )
    assert proof_two.client.attempted == 0

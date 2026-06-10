"""Stage 30.11.22 real-fed dry-run adapter tests.

Offline / fake-provider only. Proves the Stage 30.11.22 bridge maps a committed
Stage 30.11.6 candidate projection onto a Stage 30.11.18 enrichment base fact, and
that the dry-run wrapper drives the committed Stage 30.11.6 harvest seam (over a FAKE
assembler + record flattener + bounded event source) -> the bridge -> the committed
Stage 30.11.21 -> 30.11.20 -> 30.11.19 -> 30.11.18 -> 30.11.17 chain (over the
committed Stage 30.11.9 evidence source + Stage 29.2 price source + Stage 30.4.3
market-context source, all over a FAKE transport) to a RECORDED would-send -- with
NO real send. A confirmed + priced + market-present candidate dispatches; an
unconfirmed migration is skipped at Layer-0 and surfaced in the migration skip
histogram; a raising assembler is a harvest skip; an in-run duplicate is
dedupe-blocked; the no-real-send attestation pins the recording-fake transport.

The fakes (assembler, flattener, events, evidence provider, transport, sources,
clocks) live HERE. No real send, no network, no env read, no Stage 30.11.16 guard.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict, List, Mapping, Optional

import pytest

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
from PHX2.stage30.stage30_11_6_candidate_source_models import (
    Stage30_11_6CandidateProjection,
)
from PHX2.stage30.stage30_11_9_migration_evidence_source_adapter import (
    build_migration_evidence_source,
)
from PHX2.stage30.stage30_11_9_migration_evidence_source_models import (
    Stage30_11_9MigrationEvidenceRecord,
)
from PHX2.stage30.stage30_11_13_fake_composer_proof import (
    PROOF_CREATED_AT,
    PROOF_CURRENT_PRICE,
    PROOF_LATER_LOWER,
    PROOF_LIQUIDITY_USD,
    PROOF_MARKET_CAP_USD,
    PROOF_MIGRATION_ANCHOR,
    PROOF_MIGRATION_SOURCE,
    PROOF_MINT,
    PROOF_PEAK_ATH,
)
from PHX2.stage30.stage30_11_15_ping_dedupe_ledger import (
    InMemoryPingDedupeLedger,
)
from PHX2.stage30.stage30_11_17_operator_curated_candidate_list_models import (
    Stage30_11_17SessionConfig,
)
from PHX2.stage30.stage30_11_18_harvested_facts_models import (
    Stage30_11_18HarvestedCandidateFacts,
)
from PHX2.stage30.stage30_11_22_real_fed_dry_run_adapter import (
    Stage30_11_22RealFedDryRunError,
    project_harvested_candidate_to_base_facts,
    run_stage30_11_22_real_fed_dry_run,
)
from PHX2.stage30.stage30_11_22_real_fed_dry_run_models import (
    STAGE30_11_22_PENDING_ENRICHMENT,
    STAGE30_11_22_PENDING_MARKET_CONTEXT_STATUS,
    STAGE30_11_22_REDACTION_STATUS_REDACTED,
    Stage30_11_22RealFedDryRunReport,
)


_GOOD_KEY: str = "abcd1234efgh5678ijkl9012mnop3456"
_GOOD_URL: str = "https://aaaa-bbbb.example"
_FETCHED_AT: str = "2026-06-07T07:06:40+00:00"
_OTHER_MINT: str = "So11111111111111111111111111111111111111112"


def _now_utc() -> datetime:
    return datetime(2026, 6, 7, 7, 6, 40, tzinfo=timezone.utc)


def _unix(iso: str) -> int:
    return int(datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp())


# ---------------------------------------------------------------------------
# Migration evidence source over a FAKE record provider (mint-keyed)
# ---------------------------------------------------------------------------


def _migration_record(token_mint: str):
    return Stage30_11_9MigrationEvidenceRecord(
        token_mint=token_mint,
        measurement_status="COMPLETE",
        migration_event_time_utc=PROOF_MIGRATION_ANCHOR,
        warnings=(),
        redaction_status="SAFE",
        source_ref=PROOF_MIGRATION_SOURCE,
    )


def _evidence_source(*, confirmed_mints=(PROOF_MINT,)):
    def _provider(token_mint: object):
        if token_mint in confirmed_mints:
            return _migration_record(token_mint)
        return None

    return build_migration_evidence_source(_provider)


# ---------------------------------------------------------------------------
# FAKE Birdeye transport (price + token-overview + ohlcv) -- opens NO socket
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
    """Path-routed fake transport serving price + token-overview + ohlcv."""

    def __init__(self, *, fetched_at_utc: str = _FETCHED_AT) -> None:
        self._fetched_at_utc = fetched_at_utc

    def get(
        self,
        *,
        endpoint_secret: Stage29_2BirdeyeEndpointSecret,
        path: str,
        query_params: Mapping[str, str],
        timeout_seconds: int,
    ) -> Stage29_2BirdeyeHttpResult:
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


# ---------------------------------------------------------------------------
# Harvest front-end fakes (assembler + record flattener over a mint event source)
# ---------------------------------------------------------------------------


def _projection_fields(token_mint: str, *, omit_market_cap: bool = False):
    fields: Dict[str, object] = {
        "token_mint": token_mint,
        "pair_type": "SOL",
        "tier_hint": "Tier 1",
        "drawdown_from_ath": "0.55",
        "migration_status": "PRESENT",
        "ath_status": "PRESENT",
        "market_context_status": "PRESENT",
        "current_market_cap_usd": "12345.67",
        "post_migration_ath_verified": True,
        "source_ref": "ref",
        "created_at_utc": PROOF_CREATED_AT,
    }
    if omit_market_cap:
        del fields["current_market_cap_usd"]
    return fields


class _FakeRecord:
    def __init__(self, candidate_id: str, fields: Dict[str, object]) -> None:
        self.candidate_id = candidate_id
        self.fields = dict(fields)


class _FakeAssembler:
    """Builds a record per event; a ``RAISE`` scenario simulates a failed assembly."""

    def __init__(self, scenario_for_mint: Optional[Dict[str, str]] = None) -> None:
        self.assemble_calls = 0
        self._scenario = scenario_for_mint or {}

    def assemble(self, normalized_event: object, *, candidate_id: str) -> object:
        self.assemble_calls += 1
        token_mint = str(normalized_event)
        scenario = self._scenario.get(token_mint, "OK")
        if scenario == "RAISE":
            raise RuntimeError("fake assembler raising")
        return _FakeRecord(
            candidate_id,
            _projection_fields(token_mint, omit_market_cap=(scenario == "OMIT_MC")),
        )


def _flatten(record: object) -> Dict[str, object]:
    assert isinstance(record, _FakeRecord)
    fields = dict(record.fields)
    fields["candidate_id"] = record.candidate_id
    return fields


# ---------------------------------------------------------------------------
# Dry-run driver
# ---------------------------------------------------------------------------


def _run(events, *, scenario_for_mint=None, confirmed_mints=(PROOF_MINT,), **kwargs):
    transport = FakeBirdeyeTransport()
    return run_stage30_11_22_real_fed_dry_run(
        events,
        assembler=_FakeAssembler(scenario_for_mint=scenario_for_mint),
        record_flattener=_flatten,
        evidence_source=_evidence_source(confirmed_mints=confirmed_mints),
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
# 1. The bridge: projection -> base fact
# ---------------------------------------------------------------------------


def _projection(token_mint: str, candidate_id: str) -> Stage30_11_6CandidateProjection:
    return Stage30_11_6CandidateProjection(
        candidate_id=candidate_id,
        token_mint=token_mint,
        pair_type="SOL",
        tier_hint="Tier 1",
        drawdown_from_ath=Decimal("0.55"),
        migration_status="PRESENT",
        ath_status="PRESENT",
        market_context_status="PRESENT",
        current_market_cap_usd=Decimal("12345.67"),
        post_migration_ath_verified=True,
        source_ref="ref",
        created_at_utc=PROOF_CREATED_AT,
    )


def test_bridge_carries_identity_verbatim_and_stamps_sentinels() -> None:
    projection = _projection(PROOF_MINT, "stage30_11_6_cand_000000")
    base = project_harvested_candidate_to_base_facts(
        projection, created_at_utc=PROOF_CREATED_AT
    )
    assert isinstance(base, Stage30_11_18HarvestedCandidateFacts)
    # Real on-chain identity carried verbatim.
    assert base.token_mint == PROOF_MINT
    assert base.candidate_id == "stage30_11_6_cand_000000"
    assert base.created_at_utc == PROOF_CREATED_AT
    # Every enrichment-filled field is a sentinel (never the projection's values).
    assert base.migration_time_utc == STAGE30_11_22_PENDING_ENRICHMENT
    assert base.current_price == STAGE30_11_22_PENDING_ENRICHMENT
    assert base.current_market_cap_usd == STAGE30_11_22_PENDING_ENRICHMENT
    assert base.liquidity_usd == STAGE30_11_22_PENDING_ENRICHMENT
    assert base.market_context_fetched_at_utc == STAGE30_11_22_PENDING_ENRICHMENT
    assert base.market_context_status == STAGE30_11_22_PENDING_MARKET_CONTEXT_STATUS
    # migration_confirmed is True but NOT trusted (30.11.21 re-confirms from evidence);
    # the optional provenance / symbol / age are left for the enrichment / unset.
    assert base.migration_confirmed is True
    assert base.symbol_or_name is None
    assert base.migration_source is None
    assert base.age_display is None


# ---------------------------------------------------------------------------
# 2. Happy path: a real-fed candidate flows end-to-end to a RECORDED would-send
# ---------------------------------------------------------------------------


def test_dry_run_happy_path_dispatches_end_to_end() -> None:
    report = _run((PROOF_MINT,))
    assert isinstance(report, Stage30_11_22RealFedDryRunReport)
    # Harvest front-end.
    assert report.events_seen == 1
    assert report.candidates_harvested == 1
    assert report.harvest_skipped_assembly_failed == 0
    assert report.harvest_skipped_projection_rejected == 0
    # Bridge.
    assert report.base_facts_built == 1
    # Layer-0 enrichment (migration -> price -> market).
    assert report.migration_enriched == 1
    assert report.migration_skipped == 0
    assert report.price_enriched == 1
    assert report.market_enriched == 1
    # Layer-1 projection + Layer-2 compose/dispatch.
    assert report.projected == 1
    assert report.rejected_projection == 0
    assert report.composed == 1
    assert report.dispatched == 1
    assert report.dedupe_blocked == 0
    assert report.would_send_recorded == 1
    assert report.stop_reason == "COMPLETED_ALL_CANDIDATES"
    assert report.redaction_status == STAGE30_11_22_REDACTION_STATUS_REDACTED


def test_dry_run_no_real_send_attestation() -> None:
    report = _run((PROOF_MINT,))
    att = report.attestation
    assert att.real_send_performed is False
    assert att.real_send_guard_invoked is False
    assert att.would_send_recorded == 1
    # The safe defaults: recording fake client + in-memory ledger.
    assert att.transport_client_kind == "Stage30_11_5RecordingFakeTransportClient"
    assert att.ledger_kind == "InMemoryPingDedupeLedger"


# ---------------------------------------------------------------------------
# 3. Skips: an unconfirmed migration + a failed assembly are surfaced, not sent
# ---------------------------------------------------------------------------


def test_dry_run_unconfirmed_migration_is_skipped_and_histogrammed() -> None:
    # _OTHER_MINT has no evidence -> Layer-0 migration skip; NOT forwarded.
    report = _run((_OTHER_MINT,), confirmed_mints=())
    assert report.candidates_harvested == 1
    assert report.base_facts_built == 1
    assert report.migration_enriched == 0
    assert report.migration_skipped == 1
    assert report.migration_skip_histogram == (
        ("SKIPPED_MISSING_MIGRATION_EVIDENCE", 1),
    )
    # The skipped fact never reached the price / market / projection layers.
    assert report.price_enriched == 0
    assert report.market_enriched == 0
    assert report.projected == 0
    assert report.dispatched == 0
    assert report.would_send_recorded == 0
    assert report.redaction_status == STAGE30_11_22_REDACTION_STATUS_REDACTED


def test_dry_run_raising_assembler_is_a_harvest_skip() -> None:
    report = _run(
        ("mint-bad", PROOF_MINT),
        scenario_for_mint={"mint-bad": "RAISE"},
    )
    assert report.events_seen == 2
    assert report.candidates_harvested == 1
    assert report.harvest_skipped_assembly_failed == 1
    assert report.base_facts_built == 1
    # The one good candidate still dispatched.
    assert report.dispatched == 1
    assert report.would_send_recorded == 1


# ---------------------------------------------------------------------------
# 4. Dedupe + bounds + fail-closed config
# ---------------------------------------------------------------------------


def test_dry_run_in_run_duplicate_is_dedupe_blocked() -> None:
    report = _run((PROOF_MINT, PROOF_MINT))
    assert report.candidates_harvested == 2
    assert report.base_facts_built == 2
    assert report.migration_enriched == 2
    assert report.projected == 2
    # The ONE shared in-memory ledger let only the first dispatch.
    assert report.dispatched == 1
    assert report.dedupe_blocked == 1
    assert report.would_send_recorded == 1


def test_dry_run_is_bounded_by_max_harvest() -> None:
    report = _run(tuple(f"mint-{i}" for i in range(8)), max_harvest=3)
    # The harvest pulled only 3 events (a single bounded for-loop stops at the cap).
    assert report.events_seen == 3
    assert report.base_facts_built <= 3


def test_dry_run_invalid_config_fails_closed() -> None:
    bad_config = Stage30_11_17SessionConfig(
        max_candidates=999, max_compositions=999, created_at_utc=PROOF_CREATED_AT
    )
    with pytest.raises(Stage30_11_22RealFedDryRunError):
        _run((PROOF_MINT,), config=bad_config)


def test_dry_run_honors_injected_ledger_for_cross_run_dedupe() -> None:
    ledger = InMemoryPingDedupeLedger()
    first = _run((PROOF_MINT,), ledger=ledger)
    assert first.dispatched == 1
    # A second run over the SAME injected ledger is dedupe-blocked cross-run.
    second = _run((PROOF_MINT,), ledger=ledger)
    assert second.dispatched == 0
    assert second.dedupe_blocked == 1
    assert second.would_send_recorded == 0

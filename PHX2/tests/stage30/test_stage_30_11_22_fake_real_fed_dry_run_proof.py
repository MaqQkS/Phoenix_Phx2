"""Stage 30.11.22 fake real-fed dry-run proof tests.

Offline / fake-provider only. Proves the thin committed proof driver builds the
default in-memory ledger + recording FAKE client and runs an INJECTED bounded event
source through the committed Stage 30.11.6 harvest seam -> the Stage 30.11.22 bridge
-> the committed enrichment chain to a RECORDED would-send, returning the report +
the client + the shared ledger so a test can assert the recorded tally (NEVER a real
send) and the cross-run dedupe.

The fakes (assembler, flattener, events, evidence provider, transport, sources,
clocks) live HERE. No real send, no network, no env read, no Stage 30.11.16 guard.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict, Mapping

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
from PHX2.stage30.stage30_11_22_real_fed_dry_run_models import (
    STAGE30_11_22_REDACTION_STATUS_REDACTED,
    Stage30_11_22RealFedDryRunReport,
)
from PHX2.stage30.stage30_11_22_fake_real_fed_dry_run_proof import (
    Stage30_11_22FakeRealFedDryRunProofResult,
    run_stage30_11_22_fake_real_fed_dry_run_proof,
)


_GOOD_KEY: str = "abcd1234efgh5678ijkl9012mnop3456"
_GOOD_URL: str = "https://aaaa-bbbb.example"
_FETCHED_AT: str = "2026-06-07T07:06:40+00:00"


def _now_utc() -> datetime:
    return datetime(2026, 6, 7, 7, 6, 40, tzinfo=timezone.utc)


def _unix(iso: str) -> int:
    return int(datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp())


def _migration_record(token_mint: str):
    return Stage30_11_9MigrationEvidenceRecord(
        token_mint=token_mint,
        measurement_status="COMPLETE",
        migration_event_time_utc=PROOF_MIGRATION_ANCHOR,
        warnings=(),
        redaction_status="SAFE",
        source_ref=PROOF_MIGRATION_SOURCE,
    )


def _evidence_source():
    def _provider(token_mint: object):
        if token_mint == PROOF_MINT:
            return _migration_record(token_mint)
        return None

    return build_migration_evidence_source(_provider)


class FakeBirdeyeTransport(Stage29_2BirdeyeHttpTransport):
    """Path-routed fake transport serving price + token-overview + ohlcv."""

    def get(
        self,
        *,
        endpoint_secret: Stage29_2BirdeyeEndpointSecret,
        path: str,
        query_params: Mapping[str, str],
        timeout_seconds: int,
    ) -> Stage29_2BirdeyeHttpResult:
        if path == BIRDEYE_PATH_PRICE:
            return self._ok(
                {
                    "success": True,
                    "data": {
                        "value": float(PROOF_CURRENT_PRICE),
                        "updateUnixTime": int(_now_utc().timestamp()),
                    },
                }
            )
        if path == BIRDEYE_PATH_TOKEN_OVERVIEW:
            return self._ok(
                {
                    "success": True,
                    "data": {
                        "marketCap": int(PROOF_MARKET_CAP_USD),
                        "liquidity": int(PROOF_LIQUIDITY_USD),
                    },
                }
            )
        if path == BIRDEYE_PATH_OHLCV:
            return self._ok(
                {
                    "success": True,
                    "data": {
                        "items": [
                            {
                                "h": PROOF_PEAK_ATH,
                                "unixTime": _unix("2026-06-06T06:15:00Z"),
                            },
                            {
                                "h": PROOF_LATER_LOWER,
                                "unixTime": _unix("2026-06-06T07:30:00Z"),
                            },
                        ]
                    },
                }
            )
        return Stage29_2BirdeyeHttpResult(
            refusal_reason=BIRDEYE_REFUSAL_REASON_HTTP_TIMEOUT,
            http_status_code=0,
            body=None,
            fetched_at_utc=_FETCHED_AT,
        )

    def _ok(self, body: dict) -> Stage29_2BirdeyeHttpResult:
        return Stage29_2BirdeyeHttpResult(
            refusal_reason=BIRDEYE_REFUSAL_REASON_NONE,
            http_status_code=200,
            body=body,
            fetched_at_utc=_FETCHED_AT,
        )


def _endpoint_secret() -> Stage29_2BirdeyeEndpointSecret:
    return Stage29_2BirdeyeEndpointSecret(_api_key=_GOOD_KEY, _base_url=_GOOD_URL)


class _FakeRecord:
    def __init__(self, candidate_id: str, fields: Dict[str, object]) -> None:
        self.candidate_id = candidate_id
        self.fields = dict(fields)


class _FakeAssembler:
    def assemble(self, normalized_event: object, *, candidate_id: str) -> object:
        token_mint = str(normalized_event)
        return _FakeRecord(
            candidate_id,
            {
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
            },
        )


def _flatten(record: object) -> Dict[str, object]:
    assert isinstance(record, _FakeRecord)
    fields = dict(record.fields)
    fields["candidate_id"] = record.candidate_id
    return fields


def _run_proof(events=(PROOF_MINT,), **kwargs):
    transport = FakeBirdeyeTransport()
    return run_stage30_11_22_fake_real_fed_dry_run_proof(
        events,
        assembler=_FakeAssembler(),
        record_flattener=_flatten,
        evidence_source=_evidence_source(),
        price_source=Stage29_2BirdeyePriceSource(
            transport=transport,
            endpoint_secret=_endpoint_secret(),
            timeout_seconds=10,
        ),
        market_context_source=Stage30_4_3BirdeyeMarketContextSource(
            transport=transport,
            endpoint_secret=_endpoint_secret(),
            timeout_seconds=10,
        ),
        ath_transport=transport,
        ath_endpoint_secret=_endpoint_secret(),
        now_utc=_now_utc(),
        now_seconds=make_constant_clock(Decimal(0)),
        created_at_utc=PROOF_CREATED_AT,
        **kwargs,
    )


# ---------------------------------------------------------------------------
# 1. The proof returns the wrapper with usable handles
# ---------------------------------------------------------------------------


def test_proof_returns_wrapper_with_handles() -> None:
    proof = _run_proof()
    assert isinstance(proof, Stage30_11_22FakeRealFedDryRunProofResult)
    assert isinstance(proof.report, Stage30_11_22RealFedDryRunReport)
    assert isinstance(proof.client, Stage30_11_5RecordingFakeTransportClient)
    assert isinstance(proof.ledger, InMemoryPingDedupeLedger)


def test_proof_happy_path_records_one_would_send() -> None:
    proof = _run_proof()
    assert proof.report.dispatched == 1
    assert proof.report.would_send_recorded == 1
    assert proof.report.redaction_status == STAGE30_11_22_REDACTION_STATUS_REDACTED
    # The recording fake client saw exactly the one dispatched would-send.
    assert proof.client.attempted == 1
    assert proof.client.token_mints == [PROOF_MINT]


# ---------------------------------------------------------------------------
# 2. Injected ledger / client are honored (cross-run dedupe)
# ---------------------------------------------------------------------------


def test_proof_honors_injected_ledger_and_client() -> None:
    ledger = InMemoryPingDedupeLedger()
    client = Stage30_11_5RecordingFakeTransportClient(created_at_utc=PROOF_CREATED_AT)
    proof = _run_proof(ledger=ledger, transport_client=client)
    assert proof.ledger is ledger
    assert proof.client is client
    assert client.attempted == 1
    # A second run over the SAME injected ledger is dedupe-blocked cross-run.
    proof_two = _run_proof(ledger=ledger)
    assert proof_two.report.dispatched == 0
    assert proof_two.report.dedupe_blocked == 1
    assert proof_two.client.attempted == 0

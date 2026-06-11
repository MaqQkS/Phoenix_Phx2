"""Stage 30.11.23 fake discovered migration-evidence bridge proof tests.

Offline / fake-provider only. Proves the END-TO-END NON-manual path: a fake Stage
29.5.7 sanitized migration-evidence summary (NEVER a hand-fed mint) -> the committed
Stage 30.11.23 bridge -> the committed Stage 30.11.22 real-fed dry-run chain (over a
FAKE Birdeye transport + a recording FAKE dispatch client + an in-memory ledger) -> a
RECORDED would-send, NEVER a real send. The dispatched mint comes from the summary's
``token_mint`` -- there is NO ``CURATED_MINT`` / ``CURATED_MIGRATION_TIME_UTC``
argument anywhere in the path. Doubles as the Stage 30.11.23 composition proof.

The fakes (summaries, transport, sources, clocks) live HERE. No real send, no network,
no env read, no Stage 30.11.16 guard.
"""

from __future__ import annotations

from dataclasses import dataclass
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
from PHX2.stage30.stage30_11_23_fake_migration_evidence_candidate_bridge_proof import (
    Stage30_11_23FakeRealFedDryRunProofResult,
    run_stage30_11_23_fake_real_fed_dry_run_proof,
)
from PHX2.stage30.stage30_11_23_migration_evidence_candidate_bridge_models import (
    STAGE30_11_23_REDACTION_STATUS_REDACTED,
)


_GOOD_KEY: str = "abcd1234efgh5678ijkl9012mnop3456"
_GOOD_URL: str = "https://aaaa-bbbb.example"
_FETCHED_AT: str = "2026-06-07T07:06:40+00:00"


def _now_utc() -> datetime:
    return datetime(2026, 6, 7, 7, 6, 40, tzinfo=timezone.utc)


def _unix(iso: str) -> int:
    return int(datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp())


@dataclass(frozen=True)
class _Summary:
    """A fake Stage 29.5.7 sanitized migration-evidence summary (read duck-typed)."""

    token_mint: object
    measurement_status: object
    migration_event_time_utc: object
    warnings: object
    redaction_status: object
    source_ref: object


def _good_summary(token_mint: object = PROOF_MINT) -> _Summary:
    return _Summary(
        token_mint=token_mint,
        measurement_status="COMPLETE",
        migration_event_time_utc=PROOF_MIGRATION_ANCHOR,
        warnings=(),
        redaction_status="SAFE",
        source_ref=PROOF_MIGRATION_SOURCE,
    )


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


def _run_proof(summaries=None, **kwargs):
    if summaries is None:
        summaries = (_good_summary(),)
    transport = FakeBirdeyeTransport()
    return run_stage30_11_23_fake_real_fed_dry_run_proof(
        summaries,
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
# 1. The proof returns the bundle + the wrapper handles
# ---------------------------------------------------------------------------


def test_proof_returns_bundle_and_handles() -> None:
    proof = _run_proof()
    assert isinstance(proof, Stage30_11_23FakeRealFedDryRunProofResult)
    assert isinstance(proof.report, Stage30_11_22RealFedDryRunReport)
    assert isinstance(proof.client, Stage30_11_5RecordingFakeTransportClient)
    assert isinstance(proof.ledger, InMemoryPingDedupeLedger)
    # The embedded bridge bundle bridged the one discovered summary.
    assert proof.inputs.report.summaries_seen == 1
    assert proof.inputs.report.bridged == 1
    assert proof.inputs.report.redaction_status == (
        STAGE30_11_23_REDACTION_STATUS_REDACTED
    )


# ---------------------------------------------------------------------------
# 2. Happy path: one would-send, recorded only, from the DISCOVERED mint
# ---------------------------------------------------------------------------


def test_proof_happy_path_records_one_would_send_from_discovered_mint() -> None:
    proof = _run_proof()
    assert proof.report.dispatched == 1
    assert proof.report.would_send_recorded == 1
    assert proof.report.redaction_status == STAGE30_11_22_REDACTION_STATUS_REDACTED
    # No real send -- the recording fake client + pinned attestation flags.
    assert proof.report.attestation.real_send_performed is False
    assert proof.report.attestation.real_send_guard_invoked is False
    assert proof.client.attempted == 1
    # The dispatched mint is the DISCOVERED summary mint, not a hand-fed CURATED_MINT.
    assert proof.client.token_mints == [PROOF_MINT]
    assert proof.inputs.events[0].token_mint == PROOF_MINT
    assert proof.client.token_mints[0] == _good_summary().token_mint


def test_dispatched_mint_traces_to_the_summary_not_a_curated_constant() -> None:
    # Feed a DIFFERENT discovered mint -- a distinct VALID 44-char base58 mint. The
    # committed Birdeye price source rejects a malformed / wrong-length mint, so the
    # discovered mint must be real-shaped to enrich; the dispatched mint then follows
    # the summary, proving nothing in the chain hardcodes PROOF_MINT.
    other = "Dz9km9VRfjeeowsMR1YmjR1GhxXHBatAEVhggxYVfaNe"
    proof = _run_proof((_good_summary(token_mint=other),))
    assert proof.inputs.report.bridged == 1
    assert proof.report.dispatched == 1
    assert proof.client.token_mints == [other]


# ---------------------------------------------------------------------------
# 3. A malformed summary is bridged-skipped and never dispatches
# ---------------------------------------------------------------------------


def test_malformed_summary_is_not_bridged_and_not_dispatched() -> None:
    bad = _Summary(
        token_mint=PROOF_MINT,
        measurement_status="COMPLETE",
        migration_event_time_utc=PROOF_MIGRATION_ANCHOR,
        warnings=None,  # malformed -> SKIPPED_MALFORMED_WARNINGS
        redaction_status="SAFE",
        source_ref=PROOF_MIGRATION_SOURCE,
    )
    proof = _run_proof((bad,))
    assert proof.inputs.report.bridged == 0
    assert proof.report.dispatched == 0
    assert proof.report.would_send_recorded == 0
    assert proof.client.attempted == 0


# ---------------------------------------------------------------------------
# 4. Injected ledger / client are honored (cross-run dedupe)
# ---------------------------------------------------------------------------


def test_proof_honors_injected_ledger_and_client() -> None:
    ledger = InMemoryPingDedupeLedger()
    client = Stage30_11_5RecordingFakeTransportClient(
        created_at_utc=PROOF_CREATED_AT
    )
    proof = _run_proof(ledger=ledger, transport_client=client)
    assert proof.ledger is ledger
    assert proof.client is client
    assert client.attempted == 1
    # A second run over the SAME injected ledger is dedupe-blocked cross-run.
    proof_two = _run_proof(ledger=ledger)
    assert proof_two.report.dispatched == 0
    assert proof_two.report.dedupe_blocked == 1
    assert proof_two.client.attempted == 0

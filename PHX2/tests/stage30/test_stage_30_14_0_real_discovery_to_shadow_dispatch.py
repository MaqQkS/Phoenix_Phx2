"""Stage 30.14.0 real-discovery-replay -> shadow-dispatch orchestrator tests.

Offline / SYNTHETIC / fake-provider only. Proves the WHOLE Build 26.0 path -- a SYNTHETIC
discovered migration evidence record replayed from memory, auto-seeded, then flowed through
the committed Stage 30.11.23 -> 30.11.22 recheck/fake-send chain (over FAKE Birdeye-style
sources + a recording FAKE dispatch client + an in-memory ledger) -- reaches a RECORDED
would-send, NEVER a real send, with the dispatched mint tracing to the synthetic discovered
mint. A non-pump record and a fault capture are filtered/failed-closed BEFORE any dispatch;
a non-fake provider, a non-replay-source, and an out-of-bounds locked cap are refused before
anything is driven.

The synthetic record + the fakes (Birdeye transport, sources, clocks) live HERE. No real
send, no network, no env, no Stage 30.11.16 guard, no durable ledger.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Mapping

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
from PHX2.stage29.stage29_5_migration_models import (
    MIGRATION_SOURCE_HELIUS_WS,
    MIGRATION_STATUS_PRESENT,
    REFUSAL_REASON_MALFORMED_PAYLOAD,
    Stage29_5MigrationEvidenceRecord,
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
    PROOF_MINT,
    PROOF_PEAK_ATH,
)
from PHX2.stage30.stage30_11_15_ping_dedupe_ledger import (
    InMemoryPingDedupeLedger,
)
from PHX2.stage30.stage30_11_22_real_fed_dry_run_models import (
    STAGE30_11_22_REDACTION_STATUS_REDACTED,
)
from PHX2.stage30.stage30_14_0_replay_discovery_models import (
    STAGE30_14_REDACTED_UNSAFE_ID,
    STAGE30_14_REDACTION_STATUS_REDACTED,
)
from PHX2.stage30.stage30_14_0_replay_discovery_source import (
    Stage30_14ReplayDiscoverySource,
)
from PHX2.stage30.stage30_14_0_real_discovery_to_shadow_dispatch import (
    Stage30_14FakeOnly,
    Stage30_14ShadowDispatchError,
    run_stage30_14_0_real_discovery_to_shadow_dispatch,
)


_SYNTH_PUMP_MINT: str = PROOF_MINT[:-4] + "pump"
_NON_PUMP_MINT: str = PROOF_MINT  # real base58, ends "faNe" -> not a pump suffix
_POOL: str = "P" * 44
_PROG: str = "G" * 44
_QUOTE: str = "Q" * 44

_GOOD_KEY: str = "abcd1234efgh5678ijkl9012mnop3456"
_GOOD_URL: str = "https://aaaa-bbbb.example"
_FETCHED_AT: str = "2026-06-07T07:06:40+00:00"


def _now_utc() -> datetime:
    return datetime(2026, 6, 7, 7, 6, 40, tzinfo=timezone.utc)


def _unix(iso: str) -> int:
    return int(datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp())


def _synthetic_record(
    base_mint: str = _SYNTH_PUMP_MINT,
) -> Stage29_5MigrationEvidenceRecord:
    return Stage29_5MigrationEvidenceRecord(
        migration_status=MIGRATION_STATUS_PRESENT,
        migration_source=MIGRATION_SOURCE_HELIUS_WS,
        base_mint=base_mint,
        pool_account=_POOL,
        pool_program_id=_PROG,
        quote_mint=_QUOTE,
        migration_timestamp_utc=PROOF_MIGRATION_ANCHOR,
        migration_slot=318000000,
        migration_signature="build26-synth-sig",
        observed_at_utc=PROOF_CREATED_AT,
        source_event_ref="build26_0_synthetic_source_ref",
    )


class _FakeBirdeyeTransport(Stage29_2BirdeyeHttpTransport, Stage30_14FakeOnly):
    """Path-routed fake-only-marked transport serving price + token-overview + ohlcv
    (mint-agnostic)."""

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


class _FakePriceSource(Stage29_2BirdeyePriceSource, Stage30_14FakeOnly):
    """Fake-only-marked Stage 29.2 price source over the fake Birdeye transport."""


class _FakeMarketContextSource(
    Stage30_4_3BirdeyeMarketContextSource, Stage30_14FakeOnly
):
    """Fake-only-marked Stage 30.4.3 market-context source over the fake transport."""


def _endpoint_secret() -> Stage29_2BirdeyeEndpointSecret:
    return Stage29_2BirdeyeEndpointSecret(_api_key=_GOOD_KEY, _base_url=_GOOD_URL)


def _run_source(source, **kwargs):
    bird = _FakeBirdeyeTransport()
    return run_stage30_14_0_real_discovery_to_shadow_dispatch(
        source,
        price_source=_FakePriceSource(
            transport=bird,
            endpoint_secret=_endpoint_secret(),
            timeout_seconds=10,
        ),
        market_context_source=_FakeMarketContextSource(
            transport=bird,
            endpoint_secret=_endpoint_secret(),
            timeout_seconds=10,
        ),
        ath_transport=bird,
        ath_endpoint_secret=_endpoint_secret(),
        now_utc=_now_utc(),
        now_seconds=make_constant_clock(Decimal(0)),
        created_at_utc=PROOF_CREATED_AT,
        **kwargs,
    )


def _run(records, **kwargs):
    return _run_source(Stage30_14ReplayDiscoverySource(records), **kwargs)


# ---------------------------------------------------------------------------
# 1. Happy path: a synthetic pump record flows replay -> seed -> fake dispatch
# ---------------------------------------------------------------------------


def test_synthetic_pump_mint_flows_to_fake_dispatch() -> None:
    result = _run((_synthetic_record(),))

    # Discovery + auto-seed: exactly one synthetic pump mint seeded.
    assert result.seed_result.summary.accepted == 1
    assert result.seed_result.seeded_summaries[0].token_mint == _SYNTH_PUMP_MINT

    # Bridge + dry-run: the discovered summary bridged and reached ONE recorded would-send
    # (a FAKE dispatch), never a real send.
    assert result.dry_run.inputs.report.bridged == 1
    assert result.dry_run.report.dispatched == 1
    assert result.dry_run.report.would_send_recorded == 1
    assert (
        result.dry_run.report.redaction_status
        == STAGE30_11_22_REDACTION_STATUS_REDACTED
    )

    # No real send.
    assert result.dry_run.report.attestation.real_send_performed is False
    assert result.dry_run.report.attestation.real_send_guard_invoked is False

    # In-memory ledger + recording FAKE client only.
    assert isinstance(result.dry_run.ledger, InMemoryPingDedupeLedger)
    assert isinstance(
        result.dry_run.client, Stage30_11_5RecordingFakeTransportClient
    )

    # The dispatched mint traces to the synthetic discovered mint.
    assert result.dry_run.client.token_mints == [_SYNTH_PUMP_MINT]


def test_happy_path_trace_links_discovered_to_dispatched() -> None:
    trace = _run((_synthetic_record(),)).trace
    assert trace.discovered_mint == _SYNTH_PUMP_MINT
    assert trace.dispatched_mint == _SYNTH_PUMP_MINT
    assert trace.mint_traces_through is True
    assert trace.seeds_accepted == 1
    assert trace.rechecks_bridged == 1
    assert trace.dispatched == 1
    assert trace.would_send_recorded == 1
    assert trace.real_send_performed is False
    assert trace.real_send_guard_invoked is False
    # ledger_kind is in-memory only; transport_client_kind is recording fake only.
    assert "InMemory" in trace.ledger_kind
    assert "Fake" in trace.transport_client_kind
    assert trace.ledger_kind != STAGE30_14_REDACTED_UNSAFE_ID
    assert trace.transport_client_kind != STAGE30_14_REDACTED_UNSAFE_ID
    # Redaction clean.
    assert trace.redaction_status == STAGE30_14_REDACTION_STATUS_REDACTED


# ---------------------------------------------------------------------------
# 2. The pump-suffix filter gates the path
# ---------------------------------------------------------------------------


def test_non_pump_record_is_filtered_before_any_dispatch() -> None:
    result = _run((_synthetic_record(base_mint=_NON_PUMP_MINT),))
    assert result.seed_result.summary.accepted == 0
    assert result.seed_result.summary.rejected == 1
    assert result.dry_run.inputs.report.bridged == 0
    assert result.dry_run.report.dispatched == 0
    assert result.dry_run.report.would_send_recorded == 0
    assert result.dry_run.client.attempted == 0
    assert result.trace.mint_traces_through is False
    assert result.trace.discovered_mint == ""
    assert result.trace.dispatched_mint == ""


# ---------------------------------------------------------------------------
# 3. A fault capture fails closed end-to-end
# ---------------------------------------------------------------------------


def test_fault_capture_fails_closed_with_no_dispatch() -> None:
    source = Stage30_14ReplayDiscoverySource(
        (), fault_reason=REFUSAL_REASON_MALFORMED_PAYLOAD
    )
    result = _run_source(source)
    assert result.seed_result.summary.error == 1
    assert result.seed_result.summary.accepted == 0
    assert result.dry_run.report.dispatched == 0
    assert result.dry_run.report.would_send_recorded == 0
    assert result.dry_run.client.attempted == 0
    assert result.trace.mint_traces_through is False


# ---------------------------------------------------------------------------
# 4. Fail-closed guards: non-fake provider / non-replay-source / locked caps
# ---------------------------------------------------------------------------


def test_non_fake_price_source_is_refused_before_anything_runs() -> None:
    bird = _FakeBirdeyeTransport()
    # A real (unmarked) price source must be refused.
    real_price = Stage29_2BirdeyePriceSource(
        transport=bird, endpoint_secret=_endpoint_secret(), timeout_seconds=10
    )
    with pytest.raises(Stage30_14ShadowDispatchError):
        run_stage30_14_0_real_discovery_to_shadow_dispatch(
            Stage30_14ReplayDiscoverySource((_synthetic_record(),)),
            price_source=real_price,
            market_context_source=_FakeMarketContextSource(
                transport=bird,
                endpoint_secret=_endpoint_secret(),
                timeout_seconds=10,
            ),
            ath_transport=bird,
            ath_endpoint_secret=_endpoint_secret(),
            now_utc=_now_utc(),
            now_seconds=make_constant_clock(Decimal(0)),
            created_at_utc=PROOF_CREATED_AT,
        )


def test_non_replay_source_is_refused() -> None:
    with pytest.raises(Stage30_14ShadowDispatchError):
        _run_source(object())


def test_out_of_bounds_caps_are_refused() -> None:
    for bad in (
        {"max_seed": 2},
        {"max_rechecks": 2},
        {"max_fake_dispatches": 2},
        {"max_seed": 0},
    ):
        with pytest.raises(Stage30_14ShadowDispatchError):
            _run((_synthetic_record(),), **bad)

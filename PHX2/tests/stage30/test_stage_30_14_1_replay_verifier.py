"""Stage 30.14.1 replay-verifier tests.

End-to-end Build 26.1C: load a SYNTHETIC ``build26_capture_evidence.jsonl`` artifact, then
replay each reconstructed record through the committed Stage 30.14.0 path to a FAKE dispatch.
Proves ``dispatched == 1`` per record, the dispatched mint traces to the discovered mint,
``real_send_performed == False`` / ``real_send_guard_invoked == False``, and the persisted
attestation round-trips against the committed re-derived summary -- with no real send, no
durable ledger, and FAKE provider sources only.

The fakes (Birdeye transport / sources / clocks) + proof constants live HERE (tests may build
provider fakes), mirroring the committed Stage 30.14.0 orchestrator test.
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
from PHX2.stage30.stage30_4_3_market_context_birdeye_source import (
    Stage30_4_3BirdeyeMarketContextSource,
)
from PHX2.stage30.stage30_11_2_fake_runtime_gate_proof import (
    make_constant_clock,
)
from PHX2.stage30.stage30_11_13_fake_composer_proof import (
    PROOF_CREATED_AT,
    PROOF_CURRENT_PRICE,
    PROOF_LATER_LOWER,
    PROOF_LIQUIDITY_USD,
    PROOF_MARKET_CAP_USD,
    PROOF_PEAK_ATH,
)
from PHX2.stage30.stage30_14_0_real_discovery_to_shadow_dispatch import (
    Stage30_14FakeOnly,
    Stage30_14ShadowDispatchError,
)
from PHX2.stage30.stage30_14_1_evidence_artifact_loader import (
    Stage30_14_1EvidenceArtifactLoader,
)
from PHX2.stage30.stage30_14_1_evidence_artifact_models import (
    STAGE30_14_1_REDACTION_STATUS_REDACTED,
    VERIFY_ERROR_INVALID_MAX_REPLAY,
    VERIFY_ERROR_NOT_A_LOAD_RESULT,
    VERIFY_ERROR_TOO_MANY_REPLAY_RECORDS,
)
from PHX2.stage30.stage30_14_1_replay_verifier import (
    Stage30_14_1ReplayVerifyError,
    run_stage30_14_1_replay_verify,
)
from PHX2.tests.stage30.stage30_14_1_synthetic_evidence_fixtures import (
    SYNTH_PUMP_MINT,
    build_second_valid_evidence_obj,
    build_valid_evidence_obj,
    write_jsonl,
)


_GOOD_KEY: str = "abcd1234efgh5678ijkl9012mnop3456"
_GOOD_URL: str = "https://aaaa-bbbb.example"
_FETCHED_AT: str = "2026-06-07T07:06:40+00:00"


def _now_utc() -> datetime:
    return datetime(2026, 6, 7, 7, 6, 40, tzinfo=timezone.utc)


def _unix(iso: str) -> int:
    return int(datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp())


class _FakeBirdeyeTransport(Stage29_2BirdeyeHttpTransport, Stage30_14FakeOnly):
    """Path-routed fake-only-marked transport serving price + token-overview + ohlcv
    (mint-agnostic). Mirrors the committed Stage 30.14.0 orchestrator test fake."""

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


def _load(tmp_path, objs, **loader_kwargs):
    path = write_jsonl(tmp_path / "build26_capture_evidence.jsonl", objs)
    loader = Stage30_14_1EvidenceArtifactLoader(**loader_kwargs)
    return loader.load_evidence_from_path(path, created_at_utc=PROOF_CREATED_AT)


def _verify(load_result, *, price_source=None, **kwargs):
    bird = _FakeBirdeyeTransport()
    if price_source is None:
        price_source = _FakePriceSource(
            transport=bird,
            endpoint_secret=_endpoint_secret(),
            timeout_seconds=10,
        )
    return run_stage30_14_1_replay_verify(
        load_result,
        price_source=price_source,
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


# ---------------------------------------------------------------------------
# 1. Happy path: load -> replay -> fake dispatch, mint traces through
# ---------------------------------------------------------------------------


def test_loaded_synthetic_record_reaches_fake_dispatch(tmp_path) -> None:
    load_result = _load(tmp_path, [build_valid_evidence_obj()])
    assert load_result.summary.accepted == 1

    result = _verify(load_result)
    assert result.records_replayed == 1
    assert result.dispatched_total == 1
    assert result.all_traced_through is True
    assert result.all_no_real_send is True
    assert result.all_roundtrip_ok is True
    assert result.redaction_status == STAGE30_14_1_REDACTION_STATUS_REDACTED

    outcome = result.outcomes[0]
    assert outcome.token_mint == SYNTH_PUMP_MINT
    assert outcome.seeds_accepted == 1
    assert outcome.dispatched == 1
    assert outcome.would_send_recorded == 1
    assert outcome.mint_traces_through is True
    assert outcome.real_send_performed is False
    assert outcome.real_send_guard_invoked is False
    assert outcome.attestation_roundtrip_ok is True


def test_committed_shadow_result_pins_no_real_send(tmp_path) -> None:
    load_result = _load(tmp_path, [build_valid_evidence_obj()])
    result = _verify(load_result)
    shadow = result.shadow_results[0]
    # The committed dry-run report carries the no-real-send attestation.
    assert shadow.dry_run.report.dispatched == 1
    assert shadow.dry_run.report.would_send_recorded == 1
    assert shadow.dry_run.report.attestation.real_send_performed is False
    assert shadow.dry_run.report.attestation.real_send_guard_invoked is False
    assert shadow.trace.discovered_mint == SYNTH_PUMP_MINT
    assert shadow.trace.dispatched_mint == SYNTH_PUMP_MINT


# ---------------------------------------------------------------------------
# 2. Multiple records each dispatch (one committed pass per record)
# ---------------------------------------------------------------------------


def test_two_records_each_reach_fake_dispatch(tmp_path) -> None:
    load_result = _load(
        tmp_path,
        [build_valid_evidence_obj(), build_second_valid_evidence_obj()],
    )
    assert load_result.summary.accepted == 2
    result = _verify(load_result)
    assert result.records_replayed == 2
    assert result.dispatched_total == 2
    assert result.all_traced_through is True
    assert result.all_no_real_send is True
    assert result.all_roundtrip_ok is True


# ---------------------------------------------------------------------------
# 3. Fail-closed guards
# ---------------------------------------------------------------------------


def test_non_fake_price_source_surfaces_committed_error(tmp_path) -> None:
    load_result = _load(tmp_path, [build_valid_evidence_obj()])
    bird = _FakeBirdeyeTransport()
    # A real (unmarked) price source must be refused by the committed orchestrator.
    real_price = Stage29_2BirdeyePriceSource(
        transport=bird, endpoint_secret=_endpoint_secret(), timeout_seconds=10
    )
    with pytest.raises(Stage30_14ShadowDispatchError):
        _verify(load_result, price_source=real_price)


def test_not_a_load_result_raises() -> None:
    with pytest.raises(Stage30_14_1ReplayVerifyError) as exc:
        _verify(object())
    assert exc.value.reason == VERIFY_ERROR_NOT_A_LOAD_RESULT


def test_invalid_max_replay_raises(tmp_path) -> None:
    load_result = _load(tmp_path, [build_valid_evidence_obj()])
    with pytest.raises(Stage30_14_1ReplayVerifyError) as exc:
        _verify(load_result, max_replay=0)
    assert exc.value.reason == VERIFY_ERROR_INVALID_MAX_REPLAY


def test_too_many_replay_records_raises(tmp_path) -> None:
    load_result = _load(
        tmp_path,
        [build_valid_evidence_obj(), build_second_valid_evidence_obj()],
    )
    with pytest.raises(Stage30_14_1ReplayVerifyError) as exc:
        _verify(load_result, max_replay=1)
    assert exc.value.reason == VERIFY_ERROR_TOO_MANY_REPLAY_RECORDS


# ---------------------------------------------------------------------------
# 4. Empty load result -> nothing replayed, nothing dispatched
# ---------------------------------------------------------------------------


def test_empty_load_result_dispatches_nothing(tmp_path) -> None:
    load_result = _load(tmp_path, [build_valid_evidence_obj(token_mint="x" * 8)])
    # token_mint too short -> rejected -> no accepted records.
    assert load_result.summary.accepted == 0
    result = _verify(load_result)
    assert result.records_replayed == 0
    assert result.dispatched_total == 0
    assert result.shadow_results == ()

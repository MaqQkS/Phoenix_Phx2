"""Stage 29.2 Birdeye probe orchestrator pin tests.

Drives the three probe modes via fake HTTP transport injection.
Confirms no-invention audit, drawdown computation, freshness
combination, and per-mode bounded budgets.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Mapping

import pytest

from PHX2.stage29.birdeye_constants import (
    BIRDEYE_PATH_OHLCV,
    BIRDEYE_PATH_PRICE,
    DEFAULT_HTTP_TIMEOUT_SECONDS,
)
from PHX2.stage29.stage29_2_birdeye_http_transport import (
    Stage29_2BirdeyeHttpResult,
    Stage29_2BirdeyeHttpTransport,
)
from PHX2.stage29.stage29_2_birdeye_models import (
    BIRDEYE_REFUSAL_REASON_API_KEY_MISSING,
    BIRDEYE_REFUSAL_REASON_LIVE_FLAG_NOT_SET,
    BIRDEYE_REFUSAL_REASON_LOOKBACK_INVALID,
    BIRDEYE_REFUSAL_REASON_MINT_REJECTED_SAFE_SHAPE,
    BIRDEYE_REFUSAL_REASON_MODE_INVALID,
    BIRDEYE_REFUSAL_REASON_NONE,
    BIRDEYE_REFUSAL_REASON_TRANSPORT_FACTORY_NOT_CALLABLE,
    NO_INVENTION_AUDIT_FAILED,
    NO_INVENTION_AUDIT_PASSED,
)
from PHX2.stage29.stage29_2_birdeye_probe import (
    run_stage29_2_birdeye_probe,
)
from PHX2.stage29.stage29_2_birdeye_probe_models import (
    PROBE_MODE_HTTP_CONNECT_ONLY,
    PROBE_MODE_ONE_PUMPSWAP_MINT_PRICE_ATH_DRY_RUN,
    PROBE_MODE_READINESS_ONLY,
    PROBE_STATUS_CONNECTED,
    PROBE_STATUS_FAILED,
    PROBE_STATUS_FETCHED_NO_ATH_EVIDENCE,
    PROBE_STATUS_FETCHED_PRICE_ONLY,
    PROBE_STATUS_FETCHED_WITH_PRICE_AND_ATH,
    PROBE_STATUS_NOT_READY,
    PROBE_STATUS_READY,
    PROBE_STATUS_SKIPPED,
)
from PHX2.stage29.stage29_2_birdeye_readiness import (
    ENV_NAME_ALLOW_LIVE_HTTP,
    ENV_NAME_BIRDEYE_API_KEY,
    ENV_NAME_BIRDEYE_BASE_URL,
)


GOOD_MINT = "Aaa1111111111111111111111111111111111111111"
GOOD_API_KEY = "abcd1234efgh5678ijkl9012mnop3456"
GOOD_BASE_URL = "https://aaaa-bbbb.example"


def _env(*, live="1", api_key=GOOD_API_KEY, base_url=GOOD_BASE_URL):
    out: dict[str, str] = {}
    if api_key is not None:
        out[ENV_NAME_BIRDEYE_API_KEY] = api_key
    if base_url is not None:
        out[ENV_NAME_BIRDEYE_BASE_URL] = base_url
    if live is not None:
        out[ENV_NAME_ALLOW_LIVE_HTTP] = live
    return out


class ScriptedTransport(Stage29_2BirdeyeHttpTransport):
    """Transport that returns a scripted response per path."""

    def __init__(
        self,
        responses: dict[str, Stage29_2BirdeyeHttpResult],
    ) -> None:
        self._responses = responses
        self.calls: list[dict] = []

    def get(
        self,
        *,
        endpoint_secret,
        path: str,
        query_params: Mapping[str, str],
        timeout_seconds: int,
    ) -> Stage29_2BirdeyeHttpResult:
        self.calls.append(
            {
                "path": path,
                "query_params": dict(query_params),
                "timeout_seconds": timeout_seconds,
            }
        )
        if path not in self._responses:
            raise AssertionError(
                f"Test scripted no response for {path}"
            )
        return self._responses[path]


def _ok_price_body(value=0.5):
    return Stage29_2BirdeyeHttpResult(
        refusal_reason=BIRDEYE_REFUSAL_REASON_NONE,
        http_status_code=200,
        body={
            "success": True,
            "data": {"value": value, "updateUnixTime": 1716638400},
        },
        fetched_at_utc="2026-05-25T12:00:00+00:00",
    )


def _ok_ohlcv_body(items):
    return Stage29_2BirdeyeHttpResult(
        refusal_reason=BIRDEYE_REFUSAL_REASON_NONE,
        http_status_code=200,
        body={"success": True, "data": {"items": items}},
        fetched_at_utc="2026-05-25T12:00:00+00:00",
    )


FROZEN_NOW = datetime(2026, 5, 25, 12, 0, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Mode 1: READINESS_ONLY
# ---------------------------------------------------------------------------


def test_readiness_only_ready():
    rec = run_stage29_2_birdeye_probe(
        mode=PROBE_MODE_READINESS_ONLY,
        env=_env(),
    )
    assert rec.mode == PROBE_MODE_READINESS_ONLY
    assert rec.status == PROBE_STATUS_READY
    assert rec.refusal_reason == BIRDEYE_REFUSAL_REASON_NONE
    assert rec.handoff_ready is True
    assert rec.live_flag_set is True


def test_readiness_only_not_ready_missing_key():
    rec = run_stage29_2_birdeye_probe(
        mode=PROBE_MODE_READINESS_ONLY,
        env=_env(api_key=None),
    )
    assert rec.status == PROBE_STATUS_NOT_READY
    assert rec.refusal_reason == (
        BIRDEYE_REFUSAL_REASON_API_KEY_MISSING
    )
    assert rec.handoff_ready is False


def test_readiness_only_does_not_require_live_flag():
    rec = run_stage29_2_birdeye_probe(
        mode=PROBE_MODE_READINESS_ONLY,
        env=_env(live=None),
    )
    assert rec.status == PROBE_STATUS_READY
    assert rec.live_flag_set is False
    assert rec.handoff_ready is True


# ---------------------------------------------------------------------------
# Mode 2: HTTP_CONNECT_ONLY
# ---------------------------------------------------------------------------


def test_http_connect_only_connected():
    transport = ScriptedTransport(
        {BIRDEYE_PATH_PRICE: _ok_price_body()}
    )
    rec = run_stage29_2_birdeye_probe(
        mode=PROBE_MODE_HTTP_CONNECT_ONLY,
        env=_env(),
        transport_factory=lambda: transport,
    )
    assert rec.status == PROBE_STATUS_CONNECTED
    assert rec.refusal_reason == BIRDEYE_REFUSAL_REASON_NONE
    assert rec.http_status_code == 200
    assert rec.handoff_ready is True
    # The connect-only mode targets WRAPPED_SOL_MINT, not the
    # operator-supplied base_mint.
    assert transport.calls[0]["path"] == BIRDEYE_PATH_PRICE
    assert (
        transport.calls[0]["query_params"]["address"]
        == "So11111111111111111111111111111111111111112"
    )


def test_http_connect_only_skipped_when_no_live_flag():
    transport = ScriptedTransport(
        {BIRDEYE_PATH_PRICE: _ok_price_body()}
    )
    rec = run_stage29_2_birdeye_probe(
        mode=PROBE_MODE_HTTP_CONNECT_ONLY,
        env=_env(live=None),
        transport_factory=lambda: transport,
    )
    assert rec.status == PROBE_STATUS_SKIPPED
    assert rec.refusal_reason == (
        BIRDEYE_REFUSAL_REASON_LIVE_FLAG_NOT_SET
    )
    assert transport.calls == []


def test_http_connect_only_skipped_when_not_ready():
    transport = ScriptedTransport(
        {BIRDEYE_PATH_PRICE: _ok_price_body()}
    )
    rec = run_stage29_2_birdeye_probe(
        mode=PROBE_MODE_HTTP_CONNECT_ONLY,
        env=_env(api_key=None),
        transport_factory=lambda: transport,
    )
    assert rec.status == PROBE_STATUS_SKIPPED
    assert rec.refusal_reason == (
        BIRDEYE_REFUSAL_REASON_API_KEY_MISSING
    )


def test_http_connect_only_failed_when_transport_fails():
    err = Stage29_2BirdeyeHttpResult(
        refusal_reason="HTTP_STATUS_REJECTED",
        http_status_code=401,
        body=None,
        fetched_at_utc="2026-05-25T12:00:00+00:00",
    )
    transport = ScriptedTransport({BIRDEYE_PATH_PRICE: err})
    rec = run_stage29_2_birdeye_probe(
        mode=PROBE_MODE_HTTP_CONNECT_ONLY,
        env=_env(),
        transport_factory=lambda: transport,
    )
    assert rec.status == PROBE_STATUS_FAILED


# ---------------------------------------------------------------------------
# Mode 3: ONE_PUMPSWAP_MINT_PRICE_ATH_DRY_RUN
# ---------------------------------------------------------------------------


def test_mode3_fetched_with_price_and_ath():
    transport = ScriptedTransport(
        {
            BIRDEYE_PATH_PRICE: _ok_price_body(value=0.5),
            BIRDEYE_PATH_OHLCV: _ok_ohlcv_body(
                [
                    {"h": 0.1, "unixTime": 1716000000},
                    {"h": 0.8, "unixTime": 1716010000},
                ]
            ),
        }
    )
    rec = run_stage29_2_birdeye_probe(
        mode=PROBE_MODE_ONE_PUMPSWAP_MINT_PRICE_ATH_DRY_RUN,
        base_mint=GOOD_MINT,
        env=_env(),
        transport_factory=lambda: transport,
        lookback_hours=24,
        ohlcv_type="15m",
        now_utc=FROZEN_NOW,
    )
    assert rec.status == PROBE_STATUS_FETCHED_WITH_PRICE_AND_ATH
    assert rec.refusal_reason == BIRDEYE_REFUSAL_REASON_NONE
    assert rec.handoff_ready is True
    assert rec.evidence is not None
    assert rec.evidence.price_snapshot.price_value == "0.5"
    assert rec.evidence.ath_snapshot.ath_value == "0.8"
    # drawdown = (0.5 - 0.8) / 0.8 = -0.375
    assert rec.evidence.drawdown_ratio is not None
    assert rec.evidence.drawdown_ratio.startswith("-0.375")
    assert rec.evidence.no_invention_audit == (
        NO_INVENTION_AUDIT_PASSED
    )
    # Two outbound calls: price + ohlcv
    paths_called = [c["path"] for c in transport.calls]
    assert paths_called == [
        BIRDEYE_PATH_PRICE,
        BIRDEYE_PATH_OHLCV,
    ]


def test_mode3_fetched_price_only_when_ath_missing():
    transport = ScriptedTransport(
        {
            BIRDEYE_PATH_PRICE: _ok_price_body(value=0.5),
            BIRDEYE_PATH_OHLCV: _ok_ohlcv_body([]),
        }
    )
    rec = run_stage29_2_birdeye_probe(
        mode=PROBE_MODE_ONE_PUMPSWAP_MINT_PRICE_ATH_DRY_RUN,
        base_mint=GOOD_MINT,
        env=_env(),
        transport_factory=lambda: transport,
        lookback_hours=24,
        ohlcv_type="15m",
        now_utc=FROZEN_NOW,
    )
    assert rec.status == PROBE_STATUS_FETCHED_PRICE_ONLY
    assert rec.evidence is not None
    assert rec.evidence.price_snapshot.price_value == "0.5"
    assert rec.evidence.ath_snapshot.ath_value is None
    # drawdown is None because ATH is None
    assert rec.evidence.drawdown_ratio is None
    # no invention: price PRESENT must have value; ATH MISSING
    # must have None; both hold -> PASSED
    assert rec.evidence.no_invention_audit == (
        NO_INVENTION_AUDIT_PASSED
    )


def test_mode3_failed_when_both_missing():
    transport = ScriptedTransport(
        {
            BIRDEYE_PATH_PRICE: Stage29_2BirdeyeHttpResult(
                refusal_reason=(
                    "HTTP_STATUS_REJECTED"
                ),
                http_status_code=429,
                body=None,
                fetched_at_utc="2026-05-25T12:00:00+00:00",
            ),
            BIRDEYE_PATH_OHLCV: Stage29_2BirdeyeHttpResult(
                refusal_reason=(
                    "HTTP_STATUS_REJECTED"
                ),
                http_status_code=429,
                body=None,
                fetched_at_utc="2026-05-25T12:00:00+00:00",
            ),
        }
    )
    rec = run_stage29_2_birdeye_probe(
        mode=PROBE_MODE_ONE_PUMPSWAP_MINT_PRICE_ATH_DRY_RUN,
        base_mint=GOOD_MINT,
        env=_env(),
        transport_factory=lambda: transport,
        lookback_hours=24,
        ohlcv_type="15m",
        now_utc=FROZEN_NOW,
    )
    assert rec.status == PROBE_STATUS_FAILED
    assert rec.handoff_ready is False
    # The evidence is still built (carrying None values) so
    # the operator audit can see both refusal paths
    assert rec.evidence is not None
    assert rec.evidence.price_snapshot.price_value is None
    assert rec.evidence.ath_snapshot.ath_value is None
    assert rec.evidence.no_invention_audit == (
        NO_INVENTION_AUDIT_PASSED
    )


def test_mode3_failed_on_unsafe_mint():
    transport = ScriptedTransport(
        {BIRDEYE_PATH_PRICE: _ok_price_body()}
    )
    rec = run_stage29_2_birdeye_probe(
        mode=PROBE_MODE_ONE_PUMPSWAP_MINT_PRICE_ATH_DRY_RUN,
        base_mint="bad",
        env=_env(),
        transport_factory=lambda: transport,
        lookback_hours=24,
        ohlcv_type="15m",
        now_utc=FROZEN_NOW,
    )
    assert rec.status == PROBE_STATUS_FAILED
    assert rec.refusal_reason == (
        BIRDEYE_REFUSAL_REASON_MINT_REJECTED_SAFE_SHAPE
    )
    # Transport NEVER called
    assert transport.calls == []


def test_mode3_failed_on_unsafe_lookback():
    transport = ScriptedTransport(
        {BIRDEYE_PATH_PRICE: _ok_price_body()}
    )
    rec = run_stage29_2_birdeye_probe(
        mode=PROBE_MODE_ONE_PUMPSWAP_MINT_PRICE_ATH_DRY_RUN,
        base_mint=GOOD_MINT,
        env=_env(),
        transport_factory=lambda: transport,
        lookback_hours=0,
        ohlcv_type="15m",
        now_utc=FROZEN_NOW,
    )
    assert rec.status == PROBE_STATUS_FAILED
    assert rec.refusal_reason == (
        BIRDEYE_REFUSAL_REASON_LOOKBACK_INVALID
    )
    assert transport.calls == []


# ---------------------------------------------------------------------------
# Defensive paths
# ---------------------------------------------------------------------------


def test_unknown_mode_returns_failed():
    rec = run_stage29_2_birdeye_probe(
        mode="unknown",
        env=_env(),
    )
    assert rec.status == PROBE_STATUS_FAILED
    assert rec.refusal_reason == (
        BIRDEYE_REFUSAL_REASON_MODE_INVALID
    )


def test_non_string_mode_returns_failed():
    rec = run_stage29_2_birdeye_probe(
        mode=None,  # type: ignore[arg-type]
        env=_env(),
    )
    assert rec.status == PROBE_STATUS_FAILED
    assert rec.refusal_reason == (
        BIRDEYE_REFUSAL_REASON_MODE_INVALID
    )
    assert rec.mode == ""


def test_non_callable_transport_factory_returns_failed():
    rec = run_stage29_2_birdeye_probe(
        mode=PROBE_MODE_HTTP_CONNECT_ONLY,
        env=_env(),
        transport_factory="not-callable",  # type: ignore[arg-type]
    )
    assert rec.status == PROBE_STATUS_FAILED
    assert rec.refusal_reason == (
        BIRDEYE_REFUSAL_REASON_TRANSPORT_FACTORY_NOT_CALLABLE
    )


def test_transport_factory_raising_returns_failed():
    def explode():
        raise RuntimeError("boom")

    rec = run_stage29_2_birdeye_probe(
        mode=PROBE_MODE_HTTP_CONNECT_ONLY,
        env=_env(),
        transport_factory=explode,
    )
    assert rec.status == PROBE_STATUS_FAILED
    assert rec.refusal_reason == (
        BIRDEYE_REFUSAL_REASON_TRANSPORT_FACTORY_NOT_CALLABLE
    )


def test_repr_carries_only_safe_fields():
    rec = run_stage29_2_birdeye_probe(
        mode=PROBE_MODE_READINESS_ONLY,
        env=_env(),
    )
    r = repr(rec)
    assert GOOD_API_KEY not in r
    assert GOOD_BASE_URL not in r

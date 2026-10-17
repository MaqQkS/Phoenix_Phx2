"""Run-wide Helius byte-ceiling tests across WSS and HTTP."""

from __future__ import annotations

import pytest

from PHX2.free_tier_producer.helius_byte_budget import (
    HeliusByteBudget,
    SOURCE_HTTP,
    SOURCE_WSS,
)
from PHX2.free_tier_producer import helius_gap_recovery as recovery
from PHX2.tests.test_helius_gap_recovery import _source_config


def test_budget_is_shared_across_sources_and_never_exceeds_ceiling() -> None:
    budget = HeliusByteBudget(10)
    assert budget.consume(6, source=SOURCE_WSS) is True
    assert budget.consume(4, source=SOURCE_HTTP) is True
    assert budget.reached is True
    assert budget.consume(1, source=SOURCE_WSS) is False
    assert budget.snapshot() == {
        "ceiling": 10,
        "used_bytes": 10,
        "wss_bytes": 6,
        "http_bytes": 4,
        "wss_estimated_credits": 0.0,
        "http_estimated_credits": 0.0,
        "estimated_credits": 0.0,
        "remaining_bytes": 0,
        "reached": True,
        "overflow_attempted": True,
    }


def test_http_response_refuses_when_shared_budget_would_overflow(
    monkeypatch,
) -> None:
    raw = b'{"jsonrpc":"2.0","id":1,"result":{}}'
    budget = HeliusByteBudget(len(raw))
    assert budget.consume(1, source=SOURCE_WSS) is True

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self, _limit):
            return raw

    monkeypatch.setattr(
        recovery.urllib_request,
        "urlopen",
        lambda *_args, **_kwargs: Response(),
    )
    client = recovery.HeliusEnhancedHttpClient(
        _source_config(),
        byte_budget=budget,
    )
    with pytest.raises(recovery.HeliusRecoveryProviderError) as caught:
        client.call(
            {"jsonrpc": "2.0", "id": 1, "method": "test"},
            timeout_seconds=1,
            max_response_bytes=1024,
        )
    assert caught.value.reason == recovery.REASON_BYTE_CEILING
    assert budget.snapshot()["used_bytes"] == 1
    assert budget.snapshot()["overflow_attempted"] is True


def test_credit_usage_is_run_wide_and_source_separated() -> None:
    budget = HeliusByteBudget(10)
    budget.record_estimated_credits(1.25, source=SOURCE_WSS)
    budget.record_estimated_credits(10, source=SOURCE_HTTP)
    assert budget.snapshot()["wss_estimated_credits"] == 1.25
    assert budget.snapshot()["http_estimated_credits"] == 10.0
    assert budget.snapshot()["estimated_credits"] == 11.25

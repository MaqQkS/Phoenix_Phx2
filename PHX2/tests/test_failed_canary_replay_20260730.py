"""Deterministic replay of the 2026-07-30 failed real-ping canary.

Sanitized fixture of the exact eight candidates that were admitted to the
watchlist in run ``paid_primary_live_24x7_20260730T191127Z`` — seven bounded
``DEXSCREENER_RESTART_BACKFILL`` admissions plus one ``LIVE_HELIUS`` admission —
together with the market-transport failure condition that stalled all of them.

Observed in the failed run (per-candidate, from ``watch_state.jsonl``):
    market_state=MARKET_INCOMPLETE, market_reason_code=INDEPENDENT_FIELD_STALE,
    activated=None, ATH/MC/tier all None,
    backfill rows PENDING_1_20X, the live row PENDING_BASELINE.

Root cause: every market call returned HTTP 401, which the client reported as
``PROVIDER_MALFORMED`` after 32 wasted retries.

These tests pin the post-remediation behaviour: the failure is now named
correctly, is not retried, does not erase valid evidence, and a healthy
provider hydrates every one of the eight candidates.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

import pytest

from PHX2.free_tier_producer.compat import production_live_artifacts as pla
from PHX2.free_tier_producer.paid_birdeye import PaidBirdeyeMarketTransport
from PHX2.models.discovery_provenance import (
    DISCOVERY_PROVENANCE_DEX_BACKFILL,
    DISCOVERY_PROVENANCE_LIVE_HELIUS,
)
from PHX2.models.market_credential import MARKET_CREDENTIAL_INVALID
from PHX2.models.market_data_source import (
    MARKET_DATA_SOURCE_DEX_BACKFILL_PAIR,
    MARKET_DATA_SOURCE_PAID_MARKET_AND_LIVE_MIGRATION,
)
from PHX2.stage29.birdeye_constants import (
    BIRDEYE_PATH_PRICE, BIRDEYE_PATH_TOKEN_OVERVIEW,
)
from PHX2.stage29.stage29_2_birdeye_models import (
    BIRDEYE_REFUSAL_REASON_HTTP_STATUS_REJECTED,
    BIRDEYE_REFUSAL_REASON_NONE,
)

#: The exact eight mints admitted in the failed canary (public mint addresses).
BACKFILL_MINTS = (
    "GZEs9V467mznpgddszzDU13P6NTFwws9Em1u6TV9pump",
    "6M48b3EVgT4Uh1KpJTHRLzZRvxpo2ZgLPqUhpvBcpump",
    "Agmu8Xgn7rU4zFv4DMPrEBhYDdPsmiEG5hCiYyvSpump",
    "77YUCjgD1Ky8qu9ykfa7B25tr1UMnkeo92bw3cDUpump",
    "AvSANB37Z75jfnX1Ae3xyR93nzFDjdBmBoYV6YEmpump",
    "4HSJSnq81ubQL1mxNTFyfuqK6pukT4MoPGRCCYQWpump",
    "9pZ5vHYGSUFb15Ed39xWhvuQ9xFJw524BUegkR8upump",
)
LIVE_MINT = "Fzf9vJs3385BnKvp9PgHX2iWZf9CzSoWLTnZBYf2pump"

PINNED_CLOCK = 1785436800.0


def _candidate(mint: str, *, live: bool) -> Dict[str, Any]:
    return {
        "token_mint": mint,
        "discovery_provenance": (
            DISCOVERY_PROVENANCE_LIVE_HELIUS if live
            else DISCOVERY_PROVENANCE_DEX_BACKFILL),
        "current_data_source": (
            MARKET_DATA_SOURCE_PAID_MARKET_AND_LIVE_MIGRATION if live
            else MARKET_DATA_SOURCE_DEX_BACKFILL_PAIR),
        "status": "PENDING_BASELINE" if live else "PENDING_1_20X",
        "backfill_lookback_seconds": None if live else 21600,
    }


def replay_candidates() -> List[Dict[str, Any]]:
    rows = [_candidate(m, live=False) for m in BACKFILL_MINTS]
    rows.append(_candidate(LIVE_MINT, live=True))
    return rows


class _Result:
    def __init__(self, status: int, body: Optional[dict], refusal: str) -> None:
        self.http_status_code = status
        self.body = body
        self.refusal_reason = refusal
        self.fetched_at_utc = "2026-07-30T19:12:00Z"


class _Inner:
    """Inner transport that reproduces the canary's failure condition."""

    def __init__(self, mode: str) -> None:
        self.mode = mode
        self.calls: List[str] = []

    def get(self, *, endpoint_secret, path, query_params, timeout_seconds):
        self.calls.append(path)
        if self.mode == "auth_failure":
            return _Result(401, None, BIRDEYE_REFUSAL_REASON_HTTP_STATUS_REJECTED)
        if path == BIRDEYE_PATH_PRICE:
            return _Result(200, {"success": True,
                                 "data": {"value": 0.000021,
                                          "updateUnixTime": int(PINNED_CLOCK)}},
                           BIRDEYE_REFUSAL_REASON_NONE)
        if path == BIRDEYE_PATH_TOKEN_OVERVIEW:
            return _Result(200, {"success": True,
                                 "data": {"mc": 21000.0, "liquidity": 8400.0}},
                           BIRDEYE_REFUSAL_REASON_NONE)
        return _Result(200, {"success": True, "data": {"items": []}},
                       BIRDEYE_REFUSAL_REASON_NONE)


class _Secret:
    def reveal_api_key(self) -> str:
        return "k" * 32

    def reveal_base_url(self) -> str:
        return "https://market.invalid"


def _transport(mode: str, attempts: int = 4):
    inner = _Inner(mode)
    return inner, PaidBirdeyeMarketTransport(
        inner_transport=inner, endpoint_secret=_Secret(),
        min_interval_seconds=0, cache_ttl_seconds=0, max_attempts=attempts,
        now_fn=lambda: PINNED_CLOCK)


# ------------------------------------------------------------------ the fixture

def test_fixture_reproduces_the_admitted_eight() -> None:
    rows = replay_candidates()
    assert len(rows) == 8
    backfill = [r for r in rows
                if r["discovery_provenance"] == DISCOVERY_PROVENANCE_DEX_BACKFILL]
    live = [r for r in rows
            if r["discovery_provenance"] == DISCOVERY_PROVENANCE_LIVE_HELIUS]
    assert len(backfill) == 7
    assert len(live) == 1
    assert all(r["backfill_lookback_seconds"] == 21600 for r in backfill)


def test_every_replay_candidate_is_redaction_safe() -> None:
    """All eight rows must survive the real scanner (Blocker A)."""

    for row in replay_candidates():
        assert pla.scan_text(json.dumps(row)) == [], row


def test_replayed_watch_state_document_passes_the_real_scanner(tmp_path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "watch_state.jsonl").write_text(
        "\n".join(json.dumps(r) for r in replay_candidates()) + "\n",
        encoding="utf-8")
    report = pla.run_redaction_scan(run_dir)
    assert report["redaction_status"] == "REDACTED", report
    assert report["total_unsafe_hits"] == 0
    assert report["malformed_jsonl_line_total"] == 0
    assert report["positive_control_ok"] is True


# ------------------------------------------- the canary's exact failure condition

def test_auth_failure_is_named_and_not_retried_for_all_eight() -> None:
    """No 48/48 loop: one call per candidate, named a credential failure."""

    total_calls = 0
    for row in replay_candidates():
        inner, tr = _transport("auth_failure", attempts=4)
        out = tr.fetch_price_plane(row["token_mint"], timeout_seconds=5)
        # Named correctly — never PROVIDER_MALFORMED, which is what the failed
        # canary reported for what was really a rejected credential.
        assert out["_market_failure_reason"] == (
            "PROVIDER_" + MARKET_CREDENTIAL_INVALID)
        assert out["_market_failure_reason"] != "PROVIDER_MALFORMED"
        # Permanent status: exactly one attempt, zero retries.
        assert len(inner.calls) == 1
        assert tr.stats()["retries"] == 0
        assert tr.stats()["last_auth_status_class"] == MARKET_CREDENTIAL_INVALID
        total_calls += len(inner.calls)
    assert total_calls == 8


def test_no_candidate_is_silently_discarded_on_auth_failure() -> None:
    """Every candidate keeps an explicit, visible reason."""

    for row in replay_candidates():
        _inner, tr = _transport("auth_failure", attempts=1)
        out = tr.fetch_price_plane(row["token_mint"], timeout_seconds=5)
        assert out["mint"] == row["token_mint"]
        assert out["_market_failure_reason"]
        diag = tr.market_diagnostic(row["token_mint"])
        assert diag["market_reason_code"] == (
            "PROVIDER_" + MARKET_CREDENTIAL_INVALID)


# --------------------------------------------------- healthy provider hydration

def test_healthy_provider_hydrates_all_eight_candidates() -> None:
    """The invariant: every admitted candidate obtains price, MC and LP."""

    for row in replay_candidates():
        mint = row["token_mint"]
        _inner, tr = _transport("healthy", attempts=1)
        price = tr.fetch_price_plane(mint, timeout_seconds=5)
        overview = tr.fetch_overview_plane(mint, timeout_seconds=5)
        assert price.get("_market_failure_reason") is None, (mint, price)
        assert price["current_price"] is not None
        assert overview.get("_market_failure_reason") is None, (mint, overview)
        assert overview["current_market_cap_usd"] is not None
        assert overview["liquidity_usd"] is not None
        stats = tr.stats()
        assert stats["http_errors"] == 0
        assert stats["http_auth_failures"] == 0
        assert stats["last_auth_status_class"] is None


def test_healthy_provider_produces_no_auth_counters() -> None:
    _inner, tr = _transport("healthy", attempts=4)
    for row in replay_candidates():
        tr.fetch_price_plane(row["token_mint"], timeout_seconds=5)
    stats = tr.stats()
    assert stats["http_auth_failures"] == 0
    assert stats["auth_retries_skipped"] == 0
    assert stats["retries"] == 0

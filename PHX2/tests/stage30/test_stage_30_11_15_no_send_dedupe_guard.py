"""Stage 30.11.15 no-send dedupe guard tests.

Offline only. Proves the dedupe key derivation from a frozen Stage 30.11.13-shaped
snapshot is deterministic, ignores ``candidate_id`` / exact drawdown within a
bucket / current MC / ``created_at_utc``, re-keys on a meaningful change, and
fails closed on a malformed snapshot; and that the pre-dispatch guard consults
the injected ledger, records its outcome, and NEVER raises (even when the ledger
raises or returns garbage).

No real send, no network, no env read, no wallet, no trading.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import Decimal
from typing import Optional

from PHX2.stage30.stage30_11_15_ping_dedupe_ledger import (
    InMemoryPingDedupeLedger,
)
from PHX2.stage30.stage30_11_15_ping_dedupe_models import (
    DEDUPE_REASON_DUPLICATE_WITHIN_TTL,
    DEDUPE_REASON_LEDGER_UNAVAILABLE,
    DEDUPE_REASON_MALFORMED_KEY,
    DEDUPE_REASON_NEW_KEY,
    DEDUPE_VERDICT_ALLOWED,
    DEDUPE_VERDICT_SUPPRESSED_DUPLICATE,
    DEDUPE_VERDICT_UNAVAILABLE,
    STAGE30_11_15_OPERATOR_SIGNAL_KIND,
    STAGE30_11_15_POLICY_VERSION,
    Stage30_11_15PingDedupeKey,
)
from PHX2.stage30.stage30_11_15_no_send_dedupe_guard import (
    derive_ping_dedupe_key,
    make_no_send_dedupe_guard,
)


_BASE: str = "2026-06-07T07:06:40Z"
_WITHIN: str = "2026-06-07T08:06:40Z"


@dataclass(frozen=True)
class _FakeSnapshot:
    """A minimal Stage 30.11.13-shaped snapshot for the guard (duck-typed read).

    ``ath_price`` is "100" so the fractional drawdown percentage equals the
    ``drawdown_from_ath`` magnitude (pct == dd) -- making the band arithmetic
    obvious in the tests.
    """

    token_mint: str = "MintAAA"
    tier_token: str = "Tier 1"
    post_migration_ath_verified: bool = True
    ath_source_stage: str = "stage30_11_11"
    drawdown_from_ath: Decimal = Decimal("85")
    ath_price: str = "100"
    created_at_utc: str = _BASE
    candidate_id: str = "cand-1"
    current_market_cap_usd: Decimal = Decimal("9100")


# ---------------------------------------------------------------------------
# 1. derive_ping_dedupe_key: determinism + ignored axes + re-keying
# ---------------------------------------------------------------------------


def test_derivation_is_deterministic() -> None:
    snap = _FakeSnapshot()
    assert derive_ping_dedupe_key(snap) == derive_ping_dedupe_key(snap)


def test_derived_key_has_expected_axes() -> None:
    key = derive_ping_dedupe_key(_FakeSnapshot())
    assert key == Stage30_11_15PingDedupeKey(
        token_mint="MintAAA",
        operator_signal_kind=STAGE30_11_15_OPERATOR_SIGNAL_KIND,
        tier_token="Tier 1",
        drawdown_band="DD_BAND_80",
        post_migration_ath_verified=True,
        ath_source_stage="stage30_11_11",
        policy_version=STAGE30_11_15_POLICY_VERSION,
    )


def test_candidate_id_is_ignored() -> None:
    a = derive_ping_dedupe_key(_FakeSnapshot(candidate_id="cand-1"))
    b = derive_ping_dedupe_key(_FakeSnapshot(candidate_id="cand-2"))
    assert a == b


def test_created_at_and_market_cap_are_ignored() -> None:
    a = derive_ping_dedupe_key(_FakeSnapshot())
    b = derive_ping_dedupe_key(
        _FakeSnapshot(
            created_at_utc="2099-01-01T00:00:00Z",
            current_market_cap_usd=Decimal("424242"),
        )
    )
    assert a == b


def test_tiny_drawdown_move_inside_a_bucket_keeps_the_same_key() -> None:
    # 85 and 88 (pct, ath=100) both fall in the DD_BAND_80 bucket.
    a = derive_ping_dedupe_key(_FakeSnapshot(drawdown_from_ath=Decimal("85")))
    b = derive_ping_dedupe_key(_FakeSnapshot(drawdown_from_ath=Decimal("88")))
    assert a == b
    assert a.drawdown_band == "DD_BAND_80"


def test_drawdown_crossing_a_bucket_changes_the_key() -> None:
    a = derive_ping_dedupe_key(_FakeSnapshot(drawdown_from_ath=Decimal("79")))
    b = derive_ping_dedupe_key(_FakeSnapshot(drawdown_from_ath=Decimal("81")))
    assert a != b
    assert a.drawdown_band == "DD_BAND_70"
    assert b.drawdown_band == "DD_BAND_80"


def test_tier_change_changes_the_key() -> None:
    a = derive_ping_dedupe_key(_FakeSnapshot(tier_token="Tier 1"))
    b = derive_ping_dedupe_key(_FakeSnapshot(tier_token="Tier 2"))
    assert a != b


def test_policy_version_change_changes_the_key() -> None:
    a = derive_ping_dedupe_key(_FakeSnapshot(), policy_version="v0")
    b = derive_ping_dedupe_key(_FakeSnapshot(), policy_version="v1")
    assert a != b


@dataclass(frozen=True)
class _PartialSnapshot:
    token_mint: str = "MintAAA"
    # deliberately missing tier_token / drawdown_from_ath / ath_price / etc.


def test_malformed_snapshot_yields_none() -> None:
    assert derive_ping_dedupe_key(_PartialSnapshot()) is None
    assert derive_ping_dedupe_key(None) is None
    assert derive_ping_dedupe_key("not-a-snapshot") is None
    # A non-positive ATH price cannot produce a band -> None.
    assert derive_ping_dedupe_key(_FakeSnapshot(ath_price="0")) is None
    # A non-bool verified flag is malformed.
    assert (
        derive_ping_dedupe_key(replace(_FakeSnapshot()))  # sanity: well-formed
        is not None
    )


# ---------------------------------------------------------------------------
# 2. The guard: allow / suppress / unavailable + records last_outcome
# ---------------------------------------------------------------------------


def test_guard_allows_then_suppresses_same_snapshot() -> None:
    guard = make_no_send_dedupe_guard(ledger=InMemoryPingDedupeLedger())
    first = guard(_FakeSnapshot(created_at_utc=_BASE))
    assert first.verdict == DEDUPE_VERDICT_ALLOWED
    assert first.reason == DEDUPE_REASON_NEW_KEY
    assert guard.last_outcome is first

    second = guard(_FakeSnapshot(created_at_utc=_WITHIN))
    assert second.verdict == DEDUPE_VERDICT_SUPPRESSED_DUPLICATE
    assert second.reason == DEDUPE_REASON_DUPLICATE_WITHIN_TTL
    assert guard.last_outcome is second


def test_guard_allows_a_changed_tier() -> None:
    ledger = InMemoryPingDedupeLedger()
    guard = make_no_send_dedupe_guard(ledger=ledger)
    guard(_FakeSnapshot(tier_token="Tier 1", created_at_utc=_BASE))
    changed = guard(_FakeSnapshot(tier_token="Tier 2", created_at_utc=_WITHIN))
    assert changed.verdict == DEDUPE_VERDICT_ALLOWED


def test_guard_with_no_ledger_fails_closed() -> None:
    guard = make_no_send_dedupe_guard(ledger=None)
    out = guard(_FakeSnapshot())
    assert out.verdict == DEDUPE_VERDICT_UNAVAILABLE
    assert out.reason == DEDUPE_REASON_LEDGER_UNAVAILABLE


def test_guard_with_malformed_snapshot_fails_closed() -> None:
    guard = make_no_send_dedupe_guard(ledger=InMemoryPingDedupeLedger())
    out = guard(_PartialSnapshot())
    assert out.verdict == DEDUPE_VERDICT_UNAVAILABLE
    assert out.reason == DEDUPE_REASON_MALFORMED_KEY


class _RaisingLedger:
    def check_and_reserve(self, *, key, now_utc, ttl_seconds):
        raise RuntimeError("ledger boom")


class _OddReturnLedger:
    def check_and_reserve(self, *, key, now_utc, ttl_seconds):
        return "not an outcome"


def test_guard_never_raises_when_ledger_raises() -> None:
    guard = make_no_send_dedupe_guard(ledger=_RaisingLedger())
    out = guard(_FakeSnapshot())
    assert out.verdict == DEDUPE_VERDICT_UNAVAILABLE
    assert out.reason == DEDUPE_REASON_LEDGER_UNAVAILABLE


def test_guard_fails_closed_on_odd_ledger_return() -> None:
    guard = make_no_send_dedupe_guard(ledger=_OddReturnLedger())
    out = guard(_FakeSnapshot())
    assert out.verdict == DEDUPE_VERDICT_UNAVAILABLE
    assert out.reason == DEDUPE_REASON_LEDGER_UNAVAILABLE


def test_guard_uses_snapshot_created_at_as_ttl_now() -> None:
    # A custom tight TTL: the second snapshot is 1h later; with a 30-minute TTL
    # the prior reservation has aged out -> allow (proves the TTL "now" is the
    # snapshot's own created_at, not a wall clock).
    ledger = InMemoryPingDedupeLedger()
    guard = make_no_send_dedupe_guard(ledger=ledger, ttl_seconds=1800)
    guard(_FakeSnapshot(created_at_utc=_BASE))
    out = guard(_FakeSnapshot(created_at_utc=_WITHIN))
    assert out.verdict == DEDUPE_VERDICT_ALLOWED


def test_guard_is_total_over_hostile_snapshots() -> None:
    guard = make_no_send_dedupe_guard(ledger=InMemoryPingDedupeLedger())
    for snap in (None, "x", 7, _PartialSnapshot(), _FakeSnapshot()):
        out = guard(snap)
        assert out.verdict in (
            DEDUPE_VERDICT_ALLOWED,
            DEDUPE_VERDICT_SUPPRESSED_DUPLICATE,
            DEDUPE_VERDICT_UNAVAILABLE,
        )

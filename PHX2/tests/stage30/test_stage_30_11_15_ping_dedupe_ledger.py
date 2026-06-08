"""Stage 30.11.15 ping dedupe ledger tests.

Offline only. Proves the in-memory + JSONL ping dedupe ledgers suppress a
duplicate key within TTL, allow a new / aged-out / changed key, persist across a
simulated process restart through JSONL replay, and fail CLOSED (return
``DEDUPE_UNAVAILABLE``, never raise) on a corrupt line / unreadable path / write
failure / malformed key / bad now / invalid TTL.

No real send, no network, no env read, no wallet, no trading. The JSONL ledger
writes ONLY under the pytest ``tmp_path`` fixture.
"""

from __future__ import annotations

import shutil

import pytest

from PHX2.stage30.stage30_11_15_ping_dedupe_ledger import (
    InMemoryPingDedupeLedger,
    JsonlPingDedupeLedger,
)
from PHX2.stage30.stage30_11_15_ping_dedupe_models import (
    DEDUPE_REASON_DUPLICATE_WITHIN_TTL,
    DEDUPE_REASON_LEDGER_CORRUPT,
    DEDUPE_REASON_LEDGER_UNAVAILABLE,
    DEDUPE_REASON_LEDGER_WRITE_FAILED,
    DEDUPE_REASON_MALFORMED_KEY,
    DEDUPE_REASON_NEW_KEY,
    DEDUPE_REASON_TTL_EXPIRED,
    DEDUPE_VERDICT_ALLOWED,
    DEDUPE_VERDICT_SUPPRESSED_DUPLICATE,
    DEDUPE_VERDICT_UNAVAILABLE,
    STAGE30_11_15_DEFAULT_TTL_SECONDS,
    Stage30_11_15PingDedupeKey,
)


_TTL: int = STAGE30_11_15_DEFAULT_TTL_SECONDS  # 6h
_BASE: str = "2026-06-07T07:06:40Z"
_WITHIN: str = "2026-06-07T08:06:40Z"           # +1h  (< 6h)  -> suppress
_AFTER: str = "2026-06-07T14:06:41Z"            # +7h1s (> 6h) -> expired


def _key(**overrides) -> Stage30_11_15PingDedupeKey:
    base = dict(
        token_mint="MintAAA",
        operator_signal_kind="PHOENIX_OPERATOR_DIP_PING",
        tier_token="Tier 1",
        drawdown_band="DD_BAND_80",
        post_migration_ath_verified=True,
        ath_source_stage="stage30_11_11",
        policy_version="stage30_11_15_v0",
    )
    base.update(overrides)
    return Stage30_11_15PingDedupeKey(**base)


def _ledgers(tmp_path):
    """Yield labelled (ledger, is_jsonl) pairs for the shared-contract tests."""
    return (
        ("in_memory", InMemoryPingDedupeLedger(), False),
        (
            "jsonl",
            JsonlPingDedupeLedger(path=tmp_path / "sub" / "ledger.jsonl"),
            True,
        ),
    )


# ---------------------------------------------------------------------------
# 1. Shared contract: first allow, duplicate-within-TTL suppress, expiry allow
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("kind", ["in_memory", "jsonl"])
def test_first_key_allows_then_within_ttl_suppresses(kind, tmp_path) -> None:
    (tmp_path / "sub").mkdir()
    ledger = (
        InMemoryPingDedupeLedger()
        if kind == "in_memory"
        else JsonlPingDedupeLedger(path=tmp_path / "sub" / "ledger.jsonl")
    )
    key = _key()
    first = ledger.check_and_reserve(key=key, now_utc=_BASE, ttl_seconds=_TTL)
    assert first.verdict == DEDUPE_VERDICT_ALLOWED
    assert first.reason == DEDUPE_REASON_NEW_KEY
    assert first.allowed is True

    second = ledger.check_and_reserve(
        key=key, now_utc=_WITHIN, ttl_seconds=_TTL
    )
    assert second.verdict == DEDUPE_VERDICT_SUPPRESSED_DUPLICATE
    assert second.reason == DEDUPE_REASON_DUPLICATE_WITHIN_TTL
    assert second.suppressed is True


@pytest.mark.parametrize("kind", ["in_memory", "jsonl"])
def test_same_key_after_ttl_allows_again(kind, tmp_path) -> None:
    (tmp_path / "sub").mkdir()
    ledger = (
        InMemoryPingDedupeLedger()
        if kind == "in_memory"
        else JsonlPingDedupeLedger(path=tmp_path / "sub" / "ledger.jsonl")
    )
    key = _key()
    ledger.check_and_reserve(key=key, now_utc=_BASE, ttl_seconds=_TTL)
    expired = ledger.check_and_reserve(
        key=key, now_utc=_AFTER, ttl_seconds=_TTL
    )
    assert expired.verdict == DEDUPE_VERDICT_ALLOWED
    assert expired.reason == DEDUPE_REASON_TTL_EXPIRED


@pytest.mark.parametrize("kind", ["in_memory", "jsonl"])
@pytest.mark.parametrize(
    "override",
    [
        {"token_mint": "MintZZZ"},
        {"tier_token": "Tier 2"},
        {"drawdown_band": "DD_BAND_70"},
        {"post_migration_ath_verified": False},
        {"policy_version": "stage30_11_15_v1"},
        {"operator_signal_kind": "SOME_OTHER_KIND"},
        {"ath_source_stage": "stage30_11_99"},
    ],
)
def test_a_changed_key_axis_always_allows(kind, override, tmp_path) -> None:
    (tmp_path / "sub").mkdir()
    ledger = (
        InMemoryPingDedupeLedger()
        if kind == "in_memory"
        else JsonlPingDedupeLedger(path=tmp_path / "sub" / "ledger.jsonl")
    )
    ledger.check_and_reserve(key=_key(), now_utc=_BASE, ttl_seconds=_TTL)
    # A second check WITHIN the TTL but with ANY changed axis is a new key.
    changed = ledger.check_and_reserve(
        key=_key(**override), now_utc=_WITHIN, ttl_seconds=_TTL
    )
    assert changed.verdict == DEDUPE_VERDICT_ALLOWED
    assert changed.reason == DEDUPE_REASON_NEW_KEY


@pytest.mark.parametrize("kind", ["in_memory", "jsonl"])
def test_ttl_zero_never_suppresses(kind, tmp_path) -> None:
    (tmp_path / "sub").mkdir()
    ledger = (
        InMemoryPingDedupeLedger()
        if kind == "in_memory"
        else JsonlPingDedupeLedger(path=tmp_path / "sub" / "ledger.jsonl")
    )
    key = _key()
    a = ledger.check_and_reserve(key=key, now_utc=_BASE, ttl_seconds=0)
    b = ledger.check_and_reserve(key=key, now_utc=_BASE, ttl_seconds=0)
    assert a.allowed is True
    assert b.allowed is True
    assert b.reason == DEDUPE_REASON_TTL_EXPIRED


# ---------------------------------------------------------------------------
# 2. Shared contract: fail closed on malformed key / now / ttl
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("kind", ["in_memory", "jsonl"])
def test_malformed_key_fails_closed(kind, tmp_path) -> None:
    (tmp_path / "sub").mkdir()
    ledger = (
        InMemoryPingDedupeLedger()
        if kind == "in_memory"
        else JsonlPingDedupeLedger(path=tmp_path / "sub" / "ledger.jsonl")
    )
    for bad in (None, "not-a-key", 42, _key(token_mint="")):
        outcome = ledger.check_and_reserve(
            key=bad, now_utc=_BASE, ttl_seconds=_TTL
        )
        assert outcome.verdict == DEDUPE_VERDICT_UNAVAILABLE
        assert outcome.reason == DEDUPE_REASON_MALFORMED_KEY


@pytest.mark.parametrize("kind", ["in_memory", "jsonl"])
@pytest.mark.parametrize("bad_now", [None, "", "   ", "not-a-timestamp", 1234])
def test_bad_now_timestamp_fails_closed(kind, bad_now, tmp_path) -> None:
    (tmp_path / "sub").mkdir()
    ledger = (
        InMemoryPingDedupeLedger()
        if kind == "in_memory"
        else JsonlPingDedupeLedger(path=tmp_path / "sub" / "ledger.jsonl")
    )
    outcome = ledger.check_and_reserve(
        key=_key(), now_utc=bad_now, ttl_seconds=_TTL
    )
    assert outcome.verdict == DEDUPE_VERDICT_UNAVAILABLE
    assert outcome.reason == DEDUPE_REASON_LEDGER_UNAVAILABLE


@pytest.mark.parametrize("kind", ["in_memory", "jsonl"])
@pytest.mark.parametrize("bad_ttl", [None, -1, "600", 1.5, True])
def test_invalid_ttl_fails_closed(kind, bad_ttl, tmp_path) -> None:
    (tmp_path / "sub").mkdir()
    ledger = (
        InMemoryPingDedupeLedger()
        if kind == "in_memory"
        else JsonlPingDedupeLedger(path=tmp_path / "sub" / "ledger.jsonl")
    )
    outcome = ledger.check_and_reserve(
        key=_key(), now_utc=_BASE, ttl_seconds=bad_ttl
    )
    assert outcome.verdict == DEDUPE_VERDICT_UNAVAILABLE
    assert outcome.reason == DEDUPE_REASON_LEDGER_UNAVAILABLE


# ---------------------------------------------------------------------------
# 3. JSONL persistence: write once, then read it back
# ---------------------------------------------------------------------------


def test_jsonl_first_run_writes_one_line(tmp_path) -> None:
    path = tmp_path / "ledger.jsonl"
    ledger = JsonlPingDedupeLedger(path=path)
    assert not path.exists()
    out = ledger.check_and_reserve(key=_key(), now_utc=_BASE, ttl_seconds=_TTL)
    assert out.allowed is True
    assert path.is_file()
    lines = [
        line for line in path.read_text(encoding="utf-8").splitlines() if line
    ]
    assert len(lines) == 1
    # The record carries the schema version + reserved_at, never a secret.
    assert "stage30_11_15_v0_ping_dedupe_ledger" in lines[0]
    assert "reserved_at_utc" in lines[0]
    lowered = lines[0].lower()
    for forbidden in ("webhook", "bearer", "api_key", "://", "discord"):
        assert forbidden not in lowered


def test_jsonl_duplicate_within_ttl_appends_nothing(tmp_path) -> None:
    path = tmp_path / "ledger.jsonl"
    ledger = JsonlPingDedupeLedger(path=path)
    ledger.check_and_reserve(key=_key(), now_utc=_BASE, ttl_seconds=_TTL)
    ledger.check_and_reserve(key=_key(), now_utc=_WITHIN, ttl_seconds=_TTL)
    lines = [
        line for line in path.read_text(encoding="utf-8").splitlines() if line
    ]
    assert len(lines) == 1


# ---------------------------------------------------------------------------
# 4. Cross-run replay (the committed cross-run dedupe gap, closed)
# ---------------------------------------------------------------------------


def test_cross_run_replay_suppresses_after_simulated_restart(tmp_path) -> None:
    path = tmp_path / "ledger.jsonl"
    key = _key()

    # Run 1: a fresh process records the would-send.
    ledger_run1 = JsonlPingDedupeLedger(path=path)
    first = ledger_run1.check_and_reserve(
        key=key, now_utc=_BASE, ttl_seconds=_TTL
    )
    assert first.allowed is True

    # Run 2: a NEW ledger instance over the SAME file = simulated restart. It
    # replays the persisted reservation and suppresses the duplicate.
    ledger_run2 = JsonlPingDedupeLedger(path=path)
    second = ledger_run2.check_and_reserve(
        key=key, now_utc=_WITHIN, ttl_seconds=_TTL
    )
    assert second.verdict == DEDUPE_VERDICT_SUPPRESSED_DUPLICATE
    assert second.reason == DEDUPE_REASON_DUPLICATE_WITHIN_TTL


def test_cross_run_expired_ttl_after_restart_allows(tmp_path) -> None:
    path = tmp_path / "ledger.jsonl"
    key = _key()
    JsonlPingDedupeLedger(path=path).check_and_reserve(
        key=key, now_utc=_BASE, ttl_seconds=_TTL
    )
    # Restart; the persisted reservation has aged past the TTL -> allow + record.
    ledger_run2 = JsonlPingDedupeLedger(path=path)
    out = ledger_run2.check_and_reserve(
        key=key, now_utc=_AFTER, ttl_seconds=_TTL
    )
    assert out.verdict == DEDUPE_VERDICT_ALLOWED
    assert out.reason == DEDUPE_REASON_TTL_EXPIRED
    lines = [
        line for line in path.read_text(encoding="utf-8").splitlines() if line
    ]
    assert len(lines) == 2  # the original + the re-reservation


def test_cross_run_different_mint_allows_after_restart(tmp_path) -> None:
    path = tmp_path / "ledger.jsonl"
    JsonlPingDedupeLedger(path=path).check_and_reserve(
        key=_key(token_mint="MintAAA"), now_utc=_BASE, ttl_seconds=_TTL
    )
    ledger_run2 = JsonlPingDedupeLedger(path=path)
    out = ledger_run2.check_and_reserve(
        key=_key(token_mint="MintBBB"), now_utc=_WITHIN, ttl_seconds=_TTL
    )
    assert out.verdict == DEDUPE_VERDICT_ALLOWED
    assert out.reason == DEDUPE_REASON_NEW_KEY


# ---------------------------------------------------------------------------
# 5. JSONL fail-closed: corrupt / unreadable / unwritable
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "bad_line",
    [
        "not json at all",
        "{}",
        '{"schema_version":"wrong"}',
        '{"schema_version":"stage30_11_15_v0_ping_dedupe_ledger"}',
        "",
    ],
)
def test_corrupt_line_makes_ledger_unavailable(bad_line, tmp_path) -> None:
    path = tmp_path / "ledger.jsonl"
    path.write_text(bad_line + "\n", encoding="utf-8")
    ledger = JsonlPingDedupeLedger(path=path)
    out = ledger.check_and_reserve(key=_key(), now_utc=_BASE, ttl_seconds=_TTL)
    assert out.verdict == DEDUPE_VERDICT_UNAVAILABLE
    assert out.reason == DEDUPE_REASON_LEDGER_CORRUPT


def test_a_valid_line_then_corrupt_tail_is_unavailable(tmp_path) -> None:
    path = tmp_path / "ledger.jsonl"
    # One legitimate reservation, then a corrupt appended tail line.
    JsonlPingDedupeLedger(path=path).check_and_reserve(
        key=_key(), now_utc=_BASE, ttl_seconds=_TTL
    )
    with path.open("a", encoding="utf-8") as fh:
        fh.write("corrupt tail\n")
    ledger = JsonlPingDedupeLedger(path=path)
    out = ledger.check_and_reserve(key=_key(), now_utc=_WITHIN, ttl_seconds=_TTL)
    assert out.verdict == DEDUPE_VERDICT_UNAVAILABLE
    assert out.reason == DEDUPE_REASON_LEDGER_CORRUPT


def test_unparseable_reserved_at_is_corrupt(tmp_path) -> None:
    path = tmp_path / "ledger.jsonl"
    bad = (
        '{"schema_version":"stage30_11_15_v0_ping_dedupe_ledger",'
        '"token_mint":"M","operator_signal_kind":"K","tier_token":"Tier 1",'
        '"drawdown_band":"DD_BAND_80","post_migration_ath_verified":true,'
        '"ath_source_stage":"stage30_11_11","policy_version":"v0",'
        '"reserved_at_utc":"not-a-time"}'
    )
    path.write_text(bad + "\n", encoding="utf-8")
    ledger = JsonlPingDedupeLedger(path=path)
    out = ledger.check_and_reserve(key=_key(), now_utc=_BASE, ttl_seconds=_TTL)
    assert out.verdict == DEDUPE_VERDICT_UNAVAILABLE
    assert out.reason == DEDUPE_REASON_LEDGER_CORRUPT


def test_missing_parent_directory_is_unavailable(tmp_path) -> None:
    ledger = JsonlPingDedupeLedger(
        path=tmp_path / "does_not_exist" / "ledger.jsonl"
    )
    out = ledger.check_and_reserve(key=_key(), now_utc=_BASE, ttl_seconds=_TTL)
    assert out.verdict == DEDUPE_VERDICT_UNAVAILABLE
    assert out.reason == DEDUPE_REASON_LEDGER_UNAVAILABLE


def test_path_traversal_segment_is_unavailable(tmp_path) -> None:
    ledger = JsonlPingDedupeLedger(path=tmp_path / ".." / "ledger.jsonl")
    out = ledger.check_and_reserve(key=_key(), now_utc=_BASE, ttl_seconds=_TTL)
    assert out.verdict == DEDUPE_VERDICT_UNAVAILABLE
    assert out.reason == DEDUPE_REASON_LEDGER_UNAVAILABLE


def test_non_path_argument_is_unavailable() -> None:
    ledger = JsonlPingDedupeLedger(path="/tmp/a_string_not_a_path.jsonl")
    out = ledger.check_and_reserve(key=_key(), now_utc=_BASE, ttl_seconds=_TTL)
    assert out.verdict == DEDUPE_VERDICT_UNAVAILABLE
    assert out.reason == DEDUPE_REASON_LEDGER_UNAVAILABLE


def test_path_is_a_directory_is_unavailable(tmp_path) -> None:
    a_dir = tmp_path / "iam_a_dir"
    a_dir.mkdir()
    ledger = JsonlPingDedupeLedger(path=a_dir)
    out = ledger.check_and_reserve(key=_key(), now_utc=_BASE, ttl_seconds=_TTL)
    assert out.verdict == DEDUPE_VERDICT_UNAVAILABLE
    assert out.reason == DEDUPE_REASON_LEDGER_UNAVAILABLE


def test_write_failure_fails_closed(tmp_path) -> None:
    sub = tmp_path / "sub"
    sub.mkdir()
    path = sub / "ledger.jsonl"
    ledger = JsonlPingDedupeLedger(path=path)
    # Remove the parent directory AFTER construction so the append open() raises.
    shutil.rmtree(sub)
    out = ledger.check_and_reserve(key=_key(), now_utc=_BASE, ttl_seconds=_TTL)
    assert out.verdict == DEDUPE_VERDICT_UNAVAILABLE
    assert out.reason == DEDUPE_REASON_LEDGER_WRITE_FAILED


def test_check_and_reserve_never_raises(tmp_path) -> None:
    # Total over a pile of hostile inputs (the guard relies on this).
    ledger = JsonlPingDedupeLedger(path=tmp_path / "ledger.jsonl")
    for key in (None, "x", _key()):
        for now in (None, "", _BASE, 0):
            for ttl in (None, -5, _TTL):
                out = ledger.check_and_reserve(
                    key=key, now_utc=now, ttl_seconds=ttl
                )
                assert out.verdict in (
                    DEDUPE_VERDICT_ALLOWED,
                    DEDUPE_VERDICT_SUPPRESSED_DUPLICATE,
                    DEDUPE_VERDICT_UNAVAILABLE,
                )

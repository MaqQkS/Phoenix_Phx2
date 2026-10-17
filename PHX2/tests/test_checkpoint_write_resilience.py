"""PHX2 checkpoint-write resilience (transient Windows sharing-violation
remediation).

Deterministic fault-injection for the ATH / watch checkpoint persist paths.
These reproduce, on the pre-fix HEAD, the fatal `CheckpointWriteError` escape
that stopped three of three live-firehose runs (acceptance
20260723T025330Z §39), and lock in the shared bounded-retry tolerance that
mirrors the stream-cursor persist contract.

No live run, no provider/transport connection, no real ledger. Temporary
checkpoints only. Every injected sleep is a fake so the suite never blocks.

Phase-4 required-coverage map is noted per test in brackets, e.g. [P4:1].
"""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path

import pytest

from PHX2.free_tier_producer import checkpoint_envelope as cpe
from PHX2.free_tier_producer.ath_state import CentralAthStateStore
from PHX2.free_tier_producer.pumpswap_reserves import (
    BUY_LAYOUT_VIRTUAL,
    PumpSwapReserveArtifact,
    RESERVE_SOURCE_BUY_EVENT,
)
from PHX2.free_tier_producer.compat.build30_watchlist import (
    Watchlist,
    classify_watch_checkpoint_file,
)
from PHX2.free_tier_producer.compat import production_live_runner as plr


MINT = "EkNbQMQYpd4JET5FpZrqbdkYdHXeqocZcBByJpFWpump"
POOL = "ExVW9Wxpr4TnMchukxGwMYM4XYTr3yTKwpqDE35E9seW"
QUOTE = "So11111111111111111111111111111111111111112"

_TRANSIENT = "CHECKPOINT_WRITE_FAILED:PermissionError"
_STRUCTURAL = "CHECKPOINT_WRITE_CONFIRM_INVALID:QUARANTINE_JSON_INVALID"


# --------------------------------------------------------------------------- helpers

def _event(effective_quote: int, *, timestamp: int, raw_quote=None,
           virtual_quote: int = 0, supply_raw: int = 1_000_000_000_000_000):
    raw = effective_quote - virtual_quote if raw_quote is None else raw_quote
    return PumpSwapReserveArtifact(
        raw_quote_reserves=raw,
        virtual_quote_reserves=virtual_quote,
        effective_quote_reserves=effective_quote,
        base_reserves=1_000_000_000_000,
        reserve_source=RESERVE_SOURCE_BUY_EVENT,
        observation_timestamp=datetime.fromtimestamp(
            timestamp, timezone.utc).isoformat().replace("+00:00", "Z"),
        decoder_layout_version=BUY_LAYOUT_VIRTUAL,
        pool_address=POOL,
        base_mint=MINT,
        quote_mint=QUOTE,
        base_decimals=6,
        quote_decimals=9,
        event_side="BUY",
        event_timestamp=timestamp,
        base_supply=supply_raw,
    )


def _ath_store(path: Path) -> CentralAthStateStore:
    store = CentralAthStateStore(path)
    assert store.register_pool(
        mint=MINT, pool_address=POOL, quote_mint=QUOTE,
        creation_timestamp="1970-01-01T00:16:40Z")
    assert store.observe_quote_price(QUOTE, "1", observed_at=1000)
    assert store.observe_event(
        mint=MINT, artifact=_event(75_000_000_000, timestamp=1000),
        transaction_signature="tx-a", event_index=0)
    return store


def _fresh_watch(tmp_path: Path) -> Watchlist:
    return Watchlist.load(
        tmp_path / "watch_state.jsonl", max_size=64,
        terminal_history_path=tmp_path / "watch_terminal_history.jsonl")


def _read_watch_doc(state: Path):
    lines = state.read_text(encoding="utf-8").splitlines()
    header = json.loads(lines[0])
    records = [json.loads(line) for line in lines[1:] if line.strip()]
    return header, records


class _CountingFail:
    """A drop-in for cpe.write_checkpoint_generation that fails the first
    ``fail_times`` calls with ``message`` then succeeds (no filesystem)."""

    def __init__(self, fail_times: int, message: str = _TRANSIENT):
        self.fail_times = fail_times
        self.message = message
        self.calls = 0

    def __call__(self, **_kwargs):
        self.calls += 1
        if self.calls <= self.fail_times:
            raise cpe.CheckpointWriteError(self.message)
        return None


# --------------------------------------------------------------------------- resilient writer

def test_transient_then_success_retries(monkeypatch):
    """[P4:1] First write raises a retryable sharing violation; the second
    attempt succeeds."""
    fake = _CountingFail(fail_times=1)
    monkeypatch.setattr(cpe, "write_checkpoint_generation", fake)
    sleeps: list = []
    outcome = cpe.write_checkpoint_generation_resilient(
        primary_path="p", backup_path="b", header={}, records=[],
        classify=lambda p: None, sleep_fn=sleeps.append)
    assert fake.calls == 2
    assert outcome.attempts == 2 and outcome.retried == 1
    assert outcome.transient_failures == 1
    assert len(sleeps) == 1


def test_bounded_retries_then_final_success(monkeypatch):
    """[P4:2] The last allowed attempt succeeds."""
    fake = _CountingFail(fail_times=cpe.CHECKPOINT_WRITE_MAX_ATTEMPTS - 1)
    monkeypatch.setattr(cpe, "write_checkpoint_generation", fake)
    outcome = cpe.write_checkpoint_generation_resilient(
        primary_path="p", backup_path="b", header={}, records=[],
        classify=lambda p: None, sleep_fn=lambda d: None)
    assert fake.calls == cpe.CHECKPOINT_WRITE_MAX_ATTEMPTS
    assert outcome.retried == cpe.CHECKPOINT_WRITE_MAX_ATTEMPTS - 1


def test_retry_exhausted_raises(monkeypatch):
    """[P4:3] Retryable failures beyond the bound re-raise for the caller."""
    fake = _CountingFail(fail_times=99)
    monkeypatch.setattr(cpe, "write_checkpoint_generation", fake)
    with pytest.raises(cpe.CheckpointWriteError):
        cpe.write_checkpoint_generation_resilient(
            primary_path="p", backup_path="b", header={}, records=[],
            classify=lambda p: None, max_attempts=4, sleep_fn=lambda d: None)
    assert fake.calls == 4


def test_structural_readback_invalid_retried_then_fails_closed(monkeypatch):
    """[P4:5,7] A read-back/confirm validation failure is retried within the
    bound (it was observed live to be transient read contention on this
    filesystem), but a PERSISTENT one still fails closed on exhaustion —
    validation strength is preserved because every attempt re-validates."""
    # persistent structural failure -> retried to the bound, then raises
    fake = _CountingFail(fail_times=99, message=_STRUCTURAL)
    monkeypatch.setattr(cpe, "write_checkpoint_generation", fake)
    with pytest.raises(cpe.CheckpointWriteError):
        cpe.write_checkpoint_generation_resilient(
            primary_path="p", backup_path="b", header={}, records=[],
            classify=lambda p: None, max_attempts=5, sleep_fn=lambda d: None)
    assert fake.calls == 5                       # retried to the bound
    # a TRANSIENT read-contention structural failure that clears succeeds
    fake2 = _CountingFail(fail_times=3, message=_STRUCTURAL)
    monkeypatch.setattr(cpe, "write_checkpoint_generation", fake2)
    outcome = cpe.write_checkpoint_generation_resilient(
        primary_path="p", backup_path="b", header={}, records=[],
        classify=lambda p: None, sleep_fn=lambda d: None)
    assert outcome.attempts == 4 and outcome.retried == 3
    # classification remains available for observability
    assert (cpe.classify_checkpoint_write_error(cpe.CheckpointWriteError(_STRUCTURAL))
            == cpe.CHECKPOINT_FAILURE_STRUCTURAL)
    assert (cpe.classify_checkpoint_write_error(cpe.CheckpointWriteError(_TRANSIENT))
            == cpe.CHECKPOINT_FAILURE_TRANSIENT)


def test_retry_backoff_bounded_no_busyloop(monkeypatch):
    """[P4:19] Every backoff delay is capped and the count equals the retries;
    no unbounded/tight loop."""
    fake = _CountingFail(fail_times=99)
    monkeypatch.setattr(cpe, "write_checkpoint_generation", fake)
    sleeps: list = []
    with pytest.raises(cpe.CheckpointWriteError):
        cpe.write_checkpoint_generation_resilient(
            primary_path="p", backup_path="b", header={}, records=[],
            classify=lambda p: None, max_attempts=5, sleep_fn=sleeps.append)
    assert len(sleeps) == 4  # attempts-1
    assert all(0 < d <= cpe.CHECKPOINT_WRITE_RETRY_MAX_SECONDS for d in sleeps)


def test_resilient_write_survives_real_transient_replace(tmp_path, monkeypatch):
    """[P4:1,9,10] A real os.replace sharing violation on the first attempt is
    retried; the durable primary is written and the previous generation/backup
    are never lost."""
    wl = _fresh_watch(tmp_path)
    state = tmp_path / "watch_state.jsonl"
    wl.persist(state)                       # generation 1 (clean)
    header, records = _read_watch_doc(state)
    gen1_bytes = state.read_bytes()

    real_replace = os.replace
    fired = {"done": False}

    def flaky_replace(src, dst):
        if str(dst).endswith("watch_state.jsonl") and not fired["done"]:
            fired["done"] = True
            raise PermissionError(13, "sharing violation")
        return real_replace(src, dst)

    monkeypatch.setattr(cpe.os, "replace", flaky_replace)
    # Re-write the same authenticated generation resiliently: the first
    # os.replace raises a transient sharing violation, the retry succeeds.
    outcome = cpe.write_checkpoint_generation_resilient(
        primary_path=state, backup_path=Path(str(state) + ".bak"),
        header=header, records=records,
        classify=classify_watch_checkpoint_file, sleep_fn=lambda d: None)
    assert fired["done"] and outcome.retried >= 1
    assert classify_watch_checkpoint_file(state).state == cpe.FILE_VALID_CURRENT
    # the previous valid generation was preserved as backup before replace
    assert Path(str(state) + ".bak").read_bytes() == gen1_bytes


def test_wrapped_write_error_carries_only_type_name(tmp_path, monkeypatch):
    """[P4:23] The wrapped error exposes only the exception type name — never a
    path, endpoint, token, or response body."""
    wl = _fresh_watch(tmp_path)
    state = tmp_path / "watch_state.jsonl"
    wl.persist(state)
    header, records = _read_watch_doc(state)

    def boom_replace(src, dst):
        raise PermissionError(13, r"C:\secret\phx2_token.env")

    monkeypatch.setattr(cpe.os, "replace", boom_replace)
    with pytest.raises(cpe.CheckpointWriteError) as ei:
        cpe.write_checkpoint_generation(
            primary_path=state, backup_path=Path(str(state) + ".bak"),
            header=header, records=records,
            classify=classify_watch_checkpoint_file)
    msg = str(ei.value)
    assert msg == "CHECKPOINT_WRITE_FAILED:PermissionError"
    assert "secret" not in msg and "token" not in msg and ".env" not in msg


# --------------------------------------------------------------------------- watch persist

def test_watch_persist_tolerated_at_finish_tick(tmp_path):
    """[P4:14] The PROVEN fatal path: a watch persist that raises inside
    _finish_tick must be tolerated (counted, not propagated) so the tick loop
    never stops with UNEXPECTED_EXCEPTION."""

    class RaisingWatch:
        def persist(self, path):
            raise cpe.CheckpointWriteError(_TRANSIENT)

        def summary(self):
            return {"total": 0}

    tolerated = plr._finish_tick(
        RaisingWatch(), str(tmp_path / "w.jsonl"),
        on_cycle=None, ticks=1, sends=0, reseeds=0, stop_reason=None)
    assert tolerated == 1


def test_watch_persist_retries_and_advances_generation(tmp_path, monkeypatch):
    """[P4:8,15] A retried-but-successful watch persist commits exactly one new
    generation and records the retry."""
    wl = _fresh_watch(tmp_path)
    state = tmp_path / "watch_state.jsonl"
    wl.persist(state)
    gen1 = wl._checkpoint_generation

    real_replace = os.replace
    fired = {"done": False}

    def flaky_replace(src, dst):
        if str(dst).endswith("watch_state.jsonl") and not fired["done"]:
            fired["done"] = True
            raise PermissionError(13, "sharing violation")
        return real_replace(src, dst)

    monkeypatch.setattr(cpe.os, "replace", flaky_replace)
    wl.persist(state)                       # must retry internally and succeed
    m = wl.checkpoint_summary()
    assert wl._checkpoint_generation == gen1 + 1
    assert m["checkpoint_write_retried_total"] >= 1
    assert m["checkpoint_durability_status"] == cpe.CHECKPOINT_DURABILITY_HEALTHY


def test_watch_persist_failure_preserves_last_generation(tmp_path, monkeypatch):
    """[P4:9,10,15,21] An exhausted persist does NOT advance the durable
    generation and leaves the last valid primary loadable."""
    wl = _fresh_watch(tmp_path)
    state = tmp_path / "watch_state.jsonl"
    wl.persist(state)
    gen1 = wl._checkpoint_generation
    good_bytes = state.read_bytes()

    fake = _CountingFail(fail_times=99)
    monkeypatch.setattr(cpe, "write_checkpoint_generation", fake)
    monkeypatch.setattr(cpe.time, "sleep", lambda *_a, **_k: None)  # instant retries
    # persist() keeps the raise contract for the load/migration callers.
    with pytest.raises(cpe.CheckpointWriteError):
        wl.persist(state)
    monkeypatch.undo()
    assert wl._checkpoint_generation == gen1
    assert state.read_bytes() == good_bytes
    reloaded = _fresh_watch(tmp_path)
    assert reloaded._checkpoint_generation == gen1


def test_watch_persist_failure_observable(tmp_path, monkeypatch):
    """[P4:14] An unrecoverable write is surfaced in durability status/metrics —
    never a silently-healthy checkpoint."""
    wl = _fresh_watch(tmp_path)
    state = tmp_path / "watch_state.jsonl"
    wl.persist(state)
    fake = _CountingFail(fail_times=99)
    monkeypatch.setattr(cpe, "write_checkpoint_generation", fake)
    monkeypatch.setattr(cpe.time, "sleep", lambda *_a, **_k: None)  # instant retries
    with pytest.raises(cpe.CheckpointWriteError):
        wl.persist(state)
    m = wl.checkpoint_summary()
    assert m["checkpoint_durability_status"] == cpe.CHECKPOINT_DURABILITY_DEGRADED
    assert m["checkpoint_write_permanent_failed_total"] >= 1
    assert m["checkpoint_last_failure_category"] == cpe.CHECKPOINT_FAILURE_TRANSIENT


# --------------------------------------------------------------------------- ATH persist

def test_ath_observe_tolerates_persistent_write_failure(tmp_path, monkeypatch):
    """[P4:8,11,13,14] A steady-state ATH observation never terminates the
    producer on a persist failure; the durable generation is not falsely
    advanced and the in-memory ATH maximum is retained."""
    store = _ath_store(tmp_path)
    gen_before = store._checkpoint_generation

    fake = _CountingFail(fail_times=99)
    monkeypatch.setattr(cpe, "write_checkpoint_generation", fake)
    monkeypatch.setattr(cpe.time, "sleep", lambda *_a, **_k: None)  # instant retries
    # A brand-new higher observation triggers a persist that will fail; the
    # call must return (tolerated), not raise.
    store.observe_event(
        mint=MINT, artifact=_event(95_000_000_000, timestamp=1001),
        transaction_signature="tx-whale", event_index=1)
    snap = store.snapshot(MINT)
    assert snap["ath_effective_quote_reserves"] == "95000000000"  # retained in memory
    m = store.checkpoint_summary()
    assert m["checkpoint_durability_status"] == cpe.CHECKPOINT_DURABILITY_DEGRADED
    assert store._checkpoint_generation == gen_before  # no false advance


def test_ath_persist_recovers_after_transient(tmp_path, monkeypatch):
    """[P4:1,5] An ATH persist retries a transient failure and then commits."""
    store = _ath_store(tmp_path)
    real_replace = os.replace
    fired = {"n": 0}

    def flaky_replace(src, dst):
        if str(dst).endswith("ath_state_checkpoint.json") and fired["n"] == 0:
            fired["n"] += 1
            raise PermissionError(13, "sharing violation")
        return real_replace(src, dst)

    monkeypatch.setattr(cpe.os, "replace", flaky_replace)
    store.observe_event(
        mint=MINT, artifact=_event(95_000_000_000, timestamp=1001),
        transaction_signature="tx-whale", event_index=1)
    m = store.checkpoint_summary()
    assert fired["n"] == 1
    assert m["checkpoint_write_retried_total"] >= 1
    assert m["checkpoint_durability_status"] == cpe.CHECKPOINT_DURABILITY_HEALTHY


def test_ath_migration_write_failure_still_quarantines(tmp_path, monkeypatch):
    """[P4:22] The load/migration persist keeps its raise->quarantine contract:
    the tolerant steady-state wrapper does not weaken it."""
    # A malformed legacy public artifact that forces a migration write.
    legacy = tmp_path / "central_ath_state.json"
    legacy.write_text(json.dumps({
        "schema_version": "phx2_central_ath_v1",
        "mints": {MINT: {"ath_price": "0.0001", "ath_market_cap": "100"}},
    }), encoding="utf-8")

    fake = _CountingFail(fail_times=99)
    monkeypatch.setattr(cpe, "write_checkpoint_generation", fake)
    monkeypatch.setattr(cpe.time, "sleep", lambda *_a, **_k: None)  # instant retries
    store = CentralAthStateStore(tmp_path / "central_ath_state.json")
    # Migration install failed -> store must fail closed (quarantined), not
    # silently load an empty healthy state.
    assert store.checkpoint_quarantined or store.checkpoint.checkpoint_quarantined


# --------------------------------------------------------------------------- concurrency + restore

def test_concurrent_ath_persistence_serialized(tmp_path):
    """[P4:20] Concurrent persistence stays serialized under the store lock; the
    checkpoint remains valid and monotonically generationed."""
    store = _ath_store(tmp_path)
    errors: list = []

    def worker(base_ts: int):
        try:
            for i in range(20):
                store.observe_event(
                    mint=MINT,
                    artifact=_event(80_000_000_000 + base_ts + i,
                                    timestamp=2000 + base_ts + i),
                    transaction_signature=f"tx-{base_ts}-{i}", event_index=0)
        except Exception as exc:                       # pragma: no cover
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(b,))
               for b in (0, 1000)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors
    reloaded = CentralAthStateStore(tmp_path / "central_ath_state.json")
    assert not reloaded.checkpoint_quarantined


def test_watch_restart_restores_last_committed_generation(tmp_path):
    """[P4:21] A crash/restart restores the last completed durable generation."""
    wl = _fresh_watch(tmp_path)
    state = tmp_path / "watch_state.jsonl"
    wl.persist(state)
    wl.persist(state)
    gen = wl._checkpoint_generation
    reloaded = _fresh_watch(tmp_path)
    assert reloaded._checkpoint_generation == gen
    assert reloaded.checkpoint_summary()["checkpoint_status"] in (
        cpe.CHECKPOINT_PRIMARY_AND_BACKUP_OK, cpe.CHECKPOINT_PRIMARY_OK)

"""Offline cursor primary/backup rotation-race acceptance tests.

No test touches production state, a network, Telegram, or a real ledger.  The
captured fixture records only the redaction-safe facts retained by the failed
live observation; authenticated generations are constructed in memory.
"""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path

import pytest

from PHX2.free_tier_producer import checkpoint_envelope as cpe
from PHX2.free_tier_producer.stream_cursor import GrpcStreamCursorStore
from PHX2.watchdog.health import (
    HEALTHY,
    NONRESTARTABLE_INTEGRITY_FAILURE,
    REASON_CURSOR_DOCUMENT_INVALID,
    HealthInputs,
    evaluate_health,
)
from PHX2.watchdog.observe import read_cursor_checkpoint_snapshot


FIXTURE = Path(__file__).with_name("fixtures") / "cursor_rotation_20260727.json"
IDENTITY_DIGEST = "a" * 64


def _valid(generation: int, *, previous: str | None, slot: int | None = None):
    digest = f"{generation:064x}"[-64:]
    return cpe.FileClassification(
        path=Path("cursor"),
        state=cpe.FILE_VALID_CURRENT,
        header={
            "generation": generation,
            "envelope_digest": digest,
            "previous_generation_digest": previous,
        },
        records=[{
            "record_kind": "PHX2_STREAM_CURSOR_RECORD",
            "subscription_identity_digest": IDENTITY_DIGEST,
            "last_durable_slot": slot if slot is not None else generation,
        }],
        byte_digest=("b" * 63) + str(generation % 10),
        raw_bytes=f"generation={generation}".encode(),
    )


def _invalid(*, digest: str | None = None, reason=None):
    return cpe.FileClassification(
        path=Path("cursor"),
        state=cpe.FILE_INVALID,
        reason=reason or cpe.QUARANTINE_JSON_INVALID,
        byte_digest=digest,
        raw_bytes=(b"partial" if digest is not None else None),
    )


class _PairScript:
    """Return a primary/backup pair per logical observation attempt."""

    def __init__(self, pairs):
        self.pairs = list(pairs)
        self.attempt = 0

    def __call__(self, path):
        pair = self.pairs[min(self.attempt, len(self.pairs) - 1)]
        if str(path).endswith(".bak"):
            self.attempt += 1
            return pair[1]
        return pair[0]


def _read(script, *, max_attempts=3, sleeps=None):
    recorded = [] if sleeps is None else sleeps
    return read_cursor_checkpoint_snapshot(
        "live_epoch_stream_cursor.json",
        max_attempts=max_attempts,
        sleep_fn=recorded.append,
        classifier=script,
    )


def _live_health(cursor_state: str) -> HealthInputs:
    return HealthInputs(
        producer_expected=True,
        producer_pid=4242,
        producer_alive=True,
        producer_identity_ok=True,
        logical_producer_count=1,
        producer_uptime_seconds=3600.0,
        heartbeat_present=True,
        heartbeat_parse_ok=True,
        heartbeat_age_seconds=13.0,
        yellowstone_owner_count=1,
        max_active_streams_observed=1,
        cursor_document_state=cursor_state,
        cursor_checkpoint_attempted_total=4812,
        cursor_checkpoint_succeeded_total=4811,
        cursor_checkpoint_failed_total=1,
        recovery_state="IDLE",
        telegram_enabled=True,
        discord_enabled=False,
        send_capable_transport_count=1,
    )


def test_captured_live_failure_resolves_as_authenticated_rotation():
    evidence = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert evidence["circuit_reason"] == "CURSOR_DOCUMENT_INVALID"
    backup = _valid(63268, previous=f"{63267:064x}", slot=435_487_201)
    primary = _valid(
        63269, previous=backup.envelope_digest, slot=435_487_202)
    script = _PairScript([
        # Captured first observation: a Windows sharing/read failure has no
        # stable byte identity, while the preceding backup remains authentic.
        (_invalid(), backup),
        (primary, backup),
    ])

    snapshot = _read(script)

    assert snapshot.state == cpe.FILE_VALID_CURRENT
    assert snapshot.record["last_durable_slot"] == 435_487_202
    assert snapshot.facts["cursor_snapshot_status"] == (
        "CHECKPOINT_ROTATION_IN_PROGRESS_RESOLVED")
    assert snapshot.facts["cursor_snapshot_attempts"] == 2
    verdict = evaluate_health(_live_health(snapshot.state))
    assert verdict.health_class == HEALTHY
    assert REASON_CURSOR_DOCUMENT_INVALID not in verdict.reasons


@pytest.mark.parametrize(
    "primary,backup",
    [
        (_invalid(digest="1" * 64), _valid(8, previous="7" * 64)),
        (_invalid(), _valid(8, previous="7" * 64)),
        (_invalid(digest="1" * 64), _invalid(digest="2" * 64)),
    ],
)
def test_stable_partial_permission_or_dual_corruption_fails_closed(
    primary, backup,
):
    snapshot = _read(_PairScript([(primary, backup)]))
    assert snapshot.state == "INVALID"
    assert snapshot.facts["cursor_snapshot_status"] == "STABLE_INVALID"
    verdict = evaluate_health(_live_health(snapshot.state))
    assert verdict.health_class == NONRESTARTABLE_INTEGRITY_FAILURE
    assert REASON_CURSOR_DOCUMENT_INVALID in verdict.reasons


def test_cross_instant_generation_pair_is_reread_as_a_whole():
    old_backup = _valid(63267, previous=f"{63266:064x}")
    good_backup = _valid(63268, previous=old_backup.envelope_digest)
    new_primary = _valid(63269, previous=good_backup.envelope_digest)

    snapshot = _read(_PairScript([
        (new_primary, old_backup),  # N+1 / N-1: never accepted
        (new_primary, good_backup),
    ]))

    assert snapshot.state == cpe.FILE_VALID_CURRENT
    assert snapshot.facts["cursor_snapshot_attempts"] == 2
    assert snapshot.facts["cursor_snapshot_history"][0]["pair_status"] == (
        cpe.CHECKPOINT_QUARANTINED)
    assert snapshot.facts["cursor_snapshot_history"][1]["pair_status"] == (
        cpe.CHECKPOINT_PRIMARY_AND_BACKUP_OK)


def test_backup_read_collision_is_stabilized_without_using_temp():
    backup = _valid(10, previous=f"{9:064x}")
    primary = _valid(11, previous=backup.envelope_digest)
    snapshot = _read(_PairScript([
        (primary, _invalid()),
        (primary, backup),
    ]))
    assert snapshot.state == cpe.FILE_VALID_CURRENT
    assert snapshot.facts["cursor_snapshot_selected"] == "primary"
    assert snapshot.facts["cursor_snapshot_attempts"] == 2

    # A complete .next.tmp beside two absent committed files is pre-commit
    # evidence and is deliberately invisible to the reader.
    missing = cpe.FileClassification(path=Path("cursor"))
    absent = _read(_PairScript([(missing, missing)]))
    assert absent.state == cpe.FILE_MISSING


def test_producer_death_mid_rotation_does_not_grant_old_backup_validity():
    backup = _valid(20, previous=f"{19:064x}")
    snapshot = _read(_PairScript([(_invalid(), backup)]))
    assert snapshot.state == "INVALID"
    assert snapshot.facts["cursor_snapshot_attempts"] == 3


def test_retry_is_strictly_bounded_and_has_no_busy_loop():
    sleeps = []
    snapshot = _read(
        _PairScript([(_invalid(), _valid(30, previous=f"{29:064x}"))]),
        max_attempts=3,
        sleeps=sleeps,
    )
    assert snapshot.state == "INVALID"
    assert sleeps == [0.025, 0.05]
    assert snapshot.facts["cursor_snapshot_attempts"] == 3


@pytest.mark.skipif(os.name != "nt", reason="Windows replacement contract")
def test_windows_replace_never_exposes_a_deliberate_missing_primary(tmp_path):
    primary = tmp_path / "cursor.json"
    primary.write_bytes(b"generation-n")
    next_path = tmp_path / "cursor.json.next.tmp"
    next_path.write_bytes(b"generation-n-plus-1")

    os.replace(next_path, primary)

    assert primary.read_bytes() == b"generation-n-plus-1"
    assert not next_path.exists()


def test_concurrent_real_writer_reader_stress_keeps_authenticated_pair(tmp_path):
    primary = tmp_path / "live_epoch_stream_cursor.json"
    store = GrpcStreamCursorStore(
        primary_path=primary,
        subscription_identity_digest=IDENTITY_DIGEST,
    )
    store.load()
    store.commit_event(slot=1, identity="1|A|-|-|-|-|-|-|-", signature="A")
    errors = []

    def writer():
        try:
            for slot in range(2, 42):
                store.commit_event(
                    slot=slot,
                    identity=f"{slot}|A|-|-|-|-|-|-|-",
                    signature=f"S{slot}",
                )
                time.sleep(0.001)
        except Exception as exc:  # pragma: no cover - assertion reports it
            errors.append(exc)

    thread = threading.Thread(target=writer)
    thread.start()
    reads = 0
    while thread.is_alive():
        snapshot = read_cursor_checkpoint_snapshot(
            primary, retry_delays_seconds=(0.0, 0.0))
        assert snapshot.state == cpe.FILE_VALID_CURRENT
        reads += 1
        # The production watchdog polls in seconds.  This millisecond-scale
        # yield keeps the stress concurrent without manufacturing a permanent
        # exclusive reader that the real system can never create.
        time.sleep(0.002)
    thread.join()

    final = read_cursor_checkpoint_snapshot(primary)
    assert not errors
    assert reads >= 1
    assert final.state == cpe.FILE_VALID_CURRENT
    assert final.record["last_durable_slot"] == 41
    assert store.cursor_checkpoint_succeeded_total == 41
    assert store.cursor_checkpoint_failed_total == 0

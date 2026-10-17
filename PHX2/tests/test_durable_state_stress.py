"""Phase 5: durable-state stress -- repeated writes, restore, corruption.

The watch checkpoint is the surface that actually lost state in production
(61 of 63 writes failed on 2026-07-29), so it carries the heaviest load here:
hundreds of write/restore cycles, both halves of the primary/backup pair
corrupted independently and together, growth to production capacity, and
schema evolution.  The source-continuity document gets the same treatment
because it is the newest durable surface and the one an unresolved gap
depends on surviving a restart.

Nothing here touches preserved runtime evidence: every path is a tmp_path.
"""

from __future__ import annotations

from dataclasses import asdict

import pytest

from PHX2.free_tier_producer import checkpoint_envelope as CPE
from PHX2.free_tier_producer import source_continuity as SC
from PHX2.free_tier_producer.compat import build30_watchlist as W

MINT_A = "9jFMtdTtREkwnimNwagzr8fhM8R3e2cpVXK2m9eNpump"
MINT_B = "7fqbk1iad3JpHXnRacjQ4ddQoBoSUZmZ5GJwqHkKpump"

#: Production active-watch capacity, so growth is exercised at the real bound.
PRODUCTION_CAPACITY = 128
#: Well past the 63 the failed run attempted and the 63 already pinned.
SUSTAINED_GENERATIONS = 400


def _record(mint=MINT_A, candidate_id="cand_a", **kw):
    base = dict(
        token_mint=mint, candidate_id=candidate_id,
        migration_time_utc="2026-07-29T05:41:04Z", source_ref="ref",
        seeded_at_utc="2026-07-29T06:13:00Z")
    base.update(kw)
    payload = asdict(W.WatchEntry(**base))
    payload["record_digest"] = CPE.build_record_digest(
        CPE.CHECKPOINT_KIND_WATCH, payload)
    return payload


def _write(primary, backup, records, generation=1, previous=None):
    header = CPE.build_envelope_header(
        checkpoint_kind=CPE.CHECKPOINT_KIND_WATCH,
        schema_version=W.WATCH_CHECKPOINT_SCHEMA_VERSION,
        payload_encoding=CPE.PAYLOAD_ENCODING_JSONL,
        generation=generation,
        record_digests=[str(r["record_digest"]) for r in records],
        created_at_utc="2026-07-29T06:13:00Z",
        updated_at_utc=CPE.utc_now_iso(),
        previous_generation_digest=previous,
        source_id=primary.name, migration_history=())
    CPE.write_checkpoint_generation(
        primary_path=primary, backup_path=backup, header=header,
        records=records, classify=W.classify_watch_checkpoint_file)
    return header


def _mint(index: int) -> str:
    """A distinct, well-formed pump mint per index."""

    stem = MINT_A[:-8]
    return f"{stem}{index:04d}pump"


# ---------------------------------------------------------------------------
# 1. sustained write + restore
# ---------------------------------------------------------------------------


def test_four_hundred_generations_all_write_and_restore(tmp_path):
    """The failed run managed 2 of 63. Canonical state must not degrade."""

    primary = tmp_path / "watch.jsonl"
    backup = tmp_path / "watch.jsonl.bak"
    previous = None
    for generation in range(1, SUSTAINED_GENERATIONS + 1):
        rows, diagnostic = W.canonicalize_watch_checkpoint_records([
            _record(mint=MINT_A, candidate_id="a", recheck_count=generation),
            _record(mint=MINT_B, candidate_id="b", recheck_count=generation)])
        assert not diagnostic
        header = _write(primary, backup, rows, generation, previous)
        previous = header["envelope_digest"]

        # Restore on EVERY generation, not just at the end: a surface that
        # only reads back correctly at the end has still lost the states in
        # between, which is exactly what an operator restart would hit.
        state = W.classify_watch_checkpoint_file(primary)
        assert state.state == CPE.FILE_VALID_CURRENT
        restored = {r["token_mint"]: r for r in state.records}
        assert restored[MINT_A]["recheck_count"] == generation
        assert restored[MINT_B]["recheck_count"] == generation


def test_generation_chain_is_unbroken_across_sustained_writes(tmp_path):
    primary = tmp_path / "watch.jsonl"
    backup = tmp_path / "watch.jsonl.bak"
    previous = None
    for generation in range(1, 101):
        rows, _ = W.canonicalize_watch_checkpoint_records(
            [_record(recheck_count=generation)])
        header = _write(primary, backup, rows, generation, previous)
        assert header["previous_generation_digest"] == previous
        previous = header["envelope_digest"]
    assert W.classify_watch_checkpoint_file(primary).state == (
        CPE.FILE_VALID_CURRENT)


# ---------------------------------------------------------------------------
# 2. growth to the real capacity bound
# ---------------------------------------------------------------------------


def test_full_production_capacity_writes_and_restores(tmp_path):
    primary = tmp_path / "watch.jsonl"
    backup = tmp_path / "watch.jsonl.bak"
    rows, diagnostic = W.canonicalize_watch_checkpoint_records(
        [_record(mint=_mint(i), candidate_id=f"cand_{i}", recheck_count=i)
         for i in range(PRODUCTION_CAPACITY)])
    assert not diagnostic
    assert len(rows) == PRODUCTION_CAPACITY
    _write(primary, backup, rows)

    state = W.classify_watch_checkpoint_file(primary)
    assert state.state == CPE.FILE_VALID_CURRENT
    assert len(state.records) == PRODUCTION_CAPACITY
    restored = {r["token_mint"]: r for r in state.records}
    for i in range(PRODUCTION_CAPACITY):
        assert restored[_mint(i)]["recheck_count"] == i


def test_capacity_sized_state_survives_repeated_generations(tmp_path):
    primary = tmp_path / "watch.jsonl"
    backup = tmp_path / "watch.jsonl.bak"
    previous = None
    for generation in range(1, 26):
        rows, _ = W.canonicalize_watch_checkpoint_records(
            [_record(mint=_mint(i), candidate_id=f"cand_{i}",
                     recheck_count=generation)
             for i in range(PRODUCTION_CAPACITY)])
        header = _write(primary, backup, rows, generation, previous)
        previous = header["envelope_digest"]
    state = W.classify_watch_checkpoint_file(primary)
    assert state.state == CPE.FILE_VALID_CURRENT
    assert len(state.records) == PRODUCTION_CAPACITY


# ---------------------------------------------------------------------------
# 3. corruption of each half, and both
# ---------------------------------------------------------------------------


def _corrupt(path, mode="truncate"):
    data = path.read_bytes()
    if mode == "truncate":
        path.write_bytes(data[: max(1, len(data) // 2)])
    elif mode == "garbage":
        path.write_bytes(b"{not json at all\n" + data)
    elif mode == "empty":
        path.write_bytes(b"")


@pytest.mark.parametrize("mode", ["truncate", "garbage", "empty"])
def test_corrupt_primary_is_never_read_as_valid(tmp_path, mode):
    primary = tmp_path / "watch.jsonl"
    backup = tmp_path / "watch.jsonl.bak"
    rows, _ = W.canonicalize_watch_checkpoint_records([_record()])
    _write(primary, backup, rows)
    _corrupt(primary, mode)

    assert W.classify_watch_checkpoint_file(primary).state != (
        CPE.FILE_VALID_CURRENT)
    # The backup still carries a readable generation.
    assert W.classify_watch_checkpoint_file(backup).state in (
        CPE.FILE_VALID_CURRENT, CPE.FILE_MISSING)


def _write_two_generations(primary, backup, recheck=7):
    """Two generations, so a BACKUP half actually exists to corrupt.

    The backup is the PREVIOUS generation, so it only appears from the second
    write onwards -- a first-generation checkpoint has no redundant half.
    """

    rows, _ = W.canonicalize_watch_checkpoint_records([_record(recheck_count=1)])
    header = _write(primary, backup, rows, generation=1)
    rows, _ = W.canonicalize_watch_checkpoint_records(
        [_record(recheck_count=recheck)])
    _write(primary, backup, rows, generation=2,
           previous=header["envelope_digest"])
    assert backup.exists()


@pytest.mark.parametrize("mode", ["truncate", "garbage", "empty"])
def test_corrupt_backup_leaves_primary_authoritative(tmp_path, mode):
    primary = tmp_path / "watch.jsonl"
    backup = tmp_path / "watch.jsonl.bak"
    _write_two_generations(primary, backup, recheck=7)
    _corrupt(backup, mode)

    state = W.classify_watch_checkpoint_file(primary)
    assert state.state == CPE.FILE_VALID_CURRENT
    assert state.records[0]["recheck_count"] == 7


@pytest.mark.parametrize("mode", ["truncate", "garbage", "empty"])
def test_both_halves_corrupt_fails_closed(tmp_path, mode):
    """Never an empty healthy watchlist: unreadable state is unreadable."""

    primary = tmp_path / "watch.jsonl"
    backup = tmp_path / "watch.jsonl.bak"
    _write_two_generations(primary, backup)
    _corrupt(primary, mode)
    _corrupt(backup, mode)

    assert W.classify_watch_checkpoint_file(primary).state != (
        CPE.FILE_VALID_CURRENT)
    assert W.classify_watch_checkpoint_file(backup).state != (
        CPE.FILE_VALID_CURRENT)


def test_a_flipped_record_byte_is_caught_by_the_digest(tmp_path):
    primary = tmp_path / "watch.jsonl"
    backup = tmp_path / "watch.jsonl.bak"
    rows, _ = W.canonicalize_watch_checkpoint_records(
        [_record(recheck_count=3)])
    _write(primary, backup, rows)

    text = primary.read_text(encoding="utf-8")
    primary.write_text(
        text.replace('"recheck_count":3', '"recheck_count":9'),
        encoding="utf-8")
    assert W.classify_watch_checkpoint_file(primary).state != (
        CPE.FILE_VALID_CURRENT)


# ---------------------------------------------------------------------------
# 4. continuity document durability
# ---------------------------------------------------------------------------


def test_continuity_document_survives_hundreds_of_persists(tmp_path):
    path = tmp_path / "continuity.json"
    tracker = SC.SourceContinuityTracker(
        state_path=path, now_fn=lambda: "2026-07-29T06:45:37Z")
    tracker.note_slot(435896377, processed=True, durable=True)
    tracker.note_disconnect(reason_class=SC.REASON_PROVIDER_ERROR)
    tracker.note_slot(435898562, processed=True)

    for _ in range(300):
        tracker.persist()
    assert tracker.snapshot()["document_write_failures"] == 0

    restored = SC.SourceContinuityTracker(state_path=path)
    assert restored.load() is True
    assert restored.coverage_is_proven_continuous() is False
    assert restored.snapshot()["unresolved_slot_total"] == 2184


@pytest.mark.parametrize("mode", ["truncate", "garbage", "empty"])
def test_corrupt_continuity_primary_recovers_from_backup(tmp_path, mode):
    path = tmp_path / "continuity.json"
    tracker = SC.SourceContinuityTracker(
        state_path=path, now_fn=lambda: "2026-07-29T06:45:37Z")
    tracker.note_slot(435896377, processed=True, durable=True)
    tracker.note_disconnect(reason_class=SC.REASON_PROVIDER_ERROR)
    tracker.note_slot(435898562, processed=True)
    tracker.persist()          # writes primary, rotates prior to .bak
    tracker.persist()
    assert path.with_name(path.name + ".bak").exists()

    _corrupt(path, mode)
    restored = SC.SourceContinuityTracker(state_path=path)
    assert restored.load() is True
    # The gap survives the corruption of the primary half.
    assert restored.coverage_is_proven_continuous() is False


@pytest.mark.parametrize("mode", ["truncate", "garbage", "empty"])
def test_both_continuity_halves_corrupt_never_claim_continuity(tmp_path, mode):
    """Unreadable continuity evidence must not become 'no gap'."""

    path = tmp_path / "continuity.json"
    backup = path.with_name(path.name + ".bak")
    tracker = SC.SourceContinuityTracker(
        state_path=path, now_fn=lambda: "2026-07-29T06:45:37Z")
    tracker.note_slot(435896377, processed=True, durable=True)
    tracker.note_disconnect(reason_class=SC.REASON_PROVIDER_ERROR)
    tracker.note_slot(435898562, processed=True)
    tracker.persist()
    tracker.persist()

    _corrupt(path, mode)
    if backup.exists():
        _corrupt(backup, mode)

    restored = SC.SourceContinuityTracker(state_path=path)
    assert restored.load() is False
    # A tracker that restored nothing claims no prior ground, so the FIRST
    # slot after restart is a fresh anchor rather than a fabricated gap ...
    assert restored.continuity_state() == SC.NO_GAP
    # ... and it has no unresolved slots to misreport either.
    assert restored.snapshot()["unresolved_slot_total"] == 0


def test_a_tampered_continuity_digest_is_refused(tmp_path):
    path = tmp_path / "continuity.json"
    tracker = SC.SourceContinuityTracker(
        state_path=path, now_fn=lambda: "2026-07-29T06:45:37Z")
    tracker.note_slot(100, processed=True, durable=True)
    tracker.note_disconnect(reason_class=SC.REASON_PROVIDER_ERROR)
    tracker.note_slot(500, processed=True)
    tracker.persist()

    text = path.read_text(encoding="utf-8")
    path.write_text(text.replace('"gap_size_slots":399',
                                 '"gap_size_slots":1'), encoding="utf-8")
    restored = SC.SourceContinuityTracker(state_path=path)
    # Either the digest refuses the document outright, or a valid backup
    # answers instead; what must never happen is the tampered size surviving.
    if restored.load():
        assert restored.snapshot()["gap_size_slots"] != 1


# ---------------------------------------------------------------------------
# 5. schema evolution
# ---------------------------------------------------------------------------


def test_unknown_optional_continuity_fields_are_ignored_not_fatal(tmp_path):
    """A forward-compatible document must not brick an older reader."""

    record = {
        "gap_id": "gap_x", "detected_at_utc": "2026-07-29T06:45:37Z",
        "disconnect_reason_class": SC.REASON_PROVIDER_ERROR,
        "last_received_slot": 100, "last_processed_slot": 100,
        "last_durable_slot": 100, "expected_next_slot": 101,
        "first_post_reconnect_slot": 500, "gap_from_slot": 101,
        "gap_to_slot": 499, "gap_size_slots": 399,
        "unresolved_ranges": [[101, 499]],
        "a_field_from_a_future_version": {"nested": True},
    }
    gap = SC.SourceGap.from_record(record)
    assert gap.gap_size_slots == 399
    assert not hasattr(gap, "a_field_from_a_future_version")

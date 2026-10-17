"""A bootstrap recovery episode must not make the durable cursor unwritable.

2026-07-26 Stage-9 run: ``grpc_cursor_checkpoint_attempted_total = 94,959``,
``grpc_cursor_checkpoint_succeeded_total = 0``, failure category
``STRUCTURAL_CHECKPOINT_FAILURE``, and ``grpc_stream_cursor.json`` frozen at
00:57:06Z across two production runs.

Root cause, proven from the frozen document plus the running telemetry:

* the ON-DISK cursor was ``VALID_CURRENT`` with ``recovery_required=True``,
  ``recovery_from_slot=None``, ``recovery_generation=0`` -- the shape
  ``mark_recovery_failed`` leaves when it raises a recovery on a cursor that
  never opened an episode;
* the RUNNING cursor had ``recovery_from_slot=435085972`` with
  ``recovery_generation=0``, because ``_open_episode_locked`` takes its
  continuation branch and pins the boundary WITHOUT allocating a generation;
* cross-field rule 2 rejected exactly that pair, and since the boundary is
  re-proposed on every commit, every checkpoint failed forever.

Allocating a generation in the continuation branch is NOT the fix: the durable
recovery episode binds itself to ``recovery_generation`` (the live episode
records ``cursor_recovery_generation = 0``), so allocating would re-bind the
identity mid-recovery and quarantine the very episode being recovered.

The fix permits the bootstrap continuation and nothing else. These tests pin
both halves: the shape now persists, and every malformed generation-0 variant
is still refused.

Hermetic: TEMP state dirs only, no socket, no ``.env``, no real ledger, no send.
"""

from __future__ import annotations

import pytest

from PHX2.free_tier_producer import stream_cursor as sc


BOUNDARY = 435085972
DURABLE = 435233755


def _record(**overrides):
    """A v2 cursor record in the shape the failing run actually proposed."""

    record = {
        "record_kind": sc.CURSOR_RECORD_KIND,
        "last_durable_slot": DURABLE,
        "recovery_required": True,
        "recovery_from_slot": BOUNDARY,
        "recovery_target_slot": None,
        "recovery_generation": 0,
        "overlap_proven_generation": None,
        "recovery_terminal": True,
        "recovery_status": sc.RECOVERY_FAILED,
        "recovery_reason": sc.REASON_REPLAY_POSITION_TOO_OLD,
        "attempt_generation": 2,
        "attempt_open": True,
        "attempt_requested_from_slot": BOUNDARY,
        "attempt_pinned_boundary_slot": BOUNDARY,
        "last_proven_replay_boundary_slot": None,
    }
    record.update(overrides)
    return record


# --------------------------------------------------------------------------
# the exact rejection, and the exact repair
# --------------------------------------------------------------------------

def test_bootstrap_boundary_at_generation_zero_now_validates():
    """The precise document the production run could not write."""

    ok, reason = sc.validate_cursor_cross_field_state(_record())
    assert ok, f"bootstrap continuation still rejected: {reason}"


def test_an_allocated_episode_still_validates():
    ok, reason = sc.validate_cursor_cross_field_state(
        _record(recovery_generation=3))
    assert ok, reason


@pytest.mark.parametrize("overrides,why", [
    # A boundary at generation 0 that does not even claim a recovery is the
    # self-certifying shape rule 2 exists to stop.
    ({"recovery_required": False, "recovery_terminal": False,
      "recovery_reason": sc.REASON_NONE},
     "boundary at generation 0 without claiming recovery"),
    # A proof retires an episode, and an episode that proved something had to
    # have been allocated -- generation 0 cannot carry one.
    ({"overlap_proven_generation": 0,
      "last_proven_replay_boundary_slot": BOUNDARY},
     "overlap proof at generation 0"),
])
def test_malformed_generation_zero_variants_are_still_refused(overrides, why):
    ok, _reason = sc.validate_cursor_cross_field_state(_record(**overrides))
    assert not ok, f"validator accepted a malformed document: {why}"


def test_unrelated_cross_field_rules_are_unchanged():
    """The carve-out must not have widened any other rule."""

    # Terminal recovery must still say why.
    ok, _ = sc.validate_cursor_cross_field_state(
        _record(recovery_reason=sc.REASON_NONE))
    assert not ok
    # Terminal recovery must still remain a recovery.
    ok, _ = sc.validate_cursor_cross_field_state(
        _record(recovery_required=False))
    assert not ok
    # An open attempt must still be fully recorded.
    ok, _ = sc.validate_cursor_cross_field_state(
        _record(attempt_requested_from_slot=None))
    assert not ok
    ok, _ = sc.validate_cursor_cross_field_state(
        _record(attempt_pinned_boundary_slot=None))
    assert not ok
    # The pin may still never sit above what the attempt requested.
    ok, _ = sc.validate_cursor_cross_field_state(
        _record(attempt_pinned_boundary_slot=BOUNDARY + 10))
    assert not ok


# --------------------------------------------------------------------------
# the writer that produces the shape
# --------------------------------------------------------------------------

def _store(tmp_path):
    return sc.GrpcStreamCursorStore(
        primary_path=tmp_path / sc.CURSOR_PRIMARY_BASENAME,
        subscription_identity_digest="c" * 64)


def _seed_position(store):
    store.state.last_durable_slot = DURABLE
    store.state.last_durable_signature = "sig"
    store.state.last_durable_event_identity = f"{DURABLE}|sig|0|-|-|-|-|-|-"


def test_bootstrap_continuation_does_not_allocate_a_generation(tmp_path):
    """Allocating here would orphan the durable recovery episode."""

    store = _store(tmp_path)
    _seed_position(store)
    # mark_recovery_failed's shape: recovery claimed, no boundary, generation 0.
    store.state.recovery_required = True
    store.state.recovery_from_slot = None
    store.state.recovery_generation = 0

    store._open_episode_locked(boundary=BOUNDARY,
                               reason=sc.REASON_REPLAY_POSITION_TOO_OLD)

    assert store.state.recovery_from_slot == BOUNDARY
    assert store.state.recovery_generation == 0, (
        "continuation allocated a generation and would re-bind the episode")
    ok, reason = sc.validate_cursor_cross_field_state(store.state.to_record())
    assert ok, reason


def test_a_fresh_episode_still_allocates(tmp_path):
    store = _store(tmp_path)
    _seed_position(store)
    store.state.recovery_required = False
    store.state.recovery_generation = 0

    store._open_episode_locked(boundary=BOUNDARY,
                               reason=sc.REASON_REPLAY_POSITION_TOO_OLD)

    assert store.state.recovery_generation == 1
    assert store.state.recovery_from_slot == BOUNDARY


def test_the_boundary_never_moves_forward(tmp_path):
    store = _store(tmp_path)
    _seed_position(store)
    store.state.recovery_required = True
    store.state.recovery_from_slot = BOUNDARY
    store.state.recovery_generation = 0

    store._open_episode_locked(boundary=BOUNDARY + 5000,
                               reason=sc.REASON_REPLAY_POSITION_TOO_OLD)
    assert store.state.recovery_from_slot == BOUNDARY

    store._open_episode_locked(boundary=BOUNDARY - 5000,
                               reason=sc.REASON_REPLAY_POSITION_TOO_OLD)
    assert store.state.recovery_from_slot == BOUNDARY - 5000


# --------------------------------------------------------------------------
# durability: the counters, and the restart
# --------------------------------------------------------------------------

def test_checkpoint_counters_advance_truthfully(tmp_path):
    """Attempted and succeeded must both move; a failure may not be silent."""

    store = _store(tmp_path)
    _seed_position(store)
    store.state.recovery_required = True
    store.state.recovery_from_slot = None
    store.state.recovery_generation = 0
    store._open_episode_locked(boundary=BOUNDARY,
                               reason=sc.REASON_REPLAY_POSITION_TOO_OLD)

    before_attempted = store.cursor_checkpoint_attempted_total
    before_succeeded = store.cursor_checkpoint_succeeded_total
    store.persist()

    assert store.cursor_checkpoint_attempted_total > before_attempted
    assert store.cursor_checkpoint_succeeded_total > before_succeeded, (
        "the write did not succeed -- this is the production regression")
    assert store.cursor_checkpoint_failed_total == 0
    assert store.cursor_readback_failed_total == 0
    assert store.cursor_write_failed_total == 0
    assert store.cursor_durability_status != (
        sc._cpe.CHECKPOINT_DURABILITY_DEGRADED)


def test_restart_restores_the_committed_bootstrap_cursor(tmp_path):
    store = _store(tmp_path)
    _seed_position(store)
    store.state.recovery_required = True
    store.state.recovery_from_slot = None
    store.state.recovery_generation = 0
    store._open_episode_locked(boundary=BOUNDARY,
                               reason=sc.REASON_REPLAY_POSITION_TOO_OLD)
    store.persist()

    reopened = _store(tmp_path)
    reopened.load()

    assert not reopened.quarantined
    assert reopened.state.recovery_required is True
    assert reopened.state.recovery_from_slot == BOUNDARY
    assert reopened.state.recovery_generation == 0
    assert reopened.state.last_durable_slot == DURABLE
    # The episode binding a durable recovery episode references is intact.
    assert reopened.safe_resume_slot() == BOUNDARY


def test_the_boundary_still_wins_over_the_high_water_mark(tmp_path):
    """The whole point of the boundary: never resolve to last_durable_slot."""

    store = _store(tmp_path)
    _seed_position(store)
    store.state.recovery_required = True
    store.state.recovery_from_slot = None
    store.state.recovery_generation = 0
    store._open_episode_locked(boundary=BOUNDARY,
                               reason=sc.REASON_REPLAY_POSITION_TOO_OLD)
    store.persist()

    assert store.safe_resume_slot() == BOUNDARY
    assert store.safe_resume_slot() != DURABLE


def test_a_failed_write_never_advances_the_durable_cursor(tmp_path):
    """A refused checkpoint must leave the previous document authoritative."""

    store = _store(tmp_path)
    _seed_position(store)
    store.state.recovery_required = True
    store.state.recovery_from_slot = BOUNDARY
    store.state.recovery_generation = 0
    store.persist()

    # Now propose a genuinely contradictory document: a proof at generation 0.
    store.state.overlap_proven_generation = 0
    store.state.last_proven_replay_boundary_slot = BOUNDARY
    store.state.last_durable_slot = DURABLE + 10_000
    with pytest.raises(sc.StreamCursorWriteError):
        store.persist()

    reopened = _store(tmp_path)
    reopened.load()
    assert not reopened.quarantined
    assert reopened.state.last_durable_slot == DURABLE, (
        "a refused write advanced the durable position")
    assert reopened.state.overlap_proven_generation is None


def test_valid_backup_still_rescues_a_corrupt_primary(tmp_path):
    store = _store(tmp_path)
    _seed_position(store)
    store.state.recovery_required = True
    store.state.recovery_from_slot = None
    store.state.recovery_generation = 0
    store._open_episode_locked(boundary=BOUNDARY,
                               reason=sc.REASON_REPLAY_POSITION_TOO_OLD)
    store.persist()
    store.persist()  # ensure a backup generation exists

    primary = tmp_path / sc.CURSOR_PRIMARY_BASENAME
    primary.write_text("{ not json", encoding="utf-8")

    reopened = _store(tmp_path)
    reopened.load()
    assert not reopened.quarantined
    assert reopened.state.recovery_from_slot == BOUNDARY


def test_both_documents_invalid_quarantines(tmp_path):
    store = _store(tmp_path)
    _seed_position(store)
    store.state.recovery_required = True
    store.state.recovery_from_slot = BOUNDARY
    store.state.recovery_generation = 0
    store.persist()

    for name in (sc.CURSOR_PRIMARY_BASENAME, sc.CURSOR_PRIMARY_BASENAME + ".bak"):
        path = tmp_path / name
        if path.exists():
            path.write_text("{ not json", encoding="utf-8")

    reopened = _store(tmp_path)
    reopened.load()
    assert reopened.quarantined

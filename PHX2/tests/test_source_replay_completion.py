"""Same-session provider replay: request, refusal, partial and proven closure.

Phase 3 of the 2026-07-29 full offline audit.  Before this suite existed the
continuity tracker could DETECT the preserved 2,184-slot gap and expose a safe
recovery slot, but nothing ever asked the provider for it: live-epoch mode's
``_resume_decision`` had exactly one answer, ``BOOTSTRAP_LIVE_HEAD``, so every
reconnect re-armed at the provider's live head and a detected gap could only
ever stay unresolved.

The invariants proven here are deliberately narrow:

* a clean live-epoch start still bootstraps at the live head (unchanged policy);
* an open gap makes the NEXT subscription request its earliest unproven slot;
* only proven coverage closes a gap -- a provider that ignores ``from_slot``
  and serves the live head can never report RECOVERED;
* a retention refusal is terminal for that gap and never retried;
* attempts are bounded and settle on RECOVERY_FAILED;
* an unresolved gap keeps ``coverage_proven_continuous`` False across restart.
"""

from __future__ import annotations

from PHX2.free_tier_producer import source_continuity as SC

LAST_PROCESSED = 435896377
FIRST_POST_RECONNECT = 435898562
GAP_FROM = 435896378
GAP_TO = 435898561
GAP_SIZE = 2184


def _tracker(tmp_path=None, **kw):
    return SC.SourceContinuityTracker(
        state_path=(tmp_path / "continuity.json") if tmp_path else None,
        now_fn=lambda: "2026-07-29T06:45:37Z", **kw)


def _open_preserved_gap(tracker):
    """Reproduce the preserved failed-run discontinuity exactly."""

    tracker.note_slot(LAST_PROCESSED, processed=True, durable=True)
    tracker.note_disconnect(reason_class=SC.REASON_PROVIDER_ERROR)
    gap = tracker.note_slot(FIRST_POST_RECONNECT, processed=True)
    assert gap is not None
    assert (gap.gap_from_slot, gap.gap_to_slot, gap.gap_size_slots) == (
        GAP_FROM, GAP_TO, GAP_SIZE)
    return gap


# ---------------------------------------------------------------------------
# 1. request construction
# ---------------------------------------------------------------------------


def test_no_gap_requests_no_replay_so_live_head_policy_is_unchanged():
    """The live-only startup policy must be byte-for-byte what it was."""

    t = _tracker()
    assert t.replay_request() is None
    t.note_slot(LAST_PROCESSED, processed=True, durable=True)
    assert t.replay_request() is None


def test_open_gap_requests_its_earliest_unproven_slot(tmp_path):
    t = _tracker(tmp_path)
    gap = _open_preserved_gap(t)

    request = t.replay_request()
    assert request is not None
    gap_id, from_slot = request
    assert gap_id == gap.gap_id
    # The EARLIEST owed slot, never the high-water mark the stream has since
    # advanced to.
    assert from_slot == GAP_FROM


def test_partially_recovered_gap_requests_only_the_remainder(tmp_path):
    t = _tracker(tmp_path)
    _open_preserved_gap(t)
    # Half the range is proven by replayed, processed slots.
    t.apply_recovered_range(GAP_FROM, GAP_FROM + 999)

    request = t.replay_request()
    assert request is not None
    assert request[1] == GAP_FROM + 1000
    assert t.continuity_state() in SC.UNPROVEN_STATES


# ---------------------------------------------------------------------------
# 2. only proven coverage closes a gap
# ---------------------------------------------------------------------------


def test_head_only_reconnect_never_reports_recovered(tmp_path):
    """A provider that ignores from_slot serves the head; nothing is proven."""

    t = _tracker(tmp_path)
    _open_preserved_gap(t)
    t.mark_recovery_requested(t.replay_request()[0], GAP_FROM)
    assert t.continuity_state() == SC.RECOVERY_REQUESTED

    # The "replay" delivers only slots at/after the live head -- entirely
    # outside the owed range.
    for slot in range(FIRST_POST_RECONNECT, FIRST_POST_RECONNECT + 500):
        t.note_slot(slot, processed=True, durable=True)

    assert t.continuity_state() != SC.RECOVERED
    assert t.coverage_is_proven_continuous() is False
    assert t.snapshot()["unresolved_slot_total"] == GAP_SIZE


def test_complete_replayed_range_closes_the_gap(tmp_path):
    t = _tracker(tmp_path)
    _open_preserved_gap(t)
    t.mark_recovery_requested(t.replay_request()[0], GAP_FROM)

    t.apply_recovered_range(GAP_FROM, GAP_TO)

    assert t.continuity_state() == SC.NO_GAP
    assert t.coverage_is_proven_continuous() is True
    snap = t.snapshot()
    assert snap["unresolved_slot_total"] == 0
    assert snap["gap_closed_total"] == 1
    assert t.replay_request() is None


def test_replayed_slots_are_idempotent_and_order_independent(tmp_path):
    """Duplicate and out-of-order replay delivery must converge identically."""

    t = _tracker(tmp_path)
    _open_preserved_gap(t)
    # Deliver the owed range backwards, with every slot applied twice.
    for slot in range(GAP_TO, GAP_FROM - 1, -1):
        t.note_slot(slot, processed=True)
        t.note_slot(slot, processed=True)

    assert t.continuity_state() == SC.NO_GAP
    assert t.snapshot()["unresolved_slot_total"] == 0


def test_one_slot_short_is_still_unresolved(tmp_path):
    t = _tracker(tmp_path)
    _open_preserved_gap(t)
    t.apply_recovered_range(GAP_FROM, GAP_TO - 1)

    assert t.continuity_state() != SC.RECOVERED
    assert t.coverage_is_proven_continuous() is False
    assert t.snapshot()["unresolved_slot_total"] == 1


# ---------------------------------------------------------------------------
# 3. refusal, exhaustion and fail-visibly-closed
# ---------------------------------------------------------------------------


def test_retention_refusal_is_terminal_for_that_gap_and_never_retried(tmp_path):
    t = _tracker(tmp_path)
    gap = _open_preserved_gap(t)
    t.mark_recovery_requested(gap.gap_id, GAP_FROM)
    t.mark_recovery_failed(
        gap.gap_id, reason=SC.FAILURE_REPLAY_POSITION_TOO_OLD, unavailable=True)

    assert t.continuity_state() == SC.RECOVERY_UNAVAILABLE
    assert t.coverage_is_proven_continuous() is False
    # No attempt budget is spent chasing a position that can never be served.
    assert t.replay_request() is None


def test_bounded_attempts_settle_on_recovery_failed(tmp_path):
    t = _tracker(tmp_path, max_recovery_attempts=3)
    gap = _open_preserved_gap(t)

    for _ in range(3):
        request = t.replay_request()
        assert request is not None
        t.mark_recovery_requested(request[0], request[1])
        t.mark_recovery_failed(gap.gap_id, reason=SC.FAILURE_REPLAY_REFUSED)

    assert t.continuity_state() == SC.RECOVERY_FAILED
    assert t.replay_request() is None
    assert t.coverage_is_proven_continuous() is False


def test_refused_replay_with_partial_coverage_is_partially_recovered(tmp_path):
    t = _tracker(tmp_path, max_recovery_attempts=3)
    gap = _open_preserved_gap(t)
    t.mark_recovery_requested(gap.gap_id, GAP_FROM)
    t.apply_recovered_range(GAP_FROM, GAP_FROM + 99)
    t.mark_recovery_failed(gap.gap_id, reason=SC.FAILURE_REPLAY_INCOMPLETE)

    assert t.continuity_state() == SC.PARTIALLY_RECOVERED
    # Still retryable, and only for the remainder.
    assert t.replay_request()[1] == GAP_FROM + 100


def test_unavailable_recovery_is_never_displayed_as_healthy():
    assert SC.display_status_for(
        transport_connected=True,
        continuity_state=SC.RECOVERY_UNAVAILABLE,
    ) == "CONNECTED_COVERAGE_UNRESOLVED"
    assert SC.display_status_for(
        transport_connected=True,
        continuity_state=SC.RECOVERY_REQUESTED,
    ) == "CONNECTED_COVERAGE_RECOVERING"


# ---------------------------------------------------------------------------
# 4. restart boundary
# ---------------------------------------------------------------------------


def test_unresolved_gap_and_attempt_budget_survive_restart(tmp_path):
    path = tmp_path / "continuity.json"
    first = SC.SourceContinuityTracker(
        state_path=path, now_fn=lambda: "2026-07-29T06:45:37Z",
        max_recovery_attempts=3)
    gap = _open_preserved_gap(first)
    request = first.replay_request()
    first.mark_recovery_requested(request[0], request[1])
    first.mark_recovery_failed(gap.gap_id, reason=SC.FAILURE_REPLAY_REFUSED)
    first.persist()

    restored = SC.SourceContinuityTracker(
        state_path=path, max_recovery_attempts=3)
    assert restored.load() is True
    assert restored.coverage_is_proven_continuous() is False
    assert restored.snapshot()["unresolved_slot_total"] == GAP_SIZE
    # The budget already spent is durable: two attempts remain, not three.
    remaining = 0
    while restored.replay_request() is not None:
        req = restored.replay_request()
        restored.mark_recovery_requested(req[0], req[1])
        restored.mark_recovery_failed(
            gap.gap_id, reason=SC.FAILURE_REPLAY_REFUSED)
        remaining += 1
    assert remaining == 2
    assert restored.continuity_state() == SC.RECOVERY_FAILED


def test_recovery_unavailable_survives_restart_and_stays_closed(tmp_path):
    path = tmp_path / "continuity.json"
    first = SC.SourceContinuityTracker(
        state_path=path, now_fn=lambda: "2026-07-29T06:45:37Z")
    gap = _open_preserved_gap(first)
    first.mark_recovery_failed(
        gap.gap_id, reason=SC.FAILURE_REPLAY_POSITION_TOO_OLD, unavailable=True)

    restored = SC.SourceContinuityTracker(state_path=path)
    assert restored.load() is True
    assert restored.continuity_state() == SC.RECOVERY_UNAVAILABLE
    assert restored.replay_request() is None
    assert restored.coverage_is_proven_continuous() is False

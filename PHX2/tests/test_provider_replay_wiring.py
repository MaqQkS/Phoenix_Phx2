"""The live-epoch owner must actually ASK the provider for a detected gap.

These tests drive the real ``SingleGrpcPumpSwapDiscovery`` resume decision --
not a reimplementation -- because the defect being fixed was precisely that the
live-epoch branch had one hardcoded answer.  Detection without a request is
what left the preserved 2,184-slot gap permanently unresolved.
"""

from __future__ import annotations

from PHX2.free_tier_producer import source_continuity as SC
from PHX2.free_tier_producer import stream_cursor as CURSOR
from PHX2.free_tier_producer.paid_provider import (
    ProviderCandidateDedupe,
    SingleGrpcPumpSwapDiscovery,
)

LAST_PROCESSED = 435896377
FIRST_POST_RECONNECT = 435898562
GAP_FROM = 435896378
GAP_TO = 435898561


class _Epoch:
    integrity_failure = False

    def snapshot(self):
        return {"live_epoch_id": "epoch-test",
                "epoch_status": "EPOCH_HEALTHY",
                "epoch_durable": True,
                "epoch_start_slot": FIRST_POST_RECONNECT}

    def rollover(self, reason):
        return "epoch-test-2"

    def close(self, reason):
        return None


def _owner(continuity):
    return SingleGrpcPumpSwapDiscovery(
        source_factory=lambda **kw: None,
        dedupe=ProviderCandidateDedupe(),
        reconnect_backoff_seconds=0.001,
        stale_after_seconds=30,
        live_epoch_manager=_Epoch(),
        continuity=continuity,
    )


def _open_preserved_gap(tracker):
    tracker.note_slot(LAST_PROCESSED, processed=True, durable=True)
    tracker.note_disconnect(reason_class=SC.REASON_PROVIDER_ERROR)
    gap = tracker.note_slot(FIRST_POST_RECONNECT, processed=True)
    assert gap is not None
    return gap


def test_clean_live_epoch_start_still_bootstraps_at_live_head():
    """Unchanged startup policy: no gap means no replay request."""

    owner = _owner(SC.SourceContinuityTracker())
    decision = owner._resume_decision()
    assert decision.action == CURSOR.RESUME_ACTION_BOOTSTRAP_LIVE_HEAD
    assert decision.from_slot is None
    assert decision.builds_source is True


def test_open_gap_makes_the_next_subscription_request_the_owed_slot():
    tracker = SC.SourceContinuityTracker()
    _open_preserved_gap(tracker)

    decision = _owner(tracker)._resume_decision()
    assert decision.action == CURSOR.RESUME_ACTION_SUBSCRIBE_FROM_SLOT
    assert decision.from_slot == GAP_FROM
    assert decision.builds_source is True


def test_recovery_unavailable_gap_stops_requesting_and_returns_to_head():
    """Fail visibly closed: no replay spin against an unservable position."""

    tracker = SC.SourceContinuityTracker()
    gap = _open_preserved_gap(tracker)
    tracker.mark_recovery_failed(
        gap.gap_id, reason=SC.FAILURE_REPLAY_POSITION_TOO_OLD, unavailable=True)

    decision = _owner(tracker)._resume_decision()
    assert decision.action == CURSOR.RESUME_ACTION_BOOTSTRAP_LIVE_HEAD
    assert decision.from_slot is None
    # ... and the owner still refuses to claim healthy coverage.
    assert tracker.coverage_is_proven_continuous() is False


def test_epoch_integrity_failure_still_outranks_a_replay_request():
    """A dead epoch builds NOTHING, gap or no gap."""

    class _Broken(_Epoch):
        integrity_failure = True

    tracker = SC.SourceContinuityTracker()
    _open_preserved_gap(tracker)
    owner = SingleGrpcPumpSwapDiscovery(
        source_factory=lambda **kw: None,
        dedupe=ProviderCandidateDedupe(),
        reconnect_backoff_seconds=0.001,
        stale_after_seconds=30,
        live_epoch_manager=_Broken(),
        continuity=tracker,
    )
    decision = owner._resume_decision()
    assert decision.action == CURSOR.RESUME_ACTION_REFUSE_TERMINAL
    assert decision.builds_source is False


def test_snapshot_reports_the_gap_and_blocks_send_authorization():
    """An unresolved gap can never present as live-healthy or authorize a send."""

    tracker = SC.SourceContinuityTracker()
    _open_preserved_gap(tracker)
    owner = _owner(tracker)

    snap = owner.snapshot()
    assert snap["gap_unresolved"] is True
    assert snap["coverage_proven_continuous"] is False
    assert snap["source_continuity_state"] == SC.GAP_DETECTED
    assert snap["grpc_gap_from_slot"] == GAP_FROM
    assert snap["grpc_gap_to_slot"] == GAP_TO
    assert snap["grpc_gap_size_slots"] == 2184
    assert snap["live_healthy"] is False
    assert snap["grpc_display_status"] != CURSOR.DISPLAY_CONNECTED_LIVE_HEALTHY

    authorized, _reason = owner.authorizes_send()
    assert authorized is False


def test_proven_replay_restores_healthy_coverage_and_send_authorization():
    """Closing the gap by proven coverage is the ONLY way back to healthy."""

    tracker = SC.SourceContinuityTracker()
    _open_preserved_gap(tracker)
    owner = _owner(tracker)
    assert owner.snapshot()["gap_unresolved"] is True

    tracker.apply_recovered_range(GAP_FROM, GAP_TO)

    snap = owner.snapshot()
    assert snap["gap_unresolved"] is False
    assert snap["coverage_proven_continuous"] is True
    assert snap["source_continuity_state"] == SC.NO_GAP
    # Back at the live head for the next attempt: nothing is owed.
    assert owner._resume_decision().action == (
        CURSOR.RESUME_ACTION_BOOTSTRAP_LIVE_HEAD)

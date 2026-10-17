"""Canonical source-continuity invariants and the preserved 2,184-slot fixture.

The fixture reproduces the 2026-07-29 acceptance failure exactly: the single
owned stream was cut by an HTTP/2 reset at slot 435896377 and the replacement
subscription re-armed at the provider's live head, first delivering slot
435898620 while the new live epoch was armed at 435898562.  Production reported
every gap counter as zero.
"""

from __future__ import annotations

import pytest

from PHX2.free_tier_producer import source_continuity as SC

# -- preserved failed-run evidence (sanitized: slots only) ------------------
#
# The replacement subscription resumed AT the provider's live head, and the
# fresh live epoch was armed there: ``epoch_start_slot`` 435898562. That
# boundary is therefore the first slot the new stream covers, so it is the
# continuity anchor. 435898620 is simply a slot observed shortly afterwards
# (the first heartbeat sample following the reconnect) and is used here only to
# prove that continuing to ingest forward never retires the skipped range.
LAST_PROCESSED = 435896377
NEW_EPOCH_BOUNDARY = 435898562
FIRST_POST_RECONNECT = NEW_EPOCH_BOUNDARY
LATER_OBSERVED_SLOT = 435898620
EXPECTED_GAP_FROM = 435896378
EXPECTED_GAP_TO = 435898561
EXPECTED_GAP_SIZE = 2184

#: Operator-reported mint that fell inside the uncovered range. Used ONLY as an
#: observation-layer coverage fixture: PHX2 holds no metadata, market data or
#: eligibility evidence for it and this test asserts none.
MISSED_MINT_FIXTURE = "51uaudia2CdXGvbwZgwRCRxV7Aigv2oqtkBw88U7PS2N"


def _tracker(tmp_path=None, **kw):
    return SC.SourceContinuityTracker(
        state_path=(tmp_path / "continuity.json") if tmp_path else None,
        now_fn=lambda: "2026-07-29T06:45:37Z", **kw)


def _seed(tracker, slot=LAST_PROCESSED):
    tracker.note_slot(slot, processed=True, durable=True)


# ---------------------------------------------------------------------------
# Part 8: the preserved fixture
# ---------------------------------------------------------------------------


def test_preserved_2184_slot_gap_is_detected_exactly(tmp_path):
    t = _tracker(tmp_path)
    _seed(t)
    assert t.continuity_state() == SC.NO_GAP

    t.note_disconnect(reason_class=SC.REASON_PROVIDER_ERROR)
    gap = t.note_slot(FIRST_POST_RECONNECT, processed=True)

    assert gap is not None
    assert gap.gap_from_slot == EXPECTED_GAP_FROM
    assert gap.gap_to_slot == EXPECTED_GAP_TO
    assert gap.gap_size_slots == EXPECTED_GAP_SIZE
    assert gap.expected_next_slot == EXPECTED_GAP_FROM
    assert gap.first_post_reconnect_slot == FIRST_POST_RECONNECT
    assert gap.disconnect_reason_class == SC.REASON_PROVIDER_ERROR
    assert gap.recovery_status == SC.GAP_DETECTED
    assert t.continuity_state() == SC.GAP_DETECTED
    assert t.coverage_is_proven_continuous() is False


def test_old_production_path_reported_no_gap():
    """The pre-fix live-epoch path performed no slot comparison at all.

    Modelled faithfully: close the epoch, arm a fresh one at the first slot
    seen after reconnect, and report coverage from the epoch alone. It yields
    zero gap evidence for the identical slot sequence the fixture above proves.
    """

    class LegacyEpochOnlyCoverage:
        def __init__(self):
            self.epoch_start_slot = None
            self.gap_detected_total = 0

        def rollover(self):
            self.epoch_start_slot = None

        def observe_confirmed_slot(self, slot):
            if self.epoch_start_slot is None:
                self.epoch_start_slot = slot + 1

    legacy = LegacyEpochOnlyCoverage()
    legacy.observe_confirmed_slot(LAST_PROCESSED - 1)
    legacy.rollover()
    legacy.observe_confirmed_slot(EXPECTED_GAP_TO)

    assert legacy.gap_detected_total == 0
    assert legacy.epoch_start_slot == NEW_EPOCH_BOUNDARY

    t = _tracker()
    _seed(t)
    t.note_disconnect(reason_class=SC.REASON_PROVIDER_ERROR)
    t.note_slot(FIRST_POST_RECONNECT, processed=True)
    assert t.snapshot()["gap_detected_total"] == 1
    assert t.snapshot()["gap_size_slots"] == EXPECTED_GAP_SIZE


def test_missed_mint_is_only_an_observation_layer_coverage_fact(tmp_path):
    """A mint whose migration slot lies inside the gap is disclosed, not judged."""

    t = _tracker(tmp_path)
    _seed(t)
    t.note_disconnect(reason_class=SC.REASON_PROVIDER_ERROR)
    gap = t.note_slot(FIRST_POST_RECONNECT, processed=True)

    migration_slot_inside_gap = 435898329
    assert gap.gap_from_slot <= migration_slot_inside_gap <= gap.gap_to_slot
    # The tracker records coverage only. It asserts nothing about the mint's
    # metadata, market data, tier or alert eligibility -- none is knowable.
    record = gap.to_record()
    assert MISSED_MINT_FIXTURE not in str(record)
    assert t.coverage_is_proven_continuous() is False


# ---------------------------------------------------------------------------
# Part 1: continuity invariants
# ---------------------------------------------------------------------------


def test_exact_continuation_produces_no_gap():
    t = _tracker()
    _seed(t, 1000)
    t.note_disconnect(reason_class=SC.REASON_PROVIDER_DISCONNECT)
    assert t.note_slot(1001, processed=True) is None
    assert t.continuity_state() == SC.NO_GAP


def test_one_slot_gap_is_detected():
    t = _tracker()
    _seed(t, 1000)
    t.note_disconnect()
    gap = t.note_slot(1002, processed=True)
    assert gap.gap_from_slot == 1001
    assert gap.gap_to_slot == 1001
    assert gap.gap_size_slots == 1


def test_duplicate_first_slot_is_idempotent():
    t = _tracker()
    _seed(t, 1000)
    t.note_disconnect()
    assert t.note_slot(1000, processed=True) is None
    assert t.continuity_state() == SC.NO_GAP
    assert t.snapshot()["gap_detected_total"] == 0


def test_out_of_order_first_slot_does_not_invent_a_gap():
    t = _tracker()
    _seed(t, 1000)
    t.note_disconnect()
    assert t.note_slot(995, processed=True) is None
    assert t.continuity_state() == SC.NO_GAP


def test_out_of_order_slots_cannot_falsely_close_a_gap():
    t = _tracker()
    _seed(t, 1000)
    t.note_disconnect()
    t.note_slot(1010, processed=True)
    assert t.continuity_state() == SC.GAP_DETECTED
    # Late arrivals inside the range narrow it but do not close it.
    for slot in (1002, 1001, 1004):
        t.note_slot(slot, processed=True)
    assert t.continuity_state() != SC.NO_GAP
    gap = t.open_gaps()[0]
    assert gap.unresolved_slot_count == 9 - 3


def test_replayed_duplicate_slots_are_idempotent_for_coverage():
    t = _tracker()
    _seed(t, 1000)
    t.note_disconnect()
    t.note_slot(1005, processed=True)
    gap = t.open_gaps()[0]
    before = gap.unresolved_slot_count
    for _ in range(5):
        t.note_slot(1002, processed=True)
    assert t.open_gaps()[0].unresolved_slot_count == before - 1


def test_full_replay_closes_the_gap_exactly():
    t = _tracker()
    _seed(t, 1000)
    t.note_disconnect()
    t.note_slot(1010, processed=True)
    t.apply_recovered_range(1001, 1009)
    assert t.continuity_state() == SC.NO_GAP
    assert t.coverage_is_proven_continuous() is True
    assert t.snapshot()["gap_closed_total"] == 1


def test_partial_replay_remains_unresolved():
    t = _tracker()
    _seed(t, 1000)
    t.note_disconnect()
    gap = t.note_slot(1010, processed=True)
    t.mark_recovery_requested(gap.gap_id, 1001)
    t.apply_recovered_range(1001, 1005)
    assert t.continuity_state() != SC.NO_GAP
    t.mark_recovery_failed(gap.gap_id, reason=SC.FAILURE_REPLAY_INCOMPLETE)
    assert t.continuity_state() == SC.PARTIALLY_RECOVERED
    assert t.open_gaps()[0].unresolved_ranges == [[1006, 1009]]


def test_replay_unavailable_is_unresolved_not_recovered():
    t = _tracker()
    _seed(t, 1000)
    t.note_disconnect()
    gap = t.note_slot(1010, processed=True)
    t.mark_recovery_failed(gap.gap_id, reason=SC.FAILURE_REPLAY_UNSUPPORTED,
                           unavailable=True)
    assert t.continuity_state() == SC.RECOVERY_UNAVAILABLE
    assert t.coverage_is_proven_continuous() is False


def test_head_only_reconnect_does_not_close_the_gap():
    """Re-arming at head and continuing to ingest never proves the old range."""

    t = _tracker()
    _seed(t, LAST_PROCESSED)
    t.note_disconnect(reason_class=SC.REASON_PROVIDER_ERROR)
    t.note_slot(FIRST_POST_RECONNECT, processed=True)
    for slot in range(FIRST_POST_RECONNECT + 1, LATER_OBSERVED_SLOT + 500):
        t.note_slot(slot, processed=True)
    assert t.continuity_state() == SC.GAP_DETECTED
    assert t.open_gaps()[0].unresolved_slot_count == EXPECTED_GAP_SIZE


def test_gap_survives_epoch_rollover_and_rearm(tmp_path):
    t = _tracker(tmp_path)
    _seed(t)
    t.note_disconnect(reason_class=SC.REASON_PROVIDER_ERROR)
    t.note_slot(FIRST_POST_RECONNECT, processed=True)
    t.note_epoch_rollover(
        epoch_before="epoch_74d486117249", epoch_after="epoch_b981878300a6",
        boundary_before=435893890, boundary_after=NEW_EPOCH_BOUNDARY)

    gap = t.open_gaps()[0]
    assert gap.gap_size_slots == EXPECTED_GAP_SIZE
    assert gap.epoch_before == "epoch_74d486117249"
    assert gap.epoch_after == "epoch_b981878300a6"
    assert gap.epoch_boundary_after == NEW_EPOCH_BOUNDARY
    assert t.continuity_state() == SC.GAP_DETECTED


def test_candidate_closures_reference_the_gap_identity(tmp_path):
    t = _tracker(tmp_path)
    _seed(t)
    t.note_disconnect(reason_class=SC.REASON_PROVIDER_ERROR)
    gap = t.note_slot(FIRST_POST_RECONNECT, processed=True)
    t.note_candidates_closed_by_gap(3)
    assert t.open_gaps()[0].candidates_closed_by_gap == 3
    assert t.open_gaps()[0].gap_id == gap.gap_id


def test_implausible_slot_rate_is_disclosed():
    clock = {"t": 0.0}
    t = SC.SourceContinuityTracker(now_fn=lambda: "2026-07-29T06:45:37Z")
    t._monotonic = lambda: clock["t"]
    _seed(t, LAST_PROCESSED)
    t.note_disconnect(reason_class=SC.REASON_PROVIDER_ERROR)
    clock["t"] = 62.0  # 2,184 slots in 62s is physically impossible
    gap = t.note_slot(FIRST_POST_RECONNECT, processed=True)
    assert gap.implausible_jump is True
    assert gap.observed_jump_slots_per_second > SC.IMPLAUSIBLE_SLOTS_PER_SECOND
    assert t.snapshot()["implausible_jump"] is True


def test_plausible_slot_rate_is_not_flagged():
    clock = {"t": 0.0}
    t = SC.SourceContinuityTracker(now_fn=lambda: "2026-07-29T06:45:37Z")
    t._monotonic = lambda: clock["t"]
    _seed(t, 1000)
    t.note_disconnect()
    clock["t"] = 100.0
    gap = t.note_slot(1101, processed=True)
    assert gap.implausible_jump is False


def test_fresh_subscription_with_no_prior_position_claims_no_gap():
    t = _tracker()
    t.note_disconnect()
    assert t.note_slot(999999, processed=True) is None
    assert t.continuity_state() == SC.NO_GAP


def test_transport_connection_and_continuity_are_separate_states():
    assert SC.display_status_for(
        transport_connected=True,
        continuity_state=SC.NO_GAP) == "CONNECTED_LIVE_HEALTHY"
    assert SC.display_status_for(
        transport_connected=True,
        continuity_state=SC.GAP_DETECTED) == "CONNECTED_COVERAGE_RECOVERING"
    assert SC.display_status_for(
        transport_connected=True,
        continuity_state=SC.UNRESOLVED) == "CONNECTED_COVERAGE_UNRESOLVED"
    assert SC.display_status_for(
        transport_connected=False, continuity_state=SC.NO_GAP) == "DISCONNECTED"


def test_connected_socket_never_implies_healthy_coverage():
    for state in SC.UNPROVEN_STATES:
        assert SC.display_status_for(
            transport_connected=True,
            continuity_state=state) != "CONNECTED_LIVE_HEALTHY"


def test_bounded_recovery_attempts_end_in_recovery_failed():
    t = _tracker(max_recovery_attempts=2)
    _seed(t, 1000)
    t.note_disconnect()
    gap = t.note_slot(1010, processed=True)
    for _ in range(2):
        t.mark_recovery_requested(gap.gap_id, 1001)
        t.mark_recovery_failed(gap.gap_id, reason=SC.FAILURE_REPLAY_REFUSED)
    assert t.continuity_state() == SC.RECOVERY_FAILED


def test_safe_recovery_slot_is_earliest_unproven_position():
    t = _tracker()
    _seed(t, 1000)
    t.note_disconnect()
    t.note_slot(1010, processed=True)
    assert t.safe_recovery_slot() == 1001
    t.apply_recovered_range(1001, 1004)
    assert t.safe_recovery_slot() == 1005


# ---------------------------------------------------------------------------
# Part 3: durable document
# ---------------------------------------------------------------------------


def test_gap_document_is_durable_and_survives_reload(tmp_path):
    path = tmp_path / "continuity.json"
    t = SC.SourceContinuityTracker(state_path=path,
                                   now_fn=lambda: "2026-07-29T06:45:37Z")
    _seed(t)
    t.note_disconnect(reason_class=SC.REASON_PROVIDER_ERROR)
    t.note_slot(FIRST_POST_RECONNECT, processed=True)
    assert path.exists()

    restored = SC.SourceContinuityTracker(state_path=path)
    assert restored.load() is True
    assert restored.continuity_state() == SC.GAP_DETECTED
    gap = restored.open_gaps()[0]
    assert gap.gap_from_slot == EXPECTED_GAP_FROM
    assert gap.gap_to_slot == EXPECTED_GAP_TO
    assert gap.gap_size_slots == EXPECTED_GAP_SIZE


def test_tampered_gap_document_is_rejected(tmp_path):
    path = tmp_path / "continuity.json"
    t = SC.SourceContinuityTracker(state_path=path,
                                   now_fn=lambda: "2026-07-29T06:45:37Z")
    _seed(t)
    t.note_disconnect()
    t.note_slot(FIRST_POST_RECONNECT, processed=True)

    payload = path.read_text(encoding="utf-8").replace(
        str(EXPECTED_GAP_SIZE), "1")
    path.write_text(payload, encoding="utf-8")
    path.with_name(path.name + ".bak").unlink(missing_ok=True)

    restored = SC.SourceContinuityTracker(state_path=path)
    assert restored.load() is False


def test_document_never_carries_provider_exception_text(tmp_path):
    t = _tracker(tmp_path)
    _seed(t)
    t.note_disconnect(reason_class="The HTTP/2 peer reset the stream.")
    gap = t.note_slot(FIRST_POST_RECONNECT, processed=True)
    assert gap.disconnect_reason_class == SC.REASON_UNKNOWN
    assert "HTTP/2" not in str(gap.to_record())


def test_all_states_are_in_the_closed_set():
    t = _tracker()
    _seed(t, 1000)
    t.note_disconnect()
    gap = t.note_slot(1010, processed=True)
    for status in SC.CONTINUITY_STATES:
        gap.recovery_status = status
        assert t.continuity_state() in SC.CONTINUITY_STATES


# ---------------------------------------------------------------------------
# range algebra
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("ranges,expected", [
    ([], []),
    ([[1, 3], [4, 6]], [(1, 6)]),
    ([[1, 3], [5, 6]], [(1, 3), (5, 6)]),
    ([[5, 6], [1, 3], [2, 4]], [(1, 6)]),
    ([[1, 10], [3, 4]], [(1, 10)]),
])
def test_normalize_ranges(ranges, expected):
    assert SC.normalize_ranges(ranges) == expected


@pytest.mark.parametrize("span,covered,expected", [
    ((1, 10), [], [(1, 10)]),
    ((1, 10), [[1, 10]], []),
    ((1, 10), [[3, 5]], [(1, 2), (6, 10)]),
    ((1, 10), [[1, 5]], [(6, 10)]),
    ((1, 10), [[6, 10]], [(1, 5)]),
])
def test_subtract_ranges(span, covered, expected):
    assert SC.subtract_ranges(span, covered) == expected

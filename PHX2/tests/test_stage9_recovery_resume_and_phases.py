"""Stage 9: a bounded attempt clock must pause, not end, an intact episode.

The 2026-07-26 Stage-9 soak inherited a recovery episode that had been ended by
``RPC_BACKFILL_TIMEOUT`` after 1,800 s with 1,797 of 145,664 produced blocks
committed. Nothing about that episode was inconsistent -- the boundary, the
target, the block accounting and the overlap evidence were all intact -- yet the
episode was closed, so the only way forward was an operator hand edit or a
cursor reset. Both are forbidden.

These tests pin the four behaviours that fix it, and the boundaries that must
NOT move with them:

* a bounded attempt clock pauses retryably ONLY when every integrity invariant
  still holds (``RECOVERY_PAUSED_RETRYABLE``);
* an already-persisted terminal timeout is upgraded in place, authenticated,
  idempotently, retaining the original verdict as history;
* the resumed pass restarts at ``last_completed_slot + 1``, never at the live
  head, and never across an unresolved produced block;
* concurrent fetching may complete out of order, but application stays in
  canonical slot order;
* PRE_SOAK_RECOVERY seconds never count toward the acceptance clock and no
  delivery is permitted while they run.

Hermetic: every store is a TEMP directory, every RPC is a fake, no socket, no
``.env``, no real ledger, no send.
"""

from __future__ import annotations

import pytest

from PHX2.free_tier_producer import rpc_gap_recovery as rgr
from PHX2.free_tier_producer import runtime_phase as rp


SAFE_FROM = 435085972
TARGET = 435231678
LAST_COMPLETED = 435087768
PRODUCED_TOTAL = 145664
PRODUCED_COMPLETED = 1797
SKIPPED_TOTAL = 43
IDENTITY_DIGEST = "b" * 64


def _episode_record(**overrides):
    """The inherited episode's shape, exactly as it sits on disk."""

    state = rgr.RpcGapRecoveryState(
        recovery_mode=rgr.GAP_RECOVERY_MODE_RPC_BACKFILL,
        recovery_state=rgr.RECOVERY_STATE_RECOVERY_TERMINAL,
        entry_classification=rgr.ENTRY_REPLAY_REFUSED_OUT_OF_RANGE,
        subscription_identity_digest=IDENTITY_DIGEST,
        authoritative_commitment="confirmed",
        episode_generation=1,
        safe_from_slot=SAFE_FROM,
        recovery_target_slot=TARGET,
        last_completed_slot=LAST_COMPLETED,
        produced_blocks_total=PRODUCED_TOTAL,
        produced_blocks_completed=PRODUCED_COMPLETED,
        skipped_slots_total=SKIPPED_TOTAL,
        overlap_proof_state=rgr.OVERLAP_NOT_PROVEN,
        terminal_reason=rgr.TERMINAL_RPC_BACKFILL_TIMEOUT,
    )
    record = state.to_record()
    record.update(overrides)
    return record


def _store_with(tmp_path, record):
    """A real authenticated store seeded with ``record``."""

    store = rgr.RpcGapRecoveryStore(state_dir=tmp_path)
    store.state = rgr.RpcGapRecoveryState.from_record(record)
    store.persist()
    return store


# --------------------------------------------------------------------------
# integrity invariants
# --------------------------------------------------------------------------

def test_intact_timeout_episode_satisfies_the_pause_invariants():
    ok, token = rgr.recovery_pause_invariants(_episode_record())
    assert ok, token
    assert token == rgr.PAUSE_INVARIANT_OK


def test_inherited_block_accounting_partitions_the_whole_range():
    """produced + explicitly skipped must equal every slot in [safe .. target]."""

    assert PRODUCED_TOTAL + SKIPPED_TOTAL == TARGET - SAFE_FROM + 1


@pytest.mark.parametrize(
    "overrides,expected",
    [
        ({"recovery_mode": rgr.GAP_RECOVERY_MODE_PROVIDER_REPLAY_ONLY},
         rgr.PAUSE_INVARIANT_MODE_INVALID),
        ({"entry_classification": rgr.ENTRY_INELIGIBLE},
         rgr.PAUSE_INVARIANT_CLASSIFICATION_INELIGIBLE),
        ({"subscription_identity_digest": "not-a-digest"},
         rgr.PAUSE_INVARIANT_IDENTITY_INVALID),
        ({"authoritative_commitment": "processed"},
         rgr.PAUSE_INVARIANT_COMMITMENT_INVALID),
        ({"safe_from_slot": -1}, rgr.PAUSE_INVARIANT_BOUNDARY_INVALID),
        ({"recovery_target_slot": SAFE_FROM - 1},
         rgr.PAUSE_INVARIANT_TARGET_INVALID),
        # Progress outside the episode's own range is never resumable.
        ({"last_completed_slot": SAFE_FROM - 5},
         rgr.PAUSE_INVARIANT_PROGRESS_OUT_OF_RANGE),
        ({"last_completed_slot": TARGET + 5},
         rgr.PAUSE_INVARIANT_PROGRESS_OUT_OF_RANGE),
        ({"produced_blocks_completed": PRODUCED_TOTAL + 1},
         rgr.PAUSE_INVARIANT_BLOCK_ACCOUNTING_INVALID),
        # A partition that does not add up hides an unaccounted produced block.
        ({"skipped_slots_total": SKIPPED_TOTAL + 1},
         rgr.PAUSE_INVARIANT_COVERAGE_INCONSISTENT),
        ({"overlap_proof_state": rgr.OVERLAP_PROVEN},
         rgr.PAUSE_INVARIANT_OVERLAP_ALREADY_PROVEN),
    ],
)
def test_broken_evidence_can_never_pause(overrides, expected):
    ok, token = rgr.recovery_pause_invariants(_episode_record(**overrides))
    assert not ok
    assert token == expected


def test_resume_slot_is_last_completed_plus_one_never_the_head():
    assert rgr.next_resume_slot(_episode_record()) == LAST_COMPLETED + 1
    assert rgr.next_resume_slot(_episode_record()) == 435087769
    # No progress yet => the immutable boundary, still never the live head.
    assert rgr.next_resume_slot(
        _episode_record(last_completed_slot=None)) == SAFE_FROM


# --------------------------------------------------------------------------
# in-place authenticated upgrade
# --------------------------------------------------------------------------

def test_terminal_timeout_upgrades_and_retains_its_history(tmp_path):
    store = _store_with(tmp_path, _episode_record())
    assert store.state.recovery_state == rgr.RECOVERY_STATE_RECOVERY_TERMINAL

    assert store.upgrade_terminal_to_retryable() == rgr.UPGRADE_APPLIED

    state = store.state
    assert state.recovery_state == rgr.RECOVERY_STATE_RECOVERY_PAUSED_RETRYABLE
    assert state.paused_reason == rgr.TERMINAL_RPC_BACKFILL_TIMEOUT
    assert state.terminal_reason is None
    # History retained, not erased.
    assert state.prior_terminal_reason == rgr.TERMINAL_RPC_BACKFILL_TIMEOUT
    assert state.prior_terminal_at_utc
    assert state.terminal_upgrade_count == 1
    # Episode identity and every boundary survive verbatim.
    assert state.episode_generation == 1
    assert state.subscription_identity_digest == IDENTITY_DIGEST
    assert state.safe_from_slot == SAFE_FROM
    assert state.recovery_target_slot == TARGET
    assert state.last_completed_slot == LAST_COMPLETED
    assert state.produced_blocks_total == PRODUCED_TOTAL
    assert state.produced_blocks_completed == PRODUCED_COMPLETED
    assert state.skipped_slots_total == SKIPPED_TOTAL
    assert state.overlap_proof_state == rgr.OVERLAP_NOT_PROVEN


def test_upgrade_is_idempotent(tmp_path):
    store = _store_with(tmp_path, _episode_record())
    assert store.upgrade_terminal_to_retryable() == rgr.UPGRADE_APPLIED
    generation_after_first = store.generation
    for _ in range(3):
        assert store.upgrade_terminal_to_retryable() == (
            rgr.UPGRADE_ALREADY_RETRYABLE)
    assert store.state.terminal_upgrade_count == 1
    assert store.state.pause_count == 1
    # A no-op upgrade must not rewrite the authenticated document.
    assert store.generation == generation_after_first


def test_upgrade_survives_a_restart(tmp_path):
    store = _store_with(tmp_path, _episode_record())
    assert store.upgrade_terminal_to_retryable() == rgr.UPGRADE_APPLIED

    reopened = rgr.RpcGapRecoveryStore(state_dir=tmp_path)
    result = reopened.load()
    assert not reopened.quarantined, result
    assert reopened.state.recovery_state == (
        rgr.RECOVERY_STATE_RECOVERY_PAUSED_RETRYABLE)
    assert reopened.state.paused_reason == rgr.TERMINAL_RPC_BACKFILL_TIMEOUT
    assert reopened.has_resumable_episode()
    assert rgr.next_resume_slot(
        reopened.state.to_record()) == LAST_COMPLETED + 1


@pytest.mark.parametrize("reason", [
    rgr.TERMINAL_RPC_BACKFILL_FORK_INCONSISTENT,
    rgr.TERMINAL_RECOVERY_OVERLAP_NOT_PROVEN,
    rgr.TERMINAL_RPC_BACKFILL_BLOCK_UNAVAILABLE,
    rgr.TERMINAL_RECOVERY_STATE_QUARANTINED,
    rgr.TERMINAL_RPC_BACKFILL_MALFORMED_RESPONSE,
])
def test_non_timeout_terminals_stay_terminal(tmp_path, reason):
    store = _store_with(tmp_path, _episode_record(terminal_reason=reason))
    assert store.upgrade_terminal_to_retryable() == (
        rgr.UPGRADE_REFUSED_REASON_NOT_RETRYABLE)
    assert store.state.recovery_state == rgr.RECOVERY_STATE_RECOVERY_TERMINAL
    assert store.state.terminal_reason == reason


def test_timeout_on_broken_evidence_stays_terminal(tmp_path):
    """The reason is retryable but the evidence is not: stays closed."""

    store = _store_with(
        tmp_path, _episode_record(skipped_slots_total=SKIPPED_TOTAL + 1))
    assert store.upgrade_terminal_to_retryable() == (
        rgr.UPGRADE_REFUSED_INTEGRITY)
    assert store.state.recovery_state == rgr.RECOVERY_STATE_RECOVERY_TERMINAL
    assert store.state.terminal_reason == rgr.TERMINAL_RPC_BACKFILL_TIMEOUT


def test_a_healthy_episode_is_not_upgraded(tmp_path):
    store = _store_with(tmp_path, _episode_record(
        recovery_state=rgr.RECOVERY_STATE_RPC_BACKFILL_RUNNING,
        terminal_reason=None))
    assert store.upgrade_terminal_to_retryable() == (
        rgr.UPGRADE_REFUSED_NOT_TERMINAL)
    assert store.state.recovery_state == (
        rgr.RECOVERY_STATE_RPC_BACKFILL_RUNNING)


# --------------------------------------------------------------------------
# pause semantics
# --------------------------------------------------------------------------

def test_pause_retryable_refuses_a_non_retryable_reason(tmp_path):
    store = _store_with(tmp_path, _episode_record(
        recovery_state=rgr.RECOVERY_STATE_RPC_BACKFILL_RUNNING,
        terminal_reason=None))
    assert store.pause_retryable(
        reason=rgr.TERMINAL_RPC_BACKFILL_FORK_INCONSISTENT) is False
    assert store.state.recovery_state == (
        rgr.RECOVERY_STATE_RPC_BACKFILL_RUNNING)
    assert store.state.paused_reason is None


def test_pause_does_not_advance_progress(tmp_path):
    """A pause records WHY it stopped and nothing else about position."""

    store = _store_with(tmp_path, _episode_record(
        recovery_state=rgr.RECOVERY_STATE_RPC_BACKFILL_RUNNING,
        terminal_reason=None))
    before = store.state.to_record()
    assert store.pause_retryable(
        reason=rgr.TERMINAL_RPC_BACKFILL_TIMEOUT) is True
    after = store.state.to_record()
    for field in ("safe_from_slot", "recovery_target_slot",
                  "last_completed_slot", "produced_blocks_total",
                  "produced_blocks_completed", "skipped_slots_total",
                  "overlap_proof_state", "overlap_skip_identity",
                  "episode_generation", "subscription_identity_digest"):
        assert after[field] == before[field], field


def test_leaving_the_pause_clears_the_pause_marker(tmp_path):
    """Only a paused episode may carry a paused reason.

    Resuming moves the state through the ordinary update path; a stale marker
    left behind would make the very next authenticated load cross-inconsistent.
    """

    store = _store_with(tmp_path, _episode_record())
    assert store.upgrade_terminal_to_retryable() == rgr.UPGRADE_APPLIED
    store.update(recovery_state=rgr.RECOVERY_STATE_RPC_BACKFILL_PLANNED)
    assert store.state.paused_reason is None

    reopened = rgr.RpcGapRecoveryStore(state_dir=tmp_path)
    reopened.load()
    assert not reopened.quarantined
    assert reopened.state.recovery_state == (
        rgr.RECOVERY_STATE_RPC_BACKFILL_PLANNED)


def test_records_written_before_the_pause_existed_still_load(tmp_path):
    """Backward compatibility: the new counters are optional, not required."""

    record = _episode_record()
    for name in ("paused_reason", "pause_count", "resume_attempts",
                 "prior_terminal_reason", "prior_terminal_at_utc",
                 "terminal_upgrade_count"):
        record.pop(name, None)
    ok, token = rgr.validate_recovery_record(
        _rehash(record))
    assert ok, token


def _rehash(record):
    """Re-seal a hand-built record so its digest matches its contents."""

    from PHX2.free_tier_producer import checkpoint_envelope as cpe

    stripped = {k: v for k, v in record.items() if k != "record_digest"}
    stripped["record_digest"] = cpe.build_record_digest(
        rgr.CHECKPOINT_KIND_RPC_GAP_RECOVERY, stripped)
    return stripped


def test_paused_state_requires_a_retryable_reason():
    bad = _rehash(_episode_record(
        recovery_state=rgr.RECOVERY_STATE_RECOVERY_PAUSED_RETRYABLE,
        terminal_reason=None, paused_reason=None))
    ok, _token = rgr.validate_recovery_record(bad)
    assert not ok


def test_only_a_paused_state_may_carry_a_paused_reason():
    bad = _rehash(_episode_record(
        recovery_state=rgr.RECOVERY_STATE_RPC_BACKFILL_RUNNING,
        terminal_reason=None,
        paused_reason=rgr.TERMINAL_RPC_BACKFILL_TIMEOUT))
    ok, _token = rgr.validate_recovery_record(bad)
    assert not ok


def test_snapshot_reports_an_open_episode_and_the_exact_remaining_range(
    tmp_path,
):
    store = _store_with(tmp_path, _episode_record())
    assert store.snapshot()["episode_open"] is False

    assert store.upgrade_terminal_to_retryable() == rgr.UPGRADE_APPLIED
    snapshot = store.snapshot()
    assert snapshot["episode_open"] is True
    assert snapshot["recovery_state"] == (
        rgr.RECOVERY_STATE_RECOVERY_PAUSED_RETRYABLE)
    assert snapshot["next_resume_slot"] == LAST_COMPLETED + 1
    assert snapshot["safe_from_slot"] == SAFE_FROM
    assert snapshot["recovery_target_slot"] == TARGET
    assert snapshot["produced_blocks_remaining"] == (
        PRODUCED_TOTAL - PRODUCED_COMPLETED)
    assert snapshot["prior_terminal_reason"] == (
        rgr.TERMINAL_RPC_BACKFILL_TIMEOUT)


# --------------------------------------------------------------------------
# bounded provider-safe catch-up
# --------------------------------------------------------------------------

class _FakeAdapter:
    """Records fetch order; can answer out of order and signal pressure."""

    def __init__(self, *, fail_on=None, pressure_on=None, delay_map=None):
        self.fetched = []
        self.max_concurrent = 0
        self._live = 0
        self._fail_on = set(fail_on or ())
        self._pressure_on = set(pressure_on or ())
        self._delay_map = dict(delay_map or {})
        self.pressure_events = 0
        import threading

        self._lock = threading.Lock()

    def get_block(self, *, slot, commitment):
        import time as _time

        with self._lock:
            self._live += 1
            self.max_concurrent = max(self.max_concurrent, self._live)
        try:
            delay = float(self._delay_map.get(slot, 0.0))
            if delay:
                _time.sleep(delay)
            with self._lock:
                self.fetched.append(int(slot))
            if slot in self._pressure_on:
                self.pressure_events += 1
            if slot in self._fail_on:
                raise rgr.RpcBackfillBoundExceeded(
                    rgr.TERMINAL_RPC_BACKFILL_BLOCK_UNAVAILABLE)
            return {"slot": int(slot), "blockhash": f"hash-{slot}"}
        finally:
            with self._lock:
                self._live -= 1


def _fetch(adapter, slots, concurrency, window=None):
    fetcher = rgr._OrderedBlockFetcher(
        adapter=adapter, commitment="confirmed", slots=slots,
        concurrency=concurrency,
        window=window or max(1, concurrency * rgr.RPC_INFLIGHT_WINDOW_MULTIPLIER))
    return fetcher, list(fetcher)


def test_concurrency_one_is_the_original_serial_shape():
    adapter = _FakeAdapter()
    slots = [10, 11, 12, 13]
    _fetcher, results = _fetch(adapter, slots, concurrency=1)
    assert [slot for slot, _block in results] == slots
    assert adapter.fetched == slots
    assert adapter.max_concurrent == 1


def test_out_of_order_completion_still_applies_in_canonical_order():
    """The first slot is deliberately the SLOWEST to fetch."""

    slots = [100, 101, 102, 103, 104, 105]
    adapter = _FakeAdapter(delay_map={100: 0.25})
    _fetcher, results = _fetch(adapter, slots, concurrency=4)

    assert [slot for slot, _block in results] == slots, (
        "application order must be canonical regardless of completion order")
    # Proof the network really did complete out of order.
    assert adapter.fetched[0] != 100
    assert adapter.max_concurrent > 1


def test_in_flight_work_stays_inside_the_window():
    slots = list(range(200, 240))
    adapter = _FakeAdapter(delay_map={slot: 0.01 for slot in slots})
    _fetcher, results = _fetch(adapter, slots, concurrency=4)
    assert [slot for slot, _block in results] == slots
    assert adapter.max_concurrent <= 4


def test_an_unresolved_block_stops_the_pass_at_its_own_slot():
    """A later block completing first must not advance past the failure."""

    slots = [300, 301, 302, 303]
    adapter = _FakeAdapter(fail_on={301}, delay_map={301: 0.05})
    fetcher = rgr._OrderedBlockFetcher(
        adapter=adapter, commitment="confirmed", slots=slots, concurrency=4,
        window=8)
    applied = []
    with pytest.raises(rgr.RpcBackfillBoundExceeded) as excinfo:
        for slot, _block in fetcher:
            applied.append(slot)
    assert applied == [300], "advanced across an unresolved produced block"
    assert excinfo.value.reason == rgr.TERMINAL_RPC_BACKFILL_BLOCK_UNAVAILABLE


def test_provider_pressure_reduces_concurrency():
    slots = list(range(400, 432))
    adapter = _FakeAdapter(pressure_on={402, 404, 406},
                           delay_map={slot: 0.005 for slot in slots})
    fetcher, results = _fetch(adapter, slots, concurrency=8)
    assert [slot for slot, _block in results] == slots
    assert fetcher.pressure_reductions >= 1
    assert fetcher.current_concurrency < 8


def test_concurrency_ceiling_is_enforced_by_config_validation():
    base = dict(mode=rgr.GAP_RECOVERY_MODE_RPC_BACKFILL,
                authoritative_commitment="confirmed")
    ok = rgr.RpcGapRecoveryConfig(**base, rpc_concurrency=rgr.RPC_CONCURRENCY_MAX)
    assert rgr.validate_rpc_gap_recovery_config(ok) == []
    too_many = rgr.RpcGapRecoveryConfig(
        **base, rpc_concurrency=rgr.RPC_CONCURRENCY_MAX + 1)
    assert any("RPC_CONCURRENCY" in token
               for token in rgr.validate_rpc_gap_recovery_config(too_many))


def test_concurrency_above_one_is_now_a_valid_configuration():
    """The old driver pinned concurrency to exactly 1; a large inherited gap
    cannot converge at that rate."""

    config = rgr.RpcGapRecoveryConfig(
        mode=rgr.GAP_RECOVERY_MODE_RPC_BACKFILL,
        authoritative_commitment="confirmed", rpc_concurrency=8)
    assert rgr.validate_rpc_gap_recovery_config(config) == []


def test_shared_rate_schedule_bounds_the_aggregate_request_rate():
    """Concurrent workers share ONE schedule, so spacing is not multiplied
    away by the number of workers."""

    import threading

    slept = []
    clock = {"now": 0.0}
    lock = threading.Lock()

    def _monotonic():
        return clock["now"]

    def _sleep(seconds):
        with lock:
            slept.append(seconds)
            clock["now"] += seconds

    config = rgr.RpcGapRecoveryConfig(
        mode=rgr.GAP_RECOVERY_MODE_RPC_BACKFILL,
        authoritative_commitment="confirmed",
        rpc_request_spacing_seconds=0.25, rpc_concurrency=4)
    adapter = rgr.SolanaRpcBackfillAdapter(
        rpc_post_fn=lambda *a, **k: (200, {"result": 1}),
        config=config, monotonic_fn=_monotonic, sleep_fn=_sleep)

    for _ in range(4):
        adapter._space_requests()
    # Four claims against a 0.25 s schedule advance the clock ~0.75 s, i.e.
    # each additional claim waits for its own slot rather than firing at once.
    assert clock["now"] == pytest.approx(0.75, abs=1e-6)


def test_pressure_multiplier_backs_off_and_decays():
    config = rgr.RpcGapRecoveryConfig(
        mode=rgr.GAP_RECOVERY_MODE_RPC_BACKFILL,
        authoritative_commitment="confirmed")
    adapter = rgr.SolanaRpcBackfillAdapter(
        rpc_post_fn=lambda *a, **k: (200, {"result": 1}), config=config)
    assert adapter.pressure_multiplier == 1.0
    adapter._note_pressure()
    assert adapter.pressure_multiplier == 2.0
    assert adapter.pressure_events == 1
    for _ in range(rgr.PRESSURE_DECAY_CLEAN_REQUESTS):
        adapter._note_clean()
    assert adapter.pressure_multiplier == 1.0
    for _ in range(64):
        adapter._note_pressure()
    assert adapter.pressure_multiplier <= rgr.MAX_PRESSURE_MULTIPLIER


def test_checkpoint_and_resume_bounds_are_validated():
    base = dict(mode=rgr.GAP_RECOVERY_MODE_RPC_BACKFILL,
                authoritative_commitment="confirmed")
    assert any("CHECKPOINT_EVERY_BLOCKS" in token
               for token in rgr.validate_rpc_gap_recovery_config(
                   rgr.RpcGapRecoveryConfig(**base,
                                            checkpoint_every_blocks=0)))
    assert any("MAX_BACKFILL_RESUME_ATTEMPTS" in token
               for token in rgr.validate_rpc_gap_recovery_config(
                   rgr.RpcGapRecoveryConfig(**base,
                                            max_backfill_resume_attempts=0)))


# --------------------------------------------------------------------------
# pre-soak versus active-soak clocks
# --------------------------------------------------------------------------

def _inputs(**overrides):
    base = dict(recovery_required=True, recovery_episode_open=True,
                recovery_terminal=False, overlap_proven=False,
                produced_blocks_remaining=143867, source_healthy=False)
    base.update(overrides)
    return rp.ActivationInputs(**base)


def _clock(required=7200.0):
    clock_state = {"now": 0.0}

    def _monotonic():
        return clock_state["now"]

    return rp.RuntimePhaseClock(
        required_active_seconds=required, monotonic_fn=_monotonic), clock_state


def test_a_run_starts_in_pre_soak_with_delivery_blocked():
    clock, _now = _clock()
    assert clock.phase == rp.PHASE_PRE_SOAK_RECOVERY
    assert clock.delivery_permitted() is False
    assert clock.active_seconds() == 0.0


def test_pre_soak_seconds_never_count_toward_the_acceptance_clock():
    clock, now = _clock()
    now["now"] = 9000.0            # 2.5 h of inherited recovery
    clock.evaluate(_inputs())      # still blocked
    assert clock.phase == rp.PHASE_PRE_SOAK_RECOVERY
    assert clock.pre_soak_seconds() == pytest.approx(9000.0)
    assert clock.active_seconds() == 0.0
    assert clock.active_requirement_met() is False


def test_activation_requires_overlap_proof_and_a_healthy_source():
    clock, now = _clock()
    now["now"] = 9000.0
    assert clock.evaluate(_inputs()) == rp.ACTIVATION_BLOCKED_RECOVERY_OPEN
    assert clock.evaluate(_inputs(recovery_episode_open=False)) == (
        rp.ACTIVATION_BLOCKED_OVERLAP_UNPROVEN)
    assert clock.evaluate(_inputs(
        recovery_episode_open=False, overlap_proven=True)) == (
        rp.ACTIVATION_BLOCKED_BLOCKS_OUTSTANDING)
    assert clock.evaluate(_inputs(
        recovery_episode_open=False, overlap_proven=True,
        produced_blocks_remaining=0)) == (
        rp.ACTIVATION_BLOCKED_SOURCE_UNHEALTHY)
    assert clock.phase == rp.PHASE_PRE_SOAK_RECOVERY

    assert clock.evaluate(_inputs(
        recovery_episode_open=False, overlap_proven=True,
        produced_blocks_remaining=0, source_healthy=True)) == (
        rp.ACTIVATION_OK)
    assert clock.phase == rp.PHASE_ACTIVE_SOAK


def test_a_terminal_episode_never_activates_the_soak():
    clock, _now = _clock()
    assert clock.evaluate(_inputs(
        recovery_terminal=True, recovery_episode_open=False,
        overlap_proven=True, produced_blocks_remaining=0,
        source_healthy=True)) == rp.ACTIVATION_BLOCKED_RECOVERY_TERMINAL
    assert clock.phase == rp.PHASE_PRE_SOAK_RECOVERY
    assert clock.delivery_permitted() is False


def test_the_acceptance_clock_measures_only_active_seconds():
    clock, now = _clock(required=7200.0)
    now["now"] = 9000.0
    clock.evaluate(_inputs())
    ready = _inputs(recovery_episode_open=False, overlap_proven=True,
                    produced_blocks_remaining=0, source_healthy=True)
    clock.evaluate(ready)
    assert clock.phase == rp.PHASE_ACTIVE_SOAK
    assert clock.delivery_permitted() is True

    now["now"] = 9000.0 + 7199.0
    assert clock.active_seconds() == pytest.approx(7199.0)
    assert clock.active_requirement_met() is False
    now["now"] = 9000.0 + 7200.0
    assert clock.active_requirement_met() is True
    # Pre-soak is frozen at the transition, never inflated by soak time.
    assert clock.pre_soak_seconds() == pytest.approx(9000.0)


def test_activation_is_one_way():
    clock, now = _clock()
    ready = _inputs(recovery_episode_open=False, overlap_proven=True,
                    produced_blocks_remaining=0, source_healthy=True)
    assert clock.evaluate(ready) == rp.ACTIVATION_OK
    now["now"] = 100.0
    # A later degraded reading must not rewind the acceptance clock.
    assert clock.evaluate(_inputs()) == rp.ACTIVATION_OK
    assert clock.phase == rp.PHASE_ACTIVE_SOAK
    assert clock.active_seconds() == pytest.approx(100.0)


def test_a_run_with_nothing_inherited_only_waits_for_source_health():
    clock, _now = _clock()
    assert clock.evaluate(_inputs(
        recovery_required=False, source_healthy=False)) == (
        rp.ACTIVATION_BLOCKED_SOURCE_UNHEALTHY)
    assert clock.evaluate(_inputs(
        recovery_required=False, source_healthy=True)) == rp.ACTIVATION_OK


def test_phase_snapshot_is_redaction_safe_and_complete():
    clock, now = _clock()
    now["now"] = 1234.0
    clock.evaluate(_inputs())
    snapshot = clock.snapshot()
    for key in ("runtime_phase", "required_active_soak_seconds",
                "pre_soak_recovery_start_utc", "pre_soak_recovery_end_utc",
                "pre_soak_recovery_seconds", "active_soak_start_utc",
                "active_soak_elapsed_seconds", "active_soak_requirement_met",
                "delivery_permitted_by_phase", "last_activation_reason",
                "activation_evaluations"):
        assert key in snapshot
    assert snapshot["runtime_phase"] in rp.RUNTIME_PHASES
    assert snapshot["last_activation_reason"] in rp.ACTIVATION_REASONS
    assert snapshot["active_soak_start_utc"] is None
    blob = repr(snapshot).lower()
    for forbidden in ("token", "chat_id", "webhook", "authorization",
                      "api.telegram.org", "bot"):
        assert forbidden not in blob

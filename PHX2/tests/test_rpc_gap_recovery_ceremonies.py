"""Offline fake-provider ceremonies for the bounded RPC gap recovery.

Ceremony A  ordinary provider replay: certified path untouched, RPC unused.
Ceremony B  replay refused (OUT_OF_RANGE) -> quarantined live stream + bounded
            RPC backfill -> exact overlap proof -> drain -> healthy; send
            authorization blocked until proof.
Ceremony C  restart midway (coordinator-level, test_rpc_gap_backfill_recovery).
Ceremony D  required produced block unavailable -> terminal, no live-head.
Ceremony E  fork inconsistency -> terminal, no send.
Ceremony F  operator tool (test_terminal_recovery_operator).

Everything runs against fake gRPC sources and a fake JSON-RPC transport; no
socket, ledger writer or delivery transport is ever constructed.
"""

from __future__ import annotations

import threading
import time
from types import SimpleNamespace
from typing import Any, Callable, Dict, List, Optional, Tuple

import pytest

from PHX2.free_tier_producer import rpc_gap_recovery as rgr
from PHX2.free_tier_producer import stream_cursor as sc
from PHX2.free_tier_producer.paid_grpc_source import (
    build_transaction_skip_identity,
)
from PHX2.free_tier_producer.paid_provider import (
    ProviderCandidateDedupe,
    SingleGrpcPumpSwapDiscovery,
)
from PHX2.tests.test_rpc_gap_backfill_recovery import (
    BOUNDARY_SIG,
    BOUNDARY_SLOT,
    FakeRpcTransport,
    IDENTITY_DIGEST,
    OVERLAP_SIG,
    OVERLAP_SLOT,
    OVERLAP_TX_INDEX,
    PRODUCED,
    build_chain,
    make_config,
    make_coordinator,
    make_terminal_cursor,
    open_episode_with_target,
)


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    import socket
    import urllib.request

    def _refuse(*_args, **_kwargs):
        raise AssertionError("NETWORK_CONSTRUCTION_FORBIDDEN_IN_CEREMONIES")

    monkeypatch.setattr(socket, "socket", _refuse)
    monkeypatch.setattr(urllib.request, "urlopen", _refuse)
    yield


def _wait_until(predicate: Callable[[], bool], *, timeout: float = 10.0,
                interval: float = 0.02) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return predicate()


def make_live_cursor(state_dir, *, boundary: int = BOUNDARY_SLOT):
    """A healthy cursor with one committed position (NOT terminal)."""

    store = sc.build_cursor_store(
        state_dir=state_dir, subscription_identity_digest=IDENTITY_DIGEST)
    store.load()
    identity = sc.build_stream_event_identity(
        slot=boundary, signature=BOUNDARY_SIG, transaction_index=0)
    store.commit_event(slot=boundary, identity=identity,
                       signature=BOUNDARY_SIG)
    assert not store.is_terminal()
    return store


class FakeStreamSource:
    """Scripted stand-in for ``PaidCreatePoolYellowstoneSource``."""

    def __init__(self, script: Callable[["FakeStreamSource"], Any],
                 kwargs: Dict[str, Any]) -> None:
        self._script = script
        self.kwargs = dict(kwargs)
        self.from_slot = kwargs.get("from_slot")
        self.cursor = kwargs.get("cursor")
        self.observer = kwargs.get("transaction_observer")
        self.replay_requested = self.from_slot is not None
        self.replay_from_slot = self.from_slot
        self.replay_position_rejected = False
        self.replay_first_available = None
        self.replay_retention_reason = sc.REASON_NONE
        self.grpc_status_code: Optional[str] = None
        self.sanitized_error_category: Optional[str] = None
        self.sanitized_details: Optional[str] = None
        self.error_class: Optional[str] = None
        self.stream_phase = "NOT_STARTED"
        self.iterator_end_kind = "NOT_STARTED"
        self.cancellation_requested = False
        self.last_refusal_reason = "NONE"
        self.overlap_observed = False
        self.overlap_proof_accepted = False
        self.overlap_proof_slot: Optional[int] = None
        self.expected_overlap_slot = self.from_slot
        try:
            self.recovery_generation = int(
                self.cursor.state.recovery_generation)
        except Exception:
            self.recovery_generation = 0
        self.stream_generation = int(kwargs.get("stream_generation") or 0)
        self.events_scanned = 0
        self.transactions_scanned = 0
        self.create_pool_yielded = 0
        self.reserve_events_decoded = 0
        self.fee_events_decoded = 0
        self.replayed_events = 0
        self.replay_duplicates_suppressed = 0
        self.cursor_commits = 0
        self.cursor_commit_failures = 0
        self.cursor_holds = 0
        self.first_slot_observed: Optional[int] = None
        self.last_slot_observed: Optional[int] = None
        self.highest_slot_observed: Optional[int] = None
        self.stream_started_epoch: Optional[float] = None
        self.stream_ended_epoch: Optional[float] = None
        self.first_update_epoch: Optional[float] = None
        self.last_update_epoch: Optional[float] = None
        self.last_decoded_event_epoch: Optional[float] = None
        self.last_event_provider_time_utc: Optional[str] = None
        self.last_event_time_source = "UNKNOWN"
        self.last_event_replayed = False
        self.admission_counters = None
        self.closed = threading.Event()

    def observe(self, slot: int, signature: str, index: int) -> None:
        self.first_slot_observed = (
            slot if self.first_slot_observed is None
            else self.first_slot_observed)
        self.last_slot_observed = slot
        self.last_update_epoch = time.time()
        if self.first_update_epoch is None:
            self.first_update_epoch = self.last_update_epoch
        if self.observer is not None:
            self.observer(slot, signature, index,
                          build_transaction_skip_identity(
                              slot, signature, index))

    def close(self) -> None:
        self.cancellation_requested = True
        self.closed.set()

    def diagnostic_snapshot(self) -> Dict[str, Any]:
        return {
            "error_class": self.error_class,
            "grpc_status_code": self.grpc_status_code,
            "sanitized_error_category": self.sanitized_error_category,
            "sanitized_details": self.sanitized_details,
            "stream_phase": self.stream_phase,
            "iterator_end_kind": self.iterator_end_kind,
            "cancellation_requested": bool(self.cancellation_requested),
        }

    def iter_events(self, *, max_events: int):
        self.stream_started_epoch = time.time()
        result = self._script(self)
        if result is not None:
            yield from result
        self.stream_ended_epoch = time.time()


def script_refused(code: str, category: str):
    def _script(source: FakeStreamSource):
        source.replay_position_rejected = source.replay_requested
        source.grpc_status_code = code
        source.sanitized_error_category = category
        source.last_refusal_reason = f"STREAM_ERROR:{code}"
        source.iterator_end_kind = "GRPC_ERROR"
        return None
    return _script


def script_auth_failed():
    def _script(source: FakeStreamSource):
        source.grpc_status_code = "UNAUTHENTICATED"
        source.sanitized_error_category = (
            "AUTHENTICATION_OR_PERMISSION_FAILURE")
        source.last_refusal_reason = "STREAM_ERROR:UNAUTHENTICATED"
        source.iterator_end_kind = "GRPC_ERROR"
        return None
    return _script


def script_replay_honored():
    """The provider honours ``from_slot``: the certified path closes the gap."""

    def _script(source: FakeStreamSource):
        boundary = source.from_slot
        if boundary is None:
            return None
        source.observe(boundary, BOUNDARY_SIG, 0)
        source.overlap_observed = True
        source.overlap_proof_slot = boundary
        source.replayed_events = 1
        prove = getattr(source.cursor, "mark_overlap_proven", None)
        if callable(prove):
            source.overlap_proof_accepted = bool(prove(
                requested_from_slot=boundary,
                proven_boundary_slot=boundary,
                recovery_generation=source.recovery_generation))
        source.iterator_end_kind = "CLEAN_EOF"
        return None
    return _script


def script_quarantine(observations: List[Tuple[int, str, int]],
                      release: threading.Event,
                      yields: Optional[List[Tuple[Tuple[int, str, int], Any]]] = None):
    """Observe scripted transactions, optionally yield candidates, then hold."""

    def _script(source: FakeStreamSource):
        for slot, signature, index in observations:
            source.observe(slot, signature, index)
        for position, event in (yields or []):
            slot, signature, index = position
            source.observe(slot, signature, index)
            yield event
        release.wait(timeout=15.0)
        source.iterator_end_kind = "CLEAN_EOF"
    return _script


def script_idle(release: threading.Event):
    def _script(_source: FakeStreamSource):
        release.wait(timeout=15.0)
        return None
    return _script


class ScriptedFactory:
    """Cursor-aware, observer-aware factory over a queue of scripts."""

    def __init__(self, scripts: List[Callable[[FakeStreamSource], Any]],
                 *, exhausted_release: Optional[threading.Event] = None) -> None:
        self._scripts = list(scripts)
        self._exhausted_release = exhausted_release or threading.Event()
        self.sources: List[FakeStreamSource] = []

    def __call__(self, *, from_slot: Any = None, cursor: Any = None,
                 downstream_durable_fn: Any = None, stream_generation: int = 0,
                 transaction_observer: Any = None) -> FakeStreamSource:
        script = (self._scripts.pop(0) if self._scripts
                  else script_idle(self._exhausted_release))
        source = FakeStreamSource(script, dict(
            from_slot=from_slot, cursor=cursor,
            downstream_durable_fn=downstream_durable_fn,
            stream_generation=stream_generation,
            transaction_observer=transaction_observer))
        self.sources.append(source)
        return source

    def release_idle(self) -> None:
        self._exhausted_release.set()


def make_owner(factory, cursor, coordinator=None, **kwargs):
    return SingleGrpcPumpSwapDiscovery(
        source_factory=factory,
        dedupe=ProviderCandidateDedupe(max_entries=64),
        cursor_store=cursor,
        gap_recovery=coordinator,
        require_cursor_aware_factory=True,
        reconnect_backoff_seconds=0.01,
        stale_after_seconds=30.0,
        reconnect_jitter_fraction=0.0,
        **kwargs)


def make_candidate_event(slot: int, signature: str) -> Any:
    return SimpleNamespace(
        base_mint="C4ndAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAApump",
        mint="C4ndAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAApump",
        pool_account="Poo1AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
        pool_program_id="Prog1AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
        quote_mint="So11111111111111111111111111111111111111112",
        event_id=None,
        provider_event_id=f"yellowstone_{slot}_{signature[:16]}",
        observed_at_utc="2026-07-22T00:00:00Z",
        raw_event_hash=None,
        event_type="create_pool",
    )


# ---------------------------------------------------------------------------
# Ceremony A -- ordinary provider replay stays the certified path
# ---------------------------------------------------------------------------

class TestCeremonyAOrdinaryReplay:
    def test_replay_honored_leaves_rpc_recovery_unused(self, tmp_path) -> None:
        cursor = make_live_cursor(tmp_path)
        transport = FakeRpcTransport(
            head_slot=200, produced=PRODUCED, blocks=build_chain(PRODUCED))
        coordinator = make_coordinator(tmp_path, cursor, transport=transport)
        release = threading.Event()
        factory = ScriptedFactory(
            [script_replay_honored()], exhausted_release=release)
        owner = make_owner(factory, cursor, coordinator)
        owner.start()
        try:
            assert _wait_until(lambda: len(factory.sources) >= 2)
        finally:
            factory.release_idle()
            owner.stop()
        # The certified replay path proved the boundary; the RPC machinery was
        # never engaged and no RPC request was ever issued.
        assert cursor.state.last_proven_replay_boundary_slot == BOUNDARY_SLOT
        assert not cursor.is_terminal()
        assert coordinator.state() == rgr.RECOVERY_STATE_IDLE
        assert transport.calls == []
        assert factory.sources[0].overlap_proof_accepted

    def test_default_owner_without_coordinator_is_byte_identical(
            self, tmp_path) -> None:
        cursor = make_live_cursor(tmp_path)
        release = threading.Event()
        factory = ScriptedFactory(
            [script_refused("OUT_OF_RANGE", "GRPC_OUT_OF_RANGE")],
            exhausted_release=release)
        owner = make_owner(factory, cursor, None)
        owner.start()
        try:
            assert _wait_until(lambda: owner.snapshot()["status"] == "STOPPED")
        finally:
            factory.release_idle()
            owner.stop()
        # Certified terminal behaviour: stop, cursor terminal-locked,
        # operator remediation required.
        assert cursor.is_terminal()
        assert cursor.resume_decision().action == (
            sc.RESUME_ACTION_REFUSE_TERMINAL)
        assert "gap_recovery" not in owner.snapshot()


# ---------------------------------------------------------------------------
# Ceremony B -- replay refused, bounded RPC recovery succeeds
# ---------------------------------------------------------------------------

class TestCeremonyBRpcRecovery:
    def _run_ceremony(self, tmp_path, *, with_candidate: bool):
        cursor = make_live_cursor(tmp_path)
        transport = FakeRpcTransport(
            head_slot=200, produced=PRODUCED, blocks=build_chain(PRODUCED))
        coordinator = make_coordinator(tmp_path, cursor, transport=transport)
        release = threading.Event()
        yields = []
        if with_candidate:
            yields.append(((112, "S1gLater112", 0),
                           make_candidate_event(112, "S1gLater112")))
        quarantine = script_quarantine(
            [(OVERLAP_SLOT, OVERLAP_SIG, OVERLAP_TX_INDEX)], release,
            yields=yields)
        factory = ScriptedFactory(
            [script_refused("OUT_OF_RANGE", "GRPC_OUT_OF_RANGE"), quarantine],
            exhausted_release=release)
        owner = make_owner(factory, cursor, coordinator)
        owner.start()
        try:
            # The quarantined stream is live and the backfill is running:
            # sends must be blocked throughout.
            assert _wait_until(lambda: len(factory.sources) >= 2)
            authorized, reason = owner.authorizes_send()
            assert authorized is False
            assert reason != sc.REASON_NONE
            assert _wait_until(coordinator.is_proven, timeout=15.0)
            release.set()
            assert _wait_until(
                lambda: not cursor.is_terminal(), timeout=15.0)
        finally:
            release.set()
            factory.release_idle()
            owner.stop()
        return cursor, coordinator, owner, transport

    def test_exact_overlap_recovers_and_returns_healthy(self, tmp_path) -> None:
        cursor, coordinator, owner, transport = self._run_ceremony(
            tmp_path, with_candidate=False)
        assert coordinator.is_proven()
        assert not cursor.is_terminal()
        assert cursor.state.recovery_status == sc.RECOVERY_CLOSED
        snapshot = coordinator.snapshot()
        assert snapshot["overlap_proof_state"] == rgr.OVERLAP_PROVEN
        assert snapshot["overlap_slot"] == OVERLAP_SLOT
        assert snapshot["skipped_slots_total"] == 2
        # Exactly one live gRPC owner at any moment.
        assert owner.snapshot()["max_active_streams"] == 1
        # The overlap event applied once: its identity is durably deduped.
        assert cursor.is_duplicate(build_transaction_skip_identity(
            OVERLAP_SLOT, OVERLAP_SIG, OVERLAP_TX_INDEX))

    def test_unseen_buffered_candidate_applies_once(self, tmp_path) -> None:
        cursor, coordinator, owner, transport = self._run_ceremony(
            tmp_path, with_candidate=True)
        drained = owner.drain(max_candidates=10)
        mints = [c.get("token_mint") for c in drained]
        assert mints.count(
            "C4ndAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAApump") == 1
        assert coordinator.snapshot()["unseen_buffered_events_applied"] == 1
        # Re-admitting the identical candidate is suppressed by exact
        # event-id dedupe: it can never apply twice.
        assert owner._admit_candidate(dict(
            token_mint="C4ndAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAApump",
            provider_event_id="yellowstone_112_S1gLater112")) is False

    def test_restart_resumes_same_episode_not_live_head(self, tmp_path) -> None:
        # A terminal cursor with a persisted, target-bearing episode: the
        # restarted owner resumes THAT episode instead of bootstrapping.
        cursor = make_terminal_cursor(tmp_path)
        transport = FakeRpcTransport(
            head_slot=200, produced=PRODUCED, blocks=build_chain(PRODUCED))
        seed = make_coordinator(tmp_path, cursor, transport=transport)
        open_episode_with_target(seed, cursor)
        del seed
        cursor2 = sc.build_cursor_store(
            state_dir=tmp_path, subscription_identity_digest=IDENTITY_DIGEST)
        cursor2.load()
        transport2 = FakeRpcTransport(
            head_slot=200, produced=PRODUCED, blocks=build_chain(PRODUCED))
        coordinator = make_coordinator(tmp_path, cursor2, transport=transport2)
        release = threading.Event()
        factory = ScriptedFactory(
            [script_quarantine([], release)], exhausted_release=release)
        owner = make_owner(factory, cursor2, coordinator)
        owner.start()
        try:
            assert _wait_until(coordinator.is_proven, timeout=15.0)
            release.set()
            assert _wait_until(lambda: not cursor2.is_terminal(), timeout=15.0)
        finally:
            release.set()
            factory.release_idle()
            owner.stop()
        assert coordinator.snapshot()["overlap_slot"] == OVERLAP_SLOT


# ---------------------------------------------------------------------------
# refusals that must NOT enter RPC recovery
# ---------------------------------------------------------------------------

class TestIneligibleRefusals:
    @pytest.mark.parametrize("code,category", [
        ("INVALID_ARGUMENT", "GRPC_INVALID_ARGUMENT"),
        ("NOT_FOUND", "GRPC_NOT_FOUND"),
    ])
    def test_non_retention_replay_refusal_stays_terminal(
            self, tmp_path, code, category) -> None:
        cursor = make_live_cursor(tmp_path)
        transport = FakeRpcTransport(
            head_slot=200, produced=PRODUCED, blocks=build_chain(PRODUCED))
        coordinator = make_coordinator(tmp_path, cursor, transport=transport)
        release = threading.Event()
        factory = ScriptedFactory(
            [script_refused(code, category)], exhausted_release=release)
        owner = make_owner(factory, cursor, coordinator)
        owner.start()
        try:
            assert _wait_until(lambda: owner.snapshot()["status"] == "STOPPED")
        finally:
            factory.release_idle()
            owner.stop()
        assert cursor.is_terminal()
        assert coordinator.state() == rgr.RECOVERY_STATE_IDLE
        assert transport.calls == []

    def test_authorization_failure_remains_terminal(self, tmp_path) -> None:
        cursor = make_live_cursor(tmp_path)
        transport = FakeRpcTransport(
            head_slot=200, produced=PRODUCED, blocks=build_chain(PRODUCED))
        coordinator = make_coordinator(tmp_path, cursor, transport=transport)
        release = threading.Event()
        factory = ScriptedFactory(
            [script_auth_failed()], exhausted_release=release)
        owner = make_owner(factory, cursor, coordinator)
        owner.start()
        try:
            assert _wait_until(
                lambda: owner.snapshot()["status"] == "AUTH_FAILED")
        finally:
            factory.release_idle()
            owner.stop()
        assert coordinator.state() == rgr.RECOVERY_STATE_IDLE
        assert transport.calls == []

    def test_terminal_without_persisted_episode_stays_terminal(
            self, tmp_path) -> None:
        # Restart against a terminal cursor with NO recorded eligible episode
        # (e.g. a pre-feature terminal): certified stop, no recovery.
        cursor = make_terminal_cursor(tmp_path)
        transport = FakeRpcTransport(
            head_slot=200, produced=PRODUCED, blocks=build_chain(PRODUCED))
        coordinator = make_coordinator(tmp_path, cursor, transport=transport)
        release = threading.Event()
        factory = ScriptedFactory([], exhausted_release=release)
        owner = make_owner(factory, cursor, coordinator)
        owner.start()
        try:
            assert _wait_until(lambda: owner.snapshot()["status"] == "STOPPED")
        finally:
            factory.release_idle()
            owner.stop()
        assert cursor.is_terminal()
        assert factory.sources == []  # no stream was ever constructed


# ---------------------------------------------------------------------------
# Ceremony D -- unavailable block
# ---------------------------------------------------------------------------

class TestCeremonyDUnavailableBlock:
    def test_block_unavailable_is_terminal_never_live_head(
            self, tmp_path) -> None:
        cursor = make_live_cursor(tmp_path)
        blocks = build_chain(PRODUCED)
        del blocks[106]
        transport = FakeRpcTransport(
            head_slot=200, produced=PRODUCED, blocks=blocks,
            pre_responses={("getBlock", 106): [
                (200, {"error": {"code": -32004, "message": "not yet"}}),
            ] * 12})
        coordinator = make_coordinator(
            tmp_path, cursor, transport=transport,
            config=make_config(max_retries_per_request=2))
        release = threading.Event()
        factory = ScriptedFactory(
            [script_refused("OUT_OF_RANGE", "GRPC_OUT_OF_RANGE"),
             script_quarantine(
                 [(OVERLAP_SLOT, OVERLAP_SIG, OVERLAP_TX_INDEX)], release)],
            exhausted_release=release)
        owner = make_owner(factory, cursor, coordinator)
        owner.start()
        try:
            assert _wait_until(coordinator.is_terminal, timeout=15.0)
            release.set()
            assert _wait_until(
                lambda: owner.snapshot()["status"] == "STOPPED", timeout=15.0)
        finally:
            release.set()
            factory.release_idle()
            owner.stop()
        assert coordinator.terminal_reason() in (
            rgr.TERMINAL_RPC_BACKFILL_BLOCK_UNAVAILABLE,
            rgr.TERMINAL_RPC_BACKFILL_CONSECUTIVE_FAILURES)
        assert cursor.is_terminal()
        assert cursor.resume_decision().action == (
            sc.RESUME_ACTION_REFUSE_TERMINAL)
        authorized, _reason = owner.authorizes_send()
        assert authorized is False


# ---------------------------------------------------------------------------
# Ceremony E -- fork inconsistency
# ---------------------------------------------------------------------------

class TestCeremonyEForkInconsistency:
    def test_fork_between_rpc_and_buffered_evidence_is_terminal(
            self, tmp_path) -> None:
        cursor = make_terminal_cursor(tmp_path)
        blocks = build_chain(PRODUCED, overlap_sig="S1gDifferent")
        transport = FakeRpcTransport(
            head_slot=200, produced=PRODUCED, blocks=blocks)
        coordinator = make_coordinator(tmp_path, cursor, transport=transport)
        open_episode_with_target(coordinator, cursor)
        assert not coordinator.run_backfill()
        assert coordinator.terminal_reason() == (
            rgr.TERMINAL_RPC_BACKFILL_FORK_INCONSISTENT)
        assert cursor.is_terminal()
        merged = {
            **cursor.snapshot(),
            "stream_state": sc.STATE_GAP_UNRESOLVED,
            "live_healthy": False,
            "gap_unresolved": True,
        }
        authorized, _reason = sc.source_health_authorizes_send(merged)
        assert authorized is False


# ---------------------------------------------------------------------------
# production configuration surfaces
# ---------------------------------------------------------------------------

class TestProductionConfiguration:
    def test_session_parser_exposes_recovery_arguments(self) -> None:
        import argparse

        from PHX2.free_tier_producer import free_tier_session

        parser = argparse.ArgumentParser()
        free_tier_session._add_args(parser)
        options = {
            option
            for action in parser._actions
            for option in getattr(action, "option_strings", ())
        }
        assert "--grpc-gap-recovery" in options
        assert "--rpc-recovery-commitment" in options
        assert "--rpc-recovery-max-gap-slots" in options
        assert "--rpc-recovery-max-quarantine-events" in options

    def test_canonical_launcher_vector_states_recovery_mode(self) -> None:
        from PHX2.free_tier_producer import launcher_contract as lc

        argv = lc.canonical_launcher_arguments(
            launcher="launch_window_04.ps1",
            expected_head="a" * 40,
            ledger_baseline=("0" * 64) + ":1:1")
        assert "--grpc-gap-recovery" in argv
        assert argv[argv.index("--grpc-gap-recovery") + 1] == "live_epoch"
        # Helius-primary production owns reconnect recovery through the
        # bounded exact-slot HTTP path.  Bounded six-hour DexScreener
        # candidate recovery is part of the armed contract (2026-07-30
        # remediation) -- candidate recovery, never migration-source
        # authority; historical RPC replay stays absent below.
        assert argv.count("--enable-dexscreener-restart-backfill") == 1
        assert "--enable-helius-http-recovery" in argv
        assert not any(
            token.startswith("--rpc-recovery-") for token in argv)
        verdict = lc.validate_launcher_arguments(argv, expected_head="a" * 40)
        assert verdict.allowed, verdict.refusals

    def test_launcher_without_recovery_mode_refused(self) -> None:
        from PHX2.free_tier_producer import launcher_contract as lc

        argv = lc.canonical_launcher_arguments(
            launcher="launch_window_04.ps1",
            expected_head="a" * 40,
            ledger_baseline=("0" * 64) + ":1:1")
        index = argv.index("--grpc-gap-recovery")
        stripped = argv[:index] + argv[index + 2:]
        verdict = lc.validate_launcher_arguments(
            stripped, expected_head="a" * 40)
        assert not verdict.allowed
        assert lc.REFUSAL_GAP_RECOVERY_NOT_CANONICAL in verdict.refusals

    def test_production_contract_refuses_absent_mode_when_presented(
            self) -> None:
        from PHX2.free_tier_producer import production_grpc_contract as pgc

        verdict = pgc.evaluate_production_grpc_contract(
            provider_mode="paid_primary",
            paid_provider_modes=("paid_primary",),
            cursor_store=object(),
            cursor_state_dir=r"C:\Users\BalaC\phx2_paid_primary_runtime\state",
            out_dir=r"C:\Users\BalaC\phx2_paid_primary_runtime\runs\x",
            source_factory=None,
            gap_recovery_mode=None,
        )
        assert pgc.REFUSAL_GAP_RECOVERY_MODE_ABSENT in verdict.refusals

    def test_production_contract_legacy_callers_unchanged(self) -> None:
        from PHX2.free_tier_producer import production_grpc_contract as pgc

        verdict = pgc.evaluate_production_grpc_contract(
            provider_mode="paid_primary",
            paid_provider_modes=("paid_primary",),
            cursor_store=object(),
            cursor_state_dir=r"C:\Users\BalaC\phx2_paid_primary_runtime\state",
            out_dir=r"C:\Users\BalaC\phx2_paid_primary_runtime\runs\x",
            source_factory=None,
        )
        assert pgc.REFUSAL_GAP_RECOVERY_MODE_ABSENT not in verdict.refusals
        assert pgc.REFUSAL_GAP_RECOVERY_MODE_INVALID not in verdict.refusals

    def test_recovery_snapshot_never_exposes_raw_identity(self, tmp_path) -> None:
        cursor = make_terminal_cursor(tmp_path)
        transport = FakeRpcTransport(
            head_slot=200, produced=PRODUCED, blocks=build_chain(PRODUCED))
        coordinator = make_coordinator(tmp_path, cursor, transport=transport)
        open_episode_with_target(coordinator, cursor)
        assert coordinator.run_backfill()
        snapshot = coordinator.snapshot()
        flat = repr(sorted(snapshot.items()))
        assert OVERLAP_SIG not in flat
        assert "overlap_identity_digest" in snapshot
        assert snapshot["rpc_transport_configured"] is True

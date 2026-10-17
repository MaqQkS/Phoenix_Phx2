"""Bounded RPC gap-backfill recovery: units, bounds and cursor resolution.

PROVIDER-REPLAY-001: with a provider that refuses every exact ``from_slot``
replay, each disconnect terminal-locked the cursor with no tracked exit.  The
tests here pin the fail-closed shape of the new exit: entry classification,
explicit bounds, authenticated buffered quarantine, the provider-neutral RPC
adapter, the RPC->geyser bridge, and the ONE cursor transition that production
evidence -- and nothing else -- may perform.

Everything is offline: fake transports, fake clocks, temporary directories.
No socket, no ledger, no transport object is ever constructed.
"""

from __future__ import annotations

import threading
from typing import Any, Dict, List, Optional, Tuple

import pytest

from PHX2.free_tier_producer import rpc_gap_recovery as rgr
from PHX2.free_tier_producer import stream_cursor as sc
from PHX2.free_tier_producer.paid_grpc_source import (
    build_transaction_skip_identity,
)
from PHX2.stage29.pumpswap_program_constants import PUMPSWAP_PROGRAM_ID


IDENTITY_DIGEST = sc.compute_subscription_identity_digest(
    source_kind=sc.STREAM_SOURCE_YELLOWSTONE,
    commitment="CONFIRMED",
    transaction_filter_name="phx2_pumpswap_transactions",
    account_include=[PUMPSWAP_PROGRAM_ID],
    program_id=PUMPSWAP_PROGRAM_ID,
    migration_versions_supported=("migrate", "migrate_v2"),
    decoder_schema_version=sc.STREAM_CURSOR_SCHEMA_V1,
)

BOUNDARY_SLOT = 100
BOUNDARY_SIG = "S1gBoundary"
OVERLAP_SLOT = 110
OVERLAP_SIG = "S1gTarget11"
OVERLAP_TX_INDEX = 3
LATER_SIG = "S1gLater112"

BLOCK_TIME = 1_753_142_400  # 2025-07-22T00:00:00Z as a plain unix stamp


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    """No recovery test may construct a socket or perform a real HTTP call."""

    import socket
    import urllib.request

    def _refuse(*_args, **_kwargs):
        raise AssertionError("NETWORK_CONSTRUCTION_FORBIDDEN_IN_RECOVERY_TESTS")

    monkeypatch.setattr(socket, "socket", _refuse)
    monkeypatch.setattr(urllib.request, "urlopen", _refuse)
    yield


def make_terminal_cursor(state_dir, *, boundary: int = BOUNDARY_SLOT):
    """A cursor terminal-locked by a replay-retention refusal at ``boundary``."""

    store = sc.build_cursor_store(
        state_dir=state_dir, subscription_identity_digest=IDENTITY_DIGEST)
    store.load()
    identity = sc.build_stream_event_identity(
        slot=boundary, signature=BOUNDARY_SIG, transaction_index=0)
    store.commit_event(slot=boundary, identity=identity,
                       signature=BOUNDARY_SIG)
    store.mark_disconnect()
    store.begin_stream_attempt(requested_from_slot=boundary)
    store.mark_replay_retention_exceeded()
    assert store.is_terminal()
    assert store.state.recovery_reason == sc.REASON_REPLAY_POSITION_TOO_OLD
    assert store.resume_decision().action == sc.RESUME_ACTION_REFUSE_TERMINAL
    return store


def make_tx(signature: str, *, relevant: bool = True,
            failed: bool = False) -> Dict[str, Any]:
    keys = ["FeePayer1111111111111111111111111111111111"]
    if relevant:
        keys.append(PUMPSWAP_PROGRAM_ID)
    return {
        "transaction": {
            "signatures": [signature],
            "message": {"accountKeys": keys, "instructions": []},
        },
        "meta": {
            "err": ({"InstructionError": [0, "Custom"]} if failed else None),
            "logMessages": [],
            "innerInstructions": [],
            "preTokenBalances": [],
            "postTokenBalances": [],
        },
    }


def make_block(slot: int, parent_slot: int, blockhash: str,
               previous_blockhash: str, txs: List[Dict[str, Any]],
               block_time: Optional[int] = BLOCK_TIME) -> Dict[str, Any]:
    return {
        "parentSlot": parent_slot,
        "blockhash": blockhash,
        "previousBlockhash": previous_blockhash,
        "blockTime": block_time,
        "transactions": txs,
    }


def build_chain(produced: List[int], *,
                overlap_slot: Optional[int] = OVERLAP_SLOT,
                overlap_sig: Optional[str] = OVERLAP_SIG,
                overlap_index: int = OVERLAP_TX_INDEX,
                ) -> Dict[int, Dict[str, Any]]:
    blocks: Dict[int, Dict[str, Any]] = {}
    prev_slot = produced[0] - 1
    prev_hash = "Hgenesis"
    for slot in produced:
        txs: List[Dict[str, Any]] = []
        if overlap_slot is not None and slot == overlap_slot \
                and overlap_sig is not None:
            for filler in range(overlap_index):
                txs.append(make_tx(f"S1gFi{slot}x{filler}", relevant=False))
            txs.append(make_tx(overlap_sig, relevant=True))
        blocks[slot] = make_block(slot, prev_slot, f"H{slot}", prev_hash, txs)
        prev_slot = slot
        prev_hash = f"H{slot}"
    return blocks


class FakeRpcTransport:
    """Deterministic JSON-RPC transport with per-slot scripted failures."""

    def __init__(self, *, head_slot: int, produced: List[int],
                 blocks: Dict[int, Dict[str, Any]],
                 pre_responses: Optional[Dict[Tuple[str, Any], List[Tuple[int, Any]]]] = None,
                 ) -> None:
        self.head_slot = int(head_slot)
        self.produced = list(produced)
        self.blocks = dict(blocks)
        self.pre_responses = {k: list(v) for k, v in (pre_responses or {}).items()}
        self.calls: List[Tuple[str, Any]] = []

    def __call__(self, method: str, params: List[Any],
                 _timeout: float) -> Tuple[int, Optional[Dict[str, Any]]]:
        key_param = params[0] if params else None
        self.calls.append((method, key_param))
        try:
            queued = self.pre_responses.get((method, key_param))
        except TypeError:
            queued = None
        if queued:
            return queued.pop(0)
        if method == "getSlot":
            return 200, {"result": self.head_slot}
        if method == "getBlocks":
            start, end = int(params[0]), int(params[1])
            return 200, {"result": [s for s in self.produced
                                    if start <= s <= end]}
        if method == "getBlock":
            slot = int(params[0])
            block = self.blocks.get(slot)
            if block is None:
                return 200, {"error": {"code": -32007, "message": "skipped"}}
            return 200, {"result": block}
        return 200, {"error": {"code": -32601, "message": "unknown"}}


def make_config(**overrides: Any) -> rgr.RpcGapRecoveryConfig:
    base = dict(
        mode=rgr.GAP_RECOVERY_MODE_RPC_BACKFILL,
        authoritative_commitment="confirmed",
        rpc_request_spacing_seconds=0.001,
        max_commitment_wait_seconds=5.0,
        max_overlap_wait_seconds=5.0,
    )
    base.update(overrides)
    return rgr.RpcGapRecoveryConfig(**base)


def make_coordinator(state_dir, cursor, *, transport,
                     config: Optional[rgr.RpcGapRecoveryConfig] = None,
                     **kwargs: Any) -> rgr.RpcGapBackfillCoordinator:
    config = config or make_config()
    recovery_store = rgr.RpcGapRecoveryStore(state_dir=state_dir)
    recovery_store.load()
    buffer = rgr.QuarantinedLiveBuffer(
        state_dir=state_dir,
        subscription_identity_digest=IDENTITY_DIGEST,
        max_events=config.max_quarantine_events,
        max_bytes=config.max_quarantine_bytes,
        max_age_seconds=config.max_quarantine_age_seconds)
    buffer.load()
    return rgr.RpcGapBackfillCoordinator(
        config=config, recovery_store=recovery_store,
        quarantine_buffer=buffer,
        subscription_identity_digest=IDENTITY_DIGEST,
        rpc_post_fn=transport, sleep_fn=lambda _s: None, **kwargs)


def open_episode_with_target(coordinator, cursor,
                             *, target_slot: int = OVERLAP_SLOT,
                             target_sig: str = OVERLAP_SIG,
                             target_index: int = OVERLAP_TX_INDEX) -> None:
    ok, detail = coordinator.begin_or_resume_episode(
        cursor_store=cursor,
        entry_classification=rgr.ENTRY_REPLAY_REFUSED_OUT_OF_RANGE)
    assert ok, detail
    coordinator.begin_quarantine_segment()
    coordinator.note_observed_transaction(
        slot=target_slot, signature=target_sig,
        transaction_index=target_index,
        skip_identity=build_transaction_skip_identity(
            target_slot, target_sig, target_index),
        attempt_generation=int(cursor.state.attempt_generation))


PRODUCED = [100, 101, 102, 104, 105, 106, 108, 109, 110]  # 103 + 107 skipped


# ---------------------------------------------------------------------------
# configuration
# ---------------------------------------------------------------------------

class TestConfiguration:
    def test_defaults_valid_for_backfill(self) -> None:
        assert rgr.validate_rpc_gap_recovery_config(make_config()) == []

    def test_backfill_requires_explicit_commitment(self) -> None:
        config = rgr.RpcGapRecoveryConfig(
            mode=rgr.GAP_RECOVERY_MODE_RPC_BACKFILL,
            authoritative_commitment=None)
        assert rgr.CONFIG_REFUSAL_COMMITMENT_INVALID in (
            rgr.validate_rpc_gap_recovery_config(config))

    def test_processed_commitment_refused(self) -> None:
        config = rgr.RpcGapRecoveryConfig(
            mode=rgr.GAP_RECOVERY_MODE_RPC_BACKFILL,
            authoritative_commitment="processed")
        assert rgr.CONFIG_REFUSAL_COMMITMENT_INVALID in (
            rgr.validate_rpc_gap_recovery_config(config))

    @pytest.mark.parametrize("field", [
        "max_gap_slots", "max_produced_blocks", "max_transactions",
        "max_rpc_requests", "max_retries_per_request",
        "max_consecutive_rpc_failures", "max_http_429_responses",
        "max_quarantine_events", "max_quarantine_bytes",
    ])
    def test_invalid_integer_bound_refuses_not_clamps(self, field) -> None:
        config = make_config(**{field: 0})
        refusals = rgr.validate_rpc_gap_recovery_config(config)
        assert any(token.startswith(
            rgr.CONFIG_REFUSAL_BOUND_INVALID_PREFIX) for token in refusals)

    @pytest.mark.parametrize("field", [
        "max_backfill_runtime_seconds", "rpc_request_spacing_seconds",
        "max_quarantine_age_seconds", "max_commitment_wait_seconds",
        "max_overlap_wait_seconds",
    ])
    def test_invalid_number_bound_refuses(self, field) -> None:
        config = make_config(**{field: -1.0})
        refusals = rgr.validate_rpc_gap_recovery_config(config)
        assert any(token.startswith(
            rgr.CONFIG_REFUSAL_BOUND_INVALID_PREFIX) for token in refusals)

    def test_mode_invalid_refused(self) -> None:
        config = rgr.RpcGapRecoveryConfig(mode="live_head_skip")
        assert rgr.CONFIG_REFUSAL_MODE_INVALID in (
            rgr.validate_rpc_gap_recovery_config(config))

    def test_no_mode_skips_gap_to_live_head(self) -> None:
        assert "live_head" not in " ".join(rgr.GAP_RECOVERY_MODES)
        assert "skip" not in " ".join(rgr.GAP_RECOVERY_MODES)

    def test_armed_requires_explicit_mode(self) -> None:
        verdict = rgr.evaluate_armed_gap_recovery(
            require_production_grpc=True, mode_argument=None, config=None)
        assert not verdict["allowed"]
        assert rgr.CONFIG_REFUSAL_MODE_ABSENT in verdict["refusals"]

    def test_armed_backfill_requires_endpoint_presence(self) -> None:
        verdict = rgr.evaluate_armed_gap_recovery(
            require_production_grpc=True,
            mode_argument=rgr.GAP_RECOVERY_MODE_RPC_BACKFILL,
            config=make_config(), env={})
        assert rgr.CONFIG_REFUSAL_ENDPOINT_ABSENT in verdict["refusals"]

    def test_armed_backfill_allows_when_fully_configured(self) -> None:
        verdict = rgr.evaluate_armed_gap_recovery(
            require_production_grpc=True,
            mode_argument=rgr.GAP_RECOVERY_MODE_RPC_BACKFILL,
            config=make_config(),
            env={rgr.ENV_NAME_RPC_RECOVERY_ENDPOINT: "https://example"})
        assert verdict["allowed"], verdict["refusals"]

    def test_env_projection_never_echoes_values(self) -> None:
        projection = rgr.project_rpc_recovery_env_safe(
            {rgr.ENV_NAME_RPC_RECOVERY_ENDPOINT: "https://secret-host/abc"})
        assert projection == {"rpc_recovery_endpoint": "PRESENT",
                              "rpc_recovery_timeout": "DEFAULT"}


# ---------------------------------------------------------------------------
# entry classification
# ---------------------------------------------------------------------------

class TestEntryClassification:
    def test_out_of_range_is_eligible(self) -> None:
        token = rgr.classify_replay_refusal(
            replay_requested=True, replay_position_rejected=True,
            sanitized_error_category="GRPC_OUT_OF_RANGE",
            grpc_status_code="OUT_OF_RANGE")
        assert token == rgr.ENTRY_REPLAY_REFUSED_OUT_OF_RANGE

    def test_retention_precheck_is_eligible(self) -> None:
        token = rgr.classify_replay_refusal(
            replay_requested=True, replay_position_rejected=True,
            sanitized_error_category="REPLAY_RETENTION_EXCEEDED",
            grpc_status_code=None)
        assert token == rgr.ENTRY_REPLAY_RETENTION_PRECHECK

    @pytest.mark.parametrize("code,category", [
        ("INVALID_ARGUMENT", "GRPC_INVALID_ARGUMENT"),
        ("NOT_FOUND", "GRPC_NOT_FOUND"),
        ("UNAUTHENTICATED", "AUTHENTICATION_OR_PERMISSION_FAILURE"),
        ("PERMISSION_DENIED", "AUTHENTICATION_OR_PERMISSION_FAILURE"),
        ("UNAVAILABLE", "HTTP2_TRANSPORT_CLOSED"),
        ("UNKNOWN", "GRPC_UNKNOWN"),
    ])
    def test_everything_else_is_ineligible(self, code, category) -> None:
        token = rgr.classify_replay_refusal(
            replay_requested=True, replay_position_rejected=True,
            sanitized_error_category=category, grpc_status_code=code)
        assert token == rgr.ENTRY_INELIGIBLE

    def test_no_replay_requested_is_ineligible(self) -> None:
        token = rgr.classify_replay_refusal(
            replay_requested=False, replay_position_rejected=False,
            sanitized_error_category="GRPC_OUT_OF_RANGE",
            grpc_status_code="OUT_OF_RANGE")
        assert token == rgr.ENTRY_INELIGIBLE

    def test_store_refuses_ineligible_episode(self, tmp_path) -> None:
        store = rgr.RpcGapRecoveryStore(state_dir=tmp_path)
        store.load()
        with pytest.raises(ValueError):
            store.open_episode(
                entry_classification=rgr.ENTRY_INELIGIBLE,
                safe_from_slot=BOUNDARY_SLOT,
                subscription_identity_digest=IDENTITY_DIGEST,
                authoritative_commitment="confirmed",
                cursor_recovery_generation=1,
                cursor_attempt_generation=1)


# ---------------------------------------------------------------------------
# recovery episode store
# ---------------------------------------------------------------------------

class TestRecoveryStore:
    def test_safe_from_slot_is_immutable(self, tmp_path) -> None:
        store = rgr.RpcGapRecoveryStore(state_dir=tmp_path)
        store.load()
        store.open_episode(
            entry_classification=rgr.ENTRY_REPLAY_REFUSED_OUT_OF_RANGE,
            safe_from_slot=BOUNDARY_SLOT,
            subscription_identity_digest=IDENTITY_DIGEST,
            authoritative_commitment="confirmed",
            cursor_recovery_generation=1, cursor_attempt_generation=1)
        with pytest.raises(ValueError):
            store.update(safe_from_slot=BOUNDARY_SLOT + 5)
        with pytest.raises(rgr.RecoveryStoreWriteError):
            store.open_episode(
                entry_classification=rgr.ENTRY_REPLAY_REFUSED_OUT_OF_RANGE,
                safe_from_slot=BOUNDARY_SLOT + 5,
                subscription_identity_digest=IDENTITY_DIGEST,
                authoritative_commitment="confirmed",
                cursor_recovery_generation=1, cursor_attempt_generation=1)
        assert store.state.safe_from_slot == BOUNDARY_SLOT

    def test_restart_resumes_same_episode(self, tmp_path) -> None:
        first = rgr.RpcGapRecoveryStore(state_dir=tmp_path)
        first.load()
        first.open_episode(
            entry_classification=rgr.ENTRY_REPLAY_RETENTION_PRECHECK,
            safe_from_slot=BOUNDARY_SLOT,
            subscription_identity_digest=IDENTITY_DIGEST,
            authoritative_commitment="confirmed",
            cursor_recovery_generation=1, cursor_attempt_generation=2)
        first.update(recovery_target_slot=OVERLAP_SLOT,
                     last_completed_slot=104,
                     last_completed_blockhash="H104")
        second = rgr.RpcGapRecoveryStore(state_dir=tmp_path)
        second.load()
        assert second.has_resumable_episode()
        assert second.state.safe_from_slot == BOUNDARY_SLOT
        assert second.state.last_completed_slot == 104
        assert second.state.entry_classification == (
            rgr.ENTRY_REPLAY_RETENTION_PRECHECK)

    def test_terminal_requires_reason_and_reason_requires_terminal(
            self, tmp_path) -> None:
        store = rgr.RpcGapRecoveryStore(state_dir=tmp_path)
        store.load()
        store.open_episode(
            entry_classification=rgr.ENTRY_REPLAY_REFUSED_OUT_OF_RANGE,
            safe_from_slot=BOUNDARY_SLOT,
            subscription_identity_digest=IDENTITY_DIGEST,
            authoritative_commitment="confirmed",
            cursor_recovery_generation=1, cursor_attempt_generation=1)
        store.mark_terminal(reason=rgr.TERMINAL_RPC_BACKFILL_GAP_TOO_LARGE)
        reloaded = rgr.RpcGapRecoveryStore(state_dir=tmp_path)
        reloaded.load()
        assert not reloaded.quarantined
        assert reloaded.state.recovery_state == (
            rgr.RECOVERY_STATE_RECOVERY_TERMINAL)
        assert reloaded.state.terminal_reason == (
            rgr.TERMINAL_RPC_BACKFILL_GAP_TOO_LARGE)

    def test_corrupted_recovery_checkpoint_quarantines(self, tmp_path) -> None:
        store = rgr.RpcGapRecoveryStore(state_dir=tmp_path)
        store.load()
        store.open_episode(
            entry_classification=rgr.ENTRY_REPLAY_REFUSED_OUT_OF_RANGE,
            safe_from_slot=BOUNDARY_SLOT,
            subscription_identity_digest=IDENTITY_DIGEST,
            authoritative_commitment="confirmed",
            cursor_recovery_generation=1, cursor_attempt_generation=1)
        primary = store.primary_path
        primary.write_text(
            primary.read_text(encoding="utf-8").replace(
                str(BOUNDARY_SLOT), str(BOUNDARY_SLOT + 7), 1),
            encoding="utf-8")
        backup = primary.with_name(primary.name + ".bak")
        if backup.exists():
            backup.write_text(backup.read_text(
                encoding="utf-8")[:-2], encoding="utf-8")
        reloaded = rgr.RpcGapRecoveryStore(state_dir=tmp_path)
        reloaded.load()
        assert reloaded.quarantined
        with pytest.raises(rgr.RecoveryStoreWriteError):
            reloaded.update(recovery_target_slot=OVERLAP_SLOT)


# ---------------------------------------------------------------------------
# quarantine buffer
# ---------------------------------------------------------------------------

def _buffer(tmp_path, *, max_events: int = 8, max_bytes: int = 1 << 20,
            max_age: float = 3600.0) -> rgr.QuarantinedLiveBuffer:
    buffer = rgr.QuarantinedLiveBuffer(
        state_dir=tmp_path, subscription_identity_digest=IDENTITY_DIGEST,
        max_events=max_events, max_bytes=max_bytes, max_age_seconds=max_age)
    buffer.load()
    buffer.bind_episode(1)
    return buffer


def _entry(slot: int, signature: str, index: int = 0, *,
           kind: str = rgr.BUFFER_EVENT_TRANSACTION_OBSERVED,
           candidate: Optional[Dict[str, Any]] = None,
           segment: int = 1) -> Dict[str, Any]:
    return {
        "event_kind": kind,
        "slot": slot,
        "signature": signature,
        "transaction_index": index,
        "skip_identity": build_transaction_skip_identity(
            slot, signature, index),
        "candidate": candidate,
        "attempt_generation": 2,
        "segment": segment,
    }


class TestQuarantineBuffer:
    def test_survives_restart_authenticated(self, tmp_path) -> None:
        buffer = _buffer(tmp_path)
        buffer.append(_entry(OVERLAP_SLOT, OVERLAP_SIG, OVERLAP_TX_INDEX))
        reloaded = rgr.QuarantinedLiveBuffer(
            state_dir=tmp_path, subscription_identity_digest=IDENTITY_DIGEST,
            max_events=8, max_bytes=1 << 20, max_age_seconds=3600.0)
        reloaded.load()
        assert reloaded.depth() == 1
        assert reloaded.identity_matches
        entries = reloaded.ordered_entries()
        assert entries[0]["signature"] == OVERLAP_SIG

    def test_event_count_bound_never_silently_drops(self, tmp_path) -> None:
        buffer = _buffer(tmp_path, max_events=2)
        buffer.append(_entry(110, "S1gA", 0))
        buffer.append(_entry(111, "S1gB", 0))
        with pytest.raises(rgr.QuarantineBufferCapacityExceeded):
            buffer.append(_entry(112, "S1gC", 0))
        assert buffer.depth() == 2  # nothing dropped, nothing added

    def test_byte_bound_enforced(self, tmp_path) -> None:
        buffer = _buffer(tmp_path, max_bytes=400)
        with pytest.raises(rgr.QuarantineBufferCapacityExceeded):
            buffer.append(_entry(
                110, "S1gA", 0, kind=rgr.BUFFER_EVENT_MIGRATION_ADMITTED,
                candidate={"token_mint": "m" * 300 + "pump"}))

    def test_stale_generation_entries_rejected_on_rebind(self, tmp_path) -> None:
        buffer = _buffer(tmp_path)
        buffer.append(_entry(110, "S1gA", 0))
        buffer.bind_episode(2)
        assert buffer.depth() == 0

    def test_corruption_fail_closed(self, tmp_path) -> None:
        buffer = _buffer(tmp_path)
        buffer.append(_entry(110, "S1gA", 0))
        primary = buffer.primary_path
        primary.write_text(primary.read_text(
            encoding="utf-8").replace("S1gA", "S1gB"), encoding="utf-8")
        backup = primary.with_name(primary.name + ".bak")
        if backup.exists():
            backup.unlink()
        reloaded = rgr.QuarantinedLiveBuffer(
            state_dir=tmp_path, subscription_identity_digest=IDENTITY_DIGEST,
            max_events=8, max_bytes=1 << 20, max_age_seconds=3600.0)
        reloaded.load()
        assert reloaded.quarantined
        with pytest.raises(rgr.RecoveryStoreWriteError):
            reloaded.append(_entry(111, "S1gC", 0))

    def test_ordered_entries_deterministic(self, tmp_path) -> None:
        buffer = _buffer(tmp_path)
        buffer.append(_entry(112, "S1gLate", 1))
        buffer.append(_entry(110, "S1gEarly", 0))
        buffer.append(_entry(112, "S1gEarlier", 0))
        slots = [(e["slot"], e["transaction_index"])
                 for e in buffer.ordered_entries()]
        assert slots == [(110, 0), (112, 0), (112, 1)]


# ---------------------------------------------------------------------------
# RPC adapter bounds
# ---------------------------------------------------------------------------

class _ScriptTransport:
    def __init__(self, responses: List[Tuple[int, Any]]) -> None:
        self.responses = list(responses)
        self.calls = 0

    def __call__(self, _method: str, _params: List[Any],
                 _timeout: float) -> Tuple[int, Optional[Dict[str, Any]]]:
        self.calls += 1
        if self.responses:
            return self.responses.pop(0)
        return self.last_response()

    def last_response(self) -> Tuple[int, Optional[Dict[str, Any]]]:
        return 200, {"result": 1}


class TestRpcAdapterBounds:
    def _adapter(self, transport, **overrides) -> rgr.SolanaRpcBackfillAdapter:
        return rgr.SolanaRpcBackfillAdapter(
            rpc_post_fn=transport, config=make_config(**overrides),
            sleep_fn=lambda _s: None)

    def test_request_budget_enforced(self) -> None:
        adapter = self._adapter(
            _ScriptTransport([]), max_rpc_requests=2)
        adapter.get_slot(commitment="confirmed")
        adapter.get_slot(commitment="confirmed")
        with pytest.raises(rgr.RpcBackfillBoundExceeded) as excinfo:
            adapter.get_slot(commitment="confirmed")
        assert excinfo.value.reason == (
            rgr.TERMINAL_RPC_BACKFILL_REQUEST_LIMIT_EXCEEDED)

    def test_429_threshold_is_rate_limited(self) -> None:
        transport = _ScriptTransport([(429, None)] * 10)
        adapter = self._adapter(
            transport, max_http_429_responses=2, max_retries_per_request=8)
        with pytest.raises(rgr.RpcBackfillBoundExceeded) as excinfo:
            adapter.get_slot(commitment="confirmed")
        assert excinfo.value.reason == rgr.TERMINAL_RPC_BACKFILL_RATE_LIMITED
        assert adapter.http_429_count == 3

    def test_persistent_timeout_is_timeout(self) -> None:
        transport = _ScriptTransport([(0, None)] * 10)
        adapter = self._adapter(transport, max_retries_per_request=2)
        with pytest.raises(rgr.RpcBackfillBoundExceeded) as excinfo:
            adapter.get_slot(commitment="confirmed")
        assert excinfo.value.reason == rgr.TERMINAL_RPC_BACKFILL_TIMEOUT
        assert adapter.timeout_count == 3

    def test_malformed_response_terminal(self) -> None:
        transport = _ScriptTransport([(200, {"unexpected": True})] * 10)
        adapter = self._adapter(transport, max_retries_per_request=2)
        with pytest.raises(rgr.RpcBackfillBoundExceeded) as excinfo:
            adapter.get_slot(commitment="confirmed")
        assert excinfo.value.reason == (
            rgr.TERMINAL_RPC_BACKFILL_MALFORMED_RESPONSE)

    def test_block_slot_mismatch_fails_closed(self) -> None:
        bad_block = make_block(105, 106, "H105", "H104", [])
        transport = _ScriptTransport([(200, {"result": bad_block})])
        adapter = self._adapter(transport)
        with pytest.raises(rgr.RpcBackfillBoundExceeded) as excinfo:
            adapter.get_block(slot=105, commitment="confirmed")
        assert excinfo.value.reason == (
            rgr.TERMINAL_RPC_BACKFILL_MALFORMED_RESPONSE)

    def test_temporarily_unavailable_block_retries_then_succeeds(self) -> None:
        good = make_block(105, 104, "H105", "H104", [])
        transport = _ScriptTransport([
            (200, {"error": {"code": -32004, "message": "not yet"}}),
            (200, {"result": good}),
        ])
        adapter = self._adapter(transport)
        block = adapter.get_block(slot=105, commitment="confirmed")
        assert block["blockhash"] == "H105"
        assert adapter.retry_count == 1

    def test_block_unavailable_after_retry_budget(self) -> None:
        transport = _ScriptTransport(
            [(200, {"error": {"code": -32004, "message": "not yet"}})] * 10)
        adapter = self._adapter(transport, max_retries_per_request=2)
        with pytest.raises(rgr.RpcBackfillBoundExceeded) as excinfo:
            adapter.get_block(slot=105, commitment="confirmed")
        assert excinfo.value.reason == (
            rgr.TERMINAL_RPC_BACKFILL_BLOCK_UNAVAILABLE)

    def test_get_blocks_out_of_range_values_malformed(self) -> None:
        transport = _ScriptTransport([(200, {"result": [100, 250]})])
        adapter = self._adapter(transport)
        with pytest.raises(rgr.RpcBackfillBoundExceeded) as excinfo:
            adapter.get_blocks(
                start_slot=100, end_slot=110, commitment="confirmed")
        assert excinfo.value.reason == (
            rgr.TERMINAL_RPC_BACKFILL_MALFORMED_RESPONSE)


# ---------------------------------------------------------------------------
# RPC -> geyser bridge
# ---------------------------------------------------------------------------

class TestBridge:
    def test_bridge_produces_matching_skip_identity(self) -> None:
        update = rgr.build_subscribe_update_from_rpc_transaction(
            slot=OVERLAP_SLOT, block_time=BLOCK_TIME,
            transaction_index=OVERLAP_TX_INDEX,
            tx_json=make_tx(OVERLAP_SIG))
        assert update is not None
        from PHX2.free_tier_producer.paid_grpc_source import (
            extract_stream_position,
        )
        position = extract_stream_position(update)
        assert position is not None
        slot, signature, index = position
        assert (slot, signature, index) == (
            OVERLAP_SLOT, OVERLAP_SIG, OVERLAP_TX_INDEX)
        assert build_transaction_skip_identity(slot, signature, index) == (
            build_transaction_skip_identity(
                OVERLAP_SLOT, OVERLAP_SIG, OVERLAP_TX_INDEX))

    def test_bridge_refuses_failed_transactions(self) -> None:
        update = rgr.build_subscribe_update_from_rpc_transaction(
            slot=OVERLAP_SLOT, block_time=BLOCK_TIME, transaction_index=0,
            tx_json=make_tx(OVERLAP_SIG, failed=True))
        assert update is None

    def test_bridge_is_canonical_success_for_execution_status(self) -> None:
        from PHX2.free_tier_producer.migration_admission import (
            TransactionExecutionStatus,
            classify_transaction_execution_status,
        )
        update = rgr.build_subscribe_update_from_rpc_transaction(
            slot=OVERLAP_SLOT, block_time=BLOCK_TIME, transaction_index=0,
            tx_json=make_tx(OVERLAP_SIG))
        assert update is not None
        status = classify_transaction_execution_status(
            update.transaction.transaction.meta)
        assert status is TransactionExecutionStatus.SUCCESS

    def test_bridge_carries_stack_height_and_token_balances(self) -> None:
        tx = make_tx(OVERLAP_SIG)
        tx["meta"]["innerInstructions"] = [{
            "index": 0,
            "instructions": [{"programIdIndex": 1, "accounts": [0],
                              "data": "1", "stackHeight": 2}],
        }]
        tx["meta"]["preTokenBalances"] = [{
            "accountIndex": 1, "mint": "M1ntAAAApump",
            "owner": "canonical-pool-owner",
            "programId": "token-program",
            "uiTokenAmount": {
                "amount": "123456789", "decimals": 6,
                "uiAmount": 123.456789,
                "uiAmountString": "123.456789",
            },
        }]
        update = rgr.build_subscribe_update_from_rpc_transaction(
            slot=OVERLAP_SLOT, block_time=BLOCK_TIME, transaction_index=0,
            tx_json=tx)
        assert update is not None
        meta = update.transaction.transaction.meta
        assert meta.inner_instructions[0].instructions[0].stack_height == 2
        balance = meta.pre_token_balances[0]
        assert balance.mint == "M1ntAAAApump"
        assert balance.owner == "canonical-pool-owner"
        assert balance.program_id == "token-program"
        assert balance.ui_token_amount.amount == "123456789"
        assert balance.ui_token_amount.decimals == 6
        assert balance.ui_token_amount.ui_amount_string == "123.456789"

    def test_relevance_predicate_matches_subscription_filter(self) -> None:
        assert rgr.rpc_transaction_mentions_program(
            make_tx("S1gA"), PUMPSWAP_PROGRAM_ID)
        assert not rgr.rpc_transaction_mentions_program(
            make_tx("S1gA", relevant=False), PUMPSWAP_PROGRAM_ID)


# ---------------------------------------------------------------------------
# the ONE terminal-resolution transition
# ---------------------------------------------------------------------------

class TestCursorTerminalResolution:
    def _proof_kwargs(self, cursor, **overrides: Any) -> Dict[str, Any]:
        kwargs = dict(
            safe_from_slot=BOUNDARY_SLOT,
            proven_target_slot=OVERLAP_SLOT,
            overlap_identity=build_transaction_skip_identity(
                OVERLAP_SLOT, OVERLAP_SIG, OVERLAP_TX_INDEX),
            recovery_generation=int(cursor.state.recovery_generation),
            subscription_identity_digest=IDENTITY_DIGEST,
        )
        kwargs.update(overrides)
        return kwargs

    def test_binding_proof_resolves_atomically(self, tmp_path) -> None:
        cursor = make_terminal_cursor(tmp_path)
        assert cursor.resolve_terminal_retention_with_backfill_proof(
            **self._proof_kwargs(cursor))
        assert not cursor.is_terminal()
        assert cursor.state.recovery_status == sc.RECOVERY_CLOSED
        assert cursor.state.recovery_required is False
        assert cursor.resume_decision().action == (
            sc.RESUME_ACTION_SUBSCRIBE_FROM_SLOT)
        reloaded = sc.build_cursor_store(
            state_dir=tmp_path, subscription_identity_digest=IDENTITY_DIGEST)
        load = reloaded.load()
        assert not load.checkpoint_quarantined
        assert not reloaded.is_terminal()

    def test_wrong_generation_refused(self, tmp_path) -> None:
        cursor = make_terminal_cursor(tmp_path)
        assert not cursor.resolve_terminal_retention_with_backfill_proof(
            **self._proof_kwargs(
                cursor,
                recovery_generation=cursor.state.recovery_generation + 1))
        assert cursor.is_terminal()

    def test_wrong_subscription_identity_refused(self, tmp_path) -> None:
        cursor = make_terminal_cursor(tmp_path)
        assert not cursor.resolve_terminal_retention_with_backfill_proof(
            **self._proof_kwargs(
                cursor, subscription_identity_digest="ab" * 32))
        assert cursor.is_terminal()

    def test_wrong_boundary_refused(self, tmp_path) -> None:
        cursor = make_terminal_cursor(tmp_path)
        assert not cursor.resolve_terminal_retention_with_backfill_proof(
            **self._proof_kwargs(cursor, safe_from_slot=BOUNDARY_SLOT + 1))
        assert cursor.is_terminal()

    def test_identity_slot_must_be_target(self, tmp_path) -> None:
        cursor = make_terminal_cursor(tmp_path)
        assert not cursor.resolve_terminal_retention_with_backfill_proof(
            **self._proof_kwargs(
                cursor,
                overlap_identity=build_transaction_skip_identity(
                    OVERLAP_SLOT + 1, OVERLAP_SIG, OVERLAP_TX_INDEX)))
        assert cursor.is_terminal()

    def test_non_retention_terminal_never_resolvable(self, tmp_path) -> None:
        cursor = sc.build_cursor_store(
            state_dir=tmp_path, subscription_identity_digest=IDENTITY_DIGEST)
        cursor.load()
        identity = sc.build_stream_event_identity(
            slot=BOUNDARY_SLOT, signature=BOUNDARY_SIG, transaction_index=0)
        cursor.commit_event(slot=BOUNDARY_SLOT, identity=identity,
                            signature=BOUNDARY_SIG)
        cursor.mark_disconnect()
        cursor.begin_stream_attempt(requested_from_slot=BOUNDARY_SLOT)
        cursor.mark_replay_retention_exceeded(
            reason=sc.REASON_SUBSCRIPTION_IDENTITY_MISMATCH)
        assert not cursor.resolve_terminal_retention_with_backfill_proof(
            **self._proof_kwargs(cursor))
        assert cursor.is_terminal()

    def test_quarantined_cursor_never_resolvable(self, tmp_path) -> None:
        cursor = make_terminal_cursor(tmp_path)
        cursor._quarantined = True  # simulate envelope quarantine lockdown
        assert not cursor.resolve_terminal_retention_with_backfill_proof(
            **self._proof_kwargs(cursor))


# ---------------------------------------------------------------------------
# coordinator scenario matrix (fake transports; no live stream needed)
# ---------------------------------------------------------------------------

class TestCoordinatorScenarios:
    def test_exact_overlap_succeeds_and_resolves_cursor(self, tmp_path) -> None:
        cursor = make_terminal_cursor(tmp_path)
        transport = FakeRpcTransport(
            head_slot=200, produced=PRODUCED, blocks=build_chain(PRODUCED))
        coordinator = make_coordinator(tmp_path, cursor, transport=transport)
        open_episode_with_target(coordinator, cursor)
        applied: List[Dict[str, Any]] = []
        assert coordinator.run_backfill(
            apply_candidate_fn=lambda c: applied.append(c) or True)
        assert coordinator.is_proven()
        assert not cursor.is_terminal()
        snapshot = coordinator.snapshot()
        assert snapshot["recovery_state"] == (
            rgr.RECOVERY_STATE_RECOVERY_PROVEN)
        assert snapshot["overlap_proof_state"] == rgr.OVERLAP_PROVEN
        assert snapshot["skipped_slots_total"] == 2       # 103 + 107
        assert snapshot["produced_blocks_completed"] == len(PRODUCED)
        assert snapshot["overlap_slot"] == OVERLAP_SLOT

    def test_gap_exactly_at_maximum_proceeds(self, tmp_path) -> None:
        cursor = make_terminal_cursor(tmp_path)
        transport = FakeRpcTransport(
            head_slot=200, produced=PRODUCED, blocks=build_chain(PRODUCED))
        coordinator = make_coordinator(
            tmp_path, cursor, transport=transport,
            config=make_config(max_gap_slots=OVERLAP_SLOT - BOUNDARY_SLOT))
        open_episode_with_target(coordinator, cursor)
        assert coordinator.run_backfill()

    def test_gap_above_chunk_maximum_completes_in_multiple_chunks(self, tmp_path) -> None:
        cursor = make_terminal_cursor(tmp_path)
        transport = FakeRpcTransport(
            head_slot=200, produced=PRODUCED, blocks=build_chain(PRODUCED))
        coordinator = make_coordinator(
            tmp_path, cursor, transport=transport,
            config=make_config(
                max_gap_slots=OVERLAP_SLOT - BOUNDARY_SLOT - 1))
        open_episode_with_target(coordinator, cursor)
        assert coordinator.run_backfill()
        assert sum(1 for method, _ in transport.calls
                   if method == "getBlocks") == 2
        assert not cursor.is_terminal()

    def test_empty_blocks_complete(self, tmp_path) -> None:
        cursor = make_terminal_cursor(tmp_path)
        blocks = build_chain(PRODUCED)
        for slot in (101, 105):
            blocks[slot]["transactions"] = []
        transport = FakeRpcTransport(
            head_slot=200, produced=PRODUCED, blocks=blocks)
        coordinator = make_coordinator(tmp_path, cursor, transport=transport)
        open_episode_with_target(coordinator, cursor)
        assert coordinator.run_backfill()

    def test_commitment_timeout(self, tmp_path) -> None:
        cursor = make_terminal_cursor(tmp_path)
        transport = FakeRpcTransport(
            head_slot=OVERLAP_SLOT - 1, produced=PRODUCED,
            blocks=build_chain(PRODUCED))
        clock = {"now": 0.0}

        def _monotonic() -> float:
            clock["now"] += 0.5
            return clock["now"]

        coordinator = make_coordinator(
            tmp_path, cursor, transport=transport,
            config=make_config(max_commitment_wait_seconds=3.0),
            monotonic_fn=_monotonic)
        open_episode_with_target(coordinator, cursor)
        assert not coordinator.run_backfill()
        assert coordinator.terminal_reason() == (
            rgr.TERMINAL_RPC_BACKFILL_COMMITMENT_TIMEOUT)

    def test_no_overlap_event_appears(self, tmp_path) -> None:
        cursor = make_terminal_cursor(tmp_path)
        transport = FakeRpcTransport(
            head_slot=200, produced=PRODUCED, blocks=build_chain(PRODUCED))
        clock = {"now": 0.0}

        def _monotonic() -> float:
            clock["now"] += 0.5
            return clock["now"]

        coordinator = make_coordinator(
            tmp_path, cursor, transport=transport,
            config=make_config(max_overlap_wait_seconds=2.0),
            monotonic_fn=_monotonic)
        ok, _ = coordinator.begin_or_resume_episode(
            cursor_store=cursor,
            entry_classification=rgr.ENTRY_REPLAY_REFUSED_OUT_OF_RANGE)
        assert ok
        # No quarantined event is ever observed: no target appears.
        assert not coordinator.run_backfill()
        assert coordinator.terminal_reason() == (
            rgr.TERMINAL_RECOVERY_OVERLAP_NOT_PROVEN)

    def test_overlap_slot_produced_but_signature_absent_is_fork(
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

    def test_signature_matches_but_instruction_identity_differs(
            self, tmp_path) -> None:
        cursor = make_terminal_cursor(tmp_path)
        blocks = build_chain(PRODUCED, overlap_index=5)  # index 5, not 3
        transport = FakeRpcTransport(
            head_slot=200, produced=PRODUCED, blocks=blocks)
        coordinator = make_coordinator(tmp_path, cursor, transport=transport)
        open_episode_with_target(coordinator, cursor)
        assert not coordinator.run_backfill()
        assert coordinator.terminal_reason() == (
            rgr.TERMINAL_RECOVERY_OVERLAP_NOT_PROVEN)
        assert cursor.is_terminal()

    def test_buffered_slot_proven_skipped_is_fork(self, tmp_path) -> None:
        cursor = make_terminal_cursor(tmp_path)
        produced = [s for s in PRODUCED if s != OVERLAP_SLOT]
        transport = FakeRpcTransport(
            head_slot=200, produced=produced,
            blocks=build_chain(produced, overlap_slot=None))
        coordinator = make_coordinator(tmp_path, cursor, transport=transport)
        open_episode_with_target(coordinator, cursor)
        assert not coordinator.run_backfill()
        assert coordinator.terminal_reason() == (
            rgr.TERMINAL_RPC_BACKFILL_FORK_INCONSISTENT)

    def test_parent_blockhash_inconsistency_is_fork(self, tmp_path) -> None:
        cursor = make_terminal_cursor(tmp_path)
        blocks = build_chain(PRODUCED)
        blocks[106]["previousBlockhash"] = "Hforked"
        transport = FakeRpcTransport(
            head_slot=200, produced=PRODUCED, blocks=blocks)
        coordinator = make_coordinator(tmp_path, cursor, transport=transport)
        open_episode_with_target(coordinator, cursor)
        assert not coordinator.run_backfill()
        assert coordinator.terminal_reason() == (
            rgr.TERMINAL_RPC_BACKFILL_FORK_INCONSISTENT)

    def test_transaction_limit_enforced(self, tmp_path) -> None:
        cursor = make_terminal_cursor(tmp_path)
        blocks = build_chain(PRODUCED)
        blocks[101]["transactions"] = [
            make_tx(f"S1gBulk{i}", relevant=False) for i in range(5)]
        transport = FakeRpcTransport(
            head_slot=200, produced=PRODUCED, blocks=blocks)
        coordinator = make_coordinator(
            tmp_path, cursor, transport=transport,
            config=make_config(max_transactions=3))
        open_episode_with_target(coordinator, cursor)
        assert not coordinator.run_backfill()
        assert coordinator.terminal_reason() == (
            rgr.TERMINAL_RPC_BACKFILL_TRANSACTION_LIMIT_EXCEEDED)

    def test_block_limit_is_enforced_per_chunk(self, tmp_path) -> None:
        cursor = make_terminal_cursor(tmp_path)
        transport = FakeRpcTransport(
            head_slot=200, produced=PRODUCED, blocks=build_chain(PRODUCED))
        coordinator = make_coordinator(
            tmp_path, cursor, transport=transport,
            config=make_config(max_produced_blocks=3))
        open_episode_with_target(coordinator, cursor)
        assert coordinator.run_backfill()
        assert sum(1 for method, _ in transport.calls
                   if method == "getBlocks") == 4

    def test_transport_absent_is_terminal_not_live_head(self, tmp_path) -> None:
        cursor = make_terminal_cursor(tmp_path)
        coordinator = make_coordinator(tmp_path, cursor, transport=None)
        open_episode_with_target(coordinator, cursor)
        assert not coordinator.run_backfill()
        assert coordinator.terminal_reason() == (
            rgr.TERMINAL_RPC_BACKFILL_TRANSPORT_ABSENT)
        assert cursor.resume_decision().action == (
            sc.RESUME_ACTION_REFUSE_TERMINAL)

    def test_wrong_cursor_generation_refuses_resume(self, tmp_path) -> None:
        cursor = make_terminal_cursor(tmp_path)
        transport = FakeRpcTransport(
            head_slot=200, produced=PRODUCED, blocks=build_chain(PRODUCED))
        coordinator = make_coordinator(tmp_path, cursor, transport=transport)
        open_episode_with_target(coordinator, cursor)
        # A NEW cursor generation (fresh state dir) invalidates the episode.
        other_dir = tmp_path / "other_cursor"
        other_dir.mkdir()
        foreign_cursor = make_terminal_cursor(other_dir)
        foreign_cursor.state.recovery_generation += 3
        fresh = make_coordinator(tmp_path, cursor, transport=transport)
        ok, detail = fresh.begin_or_resume_episode(
            cursor_store=foreign_cursor)
        assert not ok
        assert detail == rgr.TERMINAL_RECOVERY_STATE_QUARANTINED

    def test_duplicate_overlap_applies_once(self, tmp_path) -> None:
        cursor = make_terminal_cursor(tmp_path)
        transport = FakeRpcTransport(
            head_slot=200, produced=PRODUCED, blocks=build_chain(PRODUCED))
        coordinator = make_coordinator(tmp_path, cursor, transport=transport)
        open_episode_with_target(coordinator, cursor)
        assert coordinator.run_backfill()
        overlap_identity = build_transaction_skip_identity(
            OVERLAP_SLOT, OVERLAP_SIG, OVERLAP_TX_INDEX)
        assert cursor.is_duplicate(overlap_identity)
        # A second full pass over the same blocks applies nothing twice: the
        # proven episode simply reports success without re-running.
        assert coordinator.run_backfill()
        assert coordinator.snapshot()["transactions_relevant"] == 1

    def test_crash_between_blocks_resumes_authenticated_progress(
            self, tmp_path) -> None:
        cursor = make_terminal_cursor(tmp_path)
        blocks = build_chain(PRODUCED)

        class _CrashTransport(FakeRpcTransport):
            def __call__(self, method, params, timeout):
                if method == "getBlock" and int(params[0]) == 105:
                    raise KeyboardInterrupt("simulated process crash")
                return super().__call__(method, params, timeout)

        crashing = _CrashTransport(
            head_slot=200, produced=PRODUCED, blocks=blocks)
        coordinator = make_coordinator(tmp_path, cursor, transport=crashing)
        open_episode_with_target(coordinator, cursor)
        with pytest.raises(KeyboardInterrupt):
            coordinator.run_backfill()
        # Fresh process: fresh stores from the same directory.
        cursor2 = sc.build_cursor_store(
            state_dir=tmp_path, subscription_identity_digest=IDENTITY_DIGEST)
        cursor2.load()
        assert cursor2.is_terminal()
        transport2 = FakeRpcTransport(
            head_slot=200, produced=PRODUCED, blocks=blocks)
        coordinator2 = make_coordinator(tmp_path, cursor2, transport=transport2)
        ok, _ = coordinator2.begin_or_resume_episode(cursor_store=cursor2)
        assert ok
        assert coordinator2._store.state.last_completed_slot == 104
        assert coordinator2.run_backfill()
        fetched = [p for (m, p) in transport2.calls if m == "getBlock"]
        assert 104 not in fetched and 100 not in fetched
        assert not cursor2.is_terminal()

    def test_crash_before_first_block_resumes_full_range(self, tmp_path) -> None:
        cursor = make_terminal_cursor(tmp_path)

        class _EarlyCrash(FakeRpcTransport):
            def __call__(self, method, params, timeout):
                if method == "getBlocks":
                    raise KeyboardInterrupt("simulated crash before coverage")
                return super().__call__(method, params, timeout)

        coordinator = make_coordinator(
            tmp_path, cursor,
            transport=_EarlyCrash(head_slot=200, produced=PRODUCED,
                                  blocks=build_chain(PRODUCED)))
        open_episode_with_target(coordinator, cursor)
        with pytest.raises(KeyboardInterrupt):
            coordinator.run_backfill()
        cursor2 = sc.build_cursor_store(
            state_dir=tmp_path, subscription_identity_digest=IDENTITY_DIGEST)
        cursor2.load()
        transport2 = FakeRpcTransport(
            head_slot=200, produced=PRODUCED, blocks=build_chain(PRODUCED))
        coordinator2 = make_coordinator(tmp_path, cursor2, transport=transport2)
        ok, _ = coordinator2.begin_or_resume_episode(cursor_store=cursor2)
        assert ok
        assert coordinator2._store.state.last_completed_slot is None
        assert coordinator2.run_backfill()

    def test_crash_during_block_replays_block_under_dedupe(
            self, tmp_path) -> None:
        cursor = make_terminal_cursor(tmp_path)
        blocks = build_chain(PRODUCED)
        blocks[105]["transactions"] = [make_tx("S1gRepayAAA", relevant=True)]

        class _MidBlockCrash(FakeRpcTransport):
            def __init__(self, **kwargs):
                super().__init__(**kwargs)
                self.served_105 = False

            def __call__(self, method, params, timeout):
                if method == "getBlock" and int(params[0]) == 106 \
                        and not self.served_105:
                    self.served_105 = True
                    raise KeyboardInterrupt(
                        "crash after 105 processed, before completion of 106")
                return super().__call__(method, params, timeout)

        coordinator = make_coordinator(
            tmp_path, cursor,
            transport=_MidBlockCrash(head_slot=200, produced=PRODUCED,
                                     blocks=blocks))
        open_episode_with_target(coordinator, cursor)
        with pytest.raises(KeyboardInterrupt):
            coordinator.run_backfill()
        cursor2 = sc.build_cursor_store(
            state_dir=tmp_path, subscription_identity_digest=IDENTITY_DIGEST)
        cursor2.load()
        replay_identity = build_transaction_skip_identity(
            105, "S1gRepayAAA", 0)
        assert cursor2.is_duplicate(replay_identity)
        transport2 = FakeRpcTransport(
            head_slot=200, produced=PRODUCED, blocks=blocks)
        coordinator2 = make_coordinator(tmp_path, cursor2, transport=transport2)
        ok, _ = coordinator2.begin_or_resume_episode(cursor_store=cursor2)
        assert ok
        assert coordinator2.run_backfill()
        # Block 105 completed before the crash, so it is never re-fetched and
        # its relevant transaction cannot re-apply.
        fetched = [p for (m, p) in transport2.calls if m == "getBlock"]
        assert 105 not in fetched
        assert coordinator2.snapshot()["duplicate_events_suppressed"] == 0

    def test_stop_request_pauses_without_terminal(self, tmp_path) -> None:
        cursor = make_terminal_cursor(tmp_path)
        transport = FakeRpcTransport(
            head_slot=200, produced=PRODUCED, blocks=build_chain(PRODUCED))
        coordinator = make_coordinator(tmp_path, cursor, transport=transport)
        open_episode_with_target(coordinator, cursor)
        coordinator.request_stop()
        assert not coordinator.run_backfill()
        assert not coordinator.is_terminal()
        assert coordinator.has_resumable_episode()


# ---------------------------------------------------------------------------
# runtime lock
# ---------------------------------------------------------------------------

class TestRuntimeLock:
    def test_acquire_release_and_reentry(self, tmp_path) -> None:
        lock = rgr.StateDirRuntimeLock(tmp_path)
        assert lock.acquire()
        assert not lock.held_by_live_other_process()
        again = rgr.StateDirRuntimeLock(tmp_path)
        assert again.acquire()  # same pid: re-entrant
        lock.release()

    def test_foreign_live_pid_refuses(self, tmp_path) -> None:
        lock = rgr.StateDirRuntimeLock(tmp_path)
        lock.path.write_text("999999999|2026-07-22T00:00:00Z",
                             encoding="utf-8")
        # A dead pid is reclaimed; fabricate liveness to prove the refusal.
        original = rgr.StateDirRuntimeLock._pid_alive
        try:
            rgr.StateDirRuntimeLock._pid_alive = staticmethod(
                lambda _pid: True)
            assert lock.held_by_live_other_process()
            assert not lock.acquire()
        finally:
            rgr.StateDirRuntimeLock._pid_alive = original

    def test_stale_lock_reclaimed(self, tmp_path) -> None:
        lock = rgr.StateDirRuntimeLock(tmp_path)
        lock.path.write_text("999999999|2026-07-22T00:00:00Z",
                             encoding="utf-8")
        original = rgr.StateDirRuntimeLock._pid_alive
        try:
            rgr.StateDirRuntimeLock._pid_alive = staticmethod(
                lambda _pid: False)
            assert lock.acquire()
        finally:
            rgr.StateDirRuntimeLock._pid_alive = original


# ---------------------------------------------------------------------------
# static safety: the recovery module owns no ledger, transport or send path
# ---------------------------------------------------------------------------

def test_recovery_module_touches_no_ledger_or_transport() -> None:
    import inspect as _inspect

    source = _inspect.getsource(rgr)
    for needle in ("ping_dedupe", "webhook", "telegram", "discord",
                   "delivery_transaction", "free_tier_no_send_transport"):
        assert needle not in source.lower(), needle


# ---------------------------------------------------------------------------
# RPC transport User-Agent regression (2026-07-22, classification RPC_HEADER_DEFECT).
#
# build_rpc_transport_from_env previously set ONLY Content-Type, so urllib
# attached its default ``Python-urllib/<version>`` User-Agent, which the
# provider's HTTP front door rejected with HTTP 403 (a byte-identical request
# that differed only in this header returned 200 with a valid result).  These
# offline tests pin the corrected request shape and prove the fix did not weaken
# any other part of the request or the fail-closed contract.  No socket is
# opened: urllib.request.urlopen is mocked with a capturing fake.
# ---------------------------------------------------------------------------

class _FakeHttpResponse:
    """Minimal context-manager stand-in for a urllib HTTP response."""

    def __init__(self, body: bytes, status: int = 200) -> None:
        self._body = body
        self.status = status

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> "_FakeHttpResponse":
        return self

    def __exit__(self, *_exc: Any) -> bool:
        return False


def _capturing_urlopen(captured: Dict[str, Any],
                       body: bytes = b'{"jsonrpc":"2.0","id":1,"result":123456}',
                       status: int = 200):
    def _fake(request, timeout=None):
        captured["request"] = request
        captured["timeout"] = timeout
        return _FakeHttpResponse(body, status)
    return _fake


def _transport_for(monkeypatch, endpoint: str, captured: Dict[str, Any],
                   **kw):
    import urllib.request
    monkeypatch.setattr(urllib.request, "urlopen",
                        _capturing_urlopen(captured, **kw))
    transport = rgr.build_rpc_transport_from_env(
        env={rgr.ENV_NAME_RPC_RECOVERY_ENDPOINT: endpoint})
    assert transport is not None
    return transport


def test_rpc_transport_sets_explicit_non_urllib_user_agent(monkeypatch) -> None:
    import json as _json
    from urllib.parse import urlsplit

    endpoint = "https://rpc.example.invalid/tok_0123456789abcdef0123456789ab"
    captured: Dict[str, Any] = {}
    transport = _transport_for(monkeypatch, endpoint, captured)

    status, parsed = transport("getSlot", [{"commitment": "confirmed"}], 5.0)
    assert status == 200
    assert isinstance(parsed, dict) and "result" in parsed

    req = captured["request"]
    # method / content-type
    assert req.get_method() == "POST"
    assert req.get_header("Content-type") == "application/json"
    # explicit User-Agent, equal to the shipped constant, and NOT python-urllib
    ua = req.get_header("User-agent")
    assert ua == rgr.RPC_RECOVERY_USER_AGENT
    assert ua and not ua.lower().startswith("python-urllib")
    # tokenized HTTPS path preserved exactly
    assert req.get_full_url() == endpoint
    assert urlsplit(req.get_full_url()).scheme == "https"
    assert urlsplit(req.get_full_url()).path == (
        "/tok_0123456789abcdef0123456789ab")
    # valid JSON-RPC getSlot body with confirmed commitment
    payload = _json.loads(req.data.decode("utf-8"))
    assert payload["jsonrpc"] == "2.0"
    assert payload["method"] == "getSlot"
    assert payload["params"] == [{"commitment": "confirmed"}]
    # no unintended Authorization / Origin headers
    assert req.get_header("Authorization") is None
    assert req.get_header("Origin") is None


def test_rpc_transport_preserves_tokenized_path_and_query(monkeypatch) -> None:
    from urllib.parse import urlsplit

    endpoint = "https://rpc.example.invalid/base/tok3n?k=v&n=2"
    captured: Dict[str, Any] = {}
    transport = _transport_for(monkeypatch, endpoint, captured)
    transport("getSlot", [{"commitment": "confirmed"}], 5.0)

    req = captured["request"]
    assert req.get_full_url() == endpoint
    sp = urlsplit(req.get_full_url())
    assert sp.path == "/base/tok3n"
    assert sp.query == "k=v&n=2"


def test_rpc_transport_module_user_agent_is_stable_and_neutral() -> None:
    ua = rgr.RPC_RECOVERY_USER_AGENT
    assert isinstance(ua, str) and ua
    assert not ua.lower().startswith("python-urllib")
    # neutral identifier: carries no URL / host / credential
    assert "://" not in ua


def test_rpc_transport_http_error_is_bounded_fail_closed(monkeypatch) -> None:
    import urllib.error
    import urllib.request

    endpoint = "https://rpc.example.invalid/tok"

    def _raise_http(request, timeout=None):
        raise urllib.error.HTTPError(endpoint, 403, "Forbidden", None, None)

    monkeypatch.setattr(urllib.request, "urlopen", _raise_http)
    transport = rgr.build_rpc_transport_from_env(
        env={rgr.ENV_NAME_RPC_RECOVERY_ENDPOINT: endpoint})
    status, parsed = transport("getSlot", [{"commitment": "confirmed"}], 5.0)
    # HTTP status is RETURNED (so the caller can count pressure), body is None,
    # and NOTHING is raised past the transport boundary.
    assert status == 403
    assert parsed is None


def test_rpc_transport_never_exposes_endpoint_in_errors(monkeypatch) -> None:
    import urllib.request

    endpoint = "https://secret-host.example.invalid/T0KEN_should_never_surface"

    def _raise_generic(request, timeout=None):
        raise RuntimeError("upstream failure " + endpoint)

    monkeypatch.setattr(urllib.request, "urlopen", _raise_generic)
    transport = rgr.build_rpc_transport_from_env(
        env={rgr.ENV_NAME_RPC_RECOVERY_ENDPOINT: endpoint})
    # The endpoint-bearing exception is swallowed; the transport fails closed to
    # (0, None) and never propagates the endpoint in a raised error.
    status, parsed = transport("getSlot", [{"commitment": "confirmed"}], 5.0)
    assert (status, parsed) == (0, None)


def test_adapter_with_fixed_transport_bounded_no_extra_retries(
        monkeypatch) -> None:
    endpoint = "https://rpc.example.invalid/tok"
    captured: Dict[str, Any] = {}
    transport = _transport_for(
        monkeypatch, endpoint, captured,
        body=b'{"jsonrpc":"2.0","id":1,"result":777}')
    config = rgr.RpcGapRecoveryConfig(
        mode=rgr.GAP_RECOVERY_MODE_RPC_BACKFILL,
        authoritative_commitment="confirmed")
    adapter = rgr.SolanaRpcBackfillAdapter(
        rpc_post_fn=transport, config=config, timeout_seconds=5.0)

    slot = adapter.get_slot(commitment="confirmed")
    assert slot == 777
    # exactly one request, no retries/errors: the header fix adds no round-trips
    assert adapter.request_count == 1
    assert adapter.retry_count == 0
    assert adapter.error_count == 0
    # the corrected header flows through the real adapter -> transport path
    req = captured["request"]
    assert req.get_method() == "POST"
    assert req.get_header("User-agent") == rgr.RPC_RECOVERY_USER_AGENT
    assert req.get_header("Authorization") is None


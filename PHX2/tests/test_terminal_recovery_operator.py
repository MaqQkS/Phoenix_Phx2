"""Ceremony F: the tracked terminal-recovery operator tool.

TERMINAL-RESOLUTION-001: the operator workflow for a
``REPLAY_RETENTION_EXCEEDED`` cursor.  These tests pin the tool's fail-closed
shape: explicit state directory, stale-expectation refusals, runtime-ownership
refusal, real-ledger refusal, append-only audit records, production-implementation
reuse -- and, above all, the permanent absence of every unsafe operation.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

import pytest

from PHX2.free_tier_producer import rpc_gap_recovery as rgr
from PHX2.free_tier_producer import stream_cursor as sc
from PHX2.free_tier_producer import terminal_recovery_operator as op
from PHX2.free_tier_producer.paid_grpc_source import (
    build_transaction_skip_identity,
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
        raise AssertionError("NETWORK_CONSTRUCTION_FORBIDDEN_IN_OPERATOR_TESTS")

    monkeypatch.setattr(socket, "socket", _refuse)
    monkeypatch.setattr(urllib.request, "urlopen", _refuse)
    yield


def cursor_expectations(state_dir) -> Dict[str, str]:
    classification = sc.classify_cursor_checkpoint_file(
        state_dir / sc.CURSOR_PRIMARY_BASENAME)
    return {
        "digest": str(classification.envelope_digest),
        "generation": str(int(classification.generation or 0)),
    }


def run_operator(action: str, state_dir, *, digest: Optional[str] = None,
                 generation: Optional[str] = None,
                 identity: str = IDENTITY_DIGEST,
                 extra: Optional[List[str]] = None,
                 source_factory: Any = None,
                 rpc_post_fn: Any = None) -> "tuple[int, List[str]]":
    expected = cursor_expectations(state_dir)
    argv = [
        action,
        "--state-dir", str(state_dir),
        "--expected-state-digest", digest or expected["digest"],
        "--expected-cursor-generation", generation or expected["generation"],
        "--expected-subscription-identity-digest", identity,
    ]
    argv.extend(extra or [])
    lines: List[str] = []
    code = op.main(argv, source_factory=source_factory,
                   rpc_post_fn=rpc_post_fn, out=lines.append)
    return code, lines


def seed_episode_with_target(state_dir, cursor) -> None:
    transport = FakeRpcTransport(
        head_slot=200, produced=PRODUCED, blocks=build_chain(PRODUCED))
    coordinator = make_coordinator(state_dir, cursor, transport=transport)
    open_episode_with_target(coordinator, cursor)


class RetryReplayFactory:
    """Fake provider source factory: honours or refuses exact replay."""

    def __init__(self, *, honors: bool) -> None:
        self.honors = bool(honors)
        self.calls = 0

    def __call__(self, *, from_slot: Any = None, cursor: Any = None,
                 downstream_durable_fn: Any = None, stream_generation: int = 0,
                 transaction_observer: Any = None) -> Any:
        self.calls += 1
        factory = self

        class _Source:
            replay_requested = from_slot is not None
            replay_position_rejected = not factory.honors
            replay_first_available = None
            grpc_status_code = None if factory.honors else "OUT_OF_RANGE"
            sanitized_error_category = (
                None if factory.honors else "GRPC_OUT_OF_RANGE")

            def iter_events(self, *, max_events: int):
                if factory.honors and from_slot is not None \
                        and transaction_observer is not None:
                    transaction_observer(
                        int(from_slot), BOUNDARY_SIG, 0,
                        build_transaction_skip_identity(
                            int(from_slot), BOUNDARY_SIG, 0))
                return iter(())

            def close(self) -> None:
                pass

        return _Source()


# ---------------------------------------------------------------------------
# unsafe operations do not exist
# ---------------------------------------------------------------------------

class TestUnsafeOperationsAbsent:
    def test_forbidden_operations_are_not_actions(self) -> None:
        for name in op.FORBIDDEN_OPERATIONS:
            assert name not in op.OPERATOR_ACTIONS

    @pytest.mark.parametrize("operation", list(op.FORBIDDEN_OPERATIONS))
    def test_forbidden_operation_refused(self, tmp_path, operation) -> None:
        make_terminal_cursor(tmp_path)
        code, lines = run_operator(operation, tmp_path)
        assert code == 2
        assert any(op.REFUSAL_UNSAFE_OPERATION in line for line in lines)

    def test_no_handler_symbols_for_forbidden_operations(self) -> None:
        import inspect as _inspect

        source = _inspect.getsource(op)
        for name in ("_action_clear_cursor", "_action_delete_state",
                     "_action_skip_gap", "_action_force_healthy",
                     "_action_mark_recovery_proven", "_action_set_live_head",
                     "_action_disable_overlap", "_action_ignore_corruption"):
            assert name not in source

    def test_only_production_evidence_reaches_proven(self) -> None:
        import inspect as _inspect

        source = _inspect.getsource(op)
        # The tool never assigns RECOVERY_PROVEN outside the provider-replay
        # resolution that itself required a binding cursor proof.
        assert source.count("RECOVERY_STATE_RECOVERY_PROVEN") == 1


# ---------------------------------------------------------------------------
# structural refusals
# ---------------------------------------------------------------------------

class TestStructuralRefusals:
    def test_stale_state_digest_refused(self, tmp_path) -> None:
        make_terminal_cursor(tmp_path)
        code, lines = run_operator("inspect", tmp_path, digest="f" * 64)
        assert code == 2
        assert any(op.REFUSAL_STATE_DIGEST_STALE in line for line in lines)

    def test_stale_cursor_generation_refused(self, tmp_path) -> None:
        make_terminal_cursor(tmp_path)
        code, lines = run_operator("inspect", tmp_path, generation="99")
        assert code == 2
        assert any(
            op.REFUSAL_CURSOR_GENERATION_STALE in line for line in lines)

    def test_stale_subscription_identity_refused(self, tmp_path) -> None:
        make_terminal_cursor(tmp_path)
        code, lines = run_operator("inspect", tmp_path, identity="ab" * 32)
        assert code == 2
        assert any(op.REFUSAL_SUBSCRIPTION_IDENTITY_STALE in line
                   for line in lines)

    def test_missing_expectations_refused(self, tmp_path) -> None:
        make_terminal_cursor(tmp_path)
        lines: List[str] = []
        code = op.main([
            "inspect", "--state-dir", str(tmp_path)], out=lines.append)
        assert code == 2
        assert any(op.REFUSAL_EXPECTATION_ABSENT in line for line in lines)

    def test_state_dir_holding_a_real_ledger_refused(self, tmp_path) -> None:
        make_terminal_cursor(tmp_path)
        (tmp_path / "ping_dedupe.jsonl").write_text("{}\n", encoding="utf-8")
        code, lines = run_operator("inspect", tmp_path)
        assert code == 2
        assert any(op.REFUSAL_STATE_DIR_IS_LEDGER in line for line in lines)

    def test_runtime_owned_state_dir_refused(self, tmp_path, monkeypatch) -> None:
        make_terminal_cursor(tmp_path)
        lock = rgr.StateDirRuntimeLock(tmp_path)
        lock.path.write_text("999999999|2026-07-22T00:00:00Z",
                             encoding="utf-8")
        monkeypatch.setattr(
            rgr.StateDirRuntimeLock, "_pid_alive",
            staticmethod(lambda _pid: True))
        code, lines = run_operator("inspect", tmp_path)
        assert code == 2
        assert any(
            op.REFUSAL_RUNTIME_OWNS_STATE_DIR in line for line in lines)

    def test_absent_state_dir_refused(self, tmp_path) -> None:
        lines: List[str] = []
        code = op.main([
            "inspect", "--state-dir", str(tmp_path / "missing"),
            "--expected-state-digest", "a" * 64,
            "--expected-cursor-generation", "1",
            "--expected-subscription-identity-digest", IDENTITY_DIGEST,
        ], out=lines.append)
        assert code == 2
        assert any(op.REFUSAL_STATE_DIR_ABSENT in line for line in lines)

    def test_quarantined_cursor_refused_not_ignored(self, tmp_path) -> None:
        cursor = make_terminal_cursor(tmp_path)
        primary = cursor.primary_path
        primary.write_text(primary.read_text(
            encoding="utf-8").replace("100", "101", 1), encoding="utf-8")
        backup = cursor.backup_path
        if backup.exists():
            backup.write_text(backup.read_text(
                encoding="utf-8")[:-3], encoding="utf-8")
        classification = sc.classify_cursor_checkpoint_file(primary)
        code, lines = run_operator(
            "inspect", tmp_path,
            digest=str(classification.envelope_digest), generation="0")
        assert code == 2
        assert any(op.REFUSAL_CURSOR_QUARANTINED in line for line in lines)

    def test_non_terminal_state_refuses_mutation_paths(self, tmp_path) -> None:
        store = sc.build_cursor_store(
            state_dir=tmp_path, subscription_identity_digest=IDENTITY_DIGEST)
        store.load()
        identity = sc.build_stream_event_identity(
            slot=BOUNDARY_SLOT, signature=BOUNDARY_SIG, transaction_index=0)
        store.commit_event(slot=BOUNDARY_SLOT, identity=identity,
                           signature=BOUNDARY_SIG)
        code, lines = run_operator("plan-rpc-backfill", tmp_path)
        assert code == 2
        assert any(op.REFUSAL_NOT_TERMINAL_RECOVERABLE in line
                   for line in lines)


# ---------------------------------------------------------------------------
# inspect / verify / export / plan
# ---------------------------------------------------------------------------

class TestReadOnlyActions:
    def test_inspect_prints_categorical_summary_only(self, tmp_path) -> None:
        make_terminal_cursor(tmp_path)
        code, lines = run_operator("inspect", tmp_path)
        assert code == 0
        text = "\n".join(lines)
        assert "cursor_recovery_terminal" in text
        assert '"cursor_recovery_reason": "GRPC_REPLAY_POSITION_TOO_OLD"' in text
        assert str(tmp_path) not in text          # no path values
        assert "https" not in text                # no endpoints

    def test_inspect_appends_no_audit_record(self, tmp_path) -> None:
        make_terminal_cursor(tmp_path)
        run_operator("inspect", tmp_path)
        assert not (tmp_path / op.OPERATOR_AUDIT_BASENAME).exists()

    def test_verify_reports_degraded_never_healthy(self, tmp_path) -> None:
        make_terminal_cursor(tmp_path)
        code, lines = run_operator("verify-recovery-state", tmp_path)
        assert code == 3
        assert any("DEGRADED" in line for line in lines)

    def test_export_evidence_writes_manifest(self, tmp_path) -> None:
        make_terminal_cursor(tmp_path)
        export_dir = tmp_path / "evidence_export"
        code, lines = run_operator(
            "export-evidence", tmp_path,
            extra=["--export-dir", str(export_dir)])
        assert code == 0
        manifest = json.loads(
            (export_dir / "EVIDENCE_MANIFEST.json").read_text(
                encoding="utf-8"))
        names = {entry["basename"] for entry in manifest["files"]}
        assert sc.CURSOR_PRIMARY_BASENAME in names
        for entry in manifest["files"]:
            assert len(entry["sha256"]) == 64

    def test_export_without_dir_refused(self, tmp_path) -> None:
        make_terminal_cursor(tmp_path)
        code, lines = run_operator("export-evidence", tmp_path)
        assert code == 2
        assert any(op.REFUSAL_EXPORT_DIR_ABSENT in line for line in lines)

    def test_plan_is_offline_and_reports_bounds(self, tmp_path) -> None:
        cursor = make_terminal_cursor(tmp_path)
        seed_episode_with_target(tmp_path, cursor)
        code, lines = run_operator("plan-rpc-backfill", tmp_path)
        assert code == 0
        text = "\n".join(lines)
        assert '"planning_performed_offline": true' in text
        assert '"gap_slots": 10' in text
        assert '"gap_within_bounds": true' in text


# ---------------------------------------------------------------------------
# retry-provider-replay (provider repaired / still refusing)
# ---------------------------------------------------------------------------

class TestRetryProviderReplay:
    def test_provider_repair_permits_exact_replay_retry(self, tmp_path) -> None:
        cursor = make_terminal_cursor(tmp_path)
        assert cursor.is_terminal()
        code, lines = run_operator(
            "retry-provider-replay", tmp_path,
            source_factory=RetryReplayFactory(honors=True))
        assert code == 0
        assert any("REPLAY_PROVEN_TERMINAL_RESOLVED" in line
                   for line in lines)
        reloaded = sc.build_cursor_store(
            state_dir=tmp_path, subscription_identity_digest=IDENTITY_DIGEST)
        reloaded.load()
        assert not reloaded.is_terminal()
        audit = (tmp_path / op.OPERATOR_AUDIT_BASENAME).read_text(
            encoding="utf-8").strip().splitlines()
        assert len(audit) == 1
        record = json.loads(audit[0])
        assert record["action"] == "retry-provider-replay"
        assert record["outcome"] == "REPLAY_PROVEN_TERMINAL_RESOLVED"

    def test_still_refused_replay_stays_terminal(self, tmp_path) -> None:
        cursor = make_terminal_cursor(tmp_path)
        code, lines = run_operator(
            "retry-provider-replay", tmp_path,
            source_factory=RetryReplayFactory(honors=False))
        assert code == 3
        assert any("REPLAY_STILL_REFUSED" in line for line in lines)
        reloaded = sc.build_cursor_store(
            state_dir=tmp_path, subscription_identity_digest=IDENTITY_DIGEST)
        reloaded.load()
        assert reloaded.is_terminal()

    def test_retry_without_factory_or_network_refused(self, tmp_path) -> None:
        make_terminal_cursor(tmp_path)
        code, lines = run_operator("retry-provider-replay", tmp_path)
        assert code == 2
        assert any(op.REFUSAL_NETWORK_NOT_ALLOWED in line for line in lines)


# ---------------------------------------------------------------------------
# execute / resume rpc backfill (production implementation reuse)
# ---------------------------------------------------------------------------

class TestExecuteResumeBackfill:
    def _transport(self) -> FakeRpcTransport:
        return FakeRpcTransport(
            head_slot=200, produced=PRODUCED, blocks=build_chain(PRODUCED))

    def test_execute_runs_production_backfill_to_proof(self, tmp_path) -> None:
        cursor = make_terminal_cursor(tmp_path)
        seed_episode_with_target(tmp_path, cursor)
        code, lines = run_operator(
            "execute-rpc-backfill", tmp_path,
            extra=["--acknowledge-recovered-candidates-exported"],
            rpc_post_fn=self._transport())
        assert code == 0
        assert any("RECOVERY_PROVEN" in line for line in lines)
        reloaded = sc.build_cursor_store(
            state_dir=tmp_path, subscription_identity_digest=IDENTITY_DIGEST)
        reloaded.load()
        assert not reloaded.is_terminal()
        recovery = rgr.RpcGapRecoveryStore(state_dir=tmp_path)
        recovery.load()
        assert recovery.state.recovery_state == (
            rgr.RECOVERY_STATE_RECOVERY_PROVEN)
        audit = (tmp_path / op.OPERATOR_AUDIT_BASENAME).read_text(
            encoding="utf-8").strip().splitlines()
        assert json.loads(audit[-1])["outcome"] == "RECOVERY_PROVEN"

    def test_execute_without_acknowledgement_refused(self, tmp_path) -> None:
        cursor = make_terminal_cursor(tmp_path)
        seed_episode_with_target(tmp_path, cursor)
        code, lines = run_operator(
            "execute-rpc-backfill", tmp_path, rpc_post_fn=self._transport())
        assert code == 2
        assert any(op.REFUSAL_CANDIDATE_EXPORT_UNACKNOWLEDGED in line
                   for line in lines)

    def test_execute_without_episode_refused(self, tmp_path) -> None:
        make_terminal_cursor(tmp_path)
        code, lines = run_operator(
            "execute-rpc-backfill", tmp_path,
            extra=["--acknowledge-recovered-candidates-exported"],
            rpc_post_fn=self._transport())
        assert code == 2
        assert any(op.REFUSAL_EPISODE_ABSENT in line for line in lines)

    def test_execute_with_progress_requires_resume(self, tmp_path) -> None:
        cursor = make_terminal_cursor(tmp_path)
        seed_episode_with_target(tmp_path, cursor)
        recovery = rgr.RpcGapRecoveryStore(state_dir=tmp_path)
        recovery.load()
        recovery.update(last_completed_slot=104,
                        last_completed_blockhash="H104")
        code, lines = run_operator(
            "execute-rpc-backfill", tmp_path,
            extra=["--acknowledge-recovered-candidates-exported"],
            rpc_post_fn=self._transport())
        assert code == 2
        assert any(op.REFUSAL_PROGRESS_PRESENT_USE_RESUME in line
                   for line in lines)
        code, lines = run_operator(
            "resume-rpc-backfill", tmp_path,
            extra=["--acknowledge-recovered-candidates-exported"],
            rpc_post_fn=self._transport())
        assert code == 0
        assert any("RECOVERY_PROVEN" in line for line in lines)

    def test_resume_without_progress_requires_execute(self, tmp_path) -> None:
        cursor = make_terminal_cursor(tmp_path)
        seed_episode_with_target(tmp_path, cursor)
        code, lines = run_operator(
            "resume-rpc-backfill", tmp_path,
            extra=["--acknowledge-recovered-candidates-exported"],
            rpc_post_fn=self._transport())
        assert code == 2
        assert any(op.REFUSAL_PROGRESS_ABSENT_USE_EXECUTE in line
                   for line in lines)

    def test_execute_without_transport_or_network_refused(
            self, tmp_path) -> None:
        cursor = make_terminal_cursor(tmp_path)
        seed_episode_with_target(tmp_path, cursor)
        code, lines = run_operator(
            "execute-rpc-backfill", tmp_path,
            extra=["--acknowledge-recovered-candidates-exported"])
        assert code == 2
        assert any(op.REFUSAL_NETWORK_NOT_ALLOWED in line for line in lines)

    def test_exact_proof_remains_required(self, tmp_path) -> None:
        cursor = make_terminal_cursor(tmp_path)
        seed_episode_with_target(tmp_path, cursor)
        transport = FakeRpcTransport(
            head_slot=200, produced=PRODUCED,
            blocks=build_chain(PRODUCED, overlap_sig="S1gDifferent"))
        code, lines = run_operator(
            "execute-rpc-backfill", tmp_path,
            extra=["--acknowledge-recovered-candidates-exported"],
            rpc_post_fn=transport)
        assert code == 3
        assert any("RECOVERY_TERMINAL" in line for line in lines)
        reloaded = sc.build_cursor_store(
            state_dir=tmp_path, subscription_identity_digest=IDENTITY_DIGEST)
        reloaded.load()
        assert reloaded.is_terminal()

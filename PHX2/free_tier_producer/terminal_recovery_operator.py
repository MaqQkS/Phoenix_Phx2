"""Tracked operator tool for resolving a terminal gRPC recovery cursor.

TERMINAL-RESOLUTION-001 (2026-07-22 live acceptance): a
``REPLAY_RETENTION_EXCEEDED`` terminal cursor had no tracked operator
workflow.  This module is that workflow -- and nothing more.  It drives the
SAME production recovery implementation (``stream_cursor`` and
``rpc_gap_recovery``); it contains no second state machine, and only
production evidence can transition anything to ``RECOVERY_PROVEN``.

Deliberately absent, and refused if requested: ``clear-cursor``,
``delete-state``, ``skip-gap``, ``force-healthy``, ``mark-recovery-proven``,
``set-live-head``, ``disable-overlap``, ``ignore-corruption``.  There is no
flag combination that abandons a range, fabricates coverage or overwrites
quarantined evidence.

Safety posture:

  * the cursor/state directory is EXPLICIT (``--state-dir``); nothing is
    discovered implicitly;
  * the caller must present the expected terminal-state envelope digest, the
    expected cursor generation and the expected subscription identity digest;
    a stale or foreign expectation refuses before anything is touched;
  * a state directory owned by a live PHX2 runtime refuses;
  * a state directory that is (or contains) a real ping ledger refuses;
  * every mutating action appends an operator audit record;
  * planning is fully offline; live actions additionally require
    ``--allow-network`` unless a test injects fakes;
  * output is categorical only -- no endpoint, credential, path value or raw
    provider payload is ever printed.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

from PHX2.free_tier_producer import checkpoint_envelope as _cpe
from PHX2.free_tier_producer import rpc_gap_recovery as _rgr
from PHX2.free_tier_producer import stream_cursor as _cursor_mod
from PHX2.free_tier_producer.launcher_contract import path_is_forbidden


ACTION_INSPECT = "inspect"
ACTION_EXPORT_EVIDENCE = "export-evidence"
ACTION_RETRY_PROVIDER_REPLAY = "retry-provider-replay"
ACTION_PLAN_RPC_BACKFILL = "plan-rpc-backfill"
ACTION_EXECUTE_RPC_BACKFILL = "execute-rpc-backfill"
ACTION_RESUME_RPC_BACKFILL = "resume-rpc-backfill"
ACTION_VERIFY_RECOVERY_STATE = "verify-recovery-state"

OPERATOR_ACTIONS = (
    ACTION_INSPECT,
    ACTION_EXPORT_EVIDENCE,
    ACTION_RETRY_PROVIDER_REPLAY,
    ACTION_PLAN_RPC_BACKFILL,
    ACTION_EXECUTE_RPC_BACKFILL,
    ACTION_RESUME_RPC_BACKFILL,
    ACTION_VERIFY_RECOVERY_STATE,
)

#: Unsafe operations this tool must never provide. Kept as data so tests can
#: assert both that they are refused AND that no handler exists for them.
FORBIDDEN_OPERATIONS = (
    "clear-cursor",
    "delete-state",
    "skip-gap",
    "force-healthy",
    "mark-recovery-proven",
    "set-live-head",
    "disable-overlap",
    "ignore-corruption",
)

MUTATING_ACTIONS = (
    ACTION_RETRY_PROVIDER_REPLAY,
    ACTION_EXECUTE_RPC_BACKFILL,
    ACTION_RESUME_RPC_BACKFILL,
)

# Closed-set operator refusal tokens.
REFUSAL_UNSAFE_OPERATION = "OPERATOR_UNSAFE_OPERATION_REFUSED"
REFUSAL_STATE_DIR_ABSENT = "OPERATOR_STATE_DIR_ABSENT"
REFUSAL_STATE_DIR_FORBIDDEN = "OPERATOR_STATE_DIR_FORBIDDEN_ROOT"
REFUSAL_STATE_DIR_IS_LEDGER = "OPERATOR_STATE_DIR_IS_LEDGER_DIR"
REFUSAL_RUNTIME_OWNS_STATE_DIR = "OPERATOR_RUNTIME_OWNS_STATE_DIR"
REFUSAL_EXPECTATION_ABSENT = "OPERATOR_EXPECTED_STATE_ABSENT"
REFUSAL_STATE_DIGEST_STALE = "OPERATOR_STATE_DIGEST_STALE"
REFUSAL_CURSOR_GENERATION_STALE = "OPERATOR_CURSOR_GENERATION_STALE"
REFUSAL_SUBSCRIPTION_IDENTITY_STALE = "OPERATOR_SUBSCRIPTION_IDENTITY_STALE"
REFUSAL_CURSOR_NOT_FOUND = "OPERATOR_CURSOR_NOT_FOUND"
REFUSAL_CURSOR_QUARANTINED = "OPERATOR_CURSOR_QUARANTINED"
REFUSAL_NOT_TERMINAL_RECOVERABLE = "OPERATOR_STATE_NOT_TERMINAL_RECOVERABLE"
REFUSAL_EPISODE_ABSENT = "OPERATOR_RECOVERY_EPISODE_ABSENT"
REFUSAL_OVERLAP_TARGET_ABSENT = "OPERATOR_OVERLAP_TARGET_ABSENT"
REFUSAL_TRANSPORT_ABSENT = "OPERATOR_RPC_TRANSPORT_ABSENT"
REFUSAL_NETWORK_NOT_ALLOWED = "OPERATOR_NETWORK_NOT_ALLOWED"
REFUSAL_SOURCE_FACTORY_ABSENT = "OPERATOR_SOURCE_FACTORY_ABSENT"
REFUSAL_EXPORT_DIR_ABSENT = "OPERATOR_EXPORT_DIR_ABSENT"
REFUSAL_PROGRESS_PRESENT_USE_RESUME = "OPERATOR_PROGRESS_PRESENT_USE_RESUME"
REFUSAL_PROGRESS_ABSENT_USE_EXECUTE = "OPERATOR_PROGRESS_ABSENT_USE_EXECUTE"
REFUSAL_CANDIDATE_EXPORT_UNACKNOWLEDGED = (
    "OPERATOR_RECOVERED_CANDIDATE_EXPORT_UNACKNOWLEDGED")
REFUSAL_AUDIT_WRITE_FAILED = "OPERATOR_AUDIT_WRITE_FAILED"

OPERATOR_AUDIT_BASENAME = "operator_audit.jsonl"
RECOVERED_CANDIDATES_BASENAME = "operator_recovered_candidates.jsonl"

#: Real-ledger basename; a state directory carrying one is a ledger directory
#: and is never a valid recovery target.
_LEDGER_BASENAME = "ping_dedupe.jsonl"


class _OperatorRefusal(RuntimeError):
    def __init__(self, token: str) -> None:
        super().__init__(token)
        self.token = token


def _emit(out: Callable[[str], None], line: str) -> None:
    out(line)


def _path_digest(path: Path) -> str:
    return _cpe.sha256_hex_text(str(path).lower())


class OperatorContext:
    """Validated handles on one explicit state directory. Opens nothing live."""

    def __init__(self, *, state_dir: Path,
                 expected_state_digest: str,
                 expected_cursor_generation: int,
                 expected_subscription_identity_digest: str,
                 now_iso_fn: Callable[[], str] = _cpe.utc_now_iso) -> None:
        self.state_dir = state_dir
        self.expected_state_digest = str(expected_state_digest)
        self.expected_cursor_generation = int(expected_cursor_generation)
        self.expected_identity_digest = str(
            expected_subscription_identity_digest)
        self._now_iso = now_iso_fn
        self.cursor_store: Optional[_cursor_mod.GrpcStreamCursorStore] = None
        self.recovery_store: Optional[_rgr.RpcGapRecoveryStore] = None
        self.quarantine_buffer: Optional[_rgr.QuarantinedLiveBuffer] = None
        self.cursor_load: Optional[Any] = None

    # -- structural refusals ---------------------------------------------

    def refuse_if_unsafe_target(self) -> None:
        if not self.state_dir.is_dir():
            raise _OperatorRefusal(REFUSAL_STATE_DIR_ABSENT)
        if path_is_forbidden(self.state_dir):
            raise _OperatorRefusal(REFUSAL_STATE_DIR_FORBIDDEN)
        if (self.state_dir / _LEDGER_BASENAME).exists():
            raise _OperatorRefusal(REFUSAL_STATE_DIR_IS_LEDGER)
        lock = _rgr.StateDirRuntimeLock(self.state_dir)
        if lock.held_by_live_other_process():
            raise _OperatorRefusal(REFUSAL_RUNTIME_OWNS_STATE_DIR)

    def load_and_verify_expectations(self) -> None:
        classification = _cursor_mod.classify_cursor_checkpoint_file(
            self.state_dir / _cursor_mod.CURSOR_PRIMARY_BASENAME)
        if classification.state == _cpe.FILE_MISSING:
            raise _OperatorRefusal(REFUSAL_CURSOR_NOT_FOUND)
        observed_digest = classification.envelope_digest or ""
        if observed_digest != self.expected_state_digest:
            raise _OperatorRefusal(REFUSAL_STATE_DIGEST_STALE)
        self.cursor_store = _cursor_mod.build_cursor_store(
            state_dir=self.state_dir,
            subscription_identity_digest=self.expected_identity_digest)
        self.cursor_load = self.cursor_store.load()
        if self.cursor_store.quarantined:
            # Quarantined evidence is preserved, inspected, exported -- never
            # resolved by this tool. ``ignore-corruption`` does not exist.
            raise _OperatorRefusal(REFUSAL_CURSOR_QUARANTINED)
        if not self.cursor_store.subscription_identity_matches:
            raise _OperatorRefusal(REFUSAL_SUBSCRIPTION_IDENTITY_STALE)
        if int(self.cursor_store.generation) != int(
                self.expected_cursor_generation):
            raise _OperatorRefusal(REFUSAL_CURSOR_GENERATION_STALE)
        self.recovery_store = _rgr.RpcGapRecoveryStore(
            state_dir=self.state_dir)
        self.recovery_store.load()
        config = _rgr.RpcGapRecoveryConfig(
            mode=_rgr.GAP_RECOVERY_MODE_RPC_BACKFILL,
            authoritative_commitment="confirmed")
        self.quarantine_buffer = _rgr.QuarantinedLiveBuffer(
            state_dir=self.state_dir,
            subscription_identity_digest=self.expected_identity_digest,
            max_events=config.max_quarantine_events,
            max_bytes=config.max_quarantine_bytes,
            max_age_seconds=config.max_quarantine_age_seconds)
        self.quarantine_buffer.load()

    def refuse_unless_terminal_recoverable(self) -> None:
        store = self.cursor_store
        assert store is not None
        state = store.state
        if not state.recovery_terminal:
            raise _OperatorRefusal(REFUSAL_NOT_TERMINAL_RECOVERABLE)
        if state.recovery_reason != _cursor_mod.REASON_REPLAY_POSITION_TOO_OLD:
            raise _OperatorRefusal(REFUSAL_NOT_TERMINAL_RECOVERABLE)

    # -- audit ------------------------------------------------------------

    def append_audit(self, *, action: str, outcome: str,
                     detail: Optional[Dict[str, Any]] = None) -> None:
        record = {
            "kind": "PHX2_TERMINAL_RECOVERY_OPERATOR_AUDIT",
            "at_utc": self._now_iso(),
            "action": str(action),
            "outcome": str(outcome),
            "state_dir_digest": _path_digest(self.state_dir),
            "expected_state_digest": self.expected_state_digest,
            "expected_cursor_generation": self.expected_cursor_generation,
            "expected_subscription_identity_digest": (
                self.expected_identity_digest),
        }
        if detail:
            record["detail"] = detail
        path = self.state_dir / OPERATOR_AUDIT_BASENAME
        try:
            with path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, sort_keys=True) + "\n")
        except OSError as exc:
            raise _OperatorRefusal(REFUSAL_AUDIT_WRITE_FAILED) from exc

    def audit_count(self) -> int:
        path = self.state_dir / OPERATOR_AUDIT_BASENAME
        try:
            with path.open("r", encoding="utf-8") as handle:
                return sum(1 for line in handle if line.strip())
        except OSError:
            return 0

    # -- summaries ---------------------------------------------------------

    def categorical_summary(self) -> Dict[str, Any]:
        store = self.cursor_store
        recovery = self.recovery_store
        buffer = self.quarantine_buffer
        assert store is not None and recovery is not None and buffer is not None
        cursor_state = store.state
        return {
            "cursor_generation": int(store.generation),
            "cursor_quarantined": bool(store.quarantined),
            "cursor_recovery_terminal": bool(cursor_state.recovery_terminal),
            "cursor_recovery_status": cursor_state.recovery_status,
            "cursor_recovery_reason": cursor_state.recovery_reason,
            "cursor_safe_resume_slot": cursor_state.safe_resume_slot(),
            "cursor_last_durable_slot": (
                None if not cursor_state.has_position()
                else int(cursor_state.last_durable_slot)),
            "cursor_recovery_generation": int(
                cursor_state.recovery_generation),
            "cursor_attempt_generation": int(cursor_state.attempt_generation),
            "recovery": recovery.snapshot(),
            "quarantine": buffer.snapshot(),
            "operator_action_count": self.audit_count(),
        }


def _print_summary(out: Callable[[str], None], summary: Dict[str, Any]) -> None:
    _emit(out, "operator summary (categorical only):")
    _emit(out, json.dumps(summary, sort_keys=True, indent=2, default=str))


# ---------------------------------------------------------------------------
# actions
# ---------------------------------------------------------------------------

def _action_inspect(ctx: OperatorContext,
                    out: Callable[[str], None]) -> int:
    _print_summary(out, ctx.categorical_summary())
    return 0


def _action_verify(ctx: OperatorContext, out: Callable[[str], None]) -> int:
    summary = ctx.categorical_summary()
    _print_summary(out, summary)
    degraded = bool(
        summary["cursor_recovery_terminal"]
        or summary["cursor_quarantined"]
        or summary["recovery"].get("recovery_store_quarantined")
        or summary["quarantine"].get("quarantine_store_quarantined")
        or summary["recovery"].get("recovery_state")
        in (_rgr.RECOVERY_STATE_RECOVERY_TERMINAL,)
        or summary["recovery"].get("recovery_state")
        in _rgr.RESUMABLE_RECOVERY_STATES)
    _emit(out, f"verify-recovery-state: "
               f"{'DEGRADED' if degraded else 'CONSISTENT_HEALTHY'}")
    # A degraded or terminal recovery is never reported as healthy.
    return 3 if degraded else 0


def _action_export(ctx: OperatorContext, out: Callable[[str], None],
                   export_dir: Optional[str]) -> int:
    if not export_dir:
        raise _OperatorRefusal(REFUSAL_EXPORT_DIR_ABSENT)
    target = Path(export_dir)
    target.mkdir(parents=True, exist_ok=True)
    manifest: List[Dict[str, Any]] = []
    names = (
        _cursor_mod.CURSOR_PRIMARY_BASENAME,
        _cursor_mod.CURSOR_PRIMARY_BASENAME + _cursor_mod.CURSOR_BACKUP_SUFFIX,
        _rgr.RECOVERY_PRIMARY_BASENAME,
        _rgr.RECOVERY_PRIMARY_BASENAME + ".bak",
        _rgr.QUARANTINE_PRIMARY_BASENAME,
        _rgr.QUARANTINE_PRIMARY_BASENAME + ".bak",
        OPERATOR_AUDIT_BASENAME,
    )
    for name in names:
        source = ctx.state_dir / name
        if not source.is_file():
            continue
        destination = target / name
        shutil.copyfile(source, destination)
        digest = _cpe.sha256_hex_bytes(destination.read_bytes())
        manifest.append({
            "basename": name,
            "bytes": destination.stat().st_size,
            "sha256": digest,
        })
    manifest_path = target / "EVIDENCE_MANIFEST.json"
    manifest_path.write_text(
        json.dumps({
            "kind": "PHX2_TERMINAL_RECOVERY_EVIDENCE_MANIFEST",
            "exported_at_utc": _cpe.utc_now_iso(),
            "state_dir_digest": _path_digest(ctx.state_dir),
            "files": manifest,
        }, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    _emit(out, f"export-evidence: files_exported={len(manifest)} "
               "(values on disk; nothing printed)")
    return 0


def _action_plan(ctx: OperatorContext, out: Callable[[str], None]) -> int:
    ctx.refuse_unless_terminal_recoverable()
    assert ctx.cursor_store is not None and ctx.recovery_store is not None
    cursor_state = ctx.cursor_store.state
    recovery_state = ctx.recovery_store.state
    boundary = cursor_state.safe_resume_slot()
    config = _rgr.RpcGapRecoveryConfig(
        mode=_rgr.GAP_RECOVERY_MODE_RPC_BACKFILL,
        authoritative_commitment="confirmed")
    episode_open = ctx.recovery_store.has_resumable_episode()
    target = recovery_state.recovery_target_slot if episode_open else None
    plan = {
        "safe_from_slot": boundary,
        "episode_open": episode_open,
        "entry_classification": (
            recovery_state.entry_classification if episode_open else None),
        "recovery_target_slot": target,
        "gap_slots": (None if (boundary is None or target is None)
                      else int(target) - int(boundary)),
        "gap_within_bounds": (
            None if (boundary is None or target is None)
            else (int(target) - int(boundary)) <= config.max_gap_slots),
        "last_completed_slot": (
            recovery_state.last_completed_slot if episode_open else None),
        "bounds": config.snapshot(),
        "network_required_for_execution": True,
        "planning_performed_offline": True,
    }
    _emit(out, "plan-rpc-backfill (dry, offline):")
    _emit(out, json.dumps(plan, sort_keys=True, indent=2, default=str))
    if not episode_open:
        _emit(out, "note: no open recovery episode. The production session "
                   "opens one when a classified retention refusal occurs; "
                   "this tool never fabricates an episode.")
    return 0


def _action_retry_replay(
    ctx: OperatorContext, out: Callable[[str], None],
    *, source_factory: Optional[Callable[..., Any]], allow_network: bool,
    max_probe_events: int = 4,
) -> int:
    ctx.refuse_unless_terminal_recoverable()
    assert ctx.cursor_store is not None
    if source_factory is None:
        if not allow_network:
            raise _OperatorRefusal(REFUSAL_NETWORK_NOT_ALLOWED)
        raise _OperatorRefusal(REFUSAL_SOURCE_FACTORY_ABSENT)
    cursor_store = ctx.cursor_store
    boundary = cursor_store.state.safe_resume_slot()
    if boundary is None:
        raise _OperatorRefusal(REFUSAL_NOT_TERMINAL_RECOVERABLE)
    observed: Dict[str, Any] = {}

    def _observer(slot: int, signature: str, tx_index: Optional[int],
                  skip_identity: str) -> None:
        if "identity" not in observed and int(slot) == int(boundary):
            observed["identity"] = skip_identity
            observed["slot"] = int(slot)

    kwargs: Dict[str, Any] = dict(
        from_slot=int(boundary), cursor=cursor_store,
        downstream_durable_fn=None, stream_generation=0)
    try:
        source = source_factory(transaction_observer=_observer, **kwargs)
    except TypeError:
        source = source_factory(**kwargs)
    consumed = 0
    try:
        for _event in source.iter_events(max_events=max(1, max_probe_events)):
            consumed += 1
            if "identity" in observed:
                break
    except Exception:
        pass
    finally:
        close = getattr(source, "close", None)
        if callable(close):
            try:
                close()
            except Exception:
                pass
    rejected = bool(getattr(source, "replay_position_rejected", False))
    outcome = "REPLAY_STILL_REFUSED"
    resolved = False
    if not rejected and "identity" in observed:
        resolved = bool(
            cursor_store.resolve_terminal_retention_with_backfill_proof(
                safe_from_slot=int(boundary),
                proven_target_slot=int(boundary),
                overlap_identity=str(observed["identity"]),
                recovery_generation=int(
                    cursor_store.state.recovery_generation),
                subscription_identity_digest=ctx.expected_identity_digest))
        outcome = ("REPLAY_PROVEN_TERMINAL_RESOLVED" if resolved
                   else "REPLAY_OVERLAP_SEEN_RESOLUTION_REFUSED")
    elif not rejected:
        outcome = "REPLAY_NOT_REFUSED_NO_BOUNDARY_OVERLAP_YET"
    if resolved and ctx.recovery_store is not None \
            and ctx.recovery_store.has_resumable_episode():
        try:
            ctx.recovery_store.update(
                recovery_target_slot=int(boundary),
                overlap_slot=int(observed["slot"]),
                overlap_signature="provider_replay",
                overlap_skip_identity=str(observed["identity"]),
                overlap_proof_state=_rgr.OVERLAP_PROVEN,
                recovery_state=_rgr.RECOVERY_STATE_RECOVERY_PROVEN)
        except Exception:
            pass
    ctx.append_audit(
        action=ACTION_RETRY_PROVIDER_REPLAY, outcome=outcome,
        detail={"events_probed": consumed,
                "replay_position_rejected": rejected})
    _emit(out, f"retry-provider-replay: {outcome} "
               f"(events_probed={consumed})")
    return 0 if resolved else 3


def _run_backfill(
    ctx: OperatorContext, out: Callable[[str], None],
    *, action: str, rpc_post_fn: Optional[Callable[..., Any]],
    allow_network: bool, candidates_acknowledged: bool,
) -> int:
    ctx.refuse_unless_terminal_recoverable()
    assert ctx.cursor_store is not None
    assert ctx.recovery_store is not None
    assert ctx.quarantine_buffer is not None
    recovery_store = ctx.recovery_store
    if not recovery_store.has_resumable_episode():
        raise _OperatorRefusal(REFUSAL_EPISODE_ABSENT)
    if recovery_store.state.recovery_target_slot is None:
        raise _OperatorRefusal(REFUSAL_OVERLAP_TARGET_ABSENT)
    progress = recovery_store.state.last_completed_slot is not None
    if action == ACTION_EXECUTE_RPC_BACKFILL and progress:
        raise _OperatorRefusal(REFUSAL_PROGRESS_PRESENT_USE_RESUME)
    if action == ACTION_RESUME_RPC_BACKFILL and not progress:
        raise _OperatorRefusal(REFUSAL_PROGRESS_ABSENT_USE_EXECUTE)
    if not candidates_acknowledged:
        # Candidates recovered outside a live session cannot reach the live
        # watchlist; they land durably in the export file below. The operator
        # must acknowledge that explicitly rather than discover it later.
        raise _OperatorRefusal(REFUSAL_CANDIDATE_EXPORT_UNACKNOWLEDGED)
    if rpc_post_fn is None:
        if not allow_network:
            raise _OperatorRefusal(REFUSAL_NETWORK_NOT_ALLOWED)
        rpc_post_fn = _rgr.build_rpc_transport_from_env()
        if rpc_post_fn is None:
            raise _OperatorRefusal(REFUSAL_TRANSPORT_ABSENT)
    episode = recovery_store.state
    config = _rgr.RpcGapRecoveryConfig(
        mode=_rgr.GAP_RECOVERY_MODE_RPC_BACKFILL,
        authoritative_commitment=(
            episode.authoritative_commitment
            if episode.authoritative_commitment
            in _rgr.AUTHORITATIVE_COMMITMENTS else "confirmed"))
    coordinator = _rgr.RpcGapBackfillCoordinator(
        config=config,
        recovery_store=recovery_store,
        quarantine_buffer=ctx.quarantine_buffer,
        subscription_identity_digest=ctx.expected_identity_digest,
        rpc_post_fn=rpc_post_fn,
    )
    ok, detail = coordinator.begin_or_resume_episode(
        cursor_store=ctx.cursor_store)
    if not ok:
        ctx.append_audit(action=action, outcome=f"EPISODE_REFUSED:{detail}")
        _emit(out, f"{action}: EPISODE_REFUSED ({detail})")
        return 3
    recovered_path = ctx.state_dir / RECOVERED_CANDIDATES_BASENAME
    recovered_counter = {"n": 0}

    def _export_candidate(candidate: Dict[str, Any]) -> bool:
        try:
            with recovered_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(
                    candidate, sort_keys=True, default=str) + "\n")
            recovered_counter["n"] += 1
            return True
        except OSError:
            return False

    proven = coordinator.run_backfill(apply_candidate_fn=_export_candidate)
    drained = 0
    if proven:
        plan = coordinator.drain_plan()
        for entry in plan.get("candidates") or []:
            candidate = entry.get("candidate")
            if isinstance(candidate, dict) and candidate:
                if _export_candidate(dict(candidate)):
                    drained += 1
        coordinator.mark_drained(applied=drained, suppressed=0)
    outcome = ("RECOVERY_PROVEN" if proven else
               f"RECOVERY_TERMINAL:{coordinator.terminal_reason()}")
    ctx.append_audit(
        action=action, outcome=outcome,
        detail={"recovered_candidates_exported": recovered_counter["n"],
                "buffered_candidates_drained": drained})
    _emit(out, f"{action}: {outcome} "
               f"recovered_candidates_exported={recovered_counter['n']}")
    return 0 if proven else 3


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m PHX2.free_tier_producer.terminal_recovery_operator",
        description=(
            "Fail-closed operator workflow for a terminal gRPC recovery "
            "cursor. Only production evidence can prove recovery; no unsafe "
            "operation exists."))
    parser.add_argument("action", choices=list(OPERATOR_ACTIONS)
                        + list(FORBIDDEN_OPERATIONS))
    parser.add_argument("--state-dir", dest="state_dir", required=True,
                        help="EXPLICIT cursor/state directory. Never "
                             "discovered implicitly.")
    parser.add_argument("--expected-state-digest", dest="expected_state_digest",
                        default=None,
                        help="expected envelope digest of the terminal cursor "
                             "checkpoint (from inspect/export of the incident).")
    parser.add_argument("--expected-cursor-generation",
                        dest="expected_cursor_generation", type=int,
                        default=None)
    parser.add_argument("--expected-subscription-identity-digest",
                        dest="expected_subscription_identity_digest",
                        default=None)
    parser.add_argument("--export-dir", dest="export_dir", default=None)
    parser.add_argument("--allow-network", dest="allow_network",
                        action="store_true",
                        help="permit live provider/RPC access for retry and "
                             "execute/resume. Never implied.")
    parser.add_argument("--acknowledge-recovered-candidates-exported",
                        dest="candidates_acknowledged", action="store_true",
                        help="required for execute/resume: recovered "
                             "candidates land in a durable export file, not "
                             "the live watchlist.")
    return parser


def main(argv: Optional[Sequence[str]] = None, *,
         source_factory: Optional[Callable[..., Any]] = None,
         rpc_post_fn: Optional[Callable[..., Any]] = None,
         out: Callable[[str], None] = print) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(list(argv) if argv is not None else None)
    except SystemExit as exc:
        return int(exc.code or 2)
    if args.action in FORBIDDEN_OPERATIONS:
        _emit(out, f"[refused] {REFUSAL_UNSAFE_OPERATION}: {args.action} is "
                   "not provided by this tool and never will be. Only "
                   "production evidence can transition recovery state.")
        return 2
    if (args.expected_state_digest is None
            or args.expected_cursor_generation is None
            or args.expected_subscription_identity_digest is None):
        _emit(out, f"[refused] {REFUSAL_EXPECTATION_ABSENT}")
        return 2
    ctx = OperatorContext(
        state_dir=Path(args.state_dir),
        expected_state_digest=args.expected_state_digest,
        expected_cursor_generation=args.expected_cursor_generation,
        expected_subscription_identity_digest=(
            args.expected_subscription_identity_digest))
    try:
        ctx.refuse_if_unsafe_target()
        ctx.load_and_verify_expectations()
        if args.action == ACTION_INSPECT:
            return _action_inspect(ctx, out)
        if args.action == ACTION_VERIFY_RECOVERY_STATE:
            return _action_verify(ctx, out)
        if args.action == ACTION_EXPORT_EVIDENCE:
            return _action_export(ctx, out, args.export_dir)
        if args.action == ACTION_PLAN_RPC_BACKFILL:
            return _action_plan(ctx, out)
        if args.action == ACTION_RETRY_PROVIDER_REPLAY:
            return _action_retry_replay(
                ctx, out, source_factory=source_factory,
                allow_network=bool(args.allow_network))
        if args.action in (ACTION_EXECUTE_RPC_BACKFILL,
                           ACTION_RESUME_RPC_BACKFILL):
            return _run_backfill(
                ctx, out, action=args.action, rpc_post_fn=rpc_post_fn,
                allow_network=bool(args.allow_network),
                candidates_acknowledged=bool(args.candidates_acknowledged))
        _emit(out, f"[refused] {REFUSAL_UNSAFE_OPERATION}")
        return 2
    except _OperatorRefusal as refusal:
        _emit(out, f"[refused] {refusal.token}")
        return 2


__all__ = (
    "OPERATOR_ACTIONS",
    "FORBIDDEN_OPERATIONS",
    "MUTATING_ACTIONS",
    "OPERATOR_AUDIT_BASENAME",
    "RECOVERED_CANDIDATES_BASENAME",
    "OperatorContext",
    "build_parser",
    "main",
)


if __name__ == "__main__":
    sys.exit(main())

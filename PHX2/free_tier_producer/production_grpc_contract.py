"""Armed-production configuration contract for the single Yellowstone stream.

The 2026-07-20 re-audit found that every launch path available to the operator
bypassed the cursor entirely: the normal launcher ran an out-of-repo session
that imported none of this package, and even the repository path built no
cursor because ``--provider-mode`` defaults to ``free_tier``.  The reconnect
work was, in production terms, dead code.

This module is the gate that makes that state unreachable.  It is evaluated
BEFORE any channel, stub, subscription or credential object exists, and it
refuses rather than degrades: an armed production run either executes the
tracked cursor-aware gRPC path or it does not start.

The generic development CLI keeps its historical, permissive behaviour --
free-tier discovery, no cursor, disposable directories.  Only
``--require-production-grpc`` opts into the strict contract.

Nothing here opens a socket, reads an environment file, or touches a
credential: it inspects already-safe structural values supplied by its caller.
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence


# Closed-set refusal reasons. No path fragment, endpoint, credential or raw
# exception ever reaches an artifact through these.
REFUSAL_PROVIDER_MODE_NOT_PAID = "PRODUCTION_PROVIDER_MODE_NOT_PAID_GRPC"
REFUSAL_CURSOR_STORE_ABSENT = "PRODUCTION_CURSOR_STORE_ABSENT"
REFUSAL_CURSOR_DIR_EPHEMERAL = "PRODUCTION_CURSOR_STATE_DIR_EPHEMERAL"
REFUSAL_CURSOR_DIR_IS_RUN_DIR = "PRODUCTION_CURSOR_STATE_DIR_IS_RUN_DIR"
REFUSAL_CURSOR_IDENTITY_MISMATCH = "PRODUCTION_CURSOR_IDENTITY_MISMATCH"
REFUSAL_CURSOR_QUARANTINED = "PRODUCTION_CURSOR_QUARANTINED"
REFUSAL_FACTORY_CONTRACT = "PRODUCTION_SOURCE_FACTORY_CANNOT_RESUME"
REFUSAL_LEGACY_WEBSOCKET_DISCOVERY = "PRODUCTION_LEGACY_WEBSOCKET_DISCOVERY"
REFUSAL_TWO_DISCOVERY_OWNERS = "PRODUCTION_TWO_DISCOVERY_OWNERS"
REFUSAL_HEAD_MISMATCH = "PRODUCTION_REPOSITORY_HEAD_MISMATCH"
REFUSAL_HEAD_UNREADABLE = "PRODUCTION_REPOSITORY_HEAD_UNREADABLE"
REFUSAL_GAP_RECOVERY_MODE_ABSENT = "PRODUCTION_GAP_RECOVERY_MODE_ABSENT"
REFUSAL_GAP_RECOVERY_MODE_INVALID = "PRODUCTION_GAP_RECOVERY_MODE_INVALID"

PRODUCTION_REFUSAL_REASONS = (
    REFUSAL_PROVIDER_MODE_NOT_PAID,
    REFUSAL_CURSOR_STORE_ABSENT,
    REFUSAL_CURSOR_DIR_EPHEMERAL,
    REFUSAL_CURSOR_DIR_IS_RUN_DIR,
    REFUSAL_CURSOR_IDENTITY_MISMATCH,
    REFUSAL_CURSOR_QUARANTINED,
    REFUSAL_FACTORY_CONTRACT,
    REFUSAL_LEGACY_WEBSOCKET_DISCOVERY,
    REFUSAL_TWO_DISCOVERY_OWNERS,
    REFUSAL_HEAD_MISMATCH,
    REFUSAL_HEAD_UNREADABLE,
    REFUSAL_GAP_RECOVERY_MODE_ABSENT,
    REFUSAL_GAP_RECOVERY_MODE_INVALID,
)

#: Sentinel: the caller did not present a gap-recovery mode for evaluation at
#: all (legacy call sites and tests). ``None`` means the mode is genuinely
#: unconfigured, which the ARMED contract refuses.
GAP_RECOVERY_NOT_EVALUATED = "__GAP_RECOVERY_NOT_EVALUATED__"

#: Directory name fragments that mark a location as scratch/disposable. A
#: durable resume position placed in any of these silently resets whenever the
#: operator rotates a run, which is exactly how a cursor becomes decorative.
_EPHEMERAL_MARKERS = (
    "temp", "tmp", "pytest-", "basetemp", "scratch", "cache",
)


class ProductionContractError(RuntimeError):
    """The armed production configuration is not the cursor-aware gRPC path."""


@dataclass
class ProductionContractVerdict:
    """The full, redaction-safe outcome of one contract evaluation."""

    allowed: bool
    refusals: List[str] = field(default_factory=list)
    checks: Dict[str, Any] = field(default_factory=dict)

    def raise_if_refused(self) -> None:
        if not self.allowed:
            raise ProductionContractError(
                "PRODUCTION_GRPC_CONTRACT_REFUSED: " + ", ".join(self.refusals))


def directory_is_ephemeral(path: object) -> bool:
    """Would a durable cursor placed here fail to survive a normal run?

    Judged on the resolved path only -- never on its contents -- so this is a
    pure structural check that opens nothing.
    """

    if path is None:
        return True
    try:
        resolved = Path(str(path)).expanduser().resolve()
    except (OSError, ValueError, RuntimeError):
        return True
    parts = [part.lower() for part in resolved.parts]
    for part in parts:
        for marker in _EPHEMERAL_MARKERS:
            if marker in part:
                return True
    for variable in ("TEMP", "TMP", "TMPDIR"):
        raw = os.environ.get(variable)
        if not raw:
            continue
        try:
            base = Path(raw).expanduser().resolve()
        except (OSError, ValueError, RuntimeError):
            continue
        if resolved == base or base in resolved.parents:
            return True
    return False


def read_repository_head(repo_root: object) -> Optional[str]:
    """Return the current commit of ``repo_root``, or ``None`` if unreadable.

    Uses ``git rev-parse`` with no network access and no credential use.
    """

    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(repo_root), capture_output=True, text=True, timeout=15,
            check=False)
    except (OSError, ValueError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0:
        return None
    head = (completed.stdout or "").strip()
    if len(head) != 40 or not all(c in "0123456789abcdef" for c in head.lower()):
        return None
    return head.lower()


def evaluate_production_mode_precondition(
    *,
    require_production_grpc: bool,
    provider_mode: object,
    paid_provider_modes: Sequence[str],
    cursor_state_dir: object,
    out_dir: object,
    discovery_mode: Optional[str] = None,
) -> ProductionContractVerdict:
    """Decide the ARMED requirement BEFORE the provider-mode branch it polices.

    The 2026-07-20 re-audit recorded ``--require-production-grpc`` as silently
    inert: its only call site sat inside ``if paid_mode:``, the very condition
    it exists to require, and ``--provider-mode`` defaults to ``free_tier``.  An
    armed launcher that omitted one token therefore got no refusal, no cursor,
    no contract, an open outbound health gate and legacy websocket discovery --
    while remaining fully send-capable.  ``PROVIDER_MODE_NOT_PAID_GRPC`` was
    unreachable in production precisely when it mattered.

    This runs first, on argument values alone.  It opens nothing, reads no
    environment file and touches no credential, so it can be evaluated before a
    cursor store, a source factory, a channel or a stub exists.  The remaining
    checks that genuinely need constructed objects -- the cursor store's own
    state, the factory's resume contract and the repository HEAD -- stay in
    :func:`evaluate_production_grpc_contract`, which this does not replace.

    With the flag absent the generic development CLI keeps its historical
    permissive default and this allows everything.
    """

    refusals: List[str] = []
    checks: Dict[str, Any] = {
        "require_production_grpc": bool(require_production_grpc),
        "evaluated_before_provider_branch": True,
        "provider_mode": None if provider_mode is None else str(provider_mode),
    }
    if not require_production_grpc:
        checks["enforced"] = False
        return ProductionContractVerdict(allowed=True, refusals=[], checks=checks)
    checks["enforced"] = True

    # 1. the canonical paid/gRPC provider mode, exactly as the parser spells it
    mode_ok = provider_mode is not None and str(provider_mode) in tuple(
        paid_provider_modes)
    checks["provider_mode_is_paid_grpc"] = mode_ok
    if not mode_ok:
        refusals.append(REFUSAL_PROVIDER_MODE_NOT_PAID)

    # 2. an explicit, durable cursor state directory that is not the run dir
    ephemeral = directory_is_ephemeral(cursor_state_dir)
    checks["cursor_state_dir_ephemeral"] = ephemeral
    checks["cursor_state_dir_explicit"] = cursor_state_dir is not None
    if ephemeral:
        refusals.append(REFUSAL_CURSOR_DIR_EPHEMERAL)
    same_as_run_dir = False
    try:
        if cursor_state_dir is not None and out_dir is not None:
            same_as_run_dir = (
                Path(str(cursor_state_dir)).expanduser().resolve()
                == Path(str(out_dir)).expanduser().resolve())
    except (OSError, ValueError, RuntimeError):
        same_as_run_dir = True
    checks["cursor_state_dir_is_run_dir"] = same_as_run_dir
    if same_as_run_dir:
        refusals.append(REFUSAL_CURSOR_DIR_IS_RUN_DIR)

    # 3. exactly one discovery owner, and never the legacy websocket path
    legacy_ws = str(discovery_mode or "").strip().lower() in ("ws", "hybrid")
    checks["legacy_websocket_discovery_selected"] = legacy_ws
    checks["discovery_mode"] = discovery_mode
    if legacy_ws:
        refusals.append(REFUSAL_LEGACY_WEBSOCKET_DISCOVERY)
    fallback = str(provider_mode or "").strip().lower().endswith("with_fallback")
    checks["fallback_discovery_enabled"] = fallback
    if fallback:
        refusals.append(REFUSAL_TWO_DISCOVERY_OWNERS)

    return ProductionContractVerdict(
        allowed=not refusals, refusals=refusals, checks=checks)


def evaluate_production_grpc_contract(
    *,
    provider_mode: str,
    paid_provider_modes: Sequence[str],
    cursor_store: Any,
    cursor_state_dir: object,
    out_dir: object,
    source_factory: Any,
    discovery_mode: Optional[str] = None,
    fallback_discovery_enabled: bool = False,
    expected_head: Optional[str] = None,
    repo_root: object = None,
    actual_head: Optional[str] = None,
    gap_recovery_mode: object = GAP_RECOVERY_NOT_EVALUATED,
) -> ProductionContractVerdict:
    """Decide whether an ARMED production run may proceed.

    Every check is structural and offline.  The verdict lists every refusal
    rather than short-circuiting, so one startup attempt tells the operator
    everything that is wrong instead of one thing at a time.

    ``gap_recovery_mode`` participates only when the caller presents it (the
    armed session always does): ``None`` -- the launcher stated no recovery
    mode at all -- is refused, because a production launcher must not silently
    inherit an optimistic default for what happens when the provider refuses
    replay.  Legacy callers that omit the parameter entirely keep their exact
    historical verdict.
    """

    from PHX2.free_tier_producer.paid_provider import (
        SingleGrpcPumpSwapDiscovery,
    )

    refusals: List[str] = []
    checks: Dict[str, Any] = {}

    # 1. paid/gRPC provider mode explicitly enabled
    mode_ok = str(provider_mode) in tuple(paid_provider_modes)
    checks["provider_mode_is_paid_grpc"] = mode_ok
    checks["provider_mode"] = str(provider_mode)
    if not mode_ok:
        refusals.append(REFUSAL_PROVIDER_MODE_NOT_PAID)

    # 2. a cursor store actually exists
    checks["cursor_store_present"] = cursor_store is not None
    if cursor_store is None:
        refusals.append(REFUSAL_CURSOR_STORE_ABSENT)
    else:
        quarantined = bool(getattr(cursor_store, "quarantined", False))
        identity_ok = bool(
            getattr(cursor_store, "subscription_identity_matches", True))
        checks["cursor_quarantined"] = quarantined
        checks["cursor_identity_matches"] = identity_ok
        if quarantined:
            refusals.append(REFUSAL_CURSOR_QUARANTINED)
        if not identity_ok:
            refusals.append(REFUSAL_CURSOR_IDENTITY_MISMATCH)

    # 3. the cursor lives somewhere durable, and NOT in the disposable run dir
    ephemeral = directory_is_ephemeral(cursor_state_dir)
    checks["cursor_state_dir_ephemeral"] = ephemeral
    if ephemeral:
        refusals.append(REFUSAL_CURSOR_DIR_EPHEMERAL)
    same_as_run_dir = False
    try:
        if cursor_state_dir is not None and out_dir is not None:
            same_as_run_dir = (
                Path(str(cursor_state_dir)).expanduser().resolve()
                == Path(str(out_dir)).expanduser().resolve())
    except (OSError, ValueError, RuntimeError):
        same_as_run_dir = True
    checks["cursor_state_dir_is_run_dir"] = same_as_run_dir
    if same_as_run_dir:
        refusals.append(REFUSAL_CURSOR_DIR_IS_RUN_DIR)

    # 4. the factory can genuinely carry a resume position
    factory_ok = bool(
        source_factory is not None
        and SingleGrpcPumpSwapDiscovery._factory_accepts_cursor_kwargs(
            source_factory))
    checks["source_factory_is_cursor_aware"] = factory_ok
    if not factory_ok:
        refusals.append(REFUSAL_FACTORY_CONTRACT)

    # 5. exactly one discovery owner, and never the legacy websocket path
    legacy_ws = str(discovery_mode or "").strip().lower() in ("ws", "hybrid")
    checks["legacy_websocket_discovery_selected"] = legacy_ws
    checks["discovery_mode"] = discovery_mode
    if legacy_ws:
        refusals.append(REFUSAL_LEGACY_WEBSOCKET_DISCOVERY)
    checks["fallback_discovery_enabled"] = bool(fallback_discovery_enabled)
    if fallback_discovery_enabled:
        refusals.append(REFUSAL_TWO_DISCOVERY_OWNERS)

    # 5b. an explicit gap-recovery decision, when presented for evaluation
    if gap_recovery_mode is not GAP_RECOVERY_NOT_EVALUATED:
        checks["gap_recovery_mode"] = (
            None if gap_recovery_mode is None else str(gap_recovery_mode))
        if gap_recovery_mode is None:
            refusals.append(REFUSAL_GAP_RECOVERY_MODE_ABSENT)
        else:
            try:
                from PHX2.free_tier_producer.rpc_gap_recovery import (
                    GAP_RECOVERY_MODES,
                )
                valid = str(gap_recovery_mode) in GAP_RECOVERY_MODES
            except Exception:
                valid = False
            if not valid:
                refusals.append(REFUSAL_GAP_RECOVERY_MODE_INVALID)

    # 6. the exact tracked commit
    if expected_head:
        head = actual_head if actual_head is not None else read_repository_head(
            repo_root or Path(__file__).resolve().parents[2])
        checks["expected_head"] = str(expected_head).lower()
        checks["actual_head"] = head
        if head is None:
            refusals.append(REFUSAL_HEAD_UNREADABLE)
        elif head != str(expected_head).strip().lower():
            refusals.append(REFUSAL_HEAD_MISMATCH)
    else:
        checks["expected_head"] = None

    return ProductionContractVerdict(
        allowed=not refusals, refusals=refusals, checks=checks)


__all__ = (
    "ProductionContractError",
    "ProductionContractVerdict",
    "PRODUCTION_REFUSAL_REASONS",
    "REFUSAL_PROVIDER_MODE_NOT_PAID",
    "REFUSAL_CURSOR_STORE_ABSENT",
    "REFUSAL_CURSOR_DIR_EPHEMERAL",
    "REFUSAL_CURSOR_DIR_IS_RUN_DIR",
    "REFUSAL_CURSOR_IDENTITY_MISMATCH",
    "REFUSAL_CURSOR_QUARANTINED",
    "REFUSAL_FACTORY_CONTRACT",
    "REFUSAL_LEGACY_WEBSOCKET_DISCOVERY",
    "REFUSAL_TWO_DISCOVERY_OWNERS",
    "REFUSAL_HEAD_MISMATCH",
    "REFUSAL_HEAD_UNREADABLE",
    "REFUSAL_GAP_RECOVERY_MODE_ABSENT",
    "REFUSAL_GAP_RECOVERY_MODE_INVALID",
    "GAP_RECOVERY_NOT_EVALUATED",
    "directory_is_ephemeral",
    "read_repository_head",
    "evaluate_production_mode_precondition",
    "evaluate_production_grpc_contract",
)

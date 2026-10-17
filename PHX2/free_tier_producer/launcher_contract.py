"""The canonical armed-launch shape, checkable offline without running it.

The 2026-07-20 post-fix re-audit found the production wiring repair genuine but
**unreachable**: all three armed operator launchers passed an ``--out-dir`` and
an ``--ledger-path`` inside ``_FORBIDDEN_WRITE_ROOTS``, so the session refused
with exit 2 roughly 795 lines before the gRPC contract was ever evaluated.  Two
of the three additionally pinned a spent durable baseline that could not match
the ledger they named.  No operator command could execute the repaired path at
all.

The path-isolation guard is correct and is NOT weakened here.  The launchers
were pointing at the wrong tree; this module defines the right one, and makes
the whole argument vector checkable without starting anything:

``<root>\\state``   stable cursor/checkpoint state, survives a run rotation
``<root>\\ledger``  the canonical paid-primary ping dedupe ledger
``<root>\\runs``    disposable per-run output

Nothing here opens a socket, reads an environment file, touches a credential or
starts a process.  It inspects argument values only, so the same predicate can
be applied to a launcher's text long before that launcher is ever run.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

from PHX2.free_tier_producer.phx1_parity_policy import (
    normalize_alert_policy,
)

# The tracked module every armed launcher must execute. The out-of-repo
# ``production_live_session.py`` is deliberately NOT reachable from here.
TRACKED_PRODUCTION_MODULE = "PHX2.free_tier_producer.free_tier_session"

REPO_ROOT = r"C:\Users\BalaC\Downloads\Phoenix_PHX2"
REPO_PYTHON = r"C:\Users\BalaC\Downloads\Phoenix_PHX2\.venv\Scripts\python.exe"

#: The dedicated paid-primary runtime root. Chosen because it sits outside
#: every forbidden historical tree AND outside every ephemeral marker, so a
#: durable cursor placed here survives both a fresh run directory and a restart.
PAID_PRIMARY_RUNTIME_ROOT = r"C:\Users\BalaC\phx2_paid_primary_runtime"
CANONICAL_CURSOR_STATE_DIR = str(Path(PAID_PRIMARY_RUNTIME_ROOT) / "state")
CANONICAL_LEDGER_DIR = str(Path(PAID_PRIMARY_RUNTIME_ROOT) / "ledger")
CANONICAL_LEDGER_PATH = str(Path(CANONICAL_LEDGER_DIR) / "ping_dedupe.jsonl")
CANONICAL_RUNS_ROOT = str(Path(PAID_PRIMARY_RUNTIME_ROOT) / "runs")
CANONICAL_LOGS_ROOT = str(Path(PAID_PRIMARY_RUNTIME_ROOT) / "operator_logs")

#: Mirrors ``free_tier_session._FORBIDDEN_WRITE_ROOTS`` exactly. A test asserts
#: the two never drift apart; this copy exists so the predicate stays importable
#: without pulling in the session's full dependency graph.
FORBIDDEN_WRITE_ROOTS = (
    r"c:\users\balac\phx2_one_send_ceremony",
    r"c:\users\balac\phx2_capped_one_send_ceremony",
    r"c:\users\balac\phx2_production_private_live",
)

#: Directory fragments that make a location disposable. Kept identical in
#: meaning to ``production_grpc_contract._EPHEMERAL_MARKERS``.
_EPHEMERAL_MARKERS = ("temp", "tmp", "pytest-", "basetemp", "scratch", "cache")

CANONICAL_PROVIDER_MODE = "paid_primary"
CANONICAL_DISCOVERY_MODE = "polling"
CANONICAL_MIGRATION_SOURCE_MODE = "HELIUS_PRIMARY"
#: Production begins a new bounded live epoch at the current confirmed head.
#: Historical block replay stays retired from Helius-primary authority; exact
#: bounded Helius HTTP gap recovery supplements the live migration stream
#: after a proven discontinuity, and the bounded six-hour DexScreener
#: candidate backfill (startup recovery + periodic safety net) recovers
#: eligible candidates the live stream could not have seen.  DEX backfill is
#: candidate recovery, never migration-source authority.
CANONICAL_GAP_RECOVERY_MODE = "live_epoch"

#: The alert policy an armed production launcher must state explicitly, every
#: time, exactly once.  This is the deployment-contract layer: the durable
#: epoch identity treats BOTH policies as legitimate identities and requires an
#: authenticated handoff to change between them, while this constant is what
#: makes a production launcher that silently reverts to LEGACY refuse preflight.
CANONICAL_ALERT_POLICY_CLI = "phx1_parity"
CANONICAL_ALERT_POLICY = "PHX1_PARITY"

#: Placeholder standing in for the arm-gate confirmation token. The real value
#: is fetched by the launcher at run time, held in memory, and never written to
#: an argument fixture, a transcript or an artifact.
CONFIRM_TOKEN_PLACEHOLDER = "<CONFIRM_TOKEN>"

ARMED_LAUNCHERS = (
    "launch_pressure_24h_01.ps1",
    "launch_soak_02h_01.ps1",
    "launch_window_04.ps1",
)

#: Per-launcher run identity and bounds. The run id names the disposable output
#: directory only: durable state and the canonical ledger are shared and never
#: rotate with it.
LAUNCHER_PROFILES: Dict[str, Dict[str, Any]] = {
    "launch_pressure_24h_01.ps1": {
        "run_id": "paid_primary_pressure_24h_01",
        "max_runtime_seconds": "86400",
        "max_seed_runtime": "300",
    },
    "launch_soak_02h_01.ps1": {
        "run_id": "paid_primary_soak_02h_01",
        "max_runtime_seconds": "7200",
        "max_seed_runtime": "300",
    },
    "launch_window_04.ps1": {
        "run_id": "paid_primary_window_04",
        "max_runtime_seconds": "1800",
        "max_seed_runtime": "300",
    },
}

# Closed-set refusal reasons. No path fragment, endpoint, credential or raw
# exception ever reaches an artifact through these.
REFUSAL_MODULE_NOT_TRACKED = "LAUNCHER_MODULE_NOT_TRACKED"
REFUSAL_OUT_DIR_ABSENT = "LAUNCHER_OUT_DIR_ABSENT"
REFUSAL_OUT_DIR_FORBIDDEN = "LAUNCHER_OUT_DIR_FORBIDDEN_ROOT"
REFUSAL_OUT_DIR_NOT_CANONICAL = "LAUNCHER_OUT_DIR_NOT_UNDER_RUNS_ROOT"
REFUSAL_LEDGER_ABSENT = "LAUNCHER_LEDGER_PATH_ABSENT"
REFUSAL_LEDGER_FORBIDDEN = "LAUNCHER_LEDGER_PATH_FORBIDDEN_ROOT"
REFUSAL_LEDGER_NOT_CANONICAL = "LAUNCHER_LEDGER_PATH_NOT_CANONICAL"
REFUSAL_LEDGER_BASELINE_ABSENT = "LAUNCHER_LEDGER_BASELINE_ABSENT"
REFUSAL_LEDGER_BASELINE_MISMATCH = "LAUNCHER_LEDGER_BASELINE_MISMATCH"
REFUSAL_CURSOR_DIR_ABSENT = "LAUNCHER_CURSOR_STATE_DIR_ABSENT"
REFUSAL_CURSOR_DIR_FORBIDDEN = "LAUNCHER_CURSOR_STATE_DIR_FORBIDDEN_ROOT"
REFUSAL_CURSOR_DIR_UNSTABLE = "LAUNCHER_CURSOR_STATE_DIR_UNSTABLE"
REFUSAL_CURSOR_DIR_IS_OUT_DIR = "LAUNCHER_CURSOR_STATE_DIR_IS_OUT_DIR"
REFUSAL_PROVIDER_MODE_NOT_CANONICAL = "LAUNCHER_PROVIDER_MODE_NOT_CANONICAL"
REFUSAL_PRODUCTION_FLAG_ABSENT = "LAUNCHER_PRODUCTION_GRPC_FLAG_ABSENT"
REFUSAL_LEGACY_WEBSOCKET_DISCOVERY = "LAUNCHER_LEGACY_WEBSOCKET_DISCOVERY"
REFUSAL_HEAD_PIN_ABSENT = "LAUNCHER_EXPECTED_HEAD_ABSENT"
REFUSAL_HEAD_PIN_MISMATCH = "LAUNCHER_EXPECTED_HEAD_MISMATCH"
REFUSAL_GAP_RECOVERY_NOT_CANONICAL = "LAUNCHER_GAP_RECOVERY_MODE_NOT_CANONICAL"
REFUSAL_DEX_BACKFILL_ABSENT = "LAUNCHER_DEX_RESTART_BACKFILL_ABSENT"
REFUSAL_DEX_BACKFILL_PRESENT = "LAUNCHER_HELIUS_PRIMARY_DEX_BACKFILL_PRESENT"
REFUSAL_HISTORICAL_RPC_FLAG_PRESENT = "LAUNCHER_HISTORICAL_RPC_FLAG_PRESENT"
REFUSAL_SOURCE_MODE_ABSENT = "LAUNCHER_MIGRATION_SOURCE_MODE_ABSENT"
REFUSAL_SOURCE_MODE_NOT_CANONICAL = (
    "LAUNCHER_MIGRATION_SOURCE_MODE_NOT_CANONICAL"
)
REFUSAL_HELIUS_CONFIGURATION = "LAUNCHER_HELIUS_CONFIGURATION_REQUIRED"
REFUSAL_HELIUS_HTTP_RECOVERY = "LAUNCHER_HELIUS_HTTP_RECOVERY_REQUIRED"
REFUSAL_HELIUS_TIGHT_FILTER = "LAUNCHER_HELIUS_TIGHT_FILTER_REQUIRED"
REFUSAL_SEND_AUTHORITY_COUNT = "LAUNCHER_SEND_AUTHORITY_COUNT_NOT_ONE"
REFUSAL_CHAINSTACK_SHADOW_AUTHORITY = (
    "LAUNCHER_CHAINSTACK_SHADOW_CANDIDATE_AUTHORITY"
)
REFUSAL_CHAINSTACK_RUNTIME_ARGUMENT = (
    "LAUNCHER_HELIUS_ONLY_CHAINSTACK_RUNTIME_ARGUMENT"
)
REFUSAL_SOURCE_OWNER_COUNT = "LAUNCHER_SOURCE_OWNER_COUNT_NOT_ONE"
REFUSAL_TELEGRAM_OWNER_COUNT = "LAUNCHER_TELEGRAM_OWNER_COUNT_NOT_ONE"
REFUSAL_ALERT_POLICY_ABSENT = "LAUNCHER_ALERT_POLICY_ABSENT"
REFUSAL_ALERT_POLICY_NOT_CANONICAL = "LAUNCHER_ALERT_POLICY_NOT_CANONICAL"
REFUSAL_ALERT_POLICY_UNKNOWN = "LAUNCHER_ALERT_POLICY_UNKNOWN"
REFUSAL_ALERT_POLICY_COUNT = "LAUNCHER_ALERT_POLICY_COUNT_NOT_ONE"

LAUNCHER_REFUSAL_REASONS = (
    REFUSAL_MODULE_NOT_TRACKED,
    REFUSAL_OUT_DIR_ABSENT,
    REFUSAL_OUT_DIR_FORBIDDEN,
    REFUSAL_OUT_DIR_NOT_CANONICAL,
    REFUSAL_LEDGER_ABSENT,
    REFUSAL_LEDGER_FORBIDDEN,
    REFUSAL_LEDGER_NOT_CANONICAL,
    REFUSAL_LEDGER_BASELINE_ABSENT,
    REFUSAL_LEDGER_BASELINE_MISMATCH,
    REFUSAL_CURSOR_DIR_ABSENT,
    REFUSAL_CURSOR_DIR_FORBIDDEN,
    REFUSAL_CURSOR_DIR_UNSTABLE,
    REFUSAL_CURSOR_DIR_IS_OUT_DIR,
    REFUSAL_PROVIDER_MODE_NOT_CANONICAL,
    REFUSAL_PRODUCTION_FLAG_ABSENT,
    REFUSAL_LEGACY_WEBSOCKET_DISCOVERY,
    REFUSAL_HEAD_PIN_ABSENT,
    REFUSAL_HEAD_PIN_MISMATCH,
    REFUSAL_GAP_RECOVERY_NOT_CANONICAL,
    REFUSAL_DEX_BACKFILL_ABSENT,
    REFUSAL_DEX_BACKFILL_PRESENT,
    REFUSAL_HISTORICAL_RPC_FLAG_PRESENT,
    REFUSAL_SOURCE_MODE_ABSENT,
    REFUSAL_SOURCE_MODE_NOT_CANONICAL,
    REFUSAL_HELIUS_CONFIGURATION,
    REFUSAL_HELIUS_HTTP_RECOVERY,
    REFUSAL_HELIUS_TIGHT_FILTER,
    REFUSAL_ALERT_POLICY_ABSENT,
    REFUSAL_ALERT_POLICY_NOT_CANONICAL,
    REFUSAL_ALERT_POLICY_UNKNOWN,
    REFUSAL_ALERT_POLICY_COUNT,
    REFUSAL_SEND_AUTHORITY_COUNT,
    REFUSAL_CHAINSTACK_SHADOW_AUTHORITY,
    REFUSAL_CHAINSTACK_RUNTIME_ARGUMENT,
    REFUSAL_SOURCE_OWNER_COUNT,
    REFUSAL_TELEGRAM_OWNER_COUNT,
)

#: Flags carrying a value that must never be echoed into an artifact.
SECRET_VALUED_FLAGS = ("--confirm-token",)


@dataclass
class LauncherVerdict:
    """The full, redaction-safe outcome of one launcher-argument evaluation."""

    allowed: bool
    refusals: List[str] = field(default_factory=list)
    checks: Dict[str, Any] = field(default_factory=dict)


def path_is_forbidden(path: object) -> bool:
    """True iff ``path`` sits inside any protected historical tree."""

    if path is None:
        return False
    norm = os.path.normpath(os.path.abspath(str(path))).lower()
    return any(norm == root or norm.startswith(root + os.sep)
               for root in FORBIDDEN_WRITE_ROOTS)


def path_is_ephemeral(path: object) -> bool:
    """Would durable state placed here be lost on an ordinary run rotation?"""

    if path is None:
        return True
    try:
        resolved = Path(str(path)).expanduser().resolve()
    except (OSError, ValueError, RuntimeError):
        return True
    for part in (p.lower() for p in resolved.parts):
        if any(marker in part for marker in _EPHEMERAL_MARKERS):
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


def _same_path(left: object, right: object) -> bool:
    if left is None or right is None:
        return False
    try:
        return (Path(str(left)).expanduser().resolve()
                == Path(str(right)).expanduser().resolve())
    except (OSError, ValueError, RuntimeError):
        return False


def _is_under(child: object, parent: object) -> bool:
    try:
        child_path = Path(str(child)).expanduser().resolve()
        parent_path = Path(str(parent)).expanduser().resolve()
    except (OSError, ValueError, RuntimeError):
        return False
    return parent_path in child_path.parents


def canonical_launcher_arguments(
    *, launcher: str, expected_head: str, ledger_baseline: str,
    confirm_token: str = CONFIRM_TOKEN_PLACEHOLDER,
) -> List[str]:
    """The exact argument vector an armed launcher must pass, in order.

    Durable state (``--cursor-state-dir``) and the canonical ledger are shared
    across launchers by design; only ``--out-dir`` rotates per run.
    """

    profile = LAUNCHER_PROFILES[str(launcher)]
    out_dir = str(Path(CANONICAL_RUNS_ROOT) / profile["run_id"])
    return [
        "-u",
        "-m", TRACKED_PRODUCTION_MODULE,
        "--run",
        "--enable-telegram",
        "--ack-live-free-tier",
        "--i-understand-this-can-send",
        "--confirm-token", confirm_token,
        "--require-baseline", str(ledger_baseline),
        "--ledger-path", CANONICAL_LEDGER_PATH,
        "--env", str(Path(REPO_ROOT) / ".env"),
        "--expected-head", str(expected_head),
        # ---- canonical single-stream gRPC production shape ----
        "--provider-mode", CANONICAL_PROVIDER_MODE,
        "--discovery-mode", CANONICAL_DISCOVERY_MODE,
        "--alert-policy", CANONICAL_ALERT_POLICY_CLI,
        "--migration-source-mode", CANONICAL_MIGRATION_SOURCE_MODE,
        "--enable-helius-http-recovery",
        "--enable-dexscreener-restart-backfill",
        "--require-production-grpc",
        "--cursor-state-dir", CANONICAL_CURSOR_STATE_DIR,
        "--grpc-gap-recovery", CANONICAL_GAP_RECOVERY_MODE,
        "--max-runtime-seconds", profile["max_runtime_seconds"],
        "--max-seed-runtime", profile["max_seed_runtime"],
        "--out-dir", out_dir,
    ]


_VALUED_FLAGS = {
    "--confirm-token": "confirm_token",
    "--require-baseline": "require_baseline",
    "--ledger-path": "ledger_path",
    "--env": "env_path",
    "--expected-head": "expected_head",
    "--provider-mode": "provider_mode",
    "--discovery-mode": "discovery_mode",
    "--alert-policy": "alert_policy",
    "--migration-source-mode": "migration_source_mode",
    "--cursor-state-dir": "cursor_state_dir",
    "--grpc-gap-recovery": "grpc_gap_recovery",
    "--helius-parity-late-match-seconds": (
        "helius_parity_late_match_seconds"
    ),
    "--max-runtime-seconds": "max_runtime_seconds",
    "--max-seed-runtime": "max_seed_runtime",
    "--out-dir": "out_dir",
}

_BARE_FLAGS = {
    "--run": "run",
    "--enable-telegram": "enable_telegram",
    "--ack-live-free-tier": "ack_live_free_tier",
    "--i-understand-this-can-send": "arm_acknowledged",
    "--require-production-grpc": "require_production_grpc",
    "--enable-dexscreener-restart-backfill": "enable_dexscreener_restart_backfill",
    "--enable-helius-http-recovery": "enable_helius_http_recovery",
}


def parse_launcher_arguments(argv: Sequence[str]) -> Dict[str, Any]:
    """Structurally parse one effective argument vector. Opens nothing."""

    parsed: Dict[str, Any] = {
        name: None for name in _VALUED_FLAGS.values()}
    parsed.update({name: False for name in _BARE_FLAGS.values()})
    parsed["module"] = None
    # Every occurrence of a valued flag, in order. A repeated flag otherwise
    # silently keeps only its LAST value, which is exactly how a duplicated or
    # conflicting policy selection would slip past the contract.
    occurrences: Dict[str, List[str]] = {
        name: [] for name in _VALUED_FLAGS.values()}
    tokens = [str(t) for t in argv]
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token == "-m" and index + 1 < len(tokens):
            parsed["module"] = tokens[index + 1]
            index += 2
            continue
        if token in _VALUED_FLAGS and index + 1 < len(tokens):
            parsed[_VALUED_FLAGS[token]] = tokens[index + 1]
            occurrences[_VALUED_FLAGS[token]].append(tokens[index + 1])
            index += 2
            continue
        if token in _BARE_FLAGS:
            parsed[_BARE_FLAGS[token]] = True
        index += 1
    parsed["_occurrences"] = occurrences
    return parsed


def alert_policy_occurrences(argv: Sequence[str]) -> List[str]:
    """Every ``--alert-policy`` value in one argument vector, in order."""

    parsed = parse_launcher_arguments(argv)
    return list(parsed.get("_occurrences", {}).get("alert_policy", ()))


def validate_launcher_arguments(
    argv: Sequence[str], *, expected_head: Optional[str] = None,
    ledger_baseline_fn: Optional[Callable[[str], Optional[str]]] = None,
    helius_configured: Optional[bool] = None,
    tight_filter_locked: bool = True,
    source_owner_count: int = 1,
    send_authority_count: int = 1,
    chainstack_candidate_authority: bool = False,
    telegram_owner_count: int = 1,
) -> LauncherVerdict:
    """Would this argument vector reach the repaired gRPC path, or refuse?

    Lists every violation rather than short-circuiting, so one evaluation tells
    the operator everything that is wrong.  ``ledger_baseline_fn`` is injected
    so the caller decides whether the on-disk ledger is measured at all: the
    repository test runs fully hermetic, while the offline operator probe hands
    in a real digest reader.
    """

    parsed = parse_launcher_arguments(argv)
    refusals: List[str] = []
    checks: Dict[str, Any] = {
        "module": parsed["module"],
        "provider_mode": parsed["provider_mode"],
        "discovery_mode": parsed["discovery_mode"],
        "migration_source_mode": parsed["migration_source_mode"],
        "helius_http_recovery": bool(
            parsed["enable_helius_http_recovery"]
        ),
        "require_production_grpc": bool(parsed["require_production_grpc"]),
        "out_dir": parsed["out_dir"],
        "ledger_path": parsed["ledger_path"],
        "cursor_state_dir": parsed["cursor_state_dir"],
        "expected_head": parsed["expected_head"],
        "dexscreener_restart_backfill": bool(
            parsed["enable_dexscreener_restart_backfill"]),
    }

    # 1. the tracked repository module, never an out-of-repo runner
    if parsed["module"] != TRACKED_PRODUCTION_MODULE:
        refusals.append(REFUSAL_MODULE_NOT_TRACKED)

    # 2. the disposable run directory: present, allowed, under the runs root
    out_dir = parsed["out_dir"]
    out_forbidden = path_is_forbidden(out_dir)
    checks["out_dir_forbidden"] = out_forbidden
    if out_dir is None:
        refusals.append(REFUSAL_OUT_DIR_ABSENT)
    else:
        if out_forbidden:
            refusals.append(REFUSAL_OUT_DIR_FORBIDDEN)
        if not _is_under(out_dir, CANONICAL_RUNS_ROOT):
            refusals.append(REFUSAL_OUT_DIR_NOT_CANONICAL)

    # 3. the canonical ledger, and the baseline that must match it
    ledger = parsed["ledger_path"]
    ledger_forbidden = path_is_forbidden(ledger)
    checks["ledger_forbidden"] = ledger_forbidden
    if ledger is None:
        refusals.append(REFUSAL_LEDGER_ABSENT)
    else:
        if ledger_forbidden:
            refusals.append(REFUSAL_LEDGER_FORBIDDEN)
        if not _same_path(ledger, CANONICAL_LEDGER_PATH):
            refusals.append(REFUSAL_LEDGER_NOT_CANONICAL)

    baseline = parsed["require_baseline"]
    checks["ledger_baseline_declared"] = baseline is not None
    baseline_matches = False
    if baseline is None:
        refusals.append(REFUSAL_LEDGER_BASELINE_ABSENT)
    elif ledger_baseline_fn is not None and ledger is not None:
        try:
            observed = ledger_baseline_fn(ledger)
        except Exception:
            observed = None
        baseline_matches = bool(observed is not None and str(observed) == str(baseline))
        if not baseline_matches:
            refusals.append(REFUSAL_LEDGER_BASELINE_MISMATCH)
    else:
        # Structural only: the declared baseline shape is checkable offline.
        parts = str(baseline).split(":")
        baseline_matches = (
            len(parts) == 3 and len(parts[0]) == 64
            and parts[1].isdigit() and parts[2].isdigit())
        if not baseline_matches:
            refusals.append(REFUSAL_LEDGER_BASELINE_MISMATCH)
    checks["ledger_baseline_matches"] = baseline_matches

    # 4. durable cursor state: explicit, stable, allowed, never the run dir
    cursor_dir = parsed["cursor_state_dir"]
    stable = cursor_dir is not None and not path_is_ephemeral(cursor_dir)
    checks["cursor_state_dir_stable"] = stable
    is_out_dir = _same_path(cursor_dir, out_dir)
    checks["cursor_state_dir_is_out_dir"] = is_out_dir
    if cursor_dir is None:
        refusals.append(REFUSAL_CURSOR_DIR_ABSENT)
    else:
        if path_is_forbidden(cursor_dir):
            refusals.append(REFUSAL_CURSOR_DIR_FORBIDDEN)
        if not stable:
            refusals.append(REFUSAL_CURSOR_DIR_UNSTABLE)
        if is_out_dir:
            refusals.append(REFUSAL_CURSOR_DIR_IS_OUT_DIR)

    # 5. the armed production contract, stated explicitly every time
    if str(parsed["provider_mode"] or "") != CANONICAL_PROVIDER_MODE:
        refusals.append(REFUSAL_PROVIDER_MODE_NOT_CANONICAL)
    if not parsed["require_production_grpc"]:
        refusals.append(REFUSAL_PRODUCTION_FLAG_ABSENT)
    if str(parsed["discovery_mode"] or "").strip().lower() in ("ws", "hybrid"):
        refusals.append(REFUSAL_LEGACY_WEBSOCKET_DISCOVERY)
    if parsed["migration_source_mode"] is None:
        refusals.append(REFUSAL_SOURCE_MODE_ABSENT)
    elif (
        str(parsed["migration_source_mode"]).strip().upper()
        != CANONICAL_MIGRATION_SOURCE_MODE
    ):
        refusals.append(REFUSAL_SOURCE_MODE_NOT_CANONICAL)

    # 5b. the named alert policy: stated explicitly, exactly once, canonical.
    # Missing, duplicated, conflicting and unknown are four distinct failures
    # and are reported separately so the operator sees which one applies.
    alert_values = list(
        parsed.get("_occurrences", {}).get("alert_policy", ()))
    checks["alert_policy"] = parsed["alert_policy"]
    checks["alert_policy_count"] = len(alert_values)
    checks["alert_policy_values"] = list(alert_values)
    if not alert_values:
        refusals.append(REFUSAL_ALERT_POLICY_ABSENT)
    else:
        if len(alert_values) != 1:
            refusals.append(REFUSAL_ALERT_POLICY_COUNT)
        for value in alert_values:
            try:
                normalized = normalize_alert_policy(str(value).strip())
            except ValueError:
                if REFUSAL_ALERT_POLICY_UNKNOWN not in refusals:
                    refusals.append(REFUSAL_ALERT_POLICY_UNKNOWN)
                continue
            if normalized != CANONICAL_ALERT_POLICY \
                    and REFUSAL_ALERT_POLICY_NOT_CANONICAL not in refusals:
                refusals.append(REFUSAL_ALERT_POLICY_NOT_CANONICAL)
    if helius_configured is False:
        refusals.append(REFUSAL_HELIUS_CONFIGURATION)
    if not parsed["enable_helius_http_recovery"]:
        refusals.append(REFUSAL_HELIUS_HTTP_RECOVERY)
    if not tight_filter_locked:
        refusals.append(REFUSAL_HELIUS_TIGHT_FILTER)
    if int(send_authority_count) != 1:
        refusals.append(REFUSAL_SEND_AUTHORITY_COUNT)
    if int(source_owner_count) != 1:
        refusals.append(REFUSAL_SOURCE_OWNER_COUNT)
    if chainstack_candidate_authority:
        refusals.append(REFUSAL_CHAINSTACK_SHADOW_AUTHORITY)
    chainstack_runtime_arguments = [
        str(token) for token in argv
        if (
            str(token) == "--helius-parity-late-match-seconds"
            or str(token).startswith("--chainstack")
        )
    ]
    checks["chainstack_runtime_arguments_present"] = bool(
        chainstack_runtime_arguments
    )
    if chainstack_runtime_arguments:
        refusals.append(REFUSAL_CHAINSTACK_RUNTIME_ARGUMENT)
    if int(telegram_owner_count) != 1:
        refusals.append(REFUSAL_TELEGRAM_OWNER_COUNT)
    if sum(
        1 for token in argv if str(token) == "--enable-telegram"
    ) != 1:
        refusals.append(REFUSAL_TELEGRAM_OWNER_COUNT)
    # 5b. the gap-recovery decision, stated explicitly every time
    checks["grpc_gap_recovery"] = parsed["grpc_gap_recovery"]
    if str(parsed["grpc_gap_recovery"] or "") != CANONICAL_GAP_RECOVERY_MODE:
        refusals.append(REFUSAL_GAP_RECOVERY_NOT_CANONICAL)
    # Bounded six-hour DEX candidate recovery is part of the armed
    # Helius-primary production contract (startup recovery + periodic safety
    # net); its absence is the refusal now.  Historical RPC replay stays
    # forbidden below.
    if not parsed["enable_dexscreener_restart_backfill"]:
        refusals.append(REFUSAL_DEX_BACKFILL_ABSENT)
    historical_rpc_flags = [
        token for token in argv
        if str(token).startswith("--rpc-recovery-")]
    checks["historical_rpc_flags_present"] = bool(historical_rpc_flags)
    if historical_rpc_flags:
        refusals.append(REFUSAL_HISTORICAL_RPC_FLAG_PRESENT)

    # 6. the exact tracked commit
    head_matches = False
    if parsed["expected_head"] is None:
        refusals.append(REFUSAL_HEAD_PIN_ABSENT)
    elif expected_head is not None:
        head_matches = (str(parsed["expected_head"]).strip().lower()
                        == str(expected_head).strip().lower())
        if not head_matches:
            refusals.append(REFUSAL_HEAD_PIN_MISMATCH)
    else:
        head_matches = len(str(parsed["expected_head"])) == 40
    checks["expected_head_matches"] = head_matches

    return LauncherVerdict(
        allowed=not refusals, refusals=refusals, checks=checks)


def redact_launcher_arguments(argv: Sequence[str]) -> List[str]:
    """A copy safe to write into an artifact: secret-valued flags masked."""

    tokens = [str(t) for t in argv]
    out: List[str] = []
    index = 0
    while index < len(tokens):
        token = tokens[index]
        out.append(token)
        if token in SECRET_VALUED_FLAGS and index + 1 < len(tokens):
            out.append("REDACTED")
            index += 2
            continue
        index += 1
    return out


__all__ = (
    "TRACKED_PRODUCTION_MODULE",
    "REPO_ROOT",
    "REPO_PYTHON",
    "PAID_PRIMARY_RUNTIME_ROOT",
    "CANONICAL_CURSOR_STATE_DIR",
    "CANONICAL_LEDGER_DIR",
    "CANONICAL_LEDGER_PATH",
    "CANONICAL_RUNS_ROOT",
    "CANONICAL_LOGS_ROOT",
    "CANONICAL_PROVIDER_MODE",
    "CANONICAL_DISCOVERY_MODE",
    "CANONICAL_MIGRATION_SOURCE_MODE",
    "CANONICAL_GAP_RECOVERY_MODE",
    "CANONICAL_ALERT_POLICY",
    "CANONICAL_ALERT_POLICY_CLI",
    "CONFIRM_TOKEN_PLACEHOLDER",
    "FORBIDDEN_WRITE_ROOTS",
    "ARMED_LAUNCHERS",
    "LAUNCHER_PROFILES",
    "LAUNCHER_REFUSAL_REASONS",
    "SECRET_VALUED_FLAGS",
    "LauncherVerdict",
    "path_is_forbidden",
    "path_is_ephemeral",
    "canonical_launcher_arguments",
    "parse_launcher_arguments",
    "alert_policy_occurrences",
    "validate_launcher_arguments",
    "redact_launcher_arguments",
)

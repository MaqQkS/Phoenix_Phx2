"""Offline, report-only preflight for a separately authorized paper canary.

No producer, engine, transport, credential loader, or process launcher is imported.
Success verifies a local plan; it does not authorize or start a live session.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
from typing import Any, Sequence

from PHX2.paper_trading.config import STRATEGY_BALA_PLAN, load_config
from PHX2.paper_trading.ledger import APPEND_FILES, MAX_STATE_BYTES, STATE_FILE


SCHEMA = "PHX2_PAPER_PREFLIGHT_V1"
MAX_PREFLIGHT_INPUT_FILES = 4096
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}\Z")
_HEX40 = re.compile(r"[0-9a-f]{40}\Z")
_HEX64 = re.compile(r"[0-9a-f]{64}\Z")
_WINDOWS_RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}


class PreflightError(ValueError):
    """Closed reason token: never expose config values or subprocess stderr."""


def _git(repo: Path, *args: str) -> bytes:
    env = dict(os.environ, GIT_OPTIONAL_LOCKS="0")
    result = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, env=env,
        timeout=30, check=False,
    )
    if result.returncode:
        raise PreflightError("LOCAL_GIT_READ_FAILED")
    return result.stdout


def _is_code_file(name: str) -> bool:
    path = Path(name)
    return (
        (name.startswith("PHX2/") and path.suffix in {".py", ".ps1"})
        or path.name in {"pyproject.toml", "pytest.ini"}
        or (path.name.startswith("requirements") and path.suffix == ".txt")
    )


def code_identity(repo: Path) -> dict[str, Any]:
    """Hash tracked and non-ignored untracked source, including deletions.

    This is a source digest, not a runtime-data/config/secret digest. It includes
    test and launcher code, and captures staged/unstaged contents as on disk.
    Recompute immediately before a future activation; a branch name is not a pin.
    """
    repo = repo.resolve(strict=True)
    head = _git(repo, "rev-parse", "HEAD").decode("ascii").strip()
    if not _HEX40.fullmatch(head):
        raise PreflightError("LOCAL_HEAD_INVALID")
    listing = _git(repo, "ls-files", "-z", "--cached", "--others", "--exclude-standard")
    names = sorted({n.decode("utf-8") for n in listing.split(b"\0") if n})
    names = [n for n in names if _is_code_file(n)]
    digest = hashlib.sha256(b"PHX2_SOURCE_DIGEST_V1\0")
    for name in names:
        relative = Path(name)
        if relative.is_absolute() or ".." in relative.parts:
            raise PreflightError("SOURCE_PATH_INVALID")
        path = repo / relative
        if path.is_symlink() or not path.resolve().is_relative_to(repo):
            raise PreflightError("SOURCE_PATH_ESCAPE")
        digest.update(name.encode("utf-8") + b"\0")
        digest.update(hashlib.sha256(path.read_bytes()).digest() if path.is_file() else b"DELETED")
    # Only source pathspecs: no data, .env, private configuration, or raw logs.
    changed = _git(repo, "status", "--porcelain=v1", "-z", "--untracked-files=all", "--",
                   ":(glob)PHX2/**/*.py", ":(glob)PHX2/**/*.ps1", "pytest.ini",
                   "pyproject.toml", ":(glob)**/requirements*.txt")
    return {"head": head, "source_sha256": digest.hexdigest(),
            "source_file_count": len(names), "source_dirty": bool(changed)}


def _safe_path(text: str, *, existing: bool = False) -> Path:
    if not text or any(c in text for c in "*?[]\r\n\0"):
        raise PreflightError("PATH_REQUIRES_EXACT_LOCAL_SELECTION")
    path = Path(text)
    # Reject PHX1 before any metadata/read; do not follow a symlink to it either.
    if "phoenix_bot" in {part.lower() for part in path.parts}:
        raise PreflightError("PHX1_PATH_FORBIDDEN")
    if str(path).startswith(("\\\\", "//")):
        raise PreflightError("NETWORK_PATH_FORBIDDEN")
    resolved = path.resolve(strict=existing)
    if "phoenix_bot" in {part.lower() for part in resolved.parts}:
        raise PreflightError("PHX1_PATH_FORBIDDEN")
    if {part.lower() for part in resolved.parts} & {".git", ".agents", ".codex", ".aws"}:
        raise PreflightError("PROTECTED_PATH_FORBIDDEN")
    if resolved.suffix.lower() in {".db", ".sqlite", ".sqlite3"}:
        raise PreflightError("DATABASE_PATH_FORBIDDEN")
    return resolved


def _overlaps(left: Path, right: Path) -> bool:
    return left == right or left.is_relative_to(right) or right.is_relative_to(left)


def inspect_source(root: Path, *, file_budget: int | None = None) -> dict[str, Any]:
    """Stream direct producer entries, failing before materializing an overflow.

    The caller shares one file budget across every selected root. No input
    content is read here, and scandir is closed immediately on a refusal.
    """
    remaining = MAX_PREFLIGHT_INPUT_FILES if file_budget is None else file_budget
    if not root.is_dir():
        raise PreflightError("SOURCE_ROOT_MUST_EXIST_AS_DIRECTORY")
    existing = 0

    def inspect_file(path: Path) -> None:
        nonlocal existing
        if path.is_symlink() or path.is_junction() or not path.resolve().is_relative_to(root):
            raise PreflightError("INPUT_PATH_ESCAPE")
        if path.exists():
            if not path.is_file():
                raise PreflightError("INPUT_NOT_REGULAR_FILE")
            existing += 1
            if existing > remaining:
                raise PreflightError("PAPER_INPUT_FILE_LIMIT_EXCEEDED")

    inspect_file(root / "pricing_tail.jsonl")
    candidate_dir = root / "candidates"
    if candidate_dir.exists():
        if not candidate_dir.is_dir() or candidate_dir.is_symlink() or candidate_dir.resolve() != candidate_dir:
            raise PreflightError("CANDIDATE_DIRECTORY_ESCAPE")
        with os.scandir(candidate_dir) as entries:
            for entry in entries:
                if entry.name.endswith(".jsonl"):
                    inspect_file(candidate_dir / entry.name)
    return {"selection": ["pricing_tail.jsonl", "candidates/*.jsonl (direct children only)"],
            "existing_stream_files": existing, "empty_before_producer_start": existing == 0,
            "record_types": ["BUILD30_CANDIDATE_RECHECK", "FREE_TIER_PRICING_TAIL"]}


def _bounded_int(value: Any, low: int, high: int) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and low <= value <= high


def inspect_resume(run_dir: Path, sources: list[Path], *, config_digest: str,
                   allow_input_rollover: bool) -> dict[str, Any]:
    """Inspect canonical binding and bounded input identities without mutating.

    Only closed status/count fields are returned. State contents and input
    prefixes are never output. The runtime still rechecks under its own lease.
    """
    result = {"existing_run_directory": run_dir.exists(), "stable_run_id": run_dir.name,
              "requires_checkpoint_config_and_source_identity_match": True,
              "canonical_state_max_bytes": MAX_STATE_BYTES,
              "maximum_source_roots": 16, "selected_source_roots": len(sources),
              "rollover_requested": allow_input_rollover,
              "input_binding": "NEW_RUN", "consumed_inputs_verified": 0}
    path = run_dir / STATE_FILE
    if path.is_symlink() or path.is_junction() or path.resolve().parent != run_dir:
        raise PreflightError("PAPER_STATE_PATH_REFUSED")
    if not path.exists():
        for name in APPEND_FILES:
            legacy = run_dir / name
            if legacy.is_symlink() or legacy.is_junction():
                raise PreflightError("PAPER_STATE_PATH_REFUSED")
            if legacy.exists() and legacy.stat().st_size:
                raise PreflightError("PAPER_LEGACY_STATE_REQUIRES_REVIEWED_MIGRATION")
        return result
    if path.stat().st_size > MAX_STATE_BYTES:
        raise PreflightError("PAPER_CANONICAL_STATE_SIZE_LIMIT")
    try:
        with path.open("rb") as stream:
            raw = stream.read(MAX_STATE_BYTES + 1)
        if len(raw) > MAX_STATE_BYTES:
            raise PreflightError("PAPER_CANONICAL_STATE_SIZE_LIMIT")
        saved = json.loads(raw)
    except PreflightError:
        raise
    except (OSError, ValueError, RecursionError):
        raise PreflightError("PAPER_CANONICAL_STATE_UNREADABLE") from None
    if (not isinstance(saved, dict) or saved.get("schema_version") != "phx2_paper_state_v1"
            or saved.get("run_id") != run_dir.name or saved.get("config_digest") != config_digest
            or saved.get("mode") != "LIVE_PAPER"):
        raise PreflightError("PAPER_RESUME_IDENTITY_MISMATCH")
    checkpoint = saved.get("source_checkpoint") or {}
    if not isinstance(checkpoint, dict):
        raise PreflightError("PAPER_CHECKPOINT_INVALID")
    selected = {"paths": sorted(os.path.normcase(os.path.abspath(str(p))) for p in sources),
                "producer_streams_only": True,
                "include_kinds": ["BUILD30_CANDIDATE_RECHECK", "FREE_TIER_PRICING_TAIL"]}
    prior = checkpoint.get("selection")
    if prior is not None and prior != selected:
        rollover = (allow_input_rollover and isinstance(prior, dict)
                    and prior.get("producer_streams_only") == selected["producer_streams_only"]
                    and prior.get("include_kinds") == selected["include_kinds"]
                    and isinstance(prior.get("paths"), list)
                    and all(isinstance(p, str) for p in prior["paths"])
                    and set(prior["paths"]) < set(selected["paths"]))
        if not rollover:
            raise PreflightError("PAPER_INPUT_SELECTION_MISMATCH")
        result["input_binding"] = "EXPLICIT_ADDITIVE_ROLLOVER"
    elif prior is None and (checkpoint.get("offsets") or checkpoint.get("files")):
        raise PreflightError("PAPER_INPUT_SELECTION_MISSING")
    else:
        result["input_binding"] = "MATCHED" if prior is not None else "UNCONSUMED_CANONICAL_STATE"
    files = checkpoint.get("files") or {}
    offsets = checkpoint.get("offsets") or {}
    if not isinstance(files, dict) or not isinstance(offsets, dict):
        raise PreflightError("PAPER_CHECKPOINT_INVALID")
    for name in set(files) | set(offsets):
        if not isinstance(name, str):
            raise PreflightError("PAPER_CHECKPOINT_INVALID")
        source_file = _safe_path(name)
        if not any(source_file == root / "pricing_tail.jsonl"
                   or (source_file.parent == root / "candidates" and source_file.suffix == ".jsonl")
                   for root in sources):
            raise PreflightError("PAPER_CHECKPOINT_INPUT_OUTSIDE_SELECTION")
        if not source_file.is_file():
            raise PreflightError("PAPER_CHECKPOINTED_INPUT_MISSING")
        offset = offsets.get(name, 0)
        prior_file = files.get(name)
        if not _bounded_int(offset, 0, 2**63 - 1) or not isinstance(prior_file, dict):
            raise PreflightError("PAPER_CHECKPOINT_INVALID")
        anchor_size = prior_file.get("anchor_size")
        if not _bounded_int(anchor_size, 0, 256):
            raise PreflightError("PAPER_CHECKPOINT_INVALID")
        with source_file.open("rb") as stream:
            stat = os.fstat(stream.fileno())
            current_file = {"device": stat.st_dev, "inode": stat.st_ino,
                            "anchor_size": anchor_size,
                            "anchor": hashlib.sha256(stream.read(anchor_size)).hexdigest()}
        if stat.st_size < offset or prior_file != current_file:
            raise PreflightError("PAPER_INPUT_REPLACED_OR_TRUNCATED")
        result["consumed_inputs_verified"] += 1
    return result


def build_plan(args: argparse.Namespace, *, identity: dict[str, Any] | None = None) -> dict[str, Any]:
    reasons: list[str] = []
    plan: dict[str, Any] = {
        "schema": SCHEMA, "status": "BLOCKED", "mode": "OFFLINE_PLAN_ONLY",
        "activation_authorized": False, "processes_started": 0, "network_allowed": False,
        "telegram_enabled": False, "credentials_loaded": False, "reasons": reasons,
    }
    try:
        repo = _safe_path(args.repo, existing=True)
        identity = identity if identity is not None else code_identity(repo)
        plan["code"] = identity
        if not args.reviewed_head or not _HEX40.fullmatch(args.reviewed_head) or args.reviewed_head != identity["head"]:
            reasons.append("REVIEWED_HEAD_REQUIRED_OR_MISMATCH")
        if (not args.reviewed_source_sha256 or not _HEX64.fullmatch(args.reviewed_source_sha256)
                or args.reviewed_source_sha256 != identity["source_sha256"]):
            reasons.append("REVIEWED_SOURCE_DIGEST_REQUIRED_OR_MISMATCH")
        if not _ID.fullmatch(args.run_id) or args.run_id.upper() in _WINDOWS_RESERVED:
            raise PreflightError("STABLE_RUN_ID_INVALID")
        source_texts = [args.source_root, *getattr(args, "additional_source_root", [])]
        sources = [_safe_path(text, existing=True) for text in source_texts]
        if any(Path(text).is_symlink() or Path(text).is_junction() for text in source_texts):
            raise PreflightError("INPUT_PATH_ESCAPE")
        if not 1 <= len(sources) <= 16 or len(set(sources)) != len(sources):
            raise PreflightError("PAPER_INPUT_SELECTION_INVALID")
        if any(_overlaps(left, right) for i, left in enumerate(sources) for right in sources[i + 1:]):
            raise PreflightError("PAPER_INPUT_ROOTS_OVERLAP")
        output = _safe_path(args.out_root)
        config_path = _safe_path(args.config, existing=True)
        run_dir = output / args.run_id
        if any(_overlaps(source, output) for source in sources):
            raise PreflightError("INPUT_OUTPUT_OVERLAP")
        if (output.exists() and not output.is_dir()) or (run_dir.exists() and not run_dir.is_dir()):
            raise PreflightError("PAPER_OUTPUT_MUST_BE_DIRECTORY")
        if not config_path.is_file() or config_path.suffix.lower() != ".json":
            raise PreflightError("CONFIG_MUST_BE_JSON_FILE")
        if config_path.stat().st_size > 1_000_000:
            raise PreflightError("CONFIG_TOO_LARGE")
        inspected_sources = []
        remaining_files = MAX_PREFLIGHT_INPUT_FILES
        for source in sources:
            inspected = inspect_source(source, file_budget=remaining_files)
            inspected_sources.append(inspected)
            remaining_files -= inspected["existing_stream_files"]
        plan["inputs"] = dict(inspected_sources[0])
        plan["inputs"]["source_root_count"] = len(sources)
        plan["inputs"]["aggregate_stream_file_limit"] = MAX_PREFLIGHT_INPUT_FILES
        plan["inputs"]["existing_stream_files"] = sum(item["existing_stream_files"] for item in inspected_sources)
        plan["inputs"]["empty_before_producer_start"] = not plan["inputs"]["existing_stream_files"]
        # Parse only the paper config model. Never load .env or print arbitrary
        # parser exception text (unknown keys can contain user-controlled text).
        try:
            config = load_config(config_path)
        except Exception:
            raise PreflightError("PAPER_CONFIG_INVALID") from None
        enabled = config.enabled_strategies()
        bala = [strategy for strategy in enabled if strategy.strategy_type == STRATEGY_BALA_PLAN]
        if not bala:
            reasons.append("ENABLED_BALA_STRATEGY_REQUIRED")
        if any(strategy.params.get("initials_recovery_multiple") != 1.35
               or strategy.params.get("take_profit_pct") is not None
               or strategy.params.get("runner_trailing_stop_pct") != 0.30 for strategy in bala):
            reasons.append("BALA_RECOVERY_POLICY_MISMATCH")
        if any(not _bounded_int(strategy.max_open_positions, 1, 1000) for strategy in enabled):
            reasons.append("STRATEGY_EXPOSURE_MUST_BE_BOUNDED")
            exposure = None
        else:
            exposure = sum(strategy.max_open_positions for strategy in enabled)
        if not _bounded_int(args.tail_capacity, 1, 1000):
            reasons.append("TAIL_CAPACITY_REQUIRED")
        elif exposure is not None and exposure > args.tail_capacity:
            reasons.append("PAPER_EXPOSURE_EXCEEDS_TAIL_CAPACITY")
        market = config.market_sim
        values = (market.fee_bps, market.base_slippage_bps,
                  market.impact_bps_per_pct_of_lp, market.max_impact_bps)
        if any(not isinstance(v, (int, float)) or not math.isfinite(v) or v < 0 for v in values):
            reasons.append("FILL_COSTS_INVALID")
        plan["paper_policy"] = {
            "bala_strategy_count": len(bala), "enabled_strategy_count": len(enabled),
            "max_unique_open_positions_worst_case": exposure, "tail_capacity": args.tail_capacity,
            "initials_recovery_multiple": 1.35, "take_profit_pct": None,
            "runner_trailing_stop_pct": 0.30,
            "policy_matches": not any(r in reasons for r in ("ENABLED_BALA_STRATEGY_REQUIRED", "BALA_RECOVERY_POLICY_MISMATCH")),
            "recovery_basis": "NET_FULL_COST_AFTER_SIMULATED_EXIT_FEES_SLIPPAGE_IMPACT",
            "shutdown_policy": "LEAVE_OPEN_AND_RESUME",
            "behavioral_config_digest": config.config_digest(),
        }
        if not _bounded_int(args.max_runtime_seconds, 1, 3600):
            reasons.append("CANARY_RUNTIME_BUDGET_REQUIRED_1_TO_3600_SECONDS")
        if not _bounded_int(args.max_market_requests, 1, 10000):
            reasons.append("MARKET_REQUEST_BUDGET_REQUIRED_1_TO_10000")
        if not _bounded_int(args.helius_max_raw_bytes, 1, 100000000):
            reasons.append("HELIUS_BYTE_BUDGET_REQUIRED_1_TO_100000000")
        if not _bounded_int(args.max_discovery_messages, 0, 100) or not _bounded_int(args.max_paper_messages, 0, 20):
            reasons.append("SEPARATE_MESSAGE_BUDGETS_REQUIRED_DISCOVERY_0_TO_100_PAPER_0_TO_20")
        elif args.max_discovery_messages + args.max_paper_messages > 0:
            if not args.destination_alias or not _ID.fullmatch(args.destination_alias):
                reasons.append("REVIEWED_PRIVATE_DESTINATION_ALIAS_REQUIRED")
        if args.destination_alias and not _ID.fullmatch(args.destination_alias):
            reasons.append("DESTINATION_ALIAS_INVALID")
        plan["proposed_budgets"] = {
            "runtime_seconds": args.max_runtime_seconds,
            "market_requests": args.max_market_requests,
            "separate_startup_credential_probe_requests": 1,
            "helius_raw_response_bytes": args.helius_max_raw_bytes,
            "discovery_messages": args.max_discovery_messages,
            "paper_messages": args.max_paper_messages,
            "destination_selected": bool(args.destination_alias and _ID.fullmatch(args.destination_alias)),
            "approval_state": "PENDING_SEPARATE_LIVE_AUTHORIZATION",
        }
        plan["ownership"] = {
            "producer": "ONE_SEPARATELY_OWNED_PROCESS_NEVER_STARTED_BY_PAPER",
            "paper": "ONE_PAPER_RUN_LEASE_PER_STABLE_RUN_DIRECTORY",
            "shared_feedback": "<paper-run>/paper_state.json",
            "producer_required_options": ["--paper-state-file <paper-run>/paper_state.json", "--paper-coverage-required"],
            "paper_required_options": ["--producer-streams-only", "--run-id <stable-run-id>", "--out-root <paper-output>", "--max-runtime-seconds <reviewed-seconds>", "--stop-file <paper-run>/STOP"],
            "telegram_default": "DURABLE_OUTBOX_ONLY",
        }
        # Inert documentation only. Producer max-sends-per-run=0 means unlimited,
        # so a proposed zero budget must instead keep the transport disabled.
        plan["inactive_runtime_option_map"] = {
            "producer": {
                "--paper-state-file": "<paper-run>/paper_state.json",
                "--paper-coverage-required": True,
                "--tail-max-tracked": args.tail_capacity,
                "--max-runtime-seconds": args.max_runtime_seconds,
                "--max-market-requests-total": args.max_market_requests,
                "--max-market-calls-total": args.max_market_requests,
                "--helius-max-raw-bytes": args.helius_max_raw_bytes,
                "--enable-telegram": False,
            },
            "paper": {
                "--inputs": "<all-prior-producer-roots-plus-any-reviewed-new-root>",
                "--allow-input-rollover": bool(getattr(args, "allow_input_rollover", False)),
                "--producer-streams-only": True,
                "--run-id": args.run_id,
                "--out-root": "<selected-paper-output>",
                "--stop-file": "<paper-run>/STOP",
                "--reviewed-head": identity["head"],
                "--reviewed-source-digest": identity["source_sha256"],
                "--max-runtime-seconds": args.max_runtime_seconds,
                "--max-paper-messages": 0,
                "--enable-paper-telegram": False,
            },
            "later_send_gates": {
                "discovery_zero_budget": "DISABLE_TRANSPORT_NEVER_MAX_SENDS_PER_RUN_ZERO",
                "discovery_positive_budget_flag": "--max-sends-per-run <positive-reviewed-budget>",
                "paper_positive_budget_flag": "--max-paper-messages <1-to-20-reviewed-budget>",
                "paper_confirmation": "--confirm-paper-destination PHX2_PAPER_CANARY",
                "paper_destination_pin": "--paper-destination-sha256 <reviewed-destination-sha256>",
                "paper_credentials": ["PHX2_PAPER_TELEGRAM_BOT_TOKEN", "PHX2_PAPER_TELEGRAM_CHAT_ID"],
                "separate_authorization_required": True,
            },
        }
        if (run_dir / "STOP").exists():
            reasons.append("PAPER_STOP_FILE_PRESENT")
        plan["resume"] = inspect_resume(run_dir, sources, config_digest=config.config_digest(),
                                         allow_input_rollover=bool(getattr(args, "allow_input_rollover", False)))
    except PreflightError as exc:
        reasons.append(str(exc))
    except (OSError, ValueError, subprocess.SubprocessError):
        reasons.append("LOCAL_PREFLIGHT_READ_FAILED")
    if not reasons:
        plan["status"] = "LOCAL_PLAN_VALID_AWAITING_LIVE_AUTHORIZATION"
    return plan


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=str(Path(__file__).resolve().parents[2]))
    parser.add_argument("--config", required=True)
    parser.add_argument("--source-root", required=True, help="one exact producer run directory; no glob/recursive parent")
    parser.add_argument("--additional-source-root", action="append", default=[],
                        help="additional exact root; retain ALL prior roots, maximum 16 total")
    parser.add_argument("--allow-input-rollover", action="store_true",
                        help="permit only additive selection change from canonical saved roots")
    parser.add_argument("--out-root", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--reviewed-head")
    parser.add_argument("--reviewed-source-sha256")
    parser.add_argument("--tail-capacity", type=int)
    parser.add_argument("--max-runtime-seconds", type=int)
    parser.add_argument("--max-market-requests", type=int)
    parser.add_argument("--helius-max-raw-bytes", type=int)
    parser.add_argument("--max-discovery-messages", type=int)
    parser.add_argument("--max-paper-messages", type=int)
    parser.add_argument("--destination-alias", help="review label only; never a key, URL or chat ID")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    plan = build_plan(build_parser().parse_args(argv))
    print(json.dumps(plan, indent=2, sort_keys=True))
    return 2 if plan["status"] == "BLOCKED" else 0


if __name__ == "__main__":
    raise SystemExit(main())

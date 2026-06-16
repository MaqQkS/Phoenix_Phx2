"""PHX2 entrypoint.

Default ``python main.py`` is SAFE and NO-SEND: it prints a one-line status and
exits 0 without touching the network, a credential, a transport, or the durable
ledger -- identical in effect to the original Stage 1 placeholder.

The only non-default behavior is the Build #23 supervised entrypoint, reached
ONLY via ``--mode private-supervised`` plus exactly one action. Even then this
process never sends: it delegates to the already-proven, out-of-repo supervised
private operator flow by SUBPROCESS (it imports no supervisor and builds no
second send path). ``--live`` only LAUNCHES that flow; the interactive human
approval, the one-line arm flip, and the single private operator send all remain
inside the supervisor.

    python main.py
    python main.py --mode private-supervised --preflight-only \
        --require-baseline <sha256>:<size_bytes>:<line_count>
    python main.py --mode private-supervised --dry-run \
        --require-baseline <sha256>:<size_bytes>:<line_count>
    python main.py --mode private-supervised --live --post-send stop \
        --require-baseline <sha256>:<size_bytes>:<line_count>

The durable-ledger baseline is an ASSERTION the supervisor verifies before
arming and re-verifies (advanced by one appended JSONL record: line_count + 1,
size_bytes grown by one record, a new sha256) after a successful send. This
entrypoint passes it through verbatim, mutates no ledger, reads no credential env
var, and prints no secret (only a redacted baseline display).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional, Sequence

# Entrypoint bootstrap: ensure the repo root (this file's grandparent) is
# importable so ``python main.py`` works whether launched from the repo root or
# from the ``PHX2/`` package directory. This is the entry script, not a library
# module; the launch boundary modules it imports perform no import-time I/O.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from PHX2.entrypoint import launcher_models as M  # noqa: E402
from PHX2.entrypoint import supervised_launcher as L  # noqa: E402


def _build_parser() -> argparse.ArgumentParser:
    """Build the entrypoint argument parser.

    ``--mode`` is restricted to the single supported supervised mode and defaults
    to ``None`` (the safe no-send status path). The three actions are a mutually
    exclusive group collapsing to one ``action`` value, so argparse rejects two
    actions at once.
    """
    parser = argparse.ArgumentParser(
        prog="main.py",
        description="PHX2 entrypoint (default: safe no-send status).",
    )
    parser.add_argument(
        "--mode",
        choices=list(M.SUPPORTED_MODES),
        default=None,
        help="supervised mode; omit for the safe no-send status.",
    )
    action_group = parser.add_mutually_exclusive_group()
    action_group.add_argument(
        "--preflight-only",
        dest="action",
        action="store_const",
        const=M.ACTION_PREFLIGHT_ONLY,
        help="policy gate + durable dedupe forecast; no send.",
    )
    action_group.add_argument(
        "--dry-run",
        dest="action",
        action="store_const",
        const=M.ACTION_DRY_RUN,
        help="preview + send-fake + dedupe forecast; no real transport.",
    )
    action_group.add_argument(
        "--live",
        dest="action",
        action="store_const",
        const=M.ACTION_LIVE,
        help="launch the supervised live flow (approval + arm stay in the "
        "supervisor).",
    )
    parser.add_argument(
        "--require-baseline",
        dest="require_baseline",
        default=None,
        help="durable ledger baseline assertion <sha256>:<size_bytes>:"
        "<line_count>.",
    )
    parser.add_argument(
        "--post-send",
        choices=list(M.SUPPORTED_POST_SEND),
        default=None,
        help="post-send lifecycle (only 'stop', only with --live).",
    )
    return parser


def _print_status() -> None:
    """Print the default safe no-send status line."""
    print(
        "[phx2] status: safe no-send entrypoint. No mode selected; "
        "nothing dispatched."
    )


def _print_summary(result: "M.LauncherResult") -> None:
    """Print a redaction-safe one-line summary of a supervised launch.

    Prints only closed-set tokens, safe flags, the REDACTED baseline display, and
    the relayed child exit code -- never the full digest, never the handoff argv,
    never an env value.
    """
    print(
        "[phx2][build23] "
        f"outcome={result.outcome} mode={result.mode} action={result.action} "
        f"baseline={result.baseline_display} "
        f"supervisor_configured={result.supervisor_configured} "
        f"invoked={result.invoked} child_exit_code={result.child_exit_code}"
    )


def main(
    argv: Optional[Sequence[str]] = None,
    *,
    env_get=None,
    runner=None,
) -> int:
    """PHX2 entrypoint.

    Returns 0 for the default safe status. For ``--mode private-supervised`` it
    delegates to the out-of-repo supervisor via :func:`supervised_launcher.launch`
    and relays the child exit code; a fail-closed refusal returns
    ``M.EXIT_REFUSED``. Argparse usage errors raise ``SystemExit(2)``.

    ``env_get`` / ``runner`` are injection seams for tests; in normal use they
    default to the real environment and a real (no-shell) subprocess runner.
    """
    parser = _build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    # Default: safe no-send status (no mode, no action). Never reaches launcher.
    if args.mode is None and args.action is None:
        _print_status()
        return M.EXIT_OK

    # An action without the supervised mode is a usage error.
    if args.mode is None:
        parser.error("an action requires --mode private-supervised")
    # The supervised mode requires exactly one action and a baseline assertion.
    if args.action is None:
        parser.error(
            "--mode private-supervised requires one of "
            "--preflight-only / --dry-run / --live"
        )
    if args.require_baseline is None:
        parser.error(
            "--mode private-supervised requires --require-baseline "
            "<sha256>:<size_bytes>:<line_count>"
        )

    result = L.launch(
        mode=args.mode,
        action=args.action,
        baseline_raw=args.require_baseline,
        post_send=args.post_send,
        env_get=env_get,
        runner=runner,
    )
    _print_summary(result)

    if result.outcome == M.OUTCOME_INVOKED_SUPERVISOR and isinstance(
        result.child_exit_code, int
    ):
        return result.child_exit_code
    return M.EXIT_REFUSED


if __name__ == "__main__":
    raise SystemExit(main())

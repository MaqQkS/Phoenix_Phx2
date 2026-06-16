"""Build #23 supervised-entrypoint launcher (thin, subprocess-only).

The thin repo-side launch boundary that ``PHX2/main.py`` delegates to for the
``--mode private-supervised`` actions. It VALIDATES the operator's mode / action /
durable-ledger baseline / post-send inputs, RESOLVES the out-of-repo supervisor
command from a single owned pointer env var, BUILDS a redaction-safe handoff argv
(closed-set flags only -- no routing, no arm, no transport, no credential), and
INVOKES the supervisor through an injected runner. The default real runner is a
plain ``subprocess.run`` that INHERITS stdio (so the supervisor can run its own
interactive human approval) and INHERITS the environment (so the supervisor --
NOT this launcher -- reads its own credentials).

What this launcher NEVER does:

  * It never imports the out-of-repo supervisor (it subprocesses it).
  * It never builds a second send path: it constructs no transport, no
    authorization sentinel, and never flips an arm. ``--live`` only LAUNCHES the
    supervised flow; the interactive approval + the one-line arm flip + the one
    real send all remain INSIDE the out-of-repo supervisor.
  * It reads exactly ONE env var -- the supervisor command pointer
    (``PHX2_SUPERVISOR_CMD``) -- and never reads a credential env var.
  * It opens no network connection, no database, writes no file, mutates no
    durable ledger, and prints no secret.

``_ARMED_REAL_SEND_WIRING_REVIEWED`` stays ``False`` for the entire Build #23
scope: this repo ships no reviewed real-send wiring of its own. The constant is a
standing review gate for any FUTURE in-repo real-send wiring; while Build #23
ships none, the launcher contains no code path that reads a credential, injects a
transport, or sends, regardless of the constant's value.

Discipline:

  * Stdlib only (``os`` / ``subprocess`` / ``json`` / ``typing``) + the Build #23
    models sibling.
  * The single owned env read is the supervisor command pointer; no scattered
    credential reads (honors the PHX2 ``SAFETY.md`` stage-owned credential
    boundary -- the network / launch boundary lives in this owned subtree).
  * ``subprocess`` is invoked WITHOUT ``shell=True`` and with an argv list.
  * No network / HTTP / gRPC / socket import; no PHX2 runtime (Stage 21-30)
    import; no PHX1 import.
  * No module-level Call node (no implicit I/O at import time).
"""

from __future__ import annotations

import json
import os
import subprocess
from typing import Callable, Optional, Sequence, Tuple

from PHX2.entrypoint.launcher_models import (
    ACTION_LIVE,
    HANDOFF_ACTION_FLAG,
    HANDOFF_BASELINE_FLAG,
    HANDOFF_MODE_FLAG,
    HANDOFF_POST_SEND_FLAG,
    FORBIDDEN_HANDOFF_FLAGS,
    FORBIDDEN_ROUTING_TOKENS,
    OUTCOME_INVOKED_SUPERVISOR,
    OUTCOME_REFUSED_INVALID_ACTION,
    OUTCOME_REFUSED_INVALID_MODE,
    OUTCOME_REFUSED_INVALID_POST_SEND,
    OUTCOME_REFUSED_MALFORMED_BASELINE,
    OUTCOME_REFUSED_SUPERVISOR_INVOCATION_FAILED,
    OUTCOME_REFUSED_SUPERVISOR_NOT_CONFIGURED,
    OUTCOME_REFUSED_UNSAFE_HANDOFF,
    POST_SEND_STOP,
    SUPERVISOR_COMMAND_ENV,
    BaselineTriple,
    LauncherResult,
    baseline_passthrough,
    is_supported_action,
    is_supported_mode,
    parse_baseline_triple,
    redacted_baseline,
)


# The standing review gate for any FUTURE in-repo real-send wiring. Build #23
# ships NONE, so it is False. The launcher has no code path that injects a
# transport, arms, or sends regardless of this value; flipping it is explicitly
# out of Build #23 scope.
_ARMED_REAL_SEND_WIRING_REVIEWED: bool = False


EnvGet = Callable[[str], Optional[str]]
Runner = Callable[[Sequence[str]], int]


# ---------------------------------------------------------------------------
# Supervisor command pointer resolution (the single owned env read)
# ---------------------------------------------------------------------------


def _parse_command_spec(value: str) -> Optional[Tuple[str, ...]]:
    """Parse the supervisor command pointer into an argv prefix tuple, or
    ``None`` (fail closed) on any malformed value.

    Two accepted shapes:

      * a JSON array of non-blank strings (e.g. ``["python", "C:\\sup.py"]``) --
        used when the supervisor is launched via an interpreter / with args;
      * any other non-blank string -- treated as a single-token command (a path
        to an executable / launcher).

    Pure / total; never raises.
    """
    text = value.strip()
    if text == "":
        return None
    if text[0] == "[":
        try:
            parsed = json.loads(text)
        except ValueError:
            return None
        if not isinstance(parsed, list) or len(parsed) == 0:
            return None
        out = []
        for item in parsed:
            if not isinstance(item, str) or item.strip() == "":
                return None
            out.append(item)
        return tuple(out)
    return (text,)


def resolve_supervisor_command(env_get: EnvGet) -> Optional[Tuple[str, ...]]:
    """Resolve the out-of-repo supervisor command prefix from the single owned
    pointer env var, or ``None`` when it is unset / blank / malformed.

    Reads ONLY ``SUPERVISOR_COMMAND_ENV`` via the injected ``env_get`` -- never a
    credential env var. The value is a command pointer, never a secret. Total.
    """
    raw = env_get(SUPERVISOR_COMMAND_ENV)
    if not isinstance(raw, str):
        return None
    return _parse_command_spec(raw)


# ---------------------------------------------------------------------------
# Handoff argv construction + self-check
# ---------------------------------------------------------------------------


def build_handoff_tail(
    *,
    mode: str,
    action: str,
    triple: BaselineTriple,
    post_send: Optional[str],
) -> Tuple[str, ...]:
    """Build the closed-set flag tail the launcher appends to the resolved
    supervisor command.

    Always ``--mode <mode> --action <action> --require-baseline <passthrough>``;
    plus ``--post-send stop`` ONLY for the live action. No routing, arm, transport,
    or credential flag is ever appended. Pure.
    """
    tail = [
        HANDOFF_MODE_FLAG,
        mode,
        HANDOFF_ACTION_FLAG,
        action,
        HANDOFF_BASELINE_FLAG,
        baseline_passthrough(triple),
    ]
    if action == ACTION_LIVE:
        tail.append(HANDOFF_POST_SEND_FLAG)
        tail.append(POST_SEND_STOP)
    return tuple(tail)


def is_safe_handoff_tail(tail: Sequence[str]) -> bool:
    """Return ``True`` iff the launcher-appended ``tail`` carries no forbidden
    routing substring and no forbidden arm / transport / authorization flag.

    Scans ONLY the launcher-controlled tail (never the operator-supplied command
    prefix, whose path could innocently contain a denylisted substring). Pure /
    total; never raises.
    """
    for element in tail:
        if not isinstance(element, str):
            return False
        lowered = element.lower()
        for token in FORBIDDEN_ROUTING_TOKENS:
            if token in lowered:
                return False
        for flag in FORBIDDEN_HANDOFF_FLAGS:
            if lowered == flag:
                return False
    return True


# ---------------------------------------------------------------------------
# Default real runner (used only at a real operator invocation; tests inject a
# fake runner and never spawn a process)
# ---------------------------------------------------------------------------


def _default_subprocess_runner(argv: Sequence[str]) -> int:
    """Run the supervisor argv as a child process and return its exit code.

    Inherits stdio (so the supervisor can run its own interactive human approval)
    and inherits the environment (so the supervisor -- not this launcher -- reads
    its own credentials). Never uses ``shell=True``; never captures / echoes
    output. This launcher itself sends nothing.
    """
    completed = subprocess.run(list(argv))
    return int(completed.returncode)


# ---------------------------------------------------------------------------
# Pure refusal / success builders
# ---------------------------------------------------------------------------


def _safe_token(value: object) -> str:
    """Echo ``value`` only when it is a string, else ``""``. Pure / total."""
    return value if isinstance(value, str) else ""


def _refuse(
    outcome: str,
    *,
    mode: object,
    action: object,
    baseline_display: str = "",
    baseline_passthrough_value: str = "",
    supervisor_configured: bool = False,
    handoff_argv: Tuple[str, ...] = (),
) -> LauncherResult:
    """Build a fail-closed ``LauncherResult`` (no subprocess spawned, nothing
    sent). Pure.
    """
    return LauncherResult(
        outcome=outcome,
        mode=_safe_token(mode),
        action=_safe_token(action),
        baseline_display=baseline_display,
        baseline_passthrough=baseline_passthrough_value,
        supervisor_configured=supervisor_configured,
        invoked=False,
        child_exit_code=None,
        handoff_argv=handoff_argv,
    )


# ---------------------------------------------------------------------------
# The launch entry point
# ---------------------------------------------------------------------------


def launch(
    *,
    mode: object,
    action: object,
    baseline_raw: object,
    post_send: object = None,
    env_get: Optional[EnvGet] = None,
    runner: Optional[Runner] = None,
) -> LauncherResult:
    """Validate inputs, resolve the out-of-repo supervisor command, build a
    redaction-safe handoff argv, and invoke the supervisor through ``runner``.

    Returns a ``LauncherResult``. On ANY validation failure it fails closed -- no
    subprocess is spawned and nothing is sent. ``--live`` only LAUNCHES the
    supervisor; this function never approves, arms, injects a transport, or sends.
    Total except for ``KeyboardInterrupt`` / ``SystemExit`` (never swallowed); a
    runner exception is caught and mapped to a fail-closed refusal.
    """
    resolved_env_get: EnvGet = os.environ.get if env_get is None else env_get
    resolved_runner: Runner = (
        _default_subprocess_runner if runner is None else runner
    )

    # ---- 1. mode must be the single supported supervised mode -----------------
    if not is_supported_mode(mode):
        return _refuse(
            OUTCOME_REFUSED_INVALID_MODE, mode=mode, action=action
        )

    # ---- 2. action must be a supported supervised action ----------------------
    if not is_supported_action(action):
        return _refuse(
            OUTCOME_REFUSED_INVALID_ACTION, mode=mode, action=action
        )

    # ---- 3. post-send pairing: "stop" with live ONLY -------------------------
    if action == ACTION_LIVE:
        if post_send != POST_SEND_STOP:
            return _refuse(
                OUTCOME_REFUSED_INVALID_POST_SEND, mode=mode, action=action
            )
    else:
        if post_send is not None:
            return _refuse(
                OUTCOME_REFUSED_INVALID_POST_SEND, mode=mode, action=action
            )

    # ---- 4. baseline must parse to the exact triple shape --------------------
    triple = parse_baseline_triple(baseline_raw)
    if triple is None:
        return _refuse(
            OUTCOME_REFUSED_MALFORMED_BASELINE, mode=mode, action=action
        )
    display = redacted_baseline(triple)
    passthrough = baseline_passthrough(triple)

    # ---- 5. the out-of-repo supervisor command pointer must resolve ----------
    command_prefix = resolve_supervisor_command(resolved_env_get)
    if command_prefix is None:
        return _refuse(
            OUTCOME_REFUSED_SUPERVISOR_NOT_CONFIGURED,
            mode=mode,
            action=action,
            baseline_display=display,
            baseline_passthrough_value=passthrough,
            supervisor_configured=False,
        )

    # ---- 6. build + self-check the closed-set handoff tail -------------------
    tail = build_handoff_tail(
        mode=mode, action=action, triple=triple, post_send=post_send
    )
    if not is_safe_handoff_tail(tail):
        return _refuse(
            OUTCOME_REFUSED_UNSAFE_HANDOFF,
            mode=mode,
            action=action,
            baseline_display=display,
            baseline_passthrough_value=passthrough,
            supervisor_configured=True,
        )
    argv = tuple(command_prefix) + tail

    # ---- 7. invoke the supervisor (no send / arm / transport HERE) -----------
    try:
        child_exit = resolved_runner(argv)
    except (KeyboardInterrupt, SystemExit):
        raise
    except BaseException:
        # A runner failure (e.g. the command could not be spawned) fails closed.
        # No exception text is retained -- it could carry a path/secret.
        return _refuse(
            OUTCOME_REFUSED_SUPERVISOR_INVOCATION_FAILED,
            mode=mode,
            action=action,
            baseline_display=display,
            baseline_passthrough_value=passthrough,
            supervisor_configured=True,
            handoff_argv=argv,
        )

    code = (
        child_exit
        if isinstance(child_exit, int) and not isinstance(child_exit, bool)
        else 1
    )
    return LauncherResult(
        outcome=OUTCOME_INVOKED_SUPERVISOR,
        mode=mode,
        action=action,
        baseline_display=display,
        baseline_passthrough=passthrough,
        supervisor_configured=True,
        invoked=True,
        child_exit_code=code,
        handoff_argv=argv,
    )


__all__ = (
    "EnvGet",
    "Runner",
    "resolve_supervisor_command",
    "build_handoff_tail",
    "is_safe_handoff_tail",
    "launch",
)

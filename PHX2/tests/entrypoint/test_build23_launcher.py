"""Build #23 launcher behavior tests (fakes only; never spawns a process).

Every test injects a FAKE runner and a FAKE env reader, so no real subprocess is
spawned, no supervisor runs, nothing is sent, and the durable ledger is never
touched. Covers supervisor-pointer resolution, the closed-set handoff tail,
fail-closed refusals (mode / action / baseline / post-send / supervisor-missing),
the single owned env read, exact baseline passthrough, child-exit relay, and the
standing `_ARMED_REAL_SEND_WIRING_REVIEWED` review gate.
"""

from __future__ import annotations

from PHX2.entrypoint import launcher_models as M
from PHX2.entrypoint import supervised_launcher as L


BASELINE_SHA: str = (
    "78D20A7A2FE69BEF8BF833B60BB92209D06D23CE69A8D6F2800F991AC0331D96"
)
BASELINE: str = f"{BASELINE_SHA}:1096:3"

_DEFAULT_CMD: str = '["python", "-c", "pass"]'
_DEFAULT_PREFIX = ("python", "-c", "pass")


class _RecordingRunner:
    """A fake runner that records argv calls and returns a fixed exit code."""

    def __init__(self, code: int = 0) -> None:
        self.code = code
        self.calls = []

    def __call__(self, argv) -> int:
        self.calls.append(tuple(argv))
        return self.code


class _RaisingRunner:
    """A fake runner that records the attempt then raises (spawn failure)."""

    def __init__(self) -> None:
        self.calls = []

    def __call__(self, argv) -> int:
        self.calls.append(tuple(argv))
        raise OSError("spawn failed")


class _RecordingEnv:
    """A fake env reader that records every key requested."""

    def __init__(self, value=_DEFAULT_CMD) -> None:
        self.value = value
        self.keys = []

    def __call__(self, key):
        self.keys.append(key)
        return self.value if key == M.SUPERVISOR_COMMAND_ENV else None


def _cmd_env(value=_DEFAULT_CMD):
    def env_get(key):
        return value if key == M.SUPERVISOR_COMMAND_ENV else None

    return env_get


def _no_env(key):
    return None


# ---------------------------------------------------------------------------
# Supervisor command pointer resolution
# ---------------------------------------------------------------------------


def test_resolve_json_array_command() -> None:
    assert L.resolve_supervisor_command(_cmd_env('["python", "sup.py"]')) == (
        "python",
        "sup.py",
    )


def test_resolve_single_token_command() -> None:
    assert L.resolve_supervisor_command(
        _cmd_env(r"C:\tools\supervisor.exe")
    ) == (r"C:\tools\supervisor.exe",)


def test_resolve_missing_blank_or_malformed_is_none() -> None:
    assert L.resolve_supervisor_command(_no_env) is None
    assert L.resolve_supervisor_command(_cmd_env("   ")) is None
    assert L.resolve_supervisor_command(_cmd_env("[]")) is None
    assert L.resolve_supervisor_command(_cmd_env("[1, 2]")) is None
    assert L.resolve_supervisor_command(_cmd_env('["ok", ""]')) is None
    assert L.resolve_supervisor_command(_cmd_env("[not json")) is None


# ---------------------------------------------------------------------------
# Handoff tail construction + self-check
# ---------------------------------------------------------------------------


def test_preflight_tail_shape() -> None:
    triple = M.parse_baseline_triple(BASELINE)
    tail = L.build_handoff_tail(
        mode=M.MODE_PRIVATE_SUPERVISED,
        action=M.ACTION_PREFLIGHT_ONLY,
        triple=triple,
        post_send=None,
    )
    assert tail == (
        "--mode",
        "private-supervised",
        "--action",
        "preflight-only",
        "--require-baseline",
        BASELINE,
    )


def test_live_tail_appends_post_send_stop() -> None:
    triple = M.parse_baseline_triple(BASELINE)
    tail = L.build_handoff_tail(
        mode=M.MODE_PRIVATE_SUPERVISED,
        action=M.ACTION_LIVE,
        triple=triple,
        post_send=M.POST_SEND_STOP,
    )
    assert tail[-2:] == ("--post-send", "stop")


def test_built_tails_are_self_check_safe() -> None:
    triple = M.parse_baseline_triple(BASELINE)
    for action, post in (
        (M.ACTION_PREFLIGHT_ONLY, None),
        (M.ACTION_DRY_RUN, None),
        (M.ACTION_LIVE, M.POST_SEND_STOP),
    ):
        tail = L.build_handoff_tail(
            mode=M.MODE_PRIVATE_SUPERVISED,
            action=action,
            triple=triple,
            post_send=post,
        )
        assert L.is_safe_handoff_tail(tail) is True
        # No forbidden arm / transport / authorization flag is ever appended.
        assert set(tail).isdisjoint(set(M.FORBIDDEN_HANDOFF_FLAGS))


def test_self_check_rejects_injected_routing_or_arm_tokens() -> None:
    assert L.is_safe_handoff_tail(["--mode", "public-broadcast"]) is False
    assert L.is_safe_handoff_tail(["--arm"]) is False
    assert L.is_safe_handoff_tail(["--inject-transport"]) is False


# ---------------------------------------------------------------------------
# Fail-closed refusals -- never spawn, never send
# ---------------------------------------------------------------------------


def test_invalid_mode_refused_runner_untouched() -> None:
    runner = _RecordingRunner()
    result = L.launch(
        mode="public",
        action=M.ACTION_DRY_RUN,
        baseline_raw=BASELINE,
        env_get=_cmd_env(),
        runner=runner,
    )
    assert result.outcome == M.OUTCOME_REFUSED_INVALID_MODE
    assert result.invoked is False
    assert runner.calls == []


def test_invalid_action_refused() -> None:
    runner = _RecordingRunner()
    result = L.launch(
        mode=M.MODE_PRIVATE_SUPERVISED,
        action="send",
        baseline_raw=BASELINE,
        env_get=_cmd_env(),
        runner=runner,
    )
    assert result.outcome == M.OUTCOME_REFUSED_INVALID_ACTION
    assert runner.calls == []


def test_malformed_baseline_refused() -> None:
    runner = _RecordingRunner()
    result = L.launch(
        mode=M.MODE_PRIVATE_SUPERVISED,
        action=M.ACTION_PREFLIGHT_ONLY,
        baseline_raw="not-a-baseline",
        env_get=_cmd_env(),
        runner=runner,
    )
    assert result.outcome == M.OUTCOME_REFUSED_MALFORMED_BASELINE
    assert result.invoked is False
    assert runner.calls == []


def test_supervisor_missing_refused_runner_untouched() -> None:
    runner = _RecordingRunner()
    result = L.launch(
        mode=M.MODE_PRIVATE_SUPERVISED,
        action=M.ACTION_PREFLIGHT_ONLY,
        baseline_raw=BASELINE,
        env_get=_no_env,
        runner=runner,
    )
    assert result.outcome == M.OUTCOME_REFUSED_SUPERVISOR_NOT_CONFIGURED
    assert result.supervisor_configured is False
    assert result.invoked is False
    assert runner.calls == []


def test_live_requires_post_send_stop() -> None:
    runner = _RecordingRunner()
    result = L.launch(
        mode=M.MODE_PRIVATE_SUPERVISED,
        action=M.ACTION_LIVE,
        baseline_raw=BASELINE,
        post_send=None,
        env_get=_cmd_env(),
        runner=runner,
    )
    assert result.outcome == M.OUTCOME_REFUSED_INVALID_POST_SEND
    assert runner.calls == []


def test_non_live_rejects_post_send() -> None:
    runner = _RecordingRunner()
    result = L.launch(
        mode=M.MODE_PRIVATE_SUPERVISED,
        action=M.ACTION_DRY_RUN,
        baseline_raw=BASELINE,
        post_send=M.POST_SEND_STOP,
        env_get=_cmd_env(),
        runner=runner,
    )
    assert result.outcome == M.OUTCOME_REFUSED_INVALID_POST_SEND
    assert runner.calls == []


def test_runner_exception_fails_closed_total() -> None:
    runner = _RaisingRunner()
    result = L.launch(
        mode=M.MODE_PRIVATE_SUPERVISED,
        action=M.ACTION_DRY_RUN,
        baseline_raw=BASELINE,
        env_get=_cmd_env(),
        runner=runner,
    )
    assert result.outcome == M.OUTCOME_REFUSED_SUPERVISOR_INVOCATION_FAILED
    assert result.invoked is False
    # The runner was attempted exactly once; the launcher never retries.
    assert len(runner.calls) == 1


# ---------------------------------------------------------------------------
# Successful invocation -- forward + relay (still no send by this launcher)
# ---------------------------------------------------------------------------


def test_invoke_forwards_and_relays_exit_zero() -> None:
    runner = _RecordingRunner(0)
    result = L.launch(
        mode=M.MODE_PRIVATE_SUPERVISED,
        action=M.ACTION_DRY_RUN,
        baseline_raw=BASELINE,
        env_get=_cmd_env(),
        runner=runner,
    )
    assert result.outcome == M.OUTCOME_INVOKED_SUPERVISOR
    assert result.invoked is True
    assert result.child_exit_code == 0
    assert result.baseline_passthrough == BASELINE
    assert len(runner.calls) == 1
    argv = runner.calls[0]
    assert argv[:3] == _DEFAULT_PREFIX
    assert "--require-baseline" in argv
    assert BASELINE in argv


def test_child_exit_code_is_relayed() -> None:
    runner = _RecordingRunner(7)
    result = L.launch(
        mode=M.MODE_PRIVATE_SUPERVISED,
        action=M.ACTION_PREFLIGHT_ONLY,
        baseline_raw=BASELINE,
        env_get=_cmd_env(),
        runner=runner,
    )
    assert result.child_exit_code == 7


def test_live_invocation_forwards_no_arm_or_transport_flag() -> None:
    runner = _RecordingRunner(0)
    result = L.launch(
        mode=M.MODE_PRIVATE_SUPERVISED,
        action=M.ACTION_LIVE,
        baseline_raw=BASELINE,
        post_send=M.POST_SEND_STOP,
        env_get=_cmd_env(),
        runner=runner,
    )
    assert result.outcome == M.OUTCOME_INVOKED_SUPERVISOR
    argv = runner.calls[0]
    # --live only LAUNCHES; the launcher injects no arm / transport / auth flag.
    assert set(argv).isdisjoint(set(M.FORBIDDEN_HANDOFF_FLAGS))
    assert "--action" in argv and "live" in argv
    assert argv[-2:] == ("--post-send", "stop")


# ---------------------------------------------------------------------------
# The single owned env read + the standing review gate
# ---------------------------------------------------------------------------


def test_launch_reads_only_the_supervisor_pointer_env() -> None:
    env = _RecordingEnv()
    runner = _RecordingRunner(0)
    L.launch(
        mode=M.MODE_PRIVATE_SUPERVISED,
        action=M.ACTION_PREFLIGHT_ONLY,
        baseline_raw=BASELINE,
        env_get=env,
        runner=runner,
    )
    # The launcher reads exactly ONE env var -- the supervisor command pointer --
    # and never a credential env var.
    assert set(env.keys) == {M.SUPERVISOR_COMMAND_ENV}


def test_armed_real_send_wiring_review_gate_is_false() -> None:
    assert L._ARMED_REAL_SEND_WIRING_REVIEWED is False

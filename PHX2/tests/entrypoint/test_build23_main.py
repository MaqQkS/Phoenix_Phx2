"""Build #23 ``main.py`` entrypoint tests (fakes only; never spawns a process).

Covers the default safe no-send path, argparse mode/action discipline, baseline
pass-through, fail-closed refusals, child-exit relay, and output secret hygiene.
Every supervised path injects a FAKE runner + FAKE env reader, so no real
subprocess is spawned, nothing is sent, no arm is flipped, no transport is
constructed, and the durable ledger is never touched.
"""

from __future__ import annotations

import pytest

from PHX2 import main as main_module
from PHX2.main import main
from PHX2.entrypoint import launcher_models as M
from PHX2.entrypoint import supervised_launcher as L


BASELINE_SHA: str = (
    "78D20A7A2FE69BEF8BF833B60BB92209D06D23CE69A8D6F2800F991AC0331D96"
)
BASELINE: str = f"{BASELINE_SHA}:1096:3"


class _RecordingRunner:
    def __init__(self, code: int = 0) -> None:
        self.code = code
        self.calls = []

    def __call__(self, argv) -> int:
        self.calls.append(tuple(argv))
        return self.code


def _cmd_env(key):
    return '["python", "-c", "pass"]' if key == M.SUPERVISOR_COMMAND_ENV else None


def _no_env(key):
    return None


# ---------------------------------------------------------------------------
# Default safe no-send path
# ---------------------------------------------------------------------------


def test_default_is_safe_and_does_not_invoke_supervisor(monkeypatch, capsys):
    def _boom(*args, **kwargs):
        raise AssertionError("default main must never reach the launcher")

    monkeypatch.setattr(L, "launch", _boom)
    assert main([]) == 0
    out = capsys.readouterr().out
    assert "safe no-send" in out


def test_default_prints_no_secret(capsys):
    main([])
    out = capsys.readouterr().out
    assert "://" not in out
    assert BASELINE_SHA not in out


# ---------------------------------------------------------------------------
# Argparse mode / action discipline
# ---------------------------------------------------------------------------


def test_only_private_supervised_mode_accepted():
    with pytest.raises(SystemExit) as ei:
        main(["--mode", "public", "--preflight-only", "--require-baseline", BASELINE])
    assert ei.value.code == 2


def test_actions_are_mutually_exclusive():
    with pytest.raises(SystemExit) as ei:
        main(
            [
                "--mode",
                "private-supervised",
                "--preflight-only",
                "--dry-run",
                "--require-baseline",
                BASELINE,
            ]
        )
    assert ei.value.code == 2


def test_mode_requires_an_action():
    with pytest.raises(SystemExit) as ei:
        main(["--mode", "private-supervised", "--require-baseline", BASELINE])
    assert ei.value.code == 2


def test_mode_requires_a_baseline():
    with pytest.raises(SystemExit) as ei:
        main(["--mode", "private-supervised", "--preflight-only"])
    assert ei.value.code == 2


def test_action_without_mode_is_usage_error():
    with pytest.raises(SystemExit) as ei:
        main(["--preflight-only", "--require-baseline", BASELINE])
    assert ei.value.code == 2


# ---------------------------------------------------------------------------
# Fail-closed refusals (no subprocess spawned)
# ---------------------------------------------------------------------------


def test_malformed_baseline_fails_closed_without_invoking():
    runner = _RecordingRunner()
    code = main(
        [
            "--mode",
            "private-supervised",
            "--preflight-only",
            "--require-baseline",
            "bad-baseline",
        ],
        env_get=_cmd_env,
        runner=runner,
    )
    assert code == M.EXIT_REFUSED
    assert runner.calls == []


def test_supervisor_missing_fails_closed_without_invoking():
    runner = _RecordingRunner()
    code = main(
        [
            "--mode",
            "private-supervised",
            "--preflight-only",
            "--require-baseline",
            BASELINE,
        ],
        env_get=_no_env,
        runner=runner,
    )
    assert code == M.EXIT_REFUSED
    assert runner.calls == []


# ---------------------------------------------------------------------------
# Pass-through, relay, routing hygiene, and live discipline
# ---------------------------------------------------------------------------


def test_valid_baseline_passed_through_as_sha256_size_line():
    runner = _RecordingRunner(0)
    code = main(
        [
            "--mode",
            "private-supervised",
            "--dry-run",
            "--require-baseline",
            BASELINE,
        ],
        env_get=_cmd_env,
        runner=runner,
    )
    assert code == 0
    assert len(runner.calls) == 1
    argv = runner.calls[0]
    # The baseline is forwarded verbatim as sha256:size_bytes:line_count.
    idx = argv.index("--require-baseline")
    assert argv[idx + 1] == BASELINE
    assert "--mode" in argv and "private-supervised" in argv
    assert "--action" in argv and "dry-run" in argv


def test_no_public_or_subscriber_tokens_in_built_argv():
    runner = _RecordingRunner(0)
    main(
        [
            "--mode",
            "private-supervised",
            "--dry-run",
            "--require-baseline",
            BASELINE,
        ],
        env_get=_cmd_env,
        runner=runner,
    )
    argv = runner.calls[0]
    # Scan the launcher-appended tail (everything after the 3-token fake prefix).
    tail = argv[3:]
    joined = " ".join(tail).lower()
    for token in M.FORBIDDEN_ROUTING_TOKENS:
        assert token not in joined


def test_child_exit_code_is_relayed():
    runner = _RecordingRunner(7)
    code = main(
        [
            "--mode",
            "private-supervised",
            "--dry-run",
            "--require-baseline",
            BASELINE,
        ],
        env_get=_cmd_env,
        runner=runner,
    )
    assert code == 7


def test_live_forwards_but_main_does_not_arm_or_send():
    runner = _RecordingRunner(0)
    code = main(
        [
            "--mode",
            "private-supervised",
            "--live",
            "--post-send",
            "stop",
            "--require-baseline",
            BASELINE,
        ],
        env_get=_cmd_env,
        runner=runner,
    )
    assert code == 0
    # main only LAUNCHES: exactly one forward; no arm / transport / auth flag.
    assert len(runner.calls) == 1
    argv = runner.calls[0]
    assert set(argv).isdisjoint(set(M.FORBIDDEN_HANDOFF_FLAGS))
    assert "live" in argv
    assert argv[-2:] == ("--post-send", "stop")


def test_summary_output_carries_no_full_digest_or_scheme(capsys):
    runner = _RecordingRunner(0)
    main(
        [
            "--mode",
            "private-supervised",
            "--dry-run",
            "--require-baseline",
            BASELINE,
        ],
        env_get=_cmd_env,
        runner=runner,
    )
    out = capsys.readouterr().out
    # The redacted summary never prints the full digest, a url scheme, or argv.
    assert BASELINE_SHA not in out
    assert BASELINE not in out
    assert "://" not in out
    assert "python" not in out  # the resolved command prefix is never printed


def test_main_module_imports_launcher_boundary():
    # main delegates to the launcher boundary (no second send path here).
    assert main_module.L is L

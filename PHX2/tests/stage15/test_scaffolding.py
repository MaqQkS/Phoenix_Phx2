"""PHASE 1 sanity tests.

Verify the Stage 15 scaffolding hangs together: modules import without
DB/runtime side effects, the CLI parser builds, --help renders, and a
known-bad invocation surfaces non-zero exit.
"""

from __future__ import annotations

import importlib
import subprocess
import sys

import pytest

from PHX2.scripts import run_stage15_operator_approval as cli
from PHX2.stage15 import errors


def test_error_code_set_is_closed() -> None:
    """ALL_ERROR_CODES exposes exactly L01-L26 + A01-A04."""

    expected_load = {f"L{n:02d}" for n in range(1, 27)}
    expected_approval = {"A01", "A02", "A03", "A04"}
    assert set(errors.LOAD_TIME_ERROR_CODES) == expected_load
    assert set(errors.APPROVAL_TIME_ERROR_CODES) == expected_approval
    assert errors.ALL_ERROR_CODES == expected_load | expected_approval


def test_error_constructors_validate_codes() -> None:
    """Stage15LoadTimeError rejects approval codes and vice-versa."""

    with pytest.raises(ValueError):
        errors.Stage15LoadTimeError("A01", "wrong tier")
    with pytest.raises(ValueError):
        errors.Stage15ApprovalTimeError("L01", "wrong tier")
    with pytest.raises(ValueError):
        errors.Stage15Error("ZZZ", "not in set")


def test_cli_help_renders() -> None:
    """argparse --help builds and renders without error."""

    parser = cli.make_parser()
    text = parser.format_help()
    assert "--stage14-run-path" in text
    assert "--operator-review" in text
    assert "--output-dir" in text
    assert "--reviewer" in text


def test_cli_help_via_subprocess() -> None:
    """The script entry point survives a real --help invocation."""

    proc = subprocess.run(
        [
            sys.executable,
            "-c",
            "from PHX2.scripts.run_stage15_operator_approval import main; "
            "raise SystemExit(main(['--help']))",
        ],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert proc.returncode == 0, proc.stderr
    assert "Stage 15 operator approval layer" in proc.stdout


def test_cli_missing_required_args_exits_nonzero(capsys: pytest.CaptureFixture[str]) -> None:
    """argparse rejects an empty argv with SystemExit(2)."""

    with pytest.raises(SystemExit) as excinfo:
        cli.main([])
    assert excinfo.value.code == 2  # argparse's default for bad args


def test_no_db_or_runtime_imports() -> None:
    """Stage 15 modules must not import DB/service/runtime modules.

    A pragmatic check: re-import each Stage 15 module fresh and assert
    that no module-level import resolves to anything under
    PHX2.db, PHX2.services, PHX2.dispatch, PHX2.renderers,
    PHX2.integrations, PHX2.filters, or PHX2.main.
    """

    forbidden_prefixes = (
        "PHX2.db",
        "PHX2.services",
        "PHX2.dispatch",
        "PHX2.renderers",
        "PHX2.integrations",
        "PHX2.filters",
        "PHX2.main",
    )

    stage15_modules = (
        "PHX2.stage15",
        "PHX2.stage15.errors",
        "PHX2.stage15.hashing",
        "PHX2.stage15.loaders",
        "PHX2.stage15.reconciler",
        "PHX2.stage15.safety_gate",
        "PHX2.stage15.writer",
        "PHX2.stage15.markdown",
        "PHX2.scripts.run_stage15_operator_approval",
    )

    for mod_name in stage15_modules:
        mod = importlib.import_module(mod_name)
        # Walk the module's globals for nested imports too
        for attr_name in dir(mod):
            attr = getattr(mod, attr_name, None)
            mod_path = getattr(attr, "__module__", "")
            if not isinstance(mod_path, str):
                continue
            for bad in forbidden_prefixes:
                assert not mod_path.startswith(bad), (
                    f"{mod_name} references {attr_name} from {mod_path} "
                    f"(forbidden prefix {bad})"
                )

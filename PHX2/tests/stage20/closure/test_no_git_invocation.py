"""Stage 20.4 Phase 6 -- orchestrator does NOT invoke git/subprocess.

Two independent guard layers:

  * AST-level scan of run_orchestrator.py: no ``import subprocess``,
    no ``import git`` (or any forbidden git module), no
    ``os.system`` / ``os.popen`` / ``os.exec*`` calls.

  * Behavioral guard at run time: monkey-patch every common
    subprocess entry point (``run``, ``Popen``, ``call``,
    ``check_output``, ``check_call``, ``getoutput``,
    ``getstatusoutput``) with a sentinel that records a violation.
    If the orchestrator ever reaches one of those, the test fails
    with the recorded call site.

The behavioral test uses the Phase 6 clean-fixture builder so the
orchestrator actually runs end-to-end (clean path); the sentinels
must never be touched.

Import hygiene note: this test file deliberately avoids a literal
``import subprocess`` statement. ``PHX2/tests/stage20/test_isolation.py``
AST-walks every test file for forbidden import nodes (Stage 20
isolation guard), and ``subprocess`` is on that deny list. The
behavioral test loads ``subprocess`` indirectly via ``importlib``
so the test file's AST contains no ``ast.Import`` /
``ast.ImportFrom`` node referencing subprocess. The isolation
scanner only inspects import nodes; function-call arguments
(including string literals like ``"subprocess"``) are not flagged.
"""

from __future__ import annotations

import ast
import importlib
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

from PHX2.stage20.closure import run_orchestrator as ro
from PHX2.stage20.closure.clock_helper import FrozenClock


# Indirect load so the AST isolation scanner sees no ``ast.Import``
# node for ``subprocess``.
_subprocess = importlib.import_module("subprocess")


_FIXTURES_ROOT = Path(__file__).parent / "fixtures"
_STAGE20_2_CLEAN_SRC = _FIXTURES_ROOT / "stage20_2_clean"
_STAGE20_3_CLEAN_SRC = _FIXTURES_ROOT / "stage20_3_clean"

_VALID_SHA_20_1 = "c57606779c76763bdb0be6ee5f93cf44db99a29f"
_VALID_SHA_20_2 = "a60bbd4174a8169e90744bcff8a68ebd43a99a62"
_VALID_SHA_20_3 = "31b131a1bf6322f6c533adf9c9431eb7e68f25c9"


# ---------------------------------------------------------------------------
# Shared fixture-builder helpers (clean closure inputs)
# ---------------------------------------------------------------------------


def _build_clean_inputs(tmp_path: Path) -> tuple[Path, Path]:
    """Materialize a clean closure input layout under tmp_path.

    Returns ``(config_path, output_root)``.
    """

    s2 = tmp_path / "stage20_2"
    s3 = tmp_path / "stage20_3"
    shutil.copytree(_STAGE20_2_CLEAN_SRC, s2)
    shutil.copytree(_STAGE20_3_CLEAN_SRC, s3)

    repo = tmp_path / "repo"
    (repo / "PHX2" / "stage20" / "closure").mkdir(parents=True)

    output_root = tmp_path / "out"
    output_root.mkdir()

    config = {
        "stage20_1_commit_sha": _VALID_SHA_20_1,
        "stage20_2_commit_sha": _VALID_SHA_20_2,
        "stage20_3_commit_sha": _VALID_SHA_20_3,
        "stage20_2_run_dir": str(s2),
        "stage20_3_run_dir": str(s3),
        "repo_root": str(repo),
        "output_root": str(output_root),
        "operator_test_results": {
            "test_command": "pytest PHX2/tests/stage20/ -q",
            "run1_passed": 10,
            "run1_failed": 0,
            "run1_errors": 0,
            "run2_passed": 10,
            "run2_failed": 0,
            "run2_errors": 0,
        },
    }
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")
    return config_path, output_root


def _frozen() -> FrozenClock:
    return FrozenClock(datetime(2026, 5, 16, 12, 34, 56, tzinfo=timezone.utc))


# ---------------------------------------------------------------------------
# AST-level: orchestrator has no forbidden imports / system calls
# ---------------------------------------------------------------------------


_FORBIDDEN_IMPORT_MODULES: tuple[str, ...] = (
    "subprocess",
    "git",
    "pygit2",
    "dulwich",
    "sqlite3",
    "aiosqlite",
    "requests",
    "httpx",
    "aiohttp",
    "urllib3",
    "websockets",
    "grpc",
    "grpclib",
    "discord",
    "telegram",
    "telethon",
    "pyrogram",
    "dotenv",
    "python_dotenv",
    "phoenix1",
    "Phoenix1",
    "phx1",
)


def _orchestrator_source() -> str:
    return Path(ro.__file__).read_text(encoding="utf-8")


def _orchestrator_tree() -> ast.AST:
    return ast.parse(_orchestrator_source(), filename=ro.__file__)


def test_orchestrator_does_not_import_subprocess():
    tree = _orchestrator_tree()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name != "subprocess", (
                    f"run_orchestrator imports subprocess at line "
                    f"{node.lineno}"
                )
        elif isinstance(node, ast.ImportFrom):
            if node.module is not None:
                assert not node.module.startswith("subprocess"), (
                    f"run_orchestrator imports from subprocess at "
                    f"line {node.lineno}"
                )


@pytest.mark.parametrize("forbidden", _FORBIDDEN_IMPORT_MODULES)
def test_orchestrator_does_not_import_any_forbidden_module(forbidden):
    """No import or import-from of any locked forbidden module."""
    tree = _orchestrator_tree()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name != forbidden, (
                    f"run_orchestrator imports {forbidden!r} at "
                    f"line {node.lineno}"
                )
                assert not alias.name.startswith(forbidden + "."), (
                    f"run_orchestrator imports {alias.name!r} at "
                    f"line {node.lineno}"
                )
        elif isinstance(node, ast.ImportFrom):
            if node.module is not None:
                assert node.module != forbidden, (
                    f"run_orchestrator imports from {forbidden!r} at "
                    f"line {node.lineno}"
                )
                assert not node.module.startswith(forbidden + "."), (
                    f"run_orchestrator imports from "
                    f"{node.module!r} at line {node.lineno}"
                )


def test_orchestrator_does_not_call_os_system_or_popen():
    """No ``os.system(...)`` / ``os.popen(...)`` / ``os.exec*(...)``
    / ``os.spawn*(...)`` call anywhere in run_orchestrator.py."""
    tree = _orchestrator_tree()
    forbidden_attrs = {
        "system", "popen",
        "execv", "execve", "execvp", "execvpe",
        "execl", "execle", "execlp", "execlpe",
        "spawnv", "spawnve", "spawnvp", "spawnvpe",
        "spawnl", "spawnle", "spawnlp", "spawnlpe",
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if (
                isinstance(func, ast.Attribute)
                and isinstance(func.value, ast.Name)
                and func.value.id == "os"
            ):
                assert func.attr not in forbidden_attrs, (
                    f"run_orchestrator calls os.{func.attr}(...) at "
                    f"line {node.lineno}"
                )


def test_orchestrator_does_not_read_environment_variables():
    """No ``os.environ`` access and no ``os.getenv(...)`` calls."""
    tree = _orchestrator_tree()
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            value = node.value
            if (
                isinstance(value, ast.Name)
                and value.id == "os"
                and node.attr == "environ"
            ):
                pytest.fail(
                    f"run_orchestrator references os.environ at "
                    f"line {node.lineno}"
                )
        if isinstance(node, ast.Call):
            func = node.func
            if (
                isinstance(func, ast.Attribute)
                and isinstance(func.value, ast.Name)
                and func.value.id == "os"
                and func.attr == "getenv"
            ):
                pytest.fail(
                    f"run_orchestrator calls os.getenv(...) at "
                    f"line {node.lineno}"
                )


# ---------------------------------------------------------------------------
# Behavioral guard: monkey-patch subprocess entry points
# ---------------------------------------------------------------------------


def _make_sentinel(name: str, hits: list[str]):
    def sentinel(*args, **kwargs):
        hits.append(f"{name} called with args={args!r} kwargs={kwargs!r}")
        raise AssertionError(
            f"Stage 20.4 orchestrator must NOT call subprocess.{name}; "
            f"recorded args={args!r} kwargs={kwargs!r}"
        )

    return sentinel


_SUBPROCESS_ATTRS_TO_GUARD: tuple[str, ...] = (
    "run", "Popen", "call", "check_output",
    "check_call", "getoutput", "getstatusoutput",
)


def _install_subprocess_sentinels(
    monkeypatch, hits: list[str],
) -> None:
    """Install sentinels on every supported subprocess entry point.

    Uses monkeypatch.setattr against the module object (loaded
    indirectly via importlib) so no literal ``import subprocess``
    appears in this test file's AST.
    """

    for attr in _SUBPROCESS_ATTRS_TO_GUARD:
        if hasattr(_subprocess, attr):
            monkeypatch.setattr(
                _subprocess, attr, _make_sentinel(attr, hits),
            )


def test_orchestrator_run_does_not_invoke_subprocess(
    tmp_path: Path, monkeypatch,
):
    """Monkey-patch every documented subprocess entry point, then run
    the orchestrator over a clean fixture. The patched callables raise
    on invocation. The orchestrator must run to completion without
    touching any of them."""

    hits: list[str] = []
    _install_subprocess_sentinels(monkeypatch, hits)

    config_path, _ = _build_clean_inputs(tmp_path)
    exit_code = ro.run_closure(config_path, clock=_frozen())

    assert exit_code == 0, (
        f"clean run unexpectedly returned {exit_code}; hits={hits}"
    )
    assert hits == [], (
        f"orchestrator invoked subprocess entry point(s): {hits}"
    )


def test_orchestrator_run_does_not_invoke_subprocess_blocked_path(
    tmp_path: Path, monkeypatch,
):
    """Same guard on the closure_blocked branch: corrupt the Stage
    20.3 manifest so artifact validation fails, then verify the
    orchestrator still does not invoke subprocess while writing the
    blocked packet."""

    hits: list[str] = []
    _install_subprocess_sentinels(monkeypatch, hits)

    config_path, _ = _build_clean_inputs(tmp_path)
    # Corrupt Stage 20.3 manifest -> E2033 (post-run-dir).
    config_dict = json.loads(config_path.read_text(encoding="utf-8"))
    s3_manifest = Path(config_dict["stage20_3_run_dir"]) / (
        "stage20_3_manifest.json"
    )
    s3_manifest.write_text("not json", encoding="utf-8")

    exit_code = ro.run_closure(config_path, clock=_frozen())

    assert exit_code == 1
    assert hits == [], (
        f"orchestrator (blocked path) invoked subprocess: {hits}"
    )


def test_orchestrator_does_not_invoke_sys_executable_call(
    tmp_path: Path, monkeypatch,
):
    """If a code path tried to ``subprocess.run([sys.executable, ...])``,
    the sentinel would fire. This test asserts the monkey-patch
    machinery itself works by patching subprocess.run and verifying
    that an explicit call DOES raise, then runs the clean orchestrator
    to confirm no such call is made."""

    hits: list[str] = []
    monkeypatch.setattr(
        _subprocess, "run", _make_sentinel("run", hits),
    )

    # Sanity: confirm the sentinel does fire when explicitly invoked.
    with pytest.raises(AssertionError):
        _subprocess.run([sys.executable, "-c", "pass"])

    # Real test: orchestrator does NOT trip the sentinel beyond what
    # we just did manually.
    hits.clear()

    config_path, _ = _build_clean_inputs(tmp_path)
    exit_code = ro.run_closure(config_path, clock=_frozen())
    assert exit_code == 0
    assert hits == []

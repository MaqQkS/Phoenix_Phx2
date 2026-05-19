"""Stage 22.5 file-scoped boundary tests for the bounded private
ingest runner and the live composition seam.

The shared Stage 22 boundary tests in
``test_stage_22_1_boundaries.py`` already enforce the rolling
production-tree scope on every Stage 22 production module
including ``bounded_live_runner.py`` and ``live_composition.py``.
This file pins the 22.5-specific properties of those two modules:

  * ``STAGE22_MINOR_VERSION`` is ``"22.5"`` (rolling axis).
  * ``bounded_live_runner.py`` imports NOTHING from Stage 21.
  * ``bounded_live_runner.py`` performs no env reads, no file
    I/O, no clock imports, no network imports, no sleep/backoff,
    no while loops, no async, no CLI surface.
  * ``live_composition.py`` is the SINGLE Stage 22 production
    file permitted to import any module in the live-composition
    allowlist.
  * The live-composition allowlist matches the design lock
    exactly.
  * The bounded runner exposes the ``run_bounded_private_ingest``
    callable with all-keyword-only parameters and the locked
    parameter order.
  * No new ``INGEST_RUNNER_OUTCOMES`` token is added by 22.5.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

from PHX2.stage22 import constants as c


STAGE22_ROOT: Path = (
    Path(__file__).parent.parent.parent / "stage22"
)
BOUNDED_RUNNER_PATH: Path = STAGE22_ROOT / "bounded_live_runner.py"
LIVE_COMPOSITION_PATH: Path = STAGE22_ROOT / "live_composition.py"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _collect_imports(path: Path) -> set[str]:
    tree = ast.parse(_read(path))
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                out.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                out.add(node.module)
    return out


def _collect_attribute_names(path: Path) -> set[str]:
    tree = ast.parse(_read(path))
    return {
        node.attr for node in ast.walk(tree)
        if isinstance(node, ast.Attribute)
    }


def _tree(path: Path) -> ast.Module:
    return ast.parse(_read(path))


# ---------------------------------------------------------------------------
# Version axis
# ---------------------------------------------------------------------------


def test_stage22_minor_version_is_22_5():
    assert c.STAGE22_MINOR_VERSION == "22.5"


# ---------------------------------------------------------------------------
# Production file presence
# ---------------------------------------------------------------------------


def test_bounded_live_runner_module_exists():
    assert BOUNDED_RUNNER_PATH.is_file()


def test_live_composition_module_exists():
    assert LIVE_COMPOSITION_PATH.is_file()


# ---------------------------------------------------------------------------
# bounded_live_runner.py: no Stage 21 imports
# ---------------------------------------------------------------------------


def test_bounded_live_runner_has_no_stage21_imports():
    imports = _collect_imports(BOUNDED_RUNNER_PATH)
    for mod in imports:
        assert not mod.startswith("PHX2.stage21"), (
            f"bounded_live_runner.py must not import PHX2.stage21; "
            f"got {mod!r}"
        )


# ---------------------------------------------------------------------------
# bounded_live_runner.py: locked import allowlist
# ---------------------------------------------------------------------------


_BOUNDED_RUNNER_ALLOWED_IMPORT_PREFIXES: tuple[str, ...] = (
    "__future__",
    "collections.abc",
    "typing",
    "PHX2.stage22.constants",
    "PHX2.stage22.errors",
    "PHX2.stage22.failure_handling",
    "PHX2.stage22.ingest_contracts",
)


def test_bounded_live_runner_imports_are_within_locked_allowlist():
    for mod in _collect_imports(BOUNDED_RUNNER_PATH):
        assert any(
            mod == prefix or mod.startswith(prefix + ".")
            for prefix in _BOUNDED_RUNNER_ALLOWED_IMPORT_PREFIXES
        ), (
            f"bounded_live_runner.py imports unexpected target {mod!r}; "
            f"allowed: {_BOUNDED_RUNNER_ALLOWED_IMPORT_PREFIXES}"
        )


# ---------------------------------------------------------------------------
# bounded_live_runner.py: no env / file I/O / clock / network / sleep
# ---------------------------------------------------------------------------


_BOUNDED_RUNNER_FORBIDDEN_TOP_MODULES: tuple[str, ...] = (
    "os",
    "time",
    "datetime",
    "calendar",
    "asyncio",
    "pathlib",
    "shutil",
    "tempfile",
    "csv",
    "requests",
    "httpx",
    "aiohttp",
    "urllib3",
    "websockets",
    "grpc",
    "grpcio",
    "discord",
    "telegram",
    "telethon",
    "sqlite3",
    "sqlalchemy",
    "dotenv",
    "keyring",
    "argparse",
    "click",
    "typer",
    "fire",
)


def test_bounded_live_runner_has_no_forbidden_top_module_imports():
    for mod in _collect_imports(BOUNDED_RUNNER_PATH):
        top = mod.split(".")[0]
        assert top not in _BOUNDED_RUNNER_FORBIDDEN_TOP_MODULES, (
            f"bounded_live_runner.py forbidden top-module import: {mod!r}"
        )


def test_bounded_live_runner_has_no_env_attribute_access():
    forbidden = {"environ", "getenv", "environb"}
    for attr in _collect_attribute_names(BOUNDED_RUNNER_PATH):
        assert attr not in forbidden, (
            f"bounded_live_runner.py forbidden env-read attribute "
            f"os.{attr}"
        )


def test_bounded_live_runner_has_no_while_loop():
    for node in ast.walk(_tree(BOUNDED_RUNNER_PATH)):
        assert not isinstance(node, ast.While), (
            "bounded_live_runner.py must not use ``while`` loops"
        )


def test_bounded_live_runner_has_no_async_function_def():
    for node in ast.walk(_tree(BOUNDED_RUNNER_PATH)):
        assert not isinstance(node, ast.AsyncFunctionDef)


def test_bounded_live_runner_has_no_main_guard():
    for node in ast.walk(_tree(BOUNDED_RUNNER_PATH)):
        if isinstance(node, ast.Compare):
            participants = [node.left] + list(node.comparators)
            has_name = any(
                isinstance(p, ast.Name) and p.id == "__name__"
                for p in participants
            )
            has_main = any(
                isinstance(p, ast.Constant) and p.value == "__main__"
                for p in participants
            )
            assert not (has_name and has_main), (
                "bounded_live_runner.py must not contain a "
                "__name__ == '__main__' guard"
            )


def test_bounded_live_runner_has_no_top_level_cli_function():
    forbidden = {"main", "cli", "entrypoint"}
    for node in _tree(BOUNDED_RUNNER_PATH).body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            assert node.name not in forbidden, (
                f"bounded_live_runner.py forbidden entrypoint "
                f"function {node.name!r}"
            )


# ---------------------------------------------------------------------------
# bounded_live_runner.py: forbidden source-text substrings
# ---------------------------------------------------------------------------


_FORBIDDEN_URL_SUBSTRINGS: tuple[str, ...] = (
    "https" + ":" + "//",
    "http" + ":" + "//",
    "wss" + ":" + "//",
    "ws" + ":" + "//",
    "discord" + "." + "com",
    "discordapp" + "." + "com",
    "hooks" + ".slack" + "." + "com",
)


def test_bounded_live_runner_has_no_url_literal_in_source():
    source = _read(BOUNDED_RUNNER_PATH)
    for needle in _FORBIDDEN_URL_SUBSTRINGS:
        assert needle not in source, (
            f"bounded_live_runner.py forbidden URL literal: {needle!r}"
        )


def test_live_composition_has_no_url_literal_in_source():
    source = _read(LIVE_COMPOSITION_PATH)
    for needle in _FORBIDDEN_URL_SUBSTRINGS:
        assert needle not in source, (
            f"live_composition.py forbidden URL literal: {needle!r}"
        )


# ---------------------------------------------------------------------------
# live_composition.py: locked import allowlist for Stage 21
# ---------------------------------------------------------------------------


_LIVE_COMPOSITION_ALLOWED_STAGE21_MODULES: frozenset[str] = frozenset({
    "PHX2.stage21.live_secrets_boundary",
    "PHX2.stage21.provider_adapter_helius",
    "PHX2.stage21.provider_event_decoder",
    "PHX2.stage21.discord_private_transport",
    "PHX2.stage21.transport_contracts",
    "PHX2.stage21.allowlist",
    "PHX2.stage21.secret_redaction",
})


_LIVE_COMPOSITION_ALLOWED_NON_STAGE21_PREFIXES: tuple[str, ...] = (
    "__future__",
    "collections.abc",
    "typing",
    "PHX2.stage22.constants",
    "PHX2.stage22.errors",
    "PHX2.stage22.ingest_contracts",
)


def test_live_composition_imports_only_from_locked_allowlist():
    imports = _collect_imports(LIVE_COMPOSITION_PATH)
    for mod in imports:
        if mod in _LIVE_COMPOSITION_ALLOWED_STAGE21_MODULES:
            continue
        assert any(
            mod == prefix or mod.startswith(prefix + ".")
            for prefix in _LIVE_COMPOSITION_ALLOWED_NON_STAGE21_PREFIXES
        ), (
            f"live_composition.py imports unexpected target {mod!r}"
        )


def test_live_composition_does_not_import_forbidden_stage21_neighbours():
    """The Stage 21.4 ``private_smoke_runner`` is NOT in the
    Stage 22.5 live-composition allowlist -- the Stage 22.5
    bounded runner is the only single-shot pass shipped by
    Stage 22.5. Stage 21 fake-path modules are also forbidden.
    """
    forbidden = {
        "PHX2.stage21.fake_provider",
        "PHX2.stage21.fake_transport",
        "PHX2.stage21.live_path_simulator",
        "PHX2.stage21.private_smoke_runner",
        "PHX2.stage21.config",
    }
    imports = _collect_imports(LIVE_COMPOSITION_PATH)
    leaked = sorted(imports & forbidden)
    assert not leaked, (
        f"live_composition.py imports forbidden Stage 21 modules: "
        f"{leaked!r}"
    )


def test_live_composition_has_no_env_attribute_access():
    forbidden = {"environ", "getenv", "environb"}
    for attr in _collect_attribute_names(LIVE_COMPOSITION_PATH):
        assert attr not in forbidden, (
            f"live_composition.py forbidden env-read attribute "
            f"os.{attr}"
        )


def test_live_composition_does_not_import_os():
    imports = _collect_imports(LIVE_COMPOSITION_PATH)
    for mod in imports:
        top = mod.split(".")[0]
        assert top != "os", (
            f"live_composition.py must not import os; got {mod!r}"
        )


def test_live_composition_has_no_while_loop():
    for node in ast.walk(_tree(LIVE_COMPOSITION_PATH)):
        assert not isinstance(node, ast.While)


def test_live_composition_has_no_async_function_def():
    for node in ast.walk(_tree(LIVE_COMPOSITION_PATH)):
        assert not isinstance(node, ast.AsyncFunctionDef)


def test_live_composition_has_no_main_guard():
    for node in ast.walk(_tree(LIVE_COMPOSITION_PATH)):
        if isinstance(node, ast.Compare):
            participants = [node.left] + list(node.comparators)
            has_name = any(
                isinstance(p, ast.Name) and p.id == "__name__"
                for p in participants
            )
            has_main = any(
                isinstance(p, ast.Constant) and p.value == "__main__"
                for p in participants
            )
            assert not (has_name and has_main)


def test_live_composition_has_no_top_level_cli_function():
    forbidden = {"main", "cli", "entrypoint"}
    for node in _tree(LIVE_COMPOSITION_PATH).body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            assert node.name not in forbidden


# ---------------------------------------------------------------------------
# Single-seam invariant: only live_composition.py imports the locked subset
# ---------------------------------------------------------------------------


def _iter_stage22_production_modules() -> list[Path]:
    return [
        p for p in STAGE22_ROOT.rglob("*.py")
        if "__pycache__" not in p.parts
    ]


def test_live_composition_is_only_stage22_file_with_locked_stage21_imports():
    for py_file in _iter_stage22_production_modules():
        if py_file.name == "live_composition.py":
            continue
        imports = _collect_imports(py_file)
        leaked = sorted(imports & _LIVE_COMPOSITION_ALLOWED_STAGE21_MODULES)
        assert not leaked, (
            f"{py_file.name}: imports live-composition-only Stage 21 "
            f"modules {leaked!r}"
        )


def test_no_stage21_file_was_modified_in_stage22_5():
    """Defensive: this test asserts the locked Stage 21 production
    files exist (and remain at their on-disk location). The git
    history is the authoritative check; this test catches the
    pathological accidental rename.
    """
    stage21_root = STAGE22_ROOT.parent / "stage21"
    must_exist = (
        "live_secrets_boundary.py",
        "provider_adapter_helius.py",
        "provider_event_decoder.py",
        "discord_private_transport.py",
        "transport_contracts.py",
        "allowlist.py",
        "secret_redaction.py",
    )
    for name in must_exist:
        assert (stage21_root / name).is_file(), (
            f"Stage 21 file {name!r} missing -- 22.5 must not move "
            f"Stage 21 production files"
        )


# ---------------------------------------------------------------------------
# Runner signature shape: all-keyword-only
# ---------------------------------------------------------------------------


def test_run_bounded_private_ingest_signature_is_all_keyword_only():
    from PHX2.stage22.bounded_live_runner import run_bounded_private_ingest

    sig = inspect.signature(run_bounded_private_ingest)
    for name, param in sig.parameters.items():
        assert param.kind is inspect.Parameter.KEYWORD_ONLY, (
            f"run_bounded_private_ingest parameter {name!r} is not "
            "keyword-only"
        )


def test_run_bounded_private_ingest_parameter_names_are_locked():
    from PHX2.stage22.bounded_live_runner import run_bounded_private_ingest

    sig = inspect.signature(run_bounded_private_ingest)
    assert list(sig.parameters.keys()) == [
        "provider_id",
        "chain",
        "observed_at_utc",
        "received_at_utc",
        "failed_at_utc",
        "readiness_check_fn",
        "fetch_outcome_fn",
        "decode_event_fn",
        "classify_decode_error_fn",
        "raw_capture_writer",
        "dedupe_ledger",
        "private_transport",
        "max_provider_attempts",
        "max_events",
        "max_dispatches",
        "stop_after_first_dispatch",
    ]


def test_run_bounded_private_ingest_default_values_are_locked():
    from PHX2.stage22.bounded_live_runner import run_bounded_private_ingest

    sig = inspect.signature(run_bounded_private_ingest)
    assert sig.parameters["max_provider_attempts"].default == 1
    assert sig.parameters["max_events"].default is None
    assert sig.parameters["max_dispatches"].default is None
    assert sig.parameters["stop_after_first_dispatch"].default is False


# ---------------------------------------------------------------------------
# 22.5 does NOT introduce new INGEST_RUNNER_OUTCOMES tokens
# ---------------------------------------------------------------------------


def test_stage22_5_does_not_add_new_ingest_runner_outcomes():
    """The Stage 22.5 runner returns existing
    ``INGEST_RUNNER_OUTCOMES`` tokens only. The locked tuple
    remains the Stage 22.1 eight-token set; no token was added
    or removed at 22.5.
    """
    assert c.INGEST_RUNNER_OUTCOMES == (
        "ok",
        "readiness_not_ready",
        "provider_failed",
        "provider_returned_zero",
        "all_malformed",
        "all_duplicates",
        "transport_refused",
        "max_attempts_exhausted",
    )


# ---------------------------------------------------------------------------
# Rolling production-file set includes the 22.5 files
# ---------------------------------------------------------------------------


def test_bounded_live_runner_is_in_rolling_locked_set():
    boundary_source = (
        STAGE22_ROOT.parent
        / "tests"
        / "stage22"
        / "test_stage_22_1_boundaries.py"
    ).read_text(encoding="utf-8")
    assert '"bounded_live_runner.py"' in boundary_source


def test_live_composition_is_in_rolling_locked_set():
    boundary_source = (
        STAGE22_ROOT.parent
        / "tests"
        / "stage22"
        / "test_stage_22_1_boundaries.py"
    ).read_text(encoding="utf-8")
    assert '"live_composition.py"' in boundary_source


# ---------------------------------------------------------------------------
# 22.5 runner error type
# ---------------------------------------------------------------------------


def test_stage22_runner_error_is_importable_from_errors_module():
    from PHX2.stage22.errors import Stage22RunnerError

    assert issubclass(Stage22RunnerError, Exception)

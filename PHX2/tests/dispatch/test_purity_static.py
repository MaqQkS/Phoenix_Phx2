"""Static purity checks on Stage 8B source files."""

import ast
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
DISPATCH_ROOT = REPO_ROOT / "PHX2" / "dispatch"


def _imports(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name
        elif isinstance(node, ast.ImportFrom):
            if node.module is not None:
                yield node.module


def test_dispatcher_does_not_import_engine_or_renderer_or_assembler():
    path = DISPATCH_ROOT / "dispatcher.py"
    forbidden = {
        "PHX2.services.alert_eligibility_engine",
        "PHX2.renderers.alert_renderer",
        "PHX2.renderers.context",
    }
    seen = set(_imports(path))
    for module in forbidden:
        assert module not in seen, f"dispatcher.py must not import {module}"


def test_preview_pipeline_imports_only_collaborators_and_alert_decision():
    path = DISPATCH_ROOT / "preview_pipeline.py"
    seen = list(_imports(path))
    # Collaborators and AlertDecision are the only PHX2 imports allowed.
    allowed = {
        "PHX2.dispatch.dispatcher",
        "PHX2.models",
        "PHX2.renderers.alert_renderer",
        "PHX2.renderers.context",
    }
    phx2_imports = [imp for imp in seen if imp.startswith("PHX2")]
    for imp in phx2_imports:
        assert imp in allowed, (
            f"preview_pipeline.py imports unexpected module {imp!r}; "
            f"allowed: {sorted(allowed)}"
        )


@pytest.mark.parametrize(
    "filename",
    ["base.py", "console.py", "file_preview.py", "discord.py"],
    ids=lambda x: x,
)
def test_sink_files_do_not_import_repository_or_service(filename: str):
    path = DISPATCH_ROOT / "sinks" / filename
    seen = list(_imports(path))
    for imp in seen:
        assert not imp.startswith("PHX2.db"), (
            f"sinks/{filename} imports forbidden module {imp}"
        )
        assert not imp.startswith("PHX2.services"), (
            f"sinks/{filename} imports forbidden module {imp}"
        )


@pytest.mark.parametrize(
    "filename",
    ["base.py", "console.py", "file_preview.py", "discord.py"],
    ids=lambda x: x,
)
def test_sink_files_do_not_call_datetime_now(filename: str):
    path = DISPATCH_ROOT / "sinks" / filename
    contents = path.read_text(encoding="utf-8")
    assert "datetime.now" not in contents, (
        f"sinks/{filename} must not call datetime.now"
    )
    assert "datetime.utcnow" not in contents, (
        f"sinks/{filename} must not call datetime.utcnow"
    )


def test_discord_sink_does_not_import_http_libraries_directly():
    """DiscordSink must depend on HttpClient only — no requests/httpx/urllib."""

    path = DISPATCH_ROOT / "sinks" / "discord.py"
    forbidden = {"requests", "httpx", "urllib", "urllib3", "aiohttp", "http.client"}
    seen = list(_imports(path))
    for imp in seen:
        # ``imp`` may be a top-level module ('requests') or a submodule
        # ('urllib.request') — check both as a prefix so 'urllib' catches
        # 'urllib.request', and as exact match for the rest.
        for module in forbidden:
            assert imp != module and not imp.startswith(module + "."), (
                f"sinks/discord.py imports forbidden HTTP module {imp}"
            )


def test_no_phoenix1_imports_in_dispatch_tree():
    for path in DISPATCH_ROOT.rglob("*.py"):
        for imp in _imports(path):
            assert not imp.startswith("phoenix1"), (
                f"{path.relative_to(REPO_ROOT)} imports phoenix1 module {imp}"
            )


def test_engine_only_imports_preview_pipeline_under_type_checking():
    """The engine must reference PreviewPipeline only as a type, not at runtime."""

    engine_path = REPO_ROOT / "PHX2" / "services" / "alert_eligibility_engine.py"
    tree = ast.parse(engine_path.read_text(encoding="utf-8"))

    runtime: list = []
    type_checking: list = []

    class Visitor(ast.NodeVisitor):
        def __init__(self) -> None:
            self.in_tc = False

        def visit_If(self, node: ast.If) -> None:
            is_tc = (
                isinstance(node.test, ast.Name) and node.test.id == "TYPE_CHECKING"
            )
            if is_tc:
                prior = self.in_tc
                self.in_tc = True
                self.generic_visit(node)
                self.in_tc = prior
            else:
                self.generic_visit(node)

        def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
            module = node.module or ""
            if module.startswith("PHX2.dispatch"):
                if self.in_tc:
                    type_checking.append(module)
                else:
                    runtime.append(module)

    Visitor().visit(tree)

    assert runtime == [], f"Engine has runtime PHX2.dispatch imports: {runtime}"

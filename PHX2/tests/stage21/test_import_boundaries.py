"""Stage 21 import boundary tests.

Mirrors the Stage 20 test_import_boundaries.py shape with the
Stage 21 specifics:

  * No import of Phoenix1.
  * No import of PHX2.stage17, PHX2.stage18, PHX2.stage19,
    PHX2.stage20.
  * No import of PHX2.db / PHX2.repositories / PHX2.config /
    PHX2.models / PHX2.services / PHX2.dispatch.
  * No top-level import of a network / messaging / scheduler /
    DB / secrets library (substring match against lowered import
    name).

The checks run AST-level on Stage 21 production .py files only
(``PHX2/stage21/**``). Test files under ``PHX2/tests/stage21/`` are
deliberately exempt -- tests are allowed to import network /
messaging library names if needed for future work, but 21.1's
tests do not.

AUDIT-001: the import-target collector reconstructs every form
of import edge, including:

  * ``import X``
  * ``import X.Y``
  * ``import X as alias`` / ``import X.Y as alias``
  * ``from X import name`` (covers ``from PHX2 import stage20``)
  * ``from X import name as alias``
  * ``from X.Y import name``
  * Dynamic ``importlib.import_module("X.Y")``,
    ``import_module("X.Y")``, and ``__import__("X.Y")`` calls with
    string-literal targets.

Each form contributes its fully-qualified target string(s) to the
collected set, so a forbidden-prefix check catches every variant.
"""

from __future__ import annotations

import ast
from pathlib import Path


STAGE21_ROOT = Path(__file__).parent.parent.parent / "stage21"


_FORBIDDEN_PRIOR_STAGE_PREFIXES: tuple[str, ...] = (
    "PHX2.stage17",
    "PHX2.stage18",
    "PHX2.stage19",
    "PHX2.stage20",
)


_FORBIDDEN_PHX2_RUNTIME_PREFIXES: tuple[str, ...] = (
    # Stage 21 runtime must not reach into the live PHX2 service
    # layer / DB layer / config layer. Stage 21.1 is artifact-based
    # and has no need for any of those.
    "PHX2.db",
    "PHX2.repositories",
    "PHX2.config",
    "PHX2.models",
    "PHX2.services",
    "PHX2.dispatch",
    "PHX2.filters",
    "PHX2.integrations",
    "PHX2.renderers",
    "PHX2.scripts",
    "PHX2.analysis",
)


_FORBIDDEN_RUNTIME_MODULE_PATTERNS: tuple[str, ...] = (
    # Network / RPC
    "requests",
    "httpx",
    "aiohttp",
    "urllib3",
    "websockets",
    "grpc",
    "grpcio",
    # Provider clients (substring match against lowered import name)
    "helius",
    "birdeye",
    "dexscreener",
    "jupiter",
    "jito",
    # Messaging
    "discord",
    "telegram",
    "telethon",
    "webhook",
    # Scheduler / daemon
    "apscheduler",
    "celery",
    "schedule",
    "crontab",
    "daemon",
    # DB
    "sqlalchemy",
    "sqlite3",
    # Secrets-management libs
    "dotenv",
    "keyring",
)


_DYNAMIC_IMPORT_FUNC_NAMES: frozenset[str] = frozenset({
    "import_module",
    "__import__",
})


def _iter_production_modules() -> list[Path]:
    """All .py files under PHX2/stage21/ excluding __pycache__."""
    return [
        p for p in STAGE21_ROOT.rglob("*.py")
        if "__pycache__" not in p.parts
    ]


def _collect_import_targets_from_source(
    source: str,
) -> tuple[set[str], set[str]]:
    """Return ``(modules, full_targets)`` for ``source``.

    * ``modules``      -- the set of imported module paths (the
      "left-hand side" of every import edge). Examples:
        ``import X``                       -> ``"X"``
        ``import X.Y``                     -> ``"X.Y"``
        ``from X import name``             -> ``"X"``
        ``from X.Y import name``           -> ``"X.Y"``
        ``importlib.import_module("X.Y")`` -> ``"X.Y"``
    * ``full_targets`` -- ``modules`` plus the ``X.member`` form
      reconstructed from every ``from X import name``. Used by
      the prior-stage / Phoenix1 prefix checks because
      ``from PHX2 import stage20`` only reveals the forbidden
      target after reconstruction.

    Pattern-substring checks (e.g. ``"webhook"``) consult
    ``modules`` ONLY -- otherwise legitimate identifier names
    like ``ENV_VAR_DISCORD_WEBHOOK_URL`` imported from a Stage 21
    constants module would trip the runtime-pattern test.

    Dynamic-import aliasing is supported:
      * ``from importlib import import_module as _im`` binds
        ``_im`` as an alias for ``importlib.import_module``;
      * ``_im("PHX2.stage20")`` is detected the same way the bare
        ``import_module("PHX2.stage20")`` form is.

    Comment / docstring mentions of module names do not
    contribute because they never produce an Import / ImportFrom
    / Call AST node.
    """
    tree = ast.parse(source)
    modules: set[str] = set()
    full_targets: set[str] = set()

    # Pass 1: collect aliases for the dynamic-import functions.
    dynamic_import_aliases: set[str] = set(_DYNAMIC_IMPORT_FUNC_NAMES)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "importlib":
            for alias in node.names:
                if alias.name in _DYNAMIC_IMPORT_FUNC_NAMES:
                    bound_name = alias.asname or alias.name
                    dynamic_import_aliases.add(bound_name)

    # Pass 2: record edges.
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                # alias.name is the dotted module path, e.g. "PHX2.stage20"
                modules.add(alias.name)
                full_targets.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if mod:
                modules.add(mod)
                full_targets.add(mod)
            for alias in node.names:
                if mod:
                    # ``from PHX2 import stage20`` -> "PHX2.stage20"
                    # ``from PHX2.stage21 import X`` -> "PHX2.stage21.X"
                    full_targets.add(f"{mod}.{alias.name}")
        elif isinstance(node, ast.Call):
            func = node.func
            is_dynamic_import = False
            if isinstance(func, ast.Attribute) and func.attr == "import_module":
                # ``importlib.import_module("X")`` / aliased receiver
                is_dynamic_import = True
            elif isinstance(func, ast.Name) and func.id in dynamic_import_aliases:
                is_dynamic_import = True
            if is_dynamic_import and node.args:
                first = node.args[0]
                if isinstance(first, ast.Constant) and isinstance(first.value, str):
                    modules.add(first.value)
                    full_targets.add(first.value)

    return modules, full_targets


def _collect_modules(file_path: Path) -> set[str]:
    modules, _ = _collect_import_targets_from_source(
        file_path.read_text(encoding="utf-8")
    )
    return modules


def _collect_full_targets(file_path: Path) -> set[str]:
    _, full = _collect_import_targets_from_source(
        file_path.read_text(encoding="utf-8")
    )
    return full


# ---------------------------------------------------------------------------
# Production-tree checks
# ---------------------------------------------------------------------------


def test_at_least_one_production_module_exists():
    files = _iter_production_modules()
    assert files, "expected at least one production .py under stage21"


def test_no_phoenix1_imports():
    for py_file in _iter_production_modules():
        for target in _collect_full_targets(py_file):
            assert not target.startswith("phoenix1"), (
                f"{py_file}: forbidden phoenix1 import target {target!r}"
            )


def test_no_prior_stage_runtime_imports():
    for py_file in _iter_production_modules():
        for target in _collect_full_targets(py_file):
            for forbidden in _FORBIDDEN_PRIOR_STAGE_PREFIXES:
                assert not target.startswith(forbidden), (
                    f"{py_file}: forbidden prior-stage target {target!r}"
                )


def test_no_phx2_runtime_layer_imports():
    for py_file in _iter_production_modules():
        for target in _collect_full_targets(py_file):
            for forbidden in _FORBIDDEN_PHX2_RUNTIME_PREFIXES:
                assert not target.startswith(forbidden), (
                    f"{py_file}: forbidden PHX2 runtime-layer target "
                    f"{target!r}"
                )


def test_no_forbidden_runtime_module_patterns():
    # Module-paths only -- identifier names imported FROM a Stage 21
    # module (e.g. ``ENV_VAR_DISCORD_WEBHOOK_URL``) are not module
    # imports and must not be substring-checked against runtime
    # library patterns.
    for py_file in _iter_production_modules():
        for module in _collect_modules(py_file):
            lower = module.lower()
            for pattern in _FORBIDDEN_RUNTIME_MODULE_PATTERNS:
                assert pattern not in lower, (
                    f"{py_file}: forbidden module pattern {pattern!r} "
                    f"in import target {module!r}"
                )


def test_no_bot_db_reference_anywhere_in_stage21_source():
    # Substring check is appropriate here: the bot.db path is a
    # file-name literal, not an import identifier. Docstring
    # mentions in the Stage 21 prohibition text use the phrasing
    # "Phoenix1 sqlite filename" instead.
    for py_file in _iter_production_modules():
        source = py_file.read_text(encoding="utf-8")
        assert "bot.db" not in source, (
            f"{py_file}: forbidden 'bot.db' reference in source"
        )


def test_no_url_literals_in_production_source():
    """Stage 21 production code must not contain https:// or wss://.

    Stage 21.1 has no need for URL literals anywhere; even in
    docstrings. The provider / transport adapters are deferred to
    later sub-stages and they will need to introduce URLs, but
    they must do so via the SecretRef boundary -- never as a
    source-level literal.
    """
    for py_file in _iter_production_modules():
        source = py_file.read_text(encoding="utf-8")
        assert "https://" not in source, (
            f"{py_file}: forbidden 'https://' in source"
        )
        assert "wss://" not in source, (
            f"{py_file}: forbidden 'wss://' in source"
        )


def test_no_top_level_network_side_effect_on_import():
    """Importing every Stage 21 production module is side-effect-free.

    A "side effect" here is a top-level statement that issues a
    network call or opens a connection. The AST check rejects any
    top-level statement that is not one of the allowed shapes
    (declarations, simple assignments, etc.).
    """
    allowed_top_level = (
        ast.Import,
        ast.ImportFrom,
        ast.ClassDef,
        ast.FunctionDef,
        ast.AsyncFunctionDef,
        ast.Assign,
        ast.AnnAssign,
        ast.AugAssign,
        ast.If,
        ast.Try,
        ast.Expr,  # docstrings live inside Expr nodes
    )
    for py_file in _iter_production_modules():
        source = py_file.read_text(encoding="utf-8")
        tree = ast.parse(source)
        for node in tree.body:
            assert isinstance(node, allowed_top_level), (
                f"{py_file}: unexpected top-level node {type(node).__name__}"
            )


# ---------------------------------------------------------------------------
# Negative fixtures: prove the collector flags every problem shape
# ---------------------------------------------------------------------------


def _has_forbidden_prior_stage(source: str) -> bool:
    """Helper: does ``source`` import any forbidden prior-stage path?"""
    _, full_targets = _collect_import_targets_from_source(source)
    for target in full_targets:
        for forbidden in _FORBIDDEN_PRIOR_STAGE_PREFIXES:
            if target.startswith(forbidden):
                return True
    return False


def test_collector_catches_dotted_from_import_with_member():
    source = "from PHX2.stage20.constants import STAGE20_VERSION\n"
    assert _has_forbidden_prior_stage(source)


def test_collector_catches_from_phx2_import_stage20():
    source = "from PHX2 import stage20\n"
    assert _has_forbidden_prior_stage(source)


def test_collector_catches_from_phx2_import_stage20_aliased():
    source = "from PHX2 import stage20 as s20\n"
    assert _has_forbidden_prior_stage(source)


def test_collector_catches_import_dotted_phx2_stage20():
    source = "import PHX2.stage20\n"
    assert _has_forbidden_prior_stage(source)


def test_collector_catches_import_dotted_phx2_stage20_aliased():
    source = "import PHX2.stage20 as s20\n"
    assert _has_forbidden_prior_stage(source)


def test_collector_catches_importlib_import_module_literal():
    source = (
        "import importlib\n"
        "m = importlib.import_module('PHX2.stage20.constants')\n"
    )
    assert _has_forbidden_prior_stage(source)


def test_collector_catches_bare_import_module_literal():
    source = (
        "from importlib import import_module\n"
        "m = import_module('PHX2.stage20')\n"
    )
    assert _has_forbidden_prior_stage(source)


def test_collector_catches_dunder_import_literal():
    source = "__import__('PHX2.stage20.constants')\n"
    assert _has_forbidden_prior_stage(source)


def test_collector_does_not_catch_docstring_mention():
    # A docstring mentioning ``PHX2.stage20`` must NOT be flagged
    # by the collector; only real import edges are.
    source = '"""Docstring mentions PHX2.stage20 but does not import it."""\n'
    assert not _has_forbidden_prior_stage(source)


def test_collector_does_not_catch_string_literal_mention():
    # A bare string literal mentioning ``PHX2.stage20`` is not an
    # import; the collector only inspects Import / ImportFrom /
    # dynamic-import Calls.
    source = "_REFERENCE = 'PHX2.stage20.constants'\n"
    assert not _has_forbidden_prior_stage(source)


def test_collector_catches_aliased_importlib():
    # ``from importlib import import_module as _im`` then
    # ``_im("PHX2.stage20")`` -- the function lookup is by Name id,
    # so the binding is matched.
    source = (
        "from importlib import import_module as _im\n"
        "m = _im('PHX2.stage20')\n"
    )
    assert _has_forbidden_prior_stage(source)


def test_collector_catches_db_via_from_phx2_import_db():
    source = "from PHX2 import db\n"
    _, full_targets = _collect_import_targets_from_source(source)
    assert "PHX2.db" in full_targets


def test_collector_catches_db_via_dynamic_import():
    source = "import importlib\nimportlib.import_module('PHX2.db.repositories')\n"
    modules, _ = _collect_import_targets_from_source(source)
    # The dynamic call adds the literal string verbatim into the
    # modules set so the module-prefix tests catch it.
    assert "PHX2.db.repositories" in modules


def test_collector_ignores_non_string_dynamic_import_arg():
    # ``__import__(some_var)`` cannot be analyzed statically; the
    # collector simply skips non-literal arguments. This is a
    # known-soft-spot acknowledged here.
    source = "name = 'PHX2.stage20'\n__import__(name)\n"
    modules, full_targets = _collect_import_targets_from_source(source)
    # The literal-string content of ``name`` is not picked up.
    assert "PHX2.stage20" not in modules
    assert "PHX2.stage20" not in full_targets


def test_module_set_does_not_include_member_names():
    # ``from X import name`` puts X in modules but X.name only in
    # full_targets -- the substring/pattern checks therefore won't
    # trip on benign identifier names like ENV_VAR_..._WEBHOOK_URL.
    source = (
        "from PHX2.stage21.constants import ENV_VAR_DISCORD_WEBHOOK_URL\n"
    )
    modules, full_targets = _collect_import_targets_from_source(source)
    assert "PHX2.stage21.constants" in modules
    assert "PHX2.stage21.constants.ENV_VAR_DISCORD_WEBHOOK_URL" not in modules
    assert "PHX2.stage21.constants.ENV_VAR_DISCORD_WEBHOOK_URL" in full_targets

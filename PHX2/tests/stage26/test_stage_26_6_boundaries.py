"""Stage 26.6 file-scope / import-boundary / vocabulary tests.

These tests focus specifically on the Stage 26.6 production files
(``review_packet_constants.py`` / ``review_packet_models.py`` /
``review_packet_builder.py`` / ``review_packet_writer.py``) and
pin:

  * No Stage 21 / 22 / 23 / 24 import.
  * No direct ``PHX2.stage25`` import; Stage 25 vocabulary is
    reached via Stage 26.1 / 26.5 surfaces or declared locally in
    Stage 26.6.
  * No network / RPC / messaging / DB / scheduler / secrets library.
  * No CLI entrypoint, no ``__name__ == "__main__"`` guard.
  * No filesystem writer call (``write_text`` / ``unlink`` /
    ``rmdir`` / ``rmtree`` / ``replace`` / ``rename`` / ``touch`` /
    ``mkdir``) OUTSIDE ``review_packet_writer.py``. The writer is
    narrowly admitted to call ``write_bytes`` because Stage 26.6
    explicitly admits a deterministic offline review-only writer.
  * No ``open(..., "w")`` / append / exclusive mode -- the writer
    uses ``Path.write_bytes`` rather than ``open()``.
  * No ``os.environ`` / ``os.getenv``.
  * No URL literal.
  * No Stage 26.7+ file name shipped (closure audit / Stage 27
    handoff / runner / CLI / dispatch).
  * No Stage 26.7+ vocabulary identifier (operator approval actor
    populated / approval timestamp populated / runtime artifact /
    enforcement actor / dispatch / live routing / subscriber tier
    / etc.).
"""

from __future__ import annotations

import ast
from pathlib import Path


STAGE26_ROOT: Path = (
    Path(__file__).resolve().parent.parent.parent / "stage26"
)


_STAGE_26_6_PRODUCTION_FILENAMES: tuple[str, ...] = (
    "review_packet_constants.py",
    "review_packet_models.py",
    "review_packet_builder.py",
    "review_packet_writer.py",
)


_STAGE_26_6_WRITER_FILENAME: str = "review_packet_writer.py"


_FORBIDDEN_PRIOR_STAGE_PREFIXES: tuple[str, ...] = (
    "PHX2.stage17",
    "PHX2.stage18",
    "PHX2.stage19",
    "PHX2.stage20",
    "PHX2.stage21",
    "PHX2.stage22",
    "PHX2.stage23",
    "PHX2.stage24",
)


_FORBIDDEN_RUNTIME_MODULE_PATTERNS: tuple[str, ...] = (
    "requests",
    "httpx",
    "aiohttp",
    "urllib3",
    "websockets",
    "grpc",
    "grpcio",
    "helius",
    "jupiter",
    "discord",
    "telegram",
    "telethon",
    "webhook",
    "apscheduler",
    "celery",
    "schedule",
    "crontab",
    "daemon",
    "sqlalchemy",
    "sqlite3",
    "dotenv",
    "keyring",
)


_FORBIDDEN_CLI_OR_SLEEP_TOP_LEVEL_MODULES: frozenset[str] = frozenset(
    {"argparse", "click", "typer", "fire", "docopt", "time", "asyncio"}
)


_FORBIDDEN_FILE_PERSISTENCE_TOP_LEVEL_MODULES: frozenset[str] = frozenset(
    {"shutil", "tempfile", "csv"}
)


_FORBIDDEN_PHX2_RUNTIME_PREFIXES: tuple[str, ...] = (
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


# Stage 26.7+ vocabulary the Stage 26.6 files MUST NOT introduce.
# ``review_packet`` / ``operator_review`` / ``approval_handoff`` /
# ``approval_required`` / ``approval_status`` / ``approval_actor`` /
# ``approval_timestamp`` / ``approval_notes`` are Stage 26.6's
# locked vocabulary and are admitted here. ``enforcement_enabled``
# is the locked Stage 26.5 / 26.6 safety-lock label and is narrowly
# admitted via the ``_identifier_admits_enforcement_enabled`` helper
# below. ``approved_by`` is explicitly forbidden because Stage 26.6
# uses ``approval_actor`` (which remains unset) rather than a
# populated ``approved_by``.
_FORBIDDEN_DOMAIN_SUBSTRINGS_FOR_STAGE_26_6: tuple[str, ...] = (
    "approval_state",
    "approved_by",
    "auto_approved",
    "enforcer",
    "ratchet",
    "tweet",
    "twitter",
    "x_api",
    "subscriber_tier",
    "dispatcher",
    "telegram",
    "discord",
    "axiom",
    "jito",
    "compute_budget",
    "router_fee",
    "live_router",
    "public_subscriber",
    "private_subscriber",
    "runtime_runner",
)


# Stage 26.6 narrowly admits the substring ``enforcement`` as part
# of (a) the locked Stage 26.5 / 26.6 safety-lock label
# ``enforcement_enabled``, and (b) the locked Stage 26.6 review-
# packet defensive label ``enforcement_leak`` (so the
# ``BLOCKED_ENFORCEMENT_LEAK`` packet status and the
# ``STG26_CAL_REVIEW_PACKET_ENFORCEMENT_LEAK`` typed-error code
# token can ship under their spec-locked names).
_ENFORCEMENT_ENABLED_FRAGMENT: str = "enforcement_enabled"
_ENFORCEMENT_LEAK_FRAGMENT: str = "enforcement_leak"


_FORBIDDEN_URL_LITERAL_SUBSTRINGS: tuple[str, ...] = (
    "h" + "ttps://",
    "h" + "ttp://",
    "w" + "ss://",
    "w" + "s://",
    "discord" + ".com",
    "discordapp" + ".com",
    "hooks" + ".slack.com",
)


_FORBIDDEN_WRITER_ATTRIBUTE_NAMES_OUTSIDE_WRITER: frozenset[str] = frozenset(
    {
        "write_text",
        "unlink",
        "rmdir",
        "rmtree",
        "replace",
        "rename",
        "touch",
        "mkdir",
    }
)


_FORBIDDEN_WRITER_ATTRIBUTE_NAMES_IN_WRITER: frozenset[str] = frozenset(
    {
        "write_text",
        "unlink",
        "rmdir",
        "rmtree",
        "replace",
        "rename",
        "touch",
        "mkdir",
    }
)


_FORBIDDEN_OPEN_MODE_TOKENS: frozenset[str] = frozenset(
    {"w", "wb", "w+", "wb+", "a", "ab", "x", "xb"}
)


_ENV_ATTR_NAMES: frozenset[str] = frozenset(
    {"environ", "getenv", "environb"}
)


# Stage 26.7+ file-basename surfaces Stage 26.6 must not introduce.
_FORBIDDEN_FUTURE_SUBSTAGE_BASENAMES: tuple[str, ...] = (
    "review_packet.py",  # single-file shim
    "operator_review.py",  # single-file shim
    "operator_approval.py",
    "approval.py",
    "approval_packet.py",
    "runner.py",
    "live_runner.py",
    "cli.py",
    "main.py",
    "scheduler.py",
    "daemon.py",
    "dispatch.py",
    "dispatcher.py",
    "telegram.py",
    "discord.py",
    "x_api.py",
    "social.py",
    "enforcement.py",
    "live_router.py",
    "subscriber_router.py",
    "stage27_handoff.py",
)


def _iter_stage26_6_production_files() -> list[Path]:
    return [
        STAGE26_ROOT / name for name in _STAGE_26_6_PRODUCTION_FILENAMES
    ]


def _read_source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _collect_imports(source: str) -> tuple[set[str], set[str]]:
    tree = ast.parse(source)
    modules: set[str] = set()
    full: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.add(alias.name)
                full.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if mod:
                modules.add(mod)
                full.add(mod)
                for alias in node.names:
                    full.add(f"{mod}.{alias.name}")
    return modules, full


def _collect_call_func_chain_names(source: str) -> set[str]:
    tree = ast.parse(source)
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func: ast.expr = node.func
            while isinstance(func, ast.Attribute):
                names.add(func.attr)
                func = func.value
            if isinstance(func, ast.Name):
                names.add(func.id)
    return names


def _collect_open_calls(source: str) -> list[ast.Call]:
    tree = ast.parse(source)
    calls: list[ast.Call] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id == "open":
                calls.append(node)
            elif isinstance(func, ast.Attribute) and func.attr == "open":
                calls.append(node)
    return calls


def _extract_all_identifiers(source: str) -> set[str]:
    tree = ast.parse(source)
    idents: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            idents.add(node.id)
        elif isinstance(node, ast.Attribute):
            idents.add(node.attr)
        elif isinstance(
            node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
        ):
            idents.add(node.name)
        elif isinstance(node, ast.arg):
            idents.add(node.arg)
        elif isinstance(node, ast.keyword) and node.arg:
            idents.add(node.arg)
        elif isinstance(node, ast.alias):
            idents.add(node.name)
            if node.asname:
                idents.add(node.asname)
    return idents


def _identifier_admits_enforcement_enabled(ident_lower: str) -> bool:
    if "enforcement" not in ident_lower:
        return True
    stripped = ident_lower.replace(_ENFORCEMENT_ENABLED_FRAGMENT, "")
    stripped = stripped.replace(_ENFORCEMENT_LEAK_FRAGMENT, "")
    return "enforcement" not in stripped


# ---------------------------------------------------------------------------
# Stage 26.6 file inventory
# ---------------------------------------------------------------------------


def test_stage_26_6_production_files_exist():
    for name in _STAGE_26_6_PRODUCTION_FILENAMES:
        path = STAGE26_ROOT / name
        assert path.is_file(), (
            f"missing Stage 26.6 production file {name!r}"
        )


def test_no_forbidden_future_substage_files_present():
    for basename in _FORBIDDEN_FUTURE_SUBSTAGE_BASENAMES:
        assert not (STAGE26_ROOT / basename).exists(), (
            f"Stage 26 must not ship {basename!r}; reserved for "
            "Stage 26.7+"
        )


# ---------------------------------------------------------------------------
# Stage 26.6 import boundaries
# ---------------------------------------------------------------------------


def test_no_stage_26_6_imports_prior_stage():
    for path in _iter_stage26_6_production_files():
        _, full = _collect_imports(_read_source(path))
        for target in full:
            for forbidden in _FORBIDDEN_PRIOR_STAGE_PREFIXES:
                assert not target.startswith(forbidden), (
                    f"{path.name}: forbidden prior-stage import {target!r}"
                )


def test_no_stage_26_6_imports_stage25_directly():
    """Stage 26.6 must NOT import from ``PHX2.stage25`` directly.

    Stage 25 vocabulary is reached via Stage 26.1 / 26.5 surfaces
    (the whitelist module is the only Stage 26 module permitted to
    import from ``PHX2.stage25``).
    """
    for path in _iter_stage26_6_production_files():
        modules, _ = _collect_imports(_read_source(path))
        for module in modules:
            assert not module.startswith("PHX2.stage25"), (
                f"{path.name}: forbidden Stage 25 import {module!r}; "
                "Stage 26.6 must consume Stage 25 vocabulary via "
                "Stage 26.1 / 26.5 surfaces"
            )


def test_no_stage_26_6_imports_runtime_module_patterns():
    for path in _iter_stage26_6_production_files():
        modules, _ = _collect_imports(_read_source(path))
        for module in modules:
            lower = module.lower()
            for pattern in _FORBIDDEN_RUNTIME_MODULE_PATTERNS:
                assert pattern not in lower, (
                    f"{path.name}: forbidden runtime pattern "
                    f"{pattern!r} in import target {module!r}"
                )


def test_no_stage_26_6_imports_cli_or_sleep_libs():
    for path in _iter_stage26_6_production_files():
        modules, _ = _collect_imports(_read_source(path))
        for module in modules:
            top = module.split(".")[0]
            assert top not in _FORBIDDEN_CLI_OR_SLEEP_TOP_LEVEL_MODULES, (
                f"{path.name}: forbidden CLI/sleep import {module!r}"
            )


def test_no_stage_26_6_imports_file_persistence_libs():
    for path in _iter_stage26_6_production_files():
        modules, _ = _collect_imports(_read_source(path))
        for module in modules:
            top = module.split(".")[0]
            assert top not in _FORBIDDEN_FILE_PERSISTENCE_TOP_LEVEL_MODULES, (
                f"{path.name}: forbidden file-persistence import {module!r}"
            )


def test_no_stage_26_6_imports_phx2_runtime_layer():
    for path in _iter_stage26_6_production_files():
        _, full = _collect_imports(_read_source(path))
        for target in full:
            for forbidden in _FORBIDDEN_PHX2_RUNTIME_PREFIXES:
                assert not target.startswith(forbidden), (
                    f"{path.name}: forbidden PHX2 runtime-layer target "
                    f"{target!r}"
                )


# ---------------------------------------------------------------------------
# Env / CLI / writer / URL boundary
# ---------------------------------------------------------------------------


def test_no_stage_26_6_reads_environ():
    for path in _iter_stage26_6_production_files():
        source = _read_source(path)
        tree = ast.parse(source)
        os_aliases: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "os":
                        os_aliases.add(alias.asname or alias.name)
            elif isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                if mod == "os":
                    for alias in node.names:
                        assert alias.name not in _ENV_ATTR_NAMES, (
                            f"{path.name}: forbidden env-read import "
                            f"{alias.name!r}"
                        )
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute):
                if (
                    isinstance(node.value, ast.Name)
                    and node.value.id in os_aliases
                ):
                    assert node.attr not in _ENV_ATTR_NAMES, (
                        f"{path.name}: forbidden os.{node.attr}"
                    )


def test_no_stage_26_6_defines_cli_entrypoint():
    forbidden_names = {"main", "cli", "entrypoint"}
    for path in _iter_stage26_6_production_files():
        tree = ast.parse(_read_source(path))
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                assert node.name not in forbidden_names, (
                    f"{path.name}: forbidden CLI-style entrypoint "
                    f"{node.name!r}"
                )


def test_no_stage_26_6_has_dunder_main_guard():
    for path in _iter_stage26_6_production_files():
        tree = ast.parse(_read_source(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Compare):
                participants: list[ast.expr] = [node.left]
                participants.extend(node.comparators)
                has_name = any(
                    isinstance(p, ast.Name) and p.id == "__name__"
                    for p in participants
                )
                has_main = any(
                    isinstance(p, ast.Constant) and p.value == "__main__"
                    for p in participants
                )
                assert not (has_name and has_main), (
                    f"{path.name}: forbidden __name__ == '__main__' guard"
                )


def test_no_stage_26_6_has_url_literal():
    for path in _iter_stage26_6_production_files():
        source = _read_source(path)
        for needle in _FORBIDDEN_URL_LITERAL_SUBSTRINGS:
            assert needle not in source, (
                f"{path.name}: forbidden URL literal {needle!r}"
            )


def test_no_stage_26_6_calls_forbidden_writer_apis_outside_writer():
    """Every Stage 26.6 file other than ``review_packet_writer.py``
    must NOT call ``write_text`` / ``write_bytes`` / ``unlink`` /
    ``rmdir`` / ``rmtree`` / ``replace`` / ``rename`` / ``touch`` /
    ``mkdir``. The writer is narrowly admitted to call
    ``write_bytes`` because Stage 26.6 explicitly admits a
    deterministic offline review-only writer.
    """
    forbidden_outside_writer = (
        _FORBIDDEN_WRITER_ATTRIBUTE_NAMES_OUTSIDE_WRITER | {"write_bytes"}
    )
    for path in _iter_stage26_6_production_files():
        called_names = _collect_call_func_chain_names(
            _read_source(path)
        )
        if path.name == _STAGE_26_6_WRITER_FILENAME:
            leaked = sorted(
                called_names & _FORBIDDEN_WRITER_ATTRIBUTE_NAMES_IN_WRITER
            )
            assert not leaked, (
                f"{path.name}: writer narrowly admits write_bytes "
                f"only; forbidden writer call(s) {leaked}"
            )
        else:
            leaked = sorted(called_names & forbidden_outside_writer)
            assert not leaked, (
                f"{path.name}: forbidden writer call(s) outside "
                f"review_packet_writer.py: {leaked}"
            )


def test_no_stage_26_6_opens_a_file_in_write_mode():
    for path in _iter_stage26_6_production_files():
        calls = _collect_open_calls(_read_source(path))
        for call in calls:
            mode: str = "r"
            if len(call.args) >= 2:
                second = call.args[1]
                if isinstance(second, ast.Constant) and isinstance(
                    second.value, str
                ):
                    mode = second.value
            for keyword in call.keywords:
                if keyword.arg == "mode" and isinstance(
                    keyword.value, ast.Constant
                ) and isinstance(keyword.value.value, str):
                    mode = keyword.value.value
            assert mode not in _FORBIDDEN_OPEN_MODE_TOKENS, (
                f"{path.name}: forbidden open() mode {mode!r}"
            )


def test_no_stage_26_6_opens_a_file_at_all():
    """Stage 26.6 uses ``Path.write_bytes`` exclusively (in the
    writer); the builder / constants / models modules never open a
    file at all.
    """
    for path in _iter_stage26_6_production_files():
        calls = _collect_open_calls(_read_source(path))
        assert not calls, (
            f"{path.name}: Stage 26.6 must not open() files; the "
            "writer uses Path.write_bytes for output"
        )


# ---------------------------------------------------------------------------
# Identifier vocabulary scan (Stage 26.7+ vocabulary forbidden)
# ---------------------------------------------------------------------------


def test_no_stage_26_6_identifier_carries_forbidden_substring():
    for path in _iter_stage26_6_production_files():
        idents = _extract_all_identifiers(_read_source(path))
        for ident in idents:
            lower = ident.lower()
            for forbidden in _FORBIDDEN_DOMAIN_SUBSTRINGS_FOR_STAGE_26_6:
                assert forbidden not in lower, (
                    f"{path.name}: identifier {ident!r} contains "
                    f"forbidden Stage 26.7+ substring {forbidden!r}"
                )


def test_enforcement_substring_only_appears_as_safety_lock_label():
    """The substring ``enforcement`` may only appear in identifiers
    as part of the locked Stage 26.5 / 26.6 safety-lock label
    ``enforcement_enabled``.
    """
    for path in _iter_stage26_6_production_files():
        idents = _extract_all_identifiers(_read_source(path))
        for ident in idents:
            lower = ident.lower()
            if "enforcement" not in lower:
                continue
            assert _identifier_admits_enforcement_enabled(lower), (
                f"{path.name}: identifier {ident!r} carries an "
                "'enforcement' substring that is not part of the "
                "locked 'enforcement_enabled' safety-lock label"
            )


def test_no_stage_26_6_identifier_implements_operator_approval():
    """Stage 26.6 must not introduce an identifier that implements
    operator approval -- approval handoff is a PENDING placeholder
    only, never an APPROVED outcome.
    """
    forbidden_approval_idents = {
        "AUTO_APPROVED",
        "APPROVED",
        "operator_approval_decision",
        "approve_packet",
        "approve_candidate",
        "approve_policy",
        "grant_approval",
    }
    for path in _iter_stage26_6_production_files():
        idents = _extract_all_identifiers(_read_source(path))
        leaked = sorted(idents & forbidden_approval_idents)
        assert not leaked, (
            f"{path.name}: forbidden operator-approval identifier(s) "
            f"{leaked}"
        )


# ---------------------------------------------------------------------------
# Top-level side-effect freedom
# ---------------------------------------------------------------------------


def test_stage_26_6_modules_have_side_effect_free_top_level():
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
        ast.Expr,
    )
    for path in _iter_stage26_6_production_files():
        tree = ast.parse(_read_source(path))
        for node in tree.body:
            assert isinstance(node, allowed_top_level), (
                f"{path.name}: unexpected top-level node "
                f"{type(node).__name__}"
            )


# ---------------------------------------------------------------------------
# Importability
# ---------------------------------------------------------------------------


def test_each_stage_26_6_production_module_imports_cleanly():
    import importlib

    expected = {
        "PHX2.stage26.review_packet_constants",
        "PHX2.stage26.review_packet_models",
        "PHX2.stage26.review_packet_builder",
        "PHX2.stage26.review_packet_writer",
    }
    for name in expected:
        module = importlib.import_module(name)
        assert module is not None

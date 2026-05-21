"""Stage 26.1 file-scope / import-boundary / vocabulary tests.

Pins the Stage 26.1 scope at the file and identifier level:

  * The Stage 26 production tree carries exactly the locked
    Stage 26.0 spec-lock files plus the Stage 26.1 production
    modules.
  * No Stage 26 production module imports Stage 21 / 22 / 23 / 24
    production code.
  * No Stage 26 production module imports a ``PHX2.stage25``
    symbol outside the locked whitelist module
    (``PHX2/stage26/stage25_schema_whitelist.py``); the whitelist
    module itself imports only from ``PHX2.stage25.constants``.
  * No Stage 26 production module imports
    ``PHX2.stage25.stage25_manifest`` (the whitelist supersedes
    the legacy re-export surface).
  * No Stage 26 production module imports a network / RPC /
    messaging / DB / scheduler / secrets library.
  * No Stage 26 production module reads ``os.environ`` /
    ``os.getenv``.
  * No Stage 26 production module defines a CLI entrypoint or a
    ``__name__ == "__main__"`` guard.
  * No Stage 26 production module writes to the filesystem
    (``write_text`` / ``write_bytes`` / ``open(..., "w")`` /
    ``Path.unlink`` / ``Path.rmdir`` / ``shutil.rmtree``).
  * No Stage 26 production module introduces denominator-status,
    cohort, threshold, policy-candidate, approval-state,
    enforcement, dispatch, X / social, or Axiom / global-fee /
    Stage 24 execution-fee vocabulary.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest


STAGE26_ROOT: Path = Path(__file__).resolve().parent.parent.parent / "stage26"


_STAGE_26_1_PRODUCTION_FILENAMES: frozenset[str] = frozenset(
    {
        "__init__.py",
        "constants.py",
        "errors.py",
        "models.py",
        "stage25_schema_whitelist.py",
        "stage25_artifact_reader.py",
        "stage25_artifact_validation.py",
        "calibration_input_contracts.py",
        # Stage 26.2 narrowly extended the locked Stage 26 production
        # tree with the denominator / outcome-eligibility surface.
        # The Stage 26.1 boundary tests still apply uniformly to
        # every Stage 26 production module (Stage 26.1 + Stage 26.2 +
        # Stage 26.3 + Stage 26.4 + Stage 26.5 + Stage 26.6) except
        # where a later sub-stage's vocabulary supersedes a Stage
        # 26.1 lock (see ``_FORBIDDEN_DOMAIN_SUBSTRINGS``).
        "eligibility_constants.py",
        "eligibility_models.py",
        "eligibility_classifier.py",
        # Stage 26.3 narrowly extended the locked Stage 26 production
        # tree with the calibration cohort builder surface.
        "cohort_constants.py",
        "cohort_models.py",
        "cohort_builder.py",
        # Stage 26.4 narrowly extended the locked Stage 26 production
        # tree with the threshold candidate generator surface.
        "threshold_constants.py",
        "threshold_models.py",
        "threshold_candidate_generator.py",
        # Stage 26.5 narrowly extended the locked Stage 26 production
        # tree with the observe-only policy candidate artifact
        # builder + writer surface. ``policy_candidate_writer.py``
        # was the first Stage 26 production module narrowly admitted
        # to call ``Path.write_bytes`` -- see
        # ``_STAGE_26_WRITER_FILENAMES`` /
        # ``test_no_stage26_production_calls_filesystem_writer_apis``
        # for the writer exemption set (Stage 26.6 extends it).
        "policy_candidate_constants.py",
        "policy_candidate_models.py",
        "policy_candidate_builder.py",
        "policy_candidate_writer.py",
        # Stage 26.6 narrowly extended the locked Stage 26 production
        # tree with the operator review packet / approval handoff
        # builder + writer surface. ``review_packet_writer.py`` is
        # the second Stage 26 production module narrowly admitted to
        # call ``Path.write_bytes`` (review packets are review-only
        # offline artifacts; the broader Stage 26.1 read-only stance
        # still applies to every other Stage 26 production module).
        "review_packet_constants.py",
        "review_packet_models.py",
        "review_packet_builder.py",
        "review_packet_writer.py",
    }
)


# Narrow Stage 26.5 / 26.6 writer exemption -- the only Stage 26
# production files admitted to call ``Path.write_bytes``. Stage 26.5
# explicitly admits a deterministic offline observe-only policy
# candidate writer; Stage 26.6 explicitly admits a deterministic
# offline review-only operator review packet writer. The broader
# Stage 26.1 read-only stance still applies to every other Stage 26
# production module.
_STAGE_26_WRITER_FILENAMES: frozenset[str] = frozenset(
    {"policy_candidate_writer.py", "review_packet_writer.py"}
)
_STAGE_26_5_WRITER_FILENAME: str = "policy_candidate_writer.py"


_LOCKED_STAGE26_ENTRIES: frozenset[str] = (
    _STAGE_26_1_PRODUCTION_FILENAMES
    | frozenset({"STAGE_26_0_SPEC_LOCK.md"})
)


_WHITELIST_MODULE_BASENAME: str = "stage25_schema_whitelist.py"


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
    {
        "argparse",
        "click",
        "typer",
        "fire",
        "docopt",
        "time",
        "asyncio",
    }
)


_FORBIDDEN_FILE_PERSISTENCE_TOP_LEVEL_MODULES: frozenset[str] = frozenset(
    {
        "shutil",
        "tempfile",
        "csv",
    }
)


_FORBIDDEN_DOMAIN_SUBSTRINGS: tuple[str, ...] = (
    # ``denominator_status`` was forbidden at Stage 26.1 because Stage
    # 26.1 must not ship denominator semantics; Stage 26.2 narrowly
    # unlocks the token because the denominator-honesty surface is
    # exactly Stage 26.2's locked scope (see Stage 26.0 spec-lock §5
    # and the Stage 26.2 charter). ``cohort`` was forbidden at Stage
    # 26.1 / 26.2 because the calibration cohort builder is Stage
    # 26.3's locked scope; Stage 26.3 narrowly unlocks ``cohort`` so
    # the cohort vocabulary can ship in the approved Stage 26.3
    # cohort_*.py files. ``threshold_candidate`` was forbidden at
    # Stage 26.1 / 26.2 / 26.3 because the threshold candidate
    # generator is Stage 26.4's locked scope; Stage 26.4 narrowly
    # unlocks ``threshold_candidate`` so the threshold candidate
    # vocabulary can ship in the approved Stage 26.4
    # threshold_*.py files. ``policy_candidate`` was forbidden at
    # Stage 26.1 / 26.2 / 26.3 (and admitted by Stage 26.4 only as
    # the forward-pointing review-readiness token
    # ``READY_FOR_POLICY_CANDIDATE_REVIEW``); Stage 26.5 narrowly
    # unlocks ``policy_candidate`` so the observe-only policy
    # candidate vocabulary can ship in the approved Stage 26.5
    # policy_candidate_*.py files. ``enforcement`` remains
    # forbidden EXCEPT as part of the locked Stage 26.5 safety-lock
    # label ``enforcement_enabled`` (the
    # ``_identifier_admits_enforcement_enabled`` helper below
    # carves out exactly that narrow allowance). Stage 26.6+
    # vocabulary (``approval_state`` / ``approved_by`` /
    # ``dispatcher`` / ``review_packet`` / ...) remains forbidden.
    "approval_state",
    "approved_by",
    "enforcement",
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
)


# Stage 26.5 narrowly admits the substring ``enforcement`` as part
# of the locked safety-lock label ``enforcement_enabled`` (every
# emitted Stage 26.5 policy candidate carries
# ``enforcement_enabled=False`` as one of the five safety locks).
# Stage 26.6 narrowly admits the same substring as part of the
# locked review-packet defensive label ``enforcement_leak`` (the
# Stage 26.6 review packet exposes ``BLOCKED_ENFORCEMENT_LEAK`` /
# ``STG26_CAL_REVIEW_PACKET_ENFORCEMENT_LEAK`` so a downstream
# operator can distinguish an enforcement leak from a runtime or
# approval leak). Identifier matches that pair ``enforcement`` with
# anything other than ``enforcement_enabled`` / ``enforcement_leak``
# (e.g. ``enforcement_action``, ``enforcement_policy``) remain
# forbidden.
_ENFORCEMENT_ENABLED_FRAGMENT: str = "enforcement_enabled"
_ENFORCEMENT_LEAK_FRAGMENT: str = "enforcement_leak"


def _identifier_admits_enforcement_enabled(ident_lower: str) -> bool:
    """Return True if every ``enforcement`` substring in ``ident_lower``
    is part of the locked Stage 26.5 safety-lock label
    ``enforcement_enabled`` or the locked Stage 26.6 review-packet
    defensive label ``enforcement_leak``.
    """
    if "enforcement" not in ident_lower:
        return True
    stripped = ident_lower.replace(_ENFORCEMENT_ENABLED_FRAGMENT, "")
    stripped = stripped.replace(_ENFORCEMENT_LEAK_FRAGMENT, "")
    return "enforcement" not in stripped


_FORBIDDEN_URL_LITERAL_SUBSTRINGS: tuple[str, ...] = (
    "h" + "ttps://",
    "h" + "ttp://",
    "w" + "ss://",
    "w" + "s://",
    "discord" + ".com",
    "discordapp" + ".com",
    "hooks" + ".slack.com",
)


_FORBIDDEN_WRITER_ATTRIBUTE_NAMES: frozenset[str] = frozenset(
    {
        "write_text",
        "write_bytes",
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


def _iter_stage26_production_files() -> list[Path]:
    return [
        p
        for p in STAGE26_ROOT.iterdir()
        if p.is_file() and p.suffix == ".py"
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


def _collect_attribute_names(source: str) -> set[str]:
    tree = ast.parse(source)
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            names.add(node.attr)
    return names


def _collect_call_func_chain_names(source: str) -> set[str]:
    """Names that participate in a function-call position (any depth)."""
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
            elif (
                isinstance(func, ast.Attribute)
                and func.attr == "open"
            ):
                calls.append(node)
    return calls


# ---------------------------------------------------------------------------
# File inventory
# ---------------------------------------------------------------------------


def test_stage26_production_tree_matches_locked_inventory():
    entries = {
        p.name
        for p in STAGE26_ROOT.iterdir()
        if not (p.is_dir() and p.name == "__pycache__")
    }
    unexpected = entries - _LOCKED_STAGE26_ENTRIES
    missing = _LOCKED_STAGE26_ENTRIES - entries
    assert not unexpected, (
        f"Stage 26 production tree has unexpected entries: {sorted(unexpected)}"
    )
    assert not missing, (
        f"Stage 26 production tree is missing entries: {sorted(missing)}"
    )


def test_no_forbidden_future_substage_files_present():
    # ``cohort.py`` / ``cohort_builder.py`` were forbidden at Stage
    # 26.1 / 26.2 because the calibration cohort builder is Stage
    # 26.3's locked scope; Stage 26.3 narrowly unlocks
    # ``cohort_builder.py`` (and the supporting ``cohort_constants.py``
    # / ``cohort_models.py``) so the locked Stage 26.3 cohort file
    # set can ship. ``threshold_candidate_generator.py`` (and the
    # supporting ``threshold_constants.py`` / ``threshold_models.py``)
    # is Stage 26.4's locked scope and ships under the
    # ``_STAGE_26_1_PRODUCTION_FILENAMES`` lock above; the generic
    # ``threshold.py`` / ``threshold_generator.py`` basenames remain
    # forbidden so a future contributor cannot ship a thin
    # alternative threshold surface under those names. Stage 26.6
    # narrowly unlocks the multi-file ``review_packet_*.py`` family
    # for the operator review packet surface, so the generic
    # single-file ``review_packet.py`` / ``operator_review.py``
    # basenames remain forbidden so a future contributor cannot
    # ship a thin alternative review-packet surface under those
    # names. Stage 26.7+ basenames remain forbidden.
    forbidden_basenames = (
        "denominator.py",
        "threshold.py",
        "threshold_generator.py",
        "policy.py",
        "policy_candidate.py",
        "policy_writer.py",
        "review_packet.py",
        "operator_review.py",
        "operator_approval.py",
        "approval.py",
        "approval_packet.py",
        "runner.py",
        "writer.py",
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
    )
    for basename in forbidden_basenames:
        assert not (STAGE26_ROOT / basename).exists(), (
            f"Stage 26 must not ship {basename!r}; reserved for Stage 26.7+"
        )


# ---------------------------------------------------------------------------
# Import boundaries
# ---------------------------------------------------------------------------


def test_no_stage26_production_imports_prior_stage():
    for path in _iter_stage26_production_files():
        _, full = _collect_imports(_read_source(path))
        for target in full:
            for forbidden in _FORBIDDEN_PRIOR_STAGE_PREFIXES:
                assert not target.startswith(forbidden), (
                    f"{path.name}: forbidden prior-stage import {target!r}"
                )


def test_no_stage26_production_imports_runtime_module_patterns():
    for path in _iter_stage26_production_files():
        modules, _ = _collect_imports(_read_source(path))
        for module in modules:
            lower = module.lower()
            for pattern in _FORBIDDEN_RUNTIME_MODULE_PATTERNS:
                assert pattern not in lower, (
                    f"{path.name}: forbidden runtime pattern {pattern!r} in "
                    f"import target {module!r}"
                )


def test_no_stage26_production_imports_cli_or_sleep_libs():
    for path in _iter_stage26_production_files():
        modules, _ = _collect_imports(_read_source(path))
        for module in modules:
            top = module.split(".")[0]
            assert top not in _FORBIDDEN_CLI_OR_SLEEP_TOP_LEVEL_MODULES, (
                f"{path.name}: forbidden CLI/sleep import {module!r}"
            )


def test_no_stage26_production_imports_file_persistence_libs():
    for path in _iter_stage26_production_files():
        modules, _ = _collect_imports(_read_source(path))
        for module in modules:
            top = module.split(".")[0]
            assert top not in _FORBIDDEN_FILE_PERSISTENCE_TOP_LEVEL_MODULES, (
                f"{path.name}: forbidden file-persistence import {module!r}"
            )


def test_no_stage26_production_imports_phx2_runtime_layer():
    for path in _iter_stage26_production_files():
        _, full = _collect_imports(_read_source(path))
        for target in full:
            for forbidden in _FORBIDDEN_PHX2_RUNTIME_PREFIXES:
                assert not target.startswith(forbidden), (
                    f"{path.name}: forbidden PHX2 runtime-layer target "
                    f"{target!r}"
                )


def test_only_whitelist_module_imports_stage25():
    """Stage 26.1 production modules other than the whitelist must NOT
    import any ``PHX2.stage25`` symbol -- they consume Stage 25
    vocabulary through ``PHX2.stage26.stage25_schema_whitelist``.
    """
    for path in _iter_stage26_production_files():
        if path.name == _WHITELIST_MODULE_BASENAME:
            continue
        modules, _ = _collect_imports(_read_source(path))
        for module in modules:
            assert not module.startswith("PHX2.stage25"), (
                f"{path.name}: forbidden Stage 25 import {module!r}; "
                "consume via PHX2.stage26.stage25_schema_whitelist instead"
            )


def test_whitelist_module_only_imports_from_stage25_constants():
    path = STAGE26_ROOT / _WHITELIST_MODULE_BASENAME
    modules, _ = _collect_imports(_read_source(path))
    stage25_modules = {m for m in modules if m.startswith("PHX2.stage25")}
    assert stage25_modules == {"PHX2.stage25.constants"}, (
        f"Whitelist module is permitted to import from PHX2.stage25.constants "
        f"only; saw {sorted(stage25_modules)}"
    )


def test_no_stage26_production_imports_stage25_manifest_module():
    """PHX2.stage25.stage25_manifest re-exports the sentinel constants
    for backward compatibility with Stage 25.6 callers; Stage 26.1
    MUST consume the sentinels through the locked whitelist surface.
    """
    for path in _iter_stage26_production_files():
        modules, full = _collect_imports(_read_source(path))
        forbidden_targets = {"PHX2.stage25.stage25_manifest"}
        leaked = modules & forbidden_targets
        full_leaked = {t for t in full if t.startswith("PHX2.stage25.stage25_manifest")}
        assert not leaked, (
            f"{path.name}: forbidden Stage 25 manifest import {sorted(leaked)}"
        )
        assert not full_leaked, (
            f"{path.name}: forbidden Stage 25 manifest from-import "
            f"{sorted(full_leaked)}"
        )


# ---------------------------------------------------------------------------
# Env / CLI / dispatch boundary
# ---------------------------------------------------------------------------


def test_no_stage26_production_reads_environ():
    for path in _iter_stage26_production_files():
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
                elif mod == "os.environ" or mod.startswith("os.environ."):
                    pytest.fail(
                        f"{path.name}: forbidden os.environ import"
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


def test_no_stage26_production_defines_cli_entrypoint():
    forbidden_names = {"main", "cli", "entrypoint"}
    for path in _iter_stage26_production_files():
        tree = ast.parse(_read_source(path))
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                assert node.name not in forbidden_names, (
                    f"{path.name}: forbidden CLI-style entrypoint "
                    f"{node.name!r}"
                )


def test_no_stage26_production_has_dunder_main_guard():
    for path in _iter_stage26_production_files():
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


def test_no_stage26_production_has_url_literal():
    for path in _iter_stage26_production_files():
        source = _read_source(path)
        for needle in _FORBIDDEN_URL_LITERAL_SUBSTRINGS:
            assert needle not in source, (
                f"{path.name}: forbidden URL literal {needle!r}"
            )


# ---------------------------------------------------------------------------
# File-writer boundary
# ---------------------------------------------------------------------------


def test_no_stage26_production_calls_filesystem_writer_apis():
    """Stage 26 production modules MUST NOT call ``write_text`` /
    ``unlink`` / ``rmdir`` / ``rmtree`` / ``replace`` / ``rename`` /
    ``touch`` / ``mkdir``. ``write_bytes`` is narrowly admitted in
    ``policy_candidate_writer.py`` (Stage 26.5 observe-only policy
    candidate writer) and ``review_packet_writer.py`` (Stage 26.6
    review-only operator review packet writer); every other Stage
    26 production module remains read-only against the filesystem.
    """
    forbidden_in_writer = (
        _FORBIDDEN_WRITER_ATTRIBUTE_NAMES - {"write_bytes"}
    )
    for path in _iter_stage26_production_files():
        called_names = _collect_call_func_chain_names(_read_source(path))
        if path.name in _STAGE_26_WRITER_FILENAMES:
            leaked = sorted(called_names & forbidden_in_writer)
            assert not leaked, (
                f"{path.name}: Stage 26 writer narrowly admits "
                f"write_bytes only; forbidden writer call(s) {leaked}"
            )
        else:
            leaked = sorted(
                called_names & _FORBIDDEN_WRITER_ATTRIBUTE_NAMES
            )
            assert not leaked, (
                f"{path.name}: forbidden writer call(s) outside "
                f"{sorted(_STAGE_26_WRITER_FILENAMES)}: {leaked}"
            )


def test_no_stage26_production_opens_a_file_in_write_mode():
    """``open(..., mode=...)`` where mode contains 'w' / 'a' / 'x' is
    forbidden. ``open(path, "rb")`` (the only mode the reader needs)
    is fine.
    """
    for path in _iter_stage26_production_files():
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


# ---------------------------------------------------------------------------
# Identifier vocabulary scan
# ---------------------------------------------------------------------------


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


def test_no_stage26_production_identifier_carries_forbidden_substring():
    for path in _iter_stage26_production_files():
        idents = _extract_all_identifiers(_read_source(path))
        for ident in idents:
            lower = ident.lower()
            for forbidden in _FORBIDDEN_DOMAIN_SUBSTRINGS:
                if forbidden == "enforcement" and forbidden in lower:
                    if _identifier_admits_enforcement_enabled(lower):
                        continue
                assert forbidden not in lower, (
                    f"{path.name}: identifier {ident!r} contains "
                    f"forbidden substring {forbidden!r}"
                )


# ---------------------------------------------------------------------------
# Importability
# ---------------------------------------------------------------------------


def test_each_stage26_production_module_imports_cleanly():
    import importlib

    expected = {
        "PHX2.stage26.constants",
        "PHX2.stage26.errors",
        "PHX2.stage26.models",
        "PHX2.stage26.stage25_schema_whitelist",
        "PHX2.stage26.stage25_artifact_reader",
        "PHX2.stage26.stage25_artifact_validation",
        "PHX2.stage26.calibration_input_contracts",
        # Stage 26.2 added the eligibility surface; the import check
        # was narrowly extended to cover it.
        "PHX2.stage26.eligibility_constants",
        "PHX2.stage26.eligibility_models",
        "PHX2.stage26.eligibility_classifier",
        # Stage 26.3 added the calibration cohort builder surface;
        # the import check was narrowly extended to cover it.
        "PHX2.stage26.cohort_constants",
        "PHX2.stage26.cohort_models",
        "PHX2.stage26.cohort_builder",
        # Stage 26.4 added the threshold candidate generator surface;
        # the import check was narrowly extended to cover it.
        "PHX2.stage26.threshold_constants",
        "PHX2.stage26.threshold_models",
        "PHX2.stage26.threshold_candidate_generator",
        # Stage 26.5 added the observe-only policy candidate
        # artifact builder + writer surface; the import check was
        # narrowly extended to cover it.
        "PHX2.stage26.policy_candidate_constants",
        "PHX2.stage26.policy_candidate_models",
        "PHX2.stage26.policy_candidate_builder",
        "PHX2.stage26.policy_candidate_writer",
        # Stage 26.6 added the operator review packet / approval
        # handoff builder + writer surface; the import check was
        # narrowly extended to cover it.
        "PHX2.stage26.review_packet_constants",
        "PHX2.stage26.review_packet_models",
        "PHX2.stage26.review_packet_builder",
        "PHX2.stage26.review_packet_writer",
    }
    for name in expected:
        module = importlib.import_module(name)
        assert module is not None


# ---------------------------------------------------------------------------
# Top-level side-effect freedom
# ---------------------------------------------------------------------------


def test_stage26_production_modules_have_side_effect_free_top_level():
    """No Stage 26.1 production module performs top-level I/O.

    Allowed top-level nodes: imports, class/function defs, type
    aliases / annotated assignments, simple constant assignments.
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
        ast.Expr,
    )
    for path in _iter_stage26_production_files():
        tree = ast.parse(_read_source(path))
        for node in tree.body:
            assert isinstance(node, allowed_top_level), (
                f"{path.name}: unexpected top-level node "
                f"{type(node).__name__}"
            )

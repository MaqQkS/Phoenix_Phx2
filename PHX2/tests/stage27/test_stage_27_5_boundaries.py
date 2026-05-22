"""Stage 27.5 boundary scan.

Pins:

  * Every Stage 27.5 production file exists at the locked path.
  * No Stage 27.5 production module reads the process environment
    (``os.environ`` / ``os.getenv`` / ``os.environb``). The Stage
    27 env-read boundary remains exactly
    ``live_secrets_readiness.py``.
  * No Stage 27.5 production module imports a network, RPC,
    messaging, Discord, Telegram, X / social, or scheduling
    library.
  * No Stage 27.5 production module imports Stage 21-26 production
    code.
  * No Stage 27.5 production module imports Stage 27.1 production
    modules (the env-read / operator-config surface stays
    independent of the rendering layer).
  * No Stage 27.5 production module carries a URL host literal, a
    Discord webhook literal, or a raw secret canary.
  * Stage 27.5 production source carries no Stage 27.6+
    implementation identifier substrings (Discord sender /
    candidate assembler / bounded runner / live dedupe / public
    router / X-social).
  * Every Stage 27.7+ implementation basename is still absent
    under ``PHX2/stage27/`` (``private_discord_sender.py``). Stage
    27.6 narrow amendment: ``live_candidate_assembler.py`` /
    ``bounded_tradeable_ping_runner.py`` / ``live_dedupe.py`` /
    ``stage27_6_manifest.py`` have been promoted to the Stage 27.6
    production surface and are no longer in the forbidden list.
  * ``PHX2/stage27/`` admits only the locked Stage 27.0 through
    27.5 file set.
  * The Stage 27.0 spec-lock-allowlist amendment admits the Stage
    27.5 production basenames and continues to forbid every Stage
    27.6+ basename.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest


PHX2_ROOT: Path = Path(__file__).resolve().parent.parent.parent
STAGE27_ROOT: Path = PHX2_ROOT / "stage27"
TESTS_STAGE27_ROOT: Path = PHX2_ROOT / "tests" / "stage27"


_STAGE_27_5_PRODUCTION_FILENAMES: tuple[str, ...] = (
    "private_ping_models.py",
    "private_ping_renderer.py",
    "private_ping_provenance.py",
    "private_ping_artifact_writer.py",
    "stage27_5_manifest.py",
)


_STAGE_27_0_THROUGH_27_5_LOCKED_PY_MODULES: frozenset[str] = (
    frozenset(
        {
            # Stage 27.0 scaffold.
            "__init__.py",
            # Stage 27.1 operator-config / secrets-readiness surface.
            "live_config_errors.py",
            "live_config_models.py",
            "live_run_identity.py",
            "live_secrets_readiness.py",
            "live_operator_config.py",
            # Stage 27.2 pair-detection production surface.
            "pair_detection_constants.py",
            "pair_detection_models.py",
            "pair_detection_contracts.py",
            "pump_pair_classifier.py",
            # Stage 27.3 provider-ingest composition surface.
            "provider_ingest_models.py",
            "provider_ingest_contracts.py",
            "provider_event_adapter.py",
            "live_provider_composition.py",
            "stage27_3_manifest.py",
            # Stage 27.4 price / ATH / migration context surface.
            "price_ath_context_models.py",
            "price_ath_context_contracts.py",
            "price_ath_context_reader.py",
            "migration_context_models.py",
            "live_measurement_context.py",
            "stage27_4_manifest.py",
            # Stage 27.5 private-ping renderer / provenance surface.
            "private_ping_models.py",
            "private_ping_renderer.py",
            "private_ping_provenance.py",
            "private_ping_artifact_writer.py",
            "stage27_5_manifest.py",
            # Stage 27.6 live-candidate assembler / bounded dry-run
            # runner / run-local dedupe surface. Stage 27.5 boundary
            # admits these because the ``PHX2/stage27/`` directory
            # now carries them; the Stage 27.5 production-file
            # allowlist and identifier scan still scope only the
            # five Stage 27.5 files.
            "live_dedupe.py",
            "live_candidate_assembler.py",
            "bounded_tradeable_ping_runner.py",
            "stage27_6_manifest.py",
            # Stage 27.7a dry-run smoke harness + Stage 27.7a
            # manifest. Stage 27.5 boundary admits these because
            # the ``PHX2/stage27/`` directory now carries them; the
            # Stage 27.5 production-file allowlist and identifier
            # scan still scope only the five Stage 27.5 files.
            "dry_run_smoke_harness.py",
            "stage27_7_manifest.py",
        }
    )
)


_STAGE_27_0_THROUGH_27_5_LOCKED_ENTRIES: frozenset[str] = (
    _STAGE_27_0_THROUGH_27_5_LOCKED_PY_MODULES
    | frozenset(
        {
            "STAGE_27_0_SPEC_LOCK.md",
            # Stage 27.7a docs admitted by the directory scan only;
            # the Stage 27.5 production-file allowlist and the
            # identifier scan still scope only the five Stage 27.5
            # files.
            "STAGE_27_OPERATOR_RUNBOOK.md",
            "STAGE_27_DRY_RUN_SMOKE_CHECKLIST.md",
        }
    )
)


def _iter_stage27_5_production_files() -> list[Path]:
    return [
        STAGE27_ROOT / name
        for name in _STAGE_27_5_PRODUCTION_FILENAMES
    ]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Production-file existence
# ---------------------------------------------------------------------------


def test_every_stage_27_5_production_file_exists():
    for name in _STAGE_27_5_PRODUCTION_FILENAMES:
        path = STAGE27_ROOT / name
        assert path.is_file(), (
            f"Stage 27.5 requires production file {path}"
        )


def test_stage27_root_admits_only_locked_27_0_through_27_5_entries():
    actual: set[str] = set()
    for entry in STAGE27_ROOT.iterdir():
        if entry.is_dir() and entry.name == "__pycache__":
            continue
        actual.add(entry.name)
    forbidden = (
        actual - _STAGE_27_0_THROUGH_27_5_LOCKED_ENTRIES
    )
    assert not forbidden, (
        f"PHX2/stage27 admits only the Stage 27.0 + 27.1 + 27.2 + "
        f"27.3 + 27.4 + 27.5 file set; forbidden entries: "
        f"{sorted(forbidden)!r}"
    )


def test_stage27_root_py_modules_match_locked_27_5_set():
    py_files = {
        p.name
        for p in STAGE27_ROOT.iterdir()
        if p.is_file() and p.suffix == ".py"
    }
    unexpected = (
        py_files - _STAGE_27_0_THROUGH_27_5_LOCKED_PY_MODULES
    )
    assert not unexpected, (
        f"Stage 27.5 must ship only the locked production .py set; "
        f"unexpected: {sorted(unexpected)!r}"
    )


# ---------------------------------------------------------------------------
# Env-read isolation
# ---------------------------------------------------------------------------


_ENV_ATTR_NAMES: frozenset[str] = frozenset(
    {"environ", "getenv", "environb"}
)


def _module_reads_environ(source: str) -> bool:
    tree = ast.parse(source)
    os_aliases: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "os":
                    os_aliases.add(alias.asname or alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module == "os":
                for alias in node.names:
                    if alias.name in _ENV_ATTR_NAMES:
                        return True
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            if (
                isinstance(node.value, ast.Name)
                and node.value.id in os_aliases
                and node.attr in _ENV_ATTR_NAMES
            ):
                return True
    return False


def test_no_stage_27_5_production_reads_environ():
    leaked: list[str] = []
    for path in _iter_stage27_5_production_files():
        if _module_reads_environ(_read(path)):
            leaked.append(path.name)
    assert not leaked, (
        f"Stage 27.5 production modules must not read os.environ; "
        f"offenders: {leaked!r}"
    )


def test_stage_27_env_read_boundary_remains_live_secrets_readiness_only():
    """Stage 27 must isolate every env-read site in
    ``live_secrets_readiness.py``. Stage 27.5 must not add a second
    env-read site anywhere under ``PHX2/stage27/``.
    """
    env_read_modules: list[str] = []
    for entry in STAGE27_ROOT.iterdir():
        if not entry.is_file() or entry.suffix != ".py":
            continue
        if entry.name == "live_secrets_readiness.py":
            continue
        if _module_reads_environ(_read(entry)):
            env_read_modules.append(entry.name)
    assert not env_read_modules, (
        "Stage 27 env-read boundary must remain isolated to "
        "live_secrets_readiness.py; offenders: "
        f"{env_read_modules!r}"
    )


# ---------------------------------------------------------------------------
# Forbidden imports
# ---------------------------------------------------------------------------


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
    "birdeye",
    "discord",
    "telegram",
    "telethon",
    "webhook",
    "apscheduler",
    "celery",
    "schedule",
    "crontab",
    "sqlalchemy",
    "sqlite3",
    "dotenv",
    "keyring",
    "tweepy",
    "twitter",
)


_FORBIDDEN_PRIOR_STAGE_PREFIXES: tuple[str, ...] = (
    "PHX2.stage17",
    "PHX2.stage18",
    "PHX2.stage19",
    "PHX2.stage20",
    "PHX2.stage21",
    "PHX2.stage22",
    "PHX2.stage23",
    "PHX2.stage24",
    "PHX2.stage25",
    "PHX2.stage26",
)


_FORBIDDEN_STAGE_27_1_MODULE_PREFIXES: tuple[str, ...] = (
    "PHX2.stage27.live_config_errors",
    "PHX2.stage27.live_config_models",
    "PHX2.stage27.live_run_identity",
    "PHX2.stage27.live_secrets_readiness",
    "PHX2.stage27.live_operator_config",
)


def _collect_imported_module_paths(source: str) -> set[str]:
    tree = ast.parse(source)
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if mod:
                modules.add(mod)
    return modules


def test_no_stage_27_5_production_imports_runtime_module_patterns():
    for path in _iter_stage27_5_production_files():
        targets = _collect_imported_module_paths(_read(path))
        for target in targets:
            lower = target.lower()
            for pattern in _FORBIDDEN_RUNTIME_MODULE_PATTERNS:
                assert pattern not in lower, (
                    f"{path}: forbidden runtime pattern "
                    f"{pattern!r} in import {target!r}"
                )


def test_no_stage_27_5_production_imports_prior_stage_code():
    for path in _iter_stage27_5_production_files():
        targets = _collect_imported_module_paths(_read(path))
        for target in targets:
            for forbidden in _FORBIDDEN_PRIOR_STAGE_PREFIXES:
                assert not target.startswith(forbidden), (
                    f"{path}: forbidden prior-stage import "
                    f"{target!r}"
                )


def test_no_stage_27_5_production_imports_stage_27_1_modules():
    for path in _iter_stage27_5_production_files():
        targets = _collect_imported_module_paths(_read(path))
        for target in targets:
            for forbidden in _FORBIDDEN_STAGE_27_1_MODULE_PREFIXES:
                assert target != forbidden, (
                    f"{path}: Stage 27.5 must not import Stage 27.1 "
                    f"module {target!r}"
                )
                assert not target.startswith(forbidden + "."), (
                    f"{path}: Stage 27.5 must not import from "
                    f"Stage 27.1 module {target!r}"
                )


# ---------------------------------------------------------------------------
# URL / leak literal scan
# ---------------------------------------------------------------------------


_FORBIDDEN_URL_LITERAL_SUBSTRINGS: tuple[str, ...] = (
    "h" + "ttps://",
    "h" + "ttp://",
    "w" + "ss://",
    "w" + "s://",
    "discord" + ".com",
    "discordapp" + ".com",
    "hooks" + ".slack.com",
    "api.helius" + ".xyz",
    "rpc.helius" + ".xyz",
    "public-api.birdeye" + ".so",
    "t" + ".me/",
    "api.twitter" + ".com",
    "api.x" + ".com",
)


def test_no_url_literal_in_stage_27_5_production_source():
    for path in _iter_stage27_5_production_files():
        source = _read(path)
        for needle in _FORBIDDEN_URL_LITERAL_SUBSTRINGS:
            assert needle not in source, (
                f"{path}: forbidden URL literal {needle!r}"
            )


# ---------------------------------------------------------------------------
# Identifier scan: no Stage 27.6+ implementation surface in Stage 27.5
# ---------------------------------------------------------------------------
#
# Substrings that would indicate Stage 27.6+ implementation creep.
# Stage 27.5's own identifiers legitimately reference private-ping
# rendering and provenance artifacts; those are not forbidden here.
# The substrings below are phrased as literal-string concatenations
# so this test file does not contain the exact substring scanners
# might re-scan.


_FORBIDDEN_LATER_SUBSTAGE_SUBSTRINGS: tuple[str, ...] = (
    "discord" + "_sender",
    "candidate" + "_assembler",
    "tradeable" + "_ping_runner",
    "bounded" + "_tradeable",
    "live" + "_dedupe",
    "live" + "_router",
    "subscriber" + "_router",
    "x" + "_social",
)


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
    return idents


def test_no_stage_27_5_production_identifier_implements_later_substage():
    for path in _iter_stage27_5_production_files():
        idents = _extract_all_identifiers(_read(path))
        for ident in idents:
            lower = ident.lower()
            for needle in _FORBIDDEN_LATER_SUBSTAGE_SUBSTRINGS:
                assert needle not in lower, (
                    f"{path}: identifier {ident!r} contains "
                    f"forbidden later-substage substring {needle!r}"
                )


# ---------------------------------------------------------------------------
# Stage 27.6+ implementation basenames must not exist
# ---------------------------------------------------------------------------


_STAGE_27_6_PLUS_FORBIDDEN_BASENAMES: tuple[str, ...] = (
    "private_discord_sender.py",
)


@pytest.mark.parametrize(
    "basename", _STAGE_27_6_PLUS_FORBIDDEN_BASENAMES
)
def test_stage_27_6_plus_basename_does_not_exist_in_stage27_root(
    basename,
):
    path = STAGE27_ROOT / basename
    assert not path.exists(), (
        f"Stage 27.5 must not introduce Stage 27.6+ implementation "
        f"basename {basename!r} under PHX2/stage27/; got {path}"
    )


# ---------------------------------------------------------------------------
# No top-level I/O
# ---------------------------------------------------------------------------


def _has_top_level_call(source: str) -> bool:
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, ast.Expr) and isinstance(
            node.value, ast.Call
        ):
            return True
    return False


def test_no_stage_27_5_production_has_top_level_call():
    for path in _iter_stage27_5_production_files():
        assert not _has_top_level_call(_read(path)), (
            f"{path}: Stage 27.5 production modules must contain no "
            f"top-level Call (no implicit I/O at import time)"
        )


# ---------------------------------------------------------------------------
# Stage 25 / Stage 26 production trees were not touched
# ---------------------------------------------------------------------------


def test_no_stage25_or_stage26_production_files_carry_stage27_5_basename():
    stage25_root = PHX2_ROOT / "stage25"
    stage26_root = PHX2_ROOT / "stage26"
    leaked: list[str] = []
    for root in (stage25_root, stage26_root):
        if not root.exists():
            continue
        for entry in root.iterdir():
            if not entry.is_file():
                continue
            if entry.name in _STAGE_27_5_PRODUCTION_FILENAMES:
                leaked.append(f"{root.name}/{entry.name}")
    assert not leaked, (
        f"Stage 27.5 production basename leaked into a prior stage "
        f"tree: {leaked!r}"
    )


# ---------------------------------------------------------------------------
# Stage 27.5 must not call datetime.now / time.time directly
# ---------------------------------------------------------------------------
#
# Stage 27.5 takes wall-clock reads only through the injected
# ``Stage27_5Clock`` Protocol. A direct ``datetime.now()`` or
# ``time.time()`` call in production would silently widen the
# clock boundary.


def _module_calls_direct_clock(source: str) -> list[str]:
    tree = ast.parse(source)
    offenders: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute):
                attr = func.attr
                value = func.value
                if isinstance(value, ast.Name):
                    name = value.id
                    if name == "datetime" and attr == "now":
                        offenders.append("datetime.now")
                    if name == "datetime" and attr == "utcnow":
                        offenders.append("datetime.utcnow")
                    if name == "time" and attr in (
                        "time",
                        "monotonic",
                        "monotonic_ns",
                        "perf_counter",
                    ):
                        offenders.append(f"time.{attr}")
    return offenders


def test_no_stage_27_5_production_calls_datetime_now():
    for path in _iter_stage27_5_production_files():
        offenders = _module_calls_direct_clock(_read(path))
        assert not offenders, (
            f"{path}: Stage 27.5 must NOT call wall-clock helpers "
            f"directly (use the injected Stage27_5Clock Protocol); "
            f"offenders: {offenders!r}"
        )


# ---------------------------------------------------------------------------
# Stage 27.5 must not write to disk at import time
# ---------------------------------------------------------------------------


_FORBIDDEN_TOP_LEVEL_WRITE_TARGETS: frozenset[str] = frozenset(
    {
        "write_bytes",
        "write_text",
        "open",
        "mkdir",
        "touch",
        "unlink",
        "rmdir",
        "rename",
        "replace",
    }
)


def _module_calls_top_level_filesystem(source: str) -> list[str]:
    tree = ast.parse(source)
    offenders: list[str] = []
    for node in tree.body:
        if isinstance(node, ast.Expr) and isinstance(
            node.value, ast.Call
        ):
            func = node.value.func
            if isinstance(func, ast.Attribute):
                if (
                    func.attr
                    in _FORBIDDEN_TOP_LEVEL_WRITE_TARGETS
                ):
                    offenders.append(func.attr)
            elif isinstance(func, ast.Name):
                if (
                    func.id
                    in _FORBIDDEN_TOP_LEVEL_WRITE_TARGETS
                ):
                    offenders.append(func.id)
    return offenders


def test_no_stage_27_5_production_writes_at_import_time():
    for path in _iter_stage27_5_production_files():
        offenders = _module_calls_top_level_filesystem(_read(path))
        assert not offenders, (
            f"{path}: Stage 27.5 production modules must not call "
            f"filesystem write helpers at import time; offenders: "
            f"{offenders!r}"
        )


# ---------------------------------------------------------------------------
# Stage 27.0 spec-lock amendment shape
# ---------------------------------------------------------------------------


def test_spec_lock_allowlist_admits_stage_27_5_basenames():
    spec_lock_test_path = (
        TESTS_STAGE27_ROOT / "test_stage_27_0_spec_lock.py"
    )
    text = spec_lock_test_path.read_text(encoding="utf-8")
    for basename in _STAGE_27_5_PRODUCTION_FILENAMES:
        assert (
            f'"{basename}"' in text or f"'{basename}'" in text
        ), (
            f"Stage 27.0 spec-lock test allowlist missing Stage "
            f"27.5 basename {basename!r}"
        )


def test_spec_lock_forbidden_list_still_forbids_stage_27_6_plus():
    spec_lock_test_path = (
        TESTS_STAGE27_ROOT / "test_stage_27_0_spec_lock.py"
    )
    text = spec_lock_test_path.read_text(encoding="utf-8")
    for basename in _STAGE_27_6_PLUS_FORBIDDEN_BASENAMES:
        assert (
            f'"{basename}"' in text or f"'{basename}'" in text
        ), (
            f"Stage 27.0 spec-lock test forbidden list missing "
            f"Stage 27.6+ basename {basename!r}"
        )


# ---------------------------------------------------------------------------
# Stage 27.5 manifest pin
# ---------------------------------------------------------------------------


def test_stage27_5_manifest_lists_production_basenames():
    from PHX2.stage27.stage27_5_manifest import (
        STAGE27_5_PRODUCTION_BASENAMES,
    )
    assert set(STAGE27_5_PRODUCTION_BASENAMES) == set(
        _STAGE_27_5_PRODUCTION_FILENAMES
    )


def test_stage27_5_manifest_lists_test_basenames():
    from PHX2.stage27.stage27_5_manifest import (
        STAGE27_5_TEST_BASENAMES,
    )
    assert STAGE27_5_TEST_BASENAMES == (
        "test_stage_27_5_private_ping_models.py",
        "test_stage_27_5_private_ping_renderer.py",
        "test_stage_27_5_private_ping_provenance.py",
        "test_stage_27_5_private_ping_artifact_writer.py",
        "test_stage_27_5_boundaries.py",
    )


def test_stage27_5_manifest_re_exports_schema_versions():
    from PHX2.stage27 import stage27_5_manifest as mfst
    assert mfst.STAGE27_5_MINOR_VERSION == "27.5"
    assert (
        mfst.STAGE27_5_PING_SCHEMA_VERSION
        == "stage27_v0_private_ping"
    )
    assert (
        mfst.STAGE27_5_PROVENANCE_SCHEMA_VERSION
        == "stage27_v0_ping_provenance"
    )

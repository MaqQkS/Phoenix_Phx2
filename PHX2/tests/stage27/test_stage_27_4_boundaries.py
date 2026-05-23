"""Stage 27.4 boundary scan.

Pins:

  * Every Stage 27.4 production file exists at the locked path.
  * No Stage 27.4 production module reads the process environment
    (``os.environ`` / ``os.getenv`` / ``os.environb``). The Stage
    27 env-read boundary remains exactly
    ``live_secrets_readiness.py``; Stage 27.4 must not add a
    second env-read site.
  * No Stage 27.4 production module imports a network, RPC,
    messaging, Discord, Telegram, X / social, or scheduling
    library.
  * No Stage 27.4 production module imports Stage 21-26 production
    code.
  * No Stage 27.4 production module imports Stage 27.1 production
    modules (the env-read / operator-config surface stays
    independent of the measurement-context layer).
  * No Stage 27.4 production module carries a URL host literal.
  * Stage 27.4 production source carries no Stage 27.5+
    implementation identifier substrings (ping renderer / Discord
    sender / candidate assembler / bounded runner / dedupe /
    public router / X-social).
  * Every Stage 27.5+ implementation basename is still absent
    under ``PHX2/stage27/``.
  * ``PHX2/stage27/`` admits only the locked Stage 27.0 + 27.1 +
    27.2 + 27.3 + 27.4 file set.
  * The Stage 27.4 spec-lock-allowlist amendment in
    ``test_stage_27_0_spec_lock.py`` admits the Stage 27.4
    production basenames and continues to forbid every Stage 27.5+
    basename.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest


PHX2_ROOT: Path = Path(__file__).resolve().parent.parent.parent
STAGE27_ROOT: Path = PHX2_ROOT / "stage27"
TESTS_STAGE27_ROOT: Path = PHX2_ROOT / "tests" / "stage27"


_STAGE_27_4_PRODUCTION_FILENAMES: tuple[str, ...] = (
    "price_ath_context_models.py",
    "price_ath_context_contracts.py",
    "price_ath_context_reader.py",
    "migration_context_models.py",
    "live_measurement_context.py",
    "stage27_4_manifest.py",
)


_STAGE_27_0_THROUGH_27_4_LOCKED_PY_MODULES: frozenset[str] = (
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
            # Stage 27.4 boundary admits these because the
            # ``PHX2/stage27/`` directory now carries them; the
            # Stage 27.4 production-file allowlist and identifier
            # scan still scope only the six Stage 27.4 files.
            "private_ping_models.py",
            "private_ping_renderer.py",
            "private_ping_provenance.py",
            "private_ping_artifact_writer.py",
            "stage27_5_manifest.py",
            # Stage 27.6 live-candidate assembler / bounded dry-run
            # runner / run-local dedupe surface. Stage 27.4 boundary
            # admits these for the same reason: the directory now
            # carries them. The Stage 27.4 production-file
            # allowlist and identifier scan still scope only the
            # six Stage 27.4 files.
            "live_dedupe.py",
            "live_candidate_assembler.py",
            "bounded_tradeable_ping_runner.py",
            "stage27_6_manifest.py",
            # Stage 27.7a dry-run smoke harness + Stage 27.7a
            # manifest. Stage 27.4 boundary admits these because
            # the ``PHX2/stage27/`` directory now carries them;
            # the Stage 27.4 production-file allowlist and
            # identifier scan still scope only the six Stage 27.4
            # files.
            "dry_run_smoke_harness.py",
            "stage27_7_manifest.py",
            # Stage 27.7b private Discord sender + dispatch +
            # models + manifest. Stage 27.4 boundary admits these
            # because the ``PHX2/stage27/`` directory now carries
            # them; the Stage 27.4 production-file allowlist and
            # identifier scan still scope only the six Stage 27.4
            # files.
            "private_discord_models.py",
            "private_discord_sender.py",
            "live_smoke_dispatch.py",
            "stage27_7b_manifest.py",
        }
    )
)


_STAGE_27_0_THROUGH_27_4_LOCKED_ENTRIES: frozenset[str] = (
    _STAGE_27_0_THROUGH_27_4_LOCKED_PY_MODULES
    | frozenset(
        {
            "STAGE_27_0_SPEC_LOCK.md",
            # Stage 27.7a docs admitted by the directory scan
            # only; the Stage 27.4 production-file allowlist and
            # identifier scan still scope only the six Stage 27.4
            # files.
            "STAGE_27_OPERATOR_RUNBOOK.md",
            "STAGE_27_DRY_RUN_SMOKE_CHECKLIST.md",
            # Stage 27.8 closure audit + Stage 28 handoff docs
            # admitted by the directory scan only.
            "STAGE_27_CLOSURE_AUDIT.md",
            "STAGE_28_HANDOFF.md",
        }
    )
)


def _iter_stage27_4_production_files() -> list[Path]:
    return [
        STAGE27_ROOT / name
        for name in _STAGE_27_4_PRODUCTION_FILENAMES
    ]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Production-file existence
# ---------------------------------------------------------------------------


def test_every_stage_27_4_production_file_exists():
    for name in _STAGE_27_4_PRODUCTION_FILENAMES:
        path = STAGE27_ROOT / name
        assert path.is_file(), (
            f"Stage 27.4 requires production file {path}"
        )


def test_stage27_root_admits_only_locked_27_0_through_27_4_entries():
    actual: set[str] = set()
    for entry in STAGE27_ROOT.iterdir():
        if entry.is_dir() and entry.name == "__pycache__":
            continue
        actual.add(entry.name)
    forbidden = actual - _STAGE_27_0_THROUGH_27_4_LOCKED_ENTRIES
    assert not forbidden, (
        f"PHX2/stage27 admits only the Stage 27.0 + 27.1 + 27.2 + "
        f"27.3 + 27.4 file set; forbidden entries: "
        f"{sorted(forbidden)!r}"
    )


def test_stage27_root_py_modules_match_locked_27_4_set():
    py_files = {
        p.name
        for p in STAGE27_ROOT.iterdir()
        if p.is_file() and p.suffix == ".py"
    }
    unexpected = (
        py_files - _STAGE_27_0_THROUGH_27_4_LOCKED_PY_MODULES
    )
    assert not unexpected, (
        f"Stage 27.4 must ship only the locked production .py set; "
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


def test_no_stage_27_4_production_reads_environ():
    leaked: list[str] = []
    for path in _iter_stage27_4_production_files():
        if _module_reads_environ(_read(path)):
            leaked.append(path.name)
    assert not leaked, (
        f"Stage 27.4 production modules must not read os.environ; "
        f"offenders: {leaked!r}"
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


def test_no_stage_27_4_production_imports_runtime_module_patterns():
    for path in _iter_stage27_4_production_files():
        targets = _collect_imported_module_paths(_read(path))
        for target in targets:
            lower = target.lower()
            for pattern in _FORBIDDEN_RUNTIME_MODULE_PATTERNS:
                assert pattern not in lower, (
                    f"{path}: forbidden runtime pattern "
                    f"{pattern!r} in import {target!r}"
                )


def test_no_stage_27_4_production_imports_prior_stage_code():
    for path in _iter_stage27_4_production_files():
        targets = _collect_imported_module_paths(_read(path))
        for target in targets:
            for forbidden in _FORBIDDEN_PRIOR_STAGE_PREFIXES:
                assert not target.startswith(forbidden), (
                    f"{path}: forbidden prior-stage import "
                    f"{target!r}"
                )


def test_no_stage_27_4_production_imports_stage_27_1_modules():
    for path in _iter_stage27_4_production_files():
        targets = _collect_imported_module_paths(_read(path))
        for target in targets:
            for forbidden in _FORBIDDEN_STAGE_27_1_MODULE_PREFIXES:
                assert target != forbidden, (
                    f"{path}: Stage 27.4 must not import Stage 27.1 "
                    f"module {target!r}"
                )
                assert not target.startswith(forbidden + "."), (
                    f"{path}: Stage 27.4 must not import from "
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


def test_no_url_literal_in_stage_27_4_production_source():
    for path in _iter_stage27_4_production_files():
        source = _read(path)
        for needle in _FORBIDDEN_URL_LITERAL_SUBSTRINGS:
            assert needle not in source, (
                f"{path}: forbidden URL literal {needle!r}"
            )


# ---------------------------------------------------------------------------
# Identifier scan: no Stage 27.5+ implementation surface in Stage 27.4
# ---------------------------------------------------------------------------


# Substrings that would indicate Stage 27.5+ implementation creep.
# Stage 27.4's own identifiers legitimately reference price / ATH /
# migration context and the provider-ingest output mirror; those are
# not forbidden here. The substrings below are phrased as literal-
# string concatenations so this test file does not contain the
# exact substring scanners might re-scan.
_FORBIDDEN_LATER_SUBSTAGE_SUBSTRINGS: tuple[str, ...] = (
    "ping" + "_renderer",
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


def test_no_stage_27_4_production_identifier_implements_later_substage():
    for path in _iter_stage27_4_production_files():
        idents = _extract_all_identifiers(_read(path))
        for ident in idents:
            lower = ident.lower()
            for needle in _FORBIDDEN_LATER_SUBSTAGE_SUBSTRINGS:
                assert needle not in lower, (
                    f"{path}: identifier {ident!r} contains "
                    f"forbidden later-substage substring {needle!r}"
                )


# ---------------------------------------------------------------------------
# Stage 27.5+ implementation basenames must not exist
# ---------------------------------------------------------------------------


# Stage 27.7b narrow amendment: ``private_discord_sender.py`` has
# been promoted to the Stage 27.7b production surface and removed
# from the forbidden list. The tuple is now empty.
_STAGE_27_5_PLUS_FORBIDDEN_BASENAMES: tuple[str, ...] = ()


@pytest.mark.parametrize(
    "basename", _STAGE_27_5_PLUS_FORBIDDEN_BASENAMES
)
def test_stage_27_5_plus_basename_does_not_exist_in_stage27_root(
    basename,
):
    path = STAGE27_ROOT / basename
    assert not path.exists(), (
        f"Stage 27.4 must not introduce Stage 27.5+ implementation "
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


def test_no_stage_27_4_production_has_top_level_call():
    for path in _iter_stage27_4_production_files():
        assert not _has_top_level_call(_read(path)), (
            f"{path}: Stage 27.4 production modules must contain no "
            f"top-level Call (no implicit I/O at import time)"
        )


# ---------------------------------------------------------------------------
# Stage 25 / Stage 26 production trees were not touched
# ---------------------------------------------------------------------------


def test_no_stage25_or_stage26_production_files_carry_stage27_4_basename():
    """Stage 25 / Stage 26 production trees must not now carry any
    Stage 27.4 production basename.
    """
    stage25_root = PHX2_ROOT / "stage25"
    stage26_root = PHX2_ROOT / "stage26"
    leaked: list[str] = []
    for root in (stage25_root, stage26_root):
        if not root.exists():
            continue
        for entry in root.iterdir():
            if not entry.is_file():
                continue
            if entry.name in _STAGE_27_4_PRODUCTION_FILENAMES:
                leaked.append(f"{root.name}/{entry.name}")
    assert not leaked, (
        f"Stage 27.4 production basename leaked into a prior stage "
        f"tree: {leaked!r}"
    )


# ---------------------------------------------------------------------------
# Stage 27.4 must not call datetime.now / time.time directly
# ---------------------------------------------------------------------------
#
# Stage 27.4 takes wall-clock reads only through the injected
# ``Stage27_4Clock`` Protocol. A direct ``datetime.now()`` or
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


def test_no_stage_27_4_production_calls_datetime_now():
    for path in _iter_stage27_4_production_files():
        offenders = _module_calls_direct_clock(_read(path))
        assert not offenders, (
            f"{path}: Stage 27.4 must NOT call wall-clock helpers "
            f"directly (use the injected Stage27_4Clock Protocol); "
            f"offenders: {offenders!r}"
        )


# ---------------------------------------------------------------------------
# Stage 27.0 spec-lock amendment shape
# ---------------------------------------------------------------------------


def test_spec_lock_allowlist_admits_stage_27_4_basenames():
    """The Stage 27.0 spec-lock test must have been amended (narrowly)
    to admit the Stage 27.4 production basenames.
    """
    spec_lock_test_path = (
        TESTS_STAGE27_ROOT / "test_stage_27_0_spec_lock.py"
    )
    text = spec_lock_test_path.read_text(encoding="utf-8")
    for basename in _STAGE_27_4_PRODUCTION_FILENAMES:
        assert (
            f'"{basename}"' in text or f"'{basename}'" in text
        ), (
            f"Stage 27.0 spec-lock test allowlist missing Stage 27.4 "
            f"basename {basename!r}"
        )


def test_spec_lock_forbidden_list_still_forbids_stage_27_5_plus():
    """The Stage 27.0 spec-lock test must continue to forbid every
    Stage 27.5+ implementation basename.
    """
    spec_lock_test_path = (
        TESTS_STAGE27_ROOT / "test_stage_27_0_spec_lock.py"
    )
    text = spec_lock_test_path.read_text(encoding="utf-8")
    for basename in _STAGE_27_5_PLUS_FORBIDDEN_BASENAMES:
        assert f'"{basename}"' in text or f"'{basename}'" in text, (
            f"Stage 27.0 spec-lock test forbidden list missing "
            f"Stage 27.5+ basename {basename!r}"
        )


# ---------------------------------------------------------------------------
# Stage 27.4 manifest pin
# ---------------------------------------------------------------------------


def test_stage27_4_manifest_lists_production_basenames():
    from PHX2.stage27.stage27_4_manifest import (
        STAGE27_4_PRODUCTION_BASENAMES,
    )
    assert set(STAGE27_4_PRODUCTION_BASENAMES) == set(
        _STAGE_27_4_PRODUCTION_FILENAMES
    )


def test_stage27_4_manifest_lists_test_basenames():
    from PHX2.stage27.stage27_4_manifest import (
        STAGE27_4_TEST_BASENAMES,
    )
    assert STAGE27_4_TEST_BASENAMES == (
        "test_stage_27_4_price_ath_context_models.py",
        "test_stage_27_4_price_ath_context_reader.py",
        "test_stage_27_4_live_measurement_context.py",
        "test_stage_27_4_boundaries.py",
    )


def test_stage27_4_manifest_re_exports_schema_versions():
    from PHX2.stage27 import stage27_4_manifest as mfst
    assert mfst.STAGE27_4_MINOR_VERSION == "27.4"
    assert (
        mfst.STAGE27_4_PRICE_ATH_SCHEMA_VERSION
        == "stage27_v0_price_ath_context"
    )
    assert (
        mfst.STAGE27_4_MIGRATION_SCHEMA_VERSION
        == "stage27_v0_migration_context"
    )
    assert (
        mfst.STAGE27_4_MEASUREMENT_SCHEMA_VERSION
        == "stage27_v0_measurement_context"
    )

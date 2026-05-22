"""Stage 27.2 boundary scan.

Pins:

  * No Stage 27.2 production module reads the process environment
    (``os.environ`` / ``os.getenv`` / ``os.environb``). The Stage
    27 env-read boundary remains exactly ``live_secrets_readiness.py``;
    Stage 27.2 must not add a second env-read site.
  * No Stage 27.2 production module imports a network, RPC,
    messaging, Discord, Telegram, X / social, or scheduling
    library.
  * No Stage 27.2 production module imports Stage 21-26 production
    code.
  * No Stage 27.2 production module imports Stage 27.1 production
    modules (the pair-detection skeleton is independent of the
    operator-config / secrets-readiness surface and must not
    reach into it).
  * No Stage 27.2 production module carries a URL host literal.
  * Stage 27.2 production source carries no Stage 27.3+
    implementation identifier substrings (provider composition /
    Discord sender / ping renderer / candidate assembler /
    bounded runner / dedupe / ATH context reader / public router /
    X-social).
  * Every Stage 27.2 production file exists.
  * Every Stage 27.3+ implementation basename is still absent
    under ``PHX2/stage27/``.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest


PHX2_ROOT: Path = Path(__file__).resolve().parent.parent.parent
STAGE27_ROOT: Path = PHX2_ROOT / "stage27"


_STAGE_27_2_PRODUCTION_FILENAMES: tuple[str, ...] = (
    "pair_detection_constants.py",
    "pair_detection_models.py",
    "pair_detection_contracts.py",
    "pump_pair_classifier.py",
)


def _iter_stage27_2_production_files() -> list[Path]:
    return [
        STAGE27_ROOT / name
        for name in _STAGE_27_2_PRODUCTION_FILENAMES
    ]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Production-file existence
# ---------------------------------------------------------------------------


def test_every_stage_27_2_production_file_exists():
    for name in _STAGE_27_2_PRODUCTION_FILENAMES:
        path = STAGE27_ROOT / name
        assert path.is_file(), (
            f"Stage 27.2 requires production file {path}"
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


def test_no_stage_27_2_production_reads_environ():
    """Stage 27.2 modules must not read the process environment.

    The Stage 27 env-read boundary remains exactly
    ``live_secrets_readiness.py``.
    """
    leaked: list[str] = []
    for path in _iter_stage27_2_production_files():
        if _module_reads_environ(_read(path)):
            leaked.append(path.name)
    assert not leaked, (
        f"Stage 27.2 production modules must not read os.environ; "
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
    "daemon",
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


# Stage 27.1 production module paths that Stage 27.2 must NOT import.
# Stage 27.2 is the pair-detection skeleton; it does not depend on
# the Stage 27.1 operator-config / secrets-readiness surface, and
# importing into it would imply Stage 27.2 silently learned about
# LIVE-mode authority / secrets / run identity.
_FORBIDDEN_STAGE_27_1_MODULE_PREFIXES: tuple[str, ...] = (
    "PHX2.stage27.live_config_errors",
    "PHX2.stage27.live_config_models",
    "PHX2.stage27.live_run_identity",
    "PHX2.stage27.live_secrets_readiness",
    "PHX2.stage27.live_operator_config",
)


def _collect_imported_module_paths(source: str) -> set[str]:
    """Return only module-path import targets.

    Unlike a full-target collector this returns just the module
    paths so the runtime-pattern scan does not false-trip on
    identifiers that legitimately reference vendor names as string
    constants.
    """
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


def test_no_stage_27_2_production_imports_runtime_module_patterns():
    for path in _iter_stage27_2_production_files():
        targets = _collect_imported_module_paths(_read(path))
        for target in targets:
            lower = target.lower()
            for pattern in _FORBIDDEN_RUNTIME_MODULE_PATTERNS:
                assert pattern not in lower, (
                    f"{path}: forbidden runtime pattern {pattern!r} "
                    f"in import {target!r}"
                )


def test_no_stage_27_2_production_imports_prior_stage_code():
    for path in _iter_stage27_2_production_files():
        targets = _collect_imported_module_paths(_read(path))
        for target in targets:
            for forbidden in _FORBIDDEN_PRIOR_STAGE_PREFIXES:
                assert not target.startswith(forbidden), (
                    f"{path}: forbidden prior-stage import {target!r}"
                )


def test_no_stage_27_2_production_imports_stage_27_1_modules():
    for path in _iter_stage27_2_production_files():
        targets = _collect_imported_module_paths(_read(path))
        for target in targets:
            for forbidden in _FORBIDDEN_STAGE_27_1_MODULE_PREFIXES:
                assert target != forbidden, (
                    f"{path}: Stage 27.2 must not import Stage 27.1 "
                    f"module {target!r}"
                )
                assert not target.startswith(forbidden + "."), (
                    f"{path}: Stage 27.2 must not import from "
                    f"Stage 27.1 module {target!r}"
                )


# ---------------------------------------------------------------------------
# URL / leak literal scan
# ---------------------------------------------------------------------------


# Stage 27.2 must carry no real URL host literal. Scheme-only
# prefixes (e.g. ``"https://"``) are not legitimate in Stage 27.2
# production source at all -- Stage 27.2 has no network surface.
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


def test_no_url_literal_in_stage_27_2_production_source():
    for path in _iter_stage27_2_production_files():
        source = _read(path)
        for needle in _FORBIDDEN_URL_LITERAL_SUBSTRINGS:
            assert needle not in source, (
                f"{path}: forbidden URL literal {needle!r}"
            )


# ---------------------------------------------------------------------------
# Identifier scan: no Stage 27.3+ implementation surface in Stage 27.2
# ---------------------------------------------------------------------------


# Substrings that would indicate Stage 27.3+ implementation creep.
# Stage 27.2's own identifiers legitimately reference pair-detection
# / pair-classifier surfaces; those are not forbidden here. The
# substrings below are phrased as literal-string concatenations so
# this test file does not contain the exact substring scanners
# might re-scan.
_FORBIDDEN_LATER_SUBSTAGE_SUBSTRINGS: tuple[str, ...] = (
    "ping" + "_renderer",
    "discord" + "_sender",
    "candidate" + "_assembler",
    "tradeable" + "_ping_runner",
    "live" + "_dedupe",
    "provider" + "_composition",
    "ath" + "_context_reader",
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


def test_no_stage_27_2_production_identifier_implements_later_substage():
    for path in _iter_stage27_2_production_files():
        idents = _extract_all_identifiers(_read(path))
        for ident in idents:
            lower = ident.lower()
            for needle in _FORBIDDEN_LATER_SUBSTAGE_SUBSTRINGS:
                assert needle not in lower, (
                    f"{path}: identifier {ident!r} contains "
                    f"forbidden later-substage substring {needle!r}"
                )


# ---------------------------------------------------------------------------
# Stage 27.3+ implementation basenames must not exist
# ---------------------------------------------------------------------------


# Stage 27.6 narrow amendment: ``live_candidate_assembler.py``,
# ``bounded_tradeable_ping_runner.py``, ``live_dedupe.py``, and
# ``stage27_6_manifest.py`` have been promoted to the Stage 27.6
# production surface and removed from the forbidden list. The LIVE
# dispatch basename (``private_discord_sender.py``) remains blocked
# at Stage 27.6 closure.
_STAGE_27_5_PLUS_FORBIDDEN_BASENAMES: tuple[str, ...] = (
    "private_discord_sender.py",
)


@pytest.mark.parametrize(
    "basename", _STAGE_27_5_PLUS_FORBIDDEN_BASENAMES
)
def test_stage_27_5_plus_basename_does_not_exist_in_stage27_root(basename):
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
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            return True
    return False


def test_no_stage_27_2_production_has_top_level_call():
    for path in _iter_stage27_2_production_files():
        assert not _has_top_level_call(_read(path)), (
            f"{path}: Stage 27.2 production modules must contain no "
            f"top-level Call (no implicit I/O at import time)"
        )


# ---------------------------------------------------------------------------
# Stage 25 / Stage 26 production trees were not touched
# ---------------------------------------------------------------------------


def test_no_stage25_or_stage26_production_files_carry_stage27_2_basename():
    """Stage 25 / Stage 26 production trees must not now carry any
    Stage 27.2 production basename.
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
            if entry.name in _STAGE_27_2_PRODUCTION_FILENAMES:
                leaked.append(f"{root.name}/{entry.name}")
    assert not leaked, (
        f"Stage 27.2 production basename leaked into a prior stage "
        f"tree: {leaked!r}"
    )

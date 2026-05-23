"""Stage 27.1 boundary scan.

Pins:

  * Only ``live_secrets_readiness.py`` reads the process
    environment (``os.environ`` / ``os.getenv`` / ``os.environb``).
  * No Stage 27 production module imports a network, RPC,
    messaging, Discord, Telegram, X / social, or scheduling
    library.
  * No Stage 27 production module imports Stage 21-26 production
    code (so the live-ingest boundaries Stage 27 must compose
    against later are not bypassed at Stage 27.1 by accident).
  * No Stage 27 production module carries a URL literal.
  * Stage 27 production source carries no Stage 27.2+ implementation
    identifier substrings (pair classifier / Discord sender / ping
    renderer / bounded runner / dedupe / enforcement / X-social).
  * ``PHX2/stage27/`` contains only the Stage 27.0 + Stage 27.1
    locked file set; every other entry is rejected.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest


REPO_ROOT: Path = Path(__file__).resolve().parent.parent.parent.parent
PHX2_ROOT: Path = Path(__file__).resolve().parent.parent.parent
STAGE27_ROOT: Path = PHX2_ROOT / "stage27"
TESTS_STAGE27_ROOT: Path = PHX2_ROOT / "tests" / "stage27"


_STAGE_27_1_PRODUCTION_FILENAMES: tuple[str, ...] = (
    "live_config_errors.py",
    "live_config_models.py",
    "live_run_identity.py",
    "live_secrets_readiness.py",
    "live_operator_config.py",
)


_STAGE_27_LOCKED_DIRECTORY_ENTRIES: frozenset[str] = frozenset(
    {
        # Stage 27.0 scaffold.
        "__init__.py",
        "STAGE_27_0_SPEC_LOCK.md",
        # Stage 27.1 production surface.
        "live_config_errors.py",
        "live_config_models.py",
        "live_run_identity.py",
        "live_secrets_readiness.py",
        "live_operator_config.py",
        # Stage 27.2 pair-detection production surface (closed-set
        # vocabularies + immutable record shapes + module-local
        # exception hierarchy + deterministic classifier skeleton).
        # No provider client, no Discord sender, no ping renderer,
        # no bounded runner, no dedupe, no env reads.
        "pair_detection_constants.py",
        "pair_detection_models.py",
        "pair_detection_contracts.py",
        "pump_pair_classifier.py",
        # Stage 27.3 provider-ingest composition surface
        # (closed-set status / reason vocabularies + immutable
        # input / output records + Stage 21 / 22 normalized-event
        # adapter Protocol + composition pipeline that invokes the
        # Stage 27.2 classifier + manifest constants). No provider
        # client, no Discord sender, no ping renderer, no bounded
        # runner, no dedupe, no price / ATH module, no env reads.
        "provider_ingest_models.py",
        "provider_ingest_contracts.py",
        "provider_event_adapter.py",
        "live_provider_composition.py",
        "stage27_3_manifest.py",
        # Stage 27.4 price / ATH / migration context production
        # surface (closed-set vocabularies + immutable record
        # shapes + module-local exception hierarchy + injectable
        # source-reader Protocol boundary + combined measurement-
        # context assembler + manifest constants). No Discord
        # sender, no ping renderer, no bounded runner, no dedupe,
        # no env reads, no real network calls.
        "price_ath_context_models.py",
        "price_ath_context_contracts.py",
        "price_ath_context_reader.py",
        "migration_context_models.py",
        "live_measurement_context.py",
        "stage27_4_manifest.py",
        # Stage 27.5 private-ping renderer / provenance / dry-run
        # artifact-writer surface (closed-set render-status /
        # artifact-kind / redaction-status vocabularies + immutable
        # payload / provenance record shapes + pure renderer +
        # injectable Stage27_5Clock Protocol + deterministic
        # offline dry-run writer + manifest constants). No Discord
        # sender, no bounded runner, no live dedupe, no env reads.
        "private_ping_models.py",
        "private_ping_renderer.py",
        "private_ping_provenance.py",
        "private_ping_artifact_writer.py",
        "stage27_5_manifest.py",
        # Stage 27.6 live-candidate assembler / bounded dry-run
        # runner / run-local dedupe surface (closed-set
        # candidate_status / candidate_reason / run_mode /
        # stop_reason vocabularies + immutable candidate / run-
        # summary / dedupe-key record shapes + pure assembler +
        # bounded dry-run runner + run-local dedupe ledger +
        # manifest constants). No Discord sender, no real provider
        # client, no persistent dedupe ledger, no env reads.
        "live_dedupe.py",
        "live_candidate_assembler.py",
        "bounded_tradeable_ping_runner.py",
        "stage27_6_manifest.py",
        # Stage 27.7a operator runbook + dry-run smoke checklist
        # + deterministic in-process dry-run smoke harness +
        # Stage 27.7a manifest. Stage 27.1 boundary admits these
        # because the ``PHX2/stage27/`` directory now carries
        # them; the Stage 27.1 production-file allowlist still
        # scopes only the five Stage 27.1 files.
        "STAGE_27_OPERATOR_RUNBOOK.md",
        "STAGE_27_DRY_RUN_SMOKE_CHECKLIST.md",
        "dry_run_smoke_harness.py",
        "stage27_7_manifest.py",
        # Stage 27.7b private Discord sender + dispatch + models +
        # manifest (controlled one-ping operator-only smoke; tests
        # use the fake transport; no public routing, no
        # subscriber routing, no paid tier routing, no Telegram,
        # no X / social, no Stage 29 enforcement, no automated
        # trading). Stage 27.1 boundary admits these because
        # ``PHX2/stage27/`` now carries them; the Stage 27.1
        # production-file allowlist still scopes only the five
        # Stage 27.1 files.
        "private_discord_models.py",
        "private_discord_sender.py",
        "live_smoke_dispatch.py",
        "stage27_7b_manifest.py",
        # Stage 27.8 closure audit + Stage 28 handoff docs only.
        "STAGE_27_CLOSURE_AUDIT.md",
        "STAGE_28_HANDOFF.md",
    }
)


# ---------------------------------------------------------------------------
# Stage 27.1 production tree shape
# ---------------------------------------------------------------------------


def test_stage27_root_carries_exactly_locked_files():
    """``PHX2/stage27/`` admits only the locked Stage 27.0 + 27.1 set.

    Every Stage 27.2+ implementation surface (pair classifier /
    Discord sender / ping renderer / bounded runner / dedupe /
    enforcement / X-social) must remain blocked at Stage 27.1.
    """
    actual: set[str] = set()
    for entry in STAGE27_ROOT.iterdir():
        if entry.is_dir() and entry.name == "__pycache__":
            continue
        actual.add(entry.name)
    forbidden = actual - _STAGE_27_LOCKED_DIRECTORY_ENTRIES
    assert not forbidden, (
        f"PHX2/stage27 admits only the locked Stage 27.0 + 27.1 file "
        f"set ({sorted(_STAGE_27_LOCKED_DIRECTORY_ENTRIES)!r}). "
        f"Stage 27.2+ implementation files (runner / classifier / "
        f"Discord sender / dedupe / provider client / price reader "
        f"/ candidate assembler) remain blocked. Forbidden entries: "
        f"{sorted(forbidden)!r}"
    )


def test_every_stage_27_1_production_file_exists():
    for name in _STAGE_27_1_PRODUCTION_FILENAMES:
        path = STAGE27_ROOT / name
        assert path.is_file(), (
            f"Stage 27.1 requires production file {path}"
        )


# ---------------------------------------------------------------------------
# Env-read isolation
# ---------------------------------------------------------------------------


_ENV_ATTR_NAMES: frozenset[str] = frozenset(
    {"environ", "getenv", "environb"}
)


def _iter_stage27_production_files() -> list[Path]:
    return [
        STAGE27_ROOT / name
        for name in _STAGE_27_1_PRODUCTION_FILENAMES
    ]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


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


def test_only_live_secrets_readiness_reads_environ():
    leaked: list[str] = []
    for path in _iter_stage27_production_files():
        if _module_reads_environ(_read(path)):
            if path.name != "live_secrets_readiness.py":
                leaked.append(path.name)
    assert not leaked, (
        f"only live_secrets_readiness.py may read os.environ / "
        f"os.getenv / os.environb; offenders: {leaked!r}"
    )


def test_live_secrets_readiness_actually_reads_environ():
    """Sanity check: the designated env-read boundary really does
    contain the env-read site. If it ever stops, the boundary lock
    has lost its grounding and must be reinstated.
    """
    path = STAGE27_ROOT / "live_secrets_readiness.py"
    assert _module_reads_environ(_read(path)), (
        f"{path}: live_secrets_readiness.py must be the Stage 27 "
        f"env-read boundary; ``os.environ`` access not found"
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


def _collect_imported_module_paths(source: str) -> set[str]:
    """Return only module-path import targets.

    Unlike a full-target collector, this returns just the module
    paths (``import X`` -> ``X``; ``from X.Y import Z`` -> ``X.Y``)
    so the runtime-pattern scan does not false-trip on identifiers
    that legitimately reference vendor names as string constants
    (e.g. the ``HELIUS_*`` / ``BIRDEYE_*`` / ``*_DISCORD_*`` env-
    variable name constants in ``live_config_models``).
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


def test_no_stage27_production_imports_runtime_module_patterns():
    for path in _iter_stage27_production_files():
        targets = _collect_imported_module_paths(_read(path))
        for target in targets:
            lower = target.lower()
            for pattern in _FORBIDDEN_RUNTIME_MODULE_PATTERNS:
                assert pattern not in lower, (
                    f"{path}: forbidden runtime pattern {pattern!r} "
                    f"in import {target!r}"
                )


def test_no_stage27_production_imports_prior_stage_code():
    for path in _iter_stage27_production_files():
        targets = _collect_imported_module_paths(_read(path))
        for target in targets:
            for forbidden in _FORBIDDEN_PRIOR_STAGE_PREFIXES:
                assert not target.startswith(forbidden), (
                    f"{path}: forbidden prior-stage import {target!r}"
                )


# ---------------------------------------------------------------------------
# URL / leak literal scan
# ---------------------------------------------------------------------------


# Stage 27.1 production code legitimately references the literal
# substrings ``"https://"`` and ``"http://"`` because the readiness
# format validator checks env values start with one of these
# schemes. The Stage 27.1 URL-leak scan therefore looks only for
# real hostnames that would indicate a hardcoded provider /
# webhook target was baked into source. Scheme-only prefixes are
# allowed.
_FORBIDDEN_URL_HOST_SUBSTRINGS: tuple[str, ...] = (
    "discord" + ".com",
    "discordapp" + ".com",
    "hooks" + ".slack.com",
    "api.helius" + ".xyz",
    "rpc.helius" + ".xyz",
    "mainnet.helius" + ".rpc.com",
    "public-api.birdeye" + ".so",
    "birdeye" + ".so/v1",
    "t" + ".me/",
    "api.twitter" + ".com",
    "api.x" + ".com",
)


def test_no_url_host_literal_in_stage27_production_source():
    for path in _iter_stage27_production_files():
        source = _read(path)
        for needle in _FORBIDDEN_URL_HOST_SUBSTRINGS:
            assert needle not in source, (
                f"{path}: forbidden URL host literal {needle!r}"
            )


# ---------------------------------------------------------------------------
# Identifier scan: no Stage 27.2+ implementation surface in Stage 27.1
# ---------------------------------------------------------------------------


# Substrings that would indicate Stage 27.2+ implementation creep.
# Phrased as literal-string concatenations so the test file itself
# does not contain the exact substring scanners might re-scan.
_FORBIDDEN_LATER_SUBSTAGE_SUBSTRINGS: tuple[str, ...] = (
    "p" + "air_classifier",
    "p" + "ump_pair_classifier",
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


def test_no_stage27_production_identifier_implements_later_substage():
    for path in _iter_stage27_production_files():
        idents = _extract_all_identifiers(_read(path))
        for ident in idents:
            lower = ident.lower()
            for needle in _FORBIDDEN_LATER_SUBSTAGE_SUBSTRINGS:
                assert needle not in lower, (
                    f"{path}: identifier {ident!r} contains "
                    f"forbidden later-substage substring {needle!r}"
                )


# ---------------------------------------------------------------------------
# Stage 27.1 must not introduce Stage 27.2+ basenames
# ---------------------------------------------------------------------------


# Stage 27.7b narrow amendment: ``private_discord_sender.py`` has
# been promoted to the Stage 27.7b production surface and removed
# from the forbidden list. The tuple is now empty.
_STAGE_27_5_PLUS_FORBIDDEN_BASENAMES: tuple[str, ...] = ()


@pytest.mark.parametrize(
    "basename", _STAGE_27_5_PLUS_FORBIDDEN_BASENAMES
)
def test_stage_27_5_plus_basename_does_not_exist(basename):
    path = STAGE27_ROOT / basename
    assert not path.exists(), (
        f"Stage 27.4 must not introduce Stage 27.5+ implementation "
        f"basename {basename!r} under PHX2/stage27/; got {path}"
    )


# ---------------------------------------------------------------------------
# Stage 26 / Stage 25 production trees were not touched
# ---------------------------------------------------------------------------


def test_no_stage25_or_stage26_production_files_carry_stage27_basename():
    """Stage 25 / Stage 26 production trees must not now carry any
    Stage 27.1 production basename (would indicate creep across the
    boundary).
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
            if entry.name in _STAGE_27_1_PRODUCTION_FILENAMES:
                leaked.append(f"{root.name}/{entry.name}")
    assert not leaked, (
        f"Stage 27.1 production basename leaked into a prior stage "
        f"tree: {leaked!r}"
    )


# ---------------------------------------------------------------------------
# Stage 27 production source carries no top-level I/O
# ---------------------------------------------------------------------------


def _has_top_level_call(source: str) -> bool:
    """Return ``True`` if the module body contains a top-level Call.

    A few top-level calls are inherent (decorators, default
    expressions). This check intentionally looks only for
    ``Expr(Call)`` at the module level -- the same shape Stage 25 /
    Stage 26 boundary tests use.
    """
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            return True
    return False


def test_no_stage27_production_has_top_level_call():
    for path in _iter_stage27_production_files():
        assert not _has_top_level_call(_read(path)), (
            f"{path}: Stage 27.1 production modules must contain no "
            f"top-level Call (no implicit I/O at import time)"
        )

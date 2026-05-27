"""Stage 28.10 boundary scan.

Pins:

  * Every Stage 28.10 production .py file exists at the locked
    path.
  * Every Stage 28.10 operator doc exists at the locked path.
  * Every Stage 28.10 test file exists at the locked path.
  * Stage 28.10 production .py modules other than the hint-aware
    candidate assembler import only stdlib + Stage 28 sibling
    modules.
  * The Stage 28.10 hint-aware candidate assembler is the ONE
    Stage 28.10 module allowed to import the approved Stage 21 /
    Stage 27 surfaces; the other Stage 28.10 production modules
    must NOT import Stage 21-27 production code.
  * Stage 28.10 production .py modules never read ``os.environ`` /
    ``os.getenv`` / ``os.environb``.
  * Stage 28.10 production .py modules contain no top-level Call
    (no implicit I/O at import time) and no top-level filesystem
    write call.
  * Stage 28.10 production source carries no URL host literal,
    no raw-secret literal, no auth-header / bearer / API-key
    prefix literal.
  * Stage 28.10 production identifiers never implement a Stage
    29+ enforcement surface, a public router, a subscriber
    router, a paid tier, Telegram, X / social, automated trading,
    wallet / private-key / signer logic, position sizing, trade
    execution, dashboard / control server, or a daemon /
    watchdog / autorestart service.
  * The Stage 28.10 manifest declares the locked basename
    inventories and scope locks.
  * Stage 28.10 production .py modules never import
    asyncio / threading / multiprocessing / subprocess / queue /
    sched / socket / urllib / http.client / ssl / grpc / grpcio /
    protobuf / requests / httpx / aiohttp / websockets / discord
    / discord.py / telegram / telethon / dotenv / keyring /
    tweepy / twitter, never call sleep / wait / schedule /
    create_task / run_until_complete.
  * No Stage 29 implementation tree exists.
  * No generated ``*_pb2.py`` / ``*_pb2_grpc.py`` stub lives
    under Stage 28.10.
  * No Stage 28.10 production module installs a dependency.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest


PHX2_ROOT: Path = Path(__file__).resolve().parent.parent.parent
REPO_ROOT: Path = PHX2_ROOT.parent
STAGE28_ROOT: Path = PHX2_ROOT / "stage28"
STAGE29_ROOT: Path = PHX2_ROOT / "stage29"
TESTS_STAGE28_ROOT: Path = PHX2_ROOT / "tests" / "stage28"


# ---------------------------------------------------------------------------
# Locked Stage 28.10 inventories
# ---------------------------------------------------------------------------


_STAGE_28_10_PRODUCTION_PY_BASENAMES: tuple[str, ...] = (
    "chainstack_yellowstone_models.py",
    "chainstack_yellowstone_contracts.py",
    "chainstack_yellowstone_event_source.py",
    "chainstack_yellowstone_candidate_assembler.py",
    "stage28_10_manifest.py",
)


_STAGE_28_10_DOC_BASENAMES: tuple[str, ...] = (
    "STAGE_28_10_CHAINSTACK_YELLOWSTONE_RUNBOOK.md",
)


_STAGE_28_10_TEST_BASENAMES: tuple[str, ...] = (
    "test_stage_28_10_chainstack_yellowstone_models.py",
    "test_stage_28_10_chainstack_yellowstone_contracts.py",
    "test_stage_28_10_chainstack_yellowstone_event_source.py",
    "test_stage_28_10_chainstack_yellowstone_candidate_assembler.py",
    "test_stage_28_10_runbook.py",
    "test_stage_28_10_boundaries.py",
)


# The Stage 28.10 hint-aware candidate assembler is the ONE Stage
# 28.10 module allowed to import approved Stage 21 / Stage 27
# surfaces. Every other Stage 28.10 production module must NOT.
_STAGE_28_10_BRIDGE_BASENAME: str = (
    "chainstack_yellowstone_candidate_assembler.py"
)


# Stage 21 / Stage 27 imports the Stage 28.10 hint-aware
# candidate assembler is allowed to use. Other Stage 28.10
# modules must not import any of these (or any other Stage 21-27
# module).
_BRIDGE_ALLOWED_STAGE_27_IMPORTS: frozenset[str] = frozenset({
    "PHX2.stage27.live_candidate_assembler",
    "PHX2.stage27.live_dedupe",
    "PHX2.stage27.provider_event_adapter",
})


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _iter_stage28_10_production_py_files() -> list[Path]:
    return [
        STAGE28_ROOT / name
        for name in _STAGE_28_10_PRODUCTION_PY_BASENAMES
    ]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


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


# ---------------------------------------------------------------------------
# Production / doc / test inventory + existence
# ---------------------------------------------------------------------------


def test_every_stage_28_10_production_py_file_exists():
    for name in _STAGE_28_10_PRODUCTION_PY_BASENAMES:
        path = STAGE28_ROOT / name
        assert path.is_file(), (
            f"Stage 28.10 requires production .py file {path}"
        )


def test_every_stage_28_10_doc_file_exists():
    for name in _STAGE_28_10_DOC_BASENAMES:
        path = STAGE28_ROOT / name
        assert path.is_file(), (
            f"Stage 28.10 requires operator doc {path}"
        )


def test_every_stage_28_10_test_file_exists():
    for name in _STAGE_28_10_TEST_BASENAMES:
        path = TESTS_STAGE28_ROOT / name
        assert path.is_file(), (
            f"Stage 28.10 requires test file {path}"
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


def test_no_stage_28_10_production_reads_environ():
    leaked: list[str] = []
    for path in _iter_stage28_10_production_py_files():
        if _module_reads_environ(_read(path)):
            leaked.append(path.name)
    assert not leaked, (
        f"Stage 28.10 production must not read os.environ / "
        f"os.getenv / os.environb; offenders: {leaked!r}"
    )


# ---------------------------------------------------------------------------
# Forbidden imports
# ---------------------------------------------------------------------------


_FORBIDDEN_RUNTIME_MODULE_PATTERNS: tuple[str, ...] = (
    "requests",
    "httpx",
    "aiohttp",
    "urllib",
    "urllib3",
    "websockets",
    "grpc",
    "grpcio",
    "grpc_tools",
    "google.protobuf",
    "protobuf",
    "solders",
    "solana",
    "construct",
    "base58",
    "helius",
    "jupiter",
    "birdeye",
    "discord",
    "discord.",
    "discord_py",
    "telegram",
    "telethon",
    "webhook_client",
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
    "socket",
    "asyncio",
    "threading",
    "multiprocessing",
    "subprocess",
    "queue",
    "sched",
    "http.client",
    "http",
    "ssl",
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


def test_no_stage_28_10_production_imports_runtime_module_patterns():
    for path in _iter_stage28_10_production_py_files():
        targets = _collect_imported_module_paths(_read(path))
        for target in targets:
            if target.startswith("PHX2."):
                continue
            lower = target.lower()
            for pattern in _FORBIDDEN_RUNTIME_MODULE_PATTERNS:
                assert pattern not in lower, (
                    f"{path}: forbidden runtime pattern "
                    f"{pattern!r} in import {target!r}"
                )


def test_no_stage_28_10_production_imports_prior_stage_17_through_26():
    for path in _iter_stage28_10_production_py_files():
        targets = _collect_imported_module_paths(_read(path))
        for target in targets:
            for forbidden in _FORBIDDEN_PRIOR_STAGE_PREFIXES:
                assert not target.startswith(forbidden), (
                    f"{path}: forbidden prior-stage import "
                    f"{target!r}"
                )


def test_only_bridge_imports_stage_27():
    """Stage 28.10 admits Stage 27 imports ONLY in the hint-aware
    candidate assembler module. The Stage 28.10 models /
    contracts / event source / manifest modules MUST NOT import
    Stage 27 production code.
    """
    for path in _iter_stage28_10_production_py_files():
        targets = _collect_imported_module_paths(_read(path))
        if path.name == _STAGE_28_10_BRIDGE_BASENAME:
            continue
        for target in targets:
            assert not target.startswith("PHX2.stage21"), (
                f"{path}: only the Stage 28.10 hint-aware "
                f"candidate assembler may import Stage 21 "
                f"modules; saw {target!r}"
            )
            assert not target.startswith("PHX2.stage27"), (
                f"{path}: only the Stage 28.10 hint-aware "
                f"candidate assembler may import Stage 27 "
                f"modules; saw {target!r}"
            )


def test_bridge_assembler_stage_27_imports_only_approved_modules():
    bridge_path = STAGE28_ROOT / _STAGE_28_10_BRIDGE_BASENAME
    targets = _collect_imported_module_paths(_read(bridge_path))
    stage_27_imports = {
        t for t in targets if t.startswith("PHX2.stage27")
    }
    for target in stage_27_imports:
        assert target in _BRIDGE_ALLOWED_STAGE_27_IMPORTS, (
            f"Stage 28.10 hint-aware candidate assembler imports "
            f"unapproved Stage 27 module {target!r}; allowed: "
            f"{sorted(_BRIDGE_ALLOWED_STAGE_27_IMPORTS)!r}"
        )


def test_no_stage_28_10_production_imports_stage_29():
    for path in _iter_stage28_10_production_py_files():
        targets = _collect_imported_module_paths(_read(path))
        for target in targets:
            assert not target.startswith("PHX2.stage29"), (
                f"{path}: Stage 28.10 must not import Stage 29 "
                f"module; saw {target!r}"
            )


# Stage 29.0 narrow amendment: allow ``PHX2/stage29/`` to exist
# iff it contains the Stage 29.0 scaffold (package marker +
# spec-lock doc).
# Stage 29.1 PumpSwap-only narrow amendment (authorized): also
# admit the Stage 29.1 PumpSwap-only hint-extractor tree. Stage
# 29.2 / 29.3 implementation files AND any Pump.fun
# bonding-curve files remain blocked from Stage 28.10.
_STAGE_29_0_ALLOWED_PROD_BASENAMES: frozenset[str] = frozenset(
    {"__init__.py", "STAGE_29_0_SPEC_LOCK.md"}
)


_STAGE_29_1_PUMPSWAP_ALLOWED_PROD_BASENAMES: frozenset[str] = (
    frozenset(
        {
            "pumpswap_program_constants.py",
            "pumpswap_hint_models.py",
            "pumpswap_hint_extractor.py",
            "pumpswap_hint_aware_decoder.py",
            "stage29_1_hint_probe_models.py",
            "stage29_1_pumpswap_hint_probe.py",
            "stage29_1_manifest.py",
            "STAGE_29_1_PUMPSWAP_HINT_EXTRACTOR_RUNBOOK.md",
        }
    )
)


# Stage 29.2 Birdeye price / ATH adapter (authorized 2026-05-25).
# Stage 28.10 narrow amendment widens the Stage-29-tree allowlist
# to admit the Stage 29.2 inventory while continuing to block
# Stage 29.3 implementation files + Pump.fun bonding-curve.
_STAGE_29_2_BIRDEYE_ALLOWED_PROD_BASENAMES: frozenset[str] = (
    frozenset(
        {
            "birdeye_constants.py",
            "stage29_2_birdeye_models.py",
            "stage29_2_birdeye_readiness.py",
            "stage29_2_birdeye_http_transport.py",
            "stage29_2_birdeye_price_source.py",
            "stage29_2_birdeye_ath_source.py",
            "stage29_2_birdeye_probe_models.py",
            "stage29_2_birdeye_probe.py",
            "stage29_2_manifest.py",
            "STAGE_29_2_BIRDEYE_PRICE_ATH_RUNBOOK.md",
        }
    )
)


_STAGE_29_3_TRADEABLE_SMOKE_ALLOWED_PROD_BASENAMES: frozenset[
    str
] = frozenset(
    {
        "stage29_3_smoke_models.py",
        "stage29_3_no_migration_evidence_source.py",
        "stage29_3_hint_aware_event_source.py",
        "stage29_3_artifact_writer.py",
        "stage29_3_tradeable_smoke.py",
        "stage29_3_manifest.py",
        "STAGE_29_3_FIRST_PRIVATE_TRADEABLE_SMOKE_RUNBOOK.md",
    }
)


# Stage 29.4 short-session private soak (authorized 2026-05-25).
# Stage 29.4.0 is spec-lock-only: this narrow amendment widens
# the Stage-29-tree allowlist to admit the Stage 29.4 runbook
# only. Stage 29.4.1 (separately authorized) widens this further
# to admit the five Stage 29.4 production .py basenames.
_STAGE_29_4_SOAK_SPEC_LOCK_ALLOWED_PROD_BASENAMES: frozenset[
    str
] = frozenset(
    {
        "STAGE_29_4_SHORT_SESSION_PRIVATE_SOAK_RUNBOOK.md",
        # Stage 29.4.1 widens the Stage 28.10 narrow amendment to
        # admit the five Stage 29.4 production .py basenames
        # pinned by the Stage 29.4.0 runbook (Section 9).
        "stage29_4_soak_models.py",
        "stage29_4_dedupe_index.py",
        "stage29_4_soak_orchestrator.py",
        "stage29_4_soak_artifact_writer.py",
        "stage29_4_manifest.py",
    }
)


# Stage 29.5 Helius WS migration evidence adapter + live private
# ping context join (authorized 2026-05-25). Stage 29.5.0 is
# spec-lock-only: this narrow amendment widens the Stage-29-tree
# allowlist to admit the Stage 29.5 spec-lock runbook only.
# Stage 29.5.1 production .py files
# (stage29_5_migration_models.py / stage29_5_helius_ws_adapter.py
# / stage29_5_migration_artifact_reader.py /
# stage29_5_candidate_to_migration_join.py /
# stage29_5_private_ping_context_projection.py /
# stage29_5_manifest.py) remain blocked at Stage 29.5.0.
_STAGE_29_5_MIGRATION_EVIDENCE_SPEC_LOCK_ALLOWED_PROD_BASENAMES: frozenset[
    str
] = frozenset(
    {
        "STAGE_29_5_MIGRATION_EVIDENCE_SPEC_LOCK.md",
        # Stage 29.5.1 production .py files (authorized 2026-05-25).
        "stage29_5_migration_models.py",
        "stage29_5_helius_ws_adapter.py",
        "stage29_5_migration_artifact_reader.py",
        "stage29_5_candidate_to_migration_join.py",
        "stage29_5_private_ping_context_projection.py",
        "stage29_5_manifest.py",
    }
)


# Stage 29.5.2 offline integration proof (authorized 2026-05-26).
# Stage 29.5.2 is the offline composition proof substage: this
# narrow amendment widens the Stage 28.10 narrow Stage-29-prod
# allowlist to admit the Stage 29.5.2 production + doc inventory.
# No runtime wiring into Stage 29.3 / 29.4 lands at Stage 29.5.2.
_STAGE_29_5_2_OFFLINE_INTEGRATION_ALLOWED_PROD_BASENAMES: frozenset[
    str
] = frozenset(
    {
        "STAGE_29_5_2_OFFLINE_INTEGRATION_PROOF_RUNBOOK.md",
        "stage29_5_2_offline_integration.py",
        "stage29_5_2_synthetic_evidence_fixtures.py",
        "stage29_5_2_manifest.py",
    }
)


# Stage 29.5.3 soak pass-entrypoint wrapper (authorized
# 2026-05-26). Stage 29.5.3 ships the runtime-adjacent wrapper +
# side-channel artifact surface that bridges Stage 29.5.2's
# offline composition into the Stage 29.4 soak path WITHOUT
# editing any Stage 29.3 or Stage 29.4 production source. This
# narrow amendment widens the Stage 28.10 Stage-29-prod
# allowlist to admit the Stage 29.5.3 production + doc inventory.
_STAGE_29_5_3_SOAK_PASS_WRAPPER_ALLOWED_PROD_BASENAMES: frozenset[
    str
] = frozenset(
    {
        "STAGE_29_5_3_SOAK_PASS_WRAPPER_RUNBOOK.md",
        "stage29_5_3_wrapped_pass_models.py",
        "stage29_5_3_soak_pass_wrapper.py",
        "stage29_5_3_side_channel_artifact_writer.py",
        "stage29_5_3_manifest.py",
    }
)


# Stage 29.5.4 direct opt-in migration context injection (authorized
# 2026-05-26). Narrow amendment widens the Stage 28.10 Stage-29-
# prod allowlist to admit the Stage 29.5.4 production + doc
# inventory.
_STAGE_29_5_4_MIGRATION_CONTEXT_INJECTION_ALLOWED_PROD_BASENAMES: frozenset[
    str
] = frozenset(
    {
        "STAGE_29_5_4_MIGRATION_CONTEXT_INJECTION_RUNBOOK.md",
        "stage29_5_4_migration_context_source_adapter.py",
        "stage29_5_4_manifest.py",
    }
)


# Stage 29.5.5 formatted private discord migration context
# rendering (authorized 2026-05-26). Narrow amendment widens
# the Stage 28.10 Stage-29-prod allowlist to admit the Stage
# 29.5.5 production + doc inventory.
_STAGE_29_5_5_PRIVATE_DISCORD_RENDERING_ALLOWED_PROD_BASENAMES: frozenset[
    str
] = frozenset(
    {
        "STAGE_29_5_5_PRIVATE_DISCORD_MIGRATION_CONTEXT_RENDERING_RUNBOOK.md",
        "stage29_5_5_render_models.py",
        "stage29_5_5_private_discord_migration_context_renderer.py",
        "stage29_5_5_migration_context_recorder.py",
        "stage29_5_5_side_channel_artifact_writer.py",
        "stage29_5_5_manifest.py",
    }
)


_STAGE_29_0_PLUS_29_1_ALLOWED_PROD_BASENAMES: frozenset[str] = (
    _STAGE_29_0_ALLOWED_PROD_BASENAMES
    | _STAGE_29_1_PUMPSWAP_ALLOWED_PROD_BASENAMES
    | _STAGE_29_2_BIRDEYE_ALLOWED_PROD_BASENAMES
    | _STAGE_29_3_TRADEABLE_SMOKE_ALLOWED_PROD_BASENAMES
    | _STAGE_29_4_SOAK_SPEC_LOCK_ALLOWED_PROD_BASENAMES
    | _STAGE_29_5_MIGRATION_EVIDENCE_SPEC_LOCK_ALLOWED_PROD_BASENAMES
    | _STAGE_29_5_2_OFFLINE_INTEGRATION_ALLOWED_PROD_BASENAMES
    | _STAGE_29_5_3_SOAK_PASS_WRAPPER_ALLOWED_PROD_BASENAMES
    | _STAGE_29_5_4_MIGRATION_CONTEXT_INJECTION_ALLOWED_PROD_BASENAMES
    | _STAGE_29_5_5_PRIVATE_DISCORD_RENDERING_ALLOWED_PROD_BASENAMES
)


_STAGE_29_0_ALLOWED_TEST_BASENAMES: frozenset[str] = frozenset(
    {"__init__.py", "test_stage_29_0_spec_lock.py"}
)


_STAGE_29_1_PUMPSWAP_ALLOWED_TEST_BASENAMES: frozenset[str] = (
    frozenset(
        {
            "test_stage_29_1_pumpswap_program_constants.py",
            "test_stage_29_1_pumpswap_hint_models.py",
            "test_stage_29_1_pumpswap_hint_extractor.py",
            "test_stage_29_1_pumpswap_hint_aware_decoder.py",
            "test_stage_29_1_hint_probe_models.py",
            "test_stage_29_1_pumpswap_hint_probe.py",
            "test_stage_29_1_runbook.py",
            "test_stage_29_1_boundaries.py",
            "test_stage_29_1_vendored_idl.py",
        }
    )
)


_STAGE_29_2_BIRDEYE_ALLOWED_TEST_BASENAMES: frozenset[str] = (
    frozenset(
        {
            "test_stage_29_2_birdeye_constants.py",
            "test_stage_29_2_birdeye_models.py",
            "test_stage_29_2_birdeye_readiness.py",
            "test_stage_29_2_birdeye_http_transport.py",
            "test_stage_29_2_birdeye_price_source.py",
            "test_stage_29_2_birdeye_ath_source.py",
            "test_stage_29_2_birdeye_probe_models.py",
            "test_stage_29_2_birdeye_probe.py",
            "test_stage_29_2_runbook.py",
            "test_stage_29_2_boundaries.py",
        }
    )
)


_STAGE_29_3_TRADEABLE_SMOKE_ALLOWED_TEST_BASENAMES: frozenset[
    str
] = frozenset(
    {
        "test_stage_29_3_smoke_models.py",
        "test_stage_29_3_no_migration_evidence_source.py",
        "test_stage_29_3_hint_aware_event_source.py",
        "test_stage_29_3_tradeable_smoke_orchestrator.py",
        "test_stage_29_3_artifact_writer.py",
        "test_stage_29_3_runbook.py",
        "test_stage_29_3_boundaries.py",
    }
)


# Stage 29.4 short-session private soak (authorized 2026-05-25).
# Stage 29.4.0 is spec-lock-only: this narrow amendment widens
# the Stage-29-tests allowlist to admit the Stage 29.4 spec-
# lock test only. Stage 29.4.1 (separately authorized) widens
# this further to admit the focused Stage 29.4 test files.
_STAGE_29_4_SOAK_SPEC_LOCK_ALLOWED_TEST_BASENAMES: frozenset[
    str
] = frozenset(
    {
        "test_stage_29_4_spec_lock.py",
        # Stage 29.4.1 widens the Stage 28.10 narrow amendment to
        # admit the focused Stage 29.4 test files.
        "test_stage_29_4_soak_models.py",
        "test_stage_29_4_dedupe_index.py",
        "test_stage_29_4_soak_orchestrator.py",
        "test_stage_29_4_soak_artifact_writer.py",
        "test_stage_29_4_boundaries.py",
    }
)


# Stage 29.5 Helius WS migration evidence adapter + live private
# ping context join (authorized 2026-05-25). Stage 29.5.0 is
# spec-lock-only: this narrow amendment widens the Stage-29-
# tests allowlist to admit the Stage 29.5 spec-lock test only.
# Stage 29.5.1 test files remain blocked at Stage 29.5.0.
_STAGE_29_5_MIGRATION_EVIDENCE_SPEC_LOCK_ALLOWED_TEST_BASENAMES: frozenset[
    str
] = frozenset(
    {
        "test_stage_29_5_spec_lock.py",
        # Stage 29.5.1 focused test files (authorized 2026-05-25).
        "test_stage_29_5_migration_models.py",
        "test_stage_29_5_helius_ws_adapter.py",
        "test_stage_29_5_migration_artifact_reader.py",
        "test_stage_29_5_candidate_to_migration_join.py",
        "test_stage_29_5_private_ping_context_projection.py",
        "test_stage_29_5_manifest.py",
        "test_stage_29_5_boundaries.py",
    }
)


# Stage 29.5.2 offline integration proof tests (authorized
# 2026-05-26). Narrow amendment widens the Stage 28.10 Stage-29-
# tests allowlist to admit the Stage 29.5.2 test inventory.
_STAGE_29_5_2_OFFLINE_INTEGRATION_ALLOWED_TEST_BASENAMES: frozenset[
    str
] = frozenset(
    {
        "test_stage_29_5_2_offline_integration.py",
        "test_stage_29_5_2_boundaries.py",
        "test_stage_29_5_2_no_integration_into_stage_29_3.py",
        "test_stage_29_5_2_manifest.py",
        "test_stage_29_5_2_spec_lock.py",
    }
)


# Stage 29.5.3 soak pass-entrypoint wrapper tests (authorized
# 2026-05-26). Narrow amendment widens the Stage 28.10 Stage-29-
# tests allowlist to admit the Stage 29.5.3 test inventory.
_STAGE_29_5_3_SOAK_PASS_WRAPPER_ALLOWED_TEST_BASENAMES: frozenset[
    str
] = frozenset(
    {
        "test_stage_29_5_3_wrapped_pass_models.py",
        "test_stage_29_5_3_soak_pass_wrapper.py",
        "test_stage_29_5_3_side_channel_artifact_writer.py",
        "test_stage_29_5_3_manifest.py",
        "test_stage_29_5_3_boundaries.py",
        "test_stage_29_5_3_no_modification_to_stage_29_3_or_29_4.py",
        "test_stage_29_5_3_spec_lock.py",
    }
)


# Stage 29.5.4 direct opt-in migration context injection tests
# (authorized 2026-05-26). Narrow amendment widens the Stage 28.10
# Stage-29-tests allowlist to admit the Stage 29.5.4 test
# inventory.
_STAGE_29_5_4_MIGRATION_CONTEXT_INJECTION_ALLOWED_TEST_BASENAMES: frozenset[
    str
] = frozenset(
    {
        "test_stage_29_5_4_migration_context_source_adapter.py",
        "test_stage_29_5_4_stage29_3_integration.py",
        "test_stage_29_5_4_default_preserves_no_migration_path.py",
        "test_stage_29_5_4_no_duplicate_dispatch.py",
        "test_stage_29_5_4_no_live_surface.py",
        "test_stage_29_5_4_no_public_no_enforcement_no_trading_no_social.py",
        "test_stage_29_5_4_boundaries.py",
        "test_stage_29_5_4_manifest.py",
        "test_stage_29_5_4_spec_lock.py",
        "test_stage_29_5_4_counter_invariants.py",
    }
)


# Stage 29.5.5 formatted private discord migration context
# rendering tests (authorized 2026-05-26). Narrow amendment
# widens the Stage 28.10 Stage-29-tests allowlist to admit the
# Stage 29.5.5 test inventory.
_STAGE_29_5_5_PRIVATE_DISCORD_RENDERING_ALLOWED_TEST_BASENAMES: frozenset[
    str
] = frozenset(
    {
        "test_stage_29_5_5_render_models.py",
        "test_stage_29_5_5_renderer.py",
        "test_stage_29_5_5_status_matrix.py",
        "test_stage_29_5_5_migration_context_recorder.py",
        "test_stage_29_5_5_side_channel_artifact_writer.py",
        "test_stage_29_5_5_redaction.py",
        "test_stage_29_5_5_stage29_3_integration.py",
        "test_stage_29_5_5_default_preserves_no_renderer_path.py",
        "test_stage_29_5_5_no_duplicate_dispatch.py",
        "test_stage_29_5_5_no_live_surface.py",
        "test_stage_29_5_5_no_enforcement_activation.py",
        "test_stage_29_5_5_no_public_no_enforcement_no_trading_no_social.py",
        "test_stage_29_5_5_boundaries.py",
        "test_stage_29_5_5_manifest.py",
        "test_stage_29_5_5_spec_lock.py",
        "test_stage_29_5_5_counter_invariants.py",
    }
)


_STAGE_29_0_PLUS_29_1_ALLOWED_TEST_BASENAMES: frozenset[str] = (
    _STAGE_29_0_ALLOWED_TEST_BASENAMES
    | _STAGE_29_1_PUMPSWAP_ALLOWED_TEST_BASENAMES
    | _STAGE_29_2_BIRDEYE_ALLOWED_TEST_BASENAMES
    | _STAGE_29_3_TRADEABLE_SMOKE_ALLOWED_TEST_BASENAMES
    | _STAGE_29_4_SOAK_SPEC_LOCK_ALLOWED_TEST_BASENAMES
    | _STAGE_29_5_MIGRATION_EVIDENCE_SPEC_LOCK_ALLOWED_TEST_BASENAMES
    | _STAGE_29_5_2_OFFLINE_INTEGRATION_ALLOWED_TEST_BASENAMES
    | _STAGE_29_5_3_SOAK_PASS_WRAPPER_ALLOWED_TEST_BASENAMES
    | _STAGE_29_5_4_MIGRATION_CONTEXT_INJECTION_ALLOWED_TEST_BASENAMES
    | _STAGE_29_5_5_PRIVATE_DISCORD_RENDERING_ALLOWED_TEST_BASENAMES
)


def test_no_stage29_implementation_tree_exists():
    # Stage 29.0 + Stage 29.1 PumpSwap-only narrow amendment:
    # PHX2/stage29/ may exist iff it ships only the Stage 29.0
    # scaffold AND the Stage 29.1 PumpSwap-only hint-extractor
    # tree. Stage 29.2 / 29.3 implementation files AND any
    # Pump.fun bonding-curve files remain blocked from Stage
    # 28.10.
    if not STAGE29_ROOT.exists():
        return
    actual = {
        entry.name
        for entry in STAGE29_ROOT.iterdir()
        if not (entry.is_dir() and entry.name == "__pycache__")
    }
    forbidden = (
        actual - _STAGE_29_0_PLUS_29_1_ALLOWED_PROD_BASENAMES
    )
    assert not forbidden, (
        f"Stage 28.10 narrow amendment: PHX2/stage29 admits "
        f"only the Stage 29.0 scaffold + Stage 29.1 PumpSwap-"
        f"only tree "
        f"({sorted(_STAGE_29_0_PLUS_29_1_ALLOWED_PROD_BASENAMES)!r}); "
        f"Stage 29.2 / 29.3 files + Pump.fun bonding-curve "
        f"files remain blocked. Forbidden entries: "
        f"{sorted(forbidden)!r}"
    )


def test_no_stage29_tests_tree_exists():
    # Stage 29.0 + Stage 29.1 PumpSwap-only narrow amendment:
    # PHX2/tests/stage29/ may exist iff it ships only the Stage
    # 29.0 tests package marker, the Stage 29.0 spec-lock test,
    # and the Stage 29.1 PumpSwap-only test set. Stage 29.2 /
    # 29.3 test files + Pump.fun bonding-curve test files
    # remain blocked.
    tests_stage29 = PHX2_ROOT / "tests" / "stage29"
    if not tests_stage29.exists():
        return
    actual = {
        entry.name
        for entry in tests_stage29.iterdir()
        if not (entry.is_dir() and entry.name == "__pycache__")
    }
    forbidden = (
        actual - _STAGE_29_0_PLUS_29_1_ALLOWED_TEST_BASENAMES
    )
    assert not forbidden, (
        f"Stage 28.10 narrow amendment: PHX2/tests/stage29 "
        f"admits only the Stage 29.0 tests + Stage 29.1 "
        f"PumpSwap-only tests "
        f"({sorted(_STAGE_29_0_PLUS_29_1_ALLOWED_TEST_BASENAMES)!r}); "
        f"Stage 29.2 / 29.3 test files + Pump.fun bonding-curve "
        f"test files remain blocked. Forbidden entries: "
        f"{sorted(forbidden)!r}"
    )


# ---------------------------------------------------------------------------
# No generated pb2 / pb2_grpc stub under Stage 28.10
# ---------------------------------------------------------------------------


def test_no_generated_protobuf_stub_under_stage28():
    leaked: list[str] = []
    for entry in STAGE28_ROOT.iterdir():
        if not entry.is_file():
            continue
        if entry.suffix != ".py":
            continue
        if entry.name.endswith("_pb2.py"):
            leaked.append(entry.name)
        if entry.name.endswith("_pb2_grpc.py"):
            leaked.append(entry.name)
    assert not leaked, (
        f"Stage 28.10 must not introduce generated protobuf "
        f"stubs under PHX2/stage28/; offenders: {leaked!r}"
    )


# ---------------------------------------------------------------------------
# URL host / raw-secret literal scan
# ---------------------------------------------------------------------------


_FORBIDDEN_URL_HOST_SUBSTRINGS: tuple[str, ...] = (
    "discord" + ".com",
    "discord" + "app.com",
    "hooks" + ".slack.com",
    "api.helius" + ".xyz",
    "rpc.helius" + ".xyz",
    "mainnet.helius" + ".rpc.com",
    "public-api.birdeye" + ".so",
    "birdeye" + ".so/v1",
    "t" + ".me/",
    "api.twitter" + ".com",
    "api.x" + ".com",
    "chainstack" + ".com/",
    "yellowstone" + ".chainstack",
)


def test_no_url_host_literal_in_stage_28_10_production_source():
    for path in _iter_stage28_10_production_py_files():
        source = _read(path)
        for needle in _FORBIDDEN_URL_HOST_SUBSTRINGS:
            assert needle not in source, (
                f"{path}: forbidden URL host literal {needle!r}"
            )


_FORBIDDEN_RAW_SECRET_LITERAL_NEEDLES: tuple[str, ...] = (
    "B" + "earer ",
    "A" + "uthorization:",
    "x-a" + "pi-key",
    "X-A" + "pi-Key",
    "s" + "k-",
    "p" + "k-",
    "DISCORD_WEBHOOK" + "_URL=",
    "HELIUS_API" + "_KEY=",
    "HELIUS_RPC" + "_URL=",
    "HELIUS_GRPC" + "_ENDPOINT=",
    "CHAINSTACK_API" + "_KEY=",
    "CHAINSTACK_XTOKEN" + "=",
    "CHAINSTACK_USERNAME" + "=",
    "CHAINSTACK_PASSWORD" + "=",
)


def test_no_raw_secret_literal_in_stage_28_10_production_source():
    for path in _iter_stage28_10_production_py_files():
        source = _read(path)
        for needle in _FORBIDDEN_RAW_SECRET_LITERAL_NEEDLES:
            assert needle not in source, (
                f"{path}: forbidden raw-secret-looking literal "
                f"{needle!r}"
            )


# ---------------------------------------------------------------------------
# Forbidden enforcement / public-routing / trading / wallet / daemon
# identifier scan
# ---------------------------------------------------------------------------


_FORBIDDEN_LATER_SUBSTAGE_OR_PUBLIC_SUBSTRINGS: tuple[str, ...] = (
    "public" + "_router",
    "subscriber" + "_router",
    "paid" + "_tier_router",
    "live" + "_router",
    "telegram" + "_sender",
    "telegram" + "_client",
    "x" + "_social",
    "social" + "_sidecar",
    "tweet" + "_ranking",
    "enforcement" + "_gate",
    "enforce" + "_policy",
    "approval" + "_gate",
    "approval" + "_status",
    "enforcement" + "_result",
    "auto" + "_trade",
    "position" + "_size",
    "trade" + "_executor",
    "wallet" + "_signer",
    "private" + "_key_loader",
    "buy" + "_signal",
    "sell" + "_signal",
    "execute" + "_trade",
    "control" + "_server",
    "http" + "_control_server",
    "auto" + "restart",
    "systemd" + "_unit",
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


def test_no_stage_28_10_production_identifier_implements_later_or_public_surface():
    for path in _iter_stage28_10_production_py_files():
        idents = _extract_all_identifiers(_read(path))
        for ident in idents:
            lower = ident.lower()
            for needle in (
                _FORBIDDEN_LATER_SUBSTAGE_OR_PUBLIC_SUBSTRINGS
            ):
                assert needle not in lower, (
                    f"{path}: identifier {ident!r} contains "
                    f"forbidden later-substage or public-"
                    f"routing substring {needle!r}"
                )


# ---------------------------------------------------------------------------
# Stage 21-27 production trees not touched
# ---------------------------------------------------------------------------


def test_no_prior_stage_production_tree_carries_stage_28_10_basename():
    leaked: list[str] = []
    for stage_dir_name in (
        "stage21",
        "stage22",
        "stage23",
        "stage24",
        "stage25",
        "stage26",
        "stage27",
    ):
        root = PHX2_ROOT / stage_dir_name
        if not root.exists():
            continue
        for entry in root.iterdir():
            if not entry.is_file():
                continue
            if entry.name in (
                _STAGE_28_10_PRODUCTION_PY_BASENAMES
            ):
                leaked.append(
                    f"{stage_dir_name}/{entry.name}"
                )
            if entry.name in _STAGE_28_10_DOC_BASENAMES:
                leaked.append(
                    f"{stage_dir_name}/{entry.name}"
                )
    assert not leaked, (
        f"Stage 28.10 basename leaked into a prior stage tree: "
        f"{leaked!r}"
    )


# ---------------------------------------------------------------------------
# No top-level Call / no top-level write
# ---------------------------------------------------------------------------


def _has_top_level_call(source: str) -> bool:
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, ast.Expr) and isinstance(
            node.value, ast.Call,
        ):
            return True
    return False


def test_no_stage_28_10_production_has_top_level_call():
    for path in _iter_stage28_10_production_py_files():
        assert not _has_top_level_call(_read(path)), (
            f"{path}: Stage 28.10 production .py modules must "
            f"contain no top-level Call (no implicit I/O at "
            f"import time)"
        )


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


def _module_calls_top_level_filesystem(
    source: str,
) -> list[str]:
    tree = ast.parse(source)
    offenders: list[str] = []
    for node in tree.body:
        if isinstance(node, ast.Expr) and isinstance(
            node.value, ast.Call,
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


def test_no_stage_28_10_production_writes_at_module_top_level():
    for path in _iter_stage28_10_production_py_files():
        offenders = _module_calls_top_level_filesystem(
            _read(path),
        )
        assert not offenders, (
            f"{path}: Stage 28.10 production .py must not call "
            f"filesystem write helpers at module top level; "
            f"offenders: {offenders!r}"
        )


# ---------------------------------------------------------------------------
# No sleep / async / scheduling calls
# ---------------------------------------------------------------------------


_FORBIDDEN_RUNTIME_CALL_ATTRS: frozenset[str] = frozenset(
    {
        "sleep",
        "wait",
        "spawn",
        "schedule",
        "create_task",
        "run_until_complete",
        "start_thread",
    }
)


def test_no_stage_28_10_production_calls_sleep_or_schedule_helpers():
    for path in _iter_stage28_10_production_py_files():
        tree = ast.parse(_read(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Attribute):
                    assert (
                        func.attr
                        not in _FORBIDDEN_RUNTIME_CALL_ATTRS
                    ), (
                        f"{path}: Stage 28.10 production .py "
                        f"must not call .{func.attr}()"
                    )
                elif isinstance(func, ast.Name):
                    assert (
                        func.id
                        not in _FORBIDDEN_RUNTIME_CALL_ATTRS
                    ), (
                        f"{path}: Stage 28.10 production .py "
                        f"must not call {func.id}()"
                    )


# ---------------------------------------------------------------------------
# No dependency-install commands embedded in production / docs
# ---------------------------------------------------------------------------


_FORBIDDEN_DEPENDENCY_INSTALL_TOKENS: tuple[str, ...] = (
    "pip install",
    "pip3 install",
    "poetry add",
    "uv add",
    "uv pip install",
    "conda install",
    "easy_install ",
)


def test_no_stage_28_10_production_carries_dependency_install_command():
    for path in _iter_stage28_10_production_py_files():
        source = _read(path)
        for token in _FORBIDDEN_DEPENDENCY_INSTALL_TOKENS:
            assert token not in source, (
                f"{path}: Stage 28.10 production must not embed "
                f"dependency install token {token!r}"
            )


# ---------------------------------------------------------------------------
# Stage 28.10 manifest declares the locked basename inventories
# ---------------------------------------------------------------------------


def test_manifest_declares_locked_production_py_basenames():
    from PHX2.stage28.stage28_10_manifest import (
        STAGE28_10_PRODUCTION_PY_BASENAMES,
    )

    assert (
        set(STAGE28_10_PRODUCTION_PY_BASENAMES)
        == set(_STAGE_28_10_PRODUCTION_PY_BASENAMES)
    )


def test_manifest_declares_locked_doc_basenames():
    from PHX2.stage28.stage28_10_manifest import (
        STAGE28_10_DOC_BASENAMES,
    )

    assert (
        set(STAGE28_10_DOC_BASENAMES)
        == set(_STAGE_28_10_DOC_BASENAMES)
    )


def test_manifest_declares_locked_test_basenames():
    from PHX2.stage28.stage28_10_manifest import (
        STAGE28_10_TEST_BASENAMES,
    )

    assert (
        set(STAGE28_10_TEST_BASENAMES)
        == set(_STAGE_28_10_TEST_BASENAMES)
    )


def test_manifest_minor_version_is_28_10():
    from PHX2.stage28.stage28_10_manifest import (
        STAGE28_10_MINOR_VERSION,
    )

    assert STAGE28_10_MINOR_VERSION == "28.10"


def test_manifest_schema_version_is_locked():
    from PHX2.stage28.stage28_10_manifest import (
        STAGE28_10_SCHEMA_VERSION,
    )

    assert (
        STAGE28_10_SCHEMA_VERSION
        == "stage28_10_chainstack_yellowstone_v0"
    )


def test_manifest_bridge_basename_is_locked():
    from PHX2.stage28.stage28_10_manifest import (
        STAGE28_10_STAGE_21_27_BRIDGE_BASENAME,
    )

    assert (
        STAGE28_10_STAGE_21_27_BRIDGE_BASENAME
        == _STAGE_28_10_BRIDGE_BASENAME
    )


def test_manifest_scope_locks_pin_stage_28_10_exclusions():
    from PHX2.stage28.stage28_10_manifest import (
        STAGE28_10_SCOPE_LOCKS,
    )

    required_phrases = {
        "Chainstack Yellowstone provider boundary scope",
        "protocol + fake + models surface only",
        "no real provider client in this stage",
        "no grpc / grpcio / protobuf imports",
        "no generated pb2 / pb2_grpc stubs",
        "no real Chainstack call",
        "no real Discord send",
        "no Stage 29 enforcement",
        "no enforcement gate",
        "no public routing",
        "no subscriber routing",
        "no paid tier routing",
        "no Telegram",
        "no X / social",
        "no automated trading",
        "no wallet / private-key / signer logic",
        "no position sizing",
        "no trade execution",
        "no dashboard / HTTP control server",
        (
            "no daemon / systemd / watchdog / autorestart "
            "service"
        ),
        "no Stage 28 closure tag movement",
        "no env reads",
        "no sleep / no scheduling / no backoff execution",
        "fake / protocol tests only",
        "pair-hint-aware candidate assembly requirement",
        (
            "Stage 21 / Stage 27 imports allowed in candidate "
            "assembler module only"
        ),
        (
            "price must be injected via Stage 27.6 sources; "
            "never faked in production"
        ),
        (
            "missing or stale price suppresses via existing "
            "Stage 27 / Stage 28.6 rules"
        ),
        "redaction-safe records",
    }
    assert required_phrases.issubset(
        set(STAGE28_10_SCOPE_LOCKS)
    )


def test_manifest_forbidden_surfaces_pin_stage_28_10_exclusions():
    from PHX2.stage28.stage28_10_manifest import (
        STAGE28_10_FORBIDDEN_SURFACES,
    )

    required = {
        "Stage 29 implementation",
        "enforcement",
        "public routing",
        "subscriber routing",
        "paid tiers",
        "Telegram",
        "X / social",
        "automated trading",
        "wallet / private-key / signer logic",
        "position sizing",
        "trade execution",
        "dashboard / HTTP control server",
        "daemon / systemd / watchdog / autorestart service",
        "grpc / grpcio / protobuf imports",
        "generated pb2 / pb2_grpc stubs",
        "real provider network calls",
        "real Discord send",
    }
    assert required.issubset(set(STAGE28_10_FORBIDDEN_SURFACES))


# ---------------------------------------------------------------------------
# Stage 28 root admits the Stage 28.10 surface (sanity scan; the
# absolute "exactly this set" admission lives in
# ``test_stage_28_6_boundaries.py`` and
# ``test_stage_28_7_boundaries.py``)
# ---------------------------------------------------------------------------


def test_stage28_root_admits_stage_28_10_files():
    actual: set[str] = set()
    for entry in STAGE28_ROOT.iterdir():
        if entry.is_dir() and entry.name == "__pycache__":
            continue
        actual.add(entry.name)
    for basename in _STAGE_28_10_PRODUCTION_PY_BASENAMES:
        assert basename in actual, (
            f"PHX2/stage28 must contain Stage 28.10 production "
            f"basename {basename!r}"
        )
    for basename in _STAGE_28_10_DOC_BASENAMES:
        assert basename in actual, (
            f"PHX2/stage28 must contain Stage 28.10 doc "
            f"basename {basename!r}"
        )


def test_tests_stage28_root_admits_stage_28_10_tests():
    actual: set[str] = set()
    for entry in TESTS_STAGE28_ROOT.iterdir():
        if entry.is_dir() and entry.name == "__pycache__":
            continue
        actual.add(entry.name)
    for basename in _STAGE_28_10_TEST_BASENAMES:
        assert basename in actual, (
            f"PHX2/tests/stage28 must contain Stage 28.10 test "
            f"basename {basename!r}"
        )

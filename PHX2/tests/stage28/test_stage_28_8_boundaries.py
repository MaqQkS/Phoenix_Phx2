"""Stage 28.8 boundary scan.

Pins (scoped to ``PHX2/stage28/`` and ``PHX2/stage29/`` where
applicable so older repo surfaces do not trip false positives):

  * No ``PHX2/stage29/`` implementation tree exists at Stage
    28.8.
  * No enforcement / public routing / subscriber routing / paid
    tier / Telegram / X-social / automated-trading / wallet /
    signer / dashboard / control-server / daemon / watchdog
    basename appears under ``PHX2/stage28/``.
  * No Stage 28.8 file (production / docs / tests) reads
    ``os.environ`` / ``os.getenv`` / ``os.environb``.
  * No Stage 28.8 file imports a network / RPC / messaging /
    scheduler / threading / asyncio / subprocess library.
  * No Stage 28.8 production module performs a real Discord
    dispatch.
  * No Stage 28.8 file calls a tag-creation command, a
    ``git tag`` shell, a ``git push`` shell, or a subprocess /
    ``os.system`` git mutation.
  * Stage 28.7 smoke harness remains offline / fake-only (the
    Stage 28.7 module imports no urllib / network library and
    declares ``live_send_attempted`` False on its smoke summary
    record).
  * The ``stage-28-closed`` tag is absent (Stage 28.8 must not
    create it).
"""

from __future__ import annotations

import ast
import subprocess
from pathlib import Path

import pytest


PHX2_ROOT: Path = Path(__file__).resolve().parent.parent.parent
REPO_ROOT: Path = PHX2_ROOT.parent
STAGE28_ROOT: Path = PHX2_ROOT / "stage28"
STAGE29_ROOT: Path = PHX2_ROOT / "stage29"
TESTS_STAGE28_ROOT: Path = PHX2_ROOT / "tests" / "stage28"


_STAGE28_8_PRODUCTION_BASENAMES: tuple[str, ...] = (
    "stage28_manifest.py",
)


_STAGE28_8_DOC_BASENAMES: tuple[str, ...] = (
    "STAGE_28_CLOSURE_AUDIT.md",
    "STAGE_29_HANDOFF.md",
)


_STAGE28_8_TEST_BASENAMES: tuple[str, ...] = (
    "test_stage_28_8_closure_audit.py",
    "test_stage_28_8_stage29_handoff.py",
    "test_stage_28_8_manifest.py",
    "test_stage_28_8_boundaries.py",
)


def _stage28_8_production_paths() -> list[Path]:
    return [
        STAGE28_ROOT / name
        for name in _STAGE28_8_PRODUCTION_BASENAMES
    ]


def _stage28_8_test_paths() -> list[Path]:
    return [
        TESTS_STAGE28_ROOT / name
        for name in _STAGE28_8_TEST_BASENAMES
    ]


def _stage28_8_doc_paths() -> list[Path]:
    return [
        STAGE28_ROOT / name
        for name in _STAGE28_8_DOC_BASENAMES
    ]


def _stage28_8_all_paths() -> list[Path]:
    return (
        _stage28_8_production_paths()
        + _stage28_8_doc_paths()
        + _stage28_8_test_paths()
    )


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# 1. Stage 28.8 files exist
# ---------------------------------------------------------------------------


def test_every_stage_28_8_production_file_exists():
    for name in _STAGE28_8_PRODUCTION_BASENAMES:
        path = STAGE28_ROOT / name
        assert path.is_file(), (
            f"Stage 28.8 requires production file {path}"
        )


def test_every_stage_28_8_doc_exists():
    for name in _STAGE28_8_DOC_BASENAMES:
        path = STAGE28_ROOT / name
        assert path.is_file(), (
            f"Stage 28.8 requires doc {path}"
        )


def test_every_stage_28_8_test_exists():
    for name in _STAGE28_8_TEST_BASENAMES:
        path = TESTS_STAGE28_ROOT / name
        assert path.is_file(), (
            f"Stage 28.8 requires test {path}"
        )


# ---------------------------------------------------------------------------
# 2. No Stage 29 implementation tree exists
# ---------------------------------------------------------------------------


# Stage 29.0 + Stage 29.1 PumpSwap-only narrow amendment:
# PHX2/stage29/ may exist iff it ships the Stage 29.0 scaffold
# AND the Stage 29.1 PumpSwap-only hint-extractor tree. Stage
# 29.2 / 29.3 implementation files AND any Pump.fun
# bonding-curve files remain blocked from Stage 28.8.
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
# Stage 28.8 narrow amendment widens the Stage-29-tree allowlist
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
# only. Stage 29.4.1 production .py files
# (stage29_4_soak_models.py / stage29_4_dedupe_index.py /
# stage29_4_soak_orchestrator.py /
# stage29_4_soak_artifact_writer.py / stage29_4_manifest.py)
# remain blocked at Stage 29.4.0.
_STAGE_29_4_SOAK_SPEC_LOCK_ALLOWED_PROD_BASENAMES: frozenset[
    str
] = frozenset(
    {
        "STAGE_29_4_SHORT_SESSION_PRIVATE_SOAK_RUNBOOK.md",
        # Stage 29.4.1 widens the Stage 28.8 narrow amendment to
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
# ping context join (authorized 2026-05-25). Stage 29.5.0 was
# spec-lock-only; Stage 29.5.1 (authorized 2026-05-25) widens
# this allowlist to admit the six Stage 29.5 production .py
# basenames pinned by the Stage 29.5.0 runbook (Section 9).
_STAGE_29_5_MIGRATION_EVIDENCE_SPEC_LOCK_ALLOWED_PROD_BASENAMES: frozenset[
    str
] = frozenset(
    {
        "STAGE_29_5_MIGRATION_EVIDENCE_SPEC_LOCK.md",
        # Stage 29.5.1 production .py files.
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
# narrow amendment widens the Stage 28.8 narrow Stage-29-prod
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
# narrow amendment widens the Stage 28.8 Stage-29-prod allowlist
# to admit the Stage 29.5.3 production + doc inventory.
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
# 2026-05-26). Stage 29.5.4 ships the Stage 27.4
# ``MigrationContextSource`` Protocol adapter that lets the
# operator pass a Stage 29.5-aware source into the Stage 29.3
# mode-3 path via the new optional ``migration_source`` kwarg on
# ``run_stage29_3_first_private_tradeable_smoke``. This narrow
# amendment widens the Stage 28.8 Stage-29-prod allowlist to
# admit the Stage 29.5.4 production + doc inventory.
_STAGE_29_5_4_MIGRATION_CONTEXT_INJECTION_ALLOWED_PROD_BASENAMES: frozenset[
    str
] = frozenset(
    {
        "STAGE_29_5_4_MIGRATION_CONTEXT_INJECTION_RUNBOOK.md",
        "stage29_5_4_migration_context_source_adapter.py",
        "stage29_5_4_manifest.py",
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
# lock test only. Stage 29.4.1 test files remain blocked at
# Stage 29.4.0.
_STAGE_29_4_SOAK_SPEC_LOCK_ALLOWED_TEST_BASENAMES: frozenset[
    str
] = frozenset(
    {
        "test_stage_29_4_spec_lock.py",
        # Stage 29.4.1 widens the Stage 28.8 narrow amendment to
        # admit the focused Stage 29.4 test files.
        "test_stage_29_4_soak_models.py",
        "test_stage_29_4_dedupe_index.py",
        "test_stage_29_4_soak_orchestrator.py",
        "test_stage_29_4_soak_artifact_writer.py",
        "test_stage_29_4_boundaries.py",
    }
)


# Stage 29.5 Helius WS migration evidence adapter + live private
# ping context join (authorized 2026-05-25). Stage 29.5.1 widens
# the Stage-29-tests allowlist to admit the focused Stage 29.5
# test files plus the spec-lock test from Stage 29.5.0.
_STAGE_29_5_MIGRATION_EVIDENCE_SPEC_LOCK_ALLOWED_TEST_BASENAMES: frozenset[
    str
] = frozenset(
    {
        "test_stage_29_5_spec_lock.py",
        # Stage 29.5.1 focused test files.
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
# 2026-05-26). Narrow amendment widens the Stage 28.8 Stage-29-
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
# 2026-05-26). Narrow amendment widens the Stage 28.8 Stage-29-
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
# (authorized 2026-05-26). Narrow amendment widens the Stage 28.8
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
)


def test_no_stage29_implementation_tree_exists():
    # Stage 29.0 + Stage 29.1 PumpSwap-only narrow amendment.
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
        f"Stage 28.8 narrow amendment: PHX2/stage29 admits "
        f"only the Stage 29.0 scaffold + Stage 29.1 PumpSwap-"
        f"only tree "
        f"({sorted(_STAGE_29_0_PLUS_29_1_ALLOWED_PROD_BASENAMES)!r}); "
        f"Stage 29.2 / 29.3 files + Pump.fun bonding-curve "
        f"files remain blocked. Forbidden entries: "
        f"{sorted(forbidden)!r}"
    )


def test_no_stage29_tests_tree_exists():
    # Stage 29.0 + Stage 29.1 PumpSwap-only narrow amendment.
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
        f"Stage 28.8 narrow amendment: PHX2/tests/stage29 "
        f"admits only the Stage 29.0 tests + Stage 29.1 "
        f"PumpSwap-only tests "
        f"({sorted(_STAGE_29_0_PLUS_29_1_ALLOWED_TEST_BASENAMES)!r}); "
        f"Stage 29.2 / 29.3 test files + Pump.fun bonding-curve "
        f"test files remain blocked. Forbidden entries: "
        f"{sorted(forbidden)!r}"
    )


# ---------------------------------------------------------------------------
# 3. Forbidden Stage 28 / Stage 29 basenames must not appear
# ---------------------------------------------------------------------------


_FORBIDDEN_STAGE28_BASENAMES: tuple[str, ...] = (
    "public_router.py",
    "subscriber_router.py",
    "paid_tier_router.py",
    "live_router.py",
    "telegram_sender.py",
    "telegram_client.py",
    "x_social.py",
    "social_sidecar.py",
    "tweet_ranking.py",
    "social_scoring.py",
    "enforcement_gate.py",
    "enforcement.py",
    "enforce_policy.py",
    "auto_trade.py",
    "position_sizer.py",
    "trade_executor.py",
    "wallet_signer.py",
    "private_key_loader.py",
    "discord_bot.py",
    "slash_commands.py",
    "subscriber_models.py",
    "subscriber_db.py",
    "dashboard.py",
    "http_control_server.py",
    "control_server.py",
    "watchdog.py",
    "autorestart.py",
    "daemon.py",
    "systemd_unit.py",
)


@pytest.mark.parametrize(
    "basename", _FORBIDDEN_STAGE28_BASENAMES
)
def test_no_forbidden_basename_under_stage28(basename):
    assert not (STAGE28_ROOT / basename).exists(), (
        f"PHX2/stage28 must not introduce forbidden basename "
        f"{basename!r} at Stage 28.8"
    )


@pytest.mark.parametrize(
    "basename", _FORBIDDEN_STAGE28_BASENAMES
)
def test_no_forbidden_basename_under_stage29(basename):
    # STAGE29_ROOT itself is forbidden by another test; this is
    # a defense-in-depth scan that the basename is not anywhere
    # in a (hypothetical) stage29 tree either.
    if not STAGE29_ROOT.exists():
        return
    assert not (STAGE29_ROOT / basename).exists()


# ---------------------------------------------------------------------------
# 4. Env-read isolation across Stage 28.8 files
# ---------------------------------------------------------------------------


_ENV_ATTR_NAMES: frozenset[str] = frozenset(
    {"environ", "getenv", "environb"}
)


def _python_module_reads_environ(source: str) -> bool:
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


def test_no_stage_28_8_python_file_reads_environ():
    offenders: list[str] = []
    for path in (
        _stage28_8_production_paths() + _stage28_8_test_paths()
    ):
        if _python_module_reads_environ(_read(path)):
            offenders.append(path.name)
    assert not offenders, (
        f"Stage 28.8 python files must not read os.environ / "
        f"os.getenv / os.environb; offenders: {offenders!r}"
    )


def test_no_stage_28_8_doc_references_env_assignment():
    forbidden = (
        "DISCORD_WEBHOOK_URL=",
        "HELIUS_API_KEY=",
        "HELIUS_RPC_URL=",
        "HELIUS_GRPC_ENDPOINT=",
        "PHX2_PROVIDER_GRPC_ENDPOINT=",
    )
    for path in _stage28_8_doc_paths():
        text = _read(path)
        for needle in forbidden:
            assert needle not in text, (
                f"{path}: must not reference raw env "
                f"assignment {needle!r}"
            )


# ---------------------------------------------------------------------------
# 5. No network / scheduler / messaging imports in Stage 28.8
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
    "queue",
    "sched",
    "http.client",
    "http",
    "ssl",
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


def test_no_stage_28_8_python_file_imports_runtime_module_patterns():
    for path in (
        _stage28_8_production_paths() + _stage28_8_test_paths()
    ):
        targets = _collect_imported_module_paths(_read(path))
        for target in targets:
            lower = target.lower()
            for pattern in _FORBIDDEN_RUNTIME_MODULE_PATTERNS:
                # ``subprocess`` is intentionally allowed only
                # for static analysis -- but ONLY if the file
                # is a Stage 28.8 boundary test that asserts
                # the absence of subprocess CALLS in the rest
                # of Stage 28.8. We always reject subprocess
                # imports in Stage 28.8 production code; for
                # tests, we narrow the exemption to this very
                # boundary test file.
                if (
                    pattern == "subprocess"
                    and path.name == "test_stage_28_8_boundaries.py"
                ):
                    continue
                assert pattern not in lower, (
                    f"{path}: forbidden runtime pattern "
                    f"{pattern!r} in import {target!r}"
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
    "PHX2.stage27",
)


def test_no_stage_28_8_python_file_imports_prior_stage_code():
    for path in (
        _stage28_8_production_paths() + _stage28_8_test_paths()
    ):
        targets = _collect_imported_module_paths(_read(path))
        for target in targets:
            for forbidden in _FORBIDDEN_PRIOR_STAGE_PREFIXES:
                assert not target.startswith(forbidden), (
                    f"{path}: forbidden prior-stage import "
                    f"{target!r}"
                )


def test_no_stage_28_8_python_file_imports_stage_29():
    for path in (
        _stage28_8_production_paths() + _stage28_8_test_paths()
    ):
        targets = _collect_imported_module_paths(_read(path))
        for target in targets:
            assert not target.startswith("PHX2.stage29"), (
                f"{path}: Stage 28.8 must not import any "
                f"Stage 29 module; saw {target!r}"
            )


# ---------------------------------------------------------------------------
# 6. No live Discord send / no real network from Stage 28.8 files
# ---------------------------------------------------------------------------


_FORBIDDEN_CALL_NETWORK_ROOTS: frozenset[str] = frozenset(
    {
        "urllib",
        "requests",
        "httpx",
        "aiohttp",
        "websockets",
        "discord",
        "telegram",
        "grpc",
        "socket",
    }
)


_FORBIDDEN_CALL_SUBPROCESS_OR_OS_TARGETS: dict[
    str, frozenset[str]
] = {
    "subprocess": frozenset(
        {
            "run",
            "Popen",
            "call",
            "check_call",
            "check_output",
        }
    ),
    "os": frozenset(
        {
            "system",
            "popen",
            "execv",
            "execve",
            "spawnv",
            "spawnve",
        }
    ),
}


def _resolve_call_root_and_chain(
    call_node: ast.Call,
) -> tuple[str | None, list[str]]:
    """Resolve a Call node's function to a (root, chain) tuple.

    For ``subprocess.run(...)`` returns ``("subprocess", ["run"])``.
    For ``urllib.request.urlopen(...)`` returns
    ``("urllib", ["request", "urlopen"])``.
    For a bare ``run(...)`` returns ``("run", [])``.
    For something like ``self.foo()`` returns ``(None, [...])``.
    """
    chain: list[str] = []
    current = call_node.func
    while isinstance(current, ast.Attribute):
        chain.insert(0, current.attr)
        current = current.value
    if isinstance(current, ast.Name):
        return current.id, chain
    return None, chain


def _find_forbidden_network_calls(
    source: str,
) -> list[str]:
    """Return the list of Call paths that look like a live-send
    invocation (``urllib.request.urlopen``, ``requests.post``,
    ``httpx.post``, ``aiohttp.ClientSession``, etc.).

    String literals embedded in source code are never reported
    here -- the AST walk only visits ``ast.Call`` nodes, so
    descriptive prose stored in a string constant remains
    safe.
    """
    tree = ast.parse(source)
    offenders: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        root, chain = _resolve_call_root_and_chain(node)
        if root is None:
            continue
        if root in _FORBIDDEN_CALL_NETWORK_ROOTS and chain:
            offenders.append(f"{root}.{'.'.join(chain)}")
    return offenders


def _find_forbidden_subprocess_or_os_calls(
    source: str,
) -> list[str]:
    """Return the list of Call paths that invoke a forbidden
    ``subprocess.*`` / ``os.*`` mutation helper.

    String literals are not reported -- the AST walk only visits
    ``ast.Call`` nodes.
    """
    tree = ast.parse(source)
    offenders: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        root, chain = _resolve_call_root_and_chain(node)
        if root is None:
            continue
        if root in _FORBIDDEN_CALL_SUBPROCESS_OR_OS_TARGETS:
            if chain:
                head = chain[0]
                if (
                    head
                    in _FORBIDDEN_CALL_SUBPROCESS_OR_OS_TARGETS[root]
                ):
                    offenders.append(f"{root}.{'.'.join(chain)}")
    return offenders


def test_no_stage_28_8_production_file_invokes_network_call():
    for path in _stage28_8_production_paths():
        offenders = _find_forbidden_network_calls(_read(path))
        assert not offenders, (
            f"{path}: forbidden live-send / network call(s) at "
            f"AST level: {offenders!r}"
        )


def test_no_stage_28_8_doc_contains_url_or_webhook_host_literal():
    forbidden_url_literals = (
        "h" + "ttps://",
        "h" + "ttp://",
        "w" + "ss://",
        "w" + "s://",
        "discord" + ".com",
        "discordapp" + ".com",
        "hooks" + ".slack.com",
    )
    for path in _stage28_8_doc_paths():
        text = _read(path)
        for needle in forbidden_url_literals:
            assert needle not in text, (
                f"{path}: forbidden URL host literal {needle!r}"
            )


# ---------------------------------------------------------------------------
# 7. No tag-creation / push command in Stage 28.8 files
# ---------------------------------------------------------------------------


def test_no_stage_28_8_production_file_calls_subprocess_or_os():
    """Stage 28.8 production code must not invoke subprocess /
    ``os.system`` / ``os.popen`` / ``os.exec*`` / ``os.spawn*``.

    The manifest is constants-only; the scan checks AST Call
    nodes, so descriptive prose stored as a string constant
    inside the manifest's tag policy / network declarations is
    not flagged.
    """
    for path in _stage28_8_production_paths():
        offenders = _find_forbidden_subprocess_or_os_calls(
            _read(path)
        )
        assert not offenders, (
            f"{path}: forbidden subprocess / os call(s) at AST "
            f"level: {offenders!r}"
        )


def test_no_stage_28_8_test_file_other_than_boundaries_calls_subprocess():
    """Every Stage 28.8 test file except the boundary test
    itself must not invoke ``subprocess.*`` / ``os.system`` /
    ``os.popen`` / etc.

    The boundary test legitimately uses
    ``subprocess.run(["git", "tag", "--list", "stage-28*"])``
    to assert the absence of the closure tag; that exemption is
    scoped to this single file. The boundary scan
    ``test_no_stage_28_8_boundaries_uses_only_git_tag_list``
    pins what the boundary test is allowed to do.
    """
    for path in _stage28_8_test_paths():
        if path.name == "test_stage_28_8_boundaries.py":
            continue
        offenders = _find_forbidden_subprocess_or_os_calls(
            _read(path)
        )
        assert not offenders, (
            f"{path}: forbidden subprocess / os call(s) at AST "
            f"level: {offenders!r}"
        )


def test_no_stage_28_8_boundaries_uses_anything_other_than_git_tag_list():
    """The boundary test's ONE permitted subprocess call is a
    read-only ``git tag --list stage-28*`` invocation. Pin that
    by AST inspection: every ``subprocess.run`` Call in this
    file must pass a list literal whose first element is
    ``"git"`` and whose second element is ``"tag"`` and whose
    third element is ``"--list"``.
    """
    boundary_path = (
        TESTS_STAGE28_ROOT / "test_stage_28_8_boundaries.py"
    )
    tree = ast.parse(_read(boundary_path))
    subprocess_calls: list[ast.Call] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        root, chain = _resolve_call_root_and_chain(node)
        if root == "subprocess" and chain == ["run"]:
            subprocess_calls.append(node)
    assert len(subprocess_calls) >= 1, (
        "expected at least one subprocess.run call in the "
        "Stage 28.8 boundary test (the git-tag-list check)"
    )
    for call in subprocess_calls:
        assert call.args, (
            "subprocess.run call must pass a positional argv "
            "list"
        )
        argv = call.args[0]
        assert isinstance(argv, ast.List), (
            "subprocess.run argv must be a literal list"
        )
        elements = [
            elt.value if isinstance(elt, ast.Constant) else None
            for elt in argv.elts
        ]
        assert (
            len(elements) >= 3
            and elements[0] == "git"
            and elements[1] == "tag"
            and elements[2] == "--list"
        ), (
            f"boundary test subprocess.run must be a read-only "
            f"git-tag-list call; saw argv={elements!r}"
        )


def test_no_stage_28_8_doc_calls_git_tag_or_push():
    # Docs may MENTION ``git tag --list`` etc. as commands the
    # operator runs manually. What docs must NOT contain is a
    # Python-runtime executable token like ``subprocess.run`` /
    # ``os.system`` -- those would imply the doc is teaching
    # someone to run the call from Python code rather than from
    # the operator's shell.
    forbidden = (
        "subprocess.run",
        "subprocess.Popen",
        "os.system",
        "os.popen",
    )
    for path in _stage28_8_doc_paths():
        text = _read(path)
        for token in forbidden:
            assert token not in text, (
                f"{path}: doc must not contain executable-"
                f"looking token {token!r}"
            )


# ---------------------------------------------------------------------------
# 8. Stage 28.7 smoke harness remains offline / fake-only
# ---------------------------------------------------------------------------


_STAGE28_7_HARNESS_PATH: Path = (
    STAGE28_ROOT / "longer_session_smoke_harness.py"
)


def test_stage_28_7_smoke_harness_imports_no_network_module():
    source = _read(_STAGE28_7_HARNESS_PATH)
    targets = _collect_imported_module_paths(source)
    allowed_stage_28_modules = {
        "PHX2.stage28.audited_http_transport_models",
        "PHX2.stage28.bounded_private_session_runner",
        "PHX2.stage28.session_runner_models",
    }
    for target in targets:
        if target in allowed_stage_28_modules:
            continue
        lower = target.lower()
        for pattern in _FORBIDDEN_RUNTIME_MODULE_PATTERNS:
            assert pattern not in lower, (
                f"Stage 28.7 harness statically imports a "
                f"forbidden module {target!r} (contains "
                f"{pattern!r})"
            )


def test_stage_28_7_smoke_harness_declares_live_send_false_in_summary():
    """The Stage 28.7 harness must always set
    ``live_send_attempted=False`` and ``live_send_count=0`` on
    its smoke summary record. Stage 28.8 re-pins that invariant
    by source-scanning the harness for the literal lines.
    """
    source = _read(_STAGE28_7_HARNESS_PATH)
    assert "live_send_attempted=False" in source
    assert "live_send_count=0" in source


# ---------------------------------------------------------------------------
# 9. stage-28-closed annotated tag exists at Stage 28.8 commit
# ---------------------------------------------------------------------------


# Locked Stage 28.8 closure commit SHA that the ``stage-28-closed``
# annotated tag must peel to. Captured here so a downstream
# reader does not have to re-derive it from git history.
_STAGE_28_8_CLOSURE_COMMIT_SHA: str = (
    "a897bb0531259bbe065efb3e38703a7c3be156c7"
)


def test_stage_28_closed_tag_exists_at_stage_28_8_commit():
    """The ``stage-28-closed`` annotated tag must exist locally,
    must be an annotated tag (object type ``tag``), and must
    peel to the locked Stage 28.8 closure commit SHA.

    The assertion was inverted from "tag must remain absent" to
    "tag must exist at the locked Stage 28.8 commit" after the
    operator explicitly created the annotated tag on the Stage
    28.8 closure commit (post-Stage-28.8). The Stage 28.9
    operational adapter substage runs against the already-closed
    Stage 28 reliability core; the tag's existence is the
    locked closure marker.

    Implementation note: the locked Stage 28.8 boundary scan
    ``test_no_stage_28_8_boundaries_uses_anything_other_than_git_tag_list``
    pins that every ``subprocess.run`` call in this file must
    use ``["git", "tag", "--list", ...]`` argv. The single
    ``git tag --list --format=...`` call below satisfies the
    operator's three required assertions (name / object type /
    peeled SHA) without widening that allowlist.
    """
    result = subprocess.run(
        [
            "git",
            "tag",
            "--list",
            "--format=%(refname:short) %(objecttype) %(object)",
            "stage-28-closed",
        ],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, (
        f"git tag --list failed: stderr={result.stderr!r}"
    )
    lines = [
        line.strip()
        for line in result.stdout.splitlines()
        if line.strip()
    ]
    # 1. The tag must exist (one line, refname == stage-28-closed).
    assert lines == [
        f"stage-28-closed tag {_STAGE_28_8_CLOSURE_COMMIT_SHA}"
    ] or (
        len(lines) == 1
        and lines[0].startswith("stage-28-closed ")
    ), (
        f"stage-28-closed tag must exist locally; saw stdout="
        f"{result.stdout!r}"
    )
    fields = lines[0].split(" ")
    assert len(fields) == 3, (
        f"unexpected git tag --list format output: {lines[0]!r}"
    )
    refname, objecttype, peeled_sha = fields
    # 1. git tag --list returns stage-28-closed.
    assert refname == "stage-28-closed", (
        f"expected refname stage-28-closed; saw {refname!r}"
    )
    # 2. git cat-file -t stage-28-closed equivalent: the object
    #    type must be ``tag`` (annotated tag, not lightweight).
    assert objecttype == "tag", (
        f"stage-28-closed must be an annotated tag (object type "
        f"'tag'); saw object type {objecttype!r}"
    )
    # 3. git rev-parse stage-28-closed^{} equivalent: the peeled
    #    commit SHA must match the locked Stage 28.8 closure
    #    commit.
    assert peeled_sha == _STAGE_28_8_CLOSURE_COMMIT_SHA, (
        f"stage-28-closed must peel to Stage 28.8 closure "
        f"commit {_STAGE_28_8_CLOSURE_COMMIT_SHA!r}; saw peeled "
        f"SHA {peeled_sha!r}"
    )

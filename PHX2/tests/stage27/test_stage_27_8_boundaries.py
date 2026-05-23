"""Stage 27.8 closure-only boundary tests.

Stage 27.8 may add closure/handoff docs and tests. It must not add
live runtime modules, public routing, subscriber routing, paid
tiers, Telegram, X/social, Stage 29 enforcement, automated trading,
or new env-read sites.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest


PHX2_ROOT: Path = Path(__file__).resolve().parent.parent.parent
STAGE27_ROOT: Path = PHX2_ROOT / "stage27"


_STAGE_27_7B_LOCKED_PRODUCTION_PY: frozenset[str] = frozenset(
    {
        "__init__.py",
        "live_config_errors.py",
        "live_config_models.py",
        "live_run_identity.py",
        "live_secrets_readiness.py",
        "live_operator_config.py",
        "pair_detection_constants.py",
        "pair_detection_models.py",
        "pair_detection_contracts.py",
        "pump_pair_classifier.py",
        "provider_ingest_models.py",
        "provider_ingest_contracts.py",
        "provider_event_adapter.py",
        "live_provider_composition.py",
        "stage27_3_manifest.py",
        "price_ath_context_models.py",
        "price_ath_context_contracts.py",
        "price_ath_context_reader.py",
        "migration_context_models.py",
        "live_measurement_context.py",
        "stage27_4_manifest.py",
        "private_ping_models.py",
        "private_ping_renderer.py",
        "private_ping_provenance.py",
        "private_ping_artifact_writer.py",
        "stage27_5_manifest.py",
        "live_dedupe.py",
        "live_candidate_assembler.py",
        "bounded_tradeable_ping_runner.py",
        "stage27_6_manifest.py",
        "dry_run_smoke_harness.py",
        "stage27_7_manifest.py",
        "private_discord_models.py",
        "private_discord_sender.py",
        "live_smoke_dispatch.py",
        "stage27_7b_manifest.py",
    }
)


_STAGE_27_8_ALLOWED_MD: frozenset[str] = frozenset(
    {
        "STAGE_27_0_SPEC_LOCK.md",
        "STAGE_27_OPERATOR_RUNBOOK.md",
        "STAGE_27_DRY_RUN_SMOKE_CHECKLIST.md",
        "STAGE_27_CLOSURE_AUDIT.md",
        "STAGE_28_HANDOFF.md",
    }
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_stage_27_8_adds_no_live_runtime_python_modules():
    py_files = {
        p.name
        for p in STAGE27_ROOT.iterdir()
        if p.is_file() and p.suffix == ".py"
    }
    assert py_files == _STAGE_27_7B_LOCKED_PRODUCTION_PY


def test_stage_27_8_markdown_inventory_is_closure_only():
    md_files = {
        p.name
        for p in STAGE27_ROOT.iterdir()
        if p.is_file() and p.suffix == ".md"
    }
    assert md_files == _STAGE_27_8_ALLOWED_MD


def test_stage27_root_admits_only_27_8_closure_entries():
    actual: set[str] = set()
    for entry in STAGE27_ROOT.iterdir():
        if entry.is_dir() and entry.name == "__pycache__":
            continue
        actual.add(entry.name)
    allowed = _STAGE_27_7B_LOCKED_PRODUCTION_PY | _STAGE_27_8_ALLOWED_MD
    assert actual == allowed


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


def test_no_env_reads_added_outside_live_secrets_readiness():
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


_FORBIDDEN_PUBLIC_ROUTING_OR_ENFORCEMENT_BASENAMES: tuple[str, ...] = (
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
    "discord_bot.py",
    "slash_commands.py",
    "subscriber_models.py",
    "subscriber_db.py",
    "discord.py",
    "telegram.py",
)


@pytest.mark.parametrize(
    "basename", _FORBIDDEN_PUBLIC_ROUTING_OR_ENFORCEMENT_BASENAMES
)
def test_no_public_routing_enforcement_or_x_social_module_exists(
    basename: str,
):
    assert not (STAGE27_ROOT / basename).exists()


_FORBIDDEN_STAGE_28_HARDENING_BASENAMES: tuple[str, ...] = (
    "crash_recovery.py",
    "retry_policy.py",
    "retries.py",
    "backoff.py",
    "health_checks.py",
    "restart_safe_dedupe.py",
    "provider_failure_handler.py",
    "monitoring.py",
    "logging_pipeline.py",
    "tracked_transport.py",
    "dexscreener_fallback.py",
)


@pytest.mark.parametrize("basename", _FORBIDDEN_STAGE_28_HARDENING_BASENAMES)
def test_stage_27_8_does_not_implement_stage_28_hardening(
    basename: str,
):
    assert not (STAGE27_ROOT / basename).exists()

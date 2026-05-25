"""Stage 29.1 runbook content pins.

Pins:

  * Operator runbook
    ``PHX2/stage29/STAGE_29_1_PUMPSWAP_HINT_EXTRACTOR_RUNBOOK.md``
    exists.
  * Lists the four canonical Stage 28.11 env names verbatim.
  * Lists each wrong env name from the prior plan and flags
    them as wrong.
  * Names every Stage 29.1 production file, every Stage 29.1
    test file, and the vendored IDL path.
  * Carries the Stage 29.1 forbidden-surface clauses (no
    Discord, no Birdeye, no PHX1 import, no Pump.fun
    bonding-curve decoder, no Stage 29.2/29.3).
  * Carries the live-probe shape, including the
    DECODED_WITH_HINTS / PUMP_SOL / PUMP_USDC outcome.
  * Carries no URL host literal, no raw-secret-looking
    literal.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest


PHX2_ROOT: Path = Path(__file__).resolve().parent.parent.parent
RUNBOOK_PATH: Path = (
    PHX2_ROOT / "stage29"
    / "STAGE_29_1_PUMPSWAP_HINT_EXTRACTOR_RUNBOOK.md"
)


def _runbook_text() -> str:
    return RUNBOOK_PATH.read_text(encoding="utf-8")


def _normalized(text: str) -> str:
    return " ".join(text.split())


def test_runbook_exists():
    assert RUNBOOK_PATH.is_file(), (
        f"Stage 29.1 requires operator runbook at {RUNBOOK_PATH}"
    )


# ---------------------------------------------------------------------------
# Canonical env names verbatim
# ---------------------------------------------------------------------------


_CANONICAL_ENV_NAMES: tuple[str, ...] = (
    "PHX2_CHAINSTACK_YELLOWSTONE_GRPC_ENDPOINT",
    "PHX2_CHAINSTACK_YELLOWSTONE_X_TOKEN",
    "PHX2_STAGE28_11_ALLOW_LIVE_GRPC",
    "PHX2_STAGE28_11_GRPC_TIMEOUT_SECONDS",
)


@pytest.mark.parametrize("name", _CANONICAL_ENV_NAMES)
def test_runbook_lists_canonical_env_name(name):
    assert name in _runbook_text(), (
        f"runbook missing canonical env name {name!r}"
    )


# The wrong env names from the prior plan MUST appear in the
# runbook only in the "do not use these wrong names" section so
# the operator is warned. The runbook test pins they are
# present (so the warning section is present) AND that the
# correct names ALSO appear (verified above).
_WRONG_ENV_NAMES: tuple[str, ...] = (
    "PHX2_STAGE28_11_GRPC_LIVE_ALLOW",
    "PHX2_STAGE28_11_GRPC_ENDPOINT",
    "PHX2_STAGE28_11_GRPC_X_TOKEN",
)


@pytest.mark.parametrize("name", _WRONG_ENV_NAMES)
def test_runbook_flags_each_wrong_env_name(name):
    assert name in _runbook_text(), (
        f"runbook must call out wrong env name {name!r} "
        f"explicitly so the operator does not confuse it with "
        f"the canonical name"
    )


# ---------------------------------------------------------------------------
# Production / test file inventory mentioned
# ---------------------------------------------------------------------------


_PRODUCTION_BASENAMES: tuple[str, ...] = (
    "pumpswap_program_constants.py",
    "pumpswap_hint_models.py",
    "pumpswap_hint_extractor.py",
    "pumpswap_hint_aware_decoder.py",
    "stage29_1_hint_probe_models.py",
    "stage29_1_pumpswap_hint_probe.py",
    "stage29_1_manifest.py",
)


@pytest.mark.parametrize("basename", _PRODUCTION_BASENAMES)
def test_runbook_lists_each_production_basename(basename):
    assert basename in _runbook_text()


_TEST_BASENAMES: tuple[str, ...] = (
    "test_stage_29_1_pumpswap_program_constants.py",
    "test_stage_29_1_pumpswap_hint_models.py",
    "test_stage_29_1_pumpswap_hint_extractor.py",
    "test_stage_29_1_pumpswap_hint_aware_decoder.py",
    "test_stage_29_1_hint_probe_models.py",
    "test_stage_29_1_pumpswap_hint_probe.py",
    "test_stage_29_1_runbook.py",
    "test_stage_29_1_boundaries.py",
    "test_stage_29_1_vendored_idl.py",
)


@pytest.mark.parametrize("basename", _TEST_BASENAMES)
def test_runbook_lists_each_test_basename(basename):
    assert basename in _runbook_text()


def test_runbook_lists_vendored_idl_path():
    assert "PHX2/proto/stage29_1/source/pump_amm.json" in (
        _runbook_text()
    )


# ---------------------------------------------------------------------------
# Forbidden-surface clauses
# ---------------------------------------------------------------------------


_FORBIDDEN_SURFACE_PHRASES: tuple[str, ...] = (
    "NO Discord send",
    "NO diagnostic Discord smoke",
    "NO Birdeye adapter",
    "NO Dexscreener",
    "NO Helius",
    "NO Telegram",
    "NO X / social",
    "NO automated trading",
    "NO wallet / private-key / signer logic",
    "NO position sizing",
    "NO trade execution",
    "NO public",
    "NO subscriber",
    "NO paid tier routing",
    "NO Stage 26 enforcement activation",
    "NO Stage 28.9 wrapper invocation",
    "NO Stage 28.6 bounded runner invocation",
    "NO Stage 28.4 audited transport invocation",
    "NO Pump.fun bonding-curve decoder",
    "NO Pump.fun bonding-curve program id constant",
    "NO Stage 29.2 Birdeye adapter implementation",
    "NO Stage 29.3 tradeable Discord smoke",
    "NO PHX1 import path",
)


@pytest.mark.parametrize("phrase", _FORBIDDEN_SURFACE_PHRASES)
def test_runbook_carries_forbidden_surface_clause(phrase):
    normalized = _normalized(_runbook_text())
    assert phrase in normalized, (
        f"runbook missing forbidden-surface clause {phrase!r}"
    )


# ---------------------------------------------------------------------------
# Live-probe shape
# ---------------------------------------------------------------------------


_LIVE_PROBE_SHAPE_PHRASES: tuple[str, ...] = (
    "DECODED_WITH_HINTS",
    "ONE_PUMPSWAP_EVENT_HINT_DRY_RUN",
    "PUMP_SOL",
    "PUMP_USDC",
    "pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA",
    "run_stage29_1_pumpswap_hint_probe",
    "build_runtime_config_from_env",
    "max_messages_to_scan",
    "handoff_ready",
)


@pytest.mark.parametrize("phrase", _LIVE_PROBE_SHAPE_PHRASES)
def test_runbook_lists_live_probe_shape_phrase(phrase):
    assert phrase in _runbook_text(), (
        f"runbook missing live-probe shape phrase {phrase!r}"
    )


# ---------------------------------------------------------------------------
# No URL host / raw-secret literal scan
# ---------------------------------------------------------------------------


# Concatenated literally so this test file doesn't itself trip
# a downstream URL/secret scan.
_FORBIDDEN_URL_HOSTS: tuple[str, ...] = (
    "h" + "ttps://",
    "h" + "ttp://",
    "w" + "ss://",
    "discord" + ".com",
    "discordapp" + ".com",
    "hooks" + ".slack.com",
    "birdeye" + ".so",
    "chainstack" + ".com",
    "helius" + ".xyz",
)


@pytest.mark.parametrize("needle", _FORBIDDEN_URL_HOSTS)
def test_runbook_has_no_url_literal(needle):
    assert needle not in _runbook_text(), (
        f"runbook must not contain URL literal {needle!r}"
    )


_FORBIDDEN_SECRET_PATTERNS: tuple[str, ...] = (
    r"Authorization:\s*\S+",
    r"Bearer\s+[A-Za-z0-9._~+/=-]{8,}",
    r"\bsk-[A-Za-z0-9_-]{8,}\b",
)


@pytest.mark.parametrize("pattern", _FORBIDDEN_SECRET_PATTERNS)
def test_runbook_has_no_secret_looking_raw_value(pattern):
    assert not re.search(pattern, _runbook_text())

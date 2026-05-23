"""Stage 28 handoff document tests."""

from __future__ import annotations

from pathlib import Path

import pytest


PHX2_ROOT: Path = Path(__file__).resolve().parent.parent.parent
STAGE27_ROOT: Path = PHX2_ROOT / "stage27"
STAGE28_HANDOFF_PATH: Path = STAGE27_ROOT / "STAGE_28_HANDOFF.md"


def _handoff_text() -> str:
    return STAGE28_HANDOFF_PATH.read_text(encoding="utf-8")


def _normalized(text: str) -> str:
    return " ".join(text.split())


def test_stage_28_handoff_file_exists():
    assert STAGE28_HANDOFF_PATH.is_file(), (
        f"Stage 27.8 requires {STAGE28_HANDOFF_PATH}"
    )


def test_stage_28_handoff_states_private_runner_hardening_mission():
    normalized = _normalized(_handoff_text()).lower()
    assert (
        "stage 28 mission: private live runner hardening after "
        "stage 27 closure"
    ) in normalized


_REQUIRED_STAGE_28_HARDENING_ITEMS: tuple[str, ...] = (
    "crash recovery",
    "retries/backoff",
    "health checks",
    "restart-safe dedupe",
    "provider failure handling",
    "monitoring/logging",
    "longer-running private sessions",
    "provider-neutral config cleanup for Chainstack/Helius naming",
    "optional Dexscreener fallback/cross-check design",
    "safe transition from scratch transport to audited tracked transport",
)


@pytest.mark.parametrize("phrase", _REQUIRED_STAGE_28_HARDENING_ITEMS)
def test_stage_28_handoff_contains_required_hardening_item(
    phrase: str,
):
    normalized = _normalized(_handoff_text()).lower()
    assert phrase.lower() in normalized


_STAGE_28_FORBIDDEN_SCOPE_ITEMS: tuple[str, ...] = (
    "public routing",
    "paid tiers",
    "subscriber routing",
    "X/social",
    "Stage 29 enforcement",
    "automated trading",
)


@pytest.mark.parametrize("phrase", _STAGE_28_FORBIDDEN_SCOPE_ITEMS)
def test_stage_28_handoff_keeps_forbidden_scope_out_of_stage_28(
    phrase: str,
):
    text = _handoff_text()
    assert "Stage 28 must not include" in text
    assert phrase in text


def test_stage_28_handoff_states_stage_29_owns_enforcement():
    text = _handoff_text()
    assert "Stage 29 owns approved enforcement/live gating" in text
    assert "requires its own explicit authorization" in text


def test_stage_28_handoff_states_stage_30_plus_owns_x_social():
    text = _handoff_text()
    assert "Stage 30+ owns the X/social sidecar" in text
    assert "must stay out of Stage 28" in text


def test_stage_28_handoff_says_no_stage_27_7b_dispatch_change():
    text = _normalized(_handoff_text())
    assert "should not alter Stage 27.7b dispatch behavior" in text

"""Shared pytest fixtures for Stage 15 tests."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from PHX2.tests.stage15.fixtures.builders import (
    DEFAULT_REVIEWER,
    DEFAULT_REVIEWED_AT,
    approve_row,
    make_operator_csv,
    make_stage14_run,
)


@pytest.fixture
def stage14_run(tmp_path: Path) -> Path:
    """Default valid Stage 14 run with two rules.

    Rule 1 (``shadow_rule_default_aaaa``) carries warning_flags
    ``small_n_rule;excessive_block_rate``. Rule 2 (``shadow_rule_default_bbbb``)
    has no warning_flags. Together they exercise the override path and
    the no-flags path in approval-time validation.
    """

    return make_stage14_run(tmp_path / "stage14_runs")


@pytest.fixture
def good_operator_csv(tmp_path: Path) -> Path:
    """Default valid operator review CSV approving both default rules.

    Rule 1 (with flags) gets override=true plus a reason; rule 2 (no
    flags) gets approval with no reason needed. This pairing produces
    a clean Stage 15 run when fed to the CLI.
    """

    path = tmp_path / "operator_review.csv"
    make_operator_csv(
        path,
        rows=(
            approve_row(
                "shadow_rule_default_aaaa",
                reason="flagged but accepted under observe-only",
                override=True,
            ),
            approve_row("shadow_rule_default_bbbb"),
        ),
    )
    return path


@pytest.fixture
def reviewer_name() -> str:
    return DEFAULT_REVIEWER


@pytest.fixture
def now_utc() -> datetime:
    """Stable wall-clock anchor for tests that depend on the future-
    timestamp tolerance window."""

    return datetime(2026, 5, 13, 12, 0, tzinfo=timezone.utc)

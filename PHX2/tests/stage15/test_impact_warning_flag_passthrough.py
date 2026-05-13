"""Stage 15 PHASE 2 warning-flag passthrough tests.

The warning-flag contract is the most distinctive part of Stage 15:
flags come verbatim from Stage 14's ``impact_summary_by_rule.csv``,
without derivation, without name validation, without renaming.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from PHX2.stage15.loaders import (
    load_impact_summary,
    load_stage14_artifact,
    parse_warning_flags,
)
from PHX2.tests.stage15.fixtures.builders import make_stage14_run


# ---------------------------------------------------------------------------
# parse_warning_flags semantics
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("", ()),
        ("small_n_rule", ("small_n_rule",)),
        (
            "small_n_rule;excessive_block_rate",
            ("small_n_rule", "excessive_block_rate"),
        ),
        (
            "  small_n_rule ; high_winners_blocked_rate  ",
            ("small_n_rule", "high_winners_blocked_rate"),
        ),
        (";;;", ()),
        (";a;;b;", ("a", "b")),
        # Unknown / future flag names pass through verbatim
        (
            "definitely_a_future_flag_in_2030",
            ("definitely_a_future_flag_in_2030",),
        ),
        (None, ()),
    ],
)
def test_parse_warning_flags(raw, expected) -> None:
    assert parse_warning_flags(raw) == expected


# ---------------------------------------------------------------------------
# Passthrough integration via load_impact_summary
# ---------------------------------------------------------------------------


def test_passthrough_default_fixture(tmp_path: Path) -> None:
    """The default fixture: rule_aaaa has flags, rule_bbbb has none."""

    run = make_stage14_run(tmp_path / "s14")
    rule_ids = tuple(r.rule_id for r in load_stage14_artifact(run).rules)
    impact = load_impact_summary(run, rule_ids)
    assert impact.warning_flags_by_rule["shadow_rule_default_aaaa"] == (
        "small_n_rule",
        "excessive_block_rate",
    )
    assert impact.warning_flags_by_rule["shadow_rule_default_bbbb"] == ()


def test_passthrough_unknown_future_flag(tmp_path: Path) -> None:
    """Stage 15 must not validate flag names against any enum."""

    run = make_stage14_run(
        tmp_path / "s14",
        rules=(
            {
                "rule_id": "rule_future",
                "tier_scope": "T2",
                "filter_name": "fee_gate",
                "filter_version": "fee_gate_v1",
                "filter_label": "x",
                "threshold_version": "v1",
                "warning_flags": "future_flag_xyz_2030",
            },
        ),
    )
    rule_ids = tuple(r.rule_id for r in load_stage14_artifact(run).rules)
    impact = load_impact_summary(run, rule_ids)
    assert impact.warning_flags_by_rule["rule_future"] == (
        "future_flag_xyz_2030",
    )


def test_passthrough_no_threshold_constants_in_codebase() -> None:
    """Sanity: Stage 15 must not introduce 0.25 / 0.40 / 0.30 derivation
    constants per the spec's warning-flag contract."""

    import PHX2.stage15.loaders as loaders
    import PHX2.stage15.reconciler as reconciler
    import PHX2.stage15.writer as writer
    import PHX2.stage15.markdown as md

    for module in (loaders, reconciler, writer, md):
        source = Path(module.__file__).read_text(encoding="utf-8")
        for forbidden in ("0.25", "0.40", "0.30"):
            assert forbidden not in source, (
                f"forbidden derivation constant {forbidden!r} found in "
                f"{module.__name__}"
            )


def test_no_warning_flag_enum_validation() -> None:
    """Stage 15 must not expose a warning-flag enum/allow-list. Failing
    this test means someone added derivation logic the spec forbids."""

    import PHX2.stage15.loaders as loaders

    # Inspect module-level identifiers for anything that smells like an
    # enum of warning flag names.
    forbidden_names = (
        "WARNING_FLAGS_ENUM",
        "KNOWN_WARNING_FLAGS",
        "VALID_WARNING_FLAGS",
        "ALLOWED_WARNING_FLAGS",
    )
    for name in forbidden_names:
        assert not hasattr(loaders, name), (
            f"loaders.{name} would imply Stage 15 validates flag names; "
            f"the warning-flag contract is passthrough-only"
        )

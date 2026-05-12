"""Stage 13 classifier unit tests.

Table-driven coverage of every n-band x lift x CI x direction
combination plus the cross-cutting modifiers (confidence ceiling,
censoring downgrade, anomaly overrides, per-tier override rule).

Each test is self-contained; no fixtures are shared between tests so
failures localize cleanly.
"""

from __future__ import annotations

import pytest

from PHX2.stage13.classifier import (
    CONFIDENCE_FLAG_LOW_SENTINEL,
    apply_anomaly_overrides,
    apply_censoring_downgrade,
    apply_confidence_ceiling,
    apply_per_tier_override,
    classify_row,
    compute_censoring_rate,
    determine_direction,
    summarize_tier_support,
)
from PHX2.stage13.types import EvidenceThresholds


_T = EvidenceThresholds()


# ---------------------------------------------------------------------------
# determine_direction
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "cohort,baseline,expected",
    [
        (0.3, 0.5, "tighten"),
        (0.5, 0.3, "loosen"),
        (0.5, 0.5, "none"),
        (None, 0.5, "none"),
        (0.5, None, "none"),
        (float("nan"), 0.5, "none"),
        (0.5, float("nan"), "none"),
    ],
)
def test_determine_direction(cohort, baseline, expected) -> None:
    assert determine_direction(cohort, baseline) == expected


# ---------------------------------------------------------------------------
# classify_row -- n-band gate
# ---------------------------------------------------------------------------


def test_classify_n_below_insufficient_returns_insufficient_evidence() -> None:
    # n_complete < 10 -> INSUFFICIENT_EVIDENCE, regardless of lift/CI.
    ev, act = classify_row(
        n_complete=5,
        lift_absolute=-0.25,  # large lift ignored
        ci_excludes_baseline=True,
        direction="tighten",
        thresholds=_T,
    )
    assert ev == "insufficient"
    assert act == "INSUFFICIENT_EVIDENCE"


def test_classify_n_in_weak_band_returns_weak_max() -> None:
    # 10 <= n < 20: band cap is "weak"; ADVANCE never reachable.
    ev, act = classify_row(
        n_complete=15,
        lift_absolute=-0.40,
        ci_excludes_baseline=True,
        direction="tighten",
        thresholds=_T,
    )
    assert ev == "weak"
    assert act == "HOLD_OBSERVE_ONLY"


def test_classify_n_in_moderate_band_caps_at_moderate() -> None:
    # 20 <= n < 30: band cap is "moderate". Strong lift+CI cannot push
    # to "strong"; ADVANCE remains unreachable.
    ev, act = classify_row(
        n_complete=25,
        lift_absolute=-0.40,
        ci_excludes_baseline=True,
        direction="tighten",
        thresholds=_T,
    )
    assert ev == "moderate"
    assert act == "HOLD_OBSERVE_ONLY"


def test_classify_n_in_strong_band_with_strong_lift_and_ci_excludes() -> None:
    # n >= 30 + |lift| >= 0.10 + CI excludes baseline + tighten ->
    # the only path that reaches ADVANCE_AS_CANDIDATE.
    ev, act = classify_row(
        n_complete=40,
        lift_absolute=-0.20,
        ci_excludes_baseline=True,
        direction="tighten",
        thresholds=_T,
    )
    assert ev == "strong"
    assert act == "ADVANCE_AS_CANDIDATE"


# ---------------------------------------------------------------------------
# classify_row -- lift floors
# ---------------------------------------------------------------------------


def test_classify_lift_below_moderate_floor_triggers_no_signal() -> None:
    # n_complete >= 10 and |lift| < 0.05 -> NO_SIGNAL_FOUND.
    ev, act = classify_row(
        n_complete=50,
        lift_absolute=-0.02,
        ci_excludes_baseline=False,
        direction="tighten",
        thresholds=_T,
    )
    assert ev == "strong"  # band cap retained for visibility
    assert act == "NO_SIGNAL_FOUND"


def test_classify_lift_at_moderate_floor_caps_at_moderate_without_ci() -> None:
    # |lift| == 0.05 AND CI does NOT exclude baseline -> moderate,
    # not strong.
    ev, act = classify_row(
        n_complete=50,
        lift_absolute=-0.05,
        ci_excludes_baseline=False,
        direction="tighten",
        thresholds=_T,
    )
    assert ev == "moderate"
    assert act == "HOLD_OBSERVE_ONLY"


def test_classify_strong_lift_without_ci_exclusion_falls_to_moderate() -> None:
    # |lift| = 0.15 (>= 0.10) but CI overlaps baseline -> moderate
    # (since strong requires BOTH conditions).
    ev, act = classify_row(
        n_complete=50,
        lift_absolute=-0.15,
        ci_excludes_baseline=False,
        direction="tighten",
        thresholds=_T,
    )
    assert ev == "moderate"
    assert act == "HOLD_OBSERVE_ONLY"


def test_classify_strong_lift_with_ci_exclusion_is_strong() -> None:
    ev, act = classify_row(
        n_complete=50,
        lift_absolute=0.15,
        ci_excludes_baseline=True,
        direction="loosen",
        thresholds=_T,
    )
    # Even strong loosen is capped at HOLD_OBSERVE_ONLY per L6.
    assert ev == "strong"
    assert act == "HOLD_OBSERVE_ONLY"


def test_classify_no_signal_with_no_lift_value() -> None:
    # lift_absolute=None is treated as "cannot compute" -> weak path
    # (band cap permits) and HOLD_OBSERVE_ONLY (not strong, not NO
    # SIGNAL because we cannot assert |lift| < 0.05).
    ev, act = classify_row(
        n_complete=50,
        lift_absolute=None,
        ci_excludes_baseline=False,
        direction="tighten",
        thresholds=_T,
    )
    assert ev == "weak"
    assert act == "HOLD_OBSERVE_ONLY"


# ---------------------------------------------------------------------------
# Direction interaction
# ---------------------------------------------------------------------------


def test_classify_strong_loosen_never_advances() -> None:
    ev, act = classify_row(
        n_complete=200,
        lift_absolute=0.40,
        ci_excludes_baseline=True,
        direction="loosen",
        thresholds=_T,
    )
    assert ev == "strong"
    assert act == "HOLD_OBSERVE_ONLY"


def test_classify_none_direction_never_advances() -> None:
    ev, act = classify_row(
        n_complete=200,
        lift_absolute=0.40,
        ci_excludes_baseline=True,
        direction="none",
        thresholds=_T,
    )
    assert ev == "strong"
    assert act != "ADVANCE_AS_CANDIDATE"


# ---------------------------------------------------------------------------
# Confidence ceiling
# ---------------------------------------------------------------------------


def test_confidence_ceiling_caps_strong_at_moderate() -> None:
    ev, act, applied = apply_confidence_ceiling(
        "strong",
        "ADVANCE_AS_CANDIDATE",
        CONFIDENCE_FLAG_LOW_SENTINEL,
        "tighten",
    )
    assert ev == "moderate"
    assert act == "HOLD_OBSERVE_ONLY"
    assert applied is True


def test_confidence_ceiling_passes_through_below_strong() -> None:
    ev, act, applied = apply_confidence_ceiling(
        "moderate",
        "HOLD_OBSERVE_ONLY",
        CONFIDENCE_FLAG_LOW_SENTINEL,
        "tighten",
    )
    assert ev == "moderate"
    assert act == "HOLD_OBSERVE_ONLY"
    # Still report that the flag was active even though the cap was
    # already at-or-below moderate; reviewers see it via the row's
    # confidence_ceiling_applied column.
    assert applied is True


def test_confidence_ceiling_inactive_on_caveat_flag() -> None:
    ev, act, applied = apply_confidence_ceiling(
        "strong",
        "ADVANCE_AS_CANDIDATE",
        "caveat",
        "tighten",
    )
    assert ev == "strong"
    assert act == "ADVANCE_AS_CANDIDATE"
    assert applied is False


def test_confidence_ceiling_inactive_on_standard_flag() -> None:
    ev, act, applied = apply_confidence_ceiling(
        "strong",
        "ADVANCE_AS_CANDIDATE",
        "standard",
        "tighten",
    )
    assert ev == "strong"
    assert act == "ADVANCE_AS_CANDIDATE"
    assert applied is False


def test_confidence_ceiling_inactive_on_none_flag() -> None:
    ev, act, applied = apply_confidence_ceiling(
        "strong",
        "ADVANCE_AS_CANDIDATE",
        None,
        "tighten",
    )
    assert applied is False
    assert ev == "strong"


# ---------------------------------------------------------------------------
# Censoring downgrade
# ---------------------------------------------------------------------------


def test_censoring_downgrade_strong_to_moderate_with_advance_knockon() -> None:
    ev, act, flag = apply_censoring_downgrade(
        "strong", "ADVANCE_AS_CANDIDATE", 0.50, _T,
    )
    assert ev == "moderate"
    assert act == "HOLD_OBSERVE_ONLY"
    assert flag is True


def test_censoring_downgrade_moderate_to_weak() -> None:
    ev, act, flag = apply_censoring_downgrade(
        "moderate", "HOLD_OBSERVE_ONLY", 0.50, _T,
    )
    assert ev == "weak"
    assert act == "HOLD_OBSERVE_ONLY"
    assert flag is True


def test_censoring_at_threshold_does_not_downgrade() -> None:
    # spec: "censoring_rate > 0.30". Exact 0.30 is below the trigger.
    ev, act, flag = apply_censoring_downgrade(
        "strong", "ADVANCE_AS_CANDIDATE", 0.30, _T,
    )
    assert ev == "strong"
    assert act == "ADVANCE_AS_CANDIDATE"
    assert flag is False


def test_censoring_none_rate_does_not_downgrade() -> None:
    # NULL censoring_rate (denominator zero) is not a trigger.
    ev, act, flag = apply_censoring_downgrade(
        "strong", "ADVANCE_AS_CANDIDATE", None, _T,
    )
    assert ev == "strong"
    assert act == "ADVANCE_AS_CANDIDATE"
    assert flag is False


def test_censoring_weak_stays_weak_but_flag_set() -> None:
    ev, act, flag = apply_censoring_downgrade(
        "weak", "HOLD_OBSERVE_ONLY", 0.6, _T,
    )
    assert ev == "weak"
    assert act == "HOLD_OBSERVE_ONLY"
    assert flag is True


# ---------------------------------------------------------------------------
# Anomaly overrides
# ---------------------------------------------------------------------------


def test_anomaly_cohort_rate_zero() -> None:
    action, direction, notes, triggered = apply_anomaly_overrides(
        cohort_rate=0.0,
        baseline_rate=0.5,
        action="ADVANCE_AS_CANDIDATE",
        direction="tighten",
    )
    assert triggered is True
    assert action == "ANOMALY_FLAG"
    assert direction == "none"
    assert any("cohort_rate_extreme" in n for n in notes)


def test_anomaly_cohort_rate_one() -> None:
    action, direction, notes, triggered = apply_anomaly_overrides(
        cohort_rate=1.0,
        baseline_rate=0.5,
        action="ADVANCE_AS_CANDIDATE",
        direction="loosen",
    )
    assert triggered is True
    assert action == "ANOMALY_FLAG"
    assert direction == "none"


def test_anomaly_baseline_rate_zero_emits_note() -> None:
    action, direction, notes, triggered = apply_anomaly_overrides(
        cohort_rate=0.3,
        baseline_rate=0.0,
        action="HOLD_OBSERVE_ONLY",
        direction="loosen",
    )
    assert triggered is True
    assert action == "ANOMALY_FLAG"
    assert direction == "none"
    assert "baseline_rate_zero" in notes


def test_anomaly_passes_through_when_no_trigger() -> None:
    action, direction, notes, triggered = apply_anomaly_overrides(
        cohort_rate=0.30,
        baseline_rate=0.50,
        action="ADVANCE_AS_CANDIDATE",
        direction="tighten",
    )
    assert triggered is False
    assert action == "ADVANCE_AS_CANDIDATE"
    assert direction == "tighten"
    assert notes == []


# ---------------------------------------------------------------------------
# Per-tier override
# ---------------------------------------------------------------------------


def test_per_tier_override_advance_with_matching_tier_stays_advance() -> None:
    per_tier = [
        {
            "cohort_id": "X",
            "tier_scope": "T1",
            "action_class": "ADVANCE_AS_CANDIDATE",
            "direction": "tighten",
        },
        {
            "cohort_id": "X",
            "tier_scope": "T2",
            "action_class": "HOLD_OBSERVE_ONLY",
            "direction": "tighten",
        },
    ]
    summary = summarize_tier_support("X", per_tier)
    action, direction, notes, support, disagree = apply_per_tier_override(
        overall_action="ADVANCE_AS_CANDIDATE",
        overall_direction="tighten",
        overall_notes=[],
        tier_support=summary,
    )
    assert action == "ADVANCE_AS_CANDIDATE"
    assert direction == "tighten"
    assert support == ["T1"]
    assert disagree is False


def test_per_tier_override_advance_with_all_non_blocking_downgrades_to_anomaly() -> None:
    per_tier = [
        {
            "cohort_id": "X",
            "tier_scope": "T1",
            "action_class": "NO_SIGNAL_FOUND",
            "direction": "none",
        },
        {
            "cohort_id": "X",
            "tier_scope": "T2",
            "action_class": "INSUFFICIENT_EVIDENCE",
            "direction": "none",
        },
    ]
    summary = summarize_tier_support("X", per_tier)
    action, direction, notes, support, disagree = apply_per_tier_override(
        overall_action="ADVANCE_AS_CANDIDATE",
        overall_direction="tighten",
        overall_notes=[],
        tier_support=summary,
    )
    assert action == "ANOMALY_FLAG"
    assert direction == "none"
    assert any("pooling artifact" in n for n in notes)


def test_per_tier_override_advance_with_no_matching_tier_falls_to_hold() -> None:
    per_tier = [
        {
            "cohort_id": "X",
            "tier_scope": "T1",
            "action_class": "HOLD_OBSERVE_ONLY",
            "direction": "tighten",
        },
    ]
    summary = summarize_tier_support("X", per_tier)
    action, direction, notes, support, disagree = apply_per_tier_override(
        overall_action="ADVANCE_AS_CANDIDATE",
        overall_direction="tighten",
        overall_notes=[],
        tier_support=summary,
    )
    assert action == "HOLD_OBSERVE_ONLY"
    assert any("no matching per-tier advance" in n for n in notes)


def test_per_tier_override_direction_disagreement_promotes_to_anomaly() -> None:
    per_tier = [
        {
            "cohort_id": "X",
            "tier_scope": "T1",
            "action_class": "HOLD_OBSERVE_ONLY",
            "direction": "loosen",
        },
    ]
    summary = summarize_tier_support("X", per_tier)
    action, direction, notes, support, disagree = apply_per_tier_override(
        overall_action="HOLD_OBSERVE_ONLY",
        overall_direction="tighten",
        overall_notes=[],
        tier_support=summary,
    )
    assert disagree is True
    assert action == "ANOMALY_FLAG"
    assert any("cross-tier disagreement" in n for n in notes)


def test_per_tier_override_no_per_tier_rows_leaves_overall_unchanged() -> None:
    summary = summarize_tier_support("X", [])
    action, direction, notes, support, disagree = apply_per_tier_override(
        overall_action="HOLD_OBSERVE_ONLY",
        overall_direction="tighten",
        overall_notes=[],
        tier_support=summary,
    )
    assert action == "HOLD_OBSERVE_ONLY"
    assert disagree is False
    assert support == []


# ---------------------------------------------------------------------------
# Censoring rate helper
# ---------------------------------------------------------------------------


def test_compute_censoring_rate_basic() -> None:
    assert compute_censoring_rate(80, 20) == pytest.approx(0.20)


def test_compute_censoring_rate_zero_denominator_returns_none() -> None:
    assert compute_censoring_rate(0, 0) is None


def test_compute_censoring_rate_all_censored() -> None:
    assert compute_censoring_rate(0, 10) == 1.0


# ---------------------------------------------------------------------------
# F4 audit remediation: classifier-layer guarantees about the n-band gate.
# These tests pin the contract that classify_row itself returns
# INSUFFICIENT_EVIDENCE for n < 10 regardless of how extreme the rate is.
# The downstream builder-layer F1 tests verify that the anomaly override
# does not promote those rows past the n-band cap.
# ---------------------------------------------------------------------------


def test_classify_row_low_n_with_strong_lift_still_insufficient() -> None:
    ev, act = classify_row(
        n_complete=4,
        lift_absolute=-0.50,
        ci_excludes_baseline=True,
        direction="tighten",
        thresholds=_T,
    )
    assert ev == "insufficient"
    assert act == "INSUFFICIENT_EVIDENCE"


def test_classify_row_low_n_with_loosen_direction_still_insufficient() -> None:
    ev, act = classify_row(
        n_complete=9,
        lift_absolute=0.40,
        ci_excludes_baseline=True,
        direction="loosen",
        thresholds=_T,
    )
    # The loosen cap is *also* irrelevant here -- the n-band fires
    # first and the row is INSUFFICIENT_EVIDENCE.
    assert ev == "insufficient"
    assert act == "INSUFFICIENT_EVIDENCE"


def test_anomaly_overrides_signal_low_n_but_caller_decides() -> None:
    # The anomaly helper itself still flags low-n cohort_rate=0.0 as
    # an anomaly observation; the BUILDER is the layer that gates the
    # promotion based on n_complete. This test pins that contract so
    # the F1 builder gate stays load-bearing.
    action, direction, notes, triggered = apply_anomaly_overrides(
        cohort_rate=0.0,
        baseline_rate=0.5,
        action="INSUFFICIENT_EVIDENCE",
        direction="none",
    )
    # Helper triggers; the BUILDER's n-band gate decides whether to
    # actually promote.
    assert triggered is True
    assert action == "ANOMALY_FLAG"
    assert any("cohort_rate_extreme:0.0" in n for n in notes)

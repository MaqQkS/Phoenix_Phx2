"""Stage 13 classifier (pure functions).

Implements the locked evidence-class / action-class gates from the
Stage 13 spec, plus the per-tier override rule that resolves overall
cohorts against their per-tier siblings.

All functions are pure: no I/O, no DB, no globals. The classifier
operates on already-loaded numeric inputs and returns enums + flags.
The caller (``builder.py``) is responsible for sourcing the inputs
from the Stage 12 CSV bundle and for materializing ``RecommendationRow``
objects.

Order of operations for a single row's classification:

  1. ``determine_direction(cohort_rate, baseline_rate)`` — tighten /
     loosen / none.
  2. ``classify_row(...)`` — n-band gate + lift/CI to produce an initial
     ``(evidence_class, action_class)``.
  3. ``apply_confidence_ceiling(...)`` — cap evidence_class at
     "moderate" if the upstream Stage 12 confidence_flag is
     "low_confidence".
  4. ``apply_censoring_downgrade(...)`` — downgrade evidence_class one
     notch if censoring_rate exceeds the threshold.
  5. ``apply_anomaly_overrides(...)`` — override to ANOMALY_FLAG for
     extreme/degenerate rates.
  6. After ALL per-tier rows are classified, ``apply_per_tier_override``
     resolves each overall row against the matching per-tier set.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from PHX2.stage13.types import (
    ActionClass,
    Direction,
    EvidenceClass,
    EvidenceThresholds,
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


CONFIDENCE_FLAG_LOW_SENTINEL = "low_confidence"
"""Stage 12 confidence_flag value that triggers Stage 13's evidence
ceiling. Confirmed in STEP 0 S0-2: Stage 12 emits the literal string
``"low_confidence"`` for n_complete < 10 cohorts. Spec L13 names "low"
as a placeholder for whichever sentinel STEP 0 confirms."""


# ---------------------------------------------------------------------------
# Direction
# ---------------------------------------------------------------------------


def determine_direction(
    cohort_rate: float | None,
    baseline_rate: float | None,
) -> Direction:
    """Resolve direction from cohort-vs-baseline comparison.

    tighten  : cohort_rate < baseline_rate
    loosen   : cohort_rate > baseline_rate
    none     : equal, or either side is None / NaN

    The "none" branch is used both when the rate is undefined and when
    cohort == baseline exactly. The caller may further override
    direction to "none" via anomaly logic.
    """

    if cohort_rate is None or baseline_rate is None:
        return "none"
    if isinstance(cohort_rate, float) and math.isnan(cohort_rate):
        return "none"
    if isinstance(baseline_rate, float) and math.isnan(baseline_rate):
        return "none"
    if cohort_rate < baseline_rate:
        return "tighten"
    if cohort_rate > baseline_rate:
        return "loosen"
    return "none"


# ---------------------------------------------------------------------------
# Core classification
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _BandInputs:
    """Bundled inputs for the n-band + lift gate."""

    n_complete: int
    lift_absolute: float | None
    ci_excludes_baseline: bool | None
    direction: Direction


def _evidence_band_cap(
    n_complete: int, thresholds: EvidenceThresholds
) -> EvidenceClass:
    """Return the max evidence_class permitted by the n-band gate.

    n < insufficient_below   -> "insufficient"
    n < weak_below            -> "weak"
    n < moderate_below        -> "moderate"
    n >= moderate_below       -> "strong"

    Per spec §EVIDENCE-CLASS GATING, the band is the dominant gate; lift
    and CI conditions cannot upgrade evidence_class past this cap.
    """

    if n_complete < thresholds.insufficient_below:
        return "insufficient"
    if n_complete < thresholds.weak_below:
        return "weak"
    if n_complete < thresholds.moderate_below:
        return "moderate"
    return "strong"


def _classify_within_band_cap(
    inputs: _BandInputs,
    band_cap: EvidenceClass,
    thresholds: EvidenceThresholds,
) -> EvidenceClass:
    """Refine evidence_class downward from the band cap by lift/CI tests.

    Strong requires:    |lift| >= lift_strong_min AND CI excludes baseline
    Moderate requires:  |lift| >= lift_moderate_min (and not strong)
    Otherwise:          fall back to "weak" if band_cap permits, else
                         the band cap itself.

    "insufficient" is short-circuited up-stack by ``classify_row``.
    """

    lift = inputs.lift_absolute
    if lift is None:
        return band_cap if band_cap == "weak" else "weak"

    abs_lift = abs(lift)
    is_strong_lift = abs_lift >= thresholds.lift_strong_min
    is_moderate_lift = abs_lift >= thresholds.lift_moderate_min

    if band_cap == "strong" and is_strong_lift and inputs.ci_excludes_baseline:
        return "strong"
    if band_cap in ("strong", "moderate") and is_moderate_lift:
        return "moderate"
    if band_cap in ("strong", "moderate"):
        return "weak"
    return band_cap


def _is_no_signal(
    n_complete: int,
    lift_absolute: float | None,
    thresholds: EvidenceThresholds,
) -> bool:
    """NO_SIGNAL_FOUND trigger (spec §EVIDENCE-CLASS GATING):

    n_complete >= 10 AND |lift| < 0.05.
    """

    if n_complete < thresholds.insufficient_below:
        return False
    if lift_absolute is None:
        return False
    return abs(lift_absolute) < thresholds.lift_moderate_min


def classify_row(
    *,
    n_complete: int,
    lift_absolute: float | None,
    ci_excludes_baseline: bool | None,
    direction: Direction,
    thresholds: EvidenceThresholds,
) -> tuple[EvidenceClass, ActionClass]:
    """Initial (evidence_class, action_class) from n / lift / CI / direction.

    This is step 2 in the pipeline order described at module-top.
    Confidence-flag ceiling, censoring downgrade, anomaly overrides, and
    the loosen cap are applied by the dedicated helpers below.

    The loosen cap is enforced here in the simplest form: any loosen
    finding -- even strong loosen -- is downgraded to HOLD_OBSERVE_ONLY
    by the action-class assignment. This matches spec L6 ("loosen is
    capped at HOLD_OBSERVE_ONLY in v0").
    """

    band_cap = _evidence_band_cap(n_complete, thresholds)
    if band_cap == "insufficient":
        return ("insufficient", "INSUFFICIENT_EVIDENCE")

    if _is_no_signal(n_complete, lift_absolute, thresholds):
        # n_complete >= 10 and |lift| < 0.05 -> NO_SIGNAL_FOUND.
        # Evidence class is still the band cap (so reviewers can see
        # that the cohort had reasonable n but no detectable lift).
        return (band_cap, "NO_SIGNAL_FOUND")

    evidence = _classify_within_band_cap(
        _BandInputs(
            n_complete=n_complete,
            lift_absolute=lift_absolute,
            ci_excludes_baseline=ci_excludes_baseline,
            direction=direction,
        ),
        band_cap,
        thresholds,
    )

    action: ActionClass
    if direction == "loosen":
        # Hard cap per spec L6 -- loosen is never ADVANCE_AS_CANDIDATE.
        action = "HOLD_OBSERVE_ONLY"
    elif evidence == "strong" and direction == "tighten":
        action = "ADVANCE_AS_CANDIDATE"
    else:
        action = "HOLD_OBSERVE_ONLY"

    return (evidence, action)


# ---------------------------------------------------------------------------
# Confidence-flag ceiling
# ---------------------------------------------------------------------------


def apply_confidence_ceiling(
    evidence: EvidenceClass,
    action: ActionClass,
    confidence_flag: str | None,
    direction: Direction,
) -> tuple[EvidenceClass, ActionClass, bool]:
    """Cap evidence_class at "moderate" when upstream confidence is low.

    Per spec L13, when Stage 12's confidence_flag is the low sentinel,
    Stage 13's evidence_class is bounded above by "moderate". Strong
    cohorts therefore drop to moderate AND, by knock-on, their
    ADVANCE_AS_CANDIDATE downgrades to HOLD_OBSERVE_ONLY.

    Returns ``(evidence, action, confidence_ceiling_applied)``.
    """

    if confidence_flag != CONFIDENCE_FLAG_LOW_SENTINEL:
        return (evidence, action, False)
    if evidence != "strong":
        # Already at-or-below moderate. Flag is informational but
        # doesn't actually constrain anything for this row.
        return (evidence, action, True)

    new_evidence: EvidenceClass = "moderate"
    if action == "ADVANCE_AS_CANDIDATE":
        new_action: ActionClass = "HOLD_OBSERVE_ONLY"
    else:
        new_action = action
    return (new_evidence, new_action, True)


# ---------------------------------------------------------------------------
# Censoring downgrade
# ---------------------------------------------------------------------------


def apply_censoring_downgrade(
    evidence: EvidenceClass,
    action: ActionClass,
    censoring_rate: float | None,
    thresholds: EvidenceThresholds,
) -> tuple[EvidenceClass, ActionClass, bool]:
    """Downgrade one notch when censoring_rate exceeds the warn threshold.

    strong   -> moderate
    moderate -> weak

    Per spec §CENSORING DOWNGRADE, NULL censoring_rate (denominator
    zero) does not trigger a downgrade. The boolean third element of
    the return tuple is ``censoring_warning_flag``.

    A downgrade from "strong" carries a knock-on ADVANCE -> HOLD
    transition, since ADVANCE requires strong tighten.
    """

    if censoring_rate is None:
        return (evidence, action, False)
    if censoring_rate <= thresholds.censoring_warn_threshold:
        return (evidence, action, False)

    if evidence == "strong":
        new_evidence: EvidenceClass = "moderate"
        new_action: ActionClass = (
            "HOLD_OBSERVE_ONLY"
            if action == "ADVANCE_AS_CANDIDATE"
            else action
        )
        return (new_evidence, new_action, True)
    if evidence == "moderate":
        return ("weak", action, True)
    return (evidence, action, True)


# ---------------------------------------------------------------------------
# Anomaly overrides
# ---------------------------------------------------------------------------


def apply_anomaly_overrides(
    *,
    cohort_rate: float | None,
    baseline_rate: float | None,
    action: ActionClass,
    direction: Direction,
) -> tuple[ActionClass, Direction, list[str], bool]:
    """Apply anomaly triggers that override all other action classes.

    Triggers per spec §ANOMALY TRIGGERS (the cross-tier overall checks
    are handled separately in ``apply_per_tier_override``):

      - cohort_rate is exactly 0.0 or exactly 1.0
      - baseline_rate is exactly 0.0
        (lift_relative is NULL, direction is none, notes include
        "baseline_rate_zero")

    Returns ``(action, direction, notes, anomaly_triggered)``. ``notes``
    is a list of textual annotations the caller should merge into the
    row's ``notes`` field.
    """

    notes: list[str] = []
    anomaly = False

    if baseline_rate is not None and baseline_rate == 0.0:
        notes.append("baseline_rate_zero")
        anomaly = True

    if cohort_rate is not None and (cohort_rate == 0.0 or cohort_rate == 1.0):
        notes.append(
            f"cohort_rate_extreme:{cohort_rate}"
        )
        anomaly = True

    if anomaly:
        return ("ANOMALY_FLAG", "none", notes, True)
    return (action, direction, notes, False)


# ---------------------------------------------------------------------------
# Per-tier override rule for overall cohorts
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _TierSupportSummary:
    """Per-tier classification roll-up for one overall cohort_id.

    ``advance_directions`` holds the set of directions for which the
    cohort has at least one ADVANCE_AS_CANDIDATE per-tier row.
    ``non_blocking_only`` is True when every per-tier row is in
    {NO_SIGNAL_FOUND, INSUFFICIENT_EVIDENCE}.
    """

    advance_directions: dict[Direction, list[str]]
    non_blocking_only: bool
    direction_set: set[Direction]
    any_present: bool


def summarize_tier_support(
    cohort_id: str,
    per_tier_rows: list[dict[str, object]],
) -> _TierSupportSummary:
    """Roll up per-tier classifications for one cohort_id.

    ``per_tier_rows`` is a list of dicts with keys ``cohort_id``,
    ``tier_scope``, ``action_class``, ``direction``. Only rows whose
    ``cohort_id`` matches are considered.

    The returned summary is used by ``apply_per_tier_override``.
    """

    advance: dict[Direction, list[str]] = {}
    direction_set: set[Direction] = set()
    non_blocking_count = 0
    relevant_count = 0
    matched = False

    for row in per_tier_rows:
        if row.get("cohort_id") != cohort_id:
            continue
        matched = True
        relevant_count += 1
        action = row.get("action_class")
        direction = row.get("direction")
        if action in ("NO_SIGNAL_FOUND", "INSUFFICIENT_EVIDENCE"):
            non_blocking_count += 1
        if action == "ADVANCE_AS_CANDIDATE" and isinstance(direction, str):
            advance.setdefault(direction, []).append(  # type: ignore[arg-type]
                str(row.get("tier_scope"))
            )
        if isinstance(direction, str) and direction in ("tighten", "loosen"):
            direction_set.add(direction)  # type: ignore[arg-type]

    non_blocking_only = matched and non_blocking_count == relevant_count
    return _TierSupportSummary(
        advance_directions=advance,
        non_blocking_only=non_blocking_only,
        direction_set=direction_set,
        any_present=matched,
    )


def apply_per_tier_override(
    *,
    overall_action: ActionClass,
    overall_direction: Direction,
    overall_notes: list[str],
    tier_support: _TierSupportSummary,
) -> tuple[ActionClass, Direction, list[str], list[str], bool]:
    """Resolve an overall row's standalone classification against its
    per-tier siblings.

    Returns ``(action, direction, notes, tier_evidence_support,
    cross_tier_disagreement)``.

    Rules per spec §PER-TIER OVERRIDE RULE:

      * If overall == ADVANCE_AS_CANDIDATE and at least one per-tier row
        is ADVANCE_AS_CANDIDATE with the same direction, the overall row
        stays ADVANCE_AS_CANDIDATE; tier_evidence_support is populated.

      * Else if overall == ADVANCE_AS_CANDIDATE and all per-tier rows
        are NO_SIGNAL_FOUND/INSUFFICIENT_EVIDENCE, downgrade to
        ANOMALY_FLAG with a "pooling artifact" note.

      * Else if overall == ADVANCE_AS_CANDIDATE with no matching tier
        advance, downgrade to HOLD_OBSERVE_ONLY with a note.

      * If any per-tier row direction disagrees with the overall
        direction (tighten vs. loosen), set cross_tier_disagreement and
        promote action to ANOMALY_FLAG.

    Note: the spec's "direction disagreement" check applies regardless
    of the overall action class. It is checked after the advance-
    resolution branch so the resulting notes are stacked cleanly.
    """

    notes = list(overall_notes)
    action: ActionClass = overall_action
    direction: Direction = overall_direction
    tier_evidence_support: list[str] = []

    if action == "ADVANCE_AS_CANDIDATE":
        supporting_tiers = tier_support.advance_directions.get(direction, [])
        if supporting_tiers:
            tier_evidence_support = list(supporting_tiers)
        elif tier_support.non_blocking_only and tier_support.any_present:
            action = "ANOMALY_FLAG"
            direction = "none"
            notes.append(
                "pooling artifact: overall finding not supported by any "
                "individual tier"
            )
        else:
            action = "HOLD_OBSERVE_ONLY"
            notes.append(
                "overall advance downgraded: no matching per-tier advance "
                "support"
            )

    cross_tier_disagreement = False
    if direction in ("tighten", "loosen"):
        opposite: Direction = "loosen" if direction == "tighten" else "tighten"
        if opposite in tier_support.direction_set:
            cross_tier_disagreement = True
            action = "ANOMALY_FLAG"
            notes.append(
                "cross-tier disagreement: per-tier directions conflict with "
                "overall direction"
            )

    return (action, direction, notes, tier_evidence_support, cross_tier_disagreement)


# ---------------------------------------------------------------------------
# Convenience: censoring-rate helper
# ---------------------------------------------------------------------------


def compute_censoring_rate(
    n_complete: int,
    n_censored: int,
) -> float | None:
    """Return n_censored / (n_complete + n_censored).

    Returns ``None`` when the denominator is zero (spec §CENSORING
    DOWNGRADE). Both inputs are integer counts.
    """

    denom = n_complete + n_censored
    if denom == 0:
        return None
    return n_censored / denom

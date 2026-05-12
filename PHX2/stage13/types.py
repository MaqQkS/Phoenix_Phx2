"""Stage 13 type definitions.

Locked vocabularies are expressed as ``typing.Literal`` aliases so
classifier code and writers can be statically checked against the
allowed string values. The shared ``RecommendationRow`` dataclass is
the in-memory representation of one cohort recommendation; the writer
flattens it into the locked CSV column order.

Stage 13 emits direction + cohort identity only. No threshold values
appear on any RecommendationRow.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


# ---------------------------------------------------------------------------
# Locked string vocabularies (spec §OUTPUT ARTIFACTS - Allowed values)
# ---------------------------------------------------------------------------


PolicySurface = Literal[
    "filter_label_blocking",
    "primitive_bucket_cohort",
]


TierScope = Literal["overall", "T1", "T2", "T3"]


ActionClass = Literal[
    "ADVANCE_AS_CANDIDATE",
    "HOLD_OBSERVE_ONLY",
    "NO_SIGNAL_FOUND",
    "INSUFFICIENT_EVIDENCE",
    "ANOMALY_FLAG",
]


Direction = Literal["tighten", "loosen", "none"]


EvidenceClass = Literal["strong", "moderate", "weak", "insufficient"]


PolicySeverity = Literal["low", "medium", "high", "unknown"]


ReviewPriority = Literal["urgent", "high", "normal", "low"]


# ---------------------------------------------------------------------------
# Evidence thresholds (n-band, lift, censoring, alpha)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EvidenceThresholds:
    """N-band boundaries, lift floors, censoring warn level, Wilson alpha.

    The default values are the locked v0 spec values. Tests may
    construct alternative instances to exercise edge cases, but the
    default is the only one written into the manifest at run time.
    """

    insufficient_below: int = 10
    weak_below: int = 20
    moderate_below: int = 30
    lift_moderate_min: float = 0.05
    lift_strong_min: float = 0.10
    censoring_warn_threshold: float = 0.30
    wilson_alpha: float = 0.05

    def to_manifest_dict(self) -> dict[str, object]:
        """Render the evidence-review parameters into a manifest dict.

        The returned shape matches the locked ``evidence_thresholds``
        section of the Stage 13 manifest (spec §OUTPUT ARTIFACTS).
        These values describe how Stage 13 bucketed cohorts for this
        review run; they are NOT live alert-policy thresholds and NOT
        recommended threshold values for any future policy mutation.
        """

        return {
            "n_bands": {
                "insufficient_below": self.insufficient_below,
                "weak_below": self.weak_below,
                "moderate_below": self.moderate_below,
            },
            "lift_moderate_min": self.lift_moderate_min,
            "lift_strong_min": self.lift_strong_min,
            "censoring_warn_threshold": self.censoring_warn_threshold,
            "wilson_alpha": self.wilson_alpha,
        }


# ---------------------------------------------------------------------------
# Locked label list: scam-adjacent cohort identities (module-level constant)
# ---------------------------------------------------------------------------


SCAM_ADJACENT_LABELS: tuple[str, ...] = (
    "fee_gate_v1.scam_likely",
    "fee_gate.scam_likely",
    "scam_likely",
)
"""Default scam-adjacent label list (spec §SCAM-ADJACENT LABEL LIST).

A finding whose ``cohort_id`` matches any entry here AND is an
ADVANCE_AS_CANDIDATE is escalated to ``urgent`` review priority,
regardless of policy_severity. Absent labels are silently treated as
"no scam-adjacent cohorts found this run" -- the list is documented in
the markdown methodology section.
"""


# ---------------------------------------------------------------------------
# Recommendation row (in-memory shape)
# ---------------------------------------------------------------------------


@dataclass
class RecommendationRow:
    """One classified cohort row.

    The shape mirrors the locked CSV column order in spec §OUTPUT
    ARTIFACTS exactly. ``baseline_rate`` may be ``None`` when the
    baseline is unresolvable (anomaly path); numeric columns may be
    ``None`` to denote NULL (rendered as empty string in CSV).
    """

    policy_surface: PolicySurface
    cohort_id: str
    tier_scope: TierScope
    action_class: ActionClass
    direction: Direction
    evidence_class: EvidenceClass
    policy_severity: PolicySeverity
    review_priority: ReviewPriority
    n_complete: int
    n_censored: int
    cohort_rate: float | None
    baseline_rate: float | None
    lift_absolute: float | None
    lift_relative: float | None
    wilson_ci_low: float | None
    wilson_ci_high: float | None
    ci_excludes_baseline: bool | None
    censoring_rate: float | None
    censoring_warning_flag: bool
    watchlist_flag: bool
    tier_evidence_support: list[str] = field(default_factory=list)
    cross_tier_disagreement: bool = False
    loosen_capped_flag: bool = False
    confidence_ceiling_applied: bool = False
    notes: list[str] = field(default_factory=list)

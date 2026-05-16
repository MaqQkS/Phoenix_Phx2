"""Stage 20.2 aggregated local-warning record (NamedTuple).

Only the locally-detected warnings live on this record. Upstream
warnings (W2001, W2004, W2005) are surfaced through
``validate_inputs``' ``ValidationResult.warnings`` and are NOT
re-detected nor re-stored here.

Local warnings (detected inside Stage 20.2):

  * W2002 -- preview_eligible_count_zero (bool). Fires when the
    run's PREVIEW_ELIGIBLE count is exactly zero. Does NOT mutate
    any candidate's preview_state.

  * W2006 -- candidate_review_stale (int). Count of candidates
    whose review_age_days > 30. The per-row indicator lives on
    ``PreviewCandidate.review_stale``; this is the aggregate
    count surfaced in the manifest.

  * W2007 -- eligibility_mapping_drift_detected (bool). Fires
    only when a ``prior_stage20_manifest_path`` was supplied to
    ``run_stage20_2`` AND its ``mapping_version`` or its
    ``label_mapping`` object differs from the current run's. If no
    prior manifest is provided, W2007 cannot fire.

None of these warnings alter any candidate's preview_state. They
are informational signals surfaced in manifest.warnings and the
README's active-warnings block.
"""

from __future__ import annotations

from typing import NamedTuple


class RunWarnings(NamedTuple):
    """Aggregated locally-detected warning state for one Stage 20.2 run."""

    w2002_preview_eligible_count_zero: bool
    w2006_candidate_review_stale_count: int
    w2007_eligibility_mapping_drift_detected: bool


__all__ = ["RunWarnings"]

"""Stage 20 DecisionStep model shape (NamedTuple).

Shape declaration only -- 20.2 will emit ordered DecisionStep
records as an audit trail per PreviewCandidate, documenting how
the candidate's terminal eligibility_state was reached from its
operator review label.

Field provenance:

  * candidate_id   -- foreign key to PreviewCandidate.
  * step_index     -- 0-based index within the decision trail
                      for this candidate. Each (candidate_id,
                      step_index) pair is unique within a Stage
                      20 run; E2015 catches collisions in 20.2.
  * step_name      -- a short identifier for the rule applied
                      (e.g. "label_mapped", "observe_only_clamp",
                      "evidence_present").
  * input_state    -- the PreviewEligibilityState entering this
                      step (string form).
  * output_state   -- the PreviewEligibilityState exiting this
                      step (string form).
  * is_terminating -- True for exactly one step per candidate
                      (the final step); E2016 catches zero or
                      multiple terminating steps in 20.2.
  * reason_code    -- one of REASON_CODE_* from
                      PHX2.stage20.constants.
"""

from __future__ import annotations

from typing import NamedTuple


class DecisionStep(NamedTuple):
    """One step in the eligibility-state decision trail for a candidate."""

    candidate_id: str
    step_index: int
    step_name: str
    input_state: str
    output_state: str
    is_terminating: bool
    reason_code: str


__all__ = ["DecisionStep"]

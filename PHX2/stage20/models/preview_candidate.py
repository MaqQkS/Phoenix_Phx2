"""Stage 20 PreviewCandidate model shape (NamedTuple).

Shape declaration only -- 20.2 will build instances from
validated Stage 18 evidence rows joined with Stage 19 ledger
rows. 20.1 declares the shape so downstream phases can reference
a stable type.

Field provenance:

  * candidate_id            -- 16-hex SHA-256 prefix over the
                               slice key + operator id (20.2
                               derivation).
  * stage18_run_id          -- from Stage 19 ledger row.
  * stage19_run_id          -- from Stage 19 ledger row.
  * policy_hash, rule_id,
    window_seconds          -- Stage 18 / Stage 19 slice key.
  * operator_id             -- from Stage 19 ledger row.
  * review_sequence         -- max review_sequence for this
                               (slice, operator) pair.
  * review_label            -- the operator's review label at
                               max review_sequence.
  * review_timestamp_utc    -- the run-level timestamp from the
                               Stage 19 run whose ledger row is
                               selected.
  * eligibility_state       -- one of PreviewEligibilityState
                               values, derived by applying
                               LABEL_TO_STATE_MAPPING_V0.
  * stage18_classification  -- Stage 18's classification at the
                               slice (from Stage 19 ledger).
  * stage17_label_preserved -- Stage 17's original label at the
                               slice (Stage 18 carried it
                               verbatim through Stage 19).
  * safe_for_live_dispatch  -- always False in Stage 20 v0.
  * tier_hint               -- optional hint for downstream
                               consumers ("single_tier_only",
                               "multi_tier", etc.); empty when
                               unset.
  * reason_code             -- one of REASON_CODE_* constants
                               from PHX2.stage20.constants
                               documenting WHY the candidate
                               landed in its eligibility state.
"""

from __future__ import annotations

from typing import NamedTuple


class PreviewCandidate(NamedTuple):
    """One preview-eligibility decision per (slice, operator) pair."""

    candidate_id: str
    stage18_run_id: str
    stage19_run_id: str
    policy_hash: str
    rule_id: str
    window_seconds: int
    operator_id: str
    review_sequence: int
    review_label: str
    review_timestamp_utc: str
    eligibility_state: str
    stage18_classification: str
    stage17_label_preserved: str
    safe_for_live_dispatch: bool
    tier_hint: str
    reason_code: str


__all__ = ["PreviewCandidate"]

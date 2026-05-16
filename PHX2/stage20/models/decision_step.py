"""Stage 20 DecisionStep model shape (NamedTuple).

20.1 declared the original 7-field shape. 20.2 EXTENDS this
additively per the operator's model-handling decision: every 20.1
field is preserved verbatim (no renames), and the 20.2-specific
fields are appended.

CSV emission is driven by the locked column tuple
``ALERT_ELIGIBILITY_DECISIONS_CSV_COLUMNS`` in
``PHX2.stage20.constants``, NOT by iterating
``DecisionStep._fields``. The CSV column names use ``decision_*``
prefixes (``decision_step_index``, ``decision_step_name``,
``decision_step_state``, ``decision_step_terminating``) while the
20.1 model fields use the un-prefixed names (``step_index``,
``step_name``, ``input_state``/``output_state``, ``is_terminating``).
Per operator Phase B constraint #3, BOTH the legacy 20.1 fields
and matching 20.2-named alias fields are present on the model;
``build_decision_sequence`` populates each pair with consistent
values (e.g. ``step_index == decision_step_index``). The locked
CSV column tuple therefore maps 1:1 to model fields (no CSV-layer
aliasing).

Field provenance:

  20.1-era (preserved):
    * candidate_id   -- foreign key to PreviewCandidate.
    * step_index     -- 0-based contiguous index. CSV column
                        ``decision_step_index``. Uniqueness within
                        a candidate enforced by E2015 detector.
    * step_name      -- locked vocabulary value. CSV column
                        ``decision_step_name``. One of
                        ``DECISION_STEP_NAMES_4`` (or _2 for the
                        fallback chain not shipped in 20.2).
    * input_state    -- PreviewEligibilityState string entering the
                        step. Held for shape continuity; not
                        emitted to CSV in 20.2.
    * output_state   -- PreviewEligibilityState string exiting the
                        step. Held for shape continuity; not
                        emitted to CSV in 20.2.
    * is_terminating -- bool. CSV column
                        ``decision_step_terminating`` (serialized
                        "true"/"false"). Exactly one terminating
                        row per candidate (E2016).
    * reason_code    -- one of REASON_CODE_* from
                        ``PHX2.stage20.constants``.

  20.2-era (additive, no rename of any 20.1 field):
    * decision_id        -- "dec_" + 16-hex SHA-256 prefix (see
                            ``PHX2.stage20.ids.derive_decision_id``).
    * stage20_run_id     -- the run id this decision row was
                            produced under.
    * decision_step_state -- one of DECISION_STEP_STATES
                            ("entered"|"passed"|"failed"|"terminal").
                            CSV column same name.
    * decision_outcome   -- empty string on non-terminating rows;
                            equal to candidate.preview_state on the
                            terminating row. E2017 catches mismatch.
    * evidence_code      -- E-code or W-code attached to this step,
                            or "" if none.
    * evidence_detail    -- short single-line string (no newlines).
                            "" if none.

  20.2 alias fields (per operator Phase B constraint #3 -- both
  legacy and 20.2-named field must be present, populated
  consistently by ``build_decision_sequence``):
    * decision_step_index       -- int, equals ``step_index``.
    * decision_step_name        -- str, equals ``step_name``.
    * decision_step_terminating -- bool, equals ``is_terminating``.
"""

from __future__ import annotations

from typing import NamedTuple


class DecisionStep(NamedTuple):
    """One step in the eligibility-state decision trail for a candidate."""

    # ----------------------------------------------------------------
    # 20.1 fields (preserved verbatim per operator model decision)
    # ----------------------------------------------------------------
    candidate_id: str
    step_index: int
    step_name: str
    input_state: str
    output_state: str
    is_terminating: bool
    reason_code: str

    # ----------------------------------------------------------------
    # 20.2 additive fields
    # ----------------------------------------------------------------
    decision_id: str
    stage20_run_id: str
    decision_step_state: str
    decision_outcome: str
    evidence_code: str
    evidence_detail: str
    # ----------------------------------------------------------------
    # 20.2 alias fields (operator Phase B constraint #3):
    # populated consistently with their legacy counterparts above.
    # ----------------------------------------------------------------
    decision_step_index: int
    decision_step_name: str
    decision_step_terminating: bool


__all__ = ["DecisionStep"]

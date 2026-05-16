"""Stage 20 PreviewCandidate model shape (NamedTuple).

20.1 declared the original 16-field shape (slice + operator + label
+ mapped state + safety). 20.2 EXTENDS this additively per the
operator's model-handling decision: every 20.1 field is preserved
verbatim (no renames), and the 20.2-specific fields are appended.

CSV emission is driven by the locked column tuple
``PREVIEW_CANDIDATES_CSV_COLUMNS`` in ``PHX2.stage20.constants``,
NOT by iterating ``PreviewCandidate._fields``. That tuple maps the
locked external column order to the model field names. Any field on
this NamedTuple that does NOT appear in the column tuple is held
for internal use only (e.g. ``safe_for_live_dispatch`` is a per-row
invariant flag, not a CSV column).

Field provenance:

  20.1-era (preserved):
    * candidate_id            -- 16-hex SHA-256 prefix (see
                                 ``PHX2.stage20.ids.derive_candidate_id``).
    * stage18_run_id          -- from Stage 19 ledger row.
    * stage19_run_id          -- from Stage 19 ledger row.
    * policy_hash, rule_id,
      window_seconds          -- Stage 18 / Stage 19 slice key.
    * operator_id             -- from Stage 19 ledger row.
    * review_sequence         -- max review_sequence for this
                                 (slice, operator) pair.
    * review_label            -- operator's review label at the
                                 winning review_sequence.
    * review_timestamp_utc    -- run-level timestamp from the
                                 Stage 19 invocation that produced
                                 the winning ledger row.
    * eligibility_state       -- one of PreviewEligibilityState
                                 values, derived by applying
                                 LABEL_TO_STATE_MAPPING_V0. CSV
                                 column ``preview_state`` reads
                                 this field.
    * stage18_classification  -- Stage 18's classification at the
                                 slice (from Stage 19 ledger).
    * stage17_label_preserved -- Stage 17's original label at the
                                 slice (carried verbatim).
    * safe_for_live_dispatch  -- always False in v0. Not emitted to
                                 the candidate CSV; the manifest
                                 carries the run-level invariant.
    * tier_hint               -- always empty string in v0 (no
                                 derivation source exists upstream).
    * reason_code             -- one of REASON_CODE_* from
                                 ``PHX2.stage20.constants``.

  20.2-era (additive, no rename of any 20.1 field):
    * stage20_run_id              -- the run id this candidate was
                                     produced under.
    * source_ledger_row_id        -- ledger_row_id of the winning
                                     Stage 19 row. CSV column same
                                     name.
    * mapping_version             -- MAPPING_VERSION at run time
                                     (= "v0").
    * review_age_days             -- int days from clock.now() to
                                     parsed review_timestamp_utc;
                                     -1 if parse fails.
    * review_stale                -- bool; CSV serializes "true"/
                                     "false". True iff
                                     review_age_days > 30.
    * multiple_operators_for_slice -- bool; CSV "true"/"false".
                                     True iff the slice's ledger
                                     rows contain >=2 distinct
                                     operator_id values.
    * notes                       -- always "" in v0. Reserved
                                     surface for future per-row
                                     annotations.
    * preview_state               -- 20.2 alias of ``eligibility_state``.
                                     Operator constraint (Phase B):
                                     build_candidate populates BOTH
                                     fields with the same
                                     PreviewEligibilityState value
                                     so the legacy and 20.2-aligned
                                     names stay consistent. The
                                     locked CSV column
                                     ``preview_state`` reads this
                                     field directly (no CSV-layer
                                     aliasing).
"""

from __future__ import annotations

from typing import NamedTuple


class PreviewCandidate(NamedTuple):
    """One preview-eligibility decision per (slice, operator) pair."""

    # ----------------------------------------------------------------
    # 20.1 fields (preserved verbatim per operator model decision)
    # ----------------------------------------------------------------
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

    # ----------------------------------------------------------------
    # 20.2 additive fields
    # ----------------------------------------------------------------
    stage20_run_id: str
    source_ledger_row_id: str
    mapping_version: str
    review_age_days: int
    review_stale: bool
    multiple_operators_for_slice: bool
    notes: str
    # ----------------------------------------------------------------
    # 20.2 alias of the 20.1 ``eligibility_state`` field (operator
    # Phase B constraint #2). build_candidate populates both with
    # the same PreviewEligibilityState string value.
    # ----------------------------------------------------------------
    preview_state: str


__all__ = ["PreviewCandidate"]

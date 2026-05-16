"""Stage 20.2 builder tests (Phase B).

Covers:
  * Mapping correctness for all 6 LABEL_TO_STATE_MAPPING_V0 entries.
  * Slice resolution + winning-row selection (review_sequence,
    ledger_row_id tiebreak).
  * Multi-operator-per-slice detection (boolean on PreviewCandidate;
    upstream W2004 surfacing tested separately).
  * Decision chain invariants (contiguous indices, one terminating
    row, terminating outcome matches candidate.preview_state).
  * Alias-pair consistency (operator constraints #2, #3).
  * E2011 / E2015 / E2016 / E2017 negative coverage.
  * Closed-set mapping invariant (unknown label -> ValueError).

Test fixtures synthesize Stage 19 ledger rows as plain dicts -- no
real Stage 18/19 data is used and no Stage 18/19 imports are
required.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest

from PHX2.stage20 import builder
from PHX2.stage20.builder import (
    build_all_candidates,
    build_candidate,
    build_decision_sequence,
    resolve_slices,
    select_winning_row,
    validate_candidate_id_uniqueness,
    validate_decision_sequences,
)
from PHX2.stage20.clock import FrozenClock
from PHX2.stage20.constants import (
    DECISION_STEP_NAMES_4,
    LABEL_TO_STATE_MAPPING_V0,
    MAPPING_VERSION,
    PreviewEligibilityState,
)
from PHX2.stage20.errors import Stage20ValidationError
from PHX2.stage20.input_validators import ValidationResult
from PHX2.stage20.models import DecisionStep, PreviewCandidate, RunWarnings


# Frozen reference clock for deterministic age computation.
_FROZEN_NOW = datetime(2026, 5, 15, 0, 0, 0, tzinfo=timezone.utc)


def _frozen_clock() -> FrozenClock:
    return FrozenClock(_FROZEN_NOW)


def _ts(days_ago: int) -> str:
    """Compose a Stage-19-formatted UTC timestamp at offset days_ago."""

    from datetime import timedelta

    dt = _FROZEN_NOW - timedelta(days=days_ago)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _ledger_row(
    *,
    review_label: str = "REVIEW_PROMISING_CONFIRMED",
    review_sequence: str = "1",
    ledger_row_id: str = "lrid_a",
    stage18_run_id: str = "s18_run_a",
    stage19_run_id: str = "s19_run_a",
    policy_hash: str = "ph_a",
    rule_id: str = "rule_a",
    window_seconds: str = "30",
    operator_id: str = "op_a",
    review_timestamp_utc: str = "2026-05-15T00:00:00Z",
    stage18_classification: str = "CLASS_A",
    stage17_label_preserved: str = "LABEL_A",
    review_notes: str = "",
) -> dict[str, str]:
    return {
        "stage19_run_id": stage19_run_id,
        "ledger_row_id": ledger_row_id,
        "stage18_run_id": stage18_run_id,
        "policy_hash": policy_hash,
        "rule_id": rule_id,
        "window_seconds": window_seconds,
        "operator_id": operator_id,
        "review_sequence": review_sequence,
        "review_label": review_label,
        "review_notes": review_notes,
        "review_timestamp_utc": review_timestamp_utc,
        "stage18_classification": stage18_classification,
        "stage17_label_preserved": stage17_label_preserved,
    }


def _empty_validation_result() -> ValidationResult:
    return ValidationResult(
        ok=True,
        errors=(),
        warnings=(),
        summary={},
    )


# ---------------------------------------------------------------------------
# 1. Mapping correctness -- every label produces the locked state
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "review_label, expected_state",
    [
        ("REVIEW_PROMISING_CONFIRMED",
         PreviewEligibilityState.PREVIEW_ELIGIBLE.value),
        ("WATCHLIST",
         PreviewEligibilityState.PREVIEW_OBSERVE_ONLY.value),
        ("NEEDS_MORE_DATA",
         PreviewEligibilityState.PREVIEW_NEEDS_MORE_DATA.value),
        ("INCONCLUSIVE",
         PreviewEligibilityState.PREVIEW_NEEDS_MORE_DATA.value),
        ("REVIEW_HARMFUL_CONFIRMED",
         PreviewEligibilityState.PREVIEW_EXCLUDED.value),
        ("REVIEW_REJECTED",
         PreviewEligibilityState.PREVIEW_EXCLUDED.value),
    ],
)
def test_each_label_maps_to_expected_state(
    review_label: str, expected_state: str,
):
    row = _ledger_row(review_label=review_label)
    candidate = build_candidate(
        row, [row], clock=_frozen_clock(),
        stage20_run_id="stage20_test",
    )
    assert candidate.eligibility_state == expected_state
    assert candidate.preview_state == expected_state
    # Operator constraint #2: alias pair carries identical value.
    assert candidate.eligibility_state == candidate.preview_state


# ---------------------------------------------------------------------------
# 2-6. Slice resolution + winning row selection
# ---------------------------------------------------------------------------


def test_single_operator_single_review_one_candidate():
    rows = [_ledger_row()]
    candidates, decisions, _w = build_all_candidates(
        _empty_validation_result(), rows,
        clock=_frozen_clock(), stage20_run_id="stage20_test",
        stage19_run_id="s19_run_a",
    )
    assert len(candidates) == 1
    assert len(decisions) == 4
    assert candidates[0].multiple_operators_for_slice is False


def test_single_operator_multi_review_winning_is_max_review_sequence():
    rows = [
        _ledger_row(review_sequence="1", ledger_row_id="r1"),
        _ledger_row(review_sequence="5", ledger_row_id="r2",
                    review_label="WATCHLIST"),
        _ledger_row(review_sequence="3", ledger_row_id="r3"),
    ]
    candidates, _decs, _w = build_all_candidates(
        _empty_validation_result(), rows,
        clock=_frozen_clock(), stage20_run_id="stage20_test",
        stage19_run_id="s19_run_a",
    )
    assert len(candidates) == 1
    assert candidates[0].review_sequence == 5
    assert candidates[0].source_ledger_row_id == "r2"
    assert candidates[0].preview_state == \
        PreviewEligibilityState.PREVIEW_OBSERVE_ONLY.value


def test_multi_operator_multi_review_one_candidate_flag_set():
    rows = [
        _ledger_row(operator_id="op_a", review_sequence="1",
                    ledger_row_id="r1"),
        _ledger_row(operator_id="op_b", review_sequence="2",
                    ledger_row_id="r2"),
    ]
    candidates, _decs, _w = build_all_candidates(
        _empty_validation_result(), rows,
        clock=_frozen_clock(), stage20_run_id="stage20_test",
        stage19_run_id="s19_run_a",
    )
    assert len(candidates) == 1
    c = candidates[0]
    assert c.multiple_operators_for_slice is True
    assert c.operator_id == "op_b"  # winning by review_sequence
    assert c.review_sequence == 2


def test_review_sequence_tie_breaks_by_max_ledger_row_id_string_compare():
    rows = [
        _ledger_row(review_sequence="5", ledger_row_id="rid_aaa"),
        _ledger_row(review_sequence="5", ledger_row_id="rid_zzz"),
        _ledger_row(review_sequence="5", ledger_row_id="rid_mmm"),
    ]
    winner = select_winning_row(rows)
    assert winner["ledger_row_id"] == "rid_zzz"


def test_two_distinct_slices_two_candidates_distinct_ids():
    rows = [
        _ledger_row(policy_hash="ph_a", rule_id="rule_a",
                    window_seconds="30", ledger_row_id="r1"),
        _ledger_row(policy_hash="ph_b", rule_id="rule_b",
                    window_seconds="60", ledger_row_id="r2"),
    ]
    candidates, _decs, _w = build_all_candidates(
        _empty_validation_result(), rows,
        clock=_frozen_clock(), stage20_run_id="stage20_test",
        stage19_run_id="s19_run_a",
    )
    assert len(candidates) == 2
    ids = {c.candidate_id for c in candidates}
    assert len(ids) == 2


# ---------------------------------------------------------------------------
# 7. Mix -- all 6 label mappings populate preview_state_counts correctly
# ---------------------------------------------------------------------------


def test_six_row_mix_produces_all_four_states():
    labels = list(LABEL_TO_STATE_MAPPING_V0.keys())
    rows = [
        _ledger_row(
            review_label=lbl,
            policy_hash=f"ph_{i}",
            rule_id=f"rule_{i}",
            ledger_row_id=f"r{i}",
        )
        for i, lbl in enumerate(labels)
    ]
    candidates, _decs, _w = build_all_candidates(
        _empty_validation_result(), rows,
        clock=_frozen_clock(), stage20_run_id="stage20_test",
        stage19_run_id="s19_run_a",
    )
    by_state: dict[str, int] = {}
    for c in candidates:
        by_state[c.preview_state] = by_state.get(c.preview_state, 0) + 1
    # All four preview states are reachable via the 6-label mapping.
    expected_states = {s.value for s in PreviewEligibilityState}
    assert set(by_state.keys()) == expected_states


# ---------------------------------------------------------------------------
# 8-10. Per-candidate staleness (W2006 per-row indicator)
# ---------------------------------------------------------------------------


def test_review_stale_fires_at_31_days_old():
    row = _ledger_row(review_timestamp_utc=_ts(31))
    candidate = build_candidate(
        row, [row], clock=_frozen_clock(),
        stage20_run_id="stage20_test",
    )
    assert candidate.review_age_days == 31
    assert candidate.review_stale is True


def test_review_stale_false_at_29_days_old():
    row = _ledger_row(review_timestamp_utc=_ts(29))
    candidate = build_candidate(
        row, [row], clock=_frozen_clock(),
        stage20_run_id="stage20_test",
    )
    assert candidate.review_age_days == 29
    assert candidate.review_stale is False


def test_malformed_review_timestamp_emits_minus_one_no_exception():
    row = _ledger_row(review_timestamp_utc="not-a-timestamp")
    candidate = build_candidate(
        row, [row], clock=_frozen_clock(),
        stage20_run_id="stage20_test",
    )
    assert candidate.review_age_days == -1
    assert candidate.review_stale is False


# ---------------------------------------------------------------------------
# 11-13. Empty / all-excluded / mixed -- W2002 firing
# ---------------------------------------------------------------------------


def test_empty_ledger_zero_candidates_w2002_fires():
    candidates, decisions, run_warnings = build_all_candidates(
        _empty_validation_result(), [],
        clock=_frozen_clock(), stage20_run_id="stage20_test",
        stage19_run_id="s19_run_a",
    )
    assert candidates == []
    assert decisions == []
    assert run_warnings.w2002_preview_eligible_count_zero is True


def test_all_rejected_all_excluded_w2002_fires():
    rows = [
        _ledger_row(review_label="REVIEW_REJECTED",
                    policy_hash="ph_a", ledger_row_id="r1"),
        _ledger_row(review_label="REVIEW_HARMFUL_CONFIRMED",
                    policy_hash="ph_b", ledger_row_id="r2"),
    ]
    candidates, _decs, run_warnings = build_all_candidates(
        _empty_validation_result(), rows,
        clock=_frozen_clock(), stage20_run_id="stage20_test",
        stage19_run_id="s19_run_a",
    )
    assert len(candidates) == 2
    assert all(
        c.preview_state == PreviewEligibilityState.PREVIEW_EXCLUDED.value
        for c in candidates
    )
    assert run_warnings.w2002_preview_eligible_count_zero is True


def test_at_least_one_promising_w2002_does_not_fire():
    rows = [
        _ledger_row(review_label="REVIEW_PROMISING_CONFIRMED",
                    policy_hash="ph_a", ledger_row_id="r1"),
        _ledger_row(review_label="REVIEW_REJECTED",
                    policy_hash="ph_b", ledger_row_id="r2"),
    ]
    _cands, _decs, run_warnings = build_all_candidates(
        _empty_validation_result(), rows,
        clock=_frozen_clock(), stage20_run_id="stage20_test",
        stage19_run_id="s19_run_a",
    )
    assert run_warnings.w2002_preview_eligible_count_zero is False


# ---------------------------------------------------------------------------
# 14-16. Decision chain invariants
# ---------------------------------------------------------------------------


def test_decision_step_index_is_contiguous_zero_through_three():
    row = _ledger_row()
    candidate = build_candidate(
        row, [row], clock=_frozen_clock(),
        stage20_run_id="stage20_test",
    )
    steps = build_decision_sequence(
        candidate, stage20_run_id="stage20_test",
    )
    assert [s.step_index for s in steps] == [0, 1, 2, 3]
    assert [s.decision_step_index for s in steps] == [0, 1, 2, 3]


def test_exactly_one_terminating_row_per_candidate():
    row = _ledger_row()
    candidate = build_candidate(
        row, [row], clock=_frozen_clock(),
        stage20_run_id="stage20_test",
    )
    steps = build_decision_sequence(
        candidate, stage20_run_id="stage20_test",
    )
    terminating = [s for s in steps if s.is_terminating]
    assert len(terminating) == 1
    assert terminating[0].step_name == "terminal"
    assert terminating[0].decision_step_terminating is True


def test_terminating_outcome_matches_candidate_preview_state():
    row = _ledger_row(review_label="WATCHLIST")
    candidate = build_candidate(
        row, [row], clock=_frozen_clock(),
        stage20_run_id="stage20_test",
    )
    steps = build_decision_sequence(
        candidate, stage20_run_id="stage20_test",
    )
    term = next(s for s in steps if s.is_terminating)
    assert term.decision_outcome == candidate.preview_state
    assert (
        term.decision_outcome
        == PreviewEligibilityState.PREVIEW_OBSERVE_ONLY.value
    )


def test_decision_step_state_cascade_input_to_output():
    """Operator constraint #4: input_state cascade from previous step."""

    row = _ledger_row()
    candidate = build_candidate(
        row, [row], clock=_frozen_clock(),
        stage20_run_id="stage20_test",
    )
    steps = build_decision_sequence(
        candidate, stage20_run_id="stage20_test",
    )
    # Step 0: empty input, "passed" output.
    assert steps[0].input_state == ""
    assert steps[0].output_state == "passed"
    # Subsequent input_state mirrors prior output_state.
    for i in range(1, len(steps)):
        assert steps[i].input_state == steps[i - 1].output_state
    # Terminal carries "terminal" output.
    assert steps[-1].output_state == "terminal"
    # decision_step_state mirrors output_state.
    for s in steps:
        assert s.decision_step_state == s.output_state


def test_decision_step_alias_pairs_agree():
    """Operator constraint #3: paired fields must agree."""

    row = _ledger_row()
    candidate = build_candidate(
        row, [row], clock=_frozen_clock(),
        stage20_run_id="stage20_test",
    )
    steps = build_decision_sequence(
        candidate, stage20_run_id="stage20_test",
    )
    for s in steps:
        assert s.step_index == s.decision_step_index
        assert s.step_name == s.decision_step_name
        assert s.is_terminating == s.decision_step_terminating


# ---------------------------------------------------------------------------
# 17. Closed-set invariant -- unknown label raises ValueError
# ---------------------------------------------------------------------------


def test_unknown_review_label_raises_value_error_not_silent_excluded():
    row = _ledger_row(review_label="NOT_A_REAL_LABEL")
    with pytest.raises(ValueError, match="LABEL_TO_STATE_MAPPING_V0"):
        build_candidate(
            row, [row], clock=_frozen_clock(),
            stage20_run_id="stage20_test",
        )


# ---------------------------------------------------------------------------
# 18. E2011 -- candidate_id collision (monkeypatch derive_candidate_id)
# ---------------------------------------------------------------------------


def test_e2011_fires_on_candidate_id_collision_post_build(monkeypatch):
    monkeypatch.setattr(
        "PHX2.stage20.builder.derive_candidate_id",
        lambda **_kwargs: "cand_collision_xxxxxxxx",
    )
    rows = [
        _ledger_row(policy_hash="ph_a", rule_id="rule_a",
                    window_seconds="30", ledger_row_id="r1"),
        _ledger_row(policy_hash="ph_b", rule_id="rule_b",
                    window_seconds="60", ledger_row_id="r2"),
    ]
    candidates, _decs, _w = build_all_candidates(
        _empty_validation_result(), rows,
        clock=_frozen_clock(), stage20_run_id="stage20_test",
        stage19_run_id="s19_run_a",
    )
    assert len(candidates) == 2
    # Two distinct slices, but the monkeypatched derive_candidate_id
    # collapses them onto a single id -- post-build validator must
    # flag E2011.
    with pytest.raises(Stage20ValidationError) as exc_info:
        validate_candidate_id_uniqueness(candidates)
    assert "E2011" in str(exc_info.value)
    assert exc_info.value.code == "E2011"


# ---------------------------------------------------------------------------
# 19-21. E2015 / E2016 / E2017 -- synthetic-decision validator coverage
# ---------------------------------------------------------------------------


def _step(
    candidate_id: str,
    step_index: int,
    step_name: str,
    is_terminating: bool,
    decision_outcome: str = "",
    decision_step_state: str = "passed",
) -> DecisionStep:
    return DecisionStep(
        candidate_id=candidate_id,
        step_index=step_index,
        step_name=step_name,
        input_state="",
        output_state=decision_step_state,
        is_terminating=is_terminating,
        reason_code="LABEL_MAPPED_FROM_OPERATOR_REVIEW",
        decision_id=f"dec_{candidate_id}_{step_index}",
        stage20_run_id="stage20_test",
        decision_step_state=decision_step_state,
        decision_outcome=decision_outcome,
        evidence_code="",
        evidence_detail="",
        decision_step_index=step_index,
        decision_step_name=step_name,
        decision_step_terminating=is_terminating,
    )


def _stub_candidate(
    candidate_id: str = "cand_test",
    preview_state: str = "PREVIEW_ELIGIBLE",
) -> PreviewCandidate:
    return PreviewCandidate(
        candidate_id=candidate_id,
        stage18_run_id="s18_a",
        stage19_run_id="s19_a",
        policy_hash="ph_a",
        rule_id="rule_a",
        window_seconds=30,
        operator_id="op_a",
        review_sequence=1,
        review_label="REVIEW_PROMISING_CONFIRMED",
        review_timestamp_utc=_ts(0),
        eligibility_state=preview_state,
        stage18_classification="CLASS_A",
        stage17_label_preserved="LABEL_A",
        safe_for_live_dispatch=False,
        tier_hint="",
        reason_code="LABEL_MAPPED_FROM_OPERATOR_REVIEW",
        stage20_run_id="stage20_test",
        source_ledger_row_id="lrid_a",
        mapping_version=MAPPING_VERSION,
        review_age_days=0,
        review_stale=False,
        multiple_operators_for_slice=False,
        notes="",
        preview_state=preview_state,
    )


def test_e2015_fires_on_duplicate_decision_step_index_within_candidate():
    cand = _stub_candidate("cand_x")
    decisions = [
        _step("cand_x", 0, "slice_resolved", False),
        _step("cand_x", 0, "mapping_applied", False),  # duplicate index
        _step("cand_x", 1, "terminal", True,
              decision_outcome="PREVIEW_ELIGIBLE",
              decision_step_state="terminal"),
    ]
    with pytest.raises(Stage20ValidationError) as exc:
        validate_decision_sequences(decisions, [cand])
    assert exc.value.code == "E2015"
    assert "E2015" in str(exc.value)


def test_e2016_fires_on_zero_terminating_steps():
    cand = _stub_candidate("cand_y")
    decisions = [
        _step("cand_y", 0, "slice_resolved", False),
        _step("cand_y", 1, "mapping_applied", False),
        _step("cand_y", 2, "staleness_evaluated", False),
    ]
    with pytest.raises(Stage20ValidationError) as exc:
        validate_decision_sequences(decisions, [cand])
    assert exc.value.code == "E2016"


def test_e2016_fires_on_candidate_with_zero_decision_rows():
    """Codex remediation: validate_decision_sequences must iterate
    over the candidates list, not the by_candidate dict. A
    candidate with NO decisions at all must still trip E2016.

    Prior bug: the loop walked ``by_candidate.items()``, so a
    candidate that produced zero decision rows would silently
    short-circuit (no entry in the map -> never iterated).
    """

    cand = _stub_candidate("cand_no_decisions")
    decisions: list = []  # empty -- candidate has zero rows
    with pytest.raises(Stage20ValidationError) as exc:
        validate_decision_sequences(decisions, [cand])
    assert exc.value.code == "E2016"
    assert "cand_no_decisions" in str(exc.value)
    # The detail should report 0 terminating rows.
    assert "0 terminating" in str(exc.value)


def test_e2016_fires_on_two_terminating_steps():
    cand = _stub_candidate("cand_z")
    decisions = [
        _step("cand_z", 0, "slice_resolved", False),
        _step("cand_z", 1, "terminal", True,
              decision_outcome="PREVIEW_ELIGIBLE",
              decision_step_state="terminal"),
        _step("cand_z", 2, "terminal", True,
              decision_outcome="PREVIEW_ELIGIBLE",
              decision_step_state="terminal"),
    ]
    with pytest.raises(Stage20ValidationError) as exc:
        validate_decision_sequences(decisions, [cand])
    assert exc.value.code == "E2016"


def test_e2017_fires_on_terminating_outcome_mismatch():
    cand = _stub_candidate("cand_w", preview_state="PREVIEW_ELIGIBLE")
    decisions = [
        _step("cand_w", 0, "slice_resolved", False),
        _step("cand_w", 1, "mapping_applied", False),
        _step("cand_w", 2, "staleness_evaluated", False),
        _step("cand_w", 3, "terminal", True,
              decision_outcome="PREVIEW_EXCLUDED",  # mismatch
              decision_step_state="terminal"),
    ]
    with pytest.raises(Stage20ValidationError) as exc:
        validate_decision_sequences(decisions, [cand])
    assert exc.value.code == "E2017"


def test_validators_pass_on_clean_synthetic_sequence():
    row = _ledger_row()
    candidate = build_candidate(
        row, [row], clock=_frozen_clock(),
        stage20_run_id="stage20_test",
    )
    decisions = build_decision_sequence(
        candidate, stage20_run_id="stage20_test",
    )
    validate_candidate_id_uniqueness([candidate])  # no raise
    validate_decision_sequences(decisions, [candidate])  # no raise

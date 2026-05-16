"""Stage 20.2 model shape tests — CSV column alignment.

Asserts the additive extensions on PreviewCandidate and DecisionStep
fully cover their respective locked CSV column tuples. The CSV
emitter is required to drive header / row order from the locked
``*_CSV_COLUMNS`` constant rather than the NamedTuple field order
(so a future cosmetic field reorder can never reorder the wire
format silently).

Additional assertions:
  * Every CSV column has a corresponding NamedTuple field. The
    converse is NOT required -- PreviewCandidate/DecisionStep may
    carry internal fields (e.g. ``safe_for_live_dispatch``,
    ``input_state``) that are not emitted.
  * NamedTuple field types are correct for the additive 20.2 fields.
  * Construction with all fields succeeds; missing fields fails.
"""

from __future__ import annotations

import pytest

from PHX2.stage20.constants import (
    ALERT_ELIGIBILITY_DECISIONS_CSV_COLUMNS,
    ALERT_ELIGIBILITY_DECISIONS_CSV_COLUMN_TO_FIELD,
    PREVIEW_CANDIDATES_CSV_COLUMNS,
    PREVIEW_CANDIDATES_CSV_COLUMN_TO_FIELD,
    csv_column_to_model_field,
)
from PHX2.stage20.models import (
    DecisionStep,
    PreviewCandidate,
    RunWarnings,
)


# ---------------------------------------------------------------------------
# PreviewCandidate -- column coverage and additive-field surface
# ---------------------------------------------------------------------------

# Per operator Phase B constraint #1 the alias map lives in
# ``PHX2.stage20.constants`` and is the single source of truth.
# After Phase B the alias map is empty (every CSV column matches a
# model field name 1:1 because ``preview_state`` is now a real
# PreviewCandidate field rather than a CSV-layer alias for
# ``eligibility_state``).


def test_preview_candidates_alias_map_is_empty_identity():
    """Operator constraint #1: alias map centralized in constants.

    After Phase B every CSV column maps 1:1 to a model field with
    the same name; the alias map is therefore empty. Future
    divergence would add entries here and only here.
    """

    assert dict(PREVIEW_CANDIDATES_CSV_COLUMN_TO_FIELD) == {}


def test_preview_candidate_covers_every_csv_column():
    """Every locked preview_candidates.csv column corresponds to a
    PreviewCandidate field through the centralized alias resolver.
    """

    actual = set(PreviewCandidate._fields)
    for csv_col in PREVIEW_CANDIDATES_CSV_COLUMNS:
        model_field = csv_column_to_model_field(
            csv_col, PREVIEW_CANDIDATES_CSV_COLUMN_TO_FIELD
        )
        assert model_field in actual, (
            f"CSV column {csv_col!r} maps to model field "
            f"{model_field!r}, which is missing from PreviewCandidate"
        )


def test_preview_candidate_additive_20_2_fields_present():
    actual = set(PreviewCandidate._fields)
    for f in (
        "stage20_run_id",
        "source_ledger_row_id",
        "mapping_version",
        "review_age_days",
        "review_stale",
        "multiple_operators_for_slice",
        "notes",
    ):
        assert f in actual


def test_preview_candidate_construction_with_full_kwargs():
    """Verifies the field order is consistent enough that a kwargs
    construction succeeds (no positional ambiguity).
    """

    candidate = PreviewCandidate(
        candidate_id="cand_0000000000000001",
        stage18_run_id="s18_run_a",
        stage19_run_id="s19_run_a",
        policy_hash="ph_a",
        rule_id="rule_a",
        window_seconds=30,
        operator_id="op_a",
        review_sequence=1,
        review_label="REVIEW_PROMISING_CONFIRMED",
        review_timestamp_utc="2026-05-15T00:00:00Z",
        eligibility_state="PREVIEW_ELIGIBLE",
        stage18_classification="CLASS_A",
        stage17_label_preserved="LABEL_A",
        safe_for_live_dispatch=False,
        tier_hint="",
        reason_code="LABEL_MAPPED_FROM_OPERATOR_REVIEW",
        stage20_run_id="stage20_0000000000000001",
        source_ledger_row_id="ledger_row_a",
        mapping_version="v0",
        review_age_days=0,
        review_stale=False,
        multiple_operators_for_slice=False,
        notes="",
        preview_state="PREVIEW_ELIGIBLE",
    )
    assert candidate.candidate_id == "cand_0000000000000001"
    assert candidate.stage20_run_id == "stage20_0000000000000001"
    assert candidate.review_stale is False
    assert candidate.review_age_days == 0
    # Operator constraint #2: alias pair carries the same value.
    assert candidate.eligibility_state == candidate.preview_state


def test_preview_candidate_missing_required_field_raises():
    with pytest.raises(TypeError):
        PreviewCandidate(candidate_id="x")  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# DecisionStep -- column coverage and additive-field surface
# ---------------------------------------------------------------------------

def test_alert_eligibility_decisions_alias_map_is_empty_identity():
    """Operator constraint #1: alias map centralized in constants.

    After Phase B every decision CSV column maps 1:1 to a model
    field because ``decision_step_index``, ``decision_step_name``,
    and ``decision_step_terminating`` are now real DecisionStep
    fields paired with their 20.1 counterparts (``step_index``,
    ``step_name``, ``is_terminating``) -- not CSV-layer aliases.
    """

    assert dict(ALERT_ELIGIBILITY_DECISIONS_CSV_COLUMN_TO_FIELD) == {}


def test_decision_step_covers_every_csv_column():
    """Every locked alert_eligibility_decisions.csv column resolves
    to a DecisionStep field through the centralized alias resolver.
    """

    actual = set(DecisionStep._fields)
    for csv_col in ALERT_ELIGIBILITY_DECISIONS_CSV_COLUMNS:
        model_field = csv_column_to_model_field(
            csv_col, ALERT_ELIGIBILITY_DECISIONS_CSV_COLUMN_TO_FIELD
        )
        assert model_field in actual, (
            f"CSV column {csv_col!r} maps to model field "
            f"{model_field!r}, which is missing from DecisionStep"
        )


def test_decision_step_additive_20_2_fields_present():
    actual = set(DecisionStep._fields)
    for f in (
        "decision_id",
        "stage20_run_id",
        "decision_step_state",
        "decision_outcome",
        "evidence_code",
        "evidence_detail",
        "decision_step_index",
        "decision_step_name",
        "decision_step_terminating",
    ):
        assert f in actual


def test_decision_step_construction_with_full_kwargs():
    step = DecisionStep(
        candidate_id="cand_0000000000000001",
        step_index=0,
        step_name="slice_resolved",
        input_state="",
        output_state="passed",
        is_terminating=False,
        reason_code="LABEL_MAPPED_FROM_OPERATOR_REVIEW",
        decision_id="dec_0000000000000001",
        stage20_run_id="stage20_0000000000000001",
        decision_step_state="passed",
        decision_outcome="",
        evidence_code="",
        evidence_detail="",
        decision_step_index=0,
        decision_step_name="slice_resolved",
        decision_step_terminating=False,
    )
    assert step.step_index == 0
    assert step.decision_step_state == "passed"
    assert step.is_terminating is False
    # Operator constraint #3: alias pairs carry identical values.
    assert step.step_index == step.decision_step_index
    assert step.step_name == step.decision_step_name
    assert step.is_terminating == step.decision_step_terminating


def test_decision_step_missing_required_field_raises():
    with pytest.raises(TypeError):
        DecisionStep(candidate_id="x")  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# RunWarnings -- 20.2 local-warning aggregate
# ---------------------------------------------------------------------------


def test_run_warnings_field_set():
    expected = {
        "w2002_preview_eligible_count_zero",
        "w2006_candidate_review_stale_count",
        "w2007_eligibility_mapping_drift_detected",
    }
    assert set(RunWarnings._fields) == expected


def test_run_warnings_construction_with_defaults_off():
    w = RunWarnings(
        w2002_preview_eligible_count_zero=False,
        w2006_candidate_review_stale_count=0,
        w2007_eligibility_mapping_drift_detected=False,
    )
    assert w.w2002_preview_eligible_count_zero is False
    assert w.w2006_candidate_review_stale_count == 0
    assert w.w2007_eligibility_mapping_drift_detected is False


def test_run_warnings_missing_required_field_raises():
    with pytest.raises(TypeError):
        RunWarnings(w2002_preview_eligible_count_zero=True)  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# Mapping-reuse guard -- new 20.2 modules must NOT rebind
# LABEL_TO_STATE_MAPPING_V0
# ---------------------------------------------------------------------------
#
# AST-walks every Stage 20 module (production + tests) and asserts
# none of them contains an Assign / AnnAssign node whose target is
# the name ``LABEL_TO_STATE_MAPPING_V0``. The constant must be
# imported from PHX2.stage20.constants exactly once.


def test_label_mapping_v0_is_not_rebound_anywhere():
    import ast
    import pathlib

    roots = [
        pathlib.Path("PHX2/stage20"),
        pathlib.Path("PHX2/tests/stage20"),
    ]
    constants_path = pathlib.Path("PHX2/stage20/constants.py").resolve()

    offenders: list[str] = []
    for root in roots:
        for f in sorted(root.rglob("*.py")):
            if f.resolve() == constants_path:
                # The one legitimate site of the constant's definition.
                continue
            try:
                tree = ast.parse(f.read_text(encoding="utf-8"), filename=str(f))
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.Assign):
                    for target in node.targets:
                        if (
                            isinstance(target, ast.Name)
                            and target.id == "LABEL_TO_STATE_MAPPING_V0"
                        ):
                            offenders.append(f"{f}:{node.lineno}")
                elif isinstance(node, ast.AnnAssign):
                    target = node.target
                    if (
                        isinstance(target, ast.Name)
                        and target.id == "LABEL_TO_STATE_MAPPING_V0"
                    ):
                        offenders.append(f"{f}:{node.lineno}")

    assert offenders == [], (
        "LABEL_TO_STATE_MAPPING_V0 must not be re-bound outside "
        f"constants.py. Found rebinds at: {offenders}"
    )

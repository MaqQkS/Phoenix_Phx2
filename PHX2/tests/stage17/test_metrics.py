"""Stage 17 metrics aggregation tests.

The tests construct EvaluationRow / OutcomeRow tuples directly rather
than going through SQL fixtures: this keeps each test focused on one
metric-layer invariant and makes the inputs auditable inline.
"""

from __future__ import annotations

from typing import List, Optional

from PHX2.stage17.metrics import (
    compute_coarse_summary,
    compute_data_quality,
    compute_headline_metrics,
    compute_unevaluable_breakdown,
)
from PHX2.stage17.models import EvaluationRow, OutcomeRow


# ---------------------------------------------------------------------------
# Builder helpers
# ---------------------------------------------------------------------------


def _eval(
    *,
    eid: int,
    decision_id: int,
    policy_hash: str = "ph_a",
    rule_id: str = "r1",
    tier: Optional[str] = "tier_a",
    status: str = "MATCHED",
    reason: Optional[str] = None,
) -> EvaluationRow:
    if status == "MATCHED":
        matched, blocked, r = 1, 1, None
    elif status == "NOT_MATCHED":
        matched, blocked, r = 0, 0, None
    else:
        matched, blocked = 0, 0
        r = reason or "missing_input"
    return EvaluationRow(
        id=eid,
        alert_decision_id=decision_id,
        tier_name_snapshot=tier,
        policy_hash=policy_hash,
        rule_id=rule_id,
        evaluation_status=status,
        matched=matched,
        would_have_blocked=blocked,
        unevaluable_reason=r,
        evaluated_at_utc="2026-05-13T12:00:00+00:00",
    )


def _outcome(
    *,
    decision_id: int,
    window_seconds: int = 300,
    data_status: str = "COMPLETE",
    max_return_multiple: Optional[float] = 2.0,
    max_drawdown_from_peak_pct: Optional[float] = -5.0,
    time_to_max_return_seconds: Optional[float] = 60.0,
    hit_2x: Optional[int] = 1,
    hit_3x: Optional[int] = 0,
    hit_5x: Optional[int] = 0,
) -> OutcomeRow:
    return OutcomeRow(
        alert_decision_id=decision_id,
        window_seconds=window_seconds,
        max_return_multiple=max_return_multiple,
        max_drawdown_from_peak_pct=max_drawdown_from_peak_pct,
        time_to_max_return_seconds=time_to_max_return_seconds,
        hit_2x=hit_2x,
        hit_3x=hit_3x,
        hit_5x=hit_5x,
        data_status=data_status,
    )


# ---------------------------------------------------------------------------
# Empty inputs
# ---------------------------------------------------------------------------


def test_compute_headline_metrics_empty_inputs_return_empty() -> None:
    assert compute_headline_metrics([], [], min_n=5) == ()


def test_compute_unevaluable_breakdown_empty_inputs_return_empty() -> None:
    assert compute_unevaluable_breakdown([]) == ()


def test_compute_coarse_summary_empty_inputs_return_empty() -> None:
    assert compute_coarse_summary([]) == ()


# ---------------------------------------------------------------------------
# Single matched + single not_matched with complete outcomes
# ---------------------------------------------------------------------------


def test_single_matched_and_not_matched_single_value_percentiles() -> None:
    """N=1 on each side: percentiles equal the single value."""

    evaluations = [
        _eval(eid=1, decision_id=1, status="MATCHED"),
        _eval(eid=2, decision_id=2, status="NOT_MATCHED"),
    ]
    outcomes = [
        _outcome(decision_id=1, max_return_multiple=3.0, hit_2x=1),
        _outcome(decision_id=2, max_return_multiple=1.0, hit_2x=0),
    ]
    rows = compute_headline_metrics(evaluations, outcomes, min_n=1)
    assert len(rows) == 1
    r = rows[0]
    assert r.n_matched_with_complete_outcome == 1
    assert r.n_not_matched_with_complete_outcome == 1
    assert r.meets_min_n_matched is True
    assert r.meets_min_n_not_matched is True
    assert r.max_return_multiple_p25_matched == 3.0
    assert r.max_return_multiple_p50_matched == 3.0
    assert r.max_return_multiple_p75_matched == 3.0
    assert r.max_return_multiple_p25_not_matched == 1.0
    assert r.hit_2x_rate_matched == 1.0
    assert r.hit_2x_rate_not_matched == 0.0
    assert r.delta_hit_2x_rate == 1.0


# ---------------------------------------------------------------------------
# MIN_N gating
# ---------------------------------------------------------------------------


def test_min_n_matched_false_nulls_matched_side_only() -> None:
    """If matched side has fewer than MIN_N Tier-2 rows, matched fields are NULL."""

    evals = [
        _eval(eid=i, decision_id=i, status="MATCHED") for i in range(1, 3)
    ] + [
        _eval(eid=i + 10, decision_id=i + 10, status="NOT_MATCHED")
        for i in range(5)
    ]
    outs = [_outcome(decision_id=i) for i in range(1, 3)] + [
        _outcome(decision_id=i + 10) for i in range(5)
    ]
    rows = compute_headline_metrics(evals, outs, min_n=5)
    assert len(rows) == 1
    r = rows[0]
    assert r.meets_min_n_matched is False
    assert r.meets_min_n_not_matched is True
    assert r.max_return_multiple_p25_matched is None
    assert r.max_return_multiple_p50_matched is None
    assert r.hit_2x_rate_matched is None
    # Not-matched side keeps its values.
    assert r.max_return_multiple_p25_not_matched is not None
    assert r.hit_2x_rate_not_matched is not None
    # Delta is NULL because matched is NULL.
    assert r.delta_hit_2x_rate is None


def test_min_n_not_matched_false_nulls_not_matched_side_only() -> None:
    evals = [
        _eval(eid=i, decision_id=i, status="MATCHED") for i in range(1, 6)
    ] + [
        _eval(eid=i + 10, decision_id=i + 10, status="NOT_MATCHED")
        for i in range(2)
    ]
    outs = [_outcome(decision_id=i) for i in range(1, 6)] + [
        _outcome(decision_id=i + 10) for i in range(2)
    ]
    rows = compute_headline_metrics(evals, outs, min_n=5)
    r = rows[0]
    assert r.meets_min_n_matched is True
    assert r.meets_min_n_not_matched is False
    assert r.hit_2x_rate_matched is not None
    assert r.hit_2x_rate_not_matched is None
    assert r.delta_hit_2x_rate is None


# ---------------------------------------------------------------------------
# NULL hit_2x exclusion semantics
# ---------------------------------------------------------------------------


def test_null_hit_2x_excludes_row_from_numerator_and_denominator() -> None:
    evals = [_eval(eid=i, decision_id=i, status="MATCHED") for i in range(1, 4)] + [
        _eval(eid=i + 10, decision_id=i + 10, status="NOT_MATCHED")
        for i in range(3)
    ]
    # Matched side: hit_2x = [1, 1, None] -> rate = 1.0 over 2 eligible.
    outs = [
        _outcome(decision_id=1, hit_2x=1),
        _outcome(decision_id=2, hit_2x=1),
        _outcome(decision_id=3, hit_2x=None),
        _outcome(decision_id=10, hit_2x=0),
        _outcome(decision_id=11, hit_2x=0),
        _outcome(decision_id=12, hit_2x=1),
    ]
    rows = compute_headline_metrics(evals, outs, min_n=1)
    r = rows[0]
    # Matched: 2 eligible, both hit -> 1.0.
    assert r.hit_2x_rate_matched == 1.0
    # Not-matched: 3 eligible, 1 hit -> 1/3.
    assert r.hit_2x_rate_not_matched == 1.0 / 3.0


# ---------------------------------------------------------------------------
# NULL max_return_multiple on a Tier-2 row
# ---------------------------------------------------------------------------


def test_null_max_return_multiple_excludes_from_percentile_but_keeps_hit_rate() -> None:
    """A Tier-2 row with max_return_multiple=None is excluded from
    percentile inputs but its hit_2x flag still feeds the rate."""

    evals = [
        _eval(eid=1, decision_id=1, status="MATCHED"),
        _eval(eid=2, decision_id=2, status="MATCHED"),
        _eval(eid=3, decision_id=3, status="NOT_MATCHED"),
        _eval(eid=4, decision_id=4, status="NOT_MATCHED"),
    ]
    outs = [
        _outcome(decision_id=1, max_return_multiple=None, hit_2x=1),
        _outcome(decision_id=2, max_return_multiple=2.0, hit_2x=1),
        _outcome(decision_id=3, max_return_multiple=1.0, hit_2x=0),
        _outcome(decision_id=4, max_return_multiple=1.0, hit_2x=0),
    ]
    rows = compute_headline_metrics(evals, outs, min_n=1)
    r = rows[0]
    # Percentile only over the non-NULL value.
    assert r.max_return_multiple_p50_matched == 2.0
    # Hit rate over all eligible rows: 2/2.
    assert r.hit_2x_rate_matched == 1.0


# ---------------------------------------------------------------------------
# UNEVALUABLE exclusion from percentile / rate
# ---------------------------------------------------------------------------


def test_unevaluable_rows_excluded_from_rates_but_contribute_to_n_in_scope() -> None:
    evals = [
        _eval(eid=1, decision_id=1, status="MATCHED"),
        _eval(eid=2, decision_id=2, status="NOT_MATCHED"),
        _eval(eid=3, decision_id=3, status="UNEVALUABLE", reason="r_missing"),
    ]
    outs = [
        _outcome(decision_id=1, hit_2x=1),
        _outcome(decision_id=2, hit_2x=0),
        _outcome(decision_id=3, hit_2x=1),  # Should not enter the rate.
    ]
    rows = compute_headline_metrics(evals, outs, min_n=1)
    r = rows[0]
    assert r.n_in_scope == 3
    assert r.n_matched == 1
    assert r.n_not_matched == 1
    assert r.n_unevaluable == 1
    # Matched rate ignores the UNEVALUABLE outcome.
    assert r.hit_2x_rate_matched == 1.0
    assert r.hit_2x_rate_not_matched == 0.0


# ---------------------------------------------------------------------------
# Delta NULL propagation
# ---------------------------------------------------------------------------


def test_delta_is_none_when_one_side_is_none() -> None:
    evals = [
        _eval(eid=1, decision_id=1, status="MATCHED"),
        _eval(eid=2, decision_id=2, status="NOT_MATCHED"),
    ]
    outs = [
        _outcome(decision_id=1, hit_2x=1),
        _outcome(decision_id=2, hit_2x=None),  # not_matched rate -> None.
    ]
    rows = compute_headline_metrics(evals, outs, min_n=1)
    r = rows[0]
    assert r.hit_2x_rate_matched == 1.0
    assert r.hit_2x_rate_not_matched is None
    assert r.delta_hit_2x_rate is None


# ---------------------------------------------------------------------------
# Sort order
# ---------------------------------------------------------------------------


def test_headline_row_sort_order_lexicographic() -> None:
    evals: List[EvaluationRow] = []
    outs: List[OutcomeRow] = []
    next_id = 1
    # Build slices in shuffled key order to verify the sort.
    for (ph, rid, tier) in [
        ("ph_b", "r1", "tier_b"),
        ("ph_a", "r2", "tier_a"),
        ("ph_a", "r1", None),
        ("ph_a", "r1", "tier_a"),
    ]:
        evals.append(_eval(eid=next_id, decision_id=next_id, policy_hash=ph,
                           rule_id=rid, tier=tier, status="MATCHED"))
        outs.append(_outcome(decision_id=next_id, window_seconds=300))
        next_id += 1
    rows = compute_headline_metrics(evals, outs, min_n=1)
    keys = [
        (r.policy_hash, r.rule_id, r.tier_name_snapshot or "", r.window_seconds)
        for r in rows
    ]
    assert keys == sorted(keys)
    # NULL tier sorts first within its (ph, rid) bucket.
    assert keys[0] == ("ph_a", "r1", "", 300)


def test_multiple_window_seconds_produce_separate_rows() -> None:
    evals = [_eval(eid=i, decision_id=i, status="MATCHED") for i in range(1, 4)] + [
        _eval(eid=i + 10, decision_id=i + 10, status="NOT_MATCHED")
        for i in range(3)
    ]
    outs = []
    for did in [1, 2, 3, 10, 11, 12]:
        outs.append(_outcome(decision_id=did, window_seconds=300))
        outs.append(_outcome(decision_id=did, window_seconds=3600))
    rows = compute_headline_metrics(evals, outs, min_n=1)
    windows = sorted({r.window_seconds for r in rows})
    assert windows == [300, 3600]


# ---------------------------------------------------------------------------
# Coarse summary aggregation
# ---------------------------------------------------------------------------


def test_coarse_summary_aggregates_over_tiers() -> None:
    """Two tier slices feed into one coarse summary row."""

    # tier_a: matched rate 1.0 over 5 (5/5 hit). not_matched rate 0.2 over 5
    # tier_b: matched rate 0.6 over 5 (3/5 hit). not_matched rate 0.4 over 5
    evals: List[EvaluationRow] = []
    outs: List[OutcomeRow] = []
    eid = 1
    for tier, matched_hits, not_matched_hits in (("tier_a", 5, 1), ("tier_b", 3, 2)):
        for i in range(5):
            evals.append(_eval(eid=eid, decision_id=eid, tier=tier, status="MATCHED"))
            outs.append(
                _outcome(decision_id=eid, hit_2x=1 if i < matched_hits else 0)
            )
            eid += 1
        for i in range(5):
            evals.append(_eval(eid=eid, decision_id=eid, tier=tier, status="NOT_MATCHED"))
            outs.append(
                _outcome(decision_id=eid, hit_2x=1 if i < not_matched_hits else 0)
            )
            eid += 1

    headline = compute_headline_metrics(evals, outs, min_n=1)
    coarse = compute_coarse_summary(headline)
    assert len(coarse) == 1
    c = coarse[0]
    # Weighted matched: (1.0*5 + 0.6*5) / 10 = 0.8.
    assert c.hit_2x_rate_matched == 0.8
    # Weighted not_matched: (0.2*5 + 0.4*5) / 10 = 0.3.
    assert abs(c.hit_2x_rate_not_matched - 0.3) < 1e-9
    assert abs(c.delta_hit_2x_rate - 0.5) < 1e-9


def test_coarse_mixed_by_tier_when_signs_disagree() -> None:
    """Per-tier deltas disagree in sign -> coarse label is MIXED_BY_TIER."""

    # tier_a: matched 5/5 hit, not_matched 1/5 -> delta = +0.8 (HARMFUL).
    # tier_b: matched 1/5 hit, not_matched 5/5 -> delta = -0.8 (PROMISING).
    evals: List[EvaluationRow] = []
    outs: List[OutcomeRow] = []
    eid = 1
    for tier, m_hits, nm_hits in (("tier_a", 5, 1), ("tier_b", 1, 5)):
        for i in range(5):
            evals.append(_eval(eid=eid, decision_id=eid, tier=tier, status="MATCHED"))
            outs.append(_outcome(decision_id=eid, hit_2x=1 if i < m_hits else 0))
            eid += 1
        for i in range(5):
            evals.append(_eval(eid=eid, decision_id=eid, tier=tier, status="NOT_MATCHED"))
            outs.append(_outcome(decision_id=eid, hit_2x=1 if i < nm_hits else 0))
            eid += 1

    headline = compute_headline_metrics(evals, outs, min_n=1)
    coarse = compute_coarse_summary(headline)
    assert len(coarse) == 1
    assert coarse[0].descriptive_label == "MIXED_BY_TIER"


def test_coarse_label_follows_standard_rule_when_signs_agree() -> None:
    """Both tiers PROMISING -> coarse label is also PROMISING."""

    evals: List[EvaluationRow] = []
    outs: List[OutcomeRow] = []
    eid = 1
    for tier in ("tier_a", "tier_b"):
        for i in range(5):
            evals.append(_eval(eid=eid, decision_id=eid, tier=tier, status="MATCHED"))
            outs.append(_outcome(decision_id=eid, hit_2x=0))
            eid += 1
        for i in range(5):
            evals.append(_eval(eid=eid, decision_id=eid, tier=tier, status="NOT_MATCHED"))
            outs.append(_outcome(decision_id=eid, hit_2x=1))
            eid += 1

    headline = compute_headline_metrics(evals, outs, min_n=1)
    coarse = compute_coarse_summary(headline)
    assert len(coarse) == 1
    assert coarse[0].descriptive_label == "PROMISING"


# ---------------------------------------------------------------------------
# Unevaluable breakdown
# ---------------------------------------------------------------------------


def test_unevaluable_breakdown_groups_by_reason() -> None:
    evals = [
        _eval(eid=1, decision_id=1, status="UNEVALUABLE", reason="missing_input"),
        _eval(eid=2, decision_id=2, status="UNEVALUABLE", reason="missing_input"),
        _eval(eid=3, decision_id=3, status="UNEVALUABLE", reason="bad_thresholds"),
        _eval(eid=4, decision_id=4, status="MATCHED"),  # excluded.
    ]
    rows = compute_unevaluable_breakdown(evals)
    assert len(rows) == 2
    by_reason = {r.unevaluable_reason: r.n for r in rows}
    assert by_reason == {"missing_input": 2, "bad_thresholds": 1}


def test_unevaluable_breakdown_sorted_ascending() -> None:
    evals = [
        _eval(eid=1, decision_id=1, policy_hash="ph_b", rule_id="r2",
              status="UNEVALUABLE", reason="z_reason"),
        _eval(eid=2, decision_id=2, policy_hash="ph_a", rule_id="r1",
              status="UNEVALUABLE", reason="a_reason"),
    ]
    rows = compute_unevaluable_breakdown(evals)
    keys = [(r.policy_hash, r.rule_id, r.unevaluable_reason or "") for r in rows]
    assert keys == sorted(keys)


# ---------------------------------------------------------------------------
# Data quality report
# ---------------------------------------------------------------------------


def test_data_quality_global_rows_first_then_slice_rows() -> None:
    evals = [
        _eval(eid=1, decision_id=1, status="MATCHED"),
        _eval(eid=2, decision_id=2, status="NOT_MATCHED"),
    ]
    outs = [
        _outcome(decision_id=1, data_status="NO_PRICE_DATA"),
        _outcome(decision_id=2, data_status="COMPLETE"),
    ]
    rows = compute_data_quality(evals, outs, orphan_eval_count=3, orphan_outcome_count=2)
    # First 4 rows are global-scope.
    assert [r.scope_level for r in rows[:4]] == ["global"] * 4
    metric_names = [r.metric_name for r in rows[:4]]
    assert metric_names == [
        "orphan_evaluations",
        "orphan_outcomes",
        "total_evaluations",
        "total_outcomes",
    ]
    # Slice rows come after global rows.
    slice_rows = [r for r in rows if r.scope_level == "slice"]
    # At least one slice row should be emitted for the (NO_PRICE_DATA) bucket.
    assert any(r.metric_name == "n_outcome_present_but_incomplete" for r in slice_rows)


def test_data_quality_global_orphan_counts_use_inputs() -> None:
    rows = compute_data_quality([], [], orphan_eval_count=42, orphan_outcome_count=7)
    by_name = {r.metric_name: r.metric_value for r in rows if r.scope_level == "global"}
    assert by_name["orphan_evaluations"] == 42
    assert by_name["orphan_outcomes"] == 7
    assert by_name["total_evaluations"] == 0
    assert by_name["total_outcomes"] == 0

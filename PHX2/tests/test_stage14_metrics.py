"""Stage 14 metrics + warning-flag tests.

Covers:
  * By-tier / by-rule / by-filter aggregate counts sum correctly.
  * unmatched_filter_tuple fires when a rule matches zero decisions.
  * small_n_rule fires when 0 < n_matched < 10.
  * excessive_block_rate fires when blocks > 30% of tier live total.
  * high_winners_blocked_rate fires above 30% winners among blocked-with-outcome.
  * unknown_outcome_rate fires above 30% no-outcome among blocked.
  * missing_outcome_data fires at the run level below 50% primary-outcome share.
  * Decisions whose original_action is not 'would_alert' are excluded
    from all aggregates.
"""

from __future__ import annotations

from PHX2.stage14.metrics import compute_impact
from PHX2.stage14.replay import replay
from PHX2.stage14.rules import compute_rule_id
from PHX2.stage14.types import (
    WARNING_EXCESSIVE_BLOCK_RATE,
    WARNING_HIGH_WINNERS_BLOCKED_RATE,
    WARNING_MISSING_OUTCOME_DATA,
    WARNING_SMALL_N_RULE,
    WARNING_UNKNOWN_OUTCOME_RATE,
    WARNING_UNMATCHED_FILTER_TUPLE,
    LongCsvRow,
    ShadowRule,
)


def _rule(
    tier: str = "T1",
    label: str = "scam_likely",
) -> ShadowRule:
    rid = compute_rule_id(
        policy_surface="filter_label_blocking",
        tier_scope=tier,
        filter_name="fee_gate_v1",
        filter_version="v1",
        filter_label=label,
        threshold_version="v1",
        simulated_action="SIMULATED_BLOCK",
    )
    return ShadowRule(
        rule_id=rid,
        policy_surface="filter_label_blocking",
        tier_scope=tier,
        filter_name="fee_gate_v1",
        filter_version="v1",
        filter_label=label,
        threshold_version="v1",
        simulated_action="SIMULATED_BLOCK",
        direction="tighten",
        source_recommendations=(),
    )


def _long(
    decision_id: str,
    *,
    tier_name: str = "T1",
    filter_label: str = "scam_likely",
    has_primary_outcome: bool | None = True,
    hit_2x: bool | None = False,
    decision_type: str = "would_alert",
) -> LongCsvRow:
    return LongCsvRow(
        alert_decision_id=decision_id,
        token_address="Tok",
        tier_index=1,
        tier_name=tier_name,
        decision_type=decision_type,
        filter_name="fee_gate_v1",
        filter_version="v1",
        filter_label=filter_label,
        threshold_version="v1",
        has_primary_outcome=has_primary_outcome,
        primary_outcome_hit_2x_24h=hit_2x,
        primary_outcome_hit_3x_24h=None,
        primary_outcome_hit_5x_24h=None,
    )


def test_basic_aggregation_counts() -> None:
    rule = _rule()
    replay_rows = replay(
        [rule],
        [
            _long("d_winner", hit_2x=True),
            _long("d_loser", hit_2x=False),
            _long("d_unknown", has_primary_outcome=False, hit_2x=None),
        ],
    )
    impact = compute_impact(rules=[rule], replay_rows=replay_rows)

    tier = impact.by_tier["T1"]
    assert tier.n_live_decisions == 3
    assert tier.n_simulated_blocks == 3
    assert tier.n_blocked_with_primary_outcome == 2
    assert tier.n_blocked_winners_2x == 1
    assert tier.n_blocked_no_outcome == 1

    overall = impact.by_tier["overall"]
    assert overall.n_live_decisions == 3
    assert overall.n_simulated_blocks == 3


def test_unmatched_filter_tuple_warning() -> None:
    """A rule that matches zero decisions in the long CSV gets the
    unmatched flag."""

    rule = _rule()
    replay_rows = replay(
        [rule],
        [
            # All decisions are for a different filter_label.
            _long("d1", filter_label="benign"),
        ],
    )
    impact = compute_impact(rules=[rule], replay_rows=replay_rows)
    assert WARNING_UNMATCHED_FILTER_TUPLE in impact.by_rule[0].warning_flags


def test_small_n_rule_warning() -> None:
    rule = _rule()
    long_rows = [_long(f"d{i}", hit_2x=False) for i in range(5)]
    replay_rows = replay([rule], long_rows)
    impact = compute_impact(rules=[rule], replay_rows=replay_rows)
    flags = impact.by_rule[0].warning_flags
    assert WARNING_SMALL_N_RULE in flags
    assert WARNING_UNMATCHED_FILTER_TUPLE not in flags


def test_excessive_block_rate_warning() -> None:
    """When the rule's blocks exceed 30% of the tier's live decisions
    the excessive_block_rate flag fires."""

    rule = _rule()
    # 10 live decisions in T1; 8 match the rule.
    matched = [_long(f"match_{i}", hit_2x=False) for i in range(8)]
    unmatched = [
        _long(f"miss_{i}", filter_label="benign", hit_2x=False) for i in range(2)
    ]
    replay_rows = replay([rule], matched + unmatched)
    impact = compute_impact(rules=[rule], replay_rows=replay_rows)
    assert WARNING_EXCESSIVE_BLOCK_RATE in impact.by_rule[0].warning_flags


def test_excessive_block_rate_boundary_below_threshold() -> None:
    """A 20% tier block rate must NOT trigger the warning.

    Anchors the locked v0 threshold (0.3): 0.2 sits below it.
    """

    rule = _rule()
    # 10 live decisions in T1; 2 match the rule (20% block rate).
    matched = [_long(f"match_{i}", hit_2x=False) for i in range(2)]
    unmatched = [
        _long(f"miss_{i}", filter_label="benign", hit_2x=False) for i in range(8)
    ]
    replay_rows = replay([rule], matched + unmatched)
    impact = compute_impact(rules=[rule], replay_rows=replay_rows)
    assert WARNING_EXCESSIVE_BLOCK_RATE not in impact.by_rule[0].warning_flags


def test_excessive_block_rate_boundary_above_threshold() -> None:
    """A 40% tier block rate MUST trigger the warning.

    Anchors the locked v0 threshold (0.3): 0.4 sits above it. This
    test would FAIL under the previous 0.5 threshold value, so it
    pins the post-pushback design lock.
    """

    rule = _rule()
    # 10 live decisions in T1; 4 match the rule (40% block rate).
    matched = [_long(f"match_{i}", hit_2x=False) for i in range(4)]
    unmatched = [
        _long(f"miss_{i}", filter_label="benign", hit_2x=False) for i in range(6)
    ]
    replay_rows = replay([rule], matched + unmatched)
    impact = compute_impact(rules=[rule], replay_rows=replay_rows)
    assert WARNING_EXCESSIVE_BLOCK_RATE in impact.by_rule[0].warning_flags


def test_high_winners_blocked_rate_warning() -> None:
    rule = _rule()
    # 10 blocked decisions, 7 are 2x winners → 70% > 30% threshold.
    long_rows = [_long(f"d{i}", hit_2x=(i < 7)) for i in range(10)]
    replay_rows = replay([rule], long_rows)
    impact = compute_impact(rules=[rule], replay_rows=replay_rows)
    assert WARNING_HIGH_WINNERS_BLOCKED_RATE in impact.by_rule[0].warning_flags


def test_unknown_outcome_rate_warning() -> None:
    rule = _rule()
    # 10 blocked, 5 have no primary outcome → 50% > 30% threshold.
    long_rows = []
    for i in range(10):
        if i < 5:
            long_rows.append(
                _long(f"d{i}", has_primary_outcome=False, hit_2x=None)
            )
        else:
            long_rows.append(_long(f"d{i}", hit_2x=False))
    replay_rows = replay([rule], long_rows)
    impact = compute_impact(rules=[rule], replay_rows=replay_rows)
    assert WARNING_UNKNOWN_OUTCOME_RATE in impact.by_rule[0].warning_flags


def test_missing_outcome_data_overall_warning() -> None:
    rule = _rule()
    # 10 live decisions, only 3 with primary outcome → 30% < 50% threshold.
    long_rows = []
    for i in range(10):
        if i < 3:
            long_rows.append(_long(f"d{i}", hit_2x=False))
        else:
            long_rows.append(
                _long(f"d{i}", has_primary_outcome=False, hit_2x=None)
            )
    replay_rows = replay([rule], long_rows)
    impact = compute_impact(rules=[rule], replay_rows=replay_rows)
    assert WARNING_MISSING_OUTCOME_DATA in impact.overall_warning_flags


def test_non_would_alert_decisions_excluded_from_counts() -> None:
    rule = _rule()
    replay_rows = replay(
        [rule],
        [
            _long("d_alert", decision_type="would_alert", hit_2x=True),
            _long("d_silent", decision_type="not_actionable", hit_2x=True),
        ],
    )
    impact = compute_impact(rules=[rule], replay_rows=replay_rows)
    tier = impact.by_tier["T1"]
    assert tier.n_live_decisions == 1
    assert tier.n_simulated_blocks == 1


def test_rule_with_zero_matches_has_zero_counts() -> None:
    rule = _rule()
    impact = compute_impact(rules=[rule], replay_rows=[])
    assert impact.by_rule[0].n_matched == 0
    assert impact.by_rule[0].counts.n_simulated_blocks == 0


def test_by_filter_collapses_versions() -> None:
    """Two rules with same filter_name but different threshold_version
    aggregate to one filter row."""

    rid_a = compute_rule_id(
        policy_surface="filter_label_blocking",
        tier_scope="T1",
        filter_name="fee_gate_v1",
        filter_version="v1",
        filter_label="scam_likely",
        threshold_version="v1",
        simulated_action="SIMULATED_BLOCK",
    )
    rid_b = compute_rule_id(
        policy_surface="filter_label_blocking",
        tier_scope="T1",
        filter_name="fee_gate_v1",
        filter_version="v1",
        filter_label="scam_likely",
        threshold_version="v2",
        simulated_action="SIMULATED_BLOCK",
    )
    rule_a = ShadowRule(
        rule_id=rid_a,
        policy_surface="filter_label_blocking",
        tier_scope="T1",
        filter_name="fee_gate_v1",
        filter_version="v1",
        filter_label="scam_likely",
        threshold_version="v1",
        simulated_action="SIMULATED_BLOCK",
        direction="tighten",
        source_recommendations=(),
    )
    rule_b = ShadowRule(
        rule_id=rid_b,
        policy_surface="filter_label_blocking",
        tier_scope="T1",
        filter_name="fee_gate_v1",
        filter_version="v1",
        filter_label="scam_likely",
        threshold_version="v2",
        simulated_action="SIMULATED_BLOCK",
        direction="tighten",
        source_recommendations=(),
    )
    long_rows = [
        _long("d1", hit_2x=False),  # matches rule_a (threshold_version=v1)
        # Build a long row matching rule_b directly.
        LongCsvRow(
            alert_decision_id="d2",
            token_address="Tok",
            tier_index=1,
            tier_name="T1",
            decision_type="would_alert",
            filter_name="fee_gate_v1",
            filter_version="v1",
            filter_label="scam_likely",
            threshold_version="v2",
            has_primary_outcome=True,
            primary_outcome_hit_2x_24h=False,
            primary_outcome_hit_3x_24h=None,
            primary_outcome_hit_5x_24h=None,
        ),
    ]
    replay_rows = replay([rule_a, rule_b], long_rows)
    impact = compute_impact(rules=[rule_a, rule_b], replay_rows=replay_rows)
    assert "fee_gate_v1" in impact.by_filter
    assert impact.by_filter["fee_gate_v1"].n_simulated_blocks == 2

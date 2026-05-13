"""Stage 14 replay tests.

Covers:
  * One ``ReplayRow`` per unique ``alert_decision_id`` (not per
    filter evaluation).
  * Triggering rule IDs are deduped + sorted; n_triggering_rules is
    the post-dedup count.
  * Tier mismatch / filter-tuple mismatch / missing-identity rows do
    not match.
  * Multi-rule decisions collect every matching rule ID.
  * ``decision_changed`` requires the original decision to have been
    a live alert (decision_type == "would_alert").
  * Decisions with no filter evaluations are recorded as
    SIMULATED_PASS / decision_changed=False.
"""

from __future__ import annotations

from PHX2.stage14.replay import replay
from PHX2.stage14.rules import compute_rule_id
from PHX2.stage14.types import LongCsvRow, ShadowRule


def _make_rule(
    *,
    tier_scope: str = "T1",
    filter_name: str = "fee_gate_v1",
    filter_version: str = "v1",
    filter_label: str = "scam_likely",
    threshold_version: str = "v1",
) -> ShadowRule:
    rid = compute_rule_id(
        policy_surface="filter_label_blocking",
        tier_scope=tier_scope,
        filter_name=filter_name,
        filter_version=filter_version,
        filter_label=filter_label,
        threshold_version=threshold_version,
        simulated_action="SIMULATED_BLOCK",
    )
    return ShadowRule(
        rule_id=rid,
        policy_surface="filter_label_blocking",
        tier_scope=tier_scope,
        filter_name=filter_name,
        filter_version=filter_version,
        filter_label=filter_label,
        threshold_version=threshold_version,
        simulated_action="SIMULATED_BLOCK",
        direction="tighten",
        source_recommendations=(),
    )


def _long_row(
    decision_id: str = "d1",
    *,
    tier_name: str | None = "T1",
    filter_name: str | None = "fee_gate_v1",
    filter_version: str | None = "v1",
    filter_label: str | None = "scam_likely",
    threshold_version: str | None = "v1",
    decision_type: str | None = "would_alert",
    has_primary_outcome: bool | None = True,
    primary_outcome_hit_2x_24h: bool | None = False,
    primary_outcome_hit_3x_24h: bool | None = False,
    primary_outcome_hit_5x_24h: bool | None = False,
) -> LongCsvRow:
    return LongCsvRow(
        alert_decision_id=decision_id,
        token_address="Tok",
        tier_index=1,
        tier_name=tier_name,
        decision_type=decision_type,
        filter_name=filter_name,
        filter_version=filter_version,
        filter_label=filter_label,
        threshold_version=threshold_version,
        has_primary_outcome=has_primary_outcome,
        primary_outcome_hit_2x_24h=primary_outcome_hit_2x_24h,
        primary_outcome_hit_3x_24h=primary_outcome_hit_3x_24h,
        primary_outcome_hit_5x_24h=primary_outcome_hit_5x_24h,
    )


def test_single_rule_single_decision_matches() -> None:
    rule = _make_rule()
    rows = replay([rule], [_long_row()])
    assert len(rows) == 1
    rr = rows[0]
    assert rr.simulated_action == "SIMULATED_BLOCK"
    assert rr.triggering_rule_ids == (rule.rule_id,)
    assert rr.n_triggering_rules == 1
    assert rr.decision_changed is True


def test_tier_mismatch_does_not_match() -> None:
    rule = _make_rule(tier_scope="T1")
    rows = replay([rule], [_long_row(tier_name="T2")])
    assert len(rows) == 1
    assert rows[0].simulated_action == "SIMULATED_PASS"
    assert rows[0].triggering_rule_ids == ()
    assert rows[0].decision_changed is False


def test_filter_tuple_mismatch_does_not_match() -> None:
    rule = _make_rule(filter_label="scam_likely")
    rows = replay([rule], [_long_row(filter_label="benign")])
    assert rows[0].simulated_action == "SIMULATED_PASS"


def test_missing_filter_identity_does_not_match() -> None:
    rule = _make_rule()
    rows = replay([rule], [_long_row(filter_name=None)])
    assert rows[0].simulated_action == "SIMULATED_PASS"


def test_multi_rule_match_collects_all_rule_ids() -> None:
    rule_a = _make_rule(filter_label="label_a")
    rule_b = _make_rule(filter_label="label_b")
    rows = replay(
        [rule_a, rule_b],
        [
            _long_row(decision_id="d_multi", filter_label="label_a"),
            _long_row(decision_id="d_multi", filter_label="label_b"),
        ],
    )
    assert len(rows) == 1
    triggering = rows[0].triggering_rule_ids
    assert triggering == tuple(sorted([rule_a.rule_id, rule_b.rule_id]))
    assert rows[0].n_triggering_rules == 2


def test_duplicate_filter_rows_dedupe_to_one_rule_id() -> None:
    rule = _make_rule()
    rows = replay(
        [rule],
        [
            _long_row(decision_id="d_dup"),
            _long_row(decision_id="d_dup"),
            _long_row(decision_id="d_dup"),
        ],
    )
    assert len(rows) == 1
    assert rows[0].triggering_rule_ids == (rule.rule_id,)
    assert rows[0].n_triggering_rules == 1


def test_non_would_alert_does_not_set_decision_changed() -> None:
    rule = _make_rule()
    rows = replay(
        [rule],
        [_long_row(decision_type="not_actionable")],
    )
    assert rows[0].simulated_action == "SIMULATED_BLOCK"
    assert rows[0].decision_changed is False


def test_decision_with_no_filter_rows_is_simulated_pass() -> None:
    rule = _make_rule()
    rows = replay(
        [rule],
        [_long_row(filter_name=None, filter_version=None, filter_label=None, threshold_version=None)],
    )
    assert len(rows) == 1
    assert rows[0].simulated_action == "SIMULATED_PASS"
    assert rows[0].triggering_rule_ids == ()
    assert rows[0].decision_changed is False


def test_one_row_per_decision_with_many_filter_rows() -> None:
    rule = _make_rule()
    # Three filter rows for one decision; only one (matching) should
    # produce a block but the result is still one ReplayRow.
    rows = replay(
        [rule],
        [
            _long_row(decision_id="d_many", filter_label="scam_likely"),
            _long_row(decision_id="d_many", filter_label="other"),
            _long_row(decision_id="d_many", filter_label="another"),
        ],
    )
    assert len(rows) == 1
    assert rows[0].alert_decision_id == "d_many"
    assert rows[0].simulated_action == "SIMULATED_BLOCK"


def test_outputs_sorted_by_alert_decision_id() -> None:
    rule = _make_rule()
    rows = replay(
        [rule],
        [
            _long_row(decision_id="zzz"),
            _long_row(decision_id="aaa"),
            _long_row(decision_id="mmm"),
        ],
    )
    ids = [r.alert_decision_id for r in rows]
    assert ids == sorted(ids)


def test_outcome_fields_carried_through() -> None:
    rule = _make_rule()
    rows = replay(
        [rule],
        [
            _long_row(
                decision_id="winner",
                has_primary_outcome=True,
                primary_outcome_hit_2x_24h=True,
                primary_outcome_hit_3x_24h=True,
                primary_outcome_hit_5x_24h=False,
            )
        ],
    )
    rr = rows[0]
    assert rr.has_primary_outcome is True
    assert rr.primary_outcome_hit_2x_24h is True
    assert rr.primary_outcome_hit_3x_24h is True
    assert rr.primary_outcome_hit_5x_24h is False


def test_empty_alert_decision_id_skipped() -> None:
    rule = _make_rule()
    rows = replay(
        [rule],
        [
            _long_row(decision_id=""),  # corrupt; skipped
            _long_row(decision_id="d_real"),
        ],
    )
    assert len(rows) == 1
    assert rows[0].alert_decision_id == "d_real"

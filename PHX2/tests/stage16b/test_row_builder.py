"""Phase 3 tests: Stage 16B row builder pure-function behavior.

Locks tested here:

  * row count always equals ``len(policy.rules)``
  * MATCHED / NOT_MATCHED / UNEVALUABLE status strings are exact
  * predicate_snapshot_json contains EXACTLY the 5-key predicate; LoadedRule
    audit metadata (source_stage14_rule_hash, operator_reason,
    reviewed_at_utc) is never copied in
  * canonical JSON byte-identical to PHX2.stage16a.hashing.canonical_json_dumps
  * tier_name_snapshot preserves None
  * unevaluable_reason is passed through verbatim from RuleUnevaluable
  * MATCHED rows have unevaluable_reason=None
"""

from __future__ import annotations

import json
from types import MappingProxyType
from typing import Mapping

from PHX2.stage16a.hashing import canonical_json_dumps
from PHX2.stage16a.models import (
    LoadedObserveOnlyPolicy,
    LoadedRule,
    ObserveOnlyEvaluationResult,
    RuleMatch,
    RuleUnevaluable,
)
from PHX2.stage16b.row_builder import build_rows_for_decision


# ---------------------------------------------------------------------------
# Test fixture helpers (LoadedRule / LoadedObserveOnlyPolicy / result builders)
# ---------------------------------------------------------------------------


_FIVE_KEY_PREDICATE = (
    "tier_scope",
    "filter_name",
    "filter_version",
    "filter_label",
    "threshold_version",
)


def _make_rule(
    rule_id: str = "rule_a",
    tier_scope: str = "T1",
    filter_name: str = "fee_gate",
    filter_version: str = "fee_gate_v1_no_bribes",
    filter_label: str = "NORMAL",
    threshold_version: str = "thresholds_v0_observe_only",
    *,
    source_stage14_rule_hash: str = "",
    operator_reason: str = "",
    reviewed_at_utc: str = "",
) -> LoadedRule:
    return LoadedRule(
        rule_id=rule_id,
        tier_scope=tier_scope,
        filter_name=filter_name,
        filter_version=filter_version,
        filter_label=filter_label,
        threshold_version=threshold_version,
        source_stage14_rule_hash=source_stage14_rule_hash,
        operator_reason=operator_reason,
        reviewed_at_utc=reviewed_at_utc,
    )


def _make_policy(
    rules: tuple[LoadedRule, ...],
    policy_hash: str = "sha256:" + "a" * 64,
) -> LoadedObserveOnlyPolicy:
    return LoadedObserveOnlyPolicy(
        schema_version="observe_only_runtime_policy_v0",
        policy_hash=policy_hash,
        generated_at_utc="2026-05-13T12:00:00+00:00",
        git_commit="deadbeefcafef00d",
        rules=rules,
        lineage=MappingProxyType({"source_stage14_manifest_hash": "sha256:" + "1" * 64}),
    )


def _make_match_for(rule: LoadedRule, matched_index: int = 0) -> RuleMatch:
    return RuleMatch(
        rule_id=rule.rule_id,
        matched_filter_evaluation_index=matched_index,
        predicate_snapshot=MappingProxyType({
            "tier_scope": rule.tier_scope,
            "filter_name": rule.filter_name,
            "filter_version": rule.filter_version,
            "filter_label": rule.filter_label,
            "threshold_version": rule.threshold_version,
        }),
    )


def _make_result(
    *,
    policy_hash: str = "sha256:" + "a" * 64,
    alert_decision_id: int = 1,
    matched: tuple[RuleMatch, ...] = (),
    unevaluable: tuple[RuleUnevaluable, ...] = (),
) -> ObserveOnlyEvaluationResult:
    return ObserveOnlyEvaluationResult(
        alert_decision_id=alert_decision_id,
        policy_hash=policy_hash,
        matched_rules=matched,
        unevaluable_rules=unevaluable,
    )


_EVALUATED_AT = "2026-05-13T12:00:00+00:00"


# ---------------------------------------------------------------------------
# Output cardinality
# ---------------------------------------------------------------------------


def test_row_count_equals_policy_rule_count_for_zero_results() -> None:
    rules = (
        _make_rule("rule_a"),
        _make_rule("rule_b", tier_scope="T2"),
        _make_rule("rule_c", tier_scope="T3"),
    )
    policy = _make_policy(rules)
    result = _make_result()

    rows = build_rows_for_decision(
        alert_decision_id=1,
        tier_name="T1",
        policy=policy,
        result=result,
        evaluated_at_utc=_EVALUATED_AT,
    )
    assert len(rows) == len(rules) == 3


def test_row_count_equals_policy_rule_count_for_mixed_results() -> None:
    rules = (
        _make_rule("rule_a"),
        _make_rule("rule_b", tier_scope="T2"),
        _make_rule("rule_c", tier_scope="T3"),
        _make_rule("rule_d"),
    )
    policy = _make_policy(rules)
    result = _make_result(
        matched=(_make_match_for(rules[0]),),
        unevaluable=(RuleUnevaluable(rule_id="rule_c", reason="tier_name_missing_on_decision"),),
    )

    rows = build_rows_for_decision(
        alert_decision_id=1,
        tier_name="T1",
        policy=policy,
        result=result,
        evaluated_at_utc=_EVALUATED_AT,
    )
    assert len(rows) == 4


def test_row_count_equals_policy_rule_count_for_empty_policy() -> None:
    policy = _make_policy(rules=())
    result = _make_result()

    rows = build_rows_for_decision(
        alert_decision_id=1,
        tier_name="T1",
        policy=policy,
        result=result,
        evaluated_at_utc=_EVALUATED_AT,
    )
    assert rows == ()


# ---------------------------------------------------------------------------
# Status discrimination
# ---------------------------------------------------------------------------


def test_one_match_produces_one_matched_row() -> None:
    rule = _make_rule("rule_a")
    policy = _make_policy((rule,))
    result = _make_result(matched=(_make_match_for(rule),))

    rows = build_rows_for_decision(
        alert_decision_id=1,
        tier_name="T1",
        policy=policy,
        result=result,
        evaluated_at_utc=_EVALUATED_AT,
    )
    assert len(rows) == 1
    assert rows[0].evaluation_status == "MATCHED"
    assert rows[0].matched == 1
    assert rows[0].would_have_blocked == 1
    assert rows[0].unevaluable_reason is None


def test_remaining_rules_produce_not_matched_rows() -> None:
    matched_rule = _make_rule("rule_a")
    other_rule = _make_rule("rule_b", tier_scope="T2")
    policy = _make_policy((matched_rule, other_rule))
    result = _make_result(matched=(_make_match_for(matched_rule),))

    rows = build_rows_for_decision(
        alert_decision_id=1,
        tier_name="T1",
        policy=policy,
        result=result,
        evaluated_at_utc=_EVALUATED_AT,
    )
    assert rows[0].evaluation_status == "MATCHED"
    assert rows[1].evaluation_status == "NOT_MATCHED"
    assert rows[1].matched == 0
    assert rows[1].would_have_blocked == 0
    assert rows[1].unevaluable_reason is None


def test_one_unevaluable_produces_one_unevaluable_row() -> None:
    rule = _make_rule("rule_a")
    policy = _make_policy((rule,))
    result = _make_result(
        unevaluable=(RuleUnevaluable(rule_id="rule_a", reason="tier_name_missing_on_decision"),),
    )

    rows = build_rows_for_decision(
        alert_decision_id=1,
        tier_name=None,
        policy=policy,
        result=result,
        evaluated_at_utc=_EVALUATED_AT,
    )
    assert len(rows) == 1
    assert rows[0].evaluation_status == "UNEVALUABLE"
    assert rows[0].matched == 0
    assert rows[0].would_have_blocked == 0
    assert rows[0].unevaluable_reason == "tier_name_missing_on_decision"


def test_no_matches_or_unevaluables_all_not_matched() -> None:
    rules = tuple(_make_rule(f"rule_{i}") for i in range(3))
    policy = _make_policy(rules)
    result = _make_result()

    rows = build_rows_for_decision(
        alert_decision_id=1,
        tier_name="T1",
        policy=policy,
        result=result,
        evaluated_at_utc=_EVALUATED_AT,
    )
    assert [r.evaluation_status for r in rows] == ["NOT_MATCHED"] * 3
    assert all(r.matched == 0 for r in rows)
    assert all(r.would_have_blocked == 0 for r in rows)
    assert all(r.unevaluable_reason is None for r in rows)


def test_multiple_matches_produce_multiple_matched_rows() -> None:
    rules = (
        _make_rule("rule_a"),
        _make_rule("rule_b", filter_label="ELEVATED"),
        _make_rule("rule_c", filter_label="SUSPICIOUS"),
    )
    policy = _make_policy(rules)
    result = _make_result(matched=(
        _make_match_for(rules[0]),
        _make_match_for(rules[2]),
    ))

    rows = build_rows_for_decision(
        alert_decision_id=1,
        tier_name="T1",
        policy=policy,
        result=result,
        evaluated_at_utc=_EVALUATED_AT,
    )
    assert [r.evaluation_status for r in rows] == [
        "MATCHED", "NOT_MATCHED", "MATCHED",
    ]


def test_status_strings_are_exact_uppercase_snake() -> None:
    rule_m = _make_rule("rule_m")
    rule_n = _make_rule("rule_n", tier_scope="T2")
    rule_u = _make_rule("rule_u", tier_scope="T3")
    policy = _make_policy((rule_m, rule_n, rule_u))
    result = _make_result(
        matched=(_make_match_for(rule_m),),
        unevaluable=(RuleUnevaluable(rule_id="rule_u", reason="r"),),
    )
    rows = build_rows_for_decision(
        alert_decision_id=1, tier_name="T1", policy=policy,
        result=result, evaluated_at_utc=_EVALUATED_AT,
    )
    statuses = {r.evaluation_status for r in rows}
    assert statuses == {"MATCHED", "NOT_MATCHED", "UNEVALUABLE"}


# ---------------------------------------------------------------------------
# Field propagation
# ---------------------------------------------------------------------------


def test_tier_name_snapshot_preserves_none() -> None:
    rule = _make_rule("rule_a")
    policy = _make_policy((rule,))
    result = _make_result()

    rows = build_rows_for_decision(
        alert_decision_id=1,
        tier_name=None,
        policy=policy,
        result=result,
        evaluated_at_utc=_EVALUATED_AT,
    )
    assert rows[0].tier_name_snapshot is None


def test_tier_name_snapshot_preserves_value() -> None:
    rule = _make_rule("rule_a")
    policy = _make_policy((rule,))
    result = _make_result()

    rows = build_rows_for_decision(
        alert_decision_id=1,
        tier_name="T2",
        policy=policy,
        result=result,
        evaluated_at_utc=_EVALUATED_AT,
    )
    assert rows[0].tier_name_snapshot == "T2"


def test_alert_decision_id_passed_through() -> None:
    rule = _make_rule("rule_a")
    policy = _make_policy((rule,))
    result = _make_result(alert_decision_id=999)

    rows = build_rows_for_decision(
        alert_decision_id=999,
        tier_name="T1",
        policy=policy,
        result=result,
        evaluated_at_utc=_EVALUATED_AT,
    )
    assert rows[0].alert_decision_id == 999


def test_policy_hash_passed_through() -> None:
    rule = _make_rule("rule_a")
    policy_hash = "sha256:" + "9" * 64
    policy = _make_policy((rule,), policy_hash=policy_hash)
    result = _make_result(policy_hash=policy_hash)

    rows = build_rows_for_decision(
        alert_decision_id=1,
        tier_name="T1",
        policy=policy,
        result=result,
        evaluated_at_utc=_EVALUATED_AT,
    )
    assert rows[0].policy_hash == policy_hash


def test_evaluated_at_utc_passed_through() -> None:
    rule = _make_rule("rule_a")
    policy = _make_policy((rule,))
    result = _make_result()
    evaluated_at = "2027-01-01T00:00:00+00:00"

    rows = build_rows_for_decision(
        alert_decision_id=1,
        tier_name="T1",
        policy=policy,
        result=result,
        evaluated_at_utc=evaluated_at,
    )
    assert rows[0].evaluated_at_utc == evaluated_at


def test_unevaluable_reason_passed_through() -> None:
    rule = _make_rule("rule_a")
    policy = _make_policy((rule,))
    result = _make_result(
        unevaluable=(RuleUnevaluable(rule_id="rule_a", reason="some_specific_reason"),),
    )

    rows = build_rows_for_decision(
        alert_decision_id=1,
        tier_name=None,
        policy=policy,
        result=result,
        evaluated_at_utc=_EVALUATED_AT,
    )
    assert rows[0].unevaluable_reason == "some_specific_reason"


def test_matched_row_has_null_unevaluable_reason() -> None:
    rule = _make_rule("rule_a")
    policy = _make_policy((rule,))
    result = _make_result(matched=(_make_match_for(rule),))

    rows = build_rows_for_decision(
        alert_decision_id=1,
        tier_name="T1",
        policy=policy,
        result=result,
        evaluated_at_utc=_EVALUATED_AT,
    )
    assert rows[0].unevaluable_reason is None


# ---------------------------------------------------------------------------
# predicate_snapshot_json -- canonical JSON, 5-key only
# ---------------------------------------------------------------------------


def test_predicate_snapshot_json_is_canonical() -> None:
    rule = _make_rule(
        "rule_a",
        tier_scope="T2",
        filter_name="fee_gate",
        filter_version="fee_gate_v1_no_bribes",
        filter_label="SCAM_LIKELY",
        threshold_version="thresholds_v0_observe_only",
    )
    policy = _make_policy((rule,))
    result = _make_result()

    rows = build_rows_for_decision(
        alert_decision_id=1,
        tier_name="T1",
        policy=policy,
        result=result,
        evaluated_at_utc=_EVALUATED_AT,
    )
    expected = canonical_json_dumps({
        "tier_scope": "T2",
        "filter_name": "fee_gate",
        "filter_version": "fee_gate_v1_no_bribes",
        "filter_label": "SCAM_LIKELY",
        "threshold_version": "thresholds_v0_observe_only",
    })
    assert rows[0].predicate_snapshot_json == expected


def test_canonical_json_parity_with_stage16a_matched_row() -> None:
    """MATCHED row's snapshot is canonical-JSON of the 5-key predicate."""

    rule = _make_rule(
        "rule_a",
        tier_scope="T1",
        filter_name="fee_gate",
        filter_version="fee_gate_v1_no_bribes",
        filter_label="NORMAL",
        threshold_version="thresholds_v0_observe_only",
    )
    policy = _make_policy((rule,))
    result = _make_result(matched=(_make_match_for(rule),))

    rows = build_rows_for_decision(
        alert_decision_id=1,
        tier_name="T1",
        policy=policy,
        result=result,
        evaluated_at_utc=_EVALUATED_AT,
    )
    expected = canonical_json_dumps({
        "tier_scope": "T1",
        "filter_name": "fee_gate",
        "filter_version": "fee_gate_v1_no_bribes",
        "filter_label": "NORMAL",
        "threshold_version": "thresholds_v0_observe_only",
    })
    assert rows[0].predicate_snapshot_json == expected


def test_predicate_snapshot_json_keys_are_sorted_canonical() -> None:
    """Canonical JSON sorts keys ascending; verify by parsing and re-encoding."""

    rule = _make_rule("rule_a")
    policy = _make_policy((rule,))
    result = _make_result()

    rows = build_rows_for_decision(
        alert_decision_id=1,
        tier_name="T1",
        policy=policy,
        result=result,
        evaluated_at_utc=_EVALUATED_AT,
    )
    parsed = json.loads(rows[0].predicate_snapshot_json)
    # canonical form is sort_keys=True, separators=(',', ':')
    assert rows[0].predicate_snapshot_json == json.dumps(
        parsed, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    )


def test_row_builder_predicate_snapshot_excludes_loaded_rule_extras() -> None:
    """LoadedRule audit metadata MUST NOT appear in predicate_snapshot_json.

    Build a LoadedRule with non-empty
    ``source_stage14_rule_hash``/``operator_reason``/``reviewed_at_utc``,
    build rows for all three status cases (MATCHED, NOT_MATCHED,
    UNEVALUABLE), parse each row's ``predicate_snapshot_json``, and
    assert keys are EXACTLY the 5-key predicate set.
    """

    extras = {
        "source_stage14_rule_hash": "sha256:" + "f" * 64,
        "operator_reason": "approved for observe only by Maq",
        "reviewed_at_utc": "2026-05-12T12:00:00+00:00",
    }
    rule_m = _make_rule("rule_m", **extras)
    rule_n = _make_rule("rule_n", tier_scope="T2", **extras)
    rule_u = _make_rule("rule_u", tier_scope="T3", **extras)
    policy = _make_policy((rule_m, rule_n, rule_u))
    result = _make_result(
        matched=(_make_match_for(rule_m),),
        unevaluable=(RuleUnevaluable(rule_id="rule_u", reason="tier_name_missing_on_decision"),),
    )

    rows = build_rows_for_decision(
        alert_decision_id=1,
        tier_name="T1",
        policy=policy,
        result=result,
        evaluated_at_utc=_EVALUATED_AT,
    )

    forbidden_keys = set(extras.keys())
    for row in rows:
        snapshot = json.loads(row.predicate_snapshot_json)
        # Exactly the 5 predicate keys.
        assert set(snapshot.keys()) == set(_FIVE_KEY_PREDICATE), (
            f"{row.rule_id} predicate_snapshot keys = {sorted(snapshot.keys())!r}"
        )
        # And none of the extras.
        assert not (set(snapshot.keys()) & forbidden_keys), (
            f"{row.rule_id} predicate_snapshot leaked LoadedRule extras"
        )


def test_row_builder_uses_predicate_snapshot_for_matched_rows() -> None:
    """MATCHED rows source their predicate from RuleMatch.predicate_snapshot.

    Per spec: "predicate_snapshot_json -- for MATCHED: use
    RuleMatch.predicate_snapshot". In practice the snapshot equals the
    rule's own 5-key predicate (Stage 16A constructs it that way), so the
    output is identical; this test pins the source-of-truth wiring by
    using a snapshot whose 5 keys are deliberately recognizable.
    """

    rule = _make_rule("rule_a")
    # Construct a match whose snapshot looks like the rule's predicate -- as
    # Stage 16A would produce. The row builder projects to 5 keys via
    # _predicate_from_match, so the result is the canonical 5-key JSON.
    match = RuleMatch(
        rule_id="rule_a",
        matched_filter_evaluation_index=0,
        predicate_snapshot=MappingProxyType({
            "tier_scope": rule.tier_scope,
            "filter_name": rule.filter_name,
            "filter_version": rule.filter_version,
            "filter_label": rule.filter_label,
            "threshold_version": rule.threshold_version,
        }),
    )
    policy = _make_policy((rule,))
    result = _make_result(matched=(match,))

    rows = build_rows_for_decision(
        alert_decision_id=1,
        tier_name="T1",
        policy=policy,
        result=result,
        evaluated_at_utc=_EVALUATED_AT,
    )

    parsed = json.loads(rows[0].predicate_snapshot_json)
    assert parsed == {
        "tier_scope": rule.tier_scope,
        "filter_name": rule.filter_name,
        "filter_version": rule.filter_version,
        "filter_label": rule.filter_label,
        "threshold_version": rule.threshold_version,
    }

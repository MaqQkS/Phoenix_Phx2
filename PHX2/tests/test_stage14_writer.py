"""Stage 14 writer determinism + content tests.

Covers:
  * shadow_policy_rules.json carries the literal Python False
    (JSON ``false``) at runtime_consumable.
  * CSV column order is locked.
  * Byte-identical reruns produce byte-identical bytes.
  * Empty inputs do not crash the writers.
  * The manifest is written with sorted keys + trailing newline.
"""

from __future__ import annotations

import json
from pathlib import Path

from PHX2.stage14.rules import compute_rule_id
from PHX2.stage14.types import (
    ImpactCounts,
    ReplayImpact,
    ReplayRow,
    RuleImpact,
    ShadowRule,
)
from PHX2.stage14.writer import (
    IMPACT_FILTER_CSV_COLUMNS,
    IMPACT_RULE_CSV_COLUMNS,
    IMPACT_TIER_CSV_COLUMNS,
    REPLAY_CSV_COLUMNS,
    SHADOW_POLICY_RULES_FILENAME,
    write_blocked_decisions,
    write_decision_diff,
    write_impact_by_filter,
    write_impact_by_rule,
    write_impact_by_tier,
    write_manifest,
    write_replay_results,
    write_review_markdown,
    write_run_log,
    write_saved_noise,
    write_shadow_policy_rules,
    write_would_have_blocked_winners,
)


def _rule(
    *,
    tier: str = "T1",
    label: str = "scam_likely",
    threshold: str = "v1",
) -> ShadowRule:
    rid = compute_rule_id(
        policy_surface="filter_label_blocking",
        tier_scope=tier,
        filter_name="fee_gate_v1",
        filter_version="v1",
        filter_label=label,
        threshold_version=threshold,
        simulated_action="SIMULATED_BLOCK",
    )
    return ShadowRule(
        rule_id=rid,
        policy_surface="filter_label_blocking",
        tier_scope=tier,
        filter_name="fee_gate_v1",
        filter_version="v1",
        filter_label=label,
        threshold_version=threshold,
        simulated_action="SIMULATED_BLOCK",
        direction="tighten",
        source_recommendations=(),
    )


def _replay(
    *,
    decision_id: str = "d1",
    triggering: tuple[str, ...] = (),
    decision_changed: bool = False,
    simulated_action: str = "SIMULATED_PASS",
    has_primary_outcome: bool | None = True,
    hit_2x: bool | None = False,
) -> ReplayRow:
    return ReplayRow(
        alert_decision_id=decision_id,
        token_address="Tok",
        tier_name="T1",
        original_action="would_alert",
        simulated_action=simulated_action,
        triggering_rule_ids=triggering,
        decision_changed=decision_changed,
        has_primary_outcome=has_primary_outcome,
        primary_outcome_hit_2x_24h=hit_2x,
        primary_outcome_hit_3x_24h=None,
        primary_outcome_hit_5x_24h=None,
    )


def test_shadow_policy_rules_runtime_consumable_is_json_false(tmp_path: Path) -> None:
    rule = _rule()
    path = write_shadow_policy_rules(tmp_path, [rule])
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["runtime_consumable"] is False
    # Reading the raw text confirms it is the bare JSON literal `false`
    # and not the string "false".
    text = path.read_text(encoding="utf-8")
    assert '"runtime_consumable": false' in text
    assert '"runtime_consumable": "false"' not in text


def test_shadow_policy_rules_filename_locked(tmp_path: Path) -> None:
    write_shadow_policy_rules(tmp_path, [_rule()])
    assert (tmp_path / SHADOW_POLICY_RULES_FILENAME).exists()


def test_shadow_policy_rules_rule_payload_shape(tmp_path: Path) -> None:
    rule = _rule()
    path = write_shadow_policy_rules(tmp_path, [rule])
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["allowed_actions"] == ["SIMULATED_BLOCK"]
    assert payload["rule_count"] == 1
    assert payload["rules"][0]["rule_id"] == rule.rule_id
    assert payload["rules"][0]["simulated_action"] == "SIMULATED_BLOCK"
    assert payload["rules"][0]["direction"] == "tighten"


def test_replay_results_header_matches_locked_columns(tmp_path: Path) -> None:
    path = write_replay_results(tmp_path, [_replay()])
    header = path.read_text(encoding="utf-8").splitlines()[0].split(",")
    assert tuple(header) == REPLAY_CSV_COLUMNS


def test_replay_results_byte_identical_reruns(tmp_path: Path) -> None:
    rows = [_replay(decision_id="d_b"), _replay(decision_id="d_a")]
    (tmp_path / "run1").mkdir(parents=True, exist_ok=True)
    (tmp_path / "run2").mkdir(parents=True, exist_ok=True)
    p1 = write_replay_results(tmp_path / "run1", rows)
    p2 = write_replay_results(tmp_path / "run2", list(reversed(rows)))
    assert p1.read_bytes() == p2.read_bytes()


def test_decision_diff_excludes_unchanged(tmp_path: Path) -> None:
    rows = [
        _replay(decision_id="changed", triggering=("r1",), decision_changed=True, simulated_action="SIMULATED_BLOCK"),
        _replay(decision_id="unchanged"),
    ]
    path = write_decision_diff(tmp_path, rows)
    body = path.read_text(encoding="utf-8")
    assert "changed" in body
    assert "unchanged" not in body


def test_blocked_decisions_only_blocks(tmp_path: Path) -> None:
    rows = [
        _replay(decision_id="b1", triggering=("r1",), decision_changed=True, simulated_action="SIMULATED_BLOCK"),
        _replay(decision_id="p1"),  # pass
    ]
    path = write_blocked_decisions(tmp_path, rows)
    body = path.read_text(encoding="utf-8")
    assert "b1" in body
    assert "p1" not in body


def test_would_have_blocked_winners_filters_to_2x_blocks(tmp_path: Path) -> None:
    rows = [
        _replay(
            decision_id="winner_blocked",
            triggering=("r1",),
            decision_changed=True,
            simulated_action="SIMULATED_BLOCK",
            has_primary_outcome=True,
            hit_2x=True,
        ),
        _replay(
            decision_id="loser_blocked",
            triggering=("r1",),
            decision_changed=True,
            simulated_action="SIMULATED_BLOCK",
            has_primary_outcome=True,
            hit_2x=False,
        ),
    ]
    path = write_would_have_blocked_winners(tmp_path, rows)
    body = path.read_text(encoding="utf-8")
    assert "winner_blocked" in body
    assert "loser_blocked" not in body


def test_saved_noise_filters_to_non_2x_blocks(tmp_path: Path) -> None:
    rows = [
        _replay(
            decision_id="winner_blocked",
            triggering=("r1",),
            decision_changed=True,
            simulated_action="SIMULATED_BLOCK",
            has_primary_outcome=True,
            hit_2x=True,
        ),
        _replay(
            decision_id="loser_blocked",
            triggering=("r1",),
            decision_changed=True,
            simulated_action="SIMULATED_BLOCK",
            has_primary_outcome=True,
            hit_2x=False,
        ),
    ]
    path = write_saved_noise(tmp_path, rows)
    body = path.read_text(encoding="utf-8")
    assert "loser_blocked" in body
    assert "winner_blocked" not in body


def test_impact_by_tier_header(tmp_path: Path) -> None:
    by_tier = {"overall": ImpactCounts(n_live_decisions=1), "T1": ImpactCounts()}
    path = write_impact_by_tier(tmp_path, by_tier)
    header = path.read_text(encoding="utf-8").splitlines()[0].split(",")
    assert tuple(header) == IMPACT_TIER_CSV_COLUMNS


def test_impact_by_tier_overall_first(tmp_path: Path) -> None:
    by_tier = {
        "T3": ImpactCounts(),
        "T1": ImpactCounts(),
        "T2": ImpactCounts(),
        "overall": ImpactCounts(),
    }
    path = write_impact_by_tier(tmp_path, by_tier)
    lines = path.read_text(encoding="utf-8").splitlines()
    # Header + 4 data rows
    assert len(lines) == 5
    assert lines[1].startswith("overall")
    assert lines[2].startswith("T1")
    assert lines[3].startswith("T2")
    assert lines[4].startswith("T3")


def test_impact_by_rule_header_and_warning_flags(tmp_path: Path) -> None:
    rule = _rule()
    rule_impact = RuleImpact(
        rule=rule,
        counts=ImpactCounts(n_simulated_blocks=3),
        n_matched=3,
        warning_flags=("small_n_rule", "high_winners_blocked_rate"),
    )
    by_tier = {"T1": ImpactCounts(n_live_decisions=10)}
    path = write_impact_by_rule(tmp_path, [rule_impact], by_tier)
    text = path.read_text(encoding="utf-8")
    header = text.splitlines()[0].split(",")
    assert tuple(header) == IMPACT_RULE_CSV_COLUMNS
    # Warning flags joined with ";"
    assert "small_n_rule;high_winners_blocked_rate" in text


def test_impact_by_filter_header(tmp_path: Path) -> None:
    by_filter = {"fee_gate_v1": ImpactCounts()}
    path = write_impact_by_filter(tmp_path, by_filter)
    header = path.read_text(encoding="utf-8").splitlines()[0].split(",")
    assert tuple(header) == IMPACT_FILTER_CSV_COLUMNS


def test_manifest_sorted_keys_and_trailing_newline(tmp_path: Path) -> None:
    payload = {"z": 1, "a": 2, "runtime_consumable": False}
    path = write_manifest(tmp_path, payload)
    text = path.read_text(encoding="utf-8")
    assert text.endswith("\n")
    # Parsed back, key order in raw text must be sorted alphabetically.
    raw_keys = [
        line.strip().split(":")[0].strip().strip('"')
        for line in text.splitlines()
        if ":" in line and not line.strip().startswith("{")
    ]
    assert raw_keys == sorted(raw_keys)


def test_run_log_writes_lines(tmp_path: Path) -> None:
    path = write_run_log(tmp_path, ["first event", "second event"])
    text = path.read_text(encoding="utf-8")
    assert text.endswith("\n")
    assert "first event" in text
    assert "second event" in text


def test_review_markdown_empty_inputs_does_not_crash(tmp_path: Path) -> None:
    manifest = {"run_timestamp_utc": "2026-05-12T12:00:00+00:00"}
    impact = ReplayImpact(
        by_tier={"overall": ImpactCounts()},
        by_rule=(),
        by_filter={},
        overall_warning_flags=("missing_outcome_data",),
    )
    path = write_review_markdown(
        tmp_path,
        manifest_dict=manifest,
        rules=[],
        excluded_count=0,
        impact=impact,
    )
    text = path.read_text(encoding="utf-8")
    assert "Stage 14 Shadow Policy Review" in text
    assert "missing_outcome_data" in text


def test_review_markdown_carries_rule_table(tmp_path: Path) -> None:
    rule = _rule()
    rule_impact = RuleImpact(
        rule=rule,
        counts=ImpactCounts(n_simulated_blocks=2, n_blocked_winners_2x=1),
        n_matched=2,
        warning_flags=("small_n_rule",),
    )
    impact = ReplayImpact(
        by_tier={"overall": ImpactCounts(n_live_decisions=2, n_simulated_blocks=2)},
        by_rule=(rule_impact,),
        by_filter={"fee_gate_v1": ImpactCounts(n_simulated_blocks=2)},
        overall_warning_flags=(),
    )
    manifest = {"run_timestamp_utc": "2026-05-12T12:00:00+00:00"}
    path = write_review_markdown(
        tmp_path,
        manifest_dict=manifest,
        rules=[rule],
        excluded_count=0,
        impact=impact,
    )
    text = path.read_text(encoding="utf-8")
    assert rule.rule_id in text
    assert "small_n_rule" in text

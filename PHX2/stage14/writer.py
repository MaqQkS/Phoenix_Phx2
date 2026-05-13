"""Stage 14 artifact writer.

Renders all 13 Stage 14 artifacts into a run directory with byte-level
determinism. Per the substrate locks:

  * CSV writes use ``lineterminator="\\n"``, na_rep="", floats with
    3 decimals, booleans as ``"true"``/``"false"``.
  * JSON writes use ``indent=2``, ``sort_keys=True``,
    ``ensure_ascii=False``, with a trailing newline.
  * Row order is locked per artifact (documented at each writer).
  * ``shadow_policy_rules.json`` carries ``runtime_consumable=false``
    at the top level. Stage 14's manifest carries
    ``safe_for_live_policy_consumption=false``.
  * The manifest is written LAST. Writers do not touch any path
    outside the run directory.
"""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path
from typing import Any, Iterable

from PHX2.stage14.types import (
    EXCESSIVE_BLOCK_RATE_THRESHOLD,
    HIGH_WINNERS_BLOCKED_RATE_THRESHOLD,
    ImpactCounts,
    MISSING_OUTCOME_DATA_OVERALL_THRESHOLD,
    ReplayImpact,
    ReplayRow,
    RUNTIME_CONSUMABLE,
    SMALL_N_RULE_THRESHOLD,
    ShadowRule,
    STAGE14_SCHEMA_VERSION,
    STAGE14_VERSION,
    UNKNOWN_OUTCOME_RATE_THRESHOLD,
)


# ---------------------------------------------------------------------------
# Locked file names
# ---------------------------------------------------------------------------


SHADOW_POLICY_RULES_FILENAME = "shadow_policy_rules.json"
EXCLUDED_RECOMMENDATIONS_FILENAME = "excluded_recommendations.csv"
REPLAY_RESULTS_FILENAME = "shadow_policy_replay_results.csv"
DECISION_DIFF_FILENAME = "shadow_vs_live_decision_diff.csv"
BLOCKED_DECISIONS_FILENAME = "blocked_decisions_simulated.csv"
WOULD_HAVE_BLOCKED_WINNERS_FILENAME = "would_have_blocked_winners.csv"
SAVED_NOISE_FILENAME = "saved_noise_simulated.csv"
IMPACT_BY_TIER_FILENAME = "impact_summary_by_tier.csv"
IMPACT_BY_RULE_FILENAME = "impact_summary_by_rule.csv"
IMPACT_BY_FILTER_FILENAME = "impact_summary_by_filter.csv"
REVIEW_MD_FILENAME = "stage14_shadow_policy_review.md"
RUN_LOG_FILENAME = "stage14_run.log"
MANIFEST_FILENAME = "manifest.json"


# ---------------------------------------------------------------------------
# Locked column orders
# ---------------------------------------------------------------------------


REPLAY_CSV_COLUMNS: tuple[str, ...] = (
    "alert_decision_id",
    "token_address",
    "tier_name",
    "original_action",
    "simulated_action",
    "decision_changed",
    "triggering_rule_ids",
    "n_triggering_rules",
    "has_primary_outcome",
    "primary_outcome_hit_2x_24h",
    "primary_outcome_hit_3x_24h",
    "primary_outcome_hit_5x_24h",
)


IMPACT_TIER_CSV_COLUMNS: tuple[str, ...] = (
    "tier_name",
    "n_live_decisions",
    "n_simulated_blocks",
    "n_blocked_with_primary_outcome",
    "n_blocked_winners_2x",
    "n_blocked_winners_3x",
    "n_blocked_winners_5x",
    "n_blocked_no_outcome",
)


IMPACT_RULE_CSV_COLUMNS: tuple[str, ...] = (
    "rule_id",
    "policy_surface",
    "tier_scope",
    "filter_name",
    "filter_version",
    "filter_label",
    "threshold_version",
    "simulated_action",
    "direction",
    "n_matched",
    "n_live_decisions_in_tier",
    "n_simulated_blocks",
    "n_blocked_with_primary_outcome",
    "n_blocked_winners_2x",
    "n_blocked_winners_3x",
    "n_blocked_winners_5x",
    "n_blocked_no_outcome",
    "warning_flags",
)


IMPACT_FILTER_CSV_COLUMNS: tuple[str, ...] = (
    "filter_name",
    "n_live_decisions",
    "n_simulated_blocks",
    "n_blocked_with_primary_outcome",
    "n_blocked_winners_2x",
    "n_blocked_winners_3x",
    "n_blocked_winners_5x",
    "n_blocked_no_outcome",
)


_TIER_SORT_ORDER: dict[str, int] = {
    "overall": 0,
    "T1": 1,
    "T2": 2,
    "T3": 3,
}


# ---------------------------------------------------------------------------
# Cell rendering helpers
# ---------------------------------------------------------------------------


def _format_bool(value: bool | None) -> str:
    if value is None:
        return ""
    return "true" if value else "false"


def _format_optional_string(value: str | None) -> str:
    if value is None:
        return ""
    return value


def _format_optional_int(value: int | None) -> str:
    if value is None:
        return ""
    return str(value)


def _format_rule_id_list(value: Iterable[str]) -> str:
    return ";".join(value)


def _write_csv_payload(path: Path, header: tuple[str, ...], rows: list[list[str]]) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(list(header))
    for row in rows:
        writer.writerow(row)
    payload = buffer.getvalue().encode("utf-8")
    path.write_bytes(payload)
    return payload


# ---------------------------------------------------------------------------
# shadow_policy_rules.json
# ---------------------------------------------------------------------------


def write_shadow_policy_rules(out_dir: Path, rules: list[ShadowRule]) -> Path:
    """Write shadow_policy_rules.json.

    Top-level fields:
      * stage14_version, stage14_schema_version: version pinning.
      * runtime_consumable: literal Python False (JSON ``false``).
      * allowed_actions: ``["SIMULATED_BLOCK"]`` -- the only action
        v0 emits, recorded explicitly so a downstream reader cannot
        assume more actions exist.
      * rule_count: convenience field equal to len(rules).
      * rules: sorted by rule_id (the translator already produces
        rules in this order; the JSON writer re-sorts defensively).

    Each rule's ``source_recommendations`` is sorted by cohort_id.
    """

    out_dir = Path(out_dir)
    path = out_dir / SHADOW_POLICY_RULES_FILENAME

    sorted_rules = sorted(rules, key=lambda r: r.rule_id)

    payload: dict[str, Any] = {
        "stage14_version": STAGE14_VERSION,
        "stage14_schema_version": STAGE14_SCHEMA_VERSION,
        "runtime_consumable": RUNTIME_CONSUMABLE,
        "allowed_actions": ["SIMULATED_BLOCK"],
        "rule_count": len(sorted_rules),
        "rules": [_rule_to_json(r) for r in sorted_rules],
    }

    with open(path, "w", encoding="utf-8", newline="") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True, ensure_ascii=False)
        handle.write("\n")
    return path


def _rule_to_json(rule: ShadowRule) -> dict[str, Any]:
    return {
        "rule_id": rule.rule_id,
        "policy_surface": rule.policy_surface,
        "tier_scope": rule.tier_scope,
        "filter_name": rule.filter_name,
        "filter_version": rule.filter_version,
        "filter_label": rule.filter_label,
        "threshold_version": rule.threshold_version,
        "simulated_action": rule.simulated_action,
        "direction": rule.direction,
        "source_row_count": rule.source_row_count,
        "source_recommendations": [
            {
                "cohort_id": s.cohort_id,
                "evidence_class": s.evidence_class,
                "policy_severity": s.policy_severity,
                "review_priority": s.review_priority,
                "n_complete": s.n_complete,
                "cohort_rate": s.cohort_rate,
                "baseline_rate": s.baseline_rate,
                "lift_absolute": s.lift_absolute,
                "lift_relative": s.lift_relative,
            }
            for s in rule.source_recommendations
        ],
    }


# ---------------------------------------------------------------------------
# excluded_recommendations.csv
# ---------------------------------------------------------------------------


def write_excluded_recommendations(
    out_dir: Path,
    excluded_rows: list,
    stage13_columns: tuple[str, ...],
) -> Path:
    """Write excluded_recommendations.csv.

    The header is the Stage 13 candidate CSV columns followed by an
    ``exclusion_reason`` column. Row values are preserved verbatim
    from the Stage 13 input so the file can be diffed byte-for-byte
    against the Stage 13 source. Rows are sorted by (policy_surface,
    cohort_id, tier_scope, action_class) -- the same order Stage 13
    uses for its own evidence_summary CSV.
    """

    out_dir = Path(out_dir)
    path = out_dir / EXCLUDED_RECOMMENDATIONS_FILENAME

    header = (*stage13_columns, "exclusion_reason")

    def _sort_key(item: Any) -> tuple[str, str, int, str]:
        raw = item.raw_row
        return (
            raw.get("policy_surface", ""),
            raw.get("cohort_id", ""),
            _TIER_SORT_ORDER.get(raw.get("tier_scope", ""), 99),
            raw.get("action_class", ""),
        )

    sorted_excluded = sorted(excluded_rows, key=_sort_key)

    rendered: list[list[str]] = []
    for excluded in sorted_excluded:
        row = excluded.raw_row
        rendered.append(
            [row.get(col, "") for col in stage13_columns] + [excluded.exclusion_reason]
        )

    _write_csv_payload(path, header, rendered)
    return path


# ---------------------------------------------------------------------------
# Replay CSVs (results + four derived views)
# ---------------------------------------------------------------------------


def _replay_row_to_cells(replay: ReplayRow) -> list[str]:
    return [
        replay.alert_decision_id,
        _format_optional_string(replay.token_address),
        _format_optional_string(replay.tier_name),
        _format_optional_string(replay.original_action),
        replay.simulated_action,
        _format_bool(replay.decision_changed),
        _format_rule_id_list(replay.triggering_rule_ids),
        str(replay.n_triggering_rules),
        _format_bool(replay.has_primary_outcome),
        _format_bool(replay.primary_outcome_hit_2x_24h),
        _format_bool(replay.primary_outcome_hit_3x_24h),
        _format_bool(replay.primary_outcome_hit_5x_24h),
    ]


def _write_replay_subset(
    path: Path, rows: list[ReplayRow]
) -> Path:
    rendered = [_replay_row_to_cells(r) for r in rows]
    _write_csv_payload(path, REPLAY_CSV_COLUMNS, rendered)
    return path


def write_replay_results(
    out_dir: Path, replay_rows: list[ReplayRow]
) -> Path:
    """Write shadow_policy_replay_results.csv (one row per decision)."""

    out_dir = Path(out_dir)
    sorted_rows = sorted(replay_rows, key=lambda r: r.alert_decision_id)
    return _write_replay_subset(out_dir / REPLAY_RESULTS_FILENAME, sorted_rows)


def write_decision_diff(
    out_dir: Path, replay_rows: list[ReplayRow]
) -> Path:
    """Write shadow_vs_live_decision_diff.csv (only decision_changed=true)."""

    out_dir = Path(out_dir)
    filtered = [r for r in replay_rows if r.decision_changed]
    sorted_rows = sorted(filtered, key=lambda r: r.alert_decision_id)
    return _write_replay_subset(out_dir / DECISION_DIFF_FILENAME, sorted_rows)


def write_blocked_decisions(
    out_dir: Path, replay_rows: list[ReplayRow]
) -> Path:
    """Write blocked_decisions_simulated.csv (simulated_action=BLOCK)."""

    out_dir = Path(out_dir)
    filtered = [r for r in replay_rows if r.simulated_action == "SIMULATED_BLOCK"]
    sorted_rows = sorted(filtered, key=lambda r: r.alert_decision_id)
    return _write_replay_subset(out_dir / BLOCKED_DECISIONS_FILENAME, sorted_rows)


def write_would_have_blocked_winners(
    out_dir: Path, replay_rows: list[ReplayRow]
) -> Path:
    """Write would_have_blocked_winners.csv.

    Only blocked decisions that have a primary outcome AND were 2x
    winners. This is the missed-winner proxy reviewers focus on.
    """

    out_dir = Path(out_dir)
    filtered = [
        r
        for r in replay_rows
        if r.decision_changed
        and r.has_primary_outcome is True
        and r.primary_outcome_hit_2x_24h is True
    ]
    sorted_rows = sorted(filtered, key=lambda r: r.alert_decision_id)
    return _write_replay_subset(out_dir / WOULD_HAVE_BLOCKED_WINNERS_FILENAME, sorted_rows)


def write_saved_noise(
    out_dir: Path, replay_rows: list[ReplayRow]
) -> Path:
    """Write saved_noise_simulated.csv.

    Blocked decisions that have a primary outcome AND did NOT 2x.
    These are the suppressions the shadow policy would have produced
    against decisions that did not pay off in the 24h window.
    """

    out_dir = Path(out_dir)
    filtered = [
        r
        for r in replay_rows
        if r.decision_changed
        and r.has_primary_outcome is True
        and r.primary_outcome_hit_2x_24h is False
    ]
    sorted_rows = sorted(filtered, key=lambda r: r.alert_decision_id)
    return _write_replay_subset(out_dir / SAVED_NOISE_FILENAME, sorted_rows)


# ---------------------------------------------------------------------------
# Impact summaries
# ---------------------------------------------------------------------------


def write_impact_by_tier(
    out_dir: Path, by_tier: dict[str, ImpactCounts]
) -> Path:
    out_dir = Path(out_dir)
    path = out_dir / IMPACT_BY_TIER_FILENAME

    def _sort_key(name: str) -> tuple[int, str]:
        return (_TIER_SORT_ORDER.get(name, 99), name)

    rendered: list[list[str]] = []
    for tier in sorted(by_tier.keys(), key=_sort_key):
        counts = by_tier[tier]
        rendered.append(_impact_counts_to_cells(tier, counts))

    _write_csv_payload(path, IMPACT_TIER_CSV_COLUMNS, rendered)
    return path


def _impact_counts_to_cells(key: str, counts: ImpactCounts) -> list[str]:
    return [
        key,
        str(counts.n_live_decisions),
        str(counts.n_simulated_blocks),
        str(counts.n_blocked_with_primary_outcome),
        str(counts.n_blocked_winners_2x),
        str(counts.n_blocked_winners_3x),
        str(counts.n_blocked_winners_5x),
        str(counts.n_blocked_no_outcome),
    ]


def write_impact_by_rule(
    out_dir: Path,
    by_rule: Iterable,
    by_tier: dict[str, ImpactCounts],
) -> Path:
    out_dir = Path(out_dir)
    path = out_dir / IMPACT_BY_RULE_FILENAME

    sorted_rules = sorted(by_rule, key=lambda r: r.rule.rule_id)

    rendered: list[list[str]] = []
    for rule_impact in sorted_rules:
        rule = rule_impact.rule
        tier_counts = by_tier.get(rule.tier_scope, ImpactCounts())
        rendered.append(
            [
                rule.rule_id,
                rule.policy_surface,
                rule.tier_scope,
                rule.filter_name,
                rule.filter_version,
                rule.filter_label,
                rule.threshold_version,
                rule.simulated_action,
                rule.direction,
                str(rule_impact.n_matched),
                str(tier_counts.n_live_decisions),
                str(rule_impact.counts.n_simulated_blocks),
                str(rule_impact.counts.n_blocked_with_primary_outcome),
                str(rule_impact.counts.n_blocked_winners_2x),
                str(rule_impact.counts.n_blocked_winners_3x),
                str(rule_impact.counts.n_blocked_winners_5x),
                str(rule_impact.counts.n_blocked_no_outcome),
                ";".join(rule_impact.warning_flags),
            ]
        )

    _write_csv_payload(path, IMPACT_RULE_CSV_COLUMNS, rendered)
    return path


def write_impact_by_filter(
    out_dir: Path, by_filter: dict[str, ImpactCounts]
) -> Path:
    out_dir = Path(out_dir)
    path = out_dir / IMPACT_BY_FILTER_FILENAME

    rendered: list[list[str]] = []
    for filter_name in sorted(by_filter.keys()):
        rendered.append(_impact_counts_to_cells(filter_name, by_filter[filter_name]))

    _write_csv_payload(path, IMPACT_FILTER_CSV_COLUMNS, rendered)
    return path


# ---------------------------------------------------------------------------
# Markdown review
# ---------------------------------------------------------------------------


_MARKDOWN_DISCLAIMER = (
    "> **No policy changes were applied, recommended, or queued for "
    "automatic application. Stage 14 reports what would have changed "
    "under a draft shadow policy replayed against historical "
    "decisions; human approval belongs to Stage 15, and any hard-block "
    "promotion is Stage 16+.**"
)


def write_review_markdown(
    out_dir: Path,
    *,
    manifest_dict: dict[str, Any],
    rules: list[ShadowRule],
    excluded_count: int,
    impact: ReplayImpact,
) -> Path:
    out_dir = Path(out_dir)
    path = out_dir / REVIEW_MD_FILENAME

    timestamp = manifest_dict.get("run_timestamp_utc", "?")
    overall_counts = impact.by_tier.get("overall", ImpactCounts())

    lines: list[str] = []
    lines.append(f"# Stage 14 Shadow Policy Review — {timestamp}")
    lines.append("")
    lines.append(_MARKDOWN_DISCLAIMER)
    lines.append("")

    lines.append("## Run metadata")
    lines.append("")
    lines.extend(_markdown_metadata_block(manifest_dict))
    lines.append("")

    if impact.overall_warning_flags:
        lines.append("## Replay-wide warnings")
        lines.append("")
        for flag in impact.overall_warning_flags:
            lines.append(f"- `{flag}`")
        lines.append("")

    lines.append("## Replay totals")
    lines.append("")
    lines.append(
        f"- Live alert decisions in scope: {overall_counts.n_live_decisions}"
    )
    lines.append(
        f"- Simulated blocks: {overall_counts.n_simulated_blocks}"
    )
    lines.append(
        f"- Of simulated blocks with a primary outcome: "
        f"{overall_counts.n_blocked_with_primary_outcome}"
    )
    lines.append(
        f"  - 2x winners that would have been blocked: "
        f"{overall_counts.n_blocked_winners_2x}"
    )
    lines.append(
        f"  - 3x winners that would have been blocked: "
        f"{overall_counts.n_blocked_winners_3x}"
    )
    lines.append(
        f"  - 5x winners that would have been blocked: "
        f"{overall_counts.n_blocked_winners_5x}"
    )
    lines.append(
        f"- Simulated blocks lacking a primary outcome: "
        f"{overall_counts.n_blocked_no_outcome}"
    )
    lines.append("")

    lines.append("## Translated rules")
    lines.append("")
    lines.append(f"- Rule count: {len(rules)}")
    lines.append(f"- Excluded recommendations: {excluded_count}")
    lines.append("")
    if rules:
        lines.extend(_markdown_rules_table(rules, impact))
    else:
        lines.append("_No eligible Stage 13 candidates translated to rules._")
        lines.append("")

    lines.append("## Impact by tier")
    lines.append("")
    lines.extend(_markdown_impact_tier_table(impact))

    lines.append("## Methodology")
    lines.append("")
    lines.append(
        "- Stage 14 reads only Stage 13's candidate CSV + manifest and "
        "Stage 12's decision_filter_outcome_long CSV + manifest. No DB "
        "connection is opened; no network call is made."
    )
    lines.append(
        "- Eligibility gate (locked): policy_surface=filter_label_blocking, "
        "action_class=ADVANCE_AS_CANDIDATE, direction=tighten, "
        "tier_scope in {T1, T2, T3}, all four filter-identity columns "
        "non-empty. Every Stage 13 candidate row is either translated "
        "into a shadow rule (preserving the source cohort_id) or written "
        "to excluded_recommendations.csv with a locked exclusion reason."
    )
    lines.append(
        "- Rule IDs are content-stable: SHA-256 over the identity tuple "
        "(policy_surface, tier_scope, filter_name, filter_version, "
        "filter_label, threshold_version, simulated_action). Reruns over "
        "the same Stage 13 candidate set produce the same rule IDs."
    )
    lines.append(
        "- Replay matches Stage 12 long-CSV rows by tuple (tier_name, "
        "filter_name, filter_version, filter_label, threshold_version). "
        "A decision is recorded as changed only when its original "
        "decision_type was 'would_alert' and at least one rule matched. "
        "Multiple matching rules collapse to a single SIMULATED_BLOCK "
        "with all triggering rule IDs recorded."
    )
    lines.append(
        "- Warning thresholds (advisory only): "
        f"small_n_rule<{SMALL_N_RULE_THRESHOLD}, "
        f"excessive_block_rate>{EXCESSIVE_BLOCK_RATE_THRESHOLD} "
        "(per-tier denominator), "
        f"high_winners_blocked_rate>{HIGH_WINNERS_BLOCKED_RATE_THRESHOLD} "
        "(2x winners among blocked-with-outcome), "
        f"unknown_outcome_rate>{UNKNOWN_OUTCOME_RATE_THRESHOLD} "
        "(no-outcome blocks among matched), "
        f"missing_outcome_data<{MISSING_OUTCOME_DATA_OVERALL_THRESHOLD} "
        "(primary-outcome share across live decisions)."
    )
    lines.append("")

    lines.append("## Non-goals")
    lines.append("")
    lines.append(
        "- Stage 14 does not classify a rule or policy as good or bad. "
        "All flags are advisory. Human approval is Stage 15."
    )
    lines.append(
        "- Stage 14 emits no threshold values, mutates no live config, "
        "and does not alter live alert behavior."
    )
    lines.append(
        "- Stage 14 does not create crossed or compound rules. The only "
        "simulated action in v0 is SIMULATED_BLOCK; the only direction is "
        "tighten; the only policy_surface is filter_label_blocking."
    )
    lines.append("")

    payload = "\n".join(lines)
    path.write_text(payload, encoding="utf-8", newline="")
    return path


def _markdown_metadata_block(manifest_dict: dict[str, Any]) -> list[str]:
    return [
        f"- Stage 14 version: {manifest_dict.get('stage14_version', '?')}",
        f"- Stage 14 schema_version: {manifest_dict.get('stage14_schema_version', '?')}",
        f"- Run timestamp (UTC): {manifest_dict.get('run_timestamp_utc', '?')}",
        f"- Stage 13 run path: {manifest_dict.get('stage13_run_path', '?')}",
        f"- Stage 13 manifest hash: {manifest_dict.get('stage13_manifest_hash', '?')}",
        f"- Stage 13 recommendation set version: "
        f"{manifest_dict.get('stage13_recommendation_set_version', '?')}",
        f"- Stage 12 run path: {manifest_dict.get('stage12_run_path', '?')}",
        f"- Stage 12 manifest hash: {manifest_dict.get('stage12_manifest_hash', '?')}",
        f"- Stage 12 long CSV hash: {manifest_dict.get('stage12_long_csv_hash', '?')}",
        f"- Primary outcome metric: {manifest_dict.get('primary_outcome_metric', '?')}",
        f"- safe_for_live_policy_consumption: "
        f"{manifest_dict.get('safe_for_live_policy_consumption')}",
        f"- runtime_consumable (rules JSON): "
        f"{manifest_dict.get('runtime_consumable')}",
        f"- Allowed actions: {manifest_dict.get('allowed_actions', '?')}",
        f"- Git commit: {manifest_dict.get('git_commit') or 'unavailable'}",
    ]


def _markdown_rules_table(
    rules: list[ShadowRule], impact: ReplayImpact
) -> list[str]:
    impact_by_rule_id: dict[str, Any] = {ri.rule.rule_id: ri for ri in impact.by_rule}
    headers = [
        "rule_id",
        "tier_scope",
        "filter_name",
        "filter_label",
        "threshold_version",
        "n_matched",
        "n_blocked_winners_2x",
        "n_blocked_no_outcome",
        "warning_flags",
    ]
    out = ["| " + " | ".join(headers) + " |"]
    out.append("| " + " | ".join(["---"] * len(headers)) + " |")
    for rule in sorted(rules, key=lambda r: r.rule_id):
        ri = impact_by_rule_id.get(rule.rule_id)
        if ri is None:
            n_matched = 0
            winners = 0
            no_out = 0
            flags = ""
        else:
            n_matched = ri.n_matched
            winners = ri.counts.n_blocked_winners_2x
            no_out = ri.counts.n_blocked_no_outcome
            flags = ";".join(ri.warning_flags)
        out.append(
            "| "
            + " | ".join(
                [
                    rule.rule_id,
                    rule.tier_scope,
                    rule.filter_name,
                    rule.filter_label,
                    rule.threshold_version,
                    str(n_matched),
                    str(winners),
                    str(no_out),
                    flags or "_(none)_",
                ]
            )
            + " |"
        )
    out.append("")
    return out


def _markdown_impact_tier_table(impact: ReplayImpact) -> list[str]:
    headers = [
        "tier_name",
        "n_live_decisions",
        "n_simulated_blocks",
        "n_blocked_with_primary_outcome",
        "n_blocked_winners_2x",
        "n_blocked_no_outcome",
    ]
    out = ["| " + " | ".join(headers) + " |"]
    out.append("| " + " | ".join(["---"] * len(headers)) + " |")

    def _sort_key(name: str) -> tuple[int, str]:
        return (_TIER_SORT_ORDER.get(name, 99), name)

    for tier in sorted(impact.by_tier.keys(), key=_sort_key):
        counts = impact.by_tier[tier]
        out.append(
            "| "
            + " | ".join(
                [
                    tier,
                    str(counts.n_live_decisions),
                    str(counts.n_simulated_blocks),
                    str(counts.n_blocked_with_primary_outcome),
                    str(counts.n_blocked_winners_2x),
                    str(counts.n_blocked_no_outcome),
                ]
            )
            + " |"
        )
    out.append("")
    return out


# ---------------------------------------------------------------------------
# Run log
# ---------------------------------------------------------------------------


def write_run_log(out_dir: Path, lines: list[str]) -> Path:
    """Write stage14_run.log.

    The pipeline composes the lines (one event per line, leading
    timestamp from the pinned ``now_utc`` for determinism). The file
    is a plain UTF-8 text log; no machine consumer reads it.
    """

    out_dir = Path(out_dir)
    path = out_dir / RUN_LOG_FILENAME
    payload = "\n".join(lines)
    if not payload.endswith("\n"):
        payload += "\n"
    path.write_text(payload, encoding="utf-8", newline="")
    return path


# ---------------------------------------------------------------------------
# Manifest (written LAST)
# ---------------------------------------------------------------------------


def write_manifest(out_dir: Path, manifest_dict: dict[str, Any]) -> Path:
    out_dir = Path(out_dir)
    path = out_dir / MANIFEST_FILENAME
    with open(path, "w", encoding="utf-8", newline="") as handle:
        json.dump(manifest_dict, handle, indent=2, sort_keys=True, ensure_ascii=False)
        handle.write("\n")
    return path

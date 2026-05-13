"""Stage 14 impact aggregation + advisory warning flags.

Given the translated rules and the per-decision replay rows, compute
three impact summaries (by tier, by rule, by filter_name) and attach
advisory warning flags. Stage 14 does NOT classify a rule or policy
as good or bad -- the flags are reviewer hints, not pass/fail
signals. Stage 15 owns the human-approval call.

All thresholds live as named constants in ``PHX2.stage14.types`` so
the markdown methodology section can name them precisely.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Iterable

from PHX2.stage14.types import (
    EXCESSIVE_BLOCK_RATE_THRESHOLD,
    HIGH_WINNERS_BLOCKED_RATE_THRESHOLD,
    MISSING_OUTCOME_DATA_OVERALL_THRESHOLD,
    SMALL_N_RULE_THRESHOLD,
    UNKNOWN_OUTCOME_RATE_THRESHOLD,
    WARNING_EXCESSIVE_BLOCK_RATE,
    WARNING_HIGH_WINNERS_BLOCKED_RATE,
    WARNING_MISSING_OUTCOME_DATA,
    WARNING_SMALL_N_RULE,
    WARNING_UNKNOWN_OUTCOME_RATE,
    WARNING_UNMATCHED_FILTER_TUPLE,
    ImpactCounts,
    ReplayImpact,
    ReplayRow,
    RuleImpact,
    ShadowRule,
)


WOULD_ALERT_DECISION_TYPE = "would_alert"


# ---------------------------------------------------------------------------
# Counter helper
# ---------------------------------------------------------------------------


class _CountAccumulator:
    """Mutable counter that materializes into ``ImpactCounts``.

    Kept private; ``compute_impact`` is the only call site. The seven
    fields correspond 1:1 with ``ImpactCounts``; adding a new metric
    means extending both this accumulator and the dataclass plus the
    writer's impact CSV column list.
    """

    __slots__ = (
        "n_live_decisions",
        "n_simulated_blocks",
        "n_blocked_with_primary_outcome",
        "n_blocked_winners_2x",
        "n_blocked_winners_3x",
        "n_blocked_winners_5x",
        "n_blocked_no_outcome",
    )

    def __init__(self) -> None:
        self.n_live_decisions = 0
        self.n_simulated_blocks = 0
        self.n_blocked_with_primary_outcome = 0
        self.n_blocked_winners_2x = 0
        self.n_blocked_winners_3x = 0
        self.n_blocked_winners_5x = 0
        self.n_blocked_no_outcome = 0

    def absorb_live(self) -> None:
        self.n_live_decisions += 1

    def absorb_block(self, replay_row: ReplayRow) -> None:
        self.n_simulated_blocks += 1
        if replay_row.has_primary_outcome is True:
            self.n_blocked_with_primary_outcome += 1
            if replay_row.primary_outcome_hit_2x_24h is True:
                self.n_blocked_winners_2x += 1
            if replay_row.primary_outcome_hit_3x_24h is True:
                self.n_blocked_winners_3x += 1
            if replay_row.primary_outcome_hit_5x_24h is True:
                self.n_blocked_winners_5x += 1
        else:
            self.n_blocked_no_outcome += 1

    def freeze(self) -> ImpactCounts:
        return ImpactCounts(
            n_live_decisions=self.n_live_decisions,
            n_simulated_blocks=self.n_simulated_blocks,
            n_blocked_with_primary_outcome=self.n_blocked_with_primary_outcome,
            n_blocked_winners_2x=self.n_blocked_winners_2x,
            n_blocked_winners_3x=self.n_blocked_winners_3x,
            n_blocked_winners_5x=self.n_blocked_winners_5x,
            n_blocked_no_outcome=self.n_blocked_no_outcome,
        )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def compute_impact(
    *,
    rules: Iterable[ShadowRule],
    replay_rows: Iterable[ReplayRow],
) -> ReplayImpact:
    """Aggregate replay rows into by-tier / by-rule / by-filter summaries.

    The tier dimension uses the long-CSV ``tier_name`` (T1/T2/T3 plus
    a special ``"overall"`` row that totals every decision regardless
    of tier). The filter dimension uses just ``filter_name`` (so all
    versions / labels / thresholds of one filter collapse together).

    Per-rule warning flags are computed against the per-tier total of
    the rule's tier, so the ``excessive_block_rate`` denominator is
    the live-decision count for that tier, not the run-wide total.
    """

    rules_list = list(rules)
    replay_list = list(replay_rows)

    by_tier_acc: dict[str, _CountAccumulator] = defaultdict(_CountAccumulator)
    overall_acc = _CountAccumulator()
    by_rule_acc: dict[str, _CountAccumulator] = {
        rule.rule_id: _CountAccumulator() for rule in rules_list
    }
    rule_id_to_rule: dict[str, ShadowRule] = {r.rule_id: r for r in rules_list}
    by_filter_acc: dict[str, _CountAccumulator] = defaultdict(_CountAccumulator)
    # Track unique filter_names that came from rules, so even
    # zero-impact filters appear in the by-filter summary.
    for rule in rules_list:
        _ = by_filter_acc[rule.filter_name]

    n_live_decisions = 0
    n_with_primary_outcome = 0

    for replay_row in replay_list:
        is_live = replay_row.original_action == WOULD_ALERT_DECISION_TYPE
        if not is_live:
            # Stage 12 in normal operation only emits would_alert rows,
            # but Stage 14 stays defensive: non-alerting decisions
            # never count toward live-decision totals and cannot be
            # "changed" even if a rule matched. They are silently
            # ignored for all impact metrics.
            continue

        n_live_decisions += 1
        tier = replay_row.tier_name or "unknown"
        by_tier_acc[tier].absorb_live()
        overall_acc.absorb_live()

        if replay_row.has_primary_outcome is True:
            n_with_primary_outcome += 1

        if not replay_row.decision_changed:
            continue

        # decision_changed == True implies simulated_action == SIMULATED_BLOCK
        # (replay enforces this) and the original was a live alert.
        by_tier_acc[tier].absorb_block(replay_row)
        overall_acc.absorb_block(replay_row)
        for rule_id in replay_row.triggering_rule_ids:
            acc = by_rule_acc.get(rule_id)
            if acc is None:
                # Defensive: a rule_id appeared in replay output but
                # is not in the rule set. Should not happen because
                # replay reads from the same rule tuple. Skip silently
                # rather than crash.
                continue
            acc.absorb_block(replay_row)
            rule = rule_id_to_rule[rule_id]
            by_filter_acc[rule.filter_name].absorb_block(replay_row)

    # Live-decision totals at the filter level: a filter's "live"
    # denominator is the sum of decisions in tiers where ANY rule of
    # that filter applies. For v0 we keep it simple and use the
    # run-wide live-decision count -- the same as the overall row's.
    # Per-tier numbers are still the precise breakdown and the
    # per-rule warnings drive on per-tier totals.
    for filter_name in by_filter_acc:
        by_filter_acc[filter_name].n_live_decisions = n_live_decisions

    by_tier_frozen: dict[str, ImpactCounts] = {
        tier: acc.freeze() for tier, acc in by_tier_acc.items()
    }
    by_tier_frozen["overall"] = overall_acc.freeze()
    by_filter_frozen: dict[str, ImpactCounts] = {
        name: acc.freeze() for name, acc in by_filter_acc.items()
    }

    by_rule_frozen: list[RuleImpact] = []
    for rule in rules_list:
        rule_counts = by_rule_acc[rule.rule_id].freeze()
        # n_matched at the rule level: every block this rule contributed
        # to corresponds to one decision in which the rule was in the
        # triggering set. n_matched == n_simulated_blocks for the rule.
        n_matched = rule_counts.n_simulated_blocks
        tier_counts = by_tier_frozen.get(rule.tier_scope, ImpactCounts())
        flags = _compute_rule_warning_flags(
            rule_counts=rule_counts,
            n_matched=n_matched,
            tier_live_total=tier_counts.n_live_decisions,
        )
        by_rule_frozen.append(
            RuleImpact(
                rule=rule,
                counts=rule_counts,
                n_matched=n_matched,
                warning_flags=flags,
            )
        )

    overall_flags = _compute_overall_warning_flags(
        n_live_decisions=n_live_decisions,
        n_with_primary_outcome=n_with_primary_outcome,
    )

    return ReplayImpact(
        by_tier=by_tier_frozen,
        by_rule=tuple(by_rule_frozen),
        by_filter=by_filter_frozen,
        overall_warning_flags=overall_flags,
    )


# ---------------------------------------------------------------------------
# Warning flag computation
# ---------------------------------------------------------------------------


def _compute_rule_warning_flags(
    *,
    rule_counts: ImpactCounts,
    n_matched: int,
    tier_live_total: int,
) -> tuple[str, ...]:
    """Compute the advisory warning-flag set for one rule.

    The order of flags in the returned tuple is the order they were
    evaluated; the writer joins them with ``";"`` deterministically.
    """

    flags: list[str] = []
    if n_matched == 0:
        flags.append(WARNING_UNMATCHED_FILTER_TUPLE)
    if 0 < n_matched < SMALL_N_RULE_THRESHOLD:
        # Only flag small_n when the rule matched at all; an
        # unmatched rule already carries the more specific flag.
        flags.append(WARNING_SMALL_N_RULE)
    if tier_live_total > 0:
        block_rate = n_matched / tier_live_total
        if block_rate > EXCESSIVE_BLOCK_RATE_THRESHOLD:
            flags.append(WARNING_EXCESSIVE_BLOCK_RATE)
    if rule_counts.n_blocked_with_primary_outcome > 0:
        winners_rate = (
            rule_counts.n_blocked_winners_2x
            / rule_counts.n_blocked_with_primary_outcome
        )
        if winners_rate > HIGH_WINNERS_BLOCKED_RATE_THRESHOLD:
            flags.append(WARNING_HIGH_WINNERS_BLOCKED_RATE)
    if n_matched > 0:
        unknown_rate = rule_counts.n_blocked_no_outcome / n_matched
        if unknown_rate > UNKNOWN_OUTCOME_RATE_THRESHOLD:
            flags.append(WARNING_UNKNOWN_OUTCOME_RATE)
    return tuple(flags)


def _compute_overall_warning_flags(
    *,
    n_live_decisions: int,
    n_with_primary_outcome: int,
) -> tuple[str, ...]:
    """Compute the replay-wide advisory flags.

    Currently only ``missing_outcome_data`` is run-wide -- the other
    flags are scoped to individual rules.
    """

    flags: list[str] = []
    if n_live_decisions == 0:
        # An empty replay carries the warning so the markdown surfaces
        # it; downstream rate computations would be undefined.
        flags.append(WARNING_MISSING_OUTCOME_DATA)
        return tuple(flags)
    outcome_share = n_with_primary_outcome / n_live_decisions
    if outcome_share < MISSING_OUTCOME_DATA_OVERALL_THRESHOLD:
        flags.append(WARNING_MISSING_OUTCOME_DATA)
    return tuple(flags)

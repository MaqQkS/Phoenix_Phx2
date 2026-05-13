"""Stage 14 historical replay.

Given the translated shadow rules and the Stage 12 long-CSV rows,
produce exactly one ``ReplayRow`` per unique ``alert_decision_id``.

The long CSV is decision × filter: a single alert_decision_id may
appear in zero (no filter evaluations) or many rows. The aggregation
rules below are LOCKED:

  * Match each long-CSV row against the rule index by the tuple
    ``(tier_name, filter_name, filter_version, filter_label,
    threshold_version)``. Rows missing any tuple component cannot
    match and are skipped during matching (they still contribute the
    decision's outcome fields if they are the only rows for that
    decision).
  * Collect all matching rule IDs across the decision's rows into a
    deduped + sorted tuple. ``n_triggering_rules`` is the length of
    this tuple AFTER dedup -- not the number of matching long rows.
  * ``simulated_action`` is ``SIMULATED_BLOCK`` when at least one rule
    matches, else ``SIMULATED_PASS``.
  * ``original_action`` is taken from the decision's first row's
    ``decision_type`` (Stage 12 produces the same value for every row
    of a given decision; tests assert on that consistency).
  * ``decision_changed`` is ``True`` only when the original action
    indicates the historical decision would have alerted
    (``decision_type == "would_alert"``) AND the simulated action is
    ``SIMULATED_BLOCK``. In particular, a decision whose live status
    was something other than ``would_alert`` is never counted as
    changed even if a rule happens to match -- the live system did
    not alert, so the shadow rule "blocking" is a no-op.
  * Outcome flags (``has_primary_outcome``, ``primary_outcome_hit_*``)
    are decision-level facts; the first row's values are used. Tests
    confirm Stage 12 emits identical values for every row of a
    decision.

The output tuple is sorted by ``alert_decision_id`` for deterministic
downstream byte stability.
"""

from __future__ import annotations

from collections import OrderedDict
from typing import Iterable

from PHX2.stage14.types import (
    LongCsvRow,
    ReplayRow,
    ShadowRule,
)


WOULD_ALERT_DECISION_TYPE = "would_alert"
"""Stage 12 vocabulary: the live status that indicates a decision
would have produced a live alert. Used to gate ``decision_changed``
so a SIMULATED_BLOCK on a non-alerting decision is recorded but does
not count as a behavioral change."""


SIMULATED_BLOCK = "SIMULATED_BLOCK"
SIMULATED_PASS = "SIMULATED_PASS"


# ---------------------------------------------------------------------------
# Rule index
# ---------------------------------------------------------------------------


def _build_rule_index(
    rules: Iterable[ShadowRule],
) -> dict[tuple[str, str, str, str, str], list[str]]:
    """Build a (tier_scope, filter_name, filter_version, filter_label,
    threshold_version) -> [rule_id] lookup.

    Multiple rules CAN share the same identity tuple in principle (the
    content-stable rule_id derivation only adds simulated_action to the
    tuple, which is always SIMULATED_BLOCK in v0). When that happens
    every matching rule_id is recorded against the long-CSV row.
    """

    index: dict[tuple[str, str, str, str, str], list[str]] = {}
    for rule in rules:
        key = (
            rule.tier_scope,
            rule.filter_name,
            rule.filter_version,
            rule.filter_label,
            rule.threshold_version,
        )
        index.setdefault(key, []).append(rule.rule_id)
    return index


# ---------------------------------------------------------------------------
# Per-decision aggregation
# ---------------------------------------------------------------------------


def replay(
    rules: Iterable[ShadowRule],
    long_rows: Iterable[LongCsvRow],
) -> tuple[ReplayRow, ...]:
    """Run the offline shadow-policy replay.

    Returns one ``ReplayRow`` per unique ``alert_decision_id``,
    sorted by ``alert_decision_id``.
    """

    rule_index = _build_rule_index(rules)

    # Preserve insertion order so identical inputs produce identical
    # intermediate state regardless of the final sort. The final
    # output is sorted by alert_decision_id; this OrderedDict is only
    # used during the aggregation pass.
    by_decision: "OrderedDict[str, _DecisionAggregate]" = OrderedDict()

    for row in long_rows:
        decision_id = row.alert_decision_id
        if decision_id == "":
            # Stage 12 should never emit an empty alert_decision_id;
            # if it does the row is data-corrupted and there is no way
            # to attribute its outcome to anything. Skip with no error
            # (Stage 14 reads, it does not validate Stage 12 beyond
            # the manifest schema_version).
            continue
        agg = by_decision.setdefault(decision_id, _DecisionAggregate(decision_id))
        agg.absorb(row, rule_index)

    out = [agg.to_replay_row() for agg in by_decision.values()]
    out.sort(key=lambda r: r.alert_decision_id)
    return tuple(out)


class _DecisionAggregate:
    """Mutable per-decision accumulator used during the aggregation pass.

    The first row sets the immutable decision-level fields
    (``token_address``, ``tier_name``, ``original_action``, outcome
    flags). Subsequent rows must agree on those fields by Stage 12's
    contract; this code does not enforce that strictly because Stage
    14 is a replay tool, not a Stage 12 validator -- a mismatch
    would only mean the first row's value wins, which is recoverable.

    Triggering rule IDs are accumulated into a set so duplicates are
    silently deduped; the final replay row sorts them deterministically.
    """

    __slots__ = (
        "alert_decision_id",
        "token_address",
        "tier_name",
        "original_action",
        "_rule_id_set",
        "has_primary_outcome",
        "primary_outcome_hit_2x_24h",
        "primary_outcome_hit_3x_24h",
        "primary_outcome_hit_5x_24h",
        "_decision_fields_initialized",
    )

    def __init__(self, alert_decision_id: str) -> None:
        self.alert_decision_id = alert_decision_id
        self.token_address: str | None = None
        self.tier_name: str | None = None
        self.original_action: str | None = None
        self._rule_id_set: set[str] = set()
        self.has_primary_outcome: bool | None = None
        self.primary_outcome_hit_2x_24h: bool | None = None
        self.primary_outcome_hit_3x_24h: bool | None = None
        self.primary_outcome_hit_5x_24h: bool | None = None
        self._decision_fields_initialized = False

    def absorb(
        self,
        row: LongCsvRow,
        rule_index: dict[tuple[str, str, str, str, str], list[str]],
    ) -> None:
        if not self._decision_fields_initialized:
            self.token_address = row.token_address
            self.tier_name = row.tier_name
            self.original_action = row.decision_type
            self.has_primary_outcome = row.has_primary_outcome
            self.primary_outcome_hit_2x_24h = row.primary_outcome_hit_2x_24h
            self.primary_outcome_hit_3x_24h = row.primary_outcome_hit_3x_24h
            self.primary_outcome_hit_5x_24h = row.primary_outcome_hit_5x_24h
            self._decision_fields_initialized = True

        # Match this row against the rule index.
        if not (
            row.tier_name
            and row.filter_name
            and row.filter_version
            and row.filter_label
            and row.threshold_version
        ):
            # Cannot form an identity tuple. Row is "no filter present"
            # or has incomplete filter identity; it contributes outcome
            # fields (already captured on first absorb) but no rule
            # matches.
            return
        key = (
            row.tier_name,
            row.filter_name,
            row.filter_version,
            row.filter_label,
            row.threshold_version,
        )
        matched = rule_index.get(key)
        if matched:
            self._rule_id_set.update(matched)

    def to_replay_row(self) -> ReplayRow:
        triggering = tuple(sorted(self._rule_id_set))
        simulated_action = SIMULATED_BLOCK if triggering else SIMULATED_PASS
        decision_changed = (
            self.original_action == WOULD_ALERT_DECISION_TYPE
            and simulated_action == SIMULATED_BLOCK
        )
        return ReplayRow(
            alert_decision_id=self.alert_decision_id,
            token_address=self.token_address,
            tier_name=self.tier_name,
            original_action=self.original_action,
            simulated_action=simulated_action,
            triggering_rule_ids=triggering,
            decision_changed=decision_changed,
            has_primary_outcome=self.has_primary_outcome,
            primary_outcome_hit_2x_24h=self.primary_outcome_hit_2x_24h,
            primary_outcome_hit_3x_24h=self.primary_outcome_hit_3x_24h,
            primary_outcome_hit_5x_24h=self.primary_outcome_hit_5x_24h,
        )

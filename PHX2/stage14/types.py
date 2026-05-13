"""Stage 14 type definitions.

The dataclasses below are the in-memory shape of the four kinds of
records that flow through Stage 14:

  * ``ShadowRule``     -- one translated rule produced from one or more
                          eligible Stage 13 ADVANCE_AS_CANDIDATE rows.
  * ``ExcludedRow``    -- one Stage 13 candidate row that did not meet
                          the v0 eligibility gate, plus its exclusion
                          reason from the locked vocabulary.
  * ``ReplayRow``      -- one historical alert_decision_id with its
                          original action, simulated action, and the
                          set of rule IDs that triggered.
  * ``RuleMatchSummary`` and the per-tier / per-filter summaries are
                          built by ``metrics.py`` for the impact CSVs.

Stage 14 emits ZERO threshold values and ZERO scored decisions. The
only allowed simulated action in v0 is SIMULATED_BLOCK; the only
direction is "tighten"; the only policy_surface is
"filter_label_blocking".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


# ---------------------------------------------------------------------------
# Version + safety constants (substrate-lock parity with Stage 13)
# ---------------------------------------------------------------------------


STAGE14_VERSION = "0.1.0"
STAGE14_SCHEMA_VERSION = "1.0"
"""Schema 1.0 (initial Stage 14 release): shadow_policy_rules.json,
excluded_recommendations.csv, shadow_policy_replay_results.csv,
shadow_vs_live_decision_diff.csv, blocked_decisions_simulated.csv,
would_have_blocked_winners.csv, saved_noise_simulated.csv,
impact_summary_by_tier.csv, impact_summary_by_rule.csv,
impact_summary_by_filter.csv, stage14_shadow_policy_review.md,
stage14_run.log, manifest.json."""


SAFE_FOR_LIVE_POLICY_CONSUMPTION: bool = False
"""Manifest invariant. Stage 14 outputs are exploratory replay
artifacts and MUST NOT be wired into any live-runtime consumer."""


RUNTIME_CONSUMABLE: bool = False
"""shadow_policy_rules.json invariant. The rule set is a hand-off to
Stage 15 (human approval) and Stage 16+ (potential promotion), not a
config file the runtime should ever read."""


PRIMARY_OUTCOME_METRIC = "hit_2x_24h"
"""The user-facing primary missed-winner proxy. 3x/5x metrics are also
computed for context but warning logic uses 2x as the operational
signal -- consistent with Stage 12's ``primary_outcome_hit_2x_24h``
column and Stage 13's ``PRIMARY_OUTCOME_METRIC``."""


# ---------------------------------------------------------------------------
# Locked vocabularies
# ---------------------------------------------------------------------------


PolicySurface = Literal["filter_label_blocking"]
"""Only filter_label_blocking is eligible in v0. primitive_bucket_cohort
rows are always excluded with ``not_filter_label_surface``."""


TierScope = Literal["T1", "T2", "T3"]
"""Eligible tier scopes. ``"overall"`` rows are always excluded with
``tier_scope_overall``."""


SimulatedAction = Literal["SIMULATED_BLOCK", "SIMULATED_PASS"]
"""The only simulated actions Stage 14 v0 emits. SIMULATED_BLOCK is
recorded when at least one matching rule fires; SIMULATED_PASS is the
no-change outcome (the live decision would have been unchanged)."""


Direction = Literal["tighten"]
"""Only tighten is eligible in v0. loosen and none rows are excluded."""


# ---------------------------------------------------------------------------
# Exclusion reasons (locked vocabulary; every excluded row maps to one)
# ---------------------------------------------------------------------------


EXCLUSION_NOT_FILTER_LABEL_SURFACE = "not_filter_label_surface"
EXCLUSION_NOT_ADVANCE_CANDIDATE = "not_advance_candidate"
EXCLUSION_NOT_TIGHTEN = "not_tighten"
EXCLUSION_TIER_SCOPE_OVERALL = "tier_scope_overall"
EXCLUSION_MISSING_FILTER_IDENTITY = "missing_filter_identity"


EXCLUSION_REASONS: tuple[str, ...] = (
    EXCLUSION_NOT_FILTER_LABEL_SURFACE,
    EXCLUSION_NOT_ADVANCE_CANDIDATE,
    EXCLUSION_NOT_TIGHTEN,
    EXCLUSION_TIER_SCOPE_OVERALL,
    EXCLUSION_MISSING_FILTER_IDENTITY,
)
"""Locked exclusion-reason vocabulary. The order is intentional: it
mirrors the gate order in ``rules.translate_recommendations`` so a row
fails on the *first* gate it violates and the reason is unambiguous."""


# ---------------------------------------------------------------------------
# Warning flag identifiers (advisory only, not pass/fail)
# ---------------------------------------------------------------------------


WARNING_UNMATCHED_FILTER_TUPLE = "unmatched_filter_tuple"
WARNING_SMALL_N_RULE = "small_n_rule"
WARNING_EXCESSIVE_BLOCK_RATE = "excessive_block_rate"
WARNING_HIGH_WINNERS_BLOCKED_RATE = "high_winners_blocked_rate"
WARNING_UNKNOWN_OUTCOME_RATE = "unknown_outcome_rate"
WARNING_MISSING_OUTCOME_DATA = "missing_outcome_data"


WARNING_FLAGS: tuple[str, ...] = (
    WARNING_UNMATCHED_FILTER_TUPLE,
    WARNING_SMALL_N_RULE,
    WARNING_EXCESSIVE_BLOCK_RATE,
    WARNING_HIGH_WINNERS_BLOCKED_RATE,
    WARNING_UNKNOWN_OUTCOME_RATE,
    WARNING_MISSING_OUTCOME_DATA,
)


# ---------------------------------------------------------------------------
# Warning thresholds (v0 advisory constants)
# ---------------------------------------------------------------------------


SMALL_N_RULE_THRESHOLD: int = 10
"""A rule that matches fewer than this many historical decisions is
flagged as ``small_n_rule``. Below 10, the per-rule diagnostics are
unstable; reviewers should treat the rule as anecdotal."""


EXCESSIVE_BLOCK_RATE_THRESHOLD: float = 0.3
"""A rule whose simulated blocks account for more than 30% of
historical live alerts in its tier is flagged as
``excessive_block_rate``. Blocking even a third of past alerts is a
sizable intervention, so the threshold sits well below the
naive-50% reading; the lower trip point surfaces broad rules earlier
for reviewer attention. Advisory only -- no pipeline branch depends
on this flag."""


HIGH_WINNERS_BLOCKED_RATE_THRESHOLD: float = 0.3
"""Among the rule's simulated blocks that have a primary outcome, when
more than 30% are 2x winners the rule is flagged as
``high_winners_blocked_rate`` -- it would have suppressed a notable
share of the very kind of decision the live system is supposed to
surface."""


UNKNOWN_OUTCOME_RATE_THRESHOLD: float = 0.3
"""When more than 30% of a rule's simulated blocks lack a primary
outcome, the rule is flagged as ``unknown_outcome_rate`` -- the
historical data are not sufficient to evaluate the rule's effect."""


MISSING_OUTCOME_DATA_OVERALL_THRESHOLD: float = 0.5
"""Replay-wide flag. When fewer than 50% of historical alert decisions
have a primary outcome, the entire run is flagged as
``missing_outcome_data`` and the markdown surfaces the warning at the
top so reviewers do not over-interpret rate-based diagnostics."""


# ---------------------------------------------------------------------------
# Rule + payload dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SourceRecommendation:
    """One Stage 13 candidate row that contributed to a shadow rule.

    Preserved verbatim from the Stage 13 input so reviewers can audit
    the original evidence without re-opening the Stage 13 run dir.
    Multiple ``SourceRecommendation`` entries may share a rule when
    duplicate Stage 13 rows collapse to the same content-stable rule
    ID (defensive against malformed inputs; expected in well-formed
    Stage 13 runs is exactly one).
    """

    cohort_id: str
    evidence_class: str | None
    policy_severity: str | None
    review_priority: str | None
    n_complete: int | None
    cohort_rate: float | None
    baseline_rate: float | None
    lift_absolute: float | None
    lift_relative: float | None


@dataclass(frozen=True)
class ShadowRule:
    """One translated shadow rule.

    ``rule_id`` is a content-stable short hash over the identity tuple
    (policy_surface, tier_scope, filter_name, filter_version,
    filter_label, threshold_version, simulated_action). Reruns over the
    same Stage 13 candidate set produce the same rule_id even if the
    input row order changes or new candidates are inserted before the
    old ones.

    ``source_recommendations`` is sorted by cohort_id for deterministic
    payload bytes.
    """

    rule_id: str
    policy_surface: str
    tier_scope: str
    filter_name: str
    filter_version: str
    filter_label: str
    threshold_version: str
    simulated_action: str
    direction: str
    source_recommendations: tuple[SourceRecommendation, ...]

    @property
    def source_row_count(self) -> int:
        return len(self.source_recommendations)


@dataclass(frozen=True)
class ExcludedRow:
    """One Stage 13 candidate row that did not become a shadow rule.

    Every field is the raw Stage 13 column value (preserved as a
    string so the excluded CSV round-trips byte-for-byte with the
    Stage 13 input). ``exclusion_reason`` is drawn from the locked
    vocabulary in ``EXCLUSION_REASONS``.
    """

    raw_row: dict[str, str]
    exclusion_reason: str


@dataclass(frozen=True)
class LongCsvRow:
    """One row of Stage 12's decision_filter_outcome_long.csv.

    Stage 14 cares only about the identity + outcome subset; other
    columns (filter_score, filter_reason, etc.) are read into a raw
    dict by the loader but Stage 14's replay/metrics code uses only
    these typed fields.
    """

    alert_decision_id: str
    token_address: str | None
    tier_index: int | None
    tier_name: str | None
    decision_type: str | None
    filter_name: str | None
    filter_version: str | None
    filter_label: str | None
    threshold_version: str | None
    has_primary_outcome: bool | None
    primary_outcome_hit_2x_24h: bool | None
    primary_outcome_hit_3x_24h: bool | None
    primary_outcome_hit_5x_24h: bool | None


# ---------------------------------------------------------------------------
# Replay output
# ---------------------------------------------------------------------------


@dataclass
class ReplayRow:
    """One alert_decision_id's replay outcome.

    Stage 12's long CSV is decision × filter rows; ``replay.py``
    aggregates these into exactly one ``ReplayRow`` per unique
    ``alert_decision_id``. ``triggering_rule_ids`` is deduped + sorted;
    ``n_triggering_rules`` is the length of that tuple after dedup. The
    outcome flags are taken once per decision (they are decision-level
    facts, identical across the decision's filter rows).
    """

    alert_decision_id: str
    token_address: str | None
    tier_name: str | None
    original_action: str | None
    simulated_action: str
    triggering_rule_ids: tuple[str, ...]
    decision_changed: bool
    has_primary_outcome: bool | None
    primary_outcome_hit_2x_24h: bool | None
    primary_outcome_hit_3x_24h: bool | None
    primary_outcome_hit_5x_24h: bool | None

    @property
    def n_triggering_rules(self) -> int:
        return len(self.triggering_rule_ids)


# ---------------------------------------------------------------------------
# Metrics summaries
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ImpactCounts:
    """Aggregate counts produced by ``metrics.py``.

    Used as the row payload for impact_summary_by_tier,
    impact_summary_by_rule, and impact_summary_by_filter; the writer
    flattens these onto each CSV's locked column order.
    """

    n_live_decisions: int = 0
    n_simulated_blocks: int = 0
    n_blocked_with_primary_outcome: int = 0
    n_blocked_winners_2x: int = 0
    n_blocked_winners_3x: int = 0
    n_blocked_winners_5x: int = 0
    n_blocked_no_outcome: int = 0


@dataclass(frozen=True)
class RuleImpact:
    """Per-rule impact summary + warning flags.

    ``n_matched`` is the number of historical alert_decision_ids in
    which this rule appeared in ``triggering_rule_ids``. It is the
    denominator for the per-rule warning logic.
    """

    rule: ShadowRule
    counts: ImpactCounts
    n_matched: int
    warning_flags: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class ReplayImpact:
    """Full per-replay impact bundle returned by ``metrics.compute_impact``.

    ``overall_warning_flags`` carries replay-wide warnings (currently
    only ``missing_outcome_data``); per-rule warnings live on each
    ``RuleImpact``.
    """

    by_tier: dict[str, ImpactCounts]
    by_rule: tuple[RuleImpact, ...]
    by_filter: dict[str, ImpactCounts]
    overall_warning_flags: tuple[str, ...]

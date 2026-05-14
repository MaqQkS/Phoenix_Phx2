"""Stage 16B frozen dataclasses for one telemetry row and the per-run observer report; pure data, no I/O."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class ObserveOnlyEvaluationRow:
    """One Stage 16B telemetry row produced by the row builder.

    Fields mirror the ``observe_only_policy_evaluations`` table verbatim
    EXCEPT for ``created_at_utc`` -- that column is stamped by the
    repository at insert time, not by the row builder, so it deliberately
    does not appear on the dataclass.

    ``frozen=True`` means a row cannot be mutated after construction; the
    observer pipeline always emits the row exactly once and immediately
    hands it to the repository.

    The locked posture rules (per the compound CHECK in the table DDL)
    are NOT re-enforced here -- they are the table's job. Callers (the
    row builder) construct rows in the three valid postures only:

      MATCHED      -> matched=1, would_have_blocked=1, unevaluable_reason=None
      NOT_MATCHED  -> matched=0, would_have_blocked=0, unevaluable_reason=None
      UNEVALUABLE  -> matched=0, would_have_blocked=0, unevaluable_reason=<reason>
    """

    alert_decision_id: int
    tier_name_snapshot: Optional[str]
    policy_hash: str
    rule_id: str
    evaluation_status: str
    matched: int
    would_have_blocked: int
    unevaluable_reason: Optional[str]
    predicate_snapshot_json: str
    evaluated_at_utc: str


@dataclass(frozen=True)
class ObserverRunReport:
    """Per-run summary returned by ``ObserveOnlyObserverService.run_once``.

    Carries the policy identity, the inventory the observer consumed, and
    the bucketed counter outcomes. Used by the CLI to render the single
    summary line and by tests to assert behavior.
    """

    policy_hash: str
    policy_rule_count: int
    alert_decisions_evaluated: int
    rows_inserted: int
    rows_ignored_duplicates: int
    decisions_skipped_not_found: int
    matched_count: int
    not_matched_count: int
    unevaluable_count: int
    evaluation_duration_seconds: float

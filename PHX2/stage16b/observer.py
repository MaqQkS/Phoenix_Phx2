"""Sidecar one-shot observer. Reads already-committed alert decisions, evaluates against an observe-only runtime policy via Stage 16A's pure evaluator, writes append-only telemetry. NEVER returns a value consumed by alert eligibility or dispatch. NEVER mutates any upstream table. Safe to never run; safe to crash."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Callable

from PHX2.stage16a.models import LoadedObserveOnlyPolicy
from PHX2.stage16b.models import ObserverRunReport
from PHX2.stage16b.row_builder import build_rows_for_decision


class ObserveOnlyObserverService:
    """Orchestration-only sidecar observer.

    Wires together the four collaborators Stage 16B owns plus Stage 16A's
    pure evaluator. The observer:

      1. Loads a Stage 16A runtime policy via the injected loader.
      2. Builds an evaluator instance from the loaded policy via the
         injected factory (Stage 16A's ``ObserveOnlyPolicyEvaluator`` in
         production).
      3. Enumerates the WOULD_ALERT alert_decision ids whose telemetry
         for this policy is missing.
      4. For each id, assembles a Stage 16A ``DecisionContext``, runs
         the evaluator (defensively asserts the result's policy_hash),
         translates the result into telemetry rows via the row builder,
         and writes them through the append-only repository.

    The observer NEVER implements predicate matching itself -- that is
    Stage 16A's ``ObserveOnlyPolicyEvaluator``. The observer NEVER
    issues SQL directly; every read goes through the assembler and
    every write goes through the repository. The observer NEVER mutates
    ``alert_decisions`` or ``filter_evaluations``: those are read-only
    inputs.

    Per-decision durable progress: the repository's
    ``_commit_if_top_level`` convention commits after each
    ``insert_evaluation_rows`` call. If the observer crashes mid-run,
    already-evaluated decisions remain durable; the next run picks up
    where the previous run left off because ``list_alert_decision_ids_missing_policy_eval``
    excludes any decision that has at least one telemetry row for the
    given policy_hash.
    """

    def __init__(
        self,
        policy_loader,
        evaluator_factory,
        assembler,
        repository,
        clock: Callable[[], str],
    ) -> None:
        self._policy_loader = policy_loader
        self._evaluator_factory = evaluator_factory
        self._assembler = assembler
        self._repository = repository
        self._clock = clock

    def run_once(
        self,
        runtime_policy_path: Path,
        limit: int,
    ) -> ObserverRunReport:
        """Process up to ``limit`` un-evaluated WOULD_ALERT decisions.

        Returns an ``ObserverRunReport`` summarizing the run. Total rows
        emitted always equals ``alert_decisions_evaluated *
        policy_rule_count``; the breakdown by status
        (``matched_count + not_matched_count + unevaluable_count``)
        equals total emitted rows; ``rows_inserted +
        rows_ignored_duplicates`` also equals total emitted rows.

        On empty policy (``policy.rules == ()``) returns immediately
        with all counters zero -- no decisions are queried, no
        evaluator is built.

        Raises ``RuntimeError`` if the Stage 16A evaluator returns a
        result whose ``policy_hash`` does not match the loaded policy's
        hash (defensive: this is a programmer-error condition because
        the evaluator is constructed from the policy itself).
        """

        start_perf = time.perf_counter()

        # 1. Load the policy via Stage 16A's loader.
        policy: LoadedObserveOnlyPolicy = self._policy_loader.load(runtime_policy_path)

        # 2. Empty policy -> clean empty report. Skip the
        #    evaluator-factory call and the list_missing query.
        if not policy.rules:
            duration = time.perf_counter() - start_perf
            return ObserverRunReport(
                policy_hash=policy.policy_hash,
                policy_rule_count=0,
                alert_decisions_evaluated=0,
                rows_inserted=0,
                rows_ignored_duplicates=0,
                decisions_skipped_not_found=0,
                matched_count=0,
                not_matched_count=0,
                unevaluable_count=0,
                evaluation_duration_seconds=duration,
            )

        # 3. Build an evaluator instance from the loaded policy.
        evaluator = self._evaluator_factory(policy)

        # 4. Enumerate the un-evaluated WOULD_ALERT decision ids.
        decision_ids = (
            self._repository.list_alert_decision_ids_missing_policy_eval(
                policy_hash=policy.policy_hash,
                limit=limit,
            )
        )

        # 5. Per-decision pipeline.
        alert_decisions_evaluated = 0
        rows_inserted = 0
        rows_total_emitted = 0
        decisions_skipped_not_found = 0
        matched_count = 0
        not_matched_count = 0
        unevaluable_count = 0

        for decision_id in decision_ids:
            context = self._assembler.assemble(decision_id)
            if context is None:
                # Decision was committed when list_missing queried but
                # vanished before the assembler could read it (extremely
                # rare; e.g., concurrent DB management). Count it and
                # move on rather than crashing the whole run.
                decisions_skipped_not_found += 1
                continue

            result = evaluator.evaluate_for_decision(context)

            # Defensive: the evaluator was built from `policy`, so its
            # result must carry the same policy_hash. A mismatch implies
            # a programmer-error in the evaluator_factory wiring.
            if result.policy_hash != policy.policy_hash:
                raise RuntimeError(
                    f"Stage 16A evaluator returned policy_hash="
                    f"{result.policy_hash!r}, expected "
                    f"{policy.policy_hash!r}"
                )

            evaluated_at_utc = self._clock()
            rows = build_rows_for_decision(
                alert_decision_id=decision_id,
                tier_name=context.tier_name,
                policy=policy,
                result=result,
                evaluated_at_utc=evaluated_at_utc,
            )

            inserted = self._repository.insert_evaluation_rows(rows)

            alert_decisions_evaluated += 1
            rows_inserted += inserted
            rows_total_emitted += len(rows)
            for row in rows:
                if row.evaluation_status == "MATCHED":
                    matched_count += 1
                elif row.evaluation_status == "NOT_MATCHED":
                    not_matched_count += 1
                else:  # "UNEVALUABLE"
                    unevaluable_count += 1

        rows_ignored_duplicates = rows_total_emitted - rows_inserted
        duration = time.perf_counter() - start_perf

        return ObserverRunReport(
            policy_hash=policy.policy_hash,
            policy_rule_count=len(policy.rules),
            alert_decisions_evaluated=alert_decisions_evaluated,
            rows_inserted=rows_inserted,
            rows_ignored_duplicates=rows_ignored_duplicates,
            decisions_skipped_not_found=decisions_skipped_not_found,
            matched_count=matched_count,
            not_matched_count=not_matched_count,
            unevaluable_count=unevaluable_count,
            evaluation_duration_seconds=duration,
        )

"""Stage 23.5 offline observe-only runner.

The runner evaluates the three landed Stage 23 filters
(``holder_concentration``, ``launch_structure``,
``wallet_source_quality``) against every
``Stage23FilterInput`` the caller supplies and returns a
deterministic ``Stage23RunnerResult``. The runner is pure:

  * It performs NO network I/O, no env reads, no clock reads,
    no disk writes. ``created_at_utc`` is injected by the
    caller; the runner forwards it to the
    ``Stage23FilterEvaluation`` builder.
  * It never dispatches alerts, never routes to external
    transports, and never enforces or blocks anything. Stage 23
    is observe-only.
  * It catches *typed* ``Stage23Error`` subclasses raised by
    individual filters and converts each into a deterministic
    ``UNKNOWN`` / ``MISSING`` evaluation so the runner output
    remains complete. Untyped programmer errors propagate
    unchanged.
  * It never mutates its input objects.

Surfaces:

  * ``Stage23RunnerResult``   -- immutable ``NamedTuple`` bundling
                                  the evaluations and the aggregated
                                  count snapshots.
  * ``run_stage23_filters``   -- pure function that runs the locked
                                  default filter set (or a
                                  caller-supplied substitute) over
                                  the supplied inputs.
  * ``default_filters``       -- pure factory returning the locked
                                  default filter set, primarily for
                                  tests that want to drive the
                                  filters through the same Protocol
                                  surface the runner uses.

This module imports only stdlib (``collections`` / ``types`` /
``typing``) plus the Stage 23 constants / errors / models /
filter contracts / three landed filter modules. It does NOT
import Stage 21 or Stage 22 modules, does NOT import any
network / RPC / messaging / DB / scheduler / secrets-management
library, does NOT read the process environment, does NOT define
a CLI surface, contains no top-level I/O, and writes nothing to
disk.
"""

from __future__ import annotations

from collections import Counter
from types import MappingProxyType
from typing import Mapping, NamedTuple, Sequence

from PHX2.stage23.constants import (
    DATA_STATUS_MISSING,
    LABEL_UNKNOWN,
)
from PHX2.stage23.errors import Stage23ContractError, Stage23Error
from PHX2.stage23.filter_contracts import Stage23Filter
from PHX2.stage23.holder_concentration import HolderConcentrationFilter
from PHX2.stage23.launch_structure import LaunchStructureFilter
from PHX2.stage23.models import (
    Stage23FilterEvaluation,
    Stage23FilterInput,
    Stage23FilterResult,
    build_filter_evaluation,
    build_filter_result,
)
from PHX2.stage23.wallet_source_quality import WalletSourceQualityFilter


# ---------------------------------------------------------------------------
# Runner-injected reason code (closed set)
# ---------------------------------------------------------------------------
#
# The runner constructs synthetic ``Stage23FilterResult`` records
# when a filter raises a typed ``Stage23Error``. The synthetic
# result uses the closed-set ``UNKNOWN`` label and ``MISSING``
# data status, with this single reason code naming the runner-
# injected error path. The reason code is intentionally distinct
# from any per-filter reason vocabulary so an operator scanning
# artifacts can isolate runner-injected error records.


REASON_STAGE23_FILTER_RAISED_ERROR: str = (
    "STAGE23_FILTER_RAISED_ERROR"
)


STAGE23_RUNNER_REASON_CODES: tuple[str, ...] = (
    REASON_STAGE23_FILTER_RAISED_ERROR,
)


# ---------------------------------------------------------------------------
# Default filter set
# ---------------------------------------------------------------------------


def default_filters() -> tuple[Stage23Filter, ...]:
    """Return the locked Stage 23 default filter set.

    The default set is the three Stage 23 observe-only filters
    landed across 23.2 / 23.3 / 23.4. Order is deterministic
    and matches the closed-set ``FILTER_FAMILIES`` ordering
    (holder -> launch -> wallet/source).
    """
    return (
        HolderConcentrationFilter(),
        LaunchStructureFilter(),
        WalletSourceQualityFilter(),
    )


# ---------------------------------------------------------------------------
# Stage23RunnerResult
# ---------------------------------------------------------------------------


class Stage23RunnerResult(NamedTuple):
    """Immutable result record for one Stage 23 runner invocation.

    Fields:

      * ``evaluations``         -- tuple of
                                   ``Stage23FilterEvaluation`` records
                                   sorted deterministically by
                                   ``(token_mint, event_id,
                                   captured_event_id, filter_name)``.
      * ``input_count``         -- count of inputs supplied to the
                                   runner.
      * ``evaluation_count``    -- count of evaluations produced
                                   (always ``input_count *
                                   filter_count``).
      * ``filter_count``        -- count of filters the runner
                                   evaluated (3 by default).
      * ``label_counts``        -- frozen mapping label -> count.
                                   Keys sorted ascending.
      * ``data_status_counts``  -- frozen mapping data_status ->
                                   count. Keys sorted ascending.
      * ``reason_code_counts``  -- frozen mapping reason_code ->
                                   count. Keys sorted ascending.
      * ``created_at_utc``      -- ISO-8601 UTC string the caller
                                   supplied; forwarded onto every
                                   evaluation record.
    """

    evaluations: tuple[Stage23FilterEvaluation, ...]
    input_count: int
    evaluation_count: int
    filter_count: int
    label_counts: Mapping[str, int]
    data_status_counts: Mapping[str, int]
    reason_code_counts: Mapping[str, int]
    created_at_utc: str


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _build_error_result(
    *,
    filter_obj: Stage23Filter,
) -> Stage23FilterResult:
    """Build the ``UNKNOWN`` / ``MISSING`` result for a runner-caught error.

    The result reuses the filter's own identity strings so the
    record remains attributable to the filter that raised the
    error. ``numeric_features`` is empty and ``missing_features``
    is empty because the runner has no projection to report.
    """
    return build_filter_result(
        filter_name=filter_obj.filter_name,
        filter_family=filter_obj.filter_family,
        filter_version=filter_obj.filter_version,
        threshold_version=filter_obj.threshold_version,
        label=LABEL_UNKNOWN,
        data_status=DATA_STATUS_MISSING,
        reason_codes=(REASON_STAGE23_FILTER_RAISED_ERROR,),
        numeric_features=MappingProxyType({}),
        missing_features=(),
    )


def _evaluate_one(
    *,
    filter_obj: Stage23Filter,
    filter_input: Stage23FilterInput,
) -> Stage23FilterResult:
    """Run one filter against one input, catching typed Stage23 errors.

    Untyped programmer errors are NOT caught -- they propagate
    so the test surface notices.
    """
    try:
        return filter_obj.evaluate(filter_input=filter_input)
    except Stage23Error:
        return _build_error_result(filter_obj=filter_obj)


def _evaluation_sort_key(
    evaluation: Stage23FilterEvaluation,
) -> tuple[str, str, str, str]:
    return (
        evaluation.filter_input.token_mint,
        evaluation.filter_input.event_id,
        evaluation.filter_input.captured_event_id,
        evaluation.filter_result.filter_name,
    )


def _frozen_sorted_counter(counter: Counter[str]) -> Mapping[str, int]:
    return MappingProxyType(
        {key: counter[key] for key in sorted(counter.keys())}
    )


# ---------------------------------------------------------------------------
# Public runner surface
# ---------------------------------------------------------------------------


def run_stage23_filters(
    *,
    filter_inputs: Sequence[Stage23FilterInput],
    created_at_utc: str,
    filters: Sequence[Stage23Filter] | None = None,
) -> Stage23RunnerResult:
    """Evaluate the Stage 23 filter set across every input.

    The runner emits one ``Stage23FilterEvaluation`` per
    (input, filter) pair, regardless of label / data_status. A
    filter returning ``MISSING_INPUT`` / ``UNKNOWN`` /
    ``UNSUPPORTED`` for a given input does NOT cause that input
    to be skipped against the other filters.

    Determinism:

      * Output is sorted by ``(token_mint, event_id,
        captured_event_id, filter_name)`` so re-running the same
        inputs produces byte-identical evaluations and identical
        aggregate counters.
      * Every evaluation's ``input_hash`` and
        ``evaluation_hash`` is computed once at build time. The
        runner reads neither clock nor environment.

    Raises:

      * ``Stage23ContractError`` if ``created_at_utc`` is not a
        non-empty string.
    """
    if not isinstance(created_at_utc, str) or created_at_utc == "":
        raise Stage23ContractError(
            "run_stage23_filters: created_at_utc must be a non-empty string"
        )

    used_filters: tuple[Stage23Filter, ...]
    if filters is None:
        used_filters = default_filters()
    else:
        used_filters = tuple(filters)

    evaluations_list: list[Stage23FilterEvaluation] = []
    label_counter: Counter[str] = Counter()
    data_status_counter: Counter[str] = Counter()
    reason_counter: Counter[str] = Counter()

    input_count = 0
    for filter_input in filter_inputs:
        input_count += 1
        for filter_obj in used_filters:
            result = _evaluate_one(
                filter_obj=filter_obj,
                filter_input=filter_input,
            )
            evaluation = build_filter_evaluation(
                filter_input=filter_input,
                filter_result=result,
                created_at_utc=created_at_utc,
            )
            evaluations_list.append(evaluation)
            label_counter[result.label] += 1
            data_status_counter[result.data_status] += 1
            for code in result.reason_codes:
                reason_counter[code] += 1

    sorted_evaluations = tuple(
        sorted(evaluations_list, key=_evaluation_sort_key)
    )

    return Stage23RunnerResult(
        evaluations=sorted_evaluations,
        input_count=input_count,
        evaluation_count=len(evaluations_list),
        filter_count=len(used_filters),
        label_counts=_frozen_sorted_counter(label_counter),
        data_status_counts=_frozen_sorted_counter(data_status_counter),
        reason_code_counts=_frozen_sorted_counter(reason_counter),
        created_at_utc=created_at_utc,
    )


__all__ = [
    "REASON_STAGE23_FILTER_RAISED_ERROR",
    "STAGE23_RUNNER_REASON_CODES",
    "Stage23RunnerResult",
    "default_filters",
    "run_stage23_filters",
]

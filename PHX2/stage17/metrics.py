"""Stage 17 aggregation layer (pure, no I/O).

Inputs are tuples of dataclasses produced by ``readers``; outputs are
tuples of dataclasses consumed by ``writers``. The module performs
zero side effects and no file or database access.

Percentile convention:

  * The module uses ``statistics.quantiles(data, n=4,
    method="inclusive")`` and picks indices 0/1/2 for p25 / p50 / p75.
  * For N == 1 the function returns the single value for all three
    percentiles (``statistics.quantiles`` itself rejects N == 1).
  * For N == 0 the function returns None.

NULL-propagation:

  * Any delta where either side is None is itself None. The module
    never substitutes 0 for a missing rate or percentile.
"""

from __future__ import annotations

import statistics
from collections import Counter, defaultdict
from typing import Iterable, List, Optional, Tuple

from PHX2.stage17.labels import (
    HARMFUL,
    INSUFFICIENT_SAMPLE,
    PROMISING,
    WEAK,
    label_from_delta,
)
from PHX2.stage17.models import (
    CoarseMetricRow,
    DataQualityRow,
    EvaluationRow,
    HeadlineMetricRow,
    OutcomeRow,
    UnevaluableBreakdownRow,
)
from PHX2.stage17.windows import window_label_for


# ---------------------------------------------------------------------------
# Internal: percentile helper
# ---------------------------------------------------------------------------


def _percentiles_25_50_75(
    values: Iterable[float],
) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    """Return (p25, p50, p75) for the given non-None values.

    N == 0  -> (None, None, None)
    N == 1  -> (v, v, v)
    N >= 2  -> statistics.quantiles inclusive method, indices 0/1/2.
    """

    data: List[float] = [float(v) for v in values]
    if not data:
        return (None, None, None)
    if len(data) == 1:
        single = data[0]
        return (single, single, single)
    quartiles = statistics.quantiles(data, n=4, method="inclusive")
    return (float(quartiles[0]), float(quartiles[1]), float(quartiles[2]))


def _p50_only(values: Iterable[float]) -> Optional[float]:
    """Return the p50 of the given non-None values, None if empty."""

    data: List[float] = [float(v) for v in values]
    if not data:
        return None
    if len(data) == 1:
        return data[0]
    return float(statistics.quantiles(data, n=4, method="inclusive")[1])


def _safe_delta(
    matched: Optional[float], not_matched: Optional[float]
) -> Optional[float]:
    """matched - not_matched, but None on either side propagates."""

    if matched is None or not_matched is None:
        return None
    return matched - not_matched


# ---------------------------------------------------------------------------
# Internal: rate helper
# ---------------------------------------------------------------------------


def _hit_rate(
    rows: Iterable[OutcomeRow],
    attr: str,
) -> Tuple[Optional[float], int]:
    """Compute hit-rate for ``attr`` over the given Tier-2 outcome rows.

    Rows where ``getattr(row, attr) is None`` are excluded from both
    numerator and denominator (locked NULL semantics). Returns
    ``(rate, eligible_n)`` where ``rate`` is None when no eligible
    rows exist.
    """

    eligible = [getattr(row, attr) for row in rows if getattr(row, attr) is not None]
    if not eligible:
        return (None, 0)
    return (sum(int(v) for v in eligible) / len(eligible), len(eligible))


# ---------------------------------------------------------------------------
# Public: headline metrics
# ---------------------------------------------------------------------------


def compute_headline_metrics(
    evaluations: Iterable[EvaluationRow],
    outcomes: Iterable[OutcomeRow],
    min_n: int,
) -> Tuple[HeadlineMetricRow, ...]:
    """Group by (policy_hash, rule_id, tier_name_snapshot, window_seconds).

    A row is emitted only for slices where at least one evaluation in
    the (policy_hash, rule_id, tier_name_snapshot) bucket has a
    matching ``outcome_windows`` row at the given ``window_seconds``
    (i.e., ``n_with_outcome > 0``). Slices with zero outcome data at
    a window are silently skipped -- their absence is the cleanest
    signal that there is nothing to say at that maturity.

    Returned rows are sorted lexicographically by
    ``(policy_hash, rule_id, tier_name_snapshot_or_empty,
    window_seconds)`` ascending. NULL ``tier_name_snapshot`` sorts
    as empty string (i.e., first).
    """

    eval_by_slice: dict[
        Tuple[str, str, Optional[str]], List[EvaluationRow]
    ] = defaultdict(list)
    for e in evaluations:
        eval_by_slice[(e.policy_hash, e.rule_id, e.tier_name_snapshot)].append(e)

    outcome_by_dw: dict[Tuple[int, int], OutcomeRow] = {}
    for o in outcomes:
        outcome_by_dw[(o.alert_decision_id, o.window_seconds)] = o

    rows: List[HeadlineMetricRow] = []
    for slice_key, eval_list in eval_by_slice.items():
        policy_hash, rule_id, tier_name = slice_key

        decision_ids = {e.alert_decision_id for e in eval_list}
        # Which windows have at least one outcome row for any decision in slice.
        slice_windows = sorted({
            ws for (did, ws) in outcome_by_dw.keys() if did in decision_ids
        })

        for ws in slice_windows:
            row = _compute_one_slice_row(
                policy_hash=policy_hash,
                rule_id=rule_id,
                tier_name=tier_name,
                window_seconds=ws,
                eval_list=eval_list,
                outcome_by_dw=outcome_by_dw,
                min_n=min_n,
            )
            if row.n_with_outcome > 0:
                rows.append(row)

    rows.sort(
        key=lambda r: (
            r.policy_hash,
            r.rule_id,
            r.tier_name_snapshot or "",
            r.window_seconds,
        )
    )
    return tuple(rows)


def _compute_one_slice_row(
    *,
    policy_hash: str,
    rule_id: str,
    tier_name: Optional[str],
    window_seconds: int,
    eval_list: List[EvaluationRow],
    outcome_by_dw: dict[Tuple[int, int], OutcomeRow],
    min_n: int,
) -> HeadlineMetricRow:
    n_in_scope = len(eval_list)
    n_matched = sum(1 for e in eval_list if e.evaluation_status == "MATCHED")
    n_not_matched = sum(1 for e in eval_list if e.evaluation_status == "NOT_MATCHED")
    n_unevaluable = sum(1 for e in eval_list if e.evaluation_status == "UNEVALUABLE")

    # Tier 1 (elapsed) and Tier 2 (analyzable) at this window.
    tier1_evals = [
        e for e in eval_list if (e.alert_decision_id, window_seconds) in outcome_by_dw
    ]
    n_with_outcome = len(tier1_evals)

    def _outcome_for(e: EvaluationRow) -> OutcomeRow:
        return outcome_by_dw[(e.alert_decision_id, window_seconds)]

    tier2_evals = [
        e for e in tier1_evals if _outcome_for(e).data_status == "COMPLETE"
    ]
    n_with_complete_outcome = len(tier2_evals)
    n_outcome_present_but_incomplete = n_with_outcome - n_with_complete_outcome

    matched_tier2 = [e for e in tier2_evals if e.evaluation_status == "MATCHED"]
    not_matched_tier2 = [
        e for e in tier2_evals if e.evaluation_status == "NOT_MATCHED"
    ]
    n_matched_with_complete_outcome = len(matched_tier2)
    n_not_matched_with_complete_outcome = len(not_matched_tier2)

    meets_min_n_matched = n_matched_with_complete_outcome >= min_n
    meets_min_n_not_matched = n_not_matched_with_complete_outcome >= min_n

    matched_outcomes = [_outcome_for(e) for e in matched_tier2]
    not_matched_outcomes = [_outcome_for(e) for e in not_matched_tier2]

    # Percentile computations: only over non-NULL source values.
    def _pcts_for(rows: List[OutcomeRow], attr: str) -> Tuple[
        Optional[float], Optional[float], Optional[float]
    ]:
        vals = [getattr(r, attr) for r in rows if getattr(r, attr) is not None]
        return _percentiles_25_50_75(vals)

    def _p50_for(rows: List[OutcomeRow], attr: str) -> Optional[float]:
        vals = [getattr(r, attr) for r in rows if getattr(r, attr) is not None]
        return _p50_only(vals)

    def _gated(value: Optional[float], gate: bool) -> Optional[float]:
        return value if gate else None

    mrm_m25, mrm_m50, mrm_m75 = _pcts_for(matched_outcomes, "max_return_multiple")
    mrm_n25, mrm_n50, mrm_n75 = _pcts_for(not_matched_outcomes, "max_return_multiple")
    mdd_m25, mdd_m50, mdd_m75 = _pcts_for(
        matched_outcomes, "max_drawdown_from_peak_pct"
    )
    mdd_n25, mdd_n50, mdd_n75 = _pcts_for(
        not_matched_outcomes, "max_drawdown_from_peak_pct"
    )
    ttm_m50 = _p50_for(matched_outcomes, "time_to_max_return_seconds")
    ttm_n50 = _p50_for(not_matched_outcomes, "time_to_max_return_seconds")

    hit_2x_m, _ = _hit_rate(matched_outcomes, "hit_2x")
    hit_2x_n, _ = _hit_rate(not_matched_outcomes, "hit_2x")
    hit_3x_m, _ = _hit_rate(matched_outcomes, "hit_3x")
    hit_3x_n, _ = _hit_rate(not_matched_outcomes, "hit_3x")
    hit_5x_m, _ = _hit_rate(matched_outcomes, "hit_5x")
    hit_5x_n, _ = _hit_rate(not_matched_outcomes, "hit_5x")

    # MIN_N gating: below MIN_N, all rate/percentile fields on that side
    # are NULL. Delta NULLs are derived from the gated values.
    mrm_m25_g = _gated(mrm_m25, meets_min_n_matched)
    mrm_m50_g = _gated(mrm_m50, meets_min_n_matched)
    mrm_m75_g = _gated(mrm_m75, meets_min_n_matched)
    mrm_n25_g = _gated(mrm_n25, meets_min_n_not_matched)
    mrm_n50_g = _gated(mrm_n50, meets_min_n_not_matched)
    mrm_n75_g = _gated(mrm_n75, meets_min_n_not_matched)

    mdd_m25_g = _gated(mdd_m25, meets_min_n_matched)
    mdd_m50_g = _gated(mdd_m50, meets_min_n_matched)
    mdd_m75_g = _gated(mdd_m75, meets_min_n_matched)
    mdd_n25_g = _gated(mdd_n25, meets_min_n_not_matched)
    mdd_n50_g = _gated(mdd_n50, meets_min_n_not_matched)
    mdd_n75_g = _gated(mdd_n75, meets_min_n_not_matched)

    ttm_m50_g = _gated(ttm_m50, meets_min_n_matched)
    ttm_n50_g = _gated(ttm_n50, meets_min_n_not_matched)

    hit_2x_m_g = _gated(hit_2x_m, meets_min_n_matched)
    hit_2x_n_g = _gated(hit_2x_n, meets_min_n_not_matched)
    hit_3x_m_g = _gated(hit_3x_m, meets_min_n_matched)
    hit_3x_n_g = _gated(hit_3x_n, meets_min_n_not_matched)
    hit_5x_m_g = _gated(hit_5x_m, meets_min_n_matched)
    hit_5x_n_g = _gated(hit_5x_n, meets_min_n_not_matched)

    delta_hit_2x = _safe_delta(hit_2x_m_g, hit_2x_n_g)
    delta_hit_3x = _safe_delta(hit_3x_m_g, hit_3x_n_g)
    delta_hit_5x = _safe_delta(hit_5x_m_g, hit_5x_n_g)
    delta_mrm_p50 = _safe_delta(mrm_m50_g, mrm_n50_g)
    delta_mdd_p50 = _safe_delta(mdd_m50_g, mdd_n50_g)

    label = label_from_delta(
        delta_hit_2x,
        meets_min_n_matched=meets_min_n_matched,
        meets_min_n_not_matched=meets_min_n_not_matched,
    )

    return HeadlineMetricRow(
        policy_hash=policy_hash,
        rule_id=rule_id,
        tier_name_snapshot=tier_name,
        window_seconds=window_seconds,
        window_label=window_label_for(window_seconds),
        n_in_scope=n_in_scope,
        n_matched=n_matched,
        n_not_matched=n_not_matched,
        n_unevaluable=n_unevaluable,
        n_with_outcome=n_with_outcome,
        n_with_complete_outcome=n_with_complete_outcome,
        n_outcome_present_but_incomplete=n_outcome_present_but_incomplete,
        n_matched_with_complete_outcome=n_matched_with_complete_outcome,
        n_not_matched_with_complete_outcome=n_not_matched_with_complete_outcome,
        min_n_active=min_n,
        meets_min_n_matched=meets_min_n_matched,
        meets_min_n_not_matched=meets_min_n_not_matched,
        max_return_multiple_p25_matched=mrm_m25_g,
        max_return_multiple_p50_matched=mrm_m50_g,
        max_return_multiple_p75_matched=mrm_m75_g,
        max_return_multiple_p25_not_matched=mrm_n25_g,
        max_return_multiple_p50_not_matched=mrm_n50_g,
        max_return_multiple_p75_not_matched=mrm_n75_g,
        max_drawdown_from_peak_pct_p25_matched=mdd_m25_g,
        max_drawdown_from_peak_pct_p50_matched=mdd_m50_g,
        max_drawdown_from_peak_pct_p75_matched=mdd_m75_g,
        max_drawdown_from_peak_pct_p25_not_matched=mdd_n25_g,
        max_drawdown_from_peak_pct_p50_not_matched=mdd_n50_g,
        max_drawdown_from_peak_pct_p75_not_matched=mdd_n75_g,
        time_to_max_return_seconds_p50_matched=ttm_m50_g,
        time_to_max_return_seconds_p50_not_matched=ttm_n50_g,
        hit_2x_rate_matched=hit_2x_m_g,
        hit_2x_rate_not_matched=hit_2x_n_g,
        hit_3x_rate_matched=hit_3x_m_g,
        hit_3x_rate_not_matched=hit_3x_n_g,
        hit_5x_rate_matched=hit_5x_m_g,
        hit_5x_rate_not_matched=hit_5x_n_g,
        delta_hit_2x_rate=delta_hit_2x,
        delta_hit_3x_rate=delta_hit_3x,
        delta_hit_5x_rate=delta_hit_5x,
        delta_max_return_multiple_p50=delta_mrm_p50,
        delta_max_drawdown_from_peak_pct_p50=delta_mdd_p50,
        descriptive_label=label,
    )


# ---------------------------------------------------------------------------
# Public: coarse summary
# ---------------------------------------------------------------------------


_MIXED_BY_TIER = "MIXED_BY_TIER"


def compute_coarse_summary(
    headline_rows: Iterable[HeadlineMetricRow],
) -> Tuple[CoarseMetricRow, ...]:
    """Aggregate the headline output over the ``tier_name_snapshot`` axis.

    For each (policy_hash, rule_id, window_seconds) bucket the
    aggregated counts sum across tiers; the aggregated hit-rates are
    the weighted means over Tier-2 evaluation counts (matched and
    not_matched separately); the aggregated delta is derived from
    those aggregated rates. The descriptive_label is MIXED_BY_TIER if
    the per-tier delta signs disagree across this bucket; otherwise
    it is the standard label rule applied to the aggregated delta.
    """

    rows_by_bucket: dict[
        Tuple[str, str, int], List[HeadlineMetricRow]
    ] = defaultdict(list)
    for row in headline_rows:
        rows_by_bucket[(row.policy_hash, row.rule_id, row.window_seconds)].append(row)

    out: List[CoarseMetricRow] = []
    for (policy_hash, rule_id, ws), bucket in rows_by_bucket.items():
        n_in_scope = sum(r.n_in_scope for r in bucket)
        n_matched = sum(r.n_matched for r in bucket)
        n_not_matched = sum(r.n_not_matched for r in bucket)
        n_with_complete_outcome = sum(r.n_with_complete_outcome for r in bucket)

        agg_hit_m, eligible_m = _weighted_rate(
            bucket, "hit_2x_rate_matched", "n_matched_with_complete_outcome"
        )
        agg_hit_n, eligible_n = _weighted_rate(
            bucket, "hit_2x_rate_not_matched", "n_not_matched_with_complete_outcome"
        )

        # meets_min_n gates are intentionally not re-computed at the
        # coarse level: the per-tier rows already applied MIN_N, and
        # the weighted-rate aggregator skips any tier whose rate is
        # NULL. A coarse delta is therefore NULL whenever either side
        # had no non-NULL contributing rate, mirroring the per-row
        # NULL-propagation rule. The label is MIXED_BY_TIER only when
        # the per-tier deltas actively disagree in sign.
        per_tier_deltas = [
            r.delta_hit_2x_rate for r in bucket if r.delta_hit_2x_rate is not None
        ]
        has_positive = any(d > 0.0 for d in per_tier_deltas)
        has_negative = any(d < 0.0 for d in per_tier_deltas)

        delta = _safe_delta(agg_hit_m, agg_hit_n)

        if has_positive and has_negative:
            label = _MIXED_BY_TIER
        else:
            # Reuse the per-row labeler. Treat the coarse delta as
            # gated on whether either side has eligible data.
            meets_m = agg_hit_m is not None
            meets_n = agg_hit_n is not None
            label = label_from_delta(
                delta,
                meets_min_n_matched=meets_m,
                meets_min_n_not_matched=meets_n,
            )

        out.append(
            CoarseMetricRow(
                policy_hash=policy_hash,
                rule_id=rule_id,
                window_seconds=ws,
                window_label=window_label_for(ws),
                n_in_scope=n_in_scope,
                n_matched=n_matched,
                n_not_matched=n_not_matched,
                n_with_complete_outcome=n_with_complete_outcome,
                hit_2x_rate_matched=agg_hit_m,
                hit_2x_rate_not_matched=agg_hit_n,
                delta_hit_2x_rate=delta,
                descriptive_label=label,
            )
        )

    out.sort(key=lambda r: (r.policy_hash, r.rule_id, r.window_seconds))
    return tuple(out)


def _weighted_rate(
    rows: List[HeadlineMetricRow],
    rate_attr: str,
    weight_attr: str,
) -> Tuple[Optional[float], int]:
    """Weighted mean of ``rate_attr`` weighted by ``weight_attr``.

    Skips rows where the rate is None. Returns ``(rate, total_weight)``
    or ``(None, 0)`` if no contributing row exists.
    """

    total_weight = 0
    total_num = 0.0
    for r in rows:
        rate = getattr(r, rate_attr)
        weight = getattr(r, weight_attr)
        if rate is None or weight is None or weight == 0:
            continue
        total_weight += weight
        total_num += rate * weight
    if total_weight == 0:
        return (None, 0)
    return (total_num / total_weight, total_weight)


# ---------------------------------------------------------------------------
# Public: unevaluable breakdown
# ---------------------------------------------------------------------------


def compute_unevaluable_breakdown(
    evaluations: Iterable[EvaluationRow],
) -> Tuple[UnevaluableBreakdownRow, ...]:
    """Count UNEVALUABLE evaluations by (policy_hash, rule_id, reason).

    Sorted ascending by all three keys. ``unevaluable_reason`` is
    expected to be non-NULL (the schema CHECK guarantees it) but we
    sort with a None-safe key in case fixtures override that
    invariant.
    """

    counter: Counter[Tuple[str, str, Optional[str]]] = Counter()
    for e in evaluations:
        if e.evaluation_status != "UNEVALUABLE":
            continue
        counter[(e.policy_hash, e.rule_id, e.unevaluable_reason)] += 1

    rows = [
        UnevaluableBreakdownRow(
            policy_hash=key[0],
            rule_id=key[1],
            unevaluable_reason=key[2],
            n=count,
        )
        for key, count in counter.items()
    ]
    rows.sort(
        key=lambda r: (
            r.policy_hash,
            r.rule_id,
            r.unevaluable_reason or "",
        )
    )
    return tuple(rows)


# ---------------------------------------------------------------------------
# Public: data quality report
# ---------------------------------------------------------------------------


def compute_data_quality(
    evaluations: Iterable[EvaluationRow],
    outcomes: Iterable[OutcomeRow],
    orphan_eval_count: int,
    orphan_outcome_count: int,
) -> Tuple[DataQualityRow, ...]:
    """Build the data-quality report rows.

    Global-scope rows first, then slice-scope rows where
    ``n_outcome_present_but_incomplete > 0``.
    """

    evals = list(evaluations)
    outs = list(outcomes)

    global_rows: List[DataQualityRow] = [
        DataQualityRow(
            scope_level="global",
            policy_hash=None,
            rule_id=None,
            window_seconds=None,
            metric_name="orphan_evaluations",
            metric_value=int(orphan_eval_count),
        ),
        DataQualityRow(
            scope_level="global",
            policy_hash=None,
            rule_id=None,
            window_seconds=None,
            metric_name="orphan_outcomes",
            metric_value=int(orphan_outcome_count),
        ),
        DataQualityRow(
            scope_level="global",
            policy_hash=None,
            rule_id=None,
            window_seconds=None,
            metric_name="total_evaluations",
            metric_value=len(evals),
        ),
        DataQualityRow(
            scope_level="global",
            policy_hash=None,
            rule_id=None,
            window_seconds=None,
            metric_name="total_outcomes",
            metric_value=len(outs),
        ),
    ]

    # Slice rows: surface ``n_outcome_present_but_incomplete`` only.
    outcome_by_dw: dict[Tuple[int, int], OutcomeRow] = {
        (o.alert_decision_id, o.window_seconds): o for o in outs
    }
    eval_by_slice: dict[
        Tuple[str, str, Optional[str]], List[EvaluationRow]
    ] = defaultdict(list)
    for e in evals:
        eval_by_slice[(e.policy_hash, e.rule_id, e.tier_name_snapshot)].append(e)

    slice_rows: List[Tuple[Tuple[str, str, str, int], DataQualityRow]] = []
    for slice_key, eval_list in eval_by_slice.items():
        policy_hash, rule_id, _tier = slice_key
        decision_ids = {e.alert_decision_id for e in eval_list}
        slice_windows = sorted({
            ws for (did, ws) in outcome_by_dw.keys() if did in decision_ids
        })
        for ws in slice_windows:
            tier1 = sum(
                1
                for e in eval_list
                if (e.alert_decision_id, ws) in outcome_by_dw
            )
            tier2 = sum(
                1
                for e in eval_list
                if (
                    (e.alert_decision_id, ws) in outcome_by_dw
                    and outcome_by_dw[(e.alert_decision_id, ws)].data_status
                    == "COMPLETE"
                )
            )
            incomplete = tier1 - tier2
            if incomplete > 0:
                sort_key = (policy_hash, rule_id, _tier or "", ws)
                slice_rows.append(
                    (
                        sort_key,
                        DataQualityRow(
                            scope_level="slice",
                            policy_hash=policy_hash,
                            rule_id=rule_id,
                            window_seconds=ws,
                            metric_name="n_outcome_present_but_incomplete",
                            metric_value=incomplete,
                        ),
                    )
                )

    slice_rows.sort(key=lambda pair: pair[0])
    return tuple(global_rows) + tuple(row for _, row in slice_rows)


__all__ = [
    "HARMFUL",
    "INSUFFICIENT_SAMPLE",
    "PROMISING",
    "WEAK",
    "compute_coarse_summary",
    "compute_data_quality",
    "compute_headline_metrics",
    "compute_unevaluable_breakdown",
]

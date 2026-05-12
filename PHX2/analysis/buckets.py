"""Quartile and domain bucketing for Stage 12 primitives.

Three bucketing methods exist in v0:

  * ``quartile`` — global quartile edges (Q1/Q2/Q3/Q4) computed once per
    primitive from the full eligible WOULD_ALERT population (M2). Applied
    globally across tiers, not per-tier.
  * ``domain`` — fixed (label, low, high) intervals declared in
    ``DOMAIN_BUCKETS``.
  * ``boolean`` — {true, false}. No boolean primitives are present in
    ``decision_score_features`` v0; the code path exists defensively.

The ``missing`` bucket is generic across methods: any value that is
None or NaN is routed to ``missing`` (bucket_order=0). All other
buckets follow with bucket_order = 1..N in their declared / natural
order (spec §5.2).

HC-1 (locked design spec): ``drop_from_ath`` (the decision-score-features
column whose semantic is "drawdown from ATH") is intentionally absent
from ``DOMAIN_BUCKETS``. ``tier_name`` already partitions decisions by
drawdown band — tier ranges are defined in drawdown-from-ATH space — so
applying domain buckets to ``drop_from_ath`` would duplicate the
partition. Stage 12 v0 keeps ``drop_from_ath`` on the quartile path so
within-tier drawdown variation still appears in
``cohort_primitive_bucket_by_tier``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence

import numpy as np


DomainBucketSpec = tuple[str, float | None, float | None]


DOMAIN_BUCKETS: dict[str, list[DomainBucketSpec]] = {
    "time_since_migration_seconds": [
        ("[0h, 1h)",   0.0,      3600.0),
        ("[1h, 6h)",   3600.0,   21600.0),
        ("[6h, 24h)",  21600.0,  86400.0),
        ("[24h, 72h)", 86400.0,  259200.0),
        ("[72h, inf)", 259200.0, None),
    ],
    "time_since_ath_seconds": [
        ("[0m, 5m)",   0.0,     300.0),
        ("[5m, 30m)",  300.0,   1800.0),
        ("[30m, 2h)",  1800.0,  7200.0),
        ("[2h, 24h)",  7200.0,  86400.0),
        ("[24h, inf)", 86400.0, None),
    ],
}
"""Spec §7.5 — Solana memecoin lifecycle stages.

``time_since_migration_seconds`` partitions token maturity:
  [0h,1h)   — fresh post-migration; early discovery window
  [1h,6h)   — early/mid maturity
  [6h,24h)  — mature within first day
  [24h,72h) — second-and-third day
  [72h,inf) — long-tail / aged

``time_since_ath_seconds`` partitions dip recency:
  [0m,5m)   — moments after ATH; fresh dip
  [5m,30m)  — recent dip
  [30m,2h)  — settled dip
  [2h,24h)  — late dip
  [24h,inf) — stale ATH (24h+ since peak)

Final bucket's high_exclusive=None denotes unbounded upper. The
"missing" bucket is handled generically and is NOT in this list.
"""


MISSING_BUCKET_INDEX = "missing"
MISSING_BUCKET_LABEL = "missing"
MISSING_BUCKET_ORDER = 0


@dataclass(frozen=True)
class BucketSpec:
    """One row in cohort_primitive_bucket_by_tier for a single bucket.

    bucket_index is the short identifier (``Q1``..``Q4``, ``missing``,
    ``true``/``false``, or a domain label). bucket_label is the
    human-readable rendering (``Q1 [0.000, 0.150]``, ``[0h, 1h)``,
    ``missing``). bucket_low / bucket_high are numeric bounds (None for
    ``missing`` and for unbounded sides of domain or quartile-max
    intervals). bucket_order drives the §5.2 sort key.
    """

    bucket_index: str
    bucket_label: str
    bucket_low: float | None
    bucket_high: float | None
    bucket_order: int


@dataclass(frozen=True)
class BucketResult:
    """Per-primitive bucketing output.

    name: the decision_score_features column name (authoritative form
        with ``_seconds`` suffix, etc.).
    method: ``"quartile"`` | ``"domain"`` | ``"boolean"``.
    skipped: True if the primitive could not be bucketed; False otherwise.
        Skipped primitives are NOT emitted as cohort rows.
    skip_reason: ``"no_non_null_values"`` | ``"single_value"`` |
        ``"few_distinct_values"`` | None. None when not skipped.
    bucket_specs: ordered (bucket_order ASC) list of BucketSpec, with
        the ``missing`` bucket first (bucket_order=0) when missing
        values are present. Empty list when skipped.
    assignments: one bucket_index per input value (length matches the
        input). ``MISSING_BUCKET_INDEX`` for null/NaN inputs. Empty
        list when skipped.
    edges: the three quartile edges [q1, q2, q3] when method=quartile;
        None for domain/boolean.
    """

    name: str
    method: str
    skipped: bool
    skip_reason: str | None
    bucket_specs: tuple[BucketSpec, ...]
    assignments: tuple[str, ...]
    edges: tuple[float, float, float] | None


def _is_missing(value: object) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and math.isnan(value):
        return True
    return False


def _normalize_values(values: Sequence[object]) -> list[float | None]:
    out: list[float | None] = []
    for v in values:
        if _is_missing(v):
            out.append(None)
        else:
            try:
                out.append(float(v))
            except (TypeError, ValueError):
                out.append(None)
    return out


def detect_degeneracy(values: Sequence[object]) -> str:
    """Classify the bucketability of a list of nullable primitive values.

    Returns one of:
      * ``no_non_null_values`` — every value is None/NaN.
      * ``single_value`` — exactly one distinct non-null value.
      * ``few_distinct_values`` — 2 or 3 distinct non-null values
        (quartile edges would collapse).
      * ``ok`` — 4+ distinct non-null values.
    """

    normalized = _normalize_values(values)
    non_null = [v for v in normalized if v is not None]
    if not non_null:
        return "no_non_null_values"
    distinct = len(set(non_null))
    if distinct == 1:
        return "single_value"
    if distinct < 4:
        return "few_distinct_values"
    return "ok"


def compute_quartile_edges(values: Sequence[object]) -> tuple[float, float, float]:
    """Compute (q1, q2, q3) using NumPy linear interpolation.

    The caller must route through ``detect_degeneracy`` first; passing
    in fewer than 4 distinct non-null values is undefined behavior.
    """

    non_null = [v for v in _normalize_values(values) if v is not None]
    if not non_null:
        raise ValueError("compute_quartile_edges requires non-empty values")
    arr = np.asarray(non_null, dtype=float)
    q1 = float(np.quantile(arr, 0.25, method="linear"))
    q2 = float(np.quantile(arr, 0.50, method="linear"))
    q3 = float(np.quantile(arr, 0.75, method="linear"))
    return (q1, q2, q3)


def _format_edge(value: float) -> str:
    return f"{value:.4g}"


def _quartile_bucket_index(value: float, edges: tuple[float, float, float]) -> str:
    q1, q2, q3 = edges
    if value < q1:
        return "Q1"
    if value < q2:
        return "Q2"
    if value < q3:
        return "Q3"
    return "Q4"


def _quartile_specs(
    edges: tuple[float, float, float],
    have_missing: bool,
    min_value: float,
    max_value: float,
) -> list[BucketSpec]:
    q1, q2, q3 = edges
    specs: list[BucketSpec] = []
    if have_missing:
        specs.append(
            BucketSpec(
                bucket_index=MISSING_BUCKET_INDEX,
                bucket_label=MISSING_BUCKET_LABEL,
                bucket_low=None,
                bucket_high=None,
                bucket_order=MISSING_BUCKET_ORDER,
            )
        )
    specs.append(
        BucketSpec(
            bucket_index="Q1",
            bucket_label=f"Q1 [{_format_edge(min_value)}, {_format_edge(q1)})",
            bucket_low=min_value,
            bucket_high=q1,
            bucket_order=1,
        )
    )
    specs.append(
        BucketSpec(
            bucket_index="Q2",
            bucket_label=f"Q2 [{_format_edge(q1)}, {_format_edge(q2)})",
            bucket_low=q1,
            bucket_high=q2,
            bucket_order=2,
        )
    )
    specs.append(
        BucketSpec(
            bucket_index="Q3",
            bucket_label=f"Q3 [{_format_edge(q2)}, {_format_edge(q3)})",
            bucket_low=q2,
            bucket_high=q3,
            bucket_order=3,
        )
    )
    specs.append(
        BucketSpec(
            bucket_index="Q4",
            bucket_label=f"Q4 [{_format_edge(q3)}, {_format_edge(max_value)}]",
            bucket_low=q3,
            bucket_high=max_value,
            bucket_order=4,
        )
    )
    return specs


def _domain_bucket_index(
    value: float, specs: Sequence[DomainBucketSpec]
) -> str | None:
    for label, low, high in specs:
        lo_ok = low is None or value >= low
        hi_ok = high is None or value < high
        if lo_ok and hi_ok:
            return label
    return None


def _domain_specs(
    column_name: str, have_missing: bool
) -> tuple[list[BucketSpec], list[DomainBucketSpec]]:
    domain = DOMAIN_BUCKETS[column_name]
    specs: list[BucketSpec] = []
    if have_missing:
        specs.append(
            BucketSpec(
                bucket_index=MISSING_BUCKET_INDEX,
                bucket_label=MISSING_BUCKET_LABEL,
                bucket_low=None,
                bucket_high=None,
                bucket_order=MISSING_BUCKET_ORDER,
            )
        )
    for order, (label, low, high) in enumerate(domain, start=1):
        specs.append(
            BucketSpec(
                bucket_index=label,
                bucket_label=label,
                bucket_low=low,
                bucket_high=high,
                bucket_order=order,
            )
        )
    return specs, list(domain)


def _boolean_specs(have_missing: bool) -> list[BucketSpec]:
    specs: list[BucketSpec] = []
    if have_missing:
        specs.append(
            BucketSpec(
                bucket_index=MISSING_BUCKET_INDEX,
                bucket_label=MISSING_BUCKET_LABEL,
                bucket_low=None,
                bucket_high=None,
                bucket_order=MISSING_BUCKET_ORDER,
            )
        )
    specs.append(
        BucketSpec(
            bucket_index="true",
            bucket_label="true",
            bucket_low=None,
            bucket_high=None,
            bucket_order=1,
        )
    )
    specs.append(
        BucketSpec(
            bucket_index="false",
            bucket_label="false",
            bucket_low=None,
            bucket_high=None,
            bucket_order=2,
        )
    )
    return specs


def _skipped_result(name: str, method: str, reason: str) -> BucketResult:
    return BucketResult(
        name=name,
        method=method,
        skipped=True,
        skip_reason=reason,
        bucket_specs=(),
        assignments=(),
        edges=None,
    )


def bucket_one_primitive(
    name: str,
    values: Sequence[object],
    *,
    is_boolean: bool = False,
) -> BucketResult:
    """Bucket one primitive across all eligible decisions.

    Dispatch:
      * ``is_boolean=True`` -> boolean method ({true, false, missing}).
        v0 does not exercise this code path (no boolean primitives in
        ``decision_score_features``); kept for FC-* forward-compat.
      * ``name`` in ``DOMAIN_BUCKETS`` -> domain method.
      * otherwise -> quartile method, routed through
        ``detect_degeneracy`` first.
    """

    normalized = _normalize_values(values)
    have_missing = any(v is None for v in normalized)

    if is_boolean:
        # Boolean primitives: values arrive normalized as 0.0/1.0 from
        # _normalize_values via float coercion. The "true" bucket
        # corresponds to truthy (non-zero) non-null values.
        specs = _boolean_specs(have_missing)
        assignments = tuple(
            MISSING_BUCKET_INDEX if v is None else ("true" if v else "false")
            for v in normalized
        )
        return BucketResult(
            name=name,
            method="boolean",
            skipped=False,
            skip_reason=None,
            bucket_specs=tuple(specs),
            assignments=assignments,
            edges=None,
        )

    if name in DOMAIN_BUCKETS:
        # Domain bucketing has no degeneracy check beyond the
        # all-missing case; specs are fixed regardless of value spread.
        non_null = [v for v in normalized if v is not None]
        if not non_null:
            return _skipped_result(name, "domain", "no_non_null_values")
        specs, domain = _domain_specs(name, have_missing)
        assignments_list: list[str] = []
        for v in normalized:
            if v is None:
                assignments_list.append(MISSING_BUCKET_INDEX)
            else:
                idx = _domain_bucket_index(v, domain)
                # All v0 domain buckets cover [0, inf) so a non-null
                # value always matches some bucket. Defensive fallback:
                # route to "missing" if a value lies outside the
                # declared coverage (e.g., a negative time).
                assignments_list.append(
                    idx if idx is not None else MISSING_BUCKET_INDEX
                )
        return BucketResult(
            name=name,
            method="domain",
            skipped=False,
            skip_reason=None,
            bucket_specs=tuple(specs),
            assignments=tuple(assignments_list),
            edges=None,
        )

    degeneracy = detect_degeneracy(normalized)
    if degeneracy != "ok":
        return _skipped_result(name, "quartile", degeneracy)

    edges = compute_quartile_edges(normalized)
    non_null = [v for v in normalized if v is not None]
    min_value = min(non_null)
    max_value = max(non_null)
    specs = _quartile_specs(edges, have_missing, min_value, max_value)
    assignments_list = []
    for v in normalized:
        if v is None:
            assignments_list.append(MISSING_BUCKET_INDEX)
        else:
            assignments_list.append(_quartile_bucket_index(v, edges))
    return BucketResult(
        name=name,
        method="quartile",
        skipped=False,
        skip_reason=None,
        bucket_specs=tuple(specs),
        assignments=tuple(assignments_list),
        edges=edges,
    )

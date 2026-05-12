"""Stage 12 pipeline orchestrator.

Pure function ``run(readers, params) -> RunResult``:

  * Reads alert_decisions, filter_evaluations, decision_score_features,
    outcome_windows via ``SubstrateReaders`` (L4 enforced by the
    dataclass signature).
  * Left-joins them at alert_decision_id to produce the long DataFrame.
  * Derives the primary 24h outcome flags (has_outcome_window_24h,
    outcome_censored_24h, no_outcome_24h, has_primary_outcome,
    primary_outcome_hit_{2x,3x,5x}_24h) per the operator's canonical
    naming.
  * Applies §5.2 NULLS-LAST sort to the long DataFrame.
  * Builds the four cohort DataFrames per §5.4-§5.7 using a single
    ``compute_cohort_rates`` helper.
  * Assembles the manifest via ``ManifestBuilder``.
  * Returns a ``RunResult`` containing all DataFrames + manifest +
    README context. NO file I/O happens inside this function -- the
    caller (CLI) writes files via ``writers``.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

import pandas as pd

from PHX2.analysis.buckets import bucket_one_primitive
from PHX2.analysis.manifest import ManifestBuilder
from PHX2.analysis.metrics import compute_cohort_rates
from PHX2.analysis.readers import (
    AlertDecisionsReader,
    DecisionScoreFeaturesReader,
    FilterEvaluationsReader,
    OutcomeWindowsReader,
    TokenIdentityReader,
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


WINDOWS: tuple[tuple[int, str], ...] = (
    (300, "5m"),
    (900, "15m"),
    (1800, "30m"),
    (3600, "1h"),
    (14400, "4h"),
    (86400, "24h"),
)
"""Six outcome windows (seconds + label suffix). Matches the Stage 9
``outcome_windows.window_seconds`` CHECK constraint exactly."""


PRIMARY_WINDOW_SECONDS = 86400
PRIMARY_WINDOW_SUFFIX = "24h"


OUTCOME_METRIC_COLUMNS: tuple[str, ...] = (
    "data_status",
    "max_return_multiple",
    "max_return_pct",
    "min_return_multiple",
    "min_return_pct",
    "max_drawdown_from_peak_pct",
    "time_to_max_return_seconds",
    "hit_2x",
    "hit_3x",
    "hit_5x",
    "observations_count",
    "first_observation_time",
    "last_observation_time",
)


DSF_BOOL_COLUMNS: frozenset[str] = frozenset({
    # No boolean primitives in v0 (S0-3). Kept as the set the code path
    # treats as boolean if any are discovered in future schemas.
})


COHORT_TIER_BASELINE_FILENAME = "cohort_tier_baseline.csv"
COHORT_FILTER_LABEL_OVERALL_FILENAME = "cohort_filter_label_overall.csv"
COHORT_FILTER_LABEL_BY_TIER_FILENAME = "cohort_filter_label_by_tier.csv"
COHORT_PRIMITIVE_BUCKET_BY_TIER_FILENAME = "cohort_primitive_bucket_by_tier.csv"
LONG_CSV_FILENAME = "decision_filter_outcome_long.csv"


# Canonical column order for cohort_primitive_bucket_by_tier (§5.7).
PRIMITIVE_BUCKET_COLUMNS: tuple[str, ...] = (
    "run_id",
    "tier_index",
    "tier_name",
    "primitive_name",
    "bucket_method",
    "bucket_index",
    "bucket_label",
    "bucket_low",
    "bucket_high",
    "bucket_order",
    "n_decisions",
    "n_with_outcome_window",
    "n_complete",
    "n_censored",
    "n_no_outcome",
    "hit_2x_24h_count",
    "hit_2x_24h_rate",
    "hit_2x_24h_ci_low",
    "hit_2x_24h_ci_high",
    "hit_3x_24h_count",
    "hit_3x_24h_rate",
    "hit_3x_24h_ci_low",
    "hit_3x_24h_ci_high",
    "hit_5x_24h_count",
    "hit_5x_24h_rate",
    "hit_5x_24h_ci_low",
    "hit_5x_24h_ci_high",
    "median_max_return_24h",
    "median_max_drawdown_24h",
    "confidence_flag",
)


# Canonical column order for the three "non-primitive" cohort CSVs.
def _cohort_columns_with_group(group_cols: Sequence[str]) -> tuple[str, ...]:
    return (
        "run_id",
        *group_cols,
        "n_decisions",
        "n_with_outcome_window",
        "n_complete",
        "n_censored",
        "n_no_outcome",
        "hit_2x_24h_count",
        "hit_2x_24h_rate",
        "hit_2x_24h_ci_low",
        "hit_2x_24h_ci_high",
        "hit_3x_24h_count",
        "hit_3x_24h_rate",
        "hit_3x_24h_ci_low",
        "hit_3x_24h_ci_high",
        "hit_5x_24h_count",
        "hit_5x_24h_rate",
        "hit_5x_24h_ci_low",
        "hit_5x_24h_ci_high",
        "median_max_return_24h",
        "median_max_drawdown_24h",
        "confidence_flag",
    )


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SubstrateReaders:
    """L4-enforced read surface: exactly the four analytical tables
    plus an optional display-only TokenIdentityReader.

    The dataclass signature itself is the enforcement: instances accept
    only these reader types. A reader pointing at field_features,
    clock_features, fee_windows, ath_state, ath_events,
    price_observations, raw_pumpswap_events, migration_events,
    price_curve_points, or dispatch_events cannot be passed in.
    """

    alert_decisions: AlertDecisionsReader
    filter_evaluations: FilterEvaluationsReader
    decision_score_features: DecisionScoreFeaturesReader
    outcome_windows: OutcomeWindowsReader
    token_identity: TokenIdentityReader | None = None


@dataclass(frozen=True)
class RunParams:
    """One-run parameters. All decision-time-range bounds are inclusive.

    ``git_commit`` and ``git_dirty`` carry git fingerprint values that
    the CLI captures via subprocess and passes through to ``run(...)``.
    The orchestrator itself never invokes subprocess (spec §6.2 purity
    constraint, m-3 remediation). Pass None for both when invoking
    ``run(...)`` outside a git checkout.
    """

    output_root: Path
    included_decision_statuses: tuple[str, ...] = ("would_alert",)
    decision_time_range_start: datetime | None = None
    decision_time_range_end: datetime | None = None
    run_id: str | None = None
    created_at: datetime | None = None
    as_of_time: datetime | None = None
    git_commit: str | None = None
    git_dirty: bool | None = None


@dataclass(frozen=True)
class RunResult:
    """Outputs of one Stage 12 run.

    File I/O is the CLI's responsibility; ``RunResult`` carries the
    DataFrames + manifest + README context so ``run`` stays pure.
    """

    run_id: str
    long_df: pd.DataFrame
    cohort_tier_baseline: pd.DataFrame
    cohort_filter_label_overall: pd.DataFrame
    cohort_filter_label_by_tier: pd.DataFrame
    cohort_primitive_bucket_by_tier: pd.DataFrame
    manifest: dict[str, Any]
    readme_context: dict[str, Any]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def generate_run_id(created_at: datetime) -> str:
    """``YYYYMMDDTHHMMSSZ_<6-char-random-hex>`` per spec §5.1.

    Always UTC. ``secrets.token_hex(3)`` for the suffix.
    """

    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    utc = created_at.astimezone(timezone.utc)
    timestamp = utc.strftime("%Y%m%dT%H%M%SZ")
    return f"{timestamp}_{secrets.token_hex(3)}"


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.isoformat()
    return value.isoformat()


# ---------------------------------------------------------------------------
# Long DataFrame construction
# ---------------------------------------------------------------------------


def _rename_decision_columns(decisions: pd.DataFrame) -> pd.DataFrame:
    return decisions.rename(columns={"id": "alert_decision_id"})


def _attach_symbols(
    decisions: pd.DataFrame,
    symbols: dict[str, str | None],
) -> pd.DataFrame:
    out = decisions.copy()
    if symbols:
        out["symbol"] = out["token_address"].map(symbols)
    else:
        out["symbol"] = None
    return out


def _rename_filter_columns(filters: pd.DataFrame) -> pd.DataFrame:
    return filters.rename(
        columns={
            "id": "filter_evaluation_id",
            "label": "filter_label",
            "score": "filter_score",
            "would_block": "filter_would_block",
            "policy_action": "filter_policy_action",
            "reason": "filter_reason",
            "data_status": "filter_data_status",
            "as_of_time": "filter_as_of_time",
        }
    )


def _filter_columns_for_join(filters: pd.DataFrame) -> pd.DataFrame:
    # token_address duplicates the alert_decisions column; drop it.
    drop_cols = [c for c in ("token_address",) if c in filters.columns]
    return filters.drop(columns=drop_cols) if drop_cols else filters


def _dsf_select_for_join(
    dsf: pd.DataFrame,
    primitives: Sequence[str],
) -> pd.DataFrame:
    """Pick alert_decision_id + token_symbol + primitives from DSF."""

    if dsf.empty:
        cols = ["alert_decision_id", "token_symbol", *primitives]
        return pd.DataFrame(columns=cols)
    keep = ["alert_decision_id"]
    if "token_symbol" in dsf.columns:
        keep.append("token_symbol")
    keep.extend(p for p in primitives if p in dsf.columns)
    return dsf[keep].copy()


def _per_window_columns(
    outcomes: pd.DataFrame,
    window_seconds: int,
    suffix: str,
) -> pd.DataFrame:
    """Select & rename outcome columns for one window.

    Output schema:
      alert_decision_id
      outcome_<suffix>_<metric>  -- for each metric in OUTCOME_METRIC_COLUMNS
    """

    if outcomes.empty:
        cols = ["alert_decision_id"] + [
            f"outcome_{suffix}_{m}" for m in OUTCOME_METRIC_COLUMNS
        ]
        return pd.DataFrame(columns=cols)
    sub = outcomes[outcomes["window_seconds"] == window_seconds].copy()
    sub = sub[["alert_decision_id", *OUTCOME_METRIC_COLUMNS]].copy()
    rename_map = {m: f"outcome_{suffix}_{m}" for m in OUTCOME_METRIC_COLUMNS}
    sub.rename(columns=rename_map, inplace=True)
    return sub


def _derive_primary_outcome_flags(long_df: pd.DataFrame) -> pd.DataFrame:
    """Add the operator-canonical 24h flag and aliased hit columns.

    Flags emitted:
      has_outcome_window_24h  -- 24h row exists at all
      outcome_censored_24h    -- 24h row exists AND data_status != COMPLETE
      no_outcome_24h          -- no 24h row exists
      has_primary_outcome     -- 24h row exists AND data_status == COMPLETE
      primary_outcome_hit_2x_24h / 3x / 5x  -- alias of outcome_24h_hit_*,
        NULL when not has_primary_outcome
    """

    out = long_df.copy()
    status_col = "outcome_24h_data_status"
    if status_col not in out.columns:
        out[status_col] = pd.Series([pd.NA] * len(out), dtype="object")

    has_window = out[status_col].notna()
    complete = has_window & (out[status_col] == "COMPLETE")
    censored = has_window & (out[status_col] != "COMPLETE")
    no_outcome = ~has_window

    out["has_outcome_window_24h"] = has_window.astype("boolean")
    out["outcome_censored_24h"] = censored.astype("boolean")
    out["no_outcome_24h"] = no_outcome.astype("boolean")
    out["has_primary_outcome"] = complete.astype("boolean")

    for hit_name in ("hit_2x", "hit_3x", "hit_5x"):
        src = f"outcome_24h_{hit_name}"
        dst = f"primary_outcome_{hit_name}_24h"
        if src in out.columns:
            src_bool = out[src].astype("boolean")
            out[dst] = src_bool.where(complete, other=pd.NA)
        else:
            out[dst] = pd.Series([pd.NA] * len(out), dtype="boolean")

    return out


def _coerce_outcome_hit_dtypes(long_df: pd.DataFrame) -> pd.DataFrame:
    """Coerce outcome_<W>_hit_* columns from INTEGER 0/1 to nullable
    pandas ``boolean`` dtype.

    Stage 9 schema stores hit_2x/3x/5x as INTEGER; the analysis layer
    works in nullable boolean throughout (None/True/False) so the
    DataFrame's missing-value semantics are uniform.
    """

    out = long_df.copy()
    for _seconds, suffix in WINDOWS:
        for hit in ("hit_2x", "hit_3x", "hit_5x"):
            col = f"outcome_{suffix}_{hit}"
            if col in out.columns:
                out[col] = out[col].astype("boolean")
    return out


def _build_long_df(
    decisions: pd.DataFrame,
    filters: pd.DataFrame,
    dsf: pd.DataFrame,
    outcomes: pd.DataFrame,
    symbols: dict[str, str | None],
    primitives: Sequence[str],
) -> pd.DataFrame:
    """Compose the long DataFrame via the §7.2 left-join chain."""

    decisions_renamed = _rename_decision_columns(decisions)
    decisions_with_symbol = _attach_symbols(decisions_renamed, symbols)

    filters_clean = _filter_columns_for_join(_rename_filter_columns(filters))
    long_df = decisions_with_symbol.merge(
        filters_clean, on="alert_decision_id", how="left"
    )
    long_df["filter_evaluation_present"] = long_df["filter_evaluation_id"].notna()

    dsf_clean = _dsf_select_for_join(dsf, primitives)
    dsf_present_ids = set(dsf_clean["alert_decision_id"].dropna().astype(int).tolist())

    # Compute the presence flag BEFORE the merge so the symbol
    # resolution can gate on it without confusing "DSF row exists with
    # token_symbol NULL" (preserve NULL) with "no DSF row" (fall back
    # to token_sequence_state).
    long_df["decision_score_features_present"] = long_df["alert_decision_id"].map(
        lambda x: x in dsf_present_ids
    )

    if "token_symbol" in dsf_clean.columns:
        # Rename DSF's token_symbol on import so the merge does not
        # collide with the existing symbol column.
        long_df = long_df.merge(
            dsf_clean.rename(columns={"token_symbol": "_dsf_token_symbol"}),
            on="alert_decision_id",
            how="left",
        )
        # DSF NULL is itself a decision-time-frozen value ("at decision
        # time the symbol was unknown"). Preserve it. Fall back to the
        # token_sequence_state symbol only when no DSF row exists --
        # i.e., decision_score_features_present is False.
        long_df["symbol"] = long_df["_dsf_token_symbol"].where(
            long_df["decision_score_features_present"].astype(bool),
            long_df["symbol"],
        )
        long_df.drop(columns=["_dsf_token_symbol"], inplace=True)
    else:
        long_df = long_df.merge(dsf_clean, on="alert_decision_id", how="left")

    for seconds, suffix in WINDOWS:
        window_df = _per_window_columns(outcomes, seconds, suffix)
        long_df = long_df.merge(window_df, on="alert_decision_id", how="left")

    long_df = _coerce_outcome_hit_dtypes(long_df)
    long_df = _derive_primary_outcome_flags(long_df)
    return long_df


def _apply_long_csv_sort(long_df: pd.DataFrame) -> pd.DataFrame:
    """§5.2: alert_decision_id ASC, filter_name NULLS LAST,
    filter_version NULLS LAST, filter_evaluation_id NULLS LAST.

    pandas ``na_position='last'`` honors NULL ordering for both numeric
    and string columns under the stable ``mergesort`` algorithm.
    """

    sort_cols = [
        "alert_decision_id",
        "filter_name",
        "filter_version",
        "filter_evaluation_id",
    ]
    present = [c for c in sort_cols if c in long_df.columns]
    if not present:
        return long_df
    return long_df.sort_values(
        by=present, ascending=True, na_position="last", kind="mergesort"
    ).reset_index(drop=True)


# ---------------------------------------------------------------------------
# Cohort builders
# ---------------------------------------------------------------------------


def _empty_long_df() -> pd.DataFrame:
    # Minimal schema: enough for downstream code to introspect column
    # names without crashing. Real shape is determined at first
    # non-empty run.
    base_cols = [
        "alert_decision_id",
        "token_address",
        "symbol",
        "evaluated_at",
        "decision_type",
        "tier_index",
        "tier_name",
        "primary_reason",
        "policy_version",
        "filter_evaluation_present",
        "filter_evaluation_id",
        "filter_name",
        "filter_version",
        "threshold_version",
        "filter_label",
        "filter_score",
        "filter_would_block",
        "filter_policy_action",
        "filter_reason",
        "filter_data_status",
        "decision_score_features_present",
    ]
    for _seconds, suffix in WINDOWS:
        for metric in OUTCOME_METRIC_COLUMNS:
            base_cols.append(f"outcome_{suffix}_{metric}")
    base_cols.extend(
        [
            "has_outcome_window_24h",
            "outcome_censored_24h",
            "no_outcome_24h",
            "has_primary_outcome",
            "primary_outcome_hit_2x_24h",
            "primary_outcome_hit_3x_24h",
            "primary_outcome_hit_5x_24h",
        ]
    )
    return pd.DataFrame(columns=base_cols)


def _build_cohort_tier_baseline(
    long_df: pd.DataFrame, run_id: str
) -> pd.DataFrame:
    if long_df.empty:
        return pd.DataFrame(
            columns=_cohort_columns_with_group(["tier_index", "tier_name"])
        )
    cohort = compute_cohort_rates(long_df, ["tier_index", "tier_name"])
    cohort.insert(0, "run_id", run_id)
    cohort = cohort.sort_values(
        by=["tier_index"], ascending=True, na_position="last", kind="mergesort"
    ).reset_index(drop=True)
    return cohort[list(_cohort_columns_with_group(["tier_index", "tier_name"]))]


def _filter_label_rows(long_df: pd.DataFrame) -> pd.DataFrame:
    if long_df.empty:
        return long_df
    return long_df[long_df["filter_evaluation_present"].astype(bool)].copy()


# Filter cohort identity (post-M-1 remediation): threshold_version is a
# first-class identity dimension because the Stage 10 schema's UNIQUE key
# on filter_evaluations is (alert_decision_id, filter_name, filter_version,
# threshold_version). M8 multi-version handling therefore requires
# threshold_version to partition both cohort_filter_label_overall and
# cohort_filter_label_by_tier so two threshold revisions of the same
# (filter_name, filter_version, filter_label) tuple do not merge into one
# row.
_FILTER_LABEL_OVERALL_GROUP_KEYS = (
    "filter_name",
    "filter_version",
    "threshold_version",
    "filter_label",
)
_FILTER_LABEL_BY_TIER_GROUP_KEYS = (
    "tier_index",
    "tier_name",
    "filter_name",
    "filter_version",
    "threshold_version",
    "filter_label",
)


def _build_cohort_filter_label_overall(
    long_df: pd.DataFrame, run_id: str
) -> pd.DataFrame:
    cols = _cohort_columns_with_group(_FILTER_LABEL_OVERALL_GROUP_KEYS)
    filtered = _filter_label_rows(long_df)
    if filtered.empty:
        return pd.DataFrame(columns=cols)
    cohort = compute_cohort_rates(
        filtered, list(_FILTER_LABEL_OVERALL_GROUP_KEYS)
    )
    cohort.insert(0, "run_id", run_id)
    cohort = cohort.sort_values(
        by=["filter_name", "filter_version", "threshold_version", "filter_label"],
        ascending=True,
        na_position="last",
        kind="mergesort",
    ).reset_index(drop=True)
    return cohort[list(cols)]


def _build_cohort_filter_label_by_tier(
    long_df: pd.DataFrame, run_id: str
) -> pd.DataFrame:
    cols = _cohort_columns_with_group(_FILTER_LABEL_BY_TIER_GROUP_KEYS)
    filtered = _filter_label_rows(long_df)
    if filtered.empty:
        return pd.DataFrame(columns=cols)
    cohort = compute_cohort_rates(
        filtered,
        list(_FILTER_LABEL_BY_TIER_GROUP_KEYS),
    )
    cohort.insert(0, "run_id", run_id)
    cohort = cohort.sort_values(
        by=[
            "tier_index",
            "filter_name",
            "filter_version",
            "threshold_version",
            "filter_label",
        ],
        ascending=True,
        na_position="last",
        kind="mergesort",
    ).reset_index(drop=True)
    return cohort[list(cols)]


def _build_cohort_primitive_bucket_by_tier(
    long_df: pd.DataFrame,
    primitives: Sequence[str],
    run_id: str,
    manifest: ManifestBuilder,
) -> pd.DataFrame:
    if long_df.empty or not primitives:
        return pd.DataFrame(columns=PRIMITIVE_BUCKET_COLUMNS)

    # M2: quartile edges computed once per primitive from the full
    # eligible WOULD_ALERT population, applied globally across tiers
    # (NOT per-tier). Deduplicate to one row per alert_decision_id so
    # decisions with multiple filter evaluations contribute one value.
    by_decision = long_df.drop_duplicates(
        subset=["alert_decision_id"], keep="first"
    )

    parts: list[pd.DataFrame] = []
    for primitive in primitives:
        if primitive not in long_df.columns:
            manifest.register_primitive(
                primitive,
                method="quartile",
                skipped=True,
                skip_reason="column_absent_from_long_csv",
                edges=None,
                buckets=[],
                distinct_value_count=0,
            )
            continue

        values = by_decision[primitive].tolist()
        is_bool = primitive in DSF_BOOL_COLUMNS
        result = bucket_one_primitive(primitive, values, is_boolean=is_bool)

        non_null_values = [v for v in values if v is not None and not _is_nan(v)]
        distinct_count = len({float(v) for v in non_null_values}) if non_null_values else 0

        bucket_dicts = [
            {
                "bucket_index": spec.bucket_index,
                "bucket_label": spec.bucket_label,
                "bucket_low": spec.bucket_low,
                "bucket_high": spec.bucket_high,
                "bucket_order": spec.bucket_order,
            }
            for spec in result.bucket_specs
        ]
        manifest.register_primitive(
            primitive,
            method=result.method,
            skipped=result.skipped,
            skip_reason=result.skip_reason,
            edges=result.edges,
            buckets=bucket_dicts,
            distinct_value_count=distinct_count,
        )
        if result.skipped:
            continue

        assignments_map = dict(
            zip(
                by_decision["alert_decision_id"].tolist(),
                result.assignments,
            )
        )
        spec_map = {spec.bucket_index: spec for spec in result.bucket_specs}

        local = long_df.copy()
        local["__bucket_index"] = local["alert_decision_id"].map(assignments_map)

        cohort = compute_cohort_rates(
            local, ["tier_index", "tier_name", "__bucket_index"]
        )
        cohort["primitive_name"] = primitive
        cohort["bucket_method"] = result.method
        cohort["bucket_index"] = cohort["__bucket_index"]
        cohort["bucket_label"] = cohort["__bucket_index"].map(
            {k: v.bucket_label for k, v in spec_map.items()}
        )
        cohort["bucket_low"] = cohort["__bucket_index"].map(
            {k: v.bucket_low for k, v in spec_map.items()}
        )
        cohort["bucket_high"] = cohort["__bucket_index"].map(
            {k: v.bucket_high for k, v in spec_map.items()}
        )
        cohort["bucket_order"] = cohort["__bucket_index"].map(
            {k: v.bucket_order for k, v in spec_map.items()}
        )
        cohort.drop(columns=["__bucket_index"], inplace=True)
        cohort.insert(0, "run_id", run_id)
        parts.append(cohort)

    if not parts:
        return pd.DataFrame(columns=PRIMITIVE_BUCKET_COLUMNS)

    out = pd.concat(parts, ignore_index=True)
    # Reorder & sort per §5.2.
    out = out[list(PRIMITIVE_BUCKET_COLUMNS)]
    out = out.sort_values(
        by=["tier_index", "primitive_name", "bucket_order"],
        ascending=True,
        na_position="last",
        kind="mergesort",
    ).reset_index(drop=True)
    return out


def _is_nan(v: object) -> bool:
    return isinstance(v, float) and v != v  # NaN != NaN


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def run(readers: SubstrateReaders, params: RunParams) -> RunResult:
    """Pure orchestrator: read, join, derive, group, return.

    NO file I/O. NO DB writes. The DB connections behind ``readers``
    must already be opened read-only by the caller (the CLI uses
    ``sqlite3.connect(..., uri=True)`` with ``mode=ro``).
    """

    created_at = params.created_at or datetime.now(timezone.utc)
    run_id = params.run_id or generate_run_id(created_at)

    builder = ManifestBuilder(run_id=run_id, created_at=created_at)
    builder.set_parameter(
        "included_decision_statuses", list(params.included_decision_statuses)
    )
    builder.set_parameter(
        "decision_time_range_start", _iso(params.decision_time_range_start)
    )
    builder.set_parameter(
        "decision_time_range_end", _iso(params.decision_time_range_end)
    )
    builder.set_parameter("as_of_time", _iso(params.as_of_time))
    # NOTE: output_root is deliberately NOT recorded in manifest.parameters.
    # It is a file-system configuration (where to write), not an analysis
    # input, and recording an absolute path breaks TEST 9 byte-identity
    # across runs that pick different output roots. The run directory's
    # own location is implicit from the manifest's filesystem path.

    builder.set_pre_join_count("alert_decisions", readers.alert_decisions.count())
    builder.set_pre_join_count(
        "filter_evaluations", readers.filter_evaluations.count()
    )
    builder.set_pre_join_count(
        "decision_score_features", readers.decision_score_features.count()
    )
    builder.set_pre_join_count("outcome_windows", readers.outcome_windows.count())

    decisions = readers.alert_decisions.read_all(
        included_decision_types=params.included_decision_statuses,
        decision_time_range_start=params.decision_time_range_start,
        decision_time_range_end=params.decision_time_range_end,
    )
    builder.set_post_join_count("eligible_decisions", len(decisions))

    primitives = readers.decision_score_features.discover_primitive_columns()

    if decisions.empty:
        long_df = _empty_long_df()
        tier_baseline = _build_cohort_tier_baseline(long_df, run_id)
        filter_overall = _build_cohort_filter_label_overall(long_df, run_id)
        filter_by_tier = _build_cohort_filter_label_by_tier(long_df, run_id)
        primitive_bucket = _build_cohort_primitive_bucket_by_tier(
            long_df, primitives, run_id, builder
        )
    else:
        ids = decisions["id"].tolist()
        filters = readers.filter_evaluations.read_for_decisions(ids)
        dsf = readers.decision_score_features.read_for_decisions(ids)
        outcomes = readers.outcome_windows.read_for_decisions(ids)

        symbols: dict[str, str | None] = {}
        if readers.token_identity is not None:
            symbols = readers.token_identity.read_symbols(
                decisions["token_address"].tolist()
            )

        long_df = _build_long_df(
            decisions, filters, dsf, outcomes, symbols, primitives
        )
        long_df = _apply_long_csv_sort(long_df)

        tier_baseline = _build_cohort_tier_baseline(long_df, run_id)
        filter_overall = _build_cohort_filter_label_overall(long_df, run_id)
        filter_by_tier = _build_cohort_filter_label_by_tier(long_df, run_id)
        primitive_bucket = _build_cohort_primitive_bucket_by_tier(
            long_df, primitives, run_id, builder
        )

    builder.set_post_join_count("long_csv_rows", len(long_df))
    builder.set_post_join_count("cohort_tier_baseline_rows", len(tier_baseline))
    builder.set_post_join_count(
        "cohort_filter_label_overall_rows", len(filter_overall)
    )
    builder.set_post_join_count(
        "cohort_filter_label_by_tier_rows", len(filter_by_tier)
    )
    builder.set_post_join_count(
        "cohort_primitive_bucket_by_tier_rows", len(primitive_bucket)
    )

    builder.register_output(
        "long",
        filename=LONG_CSV_FILENAME,
        schema=list(long_df.columns),
        row_count=len(long_df),
    )
    builder.register_output(
        "cohort_tier_baseline",
        filename=COHORT_TIER_BASELINE_FILENAME,
        schema=list(tier_baseline.columns),
        row_count=len(tier_baseline),
    )
    builder.register_output(
        "cohort_filter_label_overall",
        filename=COHORT_FILTER_LABEL_OVERALL_FILENAME,
        schema=list(filter_overall.columns),
        row_count=len(filter_overall),
    )
    builder.register_output(
        "cohort_filter_label_by_tier",
        filename=COHORT_FILTER_LABEL_BY_TIER_FILENAME,
        schema=list(filter_by_tier.columns),
        row_count=len(filter_by_tier),
    )
    builder.register_output(
        "cohort_primitive_bucket_by_tier",
        filename=COHORT_PRIMITIVE_BUCKET_BY_TIER_FILENAME,
        schema=list(primitive_bucket.columns),
        row_count=len(primitive_bucket),
    )

    builder.capture_environment()
    # m-3 remediation: git fingerprint is captured by the CLI (which is
    # the boundary for environmental I/O) and passed through RunParams.
    # The orchestrator never invokes subprocess.
    builder.set_git_fingerprint(params.git_commit, params.git_dirty)

    manifest_dict = builder.to_dict()

    return RunResult(
        run_id=run_id,
        long_df=long_df,
        cohort_tier_baseline=tier_baseline,
        cohort_filter_label_overall=filter_overall,
        cohort_filter_label_by_tier=filter_by_tier,
        cohort_primitive_bucket_by_tier=primitive_bucket,
        manifest=manifest_dict,
        readme_context=manifest_dict,
    )

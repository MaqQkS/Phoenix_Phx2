"""Stage 13 recommendation builder.

Given a Stage 12 ``CSVBundle`` produced by the loader, walk every
cohort row, classify it via the pure-function classifier, apply the
per-tier override rule to overall rows, and return one
``RecommendationRow`` per cohort.

The builder is the only Stage 13 module that knows the Stage 12 column
names by heart. The loader and writer treat columns as opaque dicts.
The classifier operates on already-extracted numeric inputs. Mapping
between the two lives here.

Order of operations:
  1. Compute the baseline-rate lookup table from cohort_tier_baseline,
     plus an "overall" baseline weighted across tiers.
  2. Classify every per-tier filter row and primitive-bucket row.
  3. Classify every overall filter row standalone, then apply the
     per-tier override against the matching per-tier rows.
  4. For each classified row, attach policy_severity, review_priority,
     watchlist_flag, and notes.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from PHX2.stage13.classifier import (
    apply_anomaly_overrides,
    apply_censoring_downgrade,
    apply_confidence_ceiling,
    apply_per_tier_override,
    classify_row,
    compute_censoring_rate,
    determine_direction,
    summarize_tier_support,
)
from PHX2.stage13.loader import CSVBundle, Stage13ValidationError
from PHX2.stage13.types import (
    SCAM_ADJACENT_LABELS,
    ActionClass,
    Direction,
    EvidenceClass,
    EvidenceThresholds,
    PolicySeverity,
    RecommendationRow,
    ReviewPriority,
    TierScope,
)
from PHX2.stage13.wilson import ci_excludes_baseline as ci_excludes_helper


# ---------------------------------------------------------------------------
# Baseline lookup
# ---------------------------------------------------------------------------


def _tier_baselines_from_rows(
    rows: list[dict[str, Any]],
) -> dict[tuple[int | None, str | None], float | None]:
    """Build a ``(tier_index, tier_name) -> baseline_rate`` lookup.

    Stage 12 emits one baseline row per tier; the rate column is
    ``hit_2x_24h_rate``. The result preserves None tier_index / tier_name
    rows so callers can join across (None, None) cohorts cleanly.
    """

    out: dict[tuple[int | None, str | None], float | None] = {}
    for row in rows:
        key = (row.get("tier_index"), row.get("tier_name"))
        value = row.get("hit_2x_24h_rate")
        out[key] = float(value) if isinstance(value, (int, float)) else None
    return out


def _compute_overall_baseline_rate(
    baseline_rows: list[dict[str, Any]],
) -> float | None:
    """Weighted hit_2x rate across per-tier baseline rows.

    Computed as ``sum(tier.hit_2x_24h_count) / sum(tier.n_complete)``.
    Returns None when the denominator is zero or when no Stage 12
    baseline rows are present.
    """

    num = 0.0
    den = 0
    for row in baseline_rows:
        n_complete = row.get("n_complete")
        if not isinstance(n_complete, int) or n_complete <= 0:
            continue
        count = row.get("hit_2x_24h_count")
        if not isinstance(count, int):
            continue
        num += float(count)
        den += n_complete
    if den == 0:
        return None
    return num / den


def resolve_baseline_rate(
    *,
    tier_scope: TierScope,
    tier_index: int | None,
    tier_name: str | None,
    tier_baselines: dict[tuple[int | None, str | None], float | None],
    overall_baseline: float | None,
) -> float | None:
    """Look up the baseline rate for one cohort row.

    For ``tier_scope="overall"``, returns the population-weighted
    ``overall_baseline`` computed across all per-tier baseline rows.

    For per-tier scopes, the lookup requires an exact match on
    ``(tier_index, tier_name)`` against the Stage 12 ``cohort_tier_baseline``
    file. There is no loose fall-back: per-cohort rows and baseline
    rows come from the same Stage 12 join, so a mismatch on either
    component of the key indicates a data-contract violation between
    Stage 12 outputs. Raising loudly is preferred over silently using
    a near-match that could distort lift calculations downstream.

    Stage 12 does not emit a baseline_rate column on individual cohort
    rows, so the lookup is always via this helper (spec §BASELINE RATE
    RESOLUTION).

    Raises:
      Stage13ValidationError: if the per-tier (tier_index, tier_name)
        pair is not present in ``tier_baselines``.
    """

    if tier_scope == "overall":
        return overall_baseline

    key = (tier_index, tier_name)
    if key in tier_baselines:
        return tier_baselines[key]

    # F2 remediation: strict match. The loose tier_name-only fallback
    # used previously could quietly substitute a different tier's
    # baseline when tier_index disagreed between cohort and baseline
    # rows. That is a contract violation between Stage 12 outputs, not
    # a Stage 13 concern to paper over.
    raise Stage13ValidationError(
        f"Per-tier baseline lookup failed for tier_scope={tier_scope!r}: "
        f"no Stage 12 baseline row with key "
        f"(tier_index={tier_index!r}, tier_name={tier_name!r}); "
        f"available keys: {sorted(tier_baselines.keys(), key=str)!r}"
    )


# ---------------------------------------------------------------------------
# Severity + priority
# ---------------------------------------------------------------------------


def compute_policy_severity(
    row: dict[str, Any],
    severity_available: bool,
    severity_column: str | None,
) -> PolicySeverity:
    """Compute policy_severity from the Stage 12 row's decision-volume
    column, when present.

    Bands per spec §POLICY SEVERITY:
      < 5%        -> low
      5% .. 20%   -> medium
      > 20%       -> high
      missing     -> unknown
    """

    if not severity_available or severity_column is None:
        return "unknown"

    raw = row.get(severity_column)
    if raw is None:
        return "unknown"

    coverage: float | None
    if severity_column == "decision_share":
        if isinstance(raw, (int, float)):
            coverage = float(raw)
        else:
            return "unknown"
    elif severity_column == "n_decisions_total":
        # Without the global denominator, a single n_decisions_total
        # column cannot be turned into a coverage ratio. v0 leaves
        # this path as "unknown" -- the operator can add a
        # decision_share column if they want true severity bands.
        return "unknown"
    else:
        return "unknown"

    if coverage < 0.05:
        return "low"
    if coverage <= 0.20:
        return "medium"
    return "high"


def _is_scam_adjacent(cohort_id: str) -> bool:
    return any(label in cohort_id for label in SCAM_ADJACENT_LABELS)


def compute_review_priority(
    action_class: ActionClass,
    policy_severity: PolicySeverity,
    cohort_id: str,
) -> ReviewPriority:
    """Spec §REVIEW PRIORITY.

    urgent  : ADVANCE + (severity=high OR scam-adjacent label)
    high    : ADVANCE + severity=medium
    normal  : ADVANCE + severity in (low, unknown), OR ANOMALY_FLAG
    low     : everything else
    """

    if action_class == "ADVANCE_AS_CANDIDATE":
        if policy_severity == "high" or _is_scam_adjacent(cohort_id):
            return "urgent"
        if policy_severity == "medium":
            return "high"
        return "normal"

    if action_class == "ANOMALY_FLAG":
        return "normal"

    return "low"


# ---------------------------------------------------------------------------
# Cohort-id assembly
# ---------------------------------------------------------------------------


def _filter_cohort_id(row: dict[str, Any]) -> str:
    """Build the cohort_id for a filter-label cohort.

    Format: ``filter_name@filter_version[threshold=threshold_version]:filter_label``.
    Threshold version is included because spec §FILTER COHORT IDENTITY
    (Stage 12 remediation M-1) treats it as a first-class identity
    dimension.
    """

    name = row.get("filter_name", "?")
    version = row.get("filter_version", "?")
    threshold = row.get("threshold_version", "?")
    label = row.get("filter_label", "?")
    return f"{name}@{version}[threshold={threshold}]:{label}"


def _primitive_cohort_id(row: dict[str, Any]) -> str:
    """Build the cohort_id for a primitive-bucket cohort.

    Format: ``primitive_name:bucket_label``. Buckets are already
    identified by label in Stage 12's output.
    """

    primitive = row.get("primitive_name", "?")
    label = row.get("bucket_label", "?")
    return f"{primitive}:{label}"


# ---------------------------------------------------------------------------
# Per-row classification
# ---------------------------------------------------------------------------


def _required_int(value: Any, *, field_name: str, cohort_id: str) -> int:
    """Coerce a required Stage 12 integer column into ``int``.

    Required fields (``n_complete``, ``n_censored``) must be present
    and parseable. Missing / None / non-numeric values would
    previously have silently become 0, masking upstream data
    corruption and skewing every n-band classification for the
    affected row. F3 remediation: raise so the caller surfaces the
    bad row to the operator.

    Raises:
      Stage13ValidationError: when the cell is None or non-numeric.
    """

    if isinstance(value, bool):
        # bool is a subclass of int; reject explicitly so True/False
        # cells don't sneak past as 1/0.
        raise Stage13ValidationError(
            f"Required integer column {field_name!r} for cohort "
            f"{cohort_id!r} is a boolean ({value!r}); expected int."
        )
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if value != value:  # NaN
            raise Stage13ValidationError(
                f"Required integer column {field_name!r} for cohort "
                f"{cohort_id!r} is NaN; expected int."
            )
        return int(value)
    raise Stage13ValidationError(
        f"Required integer column {field_name!r} for cohort "
        f"{cohort_id!r} is missing or non-numeric ({value!r}); "
        "expected int."
    )


def _optional_float(value: Any) -> float | None:
    """Coerce an optional Stage 12 numeric column into ``float | None``.

    Stage 12 emits NULL (empty CSV cells -> None) for rate/CI columns
    on cohorts whose ``n_complete`` is zero. ``None`` is propagated as
    a first-class signal so downstream classifier code can branch on
    "rate undefined" cleanly; silent coercion to 0.0 would be wrong
    because 0.0 is itself a legitimate rate value.
    """

    if isinstance(value, bool):
        return None
    if isinstance(value, float):
        if value != value:  # NaN
            return None
        return value
    if isinstance(value, int):
        return float(value)
    return None


def _classify_single_row(
    *,
    policy_surface: str,
    cohort_id: str,
    tier_scope: TierScope,
    row: dict[str, Any],
    baseline_rate: float | None,
    thresholds: EvidenceThresholds,
    severity_available: bool,
    severity_column: str | None,
) -> RecommendationRow:
    """Classify one Stage 12 cohort row into a RecommendationRow.

    The per-tier override is applied separately by the caller for
    overall rows; this function returns the standalone classification.
    """

    n_complete = _required_int(
        row.get("n_complete"), field_name="n_complete", cohort_id=cohort_id
    )
    n_censored = _required_int(
        row.get("n_censored"), field_name="n_censored", cohort_id=cohort_id
    )
    cohort_rate = _optional_float(row.get("hit_2x_24h_rate"))
    ci_low = _optional_float(row.get("hit_2x_24h_ci_low"))
    ci_high = _optional_float(row.get("hit_2x_24h_ci_high"))
    confidence_flag = row.get("confidence_flag")

    lift_absolute: float | None
    lift_relative: float | None
    if cohort_rate is None or baseline_rate is None:
        lift_absolute = None
        lift_relative = None
    else:
        lift_absolute = cohort_rate - baseline_rate
        if baseline_rate == 0.0:
            lift_relative = None
        else:
            lift_relative = (cohort_rate - baseline_rate) / baseline_rate

    direction: Direction = determine_direction(cohort_rate, baseline_rate)
    ci_excludes = ci_excludes_helper(ci_low, ci_high, baseline_rate)

    evidence, action = classify_row(
        n_complete=n_complete,
        lift_absolute=lift_absolute,
        ci_excludes_baseline=ci_excludes,
        direction=direction,
        thresholds=thresholds,
    )

    censoring_rate = compute_censoring_rate(n_complete, n_censored)
    evidence, action, censoring_flag = apply_censoring_downgrade(
        evidence, action, censoring_rate, thresholds
    )

    evidence, action, ceiling_applied = apply_confidence_ceiling(
        evidence,
        action,
        confidence_flag if isinstance(confidence_flag, str) else None,
        direction,
    )

    candidate_action, candidate_direction, anomaly_notes, anomaly_triggered = (
        apply_anomaly_overrides(
            cohort_rate=cohort_rate,
            baseline_rate=baseline_rate,
            action=action,
            direction=direction,
        )
    )

    # F1 remediation: n-band dominance. The n-band gate is dominant per
    # spec §EVIDENCE-CLASS GATING -- "the n band is the dominant gate."
    # Rows with n_complete < insufficient_below MUST remain
    # INSUFFICIENT_EVIDENCE / insufficient regardless of cohort_rate or
    # baseline_rate extremes. Anomaly notes are still attached for
    # transparency so reviewers see *why* the row would otherwise have
    # been flagged.
    if n_complete < thresholds.insufficient_below:
        # Preserve INSUFFICIENT_EVIDENCE classification; record any
        # anomaly observation as a note rather than promoting to
        # ANOMALY_FLAG.
        anomaly_triggered = False
        # action and direction stay at the post-classify_row values
        # ("INSUFFICIENT_EVIDENCE" + "none").
    else:
        action = candidate_action
        direction = candidate_direction

    notes: list[str] = list(anomaly_notes)
    loosen_capped_flag = False
    if direction == "loosen":
        # Spec L6: loosen never advances. Annotate if it was a strong-
        # tighten candidate downgraded; here it stayed loosen so we
        # simply flag for transparency.
        loosen_capped_flag = True

    severity = compute_policy_severity(row, severity_available, severity_column)
    priority = compute_review_priority(action, severity, cohort_id)

    watchlist_flag = priority in ("urgent", "high")

    if anomaly_triggered and "baseline_rate_zero" in anomaly_notes:
        # Force evidence_class to be informative even when baseline is 0.
        if evidence == "strong":
            evidence = "moderate"

    # Schema 1.1 filter-identity columns. cohort_id continues to encode
    # the same four parts for filter_label_blocking rows; surfacing them
    # as standalone columns lets Stage 14 join against Stage 12 long-CSV
    # rows by tuple instead of by cohort_id string parsing. For the
    # primitive_bucket_cohort surface the fields are not applicable, so
    # they stay None rather than being faked.
    if policy_surface == "filter_label_blocking":
        filter_name_value = row.get("filter_name")
        filter_version_value = row.get("filter_version")
        filter_label_value = row.get("filter_label")
        threshold_version_value = row.get("threshold_version")
    else:
        filter_name_value = None
        filter_version_value = None
        filter_label_value = None
        threshold_version_value = None

    return RecommendationRow(
        policy_surface=policy_surface,  # type: ignore[arg-type]
        cohort_id=cohort_id,
        tier_scope=tier_scope,
        action_class=action,
        direction=direction,
        evidence_class=evidence,
        policy_severity=severity,
        review_priority=priority,
        n_complete=n_complete,
        n_censored=n_censored,
        cohort_rate=cohort_rate,
        baseline_rate=baseline_rate,
        lift_absolute=lift_absolute,
        lift_relative=lift_relative,
        wilson_ci_low=ci_low,
        wilson_ci_high=ci_high,
        ci_excludes_baseline=ci_excludes,
        censoring_rate=censoring_rate,
        censoring_warning_flag=censoring_flag,
        watchlist_flag=watchlist_flag,
        tier_evidence_support=[],
        cross_tier_disagreement=False,
        loosen_capped_flag=loosen_capped_flag,
        confidence_ceiling_applied=ceiling_applied,
        notes=notes,
        filter_name=filter_name_value,
        filter_version=filter_version_value,
        filter_label=filter_label_value,
        threshold_version=threshold_version_value,
    )


def _apply_overall_override(
    overall_row: RecommendationRow,
    per_tier_rows: list[RecommendationRow],
) -> RecommendationRow:
    """Apply the per-tier override rule to a single overall row.

    Recomputes ``action_class``, ``direction``, ``notes``,
    ``tier_evidence_support``, and ``cross_tier_disagreement`` per spec
    §PER-TIER OVERRIDE RULE.
    """

    per_tier_dicts: list[dict[str, object]] = [
        {
            "cohort_id": r.cohort_id,
            "tier_scope": r.tier_scope,
            "action_class": r.action_class,
            "direction": r.direction,
        }
        for r in per_tier_rows
        if r.cohort_id == overall_row.cohort_id
    ]
    summary = summarize_tier_support(overall_row.cohort_id, per_tier_dicts)
    action, direction, notes, support, disagreement = apply_per_tier_override(
        overall_action=overall_row.action_class,
        overall_direction=overall_row.direction,
        overall_notes=overall_row.notes,
        tier_support=summary,
    )

    # Re-evaluate review_priority based on the new action_class.
    severity = overall_row.policy_severity
    priority = compute_review_priority(action, severity, overall_row.cohort_id)
    watchlist_flag = priority in ("urgent", "high")

    return replace(
        overall_row,
        action_class=action,
        direction=direction,
        notes=notes,
        tier_evidence_support=support,
        cross_tier_disagreement=disagreement,
        review_priority=priority,
        watchlist_flag=watchlist_flag,
    )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def build_recommendations(
    csv_bundle: CSVBundle,
    thresholds: EvidenceThresholds,
) -> list[RecommendationRow]:
    """Walk the CSV bundle and produce one RecommendationRow per cohort.

    The returned list contains every classified row -- INSUFFICIENT_EVIDENCE,
    ANOMALY_FLAG, HOLD_OBSERVE_ONLY, NO_SIGNAL_FOUND, and
    ADVANCE_AS_CANDIDATE alike. The writer is responsible for splitting
    these across the candidate_recommendations vs evidence_summary CSVs.
    """

    tier_baselines = _tier_baselines_from_rows(csv_bundle.tier_baseline)
    overall_baseline = _compute_overall_baseline_rate(csv_bundle.tier_baseline)

    severity_available = csv_bundle.severity_column is not None

    rows: list[RecommendationRow] = []

    # Per-tier filter-label cohorts. Must come BEFORE overall rows so
    # the per-tier override can see them.
    per_tier_filter_rows: list[RecommendationRow] = []
    for raw in csv_bundle.filter_label_by_tier:
        tier_name = raw.get("tier_name")
        tier_index = raw.get("tier_index")
        tier_scope = _coerce_tier_scope(tier_name)
        cohort_id = _filter_cohort_id(raw)
        baseline = resolve_baseline_rate(
            tier_scope=tier_scope,
            tier_index=tier_index if isinstance(tier_index, int) else None,
            tier_name=tier_name if isinstance(tier_name, str) else None,
            tier_baselines=tier_baselines,
            overall_baseline=overall_baseline,
        )
        rec = _classify_single_row(
            policy_surface="filter_label_blocking",
            cohort_id=cohort_id,
            tier_scope=tier_scope,
            row=raw,
            baseline_rate=baseline,
            thresholds=thresholds,
            severity_available=severity_available,
            severity_column=csv_bundle.severity_column,
        )
        per_tier_filter_rows.append(rec)

    # Per-tier primitive-bucket cohorts (no overall variant in Stage 12).
    primitive_rows: list[RecommendationRow] = []
    for raw in csv_bundle.primitive_bucket_by_tier:
        tier_name = raw.get("tier_name")
        tier_index = raw.get("tier_index")
        tier_scope = _coerce_tier_scope(tier_name)
        cohort_id = _primitive_cohort_id(raw)
        baseline = resolve_baseline_rate(
            tier_scope=tier_scope,
            tier_index=tier_index if isinstance(tier_index, int) else None,
            tier_name=tier_name if isinstance(tier_name, str) else None,
            tier_baselines=tier_baselines,
            overall_baseline=overall_baseline,
        )
        rec = _classify_single_row(
            policy_surface="primitive_bucket_cohort",
            cohort_id=cohort_id,
            tier_scope=tier_scope,
            row=raw,
            baseline_rate=baseline,
            thresholds=thresholds,
            severity_available=severity_available,
            severity_column=csv_bundle.severity_column,
        )
        primitive_rows.append(rec)

    # Overall filter-label cohorts, then per-tier override.
    overall_filter_rows: list[RecommendationRow] = []
    for raw in csv_bundle.filter_label_overall:
        cohort_id = _filter_cohort_id(raw)
        rec = _classify_single_row(
            policy_surface="filter_label_blocking",
            cohort_id=cohort_id,
            tier_scope="overall",
            row=raw,
            baseline_rate=overall_baseline,
            thresholds=thresholds,
            severity_available=severity_available,
            severity_column=csv_bundle.severity_column,
        )
        overall_filter_rows.append(_apply_overall_override(rec, per_tier_filter_rows))

    rows.extend(per_tier_filter_rows)
    rows.extend(overall_filter_rows)
    rows.extend(primitive_rows)

    return rows


def _coerce_tier_scope(tier_name: Any) -> TierScope:
    """Cast a raw tier_name string to a TierScope literal.

    Stage 12 tier_name values are ``"T1" | "T2" | "T3" | None`` (STEP 0
    S0-3 + analysis_fixture_builder confirmation). Unknown values fall
    back to "overall" only as a degenerate safety net; in normal data
    every per-tier row's tier_name lies in {T1, T2, T3}.
    """

    if tier_name == "T1":
        return "T1"
    if tier_name == "T2":
        return "T2"
    if tier_name == "T3":
        return "T3"
    return "overall"

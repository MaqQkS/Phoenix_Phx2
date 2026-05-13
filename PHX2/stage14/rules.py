"""Stage 14 rule translation.

Takes the raw Stage 13 candidate rows (dicts of strings) and produces
two outputs:

  * A tuple of ``ShadowRule`` -- one per content-stable rule identity
    tuple. Multiple Stage 13 rows that collapse to the same identity
    tuple are merged into one rule, with all source recommendations
    preserved on the rule's payload for traceability. Rule IDs are
    short SHA-256 hex hashes over the canonical identity string, so
    reruns over an unchanged Stage 13 candidate produce the same rule
    ID even if other candidates are inserted before or after.
  * A tuple of ``ExcludedRow`` -- one per Stage 13 row that did not
    pass the v0 eligibility gate. Each row carries an
    ``exclusion_reason`` drawn from the locked vocabulary in
    ``PHX2.stage14.types.EXCLUSION_REASONS``. The gate order is
    intentional: a row fails on the *first* gate it violates.

Invariant (enforced by ``translate_recommendations``):
    len(candidate_rows) == sum(rule.source_row_count for rule in rules)
                          + len(excluded)
So every input row maps to exactly one shadow rule's source-list or
to exactly one excluded row.
"""

from __future__ import annotations

from collections import OrderedDict
from typing import Iterable

from PHX2.stage14.hashing import short_content_hash
from PHX2.stage14.types import (
    EXCLUSION_MISSING_FILTER_IDENTITY,
    EXCLUSION_NOT_ADVANCE_CANDIDATE,
    EXCLUSION_NOT_FILTER_LABEL_SURFACE,
    EXCLUSION_NOT_TIGHTEN,
    EXCLUSION_TIER_SCOPE_OVERALL,
    ExcludedRow,
    ShadowRule,
    SourceRecommendation,
)


# The single simulated action allowed in v0. Locked vocabulary; do not
# fan out to other action enums without re-opening the Stage 14 spec.
SIMULATED_BLOCK = "SIMULATED_BLOCK"
TIGHTEN_DIRECTION = "tighten"
FILTER_LABEL_BLOCKING_SURFACE = "filter_label_blocking"
ELIGIBLE_TIER_SCOPES: frozenset[str] = frozenset({"T1", "T2", "T3"})


# ---------------------------------------------------------------------------
# Eligibility gate
# ---------------------------------------------------------------------------


def _classify_row(row: dict[str, str]) -> str | None:
    """Return the exclusion reason for ``row``, or ``None`` if eligible.

    Gate order (locked):
      1. policy_surface == "filter_label_blocking"
      2. action_class == "ADVANCE_AS_CANDIDATE"
      3. direction == "tighten"
      4. tier_scope in {T1, T2, T3}
      5. all four filter-identity columns non-empty
    """

    if row.get("policy_surface") != FILTER_LABEL_BLOCKING_SURFACE:
        return EXCLUSION_NOT_FILTER_LABEL_SURFACE
    if row.get("action_class") != "ADVANCE_AS_CANDIDATE":
        return EXCLUSION_NOT_ADVANCE_CANDIDATE
    if row.get("direction") != TIGHTEN_DIRECTION:
        return EXCLUSION_NOT_TIGHTEN
    if row.get("tier_scope") not in ELIGIBLE_TIER_SCOPES:
        return EXCLUSION_TIER_SCOPE_OVERALL
    for col in ("filter_name", "filter_version", "filter_label", "threshold_version"):
        if not (row.get(col) or "").strip():
            return EXCLUSION_MISSING_FILTER_IDENTITY
    return None


# ---------------------------------------------------------------------------
# Rule ID minting
# ---------------------------------------------------------------------------


def compute_rule_id(
    *,
    policy_surface: str,
    tier_scope: str,
    filter_name: str,
    filter_version: str,
    filter_label: str,
    threshold_version: str,
    simulated_action: str,
) -> str:
    """Mint a content-stable rule ID.

    Hash input is the pipe-joined identity tuple; the leading 12 hex
    chars of SHA-256 are appended to ``shadow_rule_``. Two reruns over
    the same Stage 13 candidate produce the same rule_id even when row
    order or unrelated candidates change. Reviewer sign-off in Stage
    15 can therefore reference a rule ID that survives later Stage 14
    reruns until the underlying identity changes.
    """

    canonical = "|".join(
        [
            policy_surface,
            tier_scope,
            filter_name,
            filter_version,
            filter_label,
            threshold_version,
            simulated_action,
        ]
    )
    return f"shadow_rule_{short_content_hash(canonical, length=12)}"


# ---------------------------------------------------------------------------
# Source-row coercion
# ---------------------------------------------------------------------------


def _optional_float(value: str | None) -> float | None:
    if value is None:
        return None
    text = value.strip()
    if text == "":
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _optional_int(value: str | None) -> int | None:
    if value is None:
        return None
    text = value.strip()
    if text == "":
        return None
    try:
        return int(text)
    except ValueError:
        try:
            return int(float(text))
        except ValueError:
            return None


def _optional_string(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.strip()
    return text if text != "" else None


def _source_recommendation(row: dict[str, str]) -> SourceRecommendation:
    return SourceRecommendation(
        cohort_id=row.get("cohort_id", "") or "",
        evidence_class=_optional_string(row.get("evidence_class")),
        policy_severity=_optional_string(row.get("policy_severity")),
        review_priority=_optional_string(row.get("review_priority")),
        n_complete=_optional_int(row.get("n_complete")),
        cohort_rate=_optional_float(row.get("cohort_rate")),
        baseline_rate=_optional_float(row.get("baseline_rate")),
        lift_absolute=_optional_float(row.get("lift_absolute")),
        lift_relative=_optional_float(row.get("lift_relative")),
    )


# ---------------------------------------------------------------------------
# Public translator
# ---------------------------------------------------------------------------


def translate_recommendations(
    candidate_rows: Iterable[dict[str, str]],
) -> tuple[tuple[ShadowRule, ...], tuple[ExcludedRow, ...]]:
    """Translate Stage 13 candidate rows into shadow rules + exclusions.

    Returns ``(rules, excluded)`` where:
      * ``rules`` is sorted by ``rule_id``.
      * Each rule's ``source_recommendations`` is sorted by cohort_id.
      * ``excluded`` preserves the input row order (the writer
        re-sorts before emission for deterministic CSV bytes).
      * Every input row is accounted for: it either contributes one
        ``SourceRecommendation`` to exactly one rule, or appears once
        in ``excluded``. The two outputs are disjoint.
    """

    rule_buckets: "OrderedDict[str, list[dict[str, str]]]" = OrderedDict()
    excluded_rows: list[ExcludedRow] = []

    for row in candidate_rows:
        reason = _classify_row(row)
        if reason is not None:
            excluded_rows.append(ExcludedRow(raw_row=dict(row), exclusion_reason=reason))
            continue

        # Eligible. Mint the rule_id and bucket by it.
        identity = (
            row["policy_surface"],
            row["tier_scope"],
            row["filter_name"],
            row["filter_version"],
            row["filter_label"],
            row["threshold_version"],
            SIMULATED_BLOCK,
        )
        rule_id = compute_rule_id(
            policy_surface=identity[0],
            tier_scope=identity[1],
            filter_name=identity[2],
            filter_version=identity[3],
            filter_label=identity[4],
            threshold_version=identity[5],
            simulated_action=identity[6],
        )
        rule_buckets.setdefault(rule_id, []).append(row)

    rules: list[ShadowRule] = []
    for rule_id, bucket in rule_buckets.items():
        # Identity tuple is consistent across the bucket by construction.
        head = bucket[0]
        sources = tuple(
            sorted(
                (_source_recommendation(r) for r in bucket),
                key=lambda s: s.cohort_id,
            )
        )
        rules.append(
            ShadowRule(
                rule_id=rule_id,
                policy_surface=head["policy_surface"],
                tier_scope=head["tier_scope"],
                filter_name=head["filter_name"],
                filter_version=head["filter_version"],
                filter_label=head["filter_label"],
                threshold_version=head["threshold_version"],
                simulated_action=SIMULATED_BLOCK,
                direction=TIGHTEN_DIRECTION,
                source_recommendations=sources,
            )
        )

    rules.sort(key=lambda r: r.rule_id)
    return tuple(rules), tuple(excluded_rows)

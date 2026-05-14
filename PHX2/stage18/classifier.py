"""Stage 18 deterministic classifier (pure, no I/O).

Classifies a single coarse-summary row into one of the six Stage
18 review labels by applying the locked gate sequence (G1..G6) in
order. On no trip, maps the Stage 17 ``descriptive_label`` through
the locked Stage 17 -> Stage 18 review-label table; an unknown
Stage 17 label is fatal (B03).

The function is pure: same inputs always produce the same
``ClassificationResult``, with no I/O, no logging, no global
state, no Stage 17 imports, no DB access.

Gate evaluation order:

  G1: ``n_matched < MIN_RULE_POSITIVE_COUNT``        (sample)
  G2: ``n_not_matched < MIN_RULE_NEGATIVE_COUNT``    (sample)
  G3: ``n_in_scope < MIN_EVALUABLE_COUNT``           (sample)
  G4: ``unevaluable_rate > MAX_UNEVALUABLE_RATE``    (data quality)
  G5: ``incomplete_outcome_ratio`` undefined         (data quality)
      (the ``complete_outcome_zero`` path) OR
      ``incomplete_outcome_ratio > MAX_INCOMPLETE_OUTCOME_RATIO``
  G6: ``headline_rows`` for this slice is empty      (data quality)

Classification rules:

  * First trip in {G1, G2, G3}             -> INSUFFICIENT_SAMPLE_REVIEW
  * First trip in {G4, G5, G6}, with no earlier
    sample trip                            -> DATA_BLOCKED_REVIEW
  * No trips, Stage 17 label is one of
    {PROMISING, WEAK, HARMFUL,
     MIXED_BY_TIER, INSUFFICIENT_SAMPLE}   -> the corresponding
                                              ``*_REVIEW`` label
  * Anything else                          -> Stage18Error("B03")

Sample gates take precedence over data-quality gates: if both fire
the classification is INSUFFICIENT_SAMPLE_REVIEW. ``gate_trips_all``
preserves every tripping gate in evaluation order for diagnostic
purposes, regardless of which bucket won the classification.

``stage17_label_preserved`` is always populated with the raw
Stage 17 label (no ``_REVIEW`` suffix). On Group A rows it is the
same information as ``classification`` modulo suffix; on Group B /
C overrides it carries the label Stage 17 would otherwise have
produced -- the operator can see what the upstream verdict was
even when Stage 18 overrode it.
"""

from __future__ import annotations

from typing import Mapping, NamedTuple, Optional, Sequence

from PHX2.stage18.constants import (
    MAX_INCOMPLETE_OUTCOME_RATIO,
    MAX_UNEVALUABLE_RATE,
    MIN_EVALUABLE_COUNT,
    MIN_RULE_NEGATIVE_COUNT,
    MIN_RULE_POSITIVE_COUNT,
    REVIEW_LABEL_DATA_BLOCKED,
    REVIEW_LABEL_HARMFUL,
    REVIEW_LABEL_INSUFFICIENT_SAMPLE,
    REVIEW_LABEL_MIXED_BY_TIER,
    REVIEW_LABEL_PROMISING,
    REVIEW_LABEL_WEAK,
    STAGE17_LABEL_HARMFUL,
    STAGE17_LABEL_INSUFFICIENT_SAMPLE,
    STAGE17_LABEL_MIXED_BY_TIER,
    STAGE17_LABEL_PROMISING,
    STAGE17_LABEL_WEAK,
)
from PHX2.stage18.errors import Stage18Error
from PHX2.stage18.metrics import (
    compute_incomplete_outcome_ratio,
    compute_tier_coverage,
    compute_unevaluable_rate,
)


# ---------------------------------------------------------------------------
# Gate identifiers (internal; exported only via ``ClassificationResult``)
# ---------------------------------------------------------------------------


_GATE_G1: str = "G1"
_GATE_G2: str = "G2"
_GATE_G3: str = "G3"
_GATE_G4: str = "G4"
_GATE_G5: str = "G5"
_GATE_G6: str = "G6"


# G5 has two distinct trip causes. The ratio-exceeded path uses
# the bare ``"G5"`` label; the zero-denominator path carries the
# ``:complete_outcome_zero`` suffix so the operator can tell the
# two apart from ``data_block_reason`` alone.
#
# ``gate_trips_all`` is a separate convention: it always uses
# plain gate IDs (``"G5"``), never the colon-suffix form, so the
# trip list stays grep-friendly across sub-reasons.
_G5_COMPLETE_OUTCOME_ZERO: str = "G5:complete_outcome_zero"


# Stage 17 -> Stage 18 review-label table for the no-gate-trip path.
_LABEL_TO_REVIEW: Mapping[str, str] = {
    STAGE17_LABEL_PROMISING: REVIEW_LABEL_PROMISING,
    STAGE17_LABEL_WEAK: REVIEW_LABEL_WEAK,
    STAGE17_LABEL_HARMFUL: REVIEW_LABEL_HARMFUL,
    STAGE17_LABEL_MIXED_BY_TIER: REVIEW_LABEL_MIXED_BY_TIER,
    STAGE17_LABEL_INSUFFICIENT_SAMPLE: REVIEW_LABEL_INSUFFICIENT_SAMPLE,
}


class ClassificationResult(NamedTuple):
    """Stage 18 classification outcome for one coarse-summary row.

    All fields are scalar except ``gate_trips_all`` which is a
    semicolon-joined string of every tripping gate ID in
    evaluation order. ``insufficient_sample_reason`` and
    ``data_block_reason`` are empty strings unless the
    corresponding bucket fired; if both sample and data-quality
    gates trip, sample-gate precedence applies and
    ``data_block_reason`` is cleared (the gate is still listed in
    ``gate_trips_all`` for diagnostic transparency).

    Locked value formats:

      ``data_block_reason``:
        * ``"G4"`` -- ``unevaluable_rate > MAX_UNEVALUABLE_RATE``.
        * ``"G5"`` -- ``incomplete_outcome_ratio >
          MAX_INCOMPLETE_OUTCOME_RATIO``.
        * ``"G5:complete_outcome_zero"`` --
          ``n_with_complete_outcome == 0`` and the ratio is
          undefined. The colon-suffix encoding keeps the field
          self-describing without introducing a separate
          sub-reason column in the output CSVs.
        * ``"G6"`` -- no headline rows for this slice.
        * ``""`` -- this row is not DATA_BLOCKED_REVIEW, OR
          sample-gate precedence cleared the bucket.

      ``insufficient_sample_reason``:
        Always one of ``{"", "G1", "G2", "G3"}``. No sub-reasons.

      ``gate_trips_all``:
        Plain gate IDs only -- ``"G1"``, ``"G2"``, ``"G3"``,
        ``"G4"``, ``"G5"``, ``"G6"`` -- semicolon-joined in
        evaluation order. Even when ``data_block_reason`` carries
        a sub-reason such as ``"G5:complete_outcome_zero"``, the
        corresponding entry in ``gate_trips_all`` is the plain
        ``"G5"``. Sub-reasons live exclusively on
        ``data_block_reason``.
    """

    classification: str
    stage17_label_preserved: str
    insufficient_sample_reason: str
    data_block_reason: str
    gate_trips_all: str
    tier_coverage: str
    unevaluable_rate: Optional[float]
    incomplete_outcome_ratio: Optional[float]


def classify_row(
    *,
    coarse_row: Mapping[str, str],
    headline_rows_for_slice: Sequence[Mapping[str, str]],
    data_quality_rows_for_slice: Sequence[Mapping[str, str]],
) -> ClassificationResult:
    """Classify one coarse-summary row.

    Args:
        coarse_row: a single row from ``coarse_summary.csv``,
            keyed by the locked column tuple.
        headline_rows_for_slice: every headline row whose
            (policy_hash, rule_id, window_seconds) matches the
            coarse row. The caller is responsible for the
            filtering; this classifier does no matching.
        data_quality_rows_for_slice: every data-quality row whose
            (policy_hash, rule_id, window_seconds) matches the
            coarse row. May include rows with any
            ``metric_name``; the metrics layer filters by
            ``scope_level == "slice"`` AND
            ``metric_name == "n_outcome_present_but_incomplete"``
            on its own.

    Returns:
        ``ClassificationResult`` -- pure value object capturing
        the chosen review label, gate diagnostics, and derived
        metrics.

    Raises:
        Stage18Error: code ``B03`` when
            ``coarse_row["descriptive_label"]`` is not one of the
            five accepted Stage 17 labels.
    """

    # Field extraction (string -> int) for the gate inputs.
    n_in_scope = int(coarse_row["n_in_scope"])
    n_matched = int(coarse_row["n_matched"])
    n_not_matched = int(coarse_row["n_not_matched"])
    n_with_complete_outcome = int(coarse_row["n_with_complete_outcome"])
    stage17_label = coarse_row["descriptive_label"]

    # Derived metrics.
    unevaluable_rate = compute_unevaluable_rate(headline_rows_for_slice)
    incomplete_outcome_ratio = compute_incomplete_outcome_ratio(
        data_quality_rows_for_slice, n_with_complete_outcome
    )
    tier_coverage = compute_tier_coverage(headline_rows_for_slice)

    # Gate evaluation: collect every trip, remember the first
    # in each group for the per-bucket reason fields.
    trips: list[str] = []
    sample_reason = ""
    data_block_reason = ""

    if n_matched < MIN_RULE_POSITIVE_COUNT:
        trips.append(_GATE_G1)
        if not sample_reason:
            sample_reason = _GATE_G1

    if n_not_matched < MIN_RULE_NEGATIVE_COUNT:
        trips.append(_GATE_G2)
        if not sample_reason:
            sample_reason = _GATE_G2

    if n_in_scope < MIN_EVALUABLE_COUNT:
        trips.append(_GATE_G3)
        if not sample_reason:
            sample_reason = _GATE_G3

    if (
        unevaluable_rate is not None
        and unevaluable_rate > MAX_UNEVALUABLE_RATE
    ):
        trips.append(_GATE_G4)
        if not data_block_reason:
            data_block_reason = _GATE_G4

    # G5 has two trip causes; both yield the same trip in
    # ``gate_trips_all`` but differ in ``data_block_reason``.
    if incomplete_outcome_ratio is None:
        # The metrics layer returns None only on
        # n_with_complete_outcome == 0.
        trips.append(_GATE_G5)
        if not data_block_reason:
            data_block_reason = _G5_COMPLETE_OUTCOME_ZERO
    elif incomplete_outcome_ratio > MAX_INCOMPLETE_OUTCOME_RATIO:
        trips.append(_GATE_G5)
        if not data_block_reason:
            data_block_reason = _GATE_G5

    if not headline_rows_for_slice:
        trips.append(_GATE_G6)
        if not data_block_reason:
            data_block_reason = _GATE_G6

    # Classification with sample-gate precedence.
    if sample_reason:
        classification = REVIEW_LABEL_INSUFFICIENT_SAMPLE
        # Sample bucket wins; the data-block reason describes a
        # gate that did fire but is not the chosen bucket.
        data_block_reason = ""
    elif data_block_reason:
        classification = REVIEW_LABEL_DATA_BLOCKED
    else:
        if stage17_label not in _LABEL_TO_REVIEW:
            raise Stage18Error(
                "B03",
                (
                    f"unknown Stage 17 descriptive_label: "
                    f"{stage17_label!r} (expected one of "
                    f"{sorted(_LABEL_TO_REVIEW.keys())})"
                ),
            )
        classification = _LABEL_TO_REVIEW[stage17_label]

    return ClassificationResult(
        classification=classification,
        stage17_label_preserved=stage17_label,
        insufficient_sample_reason=sample_reason,
        data_block_reason=data_block_reason,
        gate_trips_all=";".join(trips),
        tier_coverage=tier_coverage,
        unevaluable_rate=unevaluable_rate,
        incomplete_outcome_ratio=incomplete_outcome_ratio,
    )


__all__ = [
    "ClassificationResult",
    "classify_row",
]

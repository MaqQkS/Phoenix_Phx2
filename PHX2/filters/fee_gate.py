"""PHX2-native Fee Gate v1.0 — observe-only suspicion classifier.

Phoenix1 lineage (informational; no runtime imports or DB reads):

    Phoenix1's Fee Gate v2 was a bribe-intensity rubric derived from a
    198-token manual labeling study (April 2026). Its primary
    discriminator was ``bribes_pct_of_amm`` (bribes paid as a percentage
    of AMM fees), with a calibrated threshold of 2.81% separating
    organic activity from noise (100% organic recall, 81% noise
    rejection on the calibration sample). Phoenix1 produced an integer
    score, four labels ("Normal", "Elevated", "Suspicious",
    "SCAM Likely"), a flags list, and a stickiness rule
    (``enforce_sticky``: never downgrade). Inputs were lifetime-summed
    totals of ``total_fee``, ``lp``, ``proto``, ``creator``, ``bribes``
    (in SOL), plus ``tx_count`` (distinct signatures) and ``events``.

    Phoenix1's calibrated thresholds (from Phoenix_Bot/config.yaml and
    Phoenix_Bot/filters/fee_gate.py defaults):

      - bribes_pct_hard   = 2.81   (R1 trigger; primary separator)
      - bribes_pct_soft   = 5.0    (R2 soft-zone upper bound)
      - creator_dom_hi    = 0.70   (R3 creator-share trigger)
      - tx_count_min      = 500    (R4 thin-sample threshold)
      - suspicious_min    = 3      (band cutoff for "Suspicious")
      - scam_likely_min   = 4      (band cutoff for "SCAM Likely")

    Phoenix1's four-rule additive rubric (higher score = more
    suspicious; rules are mutually exclusive only between R1 and R2):

      - R1 (bribes hard zone): bribes_pct_of_amm < 2.81 -> +3 points
        (flag: bribes_starved)
      - R2 (bribes soft zone): 2.81 <= bribes_pct_of_amm < 5.0 ->
        +1 point (flag: bribes_low)
      - R3 (creator dominance): creator_share >= 0.70 AND
        bribes_pct_of_amm < 5.0 -> +2 points (the conjunction
        prevents penalizing heavily-manufactured tokens that pay real
        bribes; flag: creator_dom_hi)
      - R4 (thin sample): tx_count < 500 -> +1 point (flag:
        thin_sample)

    Score-to-label band mapping in Phoenix1: score 0 -> "Normal",
    score 1-2 -> "Elevated", score 3 -> "Suspicious", score >= 4 ->
    "SCAM Likely".

PHX2 Fee Gate v1.0 documented departures (six, with rationale):

  1. NO BRIBE-INTENSITY SIGNAL. PHX2 does not yet ingest bribe data.
     Phoenix1's primary calibrated discriminator is unavailable to
     v1.0; the rubric leans on creator-share dominance and pace
     heuristics instead. Recorded in KNOWN_LIMITATIONS as
     "BRIBES_SIGNAL_UNAVAILABLE".

  2. FIVE-MINUTE WINDOW HORIZON. Phoenix1 used lifetime-summed totals;
     v1.0 reads the 300-second window primitives from field_features
     (source_300s). Short horizon trades context for freshness.

  3. NO STICKINESS. Phoenix1's ``enforce_sticky`` non-downgrade rule
     is intentionally not ported. v1.0 is stateless; every evaluation
     is independent.

  4. EVENT_COUNT PROXIES TX_COUNT. Phoenix1 used distinct signatures
     for the thin-sample hedge; v1.0 uses ``event_count_5m`` (the 300s
     fee window's event count). Cardinality is not equivalent;
     thresholds need recalibration on PHX2 data before policy use.

  5. CONTINUOUS [0.0, 1.0] SCORE. Phoenix1 used an additive integer
     rubric (0, 1, 3, 4+). v1.0 emits a continuous float in [0, 1] to
     satisfy the new CHECK constraint on filter_evaluations.score and
     to make future calibration smoother.

  6. UNCALIBRATED THRESHOLDS. v1.0's threshold constants are
     placeholders awaiting Stage 12 outcome-aware calibration. Every
     constant is annotated ``# PLACEHOLDER -- uncalibrated``. Recorded
     in KNOWN_LIMITATIONS as "THRESHOLDS_UNCALIBRATED".

The label set is uppercase to align with the FilterLabel enum and the
new CHECK constraint on filter_evaluations.label.
"""

from typing import Any, Dict, List, Optional, Tuple

from PHX2.filters.base import Filter, FilterContext
from PHX2.models import DataStatus, FieldFeatures, FilterLabel, FilterResult


FILTER_NAME = "fee_gate"
FILTER_VERSION = "fee_gate_v1_no_bribes"
THRESHOLD_VERSION = "thresholds_v0_observe_only"

KNOWN_LIMITATIONS: List[str] = [
    "BRIBES_SIGNAL_UNAVAILABLE",
    "THRESHOLDS_UNCALIBRATED",
]


# R1 -- creator dominance
R1_CREATOR_SHARE_HIGH = 0.70                # PLACEHOLDER -- uncalibrated
R1_CREATOR_SHARE_ELEVATED = 0.55            # PLACEHOLDER -- uncalibrated
R1_CONTRIBUTION_HIGH = 0.40                 # PLACEHOLDER -- uncalibrated
R1_CONTRIBUTION_ELEVATED = 0.20             # PLACEHOLDER -- uncalibrated

# R2 -- LP share starvation (combined condition with creator share)
R2_LP_SHARE_LOW = 0.10                      # PLACEHOLDER -- uncalibrated
R2_CREATOR_SHARE_GATE = 0.50                # PLACEHOLDER -- uncalibrated
R2_CONTRIBUTION = 0.20                      # PLACEHOLDER -- uncalibrated

# R3 -- thin sample (event_count proxy for Phoenix1's tx_count)
R3_EVENT_COUNT_MIN = 500                    # PLACEHOLDER -- uncalibrated
R3_CONTRIBUTION = 0.10                      # PLACEHOLDER -- uncalibrated

# R4 -- fee pace anomaly (low fee_pace alongside high event_pace)
R4_FEE_PACE_LOW = 0.01                      # PLACEHOLDER -- uncalibrated
R4_EVENT_PACE_HIGH = 2.0                    # PLACEHOLDER -- uncalibrated
R4_CONTRIBUTION = 0.15                      # PLACEHOLDER -- uncalibrated

# Score-to-label thresholds. Score is clamped to [0.0, 1.0].
LABEL_THRESHOLD_SCAM_LIKELY = 0.65          # PLACEHOLDER -- uncalibrated
LABEL_THRESHOLD_SUSPICIOUS = 0.40           # PLACEHOLDER -- uncalibrated
LABEL_THRESHOLD_ELEVATED = 0.15             # PLACEHOLDER -- uncalibrated


REQUIRED_PRIMITIVE_NAMES: Tuple[str, ...] = (
    "creator_fee_share_5m",
    "lp_fee_share_5m",
    "event_count_5m",
    "fee_pace_5m_sol",
)


def _compute_score_and_reasons(
    features: FieldFeatures,
) -> Tuple[float, List[str], Dict[str, float]]:
    """Compute the raw score, the fired-reason codes, and per-rule contributions.

    Requires all REQUIRED_PRIMITIVE_NAMES to be non-None on ``features``;
    the caller in ``FeeGateFilter.evaluate`` enforces that. ``event_pace_5m``
    is optional: if None, R4 silently does not fire and an informational
    reason code is appended.
    """

    reason_codes: List[str] = []
    components: Dict[str, float] = {
        "R1_creator_dominance": 0.0,
        "R2_lp_starvation": 0.0,
        "R3_thin_sample": 0.0,
        "R4_fee_pace_anomaly": 0.0,
    }

    creator_share = float(features.creator_fee_share_5m)
    lp_share = float(features.lp_fee_share_5m)
    event_count = int(features.event_count_5m)
    fee_pace = float(features.fee_pace_5m_sol)
    event_pace = features.event_pace_5m

    # R1: creator dominance
    if creator_share >= R1_CREATOR_SHARE_HIGH:
        components["R1_creator_dominance"] = R1_CONTRIBUTION_HIGH
        reason_codes.append("CREATOR_FEE_SHARE_HIGH")
    elif creator_share >= R1_CREATOR_SHARE_ELEVATED:
        components["R1_creator_dominance"] = R1_CONTRIBUTION_ELEVATED
        reason_codes.append("CREATOR_FEE_SHARE_ELEVATED")

    # R2: LP share starvation, gated on co-occurring elevated creator share
    if lp_share < R2_LP_SHARE_LOW and creator_share >= R2_CREATOR_SHARE_GATE:
        components["R2_lp_starvation"] = R2_CONTRIBUTION
        reason_codes.append("LP_FEE_SHARE_LOW")

    # R3: thin sample
    if event_count < R3_EVENT_COUNT_MIN:
        components["R3_thin_sample"] = R3_CONTRIBUTION
        reason_codes.append("THIN_SAMPLE")

    # R4: fee pace anomaly -- only fires when both pace primitives are usable
    if event_pace is None:
        reason_codes.append("EVENT_PACE_UNAVAILABLE_FOR_R4")
    elif fee_pace < R4_FEE_PACE_LOW and float(event_pace) > R4_EVENT_PACE_HIGH:
        components["R4_fee_pace_anomaly"] = R4_CONTRIBUTION
        reason_codes.append("FEE_PACE_ANOMALOUS")

    raw_score = (
        components["R1_creator_dominance"]
        + components["R2_lp_starvation"]
        + components["R3_thin_sample"]
        + components["R4_fee_pace_anomaly"]
    )
    score = min(raw_score, 1.0)
    return score, reason_codes, components


def _score_to_label(score: float) -> FilterLabel:
    if score >= LABEL_THRESHOLD_SCAM_LIKELY:
        return FilterLabel.SCAM_LIKELY
    if score >= LABEL_THRESHOLD_SUSPICIOUS:
        return FilterLabel.SUSPICIOUS
    if score >= LABEL_THRESHOLD_ELEVATED:
        return FilterLabel.ELEVATED
    return FilterLabel.NORMAL


def _build_envelope(
    context: FilterContext,
    field_features: Optional[FieldFeatures],
) -> Dict[str, Any]:
    field_features_id = field_features.id if field_features is not None else None
    return {
        "filter_name": FILTER_NAME,
        "filter_version": FILTER_VERSION,
        "threshold_version": THRESHOLD_VERSION,
        "evaluated_at": context.as_of_time,
        "input_source_ids": {
            "alert_decision_id": context.alert_decision_id,
            "field_features_id": field_features_id,
        },
        "input_source_types": {
            "alert_decision_id": "alert_decisions.id",
            "field_features_id": "field_features.id",
        },
    }


def _build_payload(features: Optional[FieldFeatures]) -> Dict[str, Any]:
    """Full payload — every primitive, including Nones, for OK rows.

    Used on OK rows where ``event_pace_5m`` being None is informational
    (R4 simply does not fire) rather than a missing-input condition.
    The full shape preserves auditability of what the filter saw.
    """

    if features is None:
        return {}
    return {
        "creator_fee_share_5m": features.creator_fee_share_5m,
        "lp_fee_share_5m": features.lp_fee_share_5m,
        "protocol_fee_share_5m": features.protocol_fee_share_5m,
        "event_pace_5m": features.event_pace_5m,
        "fee_pace_5m_sol": features.fee_pace_5m_sol,
        "buy_sell_ratio_5m": features.buy_sell_ratio_5m,
        "event_count_5m": features.event_count_5m,
    }


def _build_partial_payload(features: Optional[FieldFeatures]) -> Dict[str, Any]:
    """Payload for MISSING rows: omit primitives whose values are None.

    Per spec Section 7.6: ``MISSING rows: payload contains only available
    primitives; missing names go in missing_reasons_json``. Filtering by
    None covers both required-primitive absence (the cause of the
    MISSING row) and incidental optional-primitive absence; the
    ``missing_reasons`` list on the row remains the authoritative record
    of which required inputs were unavailable.
    """

    if features is None:
        return {}
    return {
        name: value
        for name, value in _build_payload(features).items()
        if value is not None
    }


def _label_thresholds_snapshot() -> Dict[str, float]:
    return {
        "SCAM_LIKELY": LABEL_THRESHOLD_SCAM_LIKELY,
        "SUSPICIOUS": LABEL_THRESHOLD_SUSPICIOUS,
        "ELEVATED": LABEL_THRESHOLD_ELEVATED,
        "NORMAL": 0.0,
    }


def _build_missing_result(
    context: FilterContext,
    missing_names: List[str],
) -> FilterResult:
    """Produce a MISSING-status row when required primitives are unavailable."""

    return FilterResult(
        token_address=context.token_address,
        filter_name=FILTER_NAME,
        as_of_time=context.as_of_time,
        filter_version=FILTER_VERSION,
        threshold_version=THRESHOLD_VERSION,
        label=FilterLabel.UNKNOWN,
        score=None,
        would_block=False,
        policy_action="observe",
        reason=None,
        input_snapshot={
            "envelope": _build_envelope(context, context.field_features),
            "payload": _build_partial_payload(context.field_features),
        },
        output_reason=None,
        data_status=DataStatus.MISSING,
        missing_reasons=list(missing_names),
        alert_decision_id=context.alert_decision_id,
    )


class FeeGateFilter(Filter):
    """PHX2-native, reduced-fidelity Fee Gate. See module docstring."""

    @property
    def name(self) -> str:
        return FILTER_NAME

    @property
    def filter_version(self) -> str:
        return FILTER_VERSION

    @property
    def threshold_version(self) -> str:
        return THRESHOLD_VERSION

    @property
    def known_limitations(self) -> List[str]:
        return list(KNOWN_LIMITATIONS)

    def evaluate(self, context: FilterContext) -> FilterResult:
        features = context.field_features
        if features is None:
            return _build_missing_result(
                context, list(REQUIRED_PRIMITIVE_NAMES)
            )

        missing_names = [
            name
            for name in REQUIRED_PRIMITIVE_NAMES
            if getattr(features, name) is None
        ]
        if missing_names:
            return _build_missing_result(context, missing_names)

        score, reason_codes, components = _compute_score_and_reasons(features)
        label = _score_to_label(score)
        would_block = label == FilterLabel.SCAM_LIKELY
        policy_action = "block" if would_block else "observe"
        fired_rules = [
            rule_key
            for rule_key, contribution in components.items()
            if contribution > 0.0
        ]
        fired_summary = (
            "+".join(key.split("_", 1)[0] for key in fired_rules)
            if fired_rules
            else "no_rules"
        )
        reason = (
            f"fee_gate_v1: {label.value} "
            f"(score={score:.2f}, {fired_summary} fired)"
        )

        return FilterResult(
            token_address=context.token_address,
            filter_name=FILTER_NAME,
            as_of_time=context.as_of_time,
            filter_version=FILTER_VERSION,
            threshold_version=THRESHOLD_VERSION,
            label=label,
            score=score,
            would_block=would_block,
            policy_action=policy_action,
            reason=reason,
            input_snapshot={
                "envelope": _build_envelope(context, features),
                "payload": _build_payload(features),
            },
            output_reason={
                "score_components": components,
                "raw_score": score,
                "normalized_score": score,
                "label_thresholds": _label_thresholds_snapshot(),
                "reason_codes": reason_codes,
                "known_limitations": list(KNOWN_LIMITATIONS),
            },
            data_status=DataStatus.OK,
            missing_reasons=[],
            alert_decision_id=context.alert_decision_id,
        )

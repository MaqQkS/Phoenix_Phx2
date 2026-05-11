"""Layer 1 unit tests for FeeGateFilter.

These tests construct FilterContext instances directly and call
FeeGateFilter().evaluate(...) without touching the DB or the engine.
The threshold constants come from PHX2.filters.fee_gate so the tests
remain valid if/when calibrated values replace the placeholders.
"""

from datetime import datetime, timezone

from PHX2.filters.base import FilterContext
from PHX2.filters.fee_gate import (
    FILTER_NAME,
    FILTER_VERSION,
    KNOWN_LIMITATIONS,
    LABEL_THRESHOLD_ELEVATED,
    LABEL_THRESHOLD_SCAM_LIKELY,
    LABEL_THRESHOLD_SUSPICIOUS,
    R1_CONTRIBUTION_ELEVATED,
    R1_CONTRIBUTION_HIGH,
    R1_CREATOR_SHARE_ELEVATED,
    R1_CREATOR_SHARE_HIGH,
    R2_CONTRIBUTION,
    R2_CREATOR_SHARE_GATE,
    R2_LP_SHARE_LOW,
    R3_CONTRIBUTION,
    R3_EVENT_COUNT_MIN,
    R4_CONTRIBUTION,
    R4_EVENT_PACE_HIGH,
    R4_FEE_PACE_LOW,
    THRESHOLD_VERSION,
    FeeGateFilter,
)
from PHX2.models import (
    AlertDecision,
    DataStatus,
    DecisionType,
    FieldFeatures,
    FilterLabel,
)


TOKEN = "tok-fee-gate"
EVAL_TIME = datetime(2026, 5, 10, 14, 30, tzinfo=timezone.utc)


def _decision() -> AlertDecision:
    return AlertDecision(
        token_address=TOKEN,
        evaluated_at=EVAL_TIME,
        decision_type=DecisionType.WOULD_ALERT,
    )


def _features(**overrides) -> FieldFeatures:
    """Construct a FieldFeatures with all four required primitives valid
    and benign defaults that produce a NORMAL row when no overrides are
    applied. Override individual fields to fire specific rules.
    """

    base = dict(
        token_address=TOKEN,
        as_of_time=EVAL_TIME,
        creator_fee_share_5m=0.10,
        lp_fee_share_5m=0.80,
        protocol_fee_share_5m=0.10,
        buy_sell_ratio_5m=1.0,
        event_pace_5m=1.0,
        fee_pace_5m_sol=0.05,
        event_count_5m=R3_EVENT_COUNT_MIN + 10,
        data_status=DataStatus.OK,
    )
    base.update(overrides)
    return FieldFeatures(**base)


def _context(features) -> FilterContext:
    return FilterContext(
        alert_decision_id=42,
        token_address=TOKEN,
        as_of_time=EVAL_TIME,
        alert_decision=_decision(),
        field_features=features,
    )


def _evaluate(features) -> object:
    return FeeGateFilter().evaluate(_context(features))


# ----------------------------------------------------------------------
# T1.1 -- Rule contribution boundary tests
# ----------------------------------------------------------------------


def test_t1_1_r1_high_band_fires_high_contribution():
    result = _evaluate(_features(creator_fee_share_5m=R1_CREATOR_SHARE_HIGH))
    assert result.data_status == DataStatus.OK
    assert result.output_reason["score_components"]["R1_creator_dominance"] == (
        R1_CONTRIBUTION_HIGH
    )
    assert "CREATOR_FEE_SHARE_HIGH" in result.output_reason["reason_codes"]


def test_t1_1_r1_elevated_band_fires_elevated_contribution():
    # Just below the HIGH boundary, above the ELEVATED boundary.
    result = _evaluate(
        _features(creator_fee_share_5m=R1_CREATOR_SHARE_HIGH - 0.001)
    )
    assert result.output_reason["score_components"]["R1_creator_dominance"] == (
        R1_CONTRIBUTION_ELEVATED
    )
    assert "CREATOR_FEE_SHARE_ELEVATED" in result.output_reason["reason_codes"]


def test_t1_1_r1_below_elevated_does_not_fire():
    result = _evaluate(
        _features(creator_fee_share_5m=R1_CREATOR_SHARE_ELEVATED - 0.001)
    )
    assert result.output_reason["score_components"]["R1_creator_dominance"] == 0.0
    assert "CREATOR_FEE_SHARE_HIGH" not in result.output_reason["reason_codes"]
    assert "CREATOR_FEE_SHARE_ELEVATED" not in result.output_reason["reason_codes"]


def test_t1_1_r2_fires_when_lp_low_and_creator_at_gate():
    result = _evaluate(
        _features(
            lp_fee_share_5m=R2_LP_SHARE_LOW - 0.001,
            creator_fee_share_5m=R2_CREATOR_SHARE_GATE,
        )
    )
    assert result.output_reason["score_components"]["R2_lp_starvation"] == (
        R2_CONTRIBUTION
    )
    assert "LP_FEE_SHARE_LOW" in result.output_reason["reason_codes"]


def test_t1_1_r2_does_not_fire_when_creator_below_gate():
    result = _evaluate(
        _features(
            lp_fee_share_5m=0.0,
            creator_fee_share_5m=R2_CREATOR_SHARE_GATE - 0.001,
        )
    )
    assert result.output_reason["score_components"]["R2_lp_starvation"] == 0.0
    assert "LP_FEE_SHARE_LOW" not in result.output_reason["reason_codes"]


def test_t1_1_r3_fires_when_event_count_below_min():
    result = _evaluate(_features(event_count_5m=R3_EVENT_COUNT_MIN - 1))
    assert result.output_reason["score_components"]["R3_thin_sample"] == R3_CONTRIBUTION
    assert "THIN_SAMPLE" in result.output_reason["reason_codes"]


def test_t1_1_r3_does_not_fire_at_min_threshold():
    result = _evaluate(_features(event_count_5m=R3_EVENT_COUNT_MIN))
    assert result.output_reason["score_components"]["R3_thin_sample"] == 0.0
    assert "THIN_SAMPLE" not in result.output_reason["reason_codes"]


def test_t1_1_r4_fires_when_fee_pace_low_and_event_pace_high():
    result = _evaluate(
        _features(
            fee_pace_5m_sol=R4_FEE_PACE_LOW - 0.001,
            event_pace_5m=R4_EVENT_PACE_HIGH + 0.001,
        )
    )
    assert result.output_reason["score_components"]["R4_fee_pace_anomaly"] == (
        R4_CONTRIBUTION
    )
    assert "FEE_PACE_ANOMALOUS" in result.output_reason["reason_codes"]


# ----------------------------------------------------------------------
# T1.2 -- Score-to-label band boundary tests
# ----------------------------------------------------------------------


def test_t1_2_label_normal_at_zero_score():
    result = _evaluate(_features())
    assert result.score == 0.0
    assert result.label == FilterLabel.NORMAL


def test_t1_2_label_elevated_at_elevated_threshold():
    # R1 elevated contribution lands above the ELEVATED threshold.
    result = _evaluate(
        _features(creator_fee_share_5m=R1_CREATOR_SHARE_ELEVATED)
    )
    assert result.score >= LABEL_THRESHOLD_ELEVATED
    assert result.score < LABEL_THRESHOLD_SUSPICIOUS
    assert result.label == FilterLabel.ELEVATED


def test_t1_2_label_suspicious_at_suspicious_threshold():
    # R1 high contribution alone (0.40) lands at SUSPICIOUS threshold.
    result = _evaluate(_features(creator_fee_share_5m=R1_CREATOR_SHARE_HIGH))
    assert result.score >= LABEL_THRESHOLD_SUSPICIOUS
    assert result.score < LABEL_THRESHOLD_SCAM_LIKELY
    assert result.label == FilterLabel.SUSPICIOUS


def test_t1_2_label_scam_likely_at_scam_threshold():
    # R1 high + R2 + R3 + R4 sums to 0.85, well above SCAM_LIKELY.
    result = _evaluate(
        _features(
            creator_fee_share_5m=R1_CREATOR_SHARE_HIGH,
            lp_fee_share_5m=R2_LP_SHARE_LOW - 0.001,
            event_count_5m=R3_EVENT_COUNT_MIN - 1,
            fee_pace_5m_sol=R4_FEE_PACE_LOW - 0.001,
            event_pace_5m=R4_EVENT_PACE_HIGH + 0.001,
        )
    )
    assert result.score >= LABEL_THRESHOLD_SCAM_LIKELY
    assert result.label == FilterLabel.SCAM_LIKELY


# ----------------------------------------------------------------------
# T1.3 -- Combined-rule tests
# ----------------------------------------------------------------------


def test_t1_3_r1_high_plus_r2_fires_both_components():
    result = _evaluate(
        _features(
            creator_fee_share_5m=R1_CREATOR_SHARE_HIGH,
            lp_fee_share_5m=R2_LP_SHARE_LOW - 0.001,
        )
    )
    components = result.output_reason["score_components"]
    assert components["R1_creator_dominance"] == R1_CONTRIBUTION_HIGH
    assert components["R2_lp_starvation"] == R2_CONTRIBUTION
    assert "CREATOR_FEE_SHARE_HIGH" in result.output_reason["reason_codes"]
    assert "LP_FEE_SHARE_LOW" in result.output_reason["reason_codes"]


def test_t1_3_score_clamped_to_one():
    # Force all four rules to fire and verify clamp.
    result = _evaluate(
        _features(
            creator_fee_share_5m=R1_CREATOR_SHARE_HIGH,
            lp_fee_share_5m=R2_LP_SHARE_LOW - 0.001,
            event_count_5m=R3_EVENT_COUNT_MIN - 1,
            fee_pace_5m_sol=R4_FEE_PACE_LOW - 0.001,
            event_pace_5m=R4_EVENT_PACE_HIGH + 0.001,
        )
    )
    assert result.score <= 1.0


# ----------------------------------------------------------------------
# T1.4 -- Missing-input tests
# ----------------------------------------------------------------------


def test_t1_4_missing_creator_fee_share_yields_missing_row():
    result = _evaluate(_features(creator_fee_share_5m=None))
    assert result.data_status == DataStatus.MISSING
    assert "creator_fee_share_5m" in result.missing_reasons
    assert result.score is None
    assert result.label == FilterLabel.UNKNOWN
    assert result.output_reason is None
    assert result.reason is None


def test_t1_4_missing_lp_fee_share_yields_missing_row():
    result = _evaluate(_features(lp_fee_share_5m=None))
    assert result.data_status == DataStatus.MISSING
    assert "lp_fee_share_5m" in result.missing_reasons


def test_t1_4_missing_event_count_yields_missing_row():
    result = _evaluate(_features(event_count_5m=None))
    assert result.data_status == DataStatus.MISSING
    assert "event_count_5m" in result.missing_reasons


def test_t1_4_missing_fee_pace_yields_missing_row():
    result = _evaluate(_features(fee_pace_5m_sol=None))
    assert result.data_status == DataStatus.MISSING
    assert "fee_pace_5m_sol" in result.missing_reasons


def test_t1_4_missing_event_pace_alone_yields_ok_row_with_r4_silent():
    result = _evaluate(_features(event_pace_5m=None))
    assert result.data_status == DataStatus.OK
    assert result.output_reason["score_components"]["R4_fee_pace_anomaly"] == 0.0
    assert "EVENT_PACE_UNAVAILABLE_FOR_R4" in result.output_reason["reason_codes"]
    assert "FEE_PACE_ANOMALOUS" not in result.output_reason["reason_codes"]


def test_t1_4_field_features_none_yields_missing_with_all_primitive_names():
    context = FilterContext(
        alert_decision_id=42,
        token_address=TOKEN,
        as_of_time=EVAL_TIME,
        alert_decision=_decision(),
        field_features=None,
    )
    result = FeeGateFilter().evaluate(context)
    assert result.data_status == DataStatus.MISSING
    for name in (
        "creator_fee_share_5m",
        "lp_fee_share_5m",
        "event_count_5m",
        "fee_pace_5m_sol",
    ):
        assert name in result.missing_reasons


# ----------------------------------------------------------------------
# T1.5 -- Reason code presence per fired rule
# ----------------------------------------------------------------------


def test_t1_5_only_fired_rules_appear_in_reason_codes():
    result = _evaluate(
        _features(creator_fee_share_5m=R1_CREATOR_SHARE_HIGH)
    )
    codes = result.output_reason["reason_codes"]
    assert "CREATOR_FEE_SHARE_HIGH" in codes
    assert "LP_FEE_SHARE_LOW" not in codes
    assert "THIN_SAMPLE" not in codes
    assert "FEE_PACE_ANOMALOUS" not in codes


# ----------------------------------------------------------------------
# T1.6 -- would_block and policy_action correctness
# ----------------------------------------------------------------------


def test_t1_6_would_block_only_when_scam_likely():
    normal = _evaluate(_features())
    assert normal.would_block is False
    assert normal.policy_action == "observe"

    elevated = _evaluate(_features(creator_fee_share_5m=R1_CREATOR_SHARE_ELEVATED))
    assert elevated.label == FilterLabel.ELEVATED
    assert elevated.would_block is False
    assert elevated.policy_action == "observe"

    scam = _evaluate(
        _features(
            creator_fee_share_5m=R1_CREATOR_SHARE_HIGH,
            lp_fee_share_5m=R2_LP_SHARE_LOW - 0.001,
            event_count_5m=R3_EVENT_COUNT_MIN - 1,
            fee_pace_5m_sol=R4_FEE_PACE_LOW - 0.001,
            event_pace_5m=R4_EVENT_PACE_HIGH + 0.001,
        )
    )
    assert scam.label == FilterLabel.SCAM_LIKELY
    assert scam.would_block is True
    assert scam.policy_action == "block"


# ----------------------------------------------------------------------
# T1.7 -- known_limitations present on every OK result
# ----------------------------------------------------------------------


def test_t1_7_known_limitations_present_on_ok_rows():
    result = _evaluate(_features())
    assert result.output_reason["known_limitations"] == list(KNOWN_LIMITATIONS)


def test_t1_7_filter_identity_metadata_is_stable():
    f = FeeGateFilter()
    assert f.name == FILTER_NAME
    assert f.filter_version == FILTER_VERSION
    assert f.threshold_version == THRESHOLD_VERSION
    assert f.known_limitations == list(KNOWN_LIMITATIONS)

"""Stage 13 recommendation-builder unit tests.

Exercises the builder's contract against synthetic CSV bundles:
classification correctness, per-tier override semantics, severity
gating, scam-adjacent priority, confidence ceiling, baseline-zero
anomaly behavior, and empty-input safety.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from PHX2.stage13.builder import (
    _classify_single_row,
    _optional_float,
    _required_int,
    build_recommendations,
    resolve_baseline_rate,
)
from PHX2.stage13.loader import Stage13ValidationError, load_stage12_csvs
from PHX2.stage13.types import EvidenceThresholds
from PHX2.tests.fixtures.stage13.stage12_fixture_writer import (
    BaselineRow,
    FilterByTierRow,
    FilterOverallRow,
    PrimitiveBucketRow,
    write_stage12_run,
)


_T = EvidenceThresholds()


def _find(rows, *, cohort_id: str, tier_scope: str):
    for r in rows:
        if r.cohort_id == cohort_id and r.tier_scope == tier_scope:
            return r
    raise AssertionError(
        f"row not found: cohort_id={cohort_id!r} tier_scope={tier_scope!r}; "
        f"have {[(r.cohort_id, r.tier_scope) for r in rows]}"
    )


def _baseline_rows():
    # Three tiers with baseline_rate 0.20.
    return [
        BaselineRow(
            tier_index=1, tier_name="T1", n_complete=200,
            hit_2x_24h_count=40, hit_2x_24h_rate=0.20,
            hit_2x_24h_ci_low=0.15, hit_2x_24h_ci_high=0.26,
        ),
        BaselineRow(
            tier_index=2, tier_name="T2", n_complete=150,
            hit_2x_24h_count=30, hit_2x_24h_rate=0.20,
            hit_2x_24h_ci_low=0.14, hit_2x_24h_ci_high=0.27,
        ),
        BaselineRow(
            tier_index=3, tier_name="T3", n_complete=100,
            hit_2x_24h_count=20, hit_2x_24h_rate=0.20,
            hit_2x_24h_ci_low=0.13, hit_2x_24h_ci_high=0.28,
        ),
    ]


def test_per_tier_advance_when_strong_lift_tighten(tmp_path: Path) -> None:
    run = write_stage12_run(
        tmp_path / "run",
        baseline_rows=_baseline_rows(),
        filter_overall_rows=[],
        filter_by_tier_rows=[
            FilterByTierRow(
                tier_index=1, tier_name="T1", filter_label="scam_likely",
                n_complete=100, n_censored=5,
                hit_2x_24h_count=5, hit_2x_24h_rate=0.05,
                hit_2x_24h_ci_low=0.02, hit_2x_24h_ci_high=0.10,
                confidence_flag="standard",
            ),
        ],
    )
    bundle = load_stage12_csvs(run)
    rows = build_recommendations(bundle, _T)
    row = _find(rows, cohort_id="fee_gate_v1@v1[threshold=v1]:scam_likely", tier_scope="T1")
    assert row.action_class == "ADVANCE_AS_CANDIDATE"
    assert row.direction == "tighten"
    assert row.evidence_class == "strong"
    # scam-adjacent label -> urgent priority even without severity.
    assert row.review_priority == "urgent"


def test_loosen_strong_finding_never_advances(tmp_path: Path) -> None:
    run = write_stage12_run(
        tmp_path / "run",
        baseline_rows=_baseline_rows(),
        filter_overall_rows=[],
        filter_by_tier_rows=[
            FilterByTierRow(
                tier_index=1, tier_name="T1", filter_label="big_pump",
                n_complete=100, n_censored=5,
                hit_2x_24h_count=40, hit_2x_24h_rate=0.40,
                hit_2x_24h_ci_low=0.30, hit_2x_24h_ci_high=0.50,
                confidence_flag="standard",
            ),
        ],
    )
    bundle = load_stage12_csvs(run)
    rows = build_recommendations(bundle, _T)
    row = _find(rows, cohort_id="fee_gate_v1@v1[threshold=v1]:big_pump", tier_scope="T1")
    assert row.direction == "loosen"
    assert row.action_class == "HOLD_OBSERVE_ONLY"
    assert row.loosen_capped_flag is True


def test_overall_advance_supported_by_at_least_one_tier(tmp_path: Path) -> None:
    run = write_stage12_run(
        tmp_path / "run",
        baseline_rows=_baseline_rows(),
        filter_overall_rows=[
            FilterOverallRow(
                filter_label="scam_likely",
                n_complete=250, n_censored=15,
                hit_2x_24h_count=10, hit_2x_24h_rate=0.04,
                hit_2x_24h_ci_low=0.02, hit_2x_24h_ci_high=0.07,
                confidence_flag="standard",
            ),
        ],
        filter_by_tier_rows=[
            FilterByTierRow(
                tier_index=1, tier_name="T1", filter_label="scam_likely",
                n_complete=100, hit_2x_24h_count=4, hit_2x_24h_rate=0.04,
                hit_2x_24h_ci_low=0.01, hit_2x_24h_ci_high=0.10,
            ),
            FilterByTierRow(
                tier_index=2, tier_name="T2", filter_label="scam_likely",
                n_complete=80, hit_2x_24h_count=4, hit_2x_24h_rate=0.05,
                hit_2x_24h_ci_low=0.02, hit_2x_24h_ci_high=0.12,
            ),
        ],
    )
    bundle = load_stage12_csvs(run)
    rows = build_recommendations(bundle, _T)
    cohort_id = "fee_gate_v1@v1[threshold=v1]:scam_likely"
    overall = _find(rows, cohort_id=cohort_id, tier_scope="overall")
    # Overall should keep ADVANCE because T1's per-tier row is also ADVANCE.
    assert overall.action_class == "ADVANCE_AS_CANDIDATE"
    assert "T1" in overall.tier_evidence_support
    assert overall.review_priority == "urgent"  # scam-adjacent


def test_overall_advance_with_no_tier_support_downgraded_to_hold(tmp_path: Path) -> None:
    run = write_stage12_run(
        tmp_path / "run",
        baseline_rows=_baseline_rows(),
        filter_overall_rows=[
            FilterOverallRow(
                filter_label="some_label",
                n_complete=200, n_censored=10,
                hit_2x_24h_count=10, hit_2x_24h_rate=0.05,
                hit_2x_24h_ci_low=0.02, hit_2x_24h_ci_high=0.09,
                confidence_flag="standard",
            ),
        ],
        filter_by_tier_rows=[
            FilterByTierRow(
                tier_index=1, tier_name="T1", filter_label="some_label",
                n_complete=80, hit_2x_24h_count=12, hit_2x_24h_rate=0.15,
                hit_2x_24h_ci_low=0.08, hit_2x_24h_ci_high=0.24,
            ),
        ],
    )
    bundle = load_stage12_csvs(run)
    rows = build_recommendations(bundle, _T)
    cohort_id = "fee_gate_v1@v1[threshold=v1]:some_label"
    overall = _find(rows, cohort_id=cohort_id, tier_scope="overall")
    assert overall.action_class == "HOLD_OBSERVE_ONLY"
    assert any("no matching per-tier advance" in n for n in overall.notes)


def test_overall_with_all_tiers_no_signal_becomes_anomaly(tmp_path: Path) -> None:
    run = write_stage12_run(
        tmp_path / "run",
        baseline_rows=_baseline_rows(),
        filter_overall_rows=[
            FilterOverallRow(
                filter_label="some_label",
                n_complete=300, n_censored=20,
                hit_2x_24h_count=30, hit_2x_24h_rate=0.10,
                hit_2x_24h_ci_low=0.06, hit_2x_24h_ci_high=0.15,
                confidence_flag="standard",
            ),
        ],
        filter_by_tier_rows=[
            FilterByTierRow(
                tier_index=1, tier_name="T1", filter_label="some_label",
                n_complete=100, hit_2x_24h_count=22, hit_2x_24h_rate=0.22,
                hit_2x_24h_ci_low=0.14, hit_2x_24h_ci_high=0.31,
            ),
            FilterByTierRow(
                tier_index=2, tier_name="T2", filter_label="some_label",
                n_complete=80, hit_2x_24h_count=18, hit_2x_24h_rate=0.225,
                hit_2x_24h_ci_low=0.14, hit_2x_24h_ci_high=0.33,
            ),
        ],
    )
    bundle = load_stage12_csvs(run)
    rows = build_recommendations(bundle, _T)
    cohort_id = "fee_gate_v1@v1[threshold=v1]:some_label"
    overall = _find(rows, cohort_id=cohort_id, tier_scope="overall")
    # The overall row standalone would be ADVANCE_AS_CANDIDATE (tighten,
    # strong) but every per-tier row is NO_SIGNAL_FOUND (|lift| < 0.05).
    # Pooling-artifact path -> ANOMALY_FLAG.
    assert overall.action_class == "ANOMALY_FLAG"
    assert any("pooling artifact" in n for n in overall.notes)


def test_overall_direction_disagreement_promotes_to_anomaly(tmp_path: Path) -> None:
    run = write_stage12_run(
        tmp_path / "run",
        baseline_rows=_baseline_rows(),
        filter_overall_rows=[
            FilterOverallRow(
                filter_label="some_label",
                n_complete=200,
                hit_2x_24h_count=10, hit_2x_24h_rate=0.05,
                hit_2x_24h_ci_low=0.03, hit_2x_24h_ci_high=0.08,
            ),
        ],
        filter_by_tier_rows=[
            FilterByTierRow(
                tier_index=1, tier_name="T1", filter_label="some_label",
                n_complete=80, hit_2x_24h_count=4, hit_2x_24h_rate=0.05,
                hit_2x_24h_ci_low=0.02, hit_2x_24h_ci_high=0.12,
            ),
            # T2: opposite direction (loosen). Although it's HOLD per
            # the cap, the direction signal is "loosen".
            FilterByTierRow(
                tier_index=2, tier_name="T2", filter_label="some_label",
                n_complete=60, hit_2x_24h_count=30, hit_2x_24h_rate=0.50,
                hit_2x_24h_ci_low=0.37, hit_2x_24h_ci_high=0.62,
            ),
        ],
    )
    bundle = load_stage12_csvs(run)
    rows = build_recommendations(bundle, _T)
    cohort_id = "fee_gate_v1@v1[threshold=v1]:some_label"
    overall = _find(rows, cohort_id=cohort_id, tier_scope="overall")
    assert overall.action_class == "ANOMALY_FLAG"
    assert overall.cross_tier_disagreement is True


def test_low_confidence_at_insufficient_n_flags_ceiling(tmp_path: Path) -> None:
    run = write_stage12_run(
        tmp_path / "run",
        baseline_rows=_baseline_rows(),
        filter_overall_rows=[],
        filter_by_tier_rows=[
            FilterByTierRow(
                tier_index=1, tier_name="T1", filter_label="scam_likely",
                n_complete=8, hit_2x_24h_count=1, hit_2x_24h_rate=0.125,
                hit_2x_24h_ci_low=0.02, hit_2x_24h_ci_high=0.45,
                confidence_flag="low_confidence",
            ),
        ],
    )
    bundle = load_stage12_csvs(run)
    rows = build_recommendations(bundle, _T)
    row = _find(rows, cohort_id="fee_gate_v1@v1[threshold=v1]:scam_likely", tier_scope="T1")
    # n_complete < 10 -> INSUFFICIENT_EVIDENCE; the ceiling still
    # flags as applied (informational) but evidence stays insufficient
    # since the band gate is dominant.
    assert row.action_class == "INSUFFICIENT_EVIDENCE"
    assert row.confidence_ceiling_applied is True


def test_low_confidence_caps_strong_at_moderate_when_n_qualifies(tmp_path: Path) -> None:
    # The low_confidence flag in Stage 12 maps to n < 10 by Stage 12's
    # own boundary. To exercise the L13 ceiling when n is high enough
    # to otherwise qualify as "strong", we inject the flag manually
    # via the fixture builder. This is a stress test of L13's logical
    # independence from the n-band.
    run = write_stage12_run(
        tmp_path / "run",
        baseline_rows=_baseline_rows(),
        filter_overall_rows=[],
        filter_by_tier_rows=[
            FilterByTierRow(
                tier_index=1, tier_name="T1", filter_label="scam_likely",
                n_complete=100, hit_2x_24h_count=5, hit_2x_24h_rate=0.05,
                hit_2x_24h_ci_low=0.02, hit_2x_24h_ci_high=0.10,
                confidence_flag="low_confidence",
            ),
        ],
    )
    bundle = load_stage12_csvs(run)
    rows = build_recommendations(bundle, _T)
    row = _find(rows, cohort_id="fee_gate_v1@v1[threshold=v1]:scam_likely", tier_scope="T1")
    assert row.evidence_class == "moderate"
    assert row.action_class == "HOLD_OBSERVE_ONLY"
    assert row.confidence_ceiling_applied is True


def test_no_signal_when_lift_below_floor(tmp_path: Path) -> None:
    run = write_stage12_run(
        tmp_path / "run",
        baseline_rows=_baseline_rows(),
        filter_overall_rows=[],
        filter_by_tier_rows=[
            FilterByTierRow(
                tier_index=1, tier_name="T1", filter_label="scam_likely",
                n_complete=80, hit_2x_24h_count=17, hit_2x_24h_rate=0.21,
                hit_2x_24h_ci_low=0.12, hit_2x_24h_ci_high=0.31,
            ),
        ],
    )
    bundle = load_stage12_csvs(run)
    rows = build_recommendations(bundle, _T)
    row = _find(rows, cohort_id="fee_gate_v1@v1[threshold=v1]:scam_likely", tier_scope="T1")
    # |lift| < 0.05 and n_complete >= 10 -> NO_SIGNAL_FOUND.
    assert row.action_class == "NO_SIGNAL_FOUND"
    assert row.direction in ("tighten", "loosen", "none")


def test_insufficient_evidence_when_n_below_floor(tmp_path: Path) -> None:
    run = write_stage12_run(
        tmp_path / "run",
        baseline_rows=_baseline_rows(),
        filter_overall_rows=[],
        filter_by_tier_rows=[
            FilterByTierRow(
                tier_index=1, tier_name="T1", filter_label="scam_likely",
                n_complete=5, hit_2x_24h_count=1, hit_2x_24h_rate=0.20,
                hit_2x_24h_ci_low=0.04, hit_2x_24h_ci_high=0.62,
                confidence_flag="low_confidence",
            ),
        ],
    )
    bundle = load_stage12_csvs(run)
    rows = build_recommendations(bundle, _T)
    row = _find(rows, cohort_id="fee_gate_v1@v1[threshold=v1]:scam_likely", tier_scope="T1")
    assert row.action_class == "INSUFFICIENT_EVIDENCE"
    assert row.evidence_class == "insufficient"


def test_baseline_zero_row_emits_anomaly_with_note(tmp_path: Path) -> None:
    # Construct an all-tiers-zero baseline so the lookup for T1 returns 0.
    run = write_stage12_run(
        tmp_path / "run",
        baseline_rows=[
            BaselineRow(
                tier_index=1, tier_name="T1", n_complete=100,
                hit_2x_24h_count=0, hit_2x_24h_rate=0.0,
                hit_2x_24h_ci_low=0.0, hit_2x_24h_ci_high=0.04,
            ),
        ],
        filter_overall_rows=[],
        filter_by_tier_rows=[
            FilterByTierRow(
                tier_index=1, tier_name="T1", filter_label="scam_likely",
                n_complete=60, hit_2x_24h_count=10, hit_2x_24h_rate=0.166,
                hit_2x_24h_ci_low=0.09, hit_2x_24h_ci_high=0.27,
            ),
        ],
    )
    bundle = load_stage12_csvs(run)
    rows = build_recommendations(bundle, _T)
    row = _find(rows, cohort_id="fee_gate_v1@v1[threshold=v1]:scam_likely", tier_scope="T1")
    assert row.action_class == "ANOMALY_FLAG"
    assert row.direction == "none"
    assert row.lift_relative is None
    assert "baseline_rate_zero" in row.notes


def test_severity_unknown_when_no_share_column(tmp_path: Path) -> None:
    run = write_stage12_run(
        tmp_path / "run",
        baseline_rows=_baseline_rows(),
        filter_overall_rows=[],
        filter_by_tier_rows=[
            FilterByTierRow(
                tier_index=1, tier_name="T1", filter_label="scam_likely",
                n_complete=100, hit_2x_24h_count=5, hit_2x_24h_rate=0.05,
                hit_2x_24h_ci_low=0.02, hit_2x_24h_ci_high=0.10,
            ),
        ],
    )
    bundle = load_stage12_csvs(run)
    rows = build_recommendations(bundle, _T)
    row = _find(rows, cohort_id="fee_gate_v1@v1[threshold=v1]:scam_likely", tier_scope="T1")
    assert row.policy_severity == "unknown"


def test_severity_high_when_share_exceeds_threshold(tmp_path: Path) -> None:
    run = write_stage12_run(
        tmp_path / "run",
        baseline_rows=_baseline_rows(),
        filter_overall_rows=[],
        filter_by_tier_rows=[
            FilterByTierRow(
                tier_index=1, tier_name="T1", filter_label="scam_likely",
                n_complete=100, hit_2x_24h_count=5, hit_2x_24h_rate=0.05,
                hit_2x_24h_ci_low=0.02, hit_2x_24h_ci_high=0.10,
                extra_columns={"decision_share": 0.45},
            ),
        ],
        extra_columns=("decision_share",),
    )
    bundle = load_stage12_csvs(run)
    rows = build_recommendations(bundle, _T)
    row = _find(rows, cohort_id="fee_gate_v1@v1[threshold=v1]:scam_likely", tier_scope="T1")
    assert row.policy_severity == "high"


def test_primitive_bucket_classified(tmp_path: Path) -> None:
    run = write_stage12_run(
        tmp_path / "run",
        baseline_rows=_baseline_rows(),
        filter_overall_rows=[],
        filter_by_tier_rows=[],
        primitive_bucket_rows=[
            PrimitiveBucketRow(
                tier_index=1, tier_name="T1",
                primitive_name="buy_pressure_5m", bucket_label="Q1",
                n_complete=60, hit_2x_24h_count=3, hit_2x_24h_rate=0.05,
                hit_2x_24h_ci_low=0.02, hit_2x_24h_ci_high=0.10,
            ),
        ],
    )
    bundle = load_stage12_csvs(run)
    rows = build_recommendations(bundle, _T)
    row = _find(rows, cohort_id="buy_pressure_5m:Q1", tier_scope="T1")
    assert row.policy_surface == "primitive_bucket_cohort"
    assert row.action_class in (
        "ADVANCE_AS_CANDIDATE", "HOLD_OBSERVE_ONLY",
        "NO_SIGNAL_FOUND",
    )


def test_empty_inputs_produce_empty_row_list(tmp_path: Path) -> None:
    run = write_stage12_run(
        tmp_path / "run",
        baseline_rows=[],
        filter_overall_rows=[],
        filter_by_tier_rows=[],
        primitive_bucket_rows=[],
    )
    bundle = load_stage12_csvs(run)
    rows = build_recommendations(bundle, _T)
    assert rows == []


# ---------------------------------------------------------------------------
# F1 audit remediation: n-band dominance over anomaly overrides.
# n_complete < 10 must remain INSUFFICIENT_EVIDENCE / insufficient even
# when cohort_rate is 0.0/1.0 or baseline_rate is 0.0.
# ---------------------------------------------------------------------------


def test_low_n_with_cohort_rate_zero_stays_insufficient_evidence(tmp_path: Path) -> None:
    run = write_stage12_run(
        tmp_path / "run",
        baseline_rows=_baseline_rows(),
        filter_overall_rows=[],
        filter_by_tier_rows=[
            FilterByTierRow(
                tier_index=1, tier_name="T1", filter_label="scam_likely",
                n_complete=5, hit_2x_24h_count=0, hit_2x_24h_rate=0.0,
                hit_2x_24h_ci_low=0.0, hit_2x_24h_ci_high=0.50,
            ),
        ],
    )
    bundle = load_stage12_csvs(run)
    rows = build_recommendations(bundle, _T)
    row = _find(
        rows,
        cohort_id="fee_gate_v1@v1[threshold=v1]:scam_likely",
        tier_scope="T1",
    )
    assert row.action_class == "INSUFFICIENT_EVIDENCE"
    assert row.evidence_class == "insufficient"
    # Anomaly observation is still recorded as a note for transparency.
    assert any("cohort_rate_extreme:0.0" in n for n in row.notes)


def test_low_n_with_cohort_rate_one_stays_insufficient_evidence(tmp_path: Path) -> None:
    run = write_stage12_run(
        tmp_path / "run",
        baseline_rows=_baseline_rows(),
        filter_overall_rows=[],
        filter_by_tier_rows=[
            FilterByTierRow(
                tier_index=1, tier_name="T1", filter_label="scam_likely",
                n_complete=6, hit_2x_24h_count=6, hit_2x_24h_rate=1.0,
                hit_2x_24h_ci_low=0.55, hit_2x_24h_ci_high=1.0,
            ),
        ],
    )
    bundle = load_stage12_csvs(run)
    rows = build_recommendations(bundle, _T)
    row = _find(
        rows,
        cohort_id="fee_gate_v1@v1[threshold=v1]:scam_likely",
        tier_scope="T1",
    )
    assert row.action_class == "INSUFFICIENT_EVIDENCE"
    assert row.evidence_class == "insufficient"
    assert any("cohort_rate_extreme:1.0" in n for n in row.notes)


def test_low_n_with_baseline_rate_zero_stays_insufficient_evidence(tmp_path: Path) -> None:
    run = write_stage12_run(
        tmp_path / "run",
        baseline_rows=[
            BaselineRow(
                tier_index=1, tier_name="T1", n_complete=100,
                hit_2x_24h_count=0, hit_2x_24h_rate=0.0,
                hit_2x_24h_ci_low=0.0, hit_2x_24h_ci_high=0.04,
            ),
        ],
        filter_overall_rows=[],
        filter_by_tier_rows=[
            FilterByTierRow(
                tier_index=1, tier_name="T1", filter_label="scam_likely",
                n_complete=4, hit_2x_24h_count=1, hit_2x_24h_rate=0.25,
                hit_2x_24h_ci_low=0.05, hit_2x_24h_ci_high=0.70,
            ),
        ],
    )
    bundle = load_stage12_csvs(run)
    rows = build_recommendations(bundle, _T)
    row = _find(
        rows,
        cohort_id="fee_gate_v1@v1[threshold=v1]:scam_likely",
        tier_scope="T1",
    )
    assert row.action_class == "INSUFFICIENT_EVIDENCE"
    assert row.evidence_class == "insufficient"
    # The baseline_rate_zero observation is still surfaced as a note.
    assert "baseline_rate_zero" in row.notes


def test_high_n_with_cohort_rate_zero_still_promotes_to_anomaly(tmp_path: Path) -> None:
    # Regression guard: the F1 fix must not block legitimate anomaly
    # promotion for cohorts that DO meet the n-band floor.
    run = write_stage12_run(
        tmp_path / "run",
        baseline_rows=_baseline_rows(),
        filter_overall_rows=[],
        filter_by_tier_rows=[
            FilterByTierRow(
                tier_index=1, tier_name="T1", filter_label="scam_likely",
                n_complete=50, hit_2x_24h_count=0, hit_2x_24h_rate=0.0,
                hit_2x_24h_ci_low=0.0, hit_2x_24h_ci_high=0.07,
            ),
        ],
    )
    bundle = load_stage12_csvs(run)
    rows = build_recommendations(bundle, _T)
    row = _find(
        rows,
        cohort_id="fee_gate_v1@v1[threshold=v1]:scam_likely",
        tier_scope="T1",
    )
    assert row.action_class == "ANOMALY_FLAG"
    assert row.direction == "none"


# ---------------------------------------------------------------------------
# F2 audit remediation: strict per-tier baseline lookup.
# ---------------------------------------------------------------------------


def test_baseline_lookup_strict_match_succeeds(tmp_path: Path) -> None:
    baselines = {(1, "T1"): 0.20, (2, "T2"): 0.18}
    rate = resolve_baseline_rate(
        tier_scope="T1",
        tier_index=1,
        tier_name="T1",
        tier_baselines=baselines,
        overall_baseline=0.19,
    )
    assert rate == 0.20


def test_baseline_lookup_mismatched_tier_index_raises() -> None:
    # Stage 12 emitted baseline rows for (1, "T1") but the per-cohort
    # row claims tier_index=99 with tier_name="T1". The old loose
    # tier_name-only fallback would have returned 0.20 silently; the
    # strict path must raise instead.
    baselines = {(1, "T1"): 0.20}
    with pytest.raises(Stage13ValidationError):
        resolve_baseline_rate(
            tier_scope="T1",
            tier_index=99,
            tier_name="T1",
            tier_baselines=baselines,
            overall_baseline=0.19,
        )


def test_baseline_lookup_mismatched_tier_name_raises() -> None:
    baselines = {(1, "T1"): 0.20}
    with pytest.raises(Stage13ValidationError):
        resolve_baseline_rate(
            tier_scope="T1",
            tier_index=1,
            tier_name="DIFFERENT",
            tier_baselines=baselines,
            overall_baseline=0.19,
        )


def test_baseline_lookup_overall_uses_population_weighted_value() -> None:
    baselines = {(1, "T1"): 0.20, (2, "T2"): 0.18}
    rate = resolve_baseline_rate(
        tier_scope="overall",
        tier_index=None,
        tier_name=None,
        tier_baselines=baselines,
        overall_baseline=0.193,
    )
    assert rate == 0.193


# ---------------------------------------------------------------------------
# F3 audit remediation: strict numeric coercion.
# Missing/None/non-numeric required fields must raise.
# Optional fields preserve None and never silently coerce to 0.0.
# ---------------------------------------------------------------------------


def test_required_int_raises_on_none() -> None:
    with pytest.raises(Stage13ValidationError):
        _required_int(None, field_name="n_complete", cohort_id="x")


def test_required_int_raises_on_string() -> None:
    with pytest.raises(Stage13ValidationError):
        _required_int("not_a_number", field_name="n_complete", cohort_id="x")


def test_required_int_raises_on_nan() -> None:
    with pytest.raises(Stage13ValidationError):
        _required_int(float("nan"), field_name="n_complete", cohort_id="x")


def test_required_int_rejects_booleans() -> None:
    # bool is a subclass of int in Python; reject explicitly so
    # accidental True/False cells don't become 1/0.
    with pytest.raises(Stage13ValidationError):
        _required_int(True, field_name="n_complete", cohort_id="x")


def test_required_int_accepts_int_and_float_int() -> None:
    assert _required_int(50, field_name="n", cohort_id="x") == 50
    assert _required_int(50.0, field_name="n", cohort_id="x") == 50


def test_optional_float_preserves_none() -> None:
    assert _optional_float(None) is None


def test_optional_float_preserves_nan_as_none() -> None:
    # NaN is unsafe arithmetic; surface as None so callers branch on
    # the "rate undefined" path instead of propagating NaN.
    assert _optional_float(float("nan")) is None


def test_optional_float_does_not_coerce_string_to_zero() -> None:
    # F3 regression: missing/non-numeric cells must NOT become 0.0
    # (which is itself a legitimate Wilson-CI boundary value).
    assert _optional_float("oops") is None


def test_optional_float_passes_through_zero_distinct_from_none() -> None:
    # A genuine cohort_rate of 0.0 must remain 0.0, distinct from None.
    assert _optional_float(0.0) == 0.0


def test_builder_raises_when_required_n_complete_missing(tmp_path: Path) -> None:
    run = write_stage12_run(
        tmp_path / "run",
        baseline_rows=_baseline_rows(),
        filter_overall_rows=[],
        filter_by_tier_rows=[
            FilterByTierRow(
                tier_index=1, tier_name="T1", filter_label="scam_likely",
                n_complete=50, hit_2x_24h_rate=0.05,
            ),
        ],
    )
    bundle = load_stage12_csvs(run)
    # Mutate the loaded bundle to simulate a Stage 12 row with missing
    # n_complete (e.g., a CSV cell that arrived as None).
    bundle.filter_label_by_tier[0]["n_complete"] = None
    with pytest.raises(Stage13ValidationError):
        build_recommendations(bundle, _T)


def test_builder_raises_when_required_n_censored_missing(tmp_path: Path) -> None:
    run = write_stage12_run(
        tmp_path / "run",
        baseline_rows=_baseline_rows(),
        filter_overall_rows=[],
        filter_by_tier_rows=[
            FilterByTierRow(
                tier_index=1, tier_name="T1", filter_label="scam_likely",
                n_complete=50, hit_2x_24h_rate=0.05,
            ),
        ],
    )
    bundle = load_stage12_csvs(run)
    bundle.filter_label_by_tier[0]["n_censored"] = "garbage"
    with pytest.raises(Stage13ValidationError):
        build_recommendations(bundle, _T)

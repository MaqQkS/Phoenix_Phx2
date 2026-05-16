"""Stage 20.2 local warning + upstream warning surfacing tests.

Covers:
  * W2007 mapping-drift detection (with prior manifest):
      - No prior manifest -> never fires.
      - Identical mapping_version + label_mapping -> no fire.
      - mapping_version differs -> fires.
      - label_mapping differs by one entry -> fires.

  * Upstream W2001/W2004/W2005 surfacing:
      - W2001 bool: any occurrence in warnings tuple.
      - W2004 count: number of "W2004" entries (test uses 3 to
        exercise the counter formula -- 20.1 emits at most 1 per
        run, see Phase B exit notes).
      - W2005 count: number of "W2005" entries.

  * 7-key manifest.warnings dict assembly (upstream + local +
    always-zero W2003).
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from PHX2.stage20.builder import (
    assemble_manifest_warnings_dict,
    compute_local_warnings,
    surface_upstream_warnings,
)
from PHX2.stage20.clock import FrozenClock
from PHX2.stage20.constants import (
    LABEL_TO_STATE_MAPPING_V0,
    MAPPING_VERSION,
    PreviewEligibilityState,
)
from PHX2.stage20.input_validators import ValidationResult
from PHX2.stage20.models import PreviewCandidate


_FROZEN_NOW = datetime(2026, 5, 15, 0, 0, 0, tzinfo=timezone.utc)


def _frozen_clock() -> FrozenClock:
    return FrozenClock(_FROZEN_NOW)


def _candidate(
    *,
    preview_state: str = "PREVIEW_ELIGIBLE",
    candidate_id: str = "cand_default",
    review_stale: bool = False,
) -> PreviewCandidate:
    return PreviewCandidate(
        candidate_id=candidate_id,
        stage18_run_id="s18_a",
        stage19_run_id="s19_a",
        policy_hash="ph_a",
        rule_id="rule_a",
        window_seconds=30,
        operator_id="op_a",
        review_sequence=1,
        review_label="REVIEW_PROMISING_CONFIRMED",
        review_timestamp_utc="2026-05-15T00:00:00Z",
        eligibility_state=preview_state,
        stage18_classification="CLASS_A",
        stage17_label_preserved="LABEL_A",
        safe_for_live_dispatch=False,
        tier_hint="",
        reason_code="LABEL_MAPPED_FROM_OPERATOR_REVIEW",
        stage20_run_id="stage20_test",
        source_ledger_row_id="lrid_default",
        mapping_version=MAPPING_VERSION,
        review_age_days=0,
        review_stale=review_stale,
        multiple_operators_for_slice=False,
        notes="",
        preview_state=preview_state,
    )


def _current_label_mapping_as_strings() -> dict[str, str]:
    """Snapshot LABEL_TO_STATE_MAPPING_V0 with string values (manifest-shape)."""

    return {k: v.value for k, v in LABEL_TO_STATE_MAPPING_V0.items()}


# ---------------------------------------------------------------------------
# 22-25. W2007 mapping-drift detection
# ---------------------------------------------------------------------------


def test_w2007_does_not_fire_without_prior_manifest():
    out = compute_local_warnings([])
    assert out["W2007_eligibility_mapping_drift_detected"] is False


def test_w2007_does_not_fire_when_prior_matches_current():
    prior_mapping = _current_label_mapping_as_strings()
    out = compute_local_warnings(
        [],
        prior_manifest_label_mapping=prior_mapping,
        prior_manifest_mapping_version=MAPPING_VERSION,
    )
    assert out["W2007_eligibility_mapping_drift_detected"] is False


def test_w2007_fires_on_mapping_version_drift():
    prior_mapping = _current_label_mapping_as_strings()
    out = compute_local_warnings(
        [],
        prior_manifest_label_mapping=prior_mapping,
        prior_manifest_mapping_version="v999",
    )
    assert out["W2007_eligibility_mapping_drift_detected"] is True


def test_w2007_fires_on_label_mapping_drift_one_entry():
    drifted = _current_label_mapping_as_strings()
    # Mutate one entry: route REVIEW_REJECTED to an unexpected state.
    drifted["REVIEW_REJECTED"] = "PREVIEW_OBSERVE_ONLY"
    out = compute_local_warnings(
        [],
        prior_manifest_label_mapping=drifted,
        prior_manifest_mapping_version=MAPPING_VERSION,
    )
    assert out["W2007_eligibility_mapping_drift_detected"] is True


# ---------------------------------------------------------------------------
# W2002 / W2006 -- via compute_local_warnings
# ---------------------------------------------------------------------------


def test_compute_local_warnings_w2002_fires_when_zero_eligible():
    candidates = [_candidate(preview_state="PREVIEW_EXCLUDED",
                             candidate_id="cand_a"),
                  _candidate(preview_state="PREVIEW_OBSERVE_ONLY",
                             candidate_id="cand_b")]
    out = compute_local_warnings(candidates)
    assert out["W2002_preview_eligible_count_zero"] is True


def test_compute_local_warnings_w2002_false_when_eligible_present():
    candidates = [_candidate(preview_state="PREVIEW_ELIGIBLE",
                             candidate_id="cand_a")]
    out = compute_local_warnings(candidates)
    assert out["W2002_preview_eligible_count_zero"] is False


def test_compute_local_warnings_w2006_counts_stale_candidates():
    candidates = [
        _candidate(candidate_id="cand_a", review_stale=True),
        _candidate(candidate_id="cand_b", review_stale=True),
        _candidate(candidate_id="cand_c", review_stale=False),
    ]
    out = compute_local_warnings(candidates)
    assert out["W2006_candidate_review_stale_count"] == 2


def test_compute_local_warnings_w2006_zero_when_no_stale():
    candidates = [_candidate(candidate_id="cand_a", review_stale=False)]
    out = compute_local_warnings(candidates)
    assert out["W2006_candidate_review_stale_count"] == 0


# ---------------------------------------------------------------------------
# 26-28. Upstream warning surfacing
# ---------------------------------------------------------------------------


def test_w2001_surface_true_when_present():
    vr = ValidationResult(
        ok=True, errors=(), warnings=("W2001",), summary={}
    )
    out = surface_upstream_warnings(vr)
    assert out["W2001_run_median_staleness_exceeded"] is True


def test_w2001_surface_false_when_absent():
    vr = ValidationResult(
        ok=True, errors=(), warnings=(), summary={}
    )
    out = surface_upstream_warnings(vr)
    assert out["W2001_run_median_staleness_exceeded"] is False


def test_w2004_count_reflects_multi_occurrence_synthetic_3():
    """Prompt test 27: synthetic 3-occurrence ValidationResult.

    20.1's input_validators in reality emits W2004 at most once
    per run (single-occurrence at run level, not per-slice -- see
    Phase B exit notes). This test pre-constructs a 3-occurrence
    warnings tuple to exercise the counter formula so that any
    future 20.1 emission-semantics change automatically surfaces
    correctly without a code change in 20.2.
    """

    vr = ValidationResult(
        ok=True, errors=(),
        warnings=("W2004", "W2004", "W2004"),
        summary={},
    )
    out = surface_upstream_warnings(vr)
    assert out["W2004_multiple_operators_per_review_slice_count"] == 3


def test_w2005_count_reflects_multi_occurrence_synthetic_2():
    vr = ValidationResult(
        ok=True, errors=(),
        warnings=("W2005", "W2005"),
        summary={},
    )
    out = surface_upstream_warnings(vr)
    assert out["W2005_stage18_evidence_missing_for_review_count"] == 2


def test_upstream_surfacing_reflects_20_1_single_occurrence_baseline():
    """20.1 documented semantics: each upstream warning fires at most
    once at run level. The counter degrades gracefully to {0, 1}.
    """

    vr = ValidationResult(
        ok=True, errors=(),
        warnings=("W2001", "W2004", "W2005"),
        summary={},
    )
    out = surface_upstream_warnings(vr)
    assert out["W2001_run_median_staleness_exceeded"] is True
    assert out["W2004_multiple_operators_per_review_slice_count"] == 1
    assert out["W2005_stage18_evidence_missing_for_review_count"] == 1


# ---------------------------------------------------------------------------
# Manifest-warnings dict assembly (7 keys)
# ---------------------------------------------------------------------------


def test_manifest_warnings_dict_has_exactly_7_keys():
    vr = ValidationResult(
        ok=True, errors=(), warnings=(), summary={}
    )
    out = assemble_manifest_warnings_dict(vr, [])
    expected_keys = {
        "W2001_run_median_staleness_exceeded",
        "W2002_preview_eligible_count_zero",
        "W2003_tier_hint_missing_count",
        "W2004_multiple_operators_per_review_slice_count",
        "W2005_stage18_evidence_missing_for_review_count",
        "W2006_candidate_review_stale_count",
        "W2007_eligibility_mapping_drift_detected",
    }
    assert set(out.keys()) == expected_keys


def test_manifest_warnings_w2003_always_zero_v0():
    vr = ValidationResult(
        ok=True, errors=(), warnings=(), summary={}
    )
    out = assemble_manifest_warnings_dict(vr, [])
    assert out["W2003_tier_hint_missing_count"] == 0


def test_manifest_warnings_combines_upstream_local_and_w2003():
    vr = ValidationResult(
        ok=True, errors=(), warnings=("W2001", "W2004"), summary={}
    )
    candidates = [
        _candidate(candidate_id="cand_a", review_stale=True,
                   preview_state="PREVIEW_OBSERVE_ONLY"),
    ]
    out = assemble_manifest_warnings_dict(vr, candidates)
    # Upstream surfacing
    assert out["W2001_run_median_staleness_exceeded"] is True
    assert out["W2004_multiple_operators_per_review_slice_count"] == 1
    assert out["W2005_stage18_evidence_missing_for_review_count"] == 0
    # Local
    assert out["W2002_preview_eligible_count_zero"] is True  # no PREVIEW_ELIGIBLE
    assert out["W2006_candidate_review_stale_count"] == 1
    assert out["W2007_eligibility_mapping_drift_detected"] is False
    # W2003 stub
    assert out["W2003_tier_hint_missing_count"] == 0


def test_manifest_warnings_w2007_propagates_from_prior_manifest_drift():
    vr = ValidationResult(
        ok=True, errors=(), warnings=(), summary={}
    )
    out = assemble_manifest_warnings_dict(
        vr, [],
        prior_manifest_label_mapping=_current_label_mapping_as_strings(),
        prior_manifest_mapping_version="v999",
    )
    assert out["W2007_eligibility_mapping_drift_detected"] is True

"""Stage 25.6 summary builder tests.

Pins:

  * ``build_stage25_summary`` counts every artifact tuple's rows
    correctly and exposes per-status / per-kind / per-confidence
    breakdowns.
  * Input tuples are never mutated.
  * Canonical serialization is deterministic across two builds and
    sorted-key / no-whitespace.
  * Empty inputs produce a fully-populated zero-count summary.
"""

from __future__ import annotations

import pytest

from PHX2.stage25.constants import (
    ATH_CANDIDATE_KIND_INSUFFICIENT_DATA,
    ATH_CANDIDATE_KIND_SOURCE_REPORTED_PEAK,
    ATH_CANDIDATE_KINDS,
    CONFIDENCE_LEVEL_HIGH,
    CONFIDENCE_LEVEL_LOW,
    CONFIDENCE_LEVEL_MEDIUM,
    CONFIDENCE_LEVEL_NONE,
    CONFIDENCE_LEVELS,
    MEASUREMENT_STATUS_MEASURED,
    MEASUREMENT_STATUS_MISSING,
    MEASUREMENT_STATUSES,
    PRICE_WINDOW_KIND_POST_MIGRATION_PRIMARY,
    PRICE_WINDOW_KIND_UNKNOWN_WINDOW,
    PRICE_WINDOW_KINDS,
    RECONCILIATION_STATUS_AGREED,
    RECONCILIATION_STATUS_NO_SOURCES,
    RECONCILIATION_STATUSES,
    REJECTION_REASONS,
    SOURCE_FAMILIES,
    SOURCE_FAMILY_BIRDEYE,
    SOURCE_FAMILY_DEXSCREENER,
    SOURCE_STATUS_PRESENT,
    SOURCE_STATUSES,
    STAGE25_SUMMARY_VERSION,
    STAGE_NAME,
    STAGE_VERSION,
)
from PHX2.stage25.errors import Stage25ContractError
from PHX2.stage25.summary import (
    build_stage25_summary,
    serialize_stage25_summary,
)
from PHX2.tests.stage25.fixtures.builders import (
    FIXED_CLOCK_UTC,
    SAMPLE_TOKEN_MINT_A,
    SAMPLE_TOKEN_MINT_B,
    make_ath_candidate,
    make_measured_migration_measurement,
    make_migration_observation,
    make_price_window_observation,
    make_unmeasured_migration_measurement,
)


def _empty_summary() -> dict[str, object]:
    summary = build_stage25_summary(
        migration_observations=(),
        migration_measurements=(),
        price_window_observations=(),
        ath_candidates=(),
        source_reconciliations=(),
        ath_measurements=(),
        rejections=(),
        created_at_utc=FIXED_CLOCK_UTC,
    )
    return dict(summary)


# ---------------------------------------------------------------------------
# Empty-input shape
# ---------------------------------------------------------------------------


def test_empty_summary_row_counts_are_zero():
    summary = _empty_summary()
    assert summary["row_counts"] == {
        "migration_observations": 0,
        "migration_measurements": 0,
        "price_window_observations": 0,
        "ath_candidates": 0,
        "source_reconciliations": 0,
        "ath_measurements": 0,
        "rejections": 0,
    }


def test_empty_summary_token_count_is_zero():
    summary = _empty_summary()
    assert summary["observed_token_count"] == 0


def test_empty_summary_status_breakdowns_have_zero_counts():
    summary = _empty_summary()
    migration_status_counts = summary["migration_measurement_status_counts"]
    assert set(migration_status_counts.keys()) == set(MEASUREMENT_STATUSES)
    assert all(count == 0 for count in migration_status_counts.values())
    window_kind_counts = summary["price_window_kind_counts"]
    assert set(window_kind_counts.keys()) == set(PRICE_WINDOW_KINDS)
    assert all(count == 0 for count in window_kind_counts.values())
    ath_kind_counts = summary["ath_candidate_kind_counts"]
    assert set(ath_kind_counts.keys()) == set(ATH_CANDIDATE_KINDS)
    assert all(count == 0 for count in ath_kind_counts.values())
    ath_confidence_counts = summary["ath_candidate_confidence_counts"]
    assert set(ath_confidence_counts.keys()) == set(CONFIDENCE_LEVELS)
    ath_source_status_counts = summary["ath_candidate_source_status_counts"]
    assert set(ath_source_status_counts.keys()) == set(SOURCE_STATUSES)
    rejection_counts = summary["rejection_reason_counts"]
    assert set(rejection_counts.keys()) == set(REJECTION_REASONS)
    reconciliation_counts = summary[
        "source_reconciliation_status_counts"
    ]
    assert set(reconciliation_counts.keys()) == set(RECONCILIATION_STATUSES)


def test_empty_summary_carries_stage_axes():
    summary = _empty_summary()
    assert summary["stage_name"] == STAGE_NAME
    assert summary["stage_version"] == STAGE_VERSION
    assert summary["summary_version"] == STAGE25_SUMMARY_VERSION
    assert summary["observe_only_mode"] == "observe_only"
    assert summary["created_at_utc"] == FIXED_CLOCK_UTC


# ---------------------------------------------------------------------------
# Counts on populated input
# ---------------------------------------------------------------------------


def test_row_counts_match_input_tuple_lengths():
    migration_observations = (
        make_migration_observation(),
        make_migration_observation(token_mint=SAMPLE_TOKEN_MINT_B),
    )
    migration_measurements = (
        make_measured_migration_measurement(),
        make_unmeasured_migration_measurement(
            token_mint=SAMPLE_TOKEN_MINT_B,
            measurement_status=MEASUREMENT_STATUS_MISSING,
            reconciliation_status=RECONCILIATION_STATUS_NO_SOURCES,
        ),
    )
    price_window_observations = (
        make_price_window_observation(),
        make_price_window_observation(
            window_kind=PRICE_WINDOW_KIND_UNKNOWN_WINDOW,
            block_time=-1,
            slot=-1,
        ),
    )
    ath_candidates = (
        make_ath_candidate(),
        make_ath_candidate(
            source_family=SOURCE_FAMILY_BIRDEYE,
            candidate_kind=ATH_CANDIDATE_KIND_INSUFFICIENT_DATA,
            confidence_level=CONFIDENCE_LEVEL_NONE,
            peak_observed_at_utc="",
            peak_slot=-1,
            peak_block_time=-1,
            peak_price=None,
        ),
    )
    summary = build_stage25_summary(
        migration_observations=migration_observations,
        migration_measurements=migration_measurements,
        price_window_observations=price_window_observations,
        ath_candidates=ath_candidates,
        source_reconciliations=(),
        ath_measurements=(),
        rejections=(),
        created_at_utc=FIXED_CLOCK_UTC,
    )
    assert summary["row_counts"] == {
        "migration_observations": 2,
        "migration_measurements": 2,
        "price_window_observations": 2,
        "ath_candidates": 2,
        "source_reconciliations": 0,
        "ath_measurements": 0,
        "rejections": 0,
    }


def test_migration_measurement_status_counts_are_correct():
    measurements = (
        make_measured_migration_measurement(),
        make_unmeasured_migration_measurement(
            measurement_status=MEASUREMENT_STATUS_MISSING,
            reconciliation_status=RECONCILIATION_STATUS_NO_SOURCES,
        ),
    )
    summary = build_stage25_summary(
        migration_observations=(),
        migration_measurements=measurements,
        price_window_observations=(),
        ath_candidates=(),
        source_reconciliations=(),
        ath_measurements=(),
        rejections=(),
        created_at_utc=FIXED_CLOCK_UTC,
    )
    status_counts = summary["migration_measurement_status_counts"]
    assert status_counts[MEASUREMENT_STATUS_MEASURED] == 1
    assert status_counts[MEASUREMENT_STATUS_MISSING] == 1
    confidence_counts = summary[
        "migration_measurement_confidence_counts"
    ]
    assert confidence_counts[CONFIDENCE_LEVEL_HIGH] == 1
    assert confidence_counts[CONFIDENCE_LEVEL_NONE] == 1
    reconciliation_counts = summary[
        "migration_measurement_reconciliation_counts"
    ]
    assert reconciliation_counts[RECONCILIATION_STATUS_AGREED] == 1
    assert reconciliation_counts[RECONCILIATION_STATUS_NO_SOURCES] == 1


def test_price_window_kind_counts_are_correct():
    observations = (
        make_price_window_observation(),
        make_price_window_observation(
            window_kind=PRICE_WINDOW_KIND_UNKNOWN_WINDOW,
            block_time=-1,
            slot=-1,
        ),
        make_price_window_observation(
            window_kind=PRICE_WINDOW_KIND_POST_MIGRATION_PRIMARY,
            source_family=SOURCE_FAMILY_BIRDEYE,
        ),
    )
    summary = build_stage25_summary(
        migration_observations=(),
        migration_measurements=(),
        price_window_observations=observations,
        ath_candidates=(),
        source_reconciliations=(),
        ath_measurements=(),
        rejections=(),
        created_at_utc=FIXED_CLOCK_UTC,
    )
    counts = summary["price_window_kind_counts"]
    assert counts[PRICE_WINDOW_KIND_POST_MIGRATION_PRIMARY] == 2
    assert counts[PRICE_WINDOW_KIND_UNKNOWN_WINDOW] == 1


def test_ath_candidate_kind_counts_are_correct():
    candidates = (
        make_ath_candidate(),
        make_ath_candidate(
            source_family=SOURCE_FAMILY_BIRDEYE,
            candidate_kind=ATH_CANDIDATE_KIND_INSUFFICIENT_DATA,
            confidence_level=CONFIDENCE_LEVEL_NONE,
            peak_observed_at_utc="",
            peak_slot=-1,
            peak_block_time=-1,
            peak_price=None,
        ),
    )
    summary = build_stage25_summary(
        migration_observations=(),
        migration_measurements=(),
        price_window_observations=(),
        ath_candidates=candidates,
        source_reconciliations=(),
        ath_measurements=(),
        rejections=(),
        created_at_utc=FIXED_CLOCK_UTC,
    )
    counts = summary["ath_candidate_kind_counts"]
    assert counts[ATH_CANDIDATE_KIND_SOURCE_REPORTED_PEAK] == 1
    assert counts[ATH_CANDIDATE_KIND_INSUFFICIENT_DATA] == 1
    confidence_counts = summary["ath_candidate_confidence_counts"]
    assert confidence_counts[CONFIDENCE_LEVEL_MEDIUM] == 1
    assert confidence_counts[CONFIDENCE_LEVEL_NONE] == 1


def test_ath_candidate_source_family_counts_are_correct():
    candidates = (
        make_ath_candidate(source_family=SOURCE_FAMILY_DEXSCREENER),
        make_ath_candidate(
            source_family=SOURCE_FAMILY_BIRDEYE,
            candidate_kind=ATH_CANDIDATE_KIND_INSUFFICIENT_DATA,
            confidence_level=CONFIDENCE_LEVEL_NONE,
            peak_observed_at_utc="",
            peak_slot=-1,
            peak_block_time=-1,
            peak_price=None,
        ),
    )
    summary = build_stage25_summary(
        migration_observations=(),
        migration_measurements=(),
        price_window_observations=(),
        ath_candidates=candidates,
        source_reconciliations=(),
        ath_measurements=(),
        rejections=(),
        created_at_utc=FIXED_CLOCK_UTC,
    )
    source_counts = summary["ath_candidate_source_family_counts"]
    assert set(source_counts.keys()) == set(SOURCE_FAMILIES)
    assert source_counts[SOURCE_FAMILY_DEXSCREENER] == 1
    assert source_counts[SOURCE_FAMILY_BIRDEYE] == 1


def test_observed_token_count_counts_distinct_token_mints():
    migration_observations = (
        make_migration_observation(),
        make_migration_observation(),
        make_migration_observation(token_mint=SAMPLE_TOKEN_MINT_B),
    )
    summary = build_stage25_summary(
        migration_observations=migration_observations,
        migration_measurements=(),
        price_window_observations=(),
        ath_candidates=(),
        source_reconciliations=(),
        ath_measurements=(),
        rejections=(),
        created_at_utc=FIXED_CLOCK_UTC,
    )
    assert summary["observed_token_count"] == 2


# ---------------------------------------------------------------------------
# Determinism / immutability
# ---------------------------------------------------------------------------


def test_summary_is_deterministic_across_two_builds():
    args = dict(
        migration_observations=(make_migration_observation(),),
        migration_measurements=(make_measured_migration_measurement(),),
        price_window_observations=(make_price_window_observation(),),
        ath_candidates=(make_ath_candidate(),),
        source_reconciliations=(),
        ath_measurements=(),
        rejections=(),
        created_at_utc=FIXED_CLOCK_UTC,
    )
    summary_a = build_stage25_summary(**args)
    summary_b = build_stage25_summary(**args)
    assert serialize_stage25_summary(summary_a) == (
        serialize_stage25_summary(summary_b)
    )


def test_summary_serialization_is_canonical():
    summary = _empty_summary()
    serialized = serialize_stage25_summary(summary)
    assert " " not in serialized
    assert "\t" not in serialized
    assert "\n" not in serialized


def test_input_tuples_are_not_mutated_by_summary_builder():
    observations = (
        make_migration_observation(),
        make_migration_observation(token_mint=SAMPLE_TOKEN_MINT_B),
    )
    before = tuple(observations)
    _ = build_stage25_summary(
        migration_observations=observations,
        migration_measurements=(),
        price_window_observations=(),
        ath_candidates=(),
        source_reconciliations=(),
        ath_measurements=(),
        rejections=(),
        created_at_utc=FIXED_CLOCK_UTC,
    )
    assert observations == before
    assert observations is before or observations == before


def test_summary_mapping_is_frozen_against_caller_mutation():
    summary = build_stage25_summary(
        migration_observations=(),
        migration_measurements=(),
        price_window_observations=(),
        ath_candidates=(),
        source_reconciliations=(),
        ath_measurements=(),
        rejections=(),
        created_at_utc=FIXED_CLOCK_UTC,
    )
    with pytest.raises(TypeError):
        summary["observed_token_count"] = 999  # type: ignore[index]


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------


def test_summary_rejects_non_tuple_input():
    with pytest.raises(Stage25ContractError):
        build_stage25_summary(
            migration_observations=[make_migration_observation()],  # type: ignore[arg-type]
            migration_measurements=(),
            price_window_observations=(),
            ath_candidates=(),
            source_reconciliations=(),
            ath_measurements=(),
            rejections=(),
            created_at_utc=FIXED_CLOCK_UTC,
        )


def test_summary_rejects_empty_created_at_utc():
    with pytest.raises(Stage25ContractError):
        build_stage25_summary(
            migration_observations=(),
            migration_measurements=(),
            price_window_observations=(),
            ath_candidates=(),
            source_reconciliations=(),
            ath_measurements=(),
            rejections=(),
            created_at_utc="",
        )


def test_summary_serialize_rejects_non_mapping():
    with pytest.raises(Stage25ContractError):
        serialize_stage25_summary("not a mapping")  # type: ignore[arg-type]

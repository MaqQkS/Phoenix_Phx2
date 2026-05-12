"""Stage 12 bucketing unit tests (TEST 6 unit-level parts).

Pipeline-level TEST 6 assertions (bucket_low/bucket_high in CSV,
manifest.primitives_analyzed shape) live in Phase 4 integration tests.
"""

from __future__ import annotations

import math

import pytest

from PHX2.analysis.buckets import (
    DOMAIN_BUCKETS,
    MISSING_BUCKET_INDEX,
    MISSING_BUCKET_ORDER,
    BucketSpec,
    bucket_one_primitive,
    compute_quartile_edges,
    detect_degeneracy,
)


# ---------------------------------------------------------------------------
# detect_degeneracy
# ---------------------------------------------------------------------------


def test_detect_degeneracy_no_non_null_values() -> None:
    assert detect_degeneracy([None, None, float("nan")]) == "no_non_null_values"
    assert detect_degeneracy([]) == "no_non_null_values"


def test_detect_degeneracy_single_value() -> None:
    assert detect_degeneracy([1.0, 1.0, 1.0, None]) == "single_value"


def test_detect_degeneracy_few_distinct_values() -> None:
    assert detect_degeneracy([1.0, 2.0]) == "few_distinct_values"
    assert detect_degeneracy([1.0, 2.0, 3.0, 2.0, 3.0]) == "few_distinct_values"


def test_detect_degeneracy_ok_threshold_is_four_distinct() -> None:
    assert detect_degeneracy([1.0, 2.0, 3.0, 4.0]) == "ok"
    assert detect_degeneracy(list(range(10))) == "ok"


# ---------------------------------------------------------------------------
# compute_quartile_edges
# ---------------------------------------------------------------------------


def test_compute_quartile_edges_thirty_values_one_to_thirty() -> None:
    # NumPy linear interpolation on [1..30]:
    #   q1 = 0.25*(30-1)+1 = 8.25
    #   q2 = 0.5*(30-1)+1  = 15.5
    #   q3 = 0.75*(30-1)+1 = 22.75
    edges = compute_quartile_edges(list(range(1, 31)))
    assert math.isclose(edges[0], 8.25)
    assert math.isclose(edges[1], 15.5)
    assert math.isclose(edges[2], 22.75)


def test_compute_quartile_edges_ignores_nulls() -> None:
    edges = compute_quartile_edges([None, 1.0, 2.0, 3.0, 4.0, float("nan"), None])
    # Effective input is [1, 2, 3, 4]: q1=1.75, q2=2.5, q3=3.25.
    assert math.isclose(edges[0], 1.75)
    assert math.isclose(edges[1], 2.5)
    assert math.isclose(edges[2], 3.25)


# ---------------------------------------------------------------------------
# bucket_one_primitive -- quartile path
# ---------------------------------------------------------------------------


def _spec_by_index(specs: tuple[BucketSpec, ...]) -> dict[str, BucketSpec]:
    return {spec.bucket_index: spec for spec in specs}


def test_bucket_one_primitive_quartile_thirty_values() -> None:
    values = list(range(1, 31))
    result = bucket_one_primitive("some_primitive", values)
    assert not result.skipped
    assert result.method == "quartile"
    assert result.edges == (8.25, 15.5, 22.75)
    # No nulls -> no "missing" bucket spec.
    assert MISSING_BUCKET_INDEX not in _spec_by_index(result.bucket_specs)
    # Q1: values < 8.25 -> 1..8 = 8 items.
    # Q2: 8.25 <= v < 15.5 -> 9..15 = 7 items.
    # Q3: 15.5 <= v < 22.75 -> 16..22 = 7 items.
    # Q4: v >= 22.75 -> 23..30 = 8 items.
    counts = {b: result.assignments.count(b) for b in ("Q1", "Q2", "Q3", "Q4")}
    assert counts == {"Q1": 8, "Q2": 7, "Q3": 7, "Q4": 8}


def test_bucket_one_primitive_quartile_missing_routed_explicitly() -> None:
    values = list(range(1, 30)) + [None]  # 29 values + 1 NULL
    result = bucket_one_primitive("some_primitive", values)
    assert not result.skipped
    assert result.method == "quartile"
    specs = _spec_by_index(result.bucket_specs)
    assert MISSING_BUCKET_INDEX in specs
    assert specs[MISSING_BUCKET_INDEX].bucket_order == MISSING_BUCKET_ORDER
    # Last assignment is the NULL -> "missing".
    assert result.assignments[-1] == MISSING_BUCKET_INDEX


def test_bucket_one_primitive_quartile_specs_have_expected_orders() -> None:
    values = list(range(1, 30)) + [None]
    result = bucket_one_primitive("some_primitive", values)
    orders = {spec.bucket_index: spec.bucket_order for spec in result.bucket_specs}
    assert orders["missing"] == 0
    assert orders["Q1"] == 1
    assert orders["Q2"] == 2
    assert orders["Q3"] == 3
    assert orders["Q4"] == 4


def test_bucket_one_primitive_quartile_specs_bucket_low_high_aligned_to_edges() -> None:
    values = list(range(1, 31))
    result = bucket_one_primitive("some_primitive", values)
    specs = _spec_by_index(result.bucket_specs)
    q1, q2, q3 = result.edges  # type: ignore[misc]
    assert specs["Q1"].bucket_low == 1.0
    assert specs["Q1"].bucket_high == q1
    assert specs["Q2"].bucket_low == q1
    assert specs["Q2"].bucket_high == q2
    assert specs["Q3"].bucket_low == q2
    assert specs["Q3"].bucket_high == q3
    assert specs["Q4"].bucket_low == q3
    assert specs["Q4"].bucket_high == 30.0


# ---------------------------------------------------------------------------
# bucket_one_primitive -- degeneracy paths
# ---------------------------------------------------------------------------


def test_bucket_one_primitive_skipped_single_value() -> None:
    result = bucket_one_primitive("flat_primitive", [5.0, 5.0, 5.0, 5.0])
    assert result.skipped
    assert result.skip_reason == "single_value"
    assert result.bucket_specs == ()
    assert result.assignments == ()


def test_bucket_one_primitive_skipped_all_null() -> None:
    result = bucket_one_primitive("missing_primitive", [None, None, float("nan")])
    assert result.skipped
    assert result.skip_reason == "no_non_null_values"


def test_bucket_one_primitive_skipped_few_distinct_values() -> None:
    result = bucket_one_primitive("sparse_primitive", [1.0, 2.0, 1.0, 2.0])
    assert result.skipped
    assert result.skip_reason == "few_distinct_values"


# ---------------------------------------------------------------------------
# bucket_one_primitive -- domain path (time_since_migration_seconds)
# ---------------------------------------------------------------------------


def test_domain_buckets_canonical_v0_has_two_primitives() -> None:
    # Spec §7.5 — exactly time_since_migration_seconds and
    # time_since_ath_seconds, NOT the outcome-window-aligned alternative.
    assert set(DOMAIN_BUCKETS.keys()) == {
        "time_since_migration_seconds",
        "time_since_ath_seconds",
    }


def test_bucket_one_primitive_domain_time_since_migration_assignments() -> None:
    # One value in each declared bucket plus an unbounded-upper case.
    values = [
        0.0,              # [0h, 1h)
        3599.0,           # [0h, 1h) (just below 1h)
        3600.0,           # [1h, 6h)
        21600.0,          # [6h, 24h)
        86400.0,          # [24h, 72h)
        259200.0,         # [72h, inf)
        1_000_000.0,      # [72h, inf)
    ]
    result = bucket_one_primitive("time_since_migration_seconds", values)
    assert not result.skipped
    assert result.method == "domain"
    assert result.assignments == (
        "[0h, 1h)",
        "[0h, 1h)",
        "[1h, 6h)",
        "[6h, 24h)",
        "[24h, 72h)",
        "[72h, inf)",
        "[72h, inf)",
    )


def test_bucket_one_primitive_domain_time_since_ath_assignments() -> None:
    values = [0.0, 299.0, 300.0, 1800.0, 7200.0, 86400.0, 100_000.0]
    result = bucket_one_primitive("time_since_ath_seconds", values)
    assert result.assignments == (
        "[0m, 5m)",
        "[0m, 5m)",
        "[5m, 30m)",
        "[30m, 2h)",
        "[2h, 24h)",
        "[24h, inf)",
        "[24h, inf)",
    )


def test_bucket_one_primitive_domain_specs_carry_low_high() -> None:
    result = bucket_one_primitive(
        "time_since_migration_seconds", [0.0, 1000.0, 5000.0]
    )
    specs = _spec_by_index(result.bucket_specs)
    assert specs["[0h, 1h)"].bucket_low == 0.0
    assert specs["[0h, 1h)"].bucket_high == 3600.0
    assert specs["[72h, inf)"].bucket_low == 259200.0
    assert specs["[72h, inf)"].bucket_high is None


def test_bucket_one_primitive_domain_missing_routed_to_missing_bucket() -> None:
    values = [0.0, None, 5000.0, float("nan")]
    result = bucket_one_primitive("time_since_migration_seconds", values)
    assert result.assignments == ("[0h, 1h)", "missing", "[1h, 6h)", "missing")
    specs = _spec_by_index(result.bucket_specs)
    assert specs["missing"].bucket_order == 0


def test_bucket_one_primitive_domain_skipped_when_all_null() -> None:
    result = bucket_one_primitive(
        "time_since_migration_seconds", [None, None, float("nan")]
    )
    assert result.skipped
    assert result.skip_reason == "no_non_null_values"


# ---------------------------------------------------------------------------
# bucket_one_primitive -- boolean path (defensive; no v0 primitives)
# ---------------------------------------------------------------------------


def test_bucket_one_primitive_boolean_path_assigns_true_false_missing() -> None:
    result = bucket_one_primitive(
        "hypothetical_boolean", [True, False, None, True], is_boolean=True
    )
    assert not result.skipped
    assert result.method == "boolean"
    assert result.assignments == ("true", "false", "missing", "true")

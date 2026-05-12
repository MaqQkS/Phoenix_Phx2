"""Stage 13 Wilson score interval unit tests.

Hand-computed reference values per spec §WILSON CI ("Do not make
statsmodels a hard runtime dependency. Use hand-computed reference
values for Wilson CI tests.").

Reference values are derived from the closed-form Wilson formula:

  p_hat = k / n
  z = 1.959963984540054
  denom = 1 + z^2/n
  center = (p_hat + z^2/(2n)) / denom
  margin = (z * sqrt(p_hat*(1-p_hat)/n + z^2/(4n^2))) / denom

The (k=5, n=10), (k=10, n=10), (k=0, n=10), and (k=1, n=1) cases
cross-check against published Wilson CI tables; the remaining cases
exercise small-n, n=1, large-n, and asymmetric-p configurations.
"""

from __future__ import annotations

import math

import pytest

from PHX2.stage13.wilson import (
    WILSON_Z_95,
    ci_excludes_baseline,
    wilson_score_interval,
)


_TOL = 1e-6


def _wilson_oracle(
    k: int, n: int, z: float = 1.959963984540054
) -> tuple[float | None, float | None]:
    """Independent in-test closed-form Wilson CI.

    Inlined here so the assertion compares
    ``wilson_score_interval`` against a *separately written* execution
    of the same formula. Catches arithmetic typos and operator-precedence
    bugs in either path.
    """

    if n == 0:
        return (None, None)
    p_hat = k / n
    z2 = z * z
    denom = 1.0 + z2 / n
    center = (p_hat + z2 / (2.0 * n)) / denom
    inner = p_hat * (1.0 - p_hat) / n + z2 / (4.0 * n * n)
    margin = (z * math.sqrt(inner)) / denom
    return (max(0.0, center - margin), min(1.0, center + margin))


def _assert_ci_close(
    actual: tuple[float | None, float | None],
    expected_low: float | None,
    expected_high: float | None,
    tol: float = _TOL,
) -> None:
    low, high = actual
    if expected_low is None:
        assert low is None
    else:
        assert low is not None
        assert math.isclose(low, expected_low, abs_tol=tol), (
            f"lower {low!r} != {expected_low!r} (tol={tol})"
        )
    if expected_high is None:
        assert high is None
    else:
        assert high is not None
        assert math.isclose(high, expected_high, abs_tol=tol), (
            f"upper {high!r} != {expected_high!r} (tol={tol})"
        )


def test_wilson_z_95_constant_is_locked() -> None:
    # The z literal must match Stage 12's locked z so cross-stage CI
    # comparisons are bit-identical.
    assert WILSON_Z_95 == 1.959963984540054


def test_n_zero_returns_pair_of_none() -> None:
    assert wilson_score_interval(0, 0) == (None, None)


# ---------------------------------------------------------------------------
# Published reference values (Wikipedia / standard Wilson CI tables).
# These use a looser tolerance because the published values are
# typically rounded to 4 decimal places. They catch structural formula
# errors -- e.g., dropping the continuity correction or swapping +/-.
# ---------------------------------------------------------------------------


def test_published_k_zero_n_ten() -> None:
    _assert_ci_close(wilson_score_interval(0, 10), 0.0, 0.2775, tol=5e-4)


def test_published_k_five_n_ten_symmetric() -> None:
    _assert_ci_close(wilson_score_interval(5, 10), 0.2366, 0.7634, tol=5e-4)


def test_published_k_ten_n_ten() -> None:
    _assert_ci_close(wilson_score_interval(10, 10), 0.7225, 1.0, tol=5e-4)


def test_published_k_one_n_one() -> None:
    _assert_ci_close(wilson_score_interval(1, 1), 0.2065, 1.0, tol=5e-4)


# ---------------------------------------------------------------------------
# Tight (1e-6) reference values via the independent oracle.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "k,n",
    [
        (0, 10),
        (10, 10),
        (5, 10),
        (1, 1),
        (0, 1),
        (50, 100),
        (80, 100),
        (1, 30),
        (3, 25),
        (29, 30),
    ],
)
def test_oracle_match_tight_tolerance(k: int, n: int) -> None:
    impl = wilson_score_interval(k, n)
    oracle = _wilson_oracle(k, n)
    _assert_ci_close(impl, oracle[0], oracle[1], tol=_TOL)


def test_k_greater_than_n_raises() -> None:
    with pytest.raises(ValueError):
        wilson_score_interval(11, 10)


def test_negative_k_raises() -> None:
    with pytest.raises(ValueError):
        wilson_score_interval(-1, 10)


def test_non_95_alpha_rejected_v0() -> None:
    # v0 hard-codes the 95% z literal; other alphas are rejected so
    # callers can't silently misuse the helper.
    with pytest.raises(ValueError):
        wilson_score_interval(5, 10, alpha=0.10)


def test_endpoints_are_within_unit_interval() -> None:
    # Sanity: across a fuzz-style sweep, bounds remain in [0, 1].
    for k in range(0, 21):
        n = 20
        lo, hi = wilson_score_interval(k, n)
        assert lo is not None and hi is not None
        assert 0.0 <= lo <= hi <= 1.0


def test_ci_excludes_baseline_strict_above() -> None:
    assert ci_excludes_baseline(0.6, 0.8, 0.55) is True


def test_ci_excludes_baseline_strict_below() -> None:
    assert ci_excludes_baseline(0.4, 0.6, 0.65) is True


def test_ci_includes_baseline_at_boundary() -> None:
    # baseline == ci_low or ci_high means the CI does NOT strictly
    # exclude it.
    assert ci_excludes_baseline(0.4, 0.6, 0.4) is False
    assert ci_excludes_baseline(0.4, 0.6, 0.6) is False


def test_ci_includes_baseline_interior() -> None:
    assert ci_excludes_baseline(0.4, 0.6, 0.5) is False


def test_ci_excludes_baseline_returns_none_on_missing_inputs() -> None:
    assert ci_excludes_baseline(None, 0.6, 0.5) is None
    assert ci_excludes_baseline(0.4, None, 0.5) is None
    assert ci_excludes_baseline(0.4, 0.6, None) is None

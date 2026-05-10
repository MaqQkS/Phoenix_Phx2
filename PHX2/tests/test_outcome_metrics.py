"""Unit tests for the OutcomeTrackingService metric calculator.

Pure function tests — no DB, no repositories, no I/O. Each case feeds a list
of (offset_seconds, price, mcap) tuples plus an alert price into
``compute_outcome_metrics`` and asserts each output field. ``offset_seconds``
is relative to ``WINDOW_START``.
"""

from datetime import datetime, timedelta, timezone
from typing import List, Optional, Sequence, Tuple

import pytest

from PHX2.models import OutcomeWindowStatus, PriceObservation
from PHX2.services.outcome_tracking_service import compute_outcome_metrics


WINDOW_START = datetime(2026, 5, 8, 12, 0, 0, tzinfo=timezone.utc)


def _obs(
    *triples: Tuple[float, Optional[float], Optional[float]],
) -> List[PriceObservation]:
    """Build a list of PriceObservation rows from (offset_seconds, price, mcap).

    Uses ``observed_at = WINDOW_START + offset_seconds``. Token, source, and
    data_status get sane defaults — those fields don't affect the calculator.
    """

    return [
        PriceObservation(
            token_address="t",
            observed_at=WINDOW_START + timedelta(seconds=offset),
            source="test",
            price=price,
            mcap=mcap,
        )
        for offset, price, mcap in triples
    ]


def test_empty_observations_returns_no_price_data_shape():
    metrics = compute_outcome_metrics([], alert_price=1.0, window_start_time=WINDOW_START)

    assert metrics.status == OutcomeWindowStatus.NO_PRICE_DATA
    assert metrics.observations_count == 0
    assert metrics.max_price is None
    assert metrics.min_price is None
    assert metrics.max_return_multiple is None
    assert metrics.max_drawdown_from_peak_pct is None
    assert metrics.hit_2x is None
    assert metrics.hit_3x is None
    assert metrics.hit_5x is None
    assert metrics.first_observation_time is None
    assert metrics.last_observation_time is None


def test_single_observation_max_equals_min_drawdown_zero():
    metrics = compute_outcome_metrics(
        _obs((60.0, 2.0, 200.0)),
        alert_price=1.0,
        window_start_time=WINDOW_START,
    )

    assert metrics.status == OutcomeWindowStatus.COMPLETE
    assert metrics.observations_count == 1
    assert metrics.max_price == 2.0
    assert metrics.min_price == 2.0
    assert metrics.max_return_multiple == pytest.approx(2.0)
    assert metrics.min_return_multiple == pytest.approx(2.0)
    assert metrics.max_drawdown_from_peak_pct == 0.0
    assert metrics.hit_2x is True
    assert metrics.hit_3x is False
    assert metrics.hit_5x is False
    assert metrics.time_to_max_return_seconds == 60.0


def test_monotonically_increasing_prices():
    metrics = compute_outcome_metrics(
        _obs(
            (10.0, 1.0, 100.0),
            (20.0, 2.0, 200.0),
            (30.0, 3.0, 300.0),
        ),
        alert_price=1.0,
        window_start_time=WINDOW_START,
    )

    assert metrics.status == OutcomeWindowStatus.COMPLETE
    assert metrics.max_price == 3.0
    assert metrics.min_price == 1.0
    assert metrics.max_observation_time == WINDOW_START + timedelta(seconds=30)
    assert metrics.min_observation_time == WINDOW_START + timedelta(seconds=10)
    assert metrics.max_drawdown_from_peak_pct == 0.0  # peak is final
    assert metrics.time_to_max_return_seconds == 30.0
    assert metrics.hit_2x is True
    assert metrics.hit_3x is True
    assert metrics.hit_5x is False


def test_monotonically_decreasing_prices():
    metrics = compute_outcome_metrics(
        _obs(
            (10.0, 3.0, 300.0),
            (20.0, 2.0, 200.0),
            (30.0, 1.0, 100.0),
        ),
        alert_price=1.0,
        window_start_time=WINDOW_START,
    )

    assert metrics.status == OutcomeWindowStatus.COMPLETE
    assert metrics.max_price == 3.0
    assert metrics.min_price == 1.0
    assert metrics.max_observation_time == WINDOW_START + timedelta(seconds=10)
    assert metrics.max_drawdown_from_peak_pct == pytest.approx(((1.0 / 3.0) - 1.0) * 100.0)


def test_v_shape_down_then_up():
    metrics = compute_outcome_metrics(
        _obs(
            (10.0, 2.0, 200.0),
            (20.0, 1.0, 100.0),
            (30.0, 3.0, 300.0),
        ),
        alert_price=1.0,
        window_start_time=WINDOW_START,
    )

    assert metrics.max_price == 3.0
    assert metrics.min_price == 1.0
    # Peak is the final observation, drawdown is 0.0.
    assert metrics.max_drawdown_from_peak_pct == 0.0


def test_inverted_v_pump_then_dump():
    metrics = compute_outcome_metrics(
        _obs(
            (10.0, 2.0, 200.0),
            (20.0, 4.0, 400.0),  # peak
            (30.0, 1.5, 150.0),  # dump
        ),
        alert_price=1.0,
        window_start_time=WINDOW_START,
    )

    assert metrics.max_price == 4.0
    assert metrics.max_drawdown_from_peak_pct == pytest.approx(((1.5 / 4.0) - 1.0) * 100.0)


def test_peak_is_final_observation_drawdown_zero_not_null():
    """Dedicated test: when the peak is the last observation, drawdown is 0.0
    (numerically distinct from None / SQL NULL). This boundary matters for
    downstream Stage 12 reports — a NULL would conflate "no later data" with
    "service not run yet."
    """

    metrics = compute_outcome_metrics(
        _obs(
            (10.0, 1.5, 150.0),
            (20.0, 2.0, 200.0),
            (30.0, 5.0, 500.0),  # peak is final
        ),
        alert_price=1.0,
        window_start_time=WINDOW_START,
    )

    assert metrics.max_drawdown_from_peak_pct == 0.0
    assert metrics.max_drawdown_from_peak_pct is not None


def test_tie_on_max_first_occurrence_wins():
    metrics = compute_outcome_metrics(
        _obs(
            (10.0, 3.0, 300.0),  # earlier peak
            (20.0, 2.0, 200.0),
            (30.0, 3.0, 300.0),  # tied, but later
        ),
        alert_price=1.0,
        window_start_time=WINDOW_START,
    )

    assert metrics.max_price == 3.0
    assert metrics.max_observation_time == WINDOW_START + timedelta(seconds=10)
    # Drawdown computed against the EARLIER peak (idx 0); later obs are
    # [2.0, 3.0], min=2.0, drawdown=((2/3)-1)*100.
    assert metrics.max_drawdown_from_peak_pct == pytest.approx(((2.0 / 3.0) - 1.0) * 100.0)


def test_tie_on_min_first_occurrence_wins():
    metrics = compute_outcome_metrics(
        _obs(
            (10.0, 1.0, 100.0),  # first min
            (20.0, 3.0, 300.0),
            (30.0, 1.0, 100.0),  # tied later
        ),
        alert_price=1.0,
        window_start_time=WINDOW_START,
    )

    assert metrics.min_price == 1.0
    assert metrics.min_observation_time == WINDOW_START + timedelta(seconds=10)


def test_hit_2x_inclusive_at_threshold():
    metrics = compute_outcome_metrics(
        _obs((10.0, 2.0, 200.0)),
        alert_price=1.0,
        window_start_time=WINDOW_START,
    )

    assert metrics.max_return_multiple == pytest.approx(2.0)
    assert metrics.hit_2x is True
    assert metrics.hit_3x is False
    assert metrics.hit_5x is False


def test_hit_3x_strictly_below_threshold():
    metrics = compute_outcome_metrics(
        _obs((10.0, 2.999, 299.9)),
        alert_price=1.0,
        window_start_time=WINDOW_START,
    )

    assert metrics.hit_2x is True
    assert metrics.hit_3x is False
    assert metrics.hit_5x is False


def test_hit_5x_inclusive_at_threshold():
    metrics = compute_outcome_metrics(
        _obs((10.0, 5.0, 500.0)),
        alert_price=1.0,
        window_start_time=WINDOW_START,
    )

    assert metrics.hit_2x is True
    assert metrics.hit_3x is True
    assert metrics.hit_5x is True


@pytest.mark.parametrize("alert_price", [None, 0.0, -1.0, float("inf"), float("nan")])
def test_invalid_alert_price_returns_invalid_shape(alert_price):
    metrics = compute_outcome_metrics(
        _obs((10.0, 1.0, 100.0)),
        alert_price=alert_price,
        window_start_time=WINDOW_START,
    )

    assert metrics.status == OutcomeWindowStatus.INVALID_ALERT_PRICE
    assert metrics.observations_count is None  # NULL by spec
    assert metrics.max_price is None
    assert metrics.min_price is None
    assert metrics.max_return_multiple is None
    assert metrics.hit_2x is None
    assert metrics.hit_3x is None
    assert metrics.hit_5x is None


def test_observations_with_only_none_prices_treated_as_no_price_data():
    metrics = compute_outcome_metrics(
        _obs(
            (10.0, None, None),
            (20.0, None, None),
        ),
        alert_price=1.0,
        window_start_time=WINDOW_START,
    )

    assert metrics.status == OutcomeWindowStatus.NO_PRICE_DATA
    assert metrics.observations_count == 0


def test_max_min_return_pcts_match_multiples():
    metrics = compute_outcome_metrics(
        _obs(
            (10.0, 0.5, 50.0),  # -50%
            (20.0, 4.0, 400.0),  # +300%
        ),
        alert_price=1.0,
        window_start_time=WINDOW_START,
    )

    assert metrics.max_return_multiple == pytest.approx(4.0)
    assert metrics.max_return_pct == pytest.approx(300.0)
    assert metrics.min_return_multiple == pytest.approx(0.5)
    assert metrics.min_return_pct == pytest.approx(-50.0)


def test_max_mcap_tracks_observation_at_max_price():
    metrics = compute_outcome_metrics(
        _obs(
            (10.0, 2.0, 999.0),
            (20.0, 4.0, 222.0),  # peak — its mcap is 222
        ),
        alert_price=1.0,
        window_start_time=WINDOW_START,
    )

    # max_mcap is the mcap snapshot of the price-peak observation, not the
    # global mcap maximum.
    assert metrics.max_price == 4.0
    assert metrics.max_mcap == 222.0


def test_max_mcap_is_none_when_source_observation_lacks_mcap():
    metrics = compute_outcome_metrics(
        _obs(
            (10.0, 2.0, None),  # peak has no mcap
        ),
        alert_price=1.0,
        window_start_time=WINDOW_START,
    )

    assert metrics.max_price == 2.0
    assert metrics.max_mcap is None

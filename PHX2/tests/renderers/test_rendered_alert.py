"""Tests for RenderedAlert dataclass and severity derivation."""

from dataclasses import FrozenInstanceError

import pytest

from PHX2.models.enums import DataStatus, DecisionType
from PHX2.renderers.rendered_alert import (
    DRY_RUN_BANNER,
    PARTIAL_DATA_STATUSES,
    RenderedAlert,
    Severity,
    derive_severity,
)


def test_dry_run_banner_value():
    assert DRY_RUN_BANNER == "[PHX2 DRY RUN — DO NOT TRADE]"


# ---- severity derivation ------------------------------------------------


@pytest.mark.parametrize("data_status", list(DataStatus))
def test_error_decision_always_severity_error(data_status):
    assert (
        derive_severity(DecisionType.ERROR, data_status) == Severity.ERROR
    )


def test_would_alert_with_ok_data_is_clean():
    assert (
        derive_severity(DecisionType.WOULD_ALERT, DataStatus.OK)
        == Severity.CLEAN
    )


@pytest.mark.parametrize("data_status", sorted(PARTIAL_DATA_STATUSES, key=lambda s: s.value))
def test_would_alert_with_partial_data_is_partial(data_status):
    assert (
        derive_severity(DecisionType.WOULD_ALERT, data_status)
        == Severity.PARTIAL
    )


@pytest.mark.parametrize(
    "data_status",
    [
        DataStatus.OK,
        DataStatus.PARTIAL,
        DataStatus.MISSING,
        DataStatus.NO_EVENTS,
        DataStatus.DATA_LIMITED,
        DataStatus.SOURCE_UNAVAILABLE,
        DataStatus.ERROR,
    ],
)
def test_skip_is_always_info(data_status):
    assert derive_severity(DecisionType.SKIP, data_status) == Severity.INFO


@pytest.mark.parametrize(
    "data_status",
    [
        DataStatus.OK,
        DataStatus.PARTIAL,
        DataStatus.MISSING,
    ],
)
def test_block_is_always_info(data_status):
    assert derive_severity(DecisionType.BLOCK, data_status) == Severity.INFO


def test_partial_data_statuses_are_unique_subset_of_data_status():
    for value in PARTIAL_DATA_STATUSES:
        assert isinstance(value, DataStatus)


def test_would_alert_with_missing_data_falls_back_to_clean():
    # A WOULD_ALERT with DataStatus.MISSING should be a contradiction in
    # practice (the engine would never emit it), but the renderer must still
    # produce a valid severity. Anything not in PARTIAL_DATA_STATUSES with a
    # non-error decision_type maps to CLEAN.
    assert (
        derive_severity(DecisionType.WOULD_ALERT, DataStatus.MISSING)
        == Severity.CLEAN
    )


# ---- RenderedAlert dataclass --------------------------------------------


def _make_minimal_rendered_alert() -> RenderedAlert:
    return RenderedAlert(
        banner=DRY_RUN_BANNER,
        severity=Severity.CLEAN,
        decision_type="would_alert",
        tier_label="T2",
        headline="WOULD_ALERT — T2",
    )


def test_rendered_alert_is_frozen():
    rendered = _make_minimal_rendered_alert()
    with pytest.raises(FrozenInstanceError):
        rendered.headline = "mutated"  # type: ignore[misc]


def test_rendered_alert_default_collections_are_separate_instances():
    a = _make_minimal_rendered_alert()
    b = _make_minimal_rendered_alert()
    assert a.token_section is not b.token_section
    assert a.missing_section is not b.missing_section


def test_rendered_alert_severity_enum_values():
    assert Severity.CLEAN.value == "clean"
    assert Severity.PARTIAL.value == "partial"
    assert Severity.ERROR.value == "error"
    assert Severity.INFO.value == "info"

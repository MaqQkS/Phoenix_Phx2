"""Synthetic Stage 23.1 test fixture builders.

These helpers build deterministic, secret-free synthetic
Stage23 records used by the Stage 23.1 test suite. No live
provider payloads are checked into the repository; the
fixtures are constructed from short non-secret literals.

The builders are intentionally simple wrappers around the
Stage 23 production model constructors so the test suite
exercises the same closed-set validation paths the future
filter implementations will exercise.
"""

from __future__ import annotations

from types import MappingProxyType
from typing import Mapping

from PHX2.stage23.constants import (
    DATA_STATUS_COMPLETE,
    FILTER_FAMILY_HOLDER_CONCENTRATION,
    LABEL_NORMAL,
)
from PHX2.stage23.models import (
    Stage23FilterInput,
    Stage23FilterResult,
    build_filter_result,
)


# A deterministic fixed clock string the tests inject so the
# Stage 23 records that carry ``created_at_utc`` produce stable
# fixtures. Mirrors the Stage 22 / Stage 21 injected-clock
# discipline.
FIXED_CLOCK_UTC: str = "2026-01-01T00:00:00Z"


def empty_payload_summary() -> Mapping[str, object]:
    return MappingProxyType({})


def make_filter_input(
    *,
    token_mint: str = "MintFixture111",
    provider_id: str = "fake_provider",
    event_id: str = "evt_abcdef0123456789abcdef01",
    captured_event_id: str = "captured_001",
    observed_at_utc: str = FIXED_CLOCK_UTC,
    slot: int = 1000,
    signature: str = "sig_fixture_001",
    payload_summary: Mapping[str, object] | None = None,
    missing_fields: tuple[str, ...] = (),
) -> Stage23FilterInput:
    """Build a synthetic ``Stage23FilterInput`` with safe defaults."""
    payload: Mapping[str, object]
    if payload_summary is None:
        payload = empty_payload_summary()
    else:
        payload = payload_summary
    return Stage23FilterInput(
        token_mint=token_mint,
        provider_id=provider_id,
        event_id=event_id,
        captured_event_id=captured_event_id,
        observed_at_utc=observed_at_utc,
        slot=slot,
        signature=signature,
        payload_summary=payload,
        missing_fields=missing_fields,
    )


def make_filter_result(
    *,
    filter_name: str = "fixture_filter",
    filter_family: str = FILTER_FAMILY_HOLDER_CONCENTRATION,
    filter_version: str = "fixture_filter_v1",
    threshold_version: str = "fixture_threshold_v1",
    label: str = LABEL_NORMAL,
    data_status: str = DATA_STATUS_COMPLETE,
    reason_codes: tuple[str, ...] = ("fixture_reason",),
    numeric_features: Mapping[str, object] | None = None,
    missing_features: tuple[str, ...] = (),
) -> Stage23FilterResult:
    """Build a synthetic ``Stage23FilterResult`` via the validated builder."""
    if numeric_features is None:
        numeric_features = MappingProxyType({"feature_a": 1.0})
    return build_filter_result(
        filter_name=filter_name,
        filter_family=filter_family,
        filter_version=filter_version,
        threshold_version=threshold_version,
        label=label,
        data_status=data_status,
        reason_codes=reason_codes,
        numeric_features=numeric_features,
        missing_features=missing_features,
    )


__all__ = [
    "FIXED_CLOCK_UTC",
    "empty_payload_summary",
    "make_filter_input",
    "make_filter_result",
]

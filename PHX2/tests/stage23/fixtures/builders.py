"""Synthetic Stage 23 test fixture builders.

These helpers build deterministic, secret-free synthetic
Stage23 records used by the Stage 23 test suite. No live
provider payloads are checked into the repository; the
fixtures are constructed from short non-secret literals.

The builders are intentionally simple wrappers around the
Stage 23 production model constructors so the test suite
exercises the same closed-set validation paths the production
filter implementations exercise.

Stage 23.2 adds the holder-snapshot payload-summary builders
used by the holder-concentration filter tests.

Stage 23.3 adds the launch-structure payload-summary builders
used by the launch-structure filter tests.
"""

from __future__ import annotations

from types import MappingProxyType
from typing import Mapping

from PHX2.stage23.constants import (
    DATA_STATUS_COMPLETE,
    FILTER_FAMILY_HOLDER_CONCENTRATION,
    LABEL_NORMAL,
)
from PHX2.stage23.holder_concentration import (
    HOLDER_PRIMITIVE_KIND_UNSUPPORTED,
    PAYLOAD_MARKER_HOLDER_PRIMITIVE_KIND,
    PRIMITIVE_CREATOR_RETAINED_PCT,
    PRIMITIVE_DEV_RELATED_RETAINED_PCT,
    PRIMITIVE_POOL_RELATED_PCT,
    PRIMITIVE_SNAPSHOT_AGE_SECONDS,
    PRIMITIVE_TOP_1_HOLDER_PCT,
    PRIMITIVE_TOP_5_HOLDER_PCT,
    PRIMITIVE_TOP_10_HOLDER_PCT,
    PRIMITIVE_TOP_20_HOLDER_PCT,
    PRIMITIVE_TOP_50_HOLDER_PCT,
    PRIMITIVE_UNIQUE_HOLDER_COUNT,
)
from PHX2.stage23.launch_structure import (
    LAUNCH_PRIMITIVE_KIND_UNSUPPORTED,
    PAYLOAD_MARKER_LAUNCH_PRIMITIVE_KIND,
    PRIMITIVE_BUYER_SOURCE_CLUSTER_COUNT,
    PRIMITIVE_FIRST_N_BUYERS_COUNT,
    PRIMITIVE_FIRST_N_EVENTS_OBSERVED,
    PRIMITIVE_FIRST_N_HOLDER_CONCENTRATION_PCT,
    PRIMITIVE_FIRST_N_UNIQUE_BUYERS,
    PRIMITIVE_FIRST_N_UNIQUE_FUNDERS,
    PRIMITIVE_LARGEST_BUYER_CLUSTER_PCT,
    PRIMITIVE_LARGEST_FUNDER_CLUSTER_PCT,
    PRIMITIVE_LAUNCH_SLOT,
    PRIMITIVE_LAUNCH_WINDOW_SECONDS,
    PRIMITIVE_NEAR_SLOT_BUYER_COUNT,
    PRIMITIVE_OBSERVED_SLOT_SPAN,
    PRIMITIVE_REPEATED_BUYER_WALLET_COUNT,
    PRIMITIVE_REPEATED_SOURCE_WALLET_COUNT,
    PRIMITIVE_SAME_SLOT_BUYER_COUNT,
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


# ---------------------------------------------------------------------------
# Holder-concentration synthetic snapshots (Stage 23.2)
# ---------------------------------------------------------------------------


def make_holder_payload_summary(
    *,
    unique_holder_count: int | None = 250,
    top_1_holder_pct: float | None = 0.05,
    top_5_holder_pct: float | None = 0.15,
    top_10_holder_pct: float | None = 0.22,
    top_20_holder_pct: float | None = 0.32,
    top_50_holder_pct: float | None = 0.50,
    creator_retained_pct: float | None = 0.05,
    dev_related_retained_pct: float | None = 0.05,
    pool_related_pct: float | None = 0.20,
    snapshot_age_seconds: float | None = 30.0,
    holder_primitive_kind: str | None = None,
) -> Mapping[str, object]:
    """Build a deterministic synthetic holder-snapshot payload_summary.

    Each primitive defaults to a value inside the
    ``NORMAL``-verdict band; tests override individual fields
    to exercise other labels. Pass ``None`` for a primitive to
    omit it from the payload (the filter then treats it as a
    missing primitive). Pass ``holder_primitive_kind`` to
    inject the optional unsupported-marker key.
    """
    pairs: tuple[tuple[str, object | None], ...] = (
        (PRIMITIVE_UNIQUE_HOLDER_COUNT, unique_holder_count),
        (PRIMITIVE_TOP_1_HOLDER_PCT, top_1_holder_pct),
        (PRIMITIVE_TOP_5_HOLDER_PCT, top_5_holder_pct),
        (PRIMITIVE_TOP_10_HOLDER_PCT, top_10_holder_pct),
        (PRIMITIVE_TOP_20_HOLDER_PCT, top_20_holder_pct),
        (PRIMITIVE_TOP_50_HOLDER_PCT, top_50_holder_pct),
        (PRIMITIVE_CREATOR_RETAINED_PCT, creator_retained_pct),
        (PRIMITIVE_DEV_RELATED_RETAINED_PCT, dev_related_retained_pct),
        (PRIMITIVE_POOL_RELATED_PCT, pool_related_pct),
        (PRIMITIVE_SNAPSHOT_AGE_SECONDS, snapshot_age_seconds),
    )
    body: dict[str, object] = {}
    for key, value in pairs:
        if value is None:
            continue
        body[key] = value
    if holder_primitive_kind is not None:
        body[PAYLOAD_MARKER_HOLDER_PRIMITIVE_KIND] = holder_primitive_kind
    return MappingProxyType(body)


def make_unsupported_holder_payload_summary() -> Mapping[str, object]:
    """Build a holder payload_summary marked unsupported.

    Some upstream sources may not be able to deliver holder
    primitives at all (token kind, chain, or provider doesn't
    support it). The marker is the locked
    ``HOLDER_PRIMITIVE_KIND_UNSUPPORTED`` token.
    """
    return MappingProxyType(
        {
            PAYLOAD_MARKER_HOLDER_PRIMITIVE_KIND: (
                HOLDER_PRIMITIVE_KIND_UNSUPPORTED
            ),
        }
    )


def make_holder_filter_input(
    *,
    payload_summary: Mapping[str, object] | None = None,
    token_mint: str = "MintFixture111",
    provider_id: str = "fake_provider",
    event_id: str = "evt_abcdef0123456789abcdef01",
    captured_event_id: str = "captured_holder_001",
    observed_at_utc: str = FIXED_CLOCK_UTC,
    slot: int = 1000,
    signature: str = "sig_holder_001",
    missing_fields: tuple[str, ...] = (),
) -> Stage23FilterInput:
    """Build a ``Stage23FilterInput`` carrying a holder payload_summary."""
    payload: Mapping[str, object]
    if payload_summary is None:
        payload = make_holder_payload_summary()
    else:
        payload = payload_summary
    return make_filter_input(
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


# ---------------------------------------------------------------------------
# Launch-structure synthetic snapshots (Stage 23.3)
# ---------------------------------------------------------------------------


def make_launch_payload_summary(
    *,
    first_n_buyers_count: int | None = 20,
    first_n_unique_buyers: int | None = 18,
    first_n_unique_funders: int | None = 15,
    same_slot_buyer_count: int | None = 1,
    near_slot_buyer_count: int | None = 2,
    buyer_source_cluster_count: int | None = 12,
    largest_buyer_cluster_pct: float | None = 0.10,
    largest_funder_cluster_pct: float | None = 0.10,
    first_n_holder_concentration_pct: float | None = 0.20,
    repeated_source_wallet_count: int | None = 0,
    repeated_buyer_wallet_count: int | None = 0,
    launch_window_seconds: float | None = 120.0,
    launch_slot: int | None = 1000,
    observed_slot_span: int | None = 60,
    first_n_events_observed: int | None = 20,
    launch_primitive_kind: str | None = None,
) -> Mapping[str, object]:
    """Build a deterministic synthetic launch-structure payload_summary.

    Each primitive defaults to a value inside the
    ``NORMAL``-verdict band; tests override individual fields
    to exercise other labels. Pass ``None`` for a primitive to
    omit it from the payload (the filter then treats it as a
    missing primitive). Pass ``launch_primitive_kind`` to
    inject the optional unsupported-marker key.
    """
    pairs: tuple[tuple[str, object | None], ...] = (
        (PRIMITIVE_FIRST_N_BUYERS_COUNT, first_n_buyers_count),
        (PRIMITIVE_FIRST_N_UNIQUE_BUYERS, first_n_unique_buyers),
        (PRIMITIVE_FIRST_N_UNIQUE_FUNDERS, first_n_unique_funders),
        (PRIMITIVE_SAME_SLOT_BUYER_COUNT, same_slot_buyer_count),
        (PRIMITIVE_NEAR_SLOT_BUYER_COUNT, near_slot_buyer_count),
        (PRIMITIVE_BUYER_SOURCE_CLUSTER_COUNT, buyer_source_cluster_count),
        (PRIMITIVE_LARGEST_BUYER_CLUSTER_PCT, largest_buyer_cluster_pct),
        (PRIMITIVE_LARGEST_FUNDER_CLUSTER_PCT, largest_funder_cluster_pct),
        (
            PRIMITIVE_FIRST_N_HOLDER_CONCENTRATION_PCT,
            first_n_holder_concentration_pct,
        ),
        (
            PRIMITIVE_REPEATED_SOURCE_WALLET_COUNT,
            repeated_source_wallet_count,
        ),
        (
            PRIMITIVE_REPEATED_BUYER_WALLET_COUNT,
            repeated_buyer_wallet_count,
        ),
        (PRIMITIVE_LAUNCH_WINDOW_SECONDS, launch_window_seconds),
        (PRIMITIVE_LAUNCH_SLOT, launch_slot),
        (PRIMITIVE_OBSERVED_SLOT_SPAN, observed_slot_span),
        (PRIMITIVE_FIRST_N_EVENTS_OBSERVED, first_n_events_observed),
    )
    body: dict[str, object] = {}
    for key, value in pairs:
        if value is None:
            continue
        body[key] = value
    if launch_primitive_kind is not None:
        body[PAYLOAD_MARKER_LAUNCH_PRIMITIVE_KIND] = launch_primitive_kind
    return MappingProxyType(body)


def make_unsupported_launch_payload_summary() -> Mapping[str, object]:
    """Build a launch payload_summary marked unsupported.

    Some upstream sources may not be able to deliver
    launch-structure primitives at all (chain, provider, or
    token kind doesn't support it). The marker is the locked
    ``LAUNCH_PRIMITIVE_KIND_UNSUPPORTED`` token.
    """
    return MappingProxyType(
        {
            PAYLOAD_MARKER_LAUNCH_PRIMITIVE_KIND: (
                LAUNCH_PRIMITIVE_KIND_UNSUPPORTED
            ),
        }
    )


def make_launch_filter_input(
    *,
    payload_summary: Mapping[str, object] | None = None,
    token_mint: str = "MintFixture111",
    provider_id: str = "fake_provider",
    event_id: str = "evt_abcdef0123456789abcdef01",
    captured_event_id: str = "captured_launch_001",
    observed_at_utc: str = FIXED_CLOCK_UTC,
    slot: int = 1000,
    signature: str = "sig_launch_001",
    missing_fields: tuple[str, ...] = (),
) -> Stage23FilterInput:
    """Build a ``Stage23FilterInput`` carrying a launch payload_summary."""
    payload: Mapping[str, object]
    if payload_summary is None:
        payload = make_launch_payload_summary()
    else:
        payload = payload_summary
    return make_filter_input(
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


__all__ = [
    "FIXED_CLOCK_UTC",
    "empty_payload_summary",
    "make_filter_input",
    "make_filter_result",
    "make_holder_filter_input",
    "make_holder_payload_summary",
    "make_launch_filter_input",
    "make_launch_payload_summary",
    "make_unsupported_holder_payload_summary",
    "make_unsupported_launch_payload_summary",
]

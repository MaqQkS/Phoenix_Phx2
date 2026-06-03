"""Stage 30.11.5 live wiring models tests.

Pins the passive Stage 30.11.5 model layer: the minor / schema version, the
closed-set assembly-decision / assembly-reason / transport-status vocabularies +
their predicates, the projection field names (required / optional / all), the
model field-name shapes, the hard bounded-run caps + defaults, the fake-wiring
proof baseline counts, the ``is_nonblank_str`` helper, and the immutability of
the carriers. Asserts the models embed only safe scalars + the committed Stage
30.11.1 snapshot type (no secret / payload / host / transport field).

Fake / offline only. No live call, no provider, no Discord, no env read.
"""

from __future__ import annotations

import dataclasses
from decimal import Decimal

import pytest

from PHX2.stage30.stage30_11_1_live_candidate_bridge_models import (
    Stage30_11LiveCandidateSnapshot,
)
from PHX2.stage30.stage30_11_5_live_wiring_models import (
    ASSEMBLY_DECISION_ASSEMBLED,
    ASSEMBLY_DECISION_REJECTED_INVALID_SHAPE,
    ASSEMBLY_DECISION_REJECTED_MISSING_FIELD,
    ASSEMBLY_REASON_INVALID_FIELD_SHAPE,
    ASSEMBLY_REASON_MISSING_REQUIRED_FIELD,
    ASSEMBLY_REASON_READY_FOR_BRIDGE,
    STAGE30_11_5_ASSEMBLY_DECISIONS,
    STAGE30_11_5_ASSEMBLY_PASS_DECISION,
    STAGE30_11_5_ASSEMBLY_PASS_REASON,
    STAGE30_11_5_ASSEMBLY_REASONS,
    STAGE30_11_5_DEFAULT_MAX_CANDIDATES,
    STAGE30_11_5_DEFAULT_MAX_DISPATCHES,
    STAGE30_11_5_DEFAULT_MAX_RUNTIME_SECONDS,
    STAGE30_11_5_EXPECTED_ASSEMBLED,
    STAGE30_11_5_EXPECTED_ASSEMBLY_REJECTED,
    STAGE30_11_5_EXPECTED_BRIDGED,
    STAGE30_11_5_EXPECTED_CANDIDATES_SEEN,
    STAGE30_11_5_EXPECTED_DIP_CANDIDATE_ID,
    STAGE30_11_5_EXPECTED_DIP_TOKEN_MINT,
    STAGE30_11_5_EXPECTED_DISPATCH_ACCEPTED,
    STAGE30_11_5_EXPECTED_DISPATCH_ATTEMPTED,
    STAGE30_11_5_EXPECTED_GATE_PASSED,
    STAGE30_11_5_EXPECTED_SOURCE_ITEMS_SEEN,
    STAGE30_11_5_EXPECTED_SUPPRESSED_BY_BRIDGE,
    STAGE30_11_5_EXPECTED_SUPPRESSED_BY_GATE,
    STAGE30_11_5_EXPECTED_TRANSPORT_ACCEPTS,
    STAGE30_11_5_EXPECTED_TRANSPORT_ATTEMPTS,
    STAGE30_11_5_LIVE_WIRING_SCHEMA_VERSION,
    STAGE30_11_5_MAX_CANDIDATES_HARD_CAP,
    STAGE30_11_5_MAX_DISPATCHES_HARD_CAP,
    STAGE30_11_5_MAX_RUNTIME_SECONDS_HARD_CAP,
    STAGE30_11_5_MINOR_VERSION,
    STAGE30_11_5_OPTIONAL_PROJECTION_FIELDS,
    STAGE30_11_5_PROJECTION_FIELDS,
    STAGE30_11_5_REQUIRED_PROJECTION_FIELDS,
    STAGE30_11_5_SOURCE_STAGE,
    STAGE30_11_5_TRANSPORT_ACCEPT_STATUS,
    STAGE30_11_5_TRANSPORT_STATUSES,
    TRANSPORT_STATUS_REJECTED,
    TRANSPORT_STATUS_WOULD_DELIVER,
    Stage30_11_5BoundedRunResult,
    Stage30_11_5BoundedRunSummary,
    Stage30_11_5LiveCandidateAssemblyResult,
    Stage30_11_5PrivateOperatorPayload,
    Stage30_11_5TransportClientResult,
    bounded_run_result_field_names,
    bounded_run_summary_field_names,
    is_assembly_decision,
    is_assembly_reason,
    is_nonblank_str,
    is_transport_status,
    live_candidate_assembly_result_field_names,
    private_operator_payload_field_names,
    transport_client_result_field_names,
)


# ---------------------------------------------------------------------------
# Versions
# ---------------------------------------------------------------------------


def test_minor_and_schema_versions_pinned() -> None:
    assert STAGE30_11_5_MINOR_VERSION == "30.11.5"
    assert STAGE30_11_5_LIVE_WIRING_SCHEMA_VERSION == "stage30_11_5_v0_live_wiring"
    assert STAGE30_11_5_SOURCE_STAGE == "30.11.5"


# ---------------------------------------------------------------------------
# Closed-set vocabularies + predicates
# ---------------------------------------------------------------------------


def test_assembly_decisions_pinned() -> None:
    assert STAGE30_11_5_ASSEMBLY_DECISIONS == (
        "ASSEMBLED_LIVE_CANDIDATE_SNAPSHOT",
        "REJECTED_MISSING_REQUIRED_FIELD",
        "REJECTED_INVALID_FIELD_SHAPE",
    )
    assert STAGE30_11_5_ASSEMBLY_PASS_DECISION == ASSEMBLY_DECISION_ASSEMBLED
    assert len(set(STAGE30_11_5_ASSEMBLY_DECISIONS)) == 3
    for decision in STAGE30_11_5_ASSEMBLY_DECISIONS:
        assert is_assembly_decision(decision)
    for nope in ("", "ASSEMBLED", "nope", None, 1):
        assert not is_assembly_decision(nope)


def test_assembly_reasons_pinned() -> None:
    assert STAGE30_11_5_ASSEMBLY_REASONS == (
        "READY_FOR_BRIDGE",
        "MISSING_REQUIRED_CANDIDATE_FIELD",
        "INVALID_CANDIDATE_FIELD_SHAPE",
    )
    assert STAGE30_11_5_ASSEMBLY_PASS_REASON == ASSEMBLY_REASON_READY_FOR_BRIDGE
    for reason in STAGE30_11_5_ASSEMBLY_REASONS:
        assert is_assembly_reason(reason)
    for nope in ("", "READY", None, 0):
        assert not is_assembly_reason(nope)


def test_assembly_token_aliases_match_tuples() -> None:
    assert ASSEMBLY_DECISION_ASSEMBLED in STAGE30_11_5_ASSEMBLY_DECISIONS
    assert ASSEMBLY_DECISION_REJECTED_MISSING_FIELD in (
        STAGE30_11_5_ASSEMBLY_DECISIONS
    )
    assert ASSEMBLY_DECISION_REJECTED_INVALID_SHAPE in (
        STAGE30_11_5_ASSEMBLY_DECISIONS
    )
    assert ASSEMBLY_REASON_MISSING_REQUIRED_FIELD in STAGE30_11_5_ASSEMBLY_REASONS
    assert ASSEMBLY_REASON_INVALID_FIELD_SHAPE in STAGE30_11_5_ASSEMBLY_REASONS


def test_transport_statuses_pinned() -> None:
    assert STAGE30_11_5_TRANSPORT_STATUSES == (
        "WOULD_DELIVER_PRIVATE_OPERATOR_MESSAGE",
        "TRANSPORT_REJECTED",
    )
    assert STAGE30_11_5_TRANSPORT_ACCEPT_STATUS == TRANSPORT_STATUS_WOULD_DELIVER
    assert TRANSPORT_STATUS_REJECTED in STAGE30_11_5_TRANSPORT_STATUSES
    for status in STAGE30_11_5_TRANSPORT_STATUSES:
        assert is_transport_status(status)
    for nope in ("", "SENT", None, 2):
        assert not is_transport_status(nope)


# ---------------------------------------------------------------------------
# Projection field names
# ---------------------------------------------------------------------------


def test_projection_fields_match_snapshot_fields() -> None:
    snapshot_fields = tuple(
        f.name for f in dataclasses.fields(Stage30_11LiveCandidateSnapshot)
    )
    # The projection the assembler reads FROM is keyed by the snapshot fields.
    assert STAGE30_11_5_PROJECTION_FIELDS == snapshot_fields


def test_required_plus_optional_partition_projection_fields() -> None:
    assert set(STAGE30_11_5_REQUIRED_PROJECTION_FIELDS).isdisjoint(
        set(STAGE30_11_5_OPTIONAL_PROJECTION_FIELDS)
    )
    assert set(STAGE30_11_5_REQUIRED_PROJECTION_FIELDS) | set(
        STAGE30_11_5_OPTIONAL_PROJECTION_FIELDS
    ) == set(STAGE30_11_5_PROJECTION_FIELDS)
    assert STAGE30_11_5_OPTIONAL_PROJECTION_FIELDS == (
        "post_migration_ath_verified",
        "source_ref",
    )
    # The required set covers the pair / price / ATH / migration / drawdown / tier
    # fields the slice fails closed on.
    for field in (
        "pair_type",
        "current_market_cap_usd",
        "ath_status",
        "migration_status",
        "drawdown_from_ath",
        "tier_hint",
    ):
        assert field in STAGE30_11_5_REQUIRED_PROJECTION_FIELDS


# ---------------------------------------------------------------------------
# Model field-name shapes
# ---------------------------------------------------------------------------


def test_model_field_names_pinned() -> None:
    assert live_candidate_assembly_result_field_names() == (
        "candidate_id",
        "token_mint",
        "assembly_decision",
        "assembly_reason",
        "rejected_field",
        "snapshot",
        "created_at_utc",
    )
    assert private_operator_payload_field_names() == (
        "candidate_id",
        "token_mint",
        "candidate_ref",
        "tier_token",
        "body",
        "source_stage",
        "created_at_utc",
    )
    assert transport_client_result_field_names() == (
        "accepted",
        "transport_status",
        "candidate_id",
        "token_mint",
        "created_at_utc",
    )
    assert bounded_run_summary_field_names() == (
        "source_items_seen",
        "assembled",
        "assembly_rejected",
        "candidates_seen",
        "bridged",
        "gate_passed",
        "dispatch_attempted",
        "dispatch_accepted",
        "suppressed_by_bridge",
        "suppressed_by_gate",
        "stopped_by_candidate_cap",
        "stopped_by_dispatch_cap",
        "stopped_by_runtime_seconds",
        "created_at_utc",
    )
    assert bounded_run_result_field_names() == (
        "assembly_outcomes",
        "runtime_outcomes",
        "summary",
        "created_at_utc",
    )


def test_no_secret_or_payload_field_names() -> None:
    all_fields = (
        live_candidate_assembly_result_field_names()
        + private_operator_payload_field_names()
        + transport_client_result_field_names()
        + bounded_run_summary_field_names()
        + bounded_run_result_field_names()
    )
    for name in all_fields:
        lower = name.lower()
        for forbidden in (
            "webhook",
            "api_key",
            "bearer",
            "authorization",
            "secret",
            "raw_payload",
            "getenv",
            "environ",
            "url",
            "host",
        ):
            assert forbidden not in lower, (
                f"Stage 30.11.5 field {name!r} carries forbidden substring "
                f"{forbidden!r}"
            )


# ---------------------------------------------------------------------------
# Hard caps + defaults
# ---------------------------------------------------------------------------


def test_hard_caps_and_defaults_pinned() -> None:
    assert STAGE30_11_5_MAX_DISPATCHES_HARD_CAP == 1
    assert STAGE30_11_5_MAX_RUNTIME_SECONDS_HARD_CAP == Decimal(60)
    assert STAGE30_11_5_MAX_CANDIDATES_HARD_CAP == 10
    assert STAGE30_11_5_DEFAULT_MAX_DISPATCHES == 1
    assert STAGE30_11_5_DEFAULT_MAX_RUNTIME_SECONDS == Decimal(60)
    assert STAGE30_11_5_DEFAULT_MAX_CANDIDATES == 10
    # The single-send default never exceeds the hard cap.
    assert STAGE30_11_5_DEFAULT_MAX_DISPATCHES <= STAGE30_11_5_MAX_DISPATCHES_HARD_CAP
    assert (
        STAGE30_11_5_DEFAULT_MAX_RUNTIME_SECONDS
        <= STAGE30_11_5_MAX_RUNTIME_SECONDS_HARD_CAP
    )
    assert STAGE30_11_5_DEFAULT_MAX_CANDIDATES <= STAGE30_11_5_MAX_CANDIDATES_HARD_CAP


# ---------------------------------------------------------------------------
# Fake-wiring proof baseline
# ---------------------------------------------------------------------------


def test_expected_baseline_counts_pinned() -> None:
    assert STAGE30_11_5_EXPECTED_SOURCE_ITEMS_SEEN == 4
    assert STAGE30_11_5_EXPECTED_ASSEMBLED == 3
    assert STAGE30_11_5_EXPECTED_ASSEMBLY_REJECTED == 1
    assert STAGE30_11_5_EXPECTED_CANDIDATES_SEEN == 3
    assert STAGE30_11_5_EXPECTED_BRIDGED == 2
    assert STAGE30_11_5_EXPECTED_GATE_PASSED == 1
    assert STAGE30_11_5_EXPECTED_DISPATCH_ATTEMPTED == 1
    assert STAGE30_11_5_EXPECTED_DISPATCH_ACCEPTED == 1
    assert STAGE30_11_5_EXPECTED_SUPPRESSED_BY_BRIDGE == 1
    assert STAGE30_11_5_EXPECTED_SUPPRESSED_BY_GATE == 1
    assert STAGE30_11_5_EXPECTED_TRANSPORT_ATTEMPTS == 1
    assert STAGE30_11_5_EXPECTED_TRANSPORT_ACCEPTS == 1
    assert STAGE30_11_5_EXPECTED_DIP_CANDIDATE_ID == "cand-tier1"
    assert STAGE30_11_5_EXPECTED_DIP_TOKEN_MINT == "mint-tier1"
    # The assembled + rejected partition the source; the dip is the only
    # transport attempt.
    assert (
        STAGE30_11_5_EXPECTED_ASSEMBLED + STAGE30_11_5_EXPECTED_ASSEMBLY_REJECTED
        == STAGE30_11_5_EXPECTED_SOURCE_ITEMS_SEEN
    )
    assert STAGE30_11_5_EXPECTED_TRANSPORT_ATTEMPTS == (
        STAGE30_11_5_EXPECTED_GATE_PASSED
    )


# ---------------------------------------------------------------------------
# Helper + immutability
# ---------------------------------------------------------------------------


def test_is_nonblank_str() -> None:
    assert is_nonblank_str("x")
    assert is_nonblank_str(" a ")
    for nope in ("", "   ", None, 0, b"x", []):
        assert not is_nonblank_str(nope)


def test_models_are_frozen() -> None:
    payload = Stage30_11_5PrivateOperatorPayload(
        candidate_id="c",
        token_mint="m",
        candidate_ref=None,
        tier_token="Tier 1",
        body="b",
        source_stage="30.11.5",
        created_at_utc="2026-01-01T00:00:00Z",
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        payload.body = "other"  # type: ignore[misc]

    result = Stage30_11_5TransportClientResult(
        accepted=True,
        transport_status=TRANSPORT_STATUS_WOULD_DELIVER,
        candidate_id="c",
        token_mint="m",
        created_at_utc="2026-01-01T00:00:00Z",
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.accepted = False  # type: ignore[misc]


def test_assembly_result_carries_snapshot_type() -> None:
    # The assembly result embeds the committed Stage 30.11.1 snapshot type.
    field_types = {
        f.name: f.type
        for f in dataclasses.fields(Stage30_11_5LiveCandidateAssemblyResult)
    }
    assert "snapshot" in field_types
    # The bounded-run carriers are well-formed dataclasses.
    assert dataclasses.is_dataclass(Stage30_11_5BoundedRunSummary)
    assert dataclasses.is_dataclass(Stage30_11_5BoundedRunResult)

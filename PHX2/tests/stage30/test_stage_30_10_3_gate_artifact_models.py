"""Stage 30.10.3 gate artifact models tests.

Covers the immutable / frozen gate artifact record + batch + in-memory sink
result models, the pinned artifact schema version, the caller-injected
``created_at_utc``, the pinned field names, and that no model field carries a
secret- / env- / payload-class name.

Pure / offline; no filesystem, no env, no network, no Discord, no wall clock.
"""

from __future__ import annotations

import dataclasses

import pytest

from PHX2.stage30.stage30_10_3_gate_artifact_models import (
    STAGE30_10_3_ARTIFACT_SCHEMA_VERSION,
    STAGE30_10_3_MINOR_VERSION,
    Stage30_10GateArtifactBatch,
    Stage30_10GateArtifactRecord,
    Stage30_10GateArtifactSinkResult,
    gate_artifact_batch_field_names,
    gate_artifact_record_field_names,
    gate_artifact_sink_result_field_names,
)


_SAFE_CREATED_AT = "2026-01-01T00:00:00Z"


def _record(**overrides) -> Stage30_10GateArtifactRecord:
    base = dict(
        proof_id="proof-1",
        candidate_id="cand-1",
        token_mint="mint-1",
        eligibility_decision="ELIGIBLE_DIP",
        eligibility_reason="TIER_ALLOWED",
        gate_decision="PASS_TO_DISPATCH",
        gate_reason="ELIGIBLE_DIP",
        send_allowed=True,
        dispatch_reservation_would_be_attempted=True,
        suppressed_before_dispatch_reservation=False,
        dispatch_failure_recorded=False,
        transport_veto_used=False,
        payload_refused_used=False,
        created_at_utc=_SAFE_CREATED_AT,
    )
    base.update(overrides)
    return Stage30_10GateArtifactRecord(**base)


def _batch(**overrides) -> Stage30_10GateArtifactBatch:
    base = dict(
        proof_id="proof-1",
        records=(_record(),),
        candidates_seen=1,
        candidates_passed=1,
        candidates_skipped=0,
        invalid_inputs=0,
        dispatch_attempts_reserved=1,
        dispatch_attempts_suppressed_before_reservation=0,
        dispatch_failures_recorded=0,
        transport_veto_count=0,
        payload_refused_count=0,
        created_at_utc=_SAFE_CREATED_AT,
    )
    base.update(overrides)
    return Stage30_10GateArtifactBatch(**base)


def _sink_result(**overrides) -> Stage30_10GateArtifactSinkResult:
    base = dict(
        proof_id="proof-1",
        records_written=1,
        batch_written=True,
        artifact_schema_version=STAGE30_10_3_ARTIFACT_SCHEMA_VERSION,
        created_at_utc=_SAFE_CREATED_AT,
    )
    base.update(overrides)
    return Stage30_10GateArtifactSinkResult(**base)


# ---------------------------------------------------------------------------
# 1. Version + schema identity
# ---------------------------------------------------------------------------


def test_minor_version_pinned() -> None:
    assert STAGE30_10_3_MINOR_VERSION == "30.10.3"


def test_artifact_schema_version_pinned() -> None:
    assert STAGE30_10_3_ARTIFACT_SCHEMA_VERSION == (
        "stage30_10_v0_gate_artifact"
    )


# ---------------------------------------------------------------------------
# 2. Models are immutable / frozen
# ---------------------------------------------------------------------------


def test_record_is_frozen() -> None:
    rec = _record()
    with pytest.raises(dataclasses.FrozenInstanceError):
        rec.gate_decision = "SKIP_BEFORE_DISPATCH"  # type: ignore[misc]


def test_batch_is_frozen() -> None:
    batch = _batch()
    with pytest.raises(dataclasses.FrozenInstanceError):
        batch.candidates_passed = 0  # type: ignore[misc]


def test_sink_result_is_frozen() -> None:
    result = _sink_result()
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.records_written = 0  # type: ignore[misc]


# ---------------------------------------------------------------------------
# 3. created_at_utc is caller-injected and echoed verbatim
# ---------------------------------------------------------------------------


def test_created_at_utc_is_caller_injected() -> None:
    assert _record(created_at_utc="2026-05-31T12:34:56Z").created_at_utc == (
        "2026-05-31T12:34:56Z"
    )
    assert _batch(created_at_utc="2026-05-31T12:34:56Z").created_at_utc == (
        "2026-05-31T12:34:56Z"
    )
    assert _sink_result(
        created_at_utc="2026-05-31T12:34:56Z"
    ).created_at_utc == "2026-05-31T12:34:56Z"


# ---------------------------------------------------------------------------
# 4. Dispatch / transport flags are real booleans + the negatives default off
# ---------------------------------------------------------------------------


def test_record_dispatch_flags_are_booleans() -> None:
    rec = _record()
    for value in (
        rec.send_allowed,
        rec.dispatch_reservation_would_be_attempted,
        rec.suppressed_before_dispatch_reservation,
        rec.dispatch_failure_recorded,
        rec.transport_veto_used,
        rec.payload_refused_used,
    ):
        assert isinstance(value, bool)


def test_batch_counts_are_ints() -> None:
    batch = _batch()
    for value in (
        batch.candidates_seen,
        batch.candidates_passed,
        batch.candidates_skipped,
        batch.invalid_inputs,
        batch.dispatch_attempts_reserved,
        batch.dispatch_attempts_suppressed_before_reservation,
        batch.dispatch_failures_recorded,
        batch.transport_veto_count,
        batch.payload_refused_count,
    ):
        assert isinstance(value, int)


def test_batch_records_is_a_tuple_of_records() -> None:
    batch = _batch(records=(_record(), _record(candidate_id="cand-2")))
    assert isinstance(batch.records, tuple)
    assert all(
        isinstance(r, Stage30_10GateArtifactRecord) for r in batch.records
    )


def test_sink_result_pins_schema_version() -> None:
    assert _sink_result().artifact_schema_version == (
        STAGE30_10_3_ARTIFACT_SCHEMA_VERSION
    )


# ---------------------------------------------------------------------------
# 5. Field-name helpers pinned + no secret / env / payload field names
# ---------------------------------------------------------------------------


def test_record_field_names_pinned() -> None:
    assert gate_artifact_record_field_names() == (
        "proof_id",
        "candidate_id",
        "token_mint",
        "eligibility_decision",
        "eligibility_reason",
        "gate_decision",
        "gate_reason",
        "send_allowed",
        "dispatch_reservation_would_be_attempted",
        "suppressed_before_dispatch_reservation",
        "dispatch_failure_recorded",
        "transport_veto_used",
        "payload_refused_used",
        "created_at_utc",
    )


def test_batch_field_names_pinned() -> None:
    assert gate_artifact_batch_field_names() == (
        "proof_id",
        "records",
        "candidates_seen",
        "candidates_passed",
        "candidates_skipped",
        "invalid_inputs",
        "dispatch_attempts_reserved",
        "dispatch_attempts_suppressed_before_reservation",
        "dispatch_failures_recorded",
        "transport_veto_count",
        "payload_refused_count",
        "created_at_utc",
    )


def test_sink_result_field_names_pinned() -> None:
    assert gate_artifact_sink_result_field_names() == (
        "proof_id",
        "records_written",
        "batch_written",
        "artifact_schema_version",
        "created_at_utc",
    )


_FORBIDDEN_FIELD_SUBSTRINGS = (
    "webhook",
    "api_key",
    "apikey",
    "bearer",
    "authorization",
    "secret",
    "password",
    "private_key",
    "privatekey",
    "mnemonic",
    "seed_phrase",
    "credential",
    "raw_payload",
    "getenv",
    "environ",
    "host",
    "endpoint",
    "url",
)


def test_no_secret_or_env_field_names() -> None:
    all_fields = (
        gate_artifact_record_field_names()
        + gate_artifact_batch_field_names()
        + gate_artifact_sink_result_field_names()
    )
    for name in all_fields:
        lower = name.lower()
        for forbidden in _FORBIDDEN_FIELD_SUBSTRINGS:
            assert forbidden not in lower, (
                f"Stage 30.10.3 model field {name!r} carries a forbidden "
                f"secret / env / payload substring {forbidden!r}"
            )

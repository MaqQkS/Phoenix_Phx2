"""Stage 30.9.2_RESUME dip-filtered live proof models tests.

Covers the immutable / frozen resume plan + per-candidate proof record +
resume proof summary models, the pinned minor version + resume id + resume
schema version + prior stage + required gate stack, the caller-injected
``created_at_utc``, the pinned field names, the planning-only gating-flag
defaults, and that no model field carries a secret- / env- / payload-class
name.

Pure / offline; no filesystem, no env, no network, no Discord, no wall clock.
"""

from __future__ import annotations

import dataclasses

import pytest

from PHX2.stage30.stage30_9_2_resume_dip_filtered_live_models import (
    STAGE30_9_2_GATE_STACK_REQUIRED,
    STAGE30_9_2_MINOR_VERSION,
    STAGE30_9_2_PRIOR_STAGE,
    STAGE30_9_2_RESUME_ID,
    STAGE30_9_2_RESUME_PROOF_SCHEMA_VERSION,
    Stage30_9_2DipFilteredCandidateProofRecord,
    Stage30_9_2DipFilteredResumePlan,
    Stage30_9_2DipFilteredResumeProofSummary,
    candidate_proof_record_field_names,
    resume_plan_field_names,
    resume_proof_summary_field_names,
)


_SAFE_CREATED_AT = "2026-01-01T00:00:00Z"


def _plan(**overrides) -> Stage30_9_2DipFilteredResumePlan:
    base = dict(
        resume_id=STAGE30_9_2_RESUME_ID,
        required_head_sha="e35e54b69668814d2ab8c096855f682c68ada8ab",
        prior_stage=STAGE30_9_2_PRIOR_STAGE,
        gate_stack_required=STAGE30_9_2_GATE_STACK_REQUIRED,
        live_allowed=False,
        dispatch_allowed=False,
        env_read_allowed=False,
        provider_call_allowed=False,
        discord_send_allowed=False,
        created_at_utc=_SAFE_CREATED_AT,
    )
    base.update(overrides)
    return Stage30_9_2DipFilteredResumePlan(**base)


def _record(**overrides) -> Stage30_9_2DipFilteredCandidateProofRecord:
    base = dict(
        candidate_id="cand-1",
        token_mint="mint-1",
        eligibility_decision="ELIGIBLE_DIP",
        eligibility_reason="TIER_ALLOWED",
        gate_decision="PASS_TO_DISPATCH",
        gate_reason="ELIGIBLE_DIP",
        artifact_schema_version="stage30_10_v0_gate_artifact",
        dispatch_reservation_would_be_attempted=True,
        suppressed_before_dispatch_reservation=False,
        dispatch_failure_recorded=False,
        transport_veto_used=False,
        payload_refused_used=False,
        created_at_utc=_SAFE_CREATED_AT,
    )
    base.update(overrides)
    return Stage30_9_2DipFilteredCandidateProofRecord(**base)


def _summary(**overrides) -> Stage30_9_2DipFilteredResumeProofSummary:
    base = dict(
        resume_id=STAGE30_9_2_RESUME_ID,
        candidates_seen=9,
        candidates_passed=3,
        candidates_skipped=5,
        invalid_inputs=1,
        dispatch_attempts_reserved=3,
        dispatch_attempts_suppressed_before_reservation=6,
        dispatch_failures_recorded=0,
        transport_veto_count=0,
        payload_refused_count=0,
        live_allowed=False,
        provider_call_allowed=False,
        discord_send_allowed=False,
        created_at_utc=_SAFE_CREATED_AT,
    )
    base.update(overrides)
    return Stage30_9_2DipFilteredResumeProofSummary(**base)


# ---------------------------------------------------------------------------
# 1. Version + resume identity
# ---------------------------------------------------------------------------


def test_minor_version_pinned() -> None:
    assert STAGE30_9_2_MINOR_VERSION == "30.9.2"


def test_resume_id_pinned() -> None:
    assert STAGE30_9_2_RESUME_ID == "30.9.2_RESUME"


def test_resume_proof_schema_version_pinned() -> None:
    assert STAGE30_9_2_RESUME_PROOF_SCHEMA_VERSION == (
        "stage30_9_2_v0_dip_filtered_resume_proof"
    )


def test_prior_stage_pinned() -> None:
    assert STAGE30_9_2_PRIOR_STAGE == "30.10.3"


def test_required_gate_stack_pinned() -> None:
    assert STAGE30_9_2_GATE_STACK_REQUIRED == (
        "30.10.1 offline tier-dip eligibility classifier",
        "30.10.2 optional pre-dispatch tier-dip gate",
        "30.10.3 gate artifact projection",
    )


# ---------------------------------------------------------------------------
# 2. Models are immutable / frozen
# ---------------------------------------------------------------------------


def test_plan_is_frozen() -> None:
    plan = _plan()
    with pytest.raises(dataclasses.FrozenInstanceError):
        plan.live_allowed = True  # type: ignore[misc]


def test_record_is_frozen() -> None:
    rec = _record()
    with pytest.raises(dataclasses.FrozenInstanceError):
        rec.gate_decision = "SKIP_BEFORE_DISPATCH"  # type: ignore[misc]


def test_summary_is_frozen() -> None:
    summary = _summary()
    with pytest.raises(dataclasses.FrozenInstanceError):
        summary.candidates_passed = 0  # type: ignore[misc]


# ---------------------------------------------------------------------------
# 3. created_at_utc is caller-injected and echoed verbatim
# ---------------------------------------------------------------------------


def test_created_at_utc_is_caller_injected() -> None:
    assert _plan(created_at_utc="2026-05-31T12:34:56Z").created_at_utc == (
        "2026-05-31T12:34:56Z"
    )
    assert _record(created_at_utc="2026-05-31T12:34:56Z").created_at_utc == (
        "2026-05-31T12:34:56Z"
    )
    assert _summary(
        created_at_utc="2026-05-31T12:34:56Z"
    ).created_at_utc == "2026-05-31T12:34:56Z"


# ---------------------------------------------------------------------------
# 4. Planning gating flags + dispatch flags are real booleans
# ---------------------------------------------------------------------------


def test_plan_gating_flags_are_booleans_and_default_false() -> None:
    plan = _plan()
    for value in (
        plan.live_allowed,
        plan.dispatch_allowed,
        plan.env_read_allowed,
        plan.provider_call_allowed,
        plan.discord_send_allowed,
    ):
        assert isinstance(value, bool)
        assert value is False


def test_record_dispatch_flags_are_booleans() -> None:
    rec = _record()
    for value in (
        rec.dispatch_reservation_would_be_attempted,
        rec.suppressed_before_dispatch_reservation,
        rec.dispatch_failure_recorded,
        rec.transport_veto_used,
        rec.payload_refused_used,
    ):
        assert isinstance(value, bool)


def test_record_transport_safety_negatives_default_false() -> None:
    rec = _record()
    assert rec.dispatch_failure_recorded is False
    assert rec.transport_veto_used is False
    assert rec.payload_refused_used is False


def test_summary_counts_are_ints_and_gating_flags_false() -> None:
    summary = _summary()
    for value in (
        summary.candidates_seen,
        summary.candidates_passed,
        summary.candidates_skipped,
        summary.invalid_inputs,
        summary.dispatch_attempts_reserved,
        summary.dispatch_attempts_suppressed_before_reservation,
        summary.dispatch_failures_recorded,
        summary.transport_veto_count,
        summary.payload_refused_count,
    ):
        assert isinstance(value, int)
    for flag in (
        summary.live_allowed,
        summary.provider_call_allowed,
        summary.discord_send_allowed,
    ):
        assert isinstance(flag, bool)
        assert flag is False


def test_plan_gate_stack_required_is_a_tuple() -> None:
    plan = _plan()
    assert isinstance(plan.gate_stack_required, tuple)
    assert plan.gate_stack_required == STAGE30_9_2_GATE_STACK_REQUIRED


# ---------------------------------------------------------------------------
# 5. Field-name helpers pinned
# ---------------------------------------------------------------------------


def test_resume_plan_field_names_pinned() -> None:
    assert resume_plan_field_names() == (
        "resume_id",
        "required_head_sha",
        "prior_stage",
        "gate_stack_required",
        "live_allowed",
        "dispatch_allowed",
        "env_read_allowed",
        "provider_call_allowed",
        "discord_send_allowed",
        "created_at_utc",
    )


def test_candidate_proof_record_field_names_pinned() -> None:
    assert candidate_proof_record_field_names() == (
        "candidate_id",
        "token_mint",
        "eligibility_decision",
        "eligibility_reason",
        "gate_decision",
        "gate_reason",
        "artifact_schema_version",
        "dispatch_reservation_would_be_attempted",
        "suppressed_before_dispatch_reservation",
        "dispatch_failure_recorded",
        "transport_veto_used",
        "payload_refused_used",
        "created_at_utc",
    )


def test_resume_proof_summary_field_names_pinned() -> None:
    assert resume_proof_summary_field_names() == (
        "resume_id",
        "candidates_seen",
        "candidates_passed",
        "candidates_skipped",
        "invalid_inputs",
        "dispatch_attempts_reserved",
        "dispatch_attempts_suppressed_before_reservation",
        "dispatch_failures_recorded",
        "transport_veto_count",
        "payload_refused_count",
        "live_allowed",
        "provider_call_allowed",
        "discord_send_allowed",
        "created_at_utc",
    )


# ---------------------------------------------------------------------------
# 6. No secret / env / payload field names
# ---------------------------------------------------------------------------


_FORBIDDEN_FIELD_SUBSTRINGS = (
    "webhook",
    "api_key",
    "apikey",
    "bearer",
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
        resume_plan_field_names()
        + candidate_proof_record_field_names()
        + resume_proof_summary_field_names()
    )
    for name in all_fields:
        lower = name.lower()
        for forbidden in _FORBIDDEN_FIELD_SUBSTRINGS:
            assert forbidden not in lower, (
                f"Stage 30.9.2 model field {name!r} carries a forbidden "
                f"secret / env / payload substring {forbidden!r}"
            )

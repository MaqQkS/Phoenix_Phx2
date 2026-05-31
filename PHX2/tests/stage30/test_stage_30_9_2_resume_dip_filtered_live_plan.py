"""Stage 30.9.2_RESUME dip-filtered live proof plan tests.

Proves the resume plan builder produces the locked planning-only plan:

  * it names the required Stage 30.10 dip-gate stack (30.10.1 classifier +
    30.10.2 pre-dispatch gate + 30.10.3 artifact projection);
  * it holds EVERY live-affecting axis closed (live / dispatch / env-read /
    provider-call / Discord-send all False);
  * it does NOT auto-run live;
  * the next action is an explicit operator-authorized live ceremony, never an
    automatic live execution and never a Stage 30.10.4;
  * ``required_head_sha`` / ``created_at_utc`` are caller-injectable; and
  * the plan is deterministic.

Pure / offline; no filesystem, no env, no network, no Discord, no wall clock.
"""

from __future__ import annotations

import dataclasses

from PHX2.stage30.stage30_9_2_resume_dip_filtered_live_models import (
    STAGE30_9_2_GATE_STACK_REQUIRED,
    STAGE30_9_2_PRIOR_STAGE,
    STAGE30_9_2_RESUME_ID,
    Stage30_9_2DipFilteredResumePlan,
)
from PHX2.stage30.stage30_9_2_resume_dip_filtered_live_plan import (
    STAGE30_9_2_DEFAULT_PLAN_CREATED_AT,
    STAGE30_9_2_LIVE_CEREMONY_REQUIRES_OPERATOR_AUTH,
    STAGE30_9_2_NEXT_ACTION,
    STAGE30_9_2_REQUIRED_HEAD_SHA,
    build_dip_filtered_resume_plan,
    resume_plan_allows_live,
    resume_plan_is_planning_only,
    resume_plan_requires_full_gate_stack,
)


# ---------------------------------------------------------------------------
# 1. The builder produces a plan with the locked identity
# ---------------------------------------------------------------------------


def test_build_returns_a_resume_plan() -> None:
    plan = build_dip_filtered_resume_plan()
    assert isinstance(plan, Stage30_9_2DipFilteredResumePlan)
    assert plan.resume_id == STAGE30_9_2_RESUME_ID == "30.9.2_RESUME"
    assert plan.prior_stage == STAGE30_9_2_PRIOR_STAGE == "30.10.3"


def test_required_head_sha_pinned_and_carried() -> None:
    assert STAGE30_9_2_REQUIRED_HEAD_SHA == (
        "e35e54b69668814d2ab8c096855f682c68ada8ab"
    )
    plan = build_dip_filtered_resume_plan()
    assert plan.required_head_sha == STAGE30_9_2_REQUIRED_HEAD_SHA


def test_default_clock_pinned_and_carried() -> None:
    assert STAGE30_9_2_DEFAULT_PLAN_CREATED_AT == "2026-01-01T00:00:00Z"
    plan = build_dip_filtered_resume_plan()
    assert plan.created_at_utc == STAGE30_9_2_DEFAULT_PLAN_CREATED_AT


# ---------------------------------------------------------------------------
# 2. The plan requires the full Stage 30.10 dip-gate stack
# ---------------------------------------------------------------------------


def test_plan_names_the_required_gate_stack() -> None:
    plan = build_dip_filtered_resume_plan()
    assert plan.gate_stack_required == STAGE30_9_2_GATE_STACK_REQUIRED
    assert plan.gate_stack_required == (
        "30.10.1 offline tier-dip eligibility classifier",
        "30.10.2 optional pre-dispatch tier-dip gate",
        "30.10.3 gate artifact projection",
    )


def test_resume_plan_requires_full_gate_stack_predicate() -> None:
    plan = build_dip_filtered_resume_plan()
    assert resume_plan_requires_full_gate_stack(plan) is True
    # A plan missing a gate-stack stage does not satisfy the predicate.
    partial = dataclasses.replace(
        plan, gate_stack_required=STAGE30_9_2_GATE_STACK_REQUIRED[:2]
    )
    assert resume_plan_requires_full_gate_stack(partial) is False


# ---------------------------------------------------------------------------
# 3. The plan refuses live / dispatch / env / provider / Discord
# ---------------------------------------------------------------------------


def test_plan_holds_every_live_affecting_axis_closed() -> None:
    plan = build_dip_filtered_resume_plan()
    assert plan.live_allowed is False
    assert plan.dispatch_allowed is False
    assert plan.env_read_allowed is False
    assert plan.provider_call_allowed is False
    assert plan.discord_send_allowed is False


def test_resume_plan_is_planning_only_predicate() -> None:
    plan = build_dip_filtered_resume_plan()
    assert resume_plan_is_planning_only(plan) is True
    # Flipping ANY single live-affecting axis makes it no longer planning-only.
    for axis in (
        "live_allowed",
        "dispatch_allowed",
        "env_read_allowed",
        "provider_call_allowed",
        "discord_send_allowed",
    ):
        flipped = dataclasses.replace(plan, **{axis: True})
        assert resume_plan_is_planning_only(flipped) is False, (
            f"flipping {axis!r} to True must not be planning-only"
        )


def test_plan_does_not_auto_run_live() -> None:
    plan = build_dip_filtered_resume_plan()
    assert resume_plan_allows_live(plan) is False


# ---------------------------------------------------------------------------
# 4. The next action is an explicit operator-authorized live ceremony
# ---------------------------------------------------------------------------


def test_live_ceremony_requires_operator_auth() -> None:
    assert STAGE30_9_2_LIVE_CEREMONY_REQUIRES_OPERATOR_AUTH is True


def test_next_action_is_explicit_operator_authorized_ceremony() -> None:
    lower = STAGE30_9_2_NEXT_ACTION.lower()
    assert "operator-authorized" in lower
    assert "live ceremony" in lower
    assert "separate" in lower
    # Never an automatic live execution; never a Stage 30.10.4.
    assert "never auto-run" in lower
    assert "30.10.4" in STAGE30_9_2_NEXT_ACTION


# ---------------------------------------------------------------------------
# 5. Caller can inject the head sha + clock; the plan is deterministic
# ---------------------------------------------------------------------------


def test_caller_can_inject_head_sha_and_clock() -> None:
    plan = build_dip_filtered_resume_plan(
        required_head_sha="deadbeef", created_at_utc="2026-05-31T00:00:00Z"
    )
    assert plan.required_head_sha == "deadbeef"
    assert plan.created_at_utc == "2026-05-31T00:00:00Z"
    # Injecting the clock never flips a live-affecting axis open.
    assert resume_plan_is_planning_only(plan) is True


def test_plan_is_deterministic() -> None:
    assert build_dip_filtered_resume_plan() == build_dip_filtered_resume_plan()

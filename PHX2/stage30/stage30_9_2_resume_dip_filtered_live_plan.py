"""Stage 30.9.2_RESUME dip-filtered live proof plan.

Pure, offline builder for the Stage 30.9.2_RESUME dip-filtered live proof
PLAN: the passive readiness carrier that records which committed gate stack
the resume is built against and pins, in auditable form, that for the
planning / fake-proof step every live-affecting axis is held closed. The
actual controlled live ceremony is a SEPARATE, explicitly operator-authorized
step that consumes this plan; the plan NEVER auto-runs live.

The default plan is the locked planning stance: it names the required Stage
30.10 dip-gate stack (30.10.1 classifier -> 30.10.2 pre-dispatch gate ->
30.10.3 artifact projection) and holds ``live_allowed`` /
``dispatch_allowed`` / ``env_read_allowed`` / ``provider_call_allowed`` /
``discord_send_allowed`` all ``False``. So the dip-filtered live proof can be
assembled and proven offline BEFORE the actual ceremony is ever
operator-authorized.

This module is the PLAN builder ONLY. It makes NO live provider call, sends
NO Discord message, reads NO process environment, opens NO network
connection, opens NO database, writes NO file, performs NO transport-layer
veto, reserves NO dispatch, and edits NO Stage 28 suppression / Stage 30.3 /
Stage 30.4 runtime orchestrator. It NEVER calls ``datetime.now`` (the clock
is caller-injected). Stage 30.9.2_RESUME planning is fake / offline only;
nothing existing imports it.

Discipline:

  * Stdlib only (``typing``).
  * Imports ONLY the Stage 30.9.2 resume-models sibling; no other PHX2
    module, no Stage 21-29 / Stage 30.3 / Stage 30.4 orchestrator / Stage 28
    suppression / live runner / provider / transport import.
  * No ``os.environ`` / ``os.getenv`` access; no env read.
  * No network, no HTTP, no gRPC, no WebSocket, no socket.
  * No database / SQLite, no zstd / compression, no default storage root.
  * No live provider, transport-destination, or request-metadata reference.
  * No PHX1 import. No wall clock (``created_at_utc`` is caller-injected).
"""

from __future__ import annotations

from PHX2.stage30.stage30_9_2_resume_dip_filtered_live_models import (
    STAGE30_9_2_GATE_STACK_REQUIRED,
    STAGE30_9_2_PRIOR_STAGE,
    STAGE30_9_2_RESUME_ID,
    Stage30_9_2DipFilteredResumePlan,
)


# The committed HEAD the Stage 30.9.2_RESUME plan is built against -- the
# Stage 30.10.3 fake gate artifact integration proof commit (the final Stage
# 30.10 fake / offline proof before resume). A safe-shape hex id; never a
# secret.
STAGE30_9_2_REQUIRED_HEAD_SHA: str = (
    "e35e54b69668814d2ab8c096855f682c68ada8ab"
)


# The deterministic caller-injected clock for the default plan (never a
# wall-clock read).
STAGE30_9_2_DEFAULT_PLAN_CREATED_AT: str = "2026-01-01T00:00:00Z"


# The Stage 30.9.2_RESUME live ceremony remains a SEPARATE, explicitly
# operator-authorized step; the plan never auto-runs live.
STAGE30_9_2_LIVE_CEREMONY_REQUIRES_OPERATOR_AUTH: bool = True


# The next action after this planning / fake-proof slice: a controlled
# dip-filtered live ceremony that is explicitly operator-authorized -- NOT an
# automatic live execution and NOT a Stage 30.10.4 (there is no Stage
# 30.10.4).
STAGE30_9_2_NEXT_ACTION: str = (
    "controlled dip-filtered private compact live ceremony -- a separate, "
    "explicitly operator-authorized step; never auto-run from this plan and "
    "never a Stage 30.10.4"
)


# ---------------------------------------------------------------------------
# Pure plan builder
# ---------------------------------------------------------------------------


def build_dip_filtered_resume_plan(
    *,
    required_head_sha: str = STAGE30_9_2_REQUIRED_HEAD_SHA,
    created_at_utc: str = STAGE30_9_2_DEFAULT_PLAN_CREATED_AT,
) -> Stage30_9_2DipFilteredResumePlan:
    """Build the locked Stage 30.9.2_RESUME dip-filtered live proof plan.

    Pure / deterministic / no I/O. Returns a frozen
    ``Stage30_9_2DipFilteredResumePlan`` that names the required Stage 30.10
    dip-gate stack and holds EVERY live-affecting axis closed
    (``live_allowed`` / ``dispatch_allowed`` / ``env_read_allowed`` /
    ``provider_call_allowed`` / ``discord_send_allowed`` all ``False``) for
    THIS planning / fake-proof step. ``required_head_sha`` / ``created_at_utc``
    are caller-injectable (the clock is never a wall-clock read); the actual
    live ceremony remains a separate, explicitly operator-authorized step.
    """
    return Stage30_9_2DipFilteredResumePlan(
        resume_id=STAGE30_9_2_RESUME_ID,
        required_head_sha=required_head_sha,
        prior_stage=STAGE30_9_2_PRIOR_STAGE,
        gate_stack_required=STAGE30_9_2_GATE_STACK_REQUIRED,
        # Planning / fake-proof step: every live-affecting axis held closed.
        live_allowed=False,
        dispatch_allowed=False,
        env_read_allowed=False,
        provider_call_allowed=False,
        discord_send_allowed=False,
        created_at_utc=created_at_utc,
    )


# ---------------------------------------------------------------------------
# Pure predicates over a plan
# ---------------------------------------------------------------------------


def resume_plan_requires_full_gate_stack(
    plan: Stage30_9_2DipFilteredResumePlan,
) -> bool:
    """Return ``True`` iff ``plan`` requires the full Stage 30.10 dip-gate
    stack (the 30.10.1 classifier + 30.10.2 pre-dispatch gate + 30.10.3
    artifact projection). Pure / total; never raises.
    """
    return tuple(plan.gate_stack_required) == STAGE30_9_2_GATE_STACK_REQUIRED


def resume_plan_is_planning_only(
    plan: Stage30_9_2DipFilteredResumePlan,
) -> bool:
    """Return ``True`` iff ``plan`` holds EVERY live-affecting axis closed.

    A planning-only plan has ``live_allowed`` / ``dispatch_allowed`` /
    ``env_read_allowed`` / ``provider_call_allowed`` / ``discord_send_allowed``
    all ``False`` -- the fake / offline stance. Pure / total; never raises.
    """
    return not any(
        (
            plan.live_allowed,
            plan.dispatch_allowed,
            plan.env_read_allowed,
            plan.provider_call_allowed,
            plan.discord_send_allowed,
        )
    )


def resume_plan_allows_live(
    plan: Stage30_9_2DipFilteredResumePlan,
) -> bool:
    """Return ``plan.live_allowed`` (``False`` for the planning / fake-proof
    plan). The plan NEVER auto-runs live; the actual ceremony is a separate,
    explicitly operator-authorized step. Pure / total; never raises.
    """
    return bool(plan.live_allowed)


__all__ = (
    "STAGE30_9_2_REQUIRED_HEAD_SHA",
    "STAGE30_9_2_DEFAULT_PLAN_CREATED_AT",
    "STAGE30_9_2_LIVE_CEREMONY_REQUIRES_OPERATOR_AUTH",
    "STAGE30_9_2_NEXT_ACTION",
    "build_dip_filtered_resume_plan",
    "resume_plan_requires_full_gate_stack",
    "resume_plan_is_planning_only",
    "resume_plan_allows_live",
)

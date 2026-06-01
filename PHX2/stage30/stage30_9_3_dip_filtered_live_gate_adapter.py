"""Stage 30.9.3 dip-filtered live gate adapter.

The pure, offline ADAPTER that is the heart of the dip-filtered live dispatch
integration seam. It accepts one ALREADY-ASSEMBLED live candidate / context
record (a Stage 30.9.3 ``Stage30_9_3LiveGateInput``) and runs the committed
Stage 30.10 dip-gate stack over it:

    the live candidate / context
      -> build the Stage 30.10.1 eligibility input (from existing context
         fields; NO provider call)
      -> the Stage 30.10.2 pre-dispatch gate         (which runs the Stage
         30.10.1 classifier internally, BEFORE dispatch reservation)
      -> the Stage 30.10.3 gate artifact projection  (the per-candidate
         artifact record)
      -> a Stage 30.9.3 ``Stage30_9_3LiveGateDecision``

The decision is the seam's verdict: ``dispatch_reservation_allowed`` is
``True`` IFF the gate ruled ``PASS_TO_DISPATCH`` (the ONLY candidate that may
reserve a dispatch / proceed toward the private compact send). Every non-pass
candidate (a normal non-dip ``SKIP_BEFORE_DISPATCH`` or an ``INVALID_INPUT``)
is suppressed cleanly BEFORE reservation; it is NEVER a dispatch failure,
NEVER a transport veto, and NEVER a transport ``PAYLOAD_REFUSED`` veto (the
three derived booleans are always ``False``, sourced verbatim from the Stage
30.10.3 projection).

The adapter NEVER fetches market data, NEVER opens a network connection,
NEVER reads the process environment, NEVER calls ``datetime.now`` (the clock
is caller-injected on the input), NEVER sends Discord, NEVER reserves a real
dispatch / performs a real send, NEVER performs a transport-layer veto, NEVER
writes a file, and edits NO Stage 28 suppression / Stage 30.3 / Stage 30.4
runtime orchestrator. It composes the committed Stage 30.10 gate stack and
projects one Stage 30.9.3 decision; nothing more.

Discipline:

  * Stdlib only (``typing``).
  * Imports only the Stage 30.9.3 models sibling + the committed Stage
    30.10.1 eligibility models, Stage 30.10.2 pre-dispatch gate + gate models,
    and Stage 30.10.3 artifact projector + artifact models. No other PHX2
    module; no Stage 21-29 / Stage 30.3 / Stage 30.4 orchestrator / Stage 28
    suppression / live runner / provider / transport import.
  * No ``os.environ`` / ``os.getenv`` access; no env read.
  * No network, no HTTP, no gRPC, no WebSocket, no socket.
  * No database / SQLite, no zstd / compression, no default storage root.
  * No live provider, transport-destination, or request-metadata reference.
  * No PHX1 import. No wall clock (``created_at_utc`` is caller-injected).
"""

from __future__ import annotations

from typing import Optional

from PHX2.stage30.stage30_9_3_dip_filtered_live_gate_models import (
    Stage30_9_3LiveGateDecision,
    Stage30_9_3LiveGateInput,
)
from PHX2.stage30.stage30_10_1_tier_dip_eligibility_models import (
    DEFAULT_STAGE30_10_DIP_ELIGIBILITY_POLICY,
    Stage30_10DipEligibilityInput,
    Stage30_10DipEligibilityPolicy,
)
from PHX2.stage30.stage30_10_2_pre_dispatch_gate import (
    evaluate_pre_dispatch_tier_dip_gate,
)
from PHX2.stage30.stage30_10_2_pre_dispatch_gate_models import (
    Stage30_10PreDispatchGateInput,
)
from PHX2.stage30.stage30_10_3_gate_artifact_models import (
    STAGE30_10_3_ARTIFACT_SCHEMA_VERSION,
    Stage30_10GateArtifactRecord,
)
from PHX2.stage30.stage30_10_3_gate_artifact_projector import (
    project_gate_record_to_artifact_record,
)


# The default safe proof-run id stamped onto the projected Stage 30.10.3
# artifact record (a safe-shape opaque label; never a secret).
STAGE30_9_3_DEFAULT_PROOF_ID: str = "stage30_9_3_dip_filtered_live_gate"


# ---------------------------------------------------------------------------
# Module-local exception (caller-shape failure)
# ---------------------------------------------------------------------------


class Stage30_9_3DipFilteredLiveGateError(Exception):
    """Closed-set Stage 30.9.3 dip-filtered live gate adapter error.

    Raised ONLY for a caller-shape failure the adapter cannot evaluate (a
    ``live_input`` that is not a ``Stage30_9_3LiveGateInput`` -- there is no
    assembled live candidate to gate). Degraded / invalid input VALUES never
    raise; they flow through to the Stage 30.10.2 gate, which classifies them
    as ``INVALID_INPUT`` / ``SKIP_BEFORE_DISPATCH`` (a clean no-send) and the
    adapter projects that verdict. Carries only a closed-set reason token;
    never a raw payload or any secret value.
    """

    def __init__(self, reason: str) -> None:
        self.reason: str = reason
        super().__init__(
            f"Stage 30.9.3 dip-filtered live gate error: reason={reason!r}"
        )


# ---------------------------------------------------------------------------
# Pure builders: live candidate / context -> Stage 30.10 gate inputs
# ---------------------------------------------------------------------------


def build_eligibility_input(
    live_input: Stage30_9_3LiveGateInput,
) -> Stage30_10DipEligibilityInput:
    """Build the Stage 30.10.1 eligibility input from an assembled live
    candidate / context record.

    Pure / deterministic / no I/O, no provider call. Maps the live context
    fields one-to-one onto the Stage 30.10.1 ``Stage30_10DipEligibilityInput``
    the classifier consults. ``created_at_utc`` is echoed (never a wall-clock
    read).
    """
    if not isinstance(live_input, Stage30_9_3LiveGateInput):
        raise Stage30_9_3DipFilteredLiveGateError(
            "INVALID_LIVE_INPUT_RECORD_TYPE"
        )
    return Stage30_10DipEligibilityInput(
        candidate_id=live_input.candidate_id,
        token_mint=live_input.token_mint,
        tier_token=live_input.tier_token,
        drawdown_from_ath=live_input.drawdown_from_ath,
        migration_status=live_input.migration_status,
        ath_status=live_input.ath_status,
        market_context_status=live_input.market_context_status,
        current_market_cap_usd=live_input.current_market_cap_usd,
        post_migration_ath_verified=live_input.post_migration_ath_verified,
        created_at_utc=live_input.created_at_utc,
    )


def build_gate_input(
    live_input: Stage30_9_3LiveGateInput,
) -> Stage30_10PreDispatchGateInput:
    """Wrap the built Stage 30.10.1 eligibility input in a Stage 30.10.2 gate
    envelope whose identity matches the live candidate.

    Pure / deterministic / no I/O. ``candidate_ref`` / ``created_at_utc`` are
    echoed from the live candidate (never a wall-clock read).
    """
    if not isinstance(live_input, Stage30_9_3LiveGateInput):
        raise Stage30_9_3DipFilteredLiveGateError(
            "INVALID_LIVE_INPUT_RECORD_TYPE"
        )
    return Stage30_10PreDispatchGateInput(
        candidate_id=live_input.candidate_id,
        token_mint=live_input.token_mint,
        eligibility_input=build_eligibility_input(live_input),
        candidate_ref=live_input.candidate_ref,
        created_at_utc=live_input.created_at_utc,
    )


# ---------------------------------------------------------------------------
# Pure projector: Stage 30.10.3 artifact record -> Stage 30.9.3 decision
# ---------------------------------------------------------------------------


def _decision_from_artifact_record(
    artifact_record: Stage30_10GateArtifactRecord,
) -> Stage30_9_3LiveGateDecision:
    """Project ONE Stage 30.10.3 gate artifact record into a Stage 30.9.3
    live gate decision.

    Pure / deterministic / no I/O. Echoes the artifact record's identity +
    eligibility / gate closed-set tokens, renames the Stage 30.10.3
    ``dispatch_reservation_would_be_attempted`` onto the Stage 30.9.3
    ``dispatch_reservation_allowed`` (same meaning: only a gate
    ``PASS_TO_DISPATCH`` candidate may reserve a dispatch), and carries the
    three always-``False`` transport-safety negatives verbatim. Drops the
    Stage 30.10.3-internal ``proof_id`` / ``send_allowed`` and stamps the
    source ``artifact_schema_version``. ``created_at_utc`` is echoed from the
    artifact record (never a wall-clock read).
    """
    return Stage30_9_3LiveGateDecision(
        candidate_id=artifact_record.candidate_id,
        token_mint=artifact_record.token_mint,
        eligibility_decision=artifact_record.eligibility_decision,
        eligibility_reason=artifact_record.eligibility_reason,
        gate_decision=artifact_record.gate_decision,
        gate_reason=artifact_record.gate_reason,
        artifact_schema_version=STAGE30_10_3_ARTIFACT_SCHEMA_VERSION,
        dispatch_reservation_allowed=(
            artifact_record.dispatch_reservation_would_be_attempted
        ),
        suppressed_before_dispatch_reservation=(
            artifact_record.suppressed_before_dispatch_reservation
        ),
        # A dip-filtered pre-dispatch skip is NEVER a dispatch failure, NEVER a
        # transport-layer veto, and NEVER a transport PAYLOAD_REFUSED veto.
        dispatch_failure_recorded=artifact_record.dispatch_failure_recorded,
        transport_veto_used=artifact_record.transport_veto_used,
        payload_refused_used=artifact_record.payload_refused_used,
        created_at_utc=artifact_record.created_at_utc,
    )


# ---------------------------------------------------------------------------
# Public adapter
# ---------------------------------------------------------------------------


def evaluate_dip_filtered_live_gate(
    live_input: Stage30_9_3LiveGateInput,
    *,
    policy: Optional[Stage30_10DipEligibilityPolicy] = None,
    proof_id: str = STAGE30_9_3_DEFAULT_PROOF_ID,
) -> Stage30_9_3LiveGateDecision:
    """Evaluate the dip-filtered live gate for ONE assembled live candidate.

    Pure / deterministic / no I/O, no provider call, no Discord send, no env
    read. Builds the Stage 30.10.1 eligibility input from ``live_input``, runs
    the Stage 30.10.2 pre-dispatch gate (which runs the Stage 30.10.1
    classifier internally), projects the Stage 30.10.3 gate artifact record,
    and returns a ``Stage30_9_3LiveGateDecision`` whose
    ``dispatch_reservation_allowed`` is ``True`` ONLY for a gate
    ``PASS_TO_DISPATCH`` candidate (the only candidate that may reserve a
    dispatch / proceed toward the private compact send). A normal non-dip skip
    returns ``SKIP_BEFORE_DISPATCH`` (``suppressed_before_dispatch_reservation
    = True``); an invalid candidate returns ``INVALID_INPUT`` (also
    suppressed). The three transport-safety negatives
    (``dispatch_failure_recorded`` / ``transport_veto_used`` /
    ``payload_refused_used``) are ALWAYS ``False``.

    When ``policy`` is ``None`` (the default) the locked Stage 30.10
    fail-closed default policy is used. Raises
    ``Stage30_9_3DipFilteredLiveGateError`` only when ``live_input`` is not a
    ``Stage30_9_3LiveGateInput`` (a caller-shape failure with no assembled
    candidate to gate); degraded input VALUES never raise. The artifact
    timestamp is the candidate's own caller-injected ``created_at_utc``.
    """
    if not isinstance(live_input, Stage30_9_3LiveGateInput):
        raise Stage30_9_3DipFilteredLiveGateError(
            "INVALID_LIVE_INPUT_RECORD_TYPE"
        )

    effective_policy: Stage30_10DipEligibilityPolicy = (
        policy
        if policy is not None
        else DEFAULT_STAGE30_10_DIP_ELIGIBILITY_POLICY
    )

    gate_input = build_gate_input(live_input)
    gate_record = evaluate_pre_dispatch_tier_dip_gate(
        gate_input, effective_policy
    )
    artifact_record = project_gate_record_to_artifact_record(
        proof_id=proof_id,
        gate_record=gate_record,
        created_at_utc=live_input.created_at_utc,
    )
    return _decision_from_artifact_record(artifact_record)


__all__ = (
    "STAGE30_9_3_DEFAULT_PROOF_ID",
    "Stage30_9_3DipFilteredLiveGateError",
    "build_eligibility_input",
    "build_gate_input",
    "evaluate_dip_filtered_live_gate",
)

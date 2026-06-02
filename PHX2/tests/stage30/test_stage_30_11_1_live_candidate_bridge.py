"""Stage 30.11.1 live-candidate assembly bridge behavior tests.

Pins the pure bridge function:

  * a valid dip-context candidate bridges to a committed Stage 30.9.3
    ``Stage30_9_3LiveGateInput`` (BRIDGED_TO_LIVE_GATE_INPUT / READY_FOR_DIP_GATE),
  * a valid NON-dip-context candidate ALSO bridges (the bridge does not decide
    dip; the committed Stage 30.9.3 gate does, later),
  * a candidate missing ATH / migration / current-market context is skipped
    (SKIPPED_MISSING_REQUIRED_CONTEXT / MISSING_REQUIRED_CONTEXT; no gate input),
  * a malformed candidate id / token mint fails closed (INVALID_BRIDGE_INPUT /
    INVALID_FIELD_SHAPE; no gate input),
  * a non-snapshot input raises the closed-set bridge error,
  * the field mapping is one-to-one and fabricates nothing,
  * the bridge exposes / calls NO dispatch sink, and
  * every bridged output is compatible with the committed Stage 30.9.3
    ``evaluate_dip_filtered_live_gate`` -- WITHOUT dispatching.

Fake / offline only; no live call, no provider, no Discord, no env read, no
dispatch reservation.
"""

from __future__ import annotations

import ast
from decimal import Decimal

import pytest

from PHX2.stage30.stage30_9_3_dip_filtered_live_gate_adapter import (
    evaluate_dip_filtered_live_gate,
)
from PHX2.stage30.stage30_9_3_dip_filtered_live_gate_models import (
    Stage30_9_3LiveGateInput,
)
import PHX2.stage30.stage30_11_1_live_candidate_bridge as BRIDGE
from PHX2.stage30.stage30_11_1_live_candidate_bridge import (
    Stage30_11LiveCandidateBridgeError,
    build_stage30_9_3_live_gate_input_from_candidate,
)
from PHX2.stage30.stage30_11_1_live_candidate_bridge_models import (
    BRIDGE_DECISION_BRIDGED_TO_LIVE_GATE_INPUT,
    BRIDGE_DECISION_INVALID_BRIDGE_INPUT,
    BRIDGE_DECISION_SKIPPED_MISSING_REQUIRED_CONTEXT,
    BRIDGE_REASON_INVALID_FIELD_SHAPE,
    BRIDGE_REASON_MISSING_REQUIRED_CONTEXT,
    BRIDGE_REASON_READY_FOR_DIP_GATE,
    Stage30_11LiveCandidateSnapshot,
)


_RESULT_CLOCK: str = "2026-02-02T00:00:00Z"
_SNAPSHOT_CLOCK: str = "2026-01-01T00:00:00Z"


def _snapshot(
    *,
    candidate_id: str = "cand-1",
    token_mint: str = "mint-1",
    tier_hint=None,
    drawdown_from_ath=Decimal("0.55"),
    migration_status="PRESENT",
    ath_status="PRESENT",
    market_context_status="PRESENT",
    current_market_cap_usd=Decimal("12345.67"),
    post_migration_ath_verified=True,
    source_ref="ref-1",
) -> Stage30_11LiveCandidateSnapshot:
    return Stage30_11LiveCandidateSnapshot(
        candidate_id=candidate_id,
        token_mint=token_mint,
        pair_type="SOL",
        tier_hint=tier_hint,
        drawdown_from_ath=drawdown_from_ath,
        migration_status=migration_status,
        ath_status=ath_status,
        market_context_status=market_context_status,
        current_market_cap_usd=current_market_cap_usd,
        post_migration_ath_verified=post_migration_ath_verified,
        source_ref=source_ref,
        created_at_utc=_SNAPSHOT_CLOCK,
    )


def _bridge(snap: Stage30_11LiveCandidateSnapshot):
    return build_stage30_9_3_live_gate_input_from_candidate(
        snap, created_at_utc=_RESULT_CLOCK
    )


# ---------------------------------------------------------------------------
# 1. Valid dip-context candidate bridges
# ---------------------------------------------------------------------------


def test_valid_dip_context_candidate_bridges() -> None:
    res = _bridge(_snapshot(tier_hint="Tier 1"))
    assert res.bridge_decision == BRIDGE_DECISION_BRIDGED_TO_LIVE_GATE_INPUT
    assert res.bridge_reason == BRIDGE_REASON_READY_FOR_DIP_GATE
    assert isinstance(res.live_gate_input, Stage30_9_3LiveGateInput)
    assert res.candidate_id == "cand-1"
    assert res.token_mint == "mint-1"


def test_bridged_field_mapping_is_one_to_one() -> None:
    res = _bridge(_snapshot(tier_hint="Tier 1"))
    gi = res.live_gate_input
    assert gi is not None
    # Identity + context mapped verbatim.
    assert gi.candidate_id == "cand-1"
    assert gi.token_mint == "mint-1"
    # tier_hint -> tier_token (the gate classifies the tier; the bridge does
    # not recompute it).
    assert gi.tier_token == "Tier 1"
    assert gi.drawdown_from_ath == Decimal("0.55")
    assert gi.migration_status == "PRESENT"
    assert gi.ath_status == "PRESENT"
    assert gi.market_context_status == "PRESENT"
    assert gi.current_market_cap_usd == Decimal("12345.67")
    assert gi.post_migration_ath_verified is True
    # source_ref -> candidate_ref.
    assert gi.candidate_ref == "ref-1"
    # The gate input carries the candidate's OWN assembled-context clock; the
    # bridge RESULT carries the (distinct) bridge-run clock.
    assert gi.created_at_utc == _SNAPSHOT_CLOCK
    assert res.created_at_utc == _RESULT_CLOCK


def test_bridge_passes_through_none_optionals() -> None:
    # tier_hint / drawdown / post_migration_ath_verified all None still bridge
    # (context present); the gate later fails them closed, not the bridge.
    res = _bridge(
        _snapshot(
            tier_hint=None,
            drawdown_from_ath=None,
            post_migration_ath_verified=None,
            source_ref=None,
        )
    )
    assert res.bridge_decision == BRIDGE_DECISION_BRIDGED_TO_LIVE_GATE_INPUT
    gi = res.live_gate_input
    assert gi is not None
    assert gi.tier_token is None
    assert gi.drawdown_from_ath is None
    assert gi.post_migration_ath_verified is None
    assert gi.candidate_ref is None


# ---------------------------------------------------------------------------
# 2. Valid NON-dip-context candidate ALSO bridges (bridge does not decide dip)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "tier_hint", ["Tier Unknown", "Tier Not Applicable", "Tier 2", None]
)
def test_valid_non_dip_context_candidate_bridges(tier_hint) -> None:
    # Any tier (or none) bridges as long as the context is present. Whether the
    # candidate is an eligible DIP is decided LATER by the Stage 30.9.3 gate.
    res = _bridge(_snapshot(tier_hint=tier_hint))
    assert res.bridge_decision == BRIDGE_DECISION_BRIDGED_TO_LIVE_GATE_INPUT
    assert res.bridge_reason == BRIDGE_REASON_READY_FOR_DIP_GATE
    assert res.live_gate_input is not None
    assert res.live_gate_input.tier_token == tier_hint


# ---------------------------------------------------------------------------
# 3. Missing required context -> clean skip
# ---------------------------------------------------------------------------


def test_missing_ath_skips() -> None:
    for bad_ath in (None, "MISSING", "STALE", ""):
        res = _bridge(_snapshot(ath_status=bad_ath))
        assert res.bridge_decision == (
            BRIDGE_DECISION_SKIPPED_MISSING_REQUIRED_CONTEXT
        )
        assert res.bridge_reason == BRIDGE_REASON_MISSING_REQUIRED_CONTEXT
        assert res.live_gate_input is None


def test_missing_migration_skips() -> None:
    for bad_mig in (None, "MISSING", "STALE", ""):
        res = _bridge(_snapshot(migration_status=bad_mig))
        assert res.bridge_decision == (
            BRIDGE_DECISION_SKIPPED_MISSING_REQUIRED_CONTEXT
        )
        assert res.bridge_reason == BRIDGE_REASON_MISSING_REQUIRED_CONTEXT
        assert res.live_gate_input is None


def test_missing_market_context_skips() -> None:
    res = _bridge(_snapshot(market_context_status=None))
    assert res.bridge_decision == (
        BRIDGE_DECISION_SKIPPED_MISSING_REQUIRED_CONTEXT
    )
    assert res.bridge_reason == BRIDGE_REASON_MISSING_REQUIRED_CONTEXT
    assert res.live_gate_input is None


def test_skip_still_echoes_identity_and_result_clock() -> None:
    res = _bridge(_snapshot(candidate_id="c-skip", ath_status=None))
    assert res.candidate_id == "c-skip"
    assert res.token_mint == "mint-1"
    assert res.created_at_utc == _RESULT_CLOCK


# ---------------------------------------------------------------------------
# 4. Malformed candidate id / token mint -> INVALID_BRIDGE_INPUT
# ---------------------------------------------------------------------------


def test_malformed_candidate_id_is_invalid() -> None:
    for bad_id in ("", "   ", "\t"):
        res = _bridge(_snapshot(candidate_id=bad_id))
        assert res.bridge_decision == BRIDGE_DECISION_INVALID_BRIDGE_INPUT
        assert res.bridge_reason == BRIDGE_REASON_INVALID_FIELD_SHAPE
        assert res.live_gate_input is None


def test_malformed_token_mint_is_invalid() -> None:
    for bad_mint in ("", "   ", "\n"):
        res = _bridge(_snapshot(token_mint=bad_mint))
        assert res.bridge_decision == BRIDGE_DECISION_INVALID_BRIDGE_INPUT
        assert res.bridge_reason == BRIDGE_REASON_INVALID_FIELD_SHAPE
        assert res.live_gate_input is None


def test_invalid_identity_takes_precedence_over_missing_context() -> None:
    # A blank id AND missing context fails closed to INVALID (shape first).
    res = _bridge(_snapshot(candidate_id="", ath_status=None))
    assert res.bridge_decision == BRIDGE_DECISION_INVALID_BRIDGE_INPUT
    assert res.live_gate_input is None


# ---------------------------------------------------------------------------
# 5. Non-snapshot input raises the closed-set bridge error
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "bad", [None, "not-a-snapshot", 7, {"candidate_id": "x"}, object()]
)
def test_non_snapshot_input_raises(bad) -> None:
    with pytest.raises(Stage30_11LiveCandidateBridgeError) as exc:
        build_stage30_9_3_live_gate_input_from_candidate(
            bad, created_at_utc=_RESULT_CLOCK
        )
    assert exc.value.reason == "INVALID_CANDIDATE_RECORD_TYPE"


# ---------------------------------------------------------------------------
# 6. The bridge exposes / calls NO dispatch sink
# ---------------------------------------------------------------------------


def test_bridge_public_surface_is_exactly_error_and_build() -> None:
    assert set(BRIDGE.__all__) == {
        "Stage30_11LiveCandidateBridgeError",
        "build_stage30_9_3_live_gate_input_from_candidate",
    }


def test_bridge_module_exposes_no_dispatch_or_sink_symbol() -> None:
    for name in dir(BRIDGE):
        lowered = name.lower()
        assert "sink" not in lowered, (
            f"Stage 30.11.1 bridge must expose no dispatch sink symbol; saw "
            f"{name!r}"
        )
        assert "dispatch" not in lowered, (
            f"Stage 30.11.1 bridge must expose no dispatch symbol; saw {name!r}"
        )


def _called_names(text: str) -> set:
    """Return the set of called function / method names in ``text`` (Call node
    callees only -- so a word appearing in a docstring / comment is NOT a
    match; only an actual call is).
    """
    names = set()
    for node in ast.walk(ast.parse(text)):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name):
                names.add(func.id)
            elif isinstance(func, ast.Attribute):
                names.add(func.attr)
    return names


def test_bridge_makes_no_dispatch_sink_or_gate_eval_call() -> None:
    # AST proof (call NAMES only, not prose): the bridge invokes no dispatch /
    # sink call and never runs the committed dip gate. The bridge's docstrings
    # legitimately describe what it does NOT do ("never reserves a dispatch",
    # naming ``evaluate_dip_filtered_live_gate`` as the downstream caller's
    # job), so this scans actual Call nodes, never the source text.
    text = open(BRIDGE.__file__, encoding="utf-8").read()
    called = _called_names(text)
    for name in called:
        lowered = name.lower()
        assert "sink" not in lowered, (
            f"Stage 30.11.1 bridge calls a sink-like function {name!r}"
        )
        assert "dispatch" not in lowered, (
            f"Stage 30.11.1 bridge calls a dispatch-like function {name!r}"
        )
        assert "reserve" not in lowered, (
            f"Stage 30.11.1 bridge calls a reserve-like function {name!r}"
        )
    for forbidden in (
        "evaluate_dip_filtered_live_gate",
        "run_dip_filtered_live_gate_integration",
        "evaluate_pre_dispatch_tier_dip_gate",
    ):
        assert forbidden not in called, (
            f"Stage 30.11.1 bridge must not call {forbidden!r}; it only "
            "assembles a gate input"
        )


# ---------------------------------------------------------------------------
# 7. Bridged outputs are compatible with the committed Stage 30.9.3 gate
#    (WITHOUT dispatching)
# ---------------------------------------------------------------------------


def test_bridged_dip_input_passes_the_committed_gate() -> None:
    res = _bridge(_snapshot(tier_hint="Tier 1"))
    assert res.live_gate_input is not None
    decision = evaluate_dip_filtered_live_gate(res.live_gate_input)
    assert decision.gate_decision == "PASS_TO_DISPATCH"
    # The gate only RULES; it reserves no dispatch and uses no transport veto.
    assert decision.dispatch_failure_recorded is False
    assert decision.transport_veto_used is False
    assert decision.payload_refused_used is False


def test_bridged_non_dip_input_skips_at_the_committed_gate() -> None:
    res = _bridge(_snapshot(tier_hint="Tier Unknown"))
    assert res.live_gate_input is not None
    decision = evaluate_dip_filtered_live_gate(res.live_gate_input)
    assert decision.gate_decision == "SKIP_BEFORE_DISPATCH"
    assert decision.dispatch_reservation_allowed is False

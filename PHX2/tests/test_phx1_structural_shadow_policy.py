from __future__ import annotations

import argparse
from dataclasses import replace
from decimal import Decimal
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from PHX2.delivery import telegram_adapter as adapter_module
from PHX2.delivery.telegram_adapter import (
    MESSAGE_LENGTH_LIMIT_EXCEEDED,
    TelegramDeliveryAdapter,
)
from PHX2.delivery.telegram_composer import (
    TELEGRAM_INTERNAL_MAX_CHARACTERS,
    BuilderReadStatement,
    TelegramMessageTooLong,
    TelegramPingData,
    compose_telegram_ping,
)
from PHX2.free_tier_producer import free_tier_session
from PHX2.free_tier_producer.phx1_fee_gate import (
    BLOCK_DATA_STALE,
    BLOCK_SCAM_LIKELY,
    PHX1_FEE_GATE_NORMAL,
    PHX1_FEE_GATE_SCAM_LIKELY,
    build_fee_snapshot,
)
from PHX2.free_tier_producer.phx1_structural_policy import (
    EFFECTIVE_POLICY_ALLOW_WITH_SHADOW_WARNING,
    EFFECTIVE_POLICY_HARD_BLOCK,
    EFFECTIVE_POLICY_PASS,
    PHX1_STRUCTURAL_POLICY_ENFORCE,
    PHX1_STRUCTURAL_POLICY_SHADOW,
    PHX1_STRUCTURAL_POLICY_VERSION,
    SHADOWABLE_STRUCTURAL_REASON_TOKENS,
    build_shadow_candidate_artifact,
    normalize_phx1_structural_policy,
    policy_metadata_for_filter_results,
    route_phx1_structural_reasons,
    validate_phx1_structural_policy_decision,
)
from PHX2.free_tier_producer.scam_policy import (
    POLICY_ALLOW,
    POLICY_HARD_BLOCK,
    SECURITY_DECISION_PROOF_INCONSISTENT,
    delivery_block_reason,
    evaluate_delivery_safety,
    seal_delivery_decision,
    validate_delivery_decision,
)


MINT = "EkNbQMQYpd4JET5FpZrqbdkYdHXeqocZcBByJpFWpump"
WSOL = "So11111111111111111111111111111111111111112"
AT = "1970-01-01T00:16:40Z"
FIXTURE = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "phx1_shadow_policy_routing.json"
)
MATRIX = (
    Path(__file__).resolve().parents[1]
    / "free_tier_producer"
    / "phx1_structural_shadow_policy_matrix.json"
)


def _fee(label: str = PHX1_FEE_GATE_NORMAL, *, stale: bool = False):
    components = {
        PHX1_FEE_GATE_NORMAL: (
            600_000_000, 200_000_000, 200_000_000, 100_000_000),
        PHX1_FEE_GATE_SCAM_LIKELY: (
            100_000_000, 100_000_000, 800_000_000, 10_000_000),
    }[label]
    lp, protocol, creator, priority = components
    state = {
        "quote_mint": WSOL,
        "quote_asset": "SOL",
        "pair_type": "TOKEN_SOL",
        "unit": "SOL",
        "lp": lp,
        "protocol": protocol,
        "creator": creator,
        "base": 5_000_000,
        "priority": priority,
        "jito": 0,
        "events": 1000,
        "signatures": {f"sig-{i}" for i in range(1000)},
        "first": AT,
        "last": AT,
        "last_epoch": 1000,
        "recent": (),
        "tx_ante": (),
    }
    return build_fee_snapshot(
        MINT,
        state=state,
        now_epoch=(1301 if stale else 1000),
    )


def _ping_data(**updates) -> TelegramPingData:
    values = {
        "token_mint": MINT,
        "token_identity": "Phoenix Test ($PHX)",
        "token_metadata_source": "TEST_FIXTURE",
        "age_minutes": 22,
        "age_display": "22m",
        "tier": 3,
        "market_cap": "$10k",
        "post_migration_ath": "$57k",
        "migration_market_cap": "$32k",
        "floor": "-82%",
        "volume": "Spiking",
        "liquidity": "$7k",
        "quote_side_liquidity": "$3.5k",
        "liquidity_basis": "TOTAL_ACTUAL_POOL_TVL",
        "liquidity_quality": "Low",
        "fee_gate_label": "Scam Likely",
        "fee_gate_score": "4",
        "lp_integrity": "DISABLED",
        "composite_verdict": "PASS",
        "bribes_amm_pct": "1.0%",
        "creator_pct": "80.0%",
        "bribes_per_tx_lamports": "100",
        "structure_read": "creator dominance high",
        "ante_last20_median": "0.000005",
        "ante_last20_p25": "0.000005",
        "ante_last20_p75": "0.000100",
        "ante_5m_median": "0.000005",
        "ante_5m_sample_count": "20",
        "base_fee_coverage": "100%",
        "ante_last20_width": "20",
        "ante_5m_width": "20",
        "priority_fee_median_lamports": "100",
        "priority_fee_sample_count": "20",
        "shape_5m": "AMBIGUOUS",
        "shape_5m_rule": "6",
        "shape_last20": "AMBIGUOUS",
        "shape_last20_rule": "6",
        "builder_read": (
            BuilderReadStatement(
                "Manual structure review required",
                ("PHX1_FEE_GATE_SCAM_LIKELY",),
            ),
        ),
        "risk_warning": "",
    }
    values.update(updates)
    return TelegramPingData(**values)


def test_policy_default_is_enforce():
    assert normalize_phx1_structural_policy() == PHX1_STRUCTURAL_POLICY_ENFORCE
    decision = evaluate_delivery_safety(fee_snapshot=_fee())
    assert decision.phx1_structural_policy == PHX1_STRUCTURAL_POLICY_ENFORCE


def test_cli_explicitly_selects_shadow():
    parser = argparse.ArgumentParser()
    free_tier_session._add_args(parser)
    args = parser.parse_args(["--phx1-structural-policy", "shadow"])
    assert normalize_phx1_structural_policy(
        args.phx1_structural_policy) == PHX1_STRUCTURAL_POLICY_SHADOW


@pytest.mark.parametrize("value", ["", "Enforce", "SHAdow", "warn", "off"])
def test_invalid_policy_values_fail_closed(value):
    with pytest.raises(ValueError, match="PHX1_STRUCTURAL_POLICY_INVALID"):
        normalize_phx1_structural_policy(value)


def test_cli_invalid_policy_value_is_rejected():
    parser = argparse.ArgumentParser()
    free_tier_session._add_args(parser)
    with pytest.raises(SystemExit):
        parser.parse_args(["--phx1-structural-policy", "SHADOW"])


def test_enforce_reproduces_legacy_gate_fields():
    decision = evaluate_delivery_safety(
        fee_snapshot=_fee(PHX1_FEE_GATE_SCAM_LIKELY))
    assert decision.verdict == POLICY_HARD_BLOCK
    assert decision.final_block_reasons == (BLOCK_SCAM_LIKELY,)
    assert decision.original_hard_block_reason_tokens == (BLOCK_SCAM_LIKELY,)
    assert not decision.eligible
    assert not decision.compose_allowed
    assert not decision.reservation_allowed
    assert not decision.ledger_mutation_allowed
    assert not decision.transport_allowed
    assert delivery_block_reason(decision) == BLOCK_SCAM_LIKELY


def test_shadow_converts_only_fee_structural_block():
    decision = evaluate_delivery_safety(
        fee_snapshot=_fee(PHX1_FEE_GATE_SCAM_LIKELY),
        phx1_structural_policy=PHX1_STRUCTURAL_POLICY_SHADOW,
    )
    assert decision.verdict == POLICY_ALLOW
    assert decision.original_phx1_structural_verdict == POLICY_HARD_BLOCK
    assert (
        decision.effective_phx1_policy_verdict
        == EFFECTIVE_POLICY_ALLOW_WITH_SHADOW_WARNING
    )
    assert decision.original_hard_block_reason_tokens == (BLOCK_SCAM_LIKELY,)
    assert decision.shadow_warning_reason_tokens == (BLOCK_SCAM_LIKELY,)
    assert decision.final_block_reasons == ()
    assert decision.manual_review_required
    assert decision.organicity_status == "UNVERIFIED"
    assert decision.eligible and decision.compose_allowed
    assert validate_delivery_decision(decision) == (True, None)


def test_original_fee_component_reasons_are_preserved():
    decision = evaluate_delivery_safety(
        fee_snapshot=_fee(PHX1_FEE_GATE_SCAM_LIKELY),
        phx1_structural_policy=PHX1_STRUCTURAL_POLICY_SHADOW,
    )
    fee_result = next(
        item for item in decision.original_filter_results
        if item[0] == "phx1_fee_gate"
    )
    assert "bribes_starved" in fee_result[2]
    assert "creator_dom_hi" in fee_result[2]
    assert BLOCK_SCAM_LIKELY in fee_result[2]


def test_multiple_shadow_reasons_are_all_retained():
    reasons = (
        "PHX1_FEE_GATE_DATA_STALE",
        "PHX2_FEE_LIFECYCLE_IMMATURE",
        "PHX2_FEE_LIFECYCLE_PROVISIONAL",
    )
    routed = route_phx1_structural_reasons(
        reasons, policy_mode=PHX1_STRUCTURAL_POLICY_SHADOW)
    assert routed.shadow_warning_reason_tokens == reasons
    assert routed.original_hard_block_reason_tokens == reasons
    assert routed.effective_phx1_policy_verdict \
        == EFFECTIVE_POLICY_ALLOW_WITH_SHADOW_WARNING


def test_one_non_shadowable_safety_failure_still_blocks():
    decision = evaluate_delivery_safety(
        fee_snapshot=_fee(PHX1_FEE_GATE_SCAM_LIKELY),
        existing_block_reasons=("DATA_GAP_UNRESOLVED",),
        phx1_structural_policy=PHX1_STRUCTURAL_POLICY_SHADOW,
    )
    assert decision.verdict == POLICY_HARD_BLOCK
    assert decision.non_shadowable_safety_reason_tokens == (
        "DATA_GAP_UNRESOLVED",)
    assert decision.final_block_reasons == ("DATA_GAP_UNRESOLVED",)
    assert not decision.manual_review_required


def test_unknown_reason_fails_closed():
    routed = route_phx1_structural_reasons(
        ("BRAND_NEW_UNCLASSIFIED_BLOCK",),
        policy_mode=PHX1_STRUCTURAL_POLICY_SHADOW,
    )
    assert routed.effective_phx1_policy_verdict == EFFECTIVE_POLICY_HARD_BLOCK
    assert routed.non_shadowable_safety_reason_tokens == (
        "BRAND_NEW_UNCLASSIFIED_BLOCK",)


def test_stale_fee_alone_shadows_but_final_market_stale_blocks():
    stale_fee = evaluate_delivery_safety(
        fee_snapshot=_fee(stale=True),
        phx1_structural_policy=PHX1_STRUCTURAL_POLICY_SHADOW,
    )
    assert stale_fee.original_hard_block_reason_tokens == (BLOCK_DATA_STALE,)
    assert stale_fee.effective_phx1_policy_verdict \
        == EFFECTIVE_POLICY_ALLOW_WITH_SHADOW_WARNING
    with_market_failure = evaluate_delivery_safety(
        fee_snapshot=_fee(stale=True),
        existing_block_reasons=("PHX1_MARKET_DATA_STALE",),
        phx1_structural_policy=PHX1_STRUCTURAL_POLICY_SHADOW,
    )
    assert with_market_failure.effective_phx1_policy_verdict \
        == EFFECTIVE_POLICY_HARD_BLOCK
    assert with_market_failure.final_block_reasons == (
        "PHX1_MARKET_DATA_STALE",)


@pytest.mark.parametrize(
    "reason",
    [
        "CANONICAL_MIGRATION_PROOF_REQUIRED",
        "MIGRATION_MINT_BINDING_INVALID",
        "CENTRAL_SECURITY_IDENTITY_MISMATCH",
    ],
)
def test_migration_and_identity_reasons_never_shadow(reason):
    routed = route_phx1_structural_reasons(
        (reason,), policy_mode=PHX1_STRUCTURAL_POLICY_SHADOW)
    assert routed.effective_phx1_policy_verdict == EFFECTIVE_POLICY_HARD_BLOCK


@pytest.mark.parametrize(
    "reason",
    [
        "DATA_GAP_UNRESOLVED",
        "PENDING_1_20X",
        "STRUCTURAL_COLLAPSE",
        "LIQUIDITY_LOST",
        "LIQUIDITY_COLLAPSE",
        "LP_CRITICALLY_LOW",
        "LIQUIDITY_USD_BELOW_MIN",
        "EFFECTIVE_RESERVE_MISMATCH",
    ],
)
def test_activation_data_gap_liquidity_loss_never_shadow(reason):
    assert route_phx1_structural_reasons(
        (reason,), policy_mode=PHX1_STRUCTURAL_POLICY_SHADOW
    ).effective_phx1_policy_verdict == EFFECTIVE_POLICY_HARD_BLOCK


@pytest.mark.parametrize(
    "reason",
    [
        "PHX1_FEE_GATE_DATA_INVALID",
        "PHX1_FEE_GATE_PROOF_INCONSISTENT",
        "SECURITY_DECISION_PROOF_INCONSISTENT",
        "NEGATIVE_NUMERIC_STATE",
        "NONFINITE_NUMERIC_STATE",
        "IMPOSSIBLE_RESERVE_STATE",
    ],
)
def test_invalid_numeric_and_proof_reasons_never_shadow(reason):
    assert route_phx1_structural_reasons(
        (reason,), policy_mode=PHX1_STRUCTURAL_POLICY_SHADOW
    ).effective_phx1_policy_verdict == EFFECTIVE_POLICY_HARD_BLOCK


@pytest.mark.parametrize(
    "reason",
    [
        "NO_SEND_MARKET_UNAVAILABLE",
        "CURRENT_MARKET_CAP_REQUIRED",
        "UNRESOLVED_MESSAGE_PLACEHOLDER",
        "AGE_MINUTES_INVALID",
        "ATH_DRAWDOWN_INCONSISTENT",
        "TIER_NOT_ELIGIBLE",
    ],
)
def test_message_and_current_market_failures_never_shadow(reason):
    assert route_phx1_structural_reasons(
        (reason,), policy_mode=PHX1_STRUCTURAL_POLICY_SHADOW
    ).effective_phx1_policy_verdict == EFFECTIVE_POLICY_HARD_BLOCK


@pytest.mark.parametrize(
    "reason",
    [
        "DUPLICATE_MIGRATION_APPLICATION",
        "DUPLICATE_CANDIDATE_APPLICATION",
        "DEDUPE_SUPPRESSED_DUPLICATE",
        "CANONICAL_LEDGER_DEDUPE_HIT",
        "CURSOR_INTEGRITY_FAILURE",
        "CENSUS_INTEGRITY_FAILURE",
        "RECONCILIATION_INTEGRITY_FAILURE",
        "CHECKPOINT_QUARANTINED",
    ],
)
def test_state_quarantine_and_duplicate_reasons_never_shadow(reason):
    assert route_phx1_structural_reasons(
        (reason,), policy_mode=PHX1_STRUCTURAL_POLICY_SHADOW
    ).effective_phx1_policy_verdict == EFFECTIVE_POLICY_HARD_BLOCK


@pytest.mark.parametrize(
    "reason",
    [
        "DELIVERY_UNKNOWN",
        "LEDGER_RESERVATION_FAILED",
        "LEDGER_COMMIT_FAILED",
        "MULTIPLE_TRANSPORT_ROUTING",
        "SEND_CAP_REACHED",
        "AUTHORIZATION_REQUIRED",
        "CONFIRMATION_REQUIRED",
    ],
)
def test_delivery_ledger_authorization_reasons_never_shadow(reason):
    assert route_phx1_structural_reasons(
        (reason,), policy_mode=PHX1_STRUCTURAL_POLICY_SHADOW
    ).effective_phx1_policy_verdict == EFFECTIVE_POLICY_HARD_BLOCK


def test_current_phx2_high_risk_terminal_never_shadows():
    routed = route_phx1_structural_reasons(
        ("SKIPPED_HIGH_RISK_DISCORD", "LIQUIDITY_COLLAPSE"),
        policy_mode=PHX1_STRUCTURAL_POLICY_SHADOW,
    )
    assert routed.effective_phx1_policy_verdict == EFFECTIVE_POLICY_HARD_BLOCK
    assert routed.shadow_warning_reason_tokens == ()


def test_all_fee_lifecycle_structural_tokens_route_together():
    reasons = (
        "PHX2_FEE_LIFECYCLE_IMMATURE",
        "PHX2_FEE_LIFECYCLE_PROVISIONAL",
        "PHX2_FEE_LIFECYCLE_TEMPORARILY_STALE",
        "PHX2_FEE_LIFECYCLE_DURABLE_SCAM_LOCK",
    )
    assert set(reasons) <= SHADOWABLE_STRUCTURAL_REASON_TOKENS
    routed = route_phx1_structural_reasons(
        reasons, policy_mode=PHX1_STRUCTURAL_POLICY_SHADOW)
    assert routed.shadow_warning_reason_tokens == reasons


def test_mixed_shadow_and_lifecycle_integrity_remains_blocked():
    routed = route_phx1_structural_reasons(
        (
            "PHX2_FEE_LIFECYCLE_TEMPORARILY_STALE",
            "PHX2_FEE_LIFECYCLE_STATE_INVALID",
        ),
        policy_mode=PHX1_STRUCTURAL_POLICY_SHADOW,
    )
    assert routed.effective_phx1_policy_verdict == EFFECTIVE_POLICY_HARD_BLOCK
    assert routed.non_shadowable_safety_reason_tokens == (
        "PHX2_FEE_LIFECYCLE_STATE_INVALID",)


def test_holder_ghost_token_is_structural_but_unverified():
    routed = route_phx1_structural_reasons(
        ("PHX1_GHOST_BLOCK",),
        policy_mode=PHX1_STRUCTURAL_POLICY_SHADOW,
    )
    assert routed.effective_phx1_policy_verdict \
        == EFFECTIVE_POLICY_ALLOW_WITH_SHADOW_WARNING
    assert routed.organicity_status == "UNVERIFIED"


def test_policy_proof_digest_detects_tampering():
    routed = route_phx1_structural_reasons(
        (BLOCK_SCAM_LIKELY,), policy_mode=PHX1_STRUCTURAL_POLICY_SHADOW)
    assert validate_phx1_structural_policy_decision(routed) == (True, None)
    forged = replace(routed, manual_review_required=False)
    assert validate_phx1_structural_policy_decision(forged) == (
        False, "PHX1_STRUCTURAL_POLICY_PROOF_INCONSISTENT")


def test_composite_proof_detects_effective_verdict_tampering():
    decision = evaluate_delivery_safety(
        fee_snapshot=_fee(PHX1_FEE_GATE_SCAM_LIKELY),
        phx1_structural_policy=PHX1_STRUCTURAL_POLICY_SHADOW,
    )
    forged = seal_delivery_decision(replace(
        decision, effective_phx1_policy_verdict=EFFECTIVE_POLICY_PASS))
    assert validate_delivery_decision(forged) == (
        False, SECURITY_DECISION_PROOF_INCONSISTENT)


def test_shadow_alert_includes_required_warning_text_and_exact_reasons():
    """2026-07-28 remediation: one compact operator policy line replaces the
    multi-line internal block.  The exact reason tokens, original verdict,
    organicity status, and manual-review flag stay on the artifact surface
    (TelegramPingData fields + the compose artifact), never in the body."""

    reasons = (
        "PHX1_FEE_GATE_SCAM_LIKELY",
        "PHX2_FEE_LIFECYCLE_DURABLE_SCAM_LOCK",
    )
    data = _ping_data(
        phx1_structural_policy_mode="SHADOW",
        original_phx1_structural_verdict="HARD_BLOCK",
        effective_phx1_policy_verdict="ALLOW_WITH_SHADOW_WARNING",
        shadow_warning_reasons=reasons,
        organicity_status="UNVERIFIED",
        manual_review_required=True,
        policy_reason_display="durable scam lock",
    )
    result = compose_telegram_ping(data)
    assert "• Policy: SHADOW BLOCK — durable scam lock" in result.text
    # The internal block never renders; the proofs stay structured.
    assert "PHX1 STRUCTURAL POLICY" not in result.text
    assert "ORIGINAL STRUCTURAL VERDICT" not in result.text
    assert "SHADOW REASONS:" not in result.text
    assert "PHX1_FEE_GATE_SCAM_LIKELY" not in result.text
    assert "ORGANICITY" not in result.text
    assert "MANUAL REVIEW REQUIRED" not in result.text
    assert data.shadow_warning_reasons == reasons
    assert data.original_phx1_structural_verdict == "HARD_BLOCK"
    assert data.organicity_status == "UNVERIFIED"
    assert data.manual_review_required is True
    assert result.rendered_character_count <= TELEGRAM_INTERNAL_MAX_CHARACTERS


def test_pass_alert_is_not_falsely_shadow_blocked():
    result = compose_telegram_ping(_ping_data(
        fee_gate_label="Normal",
        fee_gate_score="0",
    ))
    # A structural PASS renders no policy footer at all.
    assert "Policy:" not in result.text
    assert "PHX1 STRUCTURAL POLICY" not in result.text
    assert "SHADOW BLOCK" not in result.text
    assert "MANUAL REVIEW REQUIRED" not in result.text


def test_shadow_warning_overlength_raises_before_transport():
    # The raw reason tokens no longer render, so overlength pressure comes
    # from the rendered policy phrase itself; the composer length guard must
    # still fire before any transport.
    with pytest.raises(TelegramMessageTooLong):
        compose_telegram_ping(_ping_data(
            phx1_structural_policy_mode="SHADOW",
            original_phx1_structural_verdict="HARD_BLOCK",
            effective_phx1_policy_verdict="ALLOW_WITH_SHADOW_WARNING",
            shadow_warning_reasons=("PHX1_FEE_GATE_SCAM_LIKELY",),
            manual_review_required=True,
            policy_reason_display="X" * 4000,
        ))


def test_shadow_overlength_adapter_classifies_without_transport_attempt(monkeypatch):
    # Overlength pressure now comes through the rendered policy phrase (raw
    # reason tokens stay artifact-only); the adapter must still classify the
    # shadow-expected overlength without any transport attempt.
    data = _ping_data(
        phx1_structural_policy_mode="SHADOW",
        original_phx1_structural_verdict="HARD_BLOCK",
        effective_phx1_policy_verdict="ALLOW_WITH_SHADOW_WARNING",
        shadow_warning_reasons=("PHX1_FEE_GATE_SCAM_LIKELY",),
        manual_review_required=True,
        policy_reason_display="X" * 4000,
    )

    class NeverTransport:
        calls = 0

        def send_html(self, _text):
            self.calls += 1
            raise AssertionError("overlength_must_not_call_transport")

        def close(self):
            pass

    transport = NeverTransport()
    adapter = TelegramDeliveryAdapter(transport, console_sink=None)
    monkeypatch.setattr(
        adapter_module, "build_ping_data", lambda **_kwargs: data)
    adapter.bind_delivery(
        body="bound",
        mint=MINT,
        composed_snapshot=object(),
        delivery_context={},
        created_at_utc="2026-07-25T00:00:00Z",
    )
    result = adapter.send_one_audited_post(
        webhook_identity=None, payload={"content": "bound"})
    assert result.transport_status == MESSAGE_LENGTH_LIMIT_EXCEEDED
    assert result.send_attempt_count == 0
    assert transport.calls == 0


def test_shadow_artifact_contains_only_expected_safe_review_fields():
    decision = evaluate_delivery_safety(
        fee_snapshot=_fee(PHX1_FEE_GATE_SCAM_LIKELY),
        phx1_structural_policy=PHX1_STRUCTURAL_POLICY_SHADOW,
    )
    artifact = build_shadow_candidate_artifact(
        decision=decision,
        candidate={
            "token_mint": MINT,
            "candidate_id": "candidate-safe",
            "migration_slot": 123,
            "migration_time_utc": "2026-07-25T00:00:00Z",
        },
        record={
            "token_mint": MINT,
            "reason": "COMPOSED_NO_TRANSPORT",
            "compose_attempted": True,
            "compose_tier": 2,
            "activation": {
                "first_crossing_slot": 456,
                "first_crossing_timestamp": "2026-07-25T00:01:00Z",
            },
            "market_context": {"market_state": "FRESH"},
        },
        entry=SimpleNamespace(token_mint=MINT),
        observed_at_utc="2026-07-25T00:02:00Z",
        fee_gate_lifecycle={"lifecycle_state": "FRESH_CONFIRMED"},
    )
    assert artifact is not None
    assert artifact["token_mint"] == MINT
    assert artifact["manual_review_required"] is True
    assert artifact["operator_label"] is None
    assert artifact["later_outcome"] is None
    assert artifact["phx1_policy_digest"] == decision.phx1_policy_digest
    serialized = json.dumps(artifact, sort_keys=True)
    for forbidden in ("transaction_signature", "endpoint", "response_body"):
        assert forbidden not in serialized


def test_non_shadow_candidate_does_not_create_review_artifact():
    decision = evaluate_delivery_safety(fee_snapshot=_fee())
    assert build_shadow_candidate_artifact(
        decision=decision,
        candidate={"token_mint": MINT},
        record={"token_mint": MINT},
        entry=SimpleNamespace(token_mint=MINT),
        observed_at_utc="2026-07-25T00:00:00Z",
    ) is None


def test_filter_result_policy_metadata_keeps_original_result_rows():
    rows = [
        {
            "filter_name": "fee_gate_v2_score",
            "result": "HARD_BLOCK",
            "reason_token": BLOCK_SCAM_LIKELY,
        }
    ]
    metadata = policy_metadata_for_filter_results(
        rows, policy_mode=PHX1_STRUCTURAL_POLICY_SHADOW)
    assert rows[0]["result"] == "HARD_BLOCK"
    assert metadata["original_phx1_structural_verdict"] == "HARD_BLOCK"
    assert metadata["effective_phx1_policy_verdict"] \
        == EFFECTIVE_POLICY_ALLOW_WITH_SHADOW_WARNING
    assert metadata["policy_version"] == PHX1_STRUCTURAL_POLICY_VERSION


def test_policy_matrix_matches_closed_shadow_allowlist():
    matrix = json.loads(MATRIX.read_text(encoding="utf-8"))
    structural = {
        token
        for blocker in matrix["blockers"]
        if blocker["policy_classification"] == "SHADOWABLE_STRUCTURAL"
        for token in blocker["reason_tokens"]
    }
    assert structural == SHADOWABLE_STRUCTURAL_REASON_TOKENS
    assert matrix["policy"]["default"] == "ENFORCE"
    assert matrix["policy"]["modes"] == ["ENFORCE", "SHADOW"]


def test_five_token_and_holdout_frozen_routing():
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    results = {}
    for row in fixture["records"]:
        routed = route_phx1_structural_reasons(
            row["original_hard_block_reason_tokens"],
            policy_mode=PHX1_STRUCTURAL_POLICY_SHADOW,
        )
        assert routed.effective_phx1_policy_verdict \
            == row["expected_shadow_effective_verdict"]
        results[row["mint"]] = routed
    manipulated = [
        row for row in fixture["records"]
        if row["label"] == "MANIPULATED_COORDINATED"
    ]
    assert len(manipulated) == 4
    assert all(
        results[row["mint"]].effective_phx1_policy_verdict
        == EFFECTIVE_POLICY_HARD_BLOCK
        for row in manipulated
    )


def test_organic_8s8_converts_only_its_shadowable_fee_reason():
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    row = next(
        item for item in fixture["records"]
        if item["label"] == "ORGANIC_CONTROL"
    )
    routed = route_phx1_structural_reasons(
        row["original_hard_block_reason_tokens"],
        policy_mode=PHX1_STRUCTURAL_POLICY_SHADOW,
    )
    assert routed.original_phx1_structural_verdict == "HARD_BLOCK"
    assert routed.shadow_warning_reason_tokens == (BLOCK_DATA_STALE,)
    assert routed.effective_phx1_policy_verdict \
        == EFFECTIVE_POLICY_ALLOW_WITH_SHADOW_WARNING


def test_stage8_holdout_remains_true_pass():
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    row = next(
        item for item in fixture["records"]
        if item["label"] == "STAGE8_HOLDOUT"
    )
    routed = route_phx1_structural_reasons(
        row["original_hard_block_reason_tokens"],
        policy_mode=PHX1_STRUCTURAL_POLICY_SHADOW,
    )
    assert row["mint"] == "CLiSoY33WTemQYg4SJQ1oDiCcJ1YWKaVPNLUPshepump"
    assert routed.original_phx1_structural_verdict == "PASS"
    assert routed.effective_phx1_policy_verdict == EFFECTIVE_POLICY_PASS
    assert not routed.manual_review_required


def test_no_production_mint_specific_logic_was_added():
    source = (
        Path(__file__).resolve().parents[1]
        / "free_tier_producer"
        / "phx1_structural_policy.py"
    ).read_text(encoding="utf-8")
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert all(row["mint"] not in source for row in fixture["records"])


def test_switching_policy_requires_only_explicit_value_change():
    enforce = route_phx1_structural_reasons(
        (BLOCK_SCAM_LIKELY,), policy_mode="enforce")
    shadow = route_phx1_structural_reasons(
        (BLOCK_SCAM_LIKELY,), policy_mode="shadow")
    assert enforce.original_hard_block_reason_tokens \
        == shadow.original_hard_block_reason_tokens
    assert enforce.effective_phx1_policy_verdict == EFFECTIVE_POLICY_HARD_BLOCK
    assert shadow.effective_phx1_policy_verdict \
        == EFFECTIVE_POLICY_ALLOW_WITH_SHADOW_WARNING


def test_send_time_shadow_refresh_preserves_bound_safety_reasons():
    from PHX2.free_tier_producer.fee_gate_lifecycle import (
        make_fee_gate_send_time_gate,
    )
    from PHX2.free_tier_producer.scam_policy import SecurityDecisionIndex

    fee_snapshot = _fee(PHX1_FEE_GATE_SCAM_LIKELY)
    security_index = SecurityDecisionIndex()
    bound = evaluate_delivery_safety(
        fee_snapshot=fee_snapshot,
        existing_block_reasons=("PHX2_RISK_HIGH",),
        phx1_structural_policy=PHX1_STRUCTURAL_POLICY_SHADOW,
    )
    security_index.bind(bound)

    class FeeIndex:
        def snapshot(self, mint, *, now_epoch, max_age_seconds):
            assert mint == MINT
            return fee_snapshot

    class LifecycleIndex:
        def observe(self, snapshot, *, now_epoch):
            assert snapshot is fee_snapshot
            return SimpleNamespace(
                effective_snapshot=fee_snapshot,
                send_block_reasons=(
                    "PHX2_FEE_LIFECYCLE_TEMPORARILY_STALE",
                ),
            )

        def send_time_block_reason(self, *, view, bound_decision, now_epoch):
            assert bound_decision is bound
            return "PHX2_FEE_LIFECYCLE_TEMPORARILY_STALE"

    gate = make_fee_gate_send_time_gate(
        fee_index=FeeIndex(),
        lifecycle_index=LifecycleIndex(),
        security_index=security_index,
        max_age_seconds="300",
        now_epoch_fn=lambda: 1000,
        phx1_structural_policy=PHX1_STRUCTURAL_POLICY_SHADOW,
    )
    assert gate(MINT) == "PHX2_RISK_HIGH"
    refreshed = security_index.get(MINT)
    assert "PHX2_RISK_HIGH" in refreshed.original_hard_block_reason_tokens
    assert "PHX2_RISK_HIGH" in refreshed.non_shadowable_safety_reason_tokens
    assert "PHX2_FEE_LIFECYCLE_TEMPORARILY_STALE" \
        in refreshed.original_hard_block_reason_tokens
    assert refreshed.effective_phx1_policy_verdict \
        == EFFECTIVE_POLICY_HARD_BLOCK
    assert not refreshed.final_candidate_eligibility

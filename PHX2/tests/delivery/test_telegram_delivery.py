from __future__ import annotations

import hashlib
from decimal import Decimal
from types import SimpleNamespace

from PHX2.delivery.telegram_adapter import TelegramDeliveryAdapter
from PHX2.delivery.telegram_transport import (
    MESSAGE_REJECTED,
    SENT_OK,
    TelegramTransportResult,
)
from PHX2.free_tier_producer import free_tier_session
from PHX2.free_tier_producer.ath_state import (
    ATH_OBSERVATION_SEAL_SCHEMA_VERSION,
    build_ath_observation_seal_digest,
)
from PHX2.free_tier_producer.compat.build30_watchlist import (
    ACTIVATION_EVIDENCE_SCHEMA_VERSION,
    ACTIVATION_EVIDENCE_SPOT_VERSION,
    ACTIVATION_KIND_SPOT_CURRENT,
    build_activation_evidence_digest,
    build_activation_spot_evidence_digest,
    build_migration_baseline_digest,
)
from PHX2.stage30.stage30_11_13_committed_no_send_composer import (
    COMPOSE_DECISION_DISPATCHED,
    COMPOSE_DECISION_REJECTED,
    COMPOSE_REASON_NO_SEND_DISPATCH_RECORDED,
    COMPOSE_REJECTED_DEDUPE_SUPPRESSED,
    Stage30_11_13ComposedSnapshot,
    Stage30_11_13ComposeResult,
    Stage30_11_13GateBindingKey,
)
from PHX2.stage30.stage30_11_15_no_send_dedupe_guard import (
    Stage30_11_15DedupedComposeResult,
)
from PHX2.stage30.stage30_11_15_ping_dedupe_models import (
    DEDUPE_REASON_DUPLICATE_WITHIN_TTL,
    DEDUPE_REASON_NEW_KEY,
    allowed_outcome,
    suppressed_outcome,
)
from PHX2.stage30.stage30_11_16_fake_real_send_proof import (
    default_real_send_authorization,
)
from PHX2.stage30.stage30_11_16_real_private_transport_guard import (
    make_stage30_11_16_real_private_transport_guard,
)


MINT = "DC4sure5XanGz2Te2UNPAKR2iAkshzYqvsv3coH4pump"
CREATED = "2026-07-16T12:00:00Z"
LEGACY_BODY = "legacy body must never reach Telegram"
compose_send = free_tier_session.cs


def _snapshot() -> Stage30_11_13ComposedSnapshot:
    binding = Stage30_11_13GateBindingKey(
        token_mint=MINT, tier_token="Tier 3", drawdown_from_ath=Decimal("82"),
        current_market_cap_usd=Decimal("10000"), migration_status="PRESENT",
        ath_status="PRESENT", post_migration_ath_verified=True,
        created_at_utc=CREATED,
    )
    return Stage30_11_13ComposedSnapshot(
        token_mint=MINT, candidate_id="candidate-1", symbol_or_name="PHX",
        created_at_utc=CREATED, snapshot_id="snapshot-1", tier_token="Tier 3",
        drawdown_from_ath=Decimal("82"), current_market_cap_usd=Decimal("10000"),
        migration_status="PRESENT", ath_status="PRESENT",
        market_context_status="PRESENT", post_migration_ath_verified=True,
        market_context_fetched_at_utc="2026-07-16T11:59:59Z",
        market_context_max_age_seconds=300, market_context_freshness_status="FRESH",
        current_price="0.00001", ath_price="0.000057", liquidity_usd="7000",
        migration_confirmed=True, migration_time_utc="2026-07-16T11:38:00Z",
        migration_source="GRPC_EVENT", age_display="0.4h", basis_display="PRICE",
        market_cap_display="$10k", liquidity_display="$7k",
        ath_market_cap_display="$57k", absolute_drawdown="82",
        fractional_drop_pct="82.00%", tier_band_display=None,
        ath_source_stage="CENTRAL_ATH", time_from_unix=None, time_to_unix=None,
        ohlcv_type=None, span_seconds=None, ath_source_ref="GRPC_EVENT",
        gate_binding_key=binding,
    )


def _deduped(*, duplicate=False) -> Stage30_11_15DedupedComposeResult:
    compose = Stage30_11_13ComposeResult(
        decision=(COMPOSE_DECISION_REJECTED if duplicate else COMPOSE_DECISION_DISPATCHED),
        reason=(COMPOSE_REJECTED_DEDUPE_SUPPRESSED
                if duplicate else COMPOSE_REASON_NO_SEND_DISPATCH_RECORDED),
        token_mint=MINT, candidate_id="candidate-1", created_at_utc=CREATED,
        snapshot=_snapshot(), dispatched_body=(None if duplicate else LEGACY_BODY),
    )
    outcome = (
        suppressed_outcome(DEDUPE_REASON_DUPLICATE_WITHIN_TTL)
        if duplicate else allowed_outcome(DEDUPE_REASON_NEW_KEY)
    )
    return Stage30_11_15DedupedComposeResult(
        compose_result=compose, dedupe_outcome=outcome)


def _delivery_context():
    fee = SimpleNamespace(
        candidate_mint=MINT, proof_digest="fee-proof-digest",
        total_fees=Decimal("9.67"), lp_fees=Decimal("0.90"),
        protocol_fees=Decimal("3.72"), creator_fees=Decimal("5.05"),
        event_pace_per_minute=Decimal("27"), event_count=1809,
        fee_gate_label="Elevated", fee_gate_score=1,
        fee_gate_reasons=("sticky_lock",), balanced_fees=False,
        bribe_share_pct=Decimal("5.21"), creator_share=Decimal("0.522"),
        bribes_per_transaction=Decimal("0.000278478"),
        first_observed_at_utc="2026-07-16T10:23:18Z",
        last_observed_at_utc=CREATED,
        ante_last20_median=Decimal("0.000005"),
        ante_last20_p25=Decimal("0.000005"),
        ante_last20_p75=Decimal("0.0001605"),
        ante_last20_sample_count=20,
        ante_5m_median=Decimal("0.000046"),
        ante_5m_p25=Decimal("0.00000079"),
        ante_5m_p75=Decimal("0.000045899"),
        ante_5m_sample_count=134, ante_5m_base_fee_coverage=Decimal("1"),
        priority_fee_median_lamports=7074, priority_fee_sample_count=20,
        ante_5m_shape="ORGANIC", ante_5m_shape_rule="5",
        ante_last20_shape="AMBIGUOUS", ante_last20_shape_rule="6",
    )
    lp = SimpleNamespace(
        candidate_mint=MINT, proof_digest="lp-proof-digest",
        lp_integrity="PASS", lp_integrity_reasons=(),
    )
    security = SimpleNamespace(
        fee_snapshot=fee, lp_snapshot=lp, proof_digest="security-proof-digest",
        verdict="ALLOW",
    )
    activation = {
        "token_mint": MINT,
        "candidate_id": "telegram-delivery-fixture",
        "migration_time_utc": "2026-07-16T11:38:00Z",
        "activation_state": "ACTIVE_DIP_WATCH",
        "migration_baseline_status": "CAPTURED",
        "activation_multiplier": "1.20",
        "migration_market_cap_usd": "32000",
        "migration_market_cap_observed_at_utc": "2026-07-16T11:38:00Z",
        "migration_market_cap_source": "GRPC_EVENT",
        "migration_market_cap_price": "0.000032",
        "migration_supply_at_observation": "1000000000",
        "activation_target_market_cap_usd": "38400.00",
        "activation_current_market_cap_usd": "40000",
        "activated_at_utc": "2026-07-16T11:45:01Z",
        "activation_observation_source": "PAID_MARKET_PRIMARY",
        "activation_proven": True,
        "activation_observation_fresh": True,
        "activation_evidence_source": "PAID_MARKET_PRIMARY",
        "activation_evidence_market_cap_usd": "40000",
        "activation_evidence_event_at_utc": "2026-07-16T11:45:00Z",
        "activation_evidence_ingested_at_utc": "2026-07-16T11:45:01Z",
        "activation_evidence_version": ACTIVATION_EVIDENCE_SPOT_VERSION,
        "activation_proof_version": ACTIVATION_EVIDENCE_SCHEMA_VERSION,
        "activation_evidence_kind": ACTIVATION_KIND_SPOT_CURRENT,
        "activation_crossing_tick_digest": "c" * 64,
        "activation_crossing_tick_blocked": True,
        "activation_latched": True,
    }
    activation["activation_evidence_digest"] = (
        build_activation_spot_evidence_digest(
            mint=MINT, market_cap=Decimal("40000"),
            event_at_utc=activation["activation_evidence_event_at_utc"],
            source=activation["activation_evidence_source"],
        )
    )
    activation["activation_source_evidence_digest"] = activation[
        "activation_evidence_digest"]
    activation["migration_baseline_digest_version"] = (
        "phx2_migration_baseline_digest_v1")
    activation["migration_baseline_digest"] = build_migration_baseline_digest(
        token_mint=MINT, candidate_id=activation["candidate_id"],
        market_cap_usd=activation["migration_market_cap_usd"],
        observed_at_utc=activation["migration_market_cap_observed_at_utc"],
        source=activation["migration_market_cap_source"],
        price=activation["migration_market_cap_price"],
        supply=activation["migration_supply_at_observation"])
    activation["activation_observation_seal_version"] = (
        ATH_OBSERVATION_SEAL_SCHEMA_VERSION)
    activation["activation_observation_seal_digest"] = (
        build_ath_observation_seal_digest(MINT, {
            "ath_evidence_digest": activation["activation_evidence_digest"],
            "ath_ingested_at_utc": activation[
                "activation_evidence_ingested_at_utc"],
            "ath_observation_seal_validated": True,
        }))
    activation["activation_proof_digest"] = build_activation_evidence_digest(
        token_mint=MINT,
        candidate_id=activation["candidate_id"],
        migration_baseline_digest=activation["migration_baseline_digest"],
        migration_market_cap_usd=activation["migration_market_cap_usd"],
        migration_market_cap_observed_at_utc=(
            activation["migration_market_cap_observed_at_utc"]),
        activation_target_market_cap_usd=activation["activation_target_market_cap_usd"],
        activation_evidence_market_cap_usd=activation["activation_evidence_market_cap_usd"],
        activation_evidence_event_at_utc=activation["activation_evidence_event_at_utc"],
        activation_evidence_ingested_at_utc=(
            activation["activation_evidence_ingested_at_utc"]),
        activated_at_utc=activation["activated_at_utc"],
        activation_evidence_source=activation["activation_evidence_source"],
        activation_evidence_kind=activation["activation_evidence_kind"],
        activation_source_evidence_digest=activation["activation_evidence_digest"],
        activation_source_evidence_version=activation["activation_evidence_version"],
        activation_observation_seal_digest=(
            activation["activation_observation_seal_digest"]),
        activation_observation_seal_version=(
            activation["activation_observation_seal_version"]),
        activation_crossing_tick_digest=activation["activation_crossing_tick_digest"],
    )
    return {
        "candidate": {
            "token_mint": MINT,
            "discovery_provenance": "DEXSCREENER_RESTART_BACKFILL",
            "token_name": "NOngWAn",
            "symbol_or_name": "WAN",
            "migration_time_utc": "2026-07-16T11:38:00Z",
            # The production engine wrapper threads the current lifecycle
            # artifact into the candidate dict; the compose artifact must
            # reference the same lifecycle/evidence version.
            "fee_gate_lifecycle": {
                "lifecycle_version": "PHX2_FEE_GATE_LIFECYCLE_V1",
                "lifecycle_state": "FRESH_CONFIRMED",
                "evidence_proof_digest": "fee-proof-digest",
            },
        },
        "market_context": {
            "current_market_cap_usd": "10000", "liquidity_usd": "7000",
            "central_ath": {"ath_market_cap": "57000", "ath_provider": "GRPC_EVENT"},
            "risk_assessment": {
                "risk_label": "RISK_MEDIUM", "risk_reasons": ["LP_FALLING"]},
        },
        "activation": activation,
        "security_decision": security,
        "volume_classifier": "Spiking",
        "liquidity_quality": "Low",
    }


class FakeTelegramTransport:
    def __init__(self, *, ok=True):
        self.ok = ok
        self.messages = []
        self.closed = False

    def send_html(self, text):
        self.messages.append(text)
        return TelegramTransportResult(
            ok=self.ok,
            transport_status=(SENT_OK if self.ok else MESSAGE_REJECTED),
            message_id=(777 if self.ok else None),
            destination_alias="PHOENIX_CHANNEL",
            attempted_at_utc=CREATED,
            delivered_at_utc=(CREATED if self.ok else None),
            retry_count=0,
            safe_error_category=(None if self.ok else MESSAGE_REJECTED),
            send_attempt_count=1,
        )

    def close(self):
        self.closed = True


def _run(monkeypatch, transport, *, duplicate=False):
    composed = []
    attempts = []
    adapter = TelegramDeliveryAdapter(
        transport, compose_sink=composed.append, attempt_sink=attempts.append,
        console_sink=None,
    )
    monkeypatch.setattr(
        compose_send, "compose_no_send_dispatch_deduped",
        lambda *args, **kwargs: _deduped(duplicate=duplicate),
    )
    guard = make_stage30_11_16_real_private_transport_guard(transport=adapter)
    context = _delivery_context()
    result = compose_send.compose_and_maybe_send(
        SimpleNamespace(token_mint=MINT), ath_transport=None,
        ath_endpoint_secret=None, now_utc=None, now_seconds=None, ledger=object(),
        guard=guard, authorization=default_real_send_authorization(
            created_at_utc=CREATED), created_at_utc=CREATED,
        axiom_fee_appender=adapter, activation_proof=context["activation"],
        security_decision=None, delivery_context=context,
    )
    return result, adapter, composed, attempts


def test_eligible_delivery_sends_one_exact_telegram_body_and_keeps_source_proofs(monkeypatch):
    transport = FakeTelegramTransport()
    result, adapter, composed, attempts = _run(monkeypatch, transport)
    assert result["eligible"] is True
    assert result["send_result"].transport_attempted is True
    assert result["send_result"].transport_ok is True
    assert len(transport.messages) == len(composed) == len(attempts) == 1
    text = transport.messages[0]
    assert LEGACY_BODY not in text
    assert text.splitlines()[0] == (
        "<b>🔥 PHOENIX — NOngWAn ($WAN) [Tier 3]</b>")
    assert f"<code>{MINT}</code>" in text
    # A DEXSCREENER_RESTART_BACKFILL candidate has evidence only since its
    # admission: the body must label the observed maximum honestly and carry
    # the compact coverage disclosure instead of claiming a complete
    # Post-mig ATH (2026-07-27 live-quality remediation; compact operator
    # wording from the 2026-07-28 alert-quality remediation).
    assert "MC: $10k | Obs ATH: $57k | Mig: $32k" in text
    assert "Post-mig ATH" not in text
    # The coverage disclosure is provider-neutral so the rendered body never
    # carries the provider-name needle the runtime redaction scanner bans.
    assert "• Coverage: Partial (restart backfill)" in text
    assert "PARTIAL_SINCE_ADMISSION" not in text
    assert "DEXSCREENER" not in text
    assert "Floor: -82%" in text
    assert "Fee Gate:" not in text
    # 2026-07-29 final cleanup: internal subsystem rows and the Participation
    # section render nowhere; risk renders operator wording only.
    assert "LP Integrity" not in text
    assert "Composite" not in text
    assert "Risk: Medium — LP falling" in text
    assert "RISK_MEDIUM" not in text
    assert "LP_FALLING" not in text
    assert "Participation" not in text
    assert "SOL/min" not in text
    assert "Events:" not in text
    assert "Shape (5m):" not in text
    assert "Late-sequence stress state" not in text
    assert "Discovery alert · no paper fill implied" in text
    artifact = composed[0]
    telemetry = artifact["observe_only_telemetry"]
    participation = telemetry["participation"]
    assert participation["total_fees_sol"] == "9.67"
    assert participation["lp_fees_sol"] == "0.90"
    assert participation["protocol_fees_sol"] == "3.72"
    assert participation["creator_fees_sol"] == "5.05"
    assert participation["event_count"] == 1809
    assert participation["fee_evidence_valid"] is True
    assert participation["rendered_in_telegram"] is False
    assert telemetry["global_fee_support"]["observe_only"] is True
    assert telemetry["global_fee_support"]["rule_version"] == (
        "GLOBAL_FEE_SUPPORT_V1")
    assert telemetry["structure_evidence"]["fee_gate_label"] == "Elevated"
    assert telemetry["lp_integrity"] == "PASS"
    assert telemetry["composite_verdict"] == "PASS"
    assert artifact["token_identity"] == "NOngWAn ($WAN)"
    assert artifact["token_metadata_source"] == "DEXSCREENER_RESTART_BACKFILL"
    assert artifact["discovery_provenance"] == "DEXSCREENER_RESTART_BACKFILL"
    assert artifact["ath_coverage"] == "PARTIAL_SINCE_ADMISSION"
    assert artifact["token_metadata"]["metadata_pending_at_compose"] is False
    assert artifact["age_display"] == "22m"
    assert "text" not in artifact
    proofs = artifact["source_proofs"]
    assert {
        "security_decision_digest": "security-proof-digest",
        "fee_gate_digest": "fee-proof-digest",
        "lp_integrity_digest": "lp-proof-digest",
        "fee_gate_lifecycle_version": "PHX2_FEE_GATE_LIFECYCLE_V1",
        "fee_gate_lifecycle_state": "FRESH_CONFIRMED",
        "fee_gate_lifecycle_evidence_digest": "fee-proof-digest",
        "central_ath_market_cap": "57000",
        "migration_market_cap_usd": "32000",
        "activation_state": "ACTIVE_DIP_WATCH",
    }.items() <= proofs.items()
    assert proofs["activation_evidence_market_cap_usd"] == "40000"
    assert proofs["activation_evidence_source"] == "PAID_MARKET_PRIMARY"
    assert proofs["activation_evidence_kind"] == ACTIVATION_KIND_SPOT_CURRENT
    assert proofs["activation_evidence_version"] == ACTIVATION_EVIDENCE_SPOT_VERSION
    assert len(proofs["activation_evidence_digest"]) == 64
    assert proofs["activation_proof_version"] == ACTIVATION_EVIDENCE_SCHEMA_VERSION
    assert len(proofs["activation_proof_digest"]) == 64
    assert proofs["activation_latched"] is True
    assert proofs["risk_label"] == "RISK_MEDIUM"
    assert proofs["risk_reasons"] == ["LP_FALLING"]
    assert artifact["builder_read"][0] == {
        "statement": "Late-sequence stress state",
        "reason_codes": ["FEE_GATE_STICKY_LOCK"],
    }
    assert attempts[0]["result"] == SENT_OK
    assert attempts[0]["message_id"] == 777
    assert adapter.last_result is not None and adapter.last_result.ok


def test_pending_metadata_state_is_disclosed_in_the_compose_artifact(monkeypatch):
    transport = FakeTelegramTransport()
    composed = []
    adapter = TelegramDeliveryAdapter(
        transport, compose_sink=composed.append, console_sink=None)
    monkeypatch.setattr(
        compose_send, "compose_no_send_dispatch_deduped",
        lambda *args, **kwargs: _deduped(),
    )
    guard = make_stage30_11_16_real_private_transport_guard(transport=adapter)
    context = _delivery_context()
    context["candidate"]["canonical_token_metadata"] = {
        "token_mint": MINT,
        "token_name": None,
        "token_symbol": None,
        "metadata_status": "PENDING",
        "metadata_source": None,
        "metadata_first_requested_at": CREATED,
        "metadata_attempt_count": 2,
        "metadata_failure_reason": "SOURCE_FIELDS_EMPTY_OR_INVALID",
        "validated": False,
    }
    compose_send.compose_and_maybe_send(
        SimpleNamespace(token_mint=MINT), ath_transport=None,
        ath_endpoint_secret=None, now_utc=None, now_seconds=None, ledger=object(),
        guard=guard, authorization=default_real_send_authorization(
            created_at_utc=CREATED), created_at_utc=CREATED,
        axiom_fee_appender=adapter, activation_proof=context["activation"],
        security_decision=None, delivery_context=context,
    )
    metadata = composed[0]["token_metadata"]
    assert metadata["metadata_pending_at_compose"] is True
    assert metadata["metadata_status"] == "PENDING"
    assert metadata["metadata_attempt_count"] == 2
    # An unvalidated pending state never resolves the title; the candidate's
    # own backfill fields still do (independent precedence branch).
    assert composed[0]["token_identity"] == "NOngWAn ($WAN)"


def test_failed_delivery_is_not_sent_ok_and_duplicate_never_calls_transport(monkeypatch):
    failed_transport = FakeTelegramTransport(ok=False)
    failed, _, _, attempts = _run(monkeypatch, failed_transport)
    assert failed["send_result"].transport_ok is False
    assert attempts[0]["result"] == MESSAGE_REJECTED
    assert attempts[0]["message_id"] is None

    duplicate_transport = FakeTelegramTransport()
    duplicate, _, composed, duplicate_attempts = _run(
        monkeypatch, duplicate_transport, duplicate=True)
    assert duplicate["eligible"] is False and duplicate["send_result"] is None
    assert duplicate_transport.messages == []
    assert composed == [] and duplicate_attempts == []


def test_delivery_adapter_has_no_frozen_ledger_or_discord_side_effect(monkeypatch, tmp_path):
    frozen = tmp_path / "frozen.jsonl"
    frozen.write_text("frozen-ledger-sentinel\n", encoding="utf-8")
    before = hashlib.sha256(frozen.read_bytes()).hexdigest()
    transport = FakeTelegramTransport()
    _, adapter, composed, attempts = _run(monkeypatch, transport)
    adapter.close()
    assert hashlib.sha256(frozen.read_bytes()).hexdigest() == before
    assert transport.closed is True
    serialized = repr(composed) + repr(attempts)
    assert "DISCORD" not in serialized and "discord" not in serialized

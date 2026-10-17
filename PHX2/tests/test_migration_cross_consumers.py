"""One sealed migration proof, consumed consistently across the pipeline.

Chains the real seams end to end, offline: gRPC admission -> provider
candidate handoff -> watchlist seed -> decoupled baseline observation ->
liquidity-verifier decode -> LP-integrity classification -> composite security
policy -> display line -> watch-state checkpoint round-trip (the artifact the
paper engine and dashboard tail).  No network, no transport, no ledger.
"""

from types import SimpleNamespace

import pytest

from PHX2.free_tier_producer import paid_grpc_source as source_module
from PHX2.free_tier_producer import free_tier_session as producer_session
from PHX2.free_tier_producer.compat.build30_watchlist import (
    BASELINE_CAPTURED,
    WATCH_PENDING_1_20X,
    WATCH_PENDING_BASELINE,
    Watchlist,
)
from PHX2.free_tier_producer.liquidity_integrity import (
    INVALID_POOL_AUTHORITY,
    LP_INTEGRITY_PASS,
    LiquidityIntegrityIndex,
    validate_lp_snapshot,
)
from PHX2.free_tier_producer.liquidity_verifier import decode_liquidity_update
from PHX2.free_tier_producer.migration_admission import (
    MigrationProofStore,
    validate_migration_proof,
)
from PHX2.free_tier_producer.paid_provider import (
    ProviderCandidateDedupe,
    SingleGrpcPumpSwapDiscovery,
    event_to_candidate,
)
from PHX2.free_tier_producer.scam_policy import SecurityDecisionIndex
from PHX2.tests.test_migration_admission import (
    DIRECT_QUOTE_RAW,
    DUST_QUOTE_RAW,
    MINT,
    build_pool_creation_update,
)


NOW = "2026-07-17T12:00:00Z"
SOON = "2026-07-17T12:00:10Z"
LATER = "2026-07-17T12:01:00Z"


@pytest.fixture
def stage28_payload_tail(monkeypatch):
    """Replace only the Stage 28 payload projection so the REAL admission and
    quartet extraction still run inside decode_create_pool_update."""

    def fake_decode_baseline(_update, *, provider_name):
        return SimpleNamespace(
            provider_event_id="prov-evt-1", provider_name=provider_name,
            source_kind="GRPC", event_type="CREATE_POOL",
            observed_at_utc=NOW, slot=433450471, signature="sig-1",
            decoded_fields={}, chain="solana")

    def fake_build_payload(**kwargs):
        return kwargs

    def fake_project(payload):
        return SimpleNamespace(
            base_mint=payload["base_mint"], mint=payload["mint"],
            pool_account=payload["pool_account"],
            pool_program_id=payload["pool_program_id"],
            quote_mint=payload["quote_mint"], event_id="evt-1",
            provider_event_id=payload["provider_event_id"],
            observed_at_utc=payload["observed_at_utc"],
            raw_event_hash="hash-1")

    monkeypatch.setattr(source_module, "decode_subscribe_update_to_payload",
                        fake_decode_baseline)
    monkeypatch.setattr(source_module, "build_chainstack_yellowstone_payload",
                        fake_build_payload)
    monkeypatch.setattr(source_module, "project_payload_to_normalized_event",
                        fake_project)


def test_one_sealed_proof_flows_through_every_consumer(
        stage28_payload_tail, tmp_path):
    decisions = []
    admitted_event = source_module.decode_create_pool_update(
        build_pool_creation_update(), provider_name="TEST",
        admission_observer=decisions.append)
    assert admitted_event is not None
    assert admitted_event.base_mint == MINT
    decision = decisions[-1]
    assert decision.admitted
    proof = decision.proof
    assert validate_migration_proof(proof) == (True, None)

    # --- rejected populations never produce a provider event at all ---
    for update in (
        build_pool_creation_update(shape="DIRECT",
                                   quote_deposit_raw=DIRECT_QUOTE_RAW),
        build_pool_creation_update(shape="CPI_NO_PUMPFUN",
                                   quote_deposit_raw=DUST_QUOTE_RAW),
    ):
        assert source_module.decode_create_pool_update(
            update, provider_name="TEST",
            admission_observer=decisions.append) is None
    assert [d.admitted for d in decisions] == [True, False, False]

    # --- proof store (restart-safe) + liquidity index share the SAME proof ---
    store = MigrationProofStore(tmp_path / "migration_proofs.jsonl")
    assert store.seal_and_store(proof)
    liquidity_index = LiquidityIntegrityIndex()
    assert liquidity_index.register_migration_proof(proof)
    restored = MigrationProofStore(tmp_path / "migration_proofs.jsonl").get(MINT)
    assert restored is not None and restored.proof_digest == proof.proof_digest

    # --- provider handoff -> watchlist seed (only the admitted mint) ---
    owner = SingleGrpcPumpSwapDiscovery(
        source_factory=lambda: pytest.fail("no live source in offline tests"),
        dedupe=ProviderCandidateDedupe())
    owner._handle_event(admitted_event)
    drained = owner.drain(max_candidates=4)
    assert [candidate["token_mint"] for candidate in drained] == [MINT]
    watchlist = Watchlist(max_size=4)
    entry = watchlist.seed(drained[0], seeded_at_utc=NOW)
    assert entry is not None and entry.status == WATCH_PENDING_BASELINE
    assert len(watchlist.all_entries()) == 1     # fake + direct never arrived

    # --- decoupled baseline observation on the admitted candidate ---
    observed = producer_session.observe_watchlist_baseline(
        watchlist=watchlist, mint=MINT,
        market={"current_market_cap_usd": "100", "current_price": "0.0001",
                "supply_at_observation": "1000000000",
                "provider_timestamp_utc": NOW, "fetched_at_utc": NOW},
        observation_source="PAID_MARKET_PRIMARY", max_age_seconds=120.0,
        now_iso=NOW)
    assert observed is not None
    assert entry.migration_baseline_status == BASELINE_CAPTURED
    assert entry.status == WATCH_PENDING_1_20X

    # --- the verifier decode of the SAME transaction is canonical, with the
    #     migration authority absent from the header signers ---
    verifier_events = decode_liquidity_update(
        build_pool_creation_update(), observed_at_utc=NOW)
    create_events = [event for event in verifier_events
                     if event.kind == "CREATE_POOL"]
    assert len(create_events) == 1
    create = create_events[0]
    assert INVALID_POOL_AUTHORITY not in create.malformed_reasons
    assert create.canonical_semantics_valid is True
    assert create.signer is None
    for event in verifier_events:
        liquidity_index.record(event)

    # --- LP classification consumes proof + live event coherently ---
    identity = liquidity_index.identity_for(MINT)
    assert identity is not None
    assert identity.pool == proof.pool
    assert identity.migration_signature == proof.migration_signature
    assert create.transaction_signature == proof.migration_signature
    lp_snapshot = liquidity_index.snapshot(identity, now_utc=SOON)
    assert validate_lp_snapshot(lp_snapshot) == (True, None)
    assert lp_snapshot.lp_integrity == LP_INTEGRITY_PASS
    assert lp_snapshot.canonical_pool_proven
    assert lp_snapshot.sealed_migration_proof_digest == proof.proof_digest

    # --- composite policy + the display line every delivery body consumes ---
    # Production default is single-stream: the LP snapshot is not an input,
    # LP reason codes cannot block, and the display shows DISABLED (never a
    # fabricated PASS).  The archived two-stream classification above remains
    # valid offline evidence only.
    from decimal import Decimal
    from PHX2.free_tier_producer.phx1_fee_gate import FeeEvidenceIndex
    from PHX2.free_tier_producer.scam_policy import evaluate_delivery_safety
    fee_snapshot = FeeEvidenceIndex().snapshot(
        MINT, now_epoch=1_800_000_000, max_age_seconds=Decimal(300))
    delivery = evaluate_delivery_safety(fee_snapshot=fee_snapshot)
    assert delivery.lp_snapshot is None
    assert "LP_INTEGRITY_FAIL" not in delivery.final_block_reasons
    assert "LP_INTEGRITY_UNKNOWN" not in delivery.final_block_reasons
    assert "CANONICAL_POOL_PROOF_REQUIRED" not in delivery.final_block_reasons
    assert delivery.discord_transport_allowed is False    # policy invariant
    security_index = SecurityDecisionIndex()
    security_index.bind(delivery)
    line = security_index.line(MINT)
    assert line is not None and "LP Integrity: DISABLED" in line
    assert "LP Integrity: PASS" not in line

    # --- watch-state checkpoint round-trip (paper + dashboard consumption) ---
    checkpoint = tmp_path / "watch_state.jsonl"
    watchlist.persist(checkpoint)
    restored_watchlist = Watchlist.load(checkpoint, max_size=4)
    restored_entry = restored_watchlist.get(MINT)
    assert restored_entry is not None
    assert restored_entry.migration_baseline_status == BASELINE_CAPTURED
    assert restored_entry.migration_market_cap_usd == "100"
    assert (restored_entry.activation_snapshot()["activation_target_market_cap_usd"]
            == entry.activation_snapshot()["activation_target_market_cap_usd"])
    # The engine/composer read the exact same activation snapshot fields.
    assert entry.to_candidate()["activation"]["migration_market_cap_usd"] == "100"


def test_admission_rejections_reach_diagnostics_but_never_the_queue(
        stage28_payload_tail):
    rejections = []
    owner = SingleGrpcPumpSwapDiscovery(
        source_factory=lambda: pytest.fail("no live source in offline tests"),
        dedupe=ProviderCandidateDedupe())

    def observer(decision):
        if not decision.admitted:
            rejections.append(decision.diagnostic_record())

    for update in (
        build_pool_creation_update(shape="DIRECT",
                                   quote_deposit_raw=DIRECT_QUOTE_RAW),
        build_pool_creation_update(shape="CPI_NO_PUMPFUN",
                                   quote_deposit_raw=DUST_QUOTE_RAW),
    ):
        event = source_module.decode_create_pool_update(
            update, provider_name="TEST", admission_observer=observer)
        assert event is None
    assert len(rejections) == 2
    assert {record["classification"] for record in rejections} == {
        "DIRECT", "CPI_UNPROVEN"}
    assert all(record["token_mint"] for record in rejections)
    assert all(record["pool"] for record in rejections)
    assert all(record["deposit_bucket"] != "UNKNOWN" for record in rejections)
    assert owner.snapshot()["queue_depth"] == 0
    assert owner.snapshot()["candidates_accepted"] == 0


def test_event_to_candidate_projection_still_guards_the_base_mint(
        stage28_payload_tail):
    admitted_event = source_module.decode_create_pool_update(
        build_pool_creation_update(), provider_name="TEST")
    candidate = event_to_candidate(admitted_event)
    assert candidate is not None
    assert candidate["token_mint"] == MINT
    assert candidate["discovery_provider"] == "PAID_GRPC_PRIMARY"


# ---------------------------------------------------------------------------
# Real-protobuf end-to-end: admission + Stage 28 payload + verifier decode
# ---------------------------------------------------------------------------


def _build_proto_migration_update():
    """The Population A migration as a REAL geyser SubscribeUpdate, so the
    full unmonkeypatched decode path (admission -> quartet -> Stage 28 payload
    validation -> normalized event) is exercised."""
    import struct
    from PHX2.proto.stage28_11._generated import geyser_pb2
    from PHX2.free_tier_producer.liquidity_integrity import (
        CREATE_POOL_DISCRIMINATOR,
        b58decode,
        derive_associated_token_address,
        derive_pool_address,
    )
    from PHX2.free_tier_producer.migration_admission import (
        PUMPFUN_MIGRATE_INSTRUCTION_DISCRIMINATOR,
        PUMPFUN_PROGRAM_ID,
    )
    from PHX2.stage29.pumpswap_program_constants import PUMPSWAP_PROGRAM_ID
    from PHX2.tests.test_migration_admission import (
        ATA_PROGRAM, CRANKER, CREATOR, OTHER, SYSTEM, TOKEN_2022,
        TOKEN_PROGRAM, WSOL,
    )

    pool = derive_pool_address(
        index=0, creator=CREATOR, base_mint=MINT, quote_mint=WSOL)
    base_vault = derive_associated_token_address(
        owner=pool, token_program=TOKEN_PROGRAM, mint=MINT,
        associated_program=ATA_PROGRAM)
    quote_vault = derive_associated_token_address(
        owner=pool, token_program=TOKEN_PROGRAM, mint=WSOL,
        associated_program=ATA_PROGRAM)
    accounts = [
        pool, CRANKER, CREATOR, MINT, WSOL, OTHER, OTHER, OTHER, OTHER,
        base_vault, quote_vault, SYSTEM, TOKEN_2022, TOKEN_PROGRAM,
        TOKEN_PROGRAM, ATA_PROGRAM, OTHER, PUMPSWAP_PROGRAM_ID,
    ]
    key_texts = [CRANKER]
    for value in [*accounts, PUMPSWAP_PROGRAM_ID, PUMPFUN_PROGRAM_ID]:
        if value not in key_texts:
            key_texts.append(value)
    key_index = {value: position for position, value in enumerate(key_texts)}

    update = geyser_pb2.SubscribeUpdate()
    update.created_at.seconds = 1_784_000_000
    update.transaction.slot = 433450471
    info = update.transaction.transaction
    info.signature = bytes(range(64))
    info.is_vote = False
    info.index = 1
    message = info.transaction.message
    message.header.num_required_signatures = 1
    for value in key_texts:
        message.account_keys.append(b58decode(value))
    migrate = message.instructions.add()
    migrate.program_id_index = key_index[PUMPFUN_PROGRAM_ID]
    migrate.data = bytes(PUMPFUN_MIGRATE_INSTRUCTION_DISCRIMINATOR)
    meta = info.meta
    group = meta.inner_instructions.add()
    group.index = 0
    create = group.instructions.add()
    create.program_id_index = key_index[PUMPSWAP_PROGRAM_ID]
    create.accounts = bytes(key_index[value] for value in accounts)
    create.data = bytes(CREATE_POOL_DISCRIMINATOR) + struct.pack(
        "<HQQ", 0, 206_900_000_000_000, 85_000_000_000)
    create.stack_height = 2
    meta.log_messages.append("Program log: Instruction: CreatePool")
    for address, amount, decimals, mint in (
        (base_vault, 206_900_000_000_000, 6, MINT),
        (quote_vault, 85_000_000_000, 9, WSOL),
    ):
        balance = meta.post_token_balances.add()
        balance.account_index = key_index[address]
        balance.mint = mint
        balance.owner = pool
        balance.ui_token_amount.amount = str(amount)
        balance.ui_token_amount.decimals = decimals
    return update


def test_real_proto_migration_survives_the_full_unmonkeypatched_decode():
    update = _build_proto_migration_update()
    decisions = []
    event = source_module.decode_create_pool_update(
        update, provider_name="TEST_PROVIDER",
        admission_observer=decisions.append)
    assert decisions and decisions[0].admitted
    assert event is not None, "Stage 28 payload validation must accept the event"
    assert event.base_mint == MINT
    verifier_events = decode_liquidity_update(update, observed_at_utc=NOW)
    create_events = [item for item in verifier_events
                     if item.kind == "CREATE_POOL"]
    assert len(create_events) == 1
    assert create_events[0].migration_cpi_proven is True
    assert create_events[0].canonical_semantics_valid is True

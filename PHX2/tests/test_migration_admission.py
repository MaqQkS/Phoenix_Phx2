"""Migration-admission parity fixtures.

Deterministic, synthetic/redacted reconstructions of the three populations the
2026-07-17 discovery-parity investigation ground-truthed from run
phx2_live_20260717T085407Z:

  * Population A — genuine pump.fun migration: create_pool as a CPI inside the
    official pump.fun ``migrate`` frame, canonical pool/vaults, a
    non-header-signer CPI authority, ~85 SOL quote deposit  ->  ADMIT.
  * Population B — fake migration-shaped dust pool: CPI-like create_pool,
    206.9M base tokens, sub-floor quote deposit, no pump.fun ancestry -> REJECT.
  * Population C — direct signer-created pool: top-level create_pool with the
    creator as a transaction signer and a large deposit                -> REJECT.

No secrets: every key below is either a public program id, a public mint, or a
locally derived synthetic key.
"""

import hashlib
import struct
from decimal import Decimal
from types import SimpleNamespace

import pytest

from PHX2.free_tier_producer.liquidity_integrity import (
    CREATE_POOL_DISCRIMINATOR,
    b58encode,
    derive_associated_token_address,
    derive_pool_address,
)
from PHX2.free_tier_producer.migration_admission import (
    CANONICAL_POOL_MISMATCH,
    CREATE_POOL_NOT_IN_MIGRATION_CPI,
    DEFAULT_MIN_QUOTE_DEPOSIT_SOL,
    ENV_MIN_QUOTE_DEPOSIT_SOL,
    MIGRATION_EVENT_MALFORMED,
    MIGRATION_MINT_BINDING_INVALID,
    MIGRATION_PROGRAM_PROOF_MISSING,
    MIGRATION_PROOF_VERSION,
    MIGRATION_QUOTE_DEPOSIT_BELOW_FLOOR,
    MIGRATION_QUOTE_DEPOSIT_MISSING,
    MIGRATION_QUOTE_MINT_UNSUPPORTED,
    MIGRATION_TRANSACTION_FAILED,
    MIGRATION_VAULT_PROOF_INVALID,
    MIGRATION_VERSION_V1,
    MIGRATION_VERSION_V2,
    NOT_PUMPFUN_MIGRATION,
    POOL_CREATION_DIRECT,
    POOL_CREATION_MIGRATION_CPI,
    PUMPFUN_MIGRATE_INSTRUCTION_DISCRIMINATOR,
    PUMPFUN_MIGRATE_V2_INSTRUCTION_DISCRIMINATOR,
    PUMPFUN_MIGRATION_INSTRUCTION_DISCRIMINATORS,
    PUMPFUN_PROGRAM_ID,
    MigrationAdmissionConfig,
    MigrationAdmissionCounters,
    MigrationProofStore,
    build_migration_admission_config,
    evaluate_migration_admission,
    seal_migration_proof,
    validate_migration_proof,
)
from PHX2.free_tier_producer.paid_grpc_source import _base58_decode
from PHX2.stage29.pumpswap_program_constants import PUMPSWAP_PROGRAM_ID


WSOL = "So11111111111111111111111111111111111111112"
USDC = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
MINT = "EkNbQMQYpd4JET5FpZrqbdkYdHXeqocZcBByJpFWpump"
SYSTEM = "11111111111111111111111111111111"
TOKEN_2022 = "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"
TOKEN_PROGRAM = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
ATA_PROGRAM = "ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL"

CRANKER = b58encode(bytes(range(32, 64)))      # fee payer, sole header signer
CREATOR = b58encode(bytes(range(64, 96)))      # migration authority PDA stand-in
ROUTER = b58encode(bytes(range(96, 128)))      # arbitrary wrapper program
OTHER = b58encode(bytes(range(1, 33)))
UNKNOWN_QUOTE = b58encode(bytes(range(128, 160)))

SLOT = 433450471
SIGNATURE_BYTES = bytes(range(64))
POOL_INDEX = 0

MIGRATION_BASE_RAW = 206_900_000_000_000       # 206.9M tokens at 6 decimals
MIGRATION_QUOTE_RAW = 85_000_000_000           # 85 SOL at 9 decimals
DUST_QUOTE_RAW = 1_722_766_462                 # 1.72 SOL (observed fake pool)
DIRECT_QUOTE_RAW = 300_000_000_000             # 300 SOL direct pool


def _pool_for(base_mint=MINT, quote_mint=WSOL, creator=CREATOR):
    return derive_pool_address(
        index=POOL_INDEX, creator=creator, base_mint=base_mint, quote_mint=quote_mint)


def _vaults_for(pool, base_mint=MINT, quote_mint=WSOL):
    return (
        derive_associated_token_address(
            owner=pool, token_program=TOKEN_PROGRAM, mint=base_mint,
            associated_program=ATA_PROGRAM),
        derive_associated_token_address(
            owner=pool, token_program=TOKEN_PROGRAM, mint=quote_mint,
            associated_program=ATA_PROGRAM),
    )


def build_pool_creation_update(
    *,
    shape="MIGRATION",                    # MIGRATION | DIRECT | CPI_NO_PUMPFUN | WRAPPED
    base_mint=MINT,
    quote_mint=WSOL,
    quote_deposit_raw=MIGRATION_QUOTE_RAW,
    quote_decimals=9,
    creator=CREATOR,
    corrupt_pool=False,
    corrupt_vault=False,
    omit_quote_balance=False,
    failed=False,
    short_accounts=False,
    stack_heights=True,
    inner_filler=False,
    use_loaded_addresses=False,
    duplicate_create_pool=False,
    balance_mint_override=None,
    malformed_quote_amount=False,
    migrate_discriminator=PUMPFUN_MIGRATE_INSTRUCTION_DISCRIMINATOR,
):
    """One synthetic Yellowstone SubscribeUpdate holding one pool creation."""

    pool = _pool_for(base_mint=base_mint, quote_mint=quote_mint, creator=creator)
    if corrupt_pool:
        pool = OTHER
    base_vault, quote_vault = _vaults_for(pool, base_mint=base_mint, quote_mint=quote_mint)
    if corrupt_vault:
        base_vault = OTHER
    accounts = [
        pool, CRANKER, creator, base_mint, quote_mint, OTHER, OTHER, OTHER, OTHER,
        base_vault, quote_vault, SYSTEM, TOKEN_2022, TOKEN_PROGRAM, TOKEN_PROGRAM,
        ATA_PROGRAM, OTHER, PUMPSWAP_PROGRAM_ID,
    ]
    if short_accounts:
        accounts = accounts[:5]

    key_texts = [CRANKER]
    loaded_texts = []
    for value in [*accounts, base_vault, quote_vault,
                  PUMPSWAP_PROGRAM_ID, PUMPFUN_PROGRAM_ID, ROUTER]:
        if value in key_texts or value in loaded_texts:
            continue
        if use_loaded_addresses and value in (base_vault, quote_vault):
            loaded_texts.append(value)
        else:
            key_texts.append(value)
    all_texts = key_texts + loaded_texts
    key_index = {value: position for position, value in enumerate(all_texts)}

    create_pool_data = bytes(CREATE_POOL_DISCRIMINATOR) + struct.pack(
        "<HQQ", POOL_INDEX, MIGRATION_BASE_RAW, quote_deposit_raw)
    create_pool_accounts = bytes(key_index[value] for value in accounts)

    def _instruction(program, data, accounts_bytes=b"", stack_height=None):
        namespace = SimpleNamespace(
            program_id_index=key_index[program], accounts=accounts_bytes, data=data)
        if stack_height is not None:
            namespace.stack_height = stack_height
        return namespace

    migrate_data = bytes(migrate_discriminator) + b"\x00"
    inner = []
    if shape == "MIGRATION":
        top_level = [_instruction(PUMPFUN_PROGRAM_ID, migrate_data)]
        if inner_filler:
            inner.append(_instruction(
                TOKEN_PROGRAM, b"\x03filler", stack_height=2 if stack_heights else None))
        inner.append(_instruction(
            PUMPSWAP_PROGRAM_ID, create_pool_data, create_pool_accounts,
            stack_height=2 if stack_heights else None))
    elif shape == "WRAPPED":
        top_level = [_instruction(ROUTER, b"\x01router")]
        inner.append(_instruction(
            PUMPFUN_PROGRAM_ID, migrate_data,
            stack_height=2 if stack_heights else None))
        inner.append(_instruction(
            PUMPSWAP_PROGRAM_ID, create_pool_data, create_pool_accounts,
            stack_height=3 if stack_heights else None))
    elif shape == "CPI_NO_PUMPFUN":
        top_level = [_instruction(ROUTER, b"\x01router")]
        inner.append(_instruction(
            PUMPSWAP_PROGRAM_ID, create_pool_data, create_pool_accounts,
            stack_height=2 if stack_heights else None))
    elif shape == "DIRECT":
        top_level = [_instruction(PUMPSWAP_PROGRAM_ID, create_pool_data,
                                  create_pool_accounts)]
    else:
        raise AssertionError(f"unknown fixture shape {shape!r}")
    if duplicate_create_pool:
        inner.append(_instruction(
            PUMPSWAP_PROGRAM_ID, create_pool_data, create_pool_accounts,
            stack_height=2 if stack_heights else None))

    message = SimpleNamespace(
        account_keys=[_base58_decode(value) for value in key_texts],
        instructions=top_level,
        header=SimpleNamespace(num_required_signatures=1),
    )

    def _balance(address, amount, decimals, mint):
        return SimpleNamespace(
            account_index=key_index[address],
            owner=pool,
            mint=(balance_mint_override or mint),
            ui_token_amount=SimpleNamespace(amount=str(amount), decimals=decimals))

    post_balances = [_balance(base_vault, MIGRATION_BASE_RAW, 6, base_mint)]
    if not omit_quote_balance:
        quote_balance = _balance(
            quote_vault, quote_deposit_raw, quote_decimals, quote_mint)
        if malformed_quote_amount:
            quote_balance.ui_token_amount.amount = "not-a-number"
        post_balances.append(quote_balance)
    meta = SimpleNamespace(
        log_messages=["Program log: Instruction: CreatePool"],
        loaded_writable_addresses=[_base58_decode(value) for value in loaded_texts],
        loaded_readonly_addresses=[],
        inner_instructions=([SimpleNamespace(index=0, instructions=inner)]
                            if inner else []),
        pre_token_balances=[],
        post_token_balances=post_balances,
    )
    if failed:
        meta.err = SimpleNamespace(err=b"\x01")
    tx_info = SimpleNamespace(
        signature=SIGNATURE_BYTES,
        transaction=SimpleNamespace(message=message),
        meta=meta,
    )
    update = SimpleNamespace(
        transaction=SimpleNamespace(slot=SLOT, transaction=tx_info))
    update.HasField = lambda name: name == "transaction"
    return update


# ---------------------------------------------------------------------------
# Pinned constants
# ---------------------------------------------------------------------------


def test_pumpfun_program_and_migrate_discriminator_are_pinned():
    assert PUMPFUN_PROGRAM_ID == "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
    assert (PUMPFUN_MIGRATE_INSTRUCTION_DISCRIMINATOR
            == hashlib.sha256(b"global:migrate").digest()[:8])
    assert DEFAULT_MIN_QUOTE_DEPOSIT_SOL == Decimal("50")


def test_migrate_v2_discriminator_is_pinned_and_the_allowed_set_is_closed():
    assert (PUMPFUN_MIGRATE_V2_INSTRUCTION_DISCRIMINATOR
            == hashlib.sha256(b"global:migrate_v2").digest()[:8])
    assert PUMPFUN_MIGRATE_V2_INSTRUCTION_DISCRIMINATOR.hex() == "bbcb121fceedfe29"
    assert PUMPFUN_MIGRATE_INSTRUCTION_DISCRIMINATOR.hex() == "9beae792ec9ea21e"
    assert PUMPFUN_MIGRATION_INSTRUCTION_DISCRIMINATORS == {
        bytes(PUMPFUN_MIGRATE_INSTRUCTION_DISCRIMINATOR): MIGRATION_VERSION_V1,
        bytes(PUMPFUN_MIGRATE_V2_INSTRUCTION_DISCRIMINATOR): MIGRATION_VERSION_V2,
    }


# ---------------------------------------------------------------------------
# Population A — genuine migration
# ---------------------------------------------------------------------------


def test_population_a_genuine_migration_is_admitted():
    decision = evaluate_migration_admission(build_pool_creation_update())
    assert decision is not None and decision.admitted
    assert decision.classification == POOL_CREATION_MIGRATION_CPI
    assert decision.reason_codes == ()
    assert decision.candidate_mint == MINT
    assert decision.quote_deposit_sol == "85"
    assert decision.migration_version == MIGRATION_VERSION_V1
    proof = decision.proof
    valid, reason = validate_migration_proof(proof)
    assert valid, reason
    assert proof.proof_version == MIGRATION_PROOF_VERSION
    assert proof.migration_authority == CREATOR
    assert proof.migration_slot == SLOT
    assert proof.quote_deposit_raw == MIGRATION_QUOTE_RAW
    assert proof.mint_suffix_consistent is True
    assert proof.migration_instruction_version == MIGRATION_VERSION_V1


def test_genuine_migrate_v2_migration_is_admitted_with_version_exposed():
    decision = evaluate_migration_admission(build_pool_creation_update(
        migrate_discriminator=PUMPFUN_MIGRATE_V2_INSTRUCTION_DISCRIMINATOR))
    assert decision is not None and decision.admitted
    assert decision.classification == POOL_CREATION_MIGRATION_CPI
    assert decision.migration_version == MIGRATION_VERSION_V2
    proof = decision.proof
    valid, reason = validate_migration_proof(proof)
    assert valid, reason
    assert proof.migration_instruction_version == MIGRATION_VERSION_V2
    assert decision.diagnostic_record()["migration_version"] == MIGRATION_VERSION_V2


def test_wrapped_migrate_v2_cpi_with_stack_heights_is_admitted():
    decision = evaluate_migration_admission(build_pool_creation_update(
        shape="WRAPPED",
        migrate_discriminator=PUMPFUN_MIGRATE_V2_INSTRUCTION_DISCRIMINATOR))
    assert decision is not None and decision.admitted
    assert decision.migration_version == MIGRATION_VERSION_V2


def test_unknown_pumpfun_migration_discriminator_fails_closed():
    unknown = hashlib.sha256(b"global:migrate_v3").digest()[:8]
    for shape in ("MIGRATION", "WRAPPED"):
        decision = evaluate_migration_admission(build_pool_creation_update(
            shape=shape, migrate_discriminator=unknown))
        assert decision is not None and not decision.admitted
        assert MIGRATION_PROGRAM_PROOF_MISSING in decision.reason_codes
        assert NOT_PUMPFUN_MIGRATION in decision.reason_codes
        assert decision.migration_version is None
        assert decision.proof is None


def test_migration_authority_is_not_a_header_signer_yet_admits():
    update = build_pool_creation_update()
    message = update.transaction.transaction.transaction.message
    header_signers = message.account_keys[:message.header.num_required_signatures]
    assert _base58_decode(CREATOR) not in header_signers
    decision = evaluate_migration_admission(update)
    assert decision is not None and decision.admitted


def test_wrapped_migration_cpi_with_stack_heights_is_admitted():
    decision = evaluate_migration_admission(
        build_pool_creation_update(shape="WRAPPED"))
    assert decision is not None and decision.admitted


def test_wrapped_migration_without_stack_heights_fails_closed():
    decision = evaluate_migration_admission(
        build_pool_creation_update(shape="WRAPPED", stack_heights=False))
    assert decision is not None and not decision.admitted
    assert MIGRATION_PROGRAM_PROOF_MISSING in decision.reason_codes


def test_inner_instruction_indexing_is_bound_into_the_proof():
    decision = evaluate_migration_admission(
        build_pool_creation_update(inner_filler=True))
    assert decision is not None and decision.admitted
    proof = decision.proof
    assert proof.outer_instruction_index == 0
    assert proof.inner_instruction_index == 1
    assert proof.flattened_instruction_index == 2


def test_versioned_transaction_loaded_addresses_resolve():
    decision = evaluate_migration_admission(
        build_pool_creation_update(use_loaded_addresses=True))
    assert decision is not None and decision.admitted


def test_deposit_floor_boundary_admits_exactly_50_sol():
    at_floor = evaluate_migration_admission(
        build_pool_creation_update(quote_deposit_raw=50_000_000_000))
    below = evaluate_migration_admission(
        build_pool_creation_update(quote_deposit_raw=49_999_999_999))
    assert at_floor is not None and at_floor.admitted
    assert below is not None and not below.admitted
    assert MIGRATION_QUOTE_DEPOSIT_BELOW_FLOOR in below.reason_codes


# ---------------------------------------------------------------------------
# Population B — fake migration-shaped dust pool
# ---------------------------------------------------------------------------


def test_population_b_dust_pool_without_pumpfun_ancestry_is_rejected():
    decision = evaluate_migration_admission(build_pool_creation_update(
        shape="CPI_NO_PUMPFUN", quote_deposit_raw=DUST_QUOTE_RAW))
    assert decision is not None and not decision.admitted
    assert MIGRATION_PROGRAM_PROOF_MISSING in decision.reason_codes
    assert NOT_PUMPFUN_MIGRATION in decision.reason_codes
    assert decision.proof is None


def test_population_b_dust_deposit_is_rejected_even_with_forged_ancestry():
    # Defense in depth: even a hypothetical pump.fun-wrapped dust deposit
    # fails the floor.
    decision = evaluate_migration_admission(build_pool_creation_update(
        quote_deposit_raw=DUST_QUOTE_RAW))
    assert decision is not None and not decision.admitted
    assert decision.reason_codes == (MIGRATION_QUOTE_DEPOSIT_BELOW_FLOOR,)
    assert decision.deposit_bucket == "SOL_1_TO_10"


# ---------------------------------------------------------------------------
# Population C — direct signer-created pool
# ---------------------------------------------------------------------------


def test_population_c_direct_pool_is_rejected_despite_large_deposit():
    decision = evaluate_migration_admission(build_pool_creation_update(
        shape="DIRECT", quote_deposit_raw=DIRECT_QUOTE_RAW))
    assert decision is not None and not decision.admitted
    assert decision.classification == POOL_CREATION_DIRECT
    assert CREATE_POOL_NOT_IN_MIGRATION_CPI in decision.reason_codes
    assert NOT_PUMPFUN_MIGRATION in decision.reason_codes


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_failed_transaction_is_rejected():
    decision = evaluate_migration_admission(
        build_pool_creation_update(failed=True))
    assert decision is not None and not decision.admitted
    assert MIGRATION_TRANSACTION_FAILED in decision.reason_codes


def test_wrong_quote_mint_is_rejected():
    decision = evaluate_migration_admission(build_pool_creation_update(
        quote_mint=UNKNOWN_QUOTE))
    assert decision is not None and not decision.admitted
    assert MIGRATION_QUOTE_MINT_UNSUPPORTED in decision.reason_codes


def test_usdc_quote_cannot_prove_a_sol_denominated_floor():
    decision = evaluate_migration_admission(build_pool_creation_update(
        quote_mint=USDC, quote_decimals=6))
    assert decision is not None and not decision.admitted
    assert MIGRATION_QUOTE_DEPOSIT_MISSING in decision.reason_codes


def test_pool_pda_mismatch_is_rejected():
    decision = evaluate_migration_admission(
        build_pool_creation_update(corrupt_pool=True))
    assert decision is not None and not decision.admitted
    assert CANONICAL_POOL_MISMATCH in decision.reason_codes


def test_vault_mismatch_is_rejected():
    decision = evaluate_migration_admission(
        build_pool_creation_update(corrupt_vault=True))
    assert decision is not None and not decision.admitted
    assert MIGRATION_VAULT_PROOF_INVALID in decision.reason_codes


def test_missing_or_malformed_quote_delta_fails_closed():
    malformed = evaluate_migration_admission(
        build_pool_creation_update(malformed_quote_amount=True))
    assert malformed is not None and not malformed.admitted
    assert MIGRATION_QUOTE_DEPOSIT_MISSING in malformed.reason_codes
    # A wholly absent quote-vault balance also removes the vault ownership
    # evidence, so it fails closed one gate earlier.
    absent = evaluate_migration_admission(
        build_pool_creation_update(omit_quote_balance=True))
    assert absent is not None and not absent.admitted
    assert MIGRATION_VAULT_PROOF_INVALID in absent.reason_codes


def test_wrong_quote_decimals_fail_closed():
    decision = evaluate_migration_admission(
        build_pool_creation_update(quote_decimals=6))
    assert decision is not None and not decision.admitted
    assert MIGRATION_QUOTE_DEPOSIT_MISSING in decision.reason_codes


def test_balance_mint_incoherence_is_rejected():
    decision = evaluate_migration_admission(
        build_pool_creation_update(balance_mint_override=OTHER))
    assert decision is not None and not decision.admitted
    assert MIGRATION_MINT_BINDING_INVALID in decision.reason_codes


def test_duplicate_create_pool_sites_in_one_signature_are_rejected():
    decision = evaluate_migration_admission(
        build_pool_creation_update(duplicate_create_pool=True))
    assert decision is not None and not decision.admitted
    assert MIGRATION_EVENT_MALFORMED in decision.reason_codes


def test_program_layout_drift_fails_closed():
    decision = evaluate_migration_admission(
        build_pool_creation_update(short_accounts=True))
    assert decision is not None and not decision.admitted
    assert MIGRATION_EVENT_MALFORMED in decision.reason_codes


def test_non_pool_creation_transaction_is_not_a_decision():
    update = build_pool_creation_update()
    message = update.transaction.transaction.transaction.message
    meta = update.transaction.transaction.meta
    message.instructions = [SimpleNamespace(
        program_id_index=0, accounts=b"", data=b"ordinary")]
    meta.inner_instructions = []
    assert evaluate_migration_admission(update) is None


def test_mint_suffix_is_recorded_as_consistency_not_proof():
    non_pump_base = b58encode(bytes(range(160, 192)))
    decision = evaluate_migration_admission(
        build_pool_creation_update(base_mint=non_pump_base))
    assert decision is not None and decision.admitted
    assert decision.proof.mint_suffix_consistent is False


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


def test_deposit_floor_is_configurable_and_decimal_only():
    assert build_migration_admission_config(
        {}).min_quote_deposit_sol == Decimal("50")
    assert build_migration_admission_config(
        {ENV_MIN_QUOTE_DEPOSIT_SOL: "75"}).min_quote_deposit_sol == Decimal("75")
    raised = evaluate_migration_admission(
        build_pool_creation_update(),
        config=MigrationAdmissionConfig(min_quote_deposit_sol=Decimal("100")))
    assert raised is not None and not raised.admitted
    assert MIGRATION_QUOTE_DEPOSIT_BELOW_FLOOR in raised.reason_codes
    with pytest.raises(ValueError):
        build_migration_admission_config({ENV_MIN_QUOTE_DEPOSIT_SOL: "not-a-number"})
    with pytest.raises(ValueError):
        build_migration_admission_config({ENV_MIN_QUOTE_DEPOSIT_SOL: "5e1"})
    with pytest.raises(ValueError):
        MigrationAdmissionConfig(min_quote_deposit_sol=50.0)


# ---------------------------------------------------------------------------
# Proof sealing, tamper detection, and restart persistence
# ---------------------------------------------------------------------------


def test_proof_digest_detects_tampering():
    proof = evaluate_migration_admission(build_pool_creation_update()).proof
    from dataclasses import replace
    forged = replace(proof, quote_deposit_raw=proof.quote_deposit_raw + 1)
    valid, reason = validate_migration_proof(forged)
    assert not valid and reason == "MIGRATION_PROOF_DIGEST_MISMATCH"
    resealed = seal_migration_proof(forged)
    assert resealed.proof_digest != proof.proof_digest


def test_proof_store_persists_and_survives_restart(tmp_path):
    path = tmp_path / "migration_proofs.jsonl"
    proof = evaluate_migration_admission(build_pool_creation_update()).proof
    store = MigrationProofStore(path)
    assert store.seal_and_store(proof)
    assert not store.seal_and_store(proof)          # first per mint wins
    reloaded = MigrationProofStore(path)            # simulated restart
    restored = reloaded.get(MINT)
    assert restored is not None
    assert restored.proof_digest == proof.proof_digest
    assert reloaded.stats()["immutable_migration_proofs"] == 1


def test_proof_store_drops_tampered_lines_on_load(tmp_path):
    path = tmp_path / "migration_proofs.jsonl"
    proof = evaluate_migration_admission(build_pool_creation_update()).proof
    MigrationProofStore(path).seal_and_store(proof)
    text = path.read_text(encoding="utf-8")
    assert '"quote_deposit_raw":85000000000' in text
    path.write_text(text.replace('"quote_deposit_raw":85000000000',
                                 '"quote_deposit_raw":1'), encoding="utf-8")
    reloaded = MigrationProofStore(path)
    assert reloaded.get(MINT) is None
    assert reloaded.stats()["proof_load_dropped"] == 1


# ---------------------------------------------------------------------------
# Counters
# ---------------------------------------------------------------------------


def test_admission_counters_classify_all_three_populations():
    counters = MigrationAdmissionCounters()
    counters.record(evaluate_migration_admission(build_pool_creation_update()))
    counters.record(evaluate_migration_admission(build_pool_creation_update(
        shape="CPI_NO_PUMPFUN", quote_deposit_raw=DUST_QUOTE_RAW)))
    counters.record(evaluate_migration_admission(build_pool_creation_update(
        quote_deposit_raw=DUST_QUOTE_RAW)))
    counters.record(evaluate_migration_admission(build_pool_creation_update(
        shape="DIRECT", quote_deposit_raw=DIRECT_QUOTE_RAW)))
    counters.record(evaluate_migration_admission(build_pool_creation_update(
        corrupt_pool=True)))
    snap = counters.snapshot()
    assert snap["pool_creations_seen"] == 5
    assert snap["migration_proof_pass"] == 1
    assert snap["admitted_true_migrations"] == 1
    assert snap["rejected_not_migration"] == 1
    assert snap["rejected_dust_deposit"] == 1
    assert snap["rejected_direct_pool"] == 1
    assert snap["rejected_canonical_mismatch"] == 1
    assert snap["migration_v1_admitted"] == 1
    assert snap["migration_v2_admitted"] == 0
    assert snap["migration_rejected_below_deposit_floor"] == 1
    # not-proven aggregates the CPI_NO_PUMPFUN reject and the direct pool.
    assert snap["migration_rejected_not_proven"] == 2


def test_admission_counters_split_migrate_versions():
    counters = MigrationAdmissionCounters()
    counters.record(evaluate_migration_admission(build_pool_creation_update()))
    counters.record(evaluate_migration_admission(build_pool_creation_update(
        base_mint=b58encode(bytes(range(2, 34))),
        migrate_discriminator=PUMPFUN_MIGRATE_V2_INSTRUCTION_DISCRIMINATOR)))
    snap = counters.snapshot()
    assert snap["migration_v1_admitted"] == 1
    assert snap["migration_v2_admitted"] == 1
    assert snap["admitted_true_migrations"] == 2


def test_rejection_diagnostic_record_is_closed_set():
    decision = evaluate_migration_admission(build_pool_creation_update(
        shape="DIRECT", quote_deposit_raw=DIRECT_QUOTE_RAW))
    record = decision.diagnostic_record()
    assert record["kind"] == "PHX2_MIGRATION_ADMISSION"
    assert record["admitted"] is False
    assert record["classification"] == POOL_CREATION_DIRECT
    assert record["deposit_bucket"] == "GE_50_SOL"
    assert set(record) == {
        "kind", "admitted", "classification", "reason_codes", "token_mint",
        "pool", "quote_mint", "transaction_signature", "slot",
        "deposit_bucket", "quote_deposit_sol", "migration_version",
    }
    assert record["migration_version"] is None

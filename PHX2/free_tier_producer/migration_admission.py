"""Deterministic pump.fun migration admission proof for PumpSwap create_pool.

This module is the centralized production home of the pump.fun bonding-curve
program id and of the migration-proof model.  A candidate is admitted into
PHX2 discovery only when one successful non-vote transaction proves, from the
same Yellowstone ``SubscribeUpdate``:

  * the official PumpSwap program executed the exact IDL-pinned ``create_pool``
    instruction as an INNER instruction (CPI),
  * the CPI ancestry of that inner instruction is the official pump.fun
    bonding-curve program executing one of its pinned migration instructions
    (``migrate`` or ``migrate_v2``; unknown discriminators fail closed),
  * the pool equals the derived canonical PumpSwap pool PDA and both vaults
    match their associated-token derivations and are owned by the pool,
  * the base mint is coherent across the instruction accounts and the token
    balance evidence, and the quote mint is an approved quote mint,
  * the observed quote-vault delta clears a configurable Decimal deposit floor
    (defense in depth; the CPI/program relationship remains the primary proof),
  * the evidence is bound to the exact transaction signature and instruction
    index.

Mint-suffix checks are retained elsewhere only as a consistency signal; they
are never the migration proof.  Rejections carry closed-set reason codes and
stay out of the watchlist and every delivery pipeline.

The sealed :class:`MigrationProofSnapshot` is the immutable, restart-safe
historical record consumed by the watchlist and every downstream display.  It
records which pinned migration instruction version admitted the candidate.
Single-stream production performs no separate liquidity verification; the
sealed proof is the complete admission record.

No network, transport, or environment access happens at import time.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
from decimal import Decimal, InvalidOperation
from enum import Enum
import hashlib
import json
import os
import re
import struct
import threading
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from PHX2.free_tier_producer.liquidity_integrity import (
    ASSOCIATED_TOKEN_PROGRAM_ID,
    SYSTEM_PROGRAM_ID,
    TOKEN_2022_PROGRAM_ID,
    TOKEN_PROGRAM_IDS,
    WSOL_MINT,
    b58decode,
    derive_associated_token_address,
    derive_pool_address,
)
from PHX2.stage29.pumpswap_program_constants import (
    KNOWN_QUOTE_MINT_TO_PROVIDER_PAIR_TYPE_HINT,
    PUMPSWAP_PROGRAM_ID,
)
from PHX2.stage29.stage29_5_7_helius_raw_migration_models import (
    PUMPSWAP_CREATE_POOL_INSTRUCTION_DISCRIMINATOR,
)


# ---------------------------------------------------------------------------
# Centralized pump.fun bonding-curve program constants
# ---------------------------------------------------------------------------

# Official pump.fun bonding-curve program (pre-migration side).  This is the
# ONE production definition; other modules must import it from here instead of
# repeating the literal.  (The Stage 29.1 constants module deliberately
# excluded it pending an explicitly-authorized substage; this module is that
# authorized production home.)
PUMPFUN_PROGRAM_ID = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"

# Anchor instruction discriminator for the pump.fun ``migrate`` instruction:
# sha256("global:migrate")[:8].  Pinned as a literal; the fixture test derives
# it independently and asserts byte equality.
PUMPFUN_MIGRATE_INSTRUCTION_DISCRIMINATOR = bytes(
    (155, 234, 231, 146, 236, 158, 162, 30))

# Anchor instruction discriminator for the pump.fun ``migrate_v2`` instruction:
# sha256("global:migrate_v2")[:8].  The 2026-07-18 acceptance run proved live
# pump.fun migrations now execute this variant; the fixture test derives the
# bytes independently and asserts equality.
PUMPFUN_MIGRATE_V2_INSTRUCTION_DISCRIMINATOR = bytes(
    (187, 203, 18, 31, 206, 237, 254, 41))

# Raw 32-byte program ids for the hot per-instruction path.  Comparing an
# account key against these bytes is exactly equivalent to base58-encoding the
# key and comparing the text against the program-id string (base58 is a
# bijection), but avoids the O(n^2) base58 encode on every scanned instruction.
PUMPSWAP_PROGRAM_ID_BYTES = b58decode(PUMPSWAP_PROGRAM_ID)
PUMPFUN_PROGRAM_ID_BYTES = b58decode(PUMPFUN_PROGRAM_ID)


def _program_key_matches(keys: Sequence[bytes], index: object, target: bytes) -> bool:
    """True iff the account key at ``index`` equals ``target`` program-id bytes.

    Raw-byte equivalent of ``_resolve_key_text(keys, index) == <base58(target)>``.
    Out-of-range / non-int / bool indices and length-mismatched keys never
    match, matching the ``None``/non-equal outcomes of the base58 path.
    """
    if isinstance(index, bool) or not isinstance(index, int):
        return False
    if not (0 <= index < len(keys)):
        return False
    return keys[index] == target


# Closed-set migration instruction versions.
MIGRATION_VERSION_V1 = "migrate"
MIGRATION_VERSION_V2 = "migrate_v2"
MIGRATION_VERSIONS = (MIGRATION_VERSION_V1, MIGRATION_VERSION_V2)

# The ONE centralized allowed set of pump.fun migration instruction
# discriminators.  Admission proves CPI ancestry against exactly these bytes;
# any other pump.fun instruction (including unknown future migration
# variants) fails closed as unproven.
PUMPFUN_MIGRATION_INSTRUCTION_DISCRIMINATORS: Dict[bytes, str] = {
    bytes(PUMPFUN_MIGRATE_INSTRUCTION_DISCRIMINATOR): MIGRATION_VERSION_V1,
    bytes(PUMPFUN_MIGRATE_V2_INSTRUCTION_DISCRIMINATOR): MIGRATION_VERSION_V2,
}

MIGRATION_PROOF_VERSION = "PHX2_MIGRATION_PROOF_V2"
MIGRATION_PROOF_SOURCE = "PAID_GRPC_PRIMARY_SUBSCRIBE_UPDATE"

# Exact create_pool account layout (the vendored Pump AMM Anchor IDL order).
CREATE_POOL_IDX_POOL = 0
CREATE_POOL_IDX_CREATOR = 2
CREATE_POOL_IDX_BASE_MINT = 3
CREATE_POOL_IDX_QUOTE_MINT = 4
CREATE_POOL_IDX_BASE_VAULT = 9
CREATE_POOL_IDX_QUOTE_VAULT = 10
CREATE_POOL_ACCOUNT_COUNT = 18
CREATE_POOL_DATA_MIN_LEN = 26          # 8 discriminator + u16 index + 2 * u64

# Pool-creation classification (diagnostics vocabulary).
POOL_CREATION_MIGRATION_CPI = "MIGRATION_CPI"
POOL_CREATION_DIRECT = "DIRECT"
POOL_CREATION_CPI_UNPROVEN = "CPI_UNPROVEN"

# Closed-set rejection reason codes.
NOT_PUMPFUN_MIGRATION = "NOT_PUMPFUN_MIGRATION"
CREATE_POOL_NOT_IN_MIGRATION_CPI = "CREATE_POOL_NOT_IN_MIGRATION_CPI"
MIGRATION_PROGRAM_PROOF_MISSING = "MIGRATION_PROGRAM_PROOF_MISSING"
MIGRATION_QUOTE_DEPOSIT_MISSING = "MIGRATION_QUOTE_DEPOSIT_MISSING"
MIGRATION_QUOTE_DEPOSIT_BELOW_FLOOR = "MIGRATION_QUOTE_DEPOSIT_BELOW_FLOOR"
CANONICAL_POOL_MISMATCH = "CANONICAL_POOL_MISMATCH"
MIGRATION_VAULT_PROOF_INVALID = "MIGRATION_VAULT_PROOF_INVALID"
MIGRATION_MINT_BINDING_INVALID = "MIGRATION_MINT_BINDING_INVALID"
MIGRATION_TRANSACTION_FAILED = "MIGRATION_TRANSACTION_FAILED"
MIGRATION_EVENT_MALFORMED = "MIGRATION_EVENT_MALFORMED"
MIGRATION_QUOTE_MINT_UNSUPPORTED = "MIGRATION_QUOTE_MINT_UNSUPPORTED"

# Fail-closed transaction-execution reasons (PHX2-E2E-007).  A create_pool whose
# transaction outcome cannot be proven canonically successful is rejected before
# any migration proof is authorized.  ``MIGRATION_TRANSACTION_FAILED`` remains
# the reason for a recognized on-chain failure; the codes below distinguish an
# indeterminate error representation (a malformed container, an unsupported
# encoding, a failed field access, or presence that contradicts populated
# failure evidence) so a schema-drift/malformed shape can never masquerade as a
# successful transaction.
TRANSACTION_ERROR_MALFORMED_FAIL_CLOSED = "TRANSACTION_ERROR_MALFORMED_FAIL_CLOSED"
TRANSACTION_ERROR_UNSUPPORTED_ENCODING = "TRANSACTION_ERROR_UNSUPPORTED_ENCODING"
TRANSACTION_ERROR_ACCESS_FAILED = "TRANSACTION_ERROR_ACCESS_FAILED"
TRANSACTION_ERROR_PRESENCE_CONFLICT = "TRANSACTION_ERROR_PRESENCE_CONFLICT"

# The indeterminate (non on-chain-failure) fail-closed transaction reasons.
TRANSACTION_STATUS_FAIL_CLOSED_REASONS = frozenset({
    TRANSACTION_ERROR_MALFORMED_FAIL_CLOSED,
    TRANSACTION_ERROR_UNSUPPORTED_ENCODING,
    TRANSACTION_ERROR_ACCESS_FAILED,
    TRANSACTION_ERROR_PRESENCE_CONFLICT,
})

MIGRATION_REJECTION_REASONS = frozenset({
    NOT_PUMPFUN_MIGRATION,
    CREATE_POOL_NOT_IN_MIGRATION_CPI,
    MIGRATION_PROGRAM_PROOF_MISSING,
    MIGRATION_QUOTE_DEPOSIT_MISSING,
    MIGRATION_QUOTE_DEPOSIT_BELOW_FLOOR,
    CANONICAL_POOL_MISMATCH,
    MIGRATION_VAULT_PROOF_INVALID,
    MIGRATION_MINT_BINDING_INVALID,
    MIGRATION_TRANSACTION_FAILED,
    MIGRATION_EVENT_MALFORMED,
    MIGRATION_QUOTE_MINT_UNSUPPORTED,
    TRANSACTION_ERROR_MALFORMED_FAIL_CLOSED,
    TRANSACTION_ERROR_UNSUPPORTED_ENCODING,
    TRANSACTION_ERROR_ACCESS_FAILED,
    TRANSACTION_ERROR_PRESENCE_CONFLICT,
})

# Deposit buckets for redaction-safe rejection diagnostics.
DEPOSIT_BUCKET_UNKNOWN = "UNKNOWN"
DEPOSIT_BUCKET_LT_1 = "LT_1_SOL"
DEPOSIT_BUCKET_1_10 = "SOL_1_TO_10"
DEPOSIT_BUCKET_10_50 = "SOL_10_TO_50"
DEPOSIT_BUCKET_GE_50 = "GE_50_SOL"

ENV_MIN_QUOTE_DEPOSIT_SOL = "PHX2_MIGRATION_MIN_QUOTE_DEPOSIT_SOL"
DEFAULT_MIN_QUOTE_DEPOSIT_SOL = Decimal("50")

_STRICT_DECIMAL_RE = re.compile(r"\A[0-9]+(?:\.[0-9]+)?\Z")
_BASE58_ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def _b58encode_any(raw: object) -> Optional[str]:
    if not isinstance(raw, (bytes, bytearray)) or not raw:
        return None
    data = bytes(raw)
    zeros = 0
    for value in data:
        if value != 0:
            break
        zeros += 1
    number = int.from_bytes(data, "big")
    chars: List[str] = []
    while number:
        number, rem = divmod(number, 58)
        chars.append(_BASE58_ALPHABET[rem])
    return "1" * zeros + "".join(reversed(chars))


@dataclass(frozen=True)
class MigrationAdmissionConfig:
    """Decimal-only deposit floor configuration for migration admission."""

    min_quote_deposit_sol: Decimal = DEFAULT_MIN_QUOTE_DEPOSIT_SOL

    def __post_init__(self) -> None:
        value = self.min_quote_deposit_sol
        if isinstance(value, float) or not isinstance(value, Decimal):
            raise ValueError("min_quote_deposit_sol_must_be_decimal")
        if not value.is_finite() or value < 0:
            raise ValueError("min_quote_deposit_sol_invalid")


def build_migration_admission_config(
    env: Optional[Mapping[str, str]] = None,
) -> MigrationAdmissionConfig:
    """Resolve the deposit floor from ``env`` (strict decimal text, no floats).

    A malformed value raises rather than silently weakening the floor.
    """
    raw = (env or {}).get(ENV_MIN_QUOTE_DEPOSIT_SOL)
    if raw is None or not str(raw).strip():
        return MigrationAdmissionConfig()
    text = str(raw).strip()
    if not _STRICT_DECIMAL_RE.fullmatch(text):
        raise ValueError(f"{ENV_MIN_QUOTE_DEPOSIT_SOL}_INVALID")
    try:
        value = Decimal(text)
    except InvalidOperation as exc:
        raise ValueError(f"{ENV_MIN_QUOTE_DEPOSIT_SOL}_INVALID") from exc
    return MigrationAdmissionConfig(min_quote_deposit_sol=value)


@dataclass(frozen=True)
class MigrationProofSnapshot:
    """Immutable, mint-bound record of one proven pump.fun migration."""

    proof_version: str
    proof_source: str
    candidate_mint: str
    pool: str
    base_mint: str
    quote_mint: str
    base_vault: str
    quote_vault: str
    migration_authority: str
    migration_signature: str
    migration_slot: int
    outer_instruction_index: int
    inner_instruction_index: int
    flattened_instruction_index: int
    pumpfun_program_id: str
    pumpswap_program_id: str
    canonical_pda_valid: bool
    pool_creation_index_arg: int
    vault_derivation_valid: bool
    vault_ownership_valid: bool
    quote_deposit_raw: int
    quote_deposit_decimals: int
    quote_deposit_sol: str
    base_deposit_raw: int
    base_deposit_decimals: Optional[int]
    min_quote_deposit_sol: str
    mint_suffix_consistent: bool
    observed_at_utc: str
    # Which pinned pump.fun migration instruction proved the CPI ancestry
    # ("migrate" | "migrate_v2").  Part of the sealed digest.
    migration_instruction_version: str = MIGRATION_VERSION_V1
    reason_codes: Tuple[str, ...] = ()
    proof_digest: str = ""

    def to_dict(self) -> Dict[str, Any]:
        value = asdict(self)
        value["reason_codes"] = list(self.reason_codes)
        return value


def _proof_digest(proof: MigrationProofSnapshot) -> str:
    payload = proof.to_dict()
    payload.pop("proof_digest", None)
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def seal_migration_proof(proof: MigrationProofSnapshot) -> MigrationProofSnapshot:
    return replace(proof, proof_digest=_proof_digest(replace(proof, proof_digest="")))


def validate_migration_proof(proof: object) -> Tuple[bool, Optional[str]]:
    """Independent fail-closed validation for every proof consumer."""

    if not isinstance(proof, MigrationProofSnapshot):
        return False, "MIGRATION_PROOF_MISSING"
    if proof.proof_version != MIGRATION_PROOF_VERSION:
        return False, "MIGRATION_PROOF_VERSION_MISMATCH"
    if not proof.proof_digest or proof.proof_digest != _proof_digest(proof):
        return False, "MIGRATION_PROOF_DIGEST_MISMATCH"
    if not proof.candidate_mint or proof.candidate_mint != proof.base_mint:
        return False, MIGRATION_MINT_BINDING_INVALID
    if not proof.migration_signature or not proof.pool:
        return False, MIGRATION_EVENT_MALFORMED
    if proof.pumpfun_program_id != PUMPFUN_PROGRAM_ID:
        return False, MIGRATION_PROGRAM_PROOF_MISSING
    if proof.pumpswap_program_id != PUMPSWAP_PROGRAM_ID:
        return False, MIGRATION_PROGRAM_PROOF_MISSING
    if not proof.canonical_pda_valid:
        return False, CANONICAL_POOL_MISMATCH
    if not proof.vault_derivation_valid or not proof.vault_ownership_valid:
        return False, MIGRATION_VAULT_PROOF_INVALID
    if proof.migration_instruction_version not in MIGRATION_VERSIONS:
        return False, MIGRATION_PROGRAM_PROOF_MISSING
    if proof.reason_codes:
        return False, MIGRATION_EVENT_MALFORMED
    return True, None


def migration_proof_matches_identity(proof: object, identity: object) -> bool:
    """True iff a valid sealed proof binds the same mint/pool/quote/signature."""

    valid, _ = validate_migration_proof(proof)
    if not valid:
        return False
    assert isinstance(proof, MigrationProofSnapshot)
    return bool(
        proof.candidate_mint == getattr(identity, "candidate_mint", None)
        and proof.pool == getattr(identity, "pool", None)
        and proof.quote_mint == getattr(identity, "quote_mint", None)
        and proof.migration_signature == getattr(identity, "migration_signature", None)
    )


def is_exact_mint_address(value: object) -> bool:
    """A case-sensitive, canonical 32-byte Base58 public key; never normalize it."""
    if not isinstance(value, str) or not 32 <= len(value) <= 44:
        return False
    try:
        return len(b58decode(value)) == 32
    except (TypeError, ValueError):
        return False


def is_supported_mint_identity(value: object) -> bool:
    """Storage identity, NOT migration authorization.

    Legacy suffix keys remain readable for old checkpoints and offline fixtures.
    New real addresses have no suffix requirement. Discovery must independently
    pass ``candidate_migration_is_admitted`` before these stores are populated.
    """
    return bool(isinstance(value, str) and value and (
        value.endswith("pump") or is_exact_mint_address(value)))


def candidate_migration_proof(value: object) -> Optional[MigrationProofSnapshot]:
    """Parse a sealed admission record and recheck its structural invariants.

    The digest protects record integrity, not provenance: producers may attach
    this record only from the same transaction's successful admission decision.
    Unlike the historical display validator, this boundary also re-derives the
    pool and vault addresses and checks the recorded deposit floor.
    """
    try:
        if isinstance(value, Mapping):
            payload = dict(value)
            payload["reason_codes"] = tuple(payload.get("reason_codes") or ())
            proof = MigrationProofSnapshot(**payload)
        elif isinstance(value, MigrationProofSnapshot):
            proof = value
        else:
            return None
        if validate_migration_proof(proof) != (True, None):
            return None
        if proof.proof_source != MIGRATION_PROOF_SOURCE:
            return None
        if not all(is_exact_mint_address(key) for key in (
                proof.candidate_mint, proof.pool, proof.quote_mint,
                proof.base_vault, proof.quote_vault, proof.migration_authority)):
            return None
        if proof.quote_mint != WSOL_MINT or proof.candidate_mint == proof.quote_mint:
            return None
        signature = proof.migration_signature
        if not isinstance(signature, str) or not 64 <= len(signature) <= 88:
            return None
        alphabet = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
        number = 0
        for char in signature:
            digit = alphabet.find(char)
            if digit < 0:
                return None
            number = number * 58 + digit
        if len(signature) - len(signature.lstrip("1")) + (number.bit_length() + 7) // 8 != 64:
            return None
        for number in (proof.migration_slot, proof.outer_instruction_index,
                       proof.inner_instruction_index, proof.flattened_instruction_index,
                       proof.pool_creation_index_arg, proof.quote_deposit_raw,
                       proof.quote_deposit_decimals, proof.base_deposit_raw):
            if isinstance(number, bool) or not isinstance(number, int) or number < 0:
                return None
        if proof.pool_creation_index_arg > 65535 or proof.quote_deposit_decimals != 9:
            return None
        if any(flag is not True for flag in (
                proof.canonical_pda_valid, proof.vault_derivation_valid,
                proof.vault_ownership_valid)):
            return None
        deposit = Decimal(proof.quote_deposit_sol)
        floor = Decimal(proof.min_quote_deposit_sol)
        if (not deposit.is_finite() or not floor.is_finite() or floor <= 0
                or deposit < floor or deposit != Decimal(proof.quote_deposit_raw) / Decimal(10 ** 9)):
            return None
        if derive_pool_address(index=proof.pool_creation_index_arg,
                creator=proof.migration_authority, base_mint=proof.base_mint,
                quote_mint=proof.quote_mint) != proof.pool:
            return None
        for mint, vault in ((proof.base_mint, proof.base_vault),
                            (proof.quote_mint, proof.quote_vault)):
            if not any(derive_associated_token_address(owner=proof.pool,
                    token_program=program, mint=mint,
                    associated_program=ASSOCIATED_TOKEN_PROGRAM_ID) == vault
                    for program in TOKEN_PROGRAM_IDS):
                return None
        return proof
    except (TypeError, ValueError, ArithmeticError, OverflowError):
        return None


def candidate_migration_is_admitted(candidate: object) -> bool:
    """One shared candidate/restart guard, with exact proof identity binding.

    A missing proof retains the legacy suffix-only path. A present invalid proof
    never falls back to that path, even when the mint ends in ``pump``.
    """
    if not isinstance(candidate, Mapping):
        return False
    mint = candidate.get("token_mint")
    raw = candidate.get("migration_proof")
    if raw is None:
        return isinstance(mint, str) and bool(mint) and mint.endswith("pump")
    proof = candidate_migration_proof(raw)
    return bool(proof is not None
        and mint == proof.candidate_mint
        and candidate.get("pair_address") == proof.pool
        and candidate.get("migration_signature") == proof.migration_signature
        and isinstance(candidate.get("migration_slot"), int)
        and not isinstance(candidate.get("migration_slot"), bool)
        and candidate.get("migration_slot") == proof.migration_slot)


def attach_candidate_migration_proof(candidate: Dict[str, Any], proof: object,
                                     *, quote_mint: object = None) -> bool:
    """Attach only the exact decoded event's proof, before any queue or dedupe."""
    checked = candidate_migration_proof(proof)
    if checked is None or candidate.get("token_mint") != checked.candidate_mint:
        return False
    if candidate.get("pair_address") != checked.pool:
        return False
    if quote_mint is not None and quote_mint != checked.quote_mint:
        return False
    signature = candidate.get("migration_signature")
    if signature is not None and signature != checked.migration_signature:
        return False
    slot = candidate.get("migration_slot")
    if slot is not None and (isinstance(slot, bool) or not isinstance(slot, int)
                             or slot != checked.migration_slot):
        return False
    candidate["migration_slot"] = checked.migration_slot
    candidate["migration_signature"] = checked.migration_signature
    candidate["migration_proof"] = checked.to_dict()
    return candidate_migration_is_admitted(candidate)


@dataclass(frozen=True)
class MigrationAdmissionDecision:
    """Outcome of evaluating one pool-creation transaction."""

    admitted: bool
    classification: str
    reason_codes: Tuple[str, ...]
    candidate_mint: Optional[str]
    pool: Optional[str]
    quote_mint: Optional[str]
    transaction_signature: Optional[str]
    slot: Optional[int]
    deposit_bucket: str
    quote_deposit_sol: Optional[str]
    proof: Optional[MigrationProofSnapshot] = None
    # Set on admission only: which pinned migration instruction proved the
    # ancestry ("migrate" | "migrate_v2").  Rejections carry None.
    migration_version: Optional[str] = None

    def diagnostic_record(self) -> Dict[str, Any]:
        """Redaction-safe rejection/admission evidence for local artifacts."""
        return {
            "kind": "PHX2_MIGRATION_ADMISSION",
            "admitted": bool(self.admitted),
            "classification": self.classification,
            "reason_codes": list(self.reason_codes),
            "token_mint": self.candidate_mint,
            "pool": self.pool,
            "quote_mint": self.quote_mint,
            "transaction_signature": self.transaction_signature,
            "slot": self.slot,
            "deposit_bucket": self.deposit_bucket,
            "quote_deposit_sol": self.quote_deposit_sol,
            "migration_version": self.migration_version,
        }


def _deposit_bucket(quote_deposit_sol: Optional[Decimal]) -> str:
    if quote_deposit_sol is None:
        return DEPOSIT_BUCKET_UNKNOWN
    if quote_deposit_sol < Decimal(1):
        return DEPOSIT_BUCKET_LT_1
    if quote_deposit_sol < Decimal(10):
        return DEPOSIT_BUCKET_1_10
    if quote_deposit_sol < Decimal(50):
        return DEPOSIT_BUCKET_10_50
    return DEPOSIT_BUCKET_GE_50


def _resolve_key_text(keys: Sequence[bytes], index: object) -> Optional[str]:
    if isinstance(index, bool) or not isinstance(index, int):
        return None
    if not (0 <= index < len(keys)):
        return None
    return _b58encode_any(keys[index])


def _collect_account_keys(message: object, meta: object) -> List[bytes]:
    keys = [bytes(value) for value in list(getattr(message, "account_keys", ()) or ())]
    # Versioned transactions resolve address-table lookups into the loaded
    # writable/readonly extensions, in that exact order.
    keys.extend(bytes(value) for value in list(
        getattr(meta, "loaded_writable_addresses", ()) or ()))
    keys.extend(bytes(value) for value in list(
        getattr(meta, "loaded_readonly_addresses", ()) or ()))
    return keys


class TransactionExecutionStatus(Enum):
    """Closed-set classification of one transaction's execution outcome.

    Only :attr:`SUCCESS` may continue to the remaining admission/routing gates.
    Every other member is a fail-closed outcome: a recognized on-chain
    :attr:`FAILED`, or an indeterminate :attr:`MALFORMED` / :attr:`UNSUPPORTED`
    / :attr:`ACCESS_ERROR` / :attr:`PRESENCE_CONFLICT` representation that must
    never be trusted as success.
    """

    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    MALFORMED = "MALFORMED"
    UNSUPPORTED = "UNSUPPORTED"
    ACCESS_ERROR = "ACCESS_ERROR"
    PRESENCE_CONFLICT = "PRESENCE_CONFLICT"


# The generated ``TransactionStatusMeta`` error field, and the inner
# ``TransactionError`` payload field, share the same name in the vendored
# ``solana.storage.ConfirmedBlock`` schema.
_TX_ERR_FIELD = "err"
_ABSENT = object()


def _has_populated_error_bytes(meta: object) -> bool:
    """Exception-safe check for populated inner error bytes.

    Used only to reject a protobuf presence answer of "no error" that
    nonetheless carries populated failure evidence.  Never invokes truthiness
    or ``repr`` on the provider object.
    """
    try:
        err = getattr(meta, _TX_ERR_FIELD, None)
        inner = getattr(err, _TX_ERR_FIELD, None)
    except Exception:
        return False
    return isinstance(inner, (bytes, bytearray)) and len(inner) > 0


def _classify_transaction_execution_status(
    meta: object,
) -> TransactionExecutionStatus:
    if meta is None:
        return TransactionExecutionStatus.UNSUPPORTED

    has_field = getattr(meta, "HasField", None)
    if callable(has_field):
        # Generated-protobuf presence path: the message-typed ``err`` field's
        # presence is the authoritative success/failure signal, read through the
        # provider-supported API rather than through truthiness.
        try:
            present = has_field(_TX_ERR_FIELD)
        except Exception:
            # ``err`` is not a field of this message => unsupported schema.
            return TransactionExecutionStatus.UNSUPPORTED
        if present is True:
            return TransactionExecutionStatus.FAILED
        if present is not False:
            # A non-bool presence answer is not a supported presence contract.
            return TransactionExecutionStatus.UNSUPPORTED
        # Presence says "no error".  Reject the contradictory case where the
        # field nonetheless carries populated failure evidence.
        if _has_populated_error_bytes(meta):
            return TransactionExecutionStatus.PRESENCE_CONFLICT
        return TransactionExecutionStatus.SUCCESS

    # Attribute-object path (deterministic fixtures / non-protobuf providers).
    err = getattr(meta, _TX_ERR_FIELD, _ABSENT)
    if err is _ABSENT or err is None:
        # Canonical success: the top-level error field is unset / explicitly
        # None.  This is the ONLY success encoding on this path.
        return TransactionExecutionStatus.SUCCESS
    # A present, non-None error container is never canonical success.  The only
    # recognized failure encoding is a wrapper carrying nonempty error bytes; a
    # missing inner field must never default to a successful empty value.
    inner = getattr(err, _TX_ERR_FIELD, _ABSENT)
    if inner is _ABSENT or inner is None:
        return TransactionExecutionStatus.MALFORMED
    if isinstance(inner, (bytes, bytearray)):
        return (TransactionExecutionStatus.FAILED if len(inner) > 0
                else TransactionExecutionStatus.MALFORMED)
    # Any other inner type (str/int/bool/list/dict/object) is unsupported and
    # is never automatically treated as success by virtue of being falsey.
    return TransactionExecutionStatus.MALFORMED


def classify_transaction_execution_status(
    meta: object,
) -> TransactionExecutionStatus:
    """Classify one transaction's execution outcome, fail-closed by construction.

    Provider contract (vendored ``solana.storage.ConfirmedBlock``):

      * ``TransactionStatusMeta.err`` is a message-typed field
        (``TransactionError``) whose presence is authoritative — unset means the
        transaction succeeded, set means it failed.  Presence is read through
        the generated ``HasField("err")`` API, never through truthiness.
      * ``TransactionError.err`` is the serialized (nonempty) error payload.

    Deterministic offline fixtures model the same shape with attribute objects:
    canonical success omits ``err`` (or sets it to ``None``); canonical failure
    carries a wrapper whose inner ``err`` is nonempty ``bytes``.

    Only those exact canonical success encodings return
    :attr:`TransactionExecutionStatus.SUCCESS`.  A non-``None`` error container
    that is not a recognized failure — a missing inner field, a ``None`` inner
    field, an empty or wrong-typed inner field, an unsupported object, a raising
    magic method, or presence that contradicts populated failure evidence — is
    classified as a fail-closed status and never as success.  No provider object
    is mutated and no user-defined ``__bool__`` / ``__repr__`` is invoked.
    """
    try:
        return _classify_transaction_execution_status(meta)
    except Exception:
        # Any unexpected access/parsing explosion (hostile magic methods,
        # unknown provider drift) fails closed rather than defaulting to success.
        return TransactionExecutionStatus.ACCESS_ERROR


# Closed-set migration reason for each non-success execution status.  Recognized
# on-chain failure keeps its historical reason; the indeterminate statuses carry
# the precise fail-closed transaction reasons.
_TRANSACTION_STATUS_REJECTION_REASON: Dict[TransactionExecutionStatus, str] = {
    TransactionExecutionStatus.FAILED: MIGRATION_TRANSACTION_FAILED,
    TransactionExecutionStatus.MALFORMED: TRANSACTION_ERROR_MALFORMED_FAIL_CLOSED,
    TransactionExecutionStatus.UNSUPPORTED: TRANSACTION_ERROR_UNSUPPORTED_ENCODING,
    TransactionExecutionStatus.ACCESS_ERROR: TRANSACTION_ERROR_ACCESS_FAILED,
    TransactionExecutionStatus.PRESENCE_CONFLICT: TRANSACTION_ERROR_PRESENCE_CONFLICT,
}


def _transaction_failed(meta: object) -> bool:
    """Fail closed: only an explicitly recognized SUCCESS status is not failed.

    Preserves the historical boolean boundary for existing callers (migration
    admission and trusted reserve routing) while classification itself is now
    explicit — see :func:`classify_transaction_execution_status`.  Every
    non-SUCCESS status (recognized on-chain failure and every
    malformed/unsupported/indeterminate representation alike) returns ``True`` so
    the transaction is rejected.
    """
    return (classify_transaction_execution_status(meta)
            is not TransactionExecutionStatus.SUCCESS)


def _stack_height(instruction: object) -> Optional[int]:
    value = getattr(instruction, "stack_height", None)
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        return None
    return value


@dataclass(frozen=True)
class _InnerCreatePool:
    outer_index: int
    inner_index: int
    flattened_index: int
    instruction: Any
    stack_height: Optional[int]
    group_instructions: Tuple[Any, ...]
    top_level_program: Optional[str]
    top_level_data: bytes


def _find_create_pool_sites(
    message: object, meta: object, keys: Sequence[bytes],
) -> Tuple[List[int], List[_InnerCreatePool]]:
    """Locate every exact-discriminator create_pool site, split by position."""

    discriminator = bytes(PUMPSWAP_CREATE_POOL_INSTRUCTION_DISCRIMINATOR)
    top_level_hits: List[int] = []
    inner_hits: List[_InnerCreatePool] = []
    top_instructions = list(getattr(message, "instructions", ()) or ())
    # The overwhelming majority of scanned PumpSwap instructions are ordinary
    # Buy/Sell, not create_pool.  Test the cheap 8-byte discriminator prefix
    # first and only resolve the program key (raw bytes, not base58) for the
    # rare instruction whose data is create_pool-shaped.
    for outer_index, instruction in enumerate(top_instructions):
        try:
            data = bytes(instruction.data)
            if not data.startswith(discriminator):
                continue
            program_index = int(instruction.program_id_index)
        except Exception:
            continue
        if _program_key_matches(keys, program_index, PUMPSWAP_PROGRAM_ID_BYTES):
            top_level_hits.append(outer_index)
    flattened = len(top_instructions)
    for group in list(getattr(meta, "inner_instructions", ()) or ()):
        try:
            group_index = int(getattr(group, "index"))
        except Exception:
            continue
        group_instructions = tuple(getattr(group, "instructions", ()) or ())
        # The group's top-level frame is only needed to describe a create_pool
        # hit, so it is resolved lazily on the first hit in this group.
        top_program: Optional[str] = None
        top_data = b""
        top_resolved = False
        for inner_index, instruction in enumerate(group_instructions):
            flattened += 1
            try:
                data = bytes(instruction.data)
                if not data.startswith(discriminator):
                    continue
                program_index = int(instruction.program_id_index)
            except Exception:
                continue
            if not _program_key_matches(keys, program_index, PUMPSWAP_PROGRAM_ID_BYTES):
                continue
            if not top_resolved:
                top_resolved = True
                if 0 <= group_index < len(top_instructions):
                    top = top_instructions[group_index]
                    try:
                        top_program = _resolve_key_text(keys, int(top.program_id_index))
                        top_data = bytes(top.data)
                    except Exception:
                        top_program, top_data = None, b""
            inner_hits.append(_InnerCreatePool(
                outer_index=group_index,
                inner_index=inner_index,
                flattened_index=flattened - 1,
                instruction=instruction,
                stack_height=_stack_height(instruction),
                group_instructions=group_instructions,
                top_level_program=top_program,
                top_level_data=top_data,
            ))
    return top_level_hits, inner_hits


def _migration_discriminator_version(data: bytes) -> Optional[str]:
    """Closed-set version for one pump.fun instruction's leading 8 bytes.

    Only the exact pinned ``migrate``/``migrate_v2`` discriminators match;
    unknown or future pump.fun instruction discriminators return ``None`` so
    admission fails closed instead of trusting an unrecognized variant.
    """
    if not isinstance(data, (bytes, bytearray)) or len(data) < 8:
        return None
    return PUMPFUN_MIGRATION_INSTRUCTION_DISCRIMINATORS.get(bytes(data[:8]))


def _migration_ancestry_version(
    site: _InnerCreatePool, keys: Sequence[bytes],
) -> Optional[str]:
    """Deterministic CPI ancestry: the create_pool must execute inside an
    official pump.fun migration instruction frame (``migrate`` or
    ``migrate_v2``).  Returns the proven version, or ``None``."""

    if site.top_level_program == PUMPFUN_PROGRAM_ID:
        version = _migration_discriminator_version(site.top_level_data)
        if version is not None:
            return version
    # Wrapper case: the pump.fun migration itself runs as a CPI inside this
    # group.  Ancestry is provable only from recorded stack heights: a prior
    # pump.fun migration instruction whose frame is still open (no instruction
    # at or below its stack height between it and the create_pool).
    if site.stack_height is None:
        return None
    for candidate_index in range(site.inner_index - 1, -1, -1):
        instruction = site.group_instructions[candidate_index]
        try:
            program = _resolve_key_text(keys, int(instruction.program_id_index))
            data = bytes(instruction.data)
        except Exception:
            continue
        height = _stack_height(instruction)
        if height is None:
            continue
        if height >= site.stack_height:
            continue
        frame_open = True
        for between_index in range(candidate_index + 1, site.inner_index):
            between_height = _stack_height(site.group_instructions[between_index])
            if between_height is not None and between_height <= height:
                frame_open = False
                break
        if not frame_open:
            continue
        if program == PUMPFUN_PROGRAM_ID:
            return _migration_discriminator_version(data)
        # The nearest open ancestor frame is NOT pump.fun: this create_pool
        # belongs to some other program's CPI chain.
        return None
    return None


def _migration_ancestry_proven(site: _InnerCreatePool, keys: Sequence[bytes]) -> bool:
    return _migration_ancestry_version(site, keys) is not None


def migration_cpi_ancestry_version(
    *,
    group_instructions: Sequence[Any],
    inner_index: int,
    top_level_program: Optional[str],
    top_level_data: bytes,
    keys: Sequence[bytes],
) -> Optional[str]:
    """Public ancestry check for one inner instruction of one CPI group.

    Returns the proven migration version ("migrate" | "migrate_v2") iff the
    instruction at ``inner_index`` deterministically executes inside an
    official pump.fun migration frame (either the group's top-level
    instruction is a pinned pump.fun migration instruction, or a still-open
    pump.fun migration frame precedes it per recorded stack heights);
    ``None`` otherwise, including for unknown pump.fun discriminators.
    """
    if isinstance(inner_index, bool) or not isinstance(inner_index, int):
        return None
    group = tuple(group_instructions or ())
    if not (0 <= inner_index < len(group)):
        return None
    instruction = group[inner_index]
    site = _InnerCreatePool(
        outer_index=0,
        inner_index=inner_index,
        flattened_index=inner_index,
        instruction=instruction,
        stack_height=_stack_height(instruction),
        group_instructions=group,
        top_level_program=top_level_program,
        top_level_data=bytes(top_level_data or b""),
    )
    return _migration_ancestry_version(site, keys)


def migration_cpi_ancestry_proven(
    *,
    group_instructions: Sequence[Any],
    inner_index: int,
    top_level_program: Optional[str],
    top_level_data: bytes,
    keys: Sequence[bytes],
) -> bool:
    """Boolean form of :func:`migration_cpi_ancestry_version`."""
    return migration_cpi_ancestry_version(
        group_instructions=group_instructions,
        inner_index=inner_index,
        top_level_program=top_level_program,
        top_level_data=top_level_data,
        keys=keys,
    ) is not None


def _token_balance_evidence(
    meta: object, keys: Sequence[bytes],
) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, Dict[str, Any]]]:
    """Address-keyed pre/post token balance facts (amount, decimals, owner, mint)."""

    out: Tuple[Dict[str, Dict[str, Any]], Dict[str, Dict[str, Any]]] = ({}, {})
    for slot_index, attr in enumerate(("pre_token_balances", "post_token_balances")):
        for balance in list(getattr(meta, attr, ()) or ()):
            try:
                address = _resolve_key_text(keys, int(balance.account_index))
                if not address:
                    continue
                token_amount = getattr(balance, "ui_token_amount", None)
                amount_text = getattr(token_amount, "amount", None)
                decimals = getattr(token_amount, "decimals", None)
                record: Dict[str, Any] = {}
                if isinstance(amount_text, str) and amount_text.isdigit():
                    record["amount"] = int(amount_text)
                if (not isinstance(decimals, bool) and isinstance(decimals, int)
                        and 0 <= decimals <= 32):
                    record["decimals"] = decimals
                owner = getattr(balance, "owner", None)
                if isinstance(owner, str) and owner:
                    record["owner"] = owner
                mint = getattr(balance, "mint", None)
                if isinstance(mint, str) and mint:
                    record["mint"] = mint
                if record:
                    out[slot_index][address] = record
            except Exception:
                continue
    return out


def _diagnostic_wsol_deposit(
    pre: Mapping[str, Mapping[str, Any]],
    post: Mapping[str, Mapping[str, Any]],
) -> Optional[Decimal]:
    """Best-effort largest positive WSOL vault delta, for rejection buckets only."""
    best: Optional[Decimal] = None
    for address, record in post.items():
        if record.get("mint") != WSOL_MINT or record.get("decimals") != 9:
            continue
        amount = record.get("amount")
        if not isinstance(amount, int):
            continue
        previous = pre.get(address, {}).get("amount", 0)
        if not isinstance(previous, int):
            previous = 0
        delta = amount - previous
        if delta > 0:
            value = Decimal(delta) / (Decimal(10) ** 9)
            if best is None or value > best:
                best = value
    return best


def _diagnostic_layout(instruction: object, keys: Sequence[bytes]) -> Tuple[
        Optional[str], Optional[str], Optional[str]]:
    """Best-effort (pool, base, quote) from one create_pool site, for diagnostics."""
    try:
        indices = list(bytes(instruction.accounts))
    except Exception:
        return None, None, None
    if len(indices) <= CREATE_POOL_IDX_QUOTE_MINT:
        return None, None, None
    pool = _resolve_key_text(keys, indices[CREATE_POOL_IDX_POOL])
    mint_a = _resolve_key_text(keys, indices[CREATE_POOL_IDX_BASE_MINT])
    mint_b = _resolve_key_text(keys, indices[CREATE_POOL_IDX_QUOTE_MINT])
    known = set(KNOWN_QUOTE_MINT_TO_PROVIDER_PAIR_TYPE_HINT)
    if mint_a in known and mint_b not in known:
        return pool, mint_b, mint_a
    return pool, mint_a, mint_b


def evaluate_migration_admission(
    update: object,
    *,
    config: Optional[MigrationAdmissionConfig] = None,
    observed_at_utc: str = "",
) -> Optional[MigrationAdmissionDecision]:
    """Evaluate one SubscribeUpdate.  Returns ``None`` when the transaction
    contains no exact create_pool discriminator at all (not a pool creation);
    otherwise an admitted/rejected decision with closed-set reason codes."""

    cfg = config or MigrationAdmissionConfig()
    try:
        wrapper = update.transaction
        tx_info = wrapper.transaction
        message = tx_info.transaction.message
        meta = tx_info.meta
    except Exception:
        return None
    keys = _collect_account_keys(message, meta)
    if not keys:
        return None
    top_level_hits, inner_hits = _find_create_pool_sites(message, meta, keys)
    if not top_level_hits and not inner_hits:
        # Not a pool creation: the dominant per-transaction case.  The signature
        # and slot below are only needed to describe a rejection or proof, so
        # they are computed AFTER this early return -- a non-create_pool tx never
        # base58-encodes its signature here.
        return None
    try:
        signature = _b58encode_any(bytes(tx_info.signature))
    except Exception:
        signature = None
    try:
        slot = int(wrapper.slot)
    except Exception:
        slot = None

    def _reject(reasons: Sequence[str], *, classification: str,
                mint: Optional[str] = None, pool: Optional[str] = None,
                quote: Optional[str] = None,
                quote_deposit_sol: Optional[Decimal] = None,
                ) -> MigrationAdmissionDecision:
        return MigrationAdmissionDecision(
            admitted=False,
            classification=classification,
            reason_codes=tuple(dict.fromkeys(reasons)),
            candidate_mint=mint,
            pool=pool,
            quote_mint=quote,
            transaction_signature=signature,
            slot=slot,
            deposit_bucket=_deposit_bucket(quote_deposit_sol),
            quote_deposit_sol=(
                format(quote_deposit_sol, "f") if quote_deposit_sol is not None else None),
        )

    if not signature:
        return _reject((MIGRATION_EVENT_MALFORMED,),
                       classification=POOL_CREATION_CPI_UNPROVEN)
    # Transaction execution status is resolved before any migration proof is
    # authorized: a recognized failure, or any malformed/unsupported/
    # indeterminate error representation, is rejected here with its precise
    # closed-set reason rather than being reclassified by a lower-level check.
    tx_status = classify_transaction_execution_status(meta)
    if tx_status is not TransactionExecutionStatus.SUCCESS:
        return _reject((_TRANSACTION_STATUS_REJECTION_REASON[tx_status],),
                       classification=POOL_CREATION_CPI_UNPROVEN)

    if not inner_hits:
        # Top-level create_pool = direct user-created pool.  Signer presence
        # is NOT migration proof; direct pools never enter migration discovery.
        # Layout/deposit extraction here is best-effort DIAGNOSTIC evidence.
        pre_diag, post_diag = _token_balance_evidence(meta, keys)
        top_instructions = list(getattr(message, "instructions", ()) or ())
        pool_diag, mint_diag, quote_diag = _diagnostic_layout(
            top_instructions[top_level_hits[0]], keys)
        return _reject(
            (CREATE_POOL_NOT_IN_MIGRATION_CPI, NOT_PUMPFUN_MIGRATION),
            classification=POOL_CREATION_DIRECT,
            mint=mint_diag, pool=pool_diag, quote=quote_diag,
            quote_deposit_sol=_diagnostic_wsol_deposit(pre_diag, post_diag))

    proven_sites = [
        (site, version) for site, version in (
            (site, _migration_ancestry_version(site, keys))
            for site in inner_hits)
        if version is not None
    ]
    if not proven_sites:
        pre_diag, post_diag = _token_balance_evidence(meta, keys)
        pool_diag, mint_diag, quote_diag = _diagnostic_layout(
            inner_hits[0].instruction, keys)
        return _reject(
            (MIGRATION_PROGRAM_PROOF_MISSING, NOT_PUMPFUN_MIGRATION),
            classification=POOL_CREATION_CPI_UNPROVEN,
            mint=mint_diag, pool=pool_diag, quote=quote_diag,
            quote_deposit_sol=_diagnostic_wsol_deposit(pre_diag, post_diag))
    if len(proven_sites) != 1 or top_level_hits:
        # Duplicate/ambiguous create_pool sites inside one signature can not
        # bind a single canonical proof.
        return _reject((MIGRATION_EVENT_MALFORMED,),
                       classification=POOL_CREATION_CPI_UNPROVEN)
    site, migration_version = proven_sites[0]

    try:
        data = bytes(site.instruction.data)
        account_indices = list(bytes(site.instruction.accounts))
    except Exception:
        return _reject((MIGRATION_EVENT_MALFORMED,),
                       classification=POOL_CREATION_MIGRATION_CPI)
    if len(data) < CREATE_POOL_DATA_MIN_LEN or len(account_indices) < CREATE_POOL_ACCOUNT_COUNT:
        # Program-layout drift (shorter data or fewer accounts than the pinned
        # IDL layout) fails closed instead of guessing account positions.
        return _reject((MIGRATION_EVENT_MALFORMED,),
                       classification=POOL_CREATION_MIGRATION_CPI)
    accounts = [_resolve_key_text(keys, index) or "" for index in account_indices]
    pool = accounts[CREATE_POOL_IDX_POOL]
    creator = accounts[CREATE_POOL_IDX_CREATOR]
    mint_a = accounts[CREATE_POOL_IDX_BASE_MINT]
    mint_b = accounts[CREATE_POOL_IDX_QUOTE_MINT]
    base_vault_a = accounts[CREATE_POOL_IDX_BASE_VAULT]
    quote_vault_a = accounts[CREATE_POOL_IDX_QUOTE_VAULT]
    base_token_program = accounts[13]
    quote_token_program = accounts[14]
    fixed_accounts_valid = bool(
        accounts[11] == SYSTEM_PROGRAM_ID
        and accounts[12] == TOKEN_2022_PROGRAM_ID
        and base_token_program in TOKEN_PROGRAM_IDS
        and quote_token_program in TOKEN_PROGRAM_IDS
        and accounts[15] == ASSOCIATED_TOKEN_PROGRAM_ID
        and accounts[17] == PUMPSWAP_PROGRAM_ID)
    if not (pool and creator and mint_a and mint_b and fixed_accounts_valid):
        return _reject((MIGRATION_EVENT_MALFORMED,),
                       classification=POOL_CREATION_MIGRATION_CPI,
                       pool=pool or None)

    known_quotes = set(KNOWN_QUOTE_MINT_TO_PROVIDER_PAIR_TYPE_HINT)
    quote_a = mint_a in known_quotes
    quote_b = mint_b in known_quotes
    if quote_a == quote_b:
        return _reject((MIGRATION_QUOTE_MINT_UNSUPPORTED, MIGRATION_MINT_BINDING_INVALID),
                       classification=POOL_CREATION_MIGRATION_CPI, pool=pool)
    if quote_a:
        base_mint, quote_mint = mint_b, mint_a
        base_vault, quote_vault = quote_vault_a, base_vault_a
        base_token_program, quote_token_program = quote_token_program, base_token_program
    else:
        base_mint, quote_mint = mint_a, mint_b
        base_vault, quote_vault = base_vault_a, quote_vault_a
    if len({pool, base_mint, quote_mint}) != 3 or not base_vault or not quote_vault:
        return _reject((MIGRATION_MINT_BINDING_INVALID,),
                       classification=POOL_CREATION_MIGRATION_CPI, pool=pool)

    index_arg = struct.unpack_from("<H", data, 8)[0]
    try:
        canonical_pool = derive_pool_address(
            index=index_arg, creator=creator, base_mint=mint_a, quote_mint=mint_b)
        canonical_pda_valid = canonical_pool == pool
    except ValueError:
        canonical_pda_valid = False
    if not canonical_pda_valid:
        return _reject((CANONICAL_POOL_MISMATCH,),
                       classification=POOL_CREATION_MIGRATION_CPI,
                       mint=base_mint, pool=pool, quote=quote_mint)
    try:
        vault_derivation_valid = bool(
            base_vault == derive_associated_token_address(
                owner=pool, token_program=base_token_program, mint=base_mint,
                associated_program=ASSOCIATED_TOKEN_PROGRAM_ID)
            and quote_vault == derive_associated_token_address(
                owner=pool, token_program=quote_token_program, mint=quote_mint,
                associated_program=ASSOCIATED_TOKEN_PROGRAM_ID))
    except ValueError:
        vault_derivation_valid = False

    pre, post = _token_balance_evidence(meta, keys)
    base_post = post.get(base_vault, {})
    quote_post = post.get(quote_vault, {})
    vault_ownership_valid = bool(
        base_post.get("owner") == pool and quote_post.get("owner") == pool)
    if not vault_derivation_valid or not vault_ownership_valid:
        return _reject((MIGRATION_VAULT_PROOF_INVALID,),
                       classification=POOL_CREATION_MIGRATION_CPI,
                       mint=base_mint, pool=pool, quote=quote_mint)

    # Base-mint coherence across instruction accounts and balance evidence.
    base_balance_mint = base_post.get("mint")
    quote_balance_mint = quote_post.get("mint")
    if ((base_balance_mint is not None and base_balance_mint != base_mint)
            or (quote_balance_mint is not None and quote_balance_mint != quote_mint)):
        return _reject((MIGRATION_MINT_BINDING_INVALID,),
                       classification=POOL_CREATION_MIGRATION_CPI,
                       mint=base_mint, pool=pool, quote=quote_mint)

    # Exact quote deposit with unit/decimal validation.  The floor is
    # SOL-denominated, so it is only provable against the wrapped-SOL quote
    # (9 decimals); any other configuration fails closed as missing.
    quote_post_amount = quote_post.get("amount")
    quote_pre_amount = pre.get(quote_vault, {}).get("amount", 0)
    quote_decimals = quote_post.get("decimals")
    quote_deposit_raw: Optional[int] = None
    if isinstance(quote_post_amount, int) and isinstance(quote_pre_amount, int):
        delta = quote_post_amount - quote_pre_amount
        if delta > 0:
            quote_deposit_raw = delta
    deposit_provable = bool(
        quote_deposit_raw is not None
        and quote_mint == WSOL_MINT
        and quote_decimals == 9)
    if not deposit_provable:
        return _reject((MIGRATION_QUOTE_DEPOSIT_MISSING,),
                       classification=POOL_CREATION_MIGRATION_CPI,
                       mint=base_mint, pool=pool, quote=quote_mint)
    quote_deposit_sol = (
        Decimal(quote_deposit_raw) / (Decimal(10) ** int(quote_decimals)))
    if quote_deposit_sol < cfg.min_quote_deposit_sol:
        return _reject((MIGRATION_QUOTE_DEPOSIT_BELOW_FLOOR,),
                       classification=POOL_CREATION_MIGRATION_CPI,
                       mint=base_mint, pool=pool, quote=quote_mint,
                       quote_deposit_sol=quote_deposit_sol)

    base_post_amount = base_post.get("amount")
    base_pre_amount = pre.get(base_vault, {}).get("amount", 0)
    base_deposit_raw = 0
    if isinstance(base_post_amount, int) and isinstance(base_pre_amount, int):
        base_deposit_raw = max(0, base_post_amount - base_pre_amount)

    proof = seal_migration_proof(MigrationProofSnapshot(
        proof_version=MIGRATION_PROOF_VERSION,
        proof_source=MIGRATION_PROOF_SOURCE,
        candidate_mint=base_mint,
        pool=pool,
        base_mint=base_mint,
        quote_mint=quote_mint,
        base_vault=base_vault,
        quote_vault=quote_vault,
        migration_authority=creator,
        migration_signature=signature,
        migration_slot=int(slot or 0),
        outer_instruction_index=site.outer_index,
        inner_instruction_index=site.inner_index,
        flattened_instruction_index=site.flattened_index,
        pumpfun_program_id=PUMPFUN_PROGRAM_ID,
        pumpswap_program_id=PUMPSWAP_PROGRAM_ID,
        canonical_pda_valid=True,
        pool_creation_index_arg=int(index_arg),
        vault_derivation_valid=True,
        vault_ownership_valid=True,
        quote_deposit_raw=int(quote_deposit_raw),
        quote_deposit_decimals=int(quote_decimals),
        quote_deposit_sol=format(quote_deposit_sol, "f"),
        base_deposit_raw=int(base_deposit_raw),
        base_deposit_decimals=(
            base_post.get("decimals") if isinstance(base_post.get("decimals"), int)
            else None),
        min_quote_deposit_sol=format(cfg.min_quote_deposit_sol, "f"),
        mint_suffix_consistent=base_mint.endswith("pump"),
        observed_at_utc=str(observed_at_utc or ""),
        migration_instruction_version=migration_version,
    ))
    return MigrationAdmissionDecision(
        admitted=True,
        classification=POOL_CREATION_MIGRATION_CPI,
        reason_codes=(),
        candidate_mint=base_mint,
        pool=pool,
        quote_mint=quote_mint,
        transaction_signature=signature,
        slot=slot,
        deposit_bucket=_deposit_bucket(quote_deposit_sol),
        quote_deposit_sol=format(quote_deposit_sol, "f"),
        proof=proof,
        migration_version=migration_version,
    )


class MigrationAdmissionCounters:
    """Thread-safe closed-set admission counters for observability."""

    _FIELDS = (
        "pool_creations_seen",
        "migration_proof_pass",
        "migration_v1_admitted",
        "migration_v2_admitted",
        "migration_rejected_not_proven",
        "migration_rejected_below_deposit_floor",
        "rejected_not_migration",
        "rejected_dust_deposit",
        "rejected_direct_pool",
        "rejected_canonical_mismatch",
        "rejected_transaction_failed",
        "rejected_transaction_status_fail_closed",
        "rejected_transaction_status_malformed",
        "rejected_transaction_status_unsupported",
        "rejected_transaction_status_access_error",
        "rejected_transaction_status_presence_conflict",
        "rejected_malformed",
        "admitted_true_migrations",
    )

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counts = {name: 0 for name in self._FIELDS}

    def record(self, decision: MigrationAdmissionDecision) -> None:
        with self._lock:
            self._counts["pool_creations_seen"] += 1
            if decision.admitted:
                self._counts["migration_proof_pass"] += 1
                self._counts["admitted_true_migrations"] += 1
                if decision.migration_version == MIGRATION_VERSION_V2:
                    self._counts["migration_v2_admitted"] += 1
                else:
                    self._counts["migration_v1_admitted"] += 1
                return
            reasons = set(decision.reason_codes)
            if decision.classification == POOL_CREATION_DIRECT:
                self._counts["rejected_direct_pool"] += 1
                self._counts["migration_rejected_not_proven"] += 1
            elif MIGRATION_QUOTE_DEPOSIT_BELOW_FLOOR in reasons:
                self._counts["rejected_dust_deposit"] += 1
                self._counts["migration_rejected_below_deposit_floor"] += 1
            elif CANONICAL_POOL_MISMATCH in reasons:
                self._counts["rejected_canonical_mismatch"] += 1
            elif MIGRATION_TRANSACTION_FAILED in reasons:
                self._counts["rejected_transaction_failed"] += 1
            elif reasons & TRANSACTION_STATUS_FAIL_CLOSED_REASONS:
                self._counts["rejected_transaction_status_fail_closed"] += 1
                if TRANSACTION_ERROR_MALFORMED_FAIL_CLOSED in reasons:
                    self._counts["rejected_transaction_status_malformed"] += 1
                elif TRANSACTION_ERROR_UNSUPPORTED_ENCODING in reasons:
                    self._counts["rejected_transaction_status_unsupported"] += 1
                elif TRANSACTION_ERROR_ACCESS_FAILED in reasons:
                    self._counts["rejected_transaction_status_access_error"] += 1
                elif TRANSACTION_ERROR_PRESENCE_CONFLICT in reasons:
                    self._counts["rejected_transaction_status_presence_conflict"] += 1
            elif reasons & {NOT_PUMPFUN_MIGRATION, MIGRATION_PROGRAM_PROOF_MISSING}:
                self._counts["rejected_not_migration"] += 1
                self._counts["migration_rejected_not_proven"] += 1
            else:
                self._counts["rejected_malformed"] += 1

    def snapshot(self) -> Dict[str, int]:
        with self._lock:
            return dict(self._counts)


class MigrationProofStore:
    """Restart-safe, first-wins store of sealed migration proofs.

    Persistence is an append-only JSONL file; every load re-verifies each
    record's digest, so a tampered or truncated line is dropped instead of
    trusted.  The store is independent of the rolling liquidity-event buffer:
    eviction or staleness there never removes a sealed proof here.
    """

    def __init__(self, path: Optional[Any] = None) -> None:
        self._path = Path(path) if path is not None else None
        self._lock = threading.Lock()
        self._by_mint: Dict[str, MigrationProofSnapshot] = {}
        self._persist_errors = 0
        self._load_dropped = 0
        if self._path is not None and self._path.exists():
            self._load()

    def _load(self) -> None:
        try:
            text = self._path.read_text(encoding="utf-8")
        except OSError:
            return
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
                payload["reason_codes"] = tuple(payload.get("reason_codes") or ())
                proof = MigrationProofSnapshot(**payload)
            except (ValueError, TypeError):
                self._load_dropped += 1
                continue
            valid, _ = validate_migration_proof(proof)
            if not valid:
                self._load_dropped += 1
                continue
            self._by_mint.setdefault(proof.candidate_mint, proof)

    def seal_and_store(self, proof: MigrationProofSnapshot) -> bool:
        """Store a valid sealed proof (first per mint wins). Returns stored?"""
        valid, _ = validate_migration_proof(proof)
        if not valid:
            return False
        with self._lock:
            if proof.candidate_mint in self._by_mint:
                return False
            if self._path is not None:
                try:
                    self._path.parent.mkdir(parents=True, exist_ok=True)
                    payload = (json.dumps(proof.to_dict(), sort_keys=True,
                                          separators=(",", ":")) + "\n").encode("utf-8")
                    with self._path.open("ab+") as handle:
                        # A crash may leave one incomplete final append. It is
                        # not a committed proof and must not absorb the retry.
                        end = handle.tell()
                        if end:
                            handle.seek(max(0, end - 65536))
                            tail = handle.read()
                            if not tail.endswith(b"\n"):
                                boundary = tail.rfind(b"\n")
                                if boundary < 0 and end > len(tail):
                                    raise OSError("MIGRATION_PROOF_TRAILER_INVALID")
                                handle.truncate(end - len(tail) + boundary + 1)
                        handle.seek(0, os.SEEK_END)
                        handle.write(payload)
                        handle.flush()
                        os.fsync(handle.fileno())
                except OSError:
                    self._persist_errors += 1
                    # Never publish or acknowledge a proof that is not durable.
                    # The source must hold its cursor and replay the transaction.
                    raise
            self._by_mint[proof.candidate_mint] = proof
            return True

    def get(self, mint: str) -> Optional[MigrationProofSnapshot]:
        with self._lock:
            return self._by_mint.get(str(mint))

    def all_proofs(self) -> Tuple[MigrationProofSnapshot, ...]:
        with self._lock:
            return tuple(self._by_mint.values())

    def stats(self) -> Dict[str, int]:
        with self._lock:
            return {
                "immutable_migration_proofs": len(self._by_mint),
                "proof_persist_errors": self._persist_errors,
                "proof_load_dropped": self._load_dropped,
            }


__all__ = (
    "PUMPFUN_PROGRAM_ID",
    "PUMPFUN_MIGRATE_INSTRUCTION_DISCRIMINATOR",
    "PUMPFUN_MIGRATE_V2_INSTRUCTION_DISCRIMINATOR",
    "PUMPFUN_MIGRATION_INSTRUCTION_DISCRIMINATORS",
    "MIGRATION_VERSION_V1",
    "MIGRATION_VERSION_V2",
    "MIGRATION_VERSIONS",
    "MIGRATION_PROOF_VERSION",
    "MIGRATION_PROOF_SOURCE",
    "POOL_CREATION_MIGRATION_CPI",
    "POOL_CREATION_DIRECT",
    "POOL_CREATION_CPI_UNPROVEN",
    "NOT_PUMPFUN_MIGRATION",
    "CREATE_POOL_NOT_IN_MIGRATION_CPI",
    "MIGRATION_PROGRAM_PROOF_MISSING",
    "MIGRATION_QUOTE_DEPOSIT_MISSING",
    "MIGRATION_QUOTE_DEPOSIT_BELOW_FLOOR",
    "CANONICAL_POOL_MISMATCH",
    "MIGRATION_VAULT_PROOF_INVALID",
    "MIGRATION_MINT_BINDING_INVALID",
    "MIGRATION_TRANSACTION_FAILED",
    "MIGRATION_EVENT_MALFORMED",
    "MIGRATION_QUOTE_MINT_UNSUPPORTED",
    "TRANSACTION_ERROR_MALFORMED_FAIL_CLOSED",
    "TRANSACTION_ERROR_UNSUPPORTED_ENCODING",
    "TRANSACTION_ERROR_ACCESS_FAILED",
    "TRANSACTION_ERROR_PRESENCE_CONFLICT",
    "TRANSACTION_STATUS_FAIL_CLOSED_REASONS",
    "TransactionExecutionStatus",
    "classify_transaction_execution_status",
    "MIGRATION_REJECTION_REASONS",
    "ENV_MIN_QUOTE_DEPOSIT_SOL",
    "DEFAULT_MIN_QUOTE_DEPOSIT_SOL",
    "MigrationAdmissionConfig",
    "build_migration_admission_config",
    "MigrationProofSnapshot",
    "seal_migration_proof",
    "validate_migration_proof",
    "migration_proof_matches_identity",
    "is_exact_mint_address",
    "is_supported_mint_identity",
    "candidate_migration_proof",
    "candidate_migration_is_admitted",
    "attach_candidate_migration_proof",
    "migration_cpi_ancestry_proven",
    "migration_cpi_ancestry_version",
    "MigrationAdmissionDecision",
    "evaluate_migration_admission",
    "MigrationAdmissionCounters",
    "MigrationProofStore",
)

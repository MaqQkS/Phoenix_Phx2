"""Exact PumpSwap liquidity instruction decoding and bounded integrity state.

This module owns the immutable LP-integrity decision consumed by the producer,
Discord, paper, dashboard and console.  It has no network or transport imports.
The live Yellowstone adapter is in :mod:`liquidity_verifier`.
"""

from __future__ import annotations

from collections import OrderedDict, deque
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
import struct
import threading
from typing import Any, Deque, Dict, Iterable, Mapping, Optional, Sequence, Tuple

from PHX2.stage29.pumpswap_program_constants import (
    KNOWN_QUOTE_MINT_TO_PROVIDER_PAIR_TYPE_HINT,
    PUMPSWAP_PROGRAM_ID,
)


CREATE_POOL = "CREATE_POOL"
ADD_LIQUIDITY = "ADD_LIQUIDITY"
REMOVE_LIQUIDITY = "REMOVE_LIQUIDITY"
BUY = "BUY"
SELL = "SELL"
UNKNOWN = "UNKNOWN"
LIQUIDITY_EVENT_KINDS = frozenset({
    CREATE_POOL, ADD_LIQUIDITY, REMOVE_LIQUIDITY, BUY, SELL, UNKNOWN,
})

CREATE_POOL_DISCRIMINATOR = bytes((233, 146, 209, 142, 207, 104, 64, 188))
DEPOSIT_DISCRIMINATOR = bytes((242, 35, 198, 137, 82, 225, 242, 182))
WITHDRAW_DISCRIMINATOR = bytes((183, 18, 70, 156, 148, 109, 161, 34))
BUY_DISCRIMINATOR = bytes((102, 6, 61, 18, 1, 218, 235, 234))
SELL_DISCRIMINATOR = bytes((51, 230, 133, 164, 1, 127, 131, 173))

LP_INTEGRITY_PASS = "PASS"
LP_INTEGRITY_WARN = "WARN"
LP_INTEGRITY_FAIL = "FAIL"
LP_INTEGRITY_UNKNOWN = "UNKNOWN"
LP_INTEGRITY_LABELS = frozenset({
    LP_INTEGRITY_PASS, LP_INTEGRITY_WARN, LP_INTEGRITY_FAIL, LP_INTEGRITY_UNKNOWN,
})

NONCANONICAL_POOL_SELECTED = "NONCANONICAL_POOL_SELECTED"
CANONICAL_POOL_UNPROVEN = "CANONICAL_POOL_UNPROVEN"
WRONG_MINT_PAIR = "WRONG_MINT_PAIR"
INVALID_POOL_AUTHORITY = "INVALID_POOL_AUTHORITY"
INVALID_VAULT_OWNERSHIP = "INVALID_VAULT_OWNERSHIP"
IMPOSSIBLE_RESERVE_RECONCILIATION = "IMPOSSIBLE_RESERVE_RECONCILIATION"
LIQUIDITY_EVENT_MALFORMED = "LIQUIDITY_EVENT_MALFORMED"
UNEXPLAINED_LIQUIDITY_REMOVAL = "UNEXPLAINED_LIQUIDITY_REMOVAL"
PROVIDER_POOL_MISMATCH = "PROVIDER_POOL_MISMATCH"
SECONDARY_POOL_MANIPULATION_PROVEN = "SECONDARY_POOL_MANIPULATION_PROVEN"
VERIFIER_EVIDENCE_STALE = "VERIFIER_EVIDENCE_STALE"
VERIFIER_EVIDENCE_INVALID = "VERIFIER_EVIDENCE_INVALID"
MULTIPLE_ADDS_NEAR_MIGRATION = "MULTIPLE_ADDS_NEAR_MIGRATION"
LOW_SLOT_DISTANCE_BETWEEN_ADDS = "LOW_SLOT_DISTANCE_BETWEEN_ADDS"
LOW_TX_DISTANCE_BETWEEN_ADDS = "LOW_TX_DISTANCE_BETWEEN_ADDS"
SAME_SIGNER_MULTIPLE_ADDS = "SAME_SIGNER_MULTIPLE_ADDS"
SAME_FEE_PAYER_MULTIPLE_ADDS = "SAME_FEE_PAYER_MULTIPLE_ADDS"
SAME_AUTHORITY_MULTIPLE_ADDS = "SAME_AUTHORITY_MULTIPLE_ADDS"
COMMON_FUNDER_SUSPECTED = "COMMON_FUNDER_SUSPECTED"
SECONDARY_POOL_OBSERVED = "SECONDARY_POOL_OBSERVED"
LIQUIDITY_VERIFICATION_INCOMPLETE = "LIQUIDITY_VERIFICATION_INCOMPLETE"
LP_INTEGRITY_FAIL_REASON = "LP_INTEGRITY_FAIL"
LP_INTEGRITY_UNKNOWN_REASON = "LP_INTEGRITY_UNKNOWN"
LP_PROOF_MISSING = "LP_INTEGRITY_PROOF_MISSING"
LP_PROOF_INCONSISTENT = "LP_INTEGRITY_PROOF_INCONSISTENT"

LP_SNAPSHOT_VERSION = "PHX2_LP_INTEGRITY_V1"
LP_SOURCE = "LIQUIDITY_VERIFIER_STREAM"

# Pool-creation execution context for CPI-aware authority semantics.
CREATION_CONTEXT_TOP_LEVEL = "TOP_LEVEL"
CREATION_CONTEXT_MIGRATION_CPI = "MIGRATION_CPI"
CREATION_CONTEXT_CPI = "CPI"

CANONICAL_SOURCE_STREAM = "PUMPSWAP_CREATE_POOL_PDA_VAULT_AND_MIGRATION_SIGNATURE"
CANONICAL_SOURCE_SEALED_PROOF = "SEALED_MIGRATION_PROOF"
WSOL_MINT = "So11111111111111111111111111111111111111112"
SYSTEM_PROGRAM_ID = "11111111111111111111111111111111"
TOKEN_PROGRAM_ID = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
TOKEN_2022_PROGRAM_ID = "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"
ASSOCIATED_TOKEN_PROGRAM_ID = "ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL"
TOKEN_PROGRAM_IDS = frozenset((TOKEN_PROGRAM_ID, TOKEN_2022_PROGRAM_ID))

_BASE58_ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
_P = 2**255 - 19
_D = (-121665 * pow(121666, _P - 2, _P)) % _P
_SQRT_M1 = pow(2, (_P - 1) // 4, _P)


def b58decode(value: str) -> bytes:
    if not isinstance(value, str) or not value:
        raise ValueError("base58_invalid")
    number = 0
    for char in value:
        digit = _BASE58_ALPHABET.find(char)
        if digit < 0:
            raise ValueError("base58_invalid")
        number = number * 58 + digit
    zeros = len(value) - len(value.lstrip("1"))
    body = number.to_bytes((number.bit_length() + 7) // 8, "big") if number else b""
    raw = b"\x00" * zeros + body
    if len(raw) != 32:
        raise ValueError("pubkey_length_invalid")
    return raw


def b58encode(raw: bytes) -> str:
    if not isinstance(raw, bytes) or len(raw) != 32:
        raise ValueError("pubkey_length_invalid")
    zeros = len(raw) - len(raw.lstrip(b"\x00"))
    number = int.from_bytes(raw, "big")
    chars = []
    while number:
        number, rem = divmod(number, 58)
        chars.append(_BASE58_ALPHABET[rem])
    return "1" * zeros + "".join(reversed(chars))


def _on_ed25519_curve(encoded: bytes) -> bool:
    if len(encoded) != 32:
        return False
    y = int.from_bytes(encoded, "little") & ((1 << 255) - 1)
    sign = encoded[31] >> 7
    if y >= _P:
        return False
    y2 = y * y % _P
    denominator = (_D * y2 + 1) % _P
    if denominator == 0:
        return False
    x2 = (y2 - 1) * pow(denominator, _P - 2, _P) % _P
    x = pow(x2, (_P + 3) // 8, _P)
    if (x * x - x2) % _P != 0:
        x = x * _SQRT_M1 % _P
    if (x * x - x2) % _P != 0:
        return False
    return not (x == 0 and sign == 1)


def create_program_address(seeds: Sequence[bytes], program_id: str) -> str:
    if len(seeds) > 16 or any(len(seed) > 32 for seed in seeds):
        raise ValueError("pda_seed_invalid")
    digest = hashlib.sha256(
        b"".join(seeds) + b58decode(program_id) + b"ProgramDerivedAddress").digest()
    if _on_ed25519_curve(digest):
        raise ValueError("pda_on_curve")
    return b58encode(digest)


def find_program_address(seeds: Sequence[bytes], program_id: str) -> Tuple[str, int]:
    for bump in range(255, -1, -1):
        try:
            return create_program_address(tuple(seeds) + (bytes((bump,)),), program_id), bump
        except ValueError as exc:
            if str(exc) != "pda_on_curve":
                raise
    raise ValueError("pda_bump_unavailable")


def derive_pool_address(*, index: int, creator: str, base_mint: str,
                        quote_mint: str) -> str:
    if isinstance(index, bool) or not isinstance(index, int) or not (0 <= index <= 65535):
        raise ValueError("pool_index_invalid")
    return find_program_address((
        b"pool",
        struct.pack("<H", index),
        b58decode(creator),
        b58decode(base_mint),
        b58decode(quote_mint),
    ), PUMPSWAP_PROGRAM_ID)[0]


def derive_associated_token_address(*, owner: str, token_program: str,
                                    mint: str, associated_program: str) -> str:
    return find_program_address((
        b58decode(owner), b58decode(token_program), b58decode(mint),
    ), associated_program)[0]


@dataclass(frozen=True)
class LiquidityEvent:
    kind: str
    program_id: str
    discriminator_hex: str
    pool: Optional[str]
    base_mint: Optional[str]
    quote_mint: Optional[str]
    pair: Optional[str]
    base_vault: Optional[str]
    quote_vault: Optional[str]
    pool_authority: Optional[str]
    signer: Optional[str]
    fee_payer: Optional[str]
    authority: Optional[str]
    transaction_signature: str
    event_index: int
    slot: int
    timestamp_utc: str
    base_amount: Optional[int]
    quote_amount: Optional[int]
    base_reserve_delta: Optional[int]
    quote_reserve_delta: Optional[int]
    pool_pda_valid: Optional[bool]
    mint_pair_valid: Optional[bool]
    vault_derivation_valid: Optional[bool]
    vault_ownership_valid: Optional[bool]
    pool_authority_valid: Optional[bool]
    canonical_semantics_valid: bool
    malformed_reasons: Tuple[str, ...] = ()
    creation_context: Optional[str] = None
    migration_cpi_proven: bool = False

    def __post_init__(self) -> None:
        if self.kind not in LIQUIDITY_EVENT_KINDS:
            raise ValueError("liquidity_kind_invalid")
        for name in ("event_index", "slot"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{name}_invalid")

    def to_dict(self) -> Dict[str, Any]:
        value = asdict(self)
        value["malformed_reasons"] = list(self.malformed_reasons)
        return value


def _account(accounts: Sequence[str], index: int) -> Optional[str]:
    try:
        value = accounts[index]
        return value if isinstance(value, str) and value else None
    except (IndexError, TypeError):
        return None


def _amount_from_delta(delta: Optional[int], *, positive: bool) -> Optional[int]:
    if delta is None:
        return None
    if positive and delta <= 0:
        return None
    if not positive and delta >= 0:
        return None
    return abs(delta)


def decode_pumpswap_instruction(
    *,
    program_id: str,
    data: bytes,
    accounts: Sequence[str],
    signer_keys: Iterable[str],
    fee_payer: Optional[str],
    transaction_signature: str,
    event_index: int,
    slot: int,
    timestamp_utc: str,
    vault_owner_by_address: Optional[Mapping[str, str]] = None,
    reserve_delta_by_address: Optional[Mapping[str, int]] = None,
    creation_context: Optional[str] = None,
    migration_cpi_proven: bool = False,
) -> LiquidityEvent:
    """Decode one exact instruction.  Unknown and malformed inputs fail closed.

    ``creation_context`` / ``migration_cpi_proven`` describe how a create_pool
    executed (top-level vs CPI, and whether the CPI ancestry deterministically
    proved the official pump.fun ``migrate`` frame).  Authority semantics are
    context-aware: a proven migration CPI derives authority validity from the
    canonical PDA + vault derivations + vault ownership (invoke_signed PDA
    creators are never transaction-header signers), while direct creations
    keep the header-signer requirement unchanged.
    """

    signers = set(signer_keys or ())
    owners = dict(vault_owner_by_address or {})
    deltas = dict(reserve_delta_by_address or {})
    reasons = []
    kind = UNKNOWN
    pool = base = quote = base_vault = quote_vault = authority = None
    pool_pda_valid = mint_pair_valid = vault_derivation_valid = None
    vault_ownership_valid = pool_authority_valid = None
    fixed_accounts_valid = False
    base_amount = quote_amount = base_delta = quote_delta = None
    discriminator = data[:8] if isinstance(data, bytes) and len(data) >= 8 else b""
    if program_id != PUMPSWAP_PROGRAM_ID:
        reasons.append("PROGRAM_ID_MISMATCH")
    elif discriminator == CREATE_POOL_DISCRIMINATOR:
        kind = CREATE_POOL
        if len(data) < 26 or len(accounts) < 18:
            reasons.append("CREATE_POOL_LAYOUT_INVALID")
        else:
            index, base_arg, quote_arg = struct.unpack_from("<HQQ", data, 8)
            pool, authority, base, quote = (_account(accounts, i) for i in (0, 2, 3, 4))
            base_vault, quote_vault = _account(accounts, 9), _account(accounts, 10)
            base_token_program, quote_token_program = _account(accounts, 13), _account(accounts, 14)
            associated_program = _account(accounts, 15)
            fixed_accounts_valid = bool(
                _account(accounts, 11) == SYSTEM_PROGRAM_ID
                and _account(accounts, 12) == TOKEN_2022_PROGRAM_ID
                and base_token_program in TOKEN_PROGRAM_IDS
                and quote_token_program in TOKEN_PROGRAM_IDS
                and associated_program == ASSOCIATED_TOKEN_PROGRAM_ID
                and _account(accounts, 17) == PUMPSWAP_PROGRAM_ID)
            if not fixed_accounts_valid:
                reasons.append("CREATE_POOL_FIXED_ACCOUNTS_INVALID")
            seed_base, seed_quote = base, quote
            mint_pair_valid = bool(
                base and quote and base != quote
                and ((base in KNOWN_QUOTE_MINT_TO_PROVIDER_PAIR_TYPE_HINT)
                     ^ (quote in KNOWN_QUOTE_MINT_TO_PROVIDER_PAIR_TYPE_HINT)))
            if mint_pair_valid and base in KNOWN_QUOTE_MINT_TO_PROVIDER_PAIR_TYPE_HINT:
                base, quote = quote, base
                base_vault, quote_vault = quote_vault, base_vault
                base_token_program, quote_token_program = quote_token_program, base_token_program
            try:
                pool_pda_valid = bool(
                    pool and authority and base and quote
                    and pool == derive_pool_address(
                        index=index, creator=authority,
                        base_mint=str(seed_base), quote_mint=str(seed_quote)))
            except ValueError:
                pool_pda_valid = False
            try:
                vault_derivation_valid = bool(
                    pool and base and quote and base_vault and quote_vault
                    and base_token_program and quote_token_program and associated_program
                    and base_vault == derive_associated_token_address(
                        owner=pool, token_program=base_token_program, mint=base,
                        associated_program=associated_program)
                    and quote_vault == derive_associated_token_address(
                        owner=pool, token_program=quote_token_program, mint=quote,
                        associated_program=associated_program))
            except ValueError:
                vault_derivation_valid = False
            vault_ownership_valid = bool(
                pool and base_vault and quote_vault
                and owners.get(base_vault) == pool and owners.get(quote_vault) == pool)
            # Context-aware authority semantics.  A deterministically proven
            # pump.fun migration CPI creates the pool via invoke_signed, so the
            # creator PDA can never be a transaction-header signer; its
            # authority validity derives from the migration program proof plus
            # the canonical PDA and exact vault derivations/ownership instead.
            # Every other creation context keeps the header-signer requirement.
            migration_authority_proven = bool(
                migration_cpi_proven
                and creation_context == CREATION_CONTEXT_MIGRATION_CPI
                and pool_pda_valid is True
                and vault_derivation_valid is True)
            pool_authority_valid = bool(vault_ownership_valid and (
                authority in signers or migration_authority_proven))
            base_delta, quote_delta = deltas.get(base_vault), deltas.get(quote_vault)
            base_amount = _amount_from_delta(base_delta, positive=True)
            quote_amount = _amount_from_delta(quote_delta, positive=True)
            if base_amount is None or quote_amount is None:
                reasons.append("CREATE_POOL_RESERVE_DELTA_UNPROVEN")
            # Args are maximum/input semantics.  Preserve them only as a fallback
            # when exact reserve deltas agree in direction.
            if base_amount is None and base_arg > 0:
                base_amount = int(base_arg)
            if quote_amount is None and quote_arg > 0:
                quote_amount = int(quote_arg)
    elif discriminator in (DEPOSIT_DISCRIMINATOR, WITHDRAW_DISCRIMINATOR):
        kind = ADD_LIQUIDITY if discriminator == DEPOSIT_DISCRIMINATOR else REMOVE_LIQUIDITY
        if len(data) < 32 or len(accounts) < 15:
            reasons.append("LIQUIDITY_LAYOUT_INVALID")
        else:
            pool, authority, base, quote = (_account(accounts, i) for i in (0, 2, 3, 4))
            base_vault, quote_vault = _account(accounts, 9), _account(accounts, 10)
            token_program = _account(accounts, 11)
            fixed_accounts_valid = bool(
                token_program == TOKEN_PROGRAM_ID
                and _account(accounts, 12) == TOKEN_2022_PROGRAM_ID
                and _account(accounts, 14) == PUMPSWAP_PROGRAM_ID)
            if not fixed_accounts_valid:
                reasons.append("LIQUIDITY_FIXED_ACCOUNTS_INVALID")
            mint_pair_valid = bool(
                base and quote and base != quote
                and ((base in KNOWN_QUOTE_MINT_TO_PROVIDER_PAIR_TYPE_HINT)
                     ^ (quote in KNOWN_QUOTE_MINT_TO_PROVIDER_PAIR_TYPE_HINT)))
            if mint_pair_valid and base in KNOWN_QUOTE_MINT_TO_PROVIDER_PAIR_TYPE_HINT:
                base, quote = quote, base
                base_vault, quote_vault = quote_vault, base_vault
            vault_ownership_valid = bool(
                pool and base_vault and quote_vault
                and owners.get(base_vault) == pool and owners.get(quote_vault) == pool)
            pool_authority_valid = bool(vault_ownership_valid and authority in signers)
            base_delta, quote_delta = deltas.get(base_vault), deltas.get(quote_vault)
            positive = kind == ADD_LIQUIDITY
            base_amount = _amount_from_delta(base_delta, positive=positive)
            quote_amount = _amount_from_delta(quote_delta, positive=positive)
            if base_amount is None or quote_amount is None:
                reasons.append("LIQUIDITY_RESERVE_DELTA_UNPROVEN")
            # No create args are available here, so pool PDA and vault PDA cannot
            # be rederived without the original index/creator. Ownership is still exact.
            pool_pda_valid = None
            vault_derivation_valid = None
    elif discriminator in (BUY_DISCRIMINATOR, SELL_DISCRIMINATOR):
        kind = BUY if discriminator == BUY_DISCRIMINATOR else SELL
        if len(accounts) >= 9:
            pool, authority, base, quote = (_account(accounts, i) for i in (0, 1, 3, 4))
            base_vault, quote_vault = _account(accounts, 7), _account(accounts, 8)
            mint_pair_valid = bool(
                base and quote and ((base in KNOWN_QUOTE_MINT_TO_PROVIDER_PAIR_TYPE_HINT)
                                    ^ (quote in KNOWN_QUOTE_MINT_TO_PROVIDER_PAIR_TYPE_HINT)))
        else:
            reasons.append("SWAP_LAYOUT_INVALID")
    else:
        reasons.append("UNKNOWN_INSTRUCTION_DISCRIMINATOR")

    signer = authority if authority in signers else None
    if kind in (CREATE_POOL, ADD_LIQUIDITY, REMOVE_LIQUIDITY):
        if mint_pair_valid is False:
            reasons.append(WRONG_MINT_PAIR)
        if pool_pda_valid is False:
            reasons.append(NONCANONICAL_POOL_SELECTED)
        if vault_derivation_valid is False:
            reasons.append(INVALID_VAULT_OWNERSHIP)
        if vault_ownership_valid is False:
            reasons.append(INVALID_VAULT_OWNERSHIP)
        if pool_authority_valid is False:
            reasons.append(INVALID_POOL_AUTHORITY)
    canonical = bool(
        kind == CREATE_POOL and program_id == PUMPSWAP_PROGRAM_ID
        and fixed_accounts_valid
        and pool_pda_valid is True and mint_pair_valid is True
        and vault_derivation_valid is True and vault_ownership_valid is True
        and pool_authority_valid is True
        and base_amount is not None and quote_amount is not None
        and transaction_signature)
    return LiquidityEvent(
        kind=kind,
        program_id=program_id,
        discriminator_hex=discriminator.hex(),
        pool=pool,
        base_mint=base,
        quote_mint=quote,
        pair=(f"{base}/{quote}" if base and quote else None),
        base_vault=base_vault,
        quote_vault=quote_vault,
        pool_authority=pool,
        signer=signer,
        fee_payer=fee_payer,
        authority=authority,
        transaction_signature=transaction_signature,
        event_index=event_index,
        slot=slot,
        timestamp_utc=timestamp_utc,
        base_amount=base_amount,
        quote_amount=quote_amount,
        base_reserve_delta=base_delta,
        quote_reserve_delta=quote_delta,
        pool_pda_valid=pool_pda_valid,
        mint_pair_valid=mint_pair_valid,
        vault_derivation_valid=vault_derivation_valid,
        vault_ownership_valid=vault_ownership_valid,
        pool_authority_valid=pool_authority_valid,
        canonical_semantics_valid=canonical,
        malformed_reasons=tuple(dict.fromkeys(reasons)),
        creation_context=creation_context,
        migration_cpi_proven=bool(migration_cpi_proven),
    )


@dataclass(frozen=True)
class MigrationLiquidityIdentity:
    candidate_mint: str
    pool: str
    quote_mint: str
    migration_signature: str
    migration_slot: int
    migration_timestamp_utc: str
    provider_pool: Optional[str] = None


@dataclass(frozen=True)
class LiquidityIntegrityConfig:
    max_buffer_events: int = 4096
    max_retention_slots: int = 20_000
    max_retention_seconds: int = 3600
    near_slot_window: int = 64
    near_time_window_seconds: int = 120
    evidence_max_age_seconds: int = 300

    def __post_init__(self) -> None:
        for name in (
            "max_buffer_events", "max_retention_slots", "max_retention_seconds",
            "near_slot_window", "near_time_window_seconds", "evidence_max_age_seconds",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{name}_invalid")


@dataclass(frozen=True)
class LpIntegritySnapshot:
    schema_version: str
    source: str
    candidate_mint: str
    canonical_pool: Optional[str]
    canonical_pool_proven: bool
    canonical_pool_source: Optional[str]
    canonical_migration_liquidity_signature: Optional[str]
    canonical_migration_liquidity_event_index: Optional[int]
    canonical_migration_liquidity_slot: Optional[int]
    canonical_migration_liquidity_timestamp: Optional[str]
    canonical_liquidity_base_amount: Optional[int]
    canonical_liquidity_quote_amount: Optional[int]
    nearby_prior_add_count: int
    nearby_following_add_count: int
    nearest_prior_add_signature: Optional[str]
    nearest_prior_add_event_index: Optional[int]
    nearest_prior_add_slot: Optional[int]
    nearest_prior_add_timestamp: Optional[str]
    nearest_prior_add_base_amount: Optional[int]
    nearest_prior_add_quote_amount: Optional[int]
    nearest_following_add_signature: Optional[str]
    nearest_following_add_slot: Optional[int]
    nearest_following_add_timestamp: Optional[str]
    slots_between_adds: Optional[int]
    seconds_between_adds: Optional[str]
    intervening_transaction_count: Optional[int]
    same_pool: Optional[bool]
    same_signer: Optional[bool]
    same_fee_payer: Optional[bool]
    same_authority: Optional[bool]
    common_funder_evidence: str
    secondary_pool_count: int
    secondary_pool_addresses: Tuple[str, ...]
    liquidity_removed_after_migration: bool
    liquidity_removed_base_amount: int
    liquidity_removed_quote_amount: int
    reserve_reconciliation_status: str
    provider_pool_matches_canonical: Optional[bool]
    evidence_completeness: str
    evidence_observed_at_utc: str
    evidence_freshness: str
    lp_integrity: str
    lp_integrity_reasons: Tuple[str, ...]
    eligible: bool
    hard_block: bool
    evidence_event_count: int
    sealed_migration_proof_digest: Optional[str] = None
    proof_digest: str = ""

    def to_dict(self) -> Dict[str, Any]:
        value = asdict(self)
        value["secondary_pool_addresses"] = list(self.secondary_pool_addresses)
        value["lp_integrity_reasons"] = list(self.lp_integrity_reasons)
        return value


def _lp_digest(snapshot: LpIntegritySnapshot) -> str:
    payload = snapshot.to_dict()
    payload.pop("proof_digest", None)
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def seal_lp_snapshot(snapshot: LpIntegritySnapshot) -> LpIntegritySnapshot:
    return replace(snapshot, proof_digest=_lp_digest(replace(snapshot, proof_digest="")))


def _epoch(iso: Optional[str]) -> Optional[float]:
    try:
        if not isinstance(iso, str) or not iso:
            return None
        return datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp()
    except (ValueError, TypeError):
        return None


class LiquidityIntegrityIndex:
    """Bounded, deterministic pre/post-migration liquidity event buffer."""

    def __init__(self, config: Optional[LiquidityIntegrityConfig] = None) -> None:
        self.config = config or LiquidityIntegrityConfig()
        self._lock = threading.Lock()
        self._events: Deque[LiquidityEvent] = deque()
        self._dedupe: "OrderedDict[Tuple[str, int], None]" = OrderedDict()
        self._recorded = 0
        self._duplicates = 0
        self._evicted = 0
        self._identities: Dict[str, MigrationLiquidityIdentity] = {}
        self._proofs: Dict[str, Any] = {}

    def register_migration(self, identity: MigrationLiquidityIdentity) -> None:
        if not isinstance(identity, MigrationLiquidityIdentity):
            raise ValueError("migration_identity_required")
        with self._lock:
            existing = self._identities.get(identity.candidate_mint)
            if existing is not None and existing != identity:
                # The first exact primary-stream identity is immutable.
                return
            self._identities[identity.candidate_mint] = identity

    def register_migration_proof(self, proof: Any) -> bool:
        """Bind a sealed migration proof (first per mint wins) and derive the
        matching identity when none exists yet, so a restart restores both."""
        from PHX2.free_tier_producer.migration_admission import validate_migration_proof
        valid, _ = validate_migration_proof(proof)
        if not valid:
            return False
        with self._lock:
            if proof.candidate_mint in self._proofs:
                return False
            self._proofs[proof.candidate_mint] = proof
        self.register_migration(MigrationLiquidityIdentity(
            candidate_mint=proof.candidate_mint,
            pool=proof.pool,
            quote_mint=proof.quote_mint,
            migration_signature=proof.migration_signature,
            migration_slot=int(proof.migration_slot),
            migration_timestamp_utc=str(proof.observed_at_utc),
            provider_pool=proof.pool,
        ))
        return True

    def migration_proof_for(self, mint: str) -> Optional[Any]:
        with self._lock:
            return self._proofs.get(str(mint))

    def identity_for(self, mint: str) -> Optional[MigrationLiquidityIdentity]:
        with self._lock:
            return self._identities.get(str(mint))

    def record(self, event: LiquidityEvent) -> bool:
        if not isinstance(event, LiquidityEvent):
            return False
        key = (event.transaction_signature, event.event_index)
        with self._lock:
            if key in self._dedupe:
                self._duplicates += 1
                return False
            self._dedupe[key] = None
            self._events.append(event)
            self._recorded += 1
            self._evict_locked(latest=event)
            return True

    def _evict_locked(self, *, latest: LiquidityEvent) -> None:
        latest_epoch = _epoch(latest.timestamp_utc)
        while self._events:
            first = self._events[0]
            first_epoch = _epoch(first.timestamp_utc)
            too_many = len(self._events) > self.config.max_buffer_events
            too_old_slot = latest.slot - first.slot > self.config.max_retention_slots
            too_old_time = bool(
                latest_epoch is not None and first_epoch is not None
                and latest_epoch - first_epoch > self.config.max_retention_seconds)
            if not (too_many or too_old_slot or too_old_time):
                break
            removed = self._events.popleft()
            self._dedupe.pop((removed.transaction_signature, removed.event_index), None)
            self._evicted += 1

    def events_for(self, identity: MigrationLiquidityIdentity) -> Tuple[LiquidityEvent, ...]:
        with self._lock:
            events = tuple(self._events)
        relevant = []
        for event in events:
            if (event.base_mint == identity.candidate_mint
                    or event.pool == identity.pool
                    or (event.base_mint == identity.quote_mint
                        and event.quote_mint == identity.candidate_mint)):
                relevant.append(event)
        return tuple(sorted(relevant, key=lambda event: (
            event.slot, event.transaction_signature, event.event_index)))

    def snapshot(self, identity: MigrationLiquidityIdentity, *, now_utc: str) -> LpIntegritySnapshot:
        return classify_liquidity_integrity(
            identity, self.events_for(identity), config=self.config, now_utc=now_utc,
            sealed_proof=self.migration_proof_for(identity.candidate_mint))

    def stats(self) -> Dict[str, int]:
        with self._lock:
            return {
                "verifier_buffer_events": len(self._events),
                "verifier_events_recorded": self._recorded,
                "verifier_duplicates": self._duplicates,
                "verifier_events_evicted": self._evicted,
                "verifier_candidates": len(self._identities),
                "verifier_sealed_migration_proofs": len(self._proofs),
            }


def classify_liquidity_integrity(
    identity: MigrationLiquidityIdentity,
    events: Sequence[LiquidityEvent],
    *,
    config: Optional[LiquidityIntegrityConfig] = None,
    now_utc: str,
    sealed_proof: Any = None,
) -> LpIntegritySnapshot:
    cfg = config or LiquidityIntegrityConfig()
    # Historical proof vs ongoing monitoring: a valid sealed migration proof
    # keeps the canonical pool proven even after the rolling buffer evicts the
    # one-shot create event or no new liquidity event arrives for a while.
    # Contradictory LIVE evidence (removals, impossible reconciliation,
    # secondary-pool manipulation, provider mismatch) still blocks below.
    proof_backed = False
    if sealed_proof is not None:
        from PHX2.free_tier_producer.migration_admission import (
            migration_proof_matches_identity,
        )
        proof_backed = migration_proof_matches_identity(sealed_proof, identity)
    ordered = tuple(sorted(events, key=lambda event: (
        event.slot, event.transaction_signature, event.event_index)))
    canonical_matches = [
        event for event in ordered
        if event.kind == CREATE_POOL
        and event.pool == identity.pool
        and event.base_mint == identity.candidate_mint
        and event.quote_mint == identity.quote_mint
        and event.transaction_signature == identity.migration_signature
        and event.canonical_semantics_valid
    ]
    canonical = canonical_matches[0] if len(canonical_matches) == 1 else None
    adds = [event for event in ordered if event.kind == ADD_LIQUIDITY]
    prior = [event for event in adds if event.slot <= identity.migration_slot]
    following = [event for event in adds if event.slot > identity.migration_slot]
    migration_epoch = _epoch(identity.migration_timestamp_utc)

    def _near_migration(event: LiquidityEvent) -> bool:
        if abs(identity.migration_slot - event.slot) > cfg.near_slot_window:
            return False
        event_epoch = _epoch(event.timestamp_utc)
        if migration_epoch is None or event_epoch is None:
            return True
        return abs(migration_epoch - event_epoch) <= cfg.near_time_window_seconds

    prior_near = [event for event in prior if _near_migration(event)]
    following_near = [event for event in following if _near_migration(event)]
    nearest_prior = prior_near[-1] if prior_near else None
    nearest_following = following_near[0] if following_near else None
    nearest = nearest_prior or nearest_following
    secondary = sorted({
        event.pool for event in ordered
        if event.pool and event.pool != identity.pool
        and event.base_mint == identity.candidate_mint
    })
    removals = [
        event for event in ordered
        if event.kind == REMOVE_LIQUIDITY and event.slot >= identity.migration_slot
    ]
    removed_base = sum(event.base_amount or 0 for event in removals)
    removed_quote = sum(event.quote_amount or 0 for event in removals)
    malformed = [
        event for event in ordered
        if event.kind in (CREATE_POOL, ADD_LIQUIDITY, REMOVE_LIQUIDITY)
        and event.malformed_reasons
        and (event.pool == identity.pool or event.base_mint == identity.candidate_mint)
    ]
    reconciliation_fail = any(
        (event.kind == ADD_LIQUIDITY and (
            event.base_reserve_delta is not None and event.base_reserve_delta <= 0
            or event.quote_reserve_delta is not None and event.quote_reserve_delta <= 0))
        or (event.kind == REMOVE_LIQUIDITY and (
            event.base_reserve_delta is not None and event.base_reserve_delta >= 0
            or event.quote_reserve_delta is not None and event.quote_reserve_delta >= 0))
        for event in ordered
    )
    reserve_status = "FAIL" if reconciliation_fail else (
        "PASS" if canonical is not None else "UNKNOWN")
    provider_match = (
        None if not identity.provider_pool else identity.provider_pool == identity.pool)
    now_epoch = _epoch(now_utc)
    evidence_epoch = max((_epoch(event.timestamp_utc) or 0 for event in ordered), default=0)
    age = None if now_epoch is None or evidence_epoch <= 0 else Decimal(str(now_epoch - evidence_epoch))
    stale = age is None or age < 0 or age > Decimal(cfg.evidence_max_age_seconds)

    reasons = []
    fail_reasons = []
    warn_reasons = []
    if canonical is None and not proof_backed:
        reasons.append(CANONICAL_POOL_UNPROVEN)
    if stale and not proof_backed:
        # Without a sealed proof, silence stays fail-closed exactly as before.
        # With one, a stale LACK of new events never invalidates the original
        # migration proof; evidence_freshness still reports the true age.
        reasons.append(VERIFIER_EVIDENCE_STALE)
    if any(event.mint_pair_valid is False for event in malformed):
        fail_reasons.append(WRONG_MINT_PAIR)
    if any(event.pool_authority_valid is False for event in malformed):
        fail_reasons.append(INVALID_POOL_AUTHORITY)
    if any(event.vault_ownership_valid is False or event.vault_derivation_valid is False
           for event in malformed):
        fail_reasons.append(INVALID_VAULT_OWNERSHIP)
    if malformed and not fail_reasons:
        fail_reasons.append(LIQUIDITY_EVENT_MALFORMED)
    if reconciliation_fail:
        fail_reasons.append(IMPOSSIBLE_RESERVE_RECONCILIATION)
    if removals:
        fail_reasons.append(UNEXPLAINED_LIQUIDITY_REMOVAL)
    if provider_match is False:
        fail_reasons.extend((PROVIDER_POOL_MISMATCH, NONCANONICAL_POOL_SELECTED))
    if secondary:
        warn_reasons.append(SECONDARY_POOL_OBSERVED)
        secondary_events = [event for event in ordered if event.pool in secondary]
        canonical_identity = canonical or nearest
        strong_identity = bool(canonical_identity and any(
            (event.signer and event.signer == canonical_identity.signer)
            or (event.fee_payer and event.fee_payer == canonical_identity.fee_payer)
            or (event.authority and event.authority == canonical_identity.authority)
            for event in secondary_events
        ))
        if strong_identity and any(event.kind in (ADD_LIQUIDITY, REMOVE_LIQUIDITY)
                                   for event in secondary_events):
            fail_reasons.append(SECONDARY_POOL_MANIPULATION_PROVEN)
    if prior_near or following_near:
        warn_reasons.append(MULTIPLE_ADDS_NEAR_MIGRATION)
        warn_reasons.append(LOW_SLOT_DISTANCE_BETWEEN_ADDS)
    if nearest and canonical:
        if nearest.signer and nearest.signer == canonical.signer:
            warn_reasons.append(SAME_SIGNER_MULTIPLE_ADDS)
        if nearest.fee_payer and nearest.fee_payer == canonical.fee_payer:
            warn_reasons.append(SAME_FEE_PAYER_MULTIPLE_ADDS)
        if nearest.authority and nearest.authority == canonical.authority:
            warn_reasons.append(SAME_AUTHORITY_MULTIPLE_ADDS)
    if canonical is None or not ordered:
        warn_reasons.append(LIQUIDITY_VERIFICATION_INCOMPLETE)

    if fail_reasons:
        label, eligible, hard_block = LP_INTEGRITY_FAIL, False, True
        reasons = fail_reasons + reasons + warn_reasons
    elif reasons:
        label, eligible, hard_block = LP_INTEGRITY_UNKNOWN, False, True
        reasons = reasons + warn_reasons
    elif warn_reasons:
        label, eligible, hard_block = LP_INTEGRITY_WARN, True, False
        reasons = warn_reasons
    else:
        label, eligible, hard_block = LP_INTEGRITY_PASS, True, False
        reasons = []

    slot_distance = None
    time_distance = None
    tx_between = None
    if canonical is not None and nearest is not None:
        slot_distance = abs(canonical.slot - nearest.slot)
        c_epoch, n_epoch = _epoch(canonical.timestamp_utc), _epoch(nearest.timestamp_utc)
        if c_epoch is not None and n_epoch is not None:
            time_distance = format(Decimal(str(abs(c_epoch - n_epoch))), "f")
        signatures_between = {
            event.transaction_signature for event in ordered
            if min(canonical.slot, nearest.slot) < event.slot < max(canonical.slot, nearest.slot)
        }
        tx_between = len(signatures_between)
        if tx_between <= 1:
            reasons.append(LOW_TX_DISTANCE_BETWEEN_ADDS)

    if canonical is not None:
        canonical_source: Optional[str] = CANONICAL_SOURCE_STREAM
        canonical_signature = canonical.transaction_signature
        canonical_event_index: Optional[int] = canonical.event_index
        canonical_slot: Optional[int] = canonical.slot
        canonical_timestamp: Optional[str] = canonical.timestamp_utc
        canonical_base_amount: Optional[int] = canonical.base_amount
        canonical_quote_amount: Optional[int] = canonical.quote_amount
    elif proof_backed:
        canonical_source = CANONICAL_SOURCE_SEALED_PROOF
        canonical_signature = sealed_proof.migration_signature
        canonical_event_index = int(sealed_proof.flattened_instruction_index)
        canonical_slot = int(sealed_proof.migration_slot)
        canonical_timestamp = str(sealed_proof.observed_at_utc)
        canonical_base_amount = int(sealed_proof.base_deposit_raw)
        canonical_quote_amount = int(sealed_proof.quote_deposit_raw)
    else:
        canonical_source = None
        canonical_signature = None
        canonical_event_index = None
        canonical_slot = None
        canonical_timestamp = None
        canonical_base_amount = None
        canonical_quote_amount = None
    snapshot = LpIntegritySnapshot(
        schema_version=LP_SNAPSHOT_VERSION,
        source=LP_SOURCE,
        candidate_mint=identity.candidate_mint,
        canonical_pool=canonical.pool if canonical else identity.pool,
        canonical_pool_proven=bool(canonical is not None or proof_backed),
        canonical_pool_source=canonical_source,
        canonical_migration_liquidity_signature=canonical_signature,
        canonical_migration_liquidity_event_index=canonical_event_index,
        canonical_migration_liquidity_slot=canonical_slot,
        canonical_migration_liquidity_timestamp=canonical_timestamp,
        canonical_liquidity_base_amount=canonical_base_amount,
        canonical_liquidity_quote_amount=canonical_quote_amount,
        nearby_prior_add_count=len(prior_near),
        nearby_following_add_count=len(following_near),
        nearest_prior_add_signature=(nearest_prior.transaction_signature if nearest_prior else None),
        nearest_prior_add_event_index=(nearest_prior.event_index if nearest_prior else None),
        nearest_prior_add_slot=(nearest_prior.slot if nearest_prior else None),
        nearest_prior_add_timestamp=(nearest_prior.timestamp_utc if nearest_prior else None),
        nearest_prior_add_base_amount=(nearest_prior.base_amount if nearest_prior else None),
        nearest_prior_add_quote_amount=(nearest_prior.quote_amount if nearest_prior else None),
        nearest_following_add_signature=(nearest_following.transaction_signature if nearest_following else None),
        nearest_following_add_slot=(nearest_following.slot if nearest_following else None),
        nearest_following_add_timestamp=(nearest_following.timestamp_utc if nearest_following else None),
        slots_between_adds=slot_distance,
        seconds_between_adds=time_distance,
        intervening_transaction_count=tx_between,
        same_pool=(None if nearest is None else nearest.pool == identity.pool),
        same_signer=(None if nearest is None or canonical is None else nearest.signer == canonical.signer),
        same_fee_payer=(None if nearest is None or canonical is None else nearest.fee_payer == canonical.fee_payer),
        same_authority=(None if nearest is None or canonical is None else nearest.authority == canonical.authority),
        common_funder_evidence="UNKNOWN_NOT_DECODED",
        secondary_pool_count=len(secondary),
        secondary_pool_addresses=tuple(secondary),
        liquidity_removed_after_migration=bool(removals),
        liquidity_removed_base_amount=removed_base,
        liquidity_removed_quote_amount=removed_quote,
        reserve_reconciliation_status=reserve_status,
        provider_pool_matches_canonical=provider_match,
        evidence_completeness=(
            "COMPLETE" if (canonical is not None or proof_backed) and not malformed
            else "INCOMPLETE"),
        evidence_observed_at_utc=now_utc,
        evidence_freshness=("STALE" if stale else format(age or Decimal(0), "f")),
        lp_integrity=label,
        lp_integrity_reasons=tuple(dict.fromkeys(reasons)),
        eligible=eligible,
        hard_block=hard_block,
        evidence_event_count=len(ordered),
        sealed_migration_proof_digest=(
            sealed_proof.proof_digest if proof_backed else None),
    )
    return seal_lp_snapshot(snapshot)


def validate_lp_snapshot(snapshot: object) -> Tuple[bool, Optional[str]]:
    if not isinstance(snapshot, LpIntegritySnapshot):
        return False, LP_PROOF_MISSING
    if snapshot.schema_version != LP_SNAPSHOT_VERSION or snapshot.source != LP_SOURCE:
        return False, LP_PROOF_INCONSISTENT
    if not snapshot.proof_digest or snapshot.proof_digest != _lp_digest(snapshot):
        return False, LP_PROOF_INCONSISTENT
    if snapshot.lp_integrity not in LP_INTEGRITY_LABELS:
        return False, LP_PROOF_INCONSISTENT
    if snapshot.lp_integrity in (LP_INTEGRITY_FAIL, LP_INTEGRITY_UNKNOWN):
        if snapshot.eligible or not snapshot.hard_block:
            return False, LP_PROOF_INCONSISTENT
    if snapshot.lp_integrity in (LP_INTEGRITY_PASS, LP_INTEGRITY_WARN):
        if not snapshot.eligible or snapshot.hard_block:
            return False, LP_PROOF_INCONSISTENT
    if snapshot.canonical_pool_proven and not snapshot.canonical_migration_liquidity_signature:
        return False, LP_PROOF_INCONSISTENT
    return True, None


def lp_integrity_block_reason(snapshot: object) -> Optional[str]:
    valid, reason = validate_lp_snapshot(snapshot)
    if not valid:
        return reason or LP_PROOF_INCONSISTENT
    assert isinstance(snapshot, LpIntegritySnapshot)
    if snapshot.lp_integrity == LP_INTEGRITY_FAIL:
        return LP_INTEGRITY_FAIL_REASON
    if snapshot.lp_integrity == LP_INTEGRITY_UNKNOWN or not snapshot.canonical_pool_proven:
        return LP_INTEGRITY_UNKNOWN_REASON
    return None


def format_lp_integrity_lines(snapshot: LpIntegritySnapshot) -> Tuple[str, ...]:
    reasons = ",".join(snapshot.lp_integrity_reasons) if snapshot.lp_integrity_reasons else "none"
    return (
        f"LP Integrity: {snapshot.lp_integrity}",
        f"LP Integrity reasons: {reasons}",
    )


__all__ = (
    "CREATE_POOL", "ADD_LIQUIDITY", "REMOVE_LIQUIDITY", "BUY", "SELL", "UNKNOWN",
    "CREATE_POOL_DISCRIMINATOR", "DEPOSIT_DISCRIMINATOR", "WITHDRAW_DISCRIMINATOR",
    "BUY_DISCRIMINATOR", "SELL_DISCRIMINATOR",
    "LP_INTEGRITY_PASS", "LP_INTEGRITY_WARN", "LP_INTEGRITY_FAIL", "LP_INTEGRITY_UNKNOWN",
    "NONCANONICAL_POOL_SELECTED", "CANONICAL_POOL_UNPROVEN", "WRONG_MINT_PAIR",
    "INVALID_POOL_AUTHORITY", "INVALID_VAULT_OWNERSHIP", "IMPOSSIBLE_RESERVE_RECONCILIATION",
    "LIQUIDITY_EVENT_MALFORMED", "UNEXPLAINED_LIQUIDITY_REMOVAL", "PROVIDER_POOL_MISMATCH",
    "SECONDARY_POOL_MANIPULATION_PROVEN", "VERIFIER_EVIDENCE_STALE", "VERIFIER_EVIDENCE_INVALID",
    "MULTIPLE_ADDS_NEAR_MIGRATION", "LOW_SLOT_DISTANCE_BETWEEN_ADDS",
    "LOW_TX_DISTANCE_BETWEEN_ADDS", "SAME_SIGNER_MULTIPLE_ADDS",
    "SAME_FEE_PAYER_MULTIPLE_ADDS", "SAME_AUTHORITY_MULTIPLE_ADDS",
    "COMMON_FUNDER_SUSPECTED", "SECONDARY_POOL_OBSERVED", "LIQUIDITY_VERIFICATION_INCOMPLETE",
    "CREATION_CONTEXT_TOP_LEVEL", "CREATION_CONTEXT_MIGRATION_CPI", "CREATION_CONTEXT_CPI",
    "CANONICAL_SOURCE_STREAM", "CANONICAL_SOURCE_SEALED_PROOF",
    "LiquidityEvent", "MigrationLiquidityIdentity", "LiquidityIntegrityConfig",
    "LpIntegritySnapshot", "LiquidityIntegrityIndex", "decode_pumpswap_instruction",
    "derive_pool_address", "derive_associated_token_address", "find_program_address",
    "classify_liquidity_integrity", "seal_lp_snapshot", "validate_lp_snapshot",
    "lp_integrity_block_reason", "format_lp_integrity_lines",
)

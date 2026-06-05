"""Stage 29.5.7 Helius raw migration evidence normalizer.

The pure, offline NORMALIZER that turns ONE raw
Helius-shaped confirmed-transaction envelope into either a
PRESENT Stage 29.5 migration evidence record (a proven on-chain
Pump.fun -> PumpSwap migration) or a fail-closed reject result
carrying a PRECISE closed-set reason.

Input envelope shape (raw Helius transaction/log envelope -- the
standard Solana JSON-RPC ``getTransaction`` /
``transactionSubscribe`` / enhanced-webhook confirmed-transaction
object, ``encoding=json``), accepted as a parsed ``dict`` OR as
raw ``bytes`` / ``str`` JSON the normalizer parses itself:

  * ``slot``                         -- top-level int slot
  * ``blockTime``                    -- top-level int Unix UTC
                                        seconds (the migration
                                        anchor source)
  * ``signature`` (optional)         -- top-level signature str,
                                        else ``transaction.signatures[0]``
  * ``transaction.signatures``       -- list of signature strs
  * ``transaction.message.accountKeys`` -- list of base58 account
                                        key strings (ALREADY
                                        encoded; no decode needed)
  * ``transaction.message.instructions`` -- list of
                                        ``{programIdIndex, accounts}``
  * ``meta.err``                     -- ``None`` on success
  * ``meta.logMessages``             -- list of program log strs
  * ``meta.innerInstructions``       -- list of
                                        ``{index, instructions: [...]}``
                                        (the CPI inner instructions
                                        -- where a Pump.fun
                                        migration's ``create_pool``
                                        actually lives)
  * ``meta.loadedAddresses``         -- optional
                                        ``{writable, readonly}``
                                        address-lookup-table keys
                                        (versioned transactions)

Migration detection reads the plaintext log strings, the base58
``accountKeys`` strings, the integer instruction account indices,
AND the Anchor instruction discriminator -- the leading 8 bytes of
each PumpSwap instruction's ``data`` field, recovered by a bounded,
pure, hand-rolled big-integer base58 decode (NO third-party
``base58`` / ``base64`` import; NO borsh event-/arg-DATA decode
beyond the 8-byte discriminator). A migration is PROVEN iff ALL of:

  1. the envelope parses to a transaction object with ``meta``;
  2. the transaction did NOT fail (``meta.err`` is ``None`` /
     absent);
  3. it is NOT a vote transaction;
  4. the PumpSwap (Pump AMM) program was INVOKED (a
     ``Program <PUMPSWAP_PROGRAM_ID> invoke`` log line);
  5. the Anchor ``Instruction: CreatePool`` program-log marker is
     present -- a COARSE PRECONDITION only (ordinary trading emits
     ``Instruction: Buy`` / ``Instruction: Sell``). This log line
     is a tx-level string NOT bound to any one instruction, so it
     is NECESSARY but NEVER sufficient: it can no longer prove a
     migration on its own (an ordinary swap with a stray
     ``Instruction: CreatePool`` log fails at the discriminator
     gate below);
  6. EXACTLY one distinct ``(pool_account, base_mint, quote_mint)``
     quartet resolves across the PumpSwap instructions (top-level +
     inner/CPI) whose OWN ``data`` discriminator IS the IDL-pinned
     ``create_pool`` discriminator
     ``(233, 146, 209, 142, 207, 104, 64, 188)``. The quartet is
     read from the SAME instruction whose discriminator was
     checked: the new ``pool`` at account index 0, the migrated
     ``base_mint`` at index 3, and a known ``quote_mint``
     (wrapped-SOL / USDC) at index 4. An ordinary ``Buy`` / ``Sell``
     shares this EXACT ``pool``@0 / ``base_mint``@3 / ``quote_mint``@4
     account layout, so the account layout ALONE is never migration
     evidence -- ONLY the ``create_pool`` discriminator on that same
     instruction distinguishes a migration from a swap. Value-
     identical quartets (e.g. two ``create_pool`` views of the same
     new pool) collapse to one; two DISTINCT quartets (an ambiguous
     multi-pool transaction) fail closed;
  7. a non-blank transaction signature, a non-negative int slot,
     and a non-negative int ``blockTime`` are all present.

On success the normalizer emits a
:class:`~PHX2.stage29.stage29_5_migration_models.Stage29_5MigrationEvidenceRecord`
with ``migration_status=PRESENT`` /
``migration_source=HELIUS_WS``, the resolved quartet
(``pool_program_id`` = the PumpSwap program id), the
``blockTime``-derived strict trailing-``Z`` migration anchor, the
slot, the signature, and a signature+slot ``source_event_ref``.
Anything else fails closed with a precise reject reason and NO
evidence record.

The normalizer FABRICATES nothing: every axis is read directly
from the envelope; it NEVER infers migration from a token suffix,
a pair-type, or "a swap happened"; it NEVER invents a mint / pool
/ quote / timestamp / slot / signature. It is a pure function:
same envelope + same ``observed_at_utc`` => same result; it never
raises (a malformed envelope fails closed to a reject result).

Why the instruction account layout (not token-balance grouping):
a ``create_pool`` migration debits the migration creator's base +
quote token accounts INTO the new pool vaults, so BOTH the
creator and the pool PDA own a ``{base, quote}`` token-account
pair -- a token-balance owner-grouping would be ambiguous. The
``create_pool`` instruction's own account list names the pool /
base / quote at fixed IDL-pinned positions and is unambiguous; on
the Helius JSON shape those positions resolve to ready-made base58
strings. The instruction itself is identified by its own Anchor
discriminator (decoded from its ``data``), so the pool / base /
quote read is BOUND to the genuine ``create_pool`` migration
instruction and never to a look-alike ``Buy`` / ``Sell`` that
happens to share the same account positions.

Discipline:

  * Stdlib only (``json`` / ``typing``). NO third-party
    ``base58`` / ``base64`` / ``construct`` import -- the 8-byte
    Anchor discriminator is recovered by a bounded, pure,
    hand-rolled big-integer base58 decode (``_base58_decode``); no
    borsh / event-data decode is performed beyond it. NO
    ``datetime`` / ``time`` (the anchor formatter in the models
    sibling is pure integer arithmetic; the caller injects
    ``observed_at_utc``).
  * Imports ONLY the Stage 29.5 migration-models module, the
    Stage 29.1 PumpSwap program constants (the authoritative,
    vendored-IDL-pinned program id + quote mints), and the Stage
    29.5.7 models sibling. No Stage 30 import. No Stage 21-28
    import. No Stage 29.3 / 29.4 import.
  * No ``os.environ`` / ``os.getenv`` access; no env read.
  * No network, no HTTP, no gRPC, no WebSocket, no socket. The
    envelope is INJECTED -- the normalizer never opens a
    connection.
  * No module-body Call (no implicit I/O at import time).
  * No legacy pre-PHX2 import path.
"""

from __future__ import annotations

import json
from typing import List, Optional, Set, Tuple

from PHX2.stage29.pumpswap_program_constants import (
    KNOWN_QUOTE_MINT_TO_PROVIDER_PAIR_TYPE_HINT,
    PUMPSWAP_PROGRAM_ID,
)
from PHX2.stage29.stage29_5_migration_models import (
    MIGRATION_SOURCE_HELIUS_WS,
    MIGRATION_STATUS_PRESENT,
    Stage29_5MigrationEvidenceRecord,
    is_safe_iso8601_utc_string,
    is_safe_mint_or_pool_string,
)
from PHX2.stage29.stage29_5_7_helius_raw_migration_models import (
    CREATE_POOL_ACCOUNT_INDEX_BASE_MINT,
    CREATE_POOL_ACCOUNT_INDEX_POOL,
    CREATE_POOL_ACCOUNT_INDEX_QUOTE_MINT,
    CREATE_POOL_MIN_ACCOUNT_COUNT,
    NORMALIZATION_OUTCOME_MIGRATION_PROVEN,
    NORMALIZATION_OUTCOME_NO_MIGRATION_EVIDENCE,
    PUMPSWAP_CREATE_POOL_INSTRUCTION_DISCRIMINATOR,
    PUMPSWAP_CREATE_POOL_INSTRUCTION_LOG,
    PUMPSWAP_CREATE_POOL_INSTRUCTION_NAME,
    REJECT_REASON_MALFORMED_OBSERVED_AT,
    REJECT_REASON_MALFORMED_PAYLOAD,
    REJECT_REASON_MISSING_BLOCK_TIME,
    REJECT_REASON_MISSING_SIGNATURE,
    REJECT_REASON_MISSING_SLOT,
    REJECT_REASON_NO_CREATE_POOL_INSTRUCTION,
    REJECT_REASON_NONE,
    REJECT_REASON_NOT_A_TRANSACTION_ENVELOPE,
    REJECT_REASON_POOL_QUARTET_UNRESOLVED,
    REJECT_REASON_PUMPSWAP_PROGRAM_NOT_INVOKED,
    REJECT_REASON_TRANSACTION_FAILED,
    REJECT_REASON_UNSAFE_AXIS_SHAPE,
    REJECT_REASON_VOTE_TRANSACTION,
    Stage29_5_7MigrationNormalizationResult,
    build_source_ref,
    epoch_seconds_to_trailing_z_utc,
    is_nonblank_str,
    is_nonneg_int,
)


# ---------------------------------------------------------------------------
# Derived markers (built once at import time from the imported program id; plain
# string concatenation, not a Call node, so the module body stays Call-free)
# ---------------------------------------------------------------------------


# A PumpSwap program invocation log line begins with this prefix
# (``Program <PUMPSWAP_PROGRAM_ID> invoke [<depth>]``). Built from the imported,
# vendored-IDL-pinned program id so it can never drift from the rest of Stage 29.
_PUMPSWAP_INVOKE_LOG_PREFIX: str = f"Program {PUMPSWAP_PROGRAM_ID} invoke"


# A tolerant tail form of the Anchor instruction marker, in case a provider
# prefixes the program log line differently; the canonical exact form is
# ``PUMPSWAP_CREATE_POOL_INSTRUCTION_LOG``.
_CREATE_POOL_LOG_TAIL: str = (
    f"Instruction: {PUMPSWAP_CREATE_POOL_INSTRUCTION_NAME}"
)


# ---------------------------------------------------------------------------
# Pure result builders
# ---------------------------------------------------------------------------


def _reject(
    reason: str,
    *,
    pumpswap_instruction_count: int = 0,
    create_pool_match_count: int = 0,
) -> Stage29_5_7MigrationNormalizationResult:
    """Build a fail-closed (no evidence) normalization result carrying the
    precise reject reason + diagnostic counts. Pure; no I/O.
    """
    return Stage29_5_7MigrationNormalizationResult(
        outcome=NORMALIZATION_OUTCOME_NO_MIGRATION_EVIDENCE,
        reject_reason=reason,
        evidence_record=None,
        pumpswap_instruction_count=pumpswap_instruction_count,
        create_pool_match_count=create_pool_match_count,
    )


# ---------------------------------------------------------------------------
# Pure envelope readers
# ---------------------------------------------------------------------------


def _parse_envelope_to_mapping(envelope: object) -> Optional[dict]:
    """Parse ``envelope`` into a JSON object ``dict``, or ``None``.

    Pure / total; never raises. A ``dict`` is returned as-is (an already-parsed
    envelope). ``bytes`` are decoded as UTF-8 then JSON-parsed; ``str`` is
    JSON-parsed. A non-UTF-8 / non-JSON / non-object body yields ``None``.
    Mirrors the Stage 29.5 Helius WS adapter's ``_decode_message_body``
    discipline BY VALUE (minus the raw-JSON-RPC-envelope refusal -- THIS slice is
    the raw decoder the WS adapter deferred).
    """
    if isinstance(envelope, dict):
        return envelope
    if isinstance(envelope, (bytes, bytearray)):
        try:
            text = bytes(envelope).decode("utf-8")
        except UnicodeDecodeError:
            return None
    elif isinstance(envelope, str):
        text = envelope
    else:
        return None
    try:
        parsed = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return None
    if not isinstance(parsed, dict):
        return None
    return parsed


def _get_mapping(obj: object, key: str) -> Optional[dict]:
    """Return ``obj[key]`` if ``obj`` is a mapping and the value is a mapping,
    else ``None``. Pure / total.
    """
    if not isinstance(obj, dict):
        return None
    value = obj.get(key)
    return value if isinstance(value, dict) else None


def _get_list(obj: object, key: str) -> List[object]:
    """Return ``obj[key]`` if ``obj`` is a mapping and the value is a list, else
    ``[]``. Pure / total.
    """
    if not isinstance(obj, dict):
        return []
    value = obj.get(key)
    return list(value) if isinstance(value, list) else []


def _extract_log_messages(meta: dict) -> List[str]:
    """Return ``meta.logMessages`` as a list of strings (non-string entries
    dropped). Pure / total.
    """
    raw = _get_list(meta, "logMessages")
    return [line for line in raw if isinstance(line, str)]


def _pumpswap_program_invoked(logs: List[str]) -> bool:
    """Return ``True`` iff a PumpSwap program invocation log line is present
    (``Program <PUMPSWAP_PROGRAM_ID> invoke [<depth>]``). Pure / total.
    """
    return any(
        line.strip().startswith(_PUMPSWAP_INVOKE_LOG_PREFIX)
        for line in logs
    )


def _create_pool_instruction_logged(logs: List[str]) -> bool:
    """Return ``True`` iff the Anchor ``Instruction: CreatePool`` program-log
    marker is present -- the migration-proving ``create_pool`` instruction.

    Pure / total. Accepts the canonical exact marker
    (``Program log: Instruction: CreatePool``) OR a program-log line ending in
    ``Instruction: CreatePool`` (tolerant of a differently-prefixed program log),
    so an ordinary ``Instruction: Buy`` / ``Instruction: Sell`` swap is NOT
    treated as a migration.
    """
    for line in logs:
        stripped = line.strip()
        if stripped == PUMPSWAP_CREATE_POOL_INSTRUCTION_LOG:
            return True
        if (
            stripped.startswith("Program log:")
            and stripped.endswith(_CREATE_POOL_LOG_TAIL)
        ):
            return True
    return False


def _is_vote_transaction(envelope: dict, tx: Optional[dict]) -> bool:
    """Return ``True`` iff the envelope flags a vote transaction.

    Pure / total. Vote transactions are filtered from a PumpSwap subscription, so
    this is a defensive belt: any truthy ``isVote`` / ``is_vote`` flag on the
    envelope or transaction object marks a vote (which carries no migration).
    """
    for source in (envelope, tx):
        if isinstance(source, dict):
            if bool(source.get("isVote", False)) or bool(
                source.get("is_vote", False)
            ):
                return True
    return False


def _extract_signature(envelope: dict, tx: Optional[dict]) -> Optional[str]:
    """Extract the transaction signature from ``envelope.signature`` or
    ``transaction.signatures[0]``, or ``None``. Pure / total.
    """
    top = envelope.get("signature")
    if is_nonblank_str(top):
        return top  # type: ignore[return-value]
    if isinstance(tx, dict):
        signatures = tx.get("signatures")
        if isinstance(signatures, list) and signatures:
            first = signatures[0]
            if is_nonblank_str(first):
                return first  # type: ignore[return-value]
    return None


# ---------------------------------------------------------------------------
# Anchor instruction discriminator decode (bounded, stdlib-only base58)
# ---------------------------------------------------------------------------
#
# Helius / Solana ``encoding=json`` confirmed transactions carry each
# instruction's ``data`` as a base58 string. The migration proof MUST be bound to
# the ACTUAL ``create_pool`` instruction: an ordinary Buy / Sell shares
# create_pool's EXACT pool@0 / base@3 / quote@4 account layout (see the vendored
# IDL), so the account layout alone cannot tell a migration from a swap. We
# therefore decode the leading 8 bytes (the Anchor discriminator) of each PumpSwap
# instruction's ``data`` and require it to equal the IDL-pinned ``create_pool``
# discriminator. The decode is a bounded, pure, hand-rolled big-integer base58
# reader -- NO third-party ``base58`` / ``base64`` import (the boundary scan
# forbids those), and NO borsh event-/arg-data decode beyond the discriminator.


_BASE58_ALPHABET: str = (
    "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
)


def _base58_decode(data: object) -> Optional[bytes]:
    """Decode a base58 (Bitcoin-alphabet) string into raw bytes, or ``None``.

    Pure / total; never raises. Stdlib-only big-integer arithmetic (NO ``base58``
    / ``base64`` import). A non-string, an empty string, or ANY character outside
    the base58 alphabet fails closed to ``None`` -- so a base64 / malformed /
    truncated ``data`` field never yields a spurious discriminator match.
    """
    if not isinstance(data, str) or data == "":
        return None
    acc = 0
    for ch in data:
        digit = _BASE58_ALPHABET.find(ch)
        if digit < 0:
            return None
        acc = acc * 58 + digit
    # Base58 leading-zero convention: each leading '1' encodes one leading 0x00
    # byte (preserved so the discriminator byte offsets stay correct).
    leading_zeros = 0
    for ch in data:
        if ch == "1":
            leading_zeros += 1
        else:
            break
    body = acc.to_bytes((acc.bit_length() + 7) // 8, "big") if acc else b""
    return (b"\x00" * leading_zeros) + body


def _instruction_is_create_pool(instruction: object) -> bool:
    """Return ``True`` iff ``instruction``'s base58 ``data`` field decodes to a
    byte string whose leading Anchor discriminator equals the IDL-pinned PumpSwap
    ``create_pool`` discriminator.

    Pure / total; never raises. This is the BINDING check that ties the migration
    proof to the genuine ``create_pool`` instruction: an ordinary Buy / Sell -- or
    a stray tx-level ``Instruction: CreatePool`` log over an ordinary swap --
    carries a DIFFERENT discriminator and fails here, EVEN THOUGH it shares
    create_pool's pool@0 / base@3 / quote@4 account layout. A non-dict instruction,
    a missing / non-base58 / too-short ``data`` field fails closed to ``False``.
    """
    if not isinstance(instruction, dict):
        return False
    discriminator = PUMPSWAP_CREATE_POOL_INSTRUCTION_DISCRIMINATOR
    raw = _base58_decode(instruction.get("data"))
    if raw is None or len(raw) < len(discriminator):
        return False
    return tuple(raw[: len(discriminator)]) == discriminator


# ---------------------------------------------------------------------------
# Pure create_pool quartet resolver (IDL-pinned instruction account layout)
# ---------------------------------------------------------------------------


def _resolve_account_keys(message: dict, meta: dict) -> List[str]:
    """Build the full resolved account-key list an instruction's account indices
    index into: the message's static ``accountKeys`` followed by the
    ``meta.loadedAddresses`` writable then readonly keys (the canonical Solana
    index-resolution order for a versioned transaction).

    Pure / total. Each entry is a base58 string when resolvable, or ``""`` as an
    index-preserving placeholder for a malformed entry (a ``""`` placeholder
    never passes the safe-shape mint check, so a malformed key simply fails the
    quartet match). Tolerates the ``encoding=jsonParsed`` ``accountKeys`` dict
    shape (``{"pubkey": ...}``) for index alignment.
    """
    keys: List[str] = []
    for entry in _get_list(message, "accountKeys"):
        if isinstance(entry, str):
            keys.append(entry)
        elif isinstance(entry, dict):
            pubkey = entry.get("pubkey")
            keys.append(pubkey if isinstance(pubkey, str) else "")
        else:
            keys.append("")
    loaded = _get_mapping(meta, "loadedAddresses")
    if loaded is not None:
        for bucket in ("writable", "readonly"):
            for entry in _get_list(loaded, bucket):
                keys.append(entry if isinstance(entry, str) else "")
    return keys


def _collect_instructions(message: dict, meta: dict) -> List[dict]:
    """Collect ALL instruction mappings -- the top-level
    ``message.instructions`` plus every ``meta.innerInstructions[].instructions``
    (the CPI inner instructions, where a Pump.fun migration's ``create_pool``
    lives). Pure / total.
    """
    out: List[dict] = []
    for ins in _get_list(message, "instructions"):
        if isinstance(ins, dict):
            out.append(ins)
    for group in _get_list(meta, "innerInstructions"):
        if isinstance(group, dict):
            for ins in _get_list(group, "instructions"):
                if isinstance(ins, dict):
                    out.append(ins)
    return out


def _known_quote_mints() -> Set[str]:
    """Return the set of known quote mints (wrapped-SOL / USDC). Pure / total."""
    return set(KNOWN_QUOTE_MINT_TO_PROVIDER_PAIR_TYPE_HINT.keys())


def _resolve_account_at(
    resolved_keys: List[str], accounts: object, position: int
) -> Optional[str]:
    """Resolve the account key at instruction-account ``position`` against
    ``resolved_keys``, or ``None``. Pure / total; guards every index.
    """
    if not isinstance(accounts, list) or position >= len(accounts):
        return None
    idx = accounts[position]
    if isinstance(idx, bool) or not isinstance(idx, int):
        return None
    if idx < 0 or idx >= len(resolved_keys):
        return None
    key = resolved_keys[idx]
    return key if isinstance(key, str) and key != "" else None


def _program_id_of(
    resolved_keys: List[str], instruction: dict
) -> Optional[str]:
    """Resolve an instruction's program id from its ``programIdIndex`` against
    ``resolved_keys``, or ``None``. Pure / total.
    """
    prog_idx = instruction.get("programIdIndex")
    if isinstance(prog_idx, bool) or not isinstance(prog_idx, int):
        return None
    if prog_idx < 0 or prog_idx >= len(resolved_keys):
        return None
    key = resolved_keys[prog_idx]
    return key if isinstance(key, str) and key != "" else None


def _extract_create_pool_quartet(
    resolved_keys: List[str], instructions: List[dict]
) -> Tuple[Optional[Tuple[str, str, str]], int, int]:
    """Resolve the single distinct ``create_pool`` ``(pool, base, quote)`` quartet
    across the PumpSwap instructions WHOSE OWN ``data`` DISCRIMINATOR IS the
    IDL-pinned ``create_pool`` discriminator, applying the IDL-pinned account
    layout to that same instruction.

    Returns ``(quartet, pumpswap_instruction_count, create_pool_match_count)``.
    Only an instruction that passes :func:`_instruction_is_create_pool` (the
    discriminator gate) is considered -- an ordinary Buy / Sell shares the EXACT
    pool@0 / base@3 / quote@4 layout, so the layout alone never qualifies.
    ``quartet`` is the single distinct ``(pool_account, base_mint, quote_mint)``
    iff exactly one DISTINCT quartet matched a discriminator-bound ``create_pool``
    instruction (the new ``pool`` at index 0, ``base_mint`` at index 3, a known
    ``quote_mint`` at index 4; pool / base / quote distinct safe-shape strings;
    base NOT a known quote); value-identical quartets (two ``create_pool`` views
    of the same new pool) collapse to one. Zero matches or two DISTINCT quartets
    -> ``None`` (fail closed). ``create_pool_match_count`` counts only
    discriminator-bound create_pool instructions with a valid quartet shape. Pure
    / deterministic.
    """
    known_quotes = _known_quote_mints()
    pumpswap_instruction_count = 0
    matches: List[Tuple[str, str, str]] = []
    for instruction in instructions:
        program_id = _program_id_of(resolved_keys, instruction)
        if program_id != PUMPSWAP_PROGRAM_ID:
            continue
        pumpswap_instruction_count += 1
        # BIND the proof to the ACTUAL create_pool instruction: the instruction
        # whose accounts we are about to read MUST itself carry the create_pool
        # Anchor discriminator in its ``data``. A Buy / Sell -- or an ordinary swap
        # with a stray tx-level ``Instruction: CreatePool`` log -- shares the
        # pool@0 / base@3 / quote@4 layout but has a DIFFERENT discriminator, so it
        # never contributes a quartet here.
        if not _instruction_is_create_pool(instruction):
            continue
        accounts = instruction.get("accounts")
        if not isinstance(accounts, list):
            continue
        if len(accounts) < CREATE_POOL_MIN_ACCOUNT_COUNT:
            continue
        pool = _resolve_account_at(
            resolved_keys, accounts, CREATE_POOL_ACCOUNT_INDEX_POOL
        )
        base_mint = _resolve_account_at(
            resolved_keys, accounts, CREATE_POOL_ACCOUNT_INDEX_BASE_MINT
        )
        quote_mint = _resolve_account_at(
            resolved_keys, accounts, CREATE_POOL_ACCOUNT_INDEX_QUOTE_MINT
        )
        if pool is None or base_mint is None or quote_mint is None:
            continue
        if not is_safe_mint_or_pool_string(pool):
            continue
        if not is_safe_mint_or_pool_string(base_mint):
            continue
        if not is_safe_mint_or_pool_string(quote_mint):
            continue
        # The quote at index 4 must be a known quote mint (wrapped-SOL / USDC);
        # the base at index 3 must be the NON-quote token; pool / base / quote
        # must be three distinct accounts.
        if quote_mint not in known_quotes:
            continue
        if base_mint in known_quotes:
            continue
        if len({pool, base_mint, quote_mint}) != 3:
            continue
        matches.append((pool, base_mint, quote_mint))
    distinct: List[Tuple[str, str, str]] = []
    for quartet in matches:
        if quartet not in distinct:
            distinct.append(quartet)
    if len(distinct) == 1:
        return distinct[0], pumpswap_instruction_count, len(matches)
    return None, pumpswap_instruction_count, len(matches)


# ---------------------------------------------------------------------------
# Public normalizer
# ---------------------------------------------------------------------------


def normalize_helius_raw_migration_envelope(
    envelope: object,
    observed_at_utc: str,
) -> Stage29_5_7MigrationNormalizationResult:
    """Normalize ONE raw Helius confirmed-transaction envelope into a PRESENT
    Stage 29.5 migration evidence record, or fail closed with a precise reason.

    Pure / deterministic / total; never raises (a malformed envelope fails closed
    to a reject result). No I/O, no network, no env read, no wall-clock read
    (``observed_at_utc`` is caller-injected). See the module docstring for the
    full detection contract.

    Rejection precedence (top-down, FIRST failing check wins):

      1. OBSERVED-AT -- ``observed_at_utc`` must be a UTC-shaped ISO-8601 string.
         A malformed clock value -> ``MALFORMED_OBSERVED_AT``.
      2. ENVELOPE -- the payload must parse to a JSON object. A non-UTF-8 /
         non-JSON body -> ``MALFORMED_PAYLOAD``; a parsed non-object, or an
         object with no ``meta`` -> ``NOT_A_TRANSACTION_ENVELOPE``.
      3. SUCCESS -- ``meta.err`` must be ``None`` / absent. A failed transaction
         -> ``TRANSACTION_FAILED``.
      4. VOTE -- a vote transaction -> ``VOTE_TRANSACTION``.
      5. PROGRAM -- the PumpSwap program must be INVOKED. Otherwise ->
         ``PUMPSWAP_PROGRAM_NOT_INVOKED`` (wrong program).
      6. INSTRUCTION (LOG PRECONDITION) -- the Anchor ``Instruction: CreatePool``
         program-log marker must be present. This is a COARSE, NOT-sufficient gate
         (an ordinary ``Buy`` / ``Sell`` swap emits no CreatePool marker). No
         marker -> ``NO_CREATE_POOL_INSTRUCTION``.
      7. QUARTET (DISCRIMINATOR-BOUND) -- exactly one distinct
         ``(pool_account, base_mint, quote_mint)`` must resolve from a PumpSwap
         instruction whose OWN ``data`` discriminator IS the IDL-pinned
         ``create_pool`` discriminator, with the account layout read from THAT
         SAME instruction. An ordinary swap carrying a stray ``CreatePool`` log, a
         ``Buy`` / ``Sell`` account layout, or zero / ambiguous create_pool
         instructions all resolve no quartet -> ``POOL_QUARTET_UNRESOLVED``.
      8. SIGNATURE -- a non-blank signature -> else ``MISSING_SIGNATURE``.
      9. SLOT -- a non-negative int slot -> else ``MISSING_SLOT``.
      10. BLOCK TIME -- a non-negative int ``blockTime`` that formats to a strict
          trailing-``Z`` anchor -> else ``MISSING_BLOCK_TIME``.
      11. RECORD -- building the PRESENT record must not reject an axis shape ->
          else ``UNSAFE_AXIS_SHAPE`` (defensive; the quartet axes are pre-checked
          to safe shape).
      12. otherwise -> ``MIGRATION_PROVEN`` with the PRESENT evidence record.
    """
    # ---- 1. Observed-at clock value ----
    if not is_safe_iso8601_utc_string(observed_at_utc):
        return _reject(REJECT_REASON_MALFORMED_OBSERVED_AT)

    # ---- 2. Envelope -> mapping + meta ----
    mapping = _parse_envelope_to_mapping(envelope)
    if mapping is None:
        if isinstance(envelope, (dict, str, bytes, bytearray)):
            return _reject(REJECT_REASON_MALFORMED_PAYLOAD)
        return _reject(REJECT_REASON_NOT_A_TRANSACTION_ENVELOPE)
    meta = _get_mapping(mapping, "meta")
    if meta is None:
        return _reject(REJECT_REASON_NOT_A_TRANSACTION_ENVELOPE)
    tx = _get_mapping(mapping, "transaction")

    # ---- 3. Success (meta.err absent / None) ----
    if meta.get("err", None) is not None:
        return _reject(REJECT_REASON_TRANSACTION_FAILED)

    # ---- 4. Vote ----
    if _is_vote_transaction(mapping, tx):
        return _reject(REJECT_REASON_VOTE_TRANSACTION)

    # ---- 5. PumpSwap program invoked ----
    logs = _extract_log_messages(meta)
    if not _pumpswap_program_invoked(logs):
        return _reject(REJECT_REASON_PUMPSWAP_PROGRAM_NOT_INVOKED)

    # ---- 6. CreatePool migration instruction (reject ordinary swaps) ----
    if not _create_pool_instruction_logged(logs):
        return _reject(REJECT_REASON_NO_CREATE_POOL_INSTRUCTION)

    # ---- 7. Pool quartet via IDL-pinned create_pool account layout ----
    message = _get_mapping(tx, "message") if tx is not None else None
    if message is None:
        return _reject(REJECT_REASON_POOL_QUARTET_UNRESOLVED)
    resolved_keys = _resolve_account_keys(message, meta)
    instructions = _collect_instructions(message, meta)
    quartet, pumpswap_count, match_count = _extract_create_pool_quartet(
        resolved_keys, instructions
    )
    if quartet is None:
        return _reject(
            REJECT_REASON_POOL_QUARTET_UNRESOLVED,
            pumpswap_instruction_count=pumpswap_count,
            create_pool_match_count=match_count,
        )
    pool_account, base_mint, quote_mint = quartet

    # ---- 8. Signature ----
    signature = _extract_signature(mapping, tx)
    if signature is None:
        return _reject(
            REJECT_REASON_MISSING_SIGNATURE,
            pumpswap_instruction_count=pumpswap_count,
            create_pool_match_count=match_count,
        )

    # ---- 9. Slot ----
    slot = mapping.get("slot")
    if not is_nonneg_int(slot):
        return _reject(
            REJECT_REASON_MISSING_SLOT,
            pumpswap_instruction_count=pumpswap_count,
            create_pool_match_count=match_count,
        )

    # ---- 10. Block time -> strict trailing-Z anchor ----
    anchor = epoch_seconds_to_trailing_z_utc(mapping.get("blockTime"))
    if anchor is None:
        return _reject(
            REJECT_REASON_MISSING_BLOCK_TIME,
            pumpswap_instruction_count=pumpswap_count,
            create_pool_match_count=match_count,
        )

    # ---- 11. Build the PRESENT Stage 29.5 evidence record ----
    source_ref = build_source_ref(signature, int(slot))
    try:
        record = Stage29_5MigrationEvidenceRecord(
            migration_status=MIGRATION_STATUS_PRESENT,
            migration_source=MIGRATION_SOURCE_HELIUS_WS,
            base_mint=base_mint,
            pool_account=pool_account,
            pool_program_id=PUMPSWAP_PROGRAM_ID,
            quote_mint=quote_mint,
            migration_timestamp_utc=anchor,
            migration_slot=int(slot),
            migration_signature=signature,
            observed_at_utc=observed_at_utc,
            source_event_ref=source_ref,
        )
    except ValueError:
        # Defensive: the quartet axes are pre-checked to safe shape, so this is
        # only reachable for an exotic residual; fail closed rather than raise.
        return _reject(
            REJECT_REASON_UNSAFE_AXIS_SHAPE,
            pumpswap_instruction_count=pumpswap_count,
            create_pool_match_count=match_count,
        )

    # ---- 12. Proven migration ----
    return Stage29_5_7MigrationNormalizationResult(
        outcome=NORMALIZATION_OUTCOME_MIGRATION_PROVEN,
        reject_reason=REJECT_REASON_NONE,
        evidence_record=record,
        pumpswap_instruction_count=pumpswap_count,
        create_pool_match_count=match_count,
    )


__all__ = (
    "normalize_helius_raw_migration_envelope",
)

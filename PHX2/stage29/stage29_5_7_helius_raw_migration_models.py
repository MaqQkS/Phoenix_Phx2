"""Stage 29.5.7 Helius raw migration evidence model layer.

Stage 29.5.7 closes the narrowest remaining blocker the Codex
blocker audit identified: PHX2 has safe routers (Stage 30.11.9),
a correct confirmation (Stage 30.11.8), and a correct enrichment
gate (Stage 30.11.7), but it has NO real live migration evidence
PRODUCER/NORMALIZER. Every committed migration source is either a
stub (the Stage 29.5 Helius WS adapter only parses
PRE-normalized ``PUMP_AMM_MIGRATION`` messages and explicitly
refuses raw Helius JSON-RPC) or a deliberate
``MIGRATION_SOURCE_UNKNOWN`` placeholder
(``Stage29_3NoMigrationEvidenceSource``). So a harvested live
candidate could only ever die at ``MISSING_MIGRATION_EVIDENCE``.

Stage 29.5.7 ships the SMALLEST real migration evidence
producer/normalizer: it consumes a raw Helius-shaped confirmed
transaction envelope (the standard Solana JSON-RPC
``getTransaction`` / ``transactionSubscribe`` / enhanced-webhook
shape: top-level ``slot`` / ``blockTime``, ``transaction``
``signatures`` + ``message.accountKeys``, ``meta`` ``err`` /
``logMessages`` / ``preTokenBalances`` / ``postTokenBalances``),
detects the actual Pump.fun -> PumpSwap (Pump AMM) migration
event -- the on-chain ``create_pool`` instruction that emits the
``CreatePoolEvent`` -- and normalizes it into the EXISTING Stage
29.5 migration evidence shape
(:class:`~PHX2.stage29.stage29_5_migration_models.Stage29_5MigrationEvidenceRecord`
with ``migration_status=PRESENT``).

This module is the MODEL layer for that producer. It owns:

  * the IDL-pinned authoritative identity of the migration event
    (the ``create_pool`` instruction discriminator + the
    ``CreatePoolEvent`` event discriminator, mirrored BY VALUE
    from the vendored Pump AMM Anchor IDL at
    ``PHX2/proto/stage29_1/source/pump_amm.json`` and pinned
    byte-for-byte by ``test_stage_29_5_7_vendored_idl.py``);
  * the runtime migration signals the normalizer gates on -- the
    IDL-pinned ``create_pool`` instruction discriminator (the
    BINDING proof, decoded from the instruction ``data`` and
    matched on the SAME instruction whose pool / base / quote
    accounts are read) plus the Anchor ``Instruction: CreatePool``
    program-log marker (a coarse, NOT-sufficient precondition;
    ordinary trading emits ``Instruction: Buy`` /
    ``Instruction: Sell``);
  * the closed-set normalization OUTCOME + REJECT-REASON
    vocabularies (a non-migration / malformed / partial envelope
    fails closed with a PRECISE reason -- never fabricated into a
    PRESENT record);
  * a pure, clock-free epoch-seconds -> strict trailing-``Z`` UTC
    timestamp formatter (the migration anchor is derived from the
    transaction ``blockTime`` by pure integer arithmetic; the
    output is ALWAYS trailing-``Z`` and NEVER the ``+00:00``
    offset form);
  * the sanitized per-mint migration-evidence SUMMARY the
    producer projects a PRESENT record onto. Its field NAMES
    equal the Stage 30.11.9 / Stage 30.11.8 migration evidence
    field names BY VALUE (``token_mint`` / ``measurement_status``
    / ``migration_event_time_utc`` / ``warnings`` /
    ``redaction_status`` / ``source_ref``) so the committed Stage
    30.11.9 ``build_evidence_record_from_sanitized_projection``
    mapper / Stage 30.11.8 confirmation read it duck-typed --
    WITHOUT this module importing any Stage 30 module (Stage 30
    mirrors Stage 29 BY VALUE; the reverse import is forbidden);
  * the normalization RESULT carrier (the outcome + reject reason
    + the optional PRESENT evidence record + the diagnostic token
    balance counts).

Stage 29.5.7 FABRICATES nothing. Every emitted axis is sourced
directly from the raw envelope; a missing / ambiguous axis fails
the whole envelope closed. The migration anchor is computed from
the on-chain ``blockTime`` and is NEVER invented. The COMPLETE /
SAFE summary is emitted ONLY for a fully-proven PRESENT record.

Discipline:

  * Stdlib only (``dataclasses`` / ``typing``). This MODEL module
    itself performs NO decode and imports NO ``base58`` /
    ``base64``; the normalizer sibling recovers the 8-byte Anchor
    discriminator via a bounded, hand-rolled big-integer base58
    decode (NO third-party ``base58`` / ``base64`` import; no
    borsh event-/arg-data decode beyond the discriminator).
  * Imports ONLY the Stage 29.5 migration-models module (for the
    record type re-used as the normalized output). No Stage 30
    import. No Stage 21-28 import. No Stage 29.3 / 29.4 import.
  * No ``os.environ`` / ``os.getenv`` access; no env read.
  * No network, no HTTP, no gRPC, no WebSocket, no socket.
  * No ``time`` / ``datetime`` import; the epoch -> trailing-``Z``
    formatter is pure integer arithmetic (no wall-clock read --
    every clock is caller-injected).
  * No module-body Call (no implicit I/O at import time; the only
    admitted module-body Call shape is the ``@dataclass(...)``
    decorator). Every discriminator is a plain tuple-of-int
    literal, never a ``bytes(...)`` Call.
  * No legacy pre-PHX2 import path.
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from typing import Optional, Tuple

from PHX2.stage29.stage29_5_migration_models import (
    Stage29_5MigrationEvidenceRecord,
)


# ---------------------------------------------------------------------------
# Minor version + schema identity
# ---------------------------------------------------------------------------


STAGE29_5_7_MINOR_VERSION: str = "29.5.7"


STAGE29_5_7_RAW_MIGRATION_EVIDENCE_SCHEMA_VERSION: str = (
    "stage29_5_7_v0_helius_raw_migration_evidence"
)


# The safe-shape provenance token the producer stamps onto its proof tally
# (provenance only; names the slice that produced the evidence, never a secret /
# host / endpoint / transport destination).
STAGE29_5_7_SOURCE_STAGE: str = "29.5.7"


# ---------------------------------------------------------------------------
# IDL-pinned authoritative migration-event identity (Pump AMM / PumpSwap)
# ---------------------------------------------------------------------------
#
# These are the byte-for-byte Anchor discriminators of the migration-proving
# ``create_pool`` instruction and its emitted ``CreatePoolEvent`` on the public
# Pump AMM (PumpSwap) program (``pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA``).
# The authoritative provenance is the vendored Anchor IDL at
# ``PHX2/proto/stage29_1/source/pump_amm.json``;
# ``test_stage_29_5_7_vendored_idl.py`` reads that file at test time and pins
# both discriminators (and the IDL SHA-256, already pinned by Stage 29.1) match
# these tuples byte-for-byte. They are plain tuple-of-int literals (NOT a
# ``bytes(...)`` Call) so this module body carries no Call node.
#
# Pump.fun bonding-curve graduation creates the token's PumpSwap pool via this
# ``create_pool`` instruction; ordinary post-migration trading is ``Buy`` /
# ``Sell`` (different discriminators -- see Stage 29.1 constants). These
# discriminators are the AUTHORITATIVE on-chain identity the runtime detection
# gates on: the normalizer sibling decodes each PumpSwap instruction's leading
# 8-byte Anchor discriminator (via a bounded, hand-rolled base58 reader -- no
# third-party ``base58`` / ``base64`` import) and admits a migration ONLY when the
# ``create_pool`` discriminator is present on the SAME instruction whose pool /
# base / quote accounts it reads.


PUMPSWAP_CREATE_POOL_INSTRUCTION_DISCRIMINATOR: Tuple[int, ...] = (
    233,
    146,
    209,
    142,
    207,
    104,
    64,
    188,
)


PUMPSWAP_CREATE_POOL_EVENT_DISCRIMINATOR: Tuple[int, ...] = (
    177,
    49,
    12,
    210,
    160,
    118,
    167,
    116,
)


# The Anchor instruction-name program-log marker the migration-proving
# ``create_pool`` handler emits. Anchor logs ``Program log: Instruction: <Name>``
# at the start of each instruction handler, with ``<Name>`` the PascalCase of the
# instruction name (``create_pool`` -> ``CreatePool``). This plaintext log line is
# a COARSE runtime precondition the normalizer gates on -- NOT the binding
# migration proof (the create_pool instruction discriminator is); it is present on
# a real migration transaction and absent on an ordinary swap (which logs
# ``Instruction: Buy`` / ``Instruction: Sell``).
PUMPSWAP_CREATE_POOL_INSTRUCTION_NAME: str = "CreatePool"
PUMPSWAP_CREATE_POOL_INSTRUCTION_LOG: str = (
    "Program log: Instruction: CreatePool"
)


# The IDL-pinned account positions of the ``create_pool`` instruction. The Pump AMM
# ``create_pool`` account list (vendored IDL, pinned byte-for-byte by
# ``test_stage_29_5_7_vendored_idl.py``) places the new ``pool`` account at index
# 0, the ``base_mint`` (the migrated token) at index 3, and the ``quote_mint``
# (wrapped-SOL / USDC) at index 4. Helius JSON ``accountKeys`` are ALREADY base58
# strings, so reading these account positions needs no accountKey decode -- the
# authoritative, unambiguous quartet source for a ``create_pool`` migration (the
# create_pool instruction itself is identified by its decoded ``data``
# discriminator; a token-balance owner-grouping would be ambiguous because the
# migration creator AND the pool PDA both hold the base + quote token accounts).
CREATE_POOL_ACCOUNT_INDEX_POOL: int = 0
CREATE_POOL_ACCOUNT_INDEX_BASE_MINT: int = 3
CREATE_POOL_ACCOUNT_INDEX_QUOTE_MINT: int = 4
CREATE_POOL_MIN_ACCOUNT_COUNT: int = 5


# The marker fragment a PumpSwap program invocation log line carries
# (``Program <PUMPSWAP_PROGRAM_ID> invoke [<depth>]``). The normalizer builds the
# full ``Program <id> invoke`` prefix from the imported PumpSwap program id at
# call time (this module imports no program-id constant to stay a pure model
# leaf; the normalizer owns the program-id-bearing marker construction).
PUMPSWAP_PROGRAM_INVOKE_LOG_FRAGMENT: str = "invoke"


# ---------------------------------------------------------------------------
# Closed-set: normalization outcome
# ---------------------------------------------------------------------------


NORMALIZATION_OUTCOME_MIGRATION_PROVEN: str = "MIGRATION_PROVEN"
NORMALIZATION_OUTCOME_NO_MIGRATION_EVIDENCE: str = (
    "NO_MIGRATION_EVIDENCE"
)

STAGE29_5_7_NORMALIZATION_OUTCOME_VALUES: Tuple[str, ...] = (
    NORMALIZATION_OUTCOME_MIGRATION_PROVEN,
    NORMALIZATION_OUTCOME_NO_MIGRATION_EVIDENCE,
)


def is_stage29_5_7_normalization_outcome_value(value: object) -> bool:
    """Return ``True`` iff ``value`` is a closed-set normalization outcome.

    Pure / total; never raises.
    """
    return (
        isinstance(value, str)
        and value in STAGE29_5_7_NORMALIZATION_OUTCOME_VALUES
    )


# ---------------------------------------------------------------------------
# Closed-set: reject reason (the FIRST failing check's precise fail-closed cause)
# ---------------------------------------------------------------------------
#
# A non-migration / malformed / partial envelope fails closed with EXACTLY one of
# these reasons -- never collapsed into a silent unknown, never fabricated into a
# PRESENT record. ``REJECT_REASON_NONE`` accompanies the only ``MIGRATION_PROVEN``
# outcome.


REJECT_REASON_NONE: str = "NONE"
REJECT_REASON_MALFORMED_PAYLOAD: str = "MALFORMED_PAYLOAD"
REJECT_REASON_NOT_A_TRANSACTION_ENVELOPE: str = (
    "NOT_A_TRANSACTION_ENVELOPE"
)
REJECT_REASON_TRANSACTION_FAILED: str = "TRANSACTION_FAILED"
REJECT_REASON_VOTE_TRANSACTION: str = "VOTE_TRANSACTION"
REJECT_REASON_PUMPSWAP_PROGRAM_NOT_INVOKED: str = (
    "PUMPSWAP_PROGRAM_NOT_INVOKED"
)
REJECT_REASON_NO_CREATE_POOL_INSTRUCTION: str = (
    "NO_CREATE_POOL_INSTRUCTION"
)
REJECT_REASON_POOL_QUARTET_UNRESOLVED: str = (
    "POOL_QUARTET_UNRESOLVED"
)
REJECT_REASON_MISSING_SIGNATURE: str = "MISSING_SIGNATURE"
REJECT_REASON_MISSING_SLOT: str = "MISSING_SLOT"
REJECT_REASON_MISSING_BLOCK_TIME: str = "MISSING_BLOCK_TIME"
REJECT_REASON_MALFORMED_OBSERVED_AT: str = (
    "MALFORMED_OBSERVED_AT"
)
REJECT_REASON_UNSAFE_AXIS_SHAPE: str = "UNSAFE_AXIS_SHAPE"

STAGE29_5_7_REJECT_REASON_VALUES: Tuple[str, ...] = (
    REJECT_REASON_NONE,
    REJECT_REASON_MALFORMED_PAYLOAD,
    REJECT_REASON_NOT_A_TRANSACTION_ENVELOPE,
    REJECT_REASON_TRANSACTION_FAILED,
    REJECT_REASON_VOTE_TRANSACTION,
    REJECT_REASON_PUMPSWAP_PROGRAM_NOT_INVOKED,
    REJECT_REASON_NO_CREATE_POOL_INSTRUCTION,
    REJECT_REASON_POOL_QUARTET_UNRESOLVED,
    REJECT_REASON_MISSING_SIGNATURE,
    REJECT_REASON_MISSING_SLOT,
    REJECT_REASON_MISSING_BLOCK_TIME,
    REJECT_REASON_MALFORMED_OBSERVED_AT,
    REJECT_REASON_UNSAFE_AXIS_SHAPE,
)


# Every reject reason except the single proven reason. No fail-closed reason ever
# accompanies a ``MIGRATION_PROVEN`` outcome.
STAGE29_5_7_FAIL_CLOSED_REJECT_REASONS: Tuple[str, ...] = (
    REJECT_REASON_MALFORMED_PAYLOAD,
    REJECT_REASON_NOT_A_TRANSACTION_ENVELOPE,
    REJECT_REASON_TRANSACTION_FAILED,
    REJECT_REASON_VOTE_TRANSACTION,
    REJECT_REASON_PUMPSWAP_PROGRAM_NOT_INVOKED,
    REJECT_REASON_NO_CREATE_POOL_INSTRUCTION,
    REJECT_REASON_POOL_QUARTET_UNRESOLVED,
    REJECT_REASON_MISSING_SIGNATURE,
    REJECT_REASON_MISSING_SLOT,
    REJECT_REASON_MISSING_BLOCK_TIME,
    REJECT_REASON_MALFORMED_OBSERVED_AT,
    REJECT_REASON_UNSAFE_AXIS_SHAPE,
)


def is_stage29_5_7_reject_reason_value(value: object) -> bool:
    """Return ``True`` iff ``value`` is a closed-set reject reason.

    Pure / total; never raises.
    """
    return (
        isinstance(value, str)
        and value in STAGE29_5_7_REJECT_REASON_VALUES
    )


# ---------------------------------------------------------------------------
# Sanitized-output vocabulary mirrored BY VALUE (the COMPLETE / SAFE / no-warnings
# values the producer's projection stamps onto a proven summary)
# ---------------------------------------------------------------------------
#
# These equal the Stage 29.5 ``MEASUREMENT_STATUS_COMPLETE`` /
# ``REDACTION_STATUS_SAFE`` tokens the Stage 30.11.8 confirmation REQUIRES (and the
# Stage 30.5.3 bridge maps ``COMPLETE`` -> ``Known``). They are mirrored here as
# plain literals so the producer's projection (this slice) never needs the Stage 30
# modules, and an unrecognized downstream rename is caught by the composition test.
# A proven on-chain ``create_pool`` migration is a COMPLETE migration measurement
# (the migration definitively occurred); the ATH dimension is judged SEPARATELY and
# LATER by the Stage 30.11.7 enrichment, so ``COMPLETE`` here means "on-chain
# migration complete", NOT "post-migration ATH verified".
STAGE29_5_7_MEASUREMENT_STATUS_COMPLETE: str = "COMPLETE"
STAGE29_5_7_REDACTION_STATUS_SAFE: str = "SAFE"


# ---------------------------------------------------------------------------
# Pure safe-shape helpers
# ---------------------------------------------------------------------------


def is_nonblank_str(value: object) -> bool:
    """Return ``True`` iff ``value`` is a non-empty, non-blank string.

    Pure / total; never raises. Mirrors the Stage 30.11.x non-blank check BY
    VALUE; the normalizer consults it to validate the transaction signature and
    each extracted axis string.
    """
    return isinstance(value, str) and value.strip() != ""


def is_nonneg_int(value: object) -> bool:
    """Return ``True`` iff ``value`` is a non-negative ``int`` that is NOT a
    ``bool``.

    Pure / total; never raises. A ``bool`` (``True`` / ``False``) is rejected up
    front so a stray flag never coerces to ``1`` / ``0`` slot / blockTime.
    """
    return (
        isinstance(value, int)
        and not isinstance(value, bool)
        and value >= 0
    )


def epoch_seconds_to_trailing_z_utc(epoch_seconds: object) -> Optional[str]:
    """Convert a non-negative integer ``epoch_seconds`` (Unix UTC seconds, e.g.
    a Solana transaction ``blockTime``) into a strict trailing-``Z`` ISO-8601 UTC
    timestamp string (``YYYY-MM-DDTHH:MM:SSZ``), or ``None`` if it cannot.

    Pure / total; never raises. NO ``datetime`` / ``time`` import and NO
    wall-clock read -- the civil date is derived from the day count by pure
    integer arithmetic (Howard Hinnant's ``civil_from_days`` algorithm). The
    output is ALWAYS trailing-``Z`` and NEVER the ``+00:00`` offset form, so the
    Stage 30.11.8 confirmation's UTC-``Z``-only anchor check accepts it directly.

    A ``bool``, a non-``int``, or a negative value fails closed to ``None`` (the
    normalizer then rejects the envelope with ``MISSING_BLOCK_TIME``). The
    formatter does not bound the upper range (any non-negative epoch maps to a
    real civil date); a malformed / missing blockTime is the only fail path.
    """
    if not is_nonneg_int(epoch_seconds):
        return None
    # ``epoch_seconds`` is a non-negative int past the guard above.
    total_seconds = int(epoch_seconds)
    days, rem = divmod(total_seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, seconds = divmod(rem, 60)
    # civil_from_days (Hinnant): days are >= 0 here, so the era arithmetic stays
    # in the well-defined non-negative branch.
    z = days + 719468
    era = z // 146097
    doe = z - era * 146097  # [0, 146096]
    yoe = (doe - doe // 1460 + doe // 36524 - doe // 146096) // 365  # [0, 399]
    year = yoe + era * 400
    doy = doe - (365 * yoe + yoe // 4 - yoe // 100)  # [0, 365]
    mp = (5 * doy + 2) // 153  # [0, 11]
    day = doy - (153 * mp + 2) // 5 + 1  # [1, 31]
    month = mp + 3 if mp < 10 else mp - 9  # [1, 12]
    if month <= 2:
        year += 1
    return (
        f"{year:04d}-{month:02d}-{day:02d}"
        f"T{hours:02d}:{minutes:02d}:{seconds:02d}Z"
    )


def is_trailing_z_utc_shape(value: object) -> bool:
    """Return ``True`` iff ``value`` is a strict trailing-``Z`` ISO-8601 UTC
    timestamp of the exact shape ``YYYY-MM-DDTHH:MM:SS[.ffffff]Z`` with real
    calendar / clock fields.

    Pure / total; never raises. NO ``re`` / ``datetime`` import -- the check is a
    manual character + range scan, mirroring the Stage 30.11.8 confirmation's
    Z-only anchor discipline (UTC ``Z`` only; the ``+00:00`` offset form is
    REJECTED). The producer's anchor formatter always emits this exact shape; this
    predicate lets the projection / tests assert the anchor never drifted to a
    ``+00:00`` form.
    """
    if not isinstance(value, str):
        return False
    text = value
    if not text.endswith("Z"):
        return False
    core = text[:-1]
    # Optional fractional-seconds suffix.
    if "." in core:
        core, frac = core.split(".", 1)
        if not frac or not frac.isdigit() or len(frac) > 9:
            return False
    # Expect exactly ``YYYY-MM-DDTHH:MM:SS``.
    if len(core) != 19:
        return False
    if core[4] != "-" or core[7] != "-" or core[10] != "T":
        return False
    if core[13] != ":" or core[16] != ":":
        return False
    digits = (
        core[0:4]
        + core[5:7]
        + core[8:10]
        + core[11:13]
        + core[14:16]
        + core[17:19]
    )
    if not digits.isdigit():
        return False
    year = int(core[0:4])
    month = int(core[5:7])
    day = int(core[8:10])
    hour = int(core[11:13])
    minute = int(core[14:16])
    second = int(core[17:19])
    if not 1 <= month <= 12:
        return False
    if not 0 <= hour <= 23:
        return False
    if not 0 <= minute <= 59:
        return False
    if not 0 <= second <= 59:
        return False
    days_in_month = _days_in_month(year, month)
    return 1 <= day <= days_in_month


def _is_leap_year(year: int) -> bool:
    """Return ``True`` iff ``year`` is a Gregorian leap year. Pure / total."""
    return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)


def _days_in_month(year: int, month: int) -> int:
    """Return the day count of ``month`` (1..12, assumed range-checked) of
    ``year``. Pure / total.
    """
    if month == 2:
        return 29 if _is_leap_year(year) else 28
    if month in (4, 6, 9, 11):
        return 30
    return 31


def build_source_ref(signature: str, slot: int) -> str:
    """Build the safe-shape provenance ``source_ref`` for a proven migration from
    its transaction ``signature`` + ``slot``.

    Pure / total. The ref carries only public on-chain identifiers (a transaction
    signature + a slot number); it NEVER carries an endpoint URL, an API key, a
    webhook, or any secret. Shape: ``helius:sig:<signature>:slot:<slot>``.
    """
    return f"helius:sig:{signature}:slot:{slot}"


# ---------------------------------------------------------------------------
# Sanitized per-mint migration-evidence summary (Stage 30.11.9 shape BY VALUE)
# ---------------------------------------------------------------------------
#
# The producer's projection TARGET. Its field NAMES equal the Stage 30.11.9
# ``Stage30_11_9MigrationEvidenceRecord`` / Stage 30.11.8 ``Stage30_11_8MigrationEvidence``
# field names BY VALUE, so the committed Stage 30.11.9
# ``build_evidence_record_from_sanitized_projection`` mapper (or the Stage 30.11.8
# confirmation, duck-typed) consumes it without this slice importing any Stage 30
# module. Every field defaults to its FAIL-CLOSED value (all ``None``; ``warnings``
# ``None`` -- the FAIL-CLOSED sentinel for a MISSING / omitted warnings field), so a
# bare summary can never confirm. The producer's projection sets every field
# explicitly for a proven migration (``warnings`` to an explicit ``()``).


@dataclass(frozen=True)
class Stage29_5_7SanitizedMigrationEvidenceSummary:
    """Immutable sanitized per-mint migration-evidence summary.

    The producer projects a PRESENT Stage 29.5 evidence record onto one of these.
    Carries ONLY the safe summary fields the Stage 30.11.8 confirmation consults
    plus the mint it is bound to and the migration anchor it carries. The carrier
    deliberately has NO field for a migration signature, a raw provider payload, a
    host, or any secret -- so a sanitized summary can never smuggle a raw
    identifier downstream (the signature stays on the Stage 29.5 evidence record's
    own ``migration_signature`` axis + folded into the opaque ``source_ref``).

      * ``token_mint``               -- the mint this summary is FOR (the migration
                                        base mint; identity binding). Defaults to
                                        ``None``.
      * ``measurement_status``       -- ``COMPLETE`` for a proven on-chain
                                        migration (the Stage 30.11.8 confirmation
                                        requires it); the producer never promotes /
                                        invents it. Defaults to ``None``.
      * ``migration_event_time_utc`` -- the migration anchor (a strict trailing-``Z``
                                        UTC timestamp derived from the transaction
                                        ``blockTime``), carried VERBATIM (never
                                        reformatted). Defaults to ``None``.
      * ``warnings``                 -- the Stage 29.5 warning-code tuple. A proven
                                        complete migration carries an explicit
                                        ``()``. Defaults to ``None`` (the FAIL-CLOSED
                                        sentinel: a MISSING warnings is malformed
                                        evidence, NOT "no warnings").
      * ``redaction_status``         -- ``SAFE`` (the evidence carries only public
                                        chain data); the producer never invents a
                                        redaction-safe claim from unsafe data.
                                        Defaults to ``None``.
      * ``source_ref``               -- the opaque provenance ref (signature + slot)
                                        carried onto a confirmed resolution, or
                                        ``None``.
    """

    token_mint: Optional[str] = None
    measurement_status: Optional[str] = None
    migration_event_time_utc: Optional[str] = None
    warnings: Optional[Tuple[str, ...]] = None
    redaction_status: Optional[str] = None
    source_ref: Optional[str] = None


# ---------------------------------------------------------------------------
# Normalization result carrier
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Stage29_5_7MigrationNormalizationResult:
    """Immutable result of normalizing ONE raw Helius migration envelope.

    The pure normalizer returns exactly one of these. A proven migration carries
    ``outcome=MIGRATION_PROVEN`` + ``reject_reason=NONE`` + the PRESENT
    :class:`Stage29_5MigrationEvidenceRecord`; any non-migration / malformed /
    partial envelope carries ``outcome=NO_MIGRATION_EVIDENCE`` + a PRECISE
    ``reject_reason`` + ``evidence_record=None`` (fail closed, never fabricated).

      * ``outcome``                  -- one of
                                        ``STAGE29_5_7_NORMALIZATION_OUTCOME_VALUES``.
      * ``reject_reason``            -- ``NONE`` on a proven migration; otherwise
                                        the FIRST failing check's closed-set cause.
      * ``evidence_record``          -- the PRESENT Stage 29.5 evidence record on a
                                        proven migration; ``None`` on a reject.
      * ``pumpswap_instruction_count`` -- diagnostic count of PumpSwap-program
                                        instructions seen (top-level + inner; for
                                        the proof tally, never a secret).
      * ``create_pool_match_count``  -- diagnostic count of PumpSwap instructions
                                        whose OWN ``data`` discriminator IS the
                                        ``create_pool`` discriminator AND whose
                                        account layout matched the ``create_pool``
                                        quartet shape.
    """

    outcome: str
    reject_reason: str
    evidence_record: Optional[Stage29_5MigrationEvidenceRecord]
    pumpswap_instruction_count: int = 0
    create_pool_match_count: int = 0


# ---------------------------------------------------------------------------
# Field-name helpers (pure; read dataclass field names)
# ---------------------------------------------------------------------------


def sanitized_summary_field_names() -> Tuple[str, ...]:
    """Return the sanitized migration-evidence summary field names as a tuple."""
    return tuple(
        f.name
        for f in fields(Stage29_5_7SanitizedMigrationEvidenceSummary)
    )


def normalization_result_field_names() -> Tuple[str, ...]:
    """Return the normalization-result field names as a tuple."""
    return tuple(
        f.name for f in fields(Stage29_5_7MigrationNormalizationResult)
    )


__all__ = (
    # Minor version + schema identity.
    "STAGE29_5_7_MINOR_VERSION",
    "STAGE29_5_7_RAW_MIGRATION_EVIDENCE_SCHEMA_VERSION",
    "STAGE29_5_7_SOURCE_STAGE",
    # IDL-pinned migration-event identity.
    "PUMPSWAP_CREATE_POOL_INSTRUCTION_DISCRIMINATOR",
    "PUMPSWAP_CREATE_POOL_EVENT_DISCRIMINATOR",
    "PUMPSWAP_CREATE_POOL_INSTRUCTION_NAME",
    "PUMPSWAP_CREATE_POOL_INSTRUCTION_LOG",
    "PUMPSWAP_PROGRAM_INVOKE_LOG_FRAGMENT",
    "CREATE_POOL_ACCOUNT_INDEX_POOL",
    "CREATE_POOL_ACCOUNT_INDEX_BASE_MINT",
    "CREATE_POOL_ACCOUNT_INDEX_QUOTE_MINT",
    "CREATE_POOL_MIN_ACCOUNT_COUNT",
    # Normalization outcome vocabulary.
    "NORMALIZATION_OUTCOME_MIGRATION_PROVEN",
    "NORMALIZATION_OUTCOME_NO_MIGRATION_EVIDENCE",
    "STAGE29_5_7_NORMALIZATION_OUTCOME_VALUES",
    "is_stage29_5_7_normalization_outcome_value",
    # Reject-reason vocabulary.
    "REJECT_REASON_NONE",
    "REJECT_REASON_MALFORMED_PAYLOAD",
    "REJECT_REASON_NOT_A_TRANSACTION_ENVELOPE",
    "REJECT_REASON_TRANSACTION_FAILED",
    "REJECT_REASON_VOTE_TRANSACTION",
    "REJECT_REASON_PUMPSWAP_PROGRAM_NOT_INVOKED",
    "REJECT_REASON_NO_CREATE_POOL_INSTRUCTION",
    "REJECT_REASON_POOL_QUARTET_UNRESOLVED",
    "REJECT_REASON_MISSING_SIGNATURE",
    "REJECT_REASON_MISSING_SLOT",
    "REJECT_REASON_MISSING_BLOCK_TIME",
    "REJECT_REASON_MALFORMED_OBSERVED_AT",
    "REJECT_REASON_UNSAFE_AXIS_SHAPE",
    "STAGE29_5_7_REJECT_REASON_VALUES",
    "STAGE29_5_7_FAIL_CLOSED_REJECT_REASONS",
    "is_stage29_5_7_reject_reason_value",
    # Sanitized-output vocabulary (mirrored BY VALUE).
    "STAGE29_5_7_MEASUREMENT_STATUS_COMPLETE",
    "STAGE29_5_7_REDACTION_STATUS_SAFE",
    # Pure helpers.
    "is_nonblank_str",
    "is_nonneg_int",
    "epoch_seconds_to_trailing_z_utc",
    "is_trailing_z_utc_shape",
    "build_source_ref",
    # Models.
    "Stage29_5_7SanitizedMigrationEvidenceSummary",
    "Stage29_5_7MigrationNormalizationResult",
    # Field-name helpers.
    "sanitized_summary_field_names",
    "normalization_result_field_names",
)

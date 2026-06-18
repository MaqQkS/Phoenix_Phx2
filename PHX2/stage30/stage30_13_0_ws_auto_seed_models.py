"""Stage 30.13.0 bounded Helius WS auto-seeding models.

Stage 30.13 ships the committed, OFFLINE, fail-closed AUTO-SEEDER that turns bounded
Helius WS discovery output into automatically seeded candidates for the existing
supervised monitor / watchlist path -- proving that fresh pump-suffix migrated mints
can be discovered and seeded WITHOUT any manual hand-fed input, BEFORE the existing
recheck / fake-send runs. This module is the passive, pure, stdlib-only MODEL layer
for that auto-seeder: the closed-set seed-decision / seed-reason vocabularies, the
pump-suffix discovery predicate, the bounded seed-cap predicate, the per-record seed
outcome, the rolled-up four-count seed summary, and the auto-seed result the sibling
adapter emits.

The four counts this layer carries ARE the discovery ledger the operator asked Build
#24 to record:

  * ``accepted``   -- a PRESENT migration record whose base mint is a safe-shape
                      pump-suffix mint AND whose evidence projects to a COMPLETE
                      sanitized summary (the seed). It is the ONLY decision that yields
                      a seeded summary.
  * ``rejected``   -- a clean, expected decline: a non-PRESENT record
                      (``NOT_PRESENT_MIGRATION``), a PRESENT record whose mint is not a
                      safe-shape pump-suffix mint (``NOT_PUMP_SUFFIX``), or a PRESENT
                      pump-suffix record whose evidence is incomplete so the committed
                      projection returns ``None`` (``INCOMPLETE_EVIDENCE``).
  * ``duplicate``  -- a PRESENT pump-suffix mint already accepted this run (first-wins
                      dedupe; ``DUPLICATE_MINT``). Not re-seeded.
  * ``error``      -- a fail-closed fault: the injected WS discovery raised
                      (``WS_CAPTURE_FAILED`` -- a malformed capture / budget / transport
                      error), or a stream item was not a migration evidence record
                      (``NOT_A_RECORD``). Counted, never crashes the run.

This module is the MODEL layer ONLY. It builds NO result, runs NO seeder, reads NO
record, drives NO discovery, projects NO summary, calls NO transport, sends NO message,
reads NO process environment, opens NO network connection, opens NO database, writes NO
file, parses no clock, and edits NO Stage 29 / Stage 30.11 production file. Stage 30.13
is fake / offline / no-send only: the real read-only Helius WebSocket capture (a
concrete socket transport behind the committed Stage 29.5 transport Protocol), the
real-fed dry-run ceremony, and the controlled capped private send remain a SEPARATE,
explicitly operator-authorized step this slice does not run.

Discipline:

  * Stdlib only (``dataclasses`` / ``typing``).
  * Imports NO PHX2 module (a pure leaf; mirrors the Stage 30.11.2 / 30.11.23 model
    modules). The pump-suffix safe-shape check MIRRORS the committed Stage 29.5
    ``is_safe_mint_or_pool_string`` BY VALUE so the leaf imports no Stage 29 type.
  * No ``os.environ`` / ``os.getenv`` access; no env read.
  * No network, no socket; no database / SQLite, no compression.
  * No live provider, transport-destination, url, host, or request-metadata reference;
    no wallet / signing / trading surface; no public / subscriber routing.
  * No PHX1 import. No Stage 21-29 production import.
  * No ``time`` / ``datetime`` import; timestamps are caller-injected.
  * No module-level Call node (no implicit I/O at import time; the
    ``@dataclass(frozen=True)`` decorators are decorator-list Calls, not body-statement
    Calls).
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from typing import Any, Tuple


# ---------------------------------------------------------------------------
# Minor version + schema identity
# ---------------------------------------------------------------------------


STAGE30_13_0_MINOR_VERSION: str = "30.13.0"


# The Stage 30.13.0 auto-seed result schema version. Names the seed-outcome /
# seed-summary / auto-seed-result shapes; distinct from every earlier Stage 30
# schema version. Mirrored BY VALUE by the Stage 30.13 manifest section; this module
# imports no manifest.
STAGE30_13_0_AUTO_SEED_SCHEMA_VERSION: str = (
    "stage30_13_0_v0_ws_auto_seed"
)


STAGE30_13_0_PURPOSE: str = "bounded helius ws auto-seeding discovery"


# ---------------------------------------------------------------------------
# Pump-suffix discovery predicate
# ---------------------------------------------------------------------------
#
# Build #24 selects fresh pump.fun migrated mints by the literal "pump" base-mint
# suffix (the locked Build #24 criterion -- no migration-age bound). The "migrated"
# dimension comes from the PRESENT migration status the auto-seeder gates on upstream;
# this predicate is a SHAPE + SUFFIX check only.


STAGE30_13_PUMP_MINT_SUFFIX: str = "pump"


# The canonical safe length range for a base58 mint, mirrored BY VALUE from the
# committed Stage 29.5 ``is_safe_mint_or_pool_string`` so this leaf imports no Stage 29
# type. A mint shorter / longer than this is rejected as an obviously truncated /
# too-long blob.
_MIN_SAFE_MINT_LENGTH: int = 32
_MAX_SAFE_MINT_LENGTH: int = 64


def is_pump_suffix_mint(value: object) -> bool:
    """Return ``True`` iff ``value`` is a safe-shape mint string ending in the literal
    pump suffix.

    Pure / TOTAL; never raises. Safe-shape MIRRORS the committed Stage 29.5
    ``is_safe_mint_or_pool_string`` BY VALUE: a printable ``str`` of length 32..64 with
    no whitespace. The suffix check is a plain ``str.endswith`` on
    ``STAGE30_13_PUMP_MINT_SUFFIX``. A non-string, an unsafe-shape string, or a string
    that does not end in the pump suffix fails closed to ``False``. This is a SHAPE +
    SUFFIX gate ONLY -- the "migrated" dimension is the PRESENT migration status the
    auto-seeder gates on separately, and there is no migration-age bound in Build #24.
    """
    if not isinstance(value, str):
        return False
    n = len(value)
    if n < _MIN_SAFE_MINT_LENGTH or n > _MAX_SAFE_MINT_LENGTH:
        return False
    if not value.isprintable():
        return False
    if any(ch.isspace() for ch in value):
        return False
    return value.endswith(STAGE30_13_PUMP_MINT_SUFFIX)


# ---------------------------------------------------------------------------
# Bounded seed-cap predicate
# ---------------------------------------------------------------------------
#
# The auto-seeder seeds AT MOST ``max_seed`` records in a single BOUNDED loop (no
# ``while`` loop, no daemon). The hard cap mirrors the committed Stage 30.11.6
# ``max_harvest <= 10`` / Stage 30.11.23 ``max_summaries <= 10`` ceilings so the seeded
# watchlist can never exceed what the bounded downstream chain is allowed to evaluate.


STAGE30_13_MAX_SEED_HARD_CAP: int = 10
STAGE30_13_DEFAULT_MAX_SEED: int = 10


def is_within_seed_cap(max_seed: object) -> bool:
    """Return ``True`` iff ``max_seed`` is a positive ``int`` within the HARD seed cap
    (``1 <= max_seed <= STAGE30_13_MAX_SEED_HARD_CAP``).

    Pure / TOTAL; never raises. A non-int, a ``bool`` (``True`` / ``False`` are not
    budgets), a non-positive value, or a value above the hard cap fails closed to
    ``False`` -- so a run can never be parameterized to seed more candidates than the
    bounded downstream chain allows.
    """
    if isinstance(max_seed, bool):
        return False
    if not isinstance(max_seed, int):
        return False
    return 1 <= max_seed <= STAGE30_13_MAX_SEED_HARD_CAP


# ---------------------------------------------------------------------------
# Closed-set: per-record seed decision
# ---------------------------------------------------------------------------
#
# Exactly one decision per recorded outcome. ``ACCEPTED`` is the ONLY decision that
# yields a seeded summary. Mirrored BY VALUE by the Stage 30.13 manifest.


SEED_DECISION_ACCEPTED: str = "ACCEPTED"
SEED_DECISION_REJECTED: str = "REJECTED"
SEED_DECISION_DUPLICATE: str = "DUPLICATE"
SEED_DECISION_ERROR: str = "ERROR"


STAGE30_13_SEED_DECISIONS: Tuple[str, ...] = (
    SEED_DECISION_ACCEPTED,
    SEED_DECISION_REJECTED,
    SEED_DECISION_DUPLICATE,
    SEED_DECISION_ERROR,
)


# The single decision that yields a seeded summary.
STAGE30_13_SEED_ACCEPT_DECISION: str = SEED_DECISION_ACCEPTED


def is_seed_decision(value: object) -> bool:
    """Return ``True`` iff ``value`` is a closed-set seed decision. Pure / total."""
    return isinstance(value, str) and value in STAGE30_13_SEED_DECISIONS


# ---------------------------------------------------------------------------
# Closed-set: per-record seed reason
# ---------------------------------------------------------------------------
#
# Exactly one reason per seed decision. ``SEEDED_FRESH_PUMP_MIGRATION`` is the only
# reason that accompanies an accepted record. Mirrored BY VALUE by the Stage 30.13
# manifest.


# Accept.
SEED_REASON_SEEDED_FRESH_PUMP_MIGRATION: str = "SEEDED_FRESH_PUMP_MIGRATION"
# Reject.
SEED_REASON_NOT_PRESENT_MIGRATION: str = "NOT_PRESENT_MIGRATION"
SEED_REASON_NOT_PUMP_SUFFIX: str = "NOT_PUMP_SUFFIX"
SEED_REASON_INCOMPLETE_EVIDENCE: str = "INCOMPLETE_EVIDENCE"
# Duplicate.
SEED_REASON_DUPLICATE_MINT: str = "DUPLICATE_MINT"
# Error.
SEED_REASON_WS_CAPTURE_FAILED: str = "WS_CAPTURE_FAILED"
SEED_REASON_NOT_A_RECORD: str = "NOT_A_RECORD"


STAGE30_13_SEED_REASONS: Tuple[str, ...] = (
    SEED_REASON_SEEDED_FRESH_PUMP_MIGRATION,
    SEED_REASON_NOT_PRESENT_MIGRATION,
    SEED_REASON_NOT_PUMP_SUFFIX,
    SEED_REASON_INCOMPLETE_EVIDENCE,
    SEED_REASON_DUPLICATE_MINT,
    SEED_REASON_WS_CAPTURE_FAILED,
    SEED_REASON_NOT_A_RECORD,
)


# The single reason that accompanies the only accept decision.
STAGE30_13_SEED_ACCEPT_REASON: str = SEED_REASON_SEEDED_FRESH_PUMP_MIGRATION


def is_seed_reason(value: object) -> bool:
    """Return ``True`` iff ``value`` is a closed-set seed reason. Pure / total."""
    return isinstance(value, str) and value in STAGE30_13_SEED_REASONS


# ---------------------------------------------------------------------------
# Redaction status tokens + safe placeholder
# ---------------------------------------------------------------------------
#
# The auto-seeder self-scans its own seed-outcome string fields: ``REDACTED`` when
# every field is safe (the normal path -- the seeder builds only closed-set tokens +
# safe-echo mints + injected timestamps), else ``REDACTION_VIOLATION``. A token mint
# that is not a safe-echo token is replaced by ``REDACTED_UNSAFE_ID`` rather than echoed
# raw, so a forged mint can never smuggle injected text into the result. Mirrors the
# committed Stage 30.11.23 redaction discipline BY VALUE.


STAGE30_13_REDACTION_STATUS_REDACTED: str = "REDACTED"
STAGE30_13_REDACTION_STATUS_VIOLATION: str = "REDACTION_VIOLATION"
STAGE30_13_REDACTED_UNSAFE_ID: str = "REDACTED_UNSAFE_ID"


STAGE30_13_REDACTION_STATUSES: Tuple[str, ...] = (
    STAGE30_13_REDACTION_STATUS_REDACTED,
    STAGE30_13_REDACTION_STATUS_VIOLATION,
)


# ---------------------------------------------------------------------------
# Pure safe-shape predicates
# ---------------------------------------------------------------------------


def is_nonblank_str(value: object) -> bool:
    """Return ``True`` iff ``value`` is a non-empty, non-blank string. Pure / total.

    Mirrors the committed Stage 30.11.23 / 30.11.22 non-blank check BY VALUE.
    """
    return isinstance(value, str) and value.strip() != ""


def is_safe_echo_id(value: object) -> bool:
    """Return ``True`` iff ``value`` is a safe-to-echo opaque token.

    A safe-echo token is a non-empty string of length 1..128 made ONLY of ASCII
    letters / digits / ``_`` / ``-``. A base58 token mint and an underscore candidate
    id both pass; any newline / control char / whitespace / path / url / quote / scheme
    character (or an over-long value) fails. It gates the token mints the auto-seeder
    echoes into its redaction-safe seed outcomes -- an unsafe value is replaced by
    ``STAGE30_13_REDACTED_UNSAFE_ID`` rather than echoed raw. Mirrors the committed
    Stage 30.11.23 / 30.11.22 ``is_safe_echo_id`` BY VALUE. Pure / total; never raises.
    """
    if not isinstance(value, str):
        return False
    if value == "" or len(value) > 128:
        return False
    for ch in value:
        if "A" <= ch <= "Z":
            continue
        if "a" <= ch <= "z":
            continue
        if "0" <= ch <= "9":
            continue
        if ch == "_" or ch == "-":
            continue
        return False
    return True


# ---------------------------------------------------------------------------
# Immutable model: one per-record seed outcome
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Stage30_13SeedOutcome:
    """Immutable redaction-safe per-record seed outcome.

    The auto-seeder emits exactly one of these per classified discovery record (plus one
    batch-level ``ERROR`` outcome when the injected WS discovery raised). It pins the
    closed-set ``seed_decision`` + ``seed_reason`` and the safe-echo token mint; it
    carries ONLY safe scalars + a closed-set token: NO migration anchor, NO
    measurement / redaction value, NO magnitude, body, url, exception text, or secret.

      * ``token_mint``     -- echoed safe-shape base mint (``""`` when unreadable;
                              ``REDACTED_UNSAFE_ID`` when present but not a safe-echo
                              token; ``""`` for a batch-level WS-capture error).
      * ``seed_decision``  -- one of ``STAGE30_13_SEED_DECISIONS``.
      * ``seed_reason``    -- one of ``STAGE30_13_SEED_REASONS``.
      * ``created_at_utc`` -- caller-injected ISO-8601 UTC timestamp; NEVER a
                              wall-clock read.
    """

    token_mint: str
    seed_decision: str
    seed_reason: str
    created_at_utc: str


# ---------------------------------------------------------------------------
# Immutable model: rolled-up four-count seed summary
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Stage30_13SeedSummary:
    """Immutable rolled-up Stage 30.13 four-count seed summary.

    A passive tally of one bounded auto-seed pass -- the discovery ledger Build #24
    records. It proves, by counting, that ONLY a PRESENT pump-suffix record with
    complete evidence became a seed, that every non-PRESENT / non-pump / incomplete
    record was declined cleanly, that a repeat mint was deduped, and that a malformed
    capture / WS error / non-record failed closed to an error rather than crashing the
    run. Carries only non-negative integer counts + a caller-injected timestamp.

      * ``records_seen`` -- migration evidence records pulled from the batch and
                            classified (0 when the batch raised before yielding any
                            record). EXCLUDES a batch-level ``WS_CAPTURE_FAILED`` error,
                            which is recorded as an outcome but is not a "seen record".
      * ``accepted``     -- records seeded (the only decision that yields a summary).
      * ``rejected``     -- records declined (``NOT_PRESENT_MIGRATION`` /
                            ``NOT_PUMP_SUFFIX`` / ``INCOMPLETE_EVIDENCE``).
      * ``duplicate``    -- pump-suffix mints already accepted this run.
      * ``error``        -- fail-closed faults (``WS_CAPTURE_FAILED`` +
                            ``NOT_A_RECORD``).
      * ``created_at_utc`` -- caller-injected ISO-8601 UTC timestamp.

    Invariant the auto-seeder maintains:
    ``len(outcomes) == accepted + rejected + duplicate + error`` and
    ``records_seen == accepted + rejected + duplicate + (NOT_A_RECORD count)``.
    """

    records_seen: int
    accepted: int
    rejected: int
    duplicate: int
    error: int
    created_at_utc: str


# ---------------------------------------------------------------------------
# Immutable model: the auto-seed result
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Stage30_13AutoSeedResult:
    """Immutable Stage 30.13 auto-seed result.

    The auto-seeder emits exactly one of these per bounded pass. It carries the ordered
    per-record seed outcomes, the seeded sanitized summaries (the seeded watchlist --
    the ACCEPTED records' committed Stage 29.5.7 sanitized summaries, ready for the
    existing Stage 30.11.23 -> 30.11.22 chain), the rolled-up four-count summary, and a
    combined redaction status. Carries no secret, no magnitude, no body, no url, no
    transport destination.

      * ``outcomes``          -- the ordered per-record seed outcomes.
      * ``seeded_summaries``  -- the ACCEPTED records' sanitized summaries (the seeded
                                 watchlist; ``Stage29_5_7SanitizedMigrationEvidenceSummary``
                                 instances, typed ``Any`` so this leaf imports no Stage
                                 29 type).
      * ``summary``           -- the embedded ``Stage30_13SeedSummary``.
      * ``redaction_status``  -- one of ``STAGE30_13_REDACTION_STATUSES`` (``REDACTED``
                                 iff every seed-outcome string field is safe).
      * ``created_at_utc``    -- caller-injected ISO-8601 UTC timestamp.
    """

    outcomes: Tuple[Stage30_13SeedOutcome, ...]
    seeded_summaries: Tuple[Any, ...]
    summary: Stage30_13SeedSummary
    redaction_status: str
    created_at_utc: str


# ---------------------------------------------------------------------------
# Field-name helpers (pure; read dataclass field names)
# ---------------------------------------------------------------------------


def seed_outcome_field_names() -> Tuple[str, ...]:
    """Return the seed-outcome field names as a tuple."""
    return tuple(f.name for f in fields(Stage30_13SeedOutcome))


def seed_summary_field_names() -> Tuple[str, ...]:
    """Return the seed-summary field names as a tuple."""
    return tuple(f.name for f in fields(Stage30_13SeedSummary))


def auto_seed_result_field_names() -> Tuple[str, ...]:
    """Return the auto-seed-result field names as a tuple."""
    return tuple(f.name for f in fields(Stage30_13AutoSeedResult))


__all__ = (
    # Minor version + schema identity + purpose.
    "STAGE30_13_0_MINOR_VERSION",
    "STAGE30_13_0_AUTO_SEED_SCHEMA_VERSION",
    "STAGE30_13_0_PURPOSE",
    # Pump-suffix predicate.
    "STAGE30_13_PUMP_MINT_SUFFIX",
    "is_pump_suffix_mint",
    # Seed-cap predicate.
    "STAGE30_13_MAX_SEED_HARD_CAP",
    "STAGE30_13_DEFAULT_MAX_SEED",
    "is_within_seed_cap",
    # Seed decisions.
    "SEED_DECISION_ACCEPTED",
    "SEED_DECISION_REJECTED",
    "SEED_DECISION_DUPLICATE",
    "SEED_DECISION_ERROR",
    "STAGE30_13_SEED_DECISIONS",
    "STAGE30_13_SEED_ACCEPT_DECISION",
    "is_seed_decision",
    # Seed reasons.
    "SEED_REASON_SEEDED_FRESH_PUMP_MIGRATION",
    "SEED_REASON_NOT_PRESENT_MIGRATION",
    "SEED_REASON_NOT_PUMP_SUFFIX",
    "SEED_REASON_INCOMPLETE_EVIDENCE",
    "SEED_REASON_DUPLICATE_MINT",
    "SEED_REASON_WS_CAPTURE_FAILED",
    "SEED_REASON_NOT_A_RECORD",
    "STAGE30_13_SEED_REASONS",
    "STAGE30_13_SEED_ACCEPT_REASON",
    "is_seed_reason",
    # Redaction.
    "STAGE30_13_REDACTION_STATUS_REDACTED",
    "STAGE30_13_REDACTION_STATUS_VIOLATION",
    "STAGE30_13_REDACTED_UNSAFE_ID",
    "STAGE30_13_REDACTION_STATUSES",
    # Safe-shape predicates.
    "is_nonblank_str",
    "is_safe_echo_id",
    # Models.
    "Stage30_13SeedOutcome",
    "Stage30_13SeedSummary",
    "Stage30_13AutoSeedResult",
    # Field-name helpers.
    "seed_outcome_field_names",
    "seed_summary_field_names",
    "auto_seed_result_field_names",
)

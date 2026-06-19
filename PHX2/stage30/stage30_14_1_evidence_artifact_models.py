"""Stage 30.14.1 evidence-artifact loader + replay-verifier MODELS.

Build #26, substage 30.14.1. The passive, pure, stdlib-only MODEL layer for the Build
26.1C OFFLINE evidence-artifact loader + replay verifier: the slice that loads a persisted
``build26_capture_evidence.jsonl`` artifact (SYNTHETIC fixtures only in this slice; a real
Build 26.1B capture is deferred and never copied into the repo), validates the locked
15-field Build 26.1 capture-evidence schema, reconstructs a
``Stage29_5MigrationEvidenceRecord`` WITHOUT fabrication, and replays each reconstructed
record through the committed Stage 30.14.0 replay -> shadow-dispatch path to a RECORDED
would-send (a FAKE dispatch), NEVER a real send.

This module is the MODEL layer ONLY: the minor / schema / purpose identity, the locked
Build 26.1 required-field list, the locked load / replay caps (max bytes / lines / accepted
records / replay records), the closed-set load-decision / load-reason / load-error /
verify-error vocabularies, the closed-set redaction vocabulary + safe placeholder, the pure
safe-shape predicates (the pump-suffix discovery predicate + the safe-echo predicate, both
mirrored BY VALUE from the committed sources -- a pin test cross-checks them), the
provenance ``source_ref`` builder (mirrored BY VALUE from the committed Stage 29.5.7
``build_source_ref``), the pure redaction self-scan, the immutable per-line load OUTCOME,
the rolled-up load SUMMARY, the persisted-attestation carrier, the immutable load RESULT,
the immutable per-record replay-verify OUTCOME, and the immutable replay-verify RESULT
carrier. It builds NO result, loads NO file, reconstructs NO record, drives NO discovery,
runs NO recheck, calls NO transport, sends NO message, reads NO env, opens NO network,
opens NO database, writes NO file, and parses no clock.

Discipline:

  * Stdlib only (``dataclasses`` / ``typing``).
  * Imports NO PHX2 module (a pure leaf; mirrors the Stage 30.13.0 / 30.14.0 model
    modules). The pump-suffix safe-shape check MIRRORS the committed Stage 30.13.0
    ``is_pump_suffix_mint`` BY VALUE and the ``source_ref`` builder MIRRORS the committed
    Stage 29.5.7 ``build_source_ref`` BY VALUE, so this leaf imports no Stage 29 / Stage 30
    type; a pin test cross-checks both. The reconstructed record + composed committed result
    objects are carried duck-typed as ``Any`` -- no committed result type is imported here.
  * No ``os.environ`` / ``os.getenv`` access; no env read.
  * No network, no socket; no database / SQLite, no compression; no filesystem surface.
  * No live provider, transport-destination, url, host, or request-metadata reference; no
    wallet / signing / trading surface; no public / subscriber routing.
  * No PHX1 import. No Stage 21-29 production import.
  * No ``time`` / ``datetime`` import; timestamps are caller-injected.
  * No module-level Call node (no implicit I/O at import time; the
    ``@dataclass(frozen=True)`` decorators are decorator-list Calls, not body-statement
    Calls; the split-literal needle concatenations use ``+`` BinOps, never Calls).
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from typing import Any, Tuple


# ---------------------------------------------------------------------------
# Minor version + schema identity + purpose
# ---------------------------------------------------------------------------


STAGE30_14_1_MINOR_VERSION: str = "30.14.1"


# The locked Build 26.1 persisted capture-evidence artifact schema version. Names the
# ``build26_capture_evidence.jsonl`` line schema; distinct from the Stage 29.5 evidence
# record schema, the Stage 29.5.7 sanitized-summary schema, and every Stage 30.14.0 schema
# version. The loader gates every record on this exact value (fail closed on a mismatch).
BUILD26_1_CAPTURE_EVIDENCE_SCHEMA_VERSION: str = (
    "build26_1_v0_capture_evidence"
)


# The Stage 30.14.1 replay-verify result schema version. Names the load-result /
# verify-result shapes; mirrored BY VALUE by the Stage 30.14.1 manifest.
STAGE30_14_1_VERIFY_SCHEMA_VERSION: str = (
    "stage30_14_1_v0_evidence_load_replay_verify"
)


STAGE30_14_1_PURPOSE: str = (
    "offline evidence-artifact load + synthetic replay to shadow fake dispatch"
)


# ---------------------------------------------------------------------------
# Locked Build 26.1 required-field list (the 15-field capture-evidence schema)
# ---------------------------------------------------------------------------
#
# Every ``build26_capture_evidence.jsonl`` line MUST carry all 15 keys. The first 12 are
# the underlying migration-evidence record axes (the loader reconstructs a
# ``Stage29_5MigrationEvidenceRecord`` from them); the last 3 (``measurement_status`` /
# ``redaction_status`` / ``warnings``) are the persisted sanitized-summary attestation the
# loader validates and the verifier round-trips against the committed re-derived summary.


BUILD26_1_REQUIRED_FIELDS: Tuple[str, ...] = (
    "schema_version",
    "token_mint",
    "migration_status",
    "migration_source",
    "pool_account",
    "pool_program_id",
    "quote_mint",
    "migration_event_time_utc",
    "migration_slot",
    "migration_signature",
    "source_ref",
    "observed_at_utc",
    "measurement_status",
    "redaction_status",
    "warnings",
)


# ---------------------------------------------------------------------------
# Locked Build 26.1C caps
# ---------------------------------------------------------------------------
#
# Every cap fails CLOSED when exceeded -- the loader / verifier refuses with a closed-set
# reason, never silently truncates. The byte cap is checked against the file size BEFORE the
# file is read into memory.


STAGE30_14_1_DEFAULT_MAX_BYTES: int = 1_048_576       # 1 MiB
STAGE30_14_1_HARD_MAX_BYTES: int = 8_388_608          # 8 MiB
STAGE30_14_1_DEFAULT_MAX_LINES: int = 128
STAGE30_14_1_HARD_MAX_LINES: int = 4096
STAGE30_14_1_DEFAULT_MAX_ACCEPTED: int = 64
STAGE30_14_1_HARD_MAX_ACCEPTED: int = 256
STAGE30_14_1_DEFAULT_MAX_REPLAY: int = 8
STAGE30_14_1_HARD_MAX_REPLAY: int = 64


def _is_pos_int_within(value: object, hard_max: int) -> bool:
    """Return ``True`` iff ``value`` is a positive ``int`` (not ``bool``) within
    ``[1, hard_max]``. Pure / TOTAL; never raises.
    """
    if isinstance(value, bool):
        return False
    if not isinstance(value, int):
        return False
    return 1 <= value <= hard_max


def is_within_byte_cap(value: object) -> bool:
    """Return ``True`` iff ``value`` is a valid byte cap (``1..HARD_MAX_BYTES``)."""
    return _is_pos_int_within(value, STAGE30_14_1_HARD_MAX_BYTES)


def is_within_line_cap(value: object) -> bool:
    """Return ``True`` iff ``value`` is a valid line cap (``1..HARD_MAX_LINES``)."""
    return _is_pos_int_within(value, STAGE30_14_1_HARD_MAX_LINES)


def is_within_accepted_cap(value: object) -> bool:
    """Return ``True`` iff ``value`` is a valid accepted-records cap
    (``1..HARD_MAX_ACCEPTED``)."""
    return _is_pos_int_within(value, STAGE30_14_1_HARD_MAX_ACCEPTED)


def is_within_replay_cap(value: object) -> bool:
    """Return ``True`` iff ``value`` is a valid replay-records cap
    (``1..HARD_MAX_REPLAY``)."""
    return _is_pos_int_within(value, STAGE30_14_1_HARD_MAX_REPLAY)


# ---------------------------------------------------------------------------
# Closed-set: per-line load decision
# ---------------------------------------------------------------------------
#
# Exactly one decision per recorded load outcome. ``ACCEPTED`` is the ONLY decision that
# yields a reconstructed record. A structural fault (unreadable / oversized / too-many /
# malformed-jsonl / wrong-schema) is NOT a per-line decision -- it raises before any line is
# classified.


LOAD_DECISION_ACCEPTED: str = "ACCEPTED"
LOAD_DECISION_REJECTED: str = "REJECTED"


STAGE30_14_1_LOAD_DECISIONS: Tuple[str, ...] = (
    LOAD_DECISION_ACCEPTED,
    LOAD_DECISION_REJECTED,
)


def is_load_decision(value: object) -> bool:
    """Return ``True`` iff ``value`` is a closed-set load decision. Pure / total."""
    return isinstance(value, str) and value in STAGE30_14_1_LOAD_DECISIONS


# ---------------------------------------------------------------------------
# Closed-set: per-line load reason
# ---------------------------------------------------------------------------
#
# Exactly one reason per load decision. ``ACCEPTED_FRESH_EVIDENCE`` is the only reason that
# accompanies an accepted line. The first failing per-line check wins (mirrors the committed
# Stage 29.5.7 normalizer's first-failing-check reason discipline).


# Accept.
LOAD_REASON_ACCEPTED_FRESH_EVIDENCE: str = "ACCEPTED_FRESH_EVIDENCE"
# Reject (content faults).
LOAD_REASON_MISSING_REQUIRED_FIELD: str = "MISSING_REQUIRED_FIELD"
LOAD_REASON_NON_PRESENT_STATUS: str = "NON_PRESENT_STATUS"
LOAD_REASON_INVALID_SOURCE: str = "INVALID_SOURCE"
LOAD_REASON_UNSAFE_AXIS_SHAPE: str = "UNSAFE_AXIS_SHAPE"
LOAD_REASON_NOT_PUMP_SUFFIX: str = "NOT_PUMP_SUFFIX"
LOAD_REASON_MALFORMED_TIMESTAMP: str = "MALFORMED_TIMESTAMP"
LOAD_REASON_BAD_SOURCE_REF: str = "BAD_SOURCE_REF"
LOAD_REASON_INCOMPLETE_MEASUREMENT: str = "INCOMPLETE_MEASUREMENT"
LOAD_REASON_UNSAFE_REDACTION: str = "UNSAFE_REDACTION"
LOAD_REASON_NONEMPTY_WARNINGS: str = "NONEMPTY_WARNINGS"
LOAD_REASON_DUPLICATE_MINT: str = "DUPLICATE_MINT"
LOAD_REASON_DUPLICATE_SIGNATURE: str = "DUPLICATE_SIGNATURE"


STAGE30_14_1_LOAD_REJECT_REASONS: Tuple[str, ...] = (
    LOAD_REASON_MISSING_REQUIRED_FIELD,
    LOAD_REASON_NON_PRESENT_STATUS,
    LOAD_REASON_INVALID_SOURCE,
    LOAD_REASON_UNSAFE_AXIS_SHAPE,
    LOAD_REASON_NOT_PUMP_SUFFIX,
    LOAD_REASON_MALFORMED_TIMESTAMP,
    LOAD_REASON_BAD_SOURCE_REF,
    LOAD_REASON_INCOMPLETE_MEASUREMENT,
    LOAD_REASON_UNSAFE_REDACTION,
    LOAD_REASON_NONEMPTY_WARNINGS,
    LOAD_REASON_DUPLICATE_MINT,
    LOAD_REASON_DUPLICATE_SIGNATURE,
)


STAGE30_14_1_LOAD_REASONS: Tuple[str, ...] = (
    LOAD_REASON_ACCEPTED_FRESH_EVIDENCE,
) + STAGE30_14_1_LOAD_REJECT_REASONS


def is_load_reason(value: object) -> bool:
    """Return ``True`` iff ``value`` is a closed-set load reason. Pure / total."""
    return isinstance(value, str) and value in STAGE30_14_1_LOAD_REASONS


# ---------------------------------------------------------------------------
# Closed-set: structural load-error reasons (the loader RAISES these)
# ---------------------------------------------------------------------------
#
# A structural fault makes the whole artifact untrustworthy: the loader raises a
# ``Stage30_14_1EvidenceLoadError`` carrying one of these tokens BEFORE (or instead of)
# emitting per-line outcomes. A caller-shape cap fault is ``INVALID_CAP``.


LOAD_ERROR_UNREADABLE_ARTIFACT: str = "UNREADABLE_ARTIFACT"
LOAD_ERROR_FILE_TOO_LARGE: str = "FILE_TOO_LARGE"
LOAD_ERROR_TOO_MANY_LINES: str = "TOO_MANY_LINES"
LOAD_ERROR_TOO_MANY_RECORDS: str = "TOO_MANY_RECORDS"
LOAD_ERROR_MALFORMED_JSONL_LINE: str = "MALFORMED_JSONL_LINE"
LOAD_ERROR_WRONG_SCHEMA_VERSION: str = "WRONG_SCHEMA_VERSION"
LOAD_ERROR_INVALID_CAP: str = "INVALID_CAP"


STAGE30_14_1_LOAD_ERROR_REASONS: Tuple[str, ...] = (
    LOAD_ERROR_UNREADABLE_ARTIFACT,
    LOAD_ERROR_FILE_TOO_LARGE,
    LOAD_ERROR_TOO_MANY_LINES,
    LOAD_ERROR_TOO_MANY_RECORDS,
    LOAD_ERROR_MALFORMED_JSONL_LINE,
    LOAD_ERROR_WRONG_SCHEMA_VERSION,
    LOAD_ERROR_INVALID_CAP,
)


def is_load_error_reason(value: object) -> bool:
    """Return ``True`` iff ``value`` is a closed-set structural load-error reason."""
    return (
        isinstance(value, str)
        and value in STAGE30_14_1_LOAD_ERROR_REASONS
    )


# ---------------------------------------------------------------------------
# Closed-set: verify-error reasons (the verifier RAISES these)
# ---------------------------------------------------------------------------


VERIFY_ERROR_NOT_A_LOAD_RESULT: str = "NOT_A_LOAD_RESULT"
VERIFY_ERROR_INVALID_MAX_REPLAY: str = "INVALID_MAX_REPLAY"
VERIFY_ERROR_TOO_MANY_REPLAY_RECORDS: str = "TOO_MANY_REPLAY_RECORDS"


STAGE30_14_1_VERIFY_ERROR_REASONS: Tuple[str, ...] = (
    VERIFY_ERROR_NOT_A_LOAD_RESULT,
    VERIFY_ERROR_INVALID_MAX_REPLAY,
    VERIFY_ERROR_TOO_MANY_REPLAY_RECORDS,
)


def is_verify_error_reason(value: object) -> bool:
    """Return ``True`` iff ``value`` is a closed-set verify-error reason."""
    return (
        isinstance(value, str)
        and value in STAGE30_14_1_VERIFY_ERROR_REASONS
    )


# ---------------------------------------------------------------------------
# Redaction status tokens + safe placeholder
# ---------------------------------------------------------------------------
#
# The loader / verifier self-scan their own emitted string fields: ``REDACTED`` when every
# field is safe (the normal path -- only safe-echo mints + closed-set tokens + injected
# timestamps), else ``REDACTION_VIOLATION``. A token mint that is not a safe-echo token is
# replaced by ``REDACTED_UNSAFE_ID`` rather than echoed raw. Mirrors the committed Stage
# 30.13.0 / 30.14.0 redaction discipline BY VALUE.


STAGE30_14_1_REDACTION_STATUS_REDACTED: str = "REDACTED"
STAGE30_14_1_REDACTION_STATUS_VIOLATION: str = "REDACTION_VIOLATION"
STAGE30_14_1_REDACTED_UNSAFE_ID: str = "REDACTED_UNSAFE_ID"


STAGE30_14_1_REDACTION_STATUSES: Tuple[str, ...] = (
    STAGE30_14_1_REDACTION_STATUS_REDACTED,
    STAGE30_14_1_REDACTION_STATUS_VIOLATION,
)


# ---------------------------------------------------------------------------
# Redaction self-scan needles (split-literal so this module source carries no bare needle
# -- in particular no contiguous transport-scheme separator and no bare provider host).
# Mirrors the committed Stage 30.14.0 orchestrator scan BY VALUE.
# ---------------------------------------------------------------------------


_REDACTION_SCHEME_SEP: str = ":" + "/" + "/"
_REDACTION_NEEDLES: Tuple[str, ...] = (
    "disc" + "ord.com",
    "disc" + "ordapp.com",
    "/web" + "hooks/",
    "web" + "hook url",
    "ap" + "i_key",
    "ap" + "i key",
    "x-api-" + "key",
    "x-" + "token",
    "b" + "earer",
    "author" + "ization",
    "raw" + "_body",
    "response" + "_body",
    "head" + "ers",
)


def are_strings_redaction_safe(values: Tuple[str, ...]) -> bool:
    """Return ``True`` iff no string carries a transport-scheme separator or a forbidden
    url / secret needle. Pure / total; never raises. A non-string entry is skipped.
    """
    for text in values:
        if not isinstance(text, str):
            continue
        lowered = text.lower()
        if _REDACTION_SCHEME_SEP in lowered:
            return False
        for needle in _REDACTION_NEEDLES:
            if needle in lowered:
                return False
    return True


# ---------------------------------------------------------------------------
# Pump-suffix discovery predicate (mirrors the committed Stage 30.13.0 BY VALUE)
# ---------------------------------------------------------------------------
#
# Build #24 selects fresh pump.fun migrated mints by the literal ``pump`` base-mint suffix.
# This leaf mirrors the committed Stage 30.13.0 ``is_pump_suffix_mint`` BY VALUE so the
# loader can pre-reject a non-pump token mint at load time without importing the Stage
# 30.13.0 models; a pin test cross-checks the two agree on a battery of inputs.


STAGE30_14_1_PUMP_MINT_SUFFIX: str = "pump"
_MIN_SAFE_MINT_LENGTH: int = 32
_MAX_SAFE_MINT_LENGTH: int = 64
_BASE58_MINT_ALPHABET: str = (
    "123456789"
    "ABCDEFGHJKLMNPQRSTUVWXYZ"
    "abcdefghijkmnopqrstuvwxyz"
)


def is_base58_mint_string(value: object) -> bool:
    """Return ``True`` iff ``value`` is a non-empty string drawn ENTIRELY from the
    canonical base58 mint alphabet. Pure / TOTAL; never raises. Mirrors the committed Stage
    30.13.0 ``is_base58_mint_string`` BY VALUE.
    """
    if not isinstance(value, str):
        return False
    if value == "":
        return False
    for ch in value:
        if ch not in _BASE58_MINT_ALPHABET:
            return False
    return True


def is_pump_suffix_mint(value: object) -> bool:
    """Return ``True`` iff ``value`` is a safe-shape base58 mint string of length 32..64
    ending in the literal pump suffix. Pure / TOTAL; never raises. Mirrors the committed
    Stage 30.13.0 ``is_pump_suffix_mint`` BY VALUE.
    """
    if not isinstance(value, str):
        return False
    n = len(value)
    if n < _MIN_SAFE_MINT_LENGTH or n > _MAX_SAFE_MINT_LENGTH:
        return False
    if not is_base58_mint_string(value):
        return False
    return value.endswith(STAGE30_14_1_PUMP_MINT_SUFFIX)


# ---------------------------------------------------------------------------
# Provenance source_ref builder (mirrors the committed Stage 29.5.7 BY VALUE)
# ---------------------------------------------------------------------------


def build_expected_source_ref(signature: object, slot: object) -> str:
    """Build the safe-shape provenance ``source_ref`` for a proven migration from its
    transaction ``signature`` + ``slot``.

    Pure / total. Mirrors the committed Stage 29.5.7 ``build_source_ref`` BY VALUE; a pin
    test cross-checks the two agree. The ref carries only public on-chain identifiers (a
    transaction signature + a slot number); it NEVER carries an endpoint URL, an API key, a
    webhook, or any secret. Shape: ``helius:sig:<signature>:slot:<slot>``.
    """
    return f"helius:sig:{signature}:slot:{slot}"


# ---------------------------------------------------------------------------
# Pure safe-shape predicates
# ---------------------------------------------------------------------------


def is_nonblank_str(value: object) -> bool:
    """Return ``True`` iff ``value`` is a non-empty, non-blank string. Pure / total."""
    return isinstance(value, str) and value.strip() != ""


def is_safe_echo_id(value: object) -> bool:
    """Return ``True`` iff ``value`` is a safe-to-echo opaque token.

    A safe-echo token is a non-empty string of length 1..128 made ONLY of ASCII
    letters / digits / ``_`` / ``-``. A base58 token mint passes; any newline / control
    char / whitespace / path / url / quote / scheme character (or an over-long value) fails.
    It gates the token mints the loader / verifier echo into their redaction-safe outcomes.
    Mirrors the committed Stage 30.13.0 / 30.14.0 ``is_safe_echo_id`` BY VALUE. Pure /
    total; never raises.
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


def safe_echo(value: object) -> str:
    """Echo ``value`` only when it is a safe-echo token; else a safe placeholder.

    ``None`` / ``""`` -> ``""``; a non-string or an unsafe string ->
    ``STAGE30_14_1_REDACTED_UNSAFE_ID``; a safe-echo token -> itself. Mirrors the committed
    Stage 30.13.0 / 30.14.0 ``_safe_echo`` BY VALUE. Pure / total.
    """
    if value is None:
        return ""
    if not isinstance(value, str):
        return STAGE30_14_1_REDACTED_UNSAFE_ID
    if value == "":
        return ""
    return (
        value
        if is_safe_echo_id(value)
        else STAGE30_14_1_REDACTED_UNSAFE_ID
    )


# ---------------------------------------------------------------------------
# Immutable model: the persisted sanitized-summary attestation (for round-trip)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Stage30_14_1PersistedAttestation:
    """Immutable carrier of the 6 persisted sanitized-summary attestation fields parsed
    from one ACCEPTED evidence line.

    The verifier round-trips these against the committed re-derived sanitized summary
    (``seed_result.seeded_summaries[0]``) to prove the loader reconstructed the record
    faithfully -- the persisted summary must equal the committed chain's own re-projection.
    A pure carrier; the loader validated every field before constructing it.

      * ``token_mint``               -- the migration base mint (== the record's base mint).
      * ``measurement_status``       -- ``COMPLETE`` (validated by the loader).
      * ``migration_event_time_utc`` -- the migration anchor, carried verbatim.
      * ``warnings``                 -- the warning-code tuple; an accepted record carries
                                        an explicit empty ``()``.
      * ``redaction_status``         -- ``SAFE`` (validated by the loader).
      * ``source_ref``               -- the opaque ``helius:sig:<sig>:slot:<n>`` ref.
    """

    token_mint: str
    measurement_status: str
    migration_event_time_utc: str
    warnings: Tuple[str, ...]
    redaction_status: str
    source_ref: str


# ---------------------------------------------------------------------------
# Immutable model: one per-line load outcome
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Stage30_14_1EvidenceLoadOutcome:
    """Immutable redaction-safe per-line load outcome.

    The loader emits exactly one of these per classified JSONL line. It pins the closed-set
    ``load_decision`` + ``load_reason`` and the safe-echo token mint; it carries ONLY safe
    scalars + closed-set tokens: NO migration anchor, NO measurement / magnitude, NO body,
    url, ``source_ref``, exception text, or secret.

      * ``token_mint``     -- echoed safe-shape token mint (``""`` when unreadable /
                              missing; ``REDACTED_UNSAFE_ID`` when present but not a
                              safe-echo token).
      * ``load_decision``  -- one of ``STAGE30_14_1_LOAD_DECISIONS``.
      * ``load_reason``    -- one of ``STAGE30_14_1_LOAD_REASONS``.
      * ``created_at_utc`` -- caller-injected ISO-8601 UTC timestamp; NEVER a wall-clock
                              read.
    """

    token_mint: str
    load_decision: str
    load_reason: str
    created_at_utc: str


# ---------------------------------------------------------------------------
# Immutable model: rolled-up load summary
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Stage30_14_1EvidenceLoadSummary:
    """Immutable rolled-up Stage 30.14.1 load tally.

    A passive tally of one bounded load pass. Counts only + a caller-injected timestamp.

      * ``lines_seen`` -- non-empty JSONL lines parsed into objects and classified.
      * ``accepted``   -- lines reconstructed into a record (the only accept decision).
      * ``rejected``   -- lines declined on a content fault (excludes duplicates).
      * ``duplicate``  -- lines declined as a repeat mint / signature.
      * ``created_at_utc`` -- caller-injected ISO-8601 UTC timestamp.

    Invariant the loader maintains: ``lines_seen == accepted + rejected + duplicate``.
    """

    lines_seen: int
    accepted: int
    rejected: int
    duplicate: int
    created_at_utc: str


# ---------------------------------------------------------------------------
# Immutable model: the load result
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Stage30_14_1EvidenceLoadResult:
    """Immutable Stage 30.14.1 evidence load result.

    The loader emits exactly one of these per bounded pass. It carries the ordered per-line
    outcomes, the reconstructed evidence records (the accepted set, ready for the committed
    Stage 30.14.0 replay path), the aligned persisted attestations (for the verifier's
    round-trip check), the rolled-up summary, and a combined redaction status. Carries no
    secret, no magnitude, no body, no url, no transport destination.

      * ``outcomes``               -- the ordered per-line load outcomes.
      * ``accepted_records``       -- the reconstructed ``Stage29_5MigrationEvidenceRecord``
                                      instances (typed ``Any`` so this leaf imports no Stage
                                      29 type).
      * ``accepted_attestations``  -- the persisted attestations, index-aligned with
                                      ``accepted_records``.
      * ``summary``                -- the embedded ``Stage30_14_1EvidenceLoadSummary``.
      * ``redaction_status``       -- one of ``STAGE30_14_1_REDACTION_STATUSES``.
      * ``created_at_utc``         -- caller-injected ISO-8601 UTC timestamp.
    """

    outcomes: Tuple[Stage30_14_1EvidenceLoadOutcome, ...]
    accepted_records: Tuple[Any, ...]
    accepted_attestations: Tuple[Stage30_14_1PersistedAttestation, ...]
    summary: Stage30_14_1EvidenceLoadSummary
    redaction_status: str
    created_at_utc: str


# ---------------------------------------------------------------------------
# Immutable model: one per-record replay-verify outcome
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Stage30_14_1ReplayVerifyOutcome:
    """Immutable redaction-safe per-record replay-verify outcome.

    The verifier emits exactly one of these per replayed accepted record, distilled from the
    committed Stage 30.14.0 dispatch trace + the persisted-attestation round-trip check. It
    carries ONLY safe scalars + a safe-echo mint: NO migration anchor, NO magnitude, body,
    url, ``source_ref``, or secret.

      * ``token_mint``              -- the discovered + dispatched safe-echo mint.
      * ``seeds_accepted``         -- committed auto-seeder ``accepted`` (1 on the happy
                                      path).
      * ``dispatched``             -- committed recorded would-sends (1 on the happy path).
      * ``would_send_recorded``    -- FAKE client recorded would-send tally (== dispatched).
      * ``mint_traces_through``    -- the discovered mint equals the dispatched mint.
      * ``real_send_performed``    -- pinned ``False`` by the committed chain.
      * ``real_send_guard_invoked``-- pinned ``False`` (no Stage 30.11.16 guard import).
      * ``attestation_roundtrip_ok`` -- the committed re-derived summary equals the
                                      persisted attestation (faithful reconstruction).
      * ``redaction_status``       -- one of ``STAGE30_14_1_REDACTION_STATUSES``.
    """

    token_mint: str
    seeds_accepted: int
    dispatched: int
    would_send_recorded: int
    mint_traces_through: bool
    real_send_performed: bool
    real_send_guard_invoked: bool
    attestation_roundtrip_ok: bool
    redaction_status: str


# ---------------------------------------------------------------------------
# Immutable model: the replay-verify result
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Stage30_14_1ReplayVerifyResult:
    """Immutable Stage 30.14.1 replay-verify result.

    The verifier emits exactly one of these per bounded pass. It carries the distilled
    per-record outcomes, the committed Stage 30.14.0 shadow-dispatch results (duck-typed
    ``Any``), the aggregate counters / flags, a combined redaction status, and the injected
    timestamp. Carries no secret, no magnitude, no body, no url, no transport destination.

      * ``outcomes``           -- the distilled per-record verify outcomes.
      * ``shadow_results``     -- the committed ``Stage30_14ShadowDispatchResult`` objects
                                  (typed ``Any`` so this leaf imports no Stage 30.14.0 type).
      * ``records_replayed``   -- the number of records driven through the committed path.
      * ``dispatched_total``   -- the summed recorded would-sends (NEVER real sends).
      * ``all_traced_through`` -- every replayed record's mint traced end-to-end.
      * ``all_no_real_send``   -- every record pinned no-real-send + no-guard-invoked.
      * ``all_roundtrip_ok``   -- every record's attestation round-trip held.
      * ``redaction_status``   -- one of ``STAGE30_14_1_REDACTION_STATUSES``.
      * ``created_at_utc``     -- caller-injected ISO-8601 UTC timestamp.
    """

    outcomes: Tuple[Stage30_14_1ReplayVerifyOutcome, ...]
    shadow_results: Tuple[Any, ...]
    records_replayed: int
    dispatched_total: int
    all_traced_through: bool
    all_no_real_send: bool
    all_roundtrip_ok: bool
    redaction_status: str
    created_at_utc: str


# ---------------------------------------------------------------------------
# Field-name helpers (pure; read dataclass field names)
# ---------------------------------------------------------------------------


def persisted_attestation_field_names() -> Tuple[str, ...]:
    """Return the persisted-attestation field names as a tuple."""
    return tuple(f.name for f in fields(Stage30_14_1PersistedAttestation))


def evidence_load_outcome_field_names() -> Tuple[str, ...]:
    """Return the evidence-load-outcome field names as a tuple."""
    return tuple(f.name for f in fields(Stage30_14_1EvidenceLoadOutcome))


def evidence_load_summary_field_names() -> Tuple[str, ...]:
    """Return the evidence-load-summary field names as a tuple."""
    return tuple(f.name for f in fields(Stage30_14_1EvidenceLoadSummary))


def evidence_load_result_field_names() -> Tuple[str, ...]:
    """Return the evidence-load-result field names as a tuple."""
    return tuple(f.name for f in fields(Stage30_14_1EvidenceLoadResult))


def replay_verify_outcome_field_names() -> Tuple[str, ...]:
    """Return the replay-verify-outcome field names as a tuple."""
    return tuple(f.name for f in fields(Stage30_14_1ReplayVerifyOutcome))


def replay_verify_result_field_names() -> Tuple[str, ...]:
    """Return the replay-verify-result field names as a tuple."""
    return tuple(f.name for f in fields(Stage30_14_1ReplayVerifyResult))


__all__ = (
    # Minor version + schema identity + purpose.
    "STAGE30_14_1_MINOR_VERSION",
    "BUILD26_1_CAPTURE_EVIDENCE_SCHEMA_VERSION",
    "STAGE30_14_1_VERIFY_SCHEMA_VERSION",
    "STAGE30_14_1_PURPOSE",
    # Required fields.
    "BUILD26_1_REQUIRED_FIELDS",
    # Caps.
    "STAGE30_14_1_DEFAULT_MAX_BYTES",
    "STAGE30_14_1_HARD_MAX_BYTES",
    "STAGE30_14_1_DEFAULT_MAX_LINES",
    "STAGE30_14_1_HARD_MAX_LINES",
    "STAGE30_14_1_DEFAULT_MAX_ACCEPTED",
    "STAGE30_14_1_HARD_MAX_ACCEPTED",
    "STAGE30_14_1_DEFAULT_MAX_REPLAY",
    "STAGE30_14_1_HARD_MAX_REPLAY",
    "is_within_byte_cap",
    "is_within_line_cap",
    "is_within_accepted_cap",
    "is_within_replay_cap",
    # Load decisions.
    "LOAD_DECISION_ACCEPTED",
    "LOAD_DECISION_REJECTED",
    "STAGE30_14_1_LOAD_DECISIONS",
    "is_load_decision",
    # Load reasons.
    "LOAD_REASON_ACCEPTED_FRESH_EVIDENCE",
    "LOAD_REASON_MISSING_REQUIRED_FIELD",
    "LOAD_REASON_NON_PRESENT_STATUS",
    "LOAD_REASON_INVALID_SOURCE",
    "LOAD_REASON_UNSAFE_AXIS_SHAPE",
    "LOAD_REASON_NOT_PUMP_SUFFIX",
    "LOAD_REASON_MALFORMED_TIMESTAMP",
    "LOAD_REASON_BAD_SOURCE_REF",
    "LOAD_REASON_INCOMPLETE_MEASUREMENT",
    "LOAD_REASON_UNSAFE_REDACTION",
    "LOAD_REASON_NONEMPTY_WARNINGS",
    "LOAD_REASON_DUPLICATE_MINT",
    "LOAD_REASON_DUPLICATE_SIGNATURE",
    "STAGE30_14_1_LOAD_REJECT_REASONS",
    "STAGE30_14_1_LOAD_REASONS",
    "is_load_reason",
    # Structural load-error reasons.
    "LOAD_ERROR_UNREADABLE_ARTIFACT",
    "LOAD_ERROR_FILE_TOO_LARGE",
    "LOAD_ERROR_TOO_MANY_LINES",
    "LOAD_ERROR_TOO_MANY_RECORDS",
    "LOAD_ERROR_MALFORMED_JSONL_LINE",
    "LOAD_ERROR_WRONG_SCHEMA_VERSION",
    "LOAD_ERROR_INVALID_CAP",
    "STAGE30_14_1_LOAD_ERROR_REASONS",
    "is_load_error_reason",
    # Verify-error reasons.
    "VERIFY_ERROR_NOT_A_LOAD_RESULT",
    "VERIFY_ERROR_INVALID_MAX_REPLAY",
    "VERIFY_ERROR_TOO_MANY_REPLAY_RECORDS",
    "STAGE30_14_1_VERIFY_ERROR_REASONS",
    "is_verify_error_reason",
    # Redaction.
    "STAGE30_14_1_REDACTION_STATUS_REDACTED",
    "STAGE30_14_1_REDACTION_STATUS_VIOLATION",
    "STAGE30_14_1_REDACTED_UNSAFE_ID",
    "STAGE30_14_1_REDACTION_STATUSES",
    "are_strings_redaction_safe",
    # Pump-suffix predicate.
    "STAGE30_14_1_PUMP_MINT_SUFFIX",
    "is_base58_mint_string",
    "is_pump_suffix_mint",
    # Source_ref builder.
    "build_expected_source_ref",
    # Safe-shape predicates.
    "is_nonblank_str",
    "is_safe_echo_id",
    "safe_echo",
    # Models.
    "Stage30_14_1PersistedAttestation",
    "Stage30_14_1EvidenceLoadOutcome",
    "Stage30_14_1EvidenceLoadSummary",
    "Stage30_14_1EvidenceLoadResult",
    "Stage30_14_1ReplayVerifyOutcome",
    "Stage30_14_1ReplayVerifyResult",
    # Field-name helpers.
    "persisted_attestation_field_names",
    "evidence_load_outcome_field_names",
    "evidence_load_summary_field_names",
    "evidence_load_result_field_names",
    "replay_verify_outcome_field_names",
    "replay_verify_result_field_names",
)

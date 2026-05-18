"""Stage 22.2 dedupe ledger implementations.

Two implementations of the Stage 22.1 ``DedupeLedger`` Protocol:

  * ``InMemoryDedupeLedger`` -- no I/O, deterministic, for the
    future bounded runner's offline unit suite.
  * ``JsonlDedupeLedger``    -- append-only JSONL ledger with
    cross-run state reconstruction via replay. Operator
    supplies a ``pathlib.Path``; the parent directory must
    already exist; the ledger never calls ``mkdir`` / ``unlink``
    / ``rename`` / ``replace`` / ``glob`` / ``iterdir`` /
    ``rmdir`` and never imports ``shutil``.

Both implementations share the same logical dedupe identity:

    (provider_id, chain, event_id)

``provider_event_id`` and ``raw_event_hash`` are preserved on
every record for audit / correlation but are NOT part of
send-suppression identity, so a provider that mutates either
field cannot defeat dedupe by re-emitting the same logical
event. This matches the Stage 22.1 ``IngestEventKey`` docstring
clarified at 22.2. Detection of "same logical id but different
audit fields" drift is a Stage 22.3+ capture / audit concern.

Runtime semantics:

  * ``check_and_record`` is atomic on the in-memory ledger by
    construction (single-process, no async). For the JSONL
    ledger, the new ``seen`` line is written + fsynced before
    in-memory state is mutated. An ``OSError`` during the write
    returns ``ledger_unavailable`` and leaves in-memory state
    unchanged. The Stage 22.1 ``DedupeLedger`` Protocol
    contract is preserved.
  * ``mark_dispatched`` is idempotent: a second call for an
    already-dispatched key is a no-op (no record appended, no
    state change). Calling it for a logical key that was never
    seen is a hard contract violation
    (``Stage22LedgerContractError``). An ``OSError`` during
    the write raises ``Stage22LedgerContractError`` and leaves
    both in-memory and on-disk state unchanged.

Replay semantics for the JSONL ledger:

  * Missing file with existing parent -> empty state, ready
    to write.
  * Missing parent directory -> ``Stage22LedgerContractError``.
  * Empty existing file -> empty state.
  * Path traversal segment (``..``) -> rejected at
    construction.
  * Path exists but is not a regular file -> rejected.
  * Malformed JSON line / record with a field set that is not
    exactly ``LEDGER_REQUIRED_RECORD_FIELDS`` (any missing
    required field OR any unexpected extra field) / non-string
    field value / unknown schema_version / unknown record_type
    / empty required non-empty field / ``dispatched`` record
    for an unseen logical key -> ``Stage22LedgerContractError``.
  * Duplicate ``seen`` for an already-seen logical key on
    replay -> tolerated (idempotent replay).
  * Duplicate ``dispatched`` for an already-dispatched logical
    key on replay -> tolerated.

Single-writer assumption: the operator is responsible for not
pointing two processes at the same path concurrently. Stage
22.2 does not provide multi-process coordination.

This module imports only stdlib (``json`` / ``os`` /
``pathlib``) plus the Stage 22 contracts. It does NOT import
any network / RPC / messaging / DB / scheduler / secrets
library, does NOT read the process environment, does NOT
define a CLI surface, and contains no top-level I/O.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from PHX2.stage22.constants import (
    DEDUPE_OUTCOME_DUPLICATE_ALREADY_DISPATCHED,
    DEDUPE_OUTCOME_DUPLICATE_NOT_YET_DISPATCHED,
    DEDUPE_OUTCOME_LEDGER_UNAVAILABLE,
    DEDUPE_OUTCOME_NEW,
    LEDGER_RECORD_TYPE_DISPATCHED,
    LEDGER_RECORD_TYPE_SEEN,
    LEDGER_RECORD_TYPES,
    LEDGER_REQUIRED_NON_EMPTY_FIELDS,
    LEDGER_REQUIRED_RECORD_FIELDS,
    STAGE22_LEDGER_RECORD_SCHEMA_VERSION,
)
from PHX2.stage22.errors import Stage22LedgerContractError
from PHX2.stage22.ingest_contracts import DedupeOutcome, IngestEventKey


# ---------------------------------------------------------------------------
# Logical dedupe identity projection
# ---------------------------------------------------------------------------
#
# Module-private alias for clarity. The runtime value is just a
# plain ``tuple[str, str, str]`` so no extra runtime type is
# introduced; downstream consumers should not depend on the
# alias name.


_LogicalId = tuple[str, str, str]


def ingest_key_logical_id(*, key: IngestEventKey) -> _LogicalId:
    """Project ``key`` to its Stage 22.2 logical dedupe identity.

    Returns the ``(provider_id, chain, event_id)`` tuple used by
    both ledger implementations for seen / dispatched lookups.
    ``provider_event_id`` and ``raw_event_hash`` are audit
    fields and are not part of the projected identity. Pure;
    no I/O, no clock, no env reads.
    """
    return (key.provider_id, key.chain, key.event_id)


# ---------------------------------------------------------------------------
# Module-private per-key state
# ---------------------------------------------------------------------------


class _LedgerState:
    """Module-private mutable state cell for a single logical key."""

    __slots__ = ("dispatched", "full_key")

    def __init__(
        self,
        *,
        full_key: IngestEventKey,
        dispatched: bool,
    ) -> None:
        self.dispatched = dispatched
        self.full_key = full_key


# ---------------------------------------------------------------------------
# JSONL record helpers (pure, module-private)
# ---------------------------------------------------------------------------


def _serialize_record(
    *,
    record_type: str,
    key: IngestEventKey,
) -> str:
    """Serialize a ledger record to a deterministic JSON line.

    Sorted keys, compact separators, no trailing newline. The
    caller appends the newline at write time. The record carries
    only the locked seven-field schema; no timestamp, no
    transport material, no secret-shaped field.
    """
    record = {
        "schema_version": STAGE22_LEDGER_RECORD_SCHEMA_VERSION,
        "record_type": record_type,
        "provider_id": key.provider_id,
        "chain": key.chain,
        "event_id": key.event_id,
        "provider_event_id": key.provider_event_id,
        "raw_event_hash": key.raw_event_hash,
    }
    return json.dumps(record, sort_keys=True, separators=(",", ":"))


def _decode_record(
    *,
    raw: str,
    line_no: int,
) -> dict[str, str]:
    """Decode and validate a single JSONL record line.

    Returns the validated field map on success. Raises
    ``Stage22LedgerContractError`` on any contract violation:
    invalid JSON, non-object JSON, field set not exactly the
    locked seven (any missing required field OR any
    unexpected extra field), non-string field value, unknown
    schema_version, unknown record_type, or empty
    required-non-empty field.
    """
    try:
        decoded = json.loads(raw)
    except ValueError:
        raise Stage22LedgerContractError(
            f"ledger line {line_no} is not valid JSON"
        )
    if not isinstance(decoded, dict):
        raise Stage22LedgerContractError(
            f"ledger line {line_no} is not a JSON object"
        )
    expected_field_set: set[str] = set(LEDGER_REQUIRED_RECORD_FIELDS)
    actual_field_set: set[str] = set(decoded.keys())
    if actual_field_set != expected_field_set:
        extras = sorted(actual_field_set - expected_field_set)
        missing = sorted(expected_field_set - actual_field_set)
        raise Stage22LedgerContractError(
            f"ledger line {line_no} has an unexpected field set "
            f"(extras={extras}, missing={missing})"
        )
    for field in LEDGER_REQUIRED_RECORD_FIELDS:
        if not isinstance(decoded[field], str):
            raise Stage22LedgerContractError(
                f"ledger line {line_no} field {field!r} is not a string"
            )
    if decoded["schema_version"] != STAGE22_LEDGER_RECORD_SCHEMA_VERSION:
        raise Stage22LedgerContractError(
            f"ledger line {line_no} has unknown schema_version"
        )
    if decoded["record_type"] not in LEDGER_RECORD_TYPES:
        raise Stage22LedgerContractError(
            f"ledger line {line_no} has unknown record_type"
        )
    for field in LEDGER_REQUIRED_NON_EMPTY_FIELDS:
        if decoded[field] == "":
            raise Stage22LedgerContractError(
                f"ledger line {line_no} required field {field!r} is empty"
            )
    return decoded


# ---------------------------------------------------------------------------
# InMemoryDedupeLedger
# ---------------------------------------------------------------------------


class InMemoryDedupeLedger:
    """In-memory ``DedupeLedger`` implementation.

    No I/O, no clock, no env reads. The future bounded runner's
    offline unit suite uses this implementation directly; the
    JSONL ledger is the cross-run-durable production choice.

    The Stage 22.1 ``DedupeLedger`` Protocol contract is
    preserved: ``check_and_record`` is atomic; ``mark_dispatched``
    is idempotent; ``mark_dispatched`` on an unknown logical
    key raises ``Stage22LedgerContractError``; the
    ``ledger_unavailable`` outcome is never emitted (there is
    no transient I/O failure mode to model).
    """

    def __init__(self) -> None:
        self._state: dict[_LogicalId, _LedgerState] = {}

    def check_and_record(
        self,
        *,
        key: IngestEventKey,
    ) -> DedupeOutcome:
        logical = ingest_key_logical_id(key=key)
        existing = self._state.get(logical)
        if existing is None:
            self._state[logical] = _LedgerState(
                full_key=key,
                dispatched=False,
            )
            return DedupeOutcome(
                outcome=DEDUPE_OUTCOME_NEW,
                ingest_key=key,
            )
        if existing.dispatched:
            return DedupeOutcome(
                outcome=DEDUPE_OUTCOME_DUPLICATE_ALREADY_DISPATCHED,
                ingest_key=key,
            )
        return DedupeOutcome(
            outcome=DEDUPE_OUTCOME_DUPLICATE_NOT_YET_DISPATCHED,
            ingest_key=key,
        )

    def mark_dispatched(
        self,
        *,
        key: IngestEventKey,
    ) -> None:
        logical = ingest_key_logical_id(key=key)
        existing = self._state.get(logical)
        if existing is None:
            raise Stage22LedgerContractError(
                "mark_dispatched called for unknown logical key"
            )
        if existing.dispatched:
            return
        existing.dispatched = True


# ---------------------------------------------------------------------------
# JsonlDedupeLedger
# ---------------------------------------------------------------------------


class JsonlDedupeLedger:
    """Append-only JSONL ``DedupeLedger`` implementation.

    On construction the ledger replays the existing file (if
    any) and rebuilds in-memory state. Subsequent
    ``check_and_record`` / ``mark_dispatched`` calls append at
    most one line each (only on state transitions) and fsync
    before returning. Duplicate checks and idempotent
    re-dispatch calls append nothing.

    Path discipline:

      * ``path`` must be a ``pathlib.Path``.
      * ``..`` segments anywhere in ``path.parts`` are rejected.
      * The parent directory must already exist; the ledger
        never calls ``mkdir``.
      * If ``path`` exists it must be a regular file; pointing
        at a directory or other non-file path is rejected.

    Failure modes:

      * Replay sees a contract-violating line -> raise.
      * Write IOError during ``check_and_record`` -> return
        ``ledger_unavailable``; in-memory state unchanged.
      * Write IOError during ``mark_dispatched`` -> raise
        ``Stage22LedgerContractError``; in-memory state
        unchanged.

    Single-writer assumption: the operator is responsible for
    not pointing two processes at the same path concurrently.
    """

    def __init__(self, *, path: Path) -> None:
        if not isinstance(path, Path):
            raise Stage22LedgerContractError(
                "JsonlDedupeLedger requires a pathlib.Path"
            )
        if ".." in path.parts:
            raise Stage22LedgerContractError(
                "ledger path must not contain '..' path traversal "
                "segments"
            )
        parent = path.parent
        if not parent.exists() or not parent.is_dir():
            raise Stage22LedgerContractError(
                "ledger path parent directory does not exist "
                "(the ledger never creates directories)"
            )
        if path.exists() and not path.is_file():
            raise Stage22LedgerContractError(
                "ledger path exists but is not a regular file"
            )
        self._path: Path = path
        self._state: dict[_LogicalId, _LedgerState] = {}
        self._replay()

    def _replay(self) -> None:
        if not self._path.exists():
            return
        with open(self._path, "r", encoding="utf-8") as f:
            for line_no, raw in enumerate(f, start=1):
                stripped = raw.rstrip("\n")
                if stripped == "":
                    raise Stage22LedgerContractError(
                        f"ledger line {line_no} is blank"
                    )
                decoded = _decode_record(raw=stripped, line_no=line_no)
                self._apply_decoded(decoded=decoded, line_no=line_no)

    def _apply_decoded(
        self,
        *,
        decoded: dict[str, str],
        line_no: int,
    ) -> None:
        full_key = IngestEventKey(
            provider_id=decoded["provider_id"],
            chain=decoded["chain"],
            event_id=decoded["event_id"],
            provider_event_id=decoded["provider_event_id"],
            raw_event_hash=decoded["raw_event_hash"],
        )
        logical = ingest_key_logical_id(key=full_key)
        record_type = decoded["record_type"]
        existing = self._state.get(logical)
        if record_type == LEDGER_RECORD_TYPE_SEEN:
            if existing is None:
                self._state[logical] = _LedgerState(
                    full_key=full_key,
                    dispatched=False,
                )
            return
        if existing is None:
            raise Stage22LedgerContractError(
                f"ledger line {line_no} is 'dispatched' but the logical "
                "key has not been seen (corrupt ledger)"
            )
        existing.dispatched = True

    def _append_record(
        self,
        *,
        record_type: str,
        key: IngestEventKey,
    ) -> None:
        line = _serialize_record(record_type=record_type, key=key)
        with open(self._path, "a", encoding="utf-8") as f:
            f.write(line)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())

    def check_and_record(
        self,
        *,
        key: IngestEventKey,
    ) -> DedupeOutcome:
        logical = ingest_key_logical_id(key=key)
        existing = self._state.get(logical)
        if existing is not None:
            if existing.dispatched:
                return DedupeOutcome(
                    outcome=DEDUPE_OUTCOME_DUPLICATE_ALREADY_DISPATCHED,
                    ingest_key=key,
                )
            return DedupeOutcome(
                outcome=DEDUPE_OUTCOME_DUPLICATE_NOT_YET_DISPATCHED,
                ingest_key=key,
            )
        try:
            self._append_record(
                record_type=LEDGER_RECORD_TYPE_SEEN,
                key=key,
            )
        except OSError:
            return DedupeOutcome(
                outcome=DEDUPE_OUTCOME_LEDGER_UNAVAILABLE,
                ingest_key=key,
            )
        self._state[logical] = _LedgerState(
            full_key=key,
            dispatched=False,
        )
        return DedupeOutcome(
            outcome=DEDUPE_OUTCOME_NEW,
            ingest_key=key,
        )

    def mark_dispatched(
        self,
        *,
        key: IngestEventKey,
    ) -> None:
        logical = ingest_key_logical_id(key=key)
        existing = self._state.get(logical)
        if existing is None:
            raise Stage22LedgerContractError(
                "mark_dispatched called for unknown logical key"
            )
        if existing.dispatched:
            return
        try:
            self._append_record(
                record_type=LEDGER_RECORD_TYPE_DISPATCHED,
                key=key,
            )
        except OSError:
            raise Stage22LedgerContractError(
                "ledger write failed during mark_dispatched"
            )
        existing.dispatched = True


__all__ = [
    "InMemoryDedupeLedger",
    "JsonlDedupeLedger",
    "ingest_key_logical_id",
]

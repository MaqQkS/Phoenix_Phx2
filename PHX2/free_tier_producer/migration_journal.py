"""Durable migration-evidence journal and confirmed-slot cursor.

WHAT THIS IS
------------
An append-only, restart-safe record of every CONFIRMED migration proof the one
live source admitted, plus a separate authenticated cursor naming the last slot
whose evidence is durably committed.  It answers, after any restart or crash,
two questions that nothing else in PHX2 could answer durably:

  * "which migrations do we already hold evidence for?"  (idempotent replay)
  * "from which slot forward is coverage unproven?"       (gap detection)

WHAT IT IS NOT
--------------
It is NOT a delivery record.  It never touches the paid Telegram ledger, never
authorizes a send, and never replays a historical tier.  Recovered evidence
re-enters the ordinary admission/watchlist path and is subject to every
existing gate.

THE INVARIANTS
--------------
1. ONE LINE PER RECORD, WRITTEN ONCE.  Records go through the serialized
   single-``os.write`` appender (:mod:`serialized_jsonl`), so two threads can
   never interleave and a crash leaves either nothing or a complete line.

2. A TORN OR MALFORMED TRAILING WRITE CANNOT CORRUPT PRIOR STATE.  ``load``
   parses line by line; an unparseable or schema-invalid line is counted and
   skipped, never fatal, and never removes an earlier valid record.

3. IDEMPOTENT REPLAY.  A record is identified by its transaction signature.
   Re-appending the same signature (live duplicate, HTTP gap recovery returning
   a row the socket already delivered, or a restart re-reading the file) is a
   no-op that increments ``duplicate_appends`` and leaves the journal byte-wise
   unchanged.  A second signature for the same mint is a distinct record: one
   mint can legitimately be seen twice, and hiding that would lose evidence.

4. THE CURSOR NEVER LEADS THE EVIDENCE.  ``commit_cursor`` refuses to advance
   past the highest durably journalled slot.  On load, a cursor found AHEAD of
   the journal is rejected and clamped down to the journal maximum
   (``CURSOR_AHEAD_OF_JOURNAL``); a journal found ahead of the cursor pulls the
   cursor UP to it (``JOURNAL_AHEAD_OF_CURSOR``) because that evidence is on
   disk and proven.

5. ATOMIC, BACKED-UP CURSOR.  The cursor is written to a temp sibling, the
   previous document is rotated to ``.bak``, then ``os.replace`` publishes the
   new one, and both copies carry a payload digest.  A cursor that fails its
   digest is not "close enough": it is ignored in favour of the backup, and if
   both fail the journal alone rebuilds the cursor.

6. SANITIZED EVIDENCE ONLY.  A record carries mint, signature, slot, block
   time, migration kind, proof digest, source class and the persist timestamp.
   No raw provider payload, no URL, no credential, no message body.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

from PHX2.free_tier_producer.serialized_jsonl import (
    SerializedJsonlAppendError,
    SerializedJsonlAppender,
)

JOURNAL_SCHEMA_VERSION = "phx2_migration_journal_v1"
JOURNAL_RECORD_KIND = "PHX2_MIGRATION_JOURNAL_RECORD"
CURSOR_SCHEMA_VERSION = "phx2_migration_journal_cursor_v1"
CURSOR_KIND = "PHX2_MIGRATION_JOURNAL_CURSOR"

JOURNAL_BASENAME = "migration_journal.jsonl"
CURSOR_BASENAME = "migration_journal_cursor.json"

#: Migration kinds (mirrors the decoder's closed set).
MIGRATION_KIND_V1 = "migrate"
MIGRATION_KIND_V2 = "migrate_v2"
MIGRATION_KINDS = (MIGRATION_KIND_V1, MIGRATION_KIND_V2)

#: Evidence source classes (role-based; never a provider product name).
SOURCE_LIVE_STREAM = "LIVE_STREAM"
SOURCE_GAP_RECOVERY = "EXACT_GAP_RECOVERY"
SOURCE_CURATED_SAFETY_NET = "CURATED_SAFETY_NET"
JOURNAL_SOURCES = (
    SOURCE_LIVE_STREAM,
    SOURCE_GAP_RECOVERY,
    SOURCE_CURATED_SAFETY_NET,
)

# -- append/commit outcomes (closed set) ------------------------------------
APPEND_COMMITTED = "COMMITTED"
APPEND_DUPLICATE = "DUPLICATE_IDEMPOTENT"
APPEND_REJECTED_INVALID = "REJECTED_INVALID_RECORD"
APPEND_FAILED_DURABILITY = "FAILED_DURABILITY"
APPEND_OUTCOMES = (
    APPEND_COMMITTED,
    APPEND_DUPLICATE,
    APPEND_REJECTED_INVALID,
    APPEND_FAILED_DURABILITY,
)

# -- cursor reconciliation verdicts (closed set) -----------------------------
CURSOR_CONSISTENT = "CONSISTENT"
CURSOR_MISSING = "CURSOR_MISSING"
CURSOR_RESTORED_FROM_BACKUP = "CURSOR_RESTORED_FROM_BACKUP"
CURSOR_AHEAD_OF_JOURNAL = "CURSOR_AHEAD_OF_JOURNAL"
CURSOR_JOURNAL_AHEAD = "JOURNAL_AHEAD_OF_CURSOR"
CURSOR_INVALID_DOCUMENT = "CURSOR_DOCUMENT_INVALID"
CURSOR_VERDICTS = (
    CURSOR_CONSISTENT,
    CURSOR_MISSING,
    CURSOR_RESTORED_FROM_BACKUP,
    CURSOR_AHEAD_OF_JOURNAL,
    CURSOR_JOURNAL_AHEAD,
    CURSOR_INVALID_DOCUMENT,
)

# -- commit refusals (closed set) -------------------------------------------
COMMIT_OK = "CURSOR_COMMITTED"
COMMIT_REFUSED_AHEAD = "CURSOR_REFUSED_AHEAD_OF_EVIDENCE"
COMMIT_REFUSED_REGRESSION = "CURSOR_REFUSED_REGRESSION"
COMMIT_REFUSED_INVALID = "CURSOR_REFUSED_INVALID_SLOT"
COMMIT_FAILED_WRITE = "CURSOR_WRITE_FAILED"


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _is_slot(value: object) -> bool:
    return (isinstance(value, int) and not isinstance(value, bool)
            and value >= 0)


def _canonical_bytes(payload: Mapping[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("utf-8")


def _digest(payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical_bytes(payload)).hexdigest()


@dataclass(frozen=True)
class MigrationJournalRecord:
    """One sanitized, non-secret confirmed-migration proof."""

    mint: str
    signature: str
    migration_slot: int
    block_time_utc: Optional[str]
    migration_kind: str
    migration_proof_digest: str
    source: str
    persisted_at_utc: str

    def to_record(self) -> Dict[str, Any]:
        record = asdict(self)
        record["kind"] = JOURNAL_RECORD_KIND
        record["schema_version"] = JOURNAL_SCHEMA_VERSION
        return record

    @classmethod
    def from_record(
        cls, record: Mapping[str, Any],
    ) -> Optional["MigrationJournalRecord"]:
        if not isinstance(record, Mapping):
            return None
        if record.get("kind") != JOURNAL_RECORD_KIND:
            return None
        if record.get("schema_version") != JOURNAL_SCHEMA_VERSION:
            return None
        mint = record.get("mint")
        signature = record.get("signature")
        slot = record.get("migration_slot")
        kind = record.get("migration_kind")
        proof = record.get("migration_proof_digest")
        source = record.get("source")
        persisted = record.get("persisted_at_utc")
        block_time = record.get("block_time_utc")
        if (not isinstance(mint, str) or not mint
                or not isinstance(signature, str) or not signature
                or not _is_slot(slot)
                or kind not in MIGRATION_KINDS
                or not isinstance(proof, str) or not proof
                or source not in JOURNAL_SOURCES
                or not isinstance(persisted, str) or not persisted):
            return None
        if block_time is not None and not isinstance(block_time, str):
            return None
        return cls(
            mint=mint,
            signature=signature,
            migration_slot=int(slot),
            block_time_utc=block_time,
            migration_kind=kind,
            migration_proof_digest=proof,
            source=source,
            persisted_at_utc=persisted,
        )


def build_journal_record(
    *,
    mint: object,
    signature: object,
    migration_slot: object,
    migration_kind: object,
    migration_proof_digest: object = None,
    block_time_utc: object = None,
    source: object = SOURCE_LIVE_STREAM,
    now_fn: Callable[[], str] = _utc_now,
) -> Optional[MigrationJournalRecord]:
    """Build one validated journal record, or ``None`` when unusable.

    ``migration_proof_digest`` may be omitted, in which case a digest is
    derived from the sanitized identity fields.  A digest is evidence identity,
    never a secret.
    """

    if not isinstance(mint, str) or not mint:
        return None
    if not isinstance(signature, str) or not signature:
        return None
    if not _is_slot(migration_slot):
        return None
    kind = str(migration_kind or "")
    if kind not in MIGRATION_KINDS:
        return None
    safe_source = source if source in JOURNAL_SOURCES else None
    if safe_source is None:
        return None
    if block_time_utc is not None and not isinstance(block_time_utc, str):
        return None
    digest = migration_proof_digest
    if not isinstance(digest, str) or not digest:
        digest = _digest({
            "mint": mint,
            "signature": signature,
            "slot": int(migration_slot),
            "kind": kind,
        })
    return MigrationJournalRecord(
        mint=mint,
        signature=signature,
        migration_slot=int(migration_slot),
        block_time_utc=block_time_utc,
        migration_kind=kind,
        migration_proof_digest=digest,
        source=safe_source,
        persisted_at_utc=str(now_fn()),
    )


@dataclass(frozen=True)
class JournalAppendResult:
    outcome: str
    signature: Optional[str]
    migration_slot: Optional[int]
    reason: Optional[str] = None

    @property
    def committed(self) -> bool:
        return self.outcome == APPEND_COMMITTED


@dataclass(frozen=True)
class CursorCommitResult:
    outcome: str
    committed_slot: Optional[int]
    requested_slot: Optional[int]
    highest_journalled_slot: Optional[int]

    @property
    def committed(self) -> bool:
        return self.outcome == COMMIT_OK


class DurableMigrationJournal:
    """Append-only migration evidence + an authenticated confirmed-slot cursor.

    Thread-safe.  Every public method is safe to call from the source thread,
    the recovery thread and the safety-net thread concurrently.
    """

    def __init__(
        self,
        *,
        journal_path: object,
        cursor_path: object = None,
        now_fn: Callable[[], str] = _utc_now,
        fsync_records: bool = True,
    ) -> None:
        self._journal_path = Path(str(journal_path))
        self._cursor_path = (
            Path(str(cursor_path)) if cursor_path is not None
            else self._journal_path.with_name(CURSOR_BASENAME))
        self._now = now_fn
        self._lock = threading.RLock()
        self._appender = SerializedJsonlAppender(
            self._journal_path, fsync_records=bool(fsync_records))
        self._signatures: Dict[str, int] = {}
        self._mints: Dict[str, int] = {}
        self._highest_slot: Optional[int] = None
        self._committed_slot: Optional[int] = None
        self._cursor_generation = 0
        self.records_committed = 0
        self.duplicate_appends = 0
        self.rejected_records = 0
        self.durability_failures = 0
        self.malformed_lines = 0
        self.cursor_write_failures = 0
        self.last_cursor_verdict: Optional[str] = None
        self.last_commit_utc: Optional[str] = None
        self.loaded = False

    # -- paths -------------------------------------------------------------

    @property
    def journal_path(self) -> Path:
        return self._journal_path

    @property
    def cursor_path(self) -> Path:
        return self._cursor_path

    # -- load / restore ----------------------------------------------------

    def load(self) -> str:
        """Restore journal + cursor; returns the closed-set cursor verdict."""

        with self._lock:
            self._signatures.clear()
            self._mints.clear()
            self._highest_slot = None
            self.malformed_lines = 0
            for record in self._read_journal_locked():
                self._index_locked(record)
            verdict, committed, generation = self._read_cursor_locked()
            journal_max = self._highest_slot
            if committed is not None and (
                    journal_max is None or committed > journal_max):
                # The cursor claims ground the evidence does not support.  An
                # EMPTY journal supports nothing at all, so a surviving cursor
                # over a lost/truncated journal is clamped away entirely rather
                # than left asserting coverage no record backs.
                committed = journal_max
                verdict = CURSOR_AHEAD_OF_JOURNAL
            elif journal_max is not None and (
                    committed is None or committed < journal_max):
                if verdict in (CURSOR_CONSISTENT, CURSOR_RESTORED_FROM_BACKUP,
                               CURSOR_MISSING, CURSOR_INVALID_DOCUMENT):
                    verdict = CURSOR_JOURNAL_AHEAD
                committed = journal_max
            self._committed_slot = committed
            self._cursor_generation = int(generation)
            self.last_cursor_verdict = verdict
            self.loaded = True
            return verdict

    def _read_journal_locked(self) -> List[MigrationJournalRecord]:
        try:
            raw = self._journal_path.read_bytes()
        except OSError:
            return []
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            text = raw.decode("utf-8", errors="replace")
        out: List[MigrationJournalRecord] = []
        for line in text.split("\n"):
            body = line[:-1] if line.endswith("\r") else line
            if not body.strip():
                continue
            try:
                parsed = json.loads(body)
            except ValueError:
                # A torn trailing write (or any malformed line) is disclosed
                # and skipped; every earlier valid record survives.
                self.malformed_lines += 1
                continue
            record = MigrationJournalRecord.from_record(parsed)
            if record is None:
                self.malformed_lines += 1
                continue
            out.append(record)
        return out

    def _index_locked(self, record: MigrationJournalRecord) -> bool:
        if record.signature in self._signatures:
            return False
        self._signatures[record.signature] = record.migration_slot
        self._mints.setdefault(record.mint, record.migration_slot)
        if self._highest_slot is None \
                or record.migration_slot > self._highest_slot:
            self._highest_slot = record.migration_slot
        return True

    # -- append ------------------------------------------------------------

    def append(self, record: object) -> JournalAppendResult:
        """Append one confirmed proof idempotently."""

        if not isinstance(record, MigrationJournalRecord):
            built = None
            if isinstance(record, Mapping):
                built = MigrationJournalRecord.from_record(record)
            if built is None:
                with self._lock:
                    self.rejected_records += 1
                return JournalAppendResult(
                    outcome=APPEND_REJECTED_INVALID,
                    signature=None,
                    migration_slot=None,
                    reason="JOURNAL_RECORD_INVALID",
                )
            record = built
        with self._lock:
            if record.signature in self._signatures:
                self.duplicate_appends += 1
                return JournalAppendResult(
                    outcome=APPEND_DUPLICATE,
                    signature=record.signature,
                    migration_slot=record.migration_slot,
                )
            try:
                self._appender.append(record.to_record())
            except SerializedJsonlAppendError as exc:
                self.durability_failures += 1
                return JournalAppendResult(
                    outcome=APPEND_FAILED_DURABILITY,
                    signature=record.signature,
                    migration_slot=record.migration_slot,
                    reason=exc.reason,
                )
            self._index_locked(record)
            self.records_committed += 1
            return JournalAppendResult(
                outcome=APPEND_COMMITTED,
                signature=record.signature,
                migration_slot=record.migration_slot,
            )

    def append_many(
        self, records: Sequence[object],
    ) -> List[JournalAppendResult]:
        return [self.append(item) for item in records or ()]

    # -- queries -----------------------------------------------------------

    def has_signature(self, signature: object) -> bool:
        with self._lock:
            return str(signature) in self._signatures

    def has_mint(self, mint: object) -> bool:
        with self._lock:
            return str(mint) in self._mints

    @property
    def highest_journalled_slot(self) -> Optional[int]:
        with self._lock:
            return self._highest_slot

    @property
    def last_confirmed_slot(self) -> Optional[int]:
        with self._lock:
            return self._committed_slot

    @property
    def record_count(self) -> int:
        with self._lock:
            return len(self._signatures)

    def missing_range(self, first_post_restart_slot: object
                      ) -> Optional[Tuple[int, int]]:
        """Inclusive range between the durable cursor and the next live slot.

        ``None`` when nothing is owed: no cursor yet (a fresh live-only start
        claims no prior ground) or the next slot continues exactly.
        """

        if not _is_slot(first_post_restart_slot):
            return None
        with self._lock:
            anchor = self._committed_slot
        if anchor is None:
            return None
        expected = int(anchor) + 1
        first = int(first_post_restart_slot)
        if first <= expected:
            return None
        return expected, first - 1

    # -- cursor ------------------------------------------------------------

    def commit_cursor(self, slot: object) -> CursorCommitResult:
        """Advance the durable cursor, never past committed evidence."""

        with self._lock:
            highest = self._highest_slot
            if not _is_slot(slot):
                return CursorCommitResult(
                    outcome=COMMIT_REFUSED_INVALID,
                    committed_slot=self._committed_slot,
                    requested_slot=None,
                    highest_journalled_slot=highest,
                )
            value = int(slot)
            if highest is None or value > highest:
                return CursorCommitResult(
                    outcome=COMMIT_REFUSED_AHEAD,
                    committed_slot=self._committed_slot,
                    requested_slot=value,
                    highest_journalled_slot=highest,
                )
            if self._committed_slot is not None \
                    and value < self._committed_slot:
                return CursorCommitResult(
                    outcome=COMMIT_REFUSED_REGRESSION,
                    committed_slot=self._committed_slot,
                    requested_slot=value,
                    highest_journalled_slot=highest,
                )
            written = self._write_cursor_locked(value)
            if not written:
                self.cursor_write_failures += 1
                return CursorCommitResult(
                    outcome=COMMIT_FAILED_WRITE,
                    committed_slot=self._committed_slot,
                    requested_slot=value,
                    highest_journalled_slot=highest,
                )
            self._committed_slot = value
            self.last_commit_utc = str(self._now())
            return CursorCommitResult(
                outcome=COMMIT_OK,
                committed_slot=value,
                requested_slot=value,
                highest_journalled_slot=highest,
            )

    def commit_cursor_to_evidence(self) -> CursorCommitResult:
        """Advance the cursor to the highest durably journalled slot."""

        with self._lock:
            highest = self._highest_slot
        if highest is None:
            return CursorCommitResult(
                outcome=COMMIT_REFUSED_AHEAD,
                committed_slot=None,
                requested_slot=None,
                highest_journalled_slot=None,
            )
        return self.commit_cursor(highest)

    def _cursor_document_locked(self, slot: int) -> Dict[str, Any]:
        payload = {
            "kind": CURSOR_KIND,
            "schema_version": CURSOR_SCHEMA_VERSION,
            "generation": int(self._cursor_generation) + 1,
            "last_confirmed_slot": int(slot),
            "journal_record_count": len(self._signatures),
            "highest_journalled_slot": (
                None if self._highest_slot is None
                else int(self._highest_slot)),
            "updated_at_utc": str(self._now()),
        }
        payload["payload_digest"] = _digest(payload)
        return payload

    def _write_cursor_locked(self, slot: int) -> bool:
        document = self._cursor_document_locked(slot)
        try:
            self._cursor_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._cursor_path.with_name(
                self._cursor_path.name + ".next.tmp")
            data = _canonical_bytes(document)
            with tmp.open("wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            if self._cursor_path.exists():
                backup = self._cursor_path.with_name(
                    self._cursor_path.name + ".bak")
                try:
                    os.replace(self._cursor_path, backup)
                except OSError:
                    pass
            os.replace(tmp, self._cursor_path)
        except OSError:
            return False
        self._cursor_generation = int(document["generation"])
        return True

    def _read_cursor_locked(
        self,
    ) -> Tuple[str, Optional[int], int]:
        candidates = (
            (CURSOR_CONSISTENT, self._cursor_path),
            (CURSOR_RESTORED_FROM_BACKUP,
             self._cursor_path.with_name(self._cursor_path.name + ".bak")),
        )
        saw_file = False
        for verdict, path in candidates:
            try:
                raw = path.read_bytes().decode("utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            saw_file = True
            try:
                document = json.loads(raw)
            except ValueError:
                continue
            if not isinstance(document, dict) \
                    or document.get("kind") != CURSOR_KIND \
                    or document.get("schema_version") != CURSOR_SCHEMA_VERSION:
                continue
            supplied = document.get("payload_digest")
            check = {k: v for k, v in document.items()
                     if k != "payload_digest"}
            if not isinstance(supplied, str) or _digest(check) != supplied:
                continue
            slot = document.get("last_confirmed_slot")
            if not _is_slot(slot):
                continue
            try:
                generation = int(document.get("generation") or 0)
            except (TypeError, ValueError):
                generation = 0
            return verdict, int(slot), generation
        return (CURSOR_INVALID_DOCUMENT if saw_file else CURSOR_MISSING), None, 0

    # -- observability -----------------------------------------------------

    def snapshot(self) -> Dict[str, Any]:
        """Redaction-safe journal state for status surfaces and artifacts."""

        with self._lock:
            return {
                "schema_version": JOURNAL_SCHEMA_VERSION,
                "loaded": bool(self.loaded),
                "record_count": len(self._signatures),
                "distinct_mints": len(self._mints),
                "records_committed": int(self.records_committed),
                "duplicate_appends": int(self.duplicate_appends),
                "rejected_records": int(self.rejected_records),
                "durability_failures": int(self.durability_failures),
                "malformed_lines": int(self.malformed_lines),
                "cursor_write_failures": int(self.cursor_write_failures),
                "highest_journalled_slot": self._highest_slot,
                "last_confirmed_slot": self._committed_slot,
                "cursor_generation": int(self._cursor_generation),
                "cursor_verdict": self.last_cursor_verdict,
                "last_journal_commit_utc": self.last_commit_utc,
            }

    def close(self) -> None:
        self._appender.close()


__all__ = (
    "APPEND_COMMITTED",
    "APPEND_DUPLICATE",
    "APPEND_FAILED_DURABILITY",
    "APPEND_OUTCOMES",
    "APPEND_REJECTED_INVALID",
    "COMMIT_FAILED_WRITE",
    "COMMIT_OK",
    "COMMIT_REFUSED_AHEAD",
    "COMMIT_REFUSED_INVALID",
    "COMMIT_REFUSED_REGRESSION",
    "CURSOR_AHEAD_OF_JOURNAL",
    "CURSOR_BASENAME",
    "CURSOR_CONSISTENT",
    "CURSOR_INVALID_DOCUMENT",
    "CURSOR_JOURNAL_AHEAD",
    "CURSOR_KIND",
    "CURSOR_MISSING",
    "CURSOR_RESTORED_FROM_BACKUP",
    "CURSOR_SCHEMA_VERSION",
    "CURSOR_VERDICTS",
    "CursorCommitResult",
    "DurableMigrationJournal",
    "JOURNAL_BASENAME",
    "JOURNAL_RECORD_KIND",
    "JOURNAL_SCHEMA_VERSION",
    "JOURNAL_SOURCES",
    "JournalAppendResult",
    "MIGRATION_KINDS",
    "MIGRATION_KIND_V1",
    "MIGRATION_KIND_V2",
    "MigrationJournalRecord",
    "SOURCE_CURATED_SAFETY_NET",
    "SOURCE_GAP_RECOVERY",
    "SOURCE_LIVE_STREAM",
    "build_journal_record",
)

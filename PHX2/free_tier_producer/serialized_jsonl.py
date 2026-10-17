"""serialized_jsonl.py — serialized single-write JSONL appender (activation events).

WHY THIS EXISTS (2026-07-29 torn-write root cause, short-acceptance Gate G):
``activation_events.jsonl`` was appended through a per-record ``open("a")`` +
buffered text write with NO cross-thread serialization, while records arrive
from BOTH the engine thread (engine/pricing-tail observation paths) and the
market-scheduler owner thread (apply-observation callbacks).  On Windows the
CRT emulates ``O_APPEND`` as seek-to-end THEN write — NOT an atomic append —
so two racing handles can seek to the SAME end offset and the second write
overwrites the first record's front, destroying one record and leaving its
tail as a malformed JSONL fragment (proven: runs 20260729T000325Z line 1126
and 20260729T010524Z line 87 are pure tail fragments of known record species
preceded by the race winner's intact record).

THE CONTRACT (one canonical append path):
  1. The COMPLETE record is serialized to one UTF-8 line BEFORE the
     destination is opened or locked.
  2. The encoded payload is validated to contain no literal newline / CR /
     NUL byte (``json.dumps`` with default ``ensure_ascii=True`` escapes all
     control characters; the check is a hard invariant, not a hope).
  3. Payload + newline are appended as ONE logical record through a single
     ``os.write`` on a raw ``O_APPEND`` descriptor (no user-space buffering,
     so there is nothing left to flush when the lock is released).
  4. Concurrent writers are serialized through one narrowly scoped
     ``threading.Lock`` per appender instance; the session funnels every
     activation-event source through one instance, so two records can never
     interleave.  A thread lock is SUFFICIENT because exactly one producer
     process owns a run directory: the run directory is unique per run
     instance (``paid_primary_live_24x7_<stamp>Z``) and the watchdog enforces
     a single producer via its runtime lock; the watchdog itself never writes
     run artifacts.
  5. ``fsync`` per record follows the existing durability policy for
     append-only producer evidence (``watch_terminal_history.archive`` and
     ``dispatch.sinks.file_preview``): flush + fsync before the lock is
     released, so a crash leaves either nothing or a complete line.
  6. Append-only: the descriptor is opened ``O_APPEND | O_CREAT | O_WRONLY``;
     this module never rewrites, truncates, rotates, or replaces the file.
     One bounded exception, added 2026-07-31: if the file ALREADY ends without
     a newline when this appender first opens it (a torn tail left by an older
     unserialized writer, e.g. the ``provider_handoff.jsonl`` line the
     2026-07-31 run left behind), a single ``\n`` RECORD SEPARATOR is appended
     before the first new record.  Without it the next record would be
     concatenated onto the torn fragment and the damage would spread from one
     unreadable line to two.  Nothing is rewritten or removed: the torn
     fragment stays on disk exactly as found, disclosed to the scanner, while
     everything appended afterwards is guaranteed parseable.
  7. A failed append RAISES ``SerializedJsonlAppendError`` carrying only
     closed-set reason tokens and the exception TYPE name (never record
     content, never exception text) — the caller discloses it through the
     existing error-ledger policy; there is no silent record loss.
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any, Mapping, Optional

#: Closed-set append failure reasons (safe for artifacts; never carry content).
APPEND_REFUSED_NOT_SERIALIZABLE = "JSONL_RECORD_NOT_SERIALIZABLE"
APPEND_REFUSED_FORBIDDEN_BYTE = "JSONL_RECORD_FORBIDDEN_BYTE"
APPEND_FAILED_OS_ERROR = "JSONL_APPEND_OS_ERROR"
APPEND_REFUSED_CLOSED = "JSONL_APPENDER_CLOSED"

_FORBIDDEN_BYTES = (b"\n", b"\r", b"\x00")


class SerializedJsonlAppendError(Exception):
    """One refused or failed durable JSONL append.

    ``reason`` is one of the closed-set ``APPEND_*`` tokens above and
    ``error_type`` is the underlying exception's TYPE NAME only.  The message
    is built from exactly those two tokens: no record content and no
    exception text ever reaches a log or artifact through this error.
    """

    def __init__(self, reason: str, error_type: str) -> None:
        super().__init__(f"{reason}:{error_type}")
        self.reason = str(reason)
        self.error_type = str(error_type)


class SerializedJsonlAppender:
    """Serialize-first, lock-serialized, single-``os.write`` JSONL appender.

    One instance per destination file; every writer thread must share the
    instance (the session wires all activation-event sources through one).
    The record serialization (``json.dumps(record, sort_keys=True)``) is
    byte-identical to the legacy ``_append_jsonl`` output, so the on-disk
    record shape is unchanged — only the append mechanics are hardened.
    """

    def __init__(self, path: Any, *, fsync_records: bool = True) -> None:
        self._path = Path(path)
        self._lock = threading.Lock()
        self._fd: Optional[int] = None
        self._closed = False
        self._fsync_records = bool(fsync_records)
        self.appended_records = 0
        self.failed_appends = 0
        #: Set when a pre-existing torn tail forced one separator newline.
        self.repaired_torn_tail = False

    @property
    def path(self) -> Path:
        return self._path

    def append(self, record: Mapping[str, Any]) -> None:
        """Append ``record`` as one complete JSONL line, or raise.

        Raises ``SerializedJsonlAppendError`` (and counts the failure) when
        the record cannot be serialized, would embed a forbidden byte, or the
        OS-level append fails.  On success the record is fully on disk (one
        write + fsync) before the method returns.
        """

        # (1) Complete serialization BEFORE the destination is opened/locked.
        try:
            line = json.dumps(record, sort_keys=True)
        except (TypeError, ValueError) as exc:
            self.failed_appends += 1
            raise SerializedJsonlAppendError(
                APPEND_REFUSED_NOT_SERIALIZABLE, type(exc).__name__)
        payload = line.encode("utf-8")
        # (2) One record == one line: refuse any payload that could tear the
        # line-oriented contract (unreachable via ensure_ascii=True; enforced
        # as an invariant, not assumed).
        if any(marker in payload for marker in _FORBIDDEN_BYTES):
            self.failed_appends += 1
            raise SerializedJsonlAppendError(
                APPEND_REFUSED_FORBIDDEN_BYTE, "ValueError")
        data = payload + b"\n"

        # (3)+(4) One logical append under the writer lock.
        with self._lock:
            if self._closed:
                self.failed_appends += 1
                raise SerializedJsonlAppendError(
                    APPEND_REFUSED_CLOSED, "RuntimeError")
            try:
                if self._fd is None:
                    self._path.parent.mkdir(parents=True, exist_ok=True)
                    # Record-boundary check BEFORE the first append: a file
                    # left without a trailing newline by an older writer must
                    # not swallow this record onto its torn fragment.
                    needs_separator = False
                    try:
                        if self._path.stat().st_size > 0:
                            with self._path.open("rb") as probe:
                                probe.seek(-1, os.SEEK_END)
                                needs_separator = probe.read(1) != b"\n"
                    except OSError:
                        needs_separator = False
                    flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND
                    # Windows: raw byte fd (no CRLF translation), and the
                    # descriptor must not leak into spawned processes.
                    flags |= getattr(os, "O_BINARY", 0)
                    flags |= getattr(os, "O_NOINHERIT", 0)
                    self._fd = os.open(str(self._path), flags, 0o644)
                    if needs_separator:
                        os.write(self._fd, b"\n")
                        self.repaired_torn_tail = True
                written = os.write(self._fd, data)
                # A regular-file write returning short is effectively
                # impossible, but the lock is still held: finishing the
                # record here keeps it contiguous even in that case.
                while written < len(data):
                    written += os.write(self._fd, data[written:])
                # (5) Durability before the lock is released.  Raw os.write
                # has no user-space buffer (nothing else to flush).
                if self._fsync_records:
                    os.fsync(self._fd)
            except OSError as exc:
                self.failed_appends += 1
                raise SerializedJsonlAppendError(
                    APPEND_FAILED_OS_ERROR, type(exc).__name__)
            self.appended_records += 1

    def close(self) -> None:
        """Close the descriptor (idempotent). Later appends are refused."""

        with self._lock:
            self._closed = True
            fd, self._fd = self._fd, None
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass


__all__ = (
    "APPEND_FAILED_OS_ERROR",
    "APPEND_REFUSED_CLOSED",
    "APPEND_REFUSED_FORBIDDEN_BYTE",
    "APPEND_REFUSED_NOT_SERIALIZABLE",
    "SerializedJsonlAppendError",
    "SerializedJsonlAppender",
)

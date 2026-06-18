"""Stage 30.14.0 in-memory replay discovery source.

Build #26, substage 30.14.0. The concrete, in-memory, deterministic discovery the Build
26.0 orchestrator drives the committed Stage 30.13.0 auto-seeder over -- the offline
stand-in for the deferred real read-only capture (Build 26.1). It exposes the SAME
``read_migration_evidence_batch()`` contract the committed auto-seeder consumes (the same
contract the committed Stage 29.5 ``Stage29_5HeliusWebSocketAdapter`` exposes at a live
ceremony), but it opens NO socket, reads NO env, reads NO wall clock, and performs NO
network I/O: it simply REPLAYS a caller-injected, pre-built tuple of migration evidence
records.

It FABRICATES nothing: it replays ONLY what the caller injects (in Build 26.0 a SYNTHETIC
``Stage29_5MigrationEvidenceRecord`` built in the test; in the deferred Build 26.1 an
actual evidence-bearing artifact, once one exists). It re-exercises the REAL committed
auto-seeder decision ladder (PRESENT -> safe-shape pump-suffix -> not-duplicate ->
COMPLETE projection -> ACCEPTED) over the replayed records, so the discovery -> seed
boundary is proven without any live capture.

To prove the fail-closed boundary OFFLINE, the source supports a ``fault_reason`` mode:
``read_migration_evidence_batch()`` then raises the committed closed-set
``Stage29_5MigrationEvidenceError`` (exactly what a degraded / malformed real capture
raises), which the committed auto-seeder converts to one ``WS_CAPTURE_FAILED`` error
outcome -- it seeds nothing and never crashes.

The source NEVER opens a network connection, NEVER reads the process environment, NEVER
reads a wall clock, NEVER reserves a dispatch, NEVER sends a message, NEVER touches a
durable ledger, NEVER writes a file, runs NO daemon / ``while`` loop, and edits NO
committed production file.

Discipline:

  * Stdlib only (``typing``).
  * Imports ONLY the committed Stage 29.5 migration-models closed-set capture error (the
    SCOPED discovery-currency deviation -- the same module the committed auto-seeder
    imports) + the Stage 30.14.0 models sibling. No other Stage 21-29 import (no Birdeye,
    no Stage 27 / 28); no transport / dispatch / runner / durable-ledger import.
  * No ``os.environ`` / ``os.getenv`` access; no env read.
  * No network, no HTTP, no gRPC, no WebSocket, no socket (the records are injected).
  * No database / SQLite, no compression, no durable ledger, no filesystem write.
  * No live provider, transport-destination, url, or host reference; no wallet /
    signing / trading surface; no public / subscriber routing.
  * No PHX1 import. No ``time`` / ``datetime`` import.
  * No module-level Call node (no implicit I/O at import time).
"""

from __future__ import annotations

from typing import List, Optional, Tuple

from PHX2.stage29.stage29_5_migration_models import (
    Stage29_5MigrationEvidenceError,
)
from PHX2.stage30.stage30_14_0_replay_discovery_models import (
    is_nonblank_str,
)


class Stage30_14ReplaySourceError(Exception):
    """Closed-set Stage 30.14.0 replay-source caller-shape error.

    Raised ONLY for a caller-shape failure the source cannot be constructed with -- a
    non-iterable ``records`` argument, or a ``fault_reason`` that is neither ``None`` nor a
    non-blank string. A construction-time failure (this error) is distinct from a
    read-time fault: a ``fault_reason`` raises the committed
    ``Stage29_5MigrationEvidenceError`` at ``read_migration_evidence_batch()`` time so the
    committed auto-seeder converts it to a clean ``WS_CAPTURE_FAILED`` outcome. Carries
    only a closed-set reason token; never a raw payload or any secret value.
    """

    def __init__(self, reason: str) -> None:
        self.reason: str = reason
        super().__init__(
            f"Stage 30.14.0 replay-source error: reason={reason!r}"
        )


class Stage30_14ReplayDiscoverySource:
    """In-memory replay discovery exposing ``read_migration_evidence_batch()``.

    Construction takes:

      * ``records`` -- a tuple / list of pre-built migration evidence records to replay
        (Build 26.0 injects a SYNTHETIC ``Stage29_5MigrationEvidenceRecord``; the caller
        owns construction so this source fabricates nothing). A non-record item is
        replayed VERBATIM so the committed auto-seeder classifies it (``NOT_A_RECORD``);
        the source does not pre-filter.
      * ``fault_reason`` -- optional. When a non-blank string, every
        ``read_migration_evidence_batch()`` call raises
        ``Stage29_5MigrationEvidenceError(fault_reason)`` (the committed closed-set
        capture error) so the committed auto-seeder fails closed to ``WS_CAPTURE_FAILED``;
        when ``None`` (default) the source replays ``records``.

    Construction fails closed (``Stage30_14ReplaySourceError``) on a non-iterable
    ``records`` argument or a ``fault_reason`` that is neither ``None`` nor a non-blank
    string. Deterministic: every call returns the SAME records tuple (or raises the SAME
    fault). Reads no env, no clock, no network; opens no socket; reserves no dispatch;
    writes no file; runs no daemon / ``while`` loop.
    """

    __slots__ = ("_records", "_fault_reason")

    def __init__(
        self,
        records: object = (),
        *,
        fault_reason: Optional[str] = None,
    ) -> None:
        if isinstance(records, (str, bytes)) or not hasattr(
            records, "__iter__"
        ):
            # A str / bytes is technically iterable but is never a record batch; any
            # non-iterable is a caller-shape failure. Fail closed BEFORE any replay.
            raise Stage30_14ReplaySourceError("RECORDS_NOT_ITERABLE")
        if fault_reason is not None and not is_nonblank_str(fault_reason):
            raise Stage30_14ReplaySourceError("INVALID_FAULT_REASON")
        materialized: List[object] = list(records)
        self._records: Tuple[object, ...] = tuple(materialized)
        self._fault_reason: Optional[str] = fault_reason

    @property
    def record_count(self) -> int:
        """Return the number of records this source will replay (0 in fault mode use is
        still the stored count; the fault pre-empts the replay)."""
        return len(self._records)

    @property
    def is_fault_mode(self) -> bool:
        """Return ``True`` iff this source raises a capture fault instead of replaying."""
        return self._fault_reason is not None

    def read_migration_evidence_batch(self) -> Tuple[object, ...]:
        """Return the replayed records tuple, or raise the committed closed-set capture
        error in fault mode.

        The committed Stage 30.13.0 auto-seeder calls this ONCE inside its fail-closed
        guard. In fault mode the raised ``Stage29_5MigrationEvidenceError`` is converted by
        the auto-seeder to one ``WS_CAPTURE_FAILED`` error outcome (seeds nothing, never
        crashes). Otherwise the records are returned VERBATIM for the auto-seeder's bounded
        decision ladder. Deterministic; no env / clock / network read.
        """
        if self._fault_reason is not None:
            raise Stage29_5MigrationEvidenceError(self._fault_reason)
        return self._records


__all__ = (
    "Stage30_14ReplaySourceError",
    "Stage30_14ReplayDiscoverySource",
)

"""Append-only paper ledgers + snapshot artifacts.

One run directory (default under ``C:\\Users\\BalaC\\phx2_paper_trading``)
holds:

* append-only JSONL ledgers: ``paper_positions.jsonl`` (position state
  transitions), ``paper_fills.jsonl``, ``paper_events.jsonl``,
  ``paper_errors.jsonl``, ``paper_equity_curve.jsonl``,
  ``paper_closed_positions.jsonl``;
* rewritten-in-place snapshots: ``paper_summary.json``,
  ``paper_open_positions.json``, ``strategy_comparison.json`` / ``.md``,
  ``paper_recent_events.jsonl`` (bounded tail).

The engine stages appends during a transaction. Its atomic paper_state.json
commit contains full state, input checkpoints and the last projection plan.
JSONL suffixes can be rebuilt after a torn append without duplicating fills.
Legacy ledger readers remain available for reports and reviewed replay use.
"""

from __future__ import annotations

import io
import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, IO, Iterable, List, Optional

POSITIONS_FILE = "paper_positions.jsonl"
FILLS_FILE = "paper_fills.jsonl"
EVENTS_FILE = "paper_events.jsonl"
ERRORS_FILE = "paper_errors.jsonl"
EQUITY_FILE = "paper_equity_curve.jsonl"
CLOSED_FILE = "paper_closed_positions.jsonl"
SUMMARY_FILE = "paper_summary.json"
OPEN_POSITIONS_FILE = "paper_open_positions.json"
COMPARISON_JSON_FILE = "strategy_comparison.json"
COMPARISON_MD_FILE = "strategy_comparison.md"
RECENT_EVENTS_FILE = "paper_recent_events.jsonl"
RUN_CONFIG_ECHO_FILE = "run_config_echo.json"
HEARTBEAT_FILE = "heartbeat.json"
LIVE_MONITOR_FILE = "live_monitor.json"
CHECKPOINTS_FILE = "input_checkpoints.json"
STATE_FILE = "paper_state.json"
# Stop before the producer's 32 MiB feedback reader limit; never commit a
# newly opened position whose authoritative coverage pin would be unreadable.
MAX_STATE_BYTES = 24 * 1024 * 1024

APPEND_FILES = (POSITIONS_FILE, FILLS_FILE, EVENTS_FILE, ERRORS_FILE,
                EQUITY_FILE, CLOSED_FILE)

# Windows can temporarily deny ``os.replace`` while a read-only consumer has
# the destination open without delete sharing.  Keep the retry policy small,
# deterministic, and local to the atomic replacement boundary.  The complete
# backoff is 25 + 50 + 100 ms, and the elapsed-time guard prevents retries from
# continuing beyond half a second even if an individual attempt is slow.
ATOMIC_REPLACE_MAX_ATTEMPTS = 4
ATOMIC_REPLACE_INITIAL_BACKOFF_SECONDS = 0.025
ATOMIC_REPLACE_MAX_BACKOFF_SECONDS = 0.100
ATOMIC_REPLACE_MAX_DURATION_SECONDS = 0.500

# Every artifact a paper run can leave in its run directory. Used to detect
# an already-used run dir (replay refuses to append duplicates) and to
# reset one explicitly. Only these exact names are ever removed by
# reset_run_dir -- never a recursive delete.
KNOWN_RUN_ARTIFACTS = APPEND_FILES + (
    SUMMARY_FILE, OPEN_POSITIONS_FILE, COMPARISON_JSON_FILE,
    COMPARISON_MD_FILE, RECENT_EVENTS_FILE, RUN_CONFIG_ECHO_FILE,
    HEARTBEAT_FILE, LIVE_MONITOR_FILE, CHECKPOINTS_FILE, STATE_FILE,
)


def _dumps(record: Dict[str, Any]) -> str:
    return json.dumps(record, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, default=str)


class PaperLedger:
    """Writer for one paper run directory."""

    def __init__(self, run_dir: str) -> None:
        self.run_dir = Path(run_dir)
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self._handles: Dict[str, IO[str]] = {}
        self._pending = None
        # Pre-create the append-only ledgers (empty on a fresh run) so the
        # dashboard artifact set is complete before the first append.
        for name in APPEND_FILES:
            target = self.run_dir / name
            if not target.exists():
                target.touch()

    # -- append-only ledgers ------------------------------------------------

    def _handle(self, name: str) -> IO[str]:
        handle = self._handles.get(name)
        if handle is None:
            handle = io.open(self.run_dir / name, "a", encoding="utf-8",
                             newline="\n")
            self._handles[name] = handle
        return handle

    def append(self, name: str, record: Dict[str, Any]) -> None:
        if self._pending is not None:
            self._pending.append((name, json.loads(_dumps(record))))
            return
        handle = self._handle(name)
        handle.write(_dumps(record) + "\n")
        handle.flush()
        os.fsync(handle.fileno())

    def begin_transaction(self) -> None:
        if self._pending is not None:
            raise RuntimeError("PAPER_TRANSACTION_ALREADY_ACTIVE")
        self._pending = []

    def rollback_transaction(self) -> None:
        self._pending = None

    def commit_transaction(self, state: Dict[str, Any]) -> None:
        """Commit authority first, then materialize recoverable JSONL views.

        A surviving state file carries the exact pre-append offsets and rows.
        On restart, replay replaces only the last committed projection suffix,
        so a torn append or process crash cannot duplicate a simulated fill.
        """
        if self._pending is None:
            raise RuntimeError("PAPER_TRANSACTION_NOT_ACTIVE")
        self.close()
        projection = {"offsets": {
            name: (self.run_dir / name).stat().st_size for name in APPEND_FILES
        }, "rows": list(self._pending)}
        payload = dict(state, projection=projection)
        self.write_json_atomic(STATE_FILE, payload)
        self._pending = None
        self.recover_projection(payload)

    def recover_projection(self, state: Dict[str, Any]) -> None:
        projection = state.get("projection") or {}
        offsets = projection.get("offsets") or {}
        rows = projection.get("rows") or []
        if set(offsets) != set(APPEND_FILES):
            raise ValueError("PAPER_STATE_PROJECTION_INVALID")
        grouped = {name: [] for name in APPEND_FILES}
        for name, record in rows:
            if name not in grouped or not isinstance(record, dict):
                raise ValueError("PAPER_STATE_PROJECTION_INVALID")
            grouped[name].append((_dumps(record) + "\n").encode("utf-8"))
        self.close()
        # Validate every boundary before changing any projection.
        for name in APPEND_FILES:
            offset = offsets[name]
            if (not isinstance(offset, int) or isinstance(offset, bool)
                    or offset < 0 or (self.run_dir / name).stat().st_size < offset):
                raise ValueError("PAPER_STATE_LEDGER_PREFIX_MISSING")
        for name in APPEND_FILES:
            with io.open(self.run_dir / name, "r+b") as handle:
                handle.seek(offsets[name])
                handle.truncate()
                for raw in grouped[name]:
                    handle.write(raw)
                handle.flush()
                os.fsync(handle.fileno())

    def append_position(self, record: Dict[str, Any]) -> None:
        self.append(POSITIONS_FILE, record)

    def append_fill(self, record: Dict[str, Any]) -> None:
        self.append(FILLS_FILE, record)

    def append_event(self, record: Dict[str, Any]) -> None:
        self.append(EVENTS_FILE, record)

    def append_error(self, record: Dict[str, Any]) -> None:
        self.append(ERRORS_FILE, record)

    def append_equity_point(self, record: Dict[str, Any]) -> None:
        self.append(EQUITY_FILE, record)

    def append_closed_position(self, record: Dict[str, Any]) -> None:
        self.append(CLOSED_FILE, record)

    # -- snapshot artifacts ---------------------------------------------------

    def write_json_atomic(self, name: str, payload: Any) -> None:
        text = json.dumps(
            payload,
            indent=2,
            sort_keys=True,
            ensure_ascii=True,
            default=str,
        ) + "\n"
        if name == STATE_FILE and len(text.encode("utf-8")) > MAX_STATE_BYTES:
            raise ValueError("PAPER_STATE_RETENTION_LIMIT_REQUIRES_REVIEW")
        self._write_atomic(name, text)

    def write_text_atomic(self, name: str, text: str) -> None:
        self._write_atomic(name, text)

    def _write_atomic(self, name: str, text: str) -> None:
        target = self.run_dir / name
        descriptor, temporary_name = tempfile.mkstemp(
            dir=str(target.parent),
            prefix=f".{target.name}.",
            suffix=".tmp",
        )
        temporary: Optional[Path] = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
                handle.write(text)
                handle.flush()
                os.fsync(handle.fileno())

            started = time.monotonic()
            for attempt in range(1, ATOMIC_REPLACE_MAX_ATTEMPTS + 1):
                try:
                    os.replace(temporary, target)
                    temporary = None
                    return
                except PermissionError:
                    elapsed = max(0.0, time.monotonic() - started)
                    delay = min(
                        ATOMIC_REPLACE_INITIAL_BACKOFF_SECONDS * (2 ** (attempt - 1)),
                        ATOMIC_REPLACE_MAX_BACKOFF_SECONDS,
                    )
                    retrying = (
                        attempt < ATOMIC_REPLACE_MAX_ATTEMPTS
                        and elapsed + delay <= ATOMIC_REPLACE_MAX_DURATION_SECONDS
                    )
                    self._atomic_write_diagnostic(
                        name=name,
                        attempt=attempt,
                        retrying=retrying,
                    )
                    if not retrying:
                        raise
                    time.sleep(delay)
        finally:
            if temporary is not None:
                try:
                    temporary.unlink()
                except FileNotFoundError:
                    pass
                except OSError:
                    # Preserve the replacement failure as the primary error.
                    # The fixed diagnostic contains no path, payload, or raw
                    # exception text that could disclose operator data.
                    self._atomic_write_diagnostic(
                        name=name,
                        attempt=ATOMIC_REPLACE_MAX_ATTEMPTS,
                        retrying=False,
                        cleanup_failed=True,
                    )

    def _atomic_write_diagnostic(
            self, *, name: str, attempt: int, retrying: bool,
            cleanup_failed: bool = False) -> None:
        event = {
            "kind": "PAPER_ATOMIC_WRITE_DIAGNOSTIC",
            "event": (
                "ATOMIC_TEMP_CLEANUP_FAILED"
                if cleanup_failed
                else ("ATOMIC_REPLACE_RETRY" if retrying else "ATOMIC_REPLACE_FAILED")
            ),
            "artifact_category": (
                "HEARTBEAT" if name == HEARTBEAT_FILE else "PAPER_SNAPSHOT"
            ),
            "attempt_count": int(attempt),
            "max_attempts": ATOMIC_REPLACE_MAX_ATTEMPTS,
            "error_category": "PERMISSION_ERROR_ACCESS_DENIED",
        }
        try:
            self.append_event(event)
        except OSError:
            # A diagnostic failure must not replace or hide the original
            # atomic-write exception.  The caller still receives that error.
            pass

    def write_recent_events(self, events: Iterable[Dict[str, Any]]) -> None:
        lines = "".join(_dumps(e) + "\n" for e in events)
        self.write_text_atomic(RECENT_EVENTS_FILE, lines)

    def close(self) -> None:
        for handle in self._handles.values():
            try:
                handle.close()
            except OSError:
                pass
        self._handles.clear()

    def __enter__(self) -> "PaperLedger":
        return self

    def __exit__(self, *exc_info: Any) -> None:
        self.close()


def read_jsonl(path: str) -> List[Dict[str, Any]]:
    """Read a JSONL file, skipping blank/corrupt lines (crash tolerance)."""
    records: List[Dict[str, Any]] = []
    file_path = Path(path)
    if not file_path.exists():
        return records
    with io.open(file_path, "r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(record, dict):
                records.append(record)
    return records


def run_dir_has_artifacts(run_dir: str) -> bool:
    """True when the directory already holds any known paper run artifact."""
    base = Path(run_dir)
    if not base.is_dir():
        return False
    return any((base / name).exists() for name in KNOWN_RUN_ARTIFACTS)


def reset_run_dir(run_dir: str) -> int:
    """Remove the known paper artifacts (and their .tmp siblings) from one
    run directory. Touches ONLY the fixed artifact names -- anything else in
    the directory is left alone. Returns the number of files removed."""
    base = Path(run_dir)
    removed = 0
    if not base.is_dir():
        return removed
    for name in KNOWN_RUN_ARTIFACTS:
        for target in (base / name, base / (name + ".tmp")):
            if target.exists():
                try:
                    target.unlink()
                    removed += 1
                except OSError:
                    pass
    return removed


def load_last_positions(run_dir: str) -> Dict[str, Dict[str, Any]]:
    """Last recorded state per paper_trade_id from the positions ledger."""
    latest: Dict[str, Dict[str, Any]] = {}
    for record in read_jsonl(str(Path(run_dir) / POSITIONS_FILE)):
        trade_id = record.get("paper_trade_id")
        if isinstance(trade_id, str) and trade_id:
            latest[trade_id] = record
    return latest


__all__ = [
    "POSITIONS_FILE",
    "FILLS_FILE",
    "EVENTS_FILE",
    "ERRORS_FILE",
    "EQUITY_FILE",
    "CLOSED_FILE",
    "SUMMARY_FILE",
    "OPEN_POSITIONS_FILE",
    "COMPARISON_JSON_FILE",
    "COMPARISON_MD_FILE",
    "RECENT_EVENTS_FILE",
    "RUN_CONFIG_ECHO_FILE",
    "HEARTBEAT_FILE",
    "LIVE_MONITOR_FILE",
    "CHECKPOINTS_FILE",
    "STATE_FILE",
    "MAX_STATE_BYTES",
    "ATOMIC_REPLACE_MAX_ATTEMPTS",
    "ATOMIC_REPLACE_INITIAL_BACKOFF_SECONDS",
    "ATOMIC_REPLACE_MAX_BACKOFF_SECONDS",
    "ATOMIC_REPLACE_MAX_DURATION_SECONDS",
    "APPEND_FILES",
    "KNOWN_RUN_ARTIFACTS",
    "PaperLedger",
    "read_jsonl",
    "run_dir_has_artifacts",
    "reset_run_dir",
    "load_last_positions",
]

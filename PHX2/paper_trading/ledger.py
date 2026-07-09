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

Appends are flushed line-by-line and snapshots are written via a temp file
+ ``os.replace`` so a crash never leaves a torn artifact. Restart safety:
``load_last_positions()`` replays the positions ledger and returns the last
recorded state per paper_trade_id, so open positions survive a restart.
"""

from __future__ import annotations

import io
import json
import os
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

APPEND_FILES = (POSITIONS_FILE, FILLS_FILE, EVENTS_FILE, ERRORS_FILE,
                EQUITY_FILE, CLOSED_FILE)

# Every artifact a paper run can leave in its run directory. Used to detect
# an already-used run dir (replay refuses to append duplicates) and to
# reset one explicitly. Only these exact names are ever removed by
# reset_run_dir -- never a recursive delete.
KNOWN_RUN_ARTIFACTS = APPEND_FILES + (
    SUMMARY_FILE, OPEN_POSITIONS_FILE, COMPARISON_JSON_FILE,
    COMPARISON_MD_FILE, RECENT_EVENTS_FILE, RUN_CONFIG_ECHO_FILE,
    HEARTBEAT_FILE, LIVE_MONITOR_FILE, CHECKPOINTS_FILE,
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
        handle = self._handle(name)
        handle.write(_dumps(record) + "\n")
        handle.flush()

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
        target = self.run_dir / name
        tmp = target.with_suffix(target.suffix + ".tmp")
        tmp.write_text(
            json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True,
                       default=str) + "\n",
            encoding="utf-8")
        os.replace(tmp, target)

    def write_text_atomic(self, name: str, text: str) -> None:
        target = self.run_dir / name
        tmp = target.with_suffix(target.suffix + ".tmp")
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, target)

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
    "APPEND_FILES",
    "KNOWN_RUN_ARTIFACTS",
    "PaperLedger",
    "read_jsonl",
    "run_dir_has_artifacts",
    "reset_run_dir",
    "load_last_positions",
]

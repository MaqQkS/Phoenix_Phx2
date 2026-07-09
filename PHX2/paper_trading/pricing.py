"""Normalize PHX2 candidate/ping artifact JSONL records into snapshots.

Understands the real PHX2 artifact shapes that exist today:

* ``BUILD30_CANDIDATE_RECHECK`` records (per-mint recheck series with
  ``market_attempt_summary`` price/market-cap/liquidity, plus
  ``compose_tier`` / ``compose_drawdown_pct`` / ``compose_anchored_ath_mc``
  when the dip gate evaluated the candidate),
* watch-state seed records (mint + timestamps, usually price-less),
* any generic record carrying a mint plus a timestamp, with tolerant
  key aliases for price / market cap / liquidity / volume / tier / score.

Missing fields never crash normalization: they come back ``None`` and the
engine decides what that means (skip entry, data-lost, etc.).
"""

from __future__ import annotations

import glob as _glob
import io
import json
import os
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from PHX2.paper_trading.models import (
    CandidateSnapshot,
    parse_money_text,
    parse_number,
    parse_pct_text,
    parse_tier,
    parse_utc,
)

# Key aliases, first hit wins. Checked on the record root, then on the
# nested containers listed in _NESTED_CONTAINERS.
_MINT_KEYS = ("token_mint", "mint", "base_mint", "token_address")
_TS_KEYS = ("observed_at_utc", "ts_utc", "timestamp_utc", "timestamp",
            "attempt_at_utc", "fetched_at_utc", "market_context_fetched_at_utc",
            "created_at_utc", "last_observed_at_utc", "seeded_at_utc",
            "sent_at_utc")
_PRICE_KEYS = ("current_price", "price_usd", "price", "price_value")
_MC_KEYS = ("current_market_cap_usd", "market_cap_usd", "mc_usd", "mc_value",
            "market_cap")
_LP_KEYS = ("liquidity_usd", "lp_usd", "lp_value", "liquidity")
_VOLUME_KEYS = ("volume_usd", "recent_volume_usd", "volume_24h_usd",
                "volume_usd_24h")
_TIER_KEYS = ("compose_tier", "tier", "phx2_tier")
_DRAWDOWN_KEYS = ("compose_drawdown_pct", "drawdown_pct", "dip_pct")
_ATH_KEYS = ("compose_anchored_ath_mc", "anchored_ath_mc",
             "ath_market_cap_usd", "ath_mc_usd")
_SCORE_KEYS = ("score", "quality_score", "quality")
_SYMBOL_KEYS = ("token_symbol", "symbol", "symbol_or_name", "token_name",
                "name")
_SUPPLY_KEYS = ("supply", "token_supply", "circulating_supply")
_CANDIDATE_ID_KEYS = ("candidate_id", "ping_id", "artifact_id", "id")

_NESTED_CONTAINERS = ("market_attempt_summary", "market_context", "market",
                      "context")


def _first(record: Dict[str, Any], containers: List[Dict[str, Any]],
           keys: Tuple[str, ...]) -> Any:
    for key in keys:
        if key in record and record[key] is not None:
            return record[key]
    for container in containers:
        for key in keys:
            if key in container and container[key] is not None:
                return container[key]
    return None


def _last_attempt(record: Dict[str, Any]) -> Dict[str, Any]:
    summary = record.get("market_attempt_summary")
    if isinstance(summary, dict):
        attempts = summary.get("attempts")
        if isinstance(attempts, list) and attempts:
            last = attempts[-1]
            if isinstance(last, dict):
                return last
    return {}


def normalize_record(record: Any, source_file: Optional[str] = None,
                     source_line: int = 0) -> Optional[CandidateSnapshot]:
    """Map one parsed JSONL record to a CandidateSnapshot, or None.

    Returns None when the record carries no usable mint or timestamp
    (e.g. an axiom fee record, a config echo, or malformed data).
    """
    if not isinstance(record, dict):
        return None
    containers = [
        record[name] for name in _NESTED_CONTAINERS
        if isinstance(record.get(name), dict)
    ]

    mint = _first(record, containers, _MINT_KEYS)
    if not isinstance(mint, str) or not mint.strip():
        return None
    ts_epoch = parse_utc(_first(record, containers, _TS_KEYS))
    if ts_epoch is None:
        return None

    attempt = _last_attempt(record)
    price = parse_number(_first(record, containers, _PRICE_KEYS))
    if price is None:
        price = parse_number(attempt.get("price_value"))
    market_cap = parse_number(_first(record, containers, _MC_KEYS))
    if market_cap is None:
        market_cap = parse_number(attempt.get("mc_value"))
    liquidity = parse_number(_first(record, containers, _LP_KEYS))
    if liquidity is None:
        liquidity = parse_number(attempt.get("lp_value"))

    symbol = _first(record, containers, _SYMBOL_KEYS)
    if not isinstance(symbol, str) or not symbol.strip():
        symbol = None

    snapshot = CandidateSnapshot(
        ts_epoch=ts_epoch,
        mint=mint.strip(),
        candidate_id=_first(record, containers, _CANDIDATE_ID_KEYS),
        symbol=symbol,
        price_usd=price if price is not None and price > 0 else None,
        market_cap_usd=(market_cap
                        if market_cap is not None and market_cap > 0 else None),
        liquidity_usd=(liquidity
                       if liquidity is not None and liquidity >= 0 else None),
        volume_usd=parse_number(_first(record, containers, _VOLUME_KEYS)),
        supply=parse_number(_first(record, containers, _SUPPLY_KEYS)),
        tier=parse_tier(_first(record, containers, _TIER_KEYS)),
        drawdown_pct=parse_pct_text(_first(record, containers, _DRAWDOWN_KEYS)),
        ath_market_cap_usd=parse_money_text(
            _first(record, containers, _ATH_KEYS)),
        score=parse_number(_first(record, containers, _SCORE_KEYS)),
        migration_ts_epoch=parse_utc(record.get("migration_time_utc")),
        source_kind=record.get("kind") if isinstance(record.get("kind"), str)
        else None,
        source_file=source_file,
        source_line=source_line,
        extra={},
    )
    return snapshot


# ---------------------------------------------------------------------------
# File discovery + replay stream
# ---------------------------------------------------------------------------


def discover_input_files(paths: Iterable[str]) -> List[str]:
    """Expand files / directories / glob patterns into a sorted file list."""
    found: List[str] = []
    for raw in paths:
        text = str(raw)
        path = Path(text)
        if path.is_file():
            found.append(str(path))
        elif path.is_dir():
            found.extend(str(p) for p in path.rglob("*.jsonl"))
        elif any(ch in text for ch in "*?["):
            for hit in _glob.glob(text, recursive=True):
                hit_path = Path(hit)
                if hit_path.is_file():
                    found.append(str(hit_path))
                elif hit_path.is_dir():
                    found.extend(str(p) for p in hit_path.rglob("*.jsonl"))
    # Dedupe while keeping deterministic (sorted) order.
    return sorted(set(os.path.normpath(p) for p in found))


def load_snapshots(paths: Iterable[str],
                   include_kinds: Optional[Iterable[str]] = None,
                   ) -> Tuple[List[CandidateSnapshot], List[Dict[str, Any]]]:
    """Load + normalize + time-sort snapshots from JSONL inputs.

    Returns ``(snapshots, errors)``; errors carry file/line/problem text for
    the error ledger and never raise.
    """
    kinds = set(include_kinds) if include_kinds else None
    snapshots: List[CandidateSnapshot] = []
    errors: List[Dict[str, Any]] = []
    for file_path in discover_input_files(paths):
        try:
            with io.open(file_path, "r", encoding="utf-8") as handle:
                for line_no, line in enumerate(handle, start=1):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError as exc:
                        errors.append({
                            "kind": "PARSE_ERROR",
                            "file": file_path,
                            "line": line_no,
                            "error": str(exc),
                        })
                        continue
                    snap = normalize_record(record, file_path, line_no)
                    if snap is None:
                        continue
                    if kinds is not None and snap.source_kind not in kinds:
                        continue
                    snapshots.append(snap)
        except OSError as exc:
            errors.append({
                "kind": "READ_ERROR",
                "file": file_path,
                "line": 0,
                "error": str(exc),
            })
    snapshots.sort(key=lambda s: s.sort_key())
    return snapshots, errors


class TailingSnapshotSource:
    """Incremental reader for live paper mode.

    Tracks byte offsets per file and yields only newly appended records on
    each ``poll()``. Read-only on the input files; safe to point at a
    directory another process is appending to.
    """

    def __init__(self, paths: Iterable[str],
                 include_kinds: Optional[Iterable[str]] = None) -> None:
        self._paths = [str(p) for p in paths]
        self._kinds = set(include_kinds) if include_kinds else None
        self._offsets: Dict[str, int] = {}

    @property
    def offsets(self) -> Dict[str, int]:
        """Per-file byte offsets consumed so far (checkpointable)."""
        return dict(self._offsets)

    def set_offsets(self, offsets: Dict[str, int]) -> None:
        """Restore previously checkpointed offsets so a restarted live run
        does not reprocess already-consumed records."""
        self._offsets = {
            str(path): int(offset)
            for path, offset in (offsets or {}).items()
            if isinstance(offset, (int, float)) and int(offset) >= 0
        }

    def poll(self) -> Tuple[List[CandidateSnapshot], List[Dict[str, Any]]]:
        snapshots: List[CandidateSnapshot] = []
        errors: List[Dict[str, Any]] = []
        for file_path in discover_input_files(self._paths):
            offset = self._offsets.get(file_path, 0)
            try:
                size = os.path.getsize(file_path)
                if size <= offset:
                    continue
                with io.open(file_path, "r", encoding="utf-8") as handle:
                    handle.seek(offset)
                    chunk = handle.read()
                    # Only consume complete lines; partial tail is re-read
                    # on the next poll.
                    last_newline = chunk.rfind("\n")
                    if last_newline < 0:
                        continue
                    consumed = chunk[: last_newline + 1]
                    self._offsets[file_path] = offset + len(
                        consumed.encode("utf-8"))
                for line_no, line in enumerate(consumed.splitlines(), start=1):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError as exc:
                        errors.append({
                            "kind": "PARSE_ERROR",
                            "file": file_path,
                            "line": line_no,
                            "error": str(exc),
                        })
                        continue
                    snap = normalize_record(record, file_path, line_no)
                    if snap is None:
                        continue
                    if self._kinds is not None and snap.source_kind not in self._kinds:
                        continue
                    snapshots.append(snap)
            except OSError as exc:
                errors.append({
                    "kind": "READ_ERROR",
                    "file": file_path,
                    "line": 0,
                    "error": str(exc),
                })
        snapshots.sort(key=lambda s: s.sort_key())
        return snapshots, errors


__all__ = [
    "normalize_record",
    "discover_input_files",
    "load_snapshots",
    "TailingSnapshotSource",
]

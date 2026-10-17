"""PHX2 terminal watch history (PHX2-E2E-002).

Append-only, digest-sealed archive for candidates that reached a terminal
watch state (EXPIRED / SENT_OK_COMMITTED / permanent drop / dedupe-completed /
legacy SEND_ATTEMPTED). Terminal candidates leave the active scheduling map so
the configured watchlist capacity bounds *concurrently active* work instead of
process-lifetime history, while every terminal transition keeps a durable,
auditable record here.

Contract:

- One JSONL line per unique terminal transition, keyed by a stable digest over
  ``(candidate_id, token_mint, terminal_status, transition_version)`` so a
  retried or replayed transition can never create a second row.
- Every record carries a ``record_digest`` sealing its full payload; a record
  that fails digest or schema validation on load fails CLOSED
  (``TerminalHistoryCorruptionError``) and is never silently skipped.
- This archive is auditable history only. It is NEVER consulted for
  successful-send dedupe; the durable successful-send ledger (PHX2-E2E-001)
  remains authoritative for that.
- No secrets, endpoints, or provider credentials are ever written here: fields
  are closed-set status tokens, mints, candidate ids, ISO timestamps, decimal
  strings, digests, and counts.

This module performs no reserve, transport, provider, or network action.
"""

from __future__ import annotations

import hashlib
import json
import os
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple


TERMINAL_HISTORY_SCHEMA_VERSION = "phx2_watch_terminal_history_v1"
TERMINAL_TRANSITION_VERSION = "phx2_watch_terminal_transition_v1"

ARCHIVE_OUTCOME_ARCHIVED = "ARCHIVED"
ARCHIVE_OUTCOME_DUPLICATE = "DUPLICATE_SUPPRESSED"
ARCHIVE_OUTCOME_UNAVAILABLE = "ARCHIVE_UNAVAILABLE"

# The evidence fields a terminal-history record must always carry (values may
# be null when the run never observed them; keys must exist).
_REQUIRED_FIELDS = (
    "schema_version",
    "terminal_transition_version",
    "terminal_history_key",
    "candidate_id",
    "token_mint",
    "migration_time_utc",
    "migration_proof_reference",
    "seeded_at_utc",
    "terminal_at_utc",
    "terminal_status",
    "terminal_reason",
    "baseline_market_cap_usd",
    "baseline_source",
    "baseline_observed_at_utc",
    "baseline_status",
    "latest_ath_market_cap_usd",
    "latest_ath_observed_at_utc",
    "activation_result",
    "activated_at_utc",
    "activation_target_market_cap_usd",
    "activation_proof_digest",
    "latest_tier",
    "fee_gate_lifecycle_state",
    "risk_label",
    "market_state",
    "market_reason_code",
    "delivery_state",
    "delivery_ledger_key",
    "delivery_receipt_digest",
    "recheck_count",
    "record_digest",
)


class TerminalHistoryCorruptionError(ValueError):
    """A persisted terminal-history record failed schema/digest validation."""


def _json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        return format(value, "f")
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        return repr(value)
    return str(value)


def _sha256_payload(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        dict(payload), sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def build_terminal_history_key(
    *, candidate_id: str, token_mint: str, terminal_status: str
) -> str:
    """Stable idempotency key: one archived row per terminal transition."""

    return _sha256_payload({
        "terminal_transition_version": TERMINAL_TRANSITION_VERSION,
        "candidate_id": str(candidate_id or ""),
        "token_mint": str(token_mint or ""),
        "terminal_status": str(terminal_status or ""),
    })


def build_terminal_history_record(
    *,
    token_mint: str,
    candidate_id: str,
    terminal_status: str,
    terminal_reason: Optional[str],
    terminal_at_utc: str,
    seeded_at_utc: Optional[str],
    migration_time_utc: Optional[str] = None,
    migration_proof_reference: Optional[str] = None,
    baseline_market_cap_usd: Optional[str] = None,
    baseline_source: Optional[str] = None,
    baseline_observed_at_utc: Optional[str] = None,
    baseline_status: Optional[str] = None,
    activation_result: bool = False,
    activated_at_utc: Optional[str] = None,
    activation_target_market_cap_usd: Optional[str] = None,
    activation_proof_digest: Optional[str] = None,
    market_state: Optional[str] = None,
    market_reason_code: Optional[str] = None,
    delivery_state: Optional[str] = None,
    delivery_ledger_key: Optional[str] = None,
    delivery_receipt_digest: Optional[str] = None,
    recheck_count: int = 0,
    context: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Build a sealed terminal-history record. ``context`` may add the latest
    ATH / tier / Fee Gate / risk evidence when the caller has it; absent
    evidence stays explicitly null rather than being fabricated."""

    ctx = dict(context or {})
    record: Dict[str, Any] = {
        "schema_version": TERMINAL_HISTORY_SCHEMA_VERSION,
        "terminal_transition_version": TERMINAL_TRANSITION_VERSION,
        "terminal_history_key": build_terminal_history_key(
            candidate_id=candidate_id,
            token_mint=token_mint,
            terminal_status=terminal_status,
        ),
        "candidate_id": _json_safe(candidate_id),
        "token_mint": _json_safe(token_mint),
        "migration_time_utc": _json_safe(migration_time_utc),
        "migration_proof_reference": _json_safe(migration_proof_reference),
        "seeded_at_utc": _json_safe(seeded_at_utc),
        "terminal_at_utc": _json_safe(terminal_at_utc),
        "terminal_status": _json_safe(terminal_status),
        "terminal_reason": _json_safe(terminal_reason),
        "baseline_market_cap_usd": _json_safe(baseline_market_cap_usd),
        "baseline_source": _json_safe(baseline_source),
        "baseline_observed_at_utc": _json_safe(baseline_observed_at_utc),
        "baseline_status": _json_safe(baseline_status),
        "latest_ath_market_cap_usd": _json_safe(
            ctx.get("latest_ath_market_cap_usd")),
        "latest_ath_observed_at_utc": _json_safe(
            ctx.get("latest_ath_observed_at_utc")),
        "activation_result": bool(activation_result),
        "activated_at_utc": _json_safe(activated_at_utc),
        "activation_target_market_cap_usd": _json_safe(
            activation_target_market_cap_usd),
        "activation_proof_digest": _json_safe(activation_proof_digest),
        "latest_tier": _json_safe(ctx.get("latest_tier")),
        "fee_gate_lifecycle_state": _json_safe(
            ctx.get("fee_gate_lifecycle_state")),
        "risk_label": _json_safe(ctx.get("risk_label")),
        "market_state": _json_safe(market_state),
        "market_reason_code": _json_safe(market_reason_code),
        "delivery_state": _json_safe(delivery_state),
        "delivery_ledger_key": _json_safe(delivery_ledger_key),
        "delivery_receipt_digest": _json_safe(delivery_receipt_digest),
        "recheck_count": int(recheck_count or 0),
    }
    record["record_digest"] = _sha256_payload(record)
    return record


def validate_terminal_history_record(record: Any) -> Tuple[bool, str]:
    """Total validation used on every load and before every append."""

    if not isinstance(record, dict):
        return False, "RECORD_NOT_AN_OBJECT"
    if record.get("schema_version") != TERMINAL_HISTORY_SCHEMA_VERSION:
        return False, "SCHEMA_VERSION_UNSUPPORTED"
    if record.get("terminal_transition_version") != TERMINAL_TRANSITION_VERSION:
        return False, "TRANSITION_VERSION_UNSUPPORTED"
    missing = [key for key in _REQUIRED_FIELDS if key not in record]
    if missing:
        return False, "REQUIRED_FIELD_MISSING:" + missing[0]
    mint = record.get("token_mint")
    status = record.get("terminal_status")
    if not isinstance(mint, str) or not mint:
        return False, "TOKEN_MINT_INVALID"
    if not isinstance(status, str) or not status:
        return False, "TERMINAL_STATUS_INVALID"
    expected_key = build_terminal_history_key(
        candidate_id=str(record.get("candidate_id") or ""),
        token_mint=mint,
        terminal_status=status,
    )
    if record.get("terminal_history_key") != expected_key:
        return False, "TERMINAL_HISTORY_KEY_MISMATCH"
    digest = record.get("record_digest")
    body = {k: v for k, v in record.items() if k != "record_digest"}
    if not isinstance(digest, str) or digest != _sha256_payload(body):
        return False, "RECORD_DIGEST_MISMATCH"
    return True, ""


class TerminalHistoryArchive:
    """Append-only durable terminal-history store with an O(1) key index.

    ``path=None`` keeps the archive purely in memory (offline harnesses and
    legacy constructors); a real path makes every append durable (flush+fsync)
    BEFORE the caller may evict the candidate from active state.
    """

    def __init__(self, path: object = None) -> None:
        self._path: Optional[Path] = Path(path) if path is not None else None
        self._keys: set = set()
        self._status_by_mint: Dict[str, str] = {}
        self._by_status: Dict[str, int] = {}
        self._record_count = 0
        self._activated_count = 0
        if self._path is not None and self._path.exists():
            self._load_existing()

    def _load_existing(self) -> None:
        assert self._path is not None
        try:
            text = self._path.read_text(encoding="utf-8")
        except OSError as exc:
            raise TerminalHistoryCorruptionError(
                f"TERMINAL_HISTORY_UNREADABLE:{type(exc).__name__}") from exc
        for line_number, raw in enumerate(text.splitlines(), start=1):
            line = raw.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except ValueError as exc:
                raise TerminalHistoryCorruptionError(
                    f"TERMINAL_HISTORY_LINE_UNPARSEABLE:line={line_number}"
                ) from exc
            ok, reason = validate_terminal_history_record(record)
            if not ok:
                raise TerminalHistoryCorruptionError(
                    f"TERMINAL_HISTORY_RECORD_INVALID:line={line_number}:{reason}")
            self._index(record)

    def _index(self, record: Mapping[str, Any]) -> None:
        key = record["terminal_history_key"]
        if key in self._keys:
            return
        self._keys.add(key)
        self._record_count += 1
        status = str(record.get("terminal_status") or "")
        self._by_status[status] = self._by_status.get(status, 0) + 1
        self._status_by_mint[str(record.get("token_mint") or "")] = status
        if record.get("activation_result"):
            self._activated_count += 1

    @property
    def path(self) -> Optional[Path]:
        return self._path

    @property
    def count(self) -> int:
        return self._record_count

    @property
    def activated_count(self) -> int:
        return self._activated_count

    def by_status(self) -> Dict[str, int]:
        return dict(self._by_status)

    def has_key(self, key: object) -> bool:
        return key in self._keys

    def has_mint(self, mint: object) -> bool:
        return isinstance(mint, str) and mint in self._status_by_mint

    def status_for_mint(self, mint: object) -> Optional[str]:
        if not isinstance(mint, str):
            return None
        return self._status_by_mint.get(mint)

    def archive(self, record: Mapping[str, Any]) -> Tuple[bool, str]:
        """Idempotently persist one validated terminal-history record.

        Returns ``(True, ARCHIVED)`` on a durable new row,
        ``(True, DUPLICATE_SUPPRESSED)`` when the transition key is already
        archived (exactly-once retry semantics), and ``(False, reason)`` when
        the record is invalid or the durable append failed — in which case the
        caller MUST keep the candidate's state and retry later."""

        ok, reason = validate_terminal_history_record(dict(record))
        if not ok:
            return False, "RECORD_INVALID:" + reason
        key = record["terminal_history_key"]
        if key in self._keys:
            return True, ARCHIVE_OUTCOME_DUPLICATE
        if self._path is not None:
            line = json.dumps(
                dict(record), sort_keys=True, separators=(",", ":"),
                ensure_ascii=True)
            try:
                self._path.parent.mkdir(parents=True, exist_ok=True)
                with self._path.open("a", encoding="utf-8", newline="") as handle:
                    handle.write(line + "\n")
                    handle.flush()
                    os.fsync(handle.fileno())
            except OSError as exc:
                return False, f"ARCHIVE_WRITE_FAILED:{type(exc).__name__}"
        self._index(record)
        return True, ARCHIVE_OUTCOME_ARCHIVED


__all__ = (
    "TERMINAL_HISTORY_SCHEMA_VERSION",
    "TERMINAL_TRANSITION_VERSION",
    "ARCHIVE_OUTCOME_ARCHIVED",
    "ARCHIVE_OUTCOME_DUPLICATE",
    "ARCHIVE_OUTCOME_UNAVAILABLE",
    "TerminalHistoryCorruptionError",
    "TerminalHistoryArchive",
    "build_terminal_history_key",
    "build_terminal_history_record",
    "validate_terminal_history_record",
)

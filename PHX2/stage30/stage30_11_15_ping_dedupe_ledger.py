"""Stage 30.11.15 private operator ping dedupe ledger implementations.

Two implementations of the Stage 30.11.15 ``PingDedupeLedger`` Protocol -- the
committed cross-run suppression surface for the private operator ping path:

  * ``InMemoryPingDedupeLedger`` -- no I/O, deterministic, for the offline unit
    suite + the diagnostic no-send fake proof.
  * ``JsonlPingDedupeLedger``    -- append-only JSONL ledger with cross-run state
    reconstruction via replay. The operator supplies a ``pathlib.Path``; the
    parent directory must already exist; the ledger never calls ``mkdir`` /
    ``unlink`` / ``rename`` / ``replace`` and never imports ``shutil``. This is
    the implementation that closes the independent-audit cross-run dedupe gap:
    its persisted state survives a process restart, so the SAME mint / state /
    tier cannot repeatedly produce a dispatch-eligible private operator ping.

Both implementations share one method -- ``check_and_reserve`` -- which is the
atomic check-then-reserve the guard runs on the frozen Stage 30.11.13 snapshot
BEFORE dispatch:

  * a key NOT present (a genuinely new state class -- a new mint / tier /
    drawdown band / ATH-verification flip / policy version) -> reserve + return
    ``DEDUPE_ALLOWED`` (``DEDUPE_REASON_NEW_KEY``);
  * a key present whose last reservation is OLDER than ``ttl_seconds`` (the
    unchanged state aged out) -> reserve + return ``DEDUPE_ALLOWED``
    (``DEDUPE_REASON_TTL_EXPIRED``);
  * a key present and reserved WITHIN ``ttl_seconds`` -> NO write, return
    ``DEDUPE_SUPPRESSED_DUPLICATE`` (``DEDUPE_REASON_DUPLICATE_WITHIN_TTL``);
  * a malformed key / now timestamp / ttl, an unreadable / corrupt ledger, or a
    reserve write failure -> ``DEDUPE_UNAVAILABLE`` (fail closed; the guard /
    composer then withhold dispatch with transport_attempts 0).

TTL math uses ONLY caller-injected ISO-8601 timestamps: the ``now_utc`` the
guard reads off the frozen snapshot's ``created_at_utc`` and the persisted
``reserved_at_utc``. ``datetime`` is used to PARSE only; this module NEVER calls
``datetime.now`` / ``utcnow`` (no wall-clock read), exactly as the committed
Stage 30.11.13 composer parses its injected timestamps.

Replay semantics for the JSONL ledger (all fail CLOSED, never raise):

  * Bad path type / ``..`` traversal segment / missing parent directory / path
    that exists but is not a regular file / unreadable file -> the ledger
    constructs in an UNAVAILABLE state (every ``check_and_reserve`` returns
    ``DEDUPE_UNAVAILABLE`` with ``DEDUPE_REASON_LEDGER_UNAVAILABLE``).
  * A blank line / malformed JSON / wrong field set / wrong field type / unknown
    schema_version / empty required field / unparseable ``reserved_at_utc`` ->
    the ledger constructs in an UNAVAILABLE state with
    ``DEDUPE_REASON_LEDGER_CORRUPT``.
  * Missing file with an existing parent -> empty state, ready to write.
  * A later line for an already-seen key on replay -> the latest
    ``reserved_at_utc`` wins (the most recent reservation drives TTL).

Single-writer assumption: the operator is responsible for not pointing two
processes at the same path concurrently. Stage 30.11.15 provides no multi-process
coordination.

This module imports only stdlib (``json`` / ``pathlib`` / ``datetime`` /
``typing``) plus the Stage 30.11.15 models sibling. It reads NO process
environment, makes NO network / Discord / provider call, opens NO database, runs
NO daemon / loop, signs nothing, and trades nothing. The real private compact
dispatch / Discord send remains a SEPARATE, explicitly operator-authorized step
this slice does not build.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional, Protocol, Tuple

from PHX2.stage30.stage30_11_15_ping_dedupe_models import (
    DEDUPE_REASON_DUPLICATE_WITHIN_TTL,
    DEDUPE_REASON_LEDGER_CORRUPT,
    DEDUPE_REASON_LEDGER_UNAVAILABLE,
    DEDUPE_REASON_LEDGER_WRITE_FAILED,
    DEDUPE_REASON_MALFORMED_KEY,
    DEDUPE_REASON_NEW_KEY,
    DEDUPE_REASON_TTL_EXPIRED,
    STAGE30_11_15_LEDGER_RECORD_FIELDS,
    STAGE30_11_15_LEDGER_RECORD_SCHEMA_VERSION,
    STAGE30_11_15_LEDGER_REQUIRED_NON_EMPTY_FIELDS,
    STAGE30_11_15_LEDGER_RESERVED_AT_FIELD,
    STAGE30_11_15_LEDGER_SCHEMA_FIELD,
    Stage30_11_15PingDedupeKey,
    Stage30_11_15PingDedupeOutcome,
    allowed_outcome,
    canonical_ping_dedupe_key_tuple,
    is_ping_dedupe_key,
    suppressed_outcome,
    unavailable_outcome,
)


_KeyTuple = Tuple[str, str, str, str, bool, str, str]


# ---------------------------------------------------------------------------
# Pure helpers (timestamp parse, ttl shape, classify, record codec)
# ---------------------------------------------------------------------------


def _parse_iso_utc_to_unix(value: object) -> Optional[int]:
    """Parse an ISO-8601 UTC timestamp to an int unix second, or ``None`` when
    unparseable.

    Accepts a trailing ``Z`` or an explicit offset; a naive timestamp is treated
    as UTC. Pure; never raises and NEVER reads a wall clock (``datetime`` is used
    to PARSE only -- no ``datetime.now`` / ``utcnow``). Mirrors the committed
    Stage 30.11.13 ``_parse_iso_utc_to_unix`` BY VALUE.
    """
    if not isinstance(value, str):
        return None
    candidate = value.strip()
    if candidate == "":
        return None
    if candidate.endswith("Z"):
        candidate = candidate[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(candidate)
    except (ValueError, TypeError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return int(parsed.astimezone(timezone.utc).timestamp())


def _is_valid_ttl_seconds(value: object) -> bool:
    """Return ``True`` iff ``value`` is a non-negative ``int`` (not a ``bool``).

    Pure / total; never raises.
    """
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _classify_existing(
    *, existing_unix: Optional[int], now_unix: int, ttl_seconds: int
) -> Tuple[bool, str]:
    """Classify a lookup into ``(should_reserve, reason)``.

    Pure / total. A key not present is NEW (reserve). A key whose last
    reservation is within ``ttl_seconds`` of ``now`` is a duplicate (no reserve).
    Otherwise the unchanged state aged out and is allowed again (reserve). A
    ``now`` that precedes the stored reservation (a backwards clock) is treated as
    within TTL -> suppress (fail safe; never an extra ping).
    """
    if existing_unix is None:
        return True, DEDUPE_REASON_NEW_KEY
    if (now_unix - existing_unix) < ttl_seconds:
        return False, DEDUPE_REASON_DUPLICATE_WITHIN_TTL
    return True, DEDUPE_REASON_TTL_EXPIRED


def _serialize_record(
    *, key: Stage30_11_15PingDedupeKey, reserved_at_utc: str
) -> str:
    """Serialize a reservation to a deterministic JSON line (sorted keys, compact
    separators, no trailing newline; the caller appends the newline).
    """
    record = {
        STAGE30_11_15_LEDGER_SCHEMA_FIELD: (
            STAGE30_11_15_LEDGER_RECORD_SCHEMA_VERSION
        ),
        "token_mint": key.token_mint,
        "operator_signal_kind": key.operator_signal_kind,
        "tier_token": key.tier_token,
        "drawdown_band": key.drawdown_band,
        "post_migration_ath_verified": key.post_migration_ath_verified,
        "ath_source_stage": key.ath_source_stage,
        "policy_version": key.policy_version,
        STAGE30_11_15_LEDGER_RESERVED_AT_FIELD: reserved_at_utc,
    }
    return json.dumps(record, sort_keys=True, separators=(",", ":"))


def _decode_record(raw: str) -> Optional[dict]:
    """Decode + validate one JSONL record line; return the validated field map,
    or ``None`` on ANY contract violation (the caller treats ``None`` as a
    corrupt ledger and fails closed). Pure / total; never raises.
    """
    try:
        decoded = json.loads(raw)
    except ValueError:
        return None
    if not isinstance(decoded, dict):
        return None
    if set(decoded.keys()) != set(STAGE30_11_15_LEDGER_RECORD_FIELDS):
        return None
    if decoded[STAGE30_11_15_LEDGER_SCHEMA_FIELD] != (
        STAGE30_11_15_LEDGER_RECORD_SCHEMA_VERSION
    ):
        return None
    if not isinstance(decoded["post_migration_ath_verified"], bool):
        return None
    for field in STAGE30_11_15_LEDGER_RECORD_FIELDS:
        if field == "post_migration_ath_verified":
            continue
        if not isinstance(decoded[field], str):
            return None
    for field in STAGE30_11_15_LEDGER_REQUIRED_NON_EMPTY_FIELDS:
        if decoded[field].strip() == "":
            return None
    return decoded


def _key_tuple_from_record(decoded: dict) -> _KeyTuple:
    """Project a validated decoded record onto the canonical key tuple."""
    return (
        decoded["token_mint"],
        decoded["operator_signal_kind"],
        decoded["tier_token"],
        decoded["drawdown_band"],
        decoded["post_migration_ath_verified"],
        decoded["ath_source_stage"],
        decoded["policy_version"],
    )


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


class PingDedupeLedger(Protocol):
    """The Stage 30.11.15 ping dedupe ledger contract.

    One method: ``check_and_reserve`` -- atomically decide whether a key is a
    duplicate within ``ttl_seconds`` of ``now_utc`` and, when allowed, reserve it
    (so the next run sees it). Returns a closed-set ``Stage30_11_15PingDedupeOutcome``
    and NEVER raises (fail closed to ``DEDUPE_UNAVAILABLE``).
    """

    def check_and_reserve(
        self,
        *,
        key: Stage30_11_15PingDedupeKey,
        now_utc: str,
        ttl_seconds: int,
    ) -> Stage30_11_15PingDedupeOutcome:
        ...


# ---------------------------------------------------------------------------
# InMemoryPingDedupeLedger
# ---------------------------------------------------------------------------


class InMemoryPingDedupeLedger:
    """In-memory ``PingDedupeLedger`` implementation.

    No I/O, no clock, no env reads. Deterministic; for the offline unit suite +
    the diagnostic no-send fake proof. It does NOT survive a process restart, so
    it does NOT by itself close the cross-run dedupe gap -- the JSONL ledger is
    the cross-run-durable production choice. ``check_and_reserve`` never raises.
    """

    def __init__(self) -> None:
        self._state: Dict[_KeyTuple, int] = {}

    def check_and_reserve(
        self,
        *,
        key: Stage30_11_15PingDedupeKey,
        now_utc: str,
        ttl_seconds: int,
    ) -> Stage30_11_15PingDedupeOutcome:
        if not is_ping_dedupe_key(key):
            return unavailable_outcome(DEDUPE_REASON_MALFORMED_KEY)
        if not _is_valid_ttl_seconds(ttl_seconds):
            return unavailable_outcome(DEDUPE_REASON_LEDGER_UNAVAILABLE)
        now_unix = _parse_iso_utc_to_unix(now_utc)
        if now_unix is None:
            return unavailable_outcome(DEDUPE_REASON_LEDGER_UNAVAILABLE)
        tup = canonical_ping_dedupe_key_tuple(key)
        should_reserve, reason = _classify_existing(
            existing_unix=self._state.get(tup),
            now_unix=now_unix,
            ttl_seconds=ttl_seconds,
        )
        if not should_reserve:
            return suppressed_outcome(DEDUPE_REASON_DUPLICATE_WITHIN_TTL)
        self._state[tup] = now_unix
        return allowed_outcome(reason)


# ---------------------------------------------------------------------------
# JsonlPingDedupeLedger
# ---------------------------------------------------------------------------


class JsonlPingDedupeLedger:
    """Append-only JSONL ``PingDedupeLedger`` implementation (cross-run durable).

    On construction the ledger replays the existing file (if any) and rebuilds
    the in-memory last-reservation map. Every reservation appends one line via
    ``pathlib.Path.open`` (flushed + closed by the context manager). A duplicate
    within TTL appends nothing.

    Construction is TOTAL (it never raises): a bad path / traversal segment /
    missing parent / non-file / unreadable file leaves the ledger in an
    UNAVAILABLE state, and a corrupt line leaves it UNAVAILABLE with the corrupt
    reason; either way every ``check_and_reserve`` returns ``DEDUPE_UNAVAILABLE``
    so the guard / composer fail closed.

    Single-writer assumption: the operator must not point two processes at the
    same path concurrently.
    """

    def __init__(self, *, path: object) -> None:
        self._path: Optional[Path] = path if isinstance(path, Path) else None
        self._state: Dict[_KeyTuple, int] = {}
        self._available: bool = True
        self._unavailable_reason: str = ""
        try:
            self._init_replay(path)
        except OSError:
            self._mark_unavailable(DEDUPE_REASON_LEDGER_UNAVAILABLE)

    def _mark_unavailable(self, reason: str) -> None:
        self._available = False
        self._unavailable_reason = reason

    def _init_replay(self, path: object) -> None:
        if not isinstance(path, Path) or ".." in path.parts:
            self._mark_unavailable(DEDUPE_REASON_LEDGER_UNAVAILABLE)
            return
        parent = path.parent
        if not parent.exists() or not parent.is_dir():
            self._mark_unavailable(DEDUPE_REASON_LEDGER_UNAVAILABLE)
            return
        if path.exists() and not path.is_file():
            self._mark_unavailable(DEDUPE_REASON_LEDGER_UNAVAILABLE)
            return
        if not path.exists():
            return
        with path.open("r", encoding="utf-8") as f:
            for raw in f:
                stripped = raw.rstrip("\n")
                if stripped == "":
                    self._mark_unavailable(DEDUPE_REASON_LEDGER_CORRUPT)
                    return
                decoded = _decode_record(stripped)
                if decoded is None:
                    self._mark_unavailable(DEDUPE_REASON_LEDGER_CORRUPT)
                    return
                reserved_unix = _parse_iso_utc_to_unix(
                    decoded[STAGE30_11_15_LEDGER_RESERVED_AT_FIELD]
                )
                if reserved_unix is None:
                    self._mark_unavailable(DEDUPE_REASON_LEDGER_CORRUPT)
                    return
                # The latest line for a key wins (most recent reservation).
                self._state[_key_tuple_from_record(decoded)] = reserved_unix

    def _append_record(
        self, *, key: Stage30_11_15PingDedupeKey, reserved_at_utc: str
    ) -> None:
        line = _serialize_record(key=key, reserved_at_utc=reserved_at_utc)
        # Append via ``pathlib.Path.open`` (the established Stage 30.2 / 30.8
        # append-only writer discipline; no ``os`` import). The context manager
        # flushes + closes; an OSError propagates to the fail-closed caller.
        with self._path.open("a", encoding="utf-8", newline="") as f:
            f.write(line + "\n")

    def check_and_reserve(
        self,
        *,
        key: Stage30_11_15PingDedupeKey,
        now_utc: str,
        ttl_seconds: int,
    ) -> Stage30_11_15PingDedupeOutcome:
        if not self._available:
            return unavailable_outcome(
                self._unavailable_reason or DEDUPE_REASON_LEDGER_UNAVAILABLE
            )
        if not is_ping_dedupe_key(key):
            return unavailable_outcome(DEDUPE_REASON_MALFORMED_KEY)
        if not _is_valid_ttl_seconds(ttl_seconds):
            return unavailable_outcome(DEDUPE_REASON_LEDGER_UNAVAILABLE)
        now_unix = _parse_iso_utc_to_unix(now_utc)
        if now_unix is None:
            return unavailable_outcome(DEDUPE_REASON_LEDGER_UNAVAILABLE)
        tup = canonical_ping_dedupe_key_tuple(key)
        should_reserve, reason = _classify_existing(
            existing_unix=self._state.get(tup),
            now_unix=now_unix,
            ttl_seconds=ttl_seconds,
        )
        if not should_reserve:
            return suppressed_outcome(DEDUPE_REASON_DUPLICATE_WITHIN_TTL)
        try:
            self._append_record(key=key, reserved_at_utc=now_utc)
        except OSError:
            return unavailable_outcome(DEDUPE_REASON_LEDGER_WRITE_FAILED)
        self._state[tup] = now_unix
        return allowed_outcome(reason)


__all__ = (
    "PingDedupeLedger",
    "InMemoryPingDedupeLedger",
    "JsonlPingDedupeLedger",
)

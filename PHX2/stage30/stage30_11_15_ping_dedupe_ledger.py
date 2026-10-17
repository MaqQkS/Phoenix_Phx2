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


_TIER_RANKS: Dict[str, int] = {"Tier 1": 1, "Tier 2": 2, "Tier 3": 3}


def _tier_rank(tier_token: object) -> Optional[int]:
    """Closed-set tier ordinal, or ``None`` for an unrecognized token.

    Pure / total; an unknown tier token never participates in the regression
    comparison (fail open to the ordinary same-key classification, never to an
    extra ping).
    """
    if not isinstance(tier_token, str):
        return None
    return _TIER_RANKS.get(tier_token)


#: The lifetime tier-monotonicity SCOPE: mint + operator_signal_kind +
#: policy_version -- deliberately none of the other key axes, so no amount of
#: state loss (band / ATH-verification flag / source stage all change across
#: a restart re-admission) can re-key around the guard.
_TierScopeKey = Tuple[str, str, str]


def _tier_scope(key: Stage30_11_15PingDedupeKey) -> _TierScopeKey:
    return (key.token_mint, key.operator_signal_kind, key.policy_version)


def _note_reserved_tier(
    index: Dict[_TierScopeKey, int], *, scope: _TierScopeKey,
    tier_token: object,
) -> None:
    """Fold one AUTHORITATIVE reservation into the highest-tier index.

    Idempotent (``max``); an unrecognized tier token never enters the index
    (mirroring the guard, which never judges an unknown tier).  Callers invoke
    this ONLY after a reservation is durable/authoritative -- a failed append
    must leave the index exactly as it was.
    """
    rank = _tier_rank(tier_token)
    if rank is None:
        return
    if rank > index.get(scope, 0):
        index[scope] = rank


def _higher_tier_ever_reserved(
    highest_tier_by_scope: Dict[_TierScopeKey, int],
    *,
    key: Stage30_11_15PingDedupeKey,
) -> bool:
    """``True`` iff the same mint + signal kind + policy version has EVER held a
    STRICTLY HIGHER tier reservation, at any age.

    Highest-sent-tier monotonicity (2026-07-27 remediation): a candidate whose
    canonical state was lost across a process restart can legitimately re-enter
    at a LOWER tier with a different drawdown band / ATH-verification flag /
    source stage -- every axis of the exact-key lookup changes, so the exact-key
    dedupe alone cannot see the regression (proven live: Tier 2 sent 10:20:46Z,
    the SAME mint re-sent Tier 1 11:09:44Z after a restart wiped its state).
    The guard is deliberately LIFETIME-scoped over the append-only ledger, NOT
    TTL-scoped: the TTL exists so an UNCHANGED state may re-alert, but a mint
    that already alerted at a deeper tier never becomes new information at a
    shallower one -- "Tier 2 sent => no later Tier 1" holds for the whole
    ledger lifecycle, including after ordinary TTL expiry and across live /
    restart-backfill re-admission.  Tier ESCALATION (a strictly deeper tier)
    always remains allowed, and a policy-version bump intentionally re-opens
    alerting.

    2026-07-28 scalability fix: the check reads a DERIVED in-memory index
    (``highest_reserved_tier_by_scope``) built once during the single startup
    replay and folded forward on each authoritative reservation, so every
    classification is an O(1) dict lookup instead of an O(n) walk of the full
    replayed ledger state.  The append-only ledger remains the sole durable
    source of truth; the index is reconstructible from it verbatim.
    """
    candidate_rank = _tier_rank(key.tier_token)
    if candidate_rank is None:
        return False
    return highest_tier_by_scope.get(_tier_scope(key), 0) > candidate_rank


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
        #: Derived highest-reserved-tier index over the lifetime scope
        #: (mint, signal kind, policy version) -> tier rank.  O(1) per
        #: classification; folded forward only by authoritative reservations
        #: and fully reconstructible from ``_state``.
        self._highest_tier_by_scope: Dict[_TierScopeKey, int] = {}

    def _classify(
        self,
        *,
        key: Stage30_11_15PingDedupeKey,
        now_utc: str,
        ttl_seconds: int,
    ):
        if not is_ping_dedupe_key(key):
            return None, unavailable_outcome(DEDUPE_REASON_MALFORMED_KEY)
        if not _is_valid_ttl_seconds(ttl_seconds):
            return None, unavailable_outcome(DEDUPE_REASON_LEDGER_UNAVAILABLE)
        now_unix = _parse_iso_utc_to_unix(now_utc)
        if now_unix is None:
            return None, unavailable_outcome(DEDUPE_REASON_LEDGER_UNAVAILABLE)
        if _higher_tier_ever_reserved(self._highest_tier_by_scope, key=key):
            # A lower-tier alert for a mint that already reserved a higher
            # tier is a regression duplicate, never new information -- at any
            # age (lifetime monotonicity; escalation stays allowed).
            return None, suppressed_outcome(DEDUPE_REASON_DUPLICATE_WITHIN_TTL)
        tup = canonical_ping_dedupe_key_tuple(key)
        should_reserve, reason = _classify_existing(
            existing_unix=self._state.get(tup),
            now_unix=now_unix,
            ttl_seconds=ttl_seconds,
        )
        if not should_reserve:
            return None, suppressed_outcome(DEDUPE_REASON_DUPLICATE_WITHIN_TTL)
        return (tup, now_unix, reason), None

    def check_only(
        self,
        *,
        key: Stage30_11_15PingDedupeKey,
        now_utc: str,
        ttl_seconds: int,
    ) -> Stage30_11_15PingDedupeOutcome:
        """Classify without mutating: an allowed verdict reserves NOTHING."""
        plan, verdict = self._classify(
            key=key, now_utc=now_utc, ttl_seconds=ttl_seconds)
        if verdict is not None:
            return verdict
        return allowed_outcome(plan[2])

    def check_and_reserve(
        self,
        *,
        key: Stage30_11_15PingDedupeKey,
        now_utc: str,
        ttl_seconds: int,
    ) -> Stage30_11_15PingDedupeOutcome:
        plan, verdict = self._classify(
            key=key, now_utc=now_utc, ttl_seconds=ttl_seconds)
        if verdict is not None:
            return verdict
        tup, now_unix, reason = plan
        self._state[tup] = now_unix
        _note_reserved_tier(
            self._highest_tier_by_scope, scope=_tier_scope(key),
            tier_token=key.tier_token)
        return allowed_outcome(reason)

    def commit_confirmed_send(
        self,
        *,
        key: Stage30_11_15PingDedupeKey,
        now_utc: str,
        ttl_seconds: int,
    ) -> Stage30_11_15PingDedupeOutcome:
        """Record one CONFIRMED successful send. Idempotent: a key already
        reserved within TTL records nothing again (restart-safe replay)."""
        return self.check_and_reserve(
            key=key, now_utc=now_utc, ttl_seconds=ttl_seconds)


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
        #: Derived highest-reserved-tier index over the lifetime scope
        #: (mint, signal kind, policy version) -> tier rank.  Built once
        #: during the single startup replay of the append-only ledger, folded
        #: forward on each durable reservation; O(1) per classification and
        #: fully reconstructible from the ledger file.
        self._highest_tier_by_scope: Dict[_TierScopeKey, int] = {}
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
                _note_reserved_tier(
                    self._highest_tier_by_scope,
                    scope=(decoded["token_mint"],
                           decoded["operator_signal_kind"],
                           decoded["policy_version"]),
                    tier_token=decoded["tier_token"])

    def _append_record(
        self, *, key: Stage30_11_15PingDedupeKey, reserved_at_utc: str
    ) -> None:
        line = _serialize_record(key=key, reserved_at_utc=reserved_at_utc)
        # Append via ``pathlib.Path.open`` (the established Stage 30.2 / 30.8
        # append-only writer discipline; no ``os`` import). The context manager
        # flushes + closes; an OSError propagates to the fail-closed caller.
        with self._path.open("a", encoding="utf-8", newline="") as f:
            f.write(line + "\n")

    def _classify(
        self,
        *,
        key: Stage30_11_15PingDedupeKey,
        now_utc: str,
        ttl_seconds: int,
    ):
        if not self._available:
            return None, unavailable_outcome(
                self._unavailable_reason or DEDUPE_REASON_LEDGER_UNAVAILABLE
            )
        if not is_ping_dedupe_key(key):
            return None, unavailable_outcome(DEDUPE_REASON_MALFORMED_KEY)
        if not _is_valid_ttl_seconds(ttl_seconds):
            return None, unavailable_outcome(DEDUPE_REASON_LEDGER_UNAVAILABLE)
        now_unix = _parse_iso_utc_to_unix(now_utc)
        if now_unix is None:
            return None, unavailable_outcome(DEDUPE_REASON_LEDGER_UNAVAILABLE)
        if _higher_tier_ever_reserved(self._highest_tier_by_scope, key=key):
            # A lower-tier alert for a mint that already reserved a higher
            # tier is a regression duplicate, never new information -- at any
            # age (lifetime monotonicity; escalation stays allowed).
            return None, suppressed_outcome(DEDUPE_REASON_DUPLICATE_WITHIN_TTL)
        tup = canonical_ping_dedupe_key_tuple(key)
        should_reserve, reason = _classify_existing(
            existing_unix=self._state.get(tup),
            now_unix=now_unix,
            ttl_seconds=ttl_seconds,
        )
        if not should_reserve:
            return None, suppressed_outcome(DEDUPE_REASON_DUPLICATE_WITHIN_TTL)
        return (tup, now_unix, reason), None

    def check_only(
        self,
        *,
        key: Stage30_11_15PingDedupeKey,
        now_utc: str,
        ttl_seconds: int,
    ) -> Stage30_11_15PingDedupeOutcome:
        """Classify without mutating the ledger: an allowed verdict appends
        NOTHING and reserves NOTHING (the durable successful-send row is written
        only by ``commit_confirmed_send`` after confirmed delivery)."""
        plan, verdict = self._classify(
            key=key, now_utc=now_utc, ttl_seconds=ttl_seconds)
        if verdict is not None:
            return verdict
        return allowed_outcome(plan[2])

    def check_and_reserve(
        self,
        *,
        key: Stage30_11_15PingDedupeKey,
        now_utc: str,
        ttl_seconds: int,
    ) -> Stage30_11_15PingDedupeOutcome:
        plan, verdict = self._classify(
            key=key, now_utc=now_utc, ttl_seconds=ttl_seconds)
        if verdict is not None:
            return verdict
        tup, now_unix, reason = plan
        try:
            self._append_record(key=key, reserved_at_utc=now_utc)
        except OSError:
            # The reservation never became durable: neither the replayed
            # state nor the derived tier index may advance.
            return unavailable_outcome(DEDUPE_REASON_LEDGER_WRITE_FAILED)
        self._state[tup] = now_unix
        _note_reserved_tier(
            self._highest_tier_by_scope, scope=_tier_scope(key),
            tier_token=key.tier_token)
        return allowed_outcome(reason)

    def commit_confirmed_send(
        self,
        *,
        key: Stage30_11_15PingDedupeKey,
        now_utc: str,
        ttl_seconds: int,
    ) -> Stage30_11_15PingDedupeOutcome:
        """Append the ONE durable successful-send row for a CONFIRMED delivery.

        Idempotent by classification: a key already reserved within TTL (the
        row this commit -- or an earlier confirmed send -- already wrote)
        appends nothing again, so a restart replaying a durable receipt can
        never double-append. Same fail-closed outcomes as ``check_and_reserve``.
        """
        return self.check_and_reserve(
            key=key, now_utc=now_utc, ttl_seconds=ttl_seconds)


class PeekOnlyPingDedupeLedgerView:
    """A non-mutating dedupe view over a real ledger.

    Exposes the ``PingDedupeLedger`` Protocol (``check_and_reserve``) but
    delegates to the underlying ledger's ``check_only`` -- so the committed
    composer's pre-dispatch dedupe guard can still SUPPRESS duplicates while
    the durable successful-send row is deferred to the post-delivery
    ``commit_confirmed_send``. Total; never raises beyond the ledger contract.
    """

    def __init__(self, ledger: PingDedupeLedger) -> None:
        self._ledger = ledger

    def check_and_reserve(
        self,
        *,
        key: Stage30_11_15PingDedupeKey,
        now_utc: str,
        ttl_seconds: int,
    ) -> Stage30_11_15PingDedupeOutcome:
        check_only = getattr(self._ledger, "check_only", None)
        if not callable(check_only):
            return unavailable_outcome(DEDUPE_REASON_LEDGER_UNAVAILABLE)
        return check_only(key=key, now_utc=now_utc, ttl_seconds=ttl_seconds)


__all__ = (
    "PingDedupeLedger",
    "InMemoryPingDedupeLedger",
    "JsonlPingDedupeLedger",
    "PeekOnlyPingDedupeLedgerView",
)

"""Paid discovery integration for the PHX2 artifact producer.

The owner below is deliberately narrow: one background owner, one Yellowstone
subscription at a time, PumpSwap-filtered events only, and a bounded queue of
candidate-shaped records for the existing producer/watchlist pipeline.  It
does not enrich, write artifacts, reserve a ledger entry, or dispatch.
"""

from __future__ import annotations

import inspect
import queue
import random
import threading
import time
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Iterable, List, Optional

from PHX2.free_tier_producer import source_continuity as _continuity_mod
from PHX2.free_tier_producer import stream_cursor as _cursor_mod
from PHX2.free_tier_producer.migration_admission import (
    attach_candidate_migration_proof, candidate_migration_is_admitted,
)
from PHX2.free_tier_producer.admission_inbox import (
    AdmissionInboxError, DurableAdmissionInbox,
)


class SourceFactoryContractError(RuntimeError):
    """The configured source factory cannot accept a resume position.

    Raised at construction, before any network object exists.  A production
    owner must never silently fall back to a factory that cannot resume: doing
    so drops the durable cursor and re-anchors the subscription at the live
    head, which is precisely the defect the cursor exists to prevent.
    """


#: Keyword arguments a cursor-aware source factory must accept.
CURSOR_AWARE_FACTORY_KWARGS = (
    "from_slot", "cursor", "downstream_durable_fn", "stream_generation")

# Where a candidate's migration time came from.
MIGRATION_TIME_SOURCE_PROVIDER_EVENT_TIME = "PROVIDER_EVENT_TIME"
MIGRATION_TIME_SOURCE_LOCAL_RECEIPT_LIVE = "LOCAL_RECEIPT_LIVE"
MIGRATION_TIME_SOURCE_UNKNOWN = "UNKNOWN"
MIGRATION_TIME_SOURCES = (
    MIGRATION_TIME_SOURCE_PROVIDER_EVENT_TIME,
    MIGRATION_TIME_SOURCE_LOCAL_RECEIPT_LIVE,
    MIGRATION_TIME_SOURCE_UNKNOWN,
)

# Centralized closed-set provenance contract (PHX2.models.discovery_provenance):
# both live provenances carry equal authority; the local names are stable
# aliases for existing importers.
from PHX2.models.discovery_provenance import (  # noqa: E402
    LIVE_DISCOVERY_PROVENANCES,
    DISCOVERY_PROVENANCE_LIVE_HELIUS as DISCOVERY_PROVENANCE_HELIUS,
    DISCOVERY_PROVENANCE_LIVE_YELLOWSTONE as DISCOVERY_PROVENANCE_LIVE,
)
from PHX2.models.market_data_source import (  # noqa: E402
    MARKET_DATA_SOURCE_PAID_MARKET_AND_CANONICAL_RESERVES,
    MARKET_DATA_SOURCE_PAID_MARKET_AND_LIVE_MIGRATION,
)
LIVE_MIGRATION_EVIDENCE_CLASS = "CANONICAL_LIVE_MIGRATION"
LIVE_POOL_DEX_IDENTITY = "SOLANA_PUMPSWAP"


PROVIDER_MODE_FREE_TIER = "FREE_TIER"
PROVIDER_MODE_PAID_PRIMARY = "PAID_PRIMARY"
PROVIDER_MODE_PAID_WITH_FALLBACK = "PAID_WITH_FALLBACK"
PROVIDER_MODES = (
    PROVIDER_MODE_FREE_TIER,
    PROVIDER_MODE_PAID_PRIMARY,
    PROVIDER_MODE_PAID_WITH_FALLBACK,
)

STREAM_STATUS_STOPPED = "STOPPED"
STREAM_STATUS_CONNECTING = "CONNECTING"
STREAM_STATUS_CONNECTED = "CONNECTED"
STREAM_STATUS_RECONNECTING = "RECONNECTING"
STREAM_STATUS_STALE = "STALE"
STREAM_STATUS_AUTH_FAILED = "AUTH_FAILED"

_ATTEMPT_HISTORY_MAX = 32


def _utc_iso(epoch: object) -> Optional[str]:
    if not isinstance(epoch, (int, float)):
        return None
    try:
        return datetime.fromtimestamp(float(epoch), tz=timezone.utc).isoformat().replace("+00:00", "Z")
    except (OverflowError, OSError, ValueError):
        return None


def _age_seconds(now: float, epoch: object) -> Optional[float]:
    if not isinstance(epoch, (int, float)):
        return None
    return round(max(0.0, float(now) - float(epoch)), 3)


def _safe_owner_error_class(err: object) -> str:
    name = getattr(type(err), "__name__", "")
    if (isinstance(name, str) and 0 < len(name) <= 64
            and all(char.isalnum() or char == "_" for char in name)):
        return name
    return "UNSAFE_EXCEPTION_CLASS"


def _is_terminal_auth_refusal(value: object) -> bool:
    """Authentication failures are configuration state, not reconnect events."""
    return isinstance(value, str) and (
        value in ("AUTH_FAILURE", "STREAM_AUTH_FAILED")
        or value.endswith((":UNAUTHENTICATED", ":PERMISSION_DENIED"))
    )


def _admission_counts(source: object) -> Dict[str, int]:
    """Closed-set admission counters from one source; total on any failure."""
    counters = getattr(source, "admission_counters", None)
    snapshot_fn = getattr(counters, "snapshot", None)
    if not callable(snapshot_fn):
        return {}
    try:
        snap = snapshot_fn()
    except Exception:
        return {}
    return {str(k): int(v) for k, v in snap.items()
            if isinstance(v, int) and not isinstance(v, bool)}


def _merge_admission_counts(*parts: Dict[str, int]) -> Dict[str, int]:
    merged: Dict[str, int] = {}
    for part in parts:
        for key, value in (part or {}).items():
            merged[key] = merged.get(key, 0) + value
    return merged


def _display_status(
    *,
    status: str,
    transport_connected: bool,
    live_healthy: bool,
    gap_unresolved: bool,
    cursor_quarantined: bool,
    recovery_reason: str,
    stopped: bool,
) -> str:
    """One operator-facing token that never shows a gap as healthy."""

    if cursor_quarantined:
        return _cursor_mod.DISPLAY_CURSOR_QUARANTINED
    if status == STREAM_STATUS_AUTH_FAILED:
        return _cursor_mod.DISPLAY_RECOVERY_FAILED
    # A refused resume position is a TERMINAL condition needing operator
    # remediation, not a routine blip. It is checked before the stopped and
    # transport branches because both are true of a retention refusal -- the
    # owner stops and never connects -- which previously hid the real reason
    # behind the generic DISCONNECTED_RETRYING token.
    if gap_unresolved and recovery_reason == _cursor_mod.REASON_REPLAY_POSITION_TOO_OLD:
        return _cursor_mod.DISPLAY_REPLAY_UNAVAILABLE
    if status == STREAM_STATUS_STOPPED or stopped:
        return _cursor_mod.DISPLAY_STOPPED
    if not transport_connected:
        return _cursor_mod.DISPLAY_DISCONNECTED_RETRYING
    if gap_unresolved:
        if recovery_reason == _cursor_mod.REASON_REPLAY_POSITION_TOO_OLD:
            return _cursor_mod.DISPLAY_REPLAY_UNAVAILABLE
        if recovery_reason == _cursor_mod.REASON_REPLAY_UNAVAILABLE:
            return _cursor_mod.DISPLAY_GAP_UNRESOLVED
        return _cursor_mod.DISPLAY_CONNECTED_REPLAYING
    if live_healthy:
        return _cursor_mod.DISPLAY_CONNECTED_LIVE_HEALTHY
    return _cursor_mod.DISPLAY_DISCONNECTED_RETRYING


def normalize_provider_mode(value: object) -> str:
    text = str(value or PROVIDER_MODE_FREE_TIER).strip().upper().replace("-", "_")
    if text not in PROVIDER_MODES:
        raise ValueError("provider mode must be FREE_TIER, PAID_PRIMARY, or PAID_WITH_FALLBACK")
    return text


PROVIDER_DEDUPE_APPLIED_FIELD = "provider_dedupe_applied"


def mark_provider_dedupe_applied(candidate: Dict[str, Any]) -> Dict[str, Any]:
    """Stamp a candidate as already consumed by the shared provider dedupe.

    Applied at the ONE provider admission boundary, immediately after the
    shared :class:`ProviderCandidateDedupe` accepted the candidate. The stamp
    travels with the candidate through the handoff queue so a downstream
    consumer can prove -- from the candidate itself, not from a source label --
    that the provider dedupe already ran for it.
    """

    candidate[PROVIDER_DEDUPE_APPLIED_FIELD] = True
    return candidate


def provider_dedupe_already_applied(candidate: object) -> bool:
    """Return ``True`` only on positive, unambiguous proof of application.

    The field is written exactly once, by
    :func:`mark_provider_dedupe_applied`, and only after the shared dedupe
    accepted the candidate.  Absence -- the state of every WS, POLLING and
    DEX-backfill candidate, which never reaches the provider admission
    boundary -- means "not yet deduped" and MUST still be tested.  Anything
    other than the literal boolean ``True`` fails closed the same way, so a
    truthy string or a stray ``1`` can never suppress a required pass.
    """

    if not isinstance(candidate, Mapping):
        return False
    return candidate.get(PROVIDER_DEDUPE_APPLIED_FIELD) is True


def apply_provider_dedupe_once(
    candidates: Iterable[Dict[str, Any]],
    dedupe: Optional["ProviderCandidateDedupe"],
) -> List[Dict[str, Any]]:
    """Give every candidate EXACTLY ONE pass against the shared dedupe.

    The session-level discovery boundary and the paid provider admission
    boundary share ONE :class:`ProviderCandidateDedupe` instance. A candidate
    that already consumed it -- every paid-provider candidate, admitted at
    ``_admit_candidate`` on ``provider_event_id`` + mint -- is passed through
    untested: re-testing it would reject it as ``DUPLICATE_MINT`` against the
    entry its own acceptance recorded.

    A candidate with no stamp (WS, POLLING, and any other source that never
    reaches the provider boundary) is tested exactly once, on
    ``source_ref`` + mint, and stamped on acceptance so it too can never be
    tested twice.  The decision is read off the candidate, never off a source
    label, so renaming a source can never change dedupe topology.
    """

    if dedupe is None:
        return list(candidates)
    survivors: List[Dict[str, Any]] = []
    for candidate in candidates:
        if provider_dedupe_already_applied(candidate):
            survivors.append(candidate)
            continue
        if dedupe.accept(event_id=candidate.get("source_ref"),
                         mint=candidate.get("token_mint")):
            mark_provider_dedupe_applied(candidate)
            survivors.append(candidate)
    return survivors


class ProviderCandidateDedupe:
    """Thread-safe, shared signature + mint dedupe for primary and fallback.

    ONE instance is shared by the paid provider admission boundary and the
    session-level discovery boundary.  A candidate is tested against it
    exactly once: re-testing an already-admitted candidate rejects it as
    ``DUPLICATE_MINT``, because the first acceptance recorded its mint.  See
    :func:`provider_dedupe_already_applied` for how that invariant is carried.
    """

    def __init__(self, max_entries: int = 4096) -> None:
        self._max_entries = max(1, int(max_entries))
        self._event_ids: Dict[str, None] = {}
        self._mints: Dict[str, None] = {}
        self._lock = threading.Lock()
        self._duplicate_events = 0
        self._duplicate_mints = 0

    def accept(self, *, event_id: object, mint: object) -> bool:
        accepted, _ = self.accept_with_reason(event_id=event_id, mint=mint)
        return accepted

    def accept_with_reason(self, *, event_id: object, mint: object,
                           before_accept: Optional[Callable[[], None]] = None
                           ) -> tuple[bool, str]:
        if not isinstance(mint, str) or not mint:
            return False, "MALFORMED_MINT"
        safe_event_id = str(event_id or "")
        with self._lock:
            if safe_event_id and safe_event_id in self._event_ids:
                self._duplicate_events += 1
                return False, "DUPLICATE_EVENT"
            if mint in self._mints:
                self._duplicate_mints += 1
                return False, "DUPLICATE_MINT"
            if before_accept is not None:
                # Persistence failure must not consume either dedupe identity.
                before_accept()
            if safe_event_id:
                self._event_ids[safe_event_id] = None
            self._mints[mint] = None
            while len(self._event_ids) > self._max_entries:
                self._event_ids.pop(next(iter(self._event_ids)))
            while len(self._mints) > self._max_entries:
                self._mints.pop(next(iter(self._mints)))
            return True, "ACCEPTED"

    def snapshot(self) -> Dict[str, int]:
        with self._lock:
            return {
                "event_ids_tracked": len(self._event_ids),
                "mints_tracked": len(self._mints),
                "duplicate_events_dropped": self._duplicate_events,
                "duplicate_mints_dropped": self._duplicate_mints,
            }


@dataclass(frozen=True)
class MigrationEventTime:
    """The resolved migration time plus an honest account of its provenance."""

    migration_time_utc: Optional[str]
    source: str
    authoritative: bool


def resolve_migration_event_time(
    *, provider_event_time_utc: Optional[str], provider_event_time_source: str,
    local_observed_at_utc: Optional[str], replayed: bool,
) -> MigrationEventTime:
    """Decide what a candidate's migration time actually is.

    Three cases, in order of decreasing evidence:

    1. The provider stamped the event: use it.  This is the only value that
       survives replay correctly -- a migration recovered hours later still
       reports when it happened, not when it was decoded.
    2. No provider stamp, but the event arrived LIVE at the stream tip: local
       receipt time is within milliseconds of the event and is an honest
       proxy, so it is used and labelled as such.
    3. No provider stamp on a REPLAYED event: there is no defensible time.
       Returning the current wall clock here is what made a recovered old
       migration look newly migrated, so this returns ``None`` and
       ``authoritative=False``, and age-sensitive send authorization fails
       closed on it.
    """

    if (isinstance(provider_event_time_utc, str) and provider_event_time_utc
            and provider_event_time_source
            == _source_mod_event_time_provider()):
        return MigrationEventTime(
            migration_time_utc=provider_event_time_utc,
            source=MIGRATION_TIME_SOURCE_PROVIDER_EVENT_TIME,
            authoritative=True)
    if not replayed and isinstance(local_observed_at_utc, str) \
            and local_observed_at_utc:
        return MigrationEventTime(
            migration_time_utc=local_observed_at_utc,
            source=MIGRATION_TIME_SOURCE_LOCAL_RECEIPT_LIVE,
            authoritative=True)
    return MigrationEventTime(
        migration_time_utc=None,
        source=MIGRATION_TIME_SOURCE_UNKNOWN,
        authoritative=False)


def _source_mod_event_time_provider() -> str:
    from PHX2.free_tier_producer.paid_grpc_source import (
        EVENT_TIME_SOURCE_PROVIDER_CREATED_AT,
    )
    return EVENT_TIME_SOURCE_PROVIDER_CREATED_AT


def event_to_candidate(
    event: object, *, replayed: bool = False,
    provider_event_time_utc: Optional[str] = None,
    provider_event_time_source: Optional[str] = None,
    migration_proof: object = None,
    migration_signature: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Project only an extractor-proven base mint into the producer contract.

    ``migration_time_utc`` is the token's CHAIN/provider event time; the local
    receipt time is carried separately as ``local_observed_at_utc``.  The two
    were previously the same value, so a replayed migration presented a fresh
    migration time and every age-based judgement about it was wrong.

    The provider time may be supplied explicitly by the owner (which reads it
    from the source's per-event side-channel) or carried on the event itself.
    """
    base_mint = getattr(event, "base_mint", None)
    mint = getattr(event, "mint", None)
    pool_account = getattr(event, "pool_account", None)
    pool_program_id = getattr(event, "pool_program_id", None)
    quote_mint = getattr(event, "quote_mint", None)
    event_id = getattr(event, "event_id", None)
    provider_event_id = getattr(event, "provider_event_id", None)
    observed_at = getattr(event, "observed_at_utc", None)
    raw_ref = getattr(event, "raw_event_hash", None)
    provider_name = str(getattr(event, "provider_name", None) or "")
    helius_event = provider_name.startswith("HELIUS_")

    # Fail closed unless the Stage 29 decoder's actual base mint is coherent
    # with the normalized event. Pool/program/quote addresses can never stand
    # in for the candidate token mint.
    if not isinstance(base_mint, str) or not base_mint or mint != base_mint:
        return None
    if base_mint in (pool_account, pool_program_id, quote_mint):
        return None
    if not isinstance(observed_at, str) or not observed_at:
        return None
    candidate_id = str(event_id or provider_event_id or ("grpc_" + base_mint[:12]))
    if provider_event_time_utc is None:
        provider_event_time_utc = getattr(event, "provider_event_time_utc", None)
    if provider_event_time_source is None:
        provider_event_time_source = getattr(
            event, "provider_event_time_source", None)
    event_time = resolve_migration_event_time(
        provider_event_time_utc=provider_event_time_utc,
        provider_event_time_source=str(provider_event_time_source or ""),
        local_observed_at_utc=observed_at,
        replayed=bool(replayed))
    candidate = {
        "token_mint": base_mint,
        "candidate_id": candidate_id,
        "migration_time_utc": event_time.migration_time_utc,
        "local_observed_at_utc": observed_at,
        "migration_time_source": event_time.source,
        "migration_time_authoritative": bool(event_time.authoritative),
        "source_ref": str(raw_ref or provider_event_id or event_id or "grpc_event"),
        "symbol_or_name": None,
        "provider_event_id": str(provider_event_id or event_id or ""),
        "discovery_provider": (
            "HELIUS_PRIMARY" if helius_event else "PAID_GRPC_PRIMARY"
        ),
        "discovery_provenance": (
            DISCOVERY_PROVENANCE_HELIUS
            if helius_event else DISCOVERY_PROVENANCE_LIVE
        ),
        "discovery_utc": observed_at,
        "live_epoch_id": None,
        "migration_slot": getattr(event, "slot", None),
        "migration_evidence_class": LIVE_MIGRATION_EVIDENCE_CLASS,
        "pair_address": pool_account,
        "pool_dex_identity": LIVE_POOL_DEX_IDENTITY,
        "migration_mc_source": "CANONICAL_LIVE_EVENT",
        "ath_source": "CENTRAL_ATH",
        "liquidity_source": "CANONICAL_PUMPSWAP_RESERVES",
        # Artifact-safe ROLE labels only.  A provider-named value here is a
        # redaction danger needle and fails the whole run closed.
        "current_data_source": (
            MARKET_DATA_SOURCE_PAID_MARKET_AND_LIVE_MIGRATION
            if helius_event
            else MARKET_DATA_SOURCE_PAID_MARKET_AND_CANONICAL_RESERVES
        ),
        "backfill_lookback_seconds": None,
        "backfill_sweep_id": None,
        "source_confidence": "CANONICAL_LIVE",
        "dedupe_identity": "mint:" + base_mint,
        "corroborating_sources": [],
    }
    # Optional same-event exact migration baseline. The Yellowstone decoder may
    # expose this only when price, supply, decimals, and reserve evidence were
    # all complete for the create-pool observation. No later price or inferred
    # supply is used here; incomplete metadata is simply left for the Birdeye
    # first-fresh-snapshot fallback in the centralized watch state.
    baseline = getattr(event, "migration_baseline", None)
    baseline = baseline if isinstance(baseline, dict) else {}
    field_sources = {
        "migration_market_cap_usd": (
            getattr(event, "migration_market_cap_usd", None),
            baseline.get("migration_market_cap_usd"),
        ),
        "migration_market_cap_price": (
            getattr(event, "migration_market_cap_price", None),
            baseline.get("migration_market_cap_price"),
        ),
        "migration_supply_at_observation": (
            getattr(event, "migration_supply_at_observation", None),
            baseline.get("migration_supply_at_observation"),
        ),
        "migration_market_cap_observed_at_utc": (
            getattr(event, "migration_market_cap_observed_at_utc", None),
            baseline.get("migration_market_cap_observed_at_utc"),
            observed_at,
        ),
    }
    for field, values in field_sources.items():
        selected = next((value for value in values if value is not None), None)
        if selected is not None:
            candidate[field] = selected
    source = (getattr(event, "migration_market_cap_source", None)
              or baseline.get("migration_market_cap_source"))
    if source is not None:
        candidate["migration_market_cap_source"] = source
    proof = migration_proof if migration_proof is not None else getattr(
        event, "migration_proof", None)
    if proof is not None:
        candidate["migration_signature"] = (
            migration_signature if migration_signature is not None
            else provider_event_id if helius_event else getattr(event, "migration_signature", None))
    if proof is not None and not attach_candidate_migration_proof(
            candidate, proof, quote_mint=quote_mint):
        return None
    return candidate


class SingleGrpcPumpSwapDiscovery:
    """Own sequential Yellowstone subscriptions with a hard max-active of one."""

    def __init__(
        self,
        *,
        source_factory: Callable[[], Any],
        dedupe: ProviderCandidateDedupe,
        queue_max: int = 256,
        stale_after_seconds: float = 45.0,
        reconnect_backoff_seconds: float = 1.0,
        now_fn: Callable[[], float] = time.time,
        random_fn: Callable[[], float] = random.random,
        reconnect_jitter_fraction: float = 0.20,
        event_sink: Optional[Callable[[Dict[str, Any]], None]] = None,
        cursor_store: Any = None,
        require_cursor_aware_factory: bool = False,
        gap_recovery: Any = None,
        live_epoch_manager: Any = None,
        continuity: Any = None,
        source_owned_gap_recovery: bool = False,
        admission_inbox: Optional[DurableAdmissionInbox] = None,
    ) -> None:
        if not callable(source_factory):
            raise ValueError("source_factory must be callable")
        self._source_factory = source_factory
        self._authoritative_source = str(
            getattr(source_factory, "authoritative_source", "CHAINSTACK")
        )
        # Decided ONCE, from the declared signature, before any network object
        # exists. The armed production owner requires the contract; the generic
        # development CLI and offline probes may keep the legacy behaviour.
        self._factory_is_cursor_aware = self._factory_accepts_cursor_kwargs(
            source_factory)
        self._require_cursor_aware_factory = bool(require_cursor_aware_factory)
        if self._require_cursor_aware_factory:
            if not self._factory_is_cursor_aware:
                raise SourceFactoryContractError(
                    "PRODUCTION_SOURCE_FACTORY_CONTRACT_INVALID: the configured "
                    "factory cannot accept a resume position "
                    "(%s)" % ", ".join(CURSOR_AWARE_FACTORY_KWARGS))
            if cursor_store is None:
                raise SourceFactoryContractError(
                    "PRODUCTION_SOURCE_FACTORY_CONTRACT_INVALID: a cursor store "
                    "is required when the cursor-aware contract is enforced")
        # PHX2-E2E-008: the durable resume position. ``None`` preserves the
        # historical tip-anchored behaviour for callers that do not own a
        # cursor (probes, fixtures, independent tests).
        self._cursor_store = cursor_store
        # Bounded RPC gap-backfill coordinator (rpc_gap_recovery). ``None``
        # (the default and every pre-existing caller) keeps the certified
        # terminal behaviour byte-identical: a replay-retention refusal stops
        # the owner and requires operator remediation.
        self._gap_recovery = gap_recovery
        self._live_epoch = live_epoch_manager
        self._admission_inbox = admission_inbox
        self._admission_commit_failed = False
        if admission_inbox is not None and live_epoch_manager is None:
            raise SourceFactoryContractError("ADMISSION_INBOX_REQUIRES_LIVE_EPOCH")
        # The ONE authoritative source-continuity state machine. It runs in
        # every mode -- unlike the cursor bookkeeping below, which was
        # historically reachable only when live-epoch mode was off, leaving
        # production with no slot-continuity check whatsoever. A tracker is
        # always present so no call site needs a None guard.
        self._continuity = (
            continuity if continuity is not None
            else _continuity_mod.SourceContinuityTracker())
        self._source_owned_gap_recovery = bool(source_owned_gap_recovery)
        self._factory_accepts_observer = self._factory_accepts_kwarg(
            source_factory, "transaction_observer")
        self._last_handoff_durable = True
        self._stream_generation = 0
        self._dedupe = dedupe
        self._queue: queue.Queue[Dict[str, Any]] = queue.Queue(maxsize=max(1, int(queue_max)))
        # PHX2-E2E-006: optional watch-loop waker fired after a successful
        # candidate enqueue (never on drops/rejections).
        self._enqueue_waker: Optional[Callable[[], None]] = None
        self._stale_after = max(0.05, float(stale_after_seconds))
        self._backoff = max(0.0, float(reconnect_backoff_seconds))
        self._now = now_fn
        self._random = random_fn
        self._jitter_fraction = max(0.0, min(1.0, float(reconnect_jitter_fraction)))
        self._event_sink = event_sink
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._active_source: Any = None
        self._lock = threading.Lock()
        self._status = STREAM_STATUS_STOPPED
        self._active_streams = 0
        self._max_active_streams = 0
        self._stream_capacity = 1
        self._connect_attempts = 0
        self._reconnects = 0
        self._events_received = 0
        self._candidates_decoded = 0
        self._candidates_accepted = 0
        self._non_pump_dropped = 0
        self._invalid_base_mint_dropped = 0
        self._queue_dropped = 0
        self._stream_errors = 0
        self._source_updates_scanned = 0
        self._source_transactions_scanned = 0
        self._source_create_pool_yielded = 0
        self._source_reserve_events_decoded = 0
        self._source_fee_events_decoded = 0
        self._admission_totals: Dict[str, int] = {}
        self._last_message_epoch: Optional[float] = None
        self._last_candidate_epoch: Optional[float] = None
        self._last_refusal_reason: Optional[str] = None
        self._terminal_auth_failure = False
        self._terminal_recovery = False
        self._sends_blocked_by_source_health = 0
        self._session_started_epoch: Optional[float] = None
        self._last_session_duration_s: Optional[float] = None
        self._shortest_session_duration_s: Optional[float] = None
        self._longest_session_duration_s: Optional[float] = None
        self._last_reconnect_reason: Optional[str] = None
        self._reconnect_reasons: Dict[str, int] = {}
        self._authentication_failures = 0
        self._provider_disconnects = 0
        self._watchdog_reconnects = 0
        self._operator_shutdowns = 0
        self._stream_attempts: List[Dict[str, Any]] = []
        self._queue_sequence = 0
        self._queued_at: Dict[int, float] = {}
        self._handoff_artifact_errors = 0
        # --- PHX2-E2E-008 recovery counters (retired-source totals) ---
        self._replay_events = 0
        self._replay_duplicates = 0
        self._replay_requested_total = 0
        self._replay_too_old_total = 0
        self._gap_recovery_failed_total = 0
        self._gap_detected_total = 0
        self._gap_closed_total = 0
        # Bounded RPC gap-recovery bookkeeping. The admit lock serializes the
        # candidate admission path between the owner thread and the backfill
        # worker so handoff artifacts never interleave.
        self._recovery_sessions = 0
        self._admit_lock = threading.Lock()
        self._corroboration_queue: queue.Queue[Dict[str, Any]] = queue.Queue(
            maxsize=max(1, int(queue_max)))

    def _emit_handoff(self, event: str, candidate: Optional[Dict[str, Any]] = None,
                      **fields: Any) -> bool:
        if self._event_sink is None:
            return True
        record = {
            "kind": "PHX2_PROVIDER_HANDOFF",
            "event": event,
            "observed_at_utc": _utc_iso(float(self._now())),
            **fields,
        }
        if isinstance(candidate, dict):
            record.update({
                "token_mint": candidate.get("token_mint"),
                "candidate_id": candidate.get("candidate_id"),
                "provider_event_id": candidate.get("provider_event_id"),
            })
        try:
            self._event_sink(record)
            return True
        except Exception:
            with self._lock:
                self._handoff_artifact_errors += 1
                self._last_refusal_reason = "HANDOFF_ARTIFACT_WRITE_FAILED"
            return False

    def start(self) -> None:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            if self._terminal_auth_failure:
                return
            self._stop.clear()
            self._status = STREAM_STATUS_CONNECTING
            self._thread = threading.Thread(
                target=self._run, name="phx2-single-grpc-owner", daemon=True
            )
            self._thread.start()

    def stop(self, timeout_seconds: float = 2.0) -> None:
        self._stop.set()
        with self._lock:
            source = self._active_source
        close = getattr(source, "request_graceful_close", None)
        if not callable(close):
            close = getattr(source, "close", None)
        if callable(close):
            try:
                close()
            except Exception:
                pass
        thread = self._thread
        if thread is not None:
            thread.join(timeout=max(0.0, float(timeout_seconds)))
        with self._lock:
            if self._active_streams == 0 and not self._terminal_auth_failure:
                self._status = STREAM_STATUS_STOPPED

    def set_enqueue_waker(self, waker: Optional[Callable[[], None]]) -> None:
        """Install the watch-loop waker fired on successful enqueue."""

        self._enqueue_waker = waker

    def drain(self, max_candidates: int = 10) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        for _ in range(max(0, int(max_candidates))):
            try:
                candidate = self._queue.get_nowait()
            except queue.Empty:
                break
            handoff = candidate.get("provider_handoff")
            handoff = handoff if isinstance(handoff, dict) else {}
            sequence = int(handoff.get("queue_sequence") or 0)
            queued_at = handoff.get("enqueued_at_epoch")
            now = float(self._now())
            queue_age = _age_seconds(now, queued_at)
            handoff = {
                **handoff,
                "dequeued_at_utc": _utc_iso(now),
                "queue_age_seconds": queue_age,
            }
            candidate["provider_handoff"] = handoff
            with self._lock:
                self._queued_at.pop(sequence, None)
            if not self._emit_handoff(
                "CANDIDATE_DEQUEUED", candidate,
                queue_depth=self._queue.qsize(), queue_age_seconds=queue_age,
                queue_sequence=sequence,
            ):
                with self._lock:
                    if sequence:
                        self._queued_at[sequence] = float(queued_at or now)
                try:
                    self._queue.put_nowait(candidate)
                except queue.Full:
                    pass
                raise RuntimeError("HANDOFF_ARTIFACT_WRITE_FAILED")
            out.append(candidate)
        return out

    def drain_corroborations(
        self, max_candidates: int = 256
    ) -> List[Dict[str, Any]]:
        """Main-thread handoff for live evidence that deduped by mint."""

        out: List[Dict[str, Any]] = []
        for _ in range(max(0, int(max_candidates))):
            try:
                out.append(self._corroboration_queue.get_nowait())
            except queue.Empty:
                break
        return out

    def needs_fallback(self) -> bool:
        snap = self.snapshot()
        return snap["status"] in (
            STREAM_STATUS_CONNECTING,
            STREAM_STATUS_RECONNECTING,
            STREAM_STATUS_STALE,
            STREAM_STATUS_STOPPED,
        )

    def snapshot(self) -> Dict[str, Any]:
        now = float(self._now())
        epoch_snapshot: Dict[str, Any] = {}
        if self._live_epoch is not None:
            try:
                epoch_snapshot = dict(self._live_epoch.snapshot())
            except Exception:
                epoch_snapshot = {
                    "epoch_status": "EPOCH_INTEGRITY_FAILURE",
                    "epoch_durable": False,
                }
        with self._lock:
            source = self._active_source
            source_last_update = getattr(source, "last_update_epoch", None)
            last_update = self._last_message_epoch
            if isinstance(source_last_update, (int, float)):
                last_update = max(float(source_last_update), float(last_update or 0.0))
            age = (None if last_update is None
                   else round(max(0.0, now - last_update), 1))
            status = self._status
            # PHX2-E2E-008: constructing a source performs no I/O, so the
            # transport is proven only by a RAW update having been received --
            # never by the factory returning. Any of the three raw-update
            # signals is sufficient; the live source sets all of them together
            # on its first message, and none of them before it.
            transport_connected = bool(
                source is not None
                and (getattr(source, "first_update_epoch", None) is not None
                     or getattr(source, "last_update_epoch", None) is not None
                     or int(getattr(source, "events_scanned", 0) or 0) > 0))
            if status in (STREAM_STATUS_CONNECTING, STREAM_STATUS_RECONNECTING) \
                    and transport_connected:
                status = STREAM_STATUS_CONNECTED
            if status == STREAM_STATUS_CONNECTED and (age is None or age > self._stale_after):
                status = STREAM_STATUS_STALE
            coverage = (self._coverage_state(source) if source is not None
                        else {"gap_unresolved": False,
                              "recovery_status": _cursor_mod.RECOVERY_NOT_REQUIRED,
                              "recovery_reason": _cursor_mod.REASON_NONE,
                              "state": _cursor_mod.STATE_STOPPED})
            cursor_snapshot: Dict[str, Any] = {}
            cursor_quarantined = False
            identity_match = True
            if self._cursor_store is not None:
                try:
                    cursor_snapshot = dict(self._cursor_store.snapshot())
                except Exception:
                    cursor_snapshot = {}
                cursor_quarantined = bool(
                    cursor_snapshot.get("grpc_cursor_quarantined", False))
                identity_match = bool(
                    cursor_snapshot.get("grpc_subscription_identity_match", True))
                if cursor_snapshot.get("grpc_gap_unresolved"):
                    coverage = dict(coverage)
                    coverage["gap_unresolved"] = True
            continuity_snapshot = dict(self._continuity.snapshot())
            continuity_state = str(continuity_snapshot["continuity_state"])
            if self._live_epoch is not None:
                # Historical BLOCK replay stays retired, but "no historical
                # replay" never meant "coverage is proven continuous". The
                # hardcoded ``gap_unresolved: False`` here was the telemetry
                # twin of the gated cursor block: it laundered a real
                # discontinuity into a healthy-looking snapshot. The canonical
                # continuity state now answers this question in every mode.
                coverage = {
                    "gap_unresolved": not continuity_snapshot[
                        "coverage_proven_continuous"],
                    "recovery_status": continuity_state,
                    "recovery_reason": "NONE",
                    "state": epoch_snapshot.get("epoch_status", "EPOCH_STARTING"),
                }
            gap_unresolved = bool(
                coverage["gap_unresolved"]
                or not continuity_snapshot["coverage_proven_continuous"])
            # A connected socket over an unresolved gap is DEGRADED, never
            # healthy: recovery work continues but discovery coverage is
            # unproven.
            terminal_recovery = bool(
                False if self._live_epoch is not None else (
                    self._terminal_recovery
                    or cursor_snapshot.get("grpc_recovery_terminal", False)))
            live_healthy = bool(
                status == STREAM_STATUS_CONNECTED
                and transport_connected
                and not gap_unresolved
                and not cursor_quarantined
                and identity_match
                and not terminal_recovery
                and not self._terminal_auth_failure
                and (self._live_epoch is None
                     or (epoch_snapshot.get("epoch_status") == "EPOCH_HEALTHY"
                         and epoch_snapshot.get("epoch_durable") is True)))
            if terminal_recovery:
                coverage = dict(coverage)
                coverage["gap_unresolved"] = True
                coverage["state"] = _cursor_mod.STATE_REPLAY_RETENTION_EXCEEDED
                coverage["recovery_status"] = _cursor_mod.RECOVERY_FAILED
                coverage["recovery_reason"] = (
                    cursor_snapshot.get("grpc_recovery_reason")
                    or _cursor_mod.REASON_REPLAY_POSITION_TOO_OLD)
                gap_unresolved = True
            base = {
                "admission_inbox_commit_failed": (self._admission_commit_failed or
                    bool(getattr(source, "admission_commit_failed", False)) or
                    bool(self._admission_inbox is not None and
                         self._admission_inbox.snapshot()["reload_required"])),
                "admission_inbox": (self._admission_inbox.snapshot()
                                    if self._admission_inbox is not None else None),
                "provider_mode": PROVIDER_MODE_PAID_PRIMARY,
                "provider": (
                    "HELIUS_PRIMARY"
                    if self._authoritative_source == "HELIUS"
                    else "PAID_GRPC_PRIMARY"
                ),
                "primary_migration_source": self._authoritative_source,
                "status": status,
                "production_mode": (
                    "LIVE_EPOCH_HELIUS_PRIMARY"
                    if self._live_epoch is not None
                    and self._authoritative_source == "HELIUS"
                    else "LIVE_EPOCH_WITH_DEX_BACKFILL"
                    if self._live_epoch is not None
                    else "HISTORICAL_CURSOR_MODE"
                ),
                "historical_completeness_required": False if self._live_epoch is not None else True,
                "historical_rpc_backfill_enabled": False if self._live_epoch is not None else self._gap_recovery is not None,
                "historical_recovery_status": "HISTORICAL_BLOCK_REPLAY_RETIRED_FROM_PRODUCTION" if self._live_epoch is not None else None,
                "live_epoch": epoch_snapshot,
                # --- PHX2-E2E-008 health/readiness split ---
                "transport_connected": transport_connected,
                "live_healthy": live_healthy,
                "gap_unresolved": gap_unresolved,
                # Canonical source continuity. ``source_continuity`` is the
                # authoritative coverage answer; the flat mirrors below keep
                # existing readers working without a schema migration.
                "source_continuity": continuity_snapshot,
                "source_continuity_state": continuity_state,
                "coverage_proven_continuous": bool(
                    continuity_snapshot["coverage_proven_continuous"]),
                "grpc_gap_detected_total": int(
                    continuity_snapshot["gap_detected_total"]),
                "grpc_gap_closed_total": int(
                    continuity_snapshot["gap_closed_total"]),
                "grpc_gap_from_slot": continuity_snapshot["gap_from_slot"],
                "grpc_gap_to_slot": continuity_snapshot["gap_to_slot"],
                "grpc_gap_size_slots": continuity_snapshot["gap_size_slots"],
                "grpc_gap_unresolved_slot_total": int(
                    continuity_snapshot["unresolved_slot_total"]),
                "recovery_status": coverage["recovery_status"],
                "recovery_reason": coverage["recovery_reason"],
                "stream_state": coverage["state"],
                "grpc_display_status": _display_status(
                    status=status,
                    transport_connected=transport_connected,
                    live_healthy=live_healthy,
                    gap_unresolved=gap_unresolved,
                    cursor_quarantined=cursor_quarantined,
                    recovery_reason=coverage["recovery_reason"],
                    stopped=self._stop.is_set(),
                ),
                "replay_requested": bool(
                    getattr(source, "replay_requested", False)),
                "replay_from_slot": getattr(source, "replay_from_slot", None),
                # -- durable-cursor throughput decomposition -----------------
                # ``latest_received_event_slot`` is the highest slot the single
                # owned stream has read off the socket; the processed and
                # durable slots come from the cursor snapshot. Combined with an
                # out-of-band confirmed RPC head these give the full
                # provider-delivery / processing / durability lag split.
                "latest_received_event_slot": getattr(
                    source, "highest_slot_observed", None),
                "latest_processed_event_slot": cursor_snapshot.get(
                    "grpc_cursor_last_durable_slot"),
                "latest_durable_cursor_slot": cursor_snapshot.get(
                    "grpc_cursor_flushed_durable_slot"),
                "replay_event_total": int(
                    self._replay_events + int(
                        getattr(source, "replayed_events", 0) or 0)),
                "replay_duplicate_total": int(
                    self._replay_duplicates + int(
                        getattr(source, "replay_duplicates_suppressed", 0) or 0)),
                "replay_requested_total": self._replay_requested_total,
                "replay_position_too_old_total": self._replay_too_old_total,
                "gap_recovery_failed_total": self._gap_recovery_failed_total,
                "terminal_recovery": terminal_recovery,
                "terminal_recovery_reason": (
                    coverage["recovery_reason"] if terminal_recovery
                    else _cursor_mod.REASON_NONE),
                "overlap_expected_slot": getattr(
                    source, "expected_overlap_slot", None),
                "overlap_proof_slot": getattr(source, "overlap_proof_slot", None),
                "overlap_proof_accepted": bool(
                    getattr(source, "overlap_proof_accepted", False)),
                "sends_blocked_by_source_health": (
                    self._sends_blocked_by_source_health),
                "cursor": cursor_snapshot,
                "active_streams": self._active_streams,
                "max_active_streams": self._max_active_streams,
                "stream_capacity": self._stream_capacity,
                "connect_attempts": self._connect_attempts,
                "reconnects": self._reconnects,
                "events_received": self._events_received,
                "candidates_decoded": self._candidates_decoded,
                "candidates_accepted": self._candidates_accepted,
                "non_pump_dropped": self._non_pump_dropped,
                "invalid_base_mint_dropped": self._invalid_base_mint_dropped,
                "queue_dropped": self._queue_dropped,
                "stream_errors": self._stream_errors,
                "queue_depth": self._queue.qsize(),
                "oldest_queue_age_seconds": (
                    None if not self._queued_at else
                    round(max(0.0, now - min(self._queued_at.values())), 3)
                ),
                "handoff_artifact_errors": self._handoff_artifact_errors,
                "last_message_age_s": age,
                "source_updates_scanned": self._source_updates_scanned + int(
                    getattr(source, "events_scanned", 0) or 0),
                "source_transactions_scanned": self._source_transactions_scanned + int(
                    getattr(source, "transactions_scanned", 0) or 0),
                "source_create_pool_yielded": self._source_create_pool_yielded + int(
                    getattr(source, "create_pool_yielded", 0) or 0),
                "source_reserve_events_decoded": self._source_reserve_events_decoded + int(
                    getattr(source, "reserve_events_decoded", 0) or 0),
                "source_fee_events_decoded": self._source_fee_events_decoded + int(
                    getattr(source, "fee_events_decoded", 0) or 0),
                "migration_admission": _merge_admission_counts(
                    self._admission_totals, _admission_counts(source)),
                "last_refusal_reason": self._last_refusal_reason,
                "terminal_auth_failure": self._terminal_auth_failure,
                "last_reconnect_reason": self._last_reconnect_reason,
                "reconnect_reasons": dict(self._reconnect_reasons),
                "current_stream_session_duration_s": (
                    None if self._session_started_epoch is None else
                    round(max(0.0, now - self._session_started_epoch), 3)
                ),
                "last_stream_session_duration_s": self._last_session_duration_s,
                "shortest_stream_session_duration_s": self._shortest_session_duration_s,
                "longest_stream_session_duration_s": self._longest_session_duration_s,
                "authentication_failures": self._authentication_failures,
                "provider_disconnects": self._provider_disconnects,
                "watchdog_reconnects": self._watchdog_reconnects,
                "operator_shutdowns": self._operator_shutdowns,
                "stream_attempts": [dict(item) for item in self._stream_attempts],
            }
            diagnostic_fn = getattr(source, "diagnostic_snapshot", None)
            try:
                source_diagnostic = (
                    diagnostic_fn() if callable(diagnostic_fn) else {}
                )
            except Exception:
                source_diagnostic = {}
            if not isinstance(source_diagnostic, dict):
                source_diagnostic = {}
            source_metrics = source_diagnostic.get("metrics")
            if not isinstance(source_metrics, dict):
                source_metrics = {}
            base.update({
                "primary_source_state": source_diagnostic.get(
                    "status", status
                ),
                "primary_last_slot": (
                    source_diagnostic.get("last_event_slot")
                    if self._authoritative_source == "HELIUS"
                    else base.get("latest_received_event_slot")
                ),
                "primary_estimated_credits": source_metrics.get(
                    "estimated_credits", 0.0
                ),
                "primary_recovery": source_diagnostic.get(
                    "last_recovery_status", coverage["recovery_status"]
                ),
                # Persistent-reconnect observability: ladder position, jitter
                # bound, resets and the next base delay.  Numbers and
                # closed-set tokens only.
                "reconnect_policy": (
                    source_diagnostic.get("reconnect_policy")
                    if isinstance(
                        source_diagnostic.get("reconnect_policy"), dict)
                    else {}
                ),
                "gap_recovery_degraded": bool(
                    source_diagnostic.get("gap_recovery_degraded", False)),
                "migration_journal": (
                    source_diagnostic.get("migration_journal")
                    if isinstance(
                        source_diagnostic.get("migration_journal"), dict)
                    else {}
                ),
            })
        base["dedupe"] = self._dedupe.snapshot()
        if self._gap_recovery is not None:
            try:
                base["gap_recovery"] = self._gap_recovery.snapshot()
            except Exception:
                base["gap_recovery"] = {"recovery_state": "SNAPSHOT_ERROR"}
            base["recovery_sessions"] = int(self._recovery_sessions)
        return base

    def authorizes_send(self) -> tuple[bool, str]:
        """May the outbound alert path proceed against this source right now?

        Ingestion is deliberately NOT gated by this: replay, admission,
        candidate restoration, watchlist rebuilding and baseline restoration
        must keep running while degraded, or the recovery cannot complete.
        Only the outbound path is blocked.

        This owner reports health and nothing more. It performs no compose,
        holds no reservation, writes no delivery record and dispatches
        nothing -- the caller at the outbound boundary enforces the answer.
        """

        snapshot = self.snapshot()
        if self._live_epoch is not None:
            epoch = snapshot.get("live_epoch") or {}
            authorized = bool(
                snapshot.get("live_healthy")
                and epoch.get("epoch_status") == "EPOCH_HEALTHY"
                and epoch.get("epoch_durable") is True)
            if not authorized:
                with self._lock:
                    self._sends_blocked_by_source_health += 1
            return authorized, (
                "LIVE_EPOCH_HEALTHY" if authorized
                else str(epoch.get("epoch_status") or "EPOCH_STARTING"))
        merged = dict(snapshot.get("cursor") or {})
        merged.update({
            "stream_state": snapshot.get("stream_state"),
            "live_healthy": snapshot.get("live_healthy"),
            "gap_unresolved": snapshot.get("gap_unresolved"),
        })
        authorized, reason = _cursor_mod.source_health_authorizes_send(merged)
        if not authorized:
            with self._lock:
                self._sends_blocked_by_source_health += 1
        return authorized, reason

    def _resume_decision(self) -> Any:
        """What this attempt may construct, decided BEFORE it constructs it.

        A terminal, quarantined or identity-mismatched cursor answers
        ``builds_source=False``.  Consulting that first is the whole repair: the
        owner previously calculated a resume position and built the source at
        the top of the attempt and only inspected terminal state ~110 lines
        later, in the ``finally`` block -- so a dead replay position produced a
        full live-head subscription on every restart, silently skipping the
        retention pre-check it exists to trigger.
        """

        if self._live_epoch is not None:
            try:
                if self._live_epoch.integrity_failure:
                    return _cursor_mod.ResumeDecision(
                        action=_cursor_mod.RESUME_ACTION_REFUSE_TERMINAL,
                        from_slot=None, reason="EPOCH_INTEGRITY_FAILURE")
            except Exception:
                return _cursor_mod.ResumeDecision(
                    action=_cursor_mod.RESUME_ACTION_REFUSE_TERMINAL,
                    from_slot=None, reason="EPOCH_INTEGRITY_FAILURE")
            if self._source_owned_gap_recovery:
                return _cursor_mod.ResumeDecision(
                    action=_cursor_mod.RESUME_ACTION_BOOTSTRAP_LIVE_HEAD,
                    from_slot=None,
                    reason=_cursor_mod.REASON_NONE,
                )
            # Same-session gap replay. Live-epoch production previously had
            # exactly ONE resume behaviour -- bootstrap at the provider's live
            # head -- so a detected discontinuity could never be asked for
            # again and the tracker's safe recovery slot was computed and then
            # discarded. When an open gap still has attempt budget the
            # replacement subscription requests its earliest unproven slot;
            # with no open gap this returns None and the live-only startup
            # policy is byte-for-byte what it was.
            request = self._continuity.replay_request()
            if request is not None:
                _gap_id, replay_from = request
                return _cursor_mod.ResumeDecision(
                    action=_cursor_mod.RESUME_ACTION_SUBSCRIBE_FROM_SLOT,
                    from_slot=int(replay_from),
                    reason=_cursor_mod.REASON_NONE)
            return _cursor_mod.ResumeDecision(
                action=_cursor_mod.RESUME_ACTION_BOOTSTRAP_LIVE_HEAD,
                from_slot=None, reason=_cursor_mod.REASON_NONE)
        store = self._cursor_store
        if store is None:
            # No cursor is owned: the caller claims no prior coverage.
            return _cursor_mod.ResumeDecision(
                action=_cursor_mod.RESUME_ACTION_BOOTSTRAP_LIVE_HEAD,
                from_slot=None, reason=_cursor_mod.REASON_NONE)
        decide = getattr(store, "resume_decision", None)
        if callable(decide):
            try:
                return decide()
            except Exception:
                return _cursor_mod.ResumeDecision(
                    action=_cursor_mod.RESUME_ACTION_REFUSE_TERMINAL,
                    from_slot=None,
                    reason=_cursor_mod.REASON_CURSOR_READBACK_FAILED)
        # A cursor object predating the typed decision: ask about terminal
        # state FIRST, so the ambiguous ``None`` can never mean "start at tip".
        try:
            if bool(store.is_terminal()):
                return _cursor_mod.ResumeDecision(
                    action=_cursor_mod.RESUME_ACTION_REFUSE_TERMINAL,
                    from_slot=None,
                    reason=_cursor_mod.REASON_REPLAY_POSITION_TOO_OLD)
        except Exception:
            pass
        try:
            slot = store.resume_from_slot()
        except Exception:
            # An unreadable cursor must never silently become "start at tip".
            return _cursor_mod.ResumeDecision(
                action=_cursor_mod.RESUME_ACTION_REFUSE_TERMINAL,
                from_slot=None,
                reason=_cursor_mod.REASON_CURSOR_READBACK_FAILED)
        if slot is None:
            return _cursor_mod.ResumeDecision(
                action=_cursor_mod.RESUME_ACTION_BOOTSTRAP_LIVE_HEAD,
                from_slot=None, reason=_cursor_mod.REASON_NONE)
        return _cursor_mod.ResumeDecision(
            action=_cursor_mod.RESUME_ACTION_SUBSCRIBE_FROM_SLOT,
            from_slot=int(slot), reason=_cursor_mod.REASON_NONE)

    def _resume_slot(self) -> Optional[int]:
        """The inclusive slot the next subscription must replay from."""

        decision = self._resume_decision()
        if not decision.builds_source:
            return None
        return decision.from_slot

    def _begin_stream_attempt(self, resume_slot: Optional[int]) -> None:
        """Durably pin the pre-attempt boundary before the stream is built.

        Propagates a persistence failure deliberately: an event must never
        advance the authoritative position while the position it moved away
        from was never written down.
        """

        if self._live_epoch is not None:
            return
        store = self._cursor_store
        if store is None:
            return
        begin = getattr(store, "begin_stream_attempt", None)
        if callable(begin):
            begin(requested_from_slot=resume_slot)
            return
        if resume_slot is not None:
            # A cursor object predating the attempt record.
            try:
                store.mark_recovery_started(from_slot=resume_slot)
            except Exception:
                pass

    def _build_source(self, resume_slot: Optional[int],
                      stream_generation: int,
                      transaction_observer: Optional[Callable[..., None]] = None,
                      ) -> Any:
        """Call the factory, threading the resume position when it accepts one.

        The cursor-aware/legacy decision was made ONCE at construction from the
        factory's declared signature.  It is deliberately not rediscovered from
        a ``TypeError`` at call time: a ``TypeError`` raised *inside* a
        cursor-aware factory is an ordinary bug, and treating it as evidence of
        a legacy signature silently retried the call with no resume position --
        turning any internal fault into a hidden loss of the durable cursor.
        """

        if not self._factory_is_cursor_aware:
            # Only reachable when the owner was constructed without
            # ``require_cursor_aware_factory``: probes, fixtures and the
            # generic development CLI.
            return self._source_factory()
        kwargs: Dict[str, Any] = dict(
            from_slot=resume_slot,
            cursor=self._cursor_store,
            downstream_durable_fn=self._last_handoff_was_durable,
            stream_generation=stream_generation,
        )
        if transaction_observer is not None and self._factory_accepts_observer:
            kwargs["transaction_observer"] = transaction_observer
        if (self._admission_inbox is not None and
                self._factory_accepts_kwarg(self._source_factory, "candidate_commit_fn")):
            kwargs["candidate_commit_fn"] = self._commit_source_candidate
        return self._source_factory(**kwargs)

    def _commit_source_candidate(self, event: object, **context: Any) -> bool:
        """Helius live/HTTP commit seam, called before source coverage advances."""
        self._handle_event(event, **context)
        return self._last_handoff_was_durable()

    @staticmethod
    def _factory_accepts_kwarg(factory: Callable[..., Any], name: str) -> bool:
        """Does this callable declare one optional keyword by name?"""

        try:
            signature = inspect.signature(factory)
        except (TypeError, ValueError):
            return False
        parameters = signature.parameters
        if any(p.kind is inspect.Parameter.VAR_KEYWORD
               for p in parameters.values()):
            return True
        return name in parameters

    @staticmethod
    def _factory_accepts_cursor_kwargs(factory: Callable[..., Any]) -> bool:
        """Does this callable declare the cursor-aware contract?"""

        try:
            signature = inspect.signature(factory)
        except (TypeError, ValueError):
            # An un-introspectable callable cannot be *proven* cursor-aware.
            return False
        parameters = signature.parameters
        if any(p.kind is inspect.Parameter.VAR_KEYWORD
               for p in parameters.values()):
            return True
        return all(name in parameters for name in CURSOR_AWARE_FACTORY_KWARGS)

    def _last_handoff_was_durable(self) -> bool:
        with self._lock:
            return bool(self._last_handoff_durable)

    def _coverage_state(self, source: Any) -> Dict[str, Any]:
        """Prove (or refuse to prove) that a resumed stream closed its gap.

        A stream opened WITHOUT a resume position claims no prior coverage, so
        it has no gap to close.  A stream opened WITH one must show the
        provider honoured it: because ``from_slot`` is inclusive and the
        cursor was committed at a slot where a matching transaction was seen,
        that transaction MUST be redelivered.  Observing it is positive proof.
        Not observing it -- or being told the position is unavailable -- leaves
        the gap unresolved rather than optimistically assuming coverage.
        """

        requested = bool(getattr(source, "replay_requested", False))
        if not requested:
            return {
                "gap_unresolved": False,
                "recovery_status": _cursor_mod.RECOVERY_NOT_REQUIRED,
                "recovery_reason": _cursor_mod.REASON_NONE,
                "state": _cursor_mod.STATE_LIVE_HEALTHY,
            }
        if bool(getattr(source, "replay_position_rejected", False)):
            return {
                "gap_unresolved": True,
                "recovery_status": _cursor_mod.RECOVERY_FAILED,
                "recovery_reason": _cursor_mod.REASON_REPLAY_POSITION_TOO_OLD,
                "state": _cursor_mod.STATE_REPLAY_RETENTION_EXCEEDED,
            }
        if bool(getattr(source, "overlap_observed", False)):
            # Overlap alone is not coverage. When a cursor is present the proof
            # must have BOUND to the episode boundary: an overlap against a
            # position the cursor moved to on its own proves only that the
            # provider honoured wherever the cursor is now pointing.
            if self._cursor_store is not None and not bool(
                    getattr(source, "overlap_proof_accepted", False)):
                return {
                    "gap_unresolved": True,
                    "recovery_status": _cursor_mod.RECOVERY_FAILED,
                    "recovery_reason": _cursor_mod.REASON_REPLAY_UNAVAILABLE,
                    "state": _cursor_mod.STATE_GAP_UNRESOLVED,
                }
            return {
                "gap_unresolved": False,
                "recovery_status": _cursor_mod.RECOVERY_CLOSED,
                "recovery_reason": _cursor_mod.REASON_NONE,
                "state": _cursor_mod.STATE_LIVE_HEALTHY,
            }
        if getattr(source, "first_slot_observed", None) is None:
            # Replay requested, nothing received yet: still catching up.
            return {
                "gap_unresolved": True,
                "recovery_status": _cursor_mod.RECOVERY_IN_PROGRESS,
                "recovery_reason": _cursor_mod.REASON_PROVIDER_DISCONNECT,
                "state": _cursor_mod.STATE_REPLAYING,
            }
        # Data arrived but the known boundary event never came back: the
        # provider did not honour the resume position.
        return {
            "gap_unresolved": True,
            "recovery_status": _cursor_mod.RECOVERY_FAILED,
            "recovery_reason": _cursor_mod.REASON_REPLAY_UNAVAILABLE,
            "state": _cursor_mod.STATE_GAP_UNRESOLVED,
        }

    def _run(self) -> None:
        first = True
        while not self._stop.is_set():
            source = None
            terminal_auth_failure = False
            terminal_recovery = False
            owner_error_class: Optional[str] = None
            watchdog_stop = threading.Event()
            watchdog_fired = threading.Event()
            watchdog_thread: Optional[threading.Thread] = None
            session_started = float(self._now())
            reconnect_reason = "PROVIDER_DISCONNECT"
            resume_slot: Optional[int] = None
            #: The open gap THIS attempt is replaying, or None for an ordinary
            #: live-head attempt. Only a bound gap may be settled below.
            replay_gap_id: Optional[str] = None
            # A terminal / quarantined / identity-mismatched cursor is decided
            # HERE: before a resume position is calculated, before the factory
            # is called, before a channel is opened and before any
            # SubscribeRequest exists. Nothing at all is constructed.
            decision = self._resume_decision()
            if not decision.builds_source:
                # Restart-resume hook for the bounded RPC gap recovery: ONLY a
                # replay-retention terminal may continue, and only through a
                # persisted, still-binding recovery episode. Every other
                # terminal reason (quarantine, identity mismatch, unreadable
                # cursor) stops exactly as certified, coordinator or not.
                if (self._gap_recovery is not None
                        and decision.reason
                        == _cursor_mod.REASON_REPLAY_POSITION_TOO_OLD
                        and not self._stop.is_set()):
                    if self._run_recovery_session(entry_classification=None) \
                            and not self._stop.is_set():
                        continue
                with self._lock:
                    self._terminal_recovery = True
                    self._last_refusal_reason = (
                        self._last_refusal_reason or decision.reason)
                    self._status = STREAM_STATUS_STOPPED
                self._stop.set()
                break
            with self._lock:
                self._connect_attempts += 1
                attempt_number = self._connect_attempts
                if not first:
                    self._reconnects += 1
                self._status = STREAM_STATUS_CONNECTING if first else STREAM_STATUS_RECONNECTING
            first = False
            try:
                # PHX2-E2E-008: the replacement stream resumes from the last
                # proven-safe slot instead of the provider's live head. The
                # factory keeps working with no argument for callers that own
                # no cursor.
                resume_slot = decision.from_slot
                # Bind THIS attempt to the gap it is replaying, before the
                # stream exists. The attempt is counted here rather than on
                # success so a provider that refuses every time still exhausts
                # the bounded budget and settles on RECOVERY_FAILED instead of
                # retrying the same dead position forever.
                if self._live_epoch is not None and resume_slot is not None:
                    pending_replay = self._continuity.replay_request()
                    if pending_replay is not None:
                        replay_gap_id = pending_replay[0]
                        self._continuity.mark_recovery_requested(
                            replay_gap_id, resume_slot)
                # R1: the pre-attempt safe boundary is made DURABLE before the
                # stream exists, so a provider that ignores ``from_slot``
                # cannot leave the moved high-water mark as the only surviving
                # record of the position that still owed coverage. A write
                # failure propagates: no attempt runs on an unrecorded boundary.
                self._begin_stream_attempt(resume_slot)
                with self._lock:
                    self._stream_generation += 1
                    stream_generation = self._stream_generation
                source = self._build_source(resume_slot, stream_generation)
                with self._lock:
                    self._active_source = source
                    self._active_streams += 1
                    self._max_active_streams = max(self._max_active_streams, self._active_streams)
                    # NOT "connected": constructing a source performs no I/O.
                    # The transport is only proven by a received update, and
                    # health additionally requires a closed coverage gap.
                    self._session_started_epoch = session_started
                watchdog_thread = threading.Thread(
                    target=self._watch_source,
                    kwargs={
                        "source": source,
                        "session_started": session_started,
                        "stop_event": watchdog_stop,
                        "fired_event": watchdog_fired,
                    },
                    name="phx2-grpc-staleness-watchdog",
                    daemon=True,
                )
                watchdog_thread.start()
                # Keep the one owned subscription alive for a queue-sized batch
                # instead of reconnecting after every migration.  The live
                # source itself has no ordinary-message scan ceiling and is
                # explicitly cancelled by stop().
                events: Iterable[Any] = source.iter_events(max_events=self._queue.maxsize)
                for event in events:
                    if self._stop.is_set():
                        break
                    if getattr(source, "candidate_handoff_owned", False):
                        # The source's explicit commit callback already ran
                        # before its processed cursor/HTTP coverage advanced.
                        continue
                    # Read the source's per-event provider-time side-channel
                    # synchronously, while it still describes THIS event.
                    self._handle_event(
                        event,
                        provider_event_time_utc=getattr(
                            source, "last_event_provider_time_utc", None),
                        provider_event_time_source=getattr(
                            source, "last_event_time_source", None),
                        replayed=bool(getattr(
                            source, "last_event_replayed", False)),
                        migration_proof=getattr(source, "last_event_migration_proof", None),
                        migration_signature=getattr(source, "last_event_signature", None),
                        event_slot=getattr(source, "last_event_slot", None))
                refusal = getattr(source, "last_refusal_reason", None)
                if getattr(source, "admission_commit_failed", False):
                    with self._lock:
                        self._admission_commit_failed = True
                        self._terminal_recovery = True
                    refusal = "ADMISSION_INBOX_COMMIT_FAILED"
                    self._stop.set()
                terminal_auth_failure = _is_terminal_auth_refusal(refusal)
                if terminal_auth_failure:
                    reconnect_reason = "AUTH_FAILURE"
                elif self._stop.is_set():
                    reconnect_reason = "OPERATOR_SHUTDOWN"
                elif watchdog_fired.is_set():
                    reconnect_reason = "WATCHDOG_STALE"
                elif refusal not in (None, "NONE"):
                    reconnect_reason = "PROVIDER_ERROR"
                with self._lock:
                    self._last_refusal_reason = str(refusal) if refusal else None
                    if refusal not in (None, "NONE"):
                        self._stream_errors += 1
                    if terminal_auth_failure:
                        self._terminal_auth_failure = True
                        self._status = STREAM_STATUS_AUTH_FAILED
            except Exception as exc:
                reconnect_reason = "OWNER_ERROR"
                owner_error_class = _safe_owner_error_class(exc)
                with self._lock:
                    self._stream_errors += 1
                    self._last_refusal_reason = "STREAM_OWNER_ERROR"
            finally:
                watchdog_stop.set()
                # PHX2-E2E-008: settle this attempt's coverage claim, then
                # persist the known gap boundary so the next subscription
                # resumes from it instead of from the provider's live head.
                coverage_at_end: Dict[str, Any] = (
                    self._coverage_state(source) if source is not None
                    else {"gap_unresolved": False,
                          "recovery_status": _cursor_mod.RECOVERY_NOT_REQUIRED,
                          "recovery_reason": _cursor_mod.REASON_NONE,
                          "state": _cursor_mod.STATE_STOPPED})
                # Canonical continuity bookkeeping, run in EVERY mode. This is
                # the repair for the proven defect: the cursor block below is
                # gated on live-epoch being OFF, so production recorded nothing
                # about the slot the dying stream actually reached. The
                # replacement subscription then re-armed at the provider's live
                # head and the skipped backlog vanished with every gap counter
                # reading zero. Recording a gap is evidence, never a stop: the
                # stream keeps observing forward, it simply may no longer claim
                # continuous coverage.
                if source is not None:
                    last_seen = getattr(source, "highest_slot_observed", None)
                    if isinstance(last_seen, int) \
                            and not isinstance(last_seen, bool) \
                            and not self._source_owned_gap_recovery \
                            and not getattr(source, "admission_commit_failed", False) \
                            and self._last_handoff_was_durable():
                        self._continuity.note_slot(last_seen, processed=True)
                # Settle the replay attempt bound at the top of this iteration.
                # A gap is only ever RECOVERED by proven coverage -- credited
                # slot by slot through ``note_slot`` as they are processed --
                # so a provider that silently ignores ``from_slot`` and serves
                # the live head cannot reach this branch with the gap closed.
                # Every other ending is an explicit, closed-set failure.
                # A cooperative shutdown is not a failed recovery: settling it
                # would spend the bounded budget on an attempt the operator
                # ended, so the episode resumes intact on the next start.
                if replay_gap_id is not None and not self._stop.is_set():
                    still_open = any(gap.gap_id == replay_gap_id
                                     for gap in self._continuity.open_gaps())
                    if still_open:
                        if bool(getattr(source, "replay_position_rejected",
                                        False)):
                            # The provider answered that the position is past
                            # its retention window: no attempt count will ever
                            # make it servable. Terminal for THIS gap only --
                            # the owner keeps observing forward.
                            self._continuity.mark_recovery_failed(
                                replay_gap_id,
                                reason=_continuity_mod
                                .FAILURE_REPLAY_POSITION_TOO_OLD,
                                unavailable=True)
                        elif int(getattr(source, "replayed_events", 0) or 0) > 0:
                            # Something was served but the range is still not
                            # proven: retryable, and PARTIALLY_RECOVERED once
                            # any coverage exists.
                            self._continuity.mark_recovery_failed(
                                replay_gap_id,
                                reason=_continuity_mod.FAILURE_REPLAY_INCOMPLETE)
                        else:
                            # Requested and nothing replayed: the provider
                            # refused or ignored the position.
                            self._continuity.mark_recovery_failed(
                                replay_gap_id,
                                reason=_continuity_mod.FAILURE_REPLAY_REFUSED)
                if not self._stop.is_set() and not self._source_owned_gap_recovery:
                    self._continuity.note_disconnect(
                        reason_class=str(reconnect_reason))
                if self._live_epoch is None and self._cursor_store is not None and source is not None:
                    try:
                        if bool(getattr(source, "replay_position_rejected",
                                        False)):
                            # The provider refused the resume position itself:
                            # terminal, not another reconnect.
                            self._cursor_store.mark_replay_retention_exceeded(
                                first_available=getattr(
                                    source, "replay_first_available", None))
                            terminal_recovery = True
                        elif coverage_at_end["gap_unresolved"]:
                            # Pin the episode to the position THIS attempt
                            # requested, never to the high-water mark the
                            # attempt may just have advanced past it.
                            self._cursor_store.mark_recovery_failed(
                                reason=coverage_at_end["recovery_reason"],
                                attempted_from_slot=resume_slot)
                        elif getattr(source, "replay_requested", False):
                            # Confirm the episode against the boundary this
                            # attempt actually requested; never against the
                            # position the cursor happens to hold now.
                            self._cursor_store.mark_gap_closed(
                                requested_from_slot=getattr(
                                    source, "expected_overlap_slot", None),
                                proven_boundary_slot=getattr(
                                    source, "overlap_proof_slot", None),
                                recovery_generation=int(getattr(
                                    source, "recovery_generation", 0) or 0))
                        if not self._stop.is_set() and not terminal_recovery:
                            self._cursor_store.mark_disconnect(
                                reason=_cursor_mod.REASON_PROVIDER_DISCONNECT,
                                attempted_from_slot=resume_slot)
                    except Exception:
                        # Cursor bookkeeping never interferes with stream
                        # cleanup or reconnect policy.
                        pass
                    try:
                        if self._cursor_store.is_terminal():
                            terminal_recovery = True
                    except Exception:
                        pass
                diag_fn = getattr(source, "diagnostic_snapshot", None)
                try:
                    source_diag = diag_fn() if callable(diag_fn) else {}
                except Exception:
                    # Diagnostics must never interfere with stream cleanup or reconnect policy.
                    source_diag = {
                        "error_class": "DIAGNOSTIC_SNAPSHOT_ERROR",
                        "grpc_status_code": None,
                        "sanitized_error_category": "DIAGNOSTIC_SNAPSHOT_ERROR",
                        "sanitized_details": (
                            "The diagnostic snapshot failed; raw exception text was withheld."),
                        "stream_phase": "DIAGNOSTIC_SNAPSHOT",
                        "iterator_end_kind": "DIAGNOSTIC_SNAPSHOT_ERROR",
                        "cancellation_requested": False,
                    }
                if not isinstance(source_diag, dict):
                    source_diag = {}
                cancellation_requested = bool(
                    source_diag.get("cancellation_requested", False))
                close = getattr(source, "close", None)
                if callable(close):
                    try:
                        close()
                    except Exception:
                        pass
                # Flush any batched cursor commits accumulated during this
                # attempt so the durable resume position is current at every
                # stream boundary -- reconnect, disconnect and cooperative
                # shutdown alike. Best-effort and non-raising: a failed flush is
                # surfaced through the cursor durability status/counters and the
                # position simply replays, never crashing teardown.
                if self._cursor_store is not None:
                    flush = getattr(self._cursor_store, "flush_if_pending", None)
                    if callable(flush):
                        try:
                            flush()
                        except Exception:
                            pass
                if watchdog_thread is not None:
                    watchdog_thread.join(timeout=1.0)
                attempt_ended = float(self._now())
                duration = round(max(0.0, attempt_ended - session_started), 3)
                # This decrement always happens before the reconnect delay and
                # before a new factory call: overlap is structurally impossible.
                ended_admission = _admission_counts(source)
                with self._lock:
                    active_before_cleanup = self._active_streams
                    self._source_updates_scanned += int(
                        getattr(source, "events_scanned", 0) or 0)
                    self._source_transactions_scanned += int(
                        getattr(source, "transactions_scanned", 0) or 0)
                    self._source_create_pool_yielded += int(
                        getattr(source, "create_pool_yielded", 0) or 0)
                    self._source_reserve_events_decoded += int(
                        getattr(source, "reserve_events_decoded", 0) or 0)
                    self._source_fee_events_decoded += int(
                        getattr(source, "fee_events_decoded", 0) or 0)
                    self._replay_events += int(
                        getattr(source, "replayed_events", 0) or 0)
                    self._replay_duplicates += int(
                        getattr(source, "replay_duplicates_suppressed", 0) or 0)
                    if getattr(source, "replay_requested", False):
                        self._replay_requested_total += 1
                    if getattr(source, "replay_position_rejected", False):
                        self._replay_too_old_total += 1
                    if coverage_at_end.get("gap_unresolved"):
                        self._gap_recovery_failed_total += 1
                    for key, value in ended_admission.items():
                        self._admission_totals[key] = (
                            self._admission_totals.get(key, 0) + value)
                    if self._active_source is source:
                        self._active_source = None
                    if self._active_streams > 0:
                        self._active_streams -= 1
                    active_after_cleanup = self._active_streams
                    self._session_started_epoch = None
                    self._last_session_duration_s = duration
                    if (self._shortest_session_duration_s is None
                            or duration < self._shortest_session_duration_s):
                        self._shortest_session_duration_s = duration
                    if (self._longest_session_duration_s is None
                            or duration > self._longest_session_duration_s):
                        self._longest_session_duration_s = duration
                    self._last_reconnect_reason = reconnect_reason
                    self._reconnect_reasons[reconnect_reason] = (
                        self._reconnect_reasons.get(reconnect_reason, 0) + 1
                    )
                    if reconnect_reason == "AUTH_FAILURE":
                        self._authentication_failures += 1
                    elif reconnect_reason == "WATCHDOG_STALE":
                        self._watchdog_reconnects += 1
                    elif reconnect_reason == "OPERATOR_SHUTDOWN":
                        self._operator_shutdowns += 1
                    elif reconnect_reason in ("PROVIDER_DISCONNECT", "PROVIDER_ERROR"):
                        self._provider_disconnects += 1
                    if not self._stop.is_set() and not terminal_auth_failure:
                        self._status = STREAM_STATUS_RECONNECTING
                error_class = source_diag.get("error_class")
                if owner_error_class is not None:
                    error_class = owner_error_class
                attempt_record = {
                    "attempt_number": attempt_number,
                    "attempt_started_at_utc": _utc_iso(session_started),
                    "stream_started_at_utc": _utc_iso(
                        getattr(source, "stream_started_epoch", None)),
                    "connection_established_at_utc": _utc_iso(
                        getattr(source, "first_update_epoch", None)),
                    "attempt_ended_at_utc": _utc_iso(attempt_ended),
                    "stream_duration_seconds": duration,
                    "last_message_at_utc": _utc_iso(
                        getattr(source, "last_update_epoch", None)),
                    "last_decoded_event_at_utc": _utc_iso(
                        getattr(source, "last_decoded_event_epoch", None)),
                    "seconds_since_last_message": _age_seconds(
                        attempt_ended, getattr(source, "last_update_epoch", None)),
                    "seconds_since_last_decoded_event": _age_seconds(
                        attempt_ended, getattr(source, "last_decoded_event_epoch", None)),
                    "reconnect_reason": reconnect_reason,
                    "error_class": error_class,
                    "grpc_status_code": source_diag.get("grpc_status_code"),
                    "sanitized_error_category": (
                        "OWNER_LOCAL_EXCEPTION" if owner_error_class is not None
                        else source_diag.get("sanitized_error_category")),
                    "sanitized_details": (
                        "A local exception escaped the stream owner; raw text was withheld."
                        if owner_error_class is not None else source_diag.get("sanitized_details")),
                    "stream_phase": (
                        "OWNER" if owner_error_class is not None
                        else source_diag.get("stream_phase")),
                    "iterator_end_kind": (
                        "OWNER_ERROR" if owner_error_class is not None
                        else source_diag.get("iterator_end_kind")),
                    "watchdog_trigger_kind": (
                        "LAST_MESSAGE_STALE" if watchdog_fired.is_set() else None),
                    "cancellation_requested": cancellation_requested,
                    "shutdown_requested": self._stop.is_set(),
                    "shutdown_state": (
                        "STOP_REQUESTED" if self._stop.is_set() else "RUNNING"),
                    "reconnect_scheduled": False,
                    "reconnect_delay_seconds": None,
                    "active_streams_before_cleanup": active_before_cleanup,
                    "active_streams_after_cleanup": active_after_cleanup,
                }
            if terminal_auth_failure or terminal_recovery:
                # Live-refusal hook for the bounded RPC gap recovery: only a
                # SPECIFICALLY classified retention refusal (the retention
                # pre-check, or OUT_OF_RANGE against a requested replay) may
                # enter the bounded backfill. Authentication failures,
                # INVALID_ARGUMENT, NOT_FOUND and every unknown refusal remain
                # terminal without conversion. The cursor was already
                # terminal-locked above; the coordinator is the only exit.
                recovery_entry: Optional[str] = None
                if (terminal_recovery and not terminal_auth_failure
                        and self._gap_recovery is not None
                        and source is not None and not self._stop.is_set()):
                    classification = self._classify_recovery_entry(source)
                    if classification is not None:
                        recovery_entry = classification
                if recovery_entry is not None:
                    with self._lock:
                        self._stream_attempts.append(attempt_record)
                        self._stream_attempts = self._stream_attempts[
                            -_ATTEMPT_HISTORY_MAX:]
                    if self._run_recovery_session(
                            entry_classification=recovery_entry) \
                            and not self._stop.is_set():
                        continue
                # A dead resume position must not drive a reconnect storm: the
                # only mutator that could repair it needs an event that can
                # never arrive. Stop, keep the cursor evidence intact, stay
                # unhealthy, and require operator remediation.
                with self._lock:
                    if terminal_recovery:
                        self._terminal_recovery = True
                        self._last_refusal_reason = (
                            self._last_refusal_reason
                            or _cursor_mod.REASON_REPLAY_POSITION_TOO_OLD)
                    if recovery_entry is None:
                        self._stream_attempts.append(attempt_record)
                        self._stream_attempts = self._stream_attempts[
                            -_ATTEMPT_HISTORY_MAX:]
                self._stop.set()
                break
            if self._live_epoch is not None and not self._stop.is_set():
                try:
                    epoch_before = None
                    boundary_before = None
                    try:
                        before_snap = dict(self._live_epoch.snapshot())
                        epoch_before = before_snap.get("live_epoch_id")
                        boundary_before = before_snap.get("epoch_start_slot")
                    except Exception:
                        pass
                    self._live_epoch.rollover(reconnect_reason)
                    # Rollover NEVER clears continuity evidence: the re-arm is
                    # recorded ON the open gap so a reader can see exactly
                    # which epoch boundary jumped over which unproven range.
                    try:
                        after_snap = dict(self._live_epoch.snapshot())
                        self._continuity.note_epoch_rollover(
                            epoch_before=epoch_before,
                            epoch_after=after_snap.get("live_epoch_id"),
                            boundary_before=boundary_before,
                            boundary_after=after_snap.get("epoch_start_slot"))
                    except Exception:
                        pass
                except Exception:
                    with self._lock:
                        self._terminal_recovery = True
                        self._last_refusal_reason = "EPOCH_INTEGRITY_FAILURE"
                    self._stop.set()
                    break
            jitter = self._backoff * self._jitter_fraction * (2.0 * self._random() - 1.0)
            delay = max(0.0, self._backoff + jitter)
            attempt_record["reconnect_scheduled"] = not self._stop.is_set()
            attempt_record["reconnect_delay_seconds"] = (
                round(delay, 3) if attempt_record["reconnect_scheduled"] else None)
            with self._lock:
                self._stream_attempts.append(attempt_record)
                self._stream_attempts = self._stream_attempts[-_ATTEMPT_HISTORY_MAX:]
            if self._stop.wait(delay):
                break
        if self._live_epoch is not None:
            try:
                self._live_epoch.close("OPERATOR_SHUTDOWN")
            except Exception:
                pass
        with self._lock:
            if self._active_streams == 0 and not self._terminal_auth_failure:
                self._status = STREAM_STATUS_STOPPED

    # -- bounded RPC gap recovery (PROVIDER-REPLAY-001) -------------------

    def _classify_recovery_entry(self, source: Any) -> Optional[str]:
        """The coordinator entry token for this refusal, or ``None``.

        Delegates the classification itself to the recovery module's closed
        set; answers ``None`` for everything that must remain terminal.
        """

        try:
            from PHX2.free_tier_producer.rpc_gap_recovery import (
                BACKFILL_ELIGIBLE_CLASSIFICATIONS,
                classify_replay_refusal,
            )
        except Exception:
            return None
        classification = classify_replay_refusal(
            replay_requested=bool(getattr(source, "replay_requested", False)),
            replay_position_rejected=bool(
                getattr(source, "replay_position_rejected", False)),
            sanitized_error_category=getattr(
                source, "sanitized_error_category", None),
            grpc_status_code=getattr(source, "grpc_status_code", None),
        )
        if classification not in BACKFILL_ELIGIBLE_CLASSIFICATIONS:
            return None
        return classification

    def _drain_recovered_buffer(self) -> None:
        """Apply buffered quarantined candidates once, in deterministic order.

        Runs only after ``RECOVERY_PROVEN``.  Every application travels the
        normal admission path, so exact event-id/mint dedupe suppresses the
        copies the RPC backfill already applied.  When the quarantine spanned
        more than one live-stream segment the internal gap between segments
        was never proven, so a fresh ordinary recovery episode is opened at
        the drained boundary -- the owner must never report healthy across an
        unproven range.
        """

        coordinator = self._gap_recovery
        if coordinator is None:
            return
        plan = coordinator.drain_plan()
        applied = 0
        suppressed = 0
        for entry in plan.get("candidates") or []:
            candidate = entry.get("candidate")
            if not isinstance(candidate, dict) or not candidate:
                continue
            if self._admit_candidate(dict(candidate)):
                applied += 1
            else:
                suppressed += 1
        try:
            coordinator.mark_drained(applied=applied, suppressed=suppressed)
        except Exception:
            pass
        if plan.get("requires_reopened_episode") \
                and plan.get("reopen_boundary_slot") is not None \
                and self._cursor_store is not None:
            try:
                self._cursor_store.mark_disconnect(
                    reason=_cursor_mod.REASON_PROVIDER_DISCONNECT,
                    attempted_from_slot=int(plan["reopen_boundary_slot"]))
            except Exception:
                pass

    def _run_recovery_session(
        self, *, entry_classification: Optional[str]) -> bool:
        """One bounded RPC gap-recovery episode: quarantine + backfill + drain.

        Returns ``True`` only when the episode reached ``RECOVERY_PROVEN`` and
        the buffered live events were drained.  The quarantined replacement
        stream is THE one gRPC stream of the owner -- no second subscription
        exists at any point -- and its events reach the normal pipeline only
        after the proof.  A failed session leaves the cursor terminal-locked
        exactly as certified.
        """

        coordinator = self._gap_recovery
        if coordinator is None or self._cursor_store is None:
            return False
        if not self._factory_is_cursor_aware \
                or not self._factory_accepts_observer:
            try:
                from PHX2.free_tier_producer.rpc_gap_recovery import (
                    TERMINAL_RECOVERY_SOURCE_OBSERVER_UNSUPPORTED,
                )
                coordinator.mark_session_failure(
                    TERMINAL_RECOVERY_SOURCE_OBSERVER_UNSUPPORTED)
            except Exception:
                pass
            return False
        ok, _detail = coordinator.begin_or_resume_episode(
            cursor_store=self._cursor_store,
            entry_classification=entry_classification)
        if not ok:
            return False
        with self._lock:
            self._status = STREAM_STATUS_RECONNECTING
            self._recovery_sessions += 1
        backfill_outcome = {"proven": False}

        def _backfill_worker() -> None:
            """Run the backfill, resuming across every retryable pause.

            A pause means one bounded ATTEMPT clock expired while the durable
            evidence stayed intact; the next attempt resumes at
            ``last_completed_slot + 1``.  Resumes are bounded so a provider that
            cannot keep up ends the pre-soak rather than looping forever, and a
            terminal episode still ends immediately.
            """

            attempts = 0
            try:
                max_resumes = int(
                    coordinator.config.max_backfill_resume_attempts)
            except Exception:
                max_resumes = 0
            while True:
                try:
                    proven = bool(coordinator.run_backfill(
                        apply_candidate_fn=self._admit_candidate))
                except Exception:
                    proven = False
                backfill_outcome["proven"] = proven
                backfill_outcome["resume_attempts"] = attempts
                if proven or self._stop.is_set():
                    return
                if not coordinator.is_paused():
                    # Terminal, or a stop was requested inside the pass.
                    return
                if attempts >= max_resumes:
                    backfill_outcome["resume_budget_exhausted"] = True
                    return
                attempts += 1
                try:
                    coordinator.note_resume_attempt()
                except Exception:
                    pass

        backfill_thread = threading.Thread(
            target=_backfill_worker, name="phx2-rpc-gap-backfill", daemon=True)
        backfill_thread.start()
        promoted = False
        drained = False
        observed_holder: Dict[str, Any] = {}
        try:
            while not self._stop.is_set() and not coordinator.is_terminal():
                coordinator.begin_quarantine_segment()
                # Deliberately NO ``begin_stream_attempt`` here: the
                # quarantined stream claims no coverage, and clearing the
                # refused attempt's pinned boundary would strip the terminal
                # document of the very pin its cross-field validation (BL-1)
                # requires. The terminal episode itself is the protection.
                with self._lock:
                    self._stream_generation += 1
                    stream_generation = self._stream_generation
                try:
                    attempt_generation = int(
                        self._cursor_store.state.attempt_generation)
                except Exception:
                    attempt_generation = 0

                def _observer(slot: int, signature: str,
                              tx_index: Optional[int], skip_identity: str,
                              _generation: int = attempt_generation) -> None:
                    observed_holder["last"] = (
                        slot, signature, tx_index, skip_identity)
                    coordinator.note_observed_transaction(
                        slot=slot, signature=signature,
                        transaction_index=tx_index,
                        skip_identity=skip_identity,
                        attempt_generation=_generation)

                source = self._build_source(
                    None, stream_generation, transaction_observer=_observer)
                with self._lock:
                    self._active_source = source
                    self._active_streams += 1
                    self._max_active_streams = max(
                        self._max_active_streams, self._active_streams)
                try:
                    for event in source.iter_events(
                            max_events=self._queue.maxsize):
                        if self._stop.is_set() or coordinator.is_terminal():
                            break
                        if not promoted and coordinator.is_proven():
                            self._drain_recovered_buffer()
                            drained = True
                            promoted = True
                        if promoted:
                            if getattr(source, "candidate_handoff_owned", False):
                                continue
                            self._handle_event(
                                event,
                                provider_event_time_utc=getattr(
                                    source, "last_event_provider_time_utc",
                                    None),
                                provider_event_time_source=getattr(
                                    source, "last_event_time_source", None),
                                replayed=bool(getattr(
                                    source, "last_event_replayed", False)),
                                migration_proof=getattr(source, "last_event_migration_proof", None),
                                migration_signature=getattr(source, "last_event_signature", None),
                                event_slot=getattr(
                                    source, "last_event_slot", None))
                            continue
                        # Quarantined: decoded evidence goes to the bounded
                        # buffer, never to the queue/watchlist/scheduler.
                        with self._lock:
                            self._events_received += 1
                            self._last_message_epoch = float(self._now())
                            self._last_handoff_durable = False
                        durable = False
                        candidate = event_to_candidate(
                            event, replayed=False,
                            migration_proof=getattr(source, "last_event_migration_proof", None),
                            migration_signature=getattr(source, "last_event_signature", None),
                            provider_event_time_utc=getattr(
                                source, "last_event_provider_time_utc", None),
                            provider_event_time_source=getattr(
                                source, "last_event_time_source", None))
                        position = observed_holder.get("last")
                        if candidate is None:
                            # Deterministic classification; nothing owed.
                            durable = True
                        elif position is not None:
                            slot, signature, tx_index, skip_identity = position
                            # A buffered candidate must carry its OWN source
                            # transaction slot so a later drain delivers the
                            # exact event/slot association (never a null and
                            # never another event's slot).
                            candidate["migration_slot"] = slot
                            durable = coordinator.buffer_admitted_candidate(
                                candidate=candidate, slot=slot,
                                signature=signature,
                                transaction_index=tx_index,
                                skip_identity=skip_identity,
                                attempt_generation=attempt_generation)
                        self._mark_handoff_durable(durable)
                finally:
                    close = getattr(source, "close", None)
                    if callable(close):
                        try:
                            close()
                        except Exception:
                            pass
                    with self._lock:
                        if self._active_source is source:
                            self._active_source = None
                        if self._active_streams > 0:
                            self._active_streams -= 1
                if not promoted and coordinator.is_proven():
                    self._drain_recovered_buffer()
                    drained = True
                    promoted = True
                    # Proof landed while the stream was down: the episode is
                    # closed; the outer loop reconnects through the ordinary
                    # certified path.
                    break
                if promoted:
                    # The healthy post-proof stream ended ordinarily.
                    if not self._stop.is_set() \
                            and self._cursor_store is not None:
                        try:
                            self._cursor_store.mark_disconnect(
                                reason=_cursor_mod.REASON_PROVIDER_DISCONNECT)
                        except Exception:
                            pass
                    break
                if self._stop.wait(self._backoff):
                    break
        finally:
            try:
                coordinator.request_stop()
            except Exception:
                pass
            backfill_thread.join(timeout=10.0)
        if coordinator.is_proven():
            if not drained:
                self._drain_recovered_buffer()
            return True
        return False

    def _watch_source(
        self,
        *,
        source: Any,
        session_started: float,
        stop_event: threading.Event,
        fired_event: threading.Event,
    ) -> None:
        """Cancel one stale source; replacement remains sequential in ``_run``."""
        interval = max(0.05, min(1.0, self._stale_after / 4.0))
        while not self._stop.is_set() and not stop_event.wait(interval):
            last_update = getattr(source, "last_update_epoch", None)
            anchor = float(last_update) if isinstance(last_update, (int, float)) else session_started
            if float(self._now()) - anchor <= self._stale_after:
                continue
            fired_event.set()
            close = getattr(source, "close", None)
            if callable(close):
                try:
                    close()
                except Exception:
                    pass
            return

    def _handle_event(self, event: object, *,
                      provider_event_time_utc: Optional[str] = None,
                      provider_event_time_source: Optional[str] = None,
                      replayed: bool = False,
                      migration_proof: object = None,
                      migration_signature: Optional[str] = None,
                      event_slot: Optional[int] = None) -> None:
        # PHX2-E2E-008: every exit path below must leave this flag describing
        # whether THIS event's handoff was made durable. The source consults
        # it after the yield returns and holds the cursor when it is False,
        # so a lost handoff replays instead of being silently skipped.
        with self._lock:
            self._events_received += 1
            self._last_message_epoch = float(self._now())
            self._last_handoff_durable = False
        # The frozen normalized event has no slot field; the transaction slot
        # arrives on the source's per-event side-channel exactly like the
        # provider event time. Falling back to a (nonexistent) event attribute
        # made the fail-closed live-epoch gate reject EVERY live migration
        # (EPOCH_EVENT_PRE_ARM_REJECTED, migration_slot null) and starve the
        # watchlist of live candidates entirely.
        slot_for_epoch: Optional[int] = (
            event_slot if isinstance(event_slot, int)
            and not isinstance(event_slot, bool)
            else getattr(event, "slot", None))
        epoch_id: Optional[str] = None
        if self._live_epoch is not None:
            admitted, epoch_reason, epoch_id = self._live_epoch.admit_event(
                slot_for_epoch)
            if not admitted:
                self._emit_handoff(
                    "EPOCH_EVENT_REJECTED", reason=epoch_reason,
                    live_epoch_id=epoch_id,
                    migration_slot=slot_for_epoch)
                self._mark_handoff_durable(True)
                return
        candidate = event_to_candidate(
            event, replayed=replayed,
            migration_proof=migration_proof,
            migration_signature=migration_signature,
            provider_event_time_utc=provider_event_time_utc,
            provider_event_time_source=provider_event_time_source)
        if candidate is not None and event_slot is not None:
            proof_slot = candidate.get("migration_slot")
            if proof_slot is not None and proof_slot != event_slot:
                candidate = None
            elif candidate is not None:
                candidate["migration_slot"] = event_slot
        if candidate is not None and self._live_epoch is not None:
            candidate["live_epoch_id"] = epoch_id
            candidate["migration_slot"] = slot_for_epoch
        if candidate is None:
            with self._lock:
                self._invalid_base_mint_dropped += 1
            self._emit_handoff("MALFORMED_EVENT", reason="INVALID_BASE_MINT")
            # Deterministic classification, nothing owed downstream.
            self._mark_handoff_durable(True)
            return
        self._admit_candidate(candidate)

    def _admit_candidate(self, candidate: Dict[str, Any]) -> bool:
        """Admit ONE decoded candidate through dedupe, queue and handoff.

        The single admission boundary for live events, RPC-backfilled events
        and post-proof drained quarantine events alike -- which is exactly why
        an event seen by more than one source applies once.  Returns ``True``
        when candidate ownership is durable. With an inbox, memory queue
        pressure cannot discard ownership; without one, the historical
        queue/audit handoff applies. Deterministic rejections and duplicates
        return ``False`` while separately marking the source row processed.
        """

        with self._admit_lock:
            with self._lock:
                self._candidates_decoded += 1
            self._emit_handoff("CANDIDATE_DECODED", candidate, reason="DECODED")
            mint = candidate["token_mint"]
            # Same proof-bound guard as session and restart. A suffix is only
            # retained for legacy inputs that claim no sealed migration proof.
            if not candidate_migration_is_admitted(candidate):
                with self._lock:
                    self._non_pump_dropped += 1
                self._emit_handoff(
                    "NON_PUMP_DROPPED", candidate, reason="NON_PUMP_SUFFIX")
                self._mark_handoff_durable(True)
                return False
            if self._admission_inbox is None and self._queue.full():
                # Refuse before consuming dedupe. Only this admission owner
                # enqueues, while concurrent consumers can only free capacity.
                with self._lock:
                    self._queue_dropped += 1
                self._emit_handoff("QUEUE_FULL", candidate, reason="QUEUE_FULL",
                                   queue_depth=self._queue.qsize())
                self._mark_handoff_durable(False)
                return False

            def commit_receipt() -> None:
                if self._admission_inbox is None:
                    return
                epoch = self._live_epoch.snapshot()
                if epoch.get("live_epoch_id") != candidate.get("live_epoch_id"):
                    raise AdmissionInboxError("ADMISSION_EPOCH_CHANGED")
                self._admission_inbox.put(candidate,
                    first_eligible_slot=epoch.get("epoch_start_slot"))

            try:
                accepted, dedupe_reason = self._dedupe.accept_with_reason(
                    event_id=candidate.get("provider_event_id"), mint=mint,
                    before_accept=commit_receipt)
            except (AdmissionInboxError, OSError):
                self._mark_handoff_durable(False)
                with self._lock:
                    self._last_refusal_reason = "ADMISSION_INBOX_COMMIT_FAILED"
                    self._admission_commit_failed = True
                    self._terminal_recovery = True
                self._stop.set()
                raise
            if not accepted:
                if dedupe_reason == "DUPLICATE_MINT" \
                        and candidate.get("discovery_provenance") in (
                            LIVE_DISCOVERY_PROVENANCES):
                    try:
                        self._corroboration_queue.put_nowait(dict(candidate))
                    except queue.Full:
                        pass
                self._emit_handoff(
                    dedupe_reason, candidate, reason=dedupe_reason)
                # Already-known candidate: the earlier acceptance owns the work.
                self._mark_handoff_durable(True)
                return False
            # The shared dedupe has now consumed this candidate's event id AND
            # its mint. Carry that fact ON the candidate so the session-level
            # discovery boundary can skip a second pass against the SAME
            # instance -- which would reject every admitted candidate as
            # DUPLICATE_MINT on the mint the acceptance above just recorded.
            mark_provider_dedupe_applied(candidate)
            enqueued_at = float(self._now())
            with self._lock:
                self._queue_sequence += 1
                sequence = self._queue_sequence
                self._queued_at[sequence] = enqueued_at
            candidate["provider_handoff"] = {
                "queue_sequence": sequence,
                "enqueued_at_utc": _utc_iso(enqueued_at),
                "enqueued_at_epoch": enqueued_at,
            }
            try:
                self._queue.put_nowait(candidate)
            except queue.Full:
                with self._lock:
                    self._queue_dropped += 1
                    self._queued_at.pop(sequence, None)
                self._emit_handoff(
                    "QUEUE_FULL", candidate, reason="QUEUE_FULL",
                    queue_depth=self._queue.qsize())
                # A durable inbox retains the complete candidate for the watch
                # replay path even when the memory queue is full.
                durable = self._admission_inbox is not None
                self._mark_handoff_durable(durable)
                return durable
            with self._lock:
                self._candidates_accepted += 1
                self._last_candidate_epoch = float(self._now())
            depth = self._queue.qsize()
            accepted_written = self._emit_handoff(
                "CANDIDATE_ACCEPTED", candidate, reason="ACCEPTED",
                queue_depth=depth)
            enqueued_written = self._emit_handoff(
                "CANDIDATE_ENQUEUED", candidate, reason="ENQUEUED",
                queue_depth=depth, queue_sequence=sequence)
            # Production ownership was committed before dedupe/enqueue. Legacy
            # owners without an inbox retain their audit-write cursor contract.
            durable = bool(self._admission_inbox is not None or
                           (accepted_written and enqueued_written))
            self._mark_handoff_durable(durable)
            # PHX2-E2E-006: a freshly enqueued genuine candidate wakes the
            # watch loop so admission is not quantized to the maintenance
            # interval.
            waker = self._enqueue_waker
            if waker is not None:
                try:
                    waker()
                except Exception:
                    pass
            return durable

    def _mark_handoff_durable(self, durable: bool) -> None:
        with self._lock:
            self._last_handoff_durable = bool(durable)


def adapt_zero_argument_factory_TEST_ONLY(
    factory: Callable[[], Any],
) -> Callable[..., Any]:
    """Wrap a legacy zero-argument factory for the cursor-aware contract.

    Deliberately named so it can never be mistaken for a production path: the
    adapted factory SWALLOWS the resume position, so a stream it builds cannot
    replay.  It exists only so offline fixtures and probes that predate the
    cursor can still be driven through an owner that enforces the contract.
    """

    def _adapter(*, from_slot: Any = None, cursor: Any = None,
                 downstream_durable_fn: Any = None,
                 stream_generation: int = 0) -> Any:
        return factory()

    _adapter.__name__ = "zero_argument_factory_adapter_TEST_ONLY"
    return _adapter


def build_live_source_factory(*, reserve_index: Any = None,
                              fee_index: Any = None,
                              liquidity_index: Any = None,
                              admission_config: Any = None,
                              admission_sink: Any = None,
                              proof_store: Any = None,
                              transport_slot_observer: Any = None,
                              census_sink: Any = None,
                              runtime_config: Any = None) -> Callable[[], Any]:
    """Build the production factory without exposing endpoint/token values."""
    from PHX2.stage28.chainstack_yellowstone_grpc_models import MODE_PROVIDER_CONNECT_ONLY
    from PHX2.stage28.chainstack_yellowstone_grpc_readiness import build_runtime_config_from_env
    from PHX2.free_tier_producer.paid_grpc_source import PaidCreatePoolYellowstoneSource

    resolved_runtime_config = runtime_config
    if resolved_runtime_config is None:
        resolved_runtime_config = build_runtime_config_from_env(
            mode=MODE_PROVIDER_CONNECT_ONLY, max_events=1
        )

    def _factory(*, from_slot: Any = None, cursor: Any = None,
                 downstream_durable_fn: Any = None,
                 stream_generation: int = 0,
                 transaction_observer: Any = None) -> Any:
        # PHX2-E2E-008: the reconnect owner supplies the durable resume
        # position. Every parameter is optional so a zero-argument call keeps
        # the historical tip-anchored behaviour for probes and fixtures.
        return PaidCreatePoolYellowstoneSource(
            runtime_config=resolved_runtime_config, max_messages_to_scan=None,
            reserve_index=reserve_index,
            fee_index=fee_index,
            liquidity_index=liquidity_index,
            admission_config=admission_config,
            admission_sink=admission_sink,
            proof_store=proof_store,
            from_slot=from_slot,
            cursor=cursor,
            downstream_durable_fn=downstream_durable_fn,
            stream_generation=stream_generation,
            transaction_observer=transaction_observer,
            transport_slot_observer=transport_slot_observer,
            census_sink=census_sink,
        )

    _factory.authoritative_source = "CHAINSTACK"  # type: ignore[attr-defined]
    return _factory


__all__ = (
    "PROVIDER_MODE_FREE_TIER",
    "PROVIDER_MODE_PAID_PRIMARY",
    "PROVIDER_MODE_PAID_WITH_FALLBACK",
    "PROVIDER_MODES",
    "DISCOVERY_PROVENANCE_LIVE",
    "DISCOVERY_PROVENANCE_HELIUS",
    "LIVE_DISCOVERY_PROVENANCES",
    "STREAM_STATUS_AUTH_FAILED",
    "ProviderCandidateDedupe",
    "PROVIDER_DEDUPE_APPLIED_FIELD",
    "apply_provider_dedupe_once",
    "mark_provider_dedupe_applied",
    "provider_dedupe_already_applied",
    "SingleGrpcPumpSwapDiscovery",
    "SourceFactoryContractError",
    "CURSOR_AWARE_FACTORY_KWARGS",
    "MigrationEventTime",
    "resolve_migration_event_time",
    "MIGRATION_TIME_SOURCE_PROVIDER_EVENT_TIME",
    "MIGRATION_TIME_SOURCE_LOCAL_RECEIPT_LIVE",
    "MIGRATION_TIME_SOURCE_UNKNOWN",
    "MIGRATION_TIME_SOURCES",
    "event_to_candidate",
    "normalize_provider_mode",
    "build_live_source_factory",
    "adapt_zero_argument_factory_TEST_ONLY",
)

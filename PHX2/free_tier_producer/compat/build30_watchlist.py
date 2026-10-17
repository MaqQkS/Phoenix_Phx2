"""PHX2 watchlist state machine with restart-safe activation persistence.

State machine::

    MIGRATION_DETECTED -> PENDING_BASELINE -> PENDING_1_20X
        -> ACTIVATED -> { ACTIVATED_WAITING_FOR_FRESH_MARKET | ACTIVE_DIP_WATCH }
        -> ACTIVE_DIP_WATCH
        -> { SENT_OK_COMMITTED | DELIVERY_UNKNOWN | DEDUPE_SUPPRESSED | EXPIRED }

``ACTIVATED`` is an emitted transition. The durable steady state is
``ACTIVE_DIP_WATCH``. Crossing the threshold never composes or sends in the
same observation; the existing dip pipeline becomes eligible on a later tick.
For a later dip tick, ``provider_timestamp_utc`` is authoritative and must be
strictly later than both the source activation event and PHX2's acceptance
timestamp. Missing/stale current market data moves a proven candidate into the
schedulable activated-waiting state without clearing its durable proof.

Delivery transaction (PHX2-E2E-001): only a CONFIRMED committed delivery
terminalizes the watch (``SENT_OK_COMMITTED``). An explicit transport failure
keeps the entry ACTIVE with bounded retry metadata
(``delivery_next_retry_at_utc`` / ``delivery_retry_count``); an ambiguous
outcome parks it in the observable, non-retryable ``DELIVERY_UNKNOWN`` state.
The legacy terminal ``SEND_ATTEMPTED`` token survives only for old checkpoints
and the Build 30 forward-watch lineage.

Active-watch capacity (PHX2-E2E-002): the configured ``max_size`` bounds the
number of *concurrently active* candidates, never lifetime history. A terminal
transition archives the candidate into the append-only terminal-history
artifact (``watch_terminal_history.py``) and releases its active slot; a full
watchlist rejects a new mint with the explicit observable reason
``ACTIVE_WATCH_CAPACITY_REACHED``. ``DELIVERY_UNKNOWN`` remains an active
(slot-holding, operator-visible, non-scheduled) unresolved state exactly as
introduced by the delivery transaction fix.

The watch-state JSONL is separate from the durable ping-dedupe ledger. This
module performs no reserve, transport, provider, or network action.
"""

from __future__ import annotations

import json
import hashlib
import os
import re
from dataclasses import asdict, dataclass, field, fields as dataclass_fields
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple
from PHX2.free_tier_producer.migration_admission import candidate_migration_is_admitted
from PHX2.free_tier_producer.admission_inbox import (
    DurableAdmissionInbox, validate_admission_receipt,
)

from PHX2.free_tier_producer.ath_state import (
    ATH_EVIDENCE_SCHEMA_VERSION,
    ATH_OBSERVATION_SEAL_SCHEMA_VERSION,
    SOURCE_PAID_CURRENT,
    SOURCE_PAID_OHLCV,
    SOURCE_PAID_V3_PAIR,
    SOURCE_PUMPSWAP_EVENT,
    STATUS_CONFIRMED,
    STATUS_PROVISIONAL,
    ath_evidence_digest_is_valid,
    ath_observation_seal_digest_is_valid,
    build_ath_observation_seal_digest,
)

try:
    from PHX2.free_tier_producer.compat.watch_terminal_history import (
        ARCHIVE_OUTCOME_ARCHIVED,
        TerminalHistoryArchive,
        TerminalHistoryCorruptionError,
        build_terminal_history_record,
    )
except ImportError:  # compat dir imported directly on sys.path
    from watch_terminal_history import (  # type: ignore[no-redef]
        ARCHIVE_OUTCOME_ARCHIVED,
        TerminalHistoryArchive,
        TerminalHistoryCorruptionError,
        build_terminal_history_record,
    )

try:
    from PHX2.free_tier_producer.paid_market_readiness import (
        MARKET_RECOVERY_BACKOFF as READINESS_RECOVERY_BACKOFF,
        LEGACY_TERMINAL_MIGRATED as READINESS_LEGACY_MIGRATED,
        LEGACY_TERMINAL_UNCLASSIFIED as READINESS_LEGACY_UNCLASSIFIED,
        classify_legacy_market_state,
    )
except ImportError:  # compat dir imported directly on sys.path
    from paid_market_readiness import (  # type: ignore[no-redef]
        MARKET_RECOVERY_BACKOFF as READINESS_RECOVERY_BACKOFF,
        LEGACY_TERMINAL_MIGRATED as READINESS_LEGACY_MIGRATED,
        LEGACY_TERMINAL_UNCLASSIFIED as READINESS_LEGACY_UNCLASSIFIED,
        classify_legacy_market_state,
    )

try:
    from PHX2.free_tier_producer import checkpoint_envelope as _cpe
except ImportError:  # compat dir imported directly on sys.path
    import checkpoint_envelope as _cpe  # type: ignore[no-redef]

# Legacy market-terminal migration probe delay (mirrors the readiness tracker
# default ``recovery_initial_delay_seconds``): a candidate whose persisted
# market-readiness state is a migrated legacy terminal must not be probed the
# instant it restores.
_LEGACY_RECOVERY_PROBE_DELAY_SECONDS = 60.0


MIGRATION_ACTIVATION_MULTIPLIER = Decimal("1.20")
BACKFILL_ACTIVATION_MULTIPLIER = Decimal("1.39")
# Centralized closed-set provenance contract: LIVE_YELLOWSTONE and LIVE_HELIUS
# are equal-authority live provenances; DEXSCREENER_RESTART_BACKFILL is the
# only provenance whose candidates may pre-date the live epoch boundary.
from PHX2.models.discovery_provenance import (  # noqa: E402
    DISCOVERY_PROVENANCES,
    LIVE_DISCOVERY_PROVENANCES,
    DISCOVERY_PROVENANCE_DEX_BACKFILL as DISCOVERY_PROVENANCE_DEX,
    DISCOVERY_PROVENANCE_LIVE_HELIUS as DISCOVERY_PROVENANCE_HELIUS,
    DISCOVERY_PROVENANCE_LIVE_YELLOWSTONE as DISCOVERY_PROVENANCE_LIVE,
)
from PHX2.models.market_data_source import (  # noqa: E402
    normalize_market_data_source,
)
from PHX2.free_tier_producer.phx1_parity_policy import (  # noqa: E402
    expected_activation_multiplier as _policy_activation_multiplier,
    resolve_policy as _resolve_alert_policy,
)
BACKFILL_MIGRATION_EVIDENCE_CLASS = "DEXSCREENER_INFERRED_MIGRATION"

WATCH_PENDING_BASELINE = "PENDING_BASELINE"
WATCH_PENDING_1_20X = "PENDING_1_20X"
WATCH_ACTIVATED = "ACTIVATED"
WATCH_ACTIVATED_WAITING = "ACTIVATED_WAITING_FOR_FRESH_MARKET"
WATCH_ACTIVE_DIP = "ACTIVE_DIP_WATCH"
# Legacy pre-delivery-transaction terminal token. The corrected engine never
# emits it for a FAILED delivery; it survives only for old checkpoints and the
# legacy Build 30 forward-watch lineage.
WATCH_SEND_ATTEMPTED = "SEND_ATTEMPTED"
# Terminal CONFIRMED delivery (transport_ok=True + durable receipt + exactly
# one successful-send ledger row committed).
WATCH_SENT_OK_COMMITTED = "SENT_OK_COMMITTED"
# Ambiguous delivery outcome after dispatch: observable, NOT success, NOT
# silently retryable. Explicit reconciliation policy resolves it.
WATCH_DELIVERY_UNKNOWN = "DELIVERY_UNKNOWN"
WATCH_DEDUPE_SUPPRESSED = "DEDUPE_SUPPRESSED"
WATCH_EXPIRED = "EXPIRED"
WATCH_REJECTED = "REJECTED"
WATCH_EVICTED = "EVICTED"
WATCH_DROPPED_NON_PUMP = "DROPPED_NON_PUMP"

BASELINE_PENDING = "PENDING"
BASELINE_CAPTURED = "CAPTURED"
BASELINE_UNPROVEN_LEGACY = "UNPROVEN_LEGACY"
BASELINE_SOURCE_GRPC_EVENT = "GRPC_EVENT"
BASELINE_SOURCE_DEX_BACKFILL = "DEXSCREENER_SOL_USD_X_410_INFERRED"
# Redaction-safe persisted token for the configured Birdeye paid-primary
# provider. Provider brand names are not written into producer artifacts
# because the inherited secret scanner treats them as danger needles.
BASELINE_SOURCE_BIRDEYE = "PAID_MARKET_PRIMARY_FALLBACK"

ACTIVATION_SOURCE_PAID_SPOT = "PAID_MARKET_PRIMARY"
ACTIVATION_EVIDENCE_SPOT_VERSION = "phx2_activation_spot_evidence_v1"
ACTIVATION_EVIDENCE_SCHEMA_VERSION = "phx2_activation_evidence_v2"
MIGRATION_BASELINE_DIGEST_SCHEMA_VERSION = "phx2_migration_baseline_digest_v1"
ACTIVATION_KIND_SPOT_CURRENT = "SPOT_CURRENT"
ACTIVATION_KIND_CONFIRMED_OHLCV_HIGH = "CONFIRMED_OHLCV_HIGH"
ACTIVATION_KIND_TRUSTED_RESERVE_EVENT = "TRUSTED_RESERVE_EVENT"
# PHX2-E2E-005: activation proof derived by the explicit legacy checkpoint
# migration from authenticated pre-proof-schema evidence. Never produced by a
# live crossing; validated by its own digest chain; requires a genuinely later
# fresh market tick before any tier evaluation.
ACTIVATION_KIND_LEGACY_MIGRATION = "LEGACY_AUTHENTICATED_ACTIVATION_MIGRATION"
ACTIVATION_LEGACY_MIGRATION_EVIDENCE_VERSION = (
    "phx2_activation_legacy_migration_evidence_v1")
ACTIVATION_LEGACY_MIGRATION_PROOF_VERSION = (
    "phx2_activation_legacy_migration_proof_v1")
ACTIVATION_LEGACY_MIGRATION_CROSSING_VERSION = (
    "phx2_legacy_migration_crossing_v1")
ACTIVATION_EVIDENCE_KINDS = (
    ACTIVATION_KIND_SPOT_CURRENT,
    ACTIVATION_KIND_CONFIRMED_OHLCV_HIGH,
    ACTIVATION_KIND_TRUSTED_RESERVE_EVENT,
)

# ---- authenticated watch checkpoint schema (PHX2-E2E-005) ------------------
WATCH_CHECKPOINT_SCHEMA_VERSION = "phx2_watch_checkpoint_v2"
# The pre-envelope on-disk shape: one JSON object per line, no envelope, no
# digests, written by every build up to and including fde2628.
WATCH_LEGACY_SCHEMA_VERSION = "phx2_watch_jsonl_legacy_v1"
QUARANTINED_CANDIDATE_RECORD_KIND = "PHX2_QUARANTINED_CANDIDATE"
ACTIVATION_EVIDENCE_SOURCES = (
    ACTIVATION_SOURCE_PAID_SPOT,
    SOURCE_PAID_OHLCV,
    SOURCE_PAID_V3_PAIR,
    SOURCE_PAID_CURRENT,
    SOURCE_PUMPSWAP_EVENT,
)

ACTIVATION_COUNTER_FIELDS = (
    "activation_proven_by_spot",
    "activation_proven_by_ohlcv_high",
    "activation_proven_by_reserve_event",
    "activation_high_rejected_pre_baseline",
    "activation_high_rejected_stale",
    "activation_high_rejected_unconfirmed",
    "activation_high_rejected_source",
    "activation_crossing_tick_blocks",
    "activation_proven_by_current_price",
    "activation_proven_without_current_spot",
    "activation_waiting_for_fresh_market",
    "activation_equal_evidence_reobserved",
    "activation_observation_seal_refreshed",
    "activation_source_event_too_old",
    "activation_evidence_stale_ingest",
    "activation_wrong_mint_rejected",
    "activation_pre_baseline_rejected",
    "activation_unconfirmed_rejected",
    "activation_disallowed_source_rejected",
)

# Backward import compatibility only. New entries never use these states.
WATCH_SEEDED = "SEEDED"
WATCH_WATCHING = "WATCHING"

_TRACKED = (
    WATCH_PENDING_BASELINE,
    WATCH_PENDING_1_20X,
    WATCH_ACTIVATED,
    WATCH_ACTIVATED_WAITING,
    WATCH_ACTIVE_DIP,
)

# --------------------------------------------------------------------------
# Centralized watch-state classification (PHX2-E2E-002). Every production
# consumer (capacity, scheduling, checkpoint restore, summaries) must use
# these helpers — never a private state list.
#
# SCHEDULABLE: receives market polling / activation / tier / gate / compose /
# delivery-retry work on watch ticks. DELIVERY_FAILED_RETRYABLE and an
# unexpired delivery attempt lease live on a schedulable entry as delivery
# metadata, so they are active by construction.
#
# ACTIVE (capacity-holding): schedulable states PLUS ``DELIVERY_UNKNOWN`` —
# an unresolved delivery outcome is production work awaiting explicit
# operator reconciliation (fa6022d semantics preserved: observable, never
# silently retried, never discarded), so it keeps its active slot while
# staying out of the market scheduler.
#
# TERMINAL: the production scheduler will never legitimately resume these.
# They are archived to terminal history and never consume active capacity.
#
# A status in NEITHER tuple (schema drift / tampering) is ambiguous: it fails
# closed as non-terminal — kept in the active map and checkpoint, counted
# against capacity, visible in ``by_status`` — and is never scheduled and
# never silently erased.
# --------------------------------------------------------------------------
SCHEDULABLE_WATCH_STATES = _TRACKED
ACTIVE_WATCH_STATES = _TRACKED + (
    WATCH_DELIVERY_UNKNOWN,
    # Legacy tokens normalize to PENDING_BASELINE at entry construction.
    WATCH_SEEDED,
    WATCH_WATCHING,
)
TERMINAL_WATCH_STATES = (
    WATCH_EXPIRED,
    WATCH_SENT_OK_COMMITTED,
    WATCH_SEND_ATTEMPTED,
    WATCH_DEDUPE_SUPPRESSED,
    WATCH_DROPPED_NON_PUMP,
    WATCH_REJECTED,
    WATCH_EVICTED,
)

# Closed-set seed outcomes (``Watchlist.seed_with_outcome``).
SEED_OUTCOME_ADMITTED = "ADMITTED"
SEED_OUTCOME_EXISTING = "EXISTING"
SEED_OUTCOME_TERMINAL_DUPLICATE = "TERMINAL_HISTORY_DUPLICATE"
SEED_OUTCOME_DROPPED_NON_PUMP = "DROPPED_NON_PUMP"
SEED_OUTCOME_CAPACITY = "ACTIVE_WATCH_CAPACITY_REACHED"
SEED_OUTCOME_INVALID = "INVALID_CANDIDATE"
SEED_OUTCOME_PRE_BOUNDARY = "PRE_BOUNDARY_NOT_ELIGIBLE"
SEED_OUTCOME_DIAGNOSTIC_ONLY = "DIAGNOSTIC_ONLY"
# PHX2-E2E-005: the authoritative checkpoint is quarantined (or the specific
# mint is a quarantined candidate) — no admission, no silent fresh start.
SEED_OUTCOME_CHECKPOINT_QUARANTINED = "CHECKPOINT_QUARANTINED"

CAPACITY_REJECTION_REASON = "ACTIVE_WATCH_CAPACITY_REACHED"


def is_schedulable_watch_state(status: object) -> bool:
    """True when the production watch loop may still work this candidate."""

    return status in SCHEDULABLE_WATCH_STATES


def is_active_watch_state(status: object) -> bool:
    """True when the candidate still requires production action and therefore
    holds one active-watch capacity slot."""

    return status in ACTIVE_WATCH_STATES


def is_terminal_watch_state(status: object) -> bool:
    """True when the production scheduler will never legitimately resume the
    candidate; terminal candidates are archived and release their slot."""

    return status in TERMINAL_WATCH_STATES


_STRICT_DECIMAL_RE = re.compile(r"\A[0-9]+(?:\.[0-9]+)?\Z")


def _decimal(value: object, *, positive: bool = True) -> Optional[Decimal]:
    """Parse an exact finite Decimal, rejecting every binary float."""

    if isinstance(value, bool) or isinstance(value, float):
        return None
    if isinstance(value, Decimal):
        out = value
    elif isinstance(value, int):
        out = Decimal(value)
    elif isinstance(value, str) and _STRICT_DECIMAL_RE.fullmatch(value.strip()):
        try:
            out = Decimal(value.strip())
        except InvalidOperation:
            return None
    else:
        return None
    if not out.is_finite() or (positive and out <= 0):
        return None
    return out


def _decimal_text(value: Decimal) -> str:
    return format(value, "f")


def _sha256_payload(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        dict(payload), sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def build_activation_spot_evidence_digest(
    *, mint: str, market_cap: Decimal, event_at_utc: str, source: str
) -> str:
    return _sha256_payload({
        "schema_version": ACTIVATION_EVIDENCE_SPOT_VERSION,
        "token_mint": mint,
        "market_cap_usd": _decimal_text(market_cap),
        "event_at_utc": event_at_utc,
        "source": source,
        "kind": ACTIVATION_KIND_SPOT_CURRENT,
    })


def build_migration_baseline_digest(
    *, token_mint: str, candidate_id: str, market_cap_usd: object,
    observed_at_utc: str, source: str, price: object, supply: object,
) -> str:
    market_cap = _decimal(market_cap_usd)
    price_value = _decimal(price)
    supply_value = _decimal(supply) if supply is not None else None
    fields = (token_mint, candidate_id, observed_at_utc, source)
    if (market_cap is None or price_value is None
            or (supply is not None and supply_value is None)
            or any(not isinstance(value, str) or not value for value in fields)):
        raise ValueError("MIGRATION_BASELINE_DIGEST_FIELDS_INVALID")
    return _sha256_payload({
        "schema_version": MIGRATION_BASELINE_DIGEST_SCHEMA_VERSION,
        "token_mint": token_mint,
        "candidate_id": candidate_id,
        "market_cap_usd": _decimal_text(market_cap),
        "observed_at_utc": observed_at_utc,
        "source": source,
        "price_usd": _decimal_text(price_value),
        "supply_at_observation": (
            _decimal_text(supply_value) if supply_value is not None else None),
    })


def build_legacy_activation_source_evidence_digest(
    *, token_mint: str, candidate_id: str, market_cap_usd: object,
    event_at_utc: str, source: str,
) -> str:
    """Digest of the authenticated legacy activation observation itself."""

    market_cap = _decimal(market_cap_usd)
    fields = (token_mint, candidate_id, event_at_utc, source)
    if market_cap is None or any(
            not isinstance(value, str) or not value for value in fields):
        raise ValueError("LEGACY_ACTIVATION_EVIDENCE_FIELDS_INVALID")
    return _sha256_payload({
        "schema_version": ACTIVATION_LEGACY_MIGRATION_EVIDENCE_VERSION,
        "token_mint": token_mint,
        "candidate_id": candidate_id,
        "market_cap_usd": _decimal_text(market_cap),
        "event_at_utc": event_at_utc,
        "source": source,
        "kind": ACTIVATION_KIND_LEGACY_MIGRATION,
    })


def build_legacy_migration_crossing_digest(
    *, token_mint: str, candidate_id: str, legacy_record_digest: str,
    activated_at_utc: str, market_cap_usd: object,
) -> str:
    """Non-replayable crossing marker for a migration-derived activation.

    Domain-separated from the live ``phx2_activation_crossing_tick_v1``
    digest, so no genuine later market tick can ever collide with it and the
    migration event itself can never satisfy a crossing-tick comparison.
    """

    market_cap = _decimal(market_cap_usd)
    fields = (token_mint, candidate_id, legacy_record_digest, activated_at_utc)
    if (market_cap is None
            or any(not isinstance(value, str) or not value for value in fields)
            or len(legacy_record_digest) != 64):
        raise ValueError("LEGACY_MIGRATION_CROSSING_FIELDS_INVALID")
    return _sha256_payload({
        "schema_version": ACTIVATION_LEGACY_MIGRATION_CROSSING_VERSION,
        "token_mint": token_mint,
        "candidate_id": candidate_id,
        "legacy_record_digest": legacy_record_digest,
        "activated_at_utc": activated_at_utc,
        "market_cap_usd": _decimal_text(market_cap),
    })


def build_legacy_activation_migration_proof_digest(
    *, token_mint: str, candidate_id: str,
    legacy_checkpoint_digest: str, legacy_record_digest: str,
    migration_baseline_digest: str,
    migration_market_cap_usd: object,
    migration_market_cap_observed_at_utc: str,
    activation_target_market_cap_usd: object,
    activation_evidence_market_cap_usd: object,
    activated_at_utc: str, activation_evidence_source: str,
    activation_migrated_from_schema: str,
    activation_migration_performed_at_utc: str,
    activation_crossing_tick_digest: str,
) -> str:
    """Seal a migration-derived activation proof over every bound field."""

    baseline = _decimal(migration_market_cap_usd)
    target = _decimal(activation_target_market_cap_usd)
    crossing = _decimal(activation_evidence_market_cap_usd)
    text_fields = (
        token_mint, candidate_id, legacy_checkpoint_digest,
        legacy_record_digest, migration_baseline_digest,
        migration_market_cap_observed_at_utc, activated_at_utc,
        activation_evidence_source, activation_migrated_from_schema,
        activation_migration_performed_at_utc, activation_crossing_tick_digest,
    )
    if (baseline is None or target is None or crossing is None
            or any(not isinstance(value, str) or not value
                   for value in text_fields)
            or len(legacy_checkpoint_digest) != 64
            or len(legacy_record_digest) != 64
            or len(migration_baseline_digest) != 64
            or len(activation_crossing_tick_digest) != 64):
        raise ValueError("LEGACY_ACTIVATION_MIGRATION_FIELDS_INVALID")
    return _sha256_payload({
        "schema_version": ACTIVATION_LEGACY_MIGRATION_PROOF_VERSION,
        "token_mint": token_mint,
        "candidate_id": candidate_id,
        "legacy_checkpoint_digest": legacy_checkpoint_digest,
        "legacy_record_digest": legacy_record_digest,
        "migration_baseline_digest": migration_baseline_digest,
        "migration_market_cap_usd": _decimal_text(baseline),
        "migration_market_cap_observed_at_utc": (
            migration_market_cap_observed_at_utc),
        "activation_multiplier": _decimal_text(MIGRATION_ACTIVATION_MULTIPLIER),
        "activation_target_market_cap_usd": _decimal_text(target),
        "activation_evidence_market_cap_usd": _decimal_text(crossing),
        "activated_at_utc": activated_at_utc,
        "activation_evidence_source": activation_evidence_source,
        "activation_evidence_kind": ACTIVATION_KIND_LEGACY_MIGRATION,
        "activation_migrated_from_schema": activation_migrated_from_schema,
        "activation_migration_performed_at_utc": (
            activation_migration_performed_at_utc),
        "activation_crossing_tick_digest": activation_crossing_tick_digest,
    })


def build_activation_evidence_digest(
    *, token_mint: str, candidate_id: str,
    migration_baseline_digest: str,
    migration_market_cap_usd: object,
    migration_market_cap_observed_at_utc: str,
    activation_target_market_cap_usd: object,
    activation_evidence_market_cap_usd: object,
    activation_evidence_event_at_utc: str,
    activation_evidence_ingested_at_utc: str,
    activated_at_utc: str, activation_evidence_source: str,
    activation_evidence_kind: str, activation_source_evidence_digest: str,
    activation_source_evidence_version: str,
    activation_observation_seal_digest: str,
    activation_observation_seal_version: str,
    activation_crossing_tick_digest: str,
    activation_multiplier: object = MIGRATION_ACTIVATION_MULTIPLIER,
) -> str:
    """Seal the complete persisted activation proof with exact decimals."""

    multiplier = _decimal(activation_multiplier)
    baseline = _decimal(migration_market_cap_usd)
    target = _decimal(activation_target_market_cap_usd)
    crossing = _decimal(activation_evidence_market_cap_usd)
    text_fields = (
        token_mint, candidate_id, migration_baseline_digest,
        migration_market_cap_observed_at_utc,
        activation_evidence_event_at_utc, activation_evidence_ingested_at_utc,
        activated_at_utc, activation_evidence_source, activation_evidence_kind,
        activation_source_evidence_digest, activation_source_evidence_version,
        activation_observation_seal_digest, activation_observation_seal_version,
        activation_crossing_tick_digest,
    )
    if (multiplier is None or multiplier <= 0
            or baseline is None or target is None or crossing is None
            or any(not isinstance(value, str) or not value for value in text_fields)
            or len(activation_source_evidence_digest) != 64
            or len(migration_baseline_digest) != 64
            or len(activation_observation_seal_digest) != 64
            or len(activation_crossing_tick_digest) != 64):
        raise ValueError("ACTIVATION_EVIDENCE_FIELDS_INVALID")
    return _sha256_payload({
        "schema_version": ACTIVATION_EVIDENCE_SCHEMA_VERSION,
        "token_mint": token_mint,
        "candidate_id": candidate_id,
        "migration_baseline_digest": migration_baseline_digest,
        "migration_market_cap_usd": _decimal_text(baseline),
        "migration_market_cap_observed_at_utc": migration_market_cap_observed_at_utc,
        "activation_multiplier": _decimal_text(multiplier),
        "activation_target_market_cap_usd": _decimal_text(target),
        "activation_evidence_market_cap_usd": _decimal_text(crossing),
        "activation_evidence_event_at_utc": activation_evidence_event_at_utc,
        "activation_evidence_ingested_at_utc": activation_evidence_ingested_at_utc,
        "activated_at_utc": activated_at_utc,
        "activation_evidence_source": activation_evidence_source,
        "activation_evidence_kind": activation_evidence_kind,
        "activation_source_evidence_digest": activation_source_evidence_digest,
        "activation_source_evidence_version": activation_source_evidence_version,
        "activation_observation_seal_digest": activation_observation_seal_digest,
        "activation_observation_seal_version": activation_observation_seal_version,
        "activation_crossing_tick_digest": activation_crossing_tick_digest,
    })


def _activation_tick_digest(
    *, mint: str, current_market_cap: Optional[Decimal],
    current_price: Optional[Decimal], provider_timestamp_utc: str,
    observation_source: str, central_evidence_digest: object,
) -> str:
    return _sha256_payload({
        "schema_version": "phx2_activation_crossing_tick_v1",
        "token_mint": mint,
        "current_market_cap_usd": (
            _decimal_text(current_market_cap) if current_market_cap is not None else None),
        "current_price_usd": (
            _decimal_text(current_price) if current_price is not None else None),
        "provider_timestamp_utc": provider_timestamp_utc,
        "observation_source": observation_source,
        "central_evidence_digest": (
            central_evidence_digest
            if isinstance(central_evidence_digest, str) else None),
    })


def _utc(value: object) -> Optional[datetime]:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def _fresh_observation(
    *, observed_at_utc: object, now_utc: object, max_age_seconds: float
) -> bool:
    observed = _utc(observed_at_utc)
    now = _utc(now_utc)
    if observed is None or now is None:
        return False
    age = (now - observed).total_seconds()
    return -5.0 <= age <= max(0.0, float(max_age_seconds))


def _legacy_migration_proof_is_valid(proof: Mapping[str, Any]) -> bool:
    """Validate a migration-derived legacy activation proof.

    Every field is re-derived from the persisted evidence; a proof that does
    not bind to its exact legacy record/checkpoint digests, baseline digest,
    non-replayable crossing marker and migration identity fails closed.
    """

    if proof.get("migration_baseline_status") != BASELINE_CAPTURED:
        return False
    if proof.get("activation_multiplier") != _decimal_text(
            MIGRATION_ACTIVATION_MULTIPLIER):
        return False
    baseline = _decimal(proof.get("migration_market_cap_usd"))
    target = _decimal(proof.get("activation_target_market_cap_usd"))
    crossing = _decimal(proof.get("activation_evidence_market_cap_usd"))
    if baseline is None or target is None or crossing is None:
        return False
    if target != baseline * MIGRATION_ACTIVATION_MULTIPLIER or crossing < target:
        return False
    try:
        expected_baseline_digest = build_migration_baseline_digest(
            token_mint=proof.get("token_mint"),
            candidate_id=proof.get("candidate_id"),
            market_cap_usd=proof.get("migration_market_cap_usd"),
            observed_at_utc=proof.get("migration_market_cap_observed_at_utc"),
            source=proof.get("migration_market_cap_source"),
            price=proof.get("migration_market_cap_price"),
            supply=proof.get("migration_supply_at_observation"),
        )
    except (TypeError, ValueError):
        return False
    if (proof.get("migration_baseline_digest_version")
            != MIGRATION_BASELINE_DIGEST_SCHEMA_VERSION
            or proof.get("migration_baseline_digest")
            != expected_baseline_digest):
        return False
    activated = _utc(proof.get("activated_at_utc"))
    event_at = _utc(proof.get("activation_evidence_event_at_utc"))
    ingested_at = _utc(proof.get("activation_evidence_ingested_at_utc"))
    baseline_at = _utc(proof.get("migration_market_cap_observed_at_utc"))
    performed_at = _utc(proof.get("activation_migration_performed_at_utc"))
    if (activated is None or event_at is None or ingested_at is None
            or baseline_at is None or performed_at is None
            or event_at <= baseline_at or activated < ingested_at):
        return False
    source = proof.get("activation_evidence_source")
    if source not in ACTIVATION_EVIDENCE_SOURCES:
        return False
    if proof.get("activation_migrated_from_schema") != WATCH_LEGACY_SCHEMA_VERSION:
        return False
    legacy_record_digest = proof.get("activation_legacy_record_digest")
    legacy_checkpoint_digest = proof.get("activation_legacy_checkpoint_digest")
    if not isinstance(legacy_record_digest, str) \
            or len(legacy_record_digest) != 64 \
            or not isinstance(legacy_checkpoint_digest, str) \
            or len(legacy_checkpoint_digest) != 64:
        return False
    if proof.get("activation_evidence_version") \
            != ACTIVATION_LEGACY_MIGRATION_EVIDENCE_VERSION:
        return False
    source_digest = proof.get("activation_evidence_digest")
    if proof.get("activation_source_evidence_digest") != source_digest:
        return False
    try:
        expected_source_digest = build_legacy_activation_source_evidence_digest(
            token_mint=proof.get("token_mint"),
            candidate_id=proof.get("candidate_id"),
            market_cap_usd=proof.get("activation_evidence_market_cap_usd"),
            event_at_utc=proof.get("activation_evidence_event_at_utc"),
            source=source,
        )
        expected_crossing_digest = build_legacy_migration_crossing_digest(
            token_mint=proof.get("token_mint"),
            candidate_id=proof.get("candidate_id"),
            legacy_record_digest=legacy_record_digest,
            activated_at_utc=proof.get("activated_at_utc"),
            market_cap_usd=proof.get("activation_evidence_market_cap_usd"),
        )
        expected_proof_digest = build_legacy_activation_migration_proof_digest(
            token_mint=proof.get("token_mint"),
            candidate_id=proof.get("candidate_id"),
            legacy_checkpoint_digest=legacy_checkpoint_digest,
            legacy_record_digest=legacy_record_digest,
            migration_baseline_digest=proof.get("migration_baseline_digest"),
            migration_market_cap_usd=proof.get("migration_market_cap_usd"),
            migration_market_cap_observed_at_utc=proof.get(
                "migration_market_cap_observed_at_utc"),
            activation_target_market_cap_usd=proof.get(
                "activation_target_market_cap_usd"),
            activation_evidence_market_cap_usd=proof.get(
                "activation_evidence_market_cap_usd"),
            activated_at_utc=proof.get("activated_at_utc"),
            activation_evidence_source=source,
            activation_migrated_from_schema=proof.get(
                "activation_migrated_from_schema"),
            activation_migration_performed_at_utc=proof.get(
                "activation_migration_performed_at_utc"),
            activation_crossing_tick_digest=proof.get(
                "activation_crossing_tick_digest"),
        )
    except (TypeError, ValueError):
        return False
    if source_digest != expected_source_digest:
        return False
    if proof.get("activation_crossing_tick_digest") != expected_crossing_digest:
        return False
    seal_digest = proof.get("activation_observation_seal_digest")
    if (proof.get("activation_observation_seal_version")
            != ATH_OBSERVATION_SEAL_SCHEMA_VERSION
            or seal_digest != build_ath_observation_seal_digest(
                proof.get("token_mint"), {
                    "ath_evidence_digest": source_digest,
                    "ath_ingested_at_utc": proof.get(
                        "activation_evidence_ingested_at_utc"),
                    "ath_observation_seal_validated": True,
                })):
        return False
    if (proof.get("activation_proof_version")
            != ACTIVATION_LEGACY_MIGRATION_PROOF_VERSION
            or proof.get("activation_proof_digest") != expected_proof_digest):
        return False
    return bool(
        proof.get("activation_proven")
        and proof.get("activation_latched")
        and proof.get("activation_crossing_tick_blocked")
        and proof.get("legacy_activation_unproven") is not True
    )


def _expected_activation_multiplier(value: object) -> Optional[Decimal]:
    """Multiplier the durable proof's ``activation_multiplier`` FIELD carries.

    This is provenance-based and deliberately policy-INDEPENDENT.  For a
    DEX-backfill candidate the field is part of the sealed restart-backfill
    evidence contract (``validate_backfill_candidate_evidence`` checks it and
    the evidence digest is computed over it), so rewriting it would invalidate
    the candidate's migration evidence rather than relax anything.  The
    threshold a candidate is actually HELD to is a separate question --
    see :func:`_activation_threshold_multiplier`.
    """

    provenance = (
        value.get("discovery_provenance")
        if isinstance(value, Mapping)
        else getattr(value, "discovery_provenance", None)
    )
    if provenance == DISCOVERY_PROVENANCE_DEX:
        return BACKFILL_ACTIVATION_MULTIPLIER
    if provenance is None or provenance in LIVE_DISCOVERY_PROVENANCES:
        return MIGRATION_ACTIVATION_MULTIPLIER
    return None


def _activation_threshold_multiplier(
    value: object, *, policy: object = None
) -> Optional[Decimal]:
    """Multiplier used to compute the activation TARGET market cap.

    Under PHX1_PARITY a DEX-backfill candidate is held to the SAME 1.20x
    threshold as a live candidate: backfill provenance must not impose an extra
    activation penalty.  Its sealed evidence field still reads 1.39 and its
    provenance is never rewritten as live -- only the threshold changes.
    """

    provenance = (
        value.get("discovery_provenance")
        if isinstance(value, Mapping)
        else getattr(value, "discovery_provenance", None)
    )
    if provenance == DISCOVERY_PROVENANCE_DEX:
        return _policy_activation_multiplier(
            discovery_provenance_is_backfill=True,
            policy=_resolve_alert_policy(policy),
        )
    if provenance is None or provenance in LIVE_DISCOVERY_PROVENANCES:
        return MIGRATION_ACTIVATION_MULTIPLIER
    return None


def _backfill_evidence_is_valid(value: Mapping[str, Any]) -> bool:
    if value.get("discovery_provenance") != DISCOVERY_PROVENANCE_DEX:
        return True
    try:
        from PHX2.free_tier_producer.dexscreener_restart_backfill import (
            validate_backfill_candidate_evidence,
        )
        valid, _ = validate_backfill_candidate_evidence(value)
        return bool(valid)
    except Exception:
        return False

def _activation_proof_is_valid(
    value: object, *, actionable_only: bool, policy: object = None
) -> bool:
    """Validate the durable proof; optionally require an actionable state."""

    policy = _resolve_alert_policy(policy)
    if isinstance(value, WatchEntry):
        proof = value.activation_snapshot()
    elif isinstance(value, dict):
        proof = value
    else:
        return False
    state = proof.get("activation_state")
    if state not in (WATCH_ACTIVATED_WAITING, WATCH_ACTIVE_DIP):
        return False
    if actionable_only and state != WATCH_ACTIVE_DIP:
        return False
    if proof.get("activation_evidence_kind") == ACTIVATION_KIND_LEGACY_MIGRATION:
        return _legacy_migration_proof_is_valid(proof)
    if proof.get("migration_baseline_status") != BASELINE_CAPTURED:
        return False
    multiplier = _expected_activation_multiplier(proof)
    if multiplier is None or proof.get("activation_multiplier") != (
            _decimal_text(multiplier)):
        return False
    if not _backfill_evidence_is_valid(proof):
        return False
    threshold = _activation_threshold_multiplier(proof, policy=policy)
    if threshold is None:
        return False
    baseline = _decimal(proof.get("migration_market_cap_usd"))
    target = _decimal(proof.get("activation_target_market_cap_usd"))
    crossing = _decimal(proof.get("activation_evidence_market_cap_usd"))
    if baseline is None or target is None or crossing is None:
        return False
    if target != baseline * threshold or crossing < target:
        return False
    baseline_digest = proof.get("migration_baseline_digest")
    baseline_version = proof.get("migration_baseline_digest_version")
    try:
        expected_baseline_digest = build_migration_baseline_digest(
            token_mint=proof.get("token_mint"),
            candidate_id=proof.get("candidate_id"),
            market_cap_usd=proof.get("migration_market_cap_usd"),
            observed_at_utc=proof.get("migration_market_cap_observed_at_utc"),
            source=proof.get("migration_market_cap_source"),
            price=proof.get("migration_market_cap_price"),
            supply=proof.get("migration_supply_at_observation"),
        )
    except (TypeError, ValueError):
        return False
    if (baseline_version != MIGRATION_BASELINE_DIGEST_SCHEMA_VERSION
            or baseline_digest != expected_baseline_digest):
        return False
    activated = _utc(proof.get("activated_at_utc"))
    event_at = _utc(proof.get("activation_evidence_event_at_utc"))
    ingested_at = _utc(proof.get("activation_evidence_ingested_at_utc"))
    if activated is None or event_at is None or ingested_at is None:
        return False
    baseline_at = _utc(proof.get("migration_market_cap_observed_at_utc"))
    if baseline_at is None or event_at <= baseline_at or activated < ingested_at:
        return False
    source = proof.get("activation_evidence_source")
    kind = proof.get("activation_evidence_kind")
    if source not in ACTIVATION_EVIDENCE_SOURCES or kind not in ACTIVATION_EVIDENCE_KINDS:
        return False
    if kind == ACTIVATION_KIND_CONFIRMED_OHLCV_HIGH and source != SOURCE_PAID_OHLCV:
        return False
    if kind == ACTIVATION_KIND_TRUSTED_RESERVE_EVENT and source != SOURCE_PUMPSWAP_EVENT:
        return False
    if (kind == ACTIVATION_KIND_SPOT_CURRENT
            and source not in (ACTIVATION_SOURCE_PAID_SPOT, SOURCE_PAID_CURRENT)):
        return False
    source_digest = proof.get("activation_evidence_digest")
    if proof.get("activation_source_evidence_digest") != source_digest:
        return False
    source_version = proof.get("activation_evidence_version")
    seal_digest = proof.get("activation_observation_seal_digest")
    seal_version = proof.get("activation_observation_seal_version")
    digest = proof.get("activation_proof_digest")
    version = proof.get("activation_proof_version")
    crossing_tick_digest = proof.get("activation_crossing_tick_digest")
    if (not isinstance(digest, str) or len(digest) != 64
            or version != ACTIVATION_EVIDENCE_SCHEMA_VERSION
            or not isinstance(source_digest, str) or len(source_digest) != 64
            or not isinstance(source_version, str) or not source_version
            or seal_version != ATH_OBSERVATION_SEAL_SCHEMA_VERSION
            or not isinstance(seal_digest, str) or len(seal_digest) != 64
            or not isinstance(crossing_tick_digest, str)
            or len(crossing_tick_digest) != 64):
        return False
    if source == ACTIVATION_SOURCE_PAID_SPOT:
        if (source_version != ACTIVATION_EVIDENCE_SPOT_VERSION
                or source_digest != build_activation_spot_evidence_digest(
                    mint=str(proof.get("token_mint") or ""), market_cap=crossing,
                    event_at_utc=str(proof.get("activation_evidence_event_at_utc") or ""),
                    source=source)):
            return False
    elif source_version != ATH_EVIDENCE_SCHEMA_VERSION:
        return False
    expected_seal_digest = build_ath_observation_seal_digest(
        proof.get("token_mint"), {
            "ath_evidence_digest": source_digest,
            "ath_ingested_at_utc": proof.get(
                "activation_evidence_ingested_at_utc"),
            "ath_observation_seal_validated": True,
        })
    if seal_digest != expected_seal_digest:
        return False
    try:
        expected_digest = build_activation_evidence_digest(
            token_mint=proof.get("token_mint"),
            candidate_id=proof.get("candidate_id"),
            migration_baseline_digest=baseline_digest,
            migration_market_cap_usd=proof.get("migration_market_cap_usd"),
            migration_market_cap_observed_at_utc=proof.get(
                "migration_market_cap_observed_at_utc"),
            activation_target_market_cap_usd=proof.get(
                "activation_target_market_cap_usd"),
            activation_evidence_market_cap_usd=proof.get(
                "activation_evidence_market_cap_usd"),
            activation_evidence_event_at_utc=proof.get(
                "activation_evidence_event_at_utc"),
            activation_evidence_ingested_at_utc=proof.get(
                "activation_evidence_ingested_at_utc"),
            activated_at_utc=proof.get("activated_at_utc"),
            activation_evidence_source=source,
            activation_evidence_kind=kind,
            activation_source_evidence_digest=source_digest,
            activation_source_evidence_version=source_version,
            activation_observation_seal_digest=seal_digest,
            activation_observation_seal_version=seal_version,
            activation_crossing_tick_digest=crossing_tick_digest,
            activation_multiplier=multiplier,
        )
    except (TypeError, ValueError):
        return False
    if digest != expected_digest:
        return False
    return bool(
        proof.get("activation_proven")
        and proof.get("activation_observation_fresh")
        and proof.get("activation_latched")
        and proof.get("activation_crossing_tick_blocked")
    )


def activation_proof_is_durable(value: object, *, policy: object = None) -> bool:
    """Proof integrity for restart/waiting state, independent of market readiness."""

    return _activation_proof_is_valid(
        value, actionable_only=False, policy=policy)


def activation_proof_is_eligible(value: object, *, policy: object = None) -> bool:
    """Fail-closed proof used immediately before compose/reserve/send.

    Under PHX1_PARITY the ABSENCE of a proof is no longer a Telegram
    prerequisite -- that decision belongs to the compose path, which consults
    the policy matrix.  This predicate keeps its exact committed meaning: it
    answers "is there a valid, actionable, tamper-free activation proof", and a
    present-but-forged proof still fails under EVERY policy.
    """

    return _activation_proof_is_valid(
        value, actionable_only=True, policy=policy)


@dataclass
class WatchEntry:
    token_mint: str
    candidate_id: str
    migration_time_utc: Optional[str]
    source_ref: Optional[str]
    seeded_at_utc: str
    discovery_provenance: str = DISCOVERY_PROVENANCE_LIVE
    discovery_utc: Optional[str] = None
    live_epoch_id: Optional[str] = None
    migration_slot: Optional[int] = None
    migration_signature: Optional[str] = None
    migration_proof: Optional[Dict[str, Any]] = None
    admission_receipt: Optional[Dict[str, Any]] = None
    migration_evidence_class: Optional[str] = None
    pair_address: Optional[str] = None
    pool_dex_identity: Optional[str] = None
    ath_source: Optional[str] = None
    liquidity_source: Optional[str] = None
    current_data_source: Optional[str] = None
    backfill_lookback_seconds: Optional[int] = None
    backfill_sweep_id: Optional[str] = None
    source_confidence: Optional[str] = None
    dedupe_identity: Optional[str] = None
    corroborating_sources: List[str] = field(default_factory=list)
    corroborated_live_epoch_id: Optional[str] = None
    corroborated_migration_slot: Optional[int] = None
    backfill_evidence_digest: Optional[str] = None
    token_name: Optional[str] = None
    backfill_market_observed_at_utc: Optional[str] = None
    backfill_initial_price_usd: Optional[str] = None
    backfill_initial_market_cap_usd: Optional[str] = None
    backfill_initial_liquidity_usd: Optional[str] = None
    backfill_volume_m5_usd: Optional[str] = None
    backfill_volume_h1_usd: Optional[str] = None
    backfill_volume_h6_usd: Optional[str] = None
    backfill_volume_h24_usd: Optional[str] = None
    backfill_volume_fields_present: bool = False
    status: str = WATCH_PENDING_BASELINE
    recheck_count: int = 0
    last_reason: Optional[str] = None
    last_observed_at_utc: Optional[str] = None
    symbol_or_name: Optional[str] = None
    market_state: Optional[str] = None
    market_reason_code: Optional[str] = None
    next_market_refresh_at_utc: Optional[str] = None
    market_attempt_count: int = 0
    # PHX2-E2E-006 independent market-plane checkpoint metadata. These are
    # plain deterministic values only; workers/futures/queues are never
    # persisted. The generation is bumped when a scheduler owner is rebuilt so
    # an old in-process result cannot cross the new owner boundary.
    market_observation_generation: int = 0
    market_price_observed_at_utc: Optional[str] = None
    market_price_source: Optional[str] = None
    market_market_cap_observed_at_utc: Optional[str] = None
    market_market_cap_source: Optional[str] = None
    market_liquidity_observed_at_utc: Optional[str] = None
    market_liquidity_source: Optional[str] = None
    market_latest_tier: Optional[str] = None
    market_latest_drawdown_pct: Optional[str] = None
    # PHX2-E2E-004: set True when a restored legacy MARKET_UNAVAILABLE terminal
    # (transient grace/attempt exhaustion) was migrated to MARKET_RECOVERY_BACKOFF.
    market_legacy_terminal_migrated: bool = False
    migration_market_cap_usd: Optional[str] = None
    migration_market_cap_source: Optional[str] = None
    migration_market_cap_observed_at_utc: Optional[str] = None
    migration_market_cap_price: Optional[str] = None
    migration_supply_at_observation: Optional[str] = None
    migration_baseline_status: str = BASELINE_PENDING
    migration_baseline_digest: Optional[str] = None
    migration_baseline_digest_version: Optional[str] = None
    activation_multiplier: str = "1.20"
    activation_target_market_cap_usd: Optional[str] = None
    activated_at_utc: Optional[str] = None
    activation_observation_source: Optional[str] = None
    activation_current_market_cap_usd: Optional[str] = None
    activation_observation_fresh: bool = False
    activation_proven: bool = False
    activation_evidence_source: Optional[str] = None
    activation_evidence_market_cap_usd: Optional[str] = None
    activation_evidence_event_at_utc: Optional[str] = None
    activation_evidence_ingested_at_utc: Optional[str] = None
    activation_evidence_digest: Optional[str] = None
    activation_evidence_version: Optional[str] = None
    activation_source_evidence_digest: Optional[str] = None
    activation_observation_seal_digest: Optional[str] = None
    activation_observation_seal_version: Optional[str] = None
    activation_proof_digest: Optional[str] = None
    activation_proof_version: Optional[str] = None
    activation_evidence_kind: Optional[str] = None
    activation_crossing_tick_digest: Optional[str] = None
    activation_crossing_tick_blocked: bool = False
    activation_latched: bool = False
    last_activation_progress_market_cap_usd: Optional[str] = None
    legacy_activation_unproven: bool = False
    # PHX2-E2E-005 legacy activation migration provenance. Set ONLY by the
    # explicit checkpoint migration; bound into the migration proof digest.
    activation_migrated_from_schema: Optional[str] = None
    activation_migration_performed_at_utc: Optional[str] = None
    activation_legacy_record_digest: Optional[str] = None
    activation_legacy_checkpoint_digest: Optional[str] = None
    # Delivery transaction state (PHX2-E2E-001). Preserved across restarts;
    # defaults keep pre-transaction checkpoints loadable.
    delivery_state: Optional[str] = None
    delivery_attempt_count: int = 0
    delivery_retry_count: int = 0
    delivery_last_failure_reason: Optional[str] = None
    delivery_next_retry_at_utc: Optional[str] = None
    delivery_attempt_id: Optional[str] = None
    delivery_receipt_message_id: Optional[int] = None
    delivery_receipt_digest: Optional[str] = None
    delivery_ledger_key: Optional[str] = None
    # Restart-state audit (2026-07-31). A candidate restored from the
    # authenticated checkpoint is re-bound to the epoch the NEW process opened
    # instead of being closed as a prior-epoch live candidate. The original
    # epoch id is preserved here so the rebinding is explainable from artifacts
    # alone; nothing about the migration evidence, baseline, activation target,
    # progress or ATH is altered by the rebinding.
    restored_from_live_epoch_id: Optional[str] = None
    epoch_rebound_at_utc: Optional[str] = None

    def __post_init__(self) -> None:
        # Old SEEDED/WATCHING records have no proof of an immutable migration
        # baseline. Restore them ineligible and let the existing age policy
        # expire them instead of fabricating a later baseline.
        if self.status in (WATCH_SEEDED, WATCH_WATCHING):
            self.status = WATCH_PENDING_BASELINE
            self.migration_baseline_status = BASELINE_UNPROVEN_LEGACY
            self.legacy_activation_unproven = True
            self.activation_proven = False
            self.last_reason = "LEGACY_ACTIVATION_UNPROVEN"
        expected_multiplier = _expected_activation_multiplier(self)
        if (expected_multiplier is None
                or self.activation_multiplier != _decimal_text(expected_multiplier)):
            self.status = WATCH_PENDING_BASELINE
            self.migration_baseline_status = BASELINE_UNPROVEN_LEGACY
            self.legacy_activation_unproven = True
            self.activation_proven = False
            self.last_reason = "ACTIVATION_MULTIPLIER_INVALID"
        if self.status in (WATCH_ACTIVATED, WATCH_ACTIVATED_WAITING, WATCH_ACTIVE_DIP):
            # A complete activation checkpoint resumes monotonically as the
            # steady active state. An interrupted proof falls back to the
            # original immutable baseline (when valid) and must re-prove the
            # crossing; it never silently becomes eligible.
            resume_state = (WATCH_ACTIVATED_WAITING
                            if self.status == WATCH_ACTIVATED_WAITING
                            else WATCH_ACTIVE_DIP)
            candidate = {**self.activation_snapshot(), "activation_state": resume_state}
            if activation_proof_is_durable(candidate):
                self.status = resume_state
            else:
                baseline = _decimal(self.migration_market_cap_usd)
                target = _decimal(self.activation_target_market_cap_usd)
                if (self.migration_baseline_status == BASELINE_CAPTURED
                        and baseline is not None and target is not None
                        and target == baseline * expected_multiplier):
                    self.status = WATCH_PENDING_1_20X
                    self.last_reason = "ACTIVATION_CHECKPOINT_INCOMPLETE"
                else:
                    self.status = WATCH_PENDING_BASELINE
                    self.migration_baseline_status = BASELINE_UNPROVEN_LEGACY
                    self.legacy_activation_unproven = True
                    self.last_reason = "ACTIVATION_CHECKPOINT_INVALID"
                self.activation_proven = False
                self.activation_observation_fresh = False
                self.activation_latched = False
                self.activation_crossing_tick_blocked = False

    def set_market_tier_projection(
        self, *, tier: object, drawdown_pct: object,
    ) -> bool:
        """Apply OBSERVE-ONLY tier telemetry, normalizing what cannot persist.

        The projected tier/drawdown are display + scheduling telemetry, never
        send authority.  A value the durable checkpoint schema cannot hold is
        EXCLUDED (set to None) rather than written through to corrupt the
        required candidate record -- the 2026-07-30 failure mode, where a
        legitimate "0" drawdown made every subsequent watch checkpoint write
        fail structurally.  Returns True when the projection was retained
        in full.
        """

        self.market_latest_tier = (
            tier if isinstance(tier, str) and tier else None)
        if drawdown_pct is None:
            self.market_latest_drawdown_pct = None
            return True
        parsed = (_decimal(drawdown_pct, positive=False)
                  if isinstance(drawdown_pct, str) else None)
        if parsed is None or parsed < 0:
            self.market_latest_drawdown_pct = None
            return False
        self.market_latest_drawdown_pct = drawdown_pct
        return True

    def to_candidate(self) -> Dict[str, Any]:
        return {
            "token_mint": self.token_mint,
            "candidate_id": self.candidate_id,
            "migration_time_utc": self.migration_time_utc,
            "source_ref": self.source_ref,
            "symbol_or_name": self.symbol_or_name,
            "token_name": self.token_name,
            "discovery_provenance": self.discovery_provenance,
            "discovery_utc": self.discovery_utc,
            "live_epoch_id": self.live_epoch_id,
            "migration_slot": self.migration_slot,
            "migration_signature": self.migration_signature,
            "migration_proof": self.migration_proof,
            "migration_evidence_class": self.migration_evidence_class,
            "pair_address": self.pair_address,
            "pool_dex_identity": self.pool_dex_identity,
            "migration_market_cap_source": self.migration_market_cap_source,
            "ath_source": self.ath_source,
            "liquidity_source": self.liquidity_source,
            "current_data_source": self.current_data_source,
            "backfill_lookback_seconds": self.backfill_lookback_seconds,
            "backfill_sweep_id": self.backfill_sweep_id,
            "source_confidence": self.source_confidence,
            "dedupe_identity": self.dedupe_identity,
            "corroborating_sources": list(self.corroborating_sources),
            "corroborated_live_epoch_id": self.corroborated_live_epoch_id,
            "corroborated_migration_slot": self.corroborated_migration_slot,
            "backfill_evidence_digest": self.backfill_evidence_digest,
            "backfill_market_observed_at_utc": self.backfill_market_observed_at_utc,
            "backfill_initial_price_usd": self.backfill_initial_price_usd,
            "backfill_initial_market_cap_usd": self.backfill_initial_market_cap_usd,
            "backfill_initial_liquidity_usd": self.backfill_initial_liquidity_usd,
            "backfill_volume_m5_usd": self.backfill_volume_m5_usd,
            "backfill_volume_h1_usd": self.backfill_volume_h1_usd,
            "backfill_volume_h6_usd": self.backfill_volume_h6_usd,
            "backfill_volume_h24_usd": self.backfill_volume_h24_usd,
            "backfill_volume_fields_present": self.backfill_volume_fields_present,
            "activation": self.activation_snapshot(),
            "delivery_retry_count": self.delivery_retry_count,
            "delivery_next_retry_at_utc": self.delivery_next_retry_at_utc,
        }

    def is_active(self) -> bool:
        """Historical API: active means still tracked by the watch loop."""
        return self.status in _TRACKED

    def is_dip_active(self) -> bool:
        return activation_proof_is_eligible(self)

    def _migration_baseline_digest_is_valid(self) -> bool:
        if (self.migration_baseline_status != BASELINE_CAPTURED
                or self.migration_baseline_digest_version
                != MIGRATION_BASELINE_DIGEST_SCHEMA_VERSION):
            return False
        try:
            expected = build_migration_baseline_digest(
                token_mint=self.token_mint,
                candidate_id=self.candidate_id,
                market_cap_usd=self.migration_market_cap_usd,
                observed_at_utc=self.migration_market_cap_observed_at_utc,
                source=self.migration_market_cap_source,
                price=self.migration_market_cap_price,
                supply=self.migration_supply_at_observation,
            )
        except (TypeError, ValueError):
            return False
        return self.migration_baseline_digest == expected

    def activation_snapshot(self) -> Dict[str, Any]:
        proof = {
            "token_mint": self.token_mint,
            "candidate_id": self.candidate_id,
            "migration_time_utc": self.migration_time_utc,
            "discovery_provenance": self.discovery_provenance,
            "discovery_utc": self.discovery_utc,
            "live_epoch_id": self.live_epoch_id,
            "migration_slot": self.migration_slot,
            "migration_evidence_class": self.migration_evidence_class,
            "pair_address": self.pair_address,
            "pool_dex_identity": self.pool_dex_identity,
            "backfill_lookback_seconds": self.backfill_lookback_seconds,
            "backfill_sweep_id": self.backfill_sweep_id,
            "source_confidence": self.source_confidence,
            "dedupe_identity": self.dedupe_identity,
            "corroborating_sources": list(self.corroborating_sources),
            "backfill_evidence_digest": self.backfill_evidence_digest,
            "migration_market_cap_usd": self.migration_market_cap_usd,
            "migration_market_cap_source": self.migration_market_cap_source,
            "migration_market_cap_observed_at_utc": self.migration_market_cap_observed_at_utc,
            "migration_market_cap_price": self.migration_market_cap_price,
            "migration_supply_at_observation": self.migration_supply_at_observation,
            "migration_baseline_status": self.migration_baseline_status,
            "migration_baseline_digest": self.migration_baseline_digest,
            "migration_baseline_digest_version": self.migration_baseline_digest_version,
            "activation_multiplier": self.activation_multiplier,
            "activation_target_market_cap_usd": self.activation_target_market_cap_usd,
            "activation_state": self.status,
            "activated_at_utc": self.activated_at_utc,
            "activation_observation_source": self.activation_observation_source,
            "activation_current_market_cap_usd": self.activation_current_market_cap_usd,
            "activation_observation_fresh": self.activation_observation_fresh,
            "activation_proven": self.activation_proven,
            "activation_evidence_source": self.activation_evidence_source,
            "activation_evidence_market_cap_usd": self.activation_evidence_market_cap_usd,
            "activation_evidence_event_at_utc": self.activation_evidence_event_at_utc,
            "activation_evidence_ingested_at_utc": self.activation_evidence_ingested_at_utc,
            "activation_evidence_digest": self.activation_evidence_digest,
            "activation_evidence_version": self.activation_evidence_version,
            "activation_source_evidence_digest": self.activation_source_evidence_digest,
            "activation_observation_seal_digest": (
                self.activation_observation_seal_digest),
            "activation_observation_seal_version": (
                self.activation_observation_seal_version),
            "activation_proof_digest": self.activation_proof_digest,
            "activation_proof_version": self.activation_proof_version,
            "activation_evidence_kind": self.activation_evidence_kind,
            "activation_crossing_tick_digest": self.activation_crossing_tick_digest,
            "activation_crossing_tick_blocked": self.activation_crossing_tick_blocked,
            "activation_latched": self.activation_latched,
            "activation_migrated_from_schema": self.activation_migrated_from_schema,
            "activation_migration_performed_at_utc": (
                self.activation_migration_performed_at_utc),
            "activation_legacy_record_digest": self.activation_legacy_record_digest,
            "activation_legacy_checkpoint_digest": (
                self.activation_legacy_checkpoint_digest),
            "activation_accepted_at_utc": self.activated_at_utc,
            "activation_waiting_for_fresh_market": (
                self.status == WATCH_ACTIVATED_WAITING),
            "activation_current_market_required_for_tier": True,
            "latest_market_readiness_state": self.market_state,
            "latest_market_readiness_reason": (
                self.market_reason_code or self.last_reason),
            "legacy_activation_unproven": self.legacy_activation_unproven,
        }
        proof["activation_eligible"] = activation_proof_is_eligible(proof)
        proof["activation_proof_valid"] = activation_proof_is_durable(proof)
        return proof

    def initial_activation_events(self) -> List[Dict[str, Any]]:
        events = [{
            "kind": "PHX2_WATCHLIST_EVENT",
            "event": "MIGRATION_DETECTED",
            "token_mint": self.token_mint,
            "candidate_id": self.candidate_id,
            "observed_at_utc": self.seeded_at_utc,
            "state": self.status,
        }]
        if self.migration_baseline_status == BASELINE_CAPTURED:
            events.append(self._baseline_event())
        events.append(self._state_event(
            self.status, observed_at_utc=self.seeded_at_utc,
            activation_target_market_cap_usd=self.activation_target_market_cap_usd))
        return events

    def _baseline_event(self) -> Dict[str, Any]:
        return {
            "kind": "PHX2_WATCHLIST_EVENT",
            "event": "BASELINE_CAPTURED",
            "token_mint": self.token_mint,
            "candidate_id": self.candidate_id,
            "observed_at_utc": self.migration_market_cap_observed_at_utc,
            "state": self.status,
            "migration_market_cap_usd": self.migration_market_cap_usd,
            "source": self.migration_market_cap_source,
            "activation_target_market_cap_usd": self.activation_target_market_cap_usd,
        }

    def _state_event(self, state: str, **extra: Any) -> Dict[str, Any]:
        return {
            "kind": "PHX2_WATCHLIST_EVENT",
            "event": state,
            "token_mint": self.token_mint,
            "candidate_id": self.candidate_id,
            "observed_at_utc": extra.pop("observed_at_utc", None),
            "state": state,
            **extra,
        }

    def _capture_baseline(
        self,
        *,
        market_cap: Decimal,
        source: str,
        observed_at_utc: str,
        price: Optional[Decimal],
        supply: Optional[Decimal],
    ) -> bool:
        if self.migration_baseline_status == BASELINE_CAPTURED:
            return False
        self.migration_market_cap_usd = _decimal_text(market_cap)
        self.migration_market_cap_source = source
        self.migration_market_cap_observed_at_utc = observed_at_utc
        self.migration_market_cap_price = (
            _decimal_text(price) if price is not None else None)
        self.migration_supply_at_observation = (
            _decimal_text(supply) if supply is not None else None)
        self.migration_baseline_status = BASELINE_CAPTURED
        self.migration_baseline_digest_version = MIGRATION_BASELINE_DIGEST_SCHEMA_VERSION
        self.migration_baseline_digest = build_migration_baseline_digest(
            token_mint=self.token_mint,
            candidate_id=self.candidate_id,
            market_cap_usd=self.migration_market_cap_usd,
            observed_at_utc=observed_at_utc,
            source=source,
            price=self.migration_market_cap_price,
            supply=self.migration_supply_at_observation,
        )
        multiplier = _expected_activation_multiplier(self)
        threshold = _activation_threshold_multiplier(self)
        if multiplier is None or threshold is None:
            return False
        # The FIELD keeps the provenance-sealed value (the backfill evidence
        # digest is computed over it); the TARGET uses the policy threshold, so
        # PHX1_PARITY removes the backfill penalty without touching evidence.
        self.activation_multiplier = _decimal_text(multiplier)
        self.activation_target_market_cap_usd = _decimal_text(
            market_cap * threshold)
        self.status = WATCH_PENDING_1_20X
        self.last_reason = "PENDING_ACTIVATION_THRESHOLD"
        return True

    def _central_activation_evidence(
        self,
        *,
        central_ath: object,
        pumpswap_reserve: object,
        target: Decimal,
        now_text: str,
        max_age_seconds: float,
    ) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]], Optional[str]]:
        """Validate already-produced central ATH evidence for activation only."""

        if not isinstance(central_ath, Mapping) or not central_ath:
            return None, None, None

        def rejected(reason: str, counter: Optional[str] = None):
            event = self._state_event(
                "ACTIVATION_EVIDENCE_REJECTED",
                observed_at_utc=now_text,
                rejection_reason=reason,
                activation_counter=counter,
                activation_evidence_source=central_ath.get("ath_provider"),
                activation_evidence_event_at_utc=central_ath.get("ath_timestamp"),
                activation_evidence_ingested_at_utc=central_ath.get(
                    "ath_ingested_at_utc"),
            )
            return None, event, reason

        source = central_ath.get("ath_provider")
        if source not in (SOURCE_PAID_OHLCV, SOURCE_PAID_V3_PAIR,
                          SOURCE_PAID_CURRENT, SOURCE_PUMPSWAP_EVENT):
            return rejected(
                "ACTIVATION_EVIDENCE_SOURCE_DISALLOWED",
                "activation_disallowed_source_rejected")
        if central_ath.get("token_mint") != self.token_mint:
            return rejected(
                "ACTIVATION_EVIDENCE_MINT_MISMATCH",
                "activation_wrong_mint_rejected")
        bound_candidate = (central_ath.get("candidate_id")
                           or central_ath.get("ath_candidate_id"))
        if bound_candidate is not None and bound_candidate != self.candidate_id:
            return rejected("ACTIVATION_EVIDENCE_CANDIDATE_MISMATCH")
        market_cap = _decimal(central_ath.get("ath_market_cap"))
        event_at = _utc(central_ath.get("ath_timestamp"))
        ingested_at = _utc(central_ath.get("ath_ingested_at_utc"))
        now_at = _utc(now_text)
        baseline_at = _utc(self.migration_market_cap_observed_at_utc)
        if (market_cap is None or event_at is None or ingested_at is None
                or now_at is None):
            return rejected("ACTIVATION_EVIDENCE_MALFORMED")
        if baseline_at is None or event_at <= baseline_at:
            return rejected(
                "ACTIVATION_EVIDENCE_PRE_BASELINE",
                "activation_pre_baseline_rejected")
        if source == SOURCE_PAID_OHLCV:
            if (central_ath.get("ath_status") != STATUS_CONFIRMED
                    or central_ath.get("ath_observation_type") != SOURCE_PAID_OHLCV):
                return rejected(
                    "ACTIVATION_EVIDENCE_UNCONFIRMED",
                    "activation_unconfirmed_rejected")
            kind = ACTIVATION_KIND_CONFIRMED_OHLCV_HIGH
        elif source == SOURCE_PAID_V3_PAIR:
            # The canonical V3 pair candle high carries the same confirmed
            # candle-high semantics as the legacy OHLCV source and therefore
            # produces the same sealed activation-proof kind.
            if (central_ath.get("ath_status") != STATUS_CONFIRMED
                    or central_ath.get("ath_observation_type")
                    != SOURCE_PAID_V3_PAIR):
                return rejected(
                    "ACTIVATION_EVIDENCE_UNCONFIRMED",
                    "activation_unconfirmed_rejected")
            kind = ACTIVATION_KIND_CONFIRMED_OHLCV_HIGH
        elif source == SOURCE_PAID_CURRENT:
            if (central_ath.get("ath_status") not in (STATUS_CONFIRMED, STATUS_PROVISIONAL)
                    or central_ath.get("ath_observation_type") != SOURCE_PAID_CURRENT):
                return rejected("ACTIVATION_EVIDENCE_CURRENT_UNTRUSTED")
            kind = ACTIVATION_KIND_SPOT_CURRENT
        else:
            reserve = pumpswap_reserve if isinstance(pumpswap_reserve, Mapping) else {}
            if (central_ath.get("ath_status") != STATUS_CONFIRMED
                    or reserve.get("reserve_trusted_for_routing") is not True):
                return rejected("ACTIVATION_EVIDENCE_RESERVE_UNTRUSTED")
            kind = ACTIVATION_KIND_TRUSTED_RESERVE_EVENT
        if central_ath.get("ath_evidence_version") != ATH_EVIDENCE_SCHEMA_VERSION:
            return rejected("ACTIVATION_EVIDENCE_SCHEMA_UNSUPPORTED")
        source_digest = central_ath.get("ath_evidence_digest")
        source_digest_alias = central_ath.get("ath_source_evidence_digest")
        if (source_digest_alias is not None and source_digest_alias != source_digest):
            return rejected("ACTIVATION_EVIDENCE_DIGEST_INVALID")
        if not ath_evidence_digest_is_valid(self.token_mint, central_ath):
            return rejected("ACTIVATION_EVIDENCE_DIGEST_INVALID")
        if not ath_observation_seal_digest_is_valid(self.token_mint, central_ath):
            return rejected("ACTIVATION_OBSERVATION_SEAL_INVALID")
        if (self.discovery_provenance != DISCOVERY_PROVENANCE_DEX
                and not _fresh_observation(
                    observed_at_utc=central_ath.get("ath_timestamp"),
                    now_utc=now_text,
                    max_age_seconds=max_age_seconds)):
            return rejected(
                "ACTIVATION_SOURCE_EVENT_TOO_OLD",
                "activation_source_event_too_old")
        if not _fresh_observation(
                observed_at_utc=central_ath.get("ath_ingested_at_utc"),
                now_utc=now_text,
                max_age_seconds=max_age_seconds):
            return rejected(
                "ACTIVATION_EVIDENCE_STALE_INGEST",
                "activation_evidence_stale_ingest")
        if ingested_at > now_at:
            return rejected("ACTIVATION_EVIDENCE_INGESTED_IN_FUTURE")
        if market_cap < target:
            return rejected("ACTIVATION_EVIDENCE_BELOW_TARGET")
        return ({
            "source": source,
            "market_cap": market_cap,
            "event_at_utc": central_ath.get("ath_timestamp"),
            "ingested_at_utc": central_ath.get("ath_ingested_at_utc"),
            "source_digest": source_digest,
            "source_version": ATH_EVIDENCE_SCHEMA_VERSION,
            "observation_seal_digest": central_ath.get(
                "ath_observation_seal_digest"),
            "observation_seal_version": central_ath.get(
                "ath_observation_seal_version"),
            "equal_reobserved": bool(
                central_ath.get("ath_equal_evidence_reobserved_count")),
            "kind": kind,
        }, None, None)

    def _latch_activation(
        self,
        *,
        evidence: Mapping[str, Any],
        baseline: Decimal,
        tick_digest: str,
        now_text: str,
        current_market_fresh: bool,
        events: List[Dict[str, Any]],
    ) -> None:
        evidence_market_cap = evidence["market_cap"]
        move_text = _decimal_text(evidence_market_cap / baseline)
        self.status = (WATCH_ACTIVE_DIP if current_market_fresh
                       else WATCH_ACTIVATED_WAITING)
        self.activated_at_utc = now_text
        self.activation_observation_source = evidence["source"]
        self.activation_current_market_cap_usd = _decimal_text(evidence_market_cap)
        self.activation_observation_fresh = True
        self.activation_proven = True
        self.activation_evidence_source = evidence["source"]
        self.activation_evidence_market_cap_usd = _decimal_text(evidence_market_cap)
        self.activation_evidence_event_at_utc = evidence["event_at_utc"]
        self.activation_evidence_ingested_at_utc = evidence["ingested_at_utc"]
        self.activation_evidence_digest = evidence["source_digest"]
        self.activation_source_evidence_digest = evidence["source_digest"]
        self.activation_evidence_version = evidence["source_version"]
        self.activation_observation_seal_digest = evidence[
            "observation_seal_digest"]
        self.activation_observation_seal_version = evidence[
            "observation_seal_version"]
        self.activation_proof_version = ACTIVATION_EVIDENCE_SCHEMA_VERSION
        self.activation_evidence_kind = evidence["kind"]
        self.activation_crossing_tick_digest = tick_digest
        self.activation_crossing_tick_blocked = True
        self.activation_latched = True
        self.activation_proof_digest = build_activation_evidence_digest(
            token_mint=self.token_mint,
            candidate_id=self.candidate_id,
            migration_baseline_digest=self.migration_baseline_digest,
            migration_market_cap_usd=self.migration_market_cap_usd,
            migration_market_cap_observed_at_utc=(
                self.migration_market_cap_observed_at_utc),
            activation_target_market_cap_usd=(
                self.activation_target_market_cap_usd),
            activation_evidence_market_cap_usd=(
                self.activation_evidence_market_cap_usd),
            activation_evidence_event_at_utc=(
                self.activation_evidence_event_at_utc),
            activation_evidence_ingested_at_utc=(
                self.activation_evidence_ingested_at_utc),
            activated_at_utc=self.activated_at_utc,
            activation_evidence_source=self.activation_evidence_source,
            activation_evidence_kind=self.activation_evidence_kind,
            activation_source_evidence_digest=self.activation_evidence_digest,
            activation_source_evidence_version=self.activation_evidence_version,
            activation_observation_seal_digest=(
                self.activation_observation_seal_digest),
            activation_observation_seal_version=(
                self.activation_observation_seal_version),
            activation_crossing_tick_digest=self.activation_crossing_tick_digest,
            activation_multiplier=self.activation_multiplier,
        )
        self.last_reason = ("ACTIVATION_THRESHOLD_REACHED" if current_market_fresh
                            else WATCH_ACTIVATED_WAITING)
        proven_counter = {
            ACTIVATION_KIND_CONFIRMED_OHLCV_HIGH:
                "activation_proven_by_ohlcv_high",
            ACTIVATION_KIND_TRUSTED_RESERVE_EVENT:
                "activation_proven_by_reserve_event",
        }.get(evidence["kind"], (
            "activation_proven_by_current_price"
            if evidence["source"] == SOURCE_PAID_CURRENT
            else "activation_proven_by_spot"))
        events.append(self._state_event(
            WATCH_ACTIVATED,
            observed_at_utc=now_text,
            activation_evidence_event_at_utc=evidence["event_at_utc"],
            activation_evidence_ingested_at_utc=evidence["ingested_at_utc"],
            activation_evidence_market_cap_usd=_decimal_text(evidence_market_cap),
            activation_evidence_source=evidence["source"],
            activation_evidence_kind=evidence["kind"],
            activation_source_evidence_digest=self.activation_evidence_digest,
            activation_observation_seal_digest=(
                self.activation_observation_seal_digest),
            activation_proof_digest=self.activation_proof_digest,
            activation_proof_version=self.activation_proof_version,
            activation_crossing_tick_blocked=True,
            activation_counter=proven_counter,
            multiplier=move_text))
        if evidence.get("equal_reobserved"):
            events.extend((self._state_event(
                "ACTIVATION_EQUAL_EVIDENCE_REOBSERVED",
                observed_at_utc=now_text,
                activation_counter="activation_equal_evidence_reobserved"),
                self._state_event(
                    "ACTIVATION_OBSERVATION_SEAL_REFRESHED",
                    observed_at_utc=now_text,
                    activation_counter="activation_observation_seal_refreshed")))
        if not current_market_fresh:
            events.append(self._state_event(
                "ACTIVATION_PROVEN_WITHOUT_CURRENT_SPOT",
                observed_at_utc=now_text,
                activation_counter="activation_proven_without_current_spot"))
        events.append(self._state_event(
            self.status,
            observed_at_utc=now_text,
            activation_evidence_market_cap_usd=_decimal_text(evidence_market_cap),
            activation_proof_digest=self.activation_proof_digest,
            activation_counter=("activation_waiting_for_fresh_market"
                                if not current_market_fresh
                                else "activation_crossing_tick_blocks"),
            multiplier=move_text))

    def observe_market(
        self,
        *,
        current_market_cap_usd: object,
        current_price: object,
        current_supply: object,
        provider_timestamp_utc: object,
        observed_at_utc: object,
        observation_source: object,
        max_age_seconds: float,
        central_ath: object = None,
        pumpswap_reserve: object = None,
    ) -> Dict[str, Any]:
        """Capture a baseline and latch on fresh spot or sealed central evidence."""

        events: List[Dict[str, Any]] = []
        just_activated = False
        if self.status not in _TRACKED:
            return {"activation": self.activation_snapshot(), "events": events,
                    "eligible": False, "just_activated": False,
                    "reason": "TERMINAL_STATE"}
        current = _decimal(current_market_cap_usd)
        price = _decimal(current_price)
        supply = _decimal(current_supply)
        source = observation_source if isinstance(observation_source, str) else ""
        provider_ts = provider_timestamp_utc if isinstance(provider_timestamp_utc, str) else ""
        now_text = observed_at_utc if isinstance(observed_at_utc, str) else ""
        central_digest = (central_ath.get("ath_evidence_digest")
                          if isinstance(central_ath, Mapping) else None)
        tick_digest = _activation_tick_digest(
            mint=self.token_mint,
            current_market_cap=current,
            current_price=price,
            provider_timestamp_utc=provider_ts,
            observation_source=source,
            central_evidence_digest=central_digest,
        )
        fresh = bool(current is not None and price is not None and source
                     and _fresh_observation(
                         observed_at_utc=provider_ts,
                         now_utc=now_text,
                         max_age_seconds=max_age_seconds))

        if self.status == WATCH_PENDING_BASELINE:
            if self.legacy_activation_unproven:
                self.last_reason = "LEGACY_ACTIVATION_UNPROVEN"
                return {"activation": self.activation_snapshot(), "events": events,
                        "eligible": False, "just_activated": False,
                        "reason": self.last_reason}
            if not fresh:
                self.last_reason = "PENDING_FRESH_MARKET_OBSERVATION"
                return {"activation": self.activation_snapshot(), "events": events,
                        "eligible": False, "just_activated": False,
                        "reason": self.last_reason}
            if source != ACTIVATION_SOURCE_PAID_SPOT:
                self.last_reason = "PENDING_PAID_PRIMARY_BASELINE"
                return {"activation": self.activation_snapshot(), "events": events,
                        "eligible": False, "just_activated": False,
                        "reason": self.last_reason}
            if self._capture_baseline(
                    market_cap=current,
                    source=BASELINE_SOURCE_BIRDEYE,
                    observed_at_utc=provider_ts,
                    price=price,
                    supply=supply):
                events.extend((self._baseline_event(), self._state_event(
                    WATCH_PENDING_1_20X,
                    observed_at_utc=provider_ts,
                    activation_target_market_cap_usd=self.activation_target_market_cap_usd)))

        if self.status == WATCH_PENDING_1_20X:
            baseline = _decimal(self.migration_market_cap_usd)
            target = _decimal(self.activation_target_market_cap_usd)
            if baseline is None or target is None:
                self.status = WATCH_PENDING_BASELINE
                self.migration_baseline_status = BASELINE_UNPROVEN_LEGACY
                self.legacy_activation_unproven = True
                self.last_reason = "BASELINE_CHECKPOINT_INVALID"
                return {"activation": self.activation_snapshot(), "events": events,
                        "eligible": False, "just_activated": False,
                        "reason": self.last_reason}
            evidence: Optional[Dict[str, Any]] = None
            provider_at = _utc(provider_ts)
            baseline_at = _utc(self.migration_market_cap_observed_at_utc)
            if (fresh and source == ACTIVATION_SOURCE_PAID_SPOT
                    and provider_at is not None
                    and baseline_at is not None and provider_at > baseline_at
                    and current >= target):
                source_digest = build_activation_spot_evidence_digest(
                    mint=self.token_mint, market_cap=current,
                    event_at_utc=provider_ts, source=source)
                observation_seal_digest = build_ath_observation_seal_digest(
                    self.token_mint, {
                        "ath_evidence_digest": source_digest,
                        "ath_ingested_at_utc": now_text,
                        "ath_observation_seal_validated": True,
                    })
                evidence = {
                    "source": ACTIVATION_SOURCE_PAID_SPOT,
                    "market_cap": current,
                    "event_at_utc": provider_ts,
                    "ingested_at_utc": now_text,
                    "source_digest": source_digest,
                    "source_version": ACTIVATION_EVIDENCE_SPOT_VERSION,
                    "observation_seal_digest": observation_seal_digest,
                    "observation_seal_version": ATH_OBSERVATION_SEAL_SCHEMA_VERSION,
                    "equal_reobserved": False,
                    "kind": ACTIVATION_KIND_SPOT_CURRENT,
                }
            if evidence is None:
                central_evidence, rejection_event, _ = self._central_activation_evidence(
                    central_ath=central_ath,
                    pumpswap_reserve=pumpswap_reserve,
                    target=target,
                    now_text=now_text,
                    max_age_seconds=max_age_seconds,
                )
                evidence = central_evidence
                if rejection_event is not None:
                    events.append(rejection_event)
            if evidence is not None:
                self._latch_activation(
                    evidence=evidence, baseline=baseline,
                    tick_digest=tick_digest, now_text=now_text,
                    current_market_fresh=fresh, events=events)
                just_activated = True
            elif (fresh and self.last_activation_progress_market_cap_usd
                  != _decimal_text(current)):
                move_text = _decimal_text(current / baseline)
                self.last_activation_progress_market_cap_usd = _decimal_text(current)
                self.last_reason = "PENDING_ACTIVATION_THRESHOLD"
                events.append(self._state_event(
                    "PROGRESS",
                    observed_at_utc=provider_ts,
                    current_market_cap_usd=_decimal_text(current),
                    multiplier=move_text,
                    activation_target_market_cap_usd=self.activation_target_market_cap_usd))

        durable_activation = activation_proof_is_durable(self)
        if durable_activation:
            if not fresh:
                was_waiting = self.status == WATCH_ACTIVATED_WAITING
                self.status = WATCH_ACTIVATED_WAITING
                self.last_reason = WATCH_ACTIVATED_WAITING
                if not was_waiting and not just_activated:
                    events.append(self._state_event(
                        WATCH_ACTIVATED_WAITING,
                        observed_at_utc=now_text,
                        activation_counter="activation_waiting_for_fresh_market"))
                return {"activation": self.activation_snapshot(), "events": events,
                        "eligible": False, "just_activated": just_activated,
                        "reason": self.last_reason}
            if just_activated:
                return {"activation": self.activation_snapshot(), "events": events,
                        "eligible": False, "just_activated": True,
                        "reason": "ACTIVATION_CROSSING_TICK_BLOCKED"}
            if tick_digest == self.activation_crossing_tick_digest:
                self.last_reason = "ACTIVATION_CROSSING_TICK_BLOCKED"
                events.append(self._state_event(
                    "ACTIVATION_CROSSING_TICK_BLOCKED",
                    observed_at_utc=now_text,
                    activation_counter="activation_crossing_tick_blocks",
                    activation_source_evidence_digest=(
                        self.activation_source_evidence_digest)))
                return {"activation": self.activation_snapshot(), "events": events,
                        "eligible": False, "just_activated": False,
                        "reason": self.last_reason}
            if not self._migration_baseline_digest_is_valid():
                self.last_reason = "MIGRATION_BASELINE_DIGEST_INVALID"
                return {"activation": self.activation_snapshot(), "events": events,
                        "eligible": False, "just_activated": False,
                        "reason": self.last_reason}
            provider_at = _utc(provider_ts)
            activation_event_at = _utc(self.activation_evidence_event_at_utc)
            activation_accepted_at = _utc(self.activated_at_utc)
            if (provider_at is None or activation_event_at is None
                    or activation_accepted_at is None
                    or provider_at <= activation_event_at
                    or provider_at <= activation_accepted_at):
                self.status = WATCH_ACTIVATED_WAITING
                self.last_reason = "ACTIVATION_LATER_MARKET_TICK_REQUIRED"
                events.append(self._state_event(
                    "ACTIVATION_LATER_MARKET_TICK_REQUIRED",
                    observed_at_utc=now_text,
                    authoritative_ordering_timestamp="provider_timestamp_utc",
                    activation_evidence_event_at_utc=(
                        self.activation_evidence_event_at_utc),
                    activation_accepted_at_utc=self.activated_at_utc))
                return {"activation": self.activation_snapshot(), "events": events,
                        "eligible": False, "just_activated": False,
                        "reason": self.last_reason}
            self.status = WATCH_ACTIVE_DIP
            self.last_reason = WATCH_ACTIVE_DIP
            return {"activation": self.activation_snapshot(), "events": events,
                    "eligible": activation_proof_is_eligible(self),
                    "just_activated": False, "reason": WATCH_ACTIVE_DIP}

        if not fresh:
            self.last_reason = "PENDING_FRESH_MARKET_OBSERVATION"
        eligible = False
        return {
            "activation": self.activation_snapshot(),
            "events": events,
            "eligible": eligible,
            "just_activated": just_activated,
            "reason": ("ACTIVE_DIP_WATCH" if eligible else self.last_reason),
        }


# ---------------------------------------------------------------------------
# Authenticated watch checkpoint validation (PHX2-E2E-005)
# ---------------------------------------------------------------------------

_WATCH_ENTRY_FIELD_NAMES: Tuple[str, ...] = tuple(
    f.name for f in dataclass_fields(WatchEntry))

# Statuses the current-schema writer may legitimately persist. Transitional
# (ACTIVATED) and legacy import tokens (SEEDED/WATCHING) are normalized before
# any persist, so their presence in an authenticated checkpoint is tamper.
_WATCH_CHECKPOINT_ALLOWED_STATUSES = (
    WATCH_PENDING_BASELINE, WATCH_PENDING_1_20X, WATCH_ACTIVATED_WAITING,
    WATCH_ACTIVE_DIP, WATCH_DELIVERY_UNKNOWN,
) + TERMINAL_WATCH_STATES

_WATCH_LEGACY_KNOWN_STATUSES = _WATCH_CHECKPOINT_ALLOWED_STATUSES + (
    WATCH_ACTIVATED, WATCH_SEEDED, WATCH_WATCHING)

#: Fields whose only meaningful value is strictly positive (a market cap, a
#: price, a supply).  Zero or negative is genuine corruption.
_WATCH_DECIMAL_FIELDS = (
    "migration_market_cap_usd", "migration_market_cap_price",
    "migration_supply_at_observation", "activation_target_market_cap_usd",
    "activation_current_market_cap_usd", "activation_evidence_market_cap_usd",
    "last_activation_progress_market_cap_usd",
    "backfill_initial_price_usd",
)

#: Fields whose domain LEGITIMATELY includes zero.
#:
#: ``market_latest_drawdown_pct`` moved here on 2026-07-30.  It is observe-only
#: tier telemetry produced by ``project_closed_tier``, which returns exactly
#: "0" the moment a mint's current market cap equals its own ATH -- which is
#: what EVERY mint looks like on the tick that first establishes its ATH from a
#: spot observation.  Validated as strictly positive, that legitimate zero was
#: rejected as CHECKPOINT_NUMERIC_INVALID, and because the value is a plain
#: JSON string the diagnostic could only report the useless field_path
#: "record".  The failure is classified STRUCTURAL (never retried), so the
#: durable watch checkpoint stopped being written entirely: 17 attempted, 2
#: succeeded, 15 consecutive structural failures.  Zero is now accepted;
#: negative, non-finite, float and non-string values still fail closed.
_WATCH_NONNEGATIVE_DECIMAL_FIELDS = (
    "backfill_initial_market_cap_usd", "backfill_initial_liquidity_usd",
    "backfill_volume_m5_usd", "backfill_volume_h1_usd",
    "backfill_volume_h6_usd", "backfill_volume_h24_usd",
    "market_latest_drawdown_pct",
)

_WATCH_TIMESTAMP_FIELDS = (
    "migration_time_utc", "seeded_at_utc", "last_observed_at_utc",
    "next_market_refresh_at_utc", "migration_market_cap_observed_at_utc",
    "activated_at_utc", "activation_evidence_event_at_utc",
    "activation_evidence_ingested_at_utc", "delivery_next_retry_at_utc",
    "activation_migration_performed_at_utc",
    "market_price_observed_at_utc", "market_market_cap_observed_at_utc",
    "market_liquidity_observed_at_utc",
    "discovery_utc", "backfill_market_observed_at_utc",
    "epoch_rebound_at_utc",
)

_WATCH_INT_FIELDS = (
    "recheck_count", "market_attempt_count", "delivery_attempt_count",
    "delivery_retry_count", "market_observation_generation",
)

_WATCH_BOOL_FIELDS = (
    "activation_observation_fresh", "activation_proven",
    "activation_crossing_tick_blocked", "activation_latched",
    "legacy_activation_unproven", "market_legacy_terminal_migrated",
    "backfill_volume_fields_present",
)


def _sanitize_checkpoint_value(value: Any) -> Any:
    """Make hostile legacy payloads canonically serializable (floats become
    their repr strings; the byte-exact original stays in the preserved
    evidence sidecar and is bound by the legacy record digest)."""

    if isinstance(value, float):
        return repr(value)
    if isinstance(value, dict):
        return {str(k): _sanitize_checkpoint_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_sanitize_checkpoint_value(v) for v in value]
    return value


def watch_checkpoint_record_identity(record: Mapping[str, Any]) -> List[Tuple]:
    """Stable identity keys: one mint may appear once, and one candidate ID
    may bind to at most one mint."""

    mint = record.get("token_mint")
    if not isinstance(mint, str) or not mint:
        raise ValueError("CHECKPOINT_MINT_BINDING_INVALID")
    if record.get("checkpoint_record_kind") == QUARANTINED_CANDIDATE_RECORD_KIND:
        return [("mint", mint)]
    return [("mint", mint), ("cid", record.get("candidate_id"))]


def _validate_quarantined_candidate_record(
    record: Mapping[str, Any],
) -> Tuple[bool, str]:
    mint = record.get("token_mint")
    if not isinstance(mint, str) or not mint:
        return False, _cpe.QUARANTINE_MINT_BINDING_INVALID
    if not isinstance(record.get("candidate_id"), str):
        return False, _cpe.QUARANTINE_CANDIDATE_BINDING_INVALID
    if record.get("quarantine_reason") not in _cpe.QUARANTINE_REASONS:
        return False, _cpe.QUARANTINE_MIGRATION_AMBIGUOUS
    if not isinstance(record.get("legacy_payload"), Mapping):
        return False, _cpe.QUARANTINE_MIGRATION_AMBIGUOUS
    if not isinstance(record.get("source_schema_version"), str):
        return False, _cpe.QUARANTINE_SCHEMA_UNSUPPORTED
    for digest_field in ("legacy_record_digest", "legacy_checkpoint_digest"):
        value = record.get(digest_field)
        if value is not None and (
                not isinstance(value, str) or len(value) != 64):
            return False, _cpe.QUARANTINE_RECORD_DIGEST_INVALID
    if _cpe.parse_utc_timestamp(record.get("quarantined_at_utc")) is None:
        return False, _cpe.QUARANTINE_TIMESTAMP_INVALID
    return True, ""


# -- canonical per-mint identity ------------------------------------------
#
# The checkpoint has always enforced ONE record per mint
# (``watch_checkpoint_record_identity``), which is the correct contract: every
# downstream consumer -- ATH, tier suppression, dedupe, delivery -- reasons
# about canonical state per mint, not per candidate_id. The defect was that
# nothing enforced that invariant BEFORE serialization, so two candidate_ids
# binding one mint produced a document that failed its own read-back
# validation with ``CHECKPOINT_DUPLICATE_RECORD``, permanently and silently.
#
# Uniqueness therefore stays "one canonical record per mint after merge".
# Compatible duplicates are merged with monotonic rules; genuinely conflicting
# duplicates fail closed with a safe reason rather than guessing.

#: Status strength, weakest first. A stronger status dominates a merge.
_STATUS_RANK = {
    WATCH_PENDING_BASELINE: 0,
    WATCH_PENDING_1_20X: 1,
    WATCH_ACTIVATED_WAITING: 2,
    WATCH_ACTIVE_DIP: 3,
    WATCH_DELIVERY_UNKNOWN: 4,
}

#: Fields merged by taking the numerically greatest value (monotonic).
_MERGE_MAX_INT_FIELDS = (
    "recheck_count", "market_attempt_count", "market_observation_generation",
    "delivery_attempt_count", "delivery_retry_count",
)

#: Fields merged by taking the greatest exact Decimal (monotonic high-water).
_MERGE_MAX_DECIMAL_FIELDS = (
    "last_activation_progress_market_cap_usd",
    "activation_evidence_market_cap_usd",
    "activation_current_market_cap_usd",
)

#: Duplicate-identity classes (closed set) surfaced in diagnostics.
DUPLICATE_IDENTITY_MINT = "DUPLICATE_MINT"
DUPLICATE_IDENTITY_CANDIDATE = "DUPLICATE_CANDIDATE_ID"
DUPLICATE_IDENTITY_NONE = "NONE"

#: Conflict reasons (closed set). Never carries candidate contents.
CONFLICT_BASELINE_MISMATCH = "CANONICAL_MERGE_BASELINE_MISMATCH"
CONFLICT_DELIVERY_MISMATCH = "CANONICAL_MERGE_DELIVERY_LEDGER_MISMATCH"
CONFLICT_ACTIVATION_MISMATCH = "CANONICAL_MERGE_ACTIVATION_PROOF_MISMATCH"


def _status_rank(record: Mapping[str, Any]) -> int:
    return _STATUS_RANK.get(str(record.get("status")), -1)


def _merge_conflict_reason(
    left: Mapping[str, Any], right: Mapping[str, Any],
) -> Optional[str]:
    """Closed-set reason two same-mint records cannot be merged, else None."""

    lb, rb = (left.get("migration_baseline_digest"),
              right.get("migration_baseline_digest"))
    if lb and rb and lb != rb:
        return CONFLICT_BASELINE_MISMATCH
    lk, rk = left.get("delivery_ledger_key"), right.get("delivery_ledger_key")
    if lk and rk and lk != rk:
        return CONFLICT_DELIVERY_MISMATCH
    la, ra = (left.get("activation_proof_digest"),
              right.get("activation_proof_digest"))
    if la and ra and la != ra:
        return CONFLICT_ACTIVATION_MISMATCH
    return None


def merge_canonical_watch_records(
    left: Mapping[str, Any], right: Mapping[str, Any],
) -> Tuple[Optional[Dict[str, Any]], str]:
    """Merge two same-mint records into one canonical record.

    Returns ``(merged, "")`` or ``(None, closed_set_conflict_reason)``. The
    dominant record is the one with the stronger status; every monotonic field
    keeps its high-water value so a merge can never regress ATH progress, a
    reached tier, an attempt count or established metadata. Provenance is
    never upgraded from partial (DEX backfill) to complete (live Yellowstone)
    unless the live record genuinely carries it.
    """

    conflict = _merge_conflict_reason(left, right)
    if conflict:
        return None, conflict
    dominant, other = (
        (left, right) if _status_rank(left) >= _status_rank(right)
        else (right, left))
    merged = dict(dominant)
    for key, value in dict(other).items():
        if merged.get(key) in (None, "", [], False) and value not in (None, ""):
            # Only fill genuine holes; the dominant record always wins a
            # contested non-empty field.
            if key == "discovery_provenance":
                continue
            merged[key] = value
    for field_name in _MERGE_MAX_INT_FIELDS:
        values = [v for v in (left.get(field_name), right.get(field_name))
                  if isinstance(v, int) and not isinstance(v, bool)]
        if values:
            merged[field_name] = max(values)
    for field_name in _MERGE_MAX_DECIMAL_FIELDS:
        best, best_text = None, None
        for source in (left, right):
            text = source.get(field_name)
            parsed = _decimal(text) if isinstance(text, str) else None
            if parsed is not None and (best is None or parsed > best):
                best, best_text = parsed, text
        if best_text is not None:
            merged[field_name] = best_text
    # Provenance: complete live evidence dominates partial backfill evidence,
    # never the reverse. A DEX record is never relabelled as live, and a live
    # record keeps its OWN live provenance (LIVE_HELIUS is never rewritten to
    # LIVE_YELLOWSTONE): when both records are live the dominant record's
    # provenance already won above.
    left_live = left.get("discovery_provenance") in LIVE_DISCOVERY_PROVENANCES
    right_live = (
        right.get("discovery_provenance") in LIVE_DISCOVERY_PROVENANCES)
    if left_live != right_live:
        live_source = left if left_live else right
        merged["discovery_provenance"] = live_source["discovery_provenance"]
        for key in ("migration_slot", "live_epoch_id",
                    "migration_evidence_class", "activation_multiplier"):
            if live_source.get(key) is not None:
                merged[key] = live_source[key]
    merged.pop("record_digest", None)
    return merged, ""


def canonicalize_watch_checkpoint_records(
    records: Sequence[Mapping[str, Any]],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Collapse same-mint records to one canonical record each.

    Returns ``(canonical_records, conflicts)``. Quarantined candidate records
    are passed through untouched: they are deliberately preserved raw and are
    already keyed by mint alone.
    """

    by_mint: Dict[str, Dict[str, Any]] = {}
    order: List[str] = []
    passthrough: List[Dict[str, Any]] = []
    conflicts: List[Dict[str, Any]] = []
    for index, raw in enumerate(records or ()):
        record = dict(raw)
        mint = record.get("token_mint")
        if record.get("checkpoint_record_kind") == QUARANTINED_CANDIDATE_RECORD_KIND \
                or not isinstance(mint, str) or not mint:
            passthrough.append(record)
            continue
        if mint not in by_mint:
            by_mint[mint] = record
            order.append(mint)
            continue
        merged, reason = merge_canonical_watch_records(by_mint[mint], record)
        if merged is None:
            conflicts.append({
                "record_index": index,
                "duplicate_identity_type": DUPLICATE_IDENTITY_MINT,
                "reason": reason,
                "record_identity_digest": _cpe.build_record_digest(
                    _cpe.CHECKPOINT_KIND_WATCH,
                    {"token_mint": mint,
                     "candidate_id": record.get("candidate_id")}),
            })
            continue
        by_mint[mint] = merged
    out: List[Dict[str, Any]] = []
    for mint in order:
        record = dict(by_mint[mint])
        record.pop("record_digest", None)
        record["record_digest"] = _cpe.build_record_digest(
            _cpe.CHECKPOINT_KIND_WATCH, record)
        out.append(record)
    out.extend(passthrough)
    out.sort(key=lambda row: (str(row.get("candidate_id") or ""),
                              str(row.get("token_mint") or "")))
    return out, conflicts


def describe_checkpoint_records(
    records: Sequence[Mapping[str, Any]],
) -> Optional[Dict[str, Any]]:
    """Pre-write validation returning SAFE diagnostics, or None when clean.

    Reports the failing record index, the closed-set reason, the offending
    field path and a record identity digest -- never candidate contents and
    never a credential-bearing value.
    """

    seen: Dict[Tuple, int] = {}
    for index, raw in enumerate(records or ()):
        record = dict(raw)
        try:
            identity = watch_checkpoint_record_identity(record)
        except ValueError:
            return {
                "failure_category": _cpe.CHECKPOINT_FAILURE_STRUCTURAL,
                "reason": _cpe.QUARANTINE_MINT_BINDING_INVALID,
                "record_index": index,
                "field_path": "token_mint",
                "record_identity_digest": None,
                "duplicate_identity_type": DUPLICATE_IDENTITY_NONE,
                "schema_version": WATCH_CHECKPOINT_SCHEMA_VERSION,
                "candidate_count": len(records or ()),
            }
        digest = _cpe.build_record_digest(
            _cpe.CHECKPOINT_KIND_WATCH,
            {"token_mint": record.get("token_mint"),
             "candidate_id": record.get("candidate_id")})
        for key in identity:
            if key in seen:
                return {
                    "failure_category": _cpe.CHECKPOINT_FAILURE_STRUCTURAL,
                    "reason": _cpe.QUARANTINE_DUPLICATE_RECORD,
                    "record_index": index,
                    "first_record_index": seen[key],
                    "field_path": f"identity.{key[0]}",
                    "record_identity_digest": digest,
                    "duplicate_identity_type": (
                        DUPLICATE_IDENTITY_MINT if key[0] == "mint"
                        else DUPLICATE_IDENTITY_CANDIDATE),
                    "schema_version": WATCH_CHECKPOINT_SCHEMA_VERSION,
                    "candidate_count": len(records or ()),
                }
            seen[key] = index
        ok, reason = validate_watch_checkpoint_record(record)
        if not ok:
            return {
                "failure_category": _cpe.CHECKPOINT_FAILURE_STRUCTURAL,
                "reason": reason,
                "record_index": index,
                "field_path": (
                    _unserializable_field_path(record)
                    or (_invalid_numeric_field_path(record)
                        if reason == _cpe.QUARANTINE_NUMERIC_INVALID else None)
                    or "record"),
                "record_identity_digest": digest,
                "duplicate_identity_type": DUPLICATE_IDENTITY_NONE,
                "schema_version": WATCH_CHECKPOINT_SCHEMA_VERSION,
                "candidate_count": len(records or ()),
            }
        path = _unserializable_field_path(record)
        if path is not None:
            return {
                "failure_category": _cpe.CHECKPOINT_FAILURE_STRUCTURAL,
                "reason": _cpe.QUARANTINE_JSON_INVALID,
                "record_index": index,
                "field_path": path,
                "record_identity_digest": digest,
                "duplicate_identity_type": DUPLICATE_IDENTITY_NONE,
                "schema_version": WATCH_CHECKPOINT_SCHEMA_VERSION,
                "candidate_count": len(records or ()),
            }
    return None


def _invalid_numeric_field_path(record: Mapping[str, Any]) -> Optional[str]:
    """Name the FIRST numerically-invalid field, in validator order.

    ``_unserializable_field_path`` only finds values JSON cannot encode, so a
    schema-shaped-but-invalid string (the 2026-07-30 drawdown "0") degraded the
    diagnostic to the bare path "record" and left 15 identical structural
    failures unattributable without a replay.  Returns the PATH only -- never
    the offending value, which may be candidate-bearing.
    """

    if not isinstance(record, Mapping):
        return None
    for field_name in _WATCH_DECIMAL_FIELDS:
        value = record.get(field_name)
        if value is None:
            continue
        if not isinstance(value, str) or _decimal(value) is None:
            return field_name
    for field_name in _WATCH_NONNEGATIVE_DECIMAL_FIELDS:
        value = record.get(field_name)
        if value is None:
            continue
        parsed = _decimal(value, positive=False)
        if not isinstance(value, str) or parsed is None or parsed < 0:
            return field_name
    expected_multiplier = _expected_activation_multiplier(record)
    if expected_multiplier is None or record.get(
            "activation_multiplier", "1.20") != _decimal_text(
                expected_multiplier):
        return "activation_multiplier"
    for field_name in _WATCH_INT_FIELDS:
        value = record.get(field_name, 0)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            return field_name
    for field_name in ("migration_slot", "backfill_lookback_seconds",
                       "corroborated_migration_slot"):
        value = record.get(field_name)
        if value is not None and (
                isinstance(value, bool) or not isinstance(value, int)
                or value < 0):
            return field_name
    receipt_id = record.get("delivery_receipt_message_id")
    if receipt_id is not None and (
            isinstance(receipt_id, bool) or not isinstance(receipt_id, int)):
        return "delivery_receipt_message_id"
    for field_name in _WATCH_BOOL_FIELDS:
        if not isinstance(record.get(field_name, False), bool):
            return field_name
    return None


def _unserializable_field_path(
    value: Any, prefix: str = "",
) -> Optional[str]:
    """Deterministic path to the first non-JSON-safe value, or None.

    Deliberately explicit instead of ``default=str``: a broad coercion turns a
    Decimal or datetime into a lossy string and hides the schema drift that
    produced it. Only the PATH is returned -- never the offending value.
    """

    if value is None or isinstance(value, (str, bool, int)):
        if isinstance(value, int) and not isinstance(value, bool):
            return None
        return None
    if isinstance(value, float):
        # Binary floats are banned outright: exact Decimal strings are the
        # approved representation everywhere in this schema.
        return prefix or "<root>"
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str):
                return f"{prefix}.<non-string-key>" if prefix else "<non-string-key>"
            path = _unserializable_field_path(
                item, f"{prefix}.{key}" if prefix else str(key))
            if path is not None:
                return path
        return None
    if isinstance(value, (list, tuple)):
        for position, item in enumerate(value):
            path = _unserializable_field_path(
                item, f"{prefix}[{position}]")
            if path is not None:
                return path
        return None
    return prefix or "<root>"


def validate_watch_checkpoint_record(
    record: Mapping[str, Any],
) -> Tuple[bool, str]:
    """Validate ONE current-schema watch checkpoint record fail-closed."""

    if not isinstance(record, Mapping):
        return False, _cpe.QUARANTINE_JSON_INVALID
    if record.get("checkpoint_record_kind") == QUARANTINED_CANDIDATE_RECORD_KIND:
        return _validate_quarantined_candidate_record(record)
    payload = {k: v for k, v in record.items() if k != "record_digest"}
    if set(payload) - set(_WATCH_ENTRY_FIELD_NAMES):
        return False, _cpe.QUARANTINE_SCHEMA_UNSUPPORTED
    mint = payload.get("token_mint")
    if not isinstance(mint, str) or not mint:
        return False, _cpe.QUARANTINE_MINT_BINDING_INVALID
    candidate_id = payload.get("candidate_id")
    if not isinstance(candidate_id, str) or not candidate_id:
        return False, _cpe.QUARANTINE_CANDIDATE_BINDING_INVALID
    status = payload.get("status")
    if status not in _WATCH_CHECKPOINT_ALLOWED_STATUSES:
        return False, _cpe.QUARANTINE_STATUS_UNSUPPORTED
    if not candidate_migration_is_admitted(payload) and status != WATCH_DROPPED_NON_PUMP:
        return False, _cpe.QUARANTINE_MINT_BINDING_INVALID
    if payload.get("admission_receipt") is not None and not validate_admission_receipt(
            payload["admission_receipt"], payload):
        return False, _cpe.QUARANTINE_MINT_BINDING_INVALID
    for field_name in _WATCH_DECIMAL_FIELDS:
        value = payload.get(field_name)
        if value is None:
            continue
        if not isinstance(value, str) or _decimal(value) is None:
            return False, _cpe.QUARANTINE_NUMERIC_INVALID
    for field_name in _WATCH_NONNEGATIVE_DECIMAL_FIELDS:
        value = payload.get(field_name)
        if value is None:
            continue
        parsed = _decimal(value, positive=False)
        if not isinstance(value, str) or parsed is None or parsed < 0:
            return False, _cpe.QUARANTINE_NUMERIC_INVALID
    expected_multiplier = _expected_activation_multiplier(payload)
    multiplier = payload.get("activation_multiplier", "1.20")
    if expected_multiplier is None or multiplier != _decimal_text(expected_multiplier):
        return False, _cpe.QUARANTINE_NUMERIC_INVALID
    if (payload.get("discovery_provenance") == DISCOVERY_PROVENANCE_DEX
            and not _backfill_evidence_is_valid(payload)):
        return False, _cpe.QUARANTINE_ACTIVATION_PROOF_INVALID
    for field_name in _WATCH_TIMESTAMP_FIELDS:
        value = payload.get(field_name)
        if value is None:
            continue
        if _utc(value) is None:
            return False, _cpe.QUARANTINE_TIMESTAMP_INVALID
    if _utc(payload.get("seeded_at_utc")) is None:
        return False, _cpe.QUARANTINE_TIMESTAMP_INVALID
    for field_name in _WATCH_INT_FIELDS:
        value = payload.get(field_name, 0)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            return False, _cpe.QUARANTINE_NUMERIC_INVALID
    for field_name in (
            "migration_slot", "backfill_lookback_seconds",
            "corroborated_migration_slot"):
        value = payload.get(field_name)
        if value is not None and (
                isinstance(value, bool) or not isinstance(value, int) or value < 0):
            return False, _cpe.QUARANTINE_NUMERIC_INVALID
    receipt_id = payload.get("delivery_receipt_message_id")
    if receipt_id is not None and (
            isinstance(receipt_id, bool) or not isinstance(receipt_id, int)):
        return False, _cpe.QUARANTINE_NUMERIC_INVALID
    for field_name in _WATCH_BOOL_FIELDS:
        value = payload.get(field_name, False)
        if not isinstance(value, bool):
            return False, _cpe.QUARANTINE_NUMERIC_INVALID
    if payload.get("migration_baseline_status", BASELINE_PENDING) not in (
            BASELINE_PENDING, BASELINE_CAPTURED, BASELINE_UNPROVEN_LEGACY):
        return False, _cpe.QUARANTINE_STATUS_UNSUPPORTED
    kind = payload.get("activation_evidence_kind")
    if kind is not None and kind not in ACTIVATION_EVIDENCE_KINDS + (
            ACTIVATION_KIND_LEGACY_MIGRATION,):
        return False, _cpe.QUARANTINE_STATUS_UNSUPPORTED
    source = payload.get("activation_evidence_source")
    if source is not None and source not in ACTIVATION_EVIDENCE_SOURCES:
        return False, _cpe.QUARANTINE_STATUS_UNSUPPORTED
    try:
        entry = WatchEntry(**payload)
    except TypeError:
        return False, _cpe.QUARANTINE_SCHEMA_UNSUPPORTED
    if entry.status != status:
        # __post_init__ refused to resume this state as written: the record
        # claims an activation/baseline the digest chain cannot prove.
        return False, _cpe.QUARANTINE_ACTIVATION_PROOF_INVALID
    if status in (WATCH_PENDING_1_20X, WATCH_ACTIVATED_WAITING, WATCH_ACTIVE_DIP):
        if payload.get("migration_baseline_status") != BASELINE_CAPTURED \
                or not entry._migration_baseline_digest_is_valid():
            return False, _cpe.QUARANTINE_ACTIVATION_PROOF_INVALID
    if status in (WATCH_ACTIVATED_WAITING, WATCH_ACTIVE_DIP):
        crossing = payload.get("activation_crossing_tick_digest")
        if not isinstance(crossing, str) or len(crossing) != 64:
            return False, _cpe.QUARANTINE_CROSSING_DIGEST_INVALID
        if not activation_proof_is_durable(entry):
            return False, _cpe.QUARANTINE_ACTIVATION_PROOF_INVALID
    if payload.get("delivery_state") == "DELIVERY_FAILED_RETRYABLE" \
            and _utc(payload.get("delivery_next_retry_at_utc")) is None:
        return False, _cpe.QUARANTINE_DELIVERY_STATE_INVALID
    if status == WATCH_SENT_OK_COMMITTED:
        if not isinstance(payload.get("delivery_receipt_digest"), str) \
                or not payload.get("delivery_receipt_digest") \
                or not isinstance(payload.get("delivery_ledger_key"), str) \
                or not payload.get("delivery_ledger_key"):
            return False, _cpe.QUARANTINE_DELIVERY_STATE_INVALID
    if status == WATCH_DELIVERY_UNKNOWN:
        # Required ambiguity evidence: the attempt identity, the recorded
        # failure classification, or (fa6022d-era checkpoints) the persisted
        # DELIVERY_UNKNOWN delivery_state marker itself.
        if not (isinstance(payload.get("delivery_attempt_id"), str)
                or isinstance(payload.get("delivery_last_failure_reason"), str)
                or payload.get("delivery_state") == WATCH_DELIVERY_UNKNOWN):
            return False, _cpe.QUARANTINE_DELIVERY_STATE_INVALID
    if payload.get("market_state") == READINESS_RECOVERY_BACKOFF:
        probe_at = _utc(payload.get("next_market_refresh_at_utc"))
        seeded_at = _utc(payload.get("seeded_at_utc"))
        if probe_at is None or (seeded_at is not None and probe_at < seeded_at):
            return False, _cpe.QUARANTINE_MARKET_STATE_INVALID
    return True, ""


def _classify_legacy_watch_text(
    text: str, raw: bytes
) -> Tuple[str, str, Any, Optional[str]]:
    """Classify a pre-envelope watch JSONL body (one record object per line).

    An empty file IS a valid, empty legacy checkpoint: the pre-envelope
    writer persisted an empty watchlist as zero bytes.
    """

    non_empty = [line for line in text.splitlines() if line.strip()]
    records: List[Dict[str, Any]] = []
    seen_mints: set = set()
    for index, line in enumerate(non_empty):
        try:
            value = _cpe.strict_json_loads(line)
        except ValueError:
            reason = (_cpe.QUARANTINE_TRUNCATED
                      if index == len(non_empty) - 1
                      else _cpe.QUARANTINE_JSON_INVALID)
            return (_cpe.FILE_INVALID, reason, None, None)
        if not isinstance(value, dict):
            return (_cpe.FILE_INVALID, _cpe.QUARANTINE_JSON_INVALID, None, None)
        mint = value.get("token_mint")
        if not isinstance(mint, str) or not mint:
            return (_cpe.FILE_INVALID, _cpe.QUARANTINE_MINT_BINDING_INVALID,
                    None, None)
        if mint in seen_mints:
            return (_cpe.FILE_INVALID, _cpe.QUARANTINE_DUPLICATE_RECORD,
                    None, None)
        seen_mints.add(mint)
        records.append(value)
    return (_cpe.FILE_VALID_LEGACY, "", records, WATCH_LEGACY_SCHEMA_VERSION)


def classify_watch_checkpoint_file(
    path: object, *, validation_now_utc: Optional[str] = None
) -> "_cpe.FileClassification":
    """Classify one watch checkpoint file under the shared envelope contract."""

    return _cpe.classify_checkpoint_file(
        path,
        kind=_cpe.CHECKPOINT_KIND_WATCH,
        supported_schema_versions=(WATCH_CHECKPOINT_SCHEMA_VERSION,),
        record_validator=validate_watch_checkpoint_record,
        identity_fn=watch_checkpoint_record_identity,
        legacy_classifier=_classify_legacy_watch_text,
        validation_now_utc=validation_now_utc,
    )


def verify_cross_checkpoint_consistency(
    watchlist: "Watchlist",
    ath_snapshots: object,
    *,
    now_utc: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Cross-checkpoint consistency after restore (PHX2-E2E-005).

    A watch candidate whose restored state claims a proven activation while
    the restored central ATH for the SAME mint is below its activation target
    is contradictory state. Contradictions are never auto-repaired by picking
    the convenient field: the candidate is quarantined for explicit operator
    resolution. Mints the ATH store does not carry are skipped (spot-only
    activation without central registration is legitimate).

    2026-08-02: the comparison reads the RESOLVED ATH market cap when the
    record carries one.  The raw ``ath_market_cap`` arm is maximized
    independently of ``ath_price``, so it can sit BELOW the true peak of the
    same record -- April was quarantined here with a resolved peak of
    ~$30,760 against a $32,980 target while its split arm read $27,483.
    A record whose resolved maximum is genuinely below its own activation
    target is still contradictory and is still quarantined."""

    findings: List[Dict[str, Any]] = []
    snapshots = ath_snapshots if isinstance(ath_snapshots, Mapping) else {}
    for entry in list(watchlist.all_entries()):
        if entry.status not in (WATCH_ACTIVATED_WAITING, WATCH_ACTIVE_DIP):
            continue
        snapshot = snapshots.get(entry.token_mint)
        if not isinstance(snapshot, Mapping):
            continue
        bound_mint = snapshot.get("token_mint")
        resolved_mc = (
            _decimal(snapshot.get("resolved_ath_market_cap"))
            if snapshot.get("resolved") is True else None)
        ath_mc = (resolved_mc if resolved_mc is not None
                  else _decimal(snapshot.get("ath_market_cap")))
        target = _decimal(entry.activation_target_market_cap_usd)
        issue: Optional[str] = None
        if isinstance(bound_mint, str) and bound_mint != entry.token_mint:
            issue = "ATH_RECORD_BOUND_TO_DIFFERENT_MINT"
        elif ath_mc is not None and target is not None and ath_mc < target:
            issue = "ACTIVATED_BUT_CENTRAL_ATH_BELOW_TARGET"
        if issue is None:
            continue
        watchlist.quarantine_candidate(
            entry.token_mint,
            reason=_cpe.QUARANTINE_CROSS_CONSISTENCY_INVALID,
            source_schema_version=WATCH_CHECKPOINT_SCHEMA_VERSION,
            legacy_payload=asdict(entry),
            quarantined_at_utc=now_utc,
        )
        findings.append({
            "kind": "PHX2_CROSS_CHECKPOINT_INCONSISTENCY",
            "token_mint": entry.token_mint,
            "candidate_id": entry.candidate_id,
            "issue": issue,
            "watch_status": entry.status,
            "activation_target_market_cap_usd": (
                entry.activation_target_market_cap_usd),
            "central_ath_market_cap": snapshot.get("ath_market_cap"),
            "central_ath_resolved_market_cap": snapshot.get(
                "resolved_ath_market_cap"),
            "central_ath_comparison_basis": (
                "RESOLVED_ATH_MARKET_CAP" if resolved_mc is not None
                else "RAW_ATH_MARKET_CAP"),
            "action": "CANDIDATE_QUARANTINED",
        })
    return findings


class Watchlist:
    """Mint-keyed watchlist with immutable activation state and atomic JSONL.

    ``max_size`` bounds *concurrently active* candidates (PHX2-E2E-002), never
    lifetime history: terminal candidates are archived into the append-only
    terminal-history artifact and release their slot. ``max_size=0`` is a
    valid explicit reject-all configuration; a negative size fails validation.
    """

    def __init__(
        self,
        *,
        max_size: int = 64,
        terminal_history: Optional[TerminalHistoryArchive] = None,
        terminal_history_path: object = None,
    ) -> None:
        size = int(max_size)
        if size < 0:
            raise ValueError("WATCHLIST_MAX_SIZE_NEGATIVE")
        self._entries: Dict[str, WatchEntry] = {}
        self._max_size = size
        if terminal_history is not None:
            self._terminal = terminal_history
        else:
            self._terminal = TerminalHistoryArchive(path=terminal_history_path)
        self._terminal_context_fn: Optional[Callable[["WatchEntry"], Any]] = None
        self._pending_terminal_at: Dict[str, str] = {}
        self._counters: Dict[str, int] = {
            "capacity_rejections": 0,
            "terminal_archive_succeeded": 0,
            "terminal_archive_failed": 0,
            "legacy_terminal_migrated": 0,
            "terminal_evicted_from_active": 0,
            # PHX2-E2E-004 legacy market-terminal restore accounting.
            "market_legacy_terminal_migrated": 0,
            "market_legacy_terminal_unclassified": 0,
            # PHX2-E2E-005 authenticated checkpoint accounting.
            "checkpoint_candidates_quarantined": 0,
            "checkpoint_legacy_activation_migrated": 0,
            "checkpoint_legacy_activation_quarantined": 0,
            "checkpoint_persist_refused": 0,
            "live_dex_corroborations": 0,
            "epoch_gap_candidates_closed": 0,
            # 2026-07-31 restart-state remediation accounting.
            "checkpoint_restored_active": 0,
            "checkpoint_restored_live_rebound": 0,
            "checkpoint_restored_diagnostic": 0,
            "post_boundary_candidates_admitted": 0,
            "pre_boundary_candidates_ignored": 0,
            "dex_diagnostic_records": 0,
            "checkpoint_mirror_write_failed": 0,
        }
        self._capacity_rejection_records: List[Dict[str, Any]] = []
        self._checkpoint_merge_conflicts: List[Dict[str, Any]] = []
        self._last_terminal_archive_error: Optional[str] = None
        # Bounded-retry checkpoint-write durability accounting (surfaced in
        # summary()/checkpoint_summary() -> heartbeat/status).
        self._checkpoint_write_metrics: Dict[str, Any] = {
            "checkpoint_write_attempted_total": 0,
            "checkpoint_write_succeeded_total": 0,
            "checkpoint_write_retried_total": 0,
            "checkpoint_write_retryable_failed_total": 0,
            "checkpoint_write_permanent_failed_total": 0,
            "checkpoint_write_retry_exhausted_total": 0,
            "checkpoint_last_success_utc": None,
            "checkpoint_last_failure_category": None,
            "checkpoint_durability_status": _cpe.CHECKPOINT_DURABILITY_HEALTHY,
            # Consecutive-failure accounting drives the health thresholds: a
            # single transient blip is DEGRADED, a structural failure is
            # immediately UNHEALTHY.
            "checkpoint_consecutive_failures": 0,
            "checkpoint_structural_failed_total": 0,
            # Safe, closed-set diagnostics for the LAST failure. The 2026-07-29
            # run persisted only the category, so 61 identical permanent
            # failures left nothing to diagnose from. Never candidate contents.
            "checkpoint_last_failure_detail": None,
            "checkpoint_last_verified_generation": 0,
            "checkpoint_durable_candidate_count": 0,
        }
        # PHX2-E2E-005: authenticated checkpoint state. Quarantined candidate
        # records are preserved raw (never normalized into WatchEntry), never
        # scheduled, never composed, and persist across restarts until an
        # explicit operator resolution.
        self._quarantined_candidates: Dict[str, Dict[str, Any]] = {}
        self._quarantine_lockdown = False
        self._checkpoint_result = _cpe.CheckpointLoadResult(
            checkpoint_kind=_cpe.CHECKPOINT_KIND_WATCH)
        self._checkpoint_generation = 0
        self._checkpoint_envelope_digest: Optional[str] = None
        self._checkpoint_created_at_utc: Optional[str] = None
        self._checkpoint_migration_history: List[Dict[str, Any]] = []
        # 2026-07-31 restart-state remediation.
        #
        # ``_mirror_path`` is an OPTIONAL read-only copy of the authoritative
        # checkpoint written beside the disposable run artifacts (dashboard,
        # paper tooling, run evidence). The authoritative pair lives in the
        # STABLE state directory; the mirror never participates in the
        # generation chain and is never restored from.
        self._mirror_path: Optional[Path] = None
        self._terminal_mirror_path: Optional[Path] = None
        # Mints restored from the authenticated checkpoint that still hold a
        # PRIOR live epoch id. This compatibility census is transient and
        # in-memory only; begin_live_only_epoch consumes it without rebinding.
        self._restored_live_pending: set = set()
        # Every active row restored from a prior process is diagnostic-only
        # until the new process opens its live-only epoch.  Keeping this set
        # separate from ``_restored_live_pending`` includes historical DEX
        # rows as well as old authenticated live rows.
        self._restored_eligibility_pending: set = set()
        self._admission_inbox: Optional[DurableAdmissionInbox] = None
        self._live_only_mode = False
        self._live_only_epoch_id: Optional[str] = None
        self._live_only_first_eligible_slot: Optional[int] = None

    # ---- centralized capacity accounting -----------------------------------

    @property
    def active_capacity(self) -> int:
        return self._max_size

    def active_count(self) -> int:
        """Concurrently active (capacity-holding) candidates: every in-map
        entry whose status is not terminal. Terminal entries awaiting an
        archive retry stay in the map for durability but hold no slot."""

        return sum(
            1 for e in self._entries.values()
            if not is_terminal_watch_state(e.status))

    def terminal_history_count(self) -> int:
        return self._terminal.count

    def total_observed_count(self) -> int:
        return len(self._entries) + self._terminal.count

    def counters(self) -> Dict[str, int]:
        return dict(self._counters)

    def capacity_rejection_records(self) -> List[Dict[str, Any]]:
        return list(self._capacity_rejection_records)

    def set_terminal_context_fn(
        self, context_fn: Optional[Callable[["WatchEntry"], Any]]
    ) -> None:
        """Optional read-only evidence hook: called once per terminal
        transition to enrich the archived record (latest ATH / tier / Fee
        Gate lifecycle / risk). Errors are contained; enrichment can never
        block or corrupt terminalization."""

        self._terminal_context_fn = context_fn

    # ---- terminal archive / eviction ---------------------------------------

    def _build_terminal_record(
        self, entry: WatchEntry, *, terminal_at_utc: str
    ) -> Dict[str, Any]:
        context: Dict[str, Any] = {}
        if self._terminal_context_fn is not None:
            try:
                supplied = self._terminal_context_fn(entry)
                if isinstance(supplied, Mapping):
                    context = dict(supplied)
            except Exception:
                context = {}
        return build_terminal_history_record(
            token_mint=entry.token_mint,
            candidate_id=entry.candidate_id,
            terminal_status=entry.status,
            terminal_reason=entry.last_reason,
            terminal_at_utc=terminal_at_utc,
            seeded_at_utc=entry.seeded_at_utc,
            migration_time_utc=entry.migration_time_utc,
            migration_proof_reference=entry.source_ref,
            baseline_market_cap_usd=entry.migration_market_cap_usd,
            baseline_source=entry.migration_market_cap_source,
            baseline_observed_at_utc=entry.migration_market_cap_observed_at_utc,
            baseline_status=entry.migration_baseline_status,
            activation_result=bool(entry.activation_proven),
            activated_at_utc=entry.activated_at_utc,
            activation_target_market_cap_usd=entry.activation_target_market_cap_usd,
            activation_proof_digest=entry.activation_proof_digest,
            market_state=entry.market_state,
            market_reason_code=entry.market_reason_code,
            delivery_state=entry.delivery_state,
            delivery_ledger_key=entry.delivery_ledger_key,
            delivery_receipt_digest=entry.delivery_receipt_digest,
            recheck_count=entry.recheck_count,
            context=context,
        )

    def _terminalize(
        self, entry: WatchEntry, *, terminal_at_utc: object, migrated: bool = False
    ) -> bool:
        """Atomic terminal transition: durably archive FIRST, only then evict
        the candidate from the active map. On archive failure the candidate
        stays in the map (and therefore in the durable checkpoint) with its
        terminal status — never counted as active, never silently discarded —
        and the archive append is retried on later ticks. The idempotent
        transition key guarantees a retry can never create a second row."""

        terminal_at = (
            terminal_at_utc if isinstance(terminal_at_utc, str) and terminal_at_utc
            else (entry.last_observed_at_utc or entry.seeded_at_utc))
        record = self._build_terminal_record(entry, terminal_at_utc=terminal_at)
        ok, outcome = self._terminal.archive(record)
        if not ok:
            self._counters["terminal_archive_failed"] += 1
            self._last_terminal_archive_error = outcome
            self._entries[entry.token_mint] = entry
            self._pending_terminal_at[entry.token_mint] = terminal_at
            return False
        if outcome == ARCHIVE_OUTCOME_ARCHIVED:
            self._counters["terminal_archive_succeeded"] += 1
        if migrated:
            # Migrated out of a legacy/mixed checkpoint: counted whether the
            # row is newly archived or an idempotent duplicate of a partially
            # completed earlier transition.
            self._counters["legacy_terminal_migrated"] += 1
        self._pending_terminal_at.pop(entry.token_mint, None)
        if entry.token_mint in self._entries:
            del self._entries[entry.token_mint]
            self._counters["terminal_evicted_from_active"] += 1
        elif migrated:
            # Restored checkpoint entry never entered the map; its eviction
            # from durable active state completes on the next persist().
            self._counters["terminal_evicted_from_active"] += 1
        self._last_terminal_archive_error = None
        return True

    def retry_pending_terminal_archives(self) -> int:
        """Retry archive appends for terminal entries still held in the map
        after an archive failure. Returns how many were released."""

        pending = [e for e in self._entries.values()
                   if is_terminal_watch_state(e.status)]
        released = 0
        for entry in pending:
            terminal_at = self._pending_terminal_at.get(
                entry.token_mint,
                entry.last_observed_at_utc or entry.seeded_at_utc)
            if self._terminalize(entry, terminal_at_utc=terminal_at):
                released += 1
        return released

    # ---- admission ---------------------------------------------------------

    def bind_admission_inbox(self, inbox: DurableAdmissionInbox) -> None:
        """Bind the stable owner before opening a new live epoch."""
        if not isinstance(inbox, DurableAdmissionInbox):
            raise TypeError("ADMISSION_INBOX_REQUIRED")
        self._admission_inbox = inbox
        for entry in self._entries.values():
            receipt = inbox.receipt_for(asdict(entry))
            if receipt is not None:
                entry.admission_receipt = receipt
            if self._entry_has_durable_admission(entry):
                self._restored_eligibility_pending.discard(entry.token_mint)
                self._restored_live_pending.discard(entry.token_mint)

    @staticmethod
    def _entry_has_durable_admission(entry: WatchEntry) -> bool:
        return validate_admission_receipt(entry.admission_receipt, asdict(entry))

    def pending_admission_candidates(self) -> List[Dict[str, Any]]:
        if self._admission_inbox is None:
            return []
        return [r["candidate"] for r in self._admission_inbox.pending()]

    def seed_pending_admission(
        self, receipt: Mapping[str, Any], *, seeded_at_utc: str
    ) -> Tuple[Optional[WatchEntry], str]:
        """Only a receipt still owned by the bound inbox can replay."""
        if (self._admission_inbox is None or not validate_admission_receipt(receipt)
                or self._admission_inbox.receipt_for(receipt["candidate"]) != receipt):
            return None, SEED_OUTCOME_INVALID
        return self.seed_with_outcome(dict(receipt["candidate"]),
                                      seeded_at_utc=seeded_at_utc)

    def seed_with_outcome(
        self, candidate: Dict[str, Any], *, seeded_at_utc: str
    ) -> Tuple[Optional[WatchEntry], str]:
        """Explicit-outcome admission. Capacity counts ONLY active candidates;
        a full watchlist rejects observably with
        ``ACTIVE_WATCH_CAPACITY_REACHED`` (never a silent drop)."""

        if self._quarantine_lockdown:
            # PHX2-E2E-005: an existing authoritative checkpoint is
            # quarantined. No admission and no silent fresh start until the
            # operator resolves the quarantine.
            return None, SEED_OUTCOME_CHECKPOINT_QUARANTINED
        mint = candidate.get("token_mint") if isinstance(candidate, dict) else None
        if not isinstance(mint, str) or not mint:
            return None, SEED_OUTCOME_INVALID
        if mint in self._quarantined_candidates:
            # A quarantined candidate is never resurrected by re-seeding.
            return None, SEED_OUTCOME_CHECKPOINT_QUARANTINED
        provenance = candidate.get("discovery_provenance") or DISCOVERY_PROVENANCE_LIVE
        if provenance not in DISCOVERY_PROVENANCES:
            return None, SEED_OUTCOME_INVALID
        if (provenance == DISCOVERY_PROVENANCE_DEX
                and not _backfill_evidence_is_valid(candidate)):
            return None, SEED_OUTCOME_INVALID
        receipt = (self._admission_inbox.receipt_for(candidate)
                   if self._admission_inbox is not None else None)
        if receipt is not None:
            # A restart must not grant an old candidate a fresh expiry clock.
            seeded_at_utc = (receipt["candidate"].get("local_observed_at_utc")
                             or receipt["candidate"]["discovery_utc"])
        if self._live_only_mode and receipt is None:
            if provenance == DISCOVERY_PROVENANCE_DEX:
                self.record_dex_diagnostic(candidate)
                return None, SEED_OUTCOME_DIAGNOSTIC_ONLY
            migration_slot = candidate.get("migration_slot")
            candidate_epoch = candidate.get("live_epoch_id")
            boundary = self._live_only_first_eligible_slot
            if (candidate_epoch != self._live_only_epoch_id
                    or boundary is None
                    or isinstance(migration_slot, bool)
                    or not isinstance(migration_slot, int)
                    or migration_slot < boundary):
                self._counters["pre_boundary_candidates_ignored"] += 1
                return None, SEED_OUTCOME_PRE_BOUNDARY
        existing = self._entries.get(mint)
        if existing is not None:
            if is_terminal_watch_state(existing.status):
                return existing, SEED_OUTCOME_TERMINAL_DUPLICATE
            if receipt is not None and validate_admission_receipt(receipt, asdict(existing)):
                existing.admission_receipt = receipt
            self.corroborate(candidate)
            return existing, SEED_OUTCOME_EXISTING
        if self._terminal.has_mint(mint):
            # Archived terminal history is never resurrected and never
            # consumes an active slot.
            return None, SEED_OUTCOME_TERMINAL_DUPLICATE
        non_pump = not candidate_migration_is_admitted(candidate)
        if not non_pump and self.active_count() >= self._max_size:
            self._counters["capacity_rejections"] += 1
            rejection = {
                "kind": "PHX2_WATCHLIST_CAPACITY_REJECTION",
                "reason": CAPACITY_REJECTION_REASON,
                "token_mint": mint,
                "candidate_id": str(candidate.get("candidate_id") or ""),
                "active_count": self.active_count(),
                "active_capacity": self._max_size,
                "observed_at_utc": seeded_at_utc,
            }
            self._capacity_rejection_records.append(rejection)
            del self._capacity_rejection_records[:-32]
            return None, SEED_OUTCOME_CAPACITY
        status = WATCH_PENDING_BASELINE if not non_pump else WATCH_DROPPED_NON_PUMP
        entry = WatchEntry(
            token_mint=mint,
            candidate_id=str(candidate.get("candidate_id") or ("b30_" + mint[:8])),
            migration_time_utc=candidate.get("migration_time_utc"),
            source_ref=candidate.get("source_ref"),
            seeded_at_utc=seeded_at_utc,
            symbol_or_name=candidate.get("symbol_or_name"),
            token_name=candidate.get("token_name"),
            discovery_provenance=provenance,
            discovery_utc=candidate.get("discovery_utc") or seeded_at_utc,
            live_epoch_id=candidate.get("live_epoch_id"),
            migration_slot=candidate.get("migration_slot"),
            migration_signature=candidate.get("migration_signature"),
            migration_proof=candidate.get("migration_proof"),
            admission_receipt=receipt,
            migration_evidence_class=candidate.get("migration_evidence_class"),
            pair_address=candidate.get("pair_address"),
            pool_dex_identity=candidate.get("pool_dex_identity"),
            ath_source=candidate.get("ath_source"),
            liquidity_source=candidate.get("liquidity_source"),
            # A legacy record persisted before the artifact-safe rename must not
            # re-emit the retired provider-named label into new artifacts.
            current_data_source=normalize_market_data_source(
                candidate.get("current_data_source")),
            backfill_lookback_seconds=candidate.get("backfill_lookback_seconds"),
            backfill_sweep_id=candidate.get("backfill_sweep_id"),
            source_confidence=candidate.get("source_confidence"),
            dedupe_identity=candidate.get("dedupe_identity") or ("mint:" + mint),
            corroborating_sources=list(candidate.get("corroborating_sources") or []),
            corroborated_live_epoch_id=candidate.get("corroborated_live_epoch_id"),
            corroborated_migration_slot=candidate.get("corroborated_migration_slot"),
            backfill_evidence_digest=candidate.get("backfill_evidence_digest"),
            backfill_market_observed_at_utc=candidate.get("backfill_market_observed_at_utc"),
            backfill_initial_price_usd=candidate.get("current_price_usd"),
            backfill_initial_market_cap_usd=candidate.get("current_market_cap_usd"),
            backfill_initial_liquidity_usd=candidate.get("liquidity_usd"),
            backfill_volume_m5_usd=candidate.get("volume_m5_usd"),
            backfill_volume_h1_usd=candidate.get("volume_h1_usd"),
            backfill_volume_h6_usd=candidate.get("volume_h6_usd"),
            backfill_volume_h24_usd=candidate.get("volume_h24_usd"),
            backfill_volume_fields_present=(candidate.get("volume_fields_present") is True),
            activation_multiplier=str(candidate.get("activation_multiplier") or (
                "1.39" if provenance == DISCOVERY_PROVENANCE_DEX else "1.20")),
            status=status,
            last_reason=("PENDING_MIGRATION_BASELINE"
                         if status == WATCH_PENDING_BASELINE else "DROPPED_NON_PUMP"),
        )
        if non_pump:
            # Dropped at admission: terminal at birth. Archived immediately;
            # holds no active slot and never blocks a later pump admission.
            self._terminalize(entry, terminal_at_utc=seeded_at_utc)
            return entry, SEED_OUTCOME_DROPPED_NON_PUMP
        event_mc = _decimal(candidate.get("migration_market_cap_usd"))
        event_price = _decimal(candidate.get("migration_market_cap_price"))
        event_supply = _decimal(candidate.get("migration_supply_at_observation"))
        event_at = candidate.get("migration_market_cap_observed_at_utc")
        source = candidate.get("migration_market_cap_source")
        migration_at = _utc(candidate.get("migration_time_utc"))
        baseline_at = _utc(event_at)
        same_event_window = bool(
            migration_at is not None and baseline_at is not None
            and abs((baseline_at - migration_at).total_seconds()) <= 120.0)
        if (provenance == DISCOVERY_PROVENANCE_DEX
                and event_mc is not None and event_price is not None
                and event_supply is not None and event_at is not None):
            entry._capture_baseline(
                market_cap=event_mc,
                source=BASELINE_SOURCE_DEX_BACKFILL,
                observed_at_utc=str(event_at),
                price=event_price,
                supply=event_supply,
            )
        elif (event_mc is not None and event_price is not None
                and event_supply is not None and same_event_window
                and source in (BASELINE_SOURCE_GRPC_EVENT,
                               "CHAINSTACK_GRPC_EVENT", "PAID_GRPC_PRIMARY")):
            entry._capture_baseline(
                market_cap=event_mc,
                source=BASELINE_SOURCE_GRPC_EVENT,
                observed_at_utc=str(event_at),
                price=event_price,
                supply=event_supply,
            )
        self._entries[mint] = entry
        if self._live_only_mode:
            self._counters["post_boundary_candidates_admitted"] += 1
        return entry, SEED_OUTCOME_ADMITTED

    def corroborate(self, candidate: Mapping[str, Any]) -> bool:
        """Record cross-source confirmation without changing first provenance."""

        mint = candidate.get("token_mint") if isinstance(candidate, Mapping) else None
        entry = self._entries.get(mint) if isinstance(mint, str) else None
        incoming = candidate.get("discovery_provenance") if isinstance(candidate, Mapping) else None
        if entry is None or not entry.is_active() or incoming not in DISCOVERY_PROVENANCES:
            return False
        if incoming == entry.discovery_provenance or incoming in entry.corroborating_sources:
            return False
        entry.corroborating_sources.append(incoming)
        if incoming in LIVE_DISCOVERY_PROVENANCES:
            entry.corroborated_live_epoch_id = candidate.get("live_epoch_id")
            slot = candidate.get("migration_slot")
            entry.corroborated_migration_slot = slot if isinstance(slot, int) else None
        self._counters["live_dex_corroborations"] += 1
        return True

    def restored_live_pending_mints(self) -> List[str]:
        """Mints restored from the checkpoint that still hold a prior epoch."""

        return sorted(self._restored_live_pending)

    def begin_live_only_epoch(
        self,
        current_epoch_id: str,
        *,
        first_eligible_slot: Optional[int],
        opened_at_utc: str,
    ) -> int:
        """Open a new empty eligibility domain for one process epoch.

        Authenticated checkpoint rows remain durable evidence, but a row
        restored by this process can never become a tracker in the new epoch.
        Its original epoch and migration slot are deliberately left unchanged
        before it is archived with the closed-set terminal classification
        ``PRE_BOUNDARY_NOT_ELIGIBLE``.
        """

        if not isinstance(current_epoch_id, str) or not current_epoch_id:
            return 0
        self._live_only_mode = True
        self._live_only_epoch_id = current_epoch_id
        self._live_only_first_eligible_slot = (
            int(first_eligible_slot)
            if isinstance(first_eligible_slot, int)
            and not isinstance(first_eligible_slot, bool)
            and first_eligible_slot > 0
            else None
        )
        retired = 0
        for mint in sorted(self._restored_eligibility_pending):
            entry = self._entries.get(mint)
            if entry is None or not entry.is_active():
                continue
            if self._entry_has_durable_admission(entry):
                continue
            entry.status = WATCH_REJECTED
            entry.last_reason = SEED_OUTCOME_PRE_BOUNDARY
            entry.last_observed_at_utc = opened_at_utc
            self._terminalize(entry, terminal_at_utc=opened_at_utc)
            retired += 1
        self._restored_eligibility_pending.clear()
        self._restored_live_pending.clear()
        self._counters["checkpoint_restored_diagnostic"] += retired
        self._counters["pre_boundary_candidates_ignored"] += retired
        return retired

    def update_live_only_epoch_boundary(
        self, current_epoch_id: str, first_eligible_slot: object
    ) -> bool:
        """Bind the authenticated first-eligible slot without changing rows."""

        if (not self._live_only_mode
                or current_epoch_id != self._live_only_epoch_id
                or isinstance(first_eligible_slot, bool)
                or not isinstance(first_eligible_slot, int)
                or first_eligible_slot <= 0):
            return False
        self._live_only_first_eligible_slot = int(first_eligible_slot)
        return True

    def record_dex_diagnostic(self, candidate: Mapping[str, Any]) -> str:
        """Count a historical DEX row without admitting or corroborating it."""

        if (not isinstance(candidate, Mapping)
                or candidate.get("discovery_provenance")
                != DISCOVERY_PROVENANCE_DEX):
            return SEED_OUTCOME_INVALID
        self._counters["dex_diagnostic_records"] += 1
        self._counters["pre_boundary_candidates_ignored"] += 1
        return SEED_OUTCOME_DIAGNOSTIC_ONLY

    def rebind_restored_live_entries(
        self, current_epoch_id: str, *, rebound_at_utc: str,
    ) -> int:
        """Compatibility surface: epoch rebinding is disabled in production.

        Callers must use :meth:`begin_live_only_epoch`, which retires restored
        eligibility while preserving the original epoch and migration slot.
        """

        return 0

    def close_live_epoch(self, epoch_id: str, *, closed_at_utc: str) -> int:
        """Make prior-epoch live candidates permanently ineligible."""

        return self._close_live_entries(
            lambda entry: entry.live_epoch_id == epoch_id,
            closed_at_utc=closed_at_utc,
        )

    def close_live_epochs_except(
        self, current_epoch_id: str, *, closed_at_utc: str
    ) -> int:
        """Enforce a fresh live-candidate set after any process restart."""

        return self._close_live_entries(
            lambda entry: entry.live_epoch_id != current_epoch_id,
            closed_at_utc=closed_at_utc,
        )

    def _close_live_entries(
        self, predicate: Callable[[WatchEntry], bool], *, closed_at_utc: str
    ) -> int:
        closed = 0
        for entry in list(self._entries.values()):
            if (entry.is_active()
                    and entry.discovery_provenance in LIVE_DISCOVERY_PROVENANCES
                    and not self._entry_has_durable_admission(entry)
                    and predicate(entry)):
                entry.status = WATCH_EXPIRED
                entry.last_reason = "LIVE_EPOCH_CLOSED"
                entry.last_observed_at_utc = closed_at_utc
                self._terminalize(entry, terminal_at_utc=closed_at_utc)
                closed += 1
        self._counters["epoch_gap_candidates_closed"] += closed
        return closed

    def seed(self, candidate: Dict[str, Any], *, seeded_at_utc: str) -> Optional[WatchEntry]:
        entry, _outcome = self.seed_with_outcome(candidate, seeded_at_utc=seeded_at_utc)
        return entry

    def get(self, mint: str) -> Optional[WatchEntry]:
        return self._entries.get(mint)

    def active_entries(self) -> List[WatchEntry]:
        return [e for e in self._entries.values() if e.is_active()]

    def tracked_entries(self) -> List[WatchEntry]:
        return self.active_entries()

    def active_dip_entries(self) -> List[WatchEntry]:
        return [e for e in self._entries.values() if e.is_dip_active()]

    def all_entries(self) -> List[WatchEntry]:
        return list(self._entries.values())

    def record_recheck(
        self,
        *,
        mint: str,
        reason: str,
        observed_at_utc: str,
        market_state: Optional[str] = None,
        market_reason_code: Optional[str] = None,
        next_market_refresh_at_utc: Optional[str] = None,
        market_attempt_count: Optional[int] = None,
        delivery_state: Optional[str] = None,
        delivery_failure_reason: Optional[str] = None,
        delivery_next_retry_at_utc: Optional[str] = None,
        delivery_retry_count: Optional[int] = None,
        delivery_attempt_id: Optional[str] = None,
        delivery_receipt_message_id: Optional[int] = None,
        delivery_receipt_digest: Optional[str] = None,
        delivery_ledger_key: Optional[str] = None,
    ) -> None:
        e = self._entries.get(mint)
        if e is None or not e.is_active():
            return
        e.recheck_count += 1
        e.last_reason = (
            WATCH_ACTIVATED_WAITING
            if (e.status == WATCH_ACTIVATED_WAITING
                and reason in (
                    "NO_SEND_ACTIVATED_WAITING_FOR_FRESH_MARKET",
                    "PENDING_FRESH_MARKET_OBSERVATION",
                    "NO_SEND_PENDING_FRESH_MARKET_OBSERVATION"))
            else reason)
        e.last_observed_at_utc = observed_at_utc
        if isinstance(market_state, str):
            e.market_state = market_state
        if isinstance(market_reason_code, str):
            e.market_reason_code = market_reason_code
        if isinstance(next_market_refresh_at_utc, str):
            e.next_market_refresh_at_utc = next_market_refresh_at_utc
        if isinstance(market_attempt_count, int) and not isinstance(market_attempt_count, bool):
            e.market_attempt_count = market_attempt_count
        if isinstance(delivery_state, str):
            e.delivery_state = delivery_state
        if isinstance(delivery_attempt_id, str):
            e.delivery_attempt_id = delivery_attempt_id
        if isinstance(delivery_receipt_message_id, int) \
                and not isinstance(delivery_receipt_message_id, bool):
            e.delivery_receipt_message_id = delivery_receipt_message_id
        if isinstance(delivery_receipt_digest, str):
            e.delivery_receipt_digest = delivery_receipt_digest
        if isinstance(delivery_ledger_key, str):
            e.delivery_ledger_key = delivery_ledger_key
        if reason == "SENT_OK_COMMITTED":
            # Terminal ONLY on confirmed committed delivery.
            e.status = WATCH_SENT_OK_COMMITTED
            e.delivery_state = WATCH_SENT_OK_COMMITTED
            e.delivery_next_retry_at_utc = None
            e.delivery_last_failure_reason = None
        elif reason == "DELIVERY_FAILED_RETRYABLE":
            # Explicit transport failure: the watch STAYS ACTIVE with bounded
            # retry metadata; the tier is NOT marked alerted.
            e.delivery_state = "DELIVERY_FAILED_RETRYABLE"
            e.delivery_attempt_count += 1
            if isinstance(delivery_retry_count, int) \
                    and not isinstance(delivery_retry_count, bool):
                e.delivery_retry_count = delivery_retry_count
            else:
                e.delivery_retry_count += 1
            if isinstance(delivery_failure_reason, str):
                e.delivery_last_failure_reason = delivery_failure_reason
            if isinstance(delivery_next_retry_at_utc, str):
                e.delivery_next_retry_at_utc = delivery_next_retry_at_utc
        elif reason == "DELIVERY_UNKNOWN":
            # Ambiguous outcome: observable, not success, not silently
            # retryable. Explicit reconciliation policy resolves it.
            e.status = WATCH_DELIVERY_UNKNOWN
            e.delivery_state = WATCH_DELIVERY_UNKNOWN
            if isinstance(delivery_failure_reason, str):
                e.delivery_last_failure_reason = delivery_failure_reason
        elif reason == "SEND_ATTEMPTED":
            # Legacy Build 30 lineage token only; the corrected production
            # engine never labels a failed delivery SEND_ATTEMPTED.
            e.status = WATCH_SEND_ATTEMPTED
        elif reason == "NOT_PUMP_SUFFIX":
            e.status = WATCH_DROPPED_NON_PUMP
        # Every other reason preserves the explicit activation state.
        if is_terminal_watch_state(e.status):
            # Terminal transition: archive durably, then release the slot.
            # DELIVERY_UNKNOWN is NOT terminal — it stays in the map holding
            # its slot until explicit operator reconciliation (fa6022d).
            self._terminalize(e, terminal_at_utc=observed_at_utc)

    def mark_dedupe_suppressed(
        self, mint: str, *, now_utc: Optional[str] = None
    ) -> None:
        e = self._entries.get(mint)
        if e is not None and e.is_active():
            e.status = WATCH_DEDUPE_SUPPRESSED
            self._terminalize(e, terminal_at_utc=now_utc)

    def expire_stale_entries(
        self,
        *,
        now_age_seconds_fn: Callable[[str], Optional[float]],
        max_age_seconds: int,
        max_rechecks: int,
        now_utc: Optional[str] = None,
    ) -> List[WatchEntry]:
        expired: List[WatchEntry] = []
        for e in list(self._entries.values()):
            if not e.is_active():
                continue
            age = now_age_seconds_fn(e.seeded_at_utc)
            if e.recheck_count >= max_rechecks or (age is not None and age >= max_age_seconds):
                e.status = WATCH_EXPIRED
                e.last_reason = (
                    "NEVER_REACHED_ACTIVATION_THRESHOLD"
                    if not e.activation_proven else "CANDIDATE_WATCH_EXPIRED")
                expired.append(e)
                # Expiration is a terminal transition: archive + release slot.
                self._terminalize(e, terminal_at_utc=now_utc)
        return expired

    def expire_stale(
        self,
        *,
        now_age_seconds_fn: Callable[[str], Optional[float]],
        max_age_seconds: int,
        max_rechecks: int,
        now_utc: Optional[str] = None,
    ) -> int:
        return len(self.expire_stale_entries(
            now_age_seconds_fn=now_age_seconds_fn,
            max_age_seconds=max_age_seconds,
            max_rechecks=max_rechecks,
            now_utc=now_utc,
        ))

    def summary(self) -> Dict[str, Any]:
        in_map_counts: Dict[str, int] = {}
        market_counts: Dict[str, int] = {}
        for e in self._entries.values():
            in_map_counts[e.status] = in_map_counts.get(e.status, 0) + 1
            if e.market_state:
                market_counts[e.market_state] = market_counts.get(e.market_state, 0) + 1
        # ``by_status`` stays the lifetime-observed per-status view (in-map
        # entries + archived terminal history) so downstream expired/sent
        # observability counters remain continuous across eviction.
        counts: Dict[str, int] = dict(in_map_counts)
        terminal_counts = self._terminal.by_status()
        for status, n in terminal_counts.items():
            counts[status] = counts.get(status, 0) + n
        tracked = sum(1 for e in self._entries.values() if e.is_active())
        active = self.active_count()
        live_candidates = sum(
            1 for e in self._entries.values()
            if e.is_active()
            and e.discovery_provenance in LIVE_DISCOVERY_PROVENANCES)
        dex_backfill_candidates = sum(
            1 for e in self._entries.values()
            if e.is_active()
            and e.discovery_provenance == DISCOVERY_PROVENANCE_DEX)
        historical_candidates_eligible = sum(
            1 for e in self._entries.values()
            if e.is_active() and self._live_only_mode
            and not self._entry_has_durable_admission(e)
            and (e.discovery_provenance == DISCOVERY_PROVENANCE_DEX
                 or e.live_epoch_id != self._live_only_epoch_id
                 or self._live_only_first_eligible_slot is None
                 or not isinstance(e.migration_slot, int)
                 or e.migration_slot < self._live_only_first_eligible_slot))
        return {
            "total": self.total_observed_count(),
            "total_observed": self.total_observed_count(),
            # WATCHLIST_COUNT is explicitly the active/tracked count — never
            # active plus historical terminal entries.
            "watchlist_count": tracked,
            "tracked": tracked,
            "active": active,
            "active_capacity": self._max_size,
            "active_capacity_remaining": max(0, self._max_size - active),
            "capacity_rejections": self._counters["capacity_rejections"],
            "live_candidates": live_candidates,
            "dex_backfill_candidates": dex_backfill_candidates,
            "live_only_epoch_mode": self._live_only_mode,
            "current_epoch_id": self._live_only_epoch_id,
            "current_epoch_boundary": self._live_only_first_eligible_slot,
            "post_boundary_candidates_admitted": self._counters[
                "post_boundary_candidates_admitted"],
            "pre_boundary_candidates_ignored": self._counters[
                "pre_boundary_candidates_ignored"],
            "restored_diagnostic_records": self._counters[
                "checkpoint_restored_diagnostic"],
            "dex_diagnostic_records": self._counters[
                "dex_diagnostic_records"],
            "dex_restart_backfill_mode": (
                "DIAGNOSTIC_ONLY" if self._live_only_mode else "LEGACY"),
            "historical_candidates_eligible": historical_candidates_eligible,
            "live_dex_corroborations": self._counters["live_dex_corroborations"],
            "epoch_gap_candidates_closed": self._counters["epoch_gap_candidates_closed"],
            "terminal_history": self._terminal.count,
            "terminal_by_status": terminal_counts,
            "terminal_pending_archive": sum(
                1 for e in self._entries.values()
                if is_terminal_watch_state(e.status)),
            "terminal_archive_succeeded": self._counters["terminal_archive_succeeded"],
            "terminal_archive_failed": self._counters["terminal_archive_failed"],
            "terminal_archive_last_error": self._last_terminal_archive_error,
            "legacy_terminal_migrated": self._counters["legacy_terminal_migrated"],
            "terminal_evicted_from_active": self._counters["terminal_evicted_from_active"],
            # PHX2-E2E-004 market-readiness recovery observability. Recovery
            # backoff is an ACTIVE, recoverable state — never a permanent failure.
            "market_recovery_backoff": market_counts.get(
                READINESS_RECOVERY_BACKOFF, 0),
            "market_ready": market_counts.get("MARKET_READY", 0),
            "market_legacy_terminal_migrated": self._counters[
                "market_legacy_terminal_migrated"],
            "market_legacy_terminal_unclassified": self._counters[
                "market_legacy_terminal_unclassified"],
            "pending_baseline": counts.get(WATCH_PENDING_BASELINE, 0),
            "pending_1_20x": counts.get(WATCH_PENDING_1_20X, 0),
            "activated": (
                sum(1 for e in self._entries.values() if e.activation_proven)
                + self._terminal.activated_count),
            "activated_waiting_for_fresh_market": counts.get(
                WATCH_ACTIVATED_WAITING, 0),
            "active_dip_watch": sum(1 for e in self._entries.values() if e.is_dip_active()),
            "sent": (counts.get(WATCH_SENT_OK_COMMITTED, 0)
                     + counts.get(WATCH_SEND_ATTEMPTED, 0)),
            "sent_committed": counts.get(WATCH_SENT_OK_COMMITTED, 0),
            "delivery_unknown": counts.get(WATCH_DELIVERY_UNKNOWN, 0),
            "delivery_retryable": sum(
                1 for e in self._entries.values()
                if e.is_active()
                and e.delivery_state == "DELIVERY_FAILED_RETRYABLE"),
            "live_activation_multiplier": _decimal_text(
                MIGRATION_ACTIVATION_MULTIPLIER),
            "dex_backfill_activation_multiplier": _decimal_text(
                BACKFILL_ACTIVATION_MULTIPLIER),
            # PHX2-E2E-005 authenticated checkpoint observability. A
            # quarantined checkpoint is NEVER displayed as an empty healthy
            # watchlist — consumers must branch on these fields first.
            "checkpoint_status": self._checkpoint_result.checkpoint_status,
            "checkpoint_quarantined": self._quarantine_lockdown,
            "checkpoint_quarantine_reason": (
                self._checkpoint_result.checkpoint_quarantine_reason),
            "checkpoint_quarantined_candidates": len(self._quarantined_candidates),
            "checkpoint_generation": self._checkpoint_generation,
            "checkpoint_schema_version": (
                self._checkpoint_result.checkpoint_schema_version),
            "checkpoint_recovered_from_backup": (
                self._checkpoint_result.checkpoint_recovered_from_backup),
            "checkpoint_legacy_activation_migrated": self._counters[
                "checkpoint_legacy_activation_migrated"],
            "checkpoint_legacy_activation_quarantined": self._counters[
                "checkpoint_legacy_activation_quarantined"],
            "checkpoint_persist_refused": self._counters[
                "checkpoint_persist_refused"],
            **self._checkpoint_write_metrics,
            "by_status": counts,
            "by_status_in_map": in_map_counts,
            "by_market_state": market_counts,
        }

    def _checkpoint_records(self) -> List[Dict[str, Any]]:
        """Canonical, digest-bearing record rows for the next generation."""

        rows: List[Dict[str, Any]] = []
        for entry in self._entries.values():
            payload = asdict(entry)
            payload["record_digest"] = _cpe.build_record_digest(
                _cpe.CHECKPOINT_KIND_WATCH, payload)
            rows.append(payload)
        for quarantined in self._quarantined_candidates.values():
            payload = {k: v for k, v in dict(quarantined).items()
                       if k != "record_digest"}
            payload["record_digest"] = _cpe.build_record_digest(
                _cpe.CHECKPOINT_KIND_WATCH, payload)
            rows.append(payload)
        rows.sort(key=lambda row: (str(row.get("candidate_id") or ""),
                                   str(row.get("token_mint") or "")))
        # Collapse same-mint records to ONE canonical record before the
        # document is built. Without this a second candidate_id binding an
        # already-tracked mint produced a document that failed its own
        # read-back validation with CHECKPOINT_DUPLICATE_RECORD -- permanently,
        # because the duplicate pair never resolved itself.
        canonical, conflicts = canonicalize_watch_checkpoint_records(rows)
        self._checkpoint_merge_conflicts = conflicts
        if conflicts:
            self._counters["checkpoint_canonical_merge_conflicts"] = (
                self._counters.get("checkpoint_canonical_merge_conflicts", 0)
                + len(conflicts))
        return canonical

    def persist(self, path: object) -> None:
        """Write one authenticated checkpoint generation (PHX2-E2E-005).

        The checkpoint holds candidates still requiring production action
        (active states, unresolved ``DELIVERY_UNKNOWN``), quarantined
        candidate records awaiting operator resolution, and terminal entries
        whose archive append failed and is still being retried — those are
        retried here FIRST so the terminal history is durably represented
        before the candidate leaves durable active state.

        Write order: build + validate in memory, canonical serialize, digest,
        temp-file + fsync, read back + full validation, preserve the previous
        VALID primary as the backup generation, atomic replace, confirm. The
        envelope header timestamps are write-receipt metadata and always use
        wall clock (deterministic migration anchors live in the payload). A
        quarantine lockdown REFUSES to write so the corrupt on-disk evidence
        is never replaced by an empty or guessed state.
        """

        if self._quarantine_lockdown:
            self._counters["checkpoint_persist_refused"] += 1
            return
        self.retry_pending_terminal_archives()
        p = Path(path)
        backup = p.with_suffix(p.suffix + ".bak")
        now_text = _cpe.utc_now_iso()
        created = self._checkpoint_created_at_utc or now_text
        records = self._checkpoint_records()
        header = _cpe.build_envelope_header(
            checkpoint_kind=_cpe.CHECKPOINT_KIND_WATCH,
            schema_version=WATCH_CHECKPOINT_SCHEMA_VERSION,
            payload_encoding=_cpe.PAYLOAD_ENCODING_JSONL,
            generation=self._checkpoint_generation + 1,
            record_digests=[str(row["record_digest"]) for row in records],
            created_at_utc=created,
            updated_at_utc=now_text,
            previous_generation_digest=self._checkpoint_envelope_digest,
            source_id=p.name,
            migration_history=self._checkpoint_migration_history,
        )
        # Bounded-retry tolerance for the transient Windows sharing-violation
        # class under sustained live load. persist() STILL raises on a
        # structural or retry-exhausted failure so the load/migration callers
        # keep their raise -> quarantine contract; the steady-state per-tick
        # caller (_finish_tick) tolerates that raise, mirroring the cursor.
        self._checkpoint_write_metrics["checkpoint_write_attempted_total"] += 1
        # Pre-write validation. Failing HERE preserves the prior valid
        # checkpoint untouched and, critically, records the exact safe reason:
        # the 2026-07-29 run persisted only the closed-set category, so 61
        # identical structural failures left nothing at all to diagnose.
        detail = describe_checkpoint_records(records)
        if detail is None and self._checkpoint_merge_conflicts:
            conflict = dict(self._checkpoint_merge_conflicts[0])
            detail = {
                "failure_category": _cpe.CHECKPOINT_FAILURE_STRUCTURAL,
                "reason": conflict.get("reason"),
                "record_index": conflict.get("record_index"),
                "field_path": "identity.mint",
                "record_identity_digest": conflict.get(
                    "record_identity_digest"),
                "duplicate_identity_type": conflict.get(
                    "duplicate_identity_type"),
                "schema_version": WATCH_CHECKPOINT_SCHEMA_VERSION,
                "candidate_count": len(records),
            }
        if detail is not None:
            exc = _cpe.CheckpointWriteError(
                "CHECKPOINT_WRITE_READBACK_INVALID:"
                + str(detail.get("reason") or "UNKNOWN"))
            self._note_checkpoint_write_failure(exc, detail=detail)
            raise exc
        try:
            outcome = _cpe.write_checkpoint_generation_resilient(
                primary_path=p,
                backup_path=backup,
                header=header,
                records=records,
                classify=classify_watch_checkpoint_file,
            )
        except (_cpe.CheckpointWriteError, OSError) as exc:
            self._note_checkpoint_write_failure(exc)
            raise
        self._note_checkpoint_write_success(outcome, now_text, records)
        self._checkpoint_generation = int(header["generation"])
        self._checkpoint_envelope_digest = str(header["envelope_digest"])
        self._checkpoint_created_at_utc = created
        # Transfer ownership only after the checkpoint writer verified the
        # committed generation. A failed inbox acknowledgement leaves a safe
        # duplicate pending for the next tick/restart, never missing work.
        if self._admission_inbox is not None:
            durable = []
            for receipt in self._admission_inbox.pending():
                candidate = receipt["candidate"]
                represented = any(validate_admission_receipt(receipt, record)
                                  for record in records)
                terminal = (self._terminal.path is not None and
                            self._terminal.has_mint(candidate["token_mint"]))
                if represented or terminal:
                    durable.append(receipt)
            self._admission_inbox.acknowledge_checkpoint(durable)
        self._write_mirror(p)

    def set_mirror_path(
        self, path: object, *, terminal_history_path: object = None,
    ) -> None:
        """Configure the read-only run-artifact copies of the durable state.

        The AUTHORITATIVE checkpoint pair lives in the stable state directory
        that survives per-run output-dir rotation. Dashboards, paper tooling,
        the run-artifact redaction scan and the offline selftests still expect
        ``watch_state.jsonl`` (and the terminal history) beside the run
        artifacts, so the exact bytes of each committed generation are copied
        there. A mirror equal to its source is ignored.
        """

        self._mirror_path = Path(path) if path is not None else None
        self._terminal_mirror_path = (
            Path(terminal_history_path)
            if terminal_history_path is not None else None)

    def _write_mirror(self, primary: Path) -> None:
        """Copy the just-committed durable state to the run-artifact mirrors.

        Best-effort by design and DISCLOSED via a counter: the mirror is
        telemetry, so a failure here must never fail a durable write that
        already succeeded, and must never be silent either.
        """

        self._copy_mirror(primary, self._mirror_path)
        self._copy_mirror(
            self._terminal.path, getattr(self, "_terminal_mirror_path", None))

    def _copy_mirror(
        self, source: Optional[Path], mirror: Optional[Path],
    ) -> None:
        if mirror is None or source is None:
            return
        try:
            same = source.resolve() == mirror.resolve()
        except OSError:
            same = str(source) == str(mirror)
        if same:
            return
        try:
            if not source.exists():
                return
            payload = source.read_bytes()
            mirror.parent.mkdir(parents=True, exist_ok=True)
            temp = mirror.with_name(mirror.name + ".mirror.tmp")
            with temp.open("wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(str(temp), str(mirror))
        except OSError:
            self._counters["checkpoint_mirror_write_failed"] += 1

    def _note_checkpoint_write_success(
        self, outcome, now_text, records=None,
    ) -> None:
        m = self._checkpoint_write_metrics
        m["checkpoint_write_succeeded_total"] += 1
        m["checkpoint_write_retried_total"] += outcome.retried
        m["checkpoint_write_retryable_failed_total"] += outcome.transient_failures
        m["checkpoint_last_success_utc"] = now_text
        m["checkpoint_durability_status"] = _cpe.CHECKPOINT_DURABILITY_HEALTHY
        # Durability telemetry advances only AFTER the write was verified.
        m["checkpoint_consecutive_failures"] = 0
        m["checkpoint_last_failure_detail"] = None
        m["checkpoint_last_verified_generation"] = int(
            self._checkpoint_generation) + 1
        if records is not None:
            m["checkpoint_durable_candidate_count"] = len(records)

    def _note_checkpoint_write_failure(self, exc, detail=None) -> None:
        m = self._checkpoint_write_metrics
        category = _cpe.classify_checkpoint_write_error(exc)
        m["checkpoint_last_failure_category"] = category
        m["checkpoint_write_permanent_failed_total"] += 1
        m["checkpoint_write_retry_exhausted_total"] += 1
        m["checkpoint_consecutive_failures"] += 1
        if category == _cpe.CHECKPOINT_FAILURE_STRUCTURAL:
            m["checkpoint_structural_failed_total"] += 1
        if detail is not None:
            m["checkpoint_last_failure_detail"] = dict(detail)
        m["checkpoint_durability_status"] = (
            _cpe.CHECKPOINT_DURABILITY_DEGRADED)

    @staticmethod
    def _decode_lines(text: str) -> List[WatchEntry]:
        entries: List[WatchEntry] = []
        for raw in text.splitlines():
            line = raw.strip()
            if not line:
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError("watch checkpoint record must be an object")
            entries.append(WatchEntry(**value))
        return entries

    def _migrate_legacy_market_readiness(
        self, entry: "WatchEntry", now_utc: Optional[str]
    ) -> None:
        """PHX2-E2E-004: convert a restored legacy market-terminal state.

        The watch ``status`` is authoritative for capacity/scheduling; a
        candidate in market recovery is active by its status and keeps its slot.
        This only repairs the market-readiness TELEMETRY carried on the entry so
        a legacy ``MARKET_UNAVAILABLE`` that the old code left permanent restores
        as a visible, recoverable ``MARKET_RECOVERY_BACKOFF`` — never silently
        dead, and never silently guessed when ambiguous."""

        migratable, marker = classify_legacy_market_state(
            entry.market_state, entry.market_reason_code)
        if migratable:
            base = now_utc or entry.last_observed_at_utc or entry.seeded_at_utc
            probe_at = base
            try:
                anchor = datetime.fromisoformat(str(base).replace("Z", "+00:00"))
                if anchor.tzinfo is None:
                    anchor = anchor.replace(tzinfo=timezone.utc)
                probe_at = (
                    anchor.astimezone(timezone.utc)
                    + timedelta(seconds=_LEGACY_RECOVERY_PROBE_DELAY_SECONDS)
                ).strftime("%Y-%m-%dT%H:%M:%SZ")
            except (TypeError, ValueError):
                probe_at = base
            entry.market_state = READINESS_RECOVERY_BACKOFF
            entry.market_reason_code = marker
            entry.next_market_refresh_at_utc = probe_at
            entry.market_legacy_terminal_migrated = True
            self._counters["market_legacy_terminal_migrated"] += 1
        elif marker == READINESS_LEGACY_UNCLASSIFIED:
            # Ambiguous legacy terminal: fail closed VISIBLY. Do not guess it
            # into recovery; preserve the terminal market_state and flag it for
            # the checkpoint-remediation task (PHX2-E2E-005).
            entry.market_reason_code = marker
            self._counters["market_legacy_terminal_unclassified"] += 1

    # ---- authenticated checkpoint restore (PHX2-E2E-005) -------------------

    @property
    def checkpoint(self) -> "_cpe.CheckpointLoadResult":
        return self._checkpoint_result

    @property
    def checkpoint_quarantined(self) -> bool:
        return self._quarantine_lockdown

    def checkpoint_summary(self) -> Dict[str, Any]:
        out = self._checkpoint_result.as_dict()
        out["checkpoint_quarantined_candidates"] = len(
            self._quarantined_candidates)
        out["checkpoint_persist_refused"] = self._counters[
            "checkpoint_persist_refused"]
        # Restart-state remediation telemetry (2026-07-31).
        out["checkpoint_restored_active"] = self._counters[
            "checkpoint_restored_active"]
        out["checkpoint_restored_live_rebound"] = self._counters[
            "checkpoint_restored_live_rebound"]
        out["checkpoint_restored_live_pending"] = len(
            self._restored_live_pending)
        out["checkpoint_restored_diagnostic"] = self._counters[
            "checkpoint_restored_diagnostic"]
        out["historical_candidates_eligible"] = sum(
            1 for entry in self._entries.values()
            if entry.is_active() and self._live_only_mode
            and not self._entry_has_durable_admission(entry)
            and (entry.discovery_provenance == DISCOVERY_PROVENANCE_DEX
                 or entry.live_epoch_id != self._live_only_epoch_id))
        out["checkpoint_mirror_write_failed"] = self._counters[
            "checkpoint_mirror_write_failed"]
        # Boolean only: filesystem paths are never placed in an artifact.
        out["checkpoint_mirror_configured"] = self._mirror_path is not None
        out.update(self._checkpoint_write_metrics)
        return out

    def quarantined_candidate_records(self) -> Dict[str, Dict[str, Any]]:
        return {mint: dict(record)
                for mint, record in self._quarantined_candidates.items()}

    def quarantine_candidate(
        self,
        mint: str,
        *,
        reason: str,
        source_schema_version: str = WATCH_CHECKPOINT_SCHEMA_VERSION,
        legacy_payload: Optional[Mapping[str, Any]] = None,
        legacy_record_digest: Optional[str] = None,
        legacy_checkpoint_digest: Optional[str] = None,
        quarantined_at_utc: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Move one candidate into the durable quarantine set.

        A quarantined candidate never schedules, composes, reserves, sends,
        or mutates the successful-send ledger; its evidence payload persists
        unchanged in every later checkpoint generation until an explicit
        operator resolution."""

        entry = self._entries.pop(mint, None)
        if isinstance(legacy_payload, Mapping):
            payload: Dict[str, Any] = _sanitize_checkpoint_value(
                dict(legacy_payload))
        elif entry is not None:
            payload = asdict(entry)
        else:
            payload = {}
        record = {
            "checkpoint_record_kind": QUARANTINED_CANDIDATE_RECORD_KIND,
            "token_mint": mint,
            "candidate_id": str(payload.get("candidate_id") or ""),
            "quarantine_reason": (
                reason if reason in _cpe.QUARANTINE_REASONS
                else _cpe.QUARANTINE_MIGRATION_AMBIGUOUS),
            "source_schema_version": source_schema_version,
            "legacy_record_digest": legacy_record_digest,
            "legacy_checkpoint_digest": legacy_checkpoint_digest,
            "quarantined_at_utc": (
                quarantined_at_utc if isinstance(quarantined_at_utc, str)
                and _utc(quarantined_at_utc) is not None
                else _cpe.utc_now_iso()),
            "legacy_payload": payload,
        }
        self._quarantined_candidates[mint] = record
        self._counters["checkpoint_candidates_quarantined"] += 1
        return record

    def _restore_active_entry(
        self, entry: WatchEntry, now_utc: Optional[str],
        *, source_schema_version: str,
        legacy_record_digest: Optional[str] = None,
        legacy_checkpoint_digest: Optional[str] = None,
        quarantined_at_utc: Optional[str] = None,
    ) -> Tuple[bool, Optional[str]]:
        """Insert one restored active entry, guarding terminal consistency.

        A mint whose terminal history already records a send-family terminal
        outcome (SENT_OK_COMMITTED / SEND_ATTEMPTED / DEDUPE_SUPPRESSED) must
        never restore as active — that is an alert-replay generation
        conflict and quarantines. The EXPIRED-family crash window (archive
        succeeded, checkpoint rewrite did not) restores active exactly as
        before: re-expiry is idempotent and can never duplicate history."""

        prior_terminal = self._terminal.status_for_mint(entry.token_mint)
        if prior_terminal in (WATCH_SENT_OK_COMMITTED, WATCH_SEND_ATTEMPTED,
                              WATCH_DEDUPE_SUPPRESSED):
            self.quarantine_candidate(
                entry.token_mint,
                reason=_cpe.QUARANTINE_GENERATION_CONFLICT,
                source_schema_version=source_schema_version,
                legacy_payload=asdict(entry),
                legacy_record_digest=legacy_record_digest,
                legacy_checkpoint_digest=legacy_checkpoint_digest,
                quarantined_at_utc=quarantined_at_utc,
            )
            return False, _cpe.QUARANTINE_GENERATION_CONFLICT
        self._migrate_legacy_market_readiness(entry, now_utc)
        self._entries[entry.token_mint] = entry
        self._counters["checkpoint_restored_active"] += 1
        self._restored_eligibility_pending.add(entry.token_mint)
        if entry.discovery_provenance in LIVE_DISCOVERY_PROVENANCES:
            # Compatibility census only. Production retires these as
            # diagnostics before discovery merges anything.
            self._restored_live_pending.add(entry.token_mint)
        return True, None

    @staticmethod
    def _legacy_activation_evidence(
        record: Mapping[str, Any],
    ) -> Tuple[bool, str]:
        """Decide whether an old-schema active watch carries enough
        authenticated evidence to prove its historical activation."""

        mint = record.get("token_mint")
        candidate_id = record.get("candidate_id")
        baseline = _decimal(record.get("migration_market_cap_usd"))
        target = _decimal(record.get("activation_target_market_cap_usd"))
        evidence_mc = _decimal(record.get("activation_current_market_cap_usd"))
        baseline_at = _utc(record.get("migration_market_cap_observed_at_utc"))
        activated_at = _utc(record.get("activated_at_utc"))
        source = record.get("activation_observation_source")
        if record.get("activation_proof_digest") is not None \
                or record.get("activation_evidence_digest") is not None:
            # The record CLAIMS a current-schema proof that did not validate.
            # Deriving a migration proof over contradicted evidence would be
            # guessing — quarantine instead.
            return False, "LEGACY_RECORD_CARRIES_INVALID_CURRENT_PROOF"
        if record.get("legacy_activation_unproven") is True:
            return False, "LEGACY_ACTIVATION_UNPROVEN"
        if record.get("activation_proven") is not True:
            return False, "LEGACY_ACTIVATION_NOT_PROVEN"
        if record.get("migration_baseline_status") != BASELINE_CAPTURED:
            return False, "LEGACY_BASELINE_NOT_CAPTURED"
        if record.get("activation_multiplier") != _decimal_text(
                MIGRATION_ACTIVATION_MULTIPLIER):
            return False, "LEGACY_MULTIPLIER_MISMATCH"
        if not candidate_migration_is_admitted(record) \
                or not isinstance(candidate_id, str) or not candidate_id:
            return False, "LEGACY_IDENTITY_INVALID"
        if baseline is None or target is None or evidence_mc is None:
            return False, "LEGACY_NUMERIC_EVIDENCE_MISSING"
        if target != baseline * MIGRATION_ACTIVATION_MULTIPLIER:
            return False, "LEGACY_TARGET_MISMATCH"
        if evidence_mc < target:
            return False, "LEGACY_EVIDENCE_BELOW_TARGET"
        if baseline_at is None or activated_at is None \
                or activated_at <= baseline_at:
            return False, "LEGACY_TIMESTAMP_ORDER_INVALID"
        if source not in ACTIVATION_EVIDENCE_SOURCES:
            return False, "LEGACY_SOURCE_DISALLOWED"
        if _decimal(record.get("migration_market_cap_price")) is None:
            return False, "LEGACY_BASELINE_PRICE_MISSING"
        supply = record.get("migration_supply_at_observation")
        if supply is not None and _decimal(supply) is None:
            return False, "LEGACY_BASELINE_SUPPLY_INVALID"
        return True, ""

    def _apply_legacy_activation_migration(
        self, entry: WatchEntry, record: Mapping[str, Any],
        *, legacy_record_digest: str, legacy_checkpoint_digest: str,
        performed_at_utc: str,
    ) -> None:
        """Derive the migration activation proof from proven legacy fields.

        Numeric state (baseline, target, evidence market cap) is preserved
        EXACTLY; nothing the old schema did not contain is fabricated. The
        candidate resumes as ``ACTIVATED_WAITING_FOR_FRESH_MARKET``: the
        migration event itself can never compose, reserve, or send, and tier
        evaluation requires a genuinely later fresh market tick."""

        mint = str(record.get("token_mint"))
        candidate_id = str(record.get("candidate_id"))
        activated_at = str(record.get("activated_at_utc"))
        source = str(record.get("activation_observation_source"))
        evidence_mc = _decimal(record.get("activation_current_market_cap_usd"))
        assert evidence_mc is not None
        entry.migration_baseline_digest_version = (
            MIGRATION_BASELINE_DIGEST_SCHEMA_VERSION)
        entry.migration_baseline_digest = build_migration_baseline_digest(
            token_mint=mint,
            candidate_id=candidate_id,
            market_cap_usd=entry.migration_market_cap_usd,
            observed_at_utc=entry.migration_market_cap_observed_at_utc,
            source=entry.migration_market_cap_source,
            price=entry.migration_market_cap_price,
            supply=entry.migration_supply_at_observation,
        )
        source_digest = build_legacy_activation_source_evidence_digest(
            token_mint=mint,
            candidate_id=candidate_id,
            market_cap_usd=_decimal_text(evidence_mc),
            event_at_utc=activated_at,
            source=source,
        )
        crossing_digest = build_legacy_migration_crossing_digest(
            token_mint=mint,
            candidate_id=candidate_id,
            legacy_record_digest=legacy_record_digest,
            activated_at_utc=activated_at,
            market_cap_usd=_decimal_text(evidence_mc),
        )
        entry.status = WATCH_ACTIVATED_WAITING
        entry.activated_at_utc = activated_at
        entry.activation_observation_source = source
        entry.activation_current_market_cap_usd = _decimal_text(evidence_mc)
        entry.activation_observation_fresh = False
        entry.activation_proven = True
        entry.activation_evidence_source = source
        entry.activation_evidence_market_cap_usd = _decimal_text(evidence_mc)
        entry.activation_evidence_event_at_utc = activated_at
        entry.activation_evidence_ingested_at_utc = activated_at
        entry.activation_evidence_digest = source_digest
        entry.activation_source_evidence_digest = source_digest
        entry.activation_evidence_version = (
            ACTIVATION_LEGACY_MIGRATION_EVIDENCE_VERSION)
        entry.activation_observation_seal_version = (
            ATH_OBSERVATION_SEAL_SCHEMA_VERSION)
        entry.activation_observation_seal_digest = (
            build_ath_observation_seal_digest(mint, {
                "ath_evidence_digest": source_digest,
                "ath_ingested_at_utc": activated_at,
                "ath_observation_seal_validated": True,
            }))
        entry.activation_evidence_kind = ACTIVATION_KIND_LEGACY_MIGRATION
        entry.activation_migrated_from_schema = WATCH_LEGACY_SCHEMA_VERSION
        entry.activation_migration_performed_at_utc = performed_at_utc
        entry.activation_legacy_record_digest = legacy_record_digest
        entry.activation_legacy_checkpoint_digest = legacy_checkpoint_digest
        entry.activation_crossing_tick_digest = crossing_digest
        entry.activation_crossing_tick_blocked = True
        entry.activation_latched = True
        entry.legacy_activation_unproven = False
        entry.activation_proof_version = ACTIVATION_LEGACY_MIGRATION_PROOF_VERSION
        entry.activation_proof_digest = build_legacy_activation_migration_proof_digest(
            token_mint=mint,
            candidate_id=candidate_id,
            legacy_checkpoint_digest=legacy_checkpoint_digest,
            legacy_record_digest=legacy_record_digest,
            migration_baseline_digest=entry.migration_baseline_digest,
            migration_market_cap_usd=entry.migration_market_cap_usd,
            migration_market_cap_observed_at_utc=(
                entry.migration_market_cap_observed_at_utc),
            activation_target_market_cap_usd=(
                entry.activation_target_market_cap_usd),
            activation_evidence_market_cap_usd=(
                entry.activation_evidence_market_cap_usd),
            activated_at_utc=activated_at,
            activation_evidence_source=source,
            activation_migrated_from_schema=WATCH_LEGACY_SCHEMA_VERSION,
            activation_migration_performed_at_utc=performed_at_utc,
            activation_crossing_tick_digest=crossing_digest,
        )
        entry.last_reason = "ACTIVATION_MIGRATED_FROM_LEGACY_CHECKPOINT"

    def _migrate_legacy_watch_records(
        self,
        records: Sequence[Mapping[str, Any]],
        *,
        checkpoint_digest: str,
        performed_at_utc: str,
        now_utc: Optional[str],
        result: "_cpe.CheckpointLoadResult",
    ) -> None:
        """Deterministic per-candidate legacy JSONL migration."""

        report = result.checkpoint_migration_report
        for record in records:
            mint = str(record.get("token_mint"))
            status = record.get("status")
            legacy_record_digest = hashlib.sha256(json.dumps(
                dict(record), sort_keys=True, separators=(",", ":"),
                ensure_ascii=True).encode("utf-8")).hexdigest()
            row: Dict[str, Any] = {
                "token_mint": mint,
                "candidate_id": str(record.get("candidate_id") or ""),
                "source_schema_version": WATCH_LEGACY_SCHEMA_VERSION,
                "source_status": status,
                "source_baseline_market_cap_usd": record.get(
                    "migration_market_cap_usd"),
                "legacy_record_digest": legacy_record_digest,
            }

            def _quarantine(reason: str, detail: str = "") -> None:
                self.quarantine_candidate(
                    mint,
                    reason=reason,
                    source_schema_version=WATCH_LEGACY_SCHEMA_VERSION,
                    legacy_payload=record,
                    legacy_record_digest=legacy_record_digest,
                    legacy_checkpoint_digest=checkpoint_digest,
                    quarantined_at_utc=performed_at_utc,
                )
                result.checkpoint_records_rejected += 1
                row["migration_result"] = "QUARANTINED"
                row["quarantine_reason"] = reason
                if detail:
                    row["quarantine_detail"] = detail
                report.append(row)

            if status not in _WATCH_LEGACY_KNOWN_STATUSES:
                _quarantine(_cpe.QUARANTINE_LEGACY_STATUS_UNSUPPORTED)
                continue
            unknown_fields = set(record) - set(_WATCH_ENTRY_FIELD_NAMES)
            if unknown_fields:
                _quarantine(_cpe.QUARANTINE_MIGRATION_AMBIGUOUS,
                            "UNSUPPORTED_LEGACY_FIELDS")
                continue
            try:
                entry = WatchEntry(**dict(record))
            except (TypeError, ValueError):
                _quarantine(_cpe.QUARANTINE_MIGRATION_AMBIGUOUS,
                            "LEGACY_RECORD_UNCONSTRUCTIBLE")
                continue
            if is_terminal_watch_state(entry.status):
                self._terminalize(
                    entry,
                    terminal_at_utc=(
                        entry.last_observed_at_utc or entry.seeded_at_utc),
                    migrated=True,
                )
                result.checkpoint_records_validated += 1
                row["migration_result"] = "ARCHIVED_TERMINAL"
                report.append(row)
                continue
            if status in (WATCH_ACTIVATED, WATCH_ACTIVATED_WAITING,
                          WATCH_ACTIVE_DIP) and entry.status != status:
                # The old schema lacked the current activation proof and the
                # constructor downgraded it: this is the explicit legacy
                # activation migration path.
                sufficient, detail = self._legacy_activation_evidence(record)
                if not sufficient:
                    self._counters[
                        "checkpoint_legacy_activation_quarantined"] += 1
                    _quarantine(
                        _cpe.QUARANTINE_ACTIVATION_MIGRATION_AMBIGUOUS, detail)
                    continue
                try:
                    self._apply_legacy_activation_migration(
                        entry, record,
                        legacy_record_digest=legacy_record_digest,
                        legacy_checkpoint_digest=checkpoint_digest,
                        performed_at_utc=performed_at_utc,
                    )
                    migrated_ok = activation_proof_is_durable(entry)
                except (TypeError, ValueError):
                    migrated_ok = False
                if not migrated_ok:
                    self._counters[
                        "checkpoint_legacy_activation_quarantined"] += 1
                    _quarantine(
                        _cpe.QUARANTINE_ACTIVATION_MIGRATION_AMBIGUOUS,
                        "LEGACY_MIGRATION_PROOF_UNVERIFIABLE")
                    continue
                self._counters["checkpoint_legacy_activation_migrated"] += 1
                row["activation_migration"] = (
                    "LEGACY_AUTHENTICATED_ACTIVATION_MIGRATION")
                row["requires_later_fresh_tick"] = True
            elif entry.status in (WATCH_ACTIVATED_WAITING, WATCH_ACTIVE_DIP):
                # A complete, valid current-schema proof stored in the
                # pre-envelope JSONL: restore exactly.
                row["activation_migration"] = "CURRENT_PROOF_PRESERVED"
            else:
                if entry.migration_baseline_status == BASELINE_CAPTURED:
                    if entry.migration_baseline_digest is None:
                        try:
                            entry.migration_baseline_digest = (
                                build_migration_baseline_digest(
                                    token_mint=entry.token_mint,
                                    candidate_id=entry.candidate_id,
                                    market_cap_usd=entry.migration_market_cap_usd,
                                    observed_at_utc=(
                                        entry.migration_market_cap_observed_at_utc),
                                    source=entry.migration_market_cap_source,
                                    price=entry.migration_market_cap_price,
                                    supply=entry.migration_supply_at_observation,
                                ))
                            entry.migration_baseline_digest_version = (
                                MIGRATION_BASELINE_DIGEST_SCHEMA_VERSION)
                        except (TypeError, ValueError):
                            _quarantine(_cpe.QUARANTINE_MIGRATION_AMBIGUOUS,
                                        "LEGACY_BASELINE_UNPROVABLE")
                            continue
                    elif not entry._migration_baseline_digest_is_valid():
                        _quarantine(_cpe.QUARANTINE_MIGRATION_AMBIGUOUS,
                                    "LEGACY_BASELINE_DIGEST_INVALID")
                        continue
            restored, conflict = self._restore_active_entry(
                entry, now_utc,
                source_schema_version=WATCH_LEGACY_SCHEMA_VERSION,
                legacy_record_digest=legacy_record_digest,
                legacy_checkpoint_digest=checkpoint_digest,
                quarantined_at_utc=performed_at_utc,
            )
            if restored:
                result.checkpoint_records_validated += 1
                row["migration_result"] = "RESTORED_ACTIVE"
                row["current_status"] = entry.status
            else:
                result.checkpoint_records_rejected += 1
                row["migration_result"] = "QUARANTINED"
                row["quarantine_reason"] = conflict
            report.append(row)

    @classmethod
    def load(
        cls,
        path: object,
        *,
        max_size: int = 64,
        terminal_history: Optional[TerminalHistoryArchive] = None,
        terminal_history_path: object = None,
        now_utc: Optional[str] = None,
        validation_now_utc: Optional[str] = None,
        mirror_path: object = None,
        terminal_history_mirror_path: object = None,
    ) -> "Watchlist":
        """Restore a checkpoint through the authenticated envelope contract.

        Load decision matrix (PHX2-E2E-005): a valid current checkpoint
        restores exactly; a valid supported legacy checkpoint migrates
        deterministically (preserving economic state, writing the current
        schema); corrupt, tampered, or unsupported state NEVER silently
        returns empty — the watchlist enters quarantine lockdown, refuses
        admissions, refuses persistence, and preserves the original files
        unchanged for inspection.

        Active/recoverable entries restore into the active map (ALL of them —
        an over-capacity checkpoint is preserved fail-closed and simply
        blocks new admissions until slots free). Terminal entries are
        migrated idempotently into the terminal archive and never recreate
        active-capacity pressure.

        PHX2-E2E-004: an active entry whose persisted market-readiness state is
        a legacy transient-exhaustion terminal is migrated to recovery backoff
        (``now_utc`` anchors the deterministic next probe); it stays active and
        capacity-holding and is never archived by this migration."""

        wl = cls(
            max_size=max_size,
            terminal_history=terminal_history,
            terminal_history_path=terminal_history_path,
        )
        if mirror_path is not None or terminal_history_mirror_path is not None:
            wl.set_mirror_path(
                mirror_path,
                terminal_history_path=terminal_history_mirror_path)
        p = Path(path)
        backup_path = p.with_suffix(p.suffix + ".bak")
        primary_cls = classify_watch_checkpoint_file(
            p, validation_now_utc=validation_now_utc)
        backup_cls = classify_watch_checkpoint_file(
            backup_path, validation_now_utc=validation_now_utc)
        decision = _cpe.resolve_checkpoint_pair(primary_cls, backup_cls)
        result = wl._checkpoint_result
        result.checkpoint_status = decision.status
        result.checkpoint_primary_status = primary_cls.state
        result.checkpoint_backup_status = backup_cls.state
        result.checkpoint_files_found = (
            primary_cls.state != _cpe.FILE_MISSING
            or backup_cls.state != _cpe.FILE_MISSING)
        result.checkpoint_primary_invalid_reason = (
            primary_cls.reason or None
            if primary_cls.state == _cpe.FILE_INVALID else None)
        result.checkpoint_backup_invalid_reason = (
            backup_cls.reason or None
            if backup_cls.state == _cpe.FILE_INVALID else None)
        result.checkpoint_recovered_from_backup = decision.recovered_from_backup
        result.checkpoint_generation_conflict_total = (
            1 if decision.generation_conflict else 0)
        result.checkpoint_last_validated_at_utc = (
            validation_now_utc if isinstance(validation_now_utc, str)
            and _utc(validation_now_utc) is not None else _cpe.utc_now_iso())
        result.checkpoint_notes.extend(decision.notes)
        digest_reasons = (
            _cpe.QUARANTINE_RECORD_DIGEST_INVALID,
            _cpe.QUARANTINE_PAYLOAD_DIGEST_INVALID,
            _cpe.QUARANTINE_ENVELOPE_DIGEST_INVALID,
            _cpe.QUARANTINE_EVIDENCE_DIGEST_INVALID,
            _cpe.QUARANTINE_CROSSING_DIGEST_INVALID,
        )
        for file_reason in (primary_cls.reason, backup_cls.reason):
            if file_reason in digest_reasons:
                result.checkpoint_digest_failure_total += 1
        if decision.status == _cpe.CHECKPOINT_NOT_FOUND:
            return wl
        if decision.quarantined:
            wl._quarantine_lockdown = True
            result.checkpoint_quarantined = True
            result.checkpoint_quarantine_reason = decision.quarantine_reason
            return wl

        selected = primary_cls if decision.selected == "primary" else backup_cls
        anchor_now = (now_utc if isinstance(now_utc, str)
                      and _utc(now_utc) is not None else _cpe.utc_now_iso())
        if selected.state == _cpe.FILE_VALID_CURRENT:
            header = selected.header or {}
            result.checkpoint_schema_version = header.get("schema_version")
            result.checkpoint_generation = header.get("generation")
            wl._checkpoint_generation = int(header.get("generation") or 0)
            wl._checkpoint_envelope_digest = header.get("envelope_digest")
            wl._checkpoint_created_at_utc = header.get("created_at_utc")
            wl._checkpoint_migration_history = [
                dict(item) for item in (header.get("migration_history") or [])
                if isinstance(item, Mapping)]
            for record in selected.records:
                if record.get("checkpoint_record_kind") \
                        == QUARANTINED_CANDIDATE_RECORD_KIND:
                    wl._quarantined_candidates[
                        str(record.get("token_mint"))] = dict(record)
                    wl._counters["checkpoint_candidates_quarantined"] += 1
                    continue
                payload = {k: v for k, v in record.items()
                           if k != "record_digest"}
                entry = WatchEntry(**payload)
                result.checkpoint_records_validated += 1
                if is_terminal_watch_state(entry.status):
                    wl._terminalize(
                        entry,
                        terminal_at_utc=(
                            entry.last_observed_at_utc or entry.seeded_at_utc),
                        migrated=True,
                    )
                else:
                    wl._restore_active_entry(
                        entry, now_utc,
                        source_schema_version=WATCH_CHECKPOINT_SCHEMA_VERSION,
                        legacy_checkpoint_digest=selected.byte_digest,
                        quarantined_at_utc=anchor_now,
                    )
            if decision.recovered_from_backup:
                # Controlled recovery: preserve the invalid primary evidence
                # unchanged, then rewrite a clean current primary as a NEW
                # generation chained to the recovered backup.
                if primary_cls.state == _cpe.FILE_INVALID \
                        and primary_cls.path is not None:
                    _cpe.preserve_evidence_copy(
                        primary_cls.path, label="invalid_evidence")
                try:
                    wl.persist(p)
                    result.checkpoint_notes.append(
                        "PRIMARY_REWRITTEN_FROM_BACKUP_RECOVERY")
                except (_cpe.CheckpointWriteError, OSError):
                    result.checkpoint_notes.append(
                        "PRIMARY_RECOVERY_REWRITE_FAILED")
        else:
            # Supported legacy schema: explicit deterministic migration.
            result.checkpoint_schema_version = WATCH_LEGACY_SCHEMA_VERSION
            result.checkpoint_migrations_attempted += 1
            for source_file in (primary_cls, backup_cls):
                if source_file.path is not None \
                        and source_file.state != _cpe.FILE_MISSING:
                    _cpe.preserve_evidence_copy(
                        source_file.path, label="legacy_source")
            wl._migrate_legacy_watch_records(
                list(selected.legacy_payload or []),
                checkpoint_digest=selected.byte_digest or _cpe.ZERO_DIGEST[:64],
                performed_at_utc=anchor_now,
                now_utc=now_utc,
                result=result,
            )
            wl._checkpoint_migration_history = [{
                "migrated_from_schema": WATCH_LEGACY_SCHEMA_VERSION,
                "migrated_to_schema": WATCH_CHECKPOINT_SCHEMA_VERSION,
                "migration_performed_at_utc": anchor_now,
                "migration_source": (
                    "primary" if decision.selected == "primary" else "backup"),
                "migration_source_digest": selected.byte_digest,
                "records_migrated": result.checkpoint_records_validated,
                "records_quarantined": result.checkpoint_records_rejected,
                "legacy_activation_migrated": wl._counters[
                    "checkpoint_legacy_activation_migrated"],
                "legacy_activation_quarantined": wl._counters[
                    "checkpoint_legacy_activation_quarantined"],
            }]
            try:
                wl.persist(p)
                result.checkpoint_migrations_succeeded += 1
                result.checkpoint_status = _cpe.CHECKPOINT_MIGRATED
                result.checkpoint_schema_version = (
                    WATCH_CHECKPOINT_SCHEMA_VERSION)
                result.checkpoint_generation = wl._checkpoint_generation
            except (_cpe.CheckpointWriteError, OSError) as exc:
                # Failed migration install: retain originals, do not
                # partially activate migrated candidates, quarantine.
                result.checkpoint_migrations_failed += 1
                wl._entries.clear()
                wl._quarantine_lockdown = True
                result.checkpoint_quarantined = True
                result.checkpoint_status = _cpe.CHECKPOINT_QUARANTINED
                result.checkpoint_quarantine_reason = (
                    _cpe.QUARANTINE_MIGRATION_WRITE_FAILED)
                result.checkpoint_notes.append(
                    f"MIGRATION_INSTALL_FAILED:{type(exc).__name__}")
        result.checkpoint_legacy_activation_migrated = wl._counters[
            "checkpoint_legacy_activation_migrated"]
        result.checkpoint_legacy_activation_quarantined = wl._counters[
            "checkpoint_legacy_activation_quarantined"]
        return wl


__all__ = (
    "MIGRATION_ACTIVATION_MULTIPLIER", "BACKFILL_ACTIVATION_MULTIPLIER",
    "DISCOVERY_PROVENANCE_LIVE", "DISCOVERY_PROVENANCE_HELIUS",
    "DISCOVERY_PROVENANCE_DEX",
    "DISCOVERY_PROVENANCES", "LIVE_DISCOVERY_PROVENANCES",
    "BASELINE_PENDING", "BASELINE_CAPTURED",
    "BASELINE_UNPROVEN_LEGACY", "BASELINE_SOURCE_GRPC_EVENT", "BASELINE_SOURCE_BIRDEYE", "BASELINE_SOURCE_DEX_BACKFILL",
    "WATCH_PENDING_BASELINE", "WATCH_PENDING_1_20X", "WATCH_ACTIVATED",
    "WATCH_ACTIVATED_WAITING",
    "WATCH_ACTIVE_DIP", "WATCH_REJECTED", "WATCH_EVICTED",
    "WATCH_SEEDED", "WATCH_WATCHING", "WATCH_SEND_ATTEMPTED", "WATCH_DEDUPE_SUPPRESSED",
    "WATCH_SENT_OK_COMMITTED", "WATCH_DELIVERY_UNKNOWN",
    "WATCH_EXPIRED", "WATCH_DROPPED_NON_PUMP", "activation_proof_is_eligible",
    "activation_proof_is_durable",
    "ACTIVATION_EVIDENCE_SCHEMA_VERSION", "ACTIVATION_EVIDENCE_SPOT_VERSION",
    "ACTIVATION_KIND_SPOT_CURRENT", "ACTIVATION_KIND_CONFIRMED_OHLCV_HIGH",
    "ACTIVATION_KIND_TRUSTED_RESERVE_EVENT", "ACTIVATION_COUNTER_FIELDS",
    "ACTIVATION_KIND_LEGACY_MIGRATION",
    "ACTIVATION_LEGACY_MIGRATION_EVIDENCE_VERSION",
    "ACTIVATION_LEGACY_MIGRATION_PROOF_VERSION",
    "build_activation_evidence_digest", "build_activation_spot_evidence_digest",
    "build_migration_baseline_digest", "MIGRATION_BASELINE_DIGEST_SCHEMA_VERSION",
    "build_legacy_activation_source_evidence_digest",
    "build_legacy_migration_crossing_digest",
    "build_legacy_activation_migration_proof_digest",
    "WATCH_CHECKPOINT_SCHEMA_VERSION", "WATCH_LEGACY_SCHEMA_VERSION",
    "QUARANTINED_CANDIDATE_RECORD_KIND",
    "validate_watch_checkpoint_record", "watch_checkpoint_record_identity",
    "classify_watch_checkpoint_file", "verify_cross_checkpoint_consistency",
    "SCHEDULABLE_WATCH_STATES", "ACTIVE_WATCH_STATES", "TERMINAL_WATCH_STATES",
    "is_schedulable_watch_state", "is_active_watch_state", "is_terminal_watch_state",
    "SEED_OUTCOME_ADMITTED", "SEED_OUTCOME_EXISTING",
    "SEED_OUTCOME_TERMINAL_DUPLICATE", "SEED_OUTCOME_DROPPED_NON_PUMP",
    "SEED_OUTCOME_CAPACITY", "SEED_OUTCOME_INVALID",
    "SEED_OUTCOME_CHECKPOINT_QUARANTINED", "SEED_OUTCOME_PRE_BOUNDARY",
    "SEED_OUTCOME_DIAGNOSTIC_ONLY",
    "CAPACITY_REJECTION_REASON",
    "TerminalHistoryArchive", "TerminalHistoryCorruptionError",
    "WatchEntry", "Watchlist",
    "WATCH_STATE_BASENAME", "WATCH_TERMINAL_HISTORY_BASENAME",
)

#: Canonical durable-state file names. Named here so the session, the
#: dashboard adapter and the offline tests cannot drift apart on them.
WATCH_STATE_BASENAME = "watch_state.jsonl"
WATCH_TERMINAL_HISTORY_BASENAME = "watch_terminal_history.jsonl"

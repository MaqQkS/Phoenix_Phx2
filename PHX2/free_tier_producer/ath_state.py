"""Central, monotonic ATH state shared by producer, send, paper, and dashboard.

The store owns the only mutable ATH state in the paid producer.  It accepts
validated PumpSwap reserve events and paid-provider observations, rejects
invalid shapes fail-closed, and atomically replaces ``ath_state.json`` after
every accepted change.  A duplicate Yellowstone delivery is identified by
``transaction_signature:event_index`` and is harmless across process restarts.

Market-cap observations are never reconstructed from ``current_mc / price``.
PumpSwap observations use the supply embedded in that exact decoded event;
provider current observations use the provider's direct market-cap value.
OHLCV highs may improve the price ATH without inventing a historical supply.
When an event-sourced supply observation is available for the candle time, it
may also produce a market-cap observation from that recorded supply.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, localcontext
import hashlib
import json
import os
from pathlib import Path
import threading
from typing import Any, Callable, Dict, Mapping, Optional, Tuple

from PHX2.stage29 import birdeye_constants as _bc
from PHX2.free_tier_producer.pumpswap_reserves import (
    PumpSwapReserveArtifact,
    PumpSwapReserveError,
    reserve_market_cap_usd,
    reserve_price_quote_units,
    reserve_price_usd,
)
from PHX2.free_tier_producer import checkpoint_envelope as _cpe
from PHX2.models.ath_coverage import (
    ATH_CANONICAL_SOURCE_LIVE_TRACKER,
    ATH_CANONICAL_SOURCE_V3_PAIR,
    ATH_HYDRATION_ANCHOR_MISSING,
    ATH_HYDRATION_COMPLETE,
    ATH_HYDRATION_MARKET_CAP_UNCONVERTED,
    ATH_HYDRATION_NEVER_ATTEMPTED,
    ATH_HYDRATION_PENDING,
    ATH_HYDRATION_VERIFIED,
    ATH_HYDRATION_WINDOW_INCOMPLETE,
    ATH_HYDRATION_WINDOW_STALE,
    ATH_HYDRATION_WINDOW_STARTS_AFTER_MIGRATION,
    ATH_V3_HISTORY_INCOMPLETE,
    ATH_V3_PAIR_UNAVAILABLE,
    ATH_V3_PENDING_REASONS,
)


ATH_STATE_BASENAME = "ath_state.json"
ATH_CHECKPOINT_BASENAME = "ath_state_checkpoint.json"
ATH_STATE_SCHEMA_VERSION = "phx2_central_ath_v1"
# PHX2-E2E-005: the authenticated restart checkpoint schema. The public
# ``ath_state.json`` display artifact intentionally keeps the legacy public
# shape for read-only consumers (dashboard, paper pricing).
ATH_CHECKPOINT_SCHEMA_VERSION = "phx2_central_ath_checkpoint_v2"
ATH_EVIDENCE_SCHEMA_VERSION = "phx2_central_ath_evidence_v2"
ATH_OBSERVATION_SEAL_SCHEMA_VERSION = "phx2_central_ath_observation_seal_v1"

SOURCE_PUMPSWAP_EVENT = "PUMPSWAP_EVENT_EFFECTIVE_RESERVES"
SOURCE_PAID_OHLCV = "PAID_OHLCV_HIGH"
#: 2026-08-03: canonical post-migration ATH observation -- the validated USD
#: high of the authenticated migration pair's V3 candle history.  The value
#: is ROLE-based (never a provider product name) because it travels into
#: scanned artifacts.
SOURCE_PAID_V3_PAIR = "PAID_V3_PAIR_OHLCV_HIGH"
SOURCE_PAID_CURRENT = "PAID_CURRENT_PRICE"
VALID_ATH_SOURCES = (
    SOURCE_PUMPSWAP_EVENT,
    SOURCE_PAID_OHLCV,
    SOURCE_PAID_V3_PAIR,
    SOURCE_PAID_CURRENT,
)
MAX_DURABLE_EVENT_DEDUPE_KEYS = 50_000

#: Restore-time retention horizon for the per-mint HEAVY operational maps
#: (``seen_event_keys`` / ``pending_events``).  A record whose latest activity
#: is older than this at restore keeps its full ATH core (values, evidence
#: seals, pool identity -- cross-generation regression checks compare ONLY the
#: ATH values, so retention never reads as a regression) but drops the event
#: dedupe map, whose only job -- suppressing recovery-overlap replays -- is
#: bounded to a horizon far shorter than this.  This is what keeps a DURABLE
#: cross-run checkpoint bounded instead of accumulating ~500KB of event keys
#: per hot mint forever.  Matches the ping dedupe TTL (6h).
DURABLE_RESTORE_HEAVY_STATE_RETENTION_SECONDS = 21_600

#: Whole-record retention horizon for a DURABLE (cross-run) checkpoint.  A
#: record whose latest activity is older than this at restore is RETIRED --
#: not loaded and therefore absent from the next persisted generation -- so
#: the durable checkpoint can never accumulate mints without bound.  72 h is
#: the deliberate lifecycle boundary: it comfortably exceeds every observed
#: restart/outage gap (max ~9.3 h on 2026-07-26) and the alert-relevant life
#: of a migrated mint, while the PERMANENT append-only ping-dedupe ledger --
#: not this market-evidence store -- carries the forever-scoped
#: highest-sent-tier memory.  Retiring an ATH record therefore never
#: re-opens a suppressed tier regression; a retired mint re-encountered via
#: restart backfill starts a fresh PARTIAL-coverage record (and is labeled
#: as such).  This is compatible with the live-only epoch policy: the store
#: is alert-evidence state, not ingestion history, and its lifecycle is
#: bounded by alert relevance rather than by epoch identity.
DURABLE_ATH_RECORD_RETENTION_SECONDS = 259_200

STATUS_CONFIRMED = "CONFIRMED"
STATUS_PROVISIONAL = "PROVISIONAL"

#: Supply bases an OHLCV candle high may be converted with, most authoritative
#: first.  ``EVENT_SOURCED_SUPPLY`` is the decoded PumpSwap event supply for
#: that exact candle time.  ``PROVIDER_REPORTED_SUPPLY`` is the supply the
#: market provider itself implied by publishing a market cap AND a price for
#: the SAME current observation; it is recorded verbatim from that one
#: response, never reconstructed from two different observations.  A
#: restart-backfill candidate has no swap events of its own, so without the
#: provider basis its post-migration candle high can never become a market cap
#: -- exactly the 2026-07-30 divergence, where the true 0.00006922 high sat in
#: ``ath_price`` while ``ath_market_cap`` stayed pinned to a spot tick.
SUPPLY_BASIS_EVENT = "EVENT_SOURCED_SUPPLY"
SUPPLY_BASIS_AUTHORITATIVE_RPC = "AUTHENTICATED_ONCHAIN_TOKEN_SUPPLY"
SUPPLY_BASIS_PROVIDER = "PROVIDER_REPORTED_SUPPLY"
#: The supply the ATH-PRICE observation itself proved, by carrying a market
#: cap AND a price in ONE response.  Strictly more authoritative than either
#: basis above for the resolved record, because it needs no inference across
#: observations at all: it is that observation's own circulating supply.
SUPPLY_BASIS_OBSERVATION = "OBSERVATION_IMPLIED_SUPPLY"
VALID_SUPPLY_BASES = (
    SUPPLY_BASIS_EVENT, SUPPLY_BASIS_AUTHORITATIVE_RPC,
    SUPPLY_BASIS_PROVIDER)
#: Bases valid for the RESOLVED tuple (a superset of the raw record's).
VALID_RESOLVED_SUPPLY_BASES = (
    SUPPLY_BASIS_OBSERVATION, SUPPLY_BASIS_EVENT,
    SUPPLY_BASIS_AUTHORITATIVE_RPC, SUPPLY_BASIS_PROVIDER)

#: The ONE resolution method PHX2 publishes.  The resolved market cap is the
#: accepted ATH PRICE multiplied by the authoritative supply belonging to the
#: SAME resolved observation -- never a separately maximized market cap.
RESOLUTION_PRICE_X_AUTHORITATIVE_SUPPLY = "PRICE_X_AUTHORITATIVE_SUPPLY"
VALID_ATH_RESOLUTION_METHODS = (RESOLUTION_PRICE_X_AUTHORITATIVE_SUPPLY,)

#: Working precision for the resolved supply/market-cap arithmetic.  Both the
#: producer (this module) and every consumer MUST go through
#: ``resolved_market_cap_from`` so an exact recompute check can never fail on
#: a context difference alone.
ATH_RESOLUTION_PRECISION = 60

ATH_RESOLVED_SCHEMA_VERSION = "phx2_central_ath_resolved_v1"

#: Closed reasons a record can fail to resolve.  Every one of them is
#: fail-closed: no tier, no compose, bounded retry continues.
ATH_RESOLVED_OK = "ATH_RESOLVED"
ATH_UNRESOLVED_NO_PRICE = "ATH_UNRESOLVED_NO_PRICE"
ATH_UNRESOLVED_NO_PRICE_PROVENANCE = "ATH_UNRESOLVED_NO_PRICE_PROVENANCE"
ATH_UNRESOLVED_SUPPLY_UNAVAILABLE = "ATH_UNRESOLVED_SUPPLY_UNAVAILABLE"
ATH_UNRESOLVED_SUPPLY_INVALID = "ATH_UNRESOLVED_SUPPLY_INVALID"
ATH_RESOLUTION_REASONS = (
    ATH_RESOLVED_OK,
    ATH_UNRESOLVED_NO_PRICE,
    ATH_UNRESOLVED_NO_PRICE_PROVENANCE,
    ATH_UNRESOLVED_SUPPLY_UNAVAILABLE,
    ATH_UNRESOLVED_SUPPLY_INVALID,
)

#: Bounded provider-supply timeline per mint (dedupe keeps the EARLIEST
#: observation of each distinct supply, mirroring the event-supply timeline).
MAX_PROVIDER_SUPPLY_OBSERVATIONS = 32
MAX_AUTHORITATIVE_SUPPLY_OBSERVATIONS = 32

#: A verified hydration window must reach within this many seconds of the
#: evaluation instant, otherwise the maximum is stale for a live-moving mint.
ATH_HYDRATION_MAX_WINDOW_LAG_SECONDS = 900.0
#: The window start may sit at most this far AFTER the migration anchor (one
#: candle of slack for a provider that aligns to minute boundaries).
ATH_HYDRATION_ANCHOR_TOLERANCE_SECONDS = 60.0
#: Bounded retry backoff for a pending hydration: base * 2**(attempts-1).
ATH_HYDRATION_BACKOFF_BASE_SECONDS = 30.0
ATH_HYDRATION_BACKOFF_MAX_SECONDS = 900.0

# ---- V3 pair-history state (2026-08-03) -----------------------------------

ATH_V3_STATE_SCHEMA_VERSION = "phx2_ath_v3_pair_v1"
#: Coarse full-window scan resolution.  Six hours at 15 seconds is 1,440
#: candles -- safely below the provider's 5,000-record response limit.
ATH_V3_COARSE_INTERVAL = "15s"
ATH_V3_COARSE_INTERVAL_SECONDS = _bc.BIRDEYE_V3_OHLCV_TYPE_SECONDS[
    ATH_V3_COARSE_INTERVAL]
#: Peak refinement resolution (short provider retention; a missing 1s series
#: retains the valid coarse precision explicitly instead of inventing it).
ATH_V3_REFINE_INTERVAL = "1s"
#: Bounded V3 request-ticket ids retained on the per-mint V3 state.
ATH_V3_MAX_RETAINED_TICKETS = 16

#: LIVE_TRACKER path (fallback while V3 is unavailable): the store must have
#: begun tracking this mint within this many seconds of its migration anchor
#: for the process-scoped live evidence to count as "from migration onward".
ATH_LIVE_TRACKER_ANCHOR_TOLERANCE_SECONDS = 90.0


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _decimal(value: object) -> Optional[Decimal]:
    if isinstance(value, (bool, float)):
        return None
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return number if number.is_finite() and number > 0 else None


def _text(value: Optional[Decimal]) -> Optional[str]:
    return None if value is None else format(value, "f")


def _epoch(value: object) -> Optional[float]:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
        return number if number >= 0 else None
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except (TypeError, ValueError, OSError):
        return None


def _iso(value: object) -> Optional[str]:
    epoch = _epoch(value)
    if epoch is None:
        return None
    return datetime.fromtimestamp(epoch, timezone.utc).isoformat().replace("+00:00", "Z")


def _canonical_mint(value: object) -> Optional[str]:
    from PHX2.free_tier_producer.migration_admission import is_supported_mint_identity
    return value if is_supported_mint_identity(value) else None


def resolved_market_cap_from(
    price: object, supply: object
) -> Optional[Decimal]:
    """The ONE canonical resolved-market-cap computation.

    Producer and every consumer call THIS, so an exact recompute check can
    never fail merely because two call sites used different Decimal
    contexts.  Returns ``None`` unless both inputs are finite and positive.
    """

    price_value = _decimal(price)
    supply_value = _decimal(supply)
    if price_value is None or supply_value is None:
        return None
    if price_value <= 0 or supply_value <= 0:
        return None
    with localcontext() as ctx:
        ctx.prec = ATH_RESOLUTION_PRECISION
        product = price_value * supply_value
    return product if product.is_finite() and product > 0 else None


def resolved_supply_from(
    market_cap: object, price: object
) -> Optional[Decimal]:
    """Circulating supply implied by ONE observation's own (mc, price)."""

    market_cap_value = _decimal(market_cap)
    price_value = _decimal(price)
    if market_cap_value is None or price_value is None:
        return None
    if market_cap_value <= 0 or price_value <= 0:
        return None
    with localcontext() as ctx:
        ctx.prec = ATH_RESOLUTION_PRECISION
        supply = market_cap_value / price_value
    return supply if supply.is_finite() and supply > 0 else None


def build_ath_resolved_tuple(
    record: Mapping[str, Any], *,
    event_supply_fn: Optional[Callable[[str], Tuple[
        Optional[Decimal], Optional[str]]]] = None,
    authoritative_live_epoch_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Resolve ONE coherent ATH observation tuple from a record.

    The peak PRICE is already correct and is what every tier is measured
    against -- in the 2026-08-02 run PHX2's ATH price matched PHX1 exactly
    for all four parity mints.  What was broken was the market cap beside
    it: the two arms were maximized independently, so ``ath_price`` came
    from one observation and ``ath_market_cap`` from another, and the
    composer (correctly) refused to render an alert that contradicted
    itself.

    This builds the single coherent tuple instead: the accepted ATH price,
    the authoritative supply belonging to THAT observation, and the market
    cap derived from the two.  Raw evidence is never touched -- the split
    maxima remain in the record as diagnostic history.

    Pure: reads the record, fetches nothing, mutates nothing.
    """

    unresolved: Dict[str, Any] = {
        "resolved_schema_version": ATH_RESOLVED_SCHEMA_VERSION,
        "resolved": False,
        "resolved_ath_price": None,
        "resolved_supply": None,
        "resolved_supply_basis": None,
        "resolved_ath_market_cap": None,
        "resolved_observed_at_utc": None,
        "resolved_source": None,
        "resolved_observation_type": None,
        "resolved_status": None,
        "resolved_evidence_digest": None,
        "resolution_method": None,
        "resolution_reason": ATH_UNRESOLVED_NO_PRICE,
    }
    if not isinstance(record, Mapping):
        return unresolved
    price = _decimal(record.get("ath_price"))
    if price is None or price <= 0:
        return unresolved
    provenance = record.get("price_provenance")
    provenance = provenance if isinstance(provenance, Mapping) else None
    if provenance is None or _decimal(provenance.get("price")) != price:
        # The maximum exists but PHX2 cannot name the observation that set
        # it (a pre-provenance legacy record).  Fail closed; a single fresh
        # authoritative observation restores resolution.
        return {**unresolved,
                "resolution_reason": ATH_UNRESOLVED_NO_PRICE_PROVENANCE}
    timestamp = _iso(provenance.get("timestamp"))
    if timestamp is None:
        return {**unresolved,
                "resolution_reason": ATH_UNRESOLVED_NO_PRICE_PROVENANCE}

    supply: Optional[Decimal] = None
    basis: Optional[str] = None
    declared = _decimal(provenance.get("supply"))
    declared_basis = provenance.get("supply_basis")
    declared_epoch = provenance.get("supply_live_epoch_id")
    authoritative_epoch_mismatch = bool(
        declared_basis == SUPPLY_BASIS_AUTHORITATIVE_RPC
        and authoritative_live_epoch_id is not None
        and declared_epoch != authoritative_live_epoch_id)
    # An OHLCV market cap produced from authenticated on-chain supply is not
    # an independent provider market-cap observation. Preserve the RPC basis
    # instead of relabelling the same arithmetic as provider-implied supply.
    if declared is not None and declared > 0 \
            and declared_basis == SUPPLY_BASIS_AUTHORITATIVE_RPC \
            and not authoritative_epoch_mismatch:
        supply, basis = declared, declared_basis
    # 1. The resolved observation's OWN implied supply.  Needs no inference
    #    across observations at all, so it is always preferred.
    observation_supply = resolved_supply_from(
        provenance.get("market_cap"), provenance.get("price"))
    if supply is None and observation_supply is not None \
            and not authoritative_epoch_mismatch:
        supply, basis = observation_supply, SUPPLY_BASIS_OBSERVATION
    if supply is None:
        # 2. The supply the observation itself reported (event-sourced).
        if declared is not None and declared > 0 \
                and declared_basis in VALID_SUPPLY_BASES \
                and not authoritative_epoch_mismatch:
            supply, basis = declared, declared_basis
    if supply is None and event_supply_fn is not None:
        # 3. The existing timestamp-anchored supply resolution, unchanged.
        try:
            candidate_supply, candidate_basis = event_supply_fn(timestamp)
        except Exception:
            candidate_supply, candidate_basis = None, None
        if candidate_supply is not None and candidate_supply > 0 \
                and candidate_basis in VALID_SUPPLY_BASES:
            supply, basis = candidate_supply, candidate_basis
    if supply is None:
        return {**unresolved,
                "resolution_reason": ATH_UNRESOLVED_SUPPLY_UNAVAILABLE}
    market_cap = resolved_market_cap_from(price, supply)
    if market_cap is None:
        return {**unresolved,
                "resolution_reason": ATH_UNRESOLVED_SUPPLY_INVALID}
    return {
        "resolved_schema_version": ATH_RESOLVED_SCHEMA_VERSION,
        "resolved": True,
        "resolved_ath_price": _text(price),
        "resolved_supply": _text(supply),
        "resolved_supply_basis": basis,
        "resolved_ath_market_cap": _text(market_cap),
        "resolved_observed_at_utc": timestamp,
        "resolved_source": provenance.get("provider"),
        "resolved_observation_type": provenance.get("observation_type"),
        "resolved_status": provenance.get("status"),
        "resolved_evidence_digest": provenance.get("evidence_digest"),
        "resolution_method": RESOLUTION_PRICE_X_AUTHORITATIVE_SUPPLY,
        "resolution_reason": ATH_RESOLVED_OK,
    }


def ath_resolved_tuple_is_valid(resolved: object) -> bool:
    """Structural + arithmetic validation of ONE resolved ATH tuple.

    This is what replaced the impossible split-arm equality check.  It does
    not ask whether two independent maxima happen to agree (they never
    could); it asks whether the ONE resolved observation is internally
    coherent: price, supply and market cap all finite-positive, the market
    cap exactly the canonical product of the other two, and the identity
    fields present and in their closed sets.
    """

    if not isinstance(resolved, Mapping) or resolved.get("resolved") is not True:
        return False
    if resolved.get("resolution_method") not in VALID_ATH_RESOLUTION_METHODS:
        return False
    if resolved.get("resolved_supply_basis") not in VALID_RESOLVED_SUPPLY_BASES:
        return False
    price = _decimal(resolved.get("resolved_ath_price"))
    supply = _decimal(resolved.get("resolved_supply"))
    market_cap = _decimal(resolved.get("resolved_ath_market_cap"))
    if price is None or supply is None or market_cap is None:
        return False
    if price <= 0 or supply <= 0 or market_cap <= 0:
        return False
    expected = resolved_market_cap_from(price, supply)
    if expected is None or expected != market_cap:
        return False
    if _iso(resolved.get("resolved_observed_at_utc")) is None:
        return False
    if resolved.get("resolved_source") not in VALID_ATH_SOURCES:
        return False
    observation_type = resolved.get("resolved_observation_type")
    if not isinstance(observation_type, str) or not observation_type:
        return False
    if resolved.get("resolved_status") not in (
            STATUS_CONFIRMED, STATUS_PROVISIONAL):
        return False
    return True


def build_ath_evidence_digest(mint: object, evidence: object) -> Optional[str]:
    """Return the canonical digest for one market-cap-capable ATH observation.

    The compact public ATH snapshot carries the same fields as the full restart
    provenance, so every activation consumer can independently bind the exact
    mint, Decimal value, event time, source and evidence version without a
    provider call or a second ATH implementation.
    """

    token = _canonical_mint(mint)
    if token is None or not isinstance(evidence, Mapping):
        return None
    market_cap = _decimal(
        evidence.get("market_cap")
        if "market_cap" in evidence else evidence.get("ath_market_cap"))
    price = _decimal(
        evidence.get("price")
        if "price" in evidence
        else evidence.get("ath_market_cap_evidence_price_usd"))
    timestamp = _iso(
        evidence.get("timestamp")
        if "timestamp" in evidence else evidence.get("ath_timestamp"))
    source = (evidence.get("provider")
              if "provider" in evidence else evidence.get("ath_provider"))
    observation_type = (
        evidence.get("observation_type")
        if "observation_type" in evidence
        else evidence.get("ath_observation_type"))
    status = evidence.get("status") if "status" in evidence else evidence.get("ath_status")
    if (market_cap is None or price is None or timestamp is None
            or source not in VALID_ATH_SOURCES
            or not isinstance(observation_type, str) or not observation_type
            or status not in (STATUS_CONFIRMED, STATUS_PROVISIONAL)):
        return None
    ohlcv_interval = (evidence.get("ohlcv_interval") if "ohlcv_interval" in evidence
                      else evidence.get("ath_ohlcv_interval"))
    ohlcv_time_from = (
        evidence.get("ohlcv_time_from_unix") if "ohlcv_time_from_unix" in evidence
        else evidence.get("ath_ohlcv_time_from_unix"))
    ohlcv_time_to = (
        evidence.get("ohlcv_time_to_unix") if "ohlcv_time_to_unix" in evidence
        else evidence.get("ath_ohlcv_time_to_unix"))
    ohlcv_complete = (
        evidence.get("ohlcv_history_complete")
        if "ohlcv_history_complete" in evidence
        else evidence.get("ath_ohlcv_history_complete"))
    if source in (SOURCE_PAID_OHLCV, SOURCE_PAID_V3_PAIR) and (
            not isinstance(ohlcv_interval, str) or not ohlcv_interval
            or isinstance(ohlcv_time_from, bool) or not isinstance(ohlcv_time_from, int)
            or isinstance(ohlcv_time_to, bool) or not isinstance(ohlcv_time_to, int)
            or ohlcv_time_from < 0 or ohlcv_time_to < ohlcv_time_from):
        return None
    if source == SOURCE_PAID_OHLCV and ohlcv_complete is not True:
        return None
    if source == SOURCE_PAID_V3_PAIR and ohlcv_complete not in (True, False):
        # A V3 pair observation may legitimately be sealed while its window
        # is still extending (the maximum is monotonic either way), but the
        # completeness claim must be an explicit boolean, never absent.
        return None
    event_index = (evidence.get("event_index") if "event_index" in evidence
                   else evidence.get("ath_event_index"))
    if (event_index is not None
            and (isinstance(event_index, bool) or not isinstance(event_index, int)
                 or event_index < 0)):
        return None
    payload = {
        "schema_version": ATH_EVIDENCE_SCHEMA_VERSION,
        "token_mint": token,
        "market_cap_usd": _text(market_cap),
        "price_usd": _text(price),
        "event_at_utc": timestamp,
        "source": source,
        "observation_type": observation_type,
        "status": status,
        "supply_at_observation": (
            evidence.get("supply") if "supply" in evidence
            else evidence.get("ath_supply_at_observation")),
        "transaction_signature": (
            evidence.get("transaction_signature")
            if "transaction_signature" in evidence
            else evidence.get("ath_transaction_signature")),
        "event_index": event_index,
        "raw_quote_reserves": (
            evidence.get("raw_quote_reserves") if "raw_quote_reserves" in evidence
            else evidence.get("ath_raw_quote_reserves")),
        "virtual_quote_reserves": (
            evidence.get("virtual_quote_reserves")
            if "virtual_quote_reserves" in evidence
            else evidence.get("ath_virtual_quote_reserves")),
        "effective_quote_reserves": (
            evidence.get("effective_quote_reserves")
            if "effective_quote_reserves" in evidence
            else evidence.get("ath_effective_quote_reserves")),
        "base_reserves": (
            evidence.get("base_reserves") if "base_reserves" in evidence
            else evidence.get("ath_base_reserves")),
        "ohlcv_interval": ohlcv_interval,
        "ohlcv_time_from_unix": ohlcv_time_from,
        "ohlcv_time_to_unix": ohlcv_time_to,
        "ohlcv_history_complete": ohlcv_complete,
    }
    encoded = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def ath_evidence_digest_is_valid(mint: object, evidence: object) -> bool:
    if not isinstance(evidence, Mapping):
        return False
    if evidence.get("ath_evidence_version") != ATH_EVIDENCE_SCHEMA_VERSION:
        return False
    supplied = evidence.get("ath_evidence_digest")
    expected = build_ath_evidence_digest(mint, evidence)
    return bool(isinstance(supplied, str) and len(supplied) == 64
                and expected is not None and supplied == expected)


def build_ath_observation_seal_digest(
    mint: object, evidence: object
) -> Optional[str]:
    """Seal when PHX2 received one immutable source-evidence identity.

    The economic observation digest deliberately excludes ingestion time.  This
    second digest binds that immutable identity to the latest validated local
    receipt, so an equal authoritative re-observation can refresh receipt
    freshness without pretending that the candle/event itself is newer.
    """

    token = _canonical_mint(mint)
    if token is None or not isinstance(evidence, Mapping):
        return None
    source_digest = (
        evidence.get("evidence_digest")
        if "evidence_digest" in evidence
        else evidence.get("ath_evidence_digest")
    )
    ingested_at = _iso(
        evidence.get("ingested_at_utc")
        if "ingested_at_utc" in evidence
        else evidence.get("ath_ingested_at_utc")
    )
    validated = (
        evidence.get("observation_seal_validated")
        if "observation_seal_validated" in evidence
        else evidence.get("ath_observation_seal_validated")
    )
    if (not isinstance(source_digest, str) or len(source_digest) != 64
            or ingested_at is None or validated is not True):
        return None
    payload = {
        "schema_version": ATH_OBSERVATION_SEAL_SCHEMA_VERSION,
        "token_mint": token,
        "source_evidence_digest": source_digest,
        "observed_at_utc": ingested_at,
        "validation_result": "VALID",
    }
    encoded = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def ath_observation_seal_digest_is_valid(mint: object, evidence: object) -> bool:
    if not isinstance(evidence, Mapping):
        return False
    version = evidence.get("ath_observation_seal_version")
    supplied = evidence.get("ath_observation_seal_digest")
    expected = build_ath_observation_seal_digest(mint, evidence)
    return bool(
        version == ATH_OBSERVATION_SEAL_SCHEMA_VERSION
        and isinstance(supplied, str) and len(supplied) == 64
        and expected is not None and supplied == expected
    )


def _new_mint_state() -> Dict[str, Any]:
    return {
        "ath_price": None,
        "ath_market_cap": None,
        "ath_timestamp": None,
        "ath_transaction_signature": None,
        "ath_event_index": None,
        "ath_provider": None,
        "ath_observation_type": None,
        "ath_supply_at_observation": None,
        "ath_raw_quote_reserves": None,
        "ath_virtual_quote_reserves": None,
        "ath_effective_quote_reserves": None,
        "ath_base_reserves": None,
        "ath_ohlcv_interval": None,
        "ath_ohlcv_time_from_unix": None,
        "ath_ohlcv_time_to_unix": None,
        "ath_ohlcv_history_complete": None,
        "ath_market_cap_evidence_price_usd": None,
        "ath_ingested_at_utc": None,
        "ath_evidence_version": None,
        "ath_evidence_digest": None,
        "ath_source_evidence_version": None,
        "ath_source_evidence_digest": None,
        "ath_observation_seal_version": None,
        "ath_observation_seal_digest": None,
        "ath_observation_seal_validated": False,
        "ath_equal_evidence_reobserved_count": 0,
        "ath_last_equal_evidence_reobserved_at_utc": None,
        # PHX2-E2E-005: True when this record was migrated from the
        # pre-evidence legacy schema and its authoritative maximum has no
        # source-evidence digest yet. Only an equal authoritative
        # re-observation may backfill the seal (never the numeric value).
        "ath_legacy_pre_evidence": False,
        "ath_status": STATUS_PROVISIONAL,
        # Which supply basis converted the authoritative market cap (None for
        # a provider CURRENT observation, which reports the market cap
        # directly and needs no conversion).
        "ath_supply_basis": None,
        # ---- resolved coherent ATH observation (2026-08-02) -------------
        # ONE observation: the accepted peak price, the authoritative supply
        # belonging to that same observation, and the market cap derived
        # from the two.  The raw split maxima above are PRESERVED as
        # diagnostic evidence and are never what a tier or an alert body is
        # computed from any more.
        "resolved_schema_version": None,
        "resolved": False,
        "resolved_ath_price": None,
        "resolved_supply": None,
        "resolved_supply_basis": None,
        "resolved_ath_market_cap": None,
        "resolved_observed_at_utc": None,
        "resolved_source": None,
        "resolved_observation_type": None,
        "resolved_status": None,
        "resolved_evidence_digest": None,
        "resolution_method": None,
        "resolution_reason": ATH_UNRESOLVED_NO_PRICE,
        "last_updated_at": None,
        "price_provenance": None,
        "market_cap_provenance": None,
        "seen_event_keys": {},
        "supply_observations": {},
        "authoritative_supply_observations": {},
        "provider_supply_observations": {},
        "pending_events": [],
    }


# Keys the legacy schema attached OUTSIDE the base template.
_ATH_DYNAMIC_STATE_KEYS = (
    "pool_address", "quote_mint", "pool_created_at", "ohlcv_coverage",
    "ath_hydration", "ath_v3_pair",
)
_ATH_RECORD_ALLOWED_KEYS = frozenset(
    tuple(_new_mint_state()) + _ATH_DYNAMIC_STATE_KEYS
    + ("token_mint", "record_digest"))
_ATH_TIMESTAMP_KEYS = (
    "ath_timestamp", "last_updated_at", "ath_ingested_at_utc",
    "pool_created_at", "ath_last_equal_evidence_reobserved_at_utc",
    "resolved_observed_at_utc",
)


def _ath_decimal_field_ok(value: object, *, strings_only: bool) -> bool:
    if value is None:
        return True
    if strings_only and not isinstance(value, str):
        return False
    return _decimal(value) is not None


def _optional_unix_ok(value: object) -> bool:
    return value is None or (isinstance(value, int)
                             and not isinstance(value, bool) and value >= 0)


def _validate_ath_v3_state(v3: object) -> bool:
    """Fail-closed structural validation of ONE ``ath_v3_pair`` sub-document."""

    if v3 is None:
        return True
    if not isinstance(v3, Mapping):
        return False
    if v3.get("schema_version") not in (None, ATH_V3_STATE_SCHEMA_VERSION):
        return False
    reason = v3.get("pending_reason")
    if reason is not None and reason not in ATH_V3_PENDING_REASONS:
        return False
    if v3.get("history_complete") not in (True, False, None):
        return False
    for key in ("anchor_unix", "window_from_unix", "window_to_unix",
                "cursor_unix", "candle_count"):
        if not _optional_unix_ok(v3.get(key)):
            return False
    for peak_key in ("coarse_peak", "refined_peak", "usd_peak"):
        peak = v3.get(peak_key)
        if peak is None:
            continue
        if not isinstance(peak, Mapping):
            return False
        value_key = "price_usd" if peak_key == "usd_peak" else "native_high"
        if _decimal(peak.get(value_key)) is None:
            return False
        if not _optional_unix_ok(peak.get("unix_time")):
            return False
    tickets = v3.get("request_ticket_ids")
    if tickets is not None and not isinstance(tickets, (list, tuple)):
        return False
    return True


def _validate_ath_state_fields(
    mint: str, record: Mapping[str, Any], *, strings_only: bool
) -> Tuple[bool, str]:
    """Shared per-record semantic validation (current + legacy schemas)."""

    for key in ("ath_price", "ath_market_cap",
                "ath_market_cap_evidence_price_usd",
                "resolved_ath_price", "resolved_supply",
                "resolved_ath_market_cap"):
        if not _ath_decimal_field_ok(record.get(key),
                                     strings_only=strings_only):
            return False, _cpe.QUARANTINE_NUMERIC_INVALID
    # The RESOLVED tuple is either absent/unresolved or fully coherent.  A
    # record claiming resolution whose own arithmetic does not hold is
    # genuinely corrupt and still quarantines; a record whose RAW split
    # maxima disagree is ordinary preserved history and does not.
    if record.get("resolved") is True:
        if not ath_resolved_tuple_is_valid(record):
            return False, _cpe.QUARANTINE_CROSS_CONSISTENCY_INVALID
        if _decimal(record.get("resolved_ath_price")) != _decimal(
                record.get("ath_price")):
            return False, _cpe.QUARANTINE_CROSS_CONSISTENCY_INVALID
    elif record.get("resolution_method") is not None:
        return False, _cpe.QUARANTINE_STATUS_UNSUPPORTED
    reason = record.get("resolution_reason")
    if reason is not None and reason not in ATH_RESOLUTION_REASONS:
        return False, _cpe.QUARANTINE_STATUS_UNSUPPORTED
    basis = record.get("resolved_supply_basis")
    if basis is not None and basis not in VALID_RESOLVED_SUPPLY_BASES:
        return False, _cpe.QUARANTINE_STATUS_UNSUPPORTED
    provider = record.get("ath_provider")
    if provider is not None and provider not in VALID_ATH_SOURCES:
        return False, _cpe.QUARANTINE_STATUS_UNSUPPORTED
    basis = record.get("ath_supply_basis")
    if basis is not None and basis not in VALID_SUPPLY_BASES:
        return False, _cpe.QUARANTINE_STATUS_UNSUPPORTED
    status = record.get("ath_status")
    if status is not None and status not in (STATUS_CONFIRMED,
                                             STATUS_PROVISIONAL):
        return False, _cpe.QUARANTINE_STATUS_UNSUPPORTED
    for key in _ATH_TIMESTAMP_KEYS:
        value = record.get(key)
        if value is not None and _iso(value) is None:
            return False, _cpe.QUARANTINE_TIMESTAMP_INVALID
    count = record.get("ath_equal_evidence_reobserved_count", 0)
    if count is not None and (isinstance(count, bool)
                              or not isinstance(count, int) or count < 0):
        return False, _cpe.QUARANTINE_NUMERIC_INVALID
    if not _validate_ath_v3_state(record.get("ath_v3_pair")):
        return False, _cpe.QUARANTINE_SCHEMA_UNSUPPORTED
    evidence_digest = record.get("ath_evidence_digest")
    evidence_version = record.get("ath_evidence_version")
    seal_digest = record.get("ath_observation_seal_digest")
    if evidence_digest is not None or evidence_version is not None:
        if not _cpe.is_sha256_digest(evidence_digest):
            return False, _cpe.QUARANTINE_EVIDENCE_DIGEST_INVALID
        if not ath_evidence_digest_is_valid(mint, record):
            return False, _cpe.QUARANTINE_EVIDENCE_DIGEST_INVALID
        if not _cpe.is_sha256_digest(seal_digest) \
                or not ath_observation_seal_digest_is_valid(mint, record):
            return False, _cpe.QUARANTINE_EVIDENCE_DIGEST_INVALID
    elif seal_digest is not None:
        return False, _cpe.QUARANTINE_EVIDENCE_DIGEST_INVALID
    return True, ""


def validate_ath_checkpoint_record(
    record: Mapping[str, Any],
) -> Tuple[bool, str]:
    """Validate ONE current-schema ATH checkpoint record fail-closed."""

    if not isinstance(record, Mapping):
        return False, _cpe.QUARANTINE_JSON_INVALID
    mint = record.get("token_mint")
    if _canonical_mint(mint) is None:
        return False, _cpe.QUARANTINE_MINT_BINDING_INVALID
    if set(record) - _ATH_RECORD_ALLOWED_KEYS:
        return False, _cpe.QUARANTINE_SCHEMA_UNSUPPORTED
    ok, reason = _validate_ath_state_fields(str(mint), record,
                                            strings_only=True)
    if not ok:
        return False, reason
    if record.get("ath_market_cap") is not None \
            and record.get("ath_legacy_pre_evidence") is not True \
            and record.get("ath_evidence_digest") is None:
        # A current-schema authoritative market cap must carry its sealed
        # evidence unless it is an explicitly marked legacy migration.
        return False, _cpe.QUARANTINE_EVIDENCE_DIGEST_INVALID
    if not isinstance(record.get("seen_event_keys", {}), Mapping) \
            or not isinstance(record.get("supply_observations", {}), Mapping) \
            or not isinstance(
                record.get("authoritative_supply_observations", {}), Mapping) \
            or not isinstance(
                record.get("provider_supply_observations", {}), Mapping) \
            or not isinstance(record.get("ath_hydration", {}), Mapping) \
            or not isinstance(record.get("pending_events", []), list):
        return False, _cpe.QUARANTINE_SCHEMA_UNSUPPORTED
    hydration = record.get("ath_hydration")
    if isinstance(hydration, Mapping) and hydration.get("status") not in (
            None, ATH_HYDRATION_COMPLETE, ATH_HYDRATION_PENDING):
        return False, _cpe.QUARANTINE_STATUS_UNSUPPORTED
    return True, ""


def _resolved_tuple_current(record: Mapping[str, Any]) -> bool:
    """The ONE coherent resolved observation exists and matches the maximum."""

    if record.get("resolved") is not True:
        return False
    if not ath_resolved_tuple_is_valid(record):
        return False
    return _decimal(record.get("resolved_ath_price")) == _decimal(
        record.get("ath_price"))


def evaluate_ath_hydration_detail(
    record: Mapping[str, Any], *, now_utc: Optional[str] = None,
    max_window_lag_seconds: float = ATH_HYDRATION_MAX_WINDOW_LAG_SECONDS,
    active_live_epoch_id: Optional[str] = None,
    live_coverage: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Three-path verdict on ONE record's post-migration ATH completeness.

    2026-08-03 contract (the last real alert is the specification): the
    canonical post-migration maximum is the validated USD high of the
    authenticated migration PAIR's V3 candle history, from the migration
    anchor through the evaluation instant.  Exactly three outcomes exist:

    * **Path A** -- the V3 pair history is complete, epoch-eligible, anchored
      at (or before) migration, fresh, and the ONE resolved coherent tuple
      matches it: ``ATH_HYDRATION_COMPLETE`` with canonical source
      ``PAID_V3_PAIR_OHLCV_COMPLETE``.
    * **Path B** -- V3 is temporarily unavailable, but THIS process has
      tracked the candidate live since within
      :data:`ATH_LIVE_TRACKER_ANCHOR_TOLERANCE_SECONDS` of its migration
      anchor, in the same live epoch, and the resolved tuple is coherent:
      ``ATH_HYDRATION_COMPLETE`` with canonical source
      ``LIVE_TRACKER_COMPLETE``.  Live coverage is process-scoped evidence by
      construction (it is never restored across restarts), so "uninterrupted"
      is structural, not asserted.
    * **Path C** -- neither: ``ATH_HYDRATION_PENDING`` with ONE specific
      named reason (``ATH_V3_*`` family, or the anchor/supply reasons that
      are not V3's fault).  Never a generic UNKNOWN.

    Pre-V3 token-level OHLCV coverage (``ohlcv_coverage``) no longer proves
    completeness: the 2026-08-03 alert carried exactly such a "complete"
    window whose migration-anchored ``time_from`` had silently dropped the
    partial first candle -- the candle holding the literal peak.

    Pure: reads the record and the supplied coverage, never fetches.
    """

    def _verdict(status: str, reason: str,
                 canonical: Optional[str]) -> Dict[str, Any]:
        return {"status": status, "reason": reason,
                "canonical_source": canonical}

    if not isinstance(record, Mapping):
        return _verdict(ATH_HYDRATION_PENDING,
                        ATH_HYDRATION_NEVER_ATTEMPTED, None)
    anchor = _epoch(record.get("pool_created_at"))
    if anchor is None:
        return _verdict(ATH_HYDRATION_PENDING,
                        ATH_HYDRATION_ANCHOR_MISSING, None)
    now = _epoch(now_utc) if now_utc is not None else _epoch(_now_iso())

    v3 = record.get("ath_v3_pair")
    v3 = v3 if isinstance(v3, Mapping) else None
    v3_epoch_ok = bool(
        v3 is not None
        and (active_live_epoch_id is None
             or v3.get("live_epoch_id") == active_live_epoch_id))

    # ---- Path A: canonical V3 pair history --------------------------------
    if v3 is not None and v3_epoch_ok and v3.get("history_complete") is True:
        start = v3.get("window_from_unix")
        end = v3.get("window_to_unix")
        ints_ok = (
            isinstance(start, int) and not isinstance(start, bool)
            and isinstance(end, int) and not isinstance(end, bool))
        if ints_ok and start > anchor + (
                ATH_HYDRATION_ANCHOR_TOLERANCE_SECONDS):
            # A window that begins after migration cannot contain the first
            # post-migration peak -- the exact peak a dip is measured
            # against.  Named explicitly; never silently incomplete.
            return _verdict(ATH_HYDRATION_PENDING,
                            ATH_HYDRATION_WINDOW_STARTS_AFTER_MIGRATION,
                            None)
        window_ok = ints_ok
        fresh = (
            window_ok and (now is None or (now - end) <= max(
                0.0, float(max_window_lag_seconds))))
        usd_peak = v3.get("usd_peak")
        usd_ok = isinstance(usd_peak, Mapping) and _decimal(
            usd_peak.get("price_usd")) is not None
        if window_ok and fresh and usd_ok:
            if _resolved_tuple_current(record):
                return _verdict(ATH_HYDRATION_COMPLETE,
                                ATH_HYDRATION_VERIFIED,
                                ATH_CANONICAL_SOURCE_V3_PAIR)
            return _verdict(ATH_HYDRATION_PENDING,
                            ATH_HYDRATION_MARKET_CAP_UNCONVERTED, None)
        if window_ok and not fresh:
            # A previously complete window that no longer reaches the present
            # owes an incremental extension, not a re-scan.
            pass  # falls through to Path B / Path C below

    # ---- Path B: uninterrupted process-scoped live tracker ----------------
    live = live_coverage if isinstance(live_coverage, Mapping) else None
    live_anchored_unresolved = False
    if live is not None:
        epoch_ok = live.get("live_epoch_id") == active_live_epoch_id
        started = _epoch(live.get("tracking_started_at_utc"))
        anchored = (
            started is not None
            and started <= anchor + ATH_LIVE_TRACKER_ANCHOR_TOLERANCE_SECONDS)
        if epoch_ok and anchored:
            if _resolved_tuple_current(record):
                return _verdict(ATH_HYDRATION_COMPLETE,
                                ATH_HYDRATION_VERIFIED,
                                ATH_CANONICAL_SOURCE_LIVE_TRACKER)
            # An anchored tracker whose tuple has not resolved yet is not
            # complete live evidence -- fall through so a RECORDED V3
            # failure keeps its specific name instead of being shadowed.
            live_anchored_unresolved = True

    # ---- Path C: one specific named reason --------------------------------
    if v3 is not None and v3_epoch_ok:
        reason = v3.get("pending_reason")
        if reason in ATH_V3_PENDING_REASONS:
            return _verdict(ATH_HYDRATION_PENDING, reason, None)
        return _verdict(ATH_HYDRATION_PENDING,
                        ATH_V3_HISTORY_INCOMPLETE, None)
    pair_known = bool(record.get("pool_address")) or bool(
        v3 is not None and v3.get("pair_address"))
    if not pair_known:
        return _verdict(ATH_HYDRATION_PENDING, ATH_V3_PAIR_UNAVAILABLE, None)
    if live_anchored_unresolved:
        return _verdict(ATH_HYDRATION_PENDING,
                        ATH_HYDRATION_MARKET_CAP_UNCONVERTED, None)
    return _verdict(ATH_HYDRATION_PENDING, ATH_V3_HISTORY_INCOMPLETE, None)


def evaluate_ath_hydration(
    record: Mapping[str, Any], *, now_utc: Optional[str] = None,
    max_window_lag_seconds: float = ATH_HYDRATION_MAX_WINDOW_LAG_SECONDS,
) -> Tuple[str, str]:
    """Compatibility projection of :func:`evaluate_ath_hydration_detail`.

    Callers that carry no live-epoch or live-coverage context (offline
    fixtures, replay harnesses) evaluate Paths A and C only.
    """

    detail = evaluate_ath_hydration_detail(
        record, now_utc=now_utc,
        max_window_lag_seconds=max_window_lag_seconds)
    return detail["status"], detail["reason"]


def ath_hydration_backoff_seconds(attempt_count: object) -> float:
    """Bounded exponential retry spacing for a pending hydration."""

    try:
        attempts = max(1, int(attempt_count))
    except (TypeError, ValueError):
        attempts = 1
    return min(
        ATH_HYDRATION_BACKOFF_MAX_SECONDS,
        ATH_HYDRATION_BACKOFF_BASE_SECONDS * (2.0 ** (attempts - 1)),
    )


def ath_checkpoint_record_identity(record: Mapping[str, Any]) -> Tuple:
    mint = record.get("token_mint")
    if not isinstance(mint, str) or not mint:
        raise ValueError("CHECKPOINT_MINT_BINDING_INVALID")
    return ("mint", mint)


def _classify_legacy_ath_text(
    text: str, raw: bytes
) -> Tuple[str, str, Any, Optional[str]]:
    """Classify a legacy ``phx2_central_ath_v1`` JSON document fail-closed.

    Unlike the pre-envelope watch JSONL, an empty ATH file was NEVER a valid
    artifact: it is truncation."""

    stripped = text.strip()
    if not stripped:
        return (_cpe.FILE_INVALID, _cpe.QUARANTINE_TRUNCATED, None, None)
    try:
        parsed = _cpe.strict_json_loads(text)
    except ValueError:
        reason = (_cpe.QUARANTINE_JSON_INVALID if stripped.endswith("}")
                  else _cpe.QUARANTINE_TRUNCATED)
        return (_cpe.FILE_INVALID, reason, None, None)
    if not isinstance(parsed, dict) \
            or parsed.get("schema_version") != ATH_STATE_SCHEMA_VERSION \
            or not isinstance(parsed.get("mints"), dict):
        return (_cpe.FILE_INVALID, _cpe.QUARANTINE_SCHEMA_UNSUPPORTED,
                None, None)
    for mint, raw_state in parsed["mints"].items():
        if _canonical_mint(mint) is None or not isinstance(raw_state, dict):
            return (_cpe.FILE_INVALID, _cpe.QUARANTINE_MINT_BINDING_INVALID,
                    None, None)
        ok, reason = _validate_ath_state_fields(mint, raw_state,
                                                strings_only=False)
        if not ok:
            # One tampered/invalid record poisons trust in the whole file:
            # fall through the matrix (backup, then public legacy source,
            # then quarantine) instead of silently dropping the record.
            return (_cpe.FILE_INVALID, reason, None, None)
    return (_cpe.FILE_VALID_LEGACY, "", parsed, ATH_STATE_SCHEMA_VERSION)


def classify_ath_checkpoint_file(
    path: object, *, validation_now_utc: Optional[str] = None
) -> "_cpe.FileClassification":
    return _cpe.classify_checkpoint_file(
        path,
        kind=_cpe.CHECKPOINT_KIND_ATH,
        supported_schema_versions=(ATH_CHECKPOINT_SCHEMA_VERSION,),
        record_validator=validate_ath_checkpoint_record,
        identity_fn=ath_checkpoint_record_identity,
        legacy_classifier=_classify_legacy_ath_text,
        validation_now_utc=validation_now_utc,
    )


def _ath_generation_values(
    classification: "_cpe.FileClassification",
) -> Dict[str, Tuple[Optional[Decimal], Optional[Decimal]]]:
    """mint -> (ath_market_cap, ath_price) for either schema generation."""

    out: Dict[str, Tuple[Optional[Decimal], Optional[Decimal]]] = {}
    if classification.state == _cpe.FILE_VALID_CURRENT:
        for record in classification.records:
            mint = record.get("token_mint")
            if isinstance(mint, str):
                out[mint] = (_decimal(record.get("ath_market_cap")),
                             _decimal(record.get("ath_price")))
    elif classification.state == _cpe.FILE_VALID_LEGACY \
            and isinstance(classification.legacy_payload, Mapping):
        for mint, raw_state in (
                classification.legacy_payload.get("mints") or {}).items():
            if isinstance(raw_state, Mapping):
                out[str(mint)] = (_decimal(raw_state.get("ath_market_cap")),
                                  _decimal(raw_state.get("ath_price")))
    return out


def _ath_record_latest_activity(
    classification: "_cpe.FileClassification",
) -> Dict[str, Optional[float]]:
    """mint -> latest activity epoch (``last_updated_at``/``ath_timestamp``)."""

    out: Dict[str, Optional[float]] = {}
    rows: list = []
    if classification.state == _cpe.FILE_VALID_CURRENT:
        rows = [(record.get("token_mint"), record)
                for record in classification.records]
    elif classification.state == _cpe.FILE_VALID_LEGACY \
            and isinstance(classification.legacy_payload, Mapping):
        rows = list((classification.legacy_payload.get("mints") or {}).items())
    for mint, record in rows:
        if not isinstance(mint, str) or not isinstance(record, Mapping):
            continue
        latest: Optional[float] = None
        for key in ("last_updated_at", "ath_timestamp"):
            when = _epoch(record.get(key))
            if when is not None and (latest is None or when > latest):
                latest = when
        out[str(mint)] = latest
    return out


def ath_cross_generation_check(
    selected: "_cpe.FileClassification",
    other: "_cpe.FileClassification",
) -> Tuple[bool, Optional[str], int]:
    """There is no legitimate automatic ATH reset: the selected generation
    must be numerically monotonic against every mint the other VALID
    generation also carries.

    One deliberate carve-out (2026-07-27 durable-checkpoint lifecycle): a mint
    that is entirely ABSENT from the selected generation is not a regression
    when the other generation's copy of it was already stale beyond
    ``DURABLE_ATH_RECORD_RETENTION_SECONDS`` at the selected generation's
    write time -- that is exactly what a legitimate restore-time retirement
    looks like (the pruned primary is one generation ahead of a backup that
    still carries the retired record).  A PRESENT-but-LOWER value remains a
    regression at any age, and the absence of a still-FRESH mint remains a
    regression -- accidental record loss keeps failing closed.
    """

    selected_values = _ath_generation_values(selected)
    other_values = _ath_generation_values(other)
    other_activity = _ath_record_latest_activity(other)
    selected_written_at: Optional[float] = None
    if selected.state == _cpe.FILE_VALID_CURRENT \
            and isinstance(selected.header, Mapping):
        selected_written_at = _epoch(selected.header.get("updated_at_utc"))
    regressions = 0
    for mint, (other_mc, other_price) in other_values.items():
        selected_mc, selected_price = selected_values.get(mint, (None, None))
        if mint not in selected_values:
            latest = other_activity.get(mint)
            if selected_written_at is not None and latest is not None \
                    and (selected_written_at - latest) > (
                        DURABLE_ATH_RECORD_RETENTION_SECONDS):
                continue                     # legitimate retirement
        if other_mc is not None and (
                selected_mc is None or selected_mc < other_mc):
            regressions += 1
            continue
        if other_price is not None and (
                selected_price is None or selected_price < other_price):
            regressions += 1
    if regressions:
        return False, _cpe.QUARANTINE_ATH_REGRESSION, regressions
    return True, None, 0


class CentralAthStateStore:
    """Thread-safe, write-through central ATH state.

    ``path`` may be a directory or an explicit ``*.json`` file.  Passing
    ``None`` gives tests an in-memory store while preserving identical update
    and validation behavior.
    """

    def __init__(
        self,
        path: Optional[object] = None,
        *,
        now_utc: Optional[str] = None,
        validation_now_utc: Optional[str] = None,
        checkpoint_dir: Optional[object] = None,
        hydration_now_fn: Optional[Callable[[], str]] = None,
    ) -> None:
        self._lock = threading.RLock()
        # Injected ONLY for the hydration-window freshness verdict, so an
        # offline fixture can pin a deterministic evaluation instant.  None =
        # wall clock (production).
        self._hydration_now_fn = hydration_now_fn
        self._path: Optional[Path]
        if path is None:
            self._path = None
            self._checkpoint_path = None
            self._backup_path: Optional[Path] = None
        else:
            candidate = Path(path)
            self._path = candidate if candidate.suffix.lower() == ".json" else candidate / ATH_STATE_BASENAME
            self._checkpoint_path = (
                self._path.with_name(self._path.stem + "_checkpoint.json")
                if candidate.suffix.lower() == ".json"
                else candidate / ATH_CHECKPOINT_BASENAME
            )
            self._backup_path = self._checkpoint_path.with_name(
                self._checkpoint_path.name + ".bak")
        self._durable_checkpoint = bool(
            checkpoint_dir is not None and path is not None)
        if self._durable_checkpoint:
            # Durable cross-run anchor: the AUTHENTICATED checkpoint pair lives
            # in a stable state directory that survives per-run output-dir
            # rotation, so a producer restart restores canonical ATH/tier
            # evidence instead of starting from zero (the 2026-07-27 duplicate
            # / ATH-regression class).  The human-readable ``ath_state.json``
            # mirror stays beside the run artifacts in ``path``.  Restore-time
            # record retirement and heavy-map compaction apply ONLY in this
            # durable mode: a per-run checkpoint dies with its run directory
            # and must keep reloading its own state verbatim (including
            # legacy-migration fixtures) regardless of wall-clock age.
            durable_root = Path(checkpoint_dir)
            self._checkpoint_path = durable_root / ATH_CHECKPOINT_BASENAME
            self._backup_path = self._checkpoint_path.with_name(
                self._checkpoint_path.name + ".bak")
        self._mints: Dict[str, Dict[str, Any]] = {}
        self._quote_prices: Dict[str, Decimal] = {}
        # Process-scoped eligibility identity. It is deliberately not part of
        # the durable market-evidence checkpoint: a new process opens a new
        # epoch and must bind it explicitly before prior evidence is eligible.
        self._active_live_epoch_id: Optional[str] = None
        # Process-scoped LIVE_TRACKER coverage (Path B of the hydration
        # verdict).  Deliberately NOT persisted and NOT restored: an
        # "uninterrupted live tracker" claim cannot survive a process gap, so
        # keeping it off the checkpoint makes the claim structural instead of
        # asserted.
        self._live_coverage: Dict[str, Dict[str, Any]] = {}
        # PHX2-E2E-005 authenticated checkpoint state.
        self._quarantined = False
        self._checkpoint_result = _cpe.CheckpointLoadResult(
            checkpoint_kind=_cpe.CHECKPOINT_KIND_ATH)
        self._checkpoint_generation = 0
        self._checkpoint_envelope_digest: Optional[str] = None
        self._checkpoint_created_at_utc: Optional[str] = None
        self._checkpoint_migration_history: list = []
        self._checkpoint_records_retired = 0
        # Bounded-retry checkpoint-write durability accounting (surfaced in
        # checkpoint_summary -> heartbeat/status). Initialised before _load so
        # the migration/restore persist paths can record into it.
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
        }
        self._load(now_utc=now_utc, validation_now_utc=validation_now_utc)

    @property
    def path(self) -> Optional[Path]:
        return self._path

    @property
    def checkpoint(self) -> "_cpe.CheckpointLoadResult":
        return self._checkpoint_result

    @property
    def checkpoint_quarantined(self) -> bool:
        return self._quarantined

    def checkpoint_summary(self) -> Dict[str, Any]:
        out = dict(self._checkpoint_result.as_dict())
        out.update(self._checkpoint_write_metrics)
        out["checkpoint_records_retired"] = self._checkpoint_records_retired
        return out

    def bind_live_epoch(self, live_epoch_id: object) -> bool:
        """Restrict authenticated supply to one current live-only epoch."""

        if not isinstance(live_epoch_id, str) or not live_epoch_id:
            return False
        with self._lock:
            if self._active_live_epoch_id == live_epoch_id:
                return True
            self._active_live_epoch_id = live_epoch_id
            # A new epoch is a new eligibility domain: live-tracker coverage
            # begun under a prior epoch can never satisfy Path B in this one.
            self._live_coverage = {
                mint: entry for mint, entry in self._live_coverage.items()
                if entry.get("live_epoch_id") == live_epoch_id}
            for mint, state in self._mints.items():
                self._resolve_locked(state)
                self._refresh_hydration_locked(state, mint=mint)
        return True

    @property
    def active_live_epoch_id(self) -> Optional[str]:
        """Process-scoped live epoch used by authenticated supply consumers."""

        with self._lock:
            return self._active_live_epoch_id

    def authoritative_supply_record(
        self, mint: object, *, live_epoch_id: object = None,
    ) -> Optional[Dict[str, Any]]:
        """Return one conflict-free current-epoch authenticated supply proof.

        Multiple retries may persist equivalent tickets.  They are one supply
        fact only when their exact raw amount and decimals agree; disagreement
        fails closed instead of selecting the newest convenient value.
        """

        token = _canonical_mint(mint)
        requested_epoch = (
            live_epoch_id if isinstance(live_epoch_id, str) and live_epoch_id
            else self._active_live_epoch_id)
        if token is None or requested_epoch is None:
            return None
        with self._lock:
            state = self._mints.get(token)
            if not isinstance(state, Mapping):
                return None
            eligible = [dict(value) for value in (
                state.get("authoritative_supply_observations") or {}).values()
                if isinstance(value, Mapping)
                and value.get("mint") == token
                and value.get("live_epoch_id") == requested_epoch
                and value.get("source") == "HELIUS_AUTHENTICATED_GET_TOKEN_SUPPLY"
                and value.get("validation_result") == "SUPPLY_VALID"]
            identities = {
                (value.get("raw_amount"), value.get("decimals"),
                 value.get("normalized_supply"))
                for value in eligible}
            if len(identities) != 1:
                return None
            return max(
                eligible,
                key=lambda value: (
                    int(value.get("rpc_context_slot") or -1),
                    str(value.get("request_ticket_id") or "")),
            )

    def register_pool(
        self,
        *,
        mint: object,
        pool_address: object,
        quote_mint: object,
        creation_timestamp: object = None,
    ) -> bool:
        if self._quarantined:
            return False
        token = _canonical_mint(mint)
        if token is None or not isinstance(pool_address, str) or not pool_address:
            return False
        if not isinstance(quote_mint, str) or not quote_mint:
            return False
        created = _iso(creation_timestamp)
        with self._lock:
            state = self._state(token)
            prior_pool = state.get("pool_address")
            prior_quote = state.get("quote_mint")
            if prior_pool not in (None, pool_address) or prior_quote not in (None, quote_mint):
                return False
            changed = prior_pool is None or prior_quote is None
            state["pool_address"] = pool_address
            state["quote_mint"] = quote_mint
            if created is not None:
                prior_created = state.get("pool_created_at")
                if prior_created is None or (_epoch(created) or 0) < (_epoch(prior_created) or 0):
                    state["pool_created_at"] = created
                    changed = True
            if changed:
                state["last_updated_at"] = _now_iso()
                self._persist_locked()
        return True

    def register_migration_pair(
        self,
        *,
        mint: object,
        pool_address: object,
        quote_mint: object,
        anchor_utc: object = None,
        tracking_started_at_utc: object = None,
    ) -> bool:
        """Bind ONE authenticated migration pair identity to a mint.

        Identical to :meth:`register_pool` in refusal semantics (a conflicting
        pool or quote fails closed; a repeat of the same identity is
        idempotent) and additionally begins the process-scoped live-tracker
        coverage for the mint, so Path B eligibility starts the moment PHX2
        starts watching -- never retroactively.  ``tracking_started_at_utc``
        exists for offline replay of a recorded run (pinning when tracking
        actually began); production omits it and gets the wall clock.
        """

        registered = self.register_pool(
            mint=mint, pool_address=pool_address, quote_mint=quote_mint,
            creation_timestamp=anchor_utc)
        if registered:
            self.begin_live_tracking(
                mint, anchor_utc=anchor_utc,
                started_at_utc=tracking_started_at_utc)
        return registered

    def pool_identity(self, mint: object) -> Optional[Dict[str, Any]]:
        """The registered migration-pair identity for one mint, if any."""

        token = _canonical_mint(mint)
        if token is None:
            return None
        with self._lock:
            state = self._mints.get(token) or {}
            pool = state.get("pool_address")
            if not isinstance(pool, str) or not pool:
                return None
            return {
                "pool_address": pool,
                "quote_mint": state.get("quote_mint"),
                "pool_created_at": state.get("pool_created_at"),
            }

    def begin_live_tracking(
        self, mint: object, *, anchor_utc: object = None,
        started_at_utc: object = None,
    ) -> bool:
        """Start (idempotently) process-scoped live coverage for one mint."""

        token = _canonical_mint(mint)
        if token is None:
            return False
        started = _iso(started_at_utc) or self._hydration_now()
        with self._lock:
            entry = self._live_coverage.get(token)
            if entry is not None \
                    and entry.get("live_epoch_id") == self._active_live_epoch_id:
                return True
            anchor = _iso(anchor_utc)
            if anchor is None:
                state = self._mints.get(token) or {}
                anchor = state.get("pool_created_at")
            self._live_coverage[token] = {
                "live_epoch_id": self._active_live_epoch_id,
                "tracking_started_at_utc": started,
                "anchor_utc": anchor,
                "event_count": 0,
                "poll_count": 0,
                "last_observed_at_utc": None,
            }
        return True

    def _note_live_observation_locked(
        self, mint: str, *, kind: str, observed_at: object,
    ) -> None:
        entry = self._live_coverage.get(mint)
        if entry is None \
                or entry.get("live_epoch_id") != self._active_live_epoch_id:
            return
        counter = "event_count" if kind == "event" else "poll_count"
        entry[counter] = int(entry.get(counter) or 0) + 1
        observed = _iso(observed_at)
        if observed is not None:
            prior = _epoch(entry.get("last_observed_at_utc"))
            if prior is None or (_epoch(observed) or 0) >= prior:
                entry["last_observed_at_utc"] = observed

    def live_tracker_coverage(self, mint: object) -> Optional[Dict[str, Any]]:
        token = _canonical_mint(mint)
        if token is None:
            return None
        with self._lock:
            entry = self._live_coverage.get(token)
            return dict(entry) if entry is not None else None

    def observe_quote_price(
        self, quote_mint: object, price_usd: object, *, observed_at: object = None
    ) -> bool:
        if self._quarantined:
            return False
        if not isinstance(quote_mint, str) or not quote_mint:
            return False
        price = _decimal(price_usd)
        if price is None:
            return False
        with self._lock:
            self._quote_prices[quote_mint] = price
            changed = False
            for mint, state in self._mints.items():
                if state.get("quote_mint") != quote_mint:
                    continue
                pending_events = state.pop("pending_events", [])
                if isinstance(pending_events, list):
                    for pending in pending_events:
                        if isinstance(pending, dict):
                            changed = self._apply_pending_locked(
                                mint, state, pending, quote_price_usd=price,
                                priced_at=observed_at,
                            ) or changed
            if changed:
                self._persist_locked()
        return True

    def observe_event(
        self,
        *,
        mint: object,
        artifact: object,
        transaction_signature: object,
        event_index: object,
        quote_price_usd: object = None,
        last_updated_at: object = None,
    ) -> bool:
        """Accept one validated Buy/Sell event; return True on a new delivery.

        The return value denotes dedupe acceptance, not necessarily a numeric
        ATH increase.  A valid lower/out-of-order event is recorded as seen but
        cannot reduce either maximum.
        """

        if self._quarantined:
            return False
        token = _canonical_mint(mint)
        if token is None or not isinstance(artifact, PumpSwapReserveArtifact):
            return False
        if artifact.base_mint not in (None, token):
            return False
        if not isinstance(artifact.pool_address, str) or not artifact.pool_address:
            return False
        if not isinstance(artifact.quote_mint, str) or not artifact.quote_mint:
            return False
        if not isinstance(transaction_signature, str) or not transaction_signature:
            return False
        if isinstance(event_index, bool) or not isinstance(event_index, int) or event_index < 0:
            return False
        if artifact.base_supply is None or artifact.base_supply <= 0:
            return False
        if artifact.base_decimals is None or artifact.quote_decimals is None:
            return False
        if not (0 <= artifact.base_decimals <= 255 and 0 <= artifact.quote_decimals <= 255):
            return False
        event_key = f"{transaction_signature}:{event_index}"
        with self._lock:
            # The shared stream carries swaps for the whole program.  Track ATH
            # only after this exact newborn pool was registered from its create
            # event; otherwise unrelated traffic would grow durable state
            # without bound and could bind a mint to an inferred pool.
            state = self._mints.get(token)
            if not isinstance(state, dict):
                return False
            if event_key in state["seen_event_keys"]:
                return False
            if state.get("pool_address") != artifact.pool_address:
                return False
            if state.get("quote_mint") != artifact.quote_mint:
                return False
            state["seen_event_keys"][event_key] = artifact.observation_timestamp
            while len(state["seen_event_keys"]) > MAX_DURABLE_EVENT_DEDUPE_KEYS:
                state["seen_event_keys"].pop(next(iter(state["seen_event_keys"])))
            self._note_live_observation_locked(
                token, kind="event",
                observed_at=artifact.observation_timestamp)
            # Keep an exact per-event supply timeline for OHLCV conversion.  It
            # is bounded by the same durable dedupe set, not by process uptime.
            supply_record = {
                "timestamp": artifact.observation_timestamp,
                "supply_raw": str(artifact.base_supply),
                "base_decimals": artifact.base_decimals,
            }
            same_supply = next((
                (key, value) for key, value in state["supply_observations"].items()
                if isinstance(value, dict)
                and value.get("supply_raw") == supply_record["supply_raw"]
                and value.get("base_decimals") == supply_record["base_decimals"]
            ), None)
            if same_supply is None:
                state["supply_observations"][event_key] = supply_record
            elif ((_epoch(supply_record["timestamp"]) or float("inf"))
                  < (_epoch(same_supply[1].get("timestamp")) or float("inf"))):
                del state["supply_observations"][same_supply[0]]
                state["supply_observations"][event_key] = supply_record
            state["pool_address"] = state.get("pool_address") or artifact.pool_address
            state["quote_mint"] = state.get("quote_mint") or artifact.quote_mint
            pending = self._event_payload(artifact, transaction_signature, event_index)
            quote = _decimal(quote_price_usd)
            if quote is None and artifact.quote_mint:
                quote = self._quote_prices.get(artifact.quote_mint)
            if quote is None:
                # Price and market cap are separate maxima when supply can
                # vary, so retain both quote-denominated winners while waiting
                # for the shared quote-price cache (at most two events).
                candidates = [value for value in state.get("pending_events", [])
                              if isinstance(value, dict)] + [pending]
                winners = (
                    max(candidates, key=self._pending_price_rank),
                    max(candidates, key=self._pending_rank),
                )
                unique: Dict[Tuple[Any, Any], Dict[str, Any]] = {}
                for winner in winners:
                    unique[(winner.get("transaction_signature"),
                            winner.get("event_index"))] = winner
                state["pending_events"] = list(unique.values())
                state["last_updated_at"] = _iso(last_updated_at) or _now_iso()
                self._persist_locked()
                return True
            self._apply_pending_locked(
                token, state, pending, quote_price_usd=quote,
                priced_at=last_updated_at,
            )
            self._persist_locked()
        return True

    def observe_authoritative_supply(
        self,
        *,
        mint: object,
        raw_amount: object,
        decimals: object,
        normalized_supply: object,
        rpc_context_slot: object,
        fetched_at_utc: object,
        source: object,
        live_epoch_id: object,
        request_ticket_id: object,
        validation_result: object,
    ) -> bool:
        """Persist one exact authenticated ``getTokenSupply`` observation.

        The normalized value is recomputed from raw integer units here; the
        bridge cannot smuggle in a rounded UI value.  The request ticket is
        the durable dedupe/binding key and every provenance field travels into
        the restart checkpoint with the supply.
        """

        if self._quarantined:
            return False
        token = _canonical_mint(mint)
        timestamp = _iso(fetched_at_utc)
        if token is None or timestamp is None:
            return False
        if not isinstance(raw_amount, str) or not raw_amount.isdigit():
            return False
        if isinstance(decimals, bool) or not isinstance(decimals, int) \
                or not 0 <= decimals <= 255:
            return False
        if isinstance(rpc_context_slot, bool) \
                or not isinstance(rpc_context_slot, int) \
                or rpc_context_slot < 0:
            return False
        if not isinstance(live_epoch_id, str) or not live_epoch_id:
            return False
        if not isinstance(request_ticket_id, str) or not request_ticket_id:
            return False
        if source != "HELIUS_AUTHENTICATED_GET_TOKEN_SUPPLY" \
                or validation_result != "SUPPLY_VALID":
            return False
        try:
            raw = int(raw_amount)
            with localcontext() as ctx:
                ctx.prec = max(80, len(raw_amount) + decimals + 2)
                exact = Decimal(raw) / (Decimal(10) ** decimals)
            supplied = Decimal(str(normalized_supply))
        except (InvalidOperation, TypeError, ValueError):
            return False
        if not supplied.is_finite() or supplied < 0 or supplied != exact:
            return False
        record = {
            "mint": token,
            "raw_amount": str(raw),
            "decimals": decimals,
            "normalized_supply": format(exact, "f"),
            "rpc_context_slot": rpc_context_slot,
            "fetched_at_utc": timestamp,
            "source": source,
            "live_epoch_id": live_epoch_id,
            "request_ticket_id": request_ticket_id,
            "validation_result": validation_result,
        }
        with self._lock:
            state = self._state(token)
            observations = state.setdefault(
                "authoritative_supply_observations", {})
            if not isinstance(observations, dict):
                observations = {}
                state["authoritative_supply_observations"] = observations
            if request_ticket_id in observations:
                return False
            observations[request_ticket_id] = record
            while len(observations) > MAX_AUTHORITATIVE_SUPPLY_OBSERVATIONS:
                observations.pop(next(iter(observations)))
            state["last_updated_at"] = _now_iso()
            # A supply arriving after OHLCV may resolve an already accepted
            # price maximum immediately; no second market request is needed.
            self._resolve_locked(state)
            self._refresh_hydration_locked(state, mint=token)
            self._persist_locked()
        return True

    def observe_provider_current(
        self,
        *,
        mint: object,
        price_usd: object,
        observed_at: object,
        market_cap_usd: object = None,
        supply_at_observation: object = None,
        confirmed: bool = False,
        ingested_at: object = None,
    ) -> bool:
        if self._quarantined:
            return False
        token = _canonical_mint(mint)
        price = _decimal(price_usd)
        timestamp = _iso(observed_at)
        market_cap = _decimal(market_cap_usd)
        supply = _decimal(supply_at_observation)
        if token is None or price is None or timestamp is None:
            return False
        obs = self._observation(
            price=price,
            market_cap=market_cap,
            timestamp=timestamp,
            source=SOURCE_PAID_CURRENT,
            observation_type="PAID_CURRENT_PRICE",
            confirmed=confirmed,
            supply=_text(supply),
        )
        self._seal_observation(token, obs, ingested_at=ingested_at)
        with self._lock:
            state = self._state(token)
            self._note_live_observation_locked(
                token, kind="poll", observed_at=timestamp)
            # One response that carries BOTH a market cap and a price implies
            # the provider's own circulating supply at that instant.  Recording
            # it here (from that single observation, never across two) is what
            # lets a later migration-anchored candle high become a market cap
            # for a mint PHX2 has no swap events for.
            self._record_provider_supply_locked(
                state, market_cap=market_cap, price=price, timestamp=timestamp)
            changed = self._merge_locked(state, obs)
            if changed:
                self._persist_locked()
            return changed

    @staticmethod
    def _record_provider_supply_locked(
        state: Dict[str, Any], *, market_cap: Optional[Decimal],
        price: Optional[Decimal], timestamp: str,
    ) -> None:
        if market_cap is None or price is None or price <= 0:
            return
        supply = market_cap / price
        if not supply.is_finite() or supply <= 0:
            return
        observations = state.setdefault("provider_supply_observations", {})
        if not isinstance(observations, dict):
            observations = {}
            state["provider_supply_observations"] = observations
        record = {"timestamp": timestamp, "supply": _text(supply)}
        existing = next((
            (key, value) for key, value in observations.items()
            if isinstance(value, dict) and value.get("supply") == record["supply"]
        ), None)
        if existing is None:
            observations[timestamp] = record
        elif ((_epoch(timestamp) or float("inf"))
              < (_epoch(existing[1].get("timestamp")) or float("inf"))):
            del observations[existing[0]]
            observations[timestamp] = record
        while len(observations) > MAX_PROVIDER_SUPPLY_OBSERVATIONS:
            observations.pop(next(iter(observations)))

    def _candle_high_observation_locked(
        self,
        token: str,
        state: Dict[str, Any],
        *,
        price: Decimal,
        timestamp: str,
        source: str,
        observation_type: str,
        history_complete: bool,
        interval: object,
        time_from_unix: object,
        time_to_unix: object,
        ingested_at: object = None,
    ) -> Dict[str, Any]:
        """Build ONE sealed candle-high observation with supply conversion.

        Shared by the legacy token-OHLCV path and the canonical V3 pair path
        so both convert a candle high with the identical supply-resolution
        preference order and provenance stamps.
        """

        supply_tokens_dec, supply_basis = (
            self._supply_tokens_for_timestamp_locked(state, timestamp))
        market_cap: Optional[Decimal] = None
        supply_tokens: Optional[str] = None
        if supply_tokens_dec is not None:
            market_cap = price * supply_tokens_dec
            supply_tokens = _text(supply_tokens_dec)
        obs = self._observation(
            price=price,
            market_cap=market_cap,
            timestamp=timestamp,
            source=source,
            observation_type=observation_type,
            confirmed=bool(history_complete),
            supply=supply_tokens,
        )
        obs["ohlcv_interval"] = str(interval)
        obs["ohlcv_time_from_unix"] = int(time_from_unix)
        obs["ohlcv_time_to_unix"] = int(time_to_unix)
        obs["ohlcv_history_complete"] = bool(history_complete)
        obs["supply_basis"] = supply_basis
        if supply_basis == SUPPLY_BASIS_AUTHORITATIVE_RPC:
            provenance = self._authoritative_supply_provenance_locked(
                state, supply_tokens_dec)
            if provenance is not None:
                obs["supply_live_epoch_id"] = provenance.get(
                    "live_epoch_id")
                obs["supply_request_ticket_id"] = provenance.get(
                    "request_ticket_id")
                obs["supply_rpc_context_slot"] = provenance.get(
                    "rpc_context_slot")
        self._seal_observation(token, obs, ingested_at=ingested_at)
        return obs

    def observe_ohlcv_high(
        self,
        *,
        mint: object,
        high_price_usd: object,
        candle_timestamp: object,
        history_complete: bool,
        interval: object,
        time_from_unix: object,
        time_to_unix: object,
        ingested_at: object = None,
    ) -> bool:
        if self._quarantined:
            return False
        token = _canonical_mint(mint)
        price = _decimal(high_price_usd)
        timestamp = _iso(candle_timestamp)
        if token is None or price is None or timestamp is None:
            return False
        with self._lock:
            state = self._state(token)
            obs = self._candle_high_observation_locked(
                token, state,
                price=price,
                timestamp=timestamp,
                source=SOURCE_PAID_OHLCV,
                observation_type="PAID_OHLCV_HIGH",
                history_complete=bool(history_complete),
                interval=interval,
                time_from_unix=time_from_unix,
                time_to_unix=time_to_unix,
                ingested_at=ingested_at,
            )
            changed = self._merge_locked(state, obs)
            prior = state.get("ohlcv_coverage")
            prior_complete = bool(
                isinstance(prior, Mapping)
                and prior.get("history_complete") is True)
            if bool(history_complete) or not prior_complete:
                # A PARTIAL single-page observation (the passive transport
                # observer) may contribute a maximum but must never overwrite a
                # window already PROVEN complete -- that would silently
                # un-hydrate a verified candidate on the next compose.  A
                # complete window that no longer reaches the present is aged
                # out by ATH_HYDRATION_WINDOW_STALE instead.
                state["ohlcv_coverage"] = {
                    "interval": str(interval),
                    "time_from_unix": int(time_from_unix),
                    "time_to_unix": int(time_to_unix),
                    "history_complete": bool(history_complete),
                    "last_attempted_at": _now_iso(),
                }
            self._refresh_hydration_locked(state, mint=token)
            self._persist_locked()
            return changed

    # ---- canonical V3 pair-history state (2026-08-03) ---------------------

    @staticmethod
    def _new_v3_state() -> Dict[str, Any]:
        return {
            "schema_version": ATH_V3_STATE_SCHEMA_VERSION,
            "pair_address": None,
            "quote_mint": None,
            "live_epoch_id": None,
            "anchor_unix": None,
            "coarse_interval": ATH_V3_COARSE_INTERVAL,
            "refine_interval": ATH_V3_REFINE_INTERVAL,
            "outlier_mode": None,
            "window_from_unix": None,
            "window_to_unix": None,
            "cursor_unix": None,
            "history_complete": False,
            "candle_count": 0,
            "coarse_peak": None,
            "refined_peak": None,
            "usd_peak": None,
            "pending_reason": None,
            "pending_detail": None,
            "last_attempt_at_utc": None,
            "completed_at_utc": None,
            "divergence": None,
            "request_ticket_ids": [],
            "evidence_digest": None,
        }

    def _v3_state_locked(self, state: Dict[str, Any]) -> Dict[str, Any]:
        v3 = state.get("ath_v3_pair")
        if not isinstance(v3, dict):
            v3 = self._new_v3_state()
            state["ath_v3_pair"] = v3
        elif v3.get("live_epoch_id") != self._active_live_epoch_id:
            # Live-only epoch policy: a prior epoch's V3 cursor/coverage is a
            # different eligibility domain and is never rebound.  Prior
            # numeric maxima remain in the record's ordinary evidence; only
            # the V3 eligibility state restarts.
            v3 = self._new_v3_state()
            state["ath_v3_pair"] = v3
        return v3

    @staticmethod
    def _v3_retain_tickets(v3: Dict[str, Any], ticket_ids: object) -> None:
        if not isinstance(ticket_ids, (list, tuple)):
            return
        retained = list(v3.get("request_ticket_ids") or [])
        for ticket in ticket_ids:
            if isinstance(ticket, str) and ticket:
                retained.append(ticket)
        v3["request_ticket_ids"] = retained[-ATH_V3_MAX_RETAINED_TICKETS:]

    def v3_pair_state(self, mint: object) -> Optional[Dict[str, Any]]:
        """Current-epoch V3 pair-history state for one mint (copy)."""

        token = _canonical_mint(mint)
        if token is None:
            return None
        with self._lock:
            state = self._mints.get(token)
            if not isinstance(state, dict):
                return None
            v3 = state.get("ath_v3_pair")
            if not isinstance(v3, Mapping):
                return None
            if v3.get("live_epoch_id") != self._active_live_epoch_id:
                return None
            return deepcopy(dict(v3))

    def observe_v3_pair_ath(
        self,
        *,
        mint: object,
        pair_address: object,
        quote_mint: object = None,
        anchor_unix: object,
        window_from_unix: object,
        window_to_unix: object,
        cursor_unix: object = None,
        history_complete: bool,
        candles_received: object = 0,
        coarse_peak_native: object = None,
        coarse_peak_unix: object = None,
        refined_peak_native: object = None,
        refined_peak_unix: object = None,
        refine_interval: object = None,
        refined: bool = False,
        usd_peak_price: object = None,
        usd_peak_unix: object = None,
        usd_valuation_interval: object = None,
        usd_valuation_method: object = None,
        implied_quote_usd: object = None,
        outlier_mode: object = None,
        divergence: object = None,
        request_ticket_ids: object = (),
        attempted_at_utc: object = None,
        ingested_at: object = None,
    ) -> bool:
        """Commit ONE successful V3 pair-history attempt atomically.

        Window extension, cursor advance, peak improvement, the sealed USD
        observation merge, supply conversion, tuple resolution and the
        hydration verdict all happen under one lock acquisition, so the
        persisted price / market-cap / supply / timestamp / pair / source /
        completeness tuple can never mix two different attempts.

        Peaks are monotonic: a lower value can never displace a stored one,
        so provisional evidence can never overwrite a complete canonical
        maximum.  Failures never travel through here -- see
        :meth:`note_v3_pending`.
        """

        if self._quarantined:
            return False
        token = _canonical_mint(mint)
        if token is None or not isinstance(pair_address, str) \
                or not pair_address:
            return False
        try:
            anchor = int(anchor_unix)
            window_from = int(window_from_unix)
            window_to = int(window_to_unix)
        except (TypeError, ValueError):
            return False
        if anchor < 0 or window_from < 0 or window_to < window_from:
            return False
        attempted = _iso(attempted_at_utc) or self._hydration_now()
        with self._lock:
            state = self._state(token)
            registered_pool = state.get("pool_address")
            if registered_pool not in (None, pair_address):
                # Candles for a different pool must never update this mint.
                return False
            v3 = self._v3_state_locked(state)
            v3["pair_address"] = pair_address
            if isinstance(quote_mint, str) and quote_mint:
                v3["quote_mint"] = quote_mint
            v3["live_epoch_id"] = self._active_live_epoch_id
            v3["anchor_unix"] = anchor
            if outlier_mode is not None:
                v3["outlier_mode"] = str(outlier_mode)
            prior_from = v3.get("window_from_unix")
            v3["window_from_unix"] = (
                window_from if not isinstance(prior_from, int)
                or isinstance(prior_from, bool)
                else min(prior_from, window_from))
            prior_to = v3.get("window_to_unix")
            v3["window_to_unix"] = (
                window_to if not isinstance(prior_to, int)
                or isinstance(prior_to, bool)
                else max(prior_to, window_to))
            try:
                cursor = int(cursor_unix) if cursor_unix is not None else None
            except (TypeError, ValueError):
                cursor = None
            if cursor is not None:
                prior_cursor = v3.get("cursor_unix")
                v3["cursor_unix"] = (
                    cursor if not isinstance(prior_cursor, int)
                    or isinstance(prior_cursor, bool)
                    else max(prior_cursor, cursor))
            try:
                v3["candle_count"] = int(v3.get("candle_count") or 0) + max(
                    0, int(candles_received))
            except (TypeError, ValueError):
                pass
            if bool(history_complete):
                v3["history_complete"] = True
                if v3.get("completed_at_utc") is None:
                    v3["completed_at_utc"] = attempted
            coarse_value = _decimal(coarse_peak_native)
            if coarse_value is not None:
                prior_peak = v3.get("coarse_peak")
                prior_value = (_decimal(prior_peak.get("native_high"))
                               if isinstance(prior_peak, Mapping) else None)
                if prior_value is None or coarse_value > prior_value:
                    v3["coarse_peak"] = {
                        "native_high": _text(coarse_value),
                        "unix_time": (int(coarse_peak_unix)
                                      if coarse_peak_unix is not None else None),
                        "interval": v3.get("coarse_interval"),
                    }
            refined_value = _decimal(refined_peak_native)
            if refined_value is not None:
                prior_peak = v3.get("refined_peak")
                prior_value = (_decimal(prior_peak.get("native_high"))
                               if isinstance(prior_peak, Mapping) else None)
                if prior_value is None or refined_value > prior_value:
                    v3["refined_peak"] = {
                        "native_high": _text(refined_value),
                        "unix_time": (int(refined_peak_unix)
                                      if refined_peak_unix is not None else None),
                        "interval": str(refine_interval
                                        or v3.get("refine_interval")),
                        "refined": bool(refined),
                    }
            changed = False
            usd_value = _decimal(usd_peak_price)
            if usd_value is not None:
                prior_peak = v3.get("usd_peak")
                prior_value = (_decimal(prior_peak.get("price_usd"))
                               if isinstance(prior_peak, Mapping) else None)
                usd_interval = str(
                    usd_valuation_interval or refine_interval
                    or v3.get("refine_interval"))
                usd_timestamp = _iso(usd_peak_unix)
                if usd_timestamp is not None and (
                        prior_value is None or usd_value > prior_value):
                    obs = self._candle_high_observation_locked(
                        token, state,
                        price=usd_value,
                        timestamp=usd_timestamp,
                        source=SOURCE_PAID_V3_PAIR,
                        observation_type="PAID_V3_PAIR_OHLCV_HIGH",
                        history_complete=bool(v3.get("history_complete")),
                        interval=usd_interval,
                        time_from_unix=v3["window_from_unix"],
                        time_to_unix=v3["window_to_unix"],
                        ingested_at=ingested_at,
                    )
                    changed = self._merge_locked(state, obs)
                    v3["usd_peak"] = {
                        "price_usd": _text(usd_value),
                        "unix_time": (int(usd_peak_unix)
                                      if usd_peak_unix is not None else None),
                        "interval": usd_interval,
                        "implied_quote_usd": _text(
                            _decimal(implied_quote_usd)),
                        "method": (str(usd_valuation_method)
                                   if usd_valuation_method else None),
                        "validated": True,
                    }
                    v3["evidence_digest"] = obs.get("evidence_digest")
            if isinstance(divergence, Mapping):
                v3["divergence"] = dict(divergence)
            v3["pending_reason"] = None
            v3["pending_detail"] = None
            v3["last_attempt_at_utc"] = attempted
            self._v3_retain_tickets(v3, request_ticket_ids)
            state["last_updated_at"] = _now_iso()
            self._resolve_locked(state)
            self._refresh_hydration_locked(state, mint=token)
            self._persist_locked()
        return changed

    def note_v3_pending(
        self,
        mint: object,
        reason: object,
        *,
        pending_detail: object = None,
        request_ticket_ids: object = (),
        attempted_at_utc: object = None,
    ) -> Dict[str, Any]:
        """Record ONE failed/incomplete V3 attempt with its specific reason.

        Never touches window coverage, cursors or peaks: a transient failure
        cannot regress proven evidence, it only names why the candidate is
        still waiting.
        """

        token = _canonical_mint(mint)
        if token is None or reason not in ATH_V3_PENDING_REASONS:
            return {}
        attempted = _iso(attempted_at_utc) or self._hydration_now()
        with self._lock:
            state = self._state(token)
            v3 = self._v3_state_locked(state)
            v3["live_epoch_id"] = self._active_live_epoch_id
            v3["pending_reason"] = reason
            v3["pending_detail"] = (
                str(pending_detail)[:160] if pending_detail else None)
            v3["last_attempt_at_utc"] = attempted
            self._v3_retain_tickets(v3, request_ticket_ids)
            self._refresh_hydration_locked(state, mint=token)
            self._persist_locked()
            return deepcopy(dict(v3))

    def record_ohlcv_coverage(
        self,
        *,
        mint: object,
        interval: object,
        time_from_unix: object,
        time_to_unix: object,
        history_complete: bool,
        pages: object,
    ) -> bool:
        if self._quarantined:
            return False
        token = _canonical_mint(mint)
        try:
            start = int(time_from_unix)
            end = int(time_to_unix)
            page_count = int(pages)
        except (TypeError, ValueError):
            return False
        if token is None or start < 0 or end < start or page_count < 0:
            return False
        with self._lock:
            state = self._state(token)
            state["ohlcv_coverage"] = {
                "interval": str(interval),
                "time_from_unix": start,
                "time_to_unix": end,
                "history_complete": bool(history_complete),
                "pages": page_count,
                "last_attempted_at": _now_iso(),
            }
            state["last_updated_at"] = _now_iso()
            self._refresh_hydration_locked(state, mint=token)
            self._persist_locked()
        return True

    # ---- post-migration hydration lifecycle -------------------------------

    def _hydration_now(self) -> str:
        if self._hydration_now_fn is None:
            return _now_iso()
        try:
            value = _iso(self._hydration_now_fn())
        except Exception:
            return _now_iso()
        return value or _now_iso()

    def _refresh_hydration_locked(
        self, state: Dict[str, Any], *, mint: Optional[str] = None,
    ) -> None:
        """Recompute the hydration verdict, preserving retry bookkeeping."""

        prior = state.get("ath_hydration")
        prior = dict(prior) if isinstance(prior, Mapping) else {}
        detail = evaluate_ath_hydration_detail(
            state, now_utc=self._hydration_now(),
            active_live_epoch_id=self._active_live_epoch_id,
            live_coverage=(self._live_coverage.get(mint)
                           if mint is not None else None))
        status, reason = detail["status"], detail["reason"]
        v3 = state.get("ath_v3_pair")
        v3 = v3 if isinstance(v3, Mapping) else {}
        # The canonical window is the V3 pair window when one exists; the
        # legacy token-OHLCV coverage remains visible as diagnostic history.
        coverage = state.get("ohlcv_coverage")
        coverage = coverage if isinstance(coverage, Mapping) else {}
        if v3.get("window_from_unix") is not None:
            coverage = {
                "interval": v3.get("coarse_interval"),
                "time_from_unix": v3.get("window_from_unix"),
                "time_to_unix": v3.get("window_to_unix"),
                "history_complete": v3.get("history_complete"),
                "pages": coverage.get("pages"),
            }
        anchor = state.get("pool_created_at")
        anchor_epoch = _epoch(anchor)
        window_from = coverage.get("time_from_unix")
        window_to = coverage.get("time_to_unix")
        # Which part of the required post-migration window is still unproven.
        # Reported rather than inferred, so an operator can tell an indexing
        # delay from a genuinely truncated fetch.
        missing: list = []
        if anchor_epoch is not None:
            if not isinstance(window_from, int) or isinstance(window_from, bool):
                missing.append({"from_unix": int(anchor_epoch),
                                "to_unix": None, "kind": "WINDOW_NOT_FETCHED"})
            else:
                if window_from > anchor_epoch + (
                        ATH_HYDRATION_ANCHOR_TOLERANCE_SECONDS):
                    missing.append({"from_unix": int(anchor_epoch),
                                    "to_unix": int(window_from),
                                    "kind": "PRE_WINDOW_GAP"})
                now_epoch = _epoch(self._hydration_now())
                if (isinstance(window_to, int)
                        and not isinstance(window_to, bool)
                        and now_epoch is not None
                        and (now_epoch - window_to)
                        > ATH_HYDRATION_MAX_WINDOW_LAG_SECONDS):
                    missing.append({"from_unix": int(window_to),
                                    "to_unix": int(now_epoch),
                                    "kind": "POST_WINDOW_GAP"})
        state["ath_hydration"] = {
            "status": status,
            "reason": reason,
            "anchor_utc": anchor,
            "interval": coverage.get("interval"),
            "window_from_unix": window_from,
            "window_to_unix": window_to,
            "history_complete": bool(coverage.get("history_complete") is True),
            "attempt_count": int(prior.get("attempt_count") or 0),
            "last_attempt_at_utc": prior.get("last_attempt_at_utc"),
            "next_attempt_at_utc": (
                None if status == ATH_HYDRATION_COMPLETE
                else prior.get("next_attempt_at_utc")),
            # ---- explicit scheduling + coverage telemetry (2026-08-02) ---
            "scheduled": bool(prior.get("scheduled")),
            "scheduled_at_utc": prior.get("scheduled_at_utc"),
            "pages_requested": coverage.get("pages"),
            "earliest_candle_unix": window_from,
            "latest_candle_unix": window_to,
            "missing_ranges": missing,
            # A scheduled candidate the provider has simply not indexed yet
            # is PENDING and honest about why; it is never COMPLETE and never
            # composes, but it is also not a fault.
            "indexing_pending": bool(
                status != ATH_HYDRATION_COMPLETE
                and bool(prior.get("scheduled"))
                and int(prior.get("attempt_count") or 0) > 0
                and reason in (ATH_HYDRATION_WINDOW_INCOMPLETE,
                               ATH_HYDRATION_WINDOW_STARTS_AFTER_MIGRATION,
                               ATH_V3_HISTORY_INCOMPLETE)),
            "completion_verdict": status,
            # Which allowed path proved (or would prove) the maximum.
            "ath_canonical_source": detail["canonical_source"],
            "v3_pair_address": v3.get("pair_address"),
            "v3_history_complete": bool(v3.get("history_complete") is True),
            "v3_pending_reason": v3.get("pending_reason"),
            "v3_coarse_interval": v3.get("coarse_interval"),
            "v3_refine_interval": (
                (v3.get("refined_peak") or {}).get("interval")
                if isinstance(v3.get("refined_peak"), Mapping) else None),
            "v3_outlier_mode": v3.get("outlier_mode"),
            "resolved_ath_price": state.get("resolved_ath_price"),
            "resolved_ath_market_cap": state.get("resolved_ath_market_cap"),
        }

    def schedule_hydration(
        self, mint: object, *, anchor_utc: object = None,
        scheduled_at_utc: object = None,
    ) -> Dict[str, Any]:
        """Mark ONE actively tracked candidate as owed bounded ATH hydration.

        Before 2026-08-02 hydration was driven ONLY as a side effect of the
        capacity-bounded pricing tail (32 slots).  A run tracking 145 mints
        therefore left most candidates -- including every late-admitted
        restart-backfill candidate -- at ``ATH_HYDRATION_NEVER_ATTEMPTED``
        for the whole run, which is exactly what happened to the turtleneck
        candidate: correctly discovered, correctly anchored, never hydrated,
        and so permanently unsendable.

        Scheduling is idempotent, records WHEN the obligation was created,
        and makes the candidate immediately due.  It fetches nothing.
        """

        token = _canonical_mint(mint)
        if token is None:
            return {}
        scheduled = _iso(scheduled_at_utc) or self._hydration_now()
        with self._lock:
            state = self._state(token)
            anchor = _iso(anchor_utc)
            if anchor is not None and state.get("pool_created_at") is None:
                state["pool_created_at"] = anchor
            self._refresh_hydration_locked(state, mint=token)
            hydration = state["ath_hydration"]
            if not hydration.get("scheduled"):
                hydration["scheduled"] = True
                hydration["scheduled_at_utc"] = scheduled
                state["last_updated_at"] = _now_iso()
                self._persist_locked()
            return dict(hydration)

    def pending_hydration_mints(self) -> Tuple[str, ...]:
        """Every scheduled mint whose hydration is not yet COMPLETE."""

        with self._lock:
            mints = list(self._mints)
        pending = []
        for mint in mints:
            hydration = self.hydration(mint)
            if hydration.get("scheduled") and hydration.get(
                    "status") != ATH_HYDRATION_COMPLETE:
                pending.append(mint)
        return tuple(pending)

    def note_hydration_attempt(
        self, mint: object, *, attempted_at_utc: object = None,
    ) -> Dict[str, Any]:
        """Record one bounded hydration attempt and schedule the next retry.

        Called by the driver AFTER an attempt actually reached the provider, so
        a TTL-suppressed no-op never inflates the backoff.  Returns the
        refreshed hydration state (never raises).
        """

        token = _canonical_mint(mint)
        if token is None:
            return {}
        attempted = _iso(attempted_at_utc) or _now_iso()
        with self._lock:
            state = self._state(token)
            self._refresh_hydration_locked(state, mint=token)
            hydration = state["ath_hydration"]
            hydration["attempt_count"] = int(
                hydration.get("attempt_count") or 0) + 1
            hydration["last_attempt_at_utc"] = attempted
            if hydration["status"] == ATH_HYDRATION_COMPLETE:
                hydration["next_attempt_at_utc"] = None
            else:
                base = _epoch(attempted) or 0.0
                hydration["next_attempt_at_utc"] = _iso(
                    base + ath_hydration_backoff_seconds(
                        hydration["attempt_count"]))
            self._persist_locked()
            return dict(hydration)

    def hydration(self, mint: object) -> Dict[str, Any]:
        """Current hydration state for one mint (recomputed on read)."""

        token = _canonical_mint(mint)
        if token is None:
            return {"status": ATH_HYDRATION_PENDING,
                    "reason": ATH_HYDRATION_NEVER_ATTEMPTED}
        with self._lock:
            state = self._mints.get(token)
            if not isinstance(state, dict):
                return {"status": ATH_HYDRATION_PENDING,
                        "reason": ATH_HYDRATION_NEVER_ATTEMPTED}
            self._refresh_hydration_locked(state, mint=token)
            return dict(state["ath_hydration"])

    def hydration_due(self, mint: object, *, now_utc: object = None) -> bool:
        """True when a PENDING candidate's bounded backoff has elapsed."""

        hydration = self.hydration(mint)
        if hydration.get("status") == ATH_HYDRATION_COMPLETE:
            return False
        next_at = _epoch(hydration.get("next_attempt_at_utc"))
        if next_at is None:
            return True
        now = _epoch(now_utc) if now_utc is not None \
            else _epoch(self._hydration_now())
        return now is None or now >= next_at

    def snapshot(self, mint: object) -> Optional[Dict[str, Any]]:
        token = _canonical_mint(mint)
        if token is None:
            return None
        with self._lock:
            state = self._mints.get(token)
            if not state or (state.get("ath_price") is None and state.get("ath_market_cap") is None):
                return None
            # Resolve BEFORE the hydration verdict: hydration completeness is
            # partly a statement about the resolved tuple.
            self._resolve_locked(state)
            self._refresh_hydration_locked(state, mint=token)
            out = deepcopy(state)
        out.pop("seen_event_keys", None)
        out.pop("supply_observations", None)
        out.pop("authoritative_supply_observations", None)
        out.pop("provider_supply_observations", None)
        out.pop("pending_events", None)
        out["token_mint"] = token
        out["ath_price_usd"] = out.get("ath_price")
        out["ath_market_cap_usd"] = out.get("ath_market_cap")
        out["ath_observed_at_utc"] = out.get("ath_timestamp")
        out["ath_provider"] = out.get("ath_provider")
        out["ath_confirmed"] = out.get("ath_status") == STATUS_CONFIRMED
        # Diagnostic only.  Two independently maximized arms disagreeing is
        # now a fact ABOUT the raw evidence, published for observability,
        # and no longer an automatic rejection of a coherent resolved tuple.
        out["ath_split_arm_disagreement"] = bool(
            _decimal(out.get("ath_price")) is not None
            and _decimal(out.get("ath_market_cap_evidence_price_usd"))
            is not None
            and _decimal(out.get("ath_price"))
            != _decimal(out.get("ath_market_cap_evidence_price_usd")))
        out["ath_resolved_valid"] = ath_resolved_tuple_is_valid(out)
        # Post-migration completeness travels WITH the maximum, so no consumer
        # can read the value without also reading whether it is proven.
        hydration = out.get("ath_hydration")
        hydration = hydration if isinstance(hydration, Mapping) else {}
        out["ath_hydration_status"] = hydration.get(
            "status", ATH_HYDRATION_PENDING)
        out["ath_hydration_reason"] = hydration.get(
            "reason", ATH_HYDRATION_NEVER_ATTEMPTED)
        out["ath_post_migration_complete"] = (
            out["ath_hydration_status"] == ATH_HYDRATION_COMPLETE)
        # Which allowed path proved the maximum (V3 pair canonical, or the
        # process-scoped live tracker while V3 is unavailable).
        out["ath_canonical_source"] = hydration.get("ath_canonical_source")
        return out

    def pool_created_at(self, mint: object) -> Optional[str]:
        token = _canonical_mint(mint)
        if token is None:
            return None
        with self._lock:
            state = self._mints.get(token) or {}
            value = state.get("pool_created_at")
            return value if isinstance(value, str) else None

    def all_snapshots(self) -> Dict[str, Dict[str, Any]]:
        with self._lock:
            mints = list(self._mints)
        return {mint: snap for mint in mints if (snap := self.snapshot(mint)) is not None}

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            now_epoch = _epoch(self._hydration_now())
            v3_complete = 0
            v3_incomplete = 0
            v3_waiting = 0
            v3_oldest_wait: Optional[float] = None
            for state in self._mints.values():
                hydration = state.get("ath_hydration")
                hydration = (hydration if isinstance(hydration, Mapping)
                             else {})
                v3 = state.get("ath_v3_pair")
                v3 = v3 if isinstance(v3, Mapping) else {}
                current_epoch_v3 = (
                    bool(v3)
                    and v3.get("live_epoch_id") == self._active_live_epoch_id)
                if current_epoch_v3 and v3.get("history_complete") is True:
                    v3_complete += 1
                if not hydration.get("scheduled"):
                    continue
                if hydration.get("status") == ATH_HYDRATION_COMPLETE:
                    continue
                v3_waiting += 1
                if not (current_epoch_v3
                        and v3.get("history_complete") is True):
                    v3_incomplete += 1
                scheduled_at = _epoch(hydration.get("scheduled_at_utc"))
                if scheduled_at is not None and now_epoch is not None:
                    wait = max(0.0, now_epoch - scheduled_at)
                    if v3_oldest_wait is None or wait > v3_oldest_wait:
                        v3_oldest_wait = wait
            return {
                "ath_mints": sum(1 for state in self._mints.values()
                                 if state.get("ath_price") is not None),
                "ath_event_dedupe_keys": sum(
                    len(state.get("seen_event_keys") or {}) for state in self._mints.values()),
                "ath_equal_evidence_reobserved": sum(
                    int(state.get("ath_equal_evidence_reobserved_count") or 0)
                    for state in self._mints.values()),
                "ath_pending_events": sum(
                    len(state.get("pending_events") or [])
                    for state in self._mints.values()),
                "ath_authoritative_supply_observations": sum(
                    len(state.get("authoritative_supply_observations") or {})
                    for state in self._mints.values()),
                "ath_resolved_tuples": sum(
                    1 for state in self._mints.values()
                    if state.get("resolved") is True),
                # ---- V3 pair-history plane telemetry (2026-08-03) --------
                "ath_v3_completed_histories": v3_complete,
                "ath_v3_incomplete_histories": v3_incomplete,
                "ath_v3_waiting_candidates": v3_waiting,
                "ath_v3_oldest_wait_seconds": (
                    round(v3_oldest_wait, 3)
                    if v3_oldest_wait is not None else None),
                "ath_live_tracked_mints": len(self._live_coverage),
            }

    def _state(self, mint: str) -> Dict[str, Any]:
        return self._mints.setdefault(mint, _new_mint_state())

    @staticmethod
    def _event_payload(
        artifact: PumpSwapReserveArtifact, signature: str, event_index: int
    ) -> Dict[str, Any]:
        return {
            "raw_quote_reserves": str(artifact.raw_quote_reserves),
            "virtual_quote_reserves": str(artifact.virtual_quote_reserves),
            "effective_quote_reserves": str(artifact.effective_quote_reserves),
            "base_reserves": str(artifact.base_reserves),
            "base_supply": str(artifact.base_supply),
            "base_decimals": artifact.base_decimals,
            "quote_decimals": artifact.quote_decimals,
            "timestamp": artifact.observation_timestamp,
            "transaction_signature": signature,
            "event_index": event_index,
            "event_side": artifact.event_side,
            "pool_address": artifact.pool_address,
            "quote_mint": artifact.quote_mint,
            "decoder_layout_version": artifact.decoder_layout_version,
        }

    @staticmethod
    def _pending_rank(pending: Mapping[str, Any]) -> Decimal:
        try:
            artifact = PumpSwapReserveArtifact(
                raw_quote_reserves=int(pending["raw_quote_reserves"]),
                virtual_quote_reserves=int(pending["virtual_quote_reserves"]),
                effective_quote_reserves=int(pending["effective_quote_reserves"]),
                base_reserves=int(pending["base_reserves"]),
                reserve_source="PENDING_EVENT",
                observation_timestamp=str(pending["timestamp"]),
                decoder_layout_version=str(pending["decoder_layout_version"]),
                base_decimals=int(pending["base_decimals"]),
                quote_decimals=int(pending["quote_decimals"]),
                base_supply=int(pending["base_supply"]),
            )
            supply = Decimal(artifact.base_supply) / (Decimal(10) ** artifact.base_decimals)
            return reserve_price_quote_units(artifact) * supply
        except (KeyError, TypeError, ValueError, PumpSwapReserveError):
            return Decimal(0)

    @staticmethod
    def _pending_price_rank(pending: Mapping[str, Any]) -> Decimal:
        try:
            artifact = PumpSwapReserveArtifact(
                raw_quote_reserves=int(pending["raw_quote_reserves"]),
                virtual_quote_reserves=int(pending["virtual_quote_reserves"]),
                effective_quote_reserves=int(pending["effective_quote_reserves"]),
                base_reserves=int(pending["base_reserves"]),
                reserve_source="PENDING_EVENT",
                observation_timestamp=str(pending["timestamp"]),
                decoder_layout_version=str(pending["decoder_layout_version"]),
                base_decimals=int(pending["base_decimals"]),
                quote_decimals=int(pending["quote_decimals"]),
                base_supply=int(pending["base_supply"]),
            )
            return reserve_price_quote_units(artifact)
        except (KeyError, TypeError, ValueError, PumpSwapReserveError):
            return Decimal(0)

    def _apply_pending_locked(
        self,
        mint: str,
        state: Dict[str, Any],
        pending: Mapping[str, Any],
        *,
        quote_price_usd: Decimal,
        priced_at: object,
    ) -> bool:
        try:
            artifact = PumpSwapReserveArtifact(
                raw_quote_reserves=int(pending["raw_quote_reserves"]),
                virtual_quote_reserves=int(pending["virtual_quote_reserves"]),
                effective_quote_reserves=int(pending["effective_quote_reserves"]),
                base_reserves=int(pending["base_reserves"]),
                reserve_source=SOURCE_PUMPSWAP_EVENT,
                observation_timestamp=str(pending["timestamp"]),
                decoder_layout_version=str(pending["decoder_layout_version"]),
                pool_address=pending.get("pool_address"),
                base_mint=mint,
                quote_mint=pending.get("quote_mint"),
                base_decimals=int(pending["base_decimals"]),
                quote_decimals=int(pending["quote_decimals"]),
                event_side=pending.get("event_side"),
                base_supply=int(pending["base_supply"]),
            )
            price = reserve_price_usd(artifact, quote_price_usd=quote_price_usd)
            market_cap = reserve_market_cap_usd(
                artifact, quote_price_usd=quote_price_usd)
            supply_tokens = Decimal(artifact.base_supply) / (
                Decimal(10) ** artifact.base_decimals)
        except (KeyError, TypeError, ValueError, PumpSwapReserveError):
            return False
        obs = self._observation(
            price=price,
            market_cap=market_cap,
            timestamp=str(pending["timestamp"]),
            source=SOURCE_PUMPSWAP_EVENT,
            observation_type=f"PUMPSWAP_{str(pending.get('event_side') or 'EVENT')}_EFFECTIVE_RESERVES",
            confirmed=True,
            supply=_text(supply_tokens),
        )
        obs.update({
            "transaction_signature": pending.get("transaction_signature"),
            "event_index": pending.get("event_index"),
            "raw_quote_reserves": pending.get("raw_quote_reserves"),
            "virtual_quote_reserves": pending.get("virtual_quote_reserves"),
            "effective_quote_reserves": pending.get("effective_quote_reserves"),
            "base_reserves": pending.get("base_reserves"),
            "quote_price_usd": _text(quote_price_usd),
            "quote_price_observed_at": _iso(priced_at) or _now_iso(),
            "supply_basis": SUPPLY_BASIS_EVENT,
        })
        self._seal_observation(mint, obs)
        return self._merge_locked(state, obs)

    @staticmethod
    def _observation(
        *,
        price: Decimal,
        market_cap: Optional[Decimal],
        timestamp: str,
        source: str,
        observation_type: str,
        confirmed: bool,
        supply: Optional[str],
    ) -> Dict[str, Any]:
        return {
            "price": _text(price),
            "market_cap": _text(market_cap),
            "timestamp": timestamp,
            "provider": source,
            "observation_type": observation_type,
            "supply": supply,
            "status": STATUS_CONFIRMED if confirmed else STATUS_PROVISIONAL,
            "transaction_signature": None,
            "event_index": None,
            "raw_quote_reserves": None,
            "virtual_quote_reserves": None,
            "effective_quote_reserves": None,
            "base_reserves": None,
        }

    @staticmethod
    def _seal_observation(
        mint: str, obs: Dict[str, Any], *, ingested_at: object = None
    ) -> None:
        obs["evidence_version"] = ATH_EVIDENCE_SCHEMA_VERSION
        obs["ingested_at_utc"] = _iso(ingested_at) or _now_iso()
        obs["evidence_digest"] = build_ath_evidence_digest(mint, obs)
        obs["observation_seal_version"] = ATH_OBSERVATION_SEAL_SCHEMA_VERSION
        obs["observation_seal_validated"] = obs["evidence_digest"] is not None
        obs["observation_seal_digest"] = build_ath_observation_seal_digest(mint, obs)

    def _merge_locked(self, state: Dict[str, Any], obs: Mapping[str, Any]) -> bool:
        price = _decimal(obs.get("price"))
        market_cap = _decimal(obs.get("market_cap"))
        if price is None:
            return False
        changed = False
        prior_price = _decimal(state.get("ath_price"))
        price_improves = prior_price is None or price > prior_price
        price_confirms = (
            prior_price is not None and price == prior_price
            and obs.get("status") == STATUS_CONFIRMED
            and (state.get("price_provenance") or {}).get("status") != STATUS_CONFIRMED
        )
        if price_improves or price_confirms:
            state["ath_price"] = _text(price)
            state["price_provenance"] = deepcopy(dict(obs))
            changed = True

        prior_mc = _decimal(state.get("ath_market_cap"))
        mc_improves = market_cap is not None and (prior_mc is None or market_cap > prior_mc)
        mc_confirms = (
            market_cap is not None and prior_mc is not None and market_cap == prior_mc
            and obs.get("status") == STATUS_CONFIRMED
            and state.get("ath_status") != STATUS_CONFIRMED
        )
        equal_authoritative_reobservation = (
            market_cap is not None and prior_mc is not None and market_cap == prior_mc
            and obs.get("evidence_digest") == state.get("ath_evidence_digest")
            and isinstance(obs.get("evidence_digest"), str)
            and (
                obs.get("status") == STATUS_CONFIRMED
                or obs.get("provider") == SOURCE_PAID_CURRENT
            )
            and obs.get("observation_seal_validated") is True
            and isinstance(obs.get("observation_seal_digest"), str)
        )
        # PHX2-E2E-005: a record migrated from the pre-evidence legacy schema
        # has an authoritative maximum but no source-evidence digest. An equal
        # authoritative re-observation of the SAME event identity may backfill
        # the missing evidence/observation seal — never the numeric ATH, never
        # a new crossing event, never a later dip tick.
        legacy_equal_seal_backfill = (
            market_cap is not None and prior_mc is not None
            and market_cap == prior_mc
            and state.get("ath_legacy_pre_evidence") is True
            and state.get("ath_evidence_digest") is None
            and isinstance(obs.get("evidence_digest"), str)
            and obs.get("observation_seal_validated") is True
            and isinstance(obs.get("observation_seal_digest"), str)
            and obs.get("timestamp") == state.get("ath_timestamp")
            and obs.get("provider") == state.get("ath_provider")
            and obs.get("observation_type") == state.get("ath_observation_type")
            and obs.get("status") == state.get("ath_status")
            and (state.get("ath_supply_at_observation") is None
                 or obs.get("supply") == state.get("ath_supply_at_observation"))
        )
        if mc_improves or mc_confirms:
            state["ath_market_cap"] = _text(market_cap)
            state["market_cap_provenance"] = deepcopy(dict(obs))
            state["ath_timestamp"] = obs.get("timestamp")
            state["ath_transaction_signature"] = obs.get("transaction_signature")
            state["ath_event_index"] = obs.get("event_index")
            state["ath_provider"] = obs.get("provider")
            state["ath_observation_type"] = obs.get("observation_type")
            state["ath_supply_at_observation"] = obs.get("supply")
            state["ath_raw_quote_reserves"] = obs.get("raw_quote_reserves")
            state["ath_virtual_quote_reserves"] = obs.get("virtual_quote_reserves")
            state["ath_effective_quote_reserves"] = obs.get("effective_quote_reserves")
            state["ath_base_reserves"] = obs.get("base_reserves")
            state["ath_ohlcv_interval"] = obs.get("ohlcv_interval")
            state["ath_ohlcv_time_from_unix"] = obs.get("ohlcv_time_from_unix")
            state["ath_ohlcv_time_to_unix"] = obs.get("ohlcv_time_to_unix")
            state["ath_ohlcv_history_complete"] = obs.get(
                "ohlcv_history_complete")
            state["ath_market_cap_evidence_price_usd"] = obs.get("price")
            state["ath_supply_basis"] = (
                obs.get("supply_basis")
                if obs.get("supply_basis") in VALID_SUPPLY_BASES else None)
            state["ath_ingested_at_utc"] = obs.get("ingested_at_utc")
            state["ath_evidence_version"] = obs.get("evidence_version")
            state["ath_evidence_digest"] = obs.get("evidence_digest")
            state["ath_source_evidence_version"] = obs.get("evidence_version")
            state["ath_source_evidence_digest"] = obs.get("evidence_digest")
            state["ath_observation_seal_version"] = obs.get(
                "observation_seal_version")
            state["ath_observation_seal_digest"] = obs.get(
                "observation_seal_digest")
            state["ath_observation_seal_validated"] = obs.get(
                "observation_seal_validated") is True
            state["ath_status"] = obs.get("status")
            state["ath_legacy_pre_evidence"] = False
            changed = True
        elif legacy_equal_seal_backfill:
            # Numeric ATH, event timestamp and source identity stay EXACT;
            # only the missing evidence/receipt seal is completed.
            state["ath_market_cap_evidence_price_usd"] = (
                state.get("ath_market_cap_evidence_price_usd")
                or obs.get("price"))
            state["ath_ingested_at_utc"] = obs.get("ingested_at_utc")
            state["ath_evidence_version"] = obs.get("evidence_version")
            state["ath_evidence_digest"] = obs.get("evidence_digest")
            state["ath_source_evidence_version"] = obs.get("evidence_version")
            state["ath_source_evidence_digest"] = obs.get("evidence_digest")
            state["ath_observation_seal_version"] = obs.get(
                "observation_seal_version")
            state["ath_observation_seal_digest"] = obs.get(
                "observation_seal_digest")
            state["ath_observation_seal_validated"] = True
            state["ath_legacy_pre_evidence"] = False
            state["ath_equal_evidence_reobserved_count"] = int(
                state.get("ath_equal_evidence_reobserved_count") or 0) + 1
            state["ath_last_equal_evidence_reobserved_at_utc"] = obs.get(
                "ingested_at_utc")
            changed = True
        elif equal_authoritative_reobservation:
            # Same economic identity, freshly observed.  Refresh only the local
            # receipt seal; every ATH value and source-event field stays exact.
            state["ath_ingested_at_utc"] = obs.get("ingested_at_utc")
            state["ath_observation_seal_version"] = obs.get(
                "observation_seal_version")
            state["ath_observation_seal_digest"] = obs.get(
                "observation_seal_digest")
            state["ath_observation_seal_validated"] = True
            state["ath_equal_evidence_reobserved_count"] = int(
                state.get("ath_equal_evidence_reobserved_count") or 0) + 1
            state["ath_last_equal_evidence_reobserved_at_utc"] = obs.get(
                "ingested_at_utc")
            changed = True
        elif state.get("ath_market_cap") is None and price_improves:
            # Before any market-cap-capable observation exists, expose honest
            # price provenance without fabricating a market cap.
            state["ath_timestamp"] = obs.get("timestamp")
            state["ath_provider"] = obs.get("provider")
            state["ath_observation_type"] = obs.get("observation_type")
            state["ath_status"] = obs.get("status")
        if changed:
            state["last_updated_at"] = _now_iso()
        # The resolved tuple is a projection of the record, so it is
        # recomputed on EVERY merge -- including merges that only refreshed
        # a seal -- and never drifts from the evidence it summarizes.
        self._resolve_locked(state)
        return changed

    def _resolve_locked(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Recompute this record's resolved tuple in place."""

        resolved = build_ath_resolved_tuple(
            state,
            event_supply_fn=lambda timestamp: (
                self._supply_tokens_for_timestamp_locked(state, timestamp)),
            authoritative_live_epoch_id=self._active_live_epoch_id,
        )
        state.update(resolved)
        return resolved

    def _authoritative_supply_provenance_locked(
        self, state: Mapping[str, Any], supply: Optional[Decimal],
    ) -> Optional[Mapping[str, Any]]:
        if supply is None:
            return None
        matches = []
        for value in (
                state.get("authoritative_supply_observations") or {}).values():
            if not isinstance(value, Mapping):
                continue
            if self._active_live_epoch_id is not None \
                    and value.get("live_epoch_id") != self._active_live_epoch_id:
                continue
            if _decimal(value.get("normalized_supply")) == supply:
                matches.append(value)
        return matches[0] if len(matches) == 1 else None

    def _supply_tokens_for_timestamp_locked(
        self, state: Mapping[str, Any], timestamp: str
    ) -> Tuple[Optional[Decimal], Optional[str]]:
        """Whole-token supply for one candle time, plus the basis that proved it.

        Event-sourced supply always wins.  Authenticated on-chain supply then
        wins over provider-implied supply.  Both non-event bases apply only
        while every observation agrees; disagreement leaves the candle high
        price-only instead of choosing a convenient value.
        """

        supply_raw, decimals = self._supply_for_timestamp_locked(
            state, timestamp)
        if supply_raw is not None and decimals is not None:
            return (Decimal(supply_raw) / (Decimal(10) ** decimals),
                    SUPPLY_BASIS_EVENT)
        if _epoch(timestamp) is None:
            return None, None
        authoritative = set()
        for value in (
                state.get("authoritative_supply_observations") or {}).values():
            if not isinstance(value, dict):
                continue
            if self._active_live_epoch_id is not None \
                    and value.get("live_epoch_id") != self._active_live_epoch_id:
                continue
            supply = _decimal(value.get("normalized_supply"))
            if (_epoch(value.get("fetched_at_utc")) is not None
                    and value.get("validation_result") == "SUPPLY_VALID"
                    and supply is not None):
                authoritative.add(supply)
        if len(authoritative) == 1:
            return authoritative.pop(), SUPPLY_BASIS_AUTHORITATIVE_RPC
        if len(authoritative) > 1:
            return None, None
        if self._active_live_epoch_id is not None:
            # Production has explicitly selected authenticated on-chain supply
            # for this epoch. Until that exact proof arrives, provider-implied
            # historical supply is not an eligibility substitute.
            return None, None
        supplies = set()
        for value in (state.get("provider_supply_observations") or {}).values():
            if not isinstance(value, dict):
                continue
            supply = _decimal(value.get("supply"))
            if _epoch(value.get("timestamp")) is not None and supply is not None:
                supplies.add(supply)
        # Unlike an event-sourced supply -- which is the exact supply embedded
        # in that candle's own transaction and is therefore only ever applied
        # FORWARD -- the provider basis is an explicitly bounded inference: the
        # provider reports a CURRENT circulating supply, and PHX2 applies it
        # across the bounded post-migration window only while every provider
        # observation of that window agrees.  A single disagreement disproves
        # invariance and the candle high stays a price-only maximum (no market
        # cap is ever fabricated).  Without it a restart-backfill candidate --
        # which by construction has no swap events and whose peak precedes its
        # admission -- could never convert its true post-migration high at all.
        if len(supplies) != 1:
            return None, None
        return supplies.pop(), SUPPLY_BASIS_PROVIDER

    @staticmethod
    def _supply_for_timestamp_locked(
        state: Mapping[str, Any], timestamp: str
    ) -> Tuple[Optional[int], Optional[int]]:
        target = _epoch(timestamp)
        if target is None:
            return None, None
        candidates = []
        for value in (state.get("supply_observations") or {}).values():
            if not isinstance(value, dict):
                continue
            when = _epoch(value.get("timestamp"))
            try:
                supply = int(value.get("supply_raw"))
                decimals = int(value.get("base_decimals"))
            except (TypeError, ValueError):
                continue
            if when is not None and when <= target and supply > 0 and 0 <= decimals <= 255:
                candidates.append((when, supply, decimals))
        if not candidates:
            return None, None
        _, supply, decimals = max(candidates)
        # Fail closed if the event stream has ever reported a different supply
        # or decimal basis up to this candle: invariance is then disproven.
        eligible = {(item[1], item[2]) for item in candidates}
        return (supply, decimals) if len(eligible) == 1 else (None, None)

    def _record_from_state(self, mint: str, state: Mapping[str, Any]) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"token_mint": mint}
        for key, value in state.items():
            payload[key] = deepcopy(value)
        payload["record_digest"] = _cpe.build_record_digest(
            _cpe.CHECKPOINT_KIND_ATH, payload)
        return payload

    def _restore_current_records(
        self, records, *, anchor_now_utc: Optional[str] = None,
    ) -> None:
        anchor = (
            _epoch(anchor_now_utc) if self._durable_checkpoint else None)
        for record in records:
            mint = str(record.get("token_mint"))
            if anchor is not None and self._restored_record_is_retired(
                    record, anchor_epoch=anchor):
                # Whole-record lifecycle boundary: a mint quiet for longer
                # than DURABLE_ATH_RECORD_RETENTION_SECONDS is retired at
                # restore (not loaded, absent from the next generation), so
                # the durable checkpoint never accumulates mints without
                # bound.  The cross-generation check tolerates exactly this
                # aged absence; the permanent ping-dedupe ledger -- not this
                # store -- carries the forever-scoped sent-tier memory.
                self._checkpoint_result.checkpoint_records_validated += 1
                self._checkpoint_records_retired += 1
                continue
            state = self._state(mint)
            for key, value in record.items():
                if key in ("token_mint", "record_digest"):
                    continue
                state[key] = deepcopy(value)
            if not isinstance(state.get("seen_event_keys"), dict):
                state["seen_event_keys"] = {}
            if not isinstance(state.get("supply_observations"), dict):
                state["supply_observations"] = {}
            if not isinstance(
                    state.get("authoritative_supply_observations"), dict):
                state["authoritative_supply_observations"] = {}
            if not isinstance(state.get("provider_supply_observations"), dict):
                state["provider_supply_observations"] = {}
            if not isinstance(state.get("pending_events"), list):
                state["pending_events"] = []
            if anchor is not None and self._restored_record_is_stale(
                    state, anchor_epoch=anchor):
                # Bounded durable growth: the ATH core (values, seals, pool
                # identity) is retained verbatim -- only the heavy per-event
                # operational maps of a long-quiet mint are dropped.  The
                # cross-generation regression check compares ATH values only,
                # so this compaction can never read as an ATH regression.
                state["seen_event_keys"] = {}
                state["pending_events"] = []
            # A record written by an older generation carries no resolved
            # tuple.  Resolution is a pure projection of evidence the record
            # already holds, so it is rebuilt here rather than left absent
            # until the mint happens to be observed again.
            self._resolve_locked(state)
            self._checkpoint_result.checkpoint_records_validated += 1

    @staticmethod
    def _restored_record_is_stale(
        state: Mapping[str, Any], *, anchor_epoch: float,
    ) -> bool:
        latest: Optional[float] = None
        for key in ("last_updated_at", "ath_timestamp"):
            when = _epoch(state.get(key))
            if when is not None and (latest is None or when > latest):
                latest = when
        if latest is None:
            return True
        return (anchor_epoch - latest) > (
            DURABLE_RESTORE_HEAVY_STATE_RETENTION_SECONDS)

    @staticmethod
    def _restored_record_is_retired(
        record: Mapping[str, Any], *, anchor_epoch: float,
    ) -> bool:
        latest: Optional[float] = None
        for key in ("last_updated_at", "ath_timestamp"):
            when = _epoch(record.get(key))
            if when is not None and (latest is None or when > latest):
                latest = when
        if latest is None:
            # A record with NO parseable activity timestamp cannot prove its
            # age; keep it (fail toward retention, never toward silent loss).
            return False
        return (anchor_epoch - latest) > DURABLE_ATH_RECORD_RETENTION_SECONDS

    def _migrate_legacy_mints(
        self, mints: Mapping[str, Any],
        *, source_digest: Optional[str], performed_at_utc: str,
    ) -> None:
        """Deterministic per-mint legacy ``phx2_central_ath_v1`` migration.

        Numeric maxima are preserved EXACTLY. A record whose authoritative
        market cap predates the evidence-seal schema is marked
        ``ath_legacy_pre_evidence`` instead of fabricating a digest; only an
        equal authoritative re-observation may later backfill its seal."""

        result = self._checkpoint_result
        for mint, raw in mints.items():
            state = self._state(str(mint))
            dropped = []
            for key, value in raw.items():
                if key in _ATH_RECORD_ALLOWED_KEYS and key not in (
                        "token_mint", "record_digest"):
                    state[key] = deepcopy(value)
                elif key not in ("token_mint", "record_digest"):
                    dropped.append(key)
            state["ath_price"] = _text(_decimal(raw.get("ath_price")))
            state["ath_market_cap"] = _text(_decimal(raw.get("ath_market_cap")))
            if not isinstance(state.get("seen_event_keys"), dict):
                state["seen_event_keys"] = {}
            if not isinstance(state.get("supply_observations"), dict):
                state["supply_observations"] = {}
            if not isinstance(
                    state.get("authoritative_supply_observations"), dict):
                state["authoritative_supply_observations"] = {}
            if not isinstance(state.get("provider_supply_observations"), dict):
                state["provider_supply_observations"] = {}
            if not isinstance(state.get("pending_events"), list):
                state["pending_events"] = []
            legacy_pre_evidence = (
                state.get("ath_market_cap") is not None
                and state.get("ath_evidence_digest") is None)
            state["ath_legacy_pre_evidence"] = legacy_pre_evidence
            result.checkpoint_records_validated += 1
            result.checkpoint_migration_report.append({
                "token_mint": str(mint),
                "source_schema_version": ATH_STATE_SCHEMA_VERSION,
                "source_ath_market_cap": raw.get("ath_market_cap"),
                "source_ath_timestamp": raw.get("ath_timestamp"),
                "migration_result": "MIGRATED",
                "legacy_pre_evidence": legacy_pre_evidence,
                "seal_backfill_required": legacy_pre_evidence,
                "dropped_unknown_fields": sorted(dropped),
                "source_digest": source_digest,
            })

    def _load(
        self,
        *,
        now_utc: Optional[str] = None,
        validation_now_utc: Optional[str] = None,
    ) -> None:
        if self._checkpoint_path is None:
            return
        primary_cls = classify_ath_checkpoint_file(
            self._checkpoint_path, validation_now_utc=validation_now_utc)
        backup_cls = classify_ath_checkpoint_file(
            self._backup_path, validation_now_utc=validation_now_utc)
        decision = _cpe.resolve_checkpoint_pair(
            primary_cls, backup_cls,
            cross_generation_check=ath_cross_generation_check)
        result = self._checkpoint_result
        selected: Optional[_cpe.FileClassification] = None
        public_participated = False
        migration_source = "primary" if decision.selected == "primary" else "backup"
        if primary_cls.state != _cpe.FILE_VALID_CURRENT:
            # The public artifact was a valid legacy restore source before the
            # envelope existed. Whenever the authenticated primary is not
            # usable it participates as a legacy evidence generation: it is
            # selected when nothing else is usable, or when it strictly
            # dominates the otherwise-selected generation (there is no
            # legitimate automatic ATH reset, so the higher surviving valid
            # evidence wins).
            public_cls = classify_ath_checkpoint_file(
                self._path, validation_now_utc=validation_now_utc)
            if public_cls.state == _cpe.FILE_VALID_LEGACY:
                if decision.status in (_cpe.CHECKPOINT_NOT_FOUND,
                                       _cpe.CHECKPOINT_QUARANTINED):
                    selected = public_cls
                    migration_source = "public_legacy"
                    public_participated = True
                    recovered = decision.status == _cpe.CHECKPOINT_QUARANTINED
                    decision = _cpe.CheckpointDecision(
                        status=_cpe.CHECKPOINT_RECOVERED_FROM_BACKUP
                        if recovered else _cpe.CHECKPOINT_PRIMARY_OK,
                        selected=decision.selected,
                        recovered_from_backup=recovered,
                        migrated=True,
                        primary_invalid_reason=decision.primary_invalid_reason
                        or (primary_cls.reason or None),
                        backup_invalid_reason=decision.backup_invalid_reason
                        or (backup_cls.reason or None),
                        notes=["PUBLIC_LEGACY_SOURCE_USED"],
                    )
                elif decision.selected is not None:
                    current_pick = (primary_cls if decision.selected == "primary"
                                    else backup_cls)
                    pick_ok, _, _ = ath_cross_generation_check(
                        current_pick, public_cls)
                    if not pick_ok:
                        public_ok, _, regressions = ath_cross_generation_check(
                            public_cls, current_pick)
                        if public_ok:
                            selected = public_cls
                            migration_source = "public_legacy"
                            public_participated = True
                            decision.migrated = True
                            decision.notes.append(
                                "PUBLIC_LEGACY_HIGHER_EVIDENCE_SELECTED")
                        else:
                            public_participated = True
                            decision = _cpe.CheckpointDecision(
                                status=_cpe.CHECKPOINT_QUARANTINED,
                                quarantined=True,
                                quarantine_reason=(
                                    _cpe.QUARANTINE_ATH_REGRESSION),
                                ath_regression_rejected=max(1, regressions),
                                notes=["PUBLIC_LEGACY_EVIDENCE_CONFLICT"],
                            )
            elif public_cls.state == _cpe.FILE_INVALID \
                    and decision.status == _cpe.CHECKPOINT_NOT_FOUND:
                # Existing public state with invalid content is never "no
                # checkpoint exists".
                public_participated = True
                decision = _cpe.CheckpointDecision(
                    status=_cpe.CHECKPOINT_QUARANTINED,
                    quarantined=True,
                    quarantine_reason=public_cls.reason
                    or _cpe.QUARANTINE_JSON_INVALID,
                    notes=["PUBLIC_LEGACY_SOURCE_INVALID"],
                )
        result.checkpoint_status = decision.status
        result.checkpoint_primary_status = primary_cls.state
        result.checkpoint_backup_status = backup_cls.state
        result.checkpoint_files_found = (
            primary_cls.state != _cpe.FILE_MISSING
            or backup_cls.state != _cpe.FILE_MISSING
            or public_participated)
        result.checkpoint_primary_invalid_reason = (
            primary_cls.reason or None
            if primary_cls.state == _cpe.FILE_INVALID else None)
        result.checkpoint_backup_invalid_reason = (
            backup_cls.reason or None
            if backup_cls.state == _cpe.FILE_INVALID else None)
        result.checkpoint_recovered_from_backup = decision.recovered_from_backup
        result.checkpoint_generation_conflict_total = (
            1 if decision.generation_conflict else 0)
        result.checkpoint_ath_regression_rejected = (
            decision.ath_regression_rejected)
        result.checkpoint_last_validated_at_utc = (
            validation_now_utc if isinstance(validation_now_utc, str)
            and _epoch(validation_now_utc) is not None else _cpe.utc_now_iso())
        result.checkpoint_notes.extend(decision.notes)
        for file_reason in (primary_cls.reason, backup_cls.reason):
            if file_reason in (_cpe.QUARANTINE_RECORD_DIGEST_INVALID,
                               _cpe.QUARANTINE_PAYLOAD_DIGEST_INVALID,
                               _cpe.QUARANTINE_ENVELOPE_DIGEST_INVALID,
                               _cpe.QUARANTINE_EVIDENCE_DIGEST_INVALID):
                result.checkpoint_digest_failure_total += 1
        if decision.status == _cpe.CHECKPOINT_NOT_FOUND:
            return
        if decision.quarantined:
            self._quarantined = True
            result.checkpoint_quarantined = True
            result.checkpoint_quarantine_reason = decision.quarantine_reason
            return
        if selected is None:
            selected = (primary_cls if decision.selected == "primary"
                        else backup_cls)
        anchor_now = (now_utc if isinstance(now_utc, str)
                      and _epoch(now_utc) is not None else _cpe.utc_now_iso())
        if selected.state == _cpe.FILE_VALID_CURRENT:
            header = selected.header or {}
            result.checkpoint_schema_version = header.get("schema_version")
            result.checkpoint_generation = header.get("generation")
            self._checkpoint_generation = int(header.get("generation") or 0)
            self._checkpoint_envelope_digest = header.get("envelope_digest")
            self._checkpoint_created_at_utc = header.get("created_at_utc")
            self._checkpoint_migration_history = [
                dict(item) for item in (header.get("migration_history") or [])
                if isinstance(item, Mapping)]
            self._restore_current_records(
                selected.records, anchor_now_utc=anchor_now)
            if decision.recovered_from_backup:
                if primary_cls.state == _cpe.FILE_INVALID \
                        and primary_cls.path is not None:
                    _cpe.preserve_evidence_copy(
                        primary_cls.path, label="invalid_evidence")
                try:
                    with self._lock:
                        self._persist_generation_locked()
                    result.checkpoint_notes.append(
                        "PRIMARY_REWRITTEN_FROM_BACKUP_RECOVERY")
                except (_cpe.CheckpointWriteError, OSError):
                    result.checkpoint_notes.append(
                        "PRIMARY_RECOVERY_REWRITE_FAILED")
        else:
            result.checkpoint_schema_version = ATH_STATE_SCHEMA_VERSION
            result.checkpoint_migrations_attempted += 1
            for source_file in (primary_cls, backup_cls):
                if source_file.path is not None \
                        and source_file.state != _cpe.FILE_MISSING:
                    _cpe.preserve_evidence_copy(
                        source_file.path, label="legacy_source")
            if self._path is not None and self._path.exists():
                # The public artifact was a valid legacy restore source at
                # the previous HEAD: preserve it as migration evidence too.
                _cpe.preserve_evidence_copy(self._path, label="legacy_source")
            payload = selected.legacy_payload or {}
            self._migrate_legacy_mints(
                payload.get("mints") or {},
                source_digest=selected.byte_digest,
                performed_at_utc=anchor_now,
            )
            self._checkpoint_migration_history = [{
                "migrated_from_schema": ATH_STATE_SCHEMA_VERSION,
                "migrated_to_schema": ATH_CHECKPOINT_SCHEMA_VERSION,
                "migration_performed_at_utc": anchor_now,
                "migration_source": migration_source,
                "migration_source_digest": selected.byte_digest,
                "records_migrated": result.checkpoint_records_validated,
            }]
            try:
                with self._lock:
                    self._persist_generation_locked()
                result.checkpoint_migrations_succeeded += 1
                result.checkpoint_status = _cpe.CHECKPOINT_MIGRATED
                result.checkpoint_schema_version = ATH_CHECKPOINT_SCHEMA_VERSION
                result.checkpoint_generation = self._checkpoint_generation
            except (_cpe.CheckpointWriteError, OSError) as exc:
                result.checkpoint_migrations_failed += 1
                self._mints.clear()
                self._quarantined = True
                result.checkpoint_quarantined = True
                result.checkpoint_status = _cpe.CHECKPOINT_QUARANTINED
                result.checkpoint_quarantine_reason = (
                    _cpe.QUARANTINE_MIGRATION_WRITE_FAILED)
                result.checkpoint_notes.append(
                    f"MIGRATION_INSTALL_FAILED:{type(exc).__name__}")

    def _persist_locked(self) -> None:
        """Tolerant persist for the steady-state observation paths.

        A transient checkpoint-write contention failure is retried (bounded)
        inside :meth:`_persist_generation_locked`; if it is still unresolved the
        failure is recorded (durability status + counters) and swallowed here so
        a single ATH observation can never terminate the producer. The durable
        generation is never falsely advanced and the in-memory state is retained
        for the next observation's persist. Mirrors the stream-cursor write
        tolerance. The migration/restore paths call
        :meth:`_persist_generation_locked` directly and keep the
        raise -> quarantine contract.
        """

        try:
            self._persist_generation_locked()
        except (_cpe.CheckpointWriteError, OSError):
            return

    def _note_checkpoint_write_success_locked(self, outcome, now_text) -> None:
        m = self._checkpoint_write_metrics
        m["checkpoint_write_succeeded_total"] += 1
        m["checkpoint_write_retried_total"] += outcome.retried
        m["checkpoint_write_retryable_failed_total"] += outcome.transient_failures
        m["checkpoint_last_success_utc"] = now_text
        m["checkpoint_durability_status"] = _cpe.CHECKPOINT_DURABILITY_HEALTHY

    def _note_checkpoint_write_failure_locked(self, exc) -> None:
        m = self._checkpoint_write_metrics
        category = _cpe.classify_checkpoint_write_error(exc)
        m["checkpoint_last_failure_category"] = category
        m["checkpoint_write_permanent_failed_total"] += 1
        m["checkpoint_write_retry_exhausted_total"] += 1
        m["checkpoint_durability_status"] = (
            _cpe.CHECKPOINT_DURABILITY_DEGRADED)

    def _persist_generation_locked(self) -> None:
        if self._path is None:
            return
        if self._quarantined:
            # A quarantined store never rewrites the corrupt on-disk evidence.
            return
        now_text = _cpe.utc_now_iso()
        created = self._checkpoint_created_at_utc or now_text
        records = [self._record_from_state(mint, self._mints[mint])
                   for mint in sorted(self._mints)]
        header = _cpe.build_envelope_header(
            checkpoint_kind=_cpe.CHECKPOINT_KIND_ATH,
            schema_version=ATH_CHECKPOINT_SCHEMA_VERSION,
            payload_encoding=_cpe.PAYLOAD_ENCODING_DOCUMENT,
            generation=self._checkpoint_generation + 1,
            record_digests=[str(row["record_digest"]) for row in records],
            created_at_utc=created,
            updated_at_utc=now_text,
            previous_generation_digest=self._checkpoint_envelope_digest,
            source_id=(self._checkpoint_path.name
                       if self._checkpoint_path is not None
                       else ATH_CHECKPOINT_BASENAME),
            migration_history=self._checkpoint_migration_history,
            extra_header_fields={
                "artifact_kind": "CENTRAL_ATH_RESTART_CHECKPOINT"},
        )
        self._checkpoint_write_metrics["checkpoint_write_attempted_total"] += 1
        try:
            outcome = _cpe.write_checkpoint_generation_resilient(
                primary_path=self._checkpoint_path,
                backup_path=self._backup_path,
                header=header,
                records=records,
                classify=classify_ath_checkpoint_file,
            )
        except (_cpe.CheckpointWriteError, OSError) as exc:
            self._note_checkpoint_write_failure_locked(exc)
            raise
        self._note_checkpoint_write_success_locked(outcome, now_text)
        self._checkpoint_generation = int(header["generation"])
        self._checkpoint_envelope_digest = str(header["envelope_digest"])
        self._checkpoint_created_at_utc = created
        public_mints: Dict[str, Dict[str, Any]] = {}
        for mint, state in self._mints.items():
            public = {
                key: deepcopy(value) for key, value in state.items()
                if key not in (
                    "seen_event_keys", "supply_observations", "pending_events",
                    "provider_supply_observations",
                    "authoritative_supply_observations",
                    # Full, potentially distinct price/market-cap provenance is
                    # retained in the restart checkpoint.  Shared consumers use
                    # the compact authoritative scalars and top-level event
                    # provenance below.
                    "price_provenance", "market_cap_provenance",
                )
            }
            public["dedupe_key_count"] = len(state.get("seen_event_keys") or {})
            public["pending_event_count"] = len(state.get("pending_events") or [])
            public["supply_basis_count"] = len(state.get("supply_observations") or {})
            public["provider_supply_basis_count"] = len(
                state.get("provider_supply_observations") or {})
            public["authoritative_supply_basis_count"] = len(
                state.get("authoritative_supply_observations") or {})
            public_mints[mint] = public
        public_payload = {
            "schema_version": ATH_STATE_SCHEMA_VERSION,
            "artifact_kind": "CENTRAL_ATH_PUBLIC_STATE",
            "updated_at": now_text,
            "mints": public_mints,
        }
        # The authenticated restart checkpoint generation committed first
        # (above, with backup rotation + read-back validation). A crash before
        # this public replace can leave the display view one observation old,
        # but restart can never regress the authoritative numeric state.
        self._atomic_write(self._path, public_payload)

    @staticmethod
    def _atomic_write(path: Optional[Path], payload: Mapping[str, Any]) -> None:
        if path is None:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_name(path.name + ".tmp")
        try:
            with temp.open("w", encoding="utf-8", newline="\n") as handle:
                json.dump(payload, handle, sort_keys=True, separators=(",", ":"))
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp, path)
        finally:
            try:
                if temp.exists():
                    temp.unlink()
            except OSError:
                pass


__all__ = (
    "ATH_STATE_BASENAME",
    "ATH_CHECKPOINT_BASENAME",
    "ATH_STATE_SCHEMA_VERSION",
    "ATH_CHECKPOINT_SCHEMA_VERSION",
    "ATH_EVIDENCE_SCHEMA_VERSION",
    "ATH_OBSERVATION_SEAL_SCHEMA_VERSION",
    "SUPPLY_BASIS_EVENT",
    "SUPPLY_BASIS_AUTHORITATIVE_RPC",
    "SUPPLY_BASIS_PROVIDER",
    "VALID_SUPPLY_BASES",
    "MAX_PROVIDER_SUPPLY_OBSERVATIONS",
    "MAX_AUTHORITATIVE_SUPPLY_OBSERVATIONS",
    "ATH_HYDRATION_MAX_WINDOW_LAG_SECONDS",
    "ATH_HYDRATION_ANCHOR_TOLERANCE_SECONDS",
    "ATH_HYDRATION_BACKOFF_BASE_SECONDS",
    "ATH_HYDRATION_BACKOFF_MAX_SECONDS",
    "ATH_V3_STATE_SCHEMA_VERSION",
    "ATH_V3_COARSE_INTERVAL",
    "ATH_V3_COARSE_INTERVAL_SECONDS",
    "ATH_V3_REFINE_INTERVAL",
    "ATH_V3_MAX_RETAINED_TICKETS",
    "ATH_LIVE_TRACKER_ANCHOR_TOLERANCE_SECONDS",
    "evaluate_ath_hydration",
    "evaluate_ath_hydration_detail",
    "ath_hydration_backoff_seconds",
    "validate_ath_checkpoint_record",
    "ath_checkpoint_record_identity",
    "classify_ath_checkpoint_file",
    "ath_cross_generation_check",
    "SOURCE_PUMPSWAP_EVENT",
    "SOURCE_PAID_OHLCV",
    "SOURCE_PAID_V3_PAIR",
    "SOURCE_PAID_CURRENT",
    "VALID_ATH_SOURCES",
    "MAX_DURABLE_EVENT_DEDUPE_KEYS",
    "DURABLE_RESTORE_HEAVY_STATE_RETENTION_SECONDS",
    "DURABLE_ATH_RECORD_RETENTION_SECONDS",
    "STATUS_CONFIRMED",
    "STATUS_PROVISIONAL",
    "build_ath_evidence_digest",
    "ath_evidence_digest_is_valid",
    "build_ath_observation_seal_digest",
    "ath_observation_seal_digest_is_valid",
    "CentralAthStateStore",
)

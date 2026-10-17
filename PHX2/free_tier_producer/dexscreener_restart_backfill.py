"""Bounded DexScreener restart diagnostics for live-only production.

This is diagnostic evidence, not candidate eligibility or historical
migration completeness.  It never
replays blocks, never fabricates Yellowstone evidence, and never persists a
raw HTTP response.  Two sweep kinds share one owner and one bounded window:

- STARTUP_RECOVERY: the first sweep of a live epoch scans the previous six
  hours for historical migrated pools the live stream could not have seen.
- PERIODIC_SAFETY_NET: subsequent sweeps on a bounded cadence (default 180s,
  stretched by bounded failure backoff) recover recent candidates missed by
  live discovery.

Every sweep admits only pairs created inside the hard six-hour lookback.  The
provider's candidate surface (token profiles -> token pair batches) has no
time-ordered pagination, so the durable cursor cannot narrow the request
window; instead each sweep re-scans the full bounded window (maximum overlap)
and idempotent dedupe — the per-sweep mint set here, the shared provider
dedupe, watchlist mint dedupe, and the durable delivery ledger — suppresses
repeats.  The durable cursor records sweep continuity (last successful sweep
end) so restarts and operators can prove when recovery last completed.

WHAT A SUCCESSFUL SWEEP DOES AND DOES NOT PROVE
-----------------------------------------------
A sweep that answers proves only that the requests worked.  It NEVER proves the
six-hour window was covered.  The curated surface is an editorial "latest token
profiles" list, not a migration index: it has no completeness guarantee, no
time-ordered pagination, and no way to enumerate everything that migrated.  So:

* the coverage claim of a successful poll is
  :data:`~PHX2.free_tier_producer.discovery_status.DEX_SAFETY_NET_PARTIAL_COVERAGE`,
  never "healthy" and never "complete";
* a mint the sweep did not list is reported
  :data:`~PHX2.free_tier_producer.discovery_status.NOT_OBSERVED_BY_CURATED_SOURCE`
  — a statement about the SOURCE, never evidence that the mint did not migrate;
* ``derive_backfill_status`` answers "did every REQUIRED source respond", which
  is request-level success, NOT migration coverage.

The vocabulary deliberately contains no token that would let this component
claim exhaustive six-hour completeness.
"""

from __future__ import annotations

import hashlib
import json
import os
import queue
import threading
import time
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Tuple

from PHX2.free_tier_producer.discovery_status import (
    CURATED_COVERAGE_CLAIM,
    KNOWN_COVERAGE_LIMITATIONS,
    curated_observation_status,
    dex_safety_net_coverage,
    dex_safety_net_state,
)
from PHX2.integrations.dexscreener_client import (
    DEX_BACKFILL_EMPTY,
    DEX_BACKFILL_INVALID_RESPONSE,
    DEX_BACKFILL_PARTIAL,
    DEX_BACKFILL_SUCCESS,
    DEX_BACKFILL_UNAVAILABLE,
    DexClientBounds,
    DexscreenerClient,
)


AUTHORITATIVE_PHX1_COMMIT = "318e359084d8711256747ae0fe307303d1b526d1"
# Centralized closed-set provenance contract; local name kept for importers.
from PHX2.models.discovery_provenance import (  # noqa: E402
    DISCOVERY_PROVENANCE_DEX_BACKFILL as DISCOVERY_PROVENANCE_DEX,
)
from PHX2.models.market_data_source import (  # noqa: E402
    MARKET_DATA_SOURCE_DEX_BACKFILL_PAIR,
)
MIGRATION_EVIDENCE_CLASS = "DEXSCREENER_INFERRED_MIGRATION"
MIGRATION_MC_SOURCE = "DEXSCREENER_SOL_USD_X_410_INFERRED"
POOL_DEX_IDENTITY = "SOLANA_PUMPSWAP"
#: PumpSwap quote side; used for central-ATH pool registration when the pair
#: response does not carry an explicit quote token.
WSOL_MINT = "So11111111111111111111111111111111111111112"
SOURCE_CONFIDENCE_EXACT = "PHX1_INFERRED_BASELINE"
SOURCE_CONFIDENCE_FALLBACK = "PHX1_INFERRED_BASELINE_SOL_FALLBACK"

PHX1_LOOKBACK_SECONDS = 6 * 60 * 60
DEX_ELIGIBILITY_MODE = "DIAGNOSTIC_ONLY"
PRE_BOUNDARY_NOT_ELIGIBLE = "PRE_BOUNDARY_NOT_ELIGIBLE"
PHX1_PROFILE_LIMIT = 50
PHX1_TOKEN_BATCH_SIZE = 30
PHX2_PAIR_LIMIT = 100
PHX2_CANDIDATE_LIMIT = 100

# --- Periodic safety net + durable cursor (2026-07-30 remediation) ----------
#: Bounded periodic recovery cadence.  The scheduler entry point may be called
#: every tick; a sweep starts only when the cadence has elapsed and no sweep
#: is in flight.
PERIODIC_SAFETY_NET_INTERVAL_SECONDS = 180.0
#: Failure backoff: the next attempt waits interval * 2**consecutive_failures,
#: capped here so a persistent outage retries at a bounded, visible pace.
PERIODIC_BACKOFF_MAX_MULTIPLIER = 10.0
#: Consecutive failed sweeps (no answer at all) before the operational state
#: reports FAILED instead of DEGRADED.
FAILED_SWEEP_THRESHOLD = 3

SWEEP_KIND_STARTUP = "STARTUP_RECOVERY"
SWEEP_KIND_PERIODIC = "PERIODIC_SAFETY_NET"

#: Closed-set operational state for status surfaces.  DISABLED is rendered by
#: the operator surface when the backfill owner was deliberately not
#: constructed; a constructed owner reports one of the remaining four.
BACKFILL_STATE_DISABLED = "DISABLED"
BACKFILL_STATE_STARTING = "STARTING"
BACKFILL_STATE_HEALTHY = "HEALTHY"
BACKFILL_STATE_DEGRADED = "DEGRADED"
BACKFILL_STATE_FAILED = "FAILED"
BACKFILL_OPERATIONAL_STATES = (
    BACKFILL_STATE_DISABLED,
    BACKFILL_STATE_STARTING,
    BACKFILL_STATE_HEALTHY,
    BACKFILL_STATE_DEGRADED,
    BACKFILL_STATE_FAILED,
)

BACKFILL_CURSOR_SCHEMA_VERSION = "phx2_dex_backfill_cursor_v1"

# --- Backfill source set (versioned) ---------------------------------------
# Completeness is judged against REQUIRED sources only; a retired source is
# out of the denominator and is never requested.  Values are closed-set
# tokens safe for artifacts and operator status.
SOURCE_CLASS_REQUIRED_AUTHORITATIVE = "REQUIRED_AUTHORITATIVE"
SOURCE_CLASS_REQUIRED_SUPPLEMENTAL = "REQUIRED_SUPPLEMENTAL"
SOURCE_CLASS_OPTIONAL_SUPPLEMENTAL = "OPTIONAL_SUPPLEMENTAL"
SOURCE_CLASS_INVALID_OR_RETIRED = "INVALID_OR_RETIRED"
BACKFILL_SOURCE_SET_VERSION = "phx2_dex_backfill_source_set_v2"
#: TOKEN_BATCH_<n> statuses classify under the "TOKEN_BATCH" prefix.
BACKFILL_SOURCE_CLASSES: Dict[str, str] = {
    "SOL_PRICE": SOURCE_CLASS_REQUIRED_SUPPLEMENTAL,
    "LATEST_TOKEN_PROFILES": SOURCE_CLASS_REQUIRED_AUTHORITATIVE,
    "TOKEN_BATCH": SOURCE_CLASS_REQUIRED_AUTHORITATIVE,
    "LATEST_SOLANA_PAIRS": SOURCE_CLASS_INVALID_OR_RETIRED,
}
# LATEST_SOLANA_PAIRS retirement (source_set_v2, 2026-07-29): the request was
# a chain-wide GET of a path the provider's API reference documents only as
# the pair-specific lookup "/latest/dex/pairs/{chainId}/{pairId}" with the
# pair identifier as a required path parameter; no chain-wide latest-pairs
# endpoint is documented.  Every preserved sweep (31 of 31 in the runs tree,
# including the 19 audited) failed this request deterministically with
# HTTP_STATUS_NON_2XX and it never returned a single pair, so retiring it
# removes no realized coverage.  The remaining candidate path (token profiles
# then token batches) uses only documented endpoints.
RETIRED_BACKFILL_SOURCES: Tuple[Dict[str, str], ...] = (
    {
        "source": "LATEST_SOLANA_PAIRS",
        "source_class": SOURCE_CLASS_INVALID_OR_RETIRED,
        "reason_class": "CHAIN_WIDE_REQUEST_TO_PAIR_SPECIFIC_LOOKUP",
        "retired_in": BACKFILL_SOURCE_SET_VERSION,
        "retired_utc_date": "2026-07-29",
    },
)


def backfill_source_class(name: str) -> str:
    """Classify a per-source status key; unknown names fail closed REQUIRED."""

    key = str(name)
    if key in BACKFILL_SOURCE_CLASSES:
        return BACKFILL_SOURCE_CLASSES[key]
    prefix = key.rsplit("_", 1)[0]
    return BACKFILL_SOURCE_CLASSES.get(
        prefix, SOURCE_CLASS_REQUIRED_AUTHORITATIVE)


def classify_sweep_sources(
    source_status: Mapping[str, str],
) -> Tuple[List[str], List[str], List[str]]:
    """Split requested sources into (failed, required_failed, optional_failed).

    ``failed`` lists every requested source whose status is neither success
    nor empty; the class-specific lists drive the completeness verdict.
    """

    failed = sorted(
        str(name) for name, value in source_status.items()
        if str(value) not in (DEX_BACKFILL_SUCCESS, DEX_BACKFILL_EMPTY))
    required_failed = [
        name for name in failed
        if backfill_source_class(name) in (
            SOURCE_CLASS_REQUIRED_AUTHORITATIVE,
            SOURCE_CLASS_REQUIRED_SUPPLEMENTAL)]
    optional_failed = [
        name for name in failed
        if backfill_source_class(name) == SOURCE_CLASS_OPTIONAL_SUPPLEMENTAL]
    return failed, required_failed, optional_failed


def derive_backfill_status(
    *,
    source_status: Mapping[str, str],
    accepted: int,
    unique_pairs: int,
) -> Tuple[str, str, List[str], List[str], List[str]]:
    """REQUEST-level verdict for one sweep from per-source outcomes.

    ``DEX_BACKFILL_SUCCESS`` means every remaining REQUIRED source ANSWERED; an
    OPTIONAL failure is disclosed but does not forfeit that; a retired source is
    never requested so it can neither fail nor answer.

    This is deliberately NOT a coverage verdict.  The curated surface cannot
    prove it listed every migration in the window, so no return value of this
    function may be read as six-hour completeness; the coverage claim comes
    from :func:`dex_safety_net_coverage`, which tops out at PARTIAL_COVERAGE.
    """

    failed, required_failed, optional_failed = classify_sweep_sources(
        source_status)
    if required_failed:
        if accepted or unique_pairs:
            final_status = DEX_BACKFILL_PARTIAL
        elif any(
            str(source_status.get(name)) == DEX_BACKFILL_INVALID_RESPONSE
            for name in required_failed
        ):
            final_status = DEX_BACKFILL_INVALID_RESPONSE
        else:
            final_status = DEX_BACKFILL_UNAVAILABLE
        final_event = (
            BACKFILL_PARTIAL if final_status == DEX_BACKFILL_PARTIAL
            else BACKFILL_FAILED)
    elif accepted == 0 and unique_pairs == 0:
        final_status = DEX_BACKFILL_EMPTY
        final_event = BACKFILL_EMPTY_SUCCESS
    else:
        final_status = DEX_BACKFILL_SUCCESS
        final_event = BACKFILL_COMPLETE
    return final_status, final_event, failed, required_failed, optional_failed

PHX1_SOL_FALLBACK_USD = Decimal("150")
PHX1_MIGRATION_SOL_MULTIPLIER = Decimal("410")
PHX1_SUPPLY = Decimal("1000000000")
PHX1_BACKFILL_ACTIVATION_MULTIPLIER = Decimal("1.39")
BACKFILL_CURRENT_MAX_AGE_SECONDS = 300.0
BACKFILL_EVIDENCE_SCHEMA_VERSION = "phx2_dex_restart_evidence_v1"

BACKFILL_START = "BACKFILL_START"
BACKFILL_PAGE = "BACKFILL_PAGE"
BACKFILL_RATE_LIMITED = "BACKFILL_RATE_LIMITED"
BACKFILL_RETRY = "BACKFILL_RETRY"
BACKFILL_PARTIAL = "BACKFILL_PARTIAL"
BACKFILL_EMPTY_SUCCESS = "BACKFILL_EMPTY_SUCCESS"
BACKFILL_CANDIDATE_ACCEPTED = "BACKFILL_CANDIDATE_ACCEPTED"
BACKFILL_CANDIDATE_REJECTED = "BACKFILL_CANDIDATE_REJECTED"
BACKFILL_CANDIDATE_DEDUPED = "BACKFILL_CANDIDATE_DEDUPED"
BACKFILL_COMPLETE = "BACKFILL_COMPLETE"
BACKFILL_FAILED = "BACKFILL_FAILED"
BACKFILL_SKIPPED_DUPLICATE_EPOCH = "BACKFILL_SKIPPED_DUPLICATE_EPOCH"
BACKFILL_STATUSES = (
    BACKFILL_START,
    BACKFILL_PAGE,
    BACKFILL_RATE_LIMITED,
    BACKFILL_RETRY,
    BACKFILL_PARTIAL,
    BACKFILL_EMPTY_SUCCESS,
    BACKFILL_CANDIDATE_ACCEPTED,
    BACKFILL_CANDIDATE_REJECTED,
    BACKFILL_CANDIDATE_DEDUPED,
    BACKFILL_COMPLETE,
    BACKFILL_FAILED,
    BACKFILL_SKIPPED_DUPLICATE_EPOCH,
)


def _utc_from_epoch(epoch: float) -> str:
    return datetime.fromtimestamp(
        float(epoch), tz=timezone.utc
    ).isoformat().replace("+00:00", "Z")


def _decimal(value: object) -> Optional[Decimal]:
    if value is None or isinstance(value, bool):
        return None
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return result if result.is_finite() else None


def _decimal_text(value: Decimal) -> str:
    text = format(value, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def _canonical(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")


def _evidence_payload(candidate: Mapping[str, Any]) -> Dict[str, Any]:
    fields = (
        "token_mint",
        "candidate_id",
        "discovery_provenance",
        "discovery_utc",
        "live_epoch_id",
        "migration_time_utc",
        "migration_evidence_class",
        "pair_address",
        "pool_dex_identity",
        "migration_market_cap_usd",
        "migration_market_cap_price",
        "migration_supply_at_observation",
        "migration_market_cap_source",
        "backfill_lookback_seconds",
        "backfill_sweep_id",
        "source_confidence",
        "dedupe_identity",
        "activation_multiplier",
    )
    return {
        "schema_version": BACKFILL_EVIDENCE_SCHEMA_VERSION,
        **{field: candidate.get(field) for field in fields},
    }


def build_backfill_evidence_digest(candidate: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical(_evidence_payload(candidate))).hexdigest()


def validate_backfill_candidate_evidence(
    candidate: Mapping[str, Any],
) -> Tuple[bool, str]:
    """Validate the explicit non-Yellowstone migration evidence contract."""

    if not isinstance(candidate, Mapping):
        return False, "BACKFILL_EVIDENCE_MISSING"
    if candidate.get("discovery_provenance") != DISCOVERY_PROVENANCE_DEX:
        return False, "BACKFILL_PROVENANCE_INVALID"
    if candidate.get("migration_evidence_class") != MIGRATION_EVIDENCE_CLASS:
        return False, "BACKFILL_EVIDENCE_CLASS_INVALID"
    mint = candidate.get("token_mint")
    pair = candidate.get("pair_address")
    if not isinstance(mint, str) or not mint.endswith("pump"):
        return False, "BACKFILL_MINT_INVALID"
    if not isinstance(pair, str) or not pair:
        return False, "BACKFILL_PAIR_INVALID"
    if candidate.get("pool_dex_identity") != POOL_DEX_IDENTITY:
        return False, "BACKFILL_DEX_IDENTITY_INVALID"
    baseline = _decimal(candidate.get("migration_market_cap_usd"))
    price = _decimal(candidate.get("migration_market_cap_price"))
    supply = _decimal(candidate.get("migration_supply_at_observation"))
    if baseline is None or price is None or supply is None \
            or baseline <= 0 or price <= 0 or supply != PHX1_SUPPLY \
            or price * supply != baseline:
        return False, "BACKFILL_BASELINE_INVALID"
    if candidate.get("migration_market_cap_source") != MIGRATION_MC_SOURCE:
        return False, "BACKFILL_BASELINE_SOURCE_INVALID"
    if _decimal(candidate.get("activation_multiplier")) != (
            PHX1_BACKFILL_ACTIVATION_MULTIPLIER):
        return False, "BACKFILL_ACTIVATION_MULTIPLIER_INVALID"
    if candidate.get("backfill_lookback_seconds") != PHX1_LOOKBACK_SECONDS:
        return False, "BACKFILL_LOOKBACK_INVALID"
    if not isinstance(candidate.get("backfill_sweep_id"), str) \
            or not candidate.get("backfill_sweep_id"):
        return False, "BACKFILL_SWEEP_ID_INVALID"
    supplied = candidate.get("backfill_evidence_digest")
    expected = build_backfill_evidence_digest(candidate)
    if not isinstance(supplied, str) or supplied != expected:
        return False, "BACKFILL_EVIDENCE_DIGEST_INVALID"
    return True, "BACKFILL_EVIDENCE_VALID"


def extract_pair_market(pair: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
    """PHX1-normalized pair market fields; malformed price rejects."""

    price = _decimal(pair.get("priceUsd"))
    if price is None or price <= 0:
        return None
    mcap = _decimal(pair.get("marketCap"))
    if mcap is None:
        mcap = _decimal(pair.get("fdv"))
    mcap = mcap if mcap is not None and mcap >= 0 else Decimal(0)
    liquidity = _decimal((pair.get("liquidity") or {}).get("usd"))
    liquidity = (
        liquidity if liquidity is not None and liquidity >= 0 else Decimal(0))
    volume = pair.get("volume") if isinstance(pair.get("volume"), Mapping) else {}

    def volume_value(key: str) -> Decimal:
        value = _decimal(volume.get(key))
        return value if value is not None and value >= 0 else Decimal(0)

    m5, h1, h6, h24 = (
        volume_value("m5"),
        volume_value("h1"),
        volume_value("h6"),
        volume_value("h24"),
    )
    spike = bool(h6 > 0 and h1 > Decimal("1.5") * (h6 / Decimal(6)))
    return {
        "current_price_usd": _decimal_text(price),
        "current_market_cap_usd": _decimal_text(mcap),
        "liquidity_usd": _decimal_text(liquidity),
        "volume_m5_usd": _decimal_text(m5),
        "volume_h1_usd": _decimal_text(h1),
        "volume_h6_usd": _decimal_text(h6),
        "volume_h24_usd": _decimal_text(h24),
        "volume_spike": spike,
        "volume_fields_present": bool(
            isinstance(volume, Mapping)
            and any(key in volume for key in ("m5", "h1", "h6", "h24"))),
    }


def _candidate_id(mint: str, pair: str, created_ms: int) -> str:
    digest = hashlib.sha256(
        f"{mint}|{pair}|{created_ms}".encode("utf-8")
    ).hexdigest()[:24]
    return "dex_restart_" + digest


def build_backfill_candidate(
    *,
    pair: Mapping[str, Any],
    sol_price_usd: Decimal,
    sol_fallback_used: bool,
    sweep_id: str,
    epoch_id: str,
    discovery_utc: str,
    now_epoch: float,
) -> Tuple[Optional[Dict[str, Any]], str]:
    """Apply the frozen PHX1 startup admission and inference contract."""

    if str(pair.get("chainId") or "solana").lower() != "solana":
        return None, "CHAIN_NOT_SOLANA"
    if str(pair.get("dexId") or "").lower() != "pumpswap":
        return None, "DEX_NOT_PUMPSWAP"
    pair_address = pair.get("pairAddress")
    if not isinstance(pair_address, str) or not pair_address:
        return None, "PAIR_ADDRESS_MISSING"
    base = pair.get("baseToken")
    mint = base.get("address") if isinstance(base, Mapping) else None
    if not isinstance(mint, str) or not mint.endswith("pump"):
        return None, "BASE_MINT_NOT_PUMP"
    created_raw = pair.get("pairCreatedAt")
    if isinstance(created_raw, bool) or not isinstance(created_raw, (int, float)):
        return None, "PAIR_CREATED_AT_MISSING"
    created_ms = int(created_raw)
    created_epoch = created_ms / 1000.0
    age = float(now_epoch) - created_epoch
    if age < -5.0 or age > PHX1_LOOKBACK_SECONDS:
        return None, "OUTSIDE_PHX1_LOOKBACK"
    market = extract_pair_market(pair)
    if market is None:
        return None, "CURRENT_PRICE_INVALID"
    baseline = sol_price_usd * PHX1_MIGRATION_SOL_MULTIPLIER
    baseline_price = baseline / PHX1_SUPPLY
    symbol = base.get("symbol") if isinstance(base, Mapping) else None
    name = base.get("name") if isinstance(base, Mapping) else None
    quote = pair.get("quoteToken")
    quote_mint = quote.get("address") if isinstance(quote, Mapping) else None
    if not isinstance(quote_mint, str) or not quote_mint:
        quote_mint = WSOL_MINT
    candidate: Dict[str, Any] = {
        "token_mint": mint,
        "candidate_id": _candidate_id(mint, pair_address, created_ms),
        "migration_time_utc": _utc_from_epoch(created_epoch),
        "migration_time_source": "DEXSCREENER_PAIR_CREATED_AT",
        "migration_time_authoritative": False,
        "local_observed_at_utc": discovery_utc,
        "source_ref": "dex_restart:" + hashlib.sha256(
            pair_address.encode("utf-8")).hexdigest()[:20],
        "provider_event_id": "",
        "discovery_provider": DISCOVERY_PROVENANCE_DEX,
        "symbol_or_name": (
            str(symbol) if isinstance(symbol, str) and symbol
            else str(name) if isinstance(name, str) and name else "???"),
        "token_name": str(name) if isinstance(name, str) else "",
        # Explicit symbol (2026-07-28 metadata remediation): unlike
        # ``symbol_or_name`` this never falls back to the name, so the
        # canonical metadata state can distinguish a real ticker.
        "token_symbol": str(symbol) if isinstance(symbol, str) else "",
        "discovery_provenance": DISCOVERY_PROVENANCE_DEX,
        "discovery_utc": discovery_utc,
        "live_epoch_id": epoch_id,
        "migration_slot": None,
        "eligibility_mode": DEX_ELIGIBILITY_MODE,
        "terminal_classification": PRE_BOUNDARY_NOT_ELIGIBLE,
        "migration_evidence_class": MIGRATION_EVIDENCE_CLASS,
        "pair_address": pair_address,
        "pool_dex_identity": POOL_DEX_IDENTITY,
        # Central-ATH pool registration input (bounded OHLCV hydration anchors
        # at the migration time, never at PHX2 admission time).  Deliberately
        # OUTSIDE the frozen evidence-digest field tuple.
        "quote_mint": quote_mint,
        "migration_market_cap_usd": _decimal_text(baseline),
        "migration_market_cap_price": _decimal_text(baseline_price),
        "migration_supply_at_observation": _decimal_text(PHX1_SUPPLY),
        # Baseline is inferred for the migration time, never current sweep time.
        "migration_market_cap_observed_at_utc": _utc_from_epoch(created_epoch),
        "migration_market_cap_source": MIGRATION_MC_SOURCE,
        "ath_source": "CENTRAL_ATH_PENDING",
        "liquidity_source": "DEXSCREENER_PAIR",
        "current_data_source": MARKET_DATA_SOURCE_DEX_BACKFILL_PAIR,
        "backfill_lookback_seconds": PHX1_LOOKBACK_SECONDS,
        "backfill_sweep_id": sweep_id,
        "source_confidence": (
            SOURCE_CONFIDENCE_FALLBACK if sol_fallback_used
            else SOURCE_CONFIDENCE_EXACT),
        "dedupe_identity": "mint:" + mint,
        "corroborating_sources": [],
        "activation_multiplier": _decimal_text(
            PHX1_BACKFILL_ACTIVATION_MULTIPLIER),
        "backfill_market_observed_at_utc": discovery_utc,
        **market,
    }
    candidate["backfill_evidence_digest"] = build_backfill_evidence_digest(
        candidate)
    valid, reason = validate_backfill_candidate_evidence(candidate)
    return (candidate, "ACCEPTED") if valid else (None, reason)


class DexRestartBackfill:
    """Bounded startup + periodic diagnostic history with one sweep owner.

    Sweeps run on a daemon thread so a slow or failing provider can never
    stall the live Helius source; at most one sweep is in flight at any time
    (single deterministic owner), and every sweep enforces the hard six-hour
    admission window.
    """

    def __init__(
        self,
        *,
        client_factory: Callable[[], DexscreenerClient] = DexscreenerClient,
        event_sink: Optional[Callable[[Dict[str, Any]], None]] = None,
        now_fn: Callable[[], float] = time.time,
        cursor_path: Optional[object] = None,
        periodic_interval_seconds: float = (
            PERIODIC_SAFETY_NET_INTERVAL_SECONDS),
    ) -> None:
        self._client_factory = client_factory
        self._event_sink = event_sink
        self._now = now_fn
        self._lock = threading.Lock()
        self._scheduled_epochs: set[str] = set()
        self._pending: queue.Queue[Dict[str, Any]] = queue.Queue(
            maxsize=PHX2_CANDIDATE_LIMIT)
        self._threads: List[threading.Thread] = []
        self._latest: Dict[str, Any] = {
            "status": "NOT_RUN",
            "sweep_id": None,
            "candidates_discovered": 0,
            "candidates_admitted": 0,
            "candidates_rejected": 0,
            "duplicate_suppressions": 0,
            "activation_multiplier": _decimal_text(
                PHX1_BACKFILL_ACTIVATION_MULTIPLIER),
        }
        self._market: Dict[str, Dict[str, Any]] = {}
        self._periodic_interval = max(1.0, float(periodic_interval_seconds))
        self._cursor_path = Path(cursor_path) if cursor_path else None
        self._sweep_inflight = False
        self._last_sweep_started_epoch: Optional[float] = None
        self._last_sweep_kind: Optional[str] = None
        self._consecutive_failed_sweeps = 0
        self._sweeps_completed_total = 0
        self._sweeps_failed_total = 0
        #: Mints the CURATED surface actually listed in the last answered
        #: sweep.  Absence from this set is reported as
        #: NOT_OBSERVED_BY_CURATED_SOURCE, never as "did not migrate".
        self._observed_mints: set[str] = set()
        self._curated_rows_examined = 0
        self._curated_rows_examined_total = 0
        self._last_sweep_answered = False
        self._last_required_sources_failed = False
        self._cursor: Dict[str, Any] = self._load_cursor()

    # ---- durable cursor ---------------------------------------------------

    def _load_cursor(self) -> Dict[str, Any]:
        """Tolerant durable-cursor load; malformed state means a fresh start,
        never a crash and never fabricated continuity."""

        default: Dict[str, Any] = {
            "schema_version": BACKFILL_CURSOR_SCHEMA_VERSION,
            "generation": 0,
            "last_successful_sweep_end_utc": None,
            "last_sweep_id": None,
            "last_final_status": None,
            "sweeps_completed_total": 0,
        }
        if self._cursor_path is None:
            return default
        for candidate_path in (
                self._cursor_path,
                self._cursor_path.with_name(self._cursor_path.name + ".bak")):
            try:
                document = json.loads(
                    candidate_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if (isinstance(document, dict)
                    and document.get("schema_version")
                    == BACKFILL_CURSOR_SCHEMA_VERSION):
                merged = dict(default)
                merged.update({
                    key: document.get(key) for key in default
                    if key in document})
                return merged
        return default

    def _persist_cursor_locked(self) -> None:
        if self._cursor_path is None:
            return
        try:
            self._cursor_path.parent.mkdir(parents=True, exist_ok=True)
            body = json.dumps(self._cursor, sort_keys=True, indent=2)
            backup = self._cursor_path.with_name(
                self._cursor_path.name + ".bak")
            if self._cursor_path.exists():
                try:
                    backup.write_text(
                        self._cursor_path.read_text(encoding="utf-8"),
                        encoding="utf-8")
                except OSError:
                    pass
            tmp = self._cursor_path.with_name(
                self._cursor_path.name + ".tmp")
            tmp.write_text(body, encoding="utf-8")
            os.replace(tmp, self._cursor_path)
        except OSError:
            # Cursor durability is observability, not send authority; a write
            # failure degrades continuity disclosure and nothing else.
            pass

    def _emit(self, event_status: str, **fields: Any) -> None:
        result_status = fields.pop("status", None)
        record = {
            "kind": "PHX2_DEX_RESTART_BACKFILL",
            "status": event_status,
            "result_status": result_status,
            "observed_at_utc": _utc_from_epoch(self._now()),
            **fields,
        }
        if self._event_sink is not None:
            try:
                self._event_sink(record)
            except Exception:
                pass

    def _start_sweep_thread(self, epoch_id: str, sweep_kind: str) -> None:
        thread = threading.Thread(
            target=self._run_sweep,
            args=(epoch_id, sweep_kind),
            name="phx2-dex-restart-backfill",
            daemon=True,
        )
        with self._lock:
            self._threads.append(thread)
        thread.start()

    def schedule(self, epoch_id: object) -> bool:
        """Startup recovery: exactly one initial sweep per live epoch."""

        if not isinstance(epoch_id, str) or not epoch_id:
            return False
        with self._lock:
            if epoch_id in self._scheduled_epochs:
                self._emit(
                    BACKFILL_SKIPPED_DUPLICATE_EPOCH, live_epoch_id=epoch_id)
                return False
            self._scheduled_epochs.add(epoch_id)
            self._sweep_inflight = True
            self._last_sweep_started_epoch = float(self._now())
            self._last_sweep_kind = SWEEP_KIND_STARTUP
        self._start_sweep_thread(epoch_id, SWEEP_KIND_STARTUP)
        return True

    def maybe_schedule_periodic(self, epoch_id: object) -> Tuple[bool, str]:
        """One scheduler entry point for both sweep kinds.

        Callable every tick.  Starts the STARTUP_RECOVERY sweep the first time
        an epoch is seen, then PERIODIC_SAFETY_NET sweeps once the bounded
        cadence (stretched by bounded failure backoff) has elapsed.  At most
        one sweep is ever in flight.
        """

        if not isinstance(epoch_id, str) or not epoch_id:
            return False, "EPOCH_ID_INVALID"
        with self._lock:
            if self._sweep_inflight:
                return False, "SWEEP_IN_FLIGHT"
            now = float(self._now())
            if epoch_id not in self._scheduled_epochs:
                self._scheduled_epochs.add(epoch_id)
                sweep_kind = SWEEP_KIND_STARTUP
            else:
                multiplier = min(
                    2.0 ** self._consecutive_failed_sweeps,
                    PERIODIC_BACKOFF_MAX_MULTIPLIER)
                due_at = (
                    (self._last_sweep_started_epoch or 0.0)
                    + self._periodic_interval * multiplier)
                if now < due_at:
                    return False, "NOT_DUE"
                sweep_kind = SWEEP_KIND_PERIODIC
            self._sweep_inflight = True
            self._last_sweep_started_epoch = now
            self._last_sweep_kind = sweep_kind
        self._start_sweep_thread(epoch_id, sweep_kind)
        return True, sweep_kind

    def _run_sweep(
        self, epoch_id: str, sweep_kind: str = SWEEP_KIND_STARTUP
    ) -> None:
        started_epoch = float(self._now())
        started_utc = _utc_from_epoch(started_epoch)
        sweep_id = "dex_sweep_" + hashlib.sha256(
            f"{epoch_id}|{started_utc}".encode("utf-8")
        ).hexdigest()[:20]
        self._emit(
            BACKFILL_START,
            sweep_id=sweep_id,
            sweep_kind=sweep_kind,
            live_epoch_id=epoch_id,
            lookback_seconds=PHX1_LOOKBACK_SECONDS,
            interval_start_utc=_utc_from_epoch(
                started_epoch - PHX1_LOOKBACK_SECONDS),
            interval_end_utc=started_utc,
            source_set_version=BACKFILL_SOURCE_SET_VERSION,
            retired_sources=[dict(item) for item in RETIRED_BACKFILL_SOURCES],
        )
        pairs: List[Dict[str, Any]] = []
        response_statuses: List[str] = []
        #: Per-source outcome, so a PARTIAL sweep names the coverage it lost.
        source_status: Dict[str, str] = {}
        #: Curated rows the provider actually returned this sweep (profiles +
        #: resolved pairs).  Reported so an operator can see WHAT was examined,
        #: not merely that a request succeeded.
        rows_examined = 0
        observed_mints: set[str] = set()
        try:
            client = self._client_factory()
            sol_float, sol_status = client.current_sol_price_usd()
            response_statuses.append(sol_status)
            source_status["SOL_PRICE"] = str(sol_status)
            fallback = sol_float is None or sol_float <= 0
            sol_price = (
                PHX1_SOL_FALLBACK_USD if fallback
                else Decimal(str(sol_float)))

            profiles, profile_status = client.latest_token_profiles()
            response_statuses.append(profile_status)
            source_status["LATEST_TOKEN_PROFILES"] = str(profile_status)
            rows_examined += len(profiles)
            self._emit(
                BACKFILL_PAGE,
                sweep_id=sweep_id,
                response_class="LATEST_TOKEN_PROFILES",
                response_status=profile_status,
                profiles_seen=len(profiles),
            )
            mints = [
                str(profile.get("tokenAddress"))
                for profile in profiles[:PHX1_PROFILE_LIMIT]
                if str(profile.get("chainId") or "").lower() == "solana"
                and isinstance(profile.get("tokenAddress"), str)
                and str(profile.get("tokenAddress")).endswith("pump")
            ]
            for offset in range(0, len(mints), PHX1_TOKEN_BATCH_SIZE):
                batch = mints[offset:offset + PHX1_TOKEN_BATCH_SIZE]
                resolved, token_status = client.token_pairs(batch)
                response_statuses.append(token_status)
                # One entry per batch: a sweep that lost page 3 of 5 must not
                # look like a sweep that lost nothing.
                source_status["TOKEN_BATCH_%d" % (
                    offset // PHX1_TOKEN_BATCH_SIZE)] = str(token_status)
                rows_examined += len(resolved)
                self._emit(
                    BACKFILL_PAGE,
                    sweep_id=sweep_id,
                    response_class="TOKEN_BATCH",
                    response_status=token_status,
                    pairs_seen=len(resolved),
                )
                for pair in resolved:
                    base_token = pair.get("baseToken")
                    base_mint = (base_token.get("address")
                                 if isinstance(base_token, Mapping) else None)
                    if isinstance(base_mint, str) and base_mint:
                        observed_mints.add(base_mint)
                pairs.extend([
                    pair for pair in resolved
                    if str(pair.get("dexId") or "").lower() == "pumpswap"
                ])

            unique: List[Dict[str, Any]] = []
            pair_ids: set[str] = set()
            duplicate_pairs = 0
            for pair in pairs:
                pair_id = pair.get("pairAddress")
                if not isinstance(pair_id, str) or not pair_id:
                    continue
                if pair_id in pair_ids:
                    duplicate_pairs += 1
                    self._emit(
                        BACKFILL_CANDIDATE_DEDUPED,
                        sweep_id=sweep_id,
                        dedupe_class="PAIR_ADDRESS",
                    )
                    continue
                pair_ids.add(pair_id)
                unique.append(pair)
                if len(unique) >= PHX2_PAIR_LIMIT:
                    break

            accepted = rejected = 0
            accepted_mints: set[str] = set()
            for pair in unique:
                candidate, reason = build_backfill_candidate(
                    pair=pair,
                    sol_price_usd=sol_price,
                    sol_fallback_used=fallback,
                    sweep_id=sweep_id,
                    epoch_id=epoch_id,
                    discovery_utc=started_utc,
                    now_epoch=started_epoch,
                )
                if candidate is None:
                    rejected += 1
                    self._emit(
                        BACKFILL_CANDIDATE_REJECTED,
                        sweep_id=sweep_id,
                        reason=reason,
                    )
                    continue
                mint = str(candidate["token_mint"])
                if mint in accepted_mints:
                    duplicate_pairs += 1
                    self._emit(
                        BACKFILL_CANDIDATE_DEDUPED,
                        sweep_id=sweep_id,
                        dedupe_class="MINT_FIRST_ACCEPTED_WINS",
                    )
                    continue
                accepted_mints.add(mint)
                try:
                    self._pending.put_nowait(candidate)
                except queue.Full:
                    rejected += 1
                    self._emit(
                        BACKFILL_CANDIDATE_REJECTED,
                        sweep_id=sweep_id,
                        reason="BACKFILL_CANDIDATE_QUEUE_FULL",
                    )
                    break
                accepted += 1
                with self._lock:
                    self._market[mint] = {
                        key: candidate.get(key)
                        for key in (
                            "pair_address",
                            "current_market_cap_usd",
                            "liquidity_usd",
                            "volume_m5_usd",
                            "volume_h1_usd",
                            "volume_h6_usd",
                            "volume_h24_usd",
                            "volume_fields_present",
                            "backfill_market_observed_at_utc",
                        )
                    }
                self._emit(
                    BACKFILL_CANDIDATE_ACCEPTED,
                    sweep_id=sweep_id,
                    token_mint=mint,
                    candidate_id=candidate["candidate_id"],
                )

            stats = client.stats()
            if stats["rate_limit_count"]:
                self._emit(
                    BACKFILL_RATE_LIMITED,
                    sweep_id=sweep_id,
                    count=stats["rate_limit_count"],
                )
            if stats["retry_count"]:
                self._emit(
                    BACKFILL_RETRY,
                    sweep_id=sweep_id,
                    count=stats["retry_count"],
                )
            (final_status, final_event, sources_failed, required_failed,
             optional_failed) = derive_backfill_status(
                source_status=source_status,
                accepted=accepted,
                unique_pairs=len(unique),
            )
            ended = float(self._now())
            summary = {
                "status": final_status,
                "sweep_id": sweep_id,
                "sweep_kind": sweep_kind,
                "live_epoch_id": epoch_id,
                "sweep_start_utc": started_utc,
                "sweep_end_utc": _utc_from_epoch(ended),
                "lookback_seconds": PHX1_LOOKBACK_SECONDS,
                "activation_multiplier": _decimal_text(
                    PHX1_BACKFILL_ACTIVATION_MULTIPLIER),
                "requests_attempted": stats["requests_attempted"],
                "requests_succeeded": stats["requests_succeeded"],
                "requests_failed": stats["requests_failed"],
                "responses_seen": len(response_statuses),
                "valid_pairs": len(unique),
                "candidates_discovered": len(unique),
                "candidates_admitted": accepted,
                "candidates_rejected": rejected,
                "duplicate_suppressions": duplicate_pairs,
                "retry_count": stats["retry_count"],
                "rate_limit_count": stats["rate_limit_count"],
                "duration_seconds": round(max(0.0, ended - started_epoch), 3),
                "error_class": stats.get("last_error_class"),
                # WHICH source failed, not just that one did. Every preserved
                # sweep -- 19 of 19 -- reported PARTIAL with exactly 1 of 4
                # requests failing and no way to tell from the heartbeat or
                # from ``main.py status`` which quarter of the search space
                # was never covered. The per-page events carried it; the
                # snapshot that reaches an operator did not.
                "source_status": dict(source_status),
                "sources_failed": list(sources_failed),
                "required_sources_failed": list(required_failed),
                "optional_sources_failed": list(optional_failed),
                "source_set_version": BACKFILL_SOURCE_SET_VERSION,
                "retired_sources": [
                    dict(item) for item in RETIRED_BACKFILL_SOURCES],
                "sol_price_fallback_used": fallback,
                # Curated rows the provider actually returned, and the honest
                # coverage claim.  A successful request is NOT proof that the
                # six-hour window was covered.
                "curated_rows_examined": rows_examined,
                "curated_coverage_claim": CURATED_COVERAGE_CLAIM,
                "known_coverage_limitations": list(
                    KNOWN_COVERAGE_LIMITATIONS),
            }
            with self._lock:
                self._latest = dict(summary)
                self._curated_rows_examined = rows_examined
                self._curated_rows_examined_total += rows_examined
                self._observed_mints = set(observed_mints)
                self._last_required_sources_failed = bool(required_failed)
                self._note_sweep_result_locked(
                    final_status, sweep_id=sweep_id, ended_epoch=ended)
            self._emit(final_event, **summary)
        except Exception as exc:
            ended = float(self._now())
            summary = {
                "status": DEX_BACKFILL_INVALID_RESPONSE,
                "sweep_id": sweep_id,
                "sweep_kind": sweep_kind,
                "live_epoch_id": epoch_id,
                "sweep_start_utc": started_utc,
                "sweep_end_utc": _utc_from_epoch(ended),
                "lookback_seconds": PHX1_LOOKBACK_SECONDS,
                "activation_multiplier": _decimal_text(
                    PHX1_BACKFILL_ACTIVATION_MULTIPLIER),
                "requests_attempted": 0,
                "requests_succeeded": 0,
                "requests_failed": 1,
                "candidates_discovered": 0,
                "candidates_admitted": 0,
                "candidates_rejected": 0,
                "duplicate_suppressions": 0,
                "duration_seconds": round(max(0.0, ended - started_epoch), 3),
                "error_class": type(exc).__name__[:64],
                "source_set_version": BACKFILL_SOURCE_SET_VERSION,
                "retired_sources": [
                    dict(item) for item in RETIRED_BACKFILL_SOURCES],
                "curated_rows_examined": rows_examined,
                "curated_coverage_claim": CURATED_COVERAGE_CLAIM,
                "known_coverage_limitations": list(
                    KNOWN_COVERAGE_LIMITATIONS),
            }
            with self._lock:
                self._latest = dict(summary)
                self._curated_rows_examined = rows_examined
                self._last_required_sources_failed = True
                self._note_sweep_result_locked(
                    DEX_BACKFILL_INVALID_RESPONSE,
                    sweep_id=sweep_id, ended_epoch=ended)
            self._emit(BACKFILL_FAILED, **summary)
        finally:
            with self._lock:
                self._sweep_inflight = False

    def _note_sweep_result_locked(
        self, final_status: str, *, sweep_id: str, ended_epoch: float
    ) -> None:
        """Sweep continuity bookkeeping (caller holds the lock).

        SUCCESS / EMPTY / PARTIAL all answered and advance the durable
        cursor (PARTIAL discloses its lost coverage in the summary);
        UNAVAILABLE / INVALID_RESPONSE mean no usable answer and count toward
        bounded failure backoff without advancing the cursor.
        """

        answered = final_status in (
            DEX_BACKFILL_SUCCESS, DEX_BACKFILL_EMPTY, DEX_BACKFILL_PARTIAL)
        self._last_sweep_answered = bool(answered)
        if answered:
            self._consecutive_failed_sweeps = 0
            self._sweeps_completed_total += 1
            self._cursor.update({
                "generation": int(self._cursor.get("generation") or 0) + 1,
                "last_successful_sweep_end_utc": _utc_from_epoch(ended_epoch),
                "last_sweep_id": sweep_id,
                "last_final_status": final_status,
                "sweeps_completed_total": self._sweeps_completed_total,
            })
            self._persist_cursor_locked()
        else:
            self._consecutive_failed_sweeps += 1
            self._sweeps_failed_total += 1

    def drain(self, max_candidates: int = PHX2_CANDIDATE_LIMIT
              ) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        for _ in range(max(0, int(max_candidates))):
            try:
                out.append(self._pending.get_nowait())
            except queue.Empty:
                break
        return out

    def fresh_market_gate(
        self,
        *,
        mint: str,
        now_utc: str,
        max_age_seconds: float = BACKFILL_CURRENT_MAX_AGE_SECONDS,
    ) -> Tuple[bool, str]:
        """Require fresh Dex pool/mcap/liquidity/volume before backfill send."""

        with self._lock:
            evidence = dict(self._market.get(mint) or {})
        try:
            now = datetime.fromisoformat(now_utc.replace("Z", "+00:00"))
            observed = datetime.fromisoformat(
                str(evidence.get("backfill_market_observed_at_utc")
                    or "").replace("Z", "+00:00"))
            age = (now - observed).total_seconds()
        except (TypeError, ValueError):
            age = float("inf")
        if age > max(0.0, float(max_age_seconds)) or age < -5.0:
            # PHX1 generic current refresh: highest-liquidity PumpSwap pair.
            client = DexscreenerClient(bounds=DexClientBounds(
                timeout_seconds=10.0,
                max_response_bytes=2 * 1024 * 1024,
                max_requests=2,
                max_retries=1,
                request_spacing_seconds=0.0,
            ))
            pair, status = client.highest_liquidity_pumpswap_pair(mint)
            if pair is None or status != DEX_BACKFILL_SUCCESS:
                return False, "BACKFILL_CURRENT_DATA_UNAVAILABLE"
            market = extract_pair_market(pair)
            if market is None:
                return False, "BACKFILL_CURRENT_DATA_INVALID"
            base = pair.get("baseToken")
            base = base if isinstance(base, Mapping) else {}
            evidence = {
                "pair_address": pair.get("pairAddress"),
                "backfill_market_observed_at_utc": now_utc,
                # Identity fields already present in the refresh response
                # (2026-07-28 metadata remediation); harvested by the session
                # into the canonical per-mint metadata state.
                "token_name": (str(base.get("name"))
                               if isinstance(base.get("name"), str) else ""),
                "token_symbol": (str(base.get("symbol"))
                                 if isinstance(base.get("symbol"), str) else ""),
                **market,
            }
            with self._lock:
                self._market[mint] = dict(evidence)
        mcap = _decimal(evidence.get("current_market_cap_usd"))
        liquidity = _decimal(evidence.get("liquidity_usd"))
        if mcap is None or mcap <= 0:
            return False, "BACKFILL_CURRENT_MARKET_CAP_REQUIRED"
        if liquidity is None or liquidity <= 0:
            return False, "BACKFILL_CURRENT_LIQUIDITY_REQUIRED"
        if evidence.get("volume_fields_present") is not True:
            return False, "BACKFILL_CURRENT_VOLUME_REQUIRED"
        return True, "BACKFILL_CURRENT_DATA_FRESH"

    def market_metadata(self, mint: str) -> Dict[str, Any]:
        """Identity fields captured by the last fresh-market refresh, if any."""

        with self._lock:
            evidence = dict(self._market.get(mint) or {})
        return {
            "token_name": evidence.get("token_name"),
            "token_symbol": evidence.get("token_symbol"),
        }

    def _operational_state_locked(self) -> str:
        """Closed-set operational state (caller holds the lock)."""

        if self._consecutive_failed_sweeps >= FAILED_SWEEP_THRESHOLD:
            return BACKFILL_STATE_FAILED
        if self._sweeps_completed_total == 0:
            if self._consecutive_failed_sweeps > 0:
                return BACKFILL_STATE_DEGRADED
            return BACKFILL_STATE_STARTING
        if self._consecutive_failed_sweeps > 0:
            return BACKFILL_STATE_DEGRADED
        if self._latest.get("status") == DEX_BACKFILL_PARTIAL:
            return BACKFILL_STATE_DEGRADED
        return BACKFILL_STATE_HEALTHY

    def observation_status(self, mint: object) -> str:
        """Did the CURATED surface list this mint in the last answered sweep?

        ``NOT_OBSERVED_BY_CURATED_SOURCE`` is a statement about the source, not
        about the mint: the curated list is best-effort and routinely omits
        real migrations, so absence is never evidence of no migration.
        """

        with self._lock:
            answered = bool(self._last_sweep_answered)
            observed = str(mint) in self._observed_mints
        return curated_observation_status(
            observed=observed, curated_source_answered=answered)

    def safety_net_status(self, *, enabled: bool = True) -> Dict[str, Any]:
        """Closed-set mechanism health AND the honest coverage claim.

        Two separate answers on purpose.  ``state`` says whether the poller is
        working; ``coverage`` says what the poller's output is allowed to
        claim, and a successful poll tops out at PARTIAL_COVERAGE.
        """

        with self._lock:
            failed = int(self._consecutive_failed_sweeps)
            completed = int(self._sweeps_completed_total)
            required_failed = bool(self._last_required_sources_failed)
            answered = bool(self._last_sweep_answered)
            rows = int(self._curated_rows_examined)
            rows_total = int(self._curated_rows_examined_total)
            admitted = int(self._latest.get("candidates_admitted") or 0)
        return {
            "state": dex_safety_net_state(
                enabled=bool(enabled),
                consecutive_failed_sweeps=failed,
                sweeps_completed_total=completed,
                required_sources_failed=required_failed),
            "coverage": dex_safety_net_coverage(
                enabled=bool(enabled), last_sweep_answered=answered),
            "curated_coverage_claim": CURATED_COVERAGE_CLAIM,
            "known_coverage_limitations": list(KNOWN_COVERAGE_LIMITATIONS),
            "curated_rows_examined": rows,
            "curated_rows_examined_total": rows_total,
            "curated_candidates_admitted": admitted,
            "lookback_ceiling_seconds": PHX1_LOOKBACK_SECONDS,
        }

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            multiplier = min(
                2.0 ** self._consecutive_failed_sweeps,
                PERIODIC_BACKOFF_MAX_MULTIPLIER)
            next_due = (
                None if self._last_sweep_started_epoch is None
                else _utc_from_epoch(
                    self._last_sweep_started_epoch
                    + self._periodic_interval * multiplier))
            snapshot = {
                **dict(self._latest),
                "scheduled_epoch_count": len(self._scheduled_epochs),
                "candidate_queue_depth": self._pending.qsize(),
                "fresh_market_candidates": len(self._market),
                "operational_state": self._operational_state_locked(),
                "sweep_inflight": self._sweep_inflight,
                "last_sweep_kind": self._last_sweep_kind,
                "periodic_interval_seconds": self._periodic_interval,
                "next_periodic_sweep_due_utc": next_due,
                "lookback_ceiling_seconds": PHX1_LOOKBACK_SECONDS,
                "consecutive_failed_sweeps": self._consecutive_failed_sweeps,
                "sweeps_completed_total": self._sweeps_completed_total,
                "sweeps_failed_total": self._sweeps_failed_total,
                "last_successful_sweep_end_utc": self._cursor.get(
                    "last_successful_sweep_end_utc"),
                "cursor": dict(self._cursor),
                "cursor_durable": self._cursor_path is not None,
                "last_sweep_answered": bool(self._last_sweep_answered),
                # NOTE: ``required_sources_failed`` stays the per-sweep LIST of
                # source names from ``_latest``; this boolean is a separate key
                # so neither reader is ambiguous.
                "any_required_source_failed": bool(
                    self._last_required_sources_failed),
                "curated_rows_examined": int(self._curated_rows_examined),
                "curated_rows_examined_total": int(
                    self._curated_rows_examined_total),
                "curated_mints_observed": len(self._observed_mints),
                "curated_coverage_claim": CURATED_COVERAGE_CLAIM,
                "known_coverage_limitations": list(
                    KNOWN_COVERAGE_LIMITATIONS),
            }
        # Nested so the two closed-set answers (mechanism health vs coverage
        # claim) can never be confused with the per-sweep request ``status``.
        status = self.safety_net_status(enabled=True)
        snapshot["safety_net"] = status
        snapshot["dex_safety_net_state"] = status["state"]
        snapshot["dex_safety_net_coverage"] = status["coverage"]
        return snapshot


__all__ = (
    "AUTHORITATIVE_PHX1_COMMIT",
    "CURATED_COVERAGE_CLAIM",
    "KNOWN_COVERAGE_LIMITATIONS",
    "DISCOVERY_PROVENANCE_DEX",
    "MIGRATION_EVIDENCE_CLASS",
    "MIGRATION_MC_SOURCE",
    "POOL_DEX_IDENTITY",
    "SOURCE_CLASS_REQUIRED_AUTHORITATIVE",
    "SOURCE_CLASS_REQUIRED_SUPPLEMENTAL",
    "SOURCE_CLASS_OPTIONAL_SUPPLEMENTAL",
    "SOURCE_CLASS_INVALID_OR_RETIRED",
    "BACKFILL_SOURCE_SET_VERSION",
    "BACKFILL_SOURCE_CLASSES",
    "RETIRED_BACKFILL_SOURCES",
    "backfill_source_class",
    "classify_sweep_sources",
    "derive_backfill_status",
    "PHX1_LOOKBACK_SECONDS",
    "DEX_ELIGIBILITY_MODE",
    "PRE_BOUNDARY_NOT_ELIGIBLE",
    "PERIODIC_SAFETY_NET_INTERVAL_SECONDS",
    "PERIODIC_BACKOFF_MAX_MULTIPLIER",
    "FAILED_SWEEP_THRESHOLD",
    "SWEEP_KIND_STARTUP",
    "SWEEP_KIND_PERIODIC",
    "BACKFILL_STATE_DISABLED",
    "BACKFILL_STATE_STARTING",
    "BACKFILL_STATE_HEALTHY",
    "BACKFILL_STATE_DEGRADED",
    "BACKFILL_STATE_FAILED",
    "BACKFILL_OPERATIONAL_STATES",
    "BACKFILL_CURSOR_SCHEMA_VERSION",
    "WSOL_MINT",
    "PHX1_PROFILE_LIMIT",
    "PHX1_TOKEN_BATCH_SIZE",
    "PHX2_PAIR_LIMIT",
    "PHX2_CANDIDATE_LIMIT",
    "PHX1_SOL_FALLBACK_USD",
    "PHX1_MIGRATION_SOL_MULTIPLIER",
    "PHX1_SUPPLY",
    "PHX1_BACKFILL_ACTIVATION_MULTIPLIER",
    "BACKFILL_CURRENT_MAX_AGE_SECONDS",
    "BACKFILL_EVIDENCE_SCHEMA_VERSION",
    "BACKFILL_STATUSES",
    "build_backfill_evidence_digest",
    "validate_backfill_candidate_evidence",
    "extract_pair_market",
    "build_backfill_candidate",
    "DexRestartBackfill",
)

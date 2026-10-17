"""free_tier_session.py — PHX2 live FREE-TIER private-ping + paper-artifact producer (NO-SEND default).

OUT-OF-REPO operator glue. Bridges fresh PHX2 live discovery to the committed paper engine:

    read-only Helius WS discovery (committed Build 26 capture, reused verbatim)
      -> bounded mint-keyed watchlist (Build 30, reused verbatim)
      -> committed cap-1 engine per tick (Build 29 run_cap1_candidates, reused verbatim):
           pump gate -> FREE-TIER market resolve (keyless public pools data behind the committed
           Birdeye transport seam) -> pre-reserve liquidity floor -> committed composer
           (dip gate + anchored ATH + market freshness) -> dedupe RESERVE (fresh free-tier ledger)
           -> committed Stage 30.11.16 guard
      -> DEFAULT transport: FreeTierRecordingNoSendTransport (records a WOULD-PING; sends NOTHING)
      -> growing artifact dir the committed paper engine (PHX2.scripts.phx2_live_paper_trade)
         tails live: candidates/<mint8>.jsonl, would_ping_records.jsonl, pricing_tail.jsonl,
         sends.jsonl, watch_state.jsonl, heartbeat.jsonl, producer_heartbeat/summary, errors.jsonl

Modes: --selftest (offline) | --preflight (env presence only; NO socket/RPC/GET/send) |
--run (live producer; NO-SEND by DEFAULT).

PRIVATE DISCORD IS DISABLED BY DEFAULT. ``--enable-private-discord`` requires the FULL arm gate
(ack flag + --i-understand-this-can-send + the locked confirm token + a --require-baseline match on
THE FREE-TIER ledger + webhook present) and swaps ONLY the guard's transport to the proven
Stage28_4 -> Stage28_9 private-operator seam. Private operator route only; no public/subscriber
routing; no wallet/signing/trading/swap surface anywhere in this bundle.

Ledger isolation: this producer uses its OWN dedupe ledger
(``C:\\Users\\BalaC\\phx2_live_free_tier\\ping_dedupe.jsonl``) and REFUSES any ledger/out path
inside the historical ceremony/production trees, so the old durable ledgers can never be touched.
Never prints a secret (PRESENT/MISSING only).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
import uuid
from types import SimpleNamespace
from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Tuple

_PACKAGE_DIR = Path(__file__).resolve().parent
_REPO = str(_PACKAGE_DIR.parents[1])
_COMPAT = str(_PACKAGE_DIR / "compat")
_SELF = str(_PACKAGE_DIR)
for _p in (_REPO, _COMPAT, _SELF):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import build29_cap1_compose_send as cs            # noqa: E402  (committed send lineage glue)
import build29_cap1_ledger as ledgerlib           # noqa: E402  (baseline triple helpers)
import build29_cap1_session as sess               # noqa: E402  (engine + env load/scrub)
import build30_session as b30s                    # noqa: E402  (proven discovery + transport seam)
from build30_watchlist import (                    # noqa: E402
    ACTIVATION_COUNTER_FIELDS,
    MIGRATION_ACTIVATION_MULTIPLIER, BACKFILL_ACTIVATION_MULTIPLIER,
    DISCOVERY_PROVENANCE_DEX,
    WATCH_STATE_BASENAME, WATCH_TERMINAL_HISTORY_BASENAME,
    Watchlist,
    activation_proof_is_durable,
    verify_cross_checkpoint_consistency,
)

import production_live_artifacts as artifacts     # noqa: E402  (proven serializers + scanner)
import production_live_axiom_gate as axiomgate    # noqa: E402  (Null source + strict config)
from production_live_runner import (              # noqa: E402  (proven watch loop; PHX2-E2E-006
    UNBOUNDED_RUNTIME_SECONDS,
    ProductionBounds, liquidity_floor_block_reason, production_postflight_verdict,
    run_production_live_watch,                     # added the wakeable inter-tick wait)
    runtime_bound_is_unbounded,
)

from free_tier_market_transport import (          # noqa: E402
    FreeTierMarketTransport, build_free_tier_endpoint_secret,
)
from free_tier_no_send_transport import (         # noqa: E402
    NO_SEND_TRANSPORT_KIND, FreeTierRecordingNoSendTransport,
)
from free_tier_pricing_tail import (               # noqa: E402
    TAIL_ORIGIN_WATCHLIST, FreeTierPricingTail,
)
from free_tier_credit_budget import (              # noqa: E402
    BUDGET_STOP_MARKET_PLANE_BLIND,
    RAW_WS_CAP_NOTE, FreeTierCreditBudget, FreeTierCreditBudgetCaps,
    rewrite_result_for_budget_stop, verdict_for_budget_stop,
)
from free_tier_polling_discovery import (          # noqa: E402
    POLLING_SEEN_BASENAME, FreeTierPollingCaps, FreeTierPollingDiscovery,
)
from free_tier_risk import (                        # noqa: E402
    HOLDER_SCAN_ENABLED, FreeTierRiskEngine, FreeTierRiskLineTransport,
    classify_discord_dispatch, SKIPPED_HIGH_RISK_DISCORD, SKIPPED_MEDIUM_RISK_WEAK_STRUCTURE,
)
from paid_birdeye import PaidBirdeyeMarketTransport  # noqa: E402
from PHX2.free_tier_producer.market_credential_check import (  # noqa: E402
    validate_market_credential,
)
from PHX2.free_tier_producer.admission_inbox import (  # noqa: E402
    DurableAdmissionInbox, AdmissionInboxError,
)
from paid_market_readiness import (                    # noqa: E402
    MARKET_INDEXING, MARKET_RECOVERY_BACKOFF,
    PaidMarketReadinessConfig, PaidMarketReadinessTracker,
)
from paid_provider import (                          # noqa: E402
    PROVIDER_MODE_FREE_TIER, PROVIDER_MODE_PAID_PRIMARY,
    PROVIDER_MODE_PAID_WITH_FALLBACK, PROVIDER_MODES,
    STREAM_STATUS_AUTH_FAILED,
    ProviderCandidateDedupe, SingleGrpcPumpSwapDiscovery,
    SourceFactoryContractError,
    apply_provider_dedupe_once, build_live_source_factory,
    mark_provider_dedupe_applied, normalize_provider_mode,
)
from serialized_jsonl import (                       # noqa: E402
    SerializedJsonlAppendError, SerializedJsonlAppender,
)
from PHX2.free_tier_producer.stream_cursor import (
    STREAM_CURSOR_SCHEMA_V1, STREAM_SOURCE_YELLOWSTONE,
    GrpcStreamCursorStore, build_cursor_store,
    compute_subscription_identity_digest,
    source_health_authorizes_send,
)
from PHX2.free_tier_producer.production_grpc_contract import (
    ProductionContractError,
    evaluate_production_grpc_contract,
    evaluate_production_mode_precondition,
)
from PHX2.free_tier_producer.rpc_block_pool import default_apply_processes
from PHX2.free_tier_producer.rpc_gap_recovery import (
    GAP_RECOVERY_MODE_RPC_BACKFILL,
    GAP_RECOVERY_MODE_LIVE_EPOCH,
    GAP_RECOVERY_MODES,
    OVERLAP_PROVEN,
    RECOVERY_STATE_IDLE,
    RECOVERY_STATE_RECOVERY_TERMINAL,
    QuarantinedLiveBuffer,
    RpcGapBackfillCoordinator,
    RpcGapRecoveryConfig,
    RpcGapRecoveryStore,
    build_rpc_transport_from_env,
    evaluate_armed_gap_recovery,
    project_rpc_recovery_env_safe,
)
from PHX2.free_tier_producer.live_epoch import (
    EPOCH_HEALTHY,
    HISTORICAL_REPLAY_STATUS,
    LIVE_EPOCH_CURSOR_BASENAME,
    PRODUCTION_MODE as LIVE_EPOCH_PRODUCTION_MODE,
    LiveEpochManager,
    build_durable_policy_identity,
    build_run_instance_identity,
)
from PHX2.free_tier_producer.dexscreener_restart_backfill import (
    DexRestartBackfill,
)
from PHX2.free_tier_producer.ping_quality_review import (
    PING_QUALITY_REVIEW_BASENAME,
    build_ping_quality_record,
    ping_quality_record_is_redaction_safe,
)
from PHX2.free_tier_producer.runtime_phase import (
    ActivationInputs,
    RuntimePhaseClock,
)
from PHX2.free_tier_producer.migration_admission import MIGRATION_VERSIONS
from PHX2.free_tier_producer.migration_census import (
    DISCOVERY_SOURCE_LIVE_GRPC,
    DISCOVERY_SOURCE_LIVE_HELIUS,
    MigrationCensusError,
    MigrationCensusStore,
)
from PHX2.free_tier_producer.source_continuity import SourceContinuityTracker
from PHX2.free_tier_producer.migration_journal import (
    JOURNAL_BASENAME as MIGRATION_JOURNAL_BASENAME,
    CURSOR_BASENAME as MIGRATION_JOURNAL_CURSOR_BASENAME,
    DurableMigrationJournal,
)
from PHX2.free_tier_producer.discovery_status import build_discovery_status
from PHX2.free_tier_producer.helius_credit_projection import projection_report
from PHX2.free_tier_producer.helius_byte_budget import HeliusByteBudget
from PHX2.free_tier_producer.helius_source import (
    MIGRATION_SOURCE_MODES,
    approved_tight_subscription_request,
    build_helius_primary_source_factory,
    build_production_source_runtime_plan,
    load_helius_source_config,
    load_source_selection,
    validate_production_source_contract,
)
from PHX2.free_tier_producer.transport_watermark import TransportWatermarkStore
from PHX2.stage29.pumpswap_program_constants import PUMPSWAP_PROGRAM_ID
from PHX2.stage29.stage29_3_hint_aware_event_source import (
    STAGE29_3_TRANSACTION_FILTER_NAME,
)
from PHX2.free_tier_producer.pumpswap_reserves import PumpSwapReserveIndex
from PHX2.free_tier_producer.canonical_volume import CanonicalSwapVolumeTracker
from PHX2.free_tier_producer.token_metadata import TokenMetadataResolver
from PHX2.free_tier_producer.global_fees import GlobalFeesTracker
from PHX2.free_tier_producer.market_scheduler import (
    FIELD_OVERVIEW,
    FIELD_PRICE_MC,
    MARKET_PROVIDER_BUDGET_EXHAUSTED,
    MarketObservation,
    MarketScheduler,
    MarketSchedulerConfig,
    P1_CAPACITY_UNACHIEVABLE,
    ScheduledMarketSidecar,
    SOURCE_AUTHENTICATED_RESERVE_FALLBACK,
    SOURCE_GRPC,
    classify_engine_reason_to_p1_outcome,
    evaluate_p1_capacity,
    production_p1_scheduler_fields,
)
from PHX2.free_tier_producer.market_budget import (
    MARKET_REQUEST_CAP_UNBOUNDED,
    ORIGIN_ATH_HYDRATION_OHLCV,
    MarketPhysicalRequestMeter,
    market_budget_mode,
    run_forever_market_budget_refusal,
)
from PHX2.free_tier_producer.authoritative_supply import (
    SUPPLY_ARTIFACT_BASENAME,
    AuthoritativeSupplyBridge,
    HeliusTokenSupplyClient,
)
from PHX2.free_tier_producer.authenticated_market_fallback import (
    FRESH_FALLBACK_ARTIFACT_BASENAME,
    AuthenticatedPumpSwapMarketFallback,
)
from PHX2.free_tier_producer.market_plane_health import (
    MarketPlaneConfig,
    MarketPlaneWatch,
    classify as classify_market_plane,
)
from PHX2.watchdog.operational_health import (
    SCHEDULER_STARVATION_BOUND_SECONDS,
)
from PHX2.free_tier_producer.ath_state import CentralAthStateStore
from PHX2.free_tier_producer.liquidity_integrity import WSOL_MINT
from PHX2.models.ath_coverage import (
    ATH_HYDRATION_COMPLETE,
    ath_coverage_is_complete,
    classify_ath_coverage,
)
from PHX2.free_tier_producer.phx1_fee_gate import FeeEvidenceIndex
from PHX2.free_tier_producer.fee_gate_lifecycle import (
    FeeGateLifecycleIndex,
    build_fee_gate_lifecycle_config,
    make_fee_gate_send_time_gate,
)
from PHX2.free_tier_producer.migration_admission import (
    MigrationProofStore,
    build_migration_admission_config,
)
from PHX2.free_tier_producer.scam_policy import (
    LEGACY_LP_STATE_IGNORED_SINGLE_STREAM,
    LP_INTEGRITY_MODE_DISABLED_SINGLE_STREAM,
    SecurityDecisionIndex,
    evaluate_delivery_safety,
)
from PHX2.free_tier_producer.phx1_structural_policy import (
    PHX1_STRUCTURAL_POLICY_CLI_VALUES,
    PHX1_STRUCTURAL_POLICY_ENFORCE,
    PHX1_STRUCTURAL_POLICY_SHADOW,
    build_shadow_candidate_artifact,
    normalize_phx1_structural_policy,
)
from PHX2.free_tier_producer.phx1_parity_policy import (
    ALERT_POLICY_CLI_VALUES,
    ALERT_POLICY_LEGACY,
    Phx1ParityCounters,
    bind_alert_policy,
    is_phx1_parity,
    normalize_alert_policy,
    policy_matrix,
    watch_ttl_seconds,
)
from PHX2.delivery.telegram_adapter import TelegramDeliveryAdapter
from PHX2.delivery.telegram_config import TelegramConfig, TelegramConfigError
from PHX2.delivery.telegram_transport import TelegramTransport

from build26_evidence_capture import CaptureCaps  # noqa: E402  (committed per-window caps)
from build29_cap1_market_sidecar import Cap1MarketCaps, Cap1MarketSidecar  # noqa: E402

ENV_WEBHOOK = sess.ENV_WEBHOOK                     # PHX2_STAGE21_DISCORD_WEBHOOK_URL
LOCKED_CONFIRM_TOKEN = cs.STAGE30_11_16_AUTHORIZATION_CONFIRM_TOKEN
ENV_FILE_DEFAULT = r"C:\Users\BalaC\Documents\phx2.env"

FREE_TIER_ROOT = r"C:\Users\BalaC\phx2_live_free_tier"
OUT_DIR_DEFAULT = str(Path(FREE_TIER_ROOT) / "out" / "live_01")
LEDGER_DEFAULT = str(Path(FREE_TIER_ROOT) / "ping_dedupe.jsonl")

# Historical trees this producer must NEVER write a ledger/out path into (old one-send ceremony
# ledger + production private-live tree + capped ceremony tree). Normalized-lowercase prefixes.
_FORBIDDEN_WRITE_ROOTS = (
    r"c:\users\balac\phx2_one_send_ceremony",
    r"c:\users\balac\phx2_capped_one_send_ceremony",
    r"c:\users\balac\phx2_production_private_live",
)

WOULD_PING_BASENAME = "would_ping_records.jsonl"
WOULD_PING_BODIES_BASENAME = "would_ping_bodies.jsonl"
DISCORD_BLOCKS_BASENAME = "discord_blocks.jsonl"   # risk-gated private-dispatch blocks (2026-07-12)
TELEGRAM_ATTEMPTS_BASENAME = "telegram_attempts.jsonl"
TELEGRAM_COMPOSES_BASENAME = "telegram_composes.jsonl"
ERRORS_BASENAME = "errors.jsonl"
PRODUCER_HEARTBEAT_BASENAME = "producer_heartbeat.json"
# Migration-admission diagnostics (rejections) + restart-safe sealed proofs.
MIGRATION_REJECTIONS_BASENAME = "migration_rejections.jsonl"
MIGRATION_PROOFS_BASENAME = "migration_proofs.jsonl"
# Historical two-stream artifact (the removed liquidity-verifier's event log).
# A new single-stream run never writes it; its presence in a reused run
# directory is reported as legacy state and ignored for authorization.
LEGACY_LIQUIDITY_EVENTS_BASENAME = "liquidity_events.jsonl"
# Restart-safe fee gate lifecycle state (maturity, provisional scam
# confirmations, durable scam locks).
FEE_GATE_LIFECYCLE_BASENAME = "fee_gate_lifecycle.jsonl"
PHX1_SHADOW_CANDIDATES_BASENAME = "phx1_shadow_candidates.jsonl"

# ---------------------------------------------------------------------------
# Single-stream production topology (PHX1 parity).  Production opens exactly
# ONE Yellowstone subscription — the primary migration/discovery/fee stream.
# The liquidity-verifier stream is removed: never constructed, never dormant.
# ---------------------------------------------------------------------------
PRIMARY_STREAM_MAX = 1
VERIFIER_STREAM_MAX = 0
MAX_ACTIVE_STREAMS = 1
LP_INTEGRITY_MODE = LP_INTEGRITY_MODE_DISABLED_SINGLE_STREAM
VERIFIER_STREAM_STATUS_DISABLED = "DISABLED"

# ---------------------------------------------------------------------------
# STRICT pump-suffix guard (discovery -> watchlist boundary)
# ---------------------------------------------------------------------------
NON_PUMP_GUARD_REASON = "NON_PUMP_SUFFIX"


def _is_pump_mint(mint: object) -> bool:
    """STRICT pump gate on the ACTUAL token mint/CA.

    True only for a non-empty ``str`` that ends EXACTLY with ``"pump"``
    (``mint.endswith("pump")``). Never a contains()/fuzzy/log-text match, and
    never evaluated against pool addresses or program ids: callers pass
    ``candidate["token_mint"]``, which the committed Stage 29.5.7 normalizer
    extracts from the IDL-pinned ``create_pool`` BASE-MINT account (index 3 —
    the pool account is index 0 and the quote mint index 4, so a pool address
    ending in "pump" can never stand in for the token mint).
    """
    return isinstance(mint, str) and bool(mint) and mint.endswith("pump")


def guard_pump_suffix_candidates(
    candidates: object,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Split discovery candidates into (accepted, dropped) with ``_is_pump_mint``.

    This runs immediately after mint extraction and is the ONLY door into the
    watchlist, so a non-pump mint is dropped BEFORE market enrichment, before
    watch_state/watchlist insertion, before any paper-engine artifact stream,
    and before would_ping / private_ping eligibility. Malformed candidates
    (non-dict, missing/empty/non-string mint) are dropped the same way.
    """
    accepted: List[Dict[str, Any]] = []
    dropped: List[Dict[str, Any]] = []
    from PHX2.free_tier_producer.migration_admission import candidate_migration_is_admitted
    for cand in (candidates or []):
        if isinstance(cand, dict) and candidate_migration_is_admitted(cand):
            accepted.append(cand)
        else:
            dropped.append(cand if isinstance(cand, dict) else {"token_mint": cand})
    return accepted, dropped
PRODUCER_SUMMARY_BASENAME = "producer_summary.json"
# PHX2-E2E-005 authenticated checkpoint observability artifacts.
CHECKPOINT_STATUS_BASENAME = "checkpoint_status.json"
CHECKPOINT_QUARANTINE_BASENAME = "checkpoint_quarantine.json"

# ---------------------------------------------------------------------------
# Discovery modes + run profiles (2026-07-10 two-hour-run fix)
# ---------------------------------------------------------------------------
DISCOVERY_MODE_WS = "ws"
DISCOVERY_MODE_POLLING = "polling"
DISCOVERY_MODE_HYBRID = "hybrid"
DISCOVERY_MODES = (DISCOVERY_MODE_WS, DISCOVERY_MODE_POLLING, DISCOVERY_MODE_HYBRID)

# Effective-cap resolution order: explicit CLI flag > profile > base default.
# Base defaults preserve the historical values exactly (no profile => old behavior).
# The discovery-shape keys (ws_window cadence + per-poll bounds + market-refresh budget) are
# resolvable too so a profile can tighten Helius spend by itself (a low-credit profile does not
# rely on the operator remembering the per-poll flags).
PROFILE_BASE_DEFAULTS: Dict[str, Any] = {
    "max_runtime_seconds": 7200.0,
    "max_sends_per_run": 3,
    "max_raw_ws_notifications_total": 120000,
    "max_seed_windows": 120,
    "max_candidates_total": 400,
    "max_gettransaction_total": 1024,
    "max_market_requests_total": 5000,
    "max_429_total": 5,
    "max_rpc_errors_total": 12,
    "max_polls_total": 5000,
    "reseed_interval_seconds": None,    # mode-dependent (see _MODE_RESEED_DEFAULTS)
    # Discovery-shape (base values == historical argparse defaults; no profile => old behavior).
    "ws_window_every_n_reseeds": 1,             # HYBRID: open a WS window every Nth reseed
    "poll_pools_per_cycle": 8,                  # NEW pools examined per poll (=> getSig calls)
    "poll_sig_page_limit": 1000,               # getSignaturesForAddress page size
    "poll_max_gettransaction_per_cycle": 8,    # getTransaction fetches per poll
    "market_refresh_max_calls_per_token": 4,   # bounded escalating market refresh per mint
}

# Raw-WS cap sizing (NOT Helius credits): observed 2026-07-09 ≈ 40k raw msgs per 90s window
# (~450/s). A 2h run at reseed=240s opens ~30 windows ≈ 1.2M raw msgs expected; the profile caps
# carry ~1.6x headroom so the raw-message safety bound never kills a healthy long run again.
PROFILES: Dict[str, Dict[str, Any]] = {
    "short_test_10m": {
        "max_runtime_seconds": 600.0,
        "max_sends_per_run": 3,
        "max_raw_ws_notifications_total": 200000,
        "max_seed_windows": 6,
        "max_candidates_total": 100,
        "max_gettransaction_total": 256,
        "max_market_requests_total": 2000,
        "max_429_total": 5,
        "max_rpc_errors_total": 12,
        "max_polls_total": 60,
    },
    "live_2h": {
        "max_runtime_seconds": 7200.0,
        "max_sends_per_run": 12,
        "max_raw_ws_notifications_total": 2000000,
        "max_seed_windows": 40,
        "max_candidates_total": 400,
        "max_gettransaction_total": 1024,
        "max_market_requests_total": 20000,
        "max_429_total": 8,
        "max_rpc_errors_total": 24,
        "max_polls_total": 600,
    },
    "live_4h": {
        "max_runtime_seconds": 14400.0,
        "max_sends_per_run": 24,
        "max_raw_ws_notifications_total": 4000000,
        "max_seed_windows": 80,
        "max_candidates_total": 800,
        "max_gettransaction_total": 2048,
        "max_market_requests_total": 40000,
        "max_429_total": 8,
        "max_rpc_errors_total": 32,
        "max_polls_total": 1200,
    },
    # 2026-07-10 credit-optimization profiles. The live_2h HYBRID run burned ~80k Helius credits /
    # 2h (~40k/hr) almost entirely on the broad logsSubscribe firehose (1.55M raw WS msgs); at that
    # rate the 1M free tier lasts barely a day. These pin cheaper discovery + tighter run/per-poll
    # ceilings so a 24/7 posture is affordable, while keeping private-ping / paper / market-refresh
    # behavior and the strict pump-suffix guard unchanged.
    "live_2h_low_credit": {
        # Polling-only by DEFAULT: NO broad WS firehose. Discovery is then only surgical
        # getSignaturesForAddress + getTransaction reads (a few RPC/min), not a 450 msg/s socket.
        "discovery_mode": DISCOVERY_MODE_POLLING,
        "max_runtime_seconds": 7200.0,
        "max_sends_per_run": 12,                    # same send posture as live_2h
        "max_raw_ws_notifications_total": 120000,   # only bites if hybrid is force-enabled
        "max_seed_windows": 6,                      # ditto (polling opens no windows)
        "max_candidates_total": 400,
        "max_gettransaction_total": 512,            # lower than live_2h (1024)
        "max_market_requests_total": 8000,          # bounded (market HTTP is keyless, not Helius)
        "max_429_total": 6,                         # keep the 429 tripwire low
        "max_rpc_errors_total": 24,
        "max_polls_total": 300,                     # bounds cumulative getSignaturesForAddress
        "poll_pools_per_cycle": 6,                  # bounded pools (=> getSig calls) per poll
        "poll_sig_page_limit": 500,                 # smaller getSignaturesForAddress pages
        "poll_max_gettransaction_per_cycle": 6,     # lower per-poll getTransaction
        "market_refresh_max_calls_per_token": 3,    # bounded market refresh
    },
    "live_2h_hybrid_thin": {
        # Mostly polling with OCCASIONAL short WS windows (every 5th reseed) on a small raw-WS
        # budget (~10 short windows vs live_2h's 2.0M). A middle ground ONLY if pure polling
        # misses too many migrations — NOT for the immediate next low-credit test.
        "discovery_mode": DISCOVERY_MODE_HYBRID,
        "max_runtime_seconds": 7200.0,
        "max_sends_per_run": 12,
        "max_raw_ws_notifications_total": 400000,   # ~10 short windows (vs 2.0M) => ~4x less WS
        "max_seed_windows": 12,
        "max_candidates_total": 400,
        "max_gettransaction_total": 768,
        "max_market_requests_total": 12000,
        "max_429_total": 6,
        "max_rpc_errors_total": 24,
        "max_polls_total": 300,
        "ws_window_every_n_reseeds": 5,             # WS window only every 5th reseed (thin)
        "poll_pools_per_cycle": 6,
        "poll_sig_page_limit": 500,
        "poll_max_gettransaction_per_cycle": 6,
        "market_refresh_max_calls_per_token": 3,
    },
}

# Polling is cheap (one listing GET + a couple of surgical RPCs per cycle), so polling/hybrid
# reseed faster than the WS-window cadence by default. Explicit --reseed-interval-seconds wins.
_MODE_RESEED_DEFAULTS = {
    DISCOVERY_MODE_WS: 240.0,
    DISCOVERY_MODE_POLLING: 60.0,
    DISCOVERY_MODE_HYBRID: 120.0,
}


def resolve_effective_settings(args) -> Dict[str, Any]:
    """Pure cap/runtime/discovery resolution: explicit CLI flag > --profile > base default. The
    returned dict always contains every PROFILE_BASE_DEFAULTS key with a concrete value, plus
    ``profile`` and ``discovery_mode``.

    Discovery mode resolves with the SAME precedence: an explicit ``--discovery-mode`` wins, else
    the profile's ``discovery_mode`` (``live_2h_low_credit`` pins ``polling``), else the legacy
    base default ``ws`` — so no-profile / no-flag runs keep the historical WS default exactly.
    Raises ValueError on an unknown profile/mode."""
    profile = getattr(args, "profile", None)
    if profile is not None and profile not in PROFILES:
        raise ValueError(f"unknown profile: {profile!r}")
    overlay = PROFILES.get(profile, {}) if profile else {}
    explicit_mode = getattr(args, "discovery_mode", None)
    mode = str(explicit_mode or overlay.get("discovery_mode") or DISCOVERY_MODE_WS).lower()
    if mode not in DISCOVERY_MODES:
        raise ValueError(f"unknown discovery mode: {mode!r}")
    eff: Dict[str, Any] = {"profile": profile, "discovery_mode": mode}
    for key, base in PROFILE_BASE_DEFAULTS.items():
        explicit = getattr(args, key, None)
        if explicit is not None:
            eff[key] = explicit
        elif key in overlay:
            eff[key] = overlay[key]
        elif key == "reseed_interval_seconds":
            eff[key] = _MODE_RESEED_DEFAULTS[mode]
        else:
            eff[key] = base
    return eff


def route_discovery(*, discovery_mode, reseed_index, ws_window_every_n_reseeds,
                    ws_discover_fn, poll_discover_fn,
                    ws_budget_remaining=0, ws_windows_open=0, max_seed_windows=0,
                    on_ws_skipped=None) -> List[Dict[str, Any]]:
    """Route ONE reseed tick to the discovery backend(s) for ``discovery_mode`` and return the
    merged, mint-deduped candidate list.

    HARD INVARIANT (the low-credit lever): the broad WS firehose ``ws_discover_fn`` is opened ONLY
    in ``ws`` and ``hybrid`` modes. In ``polling`` mode ``ws_discover_fn`` is NEVER called — no
    logsSubscribe socket is opened and the raw-WS counter stays 0. In ``hybrid`` a WS window opens
    only every Nth reseed AND only while the raw-WS/seed-window budget remains (else it downgrades
    to polling-only via ``on_ws_skipped`` without stopping the run)."""
    collected: List[Dict[str, Any]] = []
    seen_mints: set = set()

    def _merge(cands) -> None:
        for c in (cands or []):
            m = c.get("token_mint") if isinstance(c, dict) else None
            if m in seen_mints:
                continue
            seen_mints.add(m)
            collected.append(c)

    if discovery_mode == DISCOVERY_MODE_WS:
        _merge(ws_discover_fn())
    elif discovery_mode == DISCOVERY_MODE_POLLING:
        _merge(poll_discover_fn())          # NO ws_discover_fn call in polling-only, ever
    else:   # HYBRID: cheap poll every reseed; WS window every Nth reseed while budget remains.
        _merge(poll_discover_fn())
        ws_due = (int(reseed_index) % max(1, int(ws_window_every_n_reseeds))) == 0
        if ws_due:
            if ws_budget_remaining <= 0 or ws_windows_open >= max_seed_windows:
                if on_ws_skipped is not None:
                    on_ws_skipped()
            else:
                _merge(ws_discover_fn())
    return collected


_BIRDEYE_ENV_KEYS = (
    "PHX2_STAGE29_2_BIRDEYE_API_KEY",
    "PHX2_STAGE29_2_BIRDEYE_BASE_URL",
    "PHX2_STAGE29_2_ALLOW_LIVE_HTTP",
    "PHX2_STAGE29_2_HTTP_TIMEOUT_SECONDS",
)

_GRPC_ENV_KEYS = (
    "PHX2_CHAINSTACK_YELLOWSTONE_GRPC_ENDPOINT",
    "PHX2_CHAINSTACK_YELLOWSTONE_X_TOKEN",
    "PHX2_STAGE28_11_ALLOW_LIVE_GRPC",
    "PHX2_STAGE28_11_GRPC_TIMEOUT_SECONDS",
)


def _utc_now_dt() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _utc_now_iso() -> str:
    return _iso(_utc_now_dt())


def path_is_forbidden(path: str) -> bool:
    """True iff ``path`` (normalized) sits inside any historical ceremony/production tree."""
    norm = os.path.normpath(os.path.abspath(str(path))).lower()
    return any(norm == root or norm.startswith(root + os.sep)
               for root in _FORBIDDEN_WRITE_ROOTS)


def _producer_mode_label(
    provider_mode: str, discord_enabled: bool, telegram_enabled: bool = False
) -> str:
    if telegram_enabled:
        return ("FREE_TIER_TELEGRAM" if provider_mode == PROVIDER_MODE_FREE_TIER
                else provider_mode + "_TELEGRAM")
    if discord_enabled:
        return ("FREE_TIER_PRIVATE_DISCORD" if provider_mode == PROVIDER_MODE_FREE_TIER
                else provider_mode + "_PRIVATE_DISCORD")
    return ("FREE_TIER_NO_SEND" if provider_mode == PROVIDER_MODE_FREE_TIER
            else provider_mode + "_NO_SEND")


def _polling_required(provider_mode: str, discovery_mode: str) -> bool:
    return (
        provider_mode == PROVIDER_MODE_PAID_WITH_FALLBACK
        or (
            provider_mode == PROVIDER_MODE_FREE_TIER
            and discovery_mode in (DISCOVERY_MODE_POLLING, DISCOVERY_MODE_HYBRID)
        )
    )


def harden_no_send_env(*, allow_birdeye_fallback: bool,
                       allow_paid_provider: bool = False) -> int:
    """NO-SEND hardening: always drop send auth; retain only requested read-only providers."""
    removed = 0
    if os.environ.pop(ENV_WEBHOOK, None) is not None:
        removed += 1
    if not (allow_birdeye_fallback or allow_paid_provider):
        for k in _BIRDEYE_ENV_KEYS:
            if os.environ.pop(k, None) is not None:
                removed += 1
    if not allow_paid_provider:
        for k in _GRPC_ENV_KEYS:
            if os.environ.pop(k, None) is not None:
                removed += 1
    return removed


def _append_jsonl(path: Path, record: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, sort_keys=True) + "\n")


def resolve_watch_state_paths(
    *, out_dir: object, cursor_state_dir: object,
) -> Dict[str, Any]:
    """Decide where the watch checkpoint LIVES and where it is MIRRORED.

    The authoritative watch checkpoint is DURABLE state, not a run artifact.

    2026-07-31 restart-state root cause: it was anchored in ``--out-dir``,
    which the operator rotates every run (``runs/..._<stamp>Z``). The
    20260731T224645Z producer wrote 43 valid generations there; the
    20260731T231533Z restart opened a brand-new run dir, found nothing,
    reported ``CHECKPOINT_NOT_FOUND`` and started with an EMPTY watchlist.
    Every tracked candidate's provenance, activation progress, ATH binding and
    tracker state died with the old directory -- and one LIVE_HELIUS mint at
    1.20x / 29,719-of-35,663 was re-admitted minutes later as a DEX backfill
    candidate at 1.39x / 4,571-of-41,506, coverage PARTIAL_SINCE_ADMISSION.

    It now anchors in the STABLE state directory beside the stream cursor, the
    ATH checkpoint, the migration journal and the census -- every other
    document that already had to survive a restart. The run-artifact copies
    remain as byte-identical read-only MIRRORS, so the dashboard, the paper
    tooling, the offline selftests and the run-artifact redaction scan are all
    unaffected.

    With no stable directory configured (development posture) the durable
    location IS the run directory and behaviour is exactly as before; the armed
    production contract refuses that choice for the cursor already.
    """

    run_dir = Path(str(out_dir))
    if cursor_state_dir:
        state_dir = Path(str(cursor_state_dir))
        state_dir.mkdir(parents=True, exist_ok=True)
    else:
        state_dir = run_dir
    return {
        "durable": str(state_dir) != str(run_dir),
        "state_dir": str(state_dir),
        "run_dir": str(run_dir),
        "watch_state_path": str(state_dir / WATCH_STATE_BASENAME),
        # Append-only terminal watch history (PHX2-E2E-002): terminal
        # candidates are archived here and release their active-watch capacity
        # slot. Durable for the same reason as the checkpoint -- it is the
        # cross-restart alert-replay guard.
        "watch_terminal_history_path": str(
            state_dir / WATCH_TERMINAL_HISTORY_BASENAME),
        "watch_state_mirror_path": str(run_dir / WATCH_STATE_BASENAME),
        "watch_terminal_history_mirror_path": str(
            run_dir / WATCH_TERMINAL_HISTORY_BASENAME),
    }


def adopt_legacy_run_dir_watch_state(paths: Mapping[str, Any]) -> Dict[str, Any]:
    """Promote pre-remediation run-dir watch state into the durable location.

    Applies ONLY when a stable state directory is configured and holds no watch
    state at all; the durable pair always wins whenever it exists. Bytes are
    copied verbatim, so the envelope digest chain and every record digest still
    authenticate and the restore path stays a single, ordinary load.

    Returns ``{"adopted": bool, "copied": [...], "errors": [...]}``. Failures
    are RETURNED, never swallowed: the caller discloses them through the error
    ledger.
    """

    result: Dict[str, Any] = {"adopted": False, "copied": [], "errors": []}
    if not paths.get("durable"):
        return result
    primary = Path(str(paths["watch_state_path"]))
    backup = Path(str(paths["watch_state_path"]) + ".bak")
    if primary.exists() or backup.exists():
        return result
    mirror = Path(str(paths["watch_state_mirror_path"]))
    for legacy, durable, label in (
            (mirror, primary, "watch_state"),
            (Path(str(mirror) + ".bak"), backup, "watch_state_backup"),
            (Path(str(paths["watch_terminal_history_mirror_path"])),
             Path(str(paths["watch_terminal_history_path"])),
             "watch_terminal_history")):
        try:
            if legacy.exists() and not durable.exists():
                durable.parent.mkdir(parents=True, exist_ok=True)
                durable.write_bytes(legacy.read_bytes())
                result["adopted"] = True
                result["copied"].append(label)
        except OSError as exc:
            result["errors"].append(exc)
    return result


def _market_context_is_fresh(ctx: Any, max_age_seconds: float = 300.0) -> bool:
    """True iff ``ctx['market_context_fetched_at_utc']`` parses and is within ``max_age`` of now.
    Mirrors the committed composer freshness ceiling; fail-CLOSED (False) on any parse issue so a
    weak-MEDIUM candidate with unverifiable freshness is blocked, never sent."""
    try:
        ts = ctx.get("market_context_fetched_at_utc") if isinstance(ctx, dict) else None
        if not isinstance(ts, str) or not ts:
            return False
        fetched = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        age = (_utc_now_dt() - fetched).total_seconds()
        return 0.0 <= age <= float(max_age_seconds)
    except Exception:
        return False


class DiscordBlockLedger:
    """Per-run DISTINCT-mint tally of private-Discord dispatch blocks for the heartbeat /
    producer_summary / dashboard. A mint blocked on every recheck is ONE blocked candidate; the
    first block per (mint, category) is the one that writes an artifact row. Never raises."""

    def __init__(self) -> None:
        self._high: Dict[str, str] = {}      # mint -> mapped HIGH reason (first seen)
        self._medium: Dict[str, str] = {}    # mint -> mapped weak-MEDIUM reason (first seen)

    def record(self, decision: Any, mint: str) -> bool:
        """Fold one block decision; return True the FIRST time this (mint, category) is seen."""
        try:
            if not isinstance(mint, str) or not mint:
                return False
            td = getattr(decision, "terminal_decision", None)
            if td == SKIPPED_HIGH_RISK_DISCORD and mint not in self._high:
                self._high[mint] = getattr(decision, "mapped_reason", None) or "HIGH_RISK_OTHER"
                return True
            if td == SKIPPED_MEDIUM_RISK_WEAK_STRUCTURE and mint not in self._medium:
                self._medium[mint] = (getattr(decision, "mapped_reason", None)
                                      or "MEDIUM_RISK_STRUCTURE_REASON")
                return True
            return False
        except Exception:
            return False

    @staticmethod
    def _counts(mapping: Dict[str, str]) -> Dict[str, int]:
        out: Dict[str, int] = {}
        for reason in mapping.values():
            out[reason] = out.get(reason, 0) + 1
        return dict(sorted(out.items()))

    def snapshot(self) -> Dict[str, Any]:
        return {
            "kind": "FREE_TIER_DISCORD_BLOCK_SUMMARY",
            "high_risk_discord_block_count": len(self._high),
            "medium_risk_structure_block_count": len(self._medium),
            "high_risk_blocked_mints": sorted(self._high)[:16],
            "medium_risk_blocked_mints": sorted(self._medium)[:16],
            "high_risk_block_reason_counts": self._counts(self._high),
            "medium_risk_block_reason_counts": self._counts(self._medium),
        }


def make_discord_risk_gate(*, risk_engine: Any, discord_block_ledger: "DiscordBlockLedger",
                           discord_blocks_path: Path, min_liquidity_usd: Any, mode: str,
                           errors: Any, floor_fn: Any = None,
                           lp_integrity_mode: Optional[str] = None) -> Any:
    """Build the PRE-RESERVE private-Discord dispatch gate.

    run_cap1_candidates invokes the returned callable AFTER market context is present and BEFORE
    build_revalidation_request / compose_and_maybe_send — so a returned reason blocks the candidate
    with NO dedupe reserve, NO guarded webhook send, and NO send-cap / private_ping consume. The
    risk policy runs FIRST (RISK_HIGH blocked; RISK_MEDIUM warning-only in the
    explicit single-stream mode; alternate legacy policy remains opt-in);
    a risk-allowed candidate falls through to ``floor_fn`` (the committed minimum-liquidity floor by
    default). Extracted to module scope so the selftest can drive the EXACT production gate through
    run_cap1_candidates and prove the ordering. Total: a raise fails CLOSED (blocks) upstream."""
    _floor = floor_fn if floor_fn is not None else (
        lambda m, c: liquidity_floor_block_reason(m, c, min_liquidity_usd=min_liquidity_usd))

    def discord_risk_gate(mint: str, ctx: Dict[str, Any]) -> Optional[str]:
        # Fold THIS cycle's resolved market context into the risk state so the assessment reflects
        # the freshest LP/price/MC (a duplicate sample only reinforces; it never lowers the risk).
        try:
            risk_engine.observe_market_sample(mint, ctx)
        except Exception:
            pass
        assessment = risk_engine.assess(mint)
        if isinstance(assessment, dict):
            ctx["risk_assessment"] = {
                "risk_label": assessment.get("risk_label"),
                "risk_reasons": list(assessment.get("risk_reasons") or ()),
                "risk_line": assessment.get("risk_line"),
            }
        decision = classify_discord_dispatch(
            assessment,
            liquidity_usd=ctx.get("liquidity_usd"),
            market_cap_usd=ctx.get("current_market_cap_usd"),
            market_fresh=_market_context_is_fresh(ctx),
            lp_integrity_mode=lp_integrity_mode)
        if not decision.allowed:
            try:
                if discord_block_ledger.record(decision, mint):
                    _append_jsonl(discord_blocks_path, {
                        "kind": "FREE_TIER_DISCORD_BLOCK",
                        "token_mint": mint,
                        "terminal_decision": decision.terminal_decision,
                        "mapped_reason": decision.mapped_reason,
                        "risk_label": decision.risk_label,
                        "risk_reasons": list(decision.risk_reasons),
                        "market_context": {
                            "basis": ctx.get("basis"),
                            "current_price": ctx.get("current_price"),
                            "current_market_cap_usd": ctx.get("current_market_cap_usd"),
                            "liquidity_usd": ctx.get("liquidity_usd"),
                            "market_context_fetched_at_utc": ctx.get("market_context_fetched_at_utc"),
                        },
                        "blocked_at_utc": _utc_now_iso(),
                        "producer_mode": mode,
                    })
            except Exception as exc:
                errors.log("discord_block_record", exc)
            return decision.terminal_decision   # BLOCK pre-reserve / pre-webhook / pre-cap
        return _floor(mint, ctx)

    return discord_risk_gate


def observe_watchlist_baseline(*, watchlist: Any, mint: str, market: Any,
                               observation_source: str, max_age_seconds: float,
                               now_iso: str,
                               on_activation_event: Any = None) -> Optional[Dict[str, Any]]:
    """Read-only market observation into the centralized watchlist baseline.

    Baseline observation is decoupled from send authorization: this seam runs
    on the pricing-tail path for EVERY tracked mint — including candidates the
    security policy currently blocks — so an admitted genuine migration can
    capture its immutable migration MC from the earliest valid fresh
    authoritative observation and later prove the 1.20x crossing with another
    fresh observation.  It performs NO compose, NO reserve, NO ledger
    mutation, and NO transport call; the crossing tick itself remains
    send-blocked inside the entry state machine, and the compose-time gates
    (security proof, risk, LP floor, dip, dedupe) still decide every send."""
    if not isinstance(mint, str) or not mint or not isinstance(market, dict):
        return None
    entry = watchlist.get(mint) if hasattr(watchlist, "get") else None
    if entry is None or not entry.is_active():
        return None
    provider_ts = (market.get("provider_timestamp_utc")
                   or market.get("market_context_fetched_at_utc")
                   or market.get("fetched_at_utc"))
    observed = entry.observe_market(
        current_market_cap_usd=market.get("current_market_cap_usd"),
        current_price=market.get("current_price"),
        current_supply=market.get("supply_at_observation"),
        provider_timestamp_utc=provider_ts,
        observed_at_utc=now_iso,
        observation_source=observation_source,
        max_age_seconds=max_age_seconds,
        central_ath=market.get("central_ath"),
        pumpswap_reserve=market.get("pumpswap_reserve"),
    )
    if on_activation_event is not None:
        for event in observed.get("events", []):
            try:
                on_activation_event(event)
            except Exception:
                pass
    return observed


def build_security_artifact_record(
    *, entry: Any, decision: Any, reason: Any, tick: int,
    observed_at_utc: str, fee_gate_lifecycle: Any,
    central_ath: Any,
) -> Dict[str, Any]:
    """Project one immutable security/ATH/activation proof for artifacts."""

    mint = getattr(entry, "token_mint", None)
    return {
        "kind": "PHX2_SECURITY_DECISION",
        "token_mint": mint,
        "candidate_id": getattr(entry, "candidate_id", None),
        "tick": int(tick),
        "observed_at_utc": observed_at_utc,
        "block_reason": reason,
        "fee_gate_lifecycle": (
            dict(fee_gate_lifecycle) if isinstance(fee_gate_lifecycle, dict) else {}),
        "decision": (decision.to_dict() if hasattr(decision, "to_dict") else None),
        "phx1_structural_policy": getattr(
            decision, "phx1_structural_policy", PHX1_STRUCTURAL_POLICY_ENFORCE),
        "original_phx1_structural_verdict": getattr(
            decision, "original_phx1_structural_verdict", None),
        "effective_phx1_policy_verdict": getattr(
            decision, "effective_phx1_policy_verdict", None),
        "central_ath": dict(central_ath) if isinstance(central_ath, dict) else {},
        "activation": (entry.activation_snapshot()
                       if hasattr(entry, "activation_snapshot") else {}),
        "compose_attempts": 0 if reason else None,
        "reservation_attempts": 0 if reason else None,
        "active_ledger_mutations": 0 if reason else None,
        "discord_transport_attempts": 0 if reason else None,
        "telegram_transport_attempts": 0 if reason else None,
        "delivery_transport_attempts": 0 if reason else None,
    }


class ErrorLedger:
    """Appends closed-set producer error records to ``errors.jsonl``. Never raises; never stores
    exception text (TYPE only), a URL, or any secret."""

    def __init__(self, out_dir: str) -> None:
        self._path = Path(out_dir) / ERRORS_BASENAME
        self.count = 0

    def log(self, stage: str, exc: BaseException, note: Optional[str] = None) -> None:
        try:
            rec = {
                "kind": "FREE_TIER_PRODUCER_ERROR",
                "logged_at_utc": _utc_now_iso(),
                "stage": str(stage)[:64],
                "error_type": type(exc).__name__,
            }
            if note and artifacts.scan_value_safe(note):
                rec["note"] = str(note)[:120]
            _append_jsonl(self._path, rec)
            self.count += 1
        except Exception:
            pass


# --------------------------------------------------------------------------- preflight


_HELIUS_ONLY_DISABLED_ENV_NAMES = frozenset({
    "PHX2_CHAINSTACK_YELLOWSTONE_GRPC_ENDPOINT",
    "PHX2_CHAINSTACK_YELLOWSTONE_X_TOKEN",
    "PHX2_STAGE28_11_ALLOW_LIVE_GRPC",
    "PHX2_STAGE28_11_GRPC_TIMEOUT_SECONDS",
    "HELIUS_GRPC_ENDPOINT",
})


def _load_env_file_for_source_mode(path: str, source_mode: str) -> int:
    """Load dotenv values without resolving disabled-source credentials."""

    helius_only = (
        str(source_mode).strip().upper().replace("-", "_")
        == "HELIUS_PRIMARY"
    )
    if not helius_only:
        return sess.load_env_file(path)
    loaded = 0
    for original in Path(path).read_text(encoding="utf-8").splitlines():
        line = original.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, raw = line.split("=", 1)
        name = name.strip()
        if not name or name == "PHX2_MIGRATION_SOURCE_MODE":
            continue
        if helius_only and name in _HELIUS_ONLY_DISABLED_ENV_NAMES:
            continue
        os.environ[name] = raw.strip().strip('"').strip("'")
        loaded += 1
    return loaded


def _scrub_disabled_source_environment(source_mode: str) -> int:
    """Make accidental Chainstack resolution unreachable in Helius-only mode."""

    if (
        str(source_mode).strip().upper().replace("-", "_")
        != "HELIUS_PRIMARY"
    ):
        return 0
    removed = 0
    for name in _HELIUS_ONLY_DISABLED_ENV_NAMES:
        if name in os.environ:
            del os.environ[name]
            removed += 1
    return removed


def _detect_paid_preflight_readiness(
    source_runtime_plan: Any,
    *,
    chainstack_detector: Optional[Callable[[], Any]] = None,
    birdeye_detector: Optional[Callable[[], Any]] = None,
) -> Dict[str, Any]:
    """Read only the credentials required by the selected paid runtime.

    In particular, Helius-only mode must not import or invoke the Chainstack
    readiness surface: that surface resolves the Chainstack endpoint/token.
    Detector injection keeps this branch deterministic in offline tests.
    """

    if birdeye_detector is None:
        from PHX2.stage29.stage29_2_birdeye_readiness import (
            detect_stage29_2_birdeye_readiness,
        )
        birdeye_detector = detect_stage29_2_birdeye_readiness
    birdeye_report = birdeye_detector()
    birdeye_status = str(getattr(birdeye_report, "status", "UNAVAILABLE"))

    if bool(source_runtime_plan.construct_chainstack_grpc_channel):
        if chainstack_detector is None:
            from PHX2.stage28.chainstack_yellowstone_grpc_readiness import (
                detect_stage28_11_grpc_readiness,
            )
            chainstack_detector = detect_stage28_11_grpc_readiness
        chainstack_report = chainstack_detector()
        chainstack_status = str(
            getattr(chainstack_report, "status", "UNAVAILABLE")
        )
        chainstack_ready = chainstack_status == "READY"
    else:
        chainstack_status = "DISABLED"
        chainstack_ready = True

    return {
        "chainstack_status": chainstack_status,
        "chainstack_ready": chainstack_ready,
        "birdeye_status": birdeye_status,
        "birdeye_ready": birdeye_status == "READY",
    }


def run_preflight(args) -> int:
    if args.env:
        launcher_source_mode = os.environ.get(
            "PHX2_MIGRATION_SOURCE_MODE"
        )
        explicit_source_mode = getattr(args, "migration_source_mode", None)
        effective_source_mode = launcher_source_mode or explicit_source_mode
        if not effective_source_mode:
            print("[refused] MIGRATION_SOURCE_MODE_REFUSED: "
                  "migration source mode is required; no fallback is permitted")
            return 2
        n = _load_env_file_for_source_mode(
            args.env,
            str(effective_source_mode),
        )
        os.environ["PHX2_MIGRATION_SOURCE_MODE"] = str(
            launcher_source_mode or explicit_source_mode
        )
        scrubbed = (
            sess.scrub_unrelated_env()
            + _scrub_disabled_source_environment(str(effective_source_mode))
        )
        print(f"env: loaded {n} vars; scrubbed {scrubbed} unrelated; values NEVER printed.")
    key_present = bool((os.environ.get("HELIUS_API_KEY") or "").strip())
    url_present = bool((os.environ.get("HELIUS_RPC_URL") or "").strip())
    webhook_present = bool((os.environ.get(ENV_WEBHOOK) or "").strip())
    telegram_status: Optional[Dict[str, Any]] = None
    telegram_ok = True
    if bool(getattr(args, "enable_telegram", False)):
        try:
            telegram_status = TelegramConfig.from_mapping(os.environ).redacted_status()
        except TelegramConfigError as exc:
            telegram_ok = False
            print(f"telegram configuration: REFUSED reason={exc.reason}")
    birdeye_present = bool((os.environ.get("PHX2_STAGE29_2_BIRDEYE_API_KEY") or "").strip())
    try:
        provider_mode = normalize_provider_mode(getattr(args, "provider_mode", None))
    except ValueError as exc:
        print(f"[refused] {exc}")
        return 2
    paid_mode = provider_mode != PROVIDER_MODE_FREE_TIER
    try:
        source_selection = load_source_selection(
            explicit_mode=getattr(args, "migration_source_mode", None)
        )
    except ValueError as exc:
        print(f"[refused] MIGRATION_SOURCE_MODE_REFUSED: {exc}")
        return 2
    source_runtime_plan = build_production_source_runtime_plan(
        source_selection,
        http_recovery_enabled=bool(
            getattr(args, "enable_helius_http_recovery", False)
        ),
    )
    helius_configured = False
    if (
        source_selection.helius_production_authority
        or source_selection.helius_shadow_enabled
    ):
        try:
            load_helius_source_config(env_path=Path(args.env))
            helius_configured = True
        except ValueError:
            helius_configured = False
    source_contract = validate_production_source_contract(
        selection=source_selection,
        helius_configured=helius_configured,
        http_recovery_enabled=bool(
            getattr(args, "enable_helius_http_recovery", False)
        ),
        subscription_request=approved_tight_subscription_request(1),
        send_authority_count=1,
        chainstack_candidate_authority=False,
    )
    if not source_contract.allowed:
        print(
            "[refused] MIGRATION_SOURCE_CONTRACT_REFUSED: "
            + ", ".join(source_contract.refusals)
        )
        return 2
    grpc_ready = birdeye_ready = False
    grpc_status = birdeye_status = "NOT_REQUIRED"
    if paid_mode:
        readiness = _detect_paid_preflight_readiness(source_runtime_plan)
        grpc_status = readiness["chainstack_status"]
        birdeye_status = readiness["birdeye_status"]
        grpc_ready = bool(readiness["chainstack_ready"])
        birdeye_ready = bool(readiness["birdeye_ready"])
    try:
        import websocket  # noqa: F401
        ws_lib = True
    except Exception:
        ws_lib = False
    try:
        from PHX2.paper_trading.pricing import normalize_record  # noqa: F401
        paper_ok = True
    except Exception:
        paper_ok = False
    triple = ledgerlib.compute_baseline(args.ledger_path)
    baseline = (f"{triple.sha256}:{triple.size_bytes}:{triple.line_count}"
                if triple else "MISSING (fresh ledger will be created)")
    print(f"discovery env: HELIUS_API_KEY={'PRESENT' if key_present else 'MISSING'} "
          f"HELIUS_RPC_URL={'PRESENT' if url_present else 'MISSING'} "
          f"websocket_client_lib={ws_lib}")
    if paid_mode:
        print("market source: PAID_MARKET_PRIMARY; readiness shown below; "
              "request concurrency=1; values NEVER printed")
    else:
        print(f"market source: FREE_TIER (keyless public pools data; no paid provider required); "
              f"optional-fallback-key present={birdeye_present} (used ONLY with "
              f"--allow-birdeye-fallback)")
    print(f"provider mode: {provider_mode}; chainstack_readiness={grpc_status}; "
          f"birdeye_readiness={birdeye_status} (presence/status only; values NEVER printed)")
    print(
        "migration source: "
        f"mode={source_selection.mode} "
        f"primary={source_selection.authoritative_source} "
        f"recovery={source_runtime_plan.recovery_authority} "
        f"helius_configured={helius_configured} "
        f"helius_http_recovery={bool(getattr(args, 'enable_helius_http_recovery', False))} "
        f"shadow={source_runtime_plan.shadow_source} "
        f"chainstack_configured_for_runtime="
        f"{source_runtime_plan.resolve_chainstack_credentials}"
    )
    print(f"private discord: DISABLED BY DEFAULT; webhook_present={webhook_present} "
          f"(value NEVER printed; used ONLY with the full --enable-private-discord arm gate)")
    if telegram_status is not None:
        print("telegram_enabled=true telegram_token_configured=true "
              "telegram_chat_configured=true discord_enabled=false")
    print(f"paper engine importable: {paper_ok} (PHX2.paper_trading)")
    print(f"free-tier ledger [{args.ledger_path}]: baseline={baseline}")
    print(f"ledger path forbidden={path_is_forbidden(args.ledger_path)} "
          f"out dir forbidden={path_is_forbidden(args.out_dir)} (both must be False)")
    print("preflight: opened NO socket, made NO RPC, made NO GET, performed NO send, mutated "
          "NOTHING, printed NO secret value.")
    if source_selection.helius_production_authority:
        discovery_ok = helius_configured and ws_lib
    elif provider_mode == PROVIDER_MODE_PAID_PRIMARY:
        discovery_ok = grpc_ready
    elif provider_mode == PROVIDER_MODE_PAID_WITH_FALLBACK:
        discovery_ok = key_present and url_present
    else:
        discovery_ok = key_present and url_present and ws_lib
    ok = discovery_ok and paper_ok \
        and (
            not paid_mode
            or (
                birdeye_ready
                and (
                    grpc_ready
                    if source_selection.chainstack_production_authority
                    else helius_configured
                )
            )
        ) \
        and telegram_ok \
        and not path_is_forbidden(args.ledger_path) and not path_is_forbidden(args.out_dir)
    print(f"PREFLIGHT: {'OK' if ok else 'REFUSE (missing prerequisites above)'}")
    return 0 if ok else 2


# --------------------------------------------------------------------------- arm gate (discord)


def verify_discord_arm(args) -> Optional[str]:
    """Full arm gate for --enable-private-discord. Returns a refusal reason or None."""
    if not getattr(args, "ack_live_free_tier", False):
        return "MISSING_ACK_FLAG (--ack-live-free-tier)"
    if not getattr(args, "i_understand_this_can_send", False):
        return "MISSING_ACK_FLAG (--i-understand-this-can-send)"
    if getattr(args, "confirm_token", None) != LOCKED_CONFIRM_TOKEN:
        return "CONFIRM_TOKEN_MISMATCH"
    if not args.require_baseline:
        return "MISSING_REQUIRE_BASELINE"
    required = ledgerlib.parse_require_baseline(args.require_baseline)
    if required is None:
        return "REQUIRE_BASELINE_MALFORMED"
    actual = ledgerlib.compute_baseline(args.ledger_path)
    if actual is not None and not ledgerlib.baseline_matches(actual, required):
        return "BASELINE_MISMATCH"
    if not (os.environ.get(ENV_WEBHOOK) or "").strip():
        return "WEBHOOK_MISSING"
    return None


def verify_telegram_arm(args) -> Tuple[Optional[str], Optional[TelegramConfig]]:
    """Full production Telegram arm gate; never returns secret-bearing detail."""

    if not getattr(args, "ack_live_free_tier", False):
        return "MISSING_ACK_FLAG", None
    if not getattr(args, "i_understand_this_can_send", False):
        return "MISSING_SEND_ACK_FLAG", None
    if getattr(args, "confirm_token", None) != LOCKED_CONFIRM_TOKEN:
        return "CONFIRM_TOKEN_MISMATCH", None
    if not args.require_baseline:
        return "MISSING_REQUIRE_BASELINE", None
    required = ledgerlib.parse_require_baseline(args.require_baseline)
    if required is None:
        return "REQUIRE_BASELINE_MALFORMED", None
    actual = ledgerlib.compute_baseline(args.ledger_path)
    if actual is not None and not ledgerlib.baseline_matches(actual, required):
        return "BASELINE_MISMATCH", None
    try:
        config = TelegramConfig.from_mapping(os.environ)
    except TelegramConfigError as exc:
        return exc.reason, None
    return None, config


#: The sliding window over which provider reconnects count toward the
#: RECONNECT_STORM breaker.  The breaker exists to stop rapid reconnect CHURN
#: (a storm), not to bound the lifetime of a healthy ``--run-forever`` owner:
#: counting reconnects cumulatively guaranteed eventual self-termination on any
#: long run (proven live 2026-07-27: 6 provider-initiated stream resets spread
#: over 2.9 h -- each recovered in ~1 s with zero data loss -- crossed the
#: lifetime cap and latched ``PAID_PROVIDER_RECONNECT_STORM`` against a stream
#: that was CONNECTED_LIVE_HEALTHY, ending the run as SOURCE_FAILURE).
RECONNECT_STORM_WINDOW_SECONDS = 1800.0


class ReconnectStormWindow:
    """Sliding-window view over a cumulative provider reconnect counter.

    ``observe(cumulative)`` returns how many reconnects occurred within the
    trailing window.  A decreasing cumulative counter (a fresh provider
    instance) resets the window.  Deterministic under an injected clock.
    """

    def __init__(
        self,
        *,
        window_seconds: float = RECONNECT_STORM_WINDOW_SECONDS,
        now_fn: Callable[[], float] = time.monotonic,
    ) -> None:
        self._window_seconds = float(window_seconds)
        self._now = now_fn
        self._samples: List[Tuple[float, int]] = []

    def observe(self, cumulative: object) -> int:
        try:
            count = int(cumulative or 0)
        except (TypeError, ValueError):
            count = 0
        now = float(self._now())
        if self._samples and count < self._samples[-1][1]:
            self._samples = []
        self._samples.append((now, count))
        floor = now - self._window_seconds
        while self._samples and self._samples[0][0] < floor:
            self._samples.pop(0)
        oldest = self._samples[0][1] if self._samples else count
        return max(0, count - oldest)


def paid_provider_safety_error(
    snapshot: Any,
    *,
    max_reconnects: int,
    reconnects_in_window: Optional[int] = None,
) -> Optional[str]:
    """Closed-set automatic-stop reason for the paid stream owner.

    ``reconnects_in_window`` (when supplied by the session's
    :class:`ReconnectStormWindow`) replaces the cumulative lifetime counter in
    the storm comparison, so only reconnect CHURN inside the sliding window --
    the condition the breaker was built for -- trips it.  Callers that omit it
    keep the original cumulative semantics.
    """
    snap = snapshot if isinstance(snapshot, dict) else {}
    if snap.get("admission_inbox_commit_failed"):
        return "PAID_PROVIDER_ADMISSION_INBOX_FAILURE"
    if int(snap.get("max_active_streams") or 0) > 1:
        return "PAID_PROVIDER_STREAM_OVERLAP"
    if int(snap.get("handoff_artifact_errors") or 0) > 0:
        return "PAID_PROVIDER_HANDOFF_ARTIFACT_FAILURE"
    if snap.get("status") == STREAM_STATUS_AUTH_FAILED:
        return "PAID_PROVIDER_AUTH_FAILURE"
    reconnect_measure = (
        int(reconnects_in_window)
        if reconnects_in_window is not None
        else int(snap.get("reconnects") or 0))
    if reconnect_measure > int(max_reconnects):
        return "PAID_PROVIDER_RECONNECT_STORM"
    return None


# --------------------------------------------------------------------------- run


# --------------------------------------------------------------------- PHX2-E2E-006
# P1 scheduler capacity: one configuration source shared by the startup
# refusal formula, the runtime scheduler, and the paid transport.


def resolve_production_market_scheduling(args) -> Dict[str, Any]:
    """Resolve the effective P1 scheduling shape from session arguments.

    ``--birdeye-min-interval-seconds`` remains the explicit operator
    override for request-START spacing; when absent the production spacing
    comes from ``--market-provider-spacing-seconds`` (default 0.09 s —
    the value the operator's paid plan must be provisioned for; the
    credit-budget 429 tripwire stops a run observably if the plan
    disagrees).  Worker and in-flight counts derive from the configured
    provider concurrency unless explicitly overridden.
    """

    fields = production_p1_scheduler_fields()
    spacing = getattr(args, "birdeye_min_interval_seconds", None)
    if spacing is None:
        spacing = getattr(args, "market_provider_spacing_seconds", None)
    if spacing is None:
        spacing = fields["provider_min_interval_seconds"]
    concurrency = getattr(args, "market_provider_concurrency", None)
    if concurrency is None:
        concurrency = fields["worker_count"]
    concurrency = max(1, min(16, int(concurrency)))
    workers = getattr(args, "market_scheduler_workers", None)
    workers = concurrency if workers is None else max(1, min(16, int(workers)))
    max_inflight = getattr(args, "market_scheduler_max_inflight", None)
    max_inflight = (min(concurrency, workers) if max_inflight is None
                    else max(1, min(int(max_inflight), workers)))
    reserved = int(getattr(args, "market_p1_reserved_workers",
                           fields["p1_reserved_workers"]))
    reserved = max(0, min(reserved, workers - 1))
    return {
        "spacing_seconds": float(spacing),
        "concurrency": concurrency,
        "worker_count": workers,
        "max_inflight": max_inflight,
        "p1_reserved_workers": reserved,
        "p1_deadline_seconds": float(getattr(
            args, "market_p1_deadline_seconds", fields["p1_deadline_seconds"])),
        "healthy_response_budget_seconds": float(getattr(
            args, "market_healthy_response_budget_seconds",
            fields["healthy_response_budget_seconds"])),
        "dispatch_overhead_budget_seconds": float(getattr(
            args, "market_dispatch_overhead_budget_seconds",
            fields["dispatch_overhead_budget_seconds"])),
        "p1_max_attempts": int(getattr(
            args, "market_p1_max_attempts", fields["p1_max_attempts"])),
        "p1_request_timeout_seconds": float(getattr(
            args, "market_p1_request_timeout_seconds",
            fields["p1_request_timeout_seconds"])),
        "active_cap": max(1, min(4096, int(getattr(
            args, "max_watchlist_size", 128)))),
    }


def _transport_call_cap(args) -> Optional[int]:
    """Translate the market-request budget into a transport call ceiling.

    ``MARKET_REQUEST_CAP_UNBOUNDED`` (0) becomes ``None`` -- no ceiling -- and
    every other value passes through untouched.  The sentinel is deliberately
    NOT forwarded as a literal 0: the free-tier transport has always read 0 as
    "refuse every call", and overloading it would silently convert the
    RUN_FOREVER posture into a total market blackout.
    """

    configured = int(getattr(args, "max_market_requests_total", 0) or 0)
    return None if configured == MARKET_REQUEST_CAP_UNBOUNDED else configured


#: Largest batch the scheduler will form even if a provider declares more.
#: Bounds head-of-line delay for a priority candidate queued behind a
#: background batch: the batch is one physical request, so a large one would
#: otherwise hold a worker for its whole duration.
MAX_PAID_BATCH_SIZE = 50


def resolve_paid_batch_capability(transport) -> Dict[str, Any]:
    """Read the provider client's DECLARED batch capability.

    The scheduler already contains a complete, tested batch path (one physical
    request per batch, per-mint result mapping, no fabricated members).  What
    decides whether it is used is this declaration -- never an assumption about
    the provider's plan.  The committed paid client publishes
    ``price_batch_supported: False`` because the only price shape it implements
    is the single-address ``/defi/price`` GET; there is no multi-address
    endpoint in this repository to call.
    """

    reason = "PROVIDER_DECLARES_NO_BATCH_SUPPORT"
    supported = False
    size = 0
    try:
        stats = transport.stats()
    except Exception:
        return {"supported": False, "batch_size": 0,
                "reason": "PROVIDER_STATS_UNAVAILABLE"}
    if not isinstance(stats, Mapping):
        return {"supported": False, "batch_size": 0,
                "reason": "PROVIDER_STATS_UNAVAILABLE"}
    declared = stats.get("price_batch_supported")
    declared_size = stats.get("price_batch_size")
    if declared is True and isinstance(declared_size, int) \
            and not isinstance(declared_size, bool) and declared_size > 1:
        if not callable(getattr(transport, "fetch_price_plane_batch", None)):
            # Declared but not implemented: refuse rather than invent a URL.
            return {"supported": False, "batch_size": 0,
                    "reason": "PROVIDER_BATCH_FETCH_NOT_IMPLEMENTED"}
        supported = True
        size = min(int(declared_size), MAX_PAID_BATCH_SIZE)
        reason = "PROVIDER_DECLARES_BATCH_SUPPORT"
    return {"supported": supported, "batch_size": size, "reason": reason}


def build_production_market_scheduler_config(
    args, *, paid_batch_size: int = 0,
) -> MarketSchedulerConfig:
    """The ONE scheduler configuration the session runs and refuses on."""

    resolved = resolve_production_market_scheduling(args)

    def _numeric(name: str, fallback):
        value = getattr(args, name, None)
        return fallback if value is None else value

    return MarketSchedulerConfig(
        worker_count=resolved["worker_count"],
        max_inflight=resolved["max_inflight"],
        max_queue_size=int(_numeric("market_scheduler_queue_size", 256)),
        provider_request_budget=int(_numeric(
            "max_market_requests_total", 200000)),
        provider_min_interval_seconds=resolved["spacing_seconds"],
        paid_batch_size=max(0, min(MAX_PAID_BATCH_SIZE, int(paid_batch_size))),
        price_active_ttl_seconds=float(getattr(
            args, "market_price_active_ttl_seconds", 12.0)),
        price_pending_ttl_seconds=float(getattr(
            args, "market_price_pending_ttl_seconds", 30.0)),
        overview_active_ttl_seconds=float(getattr(
            args, "market_overview_active_ttl_seconds", 30.0)),
        overview_pending_ttl_seconds=float(getattr(
            args, "market_overview_pending_ttl_seconds", 90.0)),
        grpc_max_age_seconds=float(getattr(
            args, "market_grpc_max_age_seconds", 15.0)),
        background_starvation_seconds=float(getattr(
            args, "market_background_starvation_seconds", 120.0)),
        p1_deadline_seconds=resolved["p1_deadline_seconds"],
        max_active_candidates=resolved["active_cap"],
        healthy_response_budget_seconds=(
            resolved["healthy_response_budget_seconds"]),
        dispatch_overhead_budget_seconds=(
            resolved["dispatch_overhead_budget_seconds"]),
        p1_max_attempts=resolved["p1_max_attempts"],
        p1_request_timeout_seconds=resolved["p1_request_timeout_seconds"],
        p1_reserved_workers=resolved["p1_reserved_workers"],
        # Planning used to happen ONCE per producer watch tick.  A tick is
        # ~46 s in production, so a 12 s price TTL was unreachable by
        # construction and a tier-active candidate spent ~38 s of every
        # ~50 s guaranteed stale.  The scheduler now owns a bounded sweep of
        # its own; ``plan()`` stays idempotent and the tick still calls it.
        planner_interval_seconds=float(getattr(
            args, "market_planner_interval_seconds", 2.0)),
    )


def evaluate_session_p1_capacity(args) -> Dict[str, Any]:
    """Pure startup capacity verdict for the session's own configuration.

    Runs BEFORE any transport, channel, stub, or provider object is
    constructed.  A refusal carries only safe numeric/configuration
    evidence (no endpoint, no credential, no header)."""

    config = build_production_market_scheduler_config(args)
    return evaluate_p1_capacity(
        config, active_candidates=config.max_active_candidates)


def drain_provider_handoff_completely(discovery, *, chunk_size: int = 10,
                                      max_chunks: int = 1024) -> List[Dict[str, Any]]:
    """Drain the bounded provider handoff fully in bounded chunks.

    PHX2-E2E-006: a 128-candidate burst previously waited thirteen
    45-second watch ticks behind the 10-per-tick drain limit.  The chunks
    stay bounded (dedupe/artifact semantics per chunk are unchanged) but
    run back-to-back with no sleep between them.  ``max_chunks`` is a
    pure runaway backstop far above the bounded queue's capacity.
    """

    drained: List[Dict[str, Any]] = []
    for _pass in range(max(1, int(max_chunks))):
        chunk = discovery.drain(max_candidates=max(1, int(chunk_size)))
        if not chunk:
            break
        drained.extend(chunk)
    return drained


class P1TickWaiter:
    """Wakeable inter-tick wait with a bounded minimum gap.

    The watch loop's maintenance interval survives as the MAXIMUM idle
    wait; a P1-relevant scheduler event wakes the loop immediately.  The
    minimum gap bounds the tick rate under event storms.  No busy spin:
    every path blocks in ``Event.wait``/``sleep``.
    """

    def __init__(self, *, min_gap_seconds: float = 1.0,
                 monotonic_fn: Callable[[], float] = time.monotonic,
                 sleep_fn: Callable[[float], None] = time.sleep) -> None:
        self._event = threading.Event()
        self._min_gap = max(0.0, float(min_gap_seconds))
        self._mono = monotonic_fn
        self._sleep = sleep_fn
        self._last_return: Optional[float] = None
        self.wakes = 0
        self.waits = 0

    def wake(self) -> None:
        self.wakes += 1
        self._event.set()

    def __call__(self, timeout_seconds: float) -> None:
        self.waits += 1
        timeout = max(0.0, float(timeout_seconds))
        if self._last_return is not None and self._min_gap > 0:
            gap_left = self._min_gap - (float(self._mono()) - self._last_return)
            if gap_left > 0:
                self._sleep(min(gap_left, timeout))
                timeout = max(0.0, timeout - gap_left)
        self._event.wait(timeout)
        self._event.clear()
        self._last_return = float(self._mono())


def _bounds_from_args(args) -> ProductionBounds:
    return ProductionBounds(
        alert_policy=normalize_alert_policy(
            getattr(args, "alert_policy", None)),
        recheck_interval_seconds=float(args.recheck_interval_seconds),
        max_candidate_age_seconds=int(args.max_candidate_age_seconds),
        max_rechecks_per_candidate=int(args.max_rechecks_per_candidate),
        max_runtime_seconds=float(args.max_runtime_seconds),
        max_watchlist_size=int(args.max_watchlist_size),
        queue_pressure_max=int(args.queue_pressure_max),
        max_market_calls_total=int(args.max_market_calls_total),
        reseed_interval_seconds=float(args.reseed_interval_seconds),
        max_reseeds=int(args.max_reseeds),
        min_seconds_between_sends=float(args.min_seconds_between_sends),
        max_consecutive_source_failures=int(args.max_consecutive_source_failures),
        max_consecutive_throttles=int(args.max_consecutive_throttles),
        max_total_ticks=int(args.max_total_ticks),
    )


def _bounds_with_provider_handoff_cadence(
    bounds: ProductionBounds, provider_mode: str
) -> ProductionBounds:
    """Poll a continuously owned paid queue at every production watch tick."""
    if provider_mode == PROVIDER_MODE_FREE_TIER:
        return bounds
    return replace(
        bounds,
        reseed_interval_seconds=min(
            bounds.reseed_interval_seconds, bounds.recheck_interval_seconds),
    )


def _strict_axiom_config() -> "axiomgate.AxiomFeeGateConfig":
    # The runner refuses lax configs; Axiom stays a DISABLED (Null-source) observe-only telemetry
    # layer here: no RPC is made, no candidate is ever blocked by it.
    return axiomgate.AxiomFeeGateConfig(
        require_success=True, require_fee_metrics=True, require_recent_tx=True,
        require_candidate_mint_association=True, max_total_fee_lamports=None,
    )


def _build_producer_summary(*, result: Dict[str, Any], mode: str, out_dir: str,
                            ledger_path: str, baseline_before: Optional[str],
                            baseline_after: Optional[str], transport_stats: Dict[str, Any],
                            tail_summary: Dict[str, Any], error_count: int,
                            discord_enabled: bool, credit_budget: Dict[str, Any],
                            final: bool,
                            telegram_enabled: bool = False,
                            delivery_transport: str = "NONE",
                            non_pump_guard_dropped_total: int = 0,
                            discovery_mode: str = "WS",
                            market_freshness: Optional[Dict[str, Any]] = None,
                            profile: Optional[str] = None,
                            risk_summary: Optional[Dict[str, Any]] = None,
                            risk_discord_block: Optional[Dict[str, Any]] = None,
                            provider_telemetry: Optional[Dict[str, Any]] = None,
                            market_readiness: Optional[Dict[str, Any]] = None,
                            checkpoint_status: Optional[Dict[str, Any]] = None,
                            authoritative_supply: Optional[Dict[str, Any]] = None,
                            phx1_structural_policy: str = PHX1_STRUCTURAL_POLICY_ENFORCE,
                            alert_policy: str = ALERT_POLICY_LEGACY) -> Dict[str, Any]:
    return {
        "kind": "FREE_TIER_PRODUCER_SUMMARY",
        "mode": mode,
        "production_mode": dict(provider_telemetry or {}).get("production_mode"),
        "historical_completeness_required": dict(
            provider_telemetry or {}).get("historical_completeness_required"),
        "historical_rpc_backfill_enabled": dict(
            provider_telemetry or {}).get("historical_rpc_backfill_enabled"),
        "historical_recovery_status": dict(
            provider_telemetry or {}).get("historical_recovery_status"),
        "dexscreener_restart_backfill_enabled": dict(
            provider_telemetry or {}).get("dexscreener_restart_backfill_enabled"),
        "phx1_structural_policy": phx1_structural_policy,
        "alert_policy": alert_policy,
        "discovery_mode": discovery_mode,
        "profile": profile,
        "raw_ws_cap_note": RAW_WS_CAP_NOTE,
        "final": bool(final),
        "updated_at_utc": _utc_now_iso(),
        "outcome": result.get("outcome"),
        "stop_reason": result.get("stop_reason"),
        "budget_stop": bool(result.get("budget_stop", False)),
        "ticks": result.get("ticks", 0),
        "would_ping_count": result.get("sends", 0),
        "non_pump_guard_dropped_total": int(non_pump_guard_dropped_total),
        "reseeds": result.get("reseeds", 0),
        "market_calls": result.get("market_calls", 0),
        "ledger_path": ledger_path,
        "ledger_delta_total": result.get("total_ledger_delta"),
        "reserve_count": result.get("reserve_count"),
        "baseline_before": baseline_before,
        "baseline_after": baseline_after,
        "watchlist_summary": result.get("watchlist_summary", {}),
        "migration_activation": {
            "live_activation_multiplier": format(
                MIGRATION_ACTIVATION_MULTIPLIER, "f"),
            "dex_backfill_activation_multiplier": format(
                BACKFILL_ACTIVATION_MULTIPLIER, "f"),
            "baseline_priority": [
                "GRPC_EVENT", "DEXSCREENER_SOL_USD_X_410_INFERRED",
                "PAID_MARKET_PRIMARY_FALLBACK"],
            "counts": result.get("watchlist_summary", {}),
        },
        "market_transport_stats": transport_stats,
        "pricing_tail": tail_summary,
        "market_freshness": dict(market_freshness or {}),
        "market_scheduler": dict(result.get("market_scheduler") or {}),
        "risk_summary": dict(risk_summary or {}),
        "risk_discord_block": dict(risk_discord_block or {}),
        "provider_telemetry": dict(provider_telemetry or {}),
        "market_readiness": dict(market_readiness or {}),
        "authoritative_supply": dict(authoritative_supply or {}),
        # PHX2-E2E-005: authenticated checkpoint restore observability. A
        # quarantined checkpoint is a refused run, never an empty healthy one.
        "checkpoint": dict(checkpoint_status or {}),
        "error_count": int(error_count),
        "credit_budget": credit_budget,
        "delivery_transport": delivery_transport,
        "telegram_enabled": bool(telegram_enabled),
        "telegram_token_configured": bool(telegram_enabled),
        "telegram_chat_configured": bool(telegram_enabled),
        "private_discord_enabled": bool(discord_enabled),
        "discord_enabled": bool(discord_enabled),
        "discord_attempts": 0 if telegram_enabled else None,
        "real_send_performed": bool(
            result.get("sent_ok_count", 0) > 0
            and (telegram_enabled or discord_enabled)),
        "wallet_signing_or_trading": False,
        "public_or_subscriber_routing": False,
        "out_dir": out_dir,
    }


def _gap_recovery_config_from_args(args) -> RpcGapRecoveryConfig:
    """The explicit recovery configuration, arguments over defaults, no clamps."""

    defaults = RpcGapRecoveryConfig()

    def _pick(name: str, default_value):
        value = getattr(args, name, None)
        return default_value if value is None else value

    return RpcGapRecoveryConfig(
        mode=(getattr(args, "grpc_gap_recovery", None)
              or defaults.mode),
        authoritative_commitment=getattr(
            args, "rpc_recovery_commitment", None),
        max_gap_slots=_pick(
            "rpc_recovery_max_gap_slots", defaults.max_gap_slots),
        max_produced_blocks=_pick(
            "rpc_recovery_max_produced_blocks", defaults.max_produced_blocks),
        max_transactions=_pick(
            "rpc_recovery_max_transactions", defaults.max_transactions),
        max_backfill_runtime_seconds=_pick(
            "rpc_recovery_max_runtime_seconds",
            defaults.max_backfill_runtime_seconds),
        max_rpc_requests=_pick(
            "rpc_recovery_max_requests", defaults.max_rpc_requests),
        max_retries_per_request=_pick(
            "rpc_recovery_max_retries_per_request",
            defaults.max_retries_per_request),
        max_consecutive_rpc_failures=_pick(
            "rpc_recovery_max_consecutive_failures",
            defaults.max_consecutive_rpc_failures),
        max_http_429_responses=_pick(
            "rpc_recovery_max_429", defaults.max_http_429_responses),
        rpc_request_spacing_seconds=_pick(
            "rpc_recovery_request_spacing_seconds",
            defaults.rpc_request_spacing_seconds),
        rpc_concurrency=_pick(
            "rpc_recovery_concurrency", defaults.rpc_concurrency),
        max_quarantine_events=_pick(
            "rpc_recovery_max_quarantine_events",
            defaults.max_quarantine_events),
        max_quarantine_bytes=_pick(
            "rpc_recovery_max_quarantine_bytes",
            defaults.max_quarantine_bytes),
        max_quarantine_age_seconds=_pick(
            "rpc_recovery_max_quarantine_age_seconds",
            defaults.max_quarantine_age_seconds),
        max_commitment_wait_seconds=_pick(
            "rpc_recovery_max_commitment_wait_seconds",
            defaults.max_commitment_wait_seconds),
        max_overlap_wait_seconds=_pick(
            "rpc_recovery_max_overlap_wait_seconds",
            defaults.max_overlap_wait_seconds),
        checkpoint_every_blocks=_pick(
            "rpc_recovery_checkpoint_every_blocks",
            defaults.checkpoint_every_blocks),
        max_backfill_resume_attempts=_pick(
            "rpc_recovery_max_resume_attempts",
            defaults.max_backfill_resume_attempts),
        # Confirmed-RPC application throughput. The dataclass default is 1
        # (the serial reference, which every offline fixture keeps); the
        # PRODUCTION default is CPU-derived, because a serial recovery was
        # measured applying ~1.6 blocks/second against ~2.5 blocks/second of
        # chain growth and therefore never converges.
        rpc_apply_processes=_pick(
            "rpc_apply_processes", default_apply_processes()),
        rpc_apply_queue_bound=_pick(
            "rpc_apply_queue_bound", defaults.rpc_apply_queue_bound),
        rpc_apply_batch_size=_pick(
            "rpc_apply_batch_size", defaults.rpc_apply_batch_size),
        rpc_worker_timeout_seconds=_pick(
            "rpc_worker_timeout_seconds",
            defaults.rpc_worker_timeout_seconds),
    )


def _build_activation_inputs(provider: Any) -> ActivationInputs:
    """Read the acceptance gate's inputs from PROVEN runtime state.

    Every field is taken from the authenticated recovery record or the cursor's
    source-health latch. Anything unreadable resolves to the conservative
    value, which keeps the run in PRE_SOAK_RECOVERY with delivery blocked.
    """

    snapshot: Dict[str, Any] = {}
    try:
        snapshot = provider.snapshot() if provider is not None else {}
    except Exception:
        snapshot = {}
    recovery = snapshot.get("gap_recovery")
    recovery = recovery if isinstance(recovery, dict) else {}
    try:
        source_healthy = bool(provider.authorizes_send()[0]) \
            if provider is not None else False
    except Exception:
        source_healthy = False
    state = recovery.get("recovery_state")
    return ActivationInputs(
        # No episode ever existed for this owner => nothing to wait for.
        recovery_required=bool(recovery) and state not in (
            None, RECOVERY_STATE_IDLE),
        recovery_episode_open=bool(recovery.get("episode_open")),
        recovery_terminal=(
            state == RECOVERY_STATE_RECOVERY_TERMINAL
            or bool(recovery.get("recovery_store_quarantined"))),
        overlap_proven=(recovery.get("overlap_proof_state") == OVERLAP_PROVEN),
        produced_blocks_remaining=int(
            recovery.get("produced_blocks_remaining") or 0),
        source_healthy=source_healthy,
    )


def run_producer(args) -> int:
    paper_state_path = getattr(args, "paper_state_file", None)
    if getattr(args, "paper_coverage_required", False) and paper_state_path is None:
        print("[refused] PAPER_STATE_FEEDBACK_REQUIRED")
        return 2
    if paper_state_path is not None:
        path = Path(paper_state_path)
        if (path.name != "paper_state.json" or path.is_symlink()
                or "phoenix_bot" in [part.lower() for part in path.resolve().parts]):
            print("[refused] PAPER_STATE_FEEDBACK_PATH_REFUSED")
            return 2
    # ---- indefinite-runtime contract (Stage 10) -----------------------------
    # A supervised 24/7 service needs a producer with NO clock boundary, and it
    # must be stated explicitly rather than faked with a huge timeout. Whether
    # the operator passed --max-runtime-seconds has to be read BEFORE the
    # profile overlay below fills it in, otherwise the base default (7200) is
    # indistinguishable from an explicit choice.
    #
    # This is decided FIRST, on argument values alone: a contradictory runtime
    # boundary is refused before the environment file is even opened, so no
    # secret is loaded into the process for a run that was never going to start.
    run_forever = bool(getattr(args, "run_forever", False))
    explicit_max_runtime = getattr(args, "max_runtime_seconds", None) is not None
    if run_forever:
        conflicts: List[str] = []
        if explicit_max_runtime:
            conflicts.append("MAX_RUNTIME_SECONDS_ALSO_GIVEN")
        if float(getattr(args, "active_soak_seconds", 0.0) or 0.0) > 0.0:
            conflicts.append("ACTIVE_SOAK_SECONDS_ALSO_GIVEN")
        if int(getattr(args, "max_total_ticks", 0) or 0) > 0:
            conflicts.append("MAX_TOTAL_TICKS_ALSO_GIVEN")
        if conflicts:
            print("[refused] RUN_FOREVER_CONFLICT: "
                  f"{', '.join(conflicts)} — --run-forever is the one and only "
                  "runtime-boundary statement; it may not be combined with a "
                  "second, contradictory boundary.")
            return 2

    launcher_source_mode = os.environ.get("PHX2_MIGRATION_SOURCE_MODE")
    explicit_source_mode = getattr(args, "migration_source_mode", None)
    effective_source_mode = launcher_source_mode or explicit_source_mode
    if not effective_source_mode:
        print("[refused] MIGRATION_SOURCE_MODE_REFUSED: "
              "migration source mode is required; no fallback is permitted")
        return 2
    n = _load_env_file_for_source_mode(
        args.env,
        str(effective_source_mode),
    )
    os.environ["PHX2_MIGRATION_SOURCE_MODE"] = str(
        launcher_source_mode or explicit_source_mode
    )
    scrubbed = (
        sess.scrub_unrelated_env()
        + _scrub_disabled_source_environment(str(effective_source_mode))
    )
    print(f"env: loaded {n} vars; scrubbed {scrubbed} unrelated; values NEVER printed.")

    # ---- effective caps/runtime: explicit flag > profile > base default ----
    try:
        eff = resolve_effective_settings(args)
    except ValueError as exc:
        print(f"[refused] {exc}")
        return 2
    args = argparse.Namespace(**{**vars(args), **{k: v for k, v in eff.items()
                                                  if k not in ("profile", "discovery_mode")}})
    if run_forever:
        # Applied AFTER the overlay so no profile can reintroduce a clock.
        args.max_runtime_seconds = UNBOUNDED_RUNTIME_SECONDS
        print("[runtime] --run-forever: max_runtime_seconds=UNBOUNDED "
              "(cooperative stop file / operator interrupt / safety breakers "
              "remain the only ways this run ends)")
        # Checked HERE, after the profile overlay, because the cap that
        # actually binds is the resolved one -- the 2026-08-02 launcher stated
        # no market cap at all and silently inherited the bounded base default
        # of 5,000, which a pre-overlay check could not have seen.  A run with
        # no clock boundary must not carry a non-refilling lifetime spend
        # boundary; the market plane went permanently blind 22 minutes in.
        market_refusal = run_forever_market_budget_refusal(
            run_forever=True,
            max_market_requests_total=int(args.max_market_requests_total))
        if market_refusal is not None:
            print(f"[refused] {market_refusal}: "
                  f"--run-forever with a finite lifetime market-request cap "
                  f"({int(args.max_market_requests_total)}) is invalid — an "
                  f"indefinite deployment must state "
                  f"--max-market-requests-total 0 (UNBOUNDED). A bounded "
                  f"one-shot or test run keeps its finite cap.")
            return 2
        print("[runtime] --run-forever: market_budget_mode="
              f"{market_budget_mode(int(args.max_market_requests_total))} "
              "(physical provider requests are counted and reported, never "
              "capped; the market plane cannot be starved by budget)")
    discovery_mode = eff["discovery_mode"]
    try:
        phx1_structural_policy = normalize_phx1_structural_policy(
            getattr(args, "phx1_structural_policy", None))
        alert_policy = normalize_alert_policy(
            getattr(args, "alert_policy", None))
        provider_mode = normalize_provider_mode(getattr(args, "provider_mode", None))
    except ValueError as exc:
        print(f"[refused] {exc}")
        return 2
    # Bind the process-wide policy BEFORE any watchlist, checkpoint restore, or
    # readiness state is built: the activation-multiplier contract and the
    # adaptive cadence both read it, and a mid-run change would mean two
    # candidates in one run were judged by different rules.
    bind_alert_policy(alert_policy)
    if is_phx1_parity(alert_policy):
        # PHX1_PARITY makes the fee lifecycle a shadow annotation.  The
        # structural router is the mechanism that carries an already-computed
        # fee/structure hard block forward as a visible manual-review warning,
        # so parity implies (and states) SHADOW rather than silently depending
        # on the operator also passing --phx1-structural-policy shadow.
        if phx1_structural_policy != PHX1_STRUCTURAL_POLICY_SHADOW:
            print("[policy] PHX1_PARITY implies phx1_structural_policy=SHADOW "
                  f"(was {phx1_structural_policy})")
        phx1_structural_policy = PHX1_STRUCTURAL_POLICY_SHADOW
        # The six-hour watch applies only when the operator left the candidate
        # age at the committed default; an explicit value always wins.
        if int(getattr(args, "max_candidate_age_seconds", 0)) == 3600:
            args.max_candidate_age_seconds = watch_ttl_seconds(alert_policy)
    alert_policy_counters = Phx1ParityCounters(policy=alert_policy)
    print(f"alert policy: {alert_policy} "
          f"watch_ttl_seconds={int(args.max_candidate_age_seconds)} "
          f"phx1_structural_policy={phx1_structural_policy}")
    paid_mode = provider_mode != PROVIDER_MODE_FREE_TIER
    try:
        source_selection = load_source_selection(
            explicit_mode=getattr(args, "migration_source_mode", None)
        )
        source_selection.require_launcher_ready()
    except ValueError as exc:
        print(f"[refused] MIGRATION_SOURCE_MODE_REFUSED: {exc}")
        return 2
    helius_primary = bool(source_selection.helius_production_authority)
    helius_http_recovery_enabled = bool(
        getattr(args, "enable_helius_http_recovery", False)
    )
    source_runtime_plan = build_production_source_runtime_plan(
        source_selection,
        http_recovery_enabled=helius_http_recovery_enabled,
    )
    helius_source_config = None
    if helius_primary or source_selection.helius_shadow_enabled:
        try:
            helius_source_config = load_helius_source_config(
                env_path=Path(args.env)
            )
        except ValueError:
            helius_source_config = None
    source_contract = validate_production_source_contract(
        selection=source_selection,
        helius_configured=helius_source_config is not None,
        http_recovery_enabled=helius_http_recovery_enabled,
        subscription_request=approved_tight_subscription_request(1),
        send_authority_count=1,
        chainstack_candidate_authority=False,
    )
    if not source_contract.allowed:
        print("[refused] MIGRATION_SOURCE_CONTRACT_REFUSED: "
              + ", ".join(source_contract.refusals))
        return 2
    print("migration source: "
          f"mode={source_selection.mode} "
          f"primary={source_runtime_plan.primary_source} "
          f"recovery={source_runtime_plan.recovery_authority} "
          f"shadow={source_runtime_plan.shadow_source} "
          f"chainstack_configured_for_runtime="
          f"{source_runtime_plan.resolve_chainstack_credentials}")

    # ---- ARMED PRODUCTION REQUIREMENT (evaluated BEFORE the mode branch) ----
    # --require-production-grpc used to be checked only inside `if paid_mode:`,
    # the very condition it exists to require. Because --provider-mode defaults
    # to free_tier, an armed launcher that dropped one token got no refusal, no
    # cursor, no contract, an open outbound health gate and legacy websocket
    # discovery while staying fully send-capable. Deciding it here -- on
    # argument values alone, before any store, factory, channel or stub exists
    # -- makes that state unreachable. The object-dependent half of the
    # contract still runs below, once there is something to inspect.
    require_production_grpc = bool(
        getattr(args, "require_production_grpc", False))
    precondition = evaluate_production_mode_precondition(
        require_production_grpc=(
            require_production_grpc
            and source_selection.chainstack_production_authority
        ),
        provider_mode=provider_mode,
        paid_provider_modes=(PROVIDER_MODE_PAID_PRIMARY,
                             PROVIDER_MODE_PAID_WITH_FALLBACK),
        cursor_state_dir=getattr(args, "cursor_state_dir", None),
        out_dir=args.out_dir,
        discovery_mode=discovery_mode,
    )
    if not precondition.allowed:
        # Closed-set reasons only: never a path, endpoint or credential.
        print(f"[refused] PRODUCTION_GRPC_CONTRACT_REFUSED: "
              f"{', '.join(precondition.refusals)}")
        return 2

    # ---- bounded RPC gap-backfill recovery configuration (fail-closed) ----
    # The recovery mode must be EXPLICIT under the armed contract: a
    # production launcher may not silently inherit an optimistic default, and
    # no mode exists that converts a gap into a live-head bootstrap. Every
    # bound is validated here, before any store or network object exists;
    # invalid values refuse startup instead of being clamped.
    gap_recovery_mode = getattr(args, "grpc_gap_recovery", None)
    gap_recovery_config = _gap_recovery_config_from_args(args)
    gap_verdict = evaluate_armed_gap_recovery(
        require_production_grpc=require_production_grpc,
        mode_argument=gap_recovery_mode,
        config=gap_recovery_config,
    )
    if not gap_verdict["allowed"]:
        print(f"[refused] RPC_GAP_RECOVERY_CONFIG_REFUSED: "
              f"{', '.join(gap_verdict['refusals'])}")
        return 2
    rpc_recovery_enabled = (
        gap_recovery_config.mode == GAP_RECOVERY_MODE_RPC_BACKFILL)
    live_epoch_mode = (
        gap_recovery_config.mode == GAP_RECOVERY_MODE_LIVE_EPOCH)
    dex_backfill_enabled = bool(
        getattr(args, "enable_dexscreener_restart_backfill", False))
    production_mode_refusals: List[str] = []
    if live_epoch_mode and not paid_mode:
        production_mode_refusals.append("LIVE_EPOCH_REQUIRES_PAID_GRPC")
    if dex_backfill_enabled and not live_epoch_mode:
        production_mode_refusals.append("DEX_BACKFILL_REQUIRES_LIVE_EPOCH")
    if require_production_grpc and not live_epoch_mode:
        production_mode_refusals.append("PRODUCTION_REQUIRES_LIVE_EPOCH")
    if (
        require_production_grpc
        and (source_selection.chainstack_production_authority or helius_primary)
        and not dex_backfill_enabled
    ):
        # Bounded six-hour DEX candidate recovery (startup + periodic safety
        # net) is part of the armed production contract under BOTH candidate
        # authorities.  It is candidate recovery, never migration-source
        # authority: Helius stays the sole live source and HELIUS_HTTP stays
        # the sole live-source gap-recovery path.
        production_mode_refusals.append("PRODUCTION_REQUIRES_DEX_RESTART_BACKFILL")
    if helius_primary and rpc_recovery_enabled:
        production_mode_refusals.append(
            "HELIUS_PRIMARY_LEGACY_RPC_RECOVERY_FORBIDDEN"
        )
    if helius_primary and provider_mode == PROVIDER_MODE_PAID_WITH_FALLBACK:
        production_mode_refusals.append(
            "HELIUS_PRIMARY_POLLING_FALLBACK_AUTHORITY_FORBIDDEN"
        )
    if production_mode_refusals:
        print("[refused] LIVE_EPOCH_PRODUCTION_CONFIG_REFUSED: "
              + ", ".join(production_mode_refusals))
        return 2
    recovery_env_projection = project_rpc_recovery_env_safe()
    print("production history policy: "
          f"production_mode={LIVE_EPOCH_PRODUCTION_MODE if live_epoch_mode else 'DEVELOPMENT_LEGACY_MODE'} "
          f"historical_completeness_required={not live_epoch_mode} "
          f"historical_rpc_backfill_enabled={rpc_recovery_enabled} "
          f"dexscreener_restart_backfill_enabled={dex_backfill_enabled}")
    print("grpc gap recovery: "
          f"mode={gap_recovery_config.mode} "
          f"commitment={gap_recovery_config.authoritative_commitment} "
          f"endpoint={recovery_env_projection['rpc_recovery_endpoint']} "
          "(value NEVER printed)")
    if rpc_recovery_enabled:
        bounds = gap_recovery_config.snapshot()
        print("rpc recovery bounds: " + " ".join(
            f"{key.replace('rpc_recovery_', '')}={bounds[key]}"
            for key in sorted(bounds)
            if key.startswith("rpc_recovery_max_")
            or key in ("rpc_recovery_request_spacing_seconds",
                       "rpc_recovery_concurrency")))
        print("rpc apply pipeline: " + " ".join(
            f"{key}={bounds[key]}" for key in (
                "rpc_apply_processes", "rpc_apply_queue_bound",
                "rpc_apply_batch_size", "rpc_worker_timeout_seconds")))

    discovery_mode_display = provider_mode if paid_mode else discovery_mode.upper()
    print(f"profile: {eff['profile'] or 'none (base defaults)'} "
          f"provider_mode={provider_mode} discovery_mode={discovery_mode_display}")
    print(f"WARNING: {RAW_WS_CAP_NOTE} — the raw WS cap is an internal firehose safety bound "
          f"(observed ~40k raw msgs per 90s window).")

    discord_enabled = bool(args.enable_private_discord)
    telegram_enabled = bool(getattr(args, "enable_telegram", False))
    if discord_enabled and telegram_enabled:
        print("[refused-arm] DUAL_TRANSPORT_FORBIDDEN")
        return 2
    mode = _producer_mode_label(provider_mode, discord_enabled, telegram_enabled)
    delivery_enabled = bool(discord_enabled or telegram_enabled)
    delivery_transport = (
        "TELEGRAM" if telegram_enabled else
        "DISCORD" if discord_enabled else "NONE")
    telegram_config: Optional[TelegramConfig] = None

    # ---- path isolation (old ledgers/trees can never be touched) ----
    for label, p in (("ledger", args.ledger_path), ("out-dir", args.out_dir)):
        if path_is_forbidden(p):
            print(f"[refused] {label} path is inside a protected historical tree: {p}")
            return 2
    stop_file = Path(args.stop_file) if args.stop_file else None
    if stop_file is not None and stop_file.exists():
        print("[refused] cooperative stop file already exists; no provider started.")
        return 2

    # ---- arm gate / env hardening ----
    if telegram_enabled:
        refusal, telegram_config = verify_telegram_arm(args)
        if refusal is not None or telegram_config is None:
            print(f"[refused-arm] {refusal or 'TELEGRAM_CONFIGURATION_INVALID'} — "
                  "Telegram NOT enabled, nothing sent.")
            return 2
        # A legacy webhook can remain in the env file for rollback, but it is
        # removed from the production child before any transport construction.
        os.environ.pop(ENV_WEBHOOK, None)
        print("[armed] Telegram ENABLED transport=TELEGRAM chat=PHOENIX_CHANNEL")
        print("telegram_enabled=true telegram_token_configured=true "
              "telegram_chat_configured=true discord_enabled=false")
    elif discord_enabled:
        refusal = verify_discord_arm(args)
        if refusal is not None:
            print(f"[refused-arm] {refusal} — private discord NOT enabled, nothing sent.")
            return 2
        print("[armed] private discord ENABLED (private operator route only).")
    else:
        dropped = harden_no_send_env(
            allow_birdeye_fallback=bool(args.allow_birdeye_fallback),
            allow_paid_provider=paid_mode)
        print(f"no-send mode: {dropped} unused/send-capable env var(s) dropped from this "
              f"process; transport records would-pings only (nothing send-capable is "
              f"constructed).")

    key = os.environ.get("HELIUS_API_KEY")
    url = os.environ.get("HELIUS_RPC_URL")
    helius_required = provider_mode != PROVIDER_MODE_PAID_PRIMARY
    if helius_required and not (key and key.strip() and url and url.strip()):
        print("[refused] Helius env missing (HELIUS_API_KEY / HELIUS_RPC_URL). "
              "PRESENT/MISSING only; values never printed.")
        return 2

    # ---- per-run cumulative credit/rate budget (strict; ends the run at a tick boundary) ----
    budget = FreeTierCreditBudget(
        FreeTierCreditBudgetCaps(
            max_sends_per_run=int(args.max_sends_per_run),
            max_raw_ws_notifications_total=int(args.max_raw_ws_notifications_total),
            max_seed_windows=int(args.max_seed_windows),
            max_candidates_total=int(args.max_candidates_total),
            max_gettransaction_total=int(args.max_gettransaction_total),
            max_market_requests_total=int(args.max_market_requests_total),
            max_429_total=int(args.max_429_total),
            max_consecutive_ws_errors=int(args.max_consecutive_ws_errors),
            max_rpc_errors_total=int(args.max_rpc_errors_total),
            max_polls_total=int(args.max_polls_total),
        ),
        delivery_enabled=delivery_enabled,
        # HYBRID: raw-WS exhaustion downgrades to polling-only instead of ending the run.
        ws_exhaustion_latches=(discovery_mode != DISCOVERY_MODE_HYBRID))
    sends_cap_display = (
        "UNBOUNDED (managed 24/7; per-send gates + cooldown still apply)"
        if budget.caps.sends_unbounded else str(budget.caps.max_sends_per_run))
    print(f"credit budget: sends<={sends_cap_display} "
          f"raw_ws_notifications<={budget.caps.max_raw_ws_notifications_total} "
          f"(raw WS messages, NOT Helius credits) "
          f"seed_windows<={budget.caps.max_seed_windows} "
          f"candidates<={budget.caps.max_candidates_total} "
          f"gettransaction<={budget.caps.max_gettransaction_total} "
          f"market_requests<={budget.caps.max_market_requests_total} "
          f"polls<={budget.caps.max_polls_total} "
          f"429<{budget.caps.max_429_total + 1} "
          f"consecutive_ws_errors<{budget.caps.max_consecutive_ws_errors + 1} "
          f"rpc_errors<={budget.caps.max_rpc_errors_total}")

    out_dir = str(args.out_dir)
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    # One write-through ATH owner for the existing transaction stream, market
    # sidecar, send artifacts, pricing tail, paper monitor, and dashboard.
    # The AUTHENTICATED checkpoint pair anchors in the durable cursor state
    # dir when one is configured, so canonical ATH / achieved-tier evidence
    # survives watchdog-driven process restarts (out_dir rotates per run and
    # previously reset the ATH store to zero on every restart, producing
    # regressive duplicate alerts).  The public ``ath_state.json`` mirror
    # stays in out_dir for the dashboard / paper tooling.
    durable_ath_dir = getattr(args, "cursor_state_dir", None)
    if durable_ath_dir:
        Path(str(durable_ath_dir)).mkdir(parents=True, exist_ok=True)
    ath_store = CentralAthStateStore(
        out_dir,
        checkpoint_dir=str(durable_ath_dir) if durable_ath_dir else None)
    ath_checkpoint = ath_store.checkpoint_summary()
    print("ath checkpoint: "
          f"{ath_checkpoint.get('checkpoint_status')} "
          f"(schema={ath_checkpoint.get('checkpoint_schema_version')} "
          f"generation={ath_checkpoint.get('checkpoint_generation')} "
          f"records={ath_checkpoint.get('checkpoint_records_validated')})")
    if ath_store.checkpoint_quarantined:
        # PHX2-E2E-005: an existing authoritative ATH checkpoint failed
        # authentication. Never start normal alerting from untrusted state and
        # never overwrite the corrupt evidence with an empty fresh start.
        artifacts.write_json(out_dir, CHECKPOINT_QUARANTINE_BASENAME, {
            "kind": "PHX2_CHECKPOINT_QUARANTINE",
            "quarantined_checkpoint": "CENTRAL_ATH",
            "observed_at_utc": _utc_now_iso(),
            "ath": ath_checkpoint,
        })
        print("[refused] CHECKPOINT_QUARANTINED:CENTRAL_ATH:"
              f"{ath_checkpoint.get('checkpoint_quarantine_reason')}")
        return 2
    ledger_path = Path(args.ledger_path)
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    if not ledger_path.exists():
        ledger_path.write_text("", encoding="utf-8")   # fresh, empty free-tier ledger
        print(f"created fresh free-tier dedupe ledger: {ledger_path}")

    errors = ErrorLedger(out_dir)
    before = ledgerlib.compute_baseline(str(ledger_path))
    baseline_before = before.as_token() if before else "0-lines"

    # ---- lightweight scam/bundle risk layer (2026-07-11; ENFORCING dispatch gate 2026-07-12) ----
    # Consumes observations the run already pays for (tail fetches, sidecar market context,
    # polling discovery stats) — zero extra HTTP/RPC/WS spend, NO holder scan exists. The label
    # (a) annotates artifacts + the ping body (warn-only display line) and drives the PAPER
    # engine's high-risk skip AND (b) ENFORCES the production dispatch gate: RISK_HIGH is
    # blocked before reserve/transport/cap; in the explicit single-stream PHX1-parity mode,
    # RISK_MEDIUM remains visible but proceeds with LOW / UNKNOWN through every other gate.
    risk_engine = FreeTierRiskEngine(now_epoch_fn=time.time)
    discord_block_ledger = DiscordBlockLedger()
    discord_blocks_path = Path(out_dir) / DISCORD_BLOCKS_BASENAME
    shadow_candidates_path = Path(out_dir) / PHX1_SHADOW_CANDIDATES_BASENAME
    print(f"risk layer: ACTIVE (PHX1-parity single-stream dispatch: RISK_HIGH blocked; "
          f"RISK_MEDIUM warning-only pre-reserve; warn-only display line; free-tier signals only; "
          f"holder/bundle-wallet signals UNKNOWN by design; holder_scan_enabled="
          f"{HOLDER_SCAN_ENABLED})")

    # ---- market transport: Birdeye primary in paid modes, existing keyless path otherwise ----
    # Fed only by the already-owned paid gRPC transaction stream; it never opens
    # a second subscription.  Birdeye remains the primary market source.
    reserve_index = PumpSwapReserveIndex(
        ath_store=ath_store,
        canonical_observer_allow_historical=True,
    )
    canonical_volume = CanonicalSwapVolumeTracker()
    reserve_index.add_routing_observer(canonical_volume.observe)
    fee_index = FeeEvidenceIndex()
    security_index = SecurityDecisionIndex()

    # ---- canonical per-mint token metadata (2026-07-28 remediation) ----
    # One merge-only-improve identity state per mint, fed exclusively from
    # responses the run already fetches (backfill admission, paid overview
    # plane, backfill fresh-market gate, restored watch state).  Never a
    # network owner; never a blocking dispatch dependency beyond the bounded
    # pre-dispatch deferral.
    token_metadata = TokenMetadataResolver(now_iso_fn=_utc_now_iso)
    # Optional presentation cache: no additional metadata requests, no URLs
    # in delivery evidence, and no persistence across run restarts.
    token_logo_urls: Dict[str, str] = {}

    # ---- canonical per-mint Global Fees telemetry (observe-only) ----
    # All-time global fees paid (SOL) riding the SAME paid overview response
    # as market cap / liquidity / metadata — zero extra provider requests.
    # Never an eligibility, tier, risk, structural, or dispatch input; a
    # missing or invalid value simply omits the Telegram line.
    global_fees = GlobalFeesTracker(now_iso_fn=_utc_now_iso)

    def _harvest_token_metadata(
        mint: object, *, token_name: object, token_symbol: object, source: str,
    ) -> None:
        """Merge held identity fields; mirror onto the durable watch entry.

        Total: any failure leaves candidate flow untouched (metadata is
        display enrichment, never an eligibility input).
        """

        try:
            if not isinstance(mint, str) or not mint:
                return
            token_metadata.merge(
                mint, token_name=token_name, token_symbol=token_symbol,
                source=source)
            resolved = token_metadata.snapshot(mint)
            if resolved.get("validated") is not True:
                return
            entry = watchlist.get(mint)
            if entry is None:
                return
            name = resolved.get("token_name")
            symbol = resolved.get("token_symbol")
            if name and not getattr(entry, "token_name", None):
                entry.token_name = name
            if symbol and not getattr(entry, "symbol_or_name", None):
                entry.symbol_or_name = symbol
        except Exception as harvest_exc:
            errors.log("token_metadata_harvest", harvest_exc)

    # ---- fee gate lifecycle (freshness/maturity/durable-lock separation) ----
    # Stale or immature fee evidence blocks the CURRENT send but no longer
    # poisons a candidate permanently; a durable scam lock needs fresh mature
    # structural scam evidence confirmed across distinct evidence versions (or
    # the LP-removal composite severe proof).  A malformed policy override
    # REFUSES the run instead of silently weakening the confirmation policy.
    try:
        fee_lifecycle_config = build_fee_gate_lifecycle_config(
            os.environ,
            freshness_max_age_seconds=Decimal(str(args.market_fresh_within_seconds)))
    except ValueError as exc:
        print(f"[refused] {exc}")
        return 2
    fee_lifecycle_index = FeeGateLifecycleIndex(
        config=fee_lifecycle_config,
        path=Path(out_dir) / FEE_GATE_LIFECYCLE_BASENAME)
    _fee_lifecycle_boot = fee_lifecycle_index.stats()
    print("fee gate lifecycle: IMMATURE/FRESH_PROVISIONAL/FRESH_CONFIRMED/"
          "TEMPORARILY_STALE/DURABLE_SCAM_LOCKED; "
          f"confirmed_maturity=tx>={fee_lifecycle_config.confirmed_min_transaction_count}"
          f",events>={fee_lifecycle_config.confirmed_min_event_count}"
          f",span>={fee_lifecycle_config.confirmed_min_evidence_span_seconds}s; "
          f"provisional_maturity=tx>={fee_lifecycle_config.provisional_min_transaction_count}"
          f",events>={fee_lifecycle_config.provisional_min_event_count}"
          f",span>={fee_lifecycle_config.provisional_min_evidence_span_seconds}s; "
          f"scam_confirmations={fee_lifecycle_config.scam_confirmations_required} "
          f"(distinct evidence versions, structural reason required, "
          f"thin_sample/stale never count); "
          f"freshness_max_age="
          f"{format(fee_lifecycle_config.freshness_max_age_seconds, 'f')}s; "
          f"restored_records={_fee_lifecycle_boot['fee_lifecycle_restored_records']} "
          f"restored_locks={_fee_lifecycle_boot['fee_lifecycle_restored_locks']} "
          f"legacy_lp_locks_ignored="
          f"{_fee_lifecycle_boot['fee_lifecycle_legacy_lp_locks_ignored']} "
          f"load_dropped={_fee_lifecycle_boot['fee_lifecycle_load_dropped']}")

    # ---- migration admission (proven pump.fun migrate CPI only) + sealed proofs ----
    # The deposit floor is defense-in-depth behind the program/CPI proof and is
    # strictly Decimal (PHX2_MIGRATION_MIN_QUOTE_DEPOSIT_SOL); a malformed
    # override REFUSES the run instead of silently weakening admission.
    try:
        migration_admission_config = build_migration_admission_config(os.environ)
    except ValueError as exc:
        print(f"[refused] {exc}")
        return 2
    proof_store = MigrationProofStore(Path(out_dir) / MIGRATION_PROOFS_BASENAME)
    reserve_index.bind_proof_store(proof_store)
    restored_proofs = len(proof_store.all_proofs())
    migration_metrics: Dict[str, Any] = {
        "baseline_observed_pre_authorization": 0,
        # Observe-only tier telemetry a durable checkpoint could not hold and
        # that was therefore EXCLUDED rather than written through.
        "tier_projection_telemetry_excluded": 0,
        # Bounded migration-anchored OHLCV hydration attempts driven for
        # candidates whose post-migration ATH coverage is still pending.
        "ath_hydration_attempts": 0,
        "ath_hydration_completed": 0,
        # Lifecycle-driven sweeps (not pricing-tail side effects).
        "ath_hydration_sweeps": 0,
        "ath_hydration_driven": 0,
    }
    # Closed-set single-stream pipeline counters surfaced by every heartbeat,
    # summary and status read.
    pipeline_counters: Dict[str, int] = {
        "baselines_captured": 0,
        "candidates_activated": 0,
        "liquidity_floor_pass": 0,
        "liquidity_floor_fail": 0,
        # Sends refused because gRPC discovery coverage was unproven. A
        # non-zero value here is the observable trace that recovery health
        # actually gated the outbound path.
        "source_health_block": 0,
        **{name: 0 for name in ACTIVATION_COUNTER_FIELDS},
    }
    # Legacy two-stream artifacts (an old verifier event log, or sealed proofs
    # from a pre-migrate_v2 schema) are observably ignored: they never restore
    # verifier buffer state and never gate authorization in single-stream mode.
    legacy_lp_artifacts_present = bool(
        (Path(out_dir) / LEGACY_LIQUIDITY_EVENTS_BASENAME).exists()
        or proof_store.stats()["proof_load_dropped"] > 0)
    legacy_lp_state = (
        LEGACY_LP_STATE_IGNORED_SINGLE_STREAM if legacy_lp_artifacts_present else None)
    print(f"migration admission: pump.fun migrate/migrate_v2 CPI proof required "
          f"(unknown migration discriminators fail closed); "
          f"min_quote_deposit_sol="
          f"{format(migration_admission_config.min_quote_deposit_sol, 'f')}; "
          f"restored_sealed_proofs={restored_proofs}")
    if legacy_lp_state is not None:
        print(f"legacy lp artifacts: {legacy_lp_state} (historical two-stream "
              f"state observed; ignored for authorization)")
    fallback_transport = None
    fallback_secret = None
    market_credential_status: Optional[str] = None
    p1_backlog_ref: Dict[str, Any] = {"fn": None}
    # The ONE authoritative physical-request counter for this run, created
    # before any transport so exactly one object is shared by the market
    # transport (which records every dialled request and every early return
    # that dialled nothing) and the market scheduler (which charges only
    # immutable tickets carrying its exact job IDs). Before this existed the two
    # sides kept independent counts and disagreed by 1,528 requests.
    physical_request_meter = MarketPhysicalRequestMeter(
        ticket_artifact=Path(out_dir) / "provider_request_tickets.jsonl")
    authoritative_supply_bridge: Optional[AuthoritativeSupplyBridge] = None
    fresh_market_fallback: Optional[AuthenticatedPumpSwapMarketFallback] = None
    if helius_primary and helius_source_config is not None:
        authoritative_supply_client = HeliusTokenSupplyClient(
            rpc_base_url=helius_source_config.rpc_base_url.reveal(),
            api_key=helius_source_config.api_key.reveal(),
            physical_request_meter=physical_request_meter,
            artifact_path=Path(out_dir) / SUPPLY_ARTIFACT_BASENAME,
        )
        authoritative_supply_bridge = AuthoritativeSupplyBridge(
            client=authoritative_supply_client,
            ath_store=ath_store,
        )
        fresh_market_fallback = AuthenticatedPumpSwapMarketFallback(
            rpc_base_url=helius_source_config.rpc_base_url.reveal(),
            api_key=helius_source_config.api_key.reveal(),
            proof_store=proof_store,
            ath_store=ath_store,
            quote_price_fn=reserve_index.quote_price_snapshot,
            physical_request_meter=physical_request_meter,
            artifact_path=(Path(out_dir) /
                           FRESH_FALLBACK_ARTIFACT_BASENAME),
        )
    # Bounded-grace market-plane liveness. Purely time-based and deterministic:
    # a short outage is degraded, the same condition sustained past the grace
    # is blind and fails closed. A quiet watchlist can never trip it.
    market_plane_watch = MarketPlaneWatch(MarketPlaneConfig())
    if paid_mode:
        # ---- PHX2-E2E-006 structural capacity refusal ------------------
        # Evaluated from arguments alone, BEFORE any transport, channel,
        # stub, provider, or network object is constructed.  The formula
        # and the runtime scheduler consume the SAME configuration object.
        market_scheduling = resolve_production_market_scheduling(args)
        capacity_verdict = evaluate_session_p1_capacity(args)
        if not capacity_verdict["p1_capacity_achievable"]:
            print(f"[refused] {P1_CAPACITY_UNACHIEVABLE} "
                  f"active_cap={capacity_verdict['configured_active_cap']} "
                  f"deadline_s={capacity_verdict['required_deadline_seconds']} "
                  f"calculated_bound_s={capacity_verdict['calculated_worst_case_bound_seconds']} "
                  f"concurrency={capacity_verdict['configured_concurrency']} "
                  f"spacing_s={capacity_verdict['request_start_spacing_seconds']} "
                  f"throughput_rps={capacity_verdict['throughput_rps']} "
                  f"batch_size={capacity_verdict['batch_size']} "
                  "(no provider object was constructed)")
            return 2
        try:
            from PHX2.stage29.stage29_2_birdeye_http_transport import Stage29_2BirdeyeUrlibTransport
            from PHX2.stage29.stage29_2_birdeye_readiness import build_endpoint_secret_from_env
            endpoint_secret = build_endpoint_secret_from_env()
            # MANDATORY bounded credential gate.  Exactly one request, no retry.
            # A rejected key is fatal HERE — before the live epoch is armed,
            # before any Telegram transport exists, and with the paid ledger
            # untouched.  Presence-only readiness let an invalid credential
            # reach runtime and fail silently as 48/48 http_errors (2026-07-30).
            market_credential_verdict = validate_market_credential(
                transport=Stage29_2BirdeyeUrlibTransport(),
                endpoint_secret=endpoint_secret,
                timeout_seconds=int(
                    os.environ.get("PHX2_STAGE29_2_HTTP_TIMEOUT_SECONDS") or 10),
            )
            market_credential_status = str(
                market_credential_verdict["credential_status"])
            print("market credential: "
                  f"{market_credential_verdict['credential_status']} "
                  f"http_status={market_credential_verdict['http_status_code']} "
                  f"attempts={market_credential_verdict['attempts']} "
                  "(key/header/URL NEVER printed)")
            if market_credential_verdict["fatal"]:
                print("[refused] MARKET_CREDENTIAL_CHECK_FAILED: "
                      f"{market_credential_verdict['credential_status']} — "
                      f"{market_credential_verdict['sanitized_reason']}; "
                      "epoch NOT armed, producer NOT started, zero Telegram "
                      "attempts, paid ledger unchanged.")
                return 2
            free_market_fallback = None
            free_market_secret = None
            if provider_mode == PROVIDER_MODE_PAID_WITH_FALLBACK:
                # The keyless fallback dials a DIFFERENT provider, but it is
                # still physical spend caused by the scheduler's own fetch
                # call, so it shares the same meter. Without this its requests
                # would be real, uncounted, and invisible to reconciliation.
                free_market_fallback = FreeTierMarketTransport(
                    max_calls_total=_transport_call_cap(args),
                    physical_request_meter=physical_request_meter)
                free_market_secret = build_free_tier_endpoint_secret()
            market_transport = PaidBirdeyeMarketTransport(
                inner_transport=Stage29_2BirdeyeUrlibTransport(),
                endpoint_secret=endpoint_secret,
                fallback_transport=free_market_fallback,
                fallback_endpoint_secret=free_market_secret,
                min_interval_seconds=market_scheduling["spacing_seconds"],
                cache_ttl_seconds=float(args.birdeye_cache_ttl_seconds),
                max_attempts=int(args.birdeye_max_attempts),
                max_calls_total=_transport_call_cap(args),
                max_data_age_seconds=float(args.market_fresh_within_seconds),
                ath_store=ath_store,
                max_concurrency=market_scheduling["concurrency"],
                background_yield_fn=lambda: bool(
                    p1_backlog_ref["fn"]() if p1_backlog_ref["fn"] else False),
                # ONE provider-scoped throttle object shared with the run
                # budget: the transport decides whether to dial, the budget
                # reports the degradation. A market throttle can no longer stop
                # the producer or touch Helius discovery / watch state.
                rate_limit_backoff=budget.market_backoff,
                # ONE authoritative physical-request counter shared with the
                # market scheduler. The transport owns every write; the
                # scheduler charges only tickets carrying its exact job ID,
                # so a cache hit costs zero and a batch costs exactly one.
                physical_request_meter=physical_request_meter,
            )
            print("market: PAID_MARKET_PRIMARY (deadline scheduler, bounded workers/retries/cache; "
                  f"keyless fallback={'ON' if free_market_fallback else 'OFF'}).")
            print("market throttle: HTTP 429 -> provider-scoped bounded jittered backoff "
                  f"(ceiling {budget.market_backoff.backoff_ceiling_seconds:.1f}s, "
                  f"degraded after {budget.caps.max_429_total} consecutive); "
                  "401/403 remain permanent and fatal at the credential gate")
            print(f"market p1: capacity ACHIEVABLE "
                  f"bound_s={capacity_verdict['calculated_worst_case_bound_seconds']} "
                  f"deadline_s={capacity_verdict['required_deadline_seconds']} "
                  f"active_cap={capacity_verdict['configured_active_cap']} "
                  f"concurrency={capacity_verdict['configured_concurrency']} "
                  f"spacing_s={capacity_verdict['request_start_spacing_seconds']} "
                  f"reserved_p1_workers={market_scheduling['p1_reserved_workers']}")
        except Exception as exc:
            print(f"[refused] paid Birdeye readiness failed ({type(exc).__name__}); "
                  "no provider started; values never printed.")
            return 2
    else:
        if args.allow_birdeye_fallback:
            try:
                from PHX2.stage29.stage29_2_birdeye_http_transport import Stage29_2BirdeyeUrlibTransport
                from PHX2.stage29.stage29_2_birdeye_readiness import build_endpoint_secret_from_env
                fallback_secret = build_endpoint_secret_from_env()
                fallback_transport = Stage29_2BirdeyeUrlibTransport()
                print("market: optional keyed fallback transport constructed (used only when the "
                      "free path yields nothing).")
            except Exception as exc:
                print(f"market: fallback requested but unavailable ({type(exc).__name__}); "
                      f"continuing pure free-tier.")
        market_transport = FreeTierMarketTransport(
            fallback_transport=fallback_transport, fallback_endpoint_secret=fallback_secret,
            max_calls_total=_transport_call_cap(args),
        )
        endpoint_secret = build_free_tier_endpoint_secret()
    timeout_seconds = int(args.market_timeout_seconds)

    market_readiness = (
        PaidMarketReadinessTracker(PaidMarketReadinessConfig(
            indexing_grace_seconds=float(args.market_indexing_grace_seconds),
            max_transient_attempts=int(args.market_indexing_max_attempts),
        ))
        if paid_mode else None
    )

    # 2026-07-10 market fix: fresh pump mints often list price/MC before the free pairs lookup
    # carries liquidity.usd, so a single offset-0 attempt fails REAL_MARKET_INCOMPLETE forever
    # in that recheck. The committed sidecar's bounded escalating refresh (offsets 0/+10/+30/+60s
    # after migration, stop at first all-present) retries within the recheck; the transport's
    # pair-cache TTL (20s) makes the spaced attempts real refetches, and the per-token/total caps
    # keep it bounded. --market-refresh-max-delay-seconds 0 restores the old single-attempt mode.
    market_scheduler: Optional[MarketScheduler] = None

    def sidecar_factory(_cycle: int) -> Cap1MarketSidecar:
        if market_scheduler is not None:
            # reserve_index gives the compose/delivery context the exact-pair
            # actual-reserve telemetry (2026-07-28 liquidity remediation).
            return ScheduledMarketSidecar(
                market_scheduler, central_ath_snapshot_fn=ath_store.snapshot,
                reserve_index=reserve_index)
        return Cap1MarketSidecar(
            transport=market_transport, endpoint_secret=endpoint_secret,
            timeout_seconds=timeout_seconds, enabled=True,
            caps=Cap1MarketCaps(
                max_delayed_refresh_seconds=int(args.market_refresh_max_delay_seconds),
                max_calls_per_token=int(args.market_refresh_max_calls_per_token),
                max_calls_total=256),
            readiness_tracker=market_readiness,
            reserve_index=reserve_index,
            ath_store=ath_store,
        )

    # ---- ledger + guard transport (the ONLY mode-dependent seam) ----
    from PHX2.stage30.stage30_11_15_ping_dedupe_ledger import JsonlPingDedupeLedger
    from PHX2.stage30.stage30_11_2_fake_runtime_gate_proof import make_constant_clock
    from PHX2.stage30.stage30_11_15_ping_dedupe_models import (
        STAGE30_11_15_DEFAULT_TTL_SECONDS,
    )
    from PHX2.free_tier_producer.delivery_transaction import (
        DeliveryAttemptJournal,
        reconcile_journal_on_restart,
        reconcile_watchlist_delivery,
    )
    durable = JsonlPingDedupeLedger(path=ledger_path)

    # Delivery attempt/outbox journal (PHX2-E2E-001): lives BESIDE the durable
    # successful-send ledger (NOT in the per-run out_dir) so a confirmed-success
    # receipt survives a restart and can finish its ledger commit without a
    # second transport call. Separate schema; never a dedupe surface itself.
    delivery_outbox_path = Path(str(ledger_path)).parent / "delivery_outbox.jsonl"
    delivery_journal = DeliveryAttemptJournal(path=delivery_outbox_path)
    delivery_reconciliation = reconcile_journal_on_restart(
        journal=delivery_journal, ledger=durable, now_utc=_utc_now_iso(),
        ttl_seconds=STAGE30_11_15_DEFAULT_TTL_SECONDS)
    _append_jsonl(Path(out_dir) / "delivery_reconciliation.jsonl",
                  delivery_reconciliation)
    print("delivery: commit-after-confirmed-delivery transaction active "
          f"(outbox journal beside ledger; journal_available={delivery_journal.available} "
          f"restart_commits_completed={delivery_reconciliation['commits_completed']} "
          f"pending_unknown={delivery_reconciliation['pending_unknown']})")

    would_ping_bodies_path = Path(out_dir) / WOULD_PING_BODIES_BASENAME
    telegram_attempts_path = Path(out_dir) / TELEGRAM_ATTEMPTS_BASENAME
    telegram_composes_path = Path(out_dir) / TELEGRAM_COMPOSES_BASENAME
    telegram_adapter: Optional[TelegramDeliveryAdapter] = None
    delivery_observability: Dict[str, Any] = {
        "eligible_candidates": 0,
        "composed_alerts": 0,
        "sent_alerts": 0,
        "delivery_attempts": 0,
        "telegram_result": {
            "transport_status": "NOT_ATTEMPTED",
            "ok": False,
        },
    }

    if telegram_enabled:
        assert telegram_config is not None

        def record_telegram_compose(rec: Dict[str, Any]) -> None:
            _append_jsonl(telegram_composes_path, dict(rec))
            delivery_observability["composed_alerts"] += 1

        def record_telegram_attempt(rec: Dict[str, Any]) -> None:
            safe = dict(rec)
            _append_jsonl(telegram_attempts_path, safe)
            delivery_observability["delivery_attempts"] += 1
            transport_result = safe.get("result")
            if transport_result == "SENT_OK":
                delivery_observability["sent_alerts"] += 1
            delivery_observability["telegram_result"] = {
                **{
                    key: safe.get(key)
                    for key in (
                        "transport", "message_id", "destination_alias",
                        "attempted_at_utc", "delivered_at_utc", "retry_count",
                        "safe_error_category",
                    )
                },
                "result": transport_result,
                "ok": transport_result == "SENT_OK",
            }

        telegram_adapter = TelegramDeliveryAdapter(
            TelegramTransport(telegram_config),
            logo_resolver=lambda mint: token_logo_urls.get(mint),
            compose_sink=record_telegram_compose,
            attempt_sink=record_telegram_attempt,
            console_sink=print,
        )
        guard_transport = telegram_adapter
        authorization = cs.build_authorization(
            confirm_token=args.confirm_token,
            operator_label=args.operator_label or "PHX2_TELEGRAM_OPERATOR",
            authorization_reason=args.authorization_reason or "PHX2_TELEGRAM_PING",
            created_at_utc=_utc_now_iso())
    elif discord_enabled:
        guard_transport = b30s._build_real_private_transport(
            os.environ.get(ENV_WEBHOOK) or "", args.webhook_identity, float(timeout_seconds))
        authorization = cs.build_authorization(
            confirm_token=args.confirm_token,
            operator_label=args.operator_label or "PHX2_FREE_TIER_OPERATOR",
            authorization_reason=args.authorization_reason or "FREE_TIER_PRIVATE_PING",
            created_at_utc=_utc_now_iso())
    else:
        guard_transport = FreeTierRecordingNoSendTransport(
            on_record=lambda rec: _append_jsonl(would_ping_bodies_path, rec),
            now_iso_fn=_utc_now_iso)
        authorization = cs.build_authorization(
            confirm_token=LOCKED_CONFIRM_TOKEN,
            operator_label="PHX2_FREE_TIER_NO_SEND",
            authorization_reason="FREE_TIER_NO_SEND_WOULD_PING_RECORDING",
            created_at_utc=_utc_now_iso())

    # WARN-ONLY risk display line on the outgoing body (both modes; the no-send recorder then
    # records the annotated body into would_ping_bodies.jsonl). Same one-shot bind_body display
    # seam the production Axiom fee appender proved: annotation failure forwards the payload
    # unmodified; eligibility/reserve/send are decided entirely upstream of this wrapper.
    def _security_and_risk_lines(mint: str) -> Optional[str]:
        lines = []
        security_line = security_index.line(mint)
        if security_line:
            lines.append(security_line)
        risk_line = risk_engine.risk_line(mint)
        if risk_line:
            lines.append(risk_line)
        return "\n".join(lines) if lines else None

    if telegram_enabled:
        delivery_body_adapter: Any = telegram_adapter
        print("security display: final Telegram HTML is composed from the mint-bound immutable "
              "Fee Gate, composite, ATH, migration, activation, and tier proofs "
              "(LP Integrity displays DISABLED in single-stream mode)")
    else:
        risk_transport = FreeTierRiskLineTransport(
            inner=guard_transport, risk_line_fn=_security_and_risk_lines)
        guard_transport = risk_transport
        delivery_body_adapter = risk_transport
        print("security display: centralized Fee Gate, composite verdict, and risk "
              "are appended from the mint-bound immutable decision "
              "(LP Integrity displays DISABLED in single-stream mode)")

    # ---- watchlist (restart-safe) ----
    activation_events_path = Path(out_dir) / "activation_events.jsonl"
    # Activation events arrive from the engine thread AND the market-scheduler
    # owner thread; a raw per-record append tore this file under that
    # concurrency (Windows CRT O_APPEND is seek-then-write, 2026-07-29 Gate G).
    activation_events_appender = SerializedJsonlAppender(activation_events_path)

    def _record_activation_event(record: Dict[str, Any]) -> None:
        # One artifact writer for every activation event source, so the
        # baselines_captured / candidates_activated counters stay coherent
        # across the pricing-tail and engine observation paths.
        event = record.get("event") if isinstance(record, dict) else None
        if event == "BASELINE_CAPTURED":
            pipeline_counters["baselines_captured"] += 1
        elif event == "ACTIVATED":
            pipeline_counters["candidates_activated"] += 1
        counter = record.get("activation_counter") if isinstance(record, dict) else None
        if counter in ACTIVATION_COUNTER_FIELDS:
            pipeline_counters[counter] += 1
        try:
            activation_events_appender.append(record)
        except SerializedJsonlAppendError as exc:
            # Disclosed, never silent: closed-set reason + underlying error
            # TYPE reach errors.jsonl / error_count (no record content).
            errors.log("activation_event_append", exc,
                       note=f"{exc.reason}:{exc.error_type}")

    watch_paths = resolve_watch_state_paths(
        out_dir=out_dir,
        cursor_state_dir=getattr(args, "cursor_state_dir", None))
    watch_state_path = watch_paths["watch_state_path"]
    watch_terminal_history_path = watch_paths["watch_terminal_history_path"]
    watch_mirror_path = Path(watch_paths["watch_state_mirror_path"])
    watch_terminal_mirror_path = Path(
        watch_paths["watch_terminal_history_mirror_path"])
    watch_state_is_durable = bool(watch_paths["durable"])
    adoption = adopt_legacy_run_dir_watch_state(watch_paths)
    watch_state_adopted_from_run_dir = bool(adoption["adopted"])
    for adoption_error in adoption["errors"]:
        errors.log("watch_state_adoption", adoption_error,
                   note="WATCH_STATE_LEGACY_ADOPTION_FAILED")
    print(f"watch state: durable={watch_state_is_durable} "
          f"mirrored_to_run_dir={watch_state_is_durable} "
          f"adopted_from_run_dir={watch_state_adopted_from_run_dir}")
    if Path(watch_state_path).exists() \
            or Path(watch_state_path + ".bak").exists():
        watchlist = Watchlist.load(
            watch_state_path, max_size=int(args.max_watchlist_size),
            terminal_history_path=watch_terminal_history_path,
            mirror_path=watch_mirror_path,
            terminal_history_mirror_path=watch_terminal_mirror_path,
            now_utc=_utc_now_iso())
        watch_checkpoint = watchlist.checkpoint_summary()
        print("watch checkpoint: "
              f"{watch_checkpoint.get('checkpoint_status')} "
              f"(schema={watch_checkpoint.get('checkpoint_schema_version')} "
              f"generation={watch_checkpoint.get('checkpoint_generation')} "
              f"records={watch_checkpoint.get('checkpoint_records_validated')} "
              f"rejected={watch_checkpoint.get('checkpoint_records_rejected')} "
              f"activation_migrated="
              f"{watch_checkpoint.get('checkpoint_legacy_activation_migrated')} "
              f"quarantined_candidates="
              f"{watch_checkpoint.get('checkpoint_quarantined_candidates')})")
        if watchlist.checkpoint_quarantined:
            # PHX2-E2E-005: the authoritative watch checkpoint failed
            # authentication (primary AND backup). Refuse normal alerting;
            # preserve the evidence files unchanged for inspection.
            artifacts.write_json(out_dir, CHECKPOINT_QUARANTINE_BASENAME, {
                "kind": "PHX2_CHECKPOINT_QUARANTINE",
                "quarantined_checkpoint": "WATCH_STATE",
                "observed_at_utc": _utc_now_iso(),
                "watch": watch_checkpoint,
                "ath": ath_store.checkpoint_summary(),
            })
            print("[refused] CHECKPOINT_QUARANTINED:WATCH_STATE:"
                  f"{watch_checkpoint.get('checkpoint_quarantine_reason')}")
            return 2
        for inconsistency in verify_cross_checkpoint_consistency(
                watchlist, ath_store.all_snapshots(), now_utc=_utc_now_iso()):
            print("watch checkpoint: cross-consistency quarantine "
                  f"mint={str(inconsistency.get('token_mint'))[:16]}… "
                  f"issue={inconsistency.get('issue')}")
        restored_summary = watchlist.summary()
        print(f"watchlist: restored {len(watchlist.all_entries())} active entries "
              f"({restored_summary.get('tracked', 0)} tracked; "
              f"{restored_summary.get('active_dip_watch', 0)} active dip; "
              f"{restored_summary.get('terminal_history', 0)} terminal history; "
              f"{restored_summary.get('legacy_terminal_migrated', 0)} legacy terminal migrated; "
              f"{restored_summary.get('market_recovery_backoff', 0)} market recovery backoff; "
              f"{restored_summary.get('market_legacy_terminal_migrated', 0)} market terminal migrated) "
              "from watch_state.jsonl")
        # PHX2-E2E-004: seed the fresh in-memory readiness tracker from restored
        # recovery-backoff entries so a restart does NOT immediately re-poll the
        # provider — the next resolve before the persisted probe time returns
        # MARKET_RECOVERY_BACKOFF_NOT_DUE with zero fetches.
        if market_readiness is not None:
            for _entry in watchlist.all_entries():
                if _entry.market_state == MARKET_RECOVERY_BACKOFF:
                    try:
                        market_readiness.seed_recovery_state(
                            _entry.token_mint,
                            now_iso=_utc_now_iso(),
                            next_recovery_probe_at_utc=_entry.next_market_refresh_at_utc,
                            legacy_migrated=bool(
                                _entry.market_legacy_terminal_migrated),
                            migration_time_utc=_entry.migration_time_utc,
                        )
                    except Exception:
                        pass
    else:
        watchlist = Watchlist(
            max_size=int(args.max_watchlist_size),
            terminal_history_path=watch_terminal_history_path)
        watchlist.set_mirror_path(
            watch_mirror_path,
            terminal_history_path=watch_terminal_mirror_path)

    admission_inbox = None
    if provider_mode != PROVIDER_MODE_FREE_TIER:
        try:
            admission_inbox = DurableAdmissionInbox(
                Path(watch_state_path).parent / "pending_admissions.json",
                max_pending=int(args.queue_pressure_max))
            watchlist.bind_admission_inbox(admission_inbox)
        except AdmissionInboxError:
            print("[refused] ADMISSION_INBOX_UNAVAILABLE")
            return 2

    # Fixed for this producer process. Checkpoint generations may advance as
    # state is persisted, but request-ticket provenance must not change its
    # producer generation midway through a run.
    _ticket_producer_generation = int(
        watchlist.checkpoint_summary().get("checkpoint_generation") or 0) + 1
    physical_request_meter.set_runtime_identity(
        producer_generation=_ticket_producer_generation)

    def _checkpoint_status_snapshot() -> Dict[str, Any]:
        return {
            "kind": "PHX2_CHECKPOINT_STATUS",
            "updated_at_utc": _utc_now_iso(),
            "watch": watchlist.checkpoint_summary(),
            "ath": ath_store.checkpoint_summary(),
        }

    artifacts.write_json(
        out_dir, CHECKPOINT_STATUS_BASENAME, _checkpoint_status_snapshot())
    # Align restored watch entries with the delivery outbox: an
    # already-committed delivery terminalizes WITHOUT another transport call;
    # a pending-unknown attempt surfaces as observable DELIVERY_UNKNOWN.
    for delivery_event in reconcile_watchlist_delivery(
            watchlist=watchlist, journal=delivery_journal,
            now_utc=_utc_now_iso()):
        print(f"delivery: restart alignment {delivery_event.get('action')} "
              f"mint={str(delivery_event.get('token_mint'))[:16]}…")

    # ---- PHX2-E2E-006 deadline-aware paid market scheduler -------------
    if paid_mode:
        # A rebuilt owner advances the persisted generation before accepting
        # any provider result. Threads/futures/queue state are never restored.
        for _entry in watchlist.active_entries():
            _entry.market_observation_generation = max(
                0, int(getattr(_entry, "market_observation_generation", 0))) + 1

        def _apply_readiness_projection(entry: Any, projection: Dict[str, Any]) -> None:
            entry.market_state = projection.get("market_state")
            entry.market_reason_code = projection.get("market_reason_code")
            entry.next_market_refresh_at_utc = projection.get(
                "next_market_refresh_at_utc")
            entry.market_attempt_count = int(
                projection.get("market_attempt_count") or entry.market_attempt_count or 0)

        def _scheduler_apply_observation(
            observation: MarketObservation, snapshot: Dict[str, Any]
        ) -> None:
            entry = watchlist.get(observation.mint)
            if entry is None or entry.candidate_id != observation.candidate_id:
                return
            from PHX2.delivery.telegram_media import validate_logo_url
            logo = validate_logo_url(observation.values.get("token_logo_url"))
            if logo is not None:
                token_logo_urls[observation.mint] = logo
                if len(token_logo_urls) > 512:
                    token_logo_urls.pop(next(iter(token_logo_urls)))
            # Identity fields riding on the already-paid overview response
            # (2026-07-28 metadata remediation): merge before any snapshot
            # projection so an enriched name/ticker is available to the very
            # next compose.  Live-path candidates have no other per-mint
            # metadata source.
            if (observation.values.get("token_name") is not None
                    or observation.values.get("token_symbol") is not None):
                _harvest_token_metadata(
                    observation.mint,
                    token_name=observation.values.get("token_name"),
                    token_symbol=observation.values.get("token_symbol"),
                    source="PAID_MARKET_PRIMARY_OVERVIEW")
            # Observe-only Global Fees riding the same overview observation.
            # Total: a merge failure never touches the market apply path.
            fees_observation = observation.values.get("global_fees")
            if isinstance(fees_observation, dict):
                try:
                    global_fees.observe_overview(
                        observation.mint, fees_observation)
                except Exception as fees_exc:
                    errors.log("global_fees_observe", fees_exc)
            entry.market_observation_generation = observation.generation
            if snapshot.get("price_observed_at_utc") is not None:
                entry.market_price_observed_at_utc = snapshot.get(
                    "price_observed_at_utc")
                entry.market_price_source = snapshot.get("price_source")
            if snapshot.get("market_cap_observed_at_utc") is not None:
                entry.market_market_cap_observed_at_utc = snapshot.get(
                    "market_cap_observed_at_utc")
                entry.market_market_cap_source = snapshot.get("market_cap_source")
            if snapshot.get("liquidity_observed_at_utc") is not None:
                entry.market_liquidity_observed_at_utc = snapshot.get(
                    "liquidity_observed_at_utc")
                entry.market_liquidity_source = snapshot.get("liquidity_source")
            entry.market_state = snapshot.get("market_state")
            entry.market_reason_code = snapshot.get("market_reason_code")
            if market_readiness is not None and snapshot.get("all_present"):
                readiness_projection = market_readiness.observe_scheduled_attempt(
                    observation.mint,
                    migration_time_utc=entry.migration_time_utc,
                    now_iso=_utc_now_iso(),
                    attempt={
                        "price_value": snapshot.get("current_price"),
                        "mc_value": snapshot.get("current_market_cap_usd"),
                        "lp_value": snapshot.get("liquidity_usd"),
                        "provider_timestamp_utc": (
                            snapshot.get("market_context_fetched_at_utc")
                            or snapshot.get("provider_timestamp_utc")),
                        "provider_market_state": "MARKET_READY",
                        "provider_reason_code": "REQUIRED_FIELDS_FRESH",
                        "all_present": True,
                        "basis": "DEADLINE_SCHEDULER",
                    },
                )
                _apply_readiness_projection(entry, readiness_projection)

            # A paid overview may complete the market-cap half of an already
            # fresh paid price observation. It may then drive one paid-primary
            # evaluation. It must never relabel a cached gRPC price as paid.
            evaluate_fast_plane = bool(
                observation.field_group == FIELD_PRICE_MC
                or (observation.values.get("current_market_cap_usd") is not None
                    and snapshot.get("price_source") != SOURCE_GRPC
                    and snapshot.get("market_cap_source") != SOURCE_GRPC
                    and snapshot.get("price_fresh")
                    and snapshot.get("market_cap_fresh")))
            if evaluate_fast_plane:
                reserve_payload = observation.values.get("pumpswap_reserve")
                if not isinstance(reserve_payload, dict):
                    reserve_payload = {}
                central_ath = ath_store.snapshot(observation.mint) or {}
                if (observation.source != SOURCE_GRPC
                        and snapshot.get("current_price") is not None):
                    # The price and market-cap planes are INDEPENDENT: an
                    # overview may refresh the market cap without touching
                    # the price, so the snapshot's (price, market_cap) pair
                    # is not automatically two halves of one response.
                    # Feeding a mismatched pair here is what produced ATH
                    # records whose two maxima described different instants
                    # -- April's 06:08:21Z price sat beside a 06:08:05Z
                    # market cap -- and, through the implied supply, what
                    # made every later candle high unconvertible.  A
                    # non-coherent pair contributes its PRICE only; no
                    # market cap is invented and none is mis-attributed.
                    coherent = bool(snapshot.get("market_pair_coherent"))
                    try:
                        ath_store.observe_provider_current(
                            mint=observation.mint,
                            price_usd=snapshot.get("current_price"),
                            market_cap_usd=(
                                snapshot.get("current_market_cap_usd")
                                if coherent else None),
                            observed_at=snapshot.get("price_observed_at_utc"),
                            confirmed=False,
                        )
                        central_ath = ath_store.snapshot(observation.mint) or central_ath
                    except Exception:
                        pass
                observed = entry.observe_market(
                    current_market_cap_usd=snapshot.get("current_market_cap_usd"),
                    current_price=snapshot.get("current_price"),
                    current_supply=reserve_payload.get("base_supply"),
                    provider_timestamp_utc=(snapshot.get("price_observed_at_utc")
                                            or snapshot.get("provider_timestamp_utc")),
                    observed_at_utc=_utc_now_iso(),
                    observation_source=(
                        "CHAINSTACK_GRPC_EVENT" if observation.source == SOURCE_GRPC
                        else "AUTHENTICATED_PUMPSWAP_ACCOUNT_SNAPSHOT"
                        if observation.source == SOURCE_AUTHENTICATED_RESERVE_FALLBACK
                        else "PAID_MARKET_PRIMARY"),
                    max_age_seconds=(
                        float(args.market_grpc_max_age_seconds)
                        if observation.source == SOURCE_GRPC
                        else float(args.market_fresh_within_seconds)),
                    central_ath=central_ath,
                    pumpswap_reserve=reserve_payload,
                )
                for event in observed.get("events", ()):
                    _record_activation_event(event)
                # A tier is only meaningful against a COMPLETE post-migration
                # maximum.  A restart-backfill candidate still hydrating its
                # migration-anchored history carries only the maximum PHX2 has
                # seen since admission, so it gets NO final drawdown and NO
                # tier -- it stays retained and retryable instead.
                coverage = classify_ath_coverage(
                    discovery_provenance=entry.discovery_provenance,
                    ath_hydration_status=central_ath.get(
                        "ath_hydration_status"),
                )
                if ath_coverage_is_complete(coverage):
                    market_scheduler.record_tier_projection(  # type: ignore[union-attr]
                        observation.mint,
                        # Bind the PROJECTION to the same maximum the
                        # composer binds the real tier to.  Reading the raw
                        # split arm here would make the projected tier (which
                        # now also drives the adaptive refresh cadence) and
                        # the composed tier disagree by construction.
                        ath_market_cap_usd=(
                            central_ath.get("resolved_ath_market_cap")
                            if central_ath.get("resolved") is True
                            else (central_ath.get("ath_market_cap")
                                  or central_ath.get("ath_market_cap_usd"))),
                    )
                    projected = market_scheduler.snapshot(  # type: ignore[union-attr]
                        observation.mint)
                    if not entry.set_market_tier_projection(
                            tier=projected.get("projected_tier"),
                            drawdown_pct=projected.get(
                                "projected_drawdown_pct")):
                        migration_metrics[
                            "tier_projection_telemetry_excluded"] += 1
                else:
                    entry.set_market_tier_projection(
                        tier=None, drawdown_pct=None)
                    entry.last_reason = "ATH_HYDRATION_PENDING"
                # Adaptive-cadence heat anchor: an activation transition or an
                # active dip is renewed life, so the candidate returns to the
                # fast refresh lane immediately (PHX1_PARITY only; the tracker
                # ignores this under LEGACY).
                if market_readiness is not None and (
                        observed.get("just_activated") or entry.is_dip_active()):
                    try:
                        market_readiness.note_candidate_activity(
                            observation.mint,
                            now_iso=_utc_now_iso(),
                            is_active_dip=entry.is_dip_active(),
                        )
                    except Exception:
                        pass
            market_scheduler.update_candidates(  # type: ignore[union-attr]
                watchlist.active_entries())

        def _scheduler_failure(mint: str, field_group: str, reason: str) -> None:
            # Observe-only Global Fees failure telemetry for the overview
            # plane (closed-set mapping; never erases a prior valid value,
            # never schedules any retry of its own).
            if field_group == FIELD_OVERVIEW:
                try:
                    global_fees.observe_scheduler_failure(
                        mint, failure_reason=reason)
                except Exception as fees_exc:
                    errors.log("global_fees_failure_observe", fees_exc)
            entry = watchlist.get(mint)
            if entry is None:
                return
            if market_readiness is not None:
                readiness_projection = market_readiness.observe_scheduled_attempt(
                    mint,
                    migration_time_utc=entry.migration_time_utc,
                    now_iso=_utc_now_iso(),
                    attempt={
                        "price_value": None,
                        "mc_value": None,
                        "lp_value": None,
                        "provider_timestamp_utc": None,
                        "provider_market_state": MARKET_INDEXING,
                        "provider_reason_code": str(reason),
                        "all_present": False,
                        "basis": "DEADLINE_SCHEDULER_FAILURE",
                    },
                )
                _apply_readiness_projection(entry, readiness_projection)
            else:
                entry.market_reason_code = str(reason)
                if entry.market_state != MARKET_RECOVERY_BACKOFF:
                    entry.market_state = "MARKET_INCOMPLETE"
            entry.last_reason = f"{field_group}_{reason}"
            market_scheduler.update_candidates(  # type: ignore[union-attr]
                watchlist.active_entries())

        # Batching is driven by what the provider client DECLARES it can do,
        # never by a hardcoded number.  The committed paid client exposes only
        # single-address price/overview GET shapes, so it declares
        # price_batch_supported=False and the scheduler stays single-mint --
        # inventing a multi-mint URL against an unverified plan is exactly the
        # kind of fabrication this codebase refuses.  The moment the client
        # gains a real multi-address endpoint and declares it, the scheduler's
        # existing batch path is used with no further change here.
        batch_capability = resolve_paid_batch_capability(market_transport)
        scheduler_config = build_production_market_scheduler_config(
            args, paid_batch_size=batch_capability["batch_size"])
        print("market batching: "
              f"supported={batch_capability['supported']} "
              f"batch_size={batch_capability['batch_size']} "
              f"reason={batch_capability['reason']}")
        p1_attempt_timeout = scheduler_config.effective_p1_attempt_timeout_seconds()
        market_scheduler = MarketScheduler(
            price_fetch_fn=lambda mint, deadline_monotonic=None: (
                market_transport.fetch_price_plane(
                    mint,
                    timeout_seconds=min(
                        timeout_seconds, max(1, int(p1_attempt_timeout))),
                    deadline_monotonic=deadline_monotonic,
                    max_attempts=(scheduler_config.p1_max_attempts
                                  if deadline_monotonic is not None else None))),
            overview_fetch_fn=lambda mint, deadline_monotonic=None: (
                market_transport.fetch_overview_plane(
                    mint,
                    timeout_seconds=min(
                        timeout_seconds, max(1, int(p1_attempt_timeout))),
                    deadline_monotonic=deadline_monotonic,
                    max_attempts=(scheduler_config.p1_max_attempts
                                  if deadline_monotonic is not None else None))),
            batch_price_fetch_fn=(
                market_transport.fetch_price_plane_batch
                if batch_capability["supported"] else None),
            config=scheduler_config,
            apply_callback=_scheduler_apply_observation,
            failure_callback=_scheduler_failure,
            quote_price_apply_fn=lambda mint, price, observed_at: (
                reserve_index.cache_quote_price(
                    mint, price, observed_at=observed_at)),
            physical_request_meter=physical_request_meter,
            fresh_fallback_fetch_fn=(
                fresh_market_fallback.fetch
                if fresh_market_fallback is not None else None),
        )
        market_scheduler.note_capacity_proof(capacity_verdict)
        p1_backlog_ref["fn"] = market_scheduler.p1_backlog_pending
        market_scheduler.update_candidates(watchlist.active_entries())
        # Restart: rebuild every P1-due window from the durable watch
        # evidence timestamps, so an already-overdue candidate restarts
        # explicitly overdue and is serviced first by deadline order.
        p1_restart = market_scheduler.reconstruct_p1_from_watch(
            watchlist.active_entries())
        if p1_restart["reconstructed"]:
            print(f"market p1: restart reconstructed "
                  f"{p1_restart['reconstructed']} due windows "
                  f"(already_overdue={p1_restart['already_overdue']})")
        reserve_index.add_routing_observer(
            market_scheduler.submit_trusted_reserve)
        reserve_index.add_quote_request_observer(
            market_scheduler.request_quote_price)

    # ---- pricing tail (paper pricing continuity for EVERY accepted watchlist mint) ----
    activation_source_label = "PAID_MARKET_PRIMARY" if paid_mode else "NON_PAID_PRIMARY"

    def _drive_ath_hydration(mint: str) -> None:
        """Bounded migration-anchored OHLCV hydration for ONE pending mint.

        Nothing else in the scheduled paid topology drives the complete-window
        refresh: the scheduler only fetches the price and overview planes, so
        before this hook ``refresh_ath_history`` was never called in a
        production run and no candidate could ever reach a verified
        post-migration ATH (0 of 106 records in the 2026-07-30 canary).  The
        central ATH store owns the bounded retry schedule, the transport owns
        its own request TTL, and an attempt is only charged against the backoff
        when it actually reached the provider.  Failure here degrades hydration
        (the candidate stays pending, retained and retryable) and never affects
        admission, activation or safety.
        """

        refresh = getattr(market_transport, "refresh_ath_history", None)
        if not callable(refresh):
            return
        try:
            if not ath_store.hydration_due(mint, now_utc=_utc_now_iso()):
                return
            with physical_request_meter.ownership(
                    origin=ORIGIN_ATH_HYDRATION_OHLCV,
                    mint=mint,
                    scheduler_owner="ATH_HYDRATION",
                    batch_size=1):
                outcome = refresh(mint, timeout_seconds=timeout_seconds)
        except Exception as hydrate_exc:
            errors.log("ath_hydration_refresh", hydrate_exc)
            return
        if not isinstance(outcome, dict) or not outcome.get("attempted"):
            return
        migration_metrics["ath_hydration_attempts"] += 1
        try:
            hydration = ath_store.note_hydration_attempt(
                mint, attempted_at_utc=_utc_now_iso())
        except Exception as hydrate_exc:
            errors.log("ath_hydration_bookkeeping", hydrate_exc)
            return
        if hydration.get("status") == ATH_HYDRATION_COMPLETE:
            migration_metrics["ath_hydration_completed"] += 1

    def _sweep_ath_hydration(limit: int = 8) -> int:
        """Bounded per-tick hydration sweep over ACTIVELY TRACKED candidates.

        Hydration used to ride exclusively on the pricing tail, which is
        capacity-bounded at ``--tail-max-tracked`` slots.  A run tracking
        145 mints therefore never hydrated most of them at all, and a
        restart-backfill candidate admitted past that capacity could sit at
        ATH_HYDRATION_NEVER_ATTEMPTED indefinitely while being actively
        watched -- the exact turtleneck outcome.  This sweep is driven by
        the candidate lifecycle instead, is bounded per tick, and honours
        the store's own backoff (``hydration_due``), so it can neither
        starve nor stampede the provider.
        """

        driven = 0
        try:
            tracked = (watchlist.tracked_entries()
                       if hasattr(watchlist, "tracked_entries")
                       else watchlist.active_entries())
        except Exception as sweep_exc:
            errors.log("ath_hydration_sweep", sweep_exc)
            return 0
        for entry in tracked:
            if driven >= max(0, int(limit)):
                break
            mint = getattr(entry, "token_mint", None)
            if not isinstance(mint, str) or not mint:
                continue
            try:
                # Every actively tracked candidate OWES a bounded hydration;
                # scheduling is idempotent, so this is also the repair path
                # for candidates admitted before the obligation existed.
                # The V3 pair hydrator additionally needs the AUTHENTICATED
                # migration pair identity: the watch entry's pair_address is
                # the pool the migrate_v2 proof validated, and that proof
                # (migration_admission) admits ONLY quote == WSOL, so the
                # base/quote identity registered here is proof-derived, never
                # guessed from a provider response.
                pair_address = getattr(entry, "pair_address", None)
                if isinstance(pair_address, str) and pair_address:
                    ath_store.register_migration_pair(
                        mint=mint,
                        pool_address=pair_address,
                        quote_mint=WSOL_MINT,
                        anchor_utc=getattr(
                            entry, "migration_time_utc", None))
                ath_store.schedule_hydration(
                    mint,
                    anchor_utc=getattr(entry, "migration_time_utc", None))
                if not ath_store.hydration_due(mint, now_utc=_utc_now_iso()):
                    continue
            except Exception as sweep_exc:
                errors.log("ath_hydration_sweep", sweep_exc)
                continue
            _drive_ath_hydration(mint)
            driven += 1
        migration_metrics["ath_hydration_sweeps"] += 1
        return driven

    def _sweep_authoritative_supply(limit: int = 8) -> int:
        """Bridge live-only admitted mints into central ATH before OHLCV."""

        if authoritative_supply_bridge is None or live_epoch_manager is None:
            return 0
        epoch = live_epoch_manager.snapshot()
        epoch_id = epoch.get("live_epoch_id")
        boundary = epoch.get("epoch_start_slot")
        try:
            tracked = (watchlist.tracked_entries()
                       if hasattr(watchlist, "tracked_entries")
                       else watchlist.active_entries())
        except Exception as supply_exc:
            errors.log("authoritative_supply_sweep", supply_exc)
            return 0
        driven = 0
        for entry in tracked:
            if driven >= max(0, int(limit)):
                break
            if not authoritative_supply_bridge.due(
                    getattr(entry, "token_mint", None)):
                continue
            try:
                authoritative_supply_bridge.observe_entry(
                    entry,
                    current_epoch_id=epoch_id,
                    first_eligible_slot=boundary,
                    timeout_seconds=timeout_seconds,
                )
                driven += 1
            except Exception as supply_exc:
                errors.log("authoritative_supply_sweep", supply_exc)
        return driven

    def _fetch_market_and_observe_risk(mint: str):
        # Every tail fetch (success OR miss) doubles as a free risk observation — the risk
        # layer never fetches anything itself.
        if market_scheduler is not None:
            market = market_scheduler.snapshot(mint)
            market = {
                **market,
                "fetched_at_utc": market.get("market_context_fetched_at_utc"),
                "market_provider": "SCHEDULED_PAID_PRIMARY",
            }
        else:
            market = market_transport.fetch_simple_market(
                mint, timeout_seconds=timeout_seconds)
        if isinstance(market, dict) and reserve_index.latest(mint) is not None:
            market = {
                **market,
                "pumpswap_reserve": reserve_index.compare_market(
                    mint, birdeye_price_usd=market.get("current_price")),
            }
        risk_engine.observe_market_sample(mint, market)
        _drive_ath_hydration(mint)
        # Baseline observation DECOUPLED from send authorization: the same
        # observation the run already paid for feeds the centralized watch
        # state, so security-blocked candidates still capture the immutable
        # migration baseline and can later prove the 1.20x crossing.  This
        # path never composes, reserves, mutates the ping ledger, or sends.
        try:
            observed = observe_watchlist_baseline(
                watchlist=watchlist, mint=mint, market=market,
                observation_source=activation_source_label,
                max_age_seconds=float(args.market_fresh_within_seconds),
                now_iso=_utc_now_iso(),
                on_activation_event=_record_activation_event)
            if observed and any(
                    event.get("event") == "BASELINE_CAPTURED"
                    for event in observed.get("events", ())):
                migration_metrics["baseline_observed_pre_authorization"] += 1
        except Exception as exc:
            errors.log("baseline_observation", exc)
        return market

    def _paper_snapshot_context(mint: str, security: Any = None,
                                entry_override: Any = None) -> Dict[str, Any]:
        entry = entry_override if entry_override is not None else watchlist.get(mint)
        pinned = tail.paper_positions().get(mint, {})
        contexts = [value for value in pinned.get("paper_position_contexts", [])
                    if isinstance(value, dict) and value.get("mint") == mint
                    and value.get("candidate_id")
                    and isinstance(value.get("activation"), dict)
                    and value["activation"].get("token_mint") == mint
                    and value["activation"].get("candidate_id") == value["candidate_id"]
                    and activation_proof_is_durable(value["activation"])]
        saved = contexts[0] if contexts else None
        risk = risk_engine.assess(mint)
        # Re-evaluate using already-owned evidence so a stale cached ALLOW
        # cannot authorize paper exposure. This makes no provider request.
        if security is None and (entry is not None or saved is not None):
            security = security_decision_fn(entry if entry is not None else
                                           SimpleNamespace(token_mint=mint))
        return {
            "paper_snapshot_version": "PHX2_PAPER_SNAPSHOT_V1",
            "candidate_id": (getattr(entry, "candidate_id", None)
                             or (saved or {}).get("candidate_id")),
            "migration_time_utc": (getattr(entry, "migration_time_utc", None)
                                   or (saved or {}).get("migration_time_utc")),
            "activation": entry.activation_snapshot() if entry is not None else {},
            "paper_position_context": saved,
            "paper_position_contexts": contexts,
            "canonical_volume_5m": canonical_volume.snapshot(mint),
            "risk_label": risk.get("risk_label"),
            "risk_reasons": risk.get("risk_reasons", []),
            "risk_assessed_at_utc": risk.get("risk_assessed_at_utc"),
            "scam_policy": security.to_dict() if hasattr(security, "to_dict") else {},
            "security_assessed_at_utc": _utc_now_iso() if security is not None else None,
        }

    tail = FreeTierPricingTail(
        out_dir=out_dir,
        fetch_market_fn=_fetch_market_and_observe_risk,
        now_epoch_fn=time.time,
        max_tracked=int(args.tail_max_tracked),
        max_tail_age_seconds=float(args.tail_max_age_seconds),
        min_poll_interval_seconds=float(args.tail_poll_interval_seconds),
        ath_store=ath_store,
        context_fn=_paper_snapshot_context,
        paper_state_file=getattr(args, "paper_state_file", None),
    )
    tail.sync_paper_positions()
    for entry in watchlist.active_entries():
        # Restored actives keep their paper pricing continuity across a restart.
        tail.track(entry.token_mint, origin=TAIL_ORIGIN_WATCHLIST)

    # ---- discovery (WS windows / cheap HTTP polling / hybrid) ----
    accepted_bound = min(10, max(1, int(args.max_accepted)))  # committed CaptureCaps bound [1,10]
    discovery_windows_path = Path(out_dir) / "discovery_windows.jsonl"
    provider_handoff_path = Path(out_dir) / "provider_handoff.jsonl"
    # Same serialized single-write discipline as activation_events.jsonl.
    # Handoff records are appended from the provider drain path, the candidate
    # pipeline and the discovery callback -- three writers on a file that was
    # still using the raw per-record open("a") appender. Windows emulates
    # O_APPEND as seek-then-write, so two racing handles can claim the same end
    # offset: the 2026-07-31 run left one torn trailing line as proof. One
    # instance, one lock, one os.write per complete record.
    provider_handoff_appender = SerializedJsonlAppender(provider_handoff_path)
    security_decisions_path = Path(out_dir) / "security_decisions.jsonl"

    def _record_provider_handoff(record: Dict[str, Any]) -> None:
        try:
            provider_handoff_appender.append(record)
        except SerializedJsonlAppendError as exc:
            # Disclosed, never silent: closed-set reason + underlying error
            # TYPE only (no record content) reach errors.jsonl / error_count.
            errors.log("provider_handoff_append", exc,
                       note=f"{exc.reason}:{exc.error_type}")

    migration_rejections_path = Path(out_dir) / MIGRATION_REJECTIONS_BASENAME
    last_discovery: Dict[str, Any] = {}
    non_pump_guard = {"dropped_total": 0}
    reseed_counter = {"n": 0}

    provider_dedupe: Optional[ProviderCandidateDedupe] = None
    paid_discovery: Optional[SingleGrpcPumpSwapDiscovery] = None
    stream_cursor_store: Optional[GrpcStreamCursorStore] = None
    transport_watermark_store: Optional[TransportWatermarkStore] = None
    migration_census_store: Optional[MigrationCensusStore] = None
    live_epoch_manager: Optional[LiveEpochManager] = None
    dex_restart_backfill: Optional[DexRestartBackfill] = None
    parity_monitor: Optional[Any] = None
    chainstack_shadow: Optional[Any] = None
    helius_byte_budget: Optional[HeliusByteBudget] = None
    continuity_tracker: Optional[SourceContinuityTracker] = None
    migration_journal: Optional[DurableMigrationJournal] = None
    dex_scheduled_epoch: Dict[str, Optional[str]] = {"id": None}
    if paid_mode:
        # SINGLE-STREAM topology: exactly one Yellowstone owner (the primary
        # migration/discovery/fee stream).  No liquidity-verifier object, no
        # dormant second connection, no verifier reconnect/watchdog state.
        try:
            provider_dedupe = ProviderCandidateDedupe(
                max_entries=int(args.provider_dedupe_max_entries))
            # PHX2-E2E-008: the durable stream cursor. It is bound to the
            # MEANING of the subscription (filter, commitment, program,
            # supported migration discriminators) so a changed subscription
            # cannot silently reuse a stale resume position. Endpoint and
            # token are deliberately not inputs: they are secrets, and
            # rotating one does not change what the stream means.
            # The cursor is DURABLE state, not a run artifact: it must survive
            # a fresh --out-dir and a process restart. --out-dir remains the
            # default only for backwards compatibility; the armed production
            # contract below refuses that choice outright.
            cursor_state_dir = str(
                getattr(args, "cursor_state_dir", None) or out_dir)
            Path(cursor_state_dir).mkdir(parents=True, exist_ok=True)
            if require_production_grpc or rpc_recovery_enabled or live_epoch_mode:
                # Single-owner state directory: the terminal-recovery operator
                # tool refuses a directory a live runtime owns, and a second
                # armed runtime cannot silently share one cursor. Released on
                # process exit; a stale (dead-pid) lock is reclaimed.
                from PHX2.free_tier_producer.rpc_gap_recovery import (
                    StateDirRuntimeLock,
                )
                runtime_state_lock = StateDirRuntimeLock(cursor_state_dir)
                if not runtime_state_lock.acquire():
                    print("[refused] STATE_DIR_RUNTIME_LOCK_HELD: another "
                          "PHX2 runtime owns the cursor state directory.")
                    return 2
                import atexit as _atexit
                _atexit.register(runtime_state_lock.release)
            if live_epoch_mode:
                process_start_utc = None
                try:
                    lock_text = runtime_state_lock.path.read_text(
                        encoding="utf-8").strip()
                    process_start_utc = lock_text.split("|", 1)[1]
                except (OSError, IndexError):
                    pass

                def _positive_pid(value: object) -> Optional[int]:
                    try:
                        parsed = int(str(value or "0"))
                    except ValueError:
                        return None
                    return parsed if parsed > 0 else None

                durable_identity = build_durable_policy_identity(
                    state_dir=cursor_state_dir,
                    cursor_state_dir=cursor_state_dir,
                    canonical_ledger_path=getattr(args, "ledger_path", None),
                    repo_head=getattr(args, "expected_head", None),
                    launcher_sha256=os.environ.get(
                        "PHX2_RUN_INSTANCE_LAUNCHER_SHA256"),
                    delivery_policy=(
                        "TELEGRAM_ONLY" if telegram_enabled
                        else "DISCORD_ONLY" if discord_enabled else "NO_SEND"),
                    telegram_enabled=telegram_enabled,
                    discord_enabled=discord_enabled,
                    structural_policy=phx1_structural_policy,
                    # The EFFECTIVE policy this process actually runs, not the
                    # canonical deployment value: a producer that ran something
                    # else must be visible as a mismatch, never normalized away.
                    alert_policy=alert_policy,
                    dex_backfill_enabled=dex_backfill_enabled,
                )
                run_identity = build_run_instance_identity(
                    producer_pid=os.getpid(),
                    process_start_utc=process_start_utc,
                    run_dir=out_dir,
                    startup_manifest_digest=os.environ.get(
                        "PHX2_RUN_INSTANCE_MANIFEST_SHA256"),
                    watchdog_pid=_positive_pid(os.environ.get(
                        "PHX2_RUN_INSTANCE_WATCHDOG_PID")),
                    launcher_wrapper_pid=os.getppid(),
                    runtime_nonce=(
                        os.environ.get("PHX2_RUN_INSTANCE_NONCE")
                        or uuid.uuid4().hex),
                )
                live_epoch_manager = LiveEpochManager(
                    state_dir=cursor_state_dir,
                    durable_policy_identity=durable_identity,
                    run_instance_identity=run_identity,
                )
                if live_epoch_manager.integrity_failure:
                    print("[refused] EPOCH_INTEGRITY_FAILURE: durable live epoch "
                          "state is invalid; historical replay remains retired.")
                    return 2
                # Every process epoch is a new, empty live-only eligibility
                # domain.  Authenticated checkpoint rows remain diagnostic
                # evidence with their original epoch/slot; none are rebound.
                _epoch_open = live_epoch_manager.snapshot()
                _restored_epoch = _epoch_open.get("live_epoch_id")
                if isinstance(_restored_epoch, str) and _restored_epoch:
                    physical_request_meter.set_runtime_identity(
                        epoch_id=_restored_epoch)
                    ath_store.bind_live_epoch(_restored_epoch)
                    _diagnostic = watchlist.begin_live_only_epoch(
                        _restored_epoch,
                        first_eligible_slot=_epoch_open.get(
                            "epoch_start_slot"),
                        opened_at_utc=_utc_now_iso(),
                    )
                    if _diagnostic:
                        print(f"watchlist: retained {_diagnostic} restored "
                              "records as diagnostics; live eligibility starts "
                              "empty for the current epoch")
            migration_census_store = MigrationCensusStore(
                state_dir=cursor_state_dir,
                artifact_dir=out_dir,
                watch_expiry_seconds=int(args.max_candidate_age_seconds),
            )
            migration_census_store.load()
            if migration_census_store.quarantined:
                print("[refused] authenticated migration census quarantined; "
                      "normal discovery did not start.")
                return 2

            # Helius and Chainstack have separate continuity histories.  A
            # prior control-source gap may never poison or be laundered into
            # the newly authoritative primary-source history.
            continuity_tracker = SourceContinuityTracker(
                state_path=Path(cursor_state_dir) / (
                    "helius_source_continuity.json"
                    if helius_primary else "source_continuity.json"
                )
            )
            continuity_tracker.load()

            # Durable migration-evidence journal + confirmed-slot cursor.
            # DURABLE state (next to the continuity document), never a run
            # artifact: it must survive a fresh --out-dir and a restart, and it
            # is evidence only -- it authorizes nothing and never touches the
            # paid ledger.
            migration_journal = DurableMigrationJournal(
                journal_path=Path(cursor_state_dir)
                / MIGRATION_JOURNAL_BASENAME,
                cursor_path=Path(cursor_state_dir)
                / MIGRATION_JOURNAL_CURSOR_BASENAME,
            )
            journal_verdict = migration_journal.load()
            print(f"[source] migration_journal_records="
                  f"{migration_journal.record_count} "
                  f"last_confirmed_slot={migration_journal.last_confirmed_slot} "
                  f"cursor_verdict={journal_verdict} "
                  f"malformed_lines={migration_journal.malformed_lines}")

            def _observe_primary_confirmed_slot(
                slot: int,
                observed_at_utc: str,
            ) -> bool:
                if live_epoch_manager is not None:
                    boundary_slot = slot
                    if helius_primary:
                        epoch = live_epoch_manager.snapshot()
                        if epoch.get("epoch_start_slot") is None:
                            # A tight migration-only subscription has no dense
                            # slot feed before its first live row.  Treat that
                            # first confirmed live receipt as H+1, never as
                            # historical startup replay, so the first genuine
                            # post-connect migration is not discarded merely
                            # to establish the epoch boundary.
                            boundary_slot = max(0, slot - 1)
                    if not live_epoch_manager.observe_confirmed_slot(
                        boundary_slot,
                        observed_at_utc=observed_at_utc,
                    ):
                        return False
                return True

            def _persist_live_migration(proof: Any) -> bool:
                assert migration_census_store is not None
                migration_census_store.register_migration(
                    proof,
                    discovery_source=(
                        DISCOVERY_SOURCE_LIVE_HELIUS
                        if helius_primary
                        else DISCOVERY_SOURCE_LIVE_GRPC
                    ),
                    first_seen_utc=getattr(proof, "observed_at_utc", None),
                )
                return True

            gap_recovery_coordinator = None
            if source_runtime_plan.construct_helius_source:
                assert helius_source_config is not None
                if source_runtime_plan.construct_parity_monitor:
                    from PHX2.free_tier_producer.helius_primary_parity import (
                        CANARY_PARITY_ROOT,
                        ChainstackShadowComparator,
                        ProductionParityMonitor,
                    )
                    parity_root = Path(CANARY_PARITY_ROOT)
                    parity_monitor = ProductionParityMonitor(
                        output_path=(
                            parity_root / Path(out_dir).name / "parity.jsonl"
                        ),
                        allowed_root=parity_root,
                        late_match_seconds=float(
                            getattr(
                                args,
                                "helius_parity_late_match_seconds",
                                30.0,
                            )
                        ),
                    )

                def _observe_helius_decoder(
                    record: Dict[str, object],
                ) -> None:
                    if parity_monitor is None:
                        return
                    continuity = continuity_tracker.snapshot()
                    parity_monitor.observe_helius_decoder(
                        record,
                        reconnect_count=int(
                            record.get("reconnect_count", 0) or 0
                        ),
                        gap_state=str(
                            continuity.get("continuity_state", "UNRESOLVED")
                        ),
                        recovery_state=str(
                            continuity.get("continuity_state", "NOT_REQUESTED")
                        ),
                    )

                def _observe_helius_recovery(outcome: object) -> None:
                    if parity_monitor is not None:
                        parity_monitor.observe_helius_recovery(outcome)

                helius_byte_budget = HeliusByteBudget(
                    int(
                        getattr(
                            args,
                            "helius_max_raw_bytes",
                            1_000_000_000,
                        )
                    )
                )
                live_source_factory = build_helius_primary_source_factory(
                    config=helius_source_config,
                    continuity=continuity_tracker,
                    decoder_observer=_observe_helius_decoder,
                    recovery_observer=_observe_helius_recovery,
                    confirmed_slot_observer=_observe_primary_confirmed_slot,
                    proof_store=proof_store,
                    census_sink=_persist_live_migration,
                    byte_budget=helius_byte_budget,
                    journal=migration_journal,
                )
                paid_discovery = SingleGrpcPumpSwapDiscovery(
                    source_factory=live_source_factory,
                    dedupe=provider_dedupe,
                    admission_inbox=admission_inbox,
                    require_cursor_aware_factory=False,
                    queue_max=int(args.queue_pressure_max),
                    stale_after_seconds=float(args.grpc_stale_after_seconds),
                    reconnect_backoff_seconds=float(
                        args.grpc_reconnect_backoff_seconds
                    ),
                    event_sink=_record_provider_handoff,
                    live_epoch_manager=live_epoch_manager,
                    continuity=continuity_tracker,
                    source_owned_gap_recovery=True,
                )
                if source_runtime_plan.construct_chainstack_comparator:
                    assert parity_monitor is not None
                    chainstack_shadow = ChainstackShadowComparator(
                        monitor=parity_monitor
                    )
            elif source_runtime_plan.construct_chainstack_source:
                subscription_identity_digest = (
                    compute_subscription_identity_digest(
                        source_kind=STREAM_SOURCE_YELLOWSTONE,
                        commitment="CONFIRMED",
                        transaction_filter_name=(
                            STAGE29_3_TRANSACTION_FILTER_NAME
                        ),
                        account_include=[PUMPSWAP_PROGRAM_ID],
                        program_id=PUMPSWAP_PROGRAM_ID,
                        migration_versions_supported=MIGRATION_VERSIONS,
                        decoder_schema_version=STREAM_CURSOR_SCHEMA_V1,
                    )
                )
                stream_cursor_store = build_cursor_store(
                    state_dir=cursor_state_dir,
                    subscription_identity_digest=subscription_identity_digest,
                    persist_batch_max_events=int(
                        getattr(
                            args,
                            "cursor_persist_batch_max_events",
                            32,
                        )
                    ),
                    persist_batch_max_seconds=float(
                        getattr(
                            args,
                            "cursor_persist_batch_max_seconds",
                            0.5,
                        )
                    ),
                    basename=(
                        LIVE_EPOCH_CURSOR_BASENAME
                        if live_epoch_mode
                        else "grpc_stream_cursor.json"
                    ),
                )
                cursor_load = stream_cursor_store.load()
                if stream_cursor_store.quarantined:
                    print(
                        "[degraded] gRPC stream cursor quarantined "
                        f"({cursor_load.checkpoint_quarantine_reason}); "
                        "discovery coverage is unproven until an operator "
                        "resolves it."
                    )
                    if live_epoch_mode:
                        print("[refused] LIVE_EPOCH_CURSOR_INTEGRITY_FAILURE")
                        return 2
                transport_watermark_store = TransportWatermarkStore(
                    state_dir=cursor_state_dir
                )
                transport_watermark_store.load()
                if transport_watermark_store.quarantined:
                    print(
                        "[refused] authenticated transport watermark "
                        "quarantined; the transaction cursor was not touched."
                    )
                    return 2

                def _persist_transport_slot(
                    slot: int,
                    observed_at_utc: str,
                ) -> bool:
                    assert transport_watermark_store is not None
                    continuity_tracker.note_slot(
                        slot,
                        processed=True,
                        durable=True,
                    )
                    if not _observe_primary_confirmed_slot(
                        slot,
                        observed_at_utc,
                    ):
                        return False
                    return transport_watermark_store.observe_confirmed_slot(
                        slot,
                        observed_at_utc=observed_at_utc,
                    )

                def _persist_canonical_reserve(
                    payload: Dict[str, Any],
                ) -> bool:
                    assert migration_census_store is not None
                    result = migration_census_store.observe_canonical_reserve(
                        mint=str(payload["mint"]),
                        pool=str(payload["pool_address"]),
                        slot=int(payload["slot"]),
                        observed_at_utc=str(payload["source_timestamp"]),
                        raw_quote_reserves=payload["raw_quote_reserves"],
                        virtual_quote_reserves=payload[
                            "virtual_quote_reserves"
                        ],
                        effective_quote_reserves_value=payload[
                            "effective_quote_reserves"
                        ],
                        base_reserves=payload["base_reserves"],
                        base_supply=payload["base_supply"],
                        base_decimals=int(payload["base_decimals"]),
                        quote_decimals=int(payload["quote_decimals"]),
                        source_evidence_digest=str(
                            payload["source_evidence_digest"]
                        ),
                    )
                    accepted = bool(result.get("accepted")) or (
                        result.get("reason")
                        in (
                            "TRACKER_TERMINAL",
                            "AFTER_WATCH_DEADLINE",
                            "DUPLICATE_RESERVE_OBSERVATION",
                        )
                    )
                    if not accepted:
                        raise MigrationCensusError(
                            str(
                                result.get("reason")
                                or "RESERVE_OBSERVER_REFUSED"
                            )
                        )
                    return True

                reserve_index.add_canonical_reserve_observer(
                    _persist_canonical_reserve
                )
                live_source_factory = build_live_source_factory(
                    reserve_index=reserve_index,
                    fee_index=fee_index,
                    admission_config=migration_admission_config,
                    admission_sink=lambda record: _append_jsonl(
                        migration_rejections_path,
                        record,
                    ),
                    proof_store=proof_store,
                    transport_slot_observer=_persist_transport_slot,
                    census_sink=_persist_live_migration,
                )
                if require_production_grpc:
                    verdict = evaluate_production_grpc_contract(
                        provider_mode=provider_mode,
                        paid_provider_modes=(
                            PROVIDER_MODE_PAID_PRIMARY,
                            PROVIDER_MODE_PAID_WITH_FALLBACK,
                        ),
                        cursor_store=stream_cursor_store,
                        cursor_state_dir=cursor_state_dir,
                        out_dir=out_dir,
                        source_factory=live_source_factory,
                        discovery_mode=discovery_mode,
                        fallback_discovery_enabled=(
                            provider_mode
                            == PROVIDER_MODE_PAID_WITH_FALLBACK
                        ),
                        expected_head=getattr(args, "expected_head", None),
                        gap_recovery_mode=gap_recovery_mode,
                    )
                    print(
                        "production grpc contract: "
                        f"{'ALLOWED' if verdict.allowed else 'REFUSED'} "
                        f"refusals={verdict.refusals}"
                    )
                    verdict.raise_if_refused()
                if rpc_recovery_enabled:
                    recovery_store = RpcGapRecoveryStore(
                        state_dir=cursor_state_dir
                    )
                    recovery_load = recovery_store.load()
                    if recovery_store.quarantined:
                        print(
                            "[degraded] rpc gap-recovery state quarantined "
                            f"({recovery_load.checkpoint_quarantine_reason}); "
                            "recovery cannot resume until an operator "
                            "resolves it."
                        )
                    quarantine_buffer = QuarantinedLiveBuffer(
                        state_dir=cursor_state_dir,
                        subscription_identity_digest=(
                            subscription_identity_digest
                        ),
                        max_events=gap_recovery_config.max_quarantine_events,
                        max_bytes=gap_recovery_config.max_quarantine_bytes,
                        max_age_seconds=(
                            gap_recovery_config.max_quarantine_age_seconds
                        ),
                    )
                    quarantine_buffer.load()
                    gap_recovery_coordinator = RpcGapBackfillCoordinator(
                        config=gap_recovery_config,
                        recovery_store=recovery_store,
                        quarantine_buffer=quarantine_buffer,
                        subscription_identity_digest=(
                            subscription_identity_digest
                        ),
                        rpc_post_fn=build_rpc_transport_from_env(),
                        reserve_index=reserve_index,
                        fee_index=fee_index,
                        admission_config=migration_admission_config,
                        admission_sink=lambda record: _append_jsonl(
                            migration_rejections_path,
                            record,
                        ),
                        proof_store=proof_store,
                    )
                paid_discovery = SingleGrpcPumpSwapDiscovery(
                    source_factory=live_source_factory,
                    dedupe=provider_dedupe,
                    admission_inbox=admission_inbox,
                    require_cursor_aware_factory=require_production_grpc,
                    queue_max=int(args.queue_pressure_max),
                    stale_after_seconds=float(args.grpc_stale_after_seconds),
                    reconnect_backoff_seconds=float(
                        args.grpc_reconnect_backoff_seconds
                    ),
                    event_sink=_record_provider_handoff,
                    cursor_store=stream_cursor_store,
                    gap_recovery=gap_recovery_coordinator,
                    live_epoch_manager=live_epoch_manager,
                    continuity=continuity_tracker,
                )
            if dex_backfill_enabled:
                dex_restart_backfill = DexRestartBackfill(
                    event_sink=_record_provider_handoff,
                    cursor_path=(
                        Path(cursor_state_dir) / "dex_backfill_cursor.json"
                        if cursor_state_dir else None))
        except ProductionContractError as exc:
            # The closed-set refusal list is safe to print verbatim: it names
            # contract violations only, never a path, endpoint or credential.
            print(f"[refused] {exc}")
            return 2
        except SourceFactoryContractError as exc:
            print(f"[refused] {exc}")
            return 2
        except Exception as exc:
            print(f"[refused] paid gRPC readiness failed ({type(exc).__name__}); "
                  "no stream opened; values never printed.")
            return 2

    def _migration_admission_snapshot(base: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return {
            **dict(base or {}),
            **proof_store.stats(),
            "baseline_observed_pre_authorization": int(
                migration_metrics["baseline_observed_pre_authorization"]),
            "legacy_lp_state": legacy_lp_state,
        }

    # Static single-stream verifier view: DISABLED, zero streams, zero
    # capacity.  Present in telemetry so status surfaces stay explicit about
    # the removed role rather than silently dropping it.
    _DISABLED_VERIFIER_SNAPSHOT: Dict[str, Any] = {
        "role": "LIQUIDITY_VERIFIER",
        "status": VERIFIER_STREAM_STATUS_DISABLED,
        "active_streams": 0,
        "max_active_streams": 0,
        "stream_capacity": VERIFIER_STREAM_MAX,
    }

    def _provider_snapshot() -> Dict[str, Any]:
        if paid_discovery is None:
            return {
                "provider_mode": PROVIDER_MODE_FREE_TIER,
                "provider": "FREE_TIER",
                "status": "ACTIVE",
                "active_streams": 0,
                "max_active_streams": 0,
                "stream_capacity": 0,
                "fallback_active": False,
                "lp_integrity_mode": LP_INTEGRITY_MODE,
                "verifier_stream_status": VERIFIER_STREAM_STATUS_DISABLED,
                "pipeline_counters": dict(pipeline_counters),
                "canonical_volume": canonical_volume.stats(),
                "pumpswap_reserves": reserve_index.stats(),
                "token_metadata": token_metadata.stats(),
                "migration_admission": _migration_admission_snapshot(),
            }
        primary = paid_discovery.snapshot()
        snap = dict(primary)
        primary_active = int(primary.get("active_streams") or 0)
        primary_max = int(primary.get("max_active_streams") or 0)
        snap.update({
            "primary": primary,
            "verifier": dict(_DISABLED_VERIFIER_SNAPSHOT),
            "primary_active_streams": primary_active,
            "verifier_active_streams": 0,
            "total_active_streams": primary_active,
            "primary_max_active_streams": primary_max,
            "verifier_max_active_streams": 0,
            "total_max_active_streams": primary_max,
            "primary_stream_max": PRIMARY_STREAM_MAX,
            "verifier_stream_max": VERIFIER_STREAM_MAX,
            "max_active_streams_allowed": MAX_ACTIVE_STREAMS,
            "primary_stream_status": primary.get("status"),
            "verifier_stream_status": VERIFIER_STREAM_STATUS_DISABLED,
            "lp_integrity_mode": LP_INTEGRITY_MODE,
        })
        snap["provider_mode"] = provider_mode
        snap["migration_source_mode"] = source_selection.mode
        snap.update(source_runtime_plan.status_projection())
        snap["fallback_active"] = bool(
            not helius_primary
            and
            provider_mode == PROVIDER_MODE_PAID_WITH_FALLBACK
            and paid_discovery.needs_fallback())
        snap["fee_evidence"] = fee_index.stats()
        snap["fee_lifecycle"] = fee_lifecycle_index.stats()
        snap["security_filters"] = security_index.summary()
        snap["canonical_volume"] = canonical_volume.stats()
        snap["pumpswap_reserves"] = reserve_index.stats()
        snap["authenticated_fresh_market_fallback"] = (
            fresh_market_fallback.stats()
            if fresh_market_fallback is not None else {
                "fresh_fallback_capability_available": False})
        snap["token_metadata"] = token_metadata.stats()
        snap["pipeline_counters"] = dict(pipeline_counters)
        snap["migration_admission"] = _migration_admission_snapshot(
            snap.get("migration_admission")
            if isinstance(snap.get("migration_admission"), dict) else None)
        snap["transport_watermark"] = (
            transport_watermark_store.snapshot()
            if transport_watermark_store is not None else None)
        snap["migration_census"] = (
            migration_census_store.summary()
            if migration_census_store is not None else None)
        snap["production_mode"] = (
            LIVE_EPOCH_PRODUCTION_MODE if live_epoch_mode
            else snap.get("production_mode"))
        snap["primary_runtime_mode"] = (
            "LIVE_EPOCH_HELIUS_PRIMARY"
            if live_epoch_mode and helius_primary
            else snap.get("production_mode")
        )
        snap["historical_completeness_required"] = not live_epoch_mode
        snap["historical_rpc_backfill_enabled"] = rpc_recovery_enabled
        snap["historical_recovery_status"] = (
            HISTORICAL_REPLAY_STATUS if live_epoch_mode else None)
        snap["historical_recovery_document_state"] = (
            "RETIRED_AUDIT_ONLY" if live_epoch_mode else None)
        snap["dexscreener_restart_backfill_enabled"] = dex_backfill_enabled
        backfill_snapshot = (
            dex_restart_backfill.snapshot()
            if dex_restart_backfill is not None else None)
        snap["dexscreener_restart_backfill"] = backfill_snapshot
        # ---- continuous-discovery status (one honest projection) ----------
        # Live-source continuity, durable cursor slot, last migration-journal
        # commit, detected gaps, recovered ranges, curated rows examined,
        # curated candidates admitted, and the coverage limitations that are
        # ALWAYS true of this architecture -- each exposed separately so no
        # reader can infer six-hour completeness from a green status.
        snap["migration_journal"] = (
            migration_journal.snapshot()
            if migration_journal is not None else None)
        primary_status = str(primary.get("status") or "")
        snap["continuous_discovery"] = build_discovery_status(
            transport_connected=bool(primary.get("transport_connected")),
            reconnecting=primary_status in ("RECONNECTING", "CONNECTING"),
            authentication_failed=primary_status == "AUTH_FAILED",
            stopped=primary_status in ("STOPPED", "FAILED"),
            continuity_snapshot=(
                continuity_tracker.snapshot()
                if continuity_tracker is not None else None),
            journal_snapshot=snap["migration_journal"],
            backfill_snapshot=backfill_snapshot,
            backfill_enabled=bool(dex_backfill_enabled),
            reconnect_snapshot=(
                primary.get("reconnect_policy")
                if isinstance(primary.get("reconnect_policy"), dict) else None),
        ).to_record()
        snap["helius_credit_projection"] = projection_report()
        shadow_snapshot = (
            chainstack_shadow.snapshot()
            if chainstack_shadow is not None
            else {
                "source": "DISABLED",
                "state": "DISABLED",
                "candidate_authority": False,
                "canonical_state_authority": False,
                "source_recovery_authority": False,
                "send_authority": False,
                "reservation_authority": False,
                "ledger_authority": False,
            }
        )
        snap["shadow_source"] = (
            shadow_snapshot["source"]
            if chainstack_shadow is not None
            else source_runtime_plan.shadow_source
        )
        snap["shadow_state"] = shadow_snapshot["state"]
        snap["shadow"] = shadow_snapshot
        snap["chainstack_connected"] = bool(
            (
                source_runtime_plan.primary_source == "CHAINSTACK"
                and primary.get("status") == "CONNECTED"
            )
            or (
                chainstack_shadow is not None
                and shadow_snapshot.get("state") == "CONNECTED"
            )
        )
        snap["parity"] = (
            parity_monitor.snapshot()
            if parity_monitor is not None
            else {
                "state": "DISABLED",
                "source": "DISABLED",
                "loaded_from_prior_run": False,
                "records": 0,
                "matches": 0,
                "chainstack_only": 0,
                "helius_only": 0,
                "slot_mismatches": 0,
                "decode_mismatches": 0,
                "late_matches": 0,
                "recovered_by_helius_http": 0,
                "unresolved": 0,
                "stop_reason": None,
            }
        )
        snap["helius_byte_budget"] = (
            helius_byte_budget.snapshot()
            if helius_byte_budget is not None else None
        )
        if helius_primary and helius_byte_budget is not None:
            snap["primary_estimated_credits"] = (
                snap["helius_byte_budget"]["estimated_credits"]
            )
        return snap

    def _market_readiness_snapshot() -> Dict[str, Any]:
        return market_readiness.snapshot() if market_readiness is not None else {}

    reconnect_storm_window = ReconnectStormWindow()

    def _assert_provider_safety() -> None:
        snap = _provider_snapshot()
        refusal = paid_provider_safety_error(
            snap, max_reconnects=int(args.grpc_max_reconnects_before_stop),
            reconnects_in_window=reconnect_storm_window.observe(
                snap.get("reconnects")))
        if refusal is not None:
            raise RuntimeError(refusal)
        if int(snap.get("verifier_max_active_streams") or 0) > VERIFIER_STREAM_MAX:
            raise RuntimeError("LIQUIDITY_VERIFIER_STREAM_FORBIDDEN")
        if int(snap.get("total_active_streams") or 0) > MAX_ACTIVE_STREAMS:
            raise RuntimeError("TOTAL_GRPC_STREAM_CAP_EXCEEDED")
        if parity_monitor is not None:
            parity_stop = parity_monitor.stop_reason()
            if parity_stop is not None:
                raise RuntimeError(f"PARITY_STOP_{parity_stop}")
        if helius_byte_budget is not None and helius_byte_budget.reached:
            raise RuntimeError("HELIUS_BYTE_CEILING_REACHED")

    poller: Optional[FreeTierPollingDiscovery] = None
    polling_needed = _polling_required(provider_mode, discovery_mode)
    if polling_needed:
        poller = FreeTierPollingDiscovery(
            rpc_url=url,
            caps=FreeTierPollingCaps(
                max_pools_per_poll=int(args.poll_pools_per_cycle),
                sig_page_limit=int(args.poll_sig_page_limit),
                max_gettransaction_per_poll=int(args.poll_max_gettransaction_per_cycle),
                max_pool_age_seconds=int(args.poll_max_pool_age_seconds)),
            timeout_seconds=float(args.market_timeout_seconds),
            state_path=str(Path(out_dir) / POLLING_SEEN_BASENAME))
        print(f"polling discovery: pools_per_cycle<={args.poll_pools_per_cycle} "
              f"sig_page_limit={args.poll_sig_page_limit} "
              f"gettransaction_per_cycle<={args.poll_max_gettransaction_per_cycle} "
              f"pool_age<={args.poll_max_pool_age_seconds}s (keyless listing + surgical RPC; "
              f"actual mint always extracted from the create_pool tx)")

    def _record_discovery_window(window: Dict[str, Any]) -> None:
        last_discovery.clear()
        last_discovery.update(window)
        try:
            if artifacts.scan_value_safe(json.dumps(window, sort_keys=True)):
                _append_jsonl(discovery_windows_path, window)
        except Exception as exc:
            errors.log("discovery_window_record", exc)

    def _apply_pump_guard(raw_candidates: object,
                          source_label: str) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        # STRICT pump-suffix guard at the discovery -> watchlist boundary: applied to the
        # ACTUAL extracted token mint immediately after extraction, BEFORE budget candidate
        # accounting, watchlist seeding, market enrichment, paper artifact streams, or any
        # would_ping/private_ping eligibility — identical for WS and POLLING sources.
        candidates, guard_dropped = guard_pump_suffix_candidates(raw_candidates)
        if guard_dropped:
            non_pump_guard["dropped_total"] += len(guard_dropped)
            for _d in guard_dropped:
                print(f"[seed] {NON_PUMP_GUARD_REASON}: dropped pre-watchlist ({source_label}) "
                      f"mint={str(_d.get('token_mint'))[:48]!r}")
        # Shared-dedupe invariant: a candidate is tested against the ONE shared
        # ProviderCandidateDedupe instance exactly once. Paid-provider
        # candidates were already admitted through it at the provider boundary
        # (paid_provider._admit_candidate, keyed on provider_event_id + mint)
        # and carry provider_dedupe_applied=True; re-testing them here rejects
        # every one as DUPLICATE_MINT, because the mint check hits the entry
        # that the earlier acceptance recorded and the event-id check misses
        # (source_ref is not provider_event_id). WS, POLLING and any other
        # candidate that never reached the provider boundary carries no stamp
        # and still gets its ONE required pass. The decision is read off the
        # candidate itself, never off source_label -- a source rename (the
        # "GRPC" -> "HELIUS" cutover) must not be able to change dedupe
        # topology again.
        candidates = apply_provider_dedupe_once(candidates, provider_dedupe)
        for cand in candidates:
            # Paper pricing continuity: every guard-accepted mint gets tailed from seed time.
            covered = tail.track(str(cand.get("token_mint") or ""), origin=TAIL_ORIGIN_WATCHLIST)
            cand["paper_pricing_admission"] = "ADMITTED" if covered else "CAPACITY_UNAVAILABLE"
            # Seed-time risk context (migration time + polling creation-page sig count).
            risk_engine.observe_seed(
                str(cand.get("token_mint") or ""),
                migration_time_utc=cand.get("migration_time_utc"),
                discovery_source=source_label,
                discovery_sig_count=cand.get("discovery_sig_count"))
        return candidates, guard_dropped

    def _ws_window_discover() -> List[Dict[str, Any]]:
        # Per-window caps are SHRUNK to the remaining cumulative budget BEFORE the WS is opened;
        # an exhausted discovery budget opens nothing and ends the run at this tick's boundary.
        allowance = budget.window_allowance(
            per_window_notifications=int(args.max_notifications),
            per_window_gettransaction=int(args.max_gettransaction))
        if allowance is None:
            print(f"[seed] SKIPPED_BY_BUDGET reason={budget.stop_reason}")
            return []
        window_caps = CaptureCaps(
            max_runtime_seconds=float(args.max_seed_runtime),
            max_logs_notifications=int(allowance["max_notifications"]),
            max_gettransaction_fetches=int(allowance["max_gettransaction"]),
            max_seed=accepted_bound, max_accepted_evidence=accepted_bound)
        try:
            disc = b30s._discover_candidates(key=key, url=url, caps=window_caps)
        except Exception as exc:
            errors.log("discovery", exc)
            raise
        candidates, guard_dropped = _apply_pump_guard(disc.get("candidates"), "WS")
        stats = dict(disc.get("stats") or {})
        budget.record_window(stats, accepted=len(candidates))
        window = {
            "kind": "FREE_TIER_DISCOVERY_WINDOW",
            "discovery_source": "WS",
            "discovery_mode": discovery_mode_display,
            "window_ended_at_utc": _utc_now_iso(),
            "evidence_record_count": disc.get("evidence_record_count"),
            "accepted_candidates": len(candidates),
            "non_pump_guard_dropped": len(guard_dropped),
            "non_pump_guard_dropped_mints": [
                str((_d or {}).get("token_mint"))[:64] for _d in guard_dropped[:10]],
            **{k: v for k, v in stats.items()
               if isinstance(v, (int, bool, str)) or v is None},
        }
        _record_discovery_window(window)
        if stats.get("ws_error"):
            # The committed capture converts WS faults into an EMPTY window (no raise), which the
            # loop treats as a quiet market. Surface it in errors.jsonl so a dead/throttled WS is
            # never mistaken for silence (closed-set reason only).
            errors.log("discovery_ws", RuntimeError(),
                       note=str(stats.get("ws_error_reason") or "WS_ERROR"))
        print(f"[seed] WS notifications_seen={stats.get('notifications_seen')} "
              f"create_pool_candidates={stats.get('candidates')} "
              f"tx_fetches={stats.get('gettransaction_fetches')} "
              f"evidence_records={disc.get('evidence_record_count')} "
              f"accepted={len(candidates)} "
              f"non_pump_guard_dropped={len(guard_dropped)} "
              f"ws_error={stats.get('ws_error', False)} "
              f"| budget windows={budget.seed_windows}/{budget.caps.max_seed_windows} "
              f"raw_ws={budget.ws_notifications_seen}/{budget.caps.max_raw_ws_notifications_total} "
              f"(raw msgs, not credits) "
              f"gtx={budget.gettransaction_fetches}/{budget.caps.max_gettransaction_total} "
              f"cand={budget.candidates_accepted}/{budget.caps.max_candidates_total}")
        return candidates

    def _polling_discover() -> List[Dict[str, Any]]:
        allowance = budget.polling_allowance(
            per_poll_gettransaction=int(args.poll_max_gettransaction_per_cycle))
        if allowance is None:
            print(f"[seed] POLL_SKIPPED_BY_BUDGET reason={budget.stop_reason}")
            return []
        try:
            disc = poller.poll(created_at_utc=_utc_now_iso(),
                               max_gettransaction_allowance=allowance["max_gettransaction"])
        except Exception as exc:
            errors.log("polling_discovery", exc)
            raise
        candidates, guard_dropped = _apply_pump_guard(disc.get("candidates"), "POLLING")
        stats = dict(disc.get("stats") or {})
        budget.record_poll(stats, accepted=len(candidates), guard_dropped=len(guard_dropped))
        window = {
            "kind": "FREE_TIER_DISCOVERY_WINDOW",
            "discovery_source": "POLLING",
            "discovery_mode": discovery_mode_display,
            "window_ended_at_utc": _utc_now_iso(),
            "evidence_record_count": disc.get("evidence_record_count"),
            "accepted_candidates": len(candidates),
            "non_pump_guard_dropped": len(guard_dropped),
            "non_pump_guard_dropped_mints": [
                str((_d or {}).get("token_mint"))[:64] for _d in guard_dropped[:10]],
            **{k: v for k, v in stats.items()
               if isinstance(v, (int, bool, str)) or v is None},
        }
        _record_discovery_window(window)
        print(f"[seed] POLLING pools_listed={stats.get('pools_listed')} "
              f"pools_new={stats.get('pools_new')} "
              f"sigs_seen={stats.get('signatures_seen')} sigs_new={stats.get('signatures_new')} "
              f"tx_fetched={stats.get('transactions_fetched')} "
              f"create_pool_candidates={stats.get('create_pool_candidates')} "
              f"accepted={len(candidates)} non_pump_guard_dropped={len(guard_dropped)} "
              f"errors={stats.get('polling_errors')} 429={stats.get('polling_429')} "
              f"| budget polls={budget.poll_count}/{budget.caps.max_polls_total} "
              f"gtx={budget.gettransaction_fetches}/{budget.caps.max_gettransaction_total} "
              f"cand={budget.candidates_accepted}/{budget.caps.max_candidates_total}")
        return candidates

    def _service_live_epoch_boundary() -> None:
        if live_epoch_manager is None:
            return
        for closed in live_epoch_manager.drain_closed_epochs():
            epoch_id = closed.get("live_epoch_id")
            closed_at = closed.get("closed_at_utc") or _utc_now_iso()
            if isinstance(epoch_id, str) and epoch_id:
                watchlist.close_live_epoch(
                    epoch_id, closed_at_utc=str(closed_at))
        epoch = live_epoch_manager.snapshot()
        epoch_id = epoch.get("live_epoch_id")
        if isinstance(epoch_id, str) and epoch_id:
            physical_request_meter.set_runtime_identity(epoch_id=epoch_id)
            ath_store.bind_live_epoch(epoch_id)
            watchlist.begin_live_only_epoch(
                epoch_id,
                first_eligible_slot=epoch.get("epoch_start_slot"),
                opened_at_utc=_utc_now_iso(),
            )
            watchlist.close_live_epochs_except(
                epoch_id, closed_at_utc=_utc_now_iso())
        if dex_restart_backfill is not None:
            if isinstance(epoch_id, str) and epoch_id:
                # One scheduler entry point for both sweep kinds: the first
                # call per epoch starts STARTUP_RECOVERY (bounded six-hour
                # scan), later calls start PERIODIC_SAFETY_NET sweeps on the
                # bounded cadence.  Single-flight and failure backoff live
                # inside the backfill owner; a refused start is a normal
                # NOT_DUE / SWEEP_IN_FLIGHT tick, not an error.
                started, _sweep_kind = (
                    dex_restart_backfill.maybe_schedule_periodic(epoch_id))
                if started:
                    dex_scheduled_epoch["id"] = epoch_id

    def discovery_fn() -> List[Dict[str, Any]]:
        reseed_counter["n"] += 1
        if paid_discovery is not None:
            _service_live_epoch_boundary()
            for corroboration in paid_discovery.drain_corroborations(
                    max_candidates=int(args.queue_pressure_max)):
                watchlist.corroborate(corroboration)
            _assert_provider_safety()
            # PHX2-E2E-006: a genuine candidate burst is admitted in ONE
            # discovery pass (bounded chunks, no sleeps between them), not
            # quantized to 10 per 45-second watch tick.  Active-watch
            # capacity, mint dedupe and budget caps are all enforced
            # downstream exactly as before.
            raw_primary = drain_provider_handoff_completely(
                paid_discovery, chunk_size=accepted_bound)
            if live_epoch_manager is not None:
                _admission_epoch = live_epoch_manager.snapshot()
                _admission_epoch_id = _admission_epoch.get("live_epoch_id")
                if isinstance(_admission_epoch_id, str):
                    watchlist.update_live_only_epoch_boundary(
                        _admission_epoch_id,
                        _admission_epoch.get("epoch_start_slot"))
            if market_scheduler is not None and raw_primary:
                market_scheduler.note_handoff(drained=len(raw_primary))
            primary, _ = _apply_pump_guard(
                raw_primary,
                "HELIUS" if helius_primary else "GRPC",
            )
            collected = list(primary)
            dex_candidates: List[Dict[str, Any]] = []
            if dex_restart_backfill is not None:
                for candidate in dex_restart_backfill.drain(
                        max_candidates=int(args.queue_pressure_max)):
                    # Canonical metadata harvest for EVERY drained candidate —
                    # seeded, corroborated, or dedupe-suppressed — so a dex
                    # rediscovery of a live-admitted mint still contributes
                    # its name/ticker (2026-07-28 metadata remediation).
                    # ``symbol_or_name`` is a fallback that may hold the NAME;
                    # it counts as a ticker only when it differs from the name.
                    fallback_symbol = candidate.get("symbol_or_name")
                    if fallback_symbol == candidate.get("token_name"):
                        fallback_symbol = None
                    _harvest_token_metadata(
                        candidate.get("token_mint"),
                        token_name=candidate.get("token_name"),
                        token_symbol=(candidate.get("token_symbol")
                                      or fallback_symbol),
                        source="DEXSCREENER_RESTART_BACKFILL")
                    # DEX restart history is evidence only in live-only mode.
                    # It does not consume provider dedupe, watch capacity, ATH
                    # hydration, or current-epoch eligibility; a later Helius
                    # proof for the mint therefore remains independently
                    # admissible.
                    watchlist.record_dex_diagnostic(candidate)
                    dex_candidates.append(candidate)
            budget.record_provider_candidates(len(primary) + len(dex_candidates))
            fallback_active = (
                provider_mode == PROVIDER_MODE_PAID_WITH_FALLBACK
                and paid_discovery.needs_fallback()
            )
            if fallback_active:
                # Existing keyless polling is invoked only while the sole gRPC
                # owner reports connecting/reconnecting/stale/stopped. Shared
                # signature+mint dedupe prevents a fallback rediscovery from
                # becoming a second candidate.
                collected.extend(_polling_discover())
            window = {
                "kind": "PAID_PROVIDER_DISCOVERY_WINDOW",
                "discovery_source": (
                    "HELIUS_PRIMARY" if helius_primary else "GRPC_PRIMARY"
                ),
                "discovery_mode": provider_mode,
                "window_ended_at_utc": _utc_now_iso(),
                "accepted_candidates": len(collected),
                "dex_backfill_candidates": len(dex_candidates),
                "fallback_active": fallback_active,
                "provider_telemetry": _provider_snapshot(),
            }
            _record_discovery_window(window)
            return collected
        # route_discovery holds the hard invariant: polling-only NEVER opens a WS; hybrid opens a
        # WS window only every Nth reseed while the raw-WS/seed-window budget remains.
        return route_discovery(
            discovery_mode=discovery_mode,
            reseed_index=reseed_counter["n"],
            ws_window_every_n_reseeds=int(args.ws_window_every_n_reseeds),
            ws_discover_fn=_ws_window_discover,
            poll_discover_fn=_polling_discover,
            ws_budget_remaining=budget.raw_ws_remaining(),
            ws_windows_open=budget.seed_windows,
            max_seed_windows=budget.caps.max_seed_windows,
            on_ws_skipped=lambda: print(
                "[seed] HYBRID: WS window skipped (raw WS budget spent) — polling continues."))

    # ---- artifact callbacks ----
    would_ping_path = Path(out_dir) / WOULD_PING_BASENAME
    ping_quality_review_path = Path(out_dir) / PING_QUALITY_REVIEW_BASENAME
    def security_decision_fn(entry: Any):
        # SINGLE-STREAM security decision: PHX1 Fee Gate lifecycle only.  No
        # LP Integrity classification exists — no verifier state, no rolling
        # liquidity evidence, no canonical-pool snapshot requirement, and no
        # synthetic LP verdict standing in for any of them.
        now_epoch = int(time.time())
        fee_snapshot = fee_index.snapshot(
            entry.token_mint,
            now_epoch=now_epoch,
            max_age_seconds=Decimal(str(args.market_fresh_within_seconds)),
        )
        # Lifecycle fold: stale/immature evidence blocks the current send
        # while the candidate stays tracked (proof, baseline, ATH, activation,
        # paper and dashboard state all continue); only a confirmed durable
        # lock re-stamps the snapshot as the sticky hard block.  The
        # historical LP-removal severe proof no longer exists in single-stream
        # mode, so a durable lock requires the full fee-confirmation policy.
        lifecycle_view = fee_lifecycle_index.observe(
            fee_snapshot, now_epoch=now_epoch, severe_structural_proof=False)
        decision = evaluate_delivery_safety(
            fee_snapshot=lifecycle_view.effective_snapshot,
            existing_block_reasons=lifecycle_view.send_block_reasons,
            phx1_structural_policy=phx1_structural_policy)
        security_index.bind(decision)
        return decision

    def on_security_record(*, entry: Any, decision: Any, reason: Any, tick: int) -> None:
        mint = getattr(entry, "token_mint", None)
        record = build_security_artifact_record(
            entry=entry, decision=decision, reason=reason, tick=tick,
            observed_at_utc=_utc_now_iso(),
            fee_gate_lifecycle=fee_lifecycle_index.artifact_for(mint or ""),
            central_ath=ath_store.snapshot(mint or "") or {})
        _append_jsonl(security_decisions_path, record)

    def on_candidate_record(*, rec, entry, cycle, observed_at_utc, ledger_touched,
                            transport_attempted, axiom=None, security=None):
        try:
            mint = rec.get("token_mint", "")
            # PHX2-E2E-006: the engine's per-candidate evaluation is the
            # explicit P1 result — close any open window with the closed-set
            # outcome derived from the engine reason.  Total by design; a
            # classification miss degrades to TEMP_BLOCKED, never silence.
            if market_scheduler is not None:
                p1_outcome = classify_engine_reason_to_p1_outcome(
                    rec.get("reason"))
                if p1_outcome is not None:
                    try:
                        market_scheduler.note_p1_result(
                            mint, outcome=p1_outcome)
                    except Exception:
                        pass
            # Risk layer: fold this recheck's outcome + market context into the mint's risk
            # state, then stamp the CURRENT assessment onto the artifact. Closed-set tokens +
            # counts only (redaction-safe by construction); assess() is total, so the risk
            # layer can never break the proven fail-closed candidate-record path.
            risk_engine.observe_recheck(
                mint, reason=rec.get("reason"), compose_reason=rec.get("compose_reason"),
                market_context=rec.get("market_context"))
            risk = risk_engine.assess(mint)
            central_ath = rec.get("central_ath")
            if not isinstance(central_ath, dict) or not central_ath:
                central_ath = ath_store.snapshot(mint) or {}
            rec = {**rec, "central_ath": central_ath}
            if isinstance(rec.get("market_context"), dict):
                rec["market_context"] = {
                    **rec["market_context"], "central_ath": central_ath}
            record = artifacts.build_candidate_recheck_record(
                rec=rec, entry=entry, cycle=cycle, observed_at_utc=observed_at_utc,
                ledger_touched=ledger_touched, transport_attempted=transport_attempted,
                axiom=None, security=security)
            record = {**record,
                      "risk_label": risk["risk_label"],
                      "risk_reasons": risk["risk_reasons"],
                      "risk_unknown_signals": risk["risk_unknown_signals"],
                      "risk_line": risk["risk_line"],
                      "risk_assessed_at_utc": risk["risk_assessed_at_utc"],
                      "risk_signal_counts": risk["risk_signal_counts"],
                      "fee_gate_lifecycle": fee_lifecycle_index.artifact_for(mint)}
            record["central_ath"] = central_ath
            record.update(_paper_snapshot_context(mint, security, entry_override=entry))
            record["activation"] = rec.get("activation") or record["activation"]
            record["pricing_coverage"] = tail.coverage(mint)
            market_context = rec.get("market_context") or {}
            for key in ("price_observed_at_utc", "provider_timestamp_utc", "price_fresh",
                        "market_price_ttl_seconds", "market_cap_observed_at_utc",
                        "liquidity_observed_at_utc", "market_cap_fresh", "liquidity_fresh",
                        "market_overview_ttl_seconds"):
                if market_context.get(key) is not None:
                    record[key] = market_context[key]
            record["observed_at_utc"] = _utc_now_iso()
            artifacts.append_candidate_jsonl(out_dir, rec.get("token_mint", ""), record)
            # The review stream is non-authoritative: failure is logged but can
            # never change eligibility, dedupe, ledger, or delivery state.
            try:
                candidate_context = (
                    entry.to_candidate() if hasattr(entry, "to_candidate") else {})
                shadow_record = build_shadow_candidate_artifact(
                    decision=security,
                    candidate=candidate_context,
                    record=rec,
                    entry=entry,
                    observed_at_utc=observed_at_utc,
                    fee_gate_lifecycle=fee_lifecycle_index.artifact_for(mint),
                )
                if shadow_record is not None:
                    _append_jsonl(shadow_candidates_path, shadow_record)
            except Exception as shadow_exc:
                errors.log("phx1_shadow_candidate_artifact", shadow_exc)
            try:
                quality_candidate = (
                    entry.to_candidate() if hasattr(entry, "to_candidate") else {})
                quality_candidate["canonical_token_metadata"] = (
                    token_metadata.snapshot(mint))
                quality_candidate["canonical_volume_5m"] = (
                    canonical_volume.snapshot(mint))
                quality_candidate["global_fees"] = (
                    global_fees.snapshot(mint))
                quality_record = build_ping_quality_record(
                    candidate=quality_candidate,
                    recheck=rec,
                    security=security,
                    observed_at_utc=observed_at_utc,
                )
                if not ping_quality_record_is_redaction_safe(quality_record):
                    raise ValueError("PING_QUALITY_REDACTION_REFUSED")
                _append_jsonl(ping_quality_review_path, quality_record)
            except Exception as review_exc:
                errors.log("ping_quality_review", review_exc)
            if rec.get("reason") == "SENT_OK_COMMITTED":
                mc = rec.get("market_context") or {}
                _append_jsonl(would_ping_path, {
                    "kind": "FREE_TIER_WOULD_PING",
                    "token_mint": rec.get("token_mint", ""),
                    "candidate_id": getattr(entry, "candidate_id", None),
                    "migration_time_utc": getattr(entry, "migration_time_utc", None),
                    "observed_at_utc": observed_at_utc,
                    "tick": cycle,
                    "market_context": {
                        "current_price": mc.get("current_price"),
                        "current_market_cap_usd": mc.get("current_market_cap_usd"),
                        "liquidity_usd": mc.get("liquidity_usd"),
                        "market_context_fetched_at_utc": mc.get("market_context_fetched_at_utc"),
                        "pumpswap_reserve": mc.get("pumpswap_reserve") or {},
                        "central_ath": central_ath,
                        "activation": rec.get("activation") or {},
                    },
                    "compose_decision": rec.get("compose_decision"),
                    "compose_tier": rec.get("compose_tier"),
                    "compose_drawdown_pct": rec.get("compose_drawdown_pct"),
                    "compose_anchored_ath_mc": rec.get("compose_anchored_ath_mc"),
                    "central_ath": central_ath,
                    "activation": rec.get("activation") or {},
                    "risk_label": risk["risk_label"],
                    "risk_reasons": risk["risk_reasons"],
                    "risk_line": risk["risk_line"],
                    "producer_mode": mode,
                    "real_send_attempted": delivery_enabled,
                    "delivery_transport": delivery_transport,
                })
                tail.track(rec.get("token_mint", ""),
                           ath_market_cap_display=rec.get("compose_anchored_ath_mc"),
                           tier_at_ping=rec.get("compose_tier"))
        except Exception as exc:
            errors.log("candidate_record", exc)
            raise   # preserve the proven runner fail-closed semantics

    def on_send_record(**kw):
        try:
            record = artifacts.build_send_attempt_record(**kw)
            record = {
                **record,
                "kind": ("PHX2_TELEGRAM_SEND_ATTEMPT" if telegram_enabled
                         else "FREE_TIER_PRIVATE_SEND_ATTEMPT" if discord_enabled
                         else "FREE_TIER_WOULD_PING_ATTEMPT"),
                "producer_mode": mode,
                "delivery_transport": delivery_transport,
                "real_send": bool(delivery_enabled and record.get("sent_ok")),
                "transport_kind": ("TELEGRAM" if telegram_enabled
                                   else "STAGE28_9_PRIVATE_WEBHOOK" if discord_enabled
                                   else NO_SEND_TRANSPORT_KIND),
                "discord_transport_attempted": False if telegram_enabled else bool(
                    record.get("transport_attempted")),
                "telegram_transport_attempted": bool(
                    telegram_enabled and record.get("transport_attempted")),
                "fee_gate_lifecycle": fee_lifecycle_index.artifact_for(
                    record.get("token_mint") or ""),
            }
            bound_central = (record.get("market_context") or {}).get("central_ath")
            latest_central = ath_store.snapshot(record.get("token_mint") or "") or {}
            record["central_ath"] = (
                dict(bound_central) if isinstance(bound_central, dict) and bound_central
                else latest_central
            )
            record["activation"] = (
                (record.get("market_context") or {}).get("activation") or {})
            if (isinstance(bound_central, dict) and bound_central
                    and latest_central
                    and latest_central.get("ath_market_cap")
                    != bound_central.get("ath_market_cap")):
                record["central_ath_latest_post_send"] = latest_central
            # Risk telemetry for the reserved candidate + what the warn-only line appender
            # actually did on THIS send (closed-set status; never gates anything).
            risk = risk_engine.last_assessment(record.get("token_mint") or "")
            line_decision = (
                {} if telegram_enabled else (risk_transport.last_decision or {}))
            record = {
                **record,
                "risk_label": (risk or {}).get("risk_label"),
                "risk_reasons": (risk or {}).get("risk_reasons"),
                "risk_line": (risk or {}).get("risk_line"),
                "risk_line_status": line_decision.get("status"),
                "risk_line_appended": bool(line_decision.get("appended")),
            }
            if telegram_enabled and telegram_adapter is not None \
                    and telegram_adapter.last_result is not None:
                record["telegram"] = telegram_adapter.last_result.evidence()
                record["message_id"] = telegram_adapter.last_result.message_id
                record["transport_result"] = telegram_adapter.last_result.transport_status
            artifacts.append_send_jsonl(out_dir, record)
            budget.record_send_attempt(sent_ok=bool(record.get("sent_ok")))
            delivery_observability["eligible_candidates"] += 1
            return record
        except Exception as exc:
            errors.log("send_record", exc)
            raise

    result_holder: Dict[str, Any] = {}

    def on_heartbeat(hb):
        try:
            watchlist_observability = watchlist.summary()
            supply_status = (
                authoritative_supply_bridge.stats()
                if authoritative_supply_bridge is not None else {})
            fresh_fallback_status = (
                fresh_market_fallback.stats()
                if fresh_market_fallback is not None else {
                    "fresh_fallback_capability_available": False})
            # ---- market-plane liveness, evaluated once per tick ----------
            # Every input below is already in ``hb`` because the runner merges
            # the scheduler's stats before calling this hook.  A sustained
            # blind plane fails closed through the architecture's existing
            # cooperative stop; a transient one is visible and harmless.
            #
            # Gated on the scheduler ACTUALLY being present.  A free-tier run
            # has no market scheduler and therefore publishes no scheduler
            # telemetry, so every liveness input would read as zero -- and a
            # free-tier producer with active candidates would fail closed on a
            # market plane it never had.  Absent telemetry is "not applicable",
            # never "blind".
            scheduler_present = hb.get("scheduler_state") is not None
            central_ath_stats = ath_store.stats()
            plane = market_plane_watch.observe(
                now_monotonic=time.monotonic(),
                active_candidates=(int(
                    watchlist_observability.get("active_candidates")
                    or len(watchlist.active_entries()))
                    if scheduler_present else 0),
                budget_exhausted=bool(
                    MARKET_PROVIDER_BUDGET_EXHAUSTED in (
                        hb.get("market_scheduler_degraded_reasons") or [])),
                starved_age_seconds=hb.get(
                    "market_scheduler_starved_age_seconds"),
                starvation_bound_seconds=SCHEDULER_STARVATION_BOUND_SECONDS,
                successful_refresh_total=int(
                    hb.get("market_scheduler_jobs_completed") or 0),
                priority_refresh_attempts_total=int(
                    hb.get("priority_refresh_requested_total") or 0),
                priority_refresh_served_total=int(
                    hb.get("priority_refresh_succeeded_total") or 0),
                max_observation_age_seconds=hb.get(
                    "market_active_candidate_max_observation_age_seconds"),
                # Candidates stuck waiting on canonical V3 pair-ATH history
                # feed the verdict after a bounded grace -- DEGRADED-only by
                # design (see market_plane_health), never a producer stop.
                ath_v3_waiting_candidates=(int(
                    central_ath_stats.get("ath_v3_waiting_candidates") or 0)
                    if scheduler_present else 0),
                ath_v3_oldest_wait_seconds=central_ath_stats.get(
                    "ath_v3_oldest_wait_seconds"),
            )
            should_stop, stop_reason = classify_market_plane(plane)
            if should_stop:
                # THE canonical fail-closed action: a cooperative stop at the
                # next tick boundary, named, evidence intact.  No parallel
                # circuit mechanism, nothing auto-cleared. If the condition
                # persists across restarts the watchdog's existing restart
                # circuit opens on its own and the operator path takes over.
                budget.request_stop(BUDGET_STOP_MARKET_PLANE_BLIND)
            hb = {**hb, "producer_mode": mode,
                  **plane.to_record(),
                  "market_credential_status": market_credential_status,
                  "market_plane_fail_closed_requested": bool(should_stop),
                  "market_plane_fail_closed_reason": stop_reason or None,
                  "production_mode": (
                      LIVE_EPOCH_PRODUCTION_MODE if live_epoch_mode
                      else "DEVELOPMENT_LEGACY_MODE"),
                  "historical_completeness_required": not live_epoch_mode,
                  "historical_rpc_backfill_enabled": rpc_recovery_enabled,
                  "historical_recovery_status": (
                      HISTORICAL_REPLAY_STATUS if live_epoch_mode else None),
                  "historical_recovery_document_state": (
                      "RETIRED_AUDIT_ONLY" if live_epoch_mode else None),
                  "dexscreener_restart_backfill_enabled": dex_backfill_enabled,
                  "live_epoch": (
                      live_epoch_manager.snapshot()
                      if live_epoch_manager is not None else None),
                  "dexscreener_restart_backfill": (
                      dex_restart_backfill.snapshot()
                      if dex_restart_backfill is not None else None),
                  "live_candidates": watchlist_observability.get(
                      "live_candidates", 0),
                  "dex_backfill_candidates": watchlist_observability.get(
                      "dex_backfill_candidates", 0),
                  "dex_restart_backfill_mode": watchlist_observability.get(
                      "dex_restart_backfill_mode", "DIAGNOSTIC_ONLY"),
                  "post_boundary_candidates_admitted": (
                      watchlist_observability.get(
                          "post_boundary_candidates_admitted", 0)),
                  "pre_boundary_candidates_ignored": (
                      watchlist_observability.get(
                          "pre_boundary_candidates_ignored", 0)),
                  "restored_diagnostic_records": (
                      watchlist_observability.get(
                          "restored_diagnostic_records", 0)),
                  "dex_diagnostic_records": watchlist_observability.get(
                      "dex_diagnostic_records", 0),
                  "historical_candidates_eligible": (
                      watchlist_observability.get(
                          "historical_candidates_eligible", 0)),
                  "live_dex_corroborations": watchlist_observability.get(
                      "live_dex_corroborations", 0),
                  **dict(delivery_observability),
                  "phx1_structural_policy": phx1_structural_policy,
                  "alert_policy": alert_policy,
                  "alert_policy_matrix": policy_matrix(alert_policy),
                  "alert_policy_counters": alert_policy_counters.snapshot(),
                  "discovery_mode": discovery_mode_display,
                  "raw_ws_cap_note": RAW_WS_CAP_NOTE,
                  "lp_integrity_mode": LP_INTEGRITY_MODE,
                  "verifier_stream_status": VERIFIER_STREAM_STATUS_DISABLED,
                  "max_active_streams_allowed": MAX_ACTIVE_STREAMS,
                  "legacy_lp_state": legacy_lp_state,
                  "pipeline_counters": dict(pipeline_counters),
                  "delivery_transport": delivery_transport,
                  "telegram_enabled": telegram_enabled,
                  "telegram_token_configured": telegram_enabled,
                  "telegram_chat_configured": telegram_enabled,
                  "discord_enabled": discord_enabled,
                  "discord_attempts": 0 if telegram_enabled else None,
                  "private_discord_enabled": discord_enabled,
                  "market_transport_stats": market_transport.stats(),
                  "central_ath_stats": central_ath_stats,
                  "authoritative_supply": supply_status,
                  **supply_status,
                  "authenticated_fresh_market_fallback": (
                      fresh_fallback_status),
                  **fresh_fallback_status,
                  "pricing_tail": tail.summary(),
                  "market_freshness": tail.market_freshness(),
                  "risk_summary": risk_engine.summary(),
                  "risk_discord_block": discord_block_ledger.snapshot(),
                  "provider_telemetry": _provider_snapshot(),
                  "market_readiness": _market_readiness_snapshot(),
                  "error_count": errors.count,
                  "credit_budget": budget.snapshot(),
                  "non_pump_guard_dropped_total": non_pump_guard["dropped_total"],
                  "last_discovery_window": dict(last_discovery)}
            artifacts.append_heartbeat_jsonl(out_dir, hb)
            artifacts.write_json(out_dir, PRODUCER_HEARTBEAT_BASENAME, hb)
        except Exception as exc:
            errors.log("heartbeat", exc)

    def partial_flush_fn(snapshot):
        try:
            result_holder.update(snapshot)
            after_triple = ledgerlib.compute_baseline(str(ledger_path))
            artifacts.write_json(out_dir, PRODUCER_SUMMARY_BASENAME, _build_producer_summary(
                result=snapshot, mode=mode, out_dir=out_dir, ledger_path=str(ledger_path),
                baseline_before=baseline_before,
                baseline_after=(after_triple.as_token() if after_triple else None),
                transport_stats=market_transport.stats(), tail_summary=tail.summary(),
                error_count=errors.count, discord_enabled=discord_enabled,
                credit_budget=budget.snapshot(), final=False,
                telegram_enabled=telegram_enabled,
                delivery_transport=delivery_transport,
                non_pump_guard_dropped_total=non_pump_guard["dropped_total"],
                discovery_mode=discovery_mode_display,
                market_freshness=tail.market_freshness(), profile=eff["profile"],
                risk_summary=risk_engine.summary(),
                risk_discord_block=discord_block_ledger.snapshot(),
                provider_telemetry=_provider_snapshot(),
                market_readiness=_market_readiness_snapshot(),
                checkpoint_status=_checkpoint_status_snapshot(),
                authoritative_supply=(
                    authoritative_supply_bridge.stats()
                    if authoritative_supply_bridge is not None else {}),
                phx1_structural_policy=phx1_structural_policy,
                alert_policy=alert_policy))
        except Exception as exc:
            errors.log("partial_flush", exc)

    def on_cycle(**_kw):
        _assert_provider_safety()
        try:
            tail.poll(_utc_now_iso())
            if market_scheduler is not None:
                paper_views = []
                pins = tail.paper_positions()
                for mint in tail.tracked_mints():
                    entry = watchlist.get(mint)
                    if entry is None and mint in pins:
                        entry = SimpleNamespace(token_mint=mint,
                            candidate_id=pins[mint].get("candidate_id") or ("paper_" + mint),
                            status="PAPER_PRICE_WATCH", seeded_at_utc=None)
                    if entry is not None:
                        paper_views.append(entry)
                market_scheduler.update_paper_candidates(paper_views,
                    max_tracked=int(args.tail_max_tracked))
        except Exception as exc:
            errors.log("pricing_tail", exc)
        # Supply is an authenticated prerequisite of OHLCV market-cap
        # resolution.  Drive it first so the same tick's hydration can publish
        # a coherent price/supply/market-cap tuple.
        try:
            _sweep_authoritative_supply()
        except Exception as exc:
            errors.log("authoritative_supply_sweep", exc)
        # Hydration is a property of the CANDIDATE, not of whether the mint
        # won one of the pricing tail's bounded slots.  Bounded per tick and
        # gated by the store's own backoff; a failure here degrades
        # hydration only and never touches admission, activation or safety.
        try:
            migration_metrics["ath_hydration_driven"] += _sweep_ath_hydration()
        except Exception as exc:
            errors.log("ath_hydration_sweep", exc)
        # Budget boundary check at the tick seam, AFTER this tick's ledger/artifact work is
        # complete. Deliberately raises FreeTierBudgetExhausted through the proven runner's
        # fail-closed stop; the postflight relabels exactly that stop as BUDGET_<reason>.
        budget.observe_market(market_transport.stats())
        budget.check_and_raise()

    def redaction_scan_fn():
        return artifacts.run_redaction_scan(out_dir)

    # Free-tier discovery is an active network reseed and keeps its configured
    # cadence.  The paid owner is already continuously scanning one gRPC stream;
    # its discovery callback only drains the local queue, so never defer that
    # handoff behind the legacy WS reseed interval.
    bounds = _bounds_with_provider_handoff_cadence(
        _bounds_from_args(args), provider_mode)
    print(f"[live] PHX2 producer starting: mode={mode} out_dir={out_dir}")
    print(f"  phx1_structural_policy={phx1_structural_policy}")
    market_label = "PAID_MARKET_PRIMARY" if paid_mode else "FREE_TIER"
    print(f"  market={market_label} (fallback={'ON' if (fallback_transport or provider_mode == PROVIDER_MODE_PAID_WITH_FALLBACK) else 'OFF'}) "
          f"liquidity_floor_usd={args.min_liquidity_usd} recheck={bounds.recheck_interval_seconds:g}s "
          f"reseed={bounds.reseed_interval_seconds:g}s cooldown={bounds.min_seconds_between_sends:g}s "
          + ("max_runtime=UNBOUNDED"
             if runtime_bound_is_unbounded(bounds.max_runtime_seconds)
             else f"max_runtime={bounds.max_runtime_seconds:g}s"))
    print("  migration_activation=1.20x "
          "baseline_priority=GRPC_EVENT,PAID_MARKET_PRIMARY_FALLBACK "
          "central_ath_independent_of_spot=TRUE "
          "crossing_tick_send=BLOCKED")
    print("  baseline_observation=DECOUPLED_FROM_SEND_AUTHORIZATION "
          "(pricing-tail observations feed the centralized watch state; "
          "security-blocked candidates observe but never compose/reserve/send)")
    print(f"  stream_topology=SINGLE_STREAM PRIMARY_STREAM_MAX={PRIMARY_STREAM_MAX} "
          f"VERIFIER_STREAM_MAX={VERIFIER_STREAM_MAX} "
          f"MAX_ACTIVE_STREAMS={MAX_ACTIVE_STREAMS} "
          f"VERIFIER_STREAM_STATUS={VERIFIER_STREAM_STATUS_DISABLED} "
          f"LP_INTEGRITY_MODE={LP_INTEGRITY_MODE}")

    floor = Decimal(str(args.min_liquidity_usd))

    def _counted_liquidity_floor(mint: str, ctx: Dict[str, Any]) -> Optional[str]:
        # The unchanged committed market liquidity-dollar floor (default
        # $4,500; stale/missing liquidity fails closed inside it), plus
        # closed-set pass/fail counters for observability.
        reason = liquidity_floor_block_reason(mint, ctx, min_liquidity_usd=floor)
        if reason:
            pipeline_counters["liquidity_floor_fail"] += 1
        else:
            pipeline_counters["liquidity_floor_pass"] += 1
        return reason

    # PRE-RESERVE private-Discord dispatch gate (risk policy in front of the minimum-liquidity
    # floor). run_cap1_candidates applies it before any reserve / webhook / cap — see the factory.
    risk_and_floor_gate = make_discord_risk_gate(
        risk_engine=risk_engine, discord_block_ledger=discord_block_ledger,
        discord_blocks_path=discord_blocks_path, min_liquidity_usd=floor,
        mode=mode, errors=errors, floor_fn=_counted_liquidity_floor,
        lp_integrity_mode=LP_INTEGRITY_MODE)

    # Send-time fee gate freshness re-check at the pre-reserve boundary: the
    # security decision was bound at tick start, so evidence that went stale
    # (or a verdict that turned SCAM) between activation and compose must
    # block HERE — no compose, no reservation, no ledger mutation, no
    # transport — while the candidate stays tracked for later fresh
    # re-evaluation.  The identity-digest dedupe inside the lifecycle means
    # this re-observation can never double-count a frozen snapshot.
    fee_gate_send_time_gate = make_fee_gate_send_time_gate(
        fee_index=fee_index,
        lifecycle_index=fee_lifecycle_index,
        security_index=security_index,
        max_age_seconds=Decimal(str(args.market_fresh_within_seconds)),
        now_epoch_fn=lambda: int(time.time()),
        phx1_structural_policy=phx1_structural_policy,
        policy_counters=alert_policy_counters)

    def source_health_gate(_mint: str, _ctx: Dict[str, Any]) -> Optional[str]:
        """Block dispatch while gRPC discovery coverage is unproven.

        Runs at the pre-reserve boundary, so it precedes compose
        authorization, delivery reservation, the transport-start journal,
        dispatch and the successful-send ledger row -- all five at once.

        It deliberately does NOT block ingestion: replay, migration admission,
        deterministic rejection, candidate restoration, watchlist rebuilding
        and baseline restoration all continue while degraded, because that is
        how the recovery completes.  Only the outbound path waits.

        Free-tier mode owns no gRPC source and is therefore not gated here;
        its coverage story is the polling/WS discovery path, unchanged.
        """

        if paid_discovery is None:
            return None
        try:
            authorized, reason = paid_discovery.authorizes_send()
        except Exception as exc:
            # Fail CLOSED, matching every other gate at this boundary.
            pipeline_counters["source_health_block"] += 1
            return "SOURCE_HEALTH_GATE_ERROR (%s)" % type(exc).__name__
        if authorized:
            return None
        pipeline_counters["source_health_block"] += 1
        return "PHX2_GRPC_SOURCE_UNHEALTHY (%s)" % reason

    def discord_risk_gate(mint: str, ctx: Dict[str, Any]) -> Optional[str]:
        # Second independent enforcement location.  The bound immutable
        # decision is validated immediately before the existing risk and LP
        # floor gates and before composer/reservation/ledger/transport.
        # Discovery-coverage health is checked FIRST: if the stream cannot
        # prove what it may have missed, nothing downstream should dispatch.
        source_reason = source_health_gate(mint, ctx)
        if source_reason:
            return source_reason
        entry = watchlist.get(mint)
        if (entry is not None
                and getattr(entry, "discovery_provenance", None)
                == DISCOVERY_PROVENANCE_DEX):
            if dex_restart_backfill is None:
                return "BACKFILL_CURRENT_DATA_OWNER_MISSING"
            market_ok, market_reason = dex_restart_backfill.fresh_market_gate(
                mint=mint,
                now_utc=_utc_now_iso(),
            )
            gate_metadata = dex_restart_backfill.market_metadata(mint)
            if gate_metadata.get("token_name") or gate_metadata.get(
                    "token_symbol"):
                # Provider-neutral source token: unknown provider-name strings
                # are danger needles for the runtime artifact scanner.
                _harvest_token_metadata(
                    mint,
                    token_name=gate_metadata.get("token_name"),
                    token_symbol=gate_metadata.get("token_symbol"),
                    source="RESTART_BACKFILL_FRESH_MARKET_GATE")
            if not market_ok:
                return market_reason
        security_reason = security_index.proof_gate(mint)
        if security_reason:
            return security_reason
        lifecycle_reason = fee_gate_send_time_gate(mint)
        refreshed_security = security_index.get(mint)
        if refreshed_security is not None:
            ctx["security_decision"] = refreshed_security
            ctx["fee_gate_lifecycle"] = fee_lifecycle_index.artifact_for(mint)
        if lifecycle_reason:
            return lifecycle_reason
        block_reason = risk_and_floor_gate(mint, ctx)
        if block_reason:
            return block_reason
        # LAST gate (2026-07-28 metadata remediation): an otherwise fully
        # dispatchable candidate whose metadata enrichment is still in flight
        # may wait a bounded number of recheck ticks (attempt- and wall-clock
        # capped inside the resolver).  Exhaustion always proceeds; a resolver
        # error never blocks a send.
        try:
            return token_metadata.pre_dispatch_defer_reason(mint)
        except Exception as metadata_exc:
            errors.log("token_metadata_defer", metadata_exc)
            return None

    def run_engine(cands, **kw):
        # ``axiom_fee_appender`` is the committed compose display seam (bind_body with the
        # EXACT dispatched body + mint right before the guarded send). The risk transport
        # reuses it to arm the warn-only "Risk:" line — the runner itself never passes this
        # kwarg, so there is no collision.
        for cand in cands:
            # Thread the current lifecycle artifact into the candidate dict so
            # the delivery context (and therefore the Telegram compose
            # artifact) references the same lifecycle/evidence version as the
            # security index and the per-candidate records.
            if isinstance(cand, dict):
                mint = cand.get("token_mint") or ""
                cand["fee_gate_lifecycle"] = fee_lifecycle_index.artifact_for(
                    mint)
                cand["canonical_volume_5m"] = canonical_volume.snapshot(mint)
                # Observe-only Global Fees snapshot (exact mint) so compose
                # reads canonical state, never a transient candidate dict.
                cand["global_fees"] = global_fees.snapshot(mint)
                # Canonical metadata state (2026-07-28 remediation).  First
                # rehydrate from durable candidate fields (restored watch
                # state, admission payload) so a restart never loses an
                # already-known identity, then stamp the canonical snapshot;
                # the delivery adapter consumes it at highest precedence, so a
                # stale candidate snapshot can never override enriched state.
                fallback_symbol = cand.get("symbol_or_name")
                if fallback_symbol == cand.get("token_name"):
                    fallback_symbol = None
                _harvest_token_metadata(
                    mint,
                    token_name=cand.get("token_name"),
                    token_symbol=(cand.get("token_symbol")
                                  or fallback_symbol),
                    source="CANDIDATE_STATE")
                cand["canonical_token_metadata"] = token_metadata.snapshot(
                    mint)
        return sess.run_cap1_candidates(
            cands,
            pre_reserve_gate_fn=discord_risk_gate,
            axiom_fee_appender=delivery_body_adapter,
            delivery_journal=delivery_journal,
            **kw)

    def _terminal_history_context(entry):
        # Read-only evidence enrichment for archived terminal candidates:
        # latest central ATH, Fee Gate lifecycle state, and risk label from
        # the run's existing indices. Pure lookups — never a fetch, never a
        # block; a lookup error leaves the field explicitly null.
        mint = getattr(entry, "token_mint", "") or ""
        context: Dict[str, Any] = {}
        try:
            ath_snapshot = ath_store.snapshot(mint)
            if isinstance(ath_snapshot, dict):
                context["latest_ath_market_cap_usd"] = ath_snapshot.get(
                    "ath_market_cap_usd")
                context["latest_ath_observed_at_utc"] = ath_snapshot.get(
                    "ath_observed_at_utc")
        except Exception:
            pass
        try:
            assessment = risk_engine.last_assessment(mint)
            if isinstance(assessment, dict):
                context["risk_label"] = assessment.get("risk_label")
        except Exception:
            pass
        try:
            lifecycle = fee_lifecycle_index.artifact_for(mint)
            if isinstance(lifecycle, dict):
                context["fee_gate_lifecycle_state"] = lifecycle.get(
                    "lifecycle_state")
        except Exception:
            pass
        return context

    watchlist.set_terminal_context_fn(_terminal_history_context)

    # PHX2-E2E-006: the maintenance interval survives as the MAXIMUM idle
    # wait; P1-relevant scheduler events (tier-entry evidence, completed
    # overview enrichment, handoff arrivals) wake the loop immediately.
    # The 1-second minimum gap bounds the tick rate under event storms.
    tick_waiter: Optional[P1TickWaiter] = None
    if market_scheduler is not None:
        tick_waiter = P1TickWaiter(min_gap_seconds=1.0)
        market_scheduler.set_dispatch_waker(tick_waiter.wake)
        if paid_discovery is not None and hasattr(
                paid_discovery, "set_enqueue_waker"):
            paid_discovery.set_enqueue_waker(tick_waiter.wake)

    # ---- acceptance-phase clock -------------------------------------------
    # An inherited recovery episode is resumed while the producer is fully up
    # but structurally unable to deliver. Timing the soak from process start
    # would count that recovery as soak time, so the acceptance clock only runs
    # in ACTIVE_STAGE9_SOAK. Absent --active-soak-seconds nothing changes and
    # --max-runtime-seconds keeps its original wall-clock meaning.
    phase_clock: Optional[RuntimePhaseClock] = None
    if float(getattr(args, "active_soak_seconds", 0.0) or 0.0) > 0.0:
        phase_clock = RuntimePhaseClock(
            required_active_seconds=float(args.active_soak_seconds))
        print(f"[phase] acceptance clock armed: "
              f"required_active_soak_seconds={args.active_soak_seconds:g} "
              f"wall_clock_ceiling_seconds={args.max_wall_clock_seconds:g} "
              f"initial_phase={phase_clock.phase}")

    # SINGLE-STREAM: only the primary Yellowstone owner ever starts.  There is
    # no verifier object to start, stop, or watchdog.
    try:
        if market_scheduler is not None:
            market_scheduler.start()
        if paid_discovery is not None:
            paid_discovery.start()
            _service_live_epoch_boundary()
        if chainstack_shadow is not None:
            chainstack_shadow.start()
        result = run_production_live_watch(
            watchlist=watchlist,
            axiom_source=axiomgate.NullAxiomFeeSource(),
            axiom_config=_strict_axiom_config(),
            sidecar_factory=sidecar_factory,
            ath_transport=market_transport,
            ath_endpoint_secret=endpoint_secret,
            ledger=durable,
            guard_factory=lambda: cs.make_guard(transport=guard_transport),
            authorization=authorization,
            now_dt_fn=_utc_now_dt, now_iso_fn=_utc_now_iso,
            now_seconds=make_constant_clock(Decimal(0)),
            sleep_fn=time.sleep, monotonic_fn=time.monotonic,
            bounds=bounds, run_cap1_candidates_fn=run_engine,
            ledger_line_count_fn=b30s._ledger_line_count_fn(str(ledger_path)),
            discovery_fn=discovery_fn,
            on_axiom_record=None,           # Axiom disabled: Null source, no artifacts, no RPC
            on_candidate_record=on_candidate_record,
            on_send_record=on_send_record,
            on_cycle=on_cycle,
            redaction_scan_fn=redaction_scan_fn,
            watch_state_path=watch_state_path,
            on_heartbeat=on_heartbeat,
            on_handoff_event=_record_provider_handoff,
            on_activation_event=_record_activation_event,
            activation_market_max_age_seconds=float(args.market_fresh_within_seconds),
            activation_observation_source=activation_source_label,
            partial_flush_fn=partial_flush_fn,
            require_axiom_pass=False,
            security_decision_fn=security_decision_fn,
            on_security_record=on_security_record,
            market_scheduler=market_scheduler,
            tick_wait_fn=tick_waiter,
            policy_counters=alert_policy_counters,
            stop_requested_fn=(
                (lambda: stop_file.exists()) if stop_file is not None else None
            ),
            phase_tick_fn=(
                None if phase_clock is None else
                (lambda: phase_clock.evaluate(
                    _build_activation_inputs(paid_discovery)))),
            active_seconds_fn=(
                None if phase_clock is None else phase_clock.active_seconds),
            max_wall_clock_seconds=(
                None if phase_clock is None
                else float(args.max_wall_clock_seconds)),
        )
    finally:
        if market_scheduler is not None:
            # Stop accepting jobs before the gRPC owner is cancelled. A reserve
            # event racing with cooperative stop is therefore rejected and no
            # new provider call can begin.
            market_scheduler.request_stop()
        if chainstack_shadow is not None:
            chainstack_shadow.stop(
                timeout_seconds=float(args.grpc_stop_timeout_seconds)
            )
        if paid_discovery is not None:
            paid_discovery.stop(timeout_seconds=float(args.grpc_stop_timeout_seconds))
        if market_scheduler is not None:
            market_scheduler.stop(
                timeout_seconds=float(args.grpc_stop_timeout_seconds))
        if telegram_adapter is not None:
            telegram_adapter.close()
        # Release the serialized append descriptors only after every event
        # source (engine loop above, provider drain and scheduler owner just
        # stopped) is done.
        activation_events_appender.close()
        provider_handoff_appender.close()

    # Relabel EXACTLY our own deliberate tick-boundary budget raise as a clean BUDGET_<reason>
    # boundary; any real unexpected stop passes through untouched.
    result, _budget_tripped = rewrite_result_for_budget_stop(result, budget)

    after = ledgerlib.compute_baseline(str(ledger_path))
    scan = artifacts.run_redaction_scan(out_dir)
    artifacts.write_json(out_dir, artifacts.REDACTION_SCAN_BASENAME, scan)
    summary = _build_producer_summary(
        result=result, mode=mode, out_dir=out_dir, ledger_path=str(ledger_path),
        baseline_before=baseline_before,
        baseline_after=(after.as_token() if after else None),
        transport_stats=market_transport.stats(), tail_summary=tail.summary(),
        error_count=errors.count, discord_enabled=discord_enabled,
        credit_budget=budget.snapshot(), final=True,
        telegram_enabled=telegram_enabled,
        delivery_transport=delivery_transport,
        non_pump_guard_dropped_total=non_pump_guard["dropped_total"],
        discovery_mode=discovery_mode_display,
        market_freshness=tail.market_freshness(), profile=eff["profile"],
        risk_summary=risk_engine.summary(),
        risk_discord_block=discord_block_ledger.snapshot(),
        provider_telemetry=_provider_snapshot(),
        market_readiness=_market_readiness_snapshot(),
        checkpoint_status=_checkpoint_status_snapshot(),
        authoritative_supply=(
            authoritative_supply_bridge.stats()
            if authoritative_supply_bridge is not None else {}),
        phx1_structural_policy=phx1_structural_policy,
        alert_policy=alert_policy)
    artifacts.write_json(out_dir, PRODUCER_SUMMARY_BASENAME, summary)
    artifacts.write_json(
        out_dir, CHECKPOINT_STATUS_BASENAME, _checkpoint_status_snapshot())
    after_token = after.as_token() if after else None
    artifacts.write_json(
        out_dir,
        artifacts.LEDGER_DELTA_BASENAME,
        artifacts.build_ledger_delta(
            before=baseline_before,
            after=after_token,
            delta=result.get("total_ledger_delta"),
            transport_ok=(True if summary["real_send_performed"] else None),
            real_send_performed=summary["real_send_performed"],
            durable_ledger_used=True,
        ),
    )
    safety = artifacts.build_production_safety_report(
        outcome=str(result.get("outcome") or "UNKNOWN"),
        stop_reason=result.get("stop_reason"),
        real_send_performed=summary["real_send_performed"],
        real_private_transport_constructed=delivery_enabled,
        sends=int(result.get("sends", 0)),
        durable_ledger_opened=True,
        durable_ledger_mutated=bool(result.get("total_ledger_delta", 0)),
        total_ledger_delta=result.get("total_ledger_delta"),
        armed=delivery_enabled,
        approval_token_used=delivery_enabled,
        axiom_source="NULL_AXIOM_SOURCE",
        axiom_gate_enabled=False,
        scan=scan,
        interrupted=bool(result.get("interrupted", False)),
        postflight_complete=True,
    )
    safety = {
        **safety,
        "delivery_transport": delivery_transport,
        "phx1_structural_policy": phx1_structural_policy,
        "telegram_transport_constructed": telegram_enabled,
        "telegram_transport_closed": telegram_enabled,
        "discord_transport_constructed": discord_enabled,
        "discord_attempts": 0 if telegram_enabled else None,
        "paid_grpc_provider_surface": bool(paid_mode),
        "stage28_grpc_yellowstone_surface": bool(paid_mode),
        "provider_telemetry": _provider_snapshot(),
        "market_readiness": _market_readiness_snapshot(),
        "controlled_exit": result.get("stop_reason") in (
            "OPERATOR_REQUESTED", "MAX_RUNTIME", "BUDGET_SEND_CAP",
        ),
    }
    artifacts.write_json(out_dir, artifacts.SAFETY_REPORT_BASENAME, safety)
    # Scan after every controlled-exit artifact exists, then seal both scan and safety.
    scan = artifacts.run_redaction_scan(out_dir)
    artifacts.write_json(out_dir, artifacts.REDACTION_SCAN_BASENAME, scan)
    safety.update({
        "redaction_status": scan["redaction_status"],
        "redaction_total_unsafe_hits": scan["total_unsafe_hits"],
        "redaction_positive_control_ok": scan["positive_control_ok"],
    })
    artifacts.write_json(out_dir, artifacts.SAFETY_REPORT_BASENAME, safety)

    verdict = verdict_for_budget_stop(production_postflight_verdict(result), result)
    bsnap = budget.snapshot()
    fresh = tail.market_freshness()
    print("---- FREE-TIER PRODUCER REPORT ----")
    print(f"mode={mode} discovery_mode={discovery_mode_display} "
          f"profile={eff['profile'] or 'none'} outcome={result['outcome']} "
          f"stop_reason={result['stop_reason']} "
          f"exception_type={result['exception_type']} "
          f"budget_stop={result.get('budget_stop', False)}")
    _final_provider = _provider_snapshot()
    print(f"stream_topology: PRIMARY_STREAM_STATUS="
          f"{_final_provider.get('primary_stream_status') or _final_provider.get('status')} "
          f"ACTIVE_STREAMS={_final_provider.get('total_active_streams', _final_provider.get('active_streams', 0))} "
          f"MAX_ACTIVE_STREAMS={MAX_ACTIVE_STREAMS} "
          f"VERIFIER_STREAM_STATUS={VERIFIER_STREAM_STATUS_DISABLED} "
          f"LP_INTEGRITY_MODE={LP_INTEGRITY_MODE} "
          f"legacy_lp_state={legacy_lp_state}")
    print(f"pipeline_counters: baselines_captured={pipeline_counters['baselines_captured']} "
          f"candidates_activated={pipeline_counters['candidates_activated']} "
          f"liquidity_floor_pass={pipeline_counters['liquidity_floor_pass']} "
          f"liquidity_floor_fail={pipeline_counters['liquidity_floor_fail']}")
    print(f"ticks={result['ticks']} would_pings={result['sends']} reseeds={result['reseeds']} "
          f"market_calls={result['market_calls']} errors_logged={errors.count}")
    print(f"credit_budget: raw_ws_notifications_seen={bsnap['ws_notifications_seen']} "
          f"(NOTE: {RAW_WS_CAP_NOTE}) "
          f"seed_windows={bsnap['seed_windows']} candidate_count={bsnap['candidate_count']} "
          f"gettransaction={bsnap['gettransaction_fetches']} "
          f"market_requests={bsnap['market_requests']} 429_count={bsnap['429_count']} "
          f"send_attempts={bsnap['send_attempts']} sent_ok={bsnap['sent_ok_count']} "
          f"would_ping_count={bsnap['would_ping_count']} "
          f"private_ping_count={bsnap['private_ping_count']} "
          f"budget_stop_reason={bsnap['budget_stop_reason']}")
    poll_snap = bsnap.get("polling") or {}
    print(f"polling: poll_count={poll_snap.get('poll_count')} "
          f"pools_new={poll_snap.get('pools_new')} "
          f"signatures_seen={poll_snap.get('signatures_seen')} "
          f"signatures_new={poll_snap.get('signatures_new')} "
          f"transactions_fetched={poll_snap.get('transactions_fetched')} "
          f"create_pool_candidates={poll_snap.get('create_pool_candidates')} "
          f"pump_suffix_accepted={poll_snap.get('pump_suffix_accepted')} "
          f"non_pump_guard_dropped={poll_snap.get('non_pump_guard_dropped')} "
          f"polling_errors={poll_snap.get('polling_errors')} "
          f"polling_429={poll_snap.get('polling_429')}")
    print(f"market_freshness: fresh={fresh['market_data_fresh_count']} "
          f"stale={fresh['market_data_stale_count']} "
          f"unavailable={fresh['market_unavailable_count']} "
          f"last_successful_refresh={fresh['last_successful_market_refresh_at']} "
          f"last_error={fresh['last_market_error']} "
          f"refresh_success_total={fresh['refresh_success_total']} "
          f"refresh_miss_total={fresh['refresh_miss_total']}")
    rsnap = risk_engine.summary()
    rlabels = rsnap.get("by_label") or {}
    print(f"risk_summary: assessed={rsnap.get('assessed_mints')} "
          f"low={rlabels.get('RISK_LOW')} medium={rlabels.get('RISK_MEDIUM')} "
          f"high={rlabels.get('RISK_HIGH')} unknown={rlabels.get('RISK_UNKNOWN')} "
          f"high_risk_mints={len(rsnap.get('high_risk_mints') or [])} "
          f"holder_scan_enabled={rsnap.get('holder_scan_enabled')} (warn-only layer)")
    print(f"ledger[{ledger_path}]: before={baseline_before} "
          f"after={after.as_token() if after else None} delta={result['total_ledger_delta']} "
          f"consistent={result['ledger_consistent']}")
    print(f"watchlist={result['watchlist_summary']}")
    print(f"provider_telemetry={_provider_snapshot()}")
    print(f"market_transport={market_transport.stats()} pricing_tail={tail.summary()}")
    print(f"redaction_status={scan['redaction_status']} "
          f"total_unsafe_hits={scan['total_unsafe_hits']} "
          f"positive_control_ok={scan['positive_control_ok']}")
    print(f"phx1_structural_policy={phx1_structural_policy}")
    print(f"delivery_transport={delivery_transport} telegram_enabled={telegram_enabled} "
          f"discord_enabled={discord_enabled} discord_attempts={0 if telegram_enabled else 'N/A'} "
          f"real_send_performed={summary['real_send_performed']} "
          f"wallet_signing_or_trading=False public_or_subscriber_routing=False")
    print(f"postflight_ok={verdict['postflight_ok']} exit_code={verdict['exit_code']}")
    print(f"out_dir={out_dir}")
    return verdict["exit_code"]


# --------------------------------------------------------------------------- CLI


def _add_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--selftest", action="store_true")
    p.add_argument("--preflight", action="store_true")
    p.add_argument("--run", action="store_true")
    p.add_argument(
        "--phx1-structural-policy",
        dest="phx1_structural_policy",
        choices=list(PHX1_STRUCTURAL_POLICY_CLI_VALUES),
        default="enforce",
        help="explicit PHX1 structural/scam routing: enforce (default) or shadow",
    )
    p.add_argument(
        "--alert-policy",
        dest="alert_policy",
        choices=list(ALERT_POLICY_CLI_VALUES),
        default="legacy",
        help="named alert policy: legacy (default; every committed gate "
             "unchanged) or phx1_parity (activation and fee lifecycle become "
             "shadow, six-hour adaptive watch, bounded send-time market "
             "refresh; ATH, LP, MC, dedupe, credential and checkpoint safety "
             "stay hard)",
    )
    p.add_argument("--env", default=ENV_FILE_DEFAULT)
    p.add_argument("--out-dir", dest="out_dir", default=OUT_DIR_DEFAULT)
    p.add_argument("--ledger-path", dest="ledger_path", default=LEDGER_DEFAULT)
    p.add_argument("--stop-file", dest="stop_file", default=None,
                   help="cooperative operator stop seam; existence requests a clean final flush.")
    # Run profile + discovery mode (2026-07-10). Profile fills any cap/runtime flag the operator
    # did not set explicitly (explicit flag > profile > base default; base = historical values).
    p.add_argument("--profile", dest="profile", choices=sorted(PROFILES), default=None,
                   help="cap/runtime/discovery preset: short_test_10m | live_2h | live_4h | "
                        "live_2h_low_credit | live_2h_hybrid_thin. live_2h_low_credit pins "
                        "polling discovery (NO WS firehose) + tighter Helius spend ceilings for a "
                        "sustainable 24/7 posture; live_2h_hybrid_thin is mostly polling with "
                        "occasional short WS windows. live_2h keeps the 2.0M raw-WS cap (raw "
                        "firehose messages, NOT Helius credits).")
    p.add_argument("--discovery-mode", dest="discovery_mode", choices=list(DISCOVERY_MODES),
                   default=None,
                   help="ws = logsSubscribe windows (legacy default); polling = cheap keyless "
                        "new-pools listing + surgical getSignaturesForAddress/getTransaction (NO "
                        "WS firehose); hybrid = polling every reseed + WS windows while raw-WS "
                        "budget lasts. Unset => profile's mode (live_2h_low_credit pins polling), "
                        "else ws.")
    p.add_argument(
        "--provider-mode", dest="provider_mode",
        choices=[mode.lower() for mode in PROVIDER_MODES], default="free_tier",
        help="free_tier = existing discovery/market path; paid_primary = one Yellowstone "
             "owner + Birdeye primary; paid_with_fallback = same paid primary, with the "
             "existing keyless poller enabled only while gRPC is stale/reconnecting. Every "
             "mode is no-send by default; private Discord requires the same full arm gate.")
    p.add_argument(
        "--migration-source-mode",
        dest="migration_source_mode",
        choices=list(MIGRATION_SOURCE_MODES),
        default=None,
        help=(
            "explicit closed-set migration authority mode; must exactly match "
            "PHX2_MIGRATION_SOURCE_MODE and never falls back implicitly"
        ),
    )
    p.add_argument(
        "--enable-helius-http-recovery",
        dest="enable_helius_http_recovery",
        action="store_true",
        help=(
            "require the bounded exact-slot Helius HTTP recovery component "
            "for Helius-primary production"
        ),
    )
    p.add_argument(
        "--helius-max-raw-bytes",
        dest="helius_max_raw_bytes",
        type=int,
        default=1_000_000_000,
        help=(
            "run-wide byte ceiling shared by Helius WSS and HTTP recovery"
        ),
    )
    p.add_argument(
        "--helius-parity-late-match-seconds",
        dest="helius_parity_late_match_seconds",
        type=float,
        default=30.0,
        help="bounded Chainstack-shadow late-match grace",
    )
    p.add_argument(
        "--cursor-state-dir", dest="cursor_state_dir", default=None,
        help="STABLE directory holding the durable gRPC stream cursor. Kept "
             "separate from --out-dir on purpose: run artifacts are disposable "
             "and the operator is told to rotate the out dir per run, but the "
             "resume position must survive both a fresh run directory and a "
             "process restart. Defaults to --out-dir, which is safe for "
             "development but is REFUSED under --require-production-grpc.")
    p.add_argument(
        "--cursor-persist-batch-max-events", dest="cursor_persist_batch_max_events",
        type=int, default=32,
        help="Bounded periodic cursor persistence: write the durable stream "
             "cursor after at most this many committed events. The in-memory "
             "position advances every event (intra-session dedupe is unchanged) "
             "while the fsync-heavy authenticated checkpoint is written on a "
             "small batch, so the single consumption thread keeps pace with the "
             "firehose. 1 restores the pre-fix flush-every-event behaviour.")
    p.add_argument(
        "--cursor-persist-batch-max-seconds", dest="cursor_persist_batch_max_seconds",
        type=float, default=0.5,
        help="Bounded periodic cursor persistence: also flush when the oldest "
             "un-flushed commit is older than this many seconds, bounding the "
             "durable lag during a quiet stream. 0 disables the time trigger.")
    p.add_argument(
        "--expected-head", dest="expected_head", default=None,
        help="pin the exact repository commit this run must execute. Fails "
             "closed on a mismatch before any network object is created.")
    p.add_argument(
        "--require-production-grpc", dest="require_production_grpc",
        action="store_true",
        help="ARMED PRODUCTION CONTRACT. Fails startup, before any network "
             "object exists, unless: provider mode is a paid gRPC mode; a "
             "cursor store is built; the cursor state directory is stable "
             "(not the run dir, not a temp/scratch dir); the source factory "
             "accepts a resume position; and no legacy websocket discovery or "
             "second discovery owner is configured.")
    p.add_argument("--grpc-stale-after-seconds", dest="grpc_stale_after_seconds",
                   type=float, default=45.0)
    p.add_argument("--grpc-reconnect-backoff-seconds", dest="grpc_reconnect_backoff_seconds",
                   type=float, default=1.0)
    p.add_argument("--grpc-stop-timeout-seconds", dest="grpc_stop_timeout_seconds",
                   type=float, default=2.0)
    p.add_argument("--grpc-max-reconnects-before-stop",
                   dest="grpc_max_reconnects_before_stop", type=int, default=5,
                   help="fail closed when a repeated reconnect pattern returns.")
    # ---- explicit production history policy; legacy RPC controls stay offline ----
    p.add_argument(
        "--grpc-gap-recovery", dest="grpc_gap_recovery",
        choices=list(GAP_RECOVERY_MODES), default=None,
        help="explicit stream continuity policy. live_epoch = production "
             "starts at the current confirmed head, durably arms H+1, and "
             "does no historical block replay; rpc_backfill and "
             "provider_replay_only remain available for explicit offline "
             "audit/diagnostic use. REQUIRED under --require-production-grpc, "
             "which accepts live_epoch only and also requires the bounded "
             "DexScreener restart-backfill flag.")
    p.add_argument(
        "--enable-dexscreener-restart-backfill",
        dest="enable_dexscreener_restart_backfill",
        action="store_true",
        help="run one bounded PHX1-parity DexScreener discovery sweep at "
             "startup and once after each live-epoch rollover; required by "
             "the armed production contract.",
    )
    p.add_argument(
        "--rpc-recovery-commitment", dest="rpc_recovery_commitment",
        choices=["confirmed", "finalized"], default=None,
        help="authoritative RPC commitment for gap backfill. Must be >= the "
             "live stream's CONFIRMED subscription; REQUIRED for "
             "rpc_backfill; never silently defaulted.")
    p.add_argument("--rpc-recovery-max-gap-slots",
                   dest="rpc_recovery_max_gap_slots", type=int, default=None)
    p.add_argument("--rpc-recovery-max-produced-blocks",
                   dest="rpc_recovery_max_produced_blocks", type=int,
                   default=None)
    p.add_argument("--rpc-recovery-max-transactions",
                   dest="rpc_recovery_max_transactions", type=int, default=None)
    p.add_argument("--rpc-recovery-max-runtime-seconds",
                   dest="rpc_recovery_max_runtime_seconds", type=float,
                   default=None)
    p.add_argument("--rpc-recovery-max-requests",
                   dest="rpc_recovery_max_requests", type=int, default=None)
    p.add_argument("--rpc-recovery-max-retries-per-request",
                   dest="rpc_recovery_max_retries_per_request", type=int,
                   default=None)
    p.add_argument("--rpc-recovery-max-consecutive-failures",
                   dest="rpc_recovery_max_consecutive_failures", type=int,
                   default=None)
    p.add_argument("--rpc-recovery-max-429",
                   dest="rpc_recovery_max_429", type=int, default=None)
    p.add_argument("--rpc-recovery-request-spacing-seconds",
                   dest="rpc_recovery_request_spacing_seconds", type=float,
                   default=None)
    p.add_argument("--rpc-recovery-concurrency",
                   dest="rpc_recovery_concurrency", type=int, default=None)
    p.add_argument("--rpc-recovery-max-quarantine-events",
                   dest="rpc_recovery_max_quarantine_events", type=int,
                   default=None)
    p.add_argument("--rpc-recovery-max-quarantine-bytes",
                   dest="rpc_recovery_max_quarantine_bytes", type=int,
                   default=None)
    p.add_argument("--rpc-recovery-max-quarantine-age-seconds",
                   dest="rpc_recovery_max_quarantine_age_seconds", type=float,
                   default=None)
    p.add_argument("--rpc-recovery-max-commitment-wait-seconds",
                   dest="rpc_recovery_max_commitment_wait_seconds", type=float,
                   default=None)
    p.add_argument("--rpc-recovery-max-overlap-wait-seconds",
                   dest="rpc_recovery_max_overlap_wait_seconds", type=float,
                   default=None)
    # Confirmed-RPC block APPLICATION (decode/scan) worker pool. Ordering,
    # duplicate suppression and checkpointing stay in this process; only the
    # pure decode/scan moves. Every value is refused, never clamped, when it
    # falls outside its explicit bound.
    p.add_argument("--rpc-apply-processes",
                   dest="rpc_apply_processes", type=int, default=None,
                   help=("decode/scan worker processes (1 = in-process serial "
                         "reference; default is derived from CPU count)"))
    p.add_argument("--rpc-apply-queue-bound",
                   dest="rpc_apply_queue_bound", type=int, default=None)
    p.add_argument("--rpc-apply-batch-size",
                   dest="rpc_apply_batch_size", type=int, default=None)
    p.add_argument("--rpc-worker-timeout-seconds",
                   dest="rpc_worker_timeout_seconds", type=float, default=None)
    p.add_argument(
        "--active-soak-seconds", dest="active_soak_seconds", type=float,
        default=0.0,
        help=("seconds required in ACTIVE_STAGE9_SOAK. When > 0 the acceptance "
              "clock replaces wall clock for --max-runtime-seconds and "
              "PRE_SOAK_RECOVERY time is excluded."))
    p.add_argument(
        "--max-wall-clock-seconds", dest="max_wall_clock_seconds", type=float,
        default=86400.0,
        help=("absolute outer boundary used only alongside "
              "--active-soak-seconds, so a soak that never activates still "
              "ends."))
    p.add_argument("--rpc-recovery-checkpoint-every-blocks",
                   dest="rpc_recovery_checkpoint_every_blocks", type=int,
                   default=None)
    p.add_argument("--rpc-recovery-max-resume-attempts",
                   dest="rpc_recovery_max_resume_attempts", type=int,
                   default=None)
    p.add_argument("--provider-dedupe-max-entries", dest="provider_dedupe_max_entries",
                   type=int, default=4096)
    # Seed (discovery) bounds — consumed by the proven build30 _capture_caps.
    p.add_argument("--max-seed-runtime", dest="max_seed_runtime", type=float, default=90.0)
    p.add_argument("--max-notifications", dest="max_notifications", type=int, default=200000)
    p.add_argument("--max-gettransaction", dest="max_gettransaction", type=int, default=128)
    p.add_argument("--max-accepted", dest="max_accepted", type=int, default=10)
    # Polling discovery bounds (POLLING/HYBRID modes). Profile-managed (explicit flag > profile >
    # base default) so a low-credit profile can tighten getSig/getTransaction spend by itself.
    p.add_argument("--poll-pools-per-cycle", dest="poll_pools_per_cycle", type=int, default=None,
                   help="NEW pools examined per poll (=> getSignaturesForAddress calls). "
                        "Profile-managed; base default 8 (live_2h_low_credit: 6).")
    p.add_argument("--poll-sig-page-limit", dest="poll_sig_page_limit", type=int, default=None,
                   help="getSignaturesForAddress page size. Profile-managed; base default 1000 "
                        "(live_2h_low_credit: 500).")
    p.add_argument("--poll-max-gettransaction-per-cycle",
                   dest="poll_max_gettransaction_per_cycle", type=int, default=None,
                   help="getTransaction fetches per poll. Profile-managed; base default 8 "
                        "(live_2h_low_credit: 6).")
    p.add_argument("--poll-max-pool-age-seconds", dest="poll_max_pool_age_seconds", type=int,
                   default=1800)
    p.add_argument("--ws-window-every-n-reseeds", dest="ws_window_every_n_reseeds", type=int,
                   default=None, help="HYBRID only: open a WS window every Nth reseed tick. "
                        "Profile-managed; base default 1 (live_2h_hybrid_thin: 5).")
    # Watch-loop bounds.
    p.add_argument("--recheck-interval-seconds", dest="recheck_interval_seconds", type=float,
                   default=45.0)
    p.add_argument("--max-candidate-age-seconds", dest="max_candidate_age_seconds", type=int,
                   default=3600)
    p.add_argument("--max-rechecks-per-candidate", dest="max_rechecks_per_candidate", type=int,
                   default=240)
    p.add_argument("--max-runtime-seconds", dest="max_runtime_seconds", type=float,
                   default=None, help="profile-managed; base default 7200.")
    p.add_argument(
        "--run-forever", dest="run_forever", action="store_true",
        help=("indefinite runtime for supervised 24/7 operation: no clock "
              "boundary at all. Mutually exclusive with "
              "--max-runtime-seconds / --active-soak-seconds / "
              "--max-total-ticks. Every safety breaker and the cooperative "
              "--stop-file still end the run."))
    p.add_argument("--max-watchlist-size", dest="max_watchlist_size", type=int, default=128)
    p.add_argument("--queue-pressure-max", dest="queue_pressure_max", type=int, default=256)
    p.add_argument("--max-market-calls-total", dest="max_market_calls_total", type=int,
                   default=200000)
    p.add_argument("--reseed-interval-seconds", dest="reseed_interval_seconds", type=float,
                   default=None,
                   help="profile/mode-managed; base default 240 (ws) / 60 (polling) / "
                        "120 (hybrid).")
    p.add_argument("--max-reseeds", dest="max_reseeds", type=int, default=0)
    p.add_argument("--min-seconds-between-sends", dest="min_seconds_between_sends", type=float,
                   default=300.0)
    p.add_argument("--max-consecutive-source-failures", dest="max_consecutive_source_failures",
                   type=int, default=3)
    p.add_argument("--max-consecutive-throttles", dest="max_consecutive_throttles", type=int,
                   default=5)
    p.add_argument("--max-total-ticks", dest="max_total_ticks", type=int, default=0)
    # Market / eligibility.
    p.add_argument("--market-timeout-seconds", dest="market_timeout_seconds", type=int,
                   default=10)
    p.add_argument("--market-fresh-within-seconds", dest="market_fresh_within_seconds",
                   type=float, default=300.0)
    p.add_argument("--birdeye-min-interval-seconds", dest="birdeye_min_interval_seconds",
                   type=float, default=None,
                   help="EXPLICIT request-START spacing override. Default derives "
                        "from --market-provider-spacing-seconds (0.09 s). The old "
                        "1.05 s serialized default could not serve 128 candidates "
                        "inside the 15 s P1 deadline (PHX2-E2E-006).")
    p.add_argument("--birdeye-cache-ttl-seconds", dest="birdeye_cache_ttl_seconds",
                   type=float, default=8.0)
    p.add_argument("--birdeye-max-attempts", dest="birdeye_max_attempts",
                   type=int, default=3)
    # ---- PHX2-E2E-006 P1 scheduler capacity contract ----
    p.add_argument("--market-provider-spacing-seconds",
                   dest="market_provider_spacing_seconds", type=float, default=None,
                   help="request-START spacing across all paid provider workers "
                        "(default 0.09 s ~= 11.1 rps; must match the operator's "
                        "provisioned paid-plan throughput — the 429 credit-budget "
                        "tripwire stops the run observably on a mismatch).")
    p.add_argument("--market-provider-concurrency",
                   dest="market_provider_concurrency", type=int, default=None,
                   help="bounded provider request overlap (default 16; also the "
                        "default worker/in-flight count).")
    p.add_argument("--market-p1-deadline-seconds",
                   dest="market_p1_deadline_seconds", type=float, default=15.0,
                   help="P1 service objective: every tier-due candidate reaches an "
                        "explicit result within this many seconds of its evidence.")
    p.add_argument("--market-healthy-response-budget-seconds",
                   dest="market_healthy_response_budget_seconds", type=float,
                   default=1.5,
                   help="conservative healthy per-request completion budget used "
                        "by the startup capacity proof.")
    p.add_argument("--market-dispatch-overhead-budget-seconds",
                   dest="market_dispatch_overhead_budget_seconds", type=float,
                   default=0.5,
                   help="scheduler dispatch overhead budget in the capacity proof.")
    p.add_argument("--market-p1-max-attempts",
                   dest="market_p1_max_attempts", type=int, default=2,
                   help="maximum provider attempts inside one candidate's P1 "
                        "deadline; retries that cannot fit fail explicitly.")
    p.add_argument("--market-p1-request-timeout-seconds",
                   dest="market_p1_request_timeout_seconds", type=float, default=8.0,
                   help="per-attempt timeout for P1 work; centrally clamped so no "
                        "attempt can outlive the P1 deadline.")
    p.add_argument("--market-p1-reserved-workers",
                   dest="market_p1_reserved_workers", type=int, default=2,
                   help="workers that drain ONLY the P0/P1 fast lane so background "
                        "work can never occupy every worker.")
    p.add_argument("--market-scheduler-workers", dest="market_scheduler_workers",
                   type=int, default=None,
                   help="paid mode: provider worker count (default derives from "
                        "--market-provider-concurrency).")
    p.add_argument("--market-scheduler-max-inflight",
                   dest="market_scheduler_max_inflight", type=int, default=None,
                   help="paid mode: maximum in-flight provider jobs (default "
                        "derives from --market-provider-concurrency).")
    p.add_argument("--market-scheduler-queue-size",
                   dest="market_scheduler_queue_size", type=int, default=256,
                   help="paid mode: bounded deadline queue capacity (per lane).")
    p.add_argument("--market-price-active-ttl-seconds",
                   dest="market_price_active_ttl_seconds", type=float, default=12.0)
    p.add_argument("--market-price-pending-ttl-seconds",
                   dest="market_price_pending_ttl_seconds", type=float, default=30.0)
    p.add_argument("--market-overview-active-ttl-seconds",
                   dest="market_overview_active_ttl_seconds", type=float, default=30.0)
    p.add_argument("--market-overview-pending-ttl-seconds",
                   dest="market_overview_pending_ttl_seconds", type=float, default=90.0)
    p.add_argument("--market-grpc-max-age-seconds",
                   dest="market_grpc_max_age_seconds", type=float, default=15.0)
    p.add_argument("--market-background-starvation-seconds",
                   dest="market_background_starvation_seconds", type=float, default=120.0)
    p.add_argument("--min-liquidity-usd", dest="min_liquidity_usd", default="4500")
    # Bounded escalating market refresh for fresh mints (committed sidecar offsets 0/+10/+30/+60s
    # after migration while price/MC/LP incomplete). 0 restores the old single-attempt behavior.
    p.add_argument("--market-refresh-max-delay-seconds",
                   dest="market_refresh_max_delay_seconds", type=int, default=60)
    p.add_argument("--market-refresh-max-calls-per-token",
                   dest="market_refresh_max_calls_per_token", type=int, default=None,
                   help="bounded escalating market-refresh calls per mint. Profile-managed; base "
                        "default 4 (low-credit profiles: 3).")
    p.add_argument("--market-indexing-grace-seconds",
                   dest="market_indexing_grace_seconds", type=float, default=1800.0,
                   help="paid mode only: bounded newborn indexing/incomplete grace window.")
    p.add_argument("--market-indexing-max-attempts",
                   dest="market_indexing_max_attempts", type=int, default=30,
                   help="paid mode only: per-mint transient attempts before MARKET_UNAVAILABLE.")
    p.add_argument("--allow-birdeye-fallback", dest="allow_birdeye_fallback",
                   action="store_true",
                   help="OPTIONAL keyed market fallback, used only when the free path yields "
                        "nothing AND the env has the key. Default OFF (pure free tier).")
    # Pricing tail (tracks EVERY guard-accepted watchlist mint for paper continuity).
    p.add_argument("--tail-max-tracked", dest="tail_max_tracked", type=int, default=32)
    p.add_argument("--paper-state-file", type=Path,
                   help="explicit atomic paper_state.json feedback for open-position pricing pins")
    p.add_argument("--paper-coverage-required", action="store_true",
                   help="require explicit paper-state feedback configuration before live producer startup")
    p.add_argument("--tail-max-age-seconds", dest="tail_max_age_seconds", type=float,
                   default=21600.0)
    p.add_argument("--tail-poll-interval-seconds", dest="tail_poll_interval_seconds",
                   type=float, default=60.0,
                   help="per-mint minimum seconds between tail market refreshes (bounds spend: "
                        "runtime/interval fetches per tracked mint).")
    # Per-RUN cumulative credit/rate budget (free_tier_credit_budget). The committed capture caps
    # above are per seed WINDOW; these bound the WHOLE run so a long session can never burn an
    # unbounded number of Helius WS/RPC credits or market requests. Crossing a ceiling ends the
    # run at a tick boundary with stop_reason BUDGET_<reason> (exit 0 when invariants held).
    p.add_argument("--max-sends-per-run", dest="max_sends_per_run", type=int, default=None,
                   help="total send attempts per run (would-pings in no-send mode, real private "
                        "pings in armed mode). Profile-managed; base default 3 — CAPPED. "
                        "0 = UNBOUNDED, reserved for the managed 24/7 launcher: a run-forever "
                        "producer must not terminate merely because N alerts were sent; every "
                        "per-send gate (dedupe, tier monotonicity, risk, market completeness, "
                        "crossing-tick block, cooldown) still applies to each dispatch.")
    p.add_argument("--max-raw-ws-notifications-total", "--max-ws-notifications-total",
                   dest="max_raw_ws_notifications_total", type=int, default=None,
                   help="RAW WS message safety cap — counts raw logsSubscribe messages on the "
                        "socket, NOT Helius dashboard credits (observed ~450 raw msgs/s while a "
                        "window is open). Profile-managed; base default 120000. "
                        "--max-ws-notifications-total is the deprecated alias.")
    p.add_argument("--max-seed-windows", dest="max_seed_windows", type=int, default=None,
                   help="profile-managed; base default 120.")
    p.add_argument("--max-candidates-total", dest="max_candidates_total", type=int, default=None,
                   help="profile-managed; base default 400.")
    p.add_argument("--max-gettransaction-total", dest="max_gettransaction_total", type=int,
                   default=None, help="profile-managed; base default 1024.")
    p.add_argument("--max-market-requests-total", dest="max_market_requests_total", type=int,
                   default=None, help="profile-managed; base default 5000.")
    p.add_argument("--max-429-total", dest="max_429_total", type=int, default=None,
                   help="profile-managed; base default 5.")
    p.add_argument("--max-consecutive-ws-errors", dest="max_consecutive_ws_errors", type=int,
                   default=2)
    p.add_argument("--max-rpc-errors-total", dest="max_rpc_errors_total", type=int, default=None,
                   help="profile-managed; base default 12.")
    p.add_argument("--max-polls-total", dest="max_polls_total", type=int, default=None,
                   help="polling-cycle cap (POLLING/HYBRID). Profile-managed; base default 5000.")
    # Production Telegram / dormant Discord rollback (both disabled by default;
    # mutually exclusive and each requires the full arm gate).
    p.add_argument("--enable-telegram", dest="enable_telegram", action="store_true")
    p.add_argument("--enable-private-discord", dest="enable_private_discord",
                   action="store_true")
    p.add_argument("--ack-live-free-tier", dest="ack_live_free_tier", action="store_true")
    p.add_argument("--i-understand-this-can-send", dest="i_understand_this_can_send",
                   action="store_true")
    p.add_argument("--confirm-token", dest="confirm_token", default=None)
    p.add_argument("--require-baseline", dest="require_baseline", default=None)
    p.add_argument("--webhook-identity", dest="webhook_identity", default=None)
    p.add_argument("--operator-label", dest="operator_label", default=None)
    p.add_argument("--authorization-reason", dest="authorization_reason", default=None)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        prog="free_tier_session",
        description="PHX2 live producer (no wallet / no trading / no-send by default; "
                    "production Telegram gated; Discord is dormant rollback code).")
    _add_args(p)
    args = p.parse_args(argv)

    if args.selftest:
        import free_tier_selftest as st
        return st.main()
    if args.preflight:
        return run_preflight(args)
    if args.run:
        return run_producer(args)

    print("[refused] No mode selected. Modes: --selftest | --preflight | --run "
          "(no-send default; production uses --enable-telegram with the full arm gate).")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

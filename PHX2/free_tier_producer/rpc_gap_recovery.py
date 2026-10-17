"""Bounded JSON-RPC gap-backfill recovery for the one Yellowstone stream.

PROVIDER-REPLAY-001 (2026-07-22 live acceptance, ``LIVE_DATA_PATH_NOT_READY``):
the provisioned Yellowstone endpoint refused exact ``from_slot`` replay with
``OUT_OF_RANGE`` on two live attempts, including an approximately one-second-old
safe boundary.  Under the certified reconnect contract that refusal is --
correctly -- terminal: the cursor is preserved, resume refuses, delivery stays
blocked and an operator must intervene.  With a provider that refuses *every*
replay, every disconnect therefore terminal-locks the cursor.

This module adds the ONE sanctioned exit from that terminal state: a bounded,
provider-neutral Solana JSON-RPC backfill that re-proves the unobserved range
``[safe_from_slot .. overlap_target]`` block by block through the SAME
production decoders the gRPC path uses, and closes the episode only on an
exact cross-source overlap proof (same slot, same transaction signature, same
instruction identity, same subscription generation).  Everything else stays
fail-closed:

  * ordinary provider ``from_slot`` replay remains the first choice and its
    certified path is untouched;
  * only a specifically classified replay-retention refusal (the retention
    pre-check, or ``OUT_OF_RANGE`` against a requested replay) may enter RPC
    backfill -- authentication failures, malformed requests, identity
    mismatches, cursor corruption and unknown provider failures never convert;
  * every bound is explicit and a bound exhaustion is a stable terminal
    reason, never a silent resume at the live head;
  * send authorization stays blocked from the disconnect until
    ``RECOVERY_PROVEN`` because the cursor remains terminal-locked until the
    proof lands atomically.

Nothing in this module reads an environment file by itself, prints an endpoint
or credential, or constructs a network object unless its caller supplies a
transport.  The JSON-RPC endpoint is consumed through the same presence-only
projection pattern as the Stage 28.11 gRPC configuration and is never echoed.
"""

from __future__ import annotations

import json
import os
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor
from concurrent.futures import wait as _futures_wait
from dataclasses import dataclass
from pathlib import Path
from typing import (
    Any, Callable, Dict, Iterator, List, Mapping, Optional, Sequence, Tuple,
)

from PHX2.free_tier_producer import checkpoint_envelope as _cpe
from PHX2.free_tier_producer import rpc_block_pool as _rbp
from PHX2.free_tier_producer import rpc_block_scan as _rbs
from PHX2.free_tier_producer.rpc_block_pool import (
    RPC_APPLY_BATCH_SIZE_MAX,
    RPC_APPLY_PROCESSES_MAX,
    RPC_APPLY_QUEUE_BOUND_MAX,
    RPC_WORKER_TIMEOUT_SECONDS_MAX,
    BlockScanPoolError,
    BoundedBlockScanPool,
)
from PHX2.free_tier_producer import stream_cursor as _cursor_mod


# ---------------------------------------------------------------------------
# closed sets
# ---------------------------------------------------------------------------

#: Explicit stream-boundary modes. ``live_epoch`` is the production default:
#: it starts at the current confirmed head and makes no historical coverage
#: claim. The two legacy recovery modes remain available for offline audits.
GAP_RECOVERY_MODE_PROVIDER_REPLAY_ONLY = "provider_replay_only"
GAP_RECOVERY_MODE_RPC_BACKFILL = "rpc_backfill"
GAP_RECOVERY_MODE_LIVE_EPOCH = "live_epoch"
GAP_RECOVERY_MODES = (
    GAP_RECOVERY_MODE_PROVIDER_REPLAY_ONLY,
    GAP_RECOVERY_MODE_RPC_BACKFILL,
    GAP_RECOVERY_MODE_LIVE_EPOCH,
)

#: Conceptual recovery states (Phase 3). ``HEALTHY``/``REPLAY_REQUESTED``/
#: ``REPLAY_REFUSED`` are carried by the existing cursor/owner machinery; the
#: states below are owned by the recovery episode store.
RECOVERY_STATE_IDLE = "IDLE"
RECOVERY_STATE_REPLAY_REFUSED = "REPLAY_REFUSED"
RECOVERY_STATE_RPC_BACKFILL_PLANNED = "RPC_BACKFILL_PLANNED"
RECOVERY_STATE_RPC_BACKFILL_RUNNING = "RPC_BACKFILL_RUNNING"
RECOVERY_STATE_LIVE_STREAM_QUARANTINED = "LIVE_STREAM_QUARANTINED"
RECOVERY_STATE_OVERLAP_PENDING = "OVERLAP_PENDING"
RECOVERY_STATE_RECOVERY_PROVEN = "RECOVERY_PROVEN"
RECOVERY_STATE_RECOVERY_TERMINAL = "RECOVERY_TERMINAL"
#: A bounded ATTEMPT bound was exhausted while every integrity invariant still
#: holds.  This is explicitly NOT an integrity verdict: the durable evidence is
#: intact, the boundary and target are unchanged, and the next attempt resumes
#: at ``last_completed_slot + 1``.  Genuine integrity failures and unknown
#: reasons stay on ``RECOVERY_TERMINAL``.
RECOVERY_STATE_RECOVERY_PAUSED_RETRYABLE = "RECOVERY_PAUSED_RETRYABLE"

RECOVERY_STATES = (
    RECOVERY_STATE_IDLE,
    RECOVERY_STATE_REPLAY_REFUSED,
    RECOVERY_STATE_RPC_BACKFILL_PLANNED,
    RECOVERY_STATE_RPC_BACKFILL_RUNNING,
    RECOVERY_STATE_LIVE_STREAM_QUARANTINED,
    RECOVERY_STATE_OVERLAP_PENDING,
    RECOVERY_STATE_RECOVERY_PAUSED_RETRYABLE,
    RECOVERY_STATE_RECOVERY_PROVEN,
    RECOVERY_STATE_RECOVERY_TERMINAL,
)

#: States in which the episode is live work-in-progress and may be resumed.
RESUMABLE_RECOVERY_STATES = (
    RECOVERY_STATE_REPLAY_REFUSED,
    RECOVERY_STATE_RPC_BACKFILL_PLANNED,
    RECOVERY_STATE_RPC_BACKFILL_RUNNING,
    RECOVERY_STATE_LIVE_STREAM_QUARANTINED,
    RECOVERY_STATE_OVERLAP_PENDING,
    RECOVERY_STATE_RECOVERY_PAUSED_RETRYABLE,
)

# Terminal reasons (closed set). Every bound exhaustion and every structural
# failure lands on exactly one of these; none of them resumes at the live head.
TERMINAL_RPC_BACKFILL_GAP_TOO_LARGE = "RPC_BACKFILL_GAP_TOO_LARGE"
TERMINAL_RPC_BACKFILL_BLOCK_LIMIT_EXCEEDED = "RPC_BACKFILL_BLOCK_LIMIT_EXCEEDED"
TERMINAL_RPC_BACKFILL_TRANSACTION_LIMIT_EXCEEDED = (
    "RPC_BACKFILL_TRANSACTION_LIMIT_EXCEEDED")
TERMINAL_RPC_BACKFILL_REQUEST_LIMIT_EXCEEDED = (
    "RPC_BACKFILL_REQUEST_LIMIT_EXCEEDED")
TERMINAL_RPC_BACKFILL_TIMEOUT = "RPC_BACKFILL_TIMEOUT"
TERMINAL_RPC_BACKFILL_RATE_LIMITED = "RPC_BACKFILL_RATE_LIMITED"
TERMINAL_RPC_BACKFILL_BLOCK_UNAVAILABLE = "RPC_BACKFILL_BLOCK_UNAVAILABLE"
TERMINAL_RPC_BACKFILL_COMMITMENT_TIMEOUT = "RPC_BACKFILL_COMMITMENT_TIMEOUT"
TERMINAL_RPC_BACKFILL_FORK_INCONSISTENT = "RPC_BACKFILL_FORK_INCONSISTENT"
TERMINAL_RECOVERY_OVERLAP_NOT_PROVEN = "RECOVERY_OVERLAP_NOT_PROVEN"
TERMINAL_RECOVERY_BUFFER_CAPACITY_EXCEEDED = "RECOVERY_BUFFER_CAPACITY_EXCEEDED"
TERMINAL_RPC_BACKFILL_ENTRY_INELIGIBLE = (
    "RPC_BACKFILL_ENTRY_CLASSIFICATION_INELIGIBLE")
TERMINAL_RPC_BACKFILL_MALFORMED_RESPONSE = "RPC_BACKFILL_MALFORMED_RESPONSE"
TERMINAL_RPC_BACKFILL_CONSECUTIVE_FAILURES = (
    "RPC_BACKFILL_CONSECUTIVE_FAILURES")
TERMINAL_RPC_BACKFILL_TRANSPORT_ABSENT = "RPC_BACKFILL_TRANSPORT_ABSENT"
TERMINAL_RECOVERY_STATE_QUARANTINED = "RECOVERY_STATE_QUARANTINED"
TERMINAL_RECOVERY_SOURCE_OBSERVER_UNSUPPORTED = (
    "RPC_RECOVERY_SOURCE_OBSERVER_UNSUPPORTED")
TERMINAL_RECOVERY_CURSOR_RESOLUTION_REFUSED = (
    "RECOVERY_CURSOR_RESOLUTION_REFUSED")
#: The bounded decode/scan worker pool could not be started, or could not be
#: kept healthy inside its bounds. This is an ATTEMPT failure, not an integrity
#: verdict: nothing already applied is in doubt, so it is retryable exactly
#: like an exhausted attempt clock. It exists so the coordinator never has to
#: choose between "no pool" and "silently run the known-diverging serial path"
#: during production recovery.
TERMINAL_RPC_APPLY_POOL_UNAVAILABLE = "RPC_APPLY_POOL_UNAVAILABLE"

RECOVERY_TERMINAL_REASONS = (
    TERMINAL_RPC_BACKFILL_GAP_TOO_LARGE,
    TERMINAL_RPC_BACKFILL_BLOCK_LIMIT_EXCEEDED,
    TERMINAL_RPC_BACKFILL_TRANSACTION_LIMIT_EXCEEDED,
    TERMINAL_RPC_BACKFILL_REQUEST_LIMIT_EXCEEDED,
    TERMINAL_RPC_BACKFILL_TIMEOUT,
    TERMINAL_RPC_BACKFILL_RATE_LIMITED,
    TERMINAL_RPC_BACKFILL_BLOCK_UNAVAILABLE,
    TERMINAL_RPC_BACKFILL_COMMITMENT_TIMEOUT,
    TERMINAL_RPC_BACKFILL_FORK_INCONSISTENT,
    TERMINAL_RECOVERY_OVERLAP_NOT_PROVEN,
    TERMINAL_RECOVERY_BUFFER_CAPACITY_EXCEEDED,
    TERMINAL_RPC_BACKFILL_ENTRY_INELIGIBLE,
    TERMINAL_RPC_BACKFILL_MALFORMED_RESPONSE,
    TERMINAL_RPC_BACKFILL_CONSECUTIVE_FAILURES,
    TERMINAL_RPC_BACKFILL_TRANSPORT_ABSENT,
    TERMINAL_RECOVERY_STATE_QUARANTINED,
    TERMINAL_RECOVERY_SOURCE_OBSERVER_UNSUPPORTED,
    TERMINAL_RECOVERY_CURSOR_RESOLUTION_REFUSED,
    TERMINAL_RPC_APPLY_POOL_UNAVAILABLE,
)

#: Red-test anchor: the buffer-overflow terminal reason under its own name.
TERMINAL_RECOVERY_BUFFER_CAPACITY_EXCEEDED_TOKEN = (
    TERMINAL_RECOVERY_BUFFER_CAPACITY_EXCEEDED)

#: Reasons that may pause retryably instead of ending the episode. Membership
#: here is necessary but never sufficient: every integrity invariant in
#: :func:`recovery_pause_invariants` must also hold, or the reason stays
#: terminal.  Deliberately narrow -- an exhausted ATTEMPT clock says nothing
#: about the integrity of what was already committed, whereas fork
#: inconsistency, malformed responses, unavailable blocks, overlap failure and
#: quarantine all do.
PAUSE_RPC_BACKFILL_TIMEOUT = TERMINAL_RPC_BACKFILL_TIMEOUT
PAUSE_RPC_APPLY_POOL_UNAVAILABLE = TERMINAL_RPC_APPLY_POOL_UNAVAILABLE
RECOVERY_RETRYABLE_PAUSE_REASONS = (
    PAUSE_RPC_BACKFILL_TIMEOUT,
    PAUSE_RPC_APPLY_POOL_UNAVAILABLE,
)

#: Closed-set outcomes of :meth:`RpcGapRecoveryStore.upgrade_terminal_to_retryable`.
UPGRADE_APPLIED = "RECOVERY_TERMINAL_UPGRADED_TO_RETRYABLE"
UPGRADE_ALREADY_RETRYABLE = "RECOVERY_ALREADY_RETRYABLE"
UPGRADE_REFUSED_NOT_TERMINAL = "RECOVERY_UPGRADE_REFUSED_NOT_TERMINAL"
UPGRADE_REFUSED_REASON_NOT_RETRYABLE = (
    "RECOVERY_UPGRADE_REFUSED_REASON_NOT_RETRYABLE")
UPGRADE_REFUSED_STORE_QUARANTINED = "RECOVERY_UPGRADE_REFUSED_STORE_QUARANTINED"
UPGRADE_REFUSED_INTEGRITY = "RECOVERY_UPGRADE_REFUSED_INTEGRITY"
UPGRADE_REFUSED_WRITE_FAILED = "RECOVERY_UPGRADE_REFUSED_WRITE_FAILED"
UPGRADE_OUTCOMES = (
    UPGRADE_APPLIED,
    UPGRADE_ALREADY_RETRYABLE,
    UPGRADE_REFUSED_NOT_TERMINAL,
    UPGRADE_REFUSED_REASON_NOT_RETRYABLE,
    UPGRADE_REFUSED_STORE_QUARANTINED,
    UPGRADE_REFUSED_INTEGRITY,
    UPGRADE_REFUSED_WRITE_FAILED,
)

# Entry classifications. Only the two retention-shaped refusals may enter the
# bounded backfill; everything else stays terminal exactly as certified.
ENTRY_REPLAY_RETENTION_PRECHECK = "REPLAY_RETENTION_PRECHECK"
ENTRY_REPLAY_REFUSED_OUT_OF_RANGE = "REPLAY_REFUSED_OUT_OF_RANGE"
ENTRY_INELIGIBLE = "INELIGIBLE"
ENTRY_CLASSIFICATIONS = (
    ENTRY_REPLAY_RETENTION_PRECHECK,
    ENTRY_REPLAY_REFUSED_OUT_OF_RANGE,
    ENTRY_INELIGIBLE,
)
BACKFILL_ELIGIBLE_CLASSIFICATIONS = (
    ENTRY_REPLAY_RETENTION_PRECHECK,
    ENTRY_REPLAY_REFUSED_OUT_OF_RANGE,
)

#: Authoritative RPC commitments the backfill may use. ``processed`` is
#: deliberately absent: it is weaker than the live stream's CONFIRMED
#: subscription and a processed-level block can be abandoned by the cluster.
AUTHORITATIVE_COMMITMENTS = ("confirmed", "finalized")

#: The live Yellowstone subscription's commitment, stated explicitly so the
#: commitment relationship is a checked contract rather than an assumption
#: (see ``build_pumpswap_subscribe_request``: ``commitment = CONFIRMED``).
LIVE_STREAM_COMMITMENT = "confirmed"

# Overlap proof states.
OVERLAP_NOT_PROVEN = "NOT_PROVEN"
OVERLAP_PROVEN = "PROVEN"

#: Safe provider label attached to candidates decoded through the RPC bridge.
#: Deliberately vendor-neutral: the adapter must work against any standard
#: Solana JSON-RPC provider and no vendor name may reach an artifact.
RPC_RECOVERY_PROVIDER_LABEL = "rpc_backfill_recovery"

#: Buffered-event kinds.
BUFFER_EVENT_TRANSACTION_OBSERVED = "TRANSACTION_OBSERVED"
BUFFER_EVENT_MIGRATION_ADMITTED = "MIGRATION_ADMITTED"
BUFFER_EVENT_KINDS = (
    BUFFER_EVENT_TRANSACTION_OBSERVED, BUFFER_EVENT_MIGRATION_ADMITTED)


# ---------------------------------------------------------------------------
# configuration
# ---------------------------------------------------------------------------

# Environment surface (presence-only projection; values never echoed).
ENV_NAME_RPC_RECOVERY_ENDPOINT = "PHX2_RPC_RECOVERY_HTTP_ENDPOINT"
ENV_NAME_RPC_RECOVERY_TIMEOUT_SECONDS = (
    "PHX2_RPC_RECOVERY_HTTP_TIMEOUT_SECONDS")
RPC_RECOVERY_READ_ENV_NAMES = (
    ENV_NAME_RPC_RECOVERY_ENDPOINT,
    ENV_NAME_RPC_RECOVERY_TIMEOUT_SECONDS,
)

DEFAULT_RPC_RECOVERY_TIMEOUT_SECONDS = 20.0

#: Stable, vendor-neutral client identifier sent as the JSON-RPC ``User-Agent``.
#: Rationale (proven 2026-07-22): with no explicit User-Agent, ``urllib`` attaches
#: its default ``Python-urllib/<version>`` header, which the provider's HTTP
#: front door rejects with ``403 Forbidden`` (a ``text/plain`` body, NOT a
#: JSON-RPC error).  A request that is byte-for-byte identical except for this
#: single header returns ``200`` with a valid ``result``.  Setting an explicit
#: User-Agent is therefore the smallest fix.  The value carries NO secret and NO
#: provider name; it never exposes the endpoint, a token or any credential, and
#: does not alter any request bound, the commitment, or the fail-closed contract.
RPC_RECOVERY_USER_AGENT = "PHX2-RPC-Recovery/1.0"

#: Tested upper bound on bounded fetch concurrency. The production default
#: stays 1 (unchanged, conservative); a large inherited gap raises it
#: explicitly at the launcher. The ceiling exists so a typo cannot open an
#: unbounded number of sockets against the provider.
RPC_CONCURRENCY_MAX = 32
#: Bound on in-flight fetched blocks, expressed as a multiple of concurrency.
#: Blocks are applied in canonical order, so an out-of-order completion is held
#: in memory until its turn; this caps that hold-back.
RPC_INFLIGHT_WINDOW_MULTIPLIER = 2
#: Pressure backoff: spacing multiplier ceiling, and how many consecutive clean
#: requests halve it back down.
MAX_PRESSURE_MULTIPLIER = 16.0
PRESSURE_DECAY_CLEAN_REQUESTS = 64

# Closed-set configuration refusal tokens.
CONFIG_REFUSAL_MODE_INVALID = "RPC_RECOVERY_MODE_INVALID"
CONFIG_REFUSAL_MODE_ABSENT = "RPC_RECOVERY_MODE_ABSENT"
CONFIG_REFUSAL_COMMITMENT_INVALID = "RPC_RECOVERY_COMMITMENT_INVALID"
CONFIG_REFUSAL_ENDPOINT_ABSENT = "RPC_RECOVERY_ENDPOINT_ABSENT"
CONFIG_REFUSAL_BOUND_INVALID_PREFIX = "RPC_RECOVERY_CONFIG_INVALID"


def _positive_int(value: object) -> bool:
    return (isinstance(value, int) and not isinstance(value, bool)
            and value > 0)


def _positive_number(value: object) -> bool:
    if isinstance(value, bool):
        return False
    return isinstance(value, (int, float)) and value > 0


@dataclass(frozen=True)
class RpcGapRecoveryConfig:
    """Every recovery bound, explicit and fail-closed.

    The defaults below are derived from the measured production environment,
    not invented to satisfy tests:

    * ``max_gap_slots`` 1800: reconnect gaps observed live are seconds long
      (the failed acceptance refused an ~1 second boundary); 1800 slots is
      ~12 minutes at the ~2.5 slot/s mainnet rate -- an entire operator
      response window, far beyond any observed disconnect, while still
      bounding the worst case well below an outage-scale range.
    * ``max_produced_blocks`` 1600 / ``max_transactions`` 4_000_000: mainnet
      produces a block for the large majority of slots and a block carries on
      the order of a thousand transactions; 1800 slots therefore cannot need
      more than ~1600 block fetches or ~4M transaction scans.
    * ``max_rpc_requests`` 4096 and ``rpc_request_spacing_seconds`` 0.25: the
      2026-07-21 provider-capacity acceptance sustained 272 requests with
      zero HTTP 429 and p99 506 ms; four requests per second is comfortably
      inside that envelope and 4096 requests covers the block budget with
      retries.
    * ``max_backfill_runtime_seconds`` 1800: one ``launch_window_04`` run --
      a recovery that cannot complete inside the shortest canonical window is
      an operator decision, not an automatic one.
    * quarantine bounds (4096 events / 16 MiB / 3600 s): candidate handoffs
      are already bounded by the owner queue at 256; 4096 buffered identities
      with decoded evidence is an order of magnitude of headroom while
      keeping the authenticated buffer document small enough to rewrite on
      every append.
    """

    mode: str = GAP_RECOVERY_MODE_PROVIDER_REPLAY_ONLY
    authoritative_commitment: Optional[str] = None
    max_gap_slots: int = 1800
    max_produced_blocks: int = 1600
    max_transactions: int = 4_000_000
    max_backfill_runtime_seconds: float = 1800.0
    max_rpc_requests: int = 4096
    max_retries_per_request: int = 3
    max_consecutive_rpc_failures: int = 8
    max_http_429_responses: int = 16
    rpc_request_spacing_seconds: float = 0.25
    rpc_concurrency: int = 1
    max_quarantine_events: int = 4096
    max_quarantine_bytes: int = 16 * 1024 * 1024
    max_quarantine_age_seconds: float = 3600.0
    max_commitment_wait_seconds: float = 120.0
    max_overlap_wait_seconds: float = 900.0
    #: Blocks applied between durable checkpoints. 1 preserves the original
    #: per-block behaviour; a large inherited gap raises it so the authenticated
    #: rewrite stops dominating the catch-up. Resume replays at most this many
    #: blocks, and every replayed event is duplicate-suppressed.
    checkpoint_every_blocks: int = 1
    #: How many times one process may resume a retryably paused episode before
    #: the pre-soak gives up and exits NOT_READY rather than looping forever.
    max_backfill_resume_attempts: int = 64
    #: Worker PROCESSES for the pure decode/scan stage. 1 keeps the whole scan
    #: in this process (the serial reference). Above 1 the authoritative
    #: process stops doing JSON decode and transaction scanning under the GIL,
    #: which is the measured cause of the ~1.6 blocks/second application rate
    #: against ~2.5 blocks/second of chain growth. Ordering, duplicate
    #: suppression and checkpointing stay here regardless.
    rpc_apply_processes: int = 1
    #: Maximum batches in flight to the pool at once (input AND output depth).
    rpc_apply_queue_bound: int = 8
    #: Produced blocks per worker batch.
    rpc_apply_batch_size: int = 4
    #: Wall-clock a batch may take before the pool is rebuilt (bounded).
    rpc_worker_timeout_seconds: float = 120.0

    def snapshot(self) -> Dict[str, Any]:
        """Redaction-safe numeric/categorical view for startup echo."""

        return {
            "grpc_gap_recovery_mode": self.mode,
            "rpc_recovery_authoritative_commitment": self.authoritative_commitment,
            "rpc_recovery_live_stream_commitment": LIVE_STREAM_COMMITMENT,
            "rpc_recovery_max_gap_slots": self.max_gap_slots,
            "rpc_recovery_max_produced_blocks": self.max_produced_blocks,
            "rpc_recovery_max_transactions": self.max_transactions,
            "rpc_recovery_max_backfill_runtime_seconds": (
                self.max_backfill_runtime_seconds),
            "rpc_recovery_max_rpc_requests": self.max_rpc_requests,
            "rpc_recovery_max_retries_per_request": self.max_retries_per_request,
            "rpc_recovery_max_consecutive_rpc_failures": (
                self.max_consecutive_rpc_failures),
            "rpc_recovery_max_http_429_responses": self.max_http_429_responses,
            "rpc_recovery_request_spacing_seconds": (
                self.rpc_request_spacing_seconds),
            "rpc_recovery_concurrency": self.rpc_concurrency,
            "rpc_recovery_max_quarantine_events": self.max_quarantine_events,
            "rpc_recovery_max_quarantine_bytes": self.max_quarantine_bytes,
            "rpc_recovery_max_quarantine_age_seconds": (
                self.max_quarantine_age_seconds),
            "rpc_recovery_max_commitment_wait_seconds": (
                self.max_commitment_wait_seconds),
            "rpc_recovery_max_overlap_wait_seconds": (
                self.max_overlap_wait_seconds),
            "rpc_recovery_checkpoint_every_blocks": (
                self.checkpoint_every_blocks),
            "rpc_recovery_max_backfill_resume_attempts": (
                self.max_backfill_resume_attempts),
            "rpc_recovery_concurrency_ceiling": RPC_CONCURRENCY_MAX,
            "rpc_apply_processes": self.rpc_apply_processes,
            "rpc_apply_queue_bound": self.rpc_apply_queue_bound,
            "rpc_apply_batch_size": self.rpc_apply_batch_size,
            "rpc_worker_timeout_seconds": self.rpc_worker_timeout_seconds,
        }


def validate_rpc_gap_recovery_config(
    config: RpcGapRecoveryConfig,
) -> List[str]:
    """Closed-set refusal tokens; empty means valid. Nothing is clamped."""

    refusals: List[str] = []
    if config.mode not in GAP_RECOVERY_MODES:
        refusals.append(CONFIG_REFUSAL_MODE_INVALID)
    if config.mode == GAP_RECOVERY_MODE_RPC_BACKFILL:
        if config.authoritative_commitment not in AUTHORITATIVE_COMMITMENTS:
            refusals.append(CONFIG_REFUSAL_COMMITMENT_INVALID)
    elif config.authoritative_commitment is not None \
            and config.authoritative_commitment not in AUTHORITATIVE_COMMITMENTS:
        refusals.append(CONFIG_REFUSAL_COMMITMENT_INVALID)
    int_bounds = (
        ("max_gap_slots", config.max_gap_slots),
        ("max_produced_blocks", config.max_produced_blocks),
        ("max_transactions", config.max_transactions),
        ("max_rpc_requests", config.max_rpc_requests),
        ("max_retries_per_request", config.max_retries_per_request),
        ("max_consecutive_rpc_failures", config.max_consecutive_rpc_failures),
        ("max_http_429_responses", config.max_http_429_responses),
        ("rpc_concurrency", config.rpc_concurrency),
        ("max_quarantine_events", config.max_quarantine_events),
        ("max_quarantine_bytes", config.max_quarantine_bytes),
    )
    for name, value in int_bounds:
        if not _positive_int(value):
            refusals.append(
                f"{CONFIG_REFUSAL_BOUND_INVALID_PREFIX}:{name.upper()}")
    number_bounds = (
        ("max_backfill_runtime_seconds", config.max_backfill_runtime_seconds),
        ("rpc_request_spacing_seconds", config.rpc_request_spacing_seconds),
        ("max_quarantine_age_seconds", config.max_quarantine_age_seconds),
        ("max_commitment_wait_seconds", config.max_commitment_wait_seconds),
        ("max_overlap_wait_seconds", config.max_overlap_wait_seconds),
    )
    for name, value in number_bounds:
        if not _positive_number(value):
            refusals.append(
                f"{CONFIG_REFUSAL_BOUND_INVALID_PREFIX}:{name.upper()}")
    # Concurrency is bounded on BOTH sides: it fetches in parallel but always
    # applies in canonical slot order, so the ceiling protects the provider and
    # the in-flight hold-back, never determinism.
    if _positive_int(config.rpc_concurrency) \
            and config.rpc_concurrency > RPC_CONCURRENCY_MAX:
        refusals.append(
            f"{CONFIG_REFUSAL_BOUND_INVALID_PREFIX}:RPC_CONCURRENCY")
    if not _positive_int(config.checkpoint_every_blocks):
        refusals.append(
            f"{CONFIG_REFUSAL_BOUND_INVALID_PREFIX}:CHECKPOINT_EVERY_BLOCKS")
    if not _positive_int(config.max_backfill_resume_attempts):
        refusals.append(
            f"{CONFIG_REFUSAL_BOUND_INVALID_PREFIX}:MAX_BACKFILL_RESUME_ATTEMPTS")
    # Worker-pool bounds fail closed on BOTH sides: an out-of-range value is
    # refused, never clamped, so no configuration can create unbounded
    # processes or unbounded retained block payloads.
    pool_int_bounds = (
        ("RPC_APPLY_PROCESSES", config.rpc_apply_processes,
         RPC_APPLY_PROCESSES_MAX),
        ("RPC_APPLY_QUEUE_BOUND", config.rpc_apply_queue_bound,
         RPC_APPLY_QUEUE_BOUND_MAX),
        ("RPC_APPLY_BATCH_SIZE", config.rpc_apply_batch_size,
         RPC_APPLY_BATCH_SIZE_MAX),
    )
    for name, value, ceiling in pool_int_bounds:
        if not _positive_int(value) or value > ceiling:
            refusals.append(
                f"{CONFIG_REFUSAL_BOUND_INVALID_PREFIX}:{name}")
    if not _positive_number(config.rpc_worker_timeout_seconds) \
            or config.rpc_worker_timeout_seconds > (
                RPC_WORKER_TIMEOUT_SECONDS_MAX):
        refusals.append(
            f"{CONFIG_REFUSAL_BOUND_INVALID_PREFIX}:RPC_WORKER_TIMEOUT_SECONDS")
    return refusals


def project_rpc_recovery_env_safe(
    env: Optional[Mapping[str, str]] = None,
) -> Dict[str, str]:
    """Presence-only projection of the recovery env surface. Values withheld."""

    source: Mapping[str, str] = env if env is not None else os.environ
    endpoint = (source.get(ENV_NAME_RPC_RECOVERY_ENDPOINT) or "").strip()
    timeout_raw = (
        source.get(ENV_NAME_RPC_RECOVERY_TIMEOUT_SECONDS) or "").strip()
    timeout_status = "DEFAULT"
    if timeout_raw:
        try:
            timeout_status = (
                "OVERRIDE" if float(timeout_raw) > 0 else "INVALID")
        except ValueError:
            timeout_status = "INVALID"
    return {
        "rpc_recovery_endpoint": "PRESENT" if endpoint else "MISSING",
        "rpc_recovery_timeout": timeout_status,
    }


def build_rpc_transport_from_env(
    env: Optional[Mapping[str, str]] = None,
) -> Optional[Callable[[str, List[Any], float], Tuple[int, Optional[Dict[str, Any]]]]]:
    """A provider-neutral JSON-RPC POST transport, or ``None`` when unconfigured.

    The endpoint value is captured in a closure and never echoed, mirroring the
    polling-discovery transport.  The returned callable performs a real network
    POST and must therefore never be invoked from offline tests -- tests inject
    their own fake transport instead.
    """

    source: Mapping[str, str] = env if env is not None else os.environ
    endpoint = (source.get(ENV_NAME_RPC_RECOVERY_ENDPOINT) or "").strip()
    if not endpoint or not endpoint.lower().startswith("https://"):
        return None
    timeout_raw = (
        source.get(ENV_NAME_RPC_RECOVERY_TIMEOUT_SECONDS) or "").strip()
    try:
        timeout_default = float(timeout_raw) if timeout_raw else (
            DEFAULT_RPC_RECOVERY_TIMEOUT_SECONDS)
    except ValueError:
        timeout_default = DEFAULT_RPC_RECOVERY_TIMEOUT_SECONDS
    if timeout_default <= 0:
        timeout_default = DEFAULT_RPC_RECOVERY_TIMEOUT_SECONDS

    def _rpc_post(method: str, params: List[Any],
                  timeout_seconds: float = timeout_default,
                  raw: bool = False,
                  ) -> Tuple[int, Optional[Any]]:
        # Real read-only JSON-RPC POST. The URL lives only in this closure and
        # is NEVER printed; HTTP error statuses are RETURNED so the caller can
        # count 429 pressure instead of losing it to an exception.
        #
        # ``raw=True`` returns the UNDECODED response body so the expensive
        # JSON decode can be performed by a worker PROCESS instead of by the
        # authoritative process under the GIL.  Nothing else differs: same
        # endpoint closure, same headers, same bounds, same status semantics.
        import urllib.error
        import urllib.request

        body = json.dumps({
            "jsonrpc": "2.0", "id": 1, "method": str(method),
            "params": list(params),
        }).encode("utf-8")
        # An explicit User-Agent is REQUIRED: urllib's default
        # ``Python-urllib/<version>`` header is rejected by the provider front
        # door with HTTP 403 (see ``RPC_RECOVERY_USER_AGENT``). No Authorization
        # header is set -- the endpoint authenticates via its own tokenized path.
        request = urllib.request.Request(
            endpoint, data=body,
            headers={
                "content-type": "application/json",
                "user-agent": RPC_RECOVERY_USER_AGENT,
            }, method="POST")
        try:
            with urllib.request.urlopen(
                    request, timeout=float(timeout_seconds)) as response:
                body_bytes = response.read()
                status = int(getattr(response, "status", 200) or 200)
        except urllib.error.HTTPError as err:
            return int(err.code), None
        except Exception:
            return 0, None
        if raw:
            return status, (bytes(body_bytes) if body_bytes else None)
        try:
            parsed = json.loads(body_bytes.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return status, None
        return status, parsed if isinstance(parsed, dict) else None

    _rpc_post.supports_raw_bodies = True  # type: ignore[attr-defined]
    return _rpc_post


# ---------------------------------------------------------------------------
# replay-refusal classification
# ---------------------------------------------------------------------------

def classify_replay_refusal(
    *,
    replay_requested: bool,
    replay_position_rejected: bool,
    sanitized_error_category: Optional[str],
    grpc_status_code: Optional[str],
) -> str:
    """Which refusal happened, from the source's closed-set diagnostics only.

    Only two shapes are retention refusals: the explicit retention pre-check
    (``SubscribeReplayInfo`` said the boundary is older than ``first_available``)
    and a provider ``OUT_OF_RANGE`` against a requested replay -- the exact
    live-acceptance failure.  ``INVALID_ARGUMENT`` (a malformed request) and
    ``NOT_FOUND`` (unknown meaning) remain terminal without conversion, as do
    authentication failures and everything else.
    """

    if not replay_requested or not replay_position_rejected:
        return ENTRY_INELIGIBLE
    if sanitized_error_category == "REPLAY_RETENTION_EXCEEDED":
        return ENTRY_REPLAY_RETENTION_PRECHECK
    if grpc_status_code == "OUT_OF_RANGE":
        return ENTRY_REPLAY_REFUSED_OUT_OF_RANGE
    return ENTRY_INELIGIBLE


# ---------------------------------------------------------------------------
# recovery episode store (authenticated)
# ---------------------------------------------------------------------------

CHECKPOINT_KIND_RPC_GAP_RECOVERY = "PHX2_RPC_GAP_RECOVERY"
RPC_GAP_RECOVERY_SCHEMA_V1 = "phx2_rpc_gap_recovery_v1"
RECOVERY_RECORD_KIND = "PHX2_RPC_GAP_RECOVERY_STATE"
RECOVERY_PRIMARY_BASENAME = "rpc_gap_recovery.json"


class RecoveryStoreWriteError(RuntimeError):
    """The recovery episode could not be persisted; previous generation stands."""


class QuarantineBufferCapacityExceeded(RuntimeError):
    """A quarantine bound would be crossed; the event was NOT silently dropped."""


@dataclass
class RpcGapRecoveryState:
    """One recovery episode. ``safe_from_slot`` is immutable once opened."""

    recovery_mode: str = GAP_RECOVERY_MODE_RPC_BACKFILL
    recovery_state: str = RECOVERY_STATE_IDLE
    entry_classification: str = ENTRY_INELIGIBLE
    subscription_identity_digest: str = ""
    authoritative_commitment: str = ""
    episode_generation: int = 0
    cursor_recovery_generation: int = 0
    cursor_attempt_generation: int = 0
    safe_from_slot: int = -1
    recovery_target_slot: Optional[int] = None
    quarantined_live_first_slot: Optional[int] = None
    overlap_slot: Optional[int] = None
    overlap_signature: Optional[str] = None
    overlap_skip_identity: Optional[str] = None
    overlap_proof_state: str = OVERLAP_NOT_PROVEN
    last_completed_slot: Optional[int] = None
    last_completed_blockhash: Optional[str] = None
    produced_blocks_total: int = 0
    produced_blocks_completed: int = 0
    skipped_slots_total: int = 0
    transactions_scanned: int = 0
    transactions_relevant: int = 0
    transactions_rejected: int = 0
    migration_events_recovered: int = 0
    reserve_events_recovered: int = 0
    fee_events_recovered: int = 0
    duplicate_events_suppressed: int = 0
    unseen_buffered_events_applied: int = 0
    rpc_request_count: int = 0
    rpc_retry_count: int = 0
    rpc_timeout_count: int = 0
    rpc_429_count: int = 0
    rpc_error_count: int = 0
    backfill_runtime_ms: int = 0
    quarantine_segments: int = 0
    terminal_reason: Optional[str] = None
    # -- retryable pause / terminal-history fields (Phase 3/4) --------------
    #: Set only while ``recovery_state`` is ``RECOVERY_PAUSED_RETRYABLE``.
    paused_reason: Optional[str] = None
    #: How many times this episode paused retryably.
    pause_count: int = 0
    #: How many times a paused episode was resumed.
    resume_attempts: int = 0
    #: Original terminal verdict, RETAINED forever once a terminal record is
    #: upgraded, so the upgrade never erases the history it supersedes.
    prior_terminal_reason: Optional[str] = None
    prior_terminal_at_utc: Optional[str] = None
    #: Number of terminal -> retryable upgrades applied to this episode.
    terminal_upgrade_count: int = 0
    opened_at_utc: Optional[str] = None
    updated_at_utc: Optional[str] = None

    def to_record(self) -> Dict[str, Any]:
        return {
            "record_kind": RECOVERY_RECORD_KIND,
            "recovery_mode": str(self.recovery_mode),
            "recovery_state": str(self.recovery_state),
            "entry_classification": str(self.entry_classification),
            "subscription_identity_digest": str(
                self.subscription_identity_digest),
            "authoritative_commitment": str(self.authoritative_commitment),
            "episode_generation": int(self.episode_generation),
            "cursor_recovery_generation": int(self.cursor_recovery_generation),
            "cursor_attempt_generation": int(self.cursor_attempt_generation),
            "safe_from_slot": int(self.safe_from_slot),
            "recovery_target_slot": (
                None if self.recovery_target_slot is None
                else int(self.recovery_target_slot)),
            "quarantined_live_first_slot": (
                None if self.quarantined_live_first_slot is None
                else int(self.quarantined_live_first_slot)),
            "overlap_slot": (
                None if self.overlap_slot is None else int(self.overlap_slot)),
            "overlap_signature": self.overlap_signature,
            "overlap_skip_identity": self.overlap_skip_identity,
            "overlap_proof_state": str(self.overlap_proof_state),
            "last_completed_slot": (
                None if self.last_completed_slot is None
                else int(self.last_completed_slot)),
            "last_completed_blockhash": self.last_completed_blockhash,
            "produced_blocks_total": int(self.produced_blocks_total),
            "produced_blocks_completed": int(self.produced_blocks_completed),
            "skipped_slots_total": int(self.skipped_slots_total),
            "transactions_scanned": int(self.transactions_scanned),
            "transactions_relevant": int(self.transactions_relevant),
            "transactions_rejected": int(self.transactions_rejected),
            "migration_events_recovered": int(self.migration_events_recovered),
            "reserve_events_recovered": int(self.reserve_events_recovered),
            "fee_events_recovered": int(self.fee_events_recovered),
            "duplicate_events_suppressed": int(self.duplicate_events_suppressed),
            "unseen_buffered_events_applied": int(
                self.unseen_buffered_events_applied),
            "rpc_request_count": int(self.rpc_request_count),
            "rpc_retry_count": int(self.rpc_retry_count),
            "rpc_timeout_count": int(self.rpc_timeout_count),
            "rpc_429_count": int(self.rpc_429_count),
            "rpc_error_count": int(self.rpc_error_count),
            "backfill_runtime_ms": int(self.backfill_runtime_ms),
            "quarantine_segments": int(self.quarantine_segments),
            "terminal_reason": self.terminal_reason,
            "paused_reason": self.paused_reason,
            "pause_count": int(self.pause_count),
            "resume_attempts": int(self.resume_attempts),
            "prior_terminal_reason": self.prior_terminal_reason,
            "prior_terminal_at_utc": self.prior_terminal_at_utc,
            "terminal_upgrade_count": int(self.terminal_upgrade_count),
            "opened_at_utc": self.opened_at_utc,
            "updated_at_utc": self.updated_at_utc,
        }

    @classmethod
    def from_record(cls, record: Mapping[str, Any]) -> "RpcGapRecoveryState":
        state = cls()
        for name in state.__dataclass_fields__:
            if name in record:
                setattr(state, name, record[name])
        return state

    def clone(self) -> "RpcGapRecoveryState":
        return RpcGapRecoveryState.from_record(self.to_record())


_RECOVERY_REQUIRED_INT_FIELDS = (
    "episode_generation", "cursor_recovery_generation",
    "cursor_attempt_generation", "safe_from_slot",
    "produced_blocks_total", "produced_blocks_completed",
    "skipped_slots_total", "transactions_scanned", "transactions_relevant",
    "transactions_rejected", "migration_events_recovered",
    "reserve_events_recovered", "fee_events_recovered",
    "duplicate_events_suppressed", "unseen_buffered_events_applied",
    "rpc_request_count", "rpc_retry_count", "rpc_timeout_count",
    "rpc_429_count", "rpc_error_count", "backfill_runtime_ms",
    "quarantine_segments",
)

_RECOVERY_OPTIONAL_SLOT_FIELDS = (
    "recovery_target_slot", "quarantined_live_first_slot", "overlap_slot",
    "last_completed_slot",
)

#: Counters introduced with the retryable pause. They are validated when
#: present but deliberately NOT required: a record written before this change
#: is still a valid, authentic record and must keep loading rather than
#: quarantining on a field it could not have carried.
_RECOVERY_OPTIONAL_INT_FIELDS = (
    "pause_count", "resume_attempts", "terminal_upgrade_count",
)


def validate_recovery_record(record: Mapping[str, Any]) -> Tuple[bool, str]:
    """Kind-specific validation for the recovery checkpoint envelope."""

    if record.get("record_kind") != RECOVERY_RECORD_KIND:
        return False, _cpe.QUARANTINE_KIND_INVALID
    if record.get("recovery_mode") not in GAP_RECOVERY_MODES:
        return False, _cpe.QUARANTINE_STATUS_UNSUPPORTED
    if record.get("recovery_state") not in RECOVERY_STATES:
        return False, _cpe.QUARANTINE_STATUS_UNSUPPORTED
    if record.get("entry_classification") not in ENTRY_CLASSIFICATIONS:
        return False, _cpe.QUARANTINE_STATUS_UNSUPPORTED
    if record.get("overlap_proof_state") not in (
            OVERLAP_NOT_PROVEN, OVERLAP_PROVEN):
        return False, _cpe.QUARANTINE_STATUS_UNSUPPORTED
    for name in _RECOVERY_REQUIRED_INT_FIELDS:
        value = record.get(name)
        if isinstance(value, bool) or not isinstance(value, int):
            return False, _cpe.QUARANTINE_NUMERIC_INVALID
        if name != "safe_from_slot" and value < 0:
            return False, _cpe.QUARANTINE_NUMERIC_INVALID
    if int(record.get("safe_from_slot", -1)) < -1:
        return False, _cpe.QUARANTINE_NUMERIC_INVALID
    for name in _RECOVERY_OPTIONAL_SLOT_FIELDS:
        value = record.get(name)
        if value is None:
            continue
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            return False, _cpe.QUARANTINE_NUMERIC_INVALID
    if not _cpe.is_sha256_digest(record.get("subscription_identity_digest")):
        return False, _cpe.QUARANTINE_CANDIDATE_BINDING_INVALID
    for name in _RECOVERY_OPTIONAL_INT_FIELDS:
        if name not in record:
            continue
        value = record.get(name)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            return False, _cpe.QUARANTINE_NUMERIC_INVALID
    terminal = record.get("terminal_reason")
    if terminal is not None and terminal not in RECOVERY_TERMINAL_REASONS:
        return False, _cpe.QUARANTINE_STATUS_UNSUPPORTED
    # A terminal state must say why; a non-terminal state must not carry one.
    if record.get("recovery_state") == RECOVERY_STATE_RECOVERY_TERMINAL:
        if terminal is None:
            return False, _cpe.QUARANTINE_CROSS_CONSISTENCY_INVALID
    elif terminal is not None:
        return False, _cpe.QUARANTINE_CROSS_CONSISTENCY_INVALID
    # The retryable pause is the mirror image: it must say why it paused, the
    # reason must be one the closed set allows to retry, and no other state may
    # claim to be paused.
    paused = record.get("paused_reason")
    if record.get("recovery_state") == RECOVERY_STATE_RECOVERY_PAUSED_RETRYABLE:
        if paused not in RECOVERY_RETRYABLE_PAUSE_REASONS:
            return False, _cpe.QUARANTINE_CROSS_CONSISTENCY_INVALID
    elif paused is not None:
        return False, _cpe.QUARANTINE_CROSS_CONSISTENCY_INVALID
    # Retained terminal history is legal in ANY state (that is the point), but
    # it must still name a real terminal reason.
    prior = record.get("prior_terminal_reason")
    if prior is not None and prior not in RECOVERY_TERMINAL_REASONS:
        return False, _cpe.QUARANTINE_STATUS_UNSUPPORTED
    # An open episode must be backfill-eligible or terminal: an INELIGIBLE
    # classification can never sit in a resumable state.
    if record.get("recovery_state") in RESUMABLE_RECOVERY_STATES:
        if record.get("entry_classification") not in (
                BACKFILL_ELIGIBLE_CLASSIFICATIONS):
            return False, _cpe.QUARANTINE_CROSS_CONSISTENCY_INVALID
        if int(record.get("safe_from_slot", -1)) < 0:
            return False, _cpe.QUARANTINE_CROSS_CONSISTENCY_INVALID
    # A proven episode binds an overlap identity at the proven slot.
    if record.get("recovery_state") == RECOVERY_STATE_RECOVERY_PROVEN:
        identity = record.get("overlap_skip_identity")
        slot = record.get("overlap_slot")
        if not isinstance(identity, str) or not identity:
            return False, _cpe.QUARANTINE_CROSS_CONSISTENCY_INVALID
        if _cursor_mod.slot_of_identity(identity) != slot:
            return False, _cpe.QUARANTINE_CROSS_CONSISTENCY_INVALID
        if record.get("overlap_proof_state") != OVERLAP_PROVEN:
            return False, _cpe.QUARANTINE_CROSS_CONSISTENCY_INVALID
    if not _cpe.record_digest_is_valid(CHECKPOINT_KIND_RPC_GAP_RECOVERY, record):
        return False, _cpe.QUARANTINE_RECORD_DIGEST_INVALID
    return True, ""


#: Closed-set integrity-invariant failure tokens for the retryable pause.
PAUSE_INVARIANT_OK = ""
PAUSE_INVARIANT_MODE_INVALID = "PAUSE_INVARIANT_MODE_INVALID"
PAUSE_INVARIANT_CLASSIFICATION_INELIGIBLE = (
    "PAUSE_INVARIANT_CLASSIFICATION_INELIGIBLE")
PAUSE_INVARIANT_IDENTITY_INVALID = "PAUSE_INVARIANT_IDENTITY_INVALID"
PAUSE_INVARIANT_COMMITMENT_INVALID = "PAUSE_INVARIANT_COMMITMENT_INVALID"
PAUSE_INVARIANT_BOUNDARY_INVALID = "PAUSE_INVARIANT_BOUNDARY_INVALID"
PAUSE_INVARIANT_TARGET_INVALID = "PAUSE_INVARIANT_TARGET_INVALID"
PAUSE_INVARIANT_PROGRESS_OUT_OF_RANGE = "PAUSE_INVARIANT_PROGRESS_OUT_OF_RANGE"
PAUSE_INVARIANT_BLOCK_ACCOUNTING_INVALID = (
    "PAUSE_INVARIANT_BLOCK_ACCOUNTING_INVALID")
PAUSE_INVARIANT_COVERAGE_INCONSISTENT = "PAUSE_INVARIANT_COVERAGE_INCONSISTENT"
PAUSE_INVARIANT_OVERLAP_ALREADY_PROVEN = (
    "PAUSE_INVARIANT_OVERLAP_ALREADY_PROVEN")


def recovery_pause_invariants(record: Mapping[str, Any]) -> Tuple[bool, str]:
    """May this episode legally pause retryably instead of ending?

    Membership in :data:`RECOVERY_RETRYABLE_PAUSE_REASONS` is checked by the
    caller; this predicate answers the separate question of whether the durable
    evidence is intact enough that resuming is sound.  Every check is a fact
    already carried by the authenticated record -- nothing is inferred and
    nothing is repaired.  Any failure keeps the episode terminal.
    """

    if record.get("recovery_mode") != GAP_RECOVERY_MODE_RPC_BACKFILL:
        return False, PAUSE_INVARIANT_MODE_INVALID
    if record.get("entry_classification") not in (
            BACKFILL_ELIGIBLE_CLASSIFICATIONS):
        return False, PAUSE_INVARIANT_CLASSIFICATION_INELIGIBLE
    if not _cpe.is_sha256_digest(record.get("subscription_identity_digest")):
        return False, PAUSE_INVARIANT_IDENTITY_INVALID
    if record.get("authoritative_commitment") not in AUTHORITATIVE_COMMITMENTS:
        return False, PAUSE_INVARIANT_COMMITMENT_INVALID
    safe_from = record.get("safe_from_slot")
    if isinstance(safe_from, bool) or not isinstance(safe_from, int) \
            or safe_from < 0:
        return False, PAUSE_INVARIANT_BOUNDARY_INVALID
    target = record.get("recovery_target_slot")
    if isinstance(target, bool) or not isinstance(target, int) \
            or target <= safe_from:
        return False, PAUSE_INVARIANT_TARGET_INVALID
    last_completed = record.get("last_completed_slot")
    if last_completed is not None:
        if isinstance(last_completed, bool) \
                or not isinstance(last_completed, int) \
                or last_completed < safe_from or last_completed > target:
            return False, PAUSE_INVARIANT_PROGRESS_OUT_OF_RANGE
    total = record.get("produced_blocks_total")
    completed = record.get("produced_blocks_completed")
    skipped = record.get("skipped_slots_total")
    for value in (total, completed, skipped):
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            return False, PAUSE_INVARIANT_BLOCK_ACCOUNTING_INVALID
    if completed > total:
        return False, PAUSE_INVARIANT_BLOCK_ACCOUNTING_INVALID
    if total > 0 and (total + skipped) != (target - safe_from + 1):
        # The range proof partitions [safe_from .. target] into produced and
        # explicitly skipped slots. A partition that does not add up means a
        # produced block went unaccounted for -- never resumable.
        return False, PAUSE_INVARIANT_COVERAGE_INCONSISTENT
    if record.get("overlap_proof_state") == OVERLAP_PROVEN:
        return False, PAUSE_INVARIANT_OVERLAP_ALREADY_PROVEN
    return True, PAUSE_INVARIANT_OK


def next_resume_slot(record: Mapping[str, Any]) -> int:
    """The exact slot a resumed episode must start at.

    ``last_completed_slot + 1`` once any block completed, otherwise the
    immutable episode boundary.  Never the live head.
    """

    last_completed = record.get("last_completed_slot")
    if isinstance(last_completed, int) and not isinstance(last_completed, bool):
        return int(last_completed) + 1
    return int(record.get("safe_from_slot", 0))


def recovery_record_identity(record: Mapping[str, Any]) -> Tuple:
    if record.get("record_kind") != RECOVERY_RECORD_KIND:
        raise ValueError("RPC_GAP_RECOVERY_RECORD_KIND_INVALID")
    return (RECOVERY_RECORD_KIND,)


def classify_recovery_checkpoint_file(
    path: object, *, validation_now_utc: Optional[str] = None
) -> _cpe.FileClassification:
    return _cpe.classify_checkpoint_file(
        path,
        kind=CHECKPOINT_KIND_RPC_GAP_RECOVERY,
        supported_schema_versions=(RPC_GAP_RECOVERY_SCHEMA_V1,),
        record_validator=validate_recovery_record,
        identity_fn=recovery_record_identity,
        validation_now_utc=validation_now_utc,
    )


class _AuthenticatedSingletonStore:
    """Shared load/persist mechanics for singleton checkpoint documents.

    Mirrors ``GrpcStreamCursorStore`` exactly: load matrix, quarantine as a
    write lockdown, detached-copy mutation, publish only after read-back.
    """

    _checkpoint_kind = ""
    _schema_version = ""
    _record_kind = ""

    def __init__(self, *, primary_path: object,
                 now_iso_fn: Callable[[], str] = _cpe.utc_now_iso) -> None:
        self._primary = Path(primary_path)
        self._backup = self._primary.with_name(self._primary.name + ".bak")
        self._now_iso = now_iso_fn
        self._lock = threading.RLock()
        self._generation = 0
        self._envelope_digest: Optional[str] = None
        self._created_at: Optional[str] = None
        self._quarantined = False
        self._quarantine_reason: Optional[str] = None
        self._write_locked = False
        self.load_result = _cpe.CheckpointLoadResult(
            checkpoint_kind=self._checkpoint_kind)

    # subclasses provide:
    def _classify(self, path: object) -> _cpe.FileClassification:
        raise NotImplementedError

    def _restore_record(self, record: Mapping[str, Any]) -> None:
        raise NotImplementedError

    def _current_record(self) -> Dict[str, Any]:
        raise NotImplementedError

    @property
    def primary_path(self) -> Path:
        return self._primary

    @property
    def quarantined(self) -> bool:
        return self._quarantined

    @property
    def quarantine_reason(self) -> Optional[str]:
        return self._quarantine_reason

    @property
    def generation(self) -> int:
        return self._generation

    @property
    def envelope_digest(self) -> Optional[str]:
        return self._envelope_digest

    def load(self) -> _cpe.CheckpointLoadResult:
        with self._lock:
            primary = self._classify(self._primary)
            backup = self._classify(self._backup)
            decision = _cpe.resolve_checkpoint_pair(primary, backup)
            result = _cpe.CheckpointLoadResult(
                checkpoint_kind=self._checkpoint_kind,
                checkpoint_status=decision.status,
                checkpoint_primary_status=primary.state,
                checkpoint_backup_status=backup.state,
                checkpoint_recovered_from_backup=decision.recovered_from_backup,
                checkpoint_quarantined=decision.quarantined,
                checkpoint_quarantine_reason=decision.quarantine_reason,
                checkpoint_files_found=(
                    primary.state != _cpe.FILE_MISSING
                    or backup.state != _cpe.FILE_MISSING),
                checkpoint_source_selected=decision.selected,
                checkpoint_last_validated_at_utc=self._now_iso(),
            )
            if decision.status == _cpe.CHECKPOINT_NOT_FOUND:
                self.load_result = result
                return result
            if decision.quarantined:
                self._quarantined = True
                self._quarantine_reason = decision.quarantine_reason
                self._write_locked = True
                self.load_result = result
                return result
            selected = primary if decision.selected == "primary" else backup
            record = None
            for candidate in selected.records or []:
                if candidate.get("record_kind") == self._record_kind:
                    record = candidate
                    break
            if record is None:
                self._quarantined = True
                self._quarantine_reason = _cpe.QUARANTINE_RECORD_COUNT_MISMATCH
                self._write_locked = True
                result.checkpoint_quarantined = True
                result.checkpoint_status = _cpe.CHECKPOINT_QUARANTINED
                result.checkpoint_quarantine_reason = self._quarantine_reason
                self.load_result = result
                return result
            self._restore_record(record)
            self._generation = int(selected.header.get("generation") or 0) \
                if selected.header else 0
            self._envelope_digest = (
                selected.envelope_digest if selected.header else None)
            self._created_at = (
                selected.header.get("created_at_utc")
                if selected.header else None)
            result.checkpoint_generation = self._generation
            result.checkpoint_records_validated = 1
            self.load_result = result
            return result

    def _persist_record_locked(self, record: Dict[str, Any]) -> None:
        if self._write_locked:
            raise RecoveryStoreWriteError(TERMINAL_RECOVERY_STATE_QUARANTINED)
        now = self._now_iso()
        record["record_digest"] = _cpe.build_record_digest(
            self._checkpoint_kind, record)
        header = _cpe.build_envelope_header(
            checkpoint_kind=self._checkpoint_kind,
            schema_version=self._schema_version,
            payload_encoding=_cpe.PAYLOAD_ENCODING_DOCUMENT,
            generation=self._generation + 1,
            record_digests=[record["record_digest"]],
            created_at_utc=self._created_at or now,
            updated_at_utc=now,
            previous_generation_digest=self._envelope_digest,
            source_id=self._primary.name,
        )
        try:
            _cpe.write_checkpoint_generation(
                primary_path=self._primary,
                backup_path=self._backup,
                header=header,
                records=[record],
                classify=lambda p: self._classify(p),
            )
        except (_cpe.CheckpointWriteError, OSError) as exc:
            raise RecoveryStoreWriteError(str(type(exc).__name__)) from exc
        self._generation = int(header["generation"])
        self._envelope_digest = str(header["envelope_digest"])
        self._created_at = self._created_at or now


class RpcGapRecoveryStore(_AuthenticatedSingletonStore):
    """Durable, authenticated recovery episode state."""

    _checkpoint_kind = CHECKPOINT_KIND_RPC_GAP_RECOVERY
    _schema_version = RPC_GAP_RECOVERY_SCHEMA_V1
    _record_kind = RECOVERY_RECORD_KIND

    def __init__(self, *, state_dir: object,
                 basename: str = RECOVERY_PRIMARY_BASENAME,
                 now_iso_fn: Callable[[], str] = _cpe.utc_now_iso) -> None:
        super().__init__(primary_path=Path(state_dir) / basename,
                         now_iso_fn=now_iso_fn)
        self.state = RpcGapRecoveryState()

    def _classify(self, path: object) -> _cpe.FileClassification:
        return classify_recovery_checkpoint_file(path)

    def _restore_record(self, record: Mapping[str, Any]) -> None:
        self.state = RpcGapRecoveryState.from_record(record)

    def _current_record(self) -> Dict[str, Any]:
        return self.state.to_record()

    def _persist_state_locked(self, proposed: RpcGapRecoveryState) -> None:
        # Single write point, so the pause marker is normalised here rather
        # than at every caller: only a paused episode may carry a paused
        # reason. Resuming moves the state to RPC_BACKFILL_PLANNED through the
        # ordinary ``update`` path, and leaving a stale marker behind would
        # make the very next authenticated load cross-inconsistent.
        if proposed.recovery_state != RECOVERY_STATE_RECOVERY_PAUSED_RETRYABLE:
            proposed.paused_reason = None
        proposed.updated_at_utc = self._now_iso()
        self._persist_record_locked(proposed.to_record())
        self.state = proposed

    def persist(self) -> None:
        with self._lock:
            self._persist_state_locked(self.state.clone())

    def has_resumable_episode(self) -> bool:
        with self._lock:
            return (not self._quarantined
                    and self.state.recovery_state in RESUMABLE_RECOVERY_STATES)

    def open_episode(
        self, *, entry_classification: str, safe_from_slot: int,
        subscription_identity_digest: str, authoritative_commitment: str,
        cursor_recovery_generation: int, cursor_attempt_generation: int,
    ) -> RpcGapRecoveryState:
        """Open one episode, or resume the identical one. Boundary immutable.

        A resumable persisted episode must agree on the boundary, the identity
        digest and the cursor generation, or the store refuses: two different
        recovery episodes can never silently merge.
        """

        if entry_classification not in BACKFILL_ELIGIBLE_CLASSIFICATIONS:
            raise ValueError(TERMINAL_RPC_BACKFILL_ENTRY_INELIGIBLE)
        if isinstance(safe_from_slot, bool) or not isinstance(
                safe_from_slot, int) or safe_from_slot < 0:
            raise ValueError("RPC_GAP_RECOVERY_SAFE_FROM_SLOT_INVALID")
        with self._lock:
            if self._quarantined:
                raise RecoveryStoreWriteError(
                    TERMINAL_RECOVERY_STATE_QUARANTINED)
            state = self.state
            if state.recovery_state in RESUMABLE_RECOVERY_STATES:
                if (int(state.safe_from_slot) != int(safe_from_slot)
                        or state.subscription_identity_digest
                        != str(subscription_identity_digest)
                        or int(state.cursor_recovery_generation)
                        != int(cursor_recovery_generation)):
                    raise RecoveryStoreWriteError(
                        "RPC_GAP_RECOVERY_EPISODE_MISMATCH")
                return state
            proposed = RpcGapRecoveryState(
                recovery_mode=GAP_RECOVERY_MODE_RPC_BACKFILL,
                recovery_state=RECOVERY_STATE_REPLAY_REFUSED,
                entry_classification=str(entry_classification),
                subscription_identity_digest=str(subscription_identity_digest),
                authoritative_commitment=str(authoritative_commitment),
                episode_generation=int(state.episode_generation) + 1,
                cursor_recovery_generation=int(cursor_recovery_generation),
                cursor_attempt_generation=int(cursor_attempt_generation),
                safe_from_slot=int(safe_from_slot),
                opened_at_utc=self._now_iso(),
            )
            self._persist_state_locked(proposed)
            return self.state

    def update(self, **changes: Any) -> None:
        """Apply bounded field changes to a detached copy, then persist.

        ``safe_from_slot``, the episode identity fields and the generations are
        deliberately NOT updatable through this method.
        """

        immutable = {
            "safe_from_slot", "subscription_identity_digest",
            "episode_generation", "cursor_recovery_generation",
            "cursor_attempt_generation", "entry_classification",
            "authoritative_commitment", "opened_at_utc",
        }
        illegal = immutable.intersection(changes)
        if illegal:
            raise ValueError(
                "RPC_GAP_RECOVERY_IMMUTABLE_FIELD:" + ",".join(sorted(illegal)))
        with self._lock:
            proposed = self.state.clone()
            for name, value in changes.items():
                if name not in proposed.__dataclass_fields__:
                    raise ValueError(f"RPC_GAP_RECOVERY_UNKNOWN_FIELD:{name}")
                setattr(proposed, name, value)
            self._persist_state_locked(proposed)

    def mark_terminal(self, *, reason: str) -> None:
        safe_reason = (
            reason if reason in RECOVERY_TERMINAL_REASONS
            else TERMINAL_RECOVERY_OVERLAP_NOT_PROVEN)
        with self._lock:
            if self._quarantined:
                return
            proposed = self.state.clone()
            proposed.recovery_state = RECOVERY_STATE_RECOVERY_TERMINAL
            proposed.terminal_reason = safe_reason
            try:
                self._persist_state_locked(proposed)
            except RecoveryStoreWriteError:
                # The in-memory terminal claim stands even if the write failed:
                # claiming a dead recovery that was never persisted is the
                # conservative direction.
                self.state = proposed

    def pause_retryable(self, *, reason: str) -> bool:
        """Pause the episode instead of ending it, when that is legal.

        Returns ``True`` when the episode is now ``RECOVERY_PAUSED_RETRYABLE``.
        Returns ``False`` without changing anything when the reason is not a
        retryable one or an integrity invariant fails -- the caller must then
        mark the episode terminal exactly as before.
        """

        if reason not in RECOVERY_RETRYABLE_PAUSE_REASONS:
            return False
        with self._lock:
            if self._quarantined:
                return False
            record = self.state.to_record()
            ok, _token = recovery_pause_invariants(record)
            if not ok:
                return False
            proposed = self.state.clone()
            proposed.recovery_state = RECOVERY_STATE_RECOVERY_PAUSED_RETRYABLE
            proposed.paused_reason = str(reason)
            proposed.terminal_reason = None
            proposed.pause_count = int(proposed.pause_count) + 1
            try:
                self._persist_state_locked(proposed)
            except RecoveryStoreWriteError:
                # A pause that could not be made durable must not be claimed:
                # an unpersisted pause would silently become a live-head resume
                # after a restart. Leave the state alone and let the caller
                # fall through to the terminal path.
                return False
            return True

    def note_resume_attempt(self) -> None:
        """Record that a paused episode is being resumed. Best effort."""

        with self._lock:
            if self._quarantined:
                return
            if self.state.recovery_state != (
                    RECOVERY_STATE_RECOVERY_PAUSED_RETRYABLE):
                return
            proposed = self.state.clone()
            proposed.resume_attempts = int(proposed.resume_attempts) + 1
            try:
                self._persist_state_locked(proposed)
            except RecoveryStoreWriteError:
                pass

    def upgrade_terminal_to_retryable(self) -> str:
        """Deterministically reopen an ALREADY-PERSISTED terminal timeout.

        This is the in-place, authenticated upgrade for an episode that was
        ended by a bounded attempt clock before the retryable pause existed.
        It is idempotent, it never edits the file by hand, it preserves the
        original terminal verdict as history, and it refuses on any mismatch.
        Returns one of :data:`UPGRADE_OUTCOMES`.
        """

        with self._lock:
            if self._quarantined:
                return UPGRADE_REFUSED_STORE_QUARANTINED
            state = self.state
            if state.recovery_state == RECOVERY_STATE_RECOVERY_PAUSED_RETRYABLE:
                return UPGRADE_ALREADY_RETRYABLE
            if state.recovery_state != RECOVERY_STATE_RECOVERY_TERMINAL:
                return UPGRADE_REFUSED_NOT_TERMINAL
            reason = state.terminal_reason
            if reason not in RECOVERY_RETRYABLE_PAUSE_REASONS:
                return UPGRADE_REFUSED_REASON_NOT_RETRYABLE
            record = state.to_record()
            ok, _token = recovery_pause_invariants(record)
            if not ok:
                return UPGRADE_REFUSED_INTEGRITY
            proposed = state.clone()
            proposed.recovery_state = RECOVERY_STATE_RECOVERY_PAUSED_RETRYABLE
            proposed.paused_reason = str(reason)
            # History is retained, not erased: the original verdict and the
            # moment it was recorded survive the upgrade verbatim.
            proposed.prior_terminal_reason = str(reason)
            proposed.prior_terminal_at_utc = state.updated_at_utc
            proposed.terminal_reason = None
            proposed.pause_count = int(proposed.pause_count) + 1
            proposed.terminal_upgrade_count = int(
                proposed.terminal_upgrade_count) + 1
            try:
                self._persist_state_locked(proposed)
            except RecoveryStoreWriteError:
                return UPGRADE_REFUSED_WRITE_FAILED
            return UPGRADE_APPLIED

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            state = self.state
            return {
                "recovery_mode": state.recovery_mode,
                "recovery_state": state.recovery_state,
                "entry_classification": state.entry_classification,
                "authoritative_commitment": state.authoritative_commitment,
                "safe_from_slot": (
                    None if state.safe_from_slot < 0
                    else int(state.safe_from_slot)),
                "recovery_target_slot": state.recovery_target_slot,
                "quarantined_live_first_slot": state.quarantined_live_first_slot,
                "overlap_slot": state.overlap_slot,
                "overlap_proof_state": state.overlap_proof_state,
                "overlap_identity_digest": (
                    None if not state.overlap_skip_identity
                    else _cpe.sha256_hex_text(state.overlap_skip_identity)[:16]),
                "gap_slots": (
                    None if (state.recovery_target_slot is None
                             or state.safe_from_slot < 0)
                    else int(state.recovery_target_slot)
                    - int(state.safe_from_slot)),
                "last_completed_slot": state.last_completed_slot,
                "produced_blocks_total": state.produced_blocks_total,
                "produced_blocks_completed": state.produced_blocks_completed,
                "skipped_slots_total": state.skipped_slots_total,
                "transactions_scanned": state.transactions_scanned,
                "transactions_relevant": state.transactions_relevant,
                "transactions_rejected": state.transactions_rejected,
                "migration_events_recovered": state.migration_events_recovered,
                "reserve_events_recovered": state.reserve_events_recovered,
                "fee_events_recovered": state.fee_events_recovered,
                "duplicate_events_suppressed": state.duplicate_events_suppressed,
                "unseen_buffered_events_applied": (
                    state.unseen_buffered_events_applied),
                "rpc_request_count": state.rpc_request_count,
                "rpc_retry_count": state.rpc_retry_count,
                "rpc_timeout_count": state.rpc_timeout_count,
                "rpc_429_count": state.rpc_429_count,
                "rpc_error_count": state.rpc_error_count,
                "backfill_runtime_ms": state.backfill_runtime_ms,
                "quarantine_segments": state.quarantine_segments,
                "terminal_reason": state.terminal_reason,
                "paused_reason": state.paused_reason,
                "pause_count": int(state.pause_count),
                "resume_attempts": int(state.resume_attempts),
                "prior_terminal_reason": state.prior_terminal_reason,
                "prior_terminal_at_utc": state.prior_terminal_at_utc,
                "terminal_upgrade_count": int(state.terminal_upgrade_count),
                "episode_open": (
                    state.recovery_state in RESUMABLE_RECOVERY_STATES),
                "next_resume_slot": (
                    None if state.safe_from_slot < 0
                    else next_resume_slot(state.to_record())),
                "produced_blocks_remaining": max(
                    0, int(state.produced_blocks_total)
                    - int(state.produced_blocks_completed)),
                "recovery_store_quarantined": bool(self._quarantined),
                "recovery_store_quarantine_reason": self._quarantine_reason,
                "recovery_store_generation": int(self._generation),
            }


# ---------------------------------------------------------------------------
# quarantine buffer (authenticated, bounded)
# ---------------------------------------------------------------------------

CHECKPOINT_KIND_RECOVERY_QUARANTINE = "PHX2_RPC_RECOVERY_QUARANTINE"
RECOVERY_QUARANTINE_SCHEMA_V1 = "phx2_rpc_recovery_quarantine_v1"
QUARANTINE_RECORD_KIND = "PHX2_RPC_RECOVERY_QUARANTINE_BUFFER"
QUARANTINE_PRIMARY_BASENAME = "rpc_recovery_quarantine.json"


def _validate_buffer_entry(entry: object) -> bool:
    if not isinstance(entry, Mapping):
        return False
    if entry.get("event_kind") not in BUFFER_EVENT_KINDS:
        return False
    slot = entry.get("slot")
    if isinstance(slot, bool) or not isinstance(slot, int) or slot < 0:
        return False
    for name in ("signature", "skip_identity", "buffered_at_utc"):
        value = entry.get(name)
        if not isinstance(value, str) or not value:
            return False
    if _cursor_mod.slot_of_identity(entry.get("skip_identity")) != slot:
        return False
    for name in ("attempt_generation", "segment"):
        value = entry.get(name)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            return False
    candidate = entry.get("candidate")
    if candidate is not None and not isinstance(candidate, Mapping):
        return False
    if entry.get("event_kind") == BUFFER_EVENT_MIGRATION_ADMITTED \
            and candidate is None:
        return False
    return True


def validate_quarantine_record(record: Mapping[str, Any]) -> Tuple[bool, str]:
    if record.get("record_kind") != QUARANTINE_RECORD_KIND:
        return False, _cpe.QUARANTINE_KIND_INVALID
    if not _cpe.is_sha256_digest(record.get("subscription_identity_digest")):
        return False, _cpe.QUARANTINE_CANDIDATE_BINDING_INVALID
    episode = record.get("episode_generation")
    if isinstance(episode, bool) or not isinstance(episode, int) or episode < 0:
        return False, _cpe.QUARANTINE_NUMERIC_INVALID
    entries = record.get("entries")
    if not isinstance(entries, list):
        return False, _cpe.QUARANTINE_CANDIDATE_BINDING_INVALID
    for entry in entries:
        if not _validate_buffer_entry(entry):
            return False, _cpe.QUARANTINE_CANDIDATE_BINDING_INVALID
    if not _cpe.record_digest_is_valid(
            CHECKPOINT_KIND_RECOVERY_QUARANTINE, record):
        return False, _cpe.QUARANTINE_RECORD_DIGEST_INVALID
    return True, ""


def quarantine_record_identity(record: Mapping[str, Any]) -> Tuple:
    if record.get("record_kind") != QUARANTINE_RECORD_KIND:
        raise ValueError("RPC_RECOVERY_QUARANTINE_RECORD_KIND_INVALID")
    return (QUARANTINE_RECORD_KIND,)


def classify_quarantine_checkpoint_file(
    path: object, *, validation_now_utc: Optional[str] = None
) -> _cpe.FileClassification:
    return _cpe.classify_checkpoint_file(
        path,
        kind=CHECKPOINT_KIND_RECOVERY_QUARANTINE,
        supported_schema_versions=(RECOVERY_QUARANTINE_SCHEMA_V1,),
        record_validator=validate_quarantine_record,
        identity_fn=quarantine_record_identity,
        validation_now_utc=validation_now_utc,
    )


class QuarantinedLiveBuffer(_AuthenticatedSingletonStore):
    """Bounded, durable, authenticated buffer for quarantined live events.

    Every entry retains only durable identity plus already-decoded evidence
    (the candidate dict for an admitted migration).  No raw transaction
    payload is retained.  Appending past any bound raises
    :class:`QuarantineBufferCapacityExceeded` -- the event is never silently
    dropped; the episode goes terminal instead.
    """

    _checkpoint_kind = CHECKPOINT_KIND_RECOVERY_QUARANTINE
    _schema_version = RECOVERY_QUARANTINE_SCHEMA_V1
    _record_kind = QUARANTINE_RECORD_KIND

    def __init__(self, *, state_dir: object,
                 subscription_identity_digest: str,
                 max_events: int, max_bytes: int, max_age_seconds: float,
                 basename: str = QUARANTINE_PRIMARY_BASENAME,
                 now_iso_fn: Callable[[], str] = _cpe.utc_now_iso) -> None:
        super().__init__(primary_path=Path(state_dir) / basename,
                         now_iso_fn=now_iso_fn)
        self._identity_digest = str(subscription_identity_digest)
        self._max_events = int(max_events)
        self._max_bytes = int(max_bytes)
        self._max_age_seconds = float(max_age_seconds)
        self.episode_generation = 0
        self.entries: List[Dict[str, Any]] = []

    def _classify(self, path: object) -> _cpe.FileClassification:
        return classify_quarantine_checkpoint_file(path)

    def _restore_record(self, record: Mapping[str, Any]) -> None:
        self.episode_generation = int(record.get("episode_generation") or 0)
        self.entries = [dict(entry) for entry in record.get("entries") or []]
        self._loaded_identity_digest = str(
            record.get("subscription_identity_digest") or "")

    def _current_record(self) -> Dict[str, Any]:
        return {
            "record_kind": QUARANTINE_RECORD_KIND,
            "subscription_identity_digest": self._identity_digest,
            "episode_generation": int(self.episode_generation),
            "entries": [dict(entry) for entry in self.entries],
        }

    @property
    def identity_matches(self) -> bool:
        loaded = getattr(self, "_loaded_identity_digest", None)
        return loaded is None or loaded == self._identity_digest

    def bind_episode(self, episode_generation: int) -> None:
        """Bind the buffer to one episode; a different episode starts empty."""

        with self._lock:
            if int(self.episode_generation) != int(episode_generation):
                self.episode_generation = int(episode_generation)
                self.entries = []
                self._persist_record_locked(self._current_record())

    def depth(self) -> int:
        with self._lock:
            return len(self.entries)

    def byte_size(self) -> int:
        with self._lock:
            return len(_cpe.canonical_json(
                {"entries": self.entries}).encode("utf-8"))

    def oldest_age_seconds(self, *, now_utc: Optional[str] = None) -> Optional[float]:
        with self._lock:
            if not self.entries:
                return None
            oldest = _cpe.parse_utc_timestamp(
                self.entries[0].get("buffered_at_utc"))
        newest = _cpe.parse_utc_timestamp(now_utc or self._now_iso())
        if oldest is None or newest is None:
            return None
        return max(0.0, (newest - oldest).total_seconds())

    def append(self, entry: Dict[str, Any]) -> None:
        """Durably append one entry, enforcing every bound fail-closed."""

        payload = dict(entry)
        payload.setdefault("buffered_at_utc", self._now_iso())
        if not _validate_buffer_entry(payload):
            raise ValueError("RPC_RECOVERY_QUARANTINE_ENTRY_INVALID")
        with self._lock:
            if self._quarantined:
                raise RecoveryStoreWriteError(
                    TERMINAL_RECOVERY_STATE_QUARANTINED)
            if len(self.entries) + 1 > self._max_events:
                raise QuarantineBufferCapacityExceeded(
                    TERMINAL_RECOVERY_BUFFER_CAPACITY_EXCEEDED)
            proposed = self.entries + [payload]
            encoded = len(_cpe.canonical_json(
                {"entries": proposed}).encode("utf-8"))
            if encoded > self._max_bytes:
                raise QuarantineBufferCapacityExceeded(
                    TERMINAL_RECOVERY_BUFFER_CAPACITY_EXCEEDED)
            age = self.oldest_age_seconds()
            if age is not None and age > self._max_age_seconds:
                raise QuarantineBufferCapacityExceeded(
                    TERMINAL_RECOVERY_BUFFER_CAPACITY_EXCEEDED)
            previous = self.entries
            self.entries = proposed
            try:
                self._persist_record_locked(self._current_record())
            except RecoveryStoreWriteError:
                self.entries = previous
                raise

    def clear(self) -> None:
        with self._lock:
            self.entries = []
            try:
                self._persist_record_locked(self._current_record())
            except RecoveryStoreWriteError:
                pass

    def ordered_entries(self) -> List[Dict[str, Any]]:
        """Deterministic application order: segment, slot, tx index, arrival."""

        with self._lock:
            indexed = list(enumerate(self.entries))
        return [entry for _, entry in sorted(
            indexed,
            key=lambda pair: (
                int(pair[1].get("segment") or 0),
                int(pair[1].get("slot") or 0),
                int(pair[1].get("transaction_index") or 0)
                if isinstance(pair[1].get("transaction_index"), int) else 0,
                pair[0],
            ))]

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "quarantine_depth": len(self.entries),
                "quarantine_bytes": self.byte_size(),
                "quarantine_oldest_age_seconds": self.oldest_age_seconds(),
                "quarantine_episode_generation": int(self.episode_generation),
                "quarantine_store_quarantined": bool(self._quarantined),
                "quarantine_store_quarantine_reason": self._quarantine_reason,
            }


# ---------------------------------------------------------------------------
# provider-neutral JSON-RPC adapter
# ---------------------------------------------------------------------------

class RpcBackfillBoundExceeded(RuntimeError):
    """A hard bound was crossed. ``reason`` is a closed-set terminal token."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = (
            reason if reason in RECOVERY_TERMINAL_REASONS
            else TERMINAL_RPC_BACKFILL_MALFORMED_RESPONSE)


#: JSON-RPC error codes that prove a slot was skipped or is not present in
#: ledger storage. On a slot that ``getBlocks`` reported as produced they are
#: evidence of permanent unavailability, never of a skip.
_RPC_SLOT_SKIPPED_CODES = (-32007, -32009)
#: Block not yet available at the requested commitment: retryable.
_RPC_BLOCK_NOT_AVAILABLE_CODE = -32004


def _rpc_envelope_structurally_usable(body: object, *, raw: bool) -> bool:
    """Cheapest structural acceptance for one JSON-RPC response body.

    Decoded bodies must carry a ``result`` or an ``error`` member; raw bodies
    are only checked for being a non-empty byte string here -- the full
    envelope contract is enforced where the payload is actually decoded, so a
    raw body can never reach application with weaker validation.
    """

    if raw:
        return isinstance(body, (bytes, bytearray)) and len(body) > 0
    return isinstance(body, dict) and (
        "result" in body or "error" in body)


class SolanaRpcBackfillAdapter:
    """Bounded, deterministic block-range JSON-RPC access.

    The transport is injected: ``rpc_post_fn(method, params, timeout_seconds)``
    returning ``(http_status, parsed_json_or_None)``.  The adapter enforces the
    request budget, retry budget, spacing, 429 threshold and consecutive
    failure threshold, and translates every violation into a closed-set
    terminal reason.  It never prints or retains endpoint values -- it never
    even sees them.
    """

    def __init__(self, *, rpc_post_fn: Callable[..., Tuple[int, Optional[Dict[str, Any]]]],
                 config: RpcGapRecoveryConfig,
                 timeout_seconds: float = DEFAULT_RPC_RECOVERY_TIMEOUT_SECONDS,
                 monotonic_fn: Callable[[], float] = time.monotonic,
                 sleep_fn: Callable[[float], None] = time.sleep) -> None:
        self._post = rpc_post_fn
        self._config = config
        self._timeout = float(timeout_seconds)
        self._monotonic = monotonic_fn
        self._sleep = sleep_fn
        self._last_request_started: Optional[float] = None
        self._next_request_time: Optional[float] = None
        self._rate_lock = threading.Lock()
        self._counter_lock = threading.Lock()
        #: Multiplies the configured spacing while the provider is signalling
        #: pressure. Raised on 429/timeout, decayed on sustained success, and
        #: never below 1.0 -- the configured spacing is a floor, not a target.
        self._pressure_multiplier = 1.0
        self._pressure_events = 0
        self._clean_streak = 0
        self.request_count = 0
        self.retry_count = 0
        self.timeout_count = 0
        self.http_429_count = 0
        self.error_count = 0

    def counters(self) -> Dict[str, int]:
        with self._counter_lock:
            return {
                "rpc_request_count": int(self.request_count),
                "rpc_retry_count": int(self.retry_count),
                "rpc_timeout_count": int(self.timeout_count),
                "rpc_429_count": int(self.http_429_count),
                "rpc_error_count": int(self.error_count),
            }

    @property
    def pressure_multiplier(self) -> float:
        return float(self._pressure_multiplier)

    @property
    def pressure_events(self) -> int:
        return int(self._pressure_events)

    def _note_pressure(self) -> None:
        """Back off globally: every worker slows, not just the one that hit it."""

        with self._rate_lock:
            self._pressure_multiplier = min(
                MAX_PRESSURE_MULTIPLIER, self._pressure_multiplier * 2.0)
            self._pressure_events += 1
            self._clean_streak = 0

    def _note_clean(self) -> None:
        with self._rate_lock:
            self._clean_streak += 1
            if self._clean_streak >= PRESSURE_DECAY_CLEAN_REQUESTS \
                    and self._pressure_multiplier > 1.0:
                self._pressure_multiplier = max(
                    1.0, self._pressure_multiplier / 2.0)
                self._clean_streak = 0

    def _space_requests(self) -> None:
        """Claim the next global request slot, then wait for it.

        Concurrent workers share ONE monotonically advancing schedule, so the
        aggregate request rate stays inside ``1 / spacing`` no matter how many
        of them are in flight. Claiming the slot under the lock and sleeping
        outside it is what allows genuine concurrency without ever bursting
        past the configured rate.
        """

        spacing = float(self._config.rpc_request_spacing_seconds)
        with self._rate_lock:
            spacing = spacing * float(self._pressure_multiplier)
            now = self._monotonic()
            start_at = now if self._next_request_time is None else max(
                now, float(self._next_request_time))
            self._next_request_time = start_at + spacing
        delay = start_at - self._monotonic()
        if delay > 0:
            self._sleep(delay)

    @property
    def supports_raw_payloads(self) -> bool:
        """True when the injected transport can return UNDECODED bodies.

        Raw bodies are what allow the JSON decode to happen in a worker
        PROCESS.  A transport without the capability (every offline test
        transport) keeps the in-process decode; the coordinator refuses to
        start a process pool against such a transport rather than silently
        running the known-diverging serial path during production recovery.
        """

        return bool(getattr(self._post, "supports_raw_bodies", False))

    def _request(self, method: str, params: List[Any],
                 raw: bool = False) -> Any:
        """One budgeted request with bounded retries. Returns the envelope.

        With ``raw=True`` the return value is the UNDECODED response body
        (``bytes``); every bound, counter, retry and pressure rule is
        byte-for-byte the same path -- only the decode is deferred.
        """

        consecutive_failures = 0
        attempts = 0
        while True:
            with self._counter_lock:
                if self.request_count >= int(self._config.max_rpc_requests):
                    raise RpcBackfillBoundExceeded(
                        TERMINAL_RPC_BACKFILL_REQUEST_LIMIT_EXCEEDED)
                self.request_count += 1
            self._space_requests()
            self._last_request_started = self._monotonic()
            attempts += 1
            try:
                if raw:
                    status, body = self._post(
                        method, params, self._timeout, raw=True)
                else:
                    status, body = self._post(method, params, self._timeout)
            except Exception:
                status, body = 0, None
            if status == 429:
                with self._counter_lock:
                    self.http_429_count += 1
                    self.error_count += 1
                    exhausted = self.http_429_count > int(
                        self._config.max_http_429_responses)
                self._note_pressure()
                if exhausted:
                    raise RpcBackfillBoundExceeded(
                        TERMINAL_RPC_BACKFILL_RATE_LIMITED)
            elif status == 0:
                with self._counter_lock:
                    self.timeout_count += 1
                    self.error_count += 1
                self._note_pressure()
            elif status != 200 or body is None:
                with self._counter_lock:
                    self.error_count += 1
                self._note_pressure()
            elif not _rpc_envelope_structurally_usable(body, raw=raw):
                with self._counter_lock:
                    self.error_count += 1
                # Structurally malformed JSON-RPC: retry within budget, then
                # terminal as malformed rather than unavailable.
                if attempts > int(self._config.max_retries_per_request):
                    raise RpcBackfillBoundExceeded(
                        TERMINAL_RPC_BACKFILL_MALFORMED_RESPONSE)
                consecutive_failures += 1
                if consecutive_failures > int(
                        self._config.max_consecutive_rpc_failures):
                    raise RpcBackfillBoundExceeded(
                        TERMINAL_RPC_BACKFILL_CONSECUTIVE_FAILURES)
                with self._counter_lock:
                    self.retry_count += 1
                continue
            else:
                self._note_clean()
                return body
            # Transport-level failure (429 / timeout / HTTP error / no body).
            if attempts > int(self._config.max_retries_per_request):
                raise RpcBackfillBoundExceeded(
                    TERMINAL_RPC_BACKFILL_TIMEOUT if self.timeout_count > 0
                    and status == 0 else TERMINAL_RPC_BACKFILL_BLOCK_UNAVAILABLE)
            consecutive_failures += 1
            if consecutive_failures > int(
                    self._config.max_consecutive_rpc_failures):
                raise RpcBackfillBoundExceeded(
                    TERMINAL_RPC_BACKFILL_CONSECUTIVE_FAILURES)
            with self._counter_lock:
                self.retry_count += 1

    def get_slot(self, *, commitment: str) -> int:
        body = self._request("getSlot", [{"commitment": str(commitment)}])
        if "error" in body:
            raise RpcBackfillBoundExceeded(
                TERMINAL_RPC_BACKFILL_MALFORMED_RESPONSE)
        value = body.get("result")
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise RpcBackfillBoundExceeded(
                TERMINAL_RPC_BACKFILL_MALFORMED_RESPONSE)
        return int(value)

    def get_blocks(self, *, start_slot: int, end_slot: int,
                   commitment: str) -> List[int]:
        """Produced slots in ``[start_slot .. end_slot]``, both inclusive.

        Every slot in the range that is absent from the answer is PROVEN
        skipped by this block-range response.
        """

        body = self._request(
            "getBlocks",
            [int(start_slot), int(end_slot), {"commitment": str(commitment)}])
        if "error" in body:
            raise RpcBackfillBoundExceeded(
                TERMINAL_RPC_BACKFILL_MALFORMED_RESPONSE)
        result = body.get("result")
        if not isinstance(result, list):
            raise RpcBackfillBoundExceeded(
                TERMINAL_RPC_BACKFILL_MALFORMED_RESPONSE)
        produced: List[int] = []
        previous: Optional[int] = None
        for value in result:
            if isinstance(value, bool) or not isinstance(value, int):
                raise RpcBackfillBoundExceeded(
                    TERMINAL_RPC_BACKFILL_MALFORMED_RESPONSE)
            if value < int(start_slot) or value > int(end_slot):
                raise RpcBackfillBoundExceeded(
                    TERMINAL_RPC_BACKFILL_MALFORMED_RESPONSE)
            if previous is not None and value <= previous:
                raise RpcBackfillBoundExceeded(
                    TERMINAL_RPC_BACKFILL_MALFORMED_RESPONSE)
            produced.append(int(value))
            previous = int(value)
        return produced

    @staticmethod
    def block_request_params(*, slot: int, commitment: str) -> List[Any]:
        """The ONE canonical ``getBlock`` parameter shape. Encoding is fixed."""

        return [int(slot), {
            "commitment": str(commitment),
            "encoding": "json",
            "transactionDetails": "full",
            "maxSupportedTransactionVersion": 0,
            "rewards": False,
        }]

    def get_block_payload(self, *, slot: int, commitment: str) -> bytes:
        """Fetch one produced block as an UNDECODED JSON-RPC body.

        The expensive decode is deliberately NOT performed here -- it belongs
        to a worker process.  An error envelope is still resolved in this
        process because it is rare and must keep exactly the closed-set
        classification ``get_block`` applies: the absence of the ``"error"``
        byte sequence proves the absence of a top-level ``error`` member (JSON
        escaping makes the quoted token unrepresentable inside a string
        value), so the decode below runs only on genuine error envelopes.
        """

        attempts = 0
        params = self.block_request_params(slot=slot, commitment=commitment)
        while True:
            payload = self._request("getBlock", params, raw=True)
            if b'"error"' not in payload:
                return bytes(payload)
            try:
                body = json.loads(bytes(payload).decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                raise RpcBackfillBoundExceeded(
                    TERMINAL_RPC_BACKFILL_MALFORMED_RESPONSE)
            if not isinstance(body, dict):
                raise RpcBackfillBoundExceeded(
                    TERMINAL_RPC_BACKFILL_MALFORMED_RESPONSE)
            error = body.get("error")
            if not isinstance(error, Mapping):
                # No top-level error after all: the byte probe was a false
                # positive, so the already-fetched payload stands.
                return bytes(payload)
            code = error.get("code")
            if code in _RPC_SLOT_SKIPPED_CODES:
                raise RpcBackfillBoundExceeded(
                    TERMINAL_RPC_BACKFILL_BLOCK_UNAVAILABLE)
            if code == _RPC_BLOCK_NOT_AVAILABLE_CODE:
                attempts += 1
                if attempts > int(self._config.max_retries_per_request):
                    raise RpcBackfillBoundExceeded(
                        TERMINAL_RPC_BACKFILL_BLOCK_UNAVAILABLE)
                with self._counter_lock:
                    self.retry_count += 1
                continue
            raise RpcBackfillBoundExceeded(
                TERMINAL_RPC_BACKFILL_MALFORMED_RESPONSE)

    def get_block(self, *, slot: int, commitment: str) -> Dict[str, Any]:
        """Fetch one produced block with full transactions, bounded retries.

        A ``-32004`` (not yet available) answer retries inside the ordinary
        retry budget; a skipped/missing answer for a slot the range proof
        called produced is permanent unavailability.
        """

        attempts = 0
        while True:
            body = self._request(
                "getBlock",
                self.block_request_params(slot=slot, commitment=commitment))
            error = body.get("error")
            if isinstance(error, Mapping):
                code = error.get("code")
                if code in _RPC_SLOT_SKIPPED_CODES:
                    raise RpcBackfillBoundExceeded(
                        TERMINAL_RPC_BACKFILL_BLOCK_UNAVAILABLE)
                if code == _RPC_BLOCK_NOT_AVAILABLE_CODE:
                    attempts += 1
                    if attempts > int(self._config.max_retries_per_request):
                        raise RpcBackfillBoundExceeded(
                            TERMINAL_RPC_BACKFILL_BLOCK_UNAVAILABLE)
                    with self._counter_lock:
                        self.retry_count += 1
                    continue
                raise RpcBackfillBoundExceeded(
                    TERMINAL_RPC_BACKFILL_MALFORMED_RESPONSE)
            result = body.get("result")
            if result is None:
                raise RpcBackfillBoundExceeded(
                    TERMINAL_RPC_BACKFILL_BLOCK_UNAVAILABLE)
            if not isinstance(result, Mapping):
                raise RpcBackfillBoundExceeded(
                    TERMINAL_RPC_BACKFILL_MALFORMED_RESPONSE)
            parent_slot = result.get("parentSlot")
            blockhash = result.get("blockhash")
            previous_blockhash = result.get("previousBlockhash")
            transactions = result.get("transactions")
            if (isinstance(parent_slot, bool)
                    or not isinstance(parent_slot, int) or parent_slot < 0
                    or not isinstance(blockhash, str) or not blockhash
                    or not isinstance(previous_blockhash, str)
                    or not previous_blockhash
                    or not isinstance(transactions, list)):
                raise RpcBackfillBoundExceeded(
                    TERMINAL_RPC_BACKFILL_MALFORMED_RESPONSE)
            if parent_slot >= int(slot):
                # A block whose declared parent does not precede it cannot be
                # the block for this slot: slot mismatch, fail closed.
                raise RpcBackfillBoundExceeded(
                    TERMINAL_RPC_BACKFILL_MALFORMED_RESPONSE)
            return dict(result)


# ---------------------------------------------------------------------------
# RPC JSON -> geyser SubscribeUpdate bridge
# ---------------------------------------------------------------------------

def _b58decode_or_none(value: object) -> Optional[bytes]:
    from PHX2.free_tier_producer.paid_grpc_source import _base58_decode
    return _base58_decode(value)


def build_subscribe_update_from_rpc_transaction(
    *, slot: int, block_time: Optional[int], transaction_index: int,
    tx_json: Mapping[str, Any],
) -> Optional[Any]:
    """Project one ``getBlock`` JSON transaction onto a ``SubscribeUpdate``.

    Mechanical projection only: every business decision (admission, reserve
    decoding, fee decoding, execution-status classification) continues to run
    in the SAME production decoders that consume the live gRPC stream.  The
    projection is deliberately conservative -- anything structurally unusable
    returns ``None`` and the caller counts a rejected transaction rather than
    fabricating a partial update.

    Only canonically successful transactions are projected (``meta.err`` must
    be ``null``), mirroring the live subscription's ``failed = False`` filter;
    a failed transaction can never produce an admission, a reserve event or a
    fee event on the live path either.
    """

    from PHX2.proto.stage28_11._generated import geyser_pb2

    if isinstance(slot, bool) or not isinstance(slot, int) or slot < 0:
        return None
    if not isinstance(tx_json, Mapping):
        return None
    meta_json = tx_json.get("meta")
    tx_body = tx_json.get("transaction")
    if not isinstance(meta_json, Mapping) or not isinstance(tx_body, Mapping):
        return None
    if meta_json.get("err") is not None:
        return None
    message_json = tx_body.get("message")
    signatures = tx_body.get("signatures")
    if not isinstance(message_json, Mapping) or not isinstance(
            signatures, list) or not signatures:
        return None
    signature_bytes = _b58decode_or_none(signatures[0])
    if not signature_bytes:
        return None

    update = geyser_pb2.SubscribeUpdate()
    wrapper = update.transaction
    wrapper.slot = int(slot)
    info = wrapper.transaction
    info.signature = signature_bytes
    info.is_vote = False
    info.index = max(0, int(transaction_index))

    message = info.transaction.message
    account_keys = message_json.get("accountKeys")
    if not isinstance(account_keys, list) or not account_keys:
        return None
    for key in account_keys:
        decoded = _b58decode_or_none(key)
        if decoded is None:
            return None
        message.account_keys.append(decoded)
    for instruction in message_json.get("instructions") or []:
        if not isinstance(instruction, Mapping):
            return None
        program_index = instruction.get("programIdIndex")
        accounts = instruction.get("accounts")
        if isinstance(program_index, bool) or not isinstance(
                program_index, int) or program_index < 0:
            return None
        if not isinstance(accounts, list) or any(
                isinstance(v, bool) or not isinstance(v, int) or v < 0
                or v > 255 for v in accounts):
            return None
        data = _b58decode_or_none(instruction.get("data") or "1")
        compiled = message.instructions.add()
        compiled.program_id_index = int(program_index)
        compiled.accounts = bytes(accounts)
        compiled.data = data if data is not None else b""

    meta = info.meta
    # Canonical success: the message-typed ``err`` field stays UNSET, which is
    # exactly what classify_transaction_execution_status treats as SUCCESS.
    for log in meta_json.get("logMessages") or []:
        if isinstance(log, str):
            meta.log_messages.append(log)
    for group in meta_json.get("innerInstructions") or []:
        if not isinstance(group, Mapping):
            return None
        index = group.get("index")
        if isinstance(index, bool) or not isinstance(index, int) or index < 0:
            return None
        inner_group = meta.inner_instructions.add()
        inner_group.index = int(index)
        for instruction in group.get("instructions") or []:
            if not isinstance(instruction, Mapping):
                return None
            program_index = instruction.get("programIdIndex")
            accounts = instruction.get("accounts")
            if isinstance(program_index, bool) or not isinstance(
                    program_index, int) or program_index < 0:
                return None
            if not isinstance(accounts, list) or any(
                    isinstance(v, bool) or not isinstance(v, int) or v < 0
                    or v > 255 for v in accounts):
                return None
            data = _b58decode_or_none(instruction.get("data") or "1")
            inner = inner_group.instructions.add()
            inner.program_id_index = int(program_index)
            inner.accounts = bytes(accounts)
            inner.data = data if data is not None else b""
            stack_height = instruction.get("stackHeight")
            if isinstance(stack_height, int) and not isinstance(
                    stack_height, bool) and stack_height > 0:
                inner.stack_height = int(stack_height)
    for name, attr in (("preTokenBalances", "pre_token_balances"),
                       ("postTokenBalances", "post_token_balances")):
        for balance in meta_json.get(name) or []:
            if not isinstance(balance, Mapping):
                continue
            mint = balance.get("mint")
            amount = balance.get("uiTokenAmount")
            decimals = amount.get("decimals") if isinstance(
                amount, Mapping) else None
            if not isinstance(mint, str) or not mint:
                continue
            if isinstance(decimals, bool) or not isinstance(decimals, int):
                continue
            entry = getattr(meta, attr).add()
            account_index = balance.get("accountIndex")
            if isinstance(account_index, int) and not isinstance(
                    account_index, bool) and account_index >= 0:
                entry.account_index = int(account_index)
            entry.mint = mint
            owner = balance.get("owner")
            if isinstance(owner, str) and owner:
                entry.owner = owner
            program_id = balance.get("programId")
            if isinstance(program_id, str) and program_id:
                entry.program_id = program_id
            amount_text = amount.get("amount")
            if (
                isinstance(amount_text, str)
                and amount_text.isdigit()
            ):
                entry.ui_token_amount.amount = amount_text
            entry.ui_token_amount.decimals = int(decimals)
            ui_amount = amount.get("uiAmount")
            if (
                isinstance(ui_amount, (int, float))
                and not isinstance(ui_amount, bool)
            ):
                entry.ui_token_amount.ui_amount = float(ui_amount)
            ui_amount_string = amount.get("uiAmountString")
            if isinstance(ui_amount_string, str):
                entry.ui_token_amount.ui_amount_string = ui_amount_string
    loaded = meta_json.get("loadedAddresses")
    if isinstance(loaded, Mapping):
        for name, attr in (("writable", "loaded_writable_addresses"),
                           ("readonly", "loaded_readonly_addresses")):
            for key in loaded.get(name) or []:
                decoded = _b58decode_or_none(key)
                if decoded is None:
                    return None
                getattr(meta, attr).append(decoded)

    if isinstance(block_time, int) and not isinstance(block_time, bool) \
            and block_time > 0:
        update.created_at.seconds = int(block_time)
        update.created_at.nanos = 0
    return update


def rpc_transaction_mentions_program(
    tx_json: Mapping[str, Any], program_id: str,
) -> bool:
    """The subscription-filter parity predicate (``account_include``)."""

    if not isinstance(tx_json, Mapping):
        return False
    tx_body = tx_json.get("transaction")
    if not isinstance(tx_body, Mapping):
        return False
    message = tx_body.get("message")
    keys: List[str] = []
    if isinstance(message, Mapping):
        for key in message.get("accountKeys") or []:
            if isinstance(key, str):
                keys.append(key)
    meta = tx_json.get("meta")
    if isinstance(meta, Mapping):
        loaded = meta.get("loadedAddresses")
        if isinstance(loaded, Mapping):
            for name in ("writable", "readonly"):
                for key in loaded.get(name) or []:
                    if isinstance(key, str):
                        keys.append(key)
    return str(program_id) in keys


# ---------------------------------------------------------------------------
# state-directory runtime ownership
# ---------------------------------------------------------------------------

RUNTIME_LOCK_BASENAME = "phx2_state_dir_runtime.lock"


class StateDirRuntimeLock:
    """Advisory single-owner lock for one durable state directory.

    The armed production session acquires it so the terminal-recovery operator
    tool can REFUSE to touch a state directory a live PHX2 runtime owns, and a
    second armed runtime cannot silently share one cursor.  Stale locks (a
    dead pid) are reclaimed; a lock held by this same process is re-entrant.
    """

    def __init__(self, state_dir: object,
                 basename: str = RUNTIME_LOCK_BASENAME) -> None:
        self._path = Path(state_dir) / basename
        self._acquired = False

    @property
    def path(self) -> Path:
        return self._path

    @staticmethod
    def _pid_alive(pid: int) -> bool:
        if isinstance(pid, bool) or not isinstance(pid, int) or pid <= 0:
            return False
        # On Windows ``os.kill(pid, 0)`` calls TerminateProcess rather than
        # performing the harmless POSIX probe its spelling suggests.  Reuse the
        # watchdog's Win32 read-only liveness check so stale-lock reclamation can
        # never kill a live or PID-reused process.
        if os.name == "nt":
            from PHX2.watchdog.process import pid_alive
            return pid_alive(pid)
        try:
            os.kill(pid, 0)
        except PermissionError:
            return True
        except OSError:
            return False
        return True

    def holder_pid(self) -> Optional[int]:
        try:
            text = self._path.read_text(encoding="utf-8").strip()
        except OSError:
            return None
        try:
            value = int(text.split("|", 1)[0])
        except (ValueError, IndexError):
            return None
        return value if value > 0 else None

    def held_by_live_other_process(self) -> bool:
        holder = self.holder_pid()
        if holder is None:
            return False
        if holder == os.getpid():
            return False
        return self._pid_alive(holder)

    def acquire(self) -> bool:
        holder = self.holder_pid()
        if holder == os.getpid():
            self._acquired = True
            return True
        if holder is not None and self._pid_alive(holder):
            return False
        if holder is not None:
            # Stale: the recorded process is gone. Reclaim.
            try:
                self._path.unlink()
            except OSError:
                return False
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            handle = os.open(
                str(self._path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except OSError:
            return False
        try:
            os.write(handle, f"{os.getpid()}|{_cpe.utc_now_iso()}".encode(
                "utf-8"))
        finally:
            os.close(handle)
        self._acquired = True
        return True

    def release(self) -> None:
        if not self._acquired:
            return
        self._acquired = False
        try:
            self._path.unlink()
        except OSError:
            pass


# ---------------------------------------------------------------------------
# backfill coordinator
# ---------------------------------------------------------------------------

class _OrderedBlockFetcher:
    """Fetch produced blocks concurrently, hand them back in canonical order.

    Network completion is allowed to be out of order; APPLICATION never is.
    The iterator yields strictly ascending slots, so the caller's parent-hash
    chain check, its duplicate suppression and its durable
    ``last_completed_slot`` all keep exactly the semantics they had under the
    original single-threaded driver.  Concurrency 1 takes a synchronous path
    that is byte-for-byte the old behaviour.

    In-flight work is bounded twice over: by the window (how far ahead of the
    application point fetching may run) and by the executor's worker count.
    Provider pressure observed by the adapter halves the effective concurrency,
    so a rate-limited provider is answered by backing off rather than by
    retrying harder.
    """

    def __init__(self, *, adapter: SolanaRpcBackfillAdapter, commitment: str,
                 slots: Sequence[int], concurrency: int, window: int) -> None:
        self._adapter = adapter
        self._commitment = str(commitment)
        self._slots = [int(slot) for slot in slots]
        self._max_concurrency = max(
            1, min(int(concurrency), RPC_CONCURRENCY_MAX))
        self._window = max(1, int(window))
        self.current_concurrency = self._max_concurrency
        self.pressure_reductions = 0
        self._seen_pressure_events = int(
            getattr(adapter, "pressure_events", 0) or 0)

    def _inflight_budget(self) -> int:
        events = int(getattr(self._adapter, "pressure_events", 0) or 0)
        if events > self._seen_pressure_events:
            self._seen_pressure_events = events
            reduced = max(1, self.current_concurrency // 2)
            if reduced < self.current_concurrency:
                self.current_concurrency = reduced
                self.pressure_reductions += 1
        return max(1, min(self._window,
                          self.current_concurrency
                          * RPC_INFLIGHT_WINDOW_MULTIPLIER))

    def __iter__(self) -> "Iterator[Tuple[int, Dict[str, Any]]]":
        if self._max_concurrency <= 1:
            for slot in self._slots:
                yield slot, self._adapter.get_block(
                    slot=slot, commitment=self._commitment)
            return
        executor = ThreadPoolExecutor(
            max_workers=self._max_concurrency,
            thread_name_prefix="phx2-rpc-block")
        futures: Dict[int, "Future[Dict[str, Any]]"] = {}
        submitted = 0
        try:
            for slot in self._slots:
                while submitted < len(self._slots) \
                        and len(futures) < self._inflight_budget():
                    ahead = self._slots[submitted]
                    futures[ahead] = executor.submit(
                        self._adapter.get_block, slot=ahead,
                        commitment=self._commitment)
                    submitted += 1
                future = futures.pop(slot)
                # A worker failure surfaces exactly when its slot's turn comes,
                # so the FIRST failing slot in canonical order is the one that
                # ends the pass -- never a later one that happened to fail
                # sooner in wall-clock time.
                yield slot, future.result()
        finally:
            for pending_future in futures.values():
                pending_future.cancel()
            executor.shutdown(wait=False, cancel_futures=True)


class _OrderedBlockScanner:
    """Fetch, decode and scan produced blocks; yield them in canonical order.

    This is the seam that fixes the application-throughput defect. The network
    may complete out of order and the worker POOL may complete out of order;
    what this iterator yields is always strictly ascending by slot, so the
    caller's parent-hash chain check, duplicate suppression and durable
    ``last_completed_slot`` keep exactly the semantics they had under the
    original single-threaded driver.

    Two modes, one set of semantics:

    * ``pool is None`` -- the block is decoded and scanned in THIS process.
      That is the serial reference implementation and it is unchanged
      behaviour.
    * ``pool`` present -- only the pure decode/scan runs in worker processes;
      the authoritative process keeps ordering, application and commit.

    Both modes call the same ``rpc_block_scan`` functions, so the parallel path
    cannot drift from the serial path it is proven against.
    """

    def __init__(self, *, adapter: SolanaRpcBackfillAdapter, commitment: str,
                 slots: Sequence[int], concurrency: int, window: int,
                 program_ids: Sequence[str], pool: Any = None,
                 stall_timeout_seconds: float = 120.0,
                 monotonic_fn: Callable[[], float] = time.monotonic) -> None:
        self._adapter = adapter
        self._commitment = str(commitment)
        self._slots = [int(slot) for slot in slots]
        self._program_ids = tuple(str(value) for value in program_ids)
        self._pool = pool
        self._fetcher = _OrderedBlockFetcher(
            adapter=adapter, commitment=commitment, slots=self._slots,
            concurrency=concurrency, window=window)
        self._max_concurrency = self._fetcher._max_concurrency
        self._window = max(1, int(window))
        if pool is not None:
            # Retained payloads/results are bounded by the pipeline depth, not
            # by the length of the pass.
            self._window = max(
                self._window,
                int(pool.batch_size) * int(pool.capacity_batches)
                + int(pool.batch_size))
        self._stall_timeout = max(1.0, float(stall_timeout_seconds))
        self._monotonic = monotonic_fn
        #: Prefilter accounting, redaction-safe.
        self.prefilter_skipped = 0
        self.prefilter_decoded = 0

    @property
    def current_concurrency(self) -> int:
        return int(self._fetcher.current_concurrency)

    @property
    def pressure_reductions(self) -> int:
        return int(self._fetcher.pressure_reductions)

    def _note(self, scan: Dict[str, Any]) -> Dict[str, Any]:
        if scan.get("prefilter") == _rbs.PREFILTER_DEFINITELY_IRRELEVANT:
            self.prefilter_skipped += 1
        else:
            self.prefilter_decoded += 1
        return scan

    def __iter__(self) -> "Iterator[Tuple[int, Dict[str, Any]]]":
        if self._pool is None:
            for slot, block in self._fetcher:
                yield slot, self._note(_rbs.scan_block_result(
                    slot=slot, result=block,
                    program_ids=self._program_ids))
            return
        yield from self._iter_pooled()

    def _iter_pooled(self) -> "Iterator[Tuple[int, Dict[str, Any]]]":
        pool = self._pool
        slots = self._slots
        total = len(slots)
        executor = ThreadPoolExecutor(
            max_workers=self._max_concurrency,
            thread_name_prefix="phx2-rpc-block")
        futures: Dict[int, "Future[bytes]"] = {}
        staged: List[Tuple[int, bytes]] = []
        ready: Dict[int, Dict[str, Any]] = {}
        #: ``awaiting`` is what the pool still owes; ``requested`` is
        #: everything it was ever asked for. A bounded worker retry can
        #: legitimately deliver a slot twice, so a second copy of a REQUESTED
        #: slot is discarded; a result for a slot that was never requested is
        #: the pool lying about its work and must fail closed rather than
        #: leave the pipeline waiting for something that will never arrive.
        awaiting: set = set()
        requested: set = set()
        submitted = 0
        scan_cursor = 0
        yield_cursor = 0
        last_progress = self._monotonic()
        try:
            while yield_cursor < total:
                progressed = False
                while submitted < total \
                        and len(futures) < self._fetcher._inflight_budget():
                    ahead = slots[submitted]
                    futures[ahead] = executor.submit(
                        self._adapter.get_block_payload, slot=ahead,
                        commitment=self._commitment)
                    submitted += 1
                while scan_cursor < total \
                        and len(staged) < pool.batch_size \
                        and (scan_cursor - yield_cursor) < self._window:
                    slot = slots[scan_cursor]
                    future = futures.get(slot)
                    if future is None or not future.done():
                        break
                    # A fetch failure surfaces at its slot's CANONICAL turn,
                    # never at whichever slot happened to fail first in
                    # wall-clock time.
                    staged.append((slot, future.result()))
                    futures.pop(slot, None)
                    scan_cursor += 1
                    progressed = True
                if staged and (len(staged) >= pool.batch_size
                               or scan_cursor >= total
                               or pool.outstanding_batches == 0):
                    if pool.try_submit(staged):
                        for slot, _payload in staged:
                            awaiting.add(slot)
                            requested.add(slot)
                        staged = []
                        progressed = True
                for result in pool.poll(timeout=0.02):
                    slot = result.get("slot")
                    key = (int(slot) if isinstance(slot, int)
                           and not isinstance(slot, bool) else None)
                    if key is None or key not in requested:
                        # Never requested: hand it to the parent against the
                        # slot actually expected so the authoritative
                        # slot-identity check refuses it, instead of holding a
                        # result nobody will ever ask for.
                        yield slots[yield_cursor], self._note(result)
                        return
                    if key not in awaiting:
                        continue  # duplicate copy of an already-owed slot
                    awaiting.discard(key)
                    ready[key] = result
                    progressed = True
                while yield_cursor < total and slots[yield_cursor] in ready:
                    slot = slots[yield_cursor]
                    yield_cursor += 1
                    yield slot, self._note(ready.pop(slot))
                    progressed = True
                if progressed:
                    last_progress = self._monotonic()
                else:
                    pending = futures.get(
                        slots[scan_cursor]) if scan_cursor < total else None
                    if pending is not None:
                        _futures_wait([pending], timeout=0.05)
                    else:
                        time.sleep(0.005)
                    # Liveness is bounded too: a batch whose results never
                    # arrive must end the pass retryably, never stall it.
                    if self._monotonic() - last_progress > self._stall_timeout:
                        raise BlockScanPoolError(_rbp.POOL_TIMEOUT)
        finally:
            for pending_future in futures.values():
                pending_future.cancel()
            executor.shutdown(wait=False, cancel_futures=True)


class RpcGapBackfillCoordinator:
    """Drives one recovery episode end to end. Owned by the reconnect owner.

    The coordinator holds NO second gRPC stream and NO business logic of its
    own: quarantined live events arrive from the owner's one replacement
    stream, and backfilled transactions run through the exact production
    decoders (`ingest_reserve_events_from_update`,
    ``ingest_fee_events_from_update``, ``decode_create_pool_update``) via the
    same per-event sequence the live source executes.
    """

    def __init__(
        self,
        *,
        config: RpcGapRecoveryConfig,
        recovery_store: RpcGapRecoveryStore,
        quarantine_buffer: QuarantinedLiveBuffer,
        subscription_identity_digest: str,
        rpc_post_fn: Optional[Callable[..., Tuple[int, Optional[Dict[str, Any]]]]] = None,
        rpc_timeout_seconds: float = DEFAULT_RPC_RECOVERY_TIMEOUT_SECONDS,
        reserve_index: Any = None,
        fee_index: Any = None,
        liquidity_index: Any = None,
        admission_config: Any = None,
        admission_sink: Optional[Callable[[Dict[str, Any]], None]] = None,
        proof_store: Any = None,
        provider_label: str = RPC_RECOVERY_PROVIDER_LABEL,
        monotonic_fn: Callable[[], float] = time.monotonic,
        sleep_fn: Callable[[float], None] = time.sleep,
        now_iso_fn: Callable[[], str] = _cpe.utc_now_iso,
    ) -> None:
        refusals = validate_rpc_gap_recovery_config(config)
        if refusals:
            raise ValueError("RPC_GAP_RECOVERY_CONFIG_REFUSED: "
                             + ", ".join(refusals))
        if config.mode != GAP_RECOVERY_MODE_RPC_BACKFILL:
            raise ValueError("RPC_GAP_RECOVERY_MODE_NOT_BACKFILL")
        self._config = config
        self._store = recovery_store
        self._buffer = quarantine_buffer
        self._identity_digest = str(subscription_identity_digest)
        self._rpc_post_fn = rpc_post_fn
        self._rpc_timeout = float(rpc_timeout_seconds)
        self._reserve_index = reserve_index
        self._fee_index = fee_index
        self._liquidity_index = liquidity_index
        self._admission_config = admission_config
        self._admission_sink = admission_sink
        self._proof_store = proof_store
        self._provider_label = str(provider_label)
        self._monotonic = monotonic_fn
        self._sleep = sleep_fn
        self._now_iso = now_iso_fn
        self._lock = threading.RLock()
        self._cursor_store: Any = None
        self._segment = 0
        self._segment_first_recorded = False
        self._segment_last_observed: Dict[int, int] = {}
        self._stop_requested = False
        self._upgrade_outcome: Optional[str] = None
        #: Live catch-up telemetry for the current backfill pass.
        self._catchup: Dict[str, Any] = {
            "blocks_per_second": 0.0,
            "eta_seconds": None,
            "current_concurrency": int(config.rpc_concurrency),
            "configured_max_concurrency": int(config.rpc_concurrency),
            "pressure_reductions": 0,
        }

    # -- episode lifecycle -----------------------------------------------

    @property
    def config(self) -> RpcGapRecoveryConfig:
        return self._config

    def request_stop(self) -> None:
        self._stop_requested = True

    def state(self) -> str:
        return self._store.state.recovery_state

    def is_proven(self) -> bool:
        return self.state() == RECOVERY_STATE_RECOVERY_PROVEN

    def is_terminal(self) -> bool:
        return (self.state() == RECOVERY_STATE_RECOVERY_TERMINAL
                or self._store.quarantined)

    def is_paused(self) -> bool:
        """The episode exhausted a bounded attempt clock and may resume."""

        return (not self._store.quarantined
                and self.state() == RECOVERY_STATE_RECOVERY_PAUSED_RETRYABLE)

    def pause_reason(self) -> Optional[str]:
        return self._store.state.paused_reason

    def upgrade_outcome(self) -> Optional[str]:
        """Closed-set result of the startup terminal -> retryable upgrade."""

        return self._upgrade_outcome

    def next_resume_slot(self) -> Optional[int]:
        state = self._store.state
        if int(state.safe_from_slot) < 0:
            return None
        return next_resume_slot(state.to_record())

    def terminal_reason(self) -> Optional[str]:
        if self._store.quarantined:
            return TERMINAL_RECOVERY_STATE_QUARANTINED
        return self._store.state.terminal_reason

    def has_resumable_episode(self) -> bool:
        return self._store.has_resumable_episode()

    def begin_or_resume_episode(
        self, *, cursor_store: Any,
        entry_classification: Optional[str] = None,
    ) -> Tuple[bool, str]:
        """Open a fresh eligible episode, or resume the persisted one.

        On restart no live classification exists; only a persisted resumable
        episode (which recorded its classification when it opened) may
        continue.  A terminal cursor with no recorded eligible episode stays
        terminal exactly as certified.
        """

        self._cursor_store = cursor_store
        if self._store.quarantined or self._buffer.quarantined:
            return False, TERMINAL_RECOVERY_STATE_QUARANTINED
        if not self._buffer.identity_matches:
            return False, TERMINAL_RECOVERY_STATE_QUARANTINED
        # A persisted episode that was ended purely by a bounded attempt clock
        # is upgraded IN PLACE to the retryable pause before anything else is
        # considered. The upgrade is authenticated, idempotent and
        # invariant-gated: an episode with any integrity defect, or one ended
        # for any other reason, is left terminal exactly as certified.
        self._upgrade_outcome = self._store.upgrade_terminal_to_retryable()
        if self._store.has_resumable_episode():
            state = self._store.state
            if state.subscription_identity_digest != self._identity_digest:
                self._store.mark_terminal(
                    reason=TERMINAL_RECOVERY_STATE_QUARANTINED)
                return False, TERMINAL_RECOVERY_STATE_QUARANTINED
            if int(state.cursor_recovery_generation) != int(
                    cursor_store.state.recovery_generation):
                self._store.mark_terminal(
                    reason=TERMINAL_RECOVERY_STATE_QUARANTINED)
                return False, TERMINAL_RECOVERY_STATE_QUARANTINED
            self._buffer.bind_episode(state.episode_generation)
            self._restore_segment_tracking()
            return True, state.recovery_state
        if entry_classification is None:
            return False, TERMINAL_RPC_BACKFILL_ENTRY_INELIGIBLE
        if entry_classification not in BACKFILL_ELIGIBLE_CLASSIFICATIONS:
            return False, TERMINAL_RPC_BACKFILL_ENTRY_INELIGIBLE
        boundary = cursor_store.safe_resume_slot()
        if boundary is None:
            return False, TERMINAL_RPC_BACKFILL_ENTRY_INELIGIBLE
        try:
            state = self._store.open_episode(
                entry_classification=entry_classification,
                safe_from_slot=int(boundary),
                subscription_identity_digest=self._identity_digest,
                authoritative_commitment=str(
                    self._config.authoritative_commitment),
                cursor_recovery_generation=int(
                    cursor_store.state.recovery_generation),
                cursor_attempt_generation=int(
                    cursor_store.state.attempt_generation),
            )
        except (RecoveryStoreWriteError, ValueError):
            return False, TERMINAL_RECOVERY_STATE_QUARANTINED
        self._buffer.bind_episode(state.episode_generation)
        self._segment = 0
        self._segment_first_recorded = False
        self._segment_last_observed = {}
        return True, state.recovery_state

    def _restore_segment_tracking(self) -> None:
        with self._lock:
            self._segment = int(self._store.state.quarantine_segments)
            self._segment_first_recorded = False
            self._segment_last_observed = {}
            for entry in self._buffer.ordered_entries():
                segment = int(entry.get("segment") or 0)
                slot = int(entry.get("slot") or 0)
                previous = self._segment_last_observed.get(segment)
                if previous is None or slot > previous:
                    self._segment_last_observed[segment] = slot

    # -- quarantined live capture ----------------------------------------

    def begin_quarantine_segment(self) -> int:
        """One replacement live stream attempt = one segment."""

        with self._lock:
            self._segment += 1
            self._segment_first_recorded = False
            try:
                self._store.update(
                    quarantine_segments=self._segment,
                    recovery_state=(
                        RECOVERY_STATE_LIVE_STREAM_QUARANTINED
                        if self._store.state.recovery_state
                        in (RECOVERY_STATE_REPLAY_REFUSED,
                            RECOVERY_STATE_LIVE_STREAM_QUARANTINED)
                        else self._store.state.recovery_state))
            except RecoveryStoreWriteError:
                pass
            return self._segment

    def note_observed_transaction(
        self, *, slot: int, signature: str, transaction_index: Optional[int],
        skip_identity: str, attempt_generation: int,
    ) -> None:
        """Record one quarantined live transaction observation.

        The FIRST observation of the episode becomes the overlap target and is
        buffered durably; the first observation of every later segment is also
        buffered durably (it anchors the segment for post-proof gap
        accounting).  Every observation updates the in-memory segment tail.
        """

        if self.is_terminal():
            return
        with self._lock:
            segment = max(1, self._segment)
            previous = self._segment_last_observed.get(segment)
            if previous is None or int(slot) > previous:
                self._segment_last_observed[segment] = int(slot)
            need_target = self._store.state.recovery_target_slot is None
            need_segment_anchor = not self._segment_first_recorded
            if not need_target and not need_segment_anchor:
                return
            self._segment_first_recorded = True
            entry = {
                "event_kind": BUFFER_EVENT_TRANSACTION_OBSERVED,
                "slot": int(slot),
                "signature": str(signature),
                "transaction_index": (
                    int(transaction_index)
                    if isinstance(transaction_index, int)
                    and not isinstance(transaction_index, bool) else None),
                "skip_identity": str(skip_identity),
                "candidate": None,
                "attempt_generation": int(attempt_generation),
                "segment": segment,
            }
            try:
                self._buffer.append(entry)
            except QuarantineBufferCapacityExceeded:
                self._mark_terminal(TERMINAL_RECOVERY_BUFFER_CAPACITY_EXCEEDED)
                return
            except (RecoveryStoreWriteError, ValueError):
                self._mark_terminal(TERMINAL_RECOVERY_STATE_QUARANTINED)
                return
            if need_target:
                try:
                    self._store.update(
                        recovery_target_slot=int(slot),
                        quarantined_live_first_slot=int(slot),
                        overlap_slot=int(slot),
                        overlap_signature=str(signature),
                        overlap_skip_identity=str(skip_identity),
                        recovery_state=RECOVERY_STATE_LIVE_STREAM_QUARANTINED,
                    )
                except RecoveryStoreWriteError:
                    self._mark_terminal(TERMINAL_RECOVERY_STATE_QUARANTINED)

    def buffer_admitted_candidate(
        self, *, candidate: Mapping[str, Any], slot: int, signature: str,
        transaction_index: Optional[int], skip_identity: str,
        attempt_generation: int,
    ) -> bool:
        """Durably buffer one quarantined admitted-migration candidate."""

        if self.is_terminal():
            return False
        entry = {
            "event_kind": BUFFER_EVENT_MIGRATION_ADMITTED,
            "slot": int(slot),
            "signature": str(signature),
            "transaction_index": (
                int(transaction_index)
                if isinstance(transaction_index, int)
                and not isinstance(transaction_index, bool) else None),
            "skip_identity": str(skip_identity),
            "candidate": dict(candidate),
            "attempt_generation": int(attempt_generation),
            "segment": max(1, self._segment),
        }
        try:
            self._buffer.append(entry)
            return True
        except QuarantineBufferCapacityExceeded:
            self._mark_terminal(TERMINAL_RECOVERY_BUFFER_CAPACITY_EXCEEDED)
            return False
        except (RecoveryStoreWriteError, ValueError):
            self._mark_terminal(TERMINAL_RECOVERY_STATE_QUARANTINED)
            return False

    # -- backfill ---------------------------------------------------------

    def _mark_terminal(self, reason: str) -> None:
        self._store.mark_terminal(reason=reason)

    def _pause_or_terminal(self, reason: str) -> None:
        """Pause retryably when that is legal, otherwise end the episode.

        The store owns the decision: it re-checks every integrity invariant
        against the durable record and refuses the pause on any doubt, so an
        unknown or structurally-broken episode can never become resumable by
        going through this path.
        """

        if self._store.pause_retryable(reason=reason):
            return
        self._mark_terminal(reason)

    def mark_session_failure(self, reason: str) -> None:
        """Owner-visible structural failure (e.g. observer-less factory)."""

        self._mark_terminal(reason)

    def _runtime_exceeded(self, started: float) -> bool:
        return (self._monotonic() - started) > float(
            self._config.max_backfill_runtime_seconds)

    def _wait_for_overlap_target(self, started: float) -> Optional[int]:
        deadline = self._monotonic() + float(
            self._config.max_overlap_wait_seconds)
        while True:
            target = self._store.state.recovery_target_slot
            if target is not None:
                return int(target)
            if self._stop_requested:
                return None
            if self._runtime_exceeded(started):
                self._pause_or_terminal(TERMINAL_RPC_BACKFILL_TIMEOUT)
                return None
            if self._monotonic() >= deadline:
                self._mark_terminal(TERMINAL_RECOVERY_OVERLAP_NOT_PROVEN)
                return None
            self._sleep(0.05)

    def _wait_for_commitment(self, adapter: SolanaRpcBackfillAdapter,
                             target: int, started: float) -> bool:
        commitment = str(self._config.authoritative_commitment)
        deadline = self._monotonic() + float(
            self._config.max_commitment_wait_seconds)
        while True:
            try:
                visible = adapter.get_slot(commitment=commitment)
            except RpcBackfillBoundExceeded as exc:
                self._mark_terminal(exc.reason)
                return False
            if visible >= int(target):
                return True
            if self._stop_requested:
                return False
            if self._runtime_exceeded(started):
                self._mark_terminal(TERMINAL_RPC_BACKFILL_TIMEOUT)
                return False
            if self._monotonic() >= deadline:
                self._mark_terminal(TERMINAL_RPC_BACKFILL_COMMITMENT_TIMEOUT)
                return False
            self._sleep(min(1.0, float(
                self._config.rpc_request_spacing_seconds)))

    def _process_bridged_update(
        self, *, update: Any, slot: int, signature: str,
        transaction_index: int,
        apply_candidate_fn: Optional[Callable[[Dict[str, Any]], bool]],
        counters: Dict[str, int],
    ) -> Optional[str]:
        """One bridged transaction through the production event sequence.

        Returns the admitted-migration skip identity when a candidate was
        applied, else ``None``.  Mirrors
        ``PaidCreatePoolYellowstoneSource.iter_events`` step for step so the
        recovery path cannot drift from the live path.
        """

        from PHX2.free_tier_producer.paid_grpc_source import (
            build_admitted_event_identity,
            build_transaction_skip_identity,
            decode_create_pool_update,
        )
        from PHX2.free_tier_producer.phx1_fee_gate import (
            ingest_fee_events_from_update,
        )
        from PHX2.free_tier_producer.pumpswap_reserves import (
            ingest_reserve_events_from_update,
        )

        skip_identity = build_transaction_skip_identity(
            slot, signature, transaction_index)
        cursor = self._cursor_store
        if cursor is not None:
            try:
                if cursor.is_duplicate(skip_identity):
                    counters["duplicates"] += 1
                    try:
                        cursor.record_duplicate_replay()
                    except Exception:
                        pass
                    return None
            except Exception:
                pass
        if self._reserve_index is not None:
            counters["reserve_events"] += ingest_reserve_events_from_update(
                update, reserve_index=self._reserve_index)
        if self._fee_index is not None:
            counters["fee_events"] += ingest_fee_events_from_update(
                update, fee_index=self._fee_index)
        decision_holder: Dict[str, Any] = {}

        def _observe(decision: Any,
                     _holder: Dict[str, Any] = decision_holder) -> None:
            _holder["decision"] = decision
            if not getattr(decision, "admitted", False) \
                    and self._admission_sink is not None:
                try:
                    self._admission_sink(decision.diagnostic_record())
                except Exception:
                    pass

        event = decode_create_pool_update(
            update, provider_name=self._provider_label,
            admission_config=self._admission_config,
            admission_observer=_observe)
        if event is None:
            counters["rejected"] += 1
            if cursor is not None:
                try:
                    cursor.commit_event(
                        slot=slot, identity=skip_identity,
                        signature=signature, replayed=True)
                except Exception:
                    pass
            return None
        decision = decision_holder.get("decision")
        proof = getattr(decision, "proof", None)
        if proof is not None:
            if self._proof_store is not None:
                try:
                    self._proof_store.seal_and_store(proof)
                except Exception:
                    counters["rejected"] += 1
                    return None
            if self._liquidity_index is not None:
                try:
                    self._liquidity_index.register_migration_proof(proof)
                except Exception:
                    pass
        if self._reserve_index is not None:
            try:
                self._reserve_index.register_pool(
                    pool_address=getattr(event, "pool_account", None),
                    base_mint=getattr(event, "base_mint", None),
                    quote_mint=getattr(event, "quote_mint", None),
                    creation_timestamp=getattr(event, "observed_at_utc", None),
                )
            except Exception:
                pass
        applied = False
        if apply_candidate_fn is not None:
            from PHX2.free_tier_producer.paid_provider import event_to_candidate
            candidate = event_to_candidate(
                event, replayed=True,
                migration_proof=proof,
                migration_signature=signature,
                provider_event_time_utc=getattr(event, "observed_at_utc", None),
                provider_event_time_source="PROVIDER_CREATED_AT")
            if candidate is not None:
                try:
                    applied = bool(apply_candidate_fn(candidate))
                except Exception:
                    applied = False
        counters["migrations"] += 1
        detail_identity = build_admitted_event_identity(
            decision, slot=slot, signature=signature,
            transaction_index=transaction_index)
        if cursor is not None and (applied or apply_candidate_fn is None):
            try:
                cursor.commit_event(
                    slot=slot, identity=skip_identity, signature=signature,
                    replayed=True, detail_identity=detail_identity)
            except Exception:
                pass
        return skip_identity

    def run_backfill(
        self,
        *,
        apply_candidate_fn: Optional[Callable[[Dict[str, Any]], bool]] = None,
    ) -> bool:
        """Execute the bounded backfill for the open episode. Synchronous.

        Returns ``True`` only when the episode reached ``RECOVERY_PROVEN``
        (exact overlap plus complete block coverage plus atomic cursor
        resolution).  Every other outcome is terminal with a closed-set
        reason; nothing here can resume at the live head.
        """

        from PHX2.stage29.pumpswap_program_constants import PUMPSWAP_PROGRAM_ID

        started = self._monotonic()
        store = self._store
        state = store.state
        if store.quarantined:
            return False
        if state.recovery_state not in RESUMABLE_RECOVERY_STATES:
            return state.recovery_state == RECOVERY_STATE_RECOVERY_PROVEN
        gap_guard_target = state.recovery_target_slot
        safe_from = int(state.safe_from_slot)
        target = (int(gap_guard_target) if gap_guard_target is not None
                  else self._wait_for_overlap_target(started))
        if target is None:
            return False
        gap_slots = target - safe_from
        if gap_slots < 0:
            self._mark_terminal(TERMINAL_RPC_BACKFILL_FORK_INCONSISTENT)
            return False
        # ``max_gap_slots`` is a per-RPC chunk bound, not a terminal bound on
        # total recoverable history. Long ranges are enumerated in contiguous
        # chunks and still resume from per-block durable progress below.
        if self._rpc_post_fn is None:
            self._mark_terminal(TERMINAL_RPC_BACKFILL_TRANSPORT_ABSENT)
            return False
        adapter = SolanaRpcBackfillAdapter(
            rpc_post_fn=self._rpc_post_fn, config=self._config,
            timeout_seconds=self._rpc_timeout,
            monotonic_fn=self._monotonic, sleep_fn=self._sleep)
        counters = {"scanned": 0, "relevant": 0, "rejected": 0,
                    "duplicates": 0, "migrations": 0, "reserve_events": 0,
                    "fee_events": 0}
        #: Bound to the bounded worker pool for the lifetime of this pass; it
        #: is always shut down deterministically before the method returns.
        pool: Optional[Any] = None
        since_checkpoint = 0
        previous_slot = None
        previous_hash = None

        def _flush(extra: Optional[Dict[str, Any]] = None) -> None:
            base = store.state
            changes: Dict[str, Any] = {
                "transactions_scanned": base.transactions_scanned,
                "transactions_relevant": base.transactions_relevant,
                "transactions_rejected": base.transactions_rejected,
                "duplicate_events_suppressed": base.duplicate_events_suppressed,
                "migration_events_recovered": base.migration_events_recovered,
                "reserve_events_recovered": base.reserve_events_recovered,
                "fee_events_recovered": base.fee_events_recovered,
                "backfill_runtime_ms": int(
                    (self._monotonic() - started) * 1000),
            }
            changes.update(adapter.counters())
            if extra:
                changes.update(extra)
            try:
                store.update(**changes)
            except RecoveryStoreWriteError:
                pass

        try:
            store.update(recovery_state=RECOVERY_STATE_RPC_BACKFILL_PLANNED)
            if not self._wait_for_commitment(adapter, target, started):
                _flush()
                return False
            produced: List[int] = []
            chunk_size = min(
                int(self._config.max_gap_slots),
                int(self._config.max_produced_blocks),
            )
            chunk_start = int(safe_from)
            while chunk_start <= int(target):
                chunk_end = min(
                    int(target), chunk_start + chunk_size - 1)
                chunk_produced = adapter.get_blocks(
                    start_slot=chunk_start, end_slot=chunk_end,
                    commitment=str(self._config.authoritative_commitment))
                if len(chunk_produced) > int(
                        self._config.max_produced_blocks):
                    self._mark_terminal(
                        TERMINAL_RPC_BACKFILL_BLOCK_LIMIT_EXCEEDED)
                    _flush()
                    return False
                produced.extend(chunk_produced)
                chunk_start = chunk_end + 1
            produced_set = set(produced)
            skipped_total = (target - safe_from + 1) - len(produced)
            if target not in produced_set:
                # The overlap target was OBSERVED live by the quarantined
                # stream; a range proof that calls it skipped contradicts
                # buffered evidence.
                self._mark_terminal(TERMINAL_RPC_BACKFILL_FORK_INCONSISTENT)
                _flush()
                return False
            for entry in self._buffer.ordered_entries():
                entry_slot = int(entry.get("slot") or 0)
                if safe_from <= entry_slot <= target \
                        and entry_slot not in produced_set:
                    self._mark_terminal(
                        TERMINAL_RPC_BACKFILL_FORK_INCONSISTENT)
                    _flush()
                    return False
            store.update(
                recovery_state=RECOVERY_STATE_RPC_BACKFILL_RUNNING,
                produced_blocks_total=len(produced),
                skipped_slots_total=int(skipped_total))

            resume_after = store.state.last_completed_slot
            previous_slot: Optional[int] = None
            previous_hash: Optional[str] = store.state.last_completed_blockhash
            if resume_after is not None:
                previous_slot = int(resume_after)
            overlap_identity: Optional[str] = None
            overlap_signature_seen = False
            expected_signature = store.state.overlap_signature
            expected_identity = store.state.overlap_skip_identity

            pending = [
                slot for slot in produced
                if resume_after is None or slot > int(resume_after)]
            program_ids = (PUMPSWAP_PROGRAM_ID,)
            pool = None
            if int(self._config.rpc_apply_processes) > 1:
                if not adapter.supports_raw_payloads:
                    # Refusing is the whole point: silently running the
                    # known-diverging serial path during production recovery is
                    # exactly the failure this change exists to remove.
                    self._pause_or_terminal(
                        TERMINAL_RPC_APPLY_POOL_UNAVAILABLE)
                    _flush()
                    return False
                try:
                    pool = BoundedBlockScanPool(
                        processes=int(self._config.rpc_apply_processes),
                        queue_bound=int(self._config.rpc_apply_queue_bound),
                        batch_size=int(self._config.rpc_apply_batch_size),
                        worker_timeout_seconds=float(
                            self._config.rpc_worker_timeout_seconds),
                        program_ids=program_ids,
                        monotonic_fn=self._monotonic)
                except BlockScanPoolError:
                    self._pause_or_terminal(
                        TERMINAL_RPC_APPLY_POOL_UNAVAILABLE)
                    _flush()
                    return False
            fetcher = _OrderedBlockScanner(
                adapter=adapter,
                commitment=str(self._config.authoritative_commitment),
                slots=pending,
                concurrency=int(self._config.rpc_concurrency),
                window=max(1, int(self._config.rpc_concurrency)
                           * RPC_INFLIGHT_WINDOW_MULTIPLIER),
                program_ids=program_ids,
                pool=pool,
                stall_timeout_seconds=float(
                    self._config.rpc_worker_timeout_seconds),
                monotonic_fn=self._monotonic,
            )
            checkpoint_every = max(
                1, int(self._config.checkpoint_every_blocks))
            since_checkpoint = 0
            applied_blocks = 0
            catchup_started = self._monotonic()

            def _checkpoint(block_slot: int, blockhash: str) -> None:
                base = store.state
                store.update(
                    last_completed_slot=int(block_slot),
                    last_completed_blockhash=str(blockhash),
                    produced_blocks_completed=(
                        base.produced_blocks_completed + since_checkpoint),
                    transactions_scanned=(
                        base.transactions_scanned + counters["scanned"]),
                    transactions_relevant=(
                        base.transactions_relevant + counters["relevant"]),
                    transactions_rejected=(
                        base.transactions_rejected + counters["rejected"]),
                    duplicate_events_suppressed=(
                        base.duplicate_events_suppressed
                        + counters["duplicates"]),
                    migration_events_recovered=(
                        base.migration_events_recovered
                        + counters["migrations"]),
                    reserve_events_recovered=(
                        base.reserve_events_recovered
                        + counters["reserve_events"]),
                    fee_events_recovered=(
                        base.fee_events_recovered + counters["fee_events"]),
                    backfill_runtime_ms=int(
                        (self._monotonic() - started) * 1000),
                    **adapter.counters())
                for key in counters:
                    counters[key] = 0

            for block_slot, scan in fetcher:
                if self._stop_requested:
                    if since_checkpoint:
                        _checkpoint(int(previous_slot), str(previous_hash))
                    _flush()
                    return False
                if self._runtime_exceeded(started):
                    # A bounded ATTEMPT clock, not an integrity verdict: commit
                    # the contiguous prefix that IS complete, then pause so the
                    # next attempt resumes at last_completed_slot + 1.
                    if since_checkpoint:
                        _checkpoint(int(previous_slot), str(previous_hash))
                    self._pause_or_terminal(TERMINAL_RPC_BACKFILL_TIMEOUT)
                    _flush()
                    return False
                # A worker result is untrusted structural input: schema, slot
                # identity and entry ordering are proven BEFORE anything from
                # it can touch authoritative state.
                accepted, _token = _rbs.validate_scan_result(
                    scan, expected_slot=block_slot)
                if not accepted:
                    self._mark_terminal(
                        TERMINAL_RPC_BACKFILL_MALFORMED_RESPONSE)
                    _flush()
                    return False
                if scan["status"] != _rbs.BLOCK_SCAN_OK:
                    self._mark_terminal(
                        TERMINAL_RPC_BACKFILL_BLOCK_UNAVAILABLE
                        if scan["status"] == _rbs.BLOCK_SCAN_UNAVAILABLE
                        else TERMINAL_RPC_BACKFILL_MALFORMED_RESPONSE)
                    _flush()
                    return False
                if previous_slot is not None:
                    if int(scan["parent_slot"]) != int(previous_slot):
                        self._mark_terminal(
                            TERMINAL_RPC_BACKFILL_FORK_INCONSISTENT)
                        _flush()
                        return False
                    if previous_hash is not None and str(
                            scan["previous_blockhash"]) != str(previous_hash):
                        self._mark_terminal(
                            TERMINAL_RPC_BACKFILL_FORK_INCONSISTENT)
                        _flush()
                        return False
                # The transaction budget is consumed by EVERY scanned
                # transaction, relevant or not, and is crossed at exactly the
                # transaction that crosses it -- the same position the
                # single-threaded driver stopped at.
                transaction_count = int(scan["transaction_count"])
                allowed = (int(self._config.max_transactions)
                           - int(store.state.transactions_scanned)
                           - int(counters["scanned"]))
                budget_exceeded = transaction_count > allowed
                scan_upto = (transaction_count if not budget_exceeded
                             else max(0, allowed))
                for entry in scan["entries"]:
                    tx_index = int(entry["index"])
                    if tx_index >= scan_upto:
                        break
                    kind = entry["kind"]
                    if kind == _rbs.ENTRY_REJECT_META:
                        counters["rejected"] += 1
                        continue
                    counters["relevant"] += 1
                    if kind in (_rbs.ENTRY_REJECT_SIGNATURE,
                                _rbs.ENTRY_REJECT_PROJECTION):
                        counters["rejected"] += 1
                        continue
                    update = _rbs.parse_scan_entry_update(entry)
                    if update is None:
                        self._mark_terminal(
                            TERMINAL_RPC_BACKFILL_MALFORMED_RESPONSE)
                        _flush()
                        return False
                    signature = str(entry["signature"])
                    self._process_bridged_update(
                        update=update, slot=block_slot, signature=signature,
                        transaction_index=tx_index,
                        apply_candidate_fn=apply_candidate_fn,
                        counters=counters)
                    if (block_slot == target and expected_signature is not None
                            and signature == expected_signature):
                        overlap_signature_seen = True
                        from PHX2.free_tier_producer.paid_grpc_source import (
                            build_transaction_skip_identity,
                        )
                        bridged_identity = build_transaction_skip_identity(
                            block_slot, signature, tx_index)
                        if bridged_identity == expected_identity:
                            overlap_identity = bridged_identity
                counters["scanned"] += scan_upto + (1 if budget_exceeded else 0)
                if budget_exceeded:
                    self._mark_terminal(
                        TERMINAL_RPC_BACKFILL_TRANSACTION_LIMIT_EXCEEDED)
                    _flush()
                    return False
                # Block fully applied. Durable progress advances only across a
                # CONTIGUOUS completed prefix: blocks arrive out of order from
                # the network AND from the worker pool but are applied strictly
                # ascending, so ``last_completed_slot`` is always the top of an
                # unbroken run.
                previous_slot = int(block_slot)
                previous_hash = str(scan["blockhash"])
                since_checkpoint += 1
                applied_blocks += 1
                if since_checkpoint >= checkpoint_every:
                    _checkpoint(previous_slot, previous_hash)
                    since_checkpoint = 0
                elapsed = max(1e-6, self._monotonic() - catchup_started)
                rate = applied_blocks / elapsed
                remaining = max(0, len(pending) - applied_blocks)
                with self._lock:
                    self._catchup.update({
                        "blocks_per_second": round(rate, 3),
                        "eta_seconds": (
                            None if rate <= 0 else int(remaining / rate)),
                        "current_concurrency": fetcher.current_concurrency,
                        "configured_max_concurrency": int(
                            self._config.rpc_concurrency),
                        "pressure_reductions": fetcher.pressure_reductions,
                        "apply_processes": int(
                            self._config.rpc_apply_processes),
                        "prefilter_skipped_blocks": fetcher.prefilter_skipped,
                        "prefilter_decoded_blocks": fetcher.prefilter_decoded,
                        "worker_restarts": (
                            0 if pool is None else int(pool.restarts)),
                    })

            if since_checkpoint and previous_slot is not None:
                _checkpoint(int(previous_slot), str(previous_hash))
                since_checkpoint = 0

            # Complete coverage reached. The overlap event must have matched
            # exactly inside its RPC block.
            final_state = store.state
            if overlap_identity is None:
                already = (final_state.overlap_proof_state == OVERLAP_PROVEN)
                if already:
                    overlap_identity = final_state.overlap_skip_identity
                elif final_state.last_completed_slot is not None \
                        and int(final_state.last_completed_slot) >= target:
                    # Every block through the target completed without an
                    # exact match. A buffered signature entirely absent from
                    # the authoritative chain is fork-inconsistent; a
                    # signature that WAS found but at a different instruction
                    # identity is an unproven overlap. Neither is coverage.
                    if expected_signature is None:
                        self._mark_terminal(
                            TERMINAL_RECOVERY_OVERLAP_NOT_PROVEN)
                    elif overlap_signature_seen:
                        self._mark_terminal(
                            TERMINAL_RECOVERY_OVERLAP_NOT_PROVEN)
                    else:
                        self._mark_terminal(
                            TERMINAL_RPC_BACKFILL_FORK_INCONSISTENT)
                    _flush()
                    return False
                else:
                    self._mark_terminal(TERMINAL_RECOVERY_OVERLAP_NOT_PROVEN)
                    _flush()
                    return False
            resolve = getattr(
                self._cursor_store,
                "resolve_terminal_retention_with_backfill_proof", None)
            resolved = False
            if callable(resolve):
                try:
                    resolved = bool(resolve(
                        safe_from_slot=safe_from,
                        proven_target_slot=target,
                        overlap_identity=overlap_identity,
                        recovery_generation=int(
                            final_state.cursor_recovery_generation),
                        subscription_identity_digest=self._identity_digest))
                except Exception:
                    resolved = False
            if not resolved:
                self._mark_terminal(
                    TERMINAL_RECOVERY_CURSOR_RESOLUTION_REFUSED)
                _flush()
                return False
            _flush(extra={
                "recovery_state": RECOVERY_STATE_RECOVERY_PROVEN,
                "overlap_proof_state": OVERLAP_PROVEN,
            })
            return True
        except BlockScanPoolError:
            # Bounded worker restarts and task retries are exhausted. Nothing
            # already applied is in doubt, so the durable contiguous prefix is
            # committed and the episode pauses RETRYABLY: it never crosses the
            # unresolved produced block and it never advances the cursor.
            if since_checkpoint and previous_slot is not None:
                try:
                    _checkpoint(int(previous_slot), str(previous_hash))
                except RecoveryStoreWriteError:
                    pass
            self._pause_or_terminal(TERMINAL_RPC_APPLY_POOL_UNAVAILABLE)
            _flush()
            return False
        except RpcBackfillBoundExceeded as exc:
            # ``_pause_or_terminal`` re-checks the closed retryable set and
            # every integrity invariant, so only an exhausted attempt clock on
            # an intact episode pauses; every other bound stays terminal.
            self._pause_or_terminal(exc.reason)
            _flush()
            return False
        except (RecoveryStoreWriteError, QuarantineBufferCapacityExceeded):
            self._mark_terminal(TERMINAL_RECOVERY_STATE_QUARANTINED)
            return False
        finally:
            if pool is not None:
                pool.close()

    # -- post-proof drain -------------------------------------------------

    def drain_plan(self) -> Dict[str, Any]:
        """Deterministic application plan for the buffered live events."""

        entries = self._buffer.ordered_entries()
        candidates = [entry for entry in entries
                      if entry.get("event_kind")
                      == BUFFER_EVENT_MIGRATION_ADMITTED]
        segments = sorted({int(entry.get("segment") or 0)
                           for entry in entries}) or [1]
        reopen_boundary: Optional[int] = None
        if len(segments) > 1 or int(
                self._store.state.quarantine_segments) > 1:
            first_segment = segments[0]
            with self._lock:
                tail = self._segment_last_observed.get(first_segment)
            slots = [int(entry.get("slot") or 0) for entry in entries
                     if int(entry.get("segment") or 0) == first_segment]
            reopen_boundary = max(
                [value for value in (tail, max(slots) if slots else None,
                                     self._store.state.recovery_target_slot)
                 if value is not None])
        return {
            "candidates": candidates,
            "segments": segments,
            "requires_reopened_episode": reopen_boundary is not None,
            "reopen_boundary_slot": reopen_boundary,
        }

    def mark_drained(self, *, applied: int, suppressed: int) -> None:
        base = self._store.state
        try:
            self._store.update(
                unseen_buffered_events_applied=(
                    base.unseen_buffered_events_applied + int(applied)),
                duplicate_events_suppressed=(
                    base.duplicate_events_suppressed + int(suppressed)))
        except RecoveryStoreWriteError:
            pass
        self._buffer.clear()

    # -- observability -----------------------------------------------------

    def snapshot(self) -> Dict[str, Any]:
        merged = {
            "recovery_config": self._config.snapshot(),
            **self._store.snapshot(),
            **self._buffer.snapshot(),
        }
        merged["rpc_transport_configured"] = self._rpc_post_fn is not None
        return merged


# ---------------------------------------------------------------------------
# armed startup validation
# ---------------------------------------------------------------------------

def evaluate_armed_gap_recovery(
    *,
    require_production_grpc: bool,
    mode_argument: Optional[str],
    config: Optional[RpcGapRecoveryConfig],
    env: Optional[Mapping[str, str]] = None,
) -> Dict[str, Any]:
    """Fail-closed startup verdict for the recovery configuration.

    Under ``--require-production-grpc`` the recovery mode must be explicit --
    a production launcher may not silently inherit an optimistic default --
    and an armed ``rpc_backfill`` selection additionally requires a valid
    commitment, valid bounds and a provisioned endpoint.  Without the armed
    flag the generic development CLI keeps permissive defaults, but an
    explicitly selected invalid configuration still refuses.
    """

    refusals: List[str] = []
    checks: Dict[str, Any] = {
        "require_production_grpc": bool(require_production_grpc),
        "grpc_gap_recovery_mode": mode_argument,
    }
    if mode_argument is not None and mode_argument not in GAP_RECOVERY_MODES:
        refusals.append(CONFIG_REFUSAL_MODE_INVALID)
    if require_production_grpc and mode_argument is None:
        refusals.append(CONFIG_REFUSAL_MODE_ABSENT)
    if config is not None:
        config_refusals = validate_rpc_gap_recovery_config(config)
        refusals.extend(config_refusals)
        checks["config"] = config.snapshot()
        if config.mode == GAP_RECOVERY_MODE_RPC_BACKFILL \
                and not config_refusals:
            projection = project_rpc_recovery_env_safe(env)
            checks["rpc_recovery_env"] = projection
            if require_production_grpc \
                    and projection["rpc_recovery_endpoint"] != "PRESENT":
                refusals.append(CONFIG_REFUSAL_ENDPOINT_ABSENT)
    seen = set()
    deduped = [token for token in refusals
               if not (token in seen or seen.add(token))]
    return {"allowed": not deduped, "refusals": deduped, "checks": checks}


__all__ = (
    "RpcGapBackfillCoordinator",
    "evaluate_armed_gap_recovery",
    "StateDirRuntimeLock",
    "RUNTIME_LOCK_BASENAME",
    "GAP_RECOVERY_MODE_PROVIDER_REPLAY_ONLY",
    "GAP_RECOVERY_MODE_RPC_BACKFILL",
    "GAP_RECOVERY_MODE_LIVE_EPOCH",
    "GAP_RECOVERY_MODES",
    "RECOVERY_STATES",
    "RECOVERY_STATE_IDLE",
    "RECOVERY_STATE_REPLAY_REFUSED",
    "RECOVERY_STATE_RPC_BACKFILL_PLANNED",
    "RECOVERY_STATE_RPC_BACKFILL_RUNNING",
    "RECOVERY_STATE_LIVE_STREAM_QUARANTINED",
    "RECOVERY_STATE_OVERLAP_PENDING",
    "RECOVERY_STATE_RECOVERY_PROVEN",
    "RECOVERY_STATE_RECOVERY_TERMINAL",
    "RESUMABLE_RECOVERY_STATES",
    "RECOVERY_TERMINAL_REASONS",
    "TERMINAL_RPC_BACKFILL_GAP_TOO_LARGE",
    "TERMINAL_RPC_BACKFILL_BLOCK_LIMIT_EXCEEDED",
    "TERMINAL_RPC_BACKFILL_TRANSACTION_LIMIT_EXCEEDED",
    "TERMINAL_RPC_BACKFILL_REQUEST_LIMIT_EXCEEDED",
    "TERMINAL_RPC_BACKFILL_TIMEOUT",
    "TERMINAL_RPC_BACKFILL_RATE_LIMITED",
    "TERMINAL_RPC_BACKFILL_BLOCK_UNAVAILABLE",
    "TERMINAL_RPC_BACKFILL_COMMITMENT_TIMEOUT",
    "TERMINAL_RPC_BACKFILL_FORK_INCONSISTENT",
    "TERMINAL_RECOVERY_OVERLAP_NOT_PROVEN",
    "TERMINAL_RECOVERY_BUFFER_CAPACITY_EXCEEDED",
    "TERMINAL_RECOVERY_BUFFER_CAPACITY_EXCEEDED_TOKEN",
    "TERMINAL_RPC_BACKFILL_ENTRY_INELIGIBLE",
    "TERMINAL_RPC_BACKFILL_MALFORMED_RESPONSE",
    "TERMINAL_RPC_BACKFILL_CONSECUTIVE_FAILURES",
    "TERMINAL_RPC_BACKFILL_TRANSPORT_ABSENT",
    "TERMINAL_RECOVERY_STATE_QUARANTINED",
    "TERMINAL_RECOVERY_SOURCE_OBSERVER_UNSUPPORTED",
    "TERMINAL_RECOVERY_CURSOR_RESOLUTION_REFUSED",
    "ENTRY_REPLAY_RETENTION_PRECHECK",
    "ENTRY_REPLAY_REFUSED_OUT_OF_RANGE",
    "ENTRY_INELIGIBLE",
    "ENTRY_CLASSIFICATIONS",
    "BACKFILL_ELIGIBLE_CLASSIFICATIONS",
    "AUTHORITATIVE_COMMITMENTS",
    "LIVE_STREAM_COMMITMENT",
    "OVERLAP_NOT_PROVEN",
    "OVERLAP_PROVEN",
    "RPC_RECOVERY_PROVIDER_LABEL",
    "BUFFER_EVENT_TRANSACTION_OBSERVED",
    "BUFFER_EVENT_MIGRATION_ADMITTED",
    "BUFFER_EVENT_KINDS",
    "ENV_NAME_RPC_RECOVERY_ENDPOINT",
    "ENV_NAME_RPC_RECOVERY_TIMEOUT_SECONDS",
    "RPC_RECOVERY_READ_ENV_NAMES",
    "DEFAULT_RPC_RECOVERY_TIMEOUT_SECONDS",
    "CONFIG_REFUSAL_MODE_INVALID",
    "CONFIG_REFUSAL_MODE_ABSENT",
    "CONFIG_REFUSAL_COMMITMENT_INVALID",
    "CONFIG_REFUSAL_ENDPOINT_ABSENT",
    "CONFIG_REFUSAL_BOUND_INVALID_PREFIX",
    "RpcGapRecoveryConfig",
    "validate_rpc_gap_recovery_config",
    "project_rpc_recovery_env_safe",
    "build_rpc_transport_from_env",
    "classify_replay_refusal",
    "CHECKPOINT_KIND_RPC_GAP_RECOVERY",
    "RPC_GAP_RECOVERY_SCHEMA_V1",
    "RECOVERY_RECORD_KIND",
    "RECOVERY_PRIMARY_BASENAME",
    "RecoveryStoreWriteError",
    "QuarantineBufferCapacityExceeded",
    "RpcGapRecoveryState",
    "validate_recovery_record",
    "recovery_record_identity",
    "classify_recovery_checkpoint_file",
    "RpcGapRecoveryStore",
    "CHECKPOINT_KIND_RECOVERY_QUARANTINE",
    "RECOVERY_QUARANTINE_SCHEMA_V1",
    "QUARANTINE_RECORD_KIND",
    "QUARANTINE_PRIMARY_BASENAME",
    "validate_quarantine_record",
    "quarantine_record_identity",
    "classify_quarantine_checkpoint_file",
    "QuarantinedLiveBuffer",
    "RpcBackfillBoundExceeded",
    "SolanaRpcBackfillAdapter",
    "build_subscribe_update_from_rpc_transaction",
    "rpc_transaction_mentions_program",
)

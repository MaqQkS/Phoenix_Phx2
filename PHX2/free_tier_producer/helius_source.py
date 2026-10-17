"""Helius Enhanced WebSocket migration source for shadow operation.

The adapter is deliberately transport-only:

* it builds authenticated URLs in memory and never exposes them through repr;
* it uses the approved tight ``transactionSubscribe`` filter;
* it adapts Helius JSON into the existing PHX2 migration-admission decoder;
* it yields the same frozen Stage 28.10 normalized event used by Chainstack;
* it owns no delivery transport, delivery reservation, or paid-ledger writer.

Helius WebSocket delivery is live-only.  Reconnect continuity is recorded by
``SourceContinuityTracker`` and a separate bounded HTTP component proves any
open slot range.  This module never asks Helius WSS to replay from a slot.

RECONNECT (2026-07-31 continuous-discovery remediation).  The source used to
stop permanently after five consecutive transport failures, so any provider
outage longer than five attempts ended discovery for the rest of the run.  It
now reconnects INDEFINITELY under
:class:`~PHX2.free_tier_producer.reconnect_policy.PersistentReconnectPolicy`:
bounded exponential backoff (1, 2, 5, 10, 30, capped near 60 seconds) with
bounded jitter, reset after a sustained healthy connection, interrupted
promptly by operator shutdown.  Only an authentication rejection or a proven
non-recoverable integrity failure stops the loop; an ordinary outage never
does, and never reaches the watchdog circuit breaker.
"""

from __future__ import annotations

import asyncio
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import threading
import time
from typing import Any, AsyncIterator, Callable, Dict, Mapping, Optional, Sequence

from PHX2.free_tier_producer.migration_admission import (
    MIGRATION_VERSION_V1,
    MIGRATION_VERSION_V2,
    POOL_CREATION_MIGRATION_CPI,
    PUMPFUN_PROGRAM_ID,
    evaluate_migration_admission,
)
from PHX2.free_tier_producer.migration_journal import (
    SOURCE_LIVE_STREAM,
    build_journal_record,
)
from PHX2.free_tier_producer.reconnect_policy import (
    ACTION_STOP_AUTHENTICATION,
    ACTION_STOP_INTEGRITY,
    ACTION_STOP_OPERATOR_SHUTDOWN,
    FAILURE_AUTHENTICATION,
    FAILURE_TRANSIENT,
    HEALTHY_CONNECTION_SECONDS as _HEALTHY_CONNECTION_SECONDS,
    PersistentReconnectPolicy,
    RECONNECT_JITTER_FRACTION as _RECONNECT_JITTER_FRACTION,
    RECONNECT_LADDER_SECONDS as _RECONNECT_LADDER_SECONDS,
    RECONNECT_MAX_DELAY_SECONDS as _RECONNECT_MAX_DELAY_SECONDS,
)
from PHX2.free_tier_producer.source_continuity import (
    REASON_AUTH_FAILURE,
    REASON_OPERATOR_SHUTDOWN,
    REASON_PROVIDER_DISCONNECT,
    REASON_PROVIDER_ERROR,
    TERMINAL_GAP_STATES,
    SourceContinuityTracker,
    normalize_ranges,
)
from PHX2.shadow_probes.helius_developer import (
    ProbeProtocolError,
    build_authenticated_url,
    build_transaction_subscribe_request,
    build_transaction_unsubscribe_request,
    estimated_stream_credits,
    helius_envelope_to_decoder_update,
    uncompressed_json_bytes,
    validate_numeric_subscription_response,
    validate_unsubscribe_response,
)
from PHX2.stage28.chainstack_yellowstone_models import (
    Stage28_10NormalizedEvent,
    build_normalized_event,
)
from PHX2.stage29.pumpswap_program_constants import PUMPSWAP_PROGRAM_ID
from PHX2.config.secret_env import load_secret_environment
from PHX2.free_tier_producer.helius_byte_budget import (
    HeliusByteBudget,
    SOURCE_WSS,
)


HELIUS_SOURCE_IDENTITY = "HELIUS_ENHANCED_WSS"
HELIUS_HTTP_SOURCE_IDENTITY = "HELIUS_ENHANCED_HTTP"

MIGRATION_SOURCE_ENV = "PHX2_MIGRATION_SOURCE_MODE"
CHAINSTACK_PRIMARY = "CHAINSTACK_PRIMARY"
HELIUS_SHADOW = "HELIUS_SHADOW"
HELIUS_PRIMARY_CHAINSTACK_SHADOW = "HELIUS_PRIMARY_CHAINSTACK_SHADOW"
HELIUS_PRIMARY = "HELIUS_PRIMARY"
MIGRATION_SOURCE_MODES = (
    CHAINSTACK_PRIMARY,
    HELIUS_PRIMARY_CHAINSTACK_SHADOW,
    HELIUS_PRIMARY,
)

HELIUS_ENV_NAMES = (
    "HELIUS_API_KEY",
    "HELIUS_RPC_URL",
    "HELIUS_WS_URL",
)

STREAM_STOPPED = "STOPPED"
STREAM_CONNECTING = "CONNECTING"
STREAM_CONNECTED = "CONNECTED"
STREAM_RECONNECTING = "RECONNECTING"
STREAM_AUTH_FAILED = "AUTH_FAILED"
STREAM_FAILED = "FAILED"

ERROR_AUTH = "AUTH_FAILURE"
ERROR_RATE_LIMITED = "RATE_LIMITED"
ERROR_PROTOCOL = "PROTOCOL_INVALID"
ERROR_TRANSPORT = "TRANSPORT_ERROR"
#: Retained for readers of historical artifacts.  Persistent reconnect never
#: produces it: there is no attempt ceiling for a transient provider failure.
ERROR_RECONNECTS_EXHAUSTED = "RECONNECTS_EXHAUSTED"
ERROR_INTEGRITY = "SOURCE_INTEGRITY_FAILURE"

DEFAULT_KEEPALIVE_INTERVAL_SECONDS = 30.0
DEFAULT_KEEPALIVE_TIMEOUT_SECONDS = 20.0
DEFAULT_MAX_MESSAGE_BYTES = 32 * 1024 * 1024
#: The legacy five-attempt ceiling.  It is no longer the default: production
#: reconnects without a ceiling (``max_reconnects=None``).  Callers that WANT a
#: bounded attempt budget -- a one-shot connectivity probe, for instance --
#: still pass an explicit integer and get exactly that many reconnects.
DEFAULT_MAX_RECONNECTS = 5
DEFAULT_RECONNECT_BACKOFF_SECONDS = _RECONNECT_LADDER_SECONDS
DEFAULT_RECONNECT_MAX_DELAY_SECONDS = _RECONNECT_MAX_DELAY_SECONDS
DEFAULT_RECONNECT_JITTER_FRACTION = _RECONNECT_JITTER_FRACTION
DEFAULT_HEALTHY_CONNECTION_SECONDS = _HEALTHY_CONNECTION_SECONDS
DEFAULT_DEDUPE_ENTRIES = 8192
DEFAULT_PENDING_NOTIFICATIONS = 128


class HeliusSourceConfigurationError(ValueError):
    """Canonical Helius source configuration is missing or unsafe."""


class HeliusSourceProtocolError(RuntimeError):
    """A Helius WSS frame violates the approved source contract."""


class HeliusPrimaryNotEnabled(RuntimeError):
    """The future primary mode was selected before an audited cutover."""


class _GracefulSourceStop(Exception):
    """Internal control flow for a cooperative unsubscribe."""


class _SecretValue:
    __slots__ = ("_value",)

    def __init__(self, value: str) -> None:
        self._value = str(value)

    def reveal(self) -> str:
        return self._value

    def __repr__(self) -> str:
        return "<REDACTED>"

    def __str__(self) -> str:
        return "<REDACTED>"


@dataclass(frozen=True, repr=False)
class HeliusSourceConfig:
    """Secret-bearing canonical source configuration with a safe repr."""

    api_key: _SecretValue
    rpc_base_url: _SecretValue
    ws_base_url: _SecretValue
    keepalive_interval_seconds: float = DEFAULT_KEEPALIVE_INTERVAL_SECONDS
    keepalive_timeout_seconds: float = DEFAULT_KEEPALIVE_TIMEOUT_SECONDS
    max_message_bytes: int = DEFAULT_MAX_MESSAGE_BYTES
    #: Reconnect attempt ceiling.  ``None`` -- the production default -- means
    #: NO ceiling: ordinary transient provider failures are retried forever.
    #: An explicit integer is honoured exactly, so a bounded caller (a one-shot
    #: connectivity probe) still gets a bounded loop.
    max_reconnects: Optional[int] = None
    reconnect_backoff_seconds: tuple[float, ...] = (
        DEFAULT_RECONNECT_BACKOFF_SECONDS
    )
    dedupe_entries: int = DEFAULT_DEDUPE_ENTRIES
    max_total_raw_bytes: Optional[int] = None
    reconnect_max_delay_seconds: float = DEFAULT_RECONNECT_MAX_DELAY_SECONDS
    reconnect_jitter_fraction: float = DEFAULT_RECONNECT_JITTER_FRACTION
    healthy_connection_seconds: float = DEFAULT_HEALTHY_CONNECTION_SECONDS

    @property
    def persistent_reconnect(self) -> bool:
        """True when no attempt ceiling applies (the production default)."""

        return self.max_reconnects is None

    def __post_init__(self) -> None:
        if not 1 <= float(self.keepalive_interval_seconds) <= 300:
            raise HeliusSourceConfigurationError(
                "Helius keepalive interval is out of range"
            )
        if not 1 <= float(self.keepalive_timeout_seconds) <= 120:
            raise HeliusSourceConfigurationError(
                "Helius keepalive timeout is out of range"
            )
        if not 1024 <= int(self.max_message_bytes) <= 64 * 1024 * 1024:
            raise HeliusSourceConfigurationError(
                "Helius message ceiling is out of range"
            )
        if self.max_reconnects is not None and (
            isinstance(self.max_reconnects, bool)
            or not isinstance(self.max_reconnects, int)
            or not 0 <= int(self.max_reconnects) <= 20
        ):
            raise HeliusSourceConfigurationError(
                "Helius reconnect ceiling is out of range"
            )
        backoff = tuple(float(value) for value in self.reconnect_backoff_seconds)
        if (
            not backoff
            or any(value < 0 or value > 300 for value in backoff)
            or any(right < left for left, right in zip(backoff, backoff[1:]))
        ):
            raise HeliusSourceConfigurationError(
                "Helius reconnect backoff is invalid"
            )
        if not 128 <= int(self.dedupe_entries) <= 100_000:
            raise HeliusSourceConfigurationError(
                "Helius dedupe ceiling is out of range"
            )
        if self.max_total_raw_bytes is not None and (
            isinstance(self.max_total_raw_bytes, bool)
            or not isinstance(self.max_total_raw_bytes, int)
            or not 1 <= self.max_total_raw_bytes <= 10_000_000_000
        ):
            raise HeliusSourceConfigurationError(
                "Helius total byte ceiling is out of range"
            )
        if not 0 <= float(self.reconnect_max_delay_seconds) <= 300:
            raise HeliusSourceConfigurationError(
                "Helius reconnect delay ceiling is out of range"
            )
        if not 0 <= float(self.reconnect_jitter_fraction) <= 1:
            raise HeliusSourceConfigurationError(
                "Helius reconnect jitter fraction is out of range"
            )
        if float(self.healthy_connection_seconds) < 0:
            raise HeliusSourceConfigurationError(
                "Helius healthy-connection threshold is out of range"
            )

    def __repr__(self) -> str:
        return (
            "HeliusSourceConfig(api_key=<REDACTED>, "
            "rpc_base_url=<REDACTED>, ws_base_url=<REDACTED>, "
            f"keepalive_interval_seconds={self.keepalive_interval_seconds!r}, "
            f"keepalive_timeout_seconds={self.keepalive_timeout_seconds!r}, "
            f"max_message_bytes={self.max_message_bytes!r}, "
            f"max_reconnects={self.max_reconnects!r}, "
            f"reconnect_backoff_seconds={self.reconnect_backoff_seconds!r}, "
            f"dedupe_entries={self.dedupe_entries!r}, "
            f"max_total_raw_bytes={self.max_total_raw_bytes!r}, "
            "reconnect_max_delay_seconds="
            f"{self.reconnect_max_delay_seconds!r}, "
            f"reconnect_jitter_fraction={self.reconnect_jitter_fraction!r}, "
            f"healthy_connection_seconds={self.healthy_connection_seconds!r})"
        )

    def sanitized_presence(self) -> Dict[str, str]:
        return {name: "PRESENT" for name in HELIUS_ENV_NAMES}


def load_helius_source_config(
    *,
    env_path: Optional[Path] = None,
    environ: Optional[Mapping[str, str]] = None,
    **overrides: Any,
) -> HeliusSourceConfig:
    """Load only canonical Helius values; secret text never enters errors."""

    values = load_secret_environment(
        env_path=env_path,
        names=HELIUS_ENV_NAMES,
        environ=environ,
    )
    if any(not values.get(name, "").strip() for name in HELIUS_ENV_NAMES):
        raise HeliusSourceConfigurationError(
            "required Helius source setting is missing"
        )
    key = values["HELIUS_API_KEY"].strip()
    rpc = values["HELIUS_RPC_URL"].strip()
    wss = values["HELIUS_WS_URL"].strip()
    try:
        build_authenticated_url(rpc, key, expected_scheme="https")
        build_authenticated_url(wss, key, expected_scheme="wss")
    except Exception as exc:
        raise HeliusSourceConfigurationError(
            "Helius source URL contract is unsafe"
        ) from exc
    return HeliusSourceConfig(
        api_key=_SecretValue(key),
        rpc_base_url=_SecretValue(rpc),
        ws_base_url=_SecretValue(wss),
        **overrides,
    )


@dataclass(frozen=True)
class SourceSelection:
    """Migration-source ownership policy, separate from provider billing mode."""

    mode: str
    chainstack_production_authority: bool
    chainstack_shadow_enabled: bool
    helius_shadow_enabled: bool
    helius_production_authority: bool
    authoritative_source: str
    candidate_pipeline_owners: int
    telegram_owners: int
    delivery_owner_count: int
    paid_ledger_writers: int
    helius_send_capable: bool
    helius_delivery_reservation_capable: bool
    helius_ledger_write_capable: bool
    launcher_cutover_enabled: bool

    def require_launcher_ready(self) -> None:
        if self.helius_production_authority and not self.launcher_cutover_enabled:
            raise HeliusPrimaryNotEnabled(
                "Helius primary mode is not launcher-authorized"
            )
        if (
            self.candidate_pipeline_owners != 1
            or self.telegram_owners != 1
            or self.delivery_owner_count != 1
            or self.paid_ledger_writers != 1
        ):
            raise HeliusPrimaryNotEnabled(
                "production source ownership is not singular"
            )


@dataclass(frozen=True)
class ProductionSourceRuntimePlan:
    """Closed construction plan decided before any provider credential is read."""

    mode: str
    primary_source: str
    recovery_authority: str
    shadow_source: str
    construct_helius_source: bool
    construct_helius_http_recovery: bool
    construct_chainstack_source: bool
    construct_chainstack_grpc_channel: bool
    construct_chainstack_comparator: bool
    construct_parity_monitor: bool
    construct_chainstack_artifact_writer: bool
    resolve_chainstack_credentials: bool
    use_chainstack_source_health: bool
    source_owner_count: int
    candidate_pipeline_owners: int
    telegram_owners: int
    delivery_owner_count: int
    paid_ledger_writers: int

    def status_projection(self) -> Dict[str, object]:
        """Redaction-safe source facts for manifests, heartbeat and status."""

        chainstack_runtime = bool(
            self.construct_chainstack_source
            or self.construct_chainstack_grpc_channel
            or self.construct_chainstack_comparator
        )
        return {
            "primary_migration_source": self.primary_source,
            "primary_recovery": self.recovery_authority,
            "recovery_authority": self.recovery_authority,
            "shadow_source": self.shadow_source,
            "chainstack_configured_for_runtime": chainstack_runtime,
            # Connection is a live observation, never inferred from config.
            "chainstack_connected": False,
            "chainstack_comparator": self.construct_chainstack_comparator,
            "chainstack_source_health_enabled": self.use_chainstack_source_health,
            "candidate_authority": self.primary_source,
            "source_owner_count": self.source_owner_count,
            "candidate_pipeline_owners": self.candidate_pipeline_owners,
            "telegram_owners": self.telegram_owners,
            "delivery_owner_count": self.delivery_owner_count,
            "paid_ledger_writers": self.paid_ledger_writers,
        }


def build_production_source_runtime_plan(
    selection: SourceSelection,
    *,
    http_recovery_enabled: bool,
) -> ProductionSourceRuntimePlan:
    """Project one source mode into an explicit, testable construction plan."""

    helius_primary = bool(selection.helius_production_authority)
    canary = bool(selection.chainstack_shadow_enabled)
    chainstack_primary = bool(selection.chainstack_production_authority)
    return ProductionSourceRuntimePlan(
        mode=selection.mode,
        primary_source=selection.authoritative_source,
        recovery_authority=(
            "HELIUS_HTTP"
            if helius_primary and http_recovery_enabled
            else "CHAINSTACK"
            if chainstack_primary
            else "DISABLED"
        ),
        shadow_source="CHAINSTACK" if canary else "DISABLED",
        construct_helius_source=helius_primary,
        construct_helius_http_recovery=(
            helius_primary and bool(http_recovery_enabled)
        ),
        construct_chainstack_source=chainstack_primary or canary,
        construct_chainstack_grpc_channel=chainstack_primary or canary,
        construct_chainstack_comparator=canary,
        construct_parity_monitor=canary,
        construct_chainstack_artifact_writer=canary,
        resolve_chainstack_credentials=chainstack_primary or canary,
        use_chainstack_source_health=chainstack_primary,
        source_owner_count=2 if canary else 1,
        candidate_pipeline_owners=selection.candidate_pipeline_owners,
        telegram_owners=selection.telegram_owners,
        delivery_owner_count=selection.delivery_owner_count,
        paid_ledger_writers=selection.paid_ledger_writers,
    )


def load_source_selection(
    environ: Optional[Mapping[str, str]] = None,
    *,
    explicit_mode: Optional[str] = None,
) -> SourceSelection:
    source = os.environ if environ is None else environ
    environment_mode = source.get(MIGRATION_SOURCE_ENV)
    if environment_mode is None or not str(environment_mode).strip():
        raise HeliusSourceConfigurationError(
            "migration source mode is required; no fallback is permitted"
        )
    mode = str(environment_mode)
    mode = mode.strip().upper().replace("-", "_")
    if mode not in MIGRATION_SOURCE_MODES:
        raise HeliusSourceConfigurationError(
            "migration source mode is not in the closed set"
        )
    if explicit_mode is not None:
        normalized_explicit = (
            str(explicit_mode).strip().upper().replace("-", "_")
        )
        if normalized_explicit not in MIGRATION_SOURCE_MODES:
            raise HeliusSourceConfigurationError(
                "explicit migration source mode is not in the closed set"
            )
        if normalized_explicit != mode:
            raise HeliusSourceConfigurationError(
                "explicit and environment migration source modes differ"
            )
    helius_primary = mode in (
        HELIUS_PRIMARY_CHAINSTACK_SHADOW,
        HELIUS_PRIMARY,
    )
    return SourceSelection(
        mode=mode,
        chainstack_production_authority=mode in (
            CHAINSTACK_PRIMARY,
            HELIUS_SHADOW,
        ),
        chainstack_shadow_enabled=(
            mode == HELIUS_PRIMARY_CHAINSTACK_SHADOW
        ),
        helius_shadow_enabled=mode == HELIUS_SHADOW,
        helius_production_authority=helius_primary,
        authoritative_source=("HELIUS" if helius_primary else "CHAINSTACK"),
        candidate_pipeline_owners=1,
        telegram_owners=1,
        delivery_owner_count=1,
        paid_ledger_writers=1,
        helius_send_capable=False,
        helius_delivery_reservation_capable=False,
        helius_ledger_write_capable=False,
        launcher_cutover_enabled=helius_primary,
    )


def approved_tight_subscription_request(request_id: int) -> Dict[str, object]:
    """The one approved Helius subscription; no broadening seam is exposed."""

    request = build_transaction_subscribe_request(
        request_id=request_id,
        filter_label="TIGHT",
        pump_program_id=PUMPFUN_PROGRAM_ID,
        pumpswap_program_id=PUMPSWAP_PROGRAM_ID,
    )
    return request


def tight_filter_is_locked(request: Mapping[str, object]) -> bool:
    """True only for the exact failed/vote/accountRequired production filter."""

    expected = approved_tight_subscription_request(1)
    actual = dict(request)
    actual["id"] = 1
    return actual == expected


@dataclass(frozen=True)
class ProductionSourceContractVerdict:
    allowed: bool
    refusals: tuple[str, ...]


def validate_production_source_contract(
    *,
    selection: SourceSelection,
    helius_configured: bool,
    http_recovery_enabled: bool,
    subscription_request: Optional[Mapping[str, object]] = None,
    send_authority_count: int = 1,
    chainstack_candidate_authority: bool = False,
    chainstack_comparator_enabled: bool = False,
) -> ProductionSourceContractVerdict:
    """Validate source authority before any provider object is constructed."""

    refusals: list[str] = []
    if selection.helius_production_authority:
        if not helius_configured:
            refusals.append("HELIUS_CONFIGURATION_REQUIRED")
        if not http_recovery_enabled:
            refusals.append("HELIUS_HTTP_RECOVERY_REQUIRED")
        request = (
            approved_tight_subscription_request(1)
            if subscription_request is None
            else subscription_request
        )
        if not tight_filter_is_locked(request):
            refusals.append("HELIUS_TIGHT_FILTER_REQUIRED")
        if int(send_authority_count) != 1:
            refusals.append("SINGLE_SEND_AUTHORITY_REQUIRED")
        if selection.chainstack_shadow_enabled and chainstack_candidate_authority:
            refusals.append("CHAINSTACK_SHADOW_CANDIDATE_AUTHORITY_FORBIDDEN")
        if (
            selection.mode == HELIUS_PRIMARY
            and chainstack_comparator_enabled
        ):
            refusals.append("HELIUS_ONLY_CHAINSTACK_RUNTIME_FORBIDDEN")
        plan = build_production_source_runtime_plan(
            selection,
            http_recovery_enabled=http_recovery_enabled,
        )
        if selection.mode == HELIUS_PRIMARY and any((
            plan.construct_chainstack_source,
            plan.construct_chainstack_grpc_channel,
            plan.construct_chainstack_comparator,
            plan.construct_parity_monitor,
            plan.construct_chainstack_artifact_writer,
            plan.resolve_chainstack_credentials,
            plan.use_chainstack_source_health,
        )):
            refusals.append("HELIUS_ONLY_CHAINSTACK_RUNTIME_FORBIDDEN")
    if (
        selection.candidate_pipeline_owners != 1
        or selection.telegram_owners != 1
        or selection.delivery_owner_count != 1
        or selection.paid_ledger_writers != 1
    ):
        refusals.append("SINGLE_OWNER_CONTRACT_REQUIRED")
    return ProductionSourceContractVerdict(
        allowed=not refusals,
        refusals=tuple(dict.fromkeys(refusals)),
    )


def build_helius_primary_source_factory(
    *,
    config: HeliusSourceConfig,
    continuity: SourceContinuityTracker,
    decoder_observer: Optional[
        Callable[[Mapping[str, object]], None]
    ] = None,
    recovery_observer: Optional[Callable[[object], None]] = None,
    confirmed_slot_observer: Optional[
        Callable[[int, str], bool]
    ] = None,
    proof_store: Any = None,
    census_sink: Optional[Callable[[object], None]] = None,
    byte_budget: Optional[HeliusByteBudget] = None,
    journal: Any = None,
) -> Callable[..., "HeliusEnhancedWssSource"]:
    """Build the one authoritative Helius owner with bounded HTTP recovery."""

    from PHX2.free_tier_producer.helius_gap_recovery import (
        HeliusRecoveryConfig,
        HeliusSlotGapRecoverer,
    )

    def _factory(
        *,
        from_slot: Any = None,
        cursor: Any = None,
        downstream_durable_fn: Any = None,
        stream_generation: int = 0,
        candidate_commit_fn: Any = None,
    ) -> "HeliusEnhancedWssSource":
        # WSS is intentionally live-only. ``from_slot`` is accepted so the
        # common single-owner seam remains structural; recovery is performed
        # only by the exact bounded HTTP component below.
        # Production uses candidate_commit_fn before WSS/HTTP acknowledgement;
        # a last-yield boolean cannot protect the earlier HTTP coverage commit.
        _ = (from_slot, cursor, downstream_durable_fn, stream_generation)
        recoverer = HeliusSlotGapRecoverer(
            source_config=config,
            recovery_config=HeliusRecoveryConfig(),
            continuity=continuity,
            byte_budget=byte_budget,
            proof_store=proof_store,
            census_sink=census_sink,
            journal=journal,
            candidate_commit_fn=candidate_commit_fn,
        )
        return HeliusEnhancedWssSource(
            config=config,
            continuity=continuity,
            gap_recoverer=recoverer,
            decoder_observer=decoder_observer,
            recovery_observer=recovery_observer,
            confirmed_slot_observer=confirmed_slot_observer,
            proof_store=proof_store,
            census_sink=census_sink,
            byte_budget=byte_budget,
            journal=journal,
            candidate_commit_fn=candidate_commit_fn,
        )

    _factory.authoritative_source = "HELIUS"  # type: ignore[attr-defined]
    return _factory


@dataclass(frozen=True)
class _RecoveryTarget:
    """One exact inclusive range to ask the bounded HTTP recoverer for."""

    gap_id: str
    gap_from_slot: int
    gap_to_slot: int

    @classmethod
    def for_gap(cls, gap: Any) -> "_RecoveryTarget":
        """Narrow ``gap`` to its earliest still-unresolved sub-range."""

        low = int(getattr(gap, "gap_from_slot", 0))
        high = int(getattr(gap, "gap_to_slot", low))
        unresolved = normalize_ranges(
            getattr(gap, "unresolved_ranges", None) or [])
        if unresolved:
            low, high = int(unresolved[0][0]), int(unresolved[0][1])
        return cls(gap_id=str(getattr(gap, "gap_id", "")),
                   gap_from_slot=low, gap_to_slot=high)


@dataclass(frozen=True)
class HeliusTransactionContext:
    """In-memory source envelope retained for the current decoded event."""

    signature: str
    source_slot: int
    received_at_utc: str
    source_identity: str
    raw_uncompressed_bytes: int
    transaction: Mapping[str, object] = field(repr=False, compare=False)
    meta: Mapping[str, object] = field(repr=False, compare=False)
    loaded_addresses: tuple[str, ...] = field(repr=False, compare=False)


@dataclass
class HeliusSourceMetrics:
    connection_attempts: int = 0
    connections_established: int = 0
    reconnects: int = 0
    subscriptions: int = 0
    keepalive_pings: int = 0
    notifications_received: int = 0
    notification_bytes: int = 0
    malformed_notifications: int = 0
    wrong_subscription_notifications: int = 0
    duplicate_signatures: int = 0
    non_migrations_rejected: int = 0
    decoder_rejections: int = 0
    migrations_yielded: int = 0
    migrate: int = 0
    migrate_v2: int = 0
    byte_ceiling_reached: bool = False
    byte_ceiling_notification_discarded: bool = False
    gap_recovery_attempts: int = 0
    gap_recovery_completed: int = 0
    gap_recovery_degraded_total: int = 0
    journal_records_committed: int = 0
    journal_duplicate_records: int = 0
    journal_failures: int = 0
    last_error: Optional[str] = None

    def snapshot(self) -> Dict[str, object]:
        return {
            "connection_attempts": self.connection_attempts,
            "connections_established": self.connections_established,
            "reconnects": self.reconnects,
            "subscriptions": self.subscriptions,
            "keepalive_pings": self.keepalive_pings,
            "notifications_received": self.notifications_received,
            "notification_bytes": self.notification_bytes,
            "estimated_credits": estimated_stream_credits(
                self.notification_bytes
            ),
            "malformed_notifications": self.malformed_notifications,
            "wrong_subscription_notifications": (
                self.wrong_subscription_notifications
            ),
            "duplicate_signatures": self.duplicate_signatures,
            "non_migrations_rejected": self.non_migrations_rejected,
            "decoder_rejections": self.decoder_rejections,
            "migrations_yielded": self.migrations_yielded,
            "migrate": self.migrate,
            "migrate_v2": self.migrate_v2,
            "byte_ceiling_reached": self.byte_ceiling_reached,
            "byte_ceiling_notification_discarded": (
                self.byte_ceiling_notification_discarded
            ),
            "gap_recovery_attempts": self.gap_recovery_attempts,
            "gap_recovery_completed": self.gap_recovery_completed,
            "gap_recovery_degraded_total": self.gap_recovery_degraded_total,
            "journal_records_committed": self.journal_records_committed,
            "journal_duplicate_records": self.journal_duplicate_records,
            "journal_failures": self.journal_failures,
            "last_error": self.last_error,
        }


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _safe_error(exc: BaseException) -> str:
    status = getattr(exc, "status_code", None)
    if status in (401, 403):
        return ERROR_AUTH
    if status == 429:
        return ERROR_RATE_LIMITED
    if isinstance(exc, (HeliusSourceProtocolError, ProbeProtocolError)):
        return ERROR_PROTOCOL
    return ERROR_TRANSPORT


def _extract_transaction_parts(
    envelope: Mapping[str, object],
) -> tuple[str, int, Mapping[str, object], Mapping[str, object], tuple[str, ...]]:
    slot = envelope.get("slot")
    if isinstance(slot, bool) or not isinstance(slot, int) or slot < 0:
        raise HeliusSourceProtocolError("notification slot is invalid")
    container = envelope.get("transaction")
    transaction: object
    meta: object
    if (
        isinstance(container, Mapping)
        and isinstance(container.get("transaction"), Mapping)
        and isinstance(container.get("meta"), Mapping)
    ):
        transaction = container["transaction"]
        meta = container["meta"]
    elif isinstance(container, Mapping) and isinstance(
        envelope.get("meta"), Mapping
    ):
        transaction = container
        meta = envelope["meta"]
    else:
        raise HeliusSourceProtocolError("notification transaction is invalid")
    assert isinstance(transaction, Mapping)
    assert isinstance(meta, Mapping)
    signature = envelope.get("signature")
    signatures = transaction.get("signatures")
    if not isinstance(signature, str) or not signature:
        if (
            isinstance(signatures, list)
            and signatures
            and isinstance(signatures[0], str)
            and signatures[0]
        ):
            signature = signatures[0]
        else:
            raise HeliusSourceProtocolError("notification signature is invalid")
    loaded = meta.get("loadedAddresses")
    loaded_values: list[str] = []
    if isinstance(loaded, Mapping):
        for key in ("writable", "readonly"):
            values = loaded.get(key)
            if isinstance(values, list):
                loaded_values.extend(
                    value for value in values if isinstance(value, str)
                )
    return signature, int(slot), transaction, meta, tuple(loaded_values)


def project_admitted_helius_migration(
    *,
    decision: object,
    signature: str,
    slot: int,
    observed_at_utc: str,
    raw_event_hash: str,
    source_identity: str,
) -> Optional[Stage28_10NormalizedEvent]:
    """Project one already-decoded admission through the shared event contract."""

    if (
        not bool(getattr(decision, "admitted", False))
        or getattr(decision, "migration_version", None) not in (
            MIGRATION_VERSION_V1,
            MIGRATION_VERSION_V2,
        )
        or not getattr(decision, "candidate_mint", None)
        or not getattr(decision, "pool", None)
        or not getattr(decision, "quote_mint", None)
        or getattr(decision, "slot", None) != slot
        or getattr(decision, "transaction_signature", None) != signature
    ):
        return None
    try:
        return build_normalized_event(
            event_id="helius_" + signature,
            provider_event_id=signature,
            provider_name=source_identity,
            mint=decision.candidate_mint,
            event_type="migration",
            observed_at_utc=observed_at_utc,
            raw_event_hash="helius_" + raw_event_hash,
            quote_mint=decision.quote_mint,
            pool_account=decision.pool,
            pool_program_id=PUMPSWAP_PROGRAM_ID,
            base_mint=decision.candidate_mint,
        )
    except Exception:
        return None


class HeliusEnhancedWssSource:
    """Reconnectable Helius source yielding canonical PHX2 migration events."""

    def __init__(
        self,
        *,
        config: HeliusSourceConfig,
        continuity: Optional[SourceContinuityTracker] = None,
        gap_recoverer: Any = None,
        decoder_observer: Optional[
            Callable[[Mapping[str, object]], None]
        ] = None,
        recovery_observer: Optional[Callable[[object], None]] = None,
        confirmed_slot_observer: Optional[
            Callable[[int, str], bool]
        ] = None,
        proof_store: Any = None,
        census_sink: Optional[Callable[[object], None]] = None,
        byte_budget: Optional[HeliusByteBudget] = None,
        journal: Any = None,
        candidate_commit_fn: Optional[Callable[..., bool]] = None,
        connect_fn: Optional[Callable[..., Any]] = None,
        now_fn: Callable[[], str] = _utc_now,
        epoch_fn: Callable[[], float] = time.time,
        sleep_fn: Callable[[float], Any] = asyncio.sleep,
        rand_fn: Optional[Callable[[], float]] = None,
    ) -> None:
        self._config = config
        self._continuity = continuity or SourceContinuityTracker()
        self._gap_recoverer = gap_recoverer
        self._decoder_observer = decoder_observer
        self._recovery_observer = recovery_observer
        self._confirmed_slot_observer = confirmed_slot_observer
        self._proof_store = proof_store
        self._candidate_commit_fn = candidate_commit_fn
        self.candidate_handoff_owned = candidate_commit_fn is not None
        self.admission_commit_failed = False
        self.last_event_migration_proof: object = None
        self._census_sink = census_sink
        self._byte_budget = byte_budget or (
            HeliusByteBudget(config.max_total_raw_bytes)
            if config.max_total_raw_bytes is not None
            else None
        )
        self._journal = journal
        self._connect_fn = connect_fn
        self._now = now_fn
        self._epoch = epoch_fn
        self._sleep = sleep_fn
        self._reconnect_policy = PersistentReconnectPolicy(
            ladder=config.reconnect_backoff_seconds,
            max_delay_seconds=config.reconnect_max_delay_seconds,
            jitter_fraction=config.reconnect_jitter_fraction,
            healthy_connection_seconds=config.healthy_connection_seconds,
            rand_fn=rand_fn,
        )
        self._closed = threading.Event()
        self._active_websocket: Any = None
        self._active_loop: Optional[asyncio.AbstractEventLoop] = None
        self._async_stop: Optional[asyncio.Event] = None
        self._graceful_close_requested = False
        self._request_generation = 0
        self._seen: OrderedDict[str, None] = OrderedDict()
        self._last_subscription_id: Optional[int] = None
        self.metrics = HeliusSourceMetrics()
        self.status = STREAM_STOPPED
        self.last_refusal_reason: Optional[str] = None
        self.first_update_epoch: Optional[float] = None
        self.last_update_epoch: Optional[float] = None
        self.highest_slot_observed: Optional[int] = None
        self.events_scanned = 0
        self.transactions_scanned = 0
        self.last_event_slot: Optional[int] = None
        self.last_event_signature: Optional[str] = None
        self.last_event_received_at_utc: Optional[str] = None
        self.last_event_context: Optional[HeliusTransactionContext] = None
        self.last_event_provider_time_utc: Optional[str] = None
        self.last_event_time_source = "UNKNOWN"
        self.last_event_replayed = False
        self.last_migration_type: Optional[str] = None
        self.last_decoder_observation: Optional[
            Mapping[str, object]
        ] = None
        self.last_recovery_outcome: Any = None
        self.http_estimated_credits_total = 0.0
        self._pending_gap: Any = None
        self._recovered_gap_ids: set[str] = set()
        self.last_reconnect_decision: Any = None

    @property
    def continuity(self) -> SourceContinuityTracker:
        return self._continuity

    @property
    def reconnect_policy(self) -> PersistentReconnectPolicy:
        return self._reconnect_policy

    @property
    def gap_recovery_degraded(self) -> bool:
        """True when a detected gap spent its bounded recovery budget.

        DEGRADED, never fatal: the live source keeps reconnecting and forward
        discovery continues; only the coverage CLAIM for that exact range is
        withdrawn.
        """

        return any(gap.recovery_status in TERMINAL_GAP_STATES
                   for gap in self._continuity.open_gaps())

    def close(self) -> None:
        if not self._graceful_close_requested:
            self._continuity.note_disconnect(
                reason_class=REASON_PROVIDER_DISCONNECT
            )
        self._closed.set()
        # A stop that arrives DURING a reconnect backoff must interrupt it, not
        # wait out the remaining delay.
        loop_for_stop = self._active_loop
        stop = self._async_stop
        if loop_for_stop is not None and stop is not None \
                and loop_for_stop.is_running():
            try:
                loop_for_stop.call_soon_threadsafe(stop.set)
            except Exception:
                pass
        websocket = self._active_websocket
        close = getattr(websocket, "close", None)
        loop = self._active_loop
        if callable(close) and loop is not None and loop.is_running():
            try:
                def request_close() -> None:
                    try:
                        result = close()
                        if asyncio.iscoroutine(result):
                            asyncio.create_task(result)
                    except Exception:
                        pass

                loop.call_soon_threadsafe(request_close)
            except Exception:
                pass

    def request_graceful_close(self) -> None:
        """Stop after a best-effort unsubscribe on the active connection."""

        self._graceful_close_requested = True
        self._closed.set()
        loop = self._active_loop
        stop = self._async_stop
        if loop is not None and stop is not None and loop.is_running():
            try:
                loop.call_soon_threadsafe(stop.set)
            except Exception:
                pass

    async def _recv_or_graceful_stop(
        self, websocket: Any, *, timeout: float,
    ) -> object:
        stop = self._async_stop
        if stop is None:
            return await asyncio.wait_for(websocket.recv(), timeout=timeout)
        receive_task = asyncio.create_task(websocket.recv())
        stop_task = asyncio.create_task(stop.wait())
        try:
            done, _pending = await asyncio.wait(
                (receive_task, stop_task),
                timeout=timeout,
                return_when=asyncio.FIRST_COMPLETED,
            )
            if stop_task in done and stop_task.result():
                receive_task.cancel()
                try:
                    await receive_task
                except (asyncio.CancelledError, Exception):
                    pass
                raise _GracefulSourceStop
            if receive_task in done:
                return receive_task.result()
            receive_task.cancel()
            try:
                await receive_task
            except (asyncio.CancelledError, Exception):
                pass
            raise asyncio.TimeoutError
        finally:
            if not stop_task.done():
                stop_task.cancel()
            try:
                await stop_task
            except (asyncio.CancelledError, Exception):
                pass

    def diagnostic_snapshot(self) -> Dict[str, object]:
        metrics = self.metrics.snapshot()
        wss_credits = float(metrics.get("estimated_credits", 0.0) or 0.0)
        metrics["wss_estimated_credits"] = wss_credits
        metrics["http_estimated_credits"] = (
            self.http_estimated_credits_total
        )
        metrics["estimated_credits"] = (
            wss_credits + self.http_estimated_credits_total
        )
        journal_snapshot: Dict[str, object] = {}
        if self._journal is not None:
            try:
                journal_snapshot = dict(self._journal.snapshot())
            except Exception:
                journal_snapshot = {}
        return {
            "source_identity": HELIUS_SOURCE_IDENTITY,
            "status": self.status,
            "last_refusal_reason": self.last_refusal_reason,
            "last_event_slot": self.last_event_slot,
            "last_event_received_at_utc": self.last_event_received_at_utc,
            "metrics": metrics,
            "continuity": self._continuity.snapshot(),
            "last_recovery_status": getattr(
                self.last_recovery_outcome, "coverage_status", None
            ),
            "reconnect_policy": self._reconnect_policy.snapshot(),
            # Boolean CURRENT state; the per-observation counter lives under
            # ``metrics.gap_recovery_degraded_total`` and the two are named
            # apart on purpose.
            "gap_recovery_degraded": self.gap_recovery_degraded,
            "migration_journal": journal_snapshot,
        }

    def _journal_migration(
        self,
        *,
        decision: object,
        signature: str,
        slot: int,
        source: str,
    ) -> None:
        """Persist one confirmed proof to the durable journal (best effort).

        The journal is EVIDENCE, not send authority: a durability failure is
        counted and disclosed, but it never suppresses the event, because the
        candidate still has to pass every existing admission gate downstream.
        """

        journal = self._journal
        if journal is None:
            return
        proof = getattr(decision, "proof", None)
        record = build_journal_record(
            mint=getattr(decision, "candidate_mint", None),
            signature=signature,
            migration_slot=slot,
            migration_kind=getattr(decision, "migration_version", None),
            migration_proof_digest=getattr(proof, "proof_digest", None),
            block_time_utc=getattr(decision, "block_time_utc", None),
            source=source,
        )
        if record is None:
            self.metrics.journal_failures += 1
            return
        try:
            result = journal.append(record)
        except Exception:
            self.metrics.journal_failures += 1
            return
        outcome = getattr(result, "outcome", None)
        if outcome == "COMMITTED":
            self.metrics.journal_records_committed += 1
            try:
                journal.commit_cursor(slot)
            except Exception:
                self.metrics.journal_failures += 1
        elif outcome == "DUPLICATE_IDEMPOTENT":
            self.metrics.journal_duplicate_records += 1
        else:
            self.metrics.journal_failures += 1

    async def _default_connect(self, url: str, **kwargs: Any) -> Any:
        import websockets

        return websockets.connect(url, **kwargs)

    def _remember_signature(self, signature: str) -> bool:
        if signature in self._seen:
            self._seen.move_to_end(signature)
            self.metrics.duplicate_signatures += 1
            return False
        self._seen[signature] = None
        while len(self._seen) > self._config.dedupe_entries:
            self._seen.popitem(last=False)
        return True

    def _persist_processed_slot(self, slot: int) -> None:
        self._continuity.note_slot(slot, processed=True, durable=True)
        self._continuity.persist()

    def _emit_decoder_observation(
        self,
        *,
        signature: str,
        slot: int,
        received_at_utc: str,
        raw_bytes: int,
        verdict: str,
        migration_type: Optional[str] = None,
        mint: Optional[str] = None,
        pool: Optional[str] = None,
        rejection_reason: Optional[str] = None,
        migration_comparison_scope: bool = False,
    ) -> None:
        record: Mapping[str, object] = {
            "provider_label": HELIUS_SOURCE_IDENTITY,
            "signature_or_hash": signature,
            "slot": slot,
            "receive_timestamp": received_at_utc,
            "migration_type": migration_type,
            "mint": mint,
            "pool": pool,
            "local_decoder_verdict": verdict,
            "rejection_reason": rejection_reason,
            "bytes": raw_bytes,
            "estimated_credits": estimated_stream_credits(raw_bytes),
            "reconnect_count": self.metrics.reconnects,
            "migration_comparison_scope": bool(
                migration_comparison_scope
            ),
        }
        self.last_decoder_observation = record
        if self._decoder_observer is not None:
            try:
                self._decoder_observer(record)
            except Exception:
                pass

    def _decode_notification(
        self, raw: object, *, subscription_id: int,
    ) -> Optional[Stage28_10NormalizedEvent]:
        byte_count = uncompressed_json_bytes(raw)
        if self._byte_budget is not None and not self._byte_budget.consume(
            byte_count, source=SOURCE_WSS
        ):
            self.metrics.byte_ceiling_reached = True
            self.metrics.byte_ceiling_notification_discarded = True
            self._closed.set()
            return None
        self.metrics.notification_bytes += byte_count
        if self._byte_budget is not None:
            self._byte_budget.record_estimated_credits(
                estimated_stream_credits(byte_count),
                source=SOURCE_WSS,
            )
        if self._byte_budget is not None and self._byte_budget.reached:
            self.metrics.byte_ceiling_reached = True
            self._closed.set()
        try:
            message = json.loads(raw)
        except (json.JSONDecodeError, UnicodeDecodeError, TypeError):
            self.metrics.malformed_notifications += 1
            return None
        if (
            not isinstance(message, Mapping)
            or message.get("jsonrpc") != "2.0"
            or message.get("method") != "transactionNotification"
        ):
            self.metrics.malformed_notifications += 1
            return None
        params = message.get("params")
        if not isinstance(params, Mapping):
            self.metrics.malformed_notifications += 1
            return None
        if params.get("subscription") != subscription_id:
            self.metrics.wrong_subscription_notifications += 1
            return None
        envelope = params.get("result")
        if not isinstance(envelope, Mapping):
            self.metrics.malformed_notifications += 1
            return None
        self.metrics.notifications_received += 1
        received_at = self._now()
        try:
            signature, slot, transaction, meta, loaded = (
                _extract_transaction_parts(envelope)
            )
        except HeliusSourceProtocolError:
            self.metrics.malformed_notifications += 1
            return None

        received_epoch = float(self._epoch())
        if self.first_update_epoch is None:
            self.first_update_epoch = received_epoch
        self.last_update_epoch = received_epoch
        self.events_scanned += 1
        self.transactions_scanned += 1
        if self.highest_slot_observed is None or slot > self.highest_slot_observed:
            self.highest_slot_observed = slot

        # Receipt is recorded before local classification.  Rejections still
        # prove that this exact source row was completely processed.
        opened_gap = self._continuity.note_slot(slot)
        if opened_gap is not None:
            self._pending_gap = opened_gap
        self.last_event_slot = slot
        self.last_event_signature = signature
        self.last_event_received_at_utc = received_at
        self.last_event_context = HeliusTransactionContext(
            signature=signature,
            source_slot=slot,
            received_at_utc=received_at,
            source_identity=HELIUS_SOURCE_IDENTITY,
            raw_uncompressed_bytes=byte_count,
            transaction=transaction,
            meta=meta,
            loaded_addresses=loaded,
        )
        if self._confirmed_slot_observer is not None:
            try:
                self._confirmed_slot_observer(slot, received_at)
            except Exception:
                # The durable epoch remains non-healthy on observer failure.
                pass
        if not self._remember_signature(signature):
            self._persist_processed_slot(slot)
            return None
        try:
            update = helius_envelope_to_decoder_update(envelope)
            decision = evaluate_migration_admission(
                update, observed_at_utc=received_at
            )
        except Exception:
            self.metrics.decoder_rejections += 1
            self._emit_decoder_observation(
                signature=signature,
                slot=slot,
                received_at_utc=received_at,
                raw_bytes=byte_count,
                verdict="MALFORMED",
                rejection_reason="LOCAL_DECODE_EXCEPTION",
            )
            self._persist_processed_slot(slot)
            return None
        if decision is None:
            self.metrics.non_migrations_rejected += 1
            self._emit_decoder_observation(
                signature=signature,
                slot=slot,
                received_at_utc=received_at,
                raw_bytes=byte_count,
                verdict="REJECTED",
                rejection_reason="NOT_MIGRATION",
            )
            self._persist_processed_slot(slot)
            return None
        raw_hash = hashlib.sha256(
            raw if isinstance(raw, bytes) else str(raw).encode("utf-8")
        ).hexdigest()
        event = project_admitted_helius_migration(
            decision=decision,
            signature=signature,
            slot=slot,
            observed_at_utc=received_at,
            raw_event_hash=raw_hash,
            source_identity=HELIUS_SOURCE_IDENTITY,
        )
        if event is None:
            self.metrics.decoder_rejections += 1
            self._emit_decoder_observation(
                signature=signature,
                slot=slot,
                received_at_utc=received_at,
                raw_bytes=byte_count,
                verdict="REJECTED",
                migration_type=getattr(
                    decision, "migration_version", None
                ),
                mint=getattr(decision, "candidate_mint", None),
                pool=getattr(decision, "pool", None),
                rejection_reason=(
                    ",".join(getattr(decision, "reason_codes", ()) or ())
                    or "LOCAL_PROJECTION_REJECTED"
                ),
                migration_comparison_scope=(
                    getattr(decision, "classification", None)
                    == POOL_CREATION_MIGRATION_CPI
                ),
            )
            self._persist_processed_slot(slot)
            return None
        proof = getattr(decision, "proof", None)
        if proof is not None and self._proof_store is not None:
            try:
                self._proof_store.seal_and_store(proof)
            except Exception:
                self.metrics.decoder_rejections += 1
                self._seen.pop(signature, None)
                self.admission_commit_failed = True
                self._closed.set()
                raise HeliusSourceProtocolError("MIGRATION_PROOF_COMMIT_FAILED")
        if proof is not None and self._census_sink is not None:
            try:
                if self._census_sink(proof) is False:
                    raise OSError("MIGRATION_CENSUS_COMMIT_FAILED")
            except Exception:
                self.metrics.decoder_rejections += 1
                self._seen.pop(signature, None)
                self.admission_commit_failed = True
                self._closed.set()
                raise HeliusSourceProtocolError("MIGRATION_CENSUS_COMMIT_FAILED")
        self.last_migration_type = str(decision.migration_version)
        self.metrics.migrations_yielded += 1
        if decision.migration_version == MIGRATION_VERSION_V1:
            self.metrics.migrate += 1
        else:
            self.metrics.migrate_v2 += 1
        self._emit_decoder_observation(
            signature=signature,
            slot=slot,
            received_at_utc=received_at,
            raw_bytes=byte_count,
            verdict="ADMITTED",
            migration_type=str(decision.migration_version),
            mint=str(decision.candidate_mint),
            pool=str(decision.pool),
            migration_comparison_scope=True,
        )
        if self._candidate_commit_fn is not None:
            try:
                durable = self._candidate_commit_fn(
                    event, migration_proof=proof, migration_signature=signature,
                    event_slot=slot, replayed=False)
                if durable is not True:
                    raise RuntimeError("ADMISSION_INBOX_COMMIT_FAILED")
            except Exception:
                # Local ownership failure is terminal for this subscription.
                # Reconnecting at the live head could skip the unowned row.
                self._seen.pop(signature, None)
                self.admission_commit_failed = True
                self._closed.set()
                self.last_refusal_reason = "ADMISSION_INBOX_COMMIT_FAILED"
                raise HeliusSourceProtocolError("ADMISSION_INBOX_COMMIT_FAILED")
        self._journal_migration(
            decision=decision,
            signature=signature,
            slot=slot,
            source=SOURCE_LIVE_STREAM,
        )
        self._persist_processed_slot(slot)
        self.last_event_migration_proof = proof
        return event

    def _next_recoverable_gap(self) -> Optional["_RecoveryTarget"]:
        """The next EXACT range owed, newly detected or a bounded retry.

        A freshly detected gap goes first.  Otherwise the canonical continuity
        tracker decides: it names the first open gap whose bounded attempt
        budget is not spent, and ``None`` once every gap is recovered,
        unavailable, failed, or out of attempts.

        The returned bounds are the gap's EARLIEST STILL-UNRESOLVED sub-range,
        never the original span.  For a first attempt those are the same; for a
        retry after a partial recovery they are strictly narrower, so a retry
        never re-requests ground that was already proven.  A complete answer
        credits exactly the sub-range it covered, and the gap closes only once
        every sub-range is proven.
        """

        gap = self._pending_gap
        if gap is not None:
            self._pending_gap = None
            return _RecoveryTarget.for_gap(gap)
        request = self._continuity.replay_request()
        if request is None:
            return None
        gap_id, _from_slot = request
        for candidate in self._continuity.open_gaps():
            if candidate.gap_id == gap_id:
                return _RecoveryTarget.for_gap(candidate)
        return None

    async def _recover_pending_gap(
        self,
    ) -> tuple[Stage28_10NormalizedEvent, ...]:
        recover = getattr(self._gap_recoverer, "recover", None)
        if not callable(recover):
            self._pending_gap = None
            return ()
        gap = self._next_recoverable_gap()
        if gap is None:
            return ()
        self.metrics.gap_recovery_attempts += 1
        try:
            self.last_recovery_outcome = await asyncio.to_thread(
                recover,
                gap_id=gap.gap_id,
                gap_from_slot=gap.gap_from_slot,
                gap_to_slot=gap.gap_to_slot,
            )
            if getattr(self._gap_recoverer, "admission_commit_failed", False):
                self.admission_commit_failed = True
                self._closed.set()
                self.last_refusal_reason = "ADMISSION_INBOX_COMMIT_FAILED"
            if getattr(
                self.last_recovery_outcome, "complete_range_proven", False
            ) and gap.gap_id not in self._recovered_gap_ids:
                self._recovered_gap_ids.add(gap.gap_id)
                self.metrics.gap_recovery_completed += 1
            recovery_metrics = getattr(
                self.last_recovery_outcome,
                "metrics",
                {},
            )
            if isinstance(recovery_metrics, Mapping):
                credit_value = recovery_metrics.get(
                    "estimated_credits",
                    0,
                )
                if isinstance(credit_value, (int, float)) and not isinstance(
                    credit_value,
                    bool,
                ):
                    self.http_estimated_credits_total += float(credit_value)
            if self._recovery_observer is not None:
                try:
                    self._recovery_observer(self.last_recovery_outcome)
                except Exception:
                    pass
            if self._byte_budget is not None and self._byte_budget.reached:
                self.metrics.byte_ceiling_reached = True
                self._closed.set()
            if self.gap_recovery_degraded:
                self.metrics.gap_recovery_degraded_total += 1
            return tuple(
                getattr(self.last_recovery_outcome, "migrations", ()) or ()
            )
        except Exception:
            # The durable continuity gap remains the fail-closed authority.
            self.last_recovery_outcome = None
            return ()

    def _select_recovered_event_context(
        self,
        event: Stage28_10NormalizedEvent,
    ) -> None:
        """Expose exact HTTP side-channel identity while yielding one replay."""

        self.last_event_migration_proof = None
        outcome = self.last_recovery_outcome
        signatures = tuple(
            getattr(outcome, "recovered_signatures", ()) or ()
        )
        slots = tuple(getattr(outcome, "recovered_slots", ()) or ())
        migration_types = tuple(
            getattr(outcome, "migration_types", ()) or ()
        )
        slot_by_signature = dict(zip(signatures, slots))
        type_by_signature = dict(zip(signatures, migration_types))
        signature = str(event.provider_event_id)
        slot = slot_by_signature.get(signature)
        if not isinstance(slot, int):
            return
        observed_at = str(event.observed_at_utc)
        self.last_event_slot = slot
        self.last_event_signature = signature
        self.last_event_received_at_utc = observed_at
        self.last_event_context = HeliusTransactionContext(
            signature=signature,
            source_slot=slot,
            received_at_utc=observed_at,
            source_identity=HELIUS_HTTP_SOURCE_IDENTITY,
            raw_uncompressed_bytes=0,
            transaction={},
            meta={},
            loaded_addresses=(),
        )
        self.last_event_provider_time_utc = None
        self.last_event_time_source = "UNKNOWN"
        self.last_event_replayed = True
        if self._proof_store is not None:
            proof = self._proof_store.get(event.base_mint)
            self.last_event_migration_proof = (
                proof if proof is not None
                and proof.migration_signature == signature
                and proof.migration_slot == slot
                and proof.pool == event.pool_account else {})
        value = type_by_signature.get(signature)
        self.last_migration_type = str(value) if value else None

    async def _receive_subscription(
        self, websocket: Any, *, request_id: int,
    ) -> tuple[int, tuple[object, ...]]:
        pending: list[object] = []
        while True:
            raw = await asyncio.wait_for(
                websocket.recv(), timeout=self._config.keepalive_timeout_seconds
            )
            try:
                parsed = json.loads(raw)
            except (json.JSONDecodeError, UnicodeDecodeError, TypeError):
                if len(pending) >= DEFAULT_PENDING_NOTIFICATIONS:
                    raise HeliusSourceProtocolError(
                        "pre-subscription notification ceiling exceeded"
                    )
                pending.append(raw)
                continue
            if isinstance(parsed, Mapping) and parsed.get("id") == request_id:
                try:
                    subscription_id = validate_numeric_subscription_response(
                        parsed, request_id=request_id
                    )
                except ProbeProtocolError as exc:
                    raise HeliusSourceProtocolError(
                        "subscription response is invalid"
                    ) from exc
                return subscription_id, tuple(pending)
            if len(pending) >= DEFAULT_PENDING_NOTIFICATIONS:
                raise HeliusSourceProtocolError(
                    "pre-subscription notification ceiling exceeded"
                )
            pending.append(raw)

    async def _unsubscribe(
        self, websocket: Any, *, subscription_id: int,
    ) -> None:
        self._request_generation += 1
        request_id = self._request_generation
        await websocket.send(
            json.dumps(
                build_transaction_unsubscribe_request(
                    request_id=request_id,
                    subscription_id=subscription_id,
                ),
                separators=(",", ":"),
            )
        )
        deadline = (
            asyncio.get_running_loop().time()
            + self._config.keepalive_timeout_seconds
        )
        for _ in range(DEFAULT_PENDING_NOTIFICATIONS):
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                return
            try:
                raw = await asyncio.wait_for(
                    websocket.recv(), timeout=remaining
                )
                parsed = json.loads(raw)
            except Exception:
                return
            if not (
                isinstance(parsed, Mapping)
                and parsed.get("id") == request_id
            ):
                # A live stream may deliver transaction notifications between
                # the unsubscribe request and its JSON-RPC acknowledgement.
                # Ignore only those bounded interleavings; never treat one as
                # a successful acknowledgement.
                continue
            validate_unsubscribe_response(
                parsed, request_id=request_id
            )
            return

    async def iter_events_async(
        self, *, max_events: int,
    ) -> AsyncIterator[Stage28_10NormalizedEvent]:
        if (
            isinstance(max_events, bool)
            or not isinstance(max_events, int)
            or max_events <= 0
        ):
            raise ValueError("max_events must be a positive int")
        yielded = 0
        reconnect_number = 0
        self._active_loop = asyncio.get_running_loop()
        self._async_stop = asyncio.Event()
        self.status = STREAM_CONNECTING
        while not self._closed.is_set() and yielded < max_events:
            self.metrics.connection_attempts += 1
            self._reconnect_policy.note_connection_established(
                at_epoch=self._epoch())
            connect = self._connect_fn or self._default_connect
            url = build_authenticated_url(
                self._config.ws_base_url.reveal(),
                self._config.api_key.reveal(),
                expected_scheme="wss",
            )
            try:
                connector = connect(
                    url,
                    open_timeout=15,
                    close_timeout=10,
                    ping_interval=None,
                    max_size=self._config.max_message_bytes,
                )
                if asyncio.iscoroutine(connector):
                    connector = await connector
                url = ""
                async with connector as websocket:
                    self._active_websocket = websocket
                    self.metrics.connections_established += 1
                    self._request_generation += 1
                    request_id = self._request_generation
                    await websocket.send(
                        json.dumps(
                            approved_tight_subscription_request(request_id),
                            separators=(",", ":"),
                        )
                    )
                    subscription_id, pending = await self._receive_subscription(
                        websocket, request_id=request_id
                    )
                    self._last_subscription_id = subscription_id
                    self.metrics.subscriptions += 1
                    self.status = STREAM_CONNECTED
                    for raw in pending:
                        event = self._decode_notification(
                            raw, subscription_id=subscription_id
                        )
                        live_context = (
                            self.last_event_slot,
                            self.last_event_signature,
                            self.last_event_received_at_utc,
                            self.last_event_context,
                            self.last_event_provider_time_utc,
                            self.last_event_time_source,
                            self.last_event_replayed,
                            self.last_migration_type,
                            self.last_event_migration_proof,
                        )
                        recovered = await self._recover_pending_gap()
                        for recovered_event in recovered:
                            self._select_recovered_event_context(
                                recovered_event
                            )
                            yielded += 1
                            yield recovered_event
                            if yielded >= max_events:
                                break
                        if yielded >= max_events:
                            break
                        if event is not None:
                            (
                                self.last_event_slot,
                                self.last_event_signature,
                                self.last_event_received_at_utc,
                                self.last_event_context,
                                self.last_event_provider_time_utc,
                                self.last_event_time_source,
                                self.last_event_replayed,
                                self.last_migration_type,
                                self.last_event_migration_proof,
                            ) = live_context
                            yielded += 1
                            yield event
                            if yielded >= max_events:
                                break
                    while (
                        not self._closed.is_set()
                        and yielded < max_events
                    ):
                        try:
                            raw = await self._recv_or_graceful_stop(
                                websocket,
                                timeout=self._config.keepalive_interval_seconds,
                            )
                        except _GracefulSourceStop:
                            break
                        except asyncio.TimeoutError:
                            pong = await websocket.ping()
                            self.metrics.keepalive_pings += 1
                            await asyncio.wait_for(
                                pong,
                                timeout=self._config.keepalive_timeout_seconds,
                            )
                            continue
                        event = self._decode_notification(
                            raw, subscription_id=subscription_id
                        )
                        live_context = (
                            self.last_event_slot,
                            self.last_event_signature,
                            self.last_event_received_at_utc,
                            self.last_event_context,
                            self.last_event_provider_time_utc,
                            self.last_event_time_source,
                            self.last_event_replayed,
                            self.last_migration_type,
                            self.last_event_migration_proof,
                        )
                        recovered = await self._recover_pending_gap()
                        for recovered_event in recovered:
                            self._select_recovered_event_context(
                                recovered_event
                            )
                            yielded += 1
                            yield recovered_event
                            if yielded >= max_events:
                                break
                        if yielded >= max_events:
                            break
                        if event is not None:
                            (
                                self.last_event_slot,
                                self.last_event_signature,
                                self.last_event_received_at_utc,
                                self.last_event_context,
                                self.last_event_provider_time_utc,
                                self.last_event_time_source,
                                self.last_event_replayed,
                                self.last_migration_type,
                                self.last_event_migration_proof,
                            ) = live_context
                            yielded += 1
                            yield event
                    if (
                        not self._closed.is_set()
                        or self._graceful_close_requested
                    ):
                        await self._unsubscribe(
                            websocket, subscription_id=subscription_id
                        )
                    if yielded >= max_events:
                        # The common owner opens a fresh live subscription
                        # after each bounded yielded batch.  Even though this
                        # socket was unsubscribed cleanly, transactions can
                        # land between the two subscriptions, so the next
                        # confirmed row must prove or recover that exact range.
                        self._continuity.note_disconnect(
                            reason_class=REASON_PROVIDER_DISCONNECT
                        )
                        break
                    if self._closed.is_set():
                        break
                self._continuity.note_disconnect(
                    reason_class=REASON_PROVIDER_DISCONNECT
                )
                self._reconnect_policy.note_connection_closed(
                    at_epoch=self._epoch())
            except Exception as exc:
                url = ""
                error = _safe_error(exc)
                self.metrics.last_error = error
                self.last_refusal_reason = error
                # A connection that stayed up long enough proves the outage is
                # over; a flapping one does not reset the ladder.
                self._reconnect_policy.note_connection_closed(
                    at_epoch=self._epoch())
                if error == ERROR_AUTH:
                    # Authentication is classified SEPARATELY and never
                    # retried.  The status is recorded HERE, before the
                    # shutdown check, so a stop that races the rejection cannot
                    # erase the reason the stream actually died.
                    self.status = STREAM_AUTH_FAILED
                    self._continuity.note_disconnect(
                        reason_class=REASON_AUTH_FAILURE
                    )
                else:
                    self._continuity.note_disconnect(
                        reason_class=REASON_PROVIDER_ERROR
                    )
                decision = self._reconnect_policy.decide(
                    failure_class=(
                        FAILURE_AUTHENTICATION if error == ERROR_AUTH
                        else FAILURE_TRANSIENT),
                    shutdown_requested=bool(
                        self._graceful_close_requested
                        or self._closed.is_set()),
                )
                self.last_reconnect_decision = decision
                if decision.action == ACTION_STOP_AUTHENTICATION:
                    break
                if decision.action == ACTION_STOP_INTEGRITY:
                    self.status = STREAM_FAILED
                    self.metrics.last_error = ERROR_INTEGRITY
                    self.last_refusal_reason = ERROR_INTEGRITY
                    break
                if decision.action == ACTION_STOP_OPERATOR_SHUTDOWN:
                    # Operator shutdown exits promptly; it is not a failure.
                    break
                ceiling = self._config.max_reconnects
                if ceiling is not None and reconnect_number >= int(ceiling):
                    # A caller that asked for a bounded attempt budget gets
                    # exactly that.  Production passes None and never lands
                    # here, so an ordinary outage can no longer end discovery.
                    self.status = STREAM_FAILED
                    self.metrics.last_error = ERROR_RECONNECTS_EXHAUSTED
                    self.last_refusal_reason = ERROR_RECONNECTS_EXHAUSTED
                    break
                self.metrics.reconnects += 1
                self.status = STREAM_RECONNECTING
                reconnect_number += 1
                if await self._backoff(decision.delay_seconds):
                    # Shutdown arrived DURING the backoff.
                    break
            finally:
                url = ""
                self._active_websocket = None
        if self.status not in (STREAM_AUTH_FAILED, STREAM_FAILED):
            self.status = STREAM_STOPPED
        self._async_stop = None
        self._active_loop = None

    async def _backoff(self, delay_seconds: float) -> bool:
        """Wait out one reconnect delay; True when shutdown interrupted it.

        The delay RACES the operator-shutdown event rather than being a bare
        sleep, so a stop during a 60-second backoff exits promptly instead of
        holding the producer open for the rest of the delay.  The injected
        ``sleep_fn`` seam is preserved, so tests stay deterministic.
        """

        delay = max(0.0, float(delay_seconds))
        stop = self._async_stop
        if stop is not None and stop.is_set():
            return True
        if delay <= 0.0:
            return bool(self._closed.is_set())
        pending = self._sleep(delay)
        awaitable = asyncio.iscoroutine(pending) or isinstance(
            pending, asyncio.Future)
        if not awaitable:
            # A synchronous sleep seam has already returned.
            return bool(
                self._closed.is_set()
                or (stop is not None and stop.is_set()))
        if stop is None:
            await pending
            return bool(self._closed.is_set())
        sleep_task = asyncio.ensure_future(pending)
        stop_task = asyncio.ensure_future(stop.wait())
        try:
            done, _pending = await asyncio.wait(
                (sleep_task, stop_task),
                return_when=asyncio.FIRST_COMPLETED,
            )
            if stop_task in done:
                sleep_task.cancel()
                try:
                    await sleep_task
                except (asyncio.CancelledError, Exception):
                    pass
                return True
            return bool(self._closed.is_set())
        finally:
            if not stop_task.done():
                stop_task.cancel()
            try:
                await stop_task
            except (asyncio.CancelledError, Exception):
                pass

    def iter_events(self, *, max_events: int):
        """Synchronous source-contract adapter for existing owner/test seams."""

        loop = asyncio.new_event_loop()
        iterator = self.iter_events_async(max_events=max_events).__aiter__()
        try:
            while True:
                try:
                    event = loop.run_until_complete(iterator.__anext__())
                except StopAsyncIteration:
                    break
                yield event
        finally:
            try:
                loop.run_until_complete(iterator.aclose())
            except Exception:
                pass
            loop.close()


__all__ = (
    "CHAINSTACK_PRIMARY",
    "DEFAULT_HEALTHY_CONNECTION_SECONDS",
    "DEFAULT_RECONNECT_BACKOFF_SECONDS",
    "DEFAULT_RECONNECT_JITTER_FRACTION",
    "DEFAULT_RECONNECT_MAX_DELAY_SECONDS",
    "ERROR_AUTH",
    "ERROR_INTEGRITY",
    "ERROR_PROTOCOL",
    "ERROR_RATE_LIMITED",
    "ERROR_RECONNECTS_EXHAUSTED",
    "ERROR_TRANSPORT",
    "HELIUS_HTTP_SOURCE_IDENTITY",
    "HELIUS_PRIMARY",
    "HELIUS_PRIMARY_CHAINSTACK_SHADOW",
    "HELIUS_SHADOW",
    "HELIUS_SOURCE_IDENTITY",
    "HeliusEnhancedWssSource",
    "HeliusPrimaryNotEnabled",
    "ProductionSourceRuntimePlan",
    "HeliusSourceConfig",
    "HeliusSourceConfigurationError",
    "HeliusSourceMetrics",
    "HeliusSourceProtocolError",
    "HeliusTransactionContext",
    "MIGRATION_SOURCE_ENV",
    "MIGRATION_SOURCE_MODES",
    "ProductionSourceContractVerdict",
    "SourceSelection",
    "approved_tight_subscription_request",
    "build_helius_primary_source_factory",
    "build_production_source_runtime_plan",
    "load_helius_source_config",
    "load_source_selection",
    "project_admitted_helius_migration",
    "tight_filter_is_locked",
    "validate_production_source_contract",
)

"""Closed-set continuous-discovery status and honest coverage disclosure.

WHY THIS EXISTS
---------------
Production discovery has three independent parts — one authoritative live WSS
source, exact bounded gap recovery, and a curated best-effort DEX safety net —
and every previous status surface blurred them.  The worst failure mode was not
a wrong number but a wrong CLAIM: a successful curated DEX request read as
"the last six hours are covered", when the curated surface is a provider's
editorial list of token profiles with no completeness guarantee whatsoever.

This module is the one place that says what each part is doing, in closed-set
tokens, and states the coverage limitations explicitly rather than leaving a
reader to infer completeness from a green status.

THE THREE AXES
--------------
* LIVE SOURCE — is the one owned socket connected, or between attempts.
* GAP RECOVERY — is an exact proven slot range being recovered, and did that
  recovery run out of bounded attempts (DEGRADED, not fatal: the live source
  keeps reconnecting).
* CURATED SAFETY NET — two separate answers.  ``state`` is MECHANISM health
  (is the poller working); ``coverage`` is the COVERAGE CLAIM, and a successful
  poll reports :data:`DEX_SAFETY_NET_PARTIAL_COVERAGE`, never HEALTHY, because
  the curated surface can never prove it saw every migration.

A mint absent from the curated list is reported
:data:`NOT_OBSERVED_BY_CURATED_SOURCE` — a statement about the SOURCE, not
about the mint.  It never means "did not migrate".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Tuple

# -- live source (closed set) -----------------------------------------------
LIVE_CONNECTED = "LIVE_CONNECTED"
LIVE_RECONNECTING = "LIVE_RECONNECTING"
LIVE_STOPPED = "LIVE_STOPPED"
LIVE_AUTHENTICATION_FAILED = "LIVE_AUTHENTICATION_FAILED"

# -- exact gap recovery (closed set) ----------------------------------------
GAP_RECOVERY_IDLE = "GAP_RECOVERY_IDLE"
GAP_RECOVERY_ACTIVE = "GAP_RECOVERY_ACTIVE"
GAP_RECOVERY_DEGRADED = "GAP_RECOVERY_DEGRADED"

# -- curated DEX safety net (closed set) ------------------------------------
DEX_SAFETY_NET_HEALTHY = "DEX_SAFETY_NET_HEALTHY"
DEX_SAFETY_NET_PARTIAL_COVERAGE = "DEX_SAFETY_NET_PARTIAL_COVERAGE"
DEX_SAFETY_NET_DEGRADED = "DEX_SAFETY_NET_DEGRADED"
DEX_SAFETY_NET_DISABLED = "DEX_SAFETY_NET_DISABLED"

#: The eight states the discovery policy requires by name.  Implementations may
#: add narrower states (idle/stopped/auth) but must never drop one of these.
REQUIRED_DISCOVERY_STATES = (
    LIVE_CONNECTED,
    LIVE_RECONNECTING,
    GAP_RECOVERY_ACTIVE,
    GAP_RECOVERY_DEGRADED,
    DEX_SAFETY_NET_HEALTHY,
    DEX_SAFETY_NET_PARTIAL_COVERAGE,
    DEX_SAFETY_NET_DEGRADED,
    DEX_SAFETY_NET_DISABLED,
)

DISCOVERY_STATES = (
    LIVE_CONNECTED,
    LIVE_RECONNECTING,
    LIVE_STOPPED,
    LIVE_AUTHENTICATION_FAILED,
    GAP_RECOVERY_IDLE,
    GAP_RECOVERY_ACTIVE,
    GAP_RECOVERY_DEGRADED,
    DEX_SAFETY_NET_HEALTHY,
    DEX_SAFETY_NET_PARTIAL_COVERAGE,
    DEX_SAFETY_NET_DEGRADED,
    DEX_SAFETY_NET_DISABLED,
)

# -- curated observation verdicts (closed set) ------------------------------
OBSERVED_BY_CURATED_SOURCE = "OBSERVED_BY_CURATED_SOURCE"
NOT_OBSERVED_BY_CURATED_SOURCE = "NOT_OBSERVED_BY_CURATED_SOURCE"
CURATED_SOURCE_UNAVAILABLE = "CURATED_SOURCE_UNAVAILABLE"
CURATED_OBSERVATION_VERDICTS = (
    OBSERVED_BY_CURATED_SOURCE,
    NOT_OBSERVED_BY_CURATED_SOURCE,
    CURATED_SOURCE_UNAVAILABLE,
)

#: The coverage claim the curated safety net is allowed to make.  There is no
#: token for "complete": the curated surface cannot prove completeness, so the
#: vocabulary does not contain a word that would let it say so.
CURATED_COVERAGE_CLAIM = "CURATED_BEST_EFFORT_NOT_EXHAUSTIVE"

#: Coverage limitations that are ALWAYS true of this architecture and are
#: therefore always disclosed alongside any healthy-looking status.
KNOWN_COVERAGE_LIMITATIONS: Tuple[str, ...] = (
    "CURATED_DEX_SURFACE_IS_NOT_A_MIGRATION_INDEX",
    "CURATED_DEX_LIST_HAS_NO_TIME_ORDERED_PAGINATION",
    "CURATED_DEX_ABSENCE_IS_NOT_PROOF_OF_NO_MIGRATION",
    "LIVE_WSS_IS_LIVE_ONLY_AND_NEVER_REPLAYS",
    "COLD_START_HAS_NO_HISTORICAL_RECONSTRUCTION",
    "GAP_RECOVERY_COVERS_ONLY_PROVEN_SLOT_RANGES",
)


def live_source_state(
    *,
    transport_connected: bool,
    reconnecting: bool,
    authentication_failed: bool = False,
    stopped: bool = False,
) -> str:
    """One closed-set live-source state.  Failure classes beat connection."""

    if authentication_failed:
        return LIVE_AUTHENTICATION_FAILED
    if stopped:
        return LIVE_STOPPED
    if transport_connected and not reconnecting:
        return LIVE_CONNECTED
    if reconnecting:
        return LIVE_RECONNECTING
    return LIVE_STOPPED


def gap_recovery_state(
    *,
    open_gap_count: int,
    terminal_gap_count: int = 0,
) -> str:
    """Recovery state for the exact-range recoverer.

    A gap whose bounded attempts are spent is DEGRADED, never fatal: the live
    source keeps reconnecting and forward discovery continues.  DEGRADED is
    reported even when other gaps are still actively recovering, because the
    worst unresolved fact is the one an operator must see.
    """

    if int(terminal_gap_count or 0) > 0:
        return GAP_RECOVERY_DEGRADED
    if int(open_gap_count or 0) > 0:
        return GAP_RECOVERY_ACTIVE
    return GAP_RECOVERY_IDLE


def dex_safety_net_state(
    *,
    enabled: bool,
    consecutive_failed_sweeps: int = 0,
    sweeps_completed_total: int = 0,
    required_sources_failed: bool = False,
) -> str:
    """MECHANISM health of the curated safety net (not a coverage claim)."""

    if not enabled:
        return DEX_SAFETY_NET_DISABLED
    if int(consecutive_failed_sweeps or 0) > 0:
        return DEX_SAFETY_NET_DEGRADED
    if required_sources_failed:
        return DEX_SAFETY_NET_DEGRADED
    if int(sweeps_completed_total or 0) <= 0:
        return DEX_SAFETY_NET_DEGRADED
    return DEX_SAFETY_NET_HEALTHY


def dex_safety_net_coverage(
    *,
    enabled: bool,
    last_sweep_answered: bool,
) -> str:
    """COVERAGE CLAIM of the curated safety net.

    A successful poll reports :data:`DEX_SAFETY_NET_PARTIAL_COVERAGE`.  There
    is deliberately no path in this function that returns
    :data:`DEX_SAFETY_NET_HEALTHY`: a curated request answering successfully
    says the request worked, never that migration coverage is complete.
    """

    if not enabled:
        return DEX_SAFETY_NET_DISABLED
    if not last_sweep_answered:
        return DEX_SAFETY_NET_DEGRADED
    return DEX_SAFETY_NET_PARTIAL_COVERAGE


def curated_observation_status(
    *,
    observed: bool,
    curated_source_answered: bool,
) -> str:
    """Whether the curated source saw a mint — a claim about the SOURCE.

    ``NOT_OBSERVED_BY_CURATED_SOURCE`` never means the mint did not migrate;
    it means this best-effort surface did not list it.
    """

    if not curated_source_answered:
        return CURATED_SOURCE_UNAVAILABLE
    return (OBSERVED_BY_CURATED_SOURCE if observed
            else NOT_OBSERVED_BY_CURATED_SOURCE)


@dataclass(frozen=True)
class ContinuousDiscoveryStatus:
    """One redaction-safe projection of the whole discovery topology."""

    live_source_state: str
    gap_recovery_state: str
    dex_safety_net_state: str
    dex_safety_net_coverage: str
    curated_coverage_claim: str
    live_source_continuity_state: Optional[str]
    coverage_proven_continuous: bool
    durable_cursor_slot: Optional[int]
    last_migration_journal_commit_utc: Optional[str]
    migration_journal_record_count: int
    migration_journal_last_confirmed_slot: Optional[int]
    detected_gap_total: int
    open_gap_count: int
    recovered_ranges: Tuple[Tuple[int, int], ...]
    unresolved_ranges: Tuple[Tuple[int, int], ...]
    curated_rows_examined: int
    curated_candidates_admitted: int
    known_coverage_limitations: Tuple[str, ...] = KNOWN_COVERAGE_LIMITATIONS
    reconnect_policy: Mapping[str, Any] = field(default_factory=dict)

    def to_record(self) -> Dict[str, Any]:
        return {
            "schema_version": "phx2_continuous_discovery_status_v1",
            "live_source_state": self.live_source_state,
            "gap_recovery_state": self.gap_recovery_state,
            "dex_safety_net_state": self.dex_safety_net_state,
            "dex_safety_net_coverage": self.dex_safety_net_coverage,
            "curated_coverage_claim": self.curated_coverage_claim,
            "live_source_continuity_state": self.live_source_continuity_state,
            "coverage_proven_continuous": bool(self.coverage_proven_continuous),
            "durable_cursor_slot": self.durable_cursor_slot,
            "last_migration_journal_commit_utc": (
                self.last_migration_journal_commit_utc),
            "migration_journal_record_count": int(
                self.migration_journal_record_count),
            "migration_journal_last_confirmed_slot": (
                self.migration_journal_last_confirmed_slot),
            "detected_gap_total": int(self.detected_gap_total),
            "open_gap_count": int(self.open_gap_count),
            "recovered_ranges": [list(item) for item in self.recovered_ranges],
            "unresolved_ranges": [
                list(item) for item in self.unresolved_ranges],
            "curated_rows_examined": int(self.curated_rows_examined),
            "curated_candidates_admitted": int(
                self.curated_candidates_admitted),
            "known_coverage_limitations": list(
                self.known_coverage_limitations),
            "reconnect_policy": dict(self.reconnect_policy or {}),
        }


def _ranges(value: object) -> Tuple[Tuple[int, int], ...]:
    out: List[Tuple[int, int]] = []
    for item in value or ():
        if not isinstance(item, (list, tuple)) or len(item) != 2:
            continue
        low, high = item[0], item[1]
        if (isinstance(low, int) and not isinstance(low, bool)
                and isinstance(high, int) and not isinstance(high, bool)
                and low >= 0 and high >= low):
            out.append((int(low), int(high)))
    return tuple(out)


def _int(value: object, default: int = 0) -> int:
    if isinstance(value, int) and not isinstance(value, bool):
        return int(value)
    return int(default)


def _slot(value: object) -> Optional[int]:
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return int(value)
    return None


def build_discovery_status(
    *,
    transport_connected: bool,
    reconnecting: bool,
    authentication_failed: bool = False,
    stopped: bool = False,
    continuity_snapshot: Optional[Mapping[str, Any]] = None,
    journal_snapshot: Optional[Mapping[str, Any]] = None,
    backfill_snapshot: Optional[Mapping[str, Any]] = None,
    backfill_enabled: bool = True,
    reconnect_snapshot: Optional[Mapping[str, Any]] = None,
    terminal_gap_count: int = 0,
) -> ContinuousDiscoveryStatus:
    """Project the three subsystem snapshots into one honest status."""

    continuity = dict(continuity_snapshot or {})
    journal = dict(journal_snapshot or {})
    backfill = dict(backfill_snapshot or {})
    open_gaps = _int(continuity.get("open_gap_count"))
    answered = bool(backfill.get("last_sweep_answered", False))
    return ContinuousDiscoveryStatus(
        live_source_state=live_source_state(
            transport_connected=bool(transport_connected),
            reconnecting=bool(reconnecting),
            authentication_failed=bool(authentication_failed),
            stopped=bool(stopped)),
        gap_recovery_state=gap_recovery_state(
            open_gap_count=open_gaps,
            terminal_gap_count=_int(terminal_gap_count)),
        dex_safety_net_state=dex_safety_net_state(
            enabled=bool(backfill_enabled),
            consecutive_failed_sweeps=_int(
                backfill.get("consecutive_failed_sweeps")),
            sweeps_completed_total=_int(
                backfill.get("sweeps_completed_total")),
            required_sources_failed=bool(
                backfill.get("any_required_source_failed"))),
        dex_safety_net_coverage=dex_safety_net_coverage(
            enabled=bool(backfill_enabled),
            last_sweep_answered=answered),
        curated_coverage_claim=(
            CURATED_COVERAGE_CLAIM if backfill_enabled
            else DEX_SAFETY_NET_DISABLED),
        live_source_continuity_state=(
            str(continuity.get("continuity_state"))
            if continuity.get("continuity_state") is not None else None),
        coverage_proven_continuous=bool(
            continuity.get("coverage_proven_continuous", False)),
        durable_cursor_slot=_slot(continuity.get("last_durable_slot")),
        last_migration_journal_commit_utc=(
            journal.get("last_journal_commit_utc")
            if isinstance(journal.get("last_journal_commit_utc"), str)
            else None),
        migration_journal_record_count=_int(journal.get("record_count")),
        migration_journal_last_confirmed_slot=_slot(
            journal.get("last_confirmed_slot")),
        detected_gap_total=_int(continuity.get("gap_detected_total")),
        open_gap_count=open_gaps,
        recovered_ranges=_ranges(continuity.get("recovered_ranges")),
        unresolved_ranges=_ranges(continuity.get("unresolved_ranges")),
        curated_rows_examined=_int(backfill.get("curated_rows_examined")),
        curated_candidates_admitted=_int(
            backfill.get("candidates_admitted")),
        reconnect_policy=dict(reconnect_snapshot or {}),
    )


__all__ = (
    "CURATED_COVERAGE_CLAIM",
    "CURATED_OBSERVATION_VERDICTS",
    "CURATED_SOURCE_UNAVAILABLE",
    "ContinuousDiscoveryStatus",
    "DEX_SAFETY_NET_DEGRADED",
    "DEX_SAFETY_NET_DISABLED",
    "DEX_SAFETY_NET_HEALTHY",
    "DEX_SAFETY_NET_PARTIAL_COVERAGE",
    "DISCOVERY_STATES",
    "GAP_RECOVERY_ACTIVE",
    "GAP_RECOVERY_DEGRADED",
    "GAP_RECOVERY_IDLE",
    "KNOWN_COVERAGE_LIMITATIONS",
    "LIVE_AUTHENTICATION_FAILED",
    "LIVE_CONNECTED",
    "LIVE_RECONNECTING",
    "LIVE_STOPPED",
    "NOT_OBSERVED_BY_CURATED_SOURCE",
    "OBSERVED_BY_CURATED_SOURCE",
    "REQUIRED_DISCOVERY_STATES",
    "build_discovery_status",
    "curated_observation_status",
    "dex_safety_net_coverage",
    "dex_safety_net_state",
    "gap_recovery_state",
    "live_source_state",
)

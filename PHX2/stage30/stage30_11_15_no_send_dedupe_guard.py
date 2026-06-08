"""Stage 30.11.15 no-send private operator ping dedupe guard + orchestrator.

The pure, offline GUARD that derives a Stage 30.11.15 dedupe key from a frozen
committed Stage 30.11.13 composed snapshot and consults an INJECTED
``PingDedupeLedger`` BEFORE dispatch -- plus the thin deduped ORCHESTRATOR that
wires the guard into the committed ``compose_no_send_dispatch`` through its
``pre_dispatch_guard`` hook:

    a frozen Stage 30.11.13 ``Stage30_11_13ComposedSnapshot`` (read duck-typed)
      -> ``derive_ping_dedupe_key`` (mint + signal kind + tier + drawdown BAND +
         ATH-verified + ATH source stage + policy version; NEVER ``candidate_id``
         / exact drawdown / MC / ATH price / timestamp)
      -> the INJECTED ledger's ``check_and_reserve`` keyed off the snapshot's own
         ``created_at_utc`` (the TTL "now") -- a duplicate within TTL suppresses;
         a new / aged-out / changed state reserves + allows
      -> a closed-set ``Stage30_11_15PingDedupeOutcome`` the composer reads as
         ``allowed`` / ``unavailable``

The guard is TOTAL: a malformed snapshot / missing field / odd ledger return /
any unexpected exception fails CLOSED to ``DEDUPE_UNAVAILABLE``; it NEVER raises.
The composer's ``pre_dispatch_guard`` hook treats any non-``allowed`` verdict as
a fail-closed rejection (no runner call, no body, transport_attempts 0). The
guard owns NO persistence itself -- the injected ledger does any file I/O; the
composer stays file-free.

The orchestrator ``compose_no_send_dispatch_deduped`` REQUIRES an explicit
ledger: a ``None`` ledger fails closed (no compose) for the deduped /
send-ready path. It composes the committed ``compose_no_send_dispatch`` verbatim
(same inputs) with the guard injected, and returns the compose result paired
with the dedupe outcome.

This module builds the guard / orchestrator ONLY. It reads NO process
environment, opens NO network connection, opens NO database, writes NO file
(persistence lives entirely in the injected ledger), reads NO wall clock
(``created_at_utc`` is read off the injected snapshot), reserves NO real
dispatch, sends NO Discord message, signs nothing, trades nothing, and edits NO
ATH-anchoring / market-freshness / Stage 30.12 renderer / tier-band file. Stage
30.11.15 is fake / offline only: the real private compact dispatch / Discord
send remains a SEPARATE, explicitly operator-authorized step this slice does not
build.

Discipline:

  * Stdlib only (``dataclasses`` / ``typing``).
  * Imports the Stage 30.11.15 models + ledger siblings plus the committed Stage
    30.11.13 ``compose_no_send_dispatch`` the orchestrator drives (the permitted
    Stage 30.11 scope expansion: it composes the committed composer behind the
    dedupe guard; it forks / reimplements / edits none of it).
  * No ``os.environ`` / ``os.getenv`` access; no env read.
  * No network, no HTTP, no gRPC, no WebSocket, no socket.
  * No database / SQLite, no zstd / compression, no default storage root.
  * No live provider, transport-destination, or request-metadata reference.
  * No PHX1 import. No Stage 21-29 production import.
  * No ``time`` / ``datetime`` import; the TTL "now" is the injected snapshot's
    ``created_at_utc`` and is parsed only by the ledger.
  * No filesystem write surface (persistence is the injected ledger's job).
  * No module-level Call node (no implicit I/O at import time).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from PHX2.stage30.stage30_11_13_committed_no_send_composer import (
    compose_no_send_dispatch,
)
from PHX2.stage30.stage30_11_15_ping_dedupe_ledger import (
    PingDedupeLedger,
)
from PHX2.stage30.stage30_11_15_ping_dedupe_models import (
    DEDUPE_REASON_LEDGER_UNAVAILABLE,
    DEDUPE_REASON_MALFORMED_KEY,
    STAGE30_11_15_DEFAULT_DRAWDOWN_BUCKET_PCT,
    STAGE30_11_15_DEFAULT_TTL_SECONDS,
    STAGE30_11_15_OPERATOR_SIGNAL_KIND,
    STAGE30_11_15_POLICY_VERSION,
    Stage30_11_15PingDedupeKey,
    Stage30_11_15PingDedupeOutcome,
    drawdown_band_token,
    is_nonblank_str,
    unavailable_outcome,
)


# ---------------------------------------------------------------------------
# Key derivation from the frozen Stage 30.11.13 composed snapshot
# ---------------------------------------------------------------------------


def derive_ping_dedupe_key(
    snapshot: Any,
    *,
    operator_signal_kind: str = STAGE30_11_15_OPERATOR_SIGNAL_KIND,
    policy_version: str = STAGE30_11_15_POLICY_VERSION,
    drawdown_bucket_pct: int = STAGE30_11_15_DEFAULT_DRAWDOWN_BUCKET_PCT,
) -> Optional[Stage30_11_15PingDedupeKey]:
    """Derive the Stage 30.11.15 dedupe key from a frozen Stage 30.11.13 composed
    snapshot, or ``None`` (fail closed) on any malformed / missing field.

    Reads the snapshot duck-typed (``getattr``): ``token_mint`` / ``tier_token``
    / ``post_migration_ath_verified`` / ``ath_source_stage`` for the state-class
    axes, and ``drawdown_from_ath`` (the exact Decimal) + ``ath_price`` ONLY to
    compute the rounded ``drawdown_band`` (both are then discarded). It NEVER
    reads ``candidate_id`` / ``current_market_cap_usd`` / ``created_at_utc`` --
    those move run to run and would defeat suppression. Pure / deterministic /
    total; never raises.
    """
    token_mint = getattr(snapshot, "token_mint", None)
    tier_token = getattr(snapshot, "tier_token", None)
    verified = getattr(snapshot, "post_migration_ath_verified", None)
    ath_source_stage = getattr(snapshot, "ath_source_stage", None)
    drawdown = getattr(snapshot, "drawdown_from_ath", None)
    ath_price = getattr(snapshot, "ath_price", None)

    if not is_nonblank_str(token_mint):
        return None
    if not is_nonblank_str(tier_token):
        return None
    if not isinstance(verified, bool):
        return None
    if not is_nonblank_str(ath_source_stage):
        return None
    if not is_nonblank_str(operator_signal_kind):
        return None
    if not is_nonblank_str(policy_version):
        return None

    band = drawdown_band_token(
        drawdown, ath_price, bucket_pct=drawdown_bucket_pct
    )
    if band is None:
        return None

    return Stage30_11_15PingDedupeKey(
        token_mint=token_mint,
        operator_signal_kind=operator_signal_kind,
        tier_token=tier_token,
        drawdown_band=band,
        post_migration_ath_verified=verified,
        ath_source_stage=ath_source_stage,
        policy_version=policy_version,
    )


# ---------------------------------------------------------------------------
# The pre-dispatch dedupe guard (callable; records its last outcome)
# ---------------------------------------------------------------------------


class Stage30_11_15NoSendDedupeGuard:
    """A callable pre-dispatch dedupe guard for the committed Stage 30.11.13
    composer's ``pre_dispatch_guard`` hook.

    Given a frozen composed snapshot it derives the dedupe key, reads the TTL
    "now" off the snapshot's ``created_at_utc``, and consults the INJECTED ledger
    once. It returns -- and records on ``last_outcome`` -- a closed-set
    ``Stage30_11_15PingDedupeOutcome``. TOTAL: a malformed snapshot / missing now
    / odd ledger return / any exception fails closed to ``DEDUPE_UNAVAILABLE``;
    it NEVER raises (so the composer stays total).
    """

    def __init__(
        self,
        *,
        ledger: Optional[PingDedupeLedger],
        ttl_seconds: int = STAGE30_11_15_DEFAULT_TTL_SECONDS,
        operator_signal_kind: str = STAGE30_11_15_OPERATOR_SIGNAL_KIND,
        policy_version: str = STAGE30_11_15_POLICY_VERSION,
        drawdown_bucket_pct: int = STAGE30_11_15_DEFAULT_DRAWDOWN_BUCKET_PCT,
    ) -> None:
        self._ledger = ledger
        self._ttl_seconds = ttl_seconds
        self._operator_signal_kind = operator_signal_kind
        self._policy_version = policy_version
        self._drawdown_bucket_pct = drawdown_bucket_pct
        self.last_outcome: Optional[Stage30_11_15PingDedupeOutcome] = None

    def __call__(self, snapshot: Any) -> Stage30_11_15PingDedupeOutcome:
        outcome = self._evaluate(snapshot)
        self.last_outcome = outcome
        return outcome

    def _evaluate(self, snapshot: Any) -> Stage30_11_15PingDedupeOutcome:
        try:
            if self._ledger is None:
                return unavailable_outcome(DEDUPE_REASON_LEDGER_UNAVAILABLE)
            key = derive_ping_dedupe_key(
                snapshot,
                operator_signal_kind=self._operator_signal_kind,
                policy_version=self._policy_version,
                drawdown_bucket_pct=self._drawdown_bucket_pct,
            )
            if key is None:
                return unavailable_outcome(DEDUPE_REASON_MALFORMED_KEY)
            now_utc = getattr(snapshot, "created_at_utc", None)
            outcome = self._ledger.check_and_reserve(
                key=key, now_utc=now_utc, ttl_seconds=self._ttl_seconds
            )
            if not isinstance(outcome, Stage30_11_15PingDedupeOutcome):
                return unavailable_outcome(DEDUPE_REASON_LEDGER_UNAVAILABLE)
            return outcome
        except Exception:
            # Defense in depth: the guard is total, so a buggy ledger can never
            # raise through into the composer -- it fails closed instead.
            return unavailable_outcome(DEDUPE_REASON_LEDGER_UNAVAILABLE)


def make_no_send_dedupe_guard(
    *,
    ledger: Optional[PingDedupeLedger],
    ttl_seconds: int = STAGE30_11_15_DEFAULT_TTL_SECONDS,
    operator_signal_kind: str = STAGE30_11_15_OPERATOR_SIGNAL_KIND,
    policy_version: str = STAGE30_11_15_POLICY_VERSION,
    drawdown_bucket_pct: int = STAGE30_11_15_DEFAULT_DRAWDOWN_BUCKET_PCT,
) -> Stage30_11_15NoSendDedupeGuard:
    """Build a pre-dispatch dedupe guard bound to ``ledger`` + the TTL / key
    policy. The returned callable plugs directly into the committed Stage 30.11.13
    ``compose_no_send_dispatch(..., pre_dispatch_guard=...)`` hook.
    """
    return Stage30_11_15NoSendDedupeGuard(
        ledger=ledger,
        ttl_seconds=ttl_seconds,
        operator_signal_kind=operator_signal_kind,
        policy_version=policy_version,
        drawdown_bucket_pct=drawdown_bucket_pct,
    )


# ---------------------------------------------------------------------------
# The deduped no-send orchestrator
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Stage30_11_15DedupedComposeResult:
    """The deduped no-send compose outcome.

    ``compose_result`` is the committed Stage 30.11.13 ``Stage30_11_13ComposeResult``
    (or ``None`` when the orchestrator failed closed BEFORE composing -- a
    missing ledger). ``dedupe_outcome`` is the guard's recorded
    ``Stage30_11_15PingDedupeOutcome`` (or ``None`` when the compose rejected
    BEFORE the snapshot / guard ran -- e.g. stale market context).
    """

    compose_result: Any
    dedupe_outcome: Optional[Stage30_11_15PingDedupeOutcome]


def compose_no_send_dispatch_deduped(
    request: Any,
    *,
    ath_transport: object,
    ath_endpoint_secret: object,
    now_utc: object,
    transport_client: Any,
    now_seconds: object,
    ledger: Optional[PingDedupeLedger],
    ttl_seconds: int = STAGE30_11_15_DEFAULT_TTL_SECONDS,
    operator_signal_kind: str = STAGE30_11_15_OPERATOR_SIGNAL_KIND,
    policy_version: str = STAGE30_11_15_POLICY_VERSION,
    drawdown_bucket_pct: int = STAGE30_11_15_DEFAULT_DRAWDOWN_BUCKET_PCT,
    ath_timeout_seconds: int = 10,
    market_context_max_age_seconds: Optional[int] = None,
) -> Stage30_11_15DedupedComposeResult:
    """Compose ONE no-send dispatch behind the cross-run dedupe guard.

    Requires an explicit ``ledger``: a ``None`` ledger fails CLOSED (no compose,
    no runner call, no transport) and returns a ``DEDUPE_UNAVAILABLE`` outcome --
    the send-ready path never composes without a dedupe surface. Otherwise it
    builds a guard over the ledger and drives the committed
    ``compose_no_send_dispatch`` with it injected as ``pre_dispatch_guard``; a
    duplicate within TTL suppresses the dispatch (no runner call, no body,
    transport_attempts 0). Returns the compose result paired with the guard's
    recorded dedupe outcome. Reads no env, no network, no wall clock; sends no
    Discord; reserves no real dispatch.
    """
    if ledger is None:
        return Stage30_11_15DedupedComposeResult(
            compose_result=None,
            dedupe_outcome=unavailable_outcome(
                DEDUPE_REASON_LEDGER_UNAVAILABLE
            ),
        )

    guard = make_no_send_dedupe_guard(
        ledger=ledger,
        ttl_seconds=ttl_seconds,
        operator_signal_kind=operator_signal_kind,
        policy_version=policy_version,
        drawdown_bucket_pct=drawdown_bucket_pct,
    )

    compose_kwargs = {"ath_timeout_seconds": ath_timeout_seconds}
    if market_context_max_age_seconds is not None:
        compose_kwargs["market_context_max_age_seconds"] = (
            market_context_max_age_seconds
        )

    compose_result = compose_no_send_dispatch(
        request,
        ath_transport=ath_transport,
        ath_endpoint_secret=ath_endpoint_secret,
        now_utc=now_utc,
        transport_client=transport_client,
        now_seconds=now_seconds,
        pre_dispatch_guard=guard,
        **compose_kwargs,
    )

    return Stage30_11_15DedupedComposeResult(
        compose_result=compose_result,
        dedupe_outcome=guard.last_outcome,
    )


__all__ = (
    "derive_ping_dedupe_key",
    "Stage30_11_15NoSendDedupeGuard",
    "make_no_send_dedupe_guard",
    "Stage30_11_15DedupedComposeResult",
    "compose_no_send_dispatch_deduped",
)

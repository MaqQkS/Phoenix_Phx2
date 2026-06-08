"""Stage 30.11.13 committed end-to-end no-send composer.

The pure, offline COMPOSER that fixes the two narrowest blockers the
independent system audit left open after Stage 30.11.12:

  1. the committed Stage 30.11.10 ATH resolver accepts ANY duck-typed
     ``ath_context_source`` -- so a ceremony could (accidentally) wire an
     old sliding-window ATH source instead of the committed Stage 30.11.11
     migration-anchored source; and
  2. the PHOENIX operator body values (tier / MC / ATH MC / drop / price)
     are NOT bound to the gate-decision values -- the committed Stage
     30.12.1 body builder verifies only the ``token_mint`` at dispatch, so
     a body rendered from one revalidation snapshot could be paired with a
     gate decision computed from a DIFFERENT snapshot (silent drift).

Stage 30.11.13 closes both by composing the WHOLE committed dip-gated
private dispatch chain over ONE immutable revalidation snapshot:

    a Stage30_11_13RevalidationRequest (the raw revalidated operator
    inputs -- identity / migration confirmation / current price / current
    market cap / liquidity)
      + an INJECTED Stage 30.11.11 migration-anchored ATH source transport
        + endpoint secret + now-clock (a FAKE in every committed proof)
      + an INJECTED Stage 30.11.5 recording FAKE transport client
      -> read the migration-anchored ATH ONCE via the committed Stage
         30.11.11 source (the composer INSTANTIATES that source itself -- it
         exposes NO generic ``ath_context_source`` seam, so an old sliding
         source can NEVER be wired); fail closed unless RESOLVED + PRESENT +
         post-migration verified + a drawdown + an ATH price
      -> resolve the SAME Stage 30.11.11-backed source through the committed
         Stage 30.11.10 resolver and cross-check its drawdown equals the
         anchored drawdown (no arbitrary duck-typed source)
      -> classify the tier from the committed Stage 30.1 ``decide_tier`` over
         the committed Stage 27.4 reading; fail closed on a non-dip tier
      -> compute the ATH market cap in COMMITTED code
         (``inferred_supply = current_mc / current_price``;
         ``ath_mc = ath_price * inferred_supply``) and format it via the
         committed Stage 30.4.1 ``format_usd_compact``; fail closed (NO
         dispatch) when it cannot be computed -- a dispatch-eligible body
         NEVER shows ``Unknown`` ATH MC
      -> build ONE immutable Stage30_11_13ComposedSnapshot whose
         ``gate_binding_key`` ties the gate-decision scalars together
      -> derive BOTH the committed Stage 30.11.7 enriched candidate (-> the
         committed Stage 30.11.5 runner -> Stage 30.11.1 bridge -> Stage
         30.9.3 dip gate -> Stage 30.11.3 private sink) AND the committed
         Stage 30.12 PHOENIX body context FROM THAT ONE snapshot
      -> dispatch through the committed Stage 30.11.5 bounded runner with a
         snapshot-bound body builder that verifies the FULL binding key (not
         just the token mint) at dispatch -- a gate input that does not match
         the snapshot fails closed and NO body is emitted
      -> a Stage30_11_13ComposeResult

The composer NEVER sends Discord, NEVER calls a real transport / webhook,
NEVER reads the process environment, NEVER opens a network connection,
NEVER reserves a real dispatch, NEVER signs, NEVER trades, NEVER writes a
file, and NEVER reads a wall clock (``now_utc`` / ``now_seconds`` /
``created_at_utc`` are injected). The only transport it admits is the
committed Stage 30.11.5 in-memory recording FAKE -- a non-fake transport
client fails closed BEFORE anything is composed. The real private compact
dispatch / Discord send remains a SEPARATE, explicitly operator-authorized
step Stage 30.11.13 does NOT build.

Discipline:

  * Stdlib only (``dataclasses`` / ``decimal`` / ``typing``).
  * Integration capstone: imports the committed Stage 30.11.11 / 30.11.10 /
    30.11.7 / 30.11.5 slices, the committed Stage 30.12.1 body-builder
    factory + Stage 30.12 error, the committed Stage 30.1 ``decide_tier`` +
    tier models, the committed Stage 30.4.1 ``format_usd_compact``, and the
    committed Stage 27.4 ``MigrationContextRecord`` (for ``decide_tier``;
    the same audited Stage 27.4 dependency Stage 30.11.11 already takes). It
    drives those committed slices; it RE-IMPLEMENTS none of them and EDITS
    none of them.
  * No ``os.environ`` / ``os.getenv`` access; no env read.
  * No network, no HTTP, no gRPC, no WebSocket, no socket; the ATH source
    transport + the dispatch transport client are BOTH injected fakes.
  * No database / SQLite, no zstd / compression, no default storage root.
  * No real provider, transport-destination, webhook, or request-metadata
    reference; no wallet / signing / trading surface; no public / subscriber
    routing; no dedupe.
  * No PHX1 import. No ``time`` / ``datetime`` import; the runtime clock /
    now-clock / timestamps are caller-injected.
  * No module-level Call node (no implicit I/O at import time; the
    ``@dataclass(frozen=True)`` decorators are decorator-list Calls, not
    body-statement Calls).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Callable, Optional, Tuple

from PHX2.stage27.migration_context_models import (
    MIGRATION_REASON_OK,
    MIGRATION_SOURCE_ON_CHAIN_MIGRATION_EVENT,
    MIGRATION_STATUS_PRESENT,
    MigrationContextRecord,
    STAGE27_4_MIGRATION_SCHEMA_VERSION,
)
from PHX2.stage30.stage30_4_compact_market_context_formatter import (
    format_usd_compact,
)
from PHX2.stage30.stage30_11_5_bounded_live_runner import (
    run_stage30_11_5_bounded_live_runner,
)
from PHX2.stage30.stage30_11_5_fake_live_wiring_proof import (
    Stage30_11_5RecordingFakeTransportClient,
)
from PHX2.stage30.stage30_11_7_candidate_enrichment_adapter import (
    enrich_harvested_candidate,
)
from PHX2.stage30.stage30_11_7_candidate_enrichment_models import (
    ENRICH_DECISION_ENRICHED,
    Stage30_11_7MarketContextResolution,
    Stage30_11_7MigrationResolution,
    Stage30_11_7TierResolution,
)
from PHX2.stage30.stage30_11_10_ath_resolver_adapter import (
    build_ath_resolver,
)
from PHX2.stage30.stage30_11_11_migration_anchored_ath_source import (
    Stage30_11_11MigrationAnchoredAthContextSource,
    build_migration_anchored_ath_context_source,
)
from PHX2.stage30.stage30_12_1_phoenix_operator_ping_body_builder import (
    PhoenixOperatorPingContext,
    make_phoenix_operator_ping_body_builder,
)
from PHX2.stage30.stage30_12_phoenix_operator_ping_models import (
    Stage30_12PhoenixOperatorPingError,
)
from PHX2.stage30.tier_decision_models import (
    BASIS_PRICE,
    TIER_TOKEN_TIER_UNKNOWN,
)
from PHX2.stage30.tier_decision_projector import decide_tier


# ---------------------------------------------------------------------------
# Minor version + identity
# ---------------------------------------------------------------------------


STAGE30_11_13_MINOR_VERSION: str = "30.11.13"

STAGE30_11_13_COMPOSE_SCHEMA_VERSION: str = (
    "stage30_11_13_v0_committed_no_send_composer"
)

# The committed ATH source provenance stamp; ONLY the Stage 30.11.11
# migration-anchored source can produce a composer snapshot.
STAGE30_11_13_ATH_SOURCE_STAGE: str = "stage30_11_11"

# The gate's PRESENT token the committed Stage 30.11.7 enrichment stamps on a
# confirmed dimension (mirrored BY VALUE; the composer imports no enrichment
# status constant beyond the carriers it builds).
_CONTEXT_STATUS_PRESENT: str = "PRESENT"

_PAIR_TYPE_SOL: str = "SOL"


# ---------------------------------------------------------------------------
# Closed-set compose decision / reason tokens
# ---------------------------------------------------------------------------


COMPOSE_DECISION_DISPATCHED: str = "NO_SEND_DISPATCHED"
COMPOSE_DECISION_REJECTED: str = "REJECTED"

STAGE30_11_13_COMPOSE_DECISIONS: Tuple[str, ...] = (
    COMPOSE_DECISION_DISPATCHED,
    COMPOSE_DECISION_REJECTED,
)

COMPOSE_REASON_NO_SEND_DISPATCH_RECORDED: str = "NO_SEND_DISPATCH_RECORDED"
COMPOSE_REJECTED_INVALID_REQUEST: str = "INVALID_REQUEST"
COMPOSE_REJECTED_ATH_SOURCE_NOT_ANCHORED: str = "ATH_SOURCE_NOT_ANCHORED"
COMPOSE_REJECTED_NON_FAKE_TRANSPORT: str = "NON_FAKE_TRANSPORT"
COMPOSE_REJECTED_ATH_NOT_RESOLVED: str = "ATH_NOT_RESOLVED"
COMPOSE_REJECTED_MISSING_DRAWDOWN: str = "MISSING_DRAWDOWN"
COMPOSE_REJECTED_MISSING_ATH_PRICE: str = "MISSING_ATH_PRICE"
COMPOSE_REJECTED_ATH_RESOLUTION_MISMATCH: str = "ATH_RESOLUTION_MISMATCH"
COMPOSE_REJECTED_TIER_NOT_ELIGIBLE: str = "TIER_NOT_ELIGIBLE"
COMPOSE_REJECTED_ATH_MC_UNAVAILABLE: str = "ATH_MC_UNAVAILABLE"
COMPOSE_REJECTED_ENRICHMENT_FAILED: str = "ENRICHMENT_FAILED"
COMPOSE_REJECTED_GATE_DID_NOT_PASS: str = "GATE_DID_NOT_PASS"
COMPOSE_REJECTED_GATE_BODY_MISMATCH: str = "GATE_BODY_MISMATCH"
COMPOSE_REJECTED_BODY_BUILD_FAILED: str = "BODY_BUILD_FAILED"

STAGE30_11_13_COMPOSE_REASONS: Tuple[str, ...] = (
    COMPOSE_REASON_NO_SEND_DISPATCH_RECORDED,
    COMPOSE_REJECTED_INVALID_REQUEST,
    COMPOSE_REJECTED_ATH_SOURCE_NOT_ANCHORED,
    COMPOSE_REJECTED_NON_FAKE_TRANSPORT,
    COMPOSE_REJECTED_ATH_NOT_RESOLVED,
    COMPOSE_REJECTED_MISSING_DRAWDOWN,
    COMPOSE_REJECTED_MISSING_ATH_PRICE,
    COMPOSE_REJECTED_ATH_RESOLUTION_MISMATCH,
    COMPOSE_REJECTED_TIER_NOT_ELIGIBLE,
    COMPOSE_REJECTED_ATH_MC_UNAVAILABLE,
    COMPOSE_REJECTED_ENRICHMENT_FAILED,
    COMPOSE_REJECTED_GATE_DID_NOT_PASS,
    COMPOSE_REJECTED_GATE_BODY_MISMATCH,
    COMPOSE_REJECTED_BODY_BUILD_FAILED,
)


class Stage30_11_13ComposerError(Exception):
    """Raised by the snapshot-bound body builder when a dispatched gate input
    does NOT match the immutable snapshot's gate binding key.

    Carries a closed-set reason token (``GATE_BODY_MISMATCH``). The composer's
    own ``compose_no_send_dispatch`` never raises for a caller-shape failure --
    it returns a ``REJECTED`` result; this error exists ONLY for the
    dispatch-time binding guard, so a stale / drifted body can never be emitted
    for a different gate decision.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


# ---------------------------------------------------------------------------
# Immutable records: the revalidation request + the composed snapshot
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Stage30_11_13RevalidationRequest:
    """The raw revalidated operator inputs for ONE no-send compose.

    A passive carrier of the facts an operator / ceremony has honestly
    revalidated at compose time. Carries only safe scalars (decimal-text
    magnitudes, closed-set / opaque ids, a caller-injected timestamp); no
    secret, no raw payload, no host, no transport destination, no webhook.

      * ``token_mint`` / ``candidate_id`` -- safe-shape identity.
      * ``symbol_or_name``                -- optional display symbol.
      * ``migration_confirmed``           -- ``True`` for a confirmed
                                             migration (a non-``True`` value
                                             fails closed at compose).
      * ``migration_time_utc``            -- the confirmed migration anchor
                                             (ISO-8601 UTC; the Stage 30.11.11
                                             window start).
      * ``migration_source``              -- opaque migration provenance ref.
      * ``current_price``                 -- current price, decimal text.
      * ``current_market_cap_usd``        -- current market cap, decimal text.
      * ``liquidity_usd``                 -- optional LP, decimal text or None.
      * ``age_display``                   -- optional age display string.
      * ``created_at_utc``                -- caller-injected ISO-8601 UTC.
    """

    token_mint: str
    candidate_id: str
    migration_time_utc: str
    current_price: str
    current_market_cap_usd: str
    created_at_utc: str
    migration_confirmed: bool = True
    symbol_or_name: Optional[str] = None
    migration_source: Optional[str] = None
    liquidity_usd: Optional[str] = None
    age_display: Optional[str] = None


@dataclass(frozen=True)
class Stage30_11_13GateBindingKey:
    """The immutable tuple of gate-decision scalars a dispatched gate input
    MUST match for the snapshot-bound body to be emitted.

    Binds the body to the gate decision: ``token_mint`` + ``tier_token`` +
    ``drawdown_from_ath`` + ``current_market_cap_usd`` + ``migration_status`` +
    ``ath_status`` + ``post_migration_ath_verified`` + ``created_at_utc``. The
    magnitudes are ``Decimal`` so a re-formatted text can never spoof a value.
    """

    token_mint: str
    tier_token: str
    drawdown_from_ath: Decimal
    current_market_cap_usd: Decimal
    migration_status: str
    ath_status: str
    post_migration_ath_verified: bool
    created_at_utc: str


@dataclass(frozen=True)
class Stage30_11_13ComposedSnapshot:
    """The ONE immutable revalidation snapshot both the gate input and the
    PHOENIX body derive from. Built ONLY when every fail-closed gate passed.
    """

    # Identity
    token_mint: str
    candidate_id: str
    symbol_or_name: Optional[str]
    created_at_utc: str
    snapshot_id: str
    # Gate scalars
    tier_token: str
    drawdown_from_ath: Decimal
    current_market_cap_usd: Decimal
    migration_status: str
    ath_status: str
    market_context_status: str
    post_migration_ath_verified: bool
    # Display raws
    current_price: str
    ath_price: str
    liquidity_usd: Optional[str]
    migration_confirmed: bool
    migration_time_utc: str
    migration_source: Optional[str]
    age_display: Optional[str]
    basis_display: str
    # Derived displays
    market_cap_display: str
    liquidity_display: Optional[str]
    ath_market_cap_display: str
    absolute_drawdown: str
    fractional_drop_pct: str
    tier_band_display: Optional[str]
    # ATH provenance (the committed Stage 30.11.11 migration-anchored window)
    ath_source_stage: str
    time_from_unix: Optional[int]
    time_to_unix: Optional[int]
    ohlcv_type: Optional[str]
    span_seconds: Optional[int]
    ath_source_ref: Optional[str]
    # Binding
    gate_binding_key: Stage30_11_13GateBindingKey


@dataclass(frozen=True)
class Stage30_11_13ComposeResult:
    """The composer outcome -- a recorded no-send dispatch or a fail-closed
    rejection. ALWAYS returned (the composer never raises for a caller-shape
    failure).
    """

    decision: str
    reason: str
    token_mint: str
    candidate_id: str
    created_at_utc: str
    snapshot: Optional[Stage30_11_13ComposedSnapshot] = None
    run_result: Any = None
    transport_attempts: int = 0
    transport_accepts: int = 0
    dispatched_body: Optional[str] = None


# ---------------------------------------------------------------------------
# Internal migration anchor verdict (for the Stage 30.11.10 resolver seam)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _ComposerMigrationAnchor:
    """A confirmed Stage 30.11.8-shaped migration verdict for the committed
    Stage 30.11.10 resolver: ``confirmed is True`` + a non-blank
    ``migration_event_time_utc``. Derived from the revalidation request.
    """

    token_mint: str
    migration_event_time_utc: str
    confirmed: bool = True
    source_ref: Optional[str] = None


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def _coerce_positive_decimal(value: object) -> Optional[Decimal]:
    """Coerce safe decimal text / int / Decimal to a finite, strictly-positive
    ``Decimal``; else ``None``. Never raises.
    """
    if value is None or isinstance(value, bool):
        return None
    if not isinstance(value, (str, int, Decimal)):
        return None
    try:
        parsed = Decimal(value)
    except (InvalidOperation, ValueError, TypeError):
        return None
    if not parsed.is_finite() or parsed <= 0:
        return None
    return parsed


def _coerce_finite_decimal(value: object) -> Optional[Decimal]:
    """Coerce safe decimal text / int / Decimal to a finite (>= 0) ``Decimal``;
    else ``None``. Never raises.
    """
    if value is None or isinstance(value, bool):
        return None
    if not isinstance(value, (str, int, Decimal)):
        return None
    try:
        parsed = Decimal(value)
    except (InvalidOperation, ValueError, TypeError):
        return None
    if not parsed.is_finite() or parsed < 0:
        return None
    return parsed


def _build_present_migration_record(
    *, token_mint: str, migration_time_utc: str, observed_at_utc: str
) -> MigrationContextRecord:
    """Build a PRESENT committed Stage 27.4 ``MigrationContextRecord`` from the
    confirmed migration anchor (for the committed Stage 30.1 ``decide_tier``).
    """
    return MigrationContextRecord(
        token_mint=token_mint,
        pair_type="PUMP_SOL",
        quote_asset="SOL",
        migration_event_id=None,
        migration_timestamp_utc=migration_time_utc,
        migration_source=MIGRATION_SOURCE_ON_CHAIN_MIGRATION_EVENT,
        migration_status=MIGRATION_STATUS_PRESENT,
        migration_reason=MIGRATION_REASON_OK,
        age_since_migration_seconds=None,
        observed_at_utc=observed_at_utc,
        source_event_ref=None,
        raw_capture_ref=None,
        schema_version=STAGE27_4_MIGRATION_SCHEMA_VERSION,
    )


def _compute_ath_market_cap_display(
    *, current_market_cap_usd: Decimal, current_price: Decimal, ath_price: Decimal
) -> Optional[str]:
    """Compute + compact-format the ATH market cap in committed code.

    ``inferred_supply = current_market_cap / current_price``;
    ``ath_market_cap = ath_price * inferred_supply``; formatted via the committed
    Stage 30.4.1 ``format_usd_compact``. Returns ``None`` (fail closed) on any
    non-finite / non-positive intermediate or a formatter rejection. Pure.
    """
    try:
        inferred_supply = current_market_cap_usd / current_price
        ath_market_cap = ath_price * inferred_supply
    except (InvalidOperation, ZeroDivisionError):
        return None
    if not ath_market_cap.is_finite() or ath_market_cap <= 0:
        return None
    try:
        return format_usd_compact(format(ath_market_cap, "f"))
    except ValueError:
        return None


def _fractional_drop_display(
    *, drawdown: Decimal, ath_value: Decimal
) -> str:
    """A simple ``NN.NN%`` fractional-drop display string (display-only; the
    gate reads the Decimal drawdown, never this string). Best-effort; never
    raises.
    """
    try:
        if ath_value <= 0:
            return "Unknown"
        pct = (drawdown / ath_value) * Decimal(100)
        return f"{pct.quantize(Decimal('0.01'))}%"
    except (InvalidOperation, ZeroDivisionError):
        return "Unknown"


def _binding_mismatch(
    gate_input: Any, key: Stage30_11_13GateBindingKey
) -> bool:
    """Return ``True`` iff a dispatched gate input does NOT match EVERY field of
    the snapshot binding key. Total; a missing / malformed field is a mismatch.
    """
    if getattr(gate_input, "token_mint", None) != key.token_mint:
        return True
    if getattr(gate_input, "tier_token", None) != key.tier_token:
        return True
    if getattr(gate_input, "migration_status", None) != key.migration_status:
        return True
    if getattr(gate_input, "ath_status", None) != key.ath_status:
        return True
    if (
        getattr(gate_input, "post_migration_ath_verified", None)
        is not key.post_migration_ath_verified
    ):
        return True
    if getattr(gate_input, "created_at_utc", None) != key.created_at_utc:
        return True
    gi_drawdown = _coerce_finite_decimal(
        getattr(gate_input, "drawdown_from_ath", None)
    )
    if gi_drawdown is None or gi_drawdown != key.drawdown_from_ath:
        return True
    gi_mc = _coerce_positive_decimal(
        getattr(gate_input, "current_market_cap_usd", None)
    )
    if gi_mc is None or gi_mc != key.current_market_cap_usd:
        return True
    return False


def _make_snapshot_bound_body_builder(
    snapshot: Stage30_11_13ComposedSnapshot,
) -> Callable[[Any], str]:
    """Build the snapshot-bound compact body builder.

    Renders the committed Stage 30.12 PHOENIX body ONCE here (so a Stage 30.12
    fail-closed surfaces BEFORE the runner). The returned callable verifies the
    FULL snapshot binding key against the dispatched gate input -- not just the
    token mint -- and raises ``Stage30_11_13ComposerError`` (reason
    ``GATE_BODY_MISMATCH``) on ANY mismatch, so a body rendered for one
    snapshot can NEVER be emitted for a different gate decision.
    """
    context = PhoenixOperatorPingContext(
        token_mint=snapshot.token_mint,
        tier_token=snapshot.tier_token,
        symbol_or_name=snapshot.symbol_or_name,
        migration_confirmed=snapshot.migration_confirmed,
        migration_time_utc=snapshot.migration_time_utc,
        market_cap_display=snapshot.market_cap_display,
        liquidity_display=snapshot.liquidity_display,
        current_price=snapshot.current_price,
        ath_price=snapshot.ath_price,
        absolute_drawdown=snapshot.absolute_drawdown,
        fractional_drop_pct=snapshot.fractional_drop_pct,
        tier_band_display=snapshot.tier_band_display,
        basis_display=snapshot.basis_display,
        source_ref=snapshot.ath_source_ref,
        age_display=snapshot.age_display,
        ath_market_cap_display=snapshot.ath_market_cap_display,
    )
    # Renders ONCE here; a Stage 30.12 fail-closed raises
    # Stage30_12PhoenixOperatorPingError BEFORE the runner is composed.
    inner_builder = make_phoenix_operator_ping_body_builder(context)
    key = snapshot.gate_binding_key

    def _bound_builder(gate_input: Any) -> str:
        if _binding_mismatch(gate_input, key):
            raise Stage30_11_13ComposerError(
                COMPOSE_REJECTED_GATE_BODY_MISMATCH
            )
        # The inner builder re-checks the token mint and returns the
        # pre-rendered body verbatim.
        return inner_builder(gate_input)

    return _bound_builder


def make_snapshot_bound_body_builder(
    snapshot: Stage30_11_13ComposedSnapshot,
) -> Callable[[Any], str]:
    """Public alias for the snapshot-bound body builder (tests exercise it
    directly to prove the binding rejects a drifted gate input).
    """
    return _make_snapshot_bound_body_builder(snapshot)


# ---------------------------------------------------------------------------
# Public composer
# ---------------------------------------------------------------------------


def _rejected(
    *, request: Stage30_11_13RevalidationRequest, reason: str
) -> Stage30_11_13ComposeResult:
    return Stage30_11_13ComposeResult(
        decision=COMPOSE_DECISION_REJECTED,
        reason=reason,
        token_mint=request.token_mint,
        candidate_id=request.candidate_id,
        created_at_utc=request.created_at_utc,
    )


def compose_no_send_dispatch(
    request: Stage30_11_13RevalidationRequest,
    *,
    ath_transport: object,
    ath_endpoint_secret: object,
    now_utc: object,
    transport_client: Stage30_11_5RecordingFakeTransportClient,
    now_seconds: object,
    ath_timeout_seconds: int = 10,
) -> Stage30_11_13ComposeResult:
    """Compose ONE no-send dispatch from ONE immutable revalidation snapshot.

    Internally instantiates the committed Stage 30.11.11 migration-anchored ATH
    source over the INJECTED ``ath_transport`` + ``ath_endpoint_secret`` +
    ``now_utc`` -- there is NO generic ``ath_context_source`` seam, so an old
    sliding source can never be wired. Fails closed (returns a ``REJECTED``
    result; never raises) on every invalid request / unresolved ATH / missing
    ATH MC / non-eligible tier / enrichment failure / gate skip. Dispatches ONLY
    through the committed Stage 30.11.5 bounded runner with the injected
    recording FAKE transport client; a non-fake client fails closed first.

    Pure / deterministic apart from the injected fake client's recording side
    effects + the injected fake ATH transport's behavior; reads no env, no
    network, no wall clock; sends no Discord, reserves no real dispatch, writes
    no file.
    """
    # ---- 0. Fake-transport-only: a non-fake client fails closed first ----
    if not isinstance(
        transport_client, Stage30_11_5RecordingFakeTransportClient
    ):
        return _rejected(
            request=request, reason=COMPOSE_REJECTED_NON_FAKE_TRANSPORT
        )

    # ---- 1. Validate the request (fail closed on a non-positive / malformed
    #         price / market cap, a blank mint, or a missing migration anchor) -
    if not isinstance(request, Stage30_11_13RevalidationRequest):
        return Stage30_11_13ComposeResult(
            decision=COMPOSE_DECISION_REJECTED,
            reason=COMPOSE_REJECTED_INVALID_REQUEST,
            token_mint="",
            candidate_id="",
            created_at_utc="",
        )
    if not _is_nonblank(request.token_mint) or not _is_nonblank(
        request.candidate_id
    ):
        return _rejected(
            request=request, reason=COMPOSE_REJECTED_INVALID_REQUEST
        )
    if request.migration_confirmed is not True or not _is_nonblank(
        request.migration_time_utc
    ):
        return _rejected(
            request=request, reason=COMPOSE_REJECTED_INVALID_REQUEST
        )
    current_price = _coerce_positive_decimal(request.current_price)
    current_market_cap = _coerce_positive_decimal(
        request.current_market_cap_usd
    )
    if current_price is None or current_market_cap is None:
        return _rejected(
            request=request, reason=COMPOSE_REJECTED_INVALID_REQUEST
        )

    # ---- 2. Build the committed Stage 30.11.11 migration-anchored ATH source -
    ath_source = build_migration_anchored_ath_context_source(
        transport=ath_transport,
        endpoint_secret=ath_endpoint_secret,
        timeout_seconds=ath_timeout_seconds,
        now_utc=now_utc,
    )
    # Defense in depth: the composer ALWAYS builds the anchored source itself,
    # so this can only be the committed type. A guard makes the enforcement
    # explicit + test-pinnable.
    if not isinstance(
        ath_source, Stage30_11_11MigrationAnchoredAthContextSource
    ):
        return _rejected(
            request=request, reason=COMPOSE_REJECTED_ATH_SOURCE_NOT_ANCHORED
        )

    # ---- 3. Read the migration-anchored ATH ONCE (fail closed unless
    #         RESOLVED + PRESENT + post-migration verified + drawdown + price) -
    anchored = ath_source.resolve_anchored_ath(
        request.token_mint, request.migration_time_utc
    )
    if not getattr(anchored, "resolved", False):
        return _rejected(
            request=request, reason=COMPOSE_REJECTED_ATH_NOT_RESOLVED
        )
    anchored_drawdown = _coerce_finite_decimal(
        getattr(anchored, "drawdown_from_ath", None)
    )
    if anchored_drawdown is None:
        return _rejected(
            request=request, reason=COMPOSE_REJECTED_MISSING_DRAWDOWN
        )
    ath_price = _coerce_positive_decimal(getattr(anchored, "ath_value", None))
    if ath_price is None:
        return _rejected(
            request=request, reason=COMPOSE_REJECTED_MISSING_ATH_PRICE
        )

    # ---- 4. Resolve the SAME source through the committed Stage 30.11.10
    #         resolver + cross-check (no arbitrary duck-typed source) ----
    migration_anchor = _ComposerMigrationAnchor(
        token_mint=request.token_mint,
        migration_event_time_utc=request.migration_time_utc,
        source_ref=request.migration_source,
    )
    ath_resolver = build_ath_resolver(
        migration_resolver=_anchor_resolver(migration_anchor),
        ath_context_source=ath_source,
    )
    base_candidate = {
        "candidate_id": request.candidate_id,
        "token_mint": request.token_mint,
        "pair_type": _PAIR_TYPE_SOL,
        "source_ref": request.migration_source,
        "created_at_utc": request.created_at_utc,
    }
    ath_resolution = ath_resolver(base_candidate)
    if not (
        getattr(ath_resolution, "present", False) is True
        and getattr(ath_resolution, "fresh", False) is True
        and getattr(ath_resolution, "post_migration_ath_verified", False)
        is True
    ):
        return _rejected(
            request=request, reason=COMPOSE_REJECTED_ATH_NOT_RESOLVED
        )
    resolver_drawdown = _coerce_finite_decimal(
        getattr(ath_resolution, "drawdown_from_ath", None)
    )
    if resolver_drawdown is None:
        return _rejected(
            request=request, reason=COMPOSE_REJECTED_MISSING_DRAWDOWN
        )
    if resolver_drawdown != anchored_drawdown:
        return _rejected(
            request=request, reason=COMPOSE_REJECTED_ATH_RESOLUTION_MISMATCH
        )

    # ---- 5. Classify the tier from the committed Stage 30.1 brain ----
    migration_record = _build_present_migration_record(
        token_mint=request.token_mint,
        migration_time_utc=request.migration_time_utc,
        observed_at_utc=request.created_at_utc,
    )
    tier_decision = decide_tier(
        ath_record=getattr(anchored, "reading", None),
        migration_record=migration_record,
        basis=BASIS_PRICE,
        created_at_utc=request.created_at_utc,
        candidate_id=request.candidate_id,
        mint=request.token_mint,
    )
    tier_token = tier_decision.tier_token
    if tier_token == TIER_TOKEN_TIER_UNKNOWN:
        return _rejected(
            request=request, reason=COMPOSE_REJECTED_TIER_NOT_ELIGIBLE
        )

    # ---- 6. Compute the ATH market cap in committed code (fail closed) ----
    ath_market_cap_display = _compute_ath_market_cap_display(
        current_market_cap_usd=current_market_cap,
        current_price=current_price,
        ath_price=ath_price,
    )
    if ath_market_cap_display is None:
        return _rejected(
            request=request, reason=COMPOSE_REJECTED_ATH_MC_UNAVAILABLE
        )

    # ---- 7. Build the ONE immutable snapshot ----
    try:
        market_cap_display = format_usd_compact(
            format(current_market_cap, "f")
        )
    except ValueError:
        return _rejected(
            request=request, reason=COMPOSE_REJECTED_INVALID_REQUEST
        )
    liquidity_decimal = _coerce_finite_decimal(request.liquidity_usd)
    liquidity_display: Optional[str]
    if liquidity_decimal is None:
        liquidity_display = None
    else:
        try:
            liquidity_display = format_usd_compact(
                format(liquidity_decimal, "f")
            )
        except ValueError:
            liquidity_display = None

    binding_key = Stage30_11_13GateBindingKey(
        token_mint=request.token_mint,
        tier_token=tier_token,
        drawdown_from_ath=anchored_drawdown,
        current_market_cap_usd=current_market_cap,
        migration_status=_CONTEXT_STATUS_PRESENT,
        ath_status=_CONTEXT_STATUS_PRESENT,
        post_migration_ath_verified=True,
        created_at_utc=request.created_at_utc,
    )
    snapshot = Stage30_11_13ComposedSnapshot(
        token_mint=request.token_mint,
        candidate_id=request.candidate_id,
        symbol_or_name=request.symbol_or_name,
        created_at_utc=request.created_at_utc,
        snapshot_id=_snapshot_id(request, tier_token, anchored_drawdown),
        tier_token=tier_token,
        drawdown_from_ath=anchored_drawdown,
        current_market_cap_usd=current_market_cap,
        migration_status=_CONTEXT_STATUS_PRESENT,
        ath_status=_CONTEXT_STATUS_PRESENT,
        market_context_status=_CONTEXT_STATUS_PRESENT,
        post_migration_ath_verified=True,
        current_price=request.current_price,
        ath_price=format(ath_price, "f"),
        liquidity_usd=request.liquidity_usd,
        migration_confirmed=True,
        migration_time_utc=request.migration_time_utc,
        migration_source=request.migration_source,
        age_display=request.age_display,
        basis_display=BASIS_PRICE,
        market_cap_display=market_cap_display,
        liquidity_display=liquidity_display,
        ath_market_cap_display=ath_market_cap_display,
        absolute_drawdown=format(anchored_drawdown, "f"),
        fractional_drop_pct=_fractional_drop_display(
            drawdown=anchored_drawdown, ath_value=ath_price
        ),
        tier_band_display=None,
        ath_source_stage=STAGE30_11_13_ATH_SOURCE_STAGE,
        time_from_unix=getattr(anchored, "time_from_unix", None),
        time_to_unix=getattr(anchored, "time_to_unix", None),
        ohlcv_type=getattr(anchored, "ohlcv_type", None),
        span_seconds=getattr(anchored, "span_seconds", None),
        ath_source_ref=request.migration_source,
        gate_binding_key=binding_key,
    )

    # ---- 8. Derive the committed Stage 30.11.7 enriched candidate FROM the
    #         snapshot (its ATH dimension is the SAME committed 30.11.10 ->
    #         30.11.11 resolution) ----
    enrichment = enrich_harvested_candidate(
        base_candidate,
        market_context_resolver=_market_resolver(snapshot),
        tier_resolver=_tier_resolver(snapshot),
        migration_resolver=_migration_resolver(),
        ath_resolver=_ath_resolution_resolver(ath_resolution),
        created_at_utc=request.created_at_utc,
    )
    if (
        getattr(enrichment, "enrichment_decision", None)
        != ENRICH_DECISION_ENRICHED
        or getattr(enrichment, "enriched_candidate", None) is None
    ):
        return _rejected(
            request=request, reason=COMPOSE_REJECTED_ENRICHMENT_FAILED
        )

    # ---- 9. Build the snapshot-bound body builder (renders once; a Stage
    #         30.12 fail-closed surfaces HERE, before the runner) ----
    try:
        bound_body_builder = _make_snapshot_bound_body_builder(snapshot)
    except Stage30_12PhoenixOperatorPingError:
        return _rejected(
            request=request, reason=COMPOSE_REJECTED_BODY_BUILD_FAILED
        )

    # ---- 10. Dispatch through the committed Stage 30.11.5 bounded runner with
    #          the injected recording FAKE transport (no real send) ----
    run_result = run_stage30_11_5_bounded_live_runner(
        (enrichment.enriched_candidate,),
        transport_client=transport_client,
        now_seconds=now_seconds,
        compact_body_builder=bound_body_builder,
        created_at_utc=request.created_at_utc,
    )
    summary = getattr(run_result, "summary", None)
    if (
        getattr(summary, "gate_passed", 0) < 1
        or getattr(summary, "dispatch_accepted", 0) < 1
    ):
        return Stage30_11_13ComposeResult(
            decision=COMPOSE_DECISION_REJECTED,
            reason=COMPOSE_REJECTED_GATE_DID_NOT_PASS,
            token_mint=request.token_mint,
            candidate_id=request.candidate_id,
            created_at_utc=request.created_at_utc,
            snapshot=snapshot,
            run_result=run_result,
            transport_attempts=getattr(transport_client, "attempted", 0),
            transport_accepts=getattr(transport_client, "accepted", 0),
        )

    dispatched_body = (
        transport_client.bodies[-1] if transport_client.bodies else None
    )
    return Stage30_11_13ComposeResult(
        decision=COMPOSE_DECISION_DISPATCHED,
        reason=COMPOSE_REASON_NO_SEND_DISPATCH_RECORDED,
        token_mint=request.token_mint,
        candidate_id=request.candidate_id,
        created_at_utc=request.created_at_utc,
        snapshot=snapshot,
        run_result=run_result,
        transport_attempts=getattr(transport_client, "attempted", 0),
        transport_accepts=getattr(transport_client, "accepted", 0),
        dispatched_body=dispatched_body,
    )


# ---------------------------------------------------------------------------
# Internal resolver closures (snapshot-bound; each duck-typed for its seam)
# ---------------------------------------------------------------------------


def _is_nonblank(value: object) -> bool:
    return isinstance(value, str) and value.strip() != ""


def _snapshot_id(
    request: Stage30_11_13RevalidationRequest,
    tier_token: str,
    drawdown: Decimal,
) -> str:
    """A deterministic opaque snapshot id (no clock / no random); binds the
    identity + the decision scalars + the injected timestamp.
    """
    return (
        f"{request.token_mint}|{tier_token}|{format(drawdown, 'f')}"
        f"|{request.created_at_utc}"
    )


def _anchor_resolver(
    anchor: _ComposerMigrationAnchor,
) -> Callable[[Any], _ComposerMigrationAnchor]:
    def _resolve(_base: Any) -> _ComposerMigrationAnchor:
        return anchor

    return _resolve


def _market_resolver(
    snapshot: Stage30_11_13ComposedSnapshot,
) -> Callable[[Any], Stage30_11_7MarketContextResolution]:
    def _resolve(_base: Any) -> Stage30_11_7MarketContextResolution:
        return Stage30_11_7MarketContextResolution(
            present=True,
            current_market_cap_usd=format(
                snapshot.current_market_cap_usd, "f"
            ),
            source_ref=snapshot.ath_source_ref,
        )

    return _resolve


def _tier_resolver(
    snapshot: Stage30_11_13ComposedSnapshot,
) -> Callable[[Any], Stage30_11_7TierResolution]:
    def _resolve(_base: Any) -> Stage30_11_7TierResolution:
        return Stage30_11_7TierResolution(tier_hint=snapshot.tier_token)

    return _resolve


def _migration_resolver() -> Callable[[Any], Stage30_11_7MigrationResolution]:
    def _resolve(_base: Any) -> Stage30_11_7MigrationResolution:
        return Stage30_11_7MigrationResolution(confirmed=True)

    return _resolve


def _ath_resolution_resolver(
    resolution: Any,
) -> Callable[[Any], Any]:
    """Return the committed Stage 30.11.10 resolution (already verified against
    the Stage 30.11.11 source) verbatim for the Stage 30.11.7 ATH seam -- so the
    enriched candidate's drawdown is the SAME committed value, not a re-fetch.
    """

    def _resolve(_base: Any) -> Any:
        return resolution

    return _resolve


__all__ = (
    "STAGE30_11_13_MINOR_VERSION",
    "STAGE30_11_13_COMPOSE_SCHEMA_VERSION",
    "STAGE30_11_13_ATH_SOURCE_STAGE",
    "COMPOSE_DECISION_DISPATCHED",
    "COMPOSE_DECISION_REJECTED",
    "STAGE30_11_13_COMPOSE_DECISIONS",
    "COMPOSE_REASON_NO_SEND_DISPATCH_RECORDED",
    "COMPOSE_REJECTED_INVALID_REQUEST",
    "COMPOSE_REJECTED_ATH_SOURCE_NOT_ANCHORED",
    "COMPOSE_REJECTED_NON_FAKE_TRANSPORT",
    "COMPOSE_REJECTED_ATH_NOT_RESOLVED",
    "COMPOSE_REJECTED_MISSING_DRAWDOWN",
    "COMPOSE_REJECTED_MISSING_ATH_PRICE",
    "COMPOSE_REJECTED_ATH_RESOLUTION_MISMATCH",
    "COMPOSE_REJECTED_TIER_NOT_ELIGIBLE",
    "COMPOSE_REJECTED_ATH_MC_UNAVAILABLE",
    "COMPOSE_REJECTED_ENRICHMENT_FAILED",
    "COMPOSE_REJECTED_GATE_DID_NOT_PASS",
    "COMPOSE_REJECTED_GATE_BODY_MISMATCH",
    "COMPOSE_REJECTED_BODY_BUILD_FAILED",
    "STAGE30_11_13_COMPOSE_REASONS",
    "Stage30_11_13ComposerError",
    "Stage30_11_13RevalidationRequest",
    "Stage30_11_13GateBindingKey",
    "Stage30_11_13ComposedSnapshot",
    "Stage30_11_13ComposeResult",
    "make_snapshot_bound_body_builder",
    "compose_no_send_dispatch",
)

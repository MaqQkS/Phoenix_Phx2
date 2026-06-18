"""Stage 30.14.0 real-discovery-replay -> shadow-dispatch orchestrator.

Build #26, substage 30.14.0. Offline / SYNTHETIC only. A thin composition that proves an
ALREADY-DISCOVERED migration evidence record -- REPLAYED from memory, NEVER a live capture
-- flows through the committed Stage 30.13.0 auto-seeder and the committed Stage 30.11.23
-> 30.11.22 recheck / fake-send chain to a RECORDED would-send (a FAKE dispatch), NEVER a
real send, with the dispatched mint tracing back to the replayed discovered mint:

    an INJECTED Stage30_14ReplayDiscoverySource (a deterministic in-memory replay of
    SYNTHETIC migration evidence records) + INJECTED fake price / market-context / ATH
    sources -- EACH provider source MUST be a fake-only marked component
    (``Stage30_14FakeOnly``); a non-fake / live-looking injected component is rejected with
    a ``Stage30_14ShadowDispatchError`` BEFORE anything is driven
      -> the committed Stage 30.13.0 auto-seeder
         (``build_seeded_watchlist_from_ws_discovery``, ``max_seed=1``)
         -> the seeded sanitized summaries (the watchlist)
      -> the committed Stage 30.11.23 fake real-fed dry-run proof
         (``run_stage30_11_23_fake_real_fed_dry_run_proof``) -- which ALWAYS builds a FRESH
         in-memory dedupe ledger + a FRESH recording FAKE dispatch client internally
      -> a ``Stage30_14ShadowDispatchResult`` carrying the auto-seed result, the dry-run
         result, and the Build 26.0 dispatch trace.

Hardening (mirrors the committed Stage 30.13.4 end-to-end proof): the public orchestrator
exposes NO dispatch-client and NO durable-ledger injection knob at all -- there is no
``ledger`` and no ``transport_client`` parameter, so a replayed candidate can NEVER reach
a non-fake dispatch client or a durable ledger through accidental caller injection; the
downstream proof always constructs a fresh in-memory ledger + a fresh recording FAKE
client. The injected provider sources (price / market-context / ATH transport) MUST carry
the ``Stage30_14FakeOnly`` marker -- a live-capable object that does not is refused before
the seed -> recheck -> fake-dispatch chain runs.

This orchestrator opens NO socket, reads NO env, reads NO wall clock, sends NO private
message, calls NO real dispatch, calls NO Stage 30.11.16 real-send guard, touches NO
durable ledger, and writes NO file. Build 26.0 is SYNTHETIC: pointing the same committed
replay seam at a real, evidence-bearing artifact (Build 26.1) is a SEPARATE step, BLOCKED
until an evidence-preserving capture exists.

Discipline:

  * Stdlib only (``dataclasses`` / ``typing``).
  * Imports ONLY the Stage 30.14.0 replay-source + models siblings, the committed Stage
    30.13.0 auto-seeder, and the committed Stage 30.11.23 fake real-fed dry-run proof. No
    Stage 21-29 surface directly (the discovery currency is reached transitively through
    the committed auto-seeder); no transport / dispatch / runner / durable-ledger /
    real-send-guard import.
  * No ``os.environ`` / ``os.getenv`` access; no env read.
  * No network, no socket (the replay source + every provider source are injected); no
    database, no compression, no durable ledger, no filesystem write.
  * No live provider, transport-destination, url, or host reference; no wallet /
    signing / trading surface; no public / subscriber routing.
  * No PHX1 import. No ``time`` / ``datetime`` import; the clock + every timestamp are
    caller-injected.
  * No module-level Call node (no implicit I/O at import time).
"""

from __future__ import annotations

from typing import Tuple

from PHX2.stage30.stage30_11_23_fake_migration_evidence_candidate_bridge_proof import (
    run_stage30_11_23_fake_real_fed_dry_run_proof,
)
from PHX2.stage30.stage30_13_0_ws_auto_seeder import (
    build_seeded_watchlist_from_ws_discovery,
)
from PHX2.stage30.stage30_14_0_replay_discovery_source import (
    Stage30_14ReplayDiscoverySource,
)
from PHX2.stage30.stage30_14_0_replay_discovery_models import (
    STAGE30_14_MAX_FAKE_DISPATCHES,
    STAGE30_14_MAX_RECHECKS,
    STAGE30_14_MAX_SEED,
    STAGE30_14_REDACTED_UNSAFE_ID,
    STAGE30_14_REDACTION_STATUS_REDACTED,
    STAGE30_14_REDACTION_STATUS_VIOLATION,
    Stage30_14DispatchTrace,
    Stage30_14ShadowDispatchResult,
    is_locked_cap,
    is_safe_echo_id,
)


# ---------------------------------------------------------------------------
# Redaction self-scan needles (split-literal so this module source carries no bare
# needle -- in particular no bare provider name and no contiguous transport-scheme
# separator). Mirrors the committed Stage 30.13.0 / 30.11.23 scan BY VALUE.
# ---------------------------------------------------------------------------


_REDACTION_SCHEME_SEP: str = ":" + "/" + "/"
_REDACTION_NEEDLES: Tuple[str, ...] = (
    "disc" + "ord.com",
    "disc" + "ordapp.com",
    "/web" + "hooks/",
    "web" + "hook url",
    "ap" + "i_key",
    "ap" + "i key",
    "x-api-" + "key",
    "x-" + "token",
    "b" + "earer",
    "author" + "ization",
    "raw" + "_body",
    "response" + "_body",
    "head" + "ers",
)


# ---------------------------------------------------------------------------
# Fake-only marker + closed-set guard reason tokens + the guard error
# ---------------------------------------------------------------------------
#
# The public orchestrator accepts an injected price / market-context / ATH source ONLY
# when each is a fake-only marked component -- a test / in-memory fake inherits this
# marker; NO real provider source does. So a live-capable object can never be accidentally
# injected into the Build 26.0 synthetic proof.


class Stage30_14FakeOnly:
    """Marker base class for the in-memory / fake provider components the public Stage
    30.14.0 orchestrator accepts as injected inputs.

    A fake price source / market-context source / ATH transport built by the offline proof
    tests inherits this marker. The orchestrator enforces it on every injected provider
    source BEFORE driving the seed -> recheck -> fake-dispatch chain, so a live-capable
    object can never be accidentally injected. Empty by design -- it carries no behavior,
    only identity.
    """


STAGE30_14_REASON_INVALID_MAX_SEED: str = "INVALID_MAX_SEED"
STAGE30_14_REASON_INVALID_MAX_RECHECKS: str = "INVALID_MAX_RECHECKS"
STAGE30_14_REASON_INVALID_MAX_FAKE_DISPATCHES: str = (
    "INVALID_MAX_FAKE_DISPATCHES"
)
STAGE30_14_REASON_NOT_A_REPLAY_SOURCE: str = "NOT_A_REPLAY_SOURCE"
STAGE30_14_REASON_NON_FAKE_PRICE_SOURCE: str = "NON_FAKE_PRICE_SOURCE"
STAGE30_14_REASON_NON_FAKE_MARKET_CONTEXT_SOURCE: str = (
    "NON_FAKE_MARKET_CONTEXT_SOURCE"
)
STAGE30_14_REASON_NON_FAKE_ATH_TRANSPORT: str = "NON_FAKE_ATH_TRANSPORT"


class Stage30_14ShadowDispatchError(Exception):
    """Raised when the public Stage 30.14.0 orchestrator is called with an out-of-bounds
    locked cap, a non-replay-source discovery, or a non-fake (live-capable) provider
    component.

    Carries ONLY a closed-set reason token (one of the ``STAGE30_14_REASON_*`` values);
    never a raw object repr, payload, url, or secret. The orchestrator fails closed on this
    error BEFORE driving the seed -> recheck -> fake-dispatch chain, so a misconfigured
    call can never reach a seeder, a recheck, or a dispatch surface.
    """

    def __init__(self, reason: str) -> None:
        self.reason: str = reason
        super().__init__(
            f"Stage 30.14.0 shadow-dispatch error: reason={reason!r}"
        )


def _require_fake_only(component: object, reason: str) -> None:
    """Raise ``Stage30_14ShadowDispatchError(reason)`` unless ``component`` is a fake-only
    marked component. Pure guard; no I/O.
    """
    if not isinstance(component, Stage30_14FakeOnly):
        raise Stage30_14ShadowDispatchError(reason)


# ---------------------------------------------------------------------------
# Pure safe-shape echo + redaction self-scan
# ---------------------------------------------------------------------------


def _safe_echo(value: object) -> str:
    """Echo ``value`` only when it is a safe-echo token; else a safe placeholder.

    ``None`` / ``""`` -> ``""``; a non-string or an unsafe string ->
    ``STAGE30_14_REDACTED_UNSAFE_ID``; a safe-echo token -> itself. Mirrors the committed
    Stage 30.13.0 ``_safe_echo`` BY VALUE. Pure / total.
    """
    if value is None:
        return ""
    if not isinstance(value, str):
        return STAGE30_14_REDACTED_UNSAFE_ID
    if value == "":
        return ""
    return value if is_safe_echo_id(value) else STAGE30_14_REDACTED_UNSAFE_ID


def _strings_redaction_safe(values: Tuple[str, ...]) -> bool:
    """Return ``True`` iff no string carries a transport-scheme separator or a forbidden
    url / secret needle. Pure / total.
    """
    for text in values:
        if not isinstance(text, str):
            continue
        lowered = text.lower()
        if _REDACTION_SCHEME_SEP in lowered:
            return False
        for needle in _REDACTION_NEEDLES:
            if needle in lowered:
                return False
    return True


# ---------------------------------------------------------------------------
# Pure trace builder
# ---------------------------------------------------------------------------


def _first_seeded_mint(seed_result: object) -> str:
    """Read the first seeded summary's ``token_mint`` (safe-echoed), or ``""``. Pure."""
    summaries = getattr(seed_result, "seeded_summaries", ())
    for summary in summaries:
        return _safe_echo(getattr(summary, "token_mint", None))
    return ""


def _first_dispatched_mint(dry_run: object) -> str:
    """Read the first recorded would-send mint (safe-echoed), or ``""``. Pure."""
    client = getattr(dry_run, "client", None)
    token_mints = getattr(client, "token_mints", None)
    if not token_mints:
        return ""
    for mint in token_mints:
        return _safe_echo(mint)
    return ""


def _build_trace(
    seed_result: object, dry_run: object
) -> Stage30_14DispatchTrace:
    """Build the redaction-safe dispatch trace from the composed committed results. Pure;
    no I/O.
    """
    discovered_mint = _first_seeded_mint(seed_result)
    dispatched_mint = _first_dispatched_mint(dry_run)
    mint_traces_through = (
        discovered_mint != ""
        and discovered_mint != STAGE30_14_REDACTED_UNSAFE_ID
        and discovered_mint == dispatched_mint
    )

    seed_summary = getattr(seed_result, "summary", None)
    seeds_accepted = int(getattr(seed_summary, "accepted", 0) or 0)

    inputs = getattr(dry_run, "inputs", None)
    bridge_report = getattr(inputs, "report", None)
    rechecks_bridged = int(getattr(bridge_report, "bridged", 0) or 0)

    report = getattr(dry_run, "report", None)
    dispatched = int(getattr(report, "dispatched", 0) or 0)
    would_send_recorded = int(getattr(report, "would_send_recorded", 0) or 0)

    attestation = getattr(report, "attestation", None)
    real_send_performed = bool(
        getattr(attestation, "real_send_performed", True)
    )
    real_send_guard_invoked = bool(
        getattr(attestation, "real_send_guard_invoked", True)
    )
    transport_client_kind = _safe_echo(
        getattr(attestation, "transport_client_kind", None)
    )
    ledger_kind = _safe_echo(getattr(attestation, "ledger_kind", None))

    redaction_safe = _strings_redaction_safe(
        (
            discovered_mint,
            dispatched_mint,
            transport_client_kind,
            ledger_kind,
        )
    )
    redaction_status = (
        STAGE30_14_REDACTION_STATUS_REDACTED
        if redaction_safe
        else STAGE30_14_REDACTION_STATUS_VIOLATION
    )

    return Stage30_14DispatchTrace(
        discovered_mint=discovered_mint,
        dispatched_mint=dispatched_mint,
        mint_traces_through=mint_traces_through,
        seeds_accepted=seeds_accepted,
        rechecks_bridged=rechecks_bridged,
        dispatched=dispatched,
        would_send_recorded=would_send_recorded,
        real_send_performed=real_send_performed,
        real_send_guard_invoked=real_send_guard_invoked,
        transport_client_kind=transport_client_kind,
        ledger_kind=ledger_kind,
        redaction_status=redaction_status,
    )


# ---------------------------------------------------------------------------
# Public orchestrator
# ---------------------------------------------------------------------------


def run_stage30_14_0_real_discovery_to_shadow_dispatch(
    replay_source: object,
    *,
    price_source: object,
    market_context_source: object,
    ath_transport: object,
    ath_endpoint_secret: object,
    now_utc: object,
    now_seconds: object,
    created_at_utc: str,
    max_seed: int = STAGE30_14_MAX_SEED,
    max_rechecks: int = STAGE30_14_MAX_RECHECKS,
    max_fake_dispatches: int = STAGE30_14_MAX_FAKE_DISPATCHES,
) -> Stage30_14ShadowDispatchResult:
    """Replay an injected synthetic discovery through the committed auto-seeder + the
    committed recheck / fake-send chain, returning the seed result + dry-run result + the
    Build 26.0 dispatch trace.

    Fail closed FIRST: the locked Build 26.0 caps (``max_seed`` / ``max_rechecks`` /
    ``max_fake_dispatches`` -- each locked to 1) are validated, then ``replay_source`` MUST
    be a ``Stage30_14ReplayDiscoverySource`` and ``price_source`` /
    ``market_context_source`` / ``ath_transport`` MUST each be a fake-only marked component
    (``Stage30_14FakeOnly``); any out-of-bounds cap, non-replay-source, or non-fake
    component is rejected with ``Stage30_14ShadowDispatchError`` BEFORE anything is driven.

    There is NO ``ledger`` and NO ``transport_client`` parameter -- the committed Stage
    30.11.23 proof ALWAYS builds a fresh in-memory dedupe ledger + a fresh recording FAKE
    dispatch client, so a replayed candidate can never reach a non-fake dispatch client or
    a durable ledger through accidental caller injection.

    Pure / deterministic apart from the injected (fake) sources' own behavior; reads no
    env, no wall clock, no network; builds no real transport, reserves no real dispatch,
    sends no message, writes no file, runs no daemon / ``while`` loop. The seeded summaries
    (from the committed auto-seeder) are fed VERBATIM into the committed Stage 30.11.23 fake
    real-fed dry-run proof -- so the dispatched mint traces to the replayed discovered mint,
    never a hand-fed mint.
    """
    # Fail closed FIRST: locked caps, then the replay source, then every provider source.
    if not is_locked_cap(max_seed, STAGE30_14_MAX_SEED):
        raise Stage30_14ShadowDispatchError(STAGE30_14_REASON_INVALID_MAX_SEED)
    if not is_locked_cap(max_rechecks, STAGE30_14_MAX_RECHECKS):
        raise Stage30_14ShadowDispatchError(
            STAGE30_14_REASON_INVALID_MAX_RECHECKS
        )
    if not is_locked_cap(max_fake_dispatches, STAGE30_14_MAX_FAKE_DISPATCHES):
        raise Stage30_14ShadowDispatchError(
            STAGE30_14_REASON_INVALID_MAX_FAKE_DISPATCHES
        )
    if not isinstance(replay_source, Stage30_14ReplayDiscoverySource):
        raise Stage30_14ShadowDispatchError(
            STAGE30_14_REASON_NOT_A_REPLAY_SOURCE
        )
    _require_fake_only(price_source, STAGE30_14_REASON_NON_FAKE_PRICE_SOURCE)
    _require_fake_only(
        market_context_source,
        STAGE30_14_REASON_NON_FAKE_MARKET_CONTEXT_SOURCE,
    )
    _require_fake_only(
        ath_transport, STAGE30_14_REASON_NON_FAKE_ATH_TRANSPORT
    )

    # Discovery -> auto-seed (committed Stage 30.13.0; AT MOST max_seed seeds).
    seed_result = build_seeded_watchlist_from_ws_discovery(
        replay_source,
        created_at_utc=created_at_utc,
        max_seed=max_seed,
    )

    # Seeded summaries -> committed recheck / fake-send chain. No ``ledger`` /
    # ``transport_client`` are threaded through: the committed Stage 30.11.23 proof builds a
    # FRESH in-memory ledger + a FRESH recording FAKE client. ``max_rechecks`` bounds the
    # bridged summaries; with a single seeded summary the recorded would-send is bounded to
    # one (max_fake_dispatches) by construction.
    dry_run = run_stage30_11_23_fake_real_fed_dry_run_proof(
        seed_result.seeded_summaries,
        price_source=price_source,
        market_context_source=market_context_source,
        ath_transport=ath_transport,
        ath_endpoint_secret=ath_endpoint_secret,
        now_utc=now_utc,
        now_seconds=now_seconds,
        created_at_utc=created_at_utc,
        max_summaries=max_rechecks,
    )

    trace = _build_trace(seed_result, dry_run)
    return Stage30_14ShadowDispatchResult(
        seed_result=seed_result,
        dry_run=dry_run,
        trace=trace,
    )


__all__ = (
    "Stage30_14FakeOnly",
    "STAGE30_14_REASON_INVALID_MAX_SEED",
    "STAGE30_14_REASON_INVALID_MAX_RECHECKS",
    "STAGE30_14_REASON_INVALID_MAX_FAKE_DISPATCHES",
    "STAGE30_14_REASON_NOT_A_REPLAY_SOURCE",
    "STAGE30_14_REASON_NON_FAKE_PRICE_SOURCE",
    "STAGE30_14_REASON_NON_FAKE_MARKET_CONTEXT_SOURCE",
    "STAGE30_14_REASON_NON_FAKE_ATH_TRANSPORT",
    "Stage30_14ShadowDispatchError",
    "run_stage30_14_0_real_discovery_to_shadow_dispatch",
)

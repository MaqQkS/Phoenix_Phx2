"""Stage 30.14.1 evidence replay verifier.

Build #26, substage 30.14.1. The strict, OFFLINE driver that takes a Stage 30.14.1
``Stage30_14_1EvidenceLoadResult`` (the loader sibling's output -- reconstructed evidence
records + their persisted attestations) and replays EACH accepted record through the
committed Stage 30.14.0 replay -> shadow-dispatch path to a RECORDED would-send (a FAKE
dispatch), NEVER a real send, proving:

  * the discovered (reconstructed) mint flows seed -> recheck -> FAKE dispatch
    (``dispatched == 1`` per record);
  * the dispatched mint traces back to the discovered mint
    (``trace.mint_traces_through is True``);
  * ``real_send_performed is False`` and ``real_send_guard_invoked is False``;
  * the committed chain's RE-DERIVED sanitized summary EQUALS the persisted attestation the
    loader carried -- so the loader reconstructed the record faithfully (no fabrication),
    verified using ONLY the committed chain's own output.

Because the committed Stage 30.14.0 orchestrator is LOCKED to ``max_seed = max_rechecks =
max_fake_dispatches = 1`` (a single discovered mint per pass), the verifier drives ONE
committed pass PER accepted record (each over a single-record
``Stage30_14ReplayDiscoverySource``), bounded by ``max_replay``. The deterministic FAKE
price / market-context / ATH provider sources + clocks are CALLER-INJECTED (each a
``Stage30_14FakeOnly`` component built by the test) and forwarded VERBATIM to the committed
orchestrator -- so this verifier imports NO Birdeye / Stage 27 / Stage 28 / Stage 29.1-29.4
provider module, opens NO socket, and the committed orchestrator (not this driver) enforces
the fake-only marker + the locked caps + the no-real-send attestation.

The verifier exposes NO ``ledger`` and NO ``transport_client`` knob (the committed Stage
30.11.23 proof always builds a fresh in-memory ledger + a fresh recording FAKE client); it
reads NO env, NO wall clock (``created_at_utc`` is injected), opens NO network, reserves NO
dispatch, sends NO message, touches NO durable ledger, writes NO file, runs NO daemon /
``while`` loop, and edits NO committed production file.

Discipline:

  * Stdlib only (``typing``) -- the strict Stage 30.14.1 tier (no filesystem / json /
    network / clock / env surface).
  * Imports ONLY the Stage 30.14.1 models sibling + the committed Stage 30.14.0
    shadow-dispatch orchestrator + the committed Stage 30.14.0 replay source. No Stage
    29.5 / Birdeye / Stage 27 / Stage 28 import (the committed Stage 29.5 record / projection
    are reached TRANSITIVELY through the committed orchestrator, never imported here); no
    durable-ledger / real-send-guard / Discord / transport import; no loader import (the
    filesystem stays in the loader tier).
  * No ``os.environ`` / ``os.getenv`` access; no env read.
  * No network, no socket; no database / compression; no filesystem surface.
  * No live provider, transport-destination, url, or host reference; no wallet / signing /
    trading surface; no public / subscriber routing.
  * No PHX1 import. No ``time`` / ``datetime`` import. No module-level Call node.
"""

from __future__ import annotations

from typing import Any, List, Tuple

from PHX2.stage30.stage30_14_0_real_discovery_to_shadow_dispatch import (
    run_stage30_14_0_real_discovery_to_shadow_dispatch,
)
from PHX2.stage30.stage30_14_0_replay_discovery_source import (
    Stage30_14ReplayDiscoverySource,
)
from PHX2.stage30.stage30_14_1_evidence_artifact_models import (
    STAGE30_14_1_DEFAULT_MAX_REPLAY,
    STAGE30_14_1_REDACTION_STATUS_REDACTED,
    STAGE30_14_1_REDACTION_STATUS_VIOLATION,
    VERIFY_ERROR_INVALID_MAX_REPLAY,
    VERIFY_ERROR_NOT_A_LOAD_RESULT,
    VERIFY_ERROR_TOO_MANY_REPLAY_RECORDS,
    Stage30_14_1EvidenceLoadResult,
    Stage30_14_1ReplayVerifyOutcome,
    Stage30_14_1ReplayVerifyResult,
    are_strings_redaction_safe,
    is_verify_error_reason,
    is_within_replay_cap,
    safe_echo,
)


# ---------------------------------------------------------------------------
# Closed-set verify error
# ---------------------------------------------------------------------------


class Stage30_14_1ReplayVerifyError(Exception):
    """Closed-set Stage 30.14.1 replay-verify error.

    Raised for a caller-shape failure the verifier cannot run with -- a ``load_result`` that
    is not a ``Stage30_14_1EvidenceLoadResult``, a ``max_replay`` outside the hard cap, or an
    accepted set larger than ``max_replay``. Carries ONLY a closed-set reason token; never a
    raw payload, mint, or secret value. A committed-orchestrator refusal (a non-fake provider
    source / an out-of-bounds locked cap) surfaces as the committed
    ``Stage30_14ShadowDispatchError`` instead and is NOT swallowed here.
    """

    def __init__(self, reason: str) -> None:
        if not is_verify_error_reason(reason):
            raise ValueError(
                "Stage30_14_1ReplayVerifyError reason must be a closed-set "
                f"token; got {reason!r}"
            )
        self.reason: str = reason
        super().__init__(
            f"Stage 30.14.1 replay-verify error: reason={reason!r}"
        )


# ---------------------------------------------------------------------------
# Pure round-trip + per-record outcome helpers
# ---------------------------------------------------------------------------


def _attestation_roundtrip_ok(seed_result: object, attestation: object) -> bool:
    """Return ``True`` iff the committed chain's RE-DERIVED sanitized summary equals the
    persisted attestation the loader carried.

    The committed Stage 30.13.0 auto-seeder re-projects the reconstructed record via the
    committed Stage 29.5.7 projection, so ``seeded_summaries[0]`` IS the committed chain's
    own re-derivation. Equality across all six summary fields proves faithful reconstruction
    (no fabrication). Pure / total; never raises (duck-typed reads).
    """
    summaries = getattr(seed_result, "seeded_summaries", ())
    if len(summaries) != 1:
        return False
    summary = summaries[0]
    return (
        getattr(summary, "token_mint", None) == attestation.token_mint
        and getattr(summary, "measurement_status", None)
        == attestation.measurement_status
        and getattr(summary, "migration_event_time_utc", None)
        == attestation.migration_event_time_utc
        and tuple(getattr(summary, "warnings", ()) or ())
        == tuple(attestation.warnings or ())
        and getattr(summary, "redaction_status", None)
        == attestation.redaction_status
        and getattr(summary, "source_ref", None) == attestation.source_ref
    )


def _verify_outcome(
    shadow_result: object, attestation: object
) -> Stage30_14_1ReplayVerifyOutcome:
    """Distil one per-record verify outcome from a committed shadow-dispatch result + the
    persisted attestation. Pure; no I/O.
    """
    trace = getattr(shadow_result, "trace", None)
    discovered_mint = safe_echo(getattr(trace, "discovered_mint", ""))
    roundtrip_ok = _attestation_roundtrip_ok(
        getattr(shadow_result, "seed_result", None), attestation
    )
    redaction_status = (
        STAGE30_14_1_REDACTION_STATUS_REDACTED
        if are_strings_redaction_safe((discovered_mint,))
        else STAGE30_14_1_REDACTION_STATUS_VIOLATION
    )
    return Stage30_14_1ReplayVerifyOutcome(
        token_mint=discovered_mint,
        seeds_accepted=int(getattr(trace, "seeds_accepted", 0) or 0),
        dispatched=int(getattr(trace, "dispatched", 0) or 0),
        would_send_recorded=int(
            getattr(trace, "would_send_recorded", 0) or 0
        ),
        mint_traces_through=bool(
            getattr(trace, "mint_traces_through", False)
        ),
        real_send_performed=bool(getattr(trace, "real_send_performed", True)),
        real_send_guard_invoked=bool(
            getattr(trace, "real_send_guard_invoked", True)
        ),
        attestation_roundtrip_ok=roundtrip_ok,
        redaction_status=redaction_status,
    )


# ---------------------------------------------------------------------------
# Public bounded replay verifier
# ---------------------------------------------------------------------------


def run_stage30_14_1_replay_verify(
    load_result: object,
    *,
    price_source: object,
    market_context_source: object,
    ath_transport: object,
    ath_endpoint_secret: object,
    now_utc: object,
    now_seconds: object,
    created_at_utc: str,
    max_replay: int = STAGE30_14_1_DEFAULT_MAX_REPLAY,
) -> Stage30_14_1ReplayVerifyResult:
    """Replay each accepted reconstructed record from ``load_result`` through the committed
    Stage 30.14.0 shadow-dispatch path (locked ``1/1/1``), one committed pass per record.

    Fail closed FIRST: ``load_result`` MUST be a ``Stage30_14_1EvidenceLoadResult``,
    ``max_replay`` MUST be within the hard replay cap, and the accepted set MUST NOT exceed
    ``max_replay`` -- each violation raises ``Stage30_14_1ReplayVerifyError`` BEFORE any
    committed pass runs. The injected price / market-context / ATH sources are forwarded
    VERBATIM; the committed orchestrator enforces the fake-only marker + the locked caps +
    the no-real-send attestation (a non-fake source surfaces its
    ``Stage30_14ShadowDispatchError``, not swallowed here).

    Returns a ``Stage30_14_1ReplayVerifyResult`` carrying the distilled per-record outcomes,
    the committed shadow-dispatch results, the aggregate counters/flags, and a combined
    redaction status. Reads no env, no wall clock (``created_at_utc`` injected), no network;
    reserves no dispatch, sends no message, writes no file, runs no daemon / ``while`` loop.
    """
    if not isinstance(load_result, Stage30_14_1EvidenceLoadResult):
        raise Stage30_14_1ReplayVerifyError(VERIFY_ERROR_NOT_A_LOAD_RESULT)
    if not is_within_replay_cap(max_replay):
        raise Stage30_14_1ReplayVerifyError(VERIFY_ERROR_INVALID_MAX_REPLAY)

    records = load_result.accepted_records
    attestations = load_result.accepted_attestations
    if len(records) > max_replay:
        raise Stage30_14_1ReplayVerifyError(
            VERIFY_ERROR_TOO_MANY_REPLAY_RECORDS
        )

    outcomes: List[Stage30_14_1ReplayVerifyOutcome] = []
    shadow_results: List[Any] = []
    for index, record in enumerate(records):
        attestation = attestations[index]
        replay_source = Stage30_14ReplayDiscoverySource((record,))
        shadow_result = run_stage30_14_0_real_discovery_to_shadow_dispatch(
            replay_source,
            price_source=price_source,
            market_context_source=market_context_source,
            ath_transport=ath_transport,
            ath_endpoint_secret=ath_endpoint_secret,
            now_utc=now_utc,
            now_seconds=now_seconds,
            created_at_utc=created_at_utc,
        )
        shadow_results.append(shadow_result)
        outcomes.append(_verify_outcome(shadow_result, attestation))

    records_replayed = len(outcomes)
    dispatched_total = sum(outcome.dispatched for outcome in outcomes)
    all_traced_through = all(
        outcome.mint_traces_through for outcome in outcomes
    )
    all_no_real_send = all(
        (not outcome.real_send_performed)
        and (not outcome.real_send_guard_invoked)
        for outcome in outcomes
    )
    all_roundtrip_ok = all(
        outcome.attestation_roundtrip_ok for outcome in outcomes
    )

    scanned: List[str] = [created_at_utc]
    for outcome in outcomes:
        scanned.append(outcome.token_mint)
    redaction_status = (
        STAGE30_14_1_REDACTION_STATUS_REDACTED
        if are_strings_redaction_safe(tuple(scanned))
        else STAGE30_14_1_REDACTION_STATUS_VIOLATION
    )

    return Stage30_14_1ReplayVerifyResult(
        outcomes=tuple(outcomes),
        shadow_results=tuple(shadow_results),
        records_replayed=records_replayed,
        dispatched_total=dispatched_total,
        all_traced_through=all_traced_through,
        all_no_real_send=all_no_real_send,
        all_roundtrip_ok=all_roundtrip_ok,
        redaction_status=redaction_status,
        created_at_utc=created_at_utc,
    )


__all__ = (
    "Stage30_14_1ReplayVerifyError",
    "run_stage30_14_1_replay_verify",
)

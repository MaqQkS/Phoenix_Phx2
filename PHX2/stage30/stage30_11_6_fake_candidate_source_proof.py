"""Stage 30.11.6 offline fake candidate source / harvest proof.

A pure, deterministic, fail-closed helper that PROVES the Stage 30.11.6 harvest
seam captures real-shaped assembled candidates -- WITHOUT invoking the old
ungated dispatch path -- and feeds them through the committed Stage 30.11.5
bounded runner so ONLY a PASS dip reaches the fake private transport, using
fakes / offline projections + an INJECTED fake assembler + an INJECTED fake record
flattener + the committed Stage 30.11.5 fake wiring proof (its INJECTED in-memory
recording FAKE transport client + injected fake clock) ONLY:

    a deterministic FIVE-event fake source
      -> the Stage 30.11.6 harvest adapter (driving the injected fake assembler +
         fake record flattener; NEVER constructing a transport / dispatch sink /
         runner)
        -> one non-dip + one bridge-suppressed + one Tier 1 dip event harvest into
           a Stage 30.11.5 flat projection
        -> one event whose assembler RAISES -> SKIPPED_ASSEMBLY_FAILED (no
           candidate)
        -> one event whose flattened fields omit a required field ->
           SKIPPED_PROJECTION_REJECTED (no candidate)
      -> the harvested ``candidate_source`` (three flat projections)
      -> the committed Stage 30.11.5 fake live wiring proof (the committed bounded
         runner -> committed Stage 30.11.2 seam -> committed Stage 30.11.1 bridge
         -> committed Stage 30.9.3 dip gate -> committed Stage 30.11.3 private sink
         -> Stage 30.11.5 transport adapter -> INJECTED recording FAKE transport
         client, reached for the dip ONLY)
      -> a ``(harvest_result, runner_result, transport_client)`` triple

So a baseline run harvests three of five events (skipping the failed assembly +
the rejected projection), and the committed runner over the three harvested
projections sees three candidates, bridges two, passes one dip gate, attempts +
accepts exactly one dispatch, and the recording fake client records EXACTLY one
would-deliver -- for the Tier 1 dip ONLY -- with NO real dispatch ever reserved,
NO Discord ever sent, and the OLD ungated dispatch path NEVER invoked (the injected
fake assembler's dispatch tripwire records zero calls; the harvest adapter
constructs no transport).

It is NOT a live runner driver, NOT a live provider run, NOT a Discord send, NOT a
real dispatch reservation, NOT a real transport, NOT a real candidate source, and
NOT a new readiness gate. It CONSTRUCTS no filesystem I/O, reads no environment,
opens no network connection, reads no wall clock (every clock is injected), runs no
daemon / ``while`` loop, and touches no Discord / live provider / real transport
path. The real committed assembler binding + the controlled live ceremony remain a
SEPARATE, explicitly operator-authorized step this slice does not build.

Discipline:

  * Stdlib only (``dataclasses`` / ``typing``).
  * Imports only the Stage 30.11.6 harvest-adapter + models siblings and the
    committed Stage 30.11.5 fake-live-wiring-proof sibling (for the committed
    bounded runner + the injected recording fake transport client + injected
    clock). No other PHX2 module; no Stage 21-29 (incl. the committed Stage 28.9
    live provider session adapter / the nested Stage 27 / 28 / 29 live candidate
    record) / Stage 30.3 / Stage 30.4 orchestrator / live runner / provider / real
    transport import. The projection adapter / harvest adapter / committed runner /
    committed sink are composed TRANSITIVELY through the committed siblings.
  * No ``os`` (NO env read), NO network, NO ``sqlite3``, NO ``zstd`` /
    compression, NO ``time`` / wall clock / random, NO direct filesystem
    primitive.
  * No top-level Call (no implicit I/O at import time).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from PHX2.stage30.stage30_11_5_fake_live_wiring_proof import (
    Stage30_11_5RecordingFakeTransportClient,
    run_stage30_11_5_fake_live_wiring_proof,
)
from PHX2.stage30.stage30_11_6_candidate_harvest_adapter import (
    harvest_live_candidates,
)
from PHX2.stage30.stage30_11_6_candidate_source_models import (
    STAGE30_11_6_DEFAULT_CANDIDATE_ID_PREFIX,
    STAGE30_11_6_EXPECTED_DIP_TOKEN_MINT,
    Stage30_11_6HarvestResult,
)


# The deterministic caller-injected timestamp for the default scenario (never a
# wall-clock read). Matches the Stage 30.11.5 fake-proof clock so the composed
# proof is fully deterministic.
_DEFAULT_CREATED_AT: str = "2026-01-01T00:00:00Z"


# A context-present-but-not-``PRESENT`` ATH token: a present field value the
# Stage 30.11.6 projection accepts (the field is present) but the committed Stage
# 30.11.1 bridge later treats as NOT present (so it suppresses the candidate
# BEFORE the gate). Proves the projection never forces a degraded context to the
# bridge's ``PRESENT`` value.
_DEGRADED_CONTEXT_STATUS: str = "DEGRADED"


# Closed-set fake assembly scenarios (proof-local; never a production token).
_SCENARIO_OK: str = "OK"
_SCENARIO_ASSEMBLY_RAISES: str = "ASSEMBLY_RAISES"
_SCENARIO_PROJECTION_REJECTED: str = "PROJECTION_REJECTED"


# ---------------------------------------------------------------------------
# Fake normalized event + fake assembled record (proof-local shapes)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Stage30_11_6FakeNormalizedEvent:
    """A proof-local fake normalized event the fake assembler consumes.

    Carries the safe-scalar fields the fake assembler stamps onto a fake assembled
    record plus a closed-set ``scenario`` flag that selects the per-event outcome
    (a clean harvest, a raising assembler, or a record whose flattened fields omit
    a required field). NOT a real provider event; carries no raw payload, no host,
    no transport destination.
    """

    token_mint: str
    tier_hint: str
    ath_status: str
    scenario: str


@dataclass(frozen=True)
class Stage30_11_6FakeAssembledRecord:
    """A proof-local fake assembled candidate record the harvest adapter captures.

    Stands in for the deeply-nested committed Stage 27 / 28 / 29 live candidate
    record: it carries the safe-scalar fields the INJECTED fake record flattener
    reduces to a flat projection mapping. The harvest adapter holds it transiently
    (it is never retained on the harvest result). Carries no raw payload, no host,
    no transport destination.
    """

    candidate_id: str
    token_mint: str
    pair_type: str
    tier_hint: str
    drawdown_from_ath: str
    migration_status: str
    ath_status: str
    market_context_status: str
    current_market_cap_usd: str
    post_migration_ath_verified: bool
    source_ref: str
    created_at_utc: str
    omit_market_cap: bool


# ---------------------------------------------------------------------------
# Injected fake assembler (drives `.assemble`; records a dispatch tripwire)
# ---------------------------------------------------------------------------


class Stage30_11_6FakeRecordAssembler:
    """An in-memory fake candidate assembler for tests / proof ONLY.

    A structural match for the committed Stage 28.9 ``Stage28_9CandidateAssembler``
    protocol: ``assemble(normalized_event, *, candidate_id) -> record`` builds a
    fake assembled record and STAMPS the supplied run-scoped ``candidate_id`` on it
    (faithful to the committed ``Stage28_9DefaultCandidateAssembler``, which stamps
    the supplied id). It records the number of ``assemble`` calls + the ids it was
    handed. An event whose ``scenario`` is ``ASSEMBLY_RAISES`` makes ``assemble``
    raise (a custom assembler may raise; the harvest adapter fails closed to a
    clean skip).

    It ALSO exposes a dispatch TRIPWIRE -- the committed Stage 28.6 transport
    method name ``send_one_audited_post`` (plus a generic ``dispatch``) -- that
    increments ``dispatch_tripwire_calls`` if EVER called. The harvest adapter
    calls ONLY ``assemble``, so the tripwire stays at zero, proving the harvest
    path never reaches the old ungated dispatch surface even when one is present on
    the injected object. It sends NO Discord, imports NO transport, writes NO file,
    reads NO environment, and opens NO network connection.
    """

    def __init__(self) -> None:
        self.assemble_calls: int = 0
        self.seen_candidate_ids: List[str] = []
        self.dispatch_tripwire_calls: int = 0

    def assemble(
        self, normalized_event: object, *, candidate_id: str
    ) -> object:
        self.assemble_calls += 1
        self.seen_candidate_ids.append(candidate_id)
        if not isinstance(normalized_event, Stage30_11_6FakeNormalizedEvent):
            raise ValueError(
                "Stage 30.11.6 fake assembler rejecting a non-fake event"
            )
        if normalized_event.scenario == _SCENARIO_ASSEMBLY_RAISES:
            raise RuntimeError(
                "Stage 30.11.6 fake assembler raising for the failed-assembly "
                "scenario"
            )
        return Stage30_11_6FakeAssembledRecord(
            candidate_id=candidate_id,
            token_mint=normalized_event.token_mint,
            pair_type="SOL",
            tier_hint=normalized_event.tier_hint,
            drawdown_from_ath="0.55",
            migration_status="PRESENT",
            ath_status=normalized_event.ath_status,
            market_context_status="PRESENT",
            current_market_cap_usd="12345.67",
            post_migration_ath_verified=True,
            source_ref="ref-" + candidate_id,
            created_at_utc=_DEFAULT_CREATED_AT,
            omit_market_cap=(
                normalized_event.scenario == _SCENARIO_PROJECTION_REJECTED
            ),
        )

    # ---- Dispatch tripwire (NEVER called by the harvest adapter) ----

    def send_one_audited_post(self, *args: object, **kwargs: object) -> None:
        self.dispatch_tripwire_calls += 1

    def dispatch(self, *args: object, **kwargs: object) -> None:
        self.dispatch_tripwire_calls += 1


# ---------------------------------------------------------------------------
# Injected fake record flattener (deep record -> flat safe-scalar fields)
# ---------------------------------------------------------------------------


def fake_record_to_projection_fields(record: object) -> Dict[str, object]:
    """Reduce a fake assembled record to the flat Stage 30.11.5 projection fields.

    A proof-local stand-in for the out-of-repo ceremony-boundary flattener that
    reduces the deeply-nested committed live candidate record to safe scalars. It
    reads ONLY the fake record's safe-scalar fields into a flat mapping; when the
    record's ``omit_market_cap`` flag is set the required ``current_market_cap_usd``
    field is OMITTED (so the committed Stage 30.11.6 projection adapter fails closed
    -> SKIPPED_PROJECTION_REJECTED -> no candidate -> never reaches the transport).
    Pure; no I/O, no env, no provider call. Raises only for a non-record input (a
    caller-shape failure the harvest adapter treats as a clean skip).
    """
    if not isinstance(record, Stage30_11_6FakeAssembledRecord):
        raise ValueError(
            "Stage 30.11.6 fake flattener rejecting a non-record input"
        )
    fields: Dict[str, object] = {
        "candidate_id": record.candidate_id,
        "token_mint": record.token_mint,
        "pair_type": record.pair_type,
        "tier_hint": record.tier_hint,
        "drawdown_from_ath": record.drawdown_from_ath,
        "migration_status": record.migration_status,
        "ath_status": record.ath_status,
        "market_context_status": record.market_context_status,
        "current_market_cap_usd": record.current_market_cap_usd,
        "post_migration_ath_verified": record.post_migration_ath_verified,
        "source_ref": record.source_ref,
        "created_at_utc": record.created_at_utc,
    }
    if record.omit_market_cap:
        del fields["current_market_cap_usd"]
    return fields


# ---------------------------------------------------------------------------
# Deterministic five-event fake source
# ---------------------------------------------------------------------------


def default_fake_harvest_source() -> Tuple[Stage30_11_6FakeNormalizedEvent, ...]:
    """Build the deterministic five-event default fake source.

    One non-dip event (Tier Unknown, all context present), one bridge-suppressed
    event (a present-but-not-``PRESENT`` ATH context), one Tier 1 dip event (all
    context present; the THIRD event, index 2, so the harvest stamps it the dip
    candidate id ``stage30_11_6_cand_000002``), one failed-assembly event (the
    assembler raises), and one rejected-projection event (the flattener omits the
    required market-cap field). Pure; no I/O, no clock, no env.
    """
    return (
        Stage30_11_6FakeNormalizedEvent(
            token_mint="mint-unknown",
            tier_hint="Tier Unknown",
            ath_status="PRESENT",
            scenario=_SCENARIO_OK,
        ),
        Stage30_11_6FakeNormalizedEvent(
            token_mint="mint-no-ath",
            tier_hint="Tier 1",
            ath_status=_DEGRADED_CONTEXT_STATUS,
            scenario=_SCENARIO_OK,
        ),
        Stage30_11_6FakeNormalizedEvent(
            token_mint=STAGE30_11_6_EXPECTED_DIP_TOKEN_MINT,
            tier_hint="Tier 1",
            ath_status="PRESENT",
            scenario=_SCENARIO_OK,
        ),
        Stage30_11_6FakeNormalizedEvent(
            token_mint="mint-fail",
            tier_hint="Tier 1",
            ath_status="PRESENT",
            scenario=_SCENARIO_ASSEMBLY_RAISES,
        ),
        Stage30_11_6FakeNormalizedEvent(
            token_mint="mint-bad",
            tier_hint="Tier 1",
            ath_status="PRESENT",
            scenario=_SCENARIO_PROJECTION_REJECTED,
        ),
    )


# ---------------------------------------------------------------------------
# Public proof entry points
# ---------------------------------------------------------------------------


def run_stage30_11_6_fake_harvest(
    *,
    events: Optional[Tuple[Stage30_11_6FakeNormalizedEvent, ...]] = None,
    assembler: Optional[Stage30_11_6FakeRecordAssembler] = None,
    created_at_utc: str = _DEFAULT_CREATED_AT,
) -> Tuple[Stage30_11_6HarvestResult, Stage30_11_6FakeRecordAssembler]:
    """Run ONLY the Stage 30.11.6 harvest pass over the deterministic fake source
    and return ``(harvest_result, assembler)``.

    With every argument defaulted, the deterministic five-event default fake source
    is harvested through the harvest adapter with a fresh fake assembler + the fake
    record flattener and the default harvest cap. Pure / deterministic apart from
    the fake assembler's recording side effects; reads no clock, no env, no
    network; reserves no dispatch, sends no Discord, writes no file. The harvest
    adapter constructs NO transport, so the fake assembler's dispatch tripwire stays
    at zero.
    """
    effective_events = (
        default_fake_harvest_source() if events is None else events
    )
    effective_assembler = (
        Stage30_11_6FakeRecordAssembler() if assembler is None else assembler
    )
    harvest_result = harvest_live_candidates(
        effective_events,
        assembler=effective_assembler,
        record_flattener=fake_record_to_projection_fields,
        created_at_utc=created_at_utc,
        candidate_id_prefix=STAGE30_11_6_DEFAULT_CANDIDATE_ID_PREFIX,
    )
    return harvest_result, effective_assembler


def run_stage30_11_6_fake_candidate_source_proof(
    *,
    events: Optional[Tuple[Stage30_11_6FakeNormalizedEvent, ...]] = None,
    created_at_utc: str = _DEFAULT_CREATED_AT,
) -> Tuple[
    Stage30_11_6HarvestResult,
    object,
    Stage30_11_5RecordingFakeTransportClient,
    Stage30_11_6FakeRecordAssembler,
]:
    """Run the full Stage 30.11.6 offline end-to-end proof and return
    ``(harvest_result, runner_result, transport_client, assembler)``.

    With every argument defaulted, the deterministic five-event default fake source
    is harvested (three harvested projections; one failed assembly; one rejected
    projection), then the harvested ``candidate_source`` is fed through the
    committed Stage 30.11.5 fake live wiring proof (the committed bounded runner +
    a fresh in-memory recording FAKE transport client + an injected constant clock).
    The composed run drives EXACTLY one fake transport attempt -- for the Tier 1 dip
    (``stage30_11_6_cand_000002`` / ``mint-tier1``) ONLY; the non-dip is suppressed
    by the committed dip gate, the bridge-suppressed by the committed bridge, and the
    failed-assembly / rejected-projection events never become candidates, so none
    reaches the transport. The OLD ungated dispatch path is never invoked: the fake
    assembler's dispatch tripwire records zero calls.

    Pure / deterministic apart from the injected fakes' recording side effects;
    reads no clock, no env, no network; reserves no real dispatch, sends no Discord,
    writes no file, runs no daemon / ``while`` loop. The harvest adapter / projection
    adapter / committed runner / committed dip gate / committed private sink are
    exercised TRANSITIVELY through the committed siblings; this proof reimplements
    none of the composed slices.
    """
    harvest_result, assembler = run_stage30_11_6_fake_harvest(
        events=events, created_at_utc=created_at_utc
    )
    runner_result, transport_client = run_stage30_11_5_fake_live_wiring_proof(
        candidate_source=harvest_result.candidate_source,
        created_at_utc=created_at_utc,
    )
    return harvest_result, runner_result, transport_client, assembler


__all__ = (
    "Stage30_11_6FakeNormalizedEvent",
    "Stage30_11_6FakeAssembledRecord",
    "Stage30_11_6FakeRecordAssembler",
    "fake_record_to_projection_fields",
    "default_fake_harvest_source",
    "run_stage30_11_6_fake_harvest",
    "run_stage30_11_6_fake_candidate_source_proof",
)

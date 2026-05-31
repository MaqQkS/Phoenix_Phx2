"""Stage 30.10.3 offline fake gate artifact integration proof.

A pure, deterministic, fail-closed helper that PROVES the Stage 30.10.3
gate artifact integration composes end-to-end using fakes / offline
candidates only:

    the Stage 30.10.2 default nine-candidate fake gate scenario
      -> the Stage 30.10.2 pre-dispatch gate   (evaluated BEFORE reservation)
      -> the Stage 30.10.3 artifact projector   (records + rolled-up batch)
      -> a Stage 30.10.3 in-memory artifact sink (records the batch only)

It is NOT a live runner, NOT a live provider run, NOT a Discord send, NOT a
dispatch reservation / real send, NOT a transport-layer veto, and NOT a new
readiness gate. It CONSTRUCTS no filesystem I/O, opens no database, reads no
environment, opens no network connection, and touches no Discord / live
provider path. The only "sink" is the in-memory fake artifact sink below: it
retains the batch + records in a Python list and writes nothing to disk.

The proof reuses the SAME deterministic nine-candidate scenario as the Stage
30.10.2 fake gate proof, so the artifact batch tally matches the Stage 30.10.2
gate proof's outcome exactly:

  1. Tier 1 valid dip      -> PASS_TO_DISPATCH      (would reserve dispatch)
  2. Tier 2 valid dip      -> PASS_TO_DISPATCH      (would reserve dispatch)
  3. Tier 3 valid dip      -> PASS_TO_DISPATCH      (would reserve dispatch)
  4. Tier Unknown          -> SKIP_BEFORE_DISPATCH  (suppressed before)
  5. Tier Not Applicable   -> SKIP_BEFORE_DISPATCH  (suppressed before)
  6. missing ATH           -> SKIP_BEFORE_DISPATCH  (suppressed before)
  7. missing migration     -> SKIP_BEFORE_DISPATCH  (suppressed before)
  8. malformed drawdown    -> SKIP_BEFORE_DISPATCH  (suppressed before)
  9. invalid candidate_id  -> INVALID_INPUT         (suppressed before)

So the batch has nine artifact records, exactly three that would attempt a
dispatch reservation, exactly six suppressed BEFORE reservation, and ZERO
dispatch failures / transport vetoes / ``PAYLOAD_REFUSED`` uses -- every
skipped / invalid candidate keeps its eligibility + gate reason on its
artifact record, and no Discord / live-provider / transport path is ever
touched.

Discipline:

  * Stdlib only (``typing``).
  * Imports only the Stage 30.10.3 artifact-models + projector siblings + the
    Stage 30.10.2 gate-models + gate + fake-gate-proof siblings (to obtain the
    fake scenario and run the real gate). No other PHX2 module; no Stage 21-29
    / Stage 30.3 / Stage 30.4 orchestrator / Stage 28 suppression / live
    runner / provider / transport import.
  * No ``os`` (NO env read), NO network, NO ``sqlite3``, NO ``zstd`` /
    compression, NO clock / random, NO direct filesystem primitive.
  * No top-level Call (no implicit I/O at import time).
"""

from __future__ import annotations

from typing import List, Optional, Tuple

from PHX2.stage30.stage30_10_2_fake_gate_proof import (
    default_pre_dispatch_gate_scenario,
)
from PHX2.stage30.stage30_10_2_pre_dispatch_gate import (
    evaluate_pre_dispatch_tier_dip_gate,
)
from PHX2.stage30.stage30_10_2_pre_dispatch_gate_models import (
    Stage30_10PreDispatchGateRecord,
    Stage30_10PreDispatchGateScenario,
)
from PHX2.stage30.stage30_10_3_gate_artifact_models import (
    STAGE30_10_3_ARTIFACT_SCHEMA_VERSION,
    Stage30_10GateArtifactBatch,
    Stage30_10GateArtifactSinkResult,
)
from PHX2.stage30.stage30_10_3_gate_artifact_projector import (
    project_gate_records_to_artifact_batch,
)


# The deterministic caller-injected proof id + clock for the default proof
# (never a wall-clock read). The clock matches the Stage 30.10.2 fake gate
# scenario clock so the composed proof is fully deterministic.
_DEFAULT_PROOF_ID: str = "stage30_10_3_fake_gate_artifact_proof"
_DEFAULT_CREATED_AT: str = "2026-01-01T00:00:00Z"


# ---------------------------------------------------------------------------
# In-memory fake artifact sink (records only; writes nothing to disk)
# ---------------------------------------------------------------------------


class Stage30_10InMemoryGateArtifactSink:
    """A fake / offline artifact sink that retains a gate artifact batch in
    memory ONLY.

    It writes NOTHING to disk / database / network / compression: ``write``
    appends the batch's records to an in-memory list and returns a passive
    ``Stage30_10GateArtifactSinkResult`` attesting how many records + which
    batch were retained, plus the pinned artifact schema version. Used by the
    offline proof and by tests; it is the explicitly in-memory fake writer the
    Stage 30.10.3 slice is allowed (no filesystem persistence).
    """

    def __init__(self) -> None:
        # In-memory only; never a file handle / db connection / socket.
        self._records: List[object] = []
        self._batches: List[object] = []

    @property
    def records(self) -> Tuple[object, ...]:
        """Return the retained artifact records (in write order)."""
        return tuple(self._records)

    @property
    def batch_count(self) -> int:
        """Return the number of batches retained."""
        return len(self._batches)

    def write(
        self, batch: Stage30_10GateArtifactBatch
    ) -> Stage30_10GateArtifactSinkResult:
        """Retain ``batch`` in memory and return a passive sink result.

        Appends ``batch.records`` to the in-memory record list and the batch
        to the in-memory batch list, then returns a
        ``Stage30_10GateArtifactSinkResult``. Pure relative to the in-memory
        store; performs NO disk / database / network / compression I/O and
        reads no clock (the result timestamp is the batch's caller-injected
        ``created_at_utc``).
        """
        self._records.extend(batch.records)
        self._batches.append(batch)
        return Stage30_10GateArtifactSinkResult(
            proof_id=batch.proof_id,
            records_written=len(batch.records),
            batch_written=True,
            artifact_schema_version=STAGE30_10_3_ARTIFACT_SCHEMA_VERSION,
            created_at_utc=batch.created_at_utc,
        )


# ---------------------------------------------------------------------------
# Pure helper: scenario -> gate records
# ---------------------------------------------------------------------------


def build_fake_gate_records(
    scenario: Optional[Stage30_10PreDispatchGateScenario] = None,
) -> Tuple[Stage30_10PreDispatchGateRecord, ...]:
    """Run a Stage 30.10.2 gate scenario through the real gate and return the
    per-candidate gate records (in scenario order).

    With ``scenario=None`` the deterministic Stage 30.10.2 nine-candidate
    default scenario is used. Each gate input is evaluated through the real
    Stage 30.10.2 pre-dispatch gate with its locked fail-closed default
    policy. Pure / deterministic; reads no clock, no env, no network; never
    sends Discord, never calls a live provider, never performs a transport
    veto.
    """
    if scenario is None:
        scenario = default_pre_dispatch_gate_scenario()
    return tuple(
        evaluate_pre_dispatch_tier_dip_gate(gate_input)
        for gate_input in scenario.gate_inputs
    )


# ---------------------------------------------------------------------------
# Public entry point: scenario -> gate -> artifact batch
# ---------------------------------------------------------------------------


def run_stage30_10_3_fake_artifact_proof(
    scenario: Optional[Stage30_10PreDispatchGateScenario] = None,
    *,
    proof_id: str = _DEFAULT_PROOF_ID,
    created_at_utc: str = _DEFAULT_CREATED_AT,
) -> Stage30_10GateArtifactBatch:
    """Run the offline fake gate artifact proof and return the artifact batch.

    With ``scenario=None`` the deterministic Stage 30.10.2 nine-candidate
    default scenario is used. Each candidate is run through the real Stage
    30.10.2 gate, then the Stage 30.10.3 projector rolls the gate records into
    ONE gate artifact batch. The batch tally proves: nine artifact records,
    three that would attempt a dispatch reservation, six suppressed BEFORE
    reservation, and zero dispatch failures / transport vetoes /
    ``PAYLOAD_REFUSED`` uses. Pure / deterministic; reads no clock, no env, no
    network; never sends Discord, never calls a live provider, never performs
    a transport veto, never writes a file.
    """
    gate_records = build_fake_gate_records(scenario)
    return project_gate_records_to_artifact_batch(
        proof_id=proof_id,
        gate_records=gate_records,
        created_at_utc=created_at_utc,
    )


def run_stage30_10_3_fake_artifact_proof_into_sink(
    scenario: Optional[Stage30_10PreDispatchGateScenario] = None,
    *,
    proof_id: str = _DEFAULT_PROOF_ID,
    created_at_utc: str = _DEFAULT_CREATED_AT,
) -> Tuple[Stage30_10GateArtifactBatch, Stage30_10GateArtifactSinkResult]:
    """Run the offline fake gate artifact proof, write the batch to a fresh
    in-memory sink, and return ``(batch, sink_result)``.

    Composes ``run_stage30_10_3_fake_artifact_proof`` with the in-memory
    ``Stage30_10InMemoryGateArtifactSink``: the projected batch is retained in
    memory ONLY (no disk / database / network), and the returned sink result
    attests the retained record count + the pinned artifact schema version.
    Pure relative to the fresh in-memory sink; never writes a file, never
    sends Discord, never calls a live provider.
    """
    batch = run_stage30_10_3_fake_artifact_proof(
        scenario,
        proof_id=proof_id,
        created_at_utc=created_at_utc,
    )
    sink = Stage30_10InMemoryGateArtifactSink()
    sink_result = sink.write(batch)
    return batch, sink_result


__all__ = (
    "Stage30_10InMemoryGateArtifactSink",
    "build_fake_gate_records",
    "run_stage30_10_3_fake_artifact_proof",
    "run_stage30_10_3_fake_artifact_proof_into_sink",
)

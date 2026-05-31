"""Stage 30.10.3 pre-dispatch gate artifact projector.

Pure, offline projector that turns Stage 30.10.2 pre-dispatch gate audit
records into Stage 30.10.3 gate artifact records + a rolled-up gate artifact
batch, so the (future) Stage 30.9.2 live proof is auditable per candidate:
every candidate the gate evaluated gets an artifact record that says, in
auditable form, whether a dispatch reservation would be attempted, whether
the candidate was suppressed BEFORE reservation, and -- always negatively --
whether it was a dispatch failure / a transport veto / a ``PAYLOAD_REFUSED``
veto.

The projector is the thin ARTIFACT layer; it owns NO gate / eligibility logic
of its own. It reads ONLY the gate record's already-decided closed-set
tokens and maps the Stage 30.10.2 gate decision onto the five derived
artifact booleans:

  * ``PASS_TO_DISPATCH``
        -> ``dispatch_reservation_would_be_attempted=True``,
           ``suppressed_before_dispatch_reservation=False`` (the ONLY
           candidate that would proceed to dispatch reservation);
  * ``SKIP_BEFORE_DISPATCH``
        -> ``dispatch_reservation_would_be_attempted=False``,
           ``suppressed_before_dispatch_reservation=True`` (a NORMAL no-send
           suppressed BEFORE reservation);
  * ``INVALID_INPUT``
        -> ``dispatch_reservation_would_be_attempted=False``,
           ``suppressed_before_dispatch_reservation=True`` (fail closed);
  * any unknown / unrecognized gate decision
        -> FAIL CLOSED exactly like ``INVALID_INPUT``
           (``dispatch_reservation_would_be_attempted=False``,
           ``suppressed_before_dispatch_reservation=True``); it never attempts
           dispatch reservation.

``dispatch_reservation_would_be_attempted`` is ``True`` IFF the gate decision
is exactly ``PASS_TO_DISPATCH``; ``suppressed_before_dispatch_reservation`` is
its exact complement. The other three artifact booleans
(``dispatch_failure_recorded`` / ``transport_veto_used`` /
``payload_refused_used``) are ALWAYS ``False`` for EVERY candidate: a
pre-dispatch gate skip can never be a dispatch failure, can never use a
transport-layer veto, and can never reuse the transport ``PAYLOAD_REFUSED``
veto. This makes it impossible to confuse a candidate *skipped before
dispatch* with one that *failed during dispatch*.

The batch counts are derived from the projected records (so the batch tally
provably matches the per-record flags): ``candidates_passed`` /
``candidates_skipped`` are the ``PASS_TO_DISPATCH`` / ``SKIP_BEFORE_DISPATCH``
counts; ``invalid_inputs`` is every remaining record (``INVALID_INPUT`` plus
any unrecognized decision -- fail closed into invalid), so passed + skipped +
invalid always partitions ``candidates_seen``; ``dispatch_attempts_reserved``
equals ``candidates_passed``; ``dispatch_attempts_suppressed_before_reservation``
equals ``candidates_skipped`` + ``invalid_inputs``; and
``dispatch_failures_recorded`` / ``transport_veto_count`` /
``payload_refused_count`` are always 0.

The projector NEVER fetches data, NEVER opens a network connection, NEVER
reads the process environment, NEVER calls ``datetime.now`` (the artifact
timestamp is caller-injected), NEVER sends Discord, NEVER reserves a real
dispatch / performs a real send, NEVER performs a transport-layer veto, NEVER
writes a file, and NEVER wires into the live runtime / Stage 28 suppression /
Stage 30.3 / Stage 30.4 orchestrators. Stage 30.10.3 is fake / offline only;
nothing existing imports it.

Discipline:

  * Stdlib only (``typing``).
  * Imports only the Stage 30.10.3 artifact-models sibling + the Stage
    30.10.2 gate-models sibling (the gate record type + the gate-decision
    closed-set tokens). No other PHX2 module; no Stage 21-29 / Stage 30.3 /
    Stage 30.4 orchestrator / Stage 28 suppression / live runner / provider /
    transport import.
  * No ``os.environ`` / ``os.getenv`` access; no env read.
  * No network, no HTTP, no gRPC, no WebSocket, no socket.
  * No database / SQLite, no zstd / compression, no default storage root.
  * No live provider, transport-destination, or request-metadata reference.
  * No PHX1 import. No wall clock (``created_at_utc`` is caller-injected).
"""

from __future__ import annotations

from typing import Tuple

from PHX2.stage30.stage30_10_2_pre_dispatch_gate_models import (
    GATE_DECISION_PASS_TO_DISPATCH,
    GATE_DECISION_SKIP_BEFORE_DISPATCH,
    Stage30_10PreDispatchGateRecord,
)
from PHX2.stage30.stage30_10_3_gate_artifact_models import (
    Stage30_10GateArtifactBatch,
    Stage30_10GateArtifactRecord,
)


# ---------------------------------------------------------------------------
# Pure projector: one gate record -> one artifact record
# ---------------------------------------------------------------------------


def project_gate_record_to_artifact_record(
    *,
    proof_id: str,
    gate_record: Stage30_10PreDispatchGateRecord,
    created_at_utc: str,
) -> Stage30_10GateArtifactRecord:
    """Project ONE Stage 30.10.2 gate record into a Stage 30.10.3 artifact
    record.

    Pure / deterministic / no I/O. Echoes the gate record's identity +
    eligibility / gate closed-set tokens + ``send_allowed``, and derives the
    five artifact booleans from the gate decision:
    ``dispatch_reservation_would_be_attempted`` is ``True`` IFF the gate
    decision is exactly ``PASS_TO_DISPATCH``;
    ``suppressed_before_dispatch_reservation`` is its complement; and
    ``dispatch_failure_recorded`` / ``transport_veto_used`` /
    ``payload_refused_used`` are ALWAYS ``False``. An unknown / unrecognized
    gate decision fails closed (not attempted; suppressed). ``created_at_utc``
    is the caller-injected artifact timestamp (never a wall-clock read).
    """
    would_attempt = gate_record.gate_decision == GATE_DECISION_PASS_TO_DISPATCH
    return Stage30_10GateArtifactRecord(
        proof_id=proof_id,
        candidate_id=gate_record.candidate_id,
        token_mint=gate_record.token_mint,
        eligibility_decision=gate_record.eligibility_decision,
        eligibility_reason=gate_record.eligibility_reason,
        gate_decision=gate_record.gate_decision,
        gate_reason=gate_record.gate_reason,
        send_allowed=gate_record.send_allowed,
        dispatch_reservation_would_be_attempted=would_attempt,
        # The exact complement: every non-pass candidate (skip / invalid /
        # unknown) is suppressed cleanly BEFORE dispatch reservation.
        suppressed_before_dispatch_reservation=not would_attempt,
        # A pre-dispatch gate decision is NEVER a dispatch failure, NEVER a
        # transport-layer veto, and NEVER a transport PAYLOAD_REFUSED veto.
        dispatch_failure_recorded=False,
        transport_veto_used=False,
        payload_refused_used=False,
        created_at_utc=created_at_utc,
    )


# ---------------------------------------------------------------------------
# Pure projector: gate records -> one artifact batch
# ---------------------------------------------------------------------------


def project_gate_records_to_artifact_batch(
    *,
    proof_id: str,
    gate_records: Tuple[Stage30_10PreDispatchGateRecord, ...],
    created_at_utc: str,
) -> Stage30_10GateArtifactBatch:
    """Project a tuple of Stage 30.10.2 gate records into ONE Stage 30.10.3
    gate artifact batch.

    Pure / deterministic / no I/O. Each gate record becomes one artifact
    record (in input order); the batch counts are derived FROM the projected
    records so the tally provably matches the per-record flags:

      * ``candidates_passed`` / ``candidates_skipped`` count the
        ``PASS_TO_DISPATCH`` / ``SKIP_BEFORE_DISPATCH`` records;
      * ``invalid_inputs`` counts every remaining record (``INVALID_INPUT``
        plus any unrecognized decision -- fail closed into invalid), so
        passed + skipped + invalid always partitions ``candidates_seen``;
      * ``dispatch_attempts_reserved`` equals the would-attempt count
        (== ``candidates_passed``);
      * ``dispatch_attempts_suppressed_before_reservation`` equals the
        suppressed count (== ``candidates_skipped`` + ``invalid_inputs``);
      * ``dispatch_failures_recorded`` / ``transport_veto_count`` /
        ``payload_refused_count`` are always 0.

    An empty ``gate_records`` yields an all-zero batch (a valid, empty proof).
    """
    records = tuple(
        project_gate_record_to_artifact_record(
            proof_id=proof_id,
            gate_record=gate_record,
            created_at_utc=created_at_utc,
        )
        for gate_record in gate_records
    )

    seen = len(records)
    passed = sum(
        1
        for record in records
        if record.gate_decision == GATE_DECISION_PASS_TO_DISPATCH
    )
    skipped = sum(
        1
        for record in records
        if record.gate_decision == GATE_DECISION_SKIP_BEFORE_DISPATCH
    )
    # Everything that is neither PASS nor SKIP is invalid (INVALID_INPUT plus
    # any unrecognized decision -- fail closed into invalid). This keeps the
    # passed / skipped / invalid partition total over ``candidates_seen``.
    invalid = seen - passed - skipped

    reserved = sum(
        1 for record in records
        if record.dispatch_reservation_would_be_attempted
    )
    suppressed = sum(
        1 for record in records
        if record.suppressed_before_dispatch_reservation
    )
    failures = sum(
        1 for record in records if record.dispatch_failure_recorded
    )
    veto = sum(1 for record in records if record.transport_veto_used)
    refused = sum(1 for record in records if record.payload_refused_used)

    return Stage30_10GateArtifactBatch(
        proof_id=proof_id,
        records=records,
        candidates_seen=seen,
        candidates_passed=passed,
        candidates_skipped=skipped,
        invalid_inputs=invalid,
        dispatch_attempts_reserved=reserved,
        dispatch_attempts_suppressed_before_reservation=suppressed,
        dispatch_failures_recorded=failures,
        transport_veto_count=veto,
        payload_refused_count=refused,
        created_at_utc=created_at_utc,
    )


__all__ = (
    "project_gate_record_to_artifact_record",
    "project_gate_records_to_artifact_batch",
)

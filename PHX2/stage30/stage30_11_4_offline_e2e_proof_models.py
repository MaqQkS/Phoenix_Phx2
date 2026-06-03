"""Stage 30.11.4 offline end-to-end proof models.

Stage 30.11.4 ships the passive, pure, stdlib-only MODEL layer for the offline
end-to-end proof that composes the committed Stage 30.11.1 bridge + Stage 30.11.2
runtime gate seam + committed Stage 30.9.3 dip gate + Stage 30.11.3 private sink
adapter behind an INJECTED fake private transport: the rolled-up offline
end-to-end proof SUMMARY (the chain counters plus the proof verdict), the
end-to-end proof RESULT (the verdict + summary + the recorded runtime outcomes +
the safe-shape transport identities the fake transport saw), the closed-set proof
decision / reason vocabularies they share, the author-verified expected baseline
counts the proof asserts, and the pure safe-shape helper the proof composes.

This module is the MODEL layer ONLY. It implements NO proof (that is
``stage30_11_4_offline_e2e_proof``), composes NO bridge / gate / seam / sink,
calls NO transport, runs NO runtime, makes NO live provider call, sends NO
Discord message, reads NO process environment, opens NO network connection,
opens NO database, writes NO file, reserves NO real dispatch, reads NO wall
clock (``created_at_utc`` is caller-injected), and edits NO Stage 28 / Stage 29 /
Stage 30.3 / Stage 30.4 production file. Stage 30.11.4 is fake / offline only:
the real private compact dispatch / Discord send remains a SEPARATE, explicitly
operator-authorized step this slice does not build.

The proof emits exactly one of two closed-set proof decisions over one composed
run of the committed chain:

  * ``OFFLINE_E2E_PROOF_PASSED`` -- the composed chain behaved exactly as the
    author-verified baseline requires: the single Tier 1 dip bridged, passed the
    committed dip gate, drove the private sink, and reached the INJECTED fake
    transport for an accepted would-send; every non-dip / bridge-skip / invalid
    candidate was suppressed cleanly BEFORE the sink and never reached the
    transport (reason ``PASS_DIP_REACHED_FAKE_TRANSPORT_ONLY`` -- a RECORDED
    would-send for the dip ONLY, NEVER a real send).
  * ``OFFLINE_E2E_PROOF_FAILED`` -- the composed run did NOT match the baseline.
    Exactly one closed-set reason names why:
      - ``UNEXPECTED_TRANSPORT_ATTEMPT`` -- the fake transport saw an attempt it
        must never see (more than the one expected dip attempt, or an attempt
        for a candidate id other than the expected dip): a non-dip / bridge-skip
        / invalid candidate must NEVER reach the transport.
      - ``UNEXPECTED_E2E_COUNTS``        -- the chain counters (bridge / gate /
        sink / transport-accept / runtime-stop axes) did not match the baseline
        (for example the injected fake transport rejected the dip, so the
        accepted counts are short).
      - ``INVALID_PROOF_INPUT``          -- a caller-shape failure (a blank
        ``created_at_utc``, a malformed count, or a malformed transport-id
        sequence) the proof fails closed on BEFORE judging the counts.

Discipline:

  * Stdlib only (``dataclasses`` / ``typing``).
  * Imports NO PHX2 module (mirrors the Stage 30.9.3 / 30.11.2 / 30.11.3 model
    modules); the records carry only safe scalars / closed-set tokens. The
    end-to-end result's ``runtime_outcomes`` is typed ``Tuple[Any, ...]`` so the
    passive carrier holds the committed runtime outcome records BY VALUE without
    importing the Stage 30.11.2 outcome type.
  * No ``os.environ`` / ``os.getenv`` access; no env read.
  * No network, no HTTP, no gRPC, no WebSocket, no socket.
  * No database / SQLite, no zstd / compression, no default storage root.
  * No live provider, transport-destination, or request-metadata reference.
  * No PHX1 import. No Stage 21-29 production import.
  * No ``time`` / ``datetime`` import; ``created_at_utc`` is caller-injected.
  * No module-level Call node (no implicit I/O at import time; the
    ``@dataclass(frozen=True)`` decorators are decorator-list Calls, not
    body-statement Calls).
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from typing import Any, Tuple


# ---------------------------------------------------------------------------
# Minor version + end-to-end proof schema identity
# ---------------------------------------------------------------------------


STAGE30_11_4_MINOR_VERSION: str = "30.11.4"


# The Stage 30.11.4 offline end-to-end proof schema version. Names the proof
# summary / result shape; distinct from the Stage 30.11.3 private sink schema
# version, the Stage 30.11.2 runtime gate schema version, the Stage 30.11.1
# bridge schema version, and the Stage 30.9.3 integration schema version.
# Mirrored BY VALUE by the Stage 30.11 manifest section; this module imports no
# Stage 30.11 manifest.
STAGE30_11_4_OFFLINE_E2E_PROOF_SCHEMA_VERSION: str = (
    "stage30_11_4_v0_offline_e2e_proof"
)


# ---------------------------------------------------------------------------
# Closed-set: proof decision
# ---------------------------------------------------------------------------
#
# Exactly one proof decision per composed run. ``OFFLINE_E2E_PROOF_PASSED`` is
# the only decision on which the whole committed chain behaved as the baseline
# requires (the dip reached the fake transport ONLY). Mirrored BY VALUE by the
# Stage 30.11 manifest.


OFFLINE_E2E_PROOF_PASSED: str = "OFFLINE_E2E_PROOF_PASSED"
OFFLINE_E2E_PROOF_FAILED: str = "OFFLINE_E2E_PROOF_FAILED"


STAGE30_11_4_PROOF_DECISIONS: Tuple[str, ...] = (
    OFFLINE_E2E_PROOF_PASSED,
    OFFLINE_E2E_PROOF_FAILED,
)


# The single decision on which the composed chain matched the baseline.
STAGE30_11_4_PROOF_PASS_DECISION: str = OFFLINE_E2E_PROOF_PASSED


def is_offline_e2e_proof_decision(value: object) -> bool:
    """Return ``True`` iff ``value`` is a closed-set proof decision.

    Pure / total; never raises.
    """
    return isinstance(value, str) and value in STAGE30_11_4_PROOF_DECISIONS


# ---------------------------------------------------------------------------
# Closed-set: proof reason
# ---------------------------------------------------------------------------
#
# Exactly one proof reason per recorded result.
# ``PASS_DIP_REACHED_FAKE_TRANSPORT_ONLY`` is the only reason that accompanies a
# passed proof; it names a RECORDED would-send for the dip ONLY, NEVER a real
# send. Mirrored BY VALUE by the Stage 30.11 manifest.


PROOF_REASON_PASS_DIP_REACHED_FAKE_TRANSPORT_ONLY: str = (
    "PASS_DIP_REACHED_FAKE_TRANSPORT_ONLY"
)
PROOF_REASON_UNEXPECTED_E2E_COUNTS: str = "UNEXPECTED_E2E_COUNTS"
PROOF_REASON_UNEXPECTED_TRANSPORT_ATTEMPT: str = "UNEXPECTED_TRANSPORT_ATTEMPT"
PROOF_REASON_INVALID_PROOF_INPUT: str = "INVALID_PROOF_INPUT"


STAGE30_11_4_PROOF_REASONS: Tuple[str, ...] = (
    PROOF_REASON_PASS_DIP_REACHED_FAKE_TRANSPORT_ONLY,
    PROOF_REASON_UNEXPECTED_E2E_COUNTS,
    PROOF_REASON_UNEXPECTED_TRANSPORT_ATTEMPT,
    PROOF_REASON_INVALID_PROOF_INPUT,
)


# The single reason that accompanies the only passed decision.
STAGE30_11_4_PROOF_PASS_REASON: str = (
    PROOF_REASON_PASS_DIP_REACHED_FAKE_TRANSPORT_ONLY
)


def is_offline_e2e_proof_reason(value: object) -> bool:
    """Return ``True`` iff ``value`` is a closed-set proof reason.

    Pure / total; never raises.
    """
    return isinstance(value, str) and value in STAGE30_11_4_PROOF_REASONS


# ---------------------------------------------------------------------------
# Author-verified expected baseline counts (the committed default stream)
# ---------------------------------------------------------------------------
#
# The composed proof drives the committed Stage 30.11.2 deterministic
# five-candidate default stream through the committed runtime seam with the
# committed Stage 30.11.3 private sink (wrapped for seam compatibility) injected
# and an INJECTED in-memory recording fake transport. The author-verified
# baseline: five candidates seen (a Tier 1 dip + a non-dip + a missing-ATH +
# a missing-migration + an invalid blank-id candidate), exactly two bridged,
# exactly one passed the committed dip gate, exactly one private sink attempt /
# accept, exactly one fake transport attempt / accept -- for the dip ONLY (the
# ``cand-tier1`` / ``mint-tier1`` identity). Every non-dip / bridge-skip /
# invalid candidate is suppressed cleanly BEFORE the sink and never reaches the
# transport, and no cap / wall-clock bound is tripped. Mirrored BY VALUE by the
# Stage 30.11 manifest. NONE is a secret, a raw payload, a host, or a transport
# destination.


# ``candidates_seen`` floor: the proof requires AT LEAST the four distinct
# scenario kinds (dip / non-dip / bridge-skip / invalid); the committed default
# stream supplies five (it carries two bridge-skip candidates).
STAGE30_11_4_MIN_EXPECTED_CANDIDATES_SEEN: int = 4
STAGE30_11_4_EXPECTED_CANDIDATES_SEEN: int = 5
STAGE30_11_4_EXPECTED_BRIDGE_SUCCESSES: int = 2
STAGE30_11_4_EXPECTED_BRIDGE_SUPPRESSED: int = 3
STAGE30_11_4_EXPECTED_GATE_PASSES: int = 1
STAGE30_11_4_EXPECTED_GATE_SUPPRESSED: int = 1
STAGE30_11_4_EXPECTED_SINK_ATTEMPTS: int = 1
STAGE30_11_4_EXPECTED_SINK_ACCEPTS: int = 1
STAGE30_11_4_EXPECTED_SINK_FAILURES: int = 0
STAGE30_11_4_EXPECTED_TRANSPORT_ATTEMPTS: int = 1
STAGE30_11_4_EXPECTED_TRANSPORT_ACCEPTS: int = 1


# The exact safe-shape identity of the single dip the fake transport is allowed
# to see (the committed Stage 30.11.2 default stream's Tier 1 dip candidate). No
# other candidate id / token mint may reach the transport.
STAGE30_11_4_EXPECTED_DIP_CANDIDATE_ID: str = "cand-tier1"
STAGE30_11_4_EXPECTED_DIP_TOKEN_MINT: str = "mint-tier1"


# ---------------------------------------------------------------------------
# Pure safe-shape helper
# ---------------------------------------------------------------------------


def is_nonblank_str(value: object) -> bool:
    """Return ``True`` iff ``value`` is a non-empty, non-blank string.

    A missing (``None``), non-string, empty, or whitespace-only value is NOT a
    usable safe-shape token. Pure / total; never raises. Mirrors the Stage
    30.11.1 / 30.11.3 non-blank check BY VALUE; the proof consults it to fail
    closed on a blank ``created_at_utc`` (an ``INVALID_PROOF_INPUT``).
    """
    return isinstance(value, str) and value.strip() != ""


# ---------------------------------------------------------------------------
# Immutable model: offline end-to-end proof summary
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Stage30_11OfflineE2EProofSummary:
    """Immutable offline Stage 30.11.4 end-to-end proof tally.

    A passive summary of one composed run of the committed chain (bridge ->
    runtime gate seam -> committed dip gate -> private sink adapter -> INJECTED
    fake transport). It carries the chain counters across every stage plus the
    closed-set proof verdict, so a reader can audit -- by counting -- that ONLY
    the single dip reached the fake transport (for an accepted would-send) and
    that every non-dip / bridge-skip / invalid candidate was suppressed cleanly
    BEFORE the sink. Carries only non-negative integer counts + closed-set
    verdict tokens + a caller-injected timestamp; no secret, no payload, no host,
    no transport destination.

      * ``candidates_seen``                  -- candidates evaluated through the
                                                runtime seam (a cap / runtime
                                                cut-off candidate is not counted).
      * ``bridge_successes``                 -- count the Stage 30.11.1 bridge
                                                BRIDGED into a gate input.
      * ``bridge_suppressed``                -- count the bridge skipped / failed
                                                closed (no gate input).
      * ``gate_passes``                      -- count the committed dip gate ruled
                                                PASS_TO_DISPATCH.
      * ``gate_suppressed``                  -- count bridged but the dip gate did
                                                NOT pass.
      * ``sink_attempts``                    -- count the private sink was
                                                invoked (one per gate pass).
      * ``sink_accepts``                     -- count the private sink recorded an
                                                accepted would-send.
      * ``sink_failures``                    -- count the private sink rejected /
                                                transport-failed.
      * ``transport_attempts``               -- count the INJECTED fake transport
                                                was called.
      * ``transport_accepts``                -- count the fake transport accepted.
      * ``runtime_stopped_by_candidate_cap`` -- 1 iff the candidate cap stopped
                                                the run.
      * ``runtime_stopped_by_dispatch_cap``  -- 1 iff the dispatch cap stopped the
                                                run.
      * ``runtime_stopped_by_runtime_seconds``
                                             -- 1 iff the wall-clock bound stopped
                                                the run.
      * ``proof_decision``                   -- one of
                                                ``STAGE30_11_4_PROOF_DECISIONS``.
      * ``proof_reason``                     -- one of
                                                ``STAGE30_11_4_PROOF_REASONS``.
      * ``created_at_utc``                   -- caller-injected ISO-8601 UTC
                                                timestamp; NEVER a wall-clock read.
    """

    candidates_seen: int
    bridge_successes: int
    bridge_suppressed: int
    gate_passes: int
    gate_suppressed: int
    sink_attempts: int
    sink_accepts: int
    sink_failures: int
    transport_attempts: int
    transport_accepts: int
    runtime_stopped_by_candidate_cap: int
    runtime_stopped_by_dispatch_cap: int
    runtime_stopped_by_runtime_seconds: int
    proof_decision: str
    proof_reason: str
    created_at_utc: str


# ---------------------------------------------------------------------------
# Immutable model: offline end-to-end proof result
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Stage30_11OfflineE2EProofResult:
    """Immutable Stage 30.11.4 offline end-to-end proof result.

    The proof emits exactly one of these per composed run. It pins the closed-set
    ``proof_decision`` / ``proof_reason``, carries the rolled-up
    ``Stage30_11OfflineE2EProofSummary``, the ordered runtime outcomes the
    committed seam emitted (held as opaque records BY VALUE -- the model imports
    no Stage 30.11.2 outcome type), and the safe-shape candidate ids / token
    mints the INJECTED fake transport recorded (the transport reached ONLY the
    dip). Carries only safe scalars + the embedded summary + a caller-injected
    timestamp; no secret, no raw payload, no host, no transport destination, no
    env value.

      * ``proof_decision``          -- one of ``STAGE30_11_4_PROOF_DECISIONS``.
      * ``proof_reason``            -- one of ``STAGE30_11_4_PROOF_REASONS``.
      * ``summary``                 -- the embedded
                                       ``Stage30_11OfflineE2EProofSummary``.
      * ``runtime_outcomes``        -- the ordered committed runtime outcome
                                       records (opaque carrier; the model imports
                                       no Stage 30.11.2 outcome type).
      * ``transport_candidate_ids`` -- the ordered safe-shape candidate ids the
                                       INJECTED fake transport recorded (the dip
                                       only, on a passed proof).
      * ``transport_token_mints``   -- the ordered safe-shape token mints the
                                       INJECTED fake transport recorded.
      * ``created_at_utc``          -- caller-injected ISO-8601 UTC timestamp;
                                       NEVER a wall-clock read.
    """

    proof_decision: str
    proof_reason: str
    summary: Stage30_11OfflineE2EProofSummary
    runtime_outcomes: Tuple[Any, ...]
    transport_candidate_ids: Tuple[str, ...]
    transport_token_mints: Tuple[str, ...]
    created_at_utc: str


# ---------------------------------------------------------------------------
# Field-name helpers (pure; read dataclass field names)
# ---------------------------------------------------------------------------


def offline_e2e_proof_summary_field_names() -> Tuple[str, ...]:
    """Return the offline end-to-end proof summary field names as a tuple."""
    return tuple(f.name for f in fields(Stage30_11OfflineE2EProofSummary))


def offline_e2e_proof_result_field_names() -> Tuple[str, ...]:
    """Return the offline end-to-end proof result field names as a tuple."""
    return tuple(f.name for f in fields(Stage30_11OfflineE2EProofResult))


__all__ = (
    # Minor version + end-to-end proof schema identity.
    "STAGE30_11_4_MINOR_VERSION",
    "STAGE30_11_4_OFFLINE_E2E_PROOF_SCHEMA_VERSION",
    # Proof decisions.
    "OFFLINE_E2E_PROOF_PASSED",
    "OFFLINE_E2E_PROOF_FAILED",
    "STAGE30_11_4_PROOF_DECISIONS",
    "STAGE30_11_4_PROOF_PASS_DECISION",
    "is_offline_e2e_proof_decision",
    # Proof reasons.
    "PROOF_REASON_PASS_DIP_REACHED_FAKE_TRANSPORT_ONLY",
    "PROOF_REASON_UNEXPECTED_E2E_COUNTS",
    "PROOF_REASON_UNEXPECTED_TRANSPORT_ATTEMPT",
    "PROOF_REASON_INVALID_PROOF_INPUT",
    "STAGE30_11_4_PROOF_REASONS",
    "STAGE30_11_4_PROOF_PASS_REASON",
    "is_offline_e2e_proof_reason",
    # Expected baseline counts.
    "STAGE30_11_4_MIN_EXPECTED_CANDIDATES_SEEN",
    "STAGE30_11_4_EXPECTED_CANDIDATES_SEEN",
    "STAGE30_11_4_EXPECTED_BRIDGE_SUCCESSES",
    "STAGE30_11_4_EXPECTED_BRIDGE_SUPPRESSED",
    "STAGE30_11_4_EXPECTED_GATE_PASSES",
    "STAGE30_11_4_EXPECTED_GATE_SUPPRESSED",
    "STAGE30_11_4_EXPECTED_SINK_ATTEMPTS",
    "STAGE30_11_4_EXPECTED_SINK_ACCEPTS",
    "STAGE30_11_4_EXPECTED_SINK_FAILURES",
    "STAGE30_11_4_EXPECTED_TRANSPORT_ATTEMPTS",
    "STAGE30_11_4_EXPECTED_TRANSPORT_ACCEPTS",
    "STAGE30_11_4_EXPECTED_DIP_CANDIDATE_ID",
    "STAGE30_11_4_EXPECTED_DIP_TOKEN_MINT",
    # Safe-shape helper.
    "is_nonblank_str",
    # Models.
    "Stage30_11OfflineE2EProofSummary",
    "Stage30_11OfflineE2EProofResult",
    # Field-name helpers.
    "offline_e2e_proof_summary_field_names",
    "offline_e2e_proof_result_field_names",
)

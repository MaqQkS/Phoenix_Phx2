"""Stage 30.11.5 controlled live ceremony wiring models.

Stage 30.11.5 ships the passive, pure, stdlib-only MODEL layer for the
controlled-live-ceremony wiring slice: the closed-set vocabularies + carriers
the three Stage 30.11.5 logic modules share -- the live-candidate snapshot
ASSEMBLER (which turns an existing flat safe-scalar candidate projection into a
committed Stage 30.11.1 ``Stage30_11LiveCandidateSnapshot``), the private
TRANSPORT ADAPTER boundary (which renders a safe private operator payload from a
Stage 30.11.3 sink request and hands it to an INJECTED transport client), and
the BOUNDED LIVE RUNNER (which composes the assembler -> the committed Stage
30.11.2 runtime seam -> the committed Stage 30.11.3 private sink -> the injected
transport adapter under hard caps).

This module is the MODEL layer ONLY. It implements NO assembler / adapter /
runner (those are the sibling logic modules), runs NO bridge / dip gate / seam,
calls NO transport, wires into NO runtime, makes NO live provider call, sends NO
Discord message, reads NO process environment, opens NO network connection,
opens NO database, writes NO file, reserves NO real dispatch, reads NO wall
clock (``created_at_utc`` is caller-injected), and edits NO Stage 28 / Stage 29 /
Stage 30.3 / Stage 30.4 production file. Stage 30.11.5 is fake / offline only:
the real private compact dispatch / Discord send remains a SEPARATE, explicitly
operator-authorized step this slice does not build.

The slice owns three closed-set vocabularies:

  * the live-candidate assembly decision / reason -- the assembler emits exactly
    one of ``ASSEMBLED_LIVE_CANDIDATE_SNAPSHOT`` (a snapshot was built from a
    well-shaped projection; reason ``READY_FOR_BRIDGE`` -- the snapshot is the
    INPUT the committed Stage 30.11.1 bridge later consumes, NOT a bypass of it),
    ``REJECTED_MISSING_REQUIRED_FIELD`` (a required candidate field was absent /
    ``None``; reason ``MISSING_REQUIRED_CANDIDATE_FIELD``), or
    ``REJECTED_INVALID_FIELD_SHAPE`` (a present field was malformed -- a blank id,
    a non-coercible drawdown / market-cap, a non-bool verified flag; reason
    ``INVALID_CANDIDATE_FIELD_SHAPE``). A rejected projection NEVER yields a
    snapshot, so it never reaches the bridge / gate / transport.
  * the transport-client status -- the INJECTED low-level transport client the
    adapter calls returns exactly one of ``WOULD_DELIVER_PRIVATE_OPERATOR_MESSAGE``
    (a RECORDED would-deliver in the fakes, NEVER a real send) or
    ``TRANSPORT_REJECTED``.

It also pins the hard bounded-run caps the runner enforces
(``max_dispatches <= 1``, ``max_runtime_seconds <= 60``,
``max_candidates <= 10``) plus the author-verified fake-wiring proof baseline
(over the deterministic four-candidate fake source the proof drives: one PASS
dip + one non-dip + one bridge-suppressed + one assembler-rejected candidate,
the fake transport reaches the dip ONLY).

Discipline:

  * Stdlib only (``dataclasses`` / ``typing``).
  * Imports ONLY the committed Stage 30.11.1 bridge-models sibling (for the
    embedded ``Stage30_11LiveCandidateSnapshot`` type the assembly result
    carries); no other PHX2 module, no Stage 21-29 / Stage 30.3 / Stage 30.4
    orchestrator / Stage 28 suppression / live runner / provider / transport
    import. (Mirrors the Stage 30.11.1 bridge-models precedent of embedding ONE
    committed sibling type.)
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
from typing import Any, Optional, Tuple

from PHX2.stage30.stage30_11_1_live_candidate_bridge_models import (
    Stage30_11LiveCandidateSnapshot,
)


# ---------------------------------------------------------------------------
# Minor version + live wiring schema identity
# ---------------------------------------------------------------------------


STAGE30_11_5_MINOR_VERSION: str = "30.11.5"


# The Stage 30.11.5 controlled live ceremony wiring schema version. Names the
# assembly-result / payload / transport-client-result / bounded-run shapes;
# distinct from the Stage 30.11.4 end-to-end proof schema version, the Stage
# 30.11.3 private sink schema version, the Stage 30.11.2 runtime gate schema
# version, the Stage 30.11.1 bridge schema version, and the Stage 30.9.3
# integration schema version. Mirrored BY VALUE by the Stage 30.11 manifest
# section; this module imports no Stage 30.11 manifest.
STAGE30_11_5_LIVE_WIRING_SCHEMA_VERSION: str = "stage30_11_5_v0_live_wiring"


# The safe-shape source-stage provenance token the transport adapter stamps onto
# every built private operator payload (provenance only; names the adapter slice
# that produced the payload, never a secret / host / transport destination).
STAGE30_11_5_SOURCE_STAGE: str = "30.11.5"


# ---------------------------------------------------------------------------
# Candidate projection field names (the flat safe-scalar shape the assembler
# reads FROM)
# ---------------------------------------------------------------------------
#
# The assembler accepts an existing candidate as a flat MAPPING (dict) or an
# attribute-bearing object whose keys / attributes are the safe-scalar field
# names below -- a flat projection of the (deeply-nested) committed live
# assembled-candidate record the operator-authorized ceremony flattens at its
# boundary (so THIS committed slice imports no Stage 27 / 28 / 29 record type).
# The projection field names equal the Stage 30.11.1 snapshot field names BY
# VALUE; NONE is a secret, a raw payload, a host, or a transport destination.


# The required projection fields: each MUST be present (non-``None``) AND
# well-shaped, else the assembler fails closed. ``drawdown_from_ath`` and
# ``current_market_cap_usd`` must be a finite-coercible ``Decimal`` magnitude;
# the rest must be a non-blank string. (The assembler maps -- it never fabricates
# a missing drawdown / migration / ATH context, and it never forces a present
# context token to the bridge's ``PRESENT`` value.)
STAGE30_11_5_REQUIRED_PROJECTION_FIELDS: Tuple[str, ...] = (
    "candidate_id",
    "token_mint",
    "pair_type",
    "tier_hint",
    "drawdown_from_ath",
    "migration_status",
    "ath_status",
    "market_context_status",
    "current_market_cap_usd",
    "created_at_utc",
)


# The optional projection fields: ``None`` / absent is allowed (mapped to
# ``None`` on the snapshot); a present value must be well-shaped
# (``post_migration_ath_verified`` a ``bool``; ``source_ref`` a string).
STAGE30_11_5_OPTIONAL_PROJECTION_FIELDS: Tuple[str, ...] = (
    "post_migration_ath_verified",
    "source_ref",
)


# Every projection field name (required + optional), in snapshot order.
STAGE30_11_5_PROJECTION_FIELDS: Tuple[str, ...] = (
    "candidate_id",
    "token_mint",
    "pair_type",
    "tier_hint",
    "drawdown_from_ath",
    "migration_status",
    "ath_status",
    "market_context_status",
    "current_market_cap_usd",
    "post_migration_ath_verified",
    "source_ref",
    "created_at_utc",
)


# ---------------------------------------------------------------------------
# Closed-set: live-candidate assembly decision
# ---------------------------------------------------------------------------
#
# Exactly one assembly decision per candidate projection.
# ``ASSEMBLED_LIVE_CANDIDATE_SNAPSHOT`` is the only decision that carries a built
# Stage 30.11.1 ``Stage30_11LiveCandidateSnapshot``; the two reject decisions
# carry ``None``. Mirrored BY VALUE by the Stage 30.11 manifest.


ASSEMBLY_DECISION_ASSEMBLED: str = "ASSEMBLED_LIVE_CANDIDATE_SNAPSHOT"
ASSEMBLY_DECISION_REJECTED_MISSING_FIELD: str = "REJECTED_MISSING_REQUIRED_FIELD"
ASSEMBLY_DECISION_REJECTED_INVALID_SHAPE: str = "REJECTED_INVALID_FIELD_SHAPE"


STAGE30_11_5_ASSEMBLY_DECISIONS: Tuple[str, ...] = (
    ASSEMBLY_DECISION_ASSEMBLED,
    ASSEMBLY_DECISION_REJECTED_MISSING_FIELD,
    ASSEMBLY_DECISION_REJECTED_INVALID_SHAPE,
)


# The single decision that yields a built Stage 30.11.1 live candidate snapshot.
STAGE30_11_5_ASSEMBLY_PASS_DECISION: str = ASSEMBLY_DECISION_ASSEMBLED


def is_assembly_decision(value: object) -> bool:
    """Return ``True`` iff ``value`` is a closed-set assembly decision.

    Pure / total; never raises.
    """
    return isinstance(value, str) and value in STAGE30_11_5_ASSEMBLY_DECISIONS


# ---------------------------------------------------------------------------
# Closed-set: live-candidate assembly reason
# ---------------------------------------------------------------------------
#
# Exactly one assembly reason per decision. ``READY_FOR_BRIDGE`` is the only
# reason that accompanies a built snapshot; it names the snapshot as the INPUT
# the committed Stage 30.11.1 bridge later consumes, NEVER a bypass of it.
# Mirrored BY VALUE by the Stage 30.11 manifest.


ASSEMBLY_REASON_READY_FOR_BRIDGE: str = "READY_FOR_BRIDGE"
ASSEMBLY_REASON_MISSING_REQUIRED_FIELD: str = "MISSING_REQUIRED_CANDIDATE_FIELD"
ASSEMBLY_REASON_INVALID_FIELD_SHAPE: str = "INVALID_CANDIDATE_FIELD_SHAPE"


STAGE30_11_5_ASSEMBLY_REASONS: Tuple[str, ...] = (
    ASSEMBLY_REASON_READY_FOR_BRIDGE,
    ASSEMBLY_REASON_MISSING_REQUIRED_FIELD,
    ASSEMBLY_REASON_INVALID_FIELD_SHAPE,
)


# The single reason that accompanies the only assembled decision.
STAGE30_11_5_ASSEMBLY_PASS_REASON: str = ASSEMBLY_REASON_READY_FOR_BRIDGE


def is_assembly_reason(value: object) -> bool:
    """Return ``True`` iff ``value`` is a closed-set assembly reason.

    Pure / total; never raises.
    """
    return isinstance(value, str) and value in STAGE30_11_5_ASSEMBLY_REASONS


# ---------------------------------------------------------------------------
# Closed-set: transport-client status
# ---------------------------------------------------------------------------
#
# Exactly one transport-client status per call of the INJECTED low-level
# transport client. ``WOULD_DELIVER_PRIVATE_OPERATOR_MESSAGE`` is the only status
# on which the client accepted the payload; it names a RECORDED would-deliver (in
# the fakes the client recorded the payload), NEVER a real send. Mirrored BY
# VALUE by the Stage 30.11 manifest.


TRANSPORT_STATUS_WOULD_DELIVER: str = "WOULD_DELIVER_PRIVATE_OPERATOR_MESSAGE"
TRANSPORT_STATUS_REJECTED: str = "TRANSPORT_REJECTED"


STAGE30_11_5_TRANSPORT_STATUSES: Tuple[str, ...] = (
    TRANSPORT_STATUS_WOULD_DELIVER,
    TRANSPORT_STATUS_REJECTED,
)


# The single status on which the injected transport client accepted the payload.
STAGE30_11_5_TRANSPORT_ACCEPT_STATUS: str = TRANSPORT_STATUS_WOULD_DELIVER


def is_transport_status(value: object) -> bool:
    """Return ``True`` iff ``value`` is a closed-set transport-client status.

    Pure / total; never raises.
    """
    return isinstance(value, str) and value in STAGE30_11_5_TRANSPORT_STATUSES


# ---------------------------------------------------------------------------
# Hard bounded-run caps + defaults
# ---------------------------------------------------------------------------
#
# The bounded live runner enforces these HARD ceilings on its runtime config (a
# config above any ceiling fails closed). The defaults equal the ceilings; the
# dispatch default is the single-send default the controlled ceremony requires.
# The caps are plain ``int`` seconds / counts (this models module carries NO
# module-level Call node, so it builds no module-level ``Decimal``); the runner's
# ``default_bounded_run_config`` wraps the runtime-seconds default into a
# ``Decimal`` at call time, and the committed Stage 30.11.2 seam measures elapsed
# seconds via an INJECTED clock against the bound (a ``Decimal`` >= ``int``
# comparison is exact). The runner reads no wall clock.


STAGE30_11_5_MAX_DISPATCHES_HARD_CAP: int = 1
STAGE30_11_5_MAX_RUNTIME_SECONDS_HARD_CAP: int = 60
STAGE30_11_5_MAX_CANDIDATES_HARD_CAP: int = 10


STAGE30_11_5_DEFAULT_MAX_DISPATCHES: int = 1
STAGE30_11_5_DEFAULT_MAX_RUNTIME_SECONDS: int = 60
STAGE30_11_5_DEFAULT_MAX_CANDIDATES: int = 10


# ---------------------------------------------------------------------------
# Author-verified fake-wiring proof baseline (the deterministic fake source)
# ---------------------------------------------------------------------------
#
# The Stage 30.11.5 fake live wiring proof drives a deterministic FOUR-candidate
# fake source through the bounded runner with an INJECTED recording fake
# transport client + an injected constant clock: one non-dip + one
# bridge-suppressed (a present-but-not-``PRESENT`` ATH context) + one Tier 1 dip
# + one assembler-rejected candidate (a required field absent). The baseline:
# four source items seen, exactly three assembled (the rejected one never becomes
# a snapshot), exactly three reach the seam, exactly two bridge, exactly one
# passes the committed dip gate, exactly one dispatch attempt + accept, exactly
# one fake transport attempt + accept -- for the dip (``cand-tier1`` /
# ``mint-tier1``) ONLY. The non-dip is suppressed by the dip gate, the
# bridge-suppressed by the bridge, the rejected one by the assembler, so none
# reaches the transport; no cap / wall-clock bound is tripped. Mirrored BY VALUE
# by the Stage 30.11 manifest. NONE is a secret, a raw payload, a host, or a
# transport destination.


STAGE30_11_5_EXPECTED_SOURCE_ITEMS_SEEN: int = 4
STAGE30_11_5_EXPECTED_ASSEMBLED: int = 3
STAGE30_11_5_EXPECTED_ASSEMBLY_REJECTED: int = 1
STAGE30_11_5_EXPECTED_CANDIDATES_SEEN: int = 3
STAGE30_11_5_EXPECTED_BRIDGED: int = 2
STAGE30_11_5_EXPECTED_GATE_PASSED: int = 1
STAGE30_11_5_EXPECTED_DISPATCH_ATTEMPTED: int = 1
STAGE30_11_5_EXPECTED_DISPATCH_ACCEPTED: int = 1
STAGE30_11_5_EXPECTED_SUPPRESSED_BY_BRIDGE: int = 1
STAGE30_11_5_EXPECTED_SUPPRESSED_BY_GATE: int = 1
STAGE30_11_5_EXPECTED_TRANSPORT_ATTEMPTS: int = 1
STAGE30_11_5_EXPECTED_TRANSPORT_ACCEPTS: int = 1


# The exact safe-shape identity of the single dip the fake transport is allowed
# to see. No other candidate id / token mint may reach the transport.
STAGE30_11_5_EXPECTED_DIP_CANDIDATE_ID: str = "cand-tier1"
STAGE30_11_5_EXPECTED_DIP_TOKEN_MINT: str = "mint-tier1"


# ---------------------------------------------------------------------------
# Pure safe-shape helper
# ---------------------------------------------------------------------------


def is_nonblank_str(value: object) -> bool:
    """Return ``True`` iff ``value`` is a non-empty, non-blank string.

    A missing (``None``), non-string, empty, or whitespace-only value is NOT a
    usable safe-shape token. Pure / total; never raises. Mirrors the Stage
    30.11.1 / 30.11.3 / 30.11.4 non-blank check BY VALUE; the slice consults it
    to validate ids / status tokens / timestamps.
    """
    return isinstance(value, str) and value.strip() != ""


# ---------------------------------------------------------------------------
# Immutable model: per-candidate live-candidate assembly result
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Stage30_11_5LiveCandidateAssemblyResult:
    """Immutable per-candidate Stage 30.11.5 live-candidate assembly result.

    The assembler emits exactly one of these per candidate projection. It echoes
    the safe-shape candidate identity, pins the closed-set ``assembly_decision`` /
    ``assembly_reason``, names the first offending projection field on a reject
    (a safe FIELD NAME only, never a field VALUE; ``""`` when assembled), and
    carries the built committed Stage 30.11.1 ``Stage30_11LiveCandidateSnapshot``
    (ONLY for an ``ASSEMBLED_LIVE_CANDIDATE_SNAPSHOT`` decision; ``None``
    otherwise). Carries only safe scalars + the embedded snapshot + a
    caller-injected timestamp; no secret, no raw payload, no host, no transport
    destination, no env value. The assembler does NOT run the bridge / dip gate /
    transport -- the snapshot is the INPUT the committed Stage 30.11.1 bridge
    later consumes.

      * ``candidate_id`` / ``token_mint`` -- echoed safe-shape ids (``""`` when
                                             unreadable from the projection).
      * ``assembly_decision``             -- one of
                                             ``STAGE30_11_5_ASSEMBLY_DECISIONS``.
      * ``assembly_reason``               -- one of
                                             ``STAGE30_11_5_ASSEMBLY_REASONS``.
      * ``rejected_field``                -- the safe field NAME that failed
                                             closed (one of
                                             ``STAGE30_11_5_PROJECTION_FIELDS``),
                                             or ``""`` when assembled.
      * ``snapshot``                      -- the built committed Stage 30.11.1
                                             ``Stage30_11LiveCandidateSnapshot``
                                             (only for an ASSEMBLED decision;
                                             ``None`` for a reject).
      * ``created_at_utc``                -- caller-injected ISO-8601 UTC
                                             timestamp for the assembly run;
                                             NEVER a wall-clock read.
    """

    candidate_id: str
    token_mint: str
    assembly_decision: str
    assembly_reason: str
    rejected_field: str
    snapshot: Optional[Stage30_11LiveCandidateSnapshot]
    created_at_utc: str


# ---------------------------------------------------------------------------
# Immutable model: private operator payload (transport-adapter side)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Stage30_11_5PrivateOperatorPayload:
    """Immutable adapter-side private operator payload.

    The SAFE payload the Stage 30.11.5 private transport adapter renders from a
    committed Stage 30.11.3 ``Stage30_11PrivateSinkRequest`` and hands to the
    INJECTED low-level transport client. It carries only safe scalars: opaque
    ids, an optional opaque candidate ref, the display tier token, the rendered
    operator body (echoed from the sink request's compact body), a caller-injected
    timestamp, and the source-stage provenance token. No secret, no raw provider
    payload, no host, no transport destination, no env value. The real transport
    client (the thing that would perform a real send) is ALWAYS injected; this
    payload carries no destination of its own.

      * ``candidate_id`` / ``token_mint`` -- echoed safe-shape ids.
      * ``candidate_ref``                 -- the OPTIONAL opaque candidate ref, or
                                             ``None``.
      * ``tier_token``                    -- the echoed display tier token, or
                                             ``None``.
      * ``body``                          -- the rendered safe operator body (a
                                             display string only; never a secret /
                                             host / transport destination).
      * ``source_stage``                  -- the safe-shape source-stage
                                             provenance token (``30.11.5``).
      * ``created_at_utc``                -- caller-injected ISO-8601 UTC
                                             timestamp; NEVER a wall-clock read.
    """

    candidate_id: str
    token_mint: str
    candidate_ref: Optional[str]
    tier_token: Optional[str]
    body: str
    source_stage: str
    created_at_utc: str


# ---------------------------------------------------------------------------
# Immutable model: low-level transport-client result
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Stage30_11_5TransportClientResult:
    """Immutable result of the INJECTED low-level transport client.

    The return value of the transport client the private transport adapter
    calls: a passive verdict that records whether the client accepted the payload
    plus a closed-set status token + the echoed candidate identity. It is NOT a
    real transport result -- it carries NO status code, NO response body, NO host,
    NO transport destination, NO secret. In THIS slice the client is ALWAYS an
    in-memory recording FAKE; the real private compact dispatch / Discord send
    remains a SEPARATE, operator-authorized step Stage 30.11.5 does not build.

      * ``accepted``       -- whether the client accepted the payload.
      * ``transport_status``-- one of ``STAGE30_11_5_TRANSPORT_STATUSES``
                              (``WOULD_DELIVER_PRIVATE_OPERATOR_MESSAGE`` names a
                              RECORDED would-deliver, NEVER a real send).
      * ``candidate_id`` / ``token_mint`` -- echoed safe-shape ids.
      * ``created_at_utc`` -- caller-injected ISO-8601 UTC timestamp; NEVER a
                              wall-clock read.
    """

    accepted: bool
    transport_status: str
    candidate_id: str
    token_mint: str
    created_at_utc: str


# ---------------------------------------------------------------------------
# Immutable model: bounded-run proof summary
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Stage30_11_5BoundedRunSummary:
    """Immutable Stage 30.11.5 bounded live runner proof tally.

    A passive summary of one bounded run of the composed wiring (source ->
    assembler -> committed Stage 30.11.2 runtime seam -> committed Stage 30.11.3
    private sink -> INJECTED transport adapter -> injected transport client). It
    proves, by counting, that ONLY a candidate that assembled, bridged, AND
    passed the committed dip gate drove a transport would-deliver, that every
    assembler-rejected / bridge-skip / non-dip candidate was suppressed cleanly
    BEFORE the transport, and that the hard caps held. Carries only non-negative
    integer counts + a caller-injected timestamp; no secret, no payload, no host,
    no transport destination.

      * ``source_items_seen``           -- candidate projections taken from the
                                           bounded source (<= ``max_candidates``).
      * ``assembled``                   -- count the assembler built a snapshot.
      * ``assembly_rejected``           -- count the assembler rejected (no
                                           snapshot; never reached the seam).
      * ``candidates_seen``             -- assembled snapshots evaluated by the
                                           committed seam.
      * ``bridged``                     -- count the committed bridge BRIDGED.
      * ``gate_passed``                 -- count the committed dip gate ruled
                                           PASS_TO_DISPATCH.
      * ``dispatch_attempted``          -- count the private sink was invoked.
      * ``dispatch_accepted``           -- count the private sink recorded an
                                           accepted would-deliver.
      * ``suppressed_by_bridge``        -- count the bridge skipped / failed
                                           closed.
      * ``suppressed_by_gate``          -- count bridged but the dip gate did NOT
                                           pass.
      * ``stopped_by_candidate_cap``    -- 1 iff the seam candidate cap stopped
                                           the run.
      * ``stopped_by_dispatch_cap``     -- 1 iff the seam dispatch cap stopped the
                                           run.
      * ``stopped_by_runtime_seconds``  -- 1 iff the wall-clock bound stopped the
                                           run.
      * ``created_at_utc``              -- caller-injected ISO-8601 UTC timestamp.
    """

    source_items_seen: int
    assembled: int
    assembly_rejected: int
    candidates_seen: int
    bridged: int
    gate_passed: int
    dispatch_attempted: int
    dispatch_accepted: int
    suppressed_by_bridge: int
    suppressed_by_gate: int
    stopped_by_candidate_cap: int
    stopped_by_dispatch_cap: int
    stopped_by_runtime_seconds: int
    created_at_utc: str


# ---------------------------------------------------------------------------
# Immutable model: bounded-run result
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Stage30_11_5BoundedRunResult:
    """Immutable Stage 30.11.5 bounded live runner result.

    The runner emits exactly one of these per bounded run. It carries the ordered
    per-candidate assembly results, the ordered runtime outcomes the committed
    seam emitted (held as opaque records BY VALUE -- the model imports no Stage
    30.11.2 outcome type), and the rolled-up ``Stage30_11_5BoundedRunSummary``.
    Carries only safe scalars + the embedded results + a caller-injected
    timestamp; no secret, no raw payload, no host, no transport destination, no
    env value.

      * ``assembly_outcomes`` -- the ordered per-candidate Stage 30.11.5 assembly
                                 results.
      * ``runtime_outcomes``  -- the ordered committed runtime outcome records
                                 (opaque carrier; the model imports no Stage
                                 30.11.2 outcome type).
      * ``summary``           -- the embedded ``Stage30_11_5BoundedRunSummary``.
      * ``created_at_utc``    -- caller-injected ISO-8601 UTC timestamp; NEVER a
                                 wall-clock read.
    """

    assembly_outcomes: Tuple[Stage30_11_5LiveCandidateAssemblyResult, ...]
    runtime_outcomes: Tuple[Any, ...]
    summary: Stage30_11_5BoundedRunSummary
    created_at_utc: str


# ---------------------------------------------------------------------------
# Field-name helpers (pure; read dataclass field names)
# ---------------------------------------------------------------------------


def live_candidate_assembly_result_field_names() -> Tuple[str, ...]:
    """Return the live-candidate assembly result field names as a tuple."""
    return tuple(f.name for f in fields(Stage30_11_5LiveCandidateAssemblyResult))


def private_operator_payload_field_names() -> Tuple[str, ...]:
    """Return the private operator payload field names as a tuple."""
    return tuple(f.name for f in fields(Stage30_11_5PrivateOperatorPayload))


def transport_client_result_field_names() -> Tuple[str, ...]:
    """Return the transport-client result field names as a tuple."""
    return tuple(f.name for f in fields(Stage30_11_5TransportClientResult))


def bounded_run_summary_field_names() -> Tuple[str, ...]:
    """Return the bounded-run summary field names as a tuple."""
    return tuple(f.name for f in fields(Stage30_11_5BoundedRunSummary))


def bounded_run_result_field_names() -> Tuple[str, ...]:
    """Return the bounded-run result field names as a tuple."""
    return tuple(f.name for f in fields(Stage30_11_5BoundedRunResult))


__all__ = (
    # Minor version + live wiring schema identity.
    "STAGE30_11_5_MINOR_VERSION",
    "STAGE30_11_5_LIVE_WIRING_SCHEMA_VERSION",
    "STAGE30_11_5_SOURCE_STAGE",
    # Candidate projection field names.
    "STAGE30_11_5_REQUIRED_PROJECTION_FIELDS",
    "STAGE30_11_5_OPTIONAL_PROJECTION_FIELDS",
    "STAGE30_11_5_PROJECTION_FIELDS",
    # Assembly decisions.
    "ASSEMBLY_DECISION_ASSEMBLED",
    "ASSEMBLY_DECISION_REJECTED_MISSING_FIELD",
    "ASSEMBLY_DECISION_REJECTED_INVALID_SHAPE",
    "STAGE30_11_5_ASSEMBLY_DECISIONS",
    "STAGE30_11_5_ASSEMBLY_PASS_DECISION",
    "is_assembly_decision",
    # Assembly reasons.
    "ASSEMBLY_REASON_READY_FOR_BRIDGE",
    "ASSEMBLY_REASON_MISSING_REQUIRED_FIELD",
    "ASSEMBLY_REASON_INVALID_FIELD_SHAPE",
    "STAGE30_11_5_ASSEMBLY_REASONS",
    "STAGE30_11_5_ASSEMBLY_PASS_REASON",
    "is_assembly_reason",
    # Transport-client statuses.
    "TRANSPORT_STATUS_WOULD_DELIVER",
    "TRANSPORT_STATUS_REJECTED",
    "STAGE30_11_5_TRANSPORT_STATUSES",
    "STAGE30_11_5_TRANSPORT_ACCEPT_STATUS",
    "is_transport_status",
    # Hard caps + defaults.
    "STAGE30_11_5_MAX_DISPATCHES_HARD_CAP",
    "STAGE30_11_5_MAX_RUNTIME_SECONDS_HARD_CAP",
    "STAGE30_11_5_MAX_CANDIDATES_HARD_CAP",
    "STAGE30_11_5_DEFAULT_MAX_DISPATCHES",
    "STAGE30_11_5_DEFAULT_MAX_RUNTIME_SECONDS",
    "STAGE30_11_5_DEFAULT_MAX_CANDIDATES",
    # Fake-wiring proof baseline.
    "STAGE30_11_5_EXPECTED_SOURCE_ITEMS_SEEN",
    "STAGE30_11_5_EXPECTED_ASSEMBLED",
    "STAGE30_11_5_EXPECTED_ASSEMBLY_REJECTED",
    "STAGE30_11_5_EXPECTED_CANDIDATES_SEEN",
    "STAGE30_11_5_EXPECTED_BRIDGED",
    "STAGE30_11_5_EXPECTED_GATE_PASSED",
    "STAGE30_11_5_EXPECTED_DISPATCH_ATTEMPTED",
    "STAGE30_11_5_EXPECTED_DISPATCH_ACCEPTED",
    "STAGE30_11_5_EXPECTED_SUPPRESSED_BY_BRIDGE",
    "STAGE30_11_5_EXPECTED_SUPPRESSED_BY_GATE",
    "STAGE30_11_5_EXPECTED_TRANSPORT_ATTEMPTS",
    "STAGE30_11_5_EXPECTED_TRANSPORT_ACCEPTS",
    "STAGE30_11_5_EXPECTED_DIP_CANDIDATE_ID",
    "STAGE30_11_5_EXPECTED_DIP_TOKEN_MINT",
    # Safe-shape helper.
    "is_nonblank_str",
    # Models.
    "Stage30_11_5LiveCandidateAssemblyResult",
    "Stage30_11_5PrivateOperatorPayload",
    "Stage30_11_5TransportClientResult",
    "Stage30_11_5BoundedRunSummary",
    "Stage30_11_5BoundedRunResult",
    # Field-name helpers.
    "live_candidate_assembly_result_field_names",
    "private_operator_payload_field_names",
    "transport_client_result_field_names",
    "bounded_run_summary_field_names",
    "bounded_run_result_field_names",
)

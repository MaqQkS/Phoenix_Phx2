"""Stage 30.11.23 discovered migration-evidence -> candidate + evidence bridge models.

Stage 30.11.23 ships the passive, pure, stdlib-only MODEL layer for the committed
OFFLINE bridge that removes the LAST manual input the Stage 30.11.22 real-fed dry
run still required: a hand-fed candidate mint + migration anchor (``CURATED_MINT`` /
``CURATED_MIGRATION_TIME_UTC``). Stage 30.11.22 proved the fundamentals chain with
REAL provider reads + a FAKE dispatch, but the operator still had to type the
candidate mint AND keep it in sync with a hand-built migration-evidence record.
Stage 30.11.23 derives BOTH sides from ONE committed Stage 29.5.7 sanitized
migration-evidence summary (the operator's out-of-repo migration-evidence producer
emits it), so the candidate mint and its evidence physically cannot desync and
neither is typed by a human.

It ships only the carriers + closed-set vocabularies + pure safe-shape predicates
the sibling adapter composes:

  * the closed-set per-summary BRIDGE decision vocabulary -- ``BRIDGED_CANDIDATE_AND
    _EVIDENCE`` (the only pass token: the summary yielded BOTH a discovered-candidate
    carrier AND a bound migration-evidence record) or one of the ``SKIPPED_*``
    presence / shape / measurement / redaction / warnings / duplicate tokens (the
    summary becomes neither a candidate nor an evidence record);
  * the discovered-candidate carrier (the harvest EVENT the bridge emits per bridged
    summary -- carries ONLY the validated, safe-shape token mint; the run-scoped
    ``candidate_id`` is assigned LATER by the committed Stage 30.11.6 harvest loop,
    NOT here) and the assembled-candidate carrier (what the trivial assembler returns
    for the flattener to flatten);
  * the per-summary redaction-safe BRIDGE event (a record carrying ONLY the
    zero-based index, the closed-set decision token, the safe-echo token mint, and a
    caller-injected timestamp -- never a ``source_ref``, never an anchor, never a
    measurement / redaction value, never a magnitude, body, url, or secret);
  * the rolled-up BRIDGE report (the ordered bridge events + the non-negative counts
    + the combined redaction status + a caller-injected timestamp);
  * the real-fed INPUTS bundle (the four values the committed Stage 30.11.22 wrapper
    takes injected -- the discovered-candidate event stream, the trivial assembler,
    the placeholder flattener, the mint-keyed Stage 30.11.9 evidence source -- plus
    the embedded bridge report). All four are derived from ONE summary list in ONE
    call, so the candidate set and the evidence set are guaranteed consistent;
  * the COMPLETE / SAFE Layer-0 routing-hygiene tokens the bridge screens on (they
    MIRROR the committed Stage 30.11.8 confirmation but NEVER replace it -- migration
    confirmation still belongs to the committed Stage 30.11.8 / Stage 30.11.21
    downstream; these only stop an obviously-doomed summary from consuming a candidate
    slot and give a precise bridge-level skip reason);
  * the inert candidate-projection placeholders the flattener stamps (the committed
    Stage 30.11.22 bridge reads ONLY ``token_mint`` + ``candidate_id`` and discards
    every other field, so these are shape-satisfiers only -- never enrichment data);
  * the pure safe-shape predicates the adapter composes.

This module is the MODEL layer ONLY. It builds NO bundle, runs NO bridge, reads NO
summary, drives NO evidence source, calls NO transport, sends NO message, reads NO
process environment, opens NO network connection, opens NO database, writes NO file,
parses no clock, and edits NO harvest / enrichment / composer / dedupe / ledger /
evidence-source file. Stage 30.11.23 is fake / offline / no-send only: the real
Stage 29.5.7 migration-evidence producer (an out-of-repo WebSocket / RPC capture),
the real-fed dry-run ceremony, and the controlled capped private send remain a
SEPARATE, explicitly operator-authorized step this slice does not run.

Discipline:

  * Stdlib only (``dataclasses`` / ``typing``).
  * Imports NO PHX2 module (a pure leaf; mirrors the Stage 30.11.22 / 30.11.21 model
    modules). The Stage 29.5.7 sanitized migration-evidence summary is consumed
    DUCK-TYPED by the sibling adapter -- the Stage 29 type is NEVER imported (the
    leaf boundary forbids Stage 21-29 imports).
  * No ``os.environ`` / ``os.getenv`` access; no env read.
  * No network, no socket; no database / SQLite, no compression.
  * No live provider, transport-destination, url, host, or request-metadata
    reference; no wallet / signing / trading surface; no public / subscriber
    routing.
  * No PHX1 import. No Stage 21-29 production import.
  * No ``time`` / ``datetime`` import; timestamps are caller-injected.
  * No module-level Call node (no implicit I/O at import time; the
    ``@dataclass(frozen=True)`` decorators are decorator-list Calls, not
    body-statement Calls).
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from typing import Any, Tuple


# ---------------------------------------------------------------------------
# Minor version + schema identity
# ---------------------------------------------------------------------------


STAGE30_11_23_MINOR_VERSION: str = "30.11.23"


# The Stage 30.11.23 report schema version. Names the bridge-event / bridge-report /
# real-fed-inputs shapes; distinct from every earlier Stage 30.11 schema version.
# Mirrored BY VALUE by the Stage 30.11 manifest section; this module imports no
# manifest.
STAGE30_11_23_REPORT_SCHEMA_VERSION: str = (
    "stage30_11_23_v0_migration_evidence_candidate_bridge"
)


# The safe-shape source-stage provenance token (names the slice; never a secret /
# host / transport destination).
STAGE30_11_23_SOURCE_STAGE: str = "30.11.23"


# ---------------------------------------------------------------------------
# COMPLETE / SAFE Layer-0 routing-hygiene tokens (mirrored BY VALUE)
# ---------------------------------------------------------------------------
#
# The bridge screens a summary's ``measurement_status`` against ``COMPLETE`` and its
# ``redaction_status`` against ``SAFE`` purely as Layer-0 routing hygiene: it stops a
# summary that can never confirm from consuming a candidate slot and gives a precise
# bridge-level skip reason. These MIRROR the committed Stage 30.11.8 confirmation's
# required tokens BY VALUE but NEVER replace it -- the migration verdict is the
# committed Stage 30.11.8 / Stage 30.11.21 chain's to decide, and it independently
# re-checks COMPLETE / SAFE / staleness / the trailing-Z anchor on every bridged
# summary's carried-verbatim evidence record. (The committed Stage 29.5.7 producer
# emits only COMPLETE / SAFE summaries, so these screens are conservative.)


STAGE30_11_23_EXPECTED_MEASUREMENT_STATUS: str = "COMPLETE"
STAGE30_11_23_EXPECTED_REDACTION_STATUS: str = "SAFE"


# ---------------------------------------------------------------------------
# Closed-set: per-summary bridge decision
# ---------------------------------------------------------------------------
#
# Exactly one decision per scanned summary. ``BRIDGED_CANDIDATE_AND_EVIDENCE`` is the
# ONLY decision on which the bridge emitted BOTH a discovered-candidate carrier AND a
# bound migration-evidence record; every ``SKIPPED_*`` decision is a fail-closed
# Layer-0 rejection that yields neither. The COMPLETE / SAFE / warnings screens MIRROR
# but never replace the committed Stage 30.11.8 confirmation. Mirrored BY VALUE by the
# Stage 30.11 manifest.


BRIDGE_DECISION_BRIDGED: str = "BRIDGED_CANDIDATE_AND_EVIDENCE"
BRIDGE_DECISION_SKIPPED_NOT_A_SUMMARY: str = "SKIPPED_NOT_A_SUMMARY"
BRIDGE_DECISION_SKIPPED_MISSING_TOKEN_MINT: str = "SKIPPED_MISSING_TOKEN_MINT"
BRIDGE_DECISION_SKIPPED_INVALID_TOKEN_MINT: str = "SKIPPED_INVALID_TOKEN_MINT"
BRIDGE_DECISION_SKIPPED_MISSING_MIGRATION_TIME: str = (
    "SKIPPED_MISSING_MIGRATION_TIME"
)
BRIDGE_DECISION_SKIPPED_NOT_COMPLETE_MEASUREMENT: str = (
    "SKIPPED_NOT_COMPLETE_MEASUREMENT"
)
BRIDGE_DECISION_SKIPPED_UNSAFE_REDACTION: str = "SKIPPED_UNSAFE_REDACTION"
BRIDGE_DECISION_SKIPPED_MALFORMED_WARNINGS: str = "SKIPPED_MALFORMED_WARNINGS"
BRIDGE_DECISION_SKIPPED_EVIDENCE_UNBUILDABLE: str = (
    "SKIPPED_EVIDENCE_UNBUILDABLE"
)
BRIDGE_DECISION_SKIPPED_DUPLICATE_MINT: str = "SKIPPED_DUPLICATE_MINT"


STAGE30_11_23_BRIDGE_DECISIONS: Tuple[str, ...] = (
    BRIDGE_DECISION_BRIDGED,
    BRIDGE_DECISION_SKIPPED_NOT_A_SUMMARY,
    BRIDGE_DECISION_SKIPPED_MISSING_TOKEN_MINT,
    BRIDGE_DECISION_SKIPPED_INVALID_TOKEN_MINT,
    BRIDGE_DECISION_SKIPPED_MISSING_MIGRATION_TIME,
    BRIDGE_DECISION_SKIPPED_NOT_COMPLETE_MEASUREMENT,
    BRIDGE_DECISION_SKIPPED_UNSAFE_REDACTION,
    BRIDGE_DECISION_SKIPPED_MALFORMED_WARNINGS,
    BRIDGE_DECISION_SKIPPED_EVIDENCE_UNBUILDABLE,
    BRIDGE_DECISION_SKIPPED_DUPLICATE_MINT,
)


# The single decision that yields a bridged candidate + evidence record.
STAGE30_11_23_BRIDGE_PASS_DECISION: str = BRIDGE_DECISION_BRIDGED


def is_bridge_decision(value: object) -> bool:
    """Return ``True`` iff ``value`` is a closed-set per-summary bridge decision.

    Pure / total; never raises.
    """
    return isinstance(value, str) and value in STAGE30_11_23_BRIDGE_DECISIONS


# ---------------------------------------------------------------------------
# Redaction status tokens + safe placeholder
# ---------------------------------------------------------------------------
#
# The bridge self-scans its own bridge-event string fields: ``REDACTED`` when every
# field is safe (the normal path -- the bridge builds only closed-set tokens +
# safe-echo mints + injected timestamps), else ``REDACTION_VIOLATION``. A token mint
# that is not a safe-echo token is replaced by ``REDACTED_UNSAFE_ID`` rather than
# echoed raw, so a forged mint can never smuggle injected text into the report.


STAGE30_11_23_REDACTION_STATUS_REDACTED: str = "REDACTED"
STAGE30_11_23_REDACTION_STATUS_VIOLATION: str = "REDACTION_VIOLATION"
STAGE30_11_23_REDACTED_UNSAFE_ID: str = "REDACTED_UNSAFE_ID"


STAGE30_11_23_REDACTION_STATUSES: Tuple[str, ...] = (
    STAGE30_11_23_REDACTION_STATUS_REDACTED,
    STAGE30_11_23_REDACTION_STATUS_VIOLATION,
)


# ---------------------------------------------------------------------------
# Hard summary-scan cap + default + inert candidate-projection placeholders
# ---------------------------------------------------------------------------
#
# The bridge scans AT MOST ``max_summaries`` summaries in a single BOUNDED for-loop
# (no ``while`` loop, no daemon). The hard cap mirrors the committed Stage 30.11.6
# ``max_harvest <= 10`` / Stage 30.11.17 ``max_candidates <= 10`` ceilings so the
# discovered ``candidate_source`` can never exceed what the bounded chain is allowed
# to evaluate. A ``max_summaries`` above the cap fails closed BEFORE scanning anything.


STAGE30_11_23_MAX_SUMMARIES_HARD_CAP: int = 10
STAGE30_11_23_DEFAULT_MAX_SUMMARIES: int = 10


# The inert placeholders the flattener stamps onto the candidate-projection fields the
# committed Stage 30.11.22 bridge DISCARDS (it reads only ``token_mint`` +
# ``candidate_id`` and stamps its own ``PENDING_ENRICHMENT`` / ``PENDING`` sentinels;
# the enrichment fills the real values). ``..._PLACEHOLDER_STATUS`` fills the required
# non-blank string fields (``pair_type`` / ``tier_hint`` / ``migration_status`` /
# ``ath_status`` / ``market_context_status``); ``..._PLACEHOLDER_DECIMAL`` fills the
# required finite-``Decimal``-coercible fields (``drawdown_from_ath`` /
# ``current_market_cap_usd``) -- these MUST be numeric (a non-numeric sentinel would
# fail the committed Stage 30.11.6 projection's Decimal coercion). NEITHER ever reaches
# the composer; both are shape-satisfiers required by the committed projection
# contract, not data.
STAGE30_11_23_PLACEHOLDER_STATUS: str = "PENDING"
STAGE30_11_23_PLACEHOLDER_DECIMAL: str = "0"


# ---------------------------------------------------------------------------
# Pure safe-shape predicates
# ---------------------------------------------------------------------------


def is_nonblank_str(value: object) -> bool:
    """Return ``True`` iff ``value`` is a non-empty, non-blank string.

    Pure / total; never raises. Mirrors the Stage 30.11.22 / 30.11.18 non-blank
    check BY VALUE.
    """
    return isinstance(value, str) and value.strip() != ""


def is_safe_echo_id(value: object) -> bool:
    """Return ``True`` iff ``value`` is a safe-to-echo opaque token.

    A safe-echo token is a non-empty string of length 1..128 made ONLY of ASCII
    letters / digits / ``_`` / ``-``. A base58 token mint and an underscore
    candidate id both pass; any newline / control char / whitespace / path / url /
    quote / scheme character (or an over-long value) fails. It gates the token mints
    the bridge echoes into its redaction-safe bridge events -- an unsafe value is
    replaced by ``STAGE30_11_23_REDACTED_UNSAFE_ID`` rather than echoed raw. Mirrors
    the Stage 30.11.22 / 30.11.18 ``is_safe_echo_id`` BY VALUE. Pure / total; never
    raises.
    """
    if not isinstance(value, str):
        return False
    if value == "" or len(value) > 128:
        return False
    for ch in value:
        if "A" <= ch <= "Z":
            continue
        if "a" <= ch <= "z":
            continue
        if "0" <= ch <= "9":
            continue
        if ch == "_" or ch == "-":
            continue
        return False
    return True


# ---------------------------------------------------------------------------
# Immutable model: one discovered-candidate harvest event
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Stage30_11_23DiscoveredCandidate:
    """Immutable discovered-candidate harvest event.

    The bridge emits exactly one of these per BRIDGED summary; the tuple of them is
    the ``events`` the committed Stage 30.11.6 harvest seam (driven by the committed
    Stage 30.11.22 wrapper) consumes. It carries ONLY the validated, safe-shape token
    mint -- the on-chain identity discovered from the migration evidence. The
    run-scoped ``candidate_id`` is NOT carried here: the committed Stage 30.11.6
    harvest loop stamps a deterministic ``f"{prefix}{index:06d}"`` id and passes it to
    the assembler, so this carrier deliberately holds no id (and no magnitude, no
    anchor, no secret).

      * ``token_mint`` -- the discovered base mint (the candidate identity AND the
                          mint-keyed evidence-source key; the same string both sides).
    """

    token_mint: str


# ---------------------------------------------------------------------------
# Immutable model: one assembled discovered candidate
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Stage30_11_23AssembledCandidate:
    """Immutable assembled discovered candidate.

    What the trivial Stage 30.11.23 assembler returns for the flattener to flatten:
    the assembly of a migration-discovered candidate is identity (the discovered mint
    IS the candidate identity), so this pairs the discovered token mint with the
    run-scoped ``candidate_id`` the committed Stage 30.11.6 harvest loop assigned.
    Carries ONLY safe-shape ids; no magnitude, no anchor, no secret.

      * ``token_mint``   -- the discovered base mint (carried verbatim).
      * ``candidate_id`` -- the run-scoped harvest id the committed Stage 30.11.6 loop
                            stamped (``f"{prefix}{index:06d}"``).
    """

    token_mint: str
    candidate_id: str


# ---------------------------------------------------------------------------
# Immutable model: one per-summary redaction-safe bridge event
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Stage30_11_23BridgeEvent:
    """Immutable redaction-safe per-summary bridge event.

    The bridge emits exactly one of these per scanned summary. It pins the zero-based
    index + the closed-set ``decision`` + the safe-echo token mint; it carries ONLY
    safe scalars + a closed-set token: NO ``candidate_id`` (not known at bridge time),
    NO ``source_ref``, NO migration anchor, NO measurement / redaction value, NO
    magnitude, body, url, exception text, or secret.

      * ``index``          -- the zero-based position in the scanned order.
      * ``decision``       -- one of ``STAGE30_11_23_BRIDGE_DECISIONS``.
      * ``token_mint``     -- echoed safe-shape mint (``""`` when unreadable;
                              ``REDACTED_UNSAFE_ID`` when present but not a safe-echo
                              token).
      * ``created_at_utc`` -- caller-injected ISO-8601 UTC timestamp.
    """

    index: int
    decision: str
    token_mint: str
    created_at_utc: str


# ---------------------------------------------------------------------------
# Immutable model: rolled-up bridge report
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Stage30_11_23BridgeReport:
    """Immutable rolled-up Stage 30.11.23 bridge report.

    A passive summary of one bounded bridge pass. It proves, by counting, that ONLY a
    summary that passed every Layer-0 routing-hygiene check (a usable safe-shape mint,
    a present migration anchor, a COMPLETE measurement, a SAFE redaction, well-formed
    warnings, a buildable evidence record, a non-duplicate mint) became BOTH a
    discovered candidate AND a bound evidence record. Carries only safe scalars + the
    embedded redaction-safe events + a caller-injected timestamp.

      * ``bridge_events``    -- the ordered per-summary bridge events (one per scanned
                               summary).
      * ``summaries_seen``   -- summaries pulled + scanned (<= ``max_summaries``).
      * ``bridged``          -- summaries that yielded a candidate + evidence record.
      * ``skipped``          -- summaries failed closed (``summaries_seen`` minus
                               ``bridged``).
      * ``redaction_status`` -- one of ``STAGE30_11_23_REDACTION_STATUSES``
                               (``REDACTED`` iff every bridge-event string field is
                               safe).
      * ``created_at_utc``   -- caller-injected ISO-8601 UTC timestamp.
    """

    bridge_events: Tuple[Stage30_11_23BridgeEvent, ...]
    summaries_seen: int
    bridged: int
    skipped: int
    redaction_status: str
    created_at_utc: str


# ---------------------------------------------------------------------------
# Immutable model: the real-fed inputs bundle
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Stage30_11_23RealFedInputs:
    """Immutable bundle of the four inputs the committed Stage 30.11.22 wrapper takes.

    Built by the sibling adapter from ONE summary list; the operator unpacks it into
    ``run_stage30_11_22_real_fed_dry_run``'s injected slots. The candidate stream and
    the evidence source are derived from the SAME summaries, so a discovered candidate
    can never reference a mint with no evidence (or vice versa). Carries ONLY the four
    injectable inputs + the embedded bridge report; no secret, no magnitude, no body,
    no url, no transport destination.

      * ``events``           -- the discovered-candidate harvest events (the committed
                               Stage 30.11.6 / 30.11.22 ``events`` slot).
      * ``assembler``        -- the trivial committed Stage 30.11.23 assembler (the
                               ``assembler`` slot).
      * ``record_flattener`` -- the committed Stage 30.11.23 placeholder flattener (the
                               ``record_flattener`` slot).
      * ``evidence_source``  -- the mint-keyed committed Stage 30.11.9 evidence source
                               (the ``evidence_source`` slot).
      * ``report``           -- the embedded ``Stage30_11_23BridgeReport``.
    """

    events: Tuple[Stage30_11_23DiscoveredCandidate, ...]
    assembler: Any
    record_flattener: Any
    evidence_source: Any
    report: Stage30_11_23BridgeReport


# ---------------------------------------------------------------------------
# Field-name helpers (pure; read dataclass field names)
# ---------------------------------------------------------------------------


def discovered_candidate_field_names() -> Tuple[str, ...]:
    """Return the discovered-candidate field names as a tuple."""
    return tuple(f.name for f in fields(Stage30_11_23DiscoveredCandidate))


def assembled_candidate_field_names() -> Tuple[str, ...]:
    """Return the assembled-candidate field names as a tuple."""
    return tuple(f.name for f in fields(Stage30_11_23AssembledCandidate))


def bridge_event_field_names() -> Tuple[str, ...]:
    """Return the bridge-event field names as a tuple."""
    return tuple(f.name for f in fields(Stage30_11_23BridgeEvent))


def bridge_report_field_names() -> Tuple[str, ...]:
    """Return the bridge-report field names as a tuple."""
    return tuple(f.name for f in fields(Stage30_11_23BridgeReport))


def real_fed_inputs_field_names() -> Tuple[str, ...]:
    """Return the real-fed-inputs field names as a tuple."""
    return tuple(f.name for f in fields(Stage30_11_23RealFedInputs))


__all__ = (
    # Minor version + schema identity.
    "STAGE30_11_23_MINOR_VERSION",
    "STAGE30_11_23_REPORT_SCHEMA_VERSION",
    "STAGE30_11_23_SOURCE_STAGE",
    # COMPLETE / SAFE Layer-0 routing-hygiene tokens.
    "STAGE30_11_23_EXPECTED_MEASUREMENT_STATUS",
    "STAGE30_11_23_EXPECTED_REDACTION_STATUS",
    # Bridge decisions.
    "BRIDGE_DECISION_BRIDGED",
    "BRIDGE_DECISION_SKIPPED_NOT_A_SUMMARY",
    "BRIDGE_DECISION_SKIPPED_MISSING_TOKEN_MINT",
    "BRIDGE_DECISION_SKIPPED_INVALID_TOKEN_MINT",
    "BRIDGE_DECISION_SKIPPED_MISSING_MIGRATION_TIME",
    "BRIDGE_DECISION_SKIPPED_NOT_COMPLETE_MEASUREMENT",
    "BRIDGE_DECISION_SKIPPED_UNSAFE_REDACTION",
    "BRIDGE_DECISION_SKIPPED_MALFORMED_WARNINGS",
    "BRIDGE_DECISION_SKIPPED_EVIDENCE_UNBUILDABLE",
    "BRIDGE_DECISION_SKIPPED_DUPLICATE_MINT",
    "STAGE30_11_23_BRIDGE_DECISIONS",
    "STAGE30_11_23_BRIDGE_PASS_DECISION",
    "is_bridge_decision",
    # Redaction.
    "STAGE30_11_23_REDACTION_STATUS_REDACTED",
    "STAGE30_11_23_REDACTION_STATUS_VIOLATION",
    "STAGE30_11_23_REDACTED_UNSAFE_ID",
    "STAGE30_11_23_REDACTION_STATUSES",
    # Caps + placeholders.
    "STAGE30_11_23_MAX_SUMMARIES_HARD_CAP",
    "STAGE30_11_23_DEFAULT_MAX_SUMMARIES",
    "STAGE30_11_23_PLACEHOLDER_STATUS",
    "STAGE30_11_23_PLACEHOLDER_DECIMAL",
    # Safe-shape predicates.
    "is_nonblank_str",
    "is_safe_echo_id",
    # Models.
    "Stage30_11_23DiscoveredCandidate",
    "Stage30_11_23AssembledCandidate",
    "Stage30_11_23BridgeEvent",
    "Stage30_11_23BridgeReport",
    "Stage30_11_23RealFedInputs",
    # Field-name helpers.
    "discovered_candidate_field_names",
    "assembled_candidate_field_names",
    "bridge_event_field_names",
    "bridge_report_field_names",
    "real_fed_inputs_field_names",
)

"""Stage 30.14.0 real-discovery-replay -> shadow-dispatch models.

Build #26, substage 30.14.0. The passive, pure, stdlib-only MODEL layer for the Build
#26 SYNTHETIC offline proof that an ALREADY-DISCOVERED migration evidence record
(replayed from memory -- NEVER a live capture) flows through the committed Stage 30.13.0
auto-seeder -> the committed Stage 30.11.23 -> 30.11.22 recheck / fake-send chain to a
RECORDED would-send (a FAKE dispatch), NEVER a real send.

Build #26 exists because Build #25 proved real read-only discovery but persisted only the
discovery DECISION ledger (the accepted mint + four counts), NOT the underlying migration
evidence. So Build 26.0 is a COMMITTED, OFFLINE, SYNTHETIC-fixture proof of the REPLAY ->
recheck -> fake-dispatch plumbing. Pointing the same committed replay seam at a real,
evidence-bearing artifact (Build 26.1) is a SEPARATE step, BLOCKED until an
evidence-preserving capture exists; this slice FABRICATES nothing and replays only what a
caller injects.

This module is the MODEL layer ONLY: the minor / schema / purpose identity, the locked
Build 26.0 caps (``max_seed`` / ``max_rechecks`` / ``max_fake_dispatches`` -- all 1), the
closed-set redaction vocabulary + safe placeholder, the pure safe-shape predicates, the
immutable dispatch TRACE (the discovered -> seeded -> dispatched mint linkage + the
no-real-send attestation echo), and the immutable shadow-dispatch RESULT carrier. It
builds NO result, runs NO seeder, drives NO discovery, runs NO recheck, calls NO
transport, sends NO message, reads NO env, opens NO network, opens NO database, writes NO
file, and parses no clock.

Discipline:

  * Stdlib only (``dataclasses`` / ``typing``).
  * Imports NO PHX2 module (a pure leaf; mirrors the Stage 30.13.0 / 30.11.22 model
    modules). The composed committed result objects are carried duck-typed as ``Any`` --
    no committed result type is imported here.
  * No ``os.environ`` / ``os.getenv`` access; no env read.
  * No network, no socket; no database / SQLite, no compression.
  * No live provider, transport-destination, url, host, or request-metadata reference; no
    wallet / signing / trading surface; no public / subscriber routing.
  * No PHX1 import. No Stage 21-29 production import.
  * No ``time`` / ``datetime`` import; timestamps are caller-injected.
  * No module-level Call node (no implicit I/O at import time; the
    ``@dataclass(frozen=True)`` decorators are decorator-list Calls, not body-statement
    Calls).
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from typing import Any, Tuple


# ---------------------------------------------------------------------------
# Minor version + schema identity + purpose
# ---------------------------------------------------------------------------


STAGE30_14_0_MINOR_VERSION: str = "30.14.0"


# The Stage 30.14.0 shadow-dispatch result schema version. Names the dispatch-trace /
# shadow-dispatch-result shapes; distinct from every earlier Stage 30 schema version.
# Mirrored BY VALUE by the Stage 30.14 manifest; this module imports no manifest.
STAGE30_14_0_SCHEMA_VERSION: str = (
    "stage30_14_0_v0_real_discovery_replay_shadow_dispatch"
)


STAGE30_14_0_PURPOSE: str = (
    "synthetic real-discovery replay to shadow fake dispatch"
)


# ---------------------------------------------------------------------------
# Locked Build 26.0 caps (all 1: a single synthetic discovered mint)
# ---------------------------------------------------------------------------
#
# Build 26.0 is a SINGLE synthetic-mint proof: it seeds AT MOST one mint, rechecks AT
# MOST one summary, and records AT MOST one fake dispatch. The seed cap is passed to the
# committed Stage 30.13.0 auto-seeder (whose own hard cap is 10); the recheck cap is
# passed to the committed Stage 30.11.23 bridge as ``max_summaries``; with a single seeded
# summary the committed compose / dispatch is bounded to one would-send by construction.


STAGE30_14_MAX_SEED: int = 1
STAGE30_14_MAX_RECHECKS: int = 1
STAGE30_14_MAX_FAKE_DISPATCHES: int = 1


def is_locked_cap(value: object, cap: int) -> bool:
    """Return ``True`` iff ``value`` is exactly the locked cap ``cap``.

    Pure / TOTAL; never raises. A non-int, a ``bool`` (``True`` / ``False`` are not
    budgets), or any value other than ``cap`` fails closed to ``False`` -- so a Build 26.0
    run can never be parameterized past its single-mint bound.
    """
    if isinstance(value, bool):
        return False
    if not isinstance(value, int):
        return False
    return value == cap


# ---------------------------------------------------------------------------
# Redaction status tokens + safe placeholder
# ---------------------------------------------------------------------------
#
# The orchestrator self-scans the dispatch trace's string fields: ``REDACTED`` when every
# field is safe (the normal path -- the trace carries only safe-echo mints + safe-echo
# kind tokens + counts + bools), else ``REDACTION_VIOLATION``. A mint / kind token that is
# not a safe-echo token is replaced by ``REDACTED_UNSAFE_ID`` rather than echoed raw.
# Mirrors the committed Stage 30.13.0 / 30.11.22 redaction discipline BY VALUE.


STAGE30_14_REDACTION_STATUS_REDACTED: str = "REDACTED"
STAGE30_14_REDACTION_STATUS_VIOLATION: str = "REDACTION_VIOLATION"
STAGE30_14_REDACTED_UNSAFE_ID: str = "REDACTED_UNSAFE_ID"


STAGE30_14_REDACTION_STATUSES: Tuple[str, ...] = (
    STAGE30_14_REDACTION_STATUS_REDACTED,
    STAGE30_14_REDACTION_STATUS_VIOLATION,
)


# ---------------------------------------------------------------------------
# Pure safe-shape predicates
# ---------------------------------------------------------------------------


def is_nonblank_str(value: object) -> bool:
    """Return ``True`` iff ``value`` is a non-empty, non-blank string. Pure / total.

    Mirrors the committed Stage 30.13.0 / 30.11.22 non-blank check BY VALUE.
    """
    return isinstance(value, str) and value.strip() != ""


def is_safe_echo_id(value: object) -> bool:
    """Return ``True`` iff ``value`` is a safe-to-echo opaque token.

    A safe-echo token is a non-empty string of length 1..128 made ONLY of ASCII
    letters / digits / ``_`` / ``-``. A base58 token mint and an in-memory ledger / fake
    transport-client class-name token both pass; any newline / control char / whitespace /
    path / url / quote / scheme character (or an over-long value) fails. It gates the mints
    + kind tokens the orchestrator echoes into its redaction-safe trace -- an unsafe value
    is replaced by ``STAGE30_14_REDACTED_UNSAFE_ID`` rather than echoed raw. Mirrors the
    committed Stage 30.13.0 / 30.11.22 ``is_safe_echo_id`` BY VALUE. Pure / total; never
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
# Immutable model: the discovered -> seeded -> dispatched trace
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Stage30_14DispatchTrace:
    """Immutable redaction-safe Build 26.0 dispatch trace.

    Proves, by carrying the safe-echo mint at each hop + the recorded would-send tally +
    the pinned no-real-send attestation echo, that the SYNTHETIC discovered mint flowed
    end-to-end to a FAKE dispatch decision and NEVER a real send. Carries ONLY safe
    scalars + safe-echo tokens: NO migration anchor, NO measurement / magnitude, NO body,
    url, exception text, or secret.

      * ``discovered_mint``         -- the discovered + seeded mint: the committed Stage
                                       30.13.0 auto-seeder carries the discovered record's
                                       ``base_mint`` onto the seeded summary's
                                       ``token_mint`` VERBATIM, so this safe-echo value IS
                                       the discovered mint (``""`` when nothing seeded).
      * ``dispatched_mint``         -- the mint the recording FAKE dispatch client saw
                                       (``""`` when nothing dispatched).
      * ``mint_traces_through``     -- ``True`` iff a non-empty ``discovered_mint`` equals
                                       ``dispatched_mint`` (the end-to-end trace held).
      * ``seeds_accepted``          -- the committed auto-seeder's ``accepted`` count.
      * ``rechecks_bridged``        -- the committed Stage 30.11.23 bridge's ``bridged``
                                       count (the rechecked candidates).
      * ``dispatched``              -- the committed Stage 30.11.22 ``dispatched`` count
                                       (recorded would-sends).
      * ``would_send_recorded``     -- the FAKE client's recorded would-send tally
                                       (== ``dispatched``); NEVER a real send.
      * ``real_send_performed``     -- echoed from the committed attestation; pinned
                                       ``False`` by the composed chain.
      * ``real_send_guard_invoked`` -- echoed from the committed attestation; pinned
                                       ``False`` (the chain imports NO Stage 30.11.16
                                       real-send guard).
      * ``transport_client_kind``   -- the safe-echo class-name token of the recording
                                       FAKE dispatch client.
      * ``ledger_kind``             -- the safe-echo class-name token of the in-memory
                                       dedupe ledger.
      * ``redaction_status``        -- one of ``STAGE30_14_REDACTION_STATUSES``
                                       (``REDACTED`` iff every trace string field is safe).
    """

    discovered_mint: str
    dispatched_mint: str
    mint_traces_through: bool
    seeds_accepted: int
    rechecks_bridged: int
    dispatched: int
    would_send_recorded: int
    real_send_performed: bool
    real_send_guard_invoked: bool
    transport_client_kind: str
    ledger_kind: str
    redaction_status: str


# ---------------------------------------------------------------------------
# Immutable model: the shadow-dispatch result
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Stage30_14ShadowDispatchResult:
    """Immutable Stage 30.14.0 shadow-dispatch result.

    The orchestrator emits exactly one of these per bounded pass. It carries the committed
    auto-seed result (the four-count seed ledger + the seeded watchlist), the committed
    Stage 30.11.23 fake real-fed dry-run result (the bridge inputs + the dry-run report +
    the recording FAKE client + the in-memory ledger), and the Build 26.0 dispatch trace.
    Carries no secret, no magnitude, no body, no url, no transport destination.

      * ``seed_result`` -- the committed Stage 30.13.0 ``Stage30_13AutoSeedResult``
                           (duck-typed ``Any`` so this leaf imports no Stage 30.13 type).
      * ``dry_run``     -- the committed Stage 30.11.23
                           ``Stage30_11_23FakeRealFedDryRunProofResult`` (duck-typed
                           ``Any``).
      * ``trace``       -- the Build 26.0 ``Stage30_14DispatchTrace``.
    """

    seed_result: Any
    dry_run: Any
    trace: Stage30_14DispatchTrace


# ---------------------------------------------------------------------------
# Field-name helpers (pure; read dataclass field names)
# ---------------------------------------------------------------------------


def dispatch_trace_field_names() -> Tuple[str, ...]:
    """Return the dispatch-trace field names as a tuple."""
    return tuple(f.name for f in fields(Stage30_14DispatchTrace))


def shadow_dispatch_result_field_names() -> Tuple[str, ...]:
    """Return the shadow-dispatch-result field names as a tuple."""
    return tuple(f.name for f in fields(Stage30_14ShadowDispatchResult))


__all__ = (
    # Minor version + schema identity + purpose.
    "STAGE30_14_0_MINOR_VERSION",
    "STAGE30_14_0_SCHEMA_VERSION",
    "STAGE30_14_0_PURPOSE",
    # Locked caps.
    "STAGE30_14_MAX_SEED",
    "STAGE30_14_MAX_RECHECKS",
    "STAGE30_14_MAX_FAKE_DISPATCHES",
    "is_locked_cap",
    # Redaction.
    "STAGE30_14_REDACTION_STATUS_REDACTED",
    "STAGE30_14_REDACTION_STATUS_VIOLATION",
    "STAGE30_14_REDACTED_UNSAFE_ID",
    "STAGE30_14_REDACTION_STATUSES",
    # Safe-shape predicates.
    "is_nonblank_str",
    "is_safe_echo_id",
    # Models.
    "Stage30_14DispatchTrace",
    "Stage30_14ShadowDispatchResult",
    # Field-name helpers.
    "dispatch_trace_field_names",
    "shadow_dispatch_result_field_names",
)

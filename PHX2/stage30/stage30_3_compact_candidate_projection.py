"""Stage 30.3 compact candidate projection.

Pure projector that maps a Stage 30.3
``Stage30_3RecordedCandidateContext`` entry plus the caller-
supplied basis / created_at / session_id to:

  1. a Stage 30.1 ``TierDecisionRecord`` (via the Stage 30.1
     projector), and
  2. a Stage 30.2 ``CompactPingInputRecord`` built from the
     tier decision plus the entry's age / price_status / mint /
     identifier fields.

The Stage 30.2 display-text slots (``current_mc_text`` /
``ath_mc_text`` / ``migration_mc_text`` / ``lp_text`` /
``net_flow_text``) plus the symbol slot are left at ``None`` so
the Stage 30.2 renderer emits the ``Unknown`` literal for each.
A future Stage 30.4 MC / LP adapter will populate these slots
through the same projection contract.

The projector NEVER fetches MC, NEVER opens a network
connection, NEVER reads the process environment, NEVER calls
``datetime.now``, NEVER mutates its inputs, NEVER recomputes
tier bands (it delegates to the Stage 30.1 projector), and
NEVER invents missing display fields.

Discipline:

  * Stdlib only (``typing``).
  * Stage 30 sibling modules imported read-only.
  * No Stage 27 / Stage 28 / Stage 29 import (the tier decision
    projector is the Stage 30.1 sibling module that itself
    imports the Stage 27.4 record shapes; Stage 30.3A never
    imports Stage 27 / 28 / 29 directly).
  * No ``os.environ`` / ``os.getenv`` / ``os.environb`` access.
  * No network, no HTTP, no gRPC, no WebSocket, no socket.
  * No URL host literal, no API-key literal, no bearer-token
    literal, no authorization-header literal.
  * No PHX1 import. No legacy phoenix-1 import path.
  * No top-level Call (no implicit I/O at import time).
"""

from __future__ import annotations

from typing import Optional

from PHX2.stage30.compact_ping_models import CompactPingInputRecord
from PHX2.stage30.stage30_3_compact_runtime_models import (
    Stage30_3RecordedCandidateContext,
)
from PHX2.stage30.tier_decision_models import TierDecisionRecord
from PHX2.stage30.tier_decision_projector import decide_tier


def project_recorded_entry_to_tier_decision_record(
    *,
    entry: Stage30_3RecordedCandidateContext,
    basis: str,
    created_at_utc: str,
    session_id: Optional[str],
) -> TierDecisionRecord:
    """Project ``entry`` onto a Stage 30.1 ``TierDecisionRecord``
    via the Stage 30.1 projector.

    Pure / deterministic. Identical inputs always produce a
    byte-identical record (``NamedTuple`` equality).

    Raises ``Stage30_1TierDecisionError`` on caller-shape failures
    surfaced by the Stage 30.1 projector (invalid basis token,
    unsafe-shape ``created_at_utc``, non-record typed
    ``ath_record`` / ``migration_record``). Degraded inputs
    (missing record, missing drawdown, malformed drawdown, degraded
    ATH / migration status) DO NOT raise; they produce a
    deterministic ``TierDecisionRecord`` with the appropriate tier
    token + reason token pair per the Stage 30.1 decision
    precedence.
    """
    return decide_tier(
        ath_record=entry.ath_record,
        migration_record=entry.migration_record,
        basis=basis,
        created_at_utc=created_at_utc,
        ping_id=entry.candidate_id,
        candidate_id=entry.candidate_id,
        session_id=session_id,
        mint=entry.mint,
    )


def build_compact_ping_input_record(
    *,
    tier_decision: TierDecisionRecord,
    entry: Stage30_3RecordedCandidateContext,
    session_id: Optional[str],
    created_at_utc: str,
) -> CompactPingInputRecord:
    """Build a Stage 30.2 ``CompactPingInputRecord`` from a Stage
    30.1 ``TierDecisionRecord`` plus a Stage 30.3 recorded entry.

    The display-text slots are populated as ``None`` so the Stage
    30.2 renderer emits the ``Unknown`` literal for each (Stage
    30.3A ships zero MC / LP / Net adapter; Stage 30.4 will
    populate these slots through the same projection contract).

    Pure / deterministic. Identical inputs always produce a
    byte-identical record (``NamedTuple`` equality).
    """
    return CompactPingInputRecord(
        tier_decision=tier_decision,
        mint=entry.mint,
        symbol=None,
        current_mc_text=None,
        ath_mc_text=None,
        migration_mc_text=None,
        lp_text=None,
        net_flow_text=None,
        age_since_migration_seconds=(
            entry.age_since_migration_seconds
        ),
        price_status=entry.price_status,
        session_id=session_id,
        ping_id=entry.candidate_id,
        candidate_id=entry.candidate_id,
        created_at_utc=created_at_utc,
    )


__all__ = (
    "project_recorded_entry_to_tier_decision_record",
    "build_compact_ping_input_record",
)

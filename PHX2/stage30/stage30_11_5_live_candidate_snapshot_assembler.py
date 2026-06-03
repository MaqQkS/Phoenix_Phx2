"""Stage 30.11.5 live-candidate snapshot assembler.

The pure, offline ASSEMBLER that is the missing live INPUT source the prior
controlled live ceremony lacked: it converts an existing flat safe-scalar
candidate projection into a committed Stage 30.11.1
``Stage30_11LiveCandidateSnapshot`` -- the snapshot the committed Stage 30.11.2
runtime seam (and behind it the Stage 30.11.1 bridge + Stage 30.9.3 dip gate)
consumes:

    an existing candidate projection (a flat MAPPING / dict OR an
    attribute-bearing object whose keys / attributes are the safe-scalar
    projection field names)
      -> validate every REQUIRED field is present (fail closed -> MISSING)
      -> validate / coerce every present field's shape (fail closed -> INVALID;
         drawdown / market-cap -> a finite ``Decimal``)
      -> build a committed Stage 30.11.1 ``Stage30_11LiveCandidateSnapshot``
      -> a Stage 30.11.5 ``Stage30_11_5LiveCandidateAssemblyResult``

This is the narrowest live-input unblocker: a COMMITTED, TESTED mapping from an
existing assembled-candidate projection into the committed Stage 30.11.1
snapshot, so the later operator-authorized ceremony composes committed + tested
code for the assembly step instead of improvising a scratch projector. The
deeply-nested committed live assembled-candidate RECORD (a Stage 27 / 28 / 29
type) is flattened into this safe projection AT THE CEREMONY BOUNDARY (an
out-of-repo, operator-authorized step) so THIS committed slice imports NO Stage
21-29 record type -- it reads a flat safe projection by field name only.

The assembler ONLY builds a snapshot; it NEVER runs the bridge, NEVER decides
dip eligibility (that is the committed Stage 30.9.3 gate's job, run LATER inside
the committed seam), NEVER fabricates a missing drawdown / migration / ATH /
market context (a missing required field fails closed), NEVER forces a present
context token to the bridge's ``PRESENT`` value (a present-but-not-``PRESENT``
context is carried verbatim and the committed bridge later suppresses it), NEVER
reserves a dispatch, NEVER calls a transport, and NEVER sends Discord. The
snapshot is the INPUT the committed bridge + gate gate -- assembling it is never
a bypass of them.

The assembler NEVER fetches market data, NEVER opens a network connection,
NEVER reads the process environment, NEVER calls ``datetime.now`` (the
``created_at_utc`` of both the result and the snapshot is caller-injected), and
edits NO Stage 28 / Stage 29 / Stage 30.3 / Stage 30.4 production file. It
composes exactly one committed surface -- the Stage 30.11.1
``Stage30_11LiveCandidateSnapshot`` model -- plus the Stage 30.11.5 models
sibling; nothing more.

Discipline:

  * Stdlib only (``decimal`` / ``typing``).
  * Imports only the Stage 30.11.5 models sibling + the committed Stage 30.11.1
    bridge-models sibling (for the ``Stage30_11LiveCandidateSnapshot`` output
    type). No other PHX2 module; no Stage 21-29 / Stage 30.3 / Stage 30.4
    orchestrator / Stage 28 suppression / live runner / provider / transport
    import.
  * No ``os.environ`` / ``os.getenv`` access; no env read.
  * No network, no HTTP, no gRPC, no WebSocket, no socket.
  * No database / SQLite, no zstd / compression, no default storage root.
  * No live provider, transport-destination, or request-metadata reference.
  * No PHX1 import. No ``time`` / ``datetime`` import; timestamps are
    caller-injected.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Optional, Tuple

from PHX2.stage30.stage30_11_1_live_candidate_bridge_models import (
    Stage30_11LiveCandidateSnapshot,
)
from PHX2.stage30.stage30_11_5_live_wiring_models import (
    ASSEMBLY_DECISION_ASSEMBLED,
    ASSEMBLY_DECISION_REJECTED_INVALID_SHAPE,
    ASSEMBLY_DECISION_REJECTED_MISSING_FIELD,
    ASSEMBLY_REASON_INVALID_FIELD_SHAPE,
    ASSEMBLY_REASON_MISSING_REQUIRED_FIELD,
    ASSEMBLY_REASON_READY_FOR_BRIDGE,
    Stage30_11_5LiveCandidateAssemblyResult,
    is_nonblank_str,
)


# The ordered required string fields (each must be a non-blank string) and the
# ordered required decimal fields (each must coerce to a finite ``Decimal``).
# The check order pins which field a reject names FIRST.
_REQUIRED_STR_FIELDS: Tuple[str, ...] = (
    "candidate_id",
    "token_mint",
    "pair_type",
    "tier_hint",
    "migration_status",
    "ath_status",
    "market_context_status",
    "created_at_utc",
)
_REQUIRED_DECIMAL_FIELDS: Tuple[str, ...] = (
    "drawdown_from_ath",
    "current_market_cap_usd",
)


# ---------------------------------------------------------------------------
# Pure field readers / coercers
# ---------------------------------------------------------------------------


def _read_field(candidate: object, key: str) -> object:
    """Read field ``key`` from ``candidate``.

    Pure / total; never raises. ``candidate`` may be a flat MAPPING (read via
    ``.get``) or any attribute-bearing object (read via ``getattr``). A missing
    key / attribute (or a non-mapping / non-object) yields ``None``.
    """
    if isinstance(candidate, dict):
        return candidate.get(key)
    return getattr(candidate, key, None)


def _coerce_decimal(value: object) -> Optional[Decimal]:
    """Coerce ``value`` to a finite ``Decimal``, or return ``None`` if it cannot.

    Pure / total; never raises -- a ``bool``, a ``float`` (incl. ``nan`` /
    ``inf``), a non-numeric string, a non-finite ``Decimal`` (``NaN`` / ``sNaN`` /
    ``Infinity``), or any other malformed value fails closed to ``None`` without a
    ``decimal.InvalidOperation`` / ``TypeError`` / ``ValueError`` escaping. Only a
    finite ``Decimal`` is ever returned (so a fabricated non-finite magnitude can
    never reach the snapshot). A ``bool`` is rejected up front (``True`` /
    ``False`` are not magnitudes); a plain ``int`` and a safe decimal string are
    accepted.
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, Decimal):
        return value if value.is_finite() else None
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, str):
        text = value.strip()
        if text == "":
            return None
        try:
            result = Decimal(text)
        except (InvalidOperation, ValueError):
            return None
        return result if result.is_finite() else None
    return None


def _echo_id(value: object) -> str:
    """Return ``value`` if it is a non-blank string, else ``""`` (for echoing the
    candidate identity onto the result even on a reject). Pure / total.
    """
    return value if is_nonblank_str(value) else ""


# ---------------------------------------------------------------------------
# Pure result builders
# ---------------------------------------------------------------------------


def _rejected(
    candidate: object,
    *,
    decision: str,
    reason: str,
    rejected_field: str,
    created_at_utc: str,
) -> Stage30_11_5LiveCandidateAssemblyResult:
    """Build a fail-closed (no-snapshot) assembly result echoing whatever
    candidate identity is readable. Pure; no I/O.
    """
    return Stage30_11_5LiveCandidateAssemblyResult(
        candidate_id=_echo_id(_read_field(candidate, "candidate_id")),
        token_mint=_echo_id(_read_field(candidate, "token_mint")),
        assembly_decision=decision,
        assembly_reason=reason,
        rejected_field=rejected_field,
        snapshot=None,
        created_at_utc=created_at_utc,
    )


# ---------------------------------------------------------------------------
# Public assembler
# ---------------------------------------------------------------------------


def assemble_stage30_11_5_live_candidate_snapshot(
    candidate: object,
    *,
    created_at_utc: str,
) -> Stage30_11_5LiveCandidateAssemblyResult:
    """Assemble ONE existing candidate projection into a committed Stage 30.11.1
    live candidate snapshot.

    Pure / deterministic / total / no I/O, no provider call, no Discord send, no
    env read, no wall-clock read (``created_at_utc`` stamps the result; the
    projection's own ``created_at_utc`` flows to the snapshot). Never raises for a
    malformed candidate -- a non-mapping / non-object, a missing required field,
    or a malformed present field all fail closed to a reject result.

    Validation precedence (top-down, first match wins):

      1. any REQUIRED string field (``candidate_id`` / ``token_mint`` /
         ``pair_type`` / ``tier_hint`` / ``migration_status`` / ``ath_status`` /
         ``market_context_status`` / ``created_at_utc``) is absent (``None``) ->
         ``REJECTED_MISSING_REQUIRED_FIELD`` / ``MISSING_REQUIRED_CANDIDATE_FIELD``
         naming that field; present-but-blank / non-string ->
         ``REJECTED_INVALID_FIELD_SHAPE`` / ``INVALID_CANDIDATE_FIELD_SHAPE``.
      2. any REQUIRED decimal field (``drawdown_from_ath`` /
         ``current_market_cap_usd``) is absent -> MISSING; present-but-not-finite-
         coercible -> INVALID.
      3. an OPTIONAL field is present but malformed
         (``post_migration_ath_verified`` not a ``bool``; ``source_ref`` not a
         string) -> INVALID.
      4. otherwise -> ``ASSEMBLED_LIVE_CANDIDATE_SNAPSHOT`` / ``READY_FOR_BRIDGE``
         with the built committed Stage 30.11.1 ``Stage30_11LiveCandidateSnapshot``.

    The mapping fabricates nothing: a missing required context fails closed (it is
    NEVER defaulted to the bridge's ``PRESENT`` token), and a present-but-degraded
    context status is carried VERBATIM (the committed Stage 30.11.1 bridge -- run
    LATER inside the committed seam -- then suppresses it). The assembler does NOT
    run the bridge / dip gate / transport; the snapshot is their INPUT.
    """
    # ---- 1./2. Required string + decimal fields: present + well-shaped ----
    #
    # Read each in pinned order; the FIRST absent field is a MISSING reject, the
    # first present-but-malformed field is an INVALID reject.
    for field in _REQUIRED_STR_FIELDS:
        value = _read_field(candidate, field)
        if value is None:
            return _rejected(
                candidate,
                decision=ASSEMBLY_DECISION_REJECTED_MISSING_FIELD,
                reason=ASSEMBLY_REASON_MISSING_REQUIRED_FIELD,
                rejected_field=field,
                created_at_utc=created_at_utc,
            )
        if not is_nonblank_str(value):
            return _rejected(
                candidate,
                decision=ASSEMBLY_DECISION_REJECTED_INVALID_SHAPE,
                reason=ASSEMBLY_REASON_INVALID_FIELD_SHAPE,
                rejected_field=field,
                created_at_utc=created_at_utc,
            )

    coerced_decimals = {}
    for field in _REQUIRED_DECIMAL_FIELDS:
        value = _read_field(candidate, field)
        if value is None:
            return _rejected(
                candidate,
                decision=ASSEMBLY_DECISION_REJECTED_MISSING_FIELD,
                reason=ASSEMBLY_REASON_MISSING_REQUIRED_FIELD,
                rejected_field=field,
                created_at_utc=created_at_utc,
            )
        coerced = _coerce_decimal(value)
        if coerced is None:
            return _rejected(
                candidate,
                decision=ASSEMBLY_DECISION_REJECTED_INVALID_SHAPE,
                reason=ASSEMBLY_REASON_INVALID_FIELD_SHAPE,
                rejected_field=field,
                created_at_utc=created_at_utc,
            )
        coerced_decimals[field] = coerced

    # ---- 3. Optional fields: ``None`` / absent ok; present must be well-shaped ----
    post_migration_ath_verified = _read_field(
        candidate, "post_migration_ath_verified"
    )
    if post_migration_ath_verified is not None and not isinstance(
        post_migration_ath_verified, bool
    ):
        return _rejected(
            candidate,
            decision=ASSEMBLY_DECISION_REJECTED_INVALID_SHAPE,
            reason=ASSEMBLY_REASON_INVALID_FIELD_SHAPE,
            rejected_field="post_migration_ath_verified",
            created_at_utc=created_at_utc,
        )

    source_ref = _read_field(candidate, "source_ref")
    if source_ref is not None and not isinstance(source_ref, str):
        return _rejected(
            candidate,
            decision=ASSEMBLY_DECISION_REJECTED_INVALID_SHAPE,
            reason=ASSEMBLY_REASON_INVALID_FIELD_SHAPE,
            rejected_field="source_ref",
            created_at_utc=created_at_utc,
        )

    # ---- 4. Build the committed Stage 30.11.1 snapshot ----
    #
    # One-to-one mapping of the validated projection; no provider call, no
    # fabrication. The snapshot carries the projection's OWN ``created_at_utc``
    # (the gate evaluates the candidate as assembled); the keyword stamps the
    # assembly RESULT (when the assembler ran). Context status tokens are carried
    # verbatim -- the committed bridge decides PRESENT-ness later.
    snapshot = Stage30_11LiveCandidateSnapshot(
        candidate_id=_read_field(candidate, "candidate_id"),
        token_mint=_read_field(candidate, "token_mint"),
        pair_type=_read_field(candidate, "pair_type"),
        tier_hint=_read_field(candidate, "tier_hint"),
        drawdown_from_ath=coerced_decimals["drawdown_from_ath"],
        migration_status=_read_field(candidate, "migration_status"),
        ath_status=_read_field(candidate, "ath_status"),
        market_context_status=_read_field(candidate, "market_context_status"),
        current_market_cap_usd=coerced_decimals["current_market_cap_usd"],
        post_migration_ath_verified=post_migration_ath_verified,
        source_ref=source_ref,
        created_at_utc=_read_field(candidate, "created_at_utc"),
    )
    return Stage30_11_5LiveCandidateAssemblyResult(
        candidate_id=snapshot.candidate_id,
        token_mint=snapshot.token_mint,
        assembly_decision=ASSEMBLY_DECISION_ASSEMBLED,
        assembly_reason=ASSEMBLY_REASON_READY_FOR_BRIDGE,
        rejected_field="",
        snapshot=snapshot,
        created_at_utc=created_at_utc,
    )


__all__ = ("assemble_stage30_11_5_live_candidate_snapshot",)

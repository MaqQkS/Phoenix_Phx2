"""Stage 30.11.6 harvested-candidate -> Stage 30.11.5 projection adapter.

The pure, offline PROJECTION adapter that converts a HARVESTED assembled
candidate's flat safe-scalar fields into a Stage 30.11.5-shaped
``Stage30_11_6CandidateProjection`` -- the flat projection the committed Stage
30.11.5 bounded runner / assembler consume:

    a harvested candidate's flat fields (a flat MAPPING / dict OR an
    attribute-bearing object whose keys / attributes are the safe-scalar Stage
    30.11.5 projection field names)
      -> validate every REQUIRED field is present (fail closed -> MISSING)
      -> validate / coerce every present field's shape (fail closed -> INVALID;
         drawdown / market-cap -> a finite ``Decimal``)
      -> build a ``Stage30_11_6CandidateProjection``
      -> a ``Stage30_11_6CandidateProjectionResult``

This is the Stage 30 side of the harvest seam. The deeply-nested committed live
assembled-candidate RECORD (a Stage 27 / 28 / 29 type) is flattened into these
flat safe-scalar fields BY AN INJECTED record flattener AT THE CEREMONY BOUNDARY
(an out-of-repo, operator-authorized step the Stage 30.11.6 harvest adapter
drives) so THIS committed slice imports NO Stage 21-29 record type -- it reads a
flat safe projection by field name only, exactly as the committed Stage 30.11.5
assembler does. This adapter is the fail-closed validation gate the flattened
fields pass through BEFORE they can become a ``candidate_source`` projection: a
record whose flattened fields are missing / malformed is rejected here and NEVER
reaches the Stage 30.11.5 runner / transport.

The adapter ONLY builds a flat projection; it NEVER runs the assembler / bridge /
dip gate / runner / transport, NEVER decides dip eligibility (that is the
committed Stage 30.9.3 gate's job, run LATER), NEVER fabricates a missing
drawdown / migration / ATH / market context (a missing required field fails
closed), NEVER forces a present context token to the bridge's ``PRESENT`` value
(a present-but-degraded context status is carried VERBATIM so the committed
bridge later suppresses it), NEVER reserves a dispatch, NEVER calls a transport,
and NEVER sends Discord. Candidate identity is preserved.

The adapter NEVER fetches market data, NEVER opens a network connection, NEVER
reads the process environment, NEVER calls ``datetime.now`` (``created_at_utc``
is caller-injected), and edits NO Stage 27 / Stage 28 / Stage 29 / Stage 30.3 /
Stage 30.4 production file. It composes ONLY the Stage 30.11.6 models sibling;
nothing more.

Discipline:

  * Stdlib only (``decimal`` / ``typing``).
  * Imports ONLY the Stage 30.11.6 candidate-source-models sibling. No other PHX2
    module; no Stage 21-29 (incl. the nested Stage 27 / 28 / 29 live candidate
    record) / Stage 30.3 / Stage 30.4 orchestrator / Stage 28 suppression / live
    runner / provider / transport import.
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

from PHX2.stage30.stage30_11_6_candidate_source_models import (
    PROJECTION_DECISION_PROJECTED,
    PROJECTION_DECISION_REJECTED_INVALID_SHAPE,
    PROJECTION_DECISION_REJECTED_MISSING_FIELD,
    PROJECTION_REASON_INVALID_FIELD_SHAPE,
    PROJECTION_REASON_MISSING_REQUIRED_FIELD,
    PROJECTION_REASON_READY_FOR_LIVE_RUNNER,
    Stage30_11_6CandidateProjection,
    Stage30_11_6CandidateProjectionResult,
    is_nonblank_str,
)


# The ordered required string fields (each must be a non-blank string) and the
# ordered required decimal fields (each must coerce to a finite ``Decimal``). The
# check order pins which field a reject names FIRST. Mirrors the committed Stage
# 30.11.5 assembler precedence BY VALUE (so a record this adapter projects is one
# the committed Stage 30.11.5 assembler also accepts, and one this adapter rejects
# never becomes a candidate the runner could dispatch).
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


def _read_field(fields_source: object, key: str) -> object:
    """Read field ``key`` from ``fields_source``.

    Pure / total; never raises. ``fields_source`` may be a flat MAPPING (read via
    ``.get``) or any attribute-bearing object (read via ``getattr``). A missing
    key / attribute (or a non-mapping / non-object) yields ``None``. The adapter
    reads only the flat safe-scalar projection field names -- never the deep
    nested structure of a committed live candidate record.
    """
    if isinstance(fields_source, dict):
        return fields_source.get(key)
    return getattr(fields_source, key, None)


def _coerce_decimal(value: object) -> Optional[Decimal]:
    """Coerce ``value`` to a finite ``Decimal``, or return ``None`` if it cannot.

    Pure / total; never raises -- a ``bool``, a ``float`` (incl. ``nan`` /
    ``inf``), a non-numeric string, a non-finite ``Decimal`` (``NaN`` / ``sNaN`` /
    ``Infinity``), or any other malformed value fails closed to ``None`` without a
    ``decimal.InvalidOperation`` / ``TypeError`` / ``ValueError`` escaping. Only a
    finite ``Decimal`` is ever returned (so a fabricated non-finite magnitude can
    never reach the projection). A ``bool`` is rejected up front (``True`` /
    ``False`` are not magnitudes); a plain ``int`` and a safe decimal string are
    accepted. Mirrors the committed Stage 30.11.5 assembler coercion BY VALUE.
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
    fields_source: object,
    *,
    decision: str,
    reason: str,
    rejected_field: str,
    created_at_utc: str,
) -> Stage30_11_6CandidateProjectionResult:
    """Build a fail-closed (no-projection) result echoing whatever candidate
    identity is readable. Pure; no I/O.
    """
    return Stage30_11_6CandidateProjectionResult(
        candidate_id=_echo_id(_read_field(fields_source, "candidate_id")),
        token_mint=_echo_id(_read_field(fields_source, "token_mint")),
        projection_decision=decision,
        projection_reason=reason,
        rejected_field=rejected_field,
        projection=None,
        created_at_utc=created_at_utc,
    )


# ---------------------------------------------------------------------------
# Public projection adapter
# ---------------------------------------------------------------------------


def project_harvested_candidate(
    fields_source: object,
    *,
    created_at_utc: str,
) -> Stage30_11_6CandidateProjectionResult:
    """Project ONE harvested candidate's flat fields into a Stage 30.11.5-shaped
    flat projection.

    Pure / deterministic / total / no I/O, no provider call, no Discord send, no
    env read, no wall-clock read (``created_at_utc`` stamps the result; the
    harvested ``created_at_utc`` flows onto the projection). Never raises for a
    malformed input -- a non-mapping / non-object, a missing required field, or a
    malformed present field all fail closed to a reject result (no projection).

    Validation precedence (top-down, first match wins; mirrors the committed Stage
    30.11.5 assembler BY VALUE):

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
      4. otherwise -> ``PROJECTED_LIVE_CANDIDATE`` / ``READY_FOR_LIVE_RUNNER`` with
         the built ``Stage30_11_6CandidateProjection``.

    The projection fabricates nothing: a missing required context fails closed (it
    is NEVER defaulted to the bridge's ``PRESENT`` token), an unknown pair / a
    missing-or-stale price / a missing migration context is carried VERBATIM (the
    committed Stage 30.11.1 bridge + Stage 30.9.3 dip gate -- run LATER -- decide
    eligibility, so a degraded candidate NEVER becomes dip-eligible here), and a
    malformed ``Decimal`` fails closed. Candidate identity is preserved.
    """
    # ---- 1./2. Required string + decimal fields: present + well-shaped ----
    for field in _REQUIRED_STR_FIELDS:
        value = _read_field(fields_source, field)
        if value is None:
            return _rejected(
                fields_source,
                decision=PROJECTION_DECISION_REJECTED_MISSING_FIELD,
                reason=PROJECTION_REASON_MISSING_REQUIRED_FIELD,
                rejected_field=field,
                created_at_utc=created_at_utc,
            )
        if not is_nonblank_str(value):
            return _rejected(
                fields_source,
                decision=PROJECTION_DECISION_REJECTED_INVALID_SHAPE,
                reason=PROJECTION_REASON_INVALID_FIELD_SHAPE,
                rejected_field=field,
                created_at_utc=created_at_utc,
            )

    coerced_decimals = {}
    for field in _REQUIRED_DECIMAL_FIELDS:
        value = _read_field(fields_source, field)
        if value is None:
            return _rejected(
                fields_source,
                decision=PROJECTION_DECISION_REJECTED_MISSING_FIELD,
                reason=PROJECTION_REASON_MISSING_REQUIRED_FIELD,
                rejected_field=field,
                created_at_utc=created_at_utc,
            )
        coerced = _coerce_decimal(value)
        if coerced is None:
            return _rejected(
                fields_source,
                decision=PROJECTION_DECISION_REJECTED_INVALID_SHAPE,
                reason=PROJECTION_REASON_INVALID_FIELD_SHAPE,
                rejected_field=field,
                created_at_utc=created_at_utc,
            )
        coerced_decimals[field] = coerced

    # ---- 3. Optional fields: ``None`` / absent ok; present must be well-shaped --
    post_migration_ath_verified = _read_field(
        fields_source, "post_migration_ath_verified"
    )
    if post_migration_ath_verified is not None and not isinstance(
        post_migration_ath_verified, bool
    ):
        return _rejected(
            fields_source,
            decision=PROJECTION_DECISION_REJECTED_INVALID_SHAPE,
            reason=PROJECTION_REASON_INVALID_FIELD_SHAPE,
            rejected_field="post_migration_ath_verified",
            created_at_utc=created_at_utc,
        )

    source_ref = _read_field(fields_source, "source_ref")
    if source_ref is not None and not isinstance(source_ref, str):
        return _rejected(
            fields_source,
            decision=PROJECTION_DECISION_REJECTED_INVALID_SHAPE,
            reason=PROJECTION_REASON_INVALID_FIELD_SHAPE,
            rejected_field="source_ref",
            created_at_utc=created_at_utc,
        )

    # ---- 4. Build the Stage 30.11.5-shaped flat projection ----
    #
    # One-to-one mapping of the validated flat fields; no provider call, no
    # fabrication. Context status tokens are carried verbatim -- the committed
    # bridge decides PRESENT-ness later. The harvested ``created_at_utc`` flows
    # onto the projection (the runner evaluates the candidate as harvested); the
    # keyword stamps the projection RESULT (when the projection ran).
    projection = Stage30_11_6CandidateProjection(
        candidate_id=_read_field(fields_source, "candidate_id"),
        token_mint=_read_field(fields_source, "token_mint"),
        pair_type=_read_field(fields_source, "pair_type"),
        tier_hint=_read_field(fields_source, "tier_hint"),
        drawdown_from_ath=coerced_decimals["drawdown_from_ath"],
        migration_status=_read_field(fields_source, "migration_status"),
        ath_status=_read_field(fields_source, "ath_status"),
        market_context_status=_read_field(
            fields_source, "market_context_status"
        ),
        current_market_cap_usd=coerced_decimals["current_market_cap_usd"],
        post_migration_ath_verified=post_migration_ath_verified,
        source_ref=source_ref,
        created_at_utc=_read_field(fields_source, "created_at_utc"),
    )
    return Stage30_11_6CandidateProjectionResult(
        candidate_id=projection.candidate_id,
        token_mint=projection.token_mint,
        projection_decision=PROJECTION_DECISION_PROJECTED,
        projection_reason=PROJECTION_REASON_READY_FOR_LIVE_RUNNER,
        rejected_field="",
        projection=projection,
        created_at_utc=created_at_utc,
    )


__all__ = ("project_harvested_candidate",)

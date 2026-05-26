"""Stage 29.5 private ping migration context projection.

The projection layer is the sole authority that constructs a
:class:`Stage29_5PrivatePingMigrationContext` from a join
verdict and a Stage 27.4 ATH context record. The projection is a
pure function; same inputs => same output; never raises on a
valid pair of arguments.

The projection layer is observational only. It NEVER gates
dispatch. It NEVER mutates either input. It NEVER fabricates a
migration timestamp / slot / source. Stage 29.5 dispatch
behavior follows the existing Stage 28.9 + Stage 28.4 + Stage
28.2 chain regardless of which warning codes the projection
emits.

Stage 29.5.1 ships this projection as an offline evidence /
projection layer. Runtime integration into the Stage 29.3 +
Stage 29.4 private ping path is deferred to Stage 29.5.2; the
Stage 29.3 mode-3 orchestrator continues to inject
:class:`Stage29_3NoMigrationEvidenceSource` and does not consume
this projection at runtime yet. The Stage 29.5 boundary test
pins that not-yet-integrated state.

Stage 29.5.1 second remediation tightens COMPLETE semantics to
an 8-predicate gate. COMPLETE requires every one of:

  1. join verdict = ``JOINED``
  2. ``migration_slot`` present (non-None)
  3. ``ath_context is not None``
  4. ``ath_context.ath_status == ATH_STATUS_PRESENT``
  5. ``ath_context.ath_value is not None``
  6. ``ath_context.token_mint == join_record.candidate_base_mint``
  7. ``ath_context.ath_since_migration_status ==
     ATH_SINCE_MIGRATION_STATUS_POST_MIGRATION_ONLY``
  8. ``ath_observed_at_utc`` parses as strict UTC datetime AND
     is strictly after the matched ``migration_timestamp_utc``
     (the matched timestamp is itself parsed strictly).

If any predicate fails:

  * The projection does NOT emit ``COMPLETE``.
  * The projection does NOT set ``post_migration_ath_verified``
    to ``True``.
  * The projection emits ``PARTIAL_MIGRATION_PRESENT`` +
    ``WARNING_POST_MIGRATION_ATH_UNVERIFIED`` (and
    ``WARNING_MIGRATION_SLOT_MISSING`` additionally when
    ``migration_slot`` is missing).

The ``filter_enforcement_status`` field is locked to
``NOT_ACTIVE_STAGE_29_PENDING`` on every output; the projection
rejects any caller attempt to override it.

Discipline:

  * No env reads.
  * No network. No file I/O.
  * No third-party runtime dependency. Imports only stdlib
    (``typing``) plus the Stage 29.5 models module.
  * No top-level Call.
  * No PHX1 import.
  * Imports the Stage 27.4 ``AthContextRecord`` NamedTuple
    read-only for type-shape (an ``Optional`` parameter so the
    projection works even when the price/ATH context record is
    not yet available).
"""

from __future__ import annotations

from typing import Callable, Optional

from PHX2.stage27.price_ath_context_models import (
    ATH_SINCE_MIGRATION_STATUS_MAY_INCLUDE_PRE_MIGRATION,
    ATH_SINCE_MIGRATION_STATUS_POST_MIGRATION_ONLY,
    ATH_STATUS_PRESENT,
    AthContextRecord,
)
from PHX2.stage29.stage29_5_migration_models import (
    FILTER_ENFORCEMENT_STATUS_NOT_ACTIVE_STAGE_29_PENDING,
    MEASUREMENT_STATUS_COMPLETE,
    MEASUREMENT_STATUS_CONFLICTING_MIGRATION,
    MEASUREMENT_STATUS_INVALID_MIGRATION,
    MEASUREMENT_STATUS_MISSING_MIGRATION,
    MEASUREMENT_STATUS_PARTIAL_MIGRATION_PRESENT,
    MIGRATION_JOIN_STATUS_JOINED,
    MIGRATION_JOIN_STATUS_MULTIPLE_MATCHES,
    MIGRATION_JOIN_STATUS_NO_MATCH,
    MIGRATION_JOIN_STATUS_PAIR_MISMATCH,
    MIGRATION_JOIN_STATUS_SOURCE_INVALID,
    MIGRATION_JOIN_STATUS_TIME_WINDOW_INVALID,
    MIGRATION_SOURCE_UNKNOWN_STAGE29_5,
    REDACTION_STATUS_SAFE,
    Stage29_5MigrationJoinRecord,
    Stage29_5PrivatePingMigrationContext,
    WARNING_MIGRATION_CONFLICT,
    WARNING_MIGRATION_MISSING,
    WARNING_MIGRATION_PAIR_MISMATCH,
    WARNING_MIGRATION_SLOT_MISSING,
    WARNING_MIGRATION_SOURCE_UNKNOWN,
    WARNING_MIGRATION_STALE,
    WARNING_MIGRATION_TIMESTAMP_INVALID,
    WARNING_POST_MIGRATION_ATH_UNVERIFIED,
    is_safe_iso8601_utc_string,
    parse_safe_utc_datetime,
)


# ---------------------------------------------------------------------------
# ATH-window helper
# ---------------------------------------------------------------------------


def _ath_window_starts_post_migration(
    ath_context: Optional[AthContextRecord],
    migration_timestamp_utc: Optional[str],
) -> Optional[bool]:
    """Return True iff the Stage 27.4 ATH observation timestamp is
    strictly after the matched migration timestamp.

    Stage 29.5.1 remediation: comparison is performed on parsed
    aware ``datetime`` objects via
    :func:`parse_safe_utc_datetime`, not on raw ISO-8601 strings.

    Returns ``None`` when either input is missing, when the
    Stage 27.4 record carries no observation timestamp, or when
    either timestamp fails strict UTC datetime parsing.
    """
    if ath_context is None:
        return None
    if migration_timestamp_utc is None:
        return None
    ath_observed = ath_context.ath_observed_at_utc
    if ath_observed is None:
        return None
    try:
        ath_dt = parse_safe_utc_datetime(ath_observed)
        migration_dt = parse_safe_utc_datetime(
            migration_timestamp_utc
        )
    except ValueError:
        return None
    return ath_dt > migration_dt


def _ath_context_proves_post_migration_only_complete(
    ath_context: Optional[AthContextRecord],
    join_record: Stage29_5MigrationJoinRecord,
    migration_timestamp_utc: Optional[str],
) -> bool:
    """Stage 29.5.1 second remediation: return True iff the
    Stage 27.4 ATH context positively proves the
    POST_MIGRATION_ONLY + ATH-record-fully-populated +
    same-token + strict-after-migration conjunction the
    projection's COMPLETE gate requires.

    Each predicate failure routes the projection to
    PARTIAL_MIGRATION_PRESENT.

    The Stage 27.4 ATH record's ``ath_since_migration_status``
    field can only legitimately equal POST_MIGRATION_ONLY when
    Stage 27.4 has positively proven the ATH window does not
    include pre-migration wick data. Stage 29.5 layers two
    additional checks on top of that Stage 27.4 verdict:

      * the ATH record must positively refer to the SAME mint
        the candidate carried into the join (a cross-token
        token_mint mismatch must not silently anchor a COMPLETE
        verdict);
      * the ATH-observed timestamp must parse as a strict UTC
        datetime AND be strictly after the matched migration
        timestamp (a parsed-datetime cross-check on top of the
        Stage 27.4 POST_MIGRATION_ONLY token).
    """
    if ath_context is None:
        return False
    if ath_context.ath_status != ATH_STATUS_PRESENT:
        return False
    if ath_context.ath_value is None:
        return False
    if ath_context.token_mint is None:
        return False
    if (
        ath_context.token_mint
        != join_record.candidate_base_mint
    ):
        return False
    if (
        ath_context.ath_since_migration_status
        != ATH_SINCE_MIGRATION_STATUS_POST_MIGRATION_ONLY
    ):
        return False
    if migration_timestamp_utc is None:
        return False
    ath_observed = ath_context.ath_observed_at_utc
    if ath_observed is None:
        return False
    try:
        ath_dt = parse_safe_utc_datetime(ath_observed)
        migration_dt = parse_safe_utc_datetime(
            migration_timestamp_utc
        )
    except ValueError:
        return False
    return ath_dt > migration_dt


# ---------------------------------------------------------------------------
# Projection
# ---------------------------------------------------------------------------


def _append_dedup(out: list, code: str) -> None:
    if code not in out:
        out.append(code)


def project_private_ping_migration_context(
    join_record: Stage29_5MigrationJoinRecord,
    ath_context: Optional[AthContextRecord],
    clock: Callable[[], str],
) -> Stage29_5PrivatePingMigrationContext:
    """Pure projection — see module docstring for semantics."""
    if not isinstance(
        join_record, Stage29_5MigrationJoinRecord
    ):
        raise ValueError(
            "join_record must be a "
            "Stage29_5MigrationJoinRecord instance"
        )
    if ath_context is not None and not isinstance(
        ath_context, AthContextRecord
    ):
        raise ValueError(
            "ath_context must be an AthContextRecord or None"
        )
    if not callable(clock):
        raise ValueError("clock must be callable")
    observed_at_utc = clock()
    if not is_safe_iso8601_utc_string(observed_at_utc):
        raise ValueError(
            "clock returned a non-UTC-shaped string"
        )
    status = join_record.migration_join_status
    matched = join_record.matched_evidence
    primary = matched[0] if matched else None
    migration_timestamp_utc = (
        primary.migration_timestamp_utc
        if primary is not None
        else None
    )
    migration_slot = (
        primary.migration_slot if primary is not None else None
    )
    migration_source = (
        primary.migration_source
        if primary is not None
        else MIGRATION_SOURCE_UNKNOWN_STAGE29_5
    )
    warnings: list = []
    measurement_status: str
    post_migration_ath_verified: Optional[bool]
    if status == MIGRATION_JOIN_STATUS_NO_MATCH:
        measurement_status = MEASUREMENT_STATUS_MISSING_MIGRATION
        _append_dedup(warnings, WARNING_MIGRATION_MISSING)
        _append_dedup(
            warnings, WARNING_POST_MIGRATION_ATH_UNVERIFIED
        )
        post_migration_ath_verified = None
        migration_timestamp_utc = None
        migration_slot = None
        migration_source = (
            MIGRATION_SOURCE_UNKNOWN_STAGE29_5
        )
    elif status == MIGRATION_JOIN_STATUS_MULTIPLE_MATCHES:
        measurement_status = (
            MEASUREMENT_STATUS_CONFLICTING_MIGRATION
        )
        _append_dedup(warnings, WARNING_MIGRATION_CONFLICT)
        _append_dedup(
            warnings, WARNING_POST_MIGRATION_ATH_UNVERIFIED
        )
        post_migration_ath_verified = None
    elif status == MIGRATION_JOIN_STATUS_SOURCE_INVALID:
        measurement_status = (
            MEASUREMENT_STATUS_INVALID_MIGRATION
        )
        _append_dedup(
            warnings, WARNING_MIGRATION_TIMESTAMP_INVALID
        )
        _append_dedup(
            warnings, WARNING_POST_MIGRATION_ATH_UNVERIFIED
        )
        post_migration_ath_verified = None
    elif status == MIGRATION_JOIN_STATUS_PAIR_MISMATCH:
        measurement_status = (
            MEASUREMENT_STATUS_INVALID_MIGRATION
        )
        _append_dedup(
            warnings, WARNING_MIGRATION_PAIR_MISMATCH
        )
        _append_dedup(
            warnings, WARNING_POST_MIGRATION_ATH_UNVERIFIED
        )
        post_migration_ath_verified = None
    elif (
        status == MIGRATION_JOIN_STATUS_TIME_WINDOW_INVALID
    ):
        measurement_status = (
            MEASUREMENT_STATUS_PARTIAL_MIGRATION_PRESENT
        )
        _append_dedup(warnings, WARNING_MIGRATION_STALE)
        _append_dedup(
            warnings, WARNING_POST_MIGRATION_ATH_UNVERIFIED
        )
        post_migration_ath_verified = None
    elif status == MIGRATION_JOIN_STATUS_JOINED:
        slot_present = migration_slot is not None
        # Stage 29.5.1 second remediation: COMPLETE requires the
        # full 8-predicate gate. Any one predicate failing
        # routes the verdict to PARTIAL_MIGRATION_PRESENT and
        # prevents ``post_migration_ath_verified=True``.
        complete_proven = (
            _ath_context_proves_post_migration_only_complete(
                ath_context,
                join_record,
                migration_timestamp_utc,
            )
        )
        if slot_present and complete_proven:
            measurement_status = (
                MEASUREMENT_STATUS_COMPLETE
            )
            post_migration_ath_verified = True
        elif slot_present:
            measurement_status = (
                MEASUREMENT_STATUS_PARTIAL_MIGRATION_PRESENT
            )
            _append_dedup(
                warnings,
                WARNING_POST_MIGRATION_ATH_UNVERIFIED,
            )
            # Inside the slot-present-but-not-complete branch,
            # distinguish positive-negative signals (verified
            # False) from insufficient-information cases
            # (verified None):
            #   * Stage 27.4 explicitly says the ATH window may
            #     include pre-migration wick data ->
            #     verified=False (positive negative signal).
            #   * Either timestamp side proves ATH predates the
            #     migration -> verified=False.
            #   * Otherwise (UNKNOWN status / no ATH context /
            #     unparseable timestamps / ath_status not
            #     PRESENT / ath_value missing / token mismatch)
            #     -> verified=None (cannot prove either way).
            ath_status_token = (
                ath_context.ath_since_migration_status
                if ath_context is not None
                else None
            )
            ath_after_migration = (
                _ath_window_starts_post_migration(
                    ath_context, migration_timestamp_utc
                )
            )
            if (
                ath_status_token
                == ATH_SINCE_MIGRATION_STATUS_MAY_INCLUDE_PRE_MIGRATION
            ):
                post_migration_ath_verified = False
            elif ath_after_migration is False:
                post_migration_ath_verified = False
            else:
                post_migration_ath_verified = None
        else:
            # Slot missing — NEVER set
            # post_migration_ath_verified=True regardless of ATH
            # context state. Always carries the SLOT_MISSING +
            # POST_MIGRATION_ATH_UNVERIFIED warning pair.
            measurement_status = (
                MEASUREMENT_STATUS_PARTIAL_MIGRATION_PRESENT
            )
            _append_dedup(
                warnings,
                WARNING_MIGRATION_SLOT_MISSING,
            )
            _append_dedup(
                warnings,
                WARNING_POST_MIGRATION_ATH_UNVERIFIED,
            )
            post_migration_ath_verified = None
    else:
        raise ValueError(
            "join_record carries an unrecognized "
            f"migration_join_status {status!r}"
        )
    if (
        migration_source
        == MIGRATION_SOURCE_UNKNOWN_STAGE29_5
    ):
        _append_dedup(
            warnings, WARNING_MIGRATION_SOURCE_UNKNOWN
        )
    return Stage29_5PrivatePingMigrationContext(
        measurement_status=measurement_status,
        warnings=tuple(warnings),
        migration_timestamp_utc=migration_timestamp_utc,
        migration_slot=migration_slot,
        migration_source=migration_source,
        post_migration_ath_verified=post_migration_ath_verified,
        join_status_echoed=status,
        redaction_status=REDACTION_STATUS_SAFE,
        filter_enforcement_status=(
            FILTER_ENFORCEMENT_STATUS_NOT_ACTIVE_STAGE_29_PENDING
        ),
        observed_at_utc=observed_at_utc,
    )


__all__ = (
    "project_private_ping_migration_context",
)

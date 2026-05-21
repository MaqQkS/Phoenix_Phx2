"""Stage 25.2 migration measurement reconciler.

Pure reconciler that consolidates a tuple of
``Stage25MigrationObservation`` records into a tuple of
``Stage25MigrationMeasurement`` records, one per distinct
``token_mint``.

Public entry points:

  * ``measure_migration_for_token`` -- build a single
                                       ``Stage25MigrationMeasurement``
                                       for a caller-supplied token from
                                       the supplied observations.
  * ``measure_migrations``          -- group observations by token and
                                       emit one
                                       ``Stage25MigrationMeasurement``
                                       per token in deterministic order.

Measurement rules (Stage 25.2 invariants -- see Stage 25 docstring):

  * No observations for the requested token -> ``MISSING`` /
    reconciliation ``NO_SOURCES`` / confidence ``NONE``.
  * Any observation with the ``AMBIGUOUS`` source status forces
    ``AMBIGUOUS`` / reconciliation ``AMBIGUOUS`` / confidence
    ``NONE``. (Stage 25.2 deliberately does not add a future-policy
    override for this case.)
  * Same source family supplying two or more conflicting observations
    (different signature / slot / block_time after exact-duplicate
    dedupe) forces ``AMBIGUOUS`` / reconciliation ``AMBIGUOUS`` /
    confidence ``NONE``.
  * One valid contributing source -> ``MEASURED`` / reconciliation
    ``SINGLE_SOURCE`` / confidence ``LOW``.
  * Multiple valid contributing sources agree within
    ``MIGRATION_TIMESTAMP_TOLERANCE_SECONDS`` -> ``MEASURED`` /
    reconciliation ``AGREED`` / confidence ``HIGH``. The selected
    timestamp / signature is deterministic: the minimum block_time
    across agreeing sources with tie-breaks on source_family, then
    signature, then slot.
  * Multiple valid contributing sources disagree by more than the
    tolerance -> ``AMBIGUOUS`` / reconciliation ``DISAGREED_MAJOR`` /
    confidence ``NONE`` (no consolidated timestamp emitted).
  * No valid contributors but at least one ``PARTIAL`` observation /
    ``PRESENT`` observation missing block_time / slot / signature ->
    ``PARTIAL`` / reconciliation ``NO_SOURCES`` / confidence
    ``NONE``.
  * No valid contributors and at least one ``MALFORMED`` or
    ``DECODE_FAILED`` observation -> ``REJECTED`` / reconciliation
    ``NO_SOURCES`` / confidence ``NONE``.
  * No valid contributors and all observations are ``UNSUPPORTED`` ->
    ``UNSUPPORTED`` / reconciliation ``NO_SOURCES`` / confidence
    ``NONE``.
  * No valid contributors and all observations are ``ABSENT`` ->
    ``MISSING`` / reconciliation ``NO_SOURCES`` / confidence ``NONE``.
  * Observations whose ``token_mint`` does not match the requested
    token are rejected from the reconciliation (Stage 25.2 records the
    rejection via a reason code on the resulting measurement when no
    matching observation remains).

Output invariants:

  * The returned record's ``measurement_family`` is always
    ``MEASUREMENT_FAMILY_MIGRATION``.
  * ``consolidated_block_time`` is the first-class reconciled
    migration timestamp (Unix seconds); ``consolidated_slot`` is the
    first-class selected slot. Both carry the ``-1`` sentinel when no
    consolidated value applies (``AMBIGUOUS``, ``MISSING``,
    ``UNSUPPORTED``, ``REJECTED``, ``PARTIAL``). No duplicate
    ``reconciled_block_time_unix`` / ``reconciled_slot`` field exists.
  * ``reconciliation_status``, ``reconciled_signature``, and
    ``selected_source_family`` are FIRST-CLASS fields on
    ``Stage25MigrationMeasurement``. They are validated by
    ``build_migration_measurement_record`` against
    ``RECONCILIATION_STATUSES`` / non-empty-string /
    ``SOURCE_FAMILIES``-or-empty respectively, and are bound into the
    canonical ``measurement_hash`` so two distinct reconciliation
    outcomes never collide on one hash.
  * The ``evidence`` mapping carries ONLY auxiliary observation-level
    diagnostics -- ``contributing_source_families``,
    ``observed_source_families``, ``observation_count``,
    ``duplicate_collapsed_count`` -- and deliberately does NOT
    duplicate the promoted reconciliation fields, so a downstream
    consumer cannot encounter divergent first-class vs. evidence
    values.
  * ``contributing_source_count`` counts distinct source families
    among the valid contributors.

This module imports only stdlib (``typing``, ``types``) plus the
Stage 25 constants / errors / models / migration observation
helpers. It does NOT import Stage 21 / Stage 22 / Stage 23 /
Stage 24 production modules, does NOT import any network / RPC /
messaging / DB / scheduler / secrets-management library, does
NOT read the process environment, does NOT define a CLI surface,
and contains no top-level I/O.
"""

from __future__ import annotations

from types import MappingProxyType
from typing import Mapping

from PHX2.stage25.constants import (
    CONFIDENCE_LEVEL_HIGH,
    CONFIDENCE_LEVEL_LOW,
    CONFIDENCE_LEVEL_NONE,
    DEFAULT_SCHEMA_VERSION,
    DEFAULT_THRESHOLD_VERSION,
    MEASUREMENT_STATUS_AMBIGUOUS,
    MEASUREMENT_STATUS_MEASURED,
    MEASUREMENT_STATUS_MISSING,
    MEASUREMENT_STATUS_PARTIAL,
    MEASUREMENT_STATUS_REJECTED,
    MEASUREMENT_STATUS_UNSUPPORTED,
    MIGRATION_TIMESTAMP_TOLERANCE_SECONDS,
    REASON_CODE_MIGRATION_AMBIGUOUS_SOURCE_STATUS,
    REASON_CODE_MIGRATION_BLOCK_TIME_MISSING,
    REASON_CODE_MIGRATION_DUPLICATE_OBSERVATION_COLLAPSED,
    REASON_CODE_MIGRATION_NO_CONTRIBUTING_SOURCES,
    REASON_CODE_MIGRATION_NO_OBSERVATIONS,
    REASON_CODE_MIGRATION_SAME_SOURCE_CONFLICT,
    REASON_CODE_MIGRATION_SIGNATURE_MISSING,
    REASON_CODE_MIGRATION_SINGLE_SOURCE,
    REASON_CODE_MIGRATION_SLOT_MISSING,
    REASON_CODE_MIGRATION_SOURCES_AGREED,
    REASON_CODE_MIGRATION_SOURCES_DISAGREED,
    REASON_CODE_MIGRATION_TOKEN_MISMATCH_REJECTED,
    REASON_CODE_MIGRATION_UNSUPPORTED_SOURCE_STATUS,
    RECONCILIATION_STATUS_AGREED,
    RECONCILIATION_STATUS_AMBIGUOUS,
    RECONCILIATION_STATUS_DISAGREED_MAJOR,
    RECONCILIATION_STATUS_NO_SOURCES,
    RECONCILIATION_STATUS_SINGLE_SOURCE,
    SOURCE_STATUS_ABSENT,
    SOURCE_STATUS_AMBIGUOUS,
    SOURCE_STATUS_DECODE_FAILED,
    SOURCE_STATUS_MALFORMED,
    SOURCE_STATUS_PARTIAL,
    SOURCE_STATUS_PRESENT,
    SOURCE_STATUS_UNSUPPORTED,
    STAGE25_MIGRATION_MEASURER_NAME,
    STAGE25_MIGRATION_MEASURER_VERSION,
)
from PHX2.stage25.errors import Stage25ContractError
from PHX2.stage25.migration_observation import (
    dedupe_migration_observations,
    group_migration_observations_by_token,
    observation_is_present_with_full_evidence,
)
from PHX2.stage25.models import (
    Stage25MigrationMeasurement,
    Stage25MigrationObservation,
    build_migration_measurement_record,
)


# ---------------------------------------------------------------------------
# Internal sentinels
# ---------------------------------------------------------------------------


_SLOT_ABSENT_SENTINEL: int = -1
_BLOCK_TIME_ABSENT_SENTINEL: int = -1


def _frozen_mapping(value: Mapping[str, object]) -> Mapping[str, object]:
    return MappingProxyType(dict(value))


def _append_unique(codes: list[str], code: str) -> None:
    if code not in codes:
        codes.append(code)


# ---------------------------------------------------------------------------
# Same-source conflict detection
# ---------------------------------------------------------------------------


def _same_source_conflict(
    observations: tuple[Stage25MigrationObservation, ...],
) -> bool:
    """Return True iff any source_family supplies two or more observations
    with different (signature, slot, block_time) tuples after exact-
    duplicate dedupe.
    """
    by_source: dict[str, set[tuple[str, int, int]]] = {}
    for observation in observations:
        keys = by_source.setdefault(observation.source_family, set())
        keys.add(
            (
                observation.migration_signature,
                observation.slot,
                observation.block_time,
            )
        )
        if len(keys) > 1:
            return True
    return False


# ---------------------------------------------------------------------------
# No-contributor classification
# ---------------------------------------------------------------------------


def _resolve_no_contributor_status(
    observations: tuple[Stage25MigrationObservation, ...],
) -> tuple[str, str]:
    """Return ``(measurement_status, primary_reason_code)`` for the
    no-contributor case.

    Precedence:

      1. Any ``MALFORMED`` or ``DECODE_FAILED`` -> ``REJECTED``.
      2. Any ``PARTIAL`` or ``PRESENT``-without-full-evidence ->
         ``PARTIAL``.
      3. Any ``UNSUPPORTED`` -> ``UNSUPPORTED``.
      4. Otherwise (all ``ABSENT`` or mixture of only ABSENT) ->
         ``MISSING``.
    """
    statuses = {observation.source_status for observation in observations}
    if SOURCE_STATUS_MALFORMED in statuses or (
        SOURCE_STATUS_DECODE_FAILED in statuses
    ):
        return (
            MEASUREMENT_STATUS_REJECTED,
            REASON_CODE_MIGRATION_NO_CONTRIBUTING_SOURCES,
        )
    has_partial_evidence = SOURCE_STATUS_PARTIAL in statuses
    if not has_partial_evidence:
        for observation in observations:
            if (
                observation.source_status == SOURCE_STATUS_PRESENT
                and not observation_is_present_with_full_evidence(
                    observation
                )
            ):
                has_partial_evidence = True
                break
    if has_partial_evidence:
        return (
            MEASUREMENT_STATUS_PARTIAL,
            REASON_CODE_MIGRATION_NO_CONTRIBUTING_SOURCES,
        )
    if SOURCE_STATUS_UNSUPPORTED in statuses and statuses.issubset(
        {SOURCE_STATUS_UNSUPPORTED, SOURCE_STATUS_ABSENT}
    ):
        return (
            MEASUREMENT_STATUS_UNSUPPORTED,
            REASON_CODE_MIGRATION_UNSUPPORTED_SOURCE_STATUS,
        )
    if SOURCE_STATUS_UNSUPPORTED in statuses:
        return (
            MEASUREMENT_STATUS_UNSUPPORTED,
            REASON_CODE_MIGRATION_UNSUPPORTED_SOURCE_STATUS,
        )
    return (
        MEASUREMENT_STATUS_MISSING,
        REASON_CODE_MIGRATION_NO_CONTRIBUTING_SOURCES,
    )


def _partial_evidence_reason_codes(
    observations: tuple[Stage25MigrationObservation, ...],
) -> tuple[str, ...]:
    """Return the partial-evidence reason codes implied by the
    observation tuple (block_time / slot / signature missing on any
    non-contributing or contributing observation).

    Codes are deduplicated and returned in a deterministic order.
    """
    codes: list[str] = []
    block_missing = False
    slot_missing = False
    signature_missing = False
    for observation in observations:
        if observation.source_status not in (
            SOURCE_STATUS_PRESENT,
            SOURCE_STATUS_PARTIAL,
        ):
            continue
        if observation.block_time < 0:
            block_missing = True
        if observation.slot < 0:
            slot_missing = True
        if observation.migration_signature == "":
            signature_missing = True
    if block_missing:
        codes.append(REASON_CODE_MIGRATION_BLOCK_TIME_MISSING)
    if slot_missing:
        codes.append(REASON_CODE_MIGRATION_SLOT_MISSING)
    if signature_missing:
        codes.append(REASON_CODE_MIGRATION_SIGNATURE_MISSING)
    return tuple(codes)


# ---------------------------------------------------------------------------
# Deterministic chosen-source selection
# ---------------------------------------------------------------------------


def _choose_consolidated_source(
    contributors: tuple[Stage25MigrationObservation, ...],
) -> Stage25MigrationObservation:
    """Pick the consolidated contributor deterministically.

    Selection key (ascending): block_time, source_family,
    migration_signature, slot.

    Caller guarantees ``contributors`` is non-empty.
    """
    return min(
        contributors,
        key=lambda observation: (
            observation.block_time,
            observation.source_family,
            observation.migration_signature,
            observation.slot,
        ),
    )


# ---------------------------------------------------------------------------
# Evidence / numeric_features assembly
# ---------------------------------------------------------------------------


def _evidence_mapping(
    *,
    contributing_source_families: tuple[str, ...],
    observed_source_families: tuple[str, ...],
    observation_count: int,
    duplicate_collapsed_count: int,
) -> Mapping[str, object]:
    """Build the auxiliary ``evidence`` mapping for a migration measurement.

    Stage 25.2 promotes ``reconciliation_status`` /
    ``reconciled_signature`` / ``selected_source_family`` to first-
    class ``Stage25MigrationMeasurement`` fields, so the evidence
    mapping no longer carries them. The evidence mapping is now
    reserved strictly for auxiliary observation-level diagnostics
    (observed source families, observation count, duplicate-collapse
    count) that have no first-class equivalent on the record.
    """
    return _frozen_mapping(
        {
            "contributing_source_families": list(
                contributing_source_families
            ),
            "observed_source_families": list(observed_source_families),
            "observation_count": observation_count,
            "duplicate_collapsed_count": duplicate_collapsed_count,
        }
    )


def _numeric_features_mapping(
    *,
    contributor_count: int,
    block_time_spread_seconds: int,
    tolerance_seconds: int,
) -> Mapping[str, object]:
    return _frozen_mapping(
        {
            "contributor_count": contributor_count,
            "block_time_spread_seconds": block_time_spread_seconds,
            "tolerance_seconds": tolerance_seconds,
        }
    )


def _observed_source_families(
    observations: tuple[Stage25MigrationObservation, ...],
) -> tuple[str, ...]:
    families = {observation.source_family for observation in observations}
    return tuple(sorted(families))


# ---------------------------------------------------------------------------
# Public reconciler entry points
# ---------------------------------------------------------------------------


def measure_migration_for_token(
    token: str,
    observations: tuple[Stage25MigrationObservation, ...],
    *,
    measurement_version: str = STAGE25_MIGRATION_MEASURER_VERSION,
    threshold_version: str = DEFAULT_THRESHOLD_VERSION,
    schema_version: str = DEFAULT_SCHEMA_VERSION,
    measurer_name: str = STAGE25_MIGRATION_MEASURER_NAME,
) -> Stage25MigrationMeasurement:
    """Build a single migration measurement for ``token``.

    Observations whose ``token_mint`` does not match ``token`` are
    rejected from the reconciliation. When at least one supplied
    observation carried a mismatched token, the resulting measurement
    carries the ``MIGRATION_TOKEN_MISMATCH_REJECTED`` reason code so
    downstream readers can detect the rejection.

    The returned record is fully validated via
    ``build_migration_measurement_record`` and carries a deterministic
    ``measurement_hash``.
    """
    if not isinstance(token, str) or token == "":
        raise Stage25ContractError(
            "measure_migration_for_token: token must be a non-empty string"
        )
    if not isinstance(observations, tuple):
        raise Stage25ContractError(
            "measure_migration_for_token: observations must be a tuple"
        )

    mismatch_observed = any(
        observation.token_mint != token for observation in observations
    )
    relevant = tuple(
        observation
        for observation in observations
        if observation.token_mint == token
    )

    deduped = dedupe_migration_observations(relevant)
    duplicate_collapsed = len(relevant) - len(deduped)

    observed_families = _observed_source_families(deduped)
    contributors = tuple(
        observation
        for observation in deduped
        if observation_is_present_with_full_evidence(observation)
    )
    contributor_families: tuple[str, ...] = tuple(
        sorted({observation.source_family for observation in contributors})
    )

    extra_codes: list[str] = []
    if duplicate_collapsed > 0:
        _append_unique(
            extra_codes,
            REASON_CODE_MIGRATION_DUPLICATE_OBSERVATION_COLLAPSED,
        )
    if mismatch_observed:
        _append_unique(
            extra_codes,
            REASON_CODE_MIGRATION_TOKEN_MISMATCH_REJECTED,
        )

    # A: No observations for token.
    if not deduped:
        reason_codes: list[str] = [REASON_CODE_MIGRATION_NO_OBSERVATIONS]
        for code in extra_codes:
            _append_unique(reason_codes, code)
        return _build_unmeasured_record(
            token=token,
            measurement_status=MEASUREMENT_STATUS_MISSING,
            reconciliation_status=RECONCILIATION_STATUS_NO_SOURCES,
            reason_codes=tuple(reason_codes),
            observed_source_families=observed_families,
            contributing_source_families=contributor_families,
            observation_count=0,
            duplicate_collapsed_count=duplicate_collapsed,
            measurement_version=measurement_version,
            threshold_version=threshold_version,
            schema_version=schema_version,
            measurer_name=measurer_name,
        )

    # F: Same-source conflict.
    if _same_source_conflict(deduped):
        reason_codes = [REASON_CODE_MIGRATION_SAME_SOURCE_CONFLICT]
        for code in extra_codes:
            _append_unique(reason_codes, code)
        for code in _partial_evidence_reason_codes(deduped):
            _append_unique(reason_codes, code)
        return _build_unmeasured_record(
            token=token,
            measurement_status=MEASUREMENT_STATUS_AMBIGUOUS,
            reconciliation_status=RECONCILIATION_STATUS_AMBIGUOUS,
            reason_codes=tuple(reason_codes),
            observed_source_families=observed_families,
            contributing_source_families=contributor_families,
            observation_count=len(deduped),
            duplicate_collapsed_count=duplicate_collapsed,
            measurement_version=measurement_version,
            threshold_version=threshold_version,
            schema_version=schema_version,
            measurer_name=measurer_name,
        )

    # Any AMBIGUOUS source status -> AMBIGUOUS measurement.
    if any(
        observation.source_status == SOURCE_STATUS_AMBIGUOUS
        for observation in deduped
    ):
        reason_codes = [REASON_CODE_MIGRATION_AMBIGUOUS_SOURCE_STATUS]
        for code in extra_codes:
            _append_unique(reason_codes, code)
        for code in _partial_evidence_reason_codes(deduped):
            _append_unique(reason_codes, code)
        return _build_unmeasured_record(
            token=token,
            measurement_status=MEASUREMENT_STATUS_AMBIGUOUS,
            reconciliation_status=RECONCILIATION_STATUS_AMBIGUOUS,
            reason_codes=tuple(reason_codes),
            observed_source_families=observed_families,
            contributing_source_families=contributor_families,
            observation_count=len(deduped),
            duplicate_collapsed_count=duplicate_collapsed,
            measurement_version=measurement_version,
            threshold_version=threshold_version,
            schema_version=schema_version,
            measurer_name=measurer_name,
        )

    # B: No contributing sources.
    if not contributors:
        no_contributor_status, primary_code = _resolve_no_contributor_status(
            deduped
        )
        reason_codes = [primary_code]
        for code in extra_codes:
            _append_unique(reason_codes, code)
        for code in _partial_evidence_reason_codes(deduped):
            _append_unique(reason_codes, code)
        return _build_unmeasured_record(
            token=token,
            measurement_status=no_contributor_status,
            reconciliation_status=RECONCILIATION_STATUS_NO_SOURCES,
            reason_codes=tuple(reason_codes),
            observed_source_families=observed_families,
            contributing_source_families=contributor_families,
            observation_count=len(deduped),
            duplicate_collapsed_count=duplicate_collapsed,
            measurement_version=measurement_version,
            threshold_version=threshold_version,
            schema_version=schema_version,
            measurer_name=measurer_name,
        )

    # C: Single contributing source.
    if len(contributor_families) == 1:
        # All contributing observations share one source_family. If
        # several contributing observations from that source family
        # share the same dedupe key they have already collapsed; if
        # they don't share the key the same-source-conflict path above
        # would have fired. So we can safely pick the canonical
        # contributor.
        chosen = _choose_consolidated_source(contributors)
        reason_codes = [REASON_CODE_MIGRATION_SINGLE_SOURCE]
        for code in extra_codes:
            _append_unique(reason_codes, code)
        for code in _partial_evidence_reason_codes(deduped):
            _append_unique(reason_codes, code)
        return _build_measured_record(
            token=token,
            measurement_status=MEASUREMENT_STATUS_MEASURED,
            confidence_level=CONFIDENCE_LEVEL_LOW,
            reconciliation_status=RECONCILIATION_STATUS_SINGLE_SOURCE,
            reason_codes=tuple(reason_codes),
            chosen=chosen,
            contributor_count=1,
            block_time_spread_seconds=0,
            observed_source_families=observed_families,
            contributing_source_families=contributor_families,
            observation_count=len(deduped),
            duplicate_collapsed_count=duplicate_collapsed,
            measurement_version=measurement_version,
            threshold_version=threshold_version,
            schema_version=schema_version,
            measurer_name=measurer_name,
        )

    # D/E: Multiple contributing sources.
    block_times = [observation.block_time for observation in contributors]
    spread = max(block_times) - min(block_times)
    if spread <= MIGRATION_TIMESTAMP_TOLERANCE_SECONDS:
        chosen = _choose_consolidated_source(contributors)
        reason_codes = [REASON_CODE_MIGRATION_SOURCES_AGREED]
        for code in extra_codes:
            _append_unique(reason_codes, code)
        for code in _partial_evidence_reason_codes(deduped):
            _append_unique(reason_codes, code)
        return _build_measured_record(
            token=token,
            measurement_status=MEASUREMENT_STATUS_MEASURED,
            confidence_level=CONFIDENCE_LEVEL_HIGH,
            reconciliation_status=RECONCILIATION_STATUS_AGREED,
            reason_codes=tuple(reason_codes),
            chosen=chosen,
            contributor_count=len(contributor_families),
            block_time_spread_seconds=spread,
            observed_source_families=observed_families,
            contributing_source_families=contributor_families,
            observation_count=len(deduped),
            duplicate_collapsed_count=duplicate_collapsed,
            measurement_version=measurement_version,
            threshold_version=threshold_version,
            schema_version=schema_version,
            measurer_name=measurer_name,
        )

    # Disagreement beyond tolerance.
    reason_codes = [REASON_CODE_MIGRATION_SOURCES_DISAGREED]
    for code in extra_codes:
        _append_unique(reason_codes, code)
    for code in _partial_evidence_reason_codes(deduped):
        _append_unique(reason_codes, code)
    return _build_unmeasured_record(
        token=token,
        measurement_status=MEASUREMENT_STATUS_AMBIGUOUS,
        reconciliation_status=RECONCILIATION_STATUS_DISAGREED_MAJOR,
        reason_codes=tuple(reason_codes),
        observed_source_families=observed_families,
        contributing_source_families=contributor_families,
        observation_count=len(deduped),
        duplicate_collapsed_count=duplicate_collapsed,
        contributor_count=len(contributor_families),
        block_time_spread_seconds=spread,
        measurement_version=measurement_version,
        threshold_version=threshold_version,
        schema_version=schema_version,
        measurer_name=measurer_name,
    )


def measure_migrations(
    observations: tuple[Stage25MigrationObservation, ...],
    *,
    measurement_version: str = STAGE25_MIGRATION_MEASURER_VERSION,
    threshold_version: str = DEFAULT_THRESHOLD_VERSION,
    schema_version: str = DEFAULT_SCHEMA_VERSION,
    measurer_name: str = STAGE25_MIGRATION_MEASURER_NAME,
) -> tuple[Stage25MigrationMeasurement, ...]:
    """Group observations by token and emit one measurement per token.

    Output ordering is deterministic: token mints sorted
    lexicographically. The caller-supplied tuple is not mutated.
    """
    if not isinstance(observations, tuple):
        raise Stage25ContractError(
            "measure_migrations: observations must be a tuple"
        )
    grouped = group_migration_observations_by_token(observations)
    measurements: list[Stage25MigrationMeasurement] = []
    for token in sorted(grouped.keys()):
        measurements.append(
            measure_migration_for_token(
                token,
                grouped[token],
                measurement_version=measurement_version,
                threshold_version=threshold_version,
                schema_version=schema_version,
                measurer_name=measurer_name,
            )
        )
    return tuple(measurements)


# ---------------------------------------------------------------------------
# Internal builders
# ---------------------------------------------------------------------------


def _build_measured_record(
    *,
    token: str,
    measurement_status: str,
    confidence_level: str,
    reconciliation_status: str,
    reason_codes: tuple[str, ...],
    chosen: Stage25MigrationObservation,
    contributor_count: int,
    block_time_spread_seconds: int,
    observed_source_families: tuple[str, ...],
    contributing_source_families: tuple[str, ...],
    observation_count: int,
    duplicate_collapsed_count: int,
    measurement_version: str,
    threshold_version: str,
    schema_version: str,
    measurer_name: str,
) -> Stage25MigrationMeasurement:
    evidence = _evidence_mapping(
        contributing_source_families=contributing_source_families,
        observed_source_families=observed_source_families,
        observation_count=observation_count,
        duplicate_collapsed_count=duplicate_collapsed_count,
    )
    numeric_features = _numeric_features_mapping(
        contributor_count=contributor_count,
        block_time_spread_seconds=block_time_spread_seconds,
        tolerance_seconds=MIGRATION_TIMESTAMP_TOLERANCE_SECONDS,
    )
    return build_migration_measurement_record(
        measurement_status=measurement_status,
        confidence_level=confidence_level,
        reconciliation_status=reconciliation_status,
        token_mint=token,
        schema_version=schema_version,
        threshold_version=threshold_version,
        measurer_name=measurer_name,
        measurer_version=measurement_version,
        consolidated_slot=chosen.slot,
        consolidated_block_time=chosen.block_time,
        reconciled_signature=chosen.migration_signature,
        selected_source_family=chosen.source_family,
        contributing_source_count=contributor_count,
        reason_codes=reason_codes,
        numeric_features=numeric_features,
        evidence=evidence,
        input_missing_fields=(),
    )


def _build_unmeasured_record(
    *,
    token: str,
    measurement_status: str,
    reconciliation_status: str,
    reason_codes: tuple[str, ...],
    observed_source_families: tuple[str, ...],
    contributing_source_families: tuple[str, ...],
    observation_count: int,
    duplicate_collapsed_count: int,
    measurement_version: str,
    threshold_version: str,
    schema_version: str,
    measurer_name: str,
    contributor_count: int = 0,
    block_time_spread_seconds: int = 0,
) -> Stage25MigrationMeasurement:
    evidence = _evidence_mapping(
        contributing_source_families=contributing_source_families,
        observed_source_families=observed_source_families,
        observation_count=observation_count,
        duplicate_collapsed_count=duplicate_collapsed_count,
    )
    numeric_features = _numeric_features_mapping(
        contributor_count=contributor_count,
        block_time_spread_seconds=block_time_spread_seconds,
        tolerance_seconds=MIGRATION_TIMESTAMP_TOLERANCE_SECONDS,
    )
    return build_migration_measurement_record(
        measurement_status=measurement_status,
        confidence_level=CONFIDENCE_LEVEL_NONE,
        reconciliation_status=reconciliation_status,
        token_mint=token,
        schema_version=schema_version,
        threshold_version=threshold_version,
        measurer_name=measurer_name,
        measurer_version=measurement_version,
        consolidated_slot=_SLOT_ABSENT_SENTINEL,
        consolidated_block_time=_BLOCK_TIME_ABSENT_SENTINEL,
        reconciled_signature="",
        selected_source_family="",
        contributing_source_count=contributor_count,
        reason_codes=reason_codes,
        numeric_features=numeric_features,
        evidence=evidence,
        input_missing_fields=(),
    )


# ---------------------------------------------------------------------------
# Downstream blocking predicate
# ---------------------------------------------------------------------------


_BLOCKING_MIGRATION_STATUSES: frozenset[str] = frozenset(
    {
        MEASUREMENT_STATUS_AMBIGUOUS,
        MEASUREMENT_STATUS_MISSING,
        MEASUREMENT_STATUS_UNSUPPORTED,
        MEASUREMENT_STATUS_REJECTED,
    }
)


def migration_measurement_blocks_measured_ath(
    measurement: Stage25MigrationMeasurement,
) -> bool:
    """Return True iff ``measurement`` carries a status that MUST block
    any later ATH measurement from being ``MEASURED``.

    The downstream-blocking statuses are ``AMBIGUOUS``, ``MISSING``,
    ``UNSUPPORTED``, and ``REJECTED``. Stage 25.2 publishes the
    predicate so the Stage 25.4 ATH reconciler can consume one
    authoritative definition; the Stage 25.2 surface itself does NOT
    implement ATH logic.
    """
    return measurement.measurement_status in _BLOCKING_MIGRATION_STATUSES


__all__ = [
    "measure_migration_for_token",
    "measure_migrations",
    "migration_measurement_blocks_measured_ath",
]

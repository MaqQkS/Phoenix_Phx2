"""Stage 25.3 price-window projector.

Pure projector that classifies ``Stage25PriceObservation`` records
against a consolidated ``Stage25MigrationMeasurement`` and emits a
tuple of ``Stage25PriceWindowObservation`` records assigning each
input observation to a deterministic price window.

Public entry points:

  * ``classify_price_window_kind`` -- return the
                                      ``PRICE_WINDOW_KINDS`` token
                                      that applies to a single
                                      observation given a single
                                      migration measurement.
  * ``build_price_window_observation`` -- build one
                                          ``Stage25PriceWindowObservation``
                                          for a single (observation,
                                          migration) pair.
  * ``build_price_window_observations_for_token`` -- build the window
                                                     observations for
                                                     one token,
                                                     applying a single
                                                     migration
                                                     measurement.
  * ``build_price_window_observations`` -- top-level batch entry
                                           point that groups
                                           observations by token,
                                           pairs each token with its
                                           consolidated migration
                                           measurement, and emits a
                                           deterministic tuple of
                                           window observations.

Window classification rules (Stage 25.3 invariants -- see Stage 25
docstring):

  * Missing ``observed_at_utc`` (empty string) -> ``UNKNOWN_WINDOW``
    with the ``PRICE_WINDOW_OBSERVED_AT_MISSING`` reason code.
  * Migration not ``MEASURED`` -> ``UNKNOWN_WINDOW`` with either
    ``PRICE_WINDOW_UNKNOWN_MIGRATION`` (``AMBIGUOUS`` / ``REJECTED``
    / ``UNSUPPORTED`` / ``NOT_APPLICABLE``) or
    ``PRICE_WINDOW_MIGRATION_NOT_MEASURED`` (``MISSING`` /
    ``PARTIAL`` / no migration record for token).
  * Migration ``MEASURED`` but ``consolidated_block_time < 0`` ->
    ``UNKNOWN_WINDOW`` with the ``PRICE_WINDOW_MIGRATION_NOT_MEASURED``
    reason code.
  * Observation ``block_time < 0`` while migration is ``MEASURED`` ->
    ``UNKNOWN_WINDOW`` (cannot compute delta).
  * Migration ``MEASURED`` and observation ``block_time`` known:
      - ``block_time < consolidated_block_time``
        -> ``PRE_MIGRATION_EXCLUDED``.
      - ``consolidated_block_time <= block_time <=
        consolidated_block_time + POST_MIGRATION_PRIMARY_WINDOW_SECONDS``
        -> ``POST_MIGRATION_PRIMARY``.
      - ``block_time > consolidated_block_time +
        POST_MIGRATION_PRIMARY_WINDOW_SECONDS``
        -> ``POST_MIGRATION_EXTENDED``.
  * Source-status preservation: ``PARTIAL`` observations carry the
    ``PRICE_WINDOW_PARTIAL_SOURCE_STATUS`` reason code; ``AMBIGUOUS``
    observations carry the ``PRICE_WINDOW_AMBIGUOUS_SOURCE_STATUS``
    reason code.
  * Token mismatch: a price observation whose ``token_mint`` does not
    match the migration measurement's ``token_mint`` is rejected via
    ``Stage25ContractError``.

This module imports only stdlib (``typing``, ``types``) plus the
Stage 25 constants / errors / models. It does NOT import Stage 21
/ Stage 22 / Stage 23 / Stage 24 production modules, does NOT
import any network / RPC / messaging / DB / scheduler /
secrets-management library, does NOT read the process
environment, does NOT define a CLI surface, and contains no
top-level I/O.
"""

from __future__ import annotations

from types import MappingProxyType
from typing import Mapping

from PHX2.stage25.constants import (
    CONFIDENCE_LEVEL_NONE,
    DEFAULT_SCHEMA_VERSION,
    DEFAULT_THRESHOLD_VERSION,
    MEASUREMENT_STATUS_AMBIGUOUS,
    MEASUREMENT_STATUS_MEASURED,
    MEASUREMENT_STATUS_MISSING,
    MEASUREMENT_STATUS_NOT_APPLICABLE,
    MEASUREMENT_STATUS_PARTIAL,
    MEASUREMENT_STATUS_REJECTED,
    MEASUREMENT_STATUS_UNSUPPORTED,
    POST_MIGRATION_PRIMARY_WINDOW_SECONDS,
    PRICE_WINDOW_KIND_POST_MIGRATION_EXTENDED,
    PRICE_WINDOW_KIND_POST_MIGRATION_PRIMARY,
    PRICE_WINDOW_KIND_PRE_MIGRATION_EXCLUDED,
    PRICE_WINDOW_KIND_UNKNOWN_WINDOW,
    REASON_CODE_MIGRATION_NO_OBSERVATIONS,
    REASON_CODE_PRICE_WINDOW_AMBIGUOUS_SOURCE_STATUS,
    REASON_CODE_PRICE_WINDOW_MIGRATION_NOT_MEASURED,
    REASON_CODE_PRICE_WINDOW_OBSERVED_AT_MISSING,
    REASON_CODE_PRICE_WINDOW_PARTIAL_SOURCE_STATUS,
    REASON_CODE_PRICE_WINDOW_POST_MIGRATION_EXTENDED,
    REASON_CODE_PRICE_WINDOW_POST_MIGRATION_PRIMARY,
    REASON_CODE_PRICE_WINDOW_PRE_MIGRATION_EXCLUDED,
    REASON_CODE_PRICE_WINDOW_UNKNOWN_MIGRATION,
    RECONCILIATION_STATUS_NO_SOURCES,
    SOURCE_STATUS_AMBIGUOUS,
    SOURCE_STATUS_PARTIAL,
    STAGE25_MIGRATION_MEASURER_NAME,
    STAGE25_MIGRATION_MEASURER_VERSION,
    STAGE25_PRICE_WINDOW_VERSION,
)
from PHX2.stage25.errors import Stage25ContractError
from PHX2.stage25.models import (
    Stage25MigrationMeasurement,
    Stage25PriceObservation,
    Stage25PriceWindowObservation,
    build_migration_measurement_record,
    build_price_window_observation_record,
)
from PHX2.stage25.price_observation import (
    group_price_observations_by_token,
    normalize_price_observations,
)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


_BLOCK_TIME_ABSENT_SENTINEL: int = -1


_MIGRATION_NOT_MEASURED_PARTIAL_STATUSES: frozenset[str] = frozenset(
    {
        MEASUREMENT_STATUS_MISSING,
        MEASUREMENT_STATUS_PARTIAL,
    }
)


_MIGRATION_UNKNOWN_STATUSES: frozenset[str] = frozenset(
    {
        MEASUREMENT_STATUS_AMBIGUOUS,
        MEASUREMENT_STATUS_REJECTED,
        MEASUREMENT_STATUS_UNSUPPORTED,
        MEASUREMENT_STATUS_NOT_APPLICABLE,
    }
)


def _frozen_mapping(value: Mapping[str, object]) -> Mapping[str, object]:
    return MappingProxyType(dict(value))


def _append_unique(codes: list[str], code: str) -> None:
    if code not in codes:
        codes.append(code)


def _migration_not_measured_reason_code(
    migration: Stage25MigrationMeasurement,
) -> str:
    """Return the reason code that explains why the migration is not
    ``MEASURED``.

    Distinguishes the ``MISSING`` / ``PARTIAL`` cases (no boundary
    yet) from the ``AMBIGUOUS`` / ``REJECTED`` / ``UNSUPPORTED`` /
    ``NOT_APPLICABLE`` cases (boundary cannot be measured). The
    distinction matters because downstream readers treat the two
    families differently.
    """
    if migration.measurement_status in _MIGRATION_UNKNOWN_STATUSES:
        return REASON_CODE_PRICE_WINDOW_UNKNOWN_MIGRATION
    return REASON_CODE_PRICE_WINDOW_MIGRATION_NOT_MEASURED


def _classification_reason_code(window_kind: str) -> str:
    if window_kind == PRICE_WINDOW_KIND_POST_MIGRATION_PRIMARY:
        return REASON_CODE_PRICE_WINDOW_POST_MIGRATION_PRIMARY
    if window_kind == PRICE_WINDOW_KIND_POST_MIGRATION_EXTENDED:
        return REASON_CODE_PRICE_WINDOW_POST_MIGRATION_EXTENDED
    if window_kind == PRICE_WINDOW_KIND_PRE_MIGRATION_EXCLUDED:
        return REASON_CODE_PRICE_WINDOW_PRE_MIGRATION_EXCLUDED
    return REASON_CODE_PRICE_WINDOW_UNKNOWN_MIGRATION


# ---------------------------------------------------------------------------
# Window classification
# ---------------------------------------------------------------------------


def classify_price_window_kind(
    observation: Stage25PriceObservation,
    migration: Stage25MigrationMeasurement,
) -> str:
    """Return the ``PRICE_WINDOW_KINDS`` token that applies to
    ``observation`` given ``migration``.

    The caller is responsible for verifying ``observation.token_mint
    == migration.token_mint`` -- this helper does NOT cross-check.
    Window classification is purely a function of the observation's
    ``observed_at_utc`` / ``block_time`` and the migration's
    ``measurement_status`` / ``consolidated_block_time``.

    Returns ``UNKNOWN_WINDOW`` whenever the upstream evidence is
    insufficient to assign a deterministic window: empty
    ``observed_at_utc``, migration not ``MEASURED``, observation
    ``block_time`` absent, or migration ``consolidated_block_time``
    absent.
    """
    if observation.observed_at_utc == "":
        return PRICE_WINDOW_KIND_UNKNOWN_WINDOW
    if migration.measurement_status != MEASUREMENT_STATUS_MEASURED:
        return PRICE_WINDOW_KIND_UNKNOWN_WINDOW
    if migration.consolidated_block_time < 0:
        return PRICE_WINDOW_KIND_UNKNOWN_WINDOW
    if observation.block_time < 0:
        return PRICE_WINDOW_KIND_UNKNOWN_WINDOW
    delta = observation.block_time - migration.consolidated_block_time
    if delta < 0:
        return PRICE_WINDOW_KIND_PRE_MIGRATION_EXCLUDED
    if delta <= POST_MIGRATION_PRIMARY_WINDOW_SECONDS:
        return PRICE_WINDOW_KIND_POST_MIGRATION_PRIMARY
    return PRICE_WINDOW_KIND_POST_MIGRATION_EXTENDED


# ---------------------------------------------------------------------------
# Reason-code assembly
# ---------------------------------------------------------------------------


def _build_window_reason_codes(
    *,
    observation: Stage25PriceObservation,
    migration: Stage25MigrationMeasurement,
    window_kind: str,
) -> tuple[str, ...]:
    codes: list[str] = []
    for code in observation.reason_codes:
        _append_unique(codes, code)

    if window_kind == PRICE_WINDOW_KIND_UNKNOWN_WINDOW:
        if observation.observed_at_utc == "":
            _append_unique(
                codes, REASON_CODE_PRICE_WINDOW_OBSERVED_AT_MISSING
            )
        if migration.measurement_status != MEASUREMENT_STATUS_MEASURED:
            _append_unique(
                codes, _migration_not_measured_reason_code(migration)
            )
        elif migration.consolidated_block_time < 0:
            _append_unique(
                codes, REASON_CODE_PRICE_WINDOW_MIGRATION_NOT_MEASURED
            )
        elif observation.block_time < 0:
            _append_unique(
                codes, REASON_CODE_PRICE_WINDOW_MIGRATION_NOT_MEASURED
            )
    else:
        _append_unique(codes, _classification_reason_code(window_kind))

    if observation.source_status == SOURCE_STATUS_PARTIAL:
        _append_unique(
            codes, REASON_CODE_PRICE_WINDOW_PARTIAL_SOURCE_STATUS
        )
    elif observation.source_status == SOURCE_STATUS_AMBIGUOUS:
        _append_unique(
            codes, REASON_CODE_PRICE_WINDOW_AMBIGUOUS_SOURCE_STATUS
        )
    return tuple(codes)


def _window_evidence_mapping(
    *,
    observation: Stage25PriceObservation,
    migration: Stage25MigrationMeasurement,
    window_version: str,
    threshold_version: str,
) -> Mapping[str, object]:
    """Build the auxiliary ``evidence`` mapping for a window observation.

    Carries diagnostic provenance that downstream readers can inspect
    without re-deriving the values: the source ``observation_hash``,
    the consolidated migration ``measurement_hash``, the migration
    ``measurement_status`` / ``consolidated_block_time``, the
    projector / threshold versions, and any preserved
    ``input_missing_fields`` from the upstream observation.
    """
    return _frozen_mapping(
        {
            "source_observation_hash": observation.observation_hash,
            "migration_measurement_hash": migration.measurement_hash,
            "migration_measurement_status": migration.measurement_status,
            "migration_consolidated_block_time": (
                migration.consolidated_block_time
            ),
            "window_version": window_version,
            "threshold_version": threshold_version,
            "input_missing_fields": list(observation.input_missing_fields),
        }
    )


# ---------------------------------------------------------------------------
# Per-observation projector
# ---------------------------------------------------------------------------


def build_price_window_observation(
    observation: Stage25PriceObservation,
    migration: Stage25MigrationMeasurement,
    *,
    window_version: str = STAGE25_PRICE_WINDOW_VERSION,
    threshold_version: str = DEFAULT_THRESHOLD_VERSION,
) -> Stage25PriceWindowObservation:
    """Build a ``Stage25PriceWindowObservation`` for a single observation.

    Token mismatch between ``observation`` and ``migration`` raises
    ``Stage25ContractError`` -- the caller is expected to group by
    token before calling this routine. The returned record's
    ``window_kind`` is the result of ``classify_price_window_kind``.

    Honesty invariants:

      * ``price`` is preserved verbatim from ``observation``; the
        record validator refuses to construct a record when
        ``source_status`` is ``PRESENT`` and ``price`` is ``None``.
      * ``price = 0`` is permitted only when the upstream observation
        already carries the explicit ``PRICE_OBSERVED_ZERO`` reason
        code (the record validator enforces this).
      * Non-PRESENT ``source_status`` values are preserved verbatim on
        the window record so downstream readers can later exclude the
        observation from ATH measurement.
    """
    if not isinstance(observation, Stage25PriceObservation):
        raise Stage25ContractError(
            "build_price_window_observation: observation must be a "
            "Stage25PriceObservation"
        )
    if not isinstance(migration, Stage25MigrationMeasurement):
        raise Stage25ContractError(
            "build_price_window_observation: migration must be a "
            "Stage25MigrationMeasurement"
        )
    if observation.token_mint != migration.token_mint:
        raise Stage25ContractError(
            "build_price_window_observation: token_mint mismatch between "
            "price observation and migration measurement"
        )

    window_kind = classify_price_window_kind(observation, migration)
    reason_codes = _build_window_reason_codes(
        observation=observation,
        migration=migration,
        window_kind=window_kind,
    )
    evidence = _window_evidence_mapping(
        observation=observation,
        migration=migration,
        window_version=window_version,
        threshold_version=threshold_version,
    )
    return build_price_window_observation_record(
        token_mint=observation.token_mint,
        source_family=observation.source_family,
        source_status=observation.source_status,
        window_kind=window_kind,
        observed_at_utc=observation.observed_at_utc,
        slot=observation.slot,
        block_time=observation.block_time,
        price=observation.price,
        quote_denomination=observation.quote_denomination,
        reason_codes=reason_codes,
        evidence=evidence,
    )


# ---------------------------------------------------------------------------
# Per-token projector
# ---------------------------------------------------------------------------


def build_price_window_observations_for_token(
    token: str,
    price_observations: tuple[Stage25PriceObservation, ...],
    migration: Stage25MigrationMeasurement,
    *,
    window_version: str = STAGE25_PRICE_WINDOW_VERSION,
    threshold_version: str = DEFAULT_THRESHOLD_VERSION,
) -> tuple[Stage25PriceWindowObservation, ...]:
    """Build window observations for ``token`` given a single migration
    measurement.

    Price observations whose ``token_mint`` does not match ``token``
    are rejected via ``Stage25ContractError``. The migration
    measurement's ``token_mint`` must equal ``token`` -- a mismatch
    raises ``Stage25ContractError``.

    Output ordering is deterministic: observations are sorted by the
    canonical ``normalize_price_observations`` key before projection
    so two equivalent input tuples produce byte-identical outputs.
    """
    if not isinstance(token, str) or token == "":
        raise Stage25ContractError(
            "build_price_window_observations_for_token: token must be a "
            "non-empty string"
        )
    if not isinstance(price_observations, tuple):
        raise Stage25ContractError(
            "build_price_window_observations_for_token: price_observations "
            "must be a tuple"
        )
    if not isinstance(migration, Stage25MigrationMeasurement):
        raise Stage25ContractError(
            "build_price_window_observations_for_token: migration must be "
            "a Stage25MigrationMeasurement"
        )
    if migration.token_mint != token:
        raise Stage25ContractError(
            "build_price_window_observations_for_token: migration "
            "token_mint does not match requested token"
        )

    for observation in price_observations:
        if observation.token_mint != token:
            raise Stage25ContractError(
                "build_price_window_observations_for_token: a price "
                "observation token_mint does not match requested token"
            )

    canonical = normalize_price_observations(price_observations)
    out: list[Stage25PriceWindowObservation] = []
    for observation in canonical:
        out.append(
            build_price_window_observation(
                observation,
                migration,
                window_version=window_version,
                threshold_version=threshold_version,
            )
        )
    return tuple(out)


# ---------------------------------------------------------------------------
# Top-level batch projector
# ---------------------------------------------------------------------------


def _index_migrations_by_token(
    migration_measurements: tuple[Stage25MigrationMeasurement, ...],
) -> dict[str, Stage25MigrationMeasurement]:
    indexed: dict[str, Stage25MigrationMeasurement] = {}
    for measurement in migration_measurements:
        if not isinstance(measurement, Stage25MigrationMeasurement):
            raise Stage25ContractError(
                "build_price_window_observations: every entry in "
                "migration_measurements must be a "
                "Stage25MigrationMeasurement"
            )
        if measurement.token_mint in indexed:
            raise Stage25ContractError(
                "build_price_window_observations: duplicate migration "
                "measurement for one token"
            )
        indexed[measurement.token_mint] = measurement
    return indexed


def _synthetic_unknown_migration_for_token(
    token: str,
) -> Stage25MigrationMeasurement:
    """Return a placeholder migration measurement for a token that has
    no consolidated migration record.

    The placeholder carries ``measurement_status=MISSING`` and the
    ``-1`` sentinel for ``consolidated_block_time``; downstream
    callers use ``measurement_status`` to detect the placeholder.
    Used only inside ``build_price_window_observations`` so window
    classification stays deterministic when a token has price
    observations but no migration record.
    """
    return build_migration_measurement_record(
        measurement_status=MEASUREMENT_STATUS_MISSING,
        confidence_level=CONFIDENCE_LEVEL_NONE,
        reconciliation_status=RECONCILIATION_STATUS_NO_SOURCES,
        token_mint=token,
        schema_version=DEFAULT_SCHEMA_VERSION,
        threshold_version=DEFAULT_THRESHOLD_VERSION,
        measurer_name=STAGE25_MIGRATION_MEASURER_NAME,
        measurer_version=STAGE25_MIGRATION_MEASURER_VERSION,
        consolidated_slot=_BLOCK_TIME_ABSENT_SENTINEL,
        consolidated_block_time=_BLOCK_TIME_ABSENT_SENTINEL,
        reconciled_signature="",
        selected_source_family="",
        contributing_source_count=0,
        reason_codes=(REASON_CODE_MIGRATION_NO_OBSERVATIONS,),
        numeric_features=_frozen_mapping({}),
        evidence=_frozen_mapping({}),
        input_missing_fields=(),
    )


def build_price_window_observations(
    price_observations: tuple[Stage25PriceObservation, ...],
    migration_measurements: tuple[Stage25MigrationMeasurement, ...],
    *,
    window_version: str = STAGE25_PRICE_WINDOW_VERSION,
    threshold_version: str = DEFAULT_THRESHOLD_VERSION,
) -> tuple[Stage25PriceWindowObservation, ...]:
    """Batch projector that groups observations by token and emits
    window observations for every (token, observation) pair.

    Behavior:

      * ``price_observations`` and ``migration_measurements`` MUST be
        tuples; non-tuple inputs raise ``Stage25ContractError``.
      * A migration measurement whose ``token_mint`` duplicates an
        earlier entry raises ``Stage25ContractError`` -- the caller
        must consolidate per token before calling this routine.
      * Tokens with price observations but no migration measurement
        produce window observations with ``window_kind=UNKNOWN_WINDOW``
        and the ``PRICE_WINDOW_MIGRATION_NOT_MEASURED`` reason code
        (deterministic per the Stage 25 spec).
      * Output ordering is deterministic: tokens are sorted
        lexicographically and intra-token observations are emitted in
        canonical normalized order.
    """
    if not isinstance(price_observations, tuple):
        raise Stage25ContractError(
            "build_price_window_observations: price_observations must be a "
            "tuple"
        )
    if not isinstance(migration_measurements, tuple):
        raise Stage25ContractError(
            "build_price_window_observations: migration_measurements must "
            "be a tuple"
        )
    indexed = _index_migrations_by_token(migration_measurements)
    grouped = group_price_observations_by_token(price_observations)
    out: list[Stage25PriceWindowObservation] = []
    for token in sorted(grouped.keys()):
        observations = grouped[token]
        migration = indexed.get(token)
        if migration is None:
            migration = _synthetic_unknown_migration_for_token(token)
        out.extend(
            build_price_window_observations_for_token(
                token,
                observations,
                migration,
                window_version=window_version,
                threshold_version=threshold_version,
            )
        )
    return tuple(out)


__all__ = [
    "build_price_window_observation",
    "build_price_window_observations",
    "build_price_window_observations_for_token",
    "classify_price_window_kind",
]

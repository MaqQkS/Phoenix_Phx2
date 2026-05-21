"""Stage 25.6 summary builder.

Pure summary builder that produces a canonicalizable summary
mapping for a Stage 25 runner result. The mapping carries row
counts per artifact, status counts per closed-set token axis, and
the locked Stage 25 stage / schema / summary version axes.

Public entry points:

  * ``build_stage25_summary``     -- pure builder that consumes the
                                     Stage 25.1-25.5 tuples plus a
                                     caller-injected ``created_at_utc``
                                     and returns a deterministic
                                     ``Mapping[str, object]``.
  * ``serialize_stage25_summary`` -- deterministic canonical-JSON
                                     serializer (sorted keys, no
                                     whitespace, ASCII-safe).

Determinism rules (Stage 25.6 invariants):

  * The summary mapping is built from sorted-key dicts so two
    equivalent inputs produce byte-identical canonical JSON.
  * The builder never invokes the wall clock; the caller injects
    ``created_at_utc``.
  * The builder never mutates its inputs.
  * Empty tuples produce zero counts deterministically.

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
    ATH_CANDIDATE_KINDS,
    CONFIDENCE_LEVELS,
    DEFAULT_SCHEMA_VERSION,
    MEASUREMENT_STATUSES,
    OBSERVE_ONLY_MODE,
    PRICE_WINDOW_KINDS,
    RECONCILIATION_STATUSES,
    REJECTION_REASONS,
    SOURCE_FAMILIES,
    SOURCE_STATUSES,
    STAGE25_SUMMARY_VERSION,
    STAGE_NAME,
    STAGE_VERSION,
)
from PHX2.stage25.errors import Stage25ContractError
from PHX2.stage25.models import (
    Stage25ATHCandidate,
    Stage25ATHMeasurement,
    Stage25MeasurementRejection,
    Stage25MigrationMeasurement,
    Stage25MigrationObservation,
    Stage25PriceWindowObservation,
    Stage25SourceReconciliation,
    canonical_json,
)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _frozen_mapping(value: Mapping[str, object]) -> Mapping[str, object]:
    return MappingProxyType(dict(value))


def _count_attr(
    records: tuple[object, ...],
    attr_name: str,
    closed_set: tuple[str, ...],
) -> dict[str, int]:
    """Return a deterministic sorted-key count mapping for ``attr_name``.

    Every member of ``closed_set`` is guaranteed to appear in the
    output with a count of at least 0 so two runs over identical
    inputs always produce identical key sets.
    """
    counts: dict[str, int] = {token: 0 for token in closed_set}
    for record in records:
        value = getattr(record, attr_name)
        if value in counts:
            counts[value] += 1
        else:
            # A value outside the closed set indicates a contract
            # violation upstream; surface it so the summary still
            # reflects honest evidence rather than silently dropping
            # the row.
            counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def _count_token_mints(records: tuple[object, ...]) -> int:
    """Return the count of distinct ``token_mint`` strings."""
    seen: set[str] = set()
    for record in records:
        token = getattr(record, "token_mint", None)
        if isinstance(token, str) and token != "":
            seen.add(token)
    return len(seen)


# ---------------------------------------------------------------------------
# Public builder
# ---------------------------------------------------------------------------


def build_stage25_summary(
    *,
    migration_observations: tuple[Stage25MigrationObservation, ...],
    migration_measurements: tuple[Stage25MigrationMeasurement, ...],
    price_window_observations: tuple[Stage25PriceWindowObservation, ...],
    ath_candidates: tuple[Stage25ATHCandidate, ...],
    source_reconciliations: tuple[Stage25SourceReconciliation, ...],
    ath_measurements: tuple[Stage25ATHMeasurement, ...],
    rejections: tuple[Stage25MeasurementRejection, ...],
    created_at_utc: str,
    schema_version: str = DEFAULT_SCHEMA_VERSION,
) -> Mapping[str, object]:
    """Build the canonicalizable Stage 25 summary mapping.

    The summary records:

      * Stage / schema / summary version axes.
      * Locked ``observe_only_mode`` posture marker.
      * Caller-injected ``created_at_utc``.
      * Row counts per artifact tuple.
      * Migration measurement_status / reconciliation_status counts.
      * Price window kind counts.
      * ATH candidate kind / candidate confidence / candidate source-status
        counts.
      * Source reconciliation status / confidence counts.
      * ATH measurement_status / confidence / reconciliation_status counts.
      * Rejection reason counts.
      * Distinct ``token_mint`` count across the runner inputs.

    The builder validates its inputs as tuples; it never mutates
    them. The returned mapping is frozen via ``MappingProxyType`` so
    callers cannot accidentally mutate the canonical body.
    """
    _require_tuple("migration_observations", migration_observations)
    _require_tuple("migration_measurements", migration_measurements)
    _require_tuple("price_window_observations", price_window_observations)
    _require_tuple("ath_candidates", ath_candidates)
    _require_tuple("source_reconciliations", source_reconciliations)
    _require_tuple("ath_measurements", ath_measurements)
    _require_tuple("rejections", rejections)
    if not isinstance(created_at_utc, str) or created_at_utc == "":
        raise Stage25ContractError(
            "created_at_utc must be a non-empty string"
        )
    if not isinstance(schema_version, str) or schema_version == "":
        raise Stage25ContractError(
            "schema_version must be a non-empty string"
        )

    row_counts: dict[str, int] = {
        "migration_observations": len(migration_observations),
        "migration_measurements": len(migration_measurements),
        "price_window_observations": len(price_window_observations),
        "ath_candidates": len(ath_candidates),
        "source_reconciliations": len(source_reconciliations),
        "ath_measurements": len(ath_measurements),
        "rejections": len(rejections),
    }

    migration_observation_status_counts = _count_attr(
        migration_observations, "source_status", SOURCE_STATUSES
    )
    migration_observation_source_family_counts = _count_attr(
        migration_observations, "source_family", SOURCE_FAMILIES
    )
    migration_measurement_status_counts = _count_attr(
        migration_measurements, "measurement_status", MEASUREMENT_STATUSES
    )
    migration_measurement_confidence_counts = _count_attr(
        migration_measurements, "confidence_level", CONFIDENCE_LEVELS
    )
    migration_measurement_reconciliation_counts = _count_attr(
        migration_measurements,
        "reconciliation_status",
        RECONCILIATION_STATUSES,
    )
    price_window_kind_counts = _count_attr(
        price_window_observations, "window_kind", PRICE_WINDOW_KINDS
    )
    price_window_source_status_counts = _count_attr(
        price_window_observations, "source_status", SOURCE_STATUSES
    )
    ath_candidate_kind_counts = _count_attr(
        ath_candidates, "candidate_kind", ATH_CANDIDATE_KINDS
    )
    ath_candidate_confidence_counts = _count_attr(
        ath_candidates, "confidence_level", CONFIDENCE_LEVELS
    )
    ath_candidate_source_status_counts = _count_attr(
        ath_candidates, "source_status", SOURCE_STATUSES
    )
    ath_candidate_source_family_counts = _count_attr(
        ath_candidates, "source_family", SOURCE_FAMILIES
    )
    source_reconciliation_status_counts = _count_attr(
        source_reconciliations,
        "reconciliation_status",
        RECONCILIATION_STATUSES,
    )
    source_reconciliation_confidence_counts = _count_attr(
        source_reconciliations, "confidence_level", CONFIDENCE_LEVELS
    )
    ath_measurement_status_counts = _count_attr(
        ath_measurements, "measurement_status", MEASUREMENT_STATUSES
    )
    ath_measurement_confidence_counts = _count_attr(
        ath_measurements, "confidence_level", CONFIDENCE_LEVELS
    )
    ath_measurement_reconciliation_counts = _count_attr(
        ath_measurements,
        "reconciliation_status",
        RECONCILIATION_STATUSES,
    )
    rejection_reason_counts = _count_attr(
        rejections, "rejection_reason", REJECTION_REASONS
    )

    observed_token_set: set[str] = set()
    for record in migration_observations:
        observed_token_set.add(record.token_mint)
    for record in migration_measurements:
        observed_token_set.add(record.token_mint)
    for record in price_window_observations:
        observed_token_set.add(record.token_mint)
    for record in ath_candidates:
        observed_token_set.add(record.token_mint)
    for record in source_reconciliations:
        observed_token_set.add(record.token_mint)
    for record in ath_measurements:
        observed_token_set.add(record.token_mint)
    observed_token_count = len(observed_token_set)

    body: dict[str, object] = {
        "stage_name": STAGE_NAME,
        "stage_version": STAGE_VERSION,
        "schema_version": schema_version,
        "summary_version": STAGE25_SUMMARY_VERSION,
        "observe_only_mode": OBSERVE_ONLY_MODE,
        "created_at_utc": created_at_utc,
        "row_counts": dict(sorted(row_counts.items())),
        "observed_token_count": observed_token_count,
        "migration_observation_source_status_counts": (
            migration_observation_status_counts
        ),
        "migration_observation_source_family_counts": (
            migration_observation_source_family_counts
        ),
        "migration_measurement_status_counts": (
            migration_measurement_status_counts
        ),
        "migration_measurement_confidence_counts": (
            migration_measurement_confidence_counts
        ),
        "migration_measurement_reconciliation_counts": (
            migration_measurement_reconciliation_counts
        ),
        "price_window_kind_counts": price_window_kind_counts,
        "price_window_source_status_counts": (
            price_window_source_status_counts
        ),
        "ath_candidate_kind_counts": ath_candidate_kind_counts,
        "ath_candidate_confidence_counts": ath_candidate_confidence_counts,
        "ath_candidate_source_status_counts": (
            ath_candidate_source_status_counts
        ),
        "ath_candidate_source_family_counts": (
            ath_candidate_source_family_counts
        ),
        "source_reconciliation_status_counts": (
            source_reconciliation_status_counts
        ),
        "source_reconciliation_confidence_counts": (
            source_reconciliation_confidence_counts
        ),
        "ath_measurement_status_counts": ath_measurement_status_counts,
        "ath_measurement_confidence_counts": (
            ath_measurement_confidence_counts
        ),
        "ath_measurement_reconciliation_counts": (
            ath_measurement_reconciliation_counts
        ),
        "rejection_reason_counts": rejection_reason_counts,
    }
    return _frozen_mapping(body)


def _require_tuple(field_name: str, value: object) -> None:
    if not isinstance(value, tuple):
        raise Stage25ContractError(f"{field_name} must be a tuple")


# ---------------------------------------------------------------------------
# Public serializer
# ---------------------------------------------------------------------------


def serialize_stage25_summary(summary: Mapping[str, object]) -> str:
    """Return the canonical JSON serialization of ``summary``.

    Canonical form: sorted keys, no whitespace separators,
    ASCII-safe (non-ASCII characters are escaped via the JSON
    ``\\uXXXX`` form). Identical summaries produce byte-identical
    serializations.
    """
    if not isinstance(summary, Mapping):
        raise Stage25ContractError("summary must be a mapping")
    return canonical_json(summary)


__all__ = [
    "build_stage25_summary",
    "serialize_stage25_summary",
]

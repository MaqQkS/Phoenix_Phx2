"""Stage 26.1 immutable input record contracts.

Every model is a ``typing.NamedTuple`` so instances are tuples,
immutable, deterministically ordered, and structurally hashable
when their fields are hashable. No model imports a Stage 25 record
class -- Stage 26.1 declares its own typed shapes and the reader
projects Stage 25 JSON / JSONL bytes into them.

Model rules (locked, per Stage 26.0 spec-lock §10):

  * Fields preserve Stage 25's ``None`` exactly. No ``None`` is
    coerced to ``0`` / ``""`` / a default. ``Optional[int]`` fields
    admit ``None``; ``int``-typed fields use the Stage 25 ``-1``
    "absent" sentinel where Stage 25 does.
  * Truth-class fields hold the verbatim Stage 25
    ``MEASUREMENT_STATUSES`` token; Stage 26.1 NEVER upgrades a
    Stage 25 truth class.
  * Reason-code / hash-tuple fields are ``tuple[str, ...]`` -- the
    reader converts the JSON arrays into tuples on projection so
    the record is fully immutable at the top level.
  * Free-shape JSON objects (``evidence`` / ``numeric_features``)
    are exposed as ``types.MappingProxyType`` over the parsed
    ``dict`` so the top-level mapping is read-only. Nested values
    are preserved verbatim.
  * No model carries a ``denominator_status`` field -- denominator
    semantics are Stage 26.2.
  * No model carries an approval-state field -- approval vocabulary
    is later.

Record kinds (mirror the locked Stage 25 artifact set, one per
artifact):

  * ``Stage25ManifestInput``           -- projected stage25_manifest.json
  * ``Stage25SummaryInput``            -- projected stage25_summary.json
  * ``MigrationObservationInput``      -- one row of
                                          stage25_migration_observations.jsonl
  * ``MigrationMeasurementInput``      -- one row of
                                          stage25_migration_measurements.jsonl
  * ``PriceWindowObservationInput``    -- one row of
                                          stage25_price_window_observations.jsonl
  * ``ATHCandidateInput``              -- one row of
                                          stage25_ath_candidates.jsonl
  * ``SourceReconciliationInput``      -- one row of
                                          stage25_source_reconciliations.jsonl
  * ``ATHMeasurementInput``            -- one row of
                                          stage25_ath_measurements.jsonl
  * ``MeasurementRejectionInput``      -- one row of
                                          stage25_measurement_rejections.jsonl

Validation surface:

  * ``Stage25ArtifactReference``       -- (basename, sha256) pin.
  * ``ArtifactValidationEntry``        -- one per-artifact
                                          validation outcome.
  * ``ArtifactValidationReport``       -- tuple of entries plus a
                                          locked ``ok`` derived flag.
  * ``Stage25ArtifactSet``             -- bundle of typed records +
                                          stage25 manifest pin.
  * ``Stage26ReaderResult``            -- Stage25ArtifactSet +
                                          validation report.
  * ``Stage26CalibrationInputSet``     -- the Stage 26.1 high-level
                                          calibration-input bundle:
                                          reader result + Stage 26
                                          version axis + Stage 25
                                          manifest pin.
"""

from __future__ import annotations

from typing import Mapping, NamedTuple, Optional


# ---------------------------------------------------------------------------
# Per-row input records
# ---------------------------------------------------------------------------


class MigrationObservationInput(NamedTuple):
    """One projected stage25_migration_observations.jsonl row.

    Field order mirrors the Stage 25 writer's serialization order.
    Stage 26.1 preserves Stage 25's ``-1`` sentinel for absent
    ``slot`` / ``block_time``; it does NOT promote ``-1`` to
    ``None`` or back-fill a value.
    """

    token_mint: str
    source_family: str
    source_status: str
    observed_at_utc: str
    slot: int
    block_time: int
    migration_signature: str
    migration_pool: str
    provider_id: str
    reason_codes: tuple[str, ...]
    evidence: Mapping[str, object]
    input_missing_fields: tuple[str, ...]
    observation_hash: str


class MigrationMeasurementInput(NamedTuple):
    """One projected stage25_migration_measurements.jsonl row.

    Stage 25 invariants Stage 26.1 PRESERVES (and the reader rejects
    rows that violate them):

      * MEASURED -> ``reconciled_signature != ""`` AND
        ``selected_source_family != ""`` AND
        ``consolidated_slot >= 0`` AND
        ``consolidated_block_time >= 0``.
      * non-MEASURED -> ``reconciled_signature == ""`` AND
        ``selected_source_family == ""`` AND
        ``consolidated_slot == -1`` AND
        ``consolidated_block_time == -1``.
    """

    measurement_family: str
    measurement_status: str
    confidence_level: str
    reconciliation_status: str
    token_mint: str
    schema_version: str
    threshold_version: str
    measurer_name: str
    measurer_version: str
    consolidated_slot: int
    consolidated_block_time: int
    reconciled_signature: str
    selected_source_family: str
    contributing_source_count: int
    reason_codes: tuple[str, ...]
    numeric_features: Mapping[str, object]
    evidence: Mapping[str, object]
    input_missing_fields: tuple[str, ...]
    measurement_hash: str


class PriceWindowObservationInput(NamedTuple):
    """One projected stage25_price_window_observations.jsonl row.

    ``price`` admits ``None`` (the Stage 25 ``null``-as-unknown
    encoding); the reader does NOT coerce ``None`` to ``0`` or back-
    fill a synthetic price.
    """

    token_mint: str
    source_family: str
    source_status: str
    window_kind: str
    observed_at_utc: str
    slot: int
    block_time: int
    price: Optional[int]
    quote_denomination: str
    reason_codes: tuple[str, ...]
    evidence: Mapping[str, object]
    observation_hash: str


class ATHCandidateInput(NamedTuple):
    """One projected stage25_ath_candidates.jsonl row.

    ``peak_price`` admits ``None`` (the Stage 25 INSUFFICIENT_DATA
    encoding). Non-INSUFFICIENT_DATA rows carry a non-null
    ``peak_price``; the reader rejects rows that disagree.
    """

    token_mint: str
    source_family: str
    source_status: str
    candidate_kind: str
    confidence_level: str
    peak_observed_at_utc: str
    peak_slot: int
    peak_block_time: int
    peak_price: Optional[int]
    quote_denomination: str
    reason_codes: tuple[str, ...]
    evidence: Mapping[str, object]
    input_missing_fields: tuple[str, ...]
    candidate_hash: str


class SourceReconciliationInput(NamedTuple):
    """One projected stage25_source_reconciliations.jsonl row.

    ``disagreement_metric`` is the Stage 25 nullable object; the
    reader projects ``null`` as ``None`` and a present object as a
    read-only ``Mapping[str, object]``.
    """

    measurement_family: str
    reconciliation_status: str
    confidence_level: str
    token_mint: str
    source_families: tuple[str, ...]
    contributing_source_count: int
    disagreeing_source_count: int
    disagreement_metric: Optional[Mapping[str, object]]
    reason_codes: tuple[str, ...]
    evidence: Mapping[str, object]
    reconciliation_hash: str


class ATHMeasurementInput(NamedTuple):
    """One projected stage25_ath_measurements.jsonl row.

    Stage 25 invariants Stage 26.1 PRESERVES (the reader rejects
    rows that violate them):

      * MEASURED -> all four peak fields are populated:
        ``consolidated_peak_slot >= 0``,
        ``consolidated_peak_block_time >= 0``,
        ``consolidated_peak_price is not None``,
        ``peak_source_family != ""``,
        ``reconciled_peak_observed_at_utc != ""``.
      * non-MEASURED -> all four peak fields are absent /
        sentinel / empty.
    """

    measurement_family: str
    measurement_status: str
    confidence_level: str
    reconciliation_status: str
    token_mint: str
    schema_version: str
    threshold_version: str
    measurer_name: str
    measurer_version: str
    consolidated_peak_slot: int
    consolidated_peak_block_time: int
    consolidated_peak_price: Optional[int]
    quote_denomination: str
    peak_source_family: str
    reconciled_peak_observed_at_utc: str
    time_to_peak_seconds: Optional[int]
    contributing_source_count: int
    reason_codes: tuple[str, ...]
    numeric_features: Mapping[str, object]
    evidence: Mapping[str, object]
    input_missing_fields: tuple[str, ...]
    measurement_hash: str


class MeasurementRejectionInput(NamedTuple):
    """One projected stage25_measurement_rejections.jsonl row."""

    rejection_reason: str
    token_mint: str
    source_family: str
    detail: str
    reason_codes: tuple[str, ...]


# ---------------------------------------------------------------------------
# Manifest / summary / artifact-reference / artifact-set records
# ---------------------------------------------------------------------------


class Stage25ArtifactReference(NamedTuple):
    """A read-only (basename, sha256) reference to a Stage 25 artifact.

    The Stage 26.1 reader records the consumed Stage 25 manifest as
    a ``Stage25ArtifactReference`` whose ``artifact_basename`` is
    the manifest's own basename and whose ``artifact_sha256`` is the
    sha256 of the manifest bytes on disk at load time. Per-artifact
    references record each non-self manifest entry's
    ``(basename, sha256)`` pair so downstream Stage 26.x consumers
    can pin individual artifacts without re-reading the manifest.
    """

    artifact_basename: str
    artifact_sha256: str


class Stage25ManifestFileEntryInput(NamedTuple):
    """One file entry projected from the Stage 25 manifest's ``files`` array.

    Stage 26.1 preserves the locked Stage 25 fields verbatim and
    the locked self-entry sentinels (``-1`` byte_count / row_count;
    sentinel sha256 string) verbatim. The reader does NOT collapse
    the sentinel to a real digest and does NOT fabricate a real
    digest for the manifest self-entry.
    """

    file_basename: str
    sha256: str
    row_count: int
    byte_count: int


class Stage25Stage24ManifestPinInput(NamedTuple):
    """Projection of the optional ``upstream_stage24_pin`` object.

    Stage 26.1 records the upstream-Stage-24 pin verbatim when the
    Stage 25 manifest carries one. Stage 26.1 does NOT verify the
    upstream Stage 24 manifest's bytes -- Stage 26.1 carries the
    pin forward as evidence only.
    """

    upstream_manifest_basename: str
    upstream_manifest_sha256: str


class Stage25ManifestInput(NamedTuple):
    """Projection of stage25_manifest.json.

    Locked top-level fields mirror the Stage 25 writer's body. Stage
    26.1 preserves ``runner_name`` / ``runner_version`` /
    ``writer_name`` / ``writer_version`` verbatim so downstream
    Stage 26.x consumers can pin the exact Stage 25 code that
    produced the manifest.
    """

    stage_name: str
    stage_version: str
    schema_version: str
    observe_only_mode: str
    redaction_confirmed: str
    manifest_kind: str
    files: tuple[Stage25ManifestFileEntryInput, ...]
    upstream_stage24_pin: Optional[Stage25Stage24ManifestPinInput]
    created_at_utc: str
    runner_name: str
    runner_version: str
    writer_name: str
    writer_version: str


class Stage25SummaryInput(NamedTuple):
    """Projection of stage25_summary.json.

    Stage 26.1 preserves the Stage 25 summary's closed-set count
    maps as read-only ``MappingProxyType`` objects. The summary
    carries no per-row data and Stage 26.1 reports it verbatim --
    no aggregation or re-derivation.
    """

    stage_name: str
    stage_version: str
    schema_version: str
    summary_version: str
    observe_only_mode: str
    created_at_utc: str
    observed_token_count: int
    row_counts: Mapping[str, int]
    migration_observation_source_family_counts: Mapping[str, int]
    migration_observation_source_status_counts: Mapping[str, int]
    migration_measurement_status_counts: Mapping[str, int]
    migration_measurement_confidence_counts: Mapping[str, int]
    migration_measurement_reconciliation_counts: Mapping[str, int]
    price_window_kind_counts: Mapping[str, int]
    price_window_source_status_counts: Mapping[str, int]
    ath_candidate_kind_counts: Mapping[str, int]
    ath_candidate_confidence_counts: Mapping[str, int]
    ath_candidate_source_family_counts: Mapping[str, int]
    ath_candidate_source_status_counts: Mapping[str, int]
    source_reconciliation_status_counts: Mapping[str, int]
    source_reconciliation_confidence_counts: Mapping[str, int]
    ath_measurement_status_counts: Mapping[str, int]
    ath_measurement_confidence_counts: Mapping[str, int]
    ath_measurement_reconciliation_counts: Mapping[str, int]
    rejection_reason_counts: Mapping[str, int]


class Stage25ArtifactSet(NamedTuple):
    """Bundle of typed Stage 25 input records + the manifest pin.

    The bundle returned by the low-level
    ``load_stage25_artifact_set`` reader entrypoint. Per-record
    tuples preserve the on-disk Stage 25 row order; the reader does
    NOT re-sort.
    """

    manifest: Stage25ManifestInput
    summary: Stage25SummaryInput
    migration_observations: tuple[MigrationObservationInput, ...]
    migration_measurements: tuple[MigrationMeasurementInput, ...]
    price_window_observations: tuple[PriceWindowObservationInput, ...]
    ath_candidates: tuple[ATHCandidateInput, ...]
    source_reconciliations: tuple[SourceReconciliationInput, ...]
    ath_measurements: tuple[ATHMeasurementInput, ...]
    measurement_rejections: tuple[MeasurementRejectionInput, ...]
    stage25_manifest_pin: Stage25ArtifactReference
    per_artifact_pins: tuple[Stage25ArtifactReference, ...]


# ---------------------------------------------------------------------------
# Validation report records
# ---------------------------------------------------------------------------


class ArtifactValidationEntry(NamedTuple):
    """One per-artifact validation outcome.

    Fields:

      * ``artifact_basename`` -- the basename the entry concerns;
        ``""`` for entries that concern the artifact set as a whole.
      * ``status``            -- ``ARTIFACT_VALIDATION_STATUSES``
        token.
      * ``detail``            -- one-line diagnostic. Stage 26.1
        diagnostics deliberately stick to plain prose plus locked
        Stage 25 / Stage 26 vocabulary tokens.
      * ``error_code``        -- ``STAGE26_ERROR_CODES`` token, or
        the empty string for ``VALIDATED`` entries.
    """

    artifact_basename: str
    status: str
    detail: str
    error_code: str


class ArtifactValidationReport(NamedTuple):
    """Structured validation report for a Stage 25 artifact set.

    ``ok`` is ``True`` iff every entry's ``status`` is
    ``ARTIFACT_VALIDATION_STATUS_VALIDATED``. Stage 26.1 callers
    consult ``ok`` to gate ``load_stage25_artifact_set`` against
    the typed-error path.
    """

    entries: tuple[ArtifactValidationEntry, ...]
    ok: bool


# ---------------------------------------------------------------------------
# Reader / calibration-input wrappers
# ---------------------------------------------------------------------------


class Stage26ReaderResult(NamedTuple):
    """Pair of an artifact set and the validation report it satisfied.

    Returned by ``load_stage25_artifact_set`` when validation
    succeeded (every entry ``VALIDATED``). Carrying the report
    alongside the records lets Stage 26.x callers inspect the
    validation outcome without re-running the validator.
    """

    artifact_set: Stage25ArtifactSet
    validation_report: ArtifactValidationReport


class Stage26CalibrationInputSet(NamedTuple):
    """Stage 26.1 high-level calibration-input bundle.

    Wraps a successfully-loaded ``Stage26ReaderResult`` with the
    Stage 26 calibration-input version axis and the locked Stage 25
    manifest pin. Stage 26.2+ consumes this bundle; the Stage 25
    manifest pin is the upstream provenance Stage 26.x sub-stages
    carry forward (mirror of the Stage 24 -> Stage 25 pin
    convention).
    """

    stage26_calibration_input_version: str
    stage25_manifest_pin: Stage25ArtifactReference
    reader_result: Stage26ReaderResult


__all__ = [
    "ATHCandidateInput",
    "ATHMeasurementInput",
    "ArtifactValidationEntry",
    "ArtifactValidationReport",
    "MeasurementRejectionInput",
    "MigrationMeasurementInput",
    "MigrationObservationInput",
    "PriceWindowObservationInput",
    "SourceReconciliationInput",
    "Stage25ArtifactReference",
    "Stage25ArtifactSet",
    "Stage25ManifestFileEntryInput",
    "Stage25ManifestInput",
    "Stage25Stage24ManifestPinInput",
    "Stage25SummaryInput",
    "Stage26CalibrationInputSet",
    "Stage26ReaderResult",
]

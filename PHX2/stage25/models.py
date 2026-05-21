"""Stage 25 immutable models and deterministic hash helpers (foundation only at 25.1).

This module ships the typed ``NamedTuple`` records that every
Stage 25.2+ measurer / reconciler / runner / artifact writer
must satisfy, plus the canonical-JSON deterministic hash helpers
used to derive observation / measurement / candidate /
reconciliation hashes.

Records:

  * ``Stage25MigrationObservation``  -- per-source migration
                                        evidence row projected from
                                        a Stage 25-shaped migration-
                                        observation JSONL row.
  * ``Stage25PriceObservation``      -- per-source price-evidence
                                        row projected from a Stage
                                        25-shaped price-observation
                                        JSONL row.
  * ``Stage25MeasurementInput``      -- per-token-mint container
                                        bundling the migration- and
                                        price-observation tuples a
                                        future measurer will consume.
  * ``Stage25MigrationMeasurement``  -- consolidated migration
                                        boundary measurement
                                        (Stage 25.2+ surface; 25.1
                                        ships the shape only).
  * ``Stage25PriceWindowObservation`` -- window-classified price
                                        observation (Stage 25.3+
                                        surface).
  * ``Stage25ATHCandidate``          -- ATH candidate record
                                        (Stage 25.3+ surface).
  * ``Stage25ATHMeasurement``        -- consolidated ATH
                                        measurement (Stage 25.4+
                                        surface).
  * ``Stage25SourceReconciliation``  -- per-measurement source
                                        reconciliation record
                                        (Stage 25.4+ surface).
  * ``Stage25MeasurementRejection``  -- rejection record carrying a
                                        closed-set rejection_reason.
  * ``Stage25UnifiedMeasurement``    -- unified per-measurement disk
                                        record (Stage 25.5+ surface).
  * ``Stage25RunnerResult``          -- placeholder runner-output
                                        record (Stage 25.5+ surface).

Hashing:

  * ``canonical_json``                  -- canonical UTF-8 JSON
                                           encoding (sorted keys, no
                                           whitespace).
  * ``stage25_hash``                    -- sha256 hex of canonical
                                           JSON encoding of a
                                           canonicalizable value.
  * ``compute_observation_hash``        -- canonical hash over an
                                           observation body (migration
                                           or price).
  * ``compute_measurement_hash``        -- canonical hash over a
                                           measurement body
                                           (migration / ATH / unified).
  * ``compute_candidate_hash``          -- canonical hash over an ATH
                                           candidate body.
  * ``compute_reconciliation_hash``     -- canonical hash over a
                                           source-reconciliation body.

Design notes:

  * All records are ``NamedTuple`` so they are immutable, hashable
    by value, and trivially serializable. ``setattr`` raises.
  * Hashes are derived from canonical-JSON encoding with sorted
    keys, so dict ordering does not affect the hash.
  * Unstable runtime-only fields (``created_at_utc``) are NOT
    included in any hash.
  * Price / amount fields are ``int | None``. Stage 25 NEVER
    coerces ``None`` to ``0`` -- ``None`` honestly records "we
    did not observe this value." A legitimate observed ``0`` is
    only permitted with the explicit
    ``PRICE_OBSERVED_ZERO`` reason code.
  * Slot / block_time fields are strict ``int`` and use the ``-1``
    sentinel for "absent" so a ``NamedTuple`` field can keep its
    ``int`` annotation without breaking the deterministic
    canonical-JSON hash contract.

This module imports only stdlib (``hashlib`` / ``json`` /
``math``) plus the Stage 25 constants and errors. It does NOT
import Stage 21 / Stage 22 / Stage 23 / Stage 24 production
code, does NOT import any network / RPC / messaging / DB /
scheduler / secrets-management library, does NOT read the
process environment, does NOT define a CLI surface, and contains
no top-level I/O.
"""

from __future__ import annotations

import hashlib
import json
import math
from typing import Mapping, NamedTuple, Optional

from PHX2.stage25.constants import (
    MEASUREMENT_FAMILY_MIGRATION,
    REASON_CODE_PRICE_OBSERVED_ZERO,
    SOURCE_STATUS_PRESENT,
    assert_ath_candidate_kind_in_closed_set,
    assert_confidence_level_in_closed_set,
    assert_measurement_family_in_closed_set,
    assert_measurement_status_in_closed_set,
    assert_non_negative_int_or_minus_one_sentinel,
    assert_optional_non_negative_int,
    assert_price_window_kind_in_closed_set,
    assert_quote_denomination_in_closed_set,
    assert_reconciliation_status_in_closed_set,
    assert_rejection_reason_in_closed_set,
    assert_source_family_in_closed_set,
    assert_source_status_in_closed_set,
)
from PHX2.stage25.errors import Stage25ContractError


# ---------------------------------------------------------------------------
# Stage25MigrationObservation
# ---------------------------------------------------------------------------


class Stage25MigrationObservation(NamedTuple):
    """Per-source migration evidence row.

    One ``Stage25MigrationObservation`` is the projection of a
    single Stage 25-shaped migration-observation JSONL row.

    Fields:

      * ``token_mint``        -- short non-secret token mint string.
      * ``source_family``     -- one of ``SOURCE_FAMILIES``.
      * ``source_status``     -- one of ``SOURCE_STATUSES``.
      * ``observed_at_utc``   -- ISO-8601 UTC string carried from
                                 the upstream artifact. May be empty.
      * ``slot``              -- migration slot when present; ``-1``
                                 sentinel when absent.
      * ``block_time``        -- Unix-seconds time of the migration
                                 slot when present; ``-1`` sentinel
                                 when absent.
      * ``migration_signature`` -- transaction signature evidencing
                                 the migration when present; empty
                                 string when absent.
      * ``migration_pool``    -- post-migration pool address when
                                 present; empty string when absent.
      * ``provider_id``       -- short non-secret operator label
                                 (e.g. ``"birdeye"``).
      * ``reason_codes``      -- tuple of short closed-set reason
                                 tokens describing extra evidence
                                 (e.g. partial-evidence tokens).
      * ``evidence``          -- frozen mapping carrying upstream
                                 evidence the reader projected
                                 verbatim.
      * ``input_missing_fields`` -- sorted tuple of preserved-field
                                 concept names absent from the
                                 upstream row.
      * ``observation_hash``  -- deterministic SHA-256 hex of the
                                 canonical-JSON projection of the
                                 observation body.
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


# ---------------------------------------------------------------------------
# Stage25PriceObservation
# ---------------------------------------------------------------------------


class Stage25PriceObservation(NamedTuple):
    """Per-source price-evidence row.

    One ``Stage25PriceObservation`` is the projection of a single
    Stage 25-shaped price-observation JSONL row.

    Fields:

      * ``token_mint``         -- short non-secret token mint string.
      * ``source_family``      -- one of ``SOURCE_FAMILIES``.
      * ``source_status``      -- one of ``SOURCE_STATUSES``.
      * ``observed_at_utc``    -- ISO-8601 UTC string.
      * ``slot``               -- slot the price was observed at;
                                  ``-1`` sentinel when absent.
      * ``block_time``         -- Unix-seconds block time; ``-1``
                                  sentinel when absent.
      * ``price``              -- observed price as a non-negative
                                  int (denominated per
                                  ``quote_denomination``); ``None``
                                  when not observed. ``0`` is only
                                  legal with the explicit
                                  ``PRICE_OBSERVED_ZERO`` reason code.
      * ``quote_denomination`` -- one of ``QUOTE_DENOMINATIONS``.
      * ``provider_id``        -- short non-secret operator label.
      * ``reason_codes``       -- tuple of short closed-set reason
                                  tokens.
      * ``evidence``           -- frozen mapping carrying upstream
                                  evidence verbatim.
      * ``input_missing_fields`` -- sorted tuple of preserved-field
                                  concept names absent from the
                                  upstream row.
      * ``observation_hash``   -- deterministic SHA-256 hex of the
                                  canonical-JSON projection of the
                                  observation body.
    """

    token_mint: str
    source_family: str
    source_status: str
    observed_at_utc: str
    slot: int
    block_time: int
    price: Optional[int]
    quote_denomination: str
    provider_id: str
    reason_codes: tuple[str, ...]
    evidence: Mapping[str, object]
    input_missing_fields: tuple[str, ...]
    observation_hash: str


# ---------------------------------------------------------------------------
# Stage25MeasurementInput
# ---------------------------------------------------------------------------


class Stage25MeasurementInput(NamedTuple):
    """Per-token-mint container bundling observation tuples.

    A future Stage 25.2+ measurer consumes a
    ``Stage25MeasurementInput`` and emits a
    ``Stage25MigrationMeasurement`` / ``Stage25ATHMeasurement``
    pair. Stage 25.1 ships the container shape only.

    Fields:

      * ``token_mint``             -- short non-secret token mint
                                      string. Required non-empty.
      * ``schema_version``         -- locked Stage 25 schema version.
      * ``migration_observations`` -- tuple of
                                      ``Stage25MigrationObservation``
                                      records for this token mint.
                                      May be empty.
      * ``price_observations``     -- tuple of
                                      ``Stage25PriceObservation``
                                      records for this token mint.
                                      May be empty.
    """

    token_mint: str
    schema_version: str
    migration_observations: tuple[Stage25MigrationObservation, ...]
    price_observations: tuple[Stage25PriceObservation, ...]


# ---------------------------------------------------------------------------
# Stage25MigrationMeasurement
# ---------------------------------------------------------------------------


class Stage25MigrationMeasurement(NamedTuple):
    """Consolidated migration boundary measurement (Stage 25.2+ surface).

    Stage 25.1 ships the record shape only; the Stage 25.2 measurer
    constructs instances via ``build_migration_measurement_record``.

    Closed-set semantics:

      * ``measurement_family``    -- always ``"MIGRATION"``.
      * ``measurement_status``    -- one of ``MEASUREMENT_STATUSES``.
      * ``confidence_level``      -- one of ``CONFIDENCE_LEVELS``.
      * ``reconciliation_status`` -- one of ``RECONCILIATION_STATUSES``.
                                     First-class field added at Stage
                                     25.2 so downstream consumers do
                                     not have to parse the ``evidence``
                                     mapping.
      * ``selected_source_family`` -- either a member of
                                     ``SOURCE_FAMILIES`` or the empty
                                     string. The empty string is
                                     reserved for unmeasured records
                                     (``MISSING`` / ``AMBIGUOUS`` /
                                     ``UNSUPPORTED`` / ``REJECTED`` /
                                     ``PARTIAL``).

    ``reconciled_signature`` is the consolidated migration transaction
    signature when the measurement is ``MEASURED``; the empty string
    when the measurement is not ``MEASURED``. ``consolidated_slot`` /
    ``consolidated_block_time`` remain the first-class consolidated
    slot / Unix-seconds block time -- no duplicate ``reconciled_*``
    int field is added.
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


# ---------------------------------------------------------------------------
# Stage25PriceWindowObservation
# ---------------------------------------------------------------------------


class Stage25PriceWindowObservation(NamedTuple):
    """Window-classified price observation (Stage 25.3+ surface).

    The Stage 25.3 projector takes a ``Stage25PriceObservation`` plus
    a ``Stage25MigrationMeasurement`` and emits a window-classified
    record assigning the observation to a price window. Stage 25.1
    ships the record shape only.

    Closed-set semantics:

      * ``source_family`` -- one of ``SOURCE_FAMILIES``.
      * ``source_status`` -- one of ``SOURCE_STATUSES``. Preserved
                             verbatim from the upstream
                             ``Stage25PriceObservation`` so a
                             non-PRESENT status survives the
                             window-classification step.
      * ``window_kind``   -- one of ``PRICE_WINDOW_KINDS``.

    Honesty rules:

      * ``price`` is ``Optional[int]``. ``None`` honestly records
        "no price observed" and is reserved for non-PRESENT
        ``source_status`` values; the record validator refuses
        ``None`` when ``source_status`` is ``PRESENT``.
      * ``price = 0`` is only legal with the explicit
        ``PRICE_OBSERVED_ZERO`` reason code.
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


# ---------------------------------------------------------------------------
# Stage25ATHCandidate
# ---------------------------------------------------------------------------


class Stage25ATHCandidate(NamedTuple):
    """ATH (all-time-high) candidate record (Stage 25.3+ surface).

    A future Stage 25.3+ projector emits one
    ``Stage25ATHCandidate`` per (token_mint, source_family,
    candidate_kind) triple. Stage 25.1 ships the record shape only.

    Closed-set semantics:

      * ``candidate_kind`` -- one of ``ATH_CANDIDATE_KINDS``.
    """

    token_mint: str
    source_family: str
    candidate_kind: str
    peak_observed_at_utc: str
    peak_slot: int
    peak_block_time: int
    peak_price: Optional[int]
    quote_denomination: str
    reason_codes: tuple[str, ...]
    evidence: Mapping[str, object]
    input_missing_fields: tuple[str, ...]
    candidate_hash: str


# ---------------------------------------------------------------------------
# Stage25ATHMeasurement
# ---------------------------------------------------------------------------


class Stage25ATHMeasurement(NamedTuple):
    """Consolidated ATH measurement (Stage 25.4+ surface).

    Stage 25.1 ships the record shape only.

    Closed-set semantics:

      * ``measurement_family`` -- always ``"ATH"``.
      * ``measurement_status`` -- one of ``MEASUREMENT_STATUSES``.
      * ``confidence_level``   -- one of ``CONFIDENCE_LEVELS``.
    """

    measurement_family: str
    measurement_status: str
    confidence_level: str
    token_mint: str
    schema_version: str
    threshold_version: str
    measurer_name: str
    measurer_version: str
    consolidated_peak_slot: int
    consolidated_peak_block_time: int
    consolidated_peak_price: Optional[int]
    quote_denomination: str
    contributing_source_count: int
    reason_codes: tuple[str, ...]
    numeric_features: Mapping[str, object]
    evidence: Mapping[str, object]
    input_missing_fields: tuple[str, ...]
    measurement_hash: str


# ---------------------------------------------------------------------------
# Stage25SourceReconciliation
# ---------------------------------------------------------------------------


class Stage25SourceReconciliation(NamedTuple):
    """Per-measurement source-reconciliation record (Stage 25.4+ surface).

    Stage 25.1 ships the record shape only.

    Closed-set semantics:

      * ``reconciliation_status`` -- one of ``RECONCILIATION_STATUSES``.
      * ``measurement_family``    -- one of ``MEASUREMENT_FAMILIES``.
    """

    measurement_family: str
    reconciliation_status: str
    token_mint: str
    source_families: tuple[str, ...]
    contributing_source_count: int
    disagreeing_source_count: int
    reason_codes: tuple[str, ...]
    evidence: Mapping[str, object]
    reconciliation_hash: str


# ---------------------------------------------------------------------------
# Stage25MeasurementRejection
# ---------------------------------------------------------------------------


class Stage25MeasurementRejection(NamedTuple):
    """Rejection record carrying a closed-set rejection_reason.

    Stage 25 surfaces (input reader, measurer, reconciler) emit a
    rejection record rather than fabricating a measurement when
    an input row or measurement attempt fails a contract check.

    Closed-set semantics:

      * ``rejection_reason`` -- one of ``REJECTION_REASONS``.
    """

    rejection_reason: str
    token_mint: str
    source_family: str
    detail: str
    reason_codes: tuple[str, ...]


# ---------------------------------------------------------------------------
# Stage25UnifiedMeasurement
# ---------------------------------------------------------------------------


class Stage25UnifiedMeasurement(NamedTuple):
    """Unified per-measurement disk record (Stage 25.5+ surface).

    The disk-shape every Stage 25 measurer feeds into. Stage 25.1
    ships the record shape only; no runner constructs instances
    of it.
    """

    measurement_family: str
    measurement_status: str
    confidence_level: str
    token_mint: str
    schema_version: str
    threshold_version: str
    measurer_name: str
    measurer_version: str
    primary_slot: int
    primary_block_time: int
    primary_price: Optional[int]
    quote_denomination: str
    contributing_source_count: int
    reconciliation_status: str
    reason_codes: tuple[str, ...]
    numeric_features: Mapping[str, object]
    evidence: Mapping[str, object]
    input_missing_fields: tuple[str, ...]
    measurement_hash: str
    created_at_utc: str


# ---------------------------------------------------------------------------
# Stage25RunnerResult
# ---------------------------------------------------------------------------


class Stage25RunnerResult(NamedTuple):
    """Immutable wrapper bundling Stage 25 runner outputs (Stage 25.5+).

    Stage 25.1 ships the record shape only.
    """

    migration_measurements: tuple[Stage25MigrationMeasurement, ...]
    ath_measurements: tuple[Stage25ATHMeasurement, ...]
    unified_measurements: tuple[Stage25UnifiedMeasurement, ...]
    source_reconciliations: tuple[Stage25SourceReconciliation, ...]
    rejections: tuple[Stage25MeasurementRejection, ...]
    input_token_count: int
    input_rejection_count: int
    created_at_utc: str


# ---------------------------------------------------------------------------
# Closed-set wrappers (re-raise ValueError as Stage25ContractError)
# ---------------------------------------------------------------------------
#
# The constants module raises a private ValueError subclass on a
# closed-set miss. The model surface re-raises that as the typed
# ``Stage25ContractError`` so callers only ever catch one Stage 25
# error type.


def _wrap_closed_set(call: object) -> None:
    """Run a closed-set assertion and re-raise as Stage25ContractError."""
    try:
        call()  # type: ignore[operator]
    except ValueError as exc:
        raise Stage25ContractError(str(exc)) from exc


def _require_measurement_family(value: str) -> None:
    _wrap_closed_set(lambda: assert_measurement_family_in_closed_set(value))


def _require_source_family(value: str) -> None:
    _wrap_closed_set(lambda: assert_source_family_in_closed_set(value))


def _require_source_status(value: str) -> None:
    _wrap_closed_set(lambda: assert_source_status_in_closed_set(value))


def _require_measurement_status(value: str) -> None:
    _wrap_closed_set(lambda: assert_measurement_status_in_closed_set(value))


def _require_confidence_level(value: str) -> None:
    _wrap_closed_set(lambda: assert_confidence_level_in_closed_set(value))


def _require_rejection_reason(value: str) -> None:
    _wrap_closed_set(lambda: assert_rejection_reason_in_closed_set(value))


def _require_price_window_kind(value: str) -> None:
    _wrap_closed_set(lambda: assert_price_window_kind_in_closed_set(value))


def _require_ath_candidate_kind(value: str) -> None:
    _wrap_closed_set(lambda: assert_ath_candidate_kind_in_closed_set(value))


def _require_reconciliation_status(value: str) -> None:
    _wrap_closed_set(lambda: assert_reconciliation_status_in_closed_set(value))


def _require_quote_denomination(value: str) -> None:
    _wrap_closed_set(lambda: assert_quote_denomination_in_closed_set(value))


def _require_optional_non_negative_int(
    *,
    field_name: str,
    value: object,
) -> None:
    _wrap_closed_set(
        lambda: assert_optional_non_negative_int(
            field_name=field_name, value=value
        )
    )


def _require_non_negative_int_or_minus_one_sentinel(
    *,
    field_name: str,
    value: object,
) -> None:
    _wrap_closed_set(
        lambda: assert_non_negative_int_or_minus_one_sentinel(
            field_name=field_name, value=value
        )
    )


# ---------------------------------------------------------------------------
# Shape helpers
# ---------------------------------------------------------------------------


def _require_non_empty_string(field_name: str, value: object) -> None:
    if not isinstance(value, str) or value == "":
        raise Stage25ContractError(
            f"{field_name} must be a non-empty string"
        )


def _require_string(field_name: str, value: object) -> None:
    if not isinstance(value, str):
        raise Stage25ContractError(f"{field_name} must be a string")


def _require_tuple_of_strings(
    field_name: str,
    value: object,
) -> None:
    if not isinstance(value, tuple):
        raise Stage25ContractError(f"{field_name} must be a tuple")
    for item in value:
        if not isinstance(item, str) or item == "":
            raise Stage25ContractError(
                f"each {field_name} item must be a non-empty string"
            )


def _require_mapping(field_name: str, value: object) -> None:
    if not isinstance(value, Mapping):
        raise Stage25ContractError(f"{field_name} must be a mapping")


def _require_strict_non_negative_int(
    *, field_name: str, value: object
) -> None:
    if isinstance(value, bool):
        raise Stage25ContractError(
            f"{field_name}: bool is not a valid int"
        )
    if not isinstance(value, int):
        raise Stage25ContractError(
            f"{field_name}: expected int, got {type(value).__name__}"
        )
    if value < 0:
        raise Stage25ContractError(f"{field_name}: must be >= 0")


# ---------------------------------------------------------------------------
# Canonical-JSON / hash helpers
# ---------------------------------------------------------------------------


def _canonicalize(value: object) -> object:
    """Reduce ``value`` to a json.dumps-able shape with deterministic ordering.

    Supported value types:

      * ``str`` / ``int`` / ``bool`` / ``None``
      * ``float`` (must be finite)
      * ``list`` / ``tuple``  -- canonicalized element-wise; emitted
                                  as a list.
      * ``Mapping``           -- canonicalized recursively; emitted
                                  as a dict with sorted keys.
                                  Keys must be strings.

    Any other type raises ``Stage25ContractError``. NaN /
    Infinity / -Infinity raise: they cannot round-trip through
    strict JSON.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise Stage25ContractError(
                "non-finite float (NaN / Infinity) cannot be canonicalized"
            )
        return value
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, (list, tuple)):
        return [_canonicalize(item) for item in value]
    if isinstance(value, Mapping):
        out: dict[str, object] = {}
        for key, val in value.items():
            if not isinstance(key, str):
                raise Stage25ContractError(
                    "canonicalize requires string mapping keys; got "
                    f"{type(key).__name__}"
                )
            out[key] = _canonicalize(val)
        return out
    raise Stage25ContractError(
        f"canonicalize cannot encode type {type(value).__name__}"
    )


def canonical_json(value: object) -> str:
    """Return the canonical JSON encoding of ``value``.

    Canonical form: sorted keys, no whitespace separators,
    ASCII-safe (non-ASCII characters are escaped via the JSON
    ``\\uXXXX`` form).
    """
    reduced = _canonicalize(value)
    return json.dumps(
        reduced,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )


def stage25_hash(value: object) -> str:
    """Return the sha256 hex digest of ``canonical_json(value)``."""
    encoded = canonical_json(value).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


# ---------------------------------------------------------------------------
# Observation hash builders
# ---------------------------------------------------------------------------


def _migration_observation_canonical_body(
    obs: Stage25MigrationObservation,
) -> dict[str, object]:
    return {
        "observation_kind": "MIGRATION",
        "token_mint": obs.token_mint,
        "source_family": obs.source_family,
        "source_status": obs.source_status,
        "observed_at_utc": obs.observed_at_utc,
        "slot": obs.slot,
        "block_time": obs.block_time,
        "migration_signature": obs.migration_signature,
        "migration_pool": obs.migration_pool,
        "provider_id": obs.provider_id,
        "reason_codes": list(obs.reason_codes),
        "evidence": _canonicalize(obs.evidence),
        "input_missing_fields": list(obs.input_missing_fields),
    }


def _price_observation_canonical_body(
    obs: Stage25PriceObservation,
) -> dict[str, object]:
    return {
        "observation_kind": "PRICE",
        "token_mint": obs.token_mint,
        "source_family": obs.source_family,
        "source_status": obs.source_status,
        "observed_at_utc": obs.observed_at_utc,
        "slot": obs.slot,
        "block_time": obs.block_time,
        "price": obs.price,
        "quote_denomination": obs.quote_denomination,
        "provider_id": obs.provider_id,
        "reason_codes": list(obs.reason_codes),
        "evidence": _canonicalize(obs.evidence),
        "input_missing_fields": list(obs.input_missing_fields),
    }


def compute_observation_hash(observation: object) -> str:
    """Return the deterministic observation hash for an observation record.

    Dispatches on record type. Raises ``Stage25ContractError`` if
    ``observation`` is neither ``Stage25MigrationObservation`` nor
    ``Stage25PriceObservation``.
    """
    if isinstance(observation, Stage25MigrationObservation):
        return stage25_hash(
            _migration_observation_canonical_body(observation)
        )
    if isinstance(observation, Stage25PriceObservation):
        return stage25_hash(
            _price_observation_canonical_body(observation)
        )
    raise Stage25ContractError(
        "compute_observation_hash: unsupported observation type "
        f"{type(observation).__name__}"
    )


def compute_migration_observation_hash_from_projection(
    *,
    token_mint: str,
    source_family: str,
    source_status: str,
    observed_at_utc: str,
    slot: int,
    block_time: int,
    migration_signature: str,
    migration_pool: str,
    provider_id: str,
    reason_codes: tuple[str, ...],
    evidence: Mapping[str, object],
    input_missing_fields: tuple[str, ...],
) -> str:
    """Compute a migration observation hash from a projection.

    Used by the input reader to derive the hash before instantiating
    the ``Stage25MigrationObservation`` record. The
    ``observation_hash`` field is intentionally NOT included in
    the body (it would be a self-reference).
    """
    body: dict[str, object] = {
        "observation_kind": "MIGRATION",
        "token_mint": token_mint,
        "source_family": source_family,
        "source_status": source_status,
        "observed_at_utc": observed_at_utc,
        "slot": slot,
        "block_time": block_time,
        "migration_signature": migration_signature,
        "migration_pool": migration_pool,
        "provider_id": provider_id,
        "reason_codes": list(reason_codes),
        "evidence": _canonicalize(evidence),
        "input_missing_fields": list(input_missing_fields),
    }
    return stage25_hash(body)


def compute_price_observation_hash_from_projection(
    *,
    token_mint: str,
    source_family: str,
    source_status: str,
    observed_at_utc: str,
    slot: int,
    block_time: int,
    price: Optional[int],
    quote_denomination: str,
    provider_id: str,
    reason_codes: tuple[str, ...],
    evidence: Mapping[str, object],
    input_missing_fields: tuple[str, ...],
) -> str:
    """Compute a price observation hash from a projection.

    Used by the input reader. The ``observation_hash`` field is
    intentionally NOT included in the body.
    """
    body: dict[str, object] = {
        "observation_kind": "PRICE",
        "token_mint": token_mint,
        "source_family": source_family,
        "source_status": source_status,
        "observed_at_utc": observed_at_utc,
        "slot": slot,
        "block_time": block_time,
        "price": price,
        "quote_denomination": quote_denomination,
        "provider_id": provider_id,
        "reason_codes": list(reason_codes),
        "evidence": _canonicalize(evidence),
        "input_missing_fields": list(input_missing_fields),
    }
    return stage25_hash(body)


def compute_price_window_observation_hash_from_projection(
    *,
    token_mint: str,
    source_family: str,
    source_status: str,
    window_kind: str,
    observed_at_utc: str,
    slot: int,
    block_time: int,
    price: Optional[int],
    quote_denomination: str,
    reason_codes: tuple[str, ...],
    evidence: Mapping[str, object],
) -> str:
    """Compute a price-window observation hash from a projection.

    The Stage 25.3 ``build_price_window_observation_record`` helper
    uses this routine to derive the deterministic
    ``observation_hash`` for a ``Stage25PriceWindowObservation``. The
    canonical body carries an ``observation_kind`` discriminator
    distinct from the ``PRICE`` / ``MIGRATION`` bodies so two records
    with the same field values but different observation_kind never
    collide on a single hash.
    """
    body: dict[str, object] = {
        "observation_kind": "PRICE_WINDOW",
        "token_mint": token_mint,
        "source_family": source_family,
        "source_status": source_status,
        "window_kind": window_kind,
        "observed_at_utc": observed_at_utc,
        "slot": slot,
        "block_time": block_time,
        "price": price,
        "quote_denomination": quote_denomination,
        "reason_codes": list(reason_codes),
        "evidence": _canonicalize(evidence),
    }
    return stage25_hash(body)


# ---------------------------------------------------------------------------
# Measurement / candidate / reconciliation hash builders
# ---------------------------------------------------------------------------


def compute_measurement_hash(
    *,
    measurement_family: str,
    measurement_status: str,
    confidence_level: str,
    token_mint: str,
    schema_version: str,
    threshold_version: str,
    measurer_name: str,
    measurer_version: str,
    extra: Mapping[str, object],
) -> str:
    """Return the deterministic ``measurement_hash`` for a measurement record.

    ``extra`` carries the measurement-specific body fields (e.g.
    ``consolidated_slot`` / ``consolidated_peak_price`` /
    ``contributing_source_count``). The measurement hash binds the
    shared measurement metadata plus the measurement-specific body
    so two different measurement families producing the same body
    never collide on a single hash.
    """
    body: dict[str, object] = {
        "measurement_family": measurement_family,
        "measurement_status": measurement_status,
        "confidence_level": confidence_level,
        "token_mint": token_mint,
        "schema_version": schema_version,
        "threshold_version": threshold_version,
        "measurer_name": measurer_name,
        "measurer_version": measurer_version,
        "extra": _canonicalize(extra),
    }
    return stage25_hash(body)


def compute_candidate_hash(
    *,
    token_mint: str,
    source_family: str,
    candidate_kind: str,
    peak_observed_at_utc: str,
    peak_slot: int,
    peak_block_time: int,
    peak_price: Optional[int],
    quote_denomination: str,
    reason_codes: tuple[str, ...],
    evidence: Mapping[str, object],
    input_missing_fields: tuple[str, ...],
) -> str:
    """Return the deterministic ``candidate_hash`` for an ATH candidate."""
    body: dict[str, object] = {
        "token_mint": token_mint,
        "source_family": source_family,
        "candidate_kind": candidate_kind,
        "peak_observed_at_utc": peak_observed_at_utc,
        "peak_slot": peak_slot,
        "peak_block_time": peak_block_time,
        "peak_price": peak_price,
        "quote_denomination": quote_denomination,
        "reason_codes": list(reason_codes),
        "evidence": _canonicalize(evidence),
        "input_missing_fields": list(input_missing_fields),
    }
    return stage25_hash(body)


def compute_reconciliation_hash(
    *,
    measurement_family: str,
    reconciliation_status: str,
    token_mint: str,
    source_families: tuple[str, ...],
    contributing_source_count: int,
    disagreeing_source_count: int,
    reason_codes: tuple[str, ...],
    evidence: Mapping[str, object],
) -> str:
    """Return the deterministic ``reconciliation_hash`` for a reconciliation."""
    body: dict[str, object] = {
        "measurement_family": measurement_family,
        "reconciliation_status": reconciliation_status,
        "token_mint": token_mint,
        "source_families": list(source_families),
        "contributing_source_count": contributing_source_count,
        "disagreeing_source_count": disagreeing_source_count,
        "reason_codes": list(reason_codes),
        "evidence": _canonicalize(evidence),
    }
    return stage25_hash(body)


# ---------------------------------------------------------------------------
# Validating builders
# ---------------------------------------------------------------------------


def _require_price_zero_has_explicit_reason(
    *,
    price: Optional[int],
    reason_codes: tuple[str, ...],
) -> None:
    """Enforce the Stage 25 ``PRICE_OBSERVED_ZERO`` invariant.

    A price field of ``0`` requires the explicit
    ``PRICE_OBSERVED_ZERO`` reason code; ``None`` and any
    positive int are unaffected.
    """
    if price == 0 and REASON_CODE_PRICE_OBSERVED_ZERO not in reason_codes:
        raise Stage25ContractError(
            "price=0 requires the explicit PRICE_OBSERVED_ZERO reason code"
        )


def _require_present_status_has_observed_price(
    *,
    source_status: str,
    price: Optional[int],
) -> None:
    """Enforce the Stage 25 PRESENT-requires-observed-price invariant.

    When ``source_status`` is ``PRESENT`` the source has claimed the
    price was actually observed; ``price`` MUST therefore be a
    non-negative int (``0`` is permitted only with the explicit
    ``PRICE_OBSERVED_ZERO`` reason code, enforced separately).
    ``None`` is reserved for non-PRESENT statuses (``ABSENT``,
    ``PARTIAL``, ``AMBIGUOUS``, ``UNSUPPORTED``, ``MALFORMED``,
    ``DECODE_FAILED``).
    """
    if source_status == SOURCE_STATUS_PRESENT and price is None:
        raise Stage25ContractError(
            "price must be a non-negative int (not None) when "
            "source_status is PRESENT"
        )


def build_migration_observation(
    *,
    token_mint: str,
    source_family: str,
    source_status: str,
    observed_at_utc: str,
    slot: int,
    block_time: int,
    migration_signature: str,
    migration_pool: str,
    provider_id: str,
    reason_codes: tuple[str, ...],
    evidence: Mapping[str, object],
    input_missing_fields: tuple[str, ...],
) -> Stage25MigrationObservation:
    """Build a ``Stage25MigrationObservation`` with closed-set validation."""
    _require_non_empty_string("token_mint", token_mint)
    _require_source_family(source_family)
    _require_source_status(source_status)
    _require_string("observed_at_utc", observed_at_utc)
    _require_non_negative_int_or_minus_one_sentinel(
        field_name="slot", value=slot
    )
    _require_non_negative_int_or_minus_one_sentinel(
        field_name="block_time", value=block_time
    )
    _require_string("migration_signature", migration_signature)
    _require_string("migration_pool", migration_pool)
    _require_non_empty_string("provider_id", provider_id)
    _require_tuple_of_strings("reason_codes", reason_codes)
    _require_mapping("evidence", evidence)
    if not isinstance(input_missing_fields, tuple):
        raise Stage25ContractError(
            "input_missing_fields must be a tuple"
        )
    _require_tuple_of_strings("input_missing_fields", input_missing_fields)
    observation_hash = compute_migration_observation_hash_from_projection(
        token_mint=token_mint,
        source_family=source_family,
        source_status=source_status,
        observed_at_utc=observed_at_utc,
        slot=slot,
        block_time=block_time,
        migration_signature=migration_signature,
        migration_pool=migration_pool,
        provider_id=provider_id,
        reason_codes=reason_codes,
        evidence=evidence,
        input_missing_fields=input_missing_fields,
    )
    return Stage25MigrationObservation(
        token_mint=token_mint,
        source_family=source_family,
        source_status=source_status,
        observed_at_utc=observed_at_utc,
        slot=slot,
        block_time=block_time,
        migration_signature=migration_signature,
        migration_pool=migration_pool,
        provider_id=provider_id,
        reason_codes=reason_codes,
        evidence=evidence,
        input_missing_fields=input_missing_fields,
        observation_hash=observation_hash,
    )


def build_price_observation(
    *,
    token_mint: str,
    source_family: str,
    source_status: str,
    observed_at_utc: str,
    slot: int,
    block_time: int,
    price: Optional[int],
    quote_denomination: str,
    provider_id: str,
    reason_codes: tuple[str, ...],
    evidence: Mapping[str, object],
    input_missing_fields: tuple[str, ...],
) -> Stage25PriceObservation:
    """Build a ``Stage25PriceObservation`` with closed-set validation."""
    _require_non_empty_string("token_mint", token_mint)
    _require_source_family(source_family)
    _require_source_status(source_status)
    _require_string("observed_at_utc", observed_at_utc)
    _require_non_negative_int_or_minus_one_sentinel(
        field_name="slot", value=slot
    )
    _require_non_negative_int_or_minus_one_sentinel(
        field_name="block_time", value=block_time
    )
    _require_optional_non_negative_int(field_name="price", value=price)
    _require_quote_denomination(quote_denomination)
    _require_non_empty_string("provider_id", provider_id)
    _require_tuple_of_strings("reason_codes", reason_codes)
    _require_mapping("evidence", evidence)
    if not isinstance(input_missing_fields, tuple):
        raise Stage25ContractError(
            "input_missing_fields must be a tuple"
        )
    _require_tuple_of_strings("input_missing_fields", input_missing_fields)
    _require_present_status_has_observed_price(
        source_status=source_status, price=price
    )
    _require_price_zero_has_explicit_reason(
        price=price, reason_codes=reason_codes
    )
    observation_hash = compute_price_observation_hash_from_projection(
        token_mint=token_mint,
        source_family=source_family,
        source_status=source_status,
        observed_at_utc=observed_at_utc,
        slot=slot,
        block_time=block_time,
        price=price,
        quote_denomination=quote_denomination,
        provider_id=provider_id,
        reason_codes=reason_codes,
        evidence=evidence,
        input_missing_fields=input_missing_fields,
    )
    return Stage25PriceObservation(
        token_mint=token_mint,
        source_family=source_family,
        source_status=source_status,
        observed_at_utc=observed_at_utc,
        slot=slot,
        block_time=block_time,
        price=price,
        quote_denomination=quote_denomination,
        provider_id=provider_id,
        reason_codes=reason_codes,
        evidence=evidence,
        input_missing_fields=input_missing_fields,
        observation_hash=observation_hash,
    )


def build_price_window_observation_record(
    *,
    token_mint: str,
    source_family: str,
    source_status: str,
    window_kind: str,
    observed_at_utc: str,
    slot: int,
    block_time: int,
    price: Optional[int],
    quote_denomination: str,
    reason_codes: tuple[str, ...],
    evidence: Mapping[str, object],
) -> Stage25PriceWindowObservation:
    """Construct a ``Stage25PriceWindowObservation`` with closed-set validation.

    Stage 25.3 surface: this helper is the validated single point of
    construction for price-window observation records. Closed-set
    tokens (``source_family`` / ``source_status`` / ``window_kind`` /
    ``quote_denomination``) are validated against their Stage 25
    closed sets. Slot / block_time fields use the ``-1`` sentinel
    for "absent"; the validator accepts the sentinel so an
    observation with an absent slot / block_time still produces a
    deterministic-hash window record.

    Honesty invariants enforced here:

      * ``price`` must be ``None`` or a non-negative ``int`` (bool
        rejected, negative rejected, NaN / Infinity rejected upstream
        by canonicalization).
      * ``price = 0`` requires the explicit ``PRICE_OBSERVED_ZERO``
        reason code on the ``reason_codes`` tuple.
      * ``price = None`` is reserved for non-PRESENT
        ``source_status`` values; ``PRESENT`` requires a
        non-None ``price``.

    The observation hash binds the discriminator
    ``observation_kind="PRICE_WINDOW"`` plus every body field so two
    distinct window observations never collide on one hash.
    """
    _require_non_empty_string("token_mint", token_mint)
    _require_source_family(source_family)
    _require_source_status(source_status)
    _require_price_window_kind(window_kind)
    _require_string("observed_at_utc", observed_at_utc)
    _require_non_negative_int_or_minus_one_sentinel(
        field_name="slot", value=slot
    )
    _require_non_negative_int_or_minus_one_sentinel(
        field_name="block_time", value=block_time
    )
    _require_optional_non_negative_int(field_name="price", value=price)
    _require_quote_denomination(quote_denomination)
    _require_tuple_of_strings("reason_codes", reason_codes)
    _require_mapping("evidence", evidence)
    _require_present_status_has_observed_price(
        source_status=source_status, price=price
    )
    _require_price_zero_has_explicit_reason(
        price=price, reason_codes=reason_codes
    )
    observation_hash = (
        compute_price_window_observation_hash_from_projection(
            token_mint=token_mint,
            source_family=source_family,
            source_status=source_status,
            window_kind=window_kind,
            observed_at_utc=observed_at_utc,
            slot=slot,
            block_time=block_time,
            price=price,
            quote_denomination=quote_denomination,
            reason_codes=reason_codes,
            evidence=evidence,
        )
    )
    return Stage25PriceWindowObservation(
        token_mint=token_mint,
        source_family=source_family,
        source_status=source_status,
        window_kind=window_kind,
        observed_at_utc=observed_at_utc,
        slot=slot,
        block_time=block_time,
        price=price,
        quote_denomination=quote_denomination,
        reason_codes=reason_codes,
        evidence=evidence,
        observation_hash=observation_hash,
    )


def build_measurement_input(
    *,
    token_mint: str,
    schema_version: str,
    migration_observations: tuple[Stage25MigrationObservation, ...],
    price_observations: tuple[Stage25PriceObservation, ...],
) -> Stage25MeasurementInput:
    """Build a ``Stage25MeasurementInput`` with shape validation."""
    _require_non_empty_string("token_mint", token_mint)
    _require_non_empty_string("schema_version", schema_version)
    if not isinstance(migration_observations, tuple):
        raise Stage25ContractError(
            "migration_observations must be a tuple"
        )
    for entry in migration_observations:
        if not isinstance(entry, Stage25MigrationObservation):
            raise Stage25ContractError(
                "migration_observations must contain only "
                "Stage25MigrationObservation records"
            )
    if not isinstance(price_observations, tuple):
        raise Stage25ContractError(
            "price_observations must be a tuple"
        )
    for entry in price_observations:
        if not isinstance(entry, Stage25PriceObservation):
            raise Stage25ContractError(
                "price_observations must contain only "
                "Stage25PriceObservation records"
            )
    return Stage25MeasurementInput(
        token_mint=token_mint,
        schema_version=schema_version,
        migration_observations=migration_observations,
        price_observations=price_observations,
    )


def build_measurement_rejection(
    *,
    rejection_reason: str,
    token_mint: str,
    source_family: str,
    detail: str,
    reason_codes: tuple[str, ...],
) -> Stage25MeasurementRejection:
    """Build a ``Stage25MeasurementRejection`` with closed-set validation."""
    _require_rejection_reason(rejection_reason)
    _require_string("token_mint", token_mint)
    if source_family != "":
        _require_source_family(source_family)
    _require_string("detail", detail)
    _require_tuple_of_strings("reason_codes", reason_codes)
    return Stage25MeasurementRejection(
        rejection_reason=rejection_reason,
        token_mint=token_mint,
        source_family=source_family,
        detail=detail,
        reason_codes=reason_codes,
    )


def build_ath_candidate_record(
    *,
    token_mint: str,
    source_family: str,
    candidate_kind: str,
    peak_observed_at_utc: str,
    peak_slot: int,
    peak_block_time: int,
    peak_price: Optional[int],
    quote_denomination: str,
    reason_codes: tuple[str, ...],
    evidence: Mapping[str, object],
    input_missing_fields: tuple[str, ...],
) -> Stage25ATHCandidate:
    """Construct a ``Stage25ATHCandidate`` record with closed-set validation.

    Stage 25.1 contract surface: this helper is a pure record
    validator. It does NOT implement ATH candidate-building from
    observations / windows -- callers supply already-resolved
    peak fields and this function only validates the shape +
    closed-set tokens and computes the canonical record hash.
    """
    _require_non_empty_string("token_mint", token_mint)
    _require_source_family(source_family)
    _require_ath_candidate_kind(candidate_kind)
    _require_string("peak_observed_at_utc", peak_observed_at_utc)
    _require_non_negative_int_or_minus_one_sentinel(
        field_name="peak_slot", value=peak_slot
    )
    _require_non_negative_int_or_minus_one_sentinel(
        field_name="peak_block_time", value=peak_block_time
    )
    _require_optional_non_negative_int(
        field_name="peak_price", value=peak_price
    )
    _require_quote_denomination(quote_denomination)
    _require_tuple_of_strings("reason_codes", reason_codes)
    _require_mapping("evidence", evidence)
    if not isinstance(input_missing_fields, tuple):
        raise Stage25ContractError(
            "input_missing_fields must be a tuple"
        )
    _require_tuple_of_strings("input_missing_fields", input_missing_fields)
    _require_price_zero_has_explicit_reason(
        price=peak_price, reason_codes=reason_codes
    )
    candidate_hash = compute_candidate_hash(
        token_mint=token_mint,
        source_family=source_family,
        candidate_kind=candidate_kind,
        peak_observed_at_utc=peak_observed_at_utc,
        peak_slot=peak_slot,
        peak_block_time=peak_block_time,
        peak_price=peak_price,
        quote_denomination=quote_denomination,
        reason_codes=reason_codes,
        evidence=evidence,
        input_missing_fields=input_missing_fields,
    )
    return Stage25ATHCandidate(
        token_mint=token_mint,
        source_family=source_family,
        candidate_kind=candidate_kind,
        peak_observed_at_utc=peak_observed_at_utc,
        peak_slot=peak_slot,
        peak_block_time=peak_block_time,
        peak_price=peak_price,
        quote_denomination=quote_denomination,
        reason_codes=reason_codes,
        evidence=evidence,
        input_missing_fields=input_missing_fields,
        candidate_hash=candidate_hash,
    )


def build_source_reconciliation_record(
    *,
    measurement_family: str,
    reconciliation_status: str,
    token_mint: str,
    source_families: tuple[str, ...],
    contributing_source_count: int,
    disagreeing_source_count: int,
    reason_codes: tuple[str, ...],
    evidence: Mapping[str, object],
) -> Stage25SourceReconciliation:
    """Construct a ``Stage25SourceReconciliation`` record with closed-set validation.

    Stage 25.1 contract surface: this helper is a pure record
    validator. It does NOT compare source observations, compute
    agreement, or reconcile disagreement -- callers supply
    already-resolved status / counts and this function only
    validates the shape + closed-set tokens and computes the
    canonical record hash.
    """
    _require_measurement_family(measurement_family)
    _require_reconciliation_status(reconciliation_status)
    _require_non_empty_string("token_mint", token_mint)
    if not isinstance(source_families, tuple):
        raise Stage25ContractError(
            "source_families must be a tuple"
        )
    for entry in source_families:
        if not isinstance(entry, str) or entry == "":
            raise Stage25ContractError(
                "each source_families item must be a non-empty string"
            )
        _require_source_family(entry)
    _require_strict_non_negative_int(
        field_name="contributing_source_count",
        value=contributing_source_count,
    )
    _require_strict_non_negative_int(
        field_name="disagreeing_source_count",
        value=disagreeing_source_count,
    )
    _require_tuple_of_strings("reason_codes", reason_codes)
    _require_mapping("evidence", evidence)
    reconciliation_hash = compute_reconciliation_hash(
        measurement_family=measurement_family,
        reconciliation_status=reconciliation_status,
        token_mint=token_mint,
        source_families=source_families,
        contributing_source_count=contributing_source_count,
        disagreeing_source_count=disagreeing_source_count,
        reason_codes=reason_codes,
        evidence=evidence,
    )
    return Stage25SourceReconciliation(
        measurement_family=measurement_family,
        reconciliation_status=reconciliation_status,
        token_mint=token_mint,
        source_families=source_families,
        contributing_source_count=contributing_source_count,
        disagreeing_source_count=disagreeing_source_count,
        reason_codes=reason_codes,
        evidence=evidence,
        reconciliation_hash=reconciliation_hash,
    )


def _require_selected_source_family_or_empty(value: object) -> None:
    """Validate ``selected_source_family``.

    Accepts either the empty string (reserved for unmeasured records)
    or a member of ``SOURCE_FAMILIES``. Any other value raises
    ``Stage25ContractError``.
    """
    if not isinstance(value, str):
        raise Stage25ContractError(
            "selected_source_family must be a string"
        )
    if value == "":
        return
    _require_source_family(value)


def build_migration_measurement_record(
    *,
    measurement_status: str,
    confidence_level: str,
    reconciliation_status: str,
    token_mint: str,
    schema_version: str,
    threshold_version: str,
    measurer_name: str,
    measurer_version: str,
    consolidated_slot: int,
    consolidated_block_time: int,
    reconciled_signature: str,
    selected_source_family: str,
    contributing_source_count: int,
    reason_codes: tuple[str, ...],
    numeric_features: Mapping[str, object],
    evidence: Mapping[str, object],
    input_missing_fields: tuple[str, ...],
) -> Stage25MigrationMeasurement:
    """Construct a ``Stage25MigrationMeasurement`` with closed-set validation.

    Stage 25.2 surface: this helper is the validated single point of
    construction for migration measurement records. ``measurement_family``
    is locked to ``MEASUREMENT_FAMILY_MIGRATION`` -- callers do NOT supply
    it. Closed-set tokens (``measurement_status`` / ``confidence_level``
    / ``reconciliation_status``) are validated against
    ``MEASUREMENT_STATUSES`` / ``CONFIDENCE_LEVELS`` /
    ``RECONCILIATION_STATUSES``. ``selected_source_family`` must be the
    empty string (unmeasured) or a member of ``SOURCE_FAMILIES``.

    Slot / block-time fields use the ``-1`` sentinel for "absent"; this
    helper validates them with
    ``_require_non_negative_int_or_minus_one_sentinel`` so the canonical-
    JSON hash contract stays deterministic for unmeasured records.

    Status-conditional invariants enforced here:

      * ``measurement_status == MEASURED`` requires a non-empty
        ``reconciled_signature`` and a non-empty
        ``selected_source_family`` that is a member of
        ``SOURCE_FAMILIES``.
      * Any other ``measurement_status`` permits empty
        ``reconciled_signature`` / ``selected_source_family``.

    The measurement hash binds the measurement family / status /
    confidence level / reconciliation status / token mint / schema
    version / threshold version / measurer name / measurer version
    plus the measurement body (consolidated slot / block time,
    reconciled signature, selected source family, contributing source
    count, reason codes, numeric features, evidence, input missing
    fields) so two distinct measurement bodies never collide on one
    hash.
    """
    _require_measurement_status(measurement_status)
    _require_confidence_level(confidence_level)
    _require_reconciliation_status(reconciliation_status)
    _require_non_empty_string("token_mint", token_mint)
    _require_non_empty_string("schema_version", schema_version)
    _require_non_empty_string("threshold_version", threshold_version)
    _require_non_empty_string("measurer_name", measurer_name)
    _require_non_empty_string("measurer_version", measurer_version)
    _require_non_negative_int_or_minus_one_sentinel(
        field_name="consolidated_slot", value=consolidated_slot
    )
    _require_non_negative_int_or_minus_one_sentinel(
        field_name="consolidated_block_time",
        value=consolidated_block_time,
    )
    _require_string("reconciled_signature", reconciled_signature)
    _require_selected_source_family_or_empty(selected_source_family)
    _require_strict_non_negative_int(
        field_name="contributing_source_count",
        value=contributing_source_count,
    )
    _require_tuple_of_strings("reason_codes", reason_codes)
    _require_mapping("numeric_features", numeric_features)
    _require_mapping("evidence", evidence)
    if not isinstance(input_missing_fields, tuple):
        raise Stage25ContractError(
            "input_missing_fields must be a tuple"
        )
    _require_tuple_of_strings(
        "input_missing_fields", input_missing_fields
    )

    if measurement_status == "MEASURED":
        if reconciled_signature == "":
            raise Stage25ContractError(
                "MEASURED migration measurement requires a non-empty "
                "reconciled_signature"
            )
        if selected_source_family == "":
            raise Stage25ContractError(
                "MEASURED migration measurement requires a non-empty "
                "selected_source_family from SOURCE_FAMILIES"
            )

    measurement_hash = compute_measurement_hash(
        measurement_family=MEASUREMENT_FAMILY_MIGRATION,
        measurement_status=measurement_status,
        confidence_level=confidence_level,
        token_mint=token_mint,
        schema_version=schema_version,
        threshold_version=threshold_version,
        measurer_name=measurer_name,
        measurer_version=measurer_version,
        extra={
            "reconciliation_status": reconciliation_status,
            "consolidated_slot": consolidated_slot,
            "consolidated_block_time": consolidated_block_time,
            "reconciled_signature": reconciled_signature,
            "selected_source_family": selected_source_family,
            "contributing_source_count": contributing_source_count,
            "reason_codes": list(reason_codes),
            "numeric_features": numeric_features,
            "evidence": evidence,
            "input_missing_fields": list(input_missing_fields),
        },
    )
    return Stage25MigrationMeasurement(
        measurement_family=MEASUREMENT_FAMILY_MIGRATION,
        measurement_status=measurement_status,
        confidence_level=confidence_level,
        reconciliation_status=reconciliation_status,
        token_mint=token_mint,
        schema_version=schema_version,
        threshold_version=threshold_version,
        measurer_name=measurer_name,
        measurer_version=measurer_version,
        consolidated_slot=consolidated_slot,
        consolidated_block_time=consolidated_block_time,
        reconciled_signature=reconciled_signature,
        selected_source_family=selected_source_family,
        contributing_source_count=contributing_source_count,
        reason_codes=reason_codes,
        numeric_features=numeric_features,
        evidence=evidence,
        input_missing_fields=input_missing_fields,
        measurement_hash=measurement_hash,
    )


__all__ = [
    "Stage25ATHCandidate",
    "Stage25ATHMeasurement",
    "Stage25MeasurementInput",
    "Stage25MeasurementRejection",
    "Stage25MigrationMeasurement",
    "Stage25MigrationObservation",
    "Stage25PriceObservation",
    "Stage25PriceWindowObservation",
    "Stage25RunnerResult",
    "Stage25SourceReconciliation",
    "Stage25UnifiedMeasurement",
    "build_ath_candidate_record",
    "build_measurement_input",
    "build_measurement_rejection",
    "build_migration_measurement_record",
    "build_migration_observation",
    "build_price_observation",
    "build_price_window_observation_record",
    "build_source_reconciliation_record",
    "canonical_json",
    "compute_candidate_hash",
    "compute_measurement_hash",
    "compute_migration_observation_hash_from_projection",
    "compute_observation_hash",
    "compute_price_observation_hash_from_projection",
    "compute_price_window_observation_hash_from_projection",
    "compute_reconciliation_hash",
    "stage25_hash",
]

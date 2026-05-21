"""Stage 25.2 migration observation helpers.

Pure helpers operating on tuples of ``Stage25MigrationObservation``
records produced by the Stage 25.1 input reader. The helpers are
deterministic and side-effect-free: they consume immutable
``NamedTuple`` records, return new immutable records / containers,
and never mutate caller-supplied inputs.

Functions:

  * ``normalize_migration_observations``    -- canonicalize the order
                                               of an observation tuple
                                               so two equivalent input
                                               tuples produce
                                               byte-identical outputs.
  * ``group_migration_observations_by_token``
                                            -- group observations by
                                               ``token_mint`` with
                                               deterministic intra-
                                               group order.
  * ``dedupe_migration_observations``       -- collapse exact-duplicate
                                               observations sharing the
                                               same dedupe key.
  * ``classify_migration_observation``      -- annotate an observation
                                               with diagnostic reason
                                               codes describing the
                                               classification (missing
                                               block_time / slot /
                                               signature, unsupported /
                                               ambiguous source status).

Design notes:

  * The helpers are pure functions. They make no network calls, read
    no environment variables, open no sockets, write to no disk
    location, and import no Stage 21 / Stage 22 / Stage 23 / Stage 24
    production code.
  * The dedupe key is the deterministic tuple
    ``(token_mint, source_family, migration_signature, slot,
    block_time)``. Two observations sharing that key are collapsed to
    one; conflicting same-source observations whose signature, slot,
    or block_time differ remain as distinct rows so the measurer can
    flag the same-source conflict explicitly.
  * ``classify_migration_observation`` rebuilds the observation through
    ``build_migration_observation`` so the derived
    ``observation_hash`` reflects the annotated ``reason_codes``
    tuple. Callers that need to associate a classified observation
    with the original record can compare the original hash against
    the classified hash to detect the annotation.

This module imports only stdlib (``typing``) plus the Stage 25
constants / errors / models. It does NOT import Stage 21 /
Stage 22 / Stage 23 / Stage 24 production modules, does NOT
import any network / RPC / messaging / DB / scheduler /
secrets-management library, does NOT read the process
environment, does NOT define a CLI surface, and contains no
top-level I/O.
"""

from __future__ import annotations

from typing import Mapping

from PHX2.stage25.constants import (
    REASON_CODE_MIGRATION_AMBIGUOUS_SOURCE_STATUS,
    REASON_CODE_MIGRATION_BLOCK_TIME_MISSING,
    REASON_CODE_MIGRATION_SIGNATURE_MISSING,
    REASON_CODE_MIGRATION_SLOT_MISSING,
    REASON_CODE_MIGRATION_UNSUPPORTED_SOURCE_STATUS,
    SOURCE_STATUS_ABSENT,
    SOURCE_STATUS_AMBIGUOUS,
    SOURCE_STATUS_DECODE_FAILED,
    SOURCE_STATUS_MALFORMED,
    SOURCE_STATUS_PRESENT,
    SOURCE_STATUS_UNSUPPORTED,
)
from PHX2.stage25.errors import Stage25ContractError
from PHX2.stage25.models import (
    Stage25MigrationObservation,
    build_migration_observation,
)


# ---------------------------------------------------------------------------
# Dedupe / sort keys
# ---------------------------------------------------------------------------


_NonContributingStatuses: frozenset[str] = frozenset(
    {
        SOURCE_STATUS_ABSENT,
        SOURCE_STATUS_MALFORMED,
        SOURCE_STATUS_DECODE_FAILED,
        SOURCE_STATUS_UNSUPPORTED,
    }
)


def _dedupe_key(
    observation: Stage25MigrationObservation,
) -> tuple[str, str, str, int, int]:
    """Return the deterministic dedupe tuple for ``observation``.

    Two observations sharing the same tuple are exact duplicates and
    collapse to one record. Observations differing on any axis remain
    distinct so the measurer can record same-source conflict honestly.
    """
    return (
        observation.token_mint,
        observation.source_family,
        observation.migration_signature,
        observation.slot,
        observation.block_time,
    )


def _sort_key(
    observation: Stage25MigrationObservation,
) -> tuple[str, str, int, int, str, str]:
    """Return the deterministic sort tuple for ``observation``.

    Ordering: token, source_family, block_time, slot, signature, hash.
    The trailing ``observation_hash`` is the final disambiguator -- two
    observations identical on every other axis still produce a stable
    deterministic order via their derived canonical-JSON hash.
    """
    return (
        observation.token_mint,
        observation.source_family,
        observation.block_time,
        observation.slot,
        observation.migration_signature,
        observation.observation_hash,
    )


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def normalize_migration_observations(
    observations: tuple[Stage25MigrationObservation, ...],
) -> tuple[Stage25MigrationObservation, ...]:
    """Return ``observations`` in deterministic canonical order.

    The original tuple is not mutated. The returned tuple has the
    same length as the input.
    """
    if not isinstance(observations, tuple):
        raise Stage25ContractError(
            "normalize_migration_observations: observations must be a tuple"
        )
    return tuple(sorted(observations, key=_sort_key))


def group_migration_observations_by_token(
    observations: tuple[Stage25MigrationObservation, ...],
) -> dict[str, tuple[Stage25MigrationObservation, ...]]:
    """Group ``observations`` by ``token_mint`` with deterministic order.

    Returns a ``dict`` whose keys are token mints sorted lexicographically
    and whose values are tuples of observations in the deterministic
    sort order. The caller-supplied tuple is not mutated.

    An empty input tuple returns an empty dict.
    """
    if not isinstance(observations, tuple):
        raise Stage25ContractError(
            "group_migration_observations_by_token: observations must be "
            "a tuple"
        )
    buckets: dict[str, list[Stage25MigrationObservation]] = {}
    for observation in observations:
        buckets.setdefault(observation.token_mint, []).append(observation)
    grouped: dict[str, tuple[Stage25MigrationObservation, ...]] = {}
    for token in sorted(buckets.keys()):
        grouped[token] = tuple(sorted(buckets[token], key=_sort_key))
    return grouped


def dedupe_migration_observations(
    observations: tuple[Stage25MigrationObservation, ...],
) -> tuple[Stage25MigrationObservation, ...]:
    """Collapse exact-duplicate observations sharing the dedupe key.

    The dedupe key is ``(token_mint, source_family, migration_signature,
    slot, block_time)``. Two observations sharing that key collapse to
    one record (the first one encountered after canonical ordering).
    Conflicting same-source observations whose signature, slot, or
    block_time differ remain as distinct rows.

    The caller-supplied tuple is not mutated. Output ordering is the
    deterministic canonical sort order so two equivalent input tuples
    produce byte-identical outputs.
    """
    if not isinstance(observations, tuple):
        raise Stage25ContractError(
            "dedupe_migration_observations: observations must be a tuple"
        )
    seen: set[tuple[str, str, str, int, int]] = set()
    keepers: list[Stage25MigrationObservation] = []
    for observation in sorted(observations, key=_sort_key):
        key = _dedupe_key(observation)
        if key in seen:
            continue
        seen.add(key)
        keepers.append(observation)
    return tuple(keepers)


def classify_migration_observation(
    observation: Stage25MigrationObservation,
) -> Stage25MigrationObservation:
    """Annotate ``observation`` with diagnostic reason codes.

    Returns a NEW ``Stage25MigrationObservation`` whose ``reason_codes``
    tuple carries diagnostic markers for any of:

      * source_status is one of ``ABSENT`` / ``MALFORMED`` /
        ``DECODE_FAILED`` / ``UNSUPPORTED`` -- annotated with
        ``MIGRATION_UNSUPPORTED_SOURCE_STATUS``.
      * source_status is ``AMBIGUOUS`` -- annotated with
        ``MIGRATION_AMBIGUOUS_SOURCE_STATUS``.
      * ``block_time`` is the absent sentinel (``-1``) -- annotated
        with ``MIGRATION_BLOCK_TIME_MISSING``.
      * ``slot`` is the absent sentinel (``-1``) -- annotated with
        ``MIGRATION_SLOT_MISSING``.
      * ``migration_signature`` is the empty string -- annotated with
        ``MIGRATION_SIGNATURE_MISSING``.

    Codes already present on the input observation are not duplicated.
    When no diagnostic codes apply, the original observation is
    returned unchanged.

    The input observation is never mutated. The returned record is
    rebuilt through ``build_migration_observation`` so its
    ``observation_hash`` reflects the annotated reason_codes tuple.
    """
    extra_codes: list[str] = []
    status = observation.source_status
    if status in _NonContributingStatuses:
        extra_codes.append(REASON_CODE_MIGRATION_UNSUPPORTED_SOURCE_STATUS)
    elif status == SOURCE_STATUS_AMBIGUOUS:
        extra_codes.append(REASON_CODE_MIGRATION_AMBIGUOUS_SOURCE_STATUS)
    if observation.block_time < 0:
        extra_codes.append(REASON_CODE_MIGRATION_BLOCK_TIME_MISSING)
    if observation.slot < 0:
        extra_codes.append(REASON_CODE_MIGRATION_SLOT_MISSING)
    if observation.migration_signature == "":
        extra_codes.append(REASON_CODE_MIGRATION_SIGNATURE_MISSING)

    if not extra_codes:
        return observation

    existing = list(observation.reason_codes)
    seen: set[str] = set(existing)
    for code in extra_codes:
        if code in seen:
            continue
        seen.add(code)
        existing.append(code)

    if tuple(existing) == observation.reason_codes:
        return observation

    return build_migration_observation(
        token_mint=observation.token_mint,
        source_family=observation.source_family,
        source_status=observation.source_status,
        observed_at_utc=observation.observed_at_utc,
        slot=observation.slot,
        block_time=observation.block_time,
        migration_signature=observation.migration_signature,
        migration_pool=observation.migration_pool,
        provider_id=observation.provider_id,
        reason_codes=tuple(existing),
        evidence=observation.evidence,
        input_missing_fields=observation.input_missing_fields,
    )


# ---------------------------------------------------------------------------
# Observation contribution predicates (Stage 25.2 internal)
# ---------------------------------------------------------------------------
#
# These predicates are exposed at module scope so the Stage 25.2
# measurer in ``migration_measurement.py`` and the boundary tests
# can share one definition of "contributing observation."


def observation_is_present_with_full_evidence(
    observation: Stage25MigrationObservation,
) -> bool:
    """Return True iff ``observation`` can contribute to a measurement.

    A contributing observation has:

      * ``source_status == PRESENT``;
      * ``block_time >= 0`` (real Unix-seconds value);
      * ``slot >= 0`` (real slot);
      * a non-empty ``migration_signature``.
    """
    return (
        observation.source_status == SOURCE_STATUS_PRESENT
        and observation.block_time >= 0
        and observation.slot >= 0
        and observation.migration_signature != ""
    )


def observation_status_is_unsupported(
    observation: Stage25MigrationObservation,
) -> bool:
    """Return True iff ``observation`` carries an unsupported / absent /
    malformed / decode-failed source status.
    """
    return observation.source_status in _NonContributingStatuses


def observation_status_is_ambiguous(
    observation: Stage25MigrationObservation,
) -> bool:
    """Return True iff ``observation`` carries the ``AMBIGUOUS`` status."""
    return observation.source_status == SOURCE_STATUS_AMBIGUOUS


def observation_evidence_view(
    observation: Stage25MigrationObservation,
) -> Mapping[str, object]:
    """Return the observation's ``evidence`` mapping verbatim.

    Convenience accessor for tests and the measurer; does not copy.
    """
    return observation.evidence


__all__ = [
    "classify_migration_observation",
    "dedupe_migration_observations",
    "group_migration_observations_by_token",
    "normalize_migration_observations",
    "observation_evidence_view",
    "observation_is_present_with_full_evidence",
    "observation_status_is_ambiguous",
    "observation_status_is_unsupported",
]

"""Stage 25.6 in-memory pure runner.

Composes the Stage 25.1-25.5 pure pipeline into a deterministic
``Stage25RunnerResult``:

  1. normalise + dedupe migration observations and group by token,
  2. reconcile migration measurements per token,
  3. normalise + dedupe price observations,
  4. project price observations onto migration-relative windows,
  5. build per-source ATH candidates,
  6. reconcile candidates into per-token source reconciliations and
     consolidated ATH measurements,
  7. build the canonicalisable summary mapping,
  8. return the bundled ``Stage25RunnerResult``.

The runner is PURE: it consumes immutable Stage 25 records, returns
new immutable records / containers, and never mutates caller-
supplied inputs. The runner writes NO files; the Stage 25.6
artifact writer is the surface that promotes the runner result to
disk.

Public entry point:

  * ``run_stage25_measurement`` -- pure composition of the Stage
                                   25.1-25.5 pipeline. Returns a
                                   ``Stage25RunnerResult``.

Determinism rules (Stage 25.6 invariants):

  * Output is byte-stable for identical inputs and identical
    injected ``created_at_utc``. The summary is canonicalisable
    JSON; the per-tuple outputs are deterministic Stage 25.1-25.5
    sort orders.
  * The runner never reads the wall clock; the caller injects
    ``created_at_utc``.
  * The runner never reads disk, the process environment, or any
    network. It never opens a socket / DB cursor / dispatcher.

This module imports only stdlib (``typing``) plus the Stage 25
constants / errors / models / Stage 25.2-25.5 pure surfaces. It
does NOT import Stage 21 / Stage 22 / Stage 23 / Stage 24
production modules, does NOT import any network / RPC / messaging
/ DB / scheduler / secrets-management library, does NOT read the
process environment, does NOT define a CLI surface, and contains
no top-level I/O.
"""

from __future__ import annotations

from PHX2.stage25.ath_candidate import build_ath_candidates
from PHX2.stage25.constants import (
    DEFAULT_SCHEMA_VERSION,
    DEFAULT_THRESHOLD_VERSION,
    STAGE25_RUNNER_NAME,
    STAGE25_RUNNER_VERSION,
)
from PHX2.stage25.errors import Stage25ContractError
from PHX2.stage25.migration_measurement import measure_migrations
from PHX2.stage25.migration_observation import (
    dedupe_migration_observations,
    normalize_migration_observations,
)
from PHX2.stage25.models import (
    Stage25MigrationObservation,
    Stage25PriceObservation,
    Stage25RunnerResult,
    build_runner_result,
)
from PHX2.stage25.price_observation import (
    dedupe_price_observations,
    normalize_price_observations,
)
from PHX2.stage25.price_window import build_price_window_observations
from PHX2.stage25.source_reconciliation import reconcile_ath_candidates
from PHX2.stage25.summary import build_stage25_summary


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def run_stage25_measurement(
    *,
    migration_observations: tuple[Stage25MigrationObservation, ...],
    price_observations: tuple[Stage25PriceObservation, ...],
    created_at_utc: str,
    threshold_version: str = DEFAULT_THRESHOLD_VERSION,
    schema_version: str = DEFAULT_SCHEMA_VERSION,
) -> Stage25RunnerResult:
    """Run the Stage 25 pure measurement pipeline.

    The runner consumes two caller-supplied tuples (migration
    observations + price observations) and composes the Stage 25.1-
    25.5 pure pipeline into a single deterministic
    ``Stage25RunnerResult``.

    Parameters:

      * ``migration_observations`` -- tuple of
                                      ``Stage25MigrationObservation``.
                                      May be empty.
      * ``price_observations``     -- tuple of ``Stage25PriceObservation``.
                                      May be empty.
      * ``created_at_utc``         -- caller-injected ISO-8601 UTC
                                      string. Required non-empty.
      * ``threshold_version``      -- locked Stage 25 threshold axis.
      * ``schema_version``         -- locked Stage 25 schema axis.

    Returns a ``Stage25RunnerResult`` carrying every Stage 25.1-25.5
    tuple output plus the canonicalisable summary mapping.

    The caller-supplied tuples are NEVER mutated. The runner does
    NOT write any file or perform any I/O beyond the in-memory
    Stage 25 pipeline.
    """
    if not isinstance(migration_observations, tuple):
        raise Stage25ContractError(
            "run_stage25_measurement: migration_observations must be a "
            "tuple"
        )
    for entry in migration_observations:
        if not isinstance(entry, Stage25MigrationObservation):
            raise Stage25ContractError(
                "run_stage25_measurement: migration_observations must "
                "contain only Stage25MigrationObservation records"
            )
    if not isinstance(price_observations, tuple):
        raise Stage25ContractError(
            "run_stage25_measurement: price_observations must be a tuple"
        )
    for entry in price_observations:
        if not isinstance(entry, Stage25PriceObservation):
            raise Stage25ContractError(
                "run_stage25_measurement: price_observations must "
                "contain only Stage25PriceObservation records"
            )
    if not isinstance(created_at_utc, str) or created_at_utc == "":
        raise Stage25ContractError(
            "run_stage25_measurement: created_at_utc must be a "
            "non-empty string"
        )

    # Step 1: normalise + dedupe migration observations.
    migration_normalized = normalize_migration_observations(
        migration_observations
    )
    migration_deduped = dedupe_migration_observations(migration_normalized)

    # Step 2: reconcile migration measurements per token.
    migration_measurements = measure_migrations(
        migration_deduped,
        threshold_version=threshold_version,
        schema_version=schema_version,
    )

    # Step 3: normalise + dedupe price observations.
    price_normalized = normalize_price_observations(price_observations)
    price_deduped = dedupe_price_observations(price_normalized)

    # Step 4: project price observations onto migration-relative
    # windows. The projector emits a synthetic UNKNOWN_WINDOW record
    # for tokens with price observations but no migration record.
    price_window_observations = build_price_window_observations(
        price_deduped,
        migration_measurements,
        threshold_version=threshold_version,
    )

    # Step 5: build per-source ATH candidates from the windowed
    # observations.
    ath_candidates = build_ath_candidates(
        price_window_observations,
        threshold_version=threshold_version,
    )

    # Step 6: reconcile candidates into per-token source
    # reconciliations and consolidated ATH measurements.
    source_reconciliations, ath_measurements = reconcile_ath_candidates(
        ath_candidates,
        threshold_version=threshold_version,
        schema_version=schema_version,
    )

    # Stage 25.6 v0 does not collect runtime rejections from the
    # measurer surfaces (rejections are recorded as ``reason_codes``
    # on the measurement / observation records themselves). The
    # ``rejections`` tuple is reserved for future runtime rejection
    # records.
    rejections: tuple = ()

    # Step 7: build the canonicalisable summary mapping.
    summary = build_stage25_summary(
        migration_observations=migration_deduped,
        migration_measurements=migration_measurements,
        price_window_observations=price_window_observations,
        ath_candidates=ath_candidates,
        source_reconciliations=source_reconciliations,
        ath_measurements=ath_measurements,
        rejections=rejections,
        created_at_utc=created_at_utc,
        schema_version=schema_version,
    )

    # Step 8: assemble the runner result.
    observed_token_set: set[str] = set()
    for observation in migration_deduped:
        observed_token_set.add(observation.token_mint)
    for observation in price_deduped:
        observed_token_set.add(observation.token_mint)
    input_token_count = len(observed_token_set)

    return build_runner_result(
        migration_observations=migration_deduped,
        migration_measurements=migration_measurements,
        price_window_observations=price_window_observations,
        ath_candidates=ath_candidates,
        source_reconciliations=source_reconciliations,
        ath_measurements=ath_measurements,
        rejections=rejections,
        summary=summary,
        created_at_utc=created_at_utc,
        runner_name=STAGE25_RUNNER_NAME,
        runner_version=STAGE25_RUNNER_VERSION,
        threshold_version=threshold_version,
        schema_version=schema_version,
        input_token_count=input_token_count,
        input_rejection_count=len(rejections),
    )


__all__ = [
    "run_stage25_measurement",
]

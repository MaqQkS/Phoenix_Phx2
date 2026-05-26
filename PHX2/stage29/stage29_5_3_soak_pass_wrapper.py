"""Stage 29.5.3 migration-context soak pass-entrypoint wrapper.

The wrapper is a runtime-adjacent bridge that lets an operator
thread the Stage 29.5.2 offline migration context composition
into the Stage 29.4 short-session private soak path without
modifying any Stage 29.3 or Stage 29.4 production source.

It satisfies the Stage 29.4 ``Stage29_4PassEntrypoint`` callable
shape by delegating each pass to an INJECTED inner entrypoint.
The wrapper is DEFERRED-OBSERVATION: ``__call__`` performs ONLY
the inner pass delegation plus a minimal pending-observation
append, then returns the inner ``Stage29_4PassResult`` BY
IDENTITY. The wrapper does NOT call the evidence provider, does
NOT call the ATH context provider, does NOT call
``run_stage29_5_2_offline_integration``, and does NOT write the
side-channel artifact during ``__call__``.

All provider / composition / artifact work happens during an
EXPLICIT post-soak step:
:meth:`Stage29_5_3MigrationContextSoakPassWrapper.flush_pending_observations`.

This invariant guarantees the wrapper does NOT add latency
inside the Stage 29.4 timed pass boundary; the Stage 29.4
orchestrator's wall-clock check fires identically whether the
operator wraps the inner entrypoint or runs it raw. Provider
latency (including slow / failed providers) materializes only
during the operator-driven flush AFTER the Stage 29.4 soak
summary has been returned.

Per-call surface:

  * NEVER modifies the inner ``Stage29_4PassResult``; it returns
    the inner result by identity.
  * NEVER calls the inner entrypoint more than once per wrapper
    call (one wrapper call drives exactly one inner pass).
  * NEVER alters Stage 28 dispatch semantics, the Stage 28.9
    health snapshot, the Stage 28.2 dispatch ledger, or the
    Stage 29.4 soak summary counters; the composition is a side
    observation only.
  * NEVER calls the evidence provider, the ATH context provider,
    or :func:`run_stage29_5_2_offline_integration` from within
    ``__call__``.
  * NEVER writes the side-channel artifact from within
    ``__call__``.
  * NEVER reads the process environment.
  * NEVER opens a WebSocket / gRPC / HTTP / socket / Discord
    transport.
  * NEVER imports Stage 29.3 production (the smoke orchestrator
    is invoked only via the operator-supplied inner entrypoint
    callable).
  * NEVER imports the Stage 29.4 soak orchestrator (the wrapper
    is consumed by it, not the other way around).
  * NEVER imports the Stage 29.5.2 synthetic evidence fixtures
    module (the wrapper is generic over caller-supplied evidence
    providers; the fixtures module is exclusively test / proof
    scoped).
  * NEVER imports a PHX1 module. No legacy phoenix-1 import
    path.

Composition data flow per flush iteration (post-soak):

  pending observation (pass_index, candidate_base_mint,
                       soak_output_dir)
    + operator-supplied migration evidence records
    + operator-supplied Stage 27.4 ATH context (or None)
    + wrapper clock + optional time window + optional
      expected_pool_program_id
       -> Stage29_5CandidateAxes(base_mint=..., pool/quote=None)
       -> run_stage29_5_2_offline_integration(...)
       -> Stage29_5_3WrappedPassObservation
       -> wrapper.observations + optional JSONL side-channel
          artifact

The Stage 29.4 pass entrypoint contract requires returning a
``Stage29_4PassResult`` instance. The wrapper returns the inner
``Stage29_4PassResult`` exactly (Python identity equality), so
``soak_orchestrator.isinstance(pass_result, Stage29_4PassResult)``
holds by construction.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import (
    Callable,
    List,
    Optional,
    Protocol,
    Sequence,
    Tuple,
)

from PHX2.stage27.price_ath_context_models import (
    AthContextRecord,
)
from PHX2.stage29.stage29_4_soak_models import (
    Stage29_4PassResult,
    Stage29_4SoakBounds,
    Stage29_4SoakDedupeKey,
)
from PHX2.stage29.stage29_5_2_offline_integration import (
    Stage29_5_2OfflineIntegrationError,
    Stage29_5_2OfflineIntegrationResult,
    run_stage29_5_2_offline_integration,
)
from PHX2.stage29.stage29_5_3_wrapped_pass_models import (
    OBSERVATION_STATUS_COMPOSED,
    OBSERVATION_STATUS_COMPOSITION_REJECTED,
    OBSERVATION_STATUS_NO_CANDIDATE_AXES,
    OBSERVATION_STATUS_PROVIDER_REJECTED,
    Stage29_5_3MigrationEvidenceProviderError,
    Stage29_5_3PendingPassObservation,
    Stage29_5_3SideChannelArtifactError,
    Stage29_5_3WrappedPassError,
    Stage29_5_3WrappedPassObservation,
    is_stage29_5_3_safe_candidate_base_mint,
)
from PHX2.stage29.stage29_5_3_side_channel_artifact_writer import (
    STAGE29_5_3_SIDE_CHANNEL_ARTIFACT_BASENAME,
    append_stage29_5_3_migration_context_observation,
)
from PHX2.stage29.stage29_5_candidate_to_migration_join import (
    Stage29_5CandidateAxes,
)
from PHX2.stage29.stage29_5_migration_models import (
    Stage29_5MigrationEvidenceRecord,
)


# ---------------------------------------------------------------------------
# Provider Protocols (operator-supplied, INJECTED)
# ---------------------------------------------------------------------------


class Stage29_5_3MigrationEvidenceProvider(Protocol):
    """Operator-supplied migration-evidence provider.

    The flush step calls this Protocol once per pending
    observation whose ``candidate_base_mint`` survived the
    Stage 29.5.3 safe-shape validator. Implementations MUST:

      * Return a sequence of
        :class:`Stage29_5MigrationEvidenceRecord` instances (the
        empty sequence is a valid response for the MISSING
        path).
      * Never open a network connection on the wrapper's thread.
        Live ingestion belongs in a separate operator-owned
        layer that the operator drives outside the wrapper's
        flush; the wrapper itself stays observational and
        synchronous.
      * Never read the process environment; env reads belong on
        the operator-owned readiness boundary.
      * Raise :class:`Stage29_5_3MigrationEvidenceProviderError`
        with a closed-set reason token on any caller-visible
        failure. Other exceptions propagate as
        ``COMPOSITION_REJECTED`` defensively in non-strict
        flush mode.
    """

    def __call__(
        self, *, base_mint: str,
    ) -> Sequence[
        Stage29_5MigrationEvidenceRecord
    ]:  # pragma: no cover - Protocol
        ...


class Stage29_5_3AthContextProvider(Protocol):
    """Operator-supplied Stage 27.4 ATH context provider.

    The flush step calls this Protocol once per pending
    observation whose ``candidate_base_mint`` survived the
    Stage 29.5.3 safe-shape validator. Implementations MUST
    return either a valid :class:`AthContextRecord` (a Stage 27.4
    NamedTuple) or ``None`` when no Stage 27.4 ATH context is
    available for the base mint. Raising
    :class:`Stage29_5_3MigrationEvidenceProviderError` is
    permitted on caller-visible failure.
    """

    def __call__(
        self, *, base_mint: str,
    ) -> Optional[
        AthContextRecord
    ]:  # pragma: no cover - Protocol
        ...


# ---------------------------------------------------------------------------
# Inner pass-entrypoint Protocol (mirrors Stage 29.4 shape; the
# wrapper does NOT import the Stage 29.4 soak orchestrator's
# Protocol — we re-declare a structurally identical shape so the
# wrapper module remains decoupled from the orchestrator).
# ---------------------------------------------------------------------------


class Stage29_5_3InnerPassEntrypoint(Protocol):
    """Inner pass-entrypoint Protocol the wrapper delegates to.

    Mirrors the Stage 29.4 ``Stage29_4PassEntrypoint`` shape
    without importing the Stage 29.4 soak orchestrator. The
    wrapper module is consumed by the orchestrator at runtime;
    re-declaring the shape here keeps the wrapper module
    decoupled from the orchestrator's import surface and
    satisfies the Stage 29.5.3 boundary constraint that forbids
    importing the orchestrator.
    """

    def __call__(
        self,
        *,
        pass_index: int,
        bounds: Stage29_4SoakBounds,
        soak_output_dir: Path,
    ) -> Stage29_4PassResult:  # pragma: no cover - Protocol
        ...


# ---------------------------------------------------------------------------
# Stage 29.5.3 wrapper
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _Stage29_5_3PerPassDerivation:
    """Internal record holding per-flush derivation pieces. Not
    part of the public surface.
    """

    candidate_base_mint: Optional[str]
    candidate_axes: Optional[Stage29_5CandidateAxes]


class Stage29_5_3MigrationContextSoakPassWrapper:
    """Stage 29.5.3 soak pass-entrypoint wrapper.

    Wraps an INJECTED inner ``Stage29_5_3InnerPassEntrypoint``
    (structurally identical to the Stage 29.4
    ``Stage29_4PassEntrypoint``). On each wrapper call:

      1. Delegates one inner pass call (exactly once).
      2. Records a MINIMAL pending observation
         (``pass_index`` / safe-shape ``candidate_base_mint`` /
         ``soak_output_dir``). No provider call. No composition.
         No artifact write. No clock call.
      3. Returns the INNER ``Stage29_4PassResult`` by identity.

    On the operator-driven post-soak flush:
    :meth:`flush_pending_observations`:

      1. Walks every pending observation in pass-arrival order.
      2. Calls the evidence provider, the ATH context provider,
         and :func:`run_stage29_5_2_offline_integration` for each
         pending whose ``candidate_base_mint`` is not ``None``.
      3. Captures the closed-set Stage 29.5.3 observation status
         + Stage 29.5 join / projection echo fields onto a
         :class:`Stage29_5_3WrappedPassObservation`.
      4. Appends the composed observation to
         ``self.observations``.
      5. Optionally appends one JSONL side-channel artifact line
         into the pending's ``soak_output_dir`` (best-effort
         under non-strict flush; raises under strict flush).

    The wrapper records observations in pass-arrival order on
    ``self.observations`` after flush (a public read-only
    property). Tests consume this list to assert order +
    closed-set verdicts.

    The wrapper does NOT modify the inner result, does NOT
    change the Stage 28 dispatch chain, does NOT change the
    Stage 29.4 soak summary counters, and does NOT activate
    Stage 26 / Stage 29 enforcement.
    """

    def __init__(
        self,
        *,
        inner_pass_entrypoint: Stage29_5_3InnerPassEntrypoint,
        evidence_provider: (
            Stage29_5_3MigrationEvidenceProvider
        ),
        ath_context_provider: (
            Stage29_5_3AthContextProvider
        ),
        clock: Callable[[], str],
        time_window_start_utc: Optional[str] = None,
        time_window_end_utc: Optional[str] = None,
        expected_pool_program_id: Optional[str] = None,
        write_side_channel_artifact: bool = True,
    ) -> None:
        if inner_pass_entrypoint is None or not callable(
            inner_pass_entrypoint,
        ):
            raise Stage29_5_3WrappedPassError(
                "INNER_PASS_ENTRYPOINT_NOT_CALLABLE",
            )
        if evidence_provider is None or not callable(
            evidence_provider,
        ):
            raise Stage29_5_3WrappedPassError(
                "EVIDENCE_PROVIDER_NOT_CALLABLE",
            )
        if ath_context_provider is None or not callable(
            ath_context_provider,
        ):
            raise Stage29_5_3WrappedPassError(
                "ATH_CONTEXT_PROVIDER_NOT_CALLABLE",
            )
        if clock is None or not callable(clock):
            raise Stage29_5_3WrappedPassError(
                "CLOCK_NOT_CALLABLE",
            )
        if not isinstance(write_side_channel_artifact, bool):
            raise Stage29_5_3WrappedPassError(
                "WRITE_SIDE_CHANNEL_ARTIFACT_NOT_BOOL",
            )
        self._inner_pass_entrypoint: (
            Stage29_5_3InnerPassEntrypoint
        ) = inner_pass_entrypoint
        self._evidence_provider: (
            Stage29_5_3MigrationEvidenceProvider
        ) = evidence_provider
        self._ath_context_provider: (
            Stage29_5_3AthContextProvider
        ) = ath_context_provider
        self._clock: Callable[[], str] = clock
        self._time_window_start_utc: Optional[str] = (
            time_window_start_utc
        )
        self._time_window_end_utc: Optional[str] = (
            time_window_end_utc
        )
        self._expected_pool_program_id: Optional[str] = (
            expected_pool_program_id
        )
        self._write_side_channel_artifact: bool = (
            write_side_channel_artifact
        )
        self._pending: List[
            Stage29_5_3PendingPassObservation
        ] = []
        self._observations: List[
            Stage29_5_3WrappedPassObservation
        ] = []

    @property
    def pending_observations(
        self,
    ) -> Tuple[Stage29_5_3PendingPassObservation, ...]:
        """Return a tuple snapshot of every pending observation
        recorded so far (i.e. observations that have not yet
        been flushed). In pass-arrival order.
        """
        return tuple(self._pending)

    @property
    def observations(
        self,
    ) -> Tuple[Stage29_5_3WrappedPassObservation, ...]:
        """Return a tuple snapshot of every COMPOSED observation
        materialized so far (i.e. observations produced by past
        :meth:`flush_pending_observations` calls). In pass-arrival
        order.
        """
        return tuple(self._observations)

    @property
    def side_channel_artifact_basename(self) -> str:
        """Return the locked basename the flush writes the JSONL
        side-channel artifact under.
        """
        return STAGE29_5_3_SIDE_CHANNEL_ARTIFACT_BASENAME

    def __call__(
        self,
        *,
        pass_index: int,
        bounds: Stage29_4SoakBounds,
        soak_output_dir: Path,
    ) -> Stage29_4PassResult:
        """Drive one inner pass + append a minimal pending
        observation. Returns the INNER ``Stage29_4PassResult`` by
        identity.

        This method performs ZERO provider work, ZERO composition,
        ZERO artifact write, and ZERO clock call. Provider /
        composition / artifact work is deferred to
        :meth:`flush_pending_observations`. The Stage 29.4 timed
        pass boundary therefore observes the inner pass latency
        only; the wrapper itself contributes only the cost of
        appending one frozen-dataclass record to an in-memory
        list.

        Validates the caller-shape invariants and then delegates
        the inner call exactly once. The pending observation is
        recorded AFTER the inner call returns so the inner pass
        result's dedupe key can drive the safe-shape candidate
        base mint extraction.
        """
        if isinstance(pass_index, bool) or not isinstance(
            pass_index, int,
        ) or pass_index < 1:
            raise Stage29_5_3WrappedPassError(
                "PASS_INDEX_NOT_POSITIVE_INT",
                f"got {pass_index!r}",
            )
        if not isinstance(bounds, Stage29_4SoakBounds):
            raise Stage29_5_3WrappedPassError(
                "BOUNDS_NOT_STAGE_29_4_SOAK_BOUNDS",
            )
        if not isinstance(soak_output_dir, Path):
            raise Stage29_5_3WrappedPassError(
                "SOAK_OUTPUT_DIR_NOT_PATH",
            )

        # Delegate one inner pass call. Exactly one.
        inner_result = self._inner_pass_entrypoint(
            pass_index=pass_index,
            bounds=bounds,
            soak_output_dir=soak_output_dir,
        )

        # Append a MINIMAL pending observation. No provider call,
        # no composition, no artifact write, no clock call. The
        # safe-shape candidate base mint extraction tolerates
        # any inner_result shape by widening to None.
        candidate_base_mint = (
            self._safe_extract_candidate_base_mint(inner_result)
        )
        try:
            pending = Stage29_5_3PendingPassObservation(
                pass_index=pass_index,
                candidate_base_mint=candidate_base_mint,
                soak_output_dir=soak_output_dir,
            )
        except Stage29_5_3WrappedPassError:
            # Defensive: the pending dataclass validator
            # rejected one of the assembled fields. Fall back
            # to a safe-shape pending observation that still
            # pins pass_index / soak_output_dir and drops the
            # candidate base mint to None so the flush will
            # record NO_CANDIDATE_AXES.
            pending = Stage29_5_3PendingPassObservation(
                pass_index=pass_index,
                candidate_base_mint=None,
                soak_output_dir=soak_output_dir,
            )
        self._pending.append(pending)

        return inner_result

    def flush_pending_observations(
        self,
        *,
        strict: bool = False,
    ) -> Tuple[Stage29_5_3WrappedPassObservation, ...]:
        """Materialize a composed observation for every pending
        observation recorded so far.

        Walks every pending observation in pass-arrival order.
        For each one:

          * if the pending ``candidate_base_mint`` is ``None``,
            records ``NO_CANDIDATE_AXES`` (no provider call);
          * else calls the operator-supplied evidence provider,
            ATH context provider, and
            :func:`run_stage29_5_2_offline_integration`;
          * appends the composed observation to
            ``self.observations``;
          * optionally appends one JSONL side-channel artifact
            line into the pending's ``soak_output_dir``.

        Empties the pending queue. Returns a tuple of the
        observations materialized by THIS flush call (later
        flushes return only the observations newly composed by
        that flush; observations from earlier flushes remain in
        ``self.observations``).

        ``strict`` defaults to ``False``. In non-strict mode:

          * Provider failures map to
            ``observation_status=PROVIDER_REJECTED``.
          * Composition failures map to
            ``observation_status=COMPOSITION_REJECTED``.
          * Artifact-write failures (closed-set
            :class:`Stage29_5_3SideChannelArtifactError` or
            ``OSError``) are swallowed; the composed observation
            is still recorded on ``self.observations``.
          * Nothing raises out of this method.

        In strict mode (``strict=True``):

          * Provider failures, composition failures, and
            artifact-write failures all propagate. The pending
            queue is drained up to (but excluding) the failing
            pending — already-flushed observations remain on
            ``self.observations``; the failing pending and any
            later pending stay on ``self._pending`` so the
            operator can retry after fixing the cause.

        Strict retryability invariant: under ``strict=True`` the
        failing pending's observation is NOT appended to
        ``self._observations`` and the failing pending is NOT
        popped from ``self._pending`` until EVERY strict-mode
        side effect for that pending has succeeded. The artifact
        write therefore runs BEFORE the pending pop / observation
        append so a side-channel artifact failure leaves the
        wrapper in a fully retryable state: the failing pending
        stays queued in position zero, no fallback observation
        appears on ``self.observations``, and ``flush_pending_
        observations(strict=True)`` can be re-invoked after the
        operator fixes the underlying cause (e.g. recreates the
        missing soak output directory).
        """
        composed_this_flush: List[
            Stage29_5_3WrappedPassObservation
        ] = []
        while self._pending:
            pending = self._pending[0]
            observation = self._compose_observation_from_pending(
                pending=pending,
                strict=strict,
            )
            if (
                strict and self._write_side_channel_artifact
            ):
                # Strict mode: drive the artifact write BEFORE
                # mutating self._pending / self._observations so
                # a writer failure leaves the failing pending
                # queued for retry without ever recording the
                # failed observation on the wrapper. A composition
                # / provider failure raised out of
                # _compose_observation_from_pending has already
                # short-circuited this branch with state
                # unmodified.
                self._strict_append_artifact(
                    soak_output_dir=pending.soak_output_dir,
                    observation=observation,
                )
            self._pending.pop(0)
            self._observations.append(observation)
            composed_this_flush.append(observation)
            if (
                self._write_side_channel_artifact
                and not strict
            ):
                self._safe_append_artifact(
                    soak_output_dir=pending.soak_output_dir,
                    observation=observation,
                )
        return tuple(composed_this_flush)

    # -----------------------------------------------------------------
    # Internal helpers
    # -----------------------------------------------------------------

    def _safe_extract_candidate_base_mint(
        self, inner_result: object,
    ) -> Optional[str]:
        """Extract a safe-shape candidate base mint string from
        the inner pass result's dedupe key.

        Returns ``None`` when the inner result carries no dedupe
        key, the dedupe key is not a ``Stage29_4SoakDedupeKey``,
        the dedupe key's ``token_mint`` is not a string, or the
        ``token_mint`` fails the Stage 29.5.3 base58 safe-shape
        validator.

        The wrapper never raises out of ``__call__``; a malformed
        dedupe key becomes a ``None`` candidate base mint on the
        pending observation, which the flush translates to
        ``NO_CANDIDATE_AXES`` (with no provider call).
        """
        dedupe_key = getattr(inner_result, "dedupe_key", None)
        if dedupe_key is None:
            return None
        if not isinstance(
            dedupe_key, Stage29_4SoakDedupeKey,
        ):
            return None
        token_mint = dedupe_key.token_mint
        if not isinstance(token_mint, str):
            return None
        if not is_stage29_5_3_safe_candidate_base_mint(
            token_mint,
        ):
            return None
        return token_mint

    def _derive_candidate_axes(
        self,
        *,
        candidate_base_mint: Optional[str],
    ) -> _Stage29_5_3PerPassDerivation:
        """Derive a base-mint-only Stage 29.5 candidate axes
        record from the pending observation's
        ``candidate_base_mint``.

        Returns ``_Stage29_5_3PerPassDerivation`` with
        ``candidate_axes=None`` when the pending carries
        ``candidate_base_mint=None`` OR when the Stage 29.5
        candidate-axes validator rejects the assembled axes.
        """
        if candidate_base_mint is None:
            return _Stage29_5_3PerPassDerivation(
                candidate_base_mint=None,
                candidate_axes=None,
            )
        try:
            axes = Stage29_5CandidateAxes(
                base_mint=candidate_base_mint,
                pool_account=None,
                pool_program_id=None,
                quote_mint=None,
            )
        except ValueError:
            return _Stage29_5_3PerPassDerivation(
                candidate_base_mint=candidate_base_mint,
                candidate_axes=None,
            )
        return _Stage29_5_3PerPassDerivation(
            candidate_base_mint=candidate_base_mint,
            candidate_axes=axes,
        )

    def _safe_observed_at_utc(self) -> str:
        """Call the operator-supplied clock and return its
        result. Falls back to a closed-set sentinel string when
        the clock raises or returns a non-string.

        Called only from the flush path; never from ``__call__``.
        """
        try:
            value = self._clock()
        except Exception:  # noqa: BLE001
            return "STAGE29_5_3_CLOCK_REJECTED"
        if not isinstance(value, str) or not value:
            return "STAGE29_5_3_CLOCK_REJECTED"
        if not value.isprintable() or len(value) > 64:
            return "STAGE29_5_3_CLOCK_REJECTED"
        return value

    def _compose_observation_from_pending(
        self,
        *,
        pending: Stage29_5_3PendingPassObservation,
        strict: bool,
    ) -> Stage29_5_3WrappedPassObservation:
        """Run the Stage 29.5.2 composition (when candidate axes
        are derivable) and build a closed-set Stage 29.5.3
        observation record.

        In non-strict mode: never raises. Provider / composition
        failures map to the closed-set observation status.

        In strict mode: provider failures (raised as
        :class:`Stage29_5_3MigrationEvidenceProviderError` or any
        other exception type from the provider Protocols) and
        composition failures (raised as
        :class:`Stage29_5_2OfflineIntegrationError` /
        ``ValueError`` from the composition layer) propagate.
        """
        observed_at_utc = self._safe_observed_at_utc()
        derivation = self._derive_candidate_axes(
            candidate_base_mint=pending.candidate_base_mint,
        )
        if derivation.candidate_axes is None:
            return self._safe_build_observation(
                pass_index=pending.pass_index,
                observation_status=(
                    OBSERVATION_STATUS_NO_CANDIDATE_AXES
                ),
                candidate_base_mint=(
                    derivation.candidate_base_mint
                ),
                composition_result=None,
                observed_at_utc=observed_at_utc,
            )

        # Evidence provider.
        try:
            evidence_records = self._evidence_provider(
                base_mint=derivation.candidate_base_mint,
            )
        except Stage29_5_3MigrationEvidenceProviderError:
            if strict:
                raise
            return self._safe_build_observation(
                pass_index=pending.pass_index,
                observation_status=(
                    OBSERVATION_STATUS_PROVIDER_REJECTED
                ),
                candidate_base_mint=(
                    derivation.candidate_base_mint
                ),
                composition_result=None,
                observed_at_utc=observed_at_utc,
            )
        except Exception:  # noqa: BLE001
            if strict:
                raise
            return self._safe_build_observation(
                pass_index=pending.pass_index,
                observation_status=(
                    OBSERVATION_STATUS_PROVIDER_REJECTED
                ),
                candidate_base_mint=(
                    derivation.candidate_base_mint
                ),
                composition_result=None,
                observed_at_utc=observed_at_utc,
            )

        # ATH context provider.
        try:
            ath_context = self._ath_context_provider(
                base_mint=derivation.candidate_base_mint,
            )
        except Stage29_5_3MigrationEvidenceProviderError:
            if strict:
                raise
            return self._safe_build_observation(
                pass_index=pending.pass_index,
                observation_status=(
                    OBSERVATION_STATUS_PROVIDER_REJECTED
                ),
                candidate_base_mint=(
                    derivation.candidate_base_mint
                ),
                composition_result=None,
                observed_at_utc=observed_at_utc,
            )
        except Exception:  # noqa: BLE001
            if strict:
                raise
            return self._safe_build_observation(
                pass_index=pending.pass_index,
                observation_status=(
                    OBSERVATION_STATUS_PROVIDER_REJECTED
                ),
                candidate_base_mint=(
                    derivation.candidate_base_mint
                ),
                composition_result=None,
                observed_at_utc=observed_at_utc,
            )

        # Stage 29.5.2 offline composition.
        try:
            composition_result = (
                run_stage29_5_2_offline_integration(
                    candidate_axes=(
                        derivation.candidate_axes
                    ),
                    evidence_records=evidence_records,
                    ath_context=ath_context,
                    clock=self._clock,
                    time_window_start_utc=(
                        self._time_window_start_utc
                    ),
                    time_window_end_utc=(
                        self._time_window_end_utc
                    ),
                    expected_pool_program_id=(
                        self._expected_pool_program_id
                    ),
                )
            )
        except Stage29_5_2OfflineIntegrationError:
            if strict:
                raise
            return self._safe_build_observation(
                pass_index=pending.pass_index,
                observation_status=(
                    OBSERVATION_STATUS_COMPOSITION_REJECTED
                ),
                candidate_base_mint=(
                    derivation.candidate_base_mint
                ),
                composition_result=None,
                observed_at_utc=observed_at_utc,
            )
        except ValueError:
            if strict:
                raise
            return self._safe_build_observation(
                pass_index=pending.pass_index,
                observation_status=(
                    OBSERVATION_STATUS_COMPOSITION_REJECTED
                ),
                candidate_base_mint=(
                    derivation.candidate_base_mint
                ),
                composition_result=None,
                observed_at_utc=observed_at_utc,
            )
        except Exception:  # noqa: BLE001
            if strict:
                raise
            return self._safe_build_observation(
                pass_index=pending.pass_index,
                observation_status=(
                    OBSERVATION_STATUS_COMPOSITION_REJECTED
                ),
                candidate_base_mint=(
                    derivation.candidate_base_mint
                ),
                composition_result=None,
                observed_at_utc=observed_at_utc,
            )

        return self._safe_build_observation(
            pass_index=pending.pass_index,
            observation_status=OBSERVATION_STATUS_COMPOSED,
            candidate_base_mint=(
                derivation.candidate_base_mint
            ),
            composition_result=composition_result,
            observed_at_utc=observed_at_utc,
        )

    def _safe_build_observation(
        self,
        *,
        pass_index: int,
        observation_status: str,
        candidate_base_mint: Optional[str],
        composition_result: Optional[
            Stage29_5_2OfflineIntegrationResult
        ],
        observed_at_utc: str,
    ) -> Stage29_5_3WrappedPassObservation:
        """Build an observation record. Falls back to a
        defensive COMPOSITION_REJECTED observation when the
        dataclass validator rejects the assembled fields.

        Because the dataclass validator is strict (closed-set
        tokens, length / printable / structure invariants), this
        helper guarantees the flush composition never raises a
        validator error out: a validator failure collapses to a
        safe-shape default observation that still pins the locked
        enforcement / redaction tokens.
        """
        join_status_echoed: Optional[str] = None
        measurement_status_echoed: Optional[str] = None
        post_migration_ath_verified_echoed: Optional[bool] = None
        warnings_echoed: Tuple[str, ...] = ()
        if (
            observation_status == OBSERVATION_STATUS_COMPOSED
            and composition_result is not None
        ):
            join_status_echoed = (
                composition_result
                .join_record
                .migration_join_status
            )
            measurement_status_echoed = (
                composition_result
                .private_ping_context
                .measurement_status
            )
            post_migration_ath_verified_echoed = (
                composition_result
                .private_ping_context
                .post_migration_ath_verified
            )
            warnings_echoed = tuple(
                composition_result
                .private_ping_context
                .warnings
            )
        try:
            return Stage29_5_3WrappedPassObservation(
                pass_index=pass_index,
                observation_status=observation_status,
                candidate_base_mint=candidate_base_mint,
                join_status_echoed=join_status_echoed,
                measurement_status_echoed=(
                    measurement_status_echoed
                ),
                post_migration_ath_verified_echoed=(
                    post_migration_ath_verified_echoed
                ),
                warnings_echoed=warnings_echoed,
                observed_at_utc=observed_at_utc,
            )
        except Stage29_5_3WrappedPassError:
            # The dataclass validator rejected the assembled
            # fields; emit a safe-shape fallback observation
            # that still satisfies the validator.
            # ``observed_at_utc`` is replaced with the closed-set
            # sentinel so the printable-non-empty check always
            # succeeds.
            return Stage29_5_3WrappedPassObservation(
                pass_index=pass_index,
                observation_status=(
                    OBSERVATION_STATUS_COMPOSITION_REJECTED
                ),
                candidate_base_mint=None,
                join_status_echoed=None,
                measurement_status_echoed=None,
                post_migration_ath_verified_echoed=None,
                warnings_echoed=(),
                observed_at_utc=(
                    "STAGE29_5_3_OBSERVATION_FALLBACK"
                ),
            )

    def _safe_append_artifact(
        self,
        *,
        soak_output_dir: Path,
        observation: Stage29_5_3WrappedPassObservation,
    ) -> None:
        """Append a JSONL line for ``observation`` to the
        wrapper's side-channel artifact under ``soak_output_dir``.

        Best-effort. The flush swallows every artifact-writer
        error (closed-set or OS-level) so the composed observation
        still appears on ``self.observations``.
        """
        try:
            append_stage29_5_3_migration_context_observation(
                soak_output_dir=soak_output_dir,
                observation=observation,
            )
        except Stage29_5_3SideChannelArtifactError:
            return
        except OSError:
            return
        except Exception:  # noqa: BLE001
            return

    def _strict_append_artifact(
        self,
        *,
        soak_output_dir: Path,
        observation: Stage29_5_3WrappedPassObservation,
    ) -> None:
        """Append a JSONL line for ``observation`` under strict
        flush mode. Artifact-write failures propagate as
        :class:`Stage29_5_3SideChannelArtifactError` or
        ``OSError``.
        """
        append_stage29_5_3_migration_context_observation(
            soak_output_dir=soak_output_dir,
            observation=observation,
        )


__all__ = (
    "Stage29_5_3MigrationEvidenceProvider",
    "Stage29_5_3AthContextProvider",
    "Stage29_5_3InnerPassEntrypoint",
    "Stage29_5_3MigrationContextSoakPassWrapper",
)

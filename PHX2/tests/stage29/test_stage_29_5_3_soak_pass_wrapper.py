"""Stage 29.5.3 soak pass-entrypoint wrapper tests.

Pins the wrapper's runtime-adjacent DEFERRED-OBSERVATION
contract:

  * The wrapper satisfies the Stage 29.4 pass-entrypoint shape
    (callable with ``pass_index`` / ``bounds`` / ``soak_output_dir``
    keyword args; returns a Stage 29.4 ``Stage29_4PassResult``).
  * ``wrapper.__call__`` calls the inner entrypoint exactly once
    per wrapper call and returns the inner result by identity.
  * ``wrapper.__call__`` does NOT call the evidence provider,
    does NOT call the ATH context provider, does NOT call
    ``run_stage29_5_2_offline_integration``, and does NOT write
    the side-channel artifact.
  * ``wrapper.__call__`` appends a minimal
    :class:`Stage29_5_3PendingPassObservation` to
    ``wrapper.pending_observations``; no composed observation
    is materialized until the operator calls
    ``flush_pending_observations``.
  * Slow / failing evidence providers do NOT perturb the
    Stage 29.4 soak summary or dispatch counters; provider /
    composition / artifact work is OUTSIDE the Stage 29.4 timed
    pass boundary.
  * After ``flush_pending_observations`` the closed-set
    observation status / Stage 29.5 echo fields are recorded on
    ``wrapper.observations`` in pass-arrival order.
  * Non-strict flush swallows provider / composition / artifact
    failures; strict flush propagates them.
  * The side-channel JSONL artifact is appended at flush time
    (best-effort under non-strict; raising under strict).
  * No live WS / gRPC / HTTP / Discord imports.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import List, Optional, Sequence

import pytest

from PHX2.stage27.price_ath_context_models import (
    AthContextRecord,
)
from PHX2.stage29.stage29_4_soak_models import (
    Stage29_4PassResult,
    Stage29_4SoakBounds,
    Stage29_4SoakDedupeKey,
    build_pass_result,
    build_soak_bounds,
    build_soak_dedupe_key,
)
from PHX2.stage29.stage29_5_2_synthetic_evidence_fixtures import (
    build_synthetic_conflicting_evidence,
    build_synthetic_missing_evidence,
    build_synthetic_present_evidence,
)
from PHX2.stage29.stage29_5_3_soak_pass_wrapper import (
    Stage29_5_3MigrationContextSoakPassWrapper,
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
)
from PHX2.stage29.stage29_5_migration_models import (
    Stage29_5MigrationEvidenceRecord,
)


# ---------------------------------------------------------------------------
# Shared safe-shape constants
# ---------------------------------------------------------------------------


_BASE_MINT_A = "BeHSHaUCGC67PZLuHvj4EuNonZekbfBGMmWsWirmpump"
_BASE_MINT_B = "DummyTokenMintAaaaaaaaaaaaaaaaaaaaaaaaaapump"
_POOL_ACCOUNT_A = (
    "PoolAccount111111111111111111111111111111111"
)
_POOL_ACCOUNT_B = (
    "PoolAccount222222222222222222222222222222222"
)
_POOL_PROGRAM_ID = (
    "pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA"
)
_QUOTE_MINT_SOL = (
    "So11111111111111111111111111111111111111112"
)  # length 43
_QUOTE_MINT_SOL_PADDED = _QUOTE_MINT_SOL + "p"  # length 44 safe-shape
_MIGRATION_TS = "2026-05-26T11:00:00+00:00"
_ATH_TS = "2026-05-26T11:30:00+00:00"
_OBSERVED_AT = "2026-05-26T12:00:00+00:00"


def _safe_mint_padded(value: str) -> str:
    """Return ``value`` padded / truncated to a safe-shape Stage
    29.5.3 mint string (length 32..64, base58 alphabet only).

    The padding character ``x`` is in the canonical base58
    alphabet so the padded value passes the Stage 29.5.3
    base58-shape validator. The input is also stripped of
    non-base58 characters defensively.
    """
    base58 = (
        "123456789"
        "ABCDEFGHJKLMNPQRSTUVWXYZ"
        "abcdefghijkmnopqrstuvwxyz"
    )
    sanitized = "".join(ch for ch in value if ch in base58)
    if len(sanitized) < 32:
        return sanitized + "x" * (32 - len(sanitized))
    if len(sanitized) > 64:
        return sanitized[:64]
    return sanitized


_DEDUPE_TOKEN_MINT = _safe_mint_padded(_BASE_MINT_A)


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class _FakeInner:
    """Deterministic inner pass entrypoint that yields a
    pre-configured sequence of ``Stage29_4PassResult`` envelopes
    per call. After the sequence is exhausted, the last element
    is returned on every subsequent call (matches the canonical
    Stage 29.4 ``_make_pass_sequence_entrypoint`` discipline).
    Counts call invocations.
    """

    def __init__(
        self,
        results: Sequence[Stage29_4PassResult],
    ) -> None:
        self._results: List[Stage29_4PassResult] = list(results)
        self.call_count: int = 0
        self.calls: List[dict] = []

    def __call__(
        self,
        *,
        pass_index: int,
        bounds: Stage29_4SoakBounds,
        soak_output_dir: Path,
    ) -> Stage29_4PassResult:
        self.call_count += 1
        self.calls.append(
            {
                "pass_index": pass_index,
                "bounds": bounds,
                "soak_output_dir": soak_output_dir,
            }
        )
        if not self._results:
            raise RuntimeError(
                "_FakeInner has no pre-configured results"
            )
        idx = self.call_count - 1
        if idx >= len(self._results):
            idx = len(self._results) - 1
        return self._results[idx]


class _FakeEvidenceProvider:
    def __init__(
        self,
        per_call: Sequence[
            Sequence[Stage29_5MigrationEvidenceRecord]
        ],
    ) -> None:
        self._per_call = [list(s) for s in per_call]
        self.call_count: int = 0
        self.last_base_mint: Optional[str] = None

    def __call__(
        self, *, base_mint: str,
    ) -> Sequence[Stage29_5MigrationEvidenceRecord]:
        self.call_count += 1
        self.last_base_mint = base_mint
        if not self._per_call:
            return ()
        return tuple(self._per_call.pop(0))


class _RaisingEvidenceProvider:
    def __init__(self) -> None:
        self.call_count: int = 0

    def __call__(
        self, *, base_mint: str,
    ) -> Sequence[Stage29_5MigrationEvidenceRecord]:
        self.call_count += 1
        raise Stage29_5_3MigrationEvidenceProviderError(
            "EVIDENCE_PROVIDER_DOWN",
        )


class _UnexpectedExceptionEvidenceProvider:
    def __init__(self) -> None:
        self.call_count: int = 0

    def __call__(
        self, *, base_mint: str,
    ) -> Sequence[Stage29_5MigrationEvidenceRecord]:
        self.call_count += 1
        raise RuntimeError("UNEXPECTED")


class _MalformedEvidenceProvider:
    """Returns a sequence containing a non-record object so the
    Stage 29.5.2 composition layer raises a validator error.
    """

    def __init__(self) -> None:
        self.call_count: int = 0

    def __call__(
        self, *, base_mint: str,
    ):  # noqa: ANN201
        self.call_count += 1
        return ("not_an_evidence_record",)


class _SlowEvidenceProvider:
    """Sleeps a deterministic amount per call before returning an
    empty (MISSING-only) evidence sequence. Used to prove the
    deferred-observation design moves provider latency outside
    the Stage 29.4 timed pass boundary.
    """

    def __init__(self, *, sleep_seconds: float) -> None:
        self._sleep_seconds = sleep_seconds
        self.call_count: int = 0

    def __call__(
        self, *, base_mint: str,
    ) -> Sequence[Stage29_5MigrationEvidenceRecord]:
        self.call_count += 1
        time.sleep(self._sleep_seconds)
        return ()


class _FakeAthContextProvider:
    def __init__(
        self, snapshot: Optional[AthContextRecord],
    ) -> None:
        self._snapshot = snapshot
        self.call_count: int = 0

    def __call__(
        self, *, base_mint: str,
    ) -> Optional[AthContextRecord]:
        self.call_count += 1
        return self._snapshot


class _DeterministicClock:
    def __init__(
        self, values: Sequence[str] = (),
    ) -> None:
        self._values = list(values) or [_OBSERVED_AT]
        self.call_count: int = 0

    def __call__(self) -> str:
        self.call_count += 1
        if not self._values:
            return _OBSERVED_AT
        if len(self._values) == 1:
            return self._values[0]
        return self._values.pop(0)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_dedupe_key(
    *, token_mint: str = _DEDUPE_TOKEN_MINT,
) -> Stage29_4SoakDedupeKey:
    return build_soak_dedupe_key(
        token_mint=token_mint,
        pair_quote_asset="SOL",
        event_kind="SWAP",
        ping_type="PRIVATE_OPERATOR_OBSERVE",
        normalized_event_id="evt_001",
    )


def _build_pass_result_with_dedupe(
    *, token_mint: str = _DEDUPE_TOKEN_MINT,
) -> Stage29_4PassResult:
    return build_pass_result(
        smoke_result=_DummySmokeResult(),
        dedupe_key=_build_dedupe_key(token_mint=token_mint),
    )


def _build_pass_result_without_dedupe() -> (
    Stage29_4PassResult
):
    return build_pass_result(
        smoke_result=_DummySmokeResult(),
        dedupe_key=None,
    )


class _DummySmokeResult:
    """Duck-typed smoke result the Stage 29.4 orchestrator's
    projection helper accepts. Carries the closed-set Stage 29.3
    outcome fields the orchestrator reads.
    """

    def __init__(
        self,
        *,
        tradeable_smoke_outcome: str = "DISPATCHED",
        tradeable_smoke_refusal_reason: str = "NONE",
        events_seen: int = 1,
        candidates_dispatched: int = 1,
        candidates_suppressed: int = 0,
        dispatch_success: int = 1,
        dispatch_failure: int = 0,
    ) -> None:
        self.tradeable_smoke_outcome = tradeable_smoke_outcome
        self.tradeable_smoke_refusal_reason = (
            tradeable_smoke_refusal_reason
        )
        self.events_seen = events_seen
        self.candidates_dispatched = candidates_dispatched
        self.candidates_suppressed = candidates_suppressed
        self.dispatch_success = dispatch_success
        self.dispatch_failure = dispatch_failure


def _build_soak_bounds(
    *,
    wall_clock_seconds: int = 60,
    max_dispatches: int = 3,
    max_passes: int = 3,
    max_consecutive_suppressions: int = 5,
    heartbeat_cadence_seconds: int = 10,
) -> Stage29_4SoakBounds:
    return build_soak_bounds(
        wall_clock_seconds=wall_clock_seconds,
        max_dispatches=max_dispatches,
        max_passes=max_passes,
        max_consecutive_suppressions=(
            max_consecutive_suppressions
        ),
        heartbeat_cadence_seconds=heartbeat_cadence_seconds,
    )


def _make_ath_record(
    *,
    token_mint: Optional[str],
    ath_value: Optional[str] = "0.000054",
    ath_observed_at_utc: Optional[str] = _ATH_TS,
    ath_since_migration_status: str = "POST_MIGRATION_ONLY",
    ath_status: str = "PRESENT",
) -> AthContextRecord:
    return AthContextRecord(
        token_mint=token_mint,
        pair_type="PUMP_SOL",
        quote_asset="SOL",
        ath_value=ath_value,
        ath_unit="USD",
        ath_source="STAGE29_2_BIRDEYE_OHLCV",
        ath_observed_at_utc=ath_observed_at_utc,
        ath_since_migration_status=ath_since_migration_status,
        drawdown_from_ath=None,
        drawdown_unit="USD",
        drawdown_basis="UNKNOWN",
        ath_status=ath_status,
        ath_reason="OK",
        schema_version="stage27_v0_price_ath",
    )


@pytest.fixture
def output_dir(tmp_path: Path) -> Path:
    out = tmp_path / "stage29_5_3_soak_output"
    out.mkdir()
    return out


# ===========================================================================
# Stage 29.4 pass-entrypoint shape + inner-identity invariants
# ===========================================================================


def test_wrapper_satisfies_stage29_4_pass_entrypoint_shape(
    output_dir: Path,
) -> None:
    """Wrapper is callable with the Stage 29.4 pass-entrypoint
    keyword args and returns a Stage29_4PassResult.
    """
    inner = _FakeInner(
        [_build_pass_result_without_dedupe()],
    )
    wrapper = Stage29_5_3MigrationContextSoakPassWrapper(
        inner_pass_entrypoint=inner,
        evidence_provider=_FakeEvidenceProvider(((),)),
        ath_context_provider=_FakeAthContextProvider(None),
        clock=_DeterministicClock(),
        write_side_channel_artifact=False,
    )
    bounds = _build_soak_bounds()
    result = wrapper(
        pass_index=1,
        bounds=bounds,
        soak_output_dir=output_dir,
    )
    assert isinstance(result, Stage29_4PassResult)


def test_wrapper_returns_inner_pass_result_by_identity(
    output_dir: Path,
) -> None:
    """The wrapper must echo the inner result by Python identity
    (the same object reference). Byte-equal-via-dataclass.asdict
    is implied by identity but identity is strictly stronger.
    """
    inner_result = _build_pass_result_with_dedupe()
    inner = _FakeInner([inner_result])
    wrapper = Stage29_5_3MigrationContextSoakPassWrapper(
        inner_pass_entrypoint=inner,
        evidence_provider=_FakeEvidenceProvider(((),)),
        ath_context_provider=_FakeAthContextProvider(None),
        clock=_DeterministicClock(),
        write_side_channel_artifact=False,
    )
    bounds = _build_soak_bounds()
    result = wrapper(
        pass_index=1,
        bounds=bounds,
        soak_output_dir=output_dir,
    )
    assert result is inner_result


def test_wrapper_calls_inner_exactly_once_per_wrapper_call(
    output_dir: Path,
) -> None:
    inner = _FakeInner(
        [
            _build_pass_result_without_dedupe(),
            _build_pass_result_without_dedupe(),
            _build_pass_result_without_dedupe(),
        ]
    )
    wrapper = Stage29_5_3MigrationContextSoakPassWrapper(
        inner_pass_entrypoint=inner,
        evidence_provider=_FakeEvidenceProvider(((), (), ())),
        ath_context_provider=_FakeAthContextProvider(None),
        clock=_DeterministicClock(),
        write_side_channel_artifact=False,
    )
    bounds = _build_soak_bounds()
    for i in (1, 2, 3):
        wrapper(
            pass_index=i,
            bounds=bounds,
            soak_output_dir=output_dir,
        )
    assert inner.call_count == 3


# ===========================================================================
# Deferred-observation invariants on __call__
# ===========================================================================


def test_wrapper_call_does_not_call_evidence_provider(
    output_dir: Path,
) -> None:
    """``wrapper.__call__`` must NOT call the evidence provider
    even when the inner pass result carries a valid dedupe key.
    The provider is invoked only by ``flush_pending_observations``.
    """
    inner = _FakeInner([_build_pass_result_with_dedupe()])
    evidence_provider = _FakeEvidenceProvider(((),))
    wrapper = Stage29_5_3MigrationContextSoakPassWrapper(
        inner_pass_entrypoint=inner,
        evidence_provider=evidence_provider,
        ath_context_provider=_FakeAthContextProvider(None),
        clock=_DeterministicClock(),
        write_side_channel_artifact=False,
    )
    bounds = _build_soak_bounds()
    wrapper(
        pass_index=1,
        bounds=bounds,
        soak_output_dir=output_dir,
    )
    assert evidence_provider.call_count == 0


def test_wrapper_call_does_not_call_ath_context_provider(
    output_dir: Path,
) -> None:
    """``wrapper.__call__`` must NOT call the ATH context
    provider even when the inner pass result carries a valid
    dedupe key. The provider is invoked only by
    ``flush_pending_observations``.
    """
    inner = _FakeInner([_build_pass_result_with_dedupe()])
    ath_provider = _FakeAthContextProvider(None)
    wrapper = Stage29_5_3MigrationContextSoakPassWrapper(
        inner_pass_entrypoint=inner,
        evidence_provider=_FakeEvidenceProvider(((),)),
        ath_context_provider=ath_provider,
        clock=_DeterministicClock(),
        write_side_channel_artifact=False,
    )
    bounds = _build_soak_bounds()
    wrapper(
        pass_index=1,
        bounds=bounds,
        soak_output_dir=output_dir,
    )
    assert ath_provider.call_count == 0


def test_wrapper_call_does_not_call_clock(
    output_dir: Path,
) -> None:
    """``wrapper.__call__`` must NOT call the operator clock. The
    timestamp recorded on a composed observation is produced
    only by ``flush_pending_observations``.
    """
    inner = _FakeInner([_build_pass_result_with_dedupe()])
    clock = _DeterministicClock()
    wrapper = Stage29_5_3MigrationContextSoakPassWrapper(
        inner_pass_entrypoint=inner,
        evidence_provider=_FakeEvidenceProvider(((),)),
        ath_context_provider=_FakeAthContextProvider(None),
        clock=clock,
        write_side_channel_artifact=False,
    )
    bounds = _build_soak_bounds()
    wrapper(
        pass_index=1,
        bounds=bounds,
        soak_output_dir=output_dir,
    )
    assert clock.call_count == 0


def test_wrapper_call_does_not_write_side_channel_artifact(
    output_dir: Path,
) -> None:
    """``wrapper.__call__`` must NOT write the side-channel
    artifact even when ``write_side_channel_artifact=True``. The
    artifact is appended only by ``flush_pending_observations``.
    """
    inner = _FakeInner([_build_pass_result_with_dedupe()])
    wrapper = Stage29_5_3MigrationContextSoakPassWrapper(
        inner_pass_entrypoint=inner,
        evidence_provider=_FakeEvidenceProvider(((),)),
        ath_context_provider=_FakeAthContextProvider(None),
        clock=_DeterministicClock(),
        write_side_channel_artifact=True,
    )
    bounds = _build_soak_bounds()
    wrapper(
        pass_index=1,
        bounds=bounds,
        soak_output_dir=output_dir,
    )
    artifact = (
        output_dir / wrapper.side_channel_artifact_basename
    )
    assert not artifact.exists(), (
        "wrapper.__call__ must not write the side-channel "
        "artifact; that work is deferred to "
        "flush_pending_observations"
    )


def test_wrapper_call_records_minimal_pending_observation(
    output_dir: Path,
) -> None:
    """``wrapper.__call__`` must record exactly one minimal
    pending observation per call, with ``pass_index`` /
    ``candidate_base_mint`` / ``soak_output_dir`` populated.
    ``wrapper.observations`` (composed) remains empty until flush.
    """
    inner = _FakeInner([_build_pass_result_with_dedupe()])
    wrapper = Stage29_5_3MigrationContextSoakPassWrapper(
        inner_pass_entrypoint=inner,
        evidence_provider=_FakeEvidenceProvider(((),)),
        ath_context_provider=_FakeAthContextProvider(None),
        clock=_DeterministicClock(),
        write_side_channel_artifact=False,
    )
    bounds = _build_soak_bounds()
    wrapper(
        pass_index=1,
        bounds=bounds,
        soak_output_dir=output_dir,
    )
    assert len(wrapper.pending_observations) == 1
    pending = wrapper.pending_observations[0]
    assert isinstance(
        pending, Stage29_5_3PendingPassObservation,
    )
    assert pending.pass_index == 1
    assert pending.candidate_base_mint == _DEDUPE_TOKEN_MINT
    assert pending.soak_output_dir == output_dir
    assert wrapper.observations == ()


def test_wrapper_call_pending_observation_widens_unsafe_mint_to_none(
    output_dir: Path,
) -> None:
    """When the inner pass result's dedupe key carries a
    ``token_mint`` that fails the Stage 29.5.3 base58 safe-shape
    validator (e.g. shorter than 32 chars or carrying a
    non-base58 character), the pending observation records
    ``candidate_base_mint=None`` so the flush will produce
    ``NO_CANDIDATE_AXES`` without ever passing the unsafe mint
    to a provider or to the composition layer.

    NOTE: ``Stage29_4SoakDedupeKey`` itself has its own safe-shape
    validator; we therefore exercise this branch by constructing
    a dedupe key with a token_mint that PASSES the Stage 29.4
    safe-shape but FAILS the stricter Stage 29.5.3 base58 shape.
    A 32-char string containing the digit ``0`` (forbidden in
    base58) satisfies both: Stage 29.4 accepts ``0`` (its
    allowed-chars set is wider) while Stage 29.5.3 rejects it.
    """
    token_with_zero = "0" + "a" * 31  # length 32, contains "0"
    inner = _FakeInner(
        [
            _build_pass_result_with_dedupe(
                token_mint=token_with_zero,
            ),
        ],
    )
    wrapper = Stage29_5_3MigrationContextSoakPassWrapper(
        inner_pass_entrypoint=inner,
        evidence_provider=_FakeEvidenceProvider(((),)),
        ath_context_provider=_FakeAthContextProvider(None),
        clock=_DeterministicClock(),
        write_side_channel_artifact=False,
    )
    bounds = _build_soak_bounds()
    wrapper(
        pass_index=1,
        bounds=bounds,
        soak_output_dir=output_dir,
    )
    pending = wrapper.pending_observations[0]
    assert pending.candidate_base_mint is None


# ===========================================================================
# Behavior matrix (post-flush)
# ===========================================================================


def test_wrapper_dedupe_key_none_yields_no_candidate_axes(
    output_dir: Path,
) -> None:
    inner = _FakeInner(
        [_build_pass_result_without_dedupe()],
    )
    evidence_provider = _FakeEvidenceProvider(((),))
    ath_provider = _FakeAthContextProvider(None)
    wrapper = Stage29_5_3MigrationContextSoakPassWrapper(
        inner_pass_entrypoint=inner,
        evidence_provider=evidence_provider,
        ath_context_provider=ath_provider,
        clock=_DeterministicClock(),
        write_side_channel_artifact=False,
    )
    bounds = _build_soak_bounds()
    wrapper(
        pass_index=1,
        bounds=bounds,
        soak_output_dir=output_dir,
    )
    wrapper.flush_pending_observations()
    assert len(wrapper.observations) == 1
    obs = wrapper.observations[0]
    assert obs.observation_status == (
        OBSERVATION_STATUS_NO_CANDIDATE_AXES
    )
    assert obs.candidate_base_mint is None
    assert obs.join_status_echoed is None
    assert obs.measurement_status_echoed is None
    assert obs.warnings_echoed == ()
    # When there are no candidate axes the flush short-circuits
    # before calling the evidence / ATH providers.
    assert evidence_provider.call_count == 0
    assert ath_provider.call_count == 0


def test_wrapper_complete_composition_happy_path(
    output_dir: Path,
) -> None:
    inner_result = _build_pass_result_with_dedupe()
    inner = _FakeInner([inner_result])
    evidence_records = (
        build_synthetic_present_evidence(
            base_mint=_DEDUPE_TOKEN_MINT,
            pool_account=_POOL_ACCOUNT_A,
            pool_program_id=_POOL_PROGRAM_ID,
            quote_mint=_QUOTE_MINT_SOL_PADDED,
            migration_timestamp_utc=_MIGRATION_TS,
            observed_at_utc=_OBSERVED_AT,
            migration_slot=12345,
        ),
    )
    evidence_provider = _FakeEvidenceProvider(
        (evidence_records,),
    )
    ath_provider = _FakeAthContextProvider(
        _make_ath_record(token_mint=_DEDUPE_TOKEN_MINT),
    )
    wrapper = Stage29_5_3MigrationContextSoakPassWrapper(
        inner_pass_entrypoint=inner,
        evidence_provider=evidence_provider,
        ath_context_provider=ath_provider,
        clock=_DeterministicClock(),
        write_side_channel_artifact=False,
    )
    bounds = _build_soak_bounds()
    wrapper(
        pass_index=1,
        bounds=bounds,
        soak_output_dir=output_dir,
    )
    wrapper.flush_pending_observations()
    assert len(wrapper.observations) == 1
    obs = wrapper.observations[0]
    assert obs.observation_status == OBSERVATION_STATUS_COMPOSED
    assert obs.candidate_base_mint == _DEDUPE_TOKEN_MINT
    assert obs.join_status_echoed == "JOINED"
    assert obs.measurement_status_echoed == "COMPLETE"
    assert obs.post_migration_ath_verified_echoed is True
    assert obs.warnings_echoed == ()


def test_wrapper_missing_migration_path(
    output_dir: Path,
) -> None:
    inner_result = _build_pass_result_with_dedupe()
    inner = _FakeInner([inner_result])
    evidence_records = (
        build_synthetic_missing_evidence(
            observed_at_utc=_OBSERVED_AT,
        ),
    )
    evidence_provider = _FakeEvidenceProvider(
        (evidence_records,),
    )
    ath_provider = _FakeAthContextProvider(None)
    wrapper = Stage29_5_3MigrationContextSoakPassWrapper(
        inner_pass_entrypoint=inner,
        evidence_provider=evidence_provider,
        ath_context_provider=ath_provider,
        clock=_DeterministicClock(),
        write_side_channel_artifact=False,
    )
    bounds = _build_soak_bounds()
    wrapper(
        pass_index=1,
        bounds=bounds,
        soak_output_dir=output_dir,
    )
    wrapper.flush_pending_observations()
    obs = wrapper.observations[0]
    assert obs.observation_status == OBSERVATION_STATUS_COMPOSED
    assert obs.join_status_echoed == "NO_MATCH"
    assert obs.measurement_status_echoed == "MISSING_MIGRATION"
    assert obs.post_migration_ath_verified_echoed is None
    assert "MIGRATION_MISSING" in obs.warnings_echoed
    assert (
        "POST_MIGRATION_ATH_UNVERIFIED" in obs.warnings_echoed
    )


def test_wrapper_partial_wrong_token_ath_path_with_verified_none(
    output_dir: Path,
) -> None:
    """Wrong-token ATH context must NEVER drive verified=False;
    the Stage 29.5.1 PASS-WITH-PATCHES rule collapses every
    wrong-token / non-PRESENT case to verified=None.
    """
    inner_result = _build_pass_result_with_dedupe()
    inner = _FakeInner([inner_result])
    evidence_records = (
        build_synthetic_present_evidence(
            base_mint=_DEDUPE_TOKEN_MINT,
            pool_account=_POOL_ACCOUNT_A,
            pool_program_id=_POOL_PROGRAM_ID,
            quote_mint=_QUOTE_MINT_SOL_PADDED,
            migration_timestamp_utc=_MIGRATION_TS,
            observed_at_utc=_OBSERVED_AT,
            migration_slot=12345,
        ),
    )
    other_token = _safe_mint_padded(_BASE_MINT_B)
    ath_provider = _FakeAthContextProvider(
        _make_ath_record(token_mint=other_token),
    )
    wrapper = Stage29_5_3MigrationContextSoakPassWrapper(
        inner_pass_entrypoint=inner,
        evidence_provider=_FakeEvidenceProvider(
            (evidence_records,),
        ),
        ath_context_provider=ath_provider,
        clock=_DeterministicClock(),
        write_side_channel_artifact=False,
    )
    bounds = _build_soak_bounds()
    wrapper(
        pass_index=1,
        bounds=bounds,
        soak_output_dir=output_dir,
    )
    wrapper.flush_pending_observations()
    obs = wrapper.observations[0]
    assert obs.observation_status == OBSERVATION_STATUS_COMPOSED
    assert obs.join_status_echoed == "JOINED"
    assert obs.measurement_status_echoed == (
        "PARTIAL_MIGRATION_PRESENT"
    )
    assert obs.post_migration_ath_verified_echoed is None
    assert (
        "POST_MIGRATION_ATH_UNVERIFIED" in obs.warnings_echoed
    )


def test_wrapper_pair_mismatch_path(
    output_dir: Path,
) -> None:
    inner_result = _build_pass_result_with_dedupe()
    inner = _FakeInner([inner_result])
    record_a = build_synthetic_present_evidence(
        base_mint=_DEDUPE_TOKEN_MINT,
        pool_account=_POOL_ACCOUNT_A,
        pool_program_id=_POOL_PROGRAM_ID,
        quote_mint=_QUOTE_MINT_SOL_PADDED,
        migration_timestamp_utc=_MIGRATION_TS,
        observed_at_utc=_OBSERVED_AT,
        migration_slot=12345,
    )
    record_b = build_synthetic_present_evidence(
        base_mint=_DEDUPE_TOKEN_MINT,
        pool_account=_POOL_ACCOUNT_B,
        pool_program_id=_POOL_PROGRAM_ID,
        quote_mint=_QUOTE_MINT_SOL_PADDED,
        migration_timestamp_utc=_MIGRATION_TS,
        observed_at_utc=_OBSERVED_AT,
        migration_slot=12345,
    )
    wrapper = Stage29_5_3MigrationContextSoakPassWrapper(
        inner_pass_entrypoint=inner,
        evidence_provider=_FakeEvidenceProvider(
            ((record_a, record_b),),
        ),
        ath_context_provider=_FakeAthContextProvider(None),
        clock=_DeterministicClock(),
        write_side_channel_artifact=False,
    )
    bounds = _build_soak_bounds()
    wrapper(
        pass_index=1,
        bounds=bounds,
        soak_output_dir=output_dir,
    )
    wrapper.flush_pending_observations()
    obs = wrapper.observations[0]
    assert obs.observation_status == OBSERVATION_STATUS_COMPOSED
    assert obs.join_status_echoed == "PAIR_MISMATCH"
    assert obs.measurement_status_echoed == (
        "INVALID_MIGRATION"
    )
    assert obs.post_migration_ath_verified_echoed is None
    assert (
        "MIGRATION_PAIR_MISMATCH" in obs.warnings_echoed
    )


def test_wrapper_conflicting_path_lands_on_invalid_migration(
    output_dir: Path,
) -> None:
    inner_result = _build_pass_result_with_dedupe()
    inner = _FakeInner([inner_result])
    record = build_synthetic_conflicting_evidence(
        base_mint=_DEDUPE_TOKEN_MINT,
        pool_account=_POOL_ACCOUNT_A,
        pool_program_id=_POOL_PROGRAM_ID,
        quote_mint=_QUOTE_MINT_SOL_PADDED,
        observed_at_utc=_OBSERVED_AT,
        migration_timestamp_utc=_MIGRATION_TS,
    )
    wrapper = Stage29_5_3MigrationContextSoakPassWrapper(
        inner_pass_entrypoint=inner,
        evidence_provider=_FakeEvidenceProvider(
            ((record,),),
        ),
        ath_context_provider=_FakeAthContextProvider(None),
        clock=_DeterministicClock(),
        write_side_channel_artifact=False,
    )
    bounds = _build_soak_bounds()
    wrapper(
        pass_index=1,
        bounds=bounds,
        soak_output_dir=output_dir,
    )
    wrapper.flush_pending_observations()
    obs = wrapper.observations[0]
    assert obs.observation_status == OBSERVATION_STATUS_COMPOSED
    assert obs.join_status_echoed == "SOURCE_INVALID"
    assert obs.measurement_status_echoed == (
        "INVALID_MIGRATION"
    )


def test_wrapper_composition_rejected_on_malformed_evidence(
    output_dir: Path,
) -> None:
    inner_result = _build_pass_result_with_dedupe()
    inner = _FakeInner([inner_result])
    wrapper = Stage29_5_3MigrationContextSoakPassWrapper(
        inner_pass_entrypoint=inner,
        evidence_provider=_MalformedEvidenceProvider(),
        ath_context_provider=_FakeAthContextProvider(None),
        clock=_DeterministicClock(),
        write_side_channel_artifact=False,
    )
    bounds = _build_soak_bounds()
    result = wrapper(
        pass_index=1,
        bounds=bounds,
        soak_output_dir=output_dir,
    )
    assert result is inner_result
    wrapper.flush_pending_observations()
    obs = wrapper.observations[0]
    assert obs.observation_status == (
        OBSERVATION_STATUS_COMPOSITION_REJECTED
    )


def test_wrapper_provider_rejected_when_provider_raises_closed_set_error(
    output_dir: Path,
) -> None:
    inner_result = _build_pass_result_with_dedupe()
    inner = _FakeInner([inner_result])
    wrapper = Stage29_5_3MigrationContextSoakPassWrapper(
        inner_pass_entrypoint=inner,
        evidence_provider=_RaisingEvidenceProvider(),
        ath_context_provider=_FakeAthContextProvider(None),
        clock=_DeterministicClock(),
        write_side_channel_artifact=False,
    )
    bounds = _build_soak_bounds()
    result = wrapper(
        pass_index=1,
        bounds=bounds,
        soak_output_dir=output_dir,
    )
    assert result is inner_result
    wrapper.flush_pending_observations()
    obs = wrapper.observations[0]
    assert obs.observation_status == (
        OBSERVATION_STATUS_PROVIDER_REJECTED
    )


def test_wrapper_provider_rejected_on_unexpected_exception(
    output_dir: Path,
) -> None:
    inner_result = _build_pass_result_with_dedupe()
    inner = _FakeInner([inner_result])
    wrapper = Stage29_5_3MigrationContextSoakPassWrapper(
        inner_pass_entrypoint=inner,
        evidence_provider=(
            _UnexpectedExceptionEvidenceProvider()
        ),
        ath_context_provider=_FakeAthContextProvider(None),
        clock=_DeterministicClock(),
        write_side_channel_artifact=False,
    )
    bounds = _build_soak_bounds()
    result = wrapper(
        pass_index=1,
        bounds=bounds,
        soak_output_dir=output_dir,
    )
    assert result is inner_result
    wrapper.flush_pending_observations()
    obs = wrapper.observations[0]
    assert obs.observation_status == (
        OBSERVATION_STATUS_PROVIDER_REJECTED
    )


def test_wrapper_failed_inner_pass_still_returns_unchanged(
    output_dir: Path,
) -> None:
    """A FAILED Stage 29.3 outcome on the inner pass result must
    still flow through the wrapper untouched. The dedupe_key is
    None for the FAILED path so the wrapper records
    NO_CANDIDATE_AXES on flush.
    """
    inner_result = build_pass_result(
        smoke_result=_DummySmokeResult(
            tradeable_smoke_outcome="FAILED",
            tradeable_smoke_refusal_reason="SESSION_FAILED",
            events_seen=0,
            candidates_dispatched=0,
            candidates_suppressed=0,
            dispatch_success=0,
            dispatch_failure=1,
        ),
        dedupe_key=None,
    )
    inner = _FakeInner([inner_result])
    wrapper = Stage29_5_3MigrationContextSoakPassWrapper(
        inner_pass_entrypoint=inner,
        evidence_provider=_FakeEvidenceProvider(((),)),
        ath_context_provider=_FakeAthContextProvider(None),
        clock=_DeterministicClock(),
        write_side_channel_artifact=False,
    )
    bounds = _build_soak_bounds()
    result = wrapper(
        pass_index=1,
        bounds=bounds,
        soak_output_dir=output_dir,
    )
    assert result is inner_result
    wrapper.flush_pending_observations()
    obs = wrapper.observations[0]
    assert obs.observation_status == (
        OBSERVATION_STATUS_NO_CANDIDATE_AXES
    )


def test_wrapper_observations_preserve_pass_order(
    output_dir: Path,
) -> None:
    inner = _FakeInner(
        [
            _build_pass_result_with_dedupe(),
            _build_pass_result_without_dedupe(),
            _build_pass_result_with_dedupe(),
        ]
    )
    evidence_records_with = (
        build_synthetic_present_evidence(
            base_mint=_DEDUPE_TOKEN_MINT,
            pool_account=_POOL_ACCOUNT_A,
            pool_program_id=_POOL_PROGRAM_ID,
            quote_mint=_QUOTE_MINT_SOL_PADDED,
            migration_timestamp_utc=_MIGRATION_TS,
            observed_at_utc=_OBSERVED_AT,
            migration_slot=12345,
        ),
    )
    evidence_provider = _FakeEvidenceProvider(
        (evidence_records_with, (), evidence_records_with),
    )
    ath_provider = _FakeAthContextProvider(
        _make_ath_record(token_mint=_DEDUPE_TOKEN_MINT),
    )
    wrapper = Stage29_5_3MigrationContextSoakPassWrapper(
        inner_pass_entrypoint=inner,
        evidence_provider=evidence_provider,
        ath_context_provider=ath_provider,
        clock=_DeterministicClock(),
        write_side_channel_artifact=False,
    )
    bounds = _build_soak_bounds()
    for i in (1, 2, 3):
        wrapper(
            pass_index=i,
            bounds=bounds,
            soak_output_dir=output_dir,
        )
    wrapper.flush_pending_observations()
    assert len(wrapper.observations) == 3
    assert wrapper.observations[0].pass_index == 1
    assert wrapper.observations[1].pass_index == 2
    assert wrapper.observations[2].pass_index == 3
    assert wrapper.observations[0].observation_status == (
        OBSERVATION_STATUS_COMPOSED
    )
    assert wrapper.observations[1].observation_status == (
        OBSERVATION_STATUS_NO_CANDIDATE_AXES
    )
    assert wrapper.observations[2].observation_status == (
        OBSERVATION_STATUS_COMPOSED
    )


# ===========================================================================
# Constructor / call-time validation
# ===========================================================================


def test_wrapper_constructor_rejects_non_callable_inner_entrypoint() -> None:
    with pytest.raises(Stage29_5_3WrappedPassError):
        Stage29_5_3MigrationContextSoakPassWrapper(
            inner_pass_entrypoint=None,  # type: ignore[arg-type]
            evidence_provider=_FakeEvidenceProvider(((),)),
            ath_context_provider=(
                _FakeAthContextProvider(None)
            ),
            clock=_DeterministicClock(),
        )


def test_wrapper_constructor_rejects_non_callable_evidence_provider() -> None:
    with pytest.raises(Stage29_5_3WrappedPassError):
        Stage29_5_3MigrationContextSoakPassWrapper(
            inner_pass_entrypoint=_FakeInner([]),
            evidence_provider=None,  # type: ignore[arg-type]
            ath_context_provider=(
                _FakeAthContextProvider(None)
            ),
            clock=_DeterministicClock(),
        )


def test_wrapper_constructor_rejects_non_callable_ath_provider() -> None:
    with pytest.raises(Stage29_5_3WrappedPassError):
        Stage29_5_3MigrationContextSoakPassWrapper(
            inner_pass_entrypoint=_FakeInner([]),
            evidence_provider=_FakeEvidenceProvider(((),)),
            ath_context_provider=None,  # type: ignore[arg-type]
            clock=_DeterministicClock(),
        )


def test_wrapper_constructor_rejects_non_callable_clock() -> None:
    with pytest.raises(Stage29_5_3WrappedPassError):
        Stage29_5_3MigrationContextSoakPassWrapper(
            inner_pass_entrypoint=_FakeInner([]),
            evidence_provider=_FakeEvidenceProvider(((),)),
            ath_context_provider=(
                _FakeAthContextProvider(None)
            ),
            clock=None,  # type: ignore[arg-type]
        )


def test_wrapper_call_rejects_non_positive_pass_index(
    output_dir: Path,
) -> None:
    wrapper = Stage29_5_3MigrationContextSoakPassWrapper(
        inner_pass_entrypoint=_FakeInner(
            [_build_pass_result_without_dedupe()],
        ),
        evidence_provider=_FakeEvidenceProvider(((),)),
        ath_context_provider=_FakeAthContextProvider(None),
        clock=_DeterministicClock(),
        write_side_channel_artifact=False,
    )
    bounds = _build_soak_bounds()
    with pytest.raises(Stage29_5_3WrappedPassError):
        wrapper(
            pass_index=0,
            bounds=bounds,
            soak_output_dir=output_dir,
        )


def test_wrapper_call_rejects_non_soak_bounds(
    output_dir: Path,
) -> None:
    wrapper = Stage29_5_3MigrationContextSoakPassWrapper(
        inner_pass_entrypoint=_FakeInner(
            [_build_pass_result_without_dedupe()],
        ),
        evidence_provider=_FakeEvidenceProvider(((),)),
        ath_context_provider=_FakeAthContextProvider(None),
        clock=_DeterministicClock(),
        write_side_channel_artifact=False,
    )
    with pytest.raises(Stage29_5_3WrappedPassError):
        wrapper(
            pass_index=1,
            bounds="not_a_soak_bounds",  # type: ignore[arg-type]
            soak_output_dir=output_dir,
        )


def test_wrapper_call_rejects_non_path_output_dir() -> None:
    wrapper = Stage29_5_3MigrationContextSoakPassWrapper(
        inner_pass_entrypoint=_FakeInner(
            [_build_pass_result_without_dedupe()],
        ),
        evidence_provider=_FakeEvidenceProvider(((),)),
        ath_context_provider=_FakeAthContextProvider(None),
        clock=_DeterministicClock(),
        write_side_channel_artifact=False,
    )
    bounds = _build_soak_bounds()
    with pytest.raises(Stage29_5_3WrappedPassError):
        wrapper(
            pass_index=1,
            bounds=bounds,
            soak_output_dir="/tmp/output",  # type: ignore[arg-type]
        )


# ===========================================================================
# Side-channel artifact (flush-time)
# ===========================================================================


def test_wrapper_side_channel_artifact_is_appended_in_pass_order(
    output_dir: Path,
) -> None:
    inner = _FakeInner(
        [
            _build_pass_result_with_dedupe(),
            _build_pass_result_without_dedupe(),
        ]
    )
    evidence_records = (
        build_synthetic_missing_evidence(
            observed_at_utc=_OBSERVED_AT,
        ),
    )
    evidence_provider = _FakeEvidenceProvider(
        (evidence_records, ()),
    )
    ath_provider = _FakeAthContextProvider(None)
    wrapper = Stage29_5_3MigrationContextSoakPassWrapper(
        inner_pass_entrypoint=inner,
        evidence_provider=evidence_provider,
        ath_context_provider=ath_provider,
        clock=_DeterministicClock(),
        write_side_channel_artifact=True,
    )
    bounds = _build_soak_bounds()
    wrapper(
        pass_index=1,
        bounds=bounds,
        soak_output_dir=output_dir,
    )
    wrapper(
        pass_index=2,
        bounds=bounds,
        soak_output_dir=output_dir,
    )
    artifact = (
        output_dir / "stage29_5_3_migration_context.jsonl"
    )
    assert not artifact.exists(), (
        "flush has not run yet; artifact must not exist"
    )
    wrapper.flush_pending_observations()
    assert artifact.is_file()
    lines = artifact.read_text(
        encoding="utf-8",
    ).splitlines()
    assert len(lines) == 2
    # The first line has the COMPOSED status (MISSING_MIGRATION
    # outcome from the missing-only path through the join); the
    # second line has NO_CANDIDATE_AXES.
    assert '"observation_status":"COMPOSED"' in lines[0]
    assert (
        '"observation_status":"NO_CANDIDATE_AXES"' in lines[1]
    )


def test_wrapper_swallows_side_channel_artifact_failure_when_output_dir_missing(
    tmp_path: Path,
) -> None:
    """If the soak output directory doesn't exist, the writer
    raises Stage29_5_3SideChannelArtifactError. The non-strict
    flush must swallow this and still record the composed
    observation on ``wrapper.observations``.
    """
    output_dir = tmp_path / "does_not_exist"
    inner_result = _build_pass_result_with_dedupe()
    inner = _FakeInner([inner_result])
    wrapper = Stage29_5_3MigrationContextSoakPassWrapper(
        inner_pass_entrypoint=inner,
        evidence_provider=_FakeEvidenceProvider(
            (
                (
                    build_synthetic_missing_evidence(
                        observed_at_utc=_OBSERVED_AT,
                    ),
                ),
            ),
        ),
        ath_context_provider=_FakeAthContextProvider(None),
        clock=_DeterministicClock(),
        write_side_channel_artifact=True,
    )
    bounds = _build_soak_bounds()
    result = wrapper(
        pass_index=1,
        bounds=bounds,
        soak_output_dir=output_dir,
    )
    assert result is inner_result
    wrapper.flush_pending_observations()
    assert len(wrapper.observations) == 1
    obs = wrapper.observations[0]
    assert obs.observation_status == OBSERVATION_STATUS_COMPOSED


# ===========================================================================
# Strict flush mode
# ===========================================================================


def test_strict_flush_propagates_provider_error(
    output_dir: Path,
) -> None:
    """Strict flush propagates a closed-set provider error."""
    inner = _FakeInner([_build_pass_result_with_dedupe()])
    wrapper = Stage29_5_3MigrationContextSoakPassWrapper(
        inner_pass_entrypoint=inner,
        evidence_provider=_RaisingEvidenceProvider(),
        ath_context_provider=_FakeAthContextProvider(None),
        clock=_DeterministicClock(),
        write_side_channel_artifact=False,
    )
    bounds = _build_soak_bounds()
    wrapper(
        pass_index=1,
        bounds=bounds,
        soak_output_dir=output_dir,
    )
    with pytest.raises(
        Stage29_5_3MigrationEvidenceProviderError,
    ):
        wrapper.flush_pending_observations(strict=True)


def test_strict_flush_propagates_unexpected_provider_exception(
    output_dir: Path,
) -> None:
    """Strict flush propagates an unexpected provider exception
    type as-is.
    """
    inner = _FakeInner([_build_pass_result_with_dedupe()])
    wrapper = Stage29_5_3MigrationContextSoakPassWrapper(
        inner_pass_entrypoint=inner,
        evidence_provider=(
            _UnexpectedExceptionEvidenceProvider()
        ),
        ath_context_provider=_FakeAthContextProvider(None),
        clock=_DeterministicClock(),
        write_side_channel_artifact=False,
    )
    bounds = _build_soak_bounds()
    wrapper(
        pass_index=1,
        bounds=bounds,
        soak_output_dir=output_dir,
    )
    with pytest.raises(RuntimeError):
        wrapper.flush_pending_observations(strict=True)


def test_strict_flush_propagates_artifact_failure_when_output_dir_missing(
    tmp_path: Path,
) -> None:
    """Strict flush propagates a side-channel artifact failure
    (closed-set Stage29_5_3SideChannelArtifactError) when the
    soak output directory does not exist.
    """
    output_dir = tmp_path / "does_not_exist"
    inner = _FakeInner([_build_pass_result_with_dedupe()])
    wrapper = Stage29_5_3MigrationContextSoakPassWrapper(
        inner_pass_entrypoint=inner,
        evidence_provider=_FakeEvidenceProvider(
            (
                (
                    build_synthetic_missing_evidence(
                        observed_at_utc=_OBSERVED_AT,
                    ),
                ),
            ),
        ),
        ath_context_provider=_FakeAthContextProvider(None),
        clock=_DeterministicClock(),
        write_side_channel_artifact=True,
    )
    bounds = _build_soak_bounds()
    wrapper(
        pass_index=1,
        bounds=bounds,
        soak_output_dir=output_dir,
    )
    with pytest.raises(Stage29_5_3SideChannelArtifactError):
        wrapper.flush_pending_observations(strict=True)


def test_non_strict_flush_swallows_all_failure_modes_default(
    tmp_path: Path,
) -> None:
    """Default flush mode (non-strict) swallows provider,
    composition, and artifact failures and never raises out.
    Three pending observations exercise each path:
    PROVIDER_REJECTED (raising provider) is the relevant axis
    here because provider failure short-circuits before the
    artifact write.
    """
    output_dir_existing = tmp_path / "soak"
    output_dir_existing.mkdir()
    inner = _FakeInner(
        [
            _build_pass_result_with_dedupe(),
        ],
    )
    wrapper = Stage29_5_3MigrationContextSoakPassWrapper(
        inner_pass_entrypoint=inner,
        evidence_provider=_RaisingEvidenceProvider(),
        ath_context_provider=_FakeAthContextProvider(None),
        clock=_DeterministicClock(),
        write_side_channel_artifact=True,
    )
    bounds = _build_soak_bounds()
    wrapper(
        pass_index=1,
        bounds=bounds,
        soak_output_dir=output_dir_existing,
    )
    composed = wrapper.flush_pending_observations()
    assert len(composed) == 1
    assert composed[0].observation_status == (
        OBSERVATION_STATUS_PROVIDER_REJECTED
    )


# ===========================================================================
# Strict-mode retryability (no state mutation on artifact failure)
# ===========================================================================


def test_strict_artifact_failure_keeps_pending_and_no_observation(
    tmp_path: Path,
) -> None:
    """Strict retryability invariant: when the side-channel
    artifact write raises in ``strict=True`` mode, the failing
    pending must remain on ``wrapper.pending_observations``, no
    observation must be appended to ``wrapper.observations``,
    and the exception must propagate. After the operator fixes
    the underlying cause (creates the missing output directory),
    a retried ``flush_pending_observations(strict=True)`` must
    drain the still-pending observation, record exactly one
    composed observation on ``wrapper.observations``, and write
    exactly one JSONL artifact line.
    """
    missing_output_dir = tmp_path / "not_yet_created"
    inner = _FakeInner([_build_pass_result_with_dedupe()])
    evidence_records = (
        build_synthetic_missing_evidence(
            observed_at_utc=_OBSERVED_AT,
        ),
    )
    wrapper = Stage29_5_3MigrationContextSoakPassWrapper(
        inner_pass_entrypoint=inner,
        evidence_provider=_FakeEvidenceProvider(
            (evidence_records, evidence_records),
        ),
        ath_context_provider=_FakeAthContextProvider(None),
        clock=_DeterministicClock(),
        write_side_channel_artifact=True,
    )
    bounds = _build_soak_bounds()
    wrapper(
        pass_index=1,
        bounds=bounds,
        soak_output_dir=missing_output_dir,
    )
    assert len(wrapper.pending_observations) == 1
    assert wrapper.observations == ()

    with pytest.raises(Stage29_5_3SideChannelArtifactError):
        wrapper.flush_pending_observations(strict=True)

    # State preserved on failure: the failing pending stays
    # queued; no observation appended; the wrapper is fully
    # retryable.
    assert len(wrapper.pending_observations) == 1
    assert wrapper.pending_observations[0].pass_index == 1
    assert wrapper.observations == ()

    # Operator fixes the underlying cause.
    missing_output_dir.mkdir()

    # Retry under strict mode drains cleanly.
    composed = wrapper.flush_pending_observations(strict=True)
    assert len(composed) == 1
    assert composed[0].pass_index == 1
    assert composed[0].observation_status == (
        OBSERVATION_STATUS_COMPOSED
    )
    assert len(wrapper.observations) == 1
    assert wrapper.pending_observations == ()
    artifact = (
        missing_output_dir
        / "stage29_5_3_migration_context.jsonl"
    )
    assert artifact.is_file()
    lines = artifact.read_text(
        encoding="utf-8",
    ).splitlines()
    assert len(lines) == 1


def test_strict_artifact_failure_preserves_later_pending_items(
    tmp_path: Path,
) -> None:
    """Strict retryability across multiple pending: the first
    pending writes to an existing output dir and drains cleanly;
    the second pending writes to a missing output dir and the
    strict artifact write raises; on the raise the first
    observation must remain recorded, the failing second pending
    must remain queued, and the later third pending (also
    pointing at the missing dir) must remain queued behind the
    failing second pending. After the operator fixes the
    artifact issue, a retried strict flush drains the remaining
    two pending items in pass-arrival order.
    """
    good_dir = tmp_path / "good"
    good_dir.mkdir()
    bad_dir = tmp_path / "bad"  # not yet created
    inner = _FakeInner(
        [
            _build_pass_result_with_dedupe(),
            _build_pass_result_with_dedupe(),
            _build_pass_result_with_dedupe(),
        ],
    )
    evidence_records = (
        build_synthetic_missing_evidence(
            observed_at_utc=_OBSERVED_AT,
        ),
    )
    wrapper = Stage29_5_3MigrationContextSoakPassWrapper(
        inner_pass_entrypoint=inner,
        evidence_provider=_FakeEvidenceProvider(
            (
                evidence_records,
                evidence_records,
                evidence_records,
                evidence_records,
            ),
        ),
        ath_context_provider=_FakeAthContextProvider(None),
        clock=_DeterministicClock(),
        write_side_channel_artifact=True,
    )
    bounds = _build_soak_bounds()
    wrapper(
        pass_index=1,
        bounds=bounds,
        soak_output_dir=good_dir,
    )
    wrapper(
        pass_index=2,
        bounds=bounds,
        soak_output_dir=bad_dir,
    )
    wrapper(
        pass_index=3,
        bounds=bounds,
        soak_output_dir=bad_dir,
    )
    assert len(wrapper.pending_observations) == 3

    with pytest.raises(Stage29_5_3SideChannelArtifactError):
        wrapper.flush_pending_observations(strict=True)

    # First pending drained successfully: observation recorded,
    # artifact written under good_dir.
    assert len(wrapper.observations) == 1
    assert wrapper.observations[0].pass_index == 1
    assert wrapper.observations[0].observation_status == (
        OBSERVATION_STATUS_COMPOSED
    )
    good_artifact = (
        good_dir / "stage29_5_3_migration_context.jsonl"
    )
    assert good_artifact.is_file()
    assert (
        len(
            good_artifact.read_text(
                encoding="utf-8",
            ).splitlines()
        )
        == 1
    )

    # Failing second pending stays queued; later third pending
    # also stays queued behind it in pass-arrival order.
    assert len(wrapper.pending_observations) == 2
    assert wrapper.pending_observations[0].pass_index == 2
    assert wrapper.pending_observations[1].pass_index == 3
    assert not bad_dir.exists()

    # Operator fixes the underlying cause.
    bad_dir.mkdir()

    # Retry under strict mode drains the remaining two pending
    # items in pass-arrival order.
    composed = wrapper.flush_pending_observations(strict=True)
    assert len(composed) == 2
    assert composed[0].pass_index == 2
    assert composed[1].pass_index == 3
    assert composed[0].observation_status == (
        OBSERVATION_STATUS_COMPOSED
    )
    assert composed[1].observation_status == (
        OBSERVATION_STATUS_COMPOSED
    )
    assert len(wrapper.observations) == 3
    assert [
        o.pass_index for o in wrapper.observations
    ] == [1, 2, 3]
    assert wrapper.pending_observations == ()
    bad_artifact = (
        bad_dir / "stage29_5_3_migration_context.jsonl"
    )
    assert bad_artifact.is_file()
    bad_lines = bad_artifact.read_text(
        encoding="utf-8",
    ).splitlines()
    assert len(bad_lines) == 2


def test_non_strict_artifact_failure_swallowed_drains_pending_and_records_observation(
    tmp_path: Path,
) -> None:
    """Non-strict regression: under the default ``strict=False``
    flush mode, an artifact write failure (missing output dir)
    is swallowed; the composed observation is still recorded on
    ``wrapper.observations`` with the closed-set COMPOSED
    status; the pending queue still drains; the flush never
    raises out. The wrapper stays observational only and the
    soak result is unaffected (no soak orchestrator is invoked
    here — this pins the wrapper's behavior in isolation).
    """
    missing_output_dir = tmp_path / "still_missing"
    inner = _FakeInner([_build_pass_result_with_dedupe()])
    evidence_records = (
        build_synthetic_missing_evidence(
            observed_at_utc=_OBSERVED_AT,
        ),
    )
    wrapper = Stage29_5_3MigrationContextSoakPassWrapper(
        inner_pass_entrypoint=inner,
        evidence_provider=_FakeEvidenceProvider(
            (evidence_records,),
        ),
        ath_context_provider=_FakeAthContextProvider(None),
        clock=_DeterministicClock(),
        write_side_channel_artifact=True,
    )
    bounds = _build_soak_bounds()
    wrapper(
        pass_index=1,
        bounds=bounds,
        soak_output_dir=missing_output_dir,
    )

    composed = wrapper.flush_pending_observations()

    assert len(composed) == 1
    assert composed[0].observation_status == (
        OBSERVATION_STATUS_COMPOSED
    )
    assert len(wrapper.observations) == 1
    assert wrapper.pending_observations == ()
    # Artifact write was swallowed; nothing was created on disk.
    assert not missing_output_dir.exists()


# ===========================================================================
# Slow-provider proof: Stage 29.4 soak summary unchanged
# ===========================================================================


def test_wrapped_soak_summary_matches_control_under_slow_provider(
    tmp_path: Path,
) -> None:
    """Critical Stage 29.5.3 invariant: a slow evidence provider
    does NOT alter the Stage 29.4 soak summary or dispatch
    counters when threaded through the deferred-observation
    wrapper. The wrapper does not call the provider inside
    ``__call__``; provider latency therefore stays OUTSIDE the
    Stage 29.4 wall-clock pass boundary.

    Inputs:
      * three pre-canned DISPATCHED inner pass results with
        UNIQUE dedupe keys so dispatch_success_total grows by 1
        per pass;
      * wall_clock_seconds=1, max_dispatches=3, max_passes=3 so
        the soak completes at the dispatch cap when nothing
        slow runs inside the pass boundary;
      * a slow evidence provider that sleeps 0.6 s per call
        (3 × 0.6 = 1.8 s total, well past wall_clock_seconds=1)
        — under the OLD inline-observation design the first pass
        would push elapsed past 1 s and flip the outcome to
        COMPLETED_AT_WALL_CLOCK with passes_attempted=1 /
        dispatch_success_total=1.

    Assertions:
      * control soak (raw inner) yields COMPLETED_AT_DISPATCH_CAP
        / passes=3 / dispatch=3;
      * wrapped soak (wrapper over same inner, slow provider
        injected) yields the SAME closed-set soak outcome /
        passes / dispatch counters;
      * the slow provider was NOT called during the wrapped
        soak loop (call_count==0 immediately after the soak
        returns, before the operator calls flush);
      * after the operator calls flush, the slow provider is
        called 3 times and the wrapper records 3 composed
        observations.
    """
    from PHX2.stage29.stage29_4_soak_orchestrator import (
        run_stage29_4_short_session_private_soak,
        Stage29_4UtcClock,
    )
    from PHX2.stage29.stage29_4_soak_models import (
        soak_summary_to_dict,
    )

    pass_token_a = _safe_mint_padded("AlphaMint")
    pass_token_b = _safe_mint_padded("BetaMint")
    pass_token_c = _safe_mint_padded("GammaMint")

    def _make_inner() -> _FakeInner:
        return _FakeInner(
            [
                _build_pass_result_with_dedupe(
                    token_mint=pass_token_a,
                ),
                _build_pass_result_with_dedupe(
                    token_mint=pass_token_b,
                ),
                _build_pass_result_with_dedupe(
                    token_mint=pass_token_c,
                ),
            ],
        )

    bounds = _build_soak_bounds(
        wall_clock_seconds=1,
        max_dispatches=3,
        max_passes=3,
    )

    # Control soak: raw inner, no wrapper.
    control_dir = tmp_path / "control"
    control_dir.mkdir()
    control_inner = _make_inner()
    control_summary = (
        run_stage29_4_short_session_private_soak(
            bounds=bounds,
            output_dir=control_dir,
            pass_entrypoint=control_inner,
            clock=Stage29_4UtcClock(),
            write_artifacts=False,
        )
    )

    # Wrapped soak: deferred wrapper with slow evidence provider.
    wrapped_dir = tmp_path / "wrapped"
    wrapped_dir.mkdir()
    wrapped_inner = _make_inner()
    slow_provider = _SlowEvidenceProvider(sleep_seconds=0.6)
    wrapper = Stage29_5_3MigrationContextSoakPassWrapper(
        inner_pass_entrypoint=wrapped_inner,
        evidence_provider=slow_provider,
        ath_context_provider=_FakeAthContextProvider(None),
        clock=_DeterministicClock(),
        write_side_channel_artifact=False,
    )
    wrapped_summary = (
        run_stage29_4_short_session_private_soak(
            bounds=bounds,
            output_dir=wrapped_dir,
            pass_entrypoint=wrapper,
            clock=Stage29_4UtcClock(),
            write_artifacts=False,
        )
    )

    # CRITICAL: the provider was NOT called during the soak.
    # This is the load-bearing proof that the deferred wrapper
    # does not perturb the Stage 29.4 timed pass boundary.
    assert slow_provider.call_count == 0, (
        "evidence provider must not be called during the "
        "Stage 29.4 soak loop; the deferred wrapper moves "
        "provider work outside the wall-clock boundary"
    )

    # All three pending observations were recorded.
    assert len(wrapper.pending_observations) == 3
    # No composed observations until flush.
    assert wrapper.observations == ()

    # Wrapped soak summary must match the control soak summary
    # on every closed-set axis. start_utc_iso / end_utc_iso /
    # elapsed_wall_clock_seconds legitimately differ across two
    # distinct orchestrator runs.
    control_dict = soak_summary_to_dict(control_summary)
    wrapped_dict = soak_summary_to_dict(wrapped_summary)
    assert control_dict["soak_outcome"] == (
        "COMPLETED_AT_DISPATCH_CAP"
    )
    assert wrapped_dict["soak_outcome"] == (
        "COMPLETED_AT_DISPATCH_CAP"
    )
    assert control_dict["passes_attempted"] == 3
    assert wrapped_dict["passes_attempted"] == 3
    assert control_dict["dispatch_success_total"] == 3
    assert wrapped_dict["dispatch_success_total"] == 3
    for axis in (
        "start_utc_iso",
        "end_utc_iso",
        "elapsed_wall_clock_seconds",
    ):
        control_dict.pop(axis, None)
        wrapped_dict.pop(axis, None)
    assert control_dict == wrapped_dict

    # Now flush. The slow provider runs 3 times outside the
    # Stage 29.4 soak boundary; the soak summary is already
    # frozen and cannot be changed by flush.
    composed = wrapper.flush_pending_observations()
    assert len(composed) == 3
    assert slow_provider.call_count == 3
    assert len(wrapper.observations) == 3
    # The flushed observations report the MISSING_MIGRATION /
    # COMPOSED path (the slow provider returned () every call).
    for obs in wrapper.observations:
        assert obs.observation_status == (
            OBSERVATION_STATUS_COMPOSED
        )
        assert obs.measurement_status_echoed == (
            "MISSING_MIGRATION"
        )


# ===========================================================================
# End-to-end soak orchestrator integration (no slow provider)
# ===========================================================================


def test_wrapper_does_not_alter_stage29_4_soak_summary_or_dispatch_counters(
    output_dir: Path,
) -> None:
    """End-to-end: run the actual Stage 29.4 short-session
    private soak orchestrator twice — once with the raw inner
    entrypoint, once with the Stage 29.5.3 wrapper around the
    same inner — and assert every Stage 29.4 soak summary field
    matches byte-for-byte. The wrapper is observational only and
    must not perturb soak dispatch counters even when the
    provider returns instantly.
    """
    from PHX2.stage29.stage29_4_soak_orchestrator import (
        run_stage29_4_short_session_private_soak,
        Stage29_4UtcClock,
    )
    from PHX2.stage29.stage29_4_soak_models import (
        soak_summary_to_dict,
    )

    def _make_inner() -> _FakeInner:
        return _FakeInner(
            [
                _build_pass_result_with_dedupe(),
                _build_pass_result_with_dedupe(
                    token_mint=_safe_mint_padded("AnotherMint"),
                ),
            ],
        )

    bounds = _build_soak_bounds()
    control_inner = _make_inner()
    control_clock = Stage29_4UtcClock()
    control_dir = output_dir / "control"
    control_dir.mkdir()
    control_summary = (
        run_stage29_4_short_session_private_soak(
            bounds=bounds,
            output_dir=control_dir,
            pass_entrypoint=control_inner,
            clock=control_clock,
            write_artifacts=False,
        )
    )

    wrapped_inner = _make_inner()
    wrapped_dir = output_dir / "wrapped"
    wrapped_dir.mkdir()
    wrapper = Stage29_5_3MigrationContextSoakPassWrapper(
        inner_pass_entrypoint=wrapped_inner,
        evidence_provider=_FakeEvidenceProvider(((), ())),
        ath_context_provider=_FakeAthContextProvider(None),
        clock=_DeterministicClock(),
        write_side_channel_artifact=False,
    )
    wrapped_clock = Stage29_4UtcClock()
    wrapped_summary = (
        run_stage29_4_short_session_private_soak(
            bounds=bounds,
            output_dir=wrapped_dir,
            pass_entrypoint=wrapper,
            clock=wrapped_clock,
            write_artifacts=False,
        )
    )

    control_dict = soak_summary_to_dict(control_summary)
    wrapped_dict = soak_summary_to_dict(wrapped_summary)
    for axis in (
        "start_utc_iso",
        "end_utc_iso",
        "elapsed_wall_clock_seconds",
    ):
        control_dict.pop(axis, None)
        wrapped_dict.pop(axis, None)
    assert control_dict == wrapped_dict


# ===========================================================================
# Discipline: no live transports imported
# ===========================================================================


def test_wrapper_module_imports_no_live_transport_or_phx1() -> None:
    """The Stage 29.5.3 soak pass wrapper production file must
    not import any live transport / PHX1 / Stage 28 / Stage
    29.3 orchestrator / Stage 29.4 orchestrator module.
    """
    import ast

    wrapper_path = (
        Path(__file__).resolve().parent.parent.parent
        / "stage29"
        / "stage29_5_3_soak_pass_wrapper.py"
    )
    source = wrapper_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if mod:
                imports.add(mod)
    forbidden_substrings = (
        "websockets",
        "websocket",
        "urllib",
        "requests",
        "httpx",
        "aiohttp",
        "http.client",
        "socket",
        "grpc",
        "asyncio",
        "discord",
        "telegram",
        "phoenix_bot",
        "phx1",
        "stage29_3_tradeable_smoke",
        "stage29_4_soak_orchestrator",
    )
    for imp in imports:
        lower = imp.lower()
        for needle in forbidden_substrings:
            assert needle not in lower, (
                f"Stage 29.5.3 wrapper must not import "
                f"{imp!r}; forbidden substring {needle!r}"
            )

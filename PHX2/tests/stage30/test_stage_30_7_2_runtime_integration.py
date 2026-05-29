"""Stage 30.7.2 compact ATH runtime integration tests.

Drives the full Stage 30.4.2 opt-in parallel compact runtime session
orchestrator with an opt-in Stage 30.7.2 ``ath_context_resolver`` (built
from fake / offline Stage 30.7.1 ATH evidence) and asserts the FINAL
dispatched compact body carries the resolved ``ATH`` token:

  * KNOWN / PRESENT / USD / observed-market-cap -> ``ATH: $120k``
  * price-derived evidence                       -> ``ATH: Unknown``
  * redaction-unsafe evidence                    -> ``ATH: Unknown``
  * non-PRESENT (UNAVAILABLE) source             -> ``ATH: Unknown``
  * resolver raises                              -> ``ATH: Unknown``
  * off-shape resolver word (``"Stale"`` / junk) -> ``ATH: Unknown``
                                                    (local shape guard)
  * valid ``$Y`` from a throwaway resolver       -> renders through
  * no resolver supplied                         -> ``ATH: Unknown``
                                                    (backward compatible)

The headline proof composes all three offline seams (Stage 30.4.2 MC /
LP, Stage 30.5.2 migration, Stage 30.7.2 ATH) so the dispatched body
carries ``• MC: $83k | ATH: $120k | Mig: Known``. The ATH wiring only
fills the existing Stage 30.2 ``ath_mc_text`` slot, so the compact
renderer + models are untouched, the MC / LP enrichment is preserved,
and Net stays Unknown.

The heavy Stage 27 / Stage 28.9 / Stage 30.3 fakes + builders are
imported from the Stage 30.4.2 integration test module so this slice
reuses the proven offline scaffolding verbatim. No env reads. No
network. No real provider. No real Discord. Stdlib + pytest only.
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from typing import Iterator, Optional, Tuple

import pytest

from PHX2.stage28.live_provider_session_models import SESSION_OUTCOME_OK
from PHX2.stage30.stage30_3_compact_runtime_models import (
    WRAPPER_ORDER_LABEL_FAKE_INNER_TRANSPORT,
    WRAPPER_ORDER_LABEL_STAGE28_9_PRIVATE_WEBHOOK,
    WRAPPER_ORDER_LABEL_STAGE30_3_COMPACT_BODY,
)
from PHX2.stage30.stage30_4_compact_runtime_session_orchestrator import (
    Stage30_4_2CompactRuntimeSessionResult,
    run_stage30_4_2_compact_runtime_session,
)
from PHX2.stage30.stage30_5_compact_migration_runtime_adapter import (
    Stage30_5_2MigrationDisplayResolver,
)
from PHX2.stage30.stage30_5_migration_context_models import (
    MIGRATION_BASIS_ON_CHAIN_EVENT,
    MIGRATION_STATUS_KNOWN,
    SOURCE_REASON_SOURCE_PRESENT,
    SOURCE_STATUS_PRESENT,
    STAGE30_5_1_MIGRATION_CONTEXT_SCHEMA_VERSION,
    Stage30_5MigrationContextRecord,
)
from PHX2.stage30.stage30_7_ath_context_models import (
    ATH_BASIS_MARKET_CAP_OBSERVED,
    ATH_BASIS_PRICE_DERIVED,
    ATH_SOURCE_STATUS_PRESENT,
    ATH_SOURCE_STATUS_UNAVAILABLE,
    ATH_UNIT_USD,
    Stage30_7AthContextEvidence,
)
from PHX2.stage30.stage30_7_compact_ath_runtime_adapter import (
    Stage30_7_2AthDisplayResolver,
)

# Reuse the proven Stage 30.4.2 offline scaffolding verbatim.
from PHX2.tests.stage30.test_stage_30_4_2_compact_runtime_integration import (
    _CLOCK_TS,
    _FAKE_WEBHOOK_URL,
    _PHOENIX_PREFIX,
    _FakeClock,
    _FakeInnerCandidateAssembler,
    _FakeProviderEventSource,
    _FakeStage30_4MarketContextSource,
    _RecordingInnerTransport,
    _build_fake_reading_mc_lp,
    _build_stage27_6_record,
    _make_fake_event,
    _make_runtime_context,
    _make_session_config,
)


_VERBOSE_HEADER_MARKER: str = "PHX2 STAGE 28.9 PRIVATE OPERATOR PING"


@pytest.fixture
def out_of_repo_tmp_path() -> Iterator[Path]:
    base = tempfile.mkdtemp(prefix="phx2_stage30_7_2_test_")
    try:
        yield Path(base)
    finally:
        shutil.rmtree(base, ignore_errors=True)


# ---------------------------------------------------------------------------
# Fakes / builders
# ---------------------------------------------------------------------------


def _ath_evidence(
    *,
    ath_value: object = 120000,
    ath_unit: object = ATH_UNIT_USD,
    source_status: object = ATH_SOURCE_STATUS_PRESENT,
    basis: object = ATH_BASIS_MARKET_CAP_OBSERVED,
    redaction_safe: bool = True,
) -> Stage30_7AthContextEvidence:
    return Stage30_7AthContextEvidence(
        ath_value=ath_value,
        ath_unit=ath_unit,
        source_status=source_status,
        basis=basis,
        redaction_safe=redaction_safe,
    )


def _ath_resolver(evidence: object) -> Stage30_7_2AthDisplayResolver:
    return Stage30_7_2AthDisplayResolver(evidence=evidence)


class _StaticAthResolver:
    """Throwaway duck-typed resolver that returns a caller-supplied raw
    value from ``resolve_display_text``, BYPASSING the official Stage
    30.7.2 projection adapter.

    Used to prove the Stage 30.4.2 runtime seam enforces its OWN local
    shape guard: an adversarial / buggy resolver that returns an off-shape
    value (e.g. ``"Stale"`` / a fabricated estimate / a non-string) must
    NOT reach the compact body.
    """

    def __init__(self, *, value: object) -> None:
        self._value = value

    def resolve_display_text(
        self,
        *,
        token_mint: object,
        observed_at_utc: Optional[str] = None,
    ) -> object:
        return self._value


class _RaisingAthResolver:
    """Throwaway resolver whose ``resolve_display_text`` raises."""

    def resolve_display_text(
        self,
        *,
        token_mint: object,
        observed_at_utc: Optional[str] = None,
    ) -> object:
        raise RuntimeError("fake ATH resolver failure")


def _known_migration_resolver() -> Stage30_5_2MigrationDisplayResolver:
    """A real Stage 30.5.2 resolver that resolves to ``Mig: Known`` so the
    headline proof composes the migration seam with the ATH seam.
    """
    record = Stage30_5MigrationContextRecord(
        schema_version=STAGE30_5_1_MIGRATION_CONTEXT_SCHEMA_VERSION,
        token_label=None,
        migration_status=MIGRATION_STATUS_KNOWN,
        migration_basis=MIGRATION_BASIS_ON_CHAIN_EVENT,
        migration_event_time_utc=None,
        migration_age_seconds=None,
        source_label="stage30_7_2_fake_migration",
        source_status=SOURCE_STATUS_PRESENT,
        source_reason=SOURCE_REASON_SOURCE_PRESENT,
        runtime_consumable=False,
        observed_at_utc=_CLOCK_TS,
    )
    return Stage30_5_2MigrationDisplayResolver(
        source=_FakeMigrationSource(record=record),
    )


class _FakeMigrationSource:
    """Stage 30.5.1 source-protocol-compatible fake migration source."""

    def __init__(
        self,
        *,
        record: Optional[Stage30_5MigrationContextRecord] = None,
    ) -> None:
        self._record = record

    def read(
        self,
        token_mint: str,
        observed_at_utc: Optional[str] = None,
    ) -> Optional[Stage30_5MigrationContextRecord]:
        return self._record


def _market_source_with_mc_lp() -> _FakeStage30_4MarketContextSource:
    return _FakeStage30_4MarketContextSource(
        reading=_build_fake_reading_mc_lp(
            mc_value="83000",
            lp_value="27000",
            net_value=None,
        ),
    )


def _run_session(
    *,
    tmp_path: Path,
    ath_context_resolver: Optional[object],
    migration_context_resolver: Optional[object] = None,
    market_context_source: Optional[object],
) -> Tuple[Stage30_4_2CompactRuntimeSessionResult, str]:
    """Drive one full Stage 30.4.2 session with the supplied ATH resolver
    (+ optional migration resolver + market source) and return
    ``(result, dispatched_body_text)``.
    """
    config = _make_session_config(max_events=1, max_dispatches=1)
    source = _FakeProviderEventSource(events=(_make_fake_event(0),))
    inner_assembler = _FakeInnerCandidateAssembler(
        records=(_build_stage27_6_record(),),
    )
    inner_transport = _RecordingInnerTransport()
    wrapper_order = (
        WRAPPER_ORDER_LABEL_STAGE30_3_COMPACT_BODY,
        WRAPPER_ORDER_LABEL_STAGE28_9_PRIVATE_WEBHOOK,
        WRAPPER_ORDER_LABEL_FAKE_INNER_TRANSPORT,
    )
    context = _make_runtime_context(tmp_path=tmp_path)
    clock = _FakeClock(stamps=(_CLOCK_TS,) * 16)

    result = run_stage30_4_2_compact_runtime_session(
        session_config=config,
        provider_event_source=source,
        inner_candidate_assembler=inner_assembler,
        inner_transport=inner_transport,
        output_dir=tmp_path,
        private_webhook_url=_FAKE_WEBHOOK_URL,
        live_env_ready=True,
        live_operator_request=True,
        compact_runtime_context=context,
        clock=clock,
        wrapper_order=wrapper_order,
        market_context_source=market_context_source,
        migration_context_resolver=migration_context_resolver,
        ath_context_resolver=ath_context_resolver,
    )

    assert isinstance(result, Stage30_4_2CompactRuntimeSessionResult)
    assert inner_transport.call_count == 1
    dispatched_payload = inner_transport.received_kwargs[0]["payload"]
    return result, dispatched_payload["content"]


def _assert_common_compact_shape(body: str) -> None:
    assert body.startswith(_PHOENIX_PREFIX)
    assert _VERBOSE_HEADER_MARKER not in body
    # The Stage 30.4.2 MC / LP enrichment is preserved; Net stays Unknown
    # (Stage 30.7.2 introduces no Net field). ATH + Mig vary per test.
    assert "MC: $83k" in body
    assert "LP: $27k" in body
    assert "Net: Unknown" in body
    assert "Basis: price-basis" in body


# ---------------------------------------------------------------------------
# 1. The Stage 30.7.2 goal proof: MC + ATH + Mig all populated
# ---------------------------------------------------------------------------


def test_known_ath_renders_dollar_value_with_mc_and_mig(
    out_of_repo_tmp_path: Path,
) -> None:
    result, body = _run_session(
        tmp_path=out_of_repo_tmp_path,
        ath_context_resolver=_ath_resolver(_ath_evidence()),
        migration_context_resolver=_known_migration_resolver(),
        market_context_source=_market_source_with_mc_lp(),
    )

    assert result.inner_stage30_3_result.session_result.session_outcome == (
        SESSION_OUTCOME_OK
    )
    assert result.market_context_replacements_succeeded == 1
    _assert_common_compact_shape(body)
    # • MC: $83k | ATH: $120k | Mig: Known
    assert "ATH: $120k" in body
    assert "MC: $83k | ATH: $120k | Mig: Known" in body
    assert "• MC: $83k | ATH: $120k | Mig: Known" in body
    assert "ATH: Unknown" not in body


# ---------------------------------------------------------------------------
# 2. Degraded ATH evidence -> ATH: Unknown (projection fail-closed)
# ---------------------------------------------------------------------------


def test_price_derived_ath_renders_unknown(
    out_of_repo_tmp_path: Path,
) -> None:
    _result, body = _run_session(
        tmp_path=out_of_repo_tmp_path,
        ath_context_resolver=_ath_resolver(
            _ath_evidence(basis=ATH_BASIS_PRICE_DERIVED)
        ),
        market_context_source=_market_source_with_mc_lp(),
    )
    _assert_common_compact_shape(body)
    assert "ATH: Unknown" in body
    assert "ATH: $120k" not in body


def test_redaction_unsafe_ath_renders_unknown(
    out_of_repo_tmp_path: Path,
) -> None:
    _result, body = _run_session(
        tmp_path=out_of_repo_tmp_path,
        ath_context_resolver=_ath_resolver(
            _ath_evidence(redaction_safe=False)
        ),
        market_context_source=_market_source_with_mc_lp(),
    )
    _assert_common_compact_shape(body)
    assert "ATH: Unknown" in body


def test_non_present_source_ath_renders_unknown(
    out_of_repo_tmp_path: Path,
) -> None:
    _result, body = _run_session(
        tmp_path=out_of_repo_tmp_path,
        ath_context_resolver=_ath_resolver(
            _ath_evidence(source_status=ATH_SOURCE_STATUS_UNAVAILABLE)
        ),
        market_context_source=_market_source_with_mc_lp(),
    )
    _assert_common_compact_shape(body)
    assert "ATH: Unknown" in body


# ---------------------------------------------------------------------------
# 3. Resolver raises -> ATH: Unknown (fail closed, runtime does not crash)
# ---------------------------------------------------------------------------


def test_resolver_raises_renders_ath_unknown(
    out_of_repo_tmp_path: Path,
) -> None:
    result, body = _run_session(
        tmp_path=out_of_repo_tmp_path,
        ath_context_resolver=_RaisingAthResolver(),
        market_context_source=_market_source_with_mc_lp(),
    )
    # The replacement still succeeds (MC / LP enrich); only the ATH token
    # falls back to Unknown.
    assert result.market_context_replacements_succeeded == 1
    _assert_common_compact_shape(body)
    assert "ATH: Unknown" in body
    assert "ATH: $120k" not in body


# ---------------------------------------------------------------------------
# 4. Local shape guard: off-shape resolver output -> ATH: Unknown
# ---------------------------------------------------------------------------


def test_resolver_returning_stale_renders_ath_unknown(
    out_of_repo_tmp_path: Path,
) -> None:
    """A throwaway resolver returning ``"Stale"`` must render
    ``ATH: Unknown`` -- never ``ATH: Stale``.
    """
    _result, body = _run_session(
        tmp_path=out_of_repo_tmp_path,
        ath_context_resolver=_StaticAthResolver(value="Stale"),
        market_context_source=_market_source_with_mc_lp(),
    )
    _assert_common_compact_shape(body)
    assert "ATH: Unknown" in body
    assert "ATH: Stale" not in body


def test_resolver_returning_arbitrary_string_renders_ath_unknown(
    out_of_repo_tmp_path: Path,
) -> None:
    """An arbitrary off-shape string (a fabricated estimate) is rejected
    by the local shape guard; the body keeps ``ATH: Unknown``.
    """
    _result, body = _run_session(
        tmp_path=out_of_repo_tmp_path,
        ath_context_resolver=_StaticAthResolver(
            value="probably like 500k trust me",
        ),
        market_context_source=_market_source_with_mc_lp(),
    )
    _assert_common_compact_shape(body)
    assert "ATH: Unknown" in body
    assert "probably like 500k trust me" not in body


@pytest.mark.parametrize(
    "bad_value",
    ["", "   ", " $120k ", "$", "$.5k", "$1.", "120k", "$120K", 120000, None, ["$120k"]],
)
def test_resolver_returning_off_shape_value_renders_ath_unknown(
    out_of_repo_tmp_path: Path,
    bad_value: object,
) -> None:
    """Empty / whitespace / malformed-money / non-string resolver output
    is rejected by the local shape guard; the body keeps ``ATH: Unknown``.
    """
    _result, body = _run_session(
        tmp_path=out_of_repo_tmp_path,
        ath_context_resolver=_StaticAthResolver(value=bad_value),
        market_context_source=_market_source_with_mc_lp(),
    )
    _assert_common_compact_shape(body)
    assert "ATH: Unknown" in body


@pytest.mark.parametrize(
    "good_value",
    ["$27", "$999", "$1k", "$83k", "$120k", "$12.3k", "$1M", "$1.2M", "Unknown"],
)
def test_resolver_returning_valid_shape_renders_through(
    out_of_repo_tmp_path: Path,
    good_value: str,
) -> None:
    """The two safe Stage 30.7.1 ATH display shapes (a ``$Y`` money token
    or the literal ``Unknown``) are accepted verbatim by the runtime seam
    guard and reach the compact body ``ATH`` token.
    """
    _result, body = _run_session(
        tmp_path=out_of_repo_tmp_path,
        ath_context_resolver=_StaticAthResolver(value=good_value),
        market_context_source=_market_source_with_mc_lp(),
    )
    _assert_common_compact_shape(body)
    assert f"ATH: {good_value}" in body


# ---------------------------------------------------------------------------
# 5. No resolver supplied -> ATH: Unknown (backward compatible baseline)
# ---------------------------------------------------------------------------


def test_no_ath_resolver_is_backward_compatible_ath_unknown(
    out_of_repo_tmp_path: Path,
) -> None:
    """With no ``ath_context_resolver``, the Stage 30.4.2 runtime behaves
    exactly as before: MC / LP enrich, ATH stays Unknown, and the
    replacement still succeeds.
    """
    result, body = _run_session(
        tmp_path=out_of_repo_tmp_path,
        ath_context_resolver=None,
        market_context_source=_market_source_with_mc_lp(),
    )
    assert result.inner_stage30_3_result.session_result.session_outcome == (
        SESSION_OUTCOME_OK
    )
    assert result.market_context_replacements_attempted == 1
    assert result.market_context_replacements_succeeded == 1
    assert result.market_context_replacements_failed == 0
    _assert_common_compact_shape(body)
    assert "ATH: Unknown" in body
    assert "ATH: $120k" not in body
    # No resolver supplied -> Mig also stays Unknown (no migration
    # resolver), so the default compact body line is preserved.
    assert "Mig: Unknown" in body

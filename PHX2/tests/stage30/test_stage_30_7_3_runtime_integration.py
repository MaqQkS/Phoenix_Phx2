"""Stage 30.7.3 sanitized-ATH-bridge compact runtime integration tests.

Drives the full Stage 30.4.2 opt-in parallel compact runtime session
orchestrator with a Stage 30.7.3 ``ath_context_resolver`` built BY THE
BRIDGE from a sanitized upstream ATH-evidence shape, and asserts the FINAL
dispatched compact body carries the resolved ``ATH`` token:

  * KNOWN observed-market-cap USD shape -> ``ATH: $120k``
  * price-derived shape                 -> ``ATH: Unknown``
  * redaction-unsafe shape              -> ``ATH: Unknown``
  * non-PRESENT (UNAVAILABLE / SOURCE_ERROR / STALE / CONFLICTING) -> Unknown
  * USDC unit shape                     -> ``ATH: Unknown``
  * None / realistic Stage 27 price ATH -> ``ATH: Unknown``
  * dict-like KNOWN shape               -> ``ATH: $120k``
  * no resolver supplied                -> ``ATH: Unknown`` (backward compat)

The headline proof composes all three offline seams (Stage 30.4.2 MC / LP,
a Stage-30.5.2-shaped migration resolver, the Stage 30.7.3 bridge ATH
resolver) so the dispatched body carries
``• MC: $83k | ATH: $120k | Mig: Known``. The bridge resolver fills ONLY the
existing Stage 30.2 ``ath_mc_text`` slot through the Stage 30.7.2
``ath_context_resolver`` seam (no orchestrator edit), so the compact
renderer + models are untouched, the MC / LP enrichment is preserved, and
Net stays Unknown.

The heavy Stage 27 / Stage 28.9 / Stage 30.3 fakes + builders are imported
from the Stage 30.4.2 integration test module so this slice reuses the
proven offline scaffolding verbatim. No env reads. No network. No real
provider. No real Discord. Stdlib + pytest only.
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
from PHX2.stage30.stage30_7_sanitized_ath_bridge import (
    Stage30_7_3SanitizedUpstreamAthEvidence,
    build_stage30_ath_resolver_from_sanitized_evidence,
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
    base = tempfile.mkdtemp(prefix="phx2_stage30_7_3_test_")
    try:
        yield Path(base)
    finally:
        shutil.rmtree(base, ignore_errors=True)


# ---------------------------------------------------------------------------
# Fakes / builders
# ---------------------------------------------------------------------------


def _sanitized_evidence(
    **overrides: object,
) -> Stage30_7_3SanitizedUpstreamAthEvidence:
    base = dict(
        ath_value=120000,
        ath_unit="USD",
        source_status="PRESENT",
        basis="ATH_MARKET_CAP_OBSERVED",
        redaction_safe=True,
    )
    base.update(overrides)
    return Stage30_7_3SanitizedUpstreamAthEvidence(**base)  # type: ignore[arg-type]


def _ath_resolver_from(evidence: object) -> object:
    return build_stage30_ath_resolver_from_sanitized_evidence(
        raw_evidence=evidence,
    )


class _StaticKnownMigrationResolver:
    """A self-contained duck-typed migration resolver that resolves to
    ``Mig: Known`` so the headline proof composes the migration seam with
    the ATH seam, WITHOUT importing any Stage 30.5 module.

    The Stage 30.4.2 migration seam accepts only the closed-set words
    ``Known`` / ``Unverified`` / ``Unknown``; this returns ``Known``.
    """

    def resolve_display_text(
        self,
        *,
        token_mint: object,
        observed_at_utc: Optional[str] = None,
    ) -> str:
        return "Known"


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
    # (Stage 30.7.3 introduces no Net field). ATH + Mig vary per test.
    assert "MC: $83k" in body
    assert "LP: $27k" in body
    assert "Net: Unknown" in body
    assert "Basis: price-basis" in body


# ---------------------------------------------------------------------------
# 1. The Stage 30.7.3 goal proof: MC + ATH + Mig all populated via the bridge
# ---------------------------------------------------------------------------


def test_bridge_known_ath_renders_dollar_value_with_mc_and_mig(
    out_of_repo_tmp_path: Path,
) -> None:
    result, body = _run_session(
        tmp_path=out_of_repo_tmp_path,
        ath_context_resolver=_ath_resolver_from(_sanitized_evidence()),
        migration_context_resolver=_StaticKnownMigrationResolver(),
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


def test_bridge_dict_like_known_ath_renders_dollar_value(
    out_of_repo_tmp_path: Path,
) -> None:
    d = {
        "ath_value": 120000,
        "ath_unit": "USD",
        "source_status": "PRESENT",
        "basis": "ATH_MARKET_CAP_OBSERVED",
        "redaction_safe": True,
    }
    _result, body = _run_session(
        tmp_path=out_of_repo_tmp_path,
        ath_context_resolver=_ath_resolver_from(d),
        market_context_source=_market_source_with_mc_lp(),
    )
    _assert_common_compact_shape(body)
    assert "ATH: $120k" in body


# ---------------------------------------------------------------------------
# 2. Degraded sanitized evidence -> ATH: Unknown (bridge / projection fail-closed)
# ---------------------------------------------------------------------------


def test_bridge_price_derived_renders_ath_unknown(
    out_of_repo_tmp_path: Path,
) -> None:
    _result, body = _run_session(
        tmp_path=out_of_repo_tmp_path,
        ath_context_resolver=_ath_resolver_from(
            _sanitized_evidence(basis="ATH_PRICE_DERIVED")
        ),
        market_context_source=_market_source_with_mc_lp(),
    )
    _assert_common_compact_shape(body)
    assert "ATH: Unknown" in body
    assert "ATH: $120k" not in body


def test_bridge_redaction_unsafe_renders_ath_unknown(
    out_of_repo_tmp_path: Path,
) -> None:
    _result, body = _run_session(
        tmp_path=out_of_repo_tmp_path,
        ath_context_resolver=_ath_resolver_from(
            _sanitized_evidence(redaction_safe=False)
        ),
        market_context_source=_market_source_with_mc_lp(),
    )
    _assert_common_compact_shape(body)
    assert "ATH: Unknown" in body


@pytest.mark.parametrize(
    "status",
    ["UNAVAILABLE", "SOURCE_ERROR", "ERROR", "STALE", "CONFLICTING"],
)
def test_bridge_non_present_source_renders_ath_unknown(
    out_of_repo_tmp_path: Path,
    status: str,
) -> None:
    _result, body = _run_session(
        tmp_path=out_of_repo_tmp_path,
        ath_context_resolver=_ath_resolver_from(
            _sanitized_evidence(source_status=status)
        ),
        market_context_source=_market_source_with_mc_lp(),
    )
    _assert_common_compact_shape(body)
    assert "ATH: Unknown" in body
    assert "ATH: $120k" not in body


def test_bridge_usdc_unit_renders_ath_unknown(
    out_of_repo_tmp_path: Path,
) -> None:
    _result, body = _run_session(
        tmp_path=out_of_repo_tmp_path,
        ath_context_resolver=_ath_resolver_from(
            _sanitized_evidence(ath_unit="USDC")
        ),
        market_context_source=_market_source_with_mc_lp(),
    )
    _assert_common_compact_shape(body)
    assert "ATH: Unknown" in body


def test_bridge_none_evidence_renders_ath_unknown(
    out_of_repo_tmp_path: Path,
) -> None:
    _result, body = _run_session(
        tmp_path=out_of_repo_tmp_path,
        ath_context_resolver=_ath_resolver_from(None),
        market_context_source=_market_source_with_mc_lp(),
    )
    _assert_common_compact_shape(body)
    assert "ATH: Unknown" in body


def test_bridge_realistic_stage27_price_ath_renders_ath_unknown(
    out_of_repo_tmp_path: Path,
) -> None:
    # A sanitized copy of a real Stage 27.4 ATH context record (a PRESENT
    # price ATH with a drawdown_basis, NOT an observed market cap) is
    # honestly degraded to ATH: Unknown. Built as a plain dict so this test
    # imports no Stage 27 module.
    artifact = {
        "ath_value": "0.00012345",
        "ath_unit": "USD",
        "ath_status": "PRESENT",
        "drawdown_basis": "FROM_POST_MIGRATION_ATH",
        "redaction_safe": True,
    }
    _result, body = _run_session(
        tmp_path=out_of_repo_tmp_path,
        ath_context_resolver=_ath_resolver_from(artifact),
        market_context_source=_market_source_with_mc_lp(),
    )
    _assert_common_compact_shape(body)
    assert "ATH: Unknown" in body
    assert "0.00012345" not in body


# ---------------------------------------------------------------------------
# 3. No resolver supplied -> ATH: Unknown (backward compatible baseline)
# ---------------------------------------------------------------------------


def test_no_ath_resolver_is_backward_compatible_ath_unknown(
    out_of_repo_tmp_path: Path,
) -> None:
    result, body = _run_session(
        tmp_path=out_of_repo_tmp_path,
        ath_context_resolver=None,
        market_context_source=_market_source_with_mc_lp(),
    )
    assert result.market_context_replacements_succeeded == 1
    _assert_common_compact_shape(body)
    assert "ATH: Unknown" in body
    assert "ATH: $120k" not in body
    # No migration resolver either -> Mig stays Unknown.
    assert "Mig: Unknown" in body

"""Stage 30.5.3 migration-bridge compact runtime integration tests.

Drives the full Stage 30.4.2 opt-in parallel compact runtime session
orchestrator with a Stage 30.5.3 resolver built BY THE BRIDGE from a
sanitized Stage 29.5 migration-evidence artifact, and asserts the FINAL
dispatched compact body carries the resolved ``Mig`` token:

  * COMPLETE artifact        -> ``Mig: Known``
  * PARTIAL artifact         -> ``Mig: Unverified``
  * MISSING artifact         -> ``Mig: Unknown``
  * INVALID artifact         -> ``Mig: Unknown``
  * CONFLICTING artifact     -> ``Mig: Unknown``
  * stale PARTIAL artifact   -> ``Mig: Unknown`` (no ``Mig: Stale``)
  * no artifact (None)       -> ``Mig: Unknown``
  * no resolver supplied     -> ``Mig: Unknown`` (Stage 30.4.2 baseline)

In every case the Stage 30.4.2 MC / LP enrichment is preserved, ATH stays
Unknown, and Net stays Unknown -- the bridge fills ONLY the existing Stage
30.2 ``migration_mc_text`` slot through the Stage 30.5.2 resolver seam, so
the compact renderer + models are untouched.

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
from PHX2.stage30.stage30_5_stage29_migration_bridge import (
    STAGE29_5_MEASUREMENT_STATUS_COMPLETE,
    STAGE29_5_MEASUREMENT_STATUS_CONFLICTING_MIGRATION,
    STAGE29_5_MEASUREMENT_STATUS_INVALID_MIGRATION,
    STAGE29_5_MEASUREMENT_STATUS_MISSING_MIGRATION,
    STAGE29_5_MEASUREMENT_STATUS_PARTIAL_MIGRATION_PRESENT,
    STAGE29_5_REDACTION_STATUS_SAFE,
    STAGE29_5_WARNING_MIGRATION_STALE,
    Stage30_5_3SanitizedStage29MigrationEvidence,
    build_stage30_migration_resolver_from_stage29_artifact,
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
    base = tempfile.mkdtemp(prefix="phx2_stage30_5_3_test_")
    try:
        yield Path(base)
    finally:
        shutil.rmtree(base, ignore_errors=True)


def _sanitized_artifact(
    measurement_status: Optional[str],
    *,
    warnings: tuple = (),
    redaction_status: Optional[str] = STAGE29_5_REDACTION_STATUS_SAFE,
) -> Stage30_5_3SanitizedStage29MigrationEvidence:
    return Stage30_5_3SanitizedStage29MigrationEvidence(
        measurement_status=measurement_status,
        warnings=warnings,
        redaction_status=redaction_status,
    )


def _resolver_from_artifact(evidence: object) -> object:
    return build_stage30_migration_resolver_from_stage29_artifact(
        evidence=evidence,
    )


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
    migration_context_resolver: Optional[object],
    market_context_source: Optional[object],
) -> Tuple[Stage30_4_2CompactRuntimeSessionResult, str]:
    """Drive one full Stage 30.4.2 session with the supplied resolver +
    market source and return ``(result, dispatched_body_text)``.
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
    )

    assert isinstance(result, Stage30_4_2CompactRuntimeSessionResult)
    assert inner_transport.call_count == 1
    dispatched_payload = inner_transport.received_kwargs[0]["payload"]
    return result, dispatched_payload["content"]


def _assert_common_compact_shape(body: str) -> None:
    assert body.startswith(_PHOENIX_PREFIX)
    assert _VERBOSE_HEADER_MARKER not in body
    # The Stage 30.4.2 MC / LP enrichment is preserved; ATH + Net stay
    # Unknown (Stage 30.5.3 introduces no ATH / Net field).
    assert "MC: $83k" in body
    assert "LP: $27k" in body
    assert "ATH: Unknown" in body
    assert "Net: Unknown" in body
    assert "Basis: price-basis" in body
    # No Mig: Stale / Mig: Fresh display word ever appears.
    assert "Mig: Stale" not in body
    assert "Mig: Fresh" not in body


# ---------------------------------------------------------------------------
# 1. Confirmed COMPLETE artifact -> Mig: Known (the Stage 30.5.3 goal proof)
# ---------------------------------------------------------------------------


def test_complete_artifact_renders_mig_known(
    out_of_repo_tmp_path: Path,
) -> None:
    resolver = _resolver_from_artifact(
        _sanitized_artifact(STAGE29_5_MEASUREMENT_STATUS_COMPLETE)
    )
    result, body = _run_session(
        tmp_path=out_of_repo_tmp_path,
        migration_context_resolver=resolver,
        market_context_source=_market_source_with_mc_lp(),
    )

    assert result.inner_stage30_3_result.session_result.session_outcome == (
        SESSION_OUTCOME_OK
    )
    assert result.market_context_replacements_succeeded == 1
    _assert_common_compact_shape(body)
    # • MC: $83k | ATH: Unknown | Mig: Known
    assert "Mig: Known" in body
    assert "MC: $83k | ATH: Unknown | Mig: Known" in body
    assert "Mig: Unknown" not in body


# ---------------------------------------------------------------------------
# 2. Partial artifact -> Mig: Unverified
# ---------------------------------------------------------------------------


def test_partial_artifact_renders_mig_unverified(
    out_of_repo_tmp_path: Path,
) -> None:
    resolver = _resolver_from_artifact(
        _sanitized_artifact(
            STAGE29_5_MEASUREMENT_STATUS_PARTIAL_MIGRATION_PRESENT
        )
    )
    _result, body = _run_session(
        tmp_path=out_of_repo_tmp_path,
        migration_context_resolver=resolver,
        market_context_source=_market_source_with_mc_lp(),
    )
    _assert_common_compact_shape(body)
    assert "Mig: Unverified" in body
    assert "Mig: Known" not in body
    assert "Mig: Unknown" not in body


# ---------------------------------------------------------------------------
# 3. Missing / invalid / conflicting / None / stale -> Mig: Unknown
# ---------------------------------------------------------------------------


def test_missing_artifact_renders_mig_unknown(
    out_of_repo_tmp_path: Path,
) -> None:
    resolver = _resolver_from_artifact(
        _sanitized_artifact(STAGE29_5_MEASUREMENT_STATUS_MISSING_MIGRATION)
    )
    _result, body = _run_session(
        tmp_path=out_of_repo_tmp_path,
        migration_context_resolver=resolver,
        market_context_source=_market_source_with_mc_lp(),
    )
    _assert_common_compact_shape(body)
    assert "Mig: Unknown" in body
    assert "Mig: Known" not in body
    assert "Mig: Unverified" not in body


def test_invalid_artifact_renders_mig_unknown(
    out_of_repo_tmp_path: Path,
) -> None:
    resolver = _resolver_from_artifact(
        _sanitized_artifact(STAGE29_5_MEASUREMENT_STATUS_INVALID_MIGRATION)
    )
    _result, body = _run_session(
        tmp_path=out_of_repo_tmp_path,
        migration_context_resolver=resolver,
        market_context_source=_market_source_with_mc_lp(),
    )
    _assert_common_compact_shape(body)
    assert "Mig: Unknown" in body
    assert "Mig: Known" not in body


def test_conflicting_artifact_renders_mig_unknown(
    out_of_repo_tmp_path: Path,
) -> None:
    resolver = _resolver_from_artifact(
        _sanitized_artifact(
            STAGE29_5_MEASUREMENT_STATUS_CONFLICTING_MIGRATION
        )
    )
    _result, body = _run_session(
        tmp_path=out_of_repo_tmp_path,
        migration_context_resolver=resolver,
        market_context_source=_market_source_with_mc_lp(),
    )
    _assert_common_compact_shape(body)
    assert "Mig: Unknown" in body
    assert "Mig: Known" not in body
    assert "Mig: Unverified" not in body


def test_stale_partial_artifact_renders_mig_unknown_no_stale_word(
    out_of_repo_tmp_path: Path,
) -> None:
    resolver = _resolver_from_artifact(
        _sanitized_artifact(
            STAGE29_5_MEASUREMENT_STATUS_PARTIAL_MIGRATION_PRESENT,
            warnings=(STAGE29_5_WARNING_MIGRATION_STALE,),
        )
    )
    _result, body = _run_session(
        tmp_path=out_of_repo_tmp_path,
        migration_context_resolver=resolver,
        market_context_source=_market_source_with_mc_lp(),
    )
    _assert_common_compact_shape(body)
    assert "Mig: Unknown" in body
    assert "Mig: Unverified" not in body
    assert "Mig: Stale" not in body


def test_none_artifact_renders_mig_unknown(
    out_of_repo_tmp_path: Path,
) -> None:
    resolver = _resolver_from_artifact(None)
    _result, body = _run_session(
        tmp_path=out_of_repo_tmp_path,
        migration_context_resolver=resolver,
        market_context_source=_market_source_with_mc_lp(),
    )
    _assert_common_compact_shape(body)
    assert "Mig: Unknown" in body
    assert "Mig: Known" not in body


def test_redacted_complete_artifact_renders_mig_unknown(
    out_of_repo_tmp_path: Path,
) -> None:
    resolver = _resolver_from_artifact(
        _sanitized_artifact(
            STAGE29_5_MEASUREMENT_STATUS_COMPLETE,
            redaction_status="REDACTED",
        )
    )
    _result, body = _run_session(
        tmp_path=out_of_repo_tmp_path,
        migration_context_resolver=resolver,
        market_context_source=_market_source_with_mc_lp(),
    )
    _assert_common_compact_shape(body)
    assert "Mig: Unknown" in body
    assert "Mig: Known" not in body


# ---------------------------------------------------------------------------
# 4. No resolver supplied -> Mig: Unknown (Stage 30.4.2 baseline preserved)
# ---------------------------------------------------------------------------


def test_no_resolver_is_backward_compatible_mig_unknown(
    out_of_repo_tmp_path: Path,
) -> None:
    result, body = _run_session(
        tmp_path=out_of_repo_tmp_path,
        migration_context_resolver=None,
        market_context_source=_market_source_with_mc_lp(),
    )
    assert result.market_context_replacements_succeeded == 1
    _assert_common_compact_shape(body)
    assert "Mig: Unknown" in body
    assert "Mig: Known" not in body
    assert "Mig: Unverified" not in body

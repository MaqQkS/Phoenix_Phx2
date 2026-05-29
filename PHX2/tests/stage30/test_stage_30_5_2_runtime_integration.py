"""Stage 30.5.2 compact migration runtime integration tests.

Drives the full Stage 30.4.2 opt-in parallel compact runtime session
orchestrator with an opt-in Stage 30.5.2 ``migration_context_resolver``
and asserts the FINAL dispatched compact body carries the resolved
``Mig`` token:

  * KNOWN / PRESENT / ON_CHAIN_EVENT  -> ``Mig: Known``
  * UNVERIFIED / PRESENT / EVIDENCE_PARTIAL -> ``Mig: Unverified``
  * UNKNOWN / UNAVAILABLE / NONE      -> ``Mig: Unknown``
  * KNOWN but source_status ERROR     -> ``Mig: Unknown`` (dominance)
  * KNOWN but source_status STALE     -> ``Mig: Unknown`` (no Stale word)
  * source raises                     -> ``Mig: Unknown``
  * no resolver supplied              -> ``Mig: Unknown`` (backward
                                         compatible with Stage 30.4.2)

The migration wiring only fills the existing Stage 30.2
``migration_mc_text`` slot, so the compact renderer is untouched, the
MC / LP enrichment from Stage 30.4.2 is preserved, ATH stays Unknown,
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
from PHX2.stage30.stage30_4_compact_market_context_source_protocol import (
    Stage30_4MarketContextSourceReading,
)
from PHX2.stage30.stage30_4_compact_runtime_session_orchestrator import (
    Stage30_4_2CompactRuntimeSessionResult,
    run_stage30_4_2_compact_runtime_session,
)
from PHX2.stage30.stage30_5_compact_migration_runtime_adapter import (
    Stage30_5_2MigrationDisplayResolver,
)
from PHX2.stage30.stage30_5_migration_context_models import (
    MIGRATION_BASIS_EVIDENCE_PARTIAL,
    MIGRATION_BASIS_NONE,
    MIGRATION_BASIS_ON_CHAIN_EVENT,
    MIGRATION_STATUS_KNOWN,
    MIGRATION_STATUS_UNKNOWN,
    MIGRATION_STATUS_UNVERIFIED,
    SOURCE_REASON_EVIDENCE_PARTIAL,
    SOURCE_REASON_SOURCE_ERROR,
    SOURCE_REASON_SOURCE_PRESENT,
    SOURCE_REASON_SOURCE_STALE,
    SOURCE_REASON_SOURCE_UNAVAILABLE,
    SOURCE_STATUS_ERROR,
    SOURCE_STATUS_PRESENT,
    SOURCE_STATUS_STALE,
    SOURCE_STATUS_UNAVAILABLE,
    STAGE30_5_1_MIGRATION_CONTEXT_SCHEMA_VERSION,
    Stage30_5MigrationContextRecord,
)

# Reuse the proven Stage 30.4.2 offline scaffolding verbatim.
from PHX2.tests.stage30.test_stage_30_4_2_compact_runtime_integration import (
    _CLOCK_TS,
    _FAKE_WEBHOOK_URL,
    _PHOENIX_PREFIX,
    _SAFE_MINT,
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


# ---------------------------------------------------------------------------
# Local fixtures + fakes
# ---------------------------------------------------------------------------


_VERBOSE_HEADER_MARKER: str = "PHX2 STAGE 28.9 PRIVATE OPERATOR PING"


@pytest.fixture
def out_of_repo_tmp_path() -> Iterator[Path]:
    base = tempfile.mkdtemp(prefix="phx2_stage30_5_2_test_")
    try:
        yield Path(base)
    finally:
        shutil.rmtree(base, ignore_errors=True)


class _FakeMigrationSource:
    """Stage 30.5.1 source-protocol-compatible fake migration source."""

    def __init__(
        self,
        *,
        record: Optional[Stage30_5MigrationContextRecord] = None,
        raises: bool = False,
    ) -> None:
        self._record = record
        self._raises = raises
        self.call_count: int = 0

    def read(
        self,
        token_mint: str,
        observed_at_utc: Optional[str] = None,
    ) -> Optional[Stage30_5MigrationContextRecord]:
        self.call_count += 1
        if self._raises:
            raise RuntimeError("fake migration source failure")
        return self._record


def _migration_record(
    *,
    status: str,
    basis: str,
    source_status: str,
    source_reason: str,
) -> Stage30_5MigrationContextRecord:
    return Stage30_5MigrationContextRecord(
        schema_version=STAGE30_5_1_MIGRATION_CONTEXT_SCHEMA_VERSION,
        token_label=None,
        migration_status=status,
        migration_basis=basis,
        migration_event_time_utc=None,
        migration_age_seconds=None,
        source_label="stage30_5_2_fake_migration",
        source_status=source_status,
        source_reason=source_reason,
        runtime_consumable=False,
        observed_at_utc=_CLOCK_TS,
    )


def _resolver_for_record(
    *,
    status: str,
    basis: str,
    source_status: str,
    source_reason: str,
) -> Stage30_5_2MigrationDisplayResolver:
    return Stage30_5_2MigrationDisplayResolver(
        source=_FakeMigrationSource(
            record=_migration_record(
                status=status,
                basis=basis,
                source_status=source_status,
                source_reason=source_reason,
            ),
        ),
    )


class _StaticDisplayResolver:
    """Throwaway duck-typed resolver that returns a caller-supplied raw
    value from ``resolve_display_text``, BYPASSING the official Stage
    30.5.2 closed-set adapter.

    Used to prove the Stage 30.4.2 runtime seam enforces its OWN local
    closed-set guard: an adversarial / buggy resolver that returns an
    off-vocabulary word (e.g. ``"Stale"`` / ``"Fresh"``) must NOT reach
    the compact body.
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
    # Unknown (Stage 30.5.2 introduces no ATH / Net field).
    assert "MC: $83k" in body
    assert "LP: $27k" in body
    assert "ATH: Unknown" in body
    assert "Net: Unknown" in body
    assert "Basis: price-basis" in body
    # No Mig: Stale / Mig: Fresh display word ever appears.
    assert "Mig: Stale" not in body
    assert "Mig: Fresh" not in body


# ---------------------------------------------------------------------------
# 1. KNOWN / PRESENT -> Mig: Known
# ---------------------------------------------------------------------------


def test_known_present_renders_mig_known(
    out_of_repo_tmp_path: Path,
) -> None:
    resolver = _resolver_for_record(
        status=MIGRATION_STATUS_KNOWN,
        basis=MIGRATION_BASIS_ON_CHAIN_EVENT,
        source_status=SOURCE_STATUS_PRESENT,
        source_reason=SOURCE_REASON_SOURCE_PRESENT,
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
    assert "Mig: Known" in body
    assert "Mig: Unknown" not in body


# ---------------------------------------------------------------------------
# 2. UNVERIFIED / PRESENT -> Mig: Unverified
# ---------------------------------------------------------------------------


def test_unverified_present_renders_mig_unverified(
    out_of_repo_tmp_path: Path,
) -> None:
    resolver = _resolver_for_record(
        status=MIGRATION_STATUS_UNVERIFIED,
        basis=MIGRATION_BASIS_EVIDENCE_PARTIAL,
        source_status=SOURCE_STATUS_PRESENT,
        source_reason=SOURCE_REASON_EVIDENCE_PARTIAL,
    )
    _result, body = _run_session(
        tmp_path=out_of_repo_tmp_path,
        migration_context_resolver=resolver,
        market_context_source=_market_source_with_mc_lp(),
    )

    _assert_common_compact_shape(body)
    assert "Mig: Unverified" in body
    assert "Mig: Unknown" not in body
    assert "Mig: Known" not in body


# ---------------------------------------------------------------------------
# 3. UNKNOWN / UNAVAILABLE -> Mig: Unknown
# ---------------------------------------------------------------------------


def test_unknown_unavailable_renders_mig_unknown(
    out_of_repo_tmp_path: Path,
) -> None:
    resolver = _resolver_for_record(
        status=MIGRATION_STATUS_UNKNOWN,
        basis=MIGRATION_BASIS_NONE,
        source_status=SOURCE_STATUS_UNAVAILABLE,
        source_reason=SOURCE_REASON_SOURCE_UNAVAILABLE,
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


# ---------------------------------------------------------------------------
# 4. KNOWN but source_status ERROR -> Mig: Unknown (source dominance)
# ---------------------------------------------------------------------------


def test_known_but_source_error_renders_mig_unknown(
    out_of_repo_tmp_path: Path,
) -> None:
    resolver = _resolver_for_record(
        status=MIGRATION_STATUS_KNOWN,
        basis=MIGRATION_BASIS_ON_CHAIN_EVENT,
        source_status=SOURCE_STATUS_ERROR,
        source_reason=SOURCE_REASON_SOURCE_ERROR,
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
# 5. KNOWN but source_status STALE -> Mig: Unknown (no Stale display word)
# ---------------------------------------------------------------------------


def test_known_but_source_stale_renders_mig_unknown(
    out_of_repo_tmp_path: Path,
) -> None:
    resolver = _resolver_for_record(
        status=MIGRATION_STATUS_KNOWN,
        basis=MIGRATION_BASIS_ON_CHAIN_EVENT,
        source_status=SOURCE_STATUS_STALE,
        source_reason=SOURCE_REASON_SOURCE_STALE,
    )
    _result, body = _run_session(
        tmp_path=out_of_repo_tmp_path,
        migration_context_resolver=resolver,
        market_context_source=_market_source_with_mc_lp(),
    )

    _assert_common_compact_shape(body)
    assert "Mig: Unknown" in body
    assert "Mig: Known" not in body
    assert "Mig: Stale" not in body


# ---------------------------------------------------------------------------
# 6. Source raises -> Mig: Unknown
# ---------------------------------------------------------------------------


def test_source_raises_renders_mig_unknown(
    out_of_repo_tmp_path: Path,
) -> None:
    resolver = Stage30_5_2MigrationDisplayResolver(
        source=_FakeMigrationSource(raises=True),
    )
    _result, body = _run_session(
        tmp_path=out_of_repo_tmp_path,
        migration_context_resolver=resolver,
        market_context_source=_market_source_with_mc_lp(),
    )

    _assert_common_compact_shape(body)
    assert "Mig: Unknown" in body
    assert "Mig: Known" not in body


def test_none_record_renders_mig_unknown(
    out_of_repo_tmp_path: Path,
) -> None:
    resolver = Stage30_5_2MigrationDisplayResolver(
        source=_FakeMigrationSource(record=None),
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
# 7. No resolver supplied -> Mig: Unknown (backward compatible)
# ---------------------------------------------------------------------------


def test_no_resolver_is_backward_compatible_mig_unknown(
    out_of_repo_tmp_path: Path,
) -> None:
    """With no ``migration_context_resolver``, the Stage 30.4.2 runtime
    behaves exactly as before: MC / LP enrich, Mig stays Unknown, and
    the replacement still succeeds.
    """
    result, body = _run_session(
        tmp_path=out_of_repo_tmp_path,
        migration_context_resolver=None,
        market_context_source=_market_source_with_mc_lp(),
    )

    assert result.inner_stage30_3_result.session_result.session_outcome == (
        SESSION_OUTCOME_OK
    )
    assert result.market_context_replacements_attempted == 1
    assert result.market_context_replacements_succeeded == 1
    assert result.market_context_replacements_failed == 0
    _assert_common_compact_shape(body)
    assert "Mig: Unknown" in body
    assert "Mig: Known" not in body
    assert "Mig: Unverified" not in body


# ---------------------------------------------------------------------------
# 8. Stage 30.4.2 runtime seam closed-set guard (Codex PASS WITH PATCHES):
#    an off-vocabulary word from a throwaway resolver must NOT reach the
#    compact body. Only Known / Unverified / Unknown are accepted.
# ---------------------------------------------------------------------------


def test_resolver_returning_stale_renders_mig_unknown(
    out_of_repo_tmp_path: Path,
) -> None:
    """A throwaway resolver returning ``"Stale"`` must render
    ``Mig: Unknown`` -- never ``Mig: Stale``.
    """
    _result, body = _run_session(
        tmp_path=out_of_repo_tmp_path,
        migration_context_resolver=_StaticDisplayResolver(value="Stale"),
        market_context_source=_market_source_with_mc_lp(),
    )
    _assert_common_compact_shape(body)
    assert "Mig: Unknown" in body
    assert "Mig: Stale" not in body


def test_resolver_returning_fresh_renders_mig_unknown(
    out_of_repo_tmp_path: Path,
) -> None:
    """A throwaway resolver returning ``"Fresh"`` must render
    ``Mig: Unknown`` -- never ``Mig: Fresh``.
    """
    _result, body = _run_session(
        tmp_path=out_of_repo_tmp_path,
        migration_context_resolver=_StaticDisplayResolver(value="Fresh"),
        market_context_source=_market_source_with_mc_lp(),
    )
    _assert_common_compact_shape(body)
    assert "Mig: Unknown" in body
    assert "Mig: Fresh" not in body


def test_resolver_returning_arbitrary_string_renders_mig_unknown(
    out_of_repo_tmp_path: Path,
) -> None:
    """A throwaway resolver returning an arbitrary off-vocabulary string
    must render ``Mig: Unknown``.
    """
    _result, body = _run_session(
        tmp_path=out_of_repo_tmp_path,
        migration_context_resolver=_StaticDisplayResolver(
            value="TotallyMigratedTrustMe",
        ),
        market_context_source=_market_source_with_mc_lp(),
    )
    _assert_common_compact_shape(body)
    assert "Mig: Unknown" in body
    assert "TotallyMigratedTrustMe" not in body


@pytest.mark.parametrize(
    "bad_value",
    ["", "   ", " Known ", "known", "KNOWN", 12345, None, ["Known"]],
)
def test_resolver_returning_empty_whitespace_or_nonstring_renders_mig_unknown(
    out_of_repo_tmp_path: Path,
    bad_value: object,
) -> None:
    """Empty / whitespace / wrong-case / non-string resolver output is
    rejected by the closed-set guard; the body keeps ``Mig: Unknown``.
    """
    _result, body = _run_session(
        tmp_path=out_of_repo_tmp_path,
        migration_context_resolver=_StaticDisplayResolver(value=bad_value),
        market_context_source=_market_source_with_mc_lp(),
    )
    _assert_common_compact_shape(body)
    assert "Mig: Unknown" in body


@pytest.mark.parametrize("word", ["Known", "Unverified", "Unknown"])
def test_static_resolver_valid_words_render_through(
    out_of_repo_tmp_path: Path,
    word: str,
) -> None:
    """The three closed-set words are accepted verbatim by the runtime
    seam guard and reach the compact body ``Mig`` token.
    """
    _result, body = _run_session(
        tmp_path=out_of_repo_tmp_path,
        migration_context_resolver=_StaticDisplayResolver(value=word),
        market_context_source=_market_source_with_mc_lp(),
    )
    _assert_common_compact_shape(body)
    assert f"Mig: {word}" in body

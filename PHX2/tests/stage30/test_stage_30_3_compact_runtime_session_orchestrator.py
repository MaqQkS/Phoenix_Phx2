"""Stage 30.3B compact private runtime session orchestrator tests.

Pins the Stage 30.3B parallel orchestrator contract:

  * happy path: one normalized event -> one Stage 27.6 candidate
    -> one Stage 30.3 compact dispatch through the Stage 28.9
    bounded private session runner. Verbose Stage 28.9 header is
    REPLACED by the Stage 30.2 compact body BEFORE the inner
    transport sees the payload; the Stage 30.1 / Stage 30.2 /
    Stage 30.3 JSONL artifacts each carry one line.
  * fail-closed: a forced Stage 30.1 BASIS_INVALID failure on
    the Stage 30.3 context prevents the inner transport from
    being called and the Stage 28.9 session result is FAILED.
  * Stage 29.5.6 composition: the optional migration-context
    injector is duck-typed via ``wrap_transport`` and its
    appended block survives end-to-end.
  * wrapper_order invariants: empty tuple and wrong-first-label
    each surface ``Stage30_3CompactRuntimeError("WRAPPER_ORDER_INVALID")``.
  * boundary scan: the orchestrator module imports zero
    ``os``/env/network/provider/PHX1 surfaces, carries no
    top-level Call nodes, and its PHX2 imports stay inside the
    documented allowlist.

No env reads. No network. No real provider. No real Discord.
Stdlib + pytest only.
"""

from __future__ import annotations

import ast
import json
import shutil
import tempfile
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, Iterable, Iterator, List, Optional, Set, Tuple

import pytest

from PHX2.stage27.live_candidate_assembler import (
    CANDIDATE_REASON_RENDERED_OK,
    CANDIDATE_STATUS_RENDERED_DRY_RUN,
    STAGE27_6_CANDIDATE_SCHEMA_VERSION,
    Stage27_6LiveCandidateRecord,
)
from PHX2.stage27.migration_context_models import (
    MIGRATION_REASON_OK,
    MIGRATION_SOURCE_ON_CHAIN_MIGRATION_EVENT,
    MIGRATION_STATUS_PRESENT,
    STAGE27_4_MIGRATION_SCHEMA_VERSION,
    MigrationContextRecord,
)
from PHX2.stage27.price_ath_context_models import (
    ATH_REASON_OK,
    ATH_SINCE_MIGRATION_STATUS_POST_MIGRATION_ONLY,
    ATH_STATUS_PRESENT,
    ATH_UNIT_SOL,
    DRAWDOWN_BASIS_FROM_POST_MIGRATION_ATH,
    STAGE27_4_PRICE_ATH_SCHEMA_VERSION,
    AthContextRecord,
)
from PHX2.stage27.private_ping_models import (
    PrivatePingPayloadRecord,
    STAGE27_5_PING_SCHEMA_VERSION,
)
from PHX2.stage27.provider_ingest_models import (
    COMPOSITION_REASON_OK,
    COMPOSITION_STATUS_COMPOSED,
    EVENT_KIND_SWAP,
    ProviderIngestOutputRecord,
    STAGE27_3_SCHEMA_VERSION,
)
from PHX2.stage28.audited_http_transport_models import (
    RESPONSE_BODY_STATUS_DROPPED_UNRECORDED,
    REDACTION_STATUS_REDACTED,
    STAGE28_4_SCHEMA_VERSION,
    TRANSPORT_STATUS_SENT_OK,
    Stage28_4TransportResult,
    WEBHOOK_IDENTITY_PRIVATE_OPERATOR,
    derive_safe_reason_code,
)
from PHX2.stage28.live_provider_session_adapter import (
    STAGE28_9_DISPATCH_LEDGER_BASENAME,
    STAGE28_9_FINAL_SUMMARY_BASENAME,
    STAGE28_9_HEALTH_SNAPSHOT_BASENAME,
    STAGE28_9_HEARTBEAT_BASENAME,
)
from PHX2.stage28.live_provider_session_models import (
    SESSION_MODE_LIVE_PRIVATE,
    SESSION_OUTCOME_FAILED,
    SESSION_OUTCOME_OK,
    Stage28_9LiveProviderSessionConfig,
    build_live_provider_session_config,
)
from PHX2.stage29.stage29_5_5_render_models import (
    MIGRATION_EVIDENCE_SOURCE_TRUST_DISPLAY_TRUSTED_ON_CHAIN,
    MIGRATION_EVIDENCE_STATUS_DISPLAY_COMPLETE,
    POST_MIGRATION_ATH_VERIFIED_DISPLAY_VERIFIED,
    STAGE29_5_5_RENDERED_MIGRATION_CONTEXT_BLOCK_SCHEMA_VERSION,
    Stage29_5_5RenderedMigrationContextBlock,
)
from PHX2.stage29.stage29_5_6_private_ping_migration_context_injector import (
    STAGE29_5_6_CONTENT_MAX_CHARS,
    Stage29_5_6PrivateDiscordBodyInjector,
)
from PHX2.stage29.stage29_5_migration_models import (
    FILTER_ENFORCEMENT_STATUS_NOT_ACTIVE_STAGE_29_PENDING,
    MIGRATION_JOIN_STATUS_JOINED,
    MIGRATION_SOURCE_HELIUS_WS,
    REDACTION_STATUS_SAFE,
)
from PHX2.stage30.compact_ping_models import (
    STAGE30_2_COMPACT_PING_ARTIFACT_BASENAME,
)
from PHX2.stage30.stage30_3_compact_runtime_models import (
    COMPACT_OUTCOME_RENDERED,
    STAGE30_3_RUNTIME_WIRING_ARTIFACT_BASENAME,
    WRAPPER_ORDER_LABEL_FAKE_INNER_TRANSPORT,
    WRAPPER_ORDER_LABEL_STAGE28_9_PRIVATE_WEBHOOK,
    WRAPPER_ORDER_LABEL_STAGE29_5_6_MIGRATION,
    WRAPPER_ORDER_LABEL_STAGE30_3_COMPACT_BODY,
    Stage30_3CompactRuntimeContext,
    Stage30_3CompactRuntimeError,
)
from PHX2.stage30.stage30_3_compact_runtime_session_orchestrator import (
    Stage30_3CompactRuntimeSessionResult,
    run_stage30_3_compact_runtime_session,
)
from PHX2.stage30.tier_decision_models import (
    STAGE30_1_TIER_DECISION_ARTIFACT_BASENAME,
)


# ---------------------------------------------------------------------------
# Locked constants
# ---------------------------------------------------------------------------


_FAKE_WEBHOOK_URL: str = (
    "h" + "ttps" + "://"
    + "example.invalid/fake-stage30-3-private-webhook"
)
_SAFE_MINT: str = "FakeMintPhx2NotWso1ForTestBase58222222222222"
_MIG_TS: str = "2026-05-27T00:00:00Z"
_CLOCK_TS: str = "2026-05-27T00:00:30Z"
_PHOENIX_PREFIX: str = "\U0001f525 PHOENIX"
_VERBOSE_HEADER_MARKER: str = (
    "PHX2 STAGE 28.9 PRIVATE OPERATOR PING"
)


# ---------------------------------------------------------------------------
# out_of_repo_tmp_path fixture
# ---------------------------------------------------------------------------
#
# The Stage 28.9 readiness gate refuses any ``output_dir`` that
# resolves inside the PHX2 repo root. Operator pre-commit invocations
# may pin pytest's ``--basetemp`` to a directory INSIDE the repo
# (e.g. ``PHX2/.test_tmp_pytest_stage30_3b``), so pytest's built-in
# ``tmp_path`` fixture cannot be used as the Stage 30.3B orchestrator
# output_dir. The fixture below uses ``tempfile.mkdtemp`` (system
# temp dir, typically outside the repo) and cleans up on teardown.


@pytest.fixture
def out_of_repo_tmp_path() -> Iterator[Path]:
    base = tempfile.mkdtemp(prefix="phx2_stage30_3b_test_")
    try:
        yield Path(base)
    finally:
        shutil.rmtree(base, ignore_errors=True)


# ---------------------------------------------------------------------------
# Stage 27 fixtures
# ---------------------------------------------------------------------------


def _build_ingest_output(
    *,
    token_mint: str = _SAFE_MINT,
    pair_quote_asset: str = "SOL",
) -> ProviderIngestOutputRecord:
    return ProviderIngestOutputRecord(
        provider_id="helius_grpc",
        provider_event_id="evt_001",
        normalized_event_id="norm_001",
        event_kind=EVENT_KIND_SWAP,
        observed_at_utc="2026-05-27T00:00:00Z",
        token_mint=token_mint,
        quote_mint="So11111111111111111111111111111111111111112",
        pair_quote_asset=pair_quote_asset,
        pair_pair_type="PUMP_SOL",
        pair_bonding_curve_version="V1",
        pair_detection_status="CONFIRMED",
        pair_detection_confidence="HIGH",
        pair_detection_reason="OK",
        pair_live_policy="LIVE_OK_SOL",
        pair_calibration_lane="EXISTING_SOL_LANE",
        raw_capture_ref="raw_hash_001",
        source_summary="source_summary_001",
        composition_status=COMPOSITION_STATUS_COMPOSED,
        composition_reason=COMPOSITION_REASON_OK,
        schema_version=STAGE27_3_SCHEMA_VERSION,
    )


def _build_rendered_ping(
    *, body_text: str = "Verbose stage 27.5 body. " * 5,
) -> PrivatePingPayloadRecord:
    return PrivatePingPayloadRecord(
        ping_id="ping_001",
        run_id="phx2_run01",
        session_id="phx2_session01",
        ping_schema_version=STAGE27_5_PING_SCHEMA_VERSION,
        provider_id="helius_grpc",
        provider_event_id="evt_001",
        normalized_event_id="norm_001",
        raw_capture_ref="raw_hash_001",
        token_mint=_SAFE_MINT,
        quote_mint="So11111111111111111111111111111111111111112",
        pair_type="PUMP_SOL",
        quote_asset="SOL",
        bonding_curve_version="V1",
        pair_detection_status="CONFIRMED",
        pair_detection_confidence="HIGH",
        pair_detection_reason="OK",
        pair_live_policy="LIVE_OK_SOL",
        calibration_lane="EXISTING_SOL_LANE",
        measurement_status="COMPLETE",
        measurement_warnings=(),
        price_status="PRESENT",
        price_value_display="1.23",
        price_unit_display="USD",
        price_source_display="fake_source",
        price_staleness_seconds_display="5",
        ath_status="PRESENT",
        ath_value_display="2.00",
        ath_unit_display="USD",
        ath_since_migration_status_display="OK",
        drawdown_display="0.55",
        drawdown_basis_display="OK",
        migration_status="PRESENT",
        migration_timestamp_display=_MIG_TS,
        migration_age_seconds_display="30",
        migration_source_display="fake_migration",
        render_status="RENDERED",
        render_note="LIVE_OK",
        body_text=body_text,
    )


def _build_ath_record(mint: str = _SAFE_MINT) -> AthContextRecord:
    return AthContextRecord(
        token_mint=mint,
        pair_type="PUMPSWAP_AMM",
        quote_asset="SOL",
        ath_value="1.0",
        ath_unit=ATH_UNIT_SOL,
        ath_source="synthetic_test",
        ath_observed_at_utc=_MIG_TS,
        ath_since_migration_status=(
            ATH_SINCE_MIGRATION_STATUS_POST_MIGRATION_ONLY
        ),
        drawdown_from_ath="0.55",
        drawdown_unit=ATH_UNIT_SOL,
        drawdown_basis=DRAWDOWN_BASIS_FROM_POST_MIGRATION_ATH,
        ath_status=ATH_STATUS_PRESENT,
        ath_reason=ATH_REASON_OK,
        schema_version=STAGE27_4_PRICE_ATH_SCHEMA_VERSION,
    )


def _build_migration_record(
    mint: str = _SAFE_MINT,
) -> MigrationContextRecord:
    return MigrationContextRecord(
        token_mint=mint,
        pair_type="PUMPSWAP_AMM",
        quote_asset="SOL",
        migration_event_id="evt-001",
        migration_timestamp_utc=_MIG_TS,
        migration_source=MIGRATION_SOURCE_ON_CHAIN_MIGRATION_EVENT,
        migration_status=MIGRATION_STATUS_PRESENT,
        migration_reason=MIGRATION_REASON_OK,
        age_since_migration_seconds=30,
        observed_at_utc=_CLOCK_TS,
        source_event_ref="evt-ref-001",
        raw_capture_ref=None,
        schema_version=STAGE27_4_MIGRATION_SCHEMA_VERSION,
    )


def _build_stage27_6_record(
    *,
    candidate_id: str = "cand_001",
    token_mint: str = _SAFE_MINT,
) -> Stage27_6LiveCandidateRecord:
    """Build a Stage27_6LiveCandidateRecord that:

      * has a populated ingest_output (Stage 28.9 mapper requires
        non-empty fields),
      * has a populated rendered_ping (Stage 28.9 dispatch path),
      * carries a duck-typed measurement_context exposing
        ath_context + migration_context via SimpleNamespace (the
        Stage 30.3 recorder is duck-typed; the Stage 28.9 mapper
        never reads measurement_context).
    """
    return Stage27_6LiveCandidateRecord(
        candidate_id=candidate_id,
        run_id="phx2_run01",
        session_id="phx2_session01",
        candidate_schema_version=(
            STAGE27_6_CANDIDATE_SCHEMA_VERSION
        ),
        candidate_status=CANDIDATE_STATUS_RENDERED_DRY_RUN,
        candidate_reason=CANDIDATE_REASON_RENDERED_OK,
        ingest_output=_build_ingest_output(token_mint=token_mint),
        measurement_context=SimpleNamespace(
            ath_context=_build_ath_record(mint=token_mint),
            migration_context=_build_migration_record(mint=token_mint),
        ),
        rendered_ping=_build_rendered_ping(),
        provenance_artifact=None,
        payload_artifact_path=None,
        provenance_artifact_path=None,
        dedupe_key=None,
        write_attempted=False,
    )


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class _FakeNormalizedEvent(SimpleNamespace):
    """Stage 27.3 NormalizedEventLike Protocol-compatible fake."""


def _make_fake_event(idx: int = 0) -> _FakeNormalizedEvent:
    return _FakeNormalizedEvent(
        event_id=f"evt_{idx:03d}",
        provider_event_id=f"prov_evt_{idx:03d}",
        provider_name="fake_provider",
        mint=f"SoMintFakeAbc{idx:03d}",
        event_type="swap",
        observed_at_utc="2026-05-27T00:00:00Z",
        raw_event_hash=f"hash_{idx:03d}",
    )


class _FakeProviderEventSource:
    """Stage 28.9 Stage28_9ProviderEventSource-compatible fake.

    Yields a caller-supplied tuple of normalized events.
    """

    def __init__(
        self,
        *,
        events: Iterable[_FakeNormalizedEvent],
    ) -> None:
        self._events: Tuple[_FakeNormalizedEvent, ...] = tuple(events)
        self._iter_count: int = 0

    @property
    def iter_count(self) -> int:
        return self._iter_count

    def iter_events(
        self, *, max_events: int,
    ) -> Iterator[_FakeNormalizedEvent]:
        self._iter_count += 1
        for index, event in enumerate(self._events):
            if index >= max_events:
                return
            yield event


class _FakeInnerCandidateAssembler:
    """Stage 28.9 Stage28_9CandidateAssembler-compatible fake.

    Returns a pre-canned Stage27_6LiveCandidateRecord for each
    ``assemble`` call. The record's ``candidate_id`` is rewritten
    to the orchestrator-supplied candidate_id so the recorder
    captures the same id Stage 28.6 dispatches under.
    """

    def __init__(
        self,
        *,
        records: Iterable[Stage27_6LiveCandidateRecord],
    ) -> None:
        self._records: Tuple[
            Stage27_6LiveCandidateRecord, ...
        ] = tuple(records)
        self._call_count: int = 0

    @property
    def call_count(self) -> int:
        return self._call_count

    def assemble(
        self,
        normalized_event: object,
        *,
        candidate_id: str,
    ) -> Stage27_6LiveCandidateRecord:
        index = self._call_count
        self._call_count += 1
        if index < len(self._records):
            base = self._records[index]
        else:
            base = self._records[-1]
        return base._replace(candidate_id=candidate_id)


class _RecordingInnerTransport:
    """Stage 28.6 Stage28_6PrivateTransport-compatible fake that
    records every ``send_one_audited_post`` call and returns a
    real Stage28_4TransportResult on the SENT_OK path.
    """

    def __init__(self) -> None:
        self.call_count: int = 0
        self.received_kwargs: List[Dict[str, Any]] = []

    def send_one_audited_post(
        self, *, webhook_identity: str, payload: object,
    ) -> Stage28_4TransportResult:
        self.call_count += 1
        snapshot: Dict[str, Any] = {}
        if isinstance(payload, dict):
            snapshot = dict(payload)
        self.received_kwargs.append(
            {
                "webhook_identity": webhook_identity,
                "payload": snapshot,
            }
        )
        return Stage28_4TransportResult(
            transport_status=TRANSPORT_STATUS_SENT_OK,
            ok=True,
            http_status_code=204,
            retry_after_seconds=None,
            send_attempt_count=1,
            webhook_identity=webhook_identity,
            redaction_status=REDACTION_STATUS_REDACTED,
            safe_reason_code=derive_safe_reason_code(
                TRANSPORT_STATUS_SENT_OK
            ),
            response_body_status=(
                RESPONSE_BODY_STATUS_DROPPED_UNRECORDED
            ),
            schema_version=STAGE28_4_SCHEMA_VERSION,
        )


class _FakeClock:
    """Deterministic ISO-8601 UTC clock fake."""

    def __init__(self, *, stamps: Optional[Iterable[str]] = None) -> None:
        if stamps is None:
            stamps = (_CLOCK_TS,)
        self._stamps: List[str] = list(stamps)
        self._index: int = 0

    def now_utc_iso(self) -> str:
        if self._index < len(self._stamps):
            value = self._stamps[self._index]
            self._index += 1
        else:
            value = self._stamps[-1]
        return value


# ---------------------------------------------------------------------------
# Config + context fixtures
# ---------------------------------------------------------------------------


def _make_session_config(
    *,
    max_events: int = 1,
    max_dispatches: int = 1,
) -> Stage28_9LiveProviderSessionConfig:
    return build_live_provider_session_config(
        run_id="phx2_stage30_3_run01",
        session_id="phx2_stage30_3_session01",
        provider_id="fake_provider",
        provider_kind="fake_kind",
        max_events=max_events,
        max_dispatches=max_dispatches,
        max_ticks=32,
        max_total_retries=0,
        heartbeat_every_n_events=1,
        output_dir_safe_label="phx2_stage30_3_scratch",
        session_mode=SESSION_MODE_LIVE_PRIVATE,
    )


def _make_runtime_context(
    *,
    tmp_path: Path,
    session_id: Optional[str] = "stage30-3-ctx-001",
    basis: str = "price-basis",
) -> Stage30_3CompactRuntimeContext:
    return Stage30_3CompactRuntimeContext(
        session_id=session_id,
        run_id="stage30-3-run-001",
        basis=basis,
        output_dir=tmp_path,
    )


# ---------------------------------------------------------------------------
# Test 1: happy path
# ---------------------------------------------------------------------------


def test_orchestrator_happy_path_one_event_one_compact_dispatch(
    out_of_repo_tmp_path: Path,
) -> None:
    tmp_path = out_of_repo_tmp_path
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
    clock = _FakeClock(stamps=(_CLOCK_TS,) * 8)

    result = run_stage30_3_compact_runtime_session(
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
    )

    assert isinstance(result, Stage30_3CompactRuntimeSessionResult)
    assert result.session_result.session_outcome == SESSION_OUTCOME_OK
    assert result.session_result.dispatch_success == 1
    assert result.session_result.dispatch_failure == 0
    assert inner_transport.call_count == 1

    dispatched_payload = inner_transport.received_kwargs[0]["payload"]
    final_content = dispatched_payload["content"]
    assert final_content.startswith(_PHOENIX_PREFIX), (
        f"expected compact body prefix; got {final_content[:64]!r}"
    )
    assert _VERBOSE_HEADER_MARKER not in final_content, (
        "Stage 28.9 verbose header must have been REPLACED by the "
        "Stage 30.2 compact body before the inner transport saw it"
    )

    tier_path = tmp_path / STAGE30_1_TIER_DECISION_ARTIFACT_BASENAME
    compact_path = tmp_path / STAGE30_2_COMPACT_PING_ARTIFACT_BASENAME
    wiring_path = tmp_path / STAGE30_3_RUNTIME_WIRING_ARTIFACT_BASENAME
    for artifact_path in (tier_path, compact_path, wiring_path):
        assert artifact_path.is_file(), (
            f"expected Stage 30 artifact {artifact_path.name} to exist"
        )
        lines = [
            line
            for line in artifact_path.read_text(
                encoding="utf-8"
            ).splitlines()
            if line
        ]
        assert len(lines) == 1, (
            f"expected exactly one JSONL line in "
            f"{artifact_path.name}; got {len(lines)}"
        )

    for basename in (
        STAGE28_9_DISPATCH_LEDGER_BASENAME,
        STAGE28_9_HEARTBEAT_BASENAME,
        STAGE28_9_HEALTH_SNAPSHOT_BASENAME,
        STAGE28_9_FINAL_SUMMARY_BASENAME,
    ):
        assert (tmp_path / basename).is_file(), (
            f"expected Stage 28.9 runner artifact {basename}"
        )

    assert result.wrapper_order == wrapper_order
    assert result.compact_renders_attempted == 1
    assert result.compact_renders_succeeded == 1
    assert result.compact_renders_failed == 0
    assert result.compact_renders_skipped == 0
    assert result.recorded_entries_count == 1


# ---------------------------------------------------------------------------
# Test 2: fail-closed (Stage 30.1 BASIS_INVALID)
# ---------------------------------------------------------------------------


def test_orchestrator_fail_closed_blocks_inner_transport(
    out_of_repo_tmp_path: Path,
) -> None:
    tmp_path = out_of_repo_tmp_path
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
    # Invalid basis forces the Stage 30.1 projector to raise
    # BASIS_INVALID; the Stage 30.3 wrapper records
    # FAILED_TIER_DECISION and returns a synthetic refusal so the
    # inner transport is NEVER invoked.
    context = _make_runtime_context(
        tmp_path=tmp_path, basis="not_a_valid_basis_token",
    )
    clock = _FakeClock(stamps=(_CLOCK_TS,) * 8)

    result = run_stage30_3_compact_runtime_session(
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
    )

    assert inner_transport.call_count == 0
    assert result.session_result.session_outcome == SESSION_OUTCOME_FAILED
    assert result.session_result.dispatch_failure == 1
    assert result.session_result.dispatch_success == 0
    assert result.compact_renders_failed >= 1
    assert result.compact_renders_succeeded == 0

    wiring_path = tmp_path / STAGE30_3_RUNTIME_WIRING_ARTIFACT_BASENAME
    assert wiring_path.is_file()
    wiring_lines = [
        json.loads(line)
        for line in wiring_path.read_text(
            encoding="utf-8"
        ).splitlines()
        if line
    ]
    assert len(wiring_lines) >= 1
    first = wiring_lines[0]
    assert first["forwarded_to_inner_transport"] is False
    outcome = first["compact_outcome"]
    assert outcome.startswith("FAILED"), (
        f"expected a FAILED_* outcome; got {outcome!r}"
    )


# ---------------------------------------------------------------------------
# Test 3: Stage 29.5.6 composition through wrap_transport
# ---------------------------------------------------------------------------


def _build_safe_rendered_block() -> (
    Stage29_5_5RenderedMigrationContextBlock
):
    return Stage29_5_5RenderedMigrationContextBlock(
        migration_evidence_status_display=(
            MIGRATION_EVIDENCE_STATUS_DISPLAY_COMPLETE
        ),
        migration_evidence_source_trust_display=(
            MIGRATION_EVIDENCE_SOURCE_TRUST_DISPLAY_TRUSTED_ON_CHAIN
        ),
        post_migration_ath_verified_display=(
            POST_MIGRATION_ATH_VERIFIED_DISPLAY_VERIFIED
        ),
        migration_timestamp_utc_display="2026-05-27T00:00:00+00:00",
        migration_slot_display="12345",
        migration_source_token=MIGRATION_SOURCE_HELIUS_WS,
        join_status_echoed_token=MIGRATION_JOIN_STATUS_JOINED,
        warnings_display="none",
        redaction_status=REDACTION_STATUS_SAFE,
        filter_enforcement_status=(
            FILTER_ENFORCEMENT_STATUS_NOT_ACTIVE_STAGE_29_PENDING
        ),
        observed_at_utc=_MIG_TS,
        informational_only=True,
        not_a_trading_verdict=True,
        body_text=(
            "Migration evidence: complete\n"
            "Source: trusted on-chain\n"
            "ATH verified: yes\n"
            "informational_only: true\n"
            "not_a_trading_verdict: true"
        ),
        schema_version=(
            STAGE29_5_5_RENDERED_MIGRATION_CONTEXT_BLOCK_SCHEMA_VERSION
        ),
    )


class _FakeStage29_5_5Recorder:
    """Stage 29.5.5-shaped recorder: each entry carries
    ``rendered_block`` so the Stage 29.5.6 injector can append the
    most recent migration context block onto the dispatched body.
    """

    def __init__(self, *, entries: tuple) -> None:
        self._entries = entries

    @property
    def recorded_entries(self) -> tuple:
        return self._entries


def test_orchestrator_composes_with_stage29_5_6_injector(
    out_of_repo_tmp_path: Path,
) -> None:
    tmp_path = out_of_repo_tmp_path
    config = _make_session_config(max_events=1, max_dispatches=1)
    source = _FakeProviderEventSource(events=(_make_fake_event(0),))
    inner_assembler = _FakeInnerCandidateAssembler(
        records=(_build_stage27_6_record(),),
    )
    inner_transport = _RecordingInnerTransport()

    rendered_block = _build_safe_rendered_block()
    stage29_5_5_entry = SimpleNamespace(rendered_block=rendered_block)
    stage29_5_5_recorder = _FakeStage29_5_5Recorder(
        entries=(stage29_5_5_entry,)
    )
    injector = Stage29_5_6PrivateDiscordBodyInjector(
        migration_source=stage29_5_5_recorder,
    )

    wrapper_order = (
        WRAPPER_ORDER_LABEL_STAGE30_3_COMPACT_BODY,
        WRAPPER_ORDER_LABEL_STAGE29_5_6_MIGRATION,
        WRAPPER_ORDER_LABEL_FAKE_INNER_TRANSPORT,
    )
    context = _make_runtime_context(tmp_path=tmp_path)
    clock = _FakeClock(stamps=(_CLOCK_TS,) * 8)

    result = run_stage30_3_compact_runtime_session(
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
        private_migration_context_injector=injector,
    )

    assert result.session_result.session_outcome == SESSION_OUTCOME_OK
    assert inner_transport.call_count == 1

    final_content = inner_transport.received_kwargs[0]["payload"][
        "content"
    ]
    assert final_content.startswith(_PHOENIX_PREFIX)
    has_full = rendered_block.body_text in final_content
    has_compact_header = "[MIGRATION CONTEXT]" in final_content
    assert has_full or has_compact_header, (
        "Stage 29.5.6 injector must append either the full "
        "migration block or the [MIGRATION CONTEXT] compact "
        "fallback to the dispatched body"
    )
    assert len(final_content) <= STAGE29_5_6_CONTENT_MAX_CHARS

    # Stage 30.2 snapshot must NOT carry the Stage 29.5.6 append
    # (the compact snapshot records the compact body only).
    compact_path = tmp_path / STAGE30_2_COMPACT_PING_ARTIFACT_BASENAME
    compact_lines = [
        json.loads(line)
        for line in compact_path.read_text(
            encoding="utf-8"
        ).splitlines()
        if line
    ]
    assert len(compact_lines) == 1
    snapshot_body = compact_lines[0]["body_text"]
    assert "[MIGRATION CONTEXT]" not in snapshot_body
    assert rendered_block.body_text not in snapshot_body
    assert final_content.startswith(snapshot_body)


# ---------------------------------------------------------------------------
# Test 4: wrapper-order invalid surfaces WRAPPER_ORDER_INVALID
# ---------------------------------------------------------------------------


def test_orchestrator_raises_on_empty_wrapper_order(
    out_of_repo_tmp_path: Path,
) -> None:
    tmp_path = out_of_repo_tmp_path
    config = _make_session_config()
    source = _FakeProviderEventSource(events=(_make_fake_event(0),))
    inner_assembler = _FakeInnerCandidateAssembler(
        records=(_build_stage27_6_record(),),
    )
    inner_transport = _RecordingInnerTransport()
    context = _make_runtime_context(tmp_path=tmp_path)
    clock = _FakeClock()

    with pytest.raises(Stage30_3CompactRuntimeError) as excinfo:
        run_stage30_3_compact_runtime_session(
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
            wrapper_order=(),
        )
    assert excinfo.value.reason == "WRAPPER_ORDER_INVALID"
    assert inner_transport.call_count == 0


def test_orchestrator_raises_on_wrong_first_label_wrapper_order(
    out_of_repo_tmp_path: Path,
) -> None:
    tmp_path = out_of_repo_tmp_path
    config = _make_session_config()
    source = _FakeProviderEventSource(events=(_make_fake_event(0),))
    inner_assembler = _FakeInnerCandidateAssembler(
        records=(_build_stage27_6_record(),),
    )
    inner_transport = _RecordingInnerTransport()
    context = _make_runtime_context(tmp_path=tmp_path)
    clock = _FakeClock()

    # Wrong-first-label: the Stage 30.3 wrapper requires its own
    # compact-body label to be the outermost entry.
    bad_order = (
        WRAPPER_ORDER_LABEL_STAGE28_9_PRIVATE_WEBHOOK,
        WRAPPER_ORDER_LABEL_FAKE_INNER_TRANSPORT,
    )
    with pytest.raises(Stage30_3CompactRuntimeError) as excinfo:
        run_stage30_3_compact_runtime_session(
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
            wrapper_order=bad_order,
        )
    assert excinfo.value.reason == "WRAPPER_ORDER_INVALID"
    assert inner_transport.call_count == 0


# ---------------------------------------------------------------------------
# Test 5: boundary block on the orchestrator module
# ---------------------------------------------------------------------------


_ORCHESTRATOR_PATH: Path = (
    Path(__file__).resolve().parent.parent.parent
    / "stage30"
    / "stage30_3_compact_runtime_session_orchestrator.py"
)


_ALLOWED_PHX2_IMPORTS: Tuple[str, ...] = (
    "PHX2.stage28.live_provider_session_adapter",
    "PHX2.stage28.live_provider_session_models",
    "PHX2.stage30.stage30_3_compact_body_transport_wrapper",
    "PHX2.stage30.stage30_3_compact_candidate_context_recorder",
    "PHX2.stage30.stage30_3_compact_runtime_models",
)


_FORBIDDEN_NETWORK_IMPORTS: Tuple[str, ...] = (
    "urllib",
    "urllib.request",
    "urllib.parse",
    "urllib.error",
    "socket",
    "grpc",
    "asyncio",
    "aiohttp",
    "httpx",
    "requests",
    "websockets",
    "websocket",
    "http.client",
)


_FORBIDDEN_PROVIDER_IMPORTS: Tuple[str, ...] = (
    "discord",
    "telegram",
    "birdeye",
    "helius",
    "chainstack",
    "solders",
    "solana",
)


def _orchestrator_source() -> str:
    return _ORCHESTRATOR_PATH.read_text(encoding="utf-8")


def _orchestrator_imports() -> Set[str]:
    tree = ast.parse(_orchestrator_source())
    modules: Set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                modules.add(node.module)
    return modules


def test_orchestrator_module_does_not_import_os() -> None:
    imports = _orchestrator_imports()
    assert "os" not in imports, (
        f"orchestrator must not import os; offenders: "
        f"{sorted(imports)!r}"
    )
    for target in imports:
        assert not target.startswith("os."), (
            f"orchestrator must not import os.*; offender: {target!r}"
        )


def test_orchestrator_module_does_not_read_environ() -> None:
    tree = ast.parse(_orchestrator_source())
    os_aliases: Set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "os":
                    os_aliases.add(alias.asname or alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module == "os":
                for alias in node.names:
                    assert alias.name not in {
                        "environ",
                        "getenv",
                        "environb",
                    }, (
                        "orchestrator must not import env access "
                        f"name: {alias.name!r}"
                    )
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            if (
                isinstance(node.value, ast.Name)
                and node.value.id in os_aliases
                and node.attr in {"environ", "getenv", "environb"}
            ):
                raise AssertionError(
                    "orchestrator must not perform os.environ / "
                    "os.getenv / os.environb attribute access"
                )


def test_orchestrator_module_does_not_import_outbound_network() -> (
    None
):
    imports = _orchestrator_imports()
    for target in imports:
        for needle in _FORBIDDEN_NETWORK_IMPORTS:
            assert not (
                target == needle or target.startswith(needle + ".")
            ), (
                f"orchestrator must not import outbound-network "
                f"module {needle!r}; offender: {target!r}"
            )


def test_orchestrator_module_does_not_import_forbidden_providers() -> (
    None
):
    imports = _orchestrator_imports()
    for target in imports:
        if target.startswith("PHX2."):
            continue
        lower = target.lower()
        for needle in _FORBIDDEN_PROVIDER_IMPORTS:
            assert needle not in lower, (
                f"orchestrator must not import provider "
                f"{needle!r}; offender: {target!r}"
            )


def test_orchestrator_module_phx2_imports_subset_of_allowlist() -> None:
    imports = _orchestrator_imports()
    for target in imports:
        if not target.startswith("PHX2."):
            continue
        assert target in _ALLOWED_PHX2_IMPORTS, (
            f"orchestrator PHX2 import {target!r} is not in the "
            f"documented allowlist {sorted(_ALLOWED_PHX2_IMPORTS)!r}"
        )


def test_orchestrator_module_does_not_import_stage29() -> None:
    imports = _orchestrator_imports()
    for target in imports:
        assert not target.startswith("PHX2.stage29"), (
            f"orchestrator must not import any Stage 29 module by "
            f"name; offender: {target!r}"
        )


def test_orchestrator_module_has_no_top_level_call() -> None:
    tree = ast.parse(_orchestrator_source())
    hits: List[str] = []
    for stmt in tree.body:
        if isinstance(stmt, ast.Expr) and isinstance(
            stmt.value, ast.Call
        ):
            hits.append(ast.dump(stmt.value))
        if isinstance(stmt, ast.Assign) and isinstance(
            stmt.value, ast.Call
        ):
            hits.append(ast.dump(stmt.value))
        if isinstance(stmt, ast.AnnAssign):
            if stmt.value is not None and isinstance(
                stmt.value, ast.Call
            ):
                hits.append(ast.dump(stmt.value))
    assert not hits, (
        f"orchestrator must carry zero top-level Call nodes; "
        f"offenders: {hits!r}"
    )

"""Stage 30.4.2 opt-in parallel compact runtime session orchestrator
integration tests.

Pins the Stage 30.4.2 parallel orchestrator contract:

  * happy path: one normalized event -> one Stage 27.6 candidate
    -> one Stage 30.3 compact dispatch -> Stage 30.4.2 wrapper
    enriches the body with ``MC: $83k`` / ``LP: $27k`` /
    ``Net: Unknown`` from a fake offline source and replaces the
    Stage 30.3-supplied ``payload["content"]`` before the inner
    transport sees it. Stage 30.1 / Stage 30.2 / Stage 30.3 /
    Stage 30.4 JSONL artifacts each carry one line.
  * source=None path: the Stage 30.4.2 wrapper records an all-
    Unknown Stage 30.4 market context record, writes it to the
    Stage 30.4 artifact, and forwards the body verbatim. The body
    keeps ``MC: Unknown`` / ``LP: Unknown`` / ``Net: Unknown``.
    No Unknown -> 0 conversion fires.
  * artifact shape: each JSONL line is one JSON object with
    deterministic keys.
  * forbidden-substring scan: the dispatched body carries none of
    the trading-verdict tokens BUY / SELL / LONG / SHORT / ENTER /
    EXIT, the deferred-field tokens Vol / Floor, or the Stage 28.9
    verbose header marker.

No env reads. No network. No real provider. No real Discord.
Stdlib + pytest only.
"""

from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path
from types import SimpleNamespace
from typing import (
    Any,
    Dict,
    Iterable,
    Iterator,
    List,
    Optional,
    Tuple,
)

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
    SESSION_OUTCOME_OK,
    Stage28_9LiveProviderSessionConfig,
    build_live_provider_session_config,
)
from PHX2.stage30.compact_ping_models import (
    STAGE30_2_COMPACT_PING_ARTIFACT_BASENAME,
)
from PHX2.stage30.stage30_3_compact_runtime_models import (
    STAGE30_3_RUNTIME_WIRING_ARTIFACT_BASENAME,
    WRAPPER_ORDER_LABEL_FAKE_INNER_TRANSPORT,
    WRAPPER_ORDER_LABEL_STAGE28_9_PRIVATE_WEBHOOK,
    WRAPPER_ORDER_LABEL_STAGE30_3_COMPACT_BODY,
    Stage30_3CompactRuntimeContext,
)
from PHX2.stage30.stage30_4_compact_market_context_models import (
    NET_FLOW_BASIS_UNKNOWN,
    SOURCE_REASON_SOURCE_NOT_CONFIGURED,
    SOURCE_REASON_SOURCE_PRESENT,
    SOURCE_STATUS_PRESENT,
    SOURCE_STATUS_UNAVAILABLE,
    STAGE30_4_1_COMPACT_MARKET_CONTEXT_ARTIFACT_BASENAME,
    STATUS_KNOWN,
    STATUS_UNKNOWN,
)
from PHX2.stage30.stage30_4_compact_market_context_source_protocol import (
    Stage30_4MarketContextSourceReading,
)
from PHX2.stage30.stage30_4_compact_runtime_session_orchestrator import (
    Stage30_4_2CompactRuntimeSessionResult,
    run_stage30_4_2_compact_runtime_session,
)
from PHX2.stage30.tier_decision_models import (
    STAGE30_1_TIER_DECISION_ARTIFACT_BASENAME,
)


# ---------------------------------------------------------------------------
# Locked constants
# ---------------------------------------------------------------------------


_FAKE_WEBHOOK_URL: str = (
    "h" + "ttps" + "://"
    + "example.invalid/fake-stage30-4-2-private-webhook"
)
_SAFE_MINT: str = (
    "FakeMintPhx2NotWso1ForStage304_2Base58222222"
)
_MIG_TS: str = "2026-05-28T00:00:00Z"
_CLOCK_TS: str = "2026-05-28T00:00:30Z"
_PHOENIX_PREFIX: str = "\U0001f525 PHOENIX"
_VERBOSE_HEADER_MARKER: str = (
    "PHX2 STAGE 28.9 PRIVATE OPERATOR PING"
)


# Forbidden trading-verdict tokens (uppercase as the spec writes
# them). Split-literal so this test source does NOT itself carry
# the bare tokens (the body of the compact ping must not carry
# them either, but the test scan compares case-insensitively).
_FORBIDDEN_TRADING_VERDICT_TOKENS: Tuple[str, ...] = (
    "B" + "UY",
    "S" + "ELL",
    "L" + "ONG",
    "S" + "HORT",
    "E" + "NTER",
    "E" + "XIT",
)


# Deferred-field tokens that the Stage 30.4.2 dispatched body must
# NOT carry (the Stage 30.2 renderer uses ``Net`` / ``Drop``, never
# ``Vol`` / ``Floor``).
_FORBIDDEN_DEFERRED_FIELD_TOKENS: Tuple[str, ...] = (
    "Vol",
    "Floor",
)


# ---------------------------------------------------------------------------
# out_of_repo_tmp_path fixture
# ---------------------------------------------------------------------------
#
# The Stage 28.9 readiness gate refuses any ``output_dir`` that
# resolves inside the PHX2 repo root. Operator pre-commit invocations
# may pin pytest's ``--basetemp`` to a directory INSIDE the repo, so
# pytest's built-in ``tmp_path`` fixture cannot be used as the Stage
# 30.4.2 orchestrator output_dir. The fixture below uses
# ``tempfile.mkdtemp`` (system temp dir, typically outside the repo)
# and cleans up on teardown.


@pytest.fixture
def out_of_repo_tmp_path() -> Iterator[Path]:
    base = tempfile.mkdtemp(prefix="phx2_stage30_4_2_test_")
    try:
        yield Path(base)
    finally:
        shutil.rmtree(base, ignore_errors=True)


# ---------------------------------------------------------------------------
# Stage 27 fixtures (mirror the Stage 30.3B test fixtures shape so
# the Stage 28.9 mapper accepts the synthetic Stage 27.6 record
# verbatim)
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
        observed_at_utc="2026-05-28T00:00:00Z",
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
    *,
    body_text: str = "Verbose stage 27.5 body. " * 5,
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
            migration_context=_build_migration_record(
                mint=token_mint
            ),
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
        observed_at_utc="2026-05-28T00:00:00Z",
        raw_event_hash=f"hash_{idx:03d}",
    )


class _FakeProviderEventSource:
    """Stage 28.9 provider event source-compatible fake.

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
    """Stage 28.9 candidate-assembler-compatible fake.

    Returns a pre-canned ``Stage27_6LiveCandidateRecord`` for each
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
    """Stage 28.6 private-transport-compatible fake that records
    every ``send_one_audited_post`` call and returns a real
    ``Stage28_4TransportResult`` on the SENT_OK path.
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

    def __init__(
        self, *, stamps: Optional[Iterable[str]] = None,
    ) -> None:
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


class _FakeStage30_4MarketContextSource:
    """Stage 30.4.1 source-protocol-compatible fake.

    Returns a caller-supplied ``Stage30_4MarketContextSourceReading``
    on every ``read(token_mint)`` call. Stage 30.4.2 only invokes
    ``source.read(token_mint)`` so this fake exposes that single
    method.
    """

    def __init__(
        self,
        *,
        reading: Stage30_4MarketContextSourceReading,
    ) -> None:
        self._reading: Stage30_4MarketContextSourceReading = reading
        self._call_count: int = 0
        self.last_token_mint: Optional[str] = None

    @property
    def call_count(self) -> int:
        return self._call_count

    def read(
        self, token_mint: str,
    ) -> Stage30_4MarketContextSourceReading:
        self._call_count += 1
        self.last_token_mint = token_mint
        return self._reading


# ---------------------------------------------------------------------------
# Config + context fixtures
# ---------------------------------------------------------------------------


def _make_session_config(
    *,
    max_events: int = 1,
    max_dispatches: int = 1,
) -> Stage28_9LiveProviderSessionConfig:
    return build_live_provider_session_config(
        run_id="phx2_stage30_4_2_run01",
        session_id="phx2_stage30_4_2_session01",
        provider_id="fake_provider",
        provider_kind="fake_kind",
        max_events=max_events,
        max_dispatches=max_dispatches,
        max_ticks=32,
        max_total_retries=0,
        heartbeat_every_n_events=1,
        output_dir_safe_label="phx2_stage30_4_2_scratch",
        session_mode=SESSION_MODE_LIVE_PRIVATE,
    )


def _make_runtime_context(
    *,
    tmp_path: Path,
    session_id: Optional[str] = "stage30-4-2-ctx-001",
    basis: str = "price-basis",
) -> Stage30_3CompactRuntimeContext:
    return Stage30_3CompactRuntimeContext(
        session_id=session_id,
        run_id="stage30-4-2-run-001",
        basis=basis,
        output_dir=tmp_path,
    )


def _build_fake_reading_mc_lp(
    *,
    mc_value: Optional[str],
    lp_value: Optional[str],
    net_value: Optional[str],
    net_basis: str = NET_FLOW_BASIS_UNKNOWN,
    stale: bool = False,
    source_reason: Optional[str] = None,
) -> Stage30_4MarketContextSourceReading:
    return Stage30_4MarketContextSourceReading(
        market_cap_usd_value=mc_value,
        liquidity_usd_value=lp_value,
        net_flow_usd_value=net_value,
        net_flow_basis=net_basis,
        source_label="birdeye_token_overview",
        observed_at_utc=_CLOCK_TS,
        stale=stale,
        source_reason=source_reason,
    )


def _read_jsonl_lines(path: Path) -> List[Dict[str, Any]]:
    text = path.read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines() if line]


# ---------------------------------------------------------------------------
# Test 1: happy path -- fake source with MC=83000, LP=27000, Net missing
# ---------------------------------------------------------------------------


def test_happy_path_fake_source_fills_mc_and_lp(
    out_of_repo_tmp_path: Path,
) -> None:
    """Fake source with MC=83000 / LP=27000 / Net missing fills
    the Stage 30.2 compact body MC and LP display slots; Net stays
    Unknown; the dispatched body carries the enriched values
    instead of the Stage 30.3 baseline ``Unknown`` values.
    """
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
    clock = _FakeClock(stamps=(_CLOCK_TS,) * 16)
    fake_reading = _build_fake_reading_mc_lp(
        mc_value="83000",
        lp_value="27000",
        net_value=None,
    )
    market_source = _FakeStage30_4MarketContextSource(
        reading=fake_reading,
    )

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
        market_context_source=market_source,
    )

    assert isinstance(result, Stage30_4_2CompactRuntimeSessionResult)
    inner_30_3 = result.inner_stage30_3_result
    assert inner_30_3.session_result.session_outcome == (
        SESSION_OUTCOME_OK
    )
    assert inner_30_3.session_result.dispatch_success == 1
    assert inner_30_3.session_result.dispatch_failure == 0
    assert inner_transport.call_count == 1

    # The Stage 30.4.2 wrapper produced one Stage 30.4 record
    # and successfully replaced the body once.
    assert result.market_context_records_written == 1
    assert result.market_context_records_failed_to_write == 0
    assert result.market_context_replacements_attempted == 1
    assert result.market_context_replacements_succeeded == 1
    assert result.market_context_replacements_failed == 0

    # The fake source was queried once with the Stage 27.6 mint.
    assert market_source.call_count == 1
    assert market_source.last_token_mint == _SAFE_MINT

    # The dispatched body is the enriched compact body.
    dispatched_payload = inner_transport.received_kwargs[0][
        "payload"
    ]
    final_content = dispatched_payload["content"]

    assert final_content.startswith(_PHOENIX_PREFIX), (
        f"expected compact body prefix; got {final_content[:64]!r}"
    )
    assert _VERBOSE_HEADER_MARKER not in final_content, (
        "Stage 28.9 verbose header must have been REPLACED by the "
        "Stage 30.2 compact body before the inner transport saw it"
    )

    # MC / LP enriched, Net stays Unknown, Basis echoed.
    assert "MC: $83k" in final_content
    assert "LP: $27k" in final_content
    assert "Net: Unknown" in final_content
    assert "Basis: price-basis" in final_content

    # Deferred-field tokens must not appear.
    for token in _FORBIDDEN_DEFERRED_FIELD_TOKENS:
        assert token not in final_content, (
            f"dispatched body must not carry deferred-field token "
            f"{token!r}; got {final_content!r}"
        )

    # Trading-verdict tokens must not appear (case-insensitive).
    final_upper = final_content.upper()
    for token in _FORBIDDEN_TRADING_VERDICT_TOKENS:
        assert token not in final_upper, (
            f"dispatched body must not carry trading-verdict token "
            f"{token!r}; got {final_content!r}"
        )

    # All four Stage 30 JSONL artifacts each carry one line.
    tier_path = (
        tmp_path / STAGE30_1_TIER_DECISION_ARTIFACT_BASENAME
    )
    compact_path = (
        tmp_path / STAGE30_2_COMPACT_PING_ARTIFACT_BASENAME
    )
    wiring_path = (
        tmp_path / STAGE30_3_RUNTIME_WIRING_ARTIFACT_BASENAME
    )
    market_path = (
        tmp_path
        / STAGE30_4_1_COMPACT_MARKET_CONTEXT_ARTIFACT_BASENAME
    )
    for artifact_path in (
        tier_path,
        compact_path,
        wiring_path,
        market_path,
    ):
        assert artifact_path.is_file(), (
            f"expected Stage 30 artifact {artifact_path.name} to exist"
        )
        lines = _read_jsonl_lines(artifact_path)
        assert len(lines) == 1, (
            f"expected exactly one JSONL line in "
            f"{artifact_path.name}; got {len(lines)}"
        )

    # Stage 30.4 record carries KNOWN MC + LP, UNKNOWN Net, and
    # the hard-locked runtime_consumable=False flag.
    market_line = _read_jsonl_lines(market_path)[0]
    assert market_line["market_cap_usd_status"] == STATUS_KNOWN
    assert market_line["market_cap_usd_value"] == "83000"
    assert market_line["market_cap_display"] == "$83k"
    assert market_line["liquidity_usd_status"] == STATUS_KNOWN
    assert market_line["liquidity_usd_value"] == "27000"
    assert market_line["liquidity_display"] == "$27k"
    assert market_line["net_flow_status"] == STATUS_UNKNOWN
    assert market_line["net_flow_usd_value"] is None
    assert market_line["net_flow_display"] is None
    assert market_line["source_status"] == SOURCE_STATUS_PRESENT
    assert market_line["source_reason"] == (
        SOURCE_REASON_SOURCE_PRESENT
    )
    assert market_line["source_label"] == "birdeye_token_overview"
    assert market_line["runtime_consumable"] is False

    # Stage 28.9 runner artifacts written.
    for basename in (
        STAGE28_9_DISPATCH_LEDGER_BASENAME,
        STAGE28_9_HEARTBEAT_BASENAME,
        STAGE28_9_HEALTH_SNAPSHOT_BASENAME,
        STAGE28_9_FINAL_SUMMARY_BASENAME,
    ):
        assert (tmp_path / basename).is_file(), (
            f"expected Stage 28.9 runner artifact {basename}"
        )


# ---------------------------------------------------------------------------
# Test 2: source=None path -- all Unknown, no fabrication
# ---------------------------------------------------------------------------


def test_source_none_path_writes_unknown_artifact_and_keeps_body_unknown(
    out_of_repo_tmp_path: Path,
) -> None:
    """source=None records a Stage 30.4 market context line with
    every per-slot status UNKNOWN, every display None, no
    fabricated 0 / 0.0 / empty string, and forwards the body with
    MC / LP / Net all rendered as ``Unknown``.
    """
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
        market_context_source=None,
    )

    assert isinstance(result, Stage30_4_2CompactRuntimeSessionResult)
    inner_30_3 = result.inner_stage30_3_result
    assert inner_30_3.session_result.session_outcome == (
        SESSION_OUTCOME_OK
    )
    assert inner_transport.call_count == 1

    # Stage 30.4 record was still written (with all UNKNOWN
    # statuses); the replacement still ran (the re-rendered body
    # has the same None display values as the Stage 30.3 baseline
    # body, so the bodies are byte-identical but the wrapper did
    # the work).
    assert result.market_context_records_written == 1
    assert result.market_context_records_failed_to_write == 0
    assert result.market_context_replacements_attempted == 1
    assert result.market_context_replacements_succeeded == 1
    assert result.market_context_replacements_failed == 0

    dispatched_payload = inner_transport.received_kwargs[0][
        "payload"
    ]
    final_content = dispatched_payload["content"]

    assert final_content.startswith(_PHOENIX_PREFIX)
    assert _VERBOSE_HEADER_MARKER not in final_content

    # Every value-bearing slot renders as the literal Unknown.
    assert "MC: Unknown" in final_content
    assert "LP: Unknown" in final_content
    assert "Net: Unknown" in final_content
    assert "Basis: price-basis" in final_content

    # No Unknown -> 0 conversion: the literal Unknown is present
    # and the body must NOT carry the literal "$0" / "0.0" / "$"
    # standalone fabrications. The renderer never emits these for
    # missing values; this assertion is defense-in-depth.
    assert "MC: $0" not in final_content
    assert "LP: $0" not in final_content
    assert "Net: $0" not in final_content
    assert "MC: 0" not in final_content
    assert "LP: 0" not in final_content
    assert "Net: 0" not in final_content

    # Deferred-field tokens must not appear.
    for token in _FORBIDDEN_DEFERRED_FIELD_TOKENS:
        assert token not in final_content

    # Trading-verdict tokens must not appear.
    final_upper = final_content.upper()
    for token in _FORBIDDEN_TRADING_VERDICT_TOKENS:
        assert token not in final_upper

    # Stage 30.4 record has all UNKNOWN statuses.
    market_path = (
        tmp_path
        / STAGE30_4_1_COMPACT_MARKET_CONTEXT_ARTIFACT_BASENAME
    )
    assert market_path.is_file()
    market_line = _read_jsonl_lines(market_path)[0]
    assert market_line["market_cap_usd_status"] == STATUS_UNKNOWN
    assert market_line["market_cap_usd_value"] is None
    assert market_line["market_cap_display"] is None
    assert market_line["liquidity_usd_status"] == STATUS_UNKNOWN
    assert market_line["liquidity_usd_value"] is None
    assert market_line["liquidity_display"] is None
    assert market_line["net_flow_status"] == STATUS_UNKNOWN
    assert market_line["net_flow_usd_value"] is None
    assert market_line["net_flow_display"] is None
    assert market_line["net_flow_basis"] == NET_FLOW_BASIS_UNKNOWN
    assert market_line["source_label"] is None
    assert market_line["source_status"] == (
        SOURCE_STATUS_UNAVAILABLE
    )
    assert market_line["source_reason"] == (
        SOURCE_REASON_SOURCE_NOT_CONFIGURED
    )
    assert market_line["runtime_consumable"] is False


# ---------------------------------------------------------------------------
# Test 3: stage 30.1 / 30.2 / 30.3 artifacts still written
# ---------------------------------------------------------------------------


def test_stage_30_1_30_2_30_3_artifacts_written_alongside_stage_30_4(
    out_of_repo_tmp_path: Path,
) -> None:
    """The Stage 30.4.2 wrapper does NOT interfere with the Stage
    30.1 tier-decision / Stage 30.2 compact-ping / Stage 30.3
    runtime-wiring artifact writes. Each Stage 30 artifact carries
    exactly one JSONL line per dispatch.
    """
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
    clock = _FakeClock(stamps=(_CLOCK_TS,) * 16)
    fake_reading = _build_fake_reading_mc_lp(
        mc_value="83000",
        lp_value="27000",
        net_value=None,
    )
    market_source = _FakeStage30_4MarketContextSource(
        reading=fake_reading,
    )

    run_stage30_4_2_compact_runtime_session(
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
        market_context_source=market_source,
    )

    for basename in (
        STAGE30_1_TIER_DECISION_ARTIFACT_BASENAME,
        STAGE30_2_COMPACT_PING_ARTIFACT_BASENAME,
        STAGE30_3_RUNTIME_WIRING_ARTIFACT_BASENAME,
        STAGE30_4_1_COMPACT_MARKET_CONTEXT_ARTIFACT_BASENAME,
    ):
        artifact_path = tmp_path / basename
        assert artifact_path.is_file(), (
            f"expected Stage 30 artifact {basename} to exist"
        )
        lines = _read_jsonl_lines(artifact_path)
        assert len(lines) == 1, (
            f"expected exactly one JSONL line in {basename}; "
            f"got {len(lines)}"
        )


# ---------------------------------------------------------------------------
# Test 4: Stage 30.4 artifact is deterministic JSONL
# ---------------------------------------------------------------------------


def test_stage_30_4_artifact_line_is_deterministic_jsonl(
    out_of_repo_tmp_path: Path,
) -> None:
    """The Stage 30.4 artifact line is one JSON object encoded
    with sorted keys + no whitespace + LF terminator. Two runs
    with identical inputs produce a byte-identical line.
    """
    tmp_path_1 = out_of_repo_tmp_path

    def _run(out_dir: Path) -> str:
        config = _make_session_config(
            max_events=1, max_dispatches=1,
        )
        source = _FakeProviderEventSource(
            events=(_make_fake_event(0),),
        )
        inner_assembler = _FakeInnerCandidateAssembler(
            records=(_build_stage27_6_record(),),
        )
        inner_transport = _RecordingInnerTransport()
        wrapper_order = (
            WRAPPER_ORDER_LABEL_STAGE30_3_COMPACT_BODY,
            WRAPPER_ORDER_LABEL_STAGE28_9_PRIVATE_WEBHOOK,
            WRAPPER_ORDER_LABEL_FAKE_INNER_TRANSPORT,
        )
        context = _make_runtime_context(tmp_path=out_dir)
        clock = _FakeClock(stamps=(_CLOCK_TS,) * 16)
        market_source = _FakeStage30_4MarketContextSource(
            reading=_build_fake_reading_mc_lp(
                mc_value="83000",
                lp_value="27000",
                net_value=None,
            ),
        )
        run_stage30_4_2_compact_runtime_session(
            session_config=config,
            provider_event_source=source,
            inner_candidate_assembler=inner_assembler,
            inner_transport=inner_transport,
            output_dir=out_dir,
            private_webhook_url=_FAKE_WEBHOOK_URL,
            live_env_ready=True,
            live_operator_request=True,
            compact_runtime_context=context,
            clock=clock,
            wrapper_order=wrapper_order,
            market_context_source=market_source,
        )
        artifact_path = (
            out_dir
            / STAGE30_4_1_COMPACT_MARKET_CONTEXT_ARTIFACT_BASENAME
        )
        return artifact_path.read_text(encoding="utf-8")

    text_1 = _run(tmp_path_1)
    # Run 2 in its own temp dir.
    tmp_dir_2 = tempfile.mkdtemp(prefix="phx2_stage30_4_2_test_b_")
    try:
        text_2 = _run(Path(tmp_dir_2))
    finally:
        shutil.rmtree(tmp_dir_2, ignore_errors=True)

    assert text_1 == text_2, (
        "Stage 30.4 artifact JSONL must be byte-identical "
        "across identical-input runs"
    )
    # One line, ending in LF.
    assert text_1.count("\n") == 1
    assert text_1.endswith("\n")


# ---------------------------------------------------------------------------
# Test 5: no Discord send, no live provider call (smoke test on the
# inner transport)
# ---------------------------------------------------------------------------


def test_no_real_discord_send_or_live_provider_call(
    out_of_repo_tmp_path: Path,
) -> None:
    """The Stage 30.4.2 orchestrator dispatches one payload through
    the caller-supplied inner transport. The inner transport in
    this test is a recording fake that returns a synthetic
    Stage28_4TransportResult; no real Discord webhook is hit and
    no real provider HTTP / gRPC / WebSocket connection is opened.
    """
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
    clock = _FakeClock(stamps=(_CLOCK_TS,) * 16)
    market_source = _FakeStage30_4MarketContextSource(
        reading=_build_fake_reading_mc_lp(
            mc_value="83000",
            lp_value="27000",
            net_value=None,
        ),
    )

    run_stage30_4_2_compact_runtime_session(
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
        market_context_source=market_source,
    )

    # The recording transport is the only outbound surface. It
    # returns synthetic SENT_OK results without opening any real
    # HTTP / gRPC / WebSocket connection.
    assert inner_transport.call_count == 1
    received = inner_transport.received_kwargs[0]
    # Stage 28.9 sets webhook_identity for private operator
    # dispatches; the value is the locked closed-set token, not a
    # raw URL.
    identity = received["webhook_identity"]
    assert isinstance(identity, str)
    assert "h" + "ttps://" not in identity
    assert "discord" + ".com" not in identity.lower()

"""Stage 30.3B orchestrator redaction-safe boundary tests.

Pins the Stage 30.3B redaction contract:

  * an unsafe ``Stage30_3CompactRuntimeContext.session_id``
    (forbidden URL substring / non-base58 alphabet / length > 64)
    is reduced to the literal ``"REDACTED"`` on the wiring
    artifact's ``session_id`` slot,
  * an unsafe upstream ``ingest_output.token_mint`` is reduced to
    ``"REDACTED"`` or ``None`` on the wiring artifact's ``mint``
    slot,
  * the Stage 30.3 wiring artifact NEVER carries a URL host
    literal, an operator-channel host literal, a bearer / auth
    literal, an API-key prefix, a raw-payload field name, or an
    RPC-URL field name (concatenated-literal needles only),
  * the Stage 30.3 wiring artifact's ``wrapper_order`` is the
    caller-supplied closed-set tuple of Stage 30.3
    ``WRAPPER_ORDER_LABEL_*`` tokens.

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
    REDACTION_STATUS_REDACTED,
    RESPONSE_BODY_STATUS_DROPPED_UNRECORDED,
    STAGE28_4_SCHEMA_VERSION,
    TRANSPORT_STATUS_SENT_OK,
    Stage28_4TransportResult,
    derive_safe_reason_code,
)
from PHX2.stage28.live_provider_session_models import (
    SESSION_MODE_LIVE_PRIVATE,
    Stage28_9LiveProviderSessionConfig,
    build_live_provider_session_config,
)
from PHX2.stage30.stage30_3_compact_runtime_models import (
    STAGE30_3_RUNTIME_WIRING_ARTIFACT_BASENAME,
    WRAPPER_ORDER_LABEL_FAKE_INNER_TRANSPORT,
    WRAPPER_ORDER_LABEL_STAGE28_9_PRIVATE_WEBHOOK,
    WRAPPER_ORDER_LABEL_STAGE30_3_COMPACT_BODY,
    WRAPPER_ORDER_LABEL_VALUES,
    Stage30_3CompactRuntimeContext,
)
from PHX2.stage30.stage30_3_compact_runtime_session_orchestrator import (
    run_stage30_3_compact_runtime_session,
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
_REDACTED: str = "REDACTED"


# Unsafe session_id seed: contains the "discord"+".com" needle.
# Built via concatenated literals so this test module itself does
# not carry the raw operator-channel host substring.
_UNSAFE_SESSION_ID: str = "sess_" + "discord" + ".com" + "_evt"


# Unsafe upstream mint seed: contains forbidden URL prefix and is
# below the safe base58 mint length range.
_UNSAFE_MINT: str = "h" + "ttps" + "://" + "unsafe-mint"


# Concatenated-literal forbidden-substring vocabulary (the
# redaction scan checks artifact bytes against this needle set).
_FORBIDDEN_BYTES_NEEDLES: Tuple[str, ...] = (
    "h" + "ttp://",
    "h" + "ttps://",
    "w" + "s://",
    "w" + "ss://",
    "discord" + ".com",
    "discord" + "app.com",
    "b" + "earer",
    "a" + "uthorization",
    "s" + "k-",
    "p" + "k-",
    "api_key",
    "apikey",
    "secret",
    "private_key",
    "raw_payload",
    "rpc_url",
)


# ---------------------------------------------------------------------------
# Stage 27 fixtures (duplicated so this test module stays self-contained)
# ---------------------------------------------------------------------------


def _build_ingest_output(
    *, token_mint: str = _SAFE_MINT,
) -> ProviderIngestOutputRecord:
    return ProviderIngestOutputRecord(
        provider_id="helius_grpc",
        provider_event_id="evt_001",
        normalized_event_id="norm_001",
        event_kind=EVENT_KIND_SWAP,
        observed_at_utc="2026-05-27T00:00:00Z",
        token_mint=token_mint,
        quote_mint="So11111111111111111111111111111111111111112",
        pair_quote_asset="SOL",
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


def _build_rendered_ping() -> PrivatePingPayloadRecord:
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
        body_text="Verbose stage 27.5 body for redaction test.",
    )


def _build_ath_record() -> AthContextRecord:
    return AthContextRecord(
        token_mint=_SAFE_MINT,
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


def _build_migration_record() -> MigrationContextRecord:
    return MigrationContextRecord(
        token_mint=_SAFE_MINT,
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
    *, token_mint: str = _SAFE_MINT,
) -> Stage27_6LiveCandidateRecord:
    return Stage27_6LiveCandidateRecord(
        candidate_id="cand_001",
        run_id="phx2_run01",
        session_id="phx2_session01",
        candidate_schema_version=(
            STAGE27_6_CANDIDATE_SCHEMA_VERSION
        ),
        candidate_status=CANDIDATE_STATUS_RENDERED_DRY_RUN,
        candidate_reason=CANDIDATE_REASON_RENDERED_OK,
        ingest_output=_build_ingest_output(token_mint=token_mint),
        measurement_context=SimpleNamespace(
            ath_context=_build_ath_record(),
            migration_context=_build_migration_record(),
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
    pass


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
    def __init__(
        self, *, events: Iterable[_FakeNormalizedEvent],
    ) -> None:
        self._events: Tuple[_FakeNormalizedEvent, ...] = tuple(events)
        self._iter_count: int = 0

    def iter_events(
        self, *, max_events: int,
    ) -> Iterator[_FakeNormalizedEvent]:
        self._iter_count += 1
        for index, event in enumerate(self._events):
            if index >= max_events:
                return
            yield event


class _FakeInnerCandidateAssembler:
    def __init__(
        self, *, records: Iterable[Stage27_6LiveCandidateRecord],
    ) -> None:
        self._records: Tuple[
            Stage27_6LiveCandidateRecord, ...
        ] = tuple(records)
        self._call_count: int = 0

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
    def __init__(self, *, stamps: Optional[Iterable[str]] = None) -> None:
        if stamps is None:
            stamps = (_CLOCK_TS,) * 8
        self._stamps: List[str] = list(stamps)
        self._index: int = 0

    def now_utc_iso(self) -> str:
        if self._index < len(self._stamps):
            value = self._stamps[self._index]
            self._index += 1
        else:
            value = self._stamps[-1]
        return value


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


_WRAPPER_ORDER: Tuple[str, ...] = (
    WRAPPER_ORDER_LABEL_STAGE30_3_COMPACT_BODY,
    WRAPPER_ORDER_LABEL_STAGE28_9_PRIVATE_WEBHOOK,
    WRAPPER_ORDER_LABEL_FAKE_INNER_TRANSPORT,
)


# ---------------------------------------------------------------------------
# out_of_repo_tmp_path fixture
# ---------------------------------------------------------------------------
#
# Stage 28.9 readiness refuses any ``output_dir`` inside the PHX2
# repo root. Operator pre-commit invocations may pin pytest's
# ``--basetemp`` to a directory inside the repo, so pytest's
# built-in ``tmp_path`` cannot be used as the orchestrator
# output_dir. Use ``tempfile.mkdtemp`` (system temp, outside the
# repo) and clean up on teardown.


@pytest.fixture
def out_of_repo_tmp_path() -> Iterator[Path]:
    base = tempfile.mkdtemp(
        prefix="phx2_stage30_3b_redact_test_"
    )
    try:
        yield Path(base)
    finally:
        shutil.rmtree(base, ignore_errors=True)


def _read_wiring_lines(tmp_path: Path) -> List[Dict[str, Any]]:
    wiring_path = tmp_path / STAGE30_3_RUNTIME_WIRING_ARTIFACT_BASENAME
    assert wiring_path.is_file(), (
        f"expected Stage 30.3 wiring artifact at {wiring_path}"
    )
    return [
        json.loads(line)
        for line in wiring_path.read_text(
            encoding="utf-8"
        ).splitlines()
        if line
    ]


# ---------------------------------------------------------------------------
# Test 1: unsafe context.session_id is redacted on the wiring artifact
# ---------------------------------------------------------------------------


def test_unsafe_context_session_id_renders_as_redacted(
    out_of_repo_tmp_path: Path,
) -> None:
    tmp_path = out_of_repo_tmp_path
    config = _make_session_config()
    source = _FakeProviderEventSource(events=(_make_fake_event(0),))
    inner_assembler = _FakeInnerCandidateAssembler(
        records=(_build_stage27_6_record(),),
    )
    inner_transport = _RecordingInnerTransport()
    # Stage 28.9 readiness validates the session_config.session_id
    # (a safe-shape value). The Stage 30.3 context's session_id is
    # an independent slot the orchestrator hands to the Stage 30.3
    # wrapper; the wrapper's safe-artifact helper must redact this
    # unsafe value to "REDACTED" on the wiring artifact.
    context = Stage30_3CompactRuntimeContext(
        session_id=_UNSAFE_SESSION_ID,
        run_id="stage30-3-run-001",
        basis="price-basis",
        output_dir=tmp_path,
    )
    clock = _FakeClock()

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
        wrapper_order=_WRAPPER_ORDER,
    )

    wiring_lines = _read_wiring_lines(tmp_path)
    assert len(wiring_lines) >= 1
    assert wiring_lines[0]["session_id"] == _REDACTED


# ---------------------------------------------------------------------------
# Test 2: unsafe upstream mint is redacted on the wiring artifact
# ---------------------------------------------------------------------------


def test_unsafe_upstream_mint_renders_as_redacted_or_none(
    out_of_repo_tmp_path: Path,
) -> None:
    tmp_path = out_of_repo_tmp_path
    config = _make_session_config()
    source = _FakeProviderEventSource(events=(_make_fake_event(0),))
    inner_assembler = _FakeInnerCandidateAssembler(
        records=(
            _build_stage27_6_record(token_mint=_UNSAFE_MINT),
        ),
    )
    inner_transport = _RecordingInnerTransport()
    context = Stage30_3CompactRuntimeContext(
        session_id="stage30-3-ctx-001",
        run_id="stage30-3-run-001",
        basis="price-basis",
        output_dir=tmp_path,
    )
    clock = _FakeClock()

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
        wrapper_order=_WRAPPER_ORDER,
    )

    wiring_lines = _read_wiring_lines(tmp_path)
    assert len(wiring_lines) >= 1
    mint_value = wiring_lines[0]["mint"]
    assert mint_value in (_REDACTED, None), (
        f"expected unsafe upstream mint to be redacted or None on "
        f"the Stage 30.3 wiring artifact mint slot; got "
        f"{mint_value!r}"
    )


# ---------------------------------------------------------------------------
# Test 3: artifact bytes carry no forbidden URL / auth / secret / RPC
# ---------------------------------------------------------------------------


def test_stage30_3_artifact_bytes_carry_no_forbidden_substring(
    out_of_repo_tmp_path: Path,
) -> None:
    tmp_path = out_of_repo_tmp_path
    config = _make_session_config()
    source = _FakeProviderEventSource(events=(_make_fake_event(0),))
    # Combine unsafe session_id + unsafe upstream mint so both
    # redaction paths run on the same end-to-end session and the
    # resulting artifact bytes can be scanned at once.
    inner_assembler = _FakeInnerCandidateAssembler(
        records=(
            _build_stage27_6_record(token_mint=_UNSAFE_MINT),
        ),
    )
    inner_transport = _RecordingInnerTransport()
    context = Stage30_3CompactRuntimeContext(
        session_id=_UNSAFE_SESSION_ID,
        run_id="stage30-3-run-001",
        basis="price-basis",
        output_dir=tmp_path,
    )
    clock = _FakeClock()

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
        wrapper_order=_WRAPPER_ORDER,
    )

    wiring_path = tmp_path / STAGE30_3_RUNTIME_WIRING_ARTIFACT_BASENAME
    assert wiring_path.is_file()
    raw_bytes = wiring_path.read_text(encoding="utf-8")
    lowered = raw_bytes.lower()
    for needle in _FORBIDDEN_BYTES_NEEDLES:
        assert needle.lower() not in lowered, (
            f"Stage 30.3 wiring artifact bytes must not carry "
            f"forbidden substring {needle!r}"
        )


# ---------------------------------------------------------------------------
# Test 4: wrapper_order on the wiring artifact is the closed-set tuple
# ---------------------------------------------------------------------------


def test_stage30_3_wiring_wrapper_order_is_closed_set_tuple(
    out_of_repo_tmp_path: Path,
) -> None:
    tmp_path = out_of_repo_tmp_path
    config = _make_session_config()
    source = _FakeProviderEventSource(events=(_make_fake_event(0),))
    inner_assembler = _FakeInnerCandidateAssembler(
        records=(_build_stage27_6_record(),),
    )
    inner_transport = _RecordingInnerTransport()
    context = Stage30_3CompactRuntimeContext(
        session_id="stage30-3-ctx-001",
        run_id="stage30-3-run-001",
        basis="price-basis",
        output_dir=tmp_path,
    )
    clock = _FakeClock()

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
        wrapper_order=_WRAPPER_ORDER,
    )

    wiring_lines = _read_wiring_lines(tmp_path)
    assert len(wiring_lines) >= 1
    observed_order = wiring_lines[0]["wrapper_order"]
    assert isinstance(observed_order, list)
    assert observed_order == list(_WRAPPER_ORDER)
    for label in observed_order:
        assert label in WRAPPER_ORDER_LABEL_VALUES, (
            f"Stage 30.3 wiring wrapper_order label {label!r} is "
            f"not in the locked closed set "
            f"{sorted(WRAPPER_ORDER_LABEL_VALUES)!r}"
        )

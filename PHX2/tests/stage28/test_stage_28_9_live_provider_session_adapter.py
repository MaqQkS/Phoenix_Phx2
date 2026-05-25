"""Stage 28.9 private live provider session adapter tests.

Covers:

  * the Stage 27.6 -> Stage 28.6 candidate mapper preserves the
    Stage 27 safety suppressions (UNKNOWN pair, DISAGREE pair,
    USDC observe-only, STALE price, MISSING price, malformed),
  * the Stage 28.9 Discord payload carries the Stage 29-pending
    filter-enforcement marker + the private-operator-only policy
    mode marker + no BUY / SELL / approved / execute / trade /
    position / wallet / subscriber / paid / public language,
  * the orchestrator refuses BEFORE any provider call when
    readiness fails (live not ready / webhook missing / not
    operator-requested / output dir unsafe / provider unsafe /
    bounds invalid),
  * the orchestrator drives the Stage 28.6 bounded private
    session runner with a fake provider event source + fake
    assembler + Stage 28.6 fake transport,
  * exactly one Stage 28.6 fake transport call per dispatchable
    candidate,
  * the orchestrator stops at ``max_events``,
  * the orchestrator surfaces the Stage 28.2 dedupe-duplicate
    suppression count via the Stage 28.9 result,
  * the Stage 28.9 result carries no webhook URL, no provider
    endpoint, no raw env value.

No network. No env reads. No real provider. No real Discord.
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from typing import Iterable, Iterator, Optional

import pytest

from PHX2.stage27.live_candidate_assembler import (
    CANDIDATE_REASON_ARTIFACT_WRITE_FAILED,
    CANDIDATE_REASON_DISAGREE_PAIR_LIVE_SUPPRESSED,
    CANDIDATE_REASON_DUPLICATE_RUN_LOCAL,
    CANDIDATE_REASON_OK,
    CANDIDATE_REASON_RENDERED_OK,
    CANDIDATE_REASON_UNEXPECTED_ERROR,
    CANDIDATE_REASON_UNKNOWN_PAIR_LIVE_SUPPRESSED,
    CANDIDATE_REASON_USDC_OBSERVE_ONLY,
    CANDIDATE_STATUS_ARTIFACT_WRITE_FAILED,
    CANDIDATE_STATUS_ASSEMBLED,
    CANDIDATE_STATUS_ERROR,
    CANDIDATE_STATUS_RENDERED_DRY_RUN,
    CANDIDATE_STATUS_SKIPPED_DUPLICATE,
    CANDIDATE_STATUS_SKIPPED_UNSUPPORTED_EVENT,
    CANDIDATE_STATUS_SUPPRESSED_DISAGREE_PAIR,
    CANDIDATE_STATUS_SUPPRESSED_UNKNOWN_PAIR,
    STAGE27_6_CANDIDATE_SCHEMA_VERSION,
    Stage27_6LiveCandidateRecord,
)
from PHX2.stage27.private_ping_models import (
    PrivatePingPayloadRecord,
    STAGE27_5_PING_SCHEMA_VERSION,
)
from PHX2.stage27.provider_ingest_models import (
    COMPOSITION_REASON_OK,
    COMPOSITION_STATUS_CLASSIFIED_DISAGREE,
    COMPOSITION_STATUS_CLASSIFIED_UNKNOWN,
    COMPOSITION_STATUS_COMPOSED,
    COMPOSITION_STATUS_ERROR,
    EVENT_KIND_SWAP,
    ProviderIngestOutputRecord,
    STAGE27_3_SCHEMA_VERSION,
)
from PHX2.stage28.audited_http_transport_models import (
    TRANSPORT_STATUS_SENT_OK,
    WEBHOOK_IDENTITY_PRIVATE_OPERATOR,
)
from PHX2.stage28.live_provider_session_adapter import (
    FILTER_ENFORCEMENT_STATUS_NOT_ACTIVE_STAGE_29_PENDING,
    STAGE28_9_DISPATCH_LEDGER_BASENAME,
    STAGE28_9_FINAL_SUMMARY_BASENAME,
    STAGE28_9_HEALTH_SNAPSHOT_BASENAME,
    STAGE28_9_HEARTBEAT_BASENAME,
    STAGE28_9_PING_TYPE_LABEL,
    Stage28_9DefaultCandidateAssembler,
    Stage28_9FakeProviderEventSource,
    derive_output_dir_safe_label,
    evaluate_stage28_9_readiness,
    map_stage27_candidate_to_stage28_6_event,
    render_stage28_9_discord_content,
    run_stage28_9_live_provider_session,
)
from PHX2.stage28.live_provider_session_models import (
    POLICY_MODE_PRIVATE_OPERATOR_ONLY,
    REFUSAL_REASON_BOUNDS_INVALID,
    REFUSAL_REASON_NOT_LIVE,
    REFUSAL_REASON_NOT_OPERATOR_REQUESTED,
    REFUSAL_REASON_OUTPUT_DIR_UNSAFE,
    REFUSAL_REASON_PROVIDER_UNSAFE,
    REFUSAL_REASON_WEBHOOK_MISSING,
    SESSION_MODE_LIVE_PRIVATE,
    SESSION_OUTCOME_OK,
    SESSION_OUTCOME_REFUSED,
    Stage28_9LiveProviderSessionConfig,
    Stage28_9LiveProviderSessionResult,
    build_live_provider_session_config,
)
from PHX2.stage28.session_runner_models import (
    CANDIDATE_PAIR_STATUS_DISAGREE,
    CANDIDATE_PAIR_STATUS_OK,
    CANDIDATE_PAIR_STATUS_UNKNOWN,
    CANDIDATE_PAIR_STATUS_USDC_OBSERVE_ONLY,
    CANDIDATE_PRICE_STATUS_MISSING,
    CANDIDATE_PRICE_STATUS_OK,
    CANDIDATE_PRICE_STATUS_STALE,
    Stage28_6CandidateEvent,
    Stage28_6FakeTransport,
)


# ---------------------------------------------------------------------------
# Fake URL constant (must NEVER point at a real Discord webhook host).
# ---------------------------------------------------------------------------


_FAKE_WEBHOOK_URL: str = (
    "h" + "ttps" + "://" + "example.invalid/fake-stage28-9-webhook"
)


# ---------------------------------------------------------------------------
# out_of_repo_tmp_path fixture
# ---------------------------------------------------------------------------
#
# The Stage 28.9 readiness gate refuses any ``output_dir`` that
# resolves inside the PHX2 repo root. The required pytest
# invocation uses ``--basetemp=PHX2/.pytest_tmp`` (i.e. pytest's
# built-in ``tmp_path`` fixture lives INSIDE the repo), so the
# Stage 28.9 orchestrator happy-path tests need a separate
# fixture that allocates scratch space OUTSIDE the repo. The
# fixture below uses ``tempfile.mkdtemp`` (which honours the
# system temp dir, typically ``/tmp`` on POSIX and ``%TEMP%`` on
# Windows, both outside the repo) and cleans up after itself.


@pytest.fixture
def out_of_repo_tmp_path() -> Iterator[Path]:
    """Yield an absolute ``Path`` to an empty temp directory
    that is NOT inside the PHX2 repo root.

    Pure / deterministic per-test scratch space; cleans up on
    teardown.
    """
    base = tempfile.mkdtemp(prefix="phx2_stage28_9_test_")
    try:
        yield Path(base)
    finally:
        shutil.rmtree(base, ignore_errors=True)


# ---------------------------------------------------------------------------
# Helpers: build Stage 27 records by hand
# ---------------------------------------------------------------------------


def _make_ingest(
    *,
    token_mint: str = "SoMintFakeAbc123",
    pair_quote_asset: str = "SOL",
    event_kind: str = EVENT_KIND_SWAP,
    composition_status: str = COMPOSITION_STATUS_COMPOSED,
    composition_reason: str = COMPOSITION_REASON_OK,
    provider_event_id: str = "evt_001",
    normalized_event_id: str = "norm_001",
) -> ProviderIngestOutputRecord:
    return ProviderIngestOutputRecord(
        provider_id="helius_grpc",
        provider_event_id=provider_event_id,
        normalized_event_id=normalized_event_id,
        event_kind=event_kind,
        observed_at_utc="2026-05-23T12:00:00Z",
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
        raw_capture_ref="raw_hash_abc",
        source_summary="source_summary_abc",
        composition_status=composition_status,
        composition_reason=composition_reason,
        schema_version=STAGE27_3_SCHEMA_VERSION,
    )


def _make_rendered_ping(
    *,
    price_status: str = "PRESENT",
    pair_quote_asset: str = "SOL",
    render_status: str = "RENDERED",
    body_text: str = "PHX2 STAGE 27.5 PRIVATE DRY-RUN PING\nfoo: bar",
) -> PrivatePingPayloadRecord:
    return PrivatePingPayloadRecord(
        ping_id="ping_001",
        run_id="phx2_run01",
        session_id="phx2_session01",
        ping_schema_version=STAGE27_5_PING_SCHEMA_VERSION,
        provider_id="helius_grpc",
        provider_event_id="evt_001",
        normalized_event_id="norm_001",
        raw_capture_ref="raw_hash_abc",
        token_mint="SoMintFakeAbc123",
        quote_mint="So11111111111111111111111111111111111111112",
        pair_type="PUMP_SOL",
        quote_asset=pair_quote_asset,
        bonding_curve_version="V1",
        pair_detection_status="CONFIRMED",
        pair_detection_confidence="HIGH",
        pair_detection_reason="OK",
        pair_live_policy="LIVE_OK_SOL",
        calibration_lane="EXISTING_SOL_LANE",
        measurement_status="COMPLETE",
        measurement_warnings=(),
        price_status=price_status,
        price_value_display="1.23",
        price_unit_display="USD",
        price_source_display="fake_source",
        price_staleness_seconds_display="5",
        ath_status="PRESENT",
        ath_value_display="2.00",
        ath_unit_display="USD",
        ath_since_migration_status_display="OK",
        drawdown_display="0.5",
        drawdown_basis_display="OK",
        migration_status="PRESENT",
        migration_timestamp_display="2026-05-22T00:00:00Z",
        migration_age_seconds_display="86400",
        migration_source_display="fake_migration",
        render_status=render_status,
        render_note="LIVE_OK",
        body_text=body_text,
    )


def _make_stage27_candidate(
    *,
    candidate_id: str = "candidate_001",
    candidate_status: str = CANDIDATE_STATUS_RENDERED_DRY_RUN,
    candidate_reason: str = CANDIDATE_REASON_RENDERED_OK,
    ingest_output: Optional[ProviderIngestOutputRecord] = None,
    rendered_ping: Optional[PrivatePingPayloadRecord] = None,
    payload_artifact_path: Optional[Path] = None,
) -> Stage27_6LiveCandidateRecord:
    if ingest_output is None:
        ingest_output = _make_ingest()
    if rendered_ping is None:
        rendered_ping = _make_rendered_ping()
    return Stage27_6LiveCandidateRecord(
        candidate_id=candidate_id,
        run_id="phx2_run01",
        session_id="phx2_session01",
        candidate_schema_version=(
            STAGE27_6_CANDIDATE_SCHEMA_VERSION
        ),
        candidate_status=candidate_status,
        candidate_reason=candidate_reason,
        ingest_output=ingest_output,
        measurement_context=None,
        rendered_ping=rendered_ping,
        provenance_artifact=None,
        payload_artifact_path=payload_artifact_path,
        provenance_artifact_path=None,
        dedupe_key=None,
        write_attempted=False,
    )


# ---------------------------------------------------------------------------
# Mapper: pair-status projection
# ---------------------------------------------------------------------------


def test_mapper_ok_sol_candidate_to_ok_pair_status():
    record = _make_stage27_candidate(
        candidate_status=CANDIDATE_STATUS_RENDERED_DRY_RUN,
        candidate_reason=CANDIDATE_REASON_RENDERED_OK,
        ingest_output=_make_ingest(pair_quote_asset="SOL"),
        rendered_ping=_make_rendered_ping(
            pair_quote_asset="SOL", price_status="PRESENT",
        ),
    )
    event = map_stage27_candidate_to_stage28_6_event(record)
    assert isinstance(event, Stage28_6CandidateEvent)
    assert event.pair_status == CANDIDATE_PAIR_STATUS_OK
    assert event.price_status == CANDIDATE_PRICE_STATUS_OK
    assert event.malformed is False
    assert event.dispatch_allowed is True
    assert event.ping_type == STAGE28_9_PING_TYPE_LABEL
    assert (
        event.webhook_identity
        == WEBHOOK_IDENTITY_PRIVATE_OPERATOR
    )


def test_mapper_unknown_pair_status():
    record = _make_stage27_candidate(
        candidate_status=(
            CANDIDATE_STATUS_SUPPRESSED_UNKNOWN_PAIR
        ),
        candidate_reason=(
            CANDIDATE_REASON_UNKNOWN_PAIR_LIVE_SUPPRESSED
        ),
        ingest_output=_make_ingest(
            pair_quote_asset="UNKNOWN",
            composition_status=COMPOSITION_STATUS_CLASSIFIED_UNKNOWN,
        ),
        rendered_ping=_make_rendered_ping(
            pair_quote_asset="UNKNOWN",
        ),
    )
    event = map_stage27_candidate_to_stage28_6_event(record)
    assert event.pair_status == CANDIDATE_PAIR_STATUS_UNKNOWN


def test_mapper_disagree_pair_status():
    record = _make_stage27_candidate(
        candidate_status=(
            CANDIDATE_STATUS_SUPPRESSED_DISAGREE_PAIR
        ),
        candidate_reason=(
            CANDIDATE_REASON_DISAGREE_PAIR_LIVE_SUPPRESSED
        ),
        ingest_output=_make_ingest(
            composition_status=(
                COMPOSITION_STATUS_CLASSIFIED_DISAGREE
            ),
        ),
    )
    event = map_stage27_candidate_to_stage28_6_event(record)
    assert event.pair_status == CANDIDATE_PAIR_STATUS_DISAGREE


def test_mapper_usdc_observe_only_pair_status():
    record = _make_stage27_candidate(
        candidate_status=CANDIDATE_STATUS_RENDERED_DRY_RUN,
        candidate_reason=CANDIDATE_REASON_USDC_OBSERVE_ONLY,
        ingest_output=_make_ingest(pair_quote_asset="USDC"),
        rendered_ping=_make_rendered_ping(
            pair_quote_asset="USDC",
            render_status="RENDERED_OBSERVE_ONLY",
        ),
    )
    event = map_stage27_candidate_to_stage28_6_event(record)
    assert (
        event.pair_status
        == CANDIDATE_PAIR_STATUS_USDC_OBSERVE_ONLY
    )


# ---------------------------------------------------------------------------
# Mapper: price-status projection
# ---------------------------------------------------------------------------


def test_mapper_stale_price_to_stage28_6_stale():
    record = _make_stage27_candidate(
        rendered_ping=_make_rendered_ping(price_status="STALE"),
    )
    event = map_stage27_candidate_to_stage28_6_event(record)
    assert event.price_status == CANDIDATE_PRICE_STATUS_STALE


def test_mapper_unavailable_price_to_stage28_6_missing():
    record = _make_stage27_candidate(
        rendered_ping=_make_rendered_ping(
            price_status="UNAVAILABLE"
        ),
    )
    event = map_stage27_candidate_to_stage28_6_event(record)
    assert event.price_status == CANDIDATE_PRICE_STATUS_MISSING


def test_mapper_source_error_price_to_stage28_6_missing():
    record = _make_stage27_candidate(
        rendered_ping=_make_rendered_ping(
            price_status="SOURCE_ERROR"
        ),
    )
    event = map_stage27_candidate_to_stage28_6_event(record)
    assert event.price_status == CANDIDATE_PRICE_STATUS_MISSING


# ---------------------------------------------------------------------------
# Mapper: malformed projection
# ---------------------------------------------------------------------------


def test_mapper_error_candidate_flagged_malformed():
    record = _make_stage27_candidate(
        candidate_status=CANDIDATE_STATUS_ERROR,
        candidate_reason=CANDIDATE_REASON_UNEXPECTED_ERROR,
        ingest_output=_make_ingest(
            composition_status=COMPOSITION_STATUS_ERROR,
        ),
    )
    event = map_stage27_candidate_to_stage28_6_event(record)
    assert event.malformed is True
    assert event.dispatch_allowed is False


def test_mapper_artifact_write_failed_flagged_malformed():
    record = _make_stage27_candidate(
        candidate_status=CANDIDATE_STATUS_ARTIFACT_WRITE_FAILED,
        candidate_reason=CANDIDATE_REASON_ARTIFACT_WRITE_FAILED,
    )
    event = map_stage27_candidate_to_stage28_6_event(record)
    assert event.malformed is True


def test_mapper_skipped_unsupported_event_flagged_malformed():
    record = _make_stage27_candidate(
        candidate_status=(
            CANDIDATE_STATUS_SKIPPED_UNSUPPORTED_EVENT
        ),
        candidate_reason=CANDIDATE_REASON_OK,
    )
    event = map_stage27_candidate_to_stage28_6_event(record)
    assert event.malformed is True


def test_mapper_skipped_duplicate_flagged_malformed():
    record = _make_stage27_candidate(
        candidate_status=CANDIDATE_STATUS_SKIPPED_DUPLICATE,
        candidate_reason=CANDIDATE_REASON_DUPLICATE_RUN_LOCAL,
    )
    event = map_stage27_candidate_to_stage28_6_event(record)
    assert event.malformed is True


# ---------------------------------------------------------------------------
# Mapper: payload content includes Stage 29-pending marker
# ---------------------------------------------------------------------------


def test_mapper_payload_includes_stage_29_pending_marker():
    record = _make_stage27_candidate()
    event = map_stage27_candidate_to_stage28_6_event(record)
    assert "content" in event.rendered_payload
    content = event.rendered_payload["content"]
    assert isinstance(content, str)
    assert (
        FILTER_ENFORCEMENT_STATUS_NOT_ACTIVE_STAGE_29_PENDING
        in content
    )
    assert "Filter enforcement:" in content
    assert POLICY_MODE_PRIVATE_OPERATOR_ONLY in content


def test_mapper_payload_excludes_trading_or_routing_language():
    record = _make_stage27_candidate()
    event = map_stage27_candidate_to_stage28_6_event(record)
    content = event.rendered_payload["content"].lower()
    forbidden_lowercase_substrings = (
        # Trading verdict / decision language.
        "buy ",
        "sell ",
        "approved",
        "execute",
        "trade",
        "position",
        "auto-trade",
        "auto_trade",
        # Routing audience broadening.
        "subscriber",
        "public_router",
        "paid tier",
        "telegram",
        "x_social",
        # Wallet / signer.
        "wallet_address",
        "signer_address",
        "private_key",
    )
    for needle in forbidden_lowercase_substrings:
        assert needle not in content, (
            f"forbidden substring {needle!r} found in payload "
            f"content"
        )


def test_mapper_payload_top_level_keys_are_safe():
    record = _make_stage27_candidate()
    event = map_stage27_candidate_to_stage28_6_event(record)
    keys = set(event.rendered_payload.keys())
    assert keys == {"content"}


def test_mapper_truncates_overlong_body():
    long_body = "x" * 10_000
    record = _make_stage27_candidate(
        rendered_ping=_make_rendered_ping(body_text=long_body),
    )
    event = map_stage27_candidate_to_stage28_6_event(record)
    content = event.rendered_payload["content"]
    # Stage 28.9 cap is 1900 chars.
    assert len(content) <= 1900
    assert "[truncated]" in content


def test_mapper_uses_payload_artifact_basename_when_present(
    tmp_path: Path,
):
    artifact = tmp_path / "ping_xyz.payload.json"
    record = _make_stage27_candidate(
        payload_artifact_path=artifact,
    )
    event = map_stage27_candidate_to_stage28_6_event(record)
    assert (
        event.pre_send_artifact_reference == "ping_xyz.payload.json"
    )


def test_mapper_uses_synthetic_basename_when_artifact_absent():
    record = _make_stage27_candidate()
    event = map_stage27_candidate_to_stage28_6_event(record)
    assert event.pre_send_artifact_reference.startswith(
        "stage28_9_pending_"
    )


def test_mapper_rejects_non_stage27_record():
    from PHX2.stage28.live_provider_session_models import (
        Stage28_9UnsafeMappingError,
    )

    with pytest.raises(Stage28_9UnsafeMappingError):
        map_stage27_candidate_to_stage28_6_event(
            {"not": "a record"}  # type: ignore[arg-type]
        )


# ---------------------------------------------------------------------------
# render_stage28_9_discord_content
# ---------------------------------------------------------------------------


def test_render_includes_stage_29_pending_marker():
    record = _make_stage27_candidate()
    text = render_stage28_9_discord_content(record)
    assert "Filter enforcement:" in text
    assert (
        FILTER_ENFORCEMENT_STATUS_NOT_ACTIVE_STAGE_29_PENDING
        in text
    )


def test_render_includes_candidate_status_and_reason():
    record = _make_stage27_candidate(
        candidate_status=(
            CANDIDATE_STATUS_SUPPRESSED_UNKNOWN_PAIR
        ),
        candidate_reason=(
            CANDIDATE_REASON_UNKNOWN_PAIR_LIVE_SUPPRESSED
        ),
    )
    text = render_stage28_9_discord_content(record)
    assert (
        CANDIDATE_STATUS_SUPPRESSED_UNKNOWN_PAIR in text
    )
    assert (
        CANDIDATE_REASON_UNKNOWN_PAIR_LIVE_SUPPRESSED in text
    )


def test_render_handles_missing_rendered_ping():
    # Build a record with rendered_ping=None directly (the mapper
    # treats this as malformed but the renderer should still be
    # safe).
    record = Stage27_6LiveCandidateRecord(
        candidate_id="x",
        run_id=None,
        session_id=None,
        candidate_schema_version=(
            STAGE27_6_CANDIDATE_SCHEMA_VERSION
        ),
        candidate_status=CANDIDATE_STATUS_ERROR,
        candidate_reason=CANDIDATE_REASON_UNEXPECTED_ERROR,
        ingest_output=_make_ingest(),
        measurement_context=None,
        rendered_ping=None,
        provenance_artifact=None,
        payload_artifact_path=None,
        provenance_artifact_path=None,
        dedupe_key=None,
        write_attempted=False,
    )
    text = render_stage28_9_discord_content(record)
    assert "Stage 28.9" in text
    assert "no Stage 27.5 rendered ping" in text


# ---------------------------------------------------------------------------
# output_dir_safe_label
# ---------------------------------------------------------------------------


def test_derive_output_dir_safe_label_basic(tmp_path: Path):
    label = derive_output_dir_safe_label(tmp_path)
    assert isinstance(label, str)
    assert label != ""
    assert " " not in label


def test_derive_output_dir_safe_label_non_path():
    label = derive_output_dir_safe_label("not_a_path")  # type: ignore[arg-type]
    assert label == "<<STAGE28_9_REDACTED>>"


# ---------------------------------------------------------------------------
# Readiness gates
# ---------------------------------------------------------------------------


def _make_config(
    output_dir_safe_label: str = "scratch_run01",
    max_events: int = 8,
    max_dispatches: int = 8,
) -> Stage28_9LiveProviderSessionConfig:
    return build_live_provider_session_config(
        run_id="phx2_stage28_9_run01",
        session_id="phx2_stage28_9_session01",
        provider_id="helius_grpc",
        provider_kind="solana_websocket",
        max_events=max_events,
        max_dispatches=max_dispatches,
        max_ticks=128,
        max_total_retries=2,
        heartbeat_every_n_events=2,
        output_dir_safe_label=output_dir_safe_label,
        session_mode=SESSION_MODE_LIVE_PRIVATE,
    )


def test_readiness_refuses_when_live_env_not_ready(tmp_path: Path):
    config = _make_config()
    verdict = evaluate_stage28_9_readiness(
        config=config,
        private_webhook_url=_FAKE_WEBHOOK_URL,
        live_env_ready=False,
        live_operator_request=True,
        output_dir=tmp_path,
    )
    assert verdict.ready is False
    assert verdict.refusal_reason == REFUSAL_REASON_NOT_LIVE


def test_readiness_refuses_when_not_operator_requested(
    tmp_path: Path,
):
    config = _make_config()
    verdict = evaluate_stage28_9_readiness(
        config=config,
        private_webhook_url=_FAKE_WEBHOOK_URL,
        live_env_ready=True,
        live_operator_request=False,
        output_dir=tmp_path,
    )
    assert verdict.ready is False
    assert (
        verdict.refusal_reason
        == REFUSAL_REASON_NOT_OPERATOR_REQUESTED
    )


def test_readiness_refuses_when_webhook_missing(tmp_path: Path):
    config = _make_config()
    verdict = evaluate_stage28_9_readiness(
        config=config,
        private_webhook_url="",
        live_env_ready=True,
        live_operator_request=True,
        output_dir=tmp_path,
    )
    assert verdict.ready is False
    assert (
        verdict.refusal_reason == REFUSAL_REASON_WEBHOOK_MISSING
    )


def test_readiness_refuses_when_output_dir_missing(
    tmp_path: Path,
):
    config = _make_config()
    bogus_dir = tmp_path / "does_not_exist"
    verdict = evaluate_stage28_9_readiness(
        config=config,
        private_webhook_url=_FAKE_WEBHOOK_URL,
        live_env_ready=True,
        live_operator_request=True,
        output_dir=bogus_dir,
    )
    assert verdict.ready is False
    assert (
        verdict.refusal_reason
        == REFUSAL_REASON_OUTPUT_DIR_UNSAFE
    )


def test_readiness_refuses_when_output_dir_not_path():
    config = _make_config()
    verdict = evaluate_stage28_9_readiness(
        config=config,
        private_webhook_url=_FAKE_WEBHOOK_URL,
        live_env_ready=True,
        live_operator_request=True,
        output_dir="/not/a/path/object",
    )
    assert verdict.ready is False
    assert (
        verdict.refusal_reason
        == REFUSAL_REASON_OUTPUT_DIR_UNSAFE
    )


def test_readiness_passes_when_all_gates_pass(
    out_of_repo_tmp_path: Path,
):
    config = _make_config()
    verdict = evaluate_stage28_9_readiness(
        config=config,
        private_webhook_url=_FAKE_WEBHOOK_URL,
        live_env_ready=True,
        live_operator_request=True,
        output_dir=out_of_repo_tmp_path,
    )
    assert verdict.ready is True


# ---------------------------------------------------------------------------
# Fake provider event source + fake assembler
# ---------------------------------------------------------------------------


class _FakeNormalizedEvent:
    """Stage 27.3 ``NormalizedEventLike`` Protocol-compatible
    minimal fake. Tests use this rather than constructing a real
    Stage 21.2 record (which has its own strict validation).
    """

    def __init__(
        self,
        *,
        event_id: str,
        provider_event_id: str,
        provider_name: str,
        mint: str,
        event_type: str,
        observed_at_utc: str,
        raw_event_hash: str,
    ) -> None:
        self.event_id = event_id
        self.provider_event_id = provider_event_id
        self.provider_name = provider_name
        self.mint = mint
        self.event_type = event_type
        self.observed_at_utc = observed_at_utc
        self.raw_event_hash = raw_event_hash


class _StubCandidateAssembler:
    """Stub Stage 28.9 candidate assembler that returns a
    pre-canned tuple of Stage 27.6 candidate records (one per
    incoming normalized event, in order). The assembler is the
    test seam for the orchestrator; the real Stage 27 chain is
    NOT exercised here.
    """

    def __init__(
        self, *, records: Iterable[Stage27_6LiveCandidateRecord],
    ) -> None:
        self._records: tuple[
            Stage27_6LiveCandidateRecord, ...
        ] = tuple(records)
        self._call_count: int = 0

    @property
    def call_count(self) -> int:
        return self._call_count

    def assemble(
        self,
        normalized_event,
        *,
        candidate_id: str,
    ) -> Stage27_6LiveCandidateRecord:
        index = self._call_count
        self._call_count += 1
        if index < len(self._records):
            base = self._records[index]
        else:
            base = self._records[-1]
        # Return a new record with the orchestrator-supplied
        # candidate_id so the dedupe key downstream is
        # deterministic per assembler call.
        return base._replace(candidate_id=candidate_id)


def _make_n_fake_events(n: int) -> tuple[_FakeNormalizedEvent, ...]:
    return tuple(
        _FakeNormalizedEvent(
            event_id=f"evt_{i:03d}",
            provider_event_id=f"prov_evt_{i:03d}",
            provider_name="fake_provider",
            mint=f"SoMintFakeAbc{i:03d}",
            event_type="swap",
            observed_at_utc="2026-05-23T12:00:00Z",
            raw_event_hash=f"hash_{i:03d}",
        )
        for i in range(n)
    )


# ---------------------------------------------------------------------------
# Orchestrator: refusal paths
# ---------------------------------------------------------------------------


def test_orchestrator_refuses_when_live_env_not_ready(
    tmp_path: Path,
):
    config = _make_config()
    source = Stage28_9FakeProviderEventSource(events=())
    assembler = _StubCandidateAssembler(
        records=(_make_stage27_candidate(),),
    )
    transport = Stage28_6FakeTransport()
    result = run_stage28_9_live_provider_session(
        config=config,
        provider_event_source=source,
        candidate_assembler=assembler,
        transport=transport,
        output_dir=tmp_path,
        private_webhook_url=_FAKE_WEBHOOK_URL,
        live_env_ready=False,
        live_operator_request=True,
    )
    assert result.session_outcome == SESSION_OUTCOME_REFUSED
    assert result.refusal_reason == REFUSAL_REASON_NOT_LIVE
    # The provider must NOT have been called.
    assert source.iter_count == 0
    assert assembler.call_count == 0
    assert transport.call_count == 0


def test_orchestrator_refuses_when_webhook_missing(
    tmp_path: Path,
):
    config = _make_config()
    source = Stage28_9FakeProviderEventSource(events=())
    assembler = _StubCandidateAssembler(
        records=(_make_stage27_candidate(),),
    )
    transport = Stage28_6FakeTransport()
    result = run_stage28_9_live_provider_session(
        config=config,
        provider_event_source=source,
        candidate_assembler=assembler,
        transport=transport,
        output_dir=tmp_path,
        private_webhook_url="",
        live_env_ready=True,
        live_operator_request=True,
    )
    assert result.session_outcome == SESSION_OUTCOME_REFUSED
    assert (
        result.refusal_reason == REFUSAL_REASON_WEBHOOK_MISSING
    )
    assert source.iter_count == 0
    assert assembler.call_count == 0
    assert transport.call_count == 0


def test_orchestrator_refuses_when_not_operator_requested(
    tmp_path: Path,
):
    config = _make_config()
    source = Stage28_9FakeProviderEventSource(events=())
    assembler = _StubCandidateAssembler(
        records=(_make_stage27_candidate(),),
    )
    transport = Stage28_6FakeTransport()
    result = run_stage28_9_live_provider_session(
        config=config,
        provider_event_source=source,
        candidate_assembler=assembler,
        transport=transport,
        output_dir=tmp_path,
        private_webhook_url=_FAKE_WEBHOOK_URL,
        live_env_ready=True,
        live_operator_request=False,
    )
    assert result.session_outcome == SESSION_OUTCOME_REFUSED
    assert (
        result.refusal_reason
        == REFUSAL_REASON_NOT_OPERATOR_REQUESTED
    )
    assert source.iter_count == 0


# ---------------------------------------------------------------------------
# Orchestrator: happy path
# ---------------------------------------------------------------------------


def test_orchestrator_runs_runner_for_single_dispatchable_candidate(
    out_of_repo_tmp_path: Path,
):
    config = _make_config(max_events=1, max_dispatches=1)
    events = _make_n_fake_events(1)
    source = Stage28_9FakeProviderEventSource(events=events)
    assembler = _StubCandidateAssembler(
        records=(_make_stage27_candidate(),),
    )
    transport = Stage28_6FakeTransport(
        scripted_outcomes=(TRANSPORT_STATUS_SENT_OK,),
    )
    result = run_stage28_9_live_provider_session(
        config=config,
        provider_event_source=source,
        candidate_assembler=assembler,
        transport=transport,
        output_dir=out_of_repo_tmp_path,
        private_webhook_url=_FAKE_WEBHOOK_URL,
        live_env_ready=True,
        live_operator_request=True,
    )
    assert result.session_outcome == SESSION_OUTCOME_OK
    assert result.events_seen == 1
    assert result.candidates_assembled == 1
    assert result.dispatch_success == 1
    assert result.dispatch_failure == 0
    assert result.candidates_dispatched == 1
    assert transport.call_count == 1
    # The runner-side artifacts must have been written.
    for basename in (
        STAGE28_9_DISPATCH_LEDGER_BASENAME,
        STAGE28_9_HEALTH_SNAPSHOT_BASENAME,
        STAGE28_9_FINAL_SUMMARY_BASENAME,
    ):
        assert (out_of_repo_tmp_path / basename).exists()


def test_orchestrator_stops_at_max_events(
    out_of_repo_tmp_path: Path,
):
    config = _make_config(max_events=2, max_dispatches=10)
    events = _make_n_fake_events(5)
    source = Stage28_9FakeProviderEventSource(events=events)
    assembler = _StubCandidateAssembler(
        records=(_make_stage27_candidate(),),
    )
    transport = Stage28_6FakeTransport(
        scripted_outcomes=(TRANSPORT_STATUS_SENT_OK,),
    )
    result = run_stage28_9_live_provider_session(
        config=config,
        provider_event_source=source,
        candidate_assembler=assembler,
        transport=transport,
        output_dir=out_of_repo_tmp_path,
        private_webhook_url=_FAKE_WEBHOOK_URL,
        live_env_ready=True,
        live_operator_request=True,
    )
    assert result.events_seen <= 2


def test_orchestrator_surfaces_dedupe_suppression(
    out_of_repo_tmp_path: Path,
):
    # Two events but the same Stage 27.6 record will be produced
    # for both, yielding the same Stage 28.6 candidate event
    # (same token_mint / event_kind / ping_type /
    # normalized_event_id) which the Stage 28.2 ledger will
    # suppress as a terminal duplicate on the second arrival.
    config = _make_config(max_events=4, max_dispatches=4)
    events = _make_n_fake_events(2)
    source = Stage28_9FakeProviderEventSource(events=events)
    # Both stub records have identical normalized_event_id so the
    # Stage 28.6 dedupe key collides; using the SAME pre-canned
    # base candidate causes the second to be a duplicate.
    base_record = _make_stage27_candidate()
    assembler = _StubCandidateAssembler(
        records=(base_record, base_record),
    )
    transport = Stage28_6FakeTransport(
        scripted_outcomes=(TRANSPORT_STATUS_SENT_OK,),
    )
    result = run_stage28_9_live_provider_session(
        config=config,
        provider_event_source=source,
        candidate_assembler=assembler,
        transport=transport,
        output_dir=out_of_repo_tmp_path,
        private_webhook_url=_FAKE_WEBHOOK_URL,
        live_env_ready=True,
        live_operator_request=True,
    )
    assert result.events_seen == 2
    # First candidate dispatched; second suppressed as terminal
    # duplicate by the Stage 28.2 ledger.
    assert result.dispatch_success == 1
    assert result.duplicate_suppressed == 1


def test_orchestrator_suppresses_unknown_pair_candidate(
    out_of_repo_tmp_path: Path,
):
    config = _make_config(max_events=1, max_dispatches=4)
    events = _make_n_fake_events(1)
    source = Stage28_9FakeProviderEventSource(events=events)
    unknown_record = _make_stage27_candidate(
        candidate_status=(
            CANDIDATE_STATUS_SUPPRESSED_UNKNOWN_PAIR
        ),
        candidate_reason=(
            CANDIDATE_REASON_UNKNOWN_PAIR_LIVE_SUPPRESSED
        ),
    )
    assembler = _StubCandidateAssembler(records=(unknown_record,))
    transport = Stage28_6FakeTransport()
    result = run_stage28_9_live_provider_session(
        config=config,
        provider_event_source=source,
        candidate_assembler=assembler,
        transport=transport,
        output_dir=out_of_repo_tmp_path,
        private_webhook_url=_FAKE_WEBHOOK_URL,
        live_env_ready=True,
        live_operator_request=True,
    )
    assert result.unknown_pair_suppressed == 1
    assert result.dispatch_success == 0
    assert transport.call_count == 0


def test_orchestrator_suppresses_stale_price_candidate(
    out_of_repo_tmp_path: Path,
):
    config = _make_config(max_events=1, max_dispatches=4)
    events = _make_n_fake_events(1)
    source = Stage28_9FakeProviderEventSource(events=events)
    stale_record = _make_stage27_candidate(
        rendered_ping=_make_rendered_ping(price_status="STALE"),
    )
    assembler = _StubCandidateAssembler(records=(stale_record,))
    transport = Stage28_6FakeTransport()
    result = run_stage28_9_live_provider_session(
        config=config,
        provider_event_source=source,
        candidate_assembler=assembler,
        transport=transport,
        output_dir=out_of_repo_tmp_path,
        private_webhook_url=_FAKE_WEBHOOK_URL,
        live_env_ready=True,
        live_operator_request=True,
    )
    assert result.stale_price_suppressed == 1
    assert result.dispatch_success == 0
    assert transport.call_count == 0


def test_orchestrator_suppresses_missing_price_candidate(
    out_of_repo_tmp_path: Path,
):
    config = _make_config(max_events=1, max_dispatches=4)
    events = _make_n_fake_events(1)
    source = Stage28_9FakeProviderEventSource(events=events)
    missing_record = _make_stage27_candidate(
        rendered_ping=_make_rendered_ping(
            price_status="UNAVAILABLE"
        ),
    )
    assembler = _StubCandidateAssembler(
        records=(missing_record,),
    )
    transport = Stage28_6FakeTransport()
    result = run_stage28_9_live_provider_session(
        config=config,
        provider_event_source=source,
        candidate_assembler=assembler,
        transport=transport,
        output_dir=out_of_repo_tmp_path,
        private_webhook_url=_FAKE_WEBHOOK_URL,
        live_env_ready=True,
        live_operator_request=True,
    )
    assert result.missing_price_suppressed == 1
    assert transport.call_count == 0


def test_orchestrator_suppresses_malformed_candidate(
    out_of_repo_tmp_path: Path,
):
    config = _make_config(max_events=1, max_dispatches=4)
    events = _make_n_fake_events(1)
    source = Stage28_9FakeProviderEventSource(events=events)
    malformed_record = _make_stage27_candidate(
        candidate_status=CANDIDATE_STATUS_ERROR,
        candidate_reason=CANDIDATE_REASON_UNEXPECTED_ERROR,
    )
    assembler = _StubCandidateAssembler(
        records=(malformed_record,),
    )
    transport = Stage28_6FakeTransport()
    result = run_stage28_9_live_provider_session(
        config=config,
        provider_event_source=source,
        candidate_assembler=assembler,
        transport=transport,
        output_dir=out_of_repo_tmp_path,
        private_webhook_url=_FAKE_WEBHOOK_URL,
        live_env_ready=True,
        live_operator_request=True,
    )
    assert result.malformed_suppressed == 1
    assert transport.call_count == 0


def test_orchestrator_result_contains_no_webhook_url(
    out_of_repo_tmp_path: Path,
):
    config = _make_config(max_events=1, max_dispatches=1)
    events = _make_n_fake_events(1)
    source = Stage28_9FakeProviderEventSource(events=events)
    assembler = _StubCandidateAssembler(
        records=(_make_stage27_candidate(),),
    )
    transport = Stage28_6FakeTransport(
        scripted_outcomes=(TRANSPORT_STATUS_SENT_OK,),
    )
    result = run_stage28_9_live_provider_session(
        config=config,
        provider_event_source=source,
        candidate_assembler=assembler,
        transport=transport,
        output_dir=out_of_repo_tmp_path,
        private_webhook_url=_FAKE_WEBHOOK_URL,
        live_env_ready=True,
        live_operator_request=True,
    )
    # No field on the result may carry the URL substring.
    for value in result:
        if isinstance(value, str):
            assert "example.invalid" not in value
            assert "h" + "ttps" + "://" not in value


def test_orchestrator_result_filter_enforcement_marker_locked(
    out_of_repo_tmp_path: Path,
):
    config = _make_config(max_events=1, max_dispatches=1)
    events = _make_n_fake_events(1)
    source = Stage28_9FakeProviderEventSource(events=events)
    assembler = _StubCandidateAssembler(
        records=(_make_stage27_candidate(),),
    )
    transport = Stage28_6FakeTransport(
        scripted_outcomes=(TRANSPORT_STATUS_SENT_OK,),
    )
    result = run_stage28_9_live_provider_session(
        config=config,
        provider_event_source=source,
        candidate_assembler=assembler,
        transport=transport,
        output_dir=out_of_repo_tmp_path,
        private_webhook_url=_FAKE_WEBHOOK_URL,
        live_env_ready=True,
        live_operator_request=True,
    )
    assert (
        result.filter_enforcement_status
        == FILTER_ENFORCEMENT_STATUS_NOT_ACTIVE_STAGE_29_PENDING
    )


# ---------------------------------------------------------------------------
# Polish: output_dir repo-root containment + stop_signal passthrough
# ---------------------------------------------------------------------------


_REPO_ROOT_FOR_TESTS: Path = (
    Path(__file__).resolve().parent.parent.parent.parent
)


def test_readiness_refuses_when_output_dir_inside_repo(
    tmp_path: Path,
):
    """The Stage 28.9 readiness gate refuses an ``output_dir``
    that resolves inside the PHX2 repo root. ``tmp_path`` here
    is the pytest built-in fixture, which (per the required
    ``--basetemp=PHX2/.pytest_tmp`` invocation) is INSIDE the
    repo; the gate must refuse it with the locked
    ``OUTPUT_DIR_UNSAFE`` refusal reason.
    """
    # Sanity: confirm tmp_path is actually inside the repo so
    # this test is meaningful.
    try:
        tmp_path.resolve().relative_to(_REPO_ROOT_FOR_TESTS)
    except ValueError:
        pytest.skip(
            "tmp_path is outside the repo root for this test "
            "invocation; the repo-root refusal path can only "
            "be exercised when --basetemp lives in the repo"
        )

    config = _make_config()
    verdict = evaluate_stage28_9_readiness(
        config=config,
        private_webhook_url=_FAKE_WEBHOOK_URL,
        live_env_ready=True,
        live_operator_request=True,
        output_dir=tmp_path,
    )
    assert verdict.ready is False
    assert (
        verdict.refusal_reason
        == REFUSAL_REASON_OUTPUT_DIR_UNSAFE
    )


def test_readiness_passes_when_output_dir_outside_repo(
    out_of_repo_tmp_path: Path,
):
    """The Stage 28.9 readiness gate accepts an ``output_dir``
    that resolves outside the PHX2 repo root (the operator's
    scratch space).
    """
    # Sanity: confirm out_of_repo_tmp_path is actually outside.
    inside = False
    try:
        out_of_repo_tmp_path.resolve().relative_to(
            _REPO_ROOT_FOR_TESTS
        )
        inside = True
    except ValueError:
        inside = False
    assert not inside, (
        "out_of_repo_tmp_path fixture must allocate scratch "
        "OUTSIDE the PHX2 repo root"
    )

    config = _make_config()
    verdict = evaluate_stage28_9_readiness(
        config=config,
        private_webhook_url=_FAKE_WEBHOOK_URL,
        live_env_ready=True,
        live_operator_request=True,
        output_dir=out_of_repo_tmp_path,
    )
    assert verdict.ready is True


def test_orchestrator_refuses_inside_repo_output_dir_before_provider_call(
    tmp_path: Path,
):
    """When the operator passes an in-repo ``output_dir`` the
    Stage 28.9 orchestrator refuses BEFORE invoking the
    provider event source, the candidate assembler, or the
    transport. No write happens to the in-repo path.
    """
    try:
        tmp_path.resolve().relative_to(_REPO_ROOT_FOR_TESTS)
    except ValueError:
        pytest.skip(
            "tmp_path is outside the repo root for this test "
            "invocation; the repo-root refusal path can only "
            "be exercised when --basetemp lives in the repo"
        )

    config = _make_config(max_events=4, max_dispatches=4)
    events = _make_n_fake_events(2)
    source = Stage28_9FakeProviderEventSource(events=events)
    assembler = _StubCandidateAssembler(
        records=(_make_stage27_candidate(),),
    )
    transport = Stage28_6FakeTransport()

    result = run_stage28_9_live_provider_session(
        config=config,
        provider_event_source=source,
        candidate_assembler=assembler,
        transport=transport,
        output_dir=tmp_path,
        private_webhook_url=_FAKE_WEBHOOK_URL,
        live_env_ready=True,
        live_operator_request=True,
    )
    assert result.session_outcome == SESSION_OUTCOME_REFUSED
    assert (
        result.refusal_reason
        == REFUSAL_REASON_OUTPUT_DIR_UNSAFE
    )
    # The provider / assembler / transport must NOT have been
    # touched by the orchestrator after the readiness refusal.
    assert source.iter_count == 0
    assert assembler.call_count == 0
    assert transport.call_count == 0


def test_orchestrator_refused_in_repo_result_carries_no_raw_path(
    tmp_path: Path,
):
    """The refusal result for an in-repo ``output_dir`` must
    never echo the raw caller-supplied path on any field.
    Only closed-set tokens + safe identifiers + the safe
    output-dir label may reach the result.
    """
    try:
        tmp_path.resolve().relative_to(_REPO_ROOT_FOR_TESTS)
    except ValueError:
        pytest.skip(
            "tmp_path is outside the repo root for this test "
            "invocation; the repo-root refusal path can only "
            "be exercised when --basetemp lives in the repo"
        )

    config = _make_config()
    source = Stage28_9FakeProviderEventSource(events=())
    assembler = _StubCandidateAssembler(
        records=(_make_stage27_candidate(),),
    )
    transport = Stage28_6FakeTransport()

    result = run_stage28_9_live_provider_session(
        config=config,
        provider_event_source=source,
        candidate_assembler=assembler,
        transport=transport,
        output_dir=tmp_path,
        private_webhook_url=_FAKE_WEBHOOK_URL,
        live_env_ready=True,
        live_operator_request=True,
    )
    raw_path_str = str(tmp_path)
    raw_path_resolved = str(tmp_path.resolve())
    for value in result:
        if isinstance(value, str):
            assert raw_path_str not in value, (
                f"result field carries the raw caller path: "
                f"{value!r}"
            )
            assert raw_path_resolved not in value, (
                f"result field carries the resolved caller "
                f"path: {value!r}"
            )


def test_orchestrator_passes_stop_signal_through_to_runner(
    out_of_repo_tmp_path: Path,
):
    """Stage 28.9 forwards the optional caller-injected
    ``Stage28_6StopSignal`` to the Stage 28.6 bounded private
    session runner. The runner polls the signal between
    candidates; a pre-requested stop causes the runner to stop
    after the first candidate (Stage 28.6 polls AFTER per-
    candidate processing).
    """
    from PHX2.stage28.session_runner_models import (
        Stage28_6StopSignal,
    )
    from PHX2.stage28.health_status_models import (
        STOP_REASON_OPERATOR_STOP,
    )

    stop_signal = Stage28_6StopSignal()
    stop_signal.request_stop()  # pre-request before run

    config = _make_config(max_events=4, max_dispatches=4)
    events = _make_n_fake_events(3)
    source = Stage28_9FakeProviderEventSource(events=events)
    assembler = _StubCandidateAssembler(
        records=(_make_stage27_candidate(),),
    )
    transport = Stage28_6FakeTransport(
        scripted_outcomes=(TRANSPORT_STATUS_SENT_OK,),
    )
    result = run_stage28_9_live_provider_session(
        config=config,
        provider_event_source=source,
        candidate_assembler=assembler,
        transport=transport,
        output_dir=out_of_repo_tmp_path,
        private_webhook_url=_FAKE_WEBHOOK_URL,
        live_env_ready=True,
        live_operator_request=True,
        stop_signal=stop_signal,
    )
    # The Stage 28.6 runner polls the stop signal AFTER per-
    # candidate processing; Python's for-loop pulls the next
    # candidate from the generator before re-checking
    # ``stop.stopped``, so the orchestrator's
    # ``events_seen`` counter (the count of events pulled
    # from the generator) reaches at most 2 here: the first
    # is fully processed, the second is yielded but the
    # runner breaks at the top of the loop before processing
    # it. The dispatch_success counter is the load-bearing
    # assertion: exactly ONE candidate was dispatched before
    # the operator stop was observed.
    assert result.events_seen <= 2
    assert result.dispatch_success == 1
    assert result.candidates_dispatched == 1
    assert result.stop_reason == STOP_REASON_OPERATOR_STOP
    # And NO additional dispatches happened beyond the first.
    assert transport.call_count == 1


def test_orchestrator_stop_signal_defaults_to_none(
    out_of_repo_tmp_path: Path,
):
    """When no ``stop_signal`` is passed, the orchestrator
    forwards ``None`` to the Stage 28.6 runner (the default).
    The bounded runner then stops on the normal max-events /
    max-dispatches bounds.
    """
    config = _make_config(max_events=1, max_dispatches=1)
    events = _make_n_fake_events(1)
    source = Stage28_9FakeProviderEventSource(events=events)
    assembler = _StubCandidateAssembler(
        records=(_make_stage27_candidate(),),
    )
    transport = Stage28_6FakeTransport(
        scripted_outcomes=(TRANSPORT_STATUS_SENT_OK,),
    )
    # No stop_signal keyword: relies on default None.
    result = run_stage28_9_live_provider_session(
        config=config,
        provider_event_source=source,
        candidate_assembler=assembler,
        transport=transport,
        output_dir=out_of_repo_tmp_path,
        private_webhook_url=_FAKE_WEBHOOK_URL,
        live_env_ready=True,
        live_operator_request=True,
    )
    assert result.session_outcome == SESSION_OUTCOME_OK
    assert result.dispatch_success == 1


# ---------------------------------------------------------------------------
# FakeProviderEventSource sanity
# ---------------------------------------------------------------------------


def test_fake_provider_source_yields_events():
    events = _make_n_fake_events(3)
    source = Stage28_9FakeProviderEventSource(events=events)
    drained = list(source.iter_events(max_events=3))
    assert len(drained) == 3
    assert source.iter_count == 1


def test_fake_provider_source_caps_at_max_events():
    events = _make_n_fake_events(5)
    source = Stage28_9FakeProviderEventSource(events=events)
    drained = list(source.iter_events(max_events=2))
    assert len(drained) == 2


def test_fake_provider_source_rejects_zero_max_events():
    source = Stage28_9FakeProviderEventSource(events=())
    with pytest.raises(Exception):
        list(source.iter_events(max_events=0))


def test_default_candidate_assembler_construction_requires_sources():
    with pytest.raises(Exception):
        Stage28_9DefaultCandidateAssembler(
            sources=None,  # type: ignore[arg-type]
        )


# ---------------------------------------------------------------------------
# Stage 29.3B regression: Stage 28.9 default assembler must forward the
# Stage 28.10 hint quartet (pool / quote / provider hints) into the
# Stage 27.3 adapter so the Stage 27.2 pair classifier can resolve the
# pair instead of UNRESOLVED -> SUPPRESSED_UNKNOWN_PAIR.
# ---------------------------------------------------------------------------


from datetime import datetime, timezone  # noqa: E402

from PHX2.stage27 import (  # noqa: E402
    price_ath_context_contracts as _stage27_4_src_errors,
)
from PHX2.stage27.live_candidate_assembler import (  # noqa: E402
    Stage27_6Sources as _Stage27_6SourcesForBridge,
)
from PHX2.stage27.pair_detection_constants import (  # noqa: E402
    KNOWN_USDC_MINT as _KNOWN_USDC_MINT,
    KNOWN_WRAPPED_SOL_MINT as _KNOWN_WRAPPED_SOL_MINT,
)
from PHX2.stage27.price_ath_context_models import (  # noqa: E402
    ATH_UNIT_SOL as _ATH_UNIT_SOL,
    ATH_UNIT_USDC as _ATH_UNIT_USDC,
    PRICE_UNIT_SOL as _PRICE_UNIT_SOL,
    PRICE_UNIT_USDC as _PRICE_UNIT_USDC,
)
from PHX2.stage27.price_ath_context_reader import (  # noqa: E402
    AthSourceSnapshot as _AthSourceSnapshot,
    FrozenStage27_4Clock as _FrozenStage27_4Clock,
    MigrationSourceSnapshot as _MigrationSourceSnapshot,
    PriceSourceSnapshot as _PriceSourceSnapshot,
)
from PHX2.stage28.chainstack_yellowstone_models import (  # noqa: E402
    build_normalized_event as _build_normalized_event,
)


_BRIDGE_FIXED_UTC = datetime(2026, 5, 22, 12, 0, 30, tzinfo=timezone.utc)
_BRIDGE_FIXED_UTC_ISO = "2026-05-22T12:00:30+00:00"
_BRIDGE_BASE_MINT = "TestBaseMintBridgeAAAA1111111111111111111B"
_BRIDGE_POOL_ACCOUNT = "TestPoolBridgeXXXXXX3333333333333333333333"
_BRIDGE_PUMPSWAP_PROGRAM_ID = (
    "pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA"
)


class _BridgeFakePriceSource:
    def __init__(self, snapshot: Optional[_PriceSourceSnapshot]) -> None:
        self._snapshot = snapshot

    def read_price_snapshot(
        self, token_mint, *, pair_quote_asset,
    ):
        if self._snapshot is None:
            raise _stage27_4_src_errors.Stage27PriceSourceError(
                "SOURCE_FAILED", source_label="bridge_fake_price",
            )
        return self._snapshot


class _BridgeFakeAthSource:
    def __init__(self, snapshot: Optional[_AthSourceSnapshot]) -> None:
        self._snapshot = snapshot

    def read_ath_snapshot(
        self, token_mint, *, pair_quote_asset,
    ):
        if self._snapshot is None:
            raise _stage27_4_src_errors.Stage27AthSourceError(
                "SOURCE_FAILED", source_label="bridge_fake_ath",
            )
        return self._snapshot


class _BridgeFakeMigrationSource:
    def __init__(
        self, snapshot: Optional[_MigrationSourceSnapshot],
    ) -> None:
        self._snapshot = snapshot

    def read_migration_snapshot(self, token_mint):
        if self._snapshot is None:
            raise (
                _stage27_4_src_errors.Stage27MigrationSourceError(
                    "SOURCE_FAILED",
                    source_label="bridge_fake_migration",
                )
            )
        return self._snapshot


class _BridgeFrozenStage27_5Clock:
    def __init__(self, iso: str = _BRIDGE_FIXED_UTC_ISO) -> None:
        self._iso = iso

    def now_utc_iso(self) -> str:
        return self._iso


def _bridge_sol_sources() -> _Stage27_6SourcesForBridge:
    price = _PriceSourceSnapshot(
        price_value="0.001",
        price_unit=_PRICE_UNIT_SOL,
        source_label="bridge_birdeye",
        fetched_at_utc=_BRIDGE_FIXED_UTC_ISO,
    )
    ath = _AthSourceSnapshot(
        ath_value="0.005",
        ath_unit=_ATH_UNIT_SOL,
        source_label="bridge_birdeye",
        ath_observed_at_utc="2026-05-22T11:30:00+00:00",
        window_starts_post_migration=True,
    )
    migration = _MigrationSourceSnapshot(
        migration_event_id="bridge-mig-1",
        migration_timestamp_utc="2026-05-22T11:00:00+00:00",
        migration_source="ON_CHAIN_MIGRATION_EVENT",
        source_event_ref="bridge-prov-mig-1",
        raw_capture_ref="bridge-rcap-mig-1",
    )
    return _Stage27_6SourcesForBridge(
        price_source=_BridgeFakePriceSource(snapshot=price),
        ath_source=_BridgeFakeAthSource(snapshot=ath),
        migration_source=_BridgeFakeMigrationSource(
            snapshot=migration,
        ),
        stage27_4_clock=_FrozenStage27_4Clock(
            fixed_utc=_BRIDGE_FIXED_UTC,
        ),
        stage27_5_clock=_BridgeFrozenStage27_5Clock(),
        price_staleness_threshold_seconds=60,
    )


def _bridge_usdc_sources() -> _Stage27_6SourcesForBridge:
    price = _PriceSourceSnapshot(
        price_value="0.12",
        price_unit=_PRICE_UNIT_USDC,
        source_label="bridge_birdeye",
        fetched_at_utc=_BRIDGE_FIXED_UTC_ISO,
    )
    ath = _AthSourceSnapshot(
        ath_value="1.50",
        ath_unit=_ATH_UNIT_USDC,
        source_label="bridge_birdeye",
        ath_observed_at_utc="2026-05-22T11:30:00+00:00",
        window_starts_post_migration=True,
    )
    migration = _MigrationSourceSnapshot(
        migration_event_id="bridge-mig-1",
        migration_timestamp_utc="2026-05-22T11:00:00+00:00",
        migration_source="ON_CHAIN_MIGRATION_EVENT",
        source_event_ref="bridge-prov-mig-1",
        raw_capture_ref="bridge-rcap-mig-1",
    )
    return _Stage27_6SourcesForBridge(
        price_source=_BridgeFakePriceSource(snapshot=price),
        ath_source=_BridgeFakeAthSource(snapshot=ath),
        migration_source=_BridgeFakeMigrationSource(
            snapshot=migration,
        ),
        stage27_4_clock=_FrozenStage27_4Clock(
            fixed_utc=_BRIDGE_FIXED_UTC,
        ),
        stage27_5_clock=_BridgeFrozenStage27_5Clock(),
        price_staleness_threshold_seconds=60,
    )


def _bridge_build_normalized_event(
    *,
    base_mint: Optional[str],
    quote_mint: Optional[str],
    pool_account: Optional[str],
    pool_program_id: Optional[str],
    provider_pair_type_hint: Optional[str],
    provider_quote_asset_hint: Optional[str],
):
    """Build a Stage 28.10 NormalizedEvent with explicit hint axes.

    The base_mint kwarg also doubles as the upstream ``mint`` field
    (the Stage 27.3 adapter's ``token_mint`` projection reads ``mint``
    from the upstream event). When ``base_mint`` is ``None`` we pass
    the safe synthetic ``_BRIDGE_BASE_MINT`` as ``mint`` so the
    Stage 27.3 composer still has a token mint and reaches the
    classifier — the test then asserts the classifier returned
    UNRESOLVED because every hint axis was None.
    """
    return _build_normalized_event(
        event_id="stage28_10_bridge_evt_001",
        provider_event_id="bridge_evt_001",
        provider_name="bridge_provider",
        mint=base_mint or _BRIDGE_BASE_MINT,
        event_type="swap",
        observed_at_utc=_BRIDGE_FIXED_UTC_ISO,
        raw_event_hash="stage28_10_bridge_sig_001",
        quote_mint=quote_mint,
        pool_account=pool_account,
        pool_program_id=pool_program_id,
        base_mint=base_mint,
        bonding_curve_program_id=None,
        bonding_curve_version_hint=None,
        provider_quote_asset_hint=provider_quote_asset_hint,
        provider_pair_type_hint=provider_pair_type_hint,
        provider_bonding_curve_version_hint=None,
    )


def test_stage29_3b_default_assembler_sol_hints_not_unknown_pair():
    """Stage 29.3B regression: a Stage 28.10 NormalizedEvent carrying
    the SOL hint quartet (quote_mint=WSOL, provider_pair_type_hint=
    PUMP_SOL, provider_quote_asset_hint=SOL, pool_account /
    pool_program_id / base_mint populated) MUST classify as a SOL
    pair and NOT collapse to SUPPRESSED_UNKNOWN_PAIR.
    """
    sources = _bridge_sol_sources()
    assembler = Stage28_9DefaultCandidateAssembler(sources=sources)
    event = _bridge_build_normalized_event(
        base_mint=_BRIDGE_BASE_MINT,
        quote_mint=_KNOWN_WRAPPED_SOL_MINT,
        pool_account=_BRIDGE_POOL_ACCOUNT,
        pool_program_id=_BRIDGE_PUMPSWAP_PROGRAM_ID,
        provider_pair_type_hint="PUMP_SOL",
        provider_quote_asset_hint="SOL",
    )
    record = assembler.assemble(event, candidate_id="cand_sol_001")
    assert record.candidate_status != (
        CANDIDATE_STATUS_SUPPRESSED_UNKNOWN_PAIR
    )
    assert record.candidate_status != (
        CANDIDATE_STATUS_SUPPRESSED_DISAGREE_PAIR
    )
    # Stage 27.6 with write_artifacts=False emits ASSEMBLED for a
    # fully-classified SOL candidate.
    assert record.candidate_status == CANDIDATE_STATUS_ASSEMBLED
    assert record.candidate_reason == CANDIDATE_REASON_RENDERED_OK


def test_stage29_3b_default_assembler_usdc_hints_not_unknown_pair():
    """Stage 29.3B: a USDC hint quartet MUST classify as USDC (not
    UNKNOWN). Stage 27.6 routes USDC into the USDC observe-only
    lane via candidate_reason=USDC_OBSERVE_ONLY; the status is NOT
    SUPPRESSED_UNKNOWN_PAIR.
    """
    sources = _bridge_usdc_sources()
    assembler = Stage28_9DefaultCandidateAssembler(sources=sources)
    event = _bridge_build_normalized_event(
        base_mint=_BRIDGE_BASE_MINT,
        quote_mint=_KNOWN_USDC_MINT,
        pool_account=_BRIDGE_POOL_ACCOUNT,
        pool_program_id=_BRIDGE_PUMPSWAP_PROGRAM_ID,
        provider_pair_type_hint="PUMP_USDC",
        provider_quote_asset_hint="USDC",
    )
    record = assembler.assemble(
        event, candidate_id="cand_usdc_001",
    )
    assert record.candidate_status != (
        CANDIDATE_STATUS_SUPPRESSED_UNKNOWN_PAIR
    )
    assert record.candidate_reason == CANDIDATE_REASON_USDC_OBSERVE_ONLY


def test_stage29_3b_default_assembler_no_hints_stays_unknown_pair():
    """Stage 29.3B: when EVERY hint axis is None (the pre-29.3B
    behaviour for events that never carried hints) the candidate
    MUST still collapse to SUPPRESSED_UNKNOWN_PAIR. Proves the
    Stage 28.9 hint-forwarding never silently promotes UNKNOWN to
    SOL.
    """
    sources = _bridge_sol_sources()
    assembler = Stage28_9DefaultCandidateAssembler(sources=sources)
    event = _bridge_build_normalized_event(
        base_mint=None,
        quote_mint=None,
        pool_account=None,
        pool_program_id=None,
        provider_pair_type_hint=None,
        provider_quote_asset_hint=None,
    )
    record = assembler.assemble(
        event, candidate_id="cand_none_001",
    )
    assert record.candidate_status == (
        CANDIDATE_STATUS_SUPPRESSED_UNKNOWN_PAIR
    )
    assert record.candidate_reason == (
        CANDIDATE_REASON_UNKNOWN_PAIR_LIVE_SUPPRESSED
    )

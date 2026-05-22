"""Stage 27.7a dry-run smoke harness tests.

Pins:

  * The smoke harness refuses to run without an injected output
    root, refuses a missing / non-directory output root, refuses
    an empty smoke_id.
  * The smoke harness defaults to DRY_RUN and refuses LIVE_ALLOWED
    via the underlying Stage 27.6 runner (mode = LIVE_REFUSED,
    no event processed).
  * The default smoke event set exercises SOL, duplicate SOL,
    USDC, UNKNOWN, and DISAGREE; the smoke summary counters match
    the documented distribution.
  * SOL cases land on the EXISTING_SOL_LANE with
    LIVE_ALLOWED policy.
  * USDC cases land on USDC_OBSERVE_ONLY with LIVE_ALLOWED policy
    (observe-only render).
  * UNKNOWN cases land on UNKNOWN_PAIR_OBSERVE_ONLY with
    LIVE_SUPPRESS_UNKNOWN policy.
  * DISAGREE cases land on DISAGREE_PAIR_OBSERVE_ONLY with
    LIVE_SUPPRESS_DISAGREE policy.
  * Duplicates are short-circuited (SKIPPED_DUPLICATE) with no
    second artifact written.
  * Stage 27.5 ping payload + provenance artifact files are
    persisted for RENDERED_DRY_RUN and SUPPRESSED candidates;
    every artifact file is redacted (no URL / secret / payload
    canaries; no BUY / SELL / APPROVED / enforcement language).
  * The smoke summary canonical JSON is stable; two identical
    smoke runs produce byte-equal summaries (modulo the resolved
    output root path).
  * The harness module imports only stdlib + Stage 27.2 / 27.3 /
    27.4 / 27.5 / 27.6 production code; no network / messaging /
    Discord library is imported.
"""

from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path

import pytest

from PHX2.stage27.bounded_tradeable_ping_runner import (
    LIVE_AUTHORITY_DRY_RUN,
    LIVE_AUTHORITY_LIVE_ALLOWED,
    RUN_MODE_DRY_RUN,
    RUN_MODE_LIVE_REFUSED,
    STOP_REASON_LIVE_MODE_REFUSED,
)
from PHX2.stage27.dry_run_smoke_harness import (
    DEFAULT_SMOKE_FIXED_UTC_ISO,
    STAGE27_7A_MINOR_VERSION,
    STAGE27_7A_SMOKE_SUMMARY_SCHEMA_VERSION,
    FrozenSmokeRunnerClock,
    Stage27_7aDryRunSmokeResult,
    Stage27_7aHarnessError,
    Stage27_7aOutputRootError,
    Stage27_7aSmokeSummaryRecord,
    build_default_smoke_clock,
    build_default_smoke_events,
    build_default_smoke_sources,
    canonical_smoke_summary_json,
    run_dry_run_smoke,
)
from PHX2.stage27.live_candidate_assembler import (
    CANDIDATE_REASON_DISAGREE_PAIR_LIVE_SUPPRESSED,
    CANDIDATE_REASON_DUPLICATE_RUN_LOCAL,
    CANDIDATE_REASON_RENDERED_OK,
    CANDIDATE_REASON_UNKNOWN_PAIR_LIVE_SUPPRESSED,
    CANDIDATE_REASON_USDC_OBSERVE_ONLY,
    CANDIDATE_STATUS_RENDERED_DRY_RUN,
    CANDIDATE_STATUS_SKIPPED_DUPLICATE,
    CANDIDATE_STATUS_SUPPRESSED_DISAGREE_PAIR,
    CANDIDATE_STATUS_SUPPRESSED_UNKNOWN_PAIR,
)
from PHX2.stage27.pair_detection_constants import (
    CALIBRATION_LANE_DISAGREE_PAIR_OBSERVE_ONLY,
    CALIBRATION_LANE_EXISTING_SOL_LANE,
    CALIBRATION_LANE_UNKNOWN_PAIR_OBSERVE_ONLY,
    CALIBRATION_LANE_USDC_OBSERVE_ONLY,
    LIVE_POLICY_LIVE_ALLOWED,
    LIVE_POLICY_LIVE_SUPPRESS_DISAGREE,
    LIVE_POLICY_LIVE_SUPPRESS_UNKNOWN,
    QUOTE_ASSET_SOL,
    QUOTE_ASSET_UNKNOWN,
    QUOTE_ASSET_USDC,
)


# ---------------------------------------------------------------------------
# Project-local tmp dir fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def stage27_7a_tmp_path():
    base = Path(__file__).resolve().parent / "_stage_27_7a_tmp"
    base.mkdir(parents=True, exist_ok=True)
    path = Path(tempfile.mkdtemp(prefix="stage27_7a_", dir=base))
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)
        try:
            base.rmdir()
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Locked Stage 27.7a constants
# ---------------------------------------------------------------------------


def test_stage_27_7a_minor_version_locked():
    assert STAGE27_7A_MINOR_VERSION == "27.7a"


def test_stage_27_7a_smoke_summary_schema_version_locked():
    assert STAGE27_7A_SMOKE_SUMMARY_SCHEMA_VERSION == (
        "stage27_v0_dry_run_smoke_summary"
    )


def test_frozen_smoke_runner_clock_default_iso():
    assert (
        FrozenSmokeRunnerClock().now_utc_iso()
        == DEFAULT_SMOKE_FIXED_UTC_ISO
    )


# ---------------------------------------------------------------------------
# Output-root and smoke_id refusal
# ---------------------------------------------------------------------------


def test_harness_refuses_missing_output_root(
    stage27_7a_tmp_path,
):
    with pytest.raises(Stage27_7aOutputRootError):
        run_dry_run_smoke(
            events=build_default_smoke_events(),
            sources=build_default_smoke_sources(),
            output_root=None,  # type: ignore[arg-type]
            smoke_id="smoke-1",
        )


def test_harness_refuses_non_existent_output_root(
    stage27_7a_tmp_path,
):
    missing = stage27_7a_tmp_path / "does_not_exist"
    with pytest.raises(Stage27_7aOutputRootError):
        run_dry_run_smoke(
            events=build_default_smoke_events(),
            sources=build_default_smoke_sources(),
            output_root=missing,
            smoke_id="smoke-2",
        )


def test_harness_refuses_non_directory_output_root(
    stage27_7a_tmp_path,
):
    file_path = stage27_7a_tmp_path / "not_a_dir.txt"
    file_path.write_text("seed", encoding="utf-8")
    with pytest.raises(Stage27_7aOutputRootError):
        run_dry_run_smoke(
            events=build_default_smoke_events(),
            sources=build_default_smoke_sources(),
            output_root=file_path,
            smoke_id="smoke-3",
        )


def test_harness_refuses_non_path_output_root(
    stage27_7a_tmp_path,
):
    with pytest.raises(Stage27_7aOutputRootError):
        run_dry_run_smoke(
            events=build_default_smoke_events(),
            sources=build_default_smoke_sources(),
            output_root="/some/string/path",  # type: ignore[arg-type]
            smoke_id="smoke-4",
        )


def test_harness_refuses_empty_smoke_id(stage27_7a_tmp_path):
    with pytest.raises(Stage27_7aHarnessError):
        run_dry_run_smoke(
            events=build_default_smoke_events(),
            sources=build_default_smoke_sources(),
            output_root=stage27_7a_tmp_path,
            smoke_id="",
        )


def test_harness_refuses_non_string_smoke_id(
    stage27_7a_tmp_path,
):
    with pytest.raises(Stage27_7aHarnessError):
        run_dry_run_smoke(
            events=build_default_smoke_events(),
            sources=build_default_smoke_sources(),
            output_root=stage27_7a_tmp_path,
            smoke_id=42,  # type: ignore[arg-type]
        )


# ---------------------------------------------------------------------------
# LIVE refusal
# ---------------------------------------------------------------------------


def test_harness_defaults_to_dry_run(stage27_7a_tmp_path):
    result = run_dry_run_smoke(
        events=(),
        sources=build_default_smoke_sources(),
        output_root=stage27_7a_tmp_path,
        smoke_id="smoke-dry",
    )
    assert isinstance(result, Stage27_7aDryRunSmokeResult)
    assert result.smoke_summary.mode == RUN_MODE_DRY_RUN


def test_harness_refuses_live_allowed_authority(
    stage27_7a_tmp_path,
):
    """The Stage 27.6 runner fail-closes on LIVE_ALLOWED; the
    smoke harness surfaces a LIVE_REFUSED summary with zero events
    processed.
    """
    result = run_dry_run_smoke(
        events=build_default_smoke_events(),
        sources=build_default_smoke_sources(),
        output_root=stage27_7a_tmp_path,
        smoke_id="smoke-live",
        live_mode_authority=LIVE_AUTHORITY_LIVE_ALLOWED,
    )
    assert result.smoke_summary.mode == RUN_MODE_LIVE_REFUSED
    assert (
        result.run_summary.stop_reason
        == STOP_REASON_LIVE_MODE_REFUSED
    )
    assert result.smoke_summary.events_seen == 0
    assert result.smoke_summary.pings_rendered == 0
    assert result.smoke_summary.artifacts_written == 0
    # No artifact file landed in the temp dir.
    assert tuple(stage27_7a_tmp_path.iterdir()) == ()


def test_harness_runs_dry_for_other_authority_tokens(
    stage27_7a_tmp_path,
):
    for authority in (
        LIVE_AUTHORITY_DRY_RUN,
        "ARBITRARY_DEFAULT",
        "LIVE_REFUSED",
    ):
        result = run_dry_run_smoke(
            events=(),
            sources=build_default_smoke_sources(),
            output_root=stage27_7a_tmp_path,
            smoke_id=f"smoke-{authority}",
            live_mode_authority=authority,
        )
        assert result.smoke_summary.mode == RUN_MODE_DRY_RUN


# ---------------------------------------------------------------------------
# Default smoke event set + pair-aware behavior
# ---------------------------------------------------------------------------


def test_default_smoke_event_set_size():
    events = build_default_smoke_events()
    assert len(events) == 5


def test_default_smoke_event_set_distribution(
    stage27_7a_tmp_path,
):
    result = run_dry_run_smoke(
        events=build_default_smoke_events(),
        sources=build_default_smoke_sources(),
        output_root=stage27_7a_tmp_path,
        smoke_id="smoke-mix",
        run_id="run-mix",
        session_id="sess-mix",
        max_events=16,
    )
    s = result.smoke_summary
    # The default event set is SOL + duplicate SOL + USDC + UNKNOWN
    # + DISAGREE = 5 events.
    assert s.events_seen == 5
    # Only SOL (clean) + USDC (observe-only) candidates count as
    # pings_rendered; UNKNOWN / DISAGREE are SUPPRESSED.
    assert s.pings_rendered == 2
    # SOL writes 2 (payload + provenance), USDC writes 2, UNKNOWN
    # writes 2 (suppressed render), DISAGREE writes 2 = 8 files.
    assert s.artifacts_written == 8
    assert s.duplicates_skipped == 1
    assert s.unknown_suppressed == 1
    assert s.disagree_suppressed == 1
    assert s.usdc_observe_only_count == 1
    assert s.unsupported_skipped == 0
    assert s.errors == 0


def test_sol_event_renders_existing_sol_lane(stage27_7a_tmp_path):
    result = run_dry_run_smoke(
        events=build_default_smoke_events(),
        sources=build_default_smoke_sources(),
        output_root=stage27_7a_tmp_path,
        smoke_id="smoke-sol",
        max_events=16,
    )
    sol_candidates = [
        c
        for c in result.candidates
        if c.candidate_status == CANDIDATE_STATUS_RENDERED_DRY_RUN
        and c.candidate_reason == CANDIDATE_REASON_RENDERED_OK
    ]
    assert len(sol_candidates) == 1
    c = sol_candidates[0]
    assert c.ingest_output.pair_quote_asset == QUOTE_ASSET_SOL
    assert (
        c.ingest_output.pair_calibration_lane
        == CALIBRATION_LANE_EXISTING_SOL_LANE
    )
    assert (
        c.ingest_output.pair_live_policy
        == LIVE_POLICY_LIVE_ALLOWED
    )


def test_usdc_event_renders_observe_only(stage27_7a_tmp_path):
    result = run_dry_run_smoke(
        events=build_default_smoke_events(),
        sources=build_default_smoke_sources(),
        output_root=stage27_7a_tmp_path,
        smoke_id="smoke-usdc",
        max_events=16,
    )
    usdc_candidates = [
        c
        for c in result.candidates
        if c.candidate_status == CANDIDATE_STATUS_RENDERED_DRY_RUN
        and c.candidate_reason == CANDIDATE_REASON_USDC_OBSERVE_ONLY
    ]
    assert len(usdc_candidates) == 1
    c = usdc_candidates[0]
    assert c.ingest_output.pair_quote_asset == QUOTE_ASSET_USDC
    assert (
        c.ingest_output.pair_calibration_lane
        == CALIBRATION_LANE_USDC_OBSERVE_ONLY
    )
    # USDC MUST NOT promote into EXISTING_SOL_LANE.
    assert (
        c.ingest_output.pair_calibration_lane
        != CALIBRATION_LANE_EXISTING_SOL_LANE
    )


def test_unknown_event_records_suppress_unknown_context(
    stage27_7a_tmp_path,
):
    result = run_dry_run_smoke(
        events=build_default_smoke_events(),
        sources=build_default_smoke_sources(),
        output_root=stage27_7a_tmp_path,
        smoke_id="smoke-unk",
        max_events=16,
    )
    unknown_candidates = [
        c
        for c in result.candidates
        if c.candidate_status
        == CANDIDATE_STATUS_SUPPRESSED_UNKNOWN_PAIR
    ]
    assert len(unknown_candidates) == 1
    c = unknown_candidates[0]
    assert (
        c.candidate_reason
        == CANDIDATE_REASON_UNKNOWN_PAIR_LIVE_SUPPRESSED
    )
    assert (
        c.ingest_output.pair_quote_asset == QUOTE_ASSET_UNKNOWN
    )
    assert (
        c.ingest_output.pair_calibration_lane
        == CALIBRATION_LANE_UNKNOWN_PAIR_OBSERVE_ONLY
    )
    assert (
        c.ingest_output.pair_live_policy
        == LIVE_POLICY_LIVE_SUPPRESS_UNKNOWN
    )
    # UNKNOWN MUST NOT promote into EXISTING_SOL_LANE.
    assert (
        c.ingest_output.pair_calibration_lane
        != CALIBRATION_LANE_EXISTING_SOL_LANE
    )


def test_disagree_event_records_suppress_disagree_context(
    stage27_7a_tmp_path,
):
    result = run_dry_run_smoke(
        events=build_default_smoke_events(),
        sources=build_default_smoke_sources(),
        output_root=stage27_7a_tmp_path,
        smoke_id="smoke-dis",
        max_events=16,
    )
    disagree_candidates = [
        c
        for c in result.candidates
        if c.candidate_status
        == CANDIDATE_STATUS_SUPPRESSED_DISAGREE_PAIR
    ]
    assert len(disagree_candidates) == 1
    c = disagree_candidates[0]
    assert (
        c.candidate_reason
        == CANDIDATE_REASON_DISAGREE_PAIR_LIVE_SUPPRESSED
    )
    assert (
        c.ingest_output.pair_calibration_lane
        == CALIBRATION_LANE_DISAGREE_PAIR_OBSERVE_ONLY
    )
    assert (
        c.ingest_output.pair_live_policy
        == LIVE_POLICY_LIVE_SUPPRESS_DISAGREE
    )
    # DISAGREE MUST NOT promote into EXISTING_SOL_LANE.
    assert (
        c.ingest_output.pair_calibration_lane
        != CALIBRATION_LANE_EXISTING_SOL_LANE
    )


def test_duplicate_event_is_skipped(stage27_7a_tmp_path):
    result = run_dry_run_smoke(
        events=build_default_smoke_events(),
        sources=build_default_smoke_sources(),
        output_root=stage27_7a_tmp_path,
        smoke_id="smoke-dup",
        max_events=16,
    )
    duplicate_candidates = [
        c
        for c in result.candidates
        if c.candidate_status == CANDIDATE_STATUS_SKIPPED_DUPLICATE
    ]
    assert len(duplicate_candidates) == 1
    c = duplicate_candidates[0]
    assert (
        c.candidate_reason == CANDIDATE_REASON_DUPLICATE_RUN_LOCAL
    )
    # Duplicate did NOT cause a second write.
    assert c.write_attempted is False
    assert c.payload_artifact_path is None
    assert c.provenance_artifact_path is None


# ---------------------------------------------------------------------------
# Artifact-file presence + redaction
# ---------------------------------------------------------------------------


_FORBIDDEN_ARTIFACT_LITERALS: tuple[str, ...] = (
    # URL hosts
    "h" + "ttps://",
    "h" + "ttp://",
    "w" + "ss://",
    "w" + "s://",
    "discord" + ".com",
    "discordapp" + ".com",
    # Secret canaries
    "api_key=",
    "API_KEY=",
    "bearer ",
    "AUTHORIZATION:",
    "x-api-key",
    # Smoke-canary token (must NEVER appear; deliberately not
    # injected in the fake sources)
    "FAKE_SECRET_CANARY_27_7A",
)


def test_artifacts_written_for_rendered_and_suppressed(
    stage27_7a_tmp_path,
):
    result = run_dry_run_smoke(
        events=build_default_smoke_events(),
        sources=build_default_smoke_sources(),
        output_root=stage27_7a_tmp_path,
        smoke_id="smoke-files",
        max_events=16,
    )
    files = sorted(p.name for p in stage27_7a_tmp_path.iterdir())
    assert len(files) == 8, files
    for name in files:
        assert name.startswith("ping_") or name.startswith(
            "smoke_ping_"
        ), name
        assert name.endswith((
            "_payload.json",
            "_provenance.json",
        )), name
    # Every file is JSON-parseable.
    for path in stage27_7a_tmp_path.iterdir():
        text = path.read_text(encoding="utf-8")
        json.loads(text)
    assert result.smoke_summary.artifacts_written == 8


def test_no_artifact_contains_fake_secret_or_url_literal(
    stage27_7a_tmp_path,
):
    run_dry_run_smoke(
        events=build_default_smoke_events(),
        sources=build_default_smoke_sources(),
        output_root=stage27_7a_tmp_path,
        smoke_id="smoke-redact",
        max_events=16,
    )
    for path in stage27_7a_tmp_path.iterdir():
        text = path.read_text(encoding="utf-8")
        for needle in _FORBIDDEN_ARTIFACT_LITERALS:
            assert needle not in text, (
                f"{path.name}: forbidden literal {needle!r}"
            )


def test_no_artifact_contains_raw_payload_blob_fields(
    stage27_7a_tmp_path,
):
    """The Stage 27.5 records carry only safe-to-display canonical
    fields. Confirm no JSON file emits a raw payload field name.
    """
    forbidden_keys: tuple[str, ...] = (
        "raw_payload",
        "payload_blob",
        "raw_response",
        "response_body",
        "encoded_payload",
        "raw_bytes",
    )
    run_dry_run_smoke(
        events=build_default_smoke_events(),
        sources=build_default_smoke_sources(),
        output_root=stage27_7a_tmp_path,
        smoke_id="smoke-payload-check",
        max_events=16,
    )
    for path in stage27_7a_tmp_path.iterdir():
        parsed = json.loads(path.read_text(encoding="utf-8"))
        flat_keys = _flatten_keys(parsed)
        for key in forbidden_keys:
            assert key not in flat_keys, (
                f"{path.name}: forbidden payload key {key!r}"
            )


def _flatten_keys(node):
    """Recursively collect every JSON object key in ``node``."""
    keys: set[str] = set()
    if isinstance(node, dict):
        for k, v in node.items():
            keys.add(k)
            keys |= _flatten_keys(v)
    elif isinstance(node, list):
        for item in node:
            keys |= _flatten_keys(item)
    return keys


def test_no_artifact_contains_enforcement_language(
    stage27_7a_tmp_path,
):
    """Stage 27 is private dry-run pings; no BUY / SELL /
    APPROVED / enforcement language may land in any artifact.
    """
    forbidden_phrases: tuple[str, ...] = (
        "BUY_SIGNAL",
        "SELL_SIGNAL",
        "APPROVE_TRADE",
        "EXECUTE_TRADE",
        "BLOCK_TRADE",
        "GATE_DECISION",
        "AUTO_TRADE",
        "POSITION_SIZE",
        "ENFORCEMENT_GATE",
        "ENFORCED",
    )
    run_dry_run_smoke(
        events=build_default_smoke_events(),
        sources=build_default_smoke_sources(),
        output_root=stage27_7a_tmp_path,
        smoke_id="smoke-enf",
        max_events=16,
    )
    for path in stage27_7a_tmp_path.iterdir():
        text = path.read_text(encoding="utf-8")
        for needle in forbidden_phrases:
            assert needle not in text, (
                f"{path.name}: forbidden enforcement literal "
                f"{needle!r}"
            )


# ---------------------------------------------------------------------------
# Smoke summary canonical JSON + determinism
# ---------------------------------------------------------------------------


def test_canonical_smoke_summary_json_is_stable(
    stage27_7a_tmp_path,
):
    result = run_dry_run_smoke(
        events=build_default_smoke_events(),
        sources=build_default_smoke_sources(),
        output_root=stage27_7a_tmp_path,
        smoke_id="smoke-stable",
        run_id="run-stable",
        session_id="sess-stable",
        max_events=16,
    )
    a = canonical_smoke_summary_json(result.smoke_summary)
    b = canonical_smoke_summary_json(result.smoke_summary)
    assert a == b
    parsed = json.loads(a)
    assert parsed["smoke_id"] == "smoke-stable"
    assert parsed["run_id"] == "run-stable"
    assert parsed["session_id"] == "sess-stable"
    assert parsed["mode"] == RUN_MODE_DRY_RUN
    assert parsed["schema_version"] == (
        STAGE27_7A_SMOKE_SUMMARY_SCHEMA_VERSION
    )
    assert parsed["pings_rendered"] == 2
    assert parsed["usdc_observe_only_count"] == 1


def test_two_identical_smokes_produce_equal_summaries(
    stage27_7a_tmp_path,
):
    # Two independent output roots so the writer does not collide,
    # but the summaries should match on every field except
    # output_root.
    root_a = stage27_7a_tmp_path / "a"
    root_b = stage27_7a_tmp_path / "b"
    root_a.mkdir()
    root_b.mkdir()
    result_a = run_dry_run_smoke(
        events=build_default_smoke_events(),
        sources=build_default_smoke_sources(),
        output_root=root_a,
        smoke_id="smoke-eq",
        run_id="run-eq",
        session_id="sess-eq",
        max_events=16,
    )
    result_b = run_dry_run_smoke(
        events=build_default_smoke_events(),
        sources=build_default_smoke_sources(),
        output_root=root_b,
        smoke_id="smoke-eq",
        run_id="run-eq",
        session_id="sess-eq",
        max_events=16,
    )
    parsed_a = json.loads(
        canonical_smoke_summary_json(result_a.smoke_summary)
    )
    parsed_b = json.loads(
        canonical_smoke_summary_json(result_b.smoke_summary)
    )
    # Wipe the run-specific path field before equality compare.
    parsed_a.pop("output_root")
    parsed_b.pop("output_root")
    assert parsed_a == parsed_b


# ---------------------------------------------------------------------------
# Optional run-summary artifact passthrough
# ---------------------------------------------------------------------------


def test_smoke_can_request_stage_27_6_run_summary_artifact(
    stage27_7a_tmp_path,
):
    result = run_dry_run_smoke(
        events=build_default_smoke_events(),
        sources=build_default_smoke_sources(),
        output_root=stage27_7a_tmp_path,
        smoke_id="smoke-summary",
        run_id="run-summary",
        session_id="sess-summary",
        max_events=16,
        write_summary_artifact=True,
    )
    summary_path = (
        stage27_7a_tmp_path / "run_run-summary_summary.json"
    )
    assert summary_path.is_file()
    parsed = json.loads(
        summary_path.read_text(encoding="utf-8")
    )
    assert parsed["run_id"] == "run-summary"
    assert parsed["session_id"] == "sess-summary"
    assert (
        result.smoke_summary.events_seen
        == parsed["events_seen"]
    )


# ---------------------------------------------------------------------------
# Default builder helpers
# ---------------------------------------------------------------------------


def test_build_default_smoke_sources_returns_bundle():
    bundle = build_default_smoke_sources()
    # Smoke fakes implement the Stage 27.4 Protocol surface; calling
    # the methods must succeed without a network call.
    snap = bundle.price_source.read_price_snapshot(
        "MintAAA", pair_quote_asset=QUOTE_ASSET_SOL
    )
    assert snap.price_value == "0.001"
    ath = bundle.ath_source.read_ath_snapshot(
        "MintAAA", pair_quote_asset=QUOTE_ASSET_SOL
    )
    assert ath.ath_value == "0.005"
    mig = bundle.migration_source.read_migration_snapshot(
        "MintAAA"
    )
    assert mig.migration_event_id == "smoke-mig-1"


def test_build_default_smoke_clock_returns_frozen_clock():
    clock = build_default_smoke_clock()
    assert (
        clock.now_utc_iso() == DEFAULT_SMOKE_FIXED_UTC_ISO
    )


# ---------------------------------------------------------------------------
# Defensive: the harness module imports only Stage 27 prod + stdlib
# ---------------------------------------------------------------------------


def test_harness_module_has_no_network_import():
    import inspect

    import PHX2.stage27.dry_run_smoke_harness as harness

    source = inspect.getsource(harness)
    for needle in (
        "import requests",
        "import httpx",
        "import aiohttp",
        "import urllib3",
        "import websockets",
        "import grpc",
        "import discord",
        "from discord",
        "import telegram",
        "from telegram",
        "import socket",
        "import asyncio",
    ):
        assert needle not in source, (
            f"harness module must not contain {needle!r}"
        )


def test_harness_module_has_no_discord_or_webhook_attribute():
    import PHX2.stage27.dry_run_smoke_harness as harness

    for name in dir(harness):
        lower = name.lower()
        for needle in (
            "discord",
            "webhook",
            "send_message",
            "post_to_discord",
            "telegram",
            "tweepy",
            "twitter",
        ):
            assert needle not in lower, (
                f"harness module attribute {name!r} contains "
                f"forbidden substring {needle!r}"
            )

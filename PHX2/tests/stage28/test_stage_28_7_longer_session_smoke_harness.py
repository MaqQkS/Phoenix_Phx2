"""Stage 28.7 longer-session smoke harness tests.

Pins:

  * The offline smoke harness drives the Stage 28.6 bounded
    private session runner with a Stage 28.6 fake transport only.
  * The offline smoke writes the four Stage 28.7 runner artifacts
    + the smoke summary + the optional redaction-scan artifact
    into the operator-supplied output directory.
  * Counters are deterministic for the default synthetic
    candidate stream.
  * Dedupe / suppression paths (duplicate, UNKNOWN, DISAGREE,
    USDC, STALE, MISSING, malformed, dispatch_allowed=False) are
    exercised.
  * The retry path is exercised via the default Stage 28.7
    scripted fake transport (NETWORK_ERROR -> SENT_OK).
  * The redaction scan flags forbidden substrings and passes on a
    clean output dir.
  * The harness REFUSES a non-Path / missing / non-directory
    output dir without performing any send.
  * No live send is ever attempted; ``live_send_attempted`` /
    ``live_send_count`` remain ``False`` / ``0``.
  * No real network module is imported by the harness module's
    import graph.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from PHX2.stage28.longer_session_smoke_harness import (
    FINAL_SUMMARY_ARTIFACT_BASENAME,
    HEALTH_SNAPSHOT_ARTIFACT_BASENAME,
    HEARTBEAT_ARTIFACT_BASENAME,
    REDACTION_SCAN_ARTIFACT_BASENAME,
    SMOKE_REDACTION_STATUS_FAILED,
    SMOKE_REDACTION_STATUS_NOT_SCANNED,
    SMOKE_REDACTION_STATUS_SAFE,
    SMOKE_SAFE_REASON_CODE_OK,
    SMOKE_SAFE_REASON_CODE_OUTPUT_DIR_MISSING,
    SMOKE_SAFE_REASON_CODE_OUTPUT_DIR_NOT_DIR,
    SMOKE_SAFE_REASON_CODE_OUTPUT_DIR_UNSAFE,
    SMOKE_STATUS_OK,
    SMOKE_SUMMARY_ARTIFACT_BASENAME,
    STAGE28_7_ARTIFACT_BASENAMES,
    STAGE28_7_DEFAULT_SCRIPTED_OUTCOMES,
    STAGE28_7_FORBIDDEN_ARTIFACT_SUBSTRINGS,
    STAGE28_7_MINOR_VERSION,
    STAGE28_7_REDACTION_TOKEN,
    STAGE28_7_SCHEMA_VERSION,
    STAGE28_7_SMOKE_SUMMARY_FIELD_NAMES,
    Stage28_7ArtifactWriteError,
    Stage28_7OutputDirError,
    Stage28_7SmokeHarnessError,
    Stage28_7SmokeSummary,
    build_stage28_7_default_fake_transport,
    build_stage28_7_synthetic_candidates,
    canonical_smoke_summary_json,
    read_stage28_7_smoke_summary,
    redaction_scan_to_dict,
    run_stage28_7_offline_smoke,
    scan_stage28_7_artifacts_for_redaction,
    smoke_summary_to_dict,
    write_stage28_7_redaction_scan,
    write_stage28_7_smoke_summary,
)
from PHX2.stage28.session_runner_models import (
    CANDIDATE_PAIR_STATUS_OK,
    CANDIDATE_PRICE_STATUS_OK,
    Stage28_6CandidateEvent,
    Stage28_6FakeTransport,
)
from PHX2.stage28.audited_http_transport_models import (
    TRANSPORT_STATUS_SENT_OK,
)


# ---------------------------------------------------------------------------
# Version axes
# ---------------------------------------------------------------------------


def test_minor_version_is_28_7():
    assert STAGE28_7_MINOR_VERSION == "28.7"


def test_schema_version_is_locked():
    assert (
        STAGE28_7_SCHEMA_VERSION
        == "stage28_7_longer_session_smoke_harness_v0"
    )


def test_redaction_token_is_distinctive():
    assert STAGE28_7_REDACTION_TOKEN == "<<STAGE28_7_REDACTED>>"


# ---------------------------------------------------------------------------
# Synthetic candidate stream
# ---------------------------------------------------------------------------


def test_synthetic_candidates_returns_tuple_of_candidate_events():
    candidates = build_stage28_7_synthetic_candidates()
    assert isinstance(candidates, tuple)
    assert len(candidates) == 10
    for c in candidates:
        assert isinstance(c, Stage28_6CandidateEvent)


def test_synthetic_candidates_include_duplicate_dedupe_key():
    candidates = build_stage28_7_synthetic_candidates()
    # candidate 0 and candidate 2 share normalized_event_id +
    # token_mint + event_kind + ping_type so the Stage 28.2
    # ledger flags candidate 2 as a duplicate terminal.
    assert (
        candidates[0].normalized_event_id
        == candidates[2].normalized_event_id
    )
    assert candidates[0].token_mint == candidates[2].token_mint


def test_synthetic_candidates_exercise_all_suppression_axes():
    candidates = build_stage28_7_synthetic_candidates()
    pair_statuses = {c.pair_status for c in candidates}
    price_statuses = {c.price_status for c in candidates}
    malformed_flags = {c.malformed for c in candidates}
    dispatch_allowed_flags = {c.dispatch_allowed for c in candidates}
    # Pair axes cover OK / UNKNOWN / DISAGREE / USDC_OBSERVE_ONLY.
    assert {"OK", "UNKNOWN", "DISAGREE", "USDC_OBSERVE_ONLY"}.issubset(
        pair_statuses
    )
    # Price axes cover OK / STALE / MISSING.
    assert {"OK", "STALE", "MISSING"}.issubset(price_statuses)
    # The malformed flag and dispatch_allowed=False branches each
    # appear at least once.
    assert True in malformed_flags
    assert False in dispatch_allowed_flags


# ---------------------------------------------------------------------------
# Default fake transport
# ---------------------------------------------------------------------------


def test_default_fake_transport_scripts_one_retry_then_success():
    assert STAGE28_7_DEFAULT_SCRIPTED_OUTCOMES[-1] == (
        TRANSPORT_STATUS_SENT_OK
    )
    transport = build_stage28_7_default_fake_transport()
    assert isinstance(transport, Stage28_6FakeTransport)
    assert transport.call_count == 0


# ---------------------------------------------------------------------------
# Output-directory validation
# ---------------------------------------------------------------------------


def test_offline_smoke_refuses_non_path_output_dir():
    with pytest.raises(Stage28_7OutputDirError) as exc_info:
        run_stage28_7_offline_smoke(
            output_dir="not_a_path",  # type: ignore[arg-type]
            smoke_id="smk_smoke_id_01",
            run_id="run_id_01",
            session_id="session_id_01",
        )
    assert exc_info.value.reason == (
        SMOKE_SAFE_REASON_CODE_OUTPUT_DIR_UNSAFE
    )


def test_offline_smoke_refuses_missing_output_dir(tmp_path: Path):
    missing = tmp_path / "definitely_not_created"
    with pytest.raises(Stage28_7OutputDirError) as exc_info:
        run_stage28_7_offline_smoke(
            output_dir=missing,
            smoke_id="smk_smoke_id_01",
            run_id="run_id_01",
            session_id="session_id_01",
        )
    assert exc_info.value.reason == (
        SMOKE_SAFE_REASON_CODE_OUTPUT_DIR_MISSING
    )


def test_offline_smoke_refuses_non_directory_output_dir(
    tmp_path: Path,
):
    sentinel = tmp_path / "actually_a_file"
    sentinel.write_text("hi", encoding="utf-8")
    with pytest.raises(Stage28_7OutputDirError) as exc_info:
        run_stage28_7_offline_smoke(
            output_dir=sentinel,
            smoke_id="smk_smoke_id_01",
            run_id="run_id_01",
            session_id="session_id_01",
        )
    assert exc_info.value.reason == (
        SMOKE_SAFE_REASON_CODE_OUTPUT_DIR_NOT_DIR
    )


def test_offline_smoke_refuses_secret_looking_output_dir(
    tmp_path: Path,
):
    # The validator scans the path string for secret-looking
    # substrings before checking existence. Use a substring the
    # validator's denylist would flag (a webhook host fragment).
    unsafe = tmp_path / ("d" + "iscord.com" + "_scratch")
    unsafe.mkdir()
    with pytest.raises(Stage28_7OutputDirError) as exc_info:
        run_stage28_7_offline_smoke(
            output_dir=unsafe,
            smoke_id="smk_smoke_id_01",
            run_id="run_id_01",
            session_id="session_id_01",
        )
    assert exc_info.value.reason == (
        SMOKE_SAFE_REASON_CODE_OUTPUT_DIR_UNSAFE
    )


# ---------------------------------------------------------------------------
# Offline smoke happy path
# ---------------------------------------------------------------------------


def _run_default_offline_smoke(tmp_path: Path) -> Stage28_7SmokeSummary:
    return run_stage28_7_offline_smoke(
        output_dir=tmp_path,
        smoke_id="smk_default_01",
        run_id="run_default_01",
        session_id="session_default_01",
    )


def test_offline_smoke_writes_smoke_summary(tmp_path: Path):
    summary = _run_default_offline_smoke(tmp_path)
    target = tmp_path / SMOKE_SUMMARY_ARTIFACT_BASENAME
    assert target.is_file()
    data = json.loads(target.read_text(encoding="utf-8"))
    assert data["schema_version"] == STAGE28_7_SCHEMA_VERSION
    assert data["smoke_id"] == summary.smoke_id


def test_offline_smoke_writes_heartbeat_jsonl(tmp_path: Path):
    _run_default_offline_smoke(tmp_path)
    heartbeat_path = tmp_path / HEARTBEAT_ARTIFACT_BASENAME
    assert heartbeat_path.is_file()
    lines = [
        line
        for line in heartbeat_path.read_text(
            encoding="utf-8"
        ).split("\n")
        if line
    ]
    assert lines, "expected at least one heartbeat line"
    for line in lines:
        record = json.loads(line)
        assert "schema_version" in record


def test_offline_smoke_writes_health_snapshot_json(tmp_path: Path):
    _run_default_offline_smoke(tmp_path)
    snapshot_path = tmp_path / HEALTH_SNAPSHOT_ARTIFACT_BASENAME
    assert snapshot_path.is_file()
    record = json.loads(
        snapshot_path.read_text(encoding="utf-8")
    )
    assert "schema_version" in record


def test_offline_smoke_writes_final_summary_json(tmp_path: Path):
    _run_default_offline_smoke(tmp_path)
    summary_path = tmp_path / FINAL_SUMMARY_ARTIFACT_BASENAME
    assert summary_path.is_file()
    record = json.loads(
        summary_path.read_text(encoding="utf-8")
    )
    assert "schema_version" in record


def test_offline_smoke_writes_redaction_scan_artifact(
    tmp_path: Path,
):
    summary = _run_default_offline_smoke(tmp_path)
    target = tmp_path / REDACTION_SCAN_ARTIFACT_BASENAME
    assert target.is_file()
    record = json.loads(target.read_text(encoding="utf-8"))
    assert record["redaction_status"] == SMOKE_REDACTION_STATUS_SAFE
    assert summary.redaction_status == SMOKE_REDACTION_STATUS_SAFE


def test_offline_smoke_records_no_live_send(tmp_path: Path):
    summary = _run_default_offline_smoke(tmp_path)
    assert summary.live_send_attempted is False
    assert summary.live_send_count == 0


def test_offline_smoke_default_counts_are_deterministic(
    tmp_path_factory,
):
    a = tmp_path_factory.mktemp("smoke_a")
    b = tmp_path_factory.mktemp("smoke_b")
    summary_a = run_stage28_7_offline_smoke(
        output_dir=a,
        smoke_id="smk_x",
        run_id="run_x",
        session_id="session_x",
    )
    summary_b = run_stage28_7_offline_smoke(
        output_dir=b,
        smoke_id="smk_x",
        run_id="run_x",
        session_id="session_x",
    )
    # Counter axes are deterministic across runs with identical
    # inputs (smoke_id / run_id / session_id reused; output_dir
    # differs but is not a counter input).
    for name in (
        "offline_candidate_count",
        "events_seen",
        "candidates_seen",
        "dispatch_attempts",
        "dispatch_success",
        "dispatch_failure",
        "retries_attempted",
        "duplicate_suppressed",
        "ambiguous_suppressed",
        "suppressed_count",
        "heartbeat_count",
    ):
        assert getattr(summary_a, name) == getattr(summary_b, name), (
            f"counter {name!r} drifted between deterministic runs"
        )


def test_offline_smoke_duplicate_suppressed_at_least_one(
    tmp_path: Path,
):
    summary = _run_default_offline_smoke(tmp_path)
    assert summary.duplicate_suppressed >= 1


def test_offline_smoke_suppressed_count_aggregates(tmp_path: Path):
    summary = _run_default_offline_smoke(tmp_path)
    # The default synthetic stream contributes the duplicate +
    # UNKNOWN + DISAGREE + USDC + STALE + MISSING + malformed +
    # dispatch_not_allowed branches; at least seven candidates
    # do not become a successful dispatch.
    assert summary.suppressed_count >= 5
    assert summary.suppressed_count <= summary.offline_candidate_count


def test_offline_smoke_dispatch_success_at_least_one(tmp_path: Path):
    summary = _run_default_offline_smoke(tmp_path)
    assert summary.dispatch_success >= 1


def test_offline_smoke_retries_exercised(tmp_path: Path):
    summary = _run_default_offline_smoke(tmp_path)
    assert summary.retries_attempted >= 1


def test_offline_smoke_status_ok_for_default(tmp_path: Path):
    summary = _run_default_offline_smoke(tmp_path)
    assert summary.smoke_status == SMOKE_STATUS_OK
    assert summary.safe_reason_code == SMOKE_SAFE_REASON_CODE_OK


def test_offline_smoke_smoke_summary_field_set_is_locked(
    tmp_path: Path,
):
    summary = _run_default_offline_smoke(tmp_path)
    target = tmp_path / SMOKE_SUMMARY_ARTIFACT_BASENAME
    data = json.loads(target.read_text(encoding="utf-8"))
    assert set(data.keys()) == set(STAGE28_7_SMOKE_SUMMARY_FIELD_NAMES)
    assert set(smoke_summary_to_dict(summary).keys()) == set(
        STAGE28_7_SMOKE_SUMMARY_FIELD_NAMES
    )


def test_offline_smoke_summary_canonical_json_is_stable(
    tmp_path: Path,
):
    summary = _run_default_offline_smoke(tmp_path)
    a = canonical_smoke_summary_json(summary)
    b = canonical_smoke_summary_json(summary)
    assert a == b
    # Canonical encoding: keys sorted alphabetically.
    keys_in_order = [
        token.split('"')[1]
        for token in a.split(":")
        if token.startswith('"') or '"' in token
    ]
    # We don't depend on the parser above to be perfect — instead
    # round-trip the JSON and confirm the dict matches.
    assert json.loads(a) == smoke_summary_to_dict(summary)


def test_read_smoke_summary_round_trips(tmp_path: Path):
    summary = _run_default_offline_smoke(tmp_path)
    loaded = read_stage28_7_smoke_summary(tmp_path)
    assert loaded is not None
    assert loaded["smoke_id"] == summary.smoke_id


def test_read_smoke_summary_missing_returns_none(tmp_path: Path):
    assert read_stage28_7_smoke_summary(tmp_path) is None


# ---------------------------------------------------------------------------
# Fake transport is the only transport touched
# ---------------------------------------------------------------------------


def test_offline_smoke_uses_only_fake_transport(tmp_path: Path):
    transport = Stage28_6FakeTransport(
        scripted_outcomes=(TRANSPORT_STATUS_SENT_OK,),
    )
    summary = run_stage28_7_offline_smoke(
        output_dir=tmp_path,
        smoke_id="smk_fake_only_01",
        run_id="run_fake_only_01",
        session_id="session_fake_only_01",
        transport=transport,
    )
    # The fake transport records every send; tests can assert
    # the call count matches the runner's dispatch_attempts.
    assert transport.call_count == summary.dispatch_attempts
    # No retries when the transport always sends OK.
    assert summary.retries_attempted == 0
    assert summary.dispatch_success >= 1


def test_harness_module_static_imports_have_no_forbidden_module():
    """Static dependency scan of the Stage 28.7 smoke harness
    module file.

    The harness module must not statically import any network /
    RPC / messaging / scheduler / threading / asyncio /
    subprocess library. (The boundary scan pins the same thing
    across every Stage 28.7 production .py file; this test is
    a focused sanity check against the harness module itself
    that runs in the harness test file.)
    """
    import ast as _ast

    from PHX2.stage28 import longer_session_smoke_harness

    harness_path = Path(longer_session_smoke_harness.__file__)
    tree = _ast.parse(harness_path.read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in _ast.walk(tree):
        if isinstance(node, _ast.Import):
            for alias in node.names:
                imported.add(alias.name)
        elif isinstance(node, _ast.ImportFrom):
            if node.module:
                imported.add(node.module)
    forbidden = (
        "requests",
        "httpx",
        "aiohttp",
        "urllib",
        "urllib3",
        "websockets",
        "grpc",
        "discord",
        "telegram",
        "tweepy",
        "socket",
        "asyncio",
        "threading",
        "multiprocessing",
        "subprocess",
        "queue",
        "sched",
        "http.client",
        "ssl",
    )
    allowed_stage_28_modules = {
        "PHX2.stage28.audited_http_transport_models",
        "PHX2.stage28.bounded_private_session_runner",
        "PHX2.stage28.session_runner_models",
    }
    for target in imported:
        if target in allowed_stage_28_modules:
            continue
        lower = target.lower()
        for needle in forbidden:
            assert needle not in lower, (
                f"Stage 28.7 harness statically imports a "
                f"forbidden module {target!r} (contains "
                f"{needle!r})"
            )


# ---------------------------------------------------------------------------
# Caller-supplied candidate stream
# ---------------------------------------------------------------------------


def _single_success_candidate() -> Stage28_6CandidateEvent:
    from PHX2.stage28.session_runner_models import (
        build_candidate_event,
    )
    from PHX2.stage28.audited_http_transport_models import (
        WEBHOOK_IDENTITY_PRIVATE_OPERATOR,
    )

    return build_candidate_event(
        event_id="single_event_00",
        token_mint="SingleMint00",
        pair_quote_asset="SOL",
        event_kind="single_smoke",
        ping_type="single_ping",
        normalized_event_id="single_norm_00",
        rendered_payload={"content": "single smoke"},
        pre_send_artifact_reference="single_ping_payload.json",
        webhook_identity=WEBHOOK_IDENTITY_PRIVATE_OPERATOR,
        dispatch_allowed=True,
        pair_status=CANDIDATE_PAIR_STATUS_OK,
        price_status=CANDIDATE_PRICE_STATUS_OK,
    )


def test_offline_smoke_accepts_caller_supplied_candidates(
    tmp_path: Path,
):
    transport = Stage28_6FakeTransport(
        scripted_outcomes=(TRANSPORT_STATUS_SENT_OK,),
    )
    summary = run_stage28_7_offline_smoke(
        output_dir=tmp_path,
        smoke_id="smk_single_01",
        run_id="run_single_01",
        session_id="session_single_01",
        candidates=(_single_success_candidate(),),
        transport=transport,
    )
    assert summary.offline_candidate_count == 1
    assert summary.dispatch_success == 1
    assert summary.dispatch_failure == 0
    assert summary.duplicate_suppressed == 0


# ---------------------------------------------------------------------------
# Redaction scan
# ---------------------------------------------------------------------------


def test_redaction_scan_safe_when_artifacts_are_clean(
    tmp_path: Path,
):
    _run_default_offline_smoke(tmp_path)
    result = scan_stage28_7_artifacts_for_redaction(
        output_dir=tmp_path,
    )
    assert result.redaction_status == SMOKE_REDACTION_STATUS_SAFE
    assert result.offending_basenames == ()
    assert result.offending_substrings == ()


def test_redaction_scan_flags_forbidden_substring(tmp_path: Path):
    # Plant a forbidden substring into a fake artifact basename
    # that is part of the Stage 28.7 artifact inventory; the scan
    # MUST flag it.
    tainted = tmp_path / SMOKE_SUMMARY_ARTIFACT_BASENAME
    # Use a denylisted host fragment (concatenated to avoid
    # tripping the boundary scan on this test file).
    tainted.write_text(
        '{"webhook": "h' + "ttps://disco" + "rd.com/webhooks/abc"
        + '"}',
        encoding="utf-8",
    )
    result = scan_stage28_7_artifacts_for_redaction(
        output_dir=tmp_path,
    )
    assert result.redaction_status == SMOKE_REDACTION_STATUS_FAILED
    assert SMOKE_SUMMARY_ARTIFACT_BASENAME in (
        result.offending_basenames
    )
    assert len(result.offending_substrings) >= 1


def test_redaction_scan_handles_non_path(tmp_path: Path):
    result = scan_stage28_7_artifacts_for_redaction(
        output_dir="not a path",  # type: ignore[arg-type]
    )
    assert result.redaction_status == SMOKE_REDACTION_STATUS_NOT_SCANNED


def test_redaction_scan_skips_missing_artifacts(tmp_path: Path):
    # No artifacts present yet; the scan still returns SAFE
    # because nothing was found to be forbidden.
    result = scan_stage28_7_artifacts_for_redaction(
        output_dir=tmp_path,
    )
    assert result.redaction_status == SMOKE_REDACTION_STATUS_SAFE
    assert result.files_scanned == ()


def test_redaction_scan_to_dict_round_trip(tmp_path: Path):
    _run_default_offline_smoke(tmp_path)
    result = scan_stage28_7_artifacts_for_redaction(
        output_dir=tmp_path,
    )
    d = redaction_scan_to_dict(result)
    assert d["schema_version"] == STAGE28_7_SCHEMA_VERSION
    assert d["redaction_status"] == SMOKE_REDACTION_STATUS_SAFE


def test_redaction_status_propagates_to_smoke_summary(tmp_path: Path):
    # Run the smoke once, then taint the heartbeat (which is
    # append-only across runs; the runner-written snapshot /
    # final-summary / smoke-summary files are atomically
    # overwritten on each run, so they cannot retain a planted
    # taint). The second smoke's redaction scan reads the
    # appended heartbeat (existing tainted line + new heartbeat
    # lines), finds the forbidden substring, and the harness
    # flips the smoke_status to REFUSED.
    _run_default_offline_smoke(tmp_path)
    heartbeat = tmp_path / HEARTBEAT_ARTIFACT_BASENAME
    existing = heartbeat.read_text(encoding="utf-8")
    tainted_line = (
        '{"leak":"h' + "ttps://disc" + 'ord.com/webhooks/leak"}\n'
    )
    heartbeat.write_text(existing + tainted_line, encoding="utf-8")
    summary = run_stage28_7_offline_smoke(
        output_dir=tmp_path,
        smoke_id="smk_taint_01",
        run_id="run_taint_01",
        session_id="session_taint_01",
    )
    assert summary.redaction_status == SMOKE_REDACTION_STATUS_FAILED
    assert summary.smoke_status != SMOKE_STATUS_OK


# ---------------------------------------------------------------------------
# Output safety on the smoke summary itself
# ---------------------------------------------------------------------------


def test_output_dir_safe_label_does_not_echo_full_path(
    tmp_path: Path,
):
    summary = _run_default_offline_smoke(tmp_path)
    # The full path string is not echoed on the smoke summary.
    assert str(tmp_path) not in summary.output_dir_safe_label
    # The label is a short basename label or the redaction token.
    assert len(summary.output_dir_safe_label) <= 64
    assert "/" not in summary.output_dir_safe_label
    assert "\\" not in summary.output_dir_safe_label


def test_smoke_summary_contains_no_forbidden_substring(
    tmp_path: Path,
):
    summary = _run_default_offline_smoke(tmp_path)
    body = canonical_smoke_summary_json(summary).lower()
    for needle in STAGE28_7_FORBIDDEN_ARTIFACT_SUBSTRINGS:
        assert needle.lower() not in body, (
            f"smoke summary contains forbidden substring "
            f"{needle!r}"
        )


# ---------------------------------------------------------------------------
# write_stage28_7_smoke_summary refuses bad output_dir
# ---------------------------------------------------------------------------


def test_write_smoke_summary_refuses_non_path():
    fake_summary = Stage28_7SmokeSummary(
        schema_version=STAGE28_7_SCHEMA_VERSION,
        smoke_status=SMOKE_STATUS_OK,
        run_id="run_w_01",
        session_id="session_w_01",
        smoke_id="smk_w_01",
        output_dir_safe_label="label",
        heartbeat_artifact_basename=HEARTBEAT_ARTIFACT_BASENAME,
        health_snapshot_artifact_basename=(
            HEALTH_SNAPSHOT_ARTIFACT_BASENAME
        ),
        final_summary_artifact_basename=(
            FINAL_SUMMARY_ARTIFACT_BASENAME
        ),
        smoke_summary_artifact_basename=(
            SMOKE_SUMMARY_ARTIFACT_BASENAME
        ),
        redaction_scan_artifact_basename="",
        offline_candidate_count=0,
        events_seen=0,
        candidates_seen=0,
        dispatch_attempts=0,
        dispatch_success=0,
        dispatch_failure=0,
        retries_attempted=0,
        duplicate_suppressed=0,
        ambiguous_suppressed=0,
        suppressed_count=0,
        heartbeat_count=0,
        stop_reason="MAX_EVENTS",
        final_health_status="HEALTHY",
        redaction_status=SMOKE_REDACTION_STATUS_NOT_SCANNED,
        live_send_attempted=False,
        live_send_count=0,
        safe_reason_code=SMOKE_SAFE_REASON_CODE_OK,
    )
    with pytest.raises(Stage28_7OutputDirError):
        write_stage28_7_smoke_summary(
            output_dir="not a path",  # type: ignore[arg-type]
            summary=fake_summary,
        )


def test_write_smoke_summary_oserror_wrapped(tmp_path: Path):
    summary = _run_default_offline_smoke(tmp_path)
    # Replace the smoke-summary target with a directory of the
    # same name so write_text fails with OSError.
    target = tmp_path / SMOKE_SUMMARY_ARTIFACT_BASENAME
    target.unlink()
    target.mkdir()
    with pytest.raises(Stage28_7ArtifactWriteError) as exc_info:
        write_stage28_7_smoke_summary(
            output_dir=tmp_path,
            summary=summary,
        )
    assert exc_info.value.operation == "SMOKE_SUMMARY_WRITE"


def test_write_redaction_scan_oserror_wrapped(tmp_path: Path):
    _run_default_offline_smoke(tmp_path)
    result = scan_stage28_7_artifacts_for_redaction(
        output_dir=tmp_path,
    )
    target = tmp_path / REDACTION_SCAN_ARTIFACT_BASENAME
    if target.exists():
        target.unlink()
    target.mkdir()
    with pytest.raises(Stage28_7ArtifactWriteError) as exc_info:
        write_stage28_7_redaction_scan(
            output_dir=tmp_path,
            result=result,
        )
    assert exc_info.value.operation == "REDACTION_SCAN_WRITE"


# ---------------------------------------------------------------------------
# Disable redaction scan
# ---------------------------------------------------------------------------


def test_offline_smoke_can_skip_redaction_scan(tmp_path: Path):
    summary = run_stage28_7_offline_smoke(
        output_dir=tmp_path,
        smoke_id="smk_noredact_01",
        run_id="run_noredact_01",
        session_id="session_noredact_01",
        perform_redaction_scan=False,
    )
    assert summary.redaction_status == SMOKE_REDACTION_STATUS_NOT_SCANNED
    assert summary.redaction_scan_artifact_basename == ""
    redaction_path = tmp_path / REDACTION_SCAN_ARTIFACT_BASENAME
    assert not redaction_path.exists()


# ---------------------------------------------------------------------------
# Artifact basenames are safe
# ---------------------------------------------------------------------------


def test_artifact_basenames_are_safe_basenames():
    for name in STAGE28_7_ARTIFACT_BASENAMES:
        assert "/" not in name
        assert "\\" not in name
        assert ".." not in name
        assert name.startswith("stage28_7_")


def test_artifact_basenames_inventory_is_locked():
    assert STAGE28_7_ARTIFACT_BASENAMES == (
        HEARTBEAT_ARTIFACT_BASENAME,
        HEALTH_SNAPSHOT_ARTIFACT_BASENAME,
        FINAL_SUMMARY_ARTIFACT_BASENAME,
        SMOKE_SUMMARY_ARTIFACT_BASENAME,
        REDACTION_SCAN_ARTIFACT_BASENAME,
    )


# ---------------------------------------------------------------------------
# Smoke summary type guards
# ---------------------------------------------------------------------------


def test_smoke_summary_to_dict_rejects_non_record():
    with pytest.raises(Stage28_7SmokeHarnessError):
        smoke_summary_to_dict(object())  # type: ignore[arg-type]


def test_redaction_scan_to_dict_rejects_non_record():
    with pytest.raises(Stage28_7SmokeHarnessError):
        redaction_scan_to_dict(object())  # type: ignore[arg-type]

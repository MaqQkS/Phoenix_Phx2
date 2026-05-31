"""Stage 30.9.1 artifact bridge models tests.

Covers the passive frozen records, the closed-set bridge status / reason
vocabularies + their predicates, the private webhook identity allowlist +
predicate, the deterministic fake scenario builders (default + mismatch),
and the field-name helpers. Pure / offline; no filesystem, no env, no
network.
"""

from __future__ import annotations

import dataclasses

import pytest

from PHX2.stage30.stage30_9_artifact_bridge_models import (
    BRIDGE_REASON_AMBIGUOUS_JOIN,
    BRIDGE_REASON_COUNT_MISMATCH,
    BRIDGE_REASON_INDEX_REJECTED,
    BRIDGE_REASON_MISSING_CANDIDATE_ID,
    BRIDGE_REASON_MISSING_CAPTURE_INDEX,
    BRIDGE_REASON_MISSING_COMPACT_BODY,
    BRIDGE_REASON_MISSING_DEDUPE_KEY,
    BRIDGE_REASON_MISSING_PING_ID,
    BRIDGE_REASON_MISSING_RUN_ID,
    BRIDGE_REASON_MISSING_SESSION_ID,
    BRIDGE_REASON_MISSING_TOKEN_MINT,
    BRIDGE_REASON_NONE,
    BRIDGE_REASON_NON_PRIVATE_WEBHOOK,
    BRIDGE_REASON_READER_REJECTED,
    BRIDGE_REASON_WRITER_REJECTED,
    BRIDGE_STATUS_CAPTURED,
    BRIDGE_STATUS_INDEX_FAILED,
    BRIDGE_STATUS_INVALID_INPUT,
    BRIDGE_STATUS_PROJECT_FAILED,
    BRIDGE_STATUS_PROJECTED,
    BRIDGE_STATUS_READ_FAILED,
    BRIDGE_STATUS_WRITE_FAILED,
    BRIDGE_STATUS_WRITTEN_AND_INDEXED,
    PRIVATE_WEBHOOK_IDENTITY_PRIVATE_OPERATOR,
    SANITIZED_TRANSPORT_STATUS_SENT_OK,
    SANITIZED_TRANSPORT_STATUS_UNKNOWN,
    STAGE30_9_1_BRIDGE_PROOF_SCHEMA_VERSION,
    STAGE30_9_1_BRIDGE_REASON_VALUES,
    STAGE30_9_1_BRIDGE_STATUS_VALUES,
    STAGE30_9_1_MINOR_VERSION,
    STAGE30_9_1_PRIVATE_WEBHOOK_IDENTITIES,
    STAGE30_9_1_SANITIZED_TRANSPORT_STATUS_VALUES,
    STAGE30_9_1_SCENARIO_DEDUPE_KEY_1,
    STAGE30_9_1_SCENARIO_DEDUPE_KEY_2,
    STAGE30_9_1_SCENARIO_DEDUPE_KEY_3,
    STAGE30_9_1_SCENARIO_MISMATCH_SESSION_ID,
    STAGE30_9_1_SCENARIO_SESSION_ID,
    Stage30_9BridgeProofSummary,
    Stage30_9BridgeScenario,
    Stage30_9CaptureRecord,
    Stage30_9DispatchContextRecord,
    Stage30_9ProjectorResult,
    Stage30_9SessionSummaryCounters,
    bridge_proof_summary_field_names,
    bridge_scenario_field_names,
    capture_record_field_names,
    default_bridge_scenario,
    dispatch_context_record_field_names,
    is_bridge_reason,
    is_bridge_status,
    is_private_webhook_identity,
    is_sanitized_transport_status,
    mismatch_bridge_scenario,
    normalize_transport_status,
    projector_result_field_names,
)


# ---------------------------------------------------------------------------
# 1. Version + schema identity
# ---------------------------------------------------------------------------


def test_minor_version_and_schema_pinned() -> None:
    assert STAGE30_9_1_MINOR_VERSION == "30.9.1"
    assert STAGE30_9_1_BRIDGE_PROOF_SCHEMA_VERSION == (
        "stage30_9_v0_compact_artifact_bridge_proof"
    )


# ---------------------------------------------------------------------------
# 2. Closed-set bridge status + reason
# ---------------------------------------------------------------------------


def test_bridge_status_closed_set() -> None:
    assert STAGE30_9_1_BRIDGE_STATUS_VALUES == (
        BRIDGE_STATUS_CAPTURED,
        BRIDGE_STATUS_PROJECTED,
        BRIDGE_STATUS_WRITTEN_AND_INDEXED,
        BRIDGE_STATUS_INVALID_INPUT,
        BRIDGE_STATUS_PROJECT_FAILED,
        BRIDGE_STATUS_WRITE_FAILED,
        BRIDGE_STATUS_READ_FAILED,
        BRIDGE_STATUS_INDEX_FAILED,
    )
    for token in STAGE30_9_1_BRIDGE_STATUS_VALUES:
        assert is_bridge_status(token)
    assert not is_bridge_status("NOPE")
    assert not is_bridge_status(None)
    assert not is_bridge_status(123)


def test_bridge_reason_closed_set() -> None:
    assert STAGE30_9_1_BRIDGE_REASON_VALUES == (
        BRIDGE_REASON_NONE,
        BRIDGE_REASON_MISSING_RUN_ID,
        BRIDGE_REASON_MISSING_SESSION_ID,
        BRIDGE_REASON_MISSING_PING_ID,
        BRIDGE_REASON_MISSING_CANDIDATE_ID,
        BRIDGE_REASON_MISSING_TOKEN_MINT,
        BRIDGE_REASON_MISSING_DEDUPE_KEY,
        BRIDGE_REASON_MISSING_COMPACT_BODY,
        BRIDGE_REASON_MISSING_CAPTURE_INDEX,
        BRIDGE_REASON_COUNT_MISMATCH,
        BRIDGE_REASON_AMBIGUOUS_JOIN,
        BRIDGE_REASON_NON_PRIVATE_WEBHOOK,
        BRIDGE_REASON_WRITER_REJECTED,
        BRIDGE_REASON_READER_REJECTED,
        BRIDGE_REASON_INDEX_REJECTED,
    )
    for token in STAGE30_9_1_BRIDGE_REASON_VALUES:
        assert is_bridge_reason(token)
    assert not is_bridge_reason("NOPE")
    assert not is_bridge_reason(None)


def test_sanitized_transport_status_closed_set_and_normalize() -> None:
    # The closed set carries the recognized live statuses (mirrored from the
    # Stage 28.4 vocabulary BY VALUE) plus the UNKNOWN fallback.
    assert SANITIZED_TRANSPORT_STATUS_SENT_OK == "SENT_OK"
    assert SANITIZED_TRANSPORT_STATUS_UNKNOWN == "UNKNOWN_TRANSPORT_STATUS"
    for token in STAGE30_9_1_SANITIZED_TRANSPORT_STATUS_VALUES:
        assert is_sanitized_transport_status(token)
    assert SANITIZED_TRANSPORT_STATUS_SENT_OK in (
        STAGE30_9_1_SANITIZED_TRANSPORT_STATUS_VALUES
    )
    assert SANITIZED_TRANSPORT_STATUS_UNKNOWN in (
        STAGE30_9_1_SANITIZED_TRANSPORT_STATUS_VALUES
    )

    # A recognized status is preserved verbatim.
    assert normalize_transport_status("SENT_OK") == "SENT_OK"
    assert normalize_transport_status("RATE_LIMITED") == "RATE_LIMITED"
    # An unrecognized / blank / non-string status normalizes to UNKNOWN.
    for bad in ("WEIRD_STATUS", "", "   ", None, 123, object()):
        assert normalize_transport_status(bad) == (
            SANITIZED_TRANSPORT_STATUS_UNKNOWN
        )
    assert not is_sanitized_transport_status("WEIRD_STATUS")
    assert not is_sanitized_transport_status(None)


# ---------------------------------------------------------------------------
# 3. Private webhook identity allowlist
# ---------------------------------------------------------------------------


def test_private_webhook_identity_allowlist() -> None:
    assert STAGE30_9_1_PRIVATE_WEBHOOK_IDENTITIES == (
        PRIVATE_WEBHOOK_IDENTITY_PRIVATE_OPERATOR,
    )
    assert PRIVATE_WEBHOOK_IDENTITY_PRIVATE_OPERATOR == (
        "PRIVATE_OPERATOR_WEBHOOK"
    )
    assert is_private_webhook_identity(
        PRIVATE_WEBHOOK_IDENTITY_PRIVATE_OPERATOR
    )
    # A non-private / unknown / empty / non-string identity is rejected.
    assert not is_private_webhook_identity("SOME_OTHER_IDENTITY")
    assert not is_private_webhook_identity("")
    assert not is_private_webhook_identity(None)
    assert not is_private_webhook_identity(123)


# ---------------------------------------------------------------------------
# 4. Records are frozen / immutable passive carriers
# ---------------------------------------------------------------------------


def test_records_are_frozen() -> None:
    capture = Stage30_9CaptureRecord(
        capture_index=0,
        webhook_identity="PRIVATE_OPERATOR_WEBHOOK",
        payload_body_text="body",
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        capture.capture_index = 9  # type: ignore[misc]

    context = Stage30_9DispatchContextRecord(capture_index=0, dedupe_key="k")
    with pytest.raises(dataclasses.FrozenInstanceError):
        context.dedupe_key = "z"  # type: ignore[misc]

    counters = Stage30_9SessionSummaryCounters()
    with pytest.raises(dataclasses.FrozenInstanceError):
        counters.errors = 1  # type: ignore[misc]


def test_capture_record_defaults() -> None:
    capture = Stage30_9CaptureRecord(
        capture_index=2,
        webhook_identity="PRIVATE_OPERATOR_WEBHOOK",
        payload_body_text="hello",
    )
    assert capture.payload_keys == ()
    assert capture.sanitized_transport_status is None
    assert capture.candidate_id is None
    assert capture.ping_id is None


# ---------------------------------------------------------------------------
# 5. Field-name helpers
# ---------------------------------------------------------------------------


def test_field_name_helpers() -> None:
    assert capture_record_field_names() == (
        "capture_index",
        "webhook_identity",
        "payload_body_text",
        "payload_keys",
        "sanitized_transport_status",
        "candidate_id",
        "ping_id",
    )
    assert dispatch_context_record_field_names() == (
        "capture_index",
        "dedupe_key",
        "candidate_id",
        "ping_id",
        "token_mint",
        "ping_session_id",
        "dedupe_state",
    )
    # The projector result carries a (loosely-typed) bundle slot + counts.
    result_fields = projector_result_field_names()
    assert "bundle" in result_fields
    assert "status" in result_fields and "reason" in result_fields
    # The bridge proof summary carries the index counts + forbidden flags.
    summary_fields = bridge_proof_summary_field_names()
    for name in (
        "status",
        "reason",
        "retained_count",
        "duplicate_suppressed_count",
        "invalid_suppressed_count",
        "single_bundle_write",
        "no_default_storage_root",
        "live_provider_used",
        "discord_send_used",
        "env_read_used",
    ):
        assert name in summary_fields
    scenario_fields = bridge_scenario_field_names()
    for name in (
        "name",
        "run_id",
        "session_id",
        "artifact_created_at_utc",
        "capture_records",
        "dispatch_context_records",
        "expected_retained",
        "expected_duplicate_suppressed",
        "expected_invalid_suppressed",
    ):
        assert name in scenario_fields


# ---------------------------------------------------------------------------
# 6. Deterministic default scenario
# ---------------------------------------------------------------------------


def test_default_scenario_shape_and_determinism() -> None:
    s1 = default_bridge_scenario()
    s2 = default_bridge_scenario()
    assert isinstance(s1, Stage30_9BridgeScenario)
    # No clock / random: two builds are byte-for-byte identical.
    assert s1 == s2

    # Three captured sends; one matching dispatch context per capture.
    assert len(s1.capture_records) == 3
    assert len(s1.dispatch_context_records) == 3
    assert s1.session_id == STAGE30_9_1_SCENARIO_SESSION_ID

    # Two sends share a dedupe key with DIFFERENT ping ids (a duplicate by
    # dedupe key), and a third is unique.
    ctx = s1.dispatch_context_records
    assert ctx[0].dedupe_key == STAGE30_9_1_SCENARIO_DEDUPE_KEY_1
    assert ctx[1].dedupe_key == STAGE30_9_1_SCENARIO_DEDUPE_KEY_1
    assert ctx[2].dedupe_key == STAGE30_9_1_SCENARIO_DEDUPE_KEY_2
    assert ctx[0].ping_id != ctx[1].ping_id

    # Every capture forwards the private operator identity; the join keys
    # line up with the contexts.
    for capture, context in zip(s1.capture_records, ctx):
        assert capture.webhook_identity == "PRIVATE_OPERATOR_WEBHOOK"
        assert capture.capture_index == context.capture_index
        # No divergent session scope in the default scenario.
        assert context.ping_session_id is None

    # Expected oracle: 3 pings / 2 retained / 1 duplicate / 0 invalid.
    assert s1.expected_ping_count == 3
    assert s1.expected_retained == 2
    assert s1.expected_duplicate_suppressed == 1
    assert s1.expected_invalid_suppressed == 0


# ---------------------------------------------------------------------------
# 7. Deterministic mismatch scenario
# ---------------------------------------------------------------------------


def test_mismatch_scenario_shape_and_determinism() -> None:
    s1 = mismatch_bridge_scenario()
    s2 = mismatch_bridge_scenario()
    assert s1 == s2

    # Four captured sends; the fourth context records a session scope that
    # diverges from the bundle (config) session id -> the post-run index
    # suppresses that ping as SESSION_ID_MISMATCH.
    assert len(s1.capture_records) == 4
    assert len(s1.dispatch_context_records) == 4
    assert s1.session_id == STAGE30_9_1_SCENARIO_SESSION_ID

    fourth = s1.dispatch_context_records[3]
    assert fourth.dedupe_key == STAGE30_9_1_SCENARIO_DEDUPE_KEY_3
    assert fourth.ping_session_id == STAGE30_9_1_SCENARIO_MISMATCH_SESSION_ID
    assert fourth.ping_session_id != s1.session_id

    # Expected oracle: 4 pings / 2 retained / 1 duplicate / 1 invalid.
    assert s1.expected_ping_count == 4
    assert s1.expected_retained == 2
    assert s1.expected_duplicate_suppressed == 1
    assert s1.expected_invalid_suppressed == 1


def test_scenarios_are_distinct() -> None:
    assert default_bridge_scenario().name != mismatch_bridge_scenario().name


def test_projector_result_and_summary_construct() -> None:
    # The passive result / summary records construct from plain scalars
    # (they validate nothing at construction).
    result = Stage30_9ProjectorResult(
        status=BRIDGE_STATUS_PROJECTED,
        reason=BRIDGE_REASON_NONE,
        blocked_field=None,
        bundle=object(),
        ping_artifact_count=3,
        dispatch_attempt_count=3,
        error_artifact_count=1,
    )
    assert result.status == BRIDGE_STATUS_PROJECTED
    summary = Stage30_9BridgeProofSummary(
        status=BRIDGE_STATUS_WRITTEN_AND_INDEXED,
        reason=BRIDGE_REASON_NONE,
        bridge_proof_schema_version=STAGE30_9_1_BRIDGE_PROOF_SCHEMA_VERSION,
        scenario_name="x",
        proof_session_id="s",
        capture_record_count=3,
        ping_artifacts_projected=3,
        dispatch_attempts_projected=3,
        error_artifacts_projected=1,
        bundles_written_count=1,
        bundles_read_count=1,
        ping_artifacts_seen=3,
        retained_count=2,
        duplicate_suppressed_count=1,
        invalid_suppressed_count=0,
        capture_transport_used=True,
        projector_used=True,
        writer_used=True,
        reader_used=True,
        index_builder_used=True,
        live_provider_used=False,
        discord_send_used=False,
        env_read_used=False,
        db_used=False,
        zstd_used=False,
        single_bundle_write=True,
        no_default_storage_root=True,
        dedupe_key_from_dispatch_context=True,
    )
    assert summary.status == BRIDGE_STATUS_WRITTEN_AND_INDEXED

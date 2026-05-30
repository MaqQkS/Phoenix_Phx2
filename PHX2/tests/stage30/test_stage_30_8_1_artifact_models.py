"""Stage 30.8.1 compact artifact model tests.

Pure offline unit tests for the Stage 30.8.1 closed-set vocabularies and
the passive, frozen compact artifact records. No live calls, no env
reads, no filesystem writes, no actual-disk reads.

Pinned contract:

  * minor version + artifact stage id / schema version constants,
  * the artifact-kind / validation-status / storage-budget-status
    closed sets + their predicates,
  * the redaction substitution tokens,
  * construction of a valid identity / content snapshot (with MC / LP /
    Net / ATH / Mig) / every artifact kind / a validation result,
  * the records are frozen + passive (no writer methods),
  * the field-name helpers.
"""

from __future__ import annotations

import dataclasses

import pytest

from PHX2.stage30.stage30_8_artifact_models import (
    ARTIFACT_KIND_COMPACT_DISPATCH_ATTEMPT_ARTIFACT,
    ARTIFACT_KIND_COMPACT_ERROR_ARTIFACT,
    ARTIFACT_KIND_COMPACT_PING_ARTIFACT,
    ARTIFACT_KIND_COMPACT_SESSION_SUMMARY,
    ARTIFACT_KIND_COMPACT_STORAGE_BUDGET_SNAPSHOT,
    STAGE30_8_1_MINOR_VERSION,
    STAGE30_8_ARTIFACT_KINDS,
    STAGE30_8_ARTIFACT_SCHEMA_VERSION,
    STAGE30_8_ARTIFACT_STAGE_ID,
    STAGE30_8_REDACTION_SUBSTITUTION_TOKENS,
    STAGE30_8_STORAGE_BUDGET_STATUS_VALUES,
    STAGE30_8_VALIDATION_STATUS_VALUES,
    STORAGE_BUDGET_STATUS_OK,
    Stage30_8CompactArtifactIdentity,
    Stage30_8CompactContentSnapshot,
    Stage30_8CompactDispatchAttemptArtifact,
    Stage30_8CompactErrorArtifact,
    Stage30_8CompactPingArtifact,
    Stage30_8CompactSessionSummaryArtifact,
    Stage30_8CompactStorageBudgetSnapshotArtifact,
    Stage30_8ValidationResult,
    content_snapshot_field_names,
    identity_field_names,
    is_artifact_kind,
    is_storage_budget_status,
    is_validation_status,
    validation_result_field_names,
)


# ---------------------------------------------------------------------------
# Builders (valid records)
# ---------------------------------------------------------------------------


def _identity(**overrides: object) -> Stage30_8CompactArtifactIdentity:
    kwargs = dict(
        run_id="run-001",
        session_id="sess-001",
        ping_id="ping-001",
        candidate_id="cand-001",
        token_mint="So11111111111111111111111111111111111111112",
        provider_event_id="evt-001",
        normalized_event_id="norm-001",
        observed_at_utc="2026-05-29T00:00:00Z",
        artifact_created_at_utc="2026-05-29T00:00:01Z",
        artifact_kind=ARTIFACT_KIND_COMPACT_PING_ARTIFACT,
        dedupe_key="dedupe-abc",
        compact_ping_schema_version="stage30_2_v0_compact_ping",
    )
    kwargs.update(overrides)
    return Stage30_8CompactArtifactIdentity(**kwargs)  # type: ignore[arg-type]


def _content(**overrides: object) -> Stage30_8CompactContentSnapshot:
    kwargs = dict(
        compact_body_text="PHOENIX compact body | MC: $83k | ATH: $120k",
        mc_display="$83k",
        lp_display="$12k",
        net_display="+$4k buys",
        ath_display="$120k",
        migration_display="Known",
        decision_status="ELIGIBLE",
        eligibility_status="ELIGIBLE",
        warning_codes=("PRICE_DEGRADED_NONE",),
        reason_codes=("TIER_3_IN_BAND",),
        terminal_outcome_code="DISPATCHED",
        sanitized_transport_status="OK_200",
    )
    kwargs.update(overrides)
    return Stage30_8CompactContentSnapshot(**kwargs)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# 1. Version + schema identity constants
# ---------------------------------------------------------------------------


def test_minor_version_pinned() -> None:
    assert STAGE30_8_1_MINOR_VERSION == "30.8.1"


def test_artifact_stage_id_and_schema_version_pinned() -> None:
    assert STAGE30_8_ARTIFACT_STAGE_ID == "stage30_8"
    assert STAGE30_8_ARTIFACT_SCHEMA_VERSION == (
        "stage30_8_v0_compact_artifact"
    )


# ---------------------------------------------------------------------------
# 2. Closed sets + predicates
# ---------------------------------------------------------------------------


def test_artifact_kinds_closed_set_pinned() -> None:
    assert STAGE30_8_ARTIFACT_KINDS == (
        "compact_session_summary",
        "compact_ping_artifact",
        "compact_dispatch_attempt_artifact",
        "compact_error_artifact",
        "compact_storage_budget_snapshot",
    )
    for kind in STAGE30_8_ARTIFACT_KINDS:
        assert is_artifact_kind(kind)
    assert not is_artifact_kind("nope")
    assert not is_artifact_kind(None)
    assert not is_artifact_kind(1)


def test_validation_status_closed_set_pinned() -> None:
    assert STAGE30_8_VALIDATION_STATUS_VALUES == ("VALID", "INVALID")
    for token in STAGE30_8_VALIDATION_STATUS_VALUES:
        assert is_validation_status(token)
    assert not is_validation_status("MAYBE")
    assert not is_validation_status(None)


def test_storage_budget_status_closed_set_pinned() -> None:
    assert STAGE30_8_STORAGE_BUDGET_STATUS_VALUES == (
        "OK",
        "SOFT_ALARM",
        "HARD_STOP",
        "INVALID_INPUT",
    )
    for token in STAGE30_8_STORAGE_BUDGET_STATUS_VALUES:
        assert is_storage_budget_status(token)
    assert not is_storage_budget_status("STORAGE_BUDGET_OK")
    assert not is_storage_budget_status(None)


def test_redaction_tokens_pinned() -> None:
    assert STAGE30_8_REDACTION_SUBSTITUTION_TOKENS == (
        "SAFE",
        "REDACTED",
        "Unknown",
    )


def test_closed_sets_have_no_duplicates() -> None:
    for values in (
        STAGE30_8_ARTIFACT_KINDS,
        STAGE30_8_VALIDATION_STATUS_VALUES,
        STAGE30_8_STORAGE_BUDGET_STATUS_VALUES,
        STAGE30_8_REDACTION_SUBSTITUTION_TOKENS,
    ):
        assert len(values) == len(set(values))


# ---------------------------------------------------------------------------
# 3. Construct valid identity
# ---------------------------------------------------------------------------


def test_construct_valid_identity() -> None:
    identity = _identity()
    assert identity.stage_id == "stage30_8"
    assert identity.artifact_schema_version == (
        "stage30_8_v0_compact_artifact"
    )
    assert identity.artifact_kind == "compact_ping_artifact"
    assert identity.run_id == "run-001"
    assert identity.session_id == "sess-001"
    assert identity.ping_id == "ping-001"
    assert identity.dedupe_key == "dedupe-abc"


def test_identity_defaults_stage_id_and_schema_version() -> None:
    bare = Stage30_8CompactArtifactIdentity()
    assert bare.stage_id == STAGE30_8_ARTIFACT_STAGE_ID
    assert bare.artifact_schema_version == (
        STAGE30_8_ARTIFACT_SCHEMA_VERSION
    )
    assert bare.run_id is None
    assert bare.artifact_kind is None


# ---------------------------------------------------------------------------
# 4. Construct valid content snapshot (MC / LP / Net / ATH / Mig)
# ---------------------------------------------------------------------------


def test_construct_valid_content_snapshot_with_display_fields() -> None:
    content = _content()
    assert content.mc_display == "$83k"
    assert content.lp_display == "$12k"
    assert content.net_display == "+$4k buys"
    assert content.ath_display == "$120k"
    assert content.migration_display == "Known"
    assert content.warning_codes == ("PRICE_DEGRADED_NONE",)
    assert content.reason_codes == ("TIER_3_IN_BAND",)
    assert isinstance(content.compact_body_text, str)


def test_content_snapshot_defaults_are_safe() -> None:
    bare = Stage30_8CompactContentSnapshot()
    assert bare.compact_body_text is None
    assert bare.mc_display is None
    assert bare.warning_codes == ()
    assert bare.reason_codes == ()


# ---------------------------------------------------------------------------
# 5. Construct every artifact kind
# ---------------------------------------------------------------------------


def test_construct_ping_artifact() -> None:
    artifact = Stage30_8CompactPingArtifact(
        identity=_identity(
            artifact_kind=ARTIFACT_KIND_COMPACT_PING_ARTIFACT
        ),
        content=_content(),
    )
    assert artifact.identity is not None
    assert artifact.content is not None
    assert artifact.identity.artifact_kind == "compact_ping_artifact"


def test_construct_session_summary_artifact() -> None:
    artifact = Stage30_8CompactSessionSummaryArtifact(
        identity=_identity(
            artifact_kind=ARTIFACT_KIND_COMPACT_SESSION_SUMMARY,
            ping_id=None,
        ),
        pings_emitted=3,
        dispatch_attempts=4,
        dedupe_suppressed=1,
        errors=0,
        storage_budget=Stage30_8CompactStorageBudgetSnapshotArtifact(
            identity=_identity(
                artifact_kind=(
                    ARTIFACT_KIND_COMPACT_STORAGE_BUDGET_SNAPSHOT
                ),
                ping_id=None,
            ),
            budget_status=STORAGE_BUDGET_STATUS_OK,
        ),
    )
    assert artifact.pings_emitted == 3
    assert artifact.storage_budget is not None
    assert artifact.storage_budget.budget_status == "OK"


def test_construct_dispatch_attempt_artifact() -> None:
    artifact = Stage30_8CompactDispatchAttemptArtifact(
        identity=_identity(
            artifact_kind=(
                ARTIFACT_KIND_COMPACT_DISPATCH_ATTEMPT_ARTIFACT
            )
        ),
        sanitized_transport_status="OK_200",
        attempt_index=0,
    )
    assert artifact.sanitized_transport_status == "OK_200"
    assert artifact.attempt_index == 0


def test_construct_error_artifact() -> None:
    artifact = Stage30_8CompactErrorArtifact(
        identity=_identity(
            artifact_kind=ARTIFACT_KIND_COMPACT_ERROR_ARTIFACT
        ),
        error_reason_code="ADAPTER_CALLER_SHAPE_ERROR",
    )
    assert artifact.error_reason_code == "ADAPTER_CALLER_SHAPE_ERROR"


def test_construct_storage_budget_snapshot_artifact() -> None:
    artifact = Stage30_8CompactStorageBudgetSnapshotArtifact(
        identity=_identity(
            artifact_kind=(
                ARTIFACT_KIND_COMPACT_STORAGE_BUDGET_SNAPSHOT
            ),
            ping_id=None,
        ),
        budget_status="SOFT_ALARM",
        raw_bytes_written=1024,
        durable_rows_written=12,
        archived_compressed_bytes=256,
        dropped_count=0,
        pruned_count=0,
        sealed_count=2,
        dedupe_suppressed_count=1,
        disk_usage_percent_before=64.0,
        disk_usage_percent_after=66.0,
    )
    assert artifact.budget_status == "SOFT_ALARM"
    assert artifact.raw_bytes_written == 1024
    assert artifact.disk_usage_percent_after == 66.0


def test_construct_validation_result() -> None:
    result = Stage30_8ValidationResult(
        status="VALID",
        reason="OK",
        blocked_field=None,
        safe_to_persist=True,
    )
    assert result.status == "VALID"
    assert result.safe_to_persist is True
    assert result.blocked_field is None


# ---------------------------------------------------------------------------
# 6. Records are frozen
# ---------------------------------------------------------------------------


def test_identity_is_frozen() -> None:
    identity = _identity()
    with pytest.raises(dataclasses.FrozenInstanceError):
        identity.stage_id = "x"  # type: ignore[misc]


def test_content_snapshot_is_frozen() -> None:
    content = _content()
    with pytest.raises(dataclasses.FrozenInstanceError):
        content.mc_display = "y"  # type: ignore[misc]


def test_artifacts_are_frozen() -> None:
    ping = Stage30_8CompactPingArtifact(
        identity=_identity(), content=_content()
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        ping.content = None  # type: ignore[misc]
    result = Stage30_8ValidationResult(
        status="VALID",
        reason="OK",
        blocked_field=None,
        safe_to_persist=True,
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.safe_to_persist = False  # type: ignore[misc]


# ---------------------------------------------------------------------------
# 7. Records are passive (no writer / I/O methods)
# ---------------------------------------------------------------------------


_FORBIDDEN_RECORD_METHODS = (
    "to_file",
    "from_file",
    "write",
    "writelines",
    "save",
    "persist",
    "flush",
    "append",
    "append_jsonl",
    "dump",
    "dumps",
    "open",
    "read",
    "load",
)


_RECORD_CLASSES = (
    Stage30_8CompactArtifactIdentity,
    Stage30_8CompactContentSnapshot,
    Stage30_8CompactPingArtifact,
    Stage30_8CompactSessionSummaryArtifact,
    Stage30_8CompactDispatchAttemptArtifact,
    Stage30_8CompactErrorArtifact,
    Stage30_8CompactStorageBudgetSnapshotArtifact,
    Stage30_8ValidationResult,
)


def test_records_have_no_writer_or_io_methods() -> None:
    for cls in _RECORD_CLASSES:
        for method_name in _FORBIDDEN_RECORD_METHODS:
            assert not hasattr(cls, method_name), (
                f"Stage 30.8.1 record {cls.__name__!r} must expose no "
                f"writer / I/O method; found {method_name!r}"
            )


def test_records_are_dataclasses() -> None:
    for cls in _RECORD_CLASSES:
        assert dataclasses.is_dataclass(cls)
        params = getattr(cls, "__dataclass_params__", None)
        assert params is not None and params.frozen is True, (
            f"Stage 30.8.1 record {cls.__name__!r} must be a frozen "
            f"dataclass"
        )


# ---------------------------------------------------------------------------
# 8. Field-name helpers
# ---------------------------------------------------------------------------


def test_identity_field_names() -> None:
    assert identity_field_names() == (
        "stage_id",
        "run_id",
        "session_id",
        "ping_id",
        "candidate_id",
        "token_mint",
        "provider_event_id",
        "normalized_event_id",
        "observed_at_utc",
        "artifact_created_at_utc",
        "artifact_schema_version",
        "artifact_kind",
        "dedupe_key",
        "compact_ping_schema_version",
    )


def test_content_snapshot_field_names() -> None:
    assert content_snapshot_field_names() == (
        "compact_body_text",
        "mc_display",
        "lp_display",
        "net_display",
        "ath_display",
        "migration_display",
        "decision_status",
        "eligibility_status",
        "warning_codes",
        "reason_codes",
        "terminal_outcome_code",
        "sanitized_transport_status",
    )


def test_validation_result_field_names() -> None:
    assert validation_result_field_names() == (
        "status",
        "reason",
        "blocked_field",
        "safe_to_persist",
    )

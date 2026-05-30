"""Stage 30.8.1 compact artifact validator tests.

Pure offline unit tests for the Stage 30.8.1 validator layer. No live
calls, no env reads, no filesystem writes, no actual-disk reads.

Pinned contract:

  * a valid compact ping artifact validates to VALID / safe_to_persist,
  * missing required identity / wrong schema version / wrong stage id /
    unsupported artifact kind / kind mismatch all fail closed,
  * an empty compact body for a ping fails closed,
  * a forbidden field NAME / forbidden value pattern / URL-or-credential
    string / nested raw dict-or-list payload all fail closed,
  * the closed-set safe placeholders are allowed,
  * the validators never raise on malformed input / ``None``,
  * the per-kind validators accept their valid records and fail closed
    on bad counters / percents / statuses / codes.

Forbidden-pattern probe strings are built with split-literal
concatenation so this test's own source carries none of the bare
transport / inbound-hook / API-credential needles.
"""

from __future__ import annotations

import types

from PHX2.stage30.stage30_8_artifact_models import (
    ARTIFACT_KIND_COMPACT_DISPATCH_ATTEMPT_ARTIFACT,
    ARTIFACT_KIND_COMPACT_ERROR_ARTIFACT,
    ARTIFACT_KIND_COMPACT_PING_ARTIFACT,
    ARTIFACT_KIND_COMPACT_SESSION_SUMMARY,
    ARTIFACT_KIND_COMPACT_STORAGE_BUDGET_SNAPSHOT,
    STAGE30_8_ARTIFACT_SCHEMA_VERSION,
    STAGE30_8_ARTIFACT_STAGE_ID,
    VALIDATION_STATUS_INVALID,
    VALIDATION_STATUS_VALID,
    Stage30_8CompactArtifactIdentity,
    Stage30_8CompactContentSnapshot,
    Stage30_8CompactDispatchAttemptArtifact,
    Stage30_8CompactErrorArtifact,
    Stage30_8CompactPingArtifact,
    Stage30_8CompactSessionSummaryArtifact,
    Stage30_8CompactStorageBudgetSnapshotArtifact,
)
from PHX2.stage30.stage30_8_artifact_validators import (
    VALIDATION_REASON_ARTIFACT_KIND_INVALID,
    VALIDATION_REASON_ARTIFACT_KIND_MISMATCH,
    VALIDATION_REASON_BUDGET_STATUS_INVALID,
    VALIDATION_REASON_CODES_NOT_STRING_SEQUENCE,
    VALIDATION_REASON_COUNTER_INVALID,
    VALIDATION_REASON_DISPLAY_FIELD_NOT_STRING,
    VALIDATION_REASON_EMPTY_COMPACT_BODY,
    VALIDATION_REASON_ERROR_REASON_CODE_INVALID,
    VALIDATION_REASON_FORBIDDEN_FIELD_NAME,
    VALIDATION_REASON_FORBIDDEN_VALUE_PATTERN,
    VALIDATION_REASON_INVALID_INPUT_TYPE,
    VALIDATION_REASON_MISSING_REQUIRED_IDENTITY,
    VALIDATION_REASON_NESTED_RAW_PAYLOAD,
    VALIDATION_REASON_OK,
    VALIDATION_REASON_PERCENT_INVALID,
    VALIDATION_REASON_SCHEMA_VERSION_INVALID,
    VALIDATION_REASON_STAGE_ID_INVALID,
    VALIDATION_REASON_TRANSPORT_STATUS_INVALID,
    is_forbidden_field_name,
    validate_compact_artifact_identity,
    validate_compact_content_snapshot,
    validate_compact_dispatch_attempt_artifact,
    validate_compact_error_artifact,
    validate_compact_ping_artifact,
    validate_compact_session_summary_artifact,
    validate_compact_storage_budget_snapshot_artifact,
    value_has_forbidden_pattern,
)


# A transport-URL-like probe string assembled from split literals so the
# bare needle never appears in this test's source text.
_URLISH = "open " + "h" + "ttps://" + "host/path"


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
        compact_body_text="PHOENIX compact | MC: $83k | ATH: $120k",
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


def _ping(**overrides: object) -> Stage30_8CompactPingArtifact:
    identity = overrides.pop(
        "identity",
        _identity(artifact_kind=ARTIFACT_KIND_COMPACT_PING_ARTIFACT),
    )
    content = overrides.pop("content", _content())
    return Stage30_8CompactPingArtifact(
        identity=identity, content=content  # type: ignore[arg-type]
    )


# ---------------------------------------------------------------------------
# 1. Valid ping artifact -> VALID / safe_to_persist
# ---------------------------------------------------------------------------


def test_valid_ping_artifact_is_valid_and_safe_to_persist() -> None:
    result = validate_compact_ping_artifact(_ping())
    assert result.status == VALIDATION_STATUS_VALID
    assert result.reason == VALIDATION_REASON_OK
    assert result.blocked_field is None
    assert result.safe_to_persist is True


def test_valid_identity_is_valid() -> None:
    result = validate_compact_artifact_identity(_identity())
    assert result.status == VALIDATION_STATUS_VALID
    assert result.safe_to_persist is True


# ---------------------------------------------------------------------------
# 2. Missing required identity / wrong schema / stage id / kind
# ---------------------------------------------------------------------------


def test_missing_required_identity_is_invalid() -> None:
    result = validate_compact_artifact_identity(_identity(run_id=""))
    assert result.status == VALIDATION_STATUS_INVALID
    assert result.reason == VALIDATION_REASON_MISSING_REQUIRED_IDENTITY
    assert result.blocked_field == "run_id"
    assert result.safe_to_persist is False


def test_missing_created_at_is_invalid() -> None:
    result = validate_compact_artifact_identity(
        _identity(artifact_created_at_utc=None)
    )
    assert result.status == VALIDATION_STATUS_INVALID
    assert result.reason == VALIDATION_REASON_MISSING_REQUIRED_IDENTITY
    assert result.blocked_field == "artifact_created_at_utc"


def test_present_optional_identity_must_be_nonempty() -> None:
    result = validate_compact_artifact_identity(_identity(token_mint=""))
    assert result.status == VALIDATION_STATUS_INVALID
    assert result.blocked_field == "token_mint"


def test_wrong_schema_version_is_invalid() -> None:
    result = validate_compact_artifact_identity(
        _identity(artifact_schema_version="bogus_v9")
    )
    assert result.status == VALIDATION_STATUS_INVALID
    assert result.reason == VALIDATION_REASON_SCHEMA_VERSION_INVALID
    assert result.blocked_field == "artifact_schema_version"


def test_wrong_stage_id_is_invalid() -> None:
    # The artifact stage id is the underscore form ``stage30_8``; the
    # dotted family id ``30.8`` must NOT validate.
    result = validate_compact_artifact_identity(_identity(stage_id="30.8"))
    assert result.status == VALIDATION_STATUS_INVALID
    assert result.reason == VALIDATION_REASON_STAGE_ID_INVALID
    assert result.blocked_field == "stage_id"


def test_unsupported_artifact_kind_is_invalid() -> None:
    result = validate_compact_artifact_identity(
        _identity(artifact_kind="totally_made_up_kind")
    )
    assert result.status == VALIDATION_STATUS_INVALID
    assert result.reason == VALIDATION_REASON_ARTIFACT_KIND_INVALID
    assert result.blocked_field == "artifact_kind"


def test_kind_mismatch_is_invalid() -> None:
    # A valid session-summary-kind identity handed to the ping validator
    # is a kind mismatch.
    artifact = Stage30_8CompactPingArtifact(
        identity=_identity(
            artifact_kind=ARTIFACT_KIND_COMPACT_SESSION_SUMMARY
        ),
        content=_content(),
    )
    result = validate_compact_ping_artifact(artifact)
    assert result.status == VALIDATION_STATUS_INVALID
    assert result.reason == VALIDATION_REASON_ARTIFACT_KIND_MISMATCH
    assert result.blocked_field == "artifact_kind"


def test_ping_requires_session_ping_dedupe_axes() -> None:
    for axis in ("session_id", "ping_id", "dedupe_key"):
        artifact = _ping(
            identity=_identity(
                artifact_kind=ARTIFACT_KIND_COMPACT_PING_ARTIFACT,
                **{axis: None},
            )
        )
        result = validate_compact_ping_artifact(artifact)
        assert result.status == VALIDATION_STATUS_INVALID
        assert result.reason == (
            VALIDATION_REASON_MISSING_REQUIRED_IDENTITY
        )
        assert result.blocked_field == axis


# ---------------------------------------------------------------------------
# 3. Empty compact body for ping
# ---------------------------------------------------------------------------


def test_empty_compact_body_for_ping_is_invalid() -> None:
    for bad_body in ("", None):
        artifact = _ping(content=_content(compact_body_text=bad_body))
        result = validate_compact_ping_artifact(artifact)
        assert result.status == VALIDATION_STATUS_INVALID
        assert result.reason == VALIDATION_REASON_EMPTY_COMPACT_BODY
        assert result.blocked_field == "compact_body_text"


# ---------------------------------------------------------------------------
# 4. Forbidden field name
# ---------------------------------------------------------------------------


def test_forbidden_field_name_is_invalid() -> None:
    # A future-refactor identity-like object carrying a credential-class
    # field name fails closed.
    forbidden_name = "web" + "hook"
    payload = dict(
        stage_id=STAGE30_8_ARTIFACT_STAGE_ID,
        run_id="run-1",
        session_id="s",
        ping_id="p",
        artifact_created_at_utc="t",
        artifact_schema_version=STAGE30_8_ARTIFACT_SCHEMA_VERSION,
        artifact_kind=ARTIFACT_KIND_COMPACT_PING_ARTIFACT,
        dedupe_key="d",
    )
    payload[forbidden_name] = "anything"
    namespace = types.SimpleNamespace(**payload)
    result = validate_compact_artifact_identity(namespace)
    assert result.status == VALIDATION_STATUS_INVALID
    assert result.reason == VALIDATION_REASON_FORBIDDEN_FIELD_NAME
    assert result.blocked_field == forbidden_name


def test_is_forbidden_field_name_helper() -> None:
    assert is_forbidden_field_name("web" + "hook")
    assert is_forbidden_field_name("api_" + "key")
    assert is_forbidden_field_name("author" + "ization")
    assert is_forbidden_field_name("private_key")
    assert is_forbidden_field_name("raw_provider_payload")
    assert is_forbidden_field_name("url")
    assert is_forbidden_field_name("binary")
    assert not is_forbidden_field_name("mc_display")
    assert not is_forbidden_field_name("dedupe_key")
    assert not is_forbidden_field_name("raw_bytes_written")
    assert not is_forbidden_field_name("provider_event_id")
    assert not is_forbidden_field_name(None)
    assert not is_forbidden_field_name(123)


# ---------------------------------------------------------------------------
# 5. Forbidden value pattern / URL-or-credential string
# ---------------------------------------------------------------------------


def test_forbidden_value_pattern_is_invalid() -> None:
    result = validate_compact_content_snapshot(
        _content(mc_display=_URLISH)
    )
    assert result.status == VALIDATION_STATUS_INVALID
    assert result.reason == VALIDATION_REASON_FORBIDDEN_VALUE_PATTERN
    assert result.blocked_field == "mc_display"


def test_forbidden_value_pattern_in_body_is_invalid() -> None:
    artifact = _ping(content=_content(compact_body_text=_URLISH))
    result = validate_compact_ping_artifact(artifact)
    assert result.status == VALIDATION_STATUS_INVALID
    assert result.reason == VALIDATION_REASON_FORBIDDEN_VALUE_PATTERN
    assert result.blocked_field == "compact_body_text"


def test_forbidden_value_pattern_in_codes_is_invalid() -> None:
    bad_code = "/web" + "hooks/" + "abc"
    result = validate_compact_content_snapshot(
        _content(reason_codes=(bad_code,))
    )
    assert result.status == VALIDATION_STATUS_INVALID
    assert result.reason == VALIDATION_REASON_FORBIDDEN_VALUE_PATTERN
    assert result.blocked_field == "reason_codes"


def test_value_has_forbidden_pattern_helper() -> None:
    assert value_has_forbidden_pattern(_URLISH)
    assert value_has_forbidden_pattern("x " + "b" + "earer abc")
    assert value_has_forbidden_pattern("y " + "api_" + "key=z")
    assert not value_has_forbidden_pattern("$83k")
    assert not value_has_forbidden_pattern("Unknown")
    assert not value_has_forbidden_pattern("2026-05-29T00:00:00Z")
    assert not value_has_forbidden_pattern(None)
    assert not value_has_forbidden_pattern(123)


# ---------------------------------------------------------------------------
# 6. Nested raw dict / list payload
# ---------------------------------------------------------------------------


def test_nested_raw_dict_payload_is_invalid() -> None:
    result = validate_compact_content_snapshot(
        _content(mc_display={"raw": 1})
    )
    assert result.status == VALIDATION_STATUS_INVALID
    assert result.reason == VALIDATION_REASON_NESTED_RAW_PAYLOAD
    assert result.blocked_field == "mc_display"


def test_nested_raw_list_in_non_codes_field_is_invalid() -> None:
    result = validate_compact_content_snapshot(
        _content(lp_display=["a", "b"])
    )
    assert result.status == VALIDATION_STATUS_INVALID
    assert result.reason == VALIDATION_REASON_NESTED_RAW_PAYLOAD
    assert result.blocked_field == "lp_display"


# ---------------------------------------------------------------------------
# 7. Closed-set safe placeholders allowed
# ---------------------------------------------------------------------------


def test_placeholders_are_allowed() -> None:
    content = _content(
        mc_display="Unknown",
        lp_display="REDACTED",
        net_display="SAFE",
        ath_display="Unknown",
        migration_display="Unknown",
        decision_status="Unknown",
        eligibility_status="Unknown",
        warning_codes=("SAFE",),
        reason_codes=("REDACTED",),
        terminal_outcome_code="Unknown",
        sanitized_transport_status="Unknown",
    )
    result = validate_compact_content_snapshot(content)
    assert result.status == VALIDATION_STATUS_VALID

    ping = _ping(content=_content(compact_body_text="SAFE"))
    assert (
        validate_compact_ping_artifact(ping).status
        == VALIDATION_STATUS_VALID
    )


# ---------------------------------------------------------------------------
# 8. Display field must be string / codes must be string sequence
# ---------------------------------------------------------------------------


def test_display_field_not_string_is_invalid() -> None:
    result = validate_compact_content_snapshot(_content(mc_display=123))
    assert result.status == VALIDATION_STATUS_INVALID
    assert result.reason == VALIDATION_REASON_DISPLAY_FIELD_NOT_STRING
    assert result.blocked_field == "mc_display"


def test_codes_with_non_string_element_is_invalid() -> None:
    result = validate_compact_content_snapshot(
        _content(warning_codes=(1, 2))
    )
    assert result.status == VALIDATION_STATUS_INVALID
    assert result.reason == VALIDATION_REASON_CODES_NOT_STRING_SEQUENCE
    assert result.blocked_field == "warning_codes"


def test_codes_as_bare_string_is_invalid() -> None:
    result = validate_compact_content_snapshot(
        _content(reason_codes="not-a-sequence")
    )
    assert result.status == VALIDATION_STATUS_INVALID
    assert result.reason == VALIDATION_REASON_CODES_NOT_STRING_SEQUENCE
    assert result.blocked_field == "reason_codes"


def test_codes_as_list_of_strings_is_valid() -> None:
    result = validate_compact_content_snapshot(
        _content(warning_codes=["A_CODE", "B_CODE"])
    )
    assert result.status == VALIDATION_STATUS_VALID


# ---------------------------------------------------------------------------
# 9. Per-kind valid records
# ---------------------------------------------------------------------------


def _budget(**overrides: object) -> (
    Stage30_8CompactStorageBudgetSnapshotArtifact
):
    kwargs = dict(
        identity=_identity(
            artifact_kind=ARTIFACT_KIND_COMPACT_STORAGE_BUDGET_SNAPSHOT,
            ping_id=None,
        ),
        budget_status="OK",
        raw_bytes_written=1024,
        durable_rows_written=10,
        archived_compressed_bytes=128,
        dropped_count=0,
        pruned_count=0,
        sealed_count=1,
        dedupe_suppressed_count=2,
        disk_usage_percent_before=40.0,
        disk_usage_percent_after=41.0,
    )
    kwargs.update(overrides)
    return Stage30_8CompactStorageBudgetSnapshotArtifact(
        **kwargs  # type: ignore[arg-type]
    )


def test_valid_session_summary_artifact() -> None:
    artifact = Stage30_8CompactSessionSummaryArtifact(
        identity=_identity(
            artifact_kind=ARTIFACT_KIND_COMPACT_SESSION_SUMMARY,
            ping_id=None,
        ),
        pings_emitted=3,
        dispatch_attempts=4,
        dedupe_suppressed=1,
        errors=0,
        storage_budget=_budget(),
    )
    result = validate_compact_session_summary_artifact(artifact)
    assert result.status == VALIDATION_STATUS_VALID


def test_valid_dispatch_attempt_artifact() -> None:
    artifact = Stage30_8CompactDispatchAttemptArtifact(
        identity=_identity(
            artifact_kind=(
                ARTIFACT_KIND_COMPACT_DISPATCH_ATTEMPT_ARTIFACT
            )
        ),
        sanitized_transport_status="OK_200",
        attempt_index=0,
    )
    result = validate_compact_dispatch_attempt_artifact(artifact)
    assert result.status == VALIDATION_STATUS_VALID


def test_valid_error_artifact() -> None:
    artifact = Stage30_8CompactErrorArtifact(
        identity=_identity(
            artifact_kind=ARTIFACT_KIND_COMPACT_ERROR_ARTIFACT
        ),
        error_reason_code="ADAPTER_CALLER_SHAPE_ERROR",
    )
    result = validate_compact_error_artifact(artifact)
    assert result.status == VALIDATION_STATUS_VALID


def test_valid_storage_budget_snapshot_artifact() -> None:
    result = validate_compact_storage_budget_snapshot_artifact(_budget())
    assert result.status == VALIDATION_STATUS_VALID


# ---------------------------------------------------------------------------
# 10. Per-kind fail-closed cases
# ---------------------------------------------------------------------------


def test_invalid_budget_status_is_invalid() -> None:
    for bad in ("BOGUS", None, "STORAGE_BUDGET_OK"):
        result = validate_compact_storage_budget_snapshot_artifact(
            _budget(budget_status=bad)
        )
        assert result.status == VALIDATION_STATUS_INVALID
        assert result.reason == VALIDATION_REASON_BUDGET_STATUS_INVALID
        assert result.blocked_field == "budget_status"


def test_negative_counter_is_invalid() -> None:
    result = validate_compact_storage_budget_snapshot_artifact(
        _budget(raw_bytes_written=-5)
    )
    assert result.status == VALIDATION_STATUS_INVALID
    assert result.reason == VALIDATION_REASON_COUNTER_INVALID
    assert result.blocked_field == "raw_bytes_written"


def test_bool_counter_is_invalid() -> None:
    artifact = Stage30_8CompactSessionSummaryArtifact(
        identity=_identity(
            artifact_kind=ARTIFACT_KIND_COMPACT_SESSION_SUMMARY,
            ping_id=None,
        ),
        pings_emitted=True,
    )
    result = validate_compact_session_summary_artifact(artifact)
    assert result.status == VALIDATION_STATUS_INVALID
    assert result.reason == VALIDATION_REASON_COUNTER_INVALID
    assert result.blocked_field == "pings_emitted"


def test_out_of_range_percent_is_invalid() -> None:
    for bad in (150.0, -1.0, float("nan"), float("inf")):
        result = validate_compact_storage_budget_snapshot_artifact(
            _budget(disk_usage_percent_before=bad)
        )
        assert result.status == VALIDATION_STATUS_INVALID
        assert result.reason == VALIDATION_REASON_PERCENT_INVALID
        assert result.blocked_field == "disk_usage_percent_before"


def test_missing_transport_status_is_invalid() -> None:
    for bad in ("", None):
        artifact = Stage30_8CompactDispatchAttemptArtifact(
            identity=_identity(
                artifact_kind=(
                    ARTIFACT_KIND_COMPACT_DISPATCH_ATTEMPT_ARTIFACT
                )
            ),
            sanitized_transport_status=bad,
        )
        result = validate_compact_dispatch_attempt_artifact(artifact)
        assert result.status == VALIDATION_STATUS_INVALID
        assert result.reason == (
            VALIDATION_REASON_TRANSPORT_STATUS_INVALID
        )
        assert result.blocked_field == "sanitized_transport_status"


def test_missing_error_reason_code_is_invalid() -> None:
    artifact = Stage30_8CompactErrorArtifact(
        identity=_identity(
            artifact_kind=ARTIFACT_KIND_COMPACT_ERROR_ARTIFACT
        ),
        error_reason_code=None,
    )
    result = validate_compact_error_artifact(artifact)
    assert result.status == VALIDATION_STATUS_INVALID
    assert result.reason == VALIDATION_REASON_ERROR_REASON_CODE_INVALID
    assert result.blocked_field == "error_reason_code"


# ---------------------------------------------------------------------------
# 11. Validators never raise on malformed / None input
# ---------------------------------------------------------------------------
#
# Every validator is total (never raises) AND fails closed: a malformed
# / ``None`` / non-record input returns INVALID / safe_to_persist=False.
# The content snapshot validator runs a fail-closed shape gate first, so
# a non-snapshot-like input (a scalar, string, sequence, or dict) is
# rejected with INVALID_INPUT_TYPE rather than passing as VALID.


_MALFORMED_INPUTS = (
    None,
    object(),
    123,
    "a string",
    types.SimpleNamespace(),
    types.SimpleNamespace(stage_id=42),
    {"stage_id": "stage30_8"},
    [1, 2, 3],
)


_STRICT_VALIDATORS = (
    validate_compact_artifact_identity,
    validate_compact_ping_artifact,
    validate_compact_session_summary_artifact,
    validate_compact_dispatch_attempt_artifact,
    validate_compact_error_artifact,
    validate_compact_storage_budget_snapshot_artifact,
)


def test_strict_validators_fail_closed_on_malformed_input() -> None:
    for validator in _STRICT_VALIDATORS:
        for candidate in _MALFORMED_INPUTS:
            result = validator(candidate)
            assert result.status == VALIDATION_STATUS_INVALID, (
                f"{validator.__name__} on {candidate!r} must fail closed"
            )
            assert result.safe_to_persist is False


def test_content_validator_fails_closed_on_malformed_input() -> None:
    # Codex-named probes: each must fail closed (INVALID /
    # safe_to_persist=False), never pass as VALID. A bare dict (even one
    # carrying a content-like key) is NOT an accepted snapshot input.
    malformed = (
        None,
        object(),
        123,
        "a string",
        [1, 2, 3],
        {},
        {"mc_display": 123},
    )
    for candidate in malformed:
        result = validate_compact_content_snapshot(candidate)
        assert result.status == VALIDATION_STATUS_INVALID, (
            f"content snapshot validator on {candidate!r} must fail "
            f"closed"
        )
        assert result.safe_to_persist is False
        assert result.reason == VALIDATION_REASON_INVALID_INPUT_TYPE


def test_valid_content_snapshot_remains_valid() -> None:
    # Positive control: a proper snapshot with safe display strings
    # still validates VALID / safe_to_persist=True.
    result = validate_compact_content_snapshot(_content())
    assert result.status == VALIDATION_STATUS_VALID
    assert result.safe_to_persist is True


def test_validators_are_deterministic() -> None:
    ping = _ping()
    first = validate_compact_ping_artifact(ping)
    second = validate_compact_ping_artifact(ping)
    assert first == second

"""Stage 28.5 health-status models tests.

Pins:

  * Closed-set vocabularies (provider / price / dispatch / ledger /
    transport / artifact / health / stop reason / last-event /
    last-ping / retry-budget / redaction) accept the locked tokens
    and reject anything else.
  * Counter validation rejects negative values, ``bool``, ``float``
    (incl. NaN / inf), and non-int objects.
  * Safe-identifier allowlist accepts safe shapes and rejects URL /
    bearer / webhook / secret-shaped values.
  * Record builders construct frozen NamedTuples that round-trip
    via ``*_record_to_dict`` and that carry only safe field values.
  * ``repr()`` / ``str()`` of every record never carries a canary
    secret value supplied by an upstream caller (the caller-
    supplied unsafe value is redacted at build time and never
    reaches the record).
  * Stop reason is closed-set; schema versions are locked.
"""

from __future__ import annotations

import math
from typing import Any

import pytest

from PHX2.stage28.health_status_models import (
    ARTIFACT_STATUS_OK,
    ARTIFACT_STATUS_VALUES,
    CLI_STATUS_LINE_MODEL_FIELD_NAMES,
    COUNTER_FIELD_NAMES,
    DISPATCH_STATUS_OK,
    DISPATCH_STATUS_VALUES,
    FINAL_SUMMARY_RECORD_FIELD_NAMES,
    FINAL_SUMMARY_TOTAL_FIELD_NAMES,
    HEALTH_SNAPSHOT_RECORD_FIELD_NAMES,
    HEALTH_STATUS_HEALTHY,
    HEALTH_STATUS_VALUES,
    HEARTBEAT_RECORD_FIELD_NAMES,
    LAST_EVENT_STATUS_NONE_OBSERVED,
    LAST_EVENT_STATUS_VALUES,
    LAST_PING_STATUS_NONE_RENDERED,
    LAST_PING_STATUS_VALUES,
    LEDGER_STATUS_OK,
    LEDGER_STATUS_VALUES,
    PRICE_STATUS_OK,
    PRICE_STATUS_VALUES,
    PROVIDER_STATUS_OK,
    PROVIDER_STATUS_VALUES,
    REDACTION_STATUS_REDACTED,
    REDACTION_STATUS_SAFE,
    REDACTION_STATUS_VALUES,
    RETRY_BUDGET_STATUS_OK,
    RETRY_BUDGET_STATUS_VALUES,
    SAFE_RUN_ID_MISSING,
    SAFE_RUN_ID_REDACTED,
    SAFE_SESSION_ID_REDACTED,
    STAGE28_5_CLI_STATUS_SCHEMA_VERSION,
    STAGE28_5_FINAL_SUMMARY_SCHEMA_VERSION,
    STAGE28_5_HEALTH_SNAPSHOT_SCHEMA_VERSION,
    STAGE28_5_HEARTBEAT_SCHEMA_VERSION,
    STAGE28_5_MINOR_VERSION,
    STAGE28_5_REDACTION_TOKEN,
    STOP_REASON_NOT_STOPPED,
    STOP_REASON_VALUES,
    Stage28_5CliStatusLineModel,
    Stage28_5FinalRunSummaryRecord,
    Stage28_5HealthSnapshotRecord,
    Stage28_5HealthStatusError,
    Stage28_5HealthStatusValidationError,
    Stage28_5HeartbeatRecord,
    TRANSPORT_STATUS_OK,
    TRANSPORT_STATUS_VALUES,
    build_cli_status_line_model,
    build_final_run_summary_record,
    build_health_snapshot_record,
    build_heartbeat_record,
    cli_status_line_model_to_dict,
    final_run_summary_record_to_dict,
    health_snapshot_record_to_dict,
    heartbeat_record_to_dict,
    is_artifact_status_value,
    is_dispatch_status_value,
    is_health_status_value,
    is_last_event_status_value,
    is_last_ping_status_value,
    is_ledger_status_value,
    is_price_status_value,
    is_provider_status_value,
    is_redaction_status_value,
    is_retry_budget_status_value,
    is_safe_counter_value,
    is_safe_identifier,
    is_stop_reason_value,
    is_transport_status_value,
)


# Canary secret values supplied by upstream callers. The Stage
# 28.5 record builders must redact these into safe placeholder
# constants; the canary string must NEVER appear in any record
# field, asdict projection, repr, or str.
CANARY_WEBHOOK_URL: str = "h" + "ttps://discord" + ".com/api/webhooks/123/abc"
CANARY_BEARER: str = "B" + "earer secret_token_xyz"
CANARY_API_KEY: str = "s" + "k-supersecretapikey1234"


# Locked Stage 28.5 schema versions; the tests assert these
# verbatim so a future schema bump is loud.
LOCKED_HEARTBEAT_SCHEMA_VERSION: str = "stage28_5_heartbeat_v0"
LOCKED_HEALTH_SNAPSHOT_SCHEMA_VERSION: str = (
    "stage28_5_health_snapshot_v0"
)
LOCKED_FINAL_SUMMARY_SCHEMA_VERSION: str = (
    "stage28_5_final_run_summary_v0"
)
LOCKED_CLI_STATUS_SCHEMA_VERSION: str = "stage28_5_cli_status_v0"


# ---------------------------------------------------------------------------
# Locked version axes
# ---------------------------------------------------------------------------


def test_minor_version_is_28_5():
    assert STAGE28_5_MINOR_VERSION == "28.5"


def test_heartbeat_schema_version_is_locked():
    assert (
        STAGE28_5_HEARTBEAT_SCHEMA_VERSION
        == LOCKED_HEARTBEAT_SCHEMA_VERSION
    )


def test_health_snapshot_schema_version_is_locked():
    assert (
        STAGE28_5_HEALTH_SNAPSHOT_SCHEMA_VERSION
        == LOCKED_HEALTH_SNAPSHOT_SCHEMA_VERSION
    )


def test_final_summary_schema_version_is_locked():
    assert (
        STAGE28_5_FINAL_SUMMARY_SCHEMA_VERSION
        == LOCKED_FINAL_SUMMARY_SCHEMA_VERSION
    )


def test_cli_status_schema_version_is_locked():
    assert (
        STAGE28_5_CLI_STATUS_SCHEMA_VERSION
        == LOCKED_CLI_STATUS_SCHEMA_VERSION
    )


def test_redaction_token_is_distinct():
    assert STAGE28_5_REDACTION_TOKEN == "<<STAGE28_5_REDACTED>>"


# ---------------------------------------------------------------------------
# Closed-set vocabularies
# ---------------------------------------------------------------------------


def test_provider_status_values_closed_set():
    assert set(PROVIDER_STATUS_VALUES) == {
        "OK",
        "DISCONNECTED",
        "RECONNECTING",
        "LOST",
        "NOT_STARTED",
        "UNKNOWN",
    }
    for value in PROVIDER_STATUS_VALUES:
        assert is_provider_status_value(value)
    assert not is_provider_status_value("HEALTHY")
    assert not is_provider_status_value(None)
    assert not is_provider_status_value(0)


def test_price_status_values_closed_set():
    assert set(PRICE_STATUS_VALUES) == {
        "OK",
        "STALE",
        "MISSING",
        "TIMEOUT",
        "NOT_STARTED",
        "UNKNOWN",
    }
    for value in PRICE_STATUS_VALUES:
        assert is_price_status_value(value)
    assert not is_price_status_value("DEGRADED")


def test_dispatch_status_values_closed_set():
    assert set(DISPATCH_STATUS_VALUES) == {
        "OK",
        "FAILED",
        "SUPPRESSED",
        "AMBIGUOUS",
        "NOT_STARTED",
        "UNKNOWN",
    }
    for value in DISPATCH_STATUS_VALUES:
        assert is_dispatch_status_value(value)
    assert not is_dispatch_status_value("SENT_OK")


def test_ledger_status_values_closed_set():
    assert set(LEDGER_STATUS_VALUES) == {
        "OK",
        "WRITE_FAILED",
        "REPLAY_FAILED",
        "AMBIGUOUS",
        "DUPLICATE_SUPPRESSED",
        "NOT_STARTED",
        "UNKNOWN",
    }
    for value in LEDGER_STATUS_VALUES:
        assert is_ledger_status_value(value)
    assert not is_ledger_status_value("RESERVED")


def test_transport_status_values_closed_set():
    assert set(TRANSPORT_STATUS_VALUES) == {
        "OK",
        "RATE_LIMITED",
        "SERVER_ERROR",
        "NETWORK_ERROR",
        "REFUSED",
        "NOT_STARTED",
        "UNKNOWN",
    }
    for value in TRANSPORT_STATUS_VALUES:
        assert is_transport_status_value(value)
    assert not is_transport_status_value("SENT_OK")


def test_artifact_status_values_closed_set():
    assert set(ARTIFACT_STATUS_VALUES) == {
        "OK",
        "WRITE_FAILED",
        "READ_FAILED",
        "NOT_STARTED",
        "UNKNOWN",
    }
    for value in ARTIFACT_STATUS_VALUES:
        assert is_artifact_status_value(value)
    assert not is_artifact_status_value("HEALTHY")


def test_health_status_values_closed_set():
    assert set(HEALTH_STATUS_VALUES) == {
        "HEALTHY",
        "DEGRADED",
        "FAILED",
        "STOPPED",
        "UNKNOWN",
    }
    for value in HEALTH_STATUS_VALUES:
        assert is_health_status_value(value)
    assert not is_health_status_value("OK")


def test_stop_reason_values_closed_set():
    assert set(STOP_REASON_VALUES) == {
        "MAX_EVENTS",
        "MAX_WALL_SECONDS",
        "SIGINT",
        "SIGTERM",
        "PROVIDER_LOST",
        "RETRY_BUDGET_EXHAUSTED",
        "OPERATOR_STOP",
        "ERROR",
        "NOT_STOPPED",
    }
    for value in STOP_REASON_VALUES:
        assert is_stop_reason_value(value)
    assert not is_stop_reason_value("DONE")


def test_last_event_status_values_closed_set():
    assert set(LAST_EVENT_STATUS_VALUES) == {
        "OBSERVED",
        "NONE_OBSERVED",
        "NOT_STARTED",
        "UNKNOWN",
    }
    for value in LAST_EVENT_STATUS_VALUES:
        assert is_last_event_status_value(value)
    assert not is_last_event_status_value("OK")


def test_last_ping_status_values_closed_set():
    assert set(LAST_PING_STATUS_VALUES) == {
        "RENDERED",
        "SUPPRESSED",
        "NONE_RENDERED",
        "NOT_STARTED",
        "UNKNOWN",
    }
    for value in LAST_PING_STATUS_VALUES:
        assert is_last_ping_status_value(value)
    assert not is_last_ping_status_value("OK")


def test_retry_budget_status_values_closed_set():
    assert set(RETRY_BUDGET_STATUS_VALUES) == {
        "OK",
        "NEAR_LIMIT",
        "EXHAUSTED",
        "NOT_STARTED",
        "UNKNOWN",
    }
    for value in RETRY_BUDGET_STATUS_VALUES:
        assert is_retry_budget_status_value(value)
    assert not is_retry_budget_status_value("HEALTHY")


def test_redaction_status_values_closed_set():
    assert set(REDACTION_STATUS_VALUES) == {
        "SAFE",
        "REDACTED",
        "NO_SECRET_MATERIAL",
    }
    for value in REDACTION_STATUS_VALUES:
        assert is_redaction_status_value(value)
    assert not is_redaction_status_value("OK")


# ---------------------------------------------------------------------------
# Safe-identifier validation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "value",
    [
        "run_123",
        "session-abc",
        "ABC123",
        "a",
        "z" * 64,
    ],
)
def test_safe_identifier_accepts_valid_shapes(value: str):
    assert is_safe_identifier(value)


@pytest.mark.parametrize(
    "value",
    [
        "",
        None,
        123,
        " ",
        "-leading_dash",
        "trailing_dash-",
        "has spaces",
        "with.dot",
        "with/slash",
        "with\\slash",
        "z" * 65,
        CANARY_WEBHOOK_URL,
        CANARY_BEARER,
        CANARY_API_KEY,
        "auth=secret",
        "token=abc",
        "discord" + ".com",
    ],
)
def test_safe_identifier_rejects_unsafe(value: Any):
    assert not is_safe_identifier(value)


# ---------------------------------------------------------------------------
# Counter validation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("value", [0, 1, 100, 999_999])
def test_counter_validation_accepts_nonneg_ints(value: int):
    assert is_safe_counter_value(value)


@pytest.mark.parametrize(
    "value",
    [
        -1,
        -100,
        True,
        False,
        0.0,
        1.5,
        math.nan,
        math.inf,
        -math.inf,
        "0",
        None,
        [0],
        {0: 0},
    ],
)
def test_counter_validation_rejects_unsafe(value: Any):
    assert not is_safe_counter_value(value)


# ---------------------------------------------------------------------------
# Counter / field-name inventories
# ---------------------------------------------------------------------------


def test_counter_field_names_locked():
    assert COUNTER_FIELD_NAMES == (
        "event_count",
        "candidate_count",
        "ping_rendered_count",
        "dispatch_success_count",
        "dispatch_failure_count",
        "retry_count",
        "duplicate_suppressed_count",
        "ambiguous_suppressed_count",
        "unknown_pair_suppressed_count",
        "disagree_pair_suppressed_count",
        "usdc_observe_only_count",
        "stale_price_count",
        "missing_price_count",
        "malformed_event_count",
    )


def test_final_summary_total_field_names_locked():
    assert FINAL_SUMMARY_TOTAL_FIELD_NAMES == (
        "total_events_seen",
        "total_candidates",
        "total_pings_rendered",
        "total_dispatch_success",
        "total_dispatch_failure",
        "total_retry_attempts",
        "total_duplicates_suppressed",
        "total_ambiguous_suppressed",
        "total_unknown_pair_suppressed",
        "total_disagree_pair_suppressed",
        "total_usdc_observe_only",
        "total_stale_price",
        "total_missing_price",
        "total_malformed_events",
    )


# ---------------------------------------------------------------------------
# Heartbeat record builder + projection
# ---------------------------------------------------------------------------


def _all_zero_counters_kwargs() -> dict[str, int]:
    return {
        "event_count": 0,
        "candidate_count": 0,
        "ping_rendered_count": 0,
        "dispatch_success_count": 0,
        "dispatch_failure_count": 0,
        "retry_count": 0,
        "duplicate_suppressed_count": 0,
        "ambiguous_suppressed_count": 0,
        "unknown_pair_suppressed_count": 0,
        "disagree_pair_suppressed_count": 0,
        "usdc_observe_only_count": 0,
        "stale_price_count": 0,
        "missing_price_count": 0,
        "malformed_event_count": 0,
    }


def _good_heartbeat_kwargs(**overrides: Any) -> dict[str, Any]:
    kwargs: dict[str, Any] = dict(
        run_id="run_abc",
        session_id="sess_001",
        heartbeat_index=0,
        provider_status=PROVIDER_STATUS_OK,
        price_status=PRICE_STATUS_OK,
        dispatch_status=DISPATCH_STATUS_OK,
        ledger_status=LEDGER_STATUS_OK,
        transport_status=TRANSPORT_STATUS_OK,
        artifact_status=ARTIFACT_STATUS_OK,
        stop_reason=None,
        **_all_zero_counters_kwargs(),
    )
    kwargs.update(overrides)
    return kwargs


def test_heartbeat_record_happy_path():
    record = build_heartbeat_record(**_good_heartbeat_kwargs())
    assert isinstance(record, Stage28_5HeartbeatRecord)
    assert record.schema_version == LOCKED_HEARTBEAT_SCHEMA_VERSION
    assert record.run_id == "run_abc"
    assert record.session_id == "sess_001"
    assert record.heartbeat_index == 0
    assert record.provider_status == PROVIDER_STATUS_OK
    assert record.stop_reason is None
    assert record.redaction_status == REDACTION_STATUS_SAFE


def test_heartbeat_record_redacts_unsafe_run_id():
    record = build_heartbeat_record(
        **_good_heartbeat_kwargs(run_id=CANARY_WEBHOOK_URL)
    )
    assert record.run_id == SAFE_RUN_ID_REDACTED
    assert CANARY_WEBHOOK_URL not in repr(record)
    assert CANARY_WEBHOOK_URL not in str(record)
    assert record.redaction_status == REDACTION_STATUS_REDACTED


def test_heartbeat_record_redacts_unsafe_session_id():
    record = build_heartbeat_record(
        **_good_heartbeat_kwargs(session_id=CANARY_BEARER)
    )
    assert record.session_id == SAFE_SESSION_ID_REDACTED
    assert CANARY_BEARER not in repr(record)
    assert CANARY_BEARER not in str(record)
    assert record.redaction_status == REDACTION_STATUS_REDACTED


def test_heartbeat_record_missing_run_id_uses_missing_placeholder():
    record = build_heartbeat_record(
        **_good_heartbeat_kwargs(run_id=None)
    )
    assert record.run_id == SAFE_RUN_ID_MISSING
    assert record.redaction_status == REDACTION_STATUS_REDACTED


@pytest.mark.parametrize(
    "field_name,bad_value",
    [
        ("event_count", -1),
        ("candidate_count", 1.5),
        ("ping_rendered_count", True),
        ("dispatch_success_count", "1"),
        ("malformed_event_count", math.nan),
    ],
)
def test_heartbeat_record_rejects_bad_counter(field_name: str, bad_value: Any):
    kwargs = _good_heartbeat_kwargs(**{field_name: bad_value})
    with pytest.raises(Stage28_5HealthStatusValidationError) as exc:
        build_heartbeat_record(**kwargs)
    assert exc.value.field_name == field_name


def test_heartbeat_record_rejects_bad_provider_status():
    kwargs = _good_heartbeat_kwargs(provider_status="HEALTHY")
    with pytest.raises(Stage28_5HealthStatusValidationError) as exc:
        build_heartbeat_record(**kwargs)
    assert exc.value.field_name == "provider_status"


def test_heartbeat_record_rejects_bad_stop_reason():
    kwargs = _good_heartbeat_kwargs(stop_reason="DONE")
    with pytest.raises(Stage28_5HealthStatusValidationError) as exc:
        build_heartbeat_record(**kwargs)
    assert exc.value.field_name == "stop_reason"


def test_heartbeat_record_accepts_known_stop_reason():
    kwargs = _good_heartbeat_kwargs(stop_reason=STOP_REASON_NOT_STOPPED)
    record = build_heartbeat_record(**kwargs)
    assert record.stop_reason == STOP_REASON_NOT_STOPPED


def test_heartbeat_record_is_immutable():
    record = build_heartbeat_record(**_good_heartbeat_kwargs())
    with pytest.raises(AttributeError):
        record.event_count = 99  # type: ignore[misc]


def test_heartbeat_record_to_dict_field_order_locked():
    record = build_heartbeat_record(**_good_heartbeat_kwargs())
    d = heartbeat_record_to_dict(record)
    assert tuple(d.keys()) == HEARTBEAT_RECORD_FIELD_NAMES


def test_heartbeat_record_to_dict_carries_no_canary_secret():
    record = build_heartbeat_record(
        **_good_heartbeat_kwargs(run_id=CANARY_WEBHOOK_URL)
    )
    d = heartbeat_record_to_dict(record)
    serialized = repr(d)
    assert CANARY_WEBHOOK_URL not in serialized


def test_heartbeat_record_repr_does_not_leak_canary():
    record = build_heartbeat_record(
        **_good_heartbeat_kwargs(
            run_id=CANARY_WEBHOOK_URL,
            session_id=CANARY_API_KEY,
        )
    )
    assert CANARY_WEBHOOK_URL not in repr(record)
    assert CANARY_API_KEY not in repr(record)
    assert CANARY_WEBHOOK_URL not in str(record)
    assert CANARY_API_KEY not in str(record)


# ---------------------------------------------------------------------------
# Health snapshot record builder + projection
# ---------------------------------------------------------------------------


def _good_health_snapshot_kwargs(**overrides: Any) -> dict[str, Any]:
    kwargs: dict[str, Any] = dict(
        run_id="run_abc",
        session_id="sess_001",
        provider_status=PROVIDER_STATUS_OK,
        price_status=PRICE_STATUS_OK,
        dispatch_status=DISPATCH_STATUS_OK,
        ledger_status=LEDGER_STATUS_OK,
        transport_status=TRANSPORT_STATUS_OK,
        artifact_status=ARTIFACT_STATUS_OK,
        last_event_status=LAST_EVENT_STATUS_NONE_OBSERVED,
        last_ping_status=LAST_PING_STATUS_NONE_RENDERED,
        retry_budget_status=RETRY_BUDGET_STATUS_OK,
        current_health_status=HEALTH_STATUS_HEALTHY,
        **_all_zero_counters_kwargs(),
    )
    kwargs.update(overrides)
    return kwargs


def test_health_snapshot_record_happy_path():
    record = build_health_snapshot_record(
        **_good_health_snapshot_kwargs()
    )
    assert isinstance(record, Stage28_5HealthSnapshotRecord)
    assert (
        record.schema_version
        == LOCKED_HEALTH_SNAPSHOT_SCHEMA_VERSION
    )
    assert record.current_health_status == HEALTH_STATUS_HEALTHY
    assert record.redaction_status == REDACTION_STATUS_SAFE


def test_health_snapshot_record_rejects_bad_health_status():
    kwargs = _good_health_snapshot_kwargs(
        current_health_status="OK"
    )
    with pytest.raises(Stage28_5HealthStatusValidationError) as exc:
        build_health_snapshot_record(**kwargs)
    assert exc.value.field_name == "current_health_status"


def test_health_snapshot_record_rejects_bad_last_event_status():
    kwargs = _good_health_snapshot_kwargs(
        last_event_status="OK"
    )
    with pytest.raises(Stage28_5HealthStatusValidationError) as exc:
        build_health_snapshot_record(**kwargs)
    assert exc.value.field_name == "last_event_status"


def test_health_snapshot_record_is_immutable():
    record = build_health_snapshot_record(
        **_good_health_snapshot_kwargs()
    )
    with pytest.raises(AttributeError):
        record.event_count = 99  # type: ignore[misc]


def test_health_snapshot_record_to_dict_field_order_locked():
    record = build_health_snapshot_record(
        **_good_health_snapshot_kwargs()
    )
    d = health_snapshot_record_to_dict(record)
    assert tuple(d.keys()) == HEALTH_SNAPSHOT_RECORD_FIELD_NAMES


def test_health_snapshot_record_redacts_unsafe_run_id():
    record = build_health_snapshot_record(
        **_good_health_snapshot_kwargs(run_id=CANARY_WEBHOOK_URL)
    )
    assert record.run_id == SAFE_RUN_ID_REDACTED
    assert CANARY_WEBHOOK_URL not in repr(record)


# ---------------------------------------------------------------------------
# Final-run-summary record builder + projection
# ---------------------------------------------------------------------------


def _all_zero_totals_kwargs() -> dict[str, int]:
    return {name: 0 for name in FINAL_SUMMARY_TOTAL_FIELD_NAMES}


def _good_final_summary_kwargs(**overrides: Any) -> dict[str, Any]:
    kwargs: dict[str, Any] = dict(
        run_id="run_abc",
        session_id="sess_001",
        stop_reason=STOP_REASON_NOT_STOPPED,
        final_provider_status=PROVIDER_STATUS_OK,
        final_price_status=PRICE_STATUS_OK,
        final_dispatch_status=DISPATCH_STATUS_OK,
        final_ledger_status=LEDGER_STATUS_OK,
        final_transport_status=TRANSPORT_STATUS_OK,
        final_artifact_status=ARTIFACT_STATUS_OK,
        **_all_zero_totals_kwargs(),
    )
    kwargs.update(overrides)
    return kwargs


def test_final_summary_record_happy_path():
    record = build_final_run_summary_record(
        **_good_final_summary_kwargs()
    )
    assert isinstance(record, Stage28_5FinalRunSummaryRecord)
    assert (
        record.schema_version
        == LOCKED_FINAL_SUMMARY_SCHEMA_VERSION
    )
    assert record.stop_reason == STOP_REASON_NOT_STOPPED
    assert record.redaction_status == REDACTION_STATUS_SAFE


def test_final_summary_record_requires_stop_reason():
    kwargs = _good_final_summary_kwargs()
    kwargs["stop_reason"] = "DONE"
    with pytest.raises(Stage28_5HealthStatusValidationError) as exc:
        build_final_run_summary_record(**kwargs)
    assert exc.value.field_name == "stop_reason"


def test_final_summary_record_rejects_bad_total():
    kwargs = _good_final_summary_kwargs(total_events_seen=-1)
    with pytest.raises(Stage28_5HealthStatusValidationError) as exc:
        build_final_run_summary_record(**kwargs)
    assert exc.value.field_name == "total_events_seen"


def test_final_summary_record_is_immutable():
    record = build_final_run_summary_record(
        **_good_final_summary_kwargs()
    )
    with pytest.raises(AttributeError):
        record.total_events_seen = 99  # type: ignore[misc]


def test_final_summary_record_to_dict_field_order_locked():
    record = build_final_run_summary_record(
        **_good_final_summary_kwargs()
    )
    d = final_run_summary_record_to_dict(record)
    assert tuple(d.keys()) == FINAL_SUMMARY_RECORD_FIELD_NAMES


def test_final_summary_record_repr_does_not_leak_canary():
    record = build_final_run_summary_record(
        **_good_final_summary_kwargs(run_id=CANARY_BEARER)
    )
    assert CANARY_BEARER not in repr(record)
    assert CANARY_BEARER not in str(record)


# ---------------------------------------------------------------------------
# CLI status-line model builder + projection
# ---------------------------------------------------------------------------


def _good_cli_status_kwargs(**overrides: Any) -> dict[str, Any]:
    kwargs: dict[str, Any] = dict(
        run_id="run_abc",
        session_id="sess_001",
        health_status=HEALTH_STATUS_HEALTHY,
        provider_status=PROVIDER_STATUS_OK,
        price_status=PRICE_STATUS_OK,
        dispatch_status=DISPATCH_STATUS_OK,
        ledger_status=LEDGER_STATUS_OK,
        transport_status=TRANSPORT_STATUS_OK,
        artifact_status=ARTIFACT_STATUS_OK,
        event_count=0,
        ping_rendered_count=0,
        dispatch_success_count=0,
        dispatch_failure_count=0,
        retry_count=0,
        duplicate_suppressed_count=0,
        ambiguous_suppressed_count=0,
        unknown_pair_suppressed_count=0,
        disagree_pair_suppressed_count=0,
        usdc_observe_only_count=0,
        stale_price_count=0,
        missing_price_count=0,
        malformed_event_count=0,
        stop_reason=STOP_REASON_NOT_STOPPED,
    )
    kwargs.update(overrides)
    return kwargs


def test_cli_status_model_happy_path():
    model = build_cli_status_line_model(**_good_cli_status_kwargs())
    assert isinstance(model, Stage28_5CliStatusLineModel)
    assert (
        model.schema_version
        == LOCKED_CLI_STATUS_SCHEMA_VERSION
    )
    assert model.health_status == HEALTH_STATUS_HEALTHY
    assert model.redaction_status == REDACTION_STATUS_SAFE


def test_cli_status_model_is_immutable():
    model = build_cli_status_line_model(**_good_cli_status_kwargs())
    with pytest.raises(AttributeError):
        model.event_count = 99  # type: ignore[misc]


def test_cli_status_model_to_dict_field_order_locked():
    model = build_cli_status_line_model(**_good_cli_status_kwargs())
    d = cli_status_line_model_to_dict(model)
    assert tuple(d.keys()) == CLI_STATUS_LINE_MODEL_FIELD_NAMES


def test_cli_status_model_redacts_unsafe_run_id():
    model = build_cli_status_line_model(
        **_good_cli_status_kwargs(run_id=CANARY_API_KEY)
    )
    assert model.run_id == SAFE_RUN_ID_REDACTED
    assert CANARY_API_KEY not in repr(model)
    assert CANARY_API_KEY not in str(model)


def test_cli_status_model_rejects_bad_health_status():
    kwargs = _good_cli_status_kwargs(health_status="OK")
    with pytest.raises(Stage28_5HealthStatusValidationError) as exc:
        build_cli_status_line_model(**kwargs)
    assert exc.value.field_name == "health_status"


# ---------------------------------------------------------------------------
# Exception hierarchy
# ---------------------------------------------------------------------------


def test_validation_error_is_subclass_of_health_status_error():
    assert issubclass(
        Stage28_5HealthStatusValidationError,
        Stage28_5HealthStatusError,
    )


def test_validation_error_carries_field_and_reason():
    err = Stage28_5HealthStatusValidationError(
        field_name="event_count", reason="COUNTER_NOT_NONNEG_INT"
    )
    assert err.field_name == "event_count"
    assert err.reason == "COUNTER_NOT_NONNEG_INT"
    assert "event_count" in str(err)
    assert "COUNTER_NOT_NONNEG_INT" in str(err)


def test_validation_error_str_does_not_leak_canary_when_passed_safe_args():
    # Validation errors never carry the raw rejected value; the
    # caller passes only the closed-set field name + reason. So
    # a canary string supplied as a record-build value can never
    # reach the error's str / repr.
    try:
        build_heartbeat_record(
            **_good_heartbeat_kwargs(event_count=CANARY_BEARER)
        )
    except Stage28_5HealthStatusValidationError as err:
        assert CANARY_BEARER not in str(err)
        assert CANARY_BEARER not in repr(err)
    else:
        pytest.fail("expected Stage28_5HealthStatusValidationError")

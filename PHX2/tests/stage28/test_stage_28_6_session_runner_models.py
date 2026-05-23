"""Stage 28.6 session-runner models tests.

Pins:

  * Version axes / redaction-token shape.
  * Closed-set vocabularies (pair status / price status / stop
    reason / health status / redaction status).
  * Candidate-event construction rejects unsafe / forbidden /
    secret-like inputs.
  * Runner-config construction rejects non-positive / non-int
    bounded controls.
  * Run-summary construction rejects negative counters and
    non-closed-set stop-reason / health-status tokens.
  * Repr / str / asdict of every Stage 28.6 record is safe to log
    / print / persist (no URL, webhook, API-key, bearer, or raw
    exception substring leaks).
  * The Stage 28.6 fake transport never sends real HTTP and never
    reads the process environment.
  * The Stage 28.6 stop signal carries only locked stop-reason
    tokens.
  * The Stage 28.6 deterministic tick clock is bounded and
    monotonic.
"""

from __future__ import annotations

import pytest

from PHX2.stage28.audited_http_transport_models import (
    Stage28_4TransportResult,
    TRANSPORT_STATUS_NETWORK_ERROR,
    TRANSPORT_STATUS_RATE_LIMITED,
    TRANSPORT_STATUS_SENT_OK,
    TRANSPORT_STATUS_SERVER_ERROR,
    TRANSPORT_STATUS_VALIDATION_FAILED,
)
from PHX2.stage28.health_status_models import (
    HEALTH_STATUS_HEALTHY,
    HEALTH_STATUS_VALUES,
    REDACTION_STATUS_VALUES as STAGE28_5_REDACTION_STATUS_VALUES,
    STOP_REASON_MAX_EVENTS,
    STOP_REASON_OPERATOR_STOP,
    STOP_REASON_SIGINT,
    STOP_REASON_VALUES,
)
from PHX2.stage28.session_runner_models import (
    CANDIDATE_PAIR_STATUS_DISAGREE,
    CANDIDATE_PAIR_STATUS_OK,
    CANDIDATE_PAIR_STATUS_UNKNOWN,
    CANDIDATE_PAIR_STATUS_USDC_OBSERVE_ONLY,
    CANDIDATE_PAIR_STATUS_VALUES,
    CANDIDATE_PRICE_STATUS_MISSING,
    CANDIDATE_PRICE_STATUS_OK,
    CANDIDATE_PRICE_STATUS_STALE,
    CANDIDATE_PRICE_STATUS_TIMEOUT,
    CANDIDATE_PRICE_STATUS_VALUES,
    STAGE28_6_FINAL_HEALTH_STATUS_VALUES,
    STAGE28_6_FORBIDDEN_PAYLOAD_FIELD_NAMES,
    STAGE28_6_MINOR_VERSION,
    STAGE28_6_REDACTION_STATUS_VALUES,
    STAGE28_6_REDACTION_TOKEN,
    STAGE28_6_RUN_STOP_REASON_VALUES,
    STAGE28_6_RUN_SUMMARY_COUNTER_FIELD_NAMES,
    STAGE28_6_RUN_SUMMARY_FIELD_NAMES,
    STAGE28_6_SCHEMA_VERSION,
    Stage28_6CandidateEvent,
    Stage28_6DeterministicTickClock,
    Stage28_6FakeTransport,
    Stage28_6InvalidCandidateError,
    Stage28_6InvalidRunSummaryError,
    Stage28_6InvalidRunnerConfigError,
    Stage28_6RunSummary,
    Stage28_6RunnerConfig,
    Stage28_6SessionRunnerError,
    Stage28_6StopSignal,
    build_candidate_event,
    build_run_summary,
    build_runner_config,
    is_candidate_pair_status_value,
    is_candidate_price_status_value,
    is_safe_artifact_reference,
    is_safe_candidate_field,
    is_stage28_6_final_health_status_value,
    is_stage28_6_forbidden_payload_field_name,
    is_stage28_6_stop_reason_value,
    run_summary_to_dict,
)


# ---------------------------------------------------------------------------
# Version axes / redaction token
# ---------------------------------------------------------------------------


def test_minor_version_is_28_6():
    assert STAGE28_6_MINOR_VERSION == "28.6"


def test_schema_version_is_locked():
    assert (
        STAGE28_6_SCHEMA_VERSION
        == "stage28_6_bounded_private_session_runner_v0"
    )


def test_redaction_token_is_distinctive():
    assert STAGE28_6_REDACTION_TOKEN == "<<STAGE28_6_REDACTED>>"


# ---------------------------------------------------------------------------
# Closed-set vocabularies
# ---------------------------------------------------------------------------


def test_candidate_pair_status_values_locked():
    assert set(CANDIDATE_PAIR_STATUS_VALUES) == {
        "OK",
        "UNKNOWN",
        "DISAGREE",
        "USDC_OBSERVE_ONLY",
    }


def test_candidate_price_status_values_locked():
    assert set(CANDIDATE_PRICE_STATUS_VALUES) == {
        "OK",
        "STALE",
        "MISSING",
        "TIMEOUT",
    }


def test_run_stop_reason_values_match_stage28_5():
    assert set(STAGE28_6_RUN_STOP_REASON_VALUES) == set(
        STOP_REASON_VALUES
    )


def test_final_health_status_values_match_stage28_5():
    assert set(STAGE28_6_FINAL_HEALTH_STATUS_VALUES) == set(
        HEALTH_STATUS_VALUES
    )


def test_redaction_status_values_match_stage28_5():
    assert set(STAGE28_6_REDACTION_STATUS_VALUES) == set(
        STAGE28_5_REDACTION_STATUS_VALUES
    )


@pytest.mark.parametrize("token", CANDIDATE_PAIR_STATUS_VALUES)
def test_is_candidate_pair_status_value_accepts_locked(token):
    assert is_candidate_pair_status_value(token) is True


def test_is_candidate_pair_status_value_rejects_unknown():
    for bad in ("ok", "", None, 0, "PAIR_OK"):
        assert is_candidate_pair_status_value(bad) is False


@pytest.mark.parametrize("token", CANDIDATE_PRICE_STATUS_VALUES)
def test_is_candidate_price_status_value_accepts_locked(token):
    assert is_candidate_price_status_value(token) is True


def test_is_candidate_price_status_value_rejects_unknown():
    for bad in ("ok", "", None, 0, "PRICE_OK"):
        assert is_candidate_price_status_value(bad) is False


@pytest.mark.parametrize("token", STAGE28_6_RUN_STOP_REASON_VALUES)
def test_is_stop_reason_value_accepts_locked(token):
    assert is_stage28_6_stop_reason_value(token) is True


def test_is_stop_reason_value_rejects_unknown():
    for bad in ("WALL_CLOCK", "", None, 0):
        assert is_stage28_6_stop_reason_value(bad) is False


@pytest.mark.parametrize(
    "token", STAGE28_6_FINAL_HEALTH_STATUS_VALUES
)
def test_is_final_health_status_value_accepts_locked(token):
    assert is_stage28_6_final_health_status_value(token) is True


def test_is_final_health_status_value_rejects_unknown():
    for bad in ("healthy", "", None, 0):
        assert is_stage28_6_final_health_status_value(bad) is False


# ---------------------------------------------------------------------------
# Forbidden payload field-name allowlist
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name", STAGE28_6_FORBIDDEN_PAYLOAD_FIELD_NAMES
)
def test_forbidden_payload_field_name_substring_match(name):
    assert is_stage28_6_forbidden_payload_field_name(name) is True


def test_forbidden_payload_field_name_normalization():
    # Hyphen variants normalize to underscore variants.
    assert (
        is_stage28_6_forbidden_payload_field_name("api-key") is True
    )
    assert (
        is_stage28_6_forbidden_payload_field_name("bearer-token")
        is True
    )
    assert (
        is_stage28_6_forbidden_payload_field_name("My-Subscriber-Id")
        is True
    )


def test_forbidden_payload_field_name_allows_safe_fields():
    for safe in (
        "token_mint",
        "ping_type",
        "event_kind",
        "pair_quote_asset",
        "rendered_text",
        "event_id",
    ):
        assert (
            is_stage28_6_forbidden_payload_field_name(safe) is False
        )


def test_forbidden_payload_field_name_rejects_non_strings():
    for bad in (None, 0, b"api_key", []):
        assert (
            is_stage28_6_forbidden_payload_field_name(bad) is False
        )


# ---------------------------------------------------------------------------
# Safe candidate-field allowlist
# ---------------------------------------------------------------------------


def test_is_safe_candidate_field_accepts_typical_values():
    for safe in (
        "So11111111111111111111111111111111111111112",
        "SOL",
        "tradeable_private_ping",
        "migration",
        "abc-123_xyz",
    ):
        assert is_safe_candidate_field(safe) is True


def test_is_safe_candidate_field_rejects_secret_substrings():
    for bad in (
        "h" + "ttps://example.example",
        "bearer-token",
        "discord" + ".com",
        "/webhooks/foo",
        "s" + "k-aaa",
    ):
        assert is_safe_candidate_field(bad) is False


def test_is_safe_candidate_field_rejects_special_chars():
    for bad in (
        "",
        " ",
        "/foo",
        "foo bar",
        "foo.bar",
        "_foo",
        "foo-",
        "a" * 200,
    ):
        assert is_safe_candidate_field(bad) is False


def test_is_safe_artifact_reference_accepts_basenames():
    for safe in (
        "pre_send.json",
        "candidate-001.json",
        "tradeable_pre_send.v0.json",
    ):
        assert is_safe_artifact_reference(safe) is True


def test_is_safe_artifact_reference_rejects_unsafe():
    for bad in (
        "../pre_send.json",
        "/etc/passwd",
        "h" + "ttps://example.example/pre",
        "bearer.json",
        "",
    ):
        assert is_safe_artifact_reference(bad) is False


# ---------------------------------------------------------------------------
# CandidateEvent construction
# ---------------------------------------------------------------------------


def _safe_candidate_kwargs(**overrides) -> dict:
    base = {
        "event_id": "event_001",
        "token_mint": "So11111111111111111111111111111111111111112",
        "pair_quote_asset": "SOL",
        "event_kind": "migration",
        "ping_type": "tradeable_private_ping",
        "normalized_event_id": "norm_event_001",
        "rendered_payload": {"content": "Pump fun migration ping"},
        "pre_send_artifact_reference": "pre_send_001.json",
        "webhook_identity": "PRIVATE_OPERATOR_WEBHOOK",
        "dispatch_allowed": True,
        "pair_status": CANDIDATE_PAIR_STATUS_OK,
        "price_status": CANDIDATE_PRICE_STATUS_OK,
        "malformed": False,
    }
    base.update(overrides)
    return base


def test_build_candidate_event_returns_named_tuple():
    candidate = build_candidate_event(**_safe_candidate_kwargs())
    assert isinstance(candidate, Stage28_6CandidateEvent)
    assert candidate.event_id == "event_001"
    assert candidate.pair_status == CANDIDATE_PAIR_STATUS_OK
    assert candidate.price_status == CANDIDATE_PRICE_STATUS_OK
    assert candidate.dispatch_allowed is True
    assert candidate.malformed is False


@pytest.mark.parametrize(
    "field_name",
    (
        "event_id",
        "token_mint",
        "pair_quote_asset",
        "event_kind",
        "ping_type",
        "normalized_event_id",
    ),
)
def test_build_candidate_event_rejects_unsafe_candidate_field(
    field_name,
):
    kwargs = _safe_candidate_kwargs(**{field_name: "bearer-token"})
    with pytest.raises(Stage28_6InvalidCandidateError) as exc_info:
        build_candidate_event(**kwargs)
    assert exc_info.value.field_name == field_name
    # Raw rejected value must NOT appear in the error message.
    assert "bearer-token" not in str(exc_info.value)


def test_build_candidate_event_rejects_forbidden_payload_field_name():
    kwargs = _safe_candidate_kwargs(
        rendered_payload={"subscriber_id": "abc"}
    )
    with pytest.raises(Stage28_6InvalidCandidateError) as exc_info:
        build_candidate_event(**kwargs)
    assert exc_info.value.field_name == "rendered_payload"


def test_build_candidate_event_rejects_webhook_url_in_payload():
    kwargs = _safe_candidate_kwargs(
        rendered_payload={"webhook_url": "redacted"}
    )
    with pytest.raises(Stage28_6InvalidCandidateError):
        build_candidate_event(**kwargs)


def test_build_candidate_event_rejects_api_key_in_payload():
    kwargs = _safe_candidate_kwargs(
        rendered_payload={"api_key": "redacted"}
    )
    with pytest.raises(Stage28_6InvalidCandidateError):
        build_candidate_event(**kwargs)


def test_build_candidate_event_rejects_non_dict_payload():
    kwargs = _safe_candidate_kwargs(rendered_payload="not a dict")
    with pytest.raises(Stage28_6InvalidCandidateError) as exc_info:
        build_candidate_event(**kwargs)
    assert exc_info.value.field_name == "rendered_payload"


def test_build_candidate_event_rejects_unsafe_artifact_reference():
    kwargs = _safe_candidate_kwargs(
        pre_send_artifact_reference="../oops.json"
    )
    with pytest.raises(Stage28_6InvalidCandidateError):
        build_candidate_event(**kwargs)


def test_build_candidate_event_rejects_unsafe_webhook_identity():
    kwargs = _safe_candidate_kwargs(webhook_identity="not safe label")
    with pytest.raises(Stage28_6InvalidCandidateError):
        build_candidate_event(**kwargs)


def test_build_candidate_event_rejects_non_bool_dispatch_allowed():
    kwargs = _safe_candidate_kwargs(dispatch_allowed=1)
    with pytest.raises(Stage28_6InvalidCandidateError):
        build_candidate_event(**kwargs)


def test_build_candidate_event_rejects_non_closed_set_pair_status():
    kwargs = _safe_candidate_kwargs(pair_status="UNKNOWN_LIKE")
    with pytest.raises(Stage28_6InvalidCandidateError):
        build_candidate_event(**kwargs)


def test_build_candidate_event_rejects_non_closed_set_price_status():
    kwargs = _safe_candidate_kwargs(price_status="LATE")
    with pytest.raises(Stage28_6InvalidCandidateError):
        build_candidate_event(**kwargs)


def test_candidate_event_repr_is_safe():
    candidate = build_candidate_event(**_safe_candidate_kwargs())
    rendered = repr(candidate)
    for needle in ("h" + "ttps:", "bearer ", "api_key", "discord" + ".com"):
        assert needle not in rendered.lower()


# ---------------------------------------------------------------------------
# RunnerConfig construction
# ---------------------------------------------------------------------------


def _safe_runner_config_kwargs(**overrides) -> dict:
    base = {
        "run_id": "run-001",
        "session_id": "session-001",
        "max_events": 100,
        "max_dispatches": 10,
        "max_total_retries": 4,
        "max_ticks": 200,
        "heartbeat_every_n_events": 5,
        "fail_closed_on_artifact_error": True,
        "fail_closed_on_ledger_error": True,
        "fail_closed_on_heartbeat_error": False,
    }
    base.update(overrides)
    return base


def test_build_runner_config_returns_named_tuple():
    config = build_runner_config(**_safe_runner_config_kwargs())
    assert isinstance(config, Stage28_6RunnerConfig)
    assert config.run_id == "run-001"
    assert config.max_events == 100
    assert config.max_dispatches == 10


@pytest.mark.parametrize(
    "field_name", ("max_events", "max_dispatches", "max_ticks", "heartbeat_every_n_events"),
)
def test_build_runner_config_rejects_non_positive_bounds(field_name):
    for bad in (0, -1):
        kwargs = _safe_runner_config_kwargs(**{field_name: bad})
        with pytest.raises(
            Stage28_6InvalidRunnerConfigError
        ) as exc_info:
            build_runner_config(**kwargs)
        assert exc_info.value.field_name == field_name


def test_build_runner_config_allows_zero_max_total_retries():
    config = build_runner_config(
        **_safe_runner_config_kwargs(max_total_retries=0)
    )
    assert config.max_total_retries == 0


def test_build_runner_config_rejects_negative_max_total_retries():
    with pytest.raises(Stage28_6InvalidRunnerConfigError) as exc_info:
        build_runner_config(
            **_safe_runner_config_kwargs(max_total_retries=-1)
        )
    assert exc_info.value.field_name == "max_total_retries"


def test_build_runner_config_rejects_bool_int_values():
    with pytest.raises(Stage28_6InvalidRunnerConfigError):
        build_runner_config(
            **_safe_runner_config_kwargs(max_events=True)
        )


def test_build_runner_config_rejects_unsafe_run_id():
    with pytest.raises(Stage28_6InvalidRunnerConfigError) as exc_info:
        build_runner_config(
            **_safe_runner_config_kwargs(
                run_id="h" + "ttps://bad.example"
            )
        )
    assert exc_info.value.field_name == "run_id"


def test_build_runner_config_rejects_unsafe_session_id():
    with pytest.raises(Stage28_6InvalidRunnerConfigError) as exc_info:
        build_runner_config(
            **_safe_runner_config_kwargs(session_id="bearer-token")
        )
    assert exc_info.value.field_name == "session_id"


def test_build_runner_config_rejects_non_bool_fail_closed_flags():
    for field in (
        "fail_closed_on_artifact_error",
        "fail_closed_on_ledger_error",
        "fail_closed_on_heartbeat_error",
    ):
        with pytest.raises(Stage28_6InvalidRunnerConfigError):
            build_runner_config(
                **_safe_runner_config_kwargs(**{field: 1})
            )


# ---------------------------------------------------------------------------
# RunSummary construction
# ---------------------------------------------------------------------------


def _safe_summary_kwargs(**overrides) -> dict:
    base = {
        "run_id": "run-001",
        "session_id": "session-001",
        "stop_reason": STOP_REASON_MAX_EVENTS,
        "events_seen": 5,
        "candidates_seen": 3,
        "dispatch_attempts": 2,
        "dispatch_success": 2,
        "dispatch_failure": 0,
        "retries_attempted": 0,
        "duplicates_suppressed": 0,
        "ambiguous_suppressed": 0,
        "unknown_pair_suppressed": 0,
        "disagree_pair_suppressed": 0,
        "usdc_observe_only": 0,
        "stale_price_suppressed": 0,
        "missing_price_suppressed": 0,
        "malformed_events": 0,
        "ledger_failures": 0,
        "artifact_failures": 0,
        "transport_failures": 0,
        "final_health_status": HEALTH_STATUS_HEALTHY,
    }
    base.update(overrides)
    return base


def test_build_run_summary_returns_named_tuple():
    summary = build_run_summary(**_safe_summary_kwargs())
    assert isinstance(summary, Stage28_6RunSummary)
    assert summary.stop_reason == STOP_REASON_MAX_EVENTS
    assert summary.events_seen == 5
    assert summary.candidates_seen == 3


def test_build_run_summary_rejects_negative_counter():
    with pytest.raises(Stage28_6InvalidRunSummaryError) as exc_info:
        build_run_summary(**_safe_summary_kwargs(events_seen=-1))
    assert exc_info.value.field_name == "events_seen"


def test_build_run_summary_rejects_bool_counter():
    with pytest.raises(Stage28_6InvalidRunSummaryError):
        build_run_summary(**_safe_summary_kwargs(dispatch_attempts=True))


def test_build_run_summary_rejects_unknown_stop_reason():
    with pytest.raises(Stage28_6InvalidRunSummaryError) as exc_info:
        build_run_summary(**_safe_summary_kwargs(stop_reason="MAX_FOO"))
    assert exc_info.value.field_name == "stop_reason"


def test_build_run_summary_rejects_unknown_final_health_status():
    with pytest.raises(Stage28_6InvalidRunSummaryError) as exc_info:
        build_run_summary(
            **_safe_summary_kwargs(final_health_status="GREEN")
        )
    assert exc_info.value.field_name == "final_health_status"


def test_run_summary_field_names_inventory_locked():
    expected = set(STAGE28_6_RUN_SUMMARY_FIELD_NAMES)
    actual = set(Stage28_6RunSummary._fields)
    assert expected == actual


def test_run_summary_counter_field_names_inventory_locked():
    expected = set(STAGE28_6_RUN_SUMMARY_COUNTER_FIELD_NAMES)
    for name in expected:
        assert name in Stage28_6RunSummary._fields


def test_run_summary_to_dict_returns_canonical_dict():
    summary = build_run_summary(**_safe_summary_kwargs())
    out = run_summary_to_dict(summary)
    assert set(out.keys()) == set(STAGE28_6_RUN_SUMMARY_FIELD_NAMES)


def test_run_summary_repr_is_safe():
    summary = build_run_summary(**_safe_summary_kwargs())
    rendered = repr(summary)
    for needle in ("h" + "ttps:", "bearer ", "api_key", "discord" + ".com"):
        assert needle not in rendered.lower()


# ---------------------------------------------------------------------------
# Stop signal
# ---------------------------------------------------------------------------


def test_stop_signal_starts_unrequested():
    signal = Stage28_6StopSignal()
    assert signal.is_requested() is False
    assert signal.reason == STOP_REASON_OPERATOR_STOP


def test_stop_signal_request_stop_sets_flag():
    signal = Stage28_6StopSignal()
    signal.request_stop()
    assert signal.is_requested() is True
    assert signal.reason == STOP_REASON_OPERATOR_STOP


def test_stop_signal_request_stop_accepts_sigint_reason():
    signal = Stage28_6StopSignal()
    signal.request_stop(reason=STOP_REASON_SIGINT)
    assert signal.is_requested() is True
    assert signal.reason == STOP_REASON_SIGINT


def test_stop_signal_rejects_non_operator_stop_reason():
    signal = Stage28_6StopSignal()
    with pytest.raises(Stage28_6SessionRunnerError):
        signal.request_stop(reason=STOP_REASON_MAX_EVENTS)


# ---------------------------------------------------------------------------
# Tick clock
# ---------------------------------------------------------------------------


def test_tick_clock_monotonic_and_bounded():
    clock = Stage28_6DeterministicTickClock()
    assert clock.count == 0
    first = clock.tick()
    second = clock.tick()
    assert first == 1
    assert second == 2
    assert clock.count == 2


# ---------------------------------------------------------------------------
# Fake transport
# ---------------------------------------------------------------------------


def test_fake_transport_default_yields_sent_ok():
    transport = Stage28_6FakeTransport()
    result = transport.send_one_audited_post(
        webhook_identity="PRIVATE_OPERATOR_WEBHOOK",
        payload={"content": "ping"},
    )
    assert isinstance(result, Stage28_4TransportResult)
    assert result.transport_status == TRANSPORT_STATUS_SENT_OK
    assert result.ok is True
    assert result.send_attempt_count == 1
    assert transport.call_count == 1


def test_fake_transport_scripted_sequence_consumed_in_order():
    transport = Stage28_6FakeTransport(
        scripted_outcomes=(
            TRANSPORT_STATUS_RATE_LIMITED,
            TRANSPORT_STATUS_SERVER_ERROR,
            TRANSPORT_STATUS_SENT_OK,
        ),
    )
    a = transport.send_one_audited_post(
        webhook_identity="PRIVATE_OPERATOR_WEBHOOK",
        payload={"content": "ping"},
    )
    b = transport.send_one_audited_post(
        webhook_identity="PRIVATE_OPERATOR_WEBHOOK",
        payload={"content": "ping"},
    )
    c = transport.send_one_audited_post(
        webhook_identity="PRIVATE_OPERATOR_WEBHOOK",
        payload={"content": "ping"},
    )
    assert a.transport_status == TRANSPORT_STATUS_RATE_LIMITED
    assert b.transport_status == TRANSPORT_STATUS_SERVER_ERROR
    assert c.transport_status == TRANSPORT_STATUS_SENT_OK
    assert transport.call_count == 3


def test_fake_transport_rate_limited_carries_retry_after():
    transport = Stage28_6FakeTransport(
        scripted_outcomes=(TRANSPORT_STATUS_RATE_LIMITED,),
        scripted_retry_after_seconds=2.5,
    )
    result = transport.send_one_audited_post(
        webhook_identity="PRIVATE_OPERATOR_WEBHOOK",
        payload={"content": "ping"},
    )
    assert result.retry_after_seconds == 2.5


def test_fake_transport_validation_failed_send_attempt_count_zero():
    transport = Stage28_6FakeTransport(
        scripted_outcomes=(TRANSPORT_STATUS_VALIDATION_FAILED,),
    )
    result = transport.send_one_audited_post(
        webhook_identity="PRIVATE_OPERATOR_WEBHOOK",
        payload={"content": "ping"},
    )
    assert result.send_attempt_count == 0


def test_fake_transport_network_error_send_attempt_count_one():
    transport = Stage28_6FakeTransport(
        scripted_outcomes=(TRANSPORT_STATUS_NETWORK_ERROR,),
    )
    result = transport.send_one_audited_post(
        webhook_identity="PRIVATE_OPERATOR_WEBHOOK",
        payload={"content": "ping"},
    )
    assert result.send_attempt_count == 1


def test_fake_transport_records_calls():
    transport = Stage28_6FakeTransport()
    transport.send_one_audited_post(
        webhook_identity="PRIVATE_OPERATOR_WEBHOOK",
        payload={"content": "first"},
    )
    transport.send_one_audited_post(
        webhook_identity="PRIVATE_OPERATOR_WEBHOOK",
        payload={"content": "second"},
    )
    calls = transport.calls
    assert len(calls) == 2
    assert calls[0]["payload"]["content"] == "first"
    assert calls[1]["payload"]["content"] == "second"


def test_fake_transport_rejects_non_closed_set_scripted_outcome():
    with pytest.raises(Stage28_6SessionRunnerError):
        Stage28_6FakeTransport(scripted_outcomes=("NOT_A_STATUS",))


# ---------------------------------------------------------------------------
# Redaction discipline (canary substring scan)
# ---------------------------------------------------------------------------


_CANARY_WEBHOOK_URL: str = (
    "h" + "ttps://" + "discord" + ".com/api/webhooks/12345/abcd"
)
_CANARY_API_KEY: str = "s" + "k-test-canary-1234567890"
_CANARY_BEARER: str = "Bearer canary-token-1234567890"


def test_repr_safe_under_canary_payload_rejection():
    # If a caller tries to slip a canary URL into the rendered_payload
    # under a forbidden field, construction must refuse it.
    with pytest.raises(Stage28_6InvalidCandidateError):
        build_candidate_event(
            **_safe_candidate_kwargs(
                rendered_payload={"webhook_url": _CANARY_WEBHOOK_URL},
            )
        )


def test_summary_repr_does_not_carry_canary():
    summary = build_run_summary(**_safe_summary_kwargs())
    rendered = repr(summary)
    assert _CANARY_WEBHOOK_URL not in rendered
    assert _CANARY_API_KEY not in rendered
    assert _CANARY_BEARER not in rendered

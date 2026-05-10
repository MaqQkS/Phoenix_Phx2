"""Dispatcher behavior."""

import pytest

from PHX2.dispatch.dispatcher import Dispatcher
from PHX2.dispatch.sinks.base import DeliveryResult
from PHX2.tests.dispatch._fixtures import (
    FakeRepository,
    RecordingSink,
    make_rendered_alert,
)


ROUTING_TWO = {"would_alert": {"CLEAN": ["a", "b"]}}
ROUTING_ONE = {"would_alert": {"CLEAN": ["a"]}}
ROUTING_UNKNOWN_SINK = {"would_alert": {"CLEAN": ["nope"]}}
ROUTING_EMPTY = {}


def _events(repo: FakeRepository):
    return list(repo.events.values())


def _call_sequence(repo: FakeRepository):
    return [call[0] for call in repo.calls]


def test_active_routed_writes_pending_then_invokes_sink_then_updates_to_sent():
    sink = RecordingSink("a")
    repo = FakeRepository()
    dispatcher = Dispatcher(
        sinks={"a": sink},
        repository=repo,
        routing_config=ROUTING_ONE,
    )

    dispatcher.dispatch(make_rendered_alert(), alert_decision_id=42)

    assert _call_sequence(repo) == ["create", "update_status"]
    assert repo.calls[0][1].status == "pending"
    assert len(sink.calls) == 1
    update_call = repo.calls[1]
    assert update_call[2] == "sent"
    events = _events(repo)
    assert len(events) == 1
    assert events[0].status == "sent"


def test_active_routed_to_multiple_sinks_each_run_to_completion():
    sink_a = RecordingSink("a")
    sink_b = RecordingSink("b")
    repo = FakeRepository()
    dispatcher = Dispatcher(
        sinks={"a": sink_a, "b": sink_b},
        repository=repo,
        routing_config=ROUTING_TWO,
    )

    dispatcher.dispatch(make_rendered_alert(), alert_decision_id=10)

    assert _call_sequence(repo) == [
        "create",
        "update_status",
        "create",
        "update_status",
    ]
    assert len(sink_a.calls) == 1
    assert len(sink_b.calls) == 1
    targets = [event.target for event in _events(repo)]
    assert sorted(targets) == ["a", "b"]
    statuses = [event.status for event in _events(repo)]
    assert statuses == ["sent", "sent"]


def test_first_sink_raises_second_sink_still_runs():
    boom = RecordingSink("a", raise_exc=RuntimeError("kaboom"))
    sink_b = RecordingSink("b")
    repo = FakeRepository()
    dispatcher = Dispatcher(
        sinks={"a": boom, "b": sink_b},
        repository=repo,
        routing_config=ROUTING_TWO,
    )

    dispatcher.dispatch(make_rendered_alert(), alert_decision_id=5)

    events_by_target = {event.target: event for event in _events(repo)}
    assert events_by_target["a"].status == "failed"
    assert "kaboom" in (events_by_target["a"].error_message or "")
    assert events_by_target["b"].status == "sent"
    assert len(sink_b.calls) == 1


def test_first_sink_returning_failed_result_does_not_block_second_sink():
    sink_a = RecordingSink(
        "a",
        result=DeliveryResult(
            success=False, payload_ref=None, error_message="planned_failure"
        ),
    )
    sink_b = RecordingSink("b")
    repo = FakeRepository()
    dispatcher = Dispatcher(
        sinks={"a": sink_a, "b": sink_b},
        repository=repo,
        routing_config=ROUTING_TWO,
    )

    dispatcher.dispatch(make_rendered_alert(), alert_decision_id=11)

    events_by_target = {event.target: event for event in _events(repo)}
    assert events_by_target["a"].status == "failed"
    assert "planned_failure" in (events_by_target["a"].error_message or "")
    assert events_by_target["b"].status == "sent"
    assert len(sink_b.calls) == 1


def test_sink_returning_failed_result_is_recorded_with_error_message():
    sink = RecordingSink(
        "a",
        result=DeliveryResult(success=False, payload_ref=None, error_message="nope"),
    )
    repo = FakeRepository()
    dispatcher = Dispatcher(
        sinks={"a": sink},
        repository=repo,
        routing_config=ROUTING_ONE,
    )

    dispatcher.dispatch(make_rendered_alert(), alert_decision_id=1)

    event = next(iter(repo.events.values()))
    assert event.status == "failed"
    assert event.error_message == "nope"
    assert event.payload_ref is None


def test_success_result_payload_ref_is_forwarded_into_dispatch_event():
    sink = RecordingSink(
        "a",
        result=DeliveryResult(
            success=True,
            payload_ref="/tmp/decisions.jsonl",
            error_message=None,
        ),
    )
    repo = FakeRepository()
    dispatcher = Dispatcher(
        sinks={"a": sink},
        repository=repo,
        routing_config=ROUTING_ONE,
    )

    dispatcher.dispatch(make_rendered_alert(), alert_decision_id=1)

    event = next(iter(repo.events.values()))
    assert event.status == "sent"
    assert event.payload_ref == "/tmp/decisions.jsonl"


def test_idempotency_blocks_second_dispatch_for_same_decision_target():
    sink = RecordingSink("a")
    repo = FakeRepository()
    dispatcher = Dispatcher(
        sinks={"a": sink},
        repository=repo,
        routing_config=ROUTING_ONE,
    )

    dispatcher.dispatch(make_rendered_alert(), alert_decision_id=99)
    dispatcher.dispatch(make_rendered_alert(), alert_decision_id=99)

    assert len(sink.calls) == 1
    assert len(_events(repo)) == 1


def test_failed_row_does_not_block_subsequent_dispatch():
    boom = RecordingSink("a", raise_exc=RuntimeError("kaboom"))
    repo = FakeRepository()
    dispatcher = Dispatcher(
        sinks={"a": boom},
        repository=repo,
        routing_config=ROUTING_ONE,
    )

    dispatcher.dispatch(make_rendered_alert(), alert_decision_id=99)

    # Replace the sink with a successful one and dispatch again — should write
    # a new row because the failed row does not block per the schema.
    success = RecordingSink("a")
    dispatcher._sinks["a"] = success
    dispatcher.dispatch(make_rendered_alert(), alert_decision_id=99)

    statuses = sorted(event.status for event in _events(repo))
    assert statuses == ["failed", "sent"]
    assert len(success.calls) == 1


def test_unknown_sink_writes_failed_row_and_does_not_affect_other_sinks():
    sink_b = RecordingSink("b")
    repo = FakeRepository()
    dispatcher = Dispatcher(
        sinks={"b": sink_b},
        repository=repo,
        routing_config={"would_alert": {"CLEAN": ["b"]}},
    )
    # Inject an unknown sink target into routing post-construction so the
    # runtime fallback in _dispatch_one is exercised. (Construction-time
    # validation rejects unknown sinks, so this defensive branch is only
    # reachable via post-construction mutation.)
    dispatcher._routing = {"would_alert": {"CLEAN": ["nope", "b"]}}

    dispatcher.dispatch(make_rendered_alert(), alert_decision_id=7)

    by_target = {event.target: event for event in _events(repo)}
    assert by_target["nope"].status == "failed"
    assert "unknown_sink:nope" == by_target["nope"].error_message
    assert by_target["b"].status == "sent"
    assert len(sink_b.calls) == 1


def test_active_unrouted_combination_writes_skipped_none_row():
    sink = RecordingSink("a")
    repo = FakeRepository()
    dispatcher = Dispatcher(
        sinks={"a": sink},
        repository=repo,
        routing_config=ROUTING_EMPTY,
    )

    dispatcher.dispatch(make_rendered_alert(), alert_decision_id=3)

    events = _events(repo)
    assert len(events) == 1
    assert events[0].target == "(none)"
    assert events[0].status == "skipped"
    assert events[0].completed_at is not None
    assert events[0].error_message == "no_targets:unconfigured_route"
    assert sink.calls == []


def test_disabled_mode_with_audit_writes_skipped_none_row():
    sink = RecordingSink("a")
    repo = FakeRepository()
    dispatcher = Dispatcher(
        sinks={"a": sink},
        repository=repo,
        routing_config=ROUTING_ONE,  # routing exists, but mode=disabled overrides
        mode="disabled",
        audit_undelivered=True,
    )

    dispatcher.dispatch(make_rendered_alert(), alert_decision_id=3)

    events = _events(repo)
    assert len(events) == 1
    assert events[0].target == "(none)"
    assert events[0].status == "skipped"
    assert events[0].error_message == "no_targets:disabled"
    assert sink.calls == []


def test_disabled_mode_without_audit_writes_nothing():
    sink = RecordingSink("a")
    repo = FakeRepository()
    dispatcher = Dispatcher(
        sinks={"a": sink},
        repository=repo,
        routing_config=ROUTING_ONE,
        mode="disabled",
        audit_undelivered=False,
    )

    dispatcher.dispatch(make_rendered_alert(), alert_decision_id=3)

    assert _events(repo) == []
    assert sink.calls == []


def test_dispatch_never_raises_even_if_sink_raises():
    boom = RecordingSink("a", raise_exc=ValueError("boom"))
    repo = FakeRepository()
    dispatcher = Dispatcher(
        sinks={"a": boom},
        repository=repo,
        routing_config=ROUTING_ONE,
    )

    # No exception should escape the dispatcher.
    dispatcher.dispatch(make_rendered_alert(), alert_decision_id=1)


def test_dispatch_never_raises_when_routing_returns_unknown_sink():
    repo = FakeRepository()
    dispatcher = Dispatcher(
        sinks={},
        repository=repo,
        routing_config=ROUTING_EMPTY,
    )
    # Same justification as the prior test: post-construction mutation
    # is the only way to reach the _dispatch_one unknown-sink fallback
    # now that validate_routing_config rejects unknown sinks at __init__.
    dispatcher._routing = ROUTING_UNKNOWN_SINK

    dispatcher.dispatch(make_rendered_alert(), alert_decision_id=1)
    events = _events(repo)
    assert len(events) == 1
    assert events[0].status == "failed"


def test_all_rows_share_dispatch_run_id_from_one_dispatcher_instance():
    sink_a = RecordingSink("a")
    sink_b = RecordingSink("b")
    repo = FakeRepository()
    dispatcher = Dispatcher(
        sinks={"a": sink_a, "b": sink_b},
        repository=repo,
        routing_config=ROUTING_TWO,
    )

    dispatcher.dispatch(make_rendered_alert(), alert_decision_id=1)
    dispatcher.dispatch(make_rendered_alert(), alert_decision_id=2)

    run_ids = {event.dispatch_run_id for event in _events(repo)}
    assert len(run_ids) == 1
    assert dispatcher.dispatch_run_id in run_ids


def test_invalid_mode_raises_at_construction():
    with pytest.raises(ValueError):
        Dispatcher(
            sinks={},
            repository=FakeRepository(),
            routing_config=ROUTING_EMPTY,
            mode="paranoid",
        )


def test_constructor_rejects_typo_in_sink_name():
    sink = RecordingSink("a")
    with pytest.raises(ValueError) as excinfo:
        Dispatcher(
            sinks={"a": sink},
            repository=FakeRepository(),
            routing_config={"would_alert": {"CLEAN": ["a", "tpyo"]}},
        )
    assert "tpyo" in str(excinfo.value)


def test_constructor_rejects_uppercase_decision_type_casing():
    sink = RecordingSink("a")
    with pytest.raises(ValueError) as excinfo:
        Dispatcher(
            sinks={"a": sink},
            repository=FakeRepository(),
            routing_config={"WOULD_ALERT": {"CLEAN": ["a"]}},
        )
    assert "WOULD_ALERT" in str(excinfo.value)


def test_constructor_rejects_lowercase_severity_casing():
    sink = RecordingSink("a")
    with pytest.raises(ValueError) as excinfo:
        Dispatcher(
            sinks={"a": sink},
            repository=FakeRepository(),
            routing_config={"would_alert": {"clean": ["a"]}},
        )
    assert "clean" in str(excinfo.value)

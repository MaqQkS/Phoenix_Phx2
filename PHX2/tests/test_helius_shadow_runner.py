"""Offline ownership and bounds tests for the parity runner."""

from __future__ import annotations

import inspect
import json
from pathlib import Path

import pytest

from PHX2.free_tier_producer.helius_source import (
    HELIUS_SHADOW,
    MIGRATION_SOURCE_ENV,
)
from PHX2.free_tier_producer.compat.build26_capture_artifacts import scan_text
from PHX2.scripts import helius_shadow_parity_runner as runner


@pytest.mark.parametrize(
    ("seconds", "events"),
    (
        (0, 1),
        (runner.MAX_DURATION_SECONDS + 1, 1),
        (1, 0),
        (1, runner.MAX_MIGRATION_EVENTS_PER_SOURCE + 1),
    ),
)
def test_runner_bounds_fail_before_source_construction(
    seconds: int,
    events: int,
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError):
        runner.run_shadow_parity(
            duration_seconds=seconds,
            max_events_per_source=events,
            output=tmp_path / "never.jsonl",
            env_path=None,
        )


def test_runner_requires_explicit_helius_shadow_mode(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.delenv(MIGRATION_SOURCE_ENV, raising=False)
    with pytest.raises(RuntimeError, match="HELIUS_SHADOW"):
        runner.run_shadow_parity(
            duration_seconds=1,
            max_events_per_source=1,
            output=tmp_path / "never.jsonl",
            env_path=None,
        )


def test_runner_refuses_retired_helius_shadow_mode_before_artifact_access(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv(MIGRATION_SOURCE_ENV, HELIUS_SHADOW)
    with pytest.raises(RuntimeError, match="HELIUS_SHADOW"):
        runner.run_shadow_parity(
            duration_seconds=1,
            max_events_per_source=1,
            output=tmp_path / "outside.jsonl",
            env_path=None,
        )


def test_runner_source_has_no_delivery_or_ledger_construction() -> None:
    text = inspect.getsource(runner).lower()
    for token in (
        "telegram_transport",
        "telegram_adapter",
        "delivery_transaction",
        "ping_dedupe.jsonl",
        "reserve_delivery",
        "commit_delivery",
        "production_supervisor",
        "free_tier_session",
    ):
        assert token not in text


def test_exception_names_are_sanitized() -> None:
    assert runner._safe_exception_name(OSError("secret URL")) == "OSError"
    unsafe = type("Unsafe-Name", (Exception,), {})
    assert runner._safe_exception_name(unsafe()) == "UNSAFE_EXCEPTION_CLASS"


def test_one_provider_failure_cannot_silently_cancel_the_other() -> None:
    lifecycle = runner.ProviderLifecycle()
    lifecycle.note_provider_failure("SHADOW_STREAM")
    assert lifecycle.provider_failed("SHADOW_STREAM") is True
    assert lifecycle.provider_failed("CONTROL_SOURCE") is False
    assert lifecycle.shared_stop.is_set() is False


def test_shared_stop_is_published_before_source_close() -> None:
    lifecycle = runner.ProviderLifecycle()
    order = []

    class Source:
        def __init__(self, name: str) -> None:
            self.name = name

        def close(self) -> None:
            order.append((self.name, lifecycle.shared_stop.is_set()))

    runner._request_shared_stop(
        lifecycle,
        (Source("shadow"), Source("control")),
    )
    assert order == [("shadow", True), ("control", True)]


def test_operator_summary_uses_scanner_safe_role_names() -> None:
    summary = runner.RunnerSummary(
        duration_seconds=1.0,
        task_state="ABSENT",
        control_subscription_started=True,
        control_updates=1,
        control_transactions=1,
        control_status="CANCELLED",
        control_observations=0,
        shadow_connected=True,
        shadow_notifications=1,
        shadow_observations=0,
        shadow_bytes=100,
        shadow_stream_bytes=100,
        shadow_fetch_bytes=0,
        shadow_byte_ceiling=1000,
        shadow_byte_ceiling_reached=False,
        parity_records=0,
        match_status_counts={"MATCH": 0, "CONTROL_ONLY": 0},
        source_errors=(),
        shadow_status="STOPPED",
        shadow_continuity_state="NO_GAP",
        late_match_grace_seconds=5.0,
        output="artifacts/helius_shadow_parity/safe.jsonl",
    )
    assert scan_text(json.dumps(summary.__dict__, sort_keys=True)) == []

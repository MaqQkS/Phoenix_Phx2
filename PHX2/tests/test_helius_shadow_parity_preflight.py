"""Offline safety-policy tests for the standalone parity preflight."""

from __future__ import annotations

import inspect
import json
import subprocess

import pytest

from PHX2.scripts import helius_shadow_parity_preflight as preflight
from PHX2.scripts import helius_shadow_parity_runner as runner


def _facts(**overrides):
    values = {
        "task_state": preflight.TASK_DISABLED,
        "process_enumeration_verified": True,
        "watchdog_processes": 0,
        "producer_processes": 0,
        "yellowstone_owners": 0,
        "capabilities": preflight.ShadowParityCapabilities(),
    }
    values.update(overrides)
    return preflight.ShadowParityPreflightFacts(**values)


@pytest.mark.parametrize(
    ("task_state", "safe_line"),
    (
        (preflight.TASK_ABSENT, "TASK_STATE=ABSENT_SAFE"),
        (preflight.TASK_DISABLED, "TASK_STATE=DISABLED_SAFE"),
    ),
)
def test_absent_or_disabled_task_passes(
    task_state: str, safe_line: str
) -> None:
    report = preflight.evaluate_preflight(_facts(task_state=task_state))
    assert report.sanitized_lines()[0] == safe_line


@pytest.mark.parametrize(
    ("task_state", "reason"),
    (
        (preflight.TASK_ENABLED, "TASK_ENABLED"),
        (preflight.TASK_RUNNING, "TASK_RUNNING"),
    ),
)
def test_enabled_or_running_task_refuses(
    task_state: str, reason: str
) -> None:
    with pytest.raises(preflight.ShadowParityPreflightError) as caught:
        preflight.evaluate_preflight(_facts(task_state=task_state))
    assert caught.value.reason == reason


@pytest.mark.parametrize(
    ("field", "reason"),
    (
        ("watchdog_processes", "WATCHDOG_PROCESS_PRESENT"),
        ("producer_processes", "PRODUCER_PROCESS_PRESENT"),
        ("yellowstone_owners", "YELLOWSTONE_OWNER_PRESENT"),
    ),
)
def test_existing_runtime_owner_refuses(field: str, reason: str) -> None:
    with pytest.raises(preflight.ShadowParityPreflightError) as caught:
        preflight.evaluate_preflight(_facts(**{field: 1}))
    assert caught.value.reason == reason


@pytest.mark.parametrize(
    ("capability", "reason"),
    (
        ("telegram_capable", "TELEGRAM_CONSTRUCTION_CAPABLE"),
        (
            "production_ledger_capable",
            "PRODUCTION_LEDGER_WRITE_CAPABLE",
        ),
        (
            "production_launcher_capable",
            "PRODUCTION_LAUNCHER_CAPABLE",
        ),
    ),
)
def test_forbidden_capability_refuses(
    capability: str, reason: str
) -> None:
    capabilities = preflight.ShadowParityCapabilities(
        **{capability: True}
    )
    with pytest.raises(preflight.ShadowParityPreflightError) as caught:
        preflight.evaluate_preflight(
            _facts(capabilities=capabilities)
        )
    assert caught.value.reason == reason


def test_task_query_passes_no_credentials_on_command_line(
    monkeypatch,
) -> None:
    secret = "credential-that-must-not-render"
    captured = {}

    def fake_run(arguments, **kwargs):
        captured["arguments"] = tuple(arguments)
        captured["kwargs"] = kwargs
        return subprocess.CompletedProcess(
            arguments,
            0,
            stdout=json.dumps({"state": "DISABLED"}),
            stderr="",
        )

    monkeypatch.setattr(preflight.os, "name", "nt")
    state = preflight.read_watchdog_task_state(runner=fake_run)
    assert state == preflight.TASK_DISABLED
    assert secret not in repr(captured)
    assert "--env-file" not in repr(captured["arguments"])


def test_runner_and_preflight_have_no_send_or_production_write_surface() -> None:
    text = (
        inspect.getsource(runner) + inspect.getsource(preflight)
    ).lower()
    for token in (
        "telegram_adapter",
        "delivery_transaction",
        "reserve_delivery",
        "commit_delivery",
        "launch_pressure_24h_01",
        "launch_soak_02h_01",
        "launch_window_04",
    ):
        assert token not in text


def test_preflight_report_is_presence_only() -> None:
    rendered = "\n".join(
        preflight.evaluate_preflight(_facts()).sanitized_lines()
    )
    assert rendered == "\n".join(
        (
            "TASK_STATE=DISABLED_SAFE",
            "WATCHDOG_PROCESSES=0",
            "PRODUCER_PROCESSES=0",
            "YELLOWSTONE_OWNERS=0",
            "TELEGRAM_CONSTRUCTION=DISABLED",
            "PRODUCTION_LEDGER_WRITE=DISABLED",
            "PRODUCTION_LAUNCHER=DISABLED",
        )
    )

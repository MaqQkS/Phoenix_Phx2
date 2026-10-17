from __future__ import annotations

import runpy
from datetime import datetime, timezone
from pathlib import Path

import pytest

from PHX2 import operator_cli
from PHX2.runtime import production_entrypoint as entry
from PHX2.runtime.production_supervisor import DEFAULT_HOURS, ProductionPaths, fresh_run_dir


def test_repo_root_main_delegates(monkeypatch):
    called = []

    def fake_main():
        called.append(True)
        return 17

    monkeypatch.setattr(operator_cli, "main", fake_main)
    root_main = Path(__file__).resolve().parents[3] / "main.py"
    with pytest.raises(SystemExit) as raised:
        runpy.run_path(str(root_main), run_name="__main__")
    assert raised.value.code == 17
    assert called == [True]


def test_default_duration_is_24_hours():
    assert entry.build_parser().parse_args([]).hours == DEFAULT_HOURS == 24.0


def test_fresh_timestamped_run_directory(tmp_path):
    value = fresh_run_dir(
        tmp_path, now=datetime(2026, 7, 16, 6, 42, 1, tzinfo=timezone.utc)
    )
    assert value == tmp_path / "phx2_live_20260716T064201Z"


def test_status_is_read_only_and_does_not_construct_supervisor(monkeypatch, tmp_path, capsys):
    paths = ProductionPaths(runtime_root=tmp_path, lock_path=tmp_path / "lock")
    monkeypatch.setattr(
        entry,
        "read_status",
        lambda paths, run_dir=None: {
            "active": False,
            "lock_state": "ABSENT",
            "run_dir": None,
            "processes": {},
            "paper_status": "DEGRADED",
            "paper_restart_attempts": 3,
            "paper_restart_limit": 3,
            "paper_last_exit_code": 5,
            "market_scheduler": {"queue": 7, "slo_breached": False},
        },
    )

    class ForbiddenSupervisor:
        def __init__(self, config):
            raise AssertionError("status constructed a supervisor")

    assert entry.main(["--status"], paths=paths, supervisor_type=ForbiddenSupervisor) == 0
    output = capsys.readouterr().out
    assert "PHX2_ACTIVE=NO" in output
    assert "PAPER_STATUS=DEGRADED" in output
    assert "PAPER_RESTARTS=3/3 LAST_EXIT=5" in output
    assert "MARKET_SCHEDULER={'queue': 7, 'slo_breached': False}" in output
    assert not tmp_path.joinpath("lock").exists()


@pytest.mark.parametrize(
    "flag",
    ("--no-send", "--dry-run", "--compose-only", "--source-only", "--transport-disarmed"),
)
def test_disarmed_runtime_modes_are_not_exposed(flag):
    with pytest.raises(SystemExit):
        entry.build_parser().parse_args([flag])

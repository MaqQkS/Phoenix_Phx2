from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from PHX2.paper_trading import ledger as ledger_module
from PHX2.paper_trading.ledger import (
    ATOMIC_REPLACE_MAX_ATTEMPTS,
    EVENTS_FILE,
    HEARTBEAT_FILE,
    PaperLedger,
    read_jsonl,
)


def _access_denied() -> PermissionError:
    error = PermissionError(5, "Access is denied")
    error.winerror = 5
    return error


def _temporary_files(run_dir: Path) -> list[Path]:
    return list(run_dir.glob(f".{HEARTBEAT_FILE}.*.tmp"))


def test_windows_winerror5_first_replace_retries_and_succeeds(
    tmp_path, monkeypatch
):
    ledger = PaperLedger(str(tmp_path))
    real_replace = os.replace
    attempts = []
    delays = []

    def replace(source, target):
        attempts.append((Path(source), Path(target)))
        if len(attempts) == 1:
            raise _access_denied()
        return real_replace(source, target)

    monkeypatch.setattr(ledger_module.os, "replace", replace)
    monkeypatch.setattr(ledger_module.time, "sleep", delays.append)
    ledger.write_json_atomic(HEARTBEAT_FILE, {"sequence": 2})
    ledger.close()

    assert len(attempts) == 2
    assert attempts[0][0] == attempts[1][0]
    assert attempts[0][0].parent == tmp_path
    assert attempts[0][0].name != f"{HEARTBEAT_FILE}.tmp"
    assert delays == [0.025]
    assert json.loads((tmp_path / HEARTBEAT_FILE).read_text(encoding="utf-8")) == {
        "sequence": 2
    }
    assert _temporary_files(tmp_path) == []


def test_multiple_permission_errors_succeed_with_bounded_backoff(
    tmp_path, monkeypatch
):
    ledger = PaperLedger(str(tmp_path))
    real_replace = os.replace
    attempts = 0
    delays = []

    def replace(source, target):
        nonlocal attempts
        attempts += 1
        if attempts < ATOMIC_REPLACE_MAX_ATTEMPTS:
            raise _access_denied()
        return real_replace(source, target)

    monkeypatch.setattr(ledger_module.os, "replace", replace)
    monkeypatch.setattr(ledger_module.time, "sleep", delays.append)
    ledger.write_json_atomic(HEARTBEAT_FILE, {"status": "healthy"})
    ledger.close()

    assert attempts == ATOMIC_REPLACE_MAX_ATTEMPTS
    assert delays == [0.025, 0.05, 0.1]
    assert _temporary_files(tmp_path) == []


def test_permanent_permission_error_uses_exact_limit_and_preserves_prior_heartbeat(
    tmp_path, monkeypatch
):
    target = tmp_path / HEARTBEAT_FILE
    prior = '{"sequence":1,"status":"valid"}\n'
    target.write_text(prior, encoding="utf-8")
    ledger = PaperLedger(str(tmp_path))
    attempts = 0

    def replace(source, destination):
        nonlocal attempts
        attempts += 1
        assert Path(destination).read_text(encoding="utf-8") == prior
        raise _access_denied()

    monkeypatch.setattr(ledger_module.os, "replace", replace)
    monkeypatch.setattr(ledger_module.time, "sleep", lambda _: None)

    with pytest.raises(PermissionError) as caught:
        ledger.write_json_atomic(HEARTBEAT_FILE, {"sequence": 2})
    ledger.close()

    assert caught.value.winerror == 5
    assert attempts == ATOMIC_REPLACE_MAX_ATTEMPTS
    assert target.read_text(encoding="utf-8") == prior
    assert json.loads(target.read_text(encoding="utf-8"))["sequence"] == 1
    assert _temporary_files(tmp_path) == []


def test_partial_new_heartbeat_is_never_exposed_during_retries(
    tmp_path, monkeypatch
):
    target = tmp_path / HEARTBEAT_FILE
    target.write_text('{"sequence":1}\n', encoding="utf-8")
    ledger = PaperLedger(str(tmp_path))
    real_replace = os.replace
    observed = []

    def replace(source, destination):
        observed.append(json.loads(Path(destination).read_text(encoding="utf-8")))
        if len(observed) < 3:
            raise _access_denied()
        return real_replace(source, destination)

    monkeypatch.setattr(ledger_module.os, "replace", replace)
    monkeypatch.setattr(ledger_module.time, "sleep", lambda _: None)
    ledger.write_json_atomic(HEARTBEAT_FILE, {"sequence": 2, "complete": True})
    ledger.close()

    assert observed == [{"sequence": 1}, {"sequence": 1}, {"sequence": 1}]
    assert json.loads(target.read_text(encoding="utf-8")) == {
        "sequence": 2,
        "complete": True,
    }


def test_atomic_diagnostics_are_structured_and_redaction_safe(
    tmp_path, monkeypatch
):
    secret = "super-secret-token-positive-control"
    (tmp_path / HEARTBEAT_FILE).write_text('{"sequence":1}\n', encoding="utf-8")
    ledger = PaperLedger(str(tmp_path))

    monkeypatch.setattr(
        ledger_module.os, "replace", lambda *_: (_ for _ in ()).throw(_access_denied())
    )
    monkeypatch.setattr(ledger_module.time, "sleep", lambda _: None)
    with pytest.raises(PermissionError):
        ledger.write_json_atomic(HEARTBEAT_FILE, {"token": secret})
    ledger.close()

    diagnostics = read_jsonl(str(tmp_path / EVENTS_FILE))
    assert len(diagnostics) == ATOMIC_REPLACE_MAX_ATTEMPTS
    assert diagnostics[-1] == {
        "artifact_category": "HEARTBEAT",
        "attempt_count": ATOMIC_REPLACE_MAX_ATTEMPTS,
        "error_category": "PERMISSION_ERROR_ACCESS_DENIED",
        "event": "ATOMIC_REPLACE_FAILED",
        "kind": "PAPER_ATOMIC_WRITE_DIAGNOSTIC",
        "max_attempts": ATOMIC_REPLACE_MAX_ATTEMPTS,
    }
    assert secret not in (tmp_path / EVENTS_FILE).read_text(encoding="utf-8")
    assert _temporary_files(tmp_path) == []

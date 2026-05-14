"""Phase 18.3 tests for the subprocess-isolated git helper.

These tests verify that ``get_git_commit()`` returns a 40-char
lowercase hex SHA when git produces one, and returns the literal
string ``"unknown"`` on every failure mode (missing binary,
nonzero exit, timeout, malformed output).

Failure modes are exercised by replacing the ``subprocess``
attribute inside ``PHX2.stage18._git`` for the duration of one
test, via ``monkeypatch``. The real ``subprocess`` module is not
mutated.
"""

from __future__ import annotations

import re
import subprocess

import pytest

from PHX2.stage18._git import get_git_commit


_HEX40 = re.compile(r"^[0-9a-f]{40}$")


class _StubSubprocess:
    """Stand-in for the ``subprocess`` module attribute inside
    ``PHX2.stage18._git``. Exposes the three exception classes
    referenced by the helper's ``except`` clause, plus a single
    ``run`` callable supplied by the test."""

    SubprocessError = subprocess.SubprocessError
    CalledProcessError = subprocess.CalledProcessError
    TimeoutExpired = subprocess.TimeoutExpired

    def __init__(self, run_impl) -> None:
        self.run = run_impl


class _CompletedProcess:
    """Minimal completed-process surface used by the helper."""

    def __init__(self, stdout: str) -> None:
        self.stdout = stdout


def test_get_git_commit_returns_real_sha_or_unknown_in_actual_environment() -> None:
    """No mocking. In a git checkout returns a 40-char hex SHA;
    on systems without git or outside a repo, returns ``"unknown"``.
    Either is acceptable -- the test guards against crashes and
    type mismatches, not against the host environment."""

    result = get_git_commit()
    assert result == "unknown" or _HEX40.match(result), (
        f"unexpected get_git_commit() output: {result!r}"
    )


def test_get_git_commit_returns_unknown_on_file_not_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _run(*args, **kwargs):
        raise FileNotFoundError("git binary not on PATH")

    monkeypatch.setattr(
        "PHX2.stage18._git.subprocess", _StubSubprocess(_run)
    )
    assert get_git_commit() == "unknown"


def test_get_git_commit_returns_unknown_on_called_process_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _run(*args, **kwargs):
        raise subprocess.CalledProcessError(1, ["git", "rev-parse", "HEAD"])

    monkeypatch.setattr(
        "PHX2.stage18._git.subprocess", _StubSubprocess(_run)
    )
    assert get_git_commit() == "unknown"


def test_get_git_commit_returns_unknown_on_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _run(*args, **kwargs):
        raise subprocess.TimeoutExpired(["git", "rev-parse", "HEAD"], 2)

    monkeypatch.setattr(
        "PHX2.stage18._git.subprocess", _StubSubprocess(_run)
    )
    assert get_git_commit() == "unknown"


def test_get_git_commit_returns_unknown_on_oserror(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _run(*args, **kwargs):
        raise OSError("disk failure")

    monkeypatch.setattr(
        "PHX2.stage18._git.subprocess", _StubSubprocess(_run)
    )
    assert get_git_commit() == "unknown"


def test_get_git_commit_returns_unknown_on_malformed_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _run(*args, **kwargs):
        return _CompletedProcess(stdout="not a hex sha\n")

    monkeypatch.setattr(
        "PHX2.stage18._git.subprocess", _StubSubprocess(_run)
    )
    assert get_git_commit() == "unknown"


def test_get_git_commit_returns_unknown_on_short_sha(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Short (7-char) SHA is rejected; the helper insists on the
    full 40-char form so the manifest carries an unambiguous
    reference."""

    def _run(*args, **kwargs):
        return _CompletedProcess(stdout="abc1234\n")

    monkeypatch.setattr(
        "PHX2.stage18._git.subprocess", _StubSubprocess(_run)
    )
    assert get_git_commit() == "unknown"


def test_get_git_commit_returns_unknown_on_uppercase_sha(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The helper insists on lowercase hex (git's default
    output). An uppercase 40-char string is treated as malformed."""

    def _run(*args, **kwargs):
        return _CompletedProcess(stdout=("A" * 40) + "\n")

    monkeypatch.setattr(
        "PHX2.stage18._git.subprocess", _StubSubprocess(_run)
    )
    assert get_git_commit() == "unknown"


def test_get_git_commit_returns_sha_when_subprocess_produces_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_sha = "a" * 40

    def _run(*args, **kwargs):
        return _CompletedProcess(stdout=fake_sha + "\n")

    monkeypatch.setattr(
        "PHX2.stage18._git.subprocess", _StubSubprocess(_run)
    )
    assert get_git_commit() == fake_sha


def test_get_git_commit_strips_trailing_whitespace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_sha = "0123456789abcdef" * 2 + "abcdefab"
    assert len(fake_sha) == 40

    def _run(*args, **kwargs):
        # Surround with whitespace; helper must strip before regex.
        return _CompletedProcess(stdout=f"  {fake_sha}  \n")

    monkeypatch.setattr(
        "PHX2.stage18._git.subprocess", _StubSubprocess(_run)
    )
    assert get_git_commit() == fake_sha

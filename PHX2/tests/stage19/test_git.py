"""Stage 19 _git.py tests.

Mocks ``subprocess.run`` to exercise every return path of
``get_git_commit()`` -- success on a valid SHA, success-but-
malformed, and each documented exception class.
"""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

from PHX2.stage19._git import get_git_commit


_VALID_SHA: str = "0123456789abcdef0123456789abcdef01234567"


def _mock_result(stdout: str) -> MagicMock:
    m = MagicMock()
    m.stdout = stdout
    m.returncode = 0
    return m


# ===========================================================================
# Success path
# ===========================================================================


class TestGetGitCommitSuccess:
    def test_returns_40_hex_lowercase_when_git_succeeds(self) -> None:
        with patch(
            "PHX2.stage19._git.subprocess.run",
            return_value=_mock_result(_VALID_SHA + "\n"),
        ):
            assert get_git_commit() == _VALID_SHA

    def test_strips_trailing_whitespace_from_stdout(self) -> None:
        with patch(
            "PHX2.stage19._git.subprocess.run",
            return_value=_mock_result(_VALID_SHA + "  \n\n"),
        ):
            assert get_git_commit() == _VALID_SHA

    def test_strips_leading_whitespace_too(self) -> None:
        with patch(
            "PHX2.stage19._git.subprocess.run",
            return_value=_mock_result("  " + _VALID_SHA + "\n"),
        ):
            assert get_git_commit() == _VALID_SHA


# ===========================================================================
# Exception paths -- each maps to "unknown"
# ===========================================================================


class TestGetGitCommitExceptionPaths:
    def test_file_not_found_returns_unknown(self) -> None:
        with patch(
            "PHX2.stage19._git.subprocess.run",
            side_effect=FileNotFoundError("git not on PATH"),
        ):
            assert get_git_commit() == "unknown"

    def test_called_process_error_returns_unknown(self) -> None:
        with patch(
            "PHX2.stage19._git.subprocess.run",
            side_effect=subprocess.CalledProcessError(
                returncode=128, cmd=["git", "rev-parse", "HEAD"]
            ),
        ):
            assert get_git_commit() == "unknown"

    def test_timeout_expired_returns_unknown(self) -> None:
        with patch(
            "PHX2.stage19._git.subprocess.run",
            side_effect=subprocess.TimeoutExpired(
                cmd=["git", "rev-parse", "HEAD"], timeout=5
            ),
        ):
            assert get_git_commit() == "unknown"

    def test_oserror_returns_unknown(self) -> None:
        with patch(
            "PHX2.stage19._git.subprocess.run",
            side_effect=OSError("permission denied"),
        ):
            assert get_git_commit() == "unknown"

    def test_generic_exception_returns_unknown(self) -> None:
        with patch(
            "PHX2.stage19._git.subprocess.run",
            side_effect=RuntimeError("something else"),
        ):
            assert get_git_commit() == "unknown"


# ===========================================================================
# Malformed-output paths -- each maps to "unknown"
# ===========================================================================


class TestGetGitCommitMalformedOutput:
    def test_short_sha_returns_unknown(self) -> None:
        with patch(
            "PHX2.stage19._git.subprocess.run",
            return_value=_mock_result("abc1234\n"),
        ):
            assert get_git_commit() == "unknown"

    def test_uppercase_sha_returns_unknown(self) -> None:
        with patch(
            "PHX2.stage19._git.subprocess.run",
            return_value=_mock_result(_VALID_SHA.upper() + "\n"),
        ):
            assert get_git_commit() == "unknown"

    def test_non_hex_chars_returns_unknown(self) -> None:
        # 40 chars but contains 'z'
        bad = "z" * 40
        with patch(
            "PHX2.stage19._git.subprocess.run",
            return_value=_mock_result(bad + "\n"),
        ):
            assert get_git_commit() == "unknown"

    def test_empty_output_returns_unknown(self) -> None:
        with patch(
            "PHX2.stage19._git.subprocess.run",
            return_value=_mock_result(""),
        ):
            assert get_git_commit() == "unknown"

    def test_whitespace_only_output_returns_unknown(self) -> None:
        with patch(
            "PHX2.stage19._git.subprocess.run",
            return_value=_mock_result("  \n\t\n"),
        ):
            assert get_git_commit() == "unknown"

    def test_too_long_string_returns_unknown(self) -> None:
        with patch(
            "PHX2.stage19._git.subprocess.run",
            return_value=_mock_result(_VALID_SHA + "abc\n"),
        ):
            assert get_git_commit() == "unknown"

    def test_mixed_case_returns_unknown(self) -> None:
        # Mixed case: still 40 hex but not all lowercase
        mixed = "0123456789ABCdef0123456789abcdef01234567"
        with patch(
            "PHX2.stage19._git.subprocess.run",
            return_value=_mock_result(mixed + "\n"),
        ):
            assert get_git_commit() == "unknown"

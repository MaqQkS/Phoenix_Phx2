"""Stage 26 test conftest -- workaround for a Windows tmpdir ACL issue.

The existing ``%LOCALAPPDATA%\\Temp\\pytest-of-BalaC`` directory on
this Windows environment carries restrictive ACLs that deny pytest's
default ``tmp_path`` fixture's `os.scandir` cleanup pass and cause
``PermissionError: [WinError 5]`` on every test that uses
``tmp_path``. The same environment issue has been observed in
Stage 25.6 writer / runner tests; it is NOT a Stage 26.1
regression.

This conftest overrides ``tmp_path`` for the Stage 26 test suite
with a fresh ``tempfile.mkdtemp(prefix="phx2_stage26_")`` directory
that lives under the system temp root but does not inherit the
broken ACL. The fixture cleans the directory up after the test.
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from typing import Iterator

import pytest


@pytest.fixture()
def tmp_path() -> Iterator[Path]:
    """Per-test temporary directory created under the system temp root.

    Bypasses pytest's ``pytest-of-<user>/`` tmpdir manager (which on
    this Windows environment trips a ``PermissionError`` during its
    cleanup-scan pass). The directory is removed after the test
    completes.
    """
    base = Path(tempfile.mkdtemp(prefix="phx2_stage26_"))
    try:
        yield base
    finally:
        shutil.rmtree(base, ignore_errors=True)

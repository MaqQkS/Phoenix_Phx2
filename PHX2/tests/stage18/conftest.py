"""Stage 18 pytest configuration.

IMPORTANT -- Windows ACL workaround (mirrors Stage 16A/16B/17):

Every Stage 18 test run MUST be invoked with a fresh ``--basetemp``
path, e.g.::

    py -3 -m pytest -q --basetemp=./.pytest_basetmp_stage18_p1 \\
        PHX2/tests/stage18/

The default pytest tmp directory under
``%LOCALAPPDATA%\\Temp\\pytest-of-<user>`` accumulates restrictive
ACLs that even ``Remove-Item -Force`` cannot always clear. Each
phase uses a distinct ``--basetemp`` so the run starts on a clean
slate.

Stage 17 input contract:

  * Stage 18 reads a completed Stage 17 output directory.
  * For Phase 18.1 tests the directory is hand-built by helpers in
    ``PHX2.tests.stage18.fixtures.stage17_outputs``; the production
    Stage 17 pipeline is never invoked from these tests, and the
    helpers do not import ``PHX2.stage17`` either.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from PHX2.tests.stage18.fixtures.stage17_outputs import (
    write_minimal_valid_stage17_output,
)


@pytest.fixture
def minimal_stage17_input_dir(tmp_path: Path) -> Path:
    """Return a fresh tmp directory populated with a minimal valid
    Stage 17 output (all five required artifacts present)."""

    target = tmp_path / "stage17_run"
    write_minimal_valid_stage17_output(target)
    return target

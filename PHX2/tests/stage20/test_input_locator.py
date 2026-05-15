"""Tests for Stage 20 input locator functions (20.1.B).

``locate_stage18_run`` and ``locate_stage19_run`` raise E2001 /
E2002 on missing manifests. Their happy-path returns the typed
Stage18RunFiles / Stage19RunFiles tuples.
"""

from __future__ import annotations

import pytest

from PHX2.stage20.errors import Stage20ValidationError
from PHX2.stage20.input_validators import (
    Stage18RunFiles,
    Stage19RunFiles,
    locate_stage18_run,
    locate_stage19_run,
)
from PHX2.tests.stage20.fixtures.stage18_outputs import (
    write_minimal_stage18_dir,
)
from PHX2.tests.stage20.fixtures.stage19_outputs import (
    write_minimal_stage19_dir,
)


def test_locate_stage18_returns_typed_handle(tmp_path):
    s18 = tmp_path / "stage18"
    write_minimal_stage18_dir(s18)

    files = locate_stage18_run(s18)

    assert isinstance(files, Stage18RunFiles)
    assert files.manifest_path.exists()
    assert files.review_matrix_path.exists()


def test_locate_stage18_raises_e2001_when_manifest_missing(tmp_path):
    s18 = tmp_path / "stage18"
    s18.mkdir()  # exists but empty

    with pytest.raises(Stage20ValidationError) as exc_info:
        locate_stage18_run(s18)
    assert exc_info.value.code == "E2001"


def test_locate_stage19_returns_typed_handle(tmp_path):
    s18 = tmp_path / "stage18"
    s19 = tmp_path / "stage19"
    write_minimal_stage18_dir(s18)
    write_minimal_stage19_dir(s19, stage18_dir=s18)

    files = locate_stage19_run(s19)

    assert isinstance(files, Stage19RunFiles)
    assert files.manifest_path.exists()
    assert files.ledger_path.exists()


def test_locate_stage19_raises_e2002_when_manifest_missing(tmp_path):
    s19 = tmp_path / "stage19"
    s19.mkdir()

    with pytest.raises(Stage20ValidationError) as exc_info:
        locate_stage19_run(s19)
    assert exc_info.value.code == "E2002"

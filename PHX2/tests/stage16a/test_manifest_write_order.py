"""Phase 8: manifest is written LAST -- its mtime is >= every other output file's mtime."""

from __future__ import annotations

from pathlib import Path

from PHX2.stage16a.cli import (
    MANIFEST_FILENAME,
    RUN_LOG_FILENAME,
    RUNTIME_POLICY_FILENAME,
    main as cli_main,
)
from PHX2.tests.stage16a.fixtures.builders import build_stage15_run_dir


def test_manifest_mtime_is_latest_in_output_dir(tmp_path: Path) -> None:
    s15 = build_stage15_run_dir(tmp_path / "s15")
    out = tmp_path / "out"
    rc = cli_main(
        [
            "--stage15-run-path", str(s15),
            "--output-dir", str(out),
        ]
    )
    assert rc == 0

    manifest_mtime = (out / MANIFEST_FILENAME).stat().st_mtime
    for fname in (RUNTIME_POLICY_FILENAME, RUN_LOG_FILENAME):
        other = (out / fname).stat().st_mtime
        assert manifest_mtime >= other, (
            f"manifest mtime {manifest_mtime} < {fname} mtime {other}"
        )


def test_only_three_files_in_output_dir(tmp_path: Path) -> None:
    s15 = build_stage15_run_dir(tmp_path / "s15")
    out = tmp_path / "out"
    cli_main(
        [
            "--stage15-run-path", str(s15),
            "--output-dir", str(out),
        ]
    )
    names = {p.name for p in out.iterdir()}
    assert names == {MANIFEST_FILENAME, RUNTIME_POLICY_FILENAME, RUN_LOG_FILENAME}

"""Phase 18.3 non-mutation tests.

Stage 18 must:
  * Leave every file under ``--stage17-input-dir`` byte-for-byte
    unchanged (verified via SHA-256 before and after the run).
  * Create no files outside ``--output-dir``.
  * Not create any file under ``PHX2/stage18_runs/`` in the repo.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from PHX2.stage18.cli import EXIT_OK, main


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _dir_file_hashes(d: Path) -> dict[str, str]:
    return {
        p.relative_to(d).as_posix(): _file_sha256(p)
        for p in d.rglob("*") if p.is_file()
    }


def test_stage17_input_files_unchanged_after_stage18_run(
    minimal_stage17_input_dir: Path, tmp_path: Path,
) -> None:
    """SHA-256 of every Stage 17 input file is identical before
    and after Stage 18 runs."""

    pre = _dir_file_hashes(minimal_stage17_input_dir)

    rc = main([
        "--stage17-input-dir", str(minimal_stage17_input_dir),
        "--output-dir", str(tmp_path / "stage18_out"),
        "--quiet",
    ])
    assert rc == EXIT_OK

    post = _dir_file_hashes(minimal_stage17_input_dir)
    assert pre == post


def test_no_files_created_outside_output_dir(
    minimal_stage17_input_dir: Path, tmp_path: Path,
) -> None:
    """Snapshot of ``tmp_path`` before and after the run: every
    newly-appearing path must be either ``output_dir`` itself or
    nested inside it."""

    out_dir = tmp_path / "stage18_out"
    pre_paths = {p for p in tmp_path.rglob("*")}

    rc = main([
        "--stage17-input-dir", str(minimal_stage17_input_dir),
        "--output-dir", str(out_dir),
        "--quiet",
    ])
    assert rc == EXIT_OK

    post_paths = {p for p in tmp_path.rglob("*")}
    new_paths = post_paths - pre_paths

    for p in new_paths:
        assert p == out_dir or out_dir in p.parents, (
            f"Stage 18 created a path outside --output-dir: {p}"
        )


def test_no_files_created_under_repo_stage18_runs(
    minimal_stage17_input_dir: Path, tmp_path: Path,
) -> None:
    """``PHX2/stage18_runs/`` in the repo must remain untouched.

    The convention (mirroring Stage 17's ``PHX2/stage17_runs/``)
    is that local Stage 18 run output goes to caller-supplied
    paths -- never to a fixed location in the repo.
    """

    repo_stage18_runs = (
        Path(__file__).resolve().parents[3] / "PHX2" / "stage18_runs"
    )
    pre_existed = repo_stage18_runs.exists()

    rc = main([
        "--stage17-input-dir", str(minimal_stage17_input_dir),
        "--output-dir", str(tmp_path / "stage18_out"),
        "--quiet",
    ])
    assert rc == EXIT_OK

    if not pre_existed:
        assert not repo_stage18_runs.exists(), (
            f"Stage 18 wrote to forbidden repo path: {repo_stage18_runs}"
        )

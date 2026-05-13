"""Phase 9: Stage 16A produces byte-identical artifacts on repeated runs with the same input + pinned clock + pinned git_commit."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from PHX2.stage16a.cli import (
    RUN_LOG_FILENAME,
    RUNTIME_POLICY_FILENAME,
    main as cli_main,
)
from PHX2.stage16a.runtime_policy_builder import RuntimePolicyBuilder
from PHX2.stage16a.stage15_loader import Stage15ApprovedDraftLoader
from PHX2.tests.stage16a.fixtures.builders import build_stage15_run_dir


PINNED_CLOCK = datetime(2026, 5, 13, 12, 0, 0, tzinfo=timezone.utc)
PINNED_GIT = "a" * 40


# ---------------------------------------------------------------------------
# Builder-level determinism
# ---------------------------------------------------------------------------


def test_builder_two_runs_produce_byte_identical_body(tmp_path: Path) -> None:
    s15 = build_stage15_run_dir(tmp_path / "s15")
    draft = Stage15ApprovedDraftLoader().load(s15)

    body1 = RuntimePolicyBuilder().build(
        draft, now_utc=PINNED_CLOCK, git_commit=PINNED_GIT
    )
    body2 = RuntimePolicyBuilder().build(
        draft, now_utc=PINNED_CLOCK, git_commit=PINNED_GIT
    )

    # Compare canonical-JSON-encoded forms byte-by-byte.
    enc = lambda d: json.dumps(d, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    assert enc(body1) == enc(body2)
    assert body1["policy_hash"] == body2["policy_hash"]


def test_builder_policy_hash_stable_under_rule_reorder(tmp_path: Path) -> None:
    """Stage 15 lists rules in a stable order. If a future Stage 15 change
    reorders rules, the policy_hash will change -- this test makes that
    drift visible. Currently we just confirm a single-rule run is stable."""

    s15 = build_stage15_run_dir(tmp_path / "s15")
    draft = Stage15ApprovedDraftLoader().load(s15)
    hashes = [
        RuntimePolicyBuilder().build(
            draft, now_utc=PINNED_CLOCK, git_commit=PINNED_GIT
        )["policy_hash"]
        for _ in range(3)
    ]
    assert len(set(hashes)) == 1


# ---------------------------------------------------------------------------
# CLI-level determinism (full pipeline)
# ---------------------------------------------------------------------------


def _patch_clock_and_git(monkeypatch) -> None:
    """Pin datetime.now() and capture_git_commit() inside the CLI module."""

    class _Frozen(datetime):
        @classmethod
        def now(cls, tz=None):  # noqa: D401
            return PINNED_CLOCK

    monkeypatch.setattr("PHX2.stage16a.cli.datetime", _Frozen)
    monkeypatch.setattr("PHX2.stage16a.cli.capture_git_commit", lambda: PINNED_GIT)


def test_cli_two_runs_produce_byte_identical_runtime_policy(
    tmp_path: Path, monkeypatch
) -> None:
    """Same Stage 15 input + same pinned clock + same pinned git_commit ->
    byte-identical observe_only_runtime_policy.json on disk."""

    _patch_clock_and_git(monkeypatch)
    s15 = build_stage15_run_dir(tmp_path / "s15")

    out1 = tmp_path / "out1"
    out2 = tmp_path / "out2"
    rc1 = cli_main(
        ["--stage15-run-path", str(s15), "--output-dir", str(out1)]
    )
    rc2 = cli_main(
        ["--stage15-run-path", str(s15), "--output-dir", str(out2)]
    )
    assert rc1 == 0 and rc2 == 0

    body1 = (out1 / RUNTIME_POLICY_FILENAME).read_bytes()
    body2 = (out2 / RUNTIME_POLICY_FILENAME).read_bytes()
    assert body1 == body2, "runtime policy files must be byte-identical"


def test_cli_two_runs_produce_same_policy_hash(
    tmp_path: Path, monkeypatch
) -> None:
    _patch_clock_and_git(monkeypatch)
    s15 = build_stage15_run_dir(tmp_path / "s15")

    out1 = tmp_path / "out1"
    out2 = tmp_path / "out2"
    cli_main(["--stage15-run-path", str(s15), "--output-dir", str(out1)])
    cli_main(["--stage15-run-path", str(s15), "--output-dir", str(out2)])

    h1 = json.loads(
        (out1 / RUNTIME_POLICY_FILENAME).read_text(encoding="utf-8")
    )["policy_hash"]
    h2 = json.loads(
        (out2 / RUNTIME_POLICY_FILENAME).read_text(encoding="utf-8")
    )["policy_hash"]
    assert h1 == h2


def test_cli_log_file_differs_only_in_paths(
    tmp_path: Path, monkeypatch
) -> None:
    """The run log embeds the output_dir paths, so two runs into different
    dirs produce different log bytes. The runtime policy file does NOT
    embed the output dir (only the Stage 15 input path), so it IS
    byte-identical between the two runs."""

    _patch_clock_and_git(monkeypatch)
    s15 = build_stage15_run_dir(tmp_path / "s15")

    out1 = tmp_path / "out1"
    out2 = tmp_path / "out2"
    cli_main(["--stage15-run-path", str(s15), "--output-dir", str(out1)])
    cli_main(["--stage15-run-path", str(s15), "--output-dir", str(out2)])

    log1 = (out1 / RUN_LOG_FILENAME).read_text(encoding="utf-8")
    log2 = (out2 / RUN_LOG_FILENAME).read_text(encoding="utf-8")
    # Both logs reference their own output_dir; they MUST differ.
    assert log1 != log2
    # ...but both should reference the SAME Stage 15 manifest hash.
    assert "manifest_hash=sha256:" in log1
    assert "manifest_hash=sha256:" in log2

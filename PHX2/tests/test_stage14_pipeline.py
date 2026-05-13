"""Stage 14 end-to-end pipeline tests.

Spins up paired Stage 12 + Stage 13 fixtures and asserts on:
  * All 13 output artifacts created.
  * manifest carries safe_for_live=false and runtime_consumable=false.
  * shadow_policy_rules.json carries the same flags.
  * Byte-identical reruns produce identical artifact bytes.
  * Stage 12 / Stage 13 input files are not mutated.
  * --stage12-run override is honored.
  * --stage12-run override with mismatched hash fails loudly.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from PHX2.stage14.loader import Stage14IncompatibleStage12
from PHX2.stage14.pipeline import run as run_pipeline
from PHX2.stage14.writer import (
    BLOCKED_DECISIONS_FILENAME,
    DECISION_DIFF_FILENAME,
    EXCLUDED_RECOMMENDATIONS_FILENAME,
    IMPACT_BY_FILTER_FILENAME,
    IMPACT_BY_RULE_FILENAME,
    IMPACT_BY_TIER_FILENAME,
    MANIFEST_FILENAME,
    REPLAY_RESULTS_FILENAME,
    REVIEW_MD_FILENAME,
    RUN_LOG_FILENAME,
    SAVED_NOISE_FILENAME,
    SHADOW_POLICY_RULES_FILENAME,
    WOULD_HAVE_BLOCKED_WINNERS_FILENAME,
)
from PHX2.tests.fixtures.stage14.stage14_fixture_writer import (
    Stage12LongRow,
    Stage13CandidateRow,
    build_default_bundle,
    write_stage12_run,
)


_NOW = datetime(2026, 5, 12, 12, 0, 0, tzinfo=timezone.utc)


_ARTIFACT_FILENAMES = (
    SHADOW_POLICY_RULES_FILENAME,
    EXCLUDED_RECOMMENDATIONS_FILENAME,
    REPLAY_RESULTS_FILENAME,
    DECISION_DIFF_FILENAME,
    BLOCKED_DECISIONS_FILENAME,
    WOULD_HAVE_BLOCKED_WINNERS_FILENAME,
    SAVED_NOISE_FILENAME,
    IMPACT_BY_TIER_FILENAME,
    IMPACT_BY_RULE_FILENAME,
    IMPACT_BY_FILTER_FILENAME,
    REVIEW_MD_FILENAME,
    RUN_LOG_FILENAME,
    MANIFEST_FILENAME,
)


def _sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    hasher.update(path.read_bytes())
    return hasher.hexdigest()


def test_all_thirteen_artifacts_present(tmp_path: Path) -> None:
    bundle = build_default_bundle(tmp_path)
    result = run_pipeline(
        stage13_run_path=bundle.stage13_run_path,
        output_root=tmp_path / "stage14_runs",
        now_utc=_NOW,
    )
    for name in _ARTIFACT_FILENAMES:
        assert (result.output_dir / name).exists(), name


def test_manifest_safe_flags(tmp_path: Path) -> None:
    bundle = build_default_bundle(tmp_path)
    result = run_pipeline(
        stage13_run_path=bundle.stage13_run_path,
        output_root=tmp_path / "stage14_runs",
        now_utc=_NOW,
    )
    on_disk = json.loads(
        (result.output_dir / MANIFEST_FILENAME).read_text(encoding="utf-8")
    )
    assert on_disk["safe_for_live_policy_consumption"] is False
    assert on_disk["runtime_consumable"] is False
    assert on_disk["allowed_actions"] == ["SIMULATED_BLOCK"]


def test_shadow_policy_rules_safe_flags(tmp_path: Path) -> None:
    bundle = build_default_bundle(tmp_path)
    result = run_pipeline(
        stage13_run_path=bundle.stage13_run_path,
        output_root=tmp_path / "stage14_runs",
        now_utc=_NOW,
    )
    rules_payload = json.loads(
        (result.output_dir / SHADOW_POLICY_RULES_FILENAME).read_text(encoding="utf-8")
    )
    assert rules_payload["runtime_consumable"] is False
    assert rules_payload["allowed_actions"] == ["SIMULATED_BLOCK"]


def test_reruns_produce_byte_identical_artifacts(tmp_path: Path) -> None:
    bundle = build_default_bundle(tmp_path)
    # Two runs into separate output roots so the directory names differ
    # but the artifact contents are byte-identical.
    r1 = run_pipeline(
        stage13_run_path=bundle.stage13_run_path,
        output_root=tmp_path / "out1",
        now_utc=_NOW,
    )
    r2 = run_pipeline(
        stage13_run_path=bundle.stage13_run_path,
        output_root=tmp_path / "out2",
        now_utc=_NOW,
    )
    for name in _ARTIFACT_FILENAMES:
        # The run log carries a timestamp from now_utc; with the
        # pinned _NOW the bytes still match.
        f1 = r1.output_dir / name
        f2 = r2.output_dir / name
        assert f1.read_bytes() == f2.read_bytes(), name


def test_stage_inputs_unchanged(tmp_path: Path) -> None:
    bundle = build_default_bundle(tmp_path)
    pre_hashes = {
        p: _sha256(p)
        for p in (
            bundle.stage13_run_path / "manifest.json",
            bundle.stage13_run_path / "candidate_recommendations.csv",
            bundle.stage12_run_path / "manifest.json",
            bundle.stage12_run_path / "decision_filter_outcome_long.csv",
        )
    }
    run_pipeline(
        stage13_run_path=bundle.stage13_run_path,
        output_root=tmp_path / "stage14_runs",
        now_utc=_NOW,
    )
    post_hashes = {p: _sha256(p) for p in pre_hashes}
    assert pre_hashes == post_hashes


def test_stage12_override_with_correct_hash_succeeds(tmp_path: Path) -> None:
    bundle = build_default_bundle(tmp_path)
    result = run_pipeline(
        stage13_run_path=bundle.stage13_run_path,
        stage12_run_path=bundle.stage12_run_path,
        output_root=tmp_path / "stage14_runs",
        now_utc=_NOW,
    )
    assert result.rule_count == 1


def test_stage12_override_with_mismatched_hash_fails(tmp_path: Path) -> None:
    bundle = build_default_bundle(tmp_path)
    # Build a SECOND Stage 12 directory with different content.
    different_stage12 = write_stage12_run(
        tmp_path / "stage12_other",
        long_rows=[
            Stage12LongRow(alert_decision_id="d_other"),
        ],
        run_id="20260601T000000Z_other0",
    )
    with pytest.raises(Stage14IncompatibleStage12, match="hash mismatch"):
        run_pipeline(
            stage13_run_path=bundle.stage13_run_path,
            stage12_run_path=different_stage12,
            output_root=tmp_path / "stage14_runs",
            now_utc=_NOW,
        )


def test_default_stage12_path_with_tampered_manifest_fails(tmp_path: Path) -> None:
    """Stage 14 must verify the Stage 12 manifest hash even when
    using the default path from Stage 13's manifest. If the Stage 12
    manifest is touched / swapped / rewritten between Stage 13's run
    and Stage 14's run, the hash recorded in the Stage 13 manifest
    will no longer match the actual Stage 12 manifest bytes -- and
    Stage 14 must hard-fail rather than replay against drifted input.
    """

    bundle = build_default_bundle(tmp_path)
    # Tamper with the Stage 12 manifest in place; its sha256 now
    # diverges from what Stage 13 recorded.
    stage12_manifest = bundle.stage12_run_path / "manifest.json"
    payload = json.loads(stage12_manifest.read_text(encoding="utf-8"))
    payload["created_at"] = "2099-01-01T00:00:00+00:00"
    stage12_manifest.write_text(
        json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8"
    )

    with pytest.raises(Stage14IncompatibleStage12, match="hash mismatch"):
        # Default branch: no --stage12-run override, but the hash
        # check must still fire against the tampered manifest.
        run_pipeline(
            stage13_run_path=bundle.stage13_run_path,
            output_root=tmp_path / "stage14_runs",
            now_utc=_NOW,
        )


def test_default_stage12_path_with_matching_hash_succeeds(tmp_path: Path) -> None:
    """Companion to the tampered-manifest test: when the default
    Stage 12 manifest still matches Stage 13's recorded hash, the
    run proceeds and produces all artifacts."""

    bundle = build_default_bundle(tmp_path)
    result = run_pipeline(
        stage13_run_path=bundle.stage13_run_path,
        output_root=tmp_path / "stage14_runs",
        now_utc=_NOW,
    )
    on_disk = json.loads(
        (result.output_dir / MANIFEST_FILENAME).read_text(encoding="utf-8")
    )
    assert on_disk["stage12_manifest_hash"] == bundle.stage12_manifest_hash


def test_replay_aggregates_block_counts(tmp_path: Path) -> None:
    bundle = build_default_bundle(
        tmp_path,
        long_rows=[
            Stage12LongRow(
                alert_decision_id="winner",
                primary_outcome_hit_2x_24h=True,
            ),
            Stage12LongRow(
                alert_decision_id="loser",
                primary_outcome_hit_2x_24h=False,
            ),
            Stage12LongRow(
                alert_decision_id="unknown",
                has_primary_outcome=False,
                primary_outcome_hit_2x_24h=None,
            ),
        ],
    )
    result = run_pipeline(
        stage13_run_path=bundle.stage13_run_path,
        output_root=tmp_path / "stage14_runs",
        now_utc=_NOW,
    )
    assert result.n_live_decisions == 3
    assert result.n_simulated_blocks == 3


def test_excluded_recommendations_accounted_for(tmp_path: Path) -> None:
    bundle = build_default_bundle(
        tmp_path,
        candidate_rows=[
            Stage13CandidateRow(),  # eligible
            Stage13CandidateRow(
                cohort_id="b@v1[threshold=v1]:c",
                action_class="HOLD_OBSERVE_ONLY",
            ),
            Stage13CandidateRow(
                cohort_id="c@v1[threshold=v1]:d",
                tier_scope="overall",
            ),
        ],
    )
    result = run_pipeline(
        stage13_run_path=bundle.stage13_run_path,
        output_root=tmp_path / "stage14_runs",
        now_utc=_NOW,
    )
    assert result.rule_count == 1
    assert result.excluded_count == 2

    excluded_csv = (result.output_dir / EXCLUDED_RECOMMENDATIONS_FILENAME).read_text(
        encoding="utf-8"
    )
    assert "HOLD_OBSERVE_ONLY" in excluded_csv
    assert "not_advance_candidate" in excluded_csv
    assert "tier_scope_overall" in excluded_csv


def test_manifest_written_after_other_artifacts(tmp_path: Path) -> None:
    """If we simulate a write failure on the manifest, the other
    artifacts should still exist -- the manifest being last is what
    makes a partial run identifiable."""

    bundle = build_default_bundle(tmp_path)
    result = run_pipeline(
        stage13_run_path=bundle.stage13_run_path,
        output_root=tmp_path / "stage14_runs",
        now_utc=_NOW,
    )
    manifest_mtime = (result.output_dir / MANIFEST_FILENAME).stat().st_mtime_ns
    for name in _ARTIFACT_FILENAMES:
        if name == MANIFEST_FILENAME:
            continue
        other_mtime = (result.output_dir / name).stat().st_mtime_ns
        # mtime is OS-level and may have low resolution; allow equality
        # but reject "manifest is older than another artifact".
        assert manifest_mtime >= other_mtime, name


def test_output_is_inside_run_directory_only(tmp_path: Path) -> None:
    bundle = build_default_bundle(tmp_path)
    output_root = tmp_path / "stage14_runs"
    pre_other_files = {p for p in tmp_path.rglob("*") if p.is_file()}
    result = run_pipeline(
        stage13_run_path=bundle.stage13_run_path,
        output_root=output_root,
        now_utc=_NOW,
    )
    post_other_files = {p for p in tmp_path.rglob("*") if p.is_file()}
    new_files = post_other_files - pre_other_files
    assert all(
        result.output_dir in f.parents or f.parent == result.output_dir
        for f in new_files
    )


def test_no_eligible_candidates_produces_zero_rules(tmp_path: Path) -> None:
    bundle = build_default_bundle(
        tmp_path,
        candidate_rows=[
            Stage13CandidateRow(action_class="HOLD_OBSERVE_ONLY"),
        ],
    )
    result = run_pipeline(
        stage13_run_path=bundle.stage13_run_path,
        output_root=tmp_path / "stage14_runs",
        now_utc=_NOW,
    )
    assert result.rule_count == 0
    assert result.excluded_count == 1
    # Replay still ran; with no rules every decision is SIMULATED_PASS.
    assert result.n_simulated_blocks == 0

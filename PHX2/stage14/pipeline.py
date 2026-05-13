"""Stage 14 pipeline orchestrator.

Pure-ish ``run(...)`` that loads, translates, replays, aggregates,
and writes a Stage 14 run. The function is deterministic given a
pinned ``now_utc``: the output directory's name, the manifest
timestamp, and every artifact's bytes are reproducible.

The orchestrator does NOT shell out for the git fingerprint -- the
CLI captures the git commit (subprocess at the I/O boundary) and
passes it through here. This mirrors Stage 12's m-3 remediation and
Stage 13's identical pattern.

The orchestrator opens no DB connection, makes no network call, and
writes exclusively inside ``<output-root>/<UTC_timestamp>/``. The
manifest is written LAST.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from PHX2.stage14.loader import (
    STAGE13_CANDIDATE_CSV_COLUMNS,
    Stage12Run,
    Stage13Run,
    load_stage12_run,
    load_stage13_run,
    resolve_stage12_run_path,
)
from PHX2.stage14.metrics import compute_impact
from PHX2.stage14.replay import replay
from PHX2.stage14.rules import translate_recommendations
from PHX2.stage14.types import (
    PRIMARY_OUTCOME_METRIC,
    RUNTIME_CONSUMABLE,
    SAFE_FOR_LIVE_POLICY_CONSUMPTION,
    STAGE14_SCHEMA_VERSION,
    STAGE14_VERSION,
)
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
    write_blocked_decisions,
    write_decision_diff,
    write_excluded_recommendations,
    write_impact_by_filter,
    write_impact_by_rule,
    write_impact_by_tier,
    write_manifest,
    write_replay_results,
    write_review_markdown,
    write_run_log,
    write_saved_noise,
    write_shadow_policy_rules,
    write_would_have_blocked_winners,
)


@dataclass(frozen=True)
class Stage14RunResult:
    """Result of one Stage 14 run."""

    output_dir: Path
    manifest: dict[str, Any]
    rule_count: int
    excluded_count: int
    n_live_decisions: int
    n_simulated_blocks: int


def _format_run_timestamp(now_utc: datetime) -> str:
    """Render UTC timestamp as ``YYYYMMDDTHHMMSSZ`` (deterministic).

    Same format Stage 13 uses; collisions on a single-second boundary
    are handled at directory-creation time by mkdir(exist_ok=False).
    """

    if now_utc.tzinfo is None:
        now_utc = now_utc.replace(tzinfo=timezone.utc)
    utc = now_utc.astimezone(timezone.utc)
    return utc.strftime("%Y%m%dT%H%M%SZ")


def _create_run_dir(output_root: Path, now_utc: datetime) -> Path:
    timestamp = _format_run_timestamp(now_utc)
    run_dir = Path(output_root) / timestamp
    run_dir.mkdir(parents=True, exist_ok=False)
    return run_dir


# ---------------------------------------------------------------------------
# Manifest assembly
# ---------------------------------------------------------------------------


def _build_manifest_dict(
    *,
    stage13: Stage13Run,
    stage12: Stage12Run,
    stage12_run_path: Path,
    now_utc: datetime,
    rule_count: int,
    excluded_count: int,
    n_live_decisions: int,
    n_simulated_blocks: int,
    overall_warning_flags: tuple[str, ...],
    git_commit: str | None,
) -> dict[str, Any]:
    return {
        "stage14_version": STAGE14_VERSION,
        "stage14_schema_version": STAGE14_SCHEMA_VERSION,
        "run_timestamp_utc": now_utc.astimezone(timezone.utc).isoformat(),
        "safe_for_live_policy_consumption": SAFE_FOR_LIVE_POLICY_CONSUMPTION,
        "runtime_consumable": RUNTIME_CONSUMABLE,
        "allowed_actions": ["SIMULATED_BLOCK"],
        "primary_outcome_metric": PRIMARY_OUTCOME_METRIC,
        "stage13_run_path": str(Path(stage13.manifest_path).parent.resolve()),
        "stage13_manifest_hash": stage13.manifest_hash,
        "stage13_candidate_csv_hash": stage13.candidate_csv_hash,
        "stage13_recommendation_set_version": stage13.manifest.get(
            "recommendation_set_version"
        ),
        "stage12_run_path": str(Path(stage12_run_path).resolve()),
        "stage12_manifest_hash": stage12.manifest_hash,
        "stage12_long_csv_hash": stage12.long_csv_hash,
        "rule_count": rule_count,
        "excluded_count": excluded_count,
        "n_live_decisions": n_live_decisions,
        "n_simulated_blocks": n_simulated_blocks,
        "overall_warning_flags": list(overall_warning_flags),
        "artifact_filenames": sorted(
            [
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
            ]
        ),
        "git_commit": git_commit,
    }


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def run(
    *,
    stage13_run_path: Path,
    output_root: Path,
    stage12_run_path: Path | None = None,
    now_utc: datetime | None = None,
    git_commit: str | None = None,
) -> Stage14RunResult:
    """End-to-end Stage 14 run.

    Inputs:
      stage13_run_path: directory holding the Stage 13 candidate CSV +
        manifest.json.
      output_root: directory under which the dated Stage 14 run
        directory is created.
      stage12_run_path: optional override for the Stage 12 path. When
        None, Stage 13's recorded ``stage12_run_path`` is used. When
        provided, the override's manifest hash must match Stage 13's
        recorded ``stage12_manifest_hash`` or the loader raises.
      now_utc: pinned UTC timestamp for determinism in tests. Defaults
        to ``datetime.now(timezone.utc)`` only when None.
      git_commit: optional git SHA captured by the CLI. Pass None to
        leave the manifest's ``git_commit`` as null.

    Stage 14 opens no DB connection, makes no network call, mutates no
    Stage 12 / Stage 13 artifacts, and writes only inside the
    output run directory. The manifest is written LAST so a partial
    run is always identifiable (no manifest = aborted run).

    Returns ``Stage14RunResult`` describing the produced run.
    """

    stage13_run_path = Path(stage13_run_path)
    output_root = Path(output_root)
    if now_utc is None:
        now_utc = datetime.now(timezone.utc)

    log_lines: list[str] = []
    timestamp_iso = now_utc.astimezone(timezone.utc).isoformat()

    def log(event: str) -> None:
        log_lines.append(f"{timestamp_iso} {event}")

    # 1. Load Stage 13.
    stage13 = load_stage13_run(stage13_run_path)
    log(
        f"loaded Stage 13 manifest ({stage13.manifest_hash}); "
        f"candidate rows={len(stage13.candidate_rows)}"
    )

    # 2. Resolve and load Stage 12.
    resolved_stage12_path, expected_hash = resolve_stage12_run_path(
        stage13_manifest=stage13.manifest,
        override=stage12_run_path,
    )
    stage12 = load_stage12_run(
        resolved_stage12_path, expected_manifest_hash=expected_hash
    )
    log(
        f"loaded Stage 12 manifest ({stage12.manifest_hash}); "
        f"long CSV rows={len(stage12.long_rows)}"
    )

    # 3. Translate Stage 13 rows -> shadow rules + exclusions.
    rules, excluded = translate_recommendations(stage13.candidate_rows)
    total = sum(rule.source_row_count for rule in rules) + len(excluded)
    if total != len(stage13.candidate_rows):
        # Defensive: the invariant docstring on translate_recommendations
        # is that every row maps either to a rule's source list or to
        # one excluded row. A mismatch here would mean a bug in the
        # translator; surface it loudly rather than silently emit a
        # malformed Stage 14 run.
        raise RuntimeError(
            "Stage 14 translator invariant violated: "
            f"sum(source_row_count) + len(excluded) = {total}, "
            f"len(candidate_rows) = {len(stage13.candidate_rows)}"
        )
    log(
        f"translated {len(rules)} shadow rules; "
        f"{len(excluded)} excluded recommendations"
    )

    # 4. Replay.
    replay_rows = replay(rules, stage12.long_rows)
    log(f"replayed {len(replay_rows)} unique decisions")

    # 5. Aggregate impact.
    impact = compute_impact(rules=rules, replay_rows=replay_rows)
    overall = impact.by_tier.get("overall")
    n_live_decisions = overall.n_live_decisions if overall else 0
    n_simulated_blocks = overall.n_simulated_blocks if overall else 0
    log(
        f"computed impact: live={n_live_decisions} "
        f"simulated_blocks={n_simulated_blocks} "
        f"overall_warning_flags={list(impact.overall_warning_flags)}"
    )

    # 6. Create run directory + write artifacts in deterministic order.
    run_dir = _create_run_dir(output_root, now_utc)

    write_shadow_policy_rules(run_dir, list(rules))
    write_excluded_recommendations(
        run_dir, list(excluded), STAGE13_CANDIDATE_CSV_COLUMNS
    )
    write_replay_results(run_dir, list(replay_rows))
    write_decision_diff(run_dir, list(replay_rows))
    write_blocked_decisions(run_dir, list(replay_rows))
    write_would_have_blocked_winners(run_dir, list(replay_rows))
    write_saved_noise(run_dir, list(replay_rows))
    write_impact_by_tier(run_dir, impact.by_tier)
    write_impact_by_rule(run_dir, impact.by_rule, impact.by_tier)
    write_impact_by_filter(run_dir, impact.by_filter)

    manifest_dict = _build_manifest_dict(
        stage13=stage13,
        stage12=stage12,
        stage12_run_path=resolved_stage12_path,
        now_utc=now_utc,
        rule_count=len(rules),
        excluded_count=len(excluded),
        n_live_decisions=n_live_decisions,
        n_simulated_blocks=n_simulated_blocks,
        overall_warning_flags=impact.overall_warning_flags,
        git_commit=git_commit,
    )

    write_review_markdown(
        run_dir,
        manifest_dict=manifest_dict,
        rules=list(rules),
        excluded_count=len(excluded),
        impact=impact,
    )
    log("wrote all artifacts; preparing manifest")
    write_run_log(run_dir, log_lines)

    # Manifest LAST. A partial run never carries a manifest.
    write_manifest(run_dir, manifest_dict)

    return Stage14RunResult(
        output_dir=run_dir,
        manifest=manifest_dict,
        rule_count=len(rules),
        excluded_count=len(excluded),
        n_live_decisions=n_live_decisions,
        n_simulated_blocks=n_simulated_blocks,
    )

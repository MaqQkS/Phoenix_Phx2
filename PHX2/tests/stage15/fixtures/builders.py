"""Stage 15 test fixture builders.

Each builder takes a target directory and writes a minimal but
schema-valid set of Stage 14 artifacts (or an operator review CSV)
that downstream tests can mutate to exercise specific failure paths.

Defaults are chosen so that ``make_stage14_run`` + ``make_operator_csv``
produce a passing clean run when wired to the Stage 15 CLI. Failure
tests mutate one specific field at a time after construction.
"""

from __future__ import annotations

import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _stable_rule_id(prefix: str, *parts: str) -> str:
    """Mint a content-stable rule_id matching Stage 14's pattern.

    Stage 14 uses ``"shadow_rule_" + sha256(canonical)[:12]``. We don't
    need byte-for-byte compatibility here -- we just need a stable id
    that can be referenced by the operator review CSV.
    """

    canonical = "|".join(parts)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:12]
    return f"{prefix}_{digest}"


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return f"sha256:{h.hexdigest()}"


# ---------------------------------------------------------------------------
# Stage 14 run builder
# ---------------------------------------------------------------------------


DEFAULT_RULE_SPECS = (
    {
        "rule_id": "shadow_rule_default_aaaa",
        "tier_scope": "T2",
        "filter_name": "fee_gate",
        "filter_version": "fee_gate_v1_no_bribes",
        "filter_label": "SCAM_LIKELY",
        "threshold_version": "thresholds_v0_observe_only",
        "warning_flags": "small_n_rule;excessive_block_rate",
    },
    {
        "rule_id": "shadow_rule_default_bbbb",
        "tier_scope": "T1",
        "filter_name": "fee_gate",
        "filter_version": "fee_gate_v1_no_bribes",
        "filter_label": "CLEAN",
        "threshold_version": "thresholds_v0_observe_only",
        "warning_flags": "",
    },
)


def make_stage14_run(
    base: Path,
    *,
    name: str = "20260512T120000Z",
    rules: tuple[Mapping[str, Any], ...] | None = None,
    safe_for_live: bool = False,
    runtime_consumable: bool = False,
    schema_version: str = "1.0",
    stage12_manifest_hash: str = "sha256:" + ("a" * 64),
    stage13_manifest_hash: str = "sha256:" + ("b" * 64),
    embedded_stage13_schema_version: str | None = None,
    extra_impact_rows: tuple[Mapping[str, str], ...] = (),
    omit_files: tuple[str, ...] = (),
    rules_doc_override: Mapping[str, Any] | None = None,
    manifest_override: Mapping[str, Any] | None = None,
    impact_columns_override: tuple[str, ...] | None = None,
    impact_rows_override: tuple[Mapping[str, str], ...] | None = None,
) -> Path:
    """Create a Stage 14 run directory under ``base``.

    Returns the run directory path. Override flags let individual tests
    construct invalid inputs without rewriting the whole fixture.

    Defaults reproduce a small, valid Stage 14 run with two rules. One
    rule carries warning_flags ("small_n_rule;excessive_block_rate"),
    the other has none. Together they exercise the override path and
    the no-flags path in approval-time validation.
    """

    rule_specs = rules if rules is not None else DEFAULT_RULE_SPECS
    run_dir = base / name
    run_dir.mkdir(parents=True, exist_ok=False)

    # ----- shadow_policy_rules.json -----
    rules_json_rules = []
    for spec in rule_specs:
        rules_json_rules.append(
            {
                "direction": spec.get("direction", "tighten"),
                "filter_label": spec["filter_label"],
                "filter_name": spec["filter_name"],
                "filter_version": spec["filter_version"],
                "policy_surface": spec.get("policy_surface", "filter_label_blocking"),
                "rule_id": spec["rule_id"],
                "simulated_action": spec.get("simulated_action", "SIMULATED_BLOCK"),
                "source_recommendations": [],
                "source_row_count": 1,
                "threshold_version": spec["threshold_version"],
                "tier_scope": spec["tier_scope"],
            }
        )
    rules_doc: dict[str, Any] = {
        "allowed_actions": ["SIMULATED_BLOCK"],
        "rule_count": len(rules_json_rules),
        "rules": rules_json_rules,
        "runtime_consumable": False,
        "stage14_schema_version": schema_version,
        "stage14_version": "0.1.0",
    }
    if rules_doc_override is not None:
        rules_doc = dict(rules_doc_override)
    if "shadow_policy_rules.json" not in omit_files:
        (run_dir / "shadow_policy_rules.json").write_text(
            json.dumps(rules_doc, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )

    # ----- impact_summary_by_rule.csv -----
    impact_columns = impact_columns_override or (
        "rule_id",
        "policy_surface",
        "tier_scope",
        "filter_name",
        "filter_version",
        "filter_label",
        "threshold_version",
        "simulated_action",
        "direction",
        "n_matched",
        "n_live_decisions_in_tier",
        "n_simulated_blocks",
        "n_blocked_with_primary_outcome",
        "n_blocked_winners_2x",
        "n_blocked_winners_3x",
        "n_blocked_winners_5x",
        "n_blocked_no_outcome",
        "warning_flags",
    )
    if impact_rows_override is not None:
        impact_rows = impact_rows_override
    else:
        impact_rows = []
        for spec in rule_specs:
            impact_rows.append(
                {
                    "rule_id": spec["rule_id"],
                    "policy_surface": spec.get(
                        "policy_surface", "filter_label_blocking"
                    ),
                    "tier_scope": spec["tier_scope"],
                    "filter_name": spec["filter_name"],
                    "filter_version": spec["filter_version"],
                    "filter_label": spec["filter_label"],
                    "threshold_version": spec["threshold_version"],
                    "simulated_action": spec.get("simulated_action", "SIMULATED_BLOCK"),
                    "direction": spec.get("direction", "tighten"),
                    "n_matched": "10",
                    "n_live_decisions_in_tier": "100",
                    "n_simulated_blocks": "10",
                    "n_blocked_with_primary_outcome": "8",
                    "n_blocked_winners_2x": "2",
                    "n_blocked_winners_3x": "1",
                    "n_blocked_winners_5x": "0",
                    "n_blocked_no_outcome": "2",
                    "warning_flags": spec.get("warning_flags", ""),
                }
            )
        impact_rows = tuple(impact_rows)
        if extra_impact_rows:
            impact_rows = impact_rows + tuple(extra_impact_rows)
    if "impact_summary_by_rule.csv" not in omit_files:
        _write_csv(
            run_dir / "impact_summary_by_rule.csv",
            impact_columns,
            impact_rows,
        )

    # ----- manifest.json -----
    rules_path = run_dir / "shadow_policy_rules.json"
    manifest: dict[str, Any] = {
        "stage14_version": "0.1.0",
        "stage14_schema_version": schema_version,
        "run_timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "safe_for_live_policy_consumption": safe_for_live,
        "runtime_consumable": runtime_consumable,
        "allowed_actions": ["SIMULATED_BLOCK"],
        "primary_outcome_metric": "hit_2x_24h",
        "stage13_run_path": str((base / "stage13_run").resolve()),
        "stage13_manifest_hash": stage13_manifest_hash,
        "stage13_candidate_csv_hash": "sha256:" + ("c" * 64),
        "stage13_recommendation_set_version": "sha256:deadbeef",
        "stage12_run_path": str((base / "stage12_run").resolve()),
        "stage12_manifest_hash": stage12_manifest_hash,
        "stage12_long_csv_hash": "sha256:" + ("d" * 64),
        "rule_count": len(rule_specs),
        "excluded_count": 0,
        "n_live_decisions": 100,
        "n_simulated_blocks": 10,
        "overall_warning_flags": [],
        "artifact_filenames": [],
        "git_commit": None,
    }
    if embedded_stage13_schema_version is not None:
        manifest["stage13_schema_version"] = embedded_stage13_schema_version
    if manifest_override is not None:
        manifest = dict(manifest_override)
    if "manifest.json" not in omit_files:
        (run_dir / "manifest.json").write_text(
            json.dumps(manifest, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )

    return run_dir


def _write_csv(
    path: Path, columns: tuple[str, ...], rows: tuple[Mapping[str, str], ...]
) -> None:
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=list(columns), lineterminator="\n"
        )
        writer.writeheader()
        for row in rows:
            writer.writerow({col: row.get(col, "") for col in columns})


# ---------------------------------------------------------------------------
# Operator review CSV builder
# ---------------------------------------------------------------------------


DEFAULT_REVIEWER = "Maq"
DEFAULT_REVIEWED_AT = "2026-05-12T12:00:00+00:00"


def make_operator_csv(
    path: Path,
    rows: tuple[Mapping[str, str], ...],
    *,
    columns: tuple[str, ...] = (
        "rule_id",
        "operator_decision",
        "operator_reason",
        "reviewer",
        "reviewed_at_utc",
        "override_warning_flags",
        "notes",
    ),
    bom: bool = False,
) -> Path:
    """Write an operator review CSV.

    ``rows`` should be an ordered tuple of dicts. Missing columns are
    treated as empty strings. ``bom`` writes a UTF-8 BOM at the start
    of the file so the BOM-tolerance test can verify utf-8-sig behavior.
    """

    buf: list[str] = []
    buf.append(",".join(columns))
    for row in rows:
        cells = []
        for col in columns:
            value = str(row.get(col, ""))
            # Quote cells that contain comma, newline, or quote.
            if any(ch in value for ch in (",", "\n", '"')):
                escaped = value.replace('"', '""')
                value = f'"{escaped}"'
            cells.append(value)
        buf.append(",".join(cells))
    body = "\n".join(buf) + "\n"
    if bom:
        path.write_bytes(b"\xef\xbb\xbf" + body.encode("utf-8"))
    else:
        path.write_text(body, encoding="utf-8")
    return path


def approve_row(
    rule_id: str,
    *,
    reason: str = "",
    override: bool = False,
    notes: str = "",
    reviewer: str = DEFAULT_REVIEWER,
    reviewed_at: str = DEFAULT_REVIEWED_AT,
) -> dict[str, str]:
    return {
        "rule_id": rule_id,
        "operator_decision": "APPROVE_OBSERVE_ONLY",
        "operator_reason": reason,
        "reviewer": reviewer,
        "reviewed_at_utc": reviewed_at,
        "override_warning_flags": "true" if override else "false",
        "notes": notes,
    }


def reject_row(
    rule_id: str,
    *,
    reason: str = "rejecting because reasons",
    notes: str = "",
    reviewer: str = DEFAULT_REVIEWER,
    reviewed_at: str = DEFAULT_REVIEWED_AT,
) -> dict[str, str]:
    return {
        "rule_id": rule_id,
        "operator_decision": "REJECT",
        "operator_reason": reason,
        "reviewer": reviewer,
        "reviewed_at_utc": reviewed_at,
        "override_warning_flags": "false",
        "notes": notes,
    }


def hold_row(
    rule_id: str,
    *,
    reason: str = "revisit next quarter",
    notes: str = "",
    reviewer: str = DEFAULT_REVIEWER,
    reviewed_at: str = DEFAULT_REVIEWED_AT,
) -> dict[str, str]:
    return {
        "rule_id": rule_id,
        "operator_decision": "HOLD",
        "operator_reason": reason,
        "reviewer": reviewer,
        "reviewed_at_utc": reviewed_at,
        "override_warning_flags": "false",
        "notes": notes,
    }


def needs_more_data_row(
    rule_id: str,
    *,
    reason: str = "",
    notes: str = "",
    reviewer: str = DEFAULT_REVIEWER,
    reviewed_at: str = DEFAULT_REVIEWED_AT,
) -> dict[str, str]:
    return {
        "rule_id": rule_id,
        "operator_decision": "NEEDS_MORE_DATA",
        "operator_reason": reason,
        "reviewer": reviewer,
        "reviewed_at_utc": reviewed_at,
        "override_warning_flags": "false",
        "notes": notes,
    }

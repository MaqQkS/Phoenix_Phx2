"""Stage 16A test fixture builders.

Build synthetic Stage 15 run directories whose shape matches what Stage 15's
writer actually produces (per Step 0 V1/V2 verification). Defaults are
schema-valid; keyword overrides let individual tests inject one targeted
corruption to exercise a specific L code.

Stage 15 is NOT imported here. The fixture writes Stage-15-shaped JSON
directly so Stage 16A's test surface keeps its declared import-boundary
posture (no ``PHX2.stage15.*`` runtime dependency).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from PHX2.stage16a.hashing import sha256_bytes


# ---------------------------------------------------------------------------
# Default rule + manifest defaults
# ---------------------------------------------------------------------------


DEFAULT_RULE: Mapping[str, Any] = {
    "rule_id": "rule_t2_fee_gate_scam_likely",
    "predicate": {
        "tier_scope": "T2",
        "filter_name": "fee_gate",
        "filter_version": "fee_gate_v1_no_bribes",
        "filter_label": "SCAM_LIKELY",
        "threshold_version": "thresholds_v0_observe_only",
    },
    "intended_action_if_wired": "LOG_WOULD_BLOCK",
    "hard_block_allowed": False,
    "operator_decision": "APPROVE_OBSERVE_ONLY",
    "operator_reason": "observe-only review",
    "reviewed_at_utc": "2026-05-12T12:00:00+00:00",
    "source_stage14_rule_hash": "sha256:" + "a" * 64,
    "stage14_simulated_action": "SIMULATED_BLOCK",
    "warning_flags": [],
    "override_warning_flags": False,
}


SECOND_RULE: Mapping[str, Any] = {
    "rule_id": "rule_t1_fee_gate_normal",
    "predicate": {
        "tier_scope": "T1",
        "filter_name": "fee_gate",
        "filter_version": "fee_gate_v1_no_bribes",
        "filter_label": "NORMAL",
        "threshold_version": "thresholds_v0_observe_only",
    },
    "intended_action_if_wired": "LOG_WOULD_BLOCK",
    "hard_block_allowed": False,
    "operator_decision": "APPROVE_OBSERVE_ONLY",
    "operator_reason": "observe-only review",
    "reviewed_at_utc": "2026-05-12T12:00:00+00:00",
    "source_stage14_rule_hash": "sha256:" + "b" * 64,
    "stage14_simulated_action": "SIMULATED_BLOCK",
    "warning_flags": [],
    "override_warning_flags": False,
}


def _stage15_safety_surface_draft() -> dict[str, Any]:
    return {
        "hard_block_allowed": False,
        "safe_for_live_enforcement": False,
        "safe_for_hard_blocking": False,
        "runtime_consumable": False,
        "observe_only_runtime_consumable": False,
        "safe_for_observe_only_wiring": True,
        "enforcement_mode": "NONE",
        "intended_action_set": ["LOG_WOULD_BLOCK"],
        "approval_status": "OPERATOR_APPROVED_DRAFT",
    }


def _stage15_safety_surface_manifest() -> dict[str, Any]:
    return {
        "hard_block_allowed": False,
        "safe_for_live_enforcement": False,
        "safe_for_hard_blocking": False,
        "runtime_consumable": False,
        "observe_only_runtime_consumable": False,
        "safe_for_observe_only_wiring": True,
        "enforcement_mode": "NONE",
        # Stage 15's manifest carries this extra field; subset-match treats
        # it as an allowed extra. Including it in the fixture keeps the
        # fixture byte-faithful to real Stage 15 output.
        "runtime_consumable_scope": "none",
    }


def _stage15_lineage_block() -> dict[str, Any]:
    return {
        "source_stage14_manifest_hash": "sha256:" + "1" * 64,
        "source_stage14_rules_hash": "sha256:" + "2" * 64,
        "source_stage14_impact_csv_hash": "sha256:" + "3" * 64,
        "source_stage13_manifest_hash": "sha256:" + "4" * 64,
        "source_stage12_manifest_hash": "sha256:" + "5" * 64,
        "source_operator_review_hash": "sha256:" + "6" * 64,
        "source_stage14_run_path": "/tmp/stage14",
        "source_stage14_run_id": "20260512T120000Z",
        "source_stage14_schema_version": "1.0",
        "source_stage13_schema_version": "1.1",
        "source_operator_review_path": "/tmp/op.csv",
        "reviewer": "Maq",
    }


def _stage15_json_bytes(payload: Any) -> bytes:
    """Stage 15's own write encoding: sort_keys + indent=2 + trailing newline."""

    return (
        json.dumps(payload, sort_keys=True, indent=2, ensure_ascii=False) + "\n"
    ).encode("utf-8")


# ---------------------------------------------------------------------------
# Build a Stage 15 run dir
# ---------------------------------------------------------------------------


def build_stage15_run_dir(
    base: Path,
    *,
    rules: tuple[Mapping[str, Any], ...] = (DEFAULT_RULE,),
    manifest_overrides: Mapping[str, Any] | None = None,
    manifest_remove_keys: tuple[str, ...] = (),
    draft_overrides: Mapping[str, Any] | None = None,
    draft_remove_keys: tuple[str, ...] = (),
    omit_files: tuple[str, ...] = (),
    corrupt_draft_bytes: bytes | None = None,
    corrupt_manifest_bytes: bytes | None = None,
    output_files_hash_override: str | None = None,
    omit_output_files_entry: bool = False,
) -> Path:
    """Construct a Stage 15 run dir at ``base``.

    Returns ``base`` (the run dir path). ``base`` is created if missing.

    Defaults produce a clean, valid Stage 15 run with one approved rule.
    Override kwargs corrupt exactly one field for L-code testing:

      * ``rules``: tuple of rule dicts. Empty tuple is valid (empty
        rules list, per locked O5).
      * ``manifest_overrides`` / ``draft_overrides``: dict merged on top of
        defaults (later keys win).
      * ``manifest_remove_keys`` / ``draft_remove_keys``: keys deleted
        after overrides (for L07 / L08 / L11 missing-key tests).
      * ``omit_files``: filenames to skip writing (for L02 tests).
      * ``corrupt_*_bytes``: write arbitrary bytes verbatim instead of
        encoded JSON (for L03 / L09 tests).
      * ``output_files_hash_override``: write a wrong hash into
        ``manifest.output_files`` (for L06 mismatch tests).
      * ``omit_output_files_entry``: drop the draft hash entry entirely.
    """

    base.mkdir(parents=True, exist_ok=True)

    # ---- Draft body ----
    draft: dict[str, Any] = {
        "schema_version": "stage15_approval_draft_v0",
        "stage": 15,
        **_stage15_safety_surface_draft(),
        **{k: v for k, v in _stage15_lineage_block().items()
           if k not in ("source_operator_review_path", "source_stage14_schema_version")},
        "approved_by_human": True,
        "reviewed_at_utc_range": {
            "earliest": "2026-05-12T12:00:00+00:00",
            "latest": "2026-05-12T12:00:00+00:00",
        },
        "warning_flag_source": "stage14_impact_csv",
        "created_at_utc": "2026-05-13T00:00:00+00:00",
        "git_commit": "deadbeefcafef00d",
        "rule_count_approved": len(rules),
        "rules": [dict(r) for r in rules],
    }
    if draft_overrides:
        draft.update(draft_overrides)
    for key in draft_remove_keys:
        draft.pop(key, None)

    if corrupt_draft_bytes is not None:
        draft_bytes = corrupt_draft_bytes
    else:
        draft_bytes = _stage15_json_bytes(draft)

    if DRAFT_FILE not in omit_files:
        (base / DRAFT_FILE).write_bytes(draft_bytes)

    # ---- Manifest body ----
    # Stage 15 writes hashes over the rendered file bytes (sha256:<hex>).
    # For fixture purposes we use the same computation.
    draft_hash_for_manifest = (
        output_files_hash_override
        if output_files_hash_override is not None
        else sha256_bytes(draft_bytes)
    )

    output_files: dict[str, Any] = {}
    if not omit_output_files_entry:
        output_files[DRAFT_FILE] = draft_hash_for_manifest

    manifest: dict[str, Any] = {
        "stage15_schema_version": "stage15_manifest_v0",
        "stage": 15,
        "approval_status": "APPROVED_DRAFT_WRITTEN",
        **_stage15_safety_surface_manifest(),
        **_stage15_lineage_block(),
        "reviewed_at_utc_range": {
            "earliest": "2026-05-12T12:00:00+00:00",
            "latest": "2026-05-12T12:00:00+00:00",
        },
        "warning_flag_source": "stage14_impact_csv",
        "stage14_rule_count": len(rules),
        "approved_rule_count": len(rules),
        "rejected_rule_count": 0,
        "held_rule_count": 0,
        "needs_more_data_count": 0,
        "unreviewed_rule_count": 0,
        "validation_error_count": 0,
        "accounting_total": len(rules),
        "output_files": output_files,
        "created_at_utc": "2026-05-13T00:00:00+00:00",
        "git_commit": "deadbeefcafef00d",
    }
    if manifest_overrides:
        manifest.update(manifest_overrides)
    for key in manifest_remove_keys:
        manifest.pop(key, None)

    if corrupt_manifest_bytes is not None:
        manifest_bytes = corrupt_manifest_bytes
    else:
        manifest_bytes = _stage15_json_bytes(manifest)

    if MANIFEST_FILE not in omit_files:
        (base / MANIFEST_FILE).write_bytes(manifest_bytes)

    return base


MANIFEST_FILE = "manifest.json"
DRAFT_FILE = "approved_observe_only_policy_draft.json"


# ---------------------------------------------------------------------------
# Runtime artifact builder (Phase 6+)
# ---------------------------------------------------------------------------


RUNTIME_ARTIFACT_FILENAME = "observe_only_runtime_policy.json"


def _stage15_json_pretty(payload: Any) -> bytes:
    """Same encoding the production writer uses: pretty-printed, sort_keys,
    trailing newline. Kept local to the fixture to avoid round-tripping
    through production code that is itself under test."""

    return (
        json.dumps(payload, sort_keys=True, indent=2, ensure_ascii=False) + "\n"
    ).encode("utf-8")


def make_runtime_artifact_path(
    base: Path,
    *,
    rules: tuple[Mapping[str, Any], ...] = (DEFAULT_RULE,),
    body_overrides: Mapping[str, Any] | None = None,
    body_remove_keys: tuple[str, ...] = (),
    safety_surface_override: Mapping[str, Any] | None = None,
    skip_hash_recompute: bool = False,
    corrupt_bytes: bytes | None = None,
    now_utc: Any = None,
    git_commit: str = "deadbeefcafef00ddeadbeefcafef00ddeadbeef",
) -> Path:
    """Construct a runtime artifact file for runtime-loader testing.

    By default produces a valid Stage 16A runtime artifact via the
    production builder. Override kwargs introduce one targeted defect:

      * ``body_overrides`` / ``body_remove_keys``: mutate the body after
        the builder runs.
      * ``safety_surface_override``: replace the safety_surface block
        (bypasses the builder's B01 defensive check because the override
        happens AFTER ``build()``).
      * ``skip_hash_recompute``: leave the original policy_hash in place
        even though the body was mutated (R04 should fire on load).
      * ``corrupt_bytes``: write arbitrary bytes verbatim instead of
        encoded JSON (R01).
      * ``now_utc`` / ``git_commit``: pin clock + git for determinism.

    Returns the absolute path to the written artifact file.
    """

    from datetime import datetime, timezone

    from PHX2.stage16a.hashing import sha256_canonical_dict
    from PHX2.stage16a.runtime_policy_builder import RuntimePolicyBuilder
    from PHX2.stage16a.stage15_loader import Stage15ApprovedDraftLoader

    base.mkdir(parents=True, exist_ok=True)
    out_path = base / RUNTIME_ARTIFACT_FILENAME

    if corrupt_bytes is not None:
        out_path.write_bytes(corrupt_bytes)
        return out_path

    if now_utc is None:
        now_utc = datetime(2026, 5, 13, 12, 0, 0, tzinfo=timezone.utc)

    # Build a valid runtime artifact via the production pipeline.
    s15_dir = base / "_s15"
    build_stage15_run_dir(s15_dir, rules=rules)
    draft = Stage15ApprovedDraftLoader().load(s15_dir)
    body = RuntimePolicyBuilder().build(
        draft, now_utc=now_utc, git_commit=git_commit
    )

    # Apply targeted mutations.
    if safety_surface_override is not None:
        body["safety_surface"] = dict(safety_surface_override)
    if body_overrides:
        body.update(body_overrides)
    for key in body_remove_keys:
        body.pop(key, None)

    # Recompute the policy_hash unless the test specifically wants the
    # original (stale) hash left in place to exercise R04.
    if not skip_hash_recompute and "policy_hash" in body:
        body["policy_hash"] = sha256_canonical_dict(
            {k: v for k, v in body.items() if k != "policy_hash"}
        )

    out_path.write_bytes(_stage15_json_pretty(body))
    return out_path

"""Validates and loads a Stage 15 approved-draft artifact against the L01-L22 load-time invariants.

L15 and L16 (predicate.direction / predicate.policy_surface) are intentionally
dropped per Step 0 locked remediation #2: Stage 15 already trims its draft
predicate to 5 keys, so those checks have nothing to verify.

L21 (output-dir empty) and L22 (git_commit obtainable) operate on the runtime
environment rather than the Stage 15 input itself, so they are exposed as
free functions (``initialize_output_dir`` and ``capture_git_commit``) for the
Phase 8 CLI to dispatch directly.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from PHX2.stage16a.errors import Stage16AError
from PHX2.stage16a.hashing import sha256_file
from PHX2.stage16a.safety import (
    ALLOWED_FILTER_LABELS,
    ALLOWED_TIER_SCOPES,
    EXPECTED_STAGE15_DRAFT_SAFETY_SURFACE,
    EXPECTED_STAGE15_SAFETY_SURFACE,
    REQUIRED_PREDICATE_KEYS_STAGE15,
    assert_subset_match,
)


# ---------------------------------------------------------------------------
# Filenames
# ---------------------------------------------------------------------------

MANIFEST_FILENAME = "manifest.json"
DRAFT_FILENAME = "approved_observe_only_policy_draft.json"


# Locked manifest values
STAGE15_MANIFEST_SCHEMA_VERSION = "stage15_manifest_v0"
STAGE15_DRAFT_SCHEMA_VERSION = "stage15_approval_draft_v0"
STAGE15_MANIFEST_APPROVED_STATUS = "APPROVED_DRAFT_WRITTEN"


# Required Stage 15 manifest lineage fields (L07). Each must be a non-empty
# string; Stage 15 writes them as ``"sha256:<hex>"`` strings plus a free-text
# ``reviewer``.
REQUIRED_LINEAGE_FIELDS: tuple[str, ...] = (
    "source_stage14_manifest_hash",
    "source_stage14_rules_hash",
    "source_stage14_impact_csv_hash",
    "source_stage13_manifest_hash",
    "source_stage12_manifest_hash",
    "source_operator_review_hash",
    "reviewer",
)


# Required per-rule fields (L13).
REQUIRED_RULE_FIELDS: tuple[str, ...] = (
    "rule_id",
    "predicate",
    "intended_action_if_wired",
    "hard_block_allowed",
    "operator_decision",
    "source_stage14_rule_hash",
)


@dataclass(frozen=True)
class Stage15ApprovedDraft:
    """Validated Stage 15 input ready for runtime-policy building.

    Carries both parsed bodies, both file hashes, and the resolved paths
    so the builder can populate the Stage 16A manifest's
    ``stage15_lineage_passthrough`` block without re-reading either file.
    """

    run_path: Path
    manifest_path: Path
    draft_path: Path
    manifest: Mapping[str, Any]
    draft: Mapping[str, Any]
    manifest_hash: str
    draft_hash: str


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------


class Stage15ApprovedDraftLoader:
    """Validates a Stage 15 run directory (manifest + approved draft) and returns the parsed safe-for-build payload.

    Validation runs L01-L20 in order on the input artifacts. First failure
    raises ``Stage16AError`` with the specific L code. L21 (output-dir)
    and L22 (git_commit) are CLI-level concerns and live as module-level
    helpers below.
    """

    def load(self, stage15_run_path: Path) -> Stage15ApprovedDraft:
        # L01: path exists and is a directory.
        if not stage15_run_path.exists() or not stage15_run_path.is_dir():
            raise Stage16AError("L01", str(stage15_run_path))

        # L02: both required files present.
        manifest_path = stage15_run_path / MANIFEST_FILENAME
        draft_path = stage15_run_path / DRAFT_FILENAME
        missing = [
            name for name, p in (
                (MANIFEST_FILENAME, manifest_path),
                (DRAFT_FILENAME, draft_path),
            ) if not p.is_file()
        ]
        if missing:
            raise Stage16AError("L02", f"missing: {missing!r}")

        # L03: manifest parses as JSON.
        try:
            manifest_text = manifest_path.read_text(encoding="utf-8")
            manifest = json.loads(manifest_text)
        except json.JSONDecodeError as exc:
            raise Stage16AError("L03", f"{manifest_path}: {exc}") from exc
        if not isinstance(manifest, dict):
            raise Stage16AError(
                "L03",
                f"{manifest_path}: top-level JSON is not an object",
            )

        # L04
        if manifest.get("approval_status") != STAGE15_MANIFEST_APPROVED_STATUS:
            raise Stage16AError(
                "L04",
                f"got {manifest.get('approval_status')!r}",
            )

        # L05
        if manifest.get("stage15_schema_version") != STAGE15_MANIFEST_SCHEMA_VERSION:
            raise Stage16AError(
                "L05",
                f"got {manifest.get('stage15_schema_version')!r}",
            )

        # L06: computed hash of draft == manifest.output_files entry.
        output_files = manifest.get("output_files")
        if not isinstance(output_files, dict):
            raise Stage16AError(
                "L06",
                "manifest.output_files is missing or not an object",
            )
        expected_hash = output_files.get(DRAFT_FILENAME)
        if not isinstance(expected_hash, str) or not expected_hash.strip():
            raise Stage16AError(
                "L06",
                f"manifest.output_files[{DRAFT_FILENAME!r}] is missing or empty",
            )
        computed_hash = sha256_file(draft_path)
        if computed_hash != expected_hash:
            raise Stage16AError(
                "L06",
                f"computed={computed_hash} expected={expected_hash}",
            )

        # L07: lineage fields present and non-empty.
        empty_lineage: list[str] = []
        for fld in REQUIRED_LINEAGE_FIELDS:
            v = manifest.get(fld)
            if not isinstance(v, str) or not v.strip():
                empty_lineage.append(fld)
        if empty_lineage:
            raise Stage16AError(
                "L07",
                f"missing/empty: {sorted(empty_lineage)!r}",
            )

        # L08: manifest safety surface (subset match).
        assert_subset_match(
            EXPECTED_STAGE15_SAFETY_SURFACE,
            manifest,
            code="L08",
            context="stage15 manifest",
        )

        # L09: draft parses as JSON.
        try:
            draft_text = draft_path.read_text(encoding="utf-8")
            draft = json.loads(draft_text)
        except json.JSONDecodeError as exc:
            raise Stage16AError("L09", f"{draft_path}: {exc}") from exc
        if not isinstance(draft, dict):
            raise Stage16AError(
                "L09",
                f"{draft_path}: top-level JSON is not an object",
            )

        # L10
        if draft.get("schema_version") != STAGE15_DRAFT_SCHEMA_VERSION:
            raise Stage16AError(
                "L10",
                f"got {draft.get('schema_version')!r}",
            )

        # L11: draft safety surface (subset match).
        assert_subset_match(
            EXPECTED_STAGE15_DRAFT_SAFETY_SURFACE,
            draft,
            code="L11",
            context="stage15 draft",
        )

        # L12: draft.rules is a list (possibly empty).
        rules = draft.get("rules")
        if not isinstance(rules, list):
            raise Stage16AError(
                "L12",
                f"draft.rules is {type(rules).__name__}, expected list",
            )

        # Per-rule L13, L14, L17, L18 in rule order.
        for index, rule in enumerate(rules):
            self._validate_rule(rule, index)

        # L19: duplicate rule_id.
        rule_ids = [r["rule_id"] for r in rules]
        if len(rule_ids) != len(set(rule_ids)):
            seen: set[str] = set()
            dupes: list[str] = []
            for rid in rule_ids:
                if rid in seen and rid not in dupes:
                    dupes.append(rid)
                seen.add(rid)
            raise Stage16AError("L19", f"duplicates: {dupes!r}")

        # L20: duplicate 5-tuple.
        seen_tuples: set[tuple[str, ...]] = set()
        dupe_tuples: list[tuple[str, ...]] = []
        for r in rules:
            p = r["predicate"]
            key = (
                p["tier_scope"],
                p["filter_name"],
                p["filter_version"],
                p["filter_label"],
                p["threshold_version"],
            )
            if key in seen_tuples and key not in dupe_tuples:
                dupe_tuples.append(key)
            seen_tuples.add(key)
        if dupe_tuples:
            raise Stage16AError("L20", f"duplicates: {dupe_tuples!r}")

        manifest_hash = sha256_file(manifest_path)
        return Stage15ApprovedDraft(
            run_path=stage15_run_path,
            manifest_path=manifest_path,
            draft_path=draft_path,
            manifest=manifest,
            draft=draft,
            manifest_hash=manifest_hash,
            draft_hash=computed_hash,
        )

    def _validate_rule(self, rule: Any, index: int) -> None:
        """L13, L14, L17, L18 for one rule."""

        if not isinstance(rule, dict):
            raise Stage16AError(
                "L13",
                f"rules[{index}] is {type(rule).__name__}, expected dict",
            )

        # L13: required fields present.
        missing = [f for f in REQUIRED_RULE_FIELDS if f not in rule]
        if missing:
            raise Stage16AError(
                "L13",
                f"rules[{index}] missing fields: {missing!r}",
            )

        # L13: rule_id non-empty string.
        rule_id = rule["rule_id"]
        if not isinstance(rule_id, str) or not rule_id.strip():
            raise Stage16AError(
                "L13",
                f"rules[{index}].rule_id must be a non-empty string; got {rule_id!r}",
            )

        # L13: predicate is a dict.
        predicate = rule["predicate"]
        if not isinstance(predicate, dict):
            raise Stage16AError(
                "L13",
                f"rules[{index}].predicate is {type(predicate).__name__}, expected dict",
            )

        # L13: intended_action_if_wired locked.
        if rule["intended_action_if_wired"] != "LOG_WOULD_BLOCK":
            raise Stage16AError(
                "L13",
                f"rules[{index}].intended_action_if_wired={rule['intended_action_if_wired']!r}, "
                f"expected 'LOG_WOULD_BLOCK'",
            )

        # L13: hard_block_allowed must be False.
        if rule["hard_block_allowed"] is not False:
            raise Stage16AError(
                "L13",
                f"rules[{index}].hard_block_allowed={rule['hard_block_allowed']!r}, "
                f"expected False",
            )

        # L13: operator_decision must be APPROVE_OBSERVE_ONLY.
        if rule["operator_decision"] != "APPROVE_OBSERVE_ONLY":
            raise Stage16AError(
                "L13",
                f"rules[{index}].operator_decision={rule['operator_decision']!r}, "
                f"expected 'APPROVE_OBSERVE_ONLY'",
            )

        # L13: source_stage14_rule_hash non-empty string. Per Step 0 locked
        # remediation, accept "sha256:<hex>" prefixed strings or any other
        # non-empty string (Stage 14's hash format is the source of truth).
        src_hash = rule["source_stage14_rule_hash"]
        if not isinstance(src_hash, str) or not src_hash.strip():
            raise Stage16AError(
                "L13",
                f"rules[{index}].source_stage14_rule_hash must be non-empty string; got {src_hash!r}",
            )

        # L14: predicate keys are exactly the 5-key set.
        actual_keys = set(predicate.keys())
        expected_keys = set(REQUIRED_PREDICATE_KEYS_STAGE15)
        if actual_keys != expected_keys:
            extras = sorted(actual_keys - expected_keys)
            missing_keys = sorted(expected_keys - actual_keys)
            detail = f"rules[{index}].predicate keys mismatch"
            if extras:
                detail += f" extras={extras!r}"
            if missing_keys:
                detail += f" missing={missing_keys!r}"
            raise Stage16AError("L14", detail)

        # L17: tier_scope ∈ allowed.
        tier = predicate["tier_scope"]
        if tier not in ALLOWED_TIER_SCOPES:
            raise Stage16AError(
                "L17",
                f"rules[{index}].predicate.tier_scope={tier!r}",
            )

        # L18: filter_label ∈ live-schema set.
        label = predicate["filter_label"]
        if label not in ALLOWED_FILTER_LABELS:
            raise Stage16AError(
                "L18",
                f"rules[{index}].predicate.filter_label={label!r}",
            )


# ---------------------------------------------------------------------------
# CLI-tier checks (L21, L22)
# ---------------------------------------------------------------------------


def initialize_output_dir(output_dir: Path) -> None:
    """L21: ``output_dir`` does not exist OR exists and is empty.

    Creates the directory (and any missing parents) if it doesn't exist;
    otherwise verifies it's empty. Raises ``Stage16AError("L21")`` on
    non-empty directories or path-collision with a non-directory.
    """

    if output_dir.exists():
        if not output_dir.is_dir():
            raise Stage16AError(
                "L21",
                f"{output_dir} exists and is not a directory",
            )
        if any(output_dir.iterdir()):
            raise Stage16AError("L21", f"{output_dir} is not empty")
        return
    output_dir.mkdir(parents=True, exist_ok=False)


def capture_git_commit(repo_root: Path | None = None) -> str:
    """L22: capture the PHX2 working-tree git commit SHA.

    Raises ``Stage16AError("L22")`` if git is unavailable, the path is
    not a git repo, or the subprocess otherwise fails. ``repo_root``
    defaults to two parents up from this file
    (``PHX2/stage16a/stage15_loader.py`` → PHX2 repo root) so the call
    always reports the PHX2 commit regardless of the caller's cwd.
    """

    if repo_root is None:
        repo_root = Path(__file__).resolve().parents[2]
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            check=True,
            timeout=5,
        )
    except (subprocess.SubprocessError, FileNotFoundError, OSError) as exc:
        raise Stage16AError("L22", f"git rev-parse failed: {exc}") from exc
    sha = proc.stdout.strip()
    if not sha:
        raise Stage16AError("L22", "git rev-parse returned empty output")
    return sha

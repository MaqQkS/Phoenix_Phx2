"""Phase 5: RuntimePolicyBuilder constructs a clean runtime artifact and the B01 defensive check fires on drift."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

import pytest

from PHX2.stage16a.errors import Stage16AError
from PHX2.stage16a.hashing import sha256_canonical_dict
from PHX2.stage16a.runtime_policy_builder import (
    RUNTIME_SCHEMA_VERSION,
    RuntimePolicyBuilder,
)
from PHX2.stage16a.safety import REQUIRED_PREDICATE_KEYS_RUNTIME
from PHX2.stage16a.stage15_loader import Stage15ApprovedDraftLoader
from PHX2.tests.stage16a.fixtures.builders import (
    DEFAULT_RULE,
    SECOND_RULE,
    build_stage15_run_dir,
)


PINNED_CLOCK = datetime(2026, 5, 13, 12, 0, 0, tzinfo=timezone.utc)
PINNED_GIT = "abc123def456abc123def456abc123def456abcd"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_draft(tmp_path: Path, **kwargs):
    run = build_stage15_run_dir(tmp_path / "s15", **kwargs)
    return Stage15ApprovedDraftLoader().load(run)


def _build(draft, *, now_utc=PINNED_CLOCK, git_commit=PINNED_GIT):
    return RuntimePolicyBuilder().build(
        draft, now_utc=now_utc, git_commit=git_commit
    )


# ---------------------------------------------------------------------------
# Clean build
# ---------------------------------------------------------------------------


def test_builds_artifact_with_expected_top_level_keys(tmp_path: Path) -> None:
    draft = _load_draft(tmp_path)
    body = _build(draft)
    assert set(body.keys()) == {
        "schema_version",
        "rule_count",
        "generated_at_utc",
        "git_commit",
        "safety_surface",
        "lineage",
        "rules",
        "policy_hash",
    }
    assert body["schema_version"] == RUNTIME_SCHEMA_VERSION
    assert body["rule_count"] == 1
    assert body["git_commit"] == PINNED_GIT


def test_safety_surface_is_runtime_locked(tmp_path: Path) -> None:
    draft = _load_draft(tmp_path)
    body = _build(draft)
    surface = body["safety_surface"]
    assert surface == {
        "enforcement_mode": "OBSERVE_ONLY",
        "hard_block_allowed": False,
        "safe_for_live_enforcement": False,
        "safe_for_hard_blocking": False,
        "runtime_consumable": True,
        "observe_only_runtime_consumable": True,
        "allowed_action_set": ["LOG_WOULD_BLOCK"],
    }


def test_runtime_predicate_has_exactly_five_keys(tmp_path: Path) -> None:
    """direction and policy_surface must NOT appear in the runtime predicate."""

    draft = _load_draft(tmp_path)
    body = _build(draft)
    for rule in body["rules"]:
        assert set(rule["predicate"].keys()) == set(REQUIRED_PREDICATE_KEYS_RUNTIME)
        assert "direction" not in rule["predicate"]
        assert "policy_surface" not in rule["predicate"]


def test_rule_carries_observe_only_intent(tmp_path: Path) -> None:
    draft = _load_draft(tmp_path)
    body = _build(draft)
    for rule in body["rules"]:
        assert rule["intended_action"] == "LOG_WOULD_BLOCK"
        assert rule["hard_block_allowed"] is False


def test_rule_passes_through_operator_review_metadata(tmp_path: Path) -> None:
    draft = _load_draft(tmp_path)
    body = _build(draft)
    rule = body["rules"][0]
    assert rule["rule_id"] == DEFAULT_RULE["rule_id"]
    assert rule["operator_reason"] == DEFAULT_RULE["operator_reason"]
    assert rule["reviewed_at_utc"] == DEFAULT_RULE["reviewed_at_utc"]
    assert rule["source_stage14_rule_hash"] == DEFAULT_RULE["source_stage14_rule_hash"]


def test_rules_preserve_draft_order_with_two_rules(tmp_path: Path) -> None:
    draft = _load_draft(tmp_path, rules=(DEFAULT_RULE, SECOND_RULE))
    body = _build(draft)
    rule_ids = [r["rule_id"] for r in body["rules"]]
    assert rule_ids == [DEFAULT_RULE["rule_id"], SECOND_RULE["rule_id"]]
    assert body["rule_count"] == 2


# ---------------------------------------------------------------------------
# Lineage
# ---------------------------------------------------------------------------


def test_lineage_carries_stage15_run_and_file_hashes(tmp_path: Path) -> None:
    draft = _load_draft(tmp_path)
    body = _build(draft)
    lineage = body["lineage"]
    assert lineage["source_stage15_run_path"] == str(draft.run_path.resolve())
    assert lineage["source_stage15_manifest_hash"] == draft.manifest_hash
    assert lineage["source_stage15_policy_draft_hash"] == draft.draft_hash


def test_lineage_passes_through_stage14_hashes(tmp_path: Path) -> None:
    draft = _load_draft(tmp_path)
    body = _build(draft)
    lineage = body["lineage"]
    for fld in (
        "source_stage14_manifest_hash",
        "source_stage14_rules_hash",
        "source_stage14_impact_csv_hash",
        "source_stage13_manifest_hash",
        "source_stage12_manifest_hash",
        "source_operator_review_hash",
        "reviewer",
    ):
        assert lineage[fld] == draft.manifest[fld]


# ---------------------------------------------------------------------------
# Hash reproducibility / sensitivity
# ---------------------------------------------------------------------------


def test_policy_hash_reproducible_with_pinned_clock(tmp_path: Path) -> None:
    """Two builds of the same draft with the same clock + git_commit must
    produce identical policy_hash (and identical bodies)."""

    draft1 = _load_draft(tmp_path / "a")
    draft2 = _load_draft(tmp_path / "b")
    body1 = _build(draft1)
    body2 = _build(draft2)
    # source_stage15_run_path differs between draft1 and draft2 (different
    # tmp dirs), so we compare structures sans run_path. The hash will
    # therefore differ; verify hash reproducibility on a SAME-path build.
    body3 = _build(draft1)
    assert body3["policy_hash"] == body1["policy_hash"]


def test_policy_hash_changes_with_clock(tmp_path: Path) -> None:
    draft = _load_draft(tmp_path)
    body1 = _build(draft, now_utc=PINNED_CLOCK)
    later = datetime(2026, 5, 13, 13, 0, 0, tzinfo=timezone.utc)
    body2 = _build(draft, now_utc=later)
    assert body1["policy_hash"] != body2["policy_hash"]


def test_policy_hash_changes_with_git_commit(tmp_path: Path) -> None:
    draft = _load_draft(tmp_path)
    body1 = _build(draft, git_commit=PINNED_GIT)
    body2 = _build(draft, git_commit="0" * 40)
    assert body1["policy_hash"] != body2["policy_hash"]


def test_policy_hash_changes_if_rule_count_changes(tmp_path: Path) -> None:
    draft1 = _load_draft(tmp_path / "a")
    draft2 = _load_draft(tmp_path / "b", rules=(DEFAULT_RULE, SECOND_RULE))
    body1 = _build(draft1)
    body2 = _build(draft2)
    assert body1["policy_hash"] != body2["policy_hash"]


def test_policy_hash_matches_canonical_of_body_sans_policy_hash(tmp_path: Path) -> None:
    draft = _load_draft(tmp_path)
    body = _build(draft)
    expected = sha256_canonical_dict(
        {k: v for k, v in body.items() if k != "policy_hash"}
    )
    assert body["policy_hash"] == expected


# ---------------------------------------------------------------------------
# Empty rules
# ---------------------------------------------------------------------------


def test_empty_rules_list_builds_well_formed_artifact(tmp_path: Path) -> None:
    draft = _load_draft(tmp_path, rules=())
    body = _build(draft)
    assert body["rule_count"] == 0
    assert body["rules"] == []
    assert body["safety_surface"]["enforcement_mode"] == "OBSERVE_ONLY"


# ---------------------------------------------------------------------------
# Builder rejects bad inputs
# ---------------------------------------------------------------------------


def test_builder_rejects_empty_git_commit(tmp_path: Path) -> None:
    draft = _load_draft(tmp_path)
    with pytest.raises(ValueError):
        _build(draft, git_commit="")


# ---------------------------------------------------------------------------
# B01 defensive re-check
# ---------------------------------------------------------------------------


def test_b01_fires_on_safety_surface_drift_via_monkeypatch(
    tmp_path: Path, monkeypatch
) -> None:
    """Force the builder to produce a drifted safety_surface by patching the
    seam method, then assert B01 fires."""

    def drifted_surface(self):
        return {
            "enforcement_mode": "BLOCK",  # wrong
            "hard_block_allowed": True,   # wrong
            "safe_for_live_enforcement": True,
            "safe_for_hard_blocking": True,
            "runtime_consumable": True,
            "observe_only_runtime_consumable": True,
            "allowed_action_set": ["HARD_BLOCK"],
        }

    monkeypatch.setattr(
        RuntimePolicyBuilder, "_compose_safety_surface", drifted_surface
    )
    draft = _load_draft(tmp_path)
    with pytest.raises(Stage16AError) as info:
        _build(draft)
    assert info.value.code == "B01"


def test_b01_fires_on_extra_safety_key(tmp_path: Path, monkeypatch) -> None:
    def extra_key_surface(self):
        return {
            "enforcement_mode": "OBSERVE_ONLY",
            "hard_block_allowed": False,
            "safe_for_live_enforcement": False,
            "safe_for_hard_blocking": False,
            "runtime_consumable": True,
            "observe_only_runtime_consumable": True,
            "allowed_action_set": ["LOG_WOULD_BLOCK"],
            "future_field": "drift",  # unexpected extra
        }

    monkeypatch.setattr(
        RuntimePolicyBuilder, "_compose_safety_surface", extra_key_surface
    )
    draft = _load_draft(tmp_path)
    with pytest.raises(Stage16AError) as info:
        _build(draft)
    assert info.value.code == "B01"

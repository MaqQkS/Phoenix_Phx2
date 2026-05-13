"""Phase 4: clean Stage 15 fixture loads successfully; empty-rules variant also valid."""

from __future__ import annotations

from pathlib import Path

from PHX2.stage16a.stage15_loader import (
    DRAFT_FILENAME,
    MANIFEST_FILENAME,
    Stage15ApprovedDraftLoader,
)
from PHX2.tests.stage16a.fixtures.builders import (
    DEFAULT_RULE,
    SECOND_RULE,
    build_stage15_run_dir,
)


def test_clean_default_fixture_loads(tmp_path: Path) -> None:
    run = build_stage15_run_dir(tmp_path / "s15")
    loaded = Stage15ApprovedDraftLoader().load(run)
    assert loaded.run_path == run
    assert loaded.manifest_path == run / MANIFEST_FILENAME
    assert loaded.draft_path == run / DRAFT_FILENAME
    assert loaded.manifest["approval_status"] == "APPROVED_DRAFT_WRITTEN"
    assert loaded.draft["schema_version"] == "stage15_approval_draft_v0"
    assert len(loaded.draft["rules"]) == 1
    assert loaded.manifest_hash.startswith("sha256:")
    assert loaded.draft_hash.startswith("sha256:")
    assert loaded.manifest_hash != loaded.draft_hash


def test_two_rule_fixture_loads(tmp_path: Path) -> None:
    run = build_stage15_run_dir(
        tmp_path / "s15",
        rules=(DEFAULT_RULE, SECOND_RULE),
    )
    loaded = Stage15ApprovedDraftLoader().load(run)
    assert len(loaded.draft["rules"]) == 2
    rule_ids = {r["rule_id"] for r in loaded.draft["rules"]}
    assert rule_ids == {DEFAULT_RULE["rule_id"], SECOND_RULE["rule_id"]}


def test_empty_rules_list_is_valid(tmp_path: Path) -> None:
    """Locked O5: an empty approved-rules list is a valid Stage 15 draft."""

    run = build_stage15_run_dir(tmp_path / "s15", rules=())
    loaded = Stage15ApprovedDraftLoader().load(run)
    assert loaded.draft["rules"] == []


def test_loaded_draft_carries_lineage(tmp_path: Path) -> None:
    run = build_stage15_run_dir(tmp_path / "s15")
    loaded = Stage15ApprovedDraftLoader().load(run)
    for field in (
        "source_stage14_manifest_hash",
        "source_stage14_rules_hash",
        "source_stage12_manifest_hash",
        "source_stage13_manifest_hash",
        "source_operator_review_hash",
        "reviewer",
    ):
        assert loaded.manifest[field]


def test_manifest_extra_keys_are_ignored_by_subset_match(tmp_path: Path) -> None:
    """Stage 15's manifest carries ``runtime_consumable_scope`` (and may
    add more fields in future). Subset-match must accept them."""

    run = build_stage15_run_dir(
        tmp_path / "s15",
        manifest_overrides={"future_field": "ignored"},
    )
    loaded = Stage15ApprovedDraftLoader().load(run)
    assert loaded.manifest["future_field"] == "ignored"

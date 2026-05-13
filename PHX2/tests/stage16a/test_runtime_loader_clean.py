"""Phase 6: a clean runtime artifact built by the production builder loads cleanly via ObserveOnlyPolicyLoader."""

from __future__ import annotations

from pathlib import Path

from PHX2.stage16a.models import LoadedObserveOnlyPolicy, LoadedRule
from PHX2.stage16a.observe_only_policy_loader import ObserveOnlyPolicyLoader
from PHX2.tests.stage16a.fixtures.builders import (
    DEFAULT_RULE,
    SECOND_RULE,
    make_runtime_artifact_path,
)


def test_clean_runtime_artifact_loads(tmp_path: Path) -> None:
    path = make_runtime_artifact_path(tmp_path)
    loaded = ObserveOnlyPolicyLoader().load(path)
    assert isinstance(loaded, LoadedObserveOnlyPolicy)
    assert loaded.schema_version == "observe_only_runtime_policy_v0"
    assert loaded.policy_hash.startswith("sha256:")
    assert len(loaded.rules) == 1
    assert isinstance(loaded.rules[0], LoadedRule)


def test_loaded_rule_carries_predicate_fields(tmp_path: Path) -> None:
    path = make_runtime_artifact_path(tmp_path)
    loaded = ObserveOnlyPolicyLoader().load(path)
    rule = loaded.rules[0]
    assert rule.tier_scope == DEFAULT_RULE["predicate"]["tier_scope"]
    assert rule.filter_name == DEFAULT_RULE["predicate"]["filter_name"]
    assert rule.filter_label == DEFAULT_RULE["predicate"]["filter_label"]
    assert rule.threshold_version == DEFAULT_RULE["predicate"]["threshold_version"]
    assert rule.filter_version == DEFAULT_RULE["predicate"]["filter_version"]


def test_loaded_rule_carries_observe_only_invariants(tmp_path: Path) -> None:
    path = make_runtime_artifact_path(tmp_path)
    loaded = ObserveOnlyPolicyLoader().load(path)
    for rule in loaded.rules:
        assert rule.intended_action == "LOG_WOULD_BLOCK"
        assert rule.hard_block_allowed is False


def test_two_rule_artifact_loads(tmp_path: Path) -> None:
    path = make_runtime_artifact_path(tmp_path, rules=(DEFAULT_RULE, SECOND_RULE))
    loaded = ObserveOnlyPolicyLoader().load(path)
    assert len(loaded.rules) == 2
    rule_ids = {r.rule_id for r in loaded.rules}
    assert rule_ids == {DEFAULT_RULE["rule_id"], SECOND_RULE["rule_id"]}


def test_loaded_lineage_carries_stage15_hashes(tmp_path: Path) -> None:
    path = make_runtime_artifact_path(tmp_path)
    loaded = ObserveOnlyPolicyLoader().load(path)
    assert "source_stage15_manifest_hash" in loaded.lineage
    assert "source_stage14_manifest_hash" in loaded.lineage
    assert loaded.lineage["source_stage15_manifest_hash"].startswith("sha256:")


def test_loader_does_not_cache(tmp_path: Path) -> None:
    """Two loads of the same file produce equal results without caching --
    if a future regression introduced caching, subsequent edits to the
    on-disk file would be ignored. Verify by mutating the file between
    loads and seeing the second load reflect (or reject) the change."""

    path = make_runtime_artifact_path(tmp_path)
    loader = ObserveOnlyPolicyLoader()
    first = loader.load(path)

    # Corrupt the file -- the next load must hit the (corrupt) on-disk
    # bytes, not a cached parse.
    path.write_bytes(b"{not valid json")
    from PHX2.stage16a.errors import Stage16AError
    import pytest
    with pytest.raises(Stage16AError):
        loader.load(path)

    # Recover (write a clean artifact again) and verify the loader sees
    # the new bytes.
    make_runtime_artifact_path(tmp_path)
    second = loader.load(path)
    assert second.policy_hash == first.policy_hash

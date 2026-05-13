"""Phase 6: one test per R01-R08 with a targeted corrupted runtime artifact."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from PHX2.stage16a.errors import Stage16AError
from PHX2.stage16a.observe_only_policy_loader import ObserveOnlyPolicyLoader
from PHX2.tests.stage16a.fixtures.builders import (
    DEFAULT_RULE,
    make_runtime_artifact_path,
)


def _load_and_expect(path: Path, code: str) -> Stage16AError:
    with pytest.raises(Stage16AError) as info:
        ObserveOnlyPolicyLoader().load(path)
    assert info.value.code == code, (
        f"expected {code}, got {info.value.code}: {info.value}"
    )
    return info.value


# ---------------------------------------------------------------------------
# R01 -- file missing / not valid JSON
# ---------------------------------------------------------------------------


def test_R01_file_does_not_exist(tmp_path: Path) -> None:
    _load_and_expect(tmp_path / "missing.json", "R01")


def test_R01_invalid_json(tmp_path: Path) -> None:
    path = make_runtime_artifact_path(tmp_path, corrupt_bytes=b"not json,,,")
    _load_and_expect(path, "R01")


def test_R01_top_level_not_object(tmp_path: Path) -> None:
    path = make_runtime_artifact_path(tmp_path, corrupt_bytes=b"[1, 2, 3]")
    _load_and_expect(path, "R01")


# ---------------------------------------------------------------------------
# R02 -- wrong schema_version
# ---------------------------------------------------------------------------


def test_R02_wrong_schema_version(tmp_path: Path) -> None:
    path = make_runtime_artifact_path(
        tmp_path,
        body_overrides={"schema_version": "observe_only_runtime_policy_v1"},
    )
    _load_and_expect(path, "R02")


# ---------------------------------------------------------------------------
# R03 -- safety_surface diverges (extensive cases in test_runtime_loader_safety_rejection)
# ---------------------------------------------------------------------------


def test_R03_safety_surface_missing(tmp_path: Path) -> None:
    path = make_runtime_artifact_path(
        tmp_path, body_remove_keys=("safety_surface",)
    )
    _load_and_expect(path, "R03")


# ---------------------------------------------------------------------------
# R04 -- policy_hash mismatch
# ---------------------------------------------------------------------------


def test_R04_policy_hash_missing(tmp_path: Path) -> None:
    """When policy_hash is absent, R04 fires (post-recompute leaves the
    body without a stored hash because we removed it AFTER recompute via
    skip_hash_recompute=True)."""

    path = make_runtime_artifact_path(
        tmp_path,
        body_remove_keys=("policy_hash",),
        skip_hash_recompute=True,
    )
    _load_and_expect(path, "R04")


def test_R04_one_byte_tampered_in_body(tmp_path: Path) -> None:
    """Change a field in the body without recomputing the hash."""

    path = make_runtime_artifact_path(
        tmp_path,
        body_overrides={"git_commit": "modified_after_hash"},
        skip_hash_recompute=True,
    )
    _load_and_expect(path, "R04")


def test_R04_rules_changed_after_hash(tmp_path: Path) -> None:
    """Mutate the rules list without recomputing the hash."""

    new_rule = deepcopy(dict(DEFAULT_RULE))
    new_rule["predicate"] = dict(DEFAULT_RULE["predicate"])
    new_rule["predicate"]["tier_scope"] = "T1"
    new_rule["rule_id"] = "rule_after_hash"
    path = make_runtime_artifact_path(
        tmp_path,
        body_overrides={"rules": [
            {
                "rule_id": new_rule["rule_id"],
                "predicate": new_rule["predicate"],
                "intended_action": "LOG_WOULD_BLOCK",
                "hard_block_allowed": False,
                "source_stage14_rule_hash": "sha256:" + "f" * 64,
                "operator_reason": "post-hoc",
                "reviewed_at_utc": "2026-05-12T12:00:00+00:00",
            },
        ]},
        skip_hash_recompute=True,
    )
    _load_and_expect(path, "R04")


# ---------------------------------------------------------------------------
# R05 -- lineage hex fields missing / empty
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("field", [
    "source_stage15_manifest_hash",
    "source_stage15_policy_draft_hash",
    "source_stage14_manifest_hash",
    "source_stage14_rules_hash",
    "source_stage14_impact_csv_hash",
    "source_stage13_manifest_hash",
    "source_stage12_manifest_hash",
    "source_operator_review_hash",
])
def test_R05_missing_required_lineage_hex_field(tmp_path: Path, field: str) -> None:
    """Mutate lineage[field] = "" -- empty string is not a valid hex hash."""

    # Need to first load the body, mutate lineage, then write back.
    path = make_runtime_artifact_path(tmp_path)
    import json
    body = json.loads(path.read_text(encoding="utf-8"))
    body["lineage"][field] = ""

    # Recompute hash with the corrupted lineage so we hit R05, not R04.
    from PHX2.stage16a.hashing import sha256_canonical_dict
    body["policy_hash"] = sha256_canonical_dict(
        {k: v for k, v in body.items() if k != "policy_hash"}
    )
    path.write_text(
        json.dumps(body, sort_keys=True, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    _load_and_expect(path, "R05")


def test_R05_lineage_missing_entirely(tmp_path: Path) -> None:
    path = make_runtime_artifact_path(
        tmp_path, body_remove_keys=("lineage",)
    )
    _load_and_expect(path, "R05")


# ---------------------------------------------------------------------------
# R06 -- rule shape / 5-key predicate / observe-only safety
# ---------------------------------------------------------------------------


def test_R06_rules_not_a_list(tmp_path: Path) -> None:
    path = make_runtime_artifact_path(
        tmp_path,
        body_overrides={"rules": {"not": "a list"}},
    )
    _load_and_expect(path, "R06")


def test_R06_rule_predicate_has_extra_key(tmp_path: Path) -> None:
    """Direct mutation of an already-built artifact: inject a 6th
    predicate key after the hash is computed (with recompute)."""

    import json
    from PHX2.stage16a.hashing import sha256_canonical_dict

    path = make_runtime_artifact_path(tmp_path)
    body = json.loads(path.read_text(encoding="utf-8"))
    body["rules"][0]["predicate"]["direction"] = "tighten"
    body["policy_hash"] = sha256_canonical_dict(
        {k: v for k, v in body.items() if k != "policy_hash"}
    )
    path.write_text(
        json.dumps(body, sort_keys=True, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    _load_and_expect(path, "R06")


def test_R06_rule_intended_action_not_observe(tmp_path: Path) -> None:
    import json
    from PHX2.stage16a.hashing import sha256_canonical_dict

    path = make_runtime_artifact_path(tmp_path)
    body = json.loads(path.read_text(encoding="utf-8"))
    body["rules"][0]["intended_action"] = "HARD_BLOCK"
    body["policy_hash"] = sha256_canonical_dict(
        {k: v for k, v in body.items() if k != "policy_hash"}
    )
    path.write_text(
        json.dumps(body, sort_keys=True, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    _load_and_expect(path, "R06")


def test_R06_rule_hard_block_allowed_true(tmp_path: Path) -> None:
    import json
    from PHX2.stage16a.hashing import sha256_canonical_dict

    path = make_runtime_artifact_path(tmp_path)
    body = json.loads(path.read_text(encoding="utf-8"))
    body["rules"][0]["hard_block_allowed"] = True
    body["policy_hash"] = sha256_canonical_dict(
        {k: v for k, v in body.items() if k != "policy_hash"}
    )
    path.write_text(
        json.dumps(body, sort_keys=True, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    _load_and_expect(path, "R06")


def test_R06_rule_id_empty(tmp_path: Path) -> None:
    import json
    from PHX2.stage16a.hashing import sha256_canonical_dict

    path = make_runtime_artifact_path(tmp_path)
    body = json.loads(path.read_text(encoding="utf-8"))
    body["rules"][0]["rule_id"] = ""
    body["policy_hash"] = sha256_canonical_dict(
        {k: v for k, v in body.items() if k != "policy_hash"}
    )
    path.write_text(
        json.dumps(body, sort_keys=True, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    _load_and_expect(path, "R06")


# ---------------------------------------------------------------------------
# R07 -- predicate value not in allowed set
# ---------------------------------------------------------------------------


def test_R07_tier_scope_invalid(tmp_path: Path) -> None:
    import json
    from PHX2.stage16a.hashing import sha256_canonical_dict

    path = make_runtime_artifact_path(tmp_path)
    body = json.loads(path.read_text(encoding="utf-8"))
    body["rules"][0]["predicate"]["tier_scope"] = "overall"
    body["policy_hash"] = sha256_canonical_dict(
        {k: v for k, v in body.items() if k != "policy_hash"}
    )
    path.write_text(
        json.dumps(body, sort_keys=True, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    _load_and_expect(path, "R07")


def test_R07_filter_label_invalid(tmp_path: Path) -> None:
    import json
    from PHX2.stage16a.hashing import sha256_canonical_dict

    path = make_runtime_artifact_path(tmp_path)
    body = json.loads(path.read_text(encoding="utf-8"))
    body["rules"][0]["predicate"]["filter_label"] = "CLEAN"
    body["policy_hash"] = sha256_canonical_dict(
        {k: v for k, v in body.items() if k != "policy_hash"}
    )
    path.write_text(
        json.dumps(body, sort_keys=True, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    _load_and_expect(path, "R07")


# ---------------------------------------------------------------------------
# R08 -- duplicate rule_id / duplicate 5-tuple
# ---------------------------------------------------------------------------


def test_R08_duplicate_rule_id(tmp_path: Path) -> None:
    import json
    from PHX2.stage16a.hashing import sha256_canonical_dict

    path = make_runtime_artifact_path(tmp_path)
    body = json.loads(path.read_text(encoding="utf-8"))
    dup_rule = deepcopy(body["rules"][0])
    dup_rule["predicate"] = deepcopy(body["rules"][0]["predicate"])
    dup_rule["predicate"]["tier_scope"] = "T1"  # different tuple but same rule_id
    body["rules"].append(dup_rule)
    body["policy_hash"] = sha256_canonical_dict(
        {k: v for k, v in body.items() if k != "policy_hash"}
    )
    path.write_text(
        json.dumps(body, sort_keys=True, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    _load_and_expect(path, "R08")


def test_R08_duplicate_predicate_tuple(tmp_path: Path) -> None:
    import json
    from PHX2.stage16a.hashing import sha256_canonical_dict

    path = make_runtime_artifact_path(tmp_path)
    body = json.loads(path.read_text(encoding="utf-8"))
    dup = deepcopy(body["rules"][0])
    dup["rule_id"] = "rule_duplicate"
    body["rules"].append(dup)
    body["policy_hash"] = sha256_canonical_dict(
        {k: v for k, v in body.items() if k != "policy_hash"}
    )
    path.write_text(
        json.dumps(body, sort_keys=True, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    _load_and_expect(path, "R08")

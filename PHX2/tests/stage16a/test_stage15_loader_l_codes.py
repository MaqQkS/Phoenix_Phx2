"""Phase 4: one test per L01-L22 with a targeted broken fixture.

Each test corrupts exactly one field of the Stage 15 input and asserts the
specific L code fires. L15 and L16 are intentionally absent (Step 0 locked
remediation #2: Stage 15's predicate has 5 keys, never 7).
"""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from PHX2.stage16a.errors import Stage16AError
from PHX2.stage16a.stage15_loader import (
    Stage15ApprovedDraftLoader,
    capture_git_commit,
    initialize_output_dir,
)
from PHX2.tests.stage16a.fixtures.builders import (
    DEFAULT_RULE,
    SECOND_RULE,
    build_stage15_run_dir,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_and_expect(run_dir: Path, expected_code: str) -> Stage16AError:
    loader = Stage15ApprovedDraftLoader()
    with pytest.raises(Stage16AError) as info:
        loader.load(run_dir)
    assert info.value.code == expected_code, (
        f"expected {expected_code}, got {info.value.code}: {info.value}"
    )
    return info.value


# ---------------------------------------------------------------------------
# L01 -- --stage15-run-path missing / not a directory
# ---------------------------------------------------------------------------


def test_L01_run_path_does_not_exist(tmp_path: Path) -> None:
    _load_and_expect(tmp_path / "nope", "L01")


def test_L01_run_path_is_a_file(tmp_path: Path) -> None:
    f = tmp_path / "file"
    f.write_text("hi")
    _load_and_expect(f, "L01")


# ---------------------------------------------------------------------------
# L02 -- required files missing
# ---------------------------------------------------------------------------


def test_L02_manifest_missing(tmp_path: Path) -> None:
    run = build_stage15_run_dir(tmp_path / "s15", omit_files=("manifest.json",))
    _load_and_expect(run, "L02")


def test_L02_draft_missing(tmp_path: Path) -> None:
    run = build_stage15_run_dir(
        tmp_path / "s15",
        omit_files=("approved_observe_only_policy_draft.json",),
    )
    _load_and_expect(run, "L02")


# ---------------------------------------------------------------------------
# L03 -- manifest not valid JSON
# ---------------------------------------------------------------------------


def test_L03_manifest_invalid_json(tmp_path: Path) -> None:
    run = build_stage15_run_dir(
        tmp_path / "s15",
        corrupt_manifest_bytes=b"{this is not valid json,,",
    )
    _load_and_expect(run, "L03")


def test_L03_manifest_not_an_object(tmp_path: Path) -> None:
    run = build_stage15_run_dir(
        tmp_path / "s15",
        corrupt_manifest_bytes=b'[1, 2, 3]',
    )
    _load_and_expect(run, "L03")


# ---------------------------------------------------------------------------
# L04 -- manifest.approval_status wrong
# ---------------------------------------------------------------------------


def test_L04_wrong_approval_status(tmp_path: Path) -> None:
    run = build_stage15_run_dir(
        tmp_path / "s15",
        manifest_overrides={"approval_status": "VALIDATION_FAILED"},
    )
    _load_and_expect(run, "L04")


# ---------------------------------------------------------------------------
# L05 -- manifest.stage15_schema_version wrong
# ---------------------------------------------------------------------------


def test_L05_wrong_schema_version(tmp_path: Path) -> None:
    run = build_stage15_run_dir(
        tmp_path / "s15",
        manifest_overrides={"stage15_schema_version": "stage15_manifest_v1"},
    )
    _load_and_expect(run, "L05")


# ---------------------------------------------------------------------------
# L06 -- draft hash mismatch
# ---------------------------------------------------------------------------


def test_L06_draft_hash_mismatch(tmp_path: Path) -> None:
    run = build_stage15_run_dir(
        tmp_path / "s15",
        output_files_hash_override="sha256:" + "0" * 64,
    )
    _load_and_expect(run, "L06")


def test_L06_missing_output_files_entry(tmp_path: Path) -> None:
    run = build_stage15_run_dir(
        tmp_path / "s15",
        omit_output_files_entry=True,
    )
    _load_and_expect(run, "L06")


# ---------------------------------------------------------------------------
# L07 -- missing lineage field
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("field", [
    "source_stage14_manifest_hash",
    "source_stage14_rules_hash",
    "source_stage14_impact_csv_hash",
    "source_stage13_manifest_hash",
    "source_stage12_manifest_hash",
    "source_operator_review_hash",
    "reviewer",
])
def test_L07_missing_required_lineage_field(tmp_path: Path, field: str) -> None:
    run = build_stage15_run_dir(
        tmp_path / "s15",
        manifest_overrides={field: ""},
    )
    _load_and_expect(run, "L07")


# ---------------------------------------------------------------------------
# L08 -- manifest safety surface diverges
# ---------------------------------------------------------------------------


def test_L08_hard_block_allowed_true(tmp_path: Path) -> None:
    run = build_stage15_run_dir(
        tmp_path / "s15",
        manifest_overrides={"hard_block_allowed": True},
    )
    _load_and_expect(run, "L08")


def test_L08_enforcement_mode_wrong(tmp_path: Path) -> None:
    run = build_stage15_run_dir(
        tmp_path / "s15",
        manifest_overrides={"enforcement_mode": "BLOCK"},
    )
    _load_and_expect(run, "L08")


def test_L08_safe_for_live_enforcement_true(tmp_path: Path) -> None:
    run = build_stage15_run_dir(
        tmp_path / "s15",
        manifest_overrides={"safe_for_live_enforcement": True},
    )
    _load_and_expect(run, "L08")


def test_L08_missing_safety_key(tmp_path: Path) -> None:
    run = build_stage15_run_dir(
        tmp_path / "s15",
        manifest_remove_keys=("enforcement_mode",),
    )
    _load_and_expect(run, "L08")


# ---------------------------------------------------------------------------
# L09 -- draft not valid JSON
# ---------------------------------------------------------------------------


def test_L09_draft_invalid_json(tmp_path: Path) -> None:
    """L09 corruption is special: the draft bytes go in but the manifest's
    recorded hash must still match those bytes, otherwise L06 fires first."""

    corrupt = b"not-valid-json,,,"
    from PHX2.stage16a.hashing import sha256_bytes
    run = build_stage15_run_dir(
        tmp_path / "s15",
        corrupt_draft_bytes=corrupt,
        output_files_hash_override=sha256_bytes(corrupt),
    )
    _load_and_expect(run, "L09")


# ---------------------------------------------------------------------------
# L10 -- draft.schema_version wrong
# ---------------------------------------------------------------------------


def test_L10_wrong_draft_schema_version(tmp_path: Path) -> None:
    run = build_stage15_run_dir(
        tmp_path / "s15",
        draft_overrides={"schema_version": "stage15_approval_draft_v1"},
    )
    _load_and_expect(run, "L10")


# ---------------------------------------------------------------------------
# L11 -- draft safety surface diverges
# ---------------------------------------------------------------------------


def test_L11_draft_intended_action_set_wrong(tmp_path: Path) -> None:
    run = build_stage15_run_dir(
        tmp_path / "s15",
        draft_overrides={"intended_action_set": ["HARD_BLOCK"]},
    )
    _load_and_expect(run, "L11")


def test_L11_draft_approval_status_wrong(tmp_path: Path) -> None:
    run = build_stage15_run_dir(
        tmp_path / "s15",
        draft_overrides={"approval_status": "DRAFT_REJECTED"},
    )
    _load_and_expect(run, "L11")


def test_L11_draft_runtime_consumable_true(tmp_path: Path) -> None:
    run = build_stage15_run_dir(
        tmp_path / "s15",
        draft_overrides={"runtime_consumable": True},
    )
    _load_and_expect(run, "L11")


# ---------------------------------------------------------------------------
# L12 -- draft.rules not a list
# ---------------------------------------------------------------------------


def test_L12_rules_is_dict(tmp_path: Path) -> None:
    run = build_stage15_run_dir(
        tmp_path / "s15",
        draft_overrides={"rules": {"not": "a list"}},
    )
    _load_and_expect(run, "L12")


# ---------------------------------------------------------------------------
# L13 -- rule missing required field / wrong value
# ---------------------------------------------------------------------------


def test_L13_rule_missing_rule_id(tmp_path: Path) -> None:
    r = deepcopy(dict(DEFAULT_RULE))
    del r["rule_id"]
    run = build_stage15_run_dir(tmp_path / "s15", rules=(r,))
    _load_and_expect(run, "L13")


def test_L13_rule_id_empty_string(tmp_path: Path) -> None:
    r = deepcopy(dict(DEFAULT_RULE))
    r["rule_id"] = ""
    run = build_stage15_run_dir(tmp_path / "s15", rules=(r,))
    _load_and_expect(run, "L13")


def test_L13_rule_intended_action_not_observe(tmp_path: Path) -> None:
    r = deepcopy(dict(DEFAULT_RULE))
    r["intended_action_if_wired"] = "HARD_BLOCK"
    run = build_stage15_run_dir(tmp_path / "s15", rules=(r,))
    _load_and_expect(run, "L13")


def test_L13_rule_hard_block_allowed_true(tmp_path: Path) -> None:
    r = deepcopy(dict(DEFAULT_RULE))
    r["hard_block_allowed"] = True
    run = build_stage15_run_dir(tmp_path / "s15", rules=(r,))
    _load_and_expect(run, "L13")


def test_L13_rule_operator_decision_wrong(tmp_path: Path) -> None:
    r = deepcopy(dict(DEFAULT_RULE))
    r["operator_decision"] = "REJECT"
    run = build_stage15_run_dir(tmp_path / "s15", rules=(r,))
    _load_and_expect(run, "L13")


def test_L13_rule_source_hash_empty(tmp_path: Path) -> None:
    r = deepcopy(dict(DEFAULT_RULE))
    r["source_stage14_rule_hash"] = ""
    run = build_stage15_run_dir(tmp_path / "s15", rules=(r,))
    _load_and_expect(run, "L13")


def test_L13_rule_predicate_not_a_dict(tmp_path: Path) -> None:
    r = deepcopy(dict(DEFAULT_RULE))
    r["predicate"] = "not a dict"
    run = build_stage15_run_dir(tmp_path / "s15", rules=(r,))
    _load_and_expect(run, "L13")


# ---------------------------------------------------------------------------
# L14 -- predicate keys not exactly the 5-key set
# ---------------------------------------------------------------------------


def test_L14_extra_predicate_key_direction(tmp_path: Path) -> None:
    """Adding direction back into the predicate must fail -- per locked
    remediation, the 5-key set is now the only valid shape."""

    r = deepcopy(dict(DEFAULT_RULE))
    r["predicate"] = {**r["predicate"], "direction": "tighten"}
    run = build_stage15_run_dir(tmp_path / "s15", rules=(r,))
    _load_and_expect(run, "L14")


def test_L14_extra_predicate_key_policy_surface(tmp_path: Path) -> None:
    r = deepcopy(dict(DEFAULT_RULE))
    r["predicate"] = {**r["predicate"], "policy_surface": "filter_label_blocking"}
    run = build_stage15_run_dir(tmp_path / "s15", rules=(r,))
    _load_and_expect(run, "L14")


def test_L14_missing_predicate_key_threshold_version(tmp_path: Path) -> None:
    r = deepcopy(dict(DEFAULT_RULE))
    pred = dict(r["predicate"])
    pred.pop("threshold_version")
    r["predicate"] = pred
    run = build_stage15_run_dir(tmp_path / "s15", rules=(r,))
    _load_and_expect(run, "L14")


# ---------------------------------------------------------------------------
# L17 -- tier_scope not in allowed set
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bad", ["overall", "ALL", "T0", "T4", "t1", ""])
def test_L17_tier_scope_invalid(tmp_path: Path, bad: str) -> None:
    r = deepcopy(dict(DEFAULT_RULE))
    r["predicate"] = {**r["predicate"], "tier_scope": bad}
    run = build_stage15_run_dir(tmp_path / "s15", rules=(r,))
    _load_and_expect(run, "L17")


# ---------------------------------------------------------------------------
# L18 -- filter_label not in live-schema set
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bad", ["CLEAN", "MAYBE", "EDGE", "scam_likely", ""])
def test_L18_filter_label_invalid(tmp_path: Path, bad: str) -> None:
    r = deepcopy(dict(DEFAULT_RULE))
    r["predicate"] = {**r["predicate"], "filter_label": bad}
    run = build_stage15_run_dir(tmp_path / "s15", rules=(r,))
    _load_and_expect(run, "L18")


# ---------------------------------------------------------------------------
# L19 -- duplicate rule_id
# ---------------------------------------------------------------------------


def test_L19_duplicate_rule_id(tmp_path: Path) -> None:
    r1 = deepcopy(dict(DEFAULT_RULE))
    r2 = deepcopy(dict(DEFAULT_RULE))
    r2["predicate"] = {**r2["predicate"], "tier_scope": "T1"}
    # Same rule_id, different predicate -- L19 fires before L20.
    run = build_stage15_run_dir(tmp_path / "s15", rules=(r1, r2))
    _load_and_expect(run, "L19")


# ---------------------------------------------------------------------------
# L20 -- duplicate predicate 5-tuple
# ---------------------------------------------------------------------------


def test_L20_duplicate_predicate_tuple(tmp_path: Path) -> None:
    r1 = deepcopy(dict(DEFAULT_RULE))
    r2 = deepcopy(dict(DEFAULT_RULE))
    r2["rule_id"] = "rule_t2_fee_gate_scam_likely_duplicate"
    # Same predicate, different rule_id -- L19 doesn't fire, L20 does.
    run = build_stage15_run_dir(tmp_path / "s15", rules=(r1, r2))
    _load_and_expect(run, "L20")


# ---------------------------------------------------------------------------
# L21 -- --output-dir exists and is not empty
# ---------------------------------------------------------------------------


def test_L21_output_dir_non_empty(tmp_path: Path) -> None:
    out = tmp_path / "out"
    out.mkdir()
    (out / "stray.txt").write_text("hi")
    with pytest.raises(Stage16AError) as info:
        initialize_output_dir(out)
    assert info.value.code == "L21"


def test_L21_output_dir_is_a_file(tmp_path: Path) -> None:
    out = tmp_path / "out_file"
    out.write_text("nope")
    with pytest.raises(Stage16AError) as info:
        initialize_output_dir(out)
    assert info.value.code == "L21"


def test_L21_creates_missing_output_dir(tmp_path: Path) -> None:
    out = tmp_path / "out"
    initialize_output_dir(out)
    assert out.is_dir()


def test_L21_accepts_empty_existing_dir(tmp_path: Path) -> None:
    out = tmp_path / "out"
    out.mkdir()
    initialize_output_dir(out)  # no raise
    assert out.is_dir()


# ---------------------------------------------------------------------------
# L22 -- git_commit unobtainable
#
# We can't simply call capture_git_commit() on a tmp_path because the
# default pytest --basetemp lives inside the PHX2 repo, so ``git
# rev-parse`` walks up and finds the parent .git. monkeypatching
# subprocess.run is the deterministic way to exercise each L22 surface
# (missing git, non-zero exit, empty stdout).
# ---------------------------------------------------------------------------


def test_L22_git_executable_missing(monkeypatch, tmp_path: Path) -> None:
    def fake_run(*args, **kwargs):
        raise FileNotFoundError("git: command not found")

    monkeypatch.setattr(
        "PHX2.stage16a.stage15_loader.subprocess.run", fake_run
    )
    with pytest.raises(Stage16AError) as info:
        capture_git_commit(repo_root=tmp_path)
    assert info.value.code == "L22"


def test_L22_git_nonzero_exit(monkeypatch, tmp_path: Path) -> None:
    import subprocess as _sp

    def fake_run(*args, **kwargs):
        raise _sp.CalledProcessError(returncode=128, cmd=args[0])

    monkeypatch.setattr(
        "PHX2.stage16a.stage15_loader.subprocess.run", fake_run
    )
    with pytest.raises(Stage16AError) as info:
        capture_git_commit(repo_root=tmp_path)
    assert info.value.code == "L22"


def test_L22_git_returns_empty_stdout(monkeypatch, tmp_path: Path) -> None:
    import subprocess as _sp

    def fake_run(*args, **kwargs):
        return _sp.CompletedProcess(
            args=args[0], returncode=0, stdout="\n", stderr=""
        )

    monkeypatch.setattr(
        "PHX2.stage16a.stage15_loader.subprocess.run", fake_run
    )
    with pytest.raises(Stage16AError) as info:
        capture_git_commit(repo_root=tmp_path)
    assert info.value.code == "L22"


def test_L22_default_repo_root_succeeds() -> None:
    """When called without a repo_root override, capture_git_commit uses
    the PHX2 repo root and succeeds in this checkout."""

    sha = capture_git_commit()
    assert isinstance(sha, str) and len(sha) > 0

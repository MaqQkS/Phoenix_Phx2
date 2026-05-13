"""Stage 15 PHASE 2 load-time validation tests.

One test per L01-L26. Each test mutates exactly one field of the
default valid fixture (built by ``make_stage14_run`` /
``make_operator_csv``) and asserts the corresponding error code fires.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from PHX2.stage15.errors import Stage15LoadTimeError
from PHX2.stage15.loaders import (
    initialize_output_dir,
    load_impact_summary,
    load_operator_review,
    load_stage14_artifact,
)
from PHX2.tests.stage15.fixtures.builders import (
    DEFAULT_REVIEWER,
    DEFAULT_REVIEWED_AT,
    approve_row,
    make_operator_csv,
    make_stage14_run,
    reject_row,
)


# ---------------------------------------------------------------------------
# Stage 14 artifact load-time errors (L01-L13)
# ---------------------------------------------------------------------------


def test_L01_stage14_run_path_missing(tmp_path: Path) -> None:
    with pytest.raises(Stage15LoadTimeError) as excinfo:
        load_stage14_artifact(tmp_path / "does_not_exist")
    assert excinfo.value.code == "L01"


def test_L01_stage14_run_path_is_file(tmp_path: Path) -> None:
    not_a_dir = tmp_path / "not_a_dir.txt"
    not_a_dir.write_text("hi", encoding="utf-8")
    with pytest.raises(Stage15LoadTimeError) as excinfo:
        load_stage14_artifact(not_a_dir)
    assert excinfo.value.code == "L01"


def test_L02_manifest_missing(tmp_path: Path) -> None:
    run = make_stage14_run(tmp_path / "s14", omit_files=("manifest.json",))
    with pytest.raises(Stage15LoadTimeError) as excinfo:
        load_stage14_artifact(run)
    assert excinfo.value.code == "L02"


def test_L03_rules_missing(tmp_path: Path) -> None:
    run = make_stage14_run(
        tmp_path / "s14", omit_files=("shadow_policy_rules.json",)
    )
    with pytest.raises(Stage15LoadTimeError) as excinfo:
        load_stage14_artifact(run)
    assert excinfo.value.code == "L03"


def test_L04_manifest_invalid_json(tmp_path: Path) -> None:
    run = make_stage14_run(tmp_path / "s14")
    (run / "manifest.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(Stage15LoadTimeError) as excinfo:
        load_stage14_artifact(run)
    assert excinfo.value.code == "L04"


def test_L05_safe_for_live_must_be_false(tmp_path: Path) -> None:
    run = make_stage14_run(tmp_path / "s14", safe_for_live=True)
    with pytest.raises(Stage15LoadTimeError) as excinfo:
        load_stage14_artifact(run)
    assert excinfo.value.code == "L05"


def test_L06_runtime_consumable_must_be_false(tmp_path: Path) -> None:
    run = make_stage14_run(tmp_path / "s14", runtime_consumable=True)
    with pytest.raises(Stage15LoadTimeError) as excinfo:
        load_stage14_artifact(run)
    assert excinfo.value.code == "L06"


def test_L07_unrecognized_schema_version(tmp_path: Path) -> None:
    run = make_stage14_run(tmp_path / "s14", schema_version="9.99")
    with pytest.raises(Stage15LoadTimeError) as excinfo:
        load_stage14_artifact(run)
    assert excinfo.value.code == "L07"


def test_L08_stage13_manifest_hash_blank(tmp_path: Path) -> None:
    run = make_stage14_run(tmp_path / "s14", stage13_manifest_hash="")
    with pytest.raises(Stage15LoadTimeError) as excinfo:
        load_stage14_artifact(run)
    assert excinfo.value.code == "L08"


def test_L08_embedded_stage13_schema_version_wrong(tmp_path: Path) -> None:
    run = make_stage14_run(
        tmp_path / "s14", embedded_stage13_schema_version="9.99"
    )
    with pytest.raises(Stage15LoadTimeError) as excinfo:
        load_stage14_artifact(run)
    assert excinfo.value.code == "L08"


def test_L08_embedded_stage13_schema_version_matches_passes(
    tmp_path: Path,
) -> None:
    """When Stage 14 manifest carries explicit stage13_schema_version='1.1',
    Stage 15 accepts it without forcing the field's absence."""

    run = make_stage14_run(
        tmp_path / "s14", embedded_stage13_schema_version="1.1"
    )
    artifact = load_stage14_artifact(run)
    assert artifact.stage13_schema_version == "1.1"


def test_L09_stage12_manifest_hash_missing(tmp_path: Path) -> None:
    run = make_stage14_run(tmp_path / "s14", stage12_manifest_hash="")
    with pytest.raises(Stage15LoadTimeError) as excinfo:
        load_stage14_artifact(run)
    assert excinfo.value.code == "L09"


def test_L10_recorded_rules_hash_blank(tmp_path: Path) -> None:
    """If Stage 14 manifest records a shadow_policy_rules_hash, it must
    be a non-empty string."""

    run = make_stage14_run(tmp_path / "s14")
    manifest_path = run / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["shadow_policy_rules_hash"] = ""
    manifest_path.write_text(
        json.dumps(manifest, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )
    with pytest.raises(Stage15LoadTimeError) as excinfo:
        load_stage14_artifact(run)
    assert excinfo.value.code == "L10"


def test_L11_recorded_rules_hash_mismatch(tmp_path: Path) -> None:
    """If Stage 14 manifest records a shadow_policy_rules_hash, it must
    match the on-disk hash."""

    run = make_stage14_run(tmp_path / "s14")
    manifest_path = run / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["shadow_policy_rules_hash"] = "sha256:" + ("e" * 64)
    manifest_path.write_text(
        json.dumps(manifest, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )
    with pytest.raises(Stage15LoadTimeError) as excinfo:
        load_stage14_artifact(run)
    assert excinfo.value.code == "L11"


def test_L10_L11_skipped_when_not_recorded(tmp_path: Path) -> None:
    """The current Stage 14 baseline doesn't record a rules hash;
    Stage 15 must accept that quietly."""

    run = make_stage14_run(tmp_path / "s14")
    artifact = load_stage14_artifact(run)
    assert artifact.rules_hash.startswith("sha256:")


def test_L12_rules_invalid_json(tmp_path: Path) -> None:
    run = make_stage14_run(tmp_path / "s14")
    (run / "shadow_policy_rules.json").write_text("not json", encoding="utf-8")
    with pytest.raises(Stage15LoadTimeError) as excinfo:
        load_stage14_artifact(run)
    assert excinfo.value.code == "L12"


def test_L12_rules_top_level_not_object(tmp_path: Path) -> None:
    run = make_stage14_run(tmp_path / "s14")
    (run / "shadow_policy_rules.json").write_text("[]", encoding="utf-8")
    with pytest.raises(Stage15LoadTimeError) as excinfo:
        load_stage14_artifact(run)
    assert excinfo.value.code == "L12"


def test_L13_rule_missing_rule_id(tmp_path: Path) -> None:
    run = make_stage14_run(tmp_path / "s14")
    rules_path = run / "shadow_policy_rules.json"
    doc = json.loads(rules_path.read_text(encoding="utf-8"))
    doc["rules"][0]["rule_id"] = ""
    rules_path.write_text(json.dumps(doc, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    with pytest.raises(Stage15LoadTimeError) as excinfo:
        load_stage14_artifact(run)
    assert excinfo.value.code == "L13"


def test_L13_rule_missing_predicate_field(tmp_path: Path) -> None:
    run = make_stage14_run(tmp_path / "s14")
    rules_path = run / "shadow_policy_rules.json"
    doc = json.loads(rules_path.read_text(encoding="utf-8"))
    del doc["rules"][0]["tier_scope"]
    rules_path.write_text(json.dumps(doc, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    with pytest.raises(Stage15LoadTimeError) as excinfo:
        load_stage14_artifact(run)
    assert excinfo.value.code == "L13"


def test_L13_duplicate_rule_ids(tmp_path: Path) -> None:
    run = make_stage14_run(tmp_path / "s14")
    rules_path = run / "shadow_policy_rules.json"
    doc = json.loads(rules_path.read_text(encoding="utf-8"))
    doc["rules"][1]["rule_id"] = doc["rules"][0]["rule_id"]
    rules_path.write_text(json.dumps(doc, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    with pytest.raises(Stage15LoadTimeError) as excinfo:
        load_stage14_artifact(run)
    assert excinfo.value.code == "L13"


# ---------------------------------------------------------------------------
# Operator review load-time errors (L14-L23)
# ---------------------------------------------------------------------------


def _now_anchor() -> datetime:
    return datetime(2026, 5, 13, 12, 0, tzinfo=timezone.utc)


def _rule_ids(run: Path) -> tuple[str, ...]:
    artifact = load_stage14_artifact(run)
    return tuple(r.rule_id for r in artifact.rules)


def test_L14_operator_file_missing(tmp_path: Path) -> None:
    with pytest.raises(Stage15LoadTimeError) as excinfo:
        load_operator_review(
            tmp_path / "missing.csv",
            reviewer_arg=DEFAULT_REVIEWER,
            stage14_rule_ids=(),
            now_utc=_now_anchor(),
        )
    assert excinfo.value.code == "L14"


def test_L15_missing_column(tmp_path: Path) -> None:
    run = make_stage14_run(tmp_path / "s14")
    csv_path = tmp_path / "op.csv"
    csv_path.write_text(
        "rule_id,operator_decision,operator_reason,reviewer,reviewed_at_utc,override_warning_flags\n"
        "shadow_rule_default_aaaa,APPROVE_OBSERVE_ONLY,reason,Maq,"
        "2026-05-12T12:00:00+00:00,true\n",
        encoding="utf-8",
    )
    with pytest.raises(Stage15LoadTimeError) as excinfo:
        load_operator_review(
            csv_path,
            reviewer_arg=DEFAULT_REVIEWER,
            stage14_rule_ids=_rule_ids(run),
            now_utc=_now_anchor(),
        )
    assert excinfo.value.code == "L15"


def test_L15_extra_column(tmp_path: Path) -> None:
    run = make_stage14_run(tmp_path / "s14")
    csv_path = tmp_path / "op.csv"
    csv_path.write_text(
        "rule_id,operator_decision,operator_reason,reviewer,reviewed_at_utc,"
        "override_warning_flags,notes,extra_col\n",
        encoding="utf-8",
    )
    with pytest.raises(Stage15LoadTimeError) as excinfo:
        load_operator_review(
            csv_path,
            reviewer_arg=DEFAULT_REVIEWER,
            stage14_rule_ids=_rule_ids(run),
            now_utc=_now_anchor(),
        )
    assert excinfo.value.code == "L15"


def test_L16_empty_required_field(tmp_path: Path) -> None:
    run = make_stage14_run(tmp_path / "s14")
    csv_path = tmp_path / "op.csv"
    row = approve_row("shadow_rule_default_bbbb")
    row["rule_id"] = ""
    make_operator_csv(csv_path, rows=(row,))
    with pytest.raises(Stage15LoadTimeError) as excinfo:
        load_operator_review(
            csv_path,
            reviewer_arg=DEFAULT_REVIEWER,
            stage14_rule_ids=_rule_ids(run),
            now_utc=_now_anchor(),
        )
    assert excinfo.value.code == "L16"


def test_L17_disallowed_decision(tmp_path: Path) -> None:
    run = make_stage14_run(tmp_path / "s14")
    csv_path = tmp_path / "op.csv"
    row = approve_row("shadow_rule_default_bbbb")
    row["operator_decision"] = "NUKE_THE_RULE"
    make_operator_csv(csv_path, rows=(row,))
    with pytest.raises(Stage15LoadTimeError) as excinfo:
        load_operator_review(
            csv_path,
            reviewer_arg=DEFAULT_REVIEWER,
            stage14_rule_ids=_rule_ids(run),
            now_utc=_now_anchor(),
        )
    assert excinfo.value.code == "L17"


def test_L18_non_boolean_override(tmp_path: Path) -> None:
    run = make_stage14_run(tmp_path / "s14")
    csv_path = tmp_path / "op.csv"
    row = approve_row("shadow_rule_default_bbbb")
    row["override_warning_flags"] = "maybe"
    make_operator_csv(csv_path, rows=(row,))
    with pytest.raises(Stage15LoadTimeError) as excinfo:
        load_operator_review(
            csv_path,
            reviewer_arg=DEFAULT_REVIEWER,
            stage14_rule_ids=_rule_ids(run),
            now_utc=_now_anchor(),
        )
    assert excinfo.value.code == "L18"


def test_L18_accepts_case_variants(tmp_path: Path) -> None:
    """true/false case-insensitive (TRUE, FALSE both accepted)."""

    run = make_stage14_run(tmp_path / "s14")
    csv_path = tmp_path / "op.csv"
    row1 = approve_row("shadow_rule_default_aaaa", reason="ok", override=True)
    row1["override_warning_flags"] = "TRUE"
    row2 = approve_row("shadow_rule_default_bbbb")
    row2["override_warning_flags"] = "FALSE"
    make_operator_csv(csv_path, rows=(row1, row2))
    review = load_operator_review(
        csv_path,
        reviewer_arg=DEFAULT_REVIEWER,
        stage14_rule_ids=_rule_ids(run),
        now_utc=_now_anchor(),
    )
    assert review.rows[0].override_warning_flags is True
    assert review.rows[1].override_warning_flags is False


def test_L19_invalid_timestamp(tmp_path: Path) -> None:
    run = make_stage14_run(tmp_path / "s14")
    csv_path = tmp_path / "op.csv"
    row = approve_row("shadow_rule_default_bbbb")
    row["reviewed_at_utc"] = "yesterday"
    make_operator_csv(csv_path, rows=(row,))
    with pytest.raises(Stage15LoadTimeError) as excinfo:
        load_operator_review(
            csv_path,
            reviewer_arg=DEFAULT_REVIEWER,
            stage14_rule_ids=_rule_ids(run),
            now_utc=_now_anchor(),
        )
    assert excinfo.value.code == "L19"


def test_L19_naive_timestamp_rejected(tmp_path: Path) -> None:
    run = make_stage14_run(tmp_path / "s14")
    csv_path = tmp_path / "op.csv"
    row = approve_row("shadow_rule_default_bbbb")
    row["reviewed_at_utc"] = "2026-05-12T12:00:00"
    make_operator_csv(csv_path, rows=(row,))
    with pytest.raises(Stage15LoadTimeError) as excinfo:
        load_operator_review(
            csv_path,
            reviewer_arg=DEFAULT_REVIEWER,
            stage14_rule_ids=_rule_ids(run),
            now_utc=_now_anchor(),
        )
    assert excinfo.value.code == "L19"


def test_L19_non_utc_offset_rejected(tmp_path: Path) -> None:
    run = make_stage14_run(tmp_path / "s14")
    csv_path = tmp_path / "op.csv"
    row = approve_row("shadow_rule_default_bbbb")
    row["reviewed_at_utc"] = "2026-05-12T12:00:00+05:30"
    make_operator_csv(csv_path, rows=(row,))
    with pytest.raises(Stage15LoadTimeError) as excinfo:
        load_operator_review(
            csv_path,
            reviewer_arg=DEFAULT_REVIEWER,
            stage14_rule_ids=_rule_ids(run),
            now_utc=_now_anchor(),
        )
    assert excinfo.value.code == "L19"


def test_L19_accepts_z_suffix(tmp_path: Path) -> None:
    run = make_stage14_run(tmp_path / "s14")
    csv_path = tmp_path / "op.csv"
    row = approve_row("shadow_rule_default_bbbb")
    row["reviewed_at_utc"] = "2026-05-12T12:00:00Z"
    make_operator_csv(csv_path, rows=(row,))
    review = load_operator_review(
        csv_path,
        reviewer_arg=DEFAULT_REVIEWER,
        stage14_rule_ids=_rule_ids(run),
        now_utc=_now_anchor(),
    )
    assert review.rows[0].reviewed_at_utc.utcoffset() == timedelta(0)


def test_L20_future_plus_59m_allowed(tmp_path: Path) -> None:
    run = make_stage14_run(tmp_path / "s14")
    now = _now_anchor()
    future = (now + timedelta(minutes=59)).isoformat()
    csv_path = tmp_path / "op.csv"
    row = approve_row("shadow_rule_default_bbbb", reviewed_at=future)
    make_operator_csv(csv_path, rows=(row,))
    review = load_operator_review(
        csv_path,
        reviewer_arg=DEFAULT_REVIEWER,
        stage14_rule_ids=_rule_ids(run),
        now_utc=now,
    )
    assert len(review.rows) == 1


def test_L20_future_plus_61m_rejected(tmp_path: Path) -> None:
    run = make_stage14_run(tmp_path / "s14")
    now = _now_anchor()
    future = (now + timedelta(minutes=61)).isoformat()
    csv_path = tmp_path / "op.csv"
    row = approve_row("shadow_rule_default_bbbb", reviewed_at=future)
    make_operator_csv(csv_path, rows=(row,))
    with pytest.raises(Stage15LoadTimeError) as excinfo:
        load_operator_review(
            csv_path,
            reviewer_arg=DEFAULT_REVIEWER,
            stage14_rule_ids=_rule_ids(run),
            now_utc=now,
        )
    assert excinfo.value.code == "L20"


def test_L21_reviewer_mismatch(tmp_path: Path) -> None:
    run = make_stage14_run(tmp_path / "s14")
    csv_path = tmp_path / "op.csv"
    row = approve_row("shadow_rule_default_bbbb", reviewer="someone_else")
    make_operator_csv(csv_path, rows=(row,))
    with pytest.raises(Stage15LoadTimeError) as excinfo:
        load_operator_review(
            csv_path,
            reviewer_arg=DEFAULT_REVIEWER,
            stage14_rule_ids=_rule_ids(run),
            now_utc=_now_anchor(),
        )
    assert excinfo.value.code == "L21"


def test_L22_duplicate_rule_id_in_operator_csv(tmp_path: Path) -> None:
    run = make_stage14_run(tmp_path / "s14")
    csv_path = tmp_path / "op.csv"
    make_operator_csv(
        csv_path,
        rows=(
            approve_row("shadow_rule_default_bbbb"),
            reject_row("shadow_rule_default_bbbb", reason="oops"),
        ),
    )
    with pytest.raises(Stage15LoadTimeError) as excinfo:
        load_operator_review(
            csv_path,
            reviewer_arg=DEFAULT_REVIEWER,
            stage14_rule_ids=_rule_ids(run),
            now_utc=_now_anchor(),
        )
    assert excinfo.value.code == "L22"


def test_L23_unknown_rule_id(tmp_path: Path) -> None:
    run = make_stage14_run(tmp_path / "s14")
    csv_path = tmp_path / "op.csv"
    make_operator_csv(csv_path, rows=(approve_row("unknown_rule"),))
    with pytest.raises(Stage15LoadTimeError) as excinfo:
        load_operator_review(
            csv_path,
            reviewer_arg=DEFAULT_REVIEWER,
            stage14_rule_ids=_rule_ids(run),
            now_utc=_now_anchor(),
        )
    assert excinfo.value.code == "L23"


# ---------------------------------------------------------------------------
# Output-dir error (L24)
# ---------------------------------------------------------------------------


def test_L24_non_empty_output_dir(tmp_path: Path) -> None:
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    (output_dir / "leftover.txt").write_text("x", encoding="utf-8")
    with pytest.raises(Stage15LoadTimeError) as excinfo:
        initialize_output_dir(output_dir)
    assert excinfo.value.code == "L24"


def test_L24_creates_when_missing(tmp_path: Path) -> None:
    target = tmp_path / "nested" / "stage15_out"
    initialize_output_dir(target)
    assert target.is_dir()


def test_L24_accepts_existing_empty(tmp_path: Path) -> None:
    target = tmp_path / "out"
    target.mkdir()
    initialize_output_dir(target)
    assert target.is_dir()


def test_L24_rejects_non_directory_path(tmp_path: Path) -> None:
    target = tmp_path / "not_a_dir.txt"
    target.write_text("hi", encoding="utf-8")
    with pytest.raises(Stage15LoadTimeError) as excinfo:
        initialize_output_dir(target)
    assert excinfo.value.code == "L24"


# ---------------------------------------------------------------------------
# Git commit (L25) is exercised through the CLI in end-to-end tests since
# the loader module doesn't capture git itself. The CLI test below
# confirms the L25 surface via a subprocess that hides PATH/git.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Impact summary errors (L26)
# ---------------------------------------------------------------------------


def test_L26_impact_csv_missing(tmp_path: Path) -> None:
    run = make_stage14_run(
        tmp_path / "s14", omit_files=("impact_summary_by_rule.csv",)
    )
    rule_ids = _rule_ids(run)
    with pytest.raises(Stage15LoadTimeError) as excinfo:
        load_impact_summary(run, rule_ids)
    assert excinfo.value.code == "L26"


def test_L26_missing_rule_id_column(tmp_path: Path) -> None:
    """Drop the rule_id column from the impact CSV."""

    run = make_stage14_run(
        tmp_path / "s14",
        impact_columns_override=(
            "policy_surface",
            "tier_scope",
            "warning_flags",
        ),
        impact_rows_override=(
            {
                "policy_surface": "x",
                "tier_scope": "T1",
                "warning_flags": "",
            },
        ),
    )
    rule_ids = _rule_ids(run)
    with pytest.raises(Stage15LoadTimeError) as excinfo:
        load_impact_summary(run, rule_ids)
    assert excinfo.value.code == "L26"


def test_L26_missing_warning_flags_column(tmp_path: Path) -> None:
    run = make_stage14_run(
        tmp_path / "s14",
        impact_columns_override=("rule_id", "policy_surface"),
        impact_rows_override=(
            {"rule_id": "shadow_rule_default_aaaa", "policy_surface": "x"},
            {"rule_id": "shadow_rule_default_bbbb", "policy_surface": "x"},
        ),
    )
    rule_ids = _rule_ids(run)
    with pytest.raises(Stage15LoadTimeError) as excinfo:
        load_impact_summary(run, rule_ids)
    assert excinfo.value.code == "L26"


def test_L26_missing_row_for_stage14_rule(tmp_path: Path) -> None:
    """Stage 14 has two rules but impact CSV only has one row."""

    run = make_stage14_run(
        tmp_path / "s14",
        impact_rows_override=(
            {
                "rule_id": "shadow_rule_default_aaaa",
                "warning_flags": "small_n_rule",
            },
        ),
        impact_columns_override=("rule_id", "warning_flags"),
    )
    rule_ids = _rule_ids(run)
    with pytest.raises(Stage15LoadTimeError) as excinfo:
        load_impact_summary(run, rule_ids)
    assert excinfo.value.code == "L26"


def test_L26_duplicate_row_for_stage14_rule(tmp_path: Path) -> None:
    run = make_stage14_run(
        tmp_path / "s14",
        impact_columns_override=("rule_id", "warning_flags"),
        impact_rows_override=(
            {"rule_id": "shadow_rule_default_aaaa", "warning_flags": "x"},
            {"rule_id": "shadow_rule_default_aaaa", "warning_flags": "y"},
            {"rule_id": "shadow_rule_default_bbbb", "warning_flags": ""},
        ),
    )
    rule_ids = _rule_ids(run)
    with pytest.raises(Stage15LoadTimeError) as excinfo:
        load_impact_summary(run, rule_ids)
    assert excinfo.value.code == "L26"


def test_L26_extra_row_allowed(tmp_path: Path) -> None:
    """Extra impact rows not in Stage 14 rules don't fail; they're
    surfaced via ``ImpactSummary.extra_rule_ids``."""

    run = make_stage14_run(
        tmp_path / "s14",
        extra_impact_rows=(
            {
                "rule_id": "extra_unknown_rule",
                "warning_flags": "small_n_rule",
            },
        ),
    )
    rule_ids = _rule_ids(run)
    impact = load_impact_summary(run, rule_ids)
    assert "extra_unknown_rule" in impact.extra_rule_ids
    assert "extra_unknown_rule" not in impact.warning_flags_by_rule


def test_L26_blank_rule_id_in_impact(tmp_path: Path) -> None:
    run = make_stage14_run(
        tmp_path / "s14",
        impact_columns_override=("rule_id", "warning_flags"),
        impact_rows_override=(
            {"rule_id": "shadow_rule_default_aaaa", "warning_flags": ""},
            {"rule_id": "shadow_rule_default_bbbb", "warning_flags": ""},
            {"rule_id": "", "warning_flags": ""},
        ),
    )
    rule_ids = _rule_ids(run)
    with pytest.raises(Stage15LoadTimeError) as excinfo:
        load_impact_summary(run, rule_ids)
    assert excinfo.value.code == "L26"

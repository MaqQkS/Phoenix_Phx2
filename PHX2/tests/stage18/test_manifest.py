"""Phase 18.3 manifest tests.

Verifies the locked shape of the Stage 18 manifest, the
determinism of run_id derivation, and the byte-level
determinism of the manifest serializer.
"""

from __future__ import annotations

from pathlib import Path

from PHX2.stage18.constants import (
    MANIFEST_SCHEMA_VERSION,
    MAX_INCOMPLETE_OUTCOME_RATIO,
    MAX_UNEVALUABLE_RATE,
    MIN_EVALUABLE_COUNT,
    MIN_RULE_NEGATIVE_COUNT,
    MIN_RULE_POSITIVE_COUNT,
    STAGE18_VERSION,
)
from PHX2.stage18.manifest import (
    GATES_SNAPSHOT,
    build_manifest,
    compute_run_id,
    write_manifest,
)


# ---------------------------------------------------------------------------
# compute_run_id
# ---------------------------------------------------------------------------


def test_run_id_is_sixteen_lowercase_hex_chars() -> None:
    rid = compute_run_id(
        stage17_run_id="abc",
        stage17_input_basename="run",
        input_row_counts={"a.csv": 1},
    )
    assert len(rid) == 16
    assert all(c in "0123456789abcdef" for c in rid)


def test_run_id_deterministic_for_same_inputs() -> None:
    a = compute_run_id(
        stage17_run_id="abc",
        stage17_input_basename="run",
        input_row_counts={"a": 1},
    )
    b = compute_run_id(
        stage17_run_id="abc",
        stage17_input_basename="run",
        input_row_counts={"a": 1},
    )
    assert a == b


def test_run_id_changes_when_input_row_counts_change() -> None:
    a = compute_run_id(
        stage17_run_id="abc",
        stage17_input_basename="run",
        input_row_counts={"a": 1},
    )
    b = compute_run_id(
        stage17_run_id="abc",
        stage17_input_basename="run",
        input_row_counts={"a": 2},
    )
    assert a != b


def test_run_id_changes_when_stage17_run_id_changes() -> None:
    a = compute_run_id(
        stage17_run_id="abc",
        stage17_input_basename="run",
        input_row_counts={"a": 1},
    )
    b = compute_run_id(
        stage17_run_id="def",
        stage17_input_basename="run",
        input_row_counts={"a": 1},
    )
    assert a != b


def test_run_id_changes_when_stage17_input_basename_changes() -> None:
    a = compute_run_id(
        stage17_run_id="abc",
        stage17_input_basename="run_a",
        input_row_counts={"a": 1},
    )
    b = compute_run_id(
        stage17_run_id="abc",
        stage17_input_basename="run_b",
        input_row_counts={"a": 1},
    )
    assert a != b


def test_run_id_invariant_under_dict_iteration_order() -> None:
    """``input_row_counts`` may be passed in any order; the run_id
    must be insensitive to dict iteration order thanks to
    ``sort_keys=True`` in the canonical JSON."""

    a = compute_run_id(
        stage17_run_id="abc",
        stage17_input_basename="run",
        input_row_counts={"a": 1, "b": 2},
    )
    b = compute_run_id(
        stage17_run_id="abc",
        stage17_input_basename="run",
        input_row_counts={"b": 2, "a": 1},
    )
    assert a == b


# ---------------------------------------------------------------------------
# build_manifest
# ---------------------------------------------------------------------------


def test_build_manifest_pins_schema_and_version() -> None:
    manifest = build_manifest(
        run_id="r1",
        run_started_utc="2026-01-01T00:00:00+00:00",
        run_finished_utc="2026-01-01T00:00:01+00:00",
        stage17_input_dir="/in",
        output_dir="/out",
        stage17_manifest={"schema_version": "stage17_run_manifest_v0"},
        input_row_counts={"a.csv": 1},
        output_row_counts={"b.csv": 1},
        classification_counts={"HARMFUL_REVIEW": 0},
        git_commit="unknown",
    )
    assert manifest["schema_version"] == MANIFEST_SCHEMA_VERSION
    assert manifest["stage18_version"] == STAGE18_VERSION
    assert manifest["run_id"] == "r1"


def test_build_manifest_embeds_locked_gate_constants() -> None:
    manifest = build_manifest(
        run_id="r1",
        run_started_utc="x",
        run_finished_utc="y",
        stage17_input_dir="/in",
        output_dir="/out",
        stage17_manifest={},
        input_row_counts={},
        output_row_counts={},
        classification_counts={},
        git_commit="unknown",
    )
    gates = manifest["gates"]
    assert gates["min_evaluable_count"] == MIN_EVALUABLE_COUNT
    assert gates["min_rule_positive_count"] == MIN_RULE_POSITIVE_COUNT
    assert gates["min_rule_negative_count"] == MIN_RULE_NEGATIVE_COUNT
    assert gates["max_unevaluable_rate"] == MAX_UNEVALUABLE_RATE
    assert gates["max_incomplete_outcome_ratio"] == MAX_INCOMPLETE_OUTCOME_RATIO


def test_build_manifest_embeds_stage17_manifest_verbatim() -> None:
    s17 = {
        "schema_version": "stage17_run_manifest_v0",
        "run_id": "abc",
        "policy_hashes_analyzed": ["p1", "p2"],
        "unknown_extra_field": "preserved",
    }
    manifest = build_manifest(
        run_id="r1",
        run_started_utc="x",
        run_finished_utc="y",
        stage17_input_dir="/in",
        output_dir="/out",
        stage17_manifest=s17,
        input_row_counts={},
        output_row_counts={},
        classification_counts={},
        git_commit="unknown",
    )
    assert manifest["stage17_manifest"] == s17


def test_build_manifest_carries_classification_counts_verbatim() -> None:
    counts = {
        "HARMFUL_REVIEW": 1,
        "PROMISING_REVIEW": 2,
        "WEAK_REVIEW": 3,
        "MIXED_BY_TIER_REVIEW": 4,
        "INSUFFICIENT_SAMPLE_REVIEW": 5,
        "DATA_BLOCKED_REVIEW": 6,
    }
    manifest = build_manifest(
        run_id="r1",
        run_started_utc="x",
        run_finished_utc="y",
        stage17_input_dir="/in",
        output_dir="/out",
        stage17_manifest={},
        input_row_counts={},
        output_row_counts={},
        classification_counts=counts,
        git_commit="unknown",
    )
    assert manifest["classification_counts"] == counts


def test_gates_snapshot_matches_module_constants() -> None:
    assert GATES_SNAPSHOT["min_evaluable_count"] == MIN_EVALUABLE_COUNT
    assert GATES_SNAPSHOT["min_rule_positive_count"] == MIN_RULE_POSITIVE_COUNT
    assert GATES_SNAPSHOT["min_rule_negative_count"] == MIN_RULE_NEGATIVE_COUNT
    assert GATES_SNAPSHOT["max_unevaluable_rate"] == MAX_UNEVALUABLE_RATE
    assert (
        GATES_SNAPSHOT["max_incomplete_outcome_ratio"]
        == MAX_INCOMPLETE_OUTCOME_RATIO
    )


# ---------------------------------------------------------------------------
# write_manifest
# ---------------------------------------------------------------------------


def test_write_manifest_uses_compact_sorted_json(tmp_path: Path) -> None:
    manifest = {
        "b": 2,
        "a": 1,
        "nested": {"y": 2, "x": 1},
    }
    out_path = tmp_path / "manifest.json"
    write_manifest(manifest, out_path)
    content = out_path.read_text(encoding="utf-8")
    assert content == '{"a":1,"b":2,"nested":{"x":1,"y":2}}'


def test_write_manifest_two_calls_produce_byte_identical_output(
    tmp_path: Path,
) -> None:
    manifest = {"k": [3, 1, 2], "z": "value"}
    a = tmp_path / "a.json"
    b = tmp_path / "b.json"
    write_manifest(manifest, a)
    write_manifest(manifest, b)
    assert a.read_bytes() == b.read_bytes()

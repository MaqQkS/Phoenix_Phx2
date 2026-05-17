"""Stage 20.4 input loader tests.

Cover:

  * Module surface: exception class, NamedTuple shapes, __all__.
  * Valid config -> ClosureInputConfig with empty validation_errors.
  * InputFormatError cases: file missing/not-file/unreadable JSON,
    malformed JSON, root not an object, missing required top-level
    key, operator_test_results not an object, output_root precond
    failures.
  * E2044 (commit SHA format) -- each field independently.
  * E2030 / E2031 (run dirs) -- missing / non-dir / non-string.
  * E2045 (repo_root) -- missing / no PHX2 subdir / non-string.
  * E2043 (operator_test_results) -- every C.7 rule.
  * Derived fields (both_runs_match, all_green) -- truth table.
  * Multiple errors accumulate (no short-circuit).
  * Path resolution: absolute vs repo-relative for run dirs.
  * generated_at_utc sourced from injected clock.
  * compute_config_sha8 properties (length, determinism, sensitivity).
  * AST self-audit: input_loader.py has no forbidden imports.

No conftest.py is added in Phase 2. Helper fixtures are inlined
in this module.
"""

from __future__ import annotations

import ast
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import pytest

from PHX2.stage20.closure import input_loader as il
from PHX2.stage20.closure.clock_helper import FrozenClock
from PHX2.stage20.closure.models import ClosureInputConfig


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


VALID_SHA_20_1 = "c57606779c76763bdb0be6ee5f93cf44db99a29f"
VALID_SHA_20_2 = "a60bbd4174a8169e90744bcff8a68ebd43a99a62"
VALID_SHA_20_3 = "31b131a1bf6322f6c533adf9c9431eb7e68f25c9"


@pytest.fixture
def frozen_clock():
    return FrozenClock(
        datetime(2026, 5, 16, 12, 34, 56, tzinfo=timezone.utc),
    )


@pytest.fixture
def valid_layout(tmp_path: Path):
    """Build a tmp_path layout that satisfies every E20xx check."""
    s2 = tmp_path / "stage20_runs" / "abc"
    s2.mkdir(parents=True)
    s3 = s2 / "stage20_3" / "def"
    s3.mkdir(parents=True)
    repo = tmp_path / "repo"
    (repo / "PHX2").mkdir(parents=True)
    out = tmp_path / "out"
    out.mkdir()
    return {
        "s2_dir": s2,
        "s3_dir": s3,
        "repo_root": repo,
        "output_root": out,
    }


@pytest.fixture
def valid_config_dict(valid_layout):
    return {
        "stage20_1_commit_sha": VALID_SHA_20_1,
        "stage20_2_commit_sha": VALID_SHA_20_2,
        "stage20_3_commit_sha": VALID_SHA_20_3,
        "stage20_2_run_dir": str(valid_layout["s2_dir"]),
        "stage20_3_run_dir": str(valid_layout["s3_dir"]),
        "repo_root": str(valid_layout["repo_root"]),
        "output_root": str(valid_layout["output_root"]),
        "operator_test_results": {
            "test_command": "pytest PHX2/tests/stage20/ -q",
            "run1_passed": 10,
            "run1_failed": 0,
            "run1_errors": 0,
            "run2_passed": 10,
            "run2_failed": 0,
            "run2_errors": 0,
        },
    }


@pytest.fixture
def write_config(tmp_path: Path):
    """Return a callable that writes a config dict to disk and yields
    the resulting JSON file path."""

    def _writer(d: dict, name: str = "config.json") -> Path:
        p = tmp_path / name
        p.write_text(json.dumps(d, indent=2), encoding="utf-8")
        return p

    return _writer


# ---------------------------------------------------------------------------
# Module surface
# ---------------------------------------------------------------------------


def test_input_format_error_is_exception():
    assert issubclass(il.InputFormatError, Exception)


def test_input_validation_error_fields_locked():
    assert il.InputValidationError._fields == ("code", "detail")


def test_loaded_inputs_fields_locked():
    assert il.LoadedInputs._fields == ("config", "validation_errors")


def test_required_top_level_keys_locked():
    assert il.REQUIRED_TOP_LEVEL_KEYS == (
        "stage20_1_commit_sha",
        "stage20_2_commit_sha",
        "stage20_3_commit_sha",
        "stage20_2_run_dir",
        "stage20_3_run_dir",
        "repo_root",
        "output_root",
        "operator_test_results",
    )


def test_required_operator_fields_locked():
    assert il.REQUIRED_OPERATOR_FIELDS == (
        "test_command",
        "run1_passed",
        "run1_failed",
        "run1_errors",
        "run2_passed",
        "run2_failed",
        "run2_errors",
    )


# ---------------------------------------------------------------------------
# Valid config -> empty validation errors
# ---------------------------------------------------------------------------


def test_valid_config_returns_loaded_inputs_with_no_errors(
    valid_config_dict, write_config, frozen_clock,
):
    p = write_config(valid_config_dict)
    loaded = il.load_input_config(p, clock=frozen_clock)
    assert isinstance(loaded, il.LoadedInputs)
    assert isinstance(loaded.config, ClosureInputConfig)
    assert loaded.validation_errors == ()
    assert loaded.config.stage20_1_commit_sha == VALID_SHA_20_1
    assert loaded.config.stage20_2_commit_sha == VALID_SHA_20_2
    assert loaded.config.stage20_3_commit_sha == VALID_SHA_20_3
    assert loaded.config.operator_test_results.all_green is True
    assert loaded.config.operator_test_results.both_runs_match is True


def test_valid_config_paths_are_resolved_absolute(
    valid_config_dict, write_config, frozen_clock, valid_layout,
):
    p = write_config(valid_config_dict)
    loaded = il.load_input_config(p, clock=frozen_clock)
    assert loaded.config.stage20_2_run_dir.is_absolute()
    assert loaded.config.stage20_3_run_dir.is_absolute()
    assert loaded.config.repo_root.is_absolute()
    assert loaded.config.output_root.is_absolute()
    assert (
        loaded.config.stage20_2_run_dir
        == valid_layout["s2_dir"].resolve()
    )


def test_valid_config_generated_at_utc_comes_from_clock(
    valid_config_dict, write_config,
):
    fc = FrozenClock(
        datetime(2026, 9, 9, 1, 2, 3, tzinfo=timezone.utc),
    )
    p = write_config(valid_config_dict)
    loaded = il.load_input_config(p, clock=fc)
    assert loaded.config.generated_at_utc == "2026-09-09T01:02:03Z"


# ---------------------------------------------------------------------------
# InputFormatError -- file-level failures
# ---------------------------------------------------------------------------


def test_missing_config_file_raises_input_format_error(
    tmp_path, frozen_clock,
):
    p = tmp_path / "does_not_exist.json"
    with pytest.raises(il.InputFormatError, match="not found"):
        il.load_input_config(p, clock=frozen_clock)


def test_config_path_is_directory_raises_input_format_error(
    tmp_path, frozen_clock,
):
    d = tmp_path / "config_dir"
    d.mkdir()
    with pytest.raises(il.InputFormatError, match="not a regular file"):
        il.load_input_config(d, clock=frozen_clock)


def test_malformed_json_raises_input_format_error(
    tmp_path, frozen_clock,
):
    p = tmp_path / "config.json"
    p.write_text("{not json", encoding="utf-8")
    with pytest.raises(il.InputFormatError, match="not valid JSON"):
        il.load_input_config(p, clock=frozen_clock)


def test_config_root_not_an_object_raises_input_format_error(
    tmp_path, frozen_clock,
):
    p = tmp_path / "config.json"
    p.write_text("[1,2,3]", encoding="utf-8")
    with pytest.raises(il.InputFormatError, match="must be a JSON object"):
        il.load_input_config(p, clock=frozen_clock)


@pytest.mark.parametrize("missing_key", [
    "stage20_1_commit_sha",
    "stage20_2_commit_sha",
    "stage20_3_commit_sha",
    "stage20_2_run_dir",
    "stage20_3_run_dir",
    "repo_root",
    "output_root",
    "operator_test_results",
])
def test_missing_required_top_level_key_raises(
    valid_config_dict, write_config, frozen_clock, missing_key,
):
    d = dict(valid_config_dict)
    d.pop(missing_key)
    p = write_config(d)
    with pytest.raises(
        il.InputFormatError, match="missing required top-level key",
    ):
        il.load_input_config(p, clock=frozen_clock)


def test_operator_test_results_not_a_dict_raises(
    valid_config_dict, write_config, frozen_clock,
):
    d = dict(valid_config_dict)
    d["operator_test_results"] = ["not", "a", "dict"]
    p = write_config(d)
    with pytest.raises(
        il.InputFormatError,
        match="operator_test_results must be a JSON object",
    ):
        il.load_input_config(p, clock=frozen_clock)


# ---------------------------------------------------------------------------
# InputFormatError -- output_root precondition
# ---------------------------------------------------------------------------


def test_output_root_missing_raises_input_format_error(
    valid_config_dict, write_config, frozen_clock, tmp_path,
):
    d = dict(valid_config_dict)
    d["output_root"] = str(tmp_path / "does_not_exist")
    p = write_config(d)
    with pytest.raises(il.InputFormatError, match="does not exist"):
        il.load_input_config(p, clock=frozen_clock)


def test_output_root_is_a_file_not_a_directory_raises(
    valid_config_dict, write_config, frozen_clock, tmp_path,
):
    file_path = tmp_path / "i_am_a_file"
    file_path.write_text("hello", encoding="utf-8")
    d = dict(valid_config_dict)
    d["output_root"] = str(file_path)
    p = write_config(d)
    with pytest.raises(il.InputFormatError, match="not a directory"):
        il.load_input_config(p, clock=frozen_clock)


def test_output_root_non_string_raises(
    valid_config_dict, write_config, frozen_clock,
):
    d = dict(valid_config_dict)
    d["output_root"] = 12345
    p = write_config(d)
    with pytest.raises(
        il.InputFormatError, match="must be a string path",
    ):
        il.load_input_config(p, clock=frozen_clock)


def test_output_root_not_writable_raises(
    valid_config_dict, write_config, frozen_clock, monkeypatch,
):
    """Patch os.access in the input_loader module so the writability
    check fails on a directory that physically exists. Portable across
    POSIX / Windows file-system semantics."""
    monkeypatch.setattr(
        "PHX2.stage20.closure.input_loader.os.access",
        lambda p, mode: False,
    )
    p = write_config(valid_config_dict)
    with pytest.raises(il.InputFormatError, match="not writable"):
        il.load_input_config(p, clock=frozen_clock)


# ---------------------------------------------------------------------------
# E2044 -- commit SHA format
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("field", [
    "stage20_1_commit_sha",
    "stage20_2_commit_sha",
    "stage20_3_commit_sha",
])
def test_e2044_fires_for_uppercase_commit_sha(
    valid_config_dict, write_config, frozen_clock, field,
):
    d = dict(valid_config_dict)
    d[field] = "A" * 40
    p = write_config(d)
    loaded = il.load_input_config(p, clock=frozen_clock)
    codes = [e.code for e in loaded.validation_errors]
    assert "E2044" in codes
    # The detail mentions the specific field name.
    details = " ".join(
        e.detail for e in loaded.validation_errors if e.code == "E2044"
    )
    assert field in details


@pytest.mark.parametrize("bad_value", [
    "a" * 39,            # too short
    "a" * 41,            # too long
    "",                  # empty
    "g" * 40,            # non-hex
    "ABC" + "0" * 37,    # uppercase
    " " + "a" * 39,      # leading space
])
def test_e2044_fires_for_invalid_sha_value(
    valid_config_dict, write_config, frozen_clock, bad_value,
):
    d = dict(valid_config_dict)
    d["stage20_1_commit_sha"] = bad_value
    p = write_config(d)
    loaded = il.load_input_config(p, clock=frozen_clock)
    codes = [e.code for e in loaded.validation_errors]
    assert "E2044" in codes


def test_e2044_fires_for_non_string_commit_sha(
    valid_config_dict, write_config, frozen_clock,
):
    d = dict(valid_config_dict)
    d["stage20_2_commit_sha"] = 12345
    p = write_config(d)
    loaded = il.load_input_config(p, clock=frozen_clock)
    codes = [e.code for e in loaded.validation_errors]
    assert "E2044" in codes


def test_e2044_fires_independently_per_field(
    valid_config_dict, write_config, frozen_clock,
):
    """Three bad SHAs => three E2044 entries."""
    d = dict(valid_config_dict)
    d["stage20_1_commit_sha"] = "X" * 40
    d["stage20_2_commit_sha"] = "Y" * 40
    d["stage20_3_commit_sha"] = "Z" * 40
    p = write_config(d)
    loaded = il.load_input_config(p, clock=frozen_clock)
    e2044 = [e for e in loaded.validation_errors if e.code == "E2044"]
    assert len(e2044) == 3


# ---------------------------------------------------------------------------
# E2030 / E2031 -- run dirs
# ---------------------------------------------------------------------------


def test_e2030_fires_for_missing_stage20_2_run_dir(
    valid_config_dict, write_config, frozen_clock, tmp_path,
):
    d = dict(valid_config_dict)
    d["stage20_2_run_dir"] = str(tmp_path / "does_not_exist")
    p = write_config(d)
    loaded = il.load_input_config(p, clock=frozen_clock)
    codes = [e.code for e in loaded.validation_errors]
    assert "E2030" in codes


def test_e2030_fires_when_stage20_2_run_dir_is_a_file(
    valid_config_dict, write_config, frozen_clock, tmp_path,
):
    f = tmp_path / "i_am_a_file"
    f.write_text("hello", encoding="utf-8")
    d = dict(valid_config_dict)
    d["stage20_2_run_dir"] = str(f)
    p = write_config(d)
    loaded = il.load_input_config(p, clock=frozen_clock)
    codes = [e.code for e in loaded.validation_errors]
    assert "E2030" in codes


def test_e2031_fires_for_missing_stage20_3_run_dir(
    valid_config_dict, write_config, frozen_clock, tmp_path,
):
    d = dict(valid_config_dict)
    d["stage20_3_run_dir"] = str(tmp_path / "does_not_exist")
    p = write_config(d)
    loaded = il.load_input_config(p, clock=frozen_clock)
    codes = [e.code for e in loaded.validation_errors]
    assert "E2031" in codes


def test_e2030_fires_for_non_string_run_dir(
    valid_config_dict, write_config, frozen_clock,
):
    d = dict(valid_config_dict)
    d["stage20_2_run_dir"] = 42
    p = write_config(d)
    loaded = il.load_input_config(p, clock=frozen_clock)
    codes = [e.code for e in loaded.validation_errors]
    assert "E2030" in codes


# ---------------------------------------------------------------------------
# E2045 -- repo_root
# ---------------------------------------------------------------------------


def test_e2045_fires_when_repo_root_does_not_exist(
    valid_config_dict, write_config, frozen_clock, tmp_path,
):
    d = dict(valid_config_dict)
    d["repo_root"] = str(tmp_path / "no_such_repo")
    p = write_config(d)
    loaded = il.load_input_config(p, clock=frozen_clock)
    codes = [e.code for e in loaded.validation_errors]
    assert "E2045" in codes


def test_e2045_fires_when_repo_root_has_no_phx2_subdir(
    valid_config_dict, write_config, frozen_clock, tmp_path,
):
    fake_repo = tmp_path / "fake_repo"
    fake_repo.mkdir()
    d = dict(valid_config_dict)
    d["repo_root"] = str(fake_repo)
    p = write_config(d)
    loaded = il.load_input_config(p, clock=frozen_clock)
    codes = [e.code for e in loaded.validation_errors]
    assert "E2045" in codes


def test_e2045_fires_when_repo_root_is_non_string(
    valid_config_dict, write_config, frozen_clock,
):
    d = dict(valid_config_dict)
    d["repo_root"] = 42
    p = write_config(d)
    loaded = il.load_input_config(p, clock=frozen_clock)
    codes = [e.code for e in loaded.validation_errors]
    assert "E2045" in codes


# ---------------------------------------------------------------------------
# E2043 -- operator_test_results (consistency rules)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("missing_field", [
    "test_command",
    "run1_passed",
    "run1_failed",
    "run1_errors",
    "run2_passed",
    "run2_failed",
    "run2_errors",
])
def test_e2043_fires_for_missing_operator_test_result_field(
    valid_config_dict, write_config, frozen_clock, missing_field,
):
    d = dict(valid_config_dict)
    d["operator_test_results"] = dict(valid_config_dict["operator_test_results"])
    d["operator_test_results"].pop(missing_field)
    p = write_config(d)
    loaded = il.load_input_config(p, clock=frozen_clock)
    codes = [e.code for e in loaded.validation_errors]
    assert "E2043" in codes


def test_e2043_fires_for_empty_test_command(
    valid_config_dict, write_config, frozen_clock,
):
    d = dict(valid_config_dict)
    d["operator_test_results"] = dict(valid_config_dict["operator_test_results"])
    d["operator_test_results"]["test_command"] = ""
    p = write_config(d)
    loaded = il.load_input_config(p, clock=frozen_clock)
    codes = [e.code for e in loaded.validation_errors]
    assert "E2043" in codes


def test_e2043_fires_for_whitespace_only_test_command(
    valid_config_dict, write_config, frozen_clock,
):
    d = dict(valid_config_dict)
    d["operator_test_results"] = dict(valid_config_dict["operator_test_results"])
    d["operator_test_results"]["test_command"] = "   \t\n  "
    p = write_config(d)
    loaded = il.load_input_config(p, clock=frozen_clock)
    codes = [e.code for e in loaded.validation_errors]
    assert "E2043" in codes


def test_e2043_fires_for_non_string_test_command(
    valid_config_dict, write_config, frozen_clock,
):
    d = dict(valid_config_dict)
    d["operator_test_results"] = dict(valid_config_dict["operator_test_results"])
    d["operator_test_results"]["test_command"] = 12345
    p = write_config(d)
    loaded = il.load_input_config(p, clock=frozen_clock)
    codes = [e.code for e in loaded.validation_errors]
    assert "E2043" in codes


@pytest.mark.parametrize("field", [
    "run1_passed", "run1_failed", "run1_errors",
    "run2_passed", "run2_failed", "run2_errors",
])
def test_e2043_fires_for_negative_numeric_field(
    valid_config_dict, write_config, frozen_clock, field,
):
    d = dict(valid_config_dict)
    d["operator_test_results"] = dict(valid_config_dict["operator_test_results"])
    d["operator_test_results"][field] = -1
    p = write_config(d)
    loaded = il.load_input_config(p, clock=frozen_clock)
    codes = [e.code for e in loaded.validation_errors]
    assert "E2043" in codes


def test_e2043_fires_for_non_int_numeric_field(
    valid_config_dict, write_config, frozen_clock,
):
    d = dict(valid_config_dict)
    d["operator_test_results"] = dict(valid_config_dict["operator_test_results"])
    d["operator_test_results"]["run1_passed"] = "ten"
    p = write_config(d)
    loaded = il.load_input_config(p, clock=frozen_clock)
    codes = [e.code for e in loaded.validation_errors]
    assert "E2043" in codes


def test_e2043_fires_for_bool_numeric_field_rejecting_bool_subclass(
    valid_config_dict, write_config, frozen_clock,
):
    """bool is technically a subclass of int in Python; the loader must
    reject it explicitly so True/False don't sneak through as 1/0."""
    d = dict(valid_config_dict)
    d["operator_test_results"] = dict(valid_config_dict["operator_test_results"])
    d["operator_test_results"]["run1_passed"] = True
    p = write_config(d)
    loaded = il.load_input_config(p, clock=frozen_clock)
    codes = [e.code for e in loaded.validation_errors]
    assert "E2043" in codes


def test_e2043_fires_when_run1_has_failures(
    valid_config_dict, write_config, frozen_clock,
):
    d = dict(valid_config_dict)
    d["operator_test_results"] = dict(valid_config_dict["operator_test_results"])
    d["operator_test_results"]["run1_failed"] = 2
    p = write_config(d)
    loaded = il.load_input_config(p, clock=frozen_clock)
    codes = [e.code for e in loaded.validation_errors]
    assert "E2043" in codes


def test_e2043_fires_when_run2_has_errors(
    valid_config_dict, write_config, frozen_clock,
):
    d = dict(valid_config_dict)
    d["operator_test_results"] = dict(valid_config_dict["operator_test_results"])
    d["operator_test_results"]["run2_errors"] = 1
    p = write_config(d)
    loaded = il.load_input_config(p, clock=frozen_clock)
    codes = [e.code for e in loaded.validation_errors]
    assert "E2043" in codes


def test_e2043_fires_when_passed_counts_disagree(
    valid_config_dict, write_config, frozen_clock,
):
    d = dict(valid_config_dict)
    d["operator_test_results"] = dict(valid_config_dict["operator_test_results"])
    d["operator_test_results"]["run1_passed"] = 10
    d["operator_test_results"]["run2_passed"] = 11
    p = write_config(d)
    loaded = il.load_input_config(p, clock=frozen_clock)
    codes = [e.code for e in loaded.validation_errors]
    assert "E2043" in codes


def test_e2043_fires_when_both_passed_counts_are_zero(
    valid_config_dict, write_config, frozen_clock,
):
    d = dict(valid_config_dict)
    d["operator_test_results"] = dict(valid_config_dict["operator_test_results"])
    d["operator_test_results"]["run1_passed"] = 0
    d["operator_test_results"]["run2_passed"] = 0
    p = write_config(d)
    loaded = il.load_input_config(p, clock=frozen_clock)
    codes = [e.code for e in loaded.validation_errors]
    assert "E2043" in codes


# ---------------------------------------------------------------------------
# Derived OperatorTestResults fields (both_runs_match, all_green)
# ---------------------------------------------------------------------------


def test_derived_fields_all_green_when_both_runs_green(
    valid_config_dict, write_config, frozen_clock,
):
    p = write_config(valid_config_dict)
    loaded = il.load_input_config(p, clock=frozen_clock)
    assert loaded.config.operator_test_results.both_runs_match is True
    assert loaded.config.operator_test_results.all_green is True


def test_derived_fields_both_runs_match_false_when_passed_differs(
    valid_config_dict, write_config, frozen_clock,
):
    d = dict(valid_config_dict)
    d["operator_test_results"] = dict(valid_config_dict["operator_test_results"])
    d["operator_test_results"]["run1_passed"] = 9
    d["operator_test_results"]["run2_passed"] = 10
    p = write_config(d)
    loaded = il.load_input_config(p, clock=frozen_clock)
    assert loaded.config.operator_test_results.both_runs_match is False


def test_derived_fields_all_green_false_when_any_failure_present(
    valid_config_dict, write_config, frozen_clock,
):
    d = dict(valid_config_dict)
    d["operator_test_results"] = dict(valid_config_dict["operator_test_results"])
    d["operator_test_results"]["run1_failed"] = 1
    d["operator_test_results"]["run2_failed"] = 1
    p = write_config(d)
    loaded = il.load_input_config(p, clock=frozen_clock)
    # both_runs_match is True (same failures), but all_green is False.
    assert loaded.config.operator_test_results.both_runs_match is True
    assert loaded.config.operator_test_results.all_green is False


def test_derived_fields_all_green_false_when_zero_passed(
    valid_config_dict, write_config, frozen_clock,
):
    d = dict(valid_config_dict)
    d["operator_test_results"] = dict(valid_config_dict["operator_test_results"])
    d["operator_test_results"]["run1_passed"] = 0
    d["operator_test_results"]["run2_passed"] = 0
    p = write_config(d)
    loaded = il.load_input_config(p, clock=frozen_clock)
    assert loaded.config.operator_test_results.all_green is False


# ---------------------------------------------------------------------------
# Accumulation: multiple errors do not short-circuit
# ---------------------------------------------------------------------------


def test_multiple_e20xx_errors_accumulate(
    valid_config_dict, write_config, frozen_clock, tmp_path,
):
    """Combine: bad commit SHA + missing run dir + bad operator block.
    Expect at least one of each code in the returned tuple."""
    d = dict(valid_config_dict)
    d["stage20_1_commit_sha"] = "X" * 40
    d["stage20_2_run_dir"] = str(tmp_path / "no_such")
    d["operator_test_results"] = dict(valid_config_dict["operator_test_results"])
    d["operator_test_results"]["run1_failed"] = 3
    p = write_config(d)
    loaded = il.load_input_config(p, clock=frozen_clock)
    codes = {e.code for e in loaded.validation_errors}
    assert "E2044" in codes
    assert "E2030" in codes
    assert "E2043" in codes


def test_validation_errors_is_a_tuple_not_a_list(
    valid_config_dict, write_config, frozen_clock,
):
    p = write_config(valid_config_dict)
    loaded = il.load_input_config(p, clock=frozen_clock)
    assert isinstance(loaded.validation_errors, tuple)


# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------


def test_relative_stage20_2_run_dir_resolved_against_repo_root(
    valid_config_dict, write_config, frozen_clock, valid_layout,
    tmp_path,
):
    """A relative stage20_2_run_dir resolves against repo_root, NOT CWD.

    Layout: put a valid stage20_2_run_dir inside repo_root/PHX2/stage20_runs/X.
    Then point stage20_2_run_dir at "PHX2/stage20_runs/X" (relative).
    """
    repo = valid_layout["repo_root"]
    s2_rel = repo / "PHX2" / "stage20_runs" / "X"
    s2_rel.mkdir(parents=True)
    # stage20_3 must also exist for the run to validate cleanly; reuse
    # the prebuilt s3 path (absolute).
    d = dict(valid_config_dict)
    d["stage20_2_run_dir"] = "PHX2/stage20_runs/X"
    p = write_config(d)
    loaded = il.load_input_config(p, clock=frozen_clock)
    codes = [e.code for e in loaded.validation_errors]
    assert "E2030" not in codes
    assert loaded.config.stage20_2_run_dir == s2_rel.resolve()


def test_absolute_stage20_2_run_dir_resolved_in_place(
    valid_config_dict, write_config, frozen_clock, valid_layout,
):
    d = dict(valid_config_dict)
    d["stage20_2_run_dir"] = str(valid_layout["s2_dir"].resolve())
    p = write_config(d)
    loaded = il.load_input_config(p, clock=frozen_clock)
    assert loaded.config.stage20_2_run_dir == valid_layout["s2_dir"].resolve()


# ---------------------------------------------------------------------------
# compute_config_sha8 properties
# ---------------------------------------------------------------------------


def test_compute_config_sha8_returns_8_lowercase_hex_chars(
    valid_config_dict, write_config, frozen_clock,
):
    p = write_config(valid_config_dict)
    loaded = il.load_input_config(p, clock=frozen_clock)
    sha8 = il.compute_config_sha8(loaded.config)
    assert isinstance(sha8, str)
    assert len(sha8) == 8
    assert all(ch in "0123456789abcdef" for ch in sha8)


def test_compute_config_sha8_is_deterministic_for_same_input(
    valid_config_dict, write_config, frozen_clock,
):
    p = write_config(valid_config_dict)
    loaded = il.load_input_config(p, clock=frozen_clock)
    a = il.compute_config_sha8(loaded.config)
    b = il.compute_config_sha8(loaded.config)
    assert a == b


def test_compute_config_sha8_is_invariant_across_clock_changes(
    valid_config_dict, write_config,
):
    """generated_at_utc is excluded; two different clocks against the
    same config must yield the same digest."""
    p = write_config(valid_config_dict)
    clock_a = FrozenClock(
        datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc),
    )
    clock_b = FrozenClock(
        datetime(2027, 12, 31, 23, 59, 59, tzinfo=timezone.utc),
    )
    a = il.compute_config_sha8(
        il.load_input_config(p, clock=clock_a).config,
    )
    b = il.compute_config_sha8(
        il.load_input_config(p, clock=clock_b).config,
    )
    assert a == b


def test_compute_config_sha8_changes_when_commit_sha_changes(
    valid_config_dict, write_config, frozen_clock,
):
    p1 = write_config(valid_config_dict, name="cfg1.json")
    sha_first = il.compute_config_sha8(
        il.load_input_config(p1, clock=frozen_clock).config,
    )
    d2 = dict(valid_config_dict)
    d2["stage20_1_commit_sha"] = "f" * 40  # different valid hex sha
    p2 = write_config(d2, name="cfg2.json")
    sha_second = il.compute_config_sha8(
        il.load_input_config(p2, clock=frozen_clock).config,
    )
    assert sha_first != sha_second


def test_compute_config_sha8_changes_when_run_dir_changes(
    valid_config_dict, write_config, frozen_clock, tmp_path,
):
    other_dir = tmp_path / "other_stage20_2"
    other_dir.mkdir()
    p1 = write_config(valid_config_dict, name="cfg_a.json")
    sha_a = il.compute_config_sha8(
        il.load_input_config(p1, clock=frozen_clock).config,
    )
    d2 = dict(valid_config_dict)
    d2["stage20_2_run_dir"] = str(other_dir)
    p2 = write_config(d2, name="cfg_b.json")
    sha_b = il.compute_config_sha8(
        il.load_input_config(p2, clock=frozen_clock).config,
    )
    assert sha_a != sha_b


def test_compute_config_sha8_changes_when_test_command_changes(
    valid_config_dict, write_config, frozen_clock,
):
    p1 = write_config(valid_config_dict, name="cfg_a.json")
    sha_a = il.compute_config_sha8(
        il.load_input_config(p1, clock=frozen_clock).config,
    )
    d2 = dict(valid_config_dict)
    d2["operator_test_results"] = dict(valid_config_dict["operator_test_results"])
    d2["operator_test_results"]["test_command"] = "pytest -v"
    p2 = write_config(d2, name="cfg_b.json")
    sha_b = il.compute_config_sha8(
        il.load_input_config(p2, clock=frozen_clock).config,
    )
    assert sha_a != sha_b


# ---------------------------------------------------------------------------
# Phase 2 boundary: no manifest reading, no directory creation
# ---------------------------------------------------------------------------


def test_load_input_config_does_not_create_directories(
    valid_config_dict, write_config, frozen_clock, valid_layout,
):
    """After load_input_config returns, no new directories appear
    under output_root (Phase 2 boundary: no directory creation)."""
    out = valid_layout["output_root"]
    before = sorted(p.name for p in out.iterdir())
    p = write_config(valid_config_dict)
    il.load_input_config(p, clock=frozen_clock)
    after = sorted(p.name for p in out.iterdir())
    assert before == after


def test_load_input_config_does_not_open_manifest_files(
    valid_config_dict, write_config, frozen_clock, valid_layout,
):
    """Phase 2 must not read Stage 20.2 / Stage 20.3 manifests. Verify
    indirectly: load_input_config succeeds even when the run dirs are
    empty (no manifest files present)."""
    p = write_config(valid_config_dict)
    loaded = il.load_input_config(p, clock=frozen_clock)
    assert loaded.validation_errors == ()
    # Confirm the run dirs are still empty after load.
    assert list(valid_layout["s2_dir"].iterdir()) == [
        valid_layout["s2_dir"] / "stage20_3"
    ]
    assert list(valid_layout["s3_dir"].iterdir()) == []


# ---------------------------------------------------------------------------
# AST self-audit: input_loader.py must not import forbidden modules
# ---------------------------------------------------------------------------


def _collect_imports(tree: ast.AST) -> list[tuple[str, int]]:
    """Return (module_name, lineno) pairs for every import in the tree."""

    out: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.module is not None:
                out.append((node.module, node.lineno))
        elif isinstance(node, ast.Import):
            for alias in node.names:
                out.append((alias.name, node.lineno))
    return out


_FORBIDDEN_NETWORK = frozenset({
    "requests", "httpx", "aiohttp", "urllib3", "websockets",
    "grpc", "grpclib",
    "discord", "telegram", "telethon", "pyrogram",
})

_FORBIDDEN_INNER_ONLY = frozenset({
    "dotenv", "python_dotenv",
    "sqlite3", "aiosqlite",
    "subprocess",
    "git", "pygit2", "dulwich",
})

_FORBIDDEN_PHOENIX1 = frozenset({"phoenix1", "Phoenix1", "phx1"})


def _matches_any(name: str, blacklist: frozenset[str]) -> bool:
    """True iff ``name`` equals any blacklist entry OR begins with
    ``<entry>.``."""
    if name in blacklist:
        return True
    for b in blacklist:
        if name.startswith(b + "."):
            return True
    return False


def test_input_loader_has_no_forbidden_network_imports():
    tree = ast.parse(Path(il.__file__).read_text(encoding="utf-8"))
    for name, lineno in _collect_imports(tree):
        if _matches_any(name, _FORBIDDEN_NETWORK):
            pytest.fail(
                f"input_loader.py imports forbidden network module "
                f"{name!r} at line {lineno}"
            )


def test_input_loader_has_no_forbidden_inner_only_imports():
    """Inner scope forbids dotenv/sqlite3/subprocess/git/etc."""
    tree = ast.parse(Path(il.__file__).read_text(encoding="utf-8"))
    for name, lineno in _collect_imports(tree):
        if _matches_any(name, _FORBIDDEN_INNER_ONLY):
            pytest.fail(
                f"input_loader.py imports forbidden inner-only module "
                f"{name!r} at line {lineno}"
            )


def test_input_loader_has_no_phoenix1_imports():
    tree = ast.parse(Path(il.__file__).read_text(encoding="utf-8"))
    for name, lineno in _collect_imports(tree):
        if _matches_any(name, _FORBIDDEN_PHOENIX1):
            pytest.fail(
                f"input_loader.py imports Phoenix1 module "
                f"{name!r} at line {lineno}"
            )


def test_input_loader_does_not_import_phx2_stage20_outside_closure():
    """Boundary discipline: imports from PHX2.stage20.* must only
    target PHX2.stage20.closure.* ."""
    tree = ast.parse(Path(il.__file__).read_text(encoding="utf-8"))
    for name, lineno in _collect_imports(tree):
        if name.startswith("PHX2.stage20") and not name.startswith(
            "PHX2.stage20.closure"
        ):
            pytest.fail(
                f"input_loader.py imports {name!r} at line {lineno}; "
                f"closure modules may only import from "
                f"PHX2.stage20.closure.*"
            )


def test_input_loader_has_no_os_environ_or_getenv_calls():
    """Closure inner scope forbids env reads (treated as
    FORBIDDEN_NETWORK_IMPORT_FOUND with reason='env_read' by the
    Phase 3 auditor). Pin the invariant at Phase 2 already."""
    tree = ast.parse(Path(il.__file__).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        # os.environ access
        if isinstance(node, ast.Attribute):
            value = node.value
            if (
                isinstance(value, ast.Name)
                and value.id == "os"
                and node.attr == "environ"
            ):
                pytest.fail(
                    f"input_loader.py reads os.environ at line "
                    f"{node.lineno}"
                )
        # os.getenv(...) call
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute):
                if (
                    isinstance(func.value, ast.Name)
                    and func.value.id == "os"
                    and func.attr == "getenv"
                ):
                    pytest.fail(
                        f"input_loader.py calls os.getenv() at line "
                        f"{node.lineno}"
                    )


def test_input_loader_uses_os_access_for_writability_check():
    """The single os.access call site is the writability check on
    output_root. This pins that there is exactly one such call in
    the module (so future edits don't smuggle in additional os.*
    calls without review)."""
    src = Path(il.__file__).read_text(encoding="utf-8")
    tree = ast.parse(src)
    access_calls = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute):
                if (
                    isinstance(func.value, ast.Name)
                    and func.value.id == "os"
                    and func.attr == "access"
                ):
                    access_calls += 1
    assert access_calls == 1

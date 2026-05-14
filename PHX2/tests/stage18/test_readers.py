"""Phase 18.1 reader contract tests.

Each test constructs a Stage 17 output directory under tmp_path
(via the ``fixtures.stage17_outputs`` helpers) and either exercises
the happy path or mutates one specific file to trigger a
closed-set B-code error. No subprocess, no DB, no Stage 17 imports.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from PHX2.stage18.constants import (
    COARSE_COLUMNS,
    COARSE_FILENAME,
    DATA_QUALITY_FILENAME,
    HEADLINE_COLUMNS,
    HEADLINE_FILENAME,
    MANIFEST_FILENAME,
    REQUIRED_INPUT_FILES,
    UNEVALUABLE_BREAKDOWN_FILENAME,
    UNEVALUABLE_COLUMNS,
)
from PHX2.stage18.errors import Stage18Error
from PHX2.stage18.readers import load_stage17_input_dir
from PHX2.tests.stage18.fixtures.stage17_outputs import (
    write_csv_with_header,
    write_truncated_csv_row,
)


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_valid_minimal_stage17_output_loads(
    minimal_stage17_input_dir: Path,
) -> None:
    bundle = load_stage17_input_dir(minimal_stage17_input_dir)

    assert bundle.input_dir == minimal_stage17_input_dir
    assert bundle.manifest["schema_version"] == "stage17_run_manifest_v0"

    # Row counts from the minimal fixture.
    assert len(bundle.headline_rows) == 1
    assert len(bundle.coarse_rows) == 1
    assert len(bundle.unevaluable_rows) == 0
    assert len(bundle.data_quality_rows) == 4

    # Spot-check one cell on each non-empty CSV.
    assert bundle.headline_rows[0]["rule_id"] == "rule_minimal"
    assert bundle.coarse_rows[0]["descriptive_label"] == "HARMFUL"
    assert bundle.data_quality_rows[0]["scope_level"] == "global"

    # Per-file row counts surfaced for downstream manifest support.
    assert bundle.input_row_counts == {
        HEADLINE_FILENAME: 1,
        COARSE_FILENAME: 1,
        UNEVALUABLE_BREAKDOWN_FILENAME: 0,
        DATA_QUALITY_FILENAME: 4,
    }


def test_load_returns_dict_rows_keyed_by_full_column_tuple(
    minimal_stage17_input_dir: Path,
) -> None:
    bundle = load_stage17_input_dir(minimal_stage17_input_dir)

    assert tuple(bundle.headline_rows[0].keys()) == HEADLINE_COLUMNS
    assert tuple(bundle.coarse_rows[0].keys()) == COARSE_COLUMNS
    assert tuple(bundle.data_quality_rows[0].keys()) == (
        "scope_level",
        "policy_hash",
        "rule_id",
        "window_seconds",
        "metric_name",
        "metric_value",
    )


# ---------------------------------------------------------------------------
# B01 -- input contract violations
# ---------------------------------------------------------------------------


def test_missing_directory_raises_b01(tmp_path: Path) -> None:
    missing = tmp_path / "does_not_exist"
    with pytest.raises(Stage18Error) as exc_info:
        load_stage17_input_dir(missing)
    assert exc_info.value.code == "B01"


def test_directory_path_points_to_file_raises_b01(tmp_path: Path) -> None:
    not_a_dir = tmp_path / "i_am_a_file.txt"
    not_a_dir.write_text("hi", encoding="utf-8")
    with pytest.raises(Stage18Error) as exc_info:
        load_stage17_input_dir(not_a_dir)
    assert exc_info.value.code == "B01"


@pytest.mark.parametrize("missing_filename", REQUIRED_INPUT_FILES)
def test_missing_required_artifact_raises_b01(
    minimal_stage17_input_dir: Path, missing_filename: str
) -> None:
    (minimal_stage17_input_dir / missing_filename).unlink()
    with pytest.raises(Stage18Error) as exc_info:
        load_stage17_input_dir(minimal_stage17_input_dir)
    assert exc_info.value.code == "B01"
    assert missing_filename in str(exc_info.value)


def test_empty_headline_csv_no_header_raises_b01(
    minimal_stage17_input_dir: Path,
) -> None:
    (minimal_stage17_input_dir / HEADLINE_FILENAME).write_text(
        "", encoding="utf-8"
    )
    with pytest.raises(Stage18Error) as exc_info:
        load_stage17_input_dir(minimal_stage17_input_dir)
    assert exc_info.value.code == "B01"


def test_empty_coarse_csv_no_header_raises_b01(
    minimal_stage17_input_dir: Path,
) -> None:
    (minimal_stage17_input_dir / COARSE_FILENAME).write_text(
        "", encoding="utf-8"
    )
    with pytest.raises(Stage18Error) as exc_info:
        load_stage17_input_dir(minimal_stage17_input_dir)
    assert exc_info.value.code == "B01"


def test_empty_unevaluable_csv_no_header_raises_b01(
    minimal_stage17_input_dir: Path,
) -> None:
    """Even though header-only ``unevaluable_breakdown.csv`` is
    valid, a fully empty file (no header line) is still a contract
    violation."""

    (minimal_stage17_input_dir / UNEVALUABLE_BREAKDOWN_FILENAME).write_text(
        "", encoding="utf-8"
    )
    with pytest.raises(Stage18Error) as exc_info:
        load_stage17_input_dir(minimal_stage17_input_dir)
    assert exc_info.value.code == "B01"


def test_bad_headline_header_renamed_first_column_raises_b01(
    minimal_stage17_input_dir: Path,
) -> None:
    bad_header = list(HEADLINE_COLUMNS)
    bad_header[0] = "not_policy_hash"
    write_csv_with_header(
        minimal_stage17_input_dir / HEADLINE_FILENAME, bad_header
    )
    with pytest.raises(Stage18Error) as exc_info:
        load_stage17_input_dir(minimal_stage17_input_dir)
    assert exc_info.value.code == "B01"


def test_bad_coarse_header_extra_column_raises_b01(
    minimal_stage17_input_dir: Path,
) -> None:
    bad_header = list(COARSE_COLUMNS) + ["unexpected_extra"]
    write_csv_with_header(
        minimal_stage17_input_dir / COARSE_FILENAME, bad_header
    )
    with pytest.raises(Stage18Error) as exc_info:
        load_stage17_input_dir(minimal_stage17_input_dir)
    assert exc_info.value.code == "B01"


def test_bad_data_quality_header_reordered_raises_b01(
    minimal_stage17_input_dir: Path,
) -> None:
    """Header content matches but order does not -- B01 because
    the readers bind on the exact column tuple."""

    reordered = (
        "policy_hash",
        "scope_level",
        "rule_id",
        "window_seconds",
        "metric_name",
        "metric_value",
    )
    write_csv_with_header(
        minimal_stage17_input_dir / DATA_QUALITY_FILENAME, reordered
    )
    with pytest.raises(Stage18Error) as exc_info:
        load_stage17_input_dir(minimal_stage17_input_dir)
    assert exc_info.value.code == "B01"


def test_unevaluable_csv_header_only_is_accepted(
    minimal_stage17_input_dir: Path,
) -> None:
    """``unevaluable_breakdown.csv`` is allowed to have only its
    header line; this is the common case for runs with zero
    UNEVALUABLE evaluations."""

    write_csv_with_header(
        minimal_stage17_input_dir / UNEVALUABLE_BREAKDOWN_FILENAME,
        UNEVALUABLE_COLUMNS,
    )
    bundle = load_stage17_input_dir(minimal_stage17_input_dir)
    assert bundle.unevaluable_rows == ()


# ---------------------------------------------------------------------------
# B07 -- row column-count mismatch
# ---------------------------------------------------------------------------


def test_short_headline_row_raises_b07(
    minimal_stage17_input_dir: Path,
) -> None:
    write_truncated_csv_row(
        minimal_stage17_input_dir / HEADLINE_FILENAME,
        HEADLINE_COLUMNS,
        ["abc123def456", "rule_x"],  # 2 cells where 43 expected
    )
    with pytest.raises(Stage18Error) as exc_info:
        load_stage17_input_dir(minimal_stage17_input_dir)
    assert exc_info.value.code == "B07"


def test_long_coarse_row_raises_b07(
    minimal_stage17_input_dir: Path,
) -> None:
    extra = [
        "abc123def456", "rule_x", "3600", "1h",
        "1", "0", "1", "1",
        "0", "0", "0", "WEAK", "extra",  # 13 cells; expected 12
    ]
    lines = [",".join(COARSE_COLUMNS), ",".join(extra)]
    (minimal_stage17_input_dir / COARSE_FILENAME).write_text(
        "\n".join(lines) + "\n", encoding="utf-8", newline=""
    )
    with pytest.raises(Stage18Error) as exc_info:
        load_stage17_input_dir(minimal_stage17_input_dir)
    assert exc_info.value.code == "B07"


def test_b07_message_includes_line_number(
    minimal_stage17_input_dir: Path,
) -> None:
    write_truncated_csv_row(
        minimal_stage17_input_dir / COARSE_FILENAME,
        COARSE_COLUMNS,
        ["abc123def456"],
    )
    with pytest.raises(Stage18Error) as exc_info:
        load_stage17_input_dir(minimal_stage17_input_dir)
    # Header is line 1, the bad row is line 2.
    assert "coarse_summary.csv:2" in str(exc_info.value)


# ---------------------------------------------------------------------------
# B08 -- manifest JSON parse error
# ---------------------------------------------------------------------------


def test_bad_manifest_json_raises_b08(
    minimal_stage17_input_dir: Path,
) -> None:
    (minimal_stage17_input_dir / MANIFEST_FILENAME).write_text(
        "{not valid json", encoding="utf-8"
    )
    with pytest.raises(Stage18Error) as exc_info:
        load_stage17_input_dir(minimal_stage17_input_dir)
    assert exc_info.value.code == "B08"


def test_manifest_top_level_not_object_raises_b08(
    minimal_stage17_input_dir: Path,
) -> None:
    (minimal_stage17_input_dir / MANIFEST_FILENAME).write_text(
        '["a", "list", "not", "object"]', encoding="utf-8"
    )
    with pytest.raises(Stage18Error) as exc_info:
        load_stage17_input_dir(minimal_stage17_input_dir)
    assert exc_info.value.code == "B08"


# ---------------------------------------------------------------------------
# B02 -- manifest schema_version mismatch
# ---------------------------------------------------------------------------


def test_bad_manifest_schema_version_raises_b02(
    minimal_stage17_input_dir: Path,
) -> None:
    manifest_path = minimal_stage17_input_dir / MANIFEST_FILENAME
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload["schema_version"] = "stage17_run_manifest_v999"
    manifest_path.write_text(
        json.dumps(payload, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    with pytest.raises(Stage18Error) as exc_info:
        load_stage17_input_dir(minimal_stage17_input_dir)
    assert exc_info.value.code == "B02"


def test_missing_manifest_schema_version_raises_b02(
    minimal_stage17_input_dir: Path,
) -> None:
    manifest_path = minimal_stage17_input_dir / MANIFEST_FILENAME
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    del payload["schema_version"]
    manifest_path.write_text(
        json.dumps(payload, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    with pytest.raises(Stage18Error) as exc_info:
        load_stage17_input_dir(minimal_stage17_input_dir)
    assert exc_info.value.code == "B02"


def test_empty_manifest_file_raises_b01(
    minimal_stage17_input_dir: Path,
) -> None:
    """A truly empty manifest fails the contract check before JSON
    parsing kicks in (B01, not B08)."""

    (minimal_stage17_input_dir / MANIFEST_FILENAME).write_text(
        "", encoding="utf-8"
    )
    with pytest.raises(Stage18Error) as exc_info:
        load_stage17_input_dir(minimal_stage17_input_dir)
    assert exc_info.value.code == "B01"


def test_whitespace_only_manifest_raises_b01(
    minimal_stage17_input_dir: Path,
) -> None:
    (minimal_stage17_input_dir / MANIFEST_FILENAME).write_text(
        "   \n   \n", encoding="utf-8"
    )
    with pytest.raises(Stage18Error) as exc_info:
        load_stage17_input_dir(minimal_stage17_input_dir)
    assert exc_info.value.code == "B01"

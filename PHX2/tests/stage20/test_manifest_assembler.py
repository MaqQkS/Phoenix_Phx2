"""Stage 20.2 manifest assembler tests (Phase C).

Covers hash computation, run-id extraction, dict assembly, and the
shape validator (E2021 / E2024 / E2022).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from PHX2.stage20.constants import (
    CONSUMER_CONTRACT_VERSION,
    LABEL_TO_STATE_MAPPING_V0,
    MAPPING_VERSION,
    SAFE_FOR_LIVE_DISPATCH,
    STAGE20_MINOR_VERSION,
    STAGE20_VERSION,
)
from PHX2.stage20.errors import Stage20ValidationError
from PHX2.stage20.manifest_assembler import (
    assemble_manifest,
    compute_file_sha256,
    extract_stage18_run_id_from_stage19_manifest,
    extract_stage19_run_id,
    reconcile_output_artifacts,
    recompute_input_hashes,
    validate_manifest_shape,
    write_manifest_json,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _write(path: Path, content: bytes) -> Path:
    path.write_bytes(content)
    return path


def _stage19_manifest_with(
    path: Path,
    *,
    stage18_run_id: str = "s18_run_a",
    stage19_run_id: str = "s19_run_a",
    extra_keys: dict | None = None,
) -> Path:
    data = {
        "schema_version": "stage19_ledger_v1",
        "stage19_run_id": stage19_run_id,
        "stage18_run_id": stage18_run_id,
    }
    if extra_keys:
        data.update(extra_keys)
    path.write_bytes(json.dumps(data, sort_keys=True).encode("utf-8"))
    return path


# ---------------------------------------------------------------------------
# compute_file_sha256
# ---------------------------------------------------------------------------


def test_compute_file_sha256_matches_hashlib_expected(tmp_path):
    p = _write(tmp_path / "blob.bin", b"hello stage20")
    expected = hashlib.sha256(b"hello stage20").hexdigest()
    assert compute_file_sha256(p) == expected


def test_compute_file_sha256_deterministic_across_calls(tmp_path):
    p = _write(tmp_path / "x.bin", b"x" * 1024)
    a = compute_file_sha256(p)
    b = compute_file_sha256(p)
    assert a == b


# ---------------------------------------------------------------------------
# recompute_input_hashes
# ---------------------------------------------------------------------------


def test_recompute_input_hashes_returns_4_required_keys(tmp_path):
    s18m = _write(tmp_path / "s18_manifest.json", b'{"run_id":"a"}')
    s18rm = _write(tmp_path / "s18_rm.csv", b"policy_hash\nph_a\n")
    s19m = _write(tmp_path / "s19_manifest.json", b"{}")
    s19l = _write(tmp_path / "s19_ledger.csv", b"ledger_row_id\nx\n")

    hashes = recompute_input_hashes(s18m, s18rm, s19m, s19l)
    assert set(hashes.keys()) == {
        "stage18_manifest_sha256",
        "stage18_review_matrix_sha256",
        "stage19_ledger_sha256",
        "stage19_manifest_sha256",
    }
    assert all(isinstance(v, str) and len(v) == 64 for v in hashes.values())


def test_recompute_input_hashes_returns_5_keys_when_summary_provided(tmp_path):
    s18m = _write(tmp_path / "s18_manifest.json", b'{"run_id":"a"}')
    s18rm = _write(tmp_path / "s18_rm.csv", b"policy_hash\nph_a\n")
    s19m = _write(tmp_path / "s19_manifest.json", b"{}")
    s19l = _write(tmp_path / "s19_ledger.csv", b"ledger_row_id\nx\n")
    s19s = _write(tmp_path / "s19_summary.csv", b"stage18_run_id\nr1\n")

    hashes = recompute_input_hashes(s18m, s18rm, s19m, s19l, s19s)
    assert "stage19_summary_sha256" in hashes
    assert len(hashes) == 5


def test_recompute_input_hashes_is_deterministic(tmp_path):
    s18m = _write(tmp_path / "s18_manifest.json", b'{"run_id":"a"}')
    s18rm = _write(tmp_path / "s18_rm.csv", b"policy_hash\nph_a\n")
    s19m = _write(tmp_path / "s19_manifest.json", b"{}")
    s19l = _write(tmp_path / "s19_ledger.csv", b"ledger_row_id\nx\n")

    a = recompute_input_hashes(s18m, s18rm, s19m, s19l)
    b = recompute_input_hashes(s18m, s18rm, s19m, s19l)
    assert a == b


def test_recompute_input_hashes_raises_on_missing_file(tmp_path):
    s18m = _write(tmp_path / "s18_manifest.json", b'{"run_id":"a"}')
    s18rm = _write(tmp_path / "s18_rm.csv", b"policy_hash\nph_a\n")
    s19m = _write(tmp_path / "s19_manifest.json", b"{}")
    missing = tmp_path / "does_not_exist.csv"

    with pytest.raises(FileNotFoundError):
        recompute_input_hashes(s18m, s18rm, s19m, missing)


# ---------------------------------------------------------------------------
# Run-id extraction (operator decision B1-a)
# ---------------------------------------------------------------------------


def test_extract_stage18_run_id_from_stage19_manifest_reads_namespaced_key(
    tmp_path,
):
    p = _stage19_manifest_with(
        tmp_path / "s19m.json",
        stage18_run_id="s18_abc",
        stage19_run_id="s19_xyz",
    )
    assert extract_stage18_run_id_from_stage19_manifest(p) == "s18_abc"


def test_extract_stage19_run_id_reads_namespaced_key(tmp_path):
    p = _stage19_manifest_with(
        tmp_path / "s19m.json",
        stage18_run_id="s18_abc",
        stage19_run_id="s19_xyz",
    )
    assert extract_stage19_run_id(p) == "s19_xyz"


def test_extract_run_id_raises_on_missing_key(tmp_path):
    p = tmp_path / "s19m.json"
    p.write_bytes(b'{"schema_version":"stage19_ledger_v1"}')
    with pytest.raises(ValueError):
        extract_stage18_run_id_from_stage19_manifest(p)
    with pytest.raises(ValueError):
        extract_stage19_run_id(p)


def test_extract_run_id_raises_on_empty_string(tmp_path):
    p = tmp_path / "s19m.json"
    p.write_bytes(b'{"stage18_run_id":"","stage19_run_id":""}')
    with pytest.raises(ValueError):
        extract_stage18_run_id_from_stage19_manifest(p)


# ---------------------------------------------------------------------------
# assemble_manifest -- 19 top-level keys, label_mapping, etc.
# ---------------------------------------------------------------------------


def _example_assemble_kwargs():
    return dict(
        stage20_run_id="stage20_test_run_id",
        stage18_run_id="s18_run_a",
        stage19_run_id="s19_run_a",
        generated_at_utc="2026-05-15T00:00:00Z",
        input_hashes={
            "stage18_manifest_sha256": "a" * 64,
            "stage18_review_matrix_sha256": "b" * 64,
            "stage19_ledger_sha256": "c" * 64,
            "stage19_manifest_sha256": "d" * 64,
        },
        output_hashes={
            "preview_candidates_csv_sha256": "1" * 64,
            "alert_eligibility_decisions_csv_sha256": "2" * 64,
            "readme_md_sha256": "3" * 64,
            "stage20_run_log_sha256": "4" * 64,
        },
        preview_state_counts={
            "PREVIEW_ELIGIBLE": 1,
            "PREVIEW_OBSERVE_ONLY": 0,
            "PREVIEW_NEEDS_MORE_DATA": 0,
            "PREVIEW_EXCLUDED": 0,
        },
        preview_candidates_row_count=1,
        alert_eligibility_decisions_row_count=4,
        warnings_dict={
            "W2001_run_median_staleness_exceeded": False,
            "W2002_preview_eligible_count_zero": False,
            "W2003_tier_hint_missing_count": 0,
            "W2004_multiple_operators_per_review_slice_count": 0,
            "W2005_stage18_evidence_missing_for_review_count": 0,
            "W2006_candidate_review_stale_count": 0,
            "W2007_eligibility_mapping_drift_detected": False,
        },
    )


def test_assemble_manifest_has_exactly_19_top_level_keys():
    m = assemble_manifest(**_example_assemble_kwargs())
    expected = {
        "alert_eligibility_decisions_csv_sha256",
        "alert_eligibility_decisions_row_count",
        "consumer_contract_version",
        "generated_at_utc",
        "input_hashes",
        "label_mapping",
        "mapping_version",
        "preview_candidates_csv_sha256",
        "preview_candidates_row_count",
        "preview_state_counts",
        "readme_md_sha256",
        "safe_for_live_dispatch",
        "stage18_run_id",
        "stage19_run_id",
        "stage20_run_id",
        "stage20_run_log_sha256",
        "stage20_version",
        "stage20_minor_version",
        "warnings",
    }
    assert set(m.keys()) == expected
    assert len(m) == 19


def test_assemble_manifest_safe_for_live_dispatch_is_literal_python_false():
    m = assemble_manifest(**_example_assemble_kwargs())
    assert m["safe_for_live_dispatch"] is False
    # Also confirm the source constant.
    assert SAFE_FOR_LIVE_DISPATCH is False


def test_assemble_manifest_label_mapping_matches_locked_constant():
    m = assemble_manifest(**_example_assemble_kwargs())
    lm = m["label_mapping"]
    # str-Enum members compare equal to their str values.
    assert lm == dict(LABEL_TO_STATE_MAPPING_V0)
    # And as a pure-string dict.
    expected_str = {k: v.value for k, v in LABEL_TO_STATE_MAPPING_V0.items()}
    assert lm == expected_str


def test_assemble_manifest_input_hashes_4_keys_when_no_summary():
    m = assemble_manifest(**_example_assemble_kwargs())
    assert len(m["input_hashes"]) == 4
    assert "stage19_summary_sha256" not in m["input_hashes"]


def test_assemble_manifest_input_hashes_5_keys_when_summary_present():
    kwargs = _example_assemble_kwargs()
    kwargs["input_hashes"] = {
        **kwargs["input_hashes"],
        "stage19_summary_sha256": "5" * 64,
    }
    m = assemble_manifest(**kwargs)
    assert "stage19_summary_sha256" in m["input_hashes"]
    assert len(m["input_hashes"]) == 5


def test_assemble_manifest_warnings_has_exactly_7_keys():
    m = assemble_manifest(**_example_assemble_kwargs())
    expected = {
        "W2001_run_median_staleness_exceeded",
        "W2002_preview_eligible_count_zero",
        "W2003_tier_hint_missing_count",
        "W2004_multiple_operators_per_review_slice_count",
        "W2005_stage18_evidence_missing_for_review_count",
        "W2006_candidate_review_stale_count",
        "W2007_eligibility_mapping_drift_detected",
    }
    assert set(m["warnings"].keys()) == expected


def test_assemble_manifest_preview_state_counts_has_exactly_4_keys():
    m = assemble_manifest(**_example_assemble_kwargs())
    expected = {
        "PREVIEW_ELIGIBLE",
        "PREVIEW_OBSERVE_ONLY",
        "PREVIEW_NEEDS_MORE_DATA",
        "PREVIEW_EXCLUDED",
    }
    assert set(m["preview_state_counts"].keys()) == expected
    for v in m["preview_state_counts"].values():
        assert isinstance(v, int) and v >= 0


def test_assemble_manifest_W2003_tier_hint_missing_count_is_zero_in_v0():
    m = assemble_manifest(**_example_assemble_kwargs())
    assert m["warnings"]["W2003_tier_hint_missing_count"] == 0


def test_assemble_manifest_uses_locked_version_constants():
    m = assemble_manifest(**_example_assemble_kwargs())
    assert m["stage20_version"] == STAGE20_VERSION
    assert m["stage20_minor_version"] == STAGE20_MINOR_VERSION
    assert m["mapping_version"] == MAPPING_VERSION
    assert m["consumer_contract_version"] == CONSUMER_CONTRACT_VERSION


# ---------------------------------------------------------------------------
# validate_manifest_shape -- E2021 / E2024 / E2022
# ---------------------------------------------------------------------------


def test_validate_manifest_shape_passes_on_clean_manifest():
    m = assemble_manifest(**_example_assemble_kwargs())
    validate_manifest_shape(m)  # no raise


def test_validate_manifest_shape_raises_e2021_on_missing_input_hash_key():
    m = assemble_manifest(**_example_assemble_kwargs())
    # Drop one of the 4 required input hash keys.
    del m["input_hashes"]["stage19_ledger_sha256"]
    with pytest.raises(Stage20ValidationError) as exc:
        validate_manifest_shape(m)
    assert exc.value.code == "E2021"
    assert "E2021" in str(exc.value)


def test_validate_manifest_shape_raises_e2021_on_missing_input_hashes_object():
    m = assemble_manifest(**_example_assemble_kwargs())
    del m["input_hashes"]
    with pytest.raises(Stage20ValidationError) as exc:
        validate_manifest_shape(m)
    assert exc.value.code == "E2021"


def test_validate_manifest_shape_raises_e2024_on_missing_output_hash():
    m = assemble_manifest(**_example_assemble_kwargs())
    del m["alert_eligibility_decisions_csv_sha256"]
    with pytest.raises(Stage20ValidationError) as exc:
        validate_manifest_shape(m)
    assert exc.value.code == "E2024"
    assert "E2024" in str(exc.value)


def test_validate_manifest_shape_raises_e2022_on_safe_dispatch_true():
    """E2022 negative coverage -- the Phase C spec line "Asserts
    safe_for_live_dispatch is exactly False" is implemented inside
    validate_manifest_shape. This test exercises that locked-by-spec
    branch and is NOT a new validator added just for the test.
    """

    m = assemble_manifest(**_example_assemble_kwargs())
    m["safe_for_live_dispatch"] = True  # simulate a regression
    with pytest.raises(Stage20ValidationError) as exc:
        validate_manifest_shape(m)
    assert exc.value.code == "E2022"


def test_validate_manifest_shape_raises_e2022_on_safe_dispatch_truthy_string():
    """``is False`` identity check rejects ``"false"`` (string) too."""

    m = assemble_manifest(**_example_assemble_kwargs())
    m["safe_for_live_dispatch"] = "false"
    with pytest.raises(Stage20ValidationError) as exc:
        validate_manifest_shape(m)
    assert exc.value.code == "E2022"


# ---------------------------------------------------------------------------
# write_manifest_json -- serialization shape
# ---------------------------------------------------------------------------


def test_write_manifest_json_produces_sort_keys_compact_lf(tmp_path):
    m = assemble_manifest(**_example_assemble_kwargs())
    p = tmp_path / "manifest.json"
    write_manifest_json(p, m)
    raw = p.read_bytes()
    assert raw.endswith(b"\n")
    text = raw.decode("utf-8")
    # Compact separators -- no ', ' or ': '.
    assert ", " not in text
    assert ": " not in text
    # Parses back to an equal dict (modulo str-Enum coercion for label_mapping).
    parsed = json.loads(text)
    assert parsed["stage20_run_id"] == m["stage20_run_id"]
    assert parsed["safe_for_live_dispatch"] is False


def test_write_manifest_json_contains_exact_safe_for_live_dispatch_substring(
    tmp_path,
):
    """Phase C test 41 -- exact compact substring exists."""

    m = assemble_manifest(**_example_assemble_kwargs())
    p = tmp_path / "manifest.json"
    write_manifest_json(p, m)
    text = p.read_text(encoding="utf-8")
    assert '"safe_for_live_dispatch":false' in text


# ---------------------------------------------------------------------------
# Codex remediation: E2023 / E2025 negatives against
# reconcile_output_artifacts (the post-write reconciliation path).
# ---------------------------------------------------------------------------


def _write_clean_preview_csv(path: Path, *, row_count: int) -> None:
    """Write a header-+-N-rows preview_candidates.csv with the
    locked 18 columns. Rows are minimally populated so the data
    parses but is not otherwise meaningful.
    """

    from PHX2.stage20.constants import PREVIEW_CANDIDATES_CSV_COLUMNS

    with path.open("w", encoding="utf-8", newline="") as f:
        import csv as _csv

        w = _csv.writer(
            f, quoting=_csv.QUOTE_MINIMAL, lineterminator="\n",
        )
        w.writerow(list(PREVIEW_CANDIDATES_CSV_COLUMNS))
        for i in range(row_count):
            # Pad each row with empty cells; the reconciliation
            # function only inspects header + row count.
            w.writerow([
                f"cand_{i:016d}" if c == "candidate_id" else ""
                for c in PREVIEW_CANDIDATES_CSV_COLUMNS
            ])


def _write_clean_decisions_csv(path: Path, *, row_count: int) -> None:
    from PHX2.stage20.constants import (
        ALERT_ELIGIBILITY_DECISIONS_CSV_COLUMNS,
    )

    with path.open("w", encoding="utf-8", newline="") as f:
        import csv as _csv

        w = _csv.writer(
            f, quoting=_csv.QUOTE_MINIMAL, lineterminator="\n",
        )
        w.writerow(list(ALERT_ELIGIBILITY_DECISIONS_CSV_COLUMNS))
        for i in range(row_count):
            w.writerow([
                f"dec_{i:016d}" if c == "decision_id" else ""
                for c in ALERT_ELIGIBILITY_DECISIONS_CSV_COLUMNS
            ])


def _stub_manifest(
    *,
    preview_row_count: int,
    decisions_row_count: int,
) -> dict[str, object]:
    return {
        "preview_candidates_row_count": preview_row_count,
        "alert_eligibility_decisions_row_count": decisions_row_count,
    }


def test_reconcile_e2023_preview_row_count_mismatch(tmp_path):
    """Tamper: manifest claims 999 preview rows, the CSV has 1."""

    run_dir = tmp_path / "run"
    run_dir.mkdir()
    _write_clean_preview_csv(run_dir / "preview_candidates.csv", row_count=1)
    _write_clean_decisions_csv(
        run_dir / "alert_eligibility_decisions.csv", row_count=4,
    )
    manifest = _stub_manifest(
        preview_row_count=999, decisions_row_count=4,
    )
    with pytest.raises(Stage20ValidationError) as exc:
        reconcile_output_artifacts(manifest, run_dir)
    assert exc.value.code == "E2023"
    assert "preview_candidates_row_count" in str(exc.value)


def test_reconcile_e2023_decisions_row_count_mismatch(tmp_path):
    """Tamper: manifest claims 999 decision rows, the CSV has 4."""

    run_dir = tmp_path / "run"
    run_dir.mkdir()
    _write_clean_preview_csv(run_dir / "preview_candidates.csv", row_count=1)
    _write_clean_decisions_csv(
        run_dir / "alert_eligibility_decisions.csv", row_count=4,
    )
    manifest = _stub_manifest(
        preview_row_count=1, decisions_row_count=999,
    )
    with pytest.raises(Stage20ValidationError) as exc:
        reconcile_output_artifacts(manifest, run_dir)
    assert exc.value.code == "E2023"
    assert "alert_eligibility_decisions_row_count" in str(exc.value)


def test_reconcile_e2025_preview_missing_required_column(tmp_path):
    """Tamper: write preview_candidates.csv with a header missing
    one required column.
    """

    run_dir = tmp_path / "run"
    run_dir.mkdir()
    # Header missing "preview_state" column.
    (run_dir / "preview_candidates.csv").write_bytes(
        b"candidate_id,stage20_run_id\n"
    )
    _write_clean_decisions_csv(
        run_dir / "alert_eligibility_decisions.csv", row_count=0,
    )
    manifest = _stub_manifest(
        preview_row_count=0, decisions_row_count=0,
    )
    with pytest.raises(Stage20ValidationError) as exc:
        reconcile_output_artifacts(manifest, run_dir)
    assert exc.value.code == "E2025"
    assert "preview_candidates.csv" in str(exc.value)


def test_reconcile_e2025_decisions_missing_required_column(tmp_path):
    """Tamper: write alert_eligibility_decisions.csv with a header
    missing one required column.
    """

    run_dir = tmp_path / "run"
    run_dir.mkdir()
    _write_clean_preview_csv(
        run_dir / "preview_candidates.csv", row_count=0,
    )
    # Header missing "decision_outcome".
    (run_dir / "alert_eligibility_decisions.csv").write_bytes(
        b"decision_id,candidate_id\n"
    )
    manifest = _stub_manifest(
        preview_row_count=0, decisions_row_count=0,
    )
    with pytest.raises(Stage20ValidationError) as exc:
        reconcile_output_artifacts(manifest, run_dir)
    assert exc.value.code == "E2025"
    assert "alert_eligibility_decisions.csv" in str(exc.value)


def test_reconcile_passes_on_clean_synthetic_run(tmp_path):
    """Positive coverage: reconciliation accepts a clean run dir."""

    run_dir = tmp_path / "run"
    run_dir.mkdir()
    _write_clean_preview_csv(
        run_dir / "preview_candidates.csv", row_count=3,
    )
    _write_clean_decisions_csv(
        run_dir / "alert_eligibility_decisions.csv", row_count=12,
    )
    manifest = _stub_manifest(
        preview_row_count=3, decisions_row_count=12,
    )
    reconcile_output_artifacts(manifest, run_dir)  # no raise

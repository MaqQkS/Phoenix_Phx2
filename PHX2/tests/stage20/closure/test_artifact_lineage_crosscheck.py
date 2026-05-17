"""Stage 20.4 artifact-validator lineage crosscheck tests.

Cover the Stage 20.3 -> Stage 20.2 lineage hash crosscheck:

  * Clean fixture: lineage_crosscheck_passed is True; no E2036.
  * Each individual lineage hash field, when mutated to mismatch
    the actual Stage 20.2 file hash, fires E2036 with the
    artifact name + both hashes in the detail string.
  * Missing entire ``stage20_2_lineage`` block: E2036.
  * ``stage20_2_lineage`` not a JSON object: E2036.
  * Individual lineage hash field missing: E2036.
  * Lineage records a hash for a Stage 20.2 file that no longer
    exists: E2036 (lineage-vs-actual divergence).
  * Multiple mismatches accumulate (every bad field fires its own
    E2036).
"""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest

from PHX2.stage20.closure import artifact_validator as av


_FIXTURES_ROOT = Path(__file__).parent / "fixtures"
_STAGE20_2_CLEAN_SRC = _FIXTURES_ROOT / "stage20_2_clean"
_STAGE20_3_CLEAN_SRC = _FIXTURES_ROOT / "stage20_3_clean"


def _copy_pair(tmp_path: Path) -> tuple[Path, Path]:
    s2 = tmp_path / "stage20_2"
    s3 = tmp_path / "stage20_3"
    shutil.copytree(_STAGE20_2_CLEAN_SRC, s2)
    shutil.copytree(_STAGE20_3_CLEAN_SRC, s3)
    return s2, s3


def _load_s3_manifest(s3: Path) -> dict:
    return json.loads(
        (s3 / "stage20_3_manifest.json").read_text(encoding="utf-8")
    )


def _write_s3_manifest(s3: Path, data: dict) -> None:
    (s3 / "stage20_3_manifest.json").write_text(
        json.dumps(data), encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Clean fixture passes the lineage crosscheck
# ---------------------------------------------------------------------------


def test_clean_fixture_lineage_crosscheck_passes(tmp_path: Path):
    s2, s3 = _copy_pair(tmp_path)
    outcome = av.validate_artifacts(s2, s3)
    assert outcome.result.lineage_crosscheck_passed is True
    assert not any(e.code == "E2036" for e in outcome.errors)


# ---------------------------------------------------------------------------
# Per-field hash mismatch (E2036)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("field_name,artifact_filename", [
    ("manifest_json_sha256", "manifest.json"),
    ("preview_candidates_csv_sha256", "preview_candidates.csv"),
    ("alert_eligibility_decisions_csv_sha256",
     "alert_eligibility_decisions.csv"),
    ("readme_md_sha256", "README.md"),
    ("stage20_run_log_sha256", "stage20_run.log"),
])
def test_lineage_hash_mismatch_fires_e2036(
    tmp_path: Path, field_name, artifact_filename,
):
    """Flip one lineage hash to a wrong value and confirm E2036
    fires with the correct artifact name in the detail."""
    s2, s3 = _copy_pair(tmp_path)
    data = _load_s3_manifest(s3)
    bad_hash = "0" * 64
    data["stage20_2_lineage"][field_name] = bad_hash
    _write_s3_manifest(s3, data)

    outcome = av.validate_artifacts(s2, s3)
    e2036 = [e for e in outcome.errors if e.code == "E2036"]
    assert len(e2036) >= 1
    # At least one E2036 mentions this artifact filename in detail.
    assert any(artifact_filename in e.detail for e in e2036)
    # And the bad hash appears in the detail too.
    assert any(bad_hash in e.detail for e in e2036)
    assert outcome.result.lineage_crosscheck_passed is False


@pytest.mark.parametrize("field_name", [
    "manifest_json_sha256",
    "preview_candidates_csv_sha256",
    "alert_eligibility_decisions_csv_sha256",
    "readme_md_sha256",
    "stage20_run_log_sha256",
])
def test_lineage_hash_missing_field_fires_e2036(
    tmp_path: Path, field_name,
):
    """Dropping one lineage field from the manifest fires E2036."""
    s2, s3 = _copy_pair(tmp_path)
    data = _load_s3_manifest(s3)
    data["stage20_2_lineage"].pop(field_name)
    _write_s3_manifest(s3, data)

    outcome = av.validate_artifacts(s2, s3)
    e2036 = [e for e in outcome.errors if e.code == "E2036"]
    assert any(field_name in e.detail for e in e2036), e2036


# ---------------------------------------------------------------------------
# Missing or malformed stage20_2_lineage block (E2036)
# ---------------------------------------------------------------------------


def test_lineage_block_missing_fires_e2036(tmp_path: Path):
    s2, s3 = _copy_pair(tmp_path)
    data = _load_s3_manifest(s3)
    data.pop("stage20_2_lineage")
    _write_s3_manifest(s3, data)

    outcome = av.validate_artifacts(s2, s3)
    e2036 = [e for e in outcome.errors if e.code == "E2036"]
    assert len(e2036) >= 1
    assert any("stage20_2_lineage" in e.detail for e in e2036)
    assert outcome.result.lineage_crosscheck_passed is False


def test_lineage_block_not_a_dict_fires_e2036(tmp_path: Path):
    """If ``stage20_2_lineage`` is e.g. a list, E2036 fires."""
    s2, s3 = _copy_pair(tmp_path)
    data = _load_s3_manifest(s3)
    data["stage20_2_lineage"] = ["not", "a", "dict"]
    _write_s3_manifest(s3, data)

    outcome = av.validate_artifacts(s2, s3)
    e2036 = [e for e in outcome.errors if e.code == "E2036"]
    assert len(e2036) >= 1
    assert outcome.result.lineage_crosscheck_passed is False


# ---------------------------------------------------------------------------
# Lineage records hash for a Stage 20.2 file that is now missing (E2036)
# ---------------------------------------------------------------------------


def test_lineage_recorded_for_missing_file_fires_e2036(tmp_path: Path):
    """The 20.3 lineage block records hashes for all 5 standard
    Stage 20.2 artifacts. If one of those files is missing from
    the actual Stage 20.2 run dir, the crosscheck records E2036
    (lineage-vs-actual divergence)."""
    s2, s3 = _copy_pair(tmp_path)
    (s2 / "preview_candidates.csv").unlink()

    outcome = av.validate_artifacts(s2, s3)
    e2036 = [e for e in outcome.errors if e.code == "E2036"]
    # Crosscheck for the missing file fires.
    assert any(
        "preview_candidates.csv" in e.detail and "missing" in e.detail
        for e in e2036
    )
    # E2034 also fires separately (missing required Stage 20.2
    # artifact), but that's tested elsewhere.
    assert outcome.result.lineage_crosscheck_passed is False


def test_lineage_recorded_for_missing_optional_readme_fires_e2036(
    tmp_path: Path,
):
    """README is OPTIONAL for Stage 20.2 (missing => W2021), but the
    Stage 20.3 lineage records its hash. If README is deleted, the
    crosscheck still fires E2036 because the recorded hash describes
    a file that no longer exists."""
    s2, s3 = _copy_pair(tmp_path)
    (s2 / "README.md").unlink()

    outcome = av.validate_artifacts(s2, s3)
    e2036 = [e for e in outcome.errors if e.code == "E2036"]
    assert any(
        "README.md" in e.detail and "missing" in e.detail
        for e in e2036
    )
    # W2021 also fires.
    codes_w = [w.code for w in outcome.warnings]
    assert "W2021" in codes_w


# ---------------------------------------------------------------------------
# Accumulation: multiple lineage errors all fire
# ---------------------------------------------------------------------------


def test_multiple_lineage_mismatches_all_fire_e2036(tmp_path: Path):
    s2, s3 = _copy_pair(tmp_path)
    data = _load_s3_manifest(s3)
    # Mutate three lineage hashes simultaneously.
    data["stage20_2_lineage"]["manifest_json_sha256"] = "a" * 64
    data["stage20_2_lineage"]["preview_candidates_csv_sha256"] = "b" * 64
    data["stage20_2_lineage"]["readme_md_sha256"] = "c" * 64
    _write_s3_manifest(s3, data)

    outcome = av.validate_artifacts(s2, s3)
    e2036 = [e for e in outcome.errors if e.code == "E2036"]
    # Expect (at least) three E2036 entries, one per mismatched
    # artifact.
    assert len(e2036) >= 3
    detail_text = " | ".join(e.detail for e in e2036)
    assert "manifest.json" in detail_text
    assert "preview_candidates.csv" in detail_text
    assert "README.md" in detail_text


# ---------------------------------------------------------------------------
# Crosscheck behavior with malformed Stage 20.3 manifest
# ---------------------------------------------------------------------------


def test_lineage_crosscheck_returns_failed_when_s3_manifest_malformed(
    tmp_path: Path,
):
    """If Stage 20.3 manifest doesn't parse, lineage crosscheck
    cannot run; lineage_crosscheck_passed is False and no extra
    E2036 fires beyond the E2033 already recorded."""
    s2, s3 = _copy_pair(tmp_path)
    (s3 / "stage20_3_manifest.json").write_text(
        "this is not json", encoding="utf-8",
    )
    outcome = av.validate_artifacts(s2, s3)
    codes = [e.code for e in outcome.errors]
    assert "E2033" in codes
    assert outcome.result.lineage_crosscheck_passed is False


# ---------------------------------------------------------------------------
# Direct crosscheck helper exposure
# ---------------------------------------------------------------------------


def test_crosscheck_helper_returns_passed_for_clean_fixture(tmp_path: Path):
    s2, s3 = _copy_pair(tmp_path)
    s3_manifest = _load_s3_manifest(s3)
    result = av.crosscheck_stage20_2_lineage(s3_manifest, s2)
    assert result.passed is True
    assert result.errors == ()


def test_crosscheck_helper_returns_passed_false_on_mismatch(tmp_path: Path):
    s2, s3 = _copy_pair(tmp_path)
    s3_manifest = _load_s3_manifest(s3)
    s3_manifest["stage20_2_lineage"]["manifest_json_sha256"] = "0" * 64
    result = av.crosscheck_stage20_2_lineage(s3_manifest, s2)
    assert result.passed is False
    assert len(result.errors) >= 1
    assert all(e.code == "E2036" for e in result.errors)


def test_crosscheck_helper_handles_none_manifest_data():
    """Passing None (Stage 20.3 manifest didn't parse) returns
    passed=False with no E2036 errors of its own."""
    result = av.crosscheck_stage20_2_lineage(None, Path("/nonexistent"))
    assert result.passed is False
    assert result.errors == ()

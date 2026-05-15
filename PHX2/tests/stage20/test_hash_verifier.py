"""Tests for Stage 20 hash verifier (20.1.B).

E2003 is ACTIVE in 20.1: Stage 18 manifest + review_matrix
hashes are verified against the SHA-256 values recorded in
Stage 19's manifest.

E2004 is DEFINED-but-DEFERRED in 20.1: there is no source-of-truth
hash for the Stage 19 ledger anywhere in the current pipeline.
"""

from __future__ import annotations

import json

import pytest

from PHX2.stage20.constants import (
    CODES_ACTIVE_IN_STAGE_20_1,
    CODES_DEFERRED_IN_STAGE_20_1,
    EligibilityErrorCode,
)
from PHX2.stage20.input_validators import (
    locate_stage18_run,
    locate_stage19_run,
    verify_input_hashes,
)
from PHX2.tests.stage20.fixtures.stage18_outputs import (
    write_minimal_stage18_dir,
)
from PHX2.tests.stage20.fixtures.stage19_outputs import (
    write_minimal_stage19_dir,
)


def test_verify_input_hashes_passes_on_matching_fixture(tmp_path):
    s18 = tmp_path / "stage18"
    s19 = tmp_path / "stage19"
    write_minimal_stage18_dir(s18)
    write_minimal_stage19_dir(s19, stage18_dir=s18)

    s18_files = locate_stage18_run(s18)
    s19_files = locate_stage19_run(s19)

    errors = verify_input_hashes(s18_files, s19_files)
    assert errors == []


def test_verify_input_hashes_returns_e2003_on_review_matrix_tamper(tmp_path):
    s18 = tmp_path / "stage18"
    s19 = tmp_path / "stage19"
    write_minimal_stage18_dir(s18)
    write_minimal_stage19_dir(s19, stage18_dir=s18)

    # Tamper with the review_matrix AFTER Stage 19 has recorded its hash
    review_matrix_path = s18 / "review_matrix.csv"
    original = review_matrix_path.read_text(encoding="utf-8")
    review_matrix_path.write_text(original + "\n", encoding="utf-8")

    s18_files = locate_stage18_run(s18)
    s19_files = locate_stage19_run(s19)

    errors = verify_input_hashes(s18_files, s19_files)
    assert EligibilityErrorCode.E2003 in errors


def test_verify_input_hashes_returns_e2003_on_manifest_tamper(tmp_path):
    s18 = tmp_path / "stage18"
    s19 = tmp_path / "stage19"
    write_minimal_stage18_dir(s18)
    write_minimal_stage19_dir(s19, stage18_dir=s18)

    # Tamper with the Stage 18 manifest after Stage 19 captured the hash
    manifest_path = s18 / "manifest.json"
    raw = manifest_path.read_text(encoding="utf-8")
    parsed = json.loads(raw)
    parsed["run_started_utc"] = "tampered"
    tampered = json.dumps(
        parsed, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    manifest_path.write_text(tampered, encoding="utf-8")

    s18_files = locate_stage18_run(s18)
    s19_files = locate_stage19_run(s19)

    errors = verify_input_hashes(s18_files, s19_files)
    assert EligibilityErrorCode.E2003 in errors


def test_verify_input_hashes_no_op_when_stage19_manifest_lacks_hash_keys(tmp_path):
    """If Stage 19's manifest omits the hash fields, verify returns []."""

    s18 = tmp_path / "stage18"
    s19 = tmp_path / "stage19"
    write_minimal_stage18_dir(s18)

    s19.mkdir()
    minimal_manifest = {
        "stage19_schema_version": "stage19_ledger_v1",
        "stage19_run_id": "1234567890abcdef",
    }
    (s19 / "manifest.json").write_text(
        json.dumps(minimal_manifest), encoding="utf-8"
    )
    (s19 / "operator_review_ledger.csv").write_text(
        "stage19_run_id,ledger_row_id\n", encoding="utf-8"
    )

    s18_files = locate_stage18_run(s18)
    s19_files = locate_stage19_run(s19)

    errors = verify_input_hashes(s18_files, s19_files)
    assert errors == []


def test_e2004_defined_but_not_exercised_in_20_1():
    """E2004 remains in the enum; Stage 20.1 does not emit it.

    No source-of-truth hash for the Stage 19 ledger exists
    anywhere in the current pipeline (Stage 19's manifest records
    input-side hashes only, not output hashes). This is a
    documented scope deferral surfaced in the STEP 0 report.
    """

    assert EligibilityErrorCode.E2004.value not in CODES_ACTIVE_IN_STAGE_20_1
    assert EligibilityErrorCode.E2004.value in CODES_DEFERRED_IN_STAGE_20_1

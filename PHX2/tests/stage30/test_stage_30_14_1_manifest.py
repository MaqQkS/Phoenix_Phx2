"""Stage 30.14.1 manifest + spec-lock pin tests.

Pins the constants-only manifest against the Stage 30.14.1 models module (schema versions,
caps, redaction statuses, required-field list) and the committed Stage 29.5 sources
(COMPLETE / SAFE / PRESENT tokens), validates the inventory + two-tier allowlist
self-consistency, and checks the manifest module's own hygiene (constants-only, no PHX2
import, no top-level Call, no scheme literal) + the spec-lock doc presence.
"""

from __future__ import annotations

import ast
from pathlib import Path

from PHX2.stage29.stage29_5_migration_models import (
    MEASUREMENT_STATUS_COMPLETE,
    MIGRATION_STATUS_PRESENT,
    REDACTION_STATUS_SAFE,
)
from PHX2.stage30 import stage30_14_1_evidence_artifact_models as models
from PHX2.stage30 import stage30_14_1_manifest as manifest


PHX2_ROOT: Path = Path(__file__).resolve().parent.parent.parent
STAGE30_ROOT: Path = PHX2_ROOT / "stage30"
TESTS_STAGE30_ROOT: Path = PHX2_ROOT / "tests" / "stage30"


# ---------------------------------------------------------------------------
# 1. Schema / cap / redaction / field pins vs the models leaf
# ---------------------------------------------------------------------------


def test_schema_versions_match_models() -> None:
    assert (
        manifest.BUILD26_1_CAPTURE_EVIDENCE_SCHEMA_VERSION
        == models.BUILD26_1_CAPTURE_EVIDENCE_SCHEMA_VERSION
    )
    assert (
        manifest.STAGE30_14_1_VERIFY_SCHEMA_VERSION
        == models.STAGE30_14_1_VERIFY_SCHEMA_VERSION
    )
    assert manifest.STAGE30_14_1_MINOR_VERSION == models.STAGE30_14_1_MINOR_VERSION


def test_caps_match_models() -> None:
    assert manifest.STAGE30_14_1_DEFAULT_MAX_BYTES == models.STAGE30_14_1_DEFAULT_MAX_BYTES
    assert manifest.STAGE30_14_1_HARD_MAX_BYTES == models.STAGE30_14_1_HARD_MAX_BYTES
    assert manifest.STAGE30_14_1_DEFAULT_MAX_LINES == models.STAGE30_14_1_DEFAULT_MAX_LINES
    assert manifest.STAGE30_14_1_HARD_MAX_LINES == models.STAGE30_14_1_HARD_MAX_LINES
    assert (
        manifest.STAGE30_14_1_DEFAULT_MAX_ACCEPTED
        == models.STAGE30_14_1_DEFAULT_MAX_ACCEPTED
    )
    assert (
        manifest.STAGE30_14_1_HARD_MAX_ACCEPTED
        == models.STAGE30_14_1_HARD_MAX_ACCEPTED
    )
    assert manifest.STAGE30_14_1_DEFAULT_MAX_REPLAY == models.STAGE30_14_1_DEFAULT_MAX_REPLAY
    assert manifest.STAGE30_14_1_HARD_MAX_REPLAY == models.STAGE30_14_1_HARD_MAX_REPLAY


def test_redaction_statuses_match_models() -> None:
    assert (
        manifest.STAGE30_14_1_REDACTION_STATUSES
        == models.STAGE30_14_1_REDACTION_STATUSES
    )


def test_required_fields_match_models() -> None:
    assert (
        manifest.STAGE30_14_1_REQUIRED_FIELDS == models.BUILD26_1_REQUIRED_FIELDS
    )


def test_attestation_tokens_pin_committed_stage29_5() -> None:
    assert manifest.STAGE30_14_1_MIGRATION_STATUS_PRESENT == MIGRATION_STATUS_PRESENT
    assert (
        manifest.STAGE30_14_1_MEASUREMENT_STATUS_COMPLETE
        == MEASUREMENT_STATUS_COMPLETE
    )
    assert manifest.STAGE30_14_1_REDACTION_STATUS_SAFE == REDACTION_STATUS_SAFE


# ---------------------------------------------------------------------------
# 2. Inventory presence + scanned/manifest partition
# ---------------------------------------------------------------------------


def test_manifest_basename_in_inventory_but_not_scanned() -> None:
    assert (
        manifest.STAGE30_14_1_MANIFEST_BASENAME
        in manifest.STAGE30_14_1_ALLOWED_STAGE30_BASENAMES
    )
    assert (
        manifest.STAGE30_14_1_MANIFEST_BASENAME
        not in manifest.STAGE30_14_1_SCANNED_PRODUCTION_BASENAMES
    )


def test_inventory_production_files_exist() -> None:
    for basename in manifest.STAGE30_14_1_ALLOWED_STAGE30_BASENAMES:
        assert (STAGE30_ROOT / basename).is_file(), basename


def test_doc_and_test_files_exist() -> None:
    for basename in manifest.STAGE30_14_1_DOC_BASENAMES:
        assert (STAGE30_ROOT / basename).is_file(), basename
    for basename in manifest.STAGE30_14_1_TEST_BASENAMES:
        assert (TESTS_STAGE30_ROOT / basename).is_file(), basename


# ---------------------------------------------------------------------------
# 3. Allowlist self-consistency
# ---------------------------------------------------------------------------


def test_combined_phx2_allowlist_is_union_of_per_module() -> None:
    union = (
        set(manifest.STAGE30_14_1_MODELS_ALLOWED_PHX2_IMPORTS)
        | set(manifest.STAGE30_14_1_LOADER_ALLOWED_PHX2_IMPORTS)
        | set(manifest.STAGE30_14_1_VERIFIER_ALLOWED_PHX2_IMPORTS)
    )
    assert union == set(manifest.STAGE30_14_1_ALLOWED_PHX2_IMPORTS)
    # The models leaf is a pure leaf.
    assert manifest.STAGE30_14_1_MODELS_ALLOWED_PHX2_IMPORTS == ()


def test_stage29_allowlist_subset_of_phx2_allowlist() -> None:
    assert set(manifest.STAGE30_14_1_ALLOWED_STAGE29_IMPORTS).issubset(
        set(manifest.STAGE30_14_1_ALLOWED_PHX2_IMPORTS)
    )
    assert manifest.STAGE30_14_1_ALLOWED_STAGE29_IMPORTS == (
        manifest.STAGE30_14_1_STAGE29_MIGRATION_MODELS_MODULE,
    )


def test_scanned_tiers_partition_scanned_set() -> None:
    assert set(manifest.STAGE30_14_1_SCANNED_PRODUCTION_BASENAMES) == (
        set(manifest.STAGE30_14_1_STRICT_SCANNED_BASENAMES)
        | set(manifest.STAGE30_14_1_LOADER_SCANNED_BASENAMES)
    )
    assert set(manifest.STAGE30_14_1_STRICT_SCANNED_BASENAMES).isdisjoint(
        set(manifest.STAGE30_14_1_LOADER_SCANNED_BASENAMES)
    )


def test_write_surfaces_forbidden_and_readonly_documented() -> None:
    for needle in (".write_text(", ".write_bytes(", ".mkdir(", "open("):
        assert needle in manifest.STAGE30_14_1_FORBIDDEN_WRITE_SURFACES
    for surface in ("Path", ".exists", ".is_file", ".stat", ".read_text"):
        assert surface in manifest.STAGE30_14_1_ALLOWED_READONLY_FS_SURFACES


def test_operator_auth_note_present() -> None:
    assert manifest.STAGE30_14_1_REAL_EVIDENCE_REPLAY_REQUIRES_OPERATOR_AUTH is True
    assert isinstance(manifest.STAGE30_14_1_REAL_EVIDENCE_REPLAY_NOTE, str)
    assert "no code change" in manifest.STAGE30_14_1_REAL_EVIDENCE_REPLAY_NOTE


# ---------------------------------------------------------------------------
# 4. Manifest module hygiene (constants-only)
# ---------------------------------------------------------------------------


def _manifest_source() -> str:
    return (STAGE30_ROOT / manifest.STAGE30_14_1_MANIFEST_BASENAME).read_text(
        encoding="utf-8"
    )


def test_manifest_imports_no_phx2_and_only_typing() -> None:
    text = _manifest_source()
    tree = ast.parse(text)
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    assert not any(m.startswith("PHX2.") for m in imported), imported
    for module in imported:
        assert module in ("__future__", "typing"), module


def test_manifest_has_no_top_level_call_or_scheme_literal() -> None:
    text = _manifest_source()
    assert "://" not in text
    tree = ast.parse(text)
    for stmt in tree.body:
        if isinstance(stmt, ast.Assign):
            assert not isinstance(stmt.value, ast.Call)
        elif isinstance(stmt, ast.AnnAssign):
            assert not isinstance(stmt.value, ast.Call)
        elif isinstance(stmt, ast.Expr):
            assert not isinstance(stmt.value, ast.Call)


def test_spec_lock_doc_exists() -> None:
    doc = (
        STAGE30_ROOT
        / "STAGE_30_14_1_EVIDENCE_ARTIFACT_LOADER_REPLAY_VERIFIER_SPEC_LOCK.md"
    )
    assert doc.is_file()
    assert doc.stat().st_size > 0

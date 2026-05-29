"""Stage 30.7.4 closure manifest pin tests.

Pins the Stage 30.7.4 constants-only closure manifest: the minor
version, the closure-audit / handoff / manifest basenames, the Stage
30.7 commit chain (the four 30.7.0..30.7.3 SHAs) + required parent /
current HEAD, the final compact proof line, the final Stage 30.7 data
path, the closure inventory + test basenames, the scanned production
basename, the stdlib import allowlist, the forbidden surfaces, and the
next recommended stage. Asserts the production + test files exist,
asserts the manifest is constants-only (no def / class / Call; imports
only ``__future__`` + ``typing``), and asserts the manifest exports its
documented surface.

Doc / constants only. No live call, no env read, no provider, no
Discord.
"""

from __future__ import annotations

import ast
from pathlib import Path

import PHX2.stage30.stage30_7_4_manifest as M
from PHX2.stage30.stage30_7_4_manifest import (
    STAGE30_7_0_COMMIT,
    STAGE30_7_1_COMMIT,
    STAGE30_7_2_COMMIT,
    STAGE30_7_3_COMMIT,
    STAGE30_7_4_ALLOWED_STDLIB_IMPORTS,
    STAGE30_7_4_CLOSURE_AUDIT_BASENAME,
    STAGE30_7_4_COMPACT_PROOF_LINE,
    STAGE30_7_4_FINAL_DATA_PATH,
    STAGE30_7_4_FORBIDDEN_SURFACES,
    STAGE30_7_4_HANDOFF_BASENAME,
    STAGE30_7_4_MANIFEST_BASENAME,
    STAGE30_7_4_MINOR_VERSION,
    STAGE30_7_4_NEXT_RECOMMENDED_STAGE,
    STAGE30_7_4_NEXT_RECOMMENDED_STAGE_TITLE,
    STAGE30_7_4_REQUIRED_PARENT_HEAD,
    STAGE30_7_4_SCANNED_PRODUCTION_BASENAMES,
    STAGE30_7_4_TEST_BASENAMES,
    STAGE30_7_ALLOWED_STAGE30_BASENAMES_FOR_30_7_4,
    STAGE30_7_COMMIT_CHAIN,
)


PHX2_ROOT: Path = Path(__file__).resolve().parent.parent.parent
STAGE30_ROOT: Path = PHX2_ROOT / "stage30"
TESTS_STAGE30_ROOT: Path = PHX2_ROOT / "tests" / "stage30"


# ---------------------------------------------------------------------------
# 1. Version
# ---------------------------------------------------------------------------


def test_minor_version_pinned() -> None:
    assert STAGE30_7_4_MINOR_VERSION == "30.7.4"


# ---------------------------------------------------------------------------
# 2. Closure basenames + inventory exist
# ---------------------------------------------------------------------------


def test_closure_doc_basenames_pinned_and_exist() -> None:
    assert STAGE30_7_4_CLOSURE_AUDIT_BASENAME == (
        "STAGE_30_7_ATH_CONTEXT_CLOSURE_AUDIT.md"
    )
    assert STAGE30_7_4_HANDOFF_BASENAME == (
        "STAGE_30_7_ATH_CONTEXT_HANDOFF.md"
    )
    assert STAGE30_7_4_MANIFEST_BASENAME == "stage30_7_4_manifest.py"
    for basename in (
        STAGE30_7_4_CLOSURE_AUDIT_BASENAME,
        STAGE30_7_4_HANDOFF_BASENAME,
        STAGE30_7_4_MANIFEST_BASENAME,
    ):
        assert (STAGE30_ROOT / basename).is_file(), (
            f"Stage 30.7.4 requires {basename}"
        )


def test_allowed_stage30_basenames_is_docs_plus_manifest() -> None:
    assert STAGE30_7_ALLOWED_STAGE30_BASENAMES_FOR_30_7_4 == (
        STAGE30_7_4_CLOSURE_AUDIT_BASENAME,
        STAGE30_7_4_HANDOFF_BASENAME,
        STAGE30_7_4_MANIFEST_BASENAME,
    )
    for basename in STAGE30_7_ALLOWED_STAGE30_BASENAMES_FOR_30_7_4:
        assert (STAGE30_ROOT / basename).is_file()


def test_scanned_production_basename_is_the_manifest_only() -> None:
    # The only NEW production .py at Stage 30.7.4 is this constants-only
    # manifest; the two docs are markdown.
    assert STAGE30_7_4_SCANNED_PRODUCTION_BASENAMES == (
        STAGE30_7_4_MANIFEST_BASENAME,
    )


def test_test_basenames_pinned_and_exist() -> None:
    assert STAGE30_7_4_TEST_BASENAMES == (
        "test_stage_30_7_4_closure_audit.py",
        "test_stage_30_7_4_handoff.py",
        "test_stage_30_7_4_boundaries.py",
        "test_stage_30_7_4_manifest.py",
    )
    for basename in STAGE30_7_4_TEST_BASENAMES:
        assert (TESTS_STAGE30_ROOT / basename).is_file(), (
            f"Stage 30.7.4 requires test {basename}"
        )


# ---------------------------------------------------------------------------
# 3. Commit chain + required parent HEAD
# ---------------------------------------------------------------------------


def test_commit_chain_pinned() -> None:
    assert STAGE30_7_0_COMMIT == (
        "e5aa703cce3f3043d2ae9b35b2b8bc02be6fb09f"
    )
    assert STAGE30_7_1_COMMIT == (
        "837a0588959f62c0e6cf059091557d43bf513b2e"
    )
    assert STAGE30_7_2_COMMIT == (
        "ba71b6ea3efdb282d167a5760d2d31428612c04c"
    )
    assert STAGE30_7_3_COMMIT == (
        "3d4c5bed1967c431a6001173e907dda0c528fc33"
    )
    assert STAGE30_7_COMMIT_CHAIN == (
        ("30.7.0", STAGE30_7_0_COMMIT),
        ("30.7.1", STAGE30_7_1_COMMIT),
        ("30.7.2", STAGE30_7_2_COMMIT),
        ("30.7.3", STAGE30_7_3_COMMIT),
    )
    # Every SHA is a 40-char lowercase hex string.
    for _substage, sha in STAGE30_7_COMMIT_CHAIN:
        assert len(sha) == 40
        assert sha == sha.lower()
        assert all(ch in "0123456789abcdef" for ch in sha)


def test_required_parent_head_is_the_30_7_3_commit() -> None:
    # Stage 30.7.4 builds on top of the 30.7.3 commit (the current HEAD
    # at closure time).
    assert STAGE30_7_4_REQUIRED_PARENT_HEAD == STAGE30_7_3_COMMIT
    assert STAGE30_7_4_REQUIRED_PARENT_HEAD == (
        "3d4c5bed1967c431a6001173e907dda0c528fc33"
    )


# ---------------------------------------------------------------------------
# 4. Final proof line + data path
# ---------------------------------------------------------------------------


def test_compact_proof_line_pinned() -> None:
    assert STAGE30_7_4_COMPACT_PROOF_LINE == (
        "• MC: $83k | ATH: $120k | Mig: Known"
    )


def test_final_data_path_pinned() -> None:
    assert STAGE30_7_4_FINAL_DATA_PATH == (
        "sanitized ATH evidence",
        "Stage30_7AthContextEvidence",
        "project_ath_context(...)",
        "compact ATH text",
        "ath_mc_text",
        "compact ping body",
    )


# ---------------------------------------------------------------------------
# 5. Stdlib import allowlist + forbidden surfaces + next stage
# ---------------------------------------------------------------------------


def test_stdlib_import_allowlist_pinned() -> None:
    assert STAGE30_7_4_ALLOWED_STDLIB_IMPORTS == (
        "__future__",
        "typing",
    )


def test_forbidden_surfaces_non_empty_and_cover_key_scopes() -> None:
    assert isinstance(STAGE30_7_4_FORBIDDEN_SURFACES, tuple)
    assert len(STAGE30_7_4_FORBIDDEN_SURFACES) >= 10
    joined = " | ".join(STAGE30_7_4_FORBIDDEN_SURFACES)
    for token in (
        "live provider call",
        "Discord send",
        "database migration",
        "filesystem writer",
        "zstd",
        "drawdown recomputation",
        "tier recomputation",
        "enforcement",
        "Stage 30.7.5+ file",
    ):
        assert token in joined, (
            f"forbidden surfaces must name {token!r}"
        )


def test_next_recommended_stage_is_30_8() -> None:
    assert STAGE30_7_4_NEXT_RECOMMENDED_STAGE == "30.8"
    assert STAGE30_7_4_NEXT_RECOMMENDED_STAGE_TITLE == (
        "compact session artifact / storage readiness for 24/7 collection"
    )


# ---------------------------------------------------------------------------
# 6. Manifest is constants-only
# ---------------------------------------------------------------------------


def test_manifest_is_constants_only() -> None:
    """AST proof: the manifest contains no function / class definition
    and no Call node anywhere (constants-only), and imports only
    ``__future__`` + ``typing``.
    """
    manifest_path = STAGE30_ROOT / STAGE30_7_4_MANIFEST_BASENAME
    tree = ast.parse(manifest_path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        assert not isinstance(
            node,
            (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef),
        ), "Stage 30.7.4 manifest must be constants-only (no def/class)"
        assert not isinstance(node, ast.Call), (
            "Stage 30.7.4 manifest must be constants-only (no Call)"
        )
    allowed_import_roots = set(STAGE30_7_4_ALLOWED_STDLIB_IMPORTS)
    for node in tree.body:
        if isinstance(node, ast.ImportFrom):
            assert (node.module or "") in allowed_import_roots, (
                f"manifest imports non-allowlisted module "
                f"{node.module!r}"
            )
        elif isinstance(node, ast.Import):
            for alias in node.names:
                assert (
                    alias.name.split(".")[0] in allowed_import_roots
                ), f"manifest imports non-allowlisted module {alias.name!r}"


# ---------------------------------------------------------------------------
# 7. Manifest __all__ exports the documented surface
# ---------------------------------------------------------------------------


def test_manifest_all_exports_surface() -> None:
    for name in (
        "STAGE30_7_4_MINOR_VERSION",
        "STAGE30_7_4_CLOSURE_AUDIT_BASENAME",
        "STAGE30_7_4_HANDOFF_BASENAME",
        "STAGE30_7_4_MANIFEST_BASENAME",
        "STAGE30_7_0_COMMIT",
        "STAGE30_7_1_COMMIT",
        "STAGE30_7_2_COMMIT",
        "STAGE30_7_3_COMMIT",
        "STAGE30_7_COMMIT_CHAIN",
        "STAGE30_7_4_REQUIRED_PARENT_HEAD",
        "STAGE30_7_4_COMPACT_PROOF_LINE",
        "STAGE30_7_4_FINAL_DATA_PATH",
        "STAGE30_7_ALLOWED_STAGE30_BASENAMES_FOR_30_7_4",
        "STAGE30_7_4_TEST_BASENAMES",
        "STAGE30_7_4_SCANNED_PRODUCTION_BASENAMES",
        "STAGE30_7_4_ALLOWED_STDLIB_IMPORTS",
        "STAGE30_7_4_FORBIDDEN_SURFACES",
        "STAGE30_7_4_NEXT_RECOMMENDED_STAGE",
        "STAGE30_7_4_NEXT_RECOMMENDED_STAGE_TITLE",
    ):
        assert name in M.__all__, (
            f"manifest __all__ must export {name!r}"
        )

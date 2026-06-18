"""Stage 30.13 manifest tests.

Pins the constants-only manifest: it imports cleanly, imports stdlib (``typing``) only,
imports NO PHX2 module, carries no transport-scheme literal, has no top-level Call node
(no implicit I/O at import time), and its mirrored seed vocabulary cross-checks BY VALUE
against the Stage 30.13.0 models module. Also pins the inventory / allowlist shape.
"""

from __future__ import annotations

import ast
from pathlib import Path

import PHX2.stage30.stage30_13_0_ws_auto_seed_models as models
import PHX2.stage30.stage30_13_manifest as manifest


PHX2_ROOT: Path = Path(__file__).resolve().parent.parent.parent
MANIFEST_PATH: Path = PHX2_ROOT / "stage30" / "stage30_13_manifest.py"


def _manifest_source() -> str:
    return MANIFEST_PATH.read_text(encoding="utf-8")


def _manifest_ast() -> ast.Module:
    return ast.parse(_manifest_source())


# ---------------------------------------------------------------------------
# 1. Import cleanliness + constants-only discipline
# ---------------------------------------------------------------------------


def test_manifest_imports_cleanly() -> None:
    import PHX2.stage30.stage30_13_manifest  # noqa: F401


def test_manifest_imports_only_typing_and_no_phx2() -> None:
    tree = _manifest_ast()
    modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                modules.add(node.module)
    assert modules == {"__future__", "typing"}, (
        f"manifest must import only __future__ / typing; got {sorted(modules)!r}"
    )
    assert not any(m.startswith("PHX2.") for m in modules)


def test_manifest_carries_no_transport_scheme_literal() -> None:
    assert "://" not in _manifest_source()


def test_manifest_has_no_function_or_class_def() -> None:
    tree = _manifest_ast()
    for node in tree.body:
        assert not isinstance(
            node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
        ), "manifest is constants-only; no def / class allowed"


def test_manifest_has_no_top_level_call_nodes() -> None:
    tree = _manifest_ast()
    for stmt in tree.body:
        if isinstance(stmt, ast.Expr):
            assert not isinstance(stmt.value, ast.Call)
        elif isinstance(stmt, ast.Assign):
            assert not isinstance(stmt.value, ast.Call)
        elif isinstance(stmt, ast.AnnAssign):
            assert stmt.value is None or not isinstance(stmt.value, ast.Call)


# ---------------------------------------------------------------------------
# 2. Mirrored seed vocabulary cross-checks BY VALUE vs the models
# ---------------------------------------------------------------------------


def test_schema_version_mirrors_models() -> None:
    assert (
        manifest.STAGE30_13_0_AUTO_SEED_SCHEMA_VERSION
        == models.STAGE30_13_0_AUTO_SEED_SCHEMA_VERSION
    )


def test_pump_suffix_and_caps_mirror_models() -> None:
    assert manifest.STAGE30_13_PUMP_MINT_SUFFIX == models.STAGE30_13_PUMP_MINT_SUFFIX
    assert manifest.STAGE30_13_MAX_SEED_HARD_CAP == models.STAGE30_13_MAX_SEED_HARD_CAP
    assert manifest.STAGE30_13_DEFAULT_MAX_SEED == models.STAGE30_13_DEFAULT_MAX_SEED


def test_decisions_reasons_redaction_mirror_models() -> None:
    assert set(manifest.STAGE30_13_SEED_DECISIONS) == set(
        models.STAGE30_13_SEED_DECISIONS
    )
    assert set(manifest.STAGE30_13_SEED_REASONS) == set(
        models.STAGE30_13_SEED_REASONS
    )
    assert set(manifest.STAGE30_13_REDACTION_STATUSES) == set(
        models.STAGE30_13_REDACTION_STATUSES
    )


# ---------------------------------------------------------------------------
# 3. Inventory / allowlist shape
# ---------------------------------------------------------------------------


def test_scanned_is_subset_of_inventory() -> None:
    assert set(manifest.STAGE30_13_SCANNED_PRODUCTION_BASENAMES).issubset(
        set(manifest.STAGE30_13_ALLOWED_STAGE30_BASENAMES)
    )


def test_manifest_basename_not_scanned() -> None:
    # The constants-only manifest documents the forbidden-needle fragments, so it is
    # excluded from the boundary scan (it would self-collide).
    assert (
        manifest.STAGE30_13_MANIFEST_BASENAME
        not in manifest.STAGE30_13_SCANNED_PRODUCTION_BASENAMES
    )


def test_stage29_allowlist_subset_of_phx2_allowlist() -> None:
    assert set(manifest.STAGE30_13_ALLOWED_STAGE29_IMPORTS).issubset(
        set(manifest.STAGE30_13_ALLOWED_PHX2_IMPORTS)
    )


def test_phx2_allowlist_only_stage30_or_discovery_stage29() -> None:
    for module in manifest.STAGE30_13_ALLOWED_PHX2_IMPORTS:
        assert module.startswith("PHX2.stage30.stage30_") or (
            module in manifest.STAGE30_13_ALLOWED_STAGE29_IMPORTS
        ), f"unexpected PHX2 allowlist entry {module!r}"

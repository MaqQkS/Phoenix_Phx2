"""Stage 29.5.3 no-modification pins.

Stage 29.5.3 ships the runtime-adjacent soak pass-entrypoint
wrapper as a separate sub-inventory; it does NOT modify any
Stage 29.3 production file and does NOT modify any Stage 29.4
production file. These tests pin that invariant.

Pins:

  * Stage 29.3 mode-3 orchestrator
    (``stage29_3_tradeable_smoke.py``) still injects
    ``Stage29_3NoMigrationEvidenceSource``.
  * Stage 29.3 mode-3 orchestrator imports NO ``stage29_5*``
    module (including ``stage29_5_2*`` and ``stage29_5_3*``).
  * Stage 29.3 mode-3 orchestrator references no
    ``Stage29_5*`` / ``Stage29_5_2*`` / ``Stage29_5_3*``
    runtime identifier.
  * Stage 29.4 soak orchestrator
    (``stage29_4_soak_orchestrator.py``) imports NO
    ``stage29_5*`` module (including ``stage29_5_2*`` and
    ``stage29_5_3*``).
"""

from __future__ import annotations

import ast
from pathlib import Path


PHX2_ROOT: Path = (
    Path(__file__).resolve().parent.parent.parent
)
STAGE29_ROOT: Path = PHX2_ROOT / "stage29"


_STAGE29_3_TRADEABLE_SMOKE_PATH: Path = (
    STAGE29_ROOT / "stage29_3_tradeable_smoke.py"
)
_STAGE29_4_SOAK_ORCHESTRATOR_PATH: Path = (
    STAGE29_ROOT / "stage29_4_soak_orchestrator.py"
)
_STAGE29_4_SOAK_MODELS_PATH: Path = (
    STAGE29_ROOT / "stage29_4_soak_models.py"
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _collect_imported_module_paths(source: str) -> set[str]:
    tree = ast.parse(source)
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if mod:
                modules.add(mod)
    return modules


# ---------------------------------------------------------------------------
# Stage 29.3 mode-3 still uses Stage29_3NoMigrationEvidenceSource
# ---------------------------------------------------------------------------


def test_stage29_3_mode3_still_injects_no_migration_evidence_source() -> None:
    assert _STAGE29_3_TRADEABLE_SMOKE_PATH.is_file()
    src = _read(_STAGE29_3_TRADEABLE_SMOKE_PATH)
    assert "Stage29_3NoMigrationEvidenceSource" in src, (
        "Stage 29.3 mode-3 must still inject "
        "Stage29_3NoMigrationEvidenceSource at Stage 29.5.3; "
        "the Stage 29.5.3 wrapper does NOT activate direct "
        "Stage 29.3 migration-context injection"
    )


# ---------------------------------------------------------------------------
# Stage 29.3 mode-3 must not import any stage29_5* module
# ---------------------------------------------------------------------------


def test_stage29_3_mode3_imports_no_stage29_5_module() -> None:
    src = _read(_STAGE29_3_TRADEABLE_SMOKE_PATH)
    imported = _collect_imported_module_paths(src)
    for mod in imported:
        assert "stage29_5" not in mod, (
            f"Stage 29.3 mode-3 must not import a stage29_5* "
            f"module at Stage 29.5.3 (the wrapper is consumed "
            f"by the Stage 29.4 soak orchestrator, not the "
            f"Stage 29.3 smoke orchestrator); offender "
            f"import: {mod!r}"
        )


def test_stage29_3_mode3_imports_no_stage29_5_2_module() -> None:
    src = _read(_STAGE29_3_TRADEABLE_SMOKE_PATH)
    imported = _collect_imported_module_paths(src)
    for mod in imported:
        assert "stage29_5_2" not in mod, (
            f"Stage 29.3 mode-3 must not import a "
            f"stage29_5_2* module at Stage 29.5.3; offender "
            f"import: {mod!r}"
        )


def test_stage29_3_mode3_imports_no_stage29_5_3_module() -> None:
    src = _read(_STAGE29_3_TRADEABLE_SMOKE_PATH)
    imported = _collect_imported_module_paths(src)
    for mod in imported:
        assert "stage29_5_3" not in mod, (
            f"Stage 29.3 mode-3 must not import a "
            f"stage29_5_3* module at Stage 29.5.3 (the wrapper "
            f"is consumed by the Stage 29.4 soak orchestrator "
            f"via an operator-supplied callable); offender "
            f"import: {mod!r}"
        )


# ---------------------------------------------------------------------------
# Stage 29.3 mode-3 must not reference any Stage 29.5* identifier
# ---------------------------------------------------------------------------


_FORBIDDEN_STAGE29_5_IDENTIFIERS: tuple[str, ...] = (
    "stage29_5_migration_models",
    "stage29_5_helius_ws_adapter",
    "stage29_5_migration_artifact_reader",
    "stage29_5_candidate_to_migration_join",
    "stage29_5_private_ping_context_projection",
    "stage29_5_manifest",
    "Stage29_5MigrationEvidenceRecord",
    "Stage29_5MigrationJoinRecord",
    "Stage29_5PrivatePingMigrationContext",
    "Stage29_5HeliusWebSocketAdapter",
    "Stage29_5MigrationArtifactReader",
    "Stage29_5CandidateAxes",
    "project_private_ping_migration_context",
)


_FORBIDDEN_STAGE29_5_2_IDENTIFIERS: tuple[str, ...] = (
    "stage29_5_2_offline_integration",
    "stage29_5_2_synthetic_evidence_fixtures",
    "stage29_5_2_manifest",
    "Stage29_5_2OfflineIntegrationResult",
    "Stage29_5_2OfflineIntegrationError",
    "run_stage29_5_2_offline_integration",
)


_FORBIDDEN_STAGE29_5_3_IDENTIFIERS: tuple[str, ...] = (
    "stage29_5_3_wrapped_pass_models",
    "stage29_5_3_soak_pass_wrapper",
    "stage29_5_3_side_channel_artifact_writer",
    "stage29_5_3_manifest",
    "Stage29_5_3MigrationContextSoakPassWrapper",
    "Stage29_5_3WrappedPassObservation",
    "Stage29_5_3MigrationEvidenceProvider",
    "Stage29_5_3AthContextProvider",
    "append_stage29_5_3_migration_context_observation",
)


def test_stage29_3_mode3_references_no_stage29_5_identifier() -> None:
    src = _read(_STAGE29_3_TRADEABLE_SMOKE_PATH)
    for needle in _FORBIDDEN_STAGE29_5_IDENTIFIERS:
        assert needle not in src, (
            f"Stage 29.3 mode-3 must not reference Stage 29.5 "
            f"identifier {needle!r} at Stage 29.5.3"
        )


def test_stage29_3_mode3_references_no_stage29_5_2_identifier() -> None:
    src = _read(_STAGE29_3_TRADEABLE_SMOKE_PATH)
    for needle in _FORBIDDEN_STAGE29_5_2_IDENTIFIERS:
        assert needle not in src, (
            f"Stage 29.3 mode-3 must not reference Stage 29.5.2 "
            f"identifier {needle!r} at Stage 29.5.3"
        )


def test_stage29_3_mode3_references_no_stage29_5_3_identifier() -> None:
    src = _read(_STAGE29_3_TRADEABLE_SMOKE_PATH)
    for needle in _FORBIDDEN_STAGE29_5_3_IDENTIFIERS:
        assert needle not in src, (
            f"Stage 29.3 mode-3 must not reference Stage 29.5.3 "
            f"identifier {needle!r}; the wrapper does not "
            f"modify Stage 29.3 production"
        )


# ---------------------------------------------------------------------------
# Stage 29.4 soak orchestrator must not import any stage29_5* module
# ---------------------------------------------------------------------------


def test_stage29_4_soak_orchestrator_imports_no_stage29_5_module() -> None:
    assert _STAGE29_4_SOAK_ORCHESTRATOR_PATH.is_file()
    src = _read(_STAGE29_4_SOAK_ORCHESTRATOR_PATH)
    imported = _collect_imported_module_paths(src)
    for mod in imported:
        assert "stage29_5" not in mod, (
            f"Stage 29.4 soak orchestrator must not import a "
            f"stage29_5* module at Stage 29.5.3 (the wrapper "
            f"is supplied externally to the orchestrator via "
            f"its existing pass_entrypoint DI seam); offender "
            f"import: {mod!r}"
        )


def test_stage29_4_soak_orchestrator_imports_no_stage29_5_2_module() -> None:
    src = _read(_STAGE29_4_SOAK_ORCHESTRATOR_PATH)
    imported = _collect_imported_module_paths(src)
    for mod in imported:
        assert "stage29_5_2" not in mod, (
            f"Stage 29.4 soak orchestrator must not import a "
            f"stage29_5_2* module at Stage 29.5.3"
        )


def test_stage29_4_soak_orchestrator_imports_no_stage29_5_3_module() -> None:
    src = _read(_STAGE29_4_SOAK_ORCHESTRATOR_PATH)
    imported = _collect_imported_module_paths(src)
    for mod in imported:
        assert "stage29_5_3" not in mod, (
            f"Stage 29.4 soak orchestrator must not import a "
            f"stage29_5_3* module at Stage 29.5.3"
        )


def test_stage29_4_soak_orchestrator_references_no_stage29_5_identifier() -> None:
    src = _read(_STAGE29_4_SOAK_ORCHESTRATOR_PATH)
    for needle in _FORBIDDEN_STAGE29_5_IDENTIFIERS:
        assert needle not in src, (
            f"Stage 29.4 soak orchestrator must not reference "
            f"Stage 29.5 identifier {needle!r} at Stage 29.5.3"
        )


def test_stage29_4_soak_orchestrator_references_no_stage29_5_2_identifier() -> None:
    src = _read(_STAGE29_4_SOAK_ORCHESTRATOR_PATH)
    for needle in _FORBIDDEN_STAGE29_5_2_IDENTIFIERS:
        assert needle not in src, (
            f"Stage 29.4 soak orchestrator must not reference "
            f"Stage 29.5.2 identifier {needle!r} at Stage 29.5.3"
        )


def test_stage29_4_soak_orchestrator_references_no_stage29_5_3_identifier() -> None:
    src = _read(_STAGE29_4_SOAK_ORCHESTRATOR_PATH)
    for needle in _FORBIDDEN_STAGE29_5_3_IDENTIFIERS:
        assert needle not in src, (
            f"Stage 29.4 soak orchestrator must not reference "
            f"Stage 29.5.3 identifier {needle!r}; the wrapper "
            f"is supplied via the existing pass_entrypoint DI "
            f"seam, never imported"
        )


# ---------------------------------------------------------------------------
# Stage 29.4 soak models module is allowed to be IMPORTED by the
# Stage 29.5.3 wrapper, but must not itself import Stage 29.5* or
# Stage 29.5.3 modules.
# ---------------------------------------------------------------------------


def test_stage29_4_soak_models_imports_no_stage29_5_module() -> None:
    assert _STAGE29_4_SOAK_MODELS_PATH.is_file()
    src = _read(_STAGE29_4_SOAK_MODELS_PATH)
    imported = _collect_imported_module_paths(src)
    for mod in imported:
        assert "stage29_5" not in mod, (
            f"Stage 29.4 soak models must not import a "
            f"stage29_5* module at Stage 29.5.3; offender "
            f"import: {mod!r}"
        )

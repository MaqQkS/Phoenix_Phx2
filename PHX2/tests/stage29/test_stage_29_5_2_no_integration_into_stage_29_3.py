"""Stage 29.5.2 no-runtime-integration pins.

Stage 29.5.2 shipped the offline composition layer as a separate
sub-inventory; the runtime-wiring deferral itself has been
unlocked at Stage 29.5.4 via the opt-in
``run_stage29_3_first_private_tradeable_smoke``
``migration_source`` kwarg. The DEFAULT path remains
byte-equivalent: Stage 29.3 mode-3 continues to inject
``Stage29_3NoMigrationEvidenceSource`` when the operator omits
the kwarg, and Stage 29.3 production source imports NO
``stage29_5*`` module (the kwarg's static type is Stage 27.4's
``MigrationContextSource`` Protocol that Stage 29.3 already
imports).

Pins (still hold AT Stage 29.5.4):

  * Stage 29.3 mode-3 orchestrator
    (``stage29_3_tradeable_smoke.py``) still references
    ``Stage29_3NoMigrationEvidenceSource`` as the default
    fallback.
  * Stage 29.3 mode-3 orchestrator imports NO ``stage29_5*``
    module (including ``stage29_5_2*`` / ``stage29_5_3*`` /
    ``stage29_5_4*``).
  * Stage 29.3 mode-3 orchestrator references no
    ``Stage29_5*`` / ``Stage29_5_2*`` runtime identifier.
  * Stage 29.4 soak orchestrator
    (``stage29_4_soak_orchestrator.py``) imports NO
    ``stage29_5*`` module (including ``stage29_5_2*``).
  * The Stage 29.5 projection module docstring continues to
    name "Stage 29.5.2" and "deferred" so the deferred-
    integration narrative remains visible to the next reader.
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
_STAGE29_5_PROJECTION_PATH: Path = (
    STAGE29_ROOT
    / "stage29_5_private_ping_context_projection.py"
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


def test_stage29_3_mode3_still_injects_no_migration_evidence_source():
    assert _STAGE29_3_TRADEABLE_SMOKE_PATH.is_file()
    src = _read(_STAGE29_3_TRADEABLE_SMOKE_PATH)
    assert "Stage29_3NoMigrationEvidenceSource" in src, (
        "Stage 29.3 mode-3 must still reference "
        "Stage29_3NoMigrationEvidenceSource as the default "
        "fallback at Stage 29.5.4; the Stage 29.5.4 opt-in seam "
        "only takes effect when the operator explicitly passes "
        "the migration_source kwarg"
    )


# ---------------------------------------------------------------------------
# Stage 29.3 mode-3 must not import any stage29_5 / stage29_5_2 module
# ---------------------------------------------------------------------------


def test_stage29_3_mode3_imports_no_stage29_5_module():
    src = _read(_STAGE29_3_TRADEABLE_SMOKE_PATH)
    imported = _collect_imported_module_paths(src)
    for mod in imported:
        assert "stage29_5" not in mod, (
            f"Stage 29.3 mode-3 must not import a stage29_5* "
            f"module at Stage 29.5.4; the Stage 29.5.4 opt-in "
            f"seam supplies the adapter via the kwarg whose "
            f"static type is Stage 27.4's MigrationContextSource "
            f"Protocol, not via an import. Offender import: "
            f"{mod!r}"
        )


def test_stage29_3_mode3_imports_no_stage29_5_2_module():
    src = _read(_STAGE29_3_TRADEABLE_SMOKE_PATH)
    imported = _collect_imported_module_paths(src)
    for mod in imported:
        assert "stage29_5_2" not in mod, (
            f"Stage 29.3 mode-3 must not import a stage29_5_2* "
            f"module yet; offender import: {mod!r}"
        )


# ---------------------------------------------------------------------------
# Stage 29.3 mode-3 must not reference any Stage 29.5 / Stage 29.5.2 identifier
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


def test_stage29_3_mode3_references_no_stage29_5_identifier():
    src = _read(_STAGE29_3_TRADEABLE_SMOKE_PATH)
    for needle in _FORBIDDEN_STAGE29_5_IDENTIFIERS:
        assert needle not in src, (
            f"Stage 29.3 mode-3 must not reference Stage 29.5 "
            f"identifier {needle!r} until Stage 29.5.3 runtime "
            f"integration lands; Stage 29.5.2 is the offline "
            f"proof only"
        )


def test_stage29_3_mode3_references_no_stage29_5_2_identifier():
    src = _read(_STAGE29_3_TRADEABLE_SMOKE_PATH)
    for needle in _FORBIDDEN_STAGE29_5_2_IDENTIFIERS:
        assert needle not in src, (
            f"Stage 29.3 mode-3 must not reference Stage 29.5.2 "
            f"identifier {needle!r}; the composition is "
            f"offline-only at Stage 29.5.2"
        )


# ---------------------------------------------------------------------------
# Stage 29.4 soak orchestrator must not import any stage29_5 / stage29_5_2 module
# ---------------------------------------------------------------------------


def test_stage29_4_soak_orchestrator_imports_no_stage29_5_module():
    assert _STAGE29_4_SOAK_ORCHESTRATOR_PATH.is_file()
    src = _read(_STAGE29_4_SOAK_ORCHESTRATOR_PATH)
    imported = _collect_imported_module_paths(src)
    for mod in imported:
        assert "stage29_5" not in mod, (
            f"Stage 29.4 soak orchestrator must not import a "
            f"stage29_5* module at Stage 29.5.2; offender "
            f"import: {mod!r}"
        )


def test_stage29_4_soak_orchestrator_imports_no_stage29_5_2_module():
    src = _read(_STAGE29_4_SOAK_ORCHESTRATOR_PATH)
    imported = _collect_imported_module_paths(src)
    for mod in imported:
        assert "stage29_5_2" not in mod, (
            f"Stage 29.4 soak orchestrator must not import a "
            f"stage29_5_2* module at Stage 29.5.2 (the Stage "
            f"29.4 pass-entrypoint wrapper is deferred to "
            f"Stage 29.5.3); offender import: {mod!r}"
        )


def test_stage29_4_soak_orchestrator_references_no_stage29_5_identifier():
    src = _read(_STAGE29_4_SOAK_ORCHESTRATOR_PATH)
    for needle in _FORBIDDEN_STAGE29_5_IDENTIFIERS:
        assert needle not in src, (
            f"Stage 29.4 soak orchestrator must not reference "
            f"Stage 29.5 identifier {needle!r} at Stage 29.5.2"
        )


def test_stage29_4_soak_orchestrator_references_no_stage29_5_2_identifier():
    src = _read(_STAGE29_4_SOAK_ORCHESTRATOR_PATH)
    for needle in _FORBIDDEN_STAGE29_5_2_IDENTIFIERS:
        assert needle not in src, (
            f"Stage 29.4 soak orchestrator must not reference "
            f"Stage 29.5.2 identifier {needle!r} at Stage 29.5.2"
        )


# ---------------------------------------------------------------------------
# Stage 29.5 projection module continues to carry the deferred-integration note
# ---------------------------------------------------------------------------


def test_stage29_5_projection_docstring_still_names_deferred_integration():
    """Stage 29.5.2 is the OFFLINE integration proof; the
    runtime integration of the Stage 29.5 projection into the
    Stage 29.3 mode-3 orchestrator is still deferred. The Stage
    29.5 projection module's docstring must continue to mark
    this state explicitly so the next reader of the codebase
    does not infer end-to-end runtime integration that does not
    yet exist.
    """
    src = _read(_STAGE29_5_PROJECTION_PATH)
    lower = src.lower()
    assert "stage 29.5.2" in lower, (
        "Stage 29.5 projection docstring must reference Stage "
        "29.5.2"
    )
    assert "deferred" in lower, (
        "Stage 29.5 projection docstring must continue to use "
        "the word 'deferred' to mark the runtime integration "
        "as deferred"
    )

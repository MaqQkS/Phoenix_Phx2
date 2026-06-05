"""Stage 29.5.7 no-fake-evidence proof.

Pins audit requirement #12: test fakes are allowed ONLY as fixtures; the
production path must never call a fake / synthetic / fixture module, and must
never emit the synthetic-test source token. The real evidence the producer emits
is tagged ``HELIUS_WS`` and is derived from the raw envelope alone.
"""

from __future__ import annotations

import ast
from pathlib import Path

from PHX2.stage29.stage29_5_7_helius_raw_migration_normalizer import (
    normalize_helius_raw_migration_envelope,
)
from PHX2.stage29.stage29_5_7_live_migration_evidence_producer import (
    Stage29_5_7LiveMigrationEvidenceProducer,
)
from PHX2.tests.stage29._stage_29_5_7_helius_fixtures import (
    OBSERVED_AT_UTC,
    make_migration_envelope,
)


PHX2_ROOT: Path = Path(__file__).resolve().parent.parent.parent
STAGE29_ROOT: Path = PHX2_ROOT / "stage29"


_PRODUCTION_PY_BASENAMES: tuple[str, ...] = (
    "stage29_5_7_helius_raw_migration_models.py",
    "stage29_5_7_helius_raw_migration_normalizer.py",
    "stage29_5_7_live_migration_evidence_producer.py",
    "stage29_5_7_manifest.py",
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _imported_modules(source: str) -> set[str]:
    tree = ast.parse(source)
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                modules.add(node.module)
    return modules


def _production_files() -> list[Path]:
    return [STAGE29_ROOT / name for name in _PRODUCTION_PY_BASENAMES]


# ---------------------------------------------------------------------------
# 1. Production imports no fake / fixture / synthetic module
# ---------------------------------------------------------------------------


def test_production_imports_no_fake_or_fixture_module() -> None:
    forbidden_fragments = ("fixture", "fake", "synthetic")
    for path in _production_files():
        for target in _imported_modules(_read(path)):
            lower = target.lower()
            for fragment in forbidden_fragments:
                assert fragment not in lower, (
                    f"{path.name}: production imports {target!r}"
                )


def test_production_does_not_import_synthetic_evidence_fixtures() -> None:
    for path in _production_files():
        targets = _imported_modules(_read(path))
        assert (
            "PHX2.stage29.stage29_5_2_synthetic_evidence_fixtures"
            not in targets
        ), path.name


def test_production_does_not_import_the_test_fixtures_module() -> None:
    for path in _production_files():
        for target in _imported_modules(_read(path)):
            assert "_stage_29_5_7_helius_fixtures" not in target, path.name
            assert not target.startswith("PHX2.tests"), path.name


# ---------------------------------------------------------------------------
# 2. Production source carries no synthetic-test token literal
# ---------------------------------------------------------------------------


def test_production_source_has_no_synthetic_test_only_literal() -> None:
    needle = "SYNTHETIC_TEST" + "_ONLY"
    for path in _production_files():
        assert needle not in _read(path), path.name


# ---------------------------------------------------------------------------
# 3. The production path emits real HELIUS_WS evidence, never synthetic
# ---------------------------------------------------------------------------


def test_normalizer_emits_real_helius_ws_source() -> None:
    result = normalize_helius_raw_migration_envelope(
        make_migration_envelope(), OBSERVED_AT_UTC
    )
    assert result.evidence_record is not None
    assert result.evidence_record.migration_source == "HELIUS_WS"


def test_producer_path_emits_real_source_only() -> None:
    producer = Stage29_5_7LiveMigrationEvidenceProducer(
        clock=lambda: OBSERVED_AT_UTC
    )
    run = producer.produce_migration_evidence(
        [make_migration_envelope()], "2026-05-27T01:00:00Z"
    )
    assert run.summary.migrations_proven == 1
    for record in run.evidence_records:
        assert record.migration_source == "HELIUS_WS"


# ---------------------------------------------------------------------------
# 4. The fixtures module is genuinely test-only (sanity)
# ---------------------------------------------------------------------------


def test_fixtures_module_is_test_only() -> None:
    fixtures_path = (
        PHX2_ROOT / "tests" / "stage29" / "_stage_29_5_7_helius_fixtures.py"
    )
    assert fixtures_path.is_file()
    # It must not be on the production inventory.
    assert "_stage_29_5_7_helius_fixtures.py" not in _PRODUCTION_PY_BASENAMES

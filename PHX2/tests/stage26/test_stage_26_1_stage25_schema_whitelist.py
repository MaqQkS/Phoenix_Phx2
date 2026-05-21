"""Stage 26.1 Stage 25 schema whitelist tests.

The whitelist module is the ONLY ``PHX2.stage26`` production module
permitted to import from ``PHX2.stage25``; even there the import is
restricted to ``PHX2.stage25.constants``. The Stage 26.1 boundary
tests enforce the inverse rule for every other Stage 26 production
module.
"""

from __future__ import annotations

import ast
from pathlib import Path

from PHX2.stage25 import constants as stage25_constants
from PHX2.stage26 import stage25_schema_whitelist as wl


_WHITELIST_PATH: Path = (
    Path(__file__).resolve().parent.parent.parent
    / "stage26"
    / "stage25_schema_whitelist.py"
)


def _parse_import_targets() -> tuple[set[str], set[str], set[str]]:
    """Return (top-level modules, full ``from X import Y`` targets,
    stage25 module list)."""
    source = _WHITELIST_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    top_level_modules: set[str] = set()
    full_targets: set[str] = set()
    stage25_modules_imported_from: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                top_level_modules.add(alias.name)
                full_targets.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if mod:
                top_level_modules.add(mod)
                full_targets.add(mod)
                if mod.startswith("PHX2.stage25"):
                    stage25_modules_imported_from.add(mod)
                for alias in node.names:
                    full_targets.add(f"{mod}.{alias.name}")
    return top_level_modules, full_targets, stage25_modules_imported_from


def test_whitelist_only_stage25_import_is_constants():
    _, _, stage25_modules = _parse_import_targets()
    assert stage25_modules == {"PHX2.stage25.constants"}, (
        "Whitelist module is allowed to import from PHX2.stage25.constants "
        f"only; saw {sorted(stage25_modules)}"
    )


def test_whitelist_imports_match_locked_symbol_tuple():
    """The names imported from PHX2.stage25.constants must equal the
    locked STAGE25_SCHEMA_WHITELIST_SYMBOLS tuple.
    """
    source = _WHITELIST_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported_names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if mod == "PHX2.stage25.constants":
                for alias in node.names:
                    imported_names.add(alias.name)
    locked = set(wl.STAGE25_SCHEMA_WHITELIST_SYMBOLS)
    assert imported_names == locked, (
        "Whitelist module imports must equal the locked symbol set. "
        f"missing={sorted(locked - imported_names)} "
        f"extra={sorted(imported_names - locked)}"
    )


def test_whitelist_does_not_import_forbidden_stage25_modules():
    _, _, stage25_modules = _parse_import_targets()
    forbidden = {
        "PHX2.stage25.models",
        "PHX2.stage25.errors",
        "PHX2.stage25.measurement_contracts",
        "PHX2.stage25.input_reader",
        "PHX2.stage25.summary",
        "PHX2.stage25.runner",
        "PHX2.stage25.artifact_writer",
        "PHX2.stage25.stage25_manifest",
        "PHX2.stage25.migration_observation",
        "PHX2.stage25.migration_measurement",
        "PHX2.stage25.price_observation",
        "PHX2.stage25.price_window",
        "PHX2.stage25.ath_candidate",
        "PHX2.stage25.source_reconciliation",
    }
    overlap = stage25_modules & forbidden
    assert overlap == set(), (
        f"Whitelist imports forbidden Stage 25 module(s): {sorted(overlap)}"
    )


def test_whitelist_symbols_are_re_exported_with_identical_values():
    for symbol in wl.STAGE25_SCHEMA_WHITELIST_SYMBOLS:
        assert hasattr(wl, symbol), (
            f"Whitelist re-export is missing symbol {symbol!r}"
        )
        assert hasattr(stage25_constants, symbol), (
            f"Stage 25 constants does not expose {symbol!r}"
        )
        assert getattr(wl, symbol) is getattr(stage25_constants, symbol), (
            f"Whitelist symbol {symbol!r} is not the same object as "
            "PHX2.stage25.constants's; re-export must preserve identity"
        )


def test_whitelist_symbol_tuple_has_no_duplicates():
    symbols = wl.STAGE25_SCHEMA_WHITELIST_SYMBOLS
    assert len(symbols) == len(set(symbols))


def test_whitelist_includes_self_referential_manifest_sentinels():
    for required in (
        "SELF_REFERENTIAL_MANIFEST_SHA256",
        "SELF_REFERENTIAL_MANIFEST_BYTE_COUNT",
        "SELF_REFERENTIAL_MANIFEST_ROW_COUNT",
    ):
        assert required in wl.STAGE25_SCHEMA_WHITELIST_SYMBOLS, (
            f"Stage 26.1 whitelist must include the self-referential "
            f"manifest sentinel {required!r}"
        )


def test_whitelist_includes_artifact_filename_constants():
    for required in (
        "STAGE25_ATH_CANDIDATES_FILENAME",
        "STAGE25_ATH_MEASUREMENTS_FILENAME",
        "STAGE25_MANIFEST_FILENAME",
        "STAGE25_MEASUREMENT_REJECTIONS_FILENAME",
        "STAGE25_MIGRATION_MEASUREMENTS_FILENAME",
        "STAGE25_MIGRATION_OBSERVATIONS_FILENAME",
        "STAGE25_PRICE_WINDOW_OBSERVATIONS_FILENAME",
        "STAGE25_SOURCE_RECONCILIATIONS_FILENAME",
        "STAGE25_SUMMARY_FILENAME",
    ):
        assert required in wl.STAGE25_SCHEMA_WHITELIST_SYMBOLS

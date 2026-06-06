"""Stage 30.12 manifest pin tests.

Pins the Stage 30.12 manifest constants (minor version, renderer schema version,
the production basenames + module paths, the inventory + scanned + test
basenames, the stdlib + PHX2 import allowlists, the mirrored tier-token /
tier-band / body-cap / sentinel / footer vocabulary, the forbidden text needles,
the forbidden surfaces, the live-wiring operator-auth note), cross-checks the
mirrored values against the Stage 30.12 models module, asserts the files exist,
and validates the constants-only manifest itself (imports only stdlib + no PHX2
module, carries no transport-scheme literal, has no top-level call node).

Doc / constants only. No live call, no env read, no actual-disk write.
"""

from __future__ import annotations

import ast
from pathlib import Path

import PHX2.stage30.stage30_12_manifest as M
from PHX2.stage30.stage30_12_phoenix_operator_ping_models import (
    DISPLAY_UNKNOWN as MODELS_DISPLAY_UNKNOWN,
    STAGE30_12_BODY_CHAR_HARD_CAP as MODELS_BODY_CAP,
    STAGE30_12_OPERATOR_FOOTER as MODELS_FOOTER,
    STAGE30_12_PHOENIX_OPERATOR_PING_SCHEMA_VERSION as MODELS_SCHEMA_VERSION,
    TIER_BAND_DISPLAY_TIER_1 as MODELS_BAND_1,
    TIER_BAND_DISPLAY_TIER_2 as MODELS_BAND_2,
    TIER_BAND_DISPLAY_TIER_3 as MODELS_BAND_3,
    TIER_TOKEN_TIER_1 as MODELS_T1,
    TIER_TOKEN_TIER_2 as MODELS_T2,
    TIER_TOKEN_TIER_3 as MODELS_T3,
    TIER_TOKEN_TIER_NOT_APPLICABLE as MODELS_TNA,
    TIER_TOKEN_TIER_UNKNOWN as MODELS_TU,
)


PHX2_ROOT: Path = Path(__file__).resolve().parent.parent.parent
STAGE30_ROOT: Path = PHX2_ROOT / "stage30"


def _manifest_source() -> str:
    return (STAGE30_ROOT / M.STAGE30_12_MANIFEST_BASENAME).read_text(
        encoding="utf-8"
    )


# ---------------------------------------------------------------------------
# 1. Versions + schema (mirrored from models)
# ---------------------------------------------------------------------------


def test_stage_id_and_minor_version() -> None:
    assert M.STAGE30_12_STAGE_ID == "30.12"
    assert M.STAGE30_12_MINOR_VERSION == "30.12"


def test_renderer_schema_version_matches_models() -> None:
    assert M.STAGE30_12_RENDERER_SCHEMA_VERSION == MODELS_SCHEMA_VERSION
    assert (
        M.STAGE30_12_RENDERER_SCHEMA_VERSION
        == "stage30_12_v0_phoenix_operator_ping"
    )


# ---------------------------------------------------------------------------
# 2. Mirrored vocabulary matches the models module
# ---------------------------------------------------------------------------


def test_tier_tokens_match_models() -> None:
    assert M.STAGE30_12_TIER_TOKEN_TIER_1 == MODELS_T1
    assert M.STAGE30_12_TIER_TOKEN_TIER_2 == MODELS_T2
    assert M.STAGE30_12_TIER_TOKEN_TIER_3 == MODELS_T3
    assert M.STAGE30_12_TIER_TOKEN_TIER_UNKNOWN == MODELS_TU
    assert M.STAGE30_12_TIER_TOKEN_TIER_NOT_APPLICABLE == MODELS_TNA


def test_tier_band_displays_match_models() -> None:
    assert M.STAGE30_12_TIER_BAND_DISPLAY_TIER_1 == MODELS_BAND_1 == "50%–60%"
    assert M.STAGE30_12_TIER_BAND_DISPLAY_TIER_2 == MODELS_BAND_2 == "62%–80%"
    assert M.STAGE30_12_TIER_BAND_DISPLAY_TIER_3 == MODELS_BAND_3 == "82%–95%"


def test_cap_sentinel_footer_match_models() -> None:
    assert M.STAGE30_12_BODY_CHAR_HARD_CAP == MODELS_BODY_CAP == 1900
    assert M.STAGE30_12_DISPLAY_UNKNOWN == MODELS_DISPLAY_UNKNOWN == "Unknown"
    assert (
        M.STAGE30_12_OPERATOR_FOOTER
        == MODELS_FOOTER
        == "PRIVATE OPERATOR ONLY · PHX2"
    )


# ---------------------------------------------------------------------------
# 3. Inventory + module paths + allowlists
# ---------------------------------------------------------------------------


def test_production_basenames_and_modules() -> None:
    assert M.STAGE30_12_MODELS_BASENAME == (
        "stage30_12_phoenix_operator_ping_models.py"
    )
    assert M.STAGE30_12_RENDERER_BASENAME == (
        "stage30_12_phoenix_operator_ping_renderer.py"
    )
    assert M.STAGE30_12_MANIFEST_BASENAME == "stage30_12_manifest.py"
    assert M.STAGE30_12_MODELS_MODULE == (
        "PHX2.stage30.stage30_12_phoenix_operator_ping_models"
    )
    assert M.STAGE30_12_RENDERER_MODULE == (
        "PHX2.stage30.stage30_12_phoenix_operator_ping_renderer"
    )


def test_allowed_stage30_basenames_are_the_three_new_files() -> None:
    assert M.STAGE30_12_ALLOWED_STAGE30_BASENAMES == (
        M.STAGE30_12_MODELS_BASENAME,
        M.STAGE30_12_RENDERER_BASENAME,
        M.STAGE30_12_MANIFEST_BASENAME,
    )


def test_scanned_excludes_manifest() -> None:
    assert M.STAGE30_12_SCANNED_PRODUCTION_BASENAMES == (
        M.STAGE30_12_MODELS_BASENAME,
        M.STAGE30_12_RENDERER_BASENAME,
    )


def test_test_basenames_are_the_four_test_files() -> None:
    assert M.STAGE30_12_TEST_BASENAMES == (
        "test_stage_30_12_phoenix_operator_ping_models.py",
        "test_stage_30_12_phoenix_operator_ping_renderer.py",
        "test_stage_30_12_boundaries.py",
        "test_stage_30_12_manifest.py",
    )


def test_stdlib_allowlist_is_exactly_the_renderer_needs() -> None:
    assert M.STAGE30_12_ALLOWED_STDLIB_IMPORTS == (
        "__future__",
        "typing",
        "re",
        "decimal",
    )
    for forbidden in ("os", "sqlite3", "time", "datetime", "socket", "urllib"):
        assert forbidden not in M.STAGE30_12_ALLOWED_STDLIB_IMPORTS


def test_phx2_allowlist_is_the_two_own_siblings() -> None:
    assert M.STAGE30_12_ALLOWED_PHX2_IMPORTS == (
        M.STAGE30_12_MODELS_MODULE,
        M.STAGE30_12_RENDERER_MODULE,
    )


# ---------------------------------------------------------------------------
# 4. Forbidden needles + surfaces
# ---------------------------------------------------------------------------


def test_forbidden_text_needles_resolve_to_url_secret_forms() -> None:
    resolved = set(M.STAGE30_12_FORBIDDEN_TEXT_NEEDLES)
    assert (":" + "/" + "/") in resolved
    assert ("x-" + "api-" + "key") in resolved
    assert ("api_" + "key") in resolved
    assert ("/" + "web" + "hooks" + "/") in resolved


def test_forbidden_surfaces_name_the_locked_no_touch_areas() -> None:
    joined = " ".join(M.STAGE30_12_FORBIDDEN_SURFACES).lower()
    for term in (
        "live discord send",
        "wsol quote mint as ca",
        "stage 30.1 tier logic edit",
        "stage 30.2 compact renderer edit",
        "stage 30.11 runner / gate / transport edit",
        "commit",
        "tag",
        "push",
    ):
        assert term in joined


def test_live_wiring_requires_operator_auth() -> None:
    assert M.STAGE30_12_LIVE_WIRING_REQUIRES_OPERATOR_AUTH is True
    assert isinstance(M.STAGE30_12_LIVE_WIRING_NOTE, str)
    assert "operator-authorized" in M.STAGE30_12_LIVE_WIRING_NOTE


# ---------------------------------------------------------------------------
# 5. Files exist
# ---------------------------------------------------------------------------


def test_all_three_production_files_exist() -> None:
    for basename in M.STAGE30_12_ALLOWED_STAGE30_BASENAMES:
        assert (STAGE30_ROOT / basename).is_file(), (
            f"Stage 30.12 requires {basename}"
        )


# ---------------------------------------------------------------------------
# 6. The constants-only manifest is itself clean
# ---------------------------------------------------------------------------


def test_manifest_imports_only_stdlib_no_phx2() -> None:
    text = _manifest_source()
    tree = ast.parse(text)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert not alias.name.startswith("PHX2."), (
                    f"manifest imports PHX2 module {alias.name!r}"
                )
                top = alias.name.split(".")[0]
                assert top in M.STAGE30_12_ALLOWED_STDLIB_IMPORTS
        elif isinstance(node, ast.ImportFrom):
            assert node.module is not None
            assert not node.module.startswith("PHX2."), (
                f"manifest imports PHX2 module {node.module!r}"
            )
            top = node.module.split(".")[0]
            assert top in M.STAGE30_12_ALLOWED_STDLIB_IMPORTS


def test_manifest_carries_no_transport_scheme_literal() -> None:
    assert (":" + "/" + "/") not in _manifest_source()


def test_manifest_has_no_top_level_call_nodes() -> None:
    tree = ast.parse(_manifest_source())
    for stmt in tree.body:
        if isinstance(stmt, ast.Expr):
            assert not isinstance(stmt.value, ast.Call), (
                "manifest carries a top-level expression call"
            )
        if isinstance(stmt, (ast.Assign, ast.AnnAssign)):
            value = stmt.value
            assert not isinstance(value, ast.Call), (
                "manifest carries a top-level assignment call"
            )

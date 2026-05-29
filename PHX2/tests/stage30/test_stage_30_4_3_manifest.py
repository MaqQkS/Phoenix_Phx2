"""Stage 30.4.3 manifest pin tests.

Pins the Stage 30.4.3 manifest constants (minor version, bridge
basename + allowlist, source label, token-overview path, Stage 29.2
reuse allowlist, bridge PHX2-import allowlist, test basenames),
asserts the bridge + test files exist, asserts the manifest exports
the new surface, and asserts the Stage 30.4.0 forbidden import / text
needle sets were NOT weakened.
"""

from __future__ import annotations

from pathlib import Path

import PHX2.stage30.stage30_4_manifest as M
from PHX2.stage29.birdeye_constants import (
    BIRDEYE_ALLOWED_PATHS,
    BIRDEYE_PATH_TOKEN_OVERVIEW,
)
from PHX2.stage30.stage30_4_3_market_context_birdeye_source import (
    STAGE30_4_3_BIRDEYE_SOURCE_LABEL,
)
from PHX2.stage30.stage30_4_manifest import (
    STAGE30_4_3_BIRDEYE_TOKEN_OVERVIEW_PATH,
    STAGE30_4_3_BRIDGE_ALLOWED_PHX2_IMPORTS,
    STAGE30_4_3_MARKET_CONTEXT_BIRDEYE_SOURCE_BASENAME,
    STAGE30_4_3_MINOR_VERSION,
    STAGE30_4_3_SOURCE_LABEL,
    STAGE30_4_3_STAGE29_2_REUSE_ALLOWLIST,
    STAGE30_4_3_TEST_BASENAMES,
    STAGE30_4_ALLOWED_STAGE30_BASENAMES_FOR_30_4_3,
    STAGE30_4_FORBIDDEN_RUNTIME_IMPORTS,
    STAGE30_4_FORBIDDEN_TEXT_NEEDLES,
    STAGE30_4_OPERATOR_DECISION_FIRST_SOURCE_LABEL,
)


PHX2_ROOT: Path = Path(__file__).resolve().parent.parent.parent
STAGE30_ROOT: Path = PHX2_ROOT / "stage30"
TESTS_STAGE30_ROOT: Path = PHX2_ROOT / "tests" / "stage30"


# ---------------------------------------------------------------------------
# 1. Version + basename pins
# ---------------------------------------------------------------------------


def test_minor_version_pinned() -> None:
    assert STAGE30_4_3_MINOR_VERSION == "30.4.3"


def test_bridge_basename_pinned_and_file_exists() -> None:
    assert STAGE30_4_3_MARKET_CONTEXT_BIRDEYE_SOURCE_BASENAME == (
        "stage30_4_3_market_context_birdeye_source.py"
    )
    path = (
        STAGE30_ROOT
        / STAGE30_4_3_MARKET_CONTEXT_BIRDEYE_SOURCE_BASENAME
    )
    assert path.is_file(), f"Stage 30.4.3 requires {path}"


def test_allowed_stage30_basenames_for_30_4_3() -> None:
    assert STAGE30_4_ALLOWED_STAGE30_BASENAMES_FOR_30_4_3 == (
        STAGE30_4_3_MARKET_CONTEXT_BIRDEYE_SOURCE_BASENAME,
    )


# ---------------------------------------------------------------------------
# 2. Source label pin (matches bridge constant + operator decision)
# ---------------------------------------------------------------------------


def test_source_label_pinned() -> None:
    assert STAGE30_4_3_SOURCE_LABEL == "birdeye_token_overview"
    assert STAGE30_4_3_SOURCE_LABEL == STAGE30_4_3_BIRDEYE_SOURCE_LABEL
    assert (
        STAGE30_4_3_SOURCE_LABEL
        == STAGE30_4_OPERATOR_DECISION_FIRST_SOURCE_LABEL
    )


# ---------------------------------------------------------------------------
# 3. Token-overview path pin (matches the Stage 29.2 constant)
# ---------------------------------------------------------------------------


def test_token_overview_path_pinned_and_allowed_in_stage29() -> None:
    assert STAGE30_4_3_BIRDEYE_TOKEN_OVERVIEW_PATH == (
        "/defi/token_overview"
    )
    assert (
        STAGE30_4_3_BIRDEYE_TOKEN_OVERVIEW_PATH
        == BIRDEYE_PATH_TOKEN_OVERVIEW
    )
    assert BIRDEYE_PATH_TOKEN_OVERVIEW in BIRDEYE_ALLOWED_PATHS


def test_stage29_allowed_paths_now_three() -> None:
    assert len(BIRDEYE_ALLOWED_PATHS) == 3
    assert BIRDEYE_ALLOWED_PATHS == (
        "/defi/price",
        "/defi/ohlcv",
        "/defi/token_overview",
    )


# ---------------------------------------------------------------------------
# 4. Stage 29.2 reuse allowlist + bridge PHX2-import allowlist
# ---------------------------------------------------------------------------


def test_stage29_2_reuse_allowlist_is_the_four_approved() -> None:
    assert STAGE30_4_3_STAGE29_2_REUSE_ALLOWLIST == (
        "PHX2.stage29.birdeye_constants",
        "PHX2.stage29.stage29_2_birdeye_http_transport",
        "PHX2.stage29.stage29_2_birdeye_models",
        "PHX2.stage29.stage29_2_birdeye_readiness",
    )


def test_bridge_allowed_phx2_imports_superset_of_reuse_allowlist() -> None:
    for module in STAGE30_4_3_STAGE29_2_REUSE_ALLOWLIST:
        assert module in STAGE30_4_3_BRIDGE_ALLOWED_PHX2_IMPORTS
    assert (
        "PHX2.stage30.stage30_4_compact_market_context_models"
        in STAGE30_4_3_BRIDGE_ALLOWED_PHX2_IMPORTS
    )
    assert (
        "PHX2.stage30.stage30_4_compact_market_context_source_protocol"
        in STAGE30_4_3_BRIDGE_ALLOWED_PHX2_IMPORTS
    )
    # Exactly six entries: four Stage 29.2 + two Stage 30.4.1 siblings.
    assert len(STAGE30_4_3_BRIDGE_ALLOWED_PHX2_IMPORTS) == 6


# ---------------------------------------------------------------------------
# 5. Test inventory pin
# ---------------------------------------------------------------------------


def test_test_basenames_pinned_and_exist() -> None:
    expected = (
        "test_stage_30_4_3_birdeye_source_unknown_paths.py",
        "test_stage_30_4_3_birdeye_source_present_path.py",
        "test_stage_30_4_3_birdeye_source_partial_and_bad_values.py",
        "test_stage_30_4_3_boundaries.py",
        "test_stage_30_4_3_manifest.py",
    )
    assert STAGE30_4_3_TEST_BASENAMES == expected
    for basename in STAGE30_4_3_TEST_BASENAMES:
        path = TESTS_STAGE30_ROOT / basename
        assert path.is_file(), f"Stage 30.4.3 requires test {path}"


# ---------------------------------------------------------------------------
# 6. Manifest exports the Stage 30.4.3 surface
# ---------------------------------------------------------------------------


def test_manifest_all_exports_30_4_3_surface() -> None:
    for name in (
        "STAGE30_4_3_MINOR_VERSION",
        "STAGE30_4_3_MARKET_CONTEXT_BIRDEYE_SOURCE_BASENAME",
        "STAGE30_4_ALLOWED_STAGE30_BASENAMES_FOR_30_4_3",
        "STAGE30_4_3_SOURCE_LABEL",
        "STAGE30_4_3_BIRDEYE_TOKEN_OVERVIEW_PATH",
        "STAGE30_4_3_STAGE29_2_REUSE_ALLOWLIST",
        "STAGE30_4_3_BRIDGE_ALLOWED_PHX2_IMPORTS",
        "STAGE30_4_3_TEST_BASENAMES",
    ):
        assert name in M.__all__, (
            f"manifest __all__ must export {name!r}"
        )


# ---------------------------------------------------------------------------
# 7. Forbidden import / text needle sets were not weakened
# ---------------------------------------------------------------------------


def test_forbidden_runtime_import_set_not_weakened() -> None:
    assert len(STAGE30_4_FORBIDDEN_RUNTIME_IMPORTS) >= 20
    for needle in ("os.environ", "import socket", "from urllib"):
        assert needle in STAGE30_4_FORBIDDEN_RUNTIME_IMPORTS


def test_forbidden_text_needle_set_not_weakened() -> None:
    assert len(STAGE30_4_FORBIDDEN_TEXT_NEEDLES) >= 12

"""Stage 30.11.11 manifest pin tests.

Pins the Stage 30.11.11 manifest constants (minor / schema version, source
basename + module, the additive Stage 29.2 anchored-fetch name, the inventory +
scanned + test basenames, the stdlib + PHX2 import allowlists, the provider item
cap + interval ladder, the decision / reason closed sets, the mirrored Stage 27.4
vocabulary, the next-allowed pointer, the slice forbidden surfaces, the
operator-auth live-ceremony note), cross-checks the mirrored constants against
the Stage 30.11.11 source module + the real Stage 27.4 constants + the additive
Stage 29.2 fetch, confirms the Stage 30.11.0..30.11.10 pointers survive
unchanged, and pins the Stage 30.11.12+ future guard.

Doc / constants only. No live call, no env read, no actual-disk write.
"""

from __future__ import annotations

import re
from pathlib import Path

import PHX2.stage30.stage30_11_manifest as M
from PHX2.stage30.stage30_11_manifest import (
    STAGE30_11_10_NEXT_ALLOWED_STAGE,
    STAGE30_11_11_ALLOWED_PHX2_IMPORTS,
    STAGE30_11_11_ALLOWED_STAGE30_BASENAMES,
    STAGE30_11_11_ALLOWED_STDLIB_IMPORTS,
    STAGE30_11_11_ANCHORED_ATH_DECISIONS,
    STAGE30_11_11_ANCHORED_ATH_PASS_DECISION,
    STAGE30_11_11_ANCHORED_ATH_PASS_REASON,
    STAGE30_11_11_ANCHORED_ATH_REASONS,
    STAGE30_11_11_ANCHORED_ATH_SCHEMA_VERSION,
    STAGE30_11_11_ANCHORED_ATH_SOURCE_BASENAME,
    STAGE30_11_11_ANCHORED_ATH_SOURCE_MODULE,
    STAGE30_11_11_ATH_SINCE_MIGRATION_STATUS_POST_MIGRATION_ONLY,
    STAGE30_11_11_ATH_STATUS_PRESENT,
    STAGE30_11_11_DRAWDOWN_BASIS_FROM_POST_MIGRATION_ATH,
    STAGE30_11_11_FORBIDDEN_SURFACES,
    STAGE30_11_11_INTERVAL_LADDER,
    STAGE30_11_11_LIVE_CEREMONY_REQUIRES_OPERATOR_AUTH,
    STAGE30_11_11_MINOR_VERSION,
    STAGE30_11_11_NEXT_ALLOWED_STAGE,
    STAGE30_11_11_OHLCV_MAX_ITEMS,
    STAGE30_11_11_SCANNED_PRODUCTION_BASENAMES,
    STAGE30_11_11_SOURCE_STAGE,
    STAGE30_11_11_STAGE29_2_ANCHORED_FETCH_NAME,
    STAGE30_11_11_TEST_BASENAMES,
    STAGE30_11_11_WINDOW_TOO_LONG_REASON,
    STAGE30_11_NEXT_ALLOWED_STAGE,
    STAGE30_11_STAGE_ID,
)
import PHX2.stage29.stage29_2_birdeye_ath_source as ATH29
from PHX2.stage27.price_ath_context_models import (
    ATH_SINCE_MIGRATION_STATUS_POST_MIGRATION_ONLY as S27_POST_MIG_ONLY,
    ATH_STATUS_PRESENT as S27_ATH_STATUS_PRESENT,
    DRAWDOWN_BASIS_FROM_POST_MIGRATION_ATH as S27_DD_BASIS,
)
from PHX2.stage30.stage30_11_11_migration_anchored_ath_source import (
    STAGE30_11_11_ANCHORED_ATH_DECISIONS as SRC_DECISIONS,
    STAGE30_11_11_ANCHORED_ATH_PASS_DECISION as SRC_PASS_DECISION,
    STAGE30_11_11_ANCHORED_ATH_PASS_REASON as SRC_PASS_REASON,
    STAGE30_11_11_ANCHORED_ATH_REASONS as SRC_REASONS,
    STAGE30_11_11_ANCHORED_ATH_SCHEMA_VERSION as SRC_SCHEMA_VERSION,
    STAGE30_11_11_INTERVAL_LADDER as SRC_LADDER,
    STAGE30_11_11_MINOR_VERSION as SRC_MINOR_VERSION,
    STAGE30_11_11_OHLCV_MAX_ITEMS as SRC_MAX_ITEMS,
)


PHX2_ROOT: Path = Path(__file__).resolve().parent.parent.parent
STAGE30_ROOT: Path = PHX2_ROOT / "stage30"
TESTS_STAGE30_ROOT: Path = PHX2_ROOT / "tests" / "stage30"


# ---------------------------------------------------------------------------
# 1. Minor + schema version (mirrored from the source)
# ---------------------------------------------------------------------------


def test_minor_and_schema_version_match_source() -> None:
    assert STAGE30_11_STAGE_ID == "30.11"
    assert STAGE30_11_11_MINOR_VERSION == "30.11.11"
    assert STAGE30_11_11_MINOR_VERSION == SRC_MINOR_VERSION
    assert STAGE30_11_11_ANCHORED_ATH_SCHEMA_VERSION == (
        "stage30_11_11_v0_migration_anchored_ath"
    )
    assert STAGE30_11_11_ANCHORED_ATH_SCHEMA_VERSION == SRC_SCHEMA_VERSION
    assert STAGE30_11_11_SOURCE_STAGE == "30.11.11"


# ---------------------------------------------------------------------------
# 2. Basenames + module path + files exist
# ---------------------------------------------------------------------------


def test_basename_and_module_pinned() -> None:
    assert STAGE30_11_11_ANCHORED_ATH_SOURCE_BASENAME == (
        "stage30_11_11_migration_anchored_ath_source.py"
    )
    assert STAGE30_11_11_ANCHORED_ATH_SOURCE_MODULE == (
        "PHX2.stage30.stage30_11_11_migration_anchored_ath_source"
    )
    assert STAGE30_11_11_ALLOWED_STAGE30_BASENAMES == (
        STAGE30_11_11_ANCHORED_ATH_SOURCE_BASENAME,
    )
    assert STAGE30_11_11_SCANNED_PRODUCTION_BASENAMES == (
        STAGE30_11_11_ANCHORED_ATH_SOURCE_BASENAME,
    )


def test_production_and_test_files_exist() -> None:
    assert (
        STAGE30_ROOT / STAGE30_11_11_ANCHORED_ATH_SOURCE_BASENAME
    ).is_file()
    assert STAGE30_11_11_TEST_BASENAMES == (
        "test_stage_30_11_11_migration_anchored_ath_source.py",
        "test_stage_30_11_11_boundaries.py",
        "test_stage_30_11_11_manifest.py",
    )
    for basename in STAGE30_11_11_TEST_BASENAMES:
        assert (TESTS_STAGE30_ROOT / basename).is_file()


# ---------------------------------------------------------------------------
# 3. Import allowlists (the audited Stage 27.4 + Stage 29.2 expansion)
# ---------------------------------------------------------------------------


def test_stdlib_import_allowlist_pinned() -> None:
    assert STAGE30_11_11_ALLOWED_STDLIB_IMPORTS == (
        "__future__",
        "typing",
        "dataclasses",
        "datetime",
    )
    for forbidden in ("decimal", "re", "os", "json", "sqlite3"):
        assert forbidden not in STAGE30_11_11_ALLOWED_STDLIB_IMPORTS


def test_phx2_import_allowlist_is_stage27_4_and_stage29_2_only() -> None:
    assert STAGE30_11_11_ALLOWED_PHX2_IMPORTS == (
        "PHX2.stage27.price_ath_context_contracts",
        "PHX2.stage27.price_ath_context_models",
        "PHX2.stage27.price_ath_context_reader",
        "PHX2.stage27.migration_context_models",
        "PHX2.stage27.provider_ingest_models",
        "PHX2.stage27.pair_detection_constants",
        "PHX2.stage29.birdeye_constants",
        "PHX2.stage29.stage29_2_birdeye_ath_source",
        "PHX2.stage29.stage29_2_birdeye_models",
        "PHX2.stage29.stage29_2_birdeye_price_source",
    )
    for module in STAGE30_11_11_ALLOWED_PHX2_IMPORTS:
        assert module.startswith("PHX2.stage27.") or module.startswith(
            "PHX2.stage29."
        )
    # No Stage 28 / other Stage 30 / PHX1 in the allowlist.
    joined = " ".join(STAGE30_11_11_ALLOWED_PHX2_IMPORTS)
    assert "stage28" not in joined
    assert "stage30" not in joined
    assert "PHX1" not in joined


def test_additive_stage29_2_anchored_fetch_exists() -> None:
    assert STAGE30_11_11_STAGE29_2_ANCHORED_FETCH_NAME == (
        "fetch_birdeye_ath_snapshot_migration_anchored"
    )
    assert hasattr(ATH29, STAGE30_11_11_STAGE29_2_ANCHORED_FETCH_NAME)
    # The legacy sliding fetch is still present (unchanged path).
    assert hasattr(ATH29, "fetch_birdeye_ath_snapshot")


# ---------------------------------------------------------------------------
# 4. Interval ladder + cap (mirrored from the source)
# ---------------------------------------------------------------------------


def test_interval_ladder_and_cap_match_source() -> None:
    assert STAGE30_11_11_OHLCV_MAX_ITEMS == 1000
    assert STAGE30_11_11_OHLCV_MAX_ITEMS == SRC_MAX_ITEMS
    assert STAGE30_11_11_INTERVAL_LADDER == (
        ("1m", 60),
        ("5m", 300),
        ("15m", 900),
        ("1H", 3600),
        ("4H", 14400),
        ("1D", 86400),
    )
    assert STAGE30_11_11_INTERVAL_LADDER == SRC_LADDER
    # Finest first (strictly increasing candle seconds).
    seconds = [s for _, s in STAGE30_11_11_INTERVAL_LADDER]
    assert seconds == sorted(seconds)


# ---------------------------------------------------------------------------
# 5. Decision / reason closed sets (mirrored from the source)
# ---------------------------------------------------------------------------


def test_decisions_and_reasons_match_source() -> None:
    assert STAGE30_11_11_ANCHORED_ATH_DECISIONS == (
        "RESOLVED_ANCHORED_ATH",
        "UNRESOLVED_ANCHORED_ATH",
    )
    assert STAGE30_11_11_ANCHORED_ATH_DECISIONS == SRC_DECISIONS
    assert STAGE30_11_11_ANCHORED_ATH_PASS_DECISION == "RESOLVED_ANCHORED_ATH"
    assert STAGE30_11_11_ANCHORED_ATH_PASS_DECISION == SRC_PASS_DECISION
    assert STAGE30_11_11_ANCHORED_ATH_PASS_REASON == (
        "RESOLVED_POST_MIGRATION_ATH"
    )
    assert STAGE30_11_11_ANCHORED_ATH_PASS_REASON == SRC_PASS_REASON
    assert STAGE30_11_11_ANCHORED_ATH_PASS_REASON == (
        STAGE30_11_11_ANCHORED_ATH_REASONS[0]
    )
    assert STAGE30_11_11_ANCHORED_ATH_REASONS == SRC_REASONS
    assert len(STAGE30_11_11_ANCHORED_ATH_REASONS) == 12
    assert len(set(STAGE30_11_11_ANCHORED_ATH_REASONS)) == 12
    assert STAGE30_11_11_WINDOW_TOO_LONG_REASON == (
        "ATH_UNVERIFIED_WINDOW_TOO_LONG"
    )
    assert (
        STAGE30_11_11_WINDOW_TOO_LONG_REASON
        in STAGE30_11_11_ANCHORED_ATH_REASONS
    )


# ---------------------------------------------------------------------------
# 6. Mirrored Stage 27.4 vocabulary matches the real Stage 27.4 constants
# ---------------------------------------------------------------------------


def test_mirrored_ath_tokens_match_real_stage_27_4() -> None:
    assert STAGE30_11_11_ATH_STATUS_PRESENT == S27_ATH_STATUS_PRESENT
    assert (
        STAGE30_11_11_ATH_SINCE_MIGRATION_STATUS_POST_MIGRATION_ONLY
        == S27_POST_MIG_ONLY
    )
    assert (
        STAGE30_11_11_DRAWDOWN_BASIS_FROM_POST_MIGRATION_ATH == S27_DD_BASIS
    )


# ---------------------------------------------------------------------------
# 7. Next-allowed pointer + earlier pointers unchanged
# ---------------------------------------------------------------------------


def test_next_allowed_is_the_operator_authorized_ceremony() -> None:
    assert STAGE30_11_11_NEXT_ALLOWED_STAGE == (
        "CONTROLLED_LIVE_CEREMONY_OPERATOR_AUTHORIZED"
    )
    assert "30.11.12" not in STAGE30_11_11_NEXT_ALLOWED_STAGE
    # Earlier pointers survive unchanged.
    assert STAGE30_11_10_NEXT_ALLOWED_STAGE == (
        "CONTROLLED_LIVE_CEREMONY_OPERATOR_AUTHORIZED"
    )
    assert STAGE30_11_NEXT_ALLOWED_STAGE == "30.11.1"


def test_live_ceremony_requires_operator_auth() -> None:
    assert STAGE30_11_11_LIVE_CEREMONY_REQUIRES_OPERATOR_AUTH is True


# ---------------------------------------------------------------------------
# 8. Forbidden surfaces cover the audit's "do not" scopes
# ---------------------------------------------------------------------------


def test_slice_forbidden_surfaces_cover_key_scopes() -> None:
    assert isinstance(STAGE30_11_11_FORBIDDEN_SURFACES, tuple)
    assert len(STAGE30_11_11_FORBIDDEN_SURFACES) >= 20
    joined = " | ".join(STAGE30_11_11_FORBIDDEN_SURFACES)
    for token in (
        "real transport call",
        "private send",
        "live provider call",
        "env read",
        "wall-clock read",
        "sliding now-minus-lookback ATH window for the live dip gate",
        "clip the first post-migration peak",
        "silently truncate the anchored window start",
        "fabricate ATH",
        "recompute drawdown independently",
        "loosen post-migration ATH verification",
        "modify Stage 27.4 reader",
        "modify the Stage 29.2 lookback fetch path",
        "modify Stage 30.11.10 resolver",
        "modify the Stage 30.12 renderer / display",
        "modify Stage 30.12.1 body builder",
        "alter tier bands",
        "wallet / signing",
        "commit",
        "tag",
        "push",
        "Stage 31",
    ):
        assert token in joined, (
            f"Stage 30.11.11 forbidden surfaces must name {token!r}"
        )


# ---------------------------------------------------------------------------
# 9. Manifest __all__ exports the Stage 30.11.11 surface + earlier survives
# ---------------------------------------------------------------------------


def test_manifest_all_exports_stage_30_11_11_surface() -> None:
    for name in (
        "STAGE30_11_11_MINOR_VERSION",
        "STAGE30_11_11_ANCHORED_ATH_SCHEMA_VERSION",
        "STAGE30_11_11_SOURCE_STAGE",
        "STAGE30_11_11_ANCHORED_ATH_SOURCE_BASENAME",
        "STAGE30_11_11_ANCHORED_ATH_SOURCE_MODULE",
        "STAGE30_11_11_STAGE29_2_ANCHORED_FETCH_NAME",
        "STAGE30_11_11_ALLOWED_STAGE30_BASENAMES",
        "STAGE30_11_11_SCANNED_PRODUCTION_BASENAMES",
        "STAGE30_11_11_TEST_BASENAMES",
        "STAGE30_11_11_ALLOWED_STDLIB_IMPORTS",
        "STAGE30_11_11_ALLOWED_PHX2_IMPORTS",
        "STAGE30_11_11_OHLCV_MAX_ITEMS",
        "STAGE30_11_11_INTERVAL_LADDER",
        "STAGE30_11_11_ANCHORED_ATH_DECISIONS",
        "STAGE30_11_11_ANCHORED_ATH_REASONS",
        "STAGE30_11_11_WINDOW_TOO_LONG_REASON",
        "STAGE30_11_11_FORBIDDEN_TEXT_NEEDLES",
        "STAGE30_11_11_NEXT_ALLOWED_STAGE",
        "STAGE30_11_11_FORBIDDEN_SURFACES",
        "STAGE30_11_11_LIVE_CEREMONY_REQUIRES_OPERATOR_AUTH",
        "STAGE30_11_11_LIVE_CEREMONY_NOTE",
    ):
        assert name in M.__all__, f"manifest __all__ must export {name!r}"


def test_earlier_30_11_constants_still_present() -> None:
    for name in (
        "STAGE30_11_STAGE_ID",
        "STAGE30_11_0_MINOR_VERSION",
        "STAGE30_11_NEXT_ALLOWED_STAGE",
        "STAGE30_11_10_MINOR_VERSION",
        "STAGE30_11_10_NEXT_ALLOWED_STAGE",
        "STAGE30_11_10_FORBIDDEN_SURFACES",
    ):
        assert name in M.__all__


# ---------------------------------------------------------------------------
# 10. Stage 30.11.12+ future guard
# ---------------------------------------------------------------------------


_STAGE_30_11_MINOR_RE = re.compile(r"stage_?30_11_(\d+)")


def test_inventory_admits_no_stage_30_11_12_plus_file() -> None:
    inventory = (
        tuple(STAGE30_11_11_ALLOWED_STAGE30_BASENAMES)
        + tuple(STAGE30_11_11_TEST_BASENAMES)
    )
    violations = []
    for basename in inventory:
        for match in _STAGE_30_11_MINOR_RE.finditer(basename.lower()):
            if int(match.group(1)) >= 12:
                violations.append(basename)
    assert violations == [], (
        "Stage 30.11.11 inventory must not admit a Stage 30.11.12+ file; "
        f"saw {violations!r}"
    )

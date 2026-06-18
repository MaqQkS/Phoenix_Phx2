"""Stage 30.14 manifest + spec-lock pin tests.

Pins the constants-only manifest against the Stage 30.14.0 models module (schema version,
caps, redaction vocabulary mirrored BY VALUE), checks the inventory + doc files exist, and
asserts the spec-lock doc carries its locked invariants. Offline / pure.
"""

from __future__ import annotations

from pathlib import Path

from PHX2.stage30 import stage30_14_0_replay_discovery_models as models
from PHX2.stage30.stage30_14_manifest import (
    STAGE30_14_0_MODELS_MODULE,
    STAGE30_14_0_ORCHESTRATOR_MODULE,
    STAGE30_14_0_REPLAY_SOURCE_MODULE,
    STAGE30_14_0_SCHEMA_VERSION,
    STAGE30_14_ALLOWED_PHX2_IMPORTS,
    STAGE30_14_ALLOWED_STAGE29_IMPORTS,
    STAGE30_14_ALLOWED_STAGE30_BASENAMES,
    STAGE30_14_DOC_BASENAMES,
    STAGE30_14_MAX_FAKE_DISPATCHES,
    STAGE30_14_MAX_RECHECKS,
    STAGE30_14_MAX_SEED,
    STAGE30_14_PURPOSE,
    STAGE30_14_REDACTION_STATUSES,
    STAGE30_14_SCANNED_PRODUCTION_BASENAMES,
    STAGE30_14_STAGE29_MIGRATION_MODELS_MODULE,
    STAGE30_14_STAGE30_11_23_FAKE_PROOF_MODULE,
    STAGE30_14_STAGE30_13_0_AUTO_SEEDER_MODULE,
)


PHX2_ROOT: Path = Path(__file__).resolve().parent.parent.parent
STAGE30_ROOT: Path = PHX2_ROOT / "stage30"


# ---------------------------------------------------------------------------
# 1. Manifest mirrors the models BY VALUE
# ---------------------------------------------------------------------------


def test_schema_version_matches_models() -> None:
    assert STAGE30_14_0_SCHEMA_VERSION == models.STAGE30_14_0_SCHEMA_VERSION


def test_purpose_matches_models() -> None:
    assert STAGE30_14_PURPOSE == models.STAGE30_14_0_PURPOSE


def test_caps_match_models_and_are_all_one() -> None:
    assert STAGE30_14_MAX_SEED == models.STAGE30_14_MAX_SEED == 1
    assert STAGE30_14_MAX_RECHECKS == models.STAGE30_14_MAX_RECHECKS == 1
    assert (
        STAGE30_14_MAX_FAKE_DISPATCHES
        == models.STAGE30_14_MAX_FAKE_DISPATCHES
        == 1
    )


def test_redaction_statuses_match_models() -> None:
    assert STAGE30_14_REDACTION_STATUSES == models.STAGE30_14_REDACTION_STATUSES


# ---------------------------------------------------------------------------
# 2. Inventory + allowlist internal consistency
# ---------------------------------------------------------------------------


def test_scanned_is_subset_of_inventory() -> None:
    for basename in STAGE30_14_SCANNED_PRODUCTION_BASENAMES:
        assert basename in STAGE30_14_ALLOWED_STAGE30_BASENAMES


def test_manifest_is_excluded_from_the_scanned_set() -> None:
    # The constants-only manifest documents the forbidden needles, so scanning it against
    # its own needles would self-collide; it must NOT be in the scanned set.
    assert (
        "stage30_14_manifest.py" not in STAGE30_14_SCANNED_PRODUCTION_BASENAMES
    )
    assert "stage30_14_manifest.py" in STAGE30_14_ALLOWED_STAGE30_BASENAMES


def test_allowed_phx2_imports_carry_the_composed_committed_modules() -> None:
    for module in (
        STAGE30_14_0_MODELS_MODULE,
        STAGE30_14_0_REPLAY_SOURCE_MODULE,
        STAGE30_14_0_ORCHESTRATOR_MODULE,
        STAGE30_14_STAGE29_MIGRATION_MODELS_MODULE,
        STAGE30_14_STAGE30_13_0_AUTO_SEEDER_MODULE,
        STAGE30_14_STAGE30_11_23_FAKE_PROOF_MODULE,
    ):
        assert module in STAGE30_14_ALLOWED_PHX2_IMPORTS


def test_stage29_allowlist_is_exactly_the_one_discovery_module() -> None:
    assert set(STAGE30_14_ALLOWED_STAGE29_IMPORTS) == {
        STAGE30_14_STAGE29_MIGRATION_MODELS_MODULE
    }


def test_no_durable_ledger_or_real_send_guard_in_allowlist() -> None:
    for module in STAGE30_14_ALLOWED_PHX2_IMPORTS:
        lowered = module.lower()
        assert "stage30_11_15" not in lowered  # durable / in-memory ledger module
        assert "stage30_11_16" not in lowered  # real-send guard
        assert "discord" not in lowered
        assert "stage28" not in lowered


# ---------------------------------------------------------------------------
# 3. Inventory + doc files exist on disk
# ---------------------------------------------------------------------------


def test_inventory_basenames_exist() -> None:
    for basename in STAGE30_14_ALLOWED_STAGE30_BASENAMES:
        assert (STAGE30_ROOT / basename).is_file(), basename


def test_doc_basenames_exist() -> None:
    for basename in STAGE30_14_DOC_BASENAMES:
        assert (STAGE30_ROOT / basename).is_file(), basename


# ---------------------------------------------------------------------------
# 4. Spec-lock doc carries its locked invariants
# ---------------------------------------------------------------------------


def test_spec_lock_carries_locked_invariants() -> None:
    text = (
        STAGE30_ROOT
        / "STAGE_30_14_0_REAL_DISCOVERY_REPLAY_SHADOW_DISPATCH_SPEC_LOCK.md"
    ).read_text(encoding="utf-8")
    for needle in (
        "Build #26",
        "SYNTHETIC",
        "max_seed",
        "max_rechecks",
        "max_fake_dispatches",
        "real_send_performed",
        "real_send_guard_invoked",
        "no real send",
        "Build 26.1",
    ):
        assert needle in text, f"spec-lock missing locked phrase {needle!r}"

"""Stage 29.5.7 manifest pins."""

from __future__ import annotations

from pathlib import Path

from PHX2.stage29 import stage29_5_7_manifest as manifest
from PHX2.stage29.stage29_5_7_helius_raw_migration_models import (
    PUMPSWAP_CREATE_POOL_EVENT_DISCRIMINATOR,
    PUMPSWAP_CREATE_POOL_INSTRUCTION_DISCRIMINATOR,
    STAGE29_5_7_RAW_MIGRATION_EVIDENCE_SCHEMA_VERSION,
)


_STAGE29_ROOT: Path = Path(__file__).resolve().parent.parent.parent / "stage29"
_TESTS_ROOT: Path = Path(__file__).resolve().parent


def test_production_inventory_matches_disk() -> None:
    for name in manifest.STAGE29_5_7_PRODUCTION_PY_BASENAMES:
        assert (_STAGE29_ROOT / name).is_file(), name
    assert manifest.STAGE29_5_7_PRODUCTION_PY_BASENAMES == (
        "stage29_5_7_helius_raw_migration_models.py",
        "stage29_5_7_helius_raw_migration_normalizer.py",
        "stage29_5_7_live_migration_evidence_producer.py",
        "stage29_5_7_manifest.py",
    )


def test_doc_inventory_exists() -> None:
    for name in manifest.STAGE29_5_7_DOC_BASENAMES:
        assert (_STAGE29_ROOT / name).is_file(), name


def test_test_inventory_exists() -> None:
    for name in manifest.STAGE29_5_7_TEST_BASENAMES:
        assert (_TESTS_ROOT / name).is_file(), name


def test_zero_env_and_network_admissions() -> None:
    assert manifest.STAGE29_5_7_ENV_READ_ADMITTED_BASENAMES == ()
    assert manifest.STAGE29_5_7_OUTBOUND_NETWORK_ADMITTED_BASENAMES == ()


def test_schema_version_pin() -> None:
    assert (
        manifest.STAGE29_5_7_RAW_MIGRATION_EVIDENCE_SCHEMA_VERSION
        == STAGE29_5_7_RAW_MIGRATION_EVIDENCE_SCHEMA_VERSION
    )


def test_discriminator_pins_match_models() -> None:
    assert (
        manifest.STAGE29_5_7_CREATE_POOL_INSTRUCTION_DISCRIMINATOR
        == PUMPSWAP_CREATE_POOL_INSTRUCTION_DISCRIMINATOR
    )
    assert (
        manifest.STAGE29_5_7_CREATE_POOL_EVENT_DISCRIMINATOR
        == PUMPSWAP_CREATE_POOL_EVENT_DISCRIMINATOR
    )
    assert (
        manifest.STAGE29_5_7_CREATE_POOL_INSTRUCTION_LOG
        == "Program log: Instruction: CreatePool"
    )


def test_redaction_lock() -> None:
    assert manifest.STAGE29_5_7_REDACTION_STATUS_LOCKED == "SAFE"


def test_forbidden_surfaces_pin_the_audit_boundaries() -> None:
    surfaces = manifest.STAGE29_5_7_FORBIDDEN_SURFACES
    for required in (
        "Stage 30.11.8 confirmation loosening",
        "Stage 30 import from Stage 29",
        "ATH / drawdown patch",
        "dip gate change",
        "Stage 31 implementation",
        "Discord send",
        "third-party base58 / base64 library import",
        "Anchor borsh event-data decoder",
        "synthetic migration source in production data flow",
    ):
        assert required in surfaces, required


def test_reject_reason_values_pinned() -> None:
    assert "NONE" in manifest.STAGE29_5_7_REJECT_REASON_VALUES
    assert "NO_CREATE_POOL_INSTRUCTION" in manifest.STAGE29_5_7_REJECT_REASON_VALUES
    assert len(manifest.STAGE29_5_7_REJECT_REASON_VALUES) == 13

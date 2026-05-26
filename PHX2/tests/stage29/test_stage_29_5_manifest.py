"""Stage 29.5 manifest pin tests.

Pins the constants-only re-export inventory + forbidden-surface
list. The manifest is the boundary scan's authoritative
inventory pin; this test asserts every pin matches the actual
Stage 29.5 production tree.
"""

from __future__ import annotations

from PHX2.stage29 import stage29_5_manifest


_EXPECTED_PRODUCTION_PY_BASENAMES: tuple[str, ...] = (
    "stage29_5_migration_models.py",
    "stage29_5_helius_ws_adapter.py",
    "stage29_5_migration_artifact_reader.py",
    "stage29_5_candidate_to_migration_join.py",
    "stage29_5_private_ping_context_projection.py",
    "stage29_5_manifest.py",
)


_EXPECTED_DOC_BASENAMES: tuple[str, ...] = (
    "STAGE_29_5_MIGRATION_EVIDENCE_SPEC_LOCK.md",
)


_EXPECTED_TEST_BASENAMES: tuple[str, ...] = (
    "test_stage_29_5_migration_models.py",
    "test_stage_29_5_helius_ws_adapter.py",
    "test_stage_29_5_migration_artifact_reader.py",
    "test_stage_29_5_candidate_to_migration_join.py",
    "test_stage_29_5_private_ping_context_projection.py",
    "test_stage_29_5_manifest.py",
    "test_stage_29_5_boundaries.py",
    "test_stage_29_5_spec_lock.py",
)


def test_manifest_pins_production_inventory():
    assert (
        stage29_5_manifest.STAGE29_5_PRODUCTION_PY_BASENAMES
        == _EXPECTED_PRODUCTION_PY_BASENAMES
    )


def test_manifest_pins_doc_inventory():
    assert (
        stage29_5_manifest.STAGE29_5_DOC_BASENAMES
        == _EXPECTED_DOC_BASENAMES
    )


def test_manifest_pins_test_inventory():
    assert (
        stage29_5_manifest.STAGE29_5_TEST_BASENAMES
        == _EXPECTED_TEST_BASENAMES
    )


def test_manifest_env_read_admission_is_empty():
    assert (
        stage29_5_manifest.STAGE29_5_ENV_READ_ADMITTED_BASENAMES
        == ()
    )


def test_manifest_outbound_network_admission_is_empty():
    assert (
        stage29_5_manifest.STAGE29_5_OUTBOUND_NETWORK_ADMITTED_BASENAMES
        == ()
    )


def test_manifest_pins_migration_status_values():
    from PHX2.stage29.stage29_5_migration_models import (
        STAGE29_5_MIGRATION_STATUS_VALUES,
    )
    assert (
        stage29_5_manifest.STAGE29_5_MIGRATION_STATUS_VALUES
        == STAGE29_5_MIGRATION_STATUS_VALUES
    )


def test_manifest_pins_migration_source_values():
    from PHX2.stage29.stage29_5_migration_models import (
        STAGE29_5_MIGRATION_SOURCE_VALUES,
    )
    assert (
        stage29_5_manifest.STAGE29_5_MIGRATION_SOURCE_VALUES
        == STAGE29_5_MIGRATION_SOURCE_VALUES
    )


def test_manifest_pins_join_status_values():
    from PHX2.stage29.stage29_5_migration_models import (
        STAGE29_5_MIGRATION_JOIN_STATUS_VALUES,
    )
    assert (
        stage29_5_manifest.STAGE29_5_MIGRATION_JOIN_STATUS_VALUES
        == STAGE29_5_MIGRATION_JOIN_STATUS_VALUES
    )


def test_manifest_pins_measurement_status_values():
    from PHX2.stage29.stage29_5_migration_models import (
        STAGE29_5_MEASUREMENT_STATUS_VALUES,
    )
    assert (
        stage29_5_manifest.STAGE29_5_MEASUREMENT_STATUS_VALUES
        == STAGE29_5_MEASUREMENT_STATUS_VALUES
    )


def test_manifest_pins_warning_code_values():
    from PHX2.stage29.stage29_5_migration_models import (
        STAGE29_5_WARNING_CODE_VALUES,
    )
    assert (
        stage29_5_manifest.STAGE29_5_WARNING_CODE_VALUES
        == STAGE29_5_WARNING_CODE_VALUES
    )


def test_manifest_pins_redaction_status_values():
    from PHX2.stage29.stage29_5_migration_models import (
        STAGE29_5_REDACTION_STATUS_VALUES,
    )
    assert (
        stage29_5_manifest.STAGE29_5_REDACTION_STATUS_VALUES
        == STAGE29_5_REDACTION_STATUS_VALUES
    )


def test_manifest_pins_filter_enforcement_status_values():
    from PHX2.stage29.stage29_5_migration_models import (
        STAGE29_5_FILTER_ENFORCEMENT_STATUS_VALUES,
    )
    assert (
        stage29_5_manifest.STAGE29_5_FILTER_ENFORCEMENT_STATUS_VALUES
        == STAGE29_5_FILTER_ENFORCEMENT_STATUS_VALUES
    )


def test_manifest_pins_locked_enforcement_token():
    assert (
        stage29_5_manifest.STAGE29_5_FILTER_ENFORCEMENT_STATUS_LOCKED
        == "NOT_ACTIVE_STAGE_29_PENDING"
    )


def test_manifest_pins_refusal_reason_values():
    from PHX2.stage29.stage29_5_migration_models import (
        STAGE29_5_REFUSAL_REASON_VALUES,
    )
    assert (
        stage29_5_manifest.STAGE29_5_REFUSAL_REASON_VALUES
        == STAGE29_5_REFUSAL_REASON_VALUES
    )


def test_manifest_pins_schema_versions():
    assert (
        stage29_5_manifest.STAGE29_5_MIGRATION_EVIDENCE_SCHEMA_VERSION
        == "stage29_5_v0_migration_evidence"
    )
    assert (
        stage29_5_manifest.STAGE29_5_MIGRATION_JOIN_SCHEMA_VERSION
        == "stage29_5_v0_migration_join"
    )
    assert (
        stage29_5_manifest.STAGE29_5_PRIVATE_PING_CONTEXT_SCHEMA_VERSION
        == "stage29_5_v0_private_ping_context"
    )


def test_manifest_pins_ws_bounds():
    assert (
        stage29_5_manifest.STAGE29_5_HELIUS_WS_DEFAULT_MAX_MESSAGES_TO_READ
        == 64
    )
    assert (
        stage29_5_manifest.STAGE29_5_HELIUS_WS_HARD_MAX_MESSAGES_TO_READ
        == 1024
    )
    assert (
        stage29_5_manifest.STAGE29_5_HELIUS_WS_MIGRATION_KIND
        == "PUMP_AMM_MIGRATION"
    )


def test_manifest_pins_artifact_bounds():
    assert (
        stage29_5_manifest.STAGE29_5_ARTIFACT_DEFAULT_MAX_RECORDS_PER_CALL
        == 128
    )
    assert (
        stage29_5_manifest.STAGE29_5_ARTIFACT_HARD_MAX_RECORDS_PER_CALL
        == 4096
    )
    assert (
        stage29_5_manifest.STAGE29_5_MIGRATION_ARTIFACT_KIND
        == "STAGE29_5_MIGRATION"
    )


def test_manifest_lists_required_forbidden_surfaces():
    required = {
        "production enforcement",
        "public routing",
        "subscriber routing",
        "paid tier routing",
        "automated trading",
        "wallet / private-key / signer logic",
        "Pump.fun bonding-curve decoder",
        "Helius as a price source",
        "PHX1 import path",
        "direct PHX1 spaghetti copy",
        "new env name",
        "new third-party runtime dependency",
        "real websockets-library transport",
        "synthetic migration source in production data flow",
    }
    assert required.issubset(
        set(stage29_5_manifest.STAGE29_5_FORBIDDEN_SURFACES)
    )


def test_manifest_actual_inventory_matches_stage29_root():
    from pathlib import Path

    stage29_root = (
        Path(__file__).resolve().parent.parent.parent / "stage29"
    )
    # Stage 29.5.2 offline integration proof (authorized
    # 2026-05-26) introduces ``stage29_5_2_*.py`` files under
    # PHX2/stage29/. Stage 29.5.3 soak pass-entrypoint wrapper
    # (authorized 2026-05-26) introduces ``stage29_5_3_*.py``
    # files under PHX2/stage29/. Those files belong to the
    # Stage 29.5.2 / Stage 29.5.3 inventories respectively, not
    # the Stage 29.5 inventory; the Stage 29.5 manifest stays
    # pinned at exactly six files. This filter excludes Stage
    # 29.5.2 + Stage 29.5.3 files so the Stage 29.5 inventory
    # cross-check remains tight against the Stage 29.5 manifest.
    actual_py = {
        entry.name
        for entry in stage29_root.iterdir()
        if entry.is_file()
        and entry.suffix == ".py"
        and entry.name.startswith("stage29_5_")
        and not entry.name.startswith("stage29_5_2_")
        and not entry.name.startswith("stage29_5_3_")
    }
    expected = set(
        stage29_5_manifest.STAGE29_5_PRODUCTION_PY_BASENAMES
    )
    assert actual_py == expected

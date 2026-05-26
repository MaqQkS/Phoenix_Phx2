"""Stage 29.5.2 manifest pin tests.

Pins the constants-only re-export inventory + forbidden-surface
list. The manifest is the boundary scan's authoritative
inventory pin; this test asserts every pin matches the actual
Stage 29.5.2 production tree.
"""

from __future__ import annotations

from PHX2.stage29 import stage29_5_2_manifest


_EXPECTED_PRODUCTION_PY_BASENAMES: tuple[str, ...] = (
    "stage29_5_2_offline_integration.py",
    "stage29_5_2_synthetic_evidence_fixtures.py",
    "stage29_5_2_manifest.py",
)


_EXPECTED_DOC_BASENAMES: tuple[str, ...] = (
    "STAGE_29_5_2_OFFLINE_INTEGRATION_PROOF_RUNBOOK.md",
)


_EXPECTED_TEST_BASENAMES: tuple[str, ...] = (
    "test_stage_29_5_2_offline_integration.py",
    "test_stage_29_5_2_boundaries.py",
    "test_stage_29_5_2_no_integration_into_stage_29_3.py",
    "test_stage_29_5_2_manifest.py",
    "test_stage_29_5_2_spec_lock.py",
)


_EXPECTED_SYNTHETIC_TOKEN_ADMITTED_BASENAMES: tuple[
    str, ...
] = ("stage29_5_2_synthetic_evidence_fixtures.py",)


def test_manifest_pins_production_inventory():
    assert (
        stage29_5_2_manifest.STAGE29_5_2_PRODUCTION_PY_BASENAMES
        == _EXPECTED_PRODUCTION_PY_BASENAMES
    )


def test_manifest_pins_doc_inventory():
    assert (
        stage29_5_2_manifest.STAGE29_5_2_DOC_BASENAMES
        == _EXPECTED_DOC_BASENAMES
    )


def test_manifest_pins_test_inventory():
    assert (
        stage29_5_2_manifest.STAGE29_5_2_TEST_BASENAMES
        == _EXPECTED_TEST_BASENAMES
    )


def test_manifest_env_read_admission_is_empty():
    assert (
        stage29_5_2_manifest.STAGE29_5_2_ENV_READ_ADMITTED_BASENAMES
        == ()
    )


def test_manifest_outbound_network_admission_is_empty():
    assert (
        stage29_5_2_manifest.STAGE29_5_2_OUTBOUND_NETWORK_ADMITTED_BASENAMES
        == ()
    )


def test_manifest_synthetic_token_admission_lists_fixtures_only():
    assert (
        stage29_5_2_manifest.STAGE29_5_2_SYNTHETIC_SOURCE_TOKEN_ADMITTED_BASENAMES
        == _EXPECTED_SYNTHETIC_TOKEN_ADMITTED_BASENAMES
    )


def test_manifest_pins_schema_version():
    assert (
        stage29_5_2_manifest.STAGE29_5_2_OFFLINE_INTEGRATION_SCHEMA_VERSION
        == "stage29_5_2_v0_offline_integration"
    )


def test_manifest_pins_locked_enforcement_token():
    assert (
        stage29_5_2_manifest.STAGE29_5_2_FILTER_ENFORCEMENT_STATUS_LOCKED
        == "NOT_ACTIVE_STAGE_29_PENDING"
    )


def test_manifest_forbidden_surfaces_is_nonempty_closed_tuple():
    forbidden = (
        stage29_5_2_manifest.STAGE29_5_2_FORBIDDEN_SURFACES
    )
    assert isinstance(forbidden, tuple)
    assert len(forbidden) > 0
    for entry in forbidden:
        assert isinstance(entry, str)
        assert entry.strip() == entry
        assert entry, "forbidden-surface entry must not be empty"


def test_manifest_forbidden_surfaces_carries_canonical_invariants():
    forbidden_lower = tuple(
        s.lower()
        for s in (
            stage29_5_2_manifest
            .STAGE29_5_2_FORBIDDEN_SURFACES
        )
    )
    for needle in (
        "live helius websocket call",
        "live chainstack grpc call",
        "live birdeye http call",
        "stage 29.3 runtime wiring change",
        "stage 29.4 runtime wiring change",
        "stage 29.5 manifest inventory change",
        "soak pass-entrypoint wrapper",
    ):
        assert needle in forbidden_lower, (
            f"Stage 29.5.2 manifest must pin "
            f"{needle!r} on the forbidden-surface list"
        )

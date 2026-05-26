"""Stage 29.5.3 manifest pin tests.

Pins the constants-only re-export inventory + forbidden-surface
list. The manifest is the boundary scan's authoritative
inventory pin; this test asserts every pin matches the actual
Stage 29.5.3 production tree.
"""

from __future__ import annotations

from PHX2.stage29 import stage29_5_3_manifest


_EXPECTED_PRODUCTION_PY_BASENAMES: tuple[str, ...] = (
    "stage29_5_3_wrapped_pass_models.py",
    "stage29_5_3_soak_pass_wrapper.py",
    "stage29_5_3_side_channel_artifact_writer.py",
    "stage29_5_3_manifest.py",
)


_EXPECTED_DOC_BASENAMES: tuple[str, ...] = (
    "STAGE_29_5_3_SOAK_PASS_WRAPPER_RUNBOOK.md",
)


_EXPECTED_TEST_BASENAMES: tuple[str, ...] = (
    "test_stage_29_5_3_wrapped_pass_models.py",
    "test_stage_29_5_3_soak_pass_wrapper.py",
    "test_stage_29_5_3_side_channel_artifact_writer.py",
    "test_stage_29_5_3_manifest.py",
    "test_stage_29_5_3_boundaries.py",
    "test_stage_29_5_3_no_modification_to_stage_29_3_or_29_4.py",
    "test_stage_29_5_3_spec_lock.py",
)


def test_manifest_pins_production_inventory() -> None:
    assert (
        stage29_5_3_manifest.STAGE29_5_3_PRODUCTION_PY_BASENAMES
        == _EXPECTED_PRODUCTION_PY_BASENAMES
    )


def test_manifest_pins_doc_inventory() -> None:
    assert (
        stage29_5_3_manifest.STAGE29_5_3_DOC_BASENAMES
        == _EXPECTED_DOC_BASENAMES
    )


def test_manifest_pins_test_inventory() -> None:
    assert (
        stage29_5_3_manifest.STAGE29_5_3_TEST_BASENAMES
        == _EXPECTED_TEST_BASENAMES
    )


def test_manifest_env_read_admission_is_empty() -> None:
    assert (
        stage29_5_3_manifest.STAGE29_5_3_ENV_READ_ADMITTED_BASENAMES
        == ()
    )


def test_manifest_outbound_network_admission_is_empty() -> None:
    assert (
        stage29_5_3_manifest.STAGE29_5_3_OUTBOUND_NETWORK_ADMITTED_BASENAMES
        == ()
    )


def test_manifest_pins_observation_schema_version() -> None:
    assert (
        stage29_5_3_manifest.STAGE29_5_3_OBSERVATION_SCHEMA_VERSION
        == "stage29_5_3_wrapped_pass_observation_v0"
    )


def test_manifest_pins_observation_status_values() -> None:
    expected = (
        "NO_CANDIDATE_AXES",
        "COMPOSED",
        "COMPOSITION_REJECTED",
        "PROVIDER_REJECTED",
    )
    assert (
        stage29_5_3_manifest.STAGE29_5_3_OBSERVATION_STATUS_VALUES
        == expected
    )


def test_manifest_pins_observation_field_names() -> None:
    assert (
        stage29_5_3_manifest.STAGE29_5_3_OBSERVATION_FIELD_NAMES
        == (
            "schema_version",
            "pass_index",
            "observation_status",
            "candidate_base_mint",
            "join_status_echoed",
            "measurement_status_echoed",
            "post_migration_ath_verified_echoed",
            "warnings_echoed",
            "observed_at_utc",
            "filter_enforcement_status",
            "redaction_status",
        )
    )


def test_manifest_pins_locked_enforcement_token() -> None:
    assert (
        stage29_5_3_manifest.STAGE29_5_3_FILTER_ENFORCEMENT_STATUS_LOCKED
        == "NOT_ACTIVE_STAGE_29_PENDING"
    )


def test_manifest_pins_locked_redaction_token() -> None:
    assert (
        stage29_5_3_manifest.STAGE29_5_3_REDACTION_STATUS_LOCKED
        == "SAFE"
    )


def test_manifest_pins_side_channel_artifact_basename() -> None:
    assert (
        stage29_5_3_manifest.STAGE29_5_3_SIDE_CHANNEL_ARTIFACT_BASENAME
        == "stage29_5_3_migration_context.jsonl"
    )


def test_manifest_forbidden_surfaces_is_nonempty_closed_tuple() -> None:
    forbidden = (
        stage29_5_3_manifest.STAGE29_5_3_FORBIDDEN_SURFACES
    )
    assert isinstance(forbidden, tuple)
    assert len(forbidden) > 0
    for entry in forbidden:
        assert isinstance(entry, str)
        assert entry.strip() == entry
        assert entry


def test_manifest_forbidden_surfaces_carries_canonical_invariants() -> None:
    forbidden_lower = tuple(
        s.lower()
        for s in (
            stage29_5_3_manifest
            .STAGE29_5_3_FORBIDDEN_SURFACES
        )
    )
    required = (
        "production enforcement",
        "public routing",
        "subscriber routing",
        "paid tier routing",
        "telegram sender",
        "telegram client",
        "x / social sidecar",
        "automated trading",
        "position sizing",
        "trade execution",
        "wallet / private-key / signer logic",
        "private keys",
        "discord dispatch behavior change",
        "formatted discord rendering",
        "new env name",
        "new third-party runtime dependency",
        "phx1 import path",
        "pump.fun bonding-curve decoder",
        "dexscreener as a dispatch authority",
        "helius as a price source",
        "live helius websocket call",
        "live chainstack grpc call",
        "live birdeye http call",
        "live discord call",
        "stage 29.3 runtime wiring change",
        "stage 29.4 runtime wiring change",
        "stage 29.5 manifest inventory change",
        "stage 29.5.2 manifest inventory change",
        "direct stage 29.3 migration-context injection",
        "stage 29.6+ implementation",
    )
    for needle in required:
        assert needle in forbidden_lower, (
            f"Stage 29.5.3 manifest must pin "
            f"{needle!r} on the forbidden-surface list; "
            f"got {forbidden_lower!r}"
        )


def test_manifest_forbidden_surfaces_unlocks_only_29_5_3_surfaces() -> None:
    """Stage 29.5.3 narrows the Stage 29.5.2 forbidden-surface
    list by unlocking exactly the two surfaces Stage 29.5.3
    ships: the soak pass-entrypoint wrapper, and the side-
    channel artifact surface. Neither identifier should appear
    on the Stage 29.5.3 forbidden-surface list because the
    substage now ships them.
    """
    forbidden_lower = tuple(
        s.lower()
        for s in (
            stage29_5_3_manifest
            .STAGE29_5_3_FORBIDDEN_SURFACES
        )
    )
    assert (
        "soak pass-entrypoint wrapper"
        not in forbidden_lower
    ), (
        "Stage 29.5.3 unlocks the soak pass-entrypoint wrapper "
        "surface; the manifest must not pin it as forbidden"
    )
    assert (
        "side-channel artifact surface"
        not in forbidden_lower
    ), (
        "Stage 29.5.3 unlocks the side-channel artifact "
        "surface; the manifest must not pin it as forbidden"
    )


def test_manifest_actual_inventory_matches_stage29_root() -> None:
    from pathlib import Path

    stage29_root = (
        Path(__file__).resolve().parent.parent.parent
        / "stage29"
    )
    actual_py = {
        entry.name
        for entry in stage29_root.iterdir()
        if entry.is_file()
        and entry.suffix == ".py"
        and entry.name.startswith("stage29_5_3")
    }
    expected = set(
        stage29_5_3_manifest.STAGE29_5_3_PRODUCTION_PY_BASENAMES
    )
    assert actual_py == expected


def test_manifest_actual_runbook_matches_stage29_root() -> None:
    from pathlib import Path

    stage29_root = (
        Path(__file__).resolve().parent.parent.parent
        / "stage29"
    )
    runbook_path = (
        stage29_root
        / "STAGE_29_5_3_SOAK_PASS_WRAPPER_RUNBOOK.md"
    )
    assert runbook_path.is_file()


def test_manifest_actual_tests_match_stage29_test_root() -> None:
    from pathlib import Path

    tests_stage29 = (
        Path(__file__).resolve().parent
    )
    actual = {
        entry.name
        for entry in tests_stage29.iterdir()
        if entry.is_file()
        and entry.suffix == ".py"
        and entry.name.startswith("test_stage_29_5_3_")
    }
    expected = set(
        stage29_5_3_manifest.STAGE29_5_3_TEST_BASENAMES
    )
    assert actual == expected

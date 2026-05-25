"""Stage 29.3 no-migration-evidence source pins."""

from __future__ import annotations

from PHX2.stage27.migration_context_models import (
    MIGRATION_SOURCE_UNKNOWN,
)
from PHX2.stage27.price_ath_context_reader import (
    MigrationSourceSnapshot,
)
from PHX2.stage29.stage29_3_no_migration_evidence_source import (
    Stage29_3NoMigrationEvidenceSource,
)


def test_returns_unknown_migration_snapshot_for_any_mint():
    source = Stage29_3NoMigrationEvidenceSource()
    snap = source.read_migration_snapshot(
        "BeHSHaUCGC67PZLuHvj4EuNonZekbfBGMmWsWirmpump",
    )
    assert isinstance(snap, MigrationSourceSnapshot)
    assert snap.migration_event_id is None
    assert snap.migration_timestamp_utc is None
    assert snap.migration_source == MIGRATION_SOURCE_UNKNOWN
    assert snap.source_event_ref is None
    assert snap.raw_capture_ref is None


def test_deterministic_across_mints():
    source = Stage29_3NoMigrationEvidenceSource()
    for mint in (
        "Mint1AAA1111111111111111111111111111111111",
        "Mint2BBB2222222222222222222222222222222222",
        "Mint3CCC3333333333333333333333333333333333",
    ):
        snap = source.read_migration_snapshot(mint)
        assert snap.migration_event_id is None
        assert snap.migration_source == MIGRATION_SOURCE_UNKNOWN


def test_no_state_between_calls():
    source = Stage29_3NoMigrationEvidenceSource()
    a = source.read_migration_snapshot("MintAlpha111111111111111111111111111111111A")
    b = source.read_migration_snapshot("MintBeta22222222222222222222222222222222222B")
    assert a == b


def test_two_instances_return_identical_snapshots():
    s1 = Stage29_3NoMigrationEvidenceSource()
    s2 = Stage29_3NoMigrationEvidenceSource()
    a = s1.read_migration_snapshot("MintGamma333333333333333333333333333333333C")
    b = s2.read_migration_snapshot("MintGamma333333333333333333333333333333333C")
    assert a == b

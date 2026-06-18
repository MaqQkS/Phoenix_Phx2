"""Stage 30.14.0 replay-discovery source tests.

Offline / SYNTHETIC only. Proves the in-memory replay source:

  * yields the SAME injected migration-evidence batch deterministically;
  * driven through the committed Stage 30.13.0 auto-seeder, ACCEPTS a synthetic
    pump-suffix PRESENT record (the discovery -> seed boundary);
  * fails closed: a ``fault_reason`` raises the committed closed-set capture error so the
    auto-seeder records a ``WS_CAPTURE_FAILED`` outcome; a non-record item is classified
    ``NOT_A_RECORD``;
  * fails closed at construction on a non-iterable / str ``records`` arg or a blank
    ``fault_reason``.

The synthetic record + every fixture live HERE. No live capture, no socket, no env read,
no file write.
"""

from __future__ import annotations

import pytest

from PHX2.stage29.stage29_5_migration_models import (
    MIGRATION_SOURCE_HELIUS_WS,
    MIGRATION_STATUS_PRESENT,
    REFUSAL_REASON_MALFORMED_PAYLOAD,
    Stage29_5MigrationEvidenceError,
    Stage29_5MigrationEvidenceRecord,
)
from PHX2.stage30.stage30_11_13_fake_composer_proof import (
    PROOF_CREATED_AT,
    PROOF_MIGRATION_ANCHOR,
    PROOF_MINT,
)
from PHX2.stage30.stage30_13_0_ws_auto_seed_models import (
    SEED_DECISION_ACCEPTED,
    SEED_DECISION_ERROR,
    SEED_REASON_NOT_A_RECORD,
    SEED_REASON_SEEDED_FRESH_PUMP_MIGRATION,
    SEED_REASON_WS_CAPTURE_FAILED,
)
from PHX2.stage30.stage30_13_0_ws_auto_seeder import (
    build_seeded_watchlist_from_ws_discovery,
)
from PHX2.stage30.stage30_14_0_replay_discovery_source import (
    Stage30_14ReplayDiscoverySource,
    Stage30_14ReplaySourceError,
)


# A SYNTHETIC pump-suffix mint: a real-base58-shaped 44-char mint ending in the literal
# pump suffix (PROOF_MINT with its last 4 chars swapped for "pump"). NOT the real Build #25
# A2R6...pump mint, and built here -- the source fabricates nothing.
_SYNTH_PUMP_MINT: str = PROOF_MINT[:-4] + "pump"
_POOL: str = "P" * 44
_PROG: str = "G" * 44
_QUOTE: str = "Q" * 44


def _synthetic_record(
    base_mint: str = _SYNTH_PUMP_MINT,
) -> Stage29_5MigrationEvidenceRecord:
    return Stage29_5MigrationEvidenceRecord(
        migration_status=MIGRATION_STATUS_PRESENT,
        migration_source=MIGRATION_SOURCE_HELIUS_WS,
        base_mint=base_mint,
        pool_account=_POOL,
        pool_program_id=_PROG,
        quote_mint=_QUOTE,
        migration_timestamp_utc=PROOF_MIGRATION_ANCHOR,
        migration_slot=318000000,
        migration_signature="build26-synth-sig",
        observed_at_utc=PROOF_CREATED_AT,
        source_event_ref="build26_0_synthetic_source_ref",
    )


# ---------------------------------------------------------------------------
# 1. Deterministic yield
# ---------------------------------------------------------------------------


def test_deterministic_yield_returns_same_batch_each_call() -> None:
    record = _synthetic_record()
    source = Stage30_14ReplayDiscoverySource((record,))
    batch_one = source.read_migration_evidence_batch()
    batch_two = source.read_migration_evidence_batch()
    assert batch_one == (record,)
    assert batch_two == (record,)
    assert batch_one == batch_two
    assert source.record_count == 1
    assert source.is_fault_mode is False


# ---------------------------------------------------------------------------
# 2. Driven through the committed auto-seeder: accepts a synthetic pump record
# ---------------------------------------------------------------------------


def test_auto_seeder_over_replay_source_accepts_synthetic_pump() -> None:
    source = Stage30_14ReplayDiscoverySource((_synthetic_record(),))
    result = build_seeded_watchlist_from_ws_discovery(
        source, created_at_utc=PROOF_CREATED_AT, max_seed=1
    )
    assert result.summary.records_seen == 1
    assert result.summary.accepted == 1
    assert result.outcomes[0].seed_decision == SEED_DECISION_ACCEPTED
    assert (
        result.outcomes[0].seed_reason == SEED_REASON_SEEDED_FRESH_PUMP_MIGRATION
    )
    assert len(result.seeded_summaries) == 1
    assert result.seeded_summaries[0].token_mint == _SYNTH_PUMP_MINT
    assert result.seeded_summaries[0].measurement_status == "COMPLETE"
    assert (
        result.seeded_summaries[0].migration_event_time_utc
        == PROOF_MIGRATION_ANCHOR
    )


# ---------------------------------------------------------------------------
# 3. Fail-closed: fault mode -> WS_CAPTURE_FAILED
# ---------------------------------------------------------------------------


def test_fault_mode_raises_committed_capture_error() -> None:
    source = Stage30_14ReplayDiscoverySource(
        (), fault_reason=REFUSAL_REASON_MALFORMED_PAYLOAD
    )
    assert source.is_fault_mode is True
    with pytest.raises(Stage29_5MigrationEvidenceError):
        source.read_migration_evidence_batch()


def test_fault_mode_fails_closed_via_auto_seeder() -> None:
    source = Stage30_14ReplayDiscoverySource(
        (), fault_reason=REFUSAL_REASON_MALFORMED_PAYLOAD
    )
    result = build_seeded_watchlist_from_ws_discovery(
        source, created_at_utc=PROOF_CREATED_AT, max_seed=1
    )
    assert result.summary.error == 1
    assert result.summary.accepted == 0
    assert result.summary.records_seen == 0
    assert result.outcomes[0].seed_decision == SEED_DECISION_ERROR
    assert result.outcomes[0].seed_reason == SEED_REASON_WS_CAPTURE_FAILED
    assert result.seeded_summaries == ()


# ---------------------------------------------------------------------------
# 4. Fail-closed: a non-record item -> NOT_A_RECORD
# ---------------------------------------------------------------------------


def test_non_record_item_fails_closed_to_not_a_record() -> None:
    source = Stage30_14ReplayDiscoverySource(({"not": "a record"},))
    result = build_seeded_watchlist_from_ws_discovery(
        source, created_at_utc=PROOF_CREATED_AT, max_seed=1
    )
    assert result.summary.error == 1
    assert result.summary.accepted == 0
    assert result.outcomes[0].seed_decision == SEED_DECISION_ERROR
    assert result.outcomes[0].seed_reason == SEED_REASON_NOT_A_RECORD
    assert result.seeded_summaries == ()


# ---------------------------------------------------------------------------
# 5. Fail-closed at construction (caller shape)
# ---------------------------------------------------------------------------


def test_construction_rejects_non_iterable_records() -> None:
    with pytest.raises(Stage30_14ReplaySourceError):
        Stage30_14ReplayDiscoverySource(123)


def test_construction_rejects_str_records() -> None:
    with pytest.raises(Stage30_14ReplaySourceError):
        Stage30_14ReplayDiscoverySource("not-a-batch")


def test_construction_rejects_blank_fault_reason() -> None:
    with pytest.raises(Stage30_14ReplaySourceError):
        Stage30_14ReplayDiscoverySource((), fault_reason="   ")


def test_empty_batch_seeds_nothing() -> None:
    source = Stage30_14ReplayDiscoverySource(())
    result = build_seeded_watchlist_from_ws_discovery(
        source, created_at_utc=PROOF_CREATED_AT, max_seed=1
    )
    assert result.summary.records_seen == 0
    assert result.summary.accepted == 0
    assert result.seeded_summaries == ()

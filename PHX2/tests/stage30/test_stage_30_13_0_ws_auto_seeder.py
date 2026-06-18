"""Stage 30.13.0 bounded WS auto-seeder tests.

Offline / fake-discovery only. Drives the auto-seeder over an injected fake discovery
exposing ``read_migration_evidence_batch()`` and pins:

  * the per-record decision ladder (accepted / not-present / not-pump / duplicate /
    incomplete / not-a-record);
  * the four-count ledger + its invariants;
  * the fail-closed WS-capture-error path (the discovery raising);
  * the bounded seed cap + the caller-shape config failure;
  * the accepted record's seeded sanitized summary identity;
  * the redaction self-scan.

No real socket, no network, no env read, no Discord, no durable ledger.
"""

from __future__ import annotations

import pytest

from PHX2.stage29.stage29_5_migration_models import (
    MIGRATION_SOURCE_HELIUS_WS,
    MIGRATION_SOURCE_UNKNOWN_STAGE29_5,
    MIGRATION_STATUS_MISSING,
    MIGRATION_STATUS_PRESENT,
    REFUSAL_REASON_MALFORMED_PAYLOAD,
    Stage29_5MigrationEvidenceError,
    Stage29_5MigrationEvidenceRecord,
)
from PHX2.stage30.stage30_13_0_ws_auto_seed_models import (
    SEED_DECISION_ACCEPTED,
    SEED_DECISION_DUPLICATE,
    SEED_DECISION_ERROR,
    SEED_DECISION_REJECTED,
    SEED_REASON_DUPLICATE_MINT,
    SEED_REASON_INCOMPLETE_EVIDENCE,
    SEED_REASON_NOT_A_RECORD,
    SEED_REASON_NOT_PRESENT_MIGRATION,
    SEED_REASON_NOT_PUMP_SUFFIX,
    SEED_REASON_SEEDED_FRESH_PUMP_MIGRATION,
    SEED_REASON_WS_CAPTURE_FAILED,
    STAGE30_13_REDACTION_STATUS_REDACTED,
    Stage30_13AutoSeedResult,
)
from PHX2.stage30.stage30_13_0_ws_auto_seeder import (
    Stage30_13AutoSeedError,
    build_seeded_watchlist_from_ws_discovery,
)


_PUMP_A = "A" * 40 + "pump"
_PUMP_B = "B" * 40 + "pump"
_PUMP_C = "C" * 40 + "pump"
_NON_PUMP = "D" * 44
_POOL = "P" * 44
_PROG = "G" * 44
_QUOTE = "Q" * 44
_TS = "2026-06-06T06:00:00Z"
_OBS = "2026-06-07T00:00:00+00:00"
_CREATED = "2026-06-07T01:00:00+00:00"


def _present(mint: str, *, full: bool = True) -> Stage29_5MigrationEvidenceRecord:
    return Stage29_5MigrationEvidenceRecord(
        migration_status=MIGRATION_STATUS_PRESENT,
        migration_source=MIGRATION_SOURCE_HELIUS_WS,
        base_mint=mint,
        pool_account=_POOL,
        pool_program_id=_PROG,
        quote_mint=_QUOTE,
        migration_timestamp_utc=_TS,
        migration_slot=(123456 if full else None),
        migration_signature=("sig-x" if full else None),
        observed_at_utc=_OBS,
        source_event_ref=("ref-x" if full else None),
    )


def _missing() -> Stage29_5MigrationEvidenceRecord:
    return Stage29_5MigrationEvidenceRecord(
        migration_status=MIGRATION_STATUS_MISSING,
        migration_source=MIGRATION_SOURCE_UNKNOWN_STAGE29_5,
        base_mint=None,
        pool_account=None,
        pool_program_id=None,
        quote_mint=None,
        migration_timestamp_utc=None,
        migration_slot=None,
        migration_signature=None,
        observed_at_utc=_OBS,
        source_event_ref=None,
    )


class _FakeDiscovery:
    """In-memory fake exposing the WS adapter's ``read_migration_evidence_batch``."""

    def __init__(self, batch) -> None:
        self._batch = list(batch)

    def read_migration_evidence_batch(self):
        return tuple(self._batch)


class _RaisingDiscovery:
    def __init__(self, exc: BaseException) -> None:
        self._exc = exc

    def read_migration_evidence_batch(self):
        raise self._exc


def _seed(discovery, *, max_seed: int = 10) -> Stage30_13AutoSeedResult:
    return build_seeded_watchlist_from_ws_discovery(
        discovery, created_at_utc=_CREATED, max_seed=max_seed
    )


# ---------------------------------------------------------------------------
# 1. Accept path
# ---------------------------------------------------------------------------


def test_present_pump_record_is_accepted_and_seeded() -> None:
    result = _seed(_FakeDiscovery([_present(_PUMP_A)]))
    assert result.summary.accepted == 1
    assert result.summary.rejected == 0
    assert result.summary.duplicate == 0
    assert result.summary.error == 0
    assert result.summary.records_seen == 1
    assert len(result.seeded_summaries) == 1
    # The seeded sanitized summary carries the discovered mint identity verbatim.
    assert result.seeded_summaries[0].token_mint == _PUMP_A
    assert result.outcomes[0].seed_decision == SEED_DECISION_ACCEPTED
    assert result.outcomes[0].seed_reason == SEED_REASON_SEEDED_FRESH_PUMP_MIGRATION
    assert result.outcomes[0].token_mint == _PUMP_A
    assert result.redaction_status == STAGE30_13_REDACTION_STATUS_REDACTED


# ---------------------------------------------------------------------------
# 2. Mixed batch -> all four counts in one pass
# ---------------------------------------------------------------------------


def test_mixed_batch_yields_all_four_counts() -> None:
    batch = [
        _present(_PUMP_A),            # ACCEPTED
        _present(_PUMP_A),            # DUPLICATE (same mint, first-wins)
        _present(_NON_PUMP),         # REJECTED NOT_PUMP_SUFFIX
        _missing(),                  # REJECTED NOT_PRESENT_MIGRATION
        _present(_PUMP_B, full=False),  # REJECTED INCOMPLETE_EVIDENCE
        "i-am-not-a-record",         # ERROR NOT_A_RECORD
    ]
    result = _seed(_FakeDiscovery(batch))

    assert result.summary.accepted == 1
    assert result.summary.duplicate == 1
    assert result.summary.rejected == 3
    assert result.summary.error == 1
    assert result.summary.records_seen == 6

    decisions = [o.seed_decision for o in result.outcomes]
    reasons = [o.seed_reason for o in result.outcomes]
    assert decisions == [
        SEED_DECISION_ACCEPTED,
        SEED_DECISION_DUPLICATE,
        SEED_DECISION_REJECTED,
        SEED_DECISION_REJECTED,
        SEED_DECISION_REJECTED,
        SEED_DECISION_ERROR,
    ]
    assert reasons == [
        SEED_REASON_SEEDED_FRESH_PUMP_MIGRATION,
        SEED_REASON_DUPLICATE_MINT,
        SEED_REASON_NOT_PUMP_SUFFIX,
        SEED_REASON_NOT_PRESENT_MIGRATION,
        SEED_REASON_INCOMPLETE_EVIDENCE,
        SEED_REASON_NOT_A_RECORD,
    ]


def test_count_invariants_hold() -> None:
    batch = [
        _present(_PUMP_A),
        _present(_PUMP_A),
        _present(_NON_PUMP),
        _missing(),
        _present(_PUMP_B, full=False),
        "not-a-record",
    ]
    result = _seed(_FakeDiscovery(batch))
    s = result.summary
    # len(outcomes) == accepted + rejected + duplicate + error
    assert len(result.outcomes) == s.accepted + s.rejected + s.duplicate + s.error
    # records_seen == accepted + rejected + duplicate + (NOT_A_RECORD count)
    not_a_record = sum(
        1 for o in result.outcomes if o.seed_reason == SEED_REASON_NOT_A_RECORD
    )
    assert s.records_seen == s.accepted + s.rejected + s.duplicate + not_a_record
    # ACCEPTED is the only decision that seeds a summary.
    assert len(result.seeded_summaries) == s.accepted


# ---------------------------------------------------------------------------
# 3. Fail-closed WS capture error (the discovery raises)
# ---------------------------------------------------------------------------


def test_discovery_raising_stage29_error_is_ws_capture_failed() -> None:
    discovery = _RaisingDiscovery(
        Stage29_5MigrationEvidenceError(REFUSAL_REASON_MALFORMED_PAYLOAD, "boom")
    )
    result = _seed(discovery)
    assert result.summary.error == 1
    assert result.summary.records_seen == 0
    assert result.summary.accepted == 0
    assert len(result.seeded_summaries) == 0
    assert len(result.outcomes) == 1
    assert result.outcomes[0].seed_decision == SEED_DECISION_ERROR
    assert result.outcomes[0].seed_reason == SEED_REASON_WS_CAPTURE_FAILED
    assert result.outcomes[0].token_mint == ""


def test_discovery_raising_generic_error_also_fails_closed() -> None:
    result = _seed(_RaisingDiscovery(ValueError("real-transport-blew-up")))
    assert result.summary.error == 1
    assert result.outcomes[0].seed_reason == SEED_REASON_WS_CAPTURE_FAILED


def test_discovery_keyboard_interrupt_is_not_swallowed() -> None:
    with pytest.raises(KeyboardInterrupt):
        _seed(_RaisingDiscovery(KeyboardInterrupt()))


# ---------------------------------------------------------------------------
# 4. Bounded seed cap + caller-shape config failure
# ---------------------------------------------------------------------------


def test_seed_cap_stops_at_max_seed() -> None:
    batch = [_present(_PUMP_A), _present(_PUMP_B), _present(_PUMP_C)]
    result = _seed(_FakeDiscovery(batch), max_seed=2)
    assert result.summary.records_seen == 2
    assert result.summary.accepted == 2
    assert len(result.outcomes) == 2


def test_invalid_max_seed_fails_closed_before_driving_discovery() -> None:
    class _Tripwire:
        def read_migration_evidence_batch(self):
            raise AssertionError("discovery must not be driven on a bad cap")

    for bad in (0, -1, 11, True, "5", 5.0):
        with pytest.raises(Stage30_13AutoSeedError):
            build_seeded_watchlist_from_ws_discovery(
                _Tripwire(), created_at_utc=_CREATED, max_seed=bad  # type: ignore[arg-type]
            )


# ---------------------------------------------------------------------------
# 5. Empty batch + determinism
# ---------------------------------------------------------------------------


def test_empty_batch_yields_zero_counts_and_redacted() -> None:
    result = _seed(_FakeDiscovery([]))
    assert result.summary.records_seen == 0
    assert result.summary.accepted == 0
    assert result.summary.rejected == 0
    assert result.summary.duplicate == 0
    assert result.summary.error == 0
    assert result.outcomes == ()
    assert result.seeded_summaries == ()
    assert result.redaction_status == STAGE30_13_REDACTION_STATUS_REDACTED


def test_deterministic_for_same_batch() -> None:
    batch = [_present(_PUMP_A), _present(_NON_PUMP), _missing()]
    a = _seed(_FakeDiscovery(batch))
    b = _seed(_FakeDiscovery(batch))
    assert a == b


def test_distinct_pump_mints_all_accepted() -> None:
    batch = [_present(_PUMP_A), _present(_PUMP_B), _present(_PUMP_C)]
    result = _seed(_FakeDiscovery(batch))
    assert result.summary.accepted == 3
    assert result.summary.duplicate == 0
    seeded = {s.token_mint for s in result.seeded_summaries}
    assert seeded == {_PUMP_A, _PUMP_B, _PUMP_C}

"""Stage 22.2 InMemoryDedupeLedger semantic tests.

Pins the per-implementation semantics for the no-I/O ledger:

  * Logical dedupe identity is (provider_id, chain, event_id).
  * Audit field drift on the SAME logical key resolves as
    duplicate, not as new (the duplicate-send hazard the
    Stage 22.2 design closes).
  * mark_dispatched is idempotent on already-dispatched and a
    hard contract violation on unknown.
  * The in-memory ledger never emits ``ledger_unavailable``.
"""

from __future__ import annotations

import pytest

from PHX2.stage22.constants import (
    DEDUPE_OUTCOME_DUPLICATE_ALREADY_DISPATCHED,
    DEDUPE_OUTCOME_DUPLICATE_NOT_YET_DISPATCHED,
    DEDUPE_OUTCOME_LEDGER_UNAVAILABLE,
    DEDUPE_OUTCOME_NEW,
)
from PHX2.stage22.dedupe_ledger import (
    InMemoryDedupeLedger,
    ingest_key_logical_id,
)
from PHX2.stage22.errors import Stage22LedgerContractError
from PHX2.stage22.ingest_contracts import IngestEventKey


def _key(
    *,
    provider_id: str = "helius",
    chain: str = "solana_mainnet",
    event_id: str = "evt_0123456789abcdef01234567",
    provider_event_id: str = "prov-abc",
    raw_event_hash: str = "a" * 64,
) -> IngestEventKey:
    return IngestEventKey(
        provider_id=provider_id,
        chain=chain,
        event_id=event_id,
        provider_event_id=provider_event_id,
        raw_event_hash=raw_event_hash,
    )


# ---------------------------------------------------------------------------
# Logical identity projection
# ---------------------------------------------------------------------------


def test_ingest_key_logical_id_returns_three_tuple():
    logical = ingest_key_logical_id(key=_key())
    assert logical == (
        "helius",
        "solana_mainnet",
        "evt_0123456789abcdef01234567",
    )


def test_ingest_key_logical_id_ignores_provider_event_id():
    a = ingest_key_logical_id(key=_key(provider_event_id="prov-a"))
    b = ingest_key_logical_id(key=_key(provider_event_id="prov-b"))
    assert a == b


def test_ingest_key_logical_id_ignores_raw_event_hash():
    a = ingest_key_logical_id(key=_key(raw_event_hash="0" * 64))
    b = ingest_key_logical_id(key=_key(raw_event_hash="f" * 64))
    assert a == b


def test_ingest_key_logical_id_keyword_only_signature():
    with pytest.raises(TypeError):
        ingest_key_logical_id(_key())  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Core semantic behaviour
# ---------------------------------------------------------------------------


def test_first_check_and_record_returns_new():
    ledger = InMemoryDedupeLedger()
    outcome = ledger.check_and_record(key=_key())
    assert outcome.outcome == DEDUPE_OUTCOME_NEW
    assert outcome.ingest_key == _key()


def test_second_check_before_dispatch_returns_duplicate_not_yet_dispatched():
    ledger = InMemoryDedupeLedger()
    k = _key()
    ledger.check_and_record(key=k)
    outcome = ledger.check_and_record(key=k)
    assert outcome.outcome == DEDUPE_OUTCOME_DUPLICATE_NOT_YET_DISPATCHED


def test_mark_dispatched_changes_state():
    ledger = InMemoryDedupeLedger()
    k = _key()
    ledger.check_and_record(key=k)
    ledger.mark_dispatched(key=k)
    outcome = ledger.check_and_record(key=k)
    assert outcome.outcome == DEDUPE_OUTCOME_DUPLICATE_ALREADY_DISPATCHED


def test_check_after_dispatch_returns_duplicate_already_dispatched():
    ledger = InMemoryDedupeLedger()
    k = _key()
    ledger.check_and_record(key=k)
    ledger.mark_dispatched(key=k)
    outcome = ledger.check_and_record(key=k)
    assert outcome.outcome == DEDUPE_OUTCOME_DUPLICATE_ALREADY_DISPATCHED


# ---------------------------------------------------------------------------
# mark_dispatched discipline
# ---------------------------------------------------------------------------


def test_mark_dispatched_idempotent_on_already_dispatched():
    ledger = InMemoryDedupeLedger()
    k = _key()
    ledger.check_and_record(key=k)
    ledger.mark_dispatched(key=k)
    # second call must be a no-op, not raise
    ledger.mark_dispatched(key=k)
    outcome = ledger.check_and_record(key=k)
    assert outcome.outcome == DEDUPE_OUTCOME_DUPLICATE_ALREADY_DISPATCHED


def test_mark_dispatched_returns_none_on_success():
    ledger = InMemoryDedupeLedger()
    k = _key()
    ledger.check_and_record(key=k)
    assert ledger.mark_dispatched(key=k) is None


def test_mark_dispatched_returns_none_on_idempotent_second_call():
    ledger = InMemoryDedupeLedger()
    k = _key()
    ledger.check_and_record(key=k)
    ledger.mark_dispatched(key=k)
    assert ledger.mark_dispatched(key=k) is None


def test_mark_dispatched_unknown_logical_key_raises():
    ledger = InMemoryDedupeLedger()
    with pytest.raises(Stage22LedgerContractError):
        ledger.mark_dispatched(key=_key())


# ---------------------------------------------------------------------------
# Independent logical keys
# ---------------------------------------------------------------------------


def test_different_event_ids_independent():
    ledger = InMemoryDedupeLedger()
    k1 = _key(event_id="evt_aaaaaaaaaaaaaaaaaaaaaaaa")
    k2 = _key(event_id="evt_bbbbbbbbbbbbbbbbbbbbbbbb")
    assert ledger.check_and_record(key=k1).outcome == DEDUPE_OUTCOME_NEW
    assert ledger.check_and_record(key=k2).outcome == DEDUPE_OUTCOME_NEW
    assert (
        ledger.check_and_record(key=k1).outcome
        == DEDUPE_OUTCOME_DUPLICATE_NOT_YET_DISPATCHED
    )
    assert (
        ledger.check_and_record(key=k2).outcome
        == DEDUPE_OUTCOME_DUPLICATE_NOT_YET_DISPATCHED
    )


def test_same_event_id_different_provider_id_independent():
    ledger = InMemoryDedupeLedger()
    k1 = _key(provider_id="helius")
    k2 = _key(provider_id="birdeye")
    assert ledger.check_and_record(key=k1).outcome == DEDUPE_OUTCOME_NEW
    assert ledger.check_and_record(key=k2).outcome == DEDUPE_OUTCOME_NEW


def test_same_event_id_different_chain_independent():
    ledger = InMemoryDedupeLedger()
    k1 = _key(chain="solana_mainnet")
    k2 = _key(chain="solana_devnet")
    assert ledger.check_and_record(key=k1).outcome == DEDUPE_OUTCOME_NEW
    assert ledger.check_and_record(key=k2).outcome == DEDUPE_OUTCOME_NEW


# ---------------------------------------------------------------------------
# Audit-field drift does NOT change dedupe identity
# (the duplicate-send hazard the 22.2 design closes)
# ---------------------------------------------------------------------------


def test_audit_provider_event_id_drift_resolves_as_duplicate():
    ledger = InMemoryDedupeLedger()
    k1 = _key(provider_event_id="prov-1")
    k2 = _key(provider_event_id="prov-2")
    assert ledger.check_and_record(key=k1).outcome == DEDUPE_OUTCOME_NEW
    outcome = ledger.check_and_record(key=k2)
    assert outcome.outcome == DEDUPE_OUTCOME_DUPLICATE_NOT_YET_DISPATCHED


def test_audit_raw_event_hash_drift_resolves_as_duplicate():
    ledger = InMemoryDedupeLedger()
    k1 = _key(raw_event_hash="0" * 64)
    k2 = _key(raw_event_hash="f" * 64)
    assert ledger.check_and_record(key=k1).outcome == DEDUPE_OUTCOME_NEW
    outcome = ledger.check_and_record(key=k2)
    assert outcome.outcome == DEDUPE_OUTCOME_DUPLICATE_NOT_YET_DISPATCHED


def test_audit_drift_after_dispatch_resolves_as_already_dispatched():
    ledger = InMemoryDedupeLedger()
    k1 = _key(provider_event_id="prov-1", raw_event_hash="0" * 64)
    k2 = _key(provider_event_id="prov-2", raw_event_hash="f" * 64)
    ledger.check_and_record(key=k1)
    ledger.mark_dispatched(key=k1)
    outcome = ledger.check_and_record(key=k2)
    assert outcome.outcome == DEDUPE_OUTCOME_DUPLICATE_ALREADY_DISPATCHED


def test_mark_dispatched_works_with_audit_drift():
    ledger = InMemoryDedupeLedger()
    k1 = _key(provider_event_id="prov-1")
    k2 = _key(provider_event_id="prov-2")
    ledger.check_and_record(key=k1)
    # mark_dispatched is called with k2 which has different
    # audit fields but the same logical id. Should succeed
    # (same logical key).
    ledger.mark_dispatched(key=k2)
    outcome = ledger.check_and_record(key=k1)
    assert outcome.outcome == DEDUPE_OUTCOME_DUPLICATE_ALREADY_DISPATCHED


# ---------------------------------------------------------------------------
# DedupeOutcome echo behaviour
# ---------------------------------------------------------------------------


def test_dedupe_outcome_ingest_key_echoes_incoming_key_on_new():
    ledger = InMemoryDedupeLedger()
    k = _key()
    outcome = ledger.check_and_record(key=k)
    assert outcome.ingest_key == k


def test_dedupe_outcome_ingest_key_echoes_incoming_key_on_duplicate():
    """The outcome echoes the *incoming* key on every call, even
    when the audit fields differ from the originally-stored key.
    The caller can use this to record per-occurrence audit
    material without the ledger having to merge audit fields.
    """
    ledger = InMemoryDedupeLedger()
    k1 = _key(provider_event_id="prov-1", raw_event_hash="0" * 64)
    k2 = _key(provider_event_id="prov-2", raw_event_hash="f" * 64)
    out1 = ledger.check_and_record(key=k1)
    assert out1.ingest_key == k1
    out2 = ledger.check_and_record(key=k2)
    assert out2.ingest_key == k2


# ---------------------------------------------------------------------------
# Ledger-unavailable invariant
# ---------------------------------------------------------------------------


def test_in_memory_ledger_never_emits_ledger_unavailable_across_many_calls():
    ledger = InMemoryDedupeLedger()
    for i in range(50):
        k = _key(event_id=f"evt_{i:024x}")
        outcome = ledger.check_and_record(key=k)
        assert outcome.outcome != DEDUPE_OUTCOME_LEDGER_UNAVAILABLE


# ---------------------------------------------------------------------------
# No clock / no env / no file I/O on the in-memory implementation
# ---------------------------------------------------------------------------


def test_in_memory_ledger_construction_is_arg_free():
    ledger = InMemoryDedupeLedger()
    # Trivial smoke: construction succeeds with no args and
    # produces an empty ledger.
    outcome = ledger.check_and_record(key=_key())
    assert outcome.outcome == DEDUPE_OUTCOME_NEW


def test_two_in_memory_ledgers_have_independent_state():
    ledger_a = InMemoryDedupeLedger()
    ledger_b = InMemoryDedupeLedger()
    ledger_a.check_and_record(key=_key())
    outcome = ledger_b.check_and_record(key=_key())
    assert outcome.outcome == DEDUPE_OUTCOME_NEW


# ---------------------------------------------------------------------------
# Keyword-only signature discipline
# ---------------------------------------------------------------------------


def test_check_and_record_is_keyword_only():
    ledger = InMemoryDedupeLedger()
    with pytest.raises(TypeError):
        ledger.check_and_record(_key())  # type: ignore[misc]


def test_mark_dispatched_is_keyword_only():
    ledger = InMemoryDedupeLedger()
    ledger.check_and_record(key=_key())
    with pytest.raises(TypeError):
        ledger.mark_dispatched(_key())  # type: ignore[misc]

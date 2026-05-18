"""Stage 22.2 DedupeLedger Protocol parity tests.

Parameterizes the shared semantic suite over both Stage 22.2
ledger implementations (``InMemoryDedupeLedger`` and
``JsonlDedupeLedger``) so any behavioural drift between them
fails here. The Stage 22.1 ``DedupeLedger`` Protocol is the
contract surface both implementations satisfy.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

import pytest

from PHX2.stage22.constants import (
    DEDUPE_OUTCOME_DUPLICATE_ALREADY_DISPATCHED,
    DEDUPE_OUTCOME_DUPLICATE_NOT_YET_DISPATCHED,
    DEDUPE_OUTCOME_NEW,
)
from PHX2.stage22.dedupe_ledger import (
    InMemoryDedupeLedger,
    JsonlDedupeLedger,
)
from PHX2.stage22.errors import Stage22LedgerContractError
from PHX2.stage22.ingest_contracts import (
    DedupeLedger,
    DedupeOutcome,
    IngestEventKey,
)


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


@pytest.fixture(params=["in_memory", "jsonl"])
def ledger(
    request: pytest.FixtureRequest,
    tmp_path: Path,
) -> DedupeLedger:
    """Build one of each Stage 22.2 ledger implementation.

    The return type annotation ``DedupeLedger`` pins that both
    implementations structurally satisfy the Stage 22.1 Protocol;
    Python won't enforce this at runtime (the Protocol is not
    ``runtime_checkable``), so the parametrized semantic tests
    below are the actual parity proof.
    """
    if request.param == "in_memory":
        return InMemoryDedupeLedger()  # type: ignore[return-value]
    return JsonlDedupeLedger(  # type: ignore[return-value]
        path=tmp_path / "ledger.jsonl",
    )


# ---------------------------------------------------------------------------
# Shared semantic suite
# ---------------------------------------------------------------------------


def test_parity_first_check_returns_new(ledger: DedupeLedger) -> None:
    outcome: DedupeOutcome = ledger.check_and_record(key=_key())
    assert outcome.outcome == DEDUPE_OUTCOME_NEW
    assert outcome.ingest_key == _key()


def test_parity_duplicate_before_dispatch(ledger: DedupeLedger) -> None:
    k = _key()
    ledger.check_and_record(key=k)
    outcome = ledger.check_and_record(key=k)
    assert outcome.outcome == DEDUPE_OUTCOME_DUPLICATE_NOT_YET_DISPATCHED


def test_parity_duplicate_after_dispatch(ledger: DedupeLedger) -> None:
    k = _key()
    ledger.check_and_record(key=k)
    ledger.mark_dispatched(key=k)
    outcome = ledger.check_and_record(key=k)
    assert outcome.outcome == DEDUPE_OUTCOME_DUPLICATE_ALREADY_DISPATCHED


def test_parity_mark_dispatched_idempotent(ledger: DedupeLedger) -> None:
    k = _key()
    ledger.check_and_record(key=k)
    ledger.mark_dispatched(key=k)
    ledger.mark_dispatched(key=k)
    outcome = ledger.check_and_record(key=k)
    assert outcome.outcome == DEDUPE_OUTCOME_DUPLICATE_ALREADY_DISPATCHED


def test_parity_mark_dispatched_unknown_raises(
    ledger: DedupeLedger,
) -> None:
    with pytest.raises(Stage22LedgerContractError):
        ledger.mark_dispatched(key=_key())


def test_parity_audit_provider_event_id_drift_is_duplicate(
    ledger: DedupeLedger,
) -> None:
    ledger.check_and_record(key=_key(provider_event_id="prov-1"))
    outcome = ledger.check_and_record(key=_key(provider_event_id="prov-2"))
    assert outcome.outcome == DEDUPE_OUTCOME_DUPLICATE_NOT_YET_DISPATCHED


def test_parity_audit_raw_event_hash_drift_is_duplicate(
    ledger: DedupeLedger,
) -> None:
    ledger.check_and_record(key=_key(raw_event_hash="0" * 64))
    outcome = ledger.check_and_record(key=_key(raw_event_hash="f" * 64))
    assert outcome.outcome == DEDUPE_OUTCOME_DUPLICATE_NOT_YET_DISPATCHED


def test_parity_independent_event_ids(ledger: DedupeLedger) -> None:
    k1 = _key(event_id="evt_aaaaaaaaaaaaaaaaaaaaaaaa")
    k2 = _key(event_id="evt_bbbbbbbbbbbbbbbbbbbbbbbb")
    assert ledger.check_and_record(key=k1).outcome == DEDUPE_OUTCOME_NEW
    assert ledger.check_and_record(key=k2).outcome == DEDUPE_OUTCOME_NEW


def test_parity_independent_provider_id(ledger: DedupeLedger) -> None:
    k1 = _key(provider_id="helius")
    k2 = _key(provider_id="birdeye")
    assert ledger.check_and_record(key=k1).outcome == DEDUPE_OUTCOME_NEW
    assert ledger.check_and_record(key=k2).outcome == DEDUPE_OUTCOME_NEW


def test_parity_independent_chain(ledger: DedupeLedger) -> None:
    k1 = _key(chain="solana_mainnet")
    k2 = _key(chain="solana_devnet")
    assert ledger.check_and_record(key=k1).outcome == DEDUPE_OUTCOME_NEW
    assert ledger.check_and_record(key=k2).outcome == DEDUPE_OUTCOME_NEW


def test_parity_dedupe_outcome_echoes_incoming_key(
    ledger: DedupeLedger,
) -> None:
    k1 = _key(provider_event_id="prov-1", raw_event_hash="0" * 64)
    k2 = _key(provider_event_id="prov-2", raw_event_hash="f" * 64)
    out1 = ledger.check_and_record(key=k1)
    assert out1.ingest_key == k1
    out2 = ledger.check_and_record(key=k2)
    assert out2.ingest_key == k2


def test_parity_mark_dispatched_returns_none(ledger: DedupeLedger) -> None:
    k = _key()
    ledger.check_and_record(key=k)
    assert ledger.mark_dispatched(key=k) is None


# ---------------------------------------------------------------------------
# Structural Protocol shape
# ---------------------------------------------------------------------------


def test_check_and_record_is_callable(ledger: DedupeLedger) -> None:
    func: Callable[..., DedupeOutcome] = ledger.check_and_record
    assert callable(func)


def test_mark_dispatched_is_callable(ledger: DedupeLedger) -> None:
    func: Callable[..., None] = ledger.mark_dispatched
    assert callable(func)

"""Stage 27.6 run-local dedupe tests.

Pins:

  * ``Stage27_6DedupeKey`` is an immutable ``NamedTuple``.
  * ``make_dedupe_key`` is pure / deterministic.
  * Identical fields produce identical keys.
  * Different fields produce different keys.
  * Missing ``normalized_event_id`` falls back to
    ``provider_event_id``.
  * Both ids missing -> ``normalized_event_id`` slot is ``None``.
  * ``Stage27_6RunLocalDedupe`` admits a key once and rejects
    duplicates thereafter.
  * ``record`` reports whether the key was new.
  * ``size`` returns the recorded ledger size.
  * ``snapshot`` returns a deterministic tuple.
  * The ledger is in-memory only (no on-disk persistence surface).
"""

from __future__ import annotations

import pytest

from PHX2.stage27.live_dedupe import (
    STAGE27_6_DEDUPE_SCHEMA_VERSION,
    Stage27_6DedupeKey,
    Stage27_6RunLocalDedupe,
    make_dedupe_key,
)


# ---------------------------------------------------------------------------
# Schema version axis
# ---------------------------------------------------------------------------


def test_stage_27_6_dedupe_schema_version_is_locked():
    assert STAGE27_6_DEDUPE_SCHEMA_VERSION == (
        "stage27_v0_run_local_dedupe"
    )


# ---------------------------------------------------------------------------
# DedupeKey shape
# ---------------------------------------------------------------------------


def test_dedupe_key_is_named_tuple():
    key = Stage27_6DedupeKey(
        token_mint="MINT",
        pair_type="PUMP_SOL",
        event_kind="SWAP",
        normalized_event_id="evt1",
    )
    assert key.token_mint == "MINT"
    assert key.pair_type == "PUMP_SOL"
    assert key.event_kind == "SWAP"
    assert key.normalized_event_id == "evt1"
    assert isinstance(key, tuple)


def test_dedupe_key_is_immutable():
    key = Stage27_6DedupeKey(
        token_mint="MINT",
        pair_type="PUMP_SOL",
        event_kind="SWAP",
        normalized_event_id="evt1",
    )
    with pytest.raises(AttributeError):
        key.token_mint = "MUTATED"  # type: ignore[misc]


def test_dedupe_key_equality_is_field_wise():
    a = Stage27_6DedupeKey(
        token_mint="M",
        pair_type="PUMP_SOL",
        event_kind="SWAP",
        normalized_event_id="e",
    )
    b = Stage27_6DedupeKey(
        token_mint="M",
        pair_type="PUMP_SOL",
        event_kind="SWAP",
        normalized_event_id="e",
    )
    c = Stage27_6DedupeKey(
        token_mint="M",
        pair_type="PUMP_SOL",
        event_kind="SWAP",
        normalized_event_id="other",
    )
    assert a == b
    assert hash(a) == hash(b)
    assert a != c


# ---------------------------------------------------------------------------
# make_dedupe_key
# ---------------------------------------------------------------------------


def test_make_dedupe_key_pure_for_identical_inputs():
    a = make_dedupe_key(
        token_mint="M",
        pair_type="PUMP_SOL",
        event_kind="SWAP",
        normalized_event_id="evt",
    )
    b = make_dedupe_key(
        token_mint="M",
        pair_type="PUMP_SOL",
        event_kind="SWAP",
        normalized_event_id="evt",
    )
    assert a == b


def test_make_dedupe_key_falls_back_to_provider_event_id():
    key = make_dedupe_key(
        token_mint="M",
        pair_type="PUMP_SOL",
        event_kind="SWAP",
        normalized_event_id=None,
        provider_event_id="prov_42",
    )
    assert key.normalized_event_id == "prov_42"


def test_make_dedupe_key_falls_back_when_normalized_is_empty():
    key = make_dedupe_key(
        token_mint="M",
        pair_type="PUMP_SOL",
        event_kind="SWAP",
        normalized_event_id="",
        provider_event_id="prov_42",
    )
    assert key.normalized_event_id == "prov_42"


def test_make_dedupe_key_both_ids_missing_becomes_none():
    key = make_dedupe_key(
        token_mint="M",
        pair_type="PUMP_SOL",
        event_kind="SWAP",
        normalized_event_id=None,
        provider_event_id=None,
    )
    assert key.normalized_event_id is None


def test_make_dedupe_key_rejects_non_string_pair_type():
    with pytest.raises(TypeError):
        make_dedupe_key(
            token_mint="M",
            pair_type=123,  # type: ignore[arg-type]
            event_kind="SWAP",
            normalized_event_id="evt",
        )


def test_make_dedupe_key_rejects_non_string_event_kind():
    with pytest.raises(TypeError):
        make_dedupe_key(
            token_mint="M",
            pair_type="PUMP_SOL",
            event_kind=None,  # type: ignore[arg-type]
            normalized_event_id="evt",
        )


# ---------------------------------------------------------------------------
# RunLocalDedupe behaviour
# ---------------------------------------------------------------------------


def _key(event_id: str) -> Stage27_6DedupeKey:
    return Stage27_6DedupeKey(
        token_mint="M",
        pair_type="PUMP_SOL",
        event_kind="SWAP",
        normalized_event_id=event_id,
    )


def test_empty_ledger_says_not_duplicate():
    ledger = Stage27_6RunLocalDedupe()
    assert not ledger.is_duplicate(_key("e1"))
    assert ledger.size() == 0


def test_record_reports_new_then_duplicate():
    ledger = Stage27_6RunLocalDedupe()
    assert ledger.record(_key("e1")) is True
    assert ledger.record(_key("e1")) is False
    assert ledger.size() == 1


def test_is_duplicate_after_record():
    ledger = Stage27_6RunLocalDedupe()
    ledger.record(_key("e1"))
    assert ledger.is_duplicate(_key("e1")) is True
    assert ledger.is_duplicate(_key("e2")) is False


def test_record_grows_size():
    ledger = Stage27_6RunLocalDedupe()
    ledger.record(_key("e1"))
    ledger.record(_key("e2"))
    ledger.record(_key("e3"))
    assert ledger.size() == 3


def test_snapshot_is_sorted_and_deterministic():
    a = Stage27_6RunLocalDedupe()
    a.record(_key("c"))
    a.record(_key("a"))
    a.record(_key("b"))

    b = Stage27_6RunLocalDedupe()
    b.record(_key("a"))
    b.record(_key("b"))
    b.record(_key("c"))

    assert a.snapshot() == b.snapshot()
    assert tuple(k.normalized_event_id for k in a.snapshot()) == (
        "a",
        "b",
        "c",
    )


def test_is_duplicate_rejects_non_key():
    ledger = Stage27_6RunLocalDedupe()
    with pytest.raises(TypeError):
        ledger.is_duplicate("not_a_key")  # type: ignore[arg-type]


def test_record_rejects_non_key():
    ledger = Stage27_6RunLocalDedupe()
    with pytest.raises(TypeError):
        ledger.record("not_a_key")  # type: ignore[arg-type]


def test_two_distinct_ledgers_are_isolated():
    """Stage 27.6 dedupe is RUN-LOCAL; two ledgers do not share state."""
    a = Stage27_6RunLocalDedupe()
    b = Stage27_6RunLocalDedupe()
    a.record(_key("e1"))
    assert b.size() == 0
    assert not b.is_duplicate(_key("e1"))


def test_ledger_has_no_disk_persistence_surface():
    """The dedupe class API is intentionally tiny: no disk surface."""
    ledger = Stage27_6RunLocalDedupe()
    assert not hasattr(ledger, "write_to_disk")
    assert not hasattr(ledger, "save")
    assert not hasattr(ledger, "persist")
    assert not hasattr(ledger, "flush")
    assert not hasattr(ledger, "to_file")
    assert not hasattr(ledger, "load")

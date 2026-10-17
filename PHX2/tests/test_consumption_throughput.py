"""Synchronous event-consumption throughput guards (PHX2 Step 6).

These tests pin the minimal hot-path optimization that keeps the single-thread
gRPC event-consumption path ahead of confirmed chain progress: the per-
transaction reserve / fee / migration decoders must stop re-base58-encoding the
same signatures, program keys and account keys on every PumpSwap transaction.

The optimization is output-preserving. base58 encoding of a byte string is a
bijection, so comparing a raw 32-byte program key against the decoded program-id
bytes is exactly equivalent to comparing its base58 text against the program-id
string -- only far cheaper. This file therefore asserts BOTH:

  * a bounded base58 budget per transaction shape (the throughput property that
    fails before the fix), and
  * unchanged decoder outputs / admission decisions (the safety property that
    must hold before and after).

No network, no transport, no ledger, no send. Pure in-process decoding of
locally constructed synthetic updates.
"""
from __future__ import annotations

import base64
import struct
from types import SimpleNamespace

import pytest

from PHX2.free_tier_producer import migration_admission as ma
from PHX2.free_tier_producer import pumpswap_reserves as pr
from PHX2.free_tier_producer import phx1_fee_gate as fg
from PHX2.free_tier_producer.paid_grpc_source import _base58_decode
from PHX2.free_tier_producer.pumpswap_reserves import (
    PumpSwapReserveIndex, ingest_reserve_events_from_update, decode_buy_event,
    decode_sell_event)
from PHX2.free_tier_producer.phx1_fee_gate import (
    FeeEvidenceIndex, ingest_fee_events_from_update,
    COMPUTE_BUDGET_PROGRAM_ID, JITO_TIP_ACCOUNTS)
from PHX2.free_tier_producer.migration_admission import (
    evaluate_migration_admission)
from PHX2.stage29.pumpswap_program_constants import (
    PUMPSWAP_PROGRAM_ID, PUMPSWAP_BUY_EVENT_DISCRIMINATOR_BYTES,
    PUMPSWAP_SELL_EVENT_DISCRIMINATOR_BYTES, WRAPPED_SOL_MINT)

BASE_MINT = "EkNbQMQYpd4JET5FpZrqbdkYdHXeqocZcBByJpFWpump"
TOKEN_PROGRAM = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"


def _u64(v):
    return int(v).to_bytes(8, "little", signed=False)


def _i64(v):
    return int(v).to_bytes(8, "little", signed=True)


def _buy_event(*, lp=100_000_000, protocol=100_000_000,
               creator=800_000_000, timestamp=1000):
    body = bytearray(PUMPSWAP_BUY_EVENT_DISCRIMINATOR_BYTES)
    body.extend(_i64(timestamp))
    values = [10, 20, 30, 40, 50, 60, 70, 100, lp, 100, protocol, 80, 90]
    for value in values:
        body.extend(_u64(value))
    for seed in range(8, 15):
        body.extend(bytes((seed,)) * 32)
    body.extend(_u64(100)); body.extend(_u64(creator)); body.extend(b"\x01")
    body.extend(_u64(1) + _u64(2) + _u64(3) + _i64(4) + _u64(5))
    name = b"buy"
    body.extend(len(name).to_bytes(4, "little") + name)
    body.extend(_u64(6) + _u64(7))
    return bytes(body)


class _Meta(SimpleNamespace):
    def HasField(self, name):
        return name == "compute_units_consumed"


def _swap_update(*, side="BUY", n_fillers=6, n_inner=4):
    """A representative PumpSwap swap update (no create_pool site).

    Structured so reserve, fee and migration decoders all traverse it exactly
    as they would a live pump swap: multiple account keys, top-level
    ComputeBudget + PumpSwap instructions, an inner group of token transfers,
    a program-data BuyEvent log line and pump/WSOL token balances.
    """
    jito = sorted(JITO_TIP_ACCOUNTS)[0]
    texts = [
        "Signer1111111111111111111111111111111111111",
        BASE_MINT, WRAPPED_SOL_MINT, COMPUTE_BUDGET_PROGRAM_ID,
        PUMPSWAP_PROGRAM_ID, jito, TOKEN_PROGRAM,
        "Pool11111111111111111111111111111111111111",
        "BaseVault111111111111111111111111111111111",
        "QuoteVault11111111111111111111111111111111",
    ]
    idx = {t: i for i, t in enumerate(texts)}
    # Program / mint keys must decode to their canonical 32 bytes so raw-byte
    # matching works; index-only placeholder names (Signer/Pool/*Vault) and
    # fillers get distinct raw 32-byte values.
    keys = []
    for i, t in enumerate(texts):
        kb = _base58_decode(t)
        if kb is None or len(kb) != 32:
            kb = bytes([0xB0 + (i % 60)]) + bytes([i & 0xFF]) + bytes(30)
        keys.append(kb)
    for i in range(n_fillers):
        keys.append(bytes([0xA0 + (i % 15)]) + bytes([i & 0xFF]) + bytes(30))
    cb_i, ps_i, tok_i = (idx[COMPUTE_BUDGET_PROGRAM_ID], idx[PUMPSWAP_PROGRAM_ID],
                         idx[TOKEN_PROGRAM])
    top = [
        SimpleNamespace(program_id_index=cb_i, accounts=b"",
                        data=b"\x03" + struct.pack("<Q", 1_000_000)),
        SimpleNamespace(program_id_index=ps_i, accounts=b"\x07\x08\x09",
                        data=b"\x66" * 24),
    ]
    inner = []
    for _ in range(n_inner):
        inner.append(SimpleNamespace(program_id_index=tok_i, accounts=b"\x07\x08",
                                     data=b"\x03" + b"\x00" * 8, stack_height=2))
    message = SimpleNamespace(account_keys=keys, instructions=top,
                              header=SimpleNamespace(num_required_signatures=1))
    payload = _buy_event() if side == "BUY" else None

    def _bal(address, mint, dec):
        return SimpleNamespace(account_index=idx[address], owner="Pool11111111111111111111111111111111111111",
                               mint=mint, ui_token_amount=SimpleNamespace(amount="1000", decimals=dec))
    meta = _Meta(
        loaded_writable_addresses=[], loaded_readonly_addresses=[],
        inner_instructions=[SimpleNamespace(index=1, instructions=inner)],
        pre_token_balances=[_bal("BaseVault111111111111111111111111111111111", BASE_MINT, 6),
                            _bal("QuoteVault11111111111111111111111111111111", WRAPPED_SOL_MINT, 9)],
        post_token_balances=[_bal("BaseVault111111111111111111111111111111111", BASE_MINT, 6),
                             _bal("QuoteVault11111111111111111111111111111111", WRAPPED_SOL_MINT, 9)],
        log_messages=[
            f"Program {PUMPSWAP_PROGRAM_ID} invoke [1]",
            f"Program log: Instruction: {'Buy' if side == 'BUY' else 'Sell'}",
            "Program data: " + base64.b64encode(payload).decode("ascii"),
            f"Program {PUMPSWAP_PROGRAM_ID} success",
        ],
        fee=5000, compute_units_consumed=10,
        pre_balances=[0] * len(keys),
        post_balances=[7 if i == idx[jito] else 0 for i in range(len(keys))],
    )
    info = SimpleNamespace(signature=bytes(range(1, 65)), index=0,
                           transaction=SimpleNamespace(message=message), meta=meta)
    return SimpleNamespace(transaction=SimpleNamespace(slot=433_650_000, transaction=info))


class _Counter:
    def __init__(self, target, attr):
        self.target, self.attr, self.n = target, attr, 0
        self._orig = getattr(target, attr)

    def __enter__(self):
        orig = self._orig

        def wrapper(*a, **k):
            self.n += 1
            return orig(*a, **k)
        setattr(self.target, self.attr, wrapper)
        return self

    def __exit__(self, *exc):
        setattr(self.target, self.attr, self._orig)


# ---------------------------------------------------------------------------
# RED throughput budgets (fail before the fix, pass after)
# ---------------------------------------------------------------------------
def test_fee_ingest_does_not_base58_encode_every_account_key():
    """The fee fast-path must resolve ComputeBudget / Jito accounts by raw
    bytes, not by base58-encoding the whole account-key vector each tx."""
    update = _swap_update(n_fillers=10)
    with _Counter(fg, "_base58") as c:
        assert ingest_fee_events_from_update(update, fee_index=FeeEvidenceIndex()) == 1
    # Exactly one signature encode; never one-per-account-key.
    assert c.n == 1, f"fee path base58-encoded {c.n} values (expected 1 signature)"


def test_migration_eval_does_not_base58_program_keys_for_non_create_pool():
    """A swap carries no create_pool discriminator, so admission must scan
    instruction data first and never base58-resolve any program key (nor the
    signature, which is only needed once a site is found)."""
    update = _swap_update(n_inner=8)
    with _Counter(ma, "_b58encode_any") as c:
        assert evaluate_migration_admission(update) is None
    assert c.n == 0, f"admission base58-encoded {c.n} values on a non-create_pool tx"


def test_reserve_identities_do_not_base58_program_keys():
    """PumpSwap instruction-site identity binding must match program keys by
    raw bytes, so it never routes through the migration base58 resolver."""
    update = _swap_update(n_inner=6)
    with _Counter(ma, "_b58encode_any") as c:
        ingest_reserve_events_from_update(update, reserve_index=PumpSwapReserveIndex())
    assert c.n == 0, f"reserve identity binding base58-encoded {c.n} program keys"


def test_event_decoder_skips_discarded_pubkeys():
    """decode_buy_event keeps only the pool pubkey; the six discarded pubkeys
    must be advanced without base58-encoding a value that is thrown away."""
    payload = _buy_event()
    with _Counter(pr, "_base58_encode") as c:
        decode_buy_event(payload, base_mint=BASE_MINT, quote_mint=WRAPPED_SOL_MINT)
    assert c.n == 1, f"buy-event decode base58-encoded {c.n} pubkeys (expected 1 pool)"


def test_sell_event_decoder_skips_discarded_pubkeys():
    # SellEvent layout: disc + i64 ts + 13 u64 + pool pubkey + 6 discarded
    # pubkeys + 4 u64 (creator bps/fee, cashback bps/fee) + empty (legacy) tail.
    sell = bytearray(PUMPSWAP_SELL_EVENT_DISCRIMINATOR_BYTES)
    sell.extend(_i64(1000))
    for value in [10, 20, 30, 40, 50, 60, 70, 100, 100_000_000, 100, 100_000_000, 80, 90]:
        sell.extend(_u64(value))
    for seed in range(8, 15):  # 1 pool + 6 discarded pubkeys
        sell.extend(bytes((seed,)) * 32)
    sell.extend(_u64(100) + _u64(800_000_000) + _u64(1) + _u64(2))
    with _Counter(pr, "_base58_encode") as c:
        art = decode_sell_event(bytes(sell), base_mint=BASE_MINT, quote_mint=WRAPPED_SOL_MINT)
    assert art.event_side == "SELL"
    assert c.n == 1, f"sell-event decode base58-encoded {c.n} pubkeys (expected 1 pool)"


def test_total_base58_budget_per_swap_is_bounded():
    """Whole per-transaction budget across reserve + fee + migration for one
    representative pump swap must be small and independent of key count."""
    update = _swap_update(n_fillers=12, n_inner=8)
    total = 0
    for tgt, attr in ((ma, "_b58encode_any"), (fg, "_base58"),
                      (pr, "_base58_encode"), (pr, "_base58_encode_bytes")):
        with _Counter(tgt, attr) as c:
            ingest_reserve_events_from_update(update, reserve_index=PumpSwapReserveIndex())
            ingest_fee_events_from_update(update, fee_index=FeeEvidenceIndex())
            evaluate_migration_admission(update)
        total += c.n
    # Pre-fix this is ~50+ and scales with account/instruction count; the fix
    # bounds it to a small constant (signatures + the two kept pool pubkeys).
    assert total <= 8, f"per-swap base58 budget was {total} (expected <= 8)"


def test_base58_budget_does_not_scale_with_account_key_count():
    """Adding filler account keys must not increase the base58 budget."""
    def budget(n_fillers):
        update = _swap_update(n_fillers=n_fillers, n_inner=4)
        total = 0
        for tgt, attr in ((ma, "_b58encode_any"), (fg, "_base58"),
                          (pr, "_base58_encode"), (pr, "_base58_encode_bytes")):
            with _Counter(tgt, attr) as c:
                ingest_reserve_events_from_update(update, reserve_index=PumpSwapReserveIndex())
                ingest_fee_events_from_update(update, fee_index=FeeEvidenceIndex())
                evaluate_migration_admission(update)
            total += c.n
        return total
    assert budget(4) == budget(24), "base58 budget scales with account-key count"


# ---------------------------------------------------------------------------
# Equivalence / safety (must hold before and after the fix)
# ---------------------------------------------------------------------------
def test_reserve_output_unchanged_for_representative_buy():
    update = _swap_update()
    index = PumpSwapReserveIndex()
    assert ingest_reserve_events_from_update(update, reserve_index=index) == 1
    art = index.latest(BASE_MINT)
    assert art is not None
    assert art.event_side == "BUY"
    assert art.raw_quote_reserves == 60
    assert art.base_reserves == 50
    assert art.pool_address is not None


def test_fee_output_unchanged_for_representative_buy():
    update = _swap_update()
    index = FeeEvidenceIndex()
    assert ingest_fee_events_from_update(update, fee_index=index) == 1
    snap = index.snapshot(BASE_MINT, now_epoch=1000)
    assert snap.event_count == 1
    assert snap.transaction_count == 1
    assert snap.lp_fees == "0.1"
    assert snap.protocol_fees == "0.1"
    assert snap.priority_fees == "0.00000001"
    assert snap.jito_tips == "0.000000007"


def test_fee_dedupe_unchanged():
    update = _swap_update()
    index = FeeEvidenceIndex()
    assert ingest_fee_events_from_update(update, fee_index=index) == 1
    assert ingest_fee_events_from_update(update, fee_index=index) == 0


def test_non_pump_swap_produces_no_reserve_or_fee_events():
    """A swap whose base mint is not a pump mint must still fail closed."""
    update = _swap_update()
    for bal in (update.transaction.transaction.meta.pre_token_balances
                + update.transaction.transaction.meta.post_token_balances):
        if bal.mint == BASE_MINT:
            bal.mint = "So11111111111111111111111111111111111111112"
    assert ingest_reserve_events_from_update(update, reserve_index=PumpSwapReserveIndex()) == 0
    assert ingest_fee_events_from_update(update, fee_index=FeeEvidenceIndex()) == 0


def test_admission_none_for_swap_is_stable():
    """A pump swap is not a pool creation: admission returns None (not a
    rejection decision), exactly as before."""
    assert evaluate_migration_admission(_swap_update()) is None


def test_decoder_fails_closed_on_truncated_event():
    from PHX2.free_tier_producer.pumpswap_reserves import PumpSwapReserveError
    with pytest.raises(PumpSwapReserveError):
        decode_buy_event(bytes(PUMPSWAP_BUY_EVENT_DISCRIMINATOR_BYTES) + b"\x00" * 4,
                         base_mint=BASE_MINT, quote_mint=WRAPPED_SOL_MINT)


def test_program_match_helper_equivalent_to_base58_across_edge_cases():
    """The raw-byte program matcher must agree with base58-string comparison on
    valid keys, out-of-range indices, and wrong-length keys."""
    match = ma._program_key_matches  # added by the fix
    keys = [_base58_decode(PUMPSWAP_PROGRAM_ID), b"\x00" * 32, b"short", bytes(range(32))]
    target = ma.PUMPSWAP_PROGRAM_ID_BYTES
    for i in range(-2, len(keys) + 2):
        raw = match(keys, i, target)
        ref = (isinstance(i, int) and 0 <= i < len(keys)
               and ma._b58encode_any(keys[i]) == PUMPSWAP_PROGRAM_ID)
        assert raw == ref, (i, raw, ref)


def test_this_module_uses_no_send_transport_or_ledger():
    """Meta-guard: the consumption path exercised here is pure decoding."""
    import PHX2.free_tier_producer.pumpswap_reserves as m1
    import PHX2.free_tier_producer.phx1_fee_gate as m2
    import PHX2.free_tier_producer.migration_admission as m3
    for mod in (m1, m2, m3):
        src = mod.__dict__
        assert "requests" not in src and "socket" not in src

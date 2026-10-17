from __future__ import annotations

import base64
import struct
from types import SimpleNamespace

from PHX2.free_tier_producer.paid_grpc_source import _base58_decode
from PHX2.free_tier_producer.phx1_fee_gate import (
    COMPUTE_BUDGET_PROGRAM_ID,
    JITO_TIP_ACCOUNTS,
    PHX1_FEE_GATE_SCAM_LIKELY,
    FeeEvidenceIndex,
    ingest_fee_events_from_update,
)
from PHX2.stage29.pumpswap_program_constants import (
    PUMPSWAP_BUY_EVENT_DISCRIMINATOR_BYTES,
    WRAPPED_SOL_MINT,
)


MINT = "EkNbQMQYpd4JET5FpZrqbdkYdHXeqocZcBByJpFWpump"


def _u64(value):
    return int(value).to_bytes(8, "little", signed=False)


def _i64(value):
    return int(value).to_bytes(8, "little", signed=True)


def _buy_event(*, lp=100_000_000, protocol=100_000_000,
               creator=800_000_000, timestamp=1000):
    body = bytearray(PUMPSWAP_BUY_EVENT_DISCRIMINATOR_BYTES)
    body.extend(_i64(timestamp))
    # base/max/user reserves/pool reserves/quote/lp bps/lp/protocol bps/
    # protocol/quote with LP/user quote
    values = [10, 20, 30, 40, 50, 60, 70, 100, lp, 100, protocol, 80, 90]
    for value in values:
        body.extend(_u64(value))
    for seed in range(8, 15):
        body.extend(bytes((seed,)) * 32)
    body.extend(_u64(100))
    body.extend(_u64(creator))
    body.extend(b"\x01")
    body.extend(_u64(1) + _u64(2) + _u64(3) + _i64(4) + _u64(5))
    name = b"buy"
    body.extend(len(name).to_bytes(4, "little") + name)
    body.extend(_u64(6) + _u64(7))
    return bytes(body)


class _Meta(SimpleNamespace):
    def HasField(self, name):
        return name == "compute_units_consumed"


def _update(*payloads):
    jito = sorted(JITO_TIP_ACCOUNTS)[0]
    key_text = [MINT, WRAPPED_SOL_MINT, COMPUTE_BUDGET_PROGRAM_ID, jito]
    instruction = SimpleNamespace(
        program_id_index=2, accounts=b"", data=b"\x03" + struct.pack("<Q", 1_000_000))
    message = SimpleNamespace(
        account_keys=[_base58_decode(value) for value in key_text],
        instructions=[instruction])
    meta = _Meta(
        pre_token_balances=[SimpleNamespace(mint=MINT), SimpleNamespace(mint=WRAPPED_SOL_MINT)],
        post_token_balances=[SimpleNamespace(mint=MINT), SimpleNamespace(mint=WRAPPED_SOL_MINT)],
        loaded_writable_addresses=[], loaded_readonly_addresses=[],
        log_messages=["Program data: " + base64.b64encode(payload).decode("ascii")
                      for payload in payloads],
        fee=5_000, compute_units_consumed=10,
        pre_balances=[0, 0, 0, 100], post_balances=[0, 0, 0, 107],
    )
    info = SimpleNamespace(
        signature=bytes(range(1, 65)),
        transaction=SimpleNamespace(message=message), meta=meta)
    return SimpleNamespace(transaction=SimpleNamespace(transaction=info))


def test_primary_swap_update_accumulates_phx1_amm_priority_and_jito_fees_once_per_tx():
    index = FeeEvidenceIndex()
    payload = _buy_event()
    assert ingest_fee_events_from_update(_update(payload, payload), fee_index=index) == 2
    snapshot = index.snapshot(MINT, now_epoch=1000)
    assert snapshot.event_count == 2
    assert snapshot.transaction_count == 1
    assert snapshot.lp_fees == "0.2"
    assert snapshot.protocol_fees == "0.2"
    assert snapshot.creator_fees == "1.6"
    # 10 priority lamports + 7 Jito-tip lamports, never double-counted for
    # multiple PumpSwap events in the same transaction.
    assert snapshot.priority_fees == "0.00000001"
    assert snapshot.jito_tips == "0.000000007"
    assert snapshot.fee_gate_label == PHX1_FEE_GATE_SCAM_LIKELY
    assert snapshot.hard_block


def test_primary_fee_ingestion_is_signature_event_deduped():
    index = FeeEvidenceIndex()
    update = _update(_buy_event())
    assert ingest_fee_events_from_update(update, fee_index=index) == 1
    assert ingest_fee_events_from_update(update, fee_index=index) == 0
    assert index.snapshot(MINT, now_epoch=1000).event_count == 1

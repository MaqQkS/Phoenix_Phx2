from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from PHX2.dashboard.adapter import build_candidate_rows, load_producer
from PHX2.free_tier_producer.ath_state import (
    CentralAthStateStore,
    SOURCE_PAID_OHLCV,
    SOURCE_PUMPSWAP_EVENT,
)
from PHX2.free_tier_producer.free_tier_pricing_tail import FreeTierPricingTail
from PHX2.free_tier_producer import free_tier_session as producer_session
from PHX2.free_tier_producer.pumpswap_reserves import (
    BUY_LAYOUT_VIRTUAL,
    PumpSwapReserveArtifact,
    PumpSwapReserveError,
    RESERVE_SOURCE_BUY_EVENT,
)
from PHX2.paper_trading.pricing import normalize_record


MINT = "EkNbQMQYpd4JET5FpZrqbdkYdHXeqocZcBByJpFWpump"
POOL = "ExVW9Wxpr4TnMchukxGwMYM4XYTr3yTKwpqDE35E9seW"
QUOTE = "So11111111111111111111111111111111111111112"


def _event(
    effective_quote: int,
    *,
    timestamp: int,
    raw_quote: int | None = None,
    virtual_quote: int = 0,
    supply_raw: int = 1_000_000_000_000_000,
) -> PumpSwapReserveArtifact:
    raw = effective_quote - virtual_quote if raw_quote is None else raw_quote
    return PumpSwapReserveArtifact(
        raw_quote_reserves=raw,
        virtual_quote_reserves=virtual_quote,
        effective_quote_reserves=effective_quote,
        base_reserves=1_000_000_000_000,
        reserve_source=RESERVE_SOURCE_BUY_EVENT,
        observation_timestamp=datetime.fromtimestamp(
            timestamp, timezone.utc).isoformat().replace("+00:00", "Z"),
        decoder_layout_version=BUY_LAYOUT_VIRTUAL,
        pool_address=POOL,
        base_mint=MINT,
        quote_mint=QUOTE,
        base_decimals=6,
        quote_decimals=9,
        event_side="BUY",
        event_timestamp=timestamp,
        base_supply=supply_raw,
    )


def _store(path: Path | None = None) -> CentralAthStateStore:
    store = CentralAthStateStore(path)
    assert store.register_pool(
        mint=MINT, pool_address=POOL, quote_mint=QUOTE,
        creation_timestamp="1970-01-01T00:16:40Z")
    assert store.observe_quote_price(QUOTE, "1", observed_at=1000)
    return store


def test_whale_spike_survives_polling_lower_sell_and_duplicate_delivery(tmp_path):
    store = _store(tmp_path)
    assert store.observe_event(
        mint=MINT, artifact=_event(75_000_000_000, timestamp=1000),
        transaction_signature="tx-a", event_index=0)
    # Two valid events in one transaction; the whale event is event index 1.
    assert store.observe_event(
        mint=MINT, artifact=_event(
            95_000_000_000, timestamp=1001,
            raw_quote=90_000_000_000, virtual_quote=5_000_000_000),
        transaction_signature="tx-whale", event_index=1)
    assert store.observe_event(
        mint=MINT, artifact=_event(90_000_000_000, timestamp=1001),
        transaction_signature="tx-whale", event_index=2)
    # Duplicate gRPC delivery and an out-of-order lower sell cannot alter ATH.
    assert not store.observe_event(
        mint=MINT, artifact=_event(95_000_000_000, timestamp=1001),
        transaction_signature="tx-whale", event_index=1)
    assert store.observe_event(
        mint=MINT, artifact=_event(75_000_000_000, timestamp=1002),
        transaction_signature="tx-sell", event_index=0)
    assert not store.observe_provider_current(
        mint=MINT, price_usd="0.000075", market_cap_usd="75000",
        observed_at=1003)

    snap = store.snapshot(MINT)
    assert snap["ath_price"] == "0.000095"
    assert snap["ath_market_cap"] == "95000.000000"
    assert snap["ath_provider"] == SOURCE_PUMPSWAP_EVENT
    assert snap["ath_transaction_signature"] == "tx-whale"
    assert snap["ath_event_index"] == 1
    assert snap["ath_supply_at_observation"] == "1000000000"
    assert snap["ath_raw_quote_reserves"] == "90000000000"
    assert snap["ath_virtual_quote_reserves"] == "5000000000"
    assert snap["ath_effective_quote_reserves"] == "95000000000"
    assert store.stats()["ath_event_dedupe_keys"] == 4


def test_birdeye_lower_cannot_reduce_event_but_later_higher_upgrades_with_recorded_supply():
    store = _store()
    store.observe_event(
        mint=MINT, artifact=_event(95_000_000_000, timestamp=1000),
        transaction_signature="tx-whale", event_index=0)
    assert not store.observe_ohlcv_high(
        mint=MINT, high_price_usd="0.00009", candle_timestamp=1000,
        history_complete=True, interval="1m", time_from_unix=1000,
        time_to_unix=1059)
    assert store.snapshot(MINT)["ath_market_cap"] == "95000.000000"
    assert store.observe_ohlcv_high(
        mint=MINT, high_price_usd="0.0001", candle_timestamp=1001,
        history_complete=True, interval="1m", time_from_unix=1000,
        time_to_unix=1061)
    snap = store.snapshot(MINT)
    assert snap["ath_price"] == "0.0001"
    assert snap["ath_market_cap"] == "100000.0000"
    assert snap["ath_provider"] == SOURCE_PAID_OHLCV
    assert snap["ath_supply_at_observation"] == "1000000000"


def test_pending_event_pricing_preserves_separate_price_and_market_cap_maxima():
    store = CentralAthStateStore()
    store.register_pool(
        mint=MINT, pool_address=POOL, quote_mint=QUOTE,
        creation_timestamp="1970-01-01T00:16:40Z")
    # Higher price but only 500M supply => 50k market cap.
    store.observe_event(
        mint=MINT, artifact=_event(
            100_000_000_000, timestamp=1000,
            supply_raw=500_000_000_000_000),
        transaction_signature="tx-price", event_index=0)
    # Lower price but 1B supply => 90k market cap.
    store.observe_event(
        mint=MINT, artifact=_event(90_000_000_000, timestamp=1001),
        transaction_signature="tx-mc", event_index=0)
    assert store.stats()["ath_pending_events"] == 2
    store.observe_quote_price(QUOTE, "1", observed_at=1002)
    snap = store.snapshot(MINT)
    assert snap["ath_price"] == "0.0001"
    assert snap["ath_market_cap"] == "90000.00000"
    assert snap["price_provenance"]["transaction_signature"] == "tx-price"
    assert snap["market_cap_provenance"]["transaction_signature"] == "tx-mc"


def test_atomic_restart_and_interrupted_temp_file_restore_maximum(tmp_path):
    store = _store(tmp_path)
    store.observe_event(
        mint=MINT, artifact=_event(95_000_000_000, timestamp=1001),
        transaction_signature="tx-whale", event_index=0)
    state_path = tmp_path / "ath_state.json"
    assert state_path.is_file()
    checkpoint_path = tmp_path / "ath_state_checkpoint.json"
    assert checkpoint_path.is_file()
    public = json.loads(state_path.read_text(encoding="utf-8"))
    checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    assert public["artifact_kind"] == "CENTRAL_ATH_PUBLIC_STATE"
    assert checkpoint["artifact_kind"] == "CENTRAL_ATH_RESTART_CHECKPOINT"
    assert "seen_event_keys" not in public["mints"][MINT]
    assert "supply_observations" not in public["mints"][MINT]
    assert "price_provenance" not in public["mints"][MINT]
    assert "market_cap_provenance" not in public["mints"][MINT]
    # PHX2-E2E-005: the restart checkpoint is the authenticated envelope; the
    # full per-mint provenance (incl. the durable event dedupe keys) lives in
    # its digest-bound records.
    assert checkpoint["checkpoint_kind"] == "PHX2_CENTRAL_ATH_CHECKPOINT"
    (mint_record,) = [record for record in checkpoint["payload"]["records"]
                      if record["token_mint"] == MINT]
    assert mint_record["seen_event_keys"]
    assert producer_session.artifacts.scan_value_safe(
        state_path.read_text(encoding="utf-8"))
    # Simulate interruption before atomic replace: a corrupt temp cannot damage
    # the last fsynced main artifact.
    state_path.with_name("ath_state.json.tmp").write_text("{partial", encoding="utf-8")
    restored = CentralAthStateStore(tmp_path)
    restored.observe_provider_current(
        mint=MINT, price_usd="0.000075", market_cap_usd="75000",
        observed_at=1002)
    snap = restored.snapshot(MINT)
    assert snap["ath_market_cap"] == "95000.000000"
    assert snap["ath_transaction_signature"] == "tx-whale"
    assert not restored.observe_event(
        mint=MINT, artifact=_event(95_000_000_000, timestamp=1001),
        transaction_signature="tx-whale", event_index=0)
    # A syntactically valid but wrong-schema checkpoint must not suppress the
    # valid compact public fallback.
    checkpoint_path.write_text("{}\n", encoding="utf-8")
    public_fallback = CentralAthStateStore(tmp_path)
    assert public_fallback.snapshot(MINT)["ath_market_cap"] == "95000.000000"


def test_paper_pricing_tail_and_dashboard_read_same_central_artifact(tmp_path, monkeypatch):
    # All evidence was learned by this observation; keep event and ingestion
    # clocks aligned instead of overlaying a present-day ATH onto 1970.
    monkeypatch.setattr("PHX2.free_tier_producer.ath_state._now_iso",
                        lambda: "1970-01-01T00:16:41Z")
    producer = tmp_path / "producer"
    producer.mkdir()
    store = _store(producer)
    store.observe_event(
        mint=MINT, artifact=_event(95_000_000_000, timestamp=1001),
        transaction_signature="tx-whale", event_index=0,
        last_updated_at="1970-01-01T00:16:41Z")

    tail = FreeTierPricingTail(
        out_dir=producer,
        fetch_market_fn=lambda _mint: {
            "current_price": "0.000075",
            "current_market_cap_usd": "75000",
            "liquidity_usd": "10000",
            "fetched_at_utc": "1970-01-01T00:16:42Z",
        },
        now_epoch_fn=lambda: 1002.0,
        min_poll_interval_seconds=0,
        ath_store=store,
    )
    assert tail.track(MINT)
    assert tail.poll("1970-01-01T00:16:42Z") == 1
    record = json.loads((producer / "pricing_tail.jsonl").read_text(
        encoding="utf-8").splitlines()[-1])
    paper = normalize_record(record)
    assert paper is not None
    assert paper.ath_market_cap_usd == pytest.approx(95_000)
    assert paper.extra["central_ath"]["ath_transaction_signature"] == "tx-whale"

    (producer / "watch_state.jsonl").write_text(json.dumps({
        "candidate_id": "cand-1", "token_mint": MINT, "status": "WATCHING",
        "seeded_at_utc": "1970-01-01T00:16:40Z",
        "last_observed_at_utc": "1970-01-01T00:16:42Z",
    }) + "\n", encoding="utf-8")
    loaded = load_producer(producer, datetime.fromtimestamp(1002, timezone.utc))
    rows = build_candidate_rows(loaded, datetime.fromtimestamp(1002, timezone.utc))
    assert len(rows) == 1
    assert rows[0]["athMarketCapUsd"] == "95000.000000"
    assert rows[0]["ath"] == "$95.0K"
    assert rows[0]["athProvider"] == SOURCE_PUMPSWAP_EVENT


def test_malformed_mismatch_and_impossible_reserves_fail_closed():
    unregistered = CentralAthStateStore()
    assert not unregistered.observe_event(
        mint=MINT, artifact=_event(95_000_000_000, timestamp=1001),
        transaction_signature="tx-unregistered", event_index=0)
    store = _store()
    mismatched = _event(95_000_000_000, timestamp=1001)
    mismatched = mismatched.__class__(
        **{**mismatched.__dict__, "base_mint": "A" * 40 + "pump"})
    assert not store.observe_event(
        mint=MINT, artifact=mismatched,
        transaction_signature="tx-bad", event_index=0)
    with pytest.raises(PumpSwapReserveError):
        _event(0, timestamp=1001)

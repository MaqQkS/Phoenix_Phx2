import copy
import json
from types import SimpleNamespace

import pytest

from PHX2.paper_trading.models import parse_utc
from PHX2.paper_trading.pricing import normalize_record, TailingSnapshotSource, _overlay_central_ath
from PHX2.free_tier_producer.free_tier_pricing_tail import FreeTierPricingTail
from PHX2.free_tier_producer.market_scheduler import MarketScheduler, CandidateScheduleView

NOW = "2026-10-17T00:00:00Z"
EPOCH = parse_utc(NOW)
MINT = "2TQJeFeMD2YfAroNGPBpQxsZTxW1gGqPNPvYde65PUMP"


def record(kind="BUILD30_CANDIDATE_RECHECK"):
    return {"kind": kind, "token_mint": MINT, "candidate_id": "candidate",
        "observed_at_utc": NOW, "current_price": "1", "current_market_cap_usd": "10000",
        "liquidity_usd": "12000", "price_observed_at_utc": NOW,
        "market_cap_observed_at_utc": NOW, "liquidity_observed_at_utc": NOW,
        "market_state": "MARKET_READY", "price_fresh": True,
        "risk_label": "RISK_LOW", "risk_assessed_at_utc": NOW,
        "scam_policy": {"verdict": "ALLOW"}, "security_assessed_at_utc": NOW,
        "activation": {"activation_state": "ACTIVE_DIP_WATCH", "activation_proven": True,
            "activation_proof_valid": True, "token_mint": MINT, "candidate_id": "candidate",
            "activation_observation_fresh": True, "activation_latched": True,
            "activated_at_utc": "2026-10-16T23:55:00Z"},
        "pricing_coverage": {"admitted": True, "paper_feedback_ready": True,
            "lease_until_utc": "2026-10-17T00:10:00Z"}}


def test_candidate_and_tail_have_identical_exposure_contract():
    candidate, tail = (normalize_record(record(kind)) for kind in (
        "BUILD30_CANDIDATE_RECHECK", "FREE_TIER_PRICING_TAIL"))
    assert candidate.extra == tail.extra
    assert candidate.extra["exposure_eligible"]


def test_canonical_recent_volume_has_exact_identity_and_missing_is_unknown():
    row = record("FREE_TIER_PRICING_TAIL")
    row["canonical_volume_5m"] = {"schema_version": "phx2_canonical_swap_volume_v1",
        "status": "VALID", "mint": MINT, "window_seconds": 300,
        "sample_count": 4, "gross_volume_usd": "1234.50"}
    assert normalize_record(row).volume_usd == 1234.5
    row["canonical_volume_5m"]["mint"] = "different"
    assert normalize_record(row).volume_usd is None
    row["canonical_volume_5m"]["mint"] = MINT
    row["canonical_volume_5m"]["status"] = "INSUFFICIENT_DATA"
    assert normalize_record(row).volume_usd is None


@pytest.mark.parametrize("key", ["activation", "risk_assessed_at_utc", "scam_policy",
    "security_assessed_at_utc", "pricing_coverage", "price_observed_at_utc"])
def test_missing_context_cannot_create_exposure(key):
    row = record("FREE_TIER_PRICING_TAIL")
    del row[key]
    assert not normalize_record(row).extra["exposure_eligible"]


@pytest.mark.parametrize("field,value", [("activation_proof_valid", False),
    ("activation_proof_valid", None), ("token_mint", "wrong"), ("candidate_id", "wrong")])
def test_unbound_or_invalid_activation_never_adds_exposure(field, value):
    row = record()
    row["activation"][field] = value
    assert not normalize_record(row).extra["exposure_eligible"]


@pytest.mark.parametrize("timestamp", ["2026-10-16T23:00:00Z", "2026-10-17T00:00:01Z"])
def test_record_write_time_cannot_refresh_stale_or_future_quote(timestamp):
    row = record()
    row["price_observed_at_utc"] = timestamp
    snapshot = normalize_record(row)
    assert snapshot.price_usd == 1  # retained for diagnostics only
    assert not snapshot.extra["quote_usable"]
    assert not snapshot.extra["exposure_eligible"]


def test_future_ath_and_activation_cannot_leak_into_history():
    row = record()
    row["central_ath"] = {"ath_market_cap": "999999", "ath_timestamp": NOW,
                           "ath_ingested_at_utc": "2026-10-17T01:00:00Z"}
    row["activation"]["activated_at_utc"] = "2026-10-17T01:00:00Z"
    snap = normalize_record(row)
    assert snap.ath_market_cap_usd is None and not snap.extra["activation_eligible"]
    assert _overlay_central_ath(snap, {MINT: row["central_ath"]}).ath_market_cap_usd is None


def test_fresh_price_with_stale_overview_can_exit_but_cannot_add_exposure():
    row = record()
    row["market_state"] = "MARKET_INCOMPLETE"
    row["liquidity_observed_at_utc"] = "2026-10-16T23:00:00Z"
    snap = normalize_record(row)
    assert snap.extra["quote_usable"] and not snap.extra["exposure_eligible"]


def test_row_local_ath_wins_over_later_sibling_state():
    row = record()
    row["central_ath"] = {"ath_market_cap": "20000", "ath_timestamp": NOW}
    snap = normalize_record(row)
    _overlay_central_ath(snap, {MINT: {"ath_market_cap": "40000", "ath_timestamp": NOW,
                                     "ath_ingested_at_utc": NOW}})
    assert snap.ath_market_cap_usd == 20000


def test_source_checkpoints_identity_and_rejects_truncation(tmp_path):
    path = tmp_path / "pricing_tail.jsonl"
    path.write_text(json.dumps(record("FREE_TIER_PRICING_TAIL")) + "\n", encoding="utf-8")
    source = TailingSnapshotSource([tmp_path], producer_streams_only=True)
    snapshots, errors = source.poll()
    assert len(snapshots) == 1 and not errors
    resumed = TailingSnapshotSource([tmp_path], producer_streams_only=True)
    resumed.restore_checkpoint(source.checkpoint_state())
    assert resumed.poll()[0] == []
    path.write_text("\n", encoding="utf-8")
    with pytest.raises(ValueError, match="REPLACED_OR_TRUNCATED"):
        resumed.poll()


def test_production_source_excludes_non_candidate_artifacts_and_partial_lines(tmp_path):
    path = tmp_path / "pricing_tail.jsonl"
    body = json.dumps(record("FREE_TIER_PRICING_TAIL"))
    path.write_text(body[:100], encoding="utf-8")
    (tmp_path / "secrets.jsonl").write_text(body + "\n", encoding="utf-8")
    source = TailingSnapshotSource([tmp_path], producer_streams_only=True)
    assert source.poll() == ([], []) and source.offsets == {}
    path.write_text(body + "\n", encoding="utf-8")
    assert len(source.poll()[0]) == 1


def test_poll_has_aggregate_byte_bound_and_resumes_fairly(tmp_path, monkeypatch):
    candidates = tmp_path / "candidates"
    candidates.mkdir()
    line = (json.dumps(record()) + "\n").encode()
    paths = [candidates / f"{index:03}.jsonl" for index in range(8)]
    for path in paths:
        path.write_bytes(line * 5)
    monkeypatch.setattr(TailingSnapshotSource, "MAX_POLL_BYTES", len(line) * 2 + 10)
    monkeypatch.setattr(TailingSnapshotSource, "MAX_POLL_FILES", 2)
    source = TailingSnapshotSource([tmp_path], producer_streams_only=True)
    seen = 0
    for turn in range(24):
        before = sum(source.offsets.values())
        snapshots, errors = source.poll()
        assert not errors and len(snapshots) <= 2
        assert sum(source.offsets.values()) - before <= source.MAX_POLL_BYTES
        seen += len(snapshots)
        if turn == 3:
            checkpoint = source.checkpoint_state()
            source = TailingSnapshotSource([tmp_path], producer_streams_only=True)
            source.restore_checkpoint(checkpoint)
        if turn == 7:
            assert len(source.offsets) == 8  # no hot-file starvation after restart
    assert seen == 40 and all(offset == len(line) * 5 for offset in source.offsets.values())
    assert source.poll() == ([], [])


def test_poll_caps_complete_records_and_file_count(tmp_path, monkeypatch):
    candidates = tmp_path / "candidates"
    candidates.mkdir()
    line = json.dumps(record()) + "\n"
    for index in range(3):
        (candidates / f"{index}.jsonl").write_bytes((line * 5).encode())
    monkeypatch.setattr(TailingSnapshotSource, "MAX_POLL_RECORDS", 2)
    source = TailingSnapshotSource([tmp_path], producer_streams_only=True)
    assert len(source.poll()[0]) == 2
    assert sum(source.offsets.values()) == 2 * len(line.encode())
    monkeypatch.setattr(TailingSnapshotSource, "MAX_INPUT_FILES", 2)
    with pytest.raises(ValueError, match="INPUT_FILE_LIMIT_EXCEEDED"):
        source.poll()


def test_residual_byte_budget_defers_a_complete_valid_line(tmp_path, monkeypatch):
    candidates = tmp_path / "candidates"
    candidates.mkdir()
    first, second = candidates / "a.jsonl", candidates / "b.jsonl"
    line = (json.dumps(record()) + "\n").encode()
    first.write_bytes(line)
    second.write_bytes(line)
    monkeypatch.setattr(TailingSnapshotSource, "MAX_POLL_BYTES", len(line) + 10)
    source = TailingSnapshotSource([tmp_path], producer_streams_only=True)
    snapshots, errors = source.poll()
    assert not errors and len(snapshots) == 1
    assert str(second.resolve()) not in source.offsets
    snapshots, errors = source.poll()
    assert not errors and len(snapshots) == 1
    assert source.offsets[str(second.resolve())] == len(line)
    assert source.poll() == ([], [])


@pytest.mark.parametrize("file_count,backlog,file_limit", [(70, 0, 64), (12, 20, 3)])
def test_fresh_tail_is_serviced_each_poll_despite_candidate_backlog(
        tmp_path, monkeypatch, file_count, backlog, file_limit):
    candidates = tmp_path / "candidates"
    candidates.mkdir()
    line = (json.dumps(record()) + "\n").encode()
    for index in range(file_count):
        (candidates / f"{index:03}.jsonl").write_bytes(line * backlog)
    tail = tmp_path / "pricing_tail.jsonl"
    tail.write_bytes(b"")
    monkeypatch.setattr(TailingSnapshotSource, "MAX_POLL_FILES", file_limit)
    monkeypatch.setattr(TailingSnapshotSource, "MAX_POLL_RECORDS", 4)
    source = TailingSnapshotSource([tmp_path], producer_streams_only=True)
    for turn in range(6):
        row = record("FREE_TIER_PRICING_TAIL")
        row["candidate_id"] = f"fresh-tail-{turn}"
        with tail.open("ab") as handle:
            handle.write((json.dumps(row) + "\n").encode())
        snapshots, errors = source.poll()
        assert not errors and len(snapshots) <= 4
        fresh = [snapshot for snapshot in snapshots if snapshot.source_kind == "FREE_TIER_PRICING_TAIL"]
        assert len(fresh) == 1 and fresh[0].candidate_id == f"fresh-tail-{turn}"
        assert source.offsets[str(tail.resolve())] == tail.stat().st_size
    if backlog:
        assert len(source.offsets) == 7  # tail service does not starve candidate rotation


def test_tail_reclaims_unavailable_capacity_and_reports_rejection(tmp_path):
    clock = [EPOCH]
    tail = FreeTierPricingTail(out_dir=tmp_path, fetch_market_fn=lambda _: None,
        now_epoch_fn=lambda: clock[0], max_tracked=1, unavailable_retention_seconds=30)
    assert tail.track("A") and not tail.track("B")
    assert tail.poll(NOW) == 1  # explicit unavailable row, never a fabricated mark
    assert tail.market_freshness()["market_unavailable_count"] == 1
    clock[0] += 31
    assert tail.track("B") and tail.tracked_mints() == ("B",)
    assert tail.summary()["admission_failures"] == 1


def test_open_paper_pin_survives_age_and_missing_feedback(tmp_path):
    clock = [EPOCH]
    state = tmp_path / "paper_state.json"
    state.write_text(json.dumps({"open_mints": [{"mint": MINT, "candidate_id": "c"}],
                                "heartbeat_utc": NOW}))
    tail = FreeTierPricingTail(out_dir=tmp_path / "producer", fetch_market_fn=lambda _: {},
        now_epoch_fn=lambda: clock[0], max_tracked=1, max_tail_age_seconds=10,
        paper_state_file=state)
    tail.sync_paper_positions()
    assert tail.coverage(MINT)["paper_feedback_ready"]
    clock[0] += 600
    tail.poll("2026-10-17T00:10:00Z")
    assert MINT in tail.tracked_mints()
    assert not tail.coverage(MINT)["paper_feedback_ready"]
    assert not tail.track("B")


def test_stale_cached_tail_value_never_reports_fresh(tmp_path):
    market = record()
    market["price_observed_at_utc"] = "2026-10-16T20:00:00Z"
    tail = FreeTierPricingTail(out_dir=tmp_path, fetch_market_fn=lambda _: market,
        now_epoch_fn=lambda: EPOCH)
    tail.track(MINT)
    tail.poll(NOW)
    assert tail.market_freshness()["market_data_fresh_count"] == 0
    assert tail.market_freshness()["market_unavailable_count"] == 1


def test_tail_stamps_after_context_and_restores_stale_open_pins(tmp_path):
    clock = [EPOCH]
    state = tmp_path / "paper_state.json"
    state.write_text(json.dumps({"open_mints": [{"mint": MINT, "candidate_id": "c"}],
                                "heartbeat_utc": "2026-10-16T23:00:00Z"}))
    def fetch(_):
        clock[0] += 2
        row = record()
        row["price_observed_at_utc"] = "2026-10-17T00:00:02Z"
        return row
    def context(_):
        row = record()
        return {"risk_label": row["risk_label"], "risk_assessed_at_utc": "2026-10-17T00:00:02Z",
                "security_assessed_at_utc": "2026-10-17T00:00:02Z", "scam_policy": row["scam_policy"],
                "activation": row["activation"]}
    tail = FreeTierPricingTail(out_dir=tmp_path / "producer", fetch_market_fn=fetch,
        now_epoch_fn=lambda: clock[0], context_fn=context, paper_state_file=state)
    tail.sync_paper_positions()
    assert MINT in tail.tracked_mints() and not tail.coverage(MINT)["paper_feedback_ready"]
    tail.poll(NOW)
    row = json.loads((tmp_path / "producer/pricing_tail.jsonl").read_text())
    snap = normalize_record(row)
    assert snap.extra["quote_usable"] and snap.extra["security_current"]
    assert snap.ts_epoch == EPOCH + 2
    assert not snap.extra["exposure_eligible"]  # stale feedback still blocks new exposure


def test_scheduler_keeps_terminal_paper_quotes_without_reactivating_watch():
    scheduler = MarketScheduler(now_fn=lambda: EPOCH,
                                price_fetch_fn=lambda _: None, overview_fetch_fn=lambda _: None)
    entry = SimpleNamespace(token_mint=MINT, candidate_id="c", status="SENT_OK_COMMITTED",
                            seeded_at_utc=NOW)
    scheduler.update_candidates([])
    scheduler.update_paper_candidates([entry], max_tracked=1)
    jobs = scheduler.plan(now_epoch=EPOCH, enqueue=False)
    assert jobs and entry.status == "SENT_OK_COMMITTED"
    scheduler.update_candidates([])
    assert scheduler.plan(now_epoch=EPOCH, enqueue=False)


def test_resume_binds_source_roots_and_filter_policy(tmp_path):
    first, second = tmp_path / "one", tmp_path / "two"
    first.mkdir()
    second.mkdir()
    source = TailingSnapshotSource([first], producer_streams_only=True)
    checkpoint = source.checkpoint_state()
    for paths, strict in (([second], True), ([first], False)):
        changed = TailingSnapshotSource(paths, producer_streams_only=strict)
        with pytest.raises(ValueError, match="INPUT_SELECTION_MISMATCH"):
            changed.restore_checkpoint(checkpoint)
    with pytest.raises(ValueError, match="INPUT_SELECTION_MISSING"):
        source.restore_checkpoint({"offsets": {str(first / "pricing_tail.jsonl"): 1}})


def test_explicit_rollover_retains_prior_unread_input_and_checkpoint(tmp_path):
    first, second = tmp_path / "one", tmp_path / "two"
    first.mkdir()
    second.mkdir()
    row = record("FREE_TIER_PRICING_TAIL")
    old = first / "pricing_tail.jsonl"
    old.write_text(json.dumps(row) + "\n", encoding="utf-8")
    source = TailingSnapshotSource([first], producer_streams_only=True)
    assert len(source.poll()[0]) == 1
    checkpoint = source.checkpoint_state()
    row["candidate_id"] = "old-unread"
    with old.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row) + "\n")
    row["candidate_id"] = "new-producer"
    (second / "pricing_tail.jsonl").write_text(json.dumps(row) + "\n", encoding="utf-8")
    resumed = TailingSnapshotSource([second, first], producer_streams_only=True,
                                    allow_input_rollover=True)
    resumed.restore_checkpoint(checkpoint)
    snapshots, errors = resumed.poll()
    assert not errors and {s.candidate_id for s in snapshots} == {"old-unread", "new-producer"}
    assert resumed.poll() == ([], [])
    dropped = TailingSnapshotSource([second], producer_streams_only=True,
                                    allow_input_rollover=True)
    with pytest.raises(ValueError, match="INPUT_SELECTION_MISMATCH"):
        dropped.restore_checkpoint(resumed.checkpoint_state())
    old.unlink()
    with pytest.raises(ValueError, match="CHECKPOINTED_INPUT_MISSING"):
        resumed.poll()


def test_terminal_discovery_does_not_authorize_new_tail_entry():
    row = record()
    row["activation"].update(activation_state="SENT_OK_COMMITTED", activation_proof_valid=True)
    assert normalize_record(row).extra["exposure_eligible"]
    row["kind"] = "FREE_TIER_PRICING_TAIL"
    assert not normalize_record(row).extra["exposure_eligible"]


def test_archived_paper_context_authorizes_only_bound_continuation():
    row = record("FREE_TIER_PRICING_TAIL")
    saved = copy.deepcopy(row["activation"])
    saved.update(token_mint=MINT, candidate_id="candidate", activation_proof_valid=True)
    row["paper_position_context"] = {"mint": MINT, "candidate_id": "candidate",
        "migration_time_utc": "2026-10-16T23:00:00Z", "activation": saved}
    row["activation"] = {}
    snap = normalize_record(row)
    assert not snap.extra["exposure_eligible"] and snap.extra["dca_exposure_eligible"]
    row["paper_position_context"]["candidate_id"] = "different"
    assert not normalize_record(row).extra["dca_exposure_eligible"]
    row["paper_position_context"]["candidate_id"] = "candidate"
    row["security_assessed_at_utc"] = "2026-10-16T23:00:00Z"
    assert not normalize_record(row).extra["dca_exposure_eligible"]


def test_tail_preserves_all_same_mint_position_contexts(tmp_path):
    first = {"mint": MINT, "candidate_id": "candidate",
        "migration_time_utc": "2026-10-16T23:00:00Z", "activation": record()["activation"]}
    second = copy.deepcopy(first)
    second["candidate_id"] = "second-candidate"
    second["activation"]["candidate_id"] = "second-candidate"
    state = tmp_path / "paper_state.json"
    state.write_text(json.dumps({"heartbeat_utc": NOW, "open_mints": [
        {"mint": MINT, "candidate_id": context["candidate_id"], "paper_position_context": context}
        for context in (first, second, first)]}), encoding="utf-8")
    tail = FreeTierPricingTail(out_dir=tmp_path / "producer", fetch_market_fn=lambda _: {},
        now_epoch_fn=lambda: EPOCH, max_tracked=1, paper_state_file=state)
    tail.sync_paper_positions()
    contexts = tail.paper_positions()[MINT]["paper_position_contexts"]
    assert contexts == [first, second]
    assert tail.tracked_mints() == (MINT,) and tail.coverage(MINT)["paper_feedback_ready"]
    row = record("FREE_TIER_PRICING_TAIL")
    row["activation"] = {}
    invalid = copy.deepcopy(second)
    invalid["activation"]["token_mint"] = "wrong-mint"
    row["paper_position_contexts"] = [*contexts, invalid]
    snapshot = normalize_record(row)
    assert snapshot.extra["paper_position_contexts"] == [first, second]
    assert snapshot.extra["dca_exposure_eligible"] and not snapshot.extra["exposure_eligible"]
    row["security_assessed_at_utc"] = "2026-10-16T23:00:00Z"
    assert not normalize_record(row).extra["dca_exposure_eligible"]


def test_sibling_ath_symlink_and_event_only_known_time_are_refused(tmp_path, monkeypatch):
    from pathlib import Path
    from PHX2.paper_trading.pricing import _load_central_ath_for_input
    state = tmp_path / "ath_state.json"
    state.write_text(json.dumps({"schema_version": "phx2_central_ath_v1",
        "mints": {MINT: {"ath_market_cap": "90000"}}}), encoding="utf-8")
    original = Path.is_symlink
    monkeypatch.setattr(Path, "is_symlink", lambda path: path == state or original(path))
    assert _load_central_ath_for_input(str(tmp_path / "pricing_tail.jsonl")) == {}
    snap = normalize_record(record())
    _overlay_central_ath(snap, {MINT: {"ath_market_cap": "90000",
        "ath_timestamp": NOW, "resolved_observed_at_utc": NOW}})
    assert snap.ath_market_cap_usd is None

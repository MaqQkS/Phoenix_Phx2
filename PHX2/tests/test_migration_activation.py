from __future__ import annotations

import ast
from datetime import datetime, timezone
from decimal import Decimal
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from PHX2.dashboard.adapter import build_candidate_rows, load_producer
from PHX2.free_tier_producer import free_tier_session as producer_session
from PHX2.free_tier_producer.ath_state import CentralAthStateStore
from PHX2.free_tier_producer.compat import build29_cap1_compose_send as compose_send
from PHX2.free_tier_producer.compat.build30_watchlist import (
    BASELINE_CAPTURED,
    BASELINE_SOURCE_BIRDEYE,
    BASELINE_SOURCE_GRPC_EVENT,
    BASELINE_UNPROVEN_LEGACY,
    MIGRATION_ACTIVATION_MULTIPLIER,
    WATCH_ACTIVE_DIP,
    WATCH_EXPIRED,
    WATCH_PENDING_1_20X,
    WATCH_PENDING_BASELINE,
    WatchEntry,
    Watchlist,
    activation_proof_is_eligible,
)
from PHX2.free_tier_producer.compat.production_live_runner import (
    ProductionBounds,
    seed_discovered_candidates,
)
from PHX2.free_tier_producer.paid_provider import (
    PROVIDER_MODE_PAID_PRIMARY,
    event_to_candidate,
)
from PHX2.observability.operator_console import OperatorConsole
from PHX2.paper_trading.pricing import normalize_record
from PHX2.runtime.production_supervisor import ProductionConfig


MINT = "EkNbQMQYpd4JET5FpZrqbdkYdHXeqocZcBByJpFWpump"
MIGRATION_AT = "2026-07-16T12:00:00Z"
OBSERVED_AT = "2026-07-16T12:00:01Z"


def candidate(**overrides):
    value = {
        "token_mint": MINT,
        "candidate_id": "migration-candidate",
        "migration_time_utc": MIGRATION_AT,
        "source_ref": "grpc-event-ref",
    }
    value.update(overrides)
    return value


def event_baseline_candidate(**overrides):
    return candidate(**{
        "migration_market_cap_usd": "100",
        "migration_market_cap_source": BASELINE_SOURCE_GRPC_EVENT,
        "migration_market_cap_observed_at_utc": MIGRATION_AT,
        "migration_market_cap_price": "0.0000001",
        "migration_supply_at_observation": "1000000000",
        **overrides,
    })


def observe(entry, market_cap="110", *, price="0.00000011",
            provider_at=OBSERVED_AT, now="2026-07-16T12:00:02Z",
            source="PAID_MARKET_PRIMARY", supply=None):
    return entry.observe_market(
        current_market_cap_usd=market_cap,
        current_price=price,
        current_supply=supply,
        provider_timestamp_utc=provider_at,
        observed_at_utc=now,
        observation_source=source,
        max_age_seconds=120,
    )


def active_entry(crossing="120"):
    entry = Watchlist().seed(event_baseline_candidate(), seeded_at_utc=MIGRATION_AT)
    assert entry is not None
    result = observe(entry, crossing)
    assert result["just_activated"]
    return entry


def test_production_multiplier_is_exact_decimal_and_not_weakenable(tmp_path):
    assert MIGRATION_ACTIVATION_MULTIPLIER == Decimal("1.20")
    assert ProductionConfig(run_dir=tmp_path).migration_activation_multiplier == Decimal("1.20")
    with pytest.raises(ValueError):
        ProductionConfig(run_dir=tmp_path, migration_activation_multiplier=Decimal("1.19"))


def test_exact_event_baseline_capture_and_provenance():
    entry = Watchlist().seed(event_baseline_candidate(), seeded_at_utc=MIGRATION_AT)
    assert entry is not None
    assert entry.status == WATCH_PENDING_1_20X
    assert entry.migration_market_cap_usd == "100"
    assert entry.migration_market_cap_source == BASELINE_SOURCE_GRPC_EVENT
    assert entry.migration_market_cap_price == "0.0000001"
    assert entry.migration_supply_at_observation == "1000000000"
    assert entry.activation_target_market_cap_usd == "120.00"


@pytest.mark.parametrize("bad_field,bad_value", (
    ("migration_market_cap_usd", "0"),
    ("migration_market_cap_usd", 100.0),
    ("migration_market_cap_price", None),
    ("migration_supply_at_observation", None),
    ("migration_market_cap_observed_at_utc", "not-a-time"),
))
def test_invalid_event_baseline_is_rejected(bad_field, bad_value):
    entry = Watchlist().seed(
        event_baseline_candidate(**{bad_field: bad_value}), seeded_at_utc=MIGRATION_AT)
    assert entry is not None
    assert entry.status == WATCH_PENDING_BASELINE
    assert entry.migration_market_cap_usd is None


def test_first_fresh_birdeye_snapshot_is_fallback_baseline_without_inferred_supply():
    entry = Watchlist().seed(candidate(), seeded_at_utc=MIGRATION_AT)
    result = observe(entry, "5420", price="0.00000542")
    assert not result["eligible"]
    assert entry.migration_market_cap_usd == "5420"
    assert entry.migration_market_cap_source == BASELINE_SOURCE_BIRDEYE
    assert entry.migration_market_cap_price == "0.00000542"
    assert entry.migration_supply_at_observation is None
    assert entry.activation_target_market_cap_usd == "6504.00"


def test_stale_or_non_birdeye_fallback_never_captures():
    stale = Watchlist().seed(candidate(), seeded_at_utc=MIGRATION_AT)
    observe(stale, provider_at="2026-07-16T11:00:00Z")
    assert stale.status == WATCH_PENDING_BASELINE
    wrong = Watchlist().seed(candidate(), seeded_at_utc=MIGRATION_AT)
    observe(wrong, source="NON_PAID_PRIMARY")
    assert wrong.status == WATCH_PENDING_BASELINE


def test_baseline_is_captured_exactly_once_and_never_replaced():
    entry = Watchlist().seed(event_baseline_candidate(), seeded_at_utc=MIGRATION_AT)
    observe(entry, "50")
    observe(entry, "200")
    assert entry.migration_market_cap_usd == "100"
    assert entry.migration_market_cap_source == BASELINE_SOURCE_GRPC_EVENT
    assert entry.migration_market_cap_price == "0.0000001"


@pytest.mark.parametrize("market_cap,activates", (
    ("119.999999999999999999", False),
    ("120.00", True),
    ("120.000000000000000001", True),
))
def test_decimal_exact_activation_boundary(market_cap, activates):
    entry = Watchlist().seed(event_baseline_candidate(), seeded_at_utc=MIGRATION_AT)
    result = observe(entry, market_cap)
    assert result["just_activated"] is activates
    assert (entry.status == WATCH_ACTIVE_DIP) is activates


def test_activation_is_monotonic_and_requires_no_second_crossing():
    entry = active_entry("125")
    crossing_at = entry.activated_at_utc
    below = observe(
        entry, "90", provider_at="2026-07-16T12:00:03Z",
        now="2026-07-16T12:00:04Z")
    assert below["eligible"]
    assert not below["just_activated"]
    assert entry.status == WATCH_ACTIVE_DIP
    assert entry.activated_at_utc == crossing_at
    assert entry.activation_current_market_cap_usd == "125"


def test_crossing_emits_one_activation_sequence_and_duplicate_does_not_repeat():
    entry = Watchlist().seed(event_baseline_candidate(), seeded_at_utc=MIGRATION_AT)
    first = observe(entry, "121")
    second = observe(entry, "121")
    assert [event["event"] for event in first["events"]].count("ACTIVATED") == 1
    assert [event["event"] for event in first["events"]].count("ACTIVE_DIP_WATCH") == 1
    assert not any(event["event"] == "ACTIVATED" for event in second["events"])


def test_activation_proof_rejects_missing_malformed_and_legacy_state():
    assert not activation_proof_is_eligible(None)
    assert not activation_proof_is_eligible({"activation_state": WATCH_ACTIVE_DIP})
    legacy = WatchEntry(
        token_mint=MINT, candidate_id="legacy", migration_time_utc=MIGRATION_AT,
        source_ref=None, seeded_at_utc=MIGRATION_AT, status="WATCHING")
    assert legacy.status == WATCH_PENDING_BASELINE
    assert legacy.migration_baseline_status == BASELINE_UNPROVEN_LEGACY
    assert not activation_proof_is_eligible(legacy)
    forged = WatchEntry(
        token_mint=MINT, candidate_id="forged", migration_time_utc=MIGRATION_AT,
        source_ref=None, seeded_at_utc=MIGRATION_AT, status=WATCH_ACTIVE_DIP)
    assert forged.status == WATCH_PENDING_BASELINE
    assert not activation_proof_is_eligible(forged)


def test_compose_reserve_and_transport_are_not_reached_for_pending(monkeypatch):
    calls = {"compose": 0, "guard": 0}
    monkeypatch.setattr(
        compose_send, "compose_no_send_dispatch_deduped",
        lambda *args, **kwargs: calls.__setitem__("compose", calls["compose"] + 1))

    class Guard:
        def authorize_and_dispatch(self, *args, **kwargs):
            calls["guard"] += 1

    result = compose_send.compose_and_maybe_send(
        object(), ath_transport=object(), ath_endpoint_secret=object(),
        now_utc=datetime.now(timezone.utc), now_seconds=lambda: Decimal(0),
        ledger=object(), guard=Guard(), authorization=object(),
        created_at_utc=OBSERVED_AT, activation_proof={
            "activation_state": WATCH_PENDING_1_20X,
        })
    assert not result["eligible"]
    assert result["compose_reason"] == "ACTIVATION_PROOF_REQUIRED"
    assert calls == {"compose": 0, "guard": 0}


class _Sidecar:
    def __init__(self, market_cap="120", central_ath=None, at=OBSERVED_AT):
        self.market_cap = market_cap
        self.central_ath = central_ath or {}
        self.at = at

    def resolve(self, mint, **kwargs):
        return {
            "current_price": "0.00000012",
            "current_market_cap_usd": self.market_cap,
            "liquidity_usd": "9000",
            "market_context_fetched_at_utc": self.at,
            "provider_timestamp_utc": self.at,
            "all_present": True,
            "basis": "REAL_MARKET_PRESENT",
            "attempts": [],
            "central_ath": dict(self.central_ath),
        }

    def central_ath_snapshot(self, mint):
        return dict(self.central_ath)


def _run_candidate(entry, sidecar, *, compose_stub, pre_reserve_gate=None):
    def gate(_candidate, context):
        return observe(
            entry, context["current_market_cap_usd"],
            price=context["current_price"],
            provider_at=context["provider_timestamp_utc"],
            now="2026-07-16T12:00:02Z")

    old = producer_session.sess.cs.compose_and_maybe_send
    producer_session.sess.cs.compose_and_maybe_send = compose_stub
    try:
        return producer_session.sess.run_cap1_candidates(
            [entry.to_candidate()], sidecar=sidecar,
            ath_transport=object(), ath_endpoint_secret=object(),
            now_utc=datetime.now(timezone.utc), now_seconds=lambda: Decimal(0),
            now_iso_fn=lambda: "2026-07-16T12:00:02Z",
            sleep_fn=lambda _seconds: None, ledger=object(), guard=object(),
            authorization=object(), created_at_utc=OBSERVED_AT,
            activation_gate_fn=gate, pre_reserve_gate_fn=pre_reserve_gate)
    finally:
        producer_session.sess.cs.compose_and_maybe_send = old


def test_threshold_crossing_itself_never_composes_or_sends():
    entry = Watchlist().seed(event_baseline_candidate(), seeded_at_utc=MIGRATION_AT)
    calls = {"compose": 0}
    result = _run_candidate(
        entry, _Sidecar("120"),
        compose_stub=lambda *a, **k: calls.__setitem__("compose", 1))
    assert result["outcome"] == "ZERO_SEND"
    assert calls["compose"] == 0
    assert entry.status == WATCH_ACTIVE_DIP


def test_activated_candidate_still_passes_through_existing_risk_gate():
    entry = active_entry()
    calls = {"compose": 0}
    result = _run_candidate(
        entry, _Sidecar("110", at="2026-07-16T12:00:03Z"),
        compose_stub=lambda *a, **k: calls.__setitem__("compose", 1),
        pre_reserve_gate=lambda _mint, _ctx: "RISK_HIGH_BLOCKED")
    assert result["per_candidate"][0]["reason"] == "RISK_HIGH_BLOCKED"
    assert calls["compose"] == 0


def test_pending_market_observation_carries_authoritative_pre_activation_ath():
    entry = Watchlist().seed(event_baseline_candidate(), seeded_at_utc=MIGRATION_AT)
    ath = {"ath_market_cap": "150", "ath_provider": "GRPC_EVENT"}
    result = _run_candidate(entry, _Sidecar("110", ath), compose_stub=lambda *a, **k: None)
    record = result["per_candidate"][0]
    assert record["market_context"]["central_ath"] == ath
    assert entry.status == WATCH_PENDING_1_20X


def test_pending_ath_checkpoint_survives_restart_and_lower_observation(tmp_path):
    store = CentralAthStateStore(tmp_path)
    assert store.observe_provider_current(
        mint=MINT, price_usd="0.00015", market_cap_usd="150",
        observed_at=OBSERVED_AT, confirmed=False)
    restored = CentralAthStateStore(tmp_path)
    assert not restored.observe_provider_current(
        mint=MINT, price_usd="0.00011", market_cap_usd="110",
        observed_at="2026-07-16T12:00:03Z", confirmed=False)
    assert restored.snapshot(MINT)["ath_market_cap"] == "150"


@pytest.mark.parametrize("state", (WATCH_PENDING_BASELINE, WATCH_PENDING_1_20X, WATCH_ACTIVE_DIP))
def test_watch_activation_state_survives_restart(tmp_path, state):
    watchlist = Watchlist()
    if state == WATCH_PENDING_BASELINE:
        entry = watchlist.seed(candidate(), seeded_at_utc=MIGRATION_AT)
    else:
        entry = watchlist.seed(event_baseline_candidate(), seeded_at_utc=MIGRATION_AT)
        if state == WATCH_ACTIVE_DIP:
            observe(entry, "120")
    path = tmp_path / "watch_state.jsonl"
    watchlist.persist(path)
    restored = Watchlist.load(path).get(MINT)
    assert restored.status == state
    assert restored.migration_market_cap_usd == entry.migration_market_cap_usd
    assert restored.activated_at_utc == entry.activated_at_utc


def test_restart_keeps_activation_monotonic_and_baseline_immutable(tmp_path):
    watchlist = Watchlist()
    entry = watchlist.seed(event_baseline_candidate(), seeded_at_utc=MIGRATION_AT)
    observe(entry, "130")
    path = tmp_path / "watch_state.jsonl"
    watchlist.persist(path)
    restored = Watchlist.load(path).get(MINT)
    result = observe(
        restored, "80", provider_at="2026-07-16T12:00:03Z",
        now="2026-07-16T12:00:04Z")
    assert result["eligible"]
    assert restored.migration_market_cap_usd == "100"
    assert restored.activation_current_market_cap_usd == "130"


def test_interrupted_or_malformed_checkpoint_uses_last_valid_backup(tmp_path):
    watchlist = Watchlist()
    entry = watchlist.seed(event_baseline_candidate(), seeded_at_utc=MIGRATION_AT)
    observe(entry, "125")
    path = tmp_path / "watch_state.jsonl"
    watchlist.persist(path)
    watchlist.persist(path)  # establishes a validated backup
    path.write_text("{partial", encoding="utf-8")
    restored = Watchlist.load(path).get(MINT)
    assert restored is not None
    assert activation_proof_is_eligible(restored)


def test_legacy_watch_record_cannot_silently_capture_later_current_mc(tmp_path):
    path = tmp_path / "watch_state.jsonl"
    path.write_text(json.dumps({
        "token_mint": MINT, "candidate_id": "legacy",
        "migration_time_utc": MIGRATION_AT, "source_ref": "legacy",
        "seeded_at_utc": MIGRATION_AT, "status": "WATCHING",
    }) + "\n", encoding="utf-8")
    entry = Watchlist.load(path).get(MINT)
    result = observe(entry, "1000000")
    assert not result["eligible"]
    assert entry.migration_market_cap_usd is None
    assert entry.migration_baseline_status == BASELINE_UNPROVEN_LEGACY


def test_pending_candidate_expires_under_existing_watch_age_policy():
    watchlist = Watchlist()
    entry = watchlist.seed(event_baseline_candidate(), seeded_at_utc=MIGRATION_AT)
    expired = watchlist.expire_stale_entries(
        now_age_seconds_fn=lambda _seeded: 3600,
        max_age_seconds=3600, max_rechecks=999)
    assert expired == [entry]
    assert entry.status == WATCH_EXPIRED
    assert entry.last_reason == "NEVER_REACHED_ACTIVATION_THRESHOLD"
    assert entry not in watchlist.active_entries()


def test_real_queue_handoff_seeds_pending_and_emits_lifecycle_events():
    watchlist = Watchlist()
    handoff = []
    activation = []
    seed_discovered_candidates(
        watchlist=watchlist, candidates=[candidate()], seeded_at_utc=MIGRATION_AT,
        on_handoff_event=handoff.append, on_activation_event=activation.append)
    assert watchlist.get(MINT).status == WATCH_PENDING_BASELINE
    assert any(record["event"] == "WATCHLIST_ACKNOWLEDGED" for record in handoff)
    assert [record["event"] for record in activation] == [
        "MIGRATION_DETECTED", "PENDING_BASELINE"]


def test_paid_queue_handoff_cadence_remains_45_seconds():
    bounds = producer_session._bounds_with_provider_handoff_cadence(
        ProductionBounds(recheck_interval_seconds=45, reseed_interval_seconds=240),
        PROVIDER_MODE_PAID_PRIMARY)
    assert bounds.reseed_interval_seconds == 45


def test_same_single_yellowstone_subscribe_owner_remains():
    source = Path(producer_session.__file__).with_name("paid_grpc_source.py").read_text(
        encoding="utf-8")
    assert source.count("stub.Subscribe(") == 1
    assert "Helius" not in source and "wss://" not in source


@pytest.mark.parametrize("event,expected", (
    ({"event": "MIGRATION_DETECTED", "state": "PENDING_BASELINE"}, "MIGRATION"),
    ({"event": "BASELINE_CAPTURED", "migration_market_cap_usd": "5420",
      "source": "GRPC_EVENT"}, "CAPTURED"),
    ({"event": "PENDING_1_20X", "activation_target_market_cap_usd": "6504"},
     "PENDING_1_20X"),
    ({"event": "PROGRESS", "current_market_cap_usd": "6100", "multiplier": "1.125"},
     "move=1.125x"),
    ({"event": "ACTIVATED", "multiplier": "1.204"}, "ACTIVATED"),
    ({"event": "ACTIVE_DIP_WATCH"}, "ACTIVE_DIP_WATCH"),
    ({"event": "EXPIRED", "reason": "NEVER_REACHED_ACTIVATION_THRESHOLD"}, "EXPIRED"),
))
def test_console_renders_real_activation_events(tmp_path, event, expected):
    lines = []
    console = OperatorConsole(tmp_path, output=lines.append)
    console.render_record({"kind": "PHX2_WATCHLIST_EVENT", "token_mint": MINT, **event})
    assert any(expected in line for line in lines)


def test_console_periodic_status_reports_separate_activation_counts(tmp_path):
    lines = []
    console = OperatorConsole(tmp_path, output=lines.append, clock=lambda: 1000)
    console.render_record({
        "kind": "PRODUCTION_LIVE_HEARTBEAT",
        "pending_baseline": 1, "pending_1_20x": 2,
        "activated": 3, "active_dip_watch": 2,
        "provider_telemetry": {}, "credit_budget": {"sent_ok_count": 1},
    })
    status = next(line for line in lines if "[STATUS]" in line)
    assert "pending_baseline=1" in status
    assert "pending_1_20x=2" in status
    assert "activated=3" in status
    assert "active_dip_watch=2" in status


def test_console_import_boundary_remains_read_only():
    path = Path(producer_session.__file__).parents[1] / "observability" / "operator_console.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imports = {alias.name.split(".")[0] for node in ast.walk(tree)
               if isinstance(node, ast.Import) for alias in node.names}
    imports.update(node.module.split(".")[0] for node in ast.walk(tree)
                   if isinstance(node, ast.ImportFrom) and node.module)
    assert not imports.intersection({"requests", "urllib", "socket", "grpc", "discord"})


def test_activation_artifacts_pass_production_redaction_scan(tmp_path):
    entry = active_entry("125")
    (tmp_path / "activation_events.jsonl").write_text(
        "\n".join(json.dumps(record, sort_keys=True) for record in (
            entry.initial_activation_events()
            + observe(entry, "90")["events"])) + "\n",
        encoding="utf-8")
    (tmp_path / "producer_summary.json").write_text(json.dumps({
        "migration_activation": {
            "activation_multiplier": "1.20",
            "baseline_priority": [
                "GRPC_EVENT", "PAID_MARKET_PRIMARY_FALLBACK"],
            "counts": {"pending_baseline": 0, "pending_1_20x": 0,
                       "activated": 1, "active_dip_watch": 1},
        },
    }), encoding="utf-8")
    scan = producer_session.artifacts.run_redaction_scan(tmp_path)
    assert scan["redaction_status"] == "REDACTED"
    assert scan["total_unsafe_hits"] == 0
    assert scan["positive_control_ok"] is True


def test_paper_and_dashboard_consume_identical_central_activation_fields(tmp_path):
    activation = active_entry("125").activation_snapshot()
    record = {
        "kind": "BUILD30_CANDIDATE_RECHECK",
        "token_mint": MINT,
        "candidate_id": "migration-candidate",
        "observed_at_utc": OBSERVED_AT,
        "migration_time_utc": MIGRATION_AT,
        "activation": activation,
        "current_price": "0.00000011",
        "current_market_cap_usd": "110",
        "liquidity_usd": "9000",
    }
    paper = normalize_record(record)
    assert paper.extra["activation"] == activation
    assert paper.extra["activation_eligible"] is True

    producer = tmp_path / "producer"
    producer.mkdir()
    watch = {
        "token_mint": MINT, "candidate_id": "migration-candidate",
        "seeded_at_utc": MIGRATION_AT, "last_observed_at_utc": OBSERVED_AT,
        "status": WATCH_ACTIVE_DIP,
        **{key: value for key, value in activation.items()
           if key not in ("activation_state", "activation_eligible")},
    }
    (producer / "watch_state.jsonl").write_text(
        json.dumps(watch) + "\n", encoding="utf-8")
    candidate_dir = producer / "candidates"
    candidate_dir.mkdir()
    (candidate_dir / "migration-candidate.jsonl").write_text(
        json.dumps(record) + "\n", encoding="utf-8")
    now = datetime(2026, 7, 16, 12, 0, 2, tzinfo=timezone.utc)
    row = build_candidate_rows(load_producer(producer, now), now)[0]
    assert row["migrationMarketCapUsd"] == activation["migration_market_cap_usd"]
    assert row["migrationMarketCapSource"] == activation["migration_market_cap_source"]
    assert row["activationState"] == activation["activation_state"]
    assert row["activatedAtUtc"] == activation["activated_at_utc"]


def test_event_projection_preserves_exact_optional_grpc_baseline():
    event = SimpleNamespace(
        base_mint=MINT, mint=MINT, pool_account="POOL", pool_program_id="PROGRAM",
        quote_mint="QUOTE", event_id="event", provider_event_id="signature",
        observed_at_utc=MIGRATION_AT, raw_event_hash="hash",
        migration_baseline={
            "migration_market_cap_usd": "100",
            "migration_market_cap_source": "GRPC_EVENT",
            "migration_market_cap_observed_at_utc": MIGRATION_AT,
            "migration_market_cap_price": "0.0000001",
            "migration_supply_at_observation": "1000000000",
        })
    projected = event_to_candidate(event)
    assert projected["migration_market_cap_usd"] == "100"
    assert projected["migration_market_cap_source"] == "GRPC_EVENT"
    assert projected["migration_supply_at_observation"] == "1000000000"

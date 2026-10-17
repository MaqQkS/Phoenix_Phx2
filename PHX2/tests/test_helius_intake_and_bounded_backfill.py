"""Integrated end-to-end regression cover for the 2026-07-30 remediation.

Two invariants, proven together against real production machinery:

A. ``LIVE_HELIUS`` is valid authoritative live provenance at every production
   boundary: provider admission -> ONE dedupe pass -> watchlist seed ->
   activation intake -> corroboration -> tier evaluation -> compose ->
   fake-transport delivery.  Unknown provenance stays rejected.

B. Bounded six-hour DEX candidate recovery works under Helius-primary:
   startup recovery + periodic safety net (durable cursor, bounded backoff,
   idempotent dedupe), pre-epoch admission for approved backfill provenance
   only, ATH/market hydration anchored at MIGRATION time, single
   current-tier evaluation with no historical tier replay, failure isolation,
   and historical RPC replay / Chainstack staying disabled.

Fixtures: PHX2/tests/fixtures/helius_backfill_remediation_20260730.json —
the 17 preserved (mint, signature) pairs from the failed run
``paid_primary_live_24x7_20260730T132310Z`` plus the SQUIRREL / Pponyo /
Ashty migration-age timings PHX1 recovered and PHX2 missed.

Offline-only: no network, no real transports, no canonical ledger writes.
"""

from __future__ import annotations

import json
import threading
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

from PHX2.models.discovery_provenance import (
    BACKFILL_DISCOVERY_PROVENANCES,
    DISCOVERY_PROVENANCES,
    DISCOVERY_PROVENANCE_DEX_BACKFILL,
    DISCOVERY_PROVENANCE_LIVE_HELIUS,
    DISCOVERY_PROVENANCE_LIVE_YELLOWSTONE,
    LIVE_DISCOVERY_PROVENANCES,
    is_backfill_discovery_provenance,
    is_known_discovery_provenance,
    is_live_discovery_provenance,
)
from PHX2.delivery.telegram_adapter import TelegramDeliveryAdapter
from PHX2.delivery.telegram_composer import DISCOVERY_PROVENANCE_TOKENS
from PHX2.delivery.telegram_transport import SENT_OK
from PHX2.free_tier_producer import free_tier_session
from PHX2.free_tier_producer import helius_source
from PHX2.free_tier_producer.ath_state import CentralAthStateStore
from PHX2.free_tier_producer.compat.build30_watchlist import (
    Watchlist,
    _expected_activation_multiplier,
)
from PHX2.free_tier_producer.dexscreener_restart_backfill import (
    BACKFILL_STATE_DEGRADED,
    BACKFILL_STATE_FAILED,
    BACKFILL_STATE_HEALTHY,
    BACKFILL_STATE_STARTING,
    DexRestartBackfill,
    FAILED_SWEEP_THRESHOLD,
    PHX1_LOOKBACK_SECONDS,
    PHX1_SUPPLY,
    SWEEP_KIND_PERIODIC,
    SWEEP_KIND_STARTUP,
    build_backfill_candidate,
    validate_backfill_candidate_evidence,
)
from PHX2.free_tier_producer.launcher_contract import (
    canonical_launcher_arguments,
    validate_launcher_arguments,
)
from PHX2.free_tier_producer.live_epoch import (
    _CANONICAL_SEMANTIC_POLICY,
    EPOCH_EVENT_BEFORE_START_REJECTED,
    LiveEpochManager,
)
from PHX2.free_tier_producer.market_scheduler import project_closed_tier
from PHX2.free_tier_producer.paid_provider import (
    ProviderCandidateDedupe,
    apply_provider_dedupe_once,
    provider_dedupe_already_applied,
)
from PHX2.integrations.dexscreener_client import DEX_BACKFILL_SUCCESS
from PHX2.operator_cli import dex_backfill_status_text
from PHX2.stage30.stage30_11_16_fake_real_send_proof import (
    default_real_send_authorization,
)
from PHX2.stage30.stage30_11_16_real_private_transport_guard import (
    make_stage30_11_16_real_private_transport_guard,
)
from PHX2.tests.delivery.test_telegram_composer import (
    _sample as sample_ping_data,
)
from PHX2.tests.delivery.test_telegram_delivery import (
    CREATED as DELIVERY_CREATED,
    FakeTelegramTransport,
    MINT as DELIVERY_MINT,
    _deduped,
    _delivery_context,
)
from PHX2.tests.test_provider_dedupe_single_pass import (
    NOW,
    _admit,
    _owner,
    _paid_event,
)


FIXTURE_PATH = (
    Path(__file__).parent / "fixtures"
    / "helius_backfill_remediation_20260730.json"
)
FIXTURE = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
FUNNEL_PAIRS = [tuple(pair) for pair in FIXTURE["helius_funnel"]["pairs"]]

EPOCH_ID = "epoch_test_20260730"
#: Deterministic clock base for backfill sweeps (no wall clock anywhere).
BASE_EPOCH = 1_753_880_000.0
BASE_UTC_MS = int(BASE_EPOCH * 1000)

compose_send = free_tier_session.cs


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _dex_pair(
    *,
    mint: str = "BackfillSeedCandidateMint111111111111pump",
    pair_address: str = "BackfillPairAddress11111111111111111111111",
    created_ms: int,
    price: str = "0.00003",
    mcap: str = "30000",
    liquidity: str = "9000",
) -> dict:
    return {
        "chainId": "solana",
        "dexId": "pumpswap",
        "pairAddress": pair_address,
        "baseToken": {"address": mint, "symbol": "BKF", "name": "Backfill"},
        "quoteToken": {
            "address": "So11111111111111111111111111111111111111112"},
        "pairCreatedAt": created_ms,
        "priceUsd": price,
        "marketCap": mcap,
        "liquidity": {"usd": liquidity},
        "volume": {"m5": "100", "h1": "1000", "h6": "3000", "h24": "9000"},
    }


def _build_candidate(*, age_seconds: float, mint: str = None, pair: str = None):
    kwargs = {}
    if mint is not None:
        kwargs["mint"] = mint
    if pair is not None:
        kwargs["pair_address"] = pair
    return build_backfill_candidate(
        pair=_dex_pair(
            created_ms=int((BASE_EPOCH - age_seconds) * 1000), **kwargs),
        sol_price_usd=Decimal("150"),
        sol_fallback_used=False,
        sweep_id="dex_sweep_fixture",
        epoch_id=EPOCH_ID,
        discovery_utc="2026-07-30T13:23:20Z",
        now_epoch=BASE_EPOCH,
    )


class _FakeDexClient:
    """Deterministic in-memory DexScreener client for sweep tests."""

    def __init__(self, pairs):
        self._pairs = list(pairs)

    def current_sol_price_usd(self):
        return 150.0, DEX_BACKFILL_SUCCESS

    def latest_token_profiles(self):
        return (
            [
                {
                    "chainId": "solana",
                    "tokenAddress": pair["baseToken"]["address"],
                }
                for pair in self._pairs
            ],
            DEX_BACKFILL_SUCCESS,
        )

    def token_pairs(self, batch):
        return (
            [pair for pair in self._pairs
             if pair["baseToken"]["address"] in set(batch)],
            DEX_BACKFILL_SUCCESS,
        )

    def stats(self):
        return {
            "requests_attempted": 3,
            "requests_succeeded": 3,
            "requests_failed": 0,
            "retry_count": 0,
            "rate_limit_count": 0,
            "last_error_class": None,
        }


def _run_sweep_and_wait(backfill, epoch_id, *, timeout=5.0):
    """Start one sweep through the scheduler entry point and join it."""

    done = threading.Event()
    original_sink = backfill._event_sink

    def sink(record):
        if original_sink is not None:
            original_sink(record)
        if record.get("status") in (
                "BACKFILL_COMPLETE", "BACKFILL_EMPTY_SUCCESS",
                "BACKFILL_PARTIAL", "BACKFILL_FAILED"):
            done.set()

    backfill._event_sink = sink
    started, kind = backfill.maybe_schedule_periodic(epoch_id)
    if started:
        assert done.wait(timeout), "sweep did not complete in time"
    backfill._event_sink = original_sink
    return started, kind


def _seed_helius_candidate(watchlist, mint, *, live_epoch_id=EPOCH_ID):
    entry, outcome = watchlist.seed_with_outcome(
        {
            "token_mint": mint,
            "candidate_id": "helius_" + mint[:8],
            "source_ref": "helius_ref_" + mint[:8],
            "discovery_utc": NOW,
            "discovery_provenance": DISCOVERY_PROVENANCE_LIVE_HELIUS,
            "live_epoch_id": live_epoch_id,
            "migration_slot": 436_159_700,
            "migration_time_utc": NOW,
        },
        seeded_at_utc=NOW,
    )
    return entry, outcome


# ---------------------------------------------------------------------------
# A. centralized contract (matrix items 1, 11, 12, 13)
# ---------------------------------------------------------------------------


def test_live_helius_is_in_the_centralized_closed_set():
    assert DISCOVERY_PROVENANCE_LIVE_HELIUS == "LIVE_HELIUS"
    assert DISCOVERY_PROVENANCE_LIVE_HELIUS in DISCOVERY_PROVENANCES
    assert DISCOVERY_PROVENANCE_LIVE_HELIUS in LIVE_DISCOVERY_PROVENANCES
    assert DISCOVERY_PROVENANCE_LIVE_YELLOWSTONE in DISCOVERY_PROVENANCES
    assert DISCOVERY_PROVENANCE_DEX_BACKFILL in DISCOVERY_PROVENANCES
    assert DISCOVERY_PROVENANCE_DEX_BACKFILL in (
        BACKFILL_DISCOVERY_PROVENANCES)
    assert is_live_discovery_provenance("LIVE_HELIUS")
    assert is_live_discovery_provenance("LIVE_YELLOWSTONE")
    assert not is_live_discovery_provenance("DEXSCREENER_RESTART_BACKFILL")
    assert is_backfill_discovery_provenance("DEXSCREENER_RESTART_BACKFILL")
    assert is_known_discovery_provenance("LIVE_HELIUS")
    # Unknown values are never coerced and never accepted.
    for unknown in ("HELIUS", "live_helius", "LIVE_HELIUS ", "", None, 7):
        assert not is_known_discovery_provenance(unknown)
        assert not is_live_discovery_provenance(unknown)


def test_watchlist_and_provider_share_the_centralized_contract():
    from PHX2.free_tier_producer.compat import build30_watchlist as wl
    from PHX2.free_tier_producer import paid_provider as pp

    assert wl.DISCOVERY_PROVENANCES is DISCOVERY_PROVENANCES
    assert wl.DISCOVERY_PROVENANCE_HELIUS == "LIVE_HELIUS"
    assert wl.LIVE_DISCOVERY_PROVENANCES is LIVE_DISCOVERY_PROVENANCES
    assert pp.DISCOVERY_PROVENANCE_HELIUS == "LIVE_HELIUS"
    assert pp.LIVE_DISCOVERY_PROVENANCES is LIVE_DISCOVERY_PROVENANCES


# ---------------------------------------------------------------------------
# A. LIVE_HELIUS lifecycle (matrix items 2..10, 14)
# ---------------------------------------------------------------------------


def test_full_preserved_funnel_17_helius_candidates_reach_the_watchlist():
    """Matrix item 14: the preserved 17-candidate fixture, end to end."""

    funnel = FIXTURE["helius_funnel"]
    assert len(FUNNEL_PAIRS) == funnel["expected_decoded"] == 17

    dedupe = ProviderCandidateDedupe()
    drained = _admit(dedupe, FUNNEL_PAIRS)
    assert len(drained) == 17
    for candidate in drained:
        assert candidate["discovery_provenance"] == (
            funnel["expected_provenance"])
        assert provider_dedupe_already_applied(candidate) is (
            funnel["expected_provider_dedupe_applied"])

    # The session-level discovery boundary: exactly ONE pass, zero drops.
    survivors = apply_provider_dedupe_once(drained, dedupe)
    assert len(survivors) == funnel["expected_dedupe_survivors"] == 17
    assert dedupe.snapshot()["duplicate_mints_dropped"] == 0

    watchlist = Watchlist(max_size=128)
    admitted = 0
    activation_events = 0
    for candidate in survivors:
        candidate = dict(candidate, live_epoch_id=EPOCH_ID)
        entry, outcome = watchlist.seed_with_outcome(
            candidate, seeded_at_utc=NOW)
        assert outcome == "ADMITTED", (candidate["token_mint"], outcome)
        assert entry is not None
        assert entry.discovery_provenance == "LIVE_HELIUS"
        admitted += 1
        activation_events += len(entry.initial_activation_events())
    assert admitted == funnel["expected_watchlist_admissions"] == 17

    # Activation/tracker intake is nonzero and the funnel counters see the
    # candidates as LIVE (the zero-alert run counted them nowhere).
    assert activation_events > 0
    summary = watchlist.summary()
    assert summary["tracked"] == 17
    assert summary["live_candidates"] == 17
    assert summary["dex_backfill_candidates"] == 0
    assert len(watchlist.active_entries()) == 17


def test_helius_duplicate_mint_reaches_the_corroboration_queue():
    """Matrix item 6: the provider forwards LIVE_HELIUS duplicates."""

    dedupe = ProviderCandidateDedupe()
    owner = _owner(dedupe)
    mint, signature = FUNNEL_PAIRS[0]
    owner._handle_event(_paid_event(mint, signature))
    # Same mint, different event id: DUPLICATE_MINT at the shared dedupe.
    owner._handle_event(_paid_event(mint, signature[::-1]))
    corroborations = owner.drain_corroborations()
    assert len(corroborations) == 1
    assert corroborations[0]["discovery_provenance"] == "LIVE_HELIUS"

    # The watchlist records live corroboration from the OTHER live source.
    watchlist = Watchlist(max_size=8)
    entry, outcome = _seed_helius_candidate(watchlist, mint)
    assert outcome == "ADMITTED"
    corroborating = dict(
        corroborations[0],
        discovery_provenance=DISCOVERY_PROVENANCE_LIVE_YELLOWSTONE,
        live_epoch_id=EPOCH_ID,
    )
    assert watchlist.corroborate(corroborating) is True
    assert DISCOVERY_PROVENANCE_LIVE_YELLOWSTONE in (
        entry.corroborating_sources)
    assert entry.corroborated_live_epoch_id == EPOCH_ID


def test_helius_activation_multiplier_and_checkpoint_restore(tmp_path):
    """LIVE_HELIUS activates at the live 1.20 multiplier and survives a
    checkpoint round-trip without quarantine (matrix items 5, 7)."""

    assert _expected_activation_multiplier(
        {"discovery_provenance": "LIVE_HELIUS"}) == Decimal("1.20")
    assert _expected_activation_multiplier(
        {"discovery_provenance": "LIVE_YELLOWSTONE"}) == Decimal("1.20")
    assert _expected_activation_multiplier(
        {"discovery_provenance": "DEXSCREENER_RESTART_BACKFILL"}) == (
            Decimal("1.39"))
    assert _expected_activation_multiplier(
        {"discovery_provenance": "SOMETHING_ELSE"}) is None

    watchlist = Watchlist(max_size=8)
    entry, outcome = _seed_helius_candidate(watchlist, FUNNEL_PAIRS[1][0])
    assert outcome == "ADMITTED"
    assert entry.activation_multiplier == "1.20"

    checkpoint_path = tmp_path / "watch_state.jsonl"
    watchlist.persist(checkpoint_path)
    restored = Watchlist.load(checkpoint_path, max_size=8)
    assert restored.checkpoint_quarantined is False
    restored_entry = restored.get(FUNNEL_PAIRS[1][0])
    assert restored_entry is not None
    assert restored_entry.discovery_provenance == "LIVE_HELIUS"
    assert restored_entry.is_active()


def test_helius_entries_are_closed_at_the_live_epoch_boundary():
    """LIVE_HELIUS is live provenance: prior-epoch entries expire on epoch
    closure exactly like LIVE_YELLOWSTONE; DEX entries never epoch-close."""

    watchlist = Watchlist(max_size=8)
    entry, _ = _seed_helius_candidate(
        watchlist, FUNNEL_PAIRS[2][0], live_epoch_id="epoch_stale")
    dex_candidate, reason = _build_candidate(age_seconds=300)
    assert reason == "ACCEPTED"
    dex_entry, dex_outcome = watchlist.seed_with_outcome(
        dex_candidate, seeded_at_utc=NOW)
    assert dex_outcome == "ADMITTED"

    closed = watchlist.close_live_epochs_except(
        "epoch_current", closed_at_utc=NOW)
    assert closed == 1
    assert entry.status == "EXPIRED"
    assert dex_entry.is_active()


def test_helius_candidate_composes_and_reaches_fake_delivery(monkeypatch):
    """Matrix items 8, 9, 10, 39: compose + fake-transport delivery."""

    transport = FakeTelegramTransport()
    composed = []
    attempts = []
    adapter = TelegramDeliveryAdapter(
        transport, compose_sink=composed.append,
        attempt_sink=attempts.append, console_sink=None)
    monkeypatch.setattr(
        compose_send, "compose_no_send_dispatch_deduped",
        lambda *args, **kwargs: _deduped(),
    )
    guard = make_stage30_11_16_real_private_transport_guard(
        transport=adapter)
    context = _delivery_context()
    # The ONLY change from the proven DEX delivery harness: the candidate is
    # an authoritative LIVE_HELIUS discovery.
    context["candidate"]["discovery_provenance"] = "LIVE_HELIUS"
    result = compose_send.compose_and_maybe_send(
        SimpleNamespace(token_mint=DELIVERY_MINT), ath_transport=None,
        ath_endpoint_secret=None, now_utc=None, now_seconds=None,
        ledger=object(), guard=guard,
        authorization=default_real_send_authorization(
            created_at_utc=DELIVERY_CREATED),
        created_at_utc=DELIVERY_CREATED, axiom_fee_appender=adapter,
        activation_proof=context["activation"], security_decision=None,
        delivery_context=context,
    )
    assert result["eligible"] is True
    assert result["send_result"].transport_attempted is True
    assert result["send_result"].transport_ok is True
    assert len(transport.messages) == 1
    assert attempts[0]["result"] == SENT_OK

    artifact = composed[0]
    # Stable closed-set rendering; Helius identity preserved, never rewritten
    # to the Yellowstone token, never UNKNOWN, never raising
    # DISCOVERY_PROVENANCE_INVALID.
    assert artifact["discovery_provenance"] == "HELIUS_LIVE"
    assert artifact["ath_coverage"] == "COMPLETE_LIVE"
    body = transport.messages[0]
    assert "Coverage: Partial" not in body
    assert "LIVE_HELIUS" not in body
    assert "UNKNOWN" not in body


def test_composer_token_set_is_closed_and_helius_token_is_stable():
    assert DISCOVERY_PROVENANCE_TOKENS == (
        "LIVE", "HELIUS_LIVE", "DEXSCREENER_RESTART_BACKFILL", "MERGED",
        "UNKNOWN")
    data = replace(
        sample_ping_data(),
        discovery_provenance="HELIUS_LIVE",
        ath_coverage="COMPLETE_LIVE",
    )
    assert data.discovery_provenance == "HELIUS_LIVE"
    # The composer consumes rendering TOKENS, not raw provenance: a raw
    # LIVE_HELIUS string is not a member of the display set and still raises
    # the closed-set refusal, which pins the adapter as the one mapping site.
    with pytest.raises(ValueError, match="DISCOVERY_PROVENANCE_INVALID"):
        replace(sample_ping_data(), discovery_provenance="LIVE_HELIUS")


# ---------------------------------------------------------------------------
# B. bounded six-hour recovery window (matrix items 15..19)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "entry", FIXTURE["backfill_recovery_timings"]["entries"],
    ids=lambda entry: entry["label"])
def test_recent_migrations_inside_six_hours_are_recovered(entry):
    """SQUIRREL (~5m), Pponyo (~51m) and Ashty (~1h33m) timings."""

    age = float(entry["migration_age_seconds_before_startup"])
    assert age <= PHX1_LOOKBACK_SECONDS
    candidate, reason = _build_candidate(age_seconds=age)
    assert reason == "ACCEPTED"
    assert candidate is not None
    assert candidate["discovery_provenance"] == (
        "DEXSCREENER_RESTART_BACKFILL")
    valid, valid_reason = validate_backfill_candidate_evidence(candidate)
    assert valid, valid_reason

    watchlist = Watchlist(max_size=8)
    seeded, outcome = watchlist.seed_with_outcome(
        candidate, seeded_at_utc=NOW)
    assert outcome == "ADMITTED"
    assert seeded.discovery_provenance == "DEXSCREENER_RESTART_BACKFILL"
    assert seeded.activation_multiplier == "1.39"


def test_exact_six_hour_boundary_follows_the_documented_rule():
    boundary = FIXTURE["backfill_recovery_timings"]["boundary_seconds"]
    assert boundary == PHX1_LOOKBACK_SECONDS == 21600
    at_boundary, reason = _build_candidate(age_seconds=float(boundary))
    assert reason == "ACCEPTED"
    assert at_boundary is not None


def test_older_than_six_hours_is_rejected_explicitly():
    candidate, reason = _build_candidate(
        age_seconds=float(PHX1_LOOKBACK_SECONDS + 1))
    assert candidate is None
    assert reason == "OUTSIDE_PHX1_LOOKBACK"


# ---------------------------------------------------------------------------
# B. pre-epoch admission (matrix items 20, 21)
# ---------------------------------------------------------------------------


def test_pre_epoch_candidate_with_approved_backfill_provenance_is_accepted(
        tmp_path):
    manager = LiveEpochManager(
        state_dir=tmp_path,
        now_fn=lambda: "2026-07-30T13:23:11Z",
        id_fn=lambda: EPOCH_ID,
    )
    assert manager.observe_confirmed_slot(436_159_633)
    # A migration ~51 minutes BEFORE the epoch boundary, discovered through
    # the bounded backfill: admitted at the watchlist and untouched by the
    # epoch-closure sweep.
    candidate, reason = _build_candidate(age_seconds=3060)
    assert reason == "ACCEPTED"
    watchlist = Watchlist(max_size=8)
    entry, outcome = watchlist.seed_with_outcome(
        candidate, seeded_at_utc=NOW)
    assert outcome == "ADMITTED"
    epoch_id = manager.snapshot()["live_epoch_id"]
    watchlist.close_live_epochs_except(epoch_id, closed_at_utc=NOW)
    assert entry.is_active()


def test_pre_epoch_candidate_without_approved_provenance_is_rejected(
        tmp_path):
    manager = LiveEpochManager(
        state_dir=tmp_path,
        now_fn=lambda: "2026-07-30T13:23:11Z",
        id_fn=lambda: EPOCH_ID,
    )
    assert manager.observe_confirmed_slot(436_159_633)
    snapshot = manager.snapshot()
    start_slot = snapshot["epoch_start_slot"]
    # The live event gate: a pre-boundary slot is refused explicitly.
    admitted, reason, _epoch = manager.admit_event(start_slot - 100)
    assert admitted is False
    assert reason == EPOCH_EVENT_BEFORE_START_REJECTED
    # And a LIVE-provenance entry from a stale epoch is retired at the
    # boundary sweep: pre-epoch eligibility exists ONLY through the approved
    # bounded backfill provenance.
    watchlist = Watchlist(max_size=8)
    entry, outcome = _seed_helius_candidate(
        watchlist, FUNNEL_PAIRS[3][0], live_epoch_id="epoch_before_restart")
    assert outcome == "ADMITTED"
    watchlist.close_live_epochs_except(
        snapshot["live_epoch_id"], closed_at_utc=NOW)
    assert not entry.is_active()
    # The same candidate under an unknown provenance never seeds at all.
    unknown_entry, unknown_outcome = watchlist.seed_with_outcome(
        {
            "token_mint": FUNNEL_PAIRS[4][0],
            "candidate_id": "unknown-pre-epoch",
            "discovery_provenance": "UNAPPROVED_BACKFILL",
        },
        seeded_at_utc=NOW,
    )
    assert unknown_entry is None
    assert unknown_outcome == "INVALID_CANDIDATE"


# ---------------------------------------------------------------------------
# B. startup + periodic scheduling, cursor, idempotency (items 22..26)
# ---------------------------------------------------------------------------


def test_startup_sweep_scans_the_six_hour_window_then_periodic_cadence(
        tmp_path):
    clock = {"now": BASE_EPOCH}
    events = []
    pair = _dex_pair(created_ms=BASE_UTC_MS - 3_060_000)
    backfill = DexRestartBackfill(
        client_factory=lambda: _FakeDexClient([pair]),
        event_sink=events.append,
        now_fn=lambda: clock["now"],
        cursor_path=tmp_path / "dex_backfill_cursor.json",
    )

    started, kind = _run_sweep_and_wait(backfill, EPOCH_ID)
    assert started and kind == SWEEP_KIND_STARTUP
    start_events = [e for e in events if e["status"] == "BACKFILL_START"]
    assert start_events[0]["sweep_kind"] == SWEEP_KIND_STARTUP
    assert start_events[0]["lookback_seconds"] == PHX1_LOOKBACK_SECONDS

    # Not due yet: the cadence is a hard lower bound.
    clock["now"] = BASE_EPOCH + 60.0
    started, reason = backfill.maybe_schedule_periodic(EPOCH_ID)
    assert started is False and reason == "NOT_DUE"

    clock["now"] = BASE_EPOCH + 181.0
    started, kind = _run_sweep_and_wait(backfill, EPOCH_ID)
    assert started and kind == SWEEP_KIND_PERIODIC
    start_events = [e for e in events if e["status"] == "BACKFILL_START"]
    assert len(start_events) == 2
    assert start_events[1]["sweep_kind"] == SWEEP_KIND_PERIODIC
    # Every sweep keeps the hard six-hour admission window: the candidate
    # surface has no time pagination, so overlap is the full bounded window
    # and idempotent dedupe suppresses repeats downstream.
    assert start_events[1]["lookback_seconds"] == PHX1_LOOKBACK_SECONDS

    snapshot = backfill.snapshot()
    assert snapshot["operational_state"] == BACKFILL_STATE_HEALTHY
    assert snapshot["sweeps_completed_total"] == 2
    assert snapshot["last_successful_sweep_end_utc"] is not None


def test_cursor_is_durable_and_overlap_creates_no_duplicate_candidates(
        tmp_path):
    clock = {"now": BASE_EPOCH}
    cursor_path = tmp_path / "dex_backfill_cursor.json"
    pair = _dex_pair(created_ms=BASE_UTC_MS - 300_000)
    backfill = DexRestartBackfill(
        client_factory=lambda: _FakeDexClient([pair]),
        now_fn=lambda: clock["now"],
        cursor_path=cursor_path,
    )
    started, _ = _run_sweep_and_wait(backfill, EPOCH_ID)
    assert started
    clock["now"] = BASE_EPOCH + 200.0
    started, _ = _run_sweep_and_wait(backfill, EPOCH_ID)
    assert started

    # Both sweeps re-discovered the same pair (full-window overlap); the
    # session-boundary dedupe plus watchlist mint dedupe admit exactly one.
    drained = backfill.drain()
    assert len(drained) == 2
    dedupe = ProviderCandidateDedupe()
    watchlist = Watchlist(max_size=8)
    admitted = []
    for candidate in drained:
        accepted, _reason = dedupe.accept_with_reason(
            event_id=candidate.get("candidate_id"),
            mint=candidate.get("token_mint"))
        if not accepted:
            continue
        entry, outcome = watchlist.seed_with_outcome(
            candidate, seeded_at_utc=NOW)
        assert outcome == "ADMITTED"
        admitted.append(entry)
    assert len(admitted) == 1
    assert len(watchlist.active_entries()) == 1

    # A later duplicate row is idempotent at the seed boundary too.
    duplicate, reason = _build_candidate(age_seconds=300)
    assert reason == "ACCEPTED"
    _entry, outcome = watchlist.seed_with_outcome(
        duplicate, seeded_at_utc=NOW)
    assert outcome == "EXISTING"
    assert len(watchlist.active_entries()) == 1

    # The durable cursor survives a restart and reports the last successful
    # scan truthfully.
    assert cursor_path.exists()
    reloaded = DexRestartBackfill(
        client_factory=lambda: _FakeDexClient([pair]),
        now_fn=lambda: clock["now"],
        cursor_path=cursor_path,
    )
    snapshot = reloaded.snapshot()
    assert snapshot["cursor"]["sweeps_completed_total"] == 2
    assert snapshot["last_successful_sweep_end_utc"] is not None
    assert snapshot["cursor_durable"] is True


def test_live_helius_and_dex_discovery_of_the_same_mint_stay_one_candidate():
    """Matrix item 25: one mint, two sources, one watch entry."""

    mint = FUNNEL_PAIRS[5][0]
    watchlist = Watchlist(max_size=8)
    entry, outcome = _seed_helius_candidate(watchlist, mint)
    assert outcome == "ADMITTED"

    dex_candidate, reason = _build_candidate(
        age_seconds=300, mint=mint,
        pair="DualDiscoveryPairAddress1111111111111111111")
    assert reason == "ACCEPTED"
    dup_entry, dup_outcome = watchlist.seed_with_outcome(
        dex_candidate, seeded_at_utc=NOW)
    assert dup_outcome == "EXISTING"
    assert dup_entry is entry
    assert len(watchlist.active_entries()) == 1
    # The DEX rediscovery corroborates; first provenance never changes.
    assert entry.discovery_provenance == "LIVE_HELIUS"
    assert "DEXSCREENER_RESTART_BACKFILL" in entry.corroborating_sources


# ---------------------------------------------------------------------------
# B. hydration + tier semantics (matrix items 27..32)
# ---------------------------------------------------------------------------


def test_hydration_restores_post_migration_ath_and_current_tier(tmp_path):
    """Matrix items 27-31: migration-anchored OHLCV hydration feeds normal
    ATH/drawdown/tier evaluation; one current tier, no historical replay."""

    mint = "HydratedBackfillCandidateMint11111111111pump"
    candidate, reason = _build_candidate(age_seconds=5580, mint=mint)
    assert reason == "ACCEPTED"
    migration_time = candidate["migration_time_utc"]
    assert candidate["quote_mint"] == (
        "So11111111111111111111111111111111111111112")

    ath = CentralAthStateStore(tmp_path)
    # The session registers the pool at admission with the MIGRATION time --
    # the anchor the creation-anchored OHLCV refresh pages from.
    assert ath.register_pool(
        mint=mint,
        pool_address=candidate["pair_address"],
        quote_mint=candidate["quote_mint"],
        creation_timestamp=migration_time,
    )
    assert ath.pool_created_at(mint) == migration_time

    migration_epoch = BASE_EPOCH - 5580
    # What this process can observe on its own after admission: the current
    # (post-dip) market only.  Without hydration this would be the entire
    # "ATH" -- zero drawdown, no tier, the exact defect being remediated.
    assert ath.observe_provider_current(
        mint=mint, price_usd="0.000025",
        observed_at=BASE_EPOCH,
        market_cap_usd="25000",
        supply_at_observation="1000000000",
        confirmed=True,
    )
    unhydrated = ath.snapshot(mint)
    assert project_closed_tier(
        ath_market_cap_usd=unhydrated["ath_market_cap"],
        current_market_cap_usd="25000",
    ) == (None, "0")

    # Bounded historical hydration: the complete-window OHLCV high sits
    # BEFORE this process ever observed the mint (40 minutes after
    # migration), with evidence timestamps and source identity retained.
    assert ath.observe_ohlcv_high(
        mint=mint, high_price_usd="0.00010",
        candle_timestamp=migration_epoch + 2400,
        history_complete=True, interval="1m",
        time_from_unix=int(migration_epoch),
        time_to_unix=int(BASE_EPOCH),
    )
    snapshot = ath.snapshot(mint)
    assert snapshot is not None
    assert Decimal(str(snapshot["ath_price"])) == Decimal("0.00010")
    assert snapshot["price_provenance"]["provider"] == "PAID_OHLCV_HIGH"
    coverage = snapshot.get("ohlcv_coverage") or {}
    assert coverage.get("history_complete") is True
    assert coverage.get("time_from_unix") == int(migration_epoch)

    # Matrix items 28-31: drawdown from the RESTORED ath (pump supply is the
    # invariant 1e9 already codified as PHX1_SUPPLY), one current-tier
    # verdict, no per-crossing replay.  100k -> 25k = 75% drawdown = Tier 2
    # exactly once, even though the path history crossed the Tier 1 band on
    # the way down.
    hydrated_ath_mc = Decimal(str(snapshot["ath_price"])) * PHX1_SUPPLY
    assert hydrated_ath_mc == Decimal("100000.00000")
    tier, drawdown = project_closed_tier(
        ath_market_cap_usd=hydrated_ath_mc, current_market_cap_usd="25000")
    assert tier == "Tier 2"
    assert Decimal(drawdown) == Decimal("75")
    # State-based evaluation: exactly one tier token per current state; a
    # historical crossing has no event to replay.
    assert project_closed_tier(
        ath_market_cap_usd=hydrated_ath_mc, current_market_cap_usd="45000",
    )[0] == "Tier 1"


def test_missing_market_evidence_is_an_explicit_retryable_pending_state(
        tmp_path):
    mint = "PendingBackfillCandidateMint111111111111pump"
    candidate, reason = _build_candidate(age_seconds=3060, mint=mint)
    assert reason == "ACCEPTED"

    ath = CentralAthStateStore(tmp_path)
    assert ath.register_pool(
        mint=mint,
        pool_address=candidate["pair_address"],
        quote_mint=candidate["quote_mint"],
        creation_timestamp=candidate["migration_time_utc"],
    )
    # OHLCV answered incompletely: the coverage state says so explicitly and
    # nothing is fabricated -- no ATH value is invented from thin air.
    assert ath.record_ohlcv_coverage(
        mint=mint, interval="1m",
        time_from_unix=int(BASE_EPOCH - 3060),
        time_to_unix=int(BASE_EPOCH),
        history_complete=False, pages=1,
    )
    assert ath.snapshot(mint) is None

    # The candidate itself stays an active, retryable watch entry.
    watchlist = Watchlist(max_size=8)
    entry, outcome = watchlist.seed_with_outcome(
        candidate, seeded_at_utc=NOW)
    assert outcome == "ADMITTED"
    assert entry.is_active()
    # A valid backfill candidate seeds with its inferred migration baseline
    # already captured, so its explicit pending state is the pre-activation
    # watch (never a terminal, never a discard).
    assert entry.status == "PENDING_1_20X"

    # The bounded retry later completes: hydration lands, evidence appears.
    assert ath.observe_provider_current(
        mint=mint, price_usd="0.00003", observed_at=BASE_EPOCH + 60,
        market_cap_usd="30000", supply_at_observation="1000000000",
        confirmed=True,
    )
    assert ath.observe_ohlcv_high(
        mint=mint, high_price_usd="0.00008",
        candle_timestamp=BASE_EPOCH - 1800,
        history_complete=True, interval="1m",
        time_from_unix=int(BASE_EPOCH - 3060),
        time_to_unix=int(BASE_EPOCH + 60),
    )
    recovered = ath.snapshot(mint)
    assert recovered is not None
    assert (recovered.get("ohlcv_coverage") or {}).get(
        "history_complete") is True


# ---------------------------------------------------------------------------
# B. failure isolation + closed-set status (matrix item 33)
# ---------------------------------------------------------------------------


def test_backfill_failure_is_isolated_bounded_and_recoverable(tmp_path):
    clock = {"now": BASE_EPOCH}
    mode = {"fail": True}

    def factory():
        if mode["fail"]:
            raise RuntimeError("synthetic constructor outage")
        # A pair still inside the six-hour window AT the recovery sweep's
        # clock (five minutes old at that moment).
        return _FakeDexClient([_dex_pair(
            created_ms=int((clock["now"] - 300) * 1000))])

    backfill = DexRestartBackfill(
        client_factory=factory,
        now_fn=lambda: clock["now"],
        cursor_path=tmp_path / "dex_backfill_cursor.json",
    )
    assert backfill.snapshot()["operational_state"] == (
        BACKFILL_STATE_STARTING)

    started, _ = _run_sweep_and_wait(backfill, EPOCH_ID)
    assert started
    assert backfill.snapshot()["operational_state"] == (
        BACKFILL_STATE_DEGRADED)

    # Bounded failure backoff: the next attempt is NOT_DUE until the
    # stretched interval elapses; a failing backfill can never spin.
    clock["now"] = BASE_EPOCH + 181.0
    started, reason = backfill.maybe_schedule_periodic(EPOCH_ID)
    assert started is False and reason == "NOT_DUE"

    for attempt in range(1, FAILED_SWEEP_THRESHOLD):
        clock["now"] = BASE_EPOCH + attempt * 4000.0
        started, _ = _run_sweep_and_wait(backfill, EPOCH_ID)
        assert started
    snapshot = backfill.snapshot()
    assert snapshot["consecutive_failed_sweeps"] == FAILED_SWEEP_THRESHOLD
    assert snapshot["operational_state"] == BACKFILL_STATE_FAILED
    # The failure stays inside the backfill owner: no exception escaped, the
    # candidate queue is intact, the cursor never advanced on a failure.
    assert backfill.drain() == []
    assert snapshot["cursor"]["sweeps_completed_total"] == 0

    # Recovery: one healthy sweep returns the owner to HEALTHY.
    mode["fail"] = False
    clock["now"] = BASE_EPOCH + 90_000.0
    started, _ = _run_sweep_and_wait(backfill, EPOCH_ID)
    assert started
    snapshot = backfill.snapshot()
    assert snapshot["operational_state"] == BACKFILL_STATE_HEALTHY
    assert snapshot["consecutive_failed_sweeps"] == 0
    assert len(backfill.drain()) == 1


def test_operator_status_distinguishes_disabled_starting_and_unavailable():
    assert dex_backfill_status_text(None, enabled=False) == "DISABLED"
    assert dex_backfill_status_text(None, enabled=True) == "STARTING"
    assert dex_backfill_status_text(None) == "UNAVAILABLE"
    assert dex_backfill_status_text({"status": "NOT_RUN"}) == "STARTING"
    assert dex_backfill_status_text(
        {"status": "DEX_BACKFILL_SUCCESS",
         "operational_state": "HEALTHY"}) == "SUCCESS"
    degraded = dex_backfill_status_text(
        {"status": "DEX_BACKFILL_PARTIAL",
         "operational_state": "DEGRADED",
         "sources_failed": ["SOL_PRICE"]})
    assert degraded == "DEGRADED: PARTIAL (lost: SOL_PRICE)"


# ---------------------------------------------------------------------------
# B. retired paths stay retired (matrix items 34, 35, 36)
# ---------------------------------------------------------------------------


def test_historical_replay_stays_disabled_and_chainstack_stays_out():
    assert _CANONICAL_SEMANTIC_POLICY[
        "historical_rpc_backfill_enabled_binding"] is False
    assert _CANONICAL_SEMANTIC_POLICY[
        "dexscreener_restart_backfill_enabled_binding"] is True

    argv = canonical_launcher_arguments(
        launcher="launch_pressure_24h_01.ps1",
        expected_head="a" * 40,
        ledger_baseline=("b" * 64) + ":2928:8",
    )
    assert not any(token.startswith("--rpc-recovery-") for token in argv)
    assert not any(token.startswith("--chainstack") for token in argv)
    assert argv.count("--enable-dexscreener-restart-backfill") == 1
    verdict = validate_launcher_arguments(
        argv + ["--rpc-recovery-commitment", "confirmed"],
        expected_head="a" * 40)
    assert "LAUNCHER_HISTORICAL_RPC_FLAG_PRESENT" in verdict.refusals


def test_helius_http_remains_the_only_live_source_gap_recovery_path():
    selection = helius_source.load_source_selection(
        {"PHX2_MIGRATION_SOURCE_MODE": "HELIUS_PRIMARY"})
    plan = helius_source.build_production_source_runtime_plan(
        selection, http_recovery_enabled=True)
    assert plan.recovery_authority == "HELIUS_HTTP"
    assert plan.construct_helius_http_recovery is True
    assert plan.construct_chainstack_source is False
    assert plan.construct_chainstack_grpc_channel is False
    assert plan.construct_chainstack_comparator is False
    assert plan.resolve_chainstack_credentials is False
    projection = plan.status_projection()
    assert projection["chainstack_configured_for_runtime"] is False
    assert projection["primary_recovery"] == "HELIUS_HTTP"


# ---------------------------------------------------------------------------
# B. backfill candidate reaches fake delivery (matrix item 40)
# ---------------------------------------------------------------------------


def test_backfill_candidate_reaches_fake_delivery_reservation_and_commit(
        monkeypatch):
    transport = FakeTelegramTransport()
    composed = []
    attempts = []
    adapter = TelegramDeliveryAdapter(
        transport, compose_sink=composed.append,
        attempt_sink=attempts.append, console_sink=None)
    monkeypatch.setattr(
        compose_send, "compose_no_send_dispatch_deduped",
        lambda *args, **kwargs: _deduped(),
    )
    guard = make_stage30_11_16_real_private_transport_guard(
        transport=adapter)
    context = _delivery_context()
    assert context["candidate"]["discovery_provenance"] == (
        "DEXSCREENER_RESTART_BACKFILL")
    result = compose_send.compose_and_maybe_send(
        SimpleNamespace(token_mint=DELIVERY_MINT), ath_transport=None,
        ath_endpoint_secret=None, now_utc=None, now_seconds=None,
        ledger=object(), guard=guard,
        authorization=default_real_send_authorization(
            created_at_utc=DELIVERY_CREATED),
        created_at_utc=DELIVERY_CREATED, axiom_fee_appender=adapter,
        activation_proof=context["activation"], security_decision=None,
        delivery_context=context,
    )
    assert result["eligible"] is True
    assert result["send_result"].transport_attempted is True
    assert result["send_result"].transport_ok is True
    assert len(transport.messages) == 1
    assert composed[0]["discovery_provenance"] == (
        "DEXSCREENER_RESTART_BACKFILL")
    assert composed[0]["ath_coverage"] == "PARTIAL_SINCE_ADMISSION"
    assert attempts[0]["result"] == SENT_OK

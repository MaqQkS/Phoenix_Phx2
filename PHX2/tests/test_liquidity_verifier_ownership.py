from __future__ import annotations

import threading
import time
from types import SimpleNamespace

import pytest

from PHX2.free_tier_producer import free_tier_session as producer_session
from PHX2.free_tier_producer import liquidity_verifier as liquidity_verifier_module
from PHX2.free_tier_producer import paid_grpc_source as paid_grpc_source_module
from PHX2.free_tier_producer.ath_state import CentralAthStateStore
from PHX2.free_tier_producer.liquidity_integrity import LiquidityIntegrityIndex
from PHX2.free_tier_producer.liquidity_verifier import (
    VERIFIER_STATUS_AUTH_FAILED,
    LiquidityYellowstoneSource,
    SingleLiquidityVerifier,
    build_live_liquidity_source_factory,
    combined_stream_snapshot,
)
from PHX2.free_tier_producer.paid_provider import (
    ProviderCandidateDedupe,
    SingleGrpcPumpSwapDiscovery,
)
from PHX2.free_tier_producer.phx1_fee_gate import FeeEvidenceIndex
from PHX2.free_tier_producer.paid_grpc_source import REFUSAL_NONE
from PHX2.free_tier_producer.market_credential_check import (
    MARKET_CREDENTIAL_PROBE_MINT,
)
from PHX2.stage29.birdeye_constants import BIRDEYE_PATH_PRICE
from PHX2.stage29.stage29_2_birdeye_models import BIRDEYE_REFUSAL_REASON_NONE


def _wait(predicate, timeout=2.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.005)
    raise AssertionError("timed_out_waiting_for_verifier_state")


class _BlockingSource:
    def __init__(self, name="blocking", log=None):
        self.name = name
        self.log = log if log is not None else []
        self.entered = threading.Event()
        self.closed = threading.Event()
        self.last_refusal_reason = REFUSAL_NONE

    def iter_events(self, *, max_events):
        self.log.append("enter:" + self.name)
        self.entered.set()
        while not self.closed.wait(0.005):
            if False:
                yield None

    def close(self):
        if not self.closed.is_set():
            self.log.append("close:" + self.name)
        self.closed.set()

    def diagnostic_snapshot(self):
        return {"sanitized_error_category": None}


class _EofSource(_BlockingSource):
    def iter_events(self, *, max_events):
        self.log.append("enter:" + self.name)
        self.entered.set()
        if False:
            yield None


class _ErrorSource(_EofSource):
    def iter_events(self, *, max_events):
        self.log.append("enter:" + self.name)
        self.entered.set()
        raise RuntimeError("withheld-test-error")
        yield  # pragma: no cover - makes this a generator

    def diagnostic_snapshot(self):
        return {"sanitized_error_category": "LOCAL_SOURCE_EXCEPTION"}


class _AuthSource(_EofSource):
    def __init__(self):
        super().__init__("auth")
        self.last_refusal_reason = "STREAM_ERROR:UNAUTHENTICATED"


def test_live_verifier_factory_passes_configured_limit_as_max_events_without_io(
        monkeypatch):
    from PHX2.stage28 import chainstack_yellowstone_grpc_readiness as readiness
    from PHX2.stage28.chainstack_yellowstone_grpc_models import MODE_PROVIDER_CONNECT_ONLY

    calls = []
    runtime = SimpleNamespace(safe_config=SimpleNamespace(max_events=1))

    def fake_build_runtime_config_from_env(**kwargs):
        calls.append(kwargs)
        return runtime

    def forbidden_network(*_args, **_kwargs):
        raise AssertionError("network transport must remain unopened")

    monkeypatch.setattr(
        readiness, "build_runtime_config_from_env", fake_build_runtime_config_from_env)
    monkeypatch.setattr(liquidity_verifier_module, "_open_channel", forbidden_network)
    monkeypatch.setattr(paid_grpc_source_module, "_open_channel", forbidden_network)

    source_factory = build_live_liquidity_source_factory()
    source = source_factory()
    verifier_owner = SingleLiquidityVerifier(
        source_factory=source_factory,
        integrity_index=LiquidityIntegrityIndex(),
    )
    primary_owner = SingleGrpcPumpSwapDiscovery(
        source_factory=lambda: forbidden_network(),
        dedupe=ProviderCandidateDedupe(),
    )

    assert calls == [{"mode": MODE_PROVIDER_CONNECT_ONLY, "max_events": 1}]
    assert runtime.safe_config.max_events == 1
    assert isinstance(source, LiquidityYellowstoneSource)
    assert source._runtime_config is runtime
    assert source._max_messages is None
    assert primary_owner.snapshot()["stream_capacity"] == 1
    assert verifier_owner.snapshot()["stream_capacity"] == 1


def test_paid_primary_startup_smoke_constructs_exactly_one_stream_owner_offline(
        tmp_path, monkeypatch):
    """Single-stream production: startup reaches the ONE primary Yellowstone
    owner and never constructs, imports, or configures the liquidity
    verifier.  (Required proofs: exactly one stream; verifier constructor
    never called in production mode.)"""
    from PHX2.stage28 import chainstack_yellowstone_grpc_readiness as readiness
    from PHX2.stage29 import stage29_2_birdeye_http_transport as birdeye_http
    from PHX2.stage29 import stage29_2_birdeye_readiness as birdeye_readiness

    class StartupBoundaryReached(Exception):
        pass

    readiness_calls = []
    owner_counts = {"primary": 0}
    transport_attempts = {"grpc": 0, "http": 0, "telegram": 0, "discord": 0,
                          "credential_probe": 0}
    owners = {}

    def fake_runtime_config(**kwargs):
        # In single-stream mode the ONLY runtime-config consumer left is the
        # primary source factory, which this smoke replaces entirely — so a
        # call here would mean a second stream was being configured.
        readiness_calls.append(kwargs)
        raise AssertionError("no second stream may build a runtime config")

    def forbidden_grpc(*_args, **_kwargs):
        transport_attempts["grpc"] += 1
        raise AssertionError("gRPC transport must remain unopened")

    class _OfflineCredentialResult:
        """Canned OK answer for the mandatory startup credential probe."""

        http_status_code = 200
        refusal_reason = BIRDEYE_REFUSAL_REASON_NONE
        body = {"success": True, "data": {"value": 1.0}}
        fetched_at_utc = "2026-07-30T19:00:00Z"

    class OfflineBirdeyeInner:
        def get(self, **kwargs):
            # The armed startup path now performs exactly ONE bounded
            # credential probe before arming the epoch.  It is stubbed here so
            # this smoke stays fully offline; every OTHER market request must
            # still remain unused.
            if str(kwargs.get("path") or "") == BIRDEYE_PATH_PRICE and str(
                (kwargs.get("query_params") or {}).get("address") or ""
            ) == MARKET_CREDENTIAL_PROBE_MINT:
                transport_attempts["credential_probe"] += 1
                return _OfflineCredentialResult()
            transport_attempts["http"] += 1
            raise AssertionError("HTTP transport must remain unused")

    class _OfflineEndpointSecret:
        def reveal_api_key(self):
            return "offline-stub-key"

        def reveal_base_url(self):
            return "https://market.invalid"

    class OfflineBirdeyeMarket:
        def __init__(self, **_kwargs):
            pass

    def forbidden_telegram(*_args, **_kwargs):
        transport_attempts["telegram"] += 1
        raise AssertionError("Telegram transport must remain unused")

    def forbidden_discord(*_args, **_kwargs):
        transport_attempts["discord"] += 1
        raise AssertionError("Discord transport must remain unused")

    real_primary_type = SingleGrpcPumpSwapDiscovery

    def build_primary_owner(**kwargs):
        owner_counts["primary"] += 1
        owner = real_primary_type(**kwargs)
        owner.start = lambda: (_ for _ in ()).throw(StartupBoundaryReached())
        owners["primary"] = owner
        return owner

    ledger_path = tmp_path / "offline-ledger.jsonl"
    out_dir = tmp_path / "offline-out"
    real_compute_baseline = producer_session.ledgerlib.compute_baseline

    def compute_test_baseline(path):
        assert str(path) == str(ledger_path)
        return real_compute_baseline(path)

    monkeypatch.setattr(producer_session.sess, "load_env_file", lambda _path: 0)
    monkeypatch.setattr(producer_session.sess, "scrub_unrelated_env", lambda: 0)
    monkeypatch.setenv(
        "PHX2_MIGRATION_SOURCE_MODE", "CHAINSTACK_PRIMARY")
    monkeypatch.setattr(producer_session.ledgerlib, "compute_baseline", compute_test_baseline)
    monkeypatch.setattr(readiness, "build_runtime_config_from_env", fake_runtime_config)
    monkeypatch.setattr(
        birdeye_readiness, "build_endpoint_secret_from_env",
        lambda: _OfflineEndpointSecret())
    monkeypatch.setattr(birdeye_http, "Stage29_2BirdeyeUrlibTransport", OfflineBirdeyeInner)
    monkeypatch.setattr(producer_session, "PaidBirdeyeMarketTransport", OfflineBirdeyeMarket)
    monkeypatch.setattr(producer_session, "TelegramTransport", forbidden_telegram)
    monkeypatch.setattr(
        producer_session.b30s, "_build_real_private_transport", forbidden_discord)
    monkeypatch.setattr(liquidity_verifier_module, "_open_channel", forbidden_grpc)
    monkeypatch.setattr(paid_grpc_source_module, "_open_channel", forbidden_grpc)
    monkeypatch.setattr(
        producer_session, "build_live_source_factory", lambda **_kwargs: forbidden_grpc)
    monkeypatch.setattr(
        producer_session, "SingleGrpcPumpSwapDiscovery", build_primary_owner)

    with pytest.raises(StartupBoundaryReached):
        producer_session.main([
            "--run",
            "--provider-mode", "paid_primary",
            "--env", str(tmp_path / "offline.env"),
            "--out-dir", str(out_dir),
            "--ledger-path", str(ledger_path),
        ])

    # The production session no longer imports the verifier module at all:
    # there is no constructor to call and no dormant connection to open.
    assert not hasattr(producer_session, "SingleLiquidityVerifier")
    assert not hasattr(producer_session, "build_live_liquidity_source_factory")
    assert not hasattr(producer_session, "combined_stream_snapshot")
    assert readiness_calls == []
    assert owner_counts == {"primary": 1}
    assert owners["primary"].snapshot()["stream_capacity"] == 1
    # Exactly ONE bounded credential probe before the epoch arms; every other
    # transport stays completely unused.
    assert transport_attempts == {
        "grpc": 0, "http": 0, "telegram": 0, "discord": 0,
        "credential_probe": 1,
    }
    assert ledger_path.exists()
    assert ledger_path.stat().st_size == 0
    assert producer_session.PRIMARY_STREAM_MAX == 1
    assert producer_session.VERIFIER_STREAM_MAX == 0
    assert producer_session.MAX_ACTIVE_STREAMS == 1


def test_verifier_role_has_one_owner_one_active_stream_and_cooperative_zero_shutdown():
    source = _BlockingSource()
    verifier = SingleLiquidityVerifier(
        source_factory=lambda: source,
        integrity_index=LiquidityIntegrityIndex(),
        reconnect_backoff_seconds=0,
    )
    verifier.start()
    _wait(source.entered.is_set)
    verifier.start()  # idempotent: cannot create a second role owner
    assert verifier.snapshot()["active_streams"] == 1
    verifier.stop(timeout_seconds=1)
    snapshot = verifier.snapshot()
    assert snapshot["active_streams"] == 0
    assert snapshot["max_active_streams"] == 1
    assert snapshot["connect_attempts"] == 1
    assert snapshot["shutdown_state"] == "COMPLETE"
    assert snapshot["cleanup_state"] == "CLEAN"
    assert snapshot["attempt_history"][0]["active_streams_after_cleanup"] == 0


def test_verifier_reconnect_closes_previous_stream_before_next_attempt():
    log = []
    first = _EofSource("first", log)
    second = _BlockingSource("second", log)
    sources = iter((first, second))
    verifier = SingleLiquidityVerifier(
        source_factory=lambda: next(sources),
        integrity_index=LiquidityIntegrityIndex(),
        reconnect_backoff_seconds=0,
    )
    verifier.start()
    _wait(second.entered.is_set)
    verifier.stop(timeout_seconds=1)
    snapshot = verifier.snapshot()
    assert log.index("close:first") < log.index("enter:second")
    assert snapshot["max_active_streams"] == 1
    assert snapshot["reconnects"] == 1
    assert [row["active_streams_after_cleanup"] for row in snapshot["attempt_history"]] == [0, 0]


def test_verifier_auth_failure_is_terminal_role_specific_and_does_not_reconnect():
    verifier = SingleLiquidityVerifier(
        source_factory=_AuthSource,
        integrity_index=LiquidityIntegrityIndex(),
        reconnect_backoff_seconds=0,
    )
    verifier.start()
    _wait(lambda: verifier.snapshot()["terminal_auth_failure"])
    snapshot = verifier.snapshot()
    assert snapshot["status"] == VERIFIER_STATUS_AUTH_FAILED
    assert snapshot["authentication_failures"] == 1
    assert snapshot["connect_attempts"] == 1
    assert snapshot["reconnects"] == 0
    assert snapshot["active_streams"] == 0
    assert snapshot["attempt_history"][0]["authentication_failure"] is True
    verifier.stop(timeout_seconds=1)


def test_verifier_watchdog_closes_stale_source_then_reconnects_without_overlap():
    first = _BlockingSource("stale")
    second = _BlockingSource("replacement")
    sources = iter((first, second))
    verifier = SingleLiquidityVerifier(
        source_factory=lambda: next(sources),
        integrity_index=LiquidityIntegrityIndex(),
        reconnect_backoff_seconds=0,
        stale_after_seconds=0.05,
    )
    verifier.start()
    _wait(second.entered.is_set)
    snapshot = verifier.snapshot()
    assert first.closed.is_set()
    assert snapshot["watchdog_reconnects"] == 1
    assert snapshot["max_active_streams"] == 1
    assert snapshot["attempt_history"][0]["watchdog_triggered"] is True
    verifier.stop(timeout_seconds=1)


def test_verifier_failure_preserves_fee_ath_and_primary_state():
    fee_index = FeeEvidenceIndex()
    ath_state = CentralAthStateStore(None)
    primary = {"active_streams": 1, "max_active_streams": 1,
               "candidate_count": 4, "fee_event_count": 9}
    before_primary = dict(primary)
    before_fee = fee_index.stats()
    before_ath = ath_state.snapshot("unchanged-mint")
    blocking = _BlockingSource("reconnected")
    sources = iter((_ErrorSource("failed"), blocking))
    verifier = SingleLiquidityVerifier(
        source_factory=lambda: next(sources),
        integrity_index=LiquidityIntegrityIndex(),
        reconnect_backoff_seconds=0,
    )
    verifier.start()
    _wait(blocking.entered.is_set)
    assert verifier.snapshot()["stream_errors"] == 1
    assert primary == before_primary
    assert fee_index.stats() == before_fee
    assert ath_state.snapshot("unchanged-mint") == before_ath
    verifier.stop(timeout_seconds=1)


def test_combined_stream_invariant_is_role_specific_and_total_two():
    combined = combined_stream_snapshot(
        {"active_streams": 1, "max_active_streams": 1},
        {"active_streams": 1, "max_active_streams": 1},
    )
    assert combined == {
        "primary_active_streams": 1,
        "verifier_active_streams": 1,
        "total_active_streams": 2,
        "primary_max_active_streams": 1,
        "verifier_max_active_streams": 1,
        "total_max_active_streams": 2,
    }

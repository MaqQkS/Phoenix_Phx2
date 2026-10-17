from __future__ import annotations

import json

from PHX2.free_tier_producer.market_plane_health import (
    MARKET_PLANE_BLIND,
    MARKET_PLANE_DEGRADED,
    MARKET_PLANE_HEALTHY,
)
from PHX2.tests.watchdog._harness import (
    FakeWorld,
    make_config,
    make_watchdog,
)
from PHX2.watchdog import operational_health as OH
from PHX2.watchdog.state import (
    CIRCUIT_OPEN_STATUS,
    CircuitState,
    load_circuit_state,
    save_circuit_state,
)


def _accounting_fields(*, provider_delta: int = 0, charge_delta: int = 0):
    return {
        "scheduler_physical_requests_total": 20,
        "transport_physical_requests_total": 20 + provider_delta,
        "reconciled_total": 20,
        "unreconciled_delta": provider_delta,
        "scheduler_charge_delta": charge_delta,
        "reconciliation_reasons": {"SCHEDULER_OWNED": 20},
    }


def _market_fields(status: str, *, age: float = 0.0, grace: float = 60.0):
    return {
        "market_plane_status": status,
        "market_plane_reasons": (
            ["MARKET_OBSERVATION_STARVED_BEYOND_BOUND"]
            if status in (MARKET_PLANE_BLIND, MARKET_PLANE_DEGRADED) else []),
        "market_plane_blind_age_seconds": age,
        "market_plane_grace_seconds": grace,
        "market_plane_active_candidate_count": 3,
    }


def _status(config):
    return json.loads(config.status_path.read_text(encoding="utf-8"))


def test_daemon_accounting_fault_is_the_status_and_control_verdict(tmp_path):
    config = make_config(tmp_path, circuit_max_restarts=3)
    world = FakeWorld(config)
    watchdog = make_watchdog(config, world)
    watchdog.run(max_cycles=1)

    world.write_heartbeat(
        world.spawns[-1].run_dir,
        **_market_fields(MARKET_PLANE_HEALTHY),
        **_accounting_fields(provider_delta=5),
    )
    result = watchdog.run(max_cycles=1)

    document = _status(config)
    assert result.final_health == OH.UNHEALTHY_REQUEST_ACCOUNTING
    assert document["health_class"] == result.final_health
    assert document["observation"]["operational_status"] == result.final_health
    assert document["observation"]["canonical_health_class"] == result.final_health
    assert document["health_control_class"] == "RESTARTABLE_PROCESS_FAILURE"
    assert len(world.spawns) == 2, (
        "accounting failure was displayed but did not reach daemon control")
    assert document["stable_since_utc"] is None


def test_persistent_market_blindness_reaches_bounded_circuit(tmp_path):
    config = make_config(
        tmp_path, circuit_max_restarts=2, circuit_window_seconds=600.0)
    world = FakeWorld(config)
    watchdog = make_watchdog(config, world)
    watchdog.run(max_cycles=1)

    outcomes = []
    for generation in range(3):
        world.write_heartbeat(
            world.spawns[-1].run_dir,
            **_market_fields(
                MARKET_PLANE_BLIND if generation == 0
                else MARKET_PLANE_DEGRADED,
                age=600 if generation == 0 else 5,
                grace=60),
            **_accounting_fields(),
        )
        outcomes.append(watchdog.run(max_cycles=1).outcome)

    circuit = load_circuit_state(config.circuit_state_path)
    assert circuit.status == CIRCUIT_OPEN_STATUS
    assert circuit.open_reason == "RESTART_BUDGET_EXHAUSTED"
    assert circuit.restart_count_total == 2
    assert len(world.spawns) == 3  # initial + two bounded replacements
    assert "CIRCUIT_OPEN" in outcomes


def test_persistent_accounting_fault_cannot_restart_forever(tmp_path):
    config = make_config(tmp_path, circuit_max_restarts=1)
    world = FakeWorld(config)
    watchdog = make_watchdog(config, world)
    watchdog.run(max_cycles=1)

    for _ in range(2):
        world.write_heartbeat(
            world.spawns[-1].run_dir,
            **_market_fields(MARKET_PLANE_HEALTHY),
            **_accounting_fields(charge_delta=1),
        )
        watchdog.run(max_cycles=1)

    circuit = load_circuit_state(config.circuit_state_path)
    assert circuit.status == CIRCUIT_OPEN_STATUS
    assert circuit.open_reason == "RESTART_BUDGET_EXHAUSTED"
    assert len(world.spawns) == 2


def test_transient_market_degradation_recovers_without_restart_or_circuit(tmp_path):
    config = make_config(tmp_path)
    world = FakeWorld(config)
    watchdog = make_watchdog(config, world)
    watchdog.run(max_cycles=1)

    world.write_heartbeat(
        world.spawns[-1].run_dir,
        **_market_fields(MARKET_PLANE_DEGRADED, age=30, grace=60),
        **_accounting_fields(),
    )
    degraded = watchdog.run(max_cycles=1)
    assert degraded.final_health == OH.DEGRADED_MARKET_PLANE
    assert len(world.spawns) == 1
    assert not load_circuit_state(config.circuit_state_path).is_open
    assert _status(config)["stable_since_utc"] is None

    world.write_heartbeat(
        world.spawns[-1].run_dir,
        **_market_fields(MARKET_PLANE_HEALTHY),
        **_accounting_fields(),
    )
    recovered = watchdog.run(max_cycles=1)
    assert recovered.final_health == OH.HEALTHY
    assert len(world.spawns) == 1
    assert not load_circuit_state(config.circuit_state_path).is_open


def test_degraded_cycles_cannot_reset_restart_stability_budget(tmp_path):
    config = make_config(
        tmp_path, stable_run_reset_seconds=60.0, poll_interval_seconds=30.0)
    world = FakeWorld(config)
    watchdog = make_watchdog(config, world)
    watchdog.run(max_cycles=1)
    save_circuit_state(config.circuit_state_path, CircuitState(
        attempts_utc=[world.now()], restart_count_total=1))

    world.write_heartbeat(
        world.spawns[-1].run_dir,
        **_market_fields(MARKET_PLANE_DEGRADED, age=10, grace=300),
        **_accounting_fields(),
    )
    original_sleep = watchdog._sleep  # noqa: SLF001

    def degraded_tick(seconds: float) -> None:
        original_sleep(seconds)
        world.write_heartbeat(
            world.spawns[-1].run_dir,
            **_market_fields(MARKET_PLANE_DEGRADED, age=10, grace=300),
            **_accounting_fields(),
        )

    watchdog._sleep = degraded_tick  # noqa: SLF001
    watchdog.run(max_cycles=5)

    circuit = load_circuit_state(config.circuit_state_path)
    assert circuit.attempts_utc != []
    assert _status(config)["stable_since_utc"] is None
    assert "RESTART_BUDGET_RESET" not in (
        config.events_path.read_text(encoding="utf-8"))


def test_no_active_candidates_market_idle_does_not_trigger_starvation():
    telemetry = {
        "transport_connected": True,
        "status": "CONNECTED",
        "source_continuity_state": "NO_GAP",
        "cursor_durability_status": "CHECKPOINT_DURABILITY_HEALTHY",
        "market_plane_status": "MARKET_PLANE_IDLE",
        "market_plane_grace_seconds": 60,
        **_accounting_fields(),
    }
    verdict = OH.evaluate_operational_health(
        telemetry=telemetry, watchlist_summary={})
    assert verdict.status == OH.HEALTHY
    assert verdict.dimension("market_plane").verdict == OH.DIM_HEALTHY

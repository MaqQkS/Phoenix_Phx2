"""PHX2 F-1: the legacy MarketSchedulerConfig schema must fail closed.

Red origin (2026-07-21): the scheduler-capacity commit displaced the legacy
TTL/SLO and backlog-fraction validation below the unconditional ``return``
inside ``effective_p1_attempt_timeout_seconds()``, so the statements became
unreachable and ``MarketSchedulerConfig`` constructed silently on invalid
values (independent scheduler re-audit finding F-1).  Every rejection and
structural test in this module failed at that starting HEAD; the pre-fix
failures are preserved in the external fix workspace
(``pre_fix_failures.txt`` / ``validation_trace_before.json``).

The restored contract, owned by ``MarketSchedulerConfig.__post_init__``:

* every field in ``TTL_SLO_CONFIG_FIELDS`` must be a finite real numeric
  strictly greater than zero;
* ``backlog_high_fraction`` must be a finite real numeric inside (0, 1];
* bool, non-numeric, non-finite and string shapes refuse deterministically
  with the closed-set tokens ``market_scheduler_ttl_invalid:<field>`` /
  ``market_scheduler_backlog_fraction_invalid``;
* the refusal happens at construction — before any provider, scheduler
  worker, channel, socket or ledger object can exist.
"""

from __future__ import annotations

import ast
import dataclasses
import inspect
from dataclasses import replace
from types import SimpleNamespace

import pytest

from PHX2.free_tier_producer import market_scheduler
from PHX2.free_tier_producer.market_scheduler import MarketSchedulerConfig

# The exact legacy field list from parent 4a062b96 (order preserved).  The
# module must export the same closed set; keeping a local copy lets every
# rejection test below fail red at the pre-fix HEAD instead of dying on an
# import error.
EXPECTED_TTL_SLO_FIELDS = (
    "price_active_ttl_seconds",
    "price_pending_ttl_seconds",
    "overview_active_ttl_seconds",
    "overview_pending_ttl_seconds",
    "grpc_max_age_seconds",
    "grpc_watch_apply_slo_seconds",
    "grpc_decision_slo_seconds",
    "activated_overview_schedule_slo_seconds",
    "recovery_schedule_slo_seconds",
    "pending_price_max_age_seconds",
    "background_starvation_seconds",
    "heartbeat_jitter_slo_seconds",
)

# Positive-only numerics: zero, negatives, bool (not an accepted numeric
# shape here), non-finite floats, and incompatible string/object shapes all
# refuse.
INVALID_POSITIVE_ONLY_VALUES = (
    0,
    0.0,
    -1,
    -5.0,
    True,
    False,
    float("nan"),
    float("inf"),
    float("-inf"),
    "12.0",
    "abc",
    None,
    (12.0,),
)

INVALID_BACKLOG_FRACTION_VALUES = (
    0,
    0.0,
    -0.25,
    -1,
    1.0000001,
    1.01,
    2,
    True,
    False,
    float("nan"),
    float("inf"),
    float("-inf"),
    "0.75",
    None,
    (0.5,),
)


def _production_config(**overrides) -> MarketSchedulerConfig:
    from PHX2.free_tier_producer.market_scheduler import (
        production_p1_scheduler_fields,
    )

    fields = dict(production_p1_scheduler_fields())
    fields.update(overrides)
    return MarketSchedulerConfig(**fields)


# --------------------------------------------------------------- rejection


@pytest.mark.parametrize("field_name", EXPECTED_TTL_SLO_FIELDS)
@pytest.mark.parametrize("bad_value", INVALID_POSITIVE_ONLY_VALUES,
                         ids=[repr(v) for v in INVALID_POSITIVE_ONLY_VALUES])
def test_each_ttl_slo_field_refuses_invalid_values(field_name, bad_value):
    with pytest.raises(
            ValueError,
            match=rf"^market_scheduler_ttl_invalid:{field_name}$"):
        MarketSchedulerConfig(**{field_name: bad_value})


@pytest.mark.parametrize("bad_value", INVALID_BACKLOG_FRACTION_VALUES,
                         ids=[repr(v) for v in INVALID_BACKLOG_FRACTION_VALUES])
def test_backlog_high_fraction_refuses_invalid_values(bad_value):
    with pytest.raises(
            ValueError,
            match=r"^market_scheduler_backlog_fraction_invalid$"):
        MarketSchedulerConfig(backlog_high_fraction=bad_value)


# ------------------------------------------------------------ valid values


@pytest.mark.parametrize("field_name", EXPECTED_TTL_SLO_FIELDS)
def test_each_ttl_slo_field_accepts_small_positive_boundary(field_name):
    config = MarketSchedulerConfig(**{field_name: 0.05})
    # Validation must never mutate a valid value.
    assert getattr(config, field_name) == 0.05


def test_all_ttl_slo_fields_accept_small_positive_values_together():
    config = MarketSchedulerConfig(
        backlog_high_fraction=1e-9,
        **{name: 0.05 for name in EXPECTED_TTL_SLO_FIELDS})
    for name in EXPECTED_TTL_SLO_FIELDS:
        assert getattr(config, name) == 0.05
    assert config.backlog_high_fraction == 1e-9


def test_backlog_high_fraction_boundaries_accepted():
    assert MarketSchedulerConfig(
        backlog_high_fraction=1e-9).backlog_high_fraction == 1e-9
    assert MarketSchedulerConfig(
        backlog_high_fraction=1.0).backlog_high_fraction == 1.0
    # A bool-free int at the upper boundary is a legitimate numeric shape.
    assert MarketSchedulerConfig(
        backlog_high_fraction=1).backlog_high_fraction == 1
    assert MarketSchedulerConfig().backlog_high_fraction == 0.75


def test_default_construction_still_valid():
    config = MarketSchedulerConfig()
    assert config.price_active_ttl_seconds == 12.0
    assert config.heartbeat_jitter_slo_seconds == 5.0
    assert config.backlog_high_fraction == 0.75


def test_bool_free_int_ttl_values_accepted():
    config = MarketSchedulerConfig(grpc_max_age_seconds=15)
    assert config.grpc_max_age_seconds == 15


def test_production_defaults_construct_and_capacity_result_unchanged():
    """The restored validation must not move the 128-candidate bound."""

    from PHX2.free_tier_producer.market_scheduler import evaluate_p1_capacity

    config = _production_config(max_active_candidates=128)
    assert config.worker_count == 16
    assert config.provider_min_interval_seconds == 0.09
    assert config.healthy_response_budget_seconds == 1.5
    assert config.dispatch_overhead_budget_seconds == 0.5
    verdict = evaluate_p1_capacity(config, active_candidates=128)
    assert verdict["p1_capacity_achievable"] is True
    assert verdict["calculated_worst_case_bound_seconds"] == 13.85
    assert verdict["configured_concurrency"] == 16
    assert verdict["request_start_spacing_seconds"] == 0.09
    assert verdict["required_deadline_seconds"] == 15.0


# ------------------------------------------------------- structural guards


def _config_class_node() -> ast.ClassDef:
    tree = ast.parse(inspect.getsource(market_scheduler))
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "MarketSchedulerConfig":
            return node
    raise AssertionError("MarketSchedulerConfig class not found")


def test_ttl_slo_closed_set_is_exported_and_exact():
    exported = getattr(market_scheduler, "TTL_SLO_CONFIG_FIELDS", None)
    assert exported == EXPECTED_TTL_SLO_FIELDS
    declared = {field.name for field in dataclasses.fields(MarketSchedulerConfig)}
    assert set(EXPECTED_TTL_SLO_FIELDS) <= declared
    assert "backlog_high_fraction" in declared


def test_post_init_owns_the_legacy_validation():
    source = inspect.getsource(MarketSchedulerConfig.__post_init__)
    assert "market_scheduler_ttl_invalid" in source
    assert "market_scheduler_backlog_fraction_invalid" in source
    assert "TTL_SLO_CONFIG_FIELDS" in source


def test_effective_p1_attempt_timeout_has_no_validation_block():
    method_source = inspect.getsource(
        MarketSchedulerConfig.effective_p1_attempt_timeout_seconds)
    assert "market_scheduler_ttl_invalid" not in method_source
    assert "market_scheduler_backlog_fraction_invalid" not in method_source
    for node in _config_class_node().body:
        if (isinstance(node, ast.FunctionDef)
                and node.name == "effective_p1_attempt_timeout_seconds"):
            assert not any(isinstance(inner, (ast.For, ast.Raise))
                           for inner in ast.walk(node))
            assert isinstance(node.body[-1], ast.Return)
            break
    else:
        raise AssertionError("effective_p1_attempt_timeout_seconds not found")


def test_no_statement_follows_an_unconditional_terminator_in_config_class():
    """The F-1 defect shape: statements after return/raise in one block."""

    violations = []
    for child in ast.walk(_config_class_node()):
        for attribute in ("body", "orelse", "finalbody"):
            block = getattr(child, attribute, None)
            if not (isinstance(block, list) and block
                    and isinstance(block[0], ast.stmt)):
                continue
            for index, statement in enumerate(block):
                if (isinstance(statement, (ast.Return, ast.Raise))
                        and index < len(block) - 1):
                    violations.append(
                        f"line {statement.lineno}: unreachable statements "
                        f"start at line {block[index + 1].lineno}")
    assert violations == [], violations


# ------------------------------------------- startup fail-closed (Phase 4)


@pytest.fixture
def _no_socket(monkeypatch):
    import socket as socket_module

    def _forbidden(*_args, **_kwargs):
        raise AssertionError(
            "socket construction attempted during startup config validation")

    monkeypatch.setattr(socket_module, "socket", _forbidden)


@pytest.fixture
def _construction_spies(monkeypatch):
    """Record provider/scheduler/ledger construction during the refusal."""

    from PHX2.free_tier_producer.market_scheduler import MarketScheduler
    from PHX2.free_tier_producer.paid_birdeye import PaidBirdeyeMarketTransport
    from PHX2.stage30.stage30_11_15_ping_dedupe_ledger import (
        JsonlPingDedupeLedger,
    )

    constructed = []

    def _spy(label, original):
        def _record(self, *args, **kwargs):
            constructed.append(label)
            return original(self, *args, **kwargs)

        return _record

    monkeypatch.setattr(
        MarketScheduler, "__init__",
        _spy("scheduler_worker", MarketScheduler.__init__))
    monkeypatch.setattr(
        PaidBirdeyeMarketTransport, "__init__",
        _spy("provider_transport", PaidBirdeyeMarketTransport.__init__))
    monkeypatch.setattr(
        JsonlPingDedupeLedger, "__init__",
        _spy("ledger", JsonlPingDedupeLedger.__init__))
    return constructed


def _real_session_args(argv):
    import argparse

    from PHX2.free_tier_producer import free_tier_session

    parser = argparse.ArgumentParser()
    free_tier_session._add_args(parser)
    return free_tier_session, parser.parse_args(argv)


def test_startup_config_validation_precedes_every_construction_site():
    """Source order: the config-validating preflight runs first in paid mode."""

    from PHX2.free_tier_producer import free_tier_session

    source = inspect.getsource(free_tier_session)
    capacity_at = source.index(
        "capacity_verdict = evaluate_session_p1_capacity(args)")
    transport_at = source.index("Stage29_2BirdeyeUrlibTransport()")
    ledger_at = source.index("JsonlPingDedupeLedger(path=ledger_path)")
    grpc_at = source.index("paid_discovery.start()")
    assert capacity_at < transport_at < ledger_at < grpc_at, (
        "config validation must run before the provider transport, the "
        "durable ledger, and the gRPC owner ever exist")


@pytest.mark.parametrize("argv, field_name", [
    (["--market-price-active-ttl-seconds", "-5"],
     "price_active_ttl_seconds"),
    (["--market-grpc-max-age-seconds", "-1"],
     "grpc_max_age_seconds"),
    (["--market-overview-active-ttl-seconds", "nan"],
     "overview_active_ttl_seconds"),
    (["--market-background-starvation-seconds", "0"],
     "background_starvation_seconds"),
])
def test_startup_refuses_invalid_operator_flags_before_construction(
        argv, field_name, _no_socket, _construction_spies):
    """The real argparse surface + the real preflight helper fail closed."""

    free_tier_session, args = _real_session_args(argv)
    with pytest.raises(
            ValueError,
            match=rf"^market_scheduler_ttl_invalid:{field_name}$"):
        free_tier_session.evaluate_session_p1_capacity(args)
    assert _construction_spies == []


def test_startup_refuses_invalid_backlog_fraction_at_schema_layer(
        _no_socket, _construction_spies):
    """``backlog_high_fraction`` has no operator flag in the production
    builder (it keeps the 0.75 default), so its fail-closed proof drives the
    shared schema layer on the REAL production-built config object."""

    free_tier_session, args = _real_session_args([])
    config = free_tier_session.build_production_market_scheduler_config(args)
    assert config.backlog_high_fraction == 0.75
    for bad_fraction in (0.0, 1.01):
        with pytest.raises(
                ValueError,
                match=r"^market_scheduler_backlog_fraction_invalid$"):
            replace(config, backlog_high_fraction=bad_fraction)
    assert _construction_spies == []


def test_startup_capacity_preflight_still_passes_production_defaults(
        _no_socket, _construction_spies):
    free_tier_session, args = _real_session_args([])
    verdict = free_tier_session.evaluate_session_p1_capacity(args)
    assert verdict["p1_capacity_achievable"] is True
    assert verdict["calculated_worst_case_bound_seconds"] == 13.85
    assert verdict["configured_concurrency"] == 16
    assert verdict["request_start_spacing_seconds"] == 0.09
    assert _construction_spies == []


def test_session_layer_and_direct_construction_share_one_validation_path():
    """SimpleNamespace args reaching the session builder hit the same
    ``__post_init__`` contract as direct construction — one validation path,
    no session-side clamp."""

    from PHX2.free_tier_producer import free_tier_session

    namespace = SimpleNamespace(
        market_provider_spacing_seconds=0.09,
        market_provider_concurrency=16,
        market_scheduler_workers=None,
        market_scheduler_max_inflight=None,
        market_scheduler_queue_size=256,
        birdeye_min_interval_seconds=None,
        market_p1_deadline_seconds=15.0,
        market_healthy_response_budget_seconds=1.5,
        market_dispatch_overhead_budget_seconds=0.5,
        market_p1_max_attempts=2,
        market_p1_request_timeout_seconds=8.0,
        market_p1_reserved_workers=2,
        max_watchlist_size=128,
        max_market_requests_total=200000,
        market_price_active_ttl_seconds=12.0,
        market_price_pending_ttl_seconds=30.0,
        market_overview_active_ttl_seconds=30.0,
        market_overview_pending_ttl_seconds=90.0,
        market_grpc_max_age_seconds=-1.0,
        market_background_starvation_seconds=120.0,
    )
    with pytest.raises(
            ValueError,
            match=r"^market_scheduler_ttl_invalid:grpc_max_age_seconds$"):
        free_tier_session.build_production_market_scheduler_config(namespace)

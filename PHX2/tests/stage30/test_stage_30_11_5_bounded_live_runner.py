"""Stage 30.11.5 bounded live runner tests.

Proves the bounded runner composes the source -> assembler -> committed Stage
30.11.2 seam -> committed Stage 30.11.3 private sink -> injected transport adapter
under HARD caps: it fails closed on an out-of-cap config (``max_dispatches`` above
1, ``max_runtime_seconds`` above 60, ``max_candidates`` above 10, or an invalid
base config), drives EXACTLY one transport would-deliver for the PASS dip ONLY
(the non-dip suppressed by the dip gate, the bridge-suppressed by the bridge, the
invalid candidate rejected by the assembler -- none reaches the transport), bounds
the source pull at ``max_candidates``, and stops cleanly on the injected
wall-clock bound.

Fake / offline only. No live call, no provider, no Discord, no env read, no real
transport.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Dict

import pytest

from PHX2.stage30.stage30_11_2_fake_runtime_gate_proof import (
    make_constant_clock,
    make_sequence_clock,
)
from PHX2.stage30.stage30_11_2_runtime_gate_models import (
    Stage30_11RuntimeGateConfig,
)
from PHX2.stage30.stage30_11_5_bounded_live_runner import (
    Stage30_11_5BoundedLiveRunnerError,
    default_bounded_run_config,
    is_within_bounded_run_caps,
    run_stage30_11_5_bounded_live_runner,
)
from PHX2.stage30.stage30_11_5_fake_live_wiring_proof import (
    Stage30_11_5RecordingFakeTransportClient,
    default_fake_live_wiring_source,
)


_CREATED_AT = "2026-01-01T00:00:00Z"


def _run(source, *, client=None, now_seconds=None, config=None):
    effective_client = client or Stage30_11_5RecordingFakeTransportClient(
        created_at_utc=_CREATED_AT
    )
    clock = now_seconds or make_constant_clock(Decimal(0))
    result = run_stage30_11_5_bounded_live_runner(
        source,
        transport_client=effective_client,
        now_seconds=clock,
        config=config,
        created_at_utc=_CREATED_AT,
    )
    return result, effective_client


def _config(*, dispatches=1, runtime=Decimal(60), candidates=10):
    return Stage30_11RuntimeGateConfig(
        max_runtime_seconds=runtime,
        max_candidates=candidates,
        max_dispatches=dispatches,
        created_at_utc=_CREATED_AT,
    )


# ---------------------------------------------------------------------------
# Config caps
# ---------------------------------------------------------------------------


def test_default_config_is_within_caps() -> None:
    config = default_bounded_run_config(created_at_utc=_CREATED_AT)
    assert config.max_dispatches == 1
    assert config.max_runtime_seconds == Decimal(60)
    assert config.max_candidates == 10
    assert is_within_bounded_run_caps(config)


def test_is_within_bounded_run_caps_rejects_out_of_cap() -> None:
    assert not is_within_bounded_run_caps(_config(dispatches=2))
    assert not is_within_bounded_run_caps(_config(runtime=Decimal(61)))
    assert not is_within_bounded_run_caps(_config(candidates=11))
    # Invalid base configs fail closed too.
    assert not is_within_bounded_run_caps(_config(candidates=0))
    assert not is_within_bounded_run_caps(_config(runtime=Decimal(0)))
    assert not is_within_bounded_run_caps(object())
    assert not is_within_bounded_run_caps(None)


def test_runner_raises_on_out_of_cap_config_and_dispatches_nothing() -> None:
    for bad in (
        _config(dispatches=2),
        _config(runtime=Decimal(61)),
        _config(candidates=11),
    ):
        client = Stage30_11_5RecordingFakeTransportClient(
            created_at_utc=_CREATED_AT
        )
        with pytest.raises(Stage30_11_5BoundedLiveRunnerError):
            run_stage30_11_5_bounded_live_runner(
                default_fake_live_wiring_source(),
                transport_client=client,
                now_seconds=make_constant_clock(Decimal(0)),
                config=bad,
                created_at_utc=_CREATED_AT,
            )
        # Nothing was dispatched on the out-of-cap config.
        assert client.attempted == 0


# ---------------------------------------------------------------------------
# The composed bounded run: dip reaches transport ONLY
# ---------------------------------------------------------------------------


def test_default_source_reaches_transport_for_the_dip_only() -> None:
    result, client = _run(default_fake_live_wiring_source())
    s = result.summary
    assert s.source_items_seen == 4
    assert s.assembled == 3
    assert s.assembly_rejected == 1
    assert s.candidates_seen == 3
    assert s.bridged == 2
    assert s.gate_passed == 1
    assert s.dispatch_attempted == 1
    assert s.dispatch_accepted == 1
    assert s.suppressed_by_bridge == 1
    assert s.suppressed_by_gate == 1
    assert s.stopped_by_candidate_cap == 0
    assert s.stopped_by_dispatch_cap == 0
    assert s.stopped_by_runtime_seconds == 0
    # The fake transport client recorded EXACTLY one would-deliver -- the dip.
    assert client.attempted == 1
    assert client.accepted == 1
    assert client.candidate_ids == ["cand-tier1"]
    assert client.token_mints == ["mint-tier1"]


def test_non_dip_and_bridge_skip_and_invalid_never_reach_transport() -> None:
    result, client = _run(default_fake_live_wiring_source())
    # The transport saw ONLY the dip identity.
    assert set(client.candidate_ids) == {"cand-tier1"}
    assert "cand-unknown" not in client.candidate_ids  # non-dip
    assert "cand-no-ath" not in client.candidate_ids  # bridge-suppressed
    assert "cand-invalid" not in client.candidate_ids  # assembler-rejected
    # The assembler-rejected candidate is in the assembly outcomes but produced
    # no snapshot.
    rejected = [
        a for a in result.assembly_outcomes if a.snapshot is None
    ]
    assert len(rejected) == 1
    assert rejected[0].candidate_id == "cand-invalid"


def test_invalid_candidate_alone_reaches_no_transport() -> None:
    invalid: Dict[str, object] = {
        "candidate_id": "cand-bad",
        "token_mint": "mint-bad",
        "pair_type": "SOL",
        "tier_hint": "Tier 1",
        "drawdown_from_ath": "0.55",
        "migration_status": "PRESENT",
        "ath_status": "PRESENT",
        "market_context_status": "PRESENT",
        # current_market_cap_usd omitted -> assembler rejects.
        "created_at_utc": _CREATED_AT,
    }
    result, client = _run((invalid,))
    assert result.summary.assembled == 0
    assert result.summary.assembly_rejected == 1
    assert result.summary.candidates_seen == 0
    assert client.attempted == 0


# ---------------------------------------------------------------------------
# Bounds: source pull + wall-clock stop
# ---------------------------------------------------------------------------


def test_source_pull_is_bounded_by_max_candidates() -> None:
    # A source longer than max_candidates is pulled only up to the cap.
    dip = {
        "candidate_id": "cand-unknown",
        "token_mint": "mint-unknown",
        "pair_type": "SOL",
        "tier_hint": "Tier Unknown",
        "drawdown_from_ath": "0.55",
        "migration_status": "PRESENT",
        "ath_status": "PRESENT",
        "market_context_status": "PRESENT",
        "current_market_cap_usd": "12345.67",
        "created_at_utc": _CREATED_AT,
    }
    long_source = tuple(dict(dip) for _ in range(25))
    result, client = _run(long_source, config=_config(candidates=10))
    assert result.summary.source_items_seen == 10
    assert result.summary.assembled == 10
    # All non-dips -> no transport.
    assert client.attempted == 0


def test_injected_wall_clock_bound_stops_the_run() -> None:
    # A sequence clock that jumps past max_runtime_seconds after the first sample
    # stops the run before any candidate is evaluated.
    source = default_fake_live_wiring_source()
    clock = make_sequence_clock((Decimal(0), Decimal(999)))
    result, client = _run(source, now_seconds=clock)
    assert result.summary.stopped_by_runtime_seconds == 1
    assert client.attempted == 0


def test_runner_uses_default_config_when_none() -> None:
    result, client = _run(default_fake_live_wiring_source(), config=None)
    # The default config drives the baseline (one dip would-deliver).
    assert result.summary.dispatch_attempted == 1
    assert client.attempted == 1

"""Armed-production gRPC configuration contract.

The 2026-07-20 re-audit's second HIGH finding was that no launch path reachable
by the operator executed the cursor-aware code at all.  These tests pin the
contract that makes that state unreachable: an armed run either executes the
tracked repository gRPC path with a stable durable cursor, or it refuses to
start.

Offline and structural only: no socket, no provider, no ``.env``, no
credential, no real ledger, and no live process.
"""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from PHX2.free_tier_producer import production_grpc_contract as pgc
from PHX2.free_tier_producer.paid_provider import (
    PROVIDER_MODE_FREE_TIER,
    PROVIDER_MODE_PAID_PRIMARY,
    PROVIDER_MODE_PAID_WITH_FALLBACK,
    adapt_zero_argument_factory_TEST_ONLY,
)

PAID_MODES = (PROVIDER_MODE_PAID_PRIMARY, PROVIDER_MODE_PAID_WITH_FALLBACK)

REPO_ROOT = Path(__file__).resolve().parents[2]
STABLE_STATE_DIR = r"C:\Users\BalaC\phx2_production_private_live\state"
RUN_DIR = r"C:\Users\BalaC\phx2_production_private_live\out\prod_live_soak_02h_01"


def _cursor_aware_factory(*, from_slot=None, cursor=None,
                          downstream_durable_fn=None, stream_generation=0):
    return SimpleNamespace()


def _healthy_cursor():
    return SimpleNamespace(quarantined=False,
                           subscription_identity_matches=True)


def _evaluate(**overrides):
    kwargs = dict(
        provider_mode=PROVIDER_MODE_PAID_PRIMARY,
        paid_provider_modes=PAID_MODES,
        cursor_store=_healthy_cursor(),
        cursor_state_dir=STABLE_STATE_DIR,
        out_dir=RUN_DIR,
        source_factory=_cursor_aware_factory,
        discovery_mode="polling",
        fallback_discovery_enabled=False,
        expected_head=None,
    )
    kwargs.update(overrides)
    return pgc.evaluate_production_grpc_contract(**kwargs)


# ---------------------------------------------------------------------------
# the allowed configuration
# ---------------------------------------------------------------------------

def test_the_canonical_production_configuration_is_allowed():
    verdict = _evaluate()
    assert verdict.allowed is True
    assert verdict.refusals == []
    assert verdict.checks["provider_mode_is_paid_grpc"] is True
    assert verdict.checks["cursor_store_present"] is True
    assert verdict.checks["source_factory_is_cursor_aware"] is True
    assert verdict.checks["cursor_state_dir_ephemeral"] is False
    assert verdict.checks["cursor_state_dir_is_run_dir"] is False
    assert verdict.checks["legacy_websocket_discovery_selected"] is False
    assert verdict.checks["fallback_discovery_enabled"] is False


def test_a_changed_run_directory_does_not_change_the_cursor_directory():
    """Run artifacts rotate per run; the durable resume position must not."""

    for run_dir in (RUN_DIR, RUN_DIR + "_02", RUN_DIR + "_03"):
        verdict = _evaluate(out_dir=run_dir)
        assert verdict.allowed is True
        assert verdict.checks["cursor_state_dir_is_run_dir"] is False


# ---------------------------------------------------------------------------
# every fail-closed rule
# ---------------------------------------------------------------------------

def test_free_tier_mode_is_refused_for_an_armed_production_run():
    verdict = _evaluate(provider_mode=PROVIDER_MODE_FREE_TIER)
    assert verdict.allowed is False
    assert pgc.REFUSAL_PROVIDER_MODE_NOT_PAID in verdict.refusals


def test_absent_cursor_store_is_refused():
    verdict = _evaluate(cursor_store=None)
    assert verdict.allowed is False
    assert pgc.REFUSAL_CURSOR_STORE_ABSENT in verdict.refusals


def test_cursor_in_the_disposable_run_directory_is_refused():
    """The exact pre-repair wiring: build_cursor_store(state_dir=out_dir)."""

    verdict = _evaluate(cursor_state_dir=RUN_DIR, out_dir=RUN_DIR)
    assert verdict.allowed is False
    assert pgc.REFUSAL_CURSOR_DIR_IS_RUN_DIR in verdict.refusals


@pytest.mark.parametrize("ephemeral", [
    r"C:\tmp\phx2_run_state",
    r"C:\Users\BalaC\AppData\Local\Temp\phx2",
    r"C:\Users\BalaC\pytest-of-BalaC\pytest-1\basetemp",
    r"C:\Users\BalaC\scratch\cursor",
])
def test_ephemeral_cursor_directories_are_refused(ephemeral):
    verdict = _evaluate(cursor_state_dir=ephemeral)
    assert verdict.allowed is False
    assert pgc.REFUSAL_CURSOR_DIR_EPHEMERAL in verdict.refusals


def test_pytest_tmp_path_is_recognised_as_ephemeral(tmp_path):
    assert pgc.directory_is_ephemeral(tmp_path) is True
    assert pgc.directory_is_ephemeral(STABLE_STATE_DIR) is False


def test_system_temp_root_is_recognised_as_ephemeral():
    temp_root = os.environ.get("TEMP") or os.environ.get("TMP")
    if not temp_root:
        pytest.skip("no TEMP/TMP configured on this machine")
    assert pgc.directory_is_ephemeral(Path(temp_root) / "phx2_state") is True


def test_zero_argument_factory_is_refused():
    verdict = _evaluate(source_factory=lambda: SimpleNamespace())
    assert verdict.allowed is False
    assert pgc.REFUSAL_FACTORY_CONTRACT in verdict.refusals


def test_the_test_only_adapter_is_still_recognised_as_cursor_aware():
    """It satisfies the SIGNATURE contract; its name is the warning."""

    adapted = adapt_zero_argument_factory_TEST_ONLY(lambda: SimpleNamespace())
    verdict = _evaluate(source_factory=adapted)
    assert verdict.allowed is True
    assert adapted.__name__ == "zero_argument_factory_adapter_TEST_ONLY"


@pytest.mark.parametrize("mode", ["ws", "hybrid"])
def test_legacy_websocket_discovery_is_refused(mode):
    verdict = _evaluate(discovery_mode=mode)
    assert verdict.allowed is False
    assert pgc.REFUSAL_LEGACY_WEBSOCKET_DISCOVERY in verdict.refusals


def test_two_discovery_owners_are_refused():
    verdict = _evaluate(fallback_discovery_enabled=True)
    assert verdict.allowed is False
    assert pgc.REFUSAL_TWO_DISCOVERY_OWNERS in verdict.refusals


def test_quarantined_or_mismatched_cursor_is_refused():
    quarantined = _evaluate(cursor_store=SimpleNamespace(
        quarantined=True, subscription_identity_matches=True))
    assert pgc.REFUSAL_CURSOR_QUARANTINED in quarantined.refusals

    mismatched = _evaluate(cursor_store=SimpleNamespace(
        quarantined=False, subscription_identity_matches=False))
    assert pgc.REFUSAL_CURSOR_IDENTITY_MISMATCH in mismatched.refusals


# ---------------------------------------------------------------------------
# HEAD pinning
# ---------------------------------------------------------------------------

def test_head_mismatch_is_refused():
    verdict = _evaluate(
        expected_head="c8e980305ebc3fdc710e2c62eb2fda3e12da704e",
        actual_head="7b43f625e0c210b1ed2d24e19707fc6269f369cb")
    assert verdict.allowed is False
    assert pgc.REFUSAL_HEAD_MISMATCH in verdict.refusals


def test_matching_head_is_allowed_case_insensitively():
    head = "7B43F625E0C210B1ED2D24E19707FC6269F369CB"
    verdict = _evaluate(expected_head=head, actual_head=head.lower())
    assert verdict.allowed is True


def test_unreadable_head_is_refused_not_ignored():
    verdict = _evaluate(expected_head="a" * 40, actual_head=None,
                        repo_root=r"C:\definitely\not\a\repository")
    assert verdict.allowed is False
    assert pgc.REFUSAL_HEAD_UNREADABLE in verdict.refusals


def test_the_repository_head_is_actually_readable():
    head = pgc.read_repository_head(REPO_ROOT)
    assert head is not None and len(head) == 40


# ---------------------------------------------------------------------------
# refusal reporting
# ---------------------------------------------------------------------------

def test_every_refusal_is_reported_at_once():
    """One startup attempt tells the operator everything that is wrong."""

    verdict = _evaluate(
        provider_mode=PROVIDER_MODE_FREE_TIER,
        cursor_store=None,
        cursor_state_dir=RUN_DIR,
        out_dir=RUN_DIR,
        source_factory=lambda: SimpleNamespace(),
        discovery_mode="ws",
        fallback_discovery_enabled=True,
    )
    assert verdict.allowed is False
    for expected in (pgc.REFUSAL_PROVIDER_MODE_NOT_PAID,
                     pgc.REFUSAL_CURSOR_STORE_ABSENT,
                     pgc.REFUSAL_CURSOR_DIR_IS_RUN_DIR,
                     pgc.REFUSAL_FACTORY_CONTRACT,
                     pgc.REFUSAL_LEGACY_WEBSOCKET_DISCOVERY,
                     pgc.REFUSAL_TWO_DISCOVERY_OWNERS):
        assert expected in verdict.refusals


def test_refusals_are_a_closed_set_and_carry_no_path_or_secret():
    verdict = _evaluate(
        provider_mode=PROVIDER_MODE_FREE_TIER, cursor_store=None,
        cursor_state_dir=RUN_DIR, out_dir=RUN_DIR,
        source_factory=lambda: SimpleNamespace(), discovery_mode="ws")
    for reason in verdict.refusals:
        assert reason in pgc.PRODUCTION_REFUSAL_REASONS
    rendered = " ".join(verdict.refusals).lower()
    for needle in ("c:\\", "/", "http", "token", "authorization", "key"):
        assert needle not in rendered


def test_raise_if_refused_is_the_fail_closed_seam():
    with pytest.raises(pgc.ProductionContractError) as excinfo:
        _evaluate(provider_mode=PROVIDER_MODE_FREE_TIER).raise_if_refused()
    assert "PRODUCTION_GRPC_CONTRACT_REFUSED" in str(excinfo.value)
    # An allowed verdict must not raise.
    _evaluate().raise_if_refused()


# ---------------------------------------------------------------------------
# the repository CLI actually exposes the contract
# ---------------------------------------------------------------------------

def test_the_repository_cli_exposes_the_production_contract_flags():
    import argparse

    from PHX2.free_tier_producer.free_tier_session import _add_args

    parser = argparse.ArgumentParser()
    _add_args(parser)
    options = {action.dest for action in parser._actions}
    for required in ("provider_mode", "cursor_state_dir", "expected_head",
                     "require_production_grpc", "out_dir"):
        assert required in options, required

    # The exact accepted provider-mode spellings, so a launcher cannot guess.
    mode_action = next(a for a in parser._actions if a.dest == "provider_mode")
    assert set(mode_action.choices) == {
        "free_tier", "paid_primary", "paid_with_fallback"}
    assert mode_action.default == "free_tier"

    # Defaults keep the development CLI permissive.
    assert next(a for a in parser._actions
                if a.dest == "require_production_grpc").default is False
    assert next(a for a in parser._actions
                if a.dest == "cursor_state_dir").default is None

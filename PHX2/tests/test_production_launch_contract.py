"""The armed production launch path must be enforceable AND reachable.

Two blocking findings from the 2026-07-20 post-fix re-audit are pinned here:

``R4`` REQUIRE_PRODUCTION_GRPC_INERT_IN_FREE_TIER
    ``--require-production-grpc`` was evaluated only *inside* the ``paid_mode``
    branch it exists to police.  ``--provider-mode`` defaults to ``free_tier``,
    so an armed launcher that omitted one token got no refusal, no cursor, no
    contract, an open outbound health gate and legacy websocket discovery --
    while remaining fully send-capable.  The requirement has to be decided
    before the branch and before any network object exists.

``R5`` ARMED_LAUNCHERS_REFUSED_BY_FORBIDDEN_WRITE_ROOTS
    All three armed launchers passed an ``--out-dir`` and a ``--ledger-path``
    inside ``_FORBIDDEN_WRITE_ROOTS``.  The module refused with exit 2 roughly
    795 lines before the gRPC contract was ever evaluated, so no operator
    command could execute the repaired path at all.  The guard is correct and
    stays; the launchers must target an allowed canonical runtime root instead.

Everything here is offline and hermetic: argument vectors and structural source
inspection only.  No launcher is executed, no provider is contacted, no
credential or endpoint is read, and nothing is sent.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

from PHX2.free_tier_producer import free_tier_session as fts
from PHX2.free_tier_producer import launcher_contract as lc
from PHX2.free_tier_producer.production_grpc_contract import (
    REFUSAL_CURSOR_DIR_EPHEMERAL,
    REFUSAL_CURSOR_DIR_IS_RUN_DIR,
    REFUSAL_LEGACY_WEBSOCKET_DISCOVERY,
    REFUSAL_PROVIDER_MODE_NOT_PAID,
    REFUSAL_TWO_DISCOVERY_OWNERS,
    evaluate_production_mode_precondition,
)

REPAIR_HEAD = "0" * 40  # a stand-in pin; the real value is checked by the probe
LEDGER_BASELINE = (
    "417e18ec17bc1e894ad4b5ef584de5d6486d1f5ff0e67cba06cbd38cacef55fc:2561:7")


def _baseline_fn(expected):
    """A ledger-digest probe that answers ``expected`` for the canonical path."""

    def _fn(path):
        assert Path(str(path)) == Path(lc.CANONICAL_LEDGER_PATH)
        return expected

    return _fn


# ===========================================================================
# R4. the production requirement is decided BEFORE the mode branch
# ===========================================================================

def test_require_production_grpc_rejects_default_free_tier():
    """The flag with no explicit paid mode refuses before network construction."""

    verdict = evaluate_production_mode_precondition(
        require_production_grpc=True,
        provider_mode="free_tier",
        paid_provider_modes=("paid_primary", "paid_with_fallback"),
        cursor_state_dir=lc.CANONICAL_CURSOR_STATE_DIR,
        out_dir=str(Path(lc.CANONICAL_RUNS_ROOT) / "probe"),
        discovery_mode="polling",
    )
    assert verdict.allowed is False
    assert REFUSAL_PROVIDER_MODE_NOT_PAID in verdict.refusals
    # Closed-set reasons only: no path, endpoint, credential or raw exception.
    for reason in verdict.refusals:
        assert reason.isupper() or "_" in reason
        assert ":\\" not in reason and "//" not in reason
    # Nothing was constructed to reach this refusal.
    assert verdict.checks["evaluated_before_provider_branch"] is True


def test_require_production_grpc_accepts_only_canonical_mode():
    """Only the real paid gRPC modes satisfy the requirement."""

    def _evaluate(**overrides):
        kwargs = dict(
            require_production_grpc=True,
            provider_mode="paid_primary",
            paid_provider_modes=("paid_primary", "paid_with_fallback"),
            cursor_state_dir=lc.CANONICAL_CURSOR_STATE_DIR,
            out_dir=str(Path(lc.CANONICAL_RUNS_ROOT) / "probe"),
            discovery_mode="polling",
        )
        kwargs.update(overrides)
        return evaluate_production_mode_precondition(**kwargs)

    assert _evaluate().allowed is True

    # Wrong / misspelled / legacy modes all refuse.
    for mode in ("free_tier", "paid-primary", "paid_primaryy", "PAID_PRIMARY_X",
                 "websocket", "", None):
        verdict = _evaluate(provider_mode=mode)
        assert verdict.allowed is False, mode
        assert REFUSAL_PROVIDER_MODE_NOT_PAID in verdict.refusals

    # No cursor state directory at all is not a production configuration.
    assert _evaluate(cursor_state_dir=None).allowed is False

    # An ephemeral cursor directory silently resets the resume position.
    ephemeral = _evaluate(cursor_state_dir=r"C:\tmp\phx2_scratch\state")
    assert ephemeral.allowed is False
    assert REFUSAL_CURSOR_DIR_EPHEMERAL in ephemeral.refusals

    # The rotating run directory is never durable state.
    run_dir = str(Path(lc.CANONICAL_RUNS_ROOT) / "probe")
    same = _evaluate(cursor_state_dir=run_dir, out_dir=run_dir)
    assert same.allowed is False
    assert REFUSAL_CURSOR_DIR_IS_RUN_DIR in same.refusals

    # Legacy websocket discovery and a second discovery owner both refuse.
    ws = _evaluate(discovery_mode="ws")
    assert ws.allowed is False
    assert REFUSAL_LEGACY_WEBSOCKET_DISCOVERY in ws.refusals
    two = _evaluate(provider_mode="paid_with_fallback")
    assert two.allowed is False
    assert REFUSAL_TWO_DISCOVERY_OWNERS in two.refusals

    # Without the flag the generic development CLI keeps its default.
    assert _evaluate(require_production_grpc=False,
                     provider_mode="free_tier").allowed is True


def test_production_requirement_is_evaluated_before_the_provider_mode_branch():
    """R4 is an ORDERING defect, so the ordering itself is asserted.

    The precondition call must appear in ``run_producer`` strictly before the
    ``if paid_mode:`` block that previously contained the only enforcement.
    """

    tree = ast.parse(inspect.getsource(fts))
    run_producer = next(
        node for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "run_producer")

    precondition_line = None
    paid_branch_line = None
    for node in ast.walk(run_producer):
        if (precondition_line is None and isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "evaluate_production_mode_precondition"):
            precondition_line = node.lineno
        if (paid_branch_line is None and isinstance(node, ast.If)
                and isinstance(node.test, ast.Name)
                and node.test.id == "paid_mode"):
            paid_branch_line = node.lineno

    assert precondition_line is not None, (
        "the production requirement must be evaluated in run_producer")
    assert paid_branch_line is not None
    assert precondition_line < paid_branch_line, (
        "R4: the requirement must not be nested in the branch it polices")


# ===========================================================================
# R5. the armed launchers must reach the repaired path
# ===========================================================================

def test_canonical_runtime_root_is_outside_every_forbidden_root():
    """The canonical paid-primary root must not be a protected historical tree."""

    assert lc.FORBIDDEN_WRITE_ROOTS == fts._FORBIDDEN_WRITE_ROOTS, (
        "the launcher contract and the session must share one forbidden set")

    for path in (lc.PAID_PRIMARY_RUNTIME_ROOT, lc.CANONICAL_CURSOR_STATE_DIR,
                 lc.CANONICAL_LEDGER_PATH, lc.CANONICAL_RUNS_ROOT):
        assert fts.path_is_forbidden(path) is False, path
        assert lc.path_is_forbidden(path) is False, path

    # The frozen one-send ceremony ledger is never the canonical target.
    assert "one_send_ceremony" not in lc.CANONICAL_LEDGER_PATH.lower()
    # Durable state and disposable run output never share a directory.
    assert Path(lc.CANONICAL_CURSOR_STATE_DIR) != Path(lc.CANONICAL_RUNS_ROOT)
    assert Path(lc.CANONICAL_LEDGER_PATH).parent != Path(
        lc.CANONICAL_CURSOR_STATE_DIR)


@pytest.mark.parametrize("launcher", lc.ARMED_LAUNCHERS)
def test_all_armed_launchers_pass_early_path_validation(launcher):
    """Every armed launcher's effective arguments clear the module's own gates."""

    argv = lc.canonical_launcher_arguments(
        launcher=launcher, expected_head=REPAIR_HEAD,
        ledger_baseline=LEDGER_BASELINE)

    verdict = lc.validate_launcher_arguments(
        argv, expected_head=REPAIR_HEAD,
        ledger_baseline_fn=_baseline_fn(LEDGER_BASELINE))
    assert verdict.allowed is True, verdict.refusals
    assert verdict.refusals == []

    checks = verdict.checks
    assert checks["module"] == lc.TRACKED_PRODUCTION_MODULE
    assert checks["provider_mode"] == "paid_primary"
    assert checks["require_production_grpc"] is True
    assert checks["discovery_mode"] == "polling"
    assert checks["out_dir_forbidden"] is False
    assert checks["ledger_forbidden"] is False
    assert checks["cursor_state_dir_stable"] is True
    assert checks["cursor_state_dir_is_out_dir"] is False
    assert checks["ledger_baseline_matches"] is True
    assert checks["expected_head_matches"] is True

    # The same values must clear the session's own path isolation, which is
    # what refused every launcher before this repair.
    assert fts.path_is_forbidden(checks["out_dir"]) is False
    assert fts.path_is_forbidden(checks["ledger_path"]) is False

    # Each launcher gets its own run directory; state and ledger are shared.
    assert checks["cursor_state_dir"] == lc.CANONICAL_CURSOR_STATE_DIR
    assert checks["ledger_path"] == lc.CANONICAL_LEDGER_PATH
    assert Path(lc.CANONICAL_RUNS_ROOT) in Path(checks["out_dir"]).parents

    # No launcher may carry a send-capable confirmation token in the clear.
    assert "--require-runner-manifest-hash" not in argv


def test_armed_launcher_run_directories_are_distinct():
    """Two launchers must never share one disposable run directory."""

    out_dirs = set()
    for launcher in lc.ARMED_LAUNCHERS:
        argv = lc.canonical_launcher_arguments(
            launcher=launcher, expected_head=REPAIR_HEAD,
            ledger_baseline=LEDGER_BASELINE)
        out_dirs.add(lc.parse_launcher_arguments(argv)["out_dir"])
    assert len(out_dirs) == len(lc.ARMED_LAUNCHERS)


def test_launcher_negative_control_old_arguments_refuse():
    """The pre-fix argument sets must still fail at the same boundaries.

    Without this the repair could be "proved" by a validator that accepts
    everything.  These are the exact shapes the re-audit found refused.
    """

    pre_fix = [
        # launch_soak_02h_01.ps1 as audited: forbidden out-dir, frozen ledger.
        [
            "-u", "-m", lc.TRACKED_PRODUCTION_MODULE, "--run",
            "--ledger-path",
            r"C:\Users\BalaC\phx2_one_send_ceremony\ping_dedupe.jsonl",
            "--expected-head", REPAIR_HEAD,
            "--provider-mode", "paid_primary",
            "--discovery-mode", "polling",
            "--require-production-grpc",
            "--cursor-state-dir",
            r"C:\Users\BalaC\phx2_production_private_live\state",
            "--out-dir",
            r"C:\Users\BalaC\phx2_production_private_live\out\prod_live_soak_02h_01",
        ],
        # launch_window_04.ps1 as audited: additionally a spent baseline.
        [
            "-u", "-m", lc.TRACKED_PRODUCTION_MODULE, "--run",
            "--require-baseline",
            "8d498a5b0000000000000000000000000000000000000000000000000000d00d:3290:9",
            "--ledger-path",
            r"C:\Users\BalaC\phx2_one_send_ceremony\ping_dedupe.jsonl",
            "--expected-head", REPAIR_HEAD,
            "--provider-mode", "paid_primary",
            "--require-production-grpc",
            "--cursor-state-dir",
            r"C:\Users\BalaC\phx2_production_private_live\state",
            "--out-dir",
            r"C:\Users\BalaC\phx2_production_private_live\out\window_04",
        ],
        # the inert-flag shape R4 describes: the token silently does nothing.
        [
            "-u", "-m", lc.TRACKED_PRODUCTION_MODULE, "--run",
            "--ledger-path", lc.CANONICAL_LEDGER_PATH,
            "--expected-head", REPAIR_HEAD,
            "--require-production-grpc",
            "--cursor-state-dir", lc.CANONICAL_CURSOR_STATE_DIR,
            "--out-dir", str(Path(lc.CANONICAL_RUNS_ROOT) / "inert"),
        ],
    ]

    for argv in pre_fix:
        verdict = lc.validate_launcher_arguments(
            argv, expected_head=REPAIR_HEAD,
            ledger_baseline_fn=_baseline_fn(LEDGER_BASELINE))
        assert verdict.allowed is False, argv
        assert verdict.refusals

    soak, window, inert = (
        lc.validate_launcher_arguments(
            argv, expected_head=REPAIR_HEAD,
            ledger_baseline_fn=_baseline_fn(LEDGER_BASELINE))
        for argv in pre_fix)

    assert lc.REFUSAL_OUT_DIR_FORBIDDEN in soak.refusals
    assert lc.REFUSAL_LEDGER_FORBIDDEN in soak.refusals
    assert lc.REFUSAL_LEDGER_FORBIDDEN in window.refusals
    assert lc.REFUSAL_LEDGER_BASELINE_MISMATCH in window.refusals
    assert lc.REFUSAL_PROVIDER_MODE_NOT_CANONICAL in inert.refusals

    # And the session's own predicate agrees about the forbidden ones.
    assert fts.path_is_forbidden(
        r"C:\Users\BalaC\phx2_one_send_ceremony\ping_dedupe.jsonl") is True
    assert fts.path_is_forbidden(
        r"C:\Users\BalaC\phx2_production_private_live\out\window_04") is True


def test_launcher_validator_refuses_a_missing_production_flag():
    """Dropping the requirement token is refused, not silently downgraded."""

    argv = [a for a in lc.canonical_launcher_arguments(
        launcher=lc.ARMED_LAUNCHERS[0], expected_head=REPAIR_HEAD,
        ledger_baseline=LEDGER_BASELINE) if a != "--require-production-grpc"]

    verdict = lc.validate_launcher_arguments(
        argv, expected_head=REPAIR_HEAD,
        ledger_baseline_fn=_baseline_fn(LEDGER_BASELINE))
    assert verdict.allowed is False
    assert lc.REFUSAL_PRODUCTION_FLAG_ABSENT in verdict.refusals


def test_launcher_validator_refuses_a_head_pin_mismatch():
    """A launcher pinned to the wrong commit never reaches the repaired path."""

    argv = lc.canonical_launcher_arguments(
        launcher=lc.ARMED_LAUNCHERS[0], expected_head="a" * 40,
        ledger_baseline=LEDGER_BASELINE)

    verdict = lc.validate_launcher_arguments(
        argv, expected_head=REPAIR_HEAD,
        ledger_baseline_fn=_baseline_fn(LEDGER_BASELINE))
    assert verdict.allowed is False
    assert lc.REFUSAL_HEAD_PIN_MISMATCH in verdict.refusals

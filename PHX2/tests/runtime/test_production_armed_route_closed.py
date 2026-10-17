"""The supervisor / ``main.py --hours`` route must not be a fourth armed owner.

``M-2`` UNDOCUMENTED_FOURTH_ARMED_PRIVATE_LIVE_ROUTE (2026-07-20 residual
re-audit, MEDIUM).

``PHX2/runtime/production_supervisor.py::run_producer_child`` built a fully armed
producer invocation -- ``--run --enable-telegram --ack-live-free-tier
--i-understand-this-can-send --confirm-token <locked> --provider-mode
paid_primary --ledger-path <active>`` -- and called ``free_tier_session.main``
in process.  It passed **no** ``--require-production-grpc`` and **no**
``--cursor-state-dir``, so the armed production-gRPC contract was skipped and the
durable cursor fell back to a disposable per-run directory.  It was reachable
undocumented as ``python main.py --hours N`` and stood as a fourth armed owner
beside the three canonical PowerShell launchers.

The architecture decision (preferred design): the three PowerShell launchers are
the only armed private-live send path.  ``main.py --hours`` / the supervisor
producer child must fail closed -- refusing before it constructs any source,
channel, transport, writable ledger or cursor, and directing the operator to the
canonical launchers.  It must never call ``free_tier_session.main`` with an armed
vector.

Hermetic: every config points at TEMP paths, ``free_tier_session.main`` is a fake
that records its argv, and the refusal is proven to happen before it is ever
called.  No socket, no ``.env``, no real ledger, no send.
"""

from __future__ import annotations

import ast
import inspect

import pytest

from PHX2.runtime import production_supervisor as ps


ARM_FLAGS = (
    "--i-understand-this-can-send",
    "--confirm-token",
    "--enable-telegram",
    "--ack-live-free-tier",
    "--enable-private-discord",
)

CANONICAL_LAUNCHERS = (
    "launch_pressure_24h_01.ps1",
    "launch_soak_02h_01.ps1",
    "launch_window_04.ps1",
)


def _make_config(tmp_path, *, write_runtime_config=True):
    repo = tmp_path / "repo"
    (repo / "PHX2").mkdir(parents=True)
    python = repo / ".venv" / "Scripts" / "python.exe"
    python.parent.mkdir(parents=True)
    python.write_bytes(b"")
    active = tmp_path / "active.jsonl"
    frozen = tmp_path / "frozen.jsonl"
    paper = tmp_path / "paper.json"
    active.write_text("active\n", encoding="utf-8")
    frozen.write_text("frozen\n", encoding="utf-8")
    paper.write_text("{}\n", encoding="utf-8")
    paths = ps.ProductionPaths(
        repo_root=repo, runtime_root=tmp_path, lock_path=tmp_path / "lock",
        env_file=tmp_path / "env", active_ledger=active, frozen_ledger=frozen,
        paper_config=paper)
    config = ps.ProductionConfig(
        run_dir=(tmp_path / "run").resolve(), hours=1.0, paths=paths)
    config.control_dir.mkdir(parents=True)
    if write_runtime_config:
        baseline = ps.ledger_baseline(active).as_token()
        ps.atomic_json(config.control_dir / "production_config.json", {
            "provider_mode": "PAID_PRIMARY",
            "market_provider": "BIRDEYE_PRIMARY",
            "delivery_transport": "TELEGRAM",
            "telegram_enabled": True,
            "discord_enabled": False,
            "private_discord_enabled": False,
            "polling_fallback_enabled": False,
            "primary_max_grpc_streams": 1,
            "verifier_max_grpc_streams": 0,
            "max_grpc_streams": 1,
            "lp_integrity_mode": "DISABLED_SINGLE_STREAM",
            "migration_activation_multiplier": "1.20",
            "active_ledger_baseline": baseline,
        })
    return config


def test_run_producer_child_refuses_and_never_calls_session_main(
    tmp_path, monkeypatch, capsys
):
    """Even with a fully valid production config, the producer child refuses
    (exit 2) and never invokes the armed session entry point."""
    config = _make_config(tmp_path)
    from PHX2.free_tier_producer import free_tier_session

    calls = []

    def _boom(argv):
        calls.append(list(argv))
        raise AssertionError("free_tier_session.main must never be armed here")

    monkeypatch.setattr(free_tier_session, "main", _boom)
    result = ps.run_producer_child(config)
    assert result == 2
    assert calls == [], "the supervisor route constructed an armed send path"
    out = capsys.readouterr().out
    assert "[refused]" in out


def test_refusal_directs_operator_to_the_canonical_launchers(tmp_path, capsys):
    config = _make_config(tmp_path)
    assert ps.run_producer_child(config) == 2
    out = capsys.readouterr().out
    assert any(name in out for name in CANONICAL_LAUNCHERS), (
        "refusal does not name the canonical launchers")


def test_run_producer_child_source_carries_no_arm_vector():
    """No arm/send flag literal may remain in the producer-child source, and it
    may no longer call ``free_tier_session.main``."""
    source = inspect.getsource(ps.run_producer_child)
    tree = ast.parse(source)

    string_constants = {
        node.value for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)}
    present = sorted(flag for flag in ARM_FLAGS if flag in string_constants)
    assert not present, f"producer child still builds an arm vector: {present}"

    calls_session_main = any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "main"
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "free_tier_session"
        for node in ast.walk(tree))
    assert not calls_session_main, (
        "producer child still calls free_tier_session.main")


def test_child_main_producer_role_cannot_arm(tmp_path, monkeypatch):
    """The ``--child-role producer`` entry (what ``main.py --hours`` spawns)
    refuses without importing an armed send path."""
    config = _make_config(tmp_path)

    real_config_type = ps.ProductionConfig
    monkeypatch.setattr(
        ps, "ProductionConfig",
        lambda **kwargs: config if kwargs.get("run_dir") else real_config_type(**kwargs))

    from PHX2.free_tier_producer import free_tier_session
    monkeypatch.setattr(
        free_tier_session, "main",
        lambda argv: (_ for _ in ()).throw(AssertionError("armed send reached")))

    code = ps.child_main(
        ["--child-role", "producer", "--run-dir", str(config.run_dir),
         "--hours", "1"])
    assert code == 2


def test_supervisor_producer_child_refuses_before_constructing_state(
    tmp_path, monkeypatch
):
    """The refusal must precede any writable-ledger / session construction: a
    missing runtime config is not even consulted, because arming is refused
    outright."""
    config = _make_config(tmp_path, write_runtime_config=False)
    from PHX2.free_tier_producer import free_tier_session

    monkeypatch.setattr(
        free_tier_session, "main",
        lambda argv: (_ for _ in ()).throw(AssertionError("armed send reached")))
    # No production_config.json exists; the route still refuses (exit 2) rather
    # than constructing a send path.
    assert ps.run_producer_child(config) == 2


def test_no_arm_flag_appears_in_any_supervisor_child_command(tmp_path):
    """The supervisor's launched child commands (producer/paper/dashboard) carry
    no arm/send flag anywhere."""
    config = _make_config(tmp_path)
    joined = " ".join(sum(ps.build_child_commands(config).values(), []))
    for flag in ARM_FLAGS:
        assert flag not in joined, f"{flag} present in a supervisor child command"

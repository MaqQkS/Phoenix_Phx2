"""The canonical indefinite launcher contract, checked without running it.

Covers required offline tests 38-42, plus the indefinite-runtime contract added
to the producer (``--run-forever``) and the forward-only ledger-baseline proof.
"""

from __future__ import annotations

import re

import pytest

from PHX2.free_tier_producer.compat.production_live_runner import (
    UNBOUNDED_RUNTIME_SECONDS,
    ProductionBounds,
    runtime_bound_is_unbounded,
)
from PHX2.free_tier_producer.launcher_contract import (
    CANONICAL_CURSOR_STATE_DIR,
    CANONICAL_LEDGER_PATH,
    CANONICAL_RUNS_ROOT,
    REPO_PYTHON,
    TRACKED_PRODUCTION_MODULE,
)
from PHX2.watchdog.launcher_template import (
    ACTIVE_ENV_PATH,
    REFUSAL_DISCORD_PRESENT,
    REFUSAL_RUN_FOREVER_MISSING,
    REFUSAL_SHADOW_MISSING,
    REFUSAL_TELEGRAM_COUNT,
    REFUSAL_TIMEOUT_SIMULATION,
    deployment_specification,
    live_launcher_sha256,
    render_live_launcher,
    validate_live_launcher_text,
)

HEAD = "beea7c15e11b1a4456472acf790193df242f763f"
BASELINE = ("1b014af95a3c19d4aa1b36d0292fe0b0da4f169b453c546441cb26a114d9f0ed"
            ":2928:8")


@pytest.fixture(scope="module")
def launcher_text() -> str:
    return render_live_launcher(expected_head=HEAD, ledger_baseline=BASELINE)


def _quoted_args(text: str) -> list:
    return re.findall(r'"(--[a-z0-9\-]+)"', text)


# --- the rendered launcher satisfies its own contract ------------------- #

def test_rendered_launcher_has_zero_contract_refusals(launcher_text):
    assert validate_live_launcher_text(
        launcher_text, expected_head=HEAD, ledger_baseline=BASELINE) == []


def test_render_is_deterministic():
    first = live_launcher_sha256(expected_head=HEAD, ledger_baseline=BASELINE)
    second = live_launcher_sha256(expected_head=HEAD, ledger_baseline=BASELINE)
    assert first == second
    spec = deployment_specification(expected_head=HEAD,
                                    ledger_baseline=BASELINE)
    assert spec["sha256"] == first
    assert spec["contract_refusals"] == []
    assert spec["runtime_contract"] == "RUN_FOREVER"
    assert spec["delivery_transport"] == "TELEGRAM"
    assert spec["discord_enabled"] is False
    assert spec["structural_policy"] == "SHADOW"
    assert spec["migration_source_mode"] == "HELIUS_PRIMARY"
    assert spec["primary_migration_source"] == "HELIUS"
    assert spec["primary_recovery"] == "HELIUS_HTTP"
    assert spec["shadow_source"] == "DISABLED"
    assert spec["chainstack_configured_for_runtime"] is False
    assert spec["chainstack_connected"] is False
    assert spec["chainstack_comparator"] is False
    assert spec["source_owners"] == 1


def test_no_template_placeholder_survives(launcher_text):
    assert "__" not in launcher_text.replace("__PIN", ""), (
        "an unsubstituted template placeholder remains")


# --- 38. Telegram exactly once ----------------------------------------- #

def test_telegram_flag_appears_exactly_once(launcher_text):
    assert _quoted_args(launcher_text).count("--enable-telegram") == 1


def test_removing_the_telegram_flag_is_refused(launcher_text):
    broken = launcher_text.replace('"--enable-telegram",', "")
    assert REFUSAL_TELEGRAM_COUNT in validate_live_launcher_text(
        broken, expected_head=HEAD, ledger_baseline=BASELINE)


def test_duplicating_the_telegram_flag_is_refused(launcher_text):
    broken = launcher_text.replace(
        '"--enable-telegram",', '"--enable-telegram",\n  "--enable-telegram",')
    assert REFUSAL_TELEGRAM_COUNT in validate_live_launcher_text(
        broken, expected_head=HEAD, ledger_baseline=BASELINE)


# --- 39. Discord zero times ------------------------------------------- #

def test_discord_arm_flag_appears_zero_times(launcher_text):
    assert "--enable-private-discord" not in launcher_text
    assert _quoted_args(launcher_text).count("--enable-private-discord") == 0


def test_adding_a_discord_arm_flag_is_refused(launcher_text):
    broken = launcher_text.replace(
        '"--enable-telegram",', '"--enable-telegram",\n  "--enable-private-discord",')
    refusals = validate_live_launcher_text(
        broken, expected_head=HEAD, ledger_baseline=BASELINE)
    assert REFUSAL_DISCORD_PRESENT in refusals


def test_launcher_carries_no_secret_and_no_env_var_name(launcher_text):
    assert "PHX2_TELEGRAM_BOT_TOKEN" not in launcher_text
    assert "PHX2_TELEGRAM_CHAT_ID" not in launcher_text
    assert "discord.com/api/webhooks" not in launcher_text
    assert not re.search(r"\b\d{6,}:[A-Za-z0-9_\-]{30,}\b", launcher_text)


# --- 40. SHADOW mode -------------------------------------------------- #

def test_structural_policy_is_shadow_exactly_once(launcher_text):
    assert _quoted_args(launcher_text).count(
        "--phx1-structural-policy") == 1
    assert '"--phx1-structural-policy", "shadow"' in launcher_text


def test_enforce_policy_is_refused(launcher_text):
    broken = launcher_text.replace('"shadow"', '"enforce"')
    assert REFUSAL_SHADOW_MISSING in validate_live_launcher_text(
        broken, expected_head=HEAD, ledger_baseline=BASELINE)


# --- 41. fresh run / log directories per launch ------------------------ #

def test_run_and_log_directories_are_fresh_per_launch(launcher_text):
    assert "$RunStamp" in launcher_text
    assert 'ToUniversalTime().ToString("yyyyMMddTHHmmssZ")' in launcher_text
    assert "New-Item -ItemType Directory -Force $out" in launcher_text
    assert "New-Item -ItemType Directory -Force $logDir" in launcher_text
    assert '$RUN_ID  = "paid_primary_live_24x7_$RunStamp"' in launcher_text
    assert CANONICAL_RUNS_ROOT in launcher_text


def test_manifest_is_written_without_a_bom(launcher_text):
    """`Out-File -Encoding utf8` on PowerShell 5.1 emits a BOM that broke the
    manifest handshake; the launcher must write BOM-less UTF-8."""

    assert "[System.IO.File]::WriteAllText($ManifestPath, $manifestJson, $Utf8NoBom)" \
        in launcher_text
    assert "Out-File -LiteralPath $ManifestPath" not in launcher_text


def test_manifest_carries_the_run_dir_handshake(launcher_text):
    for key in ("run_dir", "log_dir", "stop_file", "cursor_state_dir",
                "ledger_path", "ledger_baseline_pinned",
                "ledger_baseline_current", "runtime_contract",
                "delivery_transport", "structural_policy",
                "watchdog_parent_pid", "launcher_sha256", "pinned_repo_head"):
        assert key in launcher_text, key


def test_stop_file_lives_in_the_per_launch_log_directory(launcher_text):
    """A stale stop file must never be able to pre-stop a later launch."""

    assert '$STOP_FILE = Join-Path $logDir "STOP_REQUESTED"' in launcher_text
    assert '"--stop-file", $STOP_FILE' in launcher_text


# --- 42. stable durable state paths ----------------------------------- #

def test_durable_state_paths_are_stable_and_canonical(launcher_text):
    assert f'$STATE_DIR = "{CANONICAL_CURSOR_STATE_DIR}"' in launcher_text
    assert '"--cursor-state-dir", $STATE_DIR' in launcher_text
    assert f'$LEDGER    = "{CANONICAL_LEDGER_PATH}"' in launcher_text
    assert '"--ledger-path", $LEDGER' in launcher_text
    # The cursor must never live in the rotating run directory.
    assert '"--cursor-state-dir", $out' not in launcher_text


def test_active_repository_env_is_used_and_documents_env_is_not(launcher_text):
    assert ACTIVE_ENV_PATH in launcher_text
    assert r"C:\Users\BalaC\Documents\phx2.env" not in launcher_text


def test_canonical_production_shape_is_stated_explicitly(launcher_text):
    for fragment in (
        f'"-m", $MODULE', '"--run",', '"--require-production-grpc"',
        '"--provider-mode", "paid_primary"',
        '"--discovery-mode", "polling"',
        '"--migration-source-mode", $SOURCE_MODE',
        '"--enable-helius-http-recovery"',
        '"--grpc-gap-recovery", "live_epoch"',
    ):
        assert fragment in launcher_text, fragment
    assert TRACKED_PRODUCTION_MODULE in launcher_text
    assert REPO_PYTHON in launcher_text
    assert '$SOURCE_MODE = "HELIUS_PRIMARY"' in launcher_text
    assert (
        '$env:PHX2_MIGRATION_SOURCE_MODE = "HELIUS_PRIMARY"'
        in launcher_text
    )
    assert "--helius-parity-late-match-seconds" not in launcher_text
    assert "--chainstack-endpoint" not in launcher_text


def test_historical_rpc_replay_flags_are_absent(launcher_text):
    assert "--rpc-recovery-" not in launcher_text
    # Bounded six-hour DEX candidate recovery is part of the armed contract
    # (2026-07-30 remediation); historical RPC replay above stays absent.
    assert _quoted_args(launcher_text).count(
        "--enable-dexscreener-restart-backfill") == 1


def test_no_wallet_signing_or_trading_is_enabled(launcher_text):
    assert not re.search(r"(?i)--enable-(wallet|trading|signing)",
                         launcher_text)
    assert "wallet_signing_enabled  = $false" in launcher_text
    assert "trading_enabled         = $false" in launcher_text


# --- indefinite runtime is real, not simulated ------------------------ #

def test_run_forever_is_present_and_no_clock_is_also_stated(launcher_text):
    assert _quoted_args(launcher_text).count("--run-forever") == 1
    assert "--max-runtime-seconds" not in launcher_text
    assert "--active-soak-seconds" not in launcher_text
    assert "--max-wall-clock-seconds" not in launcher_text


def test_a_large_timeout_instead_of_run_forever_is_refused(launcher_text):
    broken = launcher_text.replace(
        '"--run-forever",', '"--max-runtime-seconds", "99999999",')
    refusals = validate_live_launcher_text(
        broken, expected_head=HEAD, ledger_baseline=BASELINE)
    assert REFUSAL_RUN_FOREVER_MISSING in refusals
    assert REFUSAL_TIMEOUT_SIMULATION in refusals


def test_recursive_relaunch_is_refused(launcher_text):
    broken = launcher_text + '\nStart-Process powershell -ArgumentList "launch_live_24x7.ps1"\n'
    assert REFUSAL_TIMEOUT_SIMULATION in validate_live_launcher_text(
        broken, expected_head=HEAD, ledger_baseline=BASELINE)


def test_pins_appear_exactly_once_each(launcher_text):
    assert launcher_text.count(HEAD) == 1
    assert launcher_text.count(BASELINE) == 1


def test_closed_armed_route_is_absent_from_executable_code(launcher_text):
    """The header MAY assert the route is closed; the code may not use it.

    Scanning raw text would read the launcher's own negative claim ("main.py /
    the production supervisor are NOT a route ... and appear nowhere below") as a
    violation, so only code lines are scanned.
    """

    from PHX2.watchdog.launcher_template import strip_powershell_comments

    code = strip_powershell_comments(launcher_text)
    assert "production_supervisor" not in code
    assert "--hours" not in code
    assert "main.py" not in code
    assert "supervised_launcher" not in code
    # And the closed route IS still documented as closed.
    assert "M-2" in launcher_text


def test_a_launcher_that_actually_invokes_the_closed_route_is_refused(
    launcher_text,
):
    from PHX2.watchdog.launcher_template import REFUSAL_CLOSED_ROUTE

    broken = launcher_text.replace(
        '"-m", $MODULE,', '"main.py", "--hours", "24",')
    assert REFUSAL_CLOSED_ROUTE in validate_live_launcher_text(
        broken, expected_head=HEAD, ledger_baseline=BASELINE)


# --- forward-only ledger baseline proof ------------------------------- #

def test_launcher_proves_the_pinned_baseline_is_still_a_prefix(launcher_text):
    """A static pin would refuse every launch after the first real send."""

    assert "LEDGER_PINNED_PREFIX_DIVERGED" in launcher_text
    assert "LEDGER_SHORTER_THAN_PINNED_BASELINE" in launcher_text
    assert "LEDGER_LINE_COUNT_REGRESSED" in launcher_text
    assert '"--require-baseline", $CURRENT_BASELINE' in launcher_text
    assert "forward_extension_proven=True" in launcher_text


# --- the producer's own indefinite-runtime contract ------------------- #

def test_unbounded_sentinel_semantics():
    assert UNBOUNDED_RUNTIME_SECONDS == 0.0
    assert runtime_bound_is_unbounded(0.0) is True
    assert runtime_bound_is_unbounded(0) is True
    assert runtime_bound_is_unbounded(-1.0) is True
    assert runtime_bound_is_unbounded(7200.0) is False
    # A malformed value must never produce an endless run.
    assert runtime_bound_is_unbounded("nonsense") is False
    assert runtime_bound_is_unbounded(None) is False


def test_positive_runtime_bounds_keep_their_meaning():
    assert runtime_bound_is_unbounded(
        ProductionBounds().max_runtime_seconds) is False


def test_unbounded_runtime_never_stops_on_the_clock():
    """The watch loop must not emit MAX_RUNTIME when the sentinel is set."""

    from PHX2.free_tier_producer.compat import production_live_runner as runner
    import inspect

    source = inspect.getsource(runner.run_production_live_watch)
    assert "runtime_bound_is_unbounded(bounds.max_runtime_seconds)" in source, (
        "the runtime bound check no longer consults the sentinel")


def test_run_forever_flag_exists_and_conflicts_are_refused():
    """``--run-forever`` is the ONE runtime-boundary statement."""

    import argparse

    from PHX2.free_tier_producer import free_tier_session as session

    parser = argparse.ArgumentParser()
    session._add_args(parser)
    args = parser.parse_args(["--run", "--run-forever"])
    assert args.run_forever is True
    assert args.max_runtime_seconds is None

    conflicting = parser.parse_args(
        ["--run", "--run-forever", "--max-runtime-seconds", "7200"])
    assert conflicting.run_forever is True
    assert conflicting.max_runtime_seconds == 7200.0


@pytest.mark.parametrize("extra,token", [
    (["--max-runtime-seconds", "7200"], "MAX_RUNTIME_SECONDS_ALSO_GIVEN"),
    (["--active-soak-seconds", "7200"], "ACTIVE_SOAK_SECONDS_ALSO_GIVEN"),
    (["--max-total-ticks", "10"], "MAX_TOTAL_TICKS_ALSO_GIVEN"),
])
def test_run_forever_conflict_refusal_precedes_env_loading(capsys, extra, token):
    """Refused on ARGUMENTS alone -- before the env file is even opened.

    The env path given here does not exist. If the refusal did not come first the
    call would raise FileNotFoundError instead of returning 2, so this also
    proves the ordering.
    """

    import argparse

    from PHX2.free_tier_producer import free_tier_session as session

    parser = argparse.ArgumentParser()
    session._add_args(parser)
    args = parser.parse_args(
        ["--run", "--run-forever", "--env", "definitely-not-a-real-env-file"]
        + extra)

    code = session.run_producer(args)
    output = capsys.readouterr().out
    assert code == 2
    assert "RUN_FOREVER_CONFLICT" in output
    assert token in output
    assert "env: loaded" not in output, (
        "the environment file was opened before the refusal")

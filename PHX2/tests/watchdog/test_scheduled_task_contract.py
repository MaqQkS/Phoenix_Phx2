"""Windows Task Scheduler tooling contract, checked without registering a task.

Covers required offline tests 35-37.

The tooling is PowerShell, so the contract is asserted against its text: the
action, the one-instance setting, the absence of any credential or secret, the
refusal to overwrite a non-managed task of the same name, and idempotence of
every verb.  Actually registering a task is done ONCE, deliberately, by the
operator step at the end of Stage 10 -- not by the test suite.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
TOOLING = REPO_ROOT / "PHX2" / "scripts" / "phx2_watchdog_task.ps1"


@pytest.fixture(scope="module")
def tooling_text() -> str:
    return TOOLING.read_text(encoding="utf-8")


def _code_lines(text: str) -> str:
    return "\n".join(line for line in text.splitlines()
                     if not line.lstrip().startswith("#"))


def test_tooling_exists_and_is_tracked_powershell():
    assert TOOLING.exists()
    assert TOOLING.suffix == ".ps1"


# --- 35. no secret in the scheduled-task command ------------------------ #

def test_task_command_contains_no_secret(tooling_text):
    code = _code_lines(tooling_text)
    assert not re.search(r"\b\d{6,}:[A-Za-z0-9_\-]{30,}\b", code)
    # The env-var NAMES may appear only in the negative assertion that scans for
    # them; they must never be set or passed.
    assert "$env:PHX2_TELEGRAM_BOT_TOKEN" not in code
    assert "$env:PHX2_TELEGRAM_CHAT_ID" not in code
    assert "discord.com/api/webhooks" not in code
    assert "-Password" not in code
    assert "New-ScheduledTaskPrincipal" in code
    assert "-LogonType Interactive" in code


def test_task_action_uses_windowless_pythonw_run(tooling_text):
    # The registered action runs the watchdog under the WINDOWLESS interpreter
    # (pythonw.exe) so a Task-Scheduler console/session control event cannot fell
    # the shared watchdog/launcher/producer tree with STATUS_CONTROL_C_EXIT.
    assert '$ModuleArgs   = "-m PHX2.watchdog run"' in tooling_text
    assert '$WatchdogExe  = Join-Path $RepoRoot ".venv\\Scripts\\pythonw.exe"' \
        in tooling_text
    assert "New-ScheduledTaskAction -Execute $WatchdogExe -Argument $ModuleArgs" \
        in tooling_text
    assert "-WorkingDirectory $RepoRoot" in tooling_text
    # The registered action must NOT be the console interpreter.
    code = _code_lines(tooling_text)
    assert ".venv\\Scripts\\python.exe" not in code, (
        "the registered task action must be pythonw.exe, not python.exe")
    # Operator status/stop/validate stay on python.exe (visible output); the
    # header documents this so operators are not misled by the pythonw action.
    assert "status/stop/validate" in tooling_text
    assert "python.exe" in tooling_text


def test_tooling_actively_scans_its_own_command_for_secrets(tooling_text):
    """The status/schema check proves no secret is in the registered command."""

    assert "no_secret_in_command" in tooling_text
    assert re.search(r"\\d\{6,\}:\[A-Za-z0-9_\\-\]\{30,\}", tooling_text), (
        "the tooling does not scan the registered command for a bot token")


def test_task_does_not_request_highest_privilege(tooling_text):
    assert "-RunLevel Limited" in tooling_text
    assert "Highest" not in _code_lines(tooling_text)


def test_trigger_is_at_user_logon_not_boot(tooling_text):
    assert "New-ScheduledTaskTrigger -AtLogOn" in tooling_text
    assert "-AtStartup" not in tooling_text
    assert "MSFT_TaskLogonTrigger" in tooling_text


# --- 36. one-instance setting --------------------------------------------- #

def test_one_instance_maximum_is_configured_and_verified(tooling_text):
    assert "-MultipleInstances IgnoreNew" in tooling_text
    assert 'MultipleInstances -eq "IgnoreNew"' in tooling_text
    assert "single_instance_ok" in tooling_text


def test_scheduler_restart_on_failure_is_disabled(tooling_text):
    """Task Scheduler must not bypass the watchdog's circuit breaker."""

    assert "$settings.RestartCount = 0" in tooling_text
    assert "RestartCount -eq 0" in tooling_text
    assert "no_restart_on_fail" in tooling_text
    assert "authoritative_restart_controller" in tooling_text
    assert "PHX2_WATCHDOG_CIRCUIT_BREAKER" in tooling_text


def test_task_is_hidden_and_contains_no_repetition_trigger(tooling_text):
    code = _code_lines(tooling_text)
    assert "-StartWhenAvailable -Hidden -ExecutionTimeLimit" in code
    assert "Settings.Hidden -eq $true" in code
    assert "hidden_ok" in code
    assert "New-ScheduledTaskTrigger -AtLogOn" in code
    assert "RepetitionInterval" not in code
    assert "New-ScheduledTaskTrigger -Once" not in code
    assert "PT10S" not in code


# --- 37. install / enable / disable / uninstall are idempotent ----------- #

def test_every_required_verb_is_implemented(tooling_text):
    for verb in ("install", "uninstall", "enable", "disable", "status"):
        assert f'"{verb}"' in tooling_text, verb
    assert 'ValidateSet("install", "uninstall", "enable", "disable", "start", "status")' \
        in tooling_text


def test_install_is_idempotent_by_replacing_a_matching_task(tooling_text):
    assert "Unregister-ScheduledTask" in tooling_text
    assert "-Force" in tooling_text
    assert "Register-ScheduledTask" in tooling_text


def test_uninstall_is_idempotent_when_the_task_is_absent(tooling_text):
    assert "TASK_ALREADY_ABSENT" in tooling_text


def test_enable_and_disable_report_absent_task_rather_than_failing(tooling_text):
    assert tooling_text.count("TASK_ABSENT") >= 2


def test_install_refuses_to_overwrite_a_non_managed_task(tooling_text):
    assert "EXISTING_TASK_DOES_NOT_MATCH_MANAGED_SCHEMA" in tooling_text
    assert "-not $conforms -and -not $Force" in tooling_text
    assert "inspect it, then re-run with -Force" in tooling_text


def test_install_leaves_the_task_disabled(tooling_text):
    """Stage 10 ends with the task installed but DISABLED; Stage 11 enables it."""

    assert "Disable-ScheduledTask" in tooling_text
    assert "left_disabled" in tooling_text
    assert 'Stage 10 ends with the task INSTALLED but DISABLED' in tooling_text


def test_disable_stops_a_running_instance_first(tooling_text):
    assert 'if ($task.State -eq "Running")' in tooling_text
    assert "Stop-ScheduledTask" in tooling_text


def test_registration_artifact_is_written(tooling_text):
    assert "service_registration.json" in tooling_text
    assert "PHX2_WATCHDOG_SERVICE_REGISTRATION" in tooling_text
    assert "registration_state" in tooling_text


def test_no_third_party_service_wrapper_is_used(tooling_text):
    """Code only: the header legitimately asserts "no NSSM, no Docker, no WSL"."""

    lowered = _code_lines(tooling_text).lower()
    for banned in ("nssm", "docker", "wsl", "sc.exe", "pip install",
                   "srvany", "winsw", "install-module"):
        assert banned not in lowered, banned
    # ...and the tooling still documents that it installs nothing.
    assert "nothing is installed" in tooling_text.lower()


def test_no_local_variable_collides_with_a_script_parameter(tooling_text):
    """PowerShell variable names are CASE-INSENSITIVE.

    A local ``$action = New-ScheduledTaskAction ...`` is therefore the SAME
    variable as the ``[ValidateSet]``-bound ``$Action`` parameter, and the
    assignment fails at run time with "MSFT_TaskExecAction is not a valid value
    for the Action variable".  A text-only contract test cannot see that, and it
    only surfaces when an operator actually runs ``install`` -- so it is asserted
    here directly.
    """

    # The param block contains nested parentheses (attribute arguments such as
    # `[Parameter(Mandatory = $true)]`), so it needs a balanced scan -- splitting
    # on the first ")" would capture only that attribute.
    start = tooling_text.index("param(") + len("param(")
    depth = 1
    index = start
    while depth > 0:
        if tooling_text[index] == "(":
            depth += 1
        elif tooling_text[index] == ")":
            depth -= 1
        index += 1
    param_block = tooling_text[start:index - 1]
    body = tooling_text[index:]

    parameters = set()
    for line in param_block.splitlines():
        # A parameter declaration is the LAST $name on its line; anything before
        # it belongs to an attribute (e.g. `Mandatory = $true`).
        names = re.findall(r"\$(\w+)", line)
        if not names:
            continue
        if re.search(r"\$(\w+)\s*(=|,|$)", line):
            parameters.add(names[-1].lower())
    assert {"action", "taskname", "reporoot", "force"} <= parameters, parameters

    assignments = {match.group(1).lower()
                   for match in re.finditer(r"^\s*\$(\w+)\s*=", body,
                                            re.MULTILINE)}
    collisions = sorted(assignments & parameters)
    assert collisions == [], (
        f"local assignment(s) shadow a validated script parameter: {collisions}")


def test_tooling_parses_as_powershell():
    """A syntax error would only surface at operator time otherwise."""

    import subprocess

    script = (
        "$err = $null; "
        "$null = [System.Management.Automation.Language.Parser]::ParseFile("
        f"'{TOOLING}', [ref]$null, [ref]$err); "
        "if ($err.Count -gt 0) { exit 1 } else { exit 0 }")
    completed = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
        capture_output=True, text=True, timeout=120.0, check=False)
    assert completed.returncode == 0, completed.stdout + completed.stderr


def test_default_task_name_matches_the_watchdog_config():
    from PHX2.watchdog.config import DEFAULT_TASK_NAME
    assert DEFAULT_TASK_NAME == "PHX2-Watchdog"
    assert '$TaskName = "PHX2-Watchdog"' in TOOLING.read_text(encoding="utf-8")

# phx2_watchdog_task.ps1 -- Windows autostart registration for the PHX2 watchdog.
#
# Built-in Windows Task Scheduler ONLY. Nothing is installed: no NSSM, no
# third-party service wrapper, no new Python package, no Docker, no WSL service.
#
# The task's action is exactly:
#   <repo>\.venv\Scripts\pythonw.exe -m PHX2.watchdog run
# with the repository root as the working directory. pythonw.exe (the WINDOWLESS
# interpreter) is deliberate: launched by Task Scheduler, python.exe attaches to
# a console shared with the launcher and producer, and a single console/session
# control event then fells the whole tree with STATUS_CONTROL_C_EXIT
# (0xC000013A). A consoleless watchdog cannot receive such an event; combined
# with the CREATE_NO_WINDOW launcher spawn, no part of the supervised tree shares
# a visible console. Operator status/stop/validate run separately with python.exe
# so their output stays visible. The command line carries NO credential, NO Telegram
# bot token and NO chat id -- the producer reads those from the active repository
# .env through the normal configuration loader, and the watchdog never touches
# them at all.
#
# The WATCHDOG remains the authoritative restart controller. The task therefore
# does NOT use Task Scheduler's restart-on-failure feature: that would restart a
# watchdog whose circuit breaker had deliberately opened, defeating the breaker.
# The task's only job is to start ONE watchdog at logon.
#
# Actions:
#   install    register (or deterministically upgrade) the managed task, DISABLED
#   uninstall  remove the managed task
#   enable     enable the managed task
#   disable    disable the managed task
#   start      start the enabled managed task
#   status     print the task's managed-schema conformance and state
#
# install/enable/disable/uninstall are idempotent: running one twice leaves the
# same end state and reports what it did.

[CmdletBinding()]
param(
  [Parameter(Mandatory = $true, Position = 0)]
  [ValidateSet("install", "uninstall", "enable", "disable", "start", "status")]
  [string]$Action,

  [string]$TaskName = "PHX2-Watchdog",
  [string]$RepoRoot = "C:\Users\BalaC\Downloads\Phoenix_PHX2",
  [switch]$Force
)

$ErrorActionPreference = "Continue"

# WINDOWLESS interpreter for the registered action: a consoleless watchdog
# cannot be felled by a Task-Scheduler console/session control event.
$WatchdogExe  = Join-Path $RepoRoot ".venv\Scripts\pythonw.exe"
$ModuleArgs   = "-m PHX2.watchdog run"
$ManagedMark  = "PHX2 Stage 10 managed watchdog task. Authoritative restart control lives in the watchdog circuit breaker, not in Task Scheduler."
$RegistryFile = Join-Path "C:\Users\BalaC\phx2_watchdog" "service_registration.json"

function Write-Result([hashtable]$fields) {
  foreach ($k in ($fields.Keys | Sort-Object)) {
    Write-Host ("{0}={1}" -f $k, $fields[$k])
  }
}

function Get-ManagedTask {
  try { return Get-ScheduledTask -TaskName $TaskName -ErrorAction Stop } catch { return $null }
}

function Test-ManagedSchema($task) {
  # Does an existing task match the schema this script manages?
  $result = [ordered]@{
    action_count_ok      = $false
    executable_ok        = $false
    arguments_ok         = $false
    working_dir_ok       = $false
    trigger_ok           = $false
    single_instance_ok   = $false
    no_restart_on_fail   = $false
    hidden_ok             = $false
    description_ok       = $false
    no_secret_in_command = $true
  }
  if ($null -eq $task) { return $result }

  $actions = @($task.Actions)
  $result.action_count_ok = ($actions.Count -eq 1)
  if ($actions.Count -ge 1) {
    $a = $actions[0]
    $result.executable_ok  = ($a.Execute -eq $WatchdogExe)
    $result.arguments_ok   = ($a.Arguments -eq $ModuleArgs)
    $result.working_dir_ok = ($a.WorkingDirectory -eq $RepoRoot)
    $combined = "$($a.Execute) $($a.Arguments)"
    if ($combined -match '\d{6,}:[A-Za-z0-9_\-]{30,}') { $result.no_secret_in_command = $false }
    if ($combined -match '(?i)PHX2_TELEGRAM_BOT_TOKEN|PHX2_TELEGRAM_CHAT_ID|discord\.com/api/webhooks') {
      $result.no_secret_in_command = $false
    }
  }
  $triggers = @($task.Triggers)
  $result.trigger_ok = ($triggers.Count -eq 1 -and $triggers[0].CimClass.CimClassName -eq "MSFT_TaskLogonTrigger")
  $result.single_instance_ok = ($task.Settings.MultipleInstances -eq "IgnoreNew")
  $result.no_restart_on_fail = ($task.Settings.RestartCount -eq 0)
  $result.hidden_ok = ($task.Settings.Hidden -eq $true)
  $result.description_ok = ($task.Description -eq $ManagedMark)
  return $result
}

function Write-Registration([string]$state, $schema) {
  try {
    $dir = Split-Path -Parent $RegistryFile
    if ($dir) { New-Item -ItemType Directory -Force $dir | Out-Null }
    $doc = [ordered]@{
      kind                  = "PHX2_WATCHDOG_SERVICE_REGISTRATION"
      schema_version        = "PHX2_WATCHDOG_SERVICE_REGISTRATION_V1"
      task_name             = $TaskName
      updated_at_utc        = ([DateTime]::UtcNow.ToString("yyyy-MM-ddTHH:mm:ssZ"))
      registration_state    = $state
      trigger               = "AT_USER_LOGON"
      run_level             = "LIMITED"
      multiple_instances    = "IgnoreNew"
      restart_on_failure    = $false
      authoritative_restart_controller = "PHX2_WATCHDOG_CIRCUIT_BREAKER"
      secrets_in_command    = $false
      managed_schema_checks = $schema
    }
    ($doc | ConvertTo-Json -Depth 5) | Out-File -LiteralPath $RegistryFile -Encoding utf8
  } catch { }
}

switch ($Action) {

  "status" {
    $task = Get-ManagedTask
    $schema = Test-ManagedSchema $task
    $state = "ABSENT"
    if ($null -ne $task) { $state = [string]$task.State }
    $conforms = $true
    foreach ($k in $schema.Keys) { if (-not $schema[$k]) { $conforms = $false } }
    Write-Result @{
      task_name          = $TaskName
      task_present       = ($null -ne $task)
      task_state         = $state
      managed_schema_ok  = $conforms
      watchdog_exe_exists = (Test-Path -LiteralPath $WatchdogExe)
    }
    foreach ($k in ($schema.Keys | Sort-Object)) { Write-Host ("  schema_{0}={1}" -f $k, $schema[$k]) }
    # Read-only by contract: `python main.py status` routes through this action,
    # so status must not refresh or otherwise mutate service_registration.json.
    $global:LASTEXITCODE = 0
    return
  }

  "install" {
    if (-not (Test-Path -LiteralPath $WatchdogExe)) {
      Write-Result @{ installed = $false; refusal = "REPO_VENV_PYTHONW_NOT_FOUND" }
      $global:LASTEXITCODE = 2
      return
    }
    if (-not (Test-Path -LiteralPath $RepoRoot)) {
      Write-Result @{ installed = $false; refusal = "REPO_ROOT_NOT_FOUND" }
      $global:LASTEXITCODE = 2
      return
    }

    $existing = Get-ManagedTask
    if ($null -ne $existing) {
      $schema = Test-ManagedSchema $existing
      $conforms = $true
      foreach ($k in $schema.Keys) { if (-not $schema[$k]) { $conforms = $false } }
      if (-not $conforms -and -not $Force) {
        # An unrelated task of the same name must NOT be silently overwritten.
        Write-Result @{
          installed = $false
          refusal   = "EXISTING_TASK_DOES_NOT_MATCH_MANAGED_SCHEMA"
          hint      = "inspect it, then re-run with -Force to deterministically upgrade"
        }
        foreach ($k in ($schema.Keys | Sort-Object)) { Write-Host ("  schema_{0}={1}" -f $k, $schema[$k]) }
        $global:LASTEXITCODE = 2
        return
      }
      if ($existing.State -eq "Running") {
        try { Stop-ScheduledTask -TaskName $TaskName -ErrorAction Stop } catch { }
      }
      Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
    }

    # NOTE: these locals must NOT be named $action / $Action. PowerShell variable
    # names are case-insensitive, so $action IS the script's [ValidateSet] -bound
    # $Action parameter, and assigning a CimInstance to it fails validation with
    # "MSFT_TaskExecAction is not a valid value for the Action variable".
    $taskAction = New-ScheduledTaskAction -Execute $WatchdogExe -Argument $ModuleArgs -WorkingDirectory $RepoRoot
    $trigger = New-ScheduledTaskTrigger -AtLogOn -User ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name)
    # MultipleInstances=IgnoreNew: Task Scheduler will not start a second copy
    # while one is running. RestartCount=0: the watchdog's circuit breaker -- not
    # the scheduler -- decides whether anything restarts.
    $settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew `
      -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
      -StartWhenAvailable -Hidden -ExecutionTimeLimit ([TimeSpan]::Zero)
    $settings.DisallowStartIfOnBatteries = $false
    $settings.RestartCount = 0
    $settings.RestartInterval = $null
    # LIMITED run level: no highest-privilege request. Nothing in the watchdog
    # needs elevation, and the producer runs as the ordinary operator account.
    $principal = New-ScheduledTaskPrincipal `
      -UserId ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name) `
      -LogonType Interactive -RunLevel Limited

    try {
      Register-ScheduledTask -TaskName $TaskName -Action $taskAction -Trigger $trigger `
        -Settings $settings -Principal $principal -Description $ManagedMark `
        -Force -ErrorAction Stop | Out-Null
    } catch {
      Write-Result @{ installed = $false; refusal = "REGISTER_FAILED" }
      Write-Host ("  detail=" + $_.Exception.GetType().Name)
      $global:LASTEXITCODE = 3
      return
    }

    # Stage 10 ends with the task INSTALLED but DISABLED. Stage 11 enables it.
    try { Disable-ScheduledTask -TaskName $TaskName -ErrorAction Stop | Out-Null } catch { }

    $task = Get-ManagedTask
    $schema = Test-ManagedSchema $task
    $conforms = $true
    foreach ($k in $schema.Keys) { if (-not $schema[$k]) { $conforms = $false } }
    Write-Registration ([string]$task.State) $schema
    Write-Result @{
      installed         = $true
      task_name         = $TaskName
      task_state        = [string]$task.State
      managed_schema_ok = $conforms
      left_disabled     = ($task.State -eq "Disabled")
    }
    foreach ($k in ($schema.Keys | Sort-Object)) { Write-Host ("  schema_{0}={1}" -f $k, $schema[$k]) }
    $global:LASTEXITCODE = 0
    return
  }

  "enable" {
    $task = Get-ManagedTask
    if ($null -eq $task) {
      Write-Result @{ enabled = $false; refusal = "TASK_ABSENT" }
      $global:LASTEXITCODE = 2
      return
    }
    try { Enable-ScheduledTask -TaskName $TaskName -ErrorAction Stop | Out-Null } catch { }
    $task = Get-ManagedTask
    Write-Registration ([string]$task.State) (Test-ManagedSchema $task)
    Write-Result @{ enabled = ($task.State -ne "Disabled"); task_state = [string]$task.State }
    $global:LASTEXITCODE = 0
    return
  }

  "start" {
    $task = Get-ManagedTask
    if ($null -eq $task) {
      Write-Result @{ started = $false; refusal = "TASK_ABSENT" }
      $global:LASTEXITCODE = 2
      return
    }
    $schema = Test-ManagedSchema $task
    $conforms = $true
    foreach ($k in $schema.Keys) { if (-not $schema[$k]) { $conforms = $false } }
    if (-not $conforms) {
      Write-Result @{ started = $false; refusal = "TASK_SCHEMA_INVALID" }
      $global:LASTEXITCODE = 2
      return
    }
    if ($task.State -eq "Disabled") {
      Write-Result @{ started = $false; refusal = "TASK_DISABLED" }
      $global:LASTEXITCODE = 2
      return
    }
    try {
      Start-ScheduledTask -TaskName $TaskName -ErrorAction Stop
    } catch {
      Write-Result @{ started = $false; refusal = "TASK_START_FAILED" }
      $global:LASTEXITCODE = 3
      return
    }
    $task = Get-ManagedTask
    Write-Registration ([string]$task.State) $schema
    Write-Result @{
      started           = $true
      task_state        = [string]$task.State
      managed_schema_ok = $conforms
    }
    $global:LASTEXITCODE = 0
    return
  }

  "disable" {
    $task = Get-ManagedTask
    if ($null -eq $task) {
      Write-Result @{ disabled = $false; refusal = "TASK_ABSENT" }
      $global:LASTEXITCODE = 2
      return
    }
    if ($task.State -eq "Running") {
      try { Stop-ScheduledTask -TaskName $TaskName -ErrorAction Stop } catch { }
    }
    try { Disable-ScheduledTask -TaskName $TaskName -ErrorAction Stop | Out-Null } catch { }
    $task = Get-ManagedTask
    Write-Registration ([string]$task.State) (Test-ManagedSchema $task)
    Write-Result @{ disabled = ($task.State -eq "Disabled"); task_state = [string]$task.State }
    $global:LASTEXITCODE = 0
    return
  }

  "uninstall" {
    $task = Get-ManagedTask
    if ($null -eq $task) {
      Write-Result @{ uninstalled = $true; note = "TASK_ALREADY_ABSENT" }
      $global:LASTEXITCODE = 0
      return
    }
    $schema = Test-ManagedSchema $task
    $conforms = $true
    foreach ($k in $schema.Keys) { if (-not $schema[$k]) { $conforms = $false } }
    if (-not $conforms -and -not $Force) {
      Write-Result @{
        uninstalled = $false
        refusal     = "EXISTING_TASK_DOES_NOT_MATCH_MANAGED_SCHEMA"
        hint        = "inspect it, then re-run with -Force"
      }
      $global:LASTEXITCODE = 2
      return
    }
    if ($task.State -eq "Running") {
      try { Stop-ScheduledTask -TaskName $TaskName -ErrorAction Stop } catch { }
    }
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
    $gone = ($null -eq (Get-ManagedTask))
    Write-Registration "ABSENT" $schema
    Write-Result @{ uninstalled = $gone; task_name = $TaskName }
    $global:LASTEXITCODE = 0
    return
  }
}

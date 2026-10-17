"""The tracked source of truth for ``launch_live_24x7.ps1``.

The launcher itself lives OUT of the repository (it is operator glue in
``C:\\Users\\BalaC\\phx2_production_private_live``), but Stage 10 requires it to
be reproducible and auditable, so its exact text is generated from here and can
be re-deployed byte-for-byte with
``python -m PHX2.scripts.phx2_deploy_live_launcher``.

Two design points deserve stating.

**Indefinite runtime is explicit, never faked.**  The launcher passes
``--run-forever``.  It does NOT pass a very large ``--max-runtime-seconds``, does
not relaunch itself, and is not re-invoked by the watchdog on a duration
boundary: a timeout would end a perfectly healthy producer at an arbitrary
instant and the watchdog would then restart it for no reason.

**The paid-ledger pin stays a real pin.**  ``--require-baseline`` is an EXACT
match in the producer's arm gate, so a static pin would refuse every launch after
the very first real send -- which would make 24/7 operation impossible.  The
launcher instead proves the pinned baseline is still a byte-for-byte PREFIX of
the current ledger (same first ``N`` bytes, same digest, line count not
decreased) and only then passes the ledger's CURRENT baseline.  Forward-only
append is permitted; any rewrite, truncation or divergence refuses the launch
before a single provider object exists.  The pinned history therefore remains
operator-asserted, exactly as before.

No secret is ever written into this file, into the command line, into the
manifest, or into the transcript.  The Telegram bot token and chat id reach the
producer ONLY through the active repository ``.env`` and the normal
configuration loader.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any, Dict, List

from PHX2.free_tier_producer.launcher_contract import (
    CANONICAL_ALERT_POLICY,
    CANONICAL_ALERT_POLICY_CLI,
    CANONICAL_CURSOR_STATE_DIR,
    CANONICAL_DISCOVERY_MODE,
    CANONICAL_GAP_RECOVERY_MODE,
    CANONICAL_LEDGER_PATH,
    CANONICAL_LOGS_ROOT,
    CANONICAL_MIGRATION_SOURCE_MODE,
    CANONICAL_PROVIDER_MODE,
    CANONICAL_RUNS_ROOT,
    REPO_PYTHON,
    REPO_ROOT,
    TRACKED_PRODUCTION_MODULE,
)
from PHX2.free_tier_producer.market_budget import (
    MARKET_BUDGET_MODE_UNBOUNDED,
)
from PHX2.free_tier_producer.phx1_parity_policy import (
    normalize_alert_policy,
)

#: The ACTIVE repository environment file. Deliberately NOT
#: ``C:\Users\BalaC\Documents\phx2.env``: Stage 10 pins the repository ``.env``
#: as the single active configuration source.
ACTIVE_ENV_PATH = str(Path(REPO_ROOT) / ".env")

LIVE_RUN_ID = "paid_primary_live_24x7"

#: Where the arm-gate confirm token is defined. Fetched by the launcher at run
#: time, held in a PowerShell variable, never logged and never written down.
CONFIRM_TOKEN_MODULE = "PHX2.stage30.stage30_11_16_real_send_models"
CONFIRM_TOKEN_SYMBOL = "STAGE30_11_16_AUTHORIZATION_CONFIRM_TOKEN"

LIVE_LAUNCHER_BASENAME = "launch_live_24x7.ps1"

#: Historical block replay and non-Helius candidate backfill are permanently
#: absent from the Helius-primary production launcher.
_TEMPLATE = r'''# launch_live_24x7.ps1 -- CANONICAL PHX2 INDEFINITE TELEGRAM-ONLY LIVE LAUNCHER.
#
# GENERATED FILE. The tracked source of truth is
#   PHX2/watchdog/launcher_template.py
# Re-deploy byte-for-byte with
#   .venv\Scripts\python.exe -m PHX2.scripts.phx2_deploy_live_launcher --write
# Editing this file by hand makes it diverge from the audited template and the
# watchdog will refuse to start it (launcher sha256 / pinned HEAD mismatch).
#
# ROLE
#   The ONE armed delivery owner for continuous PHX2 operation. Started by the
#   PHX2 watchdog (python -m PHX2.watchdog run) or, identically, by an operator.
#   Accepted finding M-2 stays closed: main.py / the production supervisor are
#   NOT a route to an armed producer and appear nowhere below.
#
# RUNTIME
#   --run-forever. No clock boundary at all. This is NOT a large timeout and NOT
#   a self-relaunch loop: creating the cooperative stop file (or Ctrl-C in this
#   console) ends the run through the ordinary shutdown path, leaving zero
#   processes and zero locks.
#   --max-sends-per-run 0: the managed 24/7 producer has NO per-run send
#   ceiling -- a run-forever service must never terminate merely because N
#   alerts were sent (2026-07-27: the 3-send cap ended a healthy run and the
#   forced restart wiped candidate state). Bounded acceptance ceremonies keep
#   their own explicit positive caps. Every per-send gate -- dedupe, sent-tier
#   monotonicity, risk, market completeness, crossing-tick block and the
#   inter-send cooldown -- still applies to each individual dispatch.
#
# DELIVERY
#   Telegram ONLY, exactly one send-capable transport flag. No retired-transport
#   arm flag of any kind. PHX2_DISCORD_ENABLED=false in the active env keeps any
#   legacy webhook value inert. No bot token and no chat id ever reaches this
#   command line, this transcript, or the startup manifest.
#
# LEDGER PIN
#   $PIN_BASELINE below is the operator-asserted paid-primary baseline. Because
#   the producer's arm gate compares it EXACTLY, a static pin would refuse every
#   launch after the first real send. This launcher therefore proves the pinned
#   baseline is still a byte-for-byte PREFIX of the current ledger and then
#   passes the CURRENT baseline. Forward-only append is allowed; a rewrite, a
#   truncation or any divergence REFUSES the launch before any provider object
#   exists.
param(
  [string]$RunStamp = "",
  [string]$ManifestPath = "",
  [int]$WatchdogPid = 0
)

$ErrorActionPreference = "Continue"

$PY        = "__REPO_PYTHON__"
$REPO_ROOT = "__REPO_ROOT__"
$MODULE    = "__MODULE__"
$ENV_PATH  = "__ENV_PATH__"
$SOURCE_MODE = "__SOURCE_MODE__"

# Non-secret pins (a git sha and a ledger digest -- NEITHER is a secret).
$PIN_HEAD     = "__PIN_HEAD__"
$PIN_BASELINE = "__PIN_BASELINE__"

# FRESH UNIQUE run + log directories on EVERY invocation. A static literal would
# silently mix a new run's evidence with an older run's.
if ([string]::IsNullOrWhiteSpace($RunStamp)) {
  $RunStamp = (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ")
}
$RUN_ID  = "__RUN_ID___$RunStamp"
$out     = Join-Path "__RUNS_ROOT__" $RUN_ID
$logDir  = Join-Path "__LOGS_ROOT__" $RUN_ID

# STABLE durable state. The gRPC cursor, the recovery state, the census and the
# transport watermark live HERE and never rotate with $out.
$STATE_DIR = "__STATE_DIR__"
$LEDGER    = "__LEDGER_PATH__"

# Cooperative stop file, unique to THIS run so a stale one can never pre-stop a
# later launch. The watchdog creates it to request a clean shutdown.
$STOP_FILE = Join-Path $logDir "STOP_REQUESTED"

New-Item -ItemType Directory -Force $out       | Out-Null
New-Item -ItemType Directory -Force $logDir    | Out-Null
New-Item -ItemType Directory -Force $STATE_DIR | Out-Null

$consoleLog = Join-Path $logDir "console.log"
$consoleErr = Join-Path $logDir "console.err"
$transcript = Join-Path $logDir "wrapper_transcript.txt"

$Utf8NoBom = New-Object System.Text.UTF8Encoding($false)
function Write-WT([string]$msg) {
  $line = ("{0}  {1}" -f ([DateTime]::UtcNow.ToString("o")), $msg)
  [System.IO.File]::AppendAllText($transcript, $line + [Environment]::NewLine, $Utf8NoBom)
}

$launcherPath = $MyInvocation.MyCommand.Path
$launcherHash = ""
if ($launcherPath) {
  try { $launcherHash = (Get-FileHash -LiteralPath $launcherPath -Algorithm SHA256).Hash.ToLower() } catch { $launcherHash = "" }
}

Write-WT "WRAPPER_START pid=$PID run_id=$RUN_ID"
Write-WT "runtime_contract=RUN_FOREVER"
Write-WT "delivery_transport=TELEGRAM discord=false"
Write-WT "phx1_structural_policy=shadow"
Write-WT "alert_policy=__ALERT_POLICY_CLI__"
Write-WT "migration_source_mode=$SOURCE_MODE primary=HELIUS recovery=HELIUS_HTTP shadow=DISABLED"
Write-WT "pin_expected_head=$PIN_HEAD"
Write-WT "pin_baseline_prefix=$PIN_BASELINE"
Write-WT "watchdog_parent_pid=$WatchdogPid"
Write-WT "secrets_policy=token_chat_id_and_env_values_NEVER_logged_or_passed_on_argv"

function Fail-Launch([string]$reason) {
  Write-WT "WRAPPER_ABORT reason=$reason"
  Write-Host "LAUNCH REFUSED: $reason"
  $global:LASTEXITCODE = 2
}

if (!(Test-Path -LiteralPath $PY))        { Fail-Launch "PYTHON_NOT_FOUND";        return }
if (!(Test-Path -LiteralPath $REPO_ROOT)) { Fail-Launch "REPO_ROOT_NOT_FOUND";     return }
if (!(Test-Path -LiteralPath $ENV_PATH))  { Fail-Launch "ACTIVE_ENV_NOT_FOUND";    return }
if (!(Test-Path -LiteralPath (Join-Path $REPO_ROOT "PHX2\free_tier_producer\free_tier_session.py"))) {
  Fail-Launch "TRACKED_MODULE_NOT_FOUND"; return
}
if (!(Test-Path -LiteralPath $LEDGER))    { Fail-Launch "CANONICAL_LEDGER_NOT_FOUND"; return }

# ---- forward-only ledger baseline proof --------------------------------------
# The pinned baseline must still be an exact byte prefix of the live ledger.
$pinParts = $PIN_BASELINE.Split(":")
if ($pinParts.Count -ne 3) { Fail-Launch "PIN_BASELINE_MALFORMED"; return }
$pinSha   = $pinParts[0].ToLower()
$pinBytes = [int]$pinParts[1]
$pinLines = [int]$pinParts[2]

$ledgerBytesAll = [System.IO.File]::ReadAllBytes($LEDGER)
if ($ledgerBytesAll.Length -lt $pinBytes) { Fail-Launch "LEDGER_SHORTER_THAN_PINNED_BASELINE"; return }
$prefix = New-Object byte[] $pinBytes
[System.Array]::Copy($ledgerBytesAll, 0, $prefix, 0, $pinBytes)
$sha = New-Object System.Security.Cryptography.SHA256Managed
$prefixSha = (($sha.ComputeHash($prefix)) | ForEach-Object { $_.ToString("x2") }) -join ""
if ($prefixSha -ne $pinSha) { Fail-Launch "LEDGER_PINNED_PREFIX_DIVERGED"; return }

$currentSha   = (Get-FileHash -LiteralPath $LEDGER -Algorithm SHA256).Hash.ToLower()
$currentBytes = $ledgerBytesAll.Length
$currentLines = 0
foreach ($b in $ledgerBytesAll) { if ($b -eq 10) { $currentLines++ } }
if ($currentLines -lt $pinLines) { Fail-Launch "LEDGER_LINE_COUNT_REGRESSED"; return }
$CURRENT_BASELINE = "$currentSha`:$currentBytes`:$currentLines"
Write-WT "ledger_baseline_current=$CURRENT_BASELINE forward_extension_proven=True"

# ---- confirm token: held in memory; NEVER printed or logged ------------------
$tok = & $PY -c "import sys; sys.path.insert(0, r'__REPO_ROOT__'); from __CONFIRM_MODULE__ import __CONFIRM_SYMBOL__ as t; sys.stdout.write(t)"
if ([string]::IsNullOrWhiteSpace($tok)) { Fail-Launch "CONFIRM_TOKEN_EMPTY"; return }
Write-WT "token_acquired=True (value NOT logged)"

# ---- redaction-safe startup manifest ----------------------------------------
$manifestHash = ""
if (-not [string]::IsNullOrWhiteSpace($ManifestPath)) {
  $manifestDir = Split-Path -Parent $ManifestPath
  if ($manifestDir) { New-Item -ItemType Directory -Force $manifestDir | Out-Null }
  $manifest = [ordered]@{
    kind                    = "PHX2_LIVE_24X7_STARTUP_MANIFEST"
    schema_version          = "PHX2_LIVE_24X7_MANIFEST_V2"
    run_id                  = $RUN_ID
    run_stamp               = $RunStamp
    started_at_utc          = ([DateTime]::UtcNow.ToString("yyyy-MM-ddTHH:mm:ssZ"))
    wrapper_pid             = $PID
    watchdog_parent_pid     = $WatchdogPid
    pinned_repo_head        = $PIN_HEAD
    launcher_sha256         = $launcherHash
    runtime_contract        = "RUN_FOREVER"
    market_budget_mode      = "UNBOUNDED"
    market_budget_limit     = "UNBOUNDED"
    delivery_transport      = "TELEGRAM"
    telegram_enabled        = $true
    discord_enabled         = $false
    structural_policy       = "SHADOW"
    alert_policy            = "__ALERT_POLICY__"
    provider_mode           = "__PROVIDER_MODE__"
    discovery_mode          = "__DISCOVERY_MODE__"
    migration_source_mode   = $SOURCE_MODE
    primary_migration_source = "HELIUS"
    primary_recovery        = "HELIUS_HTTP"
    shadow_source           = "DISABLED"
    chainstack_configured_for_runtime = $false
    chainstack_connected    = $false
    chainstack_comparator   = $false
    source_owners           = 1
    candidate_pipeline_owners = 1
    telegram_owners         = 1
    delivery_transaction_owners = 1
    paid_ledger_writers     = 1
    chainstack_candidate_authority = $false
    chainstack_send_authority = $false
    chainstack_ledger_authority = $false
    helius_http_recovery_enabled = $true
    wallet_signing_enabled  = $false
    trading_enabled         = $false
    run_dir                 = $out
    log_dir                 = $logDir
    stop_file               = $STOP_FILE
    cursor_state_dir        = $STATE_DIR
    ledger_path             = $LEDGER
    ledger_baseline_pinned  = $PIN_BASELINE
    ledger_baseline_current = $CURRENT_BASELINE
  }
  # BOM-less UTF-8. `Out-File -Encoding utf8` on Windows PowerShell 5.1 writes a
  # BOM, which makes strict json.loads reject the document; the watchdog reads
  # with utf-8-sig as well, so this is belt AND braces.
  $manifestJson = ($manifest | ConvertTo-Json -Depth 4)
  [System.IO.File]::WriteAllText($ManifestPath, $manifestJson, $Utf8NoBom)
  try { $manifestHash = (Get-FileHash -LiteralPath $ManifestPath -Algorithm SHA256).Hash.ToLower() } catch { $manifestHash = "" }
  Write-WT "startup_manifest_written=True"
}

# Non-secret run-instance evidence is inherited by the producer. It is kept out
# of argv so process matching remains stable and no operator value is copied to
# a command line. These fields never authorize policy; they only distinguish a
# clean process/run rollover from corruption of the durable identity below.
$env:PHX2_RUN_INSTANCE_WATCHDOG_PID = [string]$WatchdogPid
$env:PHX2_RUN_INSTANCE_LAUNCHER_SHA256 = $launcherHash
$env:PHX2_RUN_INSTANCE_MANIFEST_SHA256 = $manifestHash
$env:PHX2_RUN_INSTANCE_NONCE = $RUN_ID
$env:PHX2_MIGRATION_SOURCE_MODE = "__SOURCE_MODE__"

# ---- EXACT runner arg list ---------------------------------------------------
# DELIVERY: Telegram ONLY. Exactly one send-capable transport flag appears here.
$argList = @(
  "-u",
  "-m", $MODULE,
  "--run",
  "--enable-telegram",
  "--ack-live-free-tier",
  "--i-understand-this-can-send",
  "--confirm-token", $tok,
  "--require-baseline", $CURRENT_BASELINE,
  "--ledger-path", $LEDGER,
  "--env", $ENV_PATH,
  "--expected-head", $PIN_HEAD,
  "--phx1-structural-policy", "shadow",
  "--alert-policy", "__ALERT_POLICY_CLI__",
  "--provider-mode", "__PROVIDER_MODE__",
  "--discovery-mode", "__DISCOVERY_MODE__",
  "--migration-source-mode", $SOURCE_MODE,
  "--enable-helius-http-recovery",
  "--enable-dexscreener-restart-backfill",
  "--require-production-grpc",
  "--cursor-state-dir", $STATE_DIR,
  "--grpc-gap-recovery", "__GAP_RECOVERY_MODE__",
  "--run-forever",
  "--max-sends-per-run", "0",
  # UNBOUNDED market-request budget, stated explicitly and never inherited.
  # The 2026-08-02 five-hour run omitted this flag, silently took the bounded
  # base default of 5,000, exhausted it 22 minutes after launch and spent the
  # remaining 4h38m unable to observe the market at all while still reporting
  # itself alive. A run-forever deployment must not carry a non-refilling
  # lifetime spend boundary; physical provider requests are counted and
  # reported, never capped.
  "--max-market-requests-total", "0",
  "--max-seed-runtime", "300",
  "--stop-file", $STOP_FILE,
  "--out-dir", $out
)

$exitCode = $null
$childExitCaptured = $false
try {
  Push-Location -LiteralPath $REPO_ROOT
  Write-WT "CHILD_START foreground=True cwd=$REPO_ROOT streams=console.log/console.err"
  & $PY @argList 1> $consoleLog 2> $consoleErr
  $exitCode = $LASTEXITCODE
  $childExitCaptured = $true
  Write-WT "CHILD_EXITED exit_code=$exitCode"
}
finally {
  try { Pop-Location } catch { }
  if (-not $childExitCaptured) {
    Write-WT "WRAPPER_INTERRUPTED no_child_exit_captured"
    # No send-capable orphan. Matched by parent PID + image name ONLY (never by
    # command line, which carries the confirm token).
    try {
      $kids = @(Get-CimInstance Win32_Process -Filter "ParentProcessId=$PID AND Name='python.exe'" -ErrorAction SilentlyContinue)
      if ($kids.Count -eq 0) {
        Write-WT "WRAPPER_INTERRUPTED no_live_runner_child_found"
      } else {
        foreach ($k in $kids) {
          Write-WT "WRAPPER_INTERRUPTED stopping_runner_child child_pid=$($k.ProcessId)"
          Stop-Process -Id $k.ProcessId -Force -ErrorAction SilentlyContinue
        }
      }
    } catch {
      Write-WT ("WRAPPER_INTERRUPTED orphan_check_error " + $_.Exception.Message)
    }
  }
  if ($null -eq $exitCode) { $exitCode = -1 }
  try {
    ("PROD_LIVE_EXIT_CODE=$exitCode") | Out-File -LiteralPath $consoleLog -Append -Encoding Unicode
  } catch { }
  Write-WT "PROD_LIVE_EXIT_CODE=$exitCode"
  Write-WT "WRAPPER_END recorded_exit_code=$exitCode"
  $global:LASTEXITCODE = $exitCode
}
'''


def render_live_launcher(*, expected_head: str, ledger_baseline: str) -> str:
    """The exact ``launch_live_24x7.ps1`` text for one pinned commit."""

    head = str(expected_head).strip().lower()
    baseline = str(ledger_baseline).strip()
    text = _TEMPLATE
    replacements = {
        "__REPO_PYTHON__": REPO_PYTHON,
        "__REPO_ROOT__": REPO_ROOT,
        "__MODULE__": TRACKED_PRODUCTION_MODULE,
        "__ENV_PATH__": ACTIVE_ENV_PATH,
        "__PIN_HEAD__": head,
        "__PIN_BASELINE__": baseline,
        "__RUN_ID__": LIVE_RUN_ID,
        "__RUNS_ROOT__": CANONICAL_RUNS_ROOT,
        "__LOGS_ROOT__": CANONICAL_LOGS_ROOT,
        "__STATE_DIR__": CANONICAL_CURSOR_STATE_DIR,
        "__LEDGER_PATH__": CANONICAL_LEDGER_PATH,
        "__PROVIDER_MODE__": CANONICAL_PROVIDER_MODE,
        "__DISCOVERY_MODE__": CANONICAL_DISCOVERY_MODE,
        "__SOURCE_MODE__": CANONICAL_MIGRATION_SOURCE_MODE,
        "__GAP_RECOVERY_MODE__": CANONICAL_GAP_RECOVERY_MODE,
        # Longest-token-first ordering matters: "__ALERT_POLICY__" is a prefix
        # of "__ALERT_POLICY_CLI__", so a plain dict iteration that replaced
        # the short token first would corrupt the long one into "PHX1_PARITY_CLI".
        "__ALERT_POLICY_CLI__": CANONICAL_ALERT_POLICY_CLI,
        "__ALERT_POLICY__": CANONICAL_ALERT_POLICY,
        "__CONFIRM_MODULE__": CONFIRM_TOKEN_MODULE,
        "__CONFIRM_SYMBOL__": CONFIRM_TOKEN_SYMBOL,
    }
    for token in sorted(replacements, key=len, reverse=True):
        text = text.replace(token, replacements[token])
    return text


def render_live_launcher_bytes(*, expected_head: str,
                               ledger_baseline: str) -> bytes:
    """UTF-8 (BOM-less), CRLF-free deterministic bytes for deployment."""

    return render_live_launcher(
        expected_head=expected_head,
        ledger_baseline=ledger_baseline).encode("utf-8")


def live_launcher_sha256(*, expected_head: str, ledger_baseline: str) -> str:
    return hashlib.sha256(render_live_launcher_bytes(
        expected_head=expected_head, ledger_baseline=ledger_baseline)).hexdigest()


# --------------------------------------------------------------------------- #
# offline contract checks (the same predicate a test and an operator both use)
# --------------------------------------------------------------------------- #

REFUSAL_TELEGRAM_COUNT = "LIVE_LAUNCHER_TELEGRAM_FLAG_COUNT_NOT_ONE"
REFUSAL_DISCORD_PRESENT = "LIVE_LAUNCHER_DISCORD_ARM_PRESENT"
REFUSAL_SHADOW_MISSING = "LIVE_LAUNCHER_STRUCTURAL_SHADOW_MISSING"
REFUSAL_RUN_FOREVER_MISSING = "LIVE_LAUNCHER_RUN_FOREVER_MISSING"
REFUSAL_TIMEOUT_SIMULATION = "LIVE_LAUNCHER_SIMULATED_INDEFINITE_RUNTIME"
REFUSAL_FRESH_DIRS_MISSING = "LIVE_LAUNCHER_FRESH_RUN_DIRS_MISSING"
REFUSAL_STATE_DIR_UNSTABLE = "LIVE_LAUNCHER_STATE_DIR_NOT_STABLE"
REFUSAL_LEDGER_NOT_CANONICAL = "LIVE_LAUNCHER_LEDGER_NOT_CANONICAL"
REFUSAL_ENV_NOT_ACTIVE = "LIVE_LAUNCHER_ENV_NOT_ACTIVE_REPO_ENV"
REFUSAL_HEAD_PIN_COUNT = "LIVE_LAUNCHER_HEAD_PIN_COUNT_NOT_ONE"
REFUSAL_BASELINE_PIN_COUNT = "LIVE_LAUNCHER_BASELINE_PIN_COUNT_NOT_ONE"
REFUSAL_SECRET_IN_TEXT = "LIVE_LAUNCHER_SECRET_IN_TEXT"
REFUSAL_CLOSED_ROUTE = "LIVE_LAUNCHER_CLOSED_ARMED_ROUTE_PRESENT"
REFUSAL_MODULE_MISSING = "LIVE_LAUNCHER_TRACKED_MODULE_MISSING"
REFUSAL_PRODUCTION_GRPC = "LIVE_LAUNCHER_REQUIRE_PRODUCTION_GRPC_MISSING"
REFUSAL_GAP_RECOVERY = "LIVE_LAUNCHER_GAP_RECOVERY_NOT_CANONICAL"
REFUSAL_DEX_BACKFILL = "LIVE_LAUNCHER_DEX_RESTART_BACKFILL_MISSING"
REFUSAL_DEX_BACKFILL_PRESENT = (
    "LIVE_LAUNCHER_HELIUS_PRIMARY_DEX_BACKFILL_PRESENT"
)
REFUSAL_SOURCE_MODE = "LIVE_LAUNCHER_MIGRATION_SOURCE_MODE_NOT_CANONICAL"
REFUSAL_CHAINSTACK_RUNTIME = "LIVE_LAUNCHER_HELIUS_ONLY_CHAINSTACK_RUNTIME_PRESENT"
REFUSAL_HELIUS_HTTP_RECOVERY = (
    "LIVE_LAUNCHER_HELIUS_HTTP_RECOVERY_MISSING"
)
REFUSAL_HELIUS_FILTER = "LIVE_LAUNCHER_HELIUS_TIGHT_FILTER_NOT_LOCKED"
REFUSAL_SOURCE_OWNER_COUNT = "LIVE_LAUNCHER_SOURCE_OWNER_COUNT_NOT_ONE"
REFUSAL_SHADOW_AUTHORITY = "LIVE_LAUNCHER_CHAINSTACK_SHADOW_HAS_AUTHORITY"
REFUSAL_HISTORICAL_RPC = "LIVE_LAUNCHER_HISTORICAL_RPC_FLAG_PRESENT"
REFUSAL_WALLET_OR_TRADING = "LIVE_LAUNCHER_WALLET_OR_TRADING_ENABLED"
REFUSAL_SEND_CAP_NOT_UNBOUNDED = "LIVE_LAUNCHER_SEND_CAP_NOT_UNBOUNDED"
REFUSAL_MARKET_BUDGET_NOT_UNBOUNDED = (
    "LIVE_LAUNCHER_MARKET_BUDGET_NOT_UNBOUNDED")
REFUSAL_ALERT_POLICY_MISSING = "LIVE_LAUNCHER_ALERT_POLICY_MISSING"
REFUSAL_ALERT_POLICY_COUNT = "LIVE_LAUNCHER_ALERT_POLICY_COUNT_NOT_ONE"
REFUSAL_ALERT_POLICY_UNKNOWN = "LIVE_LAUNCHER_ALERT_POLICY_UNKNOWN"
REFUSAL_ALERT_POLICY_NOT_CANONICAL = (
    "LIVE_LAUNCHER_ALERT_POLICY_NOT_CANONICAL")

LIVE_LAUNCHER_REFUSAL_REASONS = (
    REFUSAL_TELEGRAM_COUNT, REFUSAL_DISCORD_PRESENT, REFUSAL_SHADOW_MISSING,
    REFUSAL_RUN_FOREVER_MISSING, REFUSAL_TIMEOUT_SIMULATION,
    REFUSAL_FRESH_DIRS_MISSING, REFUSAL_STATE_DIR_UNSTABLE,
    REFUSAL_LEDGER_NOT_CANONICAL, REFUSAL_ENV_NOT_ACTIVE,
    REFUSAL_HEAD_PIN_COUNT, REFUSAL_BASELINE_PIN_COUNT,
    REFUSAL_SECRET_IN_TEXT, REFUSAL_CLOSED_ROUTE, REFUSAL_MODULE_MISSING,
    REFUSAL_PRODUCTION_GRPC, REFUSAL_GAP_RECOVERY,
    REFUSAL_DEX_BACKFILL, REFUSAL_DEX_BACKFILL_PRESENT, REFUSAL_SOURCE_MODE,
    REFUSAL_CHAINSTACK_RUNTIME,
    REFUSAL_HELIUS_HTTP_RECOVERY, REFUSAL_HELIUS_FILTER,
    REFUSAL_SOURCE_OWNER_COUNT,
    REFUSAL_SHADOW_AUTHORITY,
    REFUSAL_HISTORICAL_RPC, REFUSAL_WALLET_OR_TRADING,
    REFUSAL_SEND_CAP_NOT_UNBOUNDED, REFUSAL_MARKET_BUDGET_NOT_UNBOUNDED,
    REFUSAL_ALERT_POLICY_MISSING, REFUSAL_ALERT_POLICY_COUNT,
    REFUSAL_ALERT_POLICY_UNKNOWN, REFUSAL_ALERT_POLICY_NOT_CANONICAL,
)

_ARG_TOKEN = re.compile(r'"(--[a-z0-9\-]+)"')
_TELEGRAM_TOKEN_PATTERN = re.compile(r"\b\d{6,}:[A-Za-z0-9_\-]{30,}\b")


def strip_powershell_comments(text: str) -> str:
    """The EXECUTABLE half of a launcher, with whole-line comments removed.

    A launcher's header legitimately NAMES the deliberately closed route in order
    to assert that it is closed ("main.py / the production supervisor are NOT a
    route ... and appear nowhere below").  A boundary scan that matched raw
    substrings would read that negative claim as a violation, so closed-route and
    secret scanning runs against code lines only.
    """

    lines = []
    for line in str(text or "").splitlines():
        if line.lstrip().startswith("#"):
            continue
        lines.append(line)
    return "\n".join(lines)


def _quoted_flag_count(text: str, flag: str) -> int:
    """How many times ``"--flag"`` appears as a QUOTED argument token.

    Counting quoted tokens rather than raw substrings keeps a mention in a
    comment from being mistaken for an argument.
    """

    return sum(1 for token in _ARG_TOKEN.findall(text) if token == flag)


def validate_live_launcher_text(text: str, *, expected_head: str,
                                ledger_baseline: str) -> List[str]:
    """Every way this launcher text violates the Stage-10 contract."""

    refusals: List[str] = []
    body = str(text or "")
    #: Code only. Comments may name a closed route in order to assert it is shut.
    code = strip_powershell_comments(body)
    head = str(expected_head).strip().lower()
    baseline = str(ledger_baseline).strip()

    if _quoted_flag_count(body, "--enable-telegram") != 1:
        refusals.append(REFUSAL_TELEGRAM_COUNT)
    if "--enable-private-discord" in body:
        refusals.append(REFUSAL_DISCORD_PRESENT)
    if _quoted_flag_count(body, "--phx1-structural-policy") != 1 \
            or '"shadow"' not in body:
        refusals.append(REFUSAL_SHADOW_MISSING)
    # The named alert policy: stated exactly once, in code (not a comment), and
    # equal to the canonical production value.  Missing, duplicated, unknown
    # and non-canonical are distinguished so the refusal names the real fault.
    alert_flag_count = _quoted_flag_count(code, "--alert-policy")
    alert_values = re.findall(
        r'"--alert-policy"\s*,\s*"([^"]*)"', code)
    if alert_flag_count == 0:
        refusals.append(REFUSAL_ALERT_POLICY_MISSING)
    elif alert_flag_count != 1 or len(alert_values) != 1:
        refusals.append(REFUSAL_ALERT_POLICY_COUNT)
    for value in alert_values:
        try:
            normalized = normalize_alert_policy(str(value).strip())
        except ValueError:
            if REFUSAL_ALERT_POLICY_UNKNOWN not in refusals:
                refusals.append(REFUSAL_ALERT_POLICY_UNKNOWN)
            continue
        if normalized != CANONICAL_ALERT_POLICY \
                and REFUSAL_ALERT_POLICY_NOT_CANONICAL not in refusals:
            refusals.append(REFUSAL_ALERT_POLICY_NOT_CANONICAL)
    if _quoted_flag_count(body, "--run-forever") != 1:
        refusals.append(REFUSAL_RUN_FOREVER_MISSING)
    # A run-forever launcher must carry the explicit UNBOUNDED send budget:
    # any bounded per-run send cap would terminate the managed producer after
    # its Nth alert and force a state-wiping restart.
    if _quoted_flag_count(body, "--max-sends-per-run") != 1 \
            or '"--max-sends-per-run", "0"' not in body:
        refusals.append(REFUSAL_SEND_CAP_NOT_UNBOUNDED)
    # ...and the explicit UNBOUNDED market-request budget, for the same
    # reason.  Stated once, in code, and equal to the sentinel -- a launcher
    # that merely omits the flag inherits the bounded default of 5,000 and
    # goes market-blind, which is exactly what 2026-08-02 proved.  Checked
    # against ``code`` so a commented example can never satisfy it.
    if _quoted_flag_count(code, "--max-market-requests-total") != 1 \
            or '"--max-market-requests-total", "0"' not in code:
        refusals.append(REFUSAL_MARKET_BUDGET_NOT_UNBOUNDED)
    if 'market_budget_mode      = "UNBOUNDED"' not in body:
        refusals.append(REFUSAL_MARKET_BUDGET_NOT_UNBOUNDED)
    # An indefinite launcher must not ALSO state a clock, and must not relaunch.
    if "--max-runtime-seconds" in body or "--active-soak-seconds" in body \
            or "--max-wall-clock-seconds" in body:
        refusals.append(REFUSAL_TIMEOUT_SIMULATION)
    if re.search(r"(?i)&\s*\$PSCommandPath|Start-Process\s+.*launch_live_24x7",
                 body):
        refusals.append(REFUSAL_TIMEOUT_SIMULATION)
    if "$RunStamp" not in body or "New-Item -ItemType Directory -Force $out" not in body:
        refusals.append(REFUSAL_FRESH_DIRS_MISSING)
    if CANONICAL_CURSOR_STATE_DIR not in body:
        refusals.append(REFUSAL_STATE_DIR_UNSTABLE)
    if CANONICAL_LEDGER_PATH not in body:
        refusals.append(REFUSAL_LEDGER_NOT_CANONICAL)
    if ACTIVE_ENV_PATH not in body:
        refusals.append(REFUSAL_ENV_NOT_ACTIVE)
    if body.count(head) != 1:
        refusals.append(REFUSAL_HEAD_PIN_COUNT)
    if body.count(baseline) != 1:
        refusals.append(REFUSAL_BASELINE_PIN_COUNT)
    if _TELEGRAM_TOKEN_PATTERN.search(body) \
            or "PHX2_TELEGRAM_BOT_TOKEN" in code \
            or "PHX2_TELEGRAM_CHAT_ID" in code \
            or "discord.com/api/webhooks" in code:
        refusals.append(REFUSAL_SECRET_IN_TEXT)
    if "production_supervisor" in code or "--hours" in code \
            or "main.py" in code or "supervised_launcher" in code:
        refusals.append(REFUSAL_CLOSED_ROUTE)
    if TRACKED_PRODUCTION_MODULE not in body:
        refusals.append(REFUSAL_MODULE_MISSING)
    if _quoted_flag_count(body, "--require-production-grpc") != 1:
        refusals.append(REFUSAL_PRODUCTION_GRPC)
    if f'"{CANONICAL_GAP_RECOVERY_MODE}"' not in body:
        refusals.append(REFUSAL_GAP_RECOVERY)
    source_assignment = (
        f'$SOURCE_MODE = "{CANONICAL_MIGRATION_SOURCE_MODE}"'
    )
    source_env_assignment = (
        f'$env:PHX2_MIGRATION_SOURCE_MODE = '
        f'"{CANONICAL_MIGRATION_SOURCE_MODE}"'
    )
    if (
        _quoted_flag_count(body, "--migration-source-mode") != 1
        or source_assignment not in body
        or source_env_assignment not in body
    ):
        refusals.append(REFUSAL_SOURCE_MODE)
    forbidden_source_modes = (
        "HELIUS_PRIMARY_CHAINSTACK_SHADOW",
        "CHAINSTACK_PRIMARY",
        "HELIUS_SHADOW",
    )
    argument_tokens = _ARG_TOKEN.findall(body)
    if (
        any(mode in code for mode in forbidden_source_modes)
        or any(
            flag == "--helius-parity-late-match-seconds"
            or flag.startswith("--chainstack")
            for flag in argument_tokens
        )
        or "PHX2_CHAINSTACK_YELLOWSTONE_GRPC_ENDPOINT" in code
    ):
        refusals.append(REFUSAL_CHAINSTACK_RUNTIME)
    if _quoted_flag_count(body, "--enable-helius-http-recovery") != 1:
        refusals.append(REFUSAL_HELIUS_HTTP_RECOVERY)
    # Bounded six-hour DEX candidate recovery is part of the armed
    # Helius-primary production contract: exactly one flag occurrence.
    if _quoted_flag_count(
        body,
        "--enable-dexscreener-restart-backfill",
    ) != 1:
        refusals.append(REFUSAL_DEX_BACKFILL)
    from PHX2.free_tier_producer.helius_source import (
        approved_tight_subscription_request,
        tight_filter_is_locked,
    )
    if not tight_filter_is_locked(approved_tight_subscription_request(1)):
        refusals.append(REFUSAL_HELIUS_FILTER)
    if "source_owners           = 1" not in body:
        refusals.append(REFUSAL_SOURCE_OWNER_COUNT)
    authority_literals = (
        "candidate_pipeline_owners = 1",
        "telegram_owners         = 1",
        "delivery_transaction_owners = 1",
        "paid_ledger_writers     = 1",
        "shadow_source           = \"DISABLED\"",
        "chainstack_configured_for_runtime = $false",
        "chainstack_connected    = $false",
        "chainstack_comparator   = $false",
        "chainstack_candidate_authority = $false",
        "chainstack_send_authority = $false",
        "chainstack_ledger_authority = $false",
    )
    if not all(value in body for value in authority_literals):
        refusals.append(REFUSAL_SHADOW_AUTHORITY)
    if any(token.startswith("--rpc-recovery-") for token in _ARG_TOKEN.findall(body)):
        refusals.append(REFUSAL_HISTORICAL_RPC)
    if re.search(r"(?i)--enable-(wallet|trading|signing)", body):
        refusals.append(REFUSAL_WALLET_OR_TRADING)

    ordered: List[str] = []
    seen: set = set()
    for reason in refusals:
        if reason not in seen:
            seen.add(reason)
            ordered.append(reason)
    return ordered


def deployment_specification(*, expected_head: str,
                             ledger_baseline: str) -> Dict[str, Any]:
    """The deterministic deployment record for the external launcher."""

    body = render_live_launcher_bytes(
        expected_head=expected_head, ledger_baseline=ledger_baseline)
    return {
        "kind": "PHX2_LIVE_24X7_LAUNCHER_DEPLOYMENT_SPEC",
        "basename": LIVE_LAUNCHER_BASENAME,
        "template_module": "PHX2.watchdog.launcher_template",
        "encoding": "utf-8-no-bom",
        "newline": "lf",
        "bytes": len(body),
        "sha256": hashlib.sha256(body).hexdigest(),
        "pinned_repo_head": str(expected_head).strip().lower(),
        "pinned_ledger_baseline": str(ledger_baseline).strip(),
        "runtime_contract": "RUN_FOREVER",
        # Stated in the deployment identity, not merely in argv: a change of
        # market-budget posture is a change of deployment, and the watchdog
        # must be able to see which posture it authorized.
        "market_budget_mode": MARKET_BUDGET_MODE_UNBOUNDED,
        "market_budget_limit": MARKET_BUDGET_MODE_UNBOUNDED,
        "delivery_transport": "TELEGRAM",
        "migration_source_mode": CANONICAL_MIGRATION_SOURCE_MODE,
        "primary_migration_source": "HELIUS",
        "primary_recovery": "HELIUS_HTTP",
        "shadow_source": "DISABLED",
        "chainstack_configured_for_runtime": False,
        "chainstack_connected": False,
        "chainstack_comparator": False,
        "source_owners": 1,
        "helius_http_recovery_enabled": True,
        "candidate_pipeline_owners": 1,
        "telegram_owners": 1,
        "paid_ledger_writers": 1,
        "discord_enabled": False,
        "structural_policy": "SHADOW",
        "alert_policy": CANONICAL_ALERT_POLICY,
        "contract_refusals": validate_live_launcher_text(
            body.decode("utf-8"), expected_head=expected_head,
            ledger_baseline=ledger_baseline),
    }


__all__ = (
    "ACTIVE_ENV_PATH",
    "LIVE_RUN_ID",
    "LIVE_LAUNCHER_BASENAME",
    "CONFIRM_TOKEN_MODULE",
    "CONFIRM_TOKEN_SYMBOL",
    "LIVE_LAUNCHER_REFUSAL_REASONS",
    "REFUSAL_MARKET_BUDGET_NOT_UNBOUNDED",
    "REFUSAL_SEND_CAP_NOT_UNBOUNDED",
    "render_live_launcher",
    "render_live_launcher_bytes",
    "live_launcher_sha256",
    "validate_live_launcher_text",
    "deployment_specification",
)

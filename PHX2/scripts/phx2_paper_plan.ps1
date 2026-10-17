# This wrapper intentionally has no activation path and never sources .env.
# The only child process is the offline preflight Python module.
param(
    [Parameter(Mandatory = $true)][string]$Config,
    [Parameter(Mandatory = $true)][string]$SourceRoot,
    [Parameter(Mandatory = $true)][string]$OutRoot,
    [Parameter(Mandatory = $true)][string]$RunId,
    [string]$ReviewedHead,
    [string]$ReviewedSourceSha256,
    [int]$TailCapacity = 0,
    [int]$MaxRuntimeSeconds = 0,
    [int]$MaxMarketRequests = 0,
    [int]$HeliusMaxRawBytes = 0,
    [int]$MaxDiscoveryMessages = -1,
    [int]$MaxPaperMessages = -1,
    [string]$DestinationAlias
)
$ErrorActionPreference = 'Stop'
$paperRepo = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..\..')).Path
$paperPython = Join-Path $paperRepo '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $paperPython -PathType Leaf)) {
    throw 'Project Python is unavailable; no process was started.'
}
$paperArgs = @('-m', 'PHX2.scripts.phx2_paper_preflight', '--repo', $paperRepo,
    '--config', $Config, '--source-root', $SourceRoot, '--out-root', $OutRoot,
    '--run-id', $RunId, '--tail-capacity', $TailCapacity,
    '--max-runtime-seconds', $MaxRuntimeSeconds, '--max-market-requests', $MaxMarketRequests,
    '--helius-max-raw-bytes', $HeliusMaxRawBytes, '--max-discovery-messages', $MaxDiscoveryMessages,
    '--max-paper-messages', $MaxPaperMessages)
if ($ReviewedHead) { $paperArgs += @('--reviewed-head', $ReviewedHead) }
if ($ReviewedSourceSha256) { $paperArgs += @('--reviewed-source-sha256', $ReviewedSourceSha256) }
if ($DestinationAlias) { $paperArgs += @('--destination-alias', $DestinationAlias) }
Push-Location -LiteralPath $paperRepo
try {
    & $paperPython @paperArgs
    exit $LASTEXITCODE
} finally {
    Pop-Location
}

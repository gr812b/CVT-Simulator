param(
  [string]$Api = "http://localhost:8000/api/v1",
  [string]$OutputDir = "",
  [switch]$Strict,
  [switch]$FullMutating,
  [switch]$SkipRuns,
  [switch]$SkipCache,
  [switch]$RunDirectRegression,
  [string]$EvictionEndpointTemplate = "",
  [string]$ExtraArgs = ""
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Harness = Join-Path $ScriptDir "cvt_black_box_api_e2e.py"

$argsList = @($Harness, "--api", $Api)
if ($OutputDir -ne "") { $argsList += @("--output-dir", $OutputDir) }
if ($Strict) { $argsList += "--strict" }
if ($FullMutating) { $argsList += "--full-mutating" }
if ($SkipRuns) { $argsList += "--skip-runs" }
if ($SkipCache) { $argsList += "--skip-cache" }
if ($RunDirectRegression) { $argsList += "--run-direct-regression" }
if ($EvictionEndpointTemplate -ne "") { $argsList += @("--eviction-endpoint-template", $EvictionEndpointTemplate) }
if ($ExtraArgs -ne "") { $argsList += ($ExtraArgs -split ' ') }

python @argsList
exit $LASTEXITCODE

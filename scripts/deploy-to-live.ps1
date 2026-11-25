<#
.SYNOPSIS
    Copy the code and documentation from the Dev project to the Live project.

.DESCRIPTION
    Copies ONLY the code (src, including its SQL), the .bat shortcut files, 'doc\CLI Usage.md' and
    pyproject.toml (needed for 'pip install -e .'). It never touches the Live data folder, the Live database or the Live
    reference workbook, and it never copies Dev's data, .venv, .git, Power BI files, scripts or
    other docs.

    The src folder is mirrored, so a file deleted in Dev is also removed from Live.
    The Live data folder is outside src and is not affected.

.PARAMETER DryRun
    Show what would be copied or deleted without changing anything.

.PARAMETER SetupVenv
    Create the Live .venv if it is missing and run 'pip install -e .' (needed on first deploy,
    or when dependencies in pyproject.toml change).

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File ".\scripts\deploy-to-live.ps1" -DryRun
    powershell -ExecutionPolicy Bypass -File ".\scripts\deploy-to-live.ps1" -SetupVenv
#>
[CmdletBinding()]
param(
    [string]$DevPath  = 'C:\Dev\2026 Cost of Living',
    [string]$LivePath = 'C:\App\2026 Cost of Living',
    [switch]$DryRun,
    [switch]$SetupVenv
)

$ErrorActionPreference = 'Stop'

function Fail([string]$message) {
    Write-Host "ERROR: $message" -ForegroundColor Red
    exit 1
}

# ---- Checks ---------------------------------------------------------------------------------
if (-not (Test-Path -LiteralPath $DevPath -PathType Container)) { Fail "Dev folder not found: $DevPath" }
$devFull  = [IO.Path]::GetFullPath($DevPath).TrimEnd('\')
$liveFull = [IO.Path]::GetFullPath($LivePath).TrimEnd('\')
if ($devFull -ieq $liveFull) { Fail 'Dev and Live paths are the same folder.' }
if (-not (Test-Path -LiteralPath (Join-Path $devFull 'src\cost_of_living\admin_cli.py'))) {
    Fail "This doesn't look like the project: src\cost_of_living\admin_cli.py not found in $devFull"
}

if ($DryRun) { Write-Host "DRY RUN - nothing will be changed.`n" -ForegroundColor Yellow }
Write-Host "Dev : $devFull"
Write-Host "Live: $liveFull`n"

# Warn (don't stop) if Dev has uncommitted changes, so Live matches a known commit.
if (Get-Command git -ErrorAction SilentlyContinue) {
    $dirty = $null
    try { $dirty = & git -C $devFull status --porcelain 2>$null } catch { }
    if ($dirty) {
        Write-Host "WARNING: Dev has uncommitted changes. Live will get the working files, not the last commit." -ForegroundColor Yellow
        Write-Host "         Consider committing first.`n" -ForegroundColor Yellow
    }
}

# ---- Live folder layout ---------------------------------------------------------------------
$dataFolders = @('data\1. extract', 'data\2. transform', 'data\3. load', 'data\9. reference')
foreach ($folder in $dataFolders) {
    $path = Join-Path $liveFull $folder
    if (-not (Test-Path -LiteralPath $path)) {
        if ($DryRun) { Write-Host "Would create: $path" }
        else { New-Item -ItemType Directory -Path $path -Force | Out-Null; Write-Host "Created: $path" }
    }
}

# ---- Copy code folders (mirrored) -----------------------------------------------------------
function Copy-CodeFolder([string]$name) {
    $source = Join-Path $devFull $name
    $target = Join-Path $liveFull $name
    if (-not (Test-Path -LiteralPath $source -PathType Container)) {
        Write-Host "Skipped (not in Dev): $name"
        return
    }
    Write-Host "--- $name"
    $roboArgs = @(
        $source, $target, '/MIR',
        '/XD', '__pycache__', '*.egg-info', '.pytest_cache',
        '/XF', '*.pyc', '*.duckdb', '*.parquet', '*.xlsx', '*.csv',
        '/NJH', '/NJS', '/NP', '/NDL', '/R:2', '/W:2'
    )
    if ($DryRun) { $roboArgs += '/L' }
    & robocopy @roboArgs
    # Robocopy exit codes 0-7 mean success (some files copied or extra files removed); 8+ means failure.
    if ($LASTEXITCODE -ge 8) { Fail "robocopy failed for '$name' (exit code $LASTEXITCODE)." }
}

Copy-CodeFolder 'src'

# ---- Copy pyproject.toml (needed by 'pip install -e .') and the CLI usage guide -------------
Write-Host '--- project files'
$batFiles = @(Get-ChildItem -LiteralPath $devFull -Filter '*.bat' -File | ForEach-Object { $_.Name })
foreach ($file in (@('pyproject.toml', 'doc\CLI Usage.md') + $batFiles)) {
    $source = Join-Path $devFull $file
    if (-not (Test-Path -LiteralPath $source)) { Write-Host "Skipped (not in Dev): $file"; continue }
    $target = Join-Path $liveFull $file
    if ($DryRun) { Write-Host "Would copy: $file"; continue }
    New-Item -ItemType Directory -Path (Split-Path -Parent $target) -Force | Out-Null
    Copy-Item -LiteralPath $source -Destination $target -Force
    Write-Host "Copied: $file"
}

# ---- Python environment ---------------------------------------------------------------------
$venvPython = Join-Path $liveFull '.venv\Scripts\python.exe'
if ($SetupVenv -and -not $DryRun) {
    Write-Host '--- Python environment'
    Push-Location $liveFull
    try {
        if (-not (Test-Path -LiteralPath $venvPython)) {
            if (-not (Get-Command python -ErrorAction SilentlyContinue)) { Fail 'python was not found on PATH; install Python 3.11 or newer.' }
            & python -m venv .venv
            if ($LASTEXITCODE -ne 0) { Fail 'Creating the virtual environment failed.' }
            Write-Host 'Created .venv'
        }
        & $venvPython -m pip install -e .
        if ($LASTEXITCODE -ne 0) { Fail 'pip install -e . failed.' }
    }
    finally { Pop-Location }
}
elseif (-not (Test-Path -LiteralPath $venvPython)) {
    Write-Host "`nNOTE: Live has no .venv yet. Re-run with -SetupVenv to create it." -ForegroundColor Yellow
}

# ---- Reminders ------------------------------------------------------------------------------
$workbook = Join-Path $liveFull 'data\9. reference\2026 Cost of Living - Reference.xlsx'
if (-not (Test-Path -LiteralPath $workbook)) {
    Write-Host "`nNOTE: the Live reference workbook is missing. Copy your real workbook to:" -ForegroundColor Yellow
    Write-Host "      $workbook" -ForegroundColor Yellow
}

Write-Host "`nDone." -ForegroundColor Green
if ($DryRun) { Write-Host 'That was a dry run. Run again without -DryRun to copy.' }
else {
    Write-Host @"

Next, in the Live folder ($liveFull):
  1. Put your bank CSV files in  data\1. extract
  2. Put your reference workbook in  data\9. reference
  3. Run:
       .\.venv\Scripts\python.exe -m cost_of_living.admin_cli import
       .\.venv\Scripts\python.exe -m cost_of_living.admin_cli load-mappings
       .\.venv\Scripts\python.exe -m cost_of_living.admin_cli export-actuals
       .\.venv\Scripts\python.exe -m cost_of_living.admin_cli status
"@
}

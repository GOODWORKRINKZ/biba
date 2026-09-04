# BIBA Eye - one-time setup for Windows.
#   - creates the BIBA virtual environment (biba_venv) and installs packages
#   - installs Python 3 and ffmpeg automatically when missing (winget)
#   - writes initial config.json (camera IP can also be entered on the page)
#   - creates run.cmd + desktop/start-menu shortcuts with the BIBA Eye icon
# Usage:  powershell -ExecutionPolicy Bypass -File setup.ps1
param([switch]$NoShortcut)

$ErrorActionPreference = 'Stop'
$dir = Split-Path -Parent $MyInvocation.MyCommand.Path

function Write-Info { param([string]$m) Write-Host "[INFO] $m" -ForegroundColor DarkCyan }
function Write-Ok   { param([string]$m) Write-Host "[OK]   $m" -ForegroundColor Green }
function Write-Warn { param([string]$m) Write-Host "[WARN] $m" -ForegroundColor Yellow }
function Write-Err  { param([string]$m) Write-Host "[ERR]  $m" -ForegroundColor Red }
function Write-Step {
    param([string]$m)
    $bar = '=' * 58
    Write-Host ''
    Write-Host $bar -ForegroundColor Blue
    Write-Host "  $m" -ForegroundColor Blue
    Write-Host $bar -ForegroundColor Blue
}
function Show-Logo {
    Write-Host @'
    ╔═══════════════════════════════════════════════════════╗
    ║                                                       ║
    ║  ██████╗  ██╗ ██████╗   █████╗                        ║
    ║  ██╔══██╗ ██║ ██╔══██╗ ██╔══██╗                       ║
    ║  ██████╔╝ ██║ ██████╔╝ ███████║                       ║
    ║  ██╔══██╗ ██║ ██╔══██╗ ██╔══██║                       ║
    ║  ██████╔╝ ██║ ██████╔╝ ██║  ██║                       ║
    ║  ╚═════╝  ╚═╝ ╚═════╝  ╚═╝  ╚═╝                       ║
    ║                                                       ║
    ╚═══════════════════════════════════════════════════════╝
'@ -ForegroundColor Magenta
    Write-Host '              BIBA Eye Setup v1.0' -ForegroundColor Cyan
    Write-Host ''
}

function Find-Python {
    $cands = @(
        (Get-Command py -ErrorAction SilentlyContinue).Source,
        (Get-Command python -ErrorAction SilentlyContinue).Source,
        "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python310\python.exe",
        "$env:ProgramFiles\Python312\python.exe",
        "$env:ProgramFiles\Python311\python.exe",
        "C:\Python312\python.exe"
    ) | Where-Object { $_ } | Select-Object -Unique
    foreach ($c in $cands) {
        if (-not (Test-Path $c)) { continue }
        try {
            $v = & $c --version 2>$null
            if ($LASTEXITCODE -eq 0 -and $v -match 'Python 3\.(\d+)' -and [int]$Matches[1] -ge 8) {
                return $c
            }
        } catch {}
    }
    return $null
}

Show-Logo

# --- Python (system interpreter, used to create the venv) ---
Write-Step '1/5  Python'
$py = Find-Python
if (-not $py) {
    Write-Info 'Python 3.8+ not found. Installing Python 3.12 via winget...'
    winget install --id Python.Python.3.12 -e --accept-source-agreements --accept-package-agreements --silent
    $py = Find-Python
}
if (-not $py) {
    Write-Err 'Python not found. Install it manually and rerun this script.'
    exit 1
}
Write-Ok "Python: $py"

# --- BIBA virtual environment ---
Write-Step '2/5  BIBA virtual environment'
$venvDir = Join-Path $dir 'biba_venv'
$venvPy = Join-Path $venvDir 'Scripts\python.exe'
if (-not (Test-Path $venvPy)) {
    Write-Info 'Creating BIBA virtual environment (biba_venv)...'
    & $py -m venv $venvDir
    if (-not (Test-Path $venvPy)) {
        Write-Err 'Failed to create biba_venv'
        exit 1
    }
} else {
    Write-Ok 'biba_venv already exists'
}
& $venvPy -m pip install --upgrade pip --disable-pip-version-check --quiet
$req = Join-Path $dir 'requirements.txt'
if (Test-Path $req) {
    $pkgs = Get-Content $req | Where-Object { $_ -match '^\s*[A-Za-z0-9_]' }
    if ($pkgs) {
        Write-Info 'Installing packages from requirements.txt...'
        & $venvPy -m pip install -r $req --quiet
    } else {
        Write-Ok 'requirements.txt: no external packages (server uses stdlib only)'
    }
}
Write-Ok "Virtual env: $venvDir"

# --- ffmpeg ---
Write-Step '3/5  ffmpeg'
$ffmpeg = (Get-Command ffmpeg -ErrorAction SilentlyContinue).Source
if (-not $ffmpeg) {
    Write-Info 'ffmpeg not found. Installing via winget...'
    winget install --id Gyan.FFmpeg -e --accept-source-agreements --accept-package-agreements --silent
    $ffmpeg = (Get-Command ffmpeg -ErrorAction SilentlyContinue).Source
}
if (-not $ffmpeg) {
    Write-Warn 'ffmpeg not found - video will not work.'
} else {
    Write-Ok "ffmpeg: $ffmpeg"
}

# --- initial config (camera IP is also configurable from the web page) ---
Write-Step '4/5  Camera config'
$cfgPath = Join-Path $dir 'config.json'
if (-not (Test-Path $cfgPath)) {
    Write-Info 'Camera settings (can be changed later on the web page):'
    $ip = Read-Host 'Camera IP (press Enter to skip)'
    $pass = '888888'
    if ($ip) {
        $in = Read-Host 'Camera password [888888]'
        if ($in) { $pass = $in }
    }
    @{ camera_ip = $ip; camera_pass = $pass } | ConvertTo-Json |
        Set-Content -Path $cfgPath -Encoding UTF8
    Write-Ok "Config written: $cfgPath"
} else {
    Write-Ok 'config.json already exists'
}

# --- run.cmd (uses the venv python) ---
Write-Step '5/5  Launchers and shortcuts'
$run = Join-Path $dir 'run.cmd'
@"
@echo off
cd /d "%~dp0"
"biba_venv\Scripts\python.exe" server.py
pause
"@ | Set-Content -Path $run -Encoding ASCII
Write-Ok "Created: $run"

# --- shortcuts with the BIBA Eye icon ---
if (-not $NoShortcut) {
    $ico = Join-Path $dir 'biba_eye.ico'
    $sh = New-Object -ComObject WScript.Shell
    $desktop = [Environment]::GetFolderPath('Desktop')
    $startMenu = [Environment]::GetFolderPath('Programs')

    $lnkDesktop = $sh.CreateShortcut((Join-Path $desktop 'BIBA Eye.lnk'))
    $lnkDesktop.TargetPath = "$env:ComSpec"
    $lnkDesktop.Arguments = '/c "' + $run + '"'
    $lnkDesktop.WorkingDirectory = $dir
    $lnkDesktop.Description = 'BIBA Eye - FPV camera control'
    if (Test-Path $ico) { $lnkDesktop.IconLocation = "$ico,0" }
    $lnkDesktop.Save()
    Write-Ok 'Desktop shortcut created: BIBA Eye'

    $smDir = Join-Path $startMenu 'BIBA Eye'
    New-Item -ItemType Directory -Force -Path $smDir | Out-Null
    $lnkMenu = $sh.CreateShortcut((Join-Path $smDir 'BIBA Eye.lnk'))
    $lnkMenu.TargetPath = "$env:ComSpec"
    $lnkMenu.Arguments = '/c "' + $run + '"'
    $lnkMenu.WorkingDirectory = $dir
    $lnkMenu.Description = 'BIBA Eye - FPV camera control'
    if (Test-Path $ico) { $lnkMenu.IconLocation = "$ico,0" }
    $lnkMenu.Save()
    Write-Ok 'Start menu shortcut created: BIBA Eye'
} else {
    Write-Warn 'Shortcuts skipped (-NoShortcut)'
}

Write-Host ''
Write-Host '  Done. Start BIBA Eye via run.cmd or the BIBA Eye shortcut.' -ForegroundColor Green
Write-Host '  The page http://127.0.0.1:8081/ opens automatically.' -ForegroundColor Green

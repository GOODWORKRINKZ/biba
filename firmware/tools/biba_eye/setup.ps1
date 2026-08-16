# BIBA Eye - one-time setup for Windows.
#   - creates the BIBA virtual environment (biba_venv) and installs packages
#   - installs Python 3 and ffmpeg automatically when missing (winget)
#   - writes initial config.json (camera IP can also be entered on the page)
#   - creates run.cmd + desktop/start-menu shortcuts with the BIBA Eye icon
# Usage:  powershell -ExecutionPolicy Bypass -File setup.ps1
param([switch]$NoShortcut)

$ErrorActionPreference = 'Stop'
$dir = Split-Path -Parent $MyInvocation.MyCommand.Path

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

Write-Host '=== BIBA Eye setup ==='

# --- Python (system interpreter, used to create the venv) ---
$py = Find-Python
if (-not $py) {
    Write-Host 'Python 3.8+ not found. Installing Python 3.12 via winget...'
    winget install --id Python.Python.3.12 -e --accept-source-agreements --accept-package-agreements --silent
    $py = Find-Python
}
if (-not $py) {
    Write-Host 'ERROR: Python not found. Install it manually and rerun this script.' -ForegroundColor Red
    exit 1
}
Write-Host "Python: $py"

# --- BIBA virtual environment ---
$venvDir = Join-Path $dir 'biba_venv'
$venvPy = Join-Path $venvDir 'Scripts\python.exe'
if (-not (Test-Path $venvPy)) {
    Write-Host 'Creating BIBA virtual environment (biba_venv)...'
    & $py -m venv $venvDir
    if (-not (Test-Path $venvPy)) {
        Write-Host 'ERROR: failed to create biba_venv' -ForegroundColor Red
        exit 1
    }
}
& $venvPy -m pip install --upgrade pip --disable-pip-version-check --quiet
$req = Join-Path $dir 'requirements.txt'
if (Test-Path $req) {
    $pkgs = Get-Content $req | Where-Object { $_ -match '^\s*[A-Za-z0-9_]' }
    if ($pkgs) {
        Write-Host 'Installing packages from requirements.txt...'
        & $venvPy -m pip install -r $req --quiet
    } else {
        Write-Host 'requirements.txt: no external packages (server uses stdlib only).'
    }
}
Write-Host "Virtual env: $venvDir"

# --- ffmpeg ---
$ffmpeg = (Get-Command ffmpeg -ErrorAction SilentlyContinue).Source
if (-not $ffmpeg) {
    Write-Host 'ffmpeg not found. Installing via winget...'
    winget install --id Gyan.FFmpeg -e --accept-source-agreements --accept-package-agreements --silent
    $ffmpeg = (Get-Command ffmpeg -ErrorAction SilentlyContinue).Source
}
if (-not $ffmpeg) {
    Write-Host 'WARNING: ffmpeg not found - video will not work.' -ForegroundColor Yellow
} else {
    Write-Host "ffmpeg: $ffmpeg"
}

# --- initial config (camera IP is also configurable from the web page) ---
$cfgPath = Join-Path $dir 'config.json'
if (-not (Test-Path $cfgPath)) {
    Write-Host ''
    Write-Host 'Camera settings (can be changed later on the web page):'
    $ip = Read-Host 'Camera IP (press Enter to skip)'
    $pass = '888888'
    if ($ip) {
        $in = Read-Host 'Camera password [888888]'
        if ($in) { $pass = $in }
    }
    @{ camera_ip = $ip; camera_pass = $pass } | ConvertTo-Json |
        Set-Content -Path $cfgPath -Encoding UTF8
    Write-Host "Config written: $cfgPath"
}

# --- run.cmd (uses the venv python) ---
$run = Join-Path $dir 'run.cmd'
@"
@echo off
cd /d "%~dp0"
"biba_venv\Scripts\python.exe" server.py
pause
"@ | Set-Content -Path $run -Encoding ASCII
Write-Host "Created: $run"

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
    Write-Host 'Desktop shortcut created: BIBA Eye'

    $smDir = Join-Path $startMenu 'BIBA Eye'
    New-Item -ItemType Directory -Force -Path $smDir | Out-Null
    $lnkMenu = $sh.CreateShortcut((Join-Path $smDir 'BIBA Eye.lnk'))
    $lnkMenu.TargetPath = "$env:ComSpec"
    $lnkMenu.Arguments = '/c "' + $run + '"'
    $lnkMenu.WorkingDirectory = $dir
    $lnkMenu.Description = 'BIBA Eye - FPV camera control'
    if (Test-Path $ico) { $lnkMenu.IconLocation = "$ico,0" }
    $lnkMenu.Save()
    Write-Host 'Start menu shortcut created: BIBA Eye'
}

Write-Host ''
Write-Host 'Done. Start BIBA Eye via run.cmd or the BIBA Eye shortcut.' -ForegroundColor Green
Write-Host 'The page http://127.0.0.1:8081/ opens automatically.'

# BIBA Eye - one-line installer.
# Downloads the tool from GitHub and runs the full setup (Python/ffmpeg/venv/shortcuts).
# Usage (copy-paste into PowerShell):
#   irm https://raw.githubusercontent.com/GOODWORKRINKZ/biba/main/firmware/tools/biba_eye/install.ps1 | iex
param(
    [string]$Repo = 'GOODWORKRINKZ/biba',
    [string]$Branch = 'main',
    [string]$InstallDir = ''
)

[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

if (-not $InstallDir) {
    $InstallDir = Join-Path $env:LOCALAPPDATA 'BIBA Eye'
}

$base = "https://raw.githubusercontent.com/$Repo/$Branch/firmware/tools/biba_eye"
$files = @('server.py', 'index.html', 'setup.ps1', 'biba_eye.ico', 'requirements.txt', 'README.md')

Write-Host 'Downloading BIBA Eye...' -ForegroundColor Cyan
New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
foreach ($f in $files) {
    Write-Host "  $f"
    Invoke-WebRequest -Uri "$base/$f" -OutFile (Join-Path $InstallDir $f) -UseBasicParsing
}
Write-Host "Installed to: $InstallDir" -ForegroundColor Green
Write-Host ''

& powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $InstallDir 'setup.ps1')

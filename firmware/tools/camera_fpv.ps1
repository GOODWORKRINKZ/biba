# BIBA FPV: low-latency RTSP viewer for V380 Q8 (IPC-V380-Q8)
# Usage:
#   .\camera_fpv.ps1 -Password '888888'                 # watch main stream
#   .\camera_fpv.ps1 -Password '888888' -Reconnect -An  # FPV mode: auto-reconnect, no audio
#   .\camera_fpv.ps1 -Password '888888' -Path onvif2    # sub-stream (lower latency)
#   .\camera_fpv.ps1 -Password '888888' -Transport udp  # lower latency, possible artifacts
# MINIMUM LATENCY (recommended FPV preset):
#   .\camera_fpv.ps1 -Password '888888' -Path onvif2 -Transport udp -An -Reconnect

param(
    [string]$IP        = '192.168.1.107',
    [string]$User      = 'admin',
    [string]$Password,
    [string]$Path      = 'onvif1',   # onvif1 = main stream, onvif2 = sub-stream
    [string]$Transport = 'tcp',      # tcp = reliable, udp = faster
    [int]$Port         = 554,
    [switch]$Reconnect,              # auto-reconnect when stream drops
    [switch]$An                      # disable audio
)

$ErrorActionPreference = 'Stop'

if (-not $Password) {
    Write-Host @"
Device password is missing.
Usage:  .\camera_fpv.ps1 -Password 'PASSWORD'
The device password is set in the V380 Pro app when adding the camera (often 888888).
See docs/fpv_camera.md
"@
    exit 1
}

$ffplay = (Get-Command ffplay -ErrorAction SilentlyContinue).Source
if (-not $ffplay) {
    Write-Host 'ffplay not found. Install ffmpeg: winget install Gyan.FFmpeg' -ForegroundColor Red
    exit 1
}

[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$esc = [uri]::EscapeDataString($Password)
$url = "rtsp://{0}:{1}@{2}:{3}/{4}" -f $User, $esc, $IP, $Port, $Path

Write-Host "Opening stream: $url (transport=$Transport)" -ForegroundColor Green

$ffplayArgs = @(
    '-hide_banner', '-loglevel', 'warning',
    '-rtsp_transport', $Transport,
    '-max_delay', '0',
    '-avioflags', 'direct',
    '-fflags', 'nobuffer',
    '-flags', 'low_delay',
    '-analyzeduration', '100000',
    '-probesize', '100000',
    '-infbuf', '-framedrop', '-sync', 'ext',
    '-window_title', "BIBA FPV: $IP"
)
if ($An) { $ffplayArgs += @('-an') }

do {
    & $ffplay @ffplayArgs $url
    $code = $LASTEXITCODE
    if ($Reconnect) {
        Write-Host "ffplay exited (code $code), reconnecting in 2 s... (Ctrl+C to quit)" -ForegroundColor Yellow
        Start-Sleep -Seconds 2
    }
} while ($Reconnect)

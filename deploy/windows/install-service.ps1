<#
    Installs teip as an always-on Windows service with NSSM (https://nssm.cc). Run once, elevated,
    from the cloned repo after `uv sync`:
        powershell -ExecutionPolicy Bypass -File .\deploy\windows\install-service.ps1
    Idempotent. Serves http://127.0.0.1:<port>/ (config.toml); put a reverse proxy in front to share it
    on the network, or set host = "0.0.0.0" in config.toml.
#>
param(
    [string]$Nssm = 'nssm.exe',   # path to nssm.exe if it is not on PATH
    [string]$Service = 'teip',
    [int]$Port = 8014             # only used for the check at the end; the server reads config.toml
)
$ErrorActionPreference = 'Stop'
$me = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $me.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Error "This script must be run as Administrator."; exit 1
}

$Root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$Py   = Join-Path $Root '.venv\Scripts\python.exe'
$Svc  = $Service
$Log  = Join-Path $Root 'logs'
New-Item -ItemType Directory -Force -Path $Log | Out-Null

if (Get-Service $Svc -ErrorAction SilentlyContinue) {
    Write-Host "Removing existing '$Svc' service..."
    Stop-Service $Svc -Force -ErrorAction SilentlyContinue
    & $Nssm remove $Svc confirm 2>$null
    Start-Sleep -Seconds 2
}

# free the port if a dev server (uv run python serve.py) is still up
Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
    ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }

Write-Host "Installing '$Svc' service..."
& $Nssm install $Svc $Py (Join-Path $Root 'serve.py')
& $Nssm set $Svc AppDirectory $Root
& $Nssm set $Svc DisplayName 'teip (label printer)'
& $Nssm set $Svc Description 'teip: label design and print server for Brother TZe printers.'
& $Nssm set $Svc Start SERVICE_AUTO_START
& $Nssm set $Svc AppEnvironmentExtra 'PYTHONUTF8=1'
& $Nssm set $Svc AppStdout (Join-Path $Log 'service.log')
& $Nssm set $Svc AppStderr (Join-Path $Log 'service.log')
& $Nssm set $Svc AppRotateFiles 1
& $Nssm set $Svc AppRotateBytes 1048576
& $Nssm set $Svc AppExit Default Restart
& $Nssm set $Svc AppRestartDelay 3000

Start-Service $Svc
Start-Sleep -Seconds 4
try {
    $r = Invoke-WebRequest -UseBasicParsing "http://127.0.0.1:$Port/api/status" -TimeoutSec 8
    Write-Host ("SUCCESS: service running (HTTP {0}): {1}" -f $r.StatusCode, $r.Content) -ForegroundColor Green
} catch {
    Write-Warning ("Service installed but the local check failed: " + $_.Exception.Message)
    Write-Warning ("Check the log: " + (Join-Path $Log 'service.log'))
}

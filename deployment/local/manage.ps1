param(
    [ValidateSet('setup','start','stop','logs','status')][string]$Action = 'setup',
    [ValidateSet('cpu','gpu')][string]$Device = 'cpu'
)
$ErrorActionPreference = 'Stop'
$bundleDir = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
Set-Location $bundleDir
function Invoke-Docker {
    & docker @args
    if ($LASTEXITCODE -ne 0) { throw "Docker failed (exit $LASTEXITCODE)." }
}
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { throw 'Install and start Docker Desktop with WSL2 Linux containers first.' }
Invoke-Docker compose version
Invoke-Docker info
if ($Action -eq 'setup') {
    Invoke-Docker run --rm --mount "type=bind,source=$bundleDir,target=/bundle" -w /bundle python:3.10-slim-bookworm python deployment/local/configure.py --mode $Device
}
$envFile = Join-Path $bundleDir '.deploy.env'
if (-not (Test-Path $envFile)) { throw 'Run setup first.' }
$composeArgs = @('compose', '--env-file', $envFile, '-f', (Join-Path $bundleDir 'deployment/local/compose.yml'))
if (Select-String -Path $envFile -Pattern '^MEDIAUTO_DEVICE=gpu$' -Quiet) {
    $composeArgs += @('-f', (Join-Path $bundleDir 'deployment/local/compose.gpu.yml'))
}
switch ($Action) {
    'setup' {
        if ($Device -eq 'gpu') {
            Invoke-Docker @composeArgs up -d --build --wait --wait-timeout 900
        } else {
            Invoke-Docker @composeArgs pull
            Invoke-Docker @composeArgs up -d --no-build --wait --wait-timeout 900
        }
        $portLine = Select-String -Path $envFile -Pattern '^MEDIAUTO_PORT=' | Select-Object -First 1
        $appPort = if ($portLine) { ($portLine.Line -split '=', 2)[1].Trim() } else { '8092' }
        Write-Host "Ready: http://localhost:$appPort - initial login is in ADMIN_LOGIN.txt"
    }
    'start' { Invoke-Docker @composeArgs up -d --wait --wait-timeout 900 }
    'stop' { Invoke-Docker @composeArgs stop }
    'logs' { Invoke-Docker @composeArgs logs --tail 100 -f app }
    'status' { Invoke-Docker @composeArgs ps }
}

$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
Write-Host 'MeDIAuto GPU installation'
Write-Host '1. Docker GPU environment + host PostgreSQL (recommended)'
Write-Host '2. Native GPU environment from GitHub + host PostgreSQL'
$choice = Read-Host 'Choose installation method [1]'
if ([string]::IsNullOrWhiteSpace($choice)) { $choice = '1' }
switch ($choice) {
    '1' { $folder = 'docker' }
    '2' { $folder = 'native' }
    default { Write-Host 'Enter 1 or 2.'; exit 1 }
}
& powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "$folder/bootstrap.ps1")
exit $LASTEXITCODE

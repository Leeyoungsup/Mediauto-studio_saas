param([string]$Launcher='launch.py')
$ErrorActionPreference='Stop'
$python=(Get-Content -LiteralPath (Join-Path $PSScriptRoot '.python-path') -Raw).Trim()
& $python (Join-Path $PSScriptRoot $Launcher)
exit $LASTEXITCODE

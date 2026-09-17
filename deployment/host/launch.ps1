param([ValidateSet('start','stop','status')][string]$Action='start')
$ErrorActionPreference='Stop'
$python = (Get-Content -LiteralPath (Join-Path $PSScriptRoot '.python-path') -Raw).Trim()
& $python (Join-Path $PSScriptRoot 'install.py') --action $Action
exit $LASTEXITCODE

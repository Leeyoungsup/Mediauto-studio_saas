# Run with pwsh -NoProfile -File deployment/test_windows_python_detection.ps1.
# Isolated discovery tests; does not install Python or modify the real registry.
$ErrorActionPreference = 'Stop'
$work = Join-Path ([IO.Path]::GetTempPath()) ('mediauto-python-test-' + [guid]::NewGuid())
$oldProgramFiles = $env:ProgramFiles
$oldLocalAppData = $env:LOCALAPPDATA
$script:registeredPath = $null
function Test-Path {
    param([string]$Path, [string]$LiteralPath, [string]$PathType)
    $target = if ($LiteralPath) { $LiteralPath } else { $Path }
    if ($target -like 'HKLM:*') { return $false }
    if ($target -like 'HKCU:*') { return [bool]$script:registeredPath }
    return Microsoft.PowerShell.Management\Test-Path -LiteralPath $target
}
function Get-Item {
    param([string]$Path)
    if ($Path -like 'HKCU:*') {
        $key = [pscustomobject]@{Directory = $script:registeredPath}
        $key | Add-Member ScriptMethod GetValue { param($name); if ($name -eq '') { return $this.Directory }; return $null }
        return $key
    }
    return Microsoft.PowerShell.Management\Get-Item $Path
}
try {
    New-Item -ItemType Directory $work | Out-Null
    $env:ProgramFiles = Join-Path $work 'machine'
    $env:LOCALAPPDATA = Join-Path $work 'user'
    foreach ($mode in @('host', 'native')) {
        $source = Join-Path $PSScriptRoot "$mode/bootstrap.ps1"
        $tokens = $null; $errors = $null
        $ast = [Management.Automation.Language.Parser]::ParseFile($source, [ref]$tokens, [ref]$errors)
        if ($errors.Count) { throw ($errors | Out-String) }
        $function = $ast.Find({param($n) $n -is [Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -eq 'Find-CompatiblePython'}, $true)
        Invoke-Expression $function.Extent.Text
        if ($null -ne (Find-CompatiblePython)) { throw 'Missing Python should request installation' }
        $userPython = Join-Path $env:LOCALAPPDATA 'Programs/Python/Python312/python.exe'
        New-Item -ItemType Directory -Force (Split-Path $userPython) | Out-Null
        # Linux executable fixture for the native runtime probe.
        [IO.File]::WriteAllText($userPython, "#!/bin/sh`necho MEDIAUTO_PYTHON_OK`nexit 0`n")
        & chmod +x $userPython
        if ((Find-CompatiblePython) -ne $userPython) { throw 'Existing per-user Python was not reused' }
        $custom = Join-Path $work 'custom'
        New-Item -ItemType Directory -Force $custom | Out-Null
        Move-Item $userPython (Join-Path $custom 'python.exe')
        $script:registeredPath = $custom
        if ((Find-CompatiblePython) -ne (Join-Path $custom 'python.exe')) { throw 'Custom HKCU Python was not reused' }
        [IO.File]::WriteAllText((Join-Path $custom 'python.exe'), "#!/bin/sh`nexit 1`n")
        $rejected = $false
        try { Find-CompatiblePython | Out-Null } catch { $rejected = $_.Exception.Message -like '*runtime check failed*' }
        if (-not $rejected) { throw 'Broken Python must stop, not trigger scope conversion' }
        Remove-Item (Join-Path $custom 'python.exe')
        $rejected = $false
        try { Find-CompatiblePython | Out-Null } catch { $rejected = $_.Exception.Message -like '*runtime check failed*' }
        if (-not $rejected) { throw 'Stale registration must stop instead of reinstalling' }
        $script:registeredPath = $null
        Write-Host "$mode : parser and 5 Python discovery scenarios passed"
    }
} finally {
    $env:ProgramFiles = $oldProgramFiles
    $env:LOCALAPPDATA = $oldLocalAppData
    Remove-Item -Recurse -Force $work
}

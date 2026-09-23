param([switch]$PrepareOnly, [switch]$Gui)
$ErrorActionPreference = 'Stop'
$scriptPath = $PSCommandPath
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$admin = ([Security.Principal.WindowsPrincipal]$identity).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $admin) {
    $arguments = @('-NoProfile','-ExecutionPolicy','Bypass','-File',('"' + $scriptPath + '"'))
    if ($PrepareOnly) { $arguments += '-PrepareOnly' }
    if ($Gui) { $arguments += '-Gui' }
    $p = Start-Process powershell -Verb RunAs -Wait -PassThru -ArgumentList $arguments
    exit $p.ExitCode
}
Set-Location $PSScriptRoot
function Invoke-Checked {
    param([string]$Program, [string[]]$Arguments)
    & $Program @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$Program failed (exit $LASTEXITCODE)." }
}
function Find-CompatiblePython {
    # Reuse a working 64-bit Python 3.12 without changing its installation scope.
    $candidates = @()
    $registered = $false
    foreach ($reg in @('HKLM:\SOFTWARE\Python\PythonCore\3.12\InstallPath', 'HKCU:\SOFTWARE\Python\PythonCore\3.12\InstallPath')) {
        if (Test-Path $reg) {
            $registered = $true
            $key = Get-Item $reg
            $executable = $key.GetValue('ExecutablePath')
            if ($executable) { $candidates += $executable }
            $directory = $key.GetValue('')
            if ($directory) { $candidates += Join-Path $directory 'python.exe' }
        }
    }
    $candidates += Join-Path $env:ProgramFiles 'Python312\python.exe'
    $candidates += Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312\python.exe'
    $found = $false
    foreach ($candidate in ($candidates | Select-Object -Unique)) {
        if (-not (Test-Path -LiteralPath $candidate -PathType Leaf)) { continue }
        $found = $true
        try {
            $probe = & $candidate -I -c 'import sys, struct, ssl, sqlite3, venv, ensurepip, ctypes; assert sys.version_info[:2] == (3, 12) and struct.calcsize(''P'') == 8; print(''MEDIAUTO_PYTHON_OK'')' 2>$null
            if ($LASTEXITCODE -eq 0 -and $probe -contains 'MEDIAUTO_PYTHON_OK') {
                return $candidate
            }
        } catch {
            # Try the other registered/default location before reporting a broken install.
        }
    }
    if ($registered -or $found) {
        throw 'Python 3.12 was found but its 64-bit runtime check failed. Repair that Python installation, then run install.bat again. Automatic scope conversion has been stopped.'
    }
    return $null
}
try {
    if (-not [Environment]::Is64BitOperatingSystem -or $env:PROCESSOR_ARCHITECTURE -eq 'ARM64') { throw 'An x86-64 Windows PC is required.' }
    if ([Environment]::OSVersion.Version.Build -lt 19045) { throw 'Update Windows to a supported Docker Desktop version first (Windows 10 22H2 / Windows 11 or newer supported build).' }
    $runtime = Join-Path $PSScriptRoot '.runtime'
    New-Item -ItemType Directory -Force $runtime | Out-Null
    # Generated DB/admin credentials are accessible only to this user, Administrators and SYSTEM.
    $sid = $identity.User.Value
    Invoke-Checked icacls @($runtime,'/inheritance:r','/grant:r',('*' + $sid + ':(OI)(CI)F'),'*S-1-5-18:(OI)(CI)F','*S-1-5-32-544:(OI)(CI)F')
    & powershell -NoProfile -NonInteractive -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'setup-nvidia-driver.ps1')
    if ($LASTEXITCODE -eq 3010) { throw 'REBOOT REQUIRED: GPU driver installed. Restart Windows and run this installer again.' }
    if ($LASTEXITCODE -ne 0) { throw 'NVIDIA driver setup did not complete. See the message above.' }
    $needsReboot = $false
    foreach ($name in @('Microsoft-Windows-Subsystem-Linux','VirtualMachinePlatform')) {
        $feature = Get-WindowsOptionalFeature -Online -FeatureName $name
        if ($feature.State -ne 'Enabled') {
            Enable-WindowsOptionalFeature -Online -FeatureName $name -All -NoRestart | Out-Null
            $needsReboot = $true
        }
    }
    if ($needsReboot) {
        Write-Host 'WSL features enabled. Restart Windows, then run this same install.bat again to continue.'
        if (-not $PrepareOnly) { Read-Host 'Press Enter to close (restart Windows manually)' | Out-Null }
        exit 3010
    }
    Invoke-Checked wsl @('--update')
    Invoke-Checked wsl @('--set-default-version','2')
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        Start-Process 'ms-windows-store://pdp/?ProductId=9NBLGGH4NNS1'
        throw 'Install/update Microsoft App Installer in the Store window, then run install.bat again.'
    }
    $dockerDesktop = @(
        (Join-Path $env:ProgramFiles 'Docker\Docker\Docker Desktop.exe'),
        (Join-Path $env:LOCALAPPDATA 'Programs\DockerDesktop\Docker Desktop.exe')
    ) | Where-Object { Test-Path $_ } | Select-Object -First 1
    if (-not $dockerDesktop) {
        Invoke-Checked winget @('install','--id','Docker.DockerDesktop','--exact','--source','winget','--scope','machine','--accept-source-agreements','--accept-package-agreements')
        $dockerDesktop = Join-Path $env:ProgramFiles 'Docker\Docker\Docker Desktop.exe'
    }
    $env:Path = [Environment]::GetEnvironmentVariable('Path','Machine') + ';' + [Environment]::GetEnvironmentVariable('Path','User') + ';' + (Join-Path $env:ProgramFiles 'Docker\Docker\resources\bin')
    Start-Process $dockerDesktop
    Write-Host 'Starting Docker Desktop. Complete its first-run screen if shown.'
    $ready = $false
    for ($i=0; $i -lt 120; $i++) {
        & docker info --format '{{.OSType}}' 2>$null | Out-Null
        if ($LASTEXITCODE -eq 0) { $ready = $true; break }
        Start-Sleep -Seconds 5
    }
    if (-not $ready) { throw 'Docker is not ready. Check virtualization/WSL and Docker Desktop, then run install.bat again.' }
    $python = Find-CompatiblePython
    if (-not $python) {
        Invoke-Checked winget @('install','--id','Python.Python.3.12','--exact','--source','winget','--scope','machine','--silent','--accept-source-agreements','--accept-package-agreements')
        $python = Find-CompatiblePython
    }
    if (-not $python) { throw 'Python installation was not found. Restart install.bat after Python installation finishes.' }
    Write-Host ('Using existing verified Python: ' + $python)
    if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
        $gitPath = Join-Path $env:ProgramFiles 'Git\cmd'
        if (-not (Test-Path (Join-Path $gitPath 'git.exe'))) {
            Invoke-Checked winget @('install','--id','Git.Git','--exact','--source','winget','--silent','--accept-source-agreements','--accept-package-agreements')
        }
        $env:PATH = $gitPath + ';' + $env:PATH
        if (-not (Get-Command git -ErrorAction SilentlyContinue)) { throw 'Git installed but unavailable. Reopen install.bat.' }
    }
    $env:PYTHONUTF8 = '1'
    if ($PrepareOnly) { exit 0 }
    if ($Gui) {
        Invoke-Checked $python @((Join-Path (Split-Path $PSScriptRoot -Parent) 'gui.py'))
    } else {
        Invoke-Checked $python @((Join-Path $PSScriptRoot 'install.py'))
    }
} catch {
    Write-Host ('Installation stopped: ' + $_.Exception.Message) -ForegroundColor Red
    if ($Gui) {
        Add-Type -AssemblyName System.Windows.Forms
        [System.Windows.Forms.MessageBox]::Show($_.Exception.Message, 'MeDIAuto installation stopped') | Out-Null
    } elseif (-not $PrepareOnly) { Read-Host 'Press Enter to close' | Out-Null }
    exit 1
}

$ErrorActionPreference = 'Stop'
$scriptPath = $PSCommandPath
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$admin = ([Security.Principal.WindowsPrincipal]$identity).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $admin) {
    $p = Start-Process powershell -Verb RunAs -Wait -PassThru -ArgumentList @('-NoProfile','-ExecutionPolicy','Bypass','-File',('"' + $scriptPath + '"'))
    exit $p.ExitCode
}
Set-Location $PSScriptRoot
function Invoke-Checked {
    param([string]$Program, [string[]]$Arguments)
    & $Program @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$Program failed (exit $LASTEXITCODE)." }
}
try {
    if (-not [Environment]::Is64BitOperatingSystem -or $env:PROCESSOR_ARCHITECTURE -eq 'ARM64') { throw 'An x86-64 Windows PC is required.' }
    if ([Environment]::OSVersion.Version.Build -lt 19045) { throw 'Update Windows to a supported Docker Desktop version first (Windows 10 22H2 / Windows 11 or newer supported build).' }
    $runtime = Join-Path $PSScriptRoot '.runtime'
    New-Item -ItemType Directory -Force $runtime | Out-Null
    # Generated DB/admin credentials are accessible only to this user, Administrators and SYSTEM.
    $sid = $identity.User.Value
    Invoke-Checked icacls @($runtime,'/inheritance:r','/grant:r',('*' + $sid + ':(OI)(CI)F'),'*S-1-5-18:(OI)(CI)F','*S-1-5-32-544:(OI)(CI)F')
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
        Read-Host 'Press Enter to close (restart Windows manually)' | Out-Null
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
    $python = Join-Path $env:ProgramFiles 'Python312\python.exe'
    if (-not (Test-Path $python)) {
        Invoke-Checked winget @('install','--id','Python.Python.3.12','--exact','--source','winget','--scope','machine','--silent','--accept-source-agreements','--accept-package-agreements')
        $reg = 'HKLM:\SOFTWARE\Python\PythonCore\3.12\InstallPath'
        if (Test-Path $reg) { $python = Join-Path (Get-Item $reg).GetValue('') 'python.exe' }
    }
    if (-not (Test-Path $python)) { throw 'Python installation was not found. Restart install.bat after Python installation finishes.' }
    $env:PYTHONUTF8 = '1'
    Invoke-Checked $python @((Join-Path $PSScriptRoot 'install.py'))
} catch {
    Write-Host ('Installation stopped: ' + $_.Exception.Message) -ForegroundColor Red
    Read-Host 'Press Enter to close' | Out-Null
    exit 1
}

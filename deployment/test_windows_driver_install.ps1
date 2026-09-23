$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'native/setup-nvidia-driver.ps1')
$script:update=[pscustomobject]@{Title='NVIDIA - Display - 32.0.15.8180';DriverClass='Display';DriverHardwareID='PCI\VEN_10DE&DEV_1';EulaAccepted=$true}
$script:updates=[pscustomobject]@{Count=1}
$script:updates|Add-Member ScriptMethod Item {param($i) return $script:update}
$script:searcher=[pscustomobject]@{Online=$false}
$script:searcher|Add-Member ScriptMethod Search {param($query) return [pscustomobject]@{ResultCode=2;Updates=$script:updates}}
$script:collection=[pscustomobject]@{}
$script:collection|Add-Member ScriptMethod Add {param($update) return 0}
$script:downloader=[pscustomobject]@{Updates=$null}
$script:downloader|Add-Member ScriptMethod Download {return [pscustomobject]@{ResultCode=$script:downloadCode}}
$script:installer=[pscustomobject]@{Updates=$null;AllowSourcePrompts=$true}
$script:installer|Add-Member ScriptMethod Install {return [pscustomobject]@{ResultCode=2;RebootRequired=$true}}
$script:session=[pscustomobject]@{ClientApplicationID=''}
$script:session|Add-Member ScriptMethod CreateUpdateSearcher {return $script:searcher}
$script:session|Add-Member ScriptMethod CreateUpdateDownloader {return $script:downloader}
$script:session|Add-Member ScriptMethod CreateUpdateInstaller {return $script:installer}
function Test-MediautoNvidiaDriver {return $false}
function Get-CimInstance {return [pscustomobject]@{PNPDeviceID='PCI\VEN_10DE&DEV_1'}}
function New-Object {param($ComObject) if($ComObject -eq 'Microsoft.Update.Session'){return $script:session};if($ComObject -eq 'Microsoft.Update.UpdateColl'){return $script:collection};throw 'Unexpected COM object'}
$script:downloadCode=2
if((Install-MediautoNvidiaDriver) -ne 3010){throw 'Expected reboot-required result'}
$script:downloadCode=4
try {Install-MediautoNvidiaDriver;throw 'Expected download failure'}catch{if($_.Exception.Message -notlike 'Windows Update GPU driver download failed*'){throw}}
$script:updates.Count=0
try {Install-MediautoNvidiaDriver;throw 'Expected no compatible offer'}catch{if($_.Exception.Message -notlike 'Windows Update does not offer*'){throw}}
Write-Host 'Mocked Windows Update: install/reboot, download failure, no compatible offer passed.'

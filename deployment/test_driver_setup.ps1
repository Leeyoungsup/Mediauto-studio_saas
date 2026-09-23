$ErrorActionPreference='Stop'
foreach ($mode in @('native','host')) {
    $path=Join-Path $PSScriptRoot "$mode/setup-nvidia-driver.ps1"
    $t=$null;$e=$null;[System.Management.Automation.Language.Parser]::ParseFile($path,[ref]$t,[ref]$e)|Out-Null
    if($e.Count){throw $e[0]}
    . $path
    if((Get-NvidiaMarketingVersion 'NVIDIA - Display - 32.0.15.7688') -ne [version]'576.88'){throw 'version conversion'}
    if((Get-NvidiaMarketingVersion 'NVIDIA - Display - 30.0.14.7141') -ne [version]'471.41'){throw 'old version conversion'}
    $updates=@(
        [pscustomobject]@{Title='NVIDIA - Display - 30.0.14.7141';DriverClass='Display';DriverHardwareID='PCI\VEN_10DE&DEV_1'},
        [pscustomobject]@{Title='NVIDIA - Display - 32.0.15.7688';DriverClass='Display';DriverHardwareID='PCI\VEN_10DE&DEV_1'},
        [pscustomobject]@{Title='NVIDIA - Display - 32.0.15.8180';DriverClass='Display';DriverHardwareID='PCI\VEN_10DE&DEV_1'},
        [pscustomobject]@{Title='Other - Display - 32.0.15.8180';DriverClass='Display';DriverHardwareID='PCI\VEN_8086&DEV_1'},
        [pscustomobject]@{Title='NVIDIA - Audio - 32.0.15.8180';DriverClass='MEDIA';DriverHardwareID='PCI\VEN_10DE&DEV_2'}
    )
    $chosen=@(Select-MediautoDriverUpdates $updates)
    if($chosen.Count -ne 1 -or $chosen[0].Title -notmatch '8180'){throw 'driver filtering'}
    function Test-MediautoNvidiaDriver { return $true }
    if((Install-MediautoNvidiaDriver) -ne 0){throw 'existing driver reuse'}
    function Test-MediautoNvidiaDriver { return $false }
    function Get-CimInstance { return @() }
    try { Install-MediautoNvidiaDriver;throw 'Missing hardware accepted' }
    catch {if($_.Exception.Message -notlike 'No NVIDIA PCI device*'){throw}}
    Remove-Item Function:Get-CimInstance
    Write-Host "$mode driver parser, version, selection, reuse and missing-hardware tests passed"
}

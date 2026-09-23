$ErrorActionPreference = 'Stop'

function Get-NvidiaMarketingVersion([string]$Title) {
    # Windows driver version 32.0.15.7688 corresponds to NVIDIA 576.88.
    if ($Title -match '(\d+)\.(\d+)\.(\d+)\.(\d{4})(?:\D|$)') {
        $digits = ([int]$Matches[3] % 10).ToString() + $Matches[4]
        return [version]($digits.Substring(0,3) + '.' + $digits.Substring(3))
    }
    return $null
}
function Test-MediautoNvidiaDriver {
    $smi = Get-Command nvidia-smi.exe -ErrorAction SilentlyContinue
    if (-not $smi) { return $false }
    try { $versions = @(& $smi.Source --query-gpu=driver_version --format=csv,noheader 2>$null) }
    catch { return $false }
    if ($LASTEXITCODE -ne 0 -or $versions.Count -eq 0) { return $false }
    foreach ($value in $versions) {
        try { if ([version]$value.Trim() -lt [version]'570.65') { return $false } }
        catch { return $false }
    }
    return $true
}
function Select-MediautoDriverUpdates($Updates) {
    $eligible = @($Updates | Where-Object {
        $_.DriverClass -eq 'Display' -and $_.DriverHardwareID -match '^PCI\\VEN_10DE' -and
        $_.Title -match 'NVIDIA' -and (Get-NvidiaMarketingVersion $_.Title) -ge [version]'570.65'
    })
    # Windows Update already filters for this PC. Pick one newest update per device ID.
    foreach ($group in ($eligible | Group-Object DriverHardwareID)) {
        $group.Group | Sort-Object { Get-NvidiaMarketingVersion $_.Title } -Descending | Select-Object -First 1
    }
}
function Install-MediautoNvidiaDriver {
    if (Test-MediautoNvidiaDriver) { Write-Host 'NVIDIA driver is compatible; keeping it.'; return 0 }
    $devices = @(Get-CimInstance Win32_PnPEntity | Where-Object { $_.PNPDeviceID -match '^PCI\\VEN_10DE' })
    if (-not $devices) { throw 'No NVIDIA PCI device was found. GPU installation cannot continue.' }
    Write-Host 'NVIDIA driver is missing/too old. Searching Windows Update for a compatible signed display driver...'
    $session = New-Object -ComObject Microsoft.Update.Session
    $session.ClientApplicationID = 'MeDIAuto GPU installer'
    $searcher = $session.CreateUpdateSearcher()
    $searcher.Online = $true
    $search = $searcher.Search("IsInstalled=0 and IsHidden=0 and Type='Driver'")
    if ($search.ResultCode -ne 2) { throw 'Windows Update driver search did not complete successfully.' }
    $offered = @(); for ($i=0; $i -lt $search.Updates.Count; $i++) { $offered += $search.Updates.Item($i) }
    $chosen = @(Select-MediautoDriverUpdates $offered)
    if (-not $chosen) {
        throw 'Windows Update does not offer an NVIDIA display driver >=570.65 for this PC. Install the current supported driver from https://www.nvidia.com/drivers/ or the laptop vendor, reboot, and rerun setup. No CPU fallback was enabled.'
    }
    $collection = New-Object -ComObject Microsoft.Update.UpdateColl
    foreach ($update in $chosen) {
        Write-Host ('Installing signed GPU driver: '+$update.Title)
        if (-not $update.EulaAccepted) { $update.AcceptEula() }
        $null = $collection.Add($update)
    }
    $downloader = $session.CreateUpdateDownloader(); $downloader.Updates = $collection
    $download = $downloader.Download()
    if ($download.ResultCode -ne 2) { throw 'Windows Update GPU driver download failed; check Windows Update/network policy.' }
    $installer = $session.CreateUpdateInstaller(); $installer.Updates = $collection
    $installer.AllowSourcePrompts = $false
    $result = $installer.Install()
    if ($result.ResultCode -ne 2) { throw ('GPU driver installation failed. Windows Update result: '+$result.ResultCode) }
    if ($result.RebootRequired -or -not (Test-MediautoNvidiaDriver)) {
        Write-Host 'REBOOT REQUIRED: GPU driver installed. Restart Windows manually and rerun the same installer. Setup will not restart this PC automatically.'
        return 3010
    }
    Write-Host 'NVIDIA driver installation and version check passed.'
    return 0
}
if ($MyInvocation.InvocationName -ne '.') {
    try { exit (Install-MediautoNvidiaDriver) }
    catch { Write-Host ('GPU DRIVER SETUP FAILED: '+$_.Exception.Message); exit 1 }
}

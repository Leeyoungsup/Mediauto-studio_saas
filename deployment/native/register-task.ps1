param(
    [Parameter(Mandatory=$true)][string]$PythonExe,
    [Parameter(Mandatory=$true)][string]$Runner,
    [Parameter(Mandatory=$true)][string]$Settings,
    [Parameter(Mandatory=$true)][string]$TaskName,
    [Parameter(Mandatory=$true)][int]$Port,
    [string]$Bind = '127.0.0.1'
)
$ErrorActionPreference = 'Stop'
$user = [Security.Principal.WindowsIdentity]::GetCurrent().Name
$action = New-ScheduledTaskAction -Execute $PythonExe -Argument ('"' + $Runner + '" "' + $Settings + '"')
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $user
$principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited
$options = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -MultipleInstances IgnoreNew -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Principal $principal -Settings $options -Force | Out-Null
$running = Get-ScheduledTask -TaskName $TaskName
if ($running.State -eq 'Running') { Stop-ScheduledTask -TaskName $TaskName }
Start-ScheduledTask -TaskName $TaskName
if ($Bind -eq '0.0.0.0') {
    Get-NetFirewallRule -Name $TaskName -ErrorAction SilentlyContinue | Remove-NetFirewallRule
    New-NetFirewallRule -Name $TaskName -DisplayName 'MeDIAuto native app' -Direction Inbound -Action Allow -Protocol TCP -LocalPort $Port -RemoteAddress LocalSubnet | Out-Null
}

# Run from an Administrator PowerShell. Permit only the monitored VM.
$taskPrincipal = [Security.Principal.WindowsPrincipal]::new([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $taskPrincipal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Open PowerShell as Administrator to apply this VM-scoped firewall rule.'
}
if (-not (Get-NetFirewallRule -DisplayName 'OpenOps receiver from monitored VM' -ErrorAction SilentlyContinue)) {
    New-NetFirewallRule -DisplayName 'OpenOps receiver from monitored VM' -Direction Inbound -Action Allow -Protocol TCP -LocalPort 8096 -LocalAddress 192.168.1.17 -RemoteAddress 192.168.1.202 -Profile Any | Out-Null
}
Write-Output 'OpenOps receiver permitted from 192.168.1.202 to 192.168.1.17:8096.'

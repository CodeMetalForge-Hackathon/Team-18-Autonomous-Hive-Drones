param([Parameter(Mandatory=$true)][string]$CredentialsFile,
 [Parameter(Mandatory=$true)][switch]$AllowNetworkSwitch, [string]$Python = 'python')
$ErrorActionPreference = 'Stop'
if (!$AllowNetworkSwitch) { throw 'This test disconnects normal Wi-Fi; supply -AllowNetworkSwitch to opt in.' }
$wifiCredentials = Get-Content -LiteralPath $CredentialsFile -Raw | ConvertFrom-Json
$wifiBefore = (netsh wlan show interfaces) -join "`n"
$originalProfileMatch = [regex]::Match($wifiBefore,'(?m)^\s*Profile\s*:\s*(.+?)\s*$')
if (!$originalProfileMatch.Success) { throw 'Cannot determine original Wi-Fi profile.' }
$originalWifiProfile = $originalProfileMatch.Groups[1].Value.Trim()
try {
 netsh wlan connect "name=$($wifiCredentials.ssid)" "ssid=$($wifiCredentials.ssid)" 'interface=Wi-Fi'
 $joinedRover = $false
 for ($attempt=0; $attempt -lt 12; $attempt++) {
  Start-Sleep -Seconds 1
  $wifiCurrent=(netsh wlan show interfaces) -join "`n"
  if ($wifiCurrent -match ('(?m)^\s*SSID\s*:\s*'+[regex]::Escape($wifiCredentials.ssid)+'\s*$')) { $joinedRover=$true;break }
 }
 if (!$joinedRover) { throw 'Rover Wi-Fi connection failed.' }
 Start-Sleep -Seconds 2
 & $Python (Join-Path $PSScriptRoot '..\check_wifi.py')
 if ($LASTEXITCODE -ne 0) { throw 'Wireless API check failed.' }
} finally {
 netsh wlan connect "name=$originalWifiProfile" 'interface=Wi-Fi'
 Start-Sleep -Seconds 5
 Get-NetConnectionProfile | Select-Object Name,InterfaceAlias,IPv4Connectivity | Format-Table -AutoSize
}

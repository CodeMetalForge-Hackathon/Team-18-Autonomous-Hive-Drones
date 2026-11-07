param([Parameter(Mandatory=$true)][string]$DeviceInstanceId, [switch]$Install)
$ErrorActionPreference = 'Stop'
if ($DeviceInstanceId -notmatch '^USB\\VID_3251&PID_1930\\[^\\]+$') { throw 'Expected an exact Aurora 930 instance ID.' }
try {
 $signature = Get-AuthenticodeSignature "$env:SystemRoot\System32\drivers\winusb.sys"
 if ($signature.Status -ne 'Valid') { throw 'Inbox WinUSB signature is not valid.' }
 Add-Type -Path (Join-Path $PSScriptRoot 'AuroraWinUsb.cs')
 [AuroraWinUsb]::Run($DeviceInstanceId, $Install.IsPresent)
 if (!$Install) { return }
 $deviceParameters = "HKLM:\SYSTEM\CurrentControlSet\Enum\$DeviceInstanceId\Device Parameters"
 New-Item -Path $deviceParameters -Force | Out-Null
 $existingGuids = @((Get-ItemProperty -Path $deviceParameters -Name DeviceInterfaceGUIDs -ErrorAction SilentlyContinue).DeviceInterfaceGUIDs) | Where-Object { $_ }
 $interfaceGuids = @($existingGuids + '{ca3e7ab9-b4c3-4ae6-8251-579ef933890f}' | Select-Object -Unique)
 New-ItemProperty -Path $deviceParameters -Name DeviceInterfaceGUIDs -PropertyType MultiString -Value $interfaceGuids -Force | Out-Null
 pnputil /restart-device $DeviceInstanceId
 if ($LASTEXITCODE -ne 0) { throw 'Device restart failed.' }
} catch { Write-Error $_; exit 1 }

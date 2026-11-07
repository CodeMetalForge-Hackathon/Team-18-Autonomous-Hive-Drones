param([Parameter(Mandatory=$true)][string]$OutputDirectory,
 [Parameter(Mandatory=$true)][string]$Esptool, [string]$Port = 'COM5')
$ErrorActionPreference = 'Stop'
$toolDir = $OutputDirectory
$chunkSize = 131072
$partsDir = Join-Path $toolDir 'backup-parts'
New-Item -ItemType Directory -Force -Path $partsDir | Out-Null
for ($part = 0; $part -lt 32; $part++) {
 $partPath = Join-Path $partsDir "$part.bin"
 $valid = $false
 for ($attempt = 1; $attempt -le 4; $attempt++) {
  & $Esptool --chip esp32 --port $Port --baud 500000 read_flash ($part * $chunkSize) $chunkSize $partPath *> (Join-Path $partsDir "$part.log")
  if ($LASTEXITCODE -eq 0 -and (Test-Path $partPath) -and (Get-Item $partPath).Length -eq $chunkSize) { $valid = $true; break }
 }
 if (!$valid) { throw "Backup failed on chunk $part" }
 Write-Output "Backup chunk $($part + 1)/32 complete"
}
$backupPath = Join-Path $toolDir 'factory-backup-4MB.bin'
$stream = [System.IO.File]::Create($backupPath)
try { for ($part = 0; $part -lt 32; $part++) { $bytes = [System.IO.File]::ReadAllBytes((Join-Path $partsDir "$part.bin")); $stream.Write($bytes,0,$bytes.Length) } } finally { $stream.Dispose() }
Get-FileHash -LiteralPath $backupPath -Algorithm SHA256 | Format-List

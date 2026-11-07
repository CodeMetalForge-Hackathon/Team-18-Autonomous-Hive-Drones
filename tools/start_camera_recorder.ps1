param(
 [Parameter(Mandatory=$true)][string]$Python,
 [Parameter(Mandatory=$true)][string]$CameraExe,
 [Parameter(Mandatory=$true)][string]$DllDirectory,
 [Parameter(Mandatory=$true)][string]$Ffmpeg,
 [Parameter(Mandatory=$true)][string]$OutputDirectory
)
$ErrorActionPreference = 'Stop'
$repo = Split-Path $PSScriptRoot -Parent
if (Test-Path (Join-Path $repo '.camera-recorder.json')) {
 throw 'A recorder configuration already exists. Check camera_shared.py status before starting another.'
}
$pythonPath = (Resolve-Path -LiteralPath $Python).Path
$arguments = @(
 (Join-Path $PSScriptRoot 'camera_recorder.py'),
 '--camera-exe', (Resolve-Path -LiteralPath $CameraExe).Path,
 '--dll-directory', (Resolve-Path -LiteralPath $DllDirectory).Path.TrimEnd('\'),
 '--ffmpeg', (Resolve-Path -LiteralPath $Ffmpeg).Path,
 '--output', (Resolve-Path -LiteralPath $OutputDirectory).Path.TrimEnd('\')
)
# Windows paths cannot contain quote characters. Quote each resolved argument
# so spaces survive Start-Process's command-line argument joining.
$quoted = ($arguments | ForEach-Object { '"' + $_ + '"' }) -join ' '
$process = Start-Process -FilePath $pythonPath -ArgumentList $quoted -WindowStyle Hidden `
 -RedirectStandardOutput (Join-Path $OutputDirectory 'recorder.stdout.log') `
 -RedirectStandardError (Join-Path $OutputDirectory 'recorder.stderr.log') -PassThru
Write-Output "Recorder launcher PID: $($process.Id). Check camera_shared.py status."

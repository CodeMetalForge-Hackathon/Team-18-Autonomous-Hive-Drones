param(
    [Parameter(Mandatory=$true)][string]$SdkInclude,
    [string]$OutputDirectory = "$PSScriptRoot\..\build\camera"
)
$ErrorActionPreference = 'Stop'
$vswhere = "${env:ProgramFiles(x86)}\Microsoft Visual Studio\Installer\vswhere.exe"
$visualStudio = & $vswhere -latest -property installationPath
if (!$visualStudio) { throw 'Visual Studio C++ build tools not found.' }
$compilerRoot = (Get-ChildItem "$visualStudio\VC\Tools\MSVC" -Directory | Sort-Object Name -Descending | Select-Object -First 1).FullName
$kitRoot = "${env:ProgramFiles(x86)}\Windows Kits\10"
$kitVersion = Get-ChildItem "$kitRoot\Include" -Directory | Sort-Object Name -Descending | Select-Object -First 1
$env:INCLUDE = "$compilerRoot\include;$kitRoot\Include\$($kitVersion.Name)\ucrt;$kitRoot\Include\$($kitVersion.Name)\shared;$kitRoot\Include\$($kitVersion.Name)\um"
$env:LIB = "$compilerRoot\lib\x64;$kitRoot\Lib\$($kitVersion.Name)\ucrt\x64;$kitRoot\Lib\$($kitVersion.Name)\um\x64"
$compiler = "$compilerRoot\bin\Hostarm64\x64\cl.exe"
if (!(Test-Path $compiler)) { $compiler = "$compilerRoot\bin\Hostx64\x64\cl.exe" }
New-Item -ItemType Directory -Force -Path $OutputDirectory | Out-Null
& $compiler /nologo /EHsc /MD /std:c++17 /D_ITERATOR_DEBUG_LEVEL=0 /DDEPTRUM_DLL= "/I$SdkInclude" "$PSScriptRoot\camera_capture.cpp" "/Fo$OutputDirectory\camera_capture.obj" "/Fe$OutputDirectory\camera_capture.exe"
if ($LASTEXITCODE -ne 0) { throw 'Camera capture build failed.' }

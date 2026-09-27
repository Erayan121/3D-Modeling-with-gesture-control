$ErrorActionPreference = 'Stop'
$root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$build = [System.IO.Path]::GetFullPath((Join-Path $root 'build-hand-modeling'))
$dist = [System.IO.Path]::GetFullPath((Join-Path $root 'dist-hand-modeling'))
foreach ($target in @($build, $dist)) {
    if (-not $target.StartsWith($root + [System.IO.Path]::DirectorySeparatorChar)) {
        throw "unsafe build target: $target"
    }
    if (Test-Path -LiteralPath $target) { Remove-Item -LiteralPath $target -Recurse -Force }
}
$matplotlibConfig = Join-Path $build 'matplotlib'
New-Item -ItemType Directory -Path $matplotlibConfig -Force | Out-Null
$env:MPLCONFIGDIR = $matplotlibConfig
$python = Join-Path $root '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) {
    throw "project Python not found: $python"
}
$spec = Join-Path $root 'packaging\hand-modeling-demo.spec'
$env:HAND_MODELING_ONEFILE = '0'
& $python -m PyInstaller --noconfirm --clean --workpath (Join-Path $build 'onedir') --distpath $dist $spec
if ($LASTEXITCODE -ne 0) { throw 'onedir build failed' }
& (Join-Path $root 'packaging\verify-hand-modeling.ps1') -Executable (Join-Path $dist 'HandModelingDemo\HandModelingDemo.exe')
$env:HAND_MODELING_ONEFILE = '1'
& $python -m PyInstaller --noconfirm --clean --workpath (Join-Path $build 'onefile') --distpath $dist $spec
if ($LASTEXITCODE -ne 0) { throw 'onefile build failed' }
& (Join-Path $root 'packaging\verify-hand-modeling.ps1') -Executable (Join-Path $dist 'HandModelingDemo.exe')

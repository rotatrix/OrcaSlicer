param([ValidateSet('deps', 'build')][string]$Stage)
$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $true
Set-Location (Resolve-Path "$PSScriptRoot/../..")
if ($Stage -eq 'deps') {
    cmake -S deps -B deps/build -G 'Visual Studio 17 2022' -A x64 -DCMAKE_BUILD_TYPE=Release -DDEP_DEBUG=OFF
    cmake --build deps/build --config Release --target deps --parallel 1
} else {
    $env:git_commit_hash = $env:GITHUB_SHA
    cmake -S . -B build -G 'Visual Studio 17 2022' -A x64 `
        -DCMAKE_BUILD_TYPE=Release -DCMAKE_CONFIGURATION_TYPES=Release `
        -DSLIC3R_OPENAXIS=ON -DOPENAXIS_SOURCE_DIR= -DSLIC3R_PCH=ON -DORCA_TOOLS=OFF
    cmake --build build --config Release --parallel 2
    & ./scripts/run_gettext.bat
    cmake --install build --config Release
    cmake -S tests/openaxis -B build/openaxis-checks -G 'Visual Studio 17 2022' -A x64
    cmake --build build/openaxis-checks --config Release --parallel 2
    ctest --test-dir build/openaxis-checks -C Release --output-on-failure
    $smoke = Start-Process -FilePath "$PWD/build/OrcaSlicer/orca-slicer.exe" -ArgumentList '--help' `
        -WorkingDirectory "$PWD/build/OrcaSlicer" -WindowStyle Hidden -PassThru
    if (-not $smoke.WaitForExit(60000)) { throw 'Packaged application smoke check timed out' }
    if ($smoke.ExitCode -ne 0) { throw "Packaged application smoke check failed: $($smoke.ExitCode)" }
}

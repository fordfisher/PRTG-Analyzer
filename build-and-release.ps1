# Build PyPRTG_CLA EXE and create a release zip with apply-update.bat at folder root
# so the in-app updater finds it after extracting. Run from repo root.
# Usage: .\build-and-release.ps1  [optional: version override, e.g. 1.5.2]

$ErrorActionPreference = "Stop"
$repoRoot = $PSScriptRoot
Set-Location $repoRoot

# Get version from source (or use first script arg)
$versionFile = Join-Path $repoRoot "source\analyzer\version.py"
$versionLine = Get-Content $versionFile | Select-String 'ANALYZER_VERSION\s*=\s*"([^"]+)"'
if ($versionLine -match '"([^"]+)"') { $version = $matches[1] } else { $version = "0.0.0" }
if ($args.Count -ge 1) { $version = $args[0] }

Write-Host "Version: $version"

# Stop running EXE so build can overwrite
Get-Process -Name "PyPRTG_CLA" -ErrorAction SilentlyContinue | Stop-Process -Force

# Build
python -m PyInstaller PRTG_Analyzer.spec --noconfirm
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$buildDir = Join-Path $repoRoot "dist\PyPRTG_CLA"
$internalBat = Join-Path $buildDir "_internal\apply-update.bat"
$rootBat = Join-Path $buildDir "apply-update.bat"

# Required: copy apply-update.bat to folder root so the release zip contains it at root
if (Test-Path $internalBat) {
    Copy-Item -Path $internalBat -Destination $rootBat -Force
    Write-Host "Copied apply-update.bat to folder root for release zip."
} else {
    Write-Warning "apply-update.bat not found in _internal; release zip may fail for old updater clients."
}

# Create versioned folder and zip for GitHub release
$versionedName = "PyPRTG_CLA_v$version"
$distDir = Join-Path $repoRoot "dist"
$versionedDir = Join-Path $distDir $versionedName
$zipPath = Join-Path $distDir "$versionedName.zip"

if (Test-Path $versionedDir) { Remove-Item -Recurse -Force $versionedDir }
Start-Sleep -Seconds 2
Copy-Item -Path $buildDir -Destination $versionedDir -Recurse

# Zip (ensure apply-update.bat is at root inside the zip); wait for file handles to release
if (Test-Path $zipPath) { Remove-Item $zipPath -Force }
$zipDone = $false
foreach ($attempt in 1..3) {
    Start-Sleep -Seconds 3
    try {
        Compress-Archive -Path $versionedDir -DestinationPath $zipPath -Force
        $zipDone = $true
        break
    } catch {
        Write-Host "Zip attempt $attempt failed (file in use?). Retrying..."
    }
}
if (-not $zipDone) { Write-Warning "Could not create zip (files locked). Run: Compress-Archive -Path '$versionedDir' -DestinationPath '$zipPath' -Force" }

Write-Host "Release zip: $zipPath"
Write-Host "Upload this zip to the GitHub release for v$version so the in-app updater finds apply-update.bat at folder root."

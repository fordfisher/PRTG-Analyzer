# Build PyPRTG_CLA one-file EXE (version in filename) and create minimal release zip.
# Zip contains: PyPRTG_CLA_v{version}.exe, apply-update.bat, README.md, manual.html (no _internal, no manual.md).
# Run from repo root. Usage: .\build-and-release.ps1  [optional: version override, e.g. 1.5.2]

$ErrorActionPreference = "Stop"
$repoRoot = $PSScriptRoot
Set-Location $repoRoot

# Get version from source (or use first script arg)
$versionFile = Join-Path $repoRoot "source\analyzer\version.py"
$versionLine = Get-Content $versionFile | Select-String 'ANALYZER_VERSION\s*=\s*"([^"]+)"'
if ($versionLine -match '"([^"]+)"') { $version = $matches[1] } else { $version = "0.0.0" }
if ($args.Count -ge 1) { $version = $args[0] }

Write-Host "Version: $version"

# Stop any running PyPRTG_CLA (old: PyPRTG_CLA.exe; new: PyPRTG_CLA_vX.Y.Z.exe)
Get-Process | Where-Object { $_.Name -like "PyPRTG_CLA*" } | Stop-Process -Force -ErrorAction SilentlyContinue

# Build one-file EXE (output: dist/PyPRTG_CLA_v{version}.exe)
python -m PyInstaller PRTG_Analyzer.spec --noconfirm
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$versionedName = "PyPRTG_CLA_v$version"
$distDir = Join-Path $repoRoot "dist"
$singleExe = Join-Path $distDir "$versionedName.exe"
$versionedDir = Join-Path $distDir $versionedName
$zipPath = Join-Path $distDir "$versionedName.zip"

if (-not (Test-Path $singleExe)) {
    Write-Error "Build did not produce $singleExe"
    exit 1
}

# Minimal release folder: exe, apply-update.bat, README.md, manual.html
if (Test-Path $versionedDir) { Remove-Item -Recurse -Force $versionedDir }
New-Item -ItemType Directory -Path $versionedDir -Force | Out-Null

Move-Item -Path $singleExe -Destination (Join-Path $versionedDir "$versionedName.exe") -Force
Copy-Item -Path (Join-Path $repoRoot "apply-update.bat") -Destination $versionedDir -Force
Copy-Item -Path (Join-Path $repoRoot "README.md") -Destination $versionedDir -Force
Copy-Item -Path (Join-Path $repoRoot "manual.html") -Destination $versionedDir -Force

Write-Host "Release folder: $versionedDir (exe, apply-update.bat, README.md, manual.html)"

# Zip for GitHub release
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
Write-Host "Upload this zip to the GitHub release for v$version."

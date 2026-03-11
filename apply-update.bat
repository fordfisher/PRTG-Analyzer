@echo off
REM apply-update.bat — spawned by the OLD version after extracting the new ZIP.
REM Usage: apply-update.bat <old_install_dir>
REM
REM 1. Wait a few seconds for the old process to shut down.
REM 2. Kill any remaining PyPRTG_CLA.exe / port-8077 process.
REM 3. Start the new EXE (located next to this script).

setlocal

echo [apply-update] Waiting for old process to exit...
timeout /t 4 /nobreak >nul

echo [apply-update] Stopping PyPRTG_CLA.exe by name...
taskkill /IM PyPRTG_CLA.exe /F >nul 2>&1

echo [apply-update] Stopping any process on port 8077...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":8077 " ^| findstr LISTENING') do (
    taskkill /PID %%a /F >nul 2>&1
)

timeout /t 1 /nobreak >nul

echo [apply-update] Starting new version from %~dp0 ...
start "" "%~dp0PyPRTG_CLA.exe"

echo [apply-update] Done.
endlocal

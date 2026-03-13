@echo off
REM apply-update.bat — spawned by the OLD version after extracting the new ZIP.
REM Usage: apply-update.bat <old_install_dir>
REM
REM 1. Wait a few seconds for the old process to shut down.
REM 2. Kill process on port 8077 (app server) and any EXE in old_install_dir (PyPRTG_CLA.exe or PyPRTG_CLA_vX.Y.Z.exe).
REM 3. New EXE is started by the updater (this script does not start it).

setlocal

echo [apply-update] Waiting for old process to exit...
timeout /t 4 /nobreak >nul

REM Kill by EXE name(s) in old install dir (works for PyPRTG_CLA.exe and PyPRTG_CLA_vX.Y.Z.exe)
echo [apply-update] Stopping old EXE by name...
for %%f in ("%~1\*.exe") do (
    taskkill /IM "%%~nxf" /F >nul 2>&1
)

echo [apply-update] Stopping any process on port 8077...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":8077 " ^| findstr LISTENING') do (
    taskkill /PID %%a /F >nul 2>&1
)

timeout /t 1 /nobreak >nul

echo [apply-update] Done. New version is started by the updater.
endlocal

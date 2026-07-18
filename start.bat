@echo off
cd /d "%~dp0"
title Paper Trading Engine

echo === Paper Trading Engine ===
echo.

:: Kill any leftover python processes from previous sessions
powershell -Command "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | Where-Object { $_.CommandLine -match 'run_offline|run_dashboard|monitor' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }" >nul 2>&1
timeout /t 4 /nobreak >nul

:: Verify clean kill — if any still running, wait and retry
powershell -Command "$r=Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | Where-Object { $_.CommandLine -match 'run_offline|run_dashboard' }; if($r){Start-Sleep 2; $r|ForEach-Object{Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue}}" >nul 2>&1

echo [1/3] Starting Freqtrade bot...
start /min "" .venv\Scripts\python.exe run_offline.py trade --config config/config.dryrun.json --strategy AlwaysBuyStrategy

timeout /t 20 /nobreak >nul

echo [2/3] Starting dashboard...
start /min "" .venv\Scripts\python.exe run_dashboard.py

timeout /t 10 /nobreak >nul

echo [3/4] Starting auto-audit monitor...
start /min /B "" .venv\Scripts\python.exe monitor.py

timeout /t 3 /nobreak >nul

echo [4/4] Opening browser...
start http://localhost:8000

echo.
echo   Bot:       http://localhost:8080
echo   Dashboard: http://localhost:8000
echo   Monitor:   monitor_log.csv
echo.
echo Close this window to stop.
echo.

:loop
timeout /t 60 /nobreak >nul
goto loop

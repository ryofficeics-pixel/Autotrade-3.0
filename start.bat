@echo off
cd /d "%~dp0"
title Paper Trading Engine

echo === Paper Trading Engine ===
echo.

:: Kill any leftover python processes from previous sessions
powershell -Command "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | Where-Object { $_.CommandLine -match 'run_offline|run_dashboard' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }" >nul 2>&1
timeout /t 3 /nobreak >nul

echo [1/3] Starting Freqtrade bot...
start /min "" .venv\Scripts\python.exe run_offline.py trade --config config/config.dryrun.json --strategy AlwaysBuyStrategy

timeout /t 20 /nobreak >nul

echo [2/3] Starting dashboard...
start /min "" .venv\Scripts\python.exe run_dashboard.py

timeout /t 10 /nobreak >nul

echo [3/3] Opening browser...
start http://localhost:8000

echo.
echo   Bot:       http://localhost:8080
echo   Dashboard: http://localhost:8000
echo.
echo Close this window to stop.
echo.

:loop
timeout /t 60 /nobreak >nul
goto loop

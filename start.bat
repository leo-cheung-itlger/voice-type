@echo off
title VoiceType
cd /d "%~dp0"

echo ========================================
echo   VoiceType
echo ========================================
echo.

if not exist "venv\Scripts\python.exe" (
    echo [1/3] Creating Python virtual environment...
    python -m venv venv
    if errorlevel 1 exit /b 1
    call venv\Scripts\activate.bat
    echo [2/3] Installing dependencies...
    pip install -r requirements.txt -q
    if errorlevel 1 exit /b 1
) else (
    call venv\Scripts\activate.bat
)

echo [3/3] Starting VoiceType services...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start-dev.ps1" -Root "%CD%"
if errorlevel 1 (
    echo.
    echo Start failed. Check logs\api_stderr.log, logs\frontend_dev.log, and logs\managed_server_*.log.
    exit /b 1
)

echo.
echo VoiceType services started.
echo   API: http://127.0.0.1:55342
echo   Web: http://127.0.0.1:55343
echo   ASR: 127.0.0.1:55341
echo.
echo This window can be closed. Background services will keep running.

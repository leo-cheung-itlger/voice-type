@echo off
setlocal
title VoiceType Live UI
cd /d "%~dp0"

echo ========================================
echo   VoiceType Live UI
echo ========================================
echo.
echo This starts the latest source UI in a browser.
echo Use the portable EXE only when publishing a packaged build.
echo.

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start-live-ui.ps1" -Root "%CD%"
if errorlevel 1 (
    echo.
    echo VoiceType Live UI failed to start. Check logs\api_stderr.log, logs\frontend_dev.log, and logs\managed_server_*.log.
    pause
    exit /b 1
)

echo.
echo VoiceType Live UI is running.
echo   Web: http://127.0.0.1:55343/#/
echo   API: http://127.0.0.1:55342
echo.
echo This window can be closed. Background services will keep running.

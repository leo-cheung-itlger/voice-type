@echo off
cd /d "%~dp0"
echo Stopping VoiceType services...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\stop-dev.ps1" -Root "%CD%"
if errorlevel 1 (
    echo Stop command failed.
    exit /b 1
)
echo VoiceType services stopped.

@echo off
chcp 65001 >nul
echo 正在停止所有 VoiceType 服务...

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\stop-dev.ps1" -Root "%~dp0"

echo 所有服务已停止。
pause

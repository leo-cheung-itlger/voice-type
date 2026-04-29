@echo off
chcp 65001 >nul
echo 正在停止所有 VoiceType 服务...

taskkill /fi "WINDOWTITLE eq VoiceType-Server*" /f >nul 2>&1
taskkill /fi "WINDOWTITLE eq VoiceType-Client*" /f >nul 2>&1
taskkill /fi "WINDOWTITLE eq VoiceType-API*" /f >nul 2>&1

echo 所有服务已停止。
pause

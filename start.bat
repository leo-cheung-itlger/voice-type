@echo off
chcp 65001 >nul
title VoiceType - 语音输入工具

echo ========================================
echo   VoiceType - 语音输入工具
echo ========================================
echo.

cd /d "%~dp0"

if not exist "venv" (
    echo [1/3] 首次运行，创建虚拟环境...
    python -m venv venv
    call venv\Scripts\activate.bat
    echo [2/3] 安装依赖...
    pip install -r requirements.txt -q
) else (
    call venv\Scripts\activate.bat
)

echo [3/3] 启动控制台...
echo.

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start-dev.ps1" -Root "%~dp0"

echo.
echo 控制台已启动！
echo   - API 后端: http://127.0.0.1:52342
echo   - Web 控制台: http://127.0.0.1:52343
echo.
echo 请在控制台中启动 ASR 服务端和客户端。
echo.
echo 此窗口可以关闭，后台服务会继续运行。

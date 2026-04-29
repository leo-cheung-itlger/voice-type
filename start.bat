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

echo [3/3] 启动服务...
echo.

start "VoiceType-Server" cmd /k "venv\Scripts\python.exe server\asr_server.py"
timeout /t 3 /nobreak >nul
start "VoiceType-Client" cmd /k "venv\Scripts\python.exe client\client_core.py"
start "VoiceType-API" cmd /k "venv\Scripts\python.exe api\api_server.py"

echo.
echo 所有服务已启动！
echo   - ASR 服务端: ws://0.0.0.0:52341
echo   - 客户端: 已启动（按 CapsLock 开始录音）
echo   - API 后端: http://127.0.0.1:52342
echo.
echo 按任意键退出此窗口（服务继续运行）...
pause >nul

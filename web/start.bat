@echo off
echo 正在启动豆包语音对话系统...
echo.
echo 请在浏览器中打开: http://localhost:8000
echo.

:: 检查是否在web目录下
if exist app.py (
    echo 正在启动Web服务器...
    python run.py
) else (
    echo 错误：请确保在web目录下运行此脚本
    pause
    exit /b 1
)

pause
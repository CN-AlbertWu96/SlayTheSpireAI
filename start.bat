@echo off
echo ========================================
echo Slay the Spire AI 启动脚本
echo ========================================
echo.

REM 清除无效的SSL环境变量
set SSL_CERT_FILE=
set SSL_CERT_DIR=

REM 激活conda环境并运行程序
call C:\Users\Administrator\miniconda3\Scripts\activate.bat slaythespire
cd /d c:\Users\Administrator\CodeBuddy\SlayTheSpireAI

echo [INFO] 正在启动AI程序...
echo [INFO] 请确保游戏已开启Communication Mod
echo [INFO] GUI界面即将启动...
echo.

python main.py

pause

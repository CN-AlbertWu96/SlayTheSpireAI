#!/bin/bash
echo "========================================"
echo "Slay the Spire AI 启动脚本"
echo "========================================"
echo ""

# 清除无效的SSL环境变量
unset SSL_CERT_FILE
unset SSL_CERT_DIR

# 使用conda环境的Python直接运行
cd c:/Users/Administrator/CodeBuddy/SlayTheSpireAI

echo "[INFO] 正在启动AI程序..."
echo "[INFO] 请确保游戏已开启Communication Mod"
echo "[INFO] GUI界面即将启动..."
echo ""

/c/Users/Administrator/miniconda3/envs/slaythespire/python.exe main.py

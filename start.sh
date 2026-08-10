#!/usr/bin/env bash
# MajsoulMax 启动脚本
# 用法: ./start.sh [端口]   默认端口 23410
set -euo pipefail
cd "$(dirname "$0")"

PORT="${1:-23410}"

if [ ! -x ".venv/bin/mitmdump" ]; then
    echo "✗ 未找到 .venv（依赖未安装），请先执行:"
    echo "  uv venv --python 3.12 .venv"
    echo "  uv pip install -r requirements.txt --python .venv/bin/python"
    exit 1
fi

if lsof -i :"$PORT" >/dev/null 2>&1; then
    echo "✗ 端口 $PORT 已被占用，MajsoulMax 可能已在运行:"
    lsof -i :"$PORT"
    exit 1
fi

echo "→ 启动 MajsoulMax，监听 127.0.0.1:${PORT}（Ctrl+C 停止）"
exec .venv/bin/mitmdump -p "$PORT" -s addons.py

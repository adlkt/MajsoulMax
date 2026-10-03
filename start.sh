#!/usr/bin/env bash
# 只启动本地改包服务；流量接管和路由由 Clash Verge 负责。
# 用法: ./start.sh [端口]，默认 23410；自定义端口需同步 clash-verge.js。
set -euo pipefail
cd "$(dirname "$0")"

PORT="${1:-23410}"
unset VIRTUAL_ENV

if ! [[ "$PORT" =~ ^[0-9]+$ ]] || [ "${#PORT}" -gt 5 ]; then
    echo "✗ 端口必须是 1–65535 的整数"
    exit 1
fi
PORT=$((10#$PORT))
if [ "$PORT" -lt 1 ] || [ "$PORT" -gt 65535 ]; then
    echo "✗ 端口必须是 1–65535 的整数"
    exit 1
fi

if ! command -v uv >/dev/null 2>&1; then
    echo "✗ 未找到 uv，请先安装 uv"
    exit 1
fi

if lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
    echo "✗ 端口 $PORT 已被占用，请关闭占用进程或指定其他端口："
    lsof -nP -iTCP:"$PORT" -sTCP:LISTEN
    exit 1
fi

echo "→ 同步依赖 (uv sync)"
uv sync --quiet

echo "→ 请在 Clash Verge 中启用 TUN 并加载 clash-verge.js"
echo "→ 启动改包服务，监听 127.0.0.1:${PORT}（Ctrl+C 停止）"
exec uv run python addons.py "$PORT"

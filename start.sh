#!/usr/bin/env bash
# MajsoulMax 启动脚本
# 启动 PAC HTTP 服务 → 设置系统代理（仅代理雀魂）→ 启动 mitmproxy
# 用法: ./start.sh [端口]   默认端口 23410
set -uo pipefail
cd "$(dirname "$0")"

PORT="${1:-23410}"
PAC_PORT=18080

# uv 环境冲突修复（终端可能已激活其他 venv）
unset VIRTUAL_ENV

# 检测当前活跃网络服务（回退 Wi-Fi）
net_service() {
    local iface svc cur line
    iface=$(route -n get default 2>/dev/null | awk '/interface:/{print $2}')
    [ -z "$iface" ] && { echo "Wi-Fi"; return; }
    while IFS= read -r line; do
        case "$line" in
            "("*")"*) cur="${line#*\) }" ;;
            *"Device: $iface"*) svc="${cur:-Wi-Fi}"; break ;;
        esac
    done < <(networksetup -listnetworkserviceorder 2>/dev/null)
    echo "${svc:-Wi-Fi}"
}

# 幂等标志：INT/TERM/EXIT trap 与末尾显式调用会多次触发 cleanup，只执行一次
CLEANED=0
cleanup() {
    [ "$CLEANED" -eq 1 ] && return 0
    CLEANED=1
    # 兜底：无论任何退出路径，确保 mitmproxy 进程被终止、端口被释放
    [ -n "${MPID:-}" ] && kill "$MPID" 2>/dev/null || true
    [ -n "${PACD_PID:-}" ] && kill "$PACD_PID" 2>/dev/null || true
    networksetup -setautoproxyurl "$(net_service)" off 2>/dev/null || true
    echo "→ 已清理 PAC 服务和系统代理设置"
}
trap cleanup INT TERM EXIT

if ! command -v uv >/dev/null 2>&1; then
    echo "✗ 未找到 uv，请先安装: curl -LsSf https://astral.sh/uv/install.sh | sh"
    exit 1
fi

# 启动 PAC HTTP 服务（Chrome 对 file:// PAC 支持不稳定）；已在运行则复用（幂等）
if ! lsof -nP -iTCP:"$PAC_PORT" -sTCP:LISTEN >/dev/null 2>&1; then
    python3 serve-pac.py "$PAC_PORT" &
    PACD_PID=$!
    sleep 0.5
else
    echo "→ PAC 服务已在运行，复用 http://127.0.0.1:${PAC_PORT}/majsoul.pac"
fi

# 设置系统 PAC 为 HTTP 地址：只把雀魂流量导向本地代理，其余直连
NET_SERVICE="$(net_service)"
PAC_URL="http://127.0.0.1:${PAC_PORT}/majsoul.pac"
echo "→ 设置系统代理 PAC（仅代理雀魂）: ${PAC_URL} @ $NET_SERVICE"
if ! networksetup -setautoproxyurl "$NET_SERVICE" "$PAC_URL" 2>/dev/null; then
    echo "⚠ 自动设置系统代理失败（macOS 需要管理员权限）"
    echo "  手动设置一次即可（长期有效）:"
    echo "    系统设置 → 网络 → $NET_SERVICE → 详细信息 → 代理"
    echo "    勾选「自动代理配置」，URL 填: ${PAC_URL}"
fi

echo "→ 同步依赖 (uv sync)"
uv sync --quiet || { echo "✗ 依赖同步失败"; exit 1; }

if lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
    # 端口被占：优先按 PID 文件识别上次残留的 MajsoulMax，其次按命令行匹配 addons.py
    LISTEN_PID=$(lsof -nP -iTCP:"$PORT" -sTCP:LISTEN -t 2>/dev/null | head -1)
    OLD_PID=""
    [ -f /tmp/majsoul-max.pid ] && OLD_PID=$(cat /tmp/majsoul-max.pid 2>/dev/null || true)
    if [ -n "$OLD_PID" ] && kill -0 "$OLD_PID" 2>/dev/null; then
        echo "⚠ 检测到上次未退出的 MajsoulMax（PID ${OLD_PID}），自动清理..."
        kill "$OLD_PID" 2>/dev/null || true
    elif [ -n "$LISTEN_PID" ] && ps -p "$LISTEN_PID" -o command= 2>/dev/null | grep -q "addons.py"; then
        echo "⚠ 检测到残留 MajsoulMax 进程（PID ${LISTEN_PID}），自动清理..."
        kill "$LISTEN_PID" 2>/dev/null || true
    else
        echo "✗ 端口 $PORT 已被其他进程占用:"
        lsof -i :"$PORT"
        exit 1
    fi
    # 等待端口释放（最多 3 秒）
    for _ in 1 2 3 4 5 6; do
        lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1 || break
        sleep 0.5
    done
    if lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
        echo "✗ 端口 $PORT 仍被占用，自动清理失败，请手动检查:"
        lsof -i :"$PORT"
        exit 1
    fi
    echo "✓ 已清理残留进程，端口 $PORT 已释放"
fi

echo "→ 启动 MajsoulMax，监听 127.0.0.1:${PORT}（Ctrl+C 停止）"
uv run python addons.py "$PORT" &
MPID=$!
wait "$MPID"
cleanup

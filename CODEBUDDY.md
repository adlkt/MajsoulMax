# CODEBUDDY.md

雀魂 MAX —— 基于 mitmproxy 中间人攻击的雀魂辅助工具，解锁全角色/皮肤/装扮。

## 项目架构

```
MajsoulMax/
├── addons.py          # 🔑 mitmproxy 插件入口，WS/HTTP 消息分发
├── liqi_new.py        # liqi 协议解析（WS protobuf → JSON）
├── start.sh           # 启动脚本（kill 残留进程 + mitmdump）
├── config/
│   ├── settings.yaml      # 主配置（插件开关 + liqi 版本）
│   ├── settings.mod.yaml  # mod 配置（角色/皮肤/装扮）
│   ├── settings.helper.yaml
│   └── settings.replace.yaml
├── plugin/
│   ├── mod.py             # 解锁角色/皮肤/装扮/语音/称号/CG
│   ├── helper.py          # 牌局发送至雀魂小助手
│   ├── replace.py         # 替换游戏资源文件
│   └── update_liqi.py     # 从 GitHub Releases 更新 liqi 协议
├── proto/                 # liqi protobuf 定义及生成文件
├── .env                   # GITHUB_TOKEN（不提交 Git）
└── replace/               # replace 插件替换文件
```

## 消息流

```
游戏客户端 → mitmproxy(23410) → addons.py
  ├─ websocket_message → mod.main() → 修改/注入/丢弃 WS 消息
  ├─ websocket_message → liqi_proto.parse() → 维护 res_type 映射（mod 依赖）
  └─ request → replace.main() → 本地文件替换 HTTP 响应
```

## 启动方式

**用户实际运行**（推荐）：

```bash
bash start.sh
# 等价于 kill -9 23410 残留进程 → .venv/bin/mitmdump -p 23410 -s addons.py
```

此路径下 `addons.py` 模块级的 `addons = [MajsoulMaxAddon()]` 被 mitmdump 自动发现，`__main__` / `start_mitm()` 不会执行。

**备选运行**（`python addons.py`）：走 DumpMaster 路径，显式注册 addon。两条路径互斥。

## Python 环境

- venv：`.venv/`（Python 3.13.12）
- 依赖：mitmproxy>=10, protobuf==3.20.1, requests, ruamel.yaml, loguru, rich
- 安装：`.venv/bin/pip install -r requirements.txt`

## 关键约束

1. **`liqi_proto.parse()` 必须无条件调用** — 它维护 `res_type` 字典，mod 依赖它做 Res 消息拦截。不能为"轻量化"跳过。
2. **启动前必须 kill 端口 23410** — `start.sh` 已自动处理。
3. **GITHUB_TOKEN 存 `.env`，不在 settings.yaml 中** — addons.py 启动时自动从 `.env` 加载，写回 settings.yaml 前会清理 token 字段。
4. **liqi 协议版本 ≠ 游戏客户端版本** — 两套独立系统。`update_liqi.py` 只从 GitHub Releases 获取新版本，不根据游戏内版本号更新。

## 修改原则

- README.md 不动，新建独立文件
- 改动最小化，不动不需要改的部分
- 先读 git diff 再改，确保理解原始行为
- **Edit 之前必须先 Read** — 工作台硬性要求

## mod 插件核心机制

- 通过 mitmproxy 拦截 WebSocket 消息，修改 `Res` 类型消息中的角色/皮肤/装扮数据
- 依赖 `liqi_proto.parse()` 维护的 `res_type` 表来识别消息类型和匹配请求-响应
- 配置文件 `settings.mod.yaml` 在首次启用后自动生成
- 解锁仅本地有效，其他玩家看不到

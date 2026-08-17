# 雀魂 MAX

> 基于 mitmproxy 的雀魂流量拦截工具：解锁全部角色 / 皮肤 / 装扮，可选对局转发雀魂小助手。

- 🃏 **解锁**：全部角色、皮肤、装扮、称号，自定义看板娘、对局随机角色皮肤、装扮页
- 📡 **小助手**：对局数据实时转发给雀魂小助手（mahjong-helper），辅助读牌
- 🔧 **替换**：HTTP / 协议层资源替换，支持自定义游戏内容
- 🔄 **自动更新**：liqi 协议文件跟随上游自动更新，游戏版本变更无需手动处理

---

## 环境要求

| 项目 | 要求 |
|---|---|
| 系统 | macOS（推荐，一键脚本）或 Windows |
| Python | 3.12+ |
| 包管理 | [uv](https://docs.astral.sh/uv/)（`curl -LsSf https://astral.sh/uv/install.sh \| sh`） |
| 游戏 | 雀魂客户端（日服 / 国际服均可） |
| 额外 | Windows 必需 Clash Verge；macOS 可选（挂机场或规则导流） |

> 流量只拦截雀魂相关域名，其余流量全部直连，不影响正常上网。

---

## 快速开始

### macOS：一键启动（推荐）

```bash
git clone <仓库地址>
cd MajsoulMax
./start.sh
```

脚本自动完成：起 PAC 服务 → 设置系统代理（仅雀魂走代理）→ 启动 mitmproxy。退出时自动清理代理设置，不留残留。默认监听 `127.0.0.1:23410`，自定义端口：`./start.sh 端口号`。

如需挂机场：保持 Clash Verge 运行即可，脚本会自动探测并使用它的混合端口作为上游（`proxy.upstream: auto`）。

### Windows / macOS（Clash Verge 方式）

1. 安装并启动 [Clash Verge](https://github.com/clash-verge-rev/clash-verge-rev)
2. 设置 → 开启「扩展脚本」（Extend Script），将项目里的 `clash-verge.js` 内容填入（或复制到配置目录同名文件）
3. 重启 Clash Verge 使脚本生效
4. 启动 mitmproxy（不设置系统代理）：

   ```bash
   uv sync
   uv run python addons.py
   ```

5. 确认 Clash Verge 的「🀄 雀魂麻将」分组已选中 `MajsoulMax`（而不是机场 / DIRECT）

### 验证

进游戏查看主页与对局：全部角色、皮肤、装扮可用即成功。终端日志会显示 `已载入mod` 及解析到的 liqi 消息。

---

## 配置说明

配置文件：`config/settings.yaml`

```yaml
plugin_enable:
  mod: true      # 解锁全部角色、皮肤、装扮等（默认开）
  helper: false  # 转发对局到雀魂小助手，不使用请勿开启
  replace: false # 替换雀魂的游戏内容

liqi:
  auto_update: true  # 自动更新 liqi 协议文件
  github_token: ''   # 仅自己使用，请勿泄漏给任何人

proxy:
  upstream: auto     # 上游代理
```

`proxy.upstream` 三种取值：

| 值 | 行为 |
|---|---|
| `auto` | 自动检测本机 Clash Verge（有则走其混合端口，没有则直连） |
| `http://ip:端口` | 显式指定上游代理 |
| 留空 / `direct` | 直连 |

mod 的看板娘、随机皮肤、装扮页等大部分配置在**游戏内修改**，改动自动保存到 `settings.yaml`，无需手动编辑。

---

## 流量架构

```
浏览器/游戏 → PAC（macOS）或 Clash Verge 规则（Windows）
            → mitmproxy 127.0.0.1:23410
            →（可选）机场/上游代理
            → 雀魂服务器
其他域名 → 直连（不经过代理）
```

- **macOS**：`majsoul.pac` 只把雀魂域名指向本地代理，其余 `DIRECT`；由 `start.sh` 通过系统代理设置生效
- **Windows**：`clash-verge.js` 将 `MajsoulMax` 注册为本地节点，按进程（`Jantama_MahjongSoul.exe` / `雀魂麻將.exe`）与域名（`majsoul` / `maj-soul` / `mahjongsoul` / `catmjstudio`）匹配转发
- **不会死循环**：mitmproxy 自身（python 进程）访问雀魂服务器时，Clash Verge 的 bypass 规则会将其导向机场/直连，而非回环到 `MajsoulMax` 节点

---

## 常见问题

**macOS 系统代理设置失败？**
`start.sh` 设置代理需要管理员权限，失败时按提示手动设置一次即可（长期有效）：系统设置 → 网络 → 当前网络 → 详细信息 → 代理 → 勾选「自动代理配置」，URL 填 `http://127.0.0.1:18080/majsoul.pac`。

**端口 23410 被占用？**
`start.sh` 会自动识别并清理上次残留的 MajsoulMax 进程；若被其他程序占用会列出占用进程，手动处理即可。

**解锁没生效？**
先看终端日志是否出现 `已载入mod` 和 liqi 消息解析；确认系统代理（或 Clash Verge 分组）已生效，然后重启游戏再试。

**Windows 上解锁没生效？**
依次检查：① 扩展脚本是否加载成功；② 「🀄 雀魂麻将」分组是否选中 `MajsoulMax`。注意：mitmproxy 未启动时，故障转移分组会在约 30 秒后静默切到机场/直连，表现为"像没解锁"。

**liqi 更新失败？**
多为网络问题，检查能否访问 GitHub；或在 `settings.yaml` 配置 `github_token` 提高限流上限。

---

## 免责声明

本项目仅供学习研究 mitmproxy / protobuf 协议解析使用。解锁角色、皮肤等功能涉及修改游戏数据，**存在账号封禁风险**，请勿用于作弊、牟利或商业用途，使用后果自负。请尊重游戏开发商权益，支持正版。

---

## 致谢
- 项目参考: [AvenshyMajsoulMax](https://github.com/Avenshy/MajsoulMax)
- liqi 协议数据：[Avenshy/MajsoulData](https://github.com/Avenshy/MajsoulData)

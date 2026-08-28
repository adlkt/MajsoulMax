# AGENTS.md — MajsoulMax 项目协作约定

雀魂 MAX：基于 mitmproxy 的流量拦截工具（解锁角色/皮肤/装扮 + 牌局转发 mahjong-helper）。
参考实现：https://github.com/adlkt/majsoul-mod-2（本方案对齐其代理设计）

## 运行

```bash
./start.sh              # 一键：起 PAC 服务 → 设置系统代理（仅雀魂走代理）→ 启动 mitmproxy
./start.sh 23411        # 指定端口，默认 23410
uv run python addons.py # 仅启动 mitmproxy（不设置系统代理）
uv run pytest           # 全量测试（88 项，等价于 .venv/bin/python -m pytest）
```

依赖用 `uv` 管理，`.venv` 在项目根。**不要用 brew python 或其他 venv 跑** ——
mitmproxy/protobuf 只在项目 `.venv` 里。

**流量路径**：浏览器/游戏 → PAC（仅雀魂域名）→ mitmproxy(127.0.0.1:23410) →
（可选 upstream 机场）→ 目标；其他域名 DIRECT 不经过代理。
mitmproxy 本身就是代理（regular 模式），无需 pf/Clash/TUN。

```
雀魂客户端 → 系统 PAC (majsoul.pac) → mitmproxy:23410 → [上游 Clash Verge] → 雀魂服务器
                                            ↓
                          addons.py  ← liqi_new.py 解析 → proto/liqi.json 查表
                                ↓
                    plugin/mod.py    改包（角色/皮肤/装扮）
                    plugin/helper.py 转发对局
                    plugin/replace.py 替换 HTTP 资源
```

## 架构

| 路径 | 职责 |
|---|---|
| `addons.py` | mitmproxy addon 入口。WebSocket → liqi_new 解析 → mod/helper；HTTP → replace。`_hosts` 过滤非雀魂流量。启动参数：listen 127.0.0.1 + block_global=false + flow_detail=0 + termlog_verbosity=warn |
| `liqi_new.py` | protobuf 帧解析（Notify/Req/Res 三类），维护 `res_type` 表 |
| `plugin/mod.py` | 核心改包逻辑，按 method 字典分发到 handler |
| `plugin/helper.py` | 转发对局到雀魂小助手（默认关闭） |
| `plugin/replace.py` | HTTP 资源本地替换（默认关闭） |
| `plugin/update.py` | 启动时检查 liqi.desc / max_data.yaml 更新 |
| `start.sh` | 启动脚本 + 退出清理（系统代理 / PID / 端口） |
| `serve-pac.py` | HTTP 提供 `majsoul.pac`（Chrome 不支持 file:// PAC） |
| `tests/` | pytest，无网络 I/O |

`config/` 与 `proto/` 下的**实际内容均被 gitignore**，仓库里只有 `.gitkeep` 占位，
首次运行自动生成。

`proto/` 说明：

- `liqi_pb2.py` **动态从 `liqi.desc` 构建**，已做 protobuf 全版本兼容（3.x
  `GetPrototype` / 4-6.x `GetMessageClass` / 7.x+ 模块级函数，三态回退）
- `update.py` 只下载 `liqi.desc` + `max_data.yaml`，**不会覆盖 `liqi_pb2.py`**
- `basic_pb2.py` 是静态生成代码，**不要手改**
- `liqi.json` 由 `liqi.desc` 生成（`update.py:_generate_liqi_json`），是
  method_name → {req, resp} 类型映射表，缺它整个解析链路起不来

## 硬约定

- **路径必须用 `BASE_DIR = Path(__file__).resolve().parent(.parent)` 定位，禁止
  相对路径**（依赖 CWD 会炸）。⚠️ `proto/liqi_pb2.py:11` 目前仍是
  `open("./proto/liqi.desc")`，属于历史遗留，修它时一并改成 BASE_DIR
- 依赖变更改 `pyproject.toml`，不要建 requirements.txt；版本只设下限不设上限
  （mitmproxy>=12.2.3 / protobuf>=7.35.1，Python >=3.12），破坏性大版本更新时再适配
- 上游代理逻辑集中在 `resolve_upstream()`，**不要绕开它直接改 mode**
- **SaveSettings 纪律**：只有**改配置**（`self.settings`）的 handler 才
  SaveSettings；只改 message 内容的高频路径（Notify 类）**禁止触发写盘**
  （2026-08-11 性能优化后约定，防回归）
- `serve-pac.py` **只 serve `majsoul.pac` 单文件**，禁止改回
  `SimpleHTTPRequestHandler` 整目录暴露（会泄漏 settings.yaml 里的 token）
- `start.sh` 改动注意：保留 `unset VIRTUAL_ENV`（避免 venv 激活冲突）；
  networksetup 失败要容忍（`|| true` 或给提示）

## mod.py 的 handler 分发

三类消息各有一张分发表（`_NOTIFY_HANDLERS` / `_REQ_HANDLERS` / `_RES_HANDLERS`），
`main()` 只做帧解析 + 收尾序列化。加新功能时**加 handler + 注册表项**，不要在
`main()` 里塞 if/elif。

返回值签名（各表不同，别搞混）：

```python
# Notify / Res
return modify, drop, data
# Req
return modify, drop, fake, inject, inject_msg, data
```

`fake=True` 表示这个请求不发给服务器，改造成 `ReqLoginBeat` 保活包顶替。

### ⚠ 顺序耦合：mod 依赖 liqi_proto 的 res_type

`mod.main()` 的 Res 分支靠 `liqi_proto.res_type[msg_id]` 反查 method_name，而
`addons.py` 里是 **先 `mod_plugin.main()` 后 `liqi_proto.parse()`**，parse 才会
`pop(msg_id)`。调换顺序会让所有 Res handler 静默失效。

### 配置加载

三个插件各读各的 yaml（`settings.mod.yaml` / `settings.helper.yaml` /
`settings.replace.yaml`），主配置是 `settings.yaml`。默认配置以字符串形式内嵌在
源码里，本地文件只做**覆盖**，缺失键走默认值。

改默认配置要同时改源码里的内嵌模板 —— 本地 yaml 一旦生成就不会再自动补新键。

### 异常边界

addon 事件回调里任何异常都会打断整条消息流。已加 try/except 的地方（mod 处理、
helper 转发、解析失败）**不要移除**。新 handler 同理：宁可 `logger.warning` 跳过
一帧，也不要让 mitmproxy 崩。

### 日志脱敏

`addons.py:_SENSITIVE_METHODS` 里的 method（oauth2Login / login / loginBeat）在
客户端方向只打 method + 长度，不打印内容 —— 这些请求带账号凭证。新增凭证类
method 记得加进去。

## 测试约定

- **禁止网络 I/O、禁止写真实配置文件**。已有 autouse fixture 把 `SaveSettings`
  置空、`ctx.master` 换成 fake
- 构造 `mod` 实例用 `mod.__new__(mod)` 绕过 `__init__`（它会读写 yaml），
  再手动注入 `m.safe` / `m.settings`
- flow / message 用 `types.SimpleNamespace` mock，不用真的 mitmproxy 对象
- 解析层改动补 `tests/test_liqi_new.py`；mod 纯函数改动补 `tests/test_mod_utils.py`；
  改分发链路补 `tests/test_mod_dispatch.py`

## Git 约定

- 工作分支 `dev`，`main` 只收合并
- 提交格式：`YYYY-MM-DD-HH:MM 类型：描述`
  ```
  2026-08-28-21:00 文档：补全 AGENTS.md 协作约定
  ```
  类型：功能 / 修复 / 重构 / 加固 / 清理 / 工程化 / 文档
- **原子提交**：一个 commit 只含一个逻辑变更。文档改动和代码改动分开提
- 提交前按五轴自审（正确性 / 安全性 / 性能 / 一致性 / 可维护性）
- `config/settings.yaml` 含 GitHub token，**绝不可提交**。目前已被 gitignore

## 改代码前注意

- `networksetup -setautoproxyurl <svc> <url>` 是设 PAC 地址，关代理要用
  `-setautoproxystate <svc> off`。参数不同，混用会把 `off` 写成 URL
- `liqi_new.to_dict()` 靠 try/except TypeError 兼容 protobuf 4.x/5.x 的参数差异，
  不要在里面加会抛 TypeError 的代码
- `addons.py` 里 mod 处理被 `if not message.injected` 包着，`modify` 变量只在
  该分支内定义。动这块时注意 `UnboundLocalError`
- 版本号两处：`addons.py:VERSION`（带 `v` 前缀，与 GitHub tag 比较）和
  `pyproject.toml:version`（不带前缀）。改版本时两个一起改
- 历史坑与决策记录见 `.workbuddy/memory/`（按日期，`MEMORY.md` 是长期沉淀）

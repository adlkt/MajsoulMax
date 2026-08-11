# AGENTS.md — MajsoulMax 项目协作约定

雀魂 MAX：基于 mitmproxy 的流量拦截工具（解锁角色/皮肤/装扮 + 牌局转发 mahjong-helper）。

## 运行

```bash
./start.sh         # 一键：起 PAC 服务 → 设置系统代理（仅雀魂走代理）→ 启动 mitmproxy
uv run python addons.py   # 仅启动 mitmproxy（不设置系统代理）
```

- 流量路径：浏览器/游戏 → PAC（仅雀魂域名）→ mitmproxy(127.0.0.1:23410) →（可选 upstream 机场）→ 目标；其他域名 DIRECT 不经过代理。
- mitmproxy 本身就是代理（regular 模式），无需 pf/Clash/TUN。
- 参考实现：https://github.com/adlkt/majsoul-mod-2（本方案对齐其代理设计）。

## 架构

- `addons.py`：mitmproxy addon 入口（WebSocket → liqi_new 解析 → mod/helper 插件；HTTP → replace 插件）。`MajsoulMaxAddon._hosts` 过滤非雀魂域名流量。启动参数：listen 127.0.0.1 + block_global=false + flow_detail=0 + termlog_verbosity=warn；`settings.yaml` 的 `proxy.upstream` 决定 mode：`auto`=读系统代理 / 显式地址=`upstream:` 模式 / 空或 `direct`=直连
- `serve-pac.py`：HTTP 提供 `majsoul.pac`（Chrome 不支持 file:// PAC）
- `majsoul.pac`：PAC 规则（雀魂域名 → `PROXY 127.0.0.1:23410`，其他 DIRECT）
- `liqi_new.py`：雀魂 protobuf 消息解析
- `plugin/`：mod（解锁）/ helper（转发小助手）/ replace（资源替换）/ update（liqi 更新）
- `proto/`：liqi_pb2.py 动态从 liqi.desc 构建，已做 protobuf 全版本兼容（3.x/4-6.x/7+ 三态 API 回退）；update 只下载 liqi.desc/max_data.yaml，**不会覆盖 liqi_pb2.py**，手动替换 AutoLiqi 文件时需保持兼容写法；basic_pb2.py 为静态生成代码不改

## 约定

- **路径必须用 `BASE_DIR = Path(__file__).resolve().parent(.parent)` 定位，禁止相对路径**（依赖 CWD 会炸）
- 依赖变更改 `pyproject.toml`，不要重建 requirements.txt；版本策略：只设下限不设上限（mitmproxy>=12.2.3 / protobuf>=7.35.1，Python >=3.12，2026-08-10 随上游升到最新），破坏性大版本更新时再适配
- 上游代理逻辑集中在 `resolve_upstream()`，不要绕开它直接改 mode
- start.sh 改动注意：`unset VIRTUAL_ENV`（避免 venv 激活冲突）、networksetup 失败要容忍（`|| true` 或提示）
- **SaveSettings 纪律**：只有**改配置**（self.settings）的 handler 才 SaveSettings；只改 message 内容的高频路径（Notify 类）禁止触发写盘（2026-08-11 性能优化后约定，防回归）
- **serve-pac.py 只 serve majsoul.pac 单文件**，禁止改回 SimpleHTTPRequestHandler 整目录暴露（会泄漏 settings.yaml token）

## 技能包（.workbuddy/skills/）

项目已装 addyosmani/agent-skills 全量 24 技能（MIT），指导 agent 按资深工程师工作流干活，详见 `.workbuddy/README.md`。

- **开工前**：先读 `.workbuddy/skills/using-agent-skills/SKILL.md` 把任务映射到正确技能；本文件是 context-engineering 的核心输入
- **测试**：`uv run pytest` 跑全量（tests/，27 用例：liqi_new 解析层 + mod 纯函数）；测试命令是 `uv run pytest`（pyproject.toml 已配 testpaths/addopts）
- **改逻辑/修 bug 前**：读 `test-driven-development`；解析层改动必须补 `tests/test_liqi_new.py`（to_dict 兼容 + parse Req/Res/Notify 闭环是好样例），mod 纯函数改动补 `tests/test_mod_utils.py`（用 `mod.__new__` 绕过 __init__ 避免写配置文件）
- **改 addons.py 核心链路/代理逻辑前**：读 `doubt-driven-development` + `source-driven-development`（mitmproxy/protobuf API 变动大，先查官方文档再动手）
- **提交前**：读 `git-workflow-and-versioning`（原子提交 + 变更规模）+ `code-review-and-quality`（五轴自审）
- **排障时**：按 `debugging-and-error-recovery` 五步法（复现→定位→缩小→修复→防护），本项目历史坑见 `.workbuddy/memory/`
- 更新技能包：见 `.workbuddy/README.md` 的更新方式（clone 后 cp，注意 references 引用路径）

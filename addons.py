import liqi_new
import asyncio
import os
from mitmproxy.tools.dump import DumpMaster
from mitmproxy.options import Options
from loguru import logger
from mitmproxy import http, ctx
from plugin import helper, mod, replace
from ruamel.yaml import YAML
from sys import stdout
from plugin import update_liqi
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.traceback import install as install_rich_traceback

install_rich_traceback(show_locals=False, width=100)
console = Console()

VERSION = "20260212"
# —— Banner ——
console.print(Panel.fit(
    f"[bold cyan]🀄 雀魂 MAX[/bold cyan]  [dim]v{VERSION}[/dim]\n\n"
    "[dim]完全免费 · 开源 · 仅供学习交流[/dim]",
    border_style="cyan",
    padding=(1, 3),
))

# —— Logger ——
logger.remove()
logger.add(
    stdout,
    colorize=True,
    format="<dim>[{time:HH:mm:ss.SSS}]</dim> <level>{message}</level>",
)
# 导入配置
yaml = YAML()
SETTINGS = yaml.load("""\
# 插件配置，true为开启，false为关闭
plugin_enable:
  mod: true  # mod用于解锁全部角色、皮肤、装扮等
  helper: false  # helper用于将对局发送至雀魂小助手，不使用小助手请勿开启
  replace: false  # replace用于替换雀魂的游戏内容
# liqi用于解析雀魂消息
liqi:
  auto_update: true  # 是否自动更新
  liqi_version: 'v0.11.219.w'  # 本地liqi文件版本
  liqi_hash: 'e6a718c1e50b41471453b16c75b2992cbb05c2c84297b6d55edd1499a089530e'  # 本地liqi文件hash
""")
# 从 .env 文件加载环境变量（不上传 GitHub，安全存储敏感信息）
try:
    with open("./.env", "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                os.environ[key.strip()] = value.strip().strip("'").strip('"')
    logger.info("已从 .env 加载环境变量")
except FileNotFoundError:
    logger.warning("未找到 .env 文件，liqi 自动更新可能无法使用")

try:
    with open("./config/settings.yaml", "r", encoding="utf-8") as f:
        SETTINGS.update(yaml.load(f))
except Exception as e:
    logger.warning(
        f"无法读取 settings.yaml ({e})，使用默认配置：mod 启用，helper 禁用"
    )


MOD_ENABLE = SETTINGS["plugin_enable"]["mod"]
HELPER_ENABLE = SETTINGS["plugin_enable"]["helper"]
REPLACE_ENABLE = SETTINGS["plugin_enable"]["replace"]
if SETTINGS["liqi"]["auto_update"]:
    if "liqi_hash" not in SETTINGS["liqi"]:
        SETTINGS["liqi"]["liqi_hash"] = ""
    logger.info("正在检测liqi文件更新，请稍候……")
    try:
        github_token = os.environ.get("GITHUB_TOKEN", "")
        result = update_liqi.update(
            SETTINGS["liqi"]["liqi_version"],
            github_token,
            SETTINGS["liqi"]["liqi_hash"],
        )
        SETTINGS["liqi"]["liqi_version"] = result["version"]
        SETTINGS["liqi"]["liqi_hash"] = result["hash"]
    except Exception as e:
        logger.critical(f"liqi文件更新失败 ({e})，部分消息可能无法解析")
# 写回前清理敏感字段，确保 token 不会泄露到 yaml 文件中
SETTINGS["liqi"].pop("github_token", None)
with open("./config/settings.yaml", "w", encoding="utf-8") as f:
    yaml.dump(SETTINGS, f)
# —— 启动状态 ——
status_table = Table(title="启动状态", border_style="dim blue", show_header=False)
status_table.add_column("项", style="dim")
status_table.add_column("值")

def _status(label: str, enabled: bool) -> str:
    return "[green]● 启用[/green]" if enabled else "[dim]○ 关闭[/dim]"

status_table.add_row("Mod 插件", _status("mod", MOD_ENABLE))
status_table.add_row("Helper 插件", _status("helper", HELPER_ENABLE))
status_table.add_row("Replace 插件", _status("replace", REPLACE_ENABLE))
console.print(status_table)
console.print()

if MOD_ENABLE:
    mod_plugin = mod.mod(VERSION)
if HELPER_ENABLE:
    helper_plugin = helper.helper()
if REPLACE_ENABLE:
    replace_plugin = replace.replace()
liqi_proto = liqi_new.LiqiProto()
if not (MOD_ENABLE or HELPER_ENABLE or REPLACE_ENABLE):
    logger.warning("当前没有启用任何功能，请修改 ./config/settings.yaml 后重新启动")


class MajsoulMaxAddon:
    def websocket_message(self, flow: http.HTTPFlow):
        # 在捕获到WebSocket消息时触发
        assert flow.websocket is not None  # make type checker happy
        message = flow.websocket.messages[-1]
        # 不解析ob消息
        if flow.request.path == "/ob":
            if message.from_client is False:
                logger.debug(f"⬇ ob ({len(message.content)}B)")
            else:
                logger.debug(f"⬆ ob ({len(message.content)}B)")
            return
        # 解析proto消息
        if MOD_ENABLE:
            # 如果启用mod，就把WS消息丢进mod里
            if not message.injected:  # 不解析MAX自己插入的WS消息
                modify, drop, msg, inject, inject_msg = mod_plugin.main(
                    message, liqi_proto
                )
                if drop:
                    message.drop()
                if inject:
                    ctx.master.commands.call(
                        "inject.websocket", flow, True, inject_msg, False
                    )
                if modify:
                    # 如果被mod修改就同步变更
                    message.content = msg
        try:
            result = liqi_proto.parse(message)  # 解析消息，维护 res_type 映射（mod 依赖）
        except Exception as e:
            direction = "⬇" if not message.from_client else "⬆"
            logger.error(f"{direction} 解析失败 ({len(message.content)}B): {e}")
        else:
            if HELPER_ENABLE:
                if message.from_client is False:
                    helper_plugin.main(result)

    def request(self, flow: http.HTTPFlow):
        # 在捕获到HTTP消息时触发
        if REPLACE_ENABLE:
            # 如果启用replace，就把HTTP消息丢进replace里
            path = replace_plugin.main(flow.request)
            if path != "":
                with open(f"./replace{path}", "rb") as f:
                    if (body := f.read()) != b"":
                        flow.response = http.Response.make(
                            200, body
                        )  # ,  {"Content-Type": "image/png"})
                        logger.success(f"✓ 已替换 {flow.request.path}")
                    else:
                        logger.error(f"✗ 替换失败 {flow.request.path}")


addons = [MajsoulMaxAddon()]


async def start_mitm():
    console.print("[dim]⏳ mitmproxy 启动中...[/dim]")
    opts = Options(listen_host="0.0.0.0", listen_port=23410, ssl_insecure=True)
    master = DumpMaster(opts)
    master.addons.add(MajsoulMaxAddon())
    try:
        logger.info("代理已启动 → 0.0.0.0:23410")
        await master.run()
    except KeyboardInterrupt:
        master.shutdown()


if __name__ == "__main__":
    asyncio.run(start_mitm())

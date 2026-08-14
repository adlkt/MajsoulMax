import liqi_new
import asyncio
import os
import signal
import socket
import sys
from pathlib import Path
from mitmproxy.tools.dump import DumpMaster
from mitmproxy.options import Options
from loguru import logger
from mitmproxy import http, ctx
from plugin import helper, mod, replace
from ruamel.yaml import YAML
from sys import stdout
from plugin import update

BASE_DIR = Path(__file__).resolve().parent

VERSION = "v2026.07.07"


logger.remove()
logger.add(
    stdout,
    colorize=True,
    format="<cyan>[{time:HH:mm:ss.SSS}]</cyan> <level>{message}</level>",
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
  github_token: '' # 仅供自己使用，请勿泄漏给任何人
  liqi_version: '0.16.243-4.0.45'  # 本地liqi文件版本
# 上游代理（可选）：auto=自动检测本机 Clash Verge（有则走它的混合端口，没有则直连）
#                 / 填 http://ip:端口（显式指定）/ 留空或direct=直连
proxy:
  upstream: auto
""")
try:
    with open(BASE_DIR / "config" / "settings.yaml", "r", encoding="utf-8") as f:
        SETTINGS.update(yaml.load(f))
except (FileNotFoundError, KeyError):
    logger.warning(
        """首次运行，默认启用mod，禁用helper\n
        如需使用，请修改 ./config/settings.yaml 文件\n
        修改完成后重新启动即可\n
        """
    )


MOD_ENABLE = SETTINGS["plugin_enable"]["mod"]
HELPER_ENABLE = SETTINGS["plugin_enable"]["helper"]
REPLACE_ENABLE = SETTINGS['plugin_enable']["replace"]
if SETTINGS["liqi"]["auto_update"]:
    logger.info("正在检测更新，请稍候……")
    try:
        result = update.update(
            max_version = VERSION,
            liqi_version = SETTINGS["liqi"]["liqi_version"],
            token = SETTINGS["liqi"]["github_token"]
        )
        # 仅在版本实际变化时才写回，避免每次启动覆盖用户对配置文件的注释
        if result != SETTINGS["liqi"]["liqi_version"]:
            SETTINGS["liqi"]["liqi_version"] = result
            with open(BASE_DIR / "config" / "settings.yaml", "w", encoding="utf-8") as f:
                yaml.dump(SETTINGS, f)
    except Exception as e:
        logger.critical(f"更新失败！可能会导致部分消息无法解析！错误：{e}")
logger.success(
    f"""已载入配置：\n
    启用mod: {MOD_ENABLE}\n
    启用helper：{HELPER_ENABLE}\n
    启用replace：{REPLACE_ENABLE}\n
    """
)
if MOD_ENABLE:
    mod_plugin = mod.mod(VERSION)
if HELPER_ENABLE:
    helper_plugin = helper.helper()
if REPLACE_ENABLE:
    replace_plugin = replace.replace()
liqi_proto = liqi_new.LiqiProto()
if not (MOD_ENABLE or HELPER_ENABLE or REPLACE_ENABLE):
    logger.warning(
        "请注意，当前没有开启任何功能，请修改./config/settings.yaml文件并重新启动！"
    )


class MajsoulMaxAddon:
    # 只处理雀魂域名流量（双保险：即使其他流量进了代理也不处理）
    _hosts = ("maj-soul.com", "mahjongsoul.com", "majsoul", "catmjstudio", "yo-star.com")

    def websocket_message(self, flow: http.HTTPFlow):
        # 在捕获到WebSocket消息时触发
        assert flow.websocket is not None  # make type checker happy
        if not any(k in flow.request.host for k in self._hosts):
            return
        message = flow.websocket.messages[-1]
        # 不解析ob消息
        if flow.request.path == "/ob":
            if message.from_client is False:
                logger.debug(f"接收到（未解析）：{message.content}")
            else:
                logger.debug(f"已发送（未解析）：{message.content}")
            return
        # 解析proto消息
        if MOD_ENABLE:
            # 如果启用mod，就把WS消息丢进mod里
            if not message.injected: # 不解析MAX自己插入的WS消息
                try:
                    modify, drop, msg, inject, inject_msg = mod_plugin.main(
                        message, liqi_proto
                    )
                except Exception as e:
                    # 畸形/异常消息不能中断 addon，跳过 mod 处理继续走 parse
                    logger.warning(f"mod 处理异常，跳过: {e}")
                    modify = drop = inject = False
                    msg = inject_msg = b""
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
            result = liqi_proto.parse(message) # 解析消息
        except Exception as e:
            # 只记录消息长度与方向，不打印原始字节（WS 流量可能含账号 token，防泄漏）
            direction = "接收到" if message.from_client is False else "已发送"
            logger.error(f"{direction}(error) len={len(message.content)}B: {e}")
        else:
            if message.from_client is False:
                if message.injected:
                    logger.success(f"接收到(injected)：{result}")
                elif MOD_ENABLE and modify:
                    logger.success(f"接收到(modify)：{result}")
                elif MOD_ENABLE and drop:
                    logger.success(f"接收到(drop)：{result}")
                else:
                    logger.info(f"接收到：{result}")
                if HELPER_ENABLE:
                    # 如果启用helper，就把消息丢进helper里
                    helper_plugin.main(result)
            else:
                if MOD_ENABLE and modify:
                    logger.success(f"已发送(modify)：{result}")
                else:
                    logger.info(f"已发送：{result}")
    def request(self,flow: http.HTTPFlow):
        # 在捕获到HTTP消息时触发
        if not any(k in flow.request.host for k in self._hosts):
            return
        if REPLACE_ENABLE:
            # 如果启用replace，就把HTTP消息丢进replace里
            path = replace_plugin.main(flow.request)
            if path != '':
                with open(BASE_DIR / "replace" / path.lstrip('/'), "rb") as f:
                    if (body := f.read() )!=b"":
                        flow.response = http.Response.make(200, body) #,  {"Content-Type": "image/png"})
                        logger.success(f"已替换(replace)：{flow.request.path}")
                    else:
                        logger.error(f"替换错误(error):{flow.request.path}")

PID_FILE = Path("/tmp/majsoul-max.pid")


def _write_pid_file():
    try:
        PID_FILE.write_text(str(os.getpid()))
    except OSError:
        pass


def _remove_pid_file():
    try:
        PID_FILE.unlink(missing_ok=True)
    except OSError:
        pass


async def start_mitm(port: int = 23410):
    # 创建 mitmproxy 配置
    # 有外部代理（机场/VPN）就把流量转发给它，没有就 mitmproxy 直连回源
    opts = Options(
        listen_host="127.0.0.1",
        listen_port=port,
        ssl_insecure=True,
    )
    # 这些选项由 mitmproxy 内置 addon 注册，需在 DumpMaster 构造（加载 addon）后设置
    extra = {
        "block_global": False,
        "flow_detail": 0,
        "termlog_verbosity": "warn",
    }
    upstream = resolve_upstream()
    if upstream:
        # mitmproxy 12+ 的 mode 是 Sequence[str]，支持多模式组合
        extra["mode"] = [f"upstream:{upstream}"]
        auto = str(SETTINGS.get("proxy", {}).get("upstream", "auto") or "").strip().lower()
        if auto in ("", "auto"):
            logger.success(f"检测到 Clash Verge，游戏流量经其转发: {upstream}")
        else:
            logger.success(f"已启用上游代理: {upstream}（游戏流量经 mitmproxy 转发）")
    else:
        logger.info("未检测到 Clash Verge，mitmproxy 直连回源")
    master = DumpMaster(opts)
    master.options.update(**extra)
    # 加载自定义插件
    master.addons.add(MajsoulMaxAddon())
    # 记录 PID：start.sh 用它识别/清理上次残留进程，确保端口不泄漏
    _write_pid_file()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGHUP):
        try:
            # kill/关终端也能优雅退出并释放端口（不只 Ctrl+C）
            loop.add_signal_handler(sig, master.shutdown)
        except (NotImplementedError, RuntimeError):
            pass
    try:
        # 启动 mitmproxy
        await master.run()
    except KeyboardInterrupt:
        master.shutdown()
    finally:
        _remove_pid_file()


def _detect_clash_verge() -> int | None:
    """探测本机 Clash Verge 的混合端口是否可用，返回端口；不可用返回 None。

    只做端口探测：按序尝试 settings.yaml 的 proxy.clash_port → 7897（Rev 默认）→
    7890（旧版），能连上说明 Clash Verge 内核在监听，返回该端口；都连不上返回
    None（mitmproxy 直连回源）。

    不再用「进程兜底」猜端口：clash-verge-service 这类 privileged helper 常驻进程
    （路径含 clash-verge-rev）不含代理内核、也不监听混合端口，仅凭进程名判断会误
    判，把流量导向一个根本没监听的端口，导致雀魂连不上。
    """
    override = SETTINGS.get("proxy", {}).get("clash_port")
    ports = []
    if override:
        try:
            ports.append(int(override))
        except (TypeError, ValueError):
            logger.warning(f"proxy.clash_port 配置无效（{override!r}），已忽略，使用默认探测")
    ports += [7897, 7890]
    for port in ports:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.3):
                return port
        except OSError:
            continue
    return None


def resolve_upstream() -> str | None:
    """解析上游代理地址。返回 None 表示 mitmproxy 直连回源。

    规则（来自 settings.yaml 的 proxy.upstream）:
      auto / 缺省  -> 检测本机 Clash Verge（进程+端口）：有则把游戏流量转发给它的混合端口，
                      没有则 mitmproxy 自己直连出网（即「启动自己的」）
      空 / direct  -> 直连
      其他值        -> 视为显式代理地址，如 http://127.0.0.1:7890
    """
    upstream = SETTINGS.get("proxy", {}).get("upstream", "auto")
    value = str(upstream or "").strip().lower()
    if not value or value in ("direct", "none", "off"):
        return None
    if value == "auto":
        port = _detect_clash_verge()
        return f"http://127.0.0.1:{port}" if port else None
    return str(upstream)


def main():
    # 支持 start.sh 传入端口：uv run python addons.py 23410
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 23410
    asyncio.run(start_mitm(port))


if __name__ == "__main__":
    main()

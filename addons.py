import asyncio
import json
import os
import signal
import sys
from functools import partial
from pathlib import Path
from sys import stdout

from loguru import logger
from mitmproxy import ctx, http
from mitmproxy.options import Options
from mitmproxy.tools.dump import DumpMaster
from ruamel.yaml import YAML, YAMLError

from plugin import update
from plugin.results import ModResult
from plugin.storage import save_yaml
from plugin.traffic import TrafficStats

BASE_DIR = Path(__file__).resolve().parent
REPLACE_DIR = BASE_DIR / "replace"

VERSION = "v2026.07.07"


DEFAULT_SETTINGS = """\
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
"""


def _deep_merge(base: dict, override) -> None:
    """递归合并 override 到 base（嵌套 dict 逐层合并，防浅合并丢键）。

    浅合并（dict.update）在 settings.yaml 只写部分键时会把 plugin_enable/liqi
    整块替换，导致后续 ['helper'] 等 KeyError。
    """
    if override is None:
        return
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _deep_merge(base[k], v)
        else:
            base[k] = v


def _safe_replace_path(path: str) -> Path | None:
    """校验 replace 资源路径不越界，返回安全的绝对路径；越界（../ 穿越）返回 None。"""
    target = (REPLACE_DIR / path.lstrip('/')).resolve()
    if not target.is_relative_to(REPLACE_DIR):
        logger.warning(f"replace 路径越界，拒绝: {path}")
        return None
    return target


def load_settings():
    """读取配置并补齐默认项，不检查更新或创建插件。"""
    yaml = YAML()
    settings = yaml.load(DEFAULT_SETTINGS)
    try:
        with open(BASE_DIR / "config" / "settings.yaml", encoding="utf-8") as f:
            _deep_merge(settings, yaml.load(f))
    except (FileNotFoundError, KeyError, YAMLError):
        logger.warning("配置未找到或无法读取，使用默认配置；修改 ./config/settings.yaml 后重启生效")
    return settings


def prepare_protocol(settings):
    """在导入协议模块之前完成更新和首次启动的数据准备。"""
    liqi = settings["liqi"]
    if liqi["auto_update"] or update.missing_local_files():
        logger.info("正在检测更新，请稍候……")
        try:
            version = update.update(VERSION, liqi["liqi_version"], liqi["github_token"])
            if version != liqi["liqi_version"]:
                liqi["liqi_version"] = version
                save_yaml(BASE_DIR / "config" / "settings.yaml", settings, YAML())
        except Exception as e:
            logger.critical(f"更新失败！可能会导致部分消息无法解析！错误：{e}")
    if missing := update.missing_local_files():
        logger.critical("启动所需数据未补齐：{}", ', '.join(str(path.relative_to(BASE_DIR)) for path in missing))
        raise SystemExit(1)


def create_addon():
    settings = load_settings()
    prepare_protocol(settings)
    # 协议模块会在导入时读取 liqi.desc，必须等数据准备好再导入。
    from liqi_new import LiqiProto, load_rpc_map

    protocol_factory = partial(LiqiProto, rpc_map=load_rpc_map())
    enabled = settings["plugin_enable"]
    mod_plugin = helper_plugin = replace_plugin = None
    if enabled["mod"]:
        from plugin.mod import mod
        mod_plugin = mod(VERSION)
    if enabled["helper"]:
        from plugin.helper import helper
        helper_plugin = helper()
    if enabled["replace"]:
        from plugin.replace import replace
        replace_plugin = replace()
    logger.success("已载入配置：mod={}，helper={}，replace={}",
                   enabled["mod"], enabled["helper"], enabled["replace"])
    if not any(enabled.values()):
        logger.warning("当前没有开启任何功能，请修改 ./config/settings.yaml 文件并重新启动！")
    return MajsoulMaxAddon(protocol_factory, mod_plugin, helper_plugin, replace_plugin)


class MajsoulMaxAddon:
    # 只处理雀魂域名流量（双保险：即使其他流量进了代理也不处理）
    _hosts = ("maj-soul.com", "mahjongsoul.com", "majsoul", "catmjstudio", "yo-star.com")

    def __init__(self, protocol_factory, mod_plugin=None, helper_plugin=None, replace_plugin=None):
        self.protocol_factory = protocol_factory
        self.mod_plugin = mod_plugin
        self.helper_plugin = helper_plugin
        self.replace_plugin = replace_plugin
        self.emoji_panel_assets = {}
        self.connections = {}
        self.traffic = TrafficStats()

    def running(self):
        logger.success("改包服务已启动，监听 {}:{}（Ctrl+C 停止）",
                       ctx.options.listen_host, ctx.options.listen_port)

    def _connection(self, flow):
        if flow.id not in self.connections:
            plugin = self.mod_plugin.for_connection() if self.mod_plugin is not None else None
            self.connections[flow.id] = (self.protocol_factory(), plugin)
        return self.connections[flow.id]

    def websocket_end(self, flow: http.HTTPFlow):
        self.connections.pop(flow.id, None)
        self.traffic.disconnect(flow.id)

    def done(self):
        self.connections.clear()
        self.traffic.clear()
        if self.helper_plugin is not None:
            self.helper_plugin.close()

    def websocket_message(self, flow: http.HTTPFlow):
        # 在捕获到WebSocket消息时触发
        assert flow.websocket is not None  # make type checker happy
        if not any(k in flow.request.host for k in self._hosts):
            return
        message = flow.websocket.messages[-1]
        if not message.injected:
            self.traffic.packet(len(message.content), message.from_client)
        # 不解析ob消息
        if flow.request.path == "/ob":
            logger.debug("{} /ob（未解析） len={}B",
                         "发送" if message.from_client else "接收", len(message.content))
            self.traffic.report()
            return
        liqi_proto, mod_plugin = self._connection(flow)
        modification = ModResult()
        if mod_plugin is not None and not message.injected:
            try:
                modification = mod_plugin.main(message, liqi_proto)
            except Exception as e:
                logger.warning(f"mod 处理异常，跳过: {e}")
            if modification.drop:
                message.drop()
            if modification.injected_content is not None:
                ctx.master.commands.call(
                    "inject.websocket", flow, True, modification.injected_content, False
                )
            if modification.modify:
                message.content = modification.content
        try:
            result = liqi_proto.parse(message) # 解析消息
        except Exception as e:
            # 只记录消息长度与方向，不打印原始字节（WS 流量可能含账号 token，防泄漏）
            direction = "接收到" if message.from_client is False else "已发送"
            logger.error(f"{direction}(error) len={len(message.content)}B: {e}")
        else:
            if not message.injected and not modification.drop:
                self.traffic.rpc(flow.id, result)
            status = (
                "注入" if message.injected else
                "丢弃" if modification.drop else
                "修改" if modification.modify else "透传"
            )
            logger.debug("{} {} [{}] len={}B",
                         "发送" if message.from_client else "接收",
                         result['method'], status, len(message.content))
            if message.from_client is False:
                if self.helper_plugin is not None:
                    # 如果启用helper，就把消息丢进helper里（异常不能中断消息流）
                    try:
                        self.helper_plugin.main(result)
                    except Exception as e:
                        logger.warning(f"helper 处理异常，跳过: {e}")
        self.traffic.report()

    def request(self, flow: http.HTTPFlow):
        # 在捕获到HTTP消息时触发
        if not any(k in flow.request.host for k in self._hosts):
            return
        if self.mod_plugin is not None:
            from plugin.unity_emoji import PATCH_TAG
            path = flow.request.path.partition('?')[0]
            if path == '/_majsoulmax/emoji-panel-assets':
                body = json.dumps({'tag': PATCH_TAG, 'assets': list(self.emoji_panel_assets.values())}).encode()
                flow.response = http.Response.make(200, body, {'content-type': 'application/json', 'cache-control': 'no-store'})
                return
            if path in self.emoji_panel_assets:
                flow.metadata['max_emoji_panel'] = True
            if flow.metadata.get('max_emoji_panel') or path.endswith('.loader.js') or path.endswith('/bundle_info_so.majset'):
                for header in ('if-none-match', 'if-modified-since'):
                    flow.request.headers.pop(header, None)
        if self.replace_plugin is None:
            return
        path = self.replace_plugin.main(flow.request)
        if not path:
            return
        try:
            target = _safe_replace_path(path)
            if target is None:
                return
            body = target.read_bytes()
        except OSError as e:
            logger.warning("替换资源读取失败，保留原请求：{}（{}）", path, e)
            return
        if not body:
            logger.warning("替换资源为空，保留原请求：{}", path)
            return
        flow.response = http.Response.make(200, body)
        logger.debug("已替换资源：{}", flow.request.path)

    def response(self, flow: http.HTTPFlow):
        if self.mod_plugin is None or not any(k in flow.request.host for k in self._hosts):
            return
        path = flow.request.path.partition('?')[0]
        if flow.response.status_code != 200:
            return
        is_loader = path.endswith('.loader.js') and '/Build/' in path
        is_index = path.startswith('/assetbundles/') and path.endswith('/bundle_info_so.majset')
        is_panel = flow.metadata.get('max_emoji_panel', False)
        if not (is_loader or is_index or is_panel):
            return
        from plugin.unity_emoji import PATCH_TAG, patch_bundle, panel_bundle_names
        try:
            body = flow.response.content
            if is_loader:
                bootstrap = (BASE_DIR / 'plugin' / 'unity_emoji_bootstrap.js').read_bytes()
                patched = body + b'\n' + bootstrap
            elif is_index:
                prefix = path.rsplit('/', 1)[0]
                for name in panel_bundle_names(body):
                    url = prefix + '/' + name
                    self.emoji_panel_assets[url] = {'name': name, 'url': url}
                return
            elif is_panel:
                patched = patch_bundle(body)
                flow.response.headers['x-majsoulmax-emoji-panel'] = PATCH_TAG
                logger.info('已更新 Unity 对局表情面板')
            else:
                return
        except Exception as e:
            logger.warning('Unity 表情面板补丁失败，保留原资源：{}', e)
            return
        flow.response.content = patched
        for header in ('etag', 'last-modified'):
            flow.response.headers.pop(header, None)
        flow.response.headers['cache-control'] = 'no-store'


async def start_mitm(port: int = 23410, addon=None):
    # 创建 mitmproxy 配置
    # 仅提供本地改包入口；流量接管和出站路由由 Clash Verge TUN 负责。
    if addon is None:
        addon = create_addon()
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
    master = DumpMaster(opts)
    master.options.update(**extra)
    # 加载自定义插件
    master.addons.add(addon)
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


def main():
    logger.remove()
    logger.add(stdout, colorize=True,
               level=os.environ.get("MAJSOUL_LOG_LEVEL", "INFO").upper(),
               format="<cyan>[{time:HH:mm:ss}]</cyan> <level>{level: <7} {message}</level>")
    # 支持 start.sh 传入端口：uv run python addons.py 23410
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 23410
    try:
        addon = create_addon()
        asyncio.run(start_mitm(port, addon))
    except KeyboardInterrupt:
        # asyncio.run 在任务取消、清理完成后才向外抛出 Ctrl+C。
        logger.info("改包服务已停止")


if __name__ == "__main__":
    main()

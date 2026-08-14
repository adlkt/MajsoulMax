"""addons.py 集成测试：直接驱动 MajsoulMaxAddon.websocket_message 事件链。

用真实 mod_plugin/liqi_proto（模块级单例），mock flow/message 对象，
验证 addon → mod 处理 → liqi 解析 → 日志全链路。不做网络 I/O。
"""
from types import SimpleNamespace

import pytest

import addons
from proto import basic_pb2, liqi_pb2


@pytest.fixture(autouse=True)
def _no_disk_writes(monkeypatch):
    """测试期间禁止 mod_plugin 写真实配置文件（SaveSettings 置空）。"""
    if hasattr(addons, "mod_plugin"):
        monkeypatch.setattr(addons.mod_plugin, "SaveSettings", lambda: None)


@pytest.fixture(autouse=True)
def _fake_master(monkeypatch):
    """addons.ctx.master 在真实运行由 mitmproxy 注入，测试用 fake。"""
    import mitmproxy.ctx

    fake = SimpleNamespace()
    fake.commands = SimpleNamespace(call=lambda *a, **k: None)
    monkeypatch.setattr(mitmproxy.ctx, "master", fake, raising=False)
    return fake


class FakeMessage:
    """模拟 mitmproxy WebSocketMessage（content/from_client/injected/drop）。"""

    def __init__(self, content: bytes, from_client: bool = False):
        self.content = content
        self.from_client = from_client
        self.injected = False
        self._dropped = False

    def drop(self):
        self._dropped = True


def _make_flow(host: str = "game.maj-soul.com", path: str = "/1/ws",
               messages=None):
    flow = SimpleNamespace()
    flow.request = SimpleNamespace(host=host, path=path)
    flow.websocket = SimpleNamespace(messages=messages or [])
    return flow


def _notify_buf(method_name: str, data: bytes) -> bytes:
    blk = basic_pb2.BaseMessage()
    blk.method_name = method_name
    blk.data = data
    return b"\x01" + blk.SerializeToString()


@pytest.fixture
def addon():
    return addons.MajsoulMaxAddon()


class TestHostFiltering:
    def test_non_majsoul_host_ignored(self, addon):
        """非雀魂域名流量不处理（_hosts 过滤）。"""
        flow = _make_flow(host="www.example.com", messages=[FakeMessage(b"\x00")])
        addon.websocket_message(flow)  # 不应抛异常

    def test_majsoul_host_processed(self, addon):
        """雀魂域名流量进入处理链。"""
        n = liqi_pb2.NotifyAccountLevelChange()
        n.origin.id = 1
        buf = _notify_buf(".lq.NotifyAccountLevelChange",
                          n.SerializeToString())
        msg = FakeMessage(buf)
        flow = _make_flow(host="game.maj-soul.com", messages=[msg])
        addon.websocket_message(flow)  # 正常解析，不抛异常


class TestObPath:
    def test_ob_messages_skipped(self, addon):
        """/ob 观战消息不解析（只记 debug）。"""
        msg = FakeMessage(b"\x01\x02\x03")
        flow = _make_flow(host="game.maj-soul.com", path="/ob", messages=[msg])
        addon.websocket_message(flow)  # 跳过 mod/parse，不抛异常


class TestModIntegration:
    def test_notify_account_update_drops(self, addon):
        """真实 mod_plugin：NotifyAccountUpdate 带 character → drop。"""
        n = liqi_pb2.NotifyAccountUpdate()
        n.update.character.characters.add().charid = 200001
        buf = _notify_buf(".lq.NotifyAccountUpdate", n.SerializeToString())
        msg = FakeMessage(buf)
        flow = _make_flow(host="game.maj-soul.com", messages=[msg])
        addon.websocket_message(flow)
        assert msg._dropped is True

    def test_unknown_notify_passthrough(self, addon):
        """未注册的 Notify：不 drop 不修改，正常解析记录。"""
        blk = basic_pb2.BaseMessage()
        blk.method_name = ".lq.NotifySomethingUnknown"
        msg = FakeMessage(b"\x01" + blk.SerializeToString())
        flow = _make_flow(host="game.maj-soul.com", messages=[msg])
        addon.websocket_message(flow)
        assert msg._dropped is False
        # 未修改：content 保持原样
        assert msg.content == b"\x01" + blk.SerializeToString()

    def test_parse_error_does_not_crash(self, addon):
        """畸形消息：parse 抛错被捕获，只记 error 日志，不中断。"""
        msg = FakeMessage(b"\x02\xff\xff")  # 非法 msg_id/空内容
        flow = _make_flow(host="game.maj-soul.com", messages=[msg])
        addon.websocket_message(flow)  # 不抛异常


class TestReqFlow:
    def test_req_change_character_skin_injects(self, addon, _fake_master):
        """Req.changeCharacterSkin：modify + inject 触发，注入消息被发送。

        真实游戏流程是先 loginBeat 记录 contract，再改皮肤；模拟该顺序。
        """
        called = []
        _fake_master.commands.call = lambda *a, **k: called.append(a)

        # 先 loginBeat（记录 contract）
        beat = liqi_pb2.ReqLoginBeat()
        beat.contract = "abc"
        beat_blk = basic_pb2.BaseMessage()
        beat_blk.method_name = ".lq.Lobby.loginBeat"
        beat_blk.data = beat.SerializeToString()
        beat_buf = b"\x02" + b"\x00\x00" + beat_blk.SerializeToString()
        addon.websocket_message(_make_flow(
            host="game.maj-soul.com", messages=[FakeMessage(beat_buf, from_client=True)]))

        # 再 changeCharacterSkin
        req = liqi_pb2.ReqChangeCharacterSkin()
        req.character_id = 200001
        req.skin = 400101
        blk = basic_pb2.BaseMessage()
        blk.method_name = ".lq.Lobby.changeCharacterSkin"
        blk.data = req.SerializeToString()
        buf = b"\x02" + b"\x01\x00" + blk.SerializeToString()
        msg = FakeMessage(buf, from_client=True)
        flow = _make_flow(host="game.maj-soul.com", messages=[msg])

        addon.websocket_message(flow)
        assert len(called) == 1  # inject.websocket 被调用
        assert called[0][0] == "inject.websocket"

    def test_skin_change_without_login_does_not_crash(self, addon, _fake_master):
        """未登录就改皮肤：mod 抛异常被 addons 捕获，不中断 addon。"""
        called = []
        _fake_master.commands.call = lambda *a, **k: called.append(a)
        req = liqi_pb2.ReqChangeCharacterSkin()
        req.character_id = 200001
        req.skin = 400101
        blk = basic_pb2.BaseMessage()
        blk.method_name = ".lq.Lobby.changeCharacterSkin"
        blk.data = req.SerializeToString()
        buf = b"\x02" + b"\x01\x00" + blk.SerializeToString()
        msg = FakeMessage(buf, from_client=True)
        addon.websocket_message(_make_flow(
            host="game.maj-soul.com", messages=[msg]))
        assert len(called) == 0  # inject 未触发但也没崩


class TestSensitiveLogRedaction:
    """请求方向凭证脱敏：oauth2Login/login/loginBeat 只打 method+len，不打内容。"""

    @pytest.mark.parametrize("method", [
        ".lq.Lobby.oauth2Login",  # token 登录，请求含凭证
        ".lq.Lobby.login",        # 账号登录
        ".lq.Lobby.loginBeat",    # 心跳，含会话 contract
    ])
    def test_sensitive_methods_redacted(self, method):
        line = addons._redacted_log(method, 42)
        assert line is not None
        assert method in line
        assert "42" in line

    def test_plain_methods_not_redacted(self):
        assert addons._redacted_log(".lq.Lobby.fetchTitleList", 42) is None
        assert addons._redacted_log(".lq.NotifyAccountLevelChange", 42) is None

    def test_oauth2_login_request_flows_without_error(self, addon):
        """oauth2Login 请求走完整 addon 链路：不抛异常（日志脱敏）。"""
        req = liqi_pb2.ReqOauth2Login()
        req.access_token = "super-secret-token-please-do-not-log"
        blk = basic_pb2.BaseMessage()
        blk.method_name = ".lq.Lobby.oauth2Login"
        blk.data = req.SerializeToString()
        buf = b"\x02" + b"\x01\x00" + blk.SerializeToString()
        addon.websocket_message(_make_flow(
            host="game.maj-soul.com",
            messages=[FakeMessage(buf, from_client=True)]))


class TestConfigMerge:
    """SETTINGS 深合并：settings.yaml 只写部分键时，默认嵌套键不能丢
    （浅合并会把 plugin_enable 整块替换 → ['helper'] KeyError）。"""

    def test_nested_keys_preserved(self):
        base = {"plugin_enable": {"mod": True, "helper": False},
                "liqi": {"auto_update": True}}
        addons._deep_merge(base, {"proxy": {"upstream": "direct"}})
        assert base["plugin_enable"]["helper"] is False
        assert base["proxy"]["upstream"] == "direct"

    def test_partial_nested_override(self):
        base = {"liqi": {"auto_update": True, "liqi_version": "1"}}
        addons._deep_merge(base, {"liqi": {"auto_update": False}})
        assert base["liqi"]["auto_update"] is False
        assert base["liqi"]["liqi_version"] == "1"

    def test_none_override_noop(self):
        base = {"a": 1}
        addons._deep_merge(base, None)  # 空配置文件不崩


class TestSafeReplacePath:
    """replace 资源路径防呆：越界路径（../ 穿越）必须拒绝。"""

    def test_normal_path_ok(self):
        p = addons._safe_replace_path("/img/1.png")
        assert p is not None
        assert p.name == "1.png"
        assert p.is_relative_to(addons.BASE_DIR / "replace")

    def test_traversal_rejected(self):
        assert addons._safe_replace_path("../../etc/passwd") is None
        assert addons._safe_replace_path("/../../etc/passwd") is None

"""addons.py 集成测试：直接驱动 MajsoulMaxAddon.websocket_message 事件链。

用真实 mod/protocol 实例和临时配置目录，mock flow/message 对象，
验证 addon → mod 处理 → liqi 解析 → 日志全链路。不做网络 I/O。
"""
from types import SimpleNamespace
from uuid import uuid4

import pytest

import addons
from liqi_new import LiqiProto
from plugin.mod import mod
from proto import basic_pb2, liqi_pb2


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
    flow = SimpleNamespace(id=str(uuid4()))
    flow.request = SimpleNamespace(host=host, path=path)
    flow.websocket = SimpleNamespace(messages=messages or [])
    return flow


def _notify_buf(method_name: str, data: bytes) -> bytes:
    blk = basic_pb2.BaseMessage()
    blk.method_name = method_name
    blk.data = data
    return b"\x01" + blk.SerializeToString()


@pytest.fixture
def addon(monkeypatch, tmp_path):
    import plugin.mod as mod_module

    monkeypatch.setattr(mod_module, "BASE_DIR", tmp_path)
    monkeypatch.setattr(mod, "SaveSettings", lambda self: None)
    (tmp_path / "config").mkdir()
    (tmp_path / "config/max_data.yaml").write_text(
        "character: [200001]\nskin: [400101]\ntitle: []\nitem: []\n"
        "loading_image: []\nendings: []\nemoji: {}\n")
    plugin = mod(addons.VERSION)
    plugin.settings['config']['characters'][200001] = 400101
    return addons.MajsoulMaxAddon(LiqiProto, plugin)


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
        flow = _make_flow(messages=[FakeMessage(beat_buf, from_client=True)])
        addon.websocket_message(flow)

        # 再 changeCharacterSkin
        req = liqi_pb2.ReqChangeCharacterSkin()
        req.character_id = 200001
        req.skin = 400101
        blk = basic_pb2.BaseMessage()
        blk.method_name = ".lq.Lobby.changeCharacterSkin"
        blk.data = req.SerializeToString()
        buf = b"\x02" + b"\x01\x00" + blk.SerializeToString()
        msg = FakeMessage(buf, from_client=True)
        flow.websocket.messages.append(msg)

        addon.websocket_message(flow)
        assert addon.connections[flow.id][1].contract == "abc"
        assert len(called) == 1  # inject.websocket 被调用
        assert called[0][0] == "inject.websocket"
        outgoing = basic_pb2.BaseMessage.FromString(msg.content[3:])
        assert outgoing.method_name == '.lq.Lobby.loginBeat'
        assert liqi_pb2.ReqLoginBeat.FromString(outgoing.data).contract == 'abc'
        injected = basic_pb2.BaseMessage.FromString(called[0][3][1:])
        assert injected.method_name == '.lq.NotifyAccountUpdate'
        update = liqi_pb2.NotifyAccountUpdate.FromString(injected.data)
        assert update.update.character.characters[0].skin == 400101

    def test_skin_change_without_login_uses_empty_contract(self, addon, _fake_master):
        """未登录就改皮肤：contract 有空串兜底，不再抛 AttributeError，
        正常走 fake 路径——请求被顶替为 loginBeat（空 contract）发给服务器。"""
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
        # 修复前：mod 抛 AttributeError 被 addons 捕获跳过，无 inject
        # 修复后：contract 兜底空串，fake 路径正常执行并注入 NotifyAccountUpdate
        addon.websocket_message(_make_flow(
            host="game.maj-soul.com", messages=[msg]))
        assert len(called) == 1  # inject.websocket（NotifyAccountUpdate）被调用


class TestCredentialRequests:
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
        addons._deep_merge(base, {"plugin_enable": {"mod": False}})
        assert base["plugin_enable"]["helper"] is False
        assert base["plugin_enable"]["mod"] is False

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


def _rpc_message(method, payload, msg_id=7):
    blk = basic_pb2.BaseMessage(method_name=method, data=payload.SerializeToString())
    kind = b"\x02" if method else b"\x03"
    return FakeMessage(kind + msg_id.to_bytes(2, "little") + blk.SerializeToString(),
                       from_client=bool(method))


def test_connections_with_same_request_id_do_not_mix_accounts(addon, monkeypatch):
    errors = []
    monkeypatch.setattr(addons.logger, "error", lambda *args: errors.append(args))
    monkeypatch.setattr(addons.logger, "warning", lambda *args: errors.append(args))
    addon.mod_plugin.settings['config']['nickname'] = 'local'
    addon.mod_plugin.settings['config']['show_server'] = False
    first = _make_flow(messages=[_rpc_message(
        '.lq.FastTest.authGame', liqi_pb2.ReqAuthGame(account_id=111))])
    second = _make_flow(messages=[_rpc_message(
        '.lq.FastTest.authGame', liqi_pb2.ReqAuthGame(account_id=222))])
    addon.websocket_message(first)
    addon.websocket_message(second)
    for flow, own_id in ((second, 222), (first, 111)):
        response = liqi_pb2.ResAuthGame()
        for account_id in (111, 222):
            player = response.players.add(account_id=account_id, nickname='server')
            player.character.charid = 200001
        message = _rpc_message('', response)
        flow.websocket.messages.append(message)
        addon.websocket_message(flow)
        block = basic_pb2.BaseMessage.FromString(message.content[3:])
        result = liqi_pb2.ResAuthGame.FromString(block.data)
        assert [p.nickname for p in result.players] == [
            'local' if account_id == own_id else 'server' for account_id in (111, 222)]
        assert addon.connections[flow.id][0].res_type == {}
    assert errors == []
    assert addon.connections[first.id][1].safe is not addon.connections[second.id][1].safe


def test_connections_with_same_id_match_different_response_types(addon, monkeypatch):
    errors = []
    monkeypatch.setattr(addons.logger, "error", lambda *args: errors.append(args))
    monkeypatch.setattr(addons.logger, "warning", lambda *args: errors.append(args))
    first = _make_flow(messages=[_rpc_message(
        '.lq.Lobby.loginBeat', liqi_pb2.ReqLoginBeat(contract='first'))])
    second = _make_flow(messages=[_rpc_message(
        '.lq.Lobby.fetchTitleList', liqi_pb2.ReqCommon())])
    addon.websocket_message(first)
    addon.websocket_message(second)
    assert addon.connections[first.id][0].res_type[7][0] == '.lq.Lobby.loginBeat'
    assert addon.connections[second.id][0].res_type[7][0] == '.lq.Lobby.fetchTitleList'
    first.websocket.messages.append(_rpc_message('', liqi_pb2.ResCommon()))
    second.websocket.messages.append(_rpc_message('', liqi_pb2.ResTitleList()))
    addon.websocket_message(first)
    addon.websocket_message(second)
    assert addon.connections[first.id][0].res_type == {}
    assert addon.connections[second.id][0].res_type == {}
    assert errors == []


def test_connection_contract_and_cleanup(addon):
    first = _make_flow(messages=[_rpc_message(
        '.lq.Lobby.loginBeat', liqi_pb2.ReqLoginBeat(contract='first'))])
    second = _make_flow(messages=[_rpc_message(
        '.lq.Lobby.loginBeat', liqi_pb2.ReqLoginBeat(contract='second'))])
    addon.websocket_message(first)
    addon.websocket_message(second)
    assert addon.connections[first.id][1].contract == 'first'
    assert addon.connections[second.id][1].contract == 'second'
    addon.websocket_end(first)
    addon.websocket_end(first)  # 清理可重复，未处理过的连接也可安全关闭。
    assert first.id not in addon.connections
    assert second.id in addon.connections
    addon.done()
    assert addon.connections == {}


def test_protocol_isolated_when_mod_disabled():
    addon = addons.MajsoulMaxAddon(LiqiProto)
    first = _make_flow(messages=[_rpc_message(
        '.lq.Lobby.loginBeat', liqi_pb2.ReqLoginBeat())])
    second = _make_flow(messages=[_rpc_message(
        '.lq.Lobby.fetchTitleList', liqi_pb2.ReqCommon())])
    addon.websocket_message(first)
    addon.websocket_message(second)
    assert addon.connections[first.id][1] is None
    assert addon.connections[first.id][0].res_type[7][0] == '.lq.Lobby.loginBeat'
    assert addon.connections[second.id][0].res_type[7][0] == '.lq.Lobby.fetchTitleList'


def test_addon_shutdown_closes_helper():
    closed = []
    addon = addons.MajsoulMaxAddon(LiqiProto, helper_plugin=SimpleNamespace(
        close=lambda: closed.append(True)))
    addon.done()
    assert closed == [True]


def test_routine_game_messages_are_quiet_at_info(addon):
    from loguru import logger

    lines = []
    sink = logger.add(lambda message: lines.append(str(message)), level='INFO')
    try:
        flow = _make_flow(messages=[_rpc_message(
            '.lq.Lobby.loginBeat', liqi_pb2.ReqLoginBeat(contract='private-contract'))])
        addon.websocket_message(flow)
        for _ in range(20):
            notification = liqi_pb2.NotifyAccountLevelChange()
            flow.websocket.messages.append(FakeMessage(_notify_buf(
                '.lq.NotifyAccountLevelChange', notification.SerializeToString())))
            addon.websocket_message(flow)
        assert lines == []
        flow.websocket.messages.append(FakeMessage(b'\x02\xff\xff'))
        addon.websocket_message(flow)
        assert any('error' in line for line in lines)
    finally:
        logger.remove(sink)


def test_debug_messages_summarize_without_payload(addon):
    from loguru import logger

    lines = []
    sink = logger.add(lambda message: lines.append(str(message)), level='DEBUG')
    try:
        addon.websocket_message(_make_flow(messages=[_rpc_message(
            '.lq.Lobby.loginBeat', liqi_pb2.ReqLoginBeat(contract='private-contract'))]))
        addon.websocket_message(_make_flow(path='/ob', messages=[FakeMessage(b'private-ob-data')]))
        assert len(lines) == 2
        assert '.lq.Lobby.loginBeat' in lines[0]
        assert 'private-contract' not in ''.join(lines)
        assert 'private-ob-data' not in ''.join(lines)
        assert all('len=' in line for line in lines)
    finally:
        logger.remove(sink)


def test_game_traffic_summary_uses_real_rpc_messages(addon, monkeypatch):
    from plugin.traffic import TrafficStats

    now = [0.0]
    lines = []
    addon.traffic = TrafficStats(clock=lambda: now[0])
    monkeypatch.setattr(addons.logger, 'info',
                        lambda template, *args: lines.append(template.format(*args)))
    request = _rpc_message('.lq.Lobby.loginBeat', liqi_pb2.ReqLoginBeat())
    flow = _make_flow(messages=[request])
    addon.websocket_message(flow)
    now[0] = 0.05
    response = _rpc_message('', liqi_pb2.ResCommon())
    flow.websocket.messages.append(response)
    addon.websocket_message(flow)
    injected = FakeMessage(_notify_buf(
        '.lq.NotifyAccountLevelChange', liqi_pb2.NotifyAccountLevelChange().SerializeToString()))
    injected.injected = True
    flow.websocket.messages.append(injected)
    addon.websocket_message(flow)
    assert lines == []
    now[0] = 10
    addon.websocket_message(_make_flow(path='/ob', messages=[FakeMessage(b'ob-data')]))
    assert len(lines) == 1
    assert '↑1包' in lines[0]
    assert '↓2包' in lines[0]
    assert '延迟 50ms' in lines[0]
    addon.websocket_end(flow)
    assert not addon.traffic.pending


class TestReplaceFallback:
    @pytest.fixture
    def replacement(self, tmp_path, monkeypatch):
        monkeypatch.setattr(addons, 'REPLACE_DIR', tmp_path)
        addon = addons.MajsoulMaxAddon(LiqiProto, replace_plugin=SimpleNamespace(
            main=lambda request: '/img/test.png'))
        flow = _make_flow(path='/img/test.png')
        flow.response = None
        return addon, flow, tmp_path / 'img/test.png'

    def test_missing_file_leaves_original_request(self, replacement, monkeypatch):
        addon, flow, target = replacement
        warnings = []
        monkeypatch.setattr(addons.logger, 'warning', lambda *args: warnings.append(args))
        addon.request(flow)
        assert flow.response is None
        assert flow.request.path == '/img/test.png'
        assert warnings

    @pytest.mark.parametrize('error', [PermissionError, IsADirectoryError, OSError])
    def test_read_error_leaves_original_request(self, replacement, monkeypatch, error):
        from pathlib import Path

        addon, flow, target = replacement
        warnings = []
        monkeypatch.setattr(addons.logger, 'warning', lambda *args: warnings.append(args))

        def fail_read(path):
            raise error('cannot read replacement')

        monkeypatch.setattr(Path, 'read_bytes', fail_read)
        addon.request(flow)
        assert flow.response is None
        assert warnings

    def test_valid_file_replaces_response(self, replacement):
        addon, flow, target = replacement
        target.parent.mkdir()
        target.write_bytes(b'replacement-image')
        addon.request(flow)
        assert flow.response.status_code == 200
        assert flow.response.content == b'replacement-image'

    def test_empty_file_leaves_original_request(self, replacement):
        addon, flow, target = replacement
        target.parent.mkdir()
        target.write_bytes(b'')
        addon.request(flow)
        assert flow.response is None

    def test_traversal_leaves_original_request(self, replacement):
        addon, flow, target = replacement
        addon.replace_plugin.main = lambda request: '../../outside.png'
        addon.request(flow)
        assert flow.response is None


# Unity Web sends character-specific emo_id values instead of a shared ordinal.
def _emoji_game(addon, server_character=200001, local_character=200050):
    addon.mod_plugin.settings['config']['character'] = local_character
    addon.mod_plugin.settings['config']['characters'][local_character] = 400501
    flow = _make_flow(messages=[_rpc_message(
        '.lq.FastTest.authGame', liqi_pb2.ReqAuthGame(account_id=111))])
    addon.websocket_message(flow)
    response = liqi_pb2.ResAuthGame(seat_list=[222, 111, 333])
    player = response.players.add(account_id=111)
    player.character.charid = server_character
    message = _rpc_message('', response)
    flow.websocket.messages.append(message)
    addon.websocket_message(flow)
    return flow


@pytest.mark.parametrize('server_character,server_emoji', [
    (200001, 10001), (200002, 20001), (20000107, 1070001)])
def test_unity_emoji_request_and_own_broadcast_roundtrip(
        addon, server_character, server_emoji):
    import json
    flow = _emoji_game(addon, server_character)
    request = _rpc_message('.lq.FastTest.broadcastInGame',
        liqi_pb2.ReqBroadcastInGame(content='{"emo_id":500001,"keep":true}',
                                   except_self=True), msg_id=9)
    flow.websocket.messages.append(request)
    addon.websocket_message(flow)
    block = basic_pb2.BaseMessage.FromString(request.content[3:])
    sent = liqi_pb2.ReqBroadcastInGame.FromString(block.data)
    assert json.loads(sent.content) == {'emo_id': server_emoji, 'keep': True}
    assert sent.except_self is True
    assert block.method_name == '.lq.FastTest.broadcastInGame'
    assert request.content[:3] == b'\x02\x09\x00'
    # The remote acceptance belongs to the same RPC, not a fake loginBeat.
    response = _rpc_message('', liqi_pb2.ResCommon(), msg_id=9)
    flow.websocket.messages.append(response)
    addon.websocket_message(flow)
    assert 9 not in addon.connections[flow.id][0].res_type
    notification = liqi_pb2.NotifyGameBroadcast(
        seat=1, content=json.dumps({'emo_id': server_emoji, 'keep': True}))
    incoming = FakeMessage(_notify_buf('.lq.NotifyGameBroadcast',
                                      notification.SerializeToString()))
    flow.websocket.messages.append(incoming)
    addon.websocket_message(flow)
    block = basic_pb2.BaseMessage.FromString(incoming.content[1:])
    displayed = liqi_pb2.NotifyGameBroadcast.FromString(block.data)
    assert displayed.seat == 1
    assert json.loads(displayed.content) == {'emo_id': 500001, 'keep': True}


@pytest.mark.parametrize('content', [
    '{"emo":1}', '{"emo_id":500010}', '{"emo_id":99990001}',
    '{"emo_id":10001}', '{"emo_id":"500001"}', 'not JSON', '[]'])
def test_unity_emoji_unrelated_or_extra_payload_passthrough(addon, content):
    flow = _emoji_game(addon)
    request = _rpc_message('.lq.FastTest.broadcastInGame',
                          liqi_pb2.ReqBroadcastInGame(content=content), msg_id=9)
    before = request.content
    flow.websocket.messages.append(request)
    addon.websocket_message(flow)
    assert request.content == before


def test_unity_emoji_other_players_are_not_remapped(addon):
    flow = _emoji_game(addon)
    notification = liqi_pb2.NotifyGameBroadcast(seat=0, content='{"emo_id":10001}')
    message = FakeMessage(_notify_buf('.lq.NotifyGameBroadcast',
                                     notification.SerializeToString()))
    before = message.content
    flow.websocket.messages.append(message)
    addon.websocket_message(flow)
    assert message.content == before


def test_unity_emoji_no_game_snapshot_passthrough(addon):
    request = _rpc_message('.lq.FastTest.broadcastInGame',
                          liqi_pb2.ReqBroadcastInGame(content='{"emo_id":500001}'))
    before = request.content
    addon.websocket_message(_make_flow(messages=[request]))
    assert request.content == before


def test_unity_emoji_uses_actual_random_character(addon):
    import json
    addon.mod_plugin.settings['config']['random_character'] = {
        'enabled': True, 'pool': [{'character_id': 200002, 'skin_id': 400201}]}
    flow = _emoji_game(addon)
    request = _rpc_message('.lq.FastTest.broadcastInGame',
                          liqi_pb2.ReqBroadcastInGame(content='{"emo_id":20001}'))
    flow.websocket.messages.append(request)
    addon.websocket_message(flow)
    block = basic_pb2.BaseMessage.FromString(request.content[3:])
    assert json.loads(liqi_pb2.ReqBroadcastInGame.FromString(block.data).content)['emo_id'] == 10001


@pytest.mark.parametrize('index', range(9))
def test_unity_emoji_all_basic_indices(addon, index):
    import json
    flow = _emoji_game(addon)
    request = _rpc_message('.lq.FastTest.broadcastInGame',
        liqi_pb2.ReqBroadcastInGame(content=json.dumps({'emo_id': 500000 + index})))
    flow.websocket.messages.append(request)
    addon.websocket_message(flow)
    block = basic_pb2.BaseMessage.FromString(request.content[3:])
    sent = liqi_pb2.ReqBroadcastInGame.FromString(block.data)
    assert json.loads(sent.content)['emo_id'] == 10000 + index


def test_unity_emoji_missing_seat_does_not_rewrite_broadcast(addon):
    flow = _emoji_game(addon)
    addon.connections[flow.id][1].safe['emoji_mapping']['seat'] = None
    message = FakeMessage(_notify_buf('.lq.NotifyGameBroadcast',
        liqi_pb2.NotifyGameBroadcast(seat=0, content='{"emo_id":10001}').SerializeToString()))
    before = message.content
    flow.websocket.messages.append(message)
    addon.websocket_message(flow)
    assert message.content == before


def test_unity_emoji_reauthentication_clears_previous_mapping(addon):
    flow = _emoji_game(addon)
    flow.websocket.messages.append(_rpc_message('.lq.FastTest.authGame',
        liqi_pb2.ReqAuthGame(account_id=222), msg_id=10))
    addon.websocket_message(flow)
    response = liqi_pb2.ResAuthGame()
    response.error.code = 1
    flow.websocket.messages.append(_rpc_message('', response, msg_id=10))
    addon.websocket_message(flow)
    assert 'emoji_mapping' not in addon.connections[flow.id][1].safe


def test_unity_emoji_game_connections_do_not_share_mapping(addon):
    import json
    first = _emoji_game(addon, 200001)
    second = _emoji_game(addon, 200002)
    for flow, expected in ((first, 10001), (second, 20001)):
        request = _rpc_message('.lq.FastTest.broadcastInGame',
            liqi_pb2.ReqBroadcastInGame(content='{"emo_id":500001}'), msg_id=9)
        flow.websocket.messages.append(request)
        addon.websocket_message(flow)
        block = basic_pb2.BaseMessage.FromString(request.content[3:])
        assert json.loads(liqi_pb2.ReqBroadcastInGame.FromString(block.data).content)['emo_id'] == expected


def test_unity_emoji_auth_filters_list_by_real_unlocked_set(addon):
    flow = _emoji_game(addon)
    # Re-authentication gives the original server state, not the first MOD output.
    flow.websocket.messages.append(_rpc_message('.lq.FastTest.authGame',
        liqi_pb2.ReqAuthGame(account_id=111), msg_id=10))
    addon.websocket_message(flow)
    response = liqi_pb2.ResAuthGame(seat_list=[222, 111, 333])
    player = response.players.add(account_id=111)
    player.character.charid = 200001
    player.character.skin = 400101
    player.character.extra_emoji.append(14)
    player.character.enabled_emoji.extend(list(range(10000, 10009)) + [99990007])
    message = _rpc_message('', response, msg_id=10)
    flow.websocket.messages.append(message)
    addon.websocket_message(flow)
    block = basic_pb2.BaseMessage.FromString(message.content[3:])
    displayed = liqi_pb2.ResAuthGame.FromString(block.data).players[0].character
    assert list(displayed.enabled_emoji) == list(range(500000, 500009)) + [99990005]
    assert list(displayed.extra_emoji) == [14]
    assert displayed.skin == addon.mod_plugin.settings['config']['characters'][200050]
    assert displayed.is_upgraded
    # The allowed extra emoji follows the same send/receive path as basics.
    request = _rpc_message('.lq.FastTest.broadcastInGame',
        liqi_pb2.ReqBroadcastInGame(content='{"emo_id":99990005}'), msg_id=9)
    flow.websocket.messages.append(request)
    addon.websocket_message(flow)
    block = basic_pb2.BaseMessage.FromString(request.content[3:])
    assert liqi_pb2.ReqBroadcastInGame.FromString(block.data).content == '{"emo_id":99990007}'
    notification = FakeMessage(_notify_buf('.lq.NotifyGameBroadcast',
        liqi_pb2.NotifyGameBroadcast(seat=1,
            content='{"emo_id":99990007,"emo":14}').SerializeToString()))
    flow.websocket.messages.append(notification)
    addon.websocket_message(flow)
    block = basic_pb2.BaseMessage.FromString(notification.content[1:])
    assert liqi_pb2.NotifyGameBroadcast.FromString(block.data).content == '{"emo_id":99990005,"emo":14}'

"""plugin/mod.py 重构后测试：main() 字典分发路径 + 共享 handler 行为。

mod.__new__(mod) 绕过 __init__（会读写配置文件）；需要的最小状态手动注入。
"""
import struct
from types import SimpleNamespace

import pytest

import liqi_new
from plugin.mod import (
    mod,
    _NOTIFY_HANDLERS,
    _REQ_HANDLERS,
    _RES_HANDLERS,
)
from proto import basic_pb2, liqi_pb2


@pytest.fixture
def test_mod():
    """构造 mod 实例：绕过 __init__/LoadSettings，注入最小安全状态。"""
    m = mod.__new__(mod)
    m.safe = {}
    m.settings = {"config": {
        "character": 200001,
        "characters": {},
        "nickname": "",
        "star_chars": [],
        "title": 0,
        "loading_image": [],
        "emoji": False,
        "views": {},
        "views_index": 0,
        "show_server": False,
        "verified": 0,
        "anti_replace_nickname": False,
        "random_character": {"enabled": False, "pool": []},
        "safe_mode": False,
        "bianjietishi": False,
    }}
    m.max_data = {"character": [], "skin": [], "title": [], "item": [],
                  "loading_image": [], "endings": [], "emoji": {}}
    m.SaveSettings = lambda: None  # 不写盘
    return m


class TestDispatchTables:
    """分发表：所有 method_name 都指向存在的 handler，无孤儿/缺失。"""

    @pytest.mark.parametrize("table", [
        _NOTIFY_HANDLERS, _REQ_HANDLERS, _RES_HANDLERS])
    def test_all_handlers_exist(self, table):
        for handler_name in table.values():
            assert hasattr(mod, handler_name), f"缺失 handler: {handler_name}"

    def test_login_and_oauth2_share_handler(self):
        assert (_RES_HANDLERS[".lq.Lobby.login"]
                == _RES_HANDLERS[".lq.Lobby.oauth2Login"])


def _req_buf(method_name: str, data: bytes, msg_id: int = 1) -> bytes:
    blk = basic_pb2.BaseMessage()
    blk.method_name = method_name
    blk.data = data
    return b"\x02" + struct.pack("<H", msg_id) + blk.SerializeToString()


def _res_buf(msg_id: int, data: bytes) -> bytes:
    blk = basic_pb2.BaseMessage()
    blk.data = data
    return b"\x03" + struct.pack("<H", msg_id) + blk.SerializeToString()


class TestMainDispatch:
    def test_req_login_beat_records_contract(self, test_mod):
        """Req.loginBeat：记录 contract，不 modify。"""
        lp = liqi_new.LiqiProto()
        req = liqi_pb2.ReqLoginBeat()
        req.contract = "abc123"
        buf = _req_buf(".lq.Lobby.loginBeat", req.SerializeToString())
        modify, drop, msg, inject, inject_msg = test_mod.main(
            SimpleNamespace(content=buf, from_client=True), lp)
        assert test_mod.contract == "abc123"
        assert modify is False and drop is False

    def test_req_add_finished_ending_drops(self, test_mod):
        """Req.addFinishedEnding：直接 drop，不 modify。"""
        lp = liqi_new.LiqiProto()
        buf = _req_buf(".lq.Lobby.addFinishedEnding", b"")
        modify, drop, msg, inject, inject_msg = test_mod.main(
            SimpleNamespace(content=buf, from_client=True), lp)
        assert drop is True
        assert modify is False

    def test_req_change_main_character_fakes_login_beat(self, test_mod):
        """Req.changeMainCharacter：fake=True → 伪造 loginBeat 回包。"""
        lp = liqi_new.LiqiProto()
        test_mod.contract = "999"
        req = liqi_pb2.ReqChangeMainCharacter()
        req.character_id = 200002
        buf = _req_buf(".lq.Lobby.changeMainCharacter",
                       req.SerializeToString())
        modify, drop, msg, inject, inject_msg = test_mod.main(
            SimpleNamespace(content=buf, from_client=True), lp)
        assert modify is True
        # 设置已保存
        assert test_mod.settings["config"]["character"] == 200002
        # 回包是 loginBeat
        blk = basic_pb2.BaseMessage()
        blk.ParseFromString(msg[3:])
        assert blk.method_name == ".lq.Lobby.loginBeat"
        beat = liqi_pb2.ReqLoginBeat()
        beat.ParseFromString(blk.data)
        assert beat.contract == "999"

    def test_req_unknown_method_passthrough(self, test_mod):
        """未注册的 Req 方法：不 modify 不 drop，原样放行。"""
        lp = liqi_new.LiqiProto()
        buf = _req_buf(".lq.Lobby.unknownMethod", b"\x01\x02\x03")
        modify, drop, msg, inject, inject_msg = test_mod.main(
            SimpleNamespace(content=buf, from_client=True), lp)
        assert modify is False and drop is False

    def test_res_requires_prior_req(self, test_mod):
        """Res 无对应 Req：assert 失败（防错序/伪造消息）。"""
        lp = liqi_new.LiqiProto()
        buf = _res_buf(42, b"\x00")
        with pytest.raises(AssertionError):
            test_mod.main(SimpleNamespace(content=buf, from_client=False), lp)

    def test_res_fetch_title_list_modifies(self, test_mod):
        """Res.fetchTitleList：modify=True，称号列表被替换。

        res_type 由 liqi_proto.parse() 登记（addons 层职责），测试先用
        lp.parse 处理 Req 占位，再走 mod.main 处理 Res。
        """
        lp = liqi_new.LiqiProto()
        test_mod.max_data["title"] = [101, 102, 103]
        # 用 lp.parse 处理 Req，登记 res_type
        req = liqi_pb2.ReqCommon()
        req_buf = _req_buf(".lq.Lobby.fetchTitleList",
                           req.SerializeToString())
        lp.parse(SimpleNamespace(content=req_buf, from_client=True))
        res = liqi_pb2.ResTitleList()
        res.title_list.extend([1, 2])
        buf = _res_buf(1, res.SerializeToString())
        modify, drop, msg, inject, inject_msg = test_mod.main(
            SimpleNamespace(content=buf, from_client=False), lp)
        assert modify is True
        blk = basic_pb2.BaseMessage()
        blk.ParseFromString(msg[3:])
        out = liqi_pb2.ResTitleList()
        out.ParseFromString(blk.data)
        assert list(out.title_list) == [101, 102, 103]

    def test_notify_account_update_drops_when_character(self, test_mod):
        """NotifyAccountUpdate 带 character 更新：drop 掉，不转发给客户端。"""
        lp = liqi_new.LiqiProto()
        n = liqi_pb2.NotifyAccountUpdate()
        n.update.character.characters.add().charid = 200001
        blk = basic_pb2.BaseMessage()
        blk.method_name = ".lq.NotifyAccountUpdate"
        blk.data = n.SerializeToString()
        buf = b"\x01" + blk.SerializeToString()
        modify, drop, msg, inject, inject_msg = test_mod.main(
            SimpleNamespace(content=buf, from_client=False), lp)
        assert drop is True

    def test_notify_unknown_passthrough(self, test_mod):
        """未注册的 Notify：不处理。"""
        lp = liqi_new.LiqiProto()
        blk = basic_pb2.BaseMessage()
        blk.method_name = ".lq.NotifySomethingUnknown"
        buf = b"\x01" + blk.SerializeToString()
        modify, drop, msg, inject, inject_msg = test_mod.main(
            SimpleNamespace(content=buf, from_client=False), lp)
        assert modify is False and drop is False

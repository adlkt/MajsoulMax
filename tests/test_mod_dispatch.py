"""plugin/mod.py 重构后测试：main() 字典分发路径 + 共享 handler 行为。

mod.__new__(mod) 绕过 __init__（会读写配置文件）；需要的最小状态手动注入。
"""
import struct
from types import SimpleNamespace

import pytest

import liqi_new
from plugin.mod import (
    _NOTIFY_HANDLERS,
    _REQ_HANDLERS,
    _RES_HANDLERS,
    mod,
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
        result = test_mod.main(
            SimpleNamespace(content=buf, from_client=True), lp)
        assert test_mod.contract == "abc123"
        assert result.modify is False and result.drop is False

    def test_req_add_finished_ending_drops(self, test_mod):
        """Req.addFinishedEnding：直接 drop，不 modify。"""
        lp = liqi_new.LiqiProto()
        buf = _req_buf(".lq.Lobby.addFinishedEnding", b"")
        result = test_mod.main(
            SimpleNamespace(content=buf, from_client=True), lp)
        assert result.drop is True
        assert result.modify is False

    def test_req_change_main_character_fakes_login_beat(self, test_mod):
        """Req.changeMainCharacter：fake=True → 伪造 loginBeat 回包。"""
        lp = liqi_new.LiqiProto()
        test_mod.contract = "999"
        req = liqi_pb2.ReqChangeMainCharacter()
        req.character_id = 200002
        buf = _req_buf(".lq.Lobby.changeMainCharacter",
                       req.SerializeToString())
        result = test_mod.main(
            SimpleNamespace(content=buf, from_client=True), lp)
        assert result.modify is True
        # 设置已保存
        assert test_mod.settings["config"]["character"] == 200002
        # 回包是 loginBeat
        blk = basic_pb2.BaseMessage()
        blk.ParseFromString(result.content[3:])
        assert blk.method_name == ".lq.Lobby.loginBeat"
        beat = liqi_pb2.ReqLoginBeat()
        beat.ParseFromString(blk.data)
        assert beat.contract == "999"

    def test_req_unknown_method_passthrough(self, test_mod):
        """未注册的 Req 方法：不 modify 不 drop，原样放行。"""
        lp = liqi_new.LiqiProto()
        buf = _req_buf(".lq.Lobby.unknownMethod", b"\x01\x02\x03")
        result = test_mod.main(
            SimpleNamespace(content=buf, from_client=True), lp)
        assert result.modify is False and result.drop is False

    def test_res_requires_prior_req(self, test_mod):
        """无对应请求的响应应明确报错。"""
        lp = liqi_new.LiqiProto()
        buf = _res_buf(42, b"\x00")
        with pytest.raises(ValueError, match="没有对应请求"):
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
        result = test_mod.main(
            SimpleNamespace(content=buf, from_client=False), lp)
        assert result.modify is True
        blk = basic_pb2.BaseMessage()
        blk.ParseFromString(result.content[3:])
        out = liqi_pb2.ResTitleList()
        out.ParseFromString(blk.data)
        assert list(out.title_list) == [101, 102, 103]

    def test_req_save_common_views_persists_name(self, test_mod):
        """Req.saveCommonViews：分组名 name 必须持久化到 settings。"""
        test_mod.settings["config"]["views"] = {}
        test_mod.contract = "abc"
        req = liqi_pb2.ReqSaveCommonViews()
        req.save_index = 2
        req.is_use = 1
        req.name = "kake"
        v = req.views.add()
        v.slot = 1
        v.item_id = 308011
        v.type = 0
        buf = _req_buf(".lq.Lobby.saveCommonViews", req.SerializeToString())
        test_mod.main(SimpleNamespace(content=buf, from_client=True),
                      liqi_new.LiqiProto())
        saved = test_mod.settings["config"]["views"][2]
        assert saved["name"] == "kake"
        assert saved["values"][0]["item_id"] == 308011
        assert test_mod.settings["config"]["views_index"] == 2

    def test_res_fetch_all_common_views_writes_name(self, test_mod):
        """Res.fetchAllCommonViews：回包 views 必须带分组名 name，否则客户端显示默认数字。"""
        test_mod.settings["config"]["views"] = {
            0: {"name": "akag", "values": [{"slot": 1, "item_id": 308011, "type": 0}]},
            1: {"name": "sao", "values": []},
            2: {"name": "", "values": []},
        }
        test_mod.settings["config"]["views_index"] = 0
        lp = liqi_new.LiqiProto()
        # 登记 fetchAllCommonViews 的 res_type（addons 层职责，测试手动登记）
        req_buf = _req_buf(".lq.Lobby.fetchAllCommonViews",
                           liqi_pb2.ReqCommon().SerializeToString())
        lp.parse(SimpleNamespace(content=req_buf, from_client=True))
        buf = _res_buf(1, liqi_pb2.ResAllcommonViews().SerializeToString())
        result = test_mod.main(
            SimpleNamespace(content=buf, from_client=False), lp)
        assert result.modify is True
        blk = basic_pb2.BaseMessage()
        blk.ParseFromString(result.content[3:])
        out = liqi_pb2.ResAllcommonViews()
        out.ParseFromString(blk.data)
        names = {v.index: v.name for v in out.views}
        assert names == {0: "akag", 1: "sao", 2: ""}
        assert list(out.views[0].values)[0].item_id == 308011

    def test_notify_account_update_drops_when_character(self, test_mod):
        """NotifyAccountUpdate 带 character 更新：drop 掉，不转发给客户端。"""
        lp = liqi_new.LiqiProto()
        n = liqi_pb2.NotifyAccountUpdate()
        n.update.character.characters.add().charid = 200001
        blk = basic_pb2.BaseMessage()
        blk.method_name = ".lq.NotifyAccountUpdate"
        blk.data = n.SerializeToString()
        buf = b"\x01" + blk.SerializeToString()
        result = test_mod.main(
            SimpleNamespace(content=buf, from_client=False), lp)
        assert result.drop is True

    def test_notify_unknown_passthrough(self, test_mod):
        """未注册的 Notify：不处理。"""
        lp = liqi_new.LiqiProto()
        blk = basic_pb2.BaseMessage()
        blk.method_name = ".lq.NotifySomethingUnknown"
        buf = b"\x01" + blk.SerializeToString()
        result = test_mod.main(
            SimpleNamespace(content=buf, from_client=False), lp)
        assert result.modify is False and result.drop is False

    def test_res_auth_game_injects_self_views(self, test_mod):
        """Res.authGame 完整链路：自己玩家注入 + 随机装扮抽候选 + slot5 头像框。"""
        test_mod.safe = {"account_id": 123}
        test_mod.settings["config"].update({
            "character": 200001,
            "characters": {200001: 400101},
            "views": {0: {"name": "", "values": [
                {"slot": 1, "item_id": 308011, "type": 0},
                {"slot": 5, "item_id_list": [500, 501], "type": 1},
            ]}},
            "views_index": 0,
        })
        lp = liqi_new.LiqiProto()
        # 登记 authGame 的 res_type（addons 层职责，测试手动登记）
        req_buf = _req_buf(".lq.FastTest.authGame",
                           liqi_pb2.ReqAuthGame().SerializeToString())
        lp.parse(SimpleNamespace(content=req_buf, from_client=True))
        res = liqi_pb2.ResAuthGame()
        p = res.players.add()
        p.account_id = 123
        p.nickname = "orig"
        buf = _res_buf(1, res.SerializeToString())

        result = test_mod.main(
            SimpleNamespace(content=buf, from_client=False), lp)

        assert result.modify is True
        blk = basic_pb2.BaseMessage()
        blk.ParseFromString(result.content[3:])
        out = liqi_pb2.ResAuthGame()
        out.ParseFromString(blk.data)
        own = out.players[0]
        assert own.character.charid == 200001
        assert own.avatar_id == 400101
        assert own.nickname == "orig"  # 未配 nickname 时保留原值
        # 固定装扮 + 随机装扮（抽候选之一）+ 头像框 = 随机项
        assert own.views[0].item_id == 308011
        assert own.views[1].item_id in (500, 501)
        assert list(own.views[1].item_id_list) == [], "候选列表不下发"
        assert own.avatar_frame in (500, 501)


class TestNotifyGameFinishRewardV2:
    """NotifyGameFinishRewardV2：依赖 safe['characters']/['main_character_id']，
    未登录（safe 未填充）时不能 KeyError（与 room_player_update 同款守卫）。"""

    def test_not_logged_in_does_not_crash(self, test_mod):
        test_mod.safe = {}  # 未登录：safe 无 characters/main_character_id
        n = liqi_pb2.NotifyGameFinishRewardV2()
        blk = basic_pb2.BaseMessage()
        blk.method_name = ".lq.NotifyGameFinishRewardV2"
        blk.data = n.SerializeToString()

        result = test_mod._notify_game_finish_reward_v2(blk)

        assert result.modify is False and result.drop is False and result.data is None

    def test_logged_in_updates_main_character(self, test_mod):
        """已登录：主角色经验/等级被回填为满级、加 0 经验。"""
        test_mod.safe = {
            "main_character_id": 200001,
            "characters": [liqi_pb2.Character(charid=200001)],
        }
        n = liqi_pb2.NotifyGameFinishRewardV2()
        n.main_character.level = 3
        n.main_character.exp = 100
        blk = basic_pb2.BaseMessage()
        blk.method_name = ".lq.NotifyGameFinishRewardV2"
        blk.data = n.SerializeToString()

        result = test_mod._notify_game_finish_reward_v2(blk)

        assert result.modify is True
        assert result.data.main_character.level == 5
        assert result.data.main_character.exp == 0
        assert result.data.main_character.add == 0


class TestApplyViewSlots:
    """_apply_view_slots：本地装扮配置 → ViewSlot，随机装扮现场抽 item_id。"""

    def test_fixed_item(self, test_mod):
        """type=0 固定装扮：直接填 item_id，候选列表为空。"""
        views = liqi_pb2.ResAuthGame().players.add().views
        frame = test_mod._apply_view_slots(views, [
            {"slot": 1, "item_id": 308011, "type": 0},
        ])
        assert len(views) == 1
        assert views[0].slot == 1
        assert views[0].item_id == 308011
        assert list(views[0].item_id_list) == []
        assert frame is None

    def test_random_item_drawn_from_pool(self, test_mod):
        """type=1 随机装扮：现场抽一个 item_id，候选列表不下发。"""
        views = liqi_pb2.ResAuthGame().players.add().views
        frame = test_mod._apply_view_slots(views, [
            {"slot": 5, "item_id_list": [100, 200, 300], "type": 1},
        ])
        assert views[0].item_id in (100, 200, 300)
        assert list(views[0].item_id_list) == []
        assert frame in (100, 200, 300)

    def test_missing_slot_key_guard(self, test_mod):
        """view 缺 slot 键不 KeyError（防御本地配置手改坏）。"""
        views = liqi_pb2.ResAuthGame().players.add().views
        test_mod._apply_view_slots(views, [{"item_id": 1, "type": 0}])
        assert views[0].slot == 0


class TestApplySelfPlayer:
    """_apply_self_player：自己玩家角色/皮肤/昵称/称号/装扮注入（4 个 handler 共用）。"""

    def _player(self):
        return liqi_pb2.ResAuthGame().players.add()

    def test_injects_self_profile(self, test_mod):
        test_mod.settings["config"].update({
            "character": 200001,
            "characters": {200001: 400101},
            "nickname": "wjy",
            "title": 5,
            "verified": 2,
            "views_index": 0,
            "views": {0: {"name": "", "values": [
                {"slot": 1, "item_id": 308011, "type": 0}]}},
        })
        p = self._player()
        frame = test_mod._apply_self_player(p, p.views)
        assert p.character.charid == 200001
        assert p.avatar_id == 400101
        assert p.character.skin == 400101
        assert p.nickname == "wjy"
        assert p.title == 5
        assert p.verified == 2
        assert p.views[0].item_id == 308011
        assert frame is None

    def test_random_character_pool(self, test_mod):
        test_mod.settings["config"].update({
            "character": 200001,
            "characters": {200001: 400101},
            "random_character": {"enabled": True, "pool": [
                {"character_id": 200041, "skin_id": 400501}]},
            "views": {0: {"name": "", "values": []}},
            "views_index": 0,
        })
        p = self._player()
        test_mod._apply_self_player(p, p.views)
        assert p.character.charid == 200041
        assert p.avatar_id == 400501

    def test_slot5_returns_frame(self, test_mod):
        test_mod.settings["config"].update({
            "character": 200001,
            "characters": {200001: 400101},
            "views": {0: {"name": "", "values": [
                {"slot": 5, "item_id": 308099, "type": 0}]}},
            "views_index": 0,
        })
        p = self._player()
        frame = test_mod._apply_self_player(p, p.views)
        assert frame == 308099

    def test_views_mounted_on_character_container(self, test_mod):
        """views 挂载位置由调用方传入（character.views 而非 player.views）。"""
        test_mod.settings["config"].update({
            "character": 200001,
            "characters": {200001: 400101},
            "views": {0: {"name": "", "values": [
                {"slot": 1, "item_id": 308011, "type": 0}]}},
            "views_index": 0,
        })
        p = liqi_pb2.ResCreateRoom().room.persons.add()
        test_mod._apply_self_player(p, p.character.views)
        assert p.character.views[0].item_id == 308011
        assert len(p.views) == 0  # player 顶层 views 未被误填

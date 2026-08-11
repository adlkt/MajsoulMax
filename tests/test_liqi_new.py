"""liqi_new 解析层测试：to_dict 版本兼容 + LiqiProto.parse 消息闭环。"""
import struct
from types import SimpleNamespace

import pytest
from google.protobuf.json_format import MessageToDict

import liqi_new
from proto import basic_pb2, liqi_pb2


class TestToDict:
    """to_dict 是 protobuf 版本兼容封装，必须在当前版本（7.x）与旧版参数路径都能工作。"""

    def test_current_version_works(self):
        """当前 protobuf（7.x，always_print 路径）应正常输出，且包含无 presence 的默认值字段。"""
        req = liqi_pb2.ReqAuthGame()
        req.account_id = 123
        req.token = "abc"  # 普通字段
        d = liqi_new.to_dict(req)
        assert isinstance(d, dict)
        assert d["account_id"] == 123
        assert d["token"] == "abc"

    def test_legacy_param_path(self, monkeypatch):
        """旧版 protobuf（<=4.x）路径：including 参数可用 → 走 try 分支。

        当前环境是 protobuf 7.x，真实执行只走 except 分支；这里 mock 旧版
        行为验证 try 分支仍工作（在旧版 protobuf 环境下依赖不回归）。
        """
        def fake_legacy(proto_obj, **kwargs):
            assert "including_default_value_fields" in kwargs
            assert "always_print_fields_with_no_presence" not in kwargs
            return {"account_id": 7}

        monkeypatch.setattr(liqi_new, "MessageToDict", fake_legacy)
        req = liqi_pb2.ReqAuthGame()
        req.account_id = 7
        assert liqi_new.to_dict(req) == {"account_id": 7}

    def test_new_param_fallback(self, monkeypatch):
        """新版 protobuf（5.x+）路径：including 参数移除抛 TypeError → 走 except 分支。"""
        def fake_new(proto_obj, **kwargs):
            if "including_default_value_fields" in kwargs:
                raise TypeError("including_default_value_fields was removed")
            assert "always_print_fields_with_no_presence" in kwargs
            return {"account_id": 8}

        monkeypatch.setattr(liqi_new, "MessageToDict", fake_new)
        req = liqi_pb2.ReqAuthGame()
        req.account_id = 8
        assert liqi_new.to_dict(req) == {"account_id": 8}

    def test_preserves_proto_field_names(self):
        """preserving_proto_field_name=True 应保持下划线命名而非 camelCase。"""
        req = liqi_pb2.ReqAuthGame()
        req.game_uuid = "uuid-1"
        d = liqi_new.to_dict(req)
        assert "game_uuid" in d
        assert "gameUuid" not in d


def _base_message(method_name: str = "", data: bytes = b"") -> bytes:
    """构造并序列化一个 BaseMessage（method_name + data）。"""
    m = basic_pb2.BaseMessage()
    m.method_name = method_name
    m.data = data
    return m.SerializeToString()


class TestLiqiProtoParse:
    """parse 的 Req/Res 闭环：模拟真实 WS 帧字节流。"""

    def _parse(self, buf: bytes, from_client: bool = True):
        lp = liqi_new.LiqiProto()
        flow_msg = SimpleNamespace(content=buf, from_client=from_client)
        return lp.parse(flow_msg)

    def test_req_then_res_roundtrip(self):
        """Req → Res 闭环：req 登记 res_type，res 匹配后弹出，method 与 data 正确。"""
        lp = liqi_new.LiqiProto()

        # Req: 帧头 0x02 + msg_id(小端2字节) + BaseMessage(method_name, data)
        req_payload = liqi_pb2.ReqAuthGame()
        req_payload.account_id = 888
        req_payload.token = "tok"
        msg_id = 5
        req_buf = b"\x02" + struct.pack("<H", msg_id) + _base_message(
            ".lq.FastTest.authGame", req_payload.SerializeToString())
        r = lp.parse(SimpleNamespace(content=req_buf, from_client=True))
        assert r["id"] == msg_id
        assert r["type"] == liqi_new.MsgType.Req
        assert r["method"] == ".lq.FastTest.authGame"
        assert r["data"]["account_id"] == 888
        assert r["data"]["token"] == "tok"
        assert msg_id in lp.res_type  # req 已登记，等 res

        # Res: 帧头 0x03 + 相同 msg_id + BaseMessage(仅 data，method_name 为空)
        res_payload = liqi_pb2.ResAuthGame()
        res_payload.error.code = 0  # error 是嵌套 Error message
        res_buf = b"\x03" + struct.pack("<H", msg_id) + _base_message(
            "", res_payload.SerializeToString())
        r2 = lp.parse(SimpleNamespace(content=res_buf, from_client=False))
        assert r2["id"] == msg_id
        assert r2["type"] == liqi_new.MsgType.Res
        assert r2["method"] == ".lq.FastTest.authGame"  # 回填 req 的 method
        assert r2["data"]["error"]["code"] == 0
        assert msg_id not in lp.res_type  # res 已消费

    def test_notify_parses(self):
        """Notify 消息：帧头 0x01 + BaseMessage(method_name, data)。"""
        lp = liqi_new.LiqiProto()
        notify = liqi_pb2.NotifyAccountLevelChange()
        notify.origin.id = 1  # origin/final 是嵌套 AccountLevel message
        notify.final.id = 3
        notify.type = 2
        buf = b"\x01" + _base_message(".lq.NotifyAccountLevelChange",
                                      notify.SerializeToString())
        r = lp.parse(SimpleNamespace(content=buf, from_client=False))
        assert r["type"] == liqi_new.MsgType.Notify
        assert r["method"] == ".lq.NotifyAccountLevelChange"
        assert r["data"]["origin"]["id"] == 1
        assert r["data"]["final"]["id"] == 3
        assert r["data"]["type"] == 2

    def test_res_without_req_raises(self):
        """孤儿 Res（无对应 Req）：assert msg_id in res_type 应失败（防错误流序）。"""
        lp = liqi_new.LiqiProto()
        res_payload = liqi_pb2.ResAuthGame()
        buf = b"\x03" + struct.pack("<H", 99) + _base_message(
            "", res_payload.SerializeToString())
        with pytest.raises(AssertionError):
            lp.parse(SimpleNamespace(content=buf, from_client=False))

    def test_msg_id_reuse_raises(self):
        """同一 msg_id 重复 Req：assert msg_id not in res_type 应失败。"""
        lp = liqi_new.LiqiProto()
        req_payload = liqi_pb2.ReqAuthGame()
        buf = b"\x02" + struct.pack("<H", 3) + _base_message(
            ".lq.FastTest.authGame", req_payload.SerializeToString())
        lp.parse(SimpleNamespace(content=buf, from_client=True))
        with pytest.raises(AssertionError):
            lp.parse(SimpleNamespace(content=buf, from_client=True))

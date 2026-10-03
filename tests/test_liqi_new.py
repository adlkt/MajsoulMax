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

    @pytest.mark.parametrize('parameter', [
        'including_default_value_fields', 'always_print_fields_with_no_presence'])
    def test_parameter_detected_once(self, monkeypatch, parameter):
        from inspect import Parameter, Signature

        calls = []
        def converter(proto_obj, **kwargs):
            assert kwargs == {'preserving_proto_field_name': True, parameter: True}
            calls.append(proto_obj)
            return {'account_id': 7}

        converter.__signature__ = Signature([
            Parameter('proto_obj', Parameter.POSITIONAL_OR_KEYWORD),
            Parameter(parameter, Parameter.KEYWORD_ONLY, default=False)])
        original_signature = liqi_new.signature
        detections = []
        def detect(function):
            detections.append(function)
            return original_signature(function)

        monkeypatch.setattr(liqi_new, 'signature', detect)
        monkeypatch.setattr(liqi_new, 'MessageToDict', converter)
        req = liqi_pb2.ReqAuthGame(account_id=7)
        assert liqi_new.to_dict(req) == {'account_id': 7}
        assert liqi_new.to_dict(req) == {'account_id': 7}
        assert len(calls) == 2
        assert detections == [converter]

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
        """孤儿响应明确报错，不依赖可被优化模式移除的 assert。"""
        lp = liqi_new.LiqiProto()
        res_payload = liqi_pb2.ResAuthGame()
        buf = b"\x03" + struct.pack("<H", 99) + _base_message(
            "", res_payload.SerializeToString())
        with pytest.raises(ValueError, match="没有对应请求"):
            lp.parse(SimpleNamespace(content=buf, from_client=False))

    def test_msg_id_reuse_overwrites(self):
        """同一 msg_id 重复 Req：覆盖写 res_type（重连后窗口循环复用是合法场景）。"""
        lp = liqi_new.LiqiProto()
        req_payload = liqi_pb2.ReqAuthGame()
        buf = b"\x02" + struct.pack("<H", 3) + _base_message(
            ".lq.FastTest.authGame", req_payload.SerializeToString())
        lp.parse(SimpleNamespace(content=buf, from_client=True))
        # 复用同一 msg_id 发另一个 method：不抛异常，登记覆盖为最新
        buf2 = b"\x02" + struct.pack("<H", 3) + _base_message(
            ".lq.Lobby.fetchBagInfo", req_payload.SerializeToString())
        r = lp.parse(SimpleNamespace(content=buf2, from_client=True))
        assert r["method"] == ".lq.Lobby.fetchBagInfo"
        assert lp.res_type[3][0] == ".lq.Lobby.fetchBagInfo"


@pytest.mark.parametrize('content', [b'', b'\x02', b'\x02\x01', b'\x03', b'\x03\x01', b'\x00', b'\xff'])
def test_invalid_header_does_not_change_state(content):
    lp = liqi_new.LiqiProto()
    lp.res_type[42] = ('.lq.Lobby.loginBeat', liqi_pb2.ResCommon)
    before = lp.res_type.copy()
    with pytest.raises(ValueError):
        lp.parse(SimpleNamespace(content=content, from_client=True))
    assert lp.res_type == before
    assert lp.tot == 0


@pytest.mark.parametrize('kind,from_client', [(b'\x02', False), (b'\x03', True)])
def test_wrong_direction_rejected(kind, from_client):
    lp = liqi_new.LiqiProto()
    with pytest.raises(ValueError, match='方向错误'):
        lp.parse(SimpleNamespace(content=kind + b'\x01\x00', from_client=from_client))
    assert lp.res_type == {}


def test_response_with_method_rejected_without_consuming_request():
    lp = liqi_new.LiqiProto()
    lp.res_type[1] = ('.lq.Lobby.loginBeat', liqi_pb2.ResCommon)
    bad = b'\x03\x01\x00' + _base_message('.lq.Lobby.loginBeat')
    with pytest.raises(ValueError, match='方法名'):
        lp.parse(SimpleNamespace(content=bad, from_client=False))
    assert 1 in lp.res_type


def test_malformed_response_keeps_request_for_valid_response():
    from google.protobuf.message import DecodeError

    lp = liqi_new.LiqiProto()
    lp.res_type[65535] = ('.lq.Lobby.loginBeat', liqi_pb2.ResCommon)
    prefix = b'\x03\xff\xff'
    with pytest.raises(DecodeError):
        lp.parse(SimpleNamespace(content=prefix + _base_message(data=b'\xff'), from_client=False))
    assert lp.tot == 0
    assert 65535 in lp.res_type
    result = lp.parse(SimpleNamespace(content=prefix + _base_message(), from_client=False))
    assert result['id'] == 65535
    assert result['method'] == '.lq.Lobby.loginBeat'
    assert lp.res_type == {}


def test_response_conversion_failure_keeps_request(monkeypatch):
    lp = liqi_new.LiqiProto()
    lp.res_type[1] = ('.lq.Lobby.loginBeat', liqi_pb2.ResCommon)
    original = liqi_new.to_dict

    def fail_conversion(message):
        raise ValueError('conversion failed')

    monkeypatch.setattr(liqi_new, 'to_dict', fail_conversion)
    response = SimpleNamespace(content=b'\x03\x01\x00' + _base_message(), from_client=False)
    with pytest.raises(ValueError, match='conversion failed'):
        lp.parse(response)
    assert 1 in lp.res_type
    monkeypatch.setattr(liqi_new, 'to_dict', original)
    lp.parse(response)
    assert lp.res_type == {}


def test_type_prefix_removed_exactly(monkeypatch):
    lp = liqi_new.LiqiProto()
    lp.rpc_map = {'.lq.Test.call': {'req': '.lq.qRequest', 'resp': '.lq.lResponse'}}
    monkeypatch.setattr(liqi_pb2, 'qRequest', liqi_pb2.ReqCommon, raising=False)
    monkeypatch.setattr(liqi_pb2, 'lResponse', liqi_pb2.ResCommon, raising=False)
    req = b'\x02\x01\x00' + _base_message('.lq.Test.call')
    lp.parse(SimpleNamespace(content=req, from_client=True))
    assert lp.res_type[1] == ('.lq.Test.call', liqi_pb2.ResCommon)
    lp.parse(SimpleNamespace(content=b'\x03\x01\x00' + _base_message(), from_client=False))
    assert lp.res_type == {}


def test_invalid_reused_request_keeps_previous_match():
    from google.protobuf.message import DecodeError

    lp = liqi_new.LiqiProto()
    lp.res_type[1] = ('.lq.Lobby.loginBeat', liqi_pb2.ResCommon)
    bad = b'\x02\x01\x00' + _base_message('.lq.FastTest.authGame', b'\xff')
    with pytest.raises(DecodeError):
        lp.parse(SimpleNamespace(content=bad, from_client=True))
    assert lp.res_type[1] == ('.lq.Lobby.loginBeat', liqi_pb2.ResCommon)

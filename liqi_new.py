# 捕获websocket数据并解析雀魂"动作"语义为Json
import base64
import json
from enum import Enum
from functools import lru_cache
from inspect import signature
from pathlib import Path
from struct import unpack
from types import MappingProxyType

from google.protobuf.json_format import MessageToDict

from proto import basic_pb2, liqi_pb2

BASE_DIR = Path(__file__).resolve().parent


@lru_cache(maxsize=1)
def _default_fields_parameter(converter):
    """每个 protobuf 转换函数只检测一次参数，兼容旧版和新版。"""
    parameters = signature(converter).parameters
    if 'always_print_fields_with_no_presence' in parameters:
        return 'always_print_fields_with_no_presence'
    return 'including_default_value_fields'


def to_dict(proto_obj):
    return MessageToDict(
        proto_obj, preserving_proto_field_name=True,
        **{_default_fields_parameter(MessageToDict): True})


def load_rpc_map():
    """加载只读 RPC 映射；启动后各连接复用，连接状态仍各自保存。"""
    with open(BASE_DIR / 'proto' / 'liqi.json', encoding='utf-8') as f:
        mapping = json.load(f)
    return MappingProxyType({method: MappingProxyType(types) for method, types in mapping.items()})


class MsgType(Enum):
    Notify = 1
    Req = 2
    Res = 3


def parse_frame(flow_msg):
    """校验帧头与方向，供改包和完整协议解析使用。"""
    buf = flow_msg.content
    if not buf:
        raise ValueError("空协议帧")
    msg_type = MsgType(buf[0])
    header_size = 1 if msg_type == MsgType.Notify else 3
    if len(buf) < header_size:
        raise ValueError("协议帧头不完整")
    if msg_type == MsgType.Req and not flow_msg.from_client:
        raise ValueError("请求帧方向错误")
    if msg_type == MsgType.Res and flow_msg.from_client:
        raise ValueError("响应帧方向错误")
    msg_id = None if msg_type == MsgType.Notify else unpack('<H', buf[1:3])[0]
    block = basic_pb2.BaseMessage.FromString(buf[header_size:])
    if msg_type == MsgType.Res and block.method_name:
        raise ValueError("响应帧不能包含方法名")
    return msg_type, msg_id, block


def _message_class(type_name):
    if not type_name.startswith('.lq.'):
        raise ValueError("协议类型必须位于 .lq 命名空间")
    return getattr(liqi_pb2, type_name.removeprefix('.lq.'))


class LiqiProto:
    def __init__(self, rpc_map=None):
        # 解析一局的WS消息队列
        self.tot = 0  # 当前总共解析的包数量
        # 16 位请求编号 -> (方法名, 响应类型)，与连接生命周期一致
        self.res_type = {}  # int -> (method_name,pb2obj)
        self.rpc_map = load_rpc_map() if rpc_map is None else rpc_map

    def parse(self, flow_msg):
        msg_type, msg_id, msg_block = parse_frame(flow_msg)
        if msg_type == MsgType.Notify:
            method_name = msg_block.method_name
            proto_obj = _message_class(method_name).FromString(msg_block.data)
            dict_obj = to_dict(proto_obj)
            if method_name == '.lq.ActionPrototype':
                action = base64.b64decode(dict_obj['data'], validate=True)
                action_obj = getattr(liqi_pb2, dict_obj['name']).FromString(decode(action))
                dict_obj['data'] = to_dict(action_obj)
            msg_id = self.tot
        elif msg_type == MsgType.Req:
            method_name = msg_block.method_name
            rpc = self.rpc_map[method_name]
            proto_obj = _message_class(rpc['req']).FromString(msg_block.data)
            dict_obj = to_dict(proto_obj)
            response_class = _message_class(rpc['resp'])
            # 编号循环复用是合法行为；只有解析成功才覆盖旧匹配。
            self.res_type[msg_id] = (method_name, response_class)
        else:
            if msg_id not in self.res_type:
                raise ValueError("响应帧没有对应请求")
            method_name, response_class = self.res_type[msg_id]
            proto_obj = response_class.FromString(msg_block.data)
            dict_obj = to_dict(proto_obj)
            # 畸形回包或转换失败不应提前消耗请求匹配。
            del self.res_type[msg_id]
        self.tot += 1
        return {'id': msg_id, 'type': msg_type, 'method': method_name, 'data': dict_obj}


def decode(data: bytes):
    keys = [0x84, 0x5e, 0x4e, 0x42, 0x39, 0xa2, 0x1f, 0x60, 0x1c]
    data = bytearray(data)
    k = len(keys)
    d = len(data)
    for i, j in enumerate(data):
        u = (23 ^ d) + 5 * i + keys[i % k] & 255
        data[i] ^= u
    return bytes(data)

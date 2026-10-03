from base64 import b64decode
from copy import deepcopy
from pathlib import Path
from queue import Empty, Full, Queue
from threading import Thread

import requests
from loguru import logger
from ruamel.yaml import YAML

import liqi_new
from proto import liqi_pb2 as pb

from plugin.storage import save_yaml

BASE_DIR = Path(__file__).resolve().parent.parent


class helper:
    def __init__(self, queue_size: int = 128):
        if queue_size <= 0:
            raise ValueError("helper queue_size 必须大于 0")
        self.yaml = YAML()
        self.LoadSettings()
        self.method = [
            ".lq.Lobby.oauth2Login",
            ".lq.Lobby.fetchFriendList",
            ".lq.FastTest.authGame",
            ".lq.NotifyPlayerLoadGameReady",
            ".lq.ActionPrototype",
            ".lq.Lobby.fetchGameRecordList",
            ".lq.FastTest.syncGame",
            ".lq.Lobby.login"
        ]  # 需要发送给小助手的method
        self.action = [
            "ActionNewRound",
            "ActionDealTile",
            "ActionAnGangAddGang",
            "ActionChiPengGang",
            "ActionNoTile",
            "ActionHule",
            "ActionBaBei",
            "ActionLiuJu",
            "ActionUnveilTile",
            "ActionHuleXueZhanMid",
            "ActionGangResult",
            "ActionRevealTile",
            "ActionChangeTile",
            "ActionSelectGap",
            "ActionLiqi",
            "ActionDiscardTile",
            "ActionHuleXueZhanEnd",
            "ActionNewCard",
            "ActionGangResultEnd"
        ]  # '.lq.ActionPrototype'中，需要发送给小助手的action
        self._queue = Queue(maxsize=queue_size)
        self._worker = None
        self._closed = False
        logger.success('已载入helper')

    def LoadSettings(self):
        self.settings = self.yaml.load('''\
config:
  api_url: 'https://localhost:12121/' # 小助手的地址
''')

        try:
            with open(BASE_DIR / 'config' / 'settings.helper.yaml', 'r', encoding='utf8') as f:
                self.settings.update(self.yaml.load(f))
        except FileNotFoundError:
            logger.warning(
                '未检测到helper配置文件，已生成默认配置，如需自定义helper配置请手动修改 ./config/settings.helper.yaml')
            self.SaveSettings()

    def SaveSettings(self):
        save_yaml(BASE_DIR / 'config' / 'settings.helper.yaml', self.settings, self.yaml)

    def _enqueue(self, messages):
        """一条游戏事件及其补发消息作为一批入队，保证顺序且不等待网络。"""
        if self._closed:
            return
        try:
            self._queue.put_nowait(deepcopy(messages))
        except Full:
            logger.warning("[helper] 发送队列已满，跳过当前事件；小助手可能缺少牌局数据")
            return
        if self._worker is None:
            self._worker = Thread(target=self._send_loop, name="majsoul-helper", daemon=True)
            self._worker.start()

    def _send_loop(self):
        while True:
            messages = self._queue.get()
            try:
                if messages is None:
                    return
                for data in messages:
                    if self._closed:
                        break
                    try:
                        self._post(data)
                    except Exception as e:
                        logger.warning(f"[helper] 发送异常，跳过当前消息：{e}")
            finally:
                self._queue.task_done()

    def close(self):
        """停止接收，丢弃待发送事件；正在进行的请求由超时结束，不阻塞代理退出。"""
        if self._closed:
            return
        self._closed = True
        if self._worker is None:
            return
        while True:
            try:
                self._queue.get_nowait()
                self._queue.task_done()
            except Empty:
                break
        self._queue.put_nowait(None)

    def _post(self, data):
        """后台发送并校验状态；请求失败只警告，不中断后续消息。"""
        try:
            response = requests.post(
                self.settings['config']['api_url'],
                json=data, verify=False, timeout=3,
            )
            response.raise_for_status()
            logger.success('[helper] 消息已发送')
        except requests.RequestException as e:
            logger.warning(f"[helper] 发送失败（小助手不可达？）：{e}")

    def main(self, result):
        if self._closed:
            return
        if result['method'] in self.method:
            if result['method'] == '.lq.ActionPrototype':
                if result['data']['name'] in self.action:
                    data = deepcopy(result['data']['data'])
                    if result['data']['name'] == 'ActionNewRound':
                        # 雀魂弃用了md5改用sha256，但没有该字段会导致小助手无法解析牌局，也不能留空
                        # 所以干脆发一个假的，反正也用不到
                        data['md5'] = data['sha256'][:32]
                else:
                    return
            elif result['method'] == '.lq.FastTest.syncGame':  # 重新进入对局时
                actions = []
                for item in result['data']['game_restore']['actions']:
                    if item['data'] == '':
                        actions.append({'name': item['name'], 'data': {}})
                    else:
                        b64 = b64decode(item['data'])
                        action_proto_obj = getattr(
                            pb, item['name']).FromString(b64)
                        action_dict_obj = liqi_new.to_dict(action_proto_obj)
                        if item['name'] == 'ActionNewRound':
                            # 这里也是假md5，理由同上
                            action_dict_obj['md5'] = action_dict_obj['sha256'][:32]
                        actions.append(
                            {'name': item['name'], 'data': action_dict_obj})
                data = {'sync_game_actions': actions}
            else:
                data = result['data']
            messages = [data]
            if 'liqi' in data:  # 与主消息在同一批中按顺序补发立直消息。
                messages.append(data['liqi'])
            self._enqueue(messages)

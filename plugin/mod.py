import random
from pathlib import Path

from google.protobuf import json_format
from loguru import logger
from ruamel.yaml import YAML

import liqi_new
from plugin.results import HandlerResult, ModResult
from plugin.emoji import remap_content, unlocked_mapping
from proto import basic_pb2, liqi_pb2

from plugin.storage import save_yaml

BASE_DIR = Path(__file__).resolve().parent.parent


class mod:
    def __init__(self,version):
        self.version = version
        self.safe = {}
        # loginBeat 之前若收到 fake 类 Req（如换角色），main() 会伪造
        # ReqLoginBeat 保活包；先给空串兜底，防 AttributeError
        self.contract = ''
        self.yaml = YAML()
        self.max_data = {}
        self.LoadSettings()
        logger.success('已载入mod')

    def for_connection(self):
        """复用本地配置和解锁数据，每个连接独立保存账号快照与保活凭证。"""
        plugin = type(self).__new__(type(self))
        plugin.version = self.version
        plugin.yaml = self.yaml
        plugin.settings = self.settings
        plugin.max_data = self.max_data
        plugin.safe = {}
        plugin.contract = ''
        return plugin

    def LoadSettings(self):
        self.settings = self.yaml.load('''\
# 需要自定义的配置主要集中在这里，大多数无需修改，在游戏内设置即可更新
config:
  character: 200001  # 当前看板娘
  characters: {}  # 各角色使用的皮肤
  nickname: '' # 自定义你的名字
  star_chars: [] # 星标角色
  other_sort: [] # 其他角色排序
  bianjietishi: false # 强制启用便捷提示，用于部分场没有宝牌指示、和牌指示等
  title: 0  # 当前使用的称号
  loading_image: [] # 加载CG
  emoji: false # 不建议开启，用于解锁角色全部emoji，如果你本身角色没有额外表情，在对局中却发送额外表情，这种行为相当于自爆卡车
  views: # 各装扮页的装扮（新格式：{index: {name, values}}，老 list 格式启动时自动迁移）
    0: {name: '', values: []}
    1: {name: '', values: []}
    2: {name: '', values: []}
    3: {name: '', values: []}
    4: {name: '', values: []}
    5: {name: '', values: []}
    6: {name: '', values: []}
    7: {name: '', values: []}
    8: {name: '', values: []}
    9: {name: '', values: []}
  views_index: 0 # 正在使用的装扮页
  show_server: true # 显示其他玩家所在服务器
  verified: 0 # 标识设置，0为无标识，1为主播标识，2为Pro标识，显示在名字后面
  anti_replace_nickname: true # 禁止将外服玩家设为默认名称，特殊时期必备
  random_character: # 对局随机角色皮肤
    enabled: false
    pool: []
  safe_mode: false  # 地铁模式，将除自己外所有人变成一姬初始形象，防止被误认为玩黄油。电脑形象请打开“游戏设置-偏好-电脑形象-一姬的初始形象”选项。
''')
        try:
            with open(BASE_DIR / 'config' / 'settings.mod.yaml', 'r', encoding='utf-8') as f:
                temp = YAML()
                localyaml = temp.load(f)
                for i in self.settings.keys():
                    if i in localyaml.keys():
                        for j in self.settings[i]:
                            if j in localyaml[i].keys():
                                self.settings[i][j] = localyaml[i][j]
        except FileNotFoundError:
            logger.warning(
                '未检测到mod配置文件，已生成默认配置，如需自定义mod配置请手动修改 ./config/settings.mod.yaml')
        self._migrate_views_format()
        self.load_max_data()
        self.SaveSettings()

    def _migrate_views_format(self):
        """迁移 views 结构：老格式 {i: [slots]} → 新格式 {i: {name, values}}，并补齐缺失装扮页。

        - 老格式不存 name，迁移时补空串
        - 新格式加载时保留已存 name
        - 缺失的装扮页（0-9 之外或未定义）补空结构，防止 views_index 越界 KeyError
        """
        new_views = {}
        for idx in range(10):
            v = self.settings['config']['views'].get(idx, [])
            if isinstance(v, dict):
                new_views[idx] = {
                    'name': v.get('name', ''),
                    'values': v.get('values', []),
                }
            else:
                new_views[idx] = {'name': '', 'values': list(v)}
        self.settings['config']['views'] = new_views

    def _current_views(self) -> dict:
        """当前装扮页。views_index 来自服务端 useCommonView.index，无范围保证，
        越界时回退 0 页（_migrate_views_format 保证 0 页存在），防 KeyError。"""
        views = self.settings['config']['views']
        idx = self.settings['config']['views_index']
        return views.get(idx) or views.get(0) or {'name': '', 'values': []}

    def SaveSettings(self):
        save_yaml(BASE_DIR / 'config' / 'settings.mod.yaml', self.settings, self.yaml)

    def load_max_data(self):
        with open(BASE_DIR / 'config' / 'max_data.yaml', 'r', encoding='utf-8') as f:
            yaml = YAML()
            self.max_data = yaml.load(f)

    # ============ 消息分发 ============
    # 每个 case 一个 handler，按 method_name 查字典分发；main() 只做帧解析 + 收尾序列化。

    def main(self, message, liqi_proto) -> ModResult:
        buf = message.content
        msg_type, msg_id, msg_block = liqi_new.parse_frame(message)
        if msg_type == liqi_new.MsgType.Notify:
            handler_name = _NOTIFY_HANDLERS.get(msg_block.method_name)
        elif msg_type == liqi_new.MsgType.Req:
            handler_name = _REQ_HANDLERS.get(msg_block.method_name)
        else:
            if msg_id not in liqi_proto.res_type:
                raise ValueError("响应帧没有对应请求")
            method_name, _ = liqi_proto.res_type[msg_id]
            handler_name = _RES_HANDLERS.get(method_name)

        result = getattr(self, handler_name)(msg_block) if handler_name else HandlerResult()
        data = result.data
        if result.fake:
            # 将本地装扮请求替换为保活请求，避免向服务端提交解锁数据。
            data = liqi_pb2.ReqLoginBeat(contract=self.contract)
            msg_block.method_name = '.lq.Lobby.loginBeat'
        content = None
        if result.modify or result.fake:
            msg_block.data = data.SerializeToString()
            prefix = buf[:1] if msg_type == liqi_new.MsgType.Notify else buf[:3]
            content = prefix + msg_block.SerializeToString()
        return ModResult(content=content, drop=result.drop,
                         injected_content=result.injected_content)

    # ============ Notify handlers ============

    def _notify_account_update(self, msg_block):
        drop = False
        data = liqi_pb2.NotifyAccountUpdate()
        data.ParseFromString(msg_block.data)
        if data.update.HasField('character'):
            drop = True
        return HandlerResult(drop=drop, data=data)

    def _notify_room_player_update(self, msg_block):
        if not self.safe.get('account_id'):
            # 未登录（safe 未填充）前收到房间更新，无法识别自己，跳过修改
            return HandlerResult()
        modify = True
        data = liqi_pb2.NotifyRoomPlayerUpdate()
        data.ParseFromString(msg_block.data)
        for p in data.player_list:
            if p.account_id == self.safe['account_id']:
                p.avatar_id = self.settings['config']['characters'][self.settings['config']['character']]
                if self.settings['config']['nickname'] != '':
                    p.nickname = self.settings['config']['nickname']
                p.title = self.settings['config']['title']

            if self.settings['config']['show_server']:
                p.nickname = self._prepend_zone(p.account_id, p.nickname)
            if self.settings['config']['safe_mode']:
                p.character.charid=200001
                p.character.skin=400101
                p.avatar_id= 400101
        return HandlerResult(modify=modify, data=data)

    def _req_broadcast_in_game(self, msg_block):
        mapping = self.safe.get('emoji_mapping')
        if not mapping:
            return HandlerResult()
        data = liqi_pb2.ReqBroadcastInGame.FromString(msg_block.data)
        content = remap_content(data.content, mapping['send'])
        if content is None:
            return HandlerResult()
        data.content = content
        return HandlerResult(modify=True, data=data)

    def _notify_game_broadcast(self, msg_block):
        mapping = self.safe.get('emoji_mapping')
        if not mapping or mapping['seat'] is None:
            return HandlerResult()
        data = liqi_pb2.NotifyGameBroadcast.FromString(msg_block.data)
        if data.seat != mapping['seat']:
            return HandlerResult()
        content = remap_content(data.content, mapping['receive'])
        if content is None:
            return HandlerResult()
        data.content = content
        return HandlerResult(modify=True, data=data)

    def _notify_game_finish_reward_v2(self, msg_block):
        if not self.safe.get('main_character_id'):
            # 未登录（safe 未填充）前收到结算通知，无法定位主角色，跳过修改
            return HandlerResult()
        modify = True
        data = liqi_pb2.NotifyGameFinishRewardV2()
        data.ParseFromString(msg_block.data)
        for c in self.safe['characters']:
            if c.charid == self.safe['main_character_id']:
                c.exp = data.main_character.exp
                c.level = data.main_character.level
                break
        data.main_character.add = 0
        data.main_character.exp = 0
        data.main_character.level = 5
        return HandlerResult(modify=modify, data=data)

    def _notify_custom_contest_system_msg(self, msg_block):
        if not self.settings['config']['show_server']:
            return HandlerResult()
        modify = True
        data = liqi_pb2.NotifyCustomContestSystemMsg()
        data.ParseFromString(msg_block.data)
        for p in data.game_start.players:
            p.nickname = self._prepend_zone(p.account_id, p.nickname)
        return HandlerResult(modify=modify, data=data)

    # ============ Req handlers ============

    def _req_change_main_character(self, msg_block):
        fake = True
        data = liqi_pb2.ReqChangeMainCharacter()
        data.ParseFromString(msg_block.data)
        self.settings['config']['character'] = data.character_id
        self.SaveSettings()
        return HandlerResult(fake=fake, data=data)

    def _req_change_character_skin(self, msg_block):
        fake = True
        inject = True
        data = liqi_pb2.ReqChangeCharacterSkin()
        data.ParseFromString(msg_block.data)
        # 保存角色和皮肤
        self.settings['config']['characters'][data.character_id] = data.skin
        self.SaveSettings()
        update_data = liqi_pb2.NotifyAccountUpdate()
        character = update_data.update.character.characters.add()
        character.charid = data.character_id
        character.skin = data.skin
        character.exp = 0
        character.is_upgraded = True
        character.level = 5
        character.rewarded_level.extend([1, 2, 3, 4, 5])
        if self.settings['config']['emoji']:
            character.extra_emoji.extend(
                self.max_data['emoji'][character.charid])

        basic = basic_pb2.BaseMessage()
        basic.method_name = '.lq.NotifyAccountUpdate'
        basic.data = update_data.SerializeToString()
        inject_msg = b'\x01' + basic.SerializeToString()
        return HandlerResult(fake=fake, injected_content=inject_msg if inject else None, data=data)

    def _req_add_finished_ending(self, msg_block):
        return HandlerResult(drop=True)

    def _req_update_character_sort(self, msg_block):
        fake = True
        data = liqi_pb2.ReqUpdateCharacterSort()
        data.ParseFromString(msg_block.data)
        # 保存星标角色 + 其他角色排序
        self.settings['config']['star_chars'] = list(data.sort)
        self.settings['config']['other_sort'] = list(data.other_sort)
        self.SaveSettings()
        return HandlerResult(fake=fake, data=data)

    def _req_use_title(self, msg_block):
        fake = True
        data = liqi_pb2.ReqUseTitle()
        data.ParseFromString(msg_block.data)
        self.settings['config']['title'] = data.title
        self.SaveSettings()
        return HandlerResult(fake=fake, data=data)

    def _req_set_loading_image(self, msg_block):
        fake = True
        data = liqi_pb2.ReqSetLoadingImage()
        data.ParseFromString(msg_block.data)
        self.settings['config']['loading_image'] = list(
            data.images)
        self.SaveSettings()
        return HandlerResult(fake=fake, data=data)

    def _req_save_common_views(self, msg_block):
        fake = True
        modify = True
        data = liqi_pb2.ReqSaveCommonViews()
        data.ParseFromString(msg_block.data)
        for view in data.views:
            if view.type == 0 and view.item_id_list != []:
                view.ClearField('item_id_list')
            elif view.type == 1 and view.item_id != 0:
                view.ClearField('item_id')

        views = liqi_new.to_dict(data)
        self.settings['config']['views'][views['save_index']] = {
            'name': views.get('name', ''),
            'values': views['views'],
        }
        if views['is_use'] == 1:
            self.settings['config']['views_index'] = views['save_index']
        self.SaveSettings()
        return HandlerResult(modify=modify, fake=fake, data=data)

    def _req_use_common_view(self, msg_block):
        data = liqi_pb2.ReqUseCommonView()
        data.ParseFromString(msg_block.data)
        self.settings['config']['views_index'] = data.index
        self.SaveSettings()
        return HandlerResult(data=data)

    def _req_auth_game(self, msg_block):
        # 对局使用独立 WebSocket，不能依赖大厅连接的登录状态。
        data = liqi_pb2.ReqAuthGame.FromString(msg_block.data)
        self.safe['account_id'] = data.account_id
        self.safe.pop('emoji_mapping', None)
        return HandlerResult(data=data)

    def _req_login_beat(self, msg_block):
        data = liqi_pb2.ReqLoginBeat()
        data.ParseFromString(msg_block.data)
        self.contract = data.contract
        return HandlerResult(data=data)

    def _req_read_announcement(self, msg_block):
        fake = False
        data = liqi_pb2.ReqReadAnnouncement()
        data.ParseFromString(msg_block.data)
        if data.announcement_id == 666666:
            fake = True
        return HandlerResult(fake=fake, data=data)

    def _req_receive_character_rewards(self, msg_block):
        return HandlerResult(fake=True)

    def _req_set_random_character(self, msg_block):
        fake = True
        data = liqi_pb2.ReqRandomCharacter()
        data.ParseFromString(msg_block.data)
        self.settings['config']['random_character']['enabled'] = data.enabled
        self.settings['config']['random_character']['pool'] = liqi_new.to_dict(data)['pool']
        self.SaveSettings()
        return HandlerResult(fake=fake, data=data)

    # ============ 共享 helper（fetchCharacterInfo / fetchInfo 等复用） ============

    def _default_skin_id(self, character_id: int) -> int:
        """角色 id → 默认皮肤 id（如 200001 → 400101）。"""
        return int('40' + str(character_id)[4:] + '01')

    def _prepend_zone(self, account_id: int, nickname: str) -> str:
        """昵称前加服务器标识（[CN]/[JP]/[EN]/[??]）。"""
        return self.get_zone_id(account_id) + nickname

    def _fill_characters(self, target):
        """补全角色数据：注入全部角色/皮肤/称号/结局。

        target 需含 characters/skins/main_character_id/character_sort/
        other_character_sort/hidden_characters/finished_endings/rewarded_endings
        字段（ResCharacterInfo 或 ResFetchInfo.character_info 均可）。
        """
        target.ClearField('characters')
        character_keys = self.settings['config']['characters'].keys()
        for c in self.max_data['character']:
            character = target.characters.add()
            character.charid = c
            character.exp = 0
            character.is_upgraded = True
            character.level = 5
            character.rewarded_level.extend([1, 2, 3, 4, 5])
            if c not in character_keys:
                self.settings['config']['characters'][c] = self._default_skin_id(c)
            character.skin = self.settings['config']['characters'][c]
            if self.settings['config']['emoji']:
                character.extra_emoji.extend(
                    self.max_data['emoji'][character.charid])
        target.ClearField('skins')
        target.skins.extend(self.max_data['skin'])
        target.main_character_id = self.settings['config']['character']
        target.ClearField('character_sort')
        target.character_sort.extend(
            self.settings['config']['star_chars'])
        target.ClearField('other_character_sort')
        target.other_character_sort.extend(
            self.settings['config']['other_sort'])
        target.ClearField('hidden_characters')
        target.ClearField('finished_endings')
        target.ClearField('rewarded_endings')
        target.finished_endings.extend(
            self.max_data['endings'])
        target.rewarded_endings.extend(
            self.max_data['endings'])

    def _fill_bag(self, bag):
        """补全背包：保留原物品（不在 max_data 中）+ 注入 max_data 物品与加载插图。"""
        bag.ClearField('items')
        # 添加原背包物品
        for item in self.safe['items']:
            if item.item_id not in self.max_data['item']:
                myitem = bag.items.add()
                myitem.item_id = item.item_id
                myitem.stack = item.stack
        # 添加其他物品
        for id in self.max_data['item']:
            item = bag.items.add()
            item.item_id = id
            item.stack = 1
        # 添加加载插图
        for id in self.max_data['loading_image']:
            item = bag.items.add()
            item.item_id = id
            item.stack = 1

    def _fill_common_views(self, target):
        """补全装扮页：写入 views_index 与各装扮页配置（含分组名 name）。"""
        target.use = self.settings['config']['views_index']
        target.ClearField('views')
        for i, view in self.settings['config']['views'].items():
            views = target.views.add()
            json_format.ParseDict(
                {'index': i, 'name': view.get('name', ''),
                 'values': view['values']}, views)

    def _fill_title_list(self, target):
        """补全称号列表。"""
        target.ClearField('title_list')
        target.title_list.extend(self.max_data['title'])

    def _apply_view_slots(self, views_field, view_dicts) -> int | None:
        """把本地装扮配置写入 ViewSlot 列表；type=1 随机装扮现场抽一个 item_id。

        返回 slot==5 的 item_id（头像框），无则 None。随机候选列表（item_id_list）
        不下发给客户端——客户端只看 item_id 决定外观，下发整个列表会导致随机失效。
        """
        frame = None
        for view in view_dicts:
            slot = views_field.add()
            slot.slot = view.get('slot', 0)
            if view.get('type') == 0:
                slot.item_id = view.get('item_id', 0)
            else:
                slot.item_id = random.choice(view['item_id_list'])
            if slot.slot == 5:
                frame = slot.item_id
        return frame

    def _apply_self_player(self, player, views_field) -> int | None:
        """注入自己的角色/皮肤/昵称/称号/装扮（createRoom/authGame/fetchRoom/fetchGameRecord 共用）。

        views_field 为 views 挂载容器（如 character.views / player.views / account.views），
        需由调用方先 ClearField（各 handler 的挂载位置不同）。
        返回 slot5 装扮 item_id（头像框），无则 None。
        """
        cfg = self.settings['config']
        if cfg['random_character']['enabled'] and cfg['random_character']['pool']:
            item = random.choice(cfg['random_character']['pool'])
            player.character.charid = item['character_id']
            player.avatar_id = player.character.skin = item['skin_id']
        else:
            player.character.charid = cfg['character']
            player.avatar_id = player.character.skin = cfg['characters'][cfg['character']]
        if cfg['emoji']:
            player.character.extra_emoji.extend(
                self.max_data['emoji'][player.character.charid])
        if cfg['nickname'] != '':
            player.nickname = cfg['nickname']
        player.title = cfg['title']
        frame = self._apply_view_slots(
            views_field, self._current_views()['values'])
        player.verified = cfg['verified']
        return frame

    # ============ Res handlers ============

    def _res_fetch_character_info(self, msg_block):
        modify = True
        data = liqi_pb2.ResCharacterInfo()
        data.ParseFromString(msg_block.data)
        self.safe['main_character_id'] = data.main_character_id
        self.safe['characters'] = data.characters
        self._fill_characters(data)
        self.SaveSettings()  # _fill_characters 可能新增默认皮肤映射，需持久化
        return HandlerResult(modify=modify, data=data)

    def _res_login(self, msg_block):
        modify = True
        data = liqi_pb2.ResLogin()
        data.ParseFromString(msg_block.data)
        self.safe['account_id'] = data.account_id
        self.safe['nickname'] = data.account.nickname
        self.safe['skin'] = data.account.avatar_id
        self.safe['title'] = data.account.title
        self.safe['loading_image'] = data.account.loading_image
        if self.settings['config']['character'] in self.settings['config']['characters'].keys():
            data.account.avatar_id = self.settings['config'][
                'characters'][self.settings['config']['character']]
        else:
            data.account.avatar_id = self._default_skin_id(
                self.settings['config']['character'])
        for view in self._current_views()['values']:
            if view.get('slot') == 5:
                data.account.avatar_frame = view.get('item_id', 0)
        if self.settings['config']['nickname'] != '':
            data.account.nickname = self.settings['config']['nickname']
        data.account.title = self.settings['config']['title']
        data.account.ClearField('loading_image')
        data.account.loading_image.extend(
            self.settings['config']['loading_image'])
        data.account.verified = self.settings['config']['verified']
        return HandlerResult(modify=modify, data=data)

    def _res_create_room(self, msg_block):
        modify = True
        data = liqi_pb2.ResCreateRoom()
        data.ParseFromString(msg_block.data)
        for p in data.room.persons:
            p.character.is_upgraded = True
            p.character.level = 5
            p.character.rewarded_level.extend([1, 2, 3, 4, 5])
            p.character.exp = 0
            if p.account_id == self.safe['account_id']:
                p.character.ClearField('views')
                frame = self._apply_self_player(p, p.character.views)
                if frame is not None:
                    p.avatar_frame = frame
            if self.settings['config']['show_server']:
                p.nickname = self._prepend_zone(p.account_id, p.nickname)
        return HandlerResult(modify=modify, data=data)

    def _res_auth_game(self, msg_block):
        modify = True
        data = liqi_pb2.ResAuthGame()
        data.ParseFromString(msg_block.data)
        self.safe.pop('emoji_mapping', None)
        if data.HasField('error') and data.error.code:
            return HandlerResult()
        own_id = self.safe.get('account_id')
        own_seat = list(data.seat_list).index(own_id) if own_id in data.seat_list else None
        if self.settings['config']['bianjietishi']:
            data.game_config.mode.detail_rule.bianjietishi = True
            if data.game_config.meta.mode_id == 15 :
                data.game_config.meta.mode_id =11
            elif data.game_config.meta.mode_id == 16:
                data.game_config.meta.mode_id =12
            elif data.game_config.meta.mode_id == 25:
                data.game_config.meta.mode_id =23
            elif data.game_config.meta.mode_id == 26:
                data.game_config.meta.mode_id =24

        for p in data.players:
            p.character.level = 5
            p.character.is_upgraded = True
            p.character.rewarded_level.extend([1, 2, 3, 4, 5])
            p.character.exp = 0
            if p.account_id == self.safe['account_id']:
                server_character = p.character.charid
                server_emojis = list(p.character.enabled_emoji)
                p.ClearField('views')
                frame = self._apply_self_player(p, p.views)
                if frame is not None:
                    p.avatar_frame = frame

            if self.settings['config']['show_server']:
                p.nickname = self._prepend_zone(p.account_id, p.nickname)
            if self.settings['config']['safe_mode']:
                p.character.charid=200001
                p.character.skin=400101
                p.avatar_id= 400101
            if p.account_id == own_id:
                send, receive, extra_indices = unlocked_mapping(
                    server_character, p.character.charid, server_emojis)
                self.safe['emoji_mapping'] = {
                    'server': server_character,
                    'local': p.character.charid,
                    'seat': own_seat,
                    'send': send,
                    'receive': receive,
                }
                # Only advertise emojis with a server-unlocked counterpart.
                p.character.ClearField('enabled_emoji')
                p.character.enabled_emoji.extend(send)
                p.character.ClearField('extra_emoji')
                p.character.extra_emoji.extend(extra_indices)
        for p in data.robots:
            p.character.level = 5
            p.character.is_upgraded = True
            p.character.rewarded_level.extend([1, 2, 3, 4, 5])
            p.character.exp = 0
            if self.settings['config']['safe_mode']:
                p.character.charid=200001
                p.character.skin=400101
                p.avatar_id= 400101
        return HandlerResult(modify=modify, data=data)

    def _res_fetch_account_info(self, msg_block):
        modify = False
        data = liqi_pb2.ResAccountInfo()
        data.ParseFromString(msg_block.data)
        if data.account.account_id == self.safe['account_id']:
            modify = True
            data.account.avatar_id = self.settings['config'][
                'characters'][self.settings['config']['character']]
            for view in self._current_views()['values']:
                if view.get('slot') == 5:
                    data.account.avatar_frame = view.get('item_id', 0)
            if self.settings['config']['nickname'] != '':
                data.account.nickname = self.settings['config']['nickname']
            data.account.title = self.settings['config']['title']
            data.account.ClearField('loading_image')
            data.account.loading_image.extend(
                self.settings['config']['loading_image'])
            data.account.verified = self.settings['config']['verified']
        return HandlerResult(modify=modify, data=data)

    def _res_fetch_title_list(self, msg_block):
        modify = True
        data = liqi_pb2.ResTitleList()
        data.ParseFromString(msg_block.data)
        self._fill_title_list(data)
        return HandlerResult(modify=modify, data=data)

    def _res_fetch_room(self, msg_block):
        modify = True
        data = liqi_pb2.ResSelfRoom()
        data.ParseFromString(msg_block.data)
        for p in data.room.persons:
            p.character.is_upgraded = True
            p.character.level = 5
            p.character.rewarded_level.extend([1, 2, 3, 4, 5])
            p.character.exp = 0
            if p.account_id == self.safe['account_id']:
                p.character.ClearField('views')
                frame = self._apply_self_player(p, p.character.views)
                if frame is not None:
                    p.avatar_frame = frame
            if self.settings['config']['show_server']:
                p.nickname = self._prepend_zone(p.account_id, p.nickname)
        return HandlerResult(modify=modify, data=data)

    def _res_fetch_bag_info(self, msg_block):
        modify = True
        data = liqi_pb2.ResBagInfo()
        data.ParseFromString(msg_block.data)
        self.safe['items'] = data.bag.items
        self._fill_bag(data.bag)
        return HandlerResult(modify=modify, data=data)

    def _res_fetch_all_common_views(self, msg_block):
        modify = True
        data = liqi_pb2.ResAllcommonViews()
        # 先解析服务器返回（本地 views 全量覆盖，但保留字段契约，防未来依赖时炸）
        data.ParseFromString(msg_block.data)
        self._fill_common_views(data)
        return HandlerResult(modify=modify, data=data)

    def _res_fetch_info(self, msg_block):
        modify = True
        data = liqi_pb2.ResFetchInfo()
        data.ParseFromString(msg_block.data)

        # 处理角色和皮肤
        self.safe['main_character_id'] = data.character_info.main_character_id
        self.safe['characters'] = data.character_info.characters
        self._fill_characters(data.character_info)

        # 处理背包
        self.safe['items'] = data.bag_info.bag.items
        self._fill_bag(data.bag_info.bag)

        # 处理装扮
        self._fill_common_views(data.all_common_views)
        # 处理称号
        self._fill_title_list(data.title_list)
        # 处理随机角色皮肤
        data.ClearField('random_character')
        json_format.ParseDict(self.settings['config']['random_character'],data.random_character)
        self.SaveSettings()  # _fill_characters 可能新增默认皮肤映射，需持久化
        return HandlerResult(modify=modify, data=data)

    def _res_fetch_server_settings(self, msg_block):
        modify = False
        data = liqi_pb2.ResServerSettings()
        data.ParseFromString(msg_block.data)
        if self.settings['config']['anti_replace_nickname']:
            modify = True
            data.settings.nickname_setting.enable = 0
            data.settings.nickname_setting.ClearField(
                'nicknames')
        return HandlerResult(modify=modify, data=data)

    def _res_fetch_game_record(self, msg_block):
        modify = True
        data = liqi_pb2.ResGameRecord()
        data.ParseFromString(msg_block.data)
        uuid = data.head.uuid
        result = '发现读入牌谱！\n'
        for account in data.head.accounts:
            match account.seat:
                case 0:
                    result+='東: '
                case 1:
                    result+='南: '
                case 2:
                    result+='西: '
                case 3:
                    result+='北: '
            account.character.level = 5
            account.character.is_upgraded = True
            account.character.rewarded_level.extend([1, 2, 3, 4, 5])
            account.character.exp = 0
            if account.account_id == self.safe['account_id']:
                result+='（自己）'
                account.ClearField('views')
                frame = self._apply_self_player(account, account.views)
                if frame is not None:
                    account.avatar_frame = frame
            elif self.settings['config']['safe_mode']:
                account.character.charid=200001
                account.character.skin=400101
                account.avatar_id= 400101
            if self.settings['config']['show_server']:
                account.nickname = self._prepend_zone(account.account_id, account.nickname)

            result += f'{self.get_zone_id(account.account_id)}{account.nickname}\n\
账号id: {account.account_id}   加好友id: {self.encode_account_id2(account.account_id)}\n\
主视角牌谱链接: {uuid}_a{self.encode_account_id(account.account_id)}\n\
主视角牌谱链接（匿名）: {self.encodePaipuUUID(uuid)}_a{self.encode_account_id(account.account_id)}_2\n\n'

        result+='注意：只有在同一服务器才能添加好友！'
        logger.debug(result)
        return HandlerResult(modify=modify, data=data)

    def _res_fetch_random_character(self, msg_block):
        modify = True
        data = liqi_pb2.ResRandomCharacter()
        json_format.ParseDict(self.settings['config']['random_character'],data)
        return HandlerResult(modify=modify, data=data)

    # ============ 纯函数（编码/区域） ============

    def get_zone_id(self, id:int):
        i = id >> 23
        if 0 <= i <= 6:
            return '[C' + b'\xef\xbb\xbf'.decode('utf-8') + 'N]'
        elif 7 <= i <= 12:
            return '[JP]'
        elif 13 <= i <= 15:
            return '[EN]'
        else:
            return '[??]'

    def encodePaipuUUID(self,uuid) :
        result = ''
        code0=ord('0')
        codeA=ord('a')
        for i,char in enumerate(uuid):
            code = ord(char)
            temp = -1
            if code >= code0 and code0+ 10 > code :
                temp = code - code0
            elif code >= codeA and codeA + 26 > code:
                temp= code - codeA + 10
            if -1 != temp:
                temp = (temp + 17 + i) % 36
                if 10 > temp:
                    result += chr(temp + code0)
                else:
                    result +=  chr(temp + codeA - 10)

            else:
                result += char
        return result

    def encode_account_id(self,id:int) :
        return int((7 * id + 1117113 ^ 86216345) + 1358437)

    def encode_account_id2(self,p:int):
        p = 6139246 ^ p
        H = 67108863
        S = p & ~H
        Z = p & H
        for i in range(5):
            Z = (511 & Z) << 17 | Z >> 9
        return int(Z + S + 1e7)


# ============ 分发表：method_name -> handler 方法名 ============
# main() 按消息类型查对应字典，所有 handler 统一返回 HandlerResult。

_NOTIFY_HANDLERS = {
    '.lq.NotifyGameBroadcast': '_notify_game_broadcast',
    '.lq.NotifyAccountUpdate': '_notify_account_update',
    '.lq.NotifyRoomPlayerUpdate': '_notify_room_player_update',
    '.lq.NotifyGameFinishRewardV2': '_notify_game_finish_reward_v2',
    '.lq.NotifyCustomContestSystemMsg': '_notify_custom_contest_system_msg',
}

_REQ_HANDLERS = {
    '.lq.FastTest.broadcastInGame': '_req_broadcast_in_game',
    '.lq.FastTest.authGame': '_req_auth_game',
    '.lq.Lobby.changeMainCharacter': '_req_change_main_character',
    '.lq.Lobby.changeCharacterSkin': '_req_change_character_skin',
    '.lq.Lobby.addFinishedEnding': '_req_add_finished_ending',
    '.lq.Lobby.updateCharacterSort': '_req_update_character_sort',
    '.lq.Lobby.useTitle': '_req_use_title',
    '.lq.Lobby.setLoadingImage': '_req_set_loading_image',
    '.lq.Lobby.saveCommonViews': '_req_save_common_views',
    '.lq.Lobby.useCommonView': '_req_use_common_view',
    '.lq.Lobby.loginBeat': '_req_login_beat',
    '.lq.Lobby.readAnnouncement': '_req_read_announcement',
    '.lq.Lobby.receiveCharacterRewards': '_req_receive_character_rewards',
    '.lq.Lobby.setRandomCharacter': '_req_set_random_character',
}

_RES_HANDLERS = {
    '.lq.Lobby.fetchCharacterInfo': '_res_fetch_character_info',
    '.lq.Lobby.login': '_res_login',
    '.lq.Lobby.oauth2Login': '_res_login',
    '.lq.Lobby.createRoom': '_res_create_room',
    '.lq.FastTest.authGame': '_res_auth_game',
    '.lq.Lobby.fetchAccountInfo': '_res_fetch_account_info',
    '.lq.Lobby.fetchTitleList': '_res_fetch_title_list',
    '.lq.Lobby.fetchRoom': '_res_fetch_room',
    '.lq.Lobby.fetchBagInfo': '_res_fetch_bag_info',
    '.lq.Lobby.fetchAllCommonViews': '_res_fetch_all_common_views',
    '.lq.Lobby.fetchInfo': '_res_fetch_info',
    '.lq.Lobby.fetchServerSettings': '_res_fetch_server_settings',
    '.lq.Lobby.fetchGameRecord': '_res_fetch_game_record',
    '.lq.Lobby.fetchRandomCharacter': '_res_fetch_random_character',
}

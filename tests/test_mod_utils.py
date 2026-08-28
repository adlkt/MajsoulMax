"""plugin/mod.py 纯函数测试：get_zone_id / encodePaipuUUID / encode_account_id(2)。

这些方法不依赖实例状态（不读 self.settings），用 mod.__new__ 绕过 __init__
（__init__ 会读写配置文件，测试环境不应触发磁盘写入）。
"""
import pytest
from ruamel.yaml import YAML

from plugin.mod import mod
from proto import liqi_pb2, basic_pb2


@pytest.fixture
def pure_mod(monkeypatch, tmp_path):
    """绕过 __init__（会 LoadSettings/SaveSettings 读写配置），仅取方法。

    SaveSettings 重定向到 tmp_path，绝不触碰真实 config/settings.mod.yaml。
    """
    m = mod.__new__(mod)
    m.yaml = YAML()
    m.settings = {"config": {}}
    target = tmp_path / "settings.mod.yaml"

    def fake_save():
        with open(target, "w", encoding="utf-8") as f:
            m.yaml.dump(m.settings, f)

    monkeypatch.setattr(m, "SaveSettings", fake_save)
    return m


class TestGetZoneId:
    def test_cn_zone(self, pure_mod):
        # id >> 23 落在 0..6 → 国际服 CN 区（注意含 BOM \ufeff，实现故意插入防混淆）
        for raw in (0, 1, 6 << 23, 3 << 23):
            assert pure_mod.get_zone_id(raw) == "[C\uFEFFN]"

    def test_jp_zone(self, pure_mod):
        for raw in (7 << 23, 9 << 23, 12 << 23):
            assert pure_mod.get_zone_id(raw) == "[JP]"

    def test_en_zone(self, pure_mod):
        for raw in (13 << 23, 15 << 23):
            assert pure_mod.get_zone_id(raw) == "[EN]"

    def test_unknown_zone(self, pure_mod):
        assert pure_mod.get_zone_id(16 << 23) == "[??]"
        assert pure_mod.get_zone_id(1 << 30) == "[??]"


class TestEncodePaipuUUID:
    """已知输入输出映射（由实现复算得到，锁定当前行为）。"""

    @pytest.mark.parametrize("uuid,expected", [
        ("0", "h"),
        ("a", "r"),
        ("z", "g"),
        ("A", "A"),   # 非 0-9/a-z 字符原样保留
        ("-", "-"),
        ("abc123", "rtvlnp"),
    ])
    def test_known_mappings(self, pure_mod, uuid, expected):
        assert pure_mod.encodePaipuUUID(uuid) == expected

    def test_empty(self, pure_mod):
        assert pure_mod.encodePaipuUUID("") == ""


class TestEncodeAccountId:
    @pytest.mark.parametrize("account_id,expected", [
        (0, 88555397),
        (1, 88555454),
        (123, 88554484),
        (999999, 91033680),
    ])
    def test_known_mappings(self, pure_mod, account_id, expected):
        assert pure_mod.encode_account_id(account_id) == expected


class TestEncodeAccountId2:
    @pytest.mark.parametrize("raw,expected", [
        (0, 57625995),
        (1, 57626123),
        (100, 57613195),
        (12345678, 25077404),
    ])
    def test_known_mappings(self, pure_mod, raw, expected):
        assert pure_mod.encode_account_id2(raw) == expected


class TestMigrateViewsFormat:
    """views 结构迁移：老格式 {i: [slots]} → 新格式 {i: {name, values}}。"""

    def test_legacy_list_to_new_dict(self, pure_mod):
        pure_mod.settings = {"config": {"views": {
            0: [{"slot": 1, "item_id": 308011}],
            1: [],
        }}}
        pure_mod._migrate_views_format()
        v = pure_mod.settings["config"]["views"]
        assert v[0] == {"name": "", "values": [{"slot": 1, "item_id": 308011}]}
        assert v[1] == {"name": "", "values": []}

    def test_new_format_keeps_name(self, pure_mod):
        pure_mod.settings = {"config": {"views": {
            2: {"name": "kake", "values": [{"slot": 1, "item_id": 308011}]},
        }}}
        pure_mod._migrate_views_format()
        v = pure_mod.settings["config"]["views"]
        assert v[2]["name"] == "kake"
        assert v[2]["values"] == [{"slot": 1, "item_id": 308011}]

    def test_missing_pages_filled(self, pure_mod):
        pure_mod.settings = {"config": {"views": {
            0: [{"slot": 1, "item_id": 308011}],
        }}}
        pure_mod._migrate_views_format()
        v = pure_mod.settings["config"]["views"]
        assert len(v) == 10, "缺失装扮页应补齐 0-9"
        assert v[0]["values"] == [{"slot": 1, "item_id": 308011}]
        assert all(v[i] == {"name": "", "values": []} for i in range(1, 10))


class TestUpdateCharacterSort:
    """角色排序闭环：Req 保存 star_chars + other_sort，Res 回填两个字段。"""

    def test_req_saves_both_sorts(self, pure_mod):
        req = liqi_pb2.ReqUpdateCharacterSort()
        req.sort.extend([200050, 200041])
        req.other_sort.extend([200001, 200002, 200003])
        block = basic_pb2.BaseMessage()
        block.data = req.SerializeToString()

        modify, drop, fake, inject, inject_msg, data = pure_mod._req_update_character_sort(block)

        assert fake is True, "updateCharacterSort 请求应被拦截（不发给服务器）"
        assert pure_mod.settings["config"]["star_chars"] == [200050, 200041]
        assert pure_mod.settings["config"]["other_sort"] == [200001, 200002, 200003]

    def test_req_without_other_sort_keeps_empty(self, pure_mod):
        """旧客户端/旧行为：other_sort 缺省时存空列表，不报错。"""
        req = liqi_pb2.ReqUpdateCharacterSort()
        req.sort.extend([200050])
        block = basic_pb2.BaseMessage()
        block.data = req.SerializeToString()

        pure_mod._req_update_character_sort(block)

        assert pure_mod.settings["config"]["star_chars"] == [200050]
        assert pure_mod.settings["config"]["other_sort"] == []

    def test_fill_characters_restores_both_sorts(self, pure_mod):
        pure_mod.max_data = {
            "character": [200001, 200002],
            "skin": [400101, 400201],
            "endings": [1001],
            "emoji": {200001: [1], 200002: [1]},
        }
        pure_mod.settings = {"config": {
            "characters": {},
            "character": 200001,
            "emoji": False,
            "star_chars": [200050, 200041],
            "other_sort": [200001, 200002],
        }}
        target = liqi_pb2.ResCharacterInfo()

        pure_mod._fill_characters(target)

        assert list(target.character_sort) == [200050, 200041]
        assert list(target.other_character_sort) == [200001, 200002]
        assert len(target.characters) == 2, "全部角色应被注入"


class TestSaveSettings:
    """SaveSettings 直写盘：不生成 .bak（2026-08-13 用户要求移除备份逻辑）。"""

    def test_writes_settings_directly(self, monkeypatch, tmp_path):
        import plugin.mod as mod_module

        m = mod_module.mod.__new__(mod_module.mod)
        m.yaml = YAML()
        m.settings = {"config": {"character": 200001}}
        config_dir = tmp_path / "config"
        config_dir.mkdir(exist_ok=True)
        target = config_dir / "settings.mod.yaml"

        monkeypatch.setattr(mod_module, "BASE_DIR", tmp_path)
        m.SaveSettings()

        assert target.exists()
        # 不再生成 .bak 备份
        bak = config_dir / "settings.mod.yaml.bak"
        assert not bak.exists(), "已移除 .bak 备份逻辑"


class TestCurrentViews:
    """_current_views：views_index 越界回退 0 页（服务端 useCommonView.index 无范围保证）。"""

    def test_valid_index(self, pure_mod):
        pure_mod.settings["config"] = {
            "views_index": 3,
            "views": {i: {"name": f"v{i}", "values": []} for i in range(10)},
        }
        assert pure_mod._current_views()["name"] == "v3"

    def test_out_of_range_falls_back_to_zero(self, pure_mod):
        pure_mod.settings["config"] = {
            "views_index": 99,
            "views": {i: {"name": f"v{i}", "values": []} for i in range(10)},
        }
        assert pure_mod._current_views()["name"] == "v0"

    def test_missing_zero_page_returns_empty(self, pure_mod):
        pure_mod.settings["config"] = {"views_index": 99, "views": {}}
        assert pure_mod._current_views() == {"name": "", "values": []}

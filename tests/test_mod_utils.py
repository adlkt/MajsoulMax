"""plugin/mod.py 纯函数测试：get_zone_id / encodePaipuUUID / encode_account_id(2)。

这些方法不依赖实例状态（不读 self.settings），用 mod.__new__ 绕过 __init__
（__init__ 会读写配置文件，测试环境不应触发磁盘写入）。
"""
import pytest
from ruamel.yaml import YAML

from plugin.mod import mod


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


class TestSaveSettings:
    """SaveSettings 备份逻辑：写盘前必须保留旧文件为 .bak（防配置丢失）。"""

    def test_creates_backup_before_overwrite(self, monkeypatch, tmp_path):
        import plugin.mod as mod_module

        m = mod_module.mod.__new__(mod_module.mod)
        m.yaml = YAML()
        m.settings = {"config": {"character": 200001}}
        config_dir = tmp_path / "config"
        config_dir.mkdir(exist_ok=True)
        target = config_dir / "settings.mod.yaml"
        target.write_text("old-content", encoding="utf-8")

        monkeypatch.setattr(mod_module, "BASE_DIR", tmp_path)
        m.SaveSettings()

        bak = config_dir / "settings.mod.yaml.bak"
        assert bak.exists(), "写盘前必须生成 .bak 备份"
        assert bak.read_text(encoding="utf-8") == "old-content"
        assert target.exists()

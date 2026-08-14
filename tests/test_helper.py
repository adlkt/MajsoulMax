"""plugin/helper.py 测试：请求健壮性（timeout + 异常隔离）。

helper.__new__ 绕过 __init__（LoadSettings 读不到配置时会 SaveSettings 写盘），
注入最小配置；requests.post 全部 mock，不做网络 I/O。
"""
import pytest
import requests
from ruamel.yaml import YAML

from plugin.helper import helper


@pytest.fixture
def test_helper(monkeypatch, tmp_path):
    h = helper.__new__(helper)
    h.yaml = YAML()
    h.settings = {"config": {"api_url": "https://localhost:12121/"}}
    h.method = [".lq.Lobby.login", ".lq.ActionPrototype"]  # 测试用到的最小集合
    h.action = ["ActionLiqi"]
    target = tmp_path / "settings.helper.yaml"

    def fake_save():
        with open(target, "w", encoding="utf-8") as f:
            h.yaml.dump(h.settings, f)

    monkeypatch.setattr(h, "SaveSettings", fake_save)
    return h


class TestPostRobustness:
    def test_post_has_timeout(self, test_helper, monkeypatch):
        """请求必须带 timeout，防止小助手地址不可达时无限挂起阻塞 addon。"""
        captured = {}

        def fake_post(url, **kwargs):
            captured["url"] = url
            captured["kwargs"] = kwargs
            raise requests.ConnectionError("connection refused")

        monkeypatch.setattr("plugin.helper.requests.post", fake_post)

        test_helper._post({"foo": "bar"})

        assert captured["url"] == "https://localhost:12121/"
        assert captured["kwargs"]["timeout"] == 3
        assert captured["kwargs"]["json"] == {"foo": "bar"}
        assert captured["kwargs"]["verify"] is False

    def test_post_error_swallowed(self, test_helper, monkeypatch):
        """小助手不可达：ConnectionError 被吞掉打 warning，不向外抛。"""
        def fake_post(*a, **k):
            raise requests.ConnectionError("connection refused")

        monkeypatch.setattr("plugin.helper.requests.post", fake_post)

        test_helper._post({"foo": "bar"})  # 不抛异常

    def test_post_timeout_error_swallowed(self, test_helper, monkeypatch):
        """请求超时同样被吞掉。"""
        def fake_post(*a, **k):
            raise requests.Timeout("timed out")

        monkeypatch.setattr("plugin.helper.requests.post", fake_post)

        test_helper._post({"foo": "bar"})  # 不抛异常

    def test_main_sends_matching_method(self, test_helper, monkeypatch):
        """main() 匹配 method 时经 _post 发送；未匹配不发送。"""
        sent = []
        monkeypatch.setattr(
            "plugin.helper.requests.post",
            lambda *a, **k: sent.append((a, k)),
        )

        test_helper.main({"method": ".lq.Lobby.login", "data": {"account": "x"}})
        assert len(sent) == 1

        test_helper.main({"method": ".lq.NotifySomething", "data": {}})
        assert len(sent) == 1  # 未匹配 method 不发送

    def test_main_liqi_repost(self, test_helper, monkeypatch):
        """data 含 liqi 键时补发立直消息。"""
        sent = []
        monkeypatch.setattr(
            "plugin.helper.requests.post",
            lambda *a, **k: sent.append((a, k)),
        )

        test_helper.main({
            "method": ".lq.ActionPrototype",
            "data": {"name": "ActionLiqi", "data": {"liqi": {"tile": 30}}},
        })

        assert len(sent) == 2  # 主消息 + liqi 补发

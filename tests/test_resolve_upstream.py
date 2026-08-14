"""上游代理检测（_detect_clash_verge / resolve_upstream）单元测试。

防回归目标：端口都未监听时必须返回 None 走直连，绝不能靠进程兜底猜端口
（clash-verge-service 常驻 helper 曾误判成 7897，把雀魂流量导向黑洞）。
"""
import pytest

import addons


@pytest.fixture(autouse=True)
def _restore_settings():
    """每个用例后还原 SETTINGS，避免用例间串味。"""
    before = addons.SETTINGS["proxy"]
    yield
    addons.SETTINGS["proxy"] = before


class _FakeConn:
    """满足 `with socket.create_connection(...)` 上下文协议的桩连接对象。"""

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def _refuse_all(address, timeout=None, source_address=None):
    raise OSError("connection refused")


def _accept_port(port):
    def _connect(address, timeout=None, source_address=None):
        if address[1] == port:
            return _FakeConn()
        raise OSError("connection refused")
    return _connect


def test_detect_returns_port_when_listening(monkeypatch):
    addons.SETTINGS["proxy"] = {"upstream": "auto"}
    monkeypatch.setattr(addons.socket, "create_connection", _accept_port(7897))
    assert addons._detect_clash_verge() == 7897


def test_detect_prefers_configured_clash_port(monkeypatch):
    addons.SETTINGS["proxy"] = {"clash_port": 7898}
    monkeypatch.setattr(addons.socket, "create_connection", _accept_port(7898))
    assert addons._detect_clash_verge() == 7898


def test_detect_returns_none_when_all_ports_refused(monkeypatch):
    # 关键防回归：即使本机有 clash-verge-service 残留进程，端口没监听也必须直连
    addons.SETTINGS["proxy"] = {"upstream": "auto"}
    monkeypatch.setattr(addons.socket, "create_connection", _refuse_all)
    assert addons._detect_clash_verge() is None


def test_resolve_upstream_auto_no_port_returns_none(monkeypatch):
    addons.SETTINGS["proxy"] = {"upstream": "auto"}
    monkeypatch.setattr(addons.socket, "create_connection", _refuse_all)
    assert addons.resolve_upstream() is None


def test_resolve_upstream_direct_returns_none():
    addons.SETTINGS["proxy"] = {"upstream": "direct"}
    assert addons.resolve_upstream() is None


def test_resolve_upstream_empty_returns_none():
    addons.SETTINGS["proxy"] = {"upstream": ""}
    assert addons.resolve_upstream() is None


def test_resolve_upstream_explicit_address_passthrough():
    addons.SETTINGS["proxy"] = {"upstream": "http://127.0.0.1:7890"}
    assert addons.resolve_upstream() == "http://127.0.0.1:7890"

"""小助手发送测试：网络隔离、顺序、有界队列和退出；所有请求均 mock。"""
from threading import Event, Thread
from types import SimpleNamespace

import pytest
import requests

from plugin.helper import helper


@pytest.fixture
def test_helper(monkeypatch):
    def load_settings(self):
        self.settings = {"config": {"api_url": "https://localhost:12121/"}}

    monkeypatch.setattr(helper, "LoadSettings", load_settings)
    h = helper(queue_size=2)
    yield h
    h.close()
    if h._worker is not None:
        h._worker.join(timeout=5)
        assert not h._worker.is_alive()


def _wait_for_queue(h):
    done = Event()
    waiter = Thread(target=lambda: (h._queue.join(), done.set()), daemon=True)
    waiter.start()
    assert done.wait(5), "helper sender did not finish queued messages"
    waiter.join()


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
            lambda *a, **k: (sent.append((a, k)), SimpleNamespace(raise_for_status=lambda: None))[1],
        )

        test_helper.main({"method": ".lq.Lobby.login", "data": {"account": "x"}})
        _wait_for_queue(test_helper)
        assert len(sent) == 1

        test_helper.main({"method": ".lq.NotifySomething", "data": {}})
        assert len(sent) == 1  # 未匹配 method 不发送

    def test_main_liqi_repost(self, test_helper, monkeypatch):
        """data 含 liqi 键时补发立直消息。"""
        sent = []
        monkeypatch.setattr(
            "plugin.helper.requests.post",
            lambda *a, **k: (sent.append((a, k)), SimpleNamespace(raise_for_status=lambda: None))[1],
        )

        test_helper.main({
            "method": ".lq.ActionPrototype",
            "data": {"name": "ActionLiqi", "data": {"liqi": {"tile": 30}}},
        })

        _wait_for_queue(test_helper)
        assert len(sent) == 2  # 主消息 + liqi 补发
        assert sent[0][1]['json'] == {'liqi': {'tile': 30}}
        assert sent[1][1]['json'] == {'tile': 30}


def test_slow_request_does_not_block_main_and_keeps_order(test_helper, monkeypatch):
    entered, release, returned = Event(), Event(), Event()
    sent = []

    def post(url, **kwargs):
        sent.append(kwargs['json'])
        entered.set()
        assert release.wait(5)
        return SimpleNamespace(raise_for_status=lambda: None)

    monkeypatch.setattr('plugin.helper.requests.post', post)
    producer = Thread(target=lambda: (
        test_helper.main({'method': '.lq.Lobby.login', 'data': {'order': 1}}),
        returned.set()))
    producer.start()
    try:
        assert entered.wait(5)
        assert returned.wait(1), 'main waited for the HTTP request'
        test_helper.main({'method': '.lq.Lobby.login', 'data': {'order': 2}})
        assert sent == [{'order': 1}]
    finally:
        release.set()
        producer.join(timeout=5)
    _wait_for_queue(test_helper)
    assert sent == [{'order': 1}, {'order': 2}]


def test_queue_full_drops_whole_event_and_uses_snapshot(test_helper, monkeypatch):
    entered, release = Event(), Event()
    sent, warnings = [], []

    def post(url, **kwargs):
        sent.append(kwargs['json'])
        entered.set()
        assert release.wait(5)
        return SimpleNamespace(raise_for_status=lambda: None)

    monkeypatch.setattr('plugin.helper.requests.post', post)
    monkeypatch.setattr('plugin.helper.logger.warning', lambda *args: warnings.append(args))
    test_helper.main({'method': '.lq.Lobby.login', 'data': {'order': 1}})
    try:
        assert entered.wait(5)
        data = {'nested': {'value': 2}}
        test_helper.main({'method': '.lq.Lobby.login', 'data': data})
        data['nested']['value'] = 999
        test_helper.main({'method': '.lq.Lobby.login', 'data': {'order': 3}})
        test_helper.main({'method': '.lq.ActionPrototype',
                          'data': {'name': 'ActionLiqi', 'data': {'liqi': {'order': 4}}}})
        assert test_helper._queue.qsize() == 2
        assert len(warnings) == 1
    finally:
        release.set()
    _wait_for_queue(test_helper)
    assert sent == [{'order': 1}, {'nested': {'value': 2}}, {'order': 3}]


def test_close_discards_pending_messages_without_waiting(test_helper, monkeypatch):
    entered, release = Event(), Event()
    sent = []

    def post(url, **kwargs):
        sent.append(kwargs['json'])
        entered.set()
        assert release.wait(5)
        return SimpleNamespace(raise_for_status=lambda: None)

    monkeypatch.setattr('plugin.helper.requests.post', post)
    test_helper.main({'method': '.lq.Lobby.login', 'data': {'order': 1}})
    try:
        assert entered.wait(5)
        test_helper.main({'method': '.lq.Lobby.login', 'data': {'order': 2}})
        test_helper.close()
        test_helper.close()
        test_helper.main({'method': '.lq.Lobby.login', 'data': {'order': 3}})
        assert test_helper._worker.is_alive()
    finally:
        release.set()
    _wait_for_queue(test_helper)
    assert sent == [{'order': 1}]


def test_http_error_does_not_stop_later_events(test_helper, monkeypatch):
    sent = []

    def post(url, **kwargs):
        sent.append(kwargs['json'])
        def check_status():
            if len(sent) == 1:
                raise requests.HTTPError('503')
        return SimpleNamespace(raise_for_status=check_status)

    monkeypatch.setattr('plugin.helper.requests.post', post)
    test_helper.main({'method': '.lq.Lobby.login', 'data': {'order': 1}})
    test_helper.main({'method': '.lq.Lobby.login', 'data': {'order': 2}})
    _wait_for_queue(test_helper)
    assert sent == [{'order': 1}, {'order': 2}]


def test_new_round_does_not_mutate_parsed_message(test_helper, monkeypatch):
    sent = []
    monkeypatch.setattr('plugin.helper.requests.post', lambda url, **kwargs: (
        sent.append(kwargs['json']), SimpleNamespace(raise_for_status=lambda: None))[1])
    result = {'method': '.lq.ActionPrototype',
              'data': {'name': 'ActionNewRound', 'data': {'sha256': 'a' * 64}}}
    test_helper.main(result)
    _wait_for_queue(test_helper)
    assert sent[0]['md5'] == 'a' * 32
    assert 'md5' not in result['data']['data']


def test_unexpected_sender_error_does_not_kill_worker(test_helper, monkeypatch):
    sent = []

    def post(url, **kwargs):
        sent.append(kwargs['json'])
        if len(sent) == 1:
            raise ValueError('invalid request payload')
        return SimpleNamespace(raise_for_status=lambda: None)

    monkeypatch.setattr('plugin.helper.requests.post', post)
    test_helper.main({'method': '.lq.Lobby.login', 'data': {'order': 1}})
    test_helper.main({'method': '.lq.Lobby.login', 'data': {'order': 2}})
    _wait_for_queue(test_helper)
    assert sent == [{'order': 1}, {'order': 2}]


@pytest.mark.parametrize('size', [0, -1])
def test_queue_must_have_positive_capacity(size):
    with pytest.raises(ValueError, match='queue_size'):
        helper(queue_size=size)

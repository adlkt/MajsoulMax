from types import SimpleNamespace

import pytest

from plugin.traffic import TrafficStats


@pytest.fixture
def stats(monkeypatch):
    now = [0.0]
    lines = []
    monkeypatch.setattr('plugin.traffic.logger.info',
                        lambda template, *args: lines.append(template.format(*args)))
    return TrafficStats(clock=lambda: now[0]), now, lines


def rpc(kind, msg_id=7):
    return {'type': SimpleNamespace(value=kind), 'id': msg_id}


def test_summary_is_throttled_and_counts_sizes(stats):
    traffic, now, lines = stats
    traffic.packet(100, True)
    traffic.packet(300, False)
    now[0] = 9
    traffic.report()
    assert lines == []
    now[0] = 10
    traffic.report()
    assert len(lines) == 1
    assert lines[0] == '延迟 -- | ↑1包 ↓1包 | 400B'
    now[0] = 30
    traffic.report()
    assert len(lines) == 1  # 空闲时无重复汇总。
    traffic.packet(50, True)
    traffic.report()
    assert lines[1] == '延迟 -- | ↑1包 ↓0包 | 50B'


def test_rtt_matches_connection_and_survives_summary(stats):
    traffic, now, lines = stats
    traffic.packet(10, True)
    traffic.rpc('first', rpc(2))
    now[0] = 0.1
    traffic.rpc('second', rpc(2))
    now[0] = 0.3
    traffic.rpc('second', rpc(3))  # 200ms，不能匹配 first 的同编号请求。
    now[0] = 10
    traffic.report()
    assert '延迟 200ms' in lines[0]
    assert ('first', 7) in traffic.pending
    now[0] = 10.5
    traffic.rpc('first', rpc(3))
    traffic.packet(10, False)
    now[0] = 20
    traffic.report()
    assert '延迟 10500ms' in lines[1]


def test_expired_unknown_and_reused_request_ids(stats):
    traffic, now, _ = stats
    traffic.rpc('first', rpc(2))
    now[0] = 61
    traffic.rpc('first', rpc(3))
    assert traffic.rtt_count == 0
    traffic.rpc('first', rpc(3, 999))
    assert traffic.rtt_count == 0
    traffic.rpc('first', rpc(2))
    now[0] = 62
    traffic.rpc('first', rpc(2))
    now[0] = 62.1
    traffic.rpc('first', rpc(3))
    assert traffic.rtt_total == pytest.approx(100)


def test_pending_requests_are_bounded_and_cleaned_up(stats):
    traffic, _, _ = stats
    traffic.max_pending = 2
    traffic.rpc('first', rpc(2, 1))
    traffic.rpc('second', rpc(2, 2))
    traffic.rpc('first', rpc(2, 3))
    assert set(traffic.pending) == {('second', 2), ('first', 3)}
    traffic.disconnect('first')
    assert set(traffic.pending) == {('second', 2)}
    traffic.packet(100, True)
    traffic.clear()
    assert not traffic.pending
    assert traffic.sent == 0

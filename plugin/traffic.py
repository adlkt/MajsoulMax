"""汇总代理观察到的 WebSocket 流量和 RPC 往返时间。"""
from time import monotonic

from loguru import logger


class TrafficStats:
    interval = 10.0
    request_timeout = 60.0
    max_pending = 4096

    def __init__(self, clock=monotonic):
        self.clock = clock
        self.started = clock()
        self.pending = {}
        self._reset()

    def _reset(self):
        self.sent = self.received = 0
        self.sent_bytes = self.received_bytes = 0
        self.rtt_count = 0
        self.rtt_total = 0.0

    def packet(self, size, from_client):
        if from_client:
            self.sent += 1
            self.sent_bytes += size
        else:
            self.received += 1
            self.received_bytes += size

    def rpc(self, connection_id, result):
        now = self.clock()
        # 插入顺序即时间顺序，过期请求和过多未响应请求都及时释放。
        while self.pending:
            key = next(iter(self.pending))
            if now - self.pending[key] <= self.request_timeout:
                break
            self.pending.pop(key)
        key = (connection_id, result['id'])
        if result['type'].value == 2:
            self.pending.pop(key, None)
            self.pending[key] = now
            if len(self.pending) > self.max_pending:
                self.pending.pop(next(iter(self.pending)))
        elif result['type'].value == 3:
            started = self.pending.pop(key, None)
            if started is not None:
                elapsed = (now - started) * 1000
                self.rtt_count += 1
                self.rtt_total += elapsed

    def disconnect(self, connection_id):
        for key in list(self.pending):
            if key[0] == connection_id:
                self.pending.pop(key)

    def report(self):
        now = self.clock()
        elapsed = now - self.started
        count = self.sent + self.received
        if elapsed < self.interval or not count:
            return
        latency = (
            f"{self.rtt_total / self.rtt_count:.0f}ms"
            if self.rtt_count else "--"
        )
        total_bytes = self.sent_bytes + self.received_bytes
        size = f"{total_bytes}B" if total_bytes < 1024 else f"{total_bytes / 1024:.1f}KiB"
        logger.info(
            "延迟 {} | ↑{}包 ↓{}包 | {}",
            latency, self.sent, self.received, size,
        )
        self.started = now
        self._reset()

    def clear(self):
        self.pending.clear()
        self.started = self.clock()
        self._reset()

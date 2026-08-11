#!/usr/bin/env python3
"""Serve majsoul.pac over HTTP for system proxy PAC support.

Chrome 对 file:// PAC 支持不稳定，必须通过 HTTP 提供：
    http://127.0.0.1:18080/majsoul.pac
"""
import sys
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path


def main() -> None:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 18080
    basedir = Path(__file__).resolve().parent

    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(basedir), **kwargs)

        def log_message(self, fmt, *args):
            pass  # 静默，不刷日志

    server = HTTPServer(("127.0.0.1", port), Handler)
    print(f"PAC 服务已启动: http://127.0.0.1:{port}/majsoul.pac", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Serve majsoul.pac over HTTP for system proxy PAC support.

Chrome 对 file:// PAC 支持不稳定，必须通过 HTTP 提供：
    http://127.0.0.1:18080/majsoul.pac
"""
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

PAC_FILE = Path(__file__).resolve().parent / "majsoul.pac"


class PacHandler(BaseHTTPRequestHandler):
    """只提供 /majsoul.pac 一个文件，不暴露项目目录或其他路径。"""

    def do_GET(self):
        # 只允许精确路径 /majsoul.pac，其他一律 404（防目录遍历/任意文件读取）
        if self.path not in ("/majsoul.pac", "/majsoul.pac/"):
            self.send_error(404, "Not Found")
            return
        body = PAC_FILE.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "application/x-ns-proxy-autoconfig")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        pass  # 静默，不刷日志


def main() -> None:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 18080
    server = HTTPServer(("127.0.0.1", port), PacHandler)
    print(f"PAC 服务已启动: http://127.0.0.1:{port}/majsoul.pac", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()

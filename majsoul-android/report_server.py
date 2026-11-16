"""
本机静态 HTTP 服务: 程序内的 WebView 通过 http://127.0.0.1:<端口>/ 看 rating_out/ 下的报告.
安卓 WebView 对 file:// 有限制, 两端统一走这里. 只监听 127.0.0.1, 只读, 不出目录.
"""
from __future__ import annotations

import functools
import pathlib
import threading
import urllib.parse
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer


class _Handler(SimpleHTTPRequestHandler):
    def log_message(self, *a) -> None:  # 不往日志里刷访问记录
        pass

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")  # 重新生成报告后刷新就能看到
        super().end_headers()


class ReportServer:
    def __init__(self, root: pathlib.Path | str) -> None:
        self.root = pathlib.Path(root).resolve()
        self.httpd: ThreadingHTTPServer | None = None

    def start(self) -> int:
        if self.httpd is None:
            self.root.mkdir(parents=True, exist_ok=True)
            handler = functools.partial(_Handler, directory=str(self.root))
            self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
            self.httpd.daemon_threads = True
            threading.Thread(target=self.httpd.serve_forever, daemon=True,
                             name="report-server").start()
        return self.httpd.server_address[1]

    def set_root(self, root: pathlib.Path | str) -> None:
        """输出目录换了: 重开服务."""
        root = pathlib.Path(root).resolve()
        if root != self.root:
            self.stop()
            self.root = root

    def url_for(self, path: pathlib.Path | str) -> str:
        """rating_out 下某个文件的网址; 不在目录里的返回 file:// 网址."""
        p = pathlib.Path(path).resolve()
        try:
            rel = p.relative_to(self.root)
        except ValueError:
            return p.as_uri()
        port = self.start()
        return f"http://127.0.0.1:{port}/" + urllib.parse.quote(rel.as_posix())

    def stop(self) -> None:
        if self.httpd is not None:
            self.httpd.shutdown()
            self.httpd.server_close()
            self.httpd = None

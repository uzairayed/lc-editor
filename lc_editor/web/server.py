from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote

from lc_editor.app import Editor

INDEX = Path(__file__).with_name("index.html")


def start_readonly_server(editor: Editor, host: str, port: int) -> None:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.path == "/" or self.path == "/index.html":
                body = INDEX.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            if self.path == "/api/timeline":
                payload = editor.timeline_get() if editor.store else {"ok": False, "timeline": None, "timeline_summary": {}}
                stills = []
                if editor.store:
                    stills = [p.name for p in sorted(editor.store.stills_dir.glob("*.jpg"))]
                payload["stills"] = stills
                body = json.dumps(payload).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            if self.path.startswith("/stills/") and editor.store:
                name = unquote(self.path.split("/stills/", 1)[1])
                dest = (editor.store.stills_dir / Path(name).name).resolve()
                if dest.is_file() and dest.is_relative_to(editor.store.stills_dir.resolve()):
                    data = dest.read_bytes()
                    self.send_response(200)
                    self.send_header("Content-Type", "image/jpeg")
                    self.send_header("Content-Length", str(len(data)))
                    self.end_headers()
                    self.wfile.write(data)
                    return
            self.send_response(404)
            self.end_headers()

        def do_POST(self) -> None:
            self.send_response(405)
            self.send_header("Allow", "GET")
            self.end_headers()

        def log_message(self, fmt: str, *args) -> None:
            return

    httpd = ThreadingHTTPServer((host, port), Handler)
    httpd.serve_forever()

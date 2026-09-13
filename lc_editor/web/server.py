from __future__ import annotations

import json
import mimetypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from lc_editor.analysis.labels import GUI_DOMAIN_TOOLS
from lc_editor.app import Editor

INDEX = Path(__file__).with_name("index.html")
DESK_JS = Path(__file__).with_name("desk.js")
DESK_CSS = Path(__file__).with_name("desk.css")

READ_TOOLS = {
    "label_queue",
    "label_get",
    "label_conflicts",
    "label_readiness",
    "media_list",
    "shots_list",
    "media_card_propose",
    "timeline_get",
    "project_get",
}
WRITE_TOOLS = {
    "shot_card_confirm",
    "labels_bulk_confirm",
    "labels_clear",
    "labels_undo",
    "media_card_confirm",
    "media_remove",
}
HTTP_TOOLS = READ_TOOLS | WRITE_TOOLS
assert WRITE_TOOLS <= set(GUI_DOMAIN_TOOLS)
assert READ_TOOLS - {"timeline_get", "project_get"} <= set(GUI_DOMAIN_TOOLS)
STATIC = {
    "/": (INDEX, "text/html; charset=utf-8"),
    "/index.html": (INDEX, "text/html; charset=utf-8"),
    "/desk.js": (DESK_JS, "text/javascript; charset=utf-8"),
    "/desk.css": (DESK_CSS, "text/css; charset=utf-8"),
}


def _local_origin(origin: str | None) -> bool:
    if not origin:
        return True
    parsed = urlparse(origin)
    host = (parsed.hostname or "").lower()
    return host in {"127.0.0.1", "localhost"}


def _safe_file(path: Path, root: Path) -> Path | None:
    try:
        dest = path.resolve()
        base = root.resolve()
    except OSError:
        return None
    if dest.is_file() and dest.is_relative_to(base):
        return dest
    return None


def _coerce_query(values: dict[str, list[str]]) -> dict:
    out: dict = {}
    for key, items in values.items():
        if not items:
            continue
        raw = items[0]
        if raw in ("true", "True"):
            out[key] = True
        elif raw in ("false", "False"):
            out[key] = False
        elif raw in ("null", "None", ""):
            out[key] = None
        else:
            try:
                out[key] = int(raw) if raw.isdigit() or (raw.startswith("-") and raw[1:].isdigit()) else float(raw) if raw.replace(".", "", 1).isdigit() else raw
            except ValueError:
                out[key] = raw
    return out


def make_handler(editor: Editor):
    class Handler(BaseHTTPRequestHandler):
        def _reject(self, code: int, allow: str | None = None) -> None:
            self.send_response(code)
            if allow:
                self.send_header("Allow", allow)
            self.end_headers()

        def _json(self, payload: dict, code: int = 200) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _bytes(self, data: bytes, content_type: str, extra: dict[str, str] | None = None) -> None:
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            for key, value in (extra or {}).items():
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(data)

        def _send_range(self, path: Path, content_type: str) -> None:
            size = path.stat().st_size
            rng = self.headers.get("Range")
            if not rng or not rng.startswith("bytes="):
                data = path.read_bytes()
                self._bytes(data, content_type, {"Accept-Ranges": "bytes"})
                return
            spec = rng.split("=", 1)[1]
            start_s, _, end_s = spec.partition("-")
            start = int(start_s) if start_s else 0
            end = int(end_s) if end_s else size - 1
            start = max(0, start)
            end = min(size - 1, end)
            if start > end:
                self._reject(416)
                return
            length = end - start + 1
            self.send_response(206)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(length))
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            self.end_headers()
            with path.open("rb") as handle:
                handle.seek(start)
                remaining = length
                while remaining:
                    chunk = handle.read(min(65536, remaining))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    remaining -= len(chunk)

        def _project_file(self, path: Path) -> Path | None:
            if editor.store is None:
                return None
            return _safe_file(path, editor.store.root)

        def _call_tool(self, name: str, kwargs: dict) -> None:
            if name not in HTTP_TOOLS:
                self._reject(404)
                return
            payload = editor.call(name, **kwargs)
            self._json(payload)

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            path = unquote(parsed.path)
            if path in STATIC:
                dest, ctype = STATIC[path]
                if dest.is_file():
                    self._bytes(dest.read_bytes(), ctype)
                    return
            if path == "/api/timeline":
                payload = editor.timeline_get() if editor.store else {"ok": False, "timeline": None, "timeline_summary": {}}
                stills = []
                if editor.store:
                    stills = [p.name for p in sorted(editor.store.stills_dir.glob("*.jpg"))]
                payload["stills"] = stills
                self._json(payload)
                return
            if path.startswith("/api/"):
                name = path[len("/api/") :]
                if name in WRITE_TOOLS:
                    self._reject(405, "POST")
                    return
                self._call_tool(name, _coerce_query(parse_qs(parsed.query)))
                return
            if path.startswith("/stills/") and editor.store:
                name = path.split("/stills/", 1)[1]
                dest = self._project_file(editor.store.stills_dir / Path(name).name)
                if dest:
                    self._bytes(dest.read_bytes(), "image/jpeg")
                    return
            if path.startswith("/media/") and editor.store:
                parts = [p for p in path.split("/") if p]
                if len(parts) >= 3:
                    media_id, kind = parts[1], parts[2]
                    try:
                        item = editor._media(media_id)
                    except Exception:
                        self._reject(404)
                        return
                    if kind == "proxy":
                        candidate = Path(item.proxy_path or item.path or "")
                        dest = self._project_file(candidate)
                        if dest:
                            ctype = mimetypes.guess_type(dest.name)[0] or "video/mp4"
                            self._send_range(dest, ctype)
                            return
                    if kind == "thumb":
                        dest = self._project_file(editor.store.thumbs_dir / f"{item.id}.jpg")
                        if dest:
                            self._bytes(dest.read_bytes(), "image/jpeg")
                            return
            if path.startswith("/keyframes/") and editor.store:
                name = Path(path.split("/keyframes/", 1)[1]).name
                dest = self._project_file(editor.store.keyframes_dir / name)
                if dest is None:
                    for shots in editor._shots_by_media().values():
                        for shot in shots:
                            if Path(shot.keyframe).name == name or shot.id == Path(name).stem:
                                dest = self._project_file(Path(shot.keyframe))
                                if dest:
                                    break
                        if dest:
                            break
                if dest:
                    self._bytes(dest.read_bytes(), "image/jpeg")
                    return
            self._reject(404)

        def do_POST(self) -> None:
            if not _local_origin(self.headers.get("Origin")):
                self._reject(403)
                return
            parsed = urlparse(self.path)
            path = unquote(parsed.path)
            if not path.startswith("/api/"):
                self._reject(404)
                return
            name = path[len("/api/") :]
            if name in READ_TOOLS:
                self._reject(405, "GET")
                return
            if name not in WRITE_TOOLS:
                self._reject(404)
                return
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b"{}"
            try:
                body = json.loads(raw.decode("utf-8") or "{}")
            except json.JSONDecodeError:
                self._json({"ok": False, "warnings": ["invalid json"]}, 400)
                return
            if not isinstance(body, dict):
                self._json({"ok": False, "warnings": ["expected object"]}, 400)
                return
            self._call_tool(name, body)

        def log_message(self, fmt: str, *args) -> None:
            return

    return Handler


def start_readonly_server(editor: Editor, host: str, port: int) -> None:
    httpd = ThreadingHTTPServer((host, port), make_handler(editor))
    httpd.serve_forever()

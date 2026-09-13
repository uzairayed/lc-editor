from __future__ import annotations

import inspect
import json
import threading
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path

from lc_editor.analysis.labels import GUI_DOMAIN_TOOLS
from lc_editor.analysis.manifest import Shot, ShotMetrics, write_manifest
from lc_editor.server import TOOLS
from lc_editor.web.server import HTTP_TOOLS, WRITE_TOOLS, make_handler, start_readonly_server
from tests.conftest import touch_media


def _shot(media_id: str) -> Shot:
    return Shot.model_validate(
        {
            "id": "abc_00",
            "media_id": media_id,
            "in_s": 0.0,
            "out_s": 3.0,
            "duration_s": 3.0,
            "keyframe": "/tmp/abc_00.jpg",
            "metrics": ShotMetrics(),
        }
    )


def _serve(editor):
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(editor))
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return httpd


def _req(httpd, method: str, path: str, body: dict | None = None, origin: str | None = None) -> tuple[int, dict | bytes]:
    conn = HTTPConnection("127.0.0.1", httpd.server_address[1], timeout=5)
    headers = {}
    payload = None
    if origin:
        headers["Origin"] = origin
    if body is not None:
        payload = json.dumps(body)
        headers["Content-Type"] = "application/json"
    conn.request(method, path, body=payload, headers=headers)
    res = conn.getresponse()
    raw = res.read()
    conn.close()
    if res.getheader("Content-Type", "").startswith("application/json"):
        return res.status, json.loads(raw.decode("utf-8"))
    return res.status, raw


def test_http_tools_are_mcp_tools() -> None:
    assert WRITE_TOOLS <= set(GUI_DOMAIN_TOOLS) <= set(TOOLS)
    assert "clip_add" not in HTTP_TOOLS
    assert "timeline_reset" not in HTTP_TOOLS


def test_spec_ses_09_web_does_not_edit_timeline() -> None:
    source = inspect.getsource(start_readonly_server) + inspect.getsource(make_handler)
    assert "clip_add" not in source
    assert "timeline_reset" not in source
    assert "403" in source
    assert "WRITE_TOOLS" in source


def test_label_http_matches_mcp_and_rejects_abuse(editor, tmp_path: Path) -> None:
    media = touch_media(tmp_path / "src", "panel")
    editor.import_file(str(media))
    mid = editor.media[0].id
    write_manifest(editor._manifest_for(editor.media[0]), [_shot(mid)])
    httpd = _serve(editor)
    try:
        status, page = _req(httpd, "GET", "/")
        assert status == 200
        assert b"label desk" in page
        status, queued = _req(httpd, "GET", "/api/label_queue?filter=all")
        assert status == 200
        assert queued == editor.label_queue(filter="all")
        status, _ = _req(httpd, "POST", "/api/clip_add", {"media_id": mid})
        assert status == 404
        status, _ = _req(
            httpd,
            "POST",
            "/api/media_card_confirm",
            {"media_id": mid, "role": "before"},
            origin="https://evil.example",
        )
        assert status == 403
        status, confirmed = _req(
            httpd,
            "POST",
            "/api/media_card_confirm",
            {"media_id": mid, "role": "before", "subjects": ["hood"], "source": "owner"},
        )
        assert status == 200
        assert confirmed["ok"] is True
        assert editor.media[0].card.role == "before"
        status, _ = _req(httpd, "GET", "/stills/../../project.json")
        assert status == 404
        status, shot = _req(
            httpd,
            "POST",
            "/api/shot_card_confirm",
            {"shot_id": "abc_00", "role": "after"},
        )
        assert status == 200
        assert shot["label"]["role"]["value"] == "after"
        editor.project_open(str(editor.store.root))
        assert editor.shot_cards["abc_00"].role == "after"
        assert editor.media[0].card.confirmed is True
    finally:
        httpd.shutdown()

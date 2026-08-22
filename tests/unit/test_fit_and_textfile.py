from __future__ import annotations

from pathlib import Path

from lc_editor.app import Editor
from lc_editor.render.captions import write_textfile


def test_spec_edit_09_fit(editor: Editor, media_file: Path) -> None:
    editor.import_file(str(media_file))
    editor.clip_add(media_id=editor.media[-1].id, duration_s=5.0)
    clip_id = editor.timeline_get()["timeline"]["clips"][0]["id"]
    editor.caption_add(clip_id, "2 hours, one fuel stop")
    result = editor.clip_fit(clip_id)
    assert result["ok"] is True
    clip = editor.timeline_get()["timeline"]["clips"][0]
    assert clip["duration_s"] == 1.62


def test_spec_cap_10_textfile_no_trailing_newline(tmp_path: Path) -> None:
    path = tmp_path / "cap.txt"
    write_textfile(path, "It's Cafe Imran")
    raw = path.read_bytes()
    assert not raw.endswith(b"\n")
    assert b"It's Cafe Imran" == raw

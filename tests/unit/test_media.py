from __future__ import annotations

from pathlib import Path

from lc_editor.app import Editor
from tests.conftest import touch_media


def test_spec_ses_04_import_folder(editor: Editor, tmp_path: Path) -> None:
    folder = tmp_path / "inbox"
    for i in range(4):
        touch_media(folder, f"shot{i:02d}")
    result = editor.import_folder(str(folder))
    assert result["ok"] is True
    assert len(result["media"]) == 4
    listed = editor.media_list()
    assert len(listed["media"]) == 4


def test_spec_ses_05_media_remove_rejected_if_used(editor: Editor, media_file: Path) -> None:
    editor.import_file(str(media_file))
    mid = editor.media[0].id
    editor.clip_add(media_id=mid)
    bad = editor.media_remove(mid)
    assert bad["ok"] is False
    editor.clip_remove(editor.timeline_get()["timeline"]["clips"][0]["id"])
    good = editor.media_remove(mid)
    assert good["ok"] is True
    assert editor.media_list()["media"] == []


def test_spec_ses_05_probe_thumbnail_proxy(editor: Editor, media_file: Path) -> None:
    editor.import_file(str(media_file))
    mid = editor.media[0].id
    probed = editor.probe(media_id=mid)
    assert probed["probe"]["width"] == 1920
    thumb = editor.thumbnail(mid)
    assert Path(thumb["path"]).exists()
    sheet = editor.contact_sheet()
    assert Path(sheet["path"]).exists()
    proxy = editor.proxy_build(mid)
    assert proxy["paths"]


def test_spec_ses_06_burst_cover(editor: Editor, tmp_path: Path) -> None:
    folder = tmp_path / "burst"
    for i in range(4):
        touch_media(folder, f"IMG_{i:04d}", ".jpg")
    editor.import_folder(str(folder))
    covers = [m for m in editor.media_list()["media"] if m["burst_cover"]]
    assert len(covers) == 1

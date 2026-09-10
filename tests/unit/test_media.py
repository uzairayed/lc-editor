from __future__ import annotations

import json
from pathlib import Path

from lc_editor.analysis.media import parse_probe
from lc_editor.app import Editor
from lc_editor.render.runner import FakeRunner
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
    for item in listed["media"]:
        assert item["captured_at"]
        assert item["captured_at_source"] in {"probe", "exif", "mtime"}


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


def test_media_list_and_probe_expose_resolution(editor: Editor, media_file: Path) -> None:
    imported = editor.import_file(str(media_file))
    assert imported["ok"] is True
    assert imported["warnings"] == []
    item = editor.media_list()["media"][0]
    assert item["width"] == 1920
    assert item["height"] == 1080
    assert item["resolution"] == "1920x1080"
    assert item["sub_720"] is False
    probed = editor.probe(media_id=item["id"])
    assert probed["probe"]["width"] == 1920
    assert probed["probe"]["height"] == 1080
    assert probed["probe"]["resolution"] == "1920x1080"
    assert probed["probe"]["sub_720"] is False


def test_import_warns_and_lists_sub_720(tmp_path: Path) -> None:
    runner = FakeRunner(duration_s=5.0, width=512, height=288)
    editor = Editor(workspace=tmp_path, runner=runner)
    editor.project_create(name="reel", project_dir=str(tmp_path / "reel"))
    media = touch_media(tmp_path / "src", "day1")
    imported = editor.import_file(str(media))
    assert imported["ok"] is True
    assert any("SPEC-QLT-01" in w for w in imported["warnings"])
    assert imported["media"]["resolution"] == "512x288"
    assert imported["media"]["sub_720"] is True
    listed = editor.media_list()["media"][0]
    assert listed["resolution"] == "512x288"
    assert listed["sub_720"] is True
    assert listed["width"] == 512
    assert listed["height"] == 288


def test_import_folder_warns_only_sub_720(tmp_path: Path) -> None:
    runner = FakeRunner(duration_s=5.0, width=512, height=288)
    editor = Editor(workspace=tmp_path, runner=runner)
    editor.project_create(name="reel", project_dir=str(tmp_path / "reel"))
    folder = tmp_path / "inbox"
    touch_media(folder, "phone")
    imported = editor.import_folder(str(folder))
    assert imported["ok"] is True
    assert any("SPEC-QLT-01" in w for w in imported["warnings"])
    assert imported["media"][0]["sub_720"] is True


def test_import_720_is_not_sub_720(tmp_path: Path) -> None:
    runner = FakeRunner(duration_s=5.0, width=1280, height=720)
    editor = Editor(workspace=tmp_path, runner=runner)
    editor.project_create(name="reel", project_dir=str(tmp_path / "reel"))
    imported = editor.import_file(str(touch_media(tmp_path / "src", "hdready")))
    assert imported["ok"] is True
    assert imported["warnings"] == []
    assert imported["media"]["resolution"] == "1280x720"
    assert imported["media"]["sub_720"] is False


def test_parse_probe_keeps_width_height() -> None:
    payload = json.dumps(
        {
            "streams": [
                {
                    "codec_type": "video",
                    "width": 512,
                    "height": 288,
                    "r_frame_rate": "30/1",
                    "avg_frame_rate": "30/1",
                }
            ],
            "format": {"duration": "4.0"},
        }
    )
    parsed = parse_probe(payload, "video")
    assert parsed["width"] == 512
    assert parsed["height"] == 288
    assert "resolution" not in parsed


def test_spec_ses_06_burst_cover(editor: Editor, tmp_path: Path) -> None:
    folder = tmp_path / "burst"
    for i in range(4):
        touch_media(folder, f"IMG_{i:04d}", ".jpg")
    editor.import_folder(str(folder))
    covers = [m for m in editor.media_list()["media"] if m["burst_cover"]]
    assert len(covers) == 1

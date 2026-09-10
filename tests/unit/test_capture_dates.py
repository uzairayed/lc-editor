from __future__ import annotations

import json
from pathlib import Path

from lc_editor.analysis.media import (
    creation_time_from_probe,
    normalize_captured_at,
    parse_probe,
    resolve_captured_at,
)
from lc_editor.app import Editor
from lc_editor.models import MediaItem
from lc_editor.render.runner import FakeRunner
from tests.conftest import touch_media


def test_parse_probe_reads_format_creation_time() -> None:
    payload = json.dumps(
        {
            "streams": [{"codec_type": "video", "width": 1920, "height": 1080, "avg_frame_rate": "30/1"}],
            "format": {
                "duration": "5.0",
                "tags": {"creation_time": "2024-03-02T08:15:00.000000Z"},
            },
        }
    )
    parsed = parse_probe(payload, "video")
    assert parsed["creation_time"] == "2024-03-02T08:15:00.000000Z"
    assert parsed["width"] == 1920


def test_creation_time_from_stream_tags() -> None:
    found = creation_time_from_probe(
        {
            "format": {"duration": "2"},
            "streams": [{"codec_type": "video", "tags": {"creation_time": "2024-01-15T10:00:00Z"}}],
        }
    )
    assert found == "2024-01-15T10:00:00Z"


def test_resolve_prefers_probe_over_exif_and_mtime(tmp_path: Path) -> None:
    path = touch_media(tmp_path, "clip")
    captured, source = resolve_captured_at(
        probe={"creation_time": "2024-03-02T08:15:00Z"},
        exif={"DateTimeOriginal": "2023:01:01 00:00:00"},
        path=path,
    )
    assert source == "probe"
    assert captured == "2024-03-02T08:15:00Z"


def test_resolve_uses_exif_datetimeoriginal(tmp_path: Path) -> None:
    path = touch_media(tmp_path, "still", ".jpg")
    captured, source = resolve_captured_at(
        probe={},
        exif={"DateTimeOriginal": "2024:03:02 08:15:00"},
        path=path,
    )
    assert source == "exif"
    assert captured == "2024-03-02T08:15:00"


def test_resolve_falls_back_to_mtime(tmp_path: Path) -> None:
    path = touch_media(tmp_path, "clip")
    captured, source = resolve_captured_at(probe={}, exif={}, path=path)
    assert source == "mtime"
    assert captured
    assert captured.endswith("Z")


def test_normalize_exif_and_iso() -> None:
    assert normalize_captured_at("2024:03:02 08:15:00") == "2024-03-02T08:15:00"
    assert normalize_captured_at("2024-03-02T08:15:00.000000Z") == "2024-03-02T08:15:00Z"
    assert normalize_captured_at("") is None
    assert normalize_captured_at("not-a-date") is None


def test_old_media_json_loads_without_capture_fields(editor: Editor) -> None:
    path = editor._media_index_path()
    path.write_text(
        json.dumps(
            [
                {
                    "id": "m_old",
                    "path": "x.mp4",
                    "original_path": "x.mp4",
                    "kind": "video",
                }
            ]
        ),
        encoding="utf-8",
    )
    editor._load_media()
    item = editor.media[0]
    assert item.id == "m_old"
    assert item.captured_at is None
    assert item.captured_at_source is None
    assert item.shoot_day is None
    assert item.role is None


def test_import_stores_probe_creation_time(tmp_path: Path) -> None:
    runner = FakeRunner(duration_s=5.0, creation_time="2024-03-02T08:15:00Z")
    editor = Editor(workspace=tmp_path, runner=runner)
    editor.project_create(name="reel", project_dir=str(tmp_path / "reel"))
    media = touch_media(tmp_path / "src", "shot")
    imported = editor.import_file(str(media))
    assert imported["ok"] is True
    item = editor.media[0]
    assert item.captured_at == "2024-03-02T08:15:00Z"
    assert item.captured_at_source == "probe"
    probed = editor.probe(media_id=item.id)
    assert probed["probe"]["captured_at"] == "2024-03-02T08:15:00Z"
    listed = editor.media_list()["media"]
    assert listed[0]["captured_at"] == "2024-03-02T08:15:00Z"


def test_import_uses_exif_when_probe_has_no_date(editor: Editor, tmp_path: Path, monkeypatch) -> None:
    still = touch_media(tmp_path / "src", "photo", ".jpg")
    monkeypatch.setattr(
        "lc_editor.app.read_exif_tags",
        lambda path: {"DateTimeOriginal": "2024:03:02 08:15:00"},
    )
    editor.import_file(str(still))
    item = editor.media[0]
    assert item.captured_at_source == "exif"
    assert item.captured_at == "2024-03-02T08:15:00"


def test_import_uses_mtime_as_last_resort(editor: Editor, media_file: Path) -> None:
    editor.import_file(str(media_file))
    item = editor.media[0]
    assert item.captured_at_source == "mtime"
    assert item.captured_at


def test_media_list_sorts_by_captured_at(editor: Editor, tmp_path: Path) -> None:
    later = touch_media(tmp_path / "src", "later")
    earlier = touch_media(tmp_path / "src", "earlier")
    editor.import_file(str(later))
    editor.import_file(str(earlier))
    editor.media[0] = editor.media[0].model_copy(update={"captured_at": "2024-03-03T10:00:00"})
    editor.media[1] = editor.media[1].model_copy(update={"captured_at": "2024-03-01T08:00:00"})
    listed = editor.media_list()["media"]
    assert [row["captured_at"] for row in listed] == ["2024-03-01T08:00:00", "2024-03-03T10:00:00"]
    imported = editor.media_list(sort="import")["media"]
    assert [row["id"] for row in imported] == [editor.media[0].id, editor.media[1].id]


def test_media_tag_day_and_role(editor: Editor, media_file: Path) -> None:
    editor.import_file(str(media_file))
    mid = editor.media[0].id
    tagged = editor.media_tag(mid, shoot_day=1, role="before")
    assert tagged["ok"] is True
    assert tagged["media"]["shoot_day"] == 1
    assert tagged["media"]["role"] == "before"
    assert editor.media[0].shoot_day == 1
    day1 = editor.media_tag(mid, shoot_day="day1", role="wash")
    assert day1["media"]["shoot_day"] == "day1"
    assert day1["media"]["role"] == "wash"
    filtered = editor.media_list(shoot_day="day1", role="wash")
    assert [row["id"] for row in filtered["media"]] == [mid]
    empty = editor.media_tag(mid)
    assert empty["ok"] is False
    replay = editor.media_tag(mid, role="after", op_id="tag-1")
    again = editor.media_tag(mid, role="machine", op_id="tag-1")
    assert replay["media"]["role"] == again["media"]["role"] == "after"


def test_media_item_defaults_are_additive() -> None:
    item = MediaItem(id="m1", path="x.mp4", original_path="x.mp4")
    assert item.captured_at is None
    assert item.shoot_day is None
    assert item.role is None

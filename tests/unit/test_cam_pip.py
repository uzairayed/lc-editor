from __future__ import annotations

from pathlib import Path

from lc_editor.app import Editor
from lc_editor.models import Clip, MediaItem, Project
from lc_editor.render.graph import clip_hash_payload, clip_video_filters


def _wide(editor: Editor, media_file: Path) -> str:
    editor.import_file(str(media_file))
    item = editor.media[-1]
    editor.media[-1] = item.model_copy(update={"width": 1920, "height": 1080})
    editor._save_media()
    editor.clip_add(media_id=item.id, duration_s=3.0)
    return editor.timeline_get()["timeline"]["clips"][-1]["id"]


def test_spec_edit_24_cam_pip_from_source_rect(editor: Editor, media_file: Path) -> None:
    clip_id = _wide(editor, media_file)
    added = editor.cam_pip(clip_id, x=1520, y=0, w=400, h=280)
    assert added["ok"] is True
    clip = editor.timeline_get()["timeline"]["clips"][0]
    pip = clip["cam_pip"]
    assert pip["x"] == 1520
    assert pip["y"] == 0
    assert pip["w"] == 400
    assert pip["h"] == 280
    assert pip["overlay_x"] == 632
    assert pip["overlay_y"] == 72
    assert pip["overlay_w"] == 420
    assert pip["pad"] == 3


def test_spec_edit_24_cam_pip_skips_tall_source(editor: Editor, media_file: Path) -> None:
    editor.import_file(str(media_file))
    item = editor.media[-1]
    editor.media[-1] = item.model_copy(update={"width": 1080, "height": 1920})
    editor._save_media()
    editor.clip_add(media_id=item.id, duration_s=3.0)
    clip_id = editor.timeline_get()["timeline"]["clips"][0]["id"]
    skipped = editor.cam_pip(clip_id, x=10, y=10, w=200, h=200)
    assert skipped["ok"] is False
    assert any("cam" in w.lower() or "SPEC-EDIT-24" in w for w in skipped["warnings"])
    assert editor.timeline_get()["timeline"]["clips"][0].get("cam_pip") in (None, {})


def test_spec_edit_24_cam_pip_clear(editor: Editor, media_file: Path) -> None:
    clip_id = _wide(editor, media_file)
    editor.cam_pip(clip_id, 1520, 0, 400, 280)
    cleared = editor.cam_pip_clear(clip_id)
    assert cleared["ok"] is True
    assert editor.timeline_get()["timeline"]["clips"][0].get("cam_pip") in (None, {})


def test_spec_edit_24_cam_pip_suggest_16x9(editor: Editor, media_file: Path) -> None:
    clip_id = _wide(editor, media_file)
    hint = editor.cam_pip_suggest(clip_id)
    assert hint["ok"] is True
    box = hint["rect"]
    assert box["w"] > 0 and box["h"] > 0
    assert box["x"] >= 1000


def test_spec_edit_24_cam_pip_filter_crops_source_rect() -> None:
    pip_filters = getattr(__import__("lc_editor.render.graph", fromlist=["cam_pip_filters"]), "cam_pip_filters", None)
    assert callable(pip_filters)
    clip = Clip(
        id="c1",
        media_id="m1",
        cam_pip={"x": 1520, "y": 0, "w": 400, "h": 280},
    )
    media = MediaItem(id="m1", path="x.mp4", original_path="x.mp4", width=1920, height=1080)
    filt = pip_filters(clip, media)
    assert "crop=400:280:1520:0" in filt.replace(" ", "")
    assert "420" in filt
    assert "pad" in filt
    project = Project(id="p", name="n")
    hashed = clip_hash_payload(clip, [], project)
    bare = clip_hash_payload(Clip(id="c1", media_id="m1"), [], project)
    assert hashed != bare
    vf = clip_video_filters(clip, media, [], project)
    assert "overlay=632:72" in vf
    assert "crop=400:280:1520:0" in vf

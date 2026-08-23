from __future__ import annotations

from pathlib import Path

from lc_editor.app import Editor
from lc_editor.render.runner import FakeRunner
from tests.conftest import touch_media


def test_production_reel_template_music_layers(tmp_path: Path) -> None:
    runner = FakeRunner(duration_s=8.0)
    editor = Editor(workspace=tmp_path, runner=runner)
    editor.project_create(name="prod", project_dir=str(tmp_path / "prod"))
    clip = touch_media(tmp_path / "src", "ride", ".mp4")
    still = touch_media(tmp_path / "src", "chip", ".png")
    song = touch_media(tmp_path / "src", "bed", ".wav")
    editor.import_file(str(clip))
    vid = editor.media[-1].id
    editor.clip_add(media_id=vid, duration_s=2.4)
    editor.clip_add(media_id=vid, duration_s=2.6)
    editor.import_file(str(still))
    editor.layer_add(kind="image", media_id=editor.media[-1].id, start_s=0.4, duration_s=1.5, z=15)
    editor.template_apply("editorial", bindings={"hook_text": "City of tombs", "body_text": "2 hours out"})
    editor.layer_add(kind="text", text="N-5 south", start_s=3.0, duration_s=1.8, motion="type_on")
    editor.project_set(allow_music=True)
    editor.import_file(str(song))
    editor.music_add(editor.media[-1].id, duration_s=5.0, source_name="owner track", license_note="test")
    editor.beat_analyze(editor.media[-1].id)
    editor.beat_edit(bpm=100.0, offset_s=0.0)
    preview = editor.beat_sync_preview(subdivision="1/2")
    assert preview["ok"] is True
    editor.beat_sync_apply(subdivision="1/2")
    stills = editor.preview_stills()
    assert stills["ok"] is True
    review = editor.review_report()
    assert review["ok"] is True
    exported = editor.export()
    assert exported["ok"] is True
    sidecar = Path(exported["sidecar"]).read_text(encoding="utf-8")
    assert "music" in sidecar
    assert "layers" in sidecar
    assert "owner track" in sidecar

from __future__ import annotations

from pathlib import Path

from lc_editor.app import Editor
from lc_editor.models import BeatGrid, Clip, Timeline
from lc_editor.ops.sync import propose_beat_sync
from tests.conftest import touch_media


def test_music_requires_opt_in(editor: Editor, tmp_path: Path) -> None:
    track = touch_media(tmp_path / "src", "song", ".mp3")
    editor.import_file(str(track))
    audio_id = editor.media[-1].id
    blocked = editor.music_add(audio_id, source_name="test track")
    assert blocked["ok"] is False
    editor.project_set(allow_music=True)
    ok = editor.music_add(audio_id, duration_s=4.0, source_name="test track", license_note="owner")
    assert ok["ok"] is True
    listed = editor.music_list()
    assert listed["music"]


def test_sfx_and_bed_still_reject_music(editor: Editor, media_file: Path) -> None:
    editor.import_file(str(media_file))
    editor.clip_add(media_id=editor.media[-1].id, duration_s=2.0)
    assert editor.audio_bed("cinematic")["ok"] is False
    assert editor.sfx_place("music", at_s=0.0)["ok"] is False


def test_beat_analyze_and_sync_preview(editor: Editor, media_file: Path, tmp_path: Path) -> None:
    editor.import_file(str(media_file))
    editor.clip_add(media_id=editor.media[-1].id, duration_s=2.0)
    editor.clip_add(media_id=editor.media[-1].id, duration_s=2.0)
    track = touch_media(tmp_path / "src", "song", ".wav")
    editor.import_file(str(track))
    editor.project_set(allow_music=True)
    editor.music_add(editor.media[-1].id, duration_s=8.0, source_name="click")
    analyzed = editor.beat_analyze(editor.media[-1].id)
    assert analyzed["ok"] is True
    preview = editor.beat_sync_preview(strength=1.0, subdivision="1")
    assert preview["ok"] is True
    assert "proposal" in preview
    version = editor.timeline_get()["timeline"]["version"]
    applied = editor.beat_sync_apply(strength=1.0, subdivision="1")
    assert applied["ok"] is True
    assert editor.timeline_get()["timeline"]["version"] > version


def test_sync_respects_protected_and_hold() -> None:
    timeline = Timeline(
        clips=[
            Clip(id="c1", media_id="m1", duration_s=2.0, start_s=0.0, protect=True),
            Clip(id="c2", media_id="m1", duration_s=2.0, start_s=2.0),
        ],
        beat_grid=BeatGrid(media_id="a1", bpm=120, offset_s=0.0, beats=[0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0]),
    )
    preview = propose_beat_sync(timeline, strength=1.0, min_shot_s=0.5, max_shot_s=8.0)
    assert preview["ok"] is True
    assert preview["clips"][0].duration_s == 2.0

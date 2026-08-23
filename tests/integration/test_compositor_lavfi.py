from __future__ import annotations

from pathlib import Path

import pytest

from lc_editor.app import Editor
from lc_editor.render.runner import FfmpegRunner, find_tool


def _have_ffmpeg() -> bool:
    try:
        find_tool("ffmpeg")
        find_tool("ffprobe")
        return True
    except FileNotFoundError:
        return False


@pytest.mark.integration
def test_compositor_layers_and_music(tmp_path: Path) -> None:
    if not _have_ffmpeg():
        pytest.skip("ffmpeg not on PATH")
    runner = FfmpegRunner()
    video = tmp_path / "clip.mp4"
    still = tmp_path / "card.png"
    song = tmp_path / "song.wav"
    runner.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=0x1A1410:s=1920x1080:d=3:r=30",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=220:duration=3",
            "-shortest",
            str(video),
        ]
    )
    runner.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=0x334455:s=400x400:d=1", "-frames:v", "1", str(still)])
    runner.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=4", str(song)])
    editor = Editor(workspace=tmp_path, runner=runner)
    editor.project_create(name="comp", project_dir=str(tmp_path / "comp"))
    editor.import_file(str(video))
    editor.clip_add(media_id=editor.media[-1].id, duration_s=2.5)
    editor.import_file(str(still))
    editor.layer_add(kind="image", media_id=editor.media[-1].id, start_s=0.2, duration_s=1.2, z=12)
    editor.layer_add(kind="text", text="Cafe Imran, Gharo", start_s=0.3, duration_s=2.0, motion="fade")
    clip_id = editor.timeline_get()["timeline"]["clips"][0]["id"]
    editor.effect_add(clip_id, "vignette", {"amount": 0.2})
    editor.project_set(allow_music=True)
    editor.import_file(str(song))
    editor.music_add(editor.media[-1].id, duration_s=2.5, gain_db=-10, source_name="sine", license_note="test")
    editor.beat_analyze(editor.media[-1].id)
    preview = editor.preview_proxy()
    assert preview["ok"] is True
    assert Path(preview["path"]).stat().st_size > 200
    review = editor.review_report()
    assert review["ok"] is True
    exported = editor.export()
    assert exported["ok"] is True
    assert Path(exported["hero"]).stat().st_size > 200

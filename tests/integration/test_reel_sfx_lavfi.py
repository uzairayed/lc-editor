from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from lc_editor.app import Editor
from lc_editor.render.runner import FfmpegRunner

ffmpeg = shutil.which("ffmpeg")
pytestmark = pytest.mark.integration
skip_no_ffmpeg = pytest.mark.skipif(ffmpeg is None, reason="ffmpeg not on PATH")


def _tone(dest: Path, seconds: float = 3.0) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            ffmpeg,
            "-nostdin",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"testsrc2=s=640x360:d={seconds}",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=220:d={seconds}",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-shortest",
            str(dest),
        ],
        check=True,
        capture_output=True,
    )
    return dest


@skip_no_ffmpeg
def test_reel_sfx_on_zoom_and_caption_respects_mix(tmp_path: Path) -> None:
    a = _tone(tmp_path / "a.mp4", 3.0)
    b = _tone(tmp_path / "b.mp4", 3.0)
    editor = Editor(workspace=tmp_path, runner=FfmpegRunner())
    editor.project_create(name="reel", project_dir=str(tmp_path / "reel"))
    editor.import_file(str(a))
    editor.import_file(str(b))
    editor.clip_add(media_id=editor.media[0].id, duration_s=2.4)
    editor.clip_add(media_id=editor.media[1].id, duration_s=2.4)
    first = editor.timeline_get()["timeline"]["clips"][0]["id"]
    second = editor.timeline_get()["timeline"]["clips"][1]["id"]
    assert editor.motion_zoom_in(first)["ok"] is True
    assert editor.sfx_place("swipe", at_s=0.0, gain_db=-12.0)["ok"] is True
    cap = editor.caption_add(second, "Cafe Imran stop")
    assert cap["ok"] is True
    assert editor.sfx_place("button", at_s=2.4, gain_db=-12.0)["ok"] is True
    editor.audio_bed("room", gain_db=-6.0)
    mix = editor.mix_preview()
    assert mix["ok"] is True, mix
    assert mix["post_peak_dbtp"] <= -1.0
    kinds = {s["kind"] for s in editor.timeline_get()["timeline"]["sfx"]}
    assert "swipe" in kinds
    assert "button" in kinds

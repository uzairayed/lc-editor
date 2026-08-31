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


def _color(dest: Path, seconds: float) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            ffmpeg,
            "-nostdin",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"color=c=0x1A1410:s=640x360:d={seconds}",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-an",
            str(dest),
        ],
        check=True,
        capture_output=True,
    )
    return dest


@skip_no_ffmpeg
def test_zoom_suggest_static_color_clips(tmp_path: Path) -> None:
    long_a = _color(tmp_path / "a.mp4", 6.0)
    long_b = _color(tmp_path / "b.mp4", 6.0)
    short = _color(tmp_path / "c.mp4", 1.5)
    editor = Editor(workspace=tmp_path, runner=FfmpegRunner())
    editor.project_create(name="reel", project_dir=str(tmp_path / "reel"))
    editor.import_file(str(long_a))
    editor.import_file(str(long_b))
    editor.import_file(str(short))
    editor.clip_add(media_id=editor.media[0].id, duration_s=6.0)
    editor.clip_add(media_id=editor.media[1].id, duration_s=6.0)
    editor.clip_add(media_id=editor.media[2].id, duration_s=1.5)
    clips = editor.timeline_get()["timeline"]["clips"]
    a, b, c = clips[0]["id"], clips[1]["id"], clips[2]["id"]
    suggested = editor.motion_zoom_suggest()
    assert suggested["ok"] is True
    by_id = {row["clip_id"]: row for row in suggested["suggestions"]}
    assert by_id[a]["action"] == "pair"
    assert by_id[b]["action"] == "none"
    assert by_id[c]["action"] == "none"
    assert sum(1 for row in suggested["suggestions"] if row["action"] == "pair") <= 1

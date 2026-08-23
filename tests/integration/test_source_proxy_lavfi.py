from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from lc_editor.app import Editor
from lc_editor.render.runner import FfmpegRunner

ffmpeg = shutil.which("ffmpeg")
ffprobe = shutil.which("ffprobe")
pytestmark = pytest.mark.integration
skip_no_ffmpeg = pytest.mark.skipif(ffmpeg is None, reason="ffmpeg not on PATH")


def _clip(dest: Path, seconds: float = 8.0) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            ffmpeg,
            "-nostdin",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"testsrc2=s=1920x1080:d={seconds}",
            "-f",
            "lavfi",
            "-i",
            f"sine=d={seconds}",
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
def test_sixty_second_lavfi_export(tmp_path: Path) -> None:
    a = _clip(tmp_path / "a.mp4")
    b = _clip(tmp_path / "b.mp4")
    editor = Editor(workspace=tmp_path, runner=FfmpegRunner())
    editor.project_create(name="reel", project_dir=str(tmp_path / "reel"))
    editor.import_file(str(a))
    editor.import_file(str(b))
    assert Path(editor.media[0].proxy_path).exists()
    again = editor.media_proxy(editor.media[0].id)
    assert again["cached"] == [True]
    ids = [editor.media[0].id, editor.media[1].id]
    for i in range(12):
        editor.clip_add(media_id=ids[i % 2], duration_s=5.0)
    assert editor.timeline_get()["timeline_summary"]["duration_s"] == 60.0
    preview = editor.preview_proxy()
    assert preview["ok"]
    assert Path(preview["path"]).exists()
    review = editor.review_report()
    assert review["ok"], review
    exported = editor.export()
    assert exported["ok"], exported
    hero = Path(exported["hero"])
    probe = subprocess.run(
        [
            ffprobe or "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1",
            str(hero),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "width=1080" in probe.stdout
    assert "height=1920" in probe.stdout
    dur = float(next(line.split("=")[1] for line in probe.stdout.splitlines() if line.startswith("duration=")))
    assert abs(dur - 60.0) <= 0.15

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


def _run(args: list[str]) -> None:
    subprocess.run(args, check=True, capture_output=True)


def _tone(dest: Path, seconds: float = 3.0) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    _run(
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
            f"sine=frequency=440:d={seconds}",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-shortest",
            str(dest),
        ]
    )
    return dest


def _still(dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    _run(
        [
            ffmpeg,
            "-nostdin",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=white:s=640x360:d=1",
            "-frames:v",
            "1",
            "-update",
            "1",
            str(dest),
        ]
    )
    return dest


def _stream_durations(path: Path) -> tuple[float, float]:
    result = subprocess.run(
        [
            ffprobe or "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "stream=codec_type,duration",
            "-of",
            "csv=p=0",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    video = audio = None
    for line in result.stdout.splitlines():
        parts = line.split(",")
        if len(parts) < 2:
            continue
        kind, dur = parts[0], float(parts[1])
        if kind == "video":
            video = dur
        elif kind == "audio":
            audio = dur
    assert video is not None and audio is not None
    return video, audio


@skip_no_ffmpeg
def test_export_tone_and_still_share_duration(tmp_path: Path) -> None:
    tone = _tone(tmp_path / "talk.mp4")
    still = _still(tmp_path / "card.jpg")
    editor = Editor(workspace=tmp_path, runner=FfmpegRunner())
    editor.project_create(name="reel", project_dir=str(tmp_path / "reel"))
    editor.import_file(str(tone))
    editor.import_file(str(still))
    editor.clip_add(media_id=editor.media[0].id, duration_s=3.0)
    editor.clip_add(media_id=editor.media[1].id, duration_s=2.5)
    editor.motion_kenburns(editor.timeline_get()["timeline"]["clips"][-1]["id"])
    review = editor.review_report()
    assert review["ok"] is True, review
    exported = editor.export()
    assert exported["ok"] is True, exported
    video_s, audio_s = _stream_durations(Path(exported["hero"]))
    assert abs(video_s - audio_s) <= 0.05
    assert abs(video_s - 5.5) <= 0.15

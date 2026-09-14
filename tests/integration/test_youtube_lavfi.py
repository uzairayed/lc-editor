from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from lc_editor.app import Editor
from lc_editor.render.runner import FfmpegRunner

ffmpeg = shutil.which("ffmpeg")
ffprobe = shutil.which("ffprobe")
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(ffmpeg is None or ffprobe is None, reason="ffmpeg/ffprobe not on PATH"),
]


def test_youtube_sdr_export_profile(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    subprocess.run(
        [
            ffmpeg or "ffmpeg",
            "-nostdin",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=s=640x360:d=2.5:r=24",
            "-f",
            "lavfi",
            "-i",
            "sine=d=2.5",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-shortest",
            str(source),
        ],
        check=True,
        capture_output=True,
    )
    editor = Editor(workspace=tmp_path, runner=FfmpegRunner(timeout_s=120))
    assert editor.project_create(
        name="youtube",
        preset="youtube",
        width=640,
        height=360,
        fps=24,
        project_dir=str(tmp_path / "project"),
    )["ok"]
    assert editor.import_file(str(source))["ok"]
    assert editor.clip_add(media_id=editor.media[0].id, duration_s=2.5)["ok"]
    assert editor.review_report()["ok"]
    exported = editor.export(preset="youtube")
    assert exported["ok"], exported
    probe = subprocess.run(
        [
            ffprobe or "ffprobe",
            "-v",
            "error",
            "-show_entries",
            (
                "stream=codec_type,codec_name,profile,width,height,pix_fmt,sample_rate,channels,"
                "color_space,color_transfer,color_primaries"
            ),
            "-of",
            "json",
            exported["youtube"],
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    streams = json.loads(probe.stdout)["streams"]
    video = next(stream for stream in streams if stream["codec_type"] == "video")
    audio = next(stream for stream in streams if stream["codec_type"] == "audio")
    assert (video["width"], video["height"]) == (640, 360)
    assert video["codec_name"] == "h264"
    assert video["profile"] == "High"
    assert video["pix_fmt"] == "yuv420p"
    assert video["color_space"] == "bt709"
    assert audio["codec_name"] == "aac"
    assert audio["sample_rate"] == "48000"
    assert audio["channels"] == 2

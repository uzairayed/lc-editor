from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
from PIL import Image

from lc_editor.app import Editor
from lc_editor.render.runner import FfmpegRunner

ffmpeg = shutil.which("ffmpeg")
ffprobe = shutil.which("ffprobe")
pytestmark = pytest.mark.integration
skip_no_ffmpeg = pytest.mark.skipif(ffmpeg is None, reason="ffmpeg not on PATH")


def _run(args: list[str]) -> None:
    subprocess.run(args, check=True, capture_output=True)


def _probe_duration(path: Path) -> float:
    result = subprocess.run(
        [
            ffprobe or "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return float(result.stdout.strip())


def _scene_clip(dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    _run(
        [
            ffmpeg,
            "-nostdin",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=s=640x360:d=3",
            "-f",
            "lavfi",
            "-i",
            "color=c=red:s=640x360:d=3",
            "-filter_complex",
            "[0:v][1:v]concat=n=2:v=1:a=0",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(dest),
        ]
    )
    return dest


def _silent_clip(dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    _run(
        [
            ffmpeg,
            "-nostdin",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=s=640x360:d=2",
            "-an",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(dest),
        ]
    )
    return dest


@skip_no_ffmpeg
def test_analyze_detects_concat_scenes(tmp_path: Path) -> None:
    clip = _scene_clip(tmp_path / "scenes.mp4")
    editor = Editor(workspace=tmp_path, runner=FfmpegRunner())
    editor.project_create(name="reel", project_dir=str(tmp_path / "reel"))
    editor.import_file(str(clip))
    first = editor.media_analyze()
    assert first["ok"] is True
    assert first["shots"] >= 2
    shots = editor.shots_list()["shots"]
    duration = _probe_duration(Path(editor.media[0].path))
    assert abs(shots[0]["in_s"] - 0.0) < 1e-3
    assert abs(shots[-1]["out_s"] - duration) <= 0.15
    for prev, nxt in zip(shots, shots[1:]):
        assert abs(prev["out_s"] - nxt["in_s"]) < 1e-3
        assert prev["out_s"] > prev["in_s"]
    for shot in shots:
        frame = Path(shot["keyframe"])
        assert frame.exists()
        with Image.open(frame) as image:
            image.verify()
    second = editor.media_analyze()
    assert second["ok"] is True
    assert second["cached"] == [True]
    assert second["shots"] == first["shots"]


@skip_no_ffmpeg
def test_analyze_silent_lavfi(tmp_path: Path) -> None:
    clip = _silent_clip(tmp_path / "silent.mp4")
    editor = Editor(workspace=tmp_path, runner=FfmpegRunner())
    editor.project_create(name="reel", project_dir=str(tmp_path / "reel"))
    editor.import_file(str(clip))
    assert editor.media[0].has_audio is False
    result = editor.media_analyze()
    assert result["ok"] is True
    for shot in editor.shots_list()["shots"]:
        assert shot["metrics"]["audio_class"] == "silent"
        assert shot["metrics"]["audio_rms_db"] is None

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
pytestmark = pytest.mark.integration
skip_no_ffmpeg = pytest.mark.skipif(ffmpeg is None or ffprobe is None, reason="ffmpeg not on PATH")


def _run(args: list[str]) -> None:
    subprocess.run(args, check=True, capture_output=True)


def _tone(dest: Path, seconds: float = 5.0, *, audio_short: float | None = None) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    audio_d = audio_short if audio_short is not None else seconds
    _run(
        [
            ffmpeg,
            "-nostdin",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"testsrc2=s=1920x1080:d={seconds}:r=30",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=440:d={audio_d}:sample_rate=48000",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-ar",
            "48000",
            "-t",
            str(seconds) if audio_short is None else str(max(seconds, audio_d)),
            str(dest),
        ]
    )
    return dest


def _probe(path: Path) -> dict:
    result = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-show_streams",
            "-of",
            "json",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout)


def _ebur128_i(path: Path) -> float | None:
    result = subprocess.run(
        [
            ffmpeg,
            "-nostdin",
            "-i",
            str(path),
            "-af",
            "ebur128=peak=true",
            "-f",
            "null",
            "-",
        ],
        capture_output=True,
        text=True,
    )
    integrated = None
    for line in (result.stderr or "").splitlines():
        if "I:" in line and "LUFS" in line:
            try:
                integrated = float(line.split("I:")[1].split("LUFS")[0].strip())
            except ValueError:
                continue
    return integrated


@skip_no_ffmpeg
def test_hero_keeps_frames_when_audio_is_short(tmp_path: Path) -> None:
    src = _tone(tmp_path / "talk.mp4", seconds=2.5, audio_short=2.43)
    editor = Editor(workspace=tmp_path, runner=FfmpegRunner())
    editor.project_create(name="reel", project_dir=str(tmp_path / "reel"))
    editor.import_file(str(src))
    editor.clip_add(media_id=editor.media[0].id, duration_s=2.5)
    assert editor.review_report()["ok"] is True
    exported = editor.export()
    assert exported["ok"] is True, exported
    payload = _probe(Path(exported["hero"]))
    video = next(s for s in payload["streams"] if s["codec_type"] == "video")
    frames = int(video.get("nb_frames") or 0)
    if frames == 0:
        dur = float(video.get("duration") or 0)
        frames = int(round(dur * 30))
    assert abs(frames - 75) <= 2


@skip_no_ffmpeg
def test_three_windows_from_one_file_keep_audio(tmp_path: Path) -> None:
    src = _tone(tmp_path / "long.mp4", seconds=8.0)
    editor = Editor(workspace=tmp_path, runner=FfmpegRunner())
    editor.project_create(name="reel", project_dir=str(tmp_path / "reel"))
    editor.import_file(str(src))
    mid = editor.media[0].id
    editor.clip_add(media_id=mid, in_s=0.0, duration_s=2.5)
    editor.clip_add(media_id=mid, in_s=2.5, duration_s=2.5)
    editor.clip_add(media_id=mid, in_s=5.0, duration_s=2.5)
    assert editor.review_report(allow_dense=True)["ok"] is True
    exported = editor.export()
    assert exported["ok"] is True, exported
    payload = _probe(Path(exported["hero"]))
    kinds = {s["codec_type"] for s in payload["streams"]}
    assert "audio" in kinds
    audio = next(s for s in payload["streams"] if s["codec_type"] == "audio")
    assert audio["codec_name"] == "aac"
    assert int(audio["sample_rate"]) == 48000


@skip_no_ffmpeg
def test_speech_loudnorm_aac_48k_near_target(tmp_path: Path) -> None:
    src = _tone(tmp_path / "tone.mp4", seconds=5.0)
    editor = Editor(workspace=tmp_path, runner=FfmpegRunner())
    editor.project_create(name="reel", project_dir=str(tmp_path / "reel"))
    editor.import_file(str(src))
    editor.clip_add(media_id=editor.media[0].id, duration_s=5.0)
    editor.project_set(loudnorm="speech")
    assert editor.review_report()["ok"] is True
    exported = editor.export()
    assert exported["ok"] is True, exported
    payload = _probe(Path(exported["hero"]))
    audio = next(s for s in payload["streams"] if s["codec_type"] == "audio")
    assert audio["codec_name"] == "aac"
    assert int(audio["sample_rate"]) == 48000
    assert audio.get("profile", "LC") in ("LC", "AAC LC", "mp4a.40.2")
    integrated = _ebur128_i(Path(exported["hero"]))
    if integrated is not None:
        assert abs(integrated - (-14.0)) <= 1.5

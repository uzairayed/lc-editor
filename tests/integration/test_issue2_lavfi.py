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


def _color_clip(dest: Path, color: str, seconds: float = 2.0) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        ffmpeg,
        "-nostdin",
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"color=c={color}:s=1080x1920:d={seconds}:r=30",
        "-pix_fmt",
        "yuv420p",
        str(dest),
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    return dest


def _fake_wind(dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        ffmpeg,
        "-nostdin",
        "-y",
        "-f",
        "lavfi",
        "-i",
        "anoisesrc=color=pink:d=3,asplit[a][b];[a]highpass=f=50,lowpass=f=400,volume=3dB[r];"
        "[b]highpass=f=2000,volume=-6dB[h];[r][h]amix=inputs=2",
        str(dest),
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    return dest


@skip_no_ffmpeg
def test_two_block_lavfi_preview_proxy(tmp_path: Path) -> None:
    a = _color_clip(tmp_path / "a.mp4", "0x334455")
    b = _color_clip(tmp_path / "b.mp4", "0xAA7744")
    editor = Editor(workspace=tmp_path, runner=FfmpegRunner())
    editor.project_create(name="reel", project_dir=str(tmp_path / "reel"))
    editor.import_file(str(a))
    editor.import_file(str(b))
    editor.clip_add(media_id=editor.media[0].id, duration_s=2.0)
    editor.clip_add(media_id=editor.media[1].id, duration_s=2.0)
    first = editor.timeline_get()["timeline"]["clips"][0]["id"]
    assert editor.transition_set(first, "whip")["ok"]
    assert editor.transition_set(first, "j_cut")["ok"]
    preview = editor.preview_proxy()
    assert preview["ok"]
    path = Path(preview["path"])
    assert path.exists() and path.stat().st_size > 1000


@skip_no_ffmpeg
def test_fake_wind_denoise_changes_audio(tmp_path: Path) -> None:
    wind = _fake_wind(tmp_path / "fake_wind.wav")
    plate = _color_clip(tmp_path / "plate.mp4", "0x334455", 3.0)
    with_audio = tmp_path / "windy.mp4"
    subprocess.run(
        [
            ffmpeg,
            "-nostdin",
            "-y",
            "-i",
            str(plate),
            "-i",
            str(wind),
            "-c:v",
            "copy",
            "-shortest",
            str(with_audio),
        ],
        check=True,
        capture_output=True,
    )
    editor = Editor(workspace=tmp_path, runner=FfmpegRunner())
    editor.project_create(name="reel", project_dir=str(tmp_path / "reel"))
    editor.import_file(str(with_audio))
    editor.clip_add(media_id=editor.media[0].id, duration_s=3.0)
    clip_id = editor.timeline_get()["timeline"]["clips"][0]["id"]
    editor.audio_denoise(clip_id, "outdoor")
    mix = editor.mix_preview()
    assert mix["post_peak_dbtp"] <= mix["pre_peak_dbtp"]
    dest = tmp_path / "denoised.wav"
    from lc_editor.render.audio import denoise_chain

    chain = denoise_chain("outdoor")
    proc = subprocess.run(
        [ffmpeg, "-nostdin", "-y", "-i", str(wind), "-af", chain, str(dest)],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    assert dest.exists()
    assert dest.read_bytes() != wind.read_bytes()

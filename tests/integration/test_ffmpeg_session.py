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


def _make_clip(dest: Path, seconds: float = 3.0) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        ffmpeg,
        "-y",
        "-f",
        "lavfi",
        "-i",
        "testsrc2=size=1920x1080:rate=30",
        "-f",
        "lavfi",
        "-i",
        "sine=frequency=220:sample_rate=48000",
        "-t",
        str(seconds),
        "-pix_fmt",
        "yuv420p",
        "-shortest",
        str(dest),
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    return dest


@skip_no_ffmpeg
def test_spec_rnd_03_whip_filter_accepted(tmp_path: Path) -> None:
    from lc_editor.render.transitions import whip_filter

    dest = tmp_path / "whip.mp4"
    cmd = [
        ffmpeg,
        "-nostdin",
        "-y",
        "-f",
        "lavfi",
        "-i",
        "testsrc2=size=1080x1920:rate=30:duration=0.5",
        "-f",
        "lavfi",
        "-i",
        "testsrc2=size=1080x1920:rate=30:duration=0.5",
        "-filter_complex",
        whip_filter(),
        "-t",
        "0.3",
        "-an",
        str(dest),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, stdin=subprocess.DEVNULL)
    assert proc.returncode == 0, proc.stderr
    assert dest.exists() and dest.stat().st_size > 0


@skip_no_ffmpeg
def test_spec_ses_08_eleven_call_real_ffmpeg(tmp_path: Path) -> None:
    inbox = tmp_path / "inbox"
    for i in range(3):
        _make_clip(inbox / f"shot{i:02d}.mp4", 4.0)

    editor = Editor(workspace=tmp_path, runner=FfmpegRunner())
    editor.project_create(name="reel", project_dir=str(tmp_path / "reel"))
    imported = editor.import_folder(str(inbox))
    assert imported["ok"]
    editor.contact_sheet()

    ids = []
    for item in editor.media_list()["media"]:
        editor.clip_add(media_id=item["id"], duration_s=4.0)
        ids.append(editor.timeline_get()["timeline"]["clips"][-1]["id"])

    editor.clip_refocus(ids[0], 0.5, 0.4)
    editor.motion_kenburns(ids[1])
    assert editor.caption_add(ids[0], "Hook in one line")["ok"]

    editor.project_set(subject="demo reel", target_duration_s=20.0, caption_mode="sparse")
    editor.audio_bed("room")
    editor.sfx_caption_auto()
    editor.sfx_place("whoosh", 2.0, -12.0)
    editor.grade_preset("neutral")
    editor.overlay_preview("ig")
    editor.preview_stills()
    editor.preview_proxy()
    editor.clip_trim(ids[-1], 0.0, 4.0)
    editor.review_report()
    exported = editor.export()
    assert exported["ok"], exported
    hero = Path(exported["hero"])
    assert hero.exists() and hero.stat().st_size > 1000

    probe = subprocess.run(
        [
            shutil.which("ffprobe") or "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height,codec_name,pix_fmt",
            "-of",
            "csv=p=0",
            str(hero),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "1080" in probe.stdout
    assert "1920" in probe.stdout
    assert Path(exported["sidecar"]).exists()


@skip_no_ffmpeg
def test_spec_rnd_14_luts_shift_pixels(tmp_path: Path) -> None:
    from lc_editor.assets.pack import cube_path
    from lc_editor.render.paths import ffmpeg_path

    src = tmp_path / "plate.png"
    subprocess.run(
        [ffmpeg, "-nostdin", "-y", "-f", "lavfi", "-i", "color=c=0x806040:s=64x64", "-frames:v", "1", str(src)],
        check=True,
        capture_output=True,
    )
    samples = {}
    for name in ("neutral", "winter_trip", "motovlog"):
        dest = tmp_path / f"{name}.png"
        cube = cube_path(name)
        proc = subprocess.run(
            [
                ffmpeg,
                "-nostdin",
                "-y",
                "-i",
                str(src),
                "-vf",
                f"lut3d=file='{ffmpeg_path(cube)}'",
                str(dest),
            ],
            capture_output=True,
            text=True,
        )
        assert proc.returncode == 0, proc.stderr
        samples[name] = dest.read_bytes()
    assert samples["neutral"] != samples["winter_trip"]
    assert samples["neutral"] != samples["motovlog"]
    assert samples["winter_trip"] != samples["motovlog"]

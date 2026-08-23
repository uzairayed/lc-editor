from __future__ import annotations

import hashlib
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


def _fingerprints(folder: Path) -> dict[str, tuple[int, str]]:
    out: dict[str, tuple[int, str]] = {}
    for path in sorted(folder.glob("*.mp4")):
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        out[path.name] = (path.stat().st_mtime_ns, digest)
    return out


def _probe_hero(path: Path) -> tuple[int, int, float]:
    proc = subprocess.run(
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
            str(path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    width = height = 0
    duration = 0.0
    for line in proc.stdout.splitlines():
        if line.startswith("width="):
            width = int(line.split("=")[1])
        elif line.startswith("height="):
            height = int(line.split("=")[1])
        elif line.startswith("duration="):
            duration = float(line.split("=")[1])
    return width, height, duration


@skip_no_ffmpeg
def test_look_only_change_reuses_clip_intermediates(tmp_path: Path) -> None:
    a = _clip(tmp_path / "a.mp4")
    b = _clip(tmp_path / "b.mp4")
    editor = Editor(workspace=tmp_path, runner=FfmpegRunner())
    editor.project_create(name="reel", project_dir=str(tmp_path / "reel"))
    editor.import_file(str(a))
    editor.import_file(str(b))
    editor.clip_add(media_id=editor.media[0].id, in_s=0.0, out_s=2.0)
    editor.clip_add(media_id=editor.media[1].id, in_s=0.0, out_s=2.0)
    ins = [(c["in_s"], c["out_s"]) for c in editor.timeline_get()["timeline"]["clips"]]
    review = editor.review_report()
    assert review["ok"], review
    first = editor.export()
    assert first["ok"], first
    hero_a = Path(first["hero"]).read_bytes()
    width, height, dur_a = _probe_hero(Path(first["hero"]))
    assert width == 1080
    assert height == 1920
    cache = editor.store.clip_cache_dir
    before = _fingerprints(cache)
    assert before
    editor.adjustment_set(grade="motovlog", grain=0.2)
    second = editor.export()
    assert second["ok"], second
    after = _fingerprints(cache)
    assert after == before
    hero_b_path = Path(second["hero"])
    assert hero_a != hero_b_path.read_bytes()
    width_b, height_b, dur_b = _probe_hero(hero_b_path)
    assert width_b == 1080
    assert height_b == 1920
    assert abs(dur_b - dur_a) <= 0.15
    later = [(c["in_s"], c["out_s"]) for c in editor.timeline_get()["timeline"]["clips"]]
    assert later == ins

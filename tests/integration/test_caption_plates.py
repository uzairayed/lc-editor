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


def _plate(dest: Path, color: str) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            ffmpeg,
            "-nostdin",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"color=c={color}:s=1080x1920:d=3",
            "-frames:v",
            "1",
            str(dest),
        ],
        check=True,
        capture_output=True,
    )
    return dest


@skip_no_ffmpeg
def test_dark_plate_three_line_explainer(tmp_path: Path) -> None:
    plate = _plate(tmp_path / "cap_dark3.jpg", "0x1A1410")
    editor = Editor(workspace=tmp_path, runner=FfmpegRunner())
    editor.project_create(name="reel", project_dir=str(tmp_path / "reel3"))
    editor.import_file(str(plate))
    editor.clip_add(media_id=editor.media[0].id, duration_s=4.0)
    clip_id = editor.timeline_get()["timeline"]["clips"][0]["id"]
    text = "600-year-old city of tombs, 2 hours from Karachi"
    added = editor.caption_add(clip_id, text)
    assert added["ok"], added
    lint = editor.caption_lint()
    assert lint["ok"], lint
    assert len(lint["lines"]) == 3
    assert lint["hold_s"] >= 1.80
    assert lint["bbox"]["x"] >= 64
    assert lint["bbox"]["x2"] <= 853
    assert lint["bbox"]["y"] >= 422
    assert lint["bbox"]["y2"] <= 960
    proof = Path(lint["phone_proof"])
    assert proof.exists() and proof.stat().st_size > 2000


@skip_no_ffmpeg
def test_three_line_short_clip_rejected(tmp_path: Path) -> None:
    plate = _plate(tmp_path / "cap_short.jpg", "0x1A1410")
    editor = Editor(workspace=tmp_path, runner=FfmpegRunner())
    editor.project_create(name="reel", project_dir=str(tmp_path / "reel_short"))
    editor.import_file(str(plate))
    editor.clip_add(media_id=editor.media[0].id, duration_s=1.2)
    clip_id = editor.timeline_get()["timeline"]["clips"][0]["id"]
    text = "600-year-old city of tombs, 2 hours from Karachi"
    added = editor.caption_add(clip_id, text)
    assert added["ok"] is False
    assert any("SPEC-CAP-02" in w for w in added["warnings"])


@skip_no_ffmpeg
def test_dark_plate_lint_ok(tmp_path: Path) -> None:
    plate = _plate(tmp_path / "cap_dark.jpg", "0x1A1410")
    editor = Editor(workspace=tmp_path, runner=FfmpegRunner())
    editor.project_create(name="reel", project_dir=str(tmp_path / "reel"))
    editor.import_file(str(plate))
    editor.clip_add(media_id=editor.media[0].id, duration_s=3.0)
    clip_id = editor.timeline_get()["timeline"]["clips"][0]["id"]
    added = editor.caption_add(clip_id, "600-year-old city of tombs")
    assert added["ok"]
    lint = editor.caption_lint()
    assert lint["ok"], lint
    assert lint["hold_s"] >= 1.8
    assert lint["bbox"]["y"] >= 270
    assert lint["bbox"]["y2"] <= 1248
    proof = Path(lint["phone_proof"])
    assert proof.exists() and proof.stat().st_size > 2000
    assert "box" not in " ".join(lint["warnings"]).lower()


@skip_no_ffmpeg
def test_bright_plate_contrast_fails(tmp_path: Path) -> None:
    plate = _plate(tmp_path / "cap_bright.jpg", "0xF6EBD4")
    editor = Editor(workspace=tmp_path, runner=FfmpegRunner())
    editor.project_create(name="reel", project_dir=str(tmp_path / "reel"))
    editor.import_file(str(plate))
    editor.clip_add(media_id=editor.media[0].id, duration_s=3.0)
    clip_id = editor.timeline_get()["timeline"]["clips"][0]["id"]
    added = editor.caption_add(clip_id, "600-year-old city of tombs")
    assert added["ok"]
    lint = editor.caption_lint()
    assert lint["ok"] is False
    blob = " ".join(lint["errors"] + lint["warnings"])
    assert "SPEC-CAP-06" in blob
    assert "box" not in blob.lower() or "never" in blob.lower()

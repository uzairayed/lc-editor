from __future__ import annotations

from pathlib import Path

import pytest

from lc_editor.app import Editor
from lc_editor.render.runner import FfmpegRunner, find_tool


def _have_ffmpeg() -> bool:
    try:
        find_tool("ffmpeg")
        find_tool("ffprobe")
        return True
    except FileNotFoundError:
        return False


@pytest.mark.integration
def test_layout_stack_v_export(tmp_path: Path) -> None:
    if not _have_ffmpeg():
        pytest.skip("ffmpeg not on PATH")
    runner = FfmpegRunner()
    top = tmp_path / "top.mp4"
    bot = tmp_path / "bot.mp4"
    runner.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=0x8B3A2A:s=1920x1080:d=3:r=30",
            str(top),
        ]
    )
    runner.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=0xF4A300:s=1920x1080:d=3:r=30",
            str(bot),
        ]
    )
    editor = Editor(workspace=tmp_path, runner=runner)
    editor.project_create(name="pair", project_dir=str(tmp_path / "pair"))
    editor.import_file(str(top))
    editor.import_file(str(bot))
    added = editor.layout_add(
        kind="stack_v",
        panes=[{"media_id": editor.media[0].id}, {"media_id": editor.media[1].id}],
        duration_s=2.5,
    )
    assert added["ok"] is True
    stills = editor.preview_stills()
    assert stills["ok"] is True
    assert Path(stills["paths"][0]).stat().st_size > 200
    preview = editor.preview_proxy()
    assert preview["ok"] is True
    assert Path(preview["path"]).stat().st_size > 200
    review = editor.review_report()
    assert review["ok"] is True
    exported = editor.export()
    assert exported["ok"] is True
    assert Path(exported["hero"]).stat().st_size > 200
    assert Path(exported["sidecar"]).exists()

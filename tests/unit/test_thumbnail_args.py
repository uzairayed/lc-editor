from __future__ import annotations

from pathlib import Path

from lc_editor.render.jobs import extract_frame_args
from tests.conftest import touch_media


def test_issue_1_still_has_no_input_seek() -> None:
    args = extract_frame_args("ffmpeg", "a.jpg", "t.jpg", kind="image", seek_s=0.1)
    assert "-ss" not in args
    assert args[args.index("-i") + 1] == "a.jpg"
    assert "-update" in args


def test_issue_1_video_seeks_after_input() -> None:
    args = extract_frame_args("ffmpeg", "a.mp4", "t.jpg", kind="video", seek_s=0.1)
    assert args.index("-i") < args.index("-ss")
    assert args[args.index("-ss") + 1] == "0.1"


def test_issue_1_thumbnail_still_args(editor, tmp_path: Path, runner) -> None:
    still = touch_media(tmp_path / "src", "frame", ".jpg")
    editor.import_file(str(still))
    editor.thumbnail(editor.media[-1].id)
    thumb_calls = [c for c in runner.calls if "-frames:v" in c and str(editor.media[-1].path) in c]
    assert thumb_calls
    args = thumb_calls[0]
    assert "-ss" not in args

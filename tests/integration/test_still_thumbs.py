from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
from PIL import Image

from lc_editor.app import Editor
from lc_editor.render.runner import FfmpegRunner

ffmpeg = shutil.which("ffmpeg")
pytestmark = pytest.mark.integration
skip_no_ffmpeg = pytest.mark.skipif(ffmpeg is None, reason="ffmpeg not on PATH")


def _tiny_still(dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        ffmpeg,
        "-nostdin",
        "-y",
        "-f",
        "lavfi",
        "-i",
        "color=c=red:s=1080x1920:d=0.04",
        "-frames:v",
        "1",
        str(dest),
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    return dest


@skip_no_ffmpeg
def test_issue_1_still_thumbnail_and_contact_sheet(tmp_path: Path) -> None:
    still = _tiny_still(tmp_path / "stills" / "a.jpg")
    editor = Editor(workspace=tmp_path, runner=FfmpegRunner())
    editor.project_create(name="reel", project_dir=str(tmp_path / "reel"))
    editor.import_folder(str(still.parent))
    thumb = editor.thumbnail(editor.media[0].id)
    sheet = editor.contact_sheet()
    for key, payload in (("thumb", thumb), ("sheet", sheet)):
        path = Path(payload["path"])
        assert path.is_file(), key
        assert path.stat().st_size > 100, (key, path.stat().st_size)
        with Image.open(path) as im:
            im.verify()

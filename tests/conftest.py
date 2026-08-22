from __future__ import annotations

from pathlib import Path

import pytest

from lc_editor.app import Editor
from lc_editor.render.runner import FakeRunner


@pytest.fixture
def runner() -> FakeRunner:
    return FakeRunner(duration_s=5.0, width=1920, height=1080)


@pytest.fixture
def editor(tmp_path: Path, runner: FakeRunner) -> Editor:
    ed = Editor(workspace=tmp_path, runner=runner)
    ed.project_create(name="reel", project_dir=str(tmp_path / "reel"))
    return ed


def touch_media(folder: Path, name: str, suffix: str = ".mp4") -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{name}{suffix}"
    path.write_bytes(b"src")
    return path


@pytest.fixture
def media_file(tmp_path: Path) -> Path:
    return touch_media(tmp_path / "src", "shot")
